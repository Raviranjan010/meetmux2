"""Explicit one-time model training command for the deterministic demo feed."""
from .predictor import train_models

if __name__ == "__main__":
    train_models()
    print("Saved deterministic demo regression and classifier artifacts.")
