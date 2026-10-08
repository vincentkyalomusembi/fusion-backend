from app.services.ml.model_loader import load_model
from app.services.ml.preprocessing import prepare_hazard_features


HAZARD_SCORE_FIELDS = (
    "hazard_score_common",
    "hazard_score_occasional",
    "hazard_score_moderate",
    "hazard_score_severe",
    "hazard_score_extreme",
    "hazard_severity",
)


def predict_hazard_scores(records: list[dict]):
    if not records:
        return []
    predictions = load_model().predict(prepare_hazard_features(records))
    if getattr(predictions, "ndim", 1) != 2 or predictions.shape[1] != len(HAZARD_SCORE_FIELDS):
        raise ValueError(
            f"Hazard model returned shape {getattr(predictions, 'shape', None)}; "
            f"expected one row of {len(HAZARD_SCORE_FIELDS)} scores per input"
        )
    return predictions
