"""Explicit declaration catalogs: text is opt-in, never reconstructed from OTLP."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from melampus import Contract
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_FUNCTIONS = 1000
MAX_EDGES = 3000
MAX_CATALOGS = 16


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def node_id(service: str, function: str) -> str:
    return digest(json.dumps([service, function], separators=(",", ":")))


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class DeclarationCheck(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,64}$")
    contract: str = Field(min_length=1, max_length=4000)
    sample: float = Field(default=1.0, ge=0, le=1, allow_inf_nan=False)


class FunctionRef(StrictModel):
    service: str = Field(min_length=1, max_length=256)
    function: str = Field(min_length=3, max_length=256)

    @field_validator("service", "function")
    @classmethod
    def printable(cls, value: str) -> str:
        if not value.isprintable():
            raise ValueError("identifiers must be printable")
        return value

    @field_validator("function")
    @classmethod
    def qualified(cls, value: str) -> str:
        if value.count(":") != 1 or any(not p for p in value.split(":")):
            raise ValueError("function must be module:qualified_name")
        return value


class Declaration(FunctionRef):
    intent: str = Field(min_length=1, max_length=8000)
    assumptions: list[str] = Field(default_factory=list, max_length=32)
    checks: list[DeclarationCheck] = Field(default_factory=list, max_length=16)

    @field_validator("assumptions")
    @classmethod
    def bounded_assumptions(cls, values: list[str]) -> list[str]:
        if any(not v or len(v) > 2000 for v in values):
            raise ValueError("assumptions must have 1–2000 characters")
        return values

    @model_validator(mode="after")
    def unique_checks(self) -> Declaration:
        if len({c.id for c in self.checks}) != len(self.checks):
            raise ValueError("check IDs must be unique")
        return self

    def evidence(self) -> dict[str, Any]:
        return {
            **self.model_dump(),
            "intent_hash": digest(self.intent),
            "assumptions_hash": digest(
                json.dumps(self.assumptions, ensure_ascii=False, separators=(",", ":"))
            ),
            "checks": [
                {**c.model_dump(), "contract_hash": digest(c.contract)} for c in self.checks
            ],
        }


class Dependency(StrictModel):
    source: FunctionRef
    target: FunctionRef


class Catalog(StrictModel):
    schema_version: str = Field(pattern=r"^1\.0\.0$")
    codebase: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    revision: str = Field(min_length=1, max_length=128)
    functions: list[Declaration] = Field(min_length=1, max_length=MAX_FUNCTIONS)
    dependencies: list[Dependency] = Field(default_factory=list, max_length=MAX_EDGES)

    @field_validator("revision")
    @classmethod
    def valid_revision(cls, value: str) -> str:
        if not value.isprintable():
            raise ValueError("revision must be printable")
        return value

    @model_validator(mode="after")
    def consistent(self) -> Catalog:
        keys = {(f.service, f.function) for f in self.functions}
        if len(keys) != len(self.functions):
            raise ValueError("function identities must be unique")
        edges = set()
        for edge in self.dependencies:
            source = (edge.source.service, edge.source.function)
            target = (edge.target.service, edge.target.function)
            if source not in keys or target not in keys:
                raise ValueError("dependency endpoints must be declared functions")
            if (source, target) in edges:
                raise ValueError("dependencies must be unique")
            edges.add((source, target))
        return self


def from_contracts(
    *,
    codebase: str,
    revision: str,
    service: str,
    contracts: Mapping[str, Contract],
    dependencies: Sequence[tuple[str, str]] = (),
) -> dict[str, Any]:
    """Export reviewed Contract objects without executing their predicates."""
    document = {
        "schema_version": "1.0.0",
        "codebase": codebase,
        "revision": revision,
        "functions": [
            {
                "service": service,
                "function": path,
                "intent": contract.intent,
                "assumptions": list(contract.assumptions),
                "checks": [
                    {"id": c.id, "contract": c.contract, "sample": float(c.sample)}
                    for c in contract.checks
                ],
            }
            for path, contract in contracts.items()
        ],
        "dependencies": [
            {
                "source": {"service": service, "function": source},
                "target": {"service": service, "function": target},
            }
            for source, target in dependencies
        ],
    }
    return Catalog.model_validate(document).model_dump()


def matches(declaration: dict[str, Any], span: dict[str, Any]) -> bool:
    """Bind prose only to exact SDK intent, assumptions, check IDs/hashes/rates."""
    declared = {c["id"]: (c["contract_hash"], c["sample"]) for c in declaration["checks"]}
    observed = {c["id"]: (c["contract_hash"], c["sample_rate"]) for c in span["checks"]}
    return (
        declaration["intent_hash"] == span["intent_hash"]
        and declaration["assumptions_hash"]
        == span["attributes"].get("code_artifact.assumptions.hash")
        and declared == observed
    )
