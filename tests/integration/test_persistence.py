from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from incident_desk.persistence.database import transaction
from incident_desk.persistence.models import Base, Job, Run, RunStep, Tenant
from tests.integration.conftest import migration_config

pytestmark = pytest.mark.integration


def test_migrations_round_trip_and_metadata(empty_database):
    with empty_database.begin() as connection:
        assert inspect(connection).get_table_names() == []
        config = migration_config(connection)
        command.upgrade(config, "head")
        assert set(inspect(connection).get_table_names()) == {
            "alembic_version",
            "runs",
            "jobs",
            "run_steps",
            "tenants",
            "api_keys",
        }
        context = MigrationContext.configure(
            connection, opts={"compare_type": True, "compare_server_default": True}
        )
        assert compare_metadata(context, Base.metadata) == []
        command.downgrade(config, "base")
        assert set(inspect(connection).get_table_names()) <= {"alembic_version"}
        command.upgrade(config, "head")
        assert compare_metadata(context, Base.metadata) == []
        # Alembic autogenerate does not compare CHECK constraints: inspect them too.
        for table in Base.metadata.sorted_tables:
            expected = {
                c.name
                for c in table.constraints
                if c.__class__.__name__ == "CheckConstraint"
            }
            assert {
                c["name"] for c in inspect(connection).get_check_constraints(table.name)
            } == expected


def test_records_and_jsonb_round_trip(database, tenant_id):
    payload = {
        "service": "synthetic-оплата",
        "counts": [1, 2],
        "nested": {"ok": True, "missing": None},
    }
    with transaction(database) as session:
        run = new_run(tenant_id)
        session.add(run)
        session.flush()
        job = Job(run_id=run.id)
        step = RunStep(
            run_id=run.id,
            step_no=1,
            kind="fixture",
            input_payload=payload,
            output_payload={"evidence": ["ref-1"]},
        )
        session.add_all([job, step])
    with transaction(database) as session:
        saved_run = session.get(Run, run.id)
        saved_job = session.get(Job, job.id)
        saved_step = session.get(RunStep, step.id)
        assert saved_run.tenant_id == run.tenant_id
        assert saved_run.status == "queued" and saved_run.state_version == 0
        assert saved_run.created_at.utcoffset() is not None
        assert saved_job.attempt_count == saved_job.lease_generation == 0
        assert saved_job.lease_owner is None and saved_job.lease_expires_at is None
        assert saved_step.input_payload == payload
        assert saved_step.output_payload == {"evidence": ["ref-1"]}
        assert saved_step.completed_at is None
        assert saved_step.started_at.utcoffset() is not None


@pytest.fixture
def run_id(database, tenant_id):
    with transaction(database) as session:
        run = new_run(tenant_id)
        session.add(run)
    return run.id


def test_duplicate_step_rejected(database, run_id):
    with transaction(database) as session:
        session.add(RunStep(run_id=run_id, step_no=1, kind="fixture"))
    with pytest.raises(IntegrityError) as exc, transaction(database) as session:
        session.add(RunStep(run_id=run_id, step_no=1, kind="fixture"))
    assert exc.value.orig.diag.constraint_name == "uq_run_steps_run_step"


def test_duplicate_job_rejected(database, run_id):
    with transaction(database) as session:
        session.add(Job(run_id=run_id))
    with pytest.raises(IntegrityError) as exc, transaction(database) as session:
        session.add(Job(run_id=run_id))
    assert exc.value.orig.diag.constraint_name == "uq_jobs_run_id"


@pytest.mark.parametrize(
    "model,fields,constraint",
    [
        (Run, {"status": "invalid"}, "ck_runs_status"),
        (Run, {"state_version": -1}, "ck_runs_state_version"),
        (Job, {"status": "invalid"}, "ck_jobs_status"),
        (Job, {"attempt_count": -1}, "ck_jobs_attempt_count"),
        (Job, {"lease_generation": -1}, "ck_jobs_lease_generation"),
        (RunStep, {"status": "invalid"}, "ck_run_steps_status"),
        (RunStep, {"step_no": 0}, "ck_run_steps_step_no"),
    ],
)
def test_checks_rejected(database, run_id, tenant_id, model, fields, constraint):
    values = run_values(tenant_id) if model is Run else {"run_id": run_id}
    if model is RunStep:
        values.update(step_no=1, kind="fixture")
    values.update(fields)
    with pytest.raises(IntegrityError) as exc, transaction(database) as session:
        session.add(model(**values))
    assert exc.value.orig.diag.constraint_name == constraint


@pytest.mark.parametrize(
    "model,fields,constraint",
    [
        (Job, {}, "fk_jobs_run_id"),
        (RunStep, {"step_no": 1, "kind": "fixture"}, "fk_run_steps_run_id"),
    ],
)
def test_foreign_key_rejected(database, model, fields, constraint):
    with pytest.raises(IntegrityError) as exc, transaction(database) as session:
        session.add(model(run_id=uuid4(), **fields))
    assert exc.value.orig.diag.constraint_name == constraint


@pytest.mark.parametrize(
    "model,fields", [(Job, {}), (RunStep, {"step_no": 1, "kind": "fixture"})]
)
def test_run_deletion_restricted(database, run_id, model, fields):
    with transaction(database) as session:
        session.add(model(run_id=run_id, **fields))
    with pytest.raises(IntegrityError), transaction(database) as session:
        session.delete(session.get(Run, run_id))
    with transaction(database) as session:
        assert session.get(Run, run_id) is not None


def test_failed_transaction_leaves_no_partial_run_or_job(database, tenant_id):
    run_id = uuid4()
    with pytest.raises(IntegrityError), transaction(database) as session:
        session.add(new_run(tenant_id, id=run_id))
        session.flush()
        session.add(Job(run_id=run_id))
        session.flush()  # Both inserts actually reached PostgreSQL.
        session.add(Job(run_id=run_id))  # Failure at commit must roll back both.
    with transaction(database) as session:
        assert session.get(Run, run_id) is None
        assert session.scalars(select(Job).where(Job.run_id == run_id)).all() == []
        # A subsequent transaction can still commit successfully.
        session.add(new_run(tenant_id, id=run_id))
    with transaction(database) as session:
        assert session.get(Run, run_id) is not None


@pytest.fixture
def tenant_id(database):
    with transaction(database) as session:
        tenant = Tenant(name="Persistence fixture")
        session.add(tenant)
    return tenant.id


def run_values(tenant_id):
    return dict(
        tenant_id=tenant_id,
        service_id="test",
        incident_id="fixture",
        idempotency_key=str(uuid4()),
        request_hash="0" * 64,
    )


def new_run(tenant_id, **overrides):
    return Run(**(run_values(tenant_id) | overrides))
