import pytest
import pytest_asyncio
import uuid
import os
from unittest.mock import patch, MagicMock
from aegis.memory import MemoryManager

DB_URI = os.getenv(
    "DATABASE_URL", "postgresql://postgres:password@localhost:5432/aegis"
)


@pytest_asyncio.fixture
async def memory_manager():
    # Setup tables
    mm = MemoryManager(DB_URI)
    await mm.open()
    await mm.setup_memory_tables()

    # Clear tables for clean test
    async with mm.pool.connection() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM episodic_memory")
            await conn.execute("DELETE FROM procedural_memory")
            await conn.execute("DELETE FROM semantic_memory")

    yield mm
    await mm.close()


@pytest.mark.asyncio
async def test_episodic_memory_ranking(memory_manager):
    # Insert Task A
    await memory_manager.save_episodic(
        "Refactor the authentication logic", [{"step": "refactor auth"}], "Success"
    )
    # Insert Decoy Task
    await memory_manager.save_episodic(
        "Update the README file with new typos", [{"step": "fix typo"}], "Success"
    )

    # Retrieve with similar Task B
    results = await memory_manager.retrieve_episodic("Refactor auth logic", limit=2)

    assert len(results) == 2
    # Task A should rank higher than decoy
    assert results[0]["task"] == "Refactor the authentication logic"
    assert results[1]["task"] == "Update the README file with new typos"
    assert results[0]["similarity"] > results[1]["similarity"]


@pytest.mark.asyncio
async def test_procedural_skill_loop(memory_manager):
    # Store a skill
    await memory_manager.save_procedural(
        "git config tool",
        "Set git username",
        [{"tool": "execute_python", "args": "git config"}],
        True,
    )

    # Retrieve
    results = await memory_manager.retrieve_procedural(
        "I need to configure git", limit=1
    )

    assert len(results) == 1
    assert results[0]["name"] == "git config tool"


@pytest.mark.asyncio
async def test_semantic_extraction(memory_manager):
    await memory_manager.save_semantic("Node", "Python", "Depends on", "Context string")

    results = await memory_manager.query_semantic("Node")
    assert len(results) == 1
    assert results[0]["target"] == "Python"
    assert results[0]["relation"] == "Depends on"


@pytest.mark.asyncio
async def test_transactional_integrity(memory_manager):
    # Force a rollback during semantic insert by raising an exception mid-transaction
    class ForcedRollbackError(Exception):
        pass

    try:
        async with memory_manager.pool.connection() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO semantic_memory (id, entity_source, entity_target, relationship, context) VALUES (%s, %s, %s, %s, %s)",
                    (uuid.uuid4(), "A", "B", "Rel", "Ctx"),
                )
                raise ForcedRollbackError("Simulated failure")
    except ForcedRollbackError:
        pass

    # Assert zero half-written rows
    results = await memory_manager.query_semantic("A")
    assert len(results) == 0


@pytest.mark.asyncio
async def test_graph_memory_integration(memory_manager):
    from aegis.agents import synthesizer_node, planner_node

    # Patch get_memory_manager to use our test mm
    with patch("aegis.agents.get_memory_manager", return_value=memory_manager):
        # 1. Synthesizer stores a successful run
        state = {
            "task": "Test procedural integration",
            "plan": [{"step": "test"}],
            "scratchpad": {"coder_output": "Success"},
        }
        await synthesizer_node(state)

        # Verify it wrote to DB
        skills = await memory_manager.retrieve_procedural("Test procedural integration")
        assert len(skills) > 0

        episodes = await memory_manager.retrieve_episodic("Test procedural integration")
        assert len(episodes) > 0

        # 2. Planner retrieves it on next run
        # We mock the LLM inside planner_node to capture the prompt it receives
        from aegis.agents import PlanOutput

        class CaptureMock:
            async def ainvoke(self, prompt, *args, **kwargs):
                self.prompt = prompt
                return PlanOutput(plan=[{"step": "mocked", "action": "mocked"}])

        capture_mock = CaptureMock()
        with patch("aegis.agents.get_llm") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.with_structured_output.return_value = capture_mock
            mock_get_llm.return_value = mock_llm

            await planner_node({"task": "Test procedural integration"})

            # Assert the prompt contained the episodic and procedural context
            assert "Episodic:" in capture_mock.prompt
            assert "Skills:" in capture_mock.prompt
            assert "Test procedural integration" in capture_mock.prompt
