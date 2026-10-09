import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


@pytest.fixture
def telemetry():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    yield provider.get_tracer("test"), exporter
    provider.shutdown()


@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient

    from melampus_platform.app import create_app

    with TestClient(create_app(tmp_path / "platform.sqlite3")) as instance:
        yield instance
