"""Local HTTP receiver, trace APIs, and the browser explorer."""

from __future__ import annotations

import gzip
import io
import json
import re
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from google.protobuf.json_format import ParseError
from google.protobuf.message import DecodeError
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from . import __version__
from .demo import demo_catalog, generate
from .protocol import MAX_BODY
from .store import OUTCOME_RANK, Store
from .telemetry import Runtime, provider_for

STATIC = Path(__file__).parent / "static"


def create_app(
    database: Path | str = ".melampus/platform.sqlite3",
    *,
    demo: bool = False,
    max_spans: int = 250_000,
    retention_days: int = 7,
    catalog_path: Path | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        store = Store(database, max_spans=max_spans, retention_days=retention_days)
        runtime = Runtime(store)
        # Demo providers use an unwrapped sink too. They do not need their own collector spans.
        demo_provider, demo_exporter = provider_for(
            store, service="checkout-service", origin="demo", sink=runtime.exporter.sink
        )
        app.state.runtime = runtime
        app.state.demo_provider = demo_provider
        app.state.demo_exporter = demo_exporter
        app.state.demo_lock = threading.Lock()
        app.state.last_demo = 0.0
        try:
            store.import_catalog(runtime.catalog())
            if catalog_path is not None:
                if catalog_path.stat().st_size > MAX_BODY:
                    raise ValueError("Catalog exceeds 1 MiB")
                store.import_catalog(json.loads(catalog_path.read_text()))
            if demo:
                store.import_catalog(demo_catalog())
                await run_in_threadpool(generate, demo_provider)
            yield
        finally:
            demo_provider.shutdown()
            runtime.close()

    app = FastAPI(
        title="Melampus Intent Tracing",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.middleware("http")
    async def headers(request: Request, call_next: Any) -> Response:
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/healthz")
    def health() -> dict[str, str]:
        return {"status": "ready"}

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        runtime: Runtime = app.state.runtime
        return {
            **runtime.store.stats(),
            "telemetry_dropped": runtime.exporter.dropped,
            "demo_telemetry_dropped": app.state.demo_exporter.dropped,
            "schema_version": "0.1.0",
            "platform_version": __version__,
        }

    @app.post("/api/catalog")
    async def import_catalog(request: Request) -> dict[str, Any]:
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "Catalog imports must be requested from this platform")
        if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
            raise HTTPException(415, "Upload a JSON declaration catalog")
        payload = bytearray()
        async for chunk in request.stream():
            payload.extend(chunk)
            if len(payload) > MAX_BODY:
                raise HTTPException(413, "Catalog exceeds 1 MiB")
        try:
            document = json.loads(payload)
            runtime: Runtime = app.state.runtime
            return await run_in_threadpool(runtime.store.import_catalog, document)
        except (ValueError, TypeError, ValidationError) as exc:
            raise HTTPException(
                422,
                "Invalid declaration catalog; check schema, unique identities and dependency endpoints",
            ) from exc
        except OverflowError as exc:
            raise HTTPException(503, str(exc)) from exc

    @app.get("/api/mesh")
    def mesh(
        codebase: Annotated[str, Query(max_length=64)] = "",
        environment: Annotated[str, Query(max_length=256)] = "",
        minutes: Annotated[int, Query(ge=1, le=10_080)] = 60,
    ) -> dict[str, Any]:
        end = time.time_ns()
        runtime: Runtime = app.state.runtime
        try:
            return runtime.store.mesh(
                codebase=codebase,
                since_ns=end - minutes * 60 * 1_000_000_000,
                until_ns=end,
                environment=environment,
            )
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/v1/traces")
    async def receive(request: Request) -> Response:
        media = request.headers.get("content-type", "").split(";")[0].strip().lower()
        if media not in {"application/x-protobuf", "application/json"}:
            raise HTTPException(415, "Use OTLP/HTTP protobuf or JSON")
        encoding = request.headers.get("content-encoding", "identity").lower()
        if encoding not in {"identity", "gzip"}:
            raise HTTPException(415, "Use identity or gzip content encoding")
        payload = bytearray()
        async for chunk in request.stream():
            payload.extend(chunk)
            if len(payload) > MAX_BODY:
                raise HTTPException(413, "OTLP body exceeds 1 MiB")
        try:
            body = bytes(payload)
            if encoding == "gzip":
                with gzip.GzipFile(fileobj=io.BytesIO(body)) as stream:
                    body = stream.read(MAX_BODY + 1)
                if len(body) > MAX_BODY:
                    raise HTTPException(413, "Decompressed OTLP body exceeds 1 MiB")
            runtime: Runtime = app.state.runtime

            def accept() -> dict[str, int]:
                with runtime.tracer.start_as_current_span(
                    "OTLP receive", record_exception=False, set_status_on_exception=False
                ):
                    records = runtime.parse(body, media)
                    return runtime.store.ingest(records)

            await run_in_threadpool(accept)
        except (
            ValueError,
            DecodeError,
            ParseError,
            OSError,
            EOFError,
            TypeError,
            AttributeError,
            KeyError,
            RecursionError,
        ) as exc:
            raise HTTPException(400, "Invalid OTLP telemetry or Melampus declaration") from exc
        except OverflowError as exc:
            raise HTTPException(
                503,
                "Span capacity reached; increase --max-spans or shorten --retention-days",
                headers={"Retry-After": "30"},
            ) from exc
        if media == "application/json":
            return Response("{}", media_type=media)
        return Response(ExportTraceServiceResponse().SerializeToString(), media_type=media)

    @app.get("/api/traces")
    def explore(
        query: Annotated[str, Query(max_length=256)] = "",
        service: Annotated[str, Query(max_length=256)] = "",
        environment: Annotated[str, Query(max_length=256)] = "",
        origin: str = "",
        outcome: str = "",
        minutes: Annotated[int, Query(ge=1, le=10_080)] = 60,
        since_ns: Annotated[int | None, Query(ge=1, le=(1 << 63) - 1)] = None,
        until_ns: Annotated[int | None, Query(ge=1, le=(1 << 63) - 1)] = None,
        offset: Annotated[int, Query(ge=0, le=250_000)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        sort: str = "recent",
    ) -> dict[str, Any]:
        if outcome and outcome not in OUTCOME_RANK:
            raise HTTPException(422, "Unknown trace outcome")
        if origin not in {"", "platform", "demo", "application"} or sort not in {
            "recent",
            "duration",
            "failures",
        }:
            raise HTTPException(422, "Unknown origin or sort order")
        end = until_ns if until_ns is not None else time.time_ns()
        start = since_ns if since_ns is not None else end - minutes * 60 * 1_000_000_000
        if start >= end or end - start > 7 * 86_400 * 1_000_000_000:
            raise HTTPException(422, "Time window must be positive and no longer than seven days")
        runtime: Runtime = app.state.runtime
        result = runtime.store.explore(
            since_ns=start,
            until_ns=end,
            query=query,
            service=service,
            environment=environment,
            outcome=outcome,
            origin=origin,
            offset=offset,
            limit=limit,
            sort=sort,
        )
        return result

    @app.get("/api/traces/{trace_id}")
    def trace_detail(trace_id: str) -> dict[str, Any]:
        if not re.fullmatch(r"[0-9a-f]{32}", trace_id):
            raise HTTPException(422, "Trace IDs must be 32 lowercase hexadecimal characters")
        runtime: Runtime = app.state.runtime
        result = runtime.store.trace(trace_id)
        if result is None:
            raise HTTPException(404, "Trace was not found or has expired")
        return result

    @app.post("/api/demo")
    def demo_traffic(request: Request) -> dict[str, Any]:
        # Browser mutations must be same-origin; no CORS is enabled on the receiver.
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "Demo traffic must be requested from this platform")
        if not app.state.demo_lock.acquire(blocking=False):
            raise HTTPException(429, "Demo generation is already running")
        try:
            if time.monotonic() - app.state.last_demo < 3:
                raise HTTPException(429, "Wait three seconds before generating another demo")
            app.state.last_demo = time.monotonic()
            runtime: Runtime = app.state.runtime
            runtime.store.import_catalog(demo_catalog())
            result = generate(app.state.demo_provider)
            if app.state.demo_exporter.dropped:
                raise HTTPException(
                    503, "Demo telemetry could not be fully stored; check platform capacity"
                )
            return result
        finally:
            app.state.demo_lock.release()

    return app
