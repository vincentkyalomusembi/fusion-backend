from pydantic import BaseModel, ConfigDict


class LocationRead(BaseModel):
    loc_id: str
    lat: float
    lon: float
    housing_class: str
    floor_area_m2: float
    cost_per_m2_kes: float
    tiv_kes: float
    synthetic: bool
    source: str
    hazard_score_common: float
    hazard_score_occasional: float
    hazard_score_moderate: float
    hazard_score_severe: float
    hazard_score_extreme: float
    hazard_severity: float

    model_config = ConfigDict(from_attributes=True)
