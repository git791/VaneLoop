# api/Dockerfile
FROM python:3.13-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

COPY api/ ./api/
COPY infra/ ./infra/
COPY benchmarks/ ./benchmarks/
COPY replayer/ ./replayer/
COPY scripts/ ./scripts/
COPY ml/ ./ml/

RUN chmod +x ./scripts/entrypoint.sh

CMD ["./scripts/entrypoint.sh"]
