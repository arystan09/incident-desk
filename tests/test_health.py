from fastapi.testclient import TestClient

from incident_desk.main import create_app


def test_liveness() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_liveness_does_not_connect_to_configured_database(monkeypatch):
    monkeypatch.setenv(
        "INCIDENT_DESK_DATABASE_URL",
        "postgresql+psycopg://unused:unused@127.0.0.1:1/unavailable",
    )
    with TestClient(create_app()) as client:
        assert client.get("/health/live").json() == {"status": "ok"}
