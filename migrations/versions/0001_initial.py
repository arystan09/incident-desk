"""Initial investigation records. Downgrade destroys all investigation data."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), server_default="queued", nullable=False),
        sa.Column("state_version", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'waiting_approval', 'completed', "
            "'failed', 'cancelled', 'needs_review', 'rejected')",
            name="ck_runs_status",
        ),
        sa.CheckConstraint("state_version >= 0", name="ck_runs_state_version"),
    )
    op.create_index("ix_runs_tenant_created", "runs", ["tenant_id", "created_at", "id"])
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), server_default="queued", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("lease_owner", sa.Text(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_generation", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], name="fk_jobs_run_id", ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("run_id", name="uq_jobs_run_id"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_jobs_status",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_jobs_attempt_count"),
        sa.CheckConstraint("lease_generation >= 0", name="ck_jobs_lease_generation"),
    )
    op.create_index(
        "ix_jobs_queued_next_attempt",
        "jobs",
        ["next_attempt_at", "id"],
        postgresql_where=sa.text("status = 'queued'"),
    )
    op.create_table(
        "run_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("step_no", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="started", nullable=False),
        sa.Column(
            "input_payload",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("output_payload", postgresql.JSONB(none_as_null=True), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], name="fk_run_steps_run_id", ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("run_id", "step_no", name="uq_run_steps_run_step"),
        sa.CheckConstraint("step_no >= 1", name="ck_run_steps_step_no"),
        sa.CheckConstraint(
            "status IN ('started', 'completed', 'failed')", name="ck_run_steps_status"
        ),
    )


def downgrade() -> None:
    # Destructive: only run on disposable development/test databases.
    op.drop_table("run_steps")
    op.drop_index("ix_jobs_queued_next_attempt", table_name="jobs")
    op.drop_table("jobs")
    op.drop_index("ix_runs_tenant_created", table_name="runs")
    op.drop_table("runs")
