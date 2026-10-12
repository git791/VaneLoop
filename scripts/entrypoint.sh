#!/bin/sh
set -e

PORT="${PORT:-8000}"

echo "=========================================="
echo "Starting VaneLoop Cloud Web Service..."
echo "=========================================="

# 1. Start local in-memory Redis instance (hard-capped at 48MB RAM with LRU eviction)
# This completely eliminates cloud Redis quotas (like Upstash 500k commands/mo) at 0 cost!
echo "Starting local Redis instance (port 6379)..."
redis-server --daemonize yes --maxmemory 48mb --maxmemory-policy allkeys-lru --port 6379 || true

# Direct internal components to local zero-quota Redis
export REDIS_URL="redis://127.0.0.1:6379"

# 2. Run dataset sync, migrations, and background replayer loop concurrently
(
    echo "Checking C-MAPSS dataset..."
    uv run python scripts/fetch_data.py || true

    echo "Running schema migrations..."
    uv run python -m api.app.cli migrate || true

    echo "Starting background replayer loop (paced at 2000ms)..."
    export REPLAY_TICK_MS=2000
    uv run python -m replayer.loop --dataset FD001 &

    echo "Ingesting historical sensor telemetry for FD001 into Astra DB..."
    uv run python -m api.app.cli ingest --dataset FD001 || true
) &

# 3. Start FastAPI server immediately in foreground
echo "Starting FastAPI server on port $PORT..."
exec uv run uvicorn api.app.main:app --host 0.0.0.0 --port "$PORT"
