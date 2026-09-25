import hashlib
import json
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

Identifier = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=128, strict=True),
]


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    service_id: Identifier
    incident_id: Identifier

    def request_hash(self) -> str:
        canonical = json.dumps(
            {"schema_version": 1, **self.model_dump()},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class IdempotencyConflict(Exception):
    """The authenticated tenant already used this key for another input."""
