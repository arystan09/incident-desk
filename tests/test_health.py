from fastapi.testclient import TestClient

from incident_desk.main import create_app


def test_liveness() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
