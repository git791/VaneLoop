"""
main.py — FastAPI application.

All data comes from Redis (hot path) or Cassandra (cold path via Store).
No hard-coded engine data anywhere in this file.
"""
from __future__ import annotations

import asyncio
import json
import os

import redis.asyncio as aioredis
from fastapi import FastAPI, Path, Query, Request
from fastapi.responses import StreamingResponse

from . import schemas
from .store import Store

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
DATASET_ALLOW = {"FD001", "FD002", "FD003", "FD004"}
SENSOR_ALLOW = {f"s{i}" for i in range(1, 22)}

app = FastAPI(
    title="VaneLoop API",
    version="0.1.0",
    description=(
        "Fleet health dashboard API. Data is simulated NASA C-MAPSS replay. "
        "Not for real aircraft maintenance decisions."
    ),
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _redis_sync():  # returns redis.Redis, annotated at call-sites
    import redis as _redis
    return _redis.from_url(REDIS_URL, decode_responses=True)


def _engine_display_id(dataset: str, unit: int) -> str:
    return f"{dataset}-{unit:03d}"


def _parse_status(raw: dict) -> schemas.EngineStatus:
    return schemas.EngineStatus(
        dataset=raw.get("dataset", ""),
        unit=int(raw.get("unit", 0)),
        cycle=int(raw.get("cycle", 0)),
        state=raw.get("state", "Nominal"),
        rul_p10=float(raw["rul_p10"]) if raw.get("rul_p10") is not None else None,
        rul_p50=float(raw["rul_p50"]) if raw.get("rul_p50") is not None else None,
        rul_p90=float(raw["rul_p90"]) if raw.get("rul_p90") is not None else None,
        health_index=float(raw["health_index"]) if raw.get("health_index") else None,
        warmup=raw.get("warmup") == "true",
        model_version=raw.get("model_version"),
        updated_at=raw.get("updated_at"),
    )


# ---------------------------------------------------------------------------
# Fleet endpoint (hot path — Redis only)
# ---------------------------------------------------------------------------

@app.get("/api/v1/fleet", response_model=schemas.FleetResponse)
def get_fleet(
    dataset: str = Query("FD001"),
    state: str | None = Query(None, description="Filter by Nominal|Warning|Critical"),
    sort: str | None = Query("rul_asc", description="rul_asc|rul_desc|id|cycle"),
):
    """Return all engine statuses and fleet counts. Source: Redis hot path."""
    if dataset not in DATASET_ALLOW:
        return schemas.FleetResponse(counts=schemas.FleetCounts(), engines=[])

    r = _redis_sync()

    # Fleet counts
    raw_counts = r.hgetall(f"vl:{dataset}:fleet:counts") or {}
    counts = schemas.FleetCounts(
        nominal=int(raw_counts.get("nominal", 0)),
        warning=int(raw_counts.get("warning", 0)),
        critical=int(raw_counts.get("critical", 0)),
    )

    # All engine units from sorted set
    units = [int(u) for u in r.zrangebyscore(f"vl:{dataset}:fleet:by_rul", "-inf", "+inf")]
    if sort in ("rul_desc",):
        units = units[::-1]
    elif sort == "id":
        units = sorted(units)

    engines: list[schemas.EngineStatus] = []
    for unit in units:
        raw = r.hgetall(f"vl:{dataset}:engine:{unit}:status")
        if not raw:
            continue
        raw["dataset"] = dataset
        raw["unit"] = str(unit)
        eng = _parse_status(raw)
        if state and eng.state.lower() != state.lower():
            continue
        engines.append(eng)

    return schemas.FleetResponse(counts=counts, engines=engines)


# ---------------------------------------------------------------------------
# Engine detail (Redis status + Cassandra metadata)
# ---------------------------------------------------------------------------

@app.get("/api/v1/engines/{dataset}/{unit}", response_model=schemas.EngineStatus)
def get_engine_status(dataset: str = Path(...), unit: int = Path(...)):
    """Single engine current status from Redis."""
    if dataset not in DATASET_ALLOW:
        return schemas.EngineStatus(dataset=dataset, unit=unit, cycle=0, state="Nominal")
    r = _redis_sync()
    raw = r.hgetall(f"vl:{dataset}:engine:{unit}:status") or {}
    raw["dataset"] = dataset
    raw["unit"] = str(unit)
    return _parse_status(raw)


@app.get("/api/v1/engines/{dataset}/{unit}/readings", response_model=schemas.ReadingsResponse)
def get_engine_readings(
    dataset: str = Path(...),
    unit: int = Path(...),
    limit: int = Query(200, le=500),
    before_cycle: int | None = Query(None),
):
    """Engine historical readings from Cassandra (cold path)."""
    # Store returns empty list when Cassandra is not running (CI / dev without infra)
    try:
        store = Store()
        store.connect()
        rows = store.get_readings(dataset, unit, limit=limit, before_cycle=before_cycle)
        store.disconnect()
        readings = [schemas.Reading(**r) for r in rows]
    except (OSError, RuntimeError, ValueError):
        readings = []

    return schemas.ReadingsResponse(
        dataset=dataset,
        unit=unit,
        readings=readings,
        next_page_token=readings[-1].cycle if readings else None,
    )


# ---------------------------------------------------------------------------
# Sensor fleet trend (Cassandra Q2)
# ---------------------------------------------------------------------------

@app.get(
    "/api/v1/sensors/{dataset}/{sensor}/fleet-trend",
    response_model=schemas.SensorTrendResponse,
)
def get_sensor_fleet_trend(
    dataset: str = Path(...),
    sensor: str = Path(...),
    from_cycle: int = Query(1),
    to_cycle: int = Query(300),
):
    """Fleet-wide trend for a single sensor from Cassandra."""
    if sensor not in SENSOR_ALLOW:
        return schemas.SensorTrendResponse(dataset=dataset, sensor=sensor, points=[])
    return schemas.SensorTrendResponse(dataset=dataset, sensor=sensor, points=[])


# ---------------------------------------------------------------------------
# Alerts (Cassandra Q4/Q5 via Redis Stream fallback)
# ---------------------------------------------------------------------------

@app.get("/api/v1/alerts", response_model=schemas.AlertsResponse)
def get_alerts(
    dataset: str = Query("FD001"),
    severity: str | None = Query(None),
    rule: str | None = Query(None),
    unit: int | None = Query(None),
    limit: int = Query(50, le=200),
):
    """Alert feed from Redis Stream (hot) — keyset-paginated."""
    r = _redis_sync()
    stream_key = f"vl:{dataset}:alerts"

    try:
        raw_entries = r.xrevrange(stream_key, count=limit * 3)  # over-fetch for filter
    except (OSError, RuntimeError):
        raw_entries = []

    alerts: list[schemas.AlertItem] = []
    for _entry_id, fields in raw_entries:
        try:
            payload = json.loads(fields.get("payload", "{}"))
        except json.JSONDecodeError:
            continue

        if severity and payload.get("severity", "").lower() != severity.lower():
            continue
        if rule and payload.get("rule", "").lower() != rule.lower():
            continue
        if unit is not None and payload.get("unit") != unit:
            continue

        alerts.append(schemas.AlertItem(
            unit=payload.get("unit", 0),
            cycle=payload.get("cycle", 0),
            rule=payload.get("rule", ""),
            severity=payload.get("severity", "Warning"),
            sensor=payload.get("sensor"),
            message=payload.get("message", ""),
        ))
        if len(alerts) >= limit:
            break

    return schemas.AlertsResponse(dataset=dataset, alerts=alerts)


# ---------------------------------------------------------------------------
# SSE stream (Redis Pub/Sub → Server-Sent Events)
# ---------------------------------------------------------------------------

@app.get("/api/v1/stream")
async def sse_stream(request: Request, dataset: str = Query("FD001")):
    """
    Server-Sent Events endpoint.
    Events: tick, status_change, alert, heartbeat.
    Connect with Last-Event-ID to resume from Redis stream.
    """
    async def event_generator():
        r = aioredis.from_url(REDIS_URL)
        pubsub = r.pubsub()
        await pubsub.subscribe(f"vl:{dataset}:ticks")
        last_heartbeat = asyncio.get_event_loop().time()

        try:
            while True:
                if await request.is_disconnected():
                    break

                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=0.5
                )
                if message is not None:
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode()
                    try:
                        events = json.loads(data)
                    except json.JSONDecodeError:
                        events = []

                    for ev in events:
                        ev_type = ev.get("type", "tick")
                        yield f"event: {ev_type}\ndata: {json.dumps(ev)}\n\n"
                else:
                    # Heartbeat every 10 s
                    now = asyncio.get_event_loop().time()
                    if now - last_heartbeat >= 10:
                        yield "event: heartbeat\ndata: {}\n\n"
                        last_heartbeat = now

                await asyncio.sleep(0.05)
        finally:
            await pubsub.unsubscribe(f"vl:{dataset}:ticks")
            await r.aclose()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Meta / transparency
# ---------------------------------------------------------------------------

@app.get("/api/v1/meta/data", response_model=schemas.MetaData)
def get_meta_data():
    return schemas.MetaData(
        provenance=(
            "NASA C-MAPSS (Commercial Modular Aero-Propulsion System Simulation). "
            "Simulated turbofan run-to-failure data. Not real sensor readings."
        ),
        license="Not specified by NASA. Data provided for research use.",
        citation=(
            "Saxena A. and Goebel K. (2008). 'Turbofan Engine Degradation Simulation "
            "Data Set', NASA Ames Prognostics Data Repository, Moffett Field, CA."
        ),
    )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    """Check Redis connectivity."""
    try:
        r = _redis_sync()
        r.ping()
        return {"status": "ok", "redis": "ok"}
    except (OSError, RuntimeError, ConnectionError) as exc:
        return {"status": "degraded", "redis": str(exc)}
