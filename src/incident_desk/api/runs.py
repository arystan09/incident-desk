"""Synchronous run endpoints; every database operation runs off the event loop."""

import re
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine

from incident_desk.api.dependencies import current_tenant, get_engine
from incident_desk.domain.runs import IdempotencyConflict, RunRequest
from incident_desk.persistence.database import transaction
from incident_desk.persistence.runs import create_or_replay, find_run

router = APIRouter(prefix="/v1/runs", tags=["runs"])


class RunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    service_id: str
    incident_id: str
    status: str
    created_at: datetime


def idempotency_key(request: Request) -> str:
    keys = request.headers.getlist("idempotency-key")
    if len(keys) != 1 or re.fullmatch(r"[\x21-\x7e]{1,128}", keys[0]) is None:
        raise HTTPException(
            422,
            "Idempotency-Key must be 1-128 printable ASCII characters "
            "without whitespace",
        )
    return keys[0]


@router.post("", response_model=RunResponse, status_code=202)
def post_run(
    body: RunRequest,
    response: Response,
    tenant_id: Annotated[UUID, Depends(current_tenant)],
    key: Annotated[str, Depends(idempotency_key)],
    engine: Annotated[Engine, Depends(get_engine)],
) -> RunResponse:
    try:
        with transaction(engine) as session:
            run = create_or_replay(session, tenant_id, key, body)
            result = RunResponse.model_validate(run)
    except IdempotencyConflict:
        raise HTTPException(
            409, "Idempotency key already used with different input"
        ) from None
    response.headers["Location"] = f"/v1/runs/{result.id}"
    return result


@router.get("/{run_id}", response_model=RunResponse)
def get_run(
    run_id: UUID,
    tenant_id: Annotated[UUID, Depends(current_tenant)],
    engine: Annotated[Engine, Depends(get_engine)],
) -> RunResponse:
    with transaction(engine) as session:
        run = find_run(session, tenant_id, run_id)
        if run is None:
            raise HTTPException(404, "Run not found")
        return RunResponse.model_validate(run)
