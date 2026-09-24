"""Guards for test-only database creation. Never reset a supplied database."""

from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError


def test_admin_url(raw: str | None) -> URL:
    if not raw:
        raise ValueError(
            "Set TEST_DATABASE_URL to a local PostgreSQL maintenance database: "
            "postgresql+psycopg://incident_desk_test_admin:"
            "<password>@127.0.0.1:5432/postgres. "
            "The dedicated role needs LOGIN and CREATEDB. See README.md."
        )
    try:
        url = make_url(raw)
        valid = (
            url.drivername == "postgresql+psycopg"
            and url.host in {"127.0.0.1", "localhost", "::1"}
            and url.database == "postgres"
            and url.username == "incident_desk_test_admin"
            and not url.query
            and (url.port is None or 1 <= url.port <= 65535)
        )
    except (ArgumentError, ValueError, TypeError):
        valid = False
    if not valid:
        raise ValueError(
            "Unsafe TEST_DATABASE_URL: use postgresql+psycopg, a loopback host, "
            "database postgres, dedicated role incident_desk_test_admin, and no "
            "query parameters. Application DATABASE_URL is never used for tests."
        ) from None
    return url


# This is a validation helper, not a pytest test function.
test_admin_url.__test__ = False
