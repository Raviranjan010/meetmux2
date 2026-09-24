"""Offline, deterministic sklearn models with separate training and inference."""
from __future__ import annotations

from pathlib import Path
import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import (f1_score, mean_absolute_error, mean_squared_error,
                             precision_score, recall_score, roc_auc_score, r2_score)
from sklearn.model_selection import train_test_split

FEATURES = ("inbound_delay", "weather", "congestion", "scheduled_hour", "peak_bank",
            "widebody", "flight_duration", "turnaround", "passengers", "connecting_passengers",
            "runway_capacity", "gate_availability")
ARTIFACT = Path(__file__).parent / "demo_models.joblib"
THRESHOLD_MINUTES = 15


def _training_data():
    rng = np.random.default_rng(20260924)
    n = 6000
    inbound = rng.exponential(16, n).clip(0, 150)
    weather, congestion = rng.uniform(0, 100, n), rng.uniform(0, 100, n)
    hour, wide = rng.integers(0, 24, n), rng.integers(0, 2, n)
    peak = ((hour >= 7) & (hour <= 10) | (hour >= 17) & (hour <= 21)).astype(int)
    duration, pax, connecting = rng.integers(35, 180, n), rng.integers(60, 360, n), rng.integers(0, 110, n)
    turnaround, runway, availability = rng.integers(35, 85, n), rng.uniform(.55, 1, n), rng.uniform(.5, 1, n)
    X = np.column_stack((inbound, weather, congestion, hour, peak, wide, duration, turnaround,
                         pax, connecting, runway, availability))
    y = np.clip(1 + .48 * inbound + .105 * weather + .13 * congestion + 6 * peak + 3.2 * wide
                + .025 * duration + .008 * pax + 5 * (1-runway) + rng.normal(0, 5, n), 0, 180)
    return X, y


def train_models(path: Path = ARTIFACT):
    X, y = _training_data()
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=.2, random_state=42)
    reg = HistGradientBoostingRegressor(max_iter=140, max_leaf_nodes=20, learning_rate=.08,
                                        l2_regularization=1.5, random_state=42).fit(X_train, y_train)
    clf = HistGradientBoostingClassifier(max_iter=140, max_leaf_nodes=20, learning_rate=.08,
                                         l2_regularization=1.5, random_state=42).fit(X_train, y_train > THRESHOLD_MINUTES)
    yp, cp = reg.predict(X_test), clf.predict(X_test)
    prob = clf.predict_proba(X_test)[:, 1]
    metrics = {"mae": round(float(mean_absolute_error(y_test, yp)), 3),
               "rmse": round(float(np.sqrt(mean_squared_error(y_test, yp))), 3),
               "r2": round(float(r2_score(y_test, yp)), 3),
               "precision": round(float(precision_score(y_test > THRESHOLD_MINUTES, cp, zero_division=0)), 3),
               "recall": round(float(recall_score(y_test > THRESHOLD_MINUTES, cp, zero_division=0)), 3),
               "f1": round(float(f1_score(y_test > THRESHOLD_MINUTES, cp, zero_division=0)), 3),
               "roc_auc": round(float(roc_auc_score(y_test > THRESHOLD_MINUTES, prob)), 3)}
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"regressor": reg, "classifier": clf, "metrics": metrics,
                 "features": FEATURES, "threshold": THRESHOLD_MINUTES}, path)


class DelayPredictor:
    def __init__(self, path: Path = ARTIFACT):
        if not path.exists():
            raise FileNotFoundError(f"Model artifact is missing at {path}; run `python -m app.train_models` once during build/development.")
        self.bundle = joblib.load(path)

    @property
    def status(self):
        return {"mode": "Simulation / Synthetic Operations Feed", "loaded": True,
                "features": list(FEATURES), "delayThresholdMinutes": THRESHOLD_MINUTES,
                "metrics": self.bundle["metrics"]}

    def predict(self, flight, weather, congestion, runway_capacity=0.82, gate_availability=0.9):
        hour = int(flight["scheduled"][11:13])
        peak = int(7 <= hour <= 10 or 17 <= hour <= 21)
        values = np.array([[flight.get("inbound_delay", 0), weather, congestion, hour, peak,
                            int(flight.get("aircraft") == "Wide"), flight.get("duration", 60),
                            flight.get("turnaround", 45), flight.get("passengers", 120),
                            flight.get("connecting_passengers", 0), runway_capacity, gate_availability]])
        expected = max(0, float(self.bundle["regressor"].predict(values)[0]))
        risk = float(self.bundle["classifier"].predict_proba(values)[0, 1])
        # Transparent input contribution estimates, normalized for display; these are not model SHAP values.
        raw = {"Inbound rotation": flight.get("inbound_delay", 0) * .48,
               "Surface congestion": congestion * .13, "Weather impact": weather * .105,
               "Peak bank": peak * 6, "Runway pressure": (1-runway_capacity) * 5,
               "Connecting passengers": flight.get("connecting_passengers", 0) * .008}
        total = sum(max(0, v) for v in raw.values()) or 1
        drivers = [{"name": k, "value": round(max(0, v), 2), "share": round(max(0, v)/total*100, 1)}
                   for k, v in sorted(raw.items(), key=lambda item: item[1], reverse=True)]
        return {"probability": round(risk, 4), "expectedMinutes": round(expected, 1), "drivers": drivers}
