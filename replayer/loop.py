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
from api.app.store import get_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("replayer")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
TICK_MS = int(os.getenv("REPLAY_TICK_MS", "1000"))
REPLAY_MODE = os.getenv("REPLAY_MODE", "train")
MODEL_DIR = os.getenv("MODEL_DIR", "ml/artifacts")
DATA_DIR = os.getenv("VANELOOP_DATA_DIR", "data/raw")

COLS = ["unit", "cycle", "op1", "op2", "op3"] + [f"s{i}" for i in range(1, 22)]


# ---------------------------------------------------------------------------
# Optional ONNX inference loader
# ---------------------------------------------------------------------------


def _load_onnx_session(model_dir: str):
    """Returns a dict of onnxruntime.InferenceSession objects (or single session), or None if unavailable."""
    try:
        import onnxruntime as ort  # type: ignore

        model_path = os.path.join(model_dir, "model_p50.onnx")
        if os.path.exists(model_path):
            logger.info(f"Loading ONNX model from {model_path}")
            sessions = {"p50": ort.InferenceSession(model_path)}
            for q in ("p10", "p90"):
                q_path = os.path.join(model_dir, f"model_{q}.onnx")
                if os.path.exists(q_path):
                    sessions[q] = ort.InferenceSession(q_path)
            return sessions
    except ImportError:
        logger.warning("onnxruntime not installed — using linear RUL fallback.")
    return None


def _load_feature_cols(model_dir: str) -> list[str] | None:
    feat_path = os.path.join(model_dir, "features.yaml")
    if os.path.exists(feat_path):
        try:
            import yaml

            with open(feat_path) as f:
                cols = yaml.safe_load(f)
            if isinstance(cols, list):
                return cols
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not load features.yaml: %s", exc)
    return None


def _linear_rul(cycle: int, max_cycle: int) -> tuple[float, float, float]:
    """Simple degrading RUL estimate when no model is available."""
    raw_p50 = max(0.0, float(max_cycle - cycle))
    p50 = min(raw_p50, 125.0)
    p10 = max(0.0, p50 - 15.0)
    p90 = p50 + 15.0
    return p10, p50, p90


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


class DatasetReplay:
    def __init__(self, dataset: str, data_path: str, feature_cols: list[str] | None = None):
        self.dataset = dataset
        self.data_path = data_path
        self.df = pd.read_csv(data_path, sep=r"\s+", header=None, names=COLS)
        self.max_cycles: dict[int, int] = self.df.groupby("unit")["cycle"].max().to_dict()
        self.engines = sorted(self.df["unit"].unique().tolist())
        self.current_cycles: dict[int, int] = {
            u: int(self.df[self.df["unit"] == u]["cycle"].min()) for u in self.engines
        }
        self.df_indexed = self.df.set_index(["unit", "cycle"])
        self.policy = StatusPolicy()
        self.alert_engine = AlertEngine()

        self.features_indexed: pd.DataFrame | None = None
        if feature_cols:
            try:
                from sklearn.preprocessing import StandardScaler

                from ml.preprocess import FD_SENSORS, generate_rolling_features

                scaled_df = self.df.copy()
                scaler = StandardScaler()
                scaled_df[FD_SENSORS] = scaler.fit_transform(scaled_df[FD_SENSORS])
                feat_df = generate_rolling_features(scaled_df, FD_SENSORS)
                self.features_indexed = feat_df.set_index(["unit", "cycle"])[feature_cols]
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to precompute ONNX features for %s: %s", dataset, exc)


