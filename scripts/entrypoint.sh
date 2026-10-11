#!/bin/sh
set -e

PORT="${PORT:-8000}"

echo "=========================================="
echo "Starting VaneLoop Cloud Web Service..."
echo "=========================================="

# 1. Fetch NASA C-MAPSS dataset if missing
if [ ! -f "data/raw/train_FD001.txt" ]; then
    echo "Downloading NASA C-MAPSS dataset..."
    uv run python scripts/fetch_data.py || true
fi

# 2. Run migrations (creates tables/keyspaces if needed)
echo "Running migrations..."
uv run python -m api.app.cli migrate || true

# 3. Start live telemetry replayer loop in background
echo "Starting background replayer loop on all datasets..."
uv run python -m replayer.loop --dataset all &

# 4. Start FastAPI server
echo "Starting FastAPI server on port $PORT..."
exec uv run uvicorn api.app.main:app --host 0.0.0.0 --port "$PORT"
