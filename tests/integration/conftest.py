"""Each test receives its own newly created PostgreSQL database."""

import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

from tests.pg_support import test_admin_url

ROOT = Path(__file__).resolve().parents[2]


def migration_config(connection):
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


@pytest.fixture(scope="session")
def admin_engine():
    try:
        url = test_admin_url(os.environ.get("TEST_DATABASE_URL"))
    except ValueError as exc:
        pytest.fail(str(exc), pytrace=False)
    engine = create_engine(
        url,
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
        hide_parameters=True,
        connect_args={"connect_timeout": 3},
    )
    try:
        try:
            with engine.connect() as connection:
                connection.exec_driver_sql("SELECT 1")
        except SQLAlchemyError:
            pytest.fail(
                "PostgreSQL integration tests explicitly requested but the test server "
                "is unavailable. Start PostgreSQL and configure TEST_DATABASE_URL "
                "with the dedicated LOGIN/CREATEDB role; see README.md.",
                pytrace=False,
            )
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def empty_database(admin_engine):
    # Only this freshly generated name is ever passed to CREATE/DROP DATABASE.
    name = "incident_desk_test_" + uuid4().hex
    created = False
    engine = None
    try:
        try:
            with admin_engine.connect() as connection:
                connection.exec_driver_sql(
                    f'CREATE DATABASE "{name}" TEMPLATE template0'
                )
            created = True
        except SQLAlchemyError:
            pytest.fail(
                "Cannot create disposable test database. The dedicated "
                "incident_desk_test_admin role needs CREATEDB; see README.md.",
                pytrace=False,
            )
        engine = create_engine(
            admin_engine.url.set(database=name),
            poolclass=NullPool,
            hide_parameters=True,
            connect_args={
                "connect_timeout": 3,
                "options": "-c statement_timeout=10000 -c timezone=UTC",
            },
        )
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin_engine.connect() as connection:
                # No FORCE: never terminate someone else's connection.
                connection.exec_driver_sql(f'DROP DATABASE "{name}"')


@pytest.fixture
def database(empty_database):
    with empty_database.begin() as connection:
        command.upgrade(migration_config(connection), "head")
    return empty_database
