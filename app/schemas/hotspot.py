from pydantic import BaseModel, ConfigDict, Field


class HotspotCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class HotspotRead(HotspotCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)


class HotspotUploadResult(BaseModel):
    received: int
    created: int
    updated: int
