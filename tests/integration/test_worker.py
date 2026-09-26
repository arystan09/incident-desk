from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from uuid import uuid4

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import IntegrityError

from incident_desk.api.dependencies import get_engine
from incident_desk.config import Settings
from incident_desk.domain.execution import (
    NonRetryableExecutionError,
    RetryableExecutionError,
)
from incident_desk.domain.runs import RunRequest
from incident_desk.fixtures import investigate
from incident_desk.main import create_app
from incident_desk.persistence.database import transaction
from incident_desk.persistence.identity import provision_tenant
from incident_desk.persistence.jobs import LostLease, claim_job, complete, fail
from incident_desk.persistence.models import Job, Run, RunStep
from incident_desk.persistence.runs import create_or_replay
from incident_desk.worker import process_one, run_worker
from tests.integration.conftest import migration_config

pytestmark = pytest.mark.integration


def enqueue(db, incident="fixture-001"):
    with transaction(db) as session:
        tenant, key = provision_tenant(session, "Synthetic worker test")
        run = create_or_replay(
            session,
            tenant,
            "test",
            RunRequest(service_id="checkout", incident_id=incident),
        )
        return run.id, key


def job(db):
    with transaction(db) as session:
        return session.scalars(select(Job)).one()


def expire(db):
    with db.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE jobs SET lease_expires_at=now()-interval '1 second'"
        )


def due(db):
    with db.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE jobs SET next_attempt_at=now()-interval '1 second'"
        )


def test_claim_and_success(database):
    run_id, _ = enqueue(database)
    claim = claim_job(database, "a", Settings())
    assert claim.attempt == claim.generation == 1
    saved = job(database)
    assert saved.status == "running" and saved.lease_owner == "a"
    assert (saved.lease_expires_at - saved.claimed_at).total_seconds() == 60
    with transaction(database) as session:
        assert session.get(Run, run_id).status == "running"
    assert claim_job(database, "b", Settings()) is None
    complete(database, claim, investigate("checkout", "fixture-001"))
    with transaction(database) as session:
        assert session.get(Run, run_id).status == "completed"
        steps = session.scalars(select(RunStep).order_by(RunStep.step_no)).all()
        assert [s.step_no for s in steps] == [1, 2, 3, 4, 5]
        assert [s.kind for s in steps] == [
            "load_fixture",
            "inspect_metrics",
            "inspect_logs",
            "inspect_runbook",
            "summary",
        ]
        assert all(s.status == "completed" and s.completed_at for s in steps)
        assert steps[-1].output_payload["evidence_references"] == [
            "metrics",
            "logs",
            "runbook",
        ]
    assert job(database).status == "completed"
    assert job(database).lease_owner is None
    assert claim_job(database, "c", Settings()) is None


@pytest.mark.parametrize("number", [1, 2])
def test_competing_claims_use_independent_connections(database, number):
    for _ in range(number):
        enqueue(database)
    barrier = Barrier(2)
    pids = set()

    def coordinate(connection, cursor, statement, parameters, context, executemany):
        if "SKIP LOCKED" in statement:
            pids.add(cursor.connection.info.backend_pid)
            barrier.wait(timeout=10)

    event.listen(database, "before_cursor_execute", coordinate)
    try:
        with ThreadPoolExecutor(2) as pool:
            futures = [
                pool.submit(claim_job, database, name, Settings())
                for name in ("a", "b")
            ]
            claims = [f.result(timeout=15) for f in futures]
    finally:
        event.remove(database, "before_cursor_execute", coordinate)
    assert len(pids) == 2
    acquired = [c for c in claims if c]
    assert len(acquired) == number
    assert len({c.job_id for c in acquired}) == number
    assert all(c.attempt == 1 for c in acquired)


def test_expiry_recovery_fences_old_success_and_failure(database):
    enqueue(database)
    old = claim_job(database, "a", Settings())
    expire(database)
    with pytest.raises(LostLease):
        complete(database, old, investigate("checkout", "fixture-001"))
    new = claim_job(database, "b", Settings())
    assert new.attempt == new.generation == 2
    for action in (
        lambda: complete(database, old, []),
        lambda: fail(database, old, Settings(), "internal_failure", False),
    ):
        with pytest.raises(LostLease):
            action()
    complete(database, new, investigate("checkout", "fixture-001"))
    with transaction(database) as session:
        assert session.scalar(select(func.count()).select_from(RunStep)) == 5
        assert session.scalars(select(Run)).one().status == "completed"
    assert job(database).attempt_count == 2


