# api/Dockerfile
FROM python:3.13-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

COPY api/ ./api/
COPY infra/ ./infra/

CMD ["uv", "run", "uvicorn", "api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
