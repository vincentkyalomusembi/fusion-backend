import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor


class HazardPipeline:
    """RandomForest + zero cutoff, saved as one object."""

    def __init__(self, model: RandomForestRegressor, cutoff: float):
        self.model = model
        self.cutoff = cutoff

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        out = self.model.predict(X).copy()
        out[out < self.cutoff] = 0.0
        return out
