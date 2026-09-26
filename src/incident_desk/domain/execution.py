"""Observable deterministic execution contracts, with no provider calls."""

from dataclasses import dataclass
from typing import Protocol


class RetryableExecutionError(Exception):
    """Explicit transient executor failure; exception text is never persisted."""


class NonRetryableExecutionError(Exception):
    """Invalid or missing fixture input."""


@dataclass(frozen=True)
class StepResult:
    kind: str
    output: dict[str, object]


class Executor(Protocol):
    def __call__(self, service_id: str, incident_id: str) -> list[StepResult]: ...
