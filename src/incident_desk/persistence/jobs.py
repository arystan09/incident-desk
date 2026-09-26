"""Short PostgreSQL transactions for claiming and fenced result publication."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import Engine, and_, func, or_, select
from sqlalchemy.orm import Session

from incident_desk.config import Settings
from incident_desk.domain.execution import StepResult
from incident_desk.persistence.database import transaction
from incident_desk.persistence.models import Job, Run, RunStep


@dataclass(frozen=True)
class Claim:
    job_id: UUID
    run_id: UUID
    worker_id: str
    generation: int
    attempt: int
    service_id: str
    incident_id: str


class LostLease(Exception):
    """No result may be published by this attempt."""


def now(session: Session) -> datetime:
    value: datetime = session.execute(select(func.clock_timestamp())).scalar_one()
    return value


def clear_lease(job: Job) -> None:
    job.lease_owner = None
    job.lease_expires_at = None


def claim_job(engine: Engine, worker_id: str, settings: Settings) -> Claim | None:
    with transaction(engine) as session:
        job = session.scalar(
            select(Job)
            .where(
                or_(
                    and_(Job.status == "queued", Job.next_attempt_at <= func.now()),
                    and_(Job.status == "running", Job.lease_expires_at <= func.now()),
                )
            )
            .order_by(Job.next_attempt_at, Job.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return None
        run = session.scalars(
            select(Run).where(Run.id == job.run_id).with_for_update()
        ).one()
        if run.status not in {"queued", "running"}:
            # Preserve terminal history rather than resurrect inconsistent old jobs.
            job.status = "failed"
            job.last_error_code = "run_not_executable"
            clear_lease(job)
            return None
        if job.attempt_count >= settings.worker_max_attempts:
            job.status = run.status = "failed"
            job.last_error_code = "attempts_exhausted"
            run.state_version += 1
            clear_lease(job)
            return None
        job.attempt_count += 1
        job.lease_generation += 1
        job.status = run.status = "running"
        run.state_version += 1
        job.lease_owner = worker_id
        job.claimed_at = now(session)
        job.lease_expires_at = job.claimed_at + timedelta(
            seconds=settings.worker_lease_seconds
        )
        return Claim(
            job.id,
            run.id,
            worker_id,
            job.lease_generation,
            job.attempt_count,
            run.service_id,
            run.incident_id,
        )


def owned(session: Session, claim: Claim) -> tuple[Job, Run]:
    # Lock first, then read database wall time (not transaction-start time).
    job = session.scalars(
        select(Job).where(Job.id == claim.job_id).with_for_update()
    ).one()
    if (
        job.status != "running"
        or job.lease_owner != claim.worker_id
        or job.lease_generation != claim.generation
        or job.lease_expires_at is None
        or job.lease_expires_at <= now(session)
    ):
        raise LostLease
    run = session.scalars(
        select(Run).where(Run.id == job.run_id).with_for_update()
    ).one()
    if run.status != "running":
        raise LostLease
    return job, run


def append_steps(
    session: Session,
    claim: Claim,
    steps: list[StepResult],
    error_code: str | None = None,
) -> None:
    number = (
        session.scalar(
            select(func.max(RunStep.step_no)).where(RunStep.run_id == claim.run_id)
        )
        or 0
    )
    timestamp = now(session)
    for offset, step in enumerate(steps, 1):
        session.add(
            RunStep(
                run_id=claim.run_id,
                step_no=number + offset,
                kind=step.kind,
                status="failed" if error_code else "completed",
                input_payload={
                    "attempt": claim.attempt,
                    "lease_generation": claim.generation,
                },
                output_payload=step.output,
                error_code=error_code,
                completed_at=timestamp,
            )
        )


def complete(engine: Engine, claim: Claim, steps: list[StepResult]) -> None:
    with transaction(engine) as session:
        job, run = owned(session, claim)
        append_steps(session, claim, steps)
        job.status = run.status = "completed"
        job.last_error_code = None
        run.state_version += 1
        clear_lease(job)


def fail(
    engine: Engine, claim: Claim, settings: Settings, code: str, retryable: bool
) -> str:
    with transaction(engine) as session:
        job, run = owned(session, claim)
        retry = retryable and claim.attempt < settings.worker_max_attempts
        job.status = run.status = "queued" if retry else "failed"
        job.last_error_code = code
        run.state_version += 1
        if retry:
            delay = min(
                60, settings.worker_retry_base_seconds * 2 ** (claim.attempt - 1)
            )
            job.next_attempt_at = now(session) + timedelta(seconds=delay)
        append_steps(
            session, claim, [StepResult("execution_failure", {"code": code})], code
        )
        clear_lease(job)
        return "retry_scheduled" if retry else "job_failed"
