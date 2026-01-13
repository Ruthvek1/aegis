import asyncio
import json
import uuid
import os
from typing import Dict, Any, Optional
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from aegis.graph import build_graph
from aegis.memory import MemoryManager
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool, _checkpointer
    db_uri = os.getenv(
        "DATABASE_URL", "postgresql://postgres:password@localhost:5432/aegis"
    )
    _pool = AsyncConnectionPool(
        db_uri, kwargs={"autocommit": True, "prepare_threshold": 0}, open=False
    )
    await _pool.open()
    _checkpointer = AsyncPostgresSaver(_pool)  # type: ignore
    await _checkpointer.setup()

    mm = MemoryManager(db_uri)
    await mm.open()
    await mm._ensure_ready()
    import aegis.memory

    aegis.memory._global_mm = mm

    yield

    if _pool:
        await _pool.close()

    if aegis.memory._global_mm:
        await aegis.memory._global_mm.close()


app = FastAPI(title="AEGIS Control Plane", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global memory state
_pool: Optional[AsyncConnectionPool] = None
_checkpointer: Optional[AsyncPostgresSaver] = None
_pending_runs: Dict[str, dict] = {}
_active_tasks: Dict[str, asyncio.Task] = {}


class StartRunRequest(BaseModel):
    task: str
    mode: str = "flagship"
    budget: int = 10
    max_cost_usd: float = 0.5


class ResumeRunRequest(BaseModel):
    action: str = "continue"


@app.post("/runs")
async def start_run(request: StartRunRequest):
    run_id = str(uuid.uuid4())
    _pending_runs[run_id] = {
        "task": request.task,
        "mode": request.mode,
        "budget": request.budget,
        "max_cost_usd": request.max_cost_usd,
        "type": "start",
    }
    return {"run_id": run_id}


@app.post("/runs/{run_id}/resume")
async def resume_run(run_id: str, request: ResumeRunRequest):
    _pending_runs[run_id] = {"type": "resume", "action": request.action}
    return {"run_id": run_id, "status": "pending_resume"}


@app.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str):
    if run_id in _active_tasks:
        task = _active_tasks[run_id]
        task.cancel()
        return {"status": "cancelled"}
    return {"status": "not_found"}


@app.get("/runs")
async def list_runs():
    import aegis.memory

    mm = aegis.memory._global_mm
    # The event log has run events, but it's easier to just list unique thread_ids
    if not mm:
        return {"runs": []}

    async with mm.pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT DISTINCT thread_id FROM event_log ORDER BY thread_id DESC LIMIT 100"
            )
            rows = await cur.fetchall()
    return {"runs": [r[0] for r in rows]}


@app.get("/runs/{run_id}/transcript")
async def get_transcript(run_id: str):
    import aegis.memory

    mm = aegis.memory._global_mm
    if not mm:
        raise HTTPException(status_code=500, detail="Database not ready")

    async with mm.pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT node_name, event_data, timestamp FROM event_log WHERE thread_id = %s ORDER BY timestamp ASC",
                (run_id,),
            )
            rows = await cur.fetchall()

    return {
        "run_id": run_id,
        "events": [{"node": r[0], "data": r[1], "timestamp": r[2]} for r in rows],
    }


async def _run_graph_stream(run_id: str, graph, config: dict, input_data: Any):
    try:
        async for event in graph.astream_events(
            input_data, version="v2", config=config
        ):
            mapped_event = None
            event_type = event["event"]
            name = event["name"]

            if event_type == "on_chain_start":
                if name in [
                    "supervisor",
                    "planner",
                    "coder",
                    "critic",
                    "researcher",
                    "synthesizer",
                ]:
                    mapped_event = {"type": "agent_start", "agent": name}

            elif event_type == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if (
                    chunk
                    and hasattr(chunk, "content")
                    and isinstance(chunk.content, str)
                ):
                    mapped_event = {"type": "token", "content": chunk.content}

            elif event_type == "on_tool_start":
                mapped_event = {
                    "type": "tool_call",
                    "tool": name,
                    "input": event["data"].get("input"),
                }

            elif event_type == "on_tool_end":
                mapped_event = {
                    "type": "tool_result",
                    "tool": name,
                    "output": event["data"].get("output"),
                }

            elif event_type == "on_chain_end":
                if name in [
                    "supervisor",
                    "planner",
                    "coder",
                    "critic",
                    "researcher",
                    "synthesizer",
                ]:
                    mapped_event = {"type": "agent_end", "agent": name}
                    # Check for handoff
                    output = event["data"].get("output")
                    if output and isinstance(output, dict) and "next" in output:
                        yield f"data: {json.dumps({'type': 'handoff', 'next': output['next']})}\n\n"
                    # Emit usage if any cost accumulated
                    if (
                        output
                        and isinstance(output, dict)
                        and "current_cost_usd" in output
                    ):
                        yield f"data: {json.dumps({'type': 'usage', 'cost_usd': output['current_cost_usd']})}\n\n"

            elif event_type == "on_chain_error":
                mapped_event = {
                    "type": "error",
                    "error": str(event["data"].get("error")),
                }

            if mapped_event:
                yield f"data: {json.dumps(mapped_event)}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    except asyncio.CancelledError:
        yield f"data: {json.dumps({'type': 'error', 'error': 'Run cancelled due to client disconnect'})}\n\n"
        raise
    finally:
        if run_id in _active_tasks:
            del _active_tasks[run_id]


@app.get("/runs/{run_id}/stream")
async def stream_run(run_id: str, request: Request):
    if run_id not in _pending_runs and run_id not in _active_tasks:
        # It's possible the client wants to stream an existing interrupted run.
        # But we require a resume POST first to prime the pending run.
        raise HTTPException(status_code=404, detail="Run not pending")

    pending = _pending_runs.pop(run_id, None)
    if not pending:
        raise HTTPException(status_code=400, detail="Run already started")

    graph = build_graph(checkpointer=_checkpointer, interrupt_before=["synthesizer"])
    config = {"configurable": {"thread_id": run_id}}

    if pending["type"] == "start":
        input_data: Any = {
            "task": pending["task"],
            "mode": pending["mode"],
            "budget": pending["budget"],
            "max_cost_usd": pending["max_cost_usd"],
        }
    else:
        from langgraph.types import Command

        input_data = Command(resume=pending["action"])  # type: ignore

    async def stream_generator():
        # Register the active task for cancellation
        current_task = asyncio.current_task()
        if current_task:
            _active_tasks[run_id] = current_task

        async for chunk in _run_graph_stream(run_id, graph, config, input_data):
            # Check if the client disconnected
            if await request.is_disconnected():
                if current_task:
                    current_task.cancel()
                break
            yield chunk

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
