.PHONY: dev lint typecheck test cov build ci run
dev:
	uv sync --locked
lint:
	uv run --locked ruff check .
	uv run --locked ruff format --check .
typecheck:
	uv run --locked mypy -p melampus_platform
test:
	uv run --locked pytest
cov:
	uv run --locked pytest --cov=melampus_platform --cov-report=term-missing --cov-fail-under=85
build:
	uv build --no-build-isolation
	uv run --locked twine check --strict dist/*
	uv run --locked python scripts/check_dist.py
ci: dev lint typecheck cov build
run:
	uv run --locked melampus-platform $(ARGS)
