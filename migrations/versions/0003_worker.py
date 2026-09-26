"""Worker diagnostics and expired-lease selection; preserve existing records."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("claimed_at", sa.DateTime(timezone=True)))
    op.add_column("jobs", sa.Column("last_error_code", sa.String(64)))
    op.create_index(
        "ix_jobs_running_lease",
        "jobs",
        ["lease_expires_at", "id"],
        postgresql_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_running_lease", table_name="jobs")
    op.drop_column("jobs", "last_error_code")
    op.drop_column("jobs", "claimed_at")