def test_retries_due_time_backoff_and_exhaustion(database):
    enqueue(database)

    def transient(service, incident):
        raise RetryableExecutionError("private diagnostic must not persist")

    for attempt in (1, 2, 3):
        assert process_one(database, Settings(), "worker", transient)
        saved = job(database)
        assert saved.attempt_count == attempt
        assert saved.last_error_code == "transient_failure"
        if attempt < 3:
            assert saved.status == "queued"
            assert claim_job(database, "early", Settings()) is None
            assert (
                saved.next_attempt_at - saved.claimed_at
            ).total_seconds() >= 2**attempt
            due(database)
        else:
            assert saved.status == "failed"
    with transaction(database) as session:
        assert session.scalars(select(Run)).one().status == "failed"
        steps = session.scalars(select(RunStep)).all()
        assert len(steps) == 3
        assert all(
            s.status == "failed" and s.output_payload == {"code": "transient_failure"}
            for s in steps
        )
    assert claim_job(database, "after", Settings()) is None


def test_crashes_also_exhaust_attempt_budget(database):
    enqueue(database)
    for attempt in (1, 2, 3):
        assert claim_job(database, "worker", Settings()).attempt == attempt
        expire(database)
    assert claim_job(database, "new", Settings()) is None
    assert job(database).status == "failed"
    assert job(database).last_error_code == "attempts_exhausted"
    assert job(database).attempt_count == 3


@pytest.mark.parametrize(
    "error,code",
    [
        (NonRetryableExecutionError, "fixture_unavailable"),
        (RuntimeError, "internal_failure"),
    ],
)
def test_terminal_classification(database, error, code):
    enqueue(database)

    def broken(service, incident):
        raise error("never store this")

    assert process_one(database, Settings(), "worker", broken)
    assert job(database).status == "failed"
    assert job(database).last_error_code == code
    assert claim_job(database, "other", Settings()) is None


def test_missing_fixture_does_not_stop_polling(database):
    missing, _ = enqueue(database, "missing")
    valid, _ = enqueue(database)
    assert process_one(database, Settings(), "worker")
    assert process_one(database, Settings(), "worker")
    with transaction(database) as session:
        assert session.get(Run, missing).status == "failed"
        assert session.get(Run, valid).status == "completed"


def test_step_failure_rolls_back_completion(database):
    run_id, _ = enqueue(database)
    claim = claim_job(database, "worker", Settings())
    with database.begin() as connection:
        connection.exec_driver_sql(
            "ALTER TABLE run_steps ADD CONSTRAINT test_failure "
            "CHECK (kind <> 'summary')"
        )
    with pytest.raises(IntegrityError):
        complete(database, claim, investigate("checkout", "fixture-001"))
    with transaction(database) as session:
        assert session.scalar(select(func.count()).select_from(RunStep)) == 0
        assert session.get(Run, run_id).status == "running"
    assert job(database).status == "running"
    fail(database, claim, Settings(), "internal_failure", False)
    assert job(database).status == "failed"


def test_api_worker_tenants_replay_and_get(database):
    app = create_app()
    app.dependency_overrides[get_engine] = lambda: database
    with transaction(database) as session:
        identities = [provision_tenant(session, name) for name in ("one", "two")]
    with TestClient(app) as client:
        runs = []
        for _tenant, key in identities:
            headers = {"Authorization": f"Bearer {key}", "Idempotency-Key": "same"}
            body = {"service_id": "checkout", "incident_id": "fixture-001"}
            response = client.post("/v1/runs", headers=headers, json=body)
            assert response.status_code == 202 and response.json()["status"] == "queued"
            runs.append(response.json()["id"])
            assert process_one(database, Settings(), "worker")
            replay = client.post("/v1/runs", headers=headers, json=body)
            final = client.get(response.headers["location"], headers=headers)
            assert replay.json() == final.json()
            assert final.json()["status"] == "completed"
            assert set(final.json()) == {
                "id",
                "service_id",
                "incident_id",
                "status",
                "created_at",
            }
            other = runs[0] if len(runs) == 2 else str(uuid4())
            assert client.get(f"/v1/runs/{other}", headers=headers).status_code == 404
        assert not process_one(database, Settings(), "worker")
    assert len(set(runs)) == 2
    with transaction(database) as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 2
        assert session.scalar(select(func.count()).select_from(RunStep)) == 10
        assert all(j.attempt_count == 1 for j in session.scalars(select(Job)))


