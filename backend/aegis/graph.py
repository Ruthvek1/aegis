import contextlib

from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from aegis.state import AgentState
from aegis.agents import (
    planner_node,
    coder_node,
    critic_node,
    researcher_node,
    synthesizer_node,
)


def supervisor_node(state: AgentState) -> dict:
    # Router logic. In a full dynamic system, LLM decides.
    # For the FLAGSHIP flow (fix issue -> PR), the flow is linear with a loop:
    # START -> Planner -> Researcher -> Coder -> Critic -> (veto? back to Coder) -> Synthesizer -> END

    plan = state.get("plan", [])
    scratchpad = state.get("scratchpad", {})
    budget = state.get("budget", 3)  # default budget of 3 loops
    max_cost = state.get("max_cost_usd", 1.0)
    current_cost = state.get("current_cost_usd", 0.0)

    # Prompt injection guardrail
    if scratchpad.get("prompt_injection_detected"):
        return {"next": "END", "budget": 0}

    # Cost Governor
    if current_cost >= max_cost:
        scratchpad["governor_forced_synthesis"] = True
        return {"next": "synthesizer", "budget": 0, "scratchpad": scratchpad}

    if not plan:
        return {"next": "planner", "budget": budget}

    if "research_done" not in scratchpad:
        scratchpad["research_done"] = True
        return {"next": "researcher", "budget": budget, "scratchpad": scratchpad}

    if "coder_output" not in scratchpad:
        return {"next": "coder", "budget": budget}

    # We have coder output. Has it been reviewed?
    if "critic_approved" not in scratchpad:
        return {"next": "critic", "budget": budget}

    approved = scratchpad.get("critic_approved")
    if approved:
        # Go to Synthesizer on success.
        # (HitL pause is handled via interrupt_before=["synthesizer"] during compile)
        return {"next": "synthesizer", "budget": budget, "scratchpad": scratchpad}
    else:
        # Vetoed!
        if budget > 1:
            # Clear critic_approved so we know it needs review again after coder runs
            scratchpad.pop("critic_approved", None)
            return {"next": "coder", "budget": budget - 1, "scratchpad": scratchpad}
        else:
            # Budget exhausted
            return {"next": "END", "budget": 0}


def route(state: AgentState) -> str:
    nxt = state.get("next", "END")
    if nxt == "END":
        return END
    return nxt


def build_graph(checkpointer=None, interrupt_before=None):
    workflow = StateGraph(AgentState)

    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("planner", planner_node)
    workflow.add_node("coder", coder_node)
    workflow.add_node("critic", critic_node)
    workflow.add_node("researcher", researcher_node)
    workflow.add_node("synthesizer", synthesizer_node)

    workflow.add_edge(START, "supervisor")

    # Edges from agents always go back to supervisor
    workflow.add_edge("planner", "supervisor")
    workflow.add_edge("coder", "supervisor")
    workflow.add_edge("critic", "supervisor")
    workflow.add_edge("researcher", "supervisor")

    # Synthesizer always terminates the graph
    workflow.add_edge("synthesizer", END)

    # Conditional edges from supervisor to agents or END
    workflow.add_conditional_edges(
        "supervisor",
        route,
        {
            "planner": "planner",
            "coder": "coder",
            "critic": "critic",
            "researcher": "researcher",
            "synthesizer": "synthesizer",
            END: END,
        },
    )

    return workflow.compile(
        checkpointer=checkpointer, interrupt_before=interrupt_before
    )


@contextlib.asynccontextmanager
async def get_checkpointer(db_uri: str):
    """Real graph setup code to yield an AsyncPostgresSaver with correct connection kwargs."""
    connection_kwargs = {"autocommit": True, "prepare_threshold": 0}
    pool = AsyncConnectionPool(db_uri, kwargs=connection_kwargs, open=False)
    await pool.open()
    try:
        async with pool:
            checkpointer = AsyncPostgresSaver(pool)  # type: ignore
            await checkpointer.setup()
            yield checkpointer
    finally:
        pass
