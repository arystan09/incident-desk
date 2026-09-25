import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import IntegrityError, ProgrammingError

from incident_desk.api.dependencies import get_engine
from incident_desk.main import create_app
from incident_desk.persistence.database import transaction
from incident_desk.persistence.identity import key_digest, provision_tenant
from incident_desk.persistence.models import ApiKey, Job, Run, Tenant
from tests.integration.conftest import migration_config

pytestmark = pytest.mark.integration
BODY = {"service_id": "checkout", "incident_id": "fixture-001"}


@pytest.fixture
def identity(database):
    with transaction(database) as session:
        return provision_tenant(session, "API fixture")


@pytest.fixture
def app(database):
    application = create_app()
    application.dependency_overrides[get_engine] = lambda: database
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


def headers(identity, key="first"):
    return {"Authorization": f"Bearer {identity[1]}", "Idempotency-Key": key}


def counts(database):
    with transaction(database) as session:
        return session.scalar(select(func.count()).select_from(Run)), session.scalar(
            select(func.count()).select_from(Job)
        )


def test_provisioning_stores_only_digest(database, identity):
    with transaction(database) as session:
        tenant = session.get(Tenant, identity[0])
        key = session.scalars(select(ApiKey)).one()
        assert tenant.name == "API fixture"
        assert key.key_digest == hashlib.sha256(identity[1].encode()).hexdigest()
        assert len(key.key_digest) == 64
        assert len(identity[1]) == 43
        assert key.revoked_at is None
        assert "raw_key" not in ApiKey.__table__.columns
        assert key.tenant_id == tenant.id


def test_creation_replay_and_get(client, database, identity):
    first = client.post("/v1/runs", headers=headers(identity), json=BODY)
    assert first.status_code == 202
    body = first.json()
    assert set(body) == {"id", "service_id", "incident_id", "status", "created_at"}
    assert body["status"] == "queued"
    assert body["service_id"] == "checkout"
    assert datetime.fromisoformat(body["created_at"]).utcoffset() is not None
    assert first.headers["location"] == f"/v1/runs/{body['id']}"
    assert (
        client.get(first.headers["location"], headers=headers(identity)).json() == body
    )
    replay = client.post(
        "/v1/runs",
        headers=headers(identity),
        json={"incident_id": " fixture-001 ", "service_id": " checkout "},
    )
    assert replay.status_code == 202 and replay.json() == body
    assert replay.headers["location"] == first.headers["location"]
    assert counts(database) == (1, 1)
    with transaction(database) as session:
        session.get(Run, UUID(body["id"])).status = "completed"
    assert (
        client.post("/v1/runs", headers=headers(identity), json=BODY).json()["status"]
        == "completed"
    )


@pytest.mark.parametrize(
    "auth",
    [
        None,
        "",
        "Basic invalid",
        "Bearer",
        "Bearer short",
        "Bearer " + "x" * 43 + " extra",
        "Bearer " + "x" * 43,
    ],
)
def test_invalid_authentication(client, auth):
    supplied = {} if auth is None else {"Authorization": auth}
    for response in [
        client.post("/v1/runs", headers=supplied, json=BODY),
        client.get(f"/v1/runs/{uuid4()}", headers=supplied),
    ]:
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
        assert response.json() == {"detail": "Invalid or missing API key"}


def test_revoked_and_duplicate_authentication(client, database, identity):
    duplicate = [
        ("Authorization", f"Bearer {identity[1]}"),
        ("Authorization", f"Bearer {identity[1]}"),
    ]
    assert client.get(f"/v1/runs/{uuid4()}", headers=duplicate).status_code == 401
    with transaction(database) as session:
        session.scalars(
            select(ApiKey).where(ApiKey.key_digest == key_digest(identity[1]))
        ).one().revoked_at = datetime.now(UTC)
    assert (
        client.post("/v1/runs", headers=headers(identity), json=BODY).status_code == 401
    )
    assert (
        client.get(f"/v1/runs/{uuid4()}", headers=headers(identity)).status_code == 401
    )


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"service_id": "", "incident_id": "x"},
        {"service_id": "x", "incident_id": " "},
        {"service_id": "x" * 129, "incident_id": "x"},
        {"service_id": "x", "incident_id": "x" * 129},
        {"service_id": 1, "incident_id": "x"},
        BODY | {"tenant_id": str(uuid4())},
    ],
)
def test_invalid_bodies(client, identity, database, body):
    assert (
        client.post("/v1/runs", headers=headers(identity), json=body).status_code == 422
    )
    assert counts(database) == (0, 0)


