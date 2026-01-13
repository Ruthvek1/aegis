import pytest
import os
import uuid
from unittest.mock import patch, MagicMock

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool
from aegis.graph import build_graph, supervisor_node


# --- MOCKS ---
class MockRunnable:
    def __init__(self, return_value):
        self._return_value = return_value

    async def ainvoke(self, *args, **kwargs):
        return self._return_value


class MockChatModel:
    def __init__(self, *args, **kwargs):
        self.mock_invoke_return = MagicMock(content="coder output")

    async def ainvoke(self, *args, **kwargs):
        return self.mock_invoke_return

    def with_structured_output(self, schema, **kwargs):
        # Return a Runnable that returns a canned instance of the schema
        if schema.__name__ == "PlanOutput":
            val = schema(plan=[{"step": "1", "action": "mock plan"}])
        elif schema.__name__ == "CriticDecision":
            # For exact budget tests, we can toggle this
            val = schema(
                approved=getattr(self, "mock_critic_approved", True),
                feedback="mock feedback",
            )
        else:
            val = schema()
        return MockRunnable(val)


# --- TESTS ---


@pytest.fixture(autouse=True)
def mock_memory_record():
    with patch("aegis.memory.MemoryManager.record_event") as mock_record:
        mock_record.return_value = None
        yield mock_record


@pytest.fixture
def mock_llm():
    with patch("aegis.agents.get_llm", return_value=MockChatModel()) as mock:
        yield mock


@pytest.mark.asyncio
async def test_supervisor_routing():
    # Unit test for routing
    state = {"plan": [], "scratchpad": {}, "budget": 3}
    res = supervisor_node(state)
    assert res["next"] == "planner"
    assert res["budget"] == 3

    state = {"plan": [{"step": 1}], "scratchpad": {}, "budget": 3}
    res = supervisor_node(state)
    assert res["next"] == "researcher"

    state = {"plan": [{"step": 1}], "scratchpad": {"research_done": True}, "budget": 3}
    res = supervisor_node(state)
    assert res["next"] == "coder"

    state = {
        "plan": [{"step": 1}],
        "scratchpad": {"research_done": True, "coder_output": "code"},
        "budget": 3,
    }
    res = supervisor_node(state)
    assert res["next"] == "critic"

    state = {
        "plan": [{"step": 1}],
        "scratchpad": {
            "research_done": True,
            "coder_output": "code",
            "critic_approved": True,
        },
        "budget": 3,
    }

    res = supervisor_node(state)
    assert res["next"] == "synthesizer"


@pytest.mark.asyncio
async def test_happy_path(mock_llm):
    graph = build_graph()
    res = await graph.ainvoke({"task": "do a thing", "budget": 3})
    assert len(res["plan"]) > 0
    assert "coder_output" in res["scratchpad"]
    assert res["scratchpad"]["critic_approved"] is True


@pytest.mark.asyncio
async def test_veto_budget(mock_llm):
    # Make critic always veto
    mock_instance = MockChatModel()
    mock_instance.mock_critic_approved = False
    mock_llm.return_value = mock_instance

    graph = build_graph()
    res = await graph.ainvoke({"task": "impossible task", "budget": 3})

    # Assert budget was exhausted exactly
    assert res["budget"] == 0
    assert res["scratchpad"]["critic_approved"] is False


# --- CRASH RECOVERY TEST ---

DB_URI = os.getenv(
    "DATABASE_URL", "postgresql://postgres:password@localhost:5432/aegis"
)


@pytest.mark.asyncio
async def test_crash_recovery(mock_llm):
    # 1. Setup Postgres saver and create tables
    connection_kwargs = {"autocommit": True, "prepare_threshold": 0}
    pool = AsyncConnectionPool(DB_URI, kwargs=connection_kwargs, open=False)
    await pool.open()
    async with pool:
        checkpointer = AsyncPostgresSaver(pool)
        await checkpointer.setup()

        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}

        # We want to interrupt graph_a mid-run.
        # Let's set a breakpoint before "coder"
        graph_a = build_graph(checkpointer=checkpointer, interrupt_before=["coder"])

        await graph_a.ainvoke({"task": "recover me", "budget": 3}, config)

        # It should halt before coder. Verify state.
        state_a = await graph_a.aget_state(config)
        assert state_a.next == ("coder",)
        assert len(state_a.values["plan"]) > 0

    # Pool is closed, graph_a is discarded.

    # Instance B (Fresh)
    pool_b = AsyncConnectionPool(DB_URI, kwargs=connection_kwargs, open=False)
    await pool_b.open()
    async with pool_b:
        checkpointer_b = AsyncPostgresSaver(pool_b)
        graph_b = build_graph(checkpointer=checkpointer_b)

        # Resume from where we left off
        # The state should be loaded from the DB, not RAM.
        state_b = await graph_b.aget_state(config)
        assert state_b.next == ("coder",)

        # Resume execution
        final_res = await graph_b.ainvoke(None, config)

        assert "coder_output" in final_res["scratchpad"]
        assert final_res["scratchpad"]["critic_approved"] is True
