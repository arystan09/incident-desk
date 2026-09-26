"""Run with python -m incident_desk.worker; no startup migrations."""

import json
import logging
import signal
from datetime import UTC, datetime
from threading import Event
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError, SQLAlchemyError, TimeoutError

from incident_desk.config import Settings
from incident_desk.domain.execution import (
    Executor,
    NonRetryableExecutionError,
    RetryableExecutionError,
)
from incident_desk.fixtures import investigate
from incident_desk.persistence.database import engine_scope
from incident_desk.persistence.jobs import Claim, LostLease, claim_job, complete, fail

logger = logging.getLogger("incident_desk.worker")


def emit(
    event: str, worker_id: str, claim: Claim | None = None, step_kind: str | None = None
) -> None:
    fields: dict[str, object] = {
        "event": event,
        "worker_id": worker_id,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    if step_kind is not None:
        fields["step_kind"] = step_kind
    if claim is not None:
        fields.update(
            job_id=str(claim.job_id), run_id=str(claim.run_id), attempt=claim.attempt
        )
    logger.info(json.dumps(fields, sort_keys=True))


def transient(exc: Exception) -> bool:
    if isinstance(exc, (RetryableExecutionError, TimeoutError)):
        return True
    if isinstance(exc, OperationalError):
        state = getattr(exc.orig, "sqlstate", None)
        return (
            exc.connection_invalidated
            or state is None
            or state.startswith("08")
            or state in {"40001", "40P01", "57P01", "57P02", "57P03"}
        )
    return False


def process_one(
    engine: Engine, settings: Settings, worker_id: str, executor: Executor = investigate
) -> bool:
    claim = claim_job(engine, worker_id, settings)
    if claim is None:
        return False
    emit("job_claimed", worker_id, claim)
    emit("run_started", worker_id, claim)
    try:
        steps = executor(claim.service_id, claim.incident_id)
        complete(engine, claim, steps)
    except LostLease:
        emit("lease_lost", worker_id, claim)
    except Exception as exc:
        retryable = transient(exc)
        code = (
            "transient_failure"
            if retryable
            else "fixture_unavailable"
            if isinstance(exc, NonRetryableExecutionError)
            else "internal_failure"
        )
        try:
            event = fail(engine, claim, settings, code, retryable)
            emit(event, worker_id, claim)
        except LostLease:
            emit("lease_lost", worker_id, claim)
        except SQLAlchemyError:
            # If persistence itself is unavailable, expiry recovers the durable claim.
            emit("failure_persistence_unavailable", worker_id, claim)
    else:
        for step in steps:
            emit("step_completed", worker_id, claim, step.kind)
        emit("job_succeeded", worker_id, claim)
    return True


def run_worker(
    engine: Engine, settings: Settings, stop: Event, executor: Executor = investigate
) -> None:
    worker_id = str(uuid4())
    emit("worker_started", worker_id)
    try:
        while not stop.is_set():
            try:
                worked = process_one(engine, settings, worker_id, executor)
            except SQLAlchemyError as exc:
                if not transient(exc):
                    emit("worker_internal_failure", worker_id)
                    raise SystemExit(1) from None
                emit("database_unavailable", worker_id)
                worked = False
            if not worked:
                stop.wait(settings.worker_poll_seconds)
    finally:
        emit("worker_stopping", worker_id)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    stop = Event()

    def shutdown(signum: int, frame: object) -> None:
        stop.set()

    for name in ("SIGINT", "SIGTERM"):
        signal.signal(getattr(signal, name), shutdown)
    try:
        settings = Settings()
        with engine_scope(settings) as engine:
            run_worker(engine, settings, stop)
    except (ValidationError, ValueError):
        logger.error('{"event":"worker_configuration_invalid"}')
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
