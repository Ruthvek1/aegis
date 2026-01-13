import time
from typing import Any
import os
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession
import contextlib


class ToolCallError(Exception):
    pass


class ToolRegistry:
    def __init__(self, server_script: str):
        env = os.environ.copy()
        env["PYTHONPATH"] = os.path.dirname(os.path.dirname(server_script))
        self.server_params = StdioServerParameters(
            command="python", args=[server_script], env=env
        )

    @contextlib.asynccontextmanager
    async def connect(self):
        async with stdio_client(self.server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session

    async def execute_tool(
        self, session: ClientSession, name: str, args: dict[str, Any]
    ) -> str:
        # 1. Validate inputs (In a real system, we'd check against session.list_tools() schema)
        # We will do a basic try-catch for MCP execution
        start_time = time.time()
        try:
            result = await session.call_tool(name, arguments=args)

            # The MCP result is usually a CallToolResult with content blocks
            if result.isError:
                raise ToolCallError(f"Tool execution returned error: {result.content}")

            output = "\n".join(
                block.text for block in result.content if block.type == "text"
            )

            # Mock Cost logging (observability will be Phase 5)
            duration = time.time() - start_time
            print(
                f"[LOG] Tool {name} executed in {duration:.2f}s | Cost: $0.00 | Tokens: 0"
            )

            return output
        except Exception as e:
            # Mock Cost logging on error
            duration = time.time() - start_time
            print(
                f"[LOG] Tool {name} failed in {duration:.2f}s | Cost: $0.00 | Tokens: 0"
            )
            raise ToolCallError(f"Tool '{name}' failed: {str(e)}")


async def execute_with_self_correction(
    llm_node_func, state: dict, max_retries: int = 3
) -> dict:
    """
    Executes an LLM node that is expected to return tool arguments.
    If the arguments are bad or tool fails, feeds the error back to the LLM up to max_retries.
    """
    retries = 0
    last_error = None

    while retries < max_retries:
        try:
            # Invoke the LLM to get args (the mock LLM or real one)
            # For simplicity in this bounded test, we assume llm_node_func yields the args or raises
            args = await llm_node_func(state, last_error)

            # If we succeed in getting/validating args, return them
            return args
        except Exception as e:
            last_error = str(e)
            retries += 1

    raise Exception(
        f"Bound exhausted: Failed after {max_retries} attempts. Last error: {last_error}"
    )
