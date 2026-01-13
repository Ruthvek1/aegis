import pytest
import pytest_asyncio
import os
import uuid
import shutil
from unittest.mock import patch

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool
from langchain_core.messages import AIMessage

from aegis.graph import build_graph
from aegis.memory import MemoryManager
from aegis.telemetry import setup_telemetry
from aegis.time_travel import fork_from_step
from aegis.cassette import CassetteChatModel, hash_prompt


# --- FIXTURES ---


@pytest.fixture
def exporter():
    exp = InMemorySpanExporter()
    setup_telemetry(exp)
    yield exp
    exp.clear()


@pytest.fixture(scope="module")
def cassette_dir():
    cdir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "cassettes_test")
    )
    os.makedirs(cdir, exist_ok=True)
    yield cdir
    shutil.rmtree(cdir, ignore_errors=True)


DB_URI = os.getenv(
    "DATABASE_URL", "postgresql://postgres:password@localhost:5432/aegis"
)


@pytest_asyncio.fixture
async def checkpointer():
    connection_kwargs = {"autocommit": True, "prepare_threshold": 0}
    pool = AsyncConnectionPool(DB_URI, kwargs=connection_kwargs, open=False)
    await pool.open()
    async with pool:
        chk = AsyncPostgresSaver(pool)
        await chk.setup()
        yield chk


@pytest_asyncio.fixture
async def memory_manager():
    mm = MemoryManager(DB_URI)
    await mm.open()
    await mm._ensure_ready()
    # Replace global
    import aegis.memory

    aegis.memory._global_mm = mm
    yield mm
    await mm.close()
    aegis.memory._global_mm = None


# --- TESTS ---


class MockChatModel:
    def __init__(self, *args, **kwargs):
        self.model_name = "claude-3-haiku-20240307"
        self.mock_invoke_return = AIMessage(
            content="mocked output",
            response_metadata={"usage": {"input_tokens": 100, "output_tokens": 50}},
        )

    async def ainvoke(self, *args, **kwargs):
        return self.mock_invoke_return

    def with_structured_output(self, schema, **kwargs):
        class DummyRunnable:
            async def ainvoke(self, *a, **k):
                if schema.__name__ == "PlanOutput":
                    return schema(plan=[{"step": "1", "action": "test plan"}])
                elif schema.__name__ == "CriticDecision":
                    return schema(approved=True, feedback="LGTM")
                return schema()

        return DummyRunnable()


@pytest.mark.asyncio
async def test_otel_tracing(exporter, checkpointer, memory_manager):
    with patch(
        "aegis.agents.get_llm",
        return_value=CassetteChatModel(
            MockChatModel(), "dummy", "claude-3-haiku-20240307"
        ),
    ):
        graph = build_graph(checkpointer=checkpointer)
        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}

        await graph.ainvoke({"task": "Tracing test"}, config)

        spans = exporter.get_finished_spans()
        assert len(spans) > 0, "No spans exported"

        span_names = [s.name for s in spans]
        # supervisor_node is intentionally NOT instrumented (it stays synchronous),
        # so assert the instrumented worker nodes each produced a span.
        assert "planner_node" in span_names
        assert "coder_node" in span_names
        assert "critic_node" in span_names
        assert "synthesizer_node" in span_names

        # Check LLM span attributes
        llm_spans = [s for s in spans if s.name.startswith("llm_call")]
        assert len(llm_spans) > 0

        for span in llm_spans:
            # We only have cost for non-structured calls right now, or if it was captured
            if "llm.cost" in span.attributes:
                cost = span.attributes["llm.cost"]
                assert cost >= 0.0
                assert span.attributes["llm.tokens.input"] >= 0


@pytest.mark.asyncio
async def test_event_log_replay(checkpointer, memory_manager):
    with patch("aegis.agents.get_llm", return_value=MockChatModel()):
        graph = build_graph(checkpointer=checkpointer)
        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}

        await graph.ainvoke({"task": "Event log test"}, config)

        events = await memory_manager.replay_log(thread_id)
        assert len(events) > 0

        # Verify the sequence of nodes
        node_names = [e["node_name"] for e in events]
        assert "planner_node" in node_names
        assert "coder_node" in node_names


@pytest.mark.asyncio
async def test_cassette_determinism(cassette_dir):
    # Pass 1: Record
    os.environ["LIVE_API_CASSETTE"] = "record"
    model = CassetteChatModel(MockChatModel(), cassette_dir, "claude-3-haiku-20240307")
    res1 = await model.ainvoke("Tell me a joke")

    # Pass 2: Replay without MockChatModel working
    class BrokenModel:
        async def ainvoke(self, *args, **kwargs):
            raise Exception("Should not hit network!")

    os.environ["LIVE_API_CASSETTE"] = "replay"
    model2 = CassetteChatModel(BrokenModel(), cassette_dir, "claude-3-haiku-20240307")
    res2 = await model2.ainvoke("Tell me a joke")

    assert res1.content == res2.content
    os.environ.pop("LIVE_API_CASSETTE")


def test_cassette_stable_hash():
    # Prove that UUIDs are stripped
    prompt1 = "Hello user 123e4567-e89b-12d3-a456-426614174000"
    prompt2 = "Hello user 987f6543-a21b-34c5-d678-901234567890"

    h1 = hash_prompt(prompt1, {})
    h2 = hash_prompt(prompt2, {})

    assert h1 == h2, "Hashes should be identical after UUID scrub"


@pytest.mark.asyncio
async def test_fork_from_step(checkpointer, memory_manager):
    with patch("aegis.agents.get_llm", return_value=MockChatModel()):
        graph = build_graph(checkpointer=checkpointer)
        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}

        # Run full graph
        await graph.ainvoke({"task": "Fork test"}, config)

        # Fork from step 1 (right after planner)
        new_state = {"scratchpad": {"forked": True}}
        new_config = await fork_from_step(graph, thread_id, 2, new_state)

        # The new thread should have the injected state
        forked_state = await graph.aget_state(new_config)
        assert forked_state.values.get("scratchpad", {}).get("forked") is True
        assert forked_state.config["configurable"]["thread_id"] != thread_id
