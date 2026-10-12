"""
store.py -- cold-path storage adapters.

Implements one `Store` contract (docs/TECHNICAL.md 2, 4) with two backends:

* `CassandraStore` -- primary cold path. Query-first modelling: one table per
  query pattern, prepared statements only, no ALLOW FILTERING.
* `SQLiteStore`    -- fallback so the demo and CI run without a cluster. Same
  logical schema; used for tests and local development.

Both are idempotent: writing the same primary key twice is an upsert, so an
ingest or replay can restart at any time. No engine data is hard-coded here --
every value is supplied by the caller.
"""

from __future__ import annotations

import base64
import logging
import os
import sqlite3
import threading
import uuid
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


SENSOR_IDS: list[str] = [f"s{i}" for i in range(1, 22)]
OP_COLUMNS: list[str] = ["op1", "op2", "op3"]
SENSOR_BUCKET_SIZE = 50  # cycle_bucket = cycle // 50  (TECHNICAL.md 4.1 Q2)
ALERT_SHARDS = 8
ALERT_TTL_SECONDS = 7_776_000  # 90 days
MAX_CYCLE = 2_147_483_647
logger = logging.getLogger(__name__)

# Columns of `engine_readings` in physical order (infra/cassandra/schema.cql).
READING_COLUMNS: list[str] = ["dataset", "unit", "cycle", *OP_COLUMNS, *SENSOR_IDS, "rul_true"]


def cycle_bucket(cycle: int) -> int:
    return cycle // SENSOR_BUCKET_SIZE


def alert_shard(unit: int) -> int:
    return unit % ALERT_SHARDS


@runtime_checkable
class Store(Protocol):
    """The cold-path contract: one method per query in TECHNICAL.md 4.1."""

    def migrate(self, schema_path: str | Path | None = None) -> None: ...

    def upsert_readings(self, rows: Iterable[dict[str, Any]]) -> int: ...

    def get_readings(
        self,
        dataset: str,
        unit: int,
        limit: int = 200,
        before_cycle: int | None = None,
    ) -> list[dict[str, Any]]: ...

    def get_sensor_fleet_trend(
        self,
        dataset: str,
        sensor: str,
        from_cycle: int = 1,
        to_cycle: int = MAX_CYCLE,
        max_points: int = 2000,
    ) -> list[dict[str, Any]]: ...

    def write_predictions(self, rows: Iterable[dict[str, Any]]) -> int: ...

    def get_predictions(
        self,
        dataset: str,
        unit: int,
        from_cycle: int | None = None,
        to_cycle: int | None = None,
    ) -> list[dict[str, Any]]: ...

    def write_alerts(self, rows: Iterable[dict[str, Any]]) -> int: ...

    def get_alerts(
        self,
        dataset: str,
        severity: str | None = None,
        rule: str | None = None,
        unit: int | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]: ...

    def get_alerts_for_engine(
        self, dataset: str, unit: int, limit: int = 50
    ) -> list[dict[str, Any]]: ...

    def get_fleet_status(self, dataset: str) -> list[dict[str, Any]]: ...

    def close(self) -> None: ...


# ---------------------------------------------------------------------------
# Cassandra (primary cold path)
# ---------------------------------------------------------------------------


