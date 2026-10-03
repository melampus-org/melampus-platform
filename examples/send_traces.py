"""Send real Melampus traces over HTTP to the local platform.

uv run python examples/send_traces.py
"""

from __future__ import annotations

import argparse

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from melampus_platform.demo import generate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:4318/v1/traces")
    parser.add_argument("--count", type=int, default=24)
    args = parser.parse_args()
    if not 1 <= args.count <= 100:
        parser.error("count must be between 1 and 100")
    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": "checkout-service",
                "deployment.environment.name": "local",
                "melampus.origin": "demo",
            }
        )
    )
    provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter(endpoint=args.endpoint)))
    try:
        result = generate(provider, args.count)
        print(f"Generated {result['generated_traces']} synthetic checkout traces → {args.endpoint}")
        print(f"Inspect trace: {result['trace_ids'][0]}")
    finally:
        provider.shutdown()


if __name__ == "__main__":
    main()
