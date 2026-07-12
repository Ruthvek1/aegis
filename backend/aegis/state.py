from typing import TypedDict, Annotated, Any
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


def merge_dicts(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    # Shallow merge for scratchpads
    merged = a.copy()
    merged.update(b)
    return merged


def merge_lists(a: list[Any], b: list[Any]) -> list[Any]:
    return a + b


class AgentState(TypedDict, total=False):
    task: str
    mode: str
    plan: list[dict[str, Any]]
    messages: Annotated[list[BaseMessage], add_messages]
    scratchpad: Annotated[dict[str, Any], merge_dicts]
    tool_results: Annotated[list[dict[str, Any]], merge_lists]
    budget: int
    max_cost_usd: float
    current_cost_usd: float
    next: str
    final_result: str
