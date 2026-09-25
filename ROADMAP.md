# Roadmap

Current milestone: **F1 — Durable investigation foundation**.
Statuses: `todo | in_progress | blocked | in_review | done`.
Owner verification is required to move work from `in_review` to `done`.
Current task: F1-03 authenticated run API. Do not proceed to F1-04.

## F1 — Durable investigation foundation

### F1-01: Package, quality checks, documentation, Docker, and CI

- Status: done
- Dependencies: none.
- Scope: src package, typed settings, FastAPI factory and liveness, isolated tests,
  uv lock, Ruff/mypy/pytest, Makefile, documentation, API-only Docker/Compose, CI.
- Acceptance: locked Python 3.12 install succeeds; formatting, lint, typing, and
  tests pass; liveness returns HTTP 200 and exactly `{"status":"ok"}` without
  PostgreSQL or model credentials; configuration rejects invalid environments;
  Docker smoke test runs if Docker is available; unrun checks are disclosed.
- Evidence (2026-09-25, Windows, Python 3.12.14, uv 0.12.18):
  `uv sync --locked` succeeded; `uv run --locked ruff format --check .`,
  `uv run --locked ruff check .`, and `uv run --locked mypy` passed (5 application
  source files); `uv run --locked pytest` passed all 8 tests. One upstream
  Starlette warning deprecates its HTTPX test-client integration. `uv build`
  produced an sdist and wheel; archive contents exclude caches and local tooling.
  A temporary Uvicorn subprocess served `/health/live` over loopback with HTTP 200
  and exactly `{"status":"ok"}`, and was stopped after verification.
  Docker build/start/health checks were not run: Docker is not installed.
  `make check` was not run: make is not installed; all four equivalent uv commands
  passed. Hosted GitHub Actions has not run. Both action SHAs were verified with
  `git ls-remote` against official release tags. Git is not initialized, so no
  branch or commit was created at that time.
- Owner acceptance (2026-09-25): the owner explicitly accepted the reported local
  F1-01 checks as sufficient to proceed. Docker build/startup remains untested;
  hosted GitHub Actions has not run. Acceptance does not close those gaps.
  Foundation history was subsequently established as commit 57e75eb on main.
  The later F1-02 verification below closes the local Docker build/startup gap;
  it does not establish a hosted CI result.

### F1-02: PostgreSQL run/job/step models and migrations

- Status: done
- Dependencies: F1-01 (accepted by owner).
- Scope: SQLAlchemy 2 synchronous sessions, psycopg 3, explicit engine/transaction
  ownership, run/job/step constraints and indexes, Alembic migrations, disposable
  PostgreSQL integration tests, optional Compose database, and CI integration job.
  Database readiness remains deferred until an API operation uses persistence.
- Acceptance: real PostgreSQL migration from empty, metadata comparison,
  downgrade/base/upgrade in a disposable database; persistence and JSONB round-trip;
  status/counter/FK/uniqueness/deletion constraints; atomic rollback of run and job;
  liveness independent of PostgreSQL; actionable errors if integration setup is absent.
- Previous blocker resolved: earlier attempts stopped at missing PostgreSQL tooling
  and TEST_DATABASE_URL. Docker Desktop is now accessible: Engine 29.8.0, Linux
  containers, Compose 5.5.1. No project containers or volumes existed before setup.
- Setup executed: `docker compose -p incident-desk-f1 --profile database up -d --wait db`.
  Windows denied binding 127.0.0.1:5432. Changed only ignored local configuration
  to POSTGRES_PORT=55432 and matching connection URLs; the retry became healthy.
  PostgreSQL reports 17.11. Generated private development/test credentials in
  ignored `.env` and `.env.test`; none are committed or displayed. Created the
  dedicated test role with LOGIN/CREATEDB and CONNECT to postgres; explicitly
  verified NOSUPERUSER, NOCREATEROLE, NOREPLICATION, and NOBYPASSRLS.
- Migration evidence: `uv run --locked alembic upgrade head` succeeded on the new
  development database; `uv run --locked alembic current` returned `0001 (head)`.
  `uv run --locked alembic check` reported no new upgrade operations. No development
  database downgrade/reset was performed.
- Integration evidence: `uv run --locked pytest -m integration tests/integration`
  passed all 16 cases with TEST_DATABASE_URL exported. Added `path_separator = os`
  to alembic.ini to remove its configuration deprecation warning, then reran with
  `uv run --locked --env-file .env.test pytest -m integration tests/integration`:
  16 passed, no warnings. Assertions were unchanged. This includes real upgrade /
  downgrade / upgrade, model comparison, constraints, JSONB, and atomic rollback.
  A maintenance query afterward confirmed zero remaining incident_desk_test_*
  databases. Fixtures dropped only databases they created.
- Quality evidence: `uv run --locked ruff format --check .`,
  `uv run --locked ruff check .`, and `uv run --locked mypy` passed (8 source files).
  `uv run --locked pytest` passed 25 unit tests, deselecting 16 integration cases;
  the existing upstream Starlette/HTTPX warning remains. `uv build` produced the
  wheel and source archive. `git diff --check` passed.
- Docker evidence: `docker compose -p incident-desk-f1 up --build -d --wait api`
  built the image and reached healthy status. `curl.exe --fail --silent --show-error
  -w '\nHTTP %{http_code}\n' http://127.0.0.1:8000/health/live` returned HTTP 200 and
  exactly `{"status":"ok"}`. This closes the earlier local API-container verification gap.
- Cleanup: stopped only this task's API and db services with Compose `stop api` and
  `--profile database stop db`. The development volume and ignored connection files
  are retained. Restart db and use the explicit uv --env-file command above to rerun.
