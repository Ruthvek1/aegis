from mcp.server.fastmcp import FastMCP

mcp = FastMCP("github")


@mcp.tool()
def fetch_issue(repo: str, issue_number: int) -> str:
    """Fetches a GitHub issue's text."""
    # In a real tool, this would hit the GitHub API
    return f"Issue #{issue_number} in {repo}: The divide function raises ZeroDivisionError instead of ValueError when dividing by zero."


@mcp.tool()
def open_pull_request(repo: str, branch: str, title: str, body: str) -> str:
    """Opens a pull request."""
    # In a real tool, this hits the GitHub API
    return f"Successfully opened PR for {repo} on branch {branch}. Title: {title}. Body: {body}"


if __name__ == "__main__":
    mcp.run()
