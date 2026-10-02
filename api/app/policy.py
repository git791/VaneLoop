"""
policy.py — Status evaluation and alert rules.

All functions are pure (no I/O) and unit-tested in tests/test_policy.py.
"""
from __future__ import annotations

import math

SEVERITY = {"Nominal": 0, "Warning": 1, "Critical": 2}

# Informative sensors for FD001 used in R2 drift checks
INFORMATIVE_SENSORS = [
    "s2", "s3", "s4", "s7", "s8", "s9", "s11",
    "s12", "s13", "s14", "s15", "s17", "s20", "s21",
]

EWMA_LAMBDA = 0.2
DRIFT_Z_THRESHOLD = 3.0
DRIFT_CONSECUTIVE_CYCLES = 5
BASELINE_CYCLES = 20
DEBOUNCE_CYCLES = 5
HYSTERESIS_STREAK = 3
WARMUP_CYCLES = 30


# ---------------------------------------------------------------------------
# Status policy (pure function)
# ---------------------------------------------------------------------------

def compute_raw_state(rul_p10: float, rul_p50: float) -> str:
    """Return the raw (pre-hysteresis) state from RUL quantiles."""
    if rul_p10 <= 30:
        return "Critical"
    if rul_p50 <= 70 or rul_p10 <= 50:
        return "Warning"
    return "Nominal"


def apply_hysteresis(raw_state: str, prev_published: str, streak: int) -> tuple[str, int]:
    """
    Returns (next_published_state, new_streak).
    Upgrades happen immediately. Downgrades require HYSTERESIS_STREAK consecutive cycles.
    """
    if SEVERITY[raw_state] >= SEVERITY[prev_published]:
        return raw_state, 0
    # Downgrade path
    new_streak = streak + 1
    if new_streak >= HYSTERESIS_STREAK:
        return raw_state, new_streak
    return prev_published, new_streak


class StatusPolicy:
    """Stateful wrapper that tracks per-engine hysteresis across ticks."""

    def __init__(self) -> None:
        # unit -> {"raw": str, "published": str, "streak": int}
        self._history: dict[int, dict] = {}

    def evaluate(self, unit: int, cycle: int, rul_p10: float, rul_p50: float) -> str:
        """Return the final (hysteresis-applied) state for this cycle."""
        if cycle <= WARMUP_CYCLES:
            return "Nominal"

        raw = compute_raw_state(rul_p10, rul_p50)
        h = self._history.get(unit, {"raw": "Nominal", "published": "Nominal", "streak": 0})
        prev_published = h["published"]

        # Streak only counts when raw stays the same as last raw (for downgrades)
        streak = h["streak"] if raw == h["raw"] else 0
        published, streak = apply_hysteresis(raw, prev_published, streak)

        self._history[unit] = {"raw": raw, "published": published, "streak": streak}
        return published

    def current_state(self, unit: int) -> str:
        return self._history.get(unit, {}).get("published", "Nominal")


# ---------------------------------------------------------------------------
# R2 – per-engine sensor drift (EWMA z-score)
# ---------------------------------------------------------------------------

