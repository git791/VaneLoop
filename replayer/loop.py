"""
replayer/loop.py — Replay loop.

Reads the training dataset row by row (one tick = one cycle per engine),
runs ONNX inference (or a linear fallback when model is absent),
applies status policy and alert rules, then writes to Redis.

Usage:
    uv run python -m replayer.loop --dataset FD001

Environment:
    REPLAY_TICK_MS      ms between ticks (default 1000)
    REPLAY_MODE         train | test | loop  (default train)
    REDIS_URL           redis connection string
    MODEL_DIR           directory containing model.onnx + scaler.json + features.yaml
"""
from __future__ import annotations

import json
import logging
import os
import time
from itertools import count

import pandas as pd
import redis

from api.app.policy import AlertEngine, StatusPolicy

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("replayer")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
TICK_MS = int(os.getenv("REPLAY_TICK_MS", "1000"))
REPLAY_MODE = os.getenv("REPLAY_MODE", "train")
MODEL_DIR = os.getenv("MODEL_DIR", "ml/artifacts")

COLS = ["unit", "cycle", "op1", "op2", "op3"] + [f"s{i}" for i in range(1, 22)]


# ---------------------------------------------------------------------------
# Optional ONNX inference loader
# ---------------------------------------------------------------------------

def _load_onnx_session(model_dir: str):
    """Returns an onnxruntime.InferenceSession, or None if not available."""
    try:
        import onnxruntime as ort  # type: ignore
        model_path = os.path.join(model_dir, "model_p50.onnx")
        if os.path.exists(model_path):
            logger.info(f"Loading ONNX model from {model_path}")
            return ort.InferenceSession(model_path)
    except ImportError:
        logger.warning("onnxruntime not installed — using linear RUL fallback.")
    return None


def _linear_rul(cycle: int, max_cycle: int) -> tuple[float, float, float]:
    """Simple degrading RUL estimate when no model is available."""
    p50 = max(0.0, float(max_cycle - cycle))
    p10 = max(0.0, p50 - 15.0)
    p90 = p50 + 15.0
    return p10, min(p50, 125.0), p90


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run(dataset: str = "FD001", data_path: str | None = None) -> None:
    if data_path is None:
        split = "train" if REPLAY_MODE == "train" else "test"
        data_path = f"data/raw/{split}_{dataset}.txt"

    if not os.path.exists(data_path):
        logger.error(
            f"Data file not found: {data_path}\n"
            "Run:  uv run python scripts/fetch_data.py  then retry."
        )
        return

    logger.info(f"Loading {dataset} from {data_path} (mode={REPLAY_MODE})")
    df = pd.read_csv(data_path, sep=r"\s+", header=None, names=COLS)
    # Pre-compute max cycle per unit for linear RUL fallback
    max_cycles: dict[int, int] = df.groupby("unit")["cycle"].max().to_dict()

    engines = sorted(df["unit"].unique().tolist())
    current_cycles: dict[int, int] = {u: int(df[df["unit"] == u]["cycle"].min()) for u in engines}

    # Build a cycle-indexed lookup for O(1) row access
    df_indexed = df.set_index(["unit", "cycle"])

    policy = StatusPolicy()
    alert_engine = AlertEngine()
    onnx_session = _load_onnx_session(MODEL_DIR)

    logger.info(f"Connecting to Redis at {REDIS_URL}")
    r = redis.from_url(REDIS_URL, decode_responses=True)

    logger.info(f"Starting replay: {len(engines)} engines, tick={TICK_MS}ms")
    replay_start = time.time()

    for tick_idx in count():
        tick_events: list[dict] = []
        counts: dict[str, int] = {"Nominal": 0, "Warning": 0, "Critical": 0}

        for unit in engines:
            cycle = current_cycles[unit]

            try:
                row = df_indexed.loc[(unit, cycle)]
            except KeyError:
                # Engine finished its trajectory
                if REPLAY_MODE == "loop":
                    current_cycles[unit] = int(df[df["unit"] == unit]["cycle"].min())
                continue

            sensors: dict[str, float] = {f"s{i}": float(row[f"s{i}"]) for i in range(1, 22)}

            # --- Inference ---
            if onnx_session is not None:
                # TODO: build proper 30-cycle windowed input and run session
                rul_p10, rul_p50, rul_p90 = _linear_rul(cycle, max_cycles[unit])
            else:
                rul_p10, rul_p50, rul_p90 = _linear_rul(cycle, max_cycles[unit])

            # --- Policy ---
            prev_state = policy.current_state(unit)
            new_state = policy.evaluate(unit, cycle, rul_p10, rul_p50)
            counts[new_state] += 1

            # --- Alerts ---
            alerts = alert_engine.check(unit, cycle, prev_state, new_state, sensors)

            # --- Redis hot-path writes ---
            status_key = f"vl:{dataset}:engine:{unit}:status"
            r.hset(status_key, mapping={
                "dataset": dataset,
                "unit": unit,
                "cycle": cycle,
                "state": new_state,
                "rul_p10": rul_p10,
                "rul_p50": rul_p50,
                "rul_p90": rul_p90,
                "warmup": "true" if cycle <= 30 else "false",
                "model_version": "1.0.0",
                "updated_at": time.time(),
            })
            r.zadd(f"vl:{dataset}:fleet:by_rul", {str(unit): rul_p50})

            # Append tick event for SSE fan-out
            tick_events.append({
                "type": "tick" if new_state == prev_state else "status_change",
                "unit": unit,
                "cycle": cycle,
                "state": new_state,
                "rul_p50": round(rul_p50, 1),
                "rul_p10": round(rul_p10, 1),
                "rul_p90": round(rul_p90, 1),
                "warmup": cycle <= 30,
            })

            # Push alerts — never dropped
            for alert in alerts:
                payload = json.dumps({**alert, "dataset": dataset})
                r.xadd(f"vl:{dataset}:alerts", {"payload": payload}, maxlen=1000)
                tick_events.append({"type": "alert", **alert, "dataset": dataset})
                logger.info(f"ALERT unit={unit} cycle={cycle} rule={alert['rule']} sev={alert['severity']}")

            current_cycles[unit] += 1

        # Atomic fleet count update
        r.hset(f"vl:{dataset}:fleet:counts", mapping={
            "nominal": counts["Nominal"],
            "warning": counts["Warning"],
            "critical": counts["Critical"],
        })

        # Publish all tick+alert events on the pub/sub channel
        r.publish(f"vl:{dataset}:ticks", json.dumps(tick_events))

        replay_clock = time.time() - replay_start
        logger.info(
            f"tick={tick_idx} replay_t={replay_clock:.1f}s  "
            f"N={counts['Nominal']} W={counts['Warning']} C={counts['Critical']}"
        )
        time.sleep(TICK_MS / 1000.0)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", default="FD001")
    args = p.parse_args()
    run(dataset=args.dataset)
