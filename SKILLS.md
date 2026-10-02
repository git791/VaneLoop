# SKILLS.md — VaneLoop agent skills

Reusable, task-specific procedures for coding agents. Format follows the open [Agent Skills specification](https://agentskills.io/specification): each skill is a folder with a `SKILL.md` (YAML frontmatter with `name` + `description`, then Markdown instructions). Agents read only name/description at startup and load the body when a task matches (progressive disclosure).

`AGENTS.md` holds always-on rules. These skills hold procedures that are only needed sometimes.

## How to install

This file is a **bundle** for easy review. To use the skills, split each block below into its own folder:

```
.agents/skills/
├── cmapss-data-ingest/SKILL.md
├── rul-model-train-eval/SKILL.md
├── cassandra-schema-change/SKILL.md
├── api-contract-change/SKILL.md
├── fleet-ui-component/SKILL.md
├── alert-rule-tuning/SKILL.md
└── benchmark-run/SKILL.md
```

Each folder name must equal the `name` in its frontmatter. Keep each `SKILL.md` under 500 lines; move long reference material to a `references/` subfolder. Validate with `skills-ref validate ./.agents/skills/<name>` if you use the reference tooling. Claude Code looks in `.claude/skills/`; symlink it to `.agents/skills/` if needed.

## Catalog

| Skill | Use when |
|---|---|
| `cmapss-data-ingest` | Downloading, parsing, validating or loading C-MAPSS data |
| `rul-model-train-eval` | Training, evaluating, calibrating or exporting RUL models |
| `cassandra-schema-change` | Adding/changing any Cassandra table or query |
| `api-contract-change` | Changing REST/SSE endpoints or response shapes |
| `fleet-ui-component` | Building or editing dashboard UI |
| `alert-rule-tuning` | Changing status thresholds or alert rules |
| `benchmark-run` | Running or reporting Redis vs Cassandra benchmarks |

---

## 1. cmapss-data-ingest

~~~markdown
---
name: cmapss-data-ingest
description: Download, validate, parse and load NASA C-MAPSS turbofan data (FD001-FD004) into VaneLoop storage. Use when adding a dataset, fixing ingestion, rebuilding the Cassandra/Redis state, or when column names, sensor selection, RUL labels or checksums are involved.
metadata:
  version: "1.0"
  scope: data
---

# C-MAPSS ingestion

## Source and checksums
- Source of truth: NASA zip `https://data.nasa.gov/docs/legacy/CMAPSSData.zip` (landing page: data.nasa.gov/dataset/cmapss-jet-engine-simulated-data).
- The Kaggle mirror (bishals098) is a convenience copy. Verify file checksums against the NASA zip before trusting it.
- Download into `data/raw/` (gitignored) via `scripts/fetch_data.py`; store SHA-256 values in `data/CHECKSUMS.txt`.
- NASA lists the license as "not specified". Never commit the raw zip. Keep the PHM08 citation (Saxena et al., 2008) in docs.

## Parsing
1. Files: `train_FDxxx.txt`, `test_FDxxx.txt`, `RUL_FDxxx.txt`; whitespace-separated, no header, trailing spaces. Use `pandas.read_csv(sep=r"\s+", header=None)`.
2. Columns (26): `unit, cycle, op1, op2, op3, s1..s21`. There are 21 sensors despite the NASA page text saying "26".
3. Assert: expected row/engine counts per subset (FD001 train 100 engines), `cycle` strictly increasing from 1 within each unit, no NaNs.

## Labels
- Train RUL = `max_cycle(unit) - cycle`. Training target is `min(RUL, 125)`.
- Test: the last cycle of each unit gets `rul_true` from `RUL_FDxxx.txt`; earlier rows have null. Do not cap true test labels when scoring.

## Feature selection
- Compute per-dataset sensor variance; drop (near-)constant sensors. For FD001 this yields s2,3,4,7,8,9,11,12,13,14,15,17,20,21.
- For FD002/FD004, normalize within the six operating regimes (k-means on op1..op3, k=6) before judging variance. Persist choices in `config/features.yaml`; do not hard-code lists elsewhere.

## Loading
- Write through the `Store` interface, not raw CQL in scripts.
- Each reading is written to both `engine_readings` and `sensor_readings_by_sensor` (bucket = `cycle // 50`). Use async prepared statements with a concurrency cap; no multi-partition logged batches.
- Writes must be idempotent (same primary key upserts). Re-running ingest must not duplicate or change counts.
- After loading, run `vaneloop rebuild-cache` and assert Redis `fleet:counts` sum == number of engines.

## Verify before finishing
- `uv run pytest tests/ingest -q`
- Row counts in Cassandra == parsed counts; spot-check one engine's first/last cycle.
~~~

---

## 2. rul-model-train-eval

~~~markdown
---
name: rul-model-train-eval
description: Train, evaluate, calibrate and export Remaining Useful Life (RUL) models for C-MAPSS in VaneLoop. Use when changing model architecture, features, windowing, RUL capping, prediction intervals, metrics (RMSE, NASA score, coverage), or ONNX export, or when model results look too good.
metadata:
  version: "1.0"
  scope: ml
---

# RUL model training & evaluation

## Non-negotiables
- **Split by engine**, never by row (GroupKFold / group shuffle). A test asserts zero unit overlap between train and validation.
- Fit scalers/clusterers on train engines only; persist them with the model.
- Evaluate on the official test set at the **last cycle of each test engine** against `RUL_FDxxx.txt`.
- Report mean ± std over at least 5 seeds. Pin seeds and log the dataset checksum.
- Suspiciously low error (e.g. RMSE far below published FD001 results) means leakage until proven otherwise. Check windows crossing engine boundaries, scaler fit scope and label leakage first.

## Pipeline
1. Preprocess (see `cmapss-data-ingest`): selected sensors, regime normalization if needed, capped target (125).
2. Windows: length 30, stride 1, per engine only. Left-pad the first 29 cycles by repeating the first row and mark `warmup=true`.
3. Baseline first: gradient boosting on rolling stats. Then CNN/GRU. A new model is accepted only if it beats the previous best on engine-level cross-validation, not just on test.
4. Uncertainty: quantile heads (p10/p50/p90, pinball loss) with split-conformal calibration on held-out engines, or a 5-model ensemble. Report 80% interval coverage; target 75-85%.

## Metrics
- RMSE on last-cycle predictions.
- NASA score, with `d = pred - true`: sum over engines of `exp(-d/13) - 1` if `d < 0`, else `exp(d/10) - 1`.
- Coverage of the p10-p90 band.
- Alerting metrics are produced by the `alert-rule-tuning` skill.

## Export
- Export ONNX; test numerical parity vs the training framework (max abs diff < 1e-4).
- Write bundle: `model.onnx, scaler.json, features.yaml, metrics.json, model_card.md, version` where version = semver + git SHA + data checksum.
- Update `model_card.md`: architecture, data, preprocessing, metrics, limitations (simulated data, 125 cap, single fault mode in FD001).
- Bump the model version; the API exposes it at `/api/v1/meta/model` and the UI shows it.

## Verify
`make train && make eval` reproduces `metrics.json` within tolerance; `uv run pytest tests/ml -q` passes.
~~~

---

## 3. cassandra-schema-change

~~~markdown
---
name: cassandra-schema-change
description: Add or modify Cassandra tables, queries or partition/clustering keys in VaneLoop. Use for any new endpoint that needs historical data, any CQL change, partition sizing questions, TTL or compaction decisions, or schema migrations.
metadata:
  version: "1.0"
  scope: storage
---

# Cassandra schema changes

## Rules
1. **Query first.** Write the exact query the endpoint needs, then design the table around it. One query pattern -> one table. Denormalize deliberately.
2. Never use `ALLOW FILTERING`, secondary indexes on high-cardinality columns, or full-table scans.
3. Partition key must bound partition size. Estimate rows per partition at 100, 1,000 and 10,000 engines; keep partitions well under ~100 MB / ~100k rows. Add a bucket or shard to the key when a partition grows with fleet size or time.
4. Clustering order matches the dominant read (newest first -> `CLUSTERING ORDER BY (cycle DESC)`).
5. Prepared statements only. No string-built CQL.
6. Append-only, expiring data (alerts) gets a TTL and is a candidate for `TimeWindowCompactionStrategy`.
7. Avoid multi-partition logged batches for throughput. Use async writes with a concurrency cap.

## Procedure
1. Document the query, expected cardinality, and chosen keys in the PR description or an ADR.
2. Add a numbered migration `infra/cassandra/migrations/NNN_description.cql`; never edit an applied migration.
3. Update the `Store` interface and both implementations (Cassandra and SQLite/Parquet fallback).
4. Add a repository test with Testcontainers: write, read, ordering, pagination and TTL where relevant.
5. If a table is added, update the ingest/replayer write path so it is populated, and the rebuild-cache command if Redis depends on it.
6. Update `docs/TECHNICAL.md` §4 query -> table map.

## Ask the human first
Dropping a table, changing a primary key of an existing table (requires a backfill), or changing replication settings.
~~~

---

## 4. api-contract-change

~~~markdown
---
name: api-contract-change
description: Change VaneLoop REST or SSE endpoints, request/response schemas, pagination, or error formats, and keep the OpenAPI contract, generated TypeScript types, and frontend in sync. Use whenever a field is added/renamed/removed or an endpoint is created.
metadata:
  version: "1.0"
  scope: api
---

# API contract changes

## Principle
OpenAPI (`api/openapi.json`) is the contract. Server code and frontend types derive from it, not the other way round.

## Procedure
1. Edit Pydantic models / routes in `api/`. Keep routes under `/api/v1`.
2. Regenerate the spec: `uv run python -m app.export_openapi > api/openapi.json`.
3. Regenerate frontend types: `cd frontend && npm run gen:api` (openapi-typescript).
4. Update the thin client in `frontend/lib/api/` and the Zod schemas if used.
5. Update MSW handlers/fixtures. Fixtures must be sampled from real FD001 rows, not invented numbers.
6. Update affected components, including loading/empty/error/stale states.
7. Run contract tests (`uv run pytest tests/contract`, Schemathesis) and `npm test`.

## Conventions
- Engine path params are `(dataset, unit)`. Display ID `FD001-023` is derived in one helper on each side.
- Lists use keyset pagination (`before_cycle`, `before` timestamp), never offset.
- Errors use RFC 9457 problem details.
- Validate `dataset` and `sensor` against allow-lists.
- SSE events: `tick`, `status_change`, `alert`, `heartbeat`. Never drop `alert` or `status_change` under backpressure.
- Additive changes are fine. Renames/removals are breaking: add the new field, deprecate the old, remove in a later release, and say so in the PR.

## Done when
OpenAPI drift check passes in CI, generated types are committed, and no component reads a field that is not in the spec.
~~~

---

## 5. fleet-ui-component

~~~markdown
---
name: fleet-ui-component
description: Build or modify VaneLoop dashboard UI (fleet grid, engine tiles, charts, tables, alerts, badges, themes) in the Next.js frontend. Use for any visual or interaction change, status colors, accessibility, chart work, or dark/light theme tweaks.
metadata:
  version: "1.0"
  scope: frontend
---

# Fleet UI components

## Design language
"Instrument-panel minimalism": structural grids, monospace readouts (`tabular-nums`), aviation-style palette. Two themes: Glass Cockpit Dark and Skyline Day. Use theme tokens (CSS variables); no raw hex in components.

## Status
- States: Nominal, Warning, Critical (plus "warming up").
- Never color alone: pair color with icon/shape and text (circle / triangle / square).
- Contrast meets WCAG 2.2 AA in both themes; check with axe.

## Data and state
- Server components by default. `"use client"` only for charts, SSE, theme and filters.
- Initial data is fetched on the server; live updates via the `useFleetStream` hook merging into the TanStack Query cache.
- Zustand holds UI state only (theme, selected sensors, window, filters).
- Components never contain engine data, counts, alerts or latency numbers. All come from the API.

## Required states for every data view
loading (skeleton), empty, error (with retry), stale (connection badge: live / reconnecting / stale), warming up. Replace any bare "LIVE" label with the connection state and a "Simulated data" note.

## Charts
- Recharts is fine for a few thousand points; downsample server-side beyond that. Consider uPlot if profiling shows jank.
- Show RUL as p50 with a p10-p90 band; show "≥ 125" when capped.
- Provide a table alternative and meaningful `aria-label`s.
- Respect `prefers-reduced-motion`.

## Verify
`npm run lint && npm run typecheck && npm test`; Playwright smoke (Fleet -> Engine -> Alerts); axe check; screenshots at 360 px and 1280 px in the PR.
~~~

---

## 6. alert-rule-tuning

~~~markdown
---
name: alert-rule-tuning
description: Change or evaluate VaneLoop status thresholds and alert rules (status transitions, per-engine sensor drift, RUL slope), including hysteresis and debouncing. Use when alerts are noisy, late, or missing, or when thresholds in policy.py change.
metadata:
  version: "1.0"
  scope: policy
---

# Alert rule tuning

## Rules in play (api/app/policy.py)
- Status: Critical if RUL p10 <= 30; Warning if p50 <= 70 or p10 <= 50; else Nominal. Downgrade requires 3 consecutive cycles. These are product assumptions, not dataset facts.
- R1 transition alert: on upward state change.
- R2 sensor drift: per-engine baseline (cycles 1-20), EWMA (lambda ~0.2), alert when |z| > 3 for 5 consecutive cycles. Operates on regime-normalized values for FD002/FD004.
- R3 RUL slope (P1).
- Debounce: at most one alert per (engine, rule) per 5 cycles.

## Why per-engine baselines
NASA states each engine starts with different, unknown, normal wear. Fleet-wide absolute thresholds (e.g. "T50 > 1600") misfire on engines that simply started high.

## Procedure
1. Replay the **train set to failure** with the candidate configuration (`uv run vaneloop eval-alerts --dataset FD001 --config <path>`).
2. Compute: median lead time (cycles before failure) of the first Critical; false Critical per engine lifetime; alerts per engine per 100 cycles.
3. Compare to targets (PRD §4): lead time >= 30 cycles, false Critical <= 0.2 per lifetime.
4. Because late detection is costlier than early detection, prefer errors toward earlier alerts; document the trade-off.
5. Add or update unit tests for edge cases: warm-up, hysteresis flapping, regime changes, engines that fail immediately.
6. Record results in the PR (table of before/after). Do not tune on test labels.

## Ask the human first
Changing default thresholds shipped to users, or removing a rule.
~~~

---

## 7. benchmark-run

~~~markdown
---
name: benchmark-run
description: Run, extend or report the VaneLoop Redis-cached vs direct-Cassandra benchmarks and update the Benchmark page data. Use when performance numbers, latency claims, scale scenarios or the benchmarks/ directory are involved.
metadata:
  version: "1.0"
  scope: benchmark
---

# Benchmarks

## Rule zero
No hand-typed numbers. The Benchmark page renders only committed result files from `benchmarks/results/*.json`. If a number cannot be traced to a run, delete it.

## Scenarios
- S1 Fleet status at N = 100 / 1,000 / 10,000 engines: `GET /fleet` (Redis) vs reading latest status per engine from Cassandra.
- S2 Engine history (200 rows): `GET /readings`.
- S3 Sensor fleet trend: `GET /fleet-trend`.
- S4 Ingest throughput with and without cache update.
Synthetic scale-up data: resample real trajectories with noise; label it synthetic in results and UI.

## Method
1. Fresh stack: `docker compose -f infra/docker-compose.yml up -d`; seed data; record container CPU/memory limits.
2. Warm-up run, then >= 1,000 timed requests per scenario at concurrency 1, 16 and 64 (k6 or Locust).
3. Run cold-cache and warm-cache variants.
4. Output JSON with p50/p95/p99, error rate, throughput, hardware, software versions (Cassandra, Redis, Python, Node), dataset scale, git SHA and timestamp.
5. Commit the result file; the page reads `/api/v1/benchmark/latest`.

## Reporting
State what was measured, on what hardware, at what scale. Do not extrapolate ("scales infinitely") beyond tested scales. If Redis does not win in a scenario, report that.

## CI
A scheduled workflow runs the quick profile and uploads an artifact; full runs are manual.
~~~
