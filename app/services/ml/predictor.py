import numpy as np

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

# Indices of the five ordered tier scores within HAZARD_SCORE_FIELDS.
# hazard_severity (index 5) is a separate scalar and is not part of the tier chain.
_TIER_INDICES = (0, 1, 2, 3, 4)  # common, occasional, moderate, severe, extreme


def predict_hazard_scores(records: list[dict]):
    """Return hazard predictions for a batch of exposure records.

    The saved model (HazardPipeline) already applies the zero cutoff
    (scores < 0.03 → 0.0) internally, so callers receive clean outputs.

    After prediction we assert tier ordering:
        common >= occasional >= moderate >= severe >= extreme
    and raise if any row violates it, so bad model artefacts are caught
    immediately rather than silently producing nonsense loss figures.
    """
    if not records:
        return []

    predictions = load_model().predict(prepare_hazard_features(records))

    if getattr(predictions, "ndim", 1) != 2 or predictions.shape[1] != len(HAZARD_SCORE_FIELDS):
        raise ValueError(
            f"Hazard model returned shape {getattr(predictions, 'shape', None)}; "
            f"expected one row of {len(HAZARD_SCORE_FIELDS)} scores per input"
        )

    # Tier ordering assertion — common >= occasional >= moderate >= severe >= extreme.
    # This should always pass with the retrained model; if it doesn't, the saved
    # artefact is corrupt or was replaced with an incompatible model.
    tiers = predictions[:, list(_TIER_INDICES)]
    violations = np.sum(
        ~(
            (tiers[:, 0] >= tiers[:, 1]) &
            (tiers[:, 1] >= tiers[:, 2]) &
            (tiers[:, 2] >= tiers[:, 3]) &
            (tiers[:, 3] >= tiers[:, 4])
        )
    )
    if violations > 0:
        raise ValueError(
            f"Hazard model produced {violations} tier-ordering violation(s) "
            "(common >= occasional >= moderate >= severe >= extreme broken). "
            "Retrain or replace the model artefact."
        )

    return predictions
