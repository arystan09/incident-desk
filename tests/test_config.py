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
