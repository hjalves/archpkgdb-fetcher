.PHONY: all sync typecheck lint lint-check format test

all: sync typecheck lint format test

sync:
	uv sync
typecheck:
	uv run mypy .
lint:
	uv run ruff check . --fix
lint-check:
	uv run ruff check .
format:
	uv run ruff format .
test:
	uv run pytest
