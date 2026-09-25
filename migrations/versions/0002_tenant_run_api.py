"""Tenant identities and request identity, preserving pre-authentication history."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("key_digest", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_api_keys_tenant_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("key_digest", name="uq_api_keys_digest"),
    )
    # Preserve every legacy tenant ID, without granting access or inventing keys.
    op.execute(
        "INSERT INTO tenants (id, name) SELECT DISTINCT tenant_id, "
        "'legacy:' || tenant_id::text FROM runs"
    )
    for column in ("service_id", "incident_id", "idempotency_key"):
        op.add_column("runs", sa.Column(column, sa.String(128), nullable=True))
    op.add_column("runs", sa.Column("request_hash", sa.String(64), nullable=True))
    # Internal v0 identity is deliberately not the hash of a v1 public request.
    op.execute("""UPDATE runs SET service_id='legacy-unassigned',
        incident_id='legacy:' || id::text, idempotency_key='legacy:' || id::text,
        request_hash=encode(sha256(convert_to(
            'legacy-v0:' || id::text, 'UTF8')), 'hex')""")
    for column in ("service_id", "incident_id", "idempotency_key", "request_hash"):
        op.alter_column("runs", column, nullable=False)
    op.create_foreign_key(
        "fk_runs_tenant_id",
        "runs",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_runs_tenant_idempotency", "runs", ["tenant_id", "idempotency_key"]
    )


def downgrade() -> None:
    # Disposable databases only: this loses API credentials and request metadata.
    op.drop_constraint("uq_runs_tenant_idempotency", "runs", type_="unique")
    op.drop_constraint("fk_runs_tenant_id", "runs", type_="foreignkey")
    for column in ("request_hash", "idempotency_key", "incident_id", "service_id"):
        op.drop_column("runs", column)
    op.drop_table("api_keys")
    op.drop_table("tenants")
