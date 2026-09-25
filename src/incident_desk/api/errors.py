"""Public HTTP errors without reflected credentials or database diagnostics."""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import OperationalError, TimeoutError
from starlette.responses import JSONResponse


def database_error(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, OperationalError):
        state = getattr(exc.orig, "sqlstate", None)
        if not (
            exc.connection_invalidated
            or state is None
            or state.startswith("08")
            or state in {"57P01", "57P02", "57P03"}
        ):
            raise exc
    elif not isinstance(exc, TimeoutError):
        raise exc
    return JSONResponse(status_code=503, content={"detail": "Database unavailable"})


def validation_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    # Pydantic's input/context can contain arbitrary caller-provided secrets.
    errors = [
        {"loc": error["loc"], "msg": error["msg"], "type": error["type"]}
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": errors})
