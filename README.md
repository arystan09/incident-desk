# Incident Desk

Incident Desk is a personal Applied AI engineering portfolio project for a clearly
labeled synthetic service environment. It is intended to become a resumable agent
that gathers incident evidence, produces an evidence-backed conclusion or abstains,
and proposes a local ticket update that requires human approval before application.
There are no claimed customers, production deployments, or measured business results.

Current status: **F1 foundation with persistence implementation; PostgreSQL verification pending**. Implemented today: an installable Python
package, validated configuration, an application factory, process liveness, isolated
unit tests, quality commands, a container definition, and GitHub Actions CI.
F1-02 adds synchronous SQLAlchemy/psycopg persistence, an Alembic migration,
and a separate real-PostgreSQL integration suite. These database paths have not
yet executed successfully on this machine.

## Local setup

Prerequisites: Python 3.12 and uv (the checked tool version is 0.12.18).
uv can download Python 3.12 with `uv python install 3.12`. Docker Engine/Desktop
with Compose is optional. GNU make is optional.

```sh
uv python install 3.12
uv sync --locked
uv run --locked uvicorn incident_desk.main:create_app --factory --reload --host 127.0.0.1 --port 8000
```

Optionally copy `.env.example` to `.env` (`Copy-Item .env.example .env` in PowerShell).
Settings use the `INCIDENT_DESK_` prefix. `SERVICE_NAME` defaults to `incident-desk`;
`ENVIRONMENT` defaults to `development` and accepts `development`, `test`, or
`production`. A nonempty service name is required. Process environment overrides
`.env`. Unrelated settings are ignored. The environment label does not enable
authentication or otherwise make this application production-ready.

In another terminal:

```sh
curl http://127.0.0.1:8000/health/live
```

On Windows use `curl.exe http://127.0.0.1:8000/health/live`.
Expected: HTTP 200 with `{"status":"ok"}`. Stop the server with Ctrl+C.
No PostgreSQL server or model API key is required.

## Quality commands (also work in Windows PowerShell)

```sh
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked mypy
uv run --locked pytest
```

Run all four commands to reproduce `make check`; they do not rewrite source files.
To format intentionally, use `uv run --locked ruff format .`.
`make install`, `make dev`, `make lint`, `make format`, `make typecheck`,
`make test`, and `make check` wrap the uv commands above. Tests run offline using
a temporary working directory and remove prefixed environment variables to isolate
settings from the developer's `.env` and process configuration.

## Docker

```sh
docker compose -p incident-desk-f1 up --build -d --wait api
curl http://127.0.0.1:8000/health/live
docker compose -p incident-desk-f1 down
```

Use `curl.exe` on Windows. The command above runs only the API and binds host port 8000 to
loopback. The image uses Python 3.12, locked runtime dependencies, a non-root user,
and a standard-library HTTP liveness check. `.env` is excluded from the build.
The base image tags can receive upstream updates; the Python dependency lock does
not pin the entire operating system image.

## Design and current limitations

See [architecture](docs/architecture.md), [initial ADR](docs/adr/0001-initial-architecture.md),
and [roadmap](ROADMAP.md). Persistence is implemented but locally unverified.
There is no authentication, worker, model
provider, evidence tool, approval workflow, UI, or telemetry yet. Liveness only
checks that the HTTP process responds; database readiness is not implemented.
Docker execution and hosted CI require their respective runtimes; local verification
evidence and any unrun checks are recorded in the roadmap. This is not a
production-ready incident system.

## PostgreSQL development setup (PowerShell)

Use PostgreSQL 17. Install Docker Desktop yourself and start its Linux-container
engine, or use an existing PostgreSQL server with `psql` available. This project
does not install services or change Windows settings. For the existing Windows
installation, add its `bin` folder to your terminal PATH only if needed:

```powershell
$env:PATH = 'C:\Program Files\PostgreSQL\17\bin;' + $env:PATH
```

