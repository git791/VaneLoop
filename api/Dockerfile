FROM python:3.10-slim

WORKDIR /app

# Install uv
RUN pip install uv

# Copy project definition
COPY pyproject.toml .

# Install dependencies using uv
RUN uv sync --no-install-project

# Copy application source
COPY api /app/api

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
