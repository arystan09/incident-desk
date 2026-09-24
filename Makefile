.PHONY: install dev lint format typecheck test check

install:
	uv sync --locked

dev:
	uv run --locked uvicorn incident_desk.main:create_app --factory --reload --host 127.0.0.1 --port 8000

lint:
	uv run --locked ruff check .

format:
	uv run --locked ruff format .

typecheck:
	uv run --locked mypy

test:
	uv run --locked pytest

check:
	uv run --locked ruff format --check .
	uv run --locked ruff check .
	uv run --locked mypy
	uv run --locked pytest
