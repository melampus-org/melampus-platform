"""Persistent bounded storage; SQL values are always bound parameters."""

from __future__ import annotations

import json
import math
import sqlite3
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Any

OUTCOME_RANK = {"drift": 0, "error": 1, "incomplete": 2, "aligned": 3, "unverified": 4}


def summarize(spans: list[dict[str, Any]]) -> dict[str, Any]:
    """Do not let ordinary context spans turn a checked trace into an unknown trace."""
    ids = {s["span_id"] for s in spans}
    roots = [s for s in spans if s["parent_span_id"] not in ids]
    root = min(roots or spans, key=lambda s: (s["start_ns"], s["span_id"]))
    outcomes = [s["outcome"] for s in spans if s["outcome"] != "unverified"]
    start = min(s["start_ns"] for s in spans)
    end = max(s["end_ns"] for s in spans)
    checks = Counter(c["result"] for s in spans for c in s["checks"])
    return {
        "trace_id": root["trace_id"],
        "name": root["function"],
        "service": root["service"],
        "environment": root["environment"],
        "origin": root["origin"],
        "start_ns": start,
        "end_ns": end,
        "duration_ms": (end - start) / 1e6,
        "outcome": min(outcomes, key=OUTCOME_RANK.__getitem__) if outcomes else "unverified",
        "span_count": len(spans),
        "check_counts": dict(checks),
        "failed_checks": checks["failed"],
        "evaluated_checks": checks["passed"] + checks["failed"],
        "is_melampus": any(s["is_melampus"] for s in spans),
    }


