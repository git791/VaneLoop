CREATE KEYSPACE IF NOT EXISTS vaneloop
  WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

USE vaneloop;

-- Q1: full/recent history for one engine (newest first)
CREATE TABLE IF NOT EXISTS engine_readings (
  dataset text, unit int, cycle int,
  op1 double, op2 double, op3 double,
  s1 double, s2 double, s3 double, s4 double, s5 double, s6 double, s7 double,
  s8 double, s9 double, s10 double, s11 double, s12 double, s13 double,
  s14 double, s15 double, s16 double, s17 double, s18 double, s19 double,
  s20 double, s21 double,
  rul_true int,
  PRIMARY KEY ((dataset, unit), cycle)
) WITH CLUSTERING ORDER BY (cycle DESC);

-- Q2: one sensor across the fleet for a cycle range
CREATE TABLE IF NOT EXISTS sensor_readings_by_sensor (
  dataset text, sensor text, cycle_bucket int,
  cycle int, unit int, value double,
  PRIMARY KEY ((dataset, sensor, cycle_bucket), cycle, unit)
);

-- Q3: RUL predictions over an engine's life
CREATE TABLE IF NOT EXISTS engine_predictions (
  dataset text, unit int, cycle int, model_version text,
  rul_p10 float, rul_p50 float, rul_p90 float,
  health_index float, state text, warmup boolean,
  PRIMARY KEY ((dataset, unit), cycle, model_version)
) WITH CLUSTERING ORDER BY (cycle DESC, model_version ASC);

-- Q4: alert feed, newest first
CREATE TABLE IF NOT EXISTS alerts_by_day (
  dataset text, day date, shard int, ts timestamp, alert_id timeuuid,
  unit int, severity text, rule text, sensor text,
  reading double, threshold double, message text,
  PRIMARY KEY ((dataset, day, shard), ts, alert_id)
) WITH CLUSTERING ORDER BY (ts DESC, alert_id ASC)
  AND default_time_to_live = 7776000;

-- Q5: alerts for one engine
CREATE TABLE IF NOT EXISTS alerts_by_engine (
  dataset text, unit int, ts timestamp, alert_id timeuuid,
  severity text, rule text, message text,
  PRIMARY KEY ((dataset, unit), ts, alert_id)
) WITH CLUSTERING ORDER BY (ts DESC, alert_id ASC)

CREATE TABLE IF NOT EXISTS benchmarks (
    datetime timestamp,
    dataset text,
    engine_count int,
    total_rows int,
    ingest_time_sec float,
    query_time_sec float,
    memory_mb float,
    cpu_load float,
    PRIMARY KEY (datetime, dataset)
);
  AND default_time_to_live = 7776000;
