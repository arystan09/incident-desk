# Incident Desk

Incident Desk is a personal Applied AI engineering portfolio project for a clearly
labeled synthetic service environment. It is intended to become a resumable agent
that gathers incident evidence, produces an evidence-backed conclusion or abstains,
and proposes a local ticket update that requires human approval before application.
There are no claimed customers, production deployments, or measured business results.

Current status: **F1 foundation only**. Implemented today: an installable Python
package, validated configuration, an application factory, process liveness, isolated
unit tests, quality commands, a container definition, and GitHub Actions CI.

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
docker compose -p incident-desk-f1 up --build -d --wait
curl http://127.0.0.1:8000/health/live
docker compose -p incident-desk-f1 down
```

Use `curl.exe` on Windows. Compose runs only the API and binds host port 8000 to
loopback. The image uses Python 3.12, locked runtime dependencies, a non-root user,
and a standard-library HTTP liveness check. `.env` is excluded from the build.
The base image tags can receive upstream updates; the Python dependency lock does
not pin the entire operating system image.

## Design and current limitations

See [architecture](docs/architecture.md), [initial ADR](docs/adr/0001-initial-architecture.md),
and [roadmap](ROADMAP.md). There is no persistence, authentication, worker, model
provider, evidence tool, approval workflow, UI, or telemetry yet. Liveness only
checks that the HTTP process responds; database readiness is not implemented.
Docker execution and hosted CI require their respective runtimes; local verification
evidence and any unrun checks are recorded in the roadmap. This is not a
production-ready incident system.
