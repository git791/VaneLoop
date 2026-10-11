#!/bin/sh
set -e

PORT="${PORT:-8000}"

echo "=========================================="
echo "Starting VaneLoop Cloud Web Service..."
echo "=========================================="

# 1. Run dataset download, migration, ingestion, and background replayer concurrently
(
    echo "Checking C-MAPSS dataset..."
    uv run python scripts/fetch_data.py || true

    echo "Running schema migrations..."
    uv run python -m api.app.cli migrate || true

    echo "Starting background replayer loop on all datasets..."
    uv run python -m replayer.loop --dataset all &

    echo "Ingesting historical sensor telemetry for FD001..."
    uv run python -m api.app.cli ingest --dataset FD001 || true

    echo "Ingesting remaining datasets in background..."
    uv run python -m api.app.cli ingest --dataset FD002 || true
    uv run python -m api.app.cli ingest --dataset FD003 || true
    uv run python -m api.app.cli ingest --dataset FD004 || true
) &

# 2. Start FastAPI server immediately in foreground so Render port check succeeds instantly
echo "Starting FastAPI server on port $PORT..."
exec uv run uvicorn api.app.main:app --host 0.0.0.0 --port "$PORT"
