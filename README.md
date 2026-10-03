# Melampus platform

A local, persistent tracing workbench for codebase intent and executable contract evidence.
Python 3.11+. Experimental alpha; one workspace on a trusted local machine.

## Run

```sh
git clone https://github.com/melampus-org/melampus-platform.git
cd melampus-platform
uv sync --locked
make run ARGS="--demo"
```

Open **http://127.0.0.1:4318**. Send OTLP/HTTP protobuf or JSON to
**http://127.0.0.1:4318/v1/traces**. The platform pins the published Melampus Python
SDK v0.2.0 GitHub wheel; no unpublished local SDK changes are required.

- Failure-first explorer, service/environment/source filters, live refresh and search.
- Proportional trace waterfalls with per-function check outcomes and declaration hashes.
- SQLite persistence, seven-day retention and bounded admission with retry deduplication.
- Actual Melampus SDK instrumentation of platform ingestion and queries.
- Synthetic checkout example with evaluated failures, errors and suppressed checks.

[Setup, APIs and evidence semantics](docs/PLATFORM.md) · [Release process](docs/RELEASE.md)

## Development

```sh
make ci
uv run python examples/send_traces.py
```

Release decisions are VERSION and CHANGELOG.md changes. GitHub Actions validates,
tags and uploads wheel/source assets on main. PyPI publication is separate.
