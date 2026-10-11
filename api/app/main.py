"""
main.py — FastAPI application.

All data comes from Redis (hot path) or Cassandra (cold path via Store).
No hard-coded engine data anywhere in this file.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

import redis
import redis.asyncio as aioredis
from fastapi import FastAPI, Path, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from . import schemas
from .store import get_store

logger = logging.getLogger("api")

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
# CORS Configuration (Allows Next.js frontend dev server)
# ---------------------------------------------------------------------------
cors_origins = [
    origin.strip() for origin in os.getenv("CORS_ALLOW_ORIGINS", "").split(",") if origin.strip()
]
if not cors_origins or cors_origins == ["*"]:
    cors_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://vane-loop.vercel.app",
    ]
elif "https://vane-loop.vercel.app" not in cors_origins:
    cors_origins.append("https://vane-loop.vercel.app")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _redis_sync():  # returns redis.Redis, annotated at call-sites
    import redis as _redis

    return _redis.from_url(REDIS_URL, decode_responses=True)


def _with_store(callback):
    store = get_store()
    try:
        return callback(store)
    finally:
        store.close()


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
    """Return all engine statuses and fleet counts. Source: Redis hot path, fallback to Store."""
    if dataset not in DATASET_ALLOW:
        return schemas.FleetResponse(counts=schemas.FleetCounts(), engines=[])

    engines: list[schemas.EngineStatus] = []
    counts = schemas.FleetCounts()

    # Try Redis hot path first
    try:
        r = _redis_sync()
        raw_counts = r.hgetall(f"vl:{dataset}:fleet:counts") or {}
        counts = schemas.FleetCounts(
            nominal=int(raw_counts.get("nominal", 0)),
            warning=int(raw_counts.get("warning", 0)),
            critical=int(raw_counts.get("critical", 0)),
        )

        units = [int(u) for u in r.zrangebyscore(f"vl:{dataset}:fleet:by_rul", "-inf", "+inf")]
        if sort in ("rul_desc",):
            units = units[::-1]
        elif sort == "id":
            units = sorted(units)

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
    except (redis.exceptions.RedisError, OSError) as exc:
        logger.debug("Redis fleet query failed: %s", exc)

    # Cold-path fallback if Redis is down or has no data yet
    if not engines:
        try:
            store_engines = _with_store(lambda s: s.get_fleet_status(dataset))
            c_nom = sum(1 for e in store_engines if e["state"] == "Nominal")
            c_warn = sum(1 for e in store_engines if e["state"] == "Warning")
            c_crit = sum(1 for e in store_engines if e["state"] == "Critical")
            counts = schemas.FleetCounts(nominal=c_nom, warning=c_warn, critical=c_crit)

            for se in store_engines:
                if state and se["state"].lower() != state.lower():
                    continue
                engines.append(schemas.EngineStatus(**se))

            if sort == "rul_desc":
                engines.sort(
                    key=lambda e: e.rul_p50 if e.rul_p50 is not None else 999, reverse=True
                )
            elif sort == "rul_asc":
                engines.sort(key=lambda e: e.rul_p50 if e.rul_p50 is not None else 999)
            elif sort == "id":
                engines.sort(key=lambda e: e.unit)
            elif sort == "cycle":
                engines.sort(key=lambda e: e.cycle, reverse=True)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Store fleet query failed: %s", exc)

    return schemas.FleetResponse(counts=counts, engines=engines)


# ---------------------------------------------------------------------------
# Engine detail (Redis status + Cassandra metadata)
# ---------------------------------------------------------------------------


@app.get("/api/v1/engines/{dataset}/{unit}", response_model=schemas.EngineStatus)
def get_engine_status(dataset: str = Path(...), unit: int = Path(...)):
    """Single engine current status from Redis (hot) or Store (cold)."""
    if dataset not in DATASET_ALLOW:
        return schemas.EngineStatus(dataset=dataset, unit=unit, cycle=0, state="Nominal")
    try:
        r = _redis_sync()
        raw = r.hgetall(f"vl:{dataset}:engine:{unit}:status") or {}
        if raw:
            raw["dataset"] = dataset
            raw["unit"] = str(unit)
            return _parse_status(raw)
    except (redis.exceptions.RedisError, OSError) as exc:
        logger.debug("Redis engine query failed: %s", exc)

    # Fallback to Store
    try:
        readings = _with_store(lambda s: s.get_readings(dataset, unit, limit=1))
        if readings:
            latest = readings[0]
            cycle = latest["cycle"]
            raw_rul = latest.get("rul_true")
            rul_p50 = float(raw_rul) if raw_rul is not None else 125.0
            rul_p10 = max(0.0, rul_p50 - 15.0)
            rul_p90 = rul_p50 + 15.0
            if rul_p10 <= 30:
                eng_state = "Critical"
            elif rul_p50 <= 70 or rul_p10 <= 50:
                eng_state = "Warning"
            else:
                eng_state = "Nominal"
            return schemas.EngineStatus(
                dataset=dataset,
                unit=unit,
                cycle=cycle,
                state=eng_state,
                rul_p10=rul_p10,
                rul_p50=rul_p50,
                rul_p90=rul_p90,
                warmup=cycle <= 30,
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("Store engine query failed: %s", exc)

    return schemas.EngineStatus(dataset=dataset, unit=unit, cycle=0, state="Nominal")


@app.get("/api/v1/engines/{dataset}/{unit}/readings", response_model=schemas.ReadingsResponse)
def get_engine_readings(
    dataset: str = Path(...),
    unit: int = Path(...),
    limit: int = Query(200, le=500),
    before_cycle: int | None = Query(None),
):
    """Engine historical readings from Cassandra (cold path)."""
    try:
        rows = _with_store(
            lambda store: store.get_readings(dataset, unit, limit=limit, before_cycle=before_cycle)
        )
        readings = [schemas.Reading(**r) for r in rows]
    except Exception:  # noqa: BLE001
        readings = []

    return schemas.ReadingsResponse(
        dataset=dataset,
        unit=unit,
        readings=readings,
        next_page_token=readings[-1].cycle if readings else None,
    )


@app.get(
    "/api/v1/engines/{dataset}/{unit}/rul",
    response_model=schemas.PredictionsResponse,
)
def get_engine_rul(
    dataset: str = Path(...),
    unit: int = Path(...),
    from_cycle: int | None = Query(None),
    to_cycle: int | None = Query(None),
):
    """Predicted RUL trajectory with p10-p90 uncertainty from the cold path."""
    try:
        rows = _with_store(
            lambda store: store.get_predictions(
                dataset, unit, from_cycle=from_cycle, to_cycle=to_cycle
            )
        )
        predictions = [
            schemas.EngineStatus(
                dataset=row["dataset"],
                unit=row["unit"],
                cycle=row["cycle"],
                state=row.get("state") or "Nominal",
                rul_p10=row.get("rul_p10"),
                rul_p50=row.get("rul_p50"),
                rul_p90=row.get("rul_p90"),
                health_index=row.get("health_index"),
                warmup=row.get("warmup", False),
                model_version=row.get("model_version"),
            )
            for row in rows
        ]
    except Exception:  # noqa: BLE001
        predictions = []

    return schemas.PredictionsResponse(dataset=dataset, unit=unit, predictions=predictions)


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
    if dataset not in DATASET_ALLOW or sensor not in SENSOR_ALLOW:
        return schemas.SensorTrendResponse(dataset=dataset, sensor=sensor, points=[])
    try:
        points = _with_store(
            lambda store: store.get_sensor_fleet_trend(dataset, sensor, from_cycle, to_cycle)
        )
    except Exception:  # noqa: BLE001
        points = []
    return schemas.SensorTrendResponse(dataset=dataset, sensor=sensor, points=points)


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
    """Alert feed from Redis Stream (hot) or Cassandra / SQLite (cold)."""
    alerts: list[schemas.AlertItem] = []
    try:
        r = _redis_sync()
        stream_key = f"vl:{dataset}:alerts"
        raw_entries = r.xrevrange(stream_key, count=limit * 3)  # over-fetch for filter
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

            alerts.append(
                schemas.AlertItem(
                    unit=payload.get("unit", 0),
                    cycle=payload.get("cycle", 0),
                    rule=payload.get("rule", ""),
                    severity=payload.get("severity", "Warning"),
                    sensor=payload.get("sensor"),
                    message=payload.get("message", ""),
                )
            )
            if len(alerts) >= limit:
                break
    except (redis.exceptions.RedisError, OSError) as exc:
        logger.debug("Redis alerts stream query failed: %s", exc)

    # Cold-path fallback if Redis is down or has no alerts
    if not alerts:
        try:
            store_alerts = _with_store(
                lambda s: s.get_alerts(
                    dataset, severity=severity, rule=rule, unit=unit, limit=limit
                )
            )
            for a in store_alerts:
                alerts.append(
                    schemas.AlertItem(
                        unit=a.get("unit", 0),
                        cycle=a.get("cycle", 0),
                        rule=a.get("rule", ""),
                        severity=a.get("severity", "Warning"),
                        sensor=a.get("sensor"),
                        message=a.get("message", ""),
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Store alerts query failed: %s", exc)

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
        try:
            r = aioredis.from_url(REDIS_URL)
            pubsub = r.pubsub()
            await pubsub.subscribe(f"vl:{dataset}:ticks")
            last_heartbeat = asyncio.get_event_loop().time()

            try:
                while True:
                    if await request.is_disconnected():
                        break

                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
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
        except Exception as exc:  # noqa: BLE001
            logger.debug("Pubsub stream unavailable: %s", exc)
            # Fallback heartbeat generator when Redis is not running
            while True:
                if await request.is_disconnected():
                    break
                yield "event: heartbeat\ndata: {}\n\n"
                await asyncio.sleep(5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Benchmarks (committed results B-1)
# ---------------------------------------------------------------------------


@app.get("/api/v1/benchmarks")
def get_benchmarks():
    results = []
    res_dir = os.path.join("benchmarks", "results")
    if os.path.exists(res_dir):
        for f in sorted(os.listdir(res_dir)):
            if f.endswith(".json"):
                try:
                    with open(os.path.join(res_dir, f)) as fp:
                        results.append(json.load(fp))
                except (json.JSONDecodeError, OSError) as exc:
                    logger.debug("Benchmark file read failed: %s", exc)
    return {"benchmarks": results}


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
