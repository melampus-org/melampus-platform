# Melampus

## Purpose and users
Melampus helps developers keep code aligned with reviewed intent using executable
checks and OpenTelemetry execution evidence. The SDK serves AI coding sessions
and ordinary Python applications. The tracing platform serves developers
investigating failed intent checks at the function level.

## Platform
Web interface served by the standalone melampus-platform Python application. The first platform is
local, with persistent storage, as confirmed by the user. Team accounts and a
hosted service are outside this first version.

## Stack
The user delegated the choice between Python and TypeScript. Python fits the
existing SDK, protobuf definitions, and reviewed contracts. The platform uses
FastAPI, SQLite, and a browser interface without a separate frontend build.
The platform depends on the published SDK wheel. SDK users do not need the platform.

## Primary workflow
Find failed intent checks, then inspect the trace (confirmed by the user).
Filter traces by service, environment, function, time, and outcome; inspect a
parent/child waterfall and individual check evidence. Show platform self traces
so developers can investigate the platform's own intent checks.

## Product constraints
- Receive standard OTLP/HTTP traces from Melampus instrumented applications.
- Use the existing Melampus SDK to instrument the platform itself.
- Preserve schema 0.1.0 semantics: failed, errored, suppressed, and unexecuted
  checks must remain distinguishable. Missing evidence is not a pass.
- The SDK sends declaration hashes, identifiers, and outcomes, not intent prose,
  arguments, return values, or exception messages. The interface must describe
  this honestly and never invent the missing prose.
- Demonstrations execute actual SDK instrumentation and are labeled synthetic.
- Local data survives application restarts. Capacity and retention are bounded.

## Brand commitment
The user requested a Datadog inspired interface focused on tracing. Preserve the
familiar dense explorer, facets, time controls, and waterfall investigation
workflow. The identity and terminology belong to Melampus.

## Open decisions
Authentication, multi tenancy, distributed storage, and hosted deployment remain
future product decisions.

## System Mesh extension
The user requested a whole-codebase mesh view for the next version. Include declared
boundaries without execution, readable catalog intent and contracts, dependency context,
and observed execution evidence. Catalog text is explicit opt-in and never reconstructed
from OTLP hashes. Missing evidence and mismatched declarations remain distinguishable.
