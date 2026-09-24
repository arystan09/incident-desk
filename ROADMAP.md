# Roadmap

Current milestone: **F1 — Durable investigation foundation**.
Statuses: `todo | in_progress | blocked | in_review | done`.
Owner verification is required to move work from `in_review` to `done`.
Current task: F1-02 persistence only. Do not proceed to F1-03.

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

### F1-02: PostgreSQL run/job/step models and migrations

- Status: blocked
- Dependencies: F1-01 (accepted by owner).
- Scope: SQLAlchemy 2 synchronous sessions, psycopg 3, explicit engine/transaction
  ownership, run/job/step constraints and indexes, Alembic migrations, disposable
  PostgreSQL integration tests, optional Compose database, and CI integration job.
  Database readiness is deferred until an API operation uses persistence; no fake
  readiness route or public run endpoint is introduced.
- Acceptance: migrations apply to an empty real PostgreSQL database, model metadata
  matches, downgrade/base/upgrade round-trip succeeds only in a disposable database;
  records and JSONB round-trip; status/counter/FK/uniqueness constraints and restricted
  deletion reject invalid operations; a failed unit of work rolls back run and job;
  liveness works without a database; explicit integration requests fail if unavailable.
- Evidence (2026-09-25, Python 3.12.14): locked sync succeeded; Ruff linting and
  formatting verification passed; mypy passed for 8 application source files;
  `uv run --locked pytest` passed 25 unit tests with 16 integration cases deselected.
  The existing Starlette/HTTPX deprecation warning remains. `uv build` produced a
  wheel and source archive, inspected to exclude credentials and local caches.
  `uv run --locked alembic upgrade head --sql` rendered the complete PostgreSQL DDL
  successfully; this is not evidence of PostgreSQL execution.
- Blocker: `uv run --locked pytest -m integration tests/integration --maxfail=1`
  collected 16 cases and failed at setup with the actionable missing
  TEST_DATABASE_URL message (no tests silently skipped). No running PostgreSQL
  service/listener or Docker is available. The local PostgreSQL 17 directory has
  postgres/psql executables but lacks initdb and pg_ctl, so it cannot provision a
  fresh isolated server using those tools. No system service or OS setting changed.
- Unverified: actual upgrade/downgrade, live schema comparison, SQL constraints,
  persistence, and rollback against PostgreSQL. Docker build/startup and both hosted
  CI jobs remain unrun. Set up the dedicated local test role/URL using README.md,
  run all 16 integration cases, and only then mark this task in_review.

### F1-03: Tenant-scoped API authentication and idempotent run creation

- Status: todo
- Dependencies: F1-02.
- Scope: authenticated tenant context, authorization, request validation,
  idempotency constraints, and run creation/status endpoints.
- Acceptance: same tenant/key/input returns the same run, including concurrent
  requests; different input conflicts; cross-tenant access is denied; callers cannot
  set trusted tenant identity through a request body.
- Evidence: none; not implemented.

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
