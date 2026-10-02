"""
tests/test_policy.py — Unit tests for api/app/policy.py.

Run with:  uv run pytest tests/test_policy.py -v
"""
import pytest
from api.app.policy import (
    AlertEngine,
    SensorDriftTracker,
    StatusPolicy,
    apply_hysteresis,
    compute_raw_state,
    BASELINE_CYCLES,
    DRIFT_CONSECUTIVE_CYCLES,
    HYSTERESIS_STREAK,
    WARMUP_CYCLES,
)


# ---------------------------------------------------------------------------
# compute_raw_state
# ---------------------------------------------------------------------------

class TestComputeRawState:
    def test_critical_when_p10_le_30(self):
        assert compute_raw_state(rul_p10=30, rul_p50=100) == "Critical"

    def test_warning_when_p50_le_70(self):
        assert compute_raw_state(rul_p10=60, rul_p50=70) == "Warning"

    def test_warning_when_p10_le_50(self):
        assert compute_raw_state(rul_p10=50, rul_p50=80) == "Warning"

    def test_nominal_otherwise(self):
        assert compute_raw_state(rul_p10=51, rul_p50=71) == "Nominal"

    def test_boundary_critical_p10_exactly_30(self):
        assert compute_raw_state(rul_p10=30, rul_p50=50) == "Critical"


# ---------------------------------------------------------------------------
# apply_hysteresis
# ---------------------------------------------------------------------------

class TestApplyHysteresis:
    def test_upgrade_is_immediate(self):
        state, streak = apply_hysteresis("Critical", "Nominal", 0)
        assert state == "Critical"
        assert streak == 0

    def test_downgrade_needs_streak(self):
        # First downgrade attempt — stays published
        state, streak = apply_hysteresis("Nominal", "Critical", 0)
        assert state == "Critical"
        assert streak == 1

    def test_downgrade_fires_after_streak(self):
        state, streak = apply_hysteresis("Nominal", "Critical", HYSTERESIS_STREAK - 1)
        assert state == "Nominal"

    def test_same_state_is_stable(self):
        state, streak = apply_hysteresis("Warning", "Warning", 0)
        assert state == "Warning"
        assert streak == 0


# ---------------------------------------------------------------------------
# StatusPolicy (stateful)
# ---------------------------------------------------------------------------

class TestStatusPolicy:
    def test_warmup_returns_nominal(self):
        p = StatusPolicy()
        assert p.evaluate(1, cycle=1, rul_p10=0, rul_p50=0) == "Nominal"
        assert p.evaluate(1, cycle=WARMUP_CYCLES, rul_p10=0, rul_p50=0) == "Nominal"

    def test_transitions_after_warmup(self):
        p = StatusPolicy()
        # First cycle post-warmup, low RUL → Critical immediately
        state = p.evaluate(1, cycle=WARMUP_CYCLES + 1, rul_p10=10, rul_p50=20)
        assert state == "Critical"

    def test_downgrade_needs_three_cycles(self):
        p = StatusPolicy()
        cycle = WARMUP_CYCLES + 1
        # Push to Critical
        p.evaluate(1, cycle=cycle, rul_p10=10, rul_p50=20)

        # Now RUL recovers (e.g. model uncertainty shift) — should stay Critical for 2 cycles
        for i in range(1, HYSTERESIS_STREAK):
            state = p.evaluate(1, cycle=cycle + i, rul_p10=80, rul_p50=120)
            assert state == "Critical", f"Expected Critical on downgrade streak {i}"

        # On the 3rd cycle with better RUL, should downgrade
        state = p.evaluate(1, cycle=cycle + HYSTERESIS_STREAK, rul_p10=80, rul_p50=120)
        assert state == "Nominal"

    def test_multiple_units_are_independent(self):
        p = StatusPolicy()
        c = WARMUP_CYCLES + 1
        p.evaluate(1, c, rul_p10=10, rul_p50=20)   # unit 1 → Critical
        state2 = p.evaluate(2, c, rul_p10=80, rul_p50=120)  # unit 2 → Nominal
        assert state2 == "Nominal"
        assert p.current_state(1) == "Critical"


# ---------------------------------------------------------------------------
# SensorDriftTracker (R2)
# ---------------------------------------------------------------------------

class TestSensorDriftTracker:
    def _stable_readings(self, mean: float = 100.0, std: float = 1.0):
        """Returns a dict of sensor values at the baseline mean."""
        return {f"s{i}": mean for i in [2, 3, 4, 7, 8, 9, 11, 12, 13, 14, 15, 17, 20, 21]}

    def test_no_alerts_during_baseline_phase(self):
        tracker = SensorDriftTracker()
        for cycle in range(1, BASELINE_CYCLES + 1):
            alerts = tracker.update(unit=1, cycle=cycle, sensors=self._stable_readings())
        assert alerts == []

    def test_no_alerts_when_stable(self):
        tracker = SensorDriftTracker()
        for cycle in range(1, BASELINE_CYCLES + DRIFT_CONSECUTIVE_CYCLES + 5):
            alerts = tracker.update(unit=1, cycle=cycle, sensors=self._stable_readings(100.0, 1.0))
        assert alerts == []

    def test_r2_fires_after_sustained_drift(self):
        tracker = SensorDriftTracker()
        # Feed baseline — mild values, small std
        base_sensors = {f"s{i}": 100.0 for i in [2, 3, 4, 7, 8, 9, 11, 12, 13, 14, 15, 17, 20, 21]}
        for cycle in range(1, BASELINE_CYCLES + 1):
            tracker.update(unit=1, cycle=cycle, sensors=base_sensors)

        # Feed a heavily drifted sensor (s2 way above baseline)
        drifted = dict(base_sensors)
        drifted["s2"] = 1000.0  # large z-score

        fired_alerts = []
        for i in range(DRIFT_CONSECUTIVE_CYCLES + 2):
            alerts = tracker.update(unit=1, cycle=BASELINE_CYCLES + 1 + i, sensors=drifted)
            fired_alerts.extend(alerts)

        r2_alerts = [a for a in fired_alerts if a["rule"] == "R2" and a["sensor"] == "s2"]
        assert len(r2_alerts) > 0, "Expected at least one R2 alert for s2"


# ---------------------------------------------------------------------------
# AlertEngine (integration: R1 + R2 + debounce)
# ---------------------------------------------------------------------------

class TestAlertEngine:
    def test_r1_fires_on_upgrade(self):
        ae = AlertEngine()
        alerts = ae.check(unit=1, cycle=35, prev_state="Nominal", new_state="Warning", sensors={})
        assert any(a["rule"] == "R1" for a in alerts)

    def test_r1_does_not_fire_on_downgrade(self):
        ae = AlertEngine()
        alerts = ae.check(unit=1, cycle=35, prev_state="Critical", new_state="Nominal", sensors={})
        assert not any(a["rule"] == "R1" for a in alerts)

    def test_r1_debounced_within_5_cycles(self):
        ae = AlertEngine()
        ae.check(unit=1, cycle=35, prev_state="Nominal", new_state="Warning", sensors={})
        # Second alert within 5 cycles — should be suppressed
        alerts2 = ae.check(unit=1, cycle=37, prev_state="Nominal", new_state="Critical", sensors={})
        assert not any(a["rule"] == "R1" for a in alerts2)

    def test_r1_fires_again_after_debounce(self):
        ae = AlertEngine()
        ae.check(unit=1, cycle=35, prev_state="Nominal", new_state="Warning", sensors={})
        alerts2 = ae.check(unit=1, cycle=40, prev_state="Warning", new_state="Critical", sensors={})
        assert any(a["rule"] == "R1" for a in alerts2)
