"""Dogfood the SDK through OTLP without recursively tracing the exporter."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable, Sequence
from typing import Any

from melampus import Check, Contract, instrument, instrumented
from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.trace import Tracer

from . import __version__
from .catalog import from_contracts
from .protocol import parse
from .store import Store

logger = logging.getLogger(__name__)


class LocalOTLPExporter(SpanExporter):
    """Serialize real SDK spans and feed the same validated receiver pipeline.

    Keep the original unwrapped sink: exporter spans must never export themselves.
    This avoids a loopback HTTP server dependency and preserves shutdown flushing.
    """

    def __init__(self, sink: Callable[[list[dict[str, Any]]], dict[str, int]]):
        self.sink = sink
        self.dropped = 0

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            self.sink(parse(encode_spans(spans).SerializeToString(), "application/x-protobuf"))
        except (ValueError, OverflowError, OSError, sqlite3.Error):
            self.dropped += len(spans)
            logger.warning("Platform telemetry could not be stored; %d spans dropped", len(spans))
            return SpanExportResult.FAILURE
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        pass


def provider_for(
    store: Store,
    *,
    service: str,
    origin: str,
    sink: Callable[[list[dict[str, Any]]], dict[str, int]] | None = None,
) -> tuple[TracerProvider, LocalOTLPExporter]:
    exporter = LocalOTLPExporter(sink if sink is not None else store.ingest)
    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": service,
                "service.version": __version__,
                "deployment.environment.name": "local",
                "melampus.origin": origin,
            }
        )
    )
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


class Runtime:
    def __init__(self, store: Store):
        self.store = store
        # The exporter captures the original sink before registration mutates the instance.
        self.provider, self.exporter = provider_for(
            store, service="melampus-platform", origin="platform"
        )
        self.tracer: Tracer = self.provider.get_tracer("melampus.platform", __version__)
        self.contracts = {
            "ingest": Contract(
                "Persist complete validated spans once, including retry deliveries.",
                (
                    Check(
                        "delivery-accounted",
                        lambda r: r["accepted"] + r["duplicates"] + r["expired"] == r["submitted"],
                        "Every delivery is accounted for as accepted, duplicate, or expired.",
                    ),
                ),
            ),
            "explore": Contract(
                "Return a bounded page and faithful aggregate check evidence for the selected traces.",
                (
                    Check(
                        "bounded-page",
                        lambda r: len(r["traces"]) <= r["limit"],
                        "A trace page never exceeds its requested limit.",
                    ),
                    Check(
                        "page-accounted",
                        lambda r: len(r["traces"]) <= r["total"],
                        "Every returned trace is accounted for in the matching total.",
                    ),
                    Check(
                        "evidence-rate",
                        lambda r: (
                            r["summary"]["pass_rate"] is None or 0 <= r["summary"]["pass_rate"] <= 1
                        ),
                        "The pass rate is absent without evaluated evidence, otherwise within zero and one.",
                    ),
                ),
            ),
            "trace": Contract(
                "Return every stored span for exactly the requested trace.",
                (
                    Check(
                        "single-trace",
                        lambda r: (
                            r is None or all(s["trace_id"] == r["trace_id"] for s in r["spans"])
                        ),
                        "All returned spans belong to the same trace.",
                    ),
                ),
            ),
        }
        self.contracts.update(
            {
                "import_catalog": Contract(
                    "Persist one complete, validated declaration catalog per codebase.",
                    (
                        Check(
                            "catalog-accounted",
                            lambda r: 1 <= r["functions"] <= 1000,
                            "The accepted catalog has a bounded, nonempty function inventory.",
                        ),
                    ),
                ),
                "mesh": Contract(
                    "Join declared code boundaries to exact execution evidence without inventing coverage.",
                    (
                        Check(
                            "mesh-accounted",
                            lambda r: len(r["nodes"]) <= r["total_nodes"],
                            "Every visible node is accounted for in the complete mesh total.",
                        ),
                    ),
                ),
            }
        )
        instrument(
            store,
            namespace="melampus.platform:Store",
            tracer=self.tracer,
            generator="melampus-platform",
            contracts=self.contracts,
        )
        self.decode_contract = Contract(
            "Decode and validate the complete OTLP batch before allowing persistence.",
            (
                Check(
                    "bounded-batch",
                    lambda r: len(r) <= 5_000,
                    "A decoded batch contains no more than 5,000 spans.",
                ),
            ),
        )
        self.parse = instrumented(
            intent=self.decode_contract.intent,
            checks=self.decode_contract.checks,
            tracer=self.tracer,
            generator="melampus-platform",
            path="melampus.platform:decode_batch",
        )(parse)

    def catalog(self) -> dict[str, Any]:
        contracts = {
            "melampus.platform:Store." + name: contract for name, contract in self.contracts.items()
        }
        contracts["melampus.platform:decode_batch"] = self.decode_contract
        return from_contracts(
            codebase="melampus-platform",
            revision="v" + __version__,
            service="melampus-platform",
            contracts=contracts,
            dependencies=[("melampus.platform:decode_batch", "melampus.platform:Store.ingest")],
        )

    def close(self) -> None:
        self.provider.shutdown()
        self.store.close()
