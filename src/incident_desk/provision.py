"""Local-only tenant provisioning: python -m incident_desk.provision --name NAME."""

import argparse

from incident_desk.config import Settings
from incident_desk.persistence.database import engine_scope, transaction
from incident_desk.persistence.identity import provision_tenant


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a tenant and display its API key once"
    )
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    name = args.name.strip()
    if not 1 <= len(name) <= 128:
        parser.error("name must contain 1-128 characters")
    with engine_scope(Settings()) as engine, transaction(engine) as session:
        tenant_id, raw_key = provision_tenant(session, name)
    # Deliberate once-only CLI output, after the transaction has committed.
    print(f"Tenant: {tenant_id}")
    print(f"API key (shown once): {raw_key}")


if __name__ == "__main__":
    main()
