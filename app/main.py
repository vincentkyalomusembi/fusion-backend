from fastapi import FastAPI

from app.config import settings
from app.routes.hotspots import router as hotspots_router
from app.routes.locations import router as locations_router

app = FastAPI(title=settings.app_name)
app.include_router(locations_router, prefix=settings.api_v1_prefix)
app.include_router(hotspots_router, prefix=settings.api_v1_prefix)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
