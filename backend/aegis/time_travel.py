import uuid
from typing import Any


async def fork_from_step(
    graph, thread_id: str, step_index: int, new_state: dict[str, Any]
) -> dict:
    """
    Rewinds a LangGraph execution to a specific step index in the history,
    injects edited state, and forks a new thread of execution from there.

    Returns the config for the new thread.
    """
    config = {"configurable": {"thread_id": thread_id}}

    # Retrieve state history (from newest to oldest)
    history = []
    async for state_snapshot in graph.aget_state_history(config):
        history.append(state_snapshot)

    # Reverse to get chronological order
    history.reverse()

    if step_index < 0 or step_index >= len(history):
        raise ValueError(
            f"step_index {step_index} out of bounds for history length {len(history)}"
        )

    target_snapshot = history[step_index]
    target_config = target_snapshot.config

    # Fork into a new thread
    new_thread_id = str(uuid.uuid4())
    new_config = {"configurable": {"thread_id": new_thread_id}}

    # We update state using the specific checkpoint ID of the target snapshot
    # but we supply the new thread_id config so it forks!
    fork_config = {
        "configurable": {
            "thread_id": new_thread_id,
            "checkpoint_id": target_config["configurable"]["checkpoint_id"],
        }
    }

    # Apply the new state
    await graph.aupdate_state(fork_config, new_state)

    return new_config
