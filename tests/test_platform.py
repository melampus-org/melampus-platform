"""Exercise real SDK wire output, persistence, evidence semantics, and dogfooding."""

import gzip
import json
import time

import pytest
from google.protobuf.json_format import MessageToDict
from melampus import Check, Policy, instrumented
from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans

from melampus_platform.protocol import MAX_BODY, parse
from melampus_platform.store import Store


def sdk_request(telemetry, *, result=-1, policy=None, explode=False):
    tracer, exporter = telemetry

    @instrumented(
        intent="Return a nonnegative result",
        checks=(Check("nonnegative", lambda r: r >= 0, "Result must be nonnegative"),),
        tracer=tracer,
        policy=policy,
        generator="platform-tests",
        path="payments.service:charge",
    )
    def charge():
        if explode:
            raise RuntimeError("secret exception text")
        return result

    with tracer.start_as_current_span("payments.request"):
        try:
            charge()
        except RuntimeError:
            pass
    request = encode_spans(exporter.get_finished_spans())
    for resource in request.resource_spans:
        resource.resource.attributes.add(key="service.name").value.string_value = "payments"
        resource.resource.attributes.add(
            key="deployment.environment.name"
        ).value.string_value = "test"
        resource.resource.attributes.add(key="secret.resource").value.string_value = "never-store"
        for scope in resource.scope_spans:
            for span in scope.spans:
                span.attributes.add(key="secret.argument").value.string_value = "never-store"
    return request


def post(client, request):
    return client.post(
        "/v1/traces",
        content=request.SerializeToString(),
        headers={"content-type": "application/x-protobuf"},
    )


def test_sdk_to_receiver_trace_and_check_evidence(client, telemetry):
    request = sdk_request(telemetry)
    assert post(client, request).status_code == 200
    response = client.get("/api/traces", params={"service": "payments", "outcome": "drift"}).json()
    assert response["total"] == 1
    assert response["summary"]["failed_checks"] == 1
    assert response["summary"]["pass_rate"] == 0
    assert len(response["histogram"]) == 48
    assert sum(b["total"] for b in response["histogram"]) == 1
    detail = client.get("/api/traces/" + response["traces"][0]["trace_id"]).json()
    assert detail["span_count"] == 2
    assert detail["name"] == "payments.request"
    checked = next(s for s in detail["spans"] if s["is_melampus"])
    assert checked["parent_span_id"] in {s["span_id"] for s in detail["spans"]}
    assert checked["checks"][0]["id"] == "nonnegative"
    assert checked["checks"][0]["result"] == "failed"
    assert len(checked["intent_hash"]) == 64
    assert "never-store" not in json.dumps(detail)
    assert "secret exception" not in json.dumps(detail)


@pytest.mark.parametrize(
    "result,policy,explode,outcome,check_result",
    [
        (3, None, False, "aligned", "passed"),
        (-1, None, False, "drift", "failed"),
        (3, Policy(checks_per_second=0), False, "incomplete", "budget"),
        (3, None, True, "error", "not_executed"),
    ],
)
def test_evidence_outcomes_do_not_conflate_missing_with_passing(
    client,
    telemetry,
    result,
    policy,
    explode,
    outcome,
    check_result,
):
    request = sdk_request(telemetry, result=result, policy=policy, explode=explode)
    assert post(client, request).status_code == 200
    data = client.get("/api/traces", params={"service": "payments"}).json()
    assert data["traces"][0]["outcome"] == outcome
    assert data["traces"][0]["check_counts"] == {check_result: 1}
    if check_result not in {"passed", "failed"}:
        assert data["summary"]["pass_rate"] is None
        assert data["summary"]["incomplete_checks"] == 1


def test_otlp_retries_are_deduplicated_and_child_search_keeps_parent(client, telemetry):
    request = sdk_request(telemetry)
    post(client, request)
    post(client, request)
    data = client.get("/api/traces", params={"query": "payments.service:charge"}).json()
    assert data["total"] == 1
    assert data["traces"][0]["span_count"] == 2
    assert data["traces"][0]["failed_checks"] == 1
    assert data["functions"][0]["calls"] == 1
    assert client.get("/api/traces", params={"query": "%"}).json()["total"] == 0
    assert client.get("/api/traces", params={"query": "' OR 1=1 --"}).json()["total"] == 0


