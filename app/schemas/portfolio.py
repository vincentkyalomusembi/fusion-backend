from datetime import datetime
from typing import Any

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
    user_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PortfolioUploadRead(PortfolioRead):
    access_token: str


class ExceedanceCurvePoint(BaseModel):
    return_period_years: int
    annual_exceedance_probability: float
    loss_kes: float


class PortfolioResultsRead(BaseModel):
    portfolio_id: str
    total_tiv_kes: float
    total_rows: int
    eal_common_kes: float
    eal_occasional_kes: float
    eal_moderate_kes: float
    eal_severe_kes: float
    eal_extreme_kes: float
    eal_total_kes: float
    exceedance_curve: list[ExceedanceCurvePoint]
    top_locations: list[dict[str, Any]]
    computed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExplainRequest(BaseModel):
    pass  # no body needed; results are fetched server-side


class ExplainResponse(BaseModel):
    explanation: str


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=20)


class ChatResponse(BaseModel):
    reply: str


class ReportRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class ReportResponse(BaseModel):
    report: str
    actions: list[dict[str, Any]]


class AnalysisResponse(BaseModel):
    portfolio_id: str
    results: PortfolioResultsRead
    report: str
    actions: list[dict[str, Any]]


class AnalysisEmailRequest(BaseModel):
    email: str = Field(pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    attach_csv: bool = False


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
