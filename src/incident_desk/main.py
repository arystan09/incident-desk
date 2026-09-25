"""Application factory with lazy database ownership and public liveness."""

from collections.abc import AsyncIterator
from contextlib import ExitStack, asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import OperationalError, TimeoutError
from starlette.concurrency import run_in_threadpool

from incident_desk.api.errors import database_error, validation_error
from incident_desk.api.health import router as health_router
from incident_desk.api.runs import router as runs_router
from incident_desk.config import Settings
from incident_desk.persistence.database import engine_scope


def create_app() -> FastAPI:
    settings = Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        stack = ExitStack()
        try:
            if settings.database_url is not None:
                # Engine construction is lazy: startup never connects or migrates.
                app.state.engine = stack.enter_context(engine_scope(settings))
            yield
        finally:
            await run_in_threadpool(stack.close)
            app.state.engine = None

    app = FastAPI(title=settings.service_name, lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = None
    app.include_router(health_router)
    app.include_router(runs_router)
    app.add_exception_handler(OperationalError, database_error)
    app.add_exception_handler(TimeoutError, database_error)
    app.add_exception_handler(RequestValidationError, validation_error)
    return app
