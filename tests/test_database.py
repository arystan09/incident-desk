import pytest

from incident_desk.config import Settings
from incident_desk.persistence.database import engine_scope
from tests.pg_support import test_admin_url


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "postgresql+psycopg://incident_desk_test_admin:secret@remote.example/postgres",
        "postgresql+psycopg://incident_desk_test_admin:secret@localhost/incident_desk",
        "postgresql+psycopg://postgres:secret@localhost/postgres",
        "postgresql+psycopg://incident_desk_test_admin:secret@localhost/postgres?host=remote",
        "sqlite:///test.db",
    ],
)
def test_disposable_database_guard(raw):
    with pytest.raises(ValueError) as exc:
        test_admin_url(raw)
    assert "secret" not in str(exc.value)


def test_disposable_database_guard_accepts_dedicated_local_role():
    url = test_admin_url(
        "postgresql+psycopg://incident_desk_test_admin:secret@127.0.0.1:5432/postgres"
    )
    assert url.database == "postgres"


def test_engine_requires_explicit_configuration():
    with (
        pytest.raises(ValueError, match="INCIDENT_DESK_DATABASE_URL"),
        engine_scope(Settings()),
    ):
        pytest.fail("No engine should be created without configuration")


def test_engine_creation_is_lazy_and_disposes_pool(monkeypatch):
    monkeypatch.setenv(
        "INCIDENT_DESK_DATABASE_URL",
        "postgresql+psycopg://unused:unused@127.0.0.1:1/unavailable",
    )
    with engine_scope(Settings()) as engine:
        pool = engine.pool
        assert engine.hide_parameters
        assert not engine.echo
    # dispose replaces the old pool even though no connection was established.
    assert engine.pool is not pool
