import pytest
from fastapi.testclient import TestClient

from incident_desk.domain.runs import RunRequest
from incident_desk.main import create_app


def test_canonical_request_hash():
    one = RunRequest(service_id=" checkout ", incident_id=" fixture-001 ")
    two = RunRequest.model_validate(
        {"incident_id": "fixture-001", "service_id": "checkout"}
    )
    assert one.request_hash() == two.request_hash()
    assert (
        one.request_hash()
        != RunRequest(service_id="checkout", incident_id="other").request_hash()
    )


@pytest.mark.parametrize("configured", [False, True])
def test_unavailable_database_and_public_liveness(monkeypatch, configured):
    if configured:
        monkeypatch.setenv(
            "INCIDENT_DESK_DATABASE_URL",
            "postgresql+psycopg://unused:never-expose@127.0.0.1:1/missing",
        )
        monkeypatch.setenv("INCIDENT_DESK_DATABASE_CONNECT_TIMEOUT", "1")
    with TestClient(create_app()) as client:
        assert client.get("/health/live").status_code == 200
        assert client.post("/v1/runs", json={}).status_code == 401
        response = client.post(
            "/v1/runs",
            headers={"Authorization": "Bearer " + "x" * 43, "Idempotency-Key": "x"},
            json={"service_id": "x", "incident_id": "y"},
        )
        assert response.status_code == 503
        assert response.json() == {"detail": "Database unavailable"}
        assert client.get("/health/live").status_code == 200
