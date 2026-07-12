FROM python:3.11-slim

WORKDIR /app

# Install uv and docker client (if needed)
RUN apt-get update && apt-get install -y curl docker.io && \
    curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="/usr/local/bin" sh && \
    apt-get clean

COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

COPY aegis/ ./aegis/

CMD ["uv", "run", "uvicorn", "aegis.server:app", "--host", "0.0.0.0", "--port", "8000"]
