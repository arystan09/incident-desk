# Incident Desk

Incident Desk is an Applied AI engineering portfolio project for a clearly labeled
synthetic service environment. The intended workflow is to investigate an incident,
gather evidence, return a supported conclusion or abstain, and propose a local
ticket update. Applying that exact proposal will require human approval.

**The API foundation and PostgreSQL persistence code are implemented. PostgreSQL
integration tests pass against PostgreSQL 17.11; F1-02 is awaiting owner review.**

## What works today

The FastAPI application exposes `GET /health/live` and validates environment
settings. It starts without PostgreSQL or a model API key. The persistence package
contains synchronous SQLAlchemy 2/psycopg 3 models for runs, jobs, and steps, explicit
transaction helpers, and an Alembic migration. All 16 PostgreSQL integration
cases pass, including migrations, constraints, JSONB persistence, and rollback.

Investigation endpoints, authentication, workers, evidence tools, model calls,
approval, and a review interface are planned. See the [roadmap](ROADMAP.md),
[architecture](docs/architecture.md), and [persistence ADR](docs/adr/0002-synchronous-persistence.md).

## Run the API

Use Python 3.12 and uv (checked with uv 0.12.18). From the repository root:

```powershell
uv python install 3.12
uv sync --locked
uv run --locked uvicorn incident_desk.main:create_app --factory --reload --host 127.0.0.1 --port 8000
```

In another PowerShell terminal, run `curl.exe http://127.0.0.1:8000/health/live`.
On other shells use `curl`. Expect HTTP 200 and `{"status":"ok"}`. Stop with Ctrl+C.

Settings use the `INCIDENT_DESK_` prefix. The service name defaults to
`incident-desk`; environment defaults to `development` and accepts `development`,
`test`, or `production`. Shell settings override an optional `.env` file. See
[.env.example](.env.example) for the database URL and timeout settings.

## Checks

These commands work in PowerShell without make:

```powershell
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked mypy
uv run --locked pytest
```

`make check` runs the same four checks. Unit tests are offline and isolated from
local application settings; PostgreSQL cases are excluded by default. Use
`uv run --locked ruff format .` to apply formatting and `uv build` to build the
package. Other Makefile targets: `install`, `dev`, `lint`, `format`, `typecheck`,
`test`, `migrate`, and `test-integration`.

## PostgreSQL on Windows: Docker Compose

**Manual prerequisite:** install and start Docker Desktop with its Linux-container
engine. `docker version` must show a running server, and `docker compose version`
must succeed. This setup was verified locally with PostgreSQL 17.11.

1. Prepare local configuration without replacing an existing `.env`:

   ```powershell
   if (-not (Test-Path .env)) { Copy-Item .env.example .env }
   ```

   Edit `.env` and set a development-only `POSTGRES_PASSWORD`. Keep the example's
   `POSTGRES_USER=incident_desk_dev`, `POSTGRES_DB=incident_desk`, and
   `POSTGRES_PORT=5432` for the commands below. Never commit `.env`.

2. Start only the database service:

   ```powershell
   docker compose -p incident-desk-f1 --profile database up -d --wait db
   ```

   This uses `postgres:17`, binds `127.0.0.1:5432`, and keeps data in the project's
   named `postgres_data` volume. An empty password prevents initial database setup.
   Changing `.env` later does not change credentials in an existing volume.

   If Windows refuses the port binding, set `POSTGRES_PORT=55432` in `.env` and
   retry. Use that same port in both database URLs. Local verification used
   55432 because Windows denied binding 5432; no OS settings were changed.

3. Create the dedicated test role before setting `TEST_DATABASE_URL`:

   ```powershell
   docker compose -p incident-desk-f1 --profile database exec db psql -U incident_desk_dev -d postgres
   ```

   In psql, inspect `\du incident_desk_test_admin`. If the role is absent, create it:

   ```sql
   CREATE ROLE incident_desk_test_admin LOGIN CREATEDB NOSUPERUSER NOCREATEROLE NOREPLICATION NOBYPASSRLS;
   GRANT CONNECT ON DATABASE postgres TO incident_desk_test_admin;
   ```

   Set its separate test password using `\password incident_desk_test_admin`, then
   exit with `\q`. The prompt avoids putting the password in SQL history. If the
   role already exists, inspect its privileges rather than recreating it.
   The fixtures need login, connection to `postgres`, and permission to create
   databases. Ownership of each new test database permits migration and cleanup;
   superuser and role-management privileges are unnecessary.

4. Export the test URL in PowerShell without typing the password into command history:

   ```powershell
   $testPort = 5432 # Match POSTGRES_PORT in .env; use 55432 if changed above.
   $testCredential = Get-Credential -UserName incident_desk_test_admin -Message 'Enter the test role password'
   $encodedPassword = [uri]::EscapeDataString($testCredential.GetNetworkCredential().Password)
   $env:TEST_DATABASE_URL = "postgresql+psycopg://incident_desk_test_admin:${encodedPassword}@127.0.0.1:${testPort}/postgres"
   Remove-Variable testCredential, encodedPassword
   uv run --locked pytest -m integration tests/integration
   ```

   Equivalent: `make test-integration`. Do not print the URL. The fixture reads it
   from the process environment, not `.env`, and rejects non-loopback hosts,
   different role/database names, and URL query overrides. Each test creates a
   unique `incident_desk_test_<uuid>` database, runs migrations and assertions, then
   drops only that database. It never resets the supplied maintenance database or
   reads the application URL. The 16 cases include upgrade/downgrade/upgrade,
   schema comparison, constraints, JSONB round-trips, and atomic rollback.

   If your local setup already has an ignored `.env.test` containing the test URL,
   load it explicitly without displaying it:

   ```powershell
   uv run --locked --env-file .env.test pytest -m integration tests/integration
   ```

   This exports the file through uv; the fixture itself still reads only the process
   environment. Keep `.env.test` private and untracked.

To migrate the separate local application database, set `INCIDENT_DESK_DATABASE_URL`
in `.env` using the commented example and your percent-encoded development password,
then run `uv run --locked alembic upgrade head` (or `make migrate`). Migrations do
not run on API startup.

**Destructive downgrade:** `alembic downgrade base` removes the initial schema and
its data. Do not run it on an ordinary application database. The integration suite
runs that operation only inside newly created disposable databases. Interrupted
tests may leave a test database for manual inspection.

Stop the project database with `docker compose -p incident-desk-f1 --profile database stop db`.
This retains the data volume. No volume-reset command is needed for the test suite.

## API container (optional)

```powershell
docker compose -p incident-desk-f1 up --build -d --wait api
curl.exe http://127.0.0.1:8000/health/live
docker compose -p incident-desk-f1 stop api
```

The API container runs as a non-root user and uses a standard-library liveness
check. It does not start the optional database service.

## Current limitations

Liveness reports only that the HTTP process responds. There is no database
readiness endpoint, tenant isolation, worker recovery, or approval enforcement yet.
The 25 unit tests and 16 PostgreSQL integration tests pass. The API container
builds, becomes healthy, and returns HTTP 200 for liveness. Hosted GitHub Actions
has not been verified in this task, and owner review of F1-02 is pending.
[ROADMAP.md](ROADMAP.md) records executed checks separately from setup
instructions. Contribution rules are in [AGENTS.md](AGENTS.md).