def test_otlp_json_uses_hex_ids_and_gzip(client, telemetry):
    request = sdk_request(telemetry, result=2)
    document = MessageToDict(request)
    for source, target in zip(request.resource_spans, document["resourceSpans"], strict=True):
        for scope, scope_json in zip(source.scope_spans, target["scopeSpans"], strict=True):
            for span, span_json in zip(scope.spans, scope_json["spans"], strict=True):
                span_json["traceId"] = span.trace_id.hex().upper()
                span_json["spanId"] = span.span_id.hex().upper()
                if span.parent_span_id:
                    span_json["parentSpanId"] = span.parent_span_id.hex().upper()
    response = client.post(
        "/v1/traces",
        content=gzip.compress(json.dumps(document).encode()),
        headers={"content-type": "application/json; charset=utf-8", "content-encoding": "gzip"},
    )
    assert response.status_code == 200 and response.json() == {}
    assert (
        client.get("/api/traces", params={"service": "payments"}).json()["traces"][0]["outcome"]
        == "aligned"
    )


def test_batch_validation_is_atomic(client, telemetry):
    request = sdk_request(telemetry)
    invalid = request.resource_spans[0].scope_spans[0].spans.add()
    invalid.name = "invalid"
    invalid.start_time_unix_nano = time.time_ns()
    invalid.end_time_unix_nano = time.time_ns()
    assert post(client, request).status_code == 400
    assert client.get("/api/traces", params={"service": "payments"}).json()["total"] == 0


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: setattr(s, "end_time_unix_nano", 1),
        lambda s: setattr(s, "trace_id", b"\0" * 16),
        lambda s: setattr(s, "span_id", b"short"),
        lambda s: setattr(s, "name", "bad\nname"),
        lambda s: setattr(s, "end_time_unix_nano", (1 << 63) + 1),
    ],
)
def test_invalid_timing_and_identifiers_are_rejected(client, telemetry, mutate):
    request = sdk_request(telemetry)
    mutate(request.resource_spans[0].scope_spans[0].spans[0])
    assert post(client, request).status_code == 400


def test_invalid_declarations_and_unsupported_payloads(client, telemetry):
    request = sdk_request(telemetry)
    # The fixture also gives ordinary spans an unrelated attribute: find the declaration explicitly.
    checked = next(
        s
        for r in request.resource_spans
        for scope in r.scope_spans
        for s in scope.spans
        if any(a.key == "code_artifact.schema.version" for a in s.attributes)
    )
    next(
        a for a in checked.attributes if a.key == "code_artifact.check.results"
    ).value.array_value.values[0].string_value = "invented"
    assert post(client, request).status_code == 400
    assert (
        client.post(
            "/v1/traces", content=b"bad", headers={"content-type": "application/x-protobuf"}
        ).status_code
        == 400
    )
    assert (
        client.post("/v1/traces", content=b"{}", headers={"content-type": "text/plain"}).status_code
        == 415
    )
    assert (
        client.post(
            "/v1/traces",
            content=b"{}",
            headers={"content-type": "application/json", "content-encoding": "br"},
        ).status_code
        == 415
    )
    assert (
        client.post(
            "/v1/traces", content=b"[]", headers={"content-type": "application/json"}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/v1/traces",
            content=b"\x1f\x8b",
            headers={"content-type": "application/json", "content-encoding": "gzip"},
        ).status_code
        == 400
    )


def test_body_and_decompression_are_bounded(client):
    headers = {"content-type": "application/x-protobuf"}
    assert (
        client.post("/v1/traces", content=b"x" * (MAX_BODY + 1), headers=headers).status_code == 413
    )
    assert (
        client.post(
            "/v1/traces",
            content=gzip.compress(b"x" * (MAX_BODY + 1)),
            headers={**headers, "content-encoding": "gzip"},
        ).status_code
        == 413
    )


