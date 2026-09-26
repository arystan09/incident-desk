"""Actual CLI/API/worker subprocess smoke against one disposable database."""

import os
import socket
import subprocess
import sys
import time

import httpx
import pytest
from sqlalchemy import func, select

from incident_desk.persistence.database import transaction
from incident_desk.persistence.models import Job, Run, RunStep
from tests.integration.conftest import ROOT

pytestmark = pytest.mark.integration


def test_live_api_and_worker(database):
    env = os.environ.copy()
    env["INCIDENT_DESK_DATABASE_URL"] = database.url.render_as_string(
        hide_password=False
    )
    env["INCIDENT_DESK_WORKER_POLL_SECONDS"] = "0.1"
    provision = subprocess.run(
        [sys.executable, "-m", "incident_desk.provision", "--name", "Synthetic smoke"],
        env=env,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert provision.returncode == 0, "Provisioning CLI failed (output withheld)"
    raw_key = provision.stdout.strip().splitlines()[-1].split(": ", 1)[1]
    assert len(raw_key) == 43
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    processes = []
    try:
        api = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "incident_desk.main:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            env=env,
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        processes.append(api)
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=2) as client:
            deadline = time.monotonic() + 20
            while True:
                try:
                    response = client.get("/health/live")
                    if response.status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                assert api.poll() is None, "API process exited"
                assert time.monotonic() < deadline, "API startup timed out"
                time.sleep(0.1)
            headers = {"Authorization": f"Bearer {raw_key}", "Idempotency-Key": "smoke"}
            body = {"service_id": "checkout", "incident_id": "fixture-001"}
            first = client.post("/v1/runs", headers=headers, json=body)
            assert first.status_code == 202 and first.json()["status"] == "queued"
            worker = subprocess.Popen(
                [sys.executable, "-m", "incident_desk.worker"],
                env=env,
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            processes.append(worker)
            deadline = time.monotonic() + 20
            while True:
                final = client.get(first.headers["location"], headers=headers)
                assert final.status_code == 200
                if final.json()["status"] == "completed":
                    break
                assert worker.poll() is None, "Worker process exited"
                assert time.monotonic() < deadline, "Worker completion timed out"
                time.sleep(0.1)
            replay = client.post("/v1/runs", headers=headers, json=body)
            assert replay.status_code == 202 and replay.json() == final.json()
            assert final.json()["id"] == first.json()["id"]
        with transaction(database) as session:
            assert session.scalar(select(func.count()).select_from(Run)) == 1
            assert session.scalar(select(func.count()).select_from(Job)) == 1
            assert session.scalars(select(Job)).one().attempt_count == 1
            assert session.scalar(select(func.count()).select_from(RunStep)) == 5
    finally:
        # These process handles belong only to this test; never kill by process name.
        for process in reversed(processes):
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
