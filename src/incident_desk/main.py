"""HTTP application construction without external service dependencies."""

from fastapi import FastAPI

from incident_desk.api.health import router
from incident_desk.config import Settings


def create_app() -> FastAPI:
    """Validate configuration at startup and construct a fresh application."""
    settings = Settings()
    app = FastAPI(title=settings.service_name)
    app.state.settings = settings
    app.include_router(router)
    return app
