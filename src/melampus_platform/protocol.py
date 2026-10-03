"""OTLP normalization with the SDK's existing declaration validation."""

from __future__ import annotations

import base64
import json
import re
import time
from typing import Any

from google.protobuf.json_format import ParseDict
from melampus import _semconv as sc
from melampus.watcher import decode
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

MAX_BODY = 1024 * 1024
MAX_BATCH_SPANS = 5_000
MAX_TIMESTAMP = (1 << 63) - 1
RESOURCE_KEYS = {
    "service.name",
    "service.version",
    "service.namespace",
    "deployment.environment.name",
    "deployment.environment",
    "melampus.origin",
}


def value(item: Any) -> Any:
    kind = item.WhichOneof("value")
    if kind == "array_value":
        return [value(v) for v in item.array_value.values]
    if kind in {"string_value", "bool_value", "int_value", "double_value"}:
        return getattr(item, kind)
    return None


def _json_ids(document: dict[str, Any]) -> None:
    # OTLP JSON uses hex IDs, unlike protobuf's usual base64 JSON mapping.
    for resource in document.get("resourceSpans", []):
        for scope in resource.get("scopeSpans", []):
            for span in scope.get("spans", []):
                for target in [span, *span.get("links", [])]:
                    for key, size in (("traceId", 32), ("spanId", 16), ("parentSpanId", 16)):
                        identifier = target.get(key)
                        if identifier in (None, ""):
                            continue
                        if not isinstance(identifier, str) or not re.fullmatch(
                            rf"[0-9a-fA-F]{{{size}}}", identifier
                        ):
                            raise ValueError("invalid OTLP JSON identifier")
                        target[key] = base64.b64encode(bytes.fromhex(identifier)).decode()


def parse(payload: bytes, content_type: str) -> list[dict[str, Any]]:
    """Validate a complete batch before any row is committed."""
    request = ExportTraceServiceRequest()
    if content_type == "application/json":
        document = json.loads(payload)
        if not isinstance(document, dict):
            raise ValueError("OTLP JSON must be an object")
        _json_ids(document)
        ParseDict(document, request, ignore_unknown_fields=True)
    else:
        request.ParseFromString(payload)
    # Reuse the SDK wire contract rather than accepting convincing but invalid evidence.
    decode(request.SerializeToString())
    records: list[dict[str, Any]] = []
    received = time.time_ns()
    for resource in request.resource_spans:
        resource_attrs = {
            attr.key: value(attr.value)
            for attr in resource.resource.attributes
            if attr.key in RESOURCE_KEYS
        }
        for key, item in resource_attrs.items():
            if not isinstance(item, str) or len(item) > 256 or not item.isprintable():
                raise ValueError(f"invalid resource attribute: {key}")
        for scope in resource.scope_spans:
            for span in scope.spans:
                if len(records) >= MAX_BATCH_SPANS:
                    raise ValueError("too many spans in one request")
                if (
                    len(span.trace_id) != 16
                    or not any(span.trace_id)
                    or len(span.span_id) != 8
                    or not any(span.span_id)
                    or (span.parent_span_id and len(span.parent_span_id) != 8)
                ):
                    raise ValueError("invalid trace or span identifier")
                if not 0 < span.start_time_unix_nano <= span.end_time_unix_nano <= MAX_TIMESTAMP:
                    raise ValueError("invalid span timestamps")
                if not span.name or len(span.name) > 512 or not span.name.isprintable():
                    raise ValueError("invalid span name")
                if span.status.code not in (0, 1, 2):
                    raise ValueError("invalid span status")
                attrs = {
                    attr.key: value(attr.value)
                    for attr in span.attributes
                    if attr.key
                    in {
                        sc.SCHEMA_VERSION,
                        sc.FUNCTION,
                        sc.GENERATOR,
                        sc.INTENT_HASH,
                        sc.ASSUMPTIONS_HASH,
                        sc.CHECK_IDS,
                        sc.CHECK_CONTRACT_HASHES,
                        sc.CHECK_SAMPLE_RATES,
                        sc.CHECK_RESULTS,
                    }
                }
                checks = [
                    {
                        "id": identifier,
                        "contract_hash": contract,
                        "sample_rate": rate,
                        "result": result,
                    }
                    for identifier, contract, rate, result in zip(
                        attrs.get(sc.CHECK_IDS, []),
                        attrs.get(sc.CHECK_CONTRACT_HASHES, []),
                        attrs.get(sc.CHECK_SAMPLE_RATES, []),
                        attrs.get(sc.CHECK_RESULTS, []),
                        strict=True,
                    )
                ]
                results = [c["result"] for c in checks]
                if "failed" in results:
                    outcome = "drift"
                elif "error" in results or span.status.code == 2:
                    outcome = "error"
                elif any(
                    r in {"sampled_out", "budget", "disabled", "not_executed"} for r in results
                ):
                    outcome = "incomplete"
                elif results:
                    outcome = "aligned"
                else:
                    outcome = "unverified"
                origin = resource_attrs.get("melampus.origin", "application")
                records.append(
                    {
                        "trace_id": span.trace_id.hex(),
                        "span_id": span.span_id.hex(),
                        "parent_span_id": span.parent_span_id.hex() or None,
                        "name": span.name,
                        "function": attrs.get(sc.FUNCTION, span.name),
                        "service": resource_attrs.get("service.name", "unknown-service"),
                        "environment": resource_attrs.get(
                            "deployment.environment.name",
                            resource_attrs.get("deployment.environment", "unspecified"),
                        ),
                        "version": resource_attrs.get("service.version", ""),
                        "origin": origin if origin in {"platform", "demo"} else "application",
                        "start_ns": span.start_time_unix_nano,
                        "end_ns": span.end_time_unix_nano,
                        "duration_ms": (span.end_time_unix_nano - span.start_time_unix_nano) / 1e6,
                        "received_ns": received,
                        "outcome": outcome,
                        "is_melampus": sc.SCHEMA_VERSION in attrs,
                        "intent_hash": attrs.get(sc.INTENT_HASH),
                        "generator": attrs.get(sc.GENERATOR),
                        "attributes": attrs,
                        "resource": resource_attrs,
                        "checks": checks,
                    }
                )
    return records
