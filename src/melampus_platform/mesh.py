"""Join explicit declarations to bounded runtime evidence and observed call edges."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .catalog import Catalog, matches, node_id
from .store import OUTCOME_RANK

MAX_NODES = 2000
MAX_OBSERVED_EDGES = 4000


def build(catalog: dict[str, Any] | None, spans: list[dict[str, Any]]) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[tuple[str, str], dict[str, Any]] = {}
    if catalog:
        for function in Catalog.model_validate(catalog).functions:
            declaration = function.evidence()
            identity = node_id(function.service, function.function)
            nodes[identity] = {
                "id": identity,
                "service": function.service,
                "function": function.function,
                "module": function.function.split(":")[0],
                "declaration": declaration,
            }
        for edge in catalog["dependencies"]:
            key = (
                node_id(**edge["source"]),
                node_id(**edge["target"]),
            )
            edges[key] = {"source": key[0], "target": key[1], "declared": True, "calls": 0}
    checked = [s for s in spans if s["is_melampus"]]
    for span in checked:
        identity = node_id(span["service"], span["function"])
        node = nodes.setdefault(
            identity,
            {
                "id": identity,
                "service": span["service"],
                "function": span["function"],
                "module": span["function"].split(":")[0],
                "declaration": None,
            },
        )
        node.setdefault("observations", []).append(span)
    for node in nodes.values():
        observations = node.pop("observations", [])
        results = Counter(c["result"] for s in observations for c in s["checks"])
        outcomes = [s["outcome"] for s in observations]
        matching = [
            s for s in observations if node["declaration"] and matches(node["declaration"], s)
        ]
        matching_checks: dict[str, Counter[str]] = {}
        for span in matching:
            for check in span["checks"]:
                matching_checks.setdefault(check["id"], Counter())[check["result"]] += 1
        node.update(
            {
                "calls": len(observations),
                "outcome": min(outcomes, key=OUTCOME_RANK.__getitem__)
                if outcomes
                else "unobserved",
                "failed_checks": results["failed"],
                "check_counts": dict(results),
                "matching_calls": len(matching),
                "mismatched_calls": len(observations) - len(matching) if node["declaration"] else 0,
                "declaration_status": (
                    "unknown"
                    if not node["declaration"]
                    else "unobserved"
                    if not observations
                    else "mismatch"
                    if len(matching) != len(observations)
                    else "matching"
                ),
                "check_observations": {key: dict(value) for key, value in matching_checks.items()},
                "intent_hashes": sorted({s["intent_hash"] for s in observations}),
                "trace_ids": list(dict.fromkeys(s["trace_id"] for s in observations))[:5],
            }
        )
    lookup = {(s["trace_id"], s["span_id"]): s for s in spans}
    for span in checked:
        parent_id = span["parent_span_id"]
        visited = {span["span_id"]}
        while parent_id and parent_id not in visited:
            visited.add(parent_id)
            parent = lookup.get((span["trace_id"], parent_id))
            if parent is None:
                break
            if parent["is_melampus"]:
                key = (
                    node_id(parent["service"], parent["function"]),
                    node_id(span["service"], span["function"]),
                )
                if key[0] in nodes and key[1] in nodes:
                    edge = edges.setdefault(
                        key, {"source": key[0], "target": key[1], "declared": False, "calls": 0}
                    )
                    edge["calls"] += 1
                break
            parent_id = parent["parent_span_id"]
    rows = sorted(
        nodes.values(),
        key=lambda n: (not bool(n["declaration"]), n["service"], n["module"], n["function"]),
    )
    visible = rows[:MAX_NODES]
    ids = {n["id"] for n in visible}
    connections = sorted(
        [e for e in edges.values() if e["source"] in ids and e["target"] in ids],
        key=lambda e: (not e["declared"], -e["calls"], e["source"], e["target"]),
    )[:MAX_OBSERVED_EDGES]
    return {
        "nodes": visible,
        "edges": connections,
        "summary": {
            "declared": sum(bool(n["declaration"]) for n in rows),
            "observed": sum(n["calls"] > 0 for n in rows),
            "unobserved": sum(n["calls"] == 0 for n in rows),
            "drift": sum(n["outcome"] == "drift" for n in rows),
            "mismatch": sum(n["declaration_status"] == "mismatch" for n in rows),
            "unknown": sum(n["declaration"] is None for n in rows),
        },
        "total_nodes": len(rows),
        "total_edges": len(edges),
        "truncated": len(visible) != len(rows) or len(connections) != len(edges),
    }
