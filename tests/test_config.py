import pytest
from pydantic import ValidationError

from incident_desk.config import Settings
from incident_desk.main import create_app


def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "unrelated")
    monkeypatch.setenv("SERVICE_NAME", "unrelated")
    settings = Settings()
    assert settings.service_name == "incident-desk"
    assert settings.environment == "development"


def test_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INCIDENT_DESK_SERVICE_NAME", "test-desk")
    monkeypatch.setenv("INCIDENT_DESK_ENVIRONMENT", "test")
    settings = Settings()
    assert settings.service_name == "test-desk"
    assert settings.environment == "test"
    assert create_app().title == "test-desk"


@pytest.mark.parametrize("value", ["", "staging", "prod"])
def test_invalid_environment(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("INCIDENT_DESK_ENVIRONMENT", value)
    with pytest.raises(ValidationError, match="environment"):
        Settings()
    with pytest.raises(ValidationError, match="environment"):
        create_app()


@pytest.mark.parametrize("value", ["", "   "])
def test_empty_service_name(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("INCIDENT_DESK_SERVICE_NAME", value)
    with pytest.raises(ValidationError, match="service_name"):
        Settings()


@pytest.mark.parametrize(
    "url",
    [
        "sqlite:///local.db",
        "not-a-url",
        "postgresql+psycopg://host",
        "postgresql+psycopg://user:private-value@host:bad/db",
    ],
)
def test_invalid_database_configuration_is_redacted(monkeypatch, url):
    monkeypatch.setenv("INCIDENT_DESK_DATABASE_URL", url)
    with pytest.raises(ValidationError) as exc:
        Settings()
    assert "Database URL must use" in str(exc.value)
    assert url not in str(exc.value)
    assert "private-value" not in str(exc.value)


def test_database_url_is_optional_and_redacted(monkeypatch):
    assert Settings().database_url is None
    monkeypatch.setenv(
        "INCIDENT_DESK_DATABASE_URL",
        "postgresql+psycopg://user:private-value@localhost/desk",
    )
    settings = Settings()
    assert settings.database_url is not None
    assert "private-value" not in repr(settings)
    assert "private-value" not in settings.model_dump_json()


@pytest.mark.parametrize(
    "name,value", [("CONNECT_TIMEOUT", "0"), ("STATEMENT_TIMEOUT_MS", "0")]
)
def test_database_timeouts_must_be_positive(monkeypatch, name, value):
    monkeypatch.setenv(f"INCIDENT_DESK_DATABASE_{name}", value)
    with pytest.raises(ValidationError):
        Settings()
