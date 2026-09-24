# SkyFlow — Airport Operations Decision Support

SkyFlow is a deterministic hackathon demo for airport delay prediction, risk explanation, and gate planning. Its built-in feed is synthetic and is clearly labeled **Simulation / Synthetic Operations Feed**; it is not a live airport feed.

## Run locally

```powershell
# Backend
cd backend
..\.venv\Scripts\python.exe -m pip install -r requirements.txt
..\.venv\Scripts\python.exe -m app.train_models  # one-time model artifact generation
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

# Frontend, in another terminal
cd frontend
npm ci
npm run dev
```

Open `http://localhost:5173`; the API documentation is at `http://localhost:8000/docs`. Docker builds the model artifact in the API image before startup:

```powershell
docker compose up --build
```

## Implemented flow

- Separate Scikit-Learn regression and classification models. The classifier directly predicts `P(delay > 15 minutes)`; it is not derived from regression output. The deterministic synthetic dataset is trained once by `app.train_models` and the saved artifact is loaded during API startup.
- Holdout MAE, RMSE, R², precision, recall, F1, and ROC-AUC are returned from `/api/model/status`. These metrics describe synthetic holdout data, not airport performance.
- Driver values and shares are computed from actual prediction inputs and returned with each flight prediction.
- OR-Tools SCIP MILP uses binary flight/gate assignment variables, with exact assignment, gate/aircraft/terminal compatibility, gate closure, turnaround, safety buffer, and non-overlap constraints. Gurobi is optional; missing Gurobi falls back to SCIP. The solver never describes SCIP as CP-SAT.
- Baseline and optimized plans include calculated cost breakdowns, constraint audits, passenger and connection exposure, gate conflicts, and improvement values. Infeasible instances return an error and no optimized assignments.
- API routes: `/health`, `/api/state`, `/api/flights`, `/api/gates`, `/api/model/status`, `/api/predict`, `/api/optimize`, `/api/scenarios/simulate`, `/api/optimization/history`, and `/api/optimization/{run_id}`.

Replace the synthetic feed and retrain with validated historical A-CDM/ADS-B data before operational use. Prediction explanations are transparent input contribution estimates, not SHAP explanations.
