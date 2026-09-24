"""Explicit engine and transaction ownership for synchronous callers."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from incident_desk.config import Settings


@contextmanager
def engine_scope(settings: Settings) -> Iterator[Engine]:
    """Own a lazy engine; dispose its pool on exit, including failure paths."""
    if settings.database_url is None:
        raise ValueError("Set INCIDENT_DESK_DATABASE_URL to use persistence")
    engine = create_engine(
        settings.database_url.get_secret_value(),
        echo=False,
        hide_parameters=True,
        pool_pre_ping=True,
        pool_timeout=settings.database_connect_timeout,
        connect_args={
            "connect_timeout": settings.database_connect_timeout,
            "options": (
                f"-c statement_timeout={settings.database_statement_timeout_ms} "
                "-c timezone=UTC"
            ),
        },
    )
    try:
        yield engine
    finally:
        engine.dispose()


@contextmanager
def transaction(engine: Engine) -> Iterator[Session]:
    """Commit on success; rollback on failure; always close the session.

    The caller owns this unit of work. Do not commit inside it or keep it open
    during network/provider calls. Sessions must not be shared across threads.
    """
    with Session(engine, expire_on_commit=False) as session, session.begin():
        yield session
