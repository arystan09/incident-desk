"""Small packaged synthetic fixtures; no arbitrary path or URL resolution."""

import json
from importlib.resources import files

from pydantic import BaseModel, ConfigDict

from incident_desk.domain.execution import NonRetryableExecutionError, StepResult


class Fixture(BaseModel):
    model_config = ConfigDict(extra="forbid")
    service_id: str
    incident_id: str
    metrics: str
    logs: str
    runbook: str
    summary: str
    likely_cause: str


def investigate(service_id: str, incident_id: str) -> list[StepResult]:
    # Caller identifiers are only compared to a fixed catalog, never used as paths.
    catalog = files(__package__).joinpath("incidents.json").read_text("utf-8")
    fixtures = [Fixture.model_validate(item) for item in json.loads(catalog)]
    fixture = next(
        (
            f
            for f in fixtures
            if (f.service_id, f.incident_id) == (service_id, incident_id)
        ),
        None,
    )
    if fixture is None:
        raise NonRetryableExecutionError
    return [
        StepResult(
            "load_fixture",
            {"synthetic": True, "fixture_version": 1, "incident_id": incident_id},
        ),
        StepResult(
            "inspect_metrics", {"reference": "metrics", "snapshot": fixture.metrics}
        ),
        StepResult("inspect_logs", {"reference": "logs", "excerpt": fixture.logs}),
        StepResult(
            "inspect_runbook", {"reference": "runbook", "excerpt": fixture.runbook}
        ),
        StepResult(
            "summary",
            {
                "synthetic": True,
                "summary": fixture.summary,
                "likely_cause": fixture.likely_cause,
                "evidence_references": ["metrics", "logs", "runbook"],
                "suggested_next_action": fixture.runbook,
            },
        ),
    ]
