"""Standalone platform command."""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from . import __version__
from .app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(prog="melampus-platform")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4318)
    parser.add_argument("--database", type=Path, default=Path(".melampus/platform.sqlite3"))
    parser.add_argument("--max-spans", type=int, default=250_000)
    parser.add_argument("--retention-days", type=int, default=7)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--catalog", type=Path, help="load an opt-in JSON declaration catalog")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or min(args.max_spans, args.retention_days) < 1:
        parser.error("port must be 1–65535; capacity and retention must be positive")
    uvicorn.run(
        create_app(
            args.database,
            demo=args.demo,
            max_spans=args.max_spans,
            retention_days=args.retention_days,
            catalog_path=args.catalog,
        ),
        host=args.host,
        port=args.port,
    )


if __name__ == "__main__":
    main()