Copy `.env.example` to `.env` if you have not already done so. Set a development-only
`POSTGRES_PASSWORD` there. Do not commit `.env`. The database image refuses an empty
password; leaving it blank does not prevent the API-only command from working.
Compose profiles keep PostgreSQL optional. Start just this project's database:

```powershell
docker compose -p incident-desk-f1 --profile database up -d --wait db
```

This creates the `incident_desk` database with the configured development role,
binds port 5432 to loopback, and persists data in a project-scoped named volume.
Changing `.env` credentials does not change roles in an already initialized volume.
For an existing PostgreSQL installation, have its administrator create a dedicated
local database and role instead; do not point this project at production data.

Set `INCIDENT_DESK_DATABASE_URL` in `.env` (or the shell) to your database, with a
percent-encoded password. The only supported driver scheme is `postgresql+psycopg`:

```powershell
$env:INCIDENT_DESK_DATABASE_URL = 'postgresql+psycopg://incident_desk_dev:YOUR_ENCODED_PASSWORD@127.0.0.1:5432/incident_desk'
uv sync --locked
uv run --locked alembic upgrade head
```

`make migrate` runs the same upgrade. Run migrations explicitly from the checkout;
API startup never runs them. `INCIDENT_DESK_DATABASE_CONNECT_TIMEOUT` defaults to
5 seconds, and `INCIDENT_DESK_DATABASE_STATEMENT_TIMEOUT_MS` to 10000 milliseconds.
The app still serves liveness with no URL or with an unreachable database.

## Real PostgreSQL integration tests

Fast `uv run --locked pytest` excludes the `integration` marker. The explicit suite
fails with setup instructions if PostgreSQL or test configuration is unavailable.
It never falls back to SQLite and does not read TEST_DATABASE_URL from `.env`.

Create a dedicated local test role once in your development PostgreSQL instance.
For the Compose defaults, open psql with:

```powershell
docker compose -p incident-desk-f1 --profile database exec db psql -U incident_desk_dev -d postgres
```

Or use `psql -h 127.0.0.1 -U YOUR_LOCAL_ADMIN -d postgres` for an existing server.
In psql, run the following only if this dedicated role does not already exist;
`\password` prompts without putting its value in SQL history:

```text
CREATE ROLE incident_desk_test_admin LOGIN CREATEDB;
\password incident_desk_test_admin
\q
```

The test role only needs LOGIN and CREATEDB. Do not reuse application/production
credentials. Export the URL in the test shell:

```powershell
$env:TEST_DATABASE_URL = 'postgresql+psycopg://incident_desk_test_admin:YOUR_ENCODED_TEST_PASSWORD@127.0.0.1:5432/postgres'
uv run --locked pytest -m integration tests/integration
```

Equivalent: `make test-integration`. Tests accept only a loopback host, that exact
test username, database `postgres`, and no URL query parameters. The URL is used
as a maintenance connection to CREATE a unique `incident_desk_test_<uuid>` database
for each test. Only those newly created databases are migrated and dropped. No
supplied database is reset. Each test database is dropped after connections close;
an interrupted test may leave a disposable database for manual inspection.

**Destructive migration warning:** the initial downgrade removes all three tables
and all their data. Do not run `alembic downgrade base` on a normal development,
shared, or production database. The integration suite tests downgrade/base/upgrade
only inside its newly created disposable database; there is no general reset target.

Stop only the services started for this project (data volume is retained):

```powershell
docker compose -p incident-desk-f1 --profile database stop db
```

**Destructive volume reset warning:** this next command permanently deletes this
project's PostgreSQL data and removes its containers. Use only for a disposable
local environment after checking the project name and backing up anything needed:

```powershell
docker compose -p incident-desk-f1 --profile database down --volumes
```

The integration CI job uses its own PostgreSQL 17 service and disposable-only
credentials. Local PostgreSQL integration execution is blocked: no running server,
no initdb/pg_ctl tools, and no TEST_DATABASE_URL are available. Docker build/startup
and hosted GitHub Actions have still not run. See [ADR 0002](docs/adr/0002-synchronous-persistence.md)
for transaction ownership and migration decisions, and the roadmap for check evidence.
