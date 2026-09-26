# Incident Desk

Incident Desk is an Applied AI engineering portfolio project for a clearly labeled
synthetic service environment. The intended workflow is to investigate an incident,
gather evidence, return a supported conclusion or abstain, and propose a local
ticket update. Applying that exact proposal will require human approval.

**API-key authentication and tenant-scoped run creation/read APIs are implemented.
A separate worker processes queued synthetic fixtures; no LLM execution exists.**

## What works today

`GET /health/live` is public and independent of PostgreSQL. A local CLI provisions
tenants and random API keys. Authenticated callers can create a run and its job
atomically, replay a request safely, and read their own runs. PostgreSQL stores
only key digests. The worker persists deterministic fixture steps. There is no
evidence tool, model call,
approval flow, reviewer role, or UI yet.

See the [roadmap](ROADMAP.md), [architecture](docs/architecture.md), and
[API transaction ADR](docs/adr/0003-tenant-run-api.md) for scope and decisions.

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
   reads the application URL. The suite includes upgrade/downgrade/upgrade,
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
check. This Compose command is a liveness-only setup: it does not pass the host
database URL to the container. Use the host uvicorn setup below for the run API.

## Provision and call the run API (PowerShell)

Start the project database and upgrade it before provisioning. Existing local
`.env` and `.env.test` use port 55432; keep those credentials and settings.

```powershell
docker compose -p incident-desk-f1 --profile database up -d --wait db
uv run --locked alembic upgrade head
uv run --locked python -m incident_desk.provision --name "Local demo"
```

The last command creates a new tenant and displays its generated API key once.
Store it privately. It accepts no user-chosen secret; the database stores only a
SHA-256 digest. Repeating the command creates another tenant, not a replacement key.
There is no public provisioning endpoint. Start the API with the uvicorn command
above, then use another terminal:

```powershell
$credential = Get-Credential -UserName api -Message 'Paste the generated API key as the password'
$headers = @{ Authorization = "Bearer $($credential.GetNetworkCredential().Password)"; 'Idempotency-Key' = 'demo-001' }
$body = @{ service_id = 'checkout'; incident_id = 'fixture-001' } | ConvertTo-Json
$run = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/v1/runs' -Headers $headers -ContentType 'application/json' -Body $body
$replay = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/v1/runs' -Headers $headers -ContentType 'application/json' -Body $body
Invoke-RestMethod -Uri "http://127.0.0.1:8000/v1/runs/$($run.id)" -Headers $headers
Remove-Variable credential, headers
```

POST and identical replay return 202 and a Location header. Both return the same
run ID; replay may show the run's current persisted state. Reusing the same key
with different input returns 409. Keys are case-sensitive and scoped to the
authenticated tenant; another tenant can independently use `demo-001`.

Identifiers are strings, trimmed, nonempty, and at most 128 characters. Unknown
body fields are rejected. Idempotency-Key is required and must contain 1-128
printable ASCII characters without whitespace. JSON field order does not affect
request identity. Responses expose only id, service_id, incident_id, status, and
created_at. No check is made that the incident exists or has been investigated.

Missing, malformed, unknown, or revoked bearer keys return 401 with
WWW-Authenticate: Bearer. Invalid input returns 422; missing and other-tenant run
IDs both return the same 404. Tenant identity always comes from the stored API key.
Database connection failures return a generic 503 while liveness stays available.
Use HTTPS for any non-local bearer-key traffic. Do not log or share the headers.

The API integration tests are under `tests/integration`, so the existing
`uv run --locked pytest -m integration tests/integration` command and CI integration
job include authentication, migration/backfill, and coordinated concurrency tests.
For the retained local credentials use `uv run --locked --env-file .env.test pytest
-m integration tests/integration`. The database must be running.

## Current limitations

API-key authentication and deterministic synthetic execution are implemented. Tenant
isolation is enforced in application queries, not PostgreSQL row-level security.
There is no key-management HTTP API, database readiness endpoint, provider execution,
or approval enforcement. Local verification does not establish hosted CI results
or an independent security/source audit. F1-04 requires owner review before done.
[ROADMAP.md](ROADMAP.md) records exact checks. Contribution rules are in [AGENTS.md](AGENTS.md).

## Run the worker (PowerShell)

Keep the working port **55432** and ignored `.env` / `.env.test`. Start PostgreSQL,
apply migrations, provision a key and start the API using the commands above.
In a separate terminal from this repository:

```powershell
uv run --locked python -m incident_desk.worker
```

Run the same command in another terminal for a second competing worker. Each process
gets its own generated identity. Ctrl+C stops new claims and lets the current short
fixture finish. Abrupt termination is recovered through lease expiry.

Submit and replay the existing PowerShell example with service `checkout` and
incident `fixture-001`, then repeat its GET command. The API remains nonblocking;
expect `queued` -> `running` -> `completed` (success), or `failed`. Fast execution
may finish before you observe running. Replay returns the same run's current state.
The existing response fields are unchanged; steps and lease data are not public.

Available synthetic catalog pairs:

| service_id | incident_id | Fixture |
| --- | --- | --- |
| checkout | fixture-001 | Latency and cache timeouts |
| payments | fixture-002 | Payment gateway errors |
| database | fixture-003 | Connection saturation |

The worker records fixture loading, metrics, logs, runbook and a fixed structured
summary as five steps. This is deterministic orchestration, not LLM reasoning or
proof of a real incident cause. Missing fixtures fail without retrying.

Defaults are a 60-second lease, three attempts, and 1-second idle polling. Explicit
transient failures schedule retries after 2 then 4 seconds. Expired leases can be
reclaimed; old owners cannot publish after replacement. Computation may repeat after
a crash, but successful results commit once. No external side effects are performed.
See [ADR 0004](docs/adr/0004-worker-lifecycle.md) for transaction and recovery limits.

Settings can be overridden with `INCIDENT_DESK_WORKER_POLL_SECONDS`,
`INCIDENT_DESK_WORKER_LEASE_SECONDS`, `INCIDENT_DESK_WORKER_MAX_ATTEMPTS`, and
`INCIDENT_DESK_WORKER_RETRY_BASE_SECONDS`. Use the same policy for all workers.
The worker does not migrate automatically. JSON logs report lifecycle events without
credentials or evidence bodies. No Prometheus or tracing stack is required.

Run all PostgreSQL tests, including an actual CLI/API/worker subprocess smoke test:

```powershell
uv run --locked --env-file .env.test pytest -m integration tests/integration
```

The smoke test uses its own disposable database and stops only subprocesses it
created. It leaves ordinary development data intact. Existing queued development
runs are processed when you start a worker; an unknown fixture becomes failed.