- Remaining limits: hosted GitHub Actions was not verified by these local checks;
  the CI service uses its bootstrap role, while local tests used the restricted
  dedicated role. At F1-02 completion, tenant isolation, worker claims, fencing,
  and public run endpoints were still future work.
- Owner acceptance: the owner accepted the reported F1-02 verification as sufficient
  to proceed with F1-03. This does not claim hosted CI or an independent source audit.
  feat/f1-03-run-api branches directly from verified F1-02 commit 521b041;
  it builds on that history without merging or rewriting it.

### F1-03: Tenant-scoped API authentication and idempotent run creation

- Status: in_review
- Dependencies: F1-02 (accepted by owner).
- Scope: tenants/API-key digests, local provisioning CLI, bearer authentication,
  strict request/response schemas, tenant-filtered POST/GET run endpoints, atomic
  run/job creation, PostgreSQL idempotency, migration/backfill, API tests and docs.
- Acceptance: missing/malformed/unknown/revoked keys produce 401 with challenge;
  authenticated tenant identity cannot be spoofed; same tenant/key/input returns
  one run/job under sequential and coordinated concurrent requests; changed input
  conflicts; different tenants are independent; reads do not disclose other tenants;
  failed job insertion rolls back the run; PostgreSQL failures are generic 503 while
  liveness stays public; legacy 0001 data survives 0002; all quality checks pass.
- Migration evidence: development inspection before upgrade found 0 runs and 0
  distinct tenant IDs. New migration 0002 preserves legacy tenant IDs via tenants
  without API keys and internal v0 request placeholders; 0001 is unchanged. A real
  disposable migration test preserves representative status, version, job, and JSONB
  step history, then checks the new tenant foreign key. Development upgrade reached
  `0002 (head)`; `uv run --locked alembic check` found no new upgrade operations.
- Integration evidence: `uv run --locked --env-file .env.test pytest -m integration
  tests/integration --tb=short` passed 52 cases on PostgreSQL 17.11. This includes
  the original 16 persistence cases updated for the new required tenant/fields,
  all authentication/validation paths, spoofing, sequential/equivalent replay,
  cross-tenant 404 equivalence, and two coordinated concurrency cases using distinct
  backend PIDs. A real job constraint failure proves atomic rollback. A terminated
  test-owned database connection produces generic 503; SQL programming errors remain
  errors. The first run exposed a JSON SQL quoting issue in the new legacy fixture;
  it was fixed without weakening preservation assertions.
- HTTP smoke evidence: provisioned a synthetic local tenant through the actual CLI
  with captured private output, started a temporary Uvicorn process, observed POST
  202, identical replay 202/same ID, GET 200, and public liveness 200. Stopped only
  that process and revoked only its generated key. Synthetic smoke history remains
  in the development database; no investigation was executed.
- Final quality evidence: `uv run --locked ruff format --check .` and
  `uv run --locked ruff check .` passed; `uv run --locked mypy` passed for 16
  application files; `uv run --locked pytest` passed 28 fast tests (52 integration
  cases deselected). `uv build` produced the wheel and source archive; inspection
  found no private configuration or local tooling. `git diff --check` passed.
  The existing Starlette/HTTPX warning remains. CI still runs the complete
  tests/integration directory, including the new API tests.
- Cleanup and limits: zero disposable test databases remained. Stopped this task's
  project db service while retaining its data and ignored credentials on port 55432.
  Owner review is pending; hosted CI and an independent source/security audit are
  not claimed. No F1-04 work is included.

### F1-04: Worker claims, leases, fencing, and fake-provider execution

- Status: todo
- Dependencies: F1-02, F1-03.
- Scope: separate worker role, PostgreSQL job claims, lease renewal/expiry, fenced
  state transitions, step persistence, and minimal deterministic fake execution.
- Acceptance: concurrent workers do not own the same valid lease; a stale worker
  cannot commit after replacement; restart can resume persisted work; no database
  transaction spans a provider call; default execution is offline.
- Evidence: none; not implemented.

### F1-05: End-to-end fixture workflow and worker restart tests

- Status: todo
- Dependencies: F1-03, F1-04.
- Scope: reproducible synthetic fixture workflow from authenticated request through
  durable fake execution and terminal status, plus real PostgreSQL restart tests.
- Acceptance: fixture reaches the expected terminal state; killing and restarting
  the worker resumes safely; duplicate requests preserve run identity; interrupted
  progress and stale commits are covered without paid APIs.
- Evidence: none; not implemented.

## F2 — Agent and human review

All tasks below are todo; F2 follows verified F1.

| ID | Status | Task |
| --- | --- | --- |
| F2-01 | todo | Four typed evidence tools: metrics, logs, deployments, runbooks. |
| F2-02 | todo | Narrow model adapter and scripted fake provider. |
| F2-03 | todo | Bounded agent loop and evidence-reference validation. |
| F2-04 | todo | Immutable proposals, reviewer approval, and atomic local actions. |
| F2-05 | todo | Minimal review interface. |

## F3 — Reliability and evaluation

| ID | Status | Task |
| --- | --- | --- |
| F3-01 | todo | Crash and stale-worker recovery tests. |
| F3-02 | todo | Cancellation, deadlines, and bounded retries. |
| F3-03 | todo | Structured logs, tracing, metrics, and usage accounting. |
| F3-04 | todo | Tenant admission limits and security regression tests. |
| F3-05 | todo | Versioned synthetic evaluation dataset and baselines. |

## F4 — Reproducible release

| ID | Status | Task |
| --- | --- | --- |
| F4-01 | todo | Development-set experiments. |
| F4-02 | todo | Load and dependency-failure tests. |
| F4-03 | todo | Release packaging and operational runbook. |
| F4-04 | todo | Held-out evaluation artifacts. |
| F4-05 | todo | Clean-clone walkthrough and recorded-demo instructions. |
