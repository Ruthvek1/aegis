import pytest
import docker
from aegis.sandbox import run_in_sandbox
from aegis.mcp_server import SANDBOX_IMAGE


def test_docker_available():
    """Assert Docker is available and fail loudly if it isn't, so we never get a false green."""
    try:
        client = docker.from_env()
        client.ping()
    except Exception as e:
        pytest.fail(f"Docker is required for these tests but is not available: {e}")


def test_sandbox_network_isolation():
    """Test that the sandbox cannot reach the internet."""
    # Attempt to fetch a URL
    code = (
        "import urllib.request\n"
        "try:\n"
        "    urllib.request.urlopen('http://example.com', timeout=2)\n"
        "except Exception as e:\n"
        "    print('NETWORK_ERROR:', type(e).__name__)\n"
    )
    import base64

    encoded = base64.b64encode(code.encode("utf-8")).decode("utf-8")
    cmd = f"python -c \"import base64; exec(base64.b64decode('{encoded}').decode('utf-8'))\""

    exit_code, logs = run_in_sandbox(SANDBOX_IMAGE, cmd, timeout_sec=10)

    assert exit_code == 0
    assert "NETWORK_ERROR: URLError" in logs


def test_sandbox_fork_bomb():
    """Test that the sandbox restricts PIDs and survives a fork bomb without hanging the host."""
    code = (
        "import os\n"
        "while True:\n"
        "    try:\n"
        "        os.fork()\n"
        "    except OSError:\n"
        "        print('PIDS_EXHAUSTED')\n"
        "        break\n"
    )
    import base64

    encoded = base64.b64encode(code.encode("utf-8")).decode("utf-8")
    cmd = f"python -c \"import base64; exec(base64.b64decode('{encoded}').decode('utf-8'))\""

    exit_code, logs = run_in_sandbox(SANDBOX_IMAGE, cmd, timeout_sec=5)

    # It should hit the PID limit quickly and print PIDS_EXHAUSTED
    assert "PIDS_EXHAUSTED" in logs
