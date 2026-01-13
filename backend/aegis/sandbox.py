import docker
import time
from typing import Tuple
from typing import Dict, Any, Optional


def get_docker_client() -> docker.DockerClient:
    return docker.from_env()


def run_in_sandbox(
    image: str,
    command: str,
    timeout_sec: int = 5,
    volumes: Optional[Dict[str, Any]] = None,
) -> Tuple[int, str]:
    """
    Runs a command in a highly locked down Docker container.
    Enforces a wall-clock timeout from the host side, ensuring the container
    is killed and removed even if it hangs.
    """
    client = get_docker_client()

    container = None
    try:
        # Run detached to manage timeout from host
        kwargs: Dict[str, Any] = {
            "image": image,
            "command": command,
            "detach": True,
            "network_mode": "none",
            "pids_limit": 128,
            "user": "1000:1000",
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges"],
            "mem_limit": "512m",
            "memswap_limit": "512m",
            "read_only": True,
            "tmpfs": {"/workspace": "rw,noexec,nosuid,size=64m"},
            "working_dir": "/workspace",
        }
        if volumes:
            kwargs["volumes"] = volumes

        container = client.containers.run(**kwargs)  # type: ignore

        start_time = time.time()
        while True:
            # Check if container exited
            container.reload()
            if container.status == "exited":
                break

            if time.time() - start_time > timeout_sec:
                # Timeout hit
                return -1, f"Execution timed out after {timeout_sec} seconds"

            time.sleep(0.1)

        result = container.wait()
        exit_code = result.get("StatusCode", 1)
        logs = container.logs().decode("utf-8")
        return exit_code, logs

    except docker.errors.ContainerError as e:
        stderr_val = e.stderr
        if isinstance(stderr_val, bytes):
            stderr_val = stderr_val.decode("utf-8")
        return e.exit_status, stderr_val if stderr_val else str(e)
    except Exception as e:
        return -2, f"Sandbox execution failed: {str(e)}"
    finally:
        if container:
            try:
                container.kill()
            except Exception:
                pass
            try:
                container.remove(force=True)
            except Exception:
                pass
