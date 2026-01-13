import pytest
import os
from typing import Any

from aegis.tools import ToolRegistry, execute_with_self_correction


@pytest.mark.asyncio
async def test_mcp_client_server_integration():
    """Test the full client -> server -> result round-trip using stdio."""
    # We use the mcp_server.py as the target script
    server_script = os.path.join(
        os.path.dirname(__file__), "..", "aegis", "mcp_server.py"
    )

    registry = ToolRegistry(server_script)

    async with registry.connect() as session:
        # Call the execute_python tool
        args = {"code": "print('hello from sandbox')"}
        output = await registry.execute_tool(session, "execute_python", args)

        assert "Execution successful" in output
        assert "hello from sandbox" in output


class MockLLMNode:
    def __init__(self, responses, should_raise=True):
        self.responses = responses
        self.call_count = 0
        self.should_raise = should_raise

    async def __call__(self, state: dict, last_error: str) -> dict[str, Any]:
        if self.call_count < len(self.responses):
            resp = self.responses[self.call_count]
            self.call_count += 1
            if isinstance(resp, Exception):
                raise resp
            return resp
        if self.should_raise:
            raise Exception("No more mocked responses")
        return {}


@pytest.mark.asyncio
async def test_bad_args_self_correction():
    """Test self-correction: bad args (triggering error) then success on retry."""

    # Mock LLM raises ValueError first, then succeeds
    mock_llm = MockLLMNode(
        [ValueError("Malformed JSON schema"), {"code": "print('success')"}]
    )

    result = await execute_with_self_correction(mock_llm, state={}, max_retries=3)

    assert result == {"code": "print('success')"}
    assert mock_llm.call_count == 2


@pytest.mark.asyncio
async def test_bad_args_bound_exhaustion():
    """Test that it gives up gracefully after N bad calls."""

    # Mock LLM always raises errors
    mock_llm = MockLLMNode(
        [
            ValueError("Malformed JSON 1"),
            ValueError("Malformed JSON 2"),
            ValueError("Malformed JSON 3"),
        ]
    )

    with pytest.raises(Exception, match="Bound exhausted: Failed after 3 attempts"):
        await execute_with_self_correction(mock_llm, state={}, max_retries=3)

    assert mock_llm.call_count == 3
