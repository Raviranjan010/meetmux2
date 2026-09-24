from __future__ import annotations
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator
from .optimizer import GATES, audit, baseline_plan, compare_plans, optimize_gates, summarize
from .predictor import DelayPredictor

DEMO_FLIGHTS = [
 {"id":"f1","airline":"IndiGo","flight":"6E 412","direction":"ARR","scheduled":"2026-09-24T08:15:00+05:30","duration":55,"turnaround":45,"aircraft":"Narrow","terminal":"T1","inbound_delay":12,"passengers":174,"connecting_passengers":31,"baseline_gate":"A01"},
 {"id":"f2","airline":"Air India","flight":"AI 687","direction":"DEP","scheduled":"2026-09-24T08:35:00+05:30","duration":65,"turnaround":50,"aircraft":"Wide","terminal":"T1","inbound_delay":28,"passengers":264,"connecting_passengers":72,"baseline_gate":"B11"},
 {"id":"f3","airline":"IndiGo","flight":"6E 955","direction":"ARR","scheduled":"2026-09-24T09:05:00+05:30","duration":50,"turnaround":45,"aircraft":"Narrow","terminal":"T1","inbound_delay":4,"passengers":148,"connecting_passengers":24,"baseline_gate":"A02"},
 {"id":"f4","airline":"SpiceJet","flight":"SG 247","direction":"DEP","scheduled":"2026-09-24T09:20:00+05:30","duration":50,"turnaround":40,"aircraft":"Narrow","terminal":"T1","inbound_delay":19,"passengers":168,"connecting_passengers":19,"baseline_gate":"A03"},
 {"id":"f5","airline":"Air India","flight":"AI 302","direction":"ARR","scheduled":"2026-09-24T10:10:00+05:30","duration":90,"turnaround":55,"aircraft":"Wide","terminal":"T1","inbound_delay":36,"passengers":298,"connecting_passengers":86,"baseline_gate":"B12"},
 {"id":"f6","airline":"Akasa Air","flight":"QP 153","direction":"DEP","scheduled":"2026-09-24T10:40:00+05:30","duration":45,"turnaround":40,"aircraft":"Narrow","terminal":"T2","inbound_delay":0,"passengers":122,"connecting_passengers":13,"baseline_gate":"C21"},
]

class Flight(BaseModel):
    id: str
    airline: str
    flight: str
    direction: Literal["ARR", "DEP"]
    scheduled: datetime
    duration: int = Field(ge=20, le=300)
    turnaround: int = Field(default=45, ge=30, le=180)
    aircraft: Literal["Narrow", "Wide"] = "Narrow"
    terminal: Literal["T1", "T2"] = "T1"
    inbound_delay: int = Field(default=0, ge=0, le=300)
    passengers: int = Field(default=120, ge=1, le=600)
    connecting_passengers: int = Field(default=0, ge=0, le=600)
    baseline_gate: str | None = None

    @model_validator(mode="after")
    def connecting_passengers_fit_capacity(self):
        if self.connecting_passengers > self.passengers:
            raise ValueError("connecting_passengers cannot exceed passengers")
        return self

class RiskDriver(BaseModel):
    name: str
    value: float
    share: float

class RiskResult(BaseModel):
    probability: float
    expectedMinutes: float
    drivers: list[RiskDriver]

class FlightPlan(Flight):
    risk: RiskResult
    gate: str | None = None
    status: str | None = None
    reason: str | None = None

class ModelStatus(BaseModel):
    mode: str
    loaded: bool
    features: list[str]
    delayThresholdMinutes: int
    metrics: dict[str, float]

class Gate(BaseModel):
    id: str
    terminal: str
    wide: bool
    walk: int
    available: bool

class CheckResult(BaseModel):
    name: str
    passed: int
    total: int
    percentage: float

class AuditResult(BaseModel):
    checks: list[CheckResult]
    passed: int
    total: int
    percentage: float
    valid: bool

class HealthResponse(BaseModel):
    status: str
    mode: str
    engine: str

class PredictionResponse(RiskResult):
    pass

class StateResponse(BaseModel):
    mode: str
    airport: str
    weather: int
    congestion: int
    flights: list[FlightPlan]
    gates: list[Gate]
    model: ModelStatus | None

class PlanResponse(BaseModel):
    runId: str
    generatedAt: datetime
    scenario: str
    mode: str
    feasible: bool
    error: str | None = None
    weather: int | None = None
    congestion: int | None = None
    assignments: list[FlightPlan] | None = None
    baseline: dict
    optimized: dict | None = None
    comparison: dict | None = None
    connectingPassengers: int | None = None
    connectionRisk: float | None = None
    passengersProtected: float | None = None
    connectionExposureReduction: float | None = None
    solver: str | None = None

class HistoryItem(BaseModel):
    runId: str
    generatedAt: datetime
    scenario: str
    feasible: bool

