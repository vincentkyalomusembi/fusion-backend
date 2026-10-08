from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PortfolioRead(BaseModel):
    id: str
    name: str
    table_name: str
    original_filename: str
    status: str
    error: str | None
    total_rows: int
    dropped_rows: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PortfolioUploadRead(PortfolioRead):
    access_token: str


class PortfolioEmailRequest(BaseModel):
    email: str = Field(pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class PortfolioEmailResponse(BaseModel):
    sent: bool
    message_id: str | None = None


class RecordEdit(BaseModel):
    loc_id: str = Field(min_length=1, max_length=64)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    housing_class: str | None = Field(default=None, max_length=128)
    floor_area_m2: float | None = Field(default=None, ge=0)
    cost_per_m2_kes: float | None = Field(default=None, ge=0)
    tiv_kes: float | None = Field(default=None, ge=0)
    synthetic: bool | None = None
    source: str | None = None


class RecordEditBatch(BaseModel):
    records: list[RecordEdit] = Field(min_length=1, max_length=1000)
