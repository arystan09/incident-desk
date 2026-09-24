"""Process liveness, deliberately independent of downstream services."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


@router.get("/live", response_model=HealthResponse)
def liveness() -> HealthResponse:
    return HealthResponse()
