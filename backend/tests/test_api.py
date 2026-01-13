import pytest
import pytest_asyncio
import json
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, MagicMock

from aegis.server import app, _pending_runs, _active_tasks

# We mock out the actual graph and DB in the tests.


@pytest_asyncio.fixture
async def client():
    # Use ASGITransport for testing FastAPI app without running a server
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_start_run(client):
    response = await client.post("/runs", json={"task": "test task"})
    assert response.status_code == 200
    data = response.json()
    assert "run_id" in data
    run_id = data["run_id"]

    assert run_id in _pending_runs
    assert _pending_runs[run_id]["task"] == "test task"
    assert _pending_runs[run_id]["type"] == "start"


@pytest.mark.asyncio
async def test_resume_run(client):
    response = await client.post("/runs/test_id/resume", json={"action": "continue"})
    assert response.status_code == 200
    assert "test_id" in _pending_runs
    assert _pending_runs["test_id"]["type"] == "resume"
    assert _pending_runs["test_id"]["action"] == "continue"


@pytest.mark.asyncio
async def test_cancel_run(client):
    mock_task = MagicMock()
    _active_tasks["test_cancel_id"] = mock_task

    response = await client.post("/runs/test_cancel_id/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    mock_task.cancel.assert_called_once()

    _active_tasks.pop("test_cancel_id", None)


@pytest.mark.asyncio
async def test_cors_headers(client):
    # Test allowed origin
    response = await client.options(
        "/runs",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


@pytest.mark.asyncio
async def test_stream_run(client):
    # This tests the SSE streaming logic by mocking the graph
    run_id = "test_stream_id"
    _pending_runs[run_id] = {
        "task": "test task",
        "mode": "flagship",
        "budget": 10,
        "max_cost_usd": 0.5,
        "type": "start",
    }

    class MockGraph:
        async def astream_events(self, *args, **kwargs):
            yield {"event": "on_chain_start", "name": "planner", "data": {}}
            yield {
                "event": "on_chat_model_stream",
                "name": "llm",
                "data": {"chunk": MagicMock(content="token1")},
            }
            yield {
                "event": "on_chat_model_stream",
                "name": "llm",
                "data": {"chunk": MagicMock(content="token2")},
            }
            yield {
                "event": "on_chain_end",
                "name": "planner",
                "data": {"output": {"next": "coder", "current_cost_usd": 0.01}},
            }

    with patch("aegis.server.build_graph", return_value=MockGraph()):
        async with client.stream("GET", f"/runs/{run_id}/stream") as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            assert response.headers["cache-control"] == "no-cache"

            content = await response.aread()
            content_str = content.decode("utf-8")

            lines = [line for line in content_str.split("\n\n") if line.strip()]
            assert len(lines) == 7

            assert json.loads(lines[0][6:])["type"] == "agent_start"
            assert json.loads(lines[0][6:])["agent"] == "planner"

            assert json.loads(lines[1][6:])["type"] == "token"
            assert json.loads(lines[1][6:])["content"] == "token1"

            assert json.loads(lines[2][6:])["type"] == "token"
            assert json.loads(lines[2][6:])["content"] == "token2"

            assert json.loads(lines[3][6:])["type"] == "handoff"
            assert json.loads(lines[3][6:])["next"] == "coder"

            assert json.loads(lines[4][6:])["type"] == "usage"
            assert json.loads(lines[4][6:])["cost_usd"] == 0.01

            assert json.loads(lines[5][6:])["type"] == "agent_end"
            assert json.loads(lines[5][6:])["agent"] == "planner"

            assert json.loads(lines[6][6:])["type"] == "done"
