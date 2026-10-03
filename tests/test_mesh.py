"""Catalog evidence must describe exact declarations, never inferred prose or coverage."""

import copy
import json
import time

import pytest
from fastapi.testclient import TestClient
from melampus import Check, Contract

from melampus_platform.app import create_app
from melampus_platform.catalog import from_contracts
from melampus_platform.protocol import MAX_BODY, parse
from melampus_platform.store import Store
from tests.test_platform import post, sdk_request


def declaration():
    return from_contracts(
        codebase="payments-system",
        revision="reviewed-sha",
        service="payments",
        contracts={
            "payments.service:charge": Contract(
                "Return a nonnegative result",
                (Check("nonnegative", lambda r: r >= 0, "Result must be nonnegative"),),
            ),
            "payments.audit:reconcile": Contract(
                "Reconcile payments with orders",
                (Check("balanced", lambda r: r is True, "All payments are accounted for"),),
            ),
        },
        dependencies=[("payments.service:charge", "payments.audit:reconcile")],
    )


def test_catalog_persists_unobserved_inventory_and_exact_sdk_text(tmp_path, telemetry):
    path = tmp_path / "catalog.sqlite3"
    with TestClient(create_app(path)) as client:
        document = declaration()
        assert client.post("/api/catalog", json=document).status_code == 200
        post(client, sdk_request(telemetry))
        result = client.get("/api/mesh", params={"codebase": "payments-system"}).json()
        charge = next(n for n in result["nodes"] if n["function"].endswith(":charge"))
        audit = next(n for n in result["nodes"] if n["function"].endswith(":reconcile"))
        assert charge["declaration_status"] == "matching"
        assert charge["declaration"]["intent"] == "Return a nonnegative result"
        assert charge["check_observations"] == {"nonnegative": {"failed": 1}}
        assert audit["outcome"] == "unobserved" and audit["calls"] == 0
        assert audit["check_observations"] == {}
        assert result["edges"][0]["declared"] and result["edges"][0]["calls"] == 0
        assert result["summary"]["drift"] == 1
    with TestClient(create_app(path)) as restarted:
        assert (
            restarted.get("/api/mesh", params={"codebase": "payments-system"}).json()["revision"]
            == "reviewed-sha"
        )


@pytest.mark.parametrize("change", ["intent", "contract", "assumptions", "sample", "check_id"])
def test_mismatched_catalog_never_labels_runtime_checks_with_unrelated_text(
    tmp_path, telemetry, change
):
    with TestClient(create_app(tmp_path / "mesh.sqlite3")) as client:
        document = declaration()
        function = document["functions"][0]
        if change == "intent":
            function["intent"] = "Different intent"
        elif change == "contract":
            function["checks"][0]["contract"] = "Different claim"
        elif change == "assumptions":
            function["assumptions"] = ["A new assumption"]
        elif change == "sample":
            function["checks"][0]["sample"] = 0.5
        else:
            function["checks"][0]["id"] = "different-id"
        assert client.post("/api/catalog", json=document).status_code == 200
        post(client, sdk_request(telemetry))
        node = next(
            n
            for n in client.get("/api/mesh", params={"codebase": "payments-system"}).json()["nodes"]
            if n["calls"]
        )
        assert node["declaration_status"] == "mismatch"
        assert node["mismatched_calls"] == 1 and node["matching_calls"] == 0
        assert node["check_observations"] == {} and node["outcome"] == "drift"


def test_observed_edges_bridge_context_spans_but_do_not_invent_missing_parents(tmp_path, telemetry):
    records = parse(sdk_request(telemetry).SerializeToString(), "application/x-protobuf")
    checked = next(s for s in records if s["is_melampus"])
    parent = copy.deepcopy(checked)
    parent.update(span_id="1" * 16, function="payments.orders:submit", parent_span_id=None)
    context = next(s for s in records if not s["is_melampus"])
    context["parent_span_id"] = parent["span_id"]
    checked["parent_span_id"] = context["span_id"]
    store = Store(tmp_path / "edges.sqlite3")
    store.ingest([parent, context, checked])
    end = time.time_ns()
    graph = store.mesh(since_ns=end - 60 * 10**9, until_ns=end)
    assert len(graph["nodes"]) == 2
    assert graph["edges"][0]["calls"] == 1 and not graph["edges"][0]["declared"]
    assert all(n["declaration_status"] == "unknown" for n in graph["nodes"])
    store.close()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["functions"].append(d["functions"][0]),
        lambda d: d["dependencies"][0]["target"].update(function="missing:function"),
        lambda d: d.update(schema_version="999"),
        lambda d: d["functions"][0]["checks"].append(d["functions"][0]["checks"][0]),
        lambda d: d["functions"][0].update(source_code="never-accepted"),
        lambda d: d["functions"][0]["checks"][0].update(sample=2.0),
    ],
)
def test_invalid_catalog_is_atomic(client, mutate):
    good = declaration()
    assert client.post("/api/catalog", json=good).status_code == 200
    bad = copy.deepcopy(good)
    bad["revision"] = "bad"
    mutate(bad)
    assert client.post("/api/catalog", json=bad).status_code == 422
    assert (
        client.get("/api/mesh", params={"codebase": "payments-system"}).json()["revision"]
        == "reviewed-sha"
    )


def test_import_bounds_origin_scope_and_environment(client, telemetry):
    assert (
        client.post(
            "/api/catalog",
            content=b"x" * (MAX_BODY + 1),
            headers={"content-type": "application/json"},
        ).status_code
        == 413
    )
    assert (
        client.post(
            "/api/catalog", json=declaration(), headers={"Origin": "https://unrelated.example"}
        ).status_code
        == 403
    )
    assert client.post("/api/catalog", json=declaration()).status_code == 200
    post(client, sdk_request(telemetry))
    assert client.get("/api/mesh", params={"codebase": "missing"}).status_code == 404
    assert client.get("/api/mesh", params={"minutes": 10081}).status_code == 422
    result = client.get(
        "/api/mesh", params={"codebase": "payments-system", "environment": "production"}
    ).json()
    assert result["summary"]["observed"] == 0 and result["summary"]["unobserved"] == 2
    assert all(n["service"] == "payments" for n in result["nodes"])


def test_builtin_platform_catalog_matches_actual_self_instrumentation(client):
    client.get("/api/traces")
    graph = client.get("/api/mesh", params={"codebase": "melampus-platform"}).json()
    assert graph["summary"]["declared"] == 6
    assert graph["summary"]["mismatch"] == 0
    explore = next(n for n in graph["nodes"] if n["function"].endswith(".explore"))
    assert explore["calls"] == 1 and explore["declaration_status"] == "matching"
    assert "bounded-page" in explore["check_observations"]
    assert client.get("/api/status").json()["telemetry_dropped"] == 0


def test_builtin_demo_catalog_includes_unexercised_boundary(client):
    client.post("/api/demo")
    graph = client.get("/api/mesh", params={"codebase": "checkout-demo"}).json()
    assert graph["summary"]["declared"] == 6 and graph["summary"]["unobserved"] == 1
    assert graph["summary"]["mismatch"] == 0
    assert any(e["calls"] for e in graph["edges"])
    assert any(n["outcome"] == "incomplete" for n in graph["nodes"])


def test_startup_catalog_file_is_json_only(tmp_path):
    path = tmp_path / "declarations.json"
    path.write_text(json.dumps(declaration()))
    with TestClient(create_app(":memory:", catalog_path=path)) as client:
        assert client.get("/api/mesh", params={"codebase": "payments-system"}).status_code == 200
