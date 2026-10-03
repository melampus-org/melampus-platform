# Changelog

## [Unreleased]

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
