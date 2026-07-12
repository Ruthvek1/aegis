from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter

# Pricing for models per 1M tokens (Input / Output)
MODEL_PRICING = {
    # Haiku pricing: $0.25 per 1M input, $1.25 per 1M output
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    # NVIDIA Llama 3.1 Pricing (Approximate)
    "meta/llama-3.1-8b-instruct": {"input": 0.15, "output": 0.15},
    "meta/llama-3.1-70b-instruct": {"input": 0.88, "output": 0.88},
}


def setup_telemetry(exporter: SpanExporter | None = None) -> None:
    """
    Sets up the OpenTelemetry TracerProvider.
    If exporter is provided (e.g. InMemorySpanExporter for tests), it will be used.
    If no exporter is set and no environment variables ask for it,
    OpenTelemetry defaults to a no-op tracer implicitly, avoiding performance overhead.
    """
    if exporter is not None:
        provider = TracerProvider()
        processor = SimpleSpanProcessor(exporter)
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)


def get_tracer(name: str):
    """
    Returns a tracer for the given module name.
    If setup_telemetry() wasn't called, this safely returns a NoOpTracer.
    """
    return trace.get_tracer(name)
