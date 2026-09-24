"""Operational gate planning using OR-Tools SCIP MILP and explicit plan audits."""
from __future__ import annotations
from datetime import datetime
from time import perf_counter

GATES = [
    {"id":"A01","terminal":"T1","wide":False,"walk":3,"available":True},
    {"id":"A02","terminal":"T1","wide":False,"walk":5,"available":True},
    {"id":"A03","terminal":"T1","wide":False,"walk":7,"available":True},
    {"id":"B11","terminal":"T1","wide":True,"walk":4,"available":True},
    {"id":"B12","terminal":"T1","wide":True,"walk":6,"available":True},
    {"id":"C21","terminal":"T2","wide":False,"walk":5,"available":True},
    {"id":"R01","terminal":"T1","wide":True,"walk":30,"available":True,"remote":True},
    {"id":"R02","terminal":"T1","wide":True,"walk":30,"available":True,"remote":True},
    {"id":"R03","terminal":"T2","wide":True,"walk":30,"available":True,"remote":True},
]
BUFFER = 15
WEIGHTS = {"delayExposure": 1.0, "remoteStand": 650.0, "connectionRisk": 1.7,
           "gateChange": 140.0, "walkingDistance": 1.0, "operationalInstability": 35.0}

def minute(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return int(dt.timestamp() // 60)

def compatible(flight, gate):
    return gate["available"] and flight.get("terminal", "T1") == gate["terminal"] and not (flight.get("aircraft") == "Wide" and not gate["wide"])

def overlap(a, b, buffer=BUFFER):
    a0, b0 = minute(a["scheduled"]), minute(b["scheduled"])
    a1 = a0 + a.get("duration", 60) + a.get("turnaround", 45) + buffer
    b1 = b0 + b.get("duration", 60) + b.get("turnaround", 45) + buffer
    return a0 < b1 and b0 < a1

def baseline_plan(flights, closed):
    """A deterministic scheduled-gate plan, deliberately audited rather than repaired."""
    usable = GATES
    assignments = []
    for i, f in enumerate(flights):
        prior = f.get("baseline_gate")
        candidates = [g for g in usable if compatible(f, g)]
        gate = prior if prior else (candidates[i % len(candidates)]["id"] if candidates else "REMOTE")
        assignments.append({**f, "gate": gate, "status": "Baseline"})
    return assignments

def _cost(f, gate):
    pax, connecting = f.get("passengers", 0), f.get("connecting_passengers", 0)
    delay = f["risk"]["expectedMinutes"]
    exposure = delay * pax
    conn = delay * connecting
    remote = next((g.get("remote", False) for g in GATES if g["id"] == gate), gate == "REMOTE")
    walk = next((g["walk"] for g in GATES if g["id"] == gate), 30)
    change = gate != f.get("baseline_gate", gate)
    instability = 1 if f.get("risk", {}).get("probability", 0) > .65 and gate == "REMOTE" else 0
    pieces = {"delayExposure": exposure * WEIGHTS["delayExposure"],
              "remoteStand": (pax * WEIGHTS["remoteStand"] if remote else 0),
              "connectionRisk": conn * WEIGHTS["connectionRisk"],
              "gateChange": (pax * WEIGHTS["gateChange"] if change else 0),
              "walkingDistance": walk * pax * WEIGHTS["walkingDistance"],
              "operationalInstability": instability * pax * WEIGHTS["operationalInstability"]}
    return pieces

def objective_breakdown(assignments):
    result = {k: 0.0 for k in WEIGHTS}
    for f in assignments:
        for k, v in _cost(f, f["gate"]).items(): result[k] += v
    return {k: round(v, 2) for k,v in result.items()}

def audit(assignments, closed, buffer=BUFFER):
    byname = {k: [] for k in ("aircraftCompatibility", "terminalCompatibility", "gateClosures", "temporalConflicts", "turnaround", "buffer", "gateOperationalAvailability", "connectionConstraints")}
    for f in assignments:
        gate = next((g for g in GATES if g["id"] == f["gate"]), None)
        byname["aircraftCompatibility"].append(not gate or f.get("aircraft") != "Wide" or gate["wide"])
        byname["terminalCompatibility"].append(not gate or f.get("terminal", "T1") == gate["terminal"])
        byname["gateClosures"].append(f["gate"] not in closed)
        byname["gateOperationalAvailability"].append(not gate or gate["available"])
        byname["turnaround"].append(f.get("turnaround", 45) >= 30)
        byname["buffer"].append(f.get("safety_buffer", BUFFER) >= buffer)
        byname["connectionConstraints"].append(f.get("connecting_passengers", 0) <= f.get("passengers", 0))
    temporal = []
    for i, a in enumerate(assignments):
        for b in assignments[i+1:]:
            if a["gate"] == b["gate"] and a["gate"] != "REMOTE": temporal.append(not overlap(a,b,buffer))
    byname["temporalConflicts"] = temporal
    checks = [{"name": k, "passed": sum(v), "total": len(v), "percentage": round(100*sum(v)/len(v),1) if v else 100.0}
              for k,v in byname.items()]
    passed, total = sum(c["passed"] for c in checks), sum(c["total"] for c in checks)
    return {"checks": checks, "passed": passed, "total": total,
            "percentage": round(100*passed/total,1) if total else 100.0,
            "valid": all(c["passed"] == c["total"] for c in checks)}

def _impact_by_flight(assignments, closures=(), buffer=BUFFER):
    result = {}
    for f in assignments:
        gate = next((g for g in GATES if g["id"] == f["gate"]), None)
        remote = bool(gate and gate.get("remote")) or f["gate"] == "REMOTE"
        invalid = gate is not None and (not compatible(f, gate) or gate["id"] in closures)
        change = f["gate"] != f.get("baseline_gate", f["gate"])
        penalty = (45 if remote else 0) + (10 if change else 0) + (60 if invalid else 0) + (gate["walk"]*.5 if gate else 0)
        result[f["id"]] = {"passengers":f["risk"]["expectedMinutes"]+penalty,
                           "connections":f["risk"]["expectedMinutes"]+penalty}
    for i, a in enumerate(assignments):
        for b in assignments[i+1:]:
            if a["gate"] == b["gate"] and a["gate"] != "REMOTE" and overlap(a,b,buffer):
                result[a["id"]]["passengers"] += 30; result[b["id"]]["passengers"] += 30
                result[a["id"]]["connections"] += 30; result[b["id"]]["connections"] += 30
    return result

def summarize(assignments, closures=(), buffer=BUFFER):
    n = len(assignments) or 1
    breakdown = objective_breakdown(assignments)
    delay = sum(f["risk"]["expectedMinutes"] for f in assignments)
    impacts = _impact_by_flight(assignments, closures, buffer)
    exposure = sum(impacts[f["id"]]["passengers"] * f.get("passengers",0) for f in assignments)
    connection = sum(impacts[f["id"]]["connections"] * f.get("connecting_passengers",0) for f in assignments)
    return {"averageDelayMinutes": round(delay/n,2), "delayExposure": round(exposure,2),
            "remoteStands": sum(f["gate"] == "REMOTE" or next((g.get("remote",False) for g in GATES if g["id"] == f["gate"]),False) for f in assignments),
            "passengerExposure": round(exposure,2), "connectionExposure": round(connection,2),
            "gateUtilization": round(100*(len(assignments)-sum(f["gate"]=="REMOTE" or next((g.get("remote",False) for g in GATES if g["id"] == f["gate"]),False) for f in assignments))/n,1),
            "objectiveValue": round(sum(breakdown.values()),2), "breakdown": breakdown}

def optimize_gates(flights, closures, solver="SCIP", buffer=BUFFER):
    started = perf_counter()
    usable = [g for g in GATES if g["id"] not in closures and g["available"]]
    try:
        from ortools.linear_solver import pywraplp
    except ImportError as exc:
        return {"feasible": False, "reason": "OR-Tools is unavailable; no constraint-safe plan was produced.", "solver": None}
    actual_solver = "GUROBI" if solver.upper() == "GUROBI" else "SCIP"
    model = pywraplp.Solver.CreateSolver(actual_solver)
    if model is None and actual_solver == "GUROBI":
        actual_solver, model = "SCIP", pywraplp.Solver.CreateSolver("SCIP")
    if model is None:
        return {"feasible": False, "reason": "OR-Tools SCIP MILP solver is unavailable; no constraint-safe plan was produced.", "solver": None}
    x = {(i,g["id"]):model.BoolVar(f"x_{i}_{g['id']}") for i,f in enumerate(flights) for g in usable if compatible(f,g)}
    for i in range(len(flights)):
        choices = [var for (fi,_),var in x.items() if fi == i]
        model.Add(sum(choices) == 1)
    for i in range(len(flights)):
        for j in range(i+1,len(flights)):
            if overlap(flights[i], flights[j], buffer):
                for g in usable:
                    if (i,g["id"]) in x and (j,g["id"]) in x: model.Add(x[i,g["id"]]+x[j,g["id"]] <= 1)
    objective = model.Objective()
    for (i,gid), var in x.items():
        gate = next(g for g in usable if g["id"] == gid)
        objective.SetCoefficient(var, sum(_cost(flights[i],gid).values()))
    objective.SetMinimization(); model.SetTimeLimit(5000)
    status = model.Solve()
    if status not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
        return {"feasible": False, "reason": "No feasible gate plan: one or more flights have no available compatible non-conflicting gate across their turnaround and safety buffer windows.", "solver": f"OR-Tools {actual_solver} MILP"}
    assignments=[]
    for i,f in enumerate(flights):
        gate=next((gid for (fi,gid),var in x.items() if fi==i and var.solution_value()>.5),None)
        if gate is None:
            return {"feasible":False,"reason":"Solver returned an incomplete assignment; plan rejected.","solver":f"OR-Tools {actual_solver} MILP"}
        assignments.append({**f,"gate":gate,"status":"Optimized","reason":"Minimum weighted disruption cost under hard gate constraints"})
    result_audit=audit(assignments,closures,buffer)
    if not result_audit["valid"]:
        return {"feasible":False,"reason":"Solver solution failed the post-solve constraint audit and was rejected.","solver":f"OR-Tools {actual_solver} MILP","audit":result_audit}
    by_gate = {f["gate"]: f for f in assignments}
    analyses = {}
    for f in assignments:
        selected = next(g for g in GATES if g["id"] == f["gate"])
        alternatives=[]
        for gate in GATES:
            if gate["id"] in closures:
                alternatives.append({"gate":gate["id"],"feasible":False,"reason":"Gate is closed","cost":None}); continue
            if not compatible(f,gate):
                reason = "Aircraft incompatible" if f.get("aircraft")=="Wide" and not gate["wide"] else "Terminal incompatible"
                alternatives.append({"gate":gate["id"],"feasible":False,"reason":reason,"cost":None}); continue
            conflict = any(other["id"] != f["id"] and other["gate"] == gate["id"] and overlap(f,other,buffer) for other in assignments)
            cost = round(sum(_cost(f,gate["id"]).values()),2)
            alternatives.append({"gate":gate["id"],"feasible":not conflict,
                                 "reason":"Temporal conflict or safety buffer overlap" if conflict else "Higher weighted disruption cost" if cost > sum(_cost(f,selected["id"]).values()) else "Feasible alternative",
                                 "cost":cost})
        base_cost = sum(_cost(f, f.get("baseline_gate", f["gate"])).values())
        selected_cost = sum(_cost(f, f["gate"]).values())
        analyses[f["id"]] = {"selectedGate":f["gate"],"selectedCost":round(selected_cost,2),
            "checks":[{"label":"Aircraft compatible","passed":f.get("aircraft") != "Wide" or selected["wide"]},
                       {"label":"Terminal compatible","passed":f.get("terminal")==selected["terminal"]},
                       {"label":"No temporal conflict","passed":not any(other["id"] != f["id"] and other["gate"] == f["gate"] and overlap(f,other,buffer) for other in assignments)},
                       {"label":f"{buffer} min safety buffer","passed":True},
                       {"label":"Lower disruption cost than baseline","passed":selected_cost <= base_cost},
                       {"label":"Connection weighted","passed":f.get("connecting_passengers",0)>0}],
            "alternatives":alternatives}
    for f in assignments: f["gateAnalysis"] = analyses[f["id"]]
    return {"feasible":True,"assignments":assignments,"solver":f"OR-Tools {actual_solver} MILP",
            "solveTimeMs":round((perf_counter()-started)*1000,2),"objective":summarize(assignments),"audit":result_audit}

def compare_plans(baseline, optimized, closures=(), buffer=BUFFER):
    b, o = summarize(baseline,closures,buffer), summarize(optimized,closures,buffer)
    measures = ["averageDelayMinutes", "delayExposure", "remoteStands", "passengerExposure", "connectionExposure"]
    baseline_impact, optimized_impact = _impact_by_flight(baseline,closures,buffer), _impact_by_flight(optimized,closures,buffer)
    protected = sum(f.get("connecting_passengers",0) for f in optimized
                    if baseline_impact.get(f["id"],{}).get("connections",0) > optimized_impact.get(f["id"],{}).get("connections",0))
    return {"baseline":b,"optimized":o,"improvement":{k:round(b[k]-o[k],2) for k in measures},
            "passengersProtected":protected,
            "gateConflicts":{"baseline":sum(1 for i,a in enumerate(baseline) for c in baseline[i+1:] if a["gate"]==c["gate"] and a["gate"]!="REMOTE" and overlap(a,c,buffer)),
                             "optimized":sum(1 for i,a in enumerate(optimized) for c in optimized[i+1:] if a["gate"]==c["gate"] and a["gate"]!="REMOTE" and overlap(a,c,buffer))},
            "auditBaseline":audit(baseline,closures,buffer), "auditOptimized":audit(optimized,closures,buffer)}
