from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
from aegis.sandbox import run_in_sandbox

mcp = FastMCP("aegis-sandbox")

# Define the pinned image as requested: "Pin the sandbox base image by tag/digest"
SANDBOX_IMAGE = "python:3.11-alpine3.19"


class ExecPythonArgs(BaseModel):
    code: str = Field(description="Python code to execute in the sandbox")


@mcp.tool()
def execute_python(code: str) -> str:
    """Executes arbitrary python code safely in a locked down docker container."""
    # We pass the code via command string using python -c
    # Need to escape properly, or better, we can pass it via stdin, but `docker run` doesn't support interactive stdin easily in detach mode.
    # We can encode to base64 and decode inside to avoid escaping issues
    import base64

    encoded_code = base64.b64encode(code.encode("utf-8")).decode("utf-8")

    cmd = f"python -c \"import base64; exec(base64.b64decode('{encoded_code}').decode('utf-8'))\""

    exit_code, logs = run_in_sandbox(image=SANDBOX_IMAGE, command=cmd)

    if exit_code == 0:
        return f"Execution successful.\nLogs:\n{logs}"
    else:
        # We raise a ValueError so that the client wrapper can catch it and self-correct?
        # Or return as string with error indicator. Returning string is better for LLM tools unless we want to throw.
        # MCP usually returns tool results as content blocks. We'll return the string.
        return f"Execution failed with exit code {exit_code}.\nLogs:\n{logs}"


if __name__ == "__main__":
    # Start the stdio server
    mcp.run(transport="stdio")