def test_database_loss_logs_no_diagnostics(database, admin_engine, caplog):
    caplog.set_level("INFO", logger="incident_desk.worker")
    stop = Event()

    def terminate(connection, cursor, statement, parameters, context, executemany):
        if "SKIP LOCKED" in statement:
            with admin_engine.connect() as control:
                control.execute(
                    text("SELECT pg_terminate_backend(:pid)"),
                    {"pid": cursor.connection.info.backend_pid},
                )
            stop.set()

    event.listen(database, "before_cursor_execute", terminate)
    try:
        run_worker(database, Settings(), stop)
    finally:
        event.remove(database, "before_cursor_execute", terminate)
    assert '"event": "database_unavailable"' in caplog.text
    assert '"event": "worker_stopping"' in caplog.text
    assert str(database.url.password) not in caplog.text
    assert "SELECT" not in caplog.text


def test_shutdown_finishes_current_work_without_claiming_next(database):
    enqueue(database)
    enqueue(database)
    stop = Event()

    def finish_then_stop(service, incident):
        stop.set()
        # A separate connection proves no execution transaction holds job row locks.
        with database.begin() as connection:
            rows = connection.exec_driver_sql(
                "SELECT id FROM jobs FOR UPDATE NOWAIT"
            ).all()
            assert len(rows) == 2
        return investigate(service, incident)

    run_worker(database, Settings(), stop, finish_then_stop)
    with transaction(database) as session:
        assert sorted(session.scalars(select(Job.status)).all()) == [
            "completed",
            "queued",
        ]


def test_0002_data_preserved_and_processable(empty_database):
    with empty_database.begin() as connection:
        command.upgrade(migration_config(connection), "0002")
    run_id, tenant_id, job_id = uuid4(), uuid4(), uuid4()
    with empty_database.begin() as connection:
        connection.execute(
            text("INSERT INTO tenants (id,name) VALUES (:id,'legacy')"),
            {"id": tenant_id},
        )
        connection.execute(
            text(
                "INSERT INTO runs (id,tenant_id,service_id,incident_id,"
                "idempotency_key,request_hash) "
                "VALUES (:id,:tenant,'checkout','fixture-001','legacy',:hash)"
            ),
            {"id": run_id, "tenant": tenant_id, "hash": "0" * 64},
        )
        connection.execute(
            text("INSERT INTO jobs (id,run_id) VALUES (:id,:run)"),
            {"id": job_id, "run": run_id},
        )
    with empty_database.begin() as connection:
        before = connection.exec_driver_sql(
            "SELECT id,run_id,status,attempt_count,created_at FROM jobs"
        ).one()
        command.upgrade(migration_config(connection), "head")
        after = connection.exec_driver_sql(
            "SELECT id,run_id,status,attempt_count,created_at FROM jobs"
        ).one()
        assert before == after
    assert process_one(empty_database, Settings(), "worker")
    with transaction(empty_database) as session:
        assert session.get(Run, run_id).status == "completed"


def test_transient_failure_then_success_preserves_attempt_history(database):
    enqueue(database)

    def temporary(service, incident):
        raise RetryableExecutionError

    process_one(database, Settings(), "a", temporary)
    due(database)
    process_one(database, Settings(), "b")
    assert job(database).status == "completed"
    assert job(database).attempt_count == 2
    assert job(database).last_error_code is None
    with transaction(database) as session:
        steps = session.scalars(select(RunStep).order_by(RunStep.step_no)).all()
        assert [s.step_no for s in steps] == list(range(1, 7))
        assert steps[0].status == "failed"
        assert all(s.status == "completed" for s in steps[1:])


def test_worker_step_persistence_error_is_terminal_and_atomic(database):
    enqueue(database)
    with database.begin() as connection:
        connection.exec_driver_sql(
            "ALTER TABLE run_steps ADD CONSTRAINT reject_summary "
            "CHECK (kind <> 'summary')"
        )
    assert process_one(database, Settings(), "a")
    assert job(database).status == "failed"
    assert job(database).last_error_code == "internal_failure"
    with transaction(database) as session:
        steps = session.scalars(select(RunStep)).all()
        assert len(steps) == 1 and steps[0].kind == "execution_failure"
        assert session.scalars(select(Run)).one().status == "failed"
