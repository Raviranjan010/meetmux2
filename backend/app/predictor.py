"""Small, deterministic sklearn delay model suitable for a self-contained demo.

The training data represents historical operational patterns.  Replace
`build_training_set` with an airport's historical A-CDM feed in deployment;
the public API and feature contract remain unchanged.
"""
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

FEATURES = ("weather", "congestion", "inbound_delay", "peak_bank", "widebody")

def build_training_set():
    rng = np.random.default_rng(42)
    n = 1800
    weather = rng.uniform(0, 100, n); congestion = rng.uniform(0, 100, n)
    inbound = rng.exponential(16, n).clip(0, 150); peak = rng.integers(0, 2, n); wide = rng.integers(0, 2, n)
    y = 2.5 + .12 * weather + .15 * congestion + .54 * inbound + 9 * peak + 3.5 * wide + rng.normal(0, 4.5, n)
    return np.column_stack((weather, congestion, inbound, peak, wide)), y.clip(0, 180)

_X, _y = build_training_set()
MODEL = HistGradientBoostingRegressor(max_iter=130, max_leaf_nodes=18, learning_rate=.08, l2_regularization=1.5, random_state=42).fit(_X, _y)

def predict_delay(flight, weather, congestion):
    hour = int(flight["scheduled"][11:13])
    peak = int(7 <= hour <= 10 or 17 <= hour <= 21)
    wide = int(flight.get("aircraft") == "Wide")
    values = np.array([[weather, congestion, flight.get("inbound_delay", 0), peak, wide]])
    expected = int(round(float(MODEL.predict(values)[0])))
    # Converts expected taxi/turn delay to calibrated operational risk band.
    probability = round(float(1 / (1 + np.exp(-(expected - 18) / 9))), 2)
    impacts = [("Inbound rotation", flight.get("inbound_delay", 0) * .54), ("Surface congestion", congestion * .15), ("Weather impact", weather * .12), ("Peak bank", 9 * peak)]
    return {"probability": probability, "expectedMinutes": expected, "drivers": [{"name": k, "impact": round(v)} for k, v in sorted(impacts, key=lambda x: x[1], reverse=True)]}