class HistoryResponse(BaseModel):
    items: list[HistoryItem]

class PlanRequest(BaseModel):
    weather: int = Field(default=38, ge=0, le=100)
    congestion: int = Field(default=62, ge=0, le=100)
    gate_closures: list[str] = Field(default_factory=list)
    flights: list[Flight] = Field(default_factory=lambda: [Flight(**f) for f in DEMO_FLIGHTS])
    solver: Literal["SCIP", "GUROBI"] = "SCIP"

class ScenarioRequest(PlanRequest):
    name: str = "Scenario"

class PredictionRequest(BaseModel):
    flight: Flight
    weather: int = Field(ge=0, le=100)
    congestion: int = Field(ge=0, le=100)

predictor: DelayPredictor | None = None
history: dict[str, dict] = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    global predictor
    predictor = DelayPredictor()
    yield

app = FastAPI(title="SkyFlow Airport Operations API", version="2.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

def state_flights(req: PlanRequest):
    if predictor is None: raise HTTPException(503, "Prediction models are not loaded")
    rows=[]
    for model in req.flights:
        f=model.model_dump()
        f["scheduled"]=f["scheduled"].isoformat()
        f["risk"]=predictor.predict(f,req.weather,req.congestion)
        rows.append(f)
    return rows

def plan(req: PlanRequest, scenario_name="Current scenario"):
    flights=state_flights(req)
    baseline=baseline_plan(flights,req.gate_closures)
    outcome=optimize_gates(flights,req.gate_closures,req.solver)
    run_id=str(uuid4())
    if not outcome["feasible"]:
        result={"runId":run_id,"generatedAt":datetime.now(timezone.utc).isoformat(),"scenario":scenario_name,
                "mode":"Simulation / Synthetic Operations Feed","feasible":False,"error":outcome["reason"],
                "baseline":{"assignments":baseline,"metrics":summarize(baseline,req.gate_closures),"audit":audit(baseline,req.gate_closures)},
                "solver":outcome.get("solver")}
    else:
        comparison=compare_plans(baseline,outcome["assignments"],req.gate_closures)
        connecting=sum(f["connecting_passengers"] for f in flights)
        result={"runId":run_id,"generatedAt":datetime.now(timezone.utc).isoformat(),"scenario":scenario_name,
                "mode":"Simulation / Synthetic Operations Feed","feasible":True,"weather":req.weather,"congestion":req.congestion,
                "assignments":outcome["assignments"],"baseline":{"assignments":baseline,"metrics":comparison["baseline"],"audit":comparison["auditBaseline"]},
                "optimized":{"metrics":comparison["optimized"],"audit":outcome["audit"]},"comparison":comparison,
                "connectingPassengers":connecting,"connectionRisk":round(comparison["optimized"]["connectionExposure"],2),
                "passengersProtected":comparison["passengersProtected"],
                "connectionExposureReduction":comparison["improvement"]["connectionExposure"],"solver":outcome["solver"]}
    history[run_id]=result
    return result

@app.get("/health", response_model=HealthResponse)
def health(): return {"status":"ready" if predictor else "loading","mode":"Simulation / Synthetic Operations Feed","engine":"OR-Tools SCIP MILP"}

@app.get("/api/state", response_model=StateResponse)
def get_state():
    req=PlanRequest()
    flights=state_flights(req)
    scheduled=baseline_plan(flights,[])
    return {"mode":"Simulation / Synthetic Operations Feed","airport":"DEL","weather":req.weather,"congestion":req.congestion,
            "flights":scheduled,"gates":GATES,"model":predictor.status if predictor else None}

@app.get("/api/flights", response_model=list[FlightPlan])
def get_flights(): return state_flights(PlanRequest())

@app.get("/api/gates", response_model=list[Gate])
def get_gates(): return GATES

@app.get("/api/model/status", response_model=ModelStatus)
def model_status():
    if predictor is None: raise HTTPException(503,"Prediction models are not loaded")
    return predictor.status

@app.post("/api/predict", response_model=PredictionResponse)
def predict(request: PredictionRequest):
    f=request.flight.model_dump(); f["scheduled"]=f["scheduled"].isoformat()
    return predictor.predict(f,request.weather,request.congestion)

@app.post("/api/optimize", response_model=PlanResponse)
def optimize(request: PlanRequest): return plan(request)

@app.post("/api/scenarios/simulate", response_model=PlanResponse)
def simulate(request: ScenarioRequest): return plan(request,request.name)

@app.get("/api/optimization/history", response_model=HistoryResponse)
def get_history(): return {"items":[{"runId":k,"generatedAt":v["generatedAt"],"scenario":v["scenario"],"feasible":v["feasible"]} for k,v in history.items()]}

@app.get("/api/optimization/{run_id}", response_model=PlanResponse)
def get_run(run_id: str):
    if run_id not in history: raise HTTPException(404,"Optimization run not found")
    return history[run_id]