class Store:
    def __init__(
        self, path: Path | str, *, max_spans: int = 250_000, retention_days: int = 7
    ) -> None:
        if max_spans < 1 or retention_days < 1:
            raise ValueError("capacity and retention must be positive")
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.max_spans = max_spans
        self.retention_days = retention_days
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS spans (
                trace_id TEXT NOT NULL, span_id TEXT NOT NULL,
                service TEXT NOT NULL, environment TEXT NOT NULL, origin TEXT NOT NULL,
                function TEXT NOT NULL, outcome TEXT NOT NULL,
                start_ns INTEGER NOT NULL, end_ns INTEGER NOT NULL, data TEXT NOT NULL,
                PRIMARY KEY (trace_id, span_id)
            );
            CREATE INDEX IF NOT EXISTS spans_start ON spans(start_ns);
            CREATE INDEX IF NOT EXISTS spans_service ON spans(service, start_ns);
            CREATE INDEX IF NOT EXISTS spans_outcome ON spans(outcome, start_ns);
            CREATE TABLE IF NOT EXISTS catalogs (
                codebase TEXT PRIMARY KEY, revision TEXT NOT NULL,
                imported_ns INTEGER NOT NULL, document TEXT NOT NULL
            );
            """
        )
        with self.lock, self.db:
            self._prune()

    def _prune(self) -> None:
        cutoff = time.time_ns() - self.retention_days * 86_400 * 1_000_000_000
        self.db.execute("DELETE FROM spans WHERE end_ns < ?", (cutoff,))

    def ingest(self, records: list[dict[str, Any]]) -> dict[str, int]:
        unique = {(s["trace_id"], s["span_id"]): s for s in records}
        accepted = 0
        duplicates = 0
        expired = 0
        with self.lock, self.db:
            self._prune()
            cutoff = time.time_ns() - self.retention_days * 86_400 * 1_000_000_000
            expired = sum(record["end_ns"] < cutoff for record in unique.values())
            unique = {key: record for key, record in unique.items() if record["end_ns"] >= cutoff}
            count = self.db.execute("SELECT COUNT(*) FROM spans").fetchone()[0]
            new = [
                record
                for key, record in unique.items()
                if not self.db.execute(
                    "SELECT 1 FROM spans WHERE trace_id=? AND span_id=?", key
                ).fetchone()
            ]
            if count + len(new) > self.max_spans:
                raise OverflowError("span capacity reached; increase capacity or shorten retention")
            for record in new:
                self.db.execute(
                    "INSERT INTO spans VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        record["trace_id"],
                        record["span_id"],
                        record["service"],
                        record["environment"],
                        record["origin"],
                        record["function"],
                        record["outcome"],
                        record["start_ns"],
                        record["end_ns"],
                        json.dumps(record, separators=(",", ":"), allow_nan=False),
                    ),
                )
                accepted += 1
            duplicates = len(records) - accepted - expired
        return {
            "accepted": accepted,
            "duplicates": duplicates,
            "expired": expired,
            "submitted": len(records),
        }

    def trace(self, trace_id: str) -> dict[str, Any] | None:
        with self.lock, self.db:
            self._prune()
            rows = self.db.execute(
                "SELECT data FROM spans WHERE trace_id=? ORDER BY start_ns, span_id", (trace_id,)
            ).fetchall()
        if not rows:
            return None
        spans = [json.loads(r[0]) for r in rows]
        return {**summarize(spans), "spans": spans}

    def explore(
        self,
        *,
        since_ns: int,
        until_ns: int,
        query: str = "",
        service: str = "",
        environment: str = "",
        outcome: str = "",
        origin: str = "",
        offset: int = 0,
        limit: int = 50,
        sort: str = "recent",
    ) -> dict[str, Any]:
        clauses = ["start_ns >= ?", "start_ns <= ?"]
        params: list[Any] = [since_ns, until_ns]
        for column, argument in (
            ("service", service),
            ("environment", environment),
            ("origin", origin),
        ):
            if argument:
                clauses.append(f"{column} = ?")
                params.append(argument)
        if query:
            # Literal search, including percent and underscore; no accidental wildcard queries.
            needle = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            clauses.append("(function LIKE ? ESCAPE '\\' OR trace_id LIKE ? ESCAPE '\\')")
            params.extend([f"%{needle}%", f"%{needle}%"])
        with self.lock, self.db:
            self._prune()
            # A matching child selects the entire trace, preserving waterfall context.
            rows = self.db.execute(
                f"SELECT data FROM spans WHERE trace_id IN (SELECT DISTINCT trace_id FROM spans "
                f"WHERE {' AND '.join(clauses)}) ORDER BY start_ns DESC, span_id",
                params,
            ).fetchall()
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            span = json.loads(row[0])
            groups.setdefault(span["trace_id"], []).append(span)
        traces = [summarize(spans) for spans in groups.values()]
        all_traces = traces
        if outcome:
            traces = [t for t in traces if t["outcome"] == outcome]
        if sort == "duration":
            traces.sort(key=lambda t: (-t["duration_ms"], -t["start_ns"], t["trace_id"]))
        elif sort == "failures":
            traces.sort(key=lambda t: (-t["failed_checks"], -t["start_ns"], t["trace_id"]))
        else:
            traces.sort(key=lambda t: (-t["start_ns"], t["trace_id"]))
        checks: Counter[str] = Counter()
        for trace in traces:
            checks.update(trace["check_counts"])
        durations = sorted(t["duration_ms"] for t in traces)
        bins = 48
        width = max(1, (until_ns - since_ns) // bins)
        histogram = [
            {"start_ns": since_ns + i * width, "total": 0, "drift": 0, "error": 0}
            for i in range(bins)
        ]
        for trace in traces:
            index = max(0, min(bins - 1, (trace["start_ns"] - since_ns) // width))
            histogram[index]["total"] += 1
            if trace["outcome"] in {"drift", "error"}:
                histogram[index][trace["outcome"]] += 1
        functions: dict[tuple[str, str], dict[str, Any]] = {}
        selected_ids = {t["trace_id"] for t in traces}
        for trace_id, spans in groups.items():
            if trace_id not in selected_ids:
                continue
            for span in spans:
                if not span["is_melampus"]:
                    continue
                key = (span["service"], span["function"])
                item = functions.setdefault(
                    key,
                    {
                        "service": key[0],
                        "function": key[1],
                        "calls": 0,
                        "failed": 0,
                        "errors": 0,
                        "incomplete": 0,
                        "evaluated": 0,
                        "intent_hashes": set(),
                        "last_seen_ns": 0,
                    },
                )
                item["calls"] += 1
                results = Counter(c["result"] for c in span["checks"])
                item["failed"] += results["failed"]
                item["errors"] += results["error"]
                item["incomplete"] += sum(
                    results[r] for r in ("budget", "disabled", "sampled_out", "not_executed")
                )
                item["evaluated"] += results["passed"] + results["failed"]
                item["intent_hashes"].add(span["intent_hash"])
                item["last_seen_ns"] = max(item["last_seen_ns"], span["start_ns"])
        function_rows = [
            {**f, "intent_hashes": sorted(f["intent_hashes"])} for f in functions.values()
        ]
        function_rows.sort(key=lambda f: (-f["failed"], -f["last_seen_ns"], f["function"]))
        return {
            "traces": traces[offset : offset + limit],
            "total": len(traces),
            "offset": offset,
            "limit": limit,
            "summary": {
                "traces": len(traces),
                "spans": sum(t["span_count"] for t in traces),
                "failed_checks": checks["failed"],
                "evaluated_checks": checks["passed"] + checks["failed"],
                "check_errors": checks["error"],
                "incomplete_checks": sum(
                    checks[r] for r in ("budget", "disabled", "sampled_out", "not_executed")
                ),
                "pass_rate": checks["passed"] / (checks["passed"] + checks["failed"])
                if checks["passed"] + checks["failed"]
                else None,
                "p95_ms": durations[max(0, math.ceil(len(durations) * 0.95) - 1)]
                if durations
                else None,
            },
            "facets": {
                "outcomes": dict(Counter(t["outcome"] for t in all_traces)),
                "services": sorted({s["service"] for spans in groups.values() for s in spans}),
                "environments": sorted(
                    {s["environment"] for spans in groups.values() for s in spans}
                ),
                "origins": dict(Counter(t["origin"] for t in all_traces)),
            },
            "histogram": histogram,
            "functions": function_rows,
            "since_ns": since_ns,
            "until_ns": until_ns,
        }

    def stats(self) -> dict[str, Any]:
        with self.lock, self.db:
            self._prune()
            count = self.db.execute("SELECT COUNT(*) FROM spans").fetchone()[0]
        return {
            "stored_spans": count,
            "max_spans": self.max_spans,
            "retention_days": self.retention_days,
        }

    def import_catalog(self, document: dict[str, Any]) -> dict[str, Any]:
        from .catalog import MAX_CATALOGS, Catalog

        catalog = Catalog.model_validate(document)
        with self.lock, self.db:
            existing = self.db.execute(
                "SELECT 1 FROM catalogs WHERE codebase=?", (catalog.codebase,)
            ).fetchone()
            if (
                not existing
                and self.db.execute("SELECT COUNT(*) FROM catalogs").fetchone()[0] >= MAX_CATALOGS
            ):
                raise OverflowError("catalog capacity reached (16 codebases)")
            self.db.execute(
                "INSERT INTO catalogs VALUES (?,?,?,?) ON CONFLICT(codebase) DO UPDATE SET "
                "revision=excluded.revision, imported_ns=excluded.imported_ns, document=excluded.document",
                (catalog.codebase, catalog.revision, time.time_ns(), catalog.model_dump_json()),
            )
        return {
            "codebase": catalog.codebase,
            "revision": catalog.revision,
            "functions": len(catalog.functions),
        }

    def mesh(
        self, *, codebase: str = "", since_ns: int, until_ns: int, environment: str = ""
    ) -> dict[str, Any]:
        from .mesh import build

        with self.lock, self.db:
            self._prune()
            catalogs = [
                dict(zip(("codebase", "revision", "imported_ns"), row, strict=True))
                for row in self.db.execute(
                    "SELECT codebase,revision,imported_ns FROM catalogs ORDER BY codebase"
                )
            ]
            selected = codebase or (catalogs[0]["codebase"] if catalogs else "")
            row = self.db.execute(
                "SELECT document FROM catalogs WHERE codebase=?", (selected,)
            ).fetchone()
            if codebase and row is None:
                raise LookupError("codebase catalog was not found")
            document = json.loads(row[0]) if row else None
            clauses = ["start_ns >= ?", "start_ns <= ?"]
            arguments: list[Any] = [since_ns, until_ns]
            if environment:
                clauses.append("environment=?")
                arguments.append(environment)
            if document:
                services = sorted({f["service"] for f in document["functions"]})
                clauses.append("service IN (" + ",".join("?" for _ in services) + ")")
                arguments.extend(services)
            rows = self.db.execute(
                "SELECT data FROM spans WHERE "
                + " AND ".join(clauses)
                + " ORDER BY start_ns DESC,span_id",
                arguments,
            ).fetchall()
        return {
            **build(document, [json.loads(row[0]) for row in rows]),
            "catalogs": catalogs,
            "codebase": selected,
            "revision": document["revision"] if document else None,
            "since_ns": since_ns,
            "until_ns": until_ns,
            "environment": environment,
        }

    def close(self) -> None:
        with self.lock:
            self.db.close()