class SensorDriftTracker:
    """
    Tracks per-engine, per-sensor EWMA and baseline.
    R2 fires when |z| > DRIFT_Z_THRESHOLD for DRIFT_CONSECUTIVE_CYCLES straight.
    """

    def __init__(self) -> None:
        # unit -> sensor -> list[float]  (first BASELINE_CYCLES raw values)
        self._baseline_buf: dict[int, dict[str, list[float]]] = {}
        # unit -> sensor -> {"mean": float, "std": float}
        self._baseline: dict[int, dict[str, dict]] = {}
        # unit -> sensor -> ewma value
        self._ewma: dict[int, dict[str, float]] = {}
        # unit -> sensor -> consecutive z-breach count
        self._streak: dict[int, dict[str, int]] = {}

    def update(self, unit: int, cycle: int, sensors: dict[str, float]) -> list[dict]:
        """
        Feed one cycle of sensor readings.
        Returns a list of drift-alert dicts for sensors that breach the threshold.
        """
        alerts: list[dict] = []
        unit_buf = self._baseline_buf.setdefault(unit, {})
        unit_bl = self._baseline.get(unit, {})
        unit_ewma = self._ewma.setdefault(unit, {})
        unit_streak = self._streak.setdefault(unit, {})

        for sensor, value in sensors.items():
            if sensor not in INFORMATIVE_SENSORS:
                continue

            # --- Phase 1: accumulate baseline buffer ---
            buf = unit_buf.setdefault(sensor, [])
            if len(buf) < BASELINE_CYCLES:
                buf.append(value)
                if len(buf) == BASELINE_CYCLES:
                    mean = sum(buf) / len(buf)
                    std = math.sqrt(sum((x - mean) ** 2 for x in buf) / len(buf)) or 1e-6
                    self._baseline.setdefault(unit, {})[sensor] = {"mean": mean, "std": std}
                unit_ewma[sensor] = value
                unit_streak[sensor] = 0
                continue

            # --- Phase 2: EWMA update + z-score check ---
            bl = unit_bl.get(sensor, {"mean": value, "std": 1.0})
            prev_ewma = unit_ewma.get(sensor, value)
            ewma = EWMA_LAMBDA * value + (1 - EWMA_LAMBDA) * prev_ewma
            unit_ewma[sensor] = ewma

            z = (ewma - bl["mean"]) / bl["std"]
            if abs(z) > DRIFT_Z_THRESHOLD:
                unit_streak[sensor] = unit_streak.get(sensor, 0) + 1
            else:
                unit_streak[sensor] = 0

            if unit_streak[sensor] >= DRIFT_CONSECUTIVE_CYCLES:
                alerts.append({
                    "rule": "R2",
                    "sensor": sensor,
                    "z_score": round(z, 2),
                    "ewma": round(ewma, 4),
                    "baseline_mean": round(bl["mean"], 4),
                    "baseline_std": round(bl["std"], 6),
                })

        self._ewma[unit] = unit_ewma
        self._streak[unit] = unit_streak
        return alerts


# ---------------------------------------------------------------------------
# Alert engine (debounce + R1 + R2)
# ---------------------------------------------------------------------------

class AlertEngine:
    """
    Combines R1 (state transition) and R2 (sensor drift) alert rules.
    Debounces: at most 1 alert per (unit, rule) per DEBOUNCE_CYCLES.
    """

    def __init__(self) -> None:
        self._last_alert: dict[tuple, int] = {}  # (unit, rule_key) -> last cycle
        self.drift = SensorDriftTracker()

    def _can_alert(self, unit: int, rule_key: str, cycle: int) -> bool:
        last = self._last_alert.get((unit, rule_key), -9999)
        if cycle - last >= DEBOUNCE_CYCLES:
            self._last_alert[(unit, rule_key)] = cycle
            return True
        return False

    def check(
        self,
        unit: int,
        cycle: int,
        prev_state: str,
        new_state: str,
        sensors: dict[str, float],
    ) -> list[dict]:
        alerts: list[dict] = []

        # R1 — state upgrade
        if SEVERITY[new_state] > SEVERITY[prev_state] and self._can_alert(unit, "R1", cycle):
            alerts.append({
                "unit": unit,
                "cycle": cycle,
                "rule": "R1",
                "severity": new_state,
                "message": f"Status upgraded: {prev_state} → {new_state}",
            })

        # R2 — sensor drift
        drift_hits = self.drift.update(unit, cycle, sensors)
        for hit in drift_hits:
            rule_key = f"R2:{hit['sensor']}"
            if self._can_alert(unit, rule_key, cycle):
                alerts.append({
                    "unit": unit,
                    "cycle": cycle,
                    "rule": "R2",
                    "severity": "Warning",
                    "sensor": hit["sensor"],
                    "z_score": hit["z_score"],
                    "message": (
                        f"Sensor {hit['sensor']} EWMA z={hit['z_score']} "
                        f"exceeds ±{DRIFT_Z_THRESHOLD} for {DRIFT_CONSECUTIVE_CYCLES} cycles"
                    ),
                })

        return alerts
