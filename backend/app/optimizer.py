from datetime import datetime

GATES = [
    {"id": "A01", "terminal": "T1", "wide": False, "walk": 3}, {"id": "A02", "terminal": "T1", "wide": False, "walk": 5},
    {"id": "A03", "terminal": "T1", "wide": False, "walk": 7}, {"id": "B11", "terminal": "T1", "wide": True, "walk": 4},
    {"id": "B12", "terminal": "T1", "wide": True, "walk": 6}, {"id": "C21", "terminal": "T2", "wide": False, "walk": 5},
]
BUFFER = 15

def minute(iso):
    value = iso.replace("Z", "+00:00")
    return datetime.fromisoformat(value).hour * 60 + datetime.fromisoformat(value).minute

def compatible(flight, gate):
    return flight.get("terminal", "T1") == gate["terminal"] and not (flight["aircraft"] == "Wide" and not gate["wide"])

def conflicts(a, b):
    return minute(a["scheduled"]) < minute(b["scheduled"]) + b["duration"] + BUFFER and minute(b["scheduled"]) < minute(a["scheduled"]) + a["duration"] + BUFFER

def optimize_gates(flights, closures):
    # MILP formulation in OR-Tools: x[f,g] is binary when flight f occupies
    # gate g. This is solver-compatible with SCIP (bundled by OR-Tools) and
    # can be switched to Gurobi by replacing the solver name.
    try:
        from ortools.linear_solver import pywraplp
        usable = [g for g in GATES if g["id"] not in closures]
        model = pywraplp.Solver.CreateSolver("SCIP")
        if model is None: raise ImportError("No MILP backend")
        x = {(i, g["id"]): model.BoolVar(f"x_{i}_{g['id']}") for i, f in enumerate(flights) for g in usable if compatible(f, g)}
        remote = {i: model.BoolVar(f"remote_{i}") for i in range(len(flights))}
        for i in range(len(flights)):
            choices = [x[(i, g["id"])] for g in usable if (i, g["id"]) in x]
            model.Add(sum(choices) + remote[i] == 1)
        for i in range(len(flights)):
            for j in range(i + 1, len(flights)):
                if conflicts(flights[i], flights[j]):
                    for g in usable:
                        if (i, g["id"]) in x and (j, g["id"]) in x:
                            model.Add(x[(i, g["id"])] + x[(j, g["id"])] <= 1)
        # Remote parking is expensive, then favor short passenger walks.
        objective = model.Objective()
        for i in range(len(flights)): objective.SetCoefficient(remote[i], flights[i]["passengers"] * 1000)
        for i in range(len(flights)):
            for g in usable:
                if (i, g["id"]) in x: objective.SetCoefficient(x[(i, g["id"])], g["walk"])
        objective.SetMinimization(); model.SetTimeLimit(2000)
        if model.Solve() in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
            assigned = []
            for i, flight in enumerate(flights):
                gate = next((g["id"] for g in usable if (i, g["id"]) in x and x[(i, g["id"])].solution_value() > .5), "REMOTE")
                assigned.append({**flight, "gate": gate, "status": "Optimized" if gate != "REMOTE" else "Exception", "reason": "CP-SAT optimized allocation" if gate != "REMOTE" else "No compatible gate window"})
            assigned.sort(key=lambda f: minute(f["scheduled"]))
            unassigned = [f["id"] for f in assigned if f["gate"] == "REMOTE"]
            return {"assignments": assigned, "unassigned": unassigned, "metrics": {"gateUtilization": round(100 * (len(assigned)-len(unassigned)) / max(1, len(assigned))), "remoteStands": len(unassigned), "passengersProtected": sum(f["passengers"] for f in assigned if f["gate"] != "REMOTE"), "delayExposure": sum(f["risk"]["expectedMinutes"] * f["passengers"] for f in assigned if f["gate"] == "REMOTE")}, "solver": "OR-Tools SCIP MILP optimizer"}
    except ImportError:
        pass
    ordered = sorted(flights, key=lambda f: (-f["risk"]["probability"], minute(f["scheduled"])))
    usable = [g for g in GATES if g["id"] not in closures]
    assigned, unassigned = [], []
    for flight in ordered:
        options = [g for g in usable if compatible(flight, g) and not any(x["gate"] == g["id"] and conflicts(flight, x) for x in assigned)]
        if not options:
            unassigned.append(flight["id"])
            assigned.append({**flight, "gate": "REMOTE", "status": "Exception", "reason": "No compatible gate window"})
            continue
        gate = min(options, key=lambda g: g["walk"] + (8 if flight["risk"]["probability"] > .65 and not g["wide"] else 0))
        assigned.append({**flight, "gate": gate["id"], "status": "Optimized", "reason": "Best compatible gate with conflict buffer"})
    assigned.sort(key=lambda f: minute(f["scheduled"]))
    objective = sum((f["risk"]["expectedMinutes"] * f["passengers"]) for f in assigned if f["gate"] == "REMOTE")
    return {"assignments": assigned, "unassigned": unassigned, "metrics": {"gateUtilization": round(100 * (len(assigned)-len(unassigned)) / max(1, len(assigned))), "remoteStands": len(unassigned), "passengersProtected": sum(f["passengers"] for f in assigned if f["gate"] != "REMOTE"), "delayExposure": objective}, "solver": "Deterministic constraint optimizer (OR-Tools-ready)"}
