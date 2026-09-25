"""Local identity provisioning and digest lookup; no raw key persistence."""

import hashlib
import secrets
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from incident_desk.persistence.models import ApiKey, Tenant


def key_digest(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def provision_tenant(session: Session, name: str) -> tuple[UUID, str]:
    name = name.strip()
    if not 1 <= len(name) <= 128:
        raise ValueError("Tenant name must contain 1-128 characters")
    tenant = Tenant(name=name)
    session.add(tenant)
    session.flush()
    raw_key = secrets.token_urlsafe(32)
    session.add(ApiKey(tenant_id=tenant.id, key_digest=key_digest(raw_key)))
    session.flush()
    return tenant.id, raw_key


def authenticate(session: Session, raw_key: str) -> UUID | None:
    return session.scalar(
        select(ApiKey.tenant_id).where(
            ApiKey.key_digest == key_digest(raw_key), ApiKey.revoked_at.is_(None)
        )
    )
