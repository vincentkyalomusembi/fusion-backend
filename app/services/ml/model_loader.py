from functools import lru_cache
from pathlib import Path

import joblib


MODEL_PATH = Path(__file__).resolve().parents[3] / "random_forest_model" / "hazard_random_forest.joblib"


@lru_cache(maxsize=1)
def load_model():
    if not MODEL_PATH.is_file():
        raise FileNotFoundError(f"Hazard model not found at {MODEL_PATH}")
    return joblib.load(MODEL_PATH)