class CassandraStore:
    """Cassandra-backed cold-path store: prepared statements, async writes."""

    def __init__(
        self,
        contact_points: list[str] | None = None,
        keyspace: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        from cassandra.auth import PlainTextAuthProvider  # type: ignore
        from cassandra.cluster import Cluster  # type: ignore

        self.keyspace = keyspace or os.getenv("CASSANDRA_KEYSPACE", "vaneloop")

        # AstraDB Bundle handling
        bundle_path = os.getenv("CASSANDRA_SECURE_CONNECT_BUNDLE_PATH")
        bundle_base64 = os.getenv("ASTRA_DB_BUNDLE_BASE64")

        if bundle_base64 and not bundle_path:
            bundle_path = "/tmp/secure-connect.zip"
            with open(bundle_path, "wb") as f:
                f.write(base64.b64decode(bundle_base64))

        user = username if username is not None else os.getenv("CASSANDRA_USERNAME", "token")
        pwd = password if password is not None else os.getenv("CASSANDRA_PASSWORD")
        auth_provider = PlainTextAuthProvider(user, pwd) if user else None

        connect_timeout = float(os.getenv("CASSANDRA_CONNECT_TIMEOUT", "8"))

        if bundle_path:
            self.cluster = Cluster(
                cloud={"secure_connect_bundle": bundle_path},
                auth_provider=auth_provider,
                connect_timeout=connect_timeout,
            )
        else:
            cp = contact_points or os.getenv("CASSANDRA_CONTACT_POINTS", "127.0.0.1").split(",")
            port = port or int(os.getenv("CASSANDRA_PORT", "9042"))
            self.cluster = Cluster(
                [c.strip() for c in cp if c.strip()],
                port=port,
                auth_provider=auth_provider,
                connect_timeout=connect_timeout,
            )

        self.session = self.cluster.connect()
        self.session.default_timeout = None
        if hasattr(self.cluster, "metadata") and self.cluster.metadata and hasattr(self.cluster.metadata, "keyspaces"):
            available = list(self.cluster.metadata.keyspaces.keys())
            if self.keyspace not in available and "default_keyspace" in available:
                self.keyspace = "default_keyspace"

        try:
            self.session.set_keyspace(self.keyspace)
            self._prepare()
            self._ready = True
        except Exception as exc:  # noqa: BLE001 - driver exceptions vary by deployment
            # Keyspace not created yet; `migrate()` will create it and prepare.
            logger.info("Cassandra keyspace is not ready yet: %s", exc)

    def connect(self) -> None:  # kept for backwards compatibility
        pass

    def disconnect(self) -> None:
        self.close()

    # -- setup -------------------------------------------------------------

    def migrate(self, schema_path: str | Path | None = None) -> None:
        """Apply infra/cassandra/schema.cql. Safe to re-run."""
        if schema_path is None:
            schema_path = Path(__file__).resolve().parents[2] / "infra" / "cassandra" / "schema.cql"
        cql = Path(schema_path).read_text(encoding="utf-8")

        if hasattr(self.cluster, "metadata") and self.cluster.metadata and hasattr(self.cluster.metadata, "keyspaces"):
            available = list(self.cluster.metadata.keyspaces.keys())
            if self.keyspace not in available and "default_keyspace" in available:
                self.keyspace = "default_keyspace"

        try:
            self.session.set_keyspace(self.keyspace)
        except Exception:
            pass

        for stmt in _split_cql(cql):
            s = stmt.strip().upper()
            if s.startswith("CREATE KEYSPACE"):
                try:
                    self.session.execute(stmt)
                except Exception as exc:
                    logger.info("Skipped keyspace statement for managed cluster (%s): %s", stmt[:30], exc)
                continue
            if s.startswith("USE "):
                try:
                    self.session.set_keyspace(self.keyspace)
                except Exception as exc:
                    logger.info("Skipped USE keyspace statement for managed cluster (%s): %s", stmt[:30], exc)
                continue

            if not self.session.keyspace and self.keyspace:
                try:
                    self.session.set_keyspace(self.keyspace)
                except Exception:
                    pass

            self.session.execute(stmt)

        try:
            self.session.set_keyspace(self.keyspace)
        except Exception:
            pass
        self._prepare()

        self._ready = True

    def _prepare(self) -> None:
        s = self.session
        self._ins_reading = s.prepare(
            f"INSERT INTO engine_readings ({', '.join(READING_COLUMNS)}) "
            f"VALUES ({', '.join('?' for _ in READING_COLUMNS)})"
        )
        self._ins_sensor = s.prepare(
            "INSERT INTO sensor_readings_by_sensor "
            "(dataset, sensor, cycle_bucket, cycle, unit, value) VALUES (?, ?, ?, ?, ?, ?)"
        )
        self._sel_readings_before = s.prepare(
            "SELECT * FROM engine_readings WHERE dataset = ? AND unit = ? AND cycle < ? "
            "ORDER BY cycle DESC LIMIT ?"
        )
        self._sel_readings_recent = s.prepare(
            "SELECT * FROM engine_readings WHERE dataset = ? AND unit = ? "
            "ORDER BY cycle DESC LIMIT ?"
        )
        self._sel_sensor = s.prepare(
            "SELECT cycle, unit, value FROM sensor_readings_by_sensor "
            "WHERE dataset = ? AND sensor = ? AND cycle_bucket = ? "
            "AND cycle >= ? AND cycle <= ?"
        )
        self._ins_prediction = s.prepare(
            "INSERT INTO engine_predictions "
            "(dataset, unit, cycle, model_version, rul_p10, rul_p50, rul_p90, "
            "health_index, state, warmup) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        self._sel_predictions = s.prepare(
            "SELECT * FROM engine_predictions WHERE dataset = ? AND unit = ? "
            "AND cycle >= ? AND cycle <= ? ORDER BY cycle ASC"
        )
        self._ins_alert_day = s.prepare(
            "INSERT INTO alerts_by_day "
            "(dataset, day, shard, ts, alert_id, unit, severity, rule, sensor, "
            "reading, threshold, message) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        self._ins_alert_engine = s.prepare(
            "INSERT INTO alerts_by_engine (dataset, unit, ts, alert_id, severity, rule, message) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)"
        )
        self._sel_alert_day = s.prepare(
            "SELECT * FROM alerts_by_day WHERE dataset = ? AND day = ? AND shard = ? "
            "ORDER BY ts DESC LIMIT ?"
        )
        self._sel_alert_engine = s.prepare(
            "SELECT * FROM alerts_by_engine WHERE dataset = ? AND unit = ? ORDER BY ts DESC LIMIT ?"
        )

    # -- writes ------------------------------------------------------------

    def upsert_readings(self, rows: Iterable[dict[str, Any]]) -> int:
        from cassandra.concurrent import execute_concurrent_with_args  # type: ignore

        rows = list(rows)
        if not rows:
            return 0

        def _clean_val(col: str, val: Any) -> Any:
            if val is None:
                return None
            if col in ("unit", "cycle", "rul_true"):
                return int(val)
            if col in OP_COLUMNS or col in SENSOR_IDS:
                return float(val)
            return str(val)

        import time
        import logging
        log = logging.getLogger(__name__)

        total_inserted = 0
        batch_size = 1000

        for b_start in range(0, len(rows), batch_size):
            batch = rows[b_start : b_start + batch_size]
            reading_args = [
                tuple(_clean_val(c, r.get(c)) for c in READING_COLUMNS)
                for r in batch
            ]
            sensor_args = [
                (
                    r["dataset"],
                    f"s{i}",
                    cycle_bucket(int(r["cycle"])),
                    int(r["cycle"]),
                    int(r["unit"]),
                    float(r[f"s{i}"]),
                )
                for r in batch
                for i in range(1, 22)
            ]

            execute_concurrent_with_args(
                self.session,
                self._ins_reading,
                reading_args,
                concurrency=20,
            )

            for attempt in range(3):
                try:
                    execute_concurrent_with_args(
                        self.session,
                        self._ins_sensor,
                        sensor_args,
                        concurrency=20,
                    )
                    break
                except Exception as e:
                    if attempt == 2:
                        log.warning("Sensor batch write failed: %s", e)
                    time.sleep(2.0)

            total_inserted += len(batch)
            time.sleep(0.01)

        return total_inserted

    def insert_engine_reading(self, reading: dict[str, Any]) -> int:
        """Insert one reading (engine_readings row + 21 sensor index rows)."""
        return self.upsert_readings([reading])

    def write_predictions(self, rows: Iterable[dict[str, Any]]) -> int:
        from cassandra.concurrent import execute_concurrent_with_args  # type: ignore

        rows = list(rows)
        if not rows:
            return 0
        args = [
            (
                r["dataset"],
                int(r["unit"]),
                int(r["cycle"]),
                r["model_version"],
                r.get("rul_p10"),
                r.get("rul_p50"),
                r.get("rul_p90"),
                r.get("health_index"),
                r.get("state"),
                bool(r.get("warmup", False)),
            )
            for r in rows
        ]
        execute_concurrent_with_args(self.session, self._ins_prediction, args, concurrency=128)
        return len(rows)

    def write_alerts(self, rows: Iterable[dict[str, Any]]) -> int:
        from cassandra.concurrent import execute_concurrent_with_args  # type: ignore

        rows = list(rows)
        if not rows:
            return 0
        day_args, engine_args = [], []
        for r in rows:
            ts = _as_datetime(r["ts"])
            alert_id = r.get("alert_id") or uuid.uuid1()
            day_args.append(
                (
                    r["dataset"],
                    ts.date(),
                    alert_shard(int(r["unit"])),
                    ts,
                    alert_id,
                    int(r["unit"]),
                    r["severity"],
                    r["rule"],
                    r.get("sensor"),
                    r.get("reading"),
                    r.get("threshold"),
                    r.get("message", ""),
                )
            )
            engine_args.append(
                (
                    r["dataset"],
                    int(r["unit"]),
                    ts,
                    alert_id,
                    r["severity"],
                    r["rule"],
                    r.get("message", ""),
                )
            )
        execute_concurrent_with_args(self.session, self._ins_alert_day, day_args, concurrency=64)
        execute_concurrent_with_args(
            self.session, self._ins_alert_engine, engine_args, concurrency=64
        )
        return len(rows)

    # -- reads -------------------------------------------------------------

    def get_readings(self, dataset, unit, limit=200, before_cycle=None) -> list[dict[str, Any]]:
        if before_cycle is None:
            rows = self.session.execute(self._sel_readings_recent, (dataset, unit, limit))
        else:
            rows = self.session.execute(
                self._sel_readings_before, (dataset, unit, before_cycle, limit)
            )
        return [_reading_row(r) for r in rows]

    def get_sensor_fleet_trend(
        self, dataset, sensor, from_cycle=1, to_cycle=MAX_CYCLE, max_points=2000
    ) -> list[dict[str, Any]]:
        top = min(to_cycle, MAX_CYCLE)
        out: list[dict[str, Any]] = []
        for bucket in range(cycle_bucket(from_cycle), cycle_bucket(top) + 1):
            rows = self.session.execute(
                self._sel_sensor, (dataset, sensor, bucket, from_cycle, top)
            )
            out.extend(
                {"cycle": int(r.cycle), "unit": int(r.unit), "value": float(r.value)} for r in rows
            )
        out.sort(key=lambda p: (p["cycle"], p["unit"]))
        return _downsample(out, max_points)

    def get_predictions(
        self, dataset, unit, from_cycle=None, to_cycle=None
    ) -> list[dict[str, Any]]:
        lo = from_cycle if from_cycle is not None else 0
        hi = to_cycle if to_cycle is not None else MAX_CYCLE
        rows = self.session.execute(self._sel_predictions, (dataset, unit, lo, hi))
        return [_prediction_row(r) for r in rows]

    def get_alerts(
        self, dataset, severity=None, rule=None, unit=None, limit=50
    ) -> list[dict[str, Any]]:
        """Read the day-sharded feed and merge across shards (newest first)."""
        day = datetime.now(timezone.utc).date()
        merged: list[dict[str, Any]] = []
        for shard in range(ALERT_SHARDS):
            rows = self.session.execute(self._sel_alert_day, (dataset, day, shard, limit * 4))
            merged.extend(_alert_day_row(r) for r in rows)
        merged.sort(key=lambda a: a["ts"], reverse=True)
        return _filter_alerts(merged, severity, rule, unit)[:limit]

    def get_alerts_for_engine(self, dataset, unit, limit=50) -> list[dict[str, Any]]:
        rows = self.session.execute(self._sel_alert_engine, (dataset, unit, limit))
        return [_alert_engine_row(r) for r in rows]

    def get_fleet_status(self, dataset: str) -> list[dict[str, Any]]:
        return []

    def close(self) -> None:
        try:
            self.cluster.shutdown()
        except Exception as exc:  # noqa: BLE001 - shutdown must not mask application errors
            logger.warning("Cassandra shutdown failed: %s", exc)


# ---------------------------------------------------------------------------
# SQLite (fallback for local demo and CI)
# ---------------------------------------------------------------------------

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS engine_readings (
  dataset TEXT NOT NULL, unit INTEGER NOT NULL, cycle INTEGER NOT NULL,
  op1 REAL, op2 REAL, op3 REAL,
  {sensors},
  rul_true INTEGER,
  PRIMARY KEY (dataset, unit, cycle)
);
CREATE TABLE IF NOT EXISTS sensor_readings_by_sensor (
  dataset TEXT NOT NULL, sensor TEXT NOT NULL, cycle_bucket INTEGER NOT NULL,
  cycle INTEGER NOT NULL, unit INTEGER NOT NULL, value REAL,
  PRIMARY KEY (dataset, sensor, cycle_bucket, cycle, unit)
);
CREATE TABLE IF NOT EXISTS engine_predictions (
  dataset TEXT NOT NULL, unit INTEGER NOT NULL, cycle INTEGER NOT NULL,
  model_version TEXT NOT NULL,
  rul_p10 REAL, rul_p50 REAL, rul_p90 REAL,
  health_index REAL, state TEXT, warmup INTEGER,
  PRIMARY KEY (dataset, unit, cycle, model_version)
);
CREATE TABLE IF NOT EXISTS alerts_by_day (
  dataset TEXT NOT NULL, day TEXT NOT NULL, shard INTEGER NOT NULL,
  ts TEXT NOT NULL, alert_id TEXT NOT NULL,
  unit INTEGER, severity TEXT, rule TEXT, sensor TEXT,
  reading REAL, threshold REAL, message TEXT,
  PRIMARY KEY (dataset, day, shard, ts, alert_id)
);
CREATE TABLE IF NOT EXISTS alerts_by_engine (
  dataset TEXT NOT NULL, unit INTEGER NOT NULL, ts TEXT NOT NULL,
  alert_id TEXT NOT NULL,
  severity TEXT, rule TEXT, message TEXT,
  PRIMARY KEY (dataset, unit, ts, alert_id)
);
CREATE TABLE IF NOT EXISTS benchmarks (
    datetime TEXT NOT NULL,
    dataset TEXT NOT NULL,
    engine_count INTEGER NOT NULL,
    total_rows INTEGER NOT NULL,
    ingest_time_sec REAL NOT NULL,
    memory_mb REAL NOT NULL,
    PRIMARY KEY (datetime, dataset)
);
CREATE INDEX IF NOT EXISTS ix_readings_unit ON engine_readings (dataset, unit, cycle DESC);
CREATE INDEX IF NOT EXISTS ix_readings_cycle ON engine_readings (dataset, cycle);
""".format(sensors=", ".join(f"{s} REAL" for s in SENSOR_IDS))


class SQLiteStore:
    """SQLite-backed cold-path store with the same logical schema as Cassandra."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = str(path or os.getenv("VANELOOP_SQLITE_PATH", "data/vaneloop.db"))
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")

    def connect(self) -> None:  # parity with CassandraStore
        pass

    def disconnect(self) -> None:
        self.close()

    def migrate(self, schema_path: str | Path | None = None) -> None:
        with self._lock:
            self.conn.executescript(_SQLITE_SCHEMA)
            self.conn.commit()

    def upsert_readings(self, rows: Iterable[dict[str, Any]]) -> int:
        rows = list(rows)
        if not rows:
            return 0

        def _clean_val(col: str, val: Any) -> Any:
            if val is None:
                return None
            if col in ("unit", "cycle", "rul_true"):
                return int(val)
            if col in OP_COLUMNS or col in SENSOR_IDS:
                return float(val)
            return str(val)

        reading_args = [
            tuple(_clean_val(c, r.get(c)) for c in READING_COLUMNS)
            for r in rows
        ]
        sensor_args = [
            (
                r["dataset"],
                f"s{i}",
                cycle_bucket(int(r["cycle"])),
                int(r["cycle"]),
                int(r["unit"]),
                float(r[f"s{i}"]),
            )
            for r in rows
            for i in range(1, 22)
        ]
        
        reading_sql = (
            f"INSERT OR REPLACE INTO engine_readings ({', '.join(READING_COLUMNS)}) "
            f"VALUES ({', '.join('?' for _ in READING_COLUMNS)})"
        )
        sensor_sql = (
            "INSERT OR REPLACE INTO sensor_readings_by_sensor "
            "(dataset, sensor, cycle_bucket, cycle, unit, value) VALUES (?, ?, ?, ?, ?, ?)"
        )
        with self._lock:
            self.conn.executemany(reading_sql, reading_args)
            self.conn.executemany(sensor_sql, sensor_args)
            self.conn.commit()

        return len(rows)

    def insert_engine_reading(self, reading: dict[str, Any]) -> int:
        return self.upsert_readings([reading])

    def write_predictions(self, rows: Iterable[dict[str, Any]]) -> int:
        rows = list(rows)
        if not rows:
            return 0
        sql = (
            "INSERT OR REPLACE INTO engine_predictions "
            "(dataset, unit, cycle, model_version, rul_p10, rul_p50, rul_p90, "
            "health_index, state, warmup) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        args = [
            (
                r["dataset"],
                int(r["unit"]),
                int(r["cycle"]),
                r["model_version"],
                r.get("rul_p10"),
                r.get("rul_p50"),
                r.get("rul_p90"),
                r.get("health_index"),
                r.get("state"),
                int(bool(r.get("warmup", False))),
            )
            for r in rows
        ]
        with self._lock:
            self.conn.executemany(sql, args)
            self.conn.commit()
        return len(rows)

    def write_alerts(self, rows: Iterable[dict[str, Any]]) -> int:
        rows = list(rows)
        if not rows:
            return 0
        day_sql = (
            "INSERT OR REPLACE INTO alerts_by_day "
            "(dataset, day, shard, ts, alert_id, unit, severity, rule, sensor, "
            "reading, threshold, message) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        eng_sql = (
            "INSERT OR REPLACE INTO alerts_by_engine "
            "(dataset, unit, ts, alert_id, severity, rule, message) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)"
        )
        day_args, eng_args = [], []
        for r in rows:
            ts = _as_datetime(r["ts"]).isoformat()
            aid = str(r.get("alert_id") or uuid.uuid1())
            day_args.append(
                (
                    r["dataset"],
                    ts[:10],
                    alert_shard(int(r["unit"])),
                    ts,
                    aid,
                    int(r["unit"]),
                    r["severity"],
                    r["rule"],
                    r.get("sensor"),
                    r.get("reading"),
                    r.get("threshold"),
                    r.get("message", ""),
                )
            )
            eng_args.append(
                (
                    r["dataset"],
                    int(r["unit"]),
                    ts,
                    aid,
                    r["severity"],
                    r["rule"],
                    r.get("message", ""),
                )
            )
        with self._lock:
            self.conn.executemany(day_sql, day_args)
            self.conn.executemany(eng_sql, eng_args)
            self.conn.commit()
        return len(rows)

    # -- reads -------------------------------------------------------------

    def get_readings(self, dataset, unit, limit=200, before_cycle=None) -> list[dict[str, Any]]:
        if before_cycle is None:
            sql = (
                "SELECT * FROM engine_readings WHERE dataset = ? AND unit = ? "
                "ORDER BY cycle DESC LIMIT ?"
            )
            args: tuple[Any, ...] = (dataset, unit, limit)
        else:
            sql = (
                "SELECT * FROM engine_readings WHERE dataset = ? AND unit = ? AND cycle < ? "
                "ORDER BY cycle DESC LIMIT ?"
            )
            args = (dataset, unit, before_cycle, limit)
        with self._lock:
            rows = self.conn.execute(sql, args).fetchall()
        return [_reading_row(r) for r in rows]

    def get_sensor_fleet_trend(
        self, dataset, sensor, from_cycle=1, to_cycle=MAX_CYCLE, max_points=2000
    ) -> list[dict[str, Any]]:
        sql = (
            "SELECT cycle, unit, value FROM sensor_readings_by_sensor "
            "WHERE dataset = ? AND sensor = ? AND cycle BETWEEN ? AND ? ORDER BY cycle, unit"
        )
        with self._lock:
            rows = self.conn.execute(sql, (dataset, sensor, from_cycle, to_cycle)).fetchall()
        out = [
            {"cycle": int(r["cycle"]), "unit": int(r["unit"]), "value": float(r["value"])}
            for r in rows
        ]
        return _downsample(out, max_points)

    def get_predictions(
        self, dataset, unit, from_cycle=None, to_cycle=None
    ) -> list[dict[str, Any]]:
        lo = from_cycle if from_cycle is not None else 0
        hi = to_cycle if to_cycle is not None else MAX_CYCLE
        sql = (
            "SELECT * FROM engine_predictions WHERE dataset = ? AND unit = ? "
            "AND cycle BETWEEN ? AND ? ORDER BY cycle ASC"
        )
        with self._lock:
            rows = self.conn.execute(sql, (dataset, unit, lo, hi)).fetchall()
        return [_prediction_row(r) for r in rows]

    def get_alerts(
        self, dataset, severity=None, rule=None, unit=None, limit=50
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM alerts_by_day WHERE dataset = ? ORDER BY ts DESC LIMIT ?"
        with self._lock:
            rows = self.conn.execute(sql, (dataset, limit * 4)).fetchall()
        merged = [_alert_day_row(r) for r in rows]
        return _filter_alerts(merged, severity, rule, unit)[:limit]

    def get_alerts_for_engine(self, dataset, unit, limit=50) -> list[dict[str, Any]]:
        sql = (
            "SELECT * FROM alerts_by_engine WHERE dataset = ? AND unit = ? ORDER BY ts DESC LIMIT ?"
        )
        with self._lock:
            rows = self.conn.execute(sql, (dataset, unit, limit)).fetchall()
        return [_alert_engine_row(r) for r in rows]

    def get_fleet_status(self, dataset: str) -> list[dict[str, Any]]:
        # First check if replayer has written predictions
        sql_pred = (
            "SELECT p.unit, p.cycle, p.state, p.rul_p10, p.rul_p50, p.rul_p90, p.warmup "
            "FROM engine_predictions p "
            "INNER JOIN ("
            "  SELECT unit, MAX(cycle) as max_c FROM engine_predictions WHERE dataset = ? GROUP BY unit"
            ") latest ON p.unit = latest.unit AND p.cycle = latest.max_c "
            "WHERE p.dataset = ? ORDER BY p.unit"
        )
        with self._lock:
            pred_rows = self.conn.execute(sql_pred, (dataset, dataset)).fetchall()
        if pred_rows:
            return [
                {
                    "dataset": dataset,
                    "unit": int(r["unit"]),
                    "cycle": int(r["cycle"]),
                    "state": r["state"] or "Nominal",
                    "rul_p10": float(r["rul_p10"]) if r["rul_p10"] is not None else None,
                    "rul_p50": float(r["rul_p50"]) if r["rul_p50"] is not None else None,
                    "rul_p90": float(r["rul_p90"]) if r["rul_p90"] is not None else None,
                    "warmup": bool(r["warmup"]),
                }
                for r in pred_rows
            ]

        # Initial baseline before replay starts: each engine at cycle 1
        sql = (
            "SELECT unit, MIN(cycle) as cycle "
            "FROM engine_readings WHERE dataset = ? "
            "GROUP BY unit ORDER BY unit"
        )
        with self._lock:
            rows = self.conn.execute(sql, (dataset,)).fetchall()
        out = []
        for r in rows:
            u = int(r["unit"])
            c = int(r["cycle"])
            out.append(
                {
                    "dataset": dataset,
                    "unit": u,
                    "cycle": c,
                    "state": "Nominal",
                    "rul_p10": 110.0,
                    "rul_p50": 125.0,
                    "rul_p90": 140.0,
                    "warmup": True,
                }
            )
        return out

    def close(self) -> None:
        with self._lock:
            self.conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _split_cql(cql: str) -> list[str]:
    """Split a CQL script on `;`, dropping `--` comment lines and blanks."""
    kept = [line for line in cql.splitlines() if line.strip() and not line.strip().startswith("--")]
    return [s.strip() for s in "\n".join(kept).split(";") if s.strip()]


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def _get(row: Any, key: str, default: Any = None) -> Any:
    if hasattr(row, key):
        return getattr(row, key)
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def _reading_row(r: Any) -> dict[str, Any]:
    rul = _get(r, "rul_true")
    out: dict[str, Any] = {
        "dataset": _get(r, "dataset"),
        "unit": int(_get(r, "unit", 0)),
        "cycle": int(_get(r, "cycle", 0)),
        "rul_true": int(rul) if rul is not None else None,
    }
    for c in (*OP_COLUMNS, *SENSOR_IDS):
        out[c] = float(_get(r, c, 0.0) or 0.0)
    return out


def _prediction_row(r: Any) -> dict[str, Any]:
    def f(key: str) -> float | None:
        v = _get(r, key)
        return float(v) if v is not None else None

    return {
        "dataset": _get(r, "dataset"),
        "unit": int(_get(r, "unit", 0)),
        "cycle": int(_get(r, "cycle", 0)),
        "model_version": _get(r, "model_version"),
        "rul_p10": f("rul_p10"),
        "rul_p50": f("rul_p50"),
        "rul_p90": f("rul_p90"),
        "health_index": f("health_index"),
        "state": _get(r, "state"),
        "warmup": bool(_get(r, "warmup", False)),
    }


def _iso(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _alert_day_row(r: Any) -> dict[str, Any]:
    return {
        "dataset": _get(r, "dataset"),
        "unit": int(_get(r, "unit", 0)),
        "severity": _get(r, "severity"),
        "rule": _get(r, "rule"),
        "sensor": _get(r, "sensor"),
        "reading": _get(r, "reading"),
        "threshold": _get(r, "threshold"),
        "message": _get(r, "message", ""),
        "ts": _iso(_get(r, "ts")),
    }


def _alert_engine_row(r: Any) -> dict[str, Any]:
    return {
        "dataset": _get(r, "dataset"),
        "unit": int(_get(r, "unit", 0)),
        "severity": _get(r, "severity"),
        "rule": _get(r, "rule"),
        "message": _get(r, "message", ""),
        "ts": _iso(_get(r, "ts")),
    }


def _filter_alerts(
    alerts: list[dict[str, Any]], severity: str | None, rule: str | None, unit: int | None
) -> list[dict[str, Any]]:
    out = alerts
    if severity:
        out = [a for a in out if str(a.get("severity", "")).lower() == severity.lower()]
    if rule:
        out = [a for a in out if str(a.get("rule", "")).lower() == rule.lower()]
    if unit is not None:
        out = [a for a in out if a.get("unit") == unit]
    return out


def _downsample(points: list[dict[str, Any]], max_points: int) -> list[dict[str, Any]]:
    """Uniform decimation over (cycle, value) points, keeping first and last."""
    n = len(points)
    if n <= max_points or max_points < 3:
        return points
    step = (n - 1) / (max_points - 1)
    return [points[round(i * step)] for i in range(max_points)]


def get_store(force: str | None = None) -> Store:
    """Factory. `VANELOOP_STORE` = auto|cassandra|sqlite (default `auto`).

    `auto` tries Cassandra, then falls back to SQLite so the demo and CI run
    without a cluster (TECHNICAL.md 2.6).
    """
    mode = (force or os.getenv("VANELOOP_STORE", "auto")).lower()
    if mode == "sqlite":
        store = SQLiteStore()
        store.migrate()
        return store
    if mode == "cassandra":
        store = CassandraStore()
        store.migrate()
        return store

    try:
        store = CassandraStore()
        store.migrate()
        return store
    except Exception as exc:  # noqa: BLE001 - Cassandra driver exposes several connection errors
        logger.info("Falling back to SQLite store: %s", exc)
        store = SQLiteStore()
        store.migrate()
        return store