@pytest.mark.parametrize(
    "key", [None, "", " ", "contains space", "tab\there", "x" * 129, "\x7f", "café"]
)
def test_invalid_idempotency_headers(client, identity, key):
    values = [(b"authorization", f"Bearer {identity[1]}".encode())]
    if key is not None:
        values.append((b"idempotency-key", key.encode("utf-8")))
    assert client.post("/v1/runs", headers=values, json=BODY).status_code == 422


def test_duplicate_idempotency_header(client, identity):
    values = list(headers(identity).items()) + [("Idempotency-Key", "second")]
    assert client.post("/v1/runs", headers=values, json=BODY).status_code == 422


def test_conflict_and_tenant_isolation(client, database, identity):
    with transaction(database) as session:
        other = provision_tenant(session, "Other")
    first = client.post("/v1/runs", headers=headers(identity), json=BODY)
    conflict = client.post(
        "/v1/runs", headers=headers(identity), json=BODY | {"incident_id": "different"}
    )
    assert conflict.status_code == 409
    second = client.post("/v1/runs", headers=headers(other), json=BODY)
    assert second.status_code == 202 and first.json()["id"] != second.json()["id"]
    cross = client.get(first.headers["location"], headers=headers(other))
    missing = client.get(f"/v1/runs/{uuid4()}", headers=headers(other))
    assert cross.status_code == missing.status_code == 404
    assert cross.json() == missing.json() == {"detail": "Run not found"}
    spoof = client.get(
        first.headers["location"] + f"?tenant_id={identity[0]}",
        headers=headers(other) | {"X-Tenant-ID": str(identity[0])},
    )
    assert spoof.status_code == 404
    assert counts(database) == (2, 2)


def test_boundaries_and_case_sensitive_keys(client, database, identity):
    body = {"service_id": "x" * 128, "incident_id": "y" * 128}
    for key in ["a", "A", "!" * 128]:
        assert (
            client.post(
                "/v1/runs", headers=headers(identity, key), json=body
            ).status_code
            == 202
        )
    assert counts(database) == (3, 3)


@pytest.mark.parametrize("conflicting", [False, True])
def test_concurrent_requests(database, identity, conflicting):
    barrier = Barrier(2)
    backend_pids = set()

    def coordinate(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO runs"):
            backend_pids.add(cursor.connection.info.backend_pid)
            barrier.wait(timeout=10)

    event.listen(database, "before_cursor_execute", coordinate)

    def submit(body):
        application = create_app()
        application.dependency_overrides[get_engine] = lambda: database
        with TestClient(application) as client:
            return client.post("/v1/runs", headers=headers(identity), json=body)

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(submit, BODY),
                pool.submit(
                    submit, BODY | ({"incident_id": "other"} if conflicting else {})
                ),
            ]
            responses = [future.result(timeout=20) for future in futures]
    finally:
        event.remove(database, "before_cursor_execute", coordinate)
    assert len(backend_pids) == 2
    assert sorted(r.status_code for r in responses) == (
        [202, 409] if conflicting else [202, 202]
    )
    accepted = [r.json() for r in responses if r.status_code == 202]
    if not conflicting:
        assert accepted[0] == accepted[1]
    with transaction(database) as session:
        run = session.scalars(select(Run)).one()
        assert str(run.id) == accepted[0]["id"]
        assert run.incident_id == accepted[0]["incident_id"]
    assert counts(database) == (1, 1)


def test_job_failure_rolls_back_api_creation(database, app, identity):
    # A real PostgreSQL job constraint failure, not a mocked session.
    with database.begin() as connection:
        connection.exec_driver_sql(
            "ALTER TABLE jobs ADD CONSTRAINT test_reject_job CHECK (attempt_count < 0)"
        )
    with TestClient(app) as client:
        with pytest.raises(IntegrityError):
            client.post("/v1/runs", headers=headers(identity), json=BODY)
    assert counts(database) == (0, 0)
    with database.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE jobs DROP CONSTRAINT test_reject_job")
    with TestClient(app) as client:
        assert (
            client.post("/v1/runs", headers=headers(identity), json=BODY).status_code
            == 202
        )
    assert counts(database) == (1, 1)


