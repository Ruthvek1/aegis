import pytest
import pytest_asyncio
import os
import uuid
import subprocess
from unittest.mock import patch, MagicMock

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool
from aegis.graph import build_graph
import aegis.agents

DB_URI = os.getenv(
    "DATABASE_URL", "postgresql://postgres:password@localhost:5432/aegis"
)


class MultiTurnMockChatModel:
    def __init__(self, *args, **kwargs):
        self.turn = 0

    async def ainvoke(self, prompt, *args, **kwargs):
        self.turn += 1
        return MagicMock(content="RUN_CMD: python -B seed_repo/check_bug.py")

    def with_structured_output(self, schema, **kwargs):
        class MockRunnable:
            def __init__(self, schema_cls, parent):
                self.schema_cls = schema_cls
                self.parent = parent

            async def ainvoke(self, prompt, *args, **kwargs):
                if self.schema_cls.__name__ == "PlanOutput":
                    return self.schema_cls(plan=[{"step": "1"}])
                if self.schema_cls.__name__ == "CriticDecision":
                    return self.schema_cls(approved=True, feedback="Looks good to me")
                return self.schema_cls()

        return MockRunnable(schema, self)


@pytest.fixture
def mock_multi_turn_llm():
    with patch("aegis.agents.get_llm", return_value=MultiTurnMockChatModel()), \
         patch("aegis.graph.get_llm", return_value=MultiTurnMockChatModel()) as mock:
        yield mock


@pytest_asyncio.fixture
async def checkpointer():
    connection_kwargs = {"autocommit": True, "prepare_threshold": 0}
    pool = AsyncConnectionPool(DB_URI, kwargs=connection_kwargs, open=False)
    await pool.open()
    async with pool:
        checkpointer = AsyncPostgresSaver(pool)
        await checkpointer.setup()
        yield checkpointer


@pytest.mark.asyncio
async def test_flagship_demo_mocked(mock_multi_turn_llm, checkpointer):
    math_lib_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "seed_repo", "math_lib.py")
    )

    # Ensure bug is present
    subprocess.run(["git", "checkout", math_lib_path])

    # We will wrap the real coder_node to simulate it writing the fix on turn 2.
    # Turn 1 leaves the bug in place so the stdlib checker exits non-zero (proven red);
    # turn 2 writes the fix so the checker exits 0 (green). The seed_repo is bind-mounted
    # into the sandbox, so writing on the host is reflected in the container.
    original_coder = aegis.agents.coder_node
    turn_counter = 0

    async def patched_coder(state):
        nonlocal turn_counter
        turn_counter += 1
        if turn_counter == 2:
            # Turn 2: fix the bug so divide() raises ValueError on divide-by-zero.
            with open(math_lib_path, "w") as f:
                f.write(
                    "def add(a, b):\n    return a + b\n\n\n"
                    "def subtract(a, b):\n    return a - b\n\n\n"
                    "def multiply(a, b):\n    return a * b\n\n\n"
                    "def divide(a, b):\n"
                    "    if b == 0:\n"
                    "        raise ValueError('Cannot divide by zero')\n"
                    "    return a / b\n"
                )
        return await original_coder(state)

    with patch("aegis.graph.coder_node", new=patched_coder):
        graph = build_graph(checkpointer=checkpointer, interrupt_before=["synthesizer"])
        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}

        # 1. Run until interrupt
        initial_state = {
            "task": "Fix the division by zero bug",
            "mode": "flagship",
            "budget": 3,
        }
        async for output in graph.astream(initial_state, config=config):
            pass

        # Assert the graph is interrupted
        state = await graph.aget_state(config)
        assert len(state.next) > 0, "Graph should be paused at an interrupt"

        # Turn 1 should have failed, Turn 2 should have passed
        assert turn_counter == 2
        scratchpad = state.values.get("scratchpad", {})
        assert scratchpad.get("sandbox_exit_code") == 0
        assert scratchpad.get("proven_red") is True

        # Assert budget decremented
        assert state.values.get("budget") == 2

        # 2. Resume graph
        async for output in graph.astream(None, config=config):
            pass

        # Assert it reached END and PR was opened
        final_state = await graph.aget_state(config)
        assert len(final_state.next) == 0, "Graph should have finished"
        assert "pr_response" in final_state.values.get("scratchpad", {})

    # Revert files
    test_math_lib_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "seed_repo", "test_math_lib.py")
    )
    subprocess.run(["git", "checkout", math_lib_path])
    subprocess.run(["git", "checkout", test_math_lib_path])
