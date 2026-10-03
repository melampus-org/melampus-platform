# System Mesh (v0.2.0)

System Mesh combines an explicit declaration catalog with the retained runtime traces.
It is an inventory of authored code boundaries and executable claims, not a source-code inference engine.

## Use it

Open System Mesh, choose a codebase and evidence window, and select a boundary.
The inspector shows declared intent, assumptions and check contract text, their hashes,
and matching execution evidence. Solid edges are observed calls; dashed edges are declared
dependencies without observed calls. No execution means no evidence, never a pass.
Search matches function identifiers, service, intent and check contract text. The full
loaded function inventory remains accessible below the map. Select a trace link to inspect
its waterfall. On narrow screens, selecting a boundary brings its inspector into view.

Platform itself includes its real ingestion, decoding, catalog and query contracts.
Synthetic demo includes checkout checks and a declared reconciliation boundary not exercised
by the checkout scenario. Both catalogs reuse the exact Contract objects used by instrumentation.
The platform declaration inventory covers its instrumented SDK boundaries, not every uninstrumented helper.

## Export your declarations

Keep your reviewed Contract objects in a mapping keyed by full module:qualified_name paths.
Use the same mapping for SDK instrumentation and for the catalog exporter:

```python
import json
from melampus import Check, Contract
from melampus_platform.catalog import from_contracts

CONTRACTS = {
    "payments:authorize": Contract(
        "Return a valid payment authorization",
        (Check("authorized", lambda r: r is True, "Payment is authorized"),),
    ),
}
catalog = from_contracts(
    codebase="my-system",
    revision="reviewed-git-sha",
    service="my-application",
    contracts=CONTRACTS,
)
with open("declarations.json", "w") as file:
    json.dump(catalog, file)
```

Import the file in the interface, POST it as JSON to /api/catalog, or start with
`melampus-platform --catalog declarations.json`. The platform reads JSON only and never
imports application modules or executes catalog predicates. Explicit import is the opt-in
for storing readable intent/contract text locally; ordinary OTLP stays hash-only.

For multiple services or TypeScript SDK applications, author the same language-neutral
JSON shape: schema_version 1.0.0, codebase, revision, functions (service, function, intent,
assumptions, checks with id/contract/sample), and dependencies with source/target
service/function references. A built-in export example is in examples/export_catalog.py.

## Evidence binding and bounds

Text is associated with calls only when intent SHA-256, assumptions SHA-256, check IDs,
check contract SHA-256 hashes and configured sample rates all match the SDK declaration.
The hash algorithm is exactly the SDK's UTF-8 SHA-256 and compact JSON assumptions encoding.
Changed declarations stay visible as mismatches; their unrelated calls are excluded from
per-contract result totals. Revision is an author-supplied label, not verified Git provenance.

A catalog is atomic and persistent, replaces the latest catalog for its codebase, and is
limited to 1 MiB, 1000 functions, 16 checks/function and 3000 unique declared dependencies.
At most 16 codebases are stored. Catalogs persist independently of span retention.
A selected codebase scopes runtime evidence to its declared service names; service names
should identify a codebase uniquely. Environment/time filters affect evidence, not the
inventory. Without a catalog, observed functions have unknown text.

The API snapshot is bounded to 2000 nodes and 4000 connections; it explicitly reports
truncation and complete totals. The map draws at most 160 matching nodes; search narrows it,
and the inventory lists the loaded snapshot. Direct parent/child evidence is grouped by
trace ID, traversing ordinary context spans to the nearest Melampus ancestor. Missing parents
produce no inferred connection. These bounds serve a local workspace rather than distributed analytics.

GET /api/mesh accepts codebase, minutes (1–10080), and environment.
POST /api/catalog requires JSON and rejects unrelated browser origins.
