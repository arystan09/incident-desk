"""Authentication and lazy application-owned database access."""

import re
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy import Engine

from incident_desk.persistence.database import transaction
from incident_desk.persistence.identity import authenticate


def unauthorized() -> HTTPException:
    return HTTPException(
        401, "Invalid or missing API key", headers={"WWW-Authenticate": "Bearer"}
    )


def bearer_token(request: Request) -> str:
    headers = request.headers.getlist("authorization")
    if len(headers) != 1:
        raise unauthorized()
    match = re.fullmatch(r"(?i:Bearer) ([A-Za-z0-9_-]{43})", headers[0])
    if match is None:
        raise unauthorized()
    return match.group(1)


def get_engine(request: Request) -> Engine:
    engine: Engine | None = request.app.state.engine
    if engine is None:
        raise HTTPException(503, "Database unavailable")
    return engine


def current_tenant(
    token: Annotated[str, Depends(bearer_token)],
    engine: Annotated[Engine, Depends(get_engine)],
) -> UUID:
    with transaction(engine) as session:
        tenant_id = authenticate(session, token)
    if tenant_id is None:
        raise unauthorized()
    return tenant_id
