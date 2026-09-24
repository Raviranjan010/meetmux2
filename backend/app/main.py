from datetime import datetime
from typing import Literal
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from .optimizer import optimize_gates
from .predictor import predict_delay

app = FastAPI(title="SkyFlow Operations API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class Flight(BaseModel):
    id: str
    airline: str
    flight: str
    direction: Literal["ARR", "DEP"]
    scheduled: str
    duration: int = Field(ge=20, le=240)
    aircraft: Literal["Narrow", "Wide"] = "Narrow"
    terminal: str = "T1"
    inbound_delay: int = Field(default=0, ge=0, le=300)
    passengers: int = Field(default=120, ge=1)

class Scenario(BaseModel):
    weather: int = Field(default=20, ge=0, le=100)
    congestion: int = Field(default=45, ge=0, le=100)
    gate_closures: list[str] = []
    flights: list[Flight]

@app.get("/health")
def health():
    return {"status": "ready", "engine": "OR-Tools CP-SAT with heuristic fallback"}

@app.post("/api/optimize")
def optimize(scenario: Scenario):
    flights = [f.model_dump() for f in scenario.flights]
    for flight in flights:
        flight["risk"] = predict_delay(flight, scenario.weather, scenario.congestion)
    result = optimize_gates(flights, scenario.gate_closures)
    return {"generatedAt": datetime.now().isoformat(), "weather": scenario.weather, "congestion": scenario.congestion, **result}
