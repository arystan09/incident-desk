import pytest
from pydantic import ValidationError

from incident_desk.config import Settings
from incident_desk.domain.execution import NonRetryableExecutionError
from incident_desk.fixtures import investigate


@pytest.mark.parametrize(
    "field,value",
    [
        ("worker_poll_seconds", 0),
        ("worker_poll_seconds", 61),
        ("worker_lease_seconds", 4),
        ("worker_lease_seconds", 301),
        ("worker_max_attempts", 0),
        ("worker_max_attempts", 11),
        ("worker_retry_base_seconds", 0),
        ("worker_retry_base_seconds", 61),
    ],
)
def test_worker_configuration_bounds(field, value):
    with pytest.raises(ValidationError):
        Settings(**{field: value})


def test_worker_defaults_and_override(monkeypatch):
    settings = Settings()
    assert (
        settings.worker_poll_seconds,
        settings.worker_lease_seconds,
        settings.worker_max_attempts,
        settings.worker_retry_base_seconds,
    ) == (1, 60, 3, 2)
    monkeypatch.setenv("INCIDENT_DESK_WORKER_LEASE_SECONDS", "30")
    assert Settings().worker_lease_seconds == 30


@pytest.mark.parametrize(
    "service,incident",
    [
        ("checkout", "fixture-001"),
        ("payments", "fixture-002"),
        ("database", "fixture-003"),
    ],
)
def test_fixtures_are_deterministic(service, incident):
    first = investigate(service, incident)
    assert first == investigate(service, incident)
    assert len(first) == 5
    assert first[-1].output["synthetic"] is True
    assert first[-1].output["likely_cause"]


@pytest.mark.parametrize(
    "service,incident", [("wrong", "fixture-001"), ("checkout", "../../.env")]
)
def test_fixture_identifiers_do_not_resolve_paths(service, incident):
    with pytest.raises(NonRetryableExecutionError):
        investigate(service, incident)
