import os
import pytest

@pytest.fixture(autouse=True)
def dummy_env_vars():
    os.environ["OPENAI_API_KEY"] = "test-dummy-key"
    yield
    os.environ.pop("OPENAI_API_KEY", None)
