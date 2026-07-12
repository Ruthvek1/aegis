import asyncio
import json
import uuid
import os
from typing import Dict, Any, Optional
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from datetime import datetime

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
    
    try:
        # Give it a short timeout so it doesn't hang for 30s if DB is offline
        _pool = AsyncConnectionPool(
            db_uri, kwargs={"autocommit": True, "prepare_threshold": 0}, open=False, timeout=3.0
        )
        await _pool.open()
        _checkpointer = AsyncPostgresSaver(_pool)  # type: ignore
        await _checkpointer.setup()

        mm = MemoryManager(db_uri)
        await mm.open()
        await mm._ensure_ready()
        import aegis.memory
        aegis.memory._global_mm = mm
        print("✅ Database connected successfully.")
    except Exception as e:
        print(f"⚠️ Warning: Database connection failed on startup: {e}")
        print("⚠️ AEGIS is running in degraded mode (In-Memory Checkpointer & No DB persistence).")
        
        from langgraph.checkpoint.memory import MemorySaver
        _checkpointer = MemorySaver()
        
        class DummyMemoryManager:
            async def open(self): pass
            async def close(self): pass
            async def record_event(self, *args, **kwargs): pass
            async def search_events(self, *args, **kwargs): return []
            
        import aegis.memory
        aegis.memory._global_mm = DummyMemoryManager()

    yield

    if _pool:
        await _pool.close()

    if aegis.memory._global_mm:
        await aegis.memory._global_mm.close()


app = FastAPI(title="AEGIS Control Plane", lifespan=lifespan)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global memory state
_pool: Optional[AsyncConnectionPool] = None
_checkpointer: Optional[AsyncPostgresSaver] = None
_pending_runs: Dict[str, dict] = {}
_active_tasks: Dict[str, asyncio.Task] = {}
_daily_spend_usd: Dict[str, float] = {}

class StartRunRequest(BaseModel):
    task: str
    mode: str = "replay"
    api_key: Optional[str] = None
    captcha_token: Optional[str] = None
    budget: int = 10
    max_cost_usd: float = 0.5
    power_mode: str = "low"


class ResumeRunRequest(BaseModel):
    action: str = "continue"


@app.post("/runs")
@limiter.limit("5/minute")
async def start_run(request: Request, body: StartRunRequest):
    run_id = str(uuid.uuid4())
    
    mode = body.mode
    today = datetime.now().date().isoformat()
    if today not in _daily_spend_usd:
        _daily_spend_usd[today] = 0.0

    if mode == "demo":
        if not body.captcha_token or len(body.captcha_token) < 5:
            raise HTTPException(status_code=400, detail="Invalid CAPTCHA token")
        if _daily_spend_usd[today] >= 0.50:
            mode = "replay" # Kill-switch fallback

    _pending_runs[run_id] = {
        "task": body.task,
        "mode": mode,
        "api_key": body.api_key,
        "budget": body.budget,
        "max_cost_usd": body.max_cost_usd,
        "config": {
            "configurable": {
                "thread_id": run_id,
                "max_budget": body.budget,
                "max_cost_usd": body.max_cost_usd,
                "power_mode": body.power_mode
            }
        },
        "type": "start",
    }
    return {"run_id": run_id, "mode": mode}


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
    # The event log has run events, but it's easier to list unique thread_ids
    if not mm or not hasattr(mm, 'pool'):
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
    if not mm or not hasattr(mm, 'pool'):
        return {"run_id": run_id, "events": []}

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


async def _run_graph_stream(run_id: str, graph, config: dict, input_data: Any, mode: str = "flagship"):
    try:
        if mode == "replay":
            import os
            base_dir = os.path.dirname(__file__)
            run_file = os.path.join(base_dir, "..", "curated_runs", "run1.json")
            if os.path.exists(run_file):
                with open(run_file, "r") as f:
                    events = json.load(f)
                for ev in events:
                    yield f"data: {json.dumps(ev)}\n\n"
                    await asyncio.sleep(0.05)
            return

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
                    "chatter",
                    "simple_coder",
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
                    "chatter",
                    "simple_coder",
                ]:
                    mapped_event = {"type": "agent_end", "agent": name}
                    # Check for handoff
                    output = event["data"].get("output")
                    if output and isinstance(output, dict):
                        if "next" in output:
                            yield f"data: {json.dumps({'type': 'handoff', 'next': output['next']})}\n\n"
                        if "final_result" in output:
                            yield f"data: {json.dumps({'type': 'final_result', 'content': output['final_result']})}\n\n"
                    # Emit usage if any cost accumulated
                    if (
                        output
                        and isinstance(output, dict)
                        and "current_cost_usd" in output
                    ):
                        cost = output["current_cost_usd"]
                        from datetime import datetime
                        today = datetime.now().date().isoformat()
                        if today in _daily_spend_usd:
                            _daily_spend_usd[today] += cost
                        yield f"data: {json.dumps({'type': 'usage', 'cost_usd': cost})}\n\n"

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
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'error': f'Internal Error: {str(e)}'})}\n\n"
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
    if "config" in pending:
        config = pending["config"]
    else:
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

        from aegis.api_key import current_api_key
        api_key = pending.get("api_key")
        if api_key:
            current_api_key.set(api_key)

        mode = pending.get("mode", "flagship")
        async for chunk in _run_graph_stream(run_id, graph, config, input_data, mode):
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