def run(dataset: str = "FD001", data_path: str | None = None) -> None:
    datasets = ["FD001", "FD002", "FD003", "FD004"] if dataset.lower() == "all" else [dataset]
    active_replays: list[DatasetReplay] = []

    onnx_session = _load_onnx_session(MODEL_DIR)
    feature_cols = _load_feature_cols(MODEL_DIR) if onnx_session is not None else None

    for ds in datasets:
        ds_path = (
            data_path
            if (data_path and len(datasets) == 1)
            else os.path.join(DATA_DIR, f"{'train' if REPLAY_MODE == 'train' else 'test'}_{ds}.txt")
        )
        if not os.path.exists(ds_path):
            logger.warning(f"Data file not found for {ds}: {ds_path}. Skipping.")
            continue
        logger.info(f"Loading {ds} from {ds_path} (mode={REPLAY_MODE})")
        active_replays.append(DatasetReplay(ds, ds_path, feature_cols=feature_cols))

    if not active_replays:
        logger.error("No valid dataset found to replay.")
        return

    r = None
    try:
        logger.info(f"Connecting to Redis at {REDIS_URL}")
        client = redis.from_url(REDIS_URL, decode_responses=True)
        client.ping()
        r = client
        logger.info("Connected to Redis successfully.")
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Redis unavailable ({exc}); continuing with cold-path store only.")

    store = get_store()
    total_engines = sum(len(dr.engines) for dr in active_replays)
    logger.info(
        f"Starting replay: {total_engines} engines across {len(active_replays)} datasets, tick={TICK_MS}ms"
    )
    replay_start = time.time()

    for tick_idx in count():
        for dr in active_replays:
            ds = dr.dataset
            tick_events: list[dict] = []
            prediction_rows: list[dict] = []
            alert_rows: list[dict] = []
            counts: dict[str, int] = {"Nominal": 0, "Warning": 0, "Critical": 0}

            for unit in dr.engines:
                cycle = dr.current_cycles[unit]

                try:
                    row = dr.df_indexed.loc[(unit, cycle)]
                except KeyError:
                    # Engine finished its trajectory
                    if REPLAY_MODE == "loop":
                        dr.current_cycles[unit] = int(dr.df[dr.df["unit"] == unit]["cycle"].min())
                    continue

                sensors: dict[str, float] = {f"s{i}": float(row[f"s{i}"]) for i in range(1, 22)}

                # --- Inference ---
                if isinstance(onnx_session, dict) and dr.features_indexed is not None:
                    import numpy as np

                    feat_vec = (
                        dr.features_indexed.loc[(unit, cycle)]
                        .to_numpy(dtype=np.float32)
                        .reshape(1, -1)
                    )
                    raw_p50 = float(
                        onnx_session["p50"].run(None, {"float_input": feat_vec})[0].flatten()[0]
                    )
                    rul_p50 = float(np.clip(raw_p50, 0.0, 125.0))
                    if "p10" in onnx_session and "p90" in onnx_session:
                        raw_p10 = float(
                            onnx_session["p10"]
                            .run(None, {"float_input": feat_vec})[0]
                            .flatten()[0]
                        )
                        raw_p90 = float(
                            onnx_session["p90"]
                            .run(None, {"float_input": feat_vec})[0]
                            .flatten()[0]
                        )
                        rul_p10 = float(np.clip(min(raw_p10, rul_p50), 0.0, 125.0))
                        rul_p90 = float(np.clip(max(raw_p90, rul_p50), 0.0, 140.0))
                    else:
                        rul_p10 = max(0.0, rul_p50 - 15.0)
                        rul_p90 = rul_p50 + 15.0
                else:
                    rul_p10, rul_p50, rul_p90 = _linear_rul(cycle, dr.max_cycles[unit])

                # --- Policy ---
                prev_state = dr.policy.current_state(unit)
                new_state = dr.policy.evaluate(unit, cycle, rul_p10, rul_p50)
                counts[new_state] += 1

                # --- Alerts ---
                alerts = dr.alert_engine.check(unit, cycle, prev_state, new_state, sensors)

                # --- Redis hot-path writes (if available) ---
                if r is not None:
                    try:
                        status_key = f"vl:{ds}:engine:{unit}:status"
                        r.hset(
                            status_key,
                            mapping={
                                "dataset": ds,
                                "unit": unit,
                                "cycle": cycle,
                                "state": new_state,
                                "rul_p10": rul_p10,
                                "rul_p50": rul_p50,
                                "rul_p90": rul_p90,
                                "warmup": "true" if cycle <= 30 else "false",
                                "model_version": "1.0.0",
                                "updated_at": time.time(),
                            },
                        )
                        r.zadd(f"vl:{ds}:fleet:by_rul", {str(unit): rul_p50})
                    except (redis.exceptions.RedisError, OSError) as exc:
                        logger.debug("Redis status write failed: %s", exc)

                prediction_rows.append(
                    {
                        "dataset": ds,
                        "unit": unit,
                        "cycle": cycle,
                        "model_version": "replay-baseline-v0"
                        if onnx_session is None
                        else "onnx-v1",
                        "rul_p10": rul_p10,
                        "rul_p50": rul_p50,
                        "rul_p90": rul_p90,
                        "health_index": None,
                        "state": new_state,
                        "warmup": cycle <= 30,
                    }
                )

                tick_events.append(
                    {
                        "type": "tick" if new_state == prev_state else "status_change",
                        "unit": unit,
                        "cycle": cycle,
                        "state": new_state,
                        "rul_p50": round(rul_p50, 1),
                        "rul_p10": round(rul_p10, 1),
                        "rul_p90": round(rul_p90, 1),
                        "warmup": cycle <= 30,
                    }
                )

                for alert in alerts:
                    alert_payload = {**alert, "dataset": ds}
                    if r is not None:
                        try:
                            r.xadd(
                                f"vl:{ds}:alerts",
                                {"payload": json.dumps(alert_payload)},
                                maxlen=1000,
                            )
                        except (redis.exceptions.RedisError, OSError) as exc:
                            logger.debug("Redis alert push failed: %s", exc)
                    alert_rows.append(
                        {
                            **alert,
                            "dataset": ds,
                            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        }
                    )
                    tick_events.append({"type": "alert", **alert, "dataset": ds})
                    logger.info(
                        f"ALERT ds={ds} unit={unit} cycle={cycle} rule={alert['rule']} sev={alert['severity']}"
                    )

                dr.current_cycles[unit] += 1

            if r is not None:
                try:
                    r.hset(
                        f"vl:{ds}:fleet:counts",
                        mapping={
                            "nominal": counts["Nominal"],
                            "warning": counts["Warning"],
                            "critical": counts["Critical"],
                        },
                    )
                    r.publish(f"vl:{ds}:ticks", json.dumps(tick_events))
                except (redis.exceptions.RedisError, OSError) as exc:
                    logger.debug("Redis fleet count update failed: %s", exc)

            store.write_predictions(prediction_rows)
            if alert_rows:
                store.write_alerts(alert_rows)

            logger.info(
                f"[{ds}] tick={tick_idx} N={counts['Nominal']} W={counts['Warning']} C={counts['Critical']}"
            )

        replay_clock = time.time() - replay_start
        logger.info(f"tick={tick_idx} replay_elapsed={replay_clock:.1f}s")
        time.sleep(TICK_MS / 1000.0)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--dataset", default="FD001", help="FD001, FD002, FD003, FD004 or all")
    args = p.parse_args()
    run(dataset=args.dataset)