def test_schema_errors_are_not_misreported_as_unavailable(database, app, identity):
    with database.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE runs RENAME TO temporarily_missing")
    with TestClient(app) as client:
        with pytest.raises(ProgrammingError):
            client.post("/v1/runs", headers=headers(identity), json=BODY)


def test_legacy_migration_preserves_history(empty_database):
    tenant_id, run_id, job_id, step_id = uuid4(), uuid4(), uuid4(), uuid4()
    with empty_database.begin() as connection:
        config = migration_config(connection)
        command.upgrade(config, "0001")
        connection.execute(
            text(
                "INSERT INTO runs (id,tenant_id,status,state_version) "
                "VALUES (:id,:tenant,'failed',3)"
            ),
            {"id": run_id, "tenant": tenant_id},
        )
        connection.execute(
            text("INSERT INTO jobs (id,run_id) VALUES (:id,:run)"),
            {"id": job_id, "run": run_id},
        )
        connection.execute(
            text(
                "INSERT INTO run_steps (id,run_id,step_no,kind,input_payload) "
                "VALUES (:id,:run,1,'legacy',jsonb_build_object('evidence',true))"
            ),
            {"id": step_id, "run": run_id},
        )
        command.upgrade(config, "head")
    with transaction(empty_database) as session:
        run = session.get(Run, run_id)
        assert (
            run.tenant_id == tenant_id
            and run.status == "failed"
            and run.state_version == 3
        )
        assert run.service_id == "legacy-unassigned"
        assert run.idempotency_key == run.incident_id == f"legacy:{run_id}"
        assert (
            run.request_hash
            == hashlib.sha256(f"legacy-v0:{run_id}".encode()).hexdigest()
        )
        assert session.get(Tenant, tenant_id).name == f"legacy:{tenant_id}"
        assert session.get(Job, job_id).run_id == run_id
        assert session.scalar(
            text("SELECT input_payload FROM run_steps WHERE id=:id"), {"id": step_id}
        ) == {"evidence": True}
        assert session.scalar(select(func.count()).select_from(ApiKey)) == 0
    with pytest.raises(IntegrityError), transaction(empty_database) as session:
        session.add(
            Run(
                tenant_id=uuid4(),
                service_id="x",
                incident_id="y",
                idempotency_key="z",
                request_hash="0" * 64,
            )
        )


def test_actual_database_connection_loss_is_generic(
    database, admin_engine, app, identity
):
    def terminate(connection, cursor, statement, parameters, context, executemany):
        if "api_keys" in statement:
            with admin_engine.connect() as control:
                control.execute(
                    text("SELECT pg_terminate_backend(:pid)"),
                    {"pid": cursor.connection.info.backend_pid},
                )

    event.listen(database, "before_cursor_execute", terminate)
    try:
        with TestClient(app) as client:
            response = client.post("/v1/runs", headers=headers(identity), json=BODY)
            assert response.status_code == 503
            assert response.json() == {"detail": "Database unavailable"}
            assert client.get("/health/live").json() == {"status": "ok"}
    finally:
        event.remove(database, "before_cursor_execute", terminate)


def test_validation_does_not_reflect_secret_input(client, identity):
    response = client.post(
        "/v1/runs", headers=headers(identity), json=BODY | {"api_key": identity[1]}
    )
    assert response.status_code == 422
    assert identity[1] not in response.text


def test_post_ignores_caller_tenant_headers_and_query(client, database, identity):
    with transaction(database) as session:
        other = provision_tenant(session, "Not the caller")
    response = client.post(
        f"/v1/runs?tenant_id={other[0]}",
        headers=headers(identity) | {"X-Tenant-ID": str(other[0])},
        json=BODY,
    )
    assert response.status_code == 202
    with transaction(database) as session:
        assert session.get(Run, UUID(response.json()["id"])).tenant_id == identity[0]
