import pytest
import os
import uuid
import subprocess
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from aegis.graph import build_graph

DB_URI = os.getenv(
    "DATABASE_URL", "postgresql://postgres:password@localhost:5432/aegis"
)


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("LIVE_API"), reason="LIVE_API not set")
async def test_flagship_demo_live():
    """
    Opt-in live end-to-end test.
    This will actually use the real ChatAnthropic LLM to fix the seed issue.
    """
    connection_kwargs = {"autocommit": True, "prepare_threshold": 0}
    pool = AsyncConnectionPool(DB_URI, kwargs=connection_kwargs, open=False)
    await pool.open()

    async with pool:
        checkpointer = AsyncPostgresSaver(pool)
        await checkpointer.setup()

        math_lib_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "seed_repo", "math_lib.py")
        )

        # Reset seed repo
        subprocess.run(["git", "checkout", math_lib_path])

        graph = build_graph(checkpointer=checkpointer)
        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}

        # 1. Run until interrupt
        initial_state = {
            "task": "Fix the division by zero bug in math_lib.py",
            "mode": "flagship",
            "budget": 3,
        }
        async for output in graph.astream(initial_state, config=config):
            pass

        state = await graph.aget_state(config)
        assert len(state.next) > 0, "Graph should be paused at an interrupt"

        # 2. Resume graph
        async for output in graph.astream(None, config=config):
            pass

        final_state = await graph.aget_state(config)
        assert len(final_state.next) == 0, "Graph should have finished"

        # Revert file
        subprocess.run(["git", "checkout", math_lib_path])
