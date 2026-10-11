#!/bin/sh
set -e

PORT="${PORT:-8000}"

echo "=========================================="
echo "Starting VaneLoop Cloud Web Service..."
echo "=========================================="

# 1. Run dataset download, migration, and background replayer concurrently
# This ensures FastAPI binds to $PORT immediately without blocking on network tasks
(
    echo "Checking C-MAPSS dataset..."
    uv run python scripts/fetch_data.py || true

    echo "Running schema migrations..."
    uv run python -m api.app.cli migrate || true

    echo "Starting background replayer loop on all datasets..."
    uv run python -m replayer.loop --dataset all
) &

# 2. Start FastAPI server immediately in foreground so Render port check succeeds instantly
echo "Starting FastAPI server on port $PORT..."
exec uv run uvicorn api.app.main:app --host 0.0.0.0 --port "$PORT"
