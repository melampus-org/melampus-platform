# Changelog

## [Unreleased]

## [0.2.0] - 2026-10-03

### Added
- Whole-codebase System Mesh with grouped boundaries, declared dependencies and observed call edges.
- Opt-in JSON declaration catalogs with readable intent, assumptions and executable contract claims.
- Exact SDK hash/identifier/sample matching; mismatched calls do not borrow catalog check text.
- Visible unobserved declarations, function inventory, search, codebase/time/environment controls and trace links.
- Persistent catalog import API, JSON-only startup catalogs and a Contract-to-catalog exporter.
- Built-in catalogs generated from the same platform and synthetic demo Contract objects as instrumentation.

### Scope
- Catalogs describe author-declared boundaries; this version does not infer arbitrary source code or static calls.
- Ordinary OTLP stays hash-only. Text capture happens only through explicit catalog import.

## [0.1.0] - 2026-10-03

### Added
- Local persistent OTLP/HTTP protobuf and JSON receiver with gzip, bounded batches and deduplication.
- Failure-first trace explorer, filters, histogram, function aggregates and proportional waterfall.
- Exact check outcomes, declaration hashes and explicit synthetic/platform source labels.
- Real Melampus SDK instrumentation of ingestion and query contracts without export recursion.
- Standalone command, packaged browser assets, tests and automatic GitHub releases.

### Scope
- Local single workspace alpha; no team accounts, hosted deployment or gRPC receiver.
- Intent prose stays in code; trace declarations are hash-only in this version.
