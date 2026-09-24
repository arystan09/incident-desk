"""Alembic owns connections only when no test-owned connection is supplied."""

from alembic import context

from incident_desk.config import Settings
from incident_desk.persistence.database import engine_scope
from incident_desk.persistence.models import Base


def run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(
        dialect_name="postgresql", target_metadata=Base.metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()
elif (connection := context.config.attributes.get("connection")) is not None:
    run_migrations(connection)
else:
    with engine_scope(Settings()) as engine, engine.connect() as connection:
        run_migrations(connection)
