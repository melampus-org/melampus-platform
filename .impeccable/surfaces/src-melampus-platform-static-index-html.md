---
version: 1
slug: "src-melampus-platform-static-index-html"
primary_target: "src/melampus_platform/static/index.html"
related_targets: ["src/melampus_platform/static/app.js","src/melampus_platform/static/style.css"]
---

# Intent tracing explorer

Scope: src/melampus_platform/static/. Mode: Operate.
Audience: developers investigating failed intent checks in a local codebase.
Task: identify drift, filter relevant traces, inspect a waterfall and its checks.
Proof: actual SDK generated spans, persistent evidence, self instrumentation.
Constraint: familiar Datadog tracing workflow explicitly pinned by the user.

## Direction contract
THESIS: A failure-first intent tracing workbench, where a failed contract is one
click from its function and parent trace. Evidence remains connected to timing.

OWN-WORLD: Pale neutral reading fields, dark violet navigation, purple actions,
fine table rules, fixed sans typography, and red/amber/green evidence states with
text labels. Code and hashes use mono; trace facts use tabular numerals.

STORY: The developer sees actual traffic, narrows the failure set using facets,
opens a trace, selects a function span, and reads each check's exact outcome.
Synthetic traffic and platform self traces are explicitly identified.

FIRST VIEWPORT: A compact left navigation rail, breadcrumb and title, search and
time controls, a trace volume histogram, compact evidence totals, facets beside
a dense table. The failed-check filter is the primary investigation shortcut.
A trace opens a persistent side panel with a proportional waterfall and checks.

FORM: Brief-pinned Datadog style tracing explorer. Seed 944c10d9 ran; the explicit
competitor reference and failure-first workflow override the assigned direction.
Code-led build. Existing site/ is a separate marketing surface and stays intact.
Signature interaction: selecting a waterfall span reveals its contract evidence.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance


## System Mesh extension (v0.2.0)
Task: see the whole codebase's declared intent, contracts and dependencies alongside observed calls.
Inherit the existing Operate world and dense Datadog-style navigation and evidence labels.
FIRST VIEWPORT: codebase, evidence time and environment controls; compact coverage facts;
a grouped code boundary map next to a readable intent/check inspector, with full function inventory below.
Signature interaction: select a boundary to read its exact catalog text and matching runtime check evidence.
Distinguish dashed declared dependencies from solid observed calls. Unobserved declarations remain visible;
missing catalogs remain hash-only, and mismatched declarations never explain unrelated execution.
Build path: code-led extension of the incumbent application. No new visual identity or raster assets.
