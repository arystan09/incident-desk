"""Tenant-scoped run access and PostgreSQL-backed idempotency."""

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from incident_desk.domain.runs import IdempotencyConflict, RunRequest
from incident_desk.persistence.models import Job, Run


def create_or_replay(
    session: Session, tenant_id: UUID, key: str, request: RunRequest
) -> Run:
    digest = request.request_hash()
    statement = (
        insert(Run)
        .values(
            id=uuid4(),
            tenant_id=tenant_id,
            idempotency_key=key,
            service_id=request.service_id,
            incident_id=request.incident_id,
            request_hash=digest,
        )
        .on_conflict_do_nothing(constraint="uq_runs_tenant_idempotency")
        .returning(Run)
    )
    run = session.scalar(statement)
    if run is not None:
        session.add(Job(run_id=run.id))
        session.flush()
        return run
    # READ COMMITTED gives this SELECT a fresh snapshot after the unique-index wait.
    existing = session.scalars(
        select(Run).where(Run.tenant_id == tenant_id, Run.idempotency_key == key)
    ).one()
    if existing.request_hash != digest:
        raise IdempotencyConflict
    return existing


def find_run(session: Session, tenant_id: UUID, run_id: UUID) -> Run | None:
    return session.scalar(
        select(Run).where(Run.id == run_id, Run.tenant_id == tenant_id)
    )