def test_capacity_and_retention_are_atomic_and_persistent(tmp_path, telemetry):
    records = parse(sdk_request(telemetry).SerializeToString(), "application/x-protobuf")
    database = tmp_path / "persistent.sqlite3"
    store = Store(database, max_spans=1)
    with pytest.raises(OverflowError):
        store.ingest(records)
    assert store.stats()["stored_spans"] == 0
    assert store.ingest(records[:1])["accepted"] == 1
    assert store.ingest(records[:1])["duplicates"] == 1
    store.close()
    reopened = Store(database, max_spans=1)
    assert reopened.trace(records[0]["trace_id"])["span_count"] == 1
    old = {**records[1], "start_ns": 1, "end_ns": 2}
    assert reopened.ingest([old])["expired"] == 1
    assert reopened.stats()["stored_spans"] == 1
    reopened.db.execute("UPDATE spans SET end_ns=1")
    reopened.db.commit()
    assert reopened.stats()["stored_spans"] == 0
    reopened.close()


def test_platform_self_traces_are_real_sdk_checks_and_do_not_recurse(client):
    for _ in range(4):
        assert client.get("/api/traces").status_code == 200
    runtime = client.app.state.runtime
    data = runtime.exporter.sink.__self__.explore(
        since_ns=time.time_ns() - 60 * 1_000_000_000, until_ns=time.time_ns(), origin="platform"
    )
    assert data["total"] == 5
    assert data["summary"]["evaluated_checks"] == 13
    assert data["summary"]["pass_rate"] == 1
    assert all(t["service"] == "melampus-platform" for t in data["traces"])
    assert runtime.exporter.dropped == 0
    assert client.get("/api/status").json()["stored_spans"] < 10


def test_synthetic_demo_has_failure_error_suppression_and_success(client):
    response = client.post("/api/demo")
    assert response.status_code == 200
    assert response.json()["generated_traces"] == 24
    data = client.get(
        "/api/traces", params={"origin": "demo", "sort": "failures", "limit": 5}
    ).json()
    assert data["total"] == 24
    assert len(data["traces"]) == 5
    assert data["traces"][0]["failed_checks"] > 0
    assert set(data["facets"]["outcomes"]) == {"drift", "error", "incomplete", "aligned"}
    assert data["summary"]["incomplete_checks"] > 0
    assert any(f["function"] == "checkout.pricing:calculate_total" for f in data["functions"])
    second = client.get(
        "/api/traces", params={"origin": "demo", "offset": 5, "limit": 5, "sort": "failures"}
    ).json()
    assert not ({t["trace_id"] for t in second["traces"]} & {t["trace_id"] for t in data["traces"]})
    assert client.post("/api/demo").status_code == 429
    assert (
        client.post("/api/demo", headers={"Origin": "https://unrelated.example"}).status_code == 403
    )


@pytest.mark.parametrize(
    "params",
    [
        {"outcome": "unknown"},
        {"origin": "unknown"},
        {"sort": "unknown"},
        {"limit": 101},
        {"offset": -1},
        {"minutes": 0},
        {"minutes": 10081},
        {"since_ns": 100, "until_ns": 99},
        {"since_ns": 1, "until_ns": 8 * 86_400 * 1_000_000_000},
    ],
)
def test_bad_queries_are_rejected(client, params):
    assert client.get("/api/traces", params=params).status_code == 422


def test_missing_trace_static_assets_and_security_headers(client):
    assert client.get("/api/traces/" + "0" * 32).status_code == 404
    assert client.get("/api/traces/not-a-trace").status_code == 422
    response = client.get("/")
    assert response.status_code == 200
    assert "Trace Explorer" in response.text
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200
    assert client.get("/api/status").headers["Cache-Control"] == "no-store"
    assert client.get("/healthz").json() == {"status": "ready"}


def test_invalid_storage_configuration(tmp_path):
    with pytest.raises(ValueError):
        Store(tmp_path / "bad.sqlite3", max_spans=0)
    with pytest.raises(ValueError):
        Store(tmp_path / "bad.sqlite3", retention_days=0)
