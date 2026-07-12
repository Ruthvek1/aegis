import contextvars
from typing import Optional

# Ephemeral ContextVar for holding BYO keys during a request lifecycle.
# This ensures it never enters the database or persistent state.
current_api_key: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_api_key", default=None
)
