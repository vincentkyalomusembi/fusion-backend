from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routes.hotspots import router as hotspots_router
from app.routes.locations import router as locations_router
from app.routes.portfolios import router as portfolios_router

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url] if settings.frontend_url else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(locations_router, prefix=settings.api_v1_prefix)
app.include_router(hotspots_router, prefix=settings.api_v1_prefix)
app.include_router(portfolios_router, prefix=settings.api_v1_prefix)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
