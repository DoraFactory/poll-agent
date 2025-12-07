FROM python:3.10-slim

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Allow slower networks during dependency downloads
ENV UV_HTTP_TIMEOUT=120

# Copy project files
COPY pyproject.toml uv.lock ./
COPY src/ ./src/

# Install dependencies
RUN uv sync --frozen --no-dev

# Run the agent
CMD ["uv", "run", "python", "-m", "poll_agent.main"]
