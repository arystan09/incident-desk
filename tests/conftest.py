"""Keep application tests independent of local settings and credentials."""

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    for key in os.environ:
        if key.upper().startswith("INCIDENT_DESK_"):
            monkeypatch.delenv(key)
