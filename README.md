# SkyFlow — Predictive Air Traffic & Gate Optimizer

Hackathon-ready React + FastAPI platform that predicts runway/taxi delay risk and assigns gates with an OR-Tools mixed-integer linear programming (MILP) model.

## Run

```powershell
# API
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# UI (new terminal)
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The UI works in Demo Mode even when the API is not running.

Or run the complete stack with Docker:

```powershell
docker compose up --build
```

Then open `http://localhost:5173`; API documentation is at `http://localhost:8000/docs`.

## Highlights

- Scikit-learn gradient-boosting predictor using weather, surface congestion, inbound delay, peak-bank and aircraft features
- Gate allocation MILP with binary assignment decisions, aircraft compatibility, gate closures, time conflicts and 15-minute safety buffers
- OR-Tools SCIP MILP solver; deterministic heuristic fallback for lightweight demos
- Live operations board, timeline, scenario controls, and disruption-aware recommendations
