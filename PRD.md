# VaneLoop — Product Requirements Document

| | |
|---|---|
| **Version** | 1.0 (draft) |
| **Date** | 2026-10-01 |
| **Status** | Proposed |
| **Product** | VaneLoop — Aircraft Engine Health Monitoring & RUL Prognostics |
| **Live (frontend only)** | https://vane-loop.vercel.app |
| **Repo** | https://github.com/git791/VaneLoop |
| **Dataset** | NASA C-MAPSS (FD001–FD004) — [NASA Open Data](https://data.nasa.gov/dataset/cmapss-jet-engine-simulated-data), [Kaggle mirror](https://www.kaggle.com/datasets/bishals098/nasa-turbofan-engine-degradation-simulation) |

> **Safety disclaimer (product-level requirement):** VaneLoop runs on *simulated* data. It is a demonstration and learning platform. It must never be presented as, or used for, airworthiness or maintenance-release decisions.

---

## 1. Summary

VaneLoop is a fleet-level dashboard that shows which turbofan engines are healthy, which are degrading, and how many flight cycles each has left (Remaining Useful Life, RUL). It is built on NASA's C-MAPSS run-to-failure simulation data and is designed around a two-path data architecture: a cold path (Cassandra, full history) and a hot path (Redis, current state).

**Where it is today (v0.1):** a Next.js frontend with four views (Fleet, Engine detail, Alerts, Benchmark). There is no backend, no model and no real dataset behind it yet — see §2.

**Where it needs to go (v1.0):** a working end-to-end system — real C-MAPSS data, a trained RUL model with uncertainty, a replay-driven "live" stream, honest alerting, and a benchmark page that shows *measured* numbers.

## 2. Current state & gaps (audit of v0.1)

Audit method: rendered pages of the live site plus the repo README. I could not read the `frontend/` source (GitHub blocked automated access), so findings below come from what the site displays. Please verify against the code.

| # | Observation | Why it matters |
|---|---|---|
| G1 | Fleet shows **24 engines** (15 nominal / 5 warning / 4 critical); README describes a **100-tile** fleet. | Inconsistent; FD001 has 100 train engines. |
| G2 | Alerts feed lists `FD001-042`, `-067`, `-099`, which are not in the fleet grid. | Alerts are hard-coded, not derived from fleet state. |
| G3 | Engine `FD001-001` readings table reaches **cycle 199**, but its fleet tile says **Cycle 89**. To my knowledge FD001 train unit 1 has 192 cycles. | Tile and detail views read from different (generated) sources. |
| G4 | Displayed values look generated: T50 ≈ 1,600 and P30 ≈ 38. In real FD001, T50 (sensor 4) is roughly 1,400 °R and P30 (sensor 7) roughly 550 psia. | The UI is not showing real C-MAPSS data. |
| G5 | Header shows a **LIVE** badge on static data. | Misleading; C-MAPSS has no wall-clock timestamps. |
| G6 | README calls `Nf` "Core Speed". `Nf` is physical **fan** speed; core speed is `Nc`. | Domain accuracy. |
| G7 | README claims ~12 ms (Cassandra) and ~8 ms (Redis) latencies; no backend is deployed. | Performance claims must be measured and reproducible. |
| G8 | Alerts use absolute fleet-wide thresholds (e.g. T50 > 1600). | NASA states each engine starts with different, unknown initial wear that is "normal." Per-engine baselines are needed. |
| G9 | NASA dataset page lists license as "not specified." | Add attribution and a data-provenance note. |

## 3. Users & jobs-to-be-done

| Persona | Needs | Primary views |
|---|---|---|
| **Maintenance / Fleet Manager** ("Marta") | "Show me what needs attention this week; tell me if I can defer." Triage in under a minute. | Fleet, Alerts |
| **Reliability / Condition-monitoring Engineer** ("Dev") | "Why is this engine flagged? Which sensors drifted? How confident is the RUL?" | Engine detail, Model card |
| **Builder / Reviewer** (developer, hiring manager, student) | "Does this demonstrate sound NoSQL modeling, streaming, and ML engineering?" | Benchmark, Data & Model pages, README |

## 4. Goals, non-goals, success metrics

### Goals
1. Replace all mock data with real C-MAPSS data served by a real API.
2. Provide RUL predictions **with uncertainty**, and derive status (Nominal / Warning / Critical) from them transparently.
3. Deliver a replay-based live experience (SSE) so the Fleet and Alerts views update without a refresh.
4. Make the Cassandra + Redis design *demonstrably* justified through reproducible benchmarks.
5. Be honest in the UI: label simulated data, show model version, show data staleness.

### Non-goals (v1.0)
- Real-time ingestion from physical aircraft or ACARS/ADS-B feeds.
- Airworthiness, regulatory, or maintenance-release functionality.
- Multi-tenant auth, billing, or RBAC beyond a single read-only demo role (+ one admin token for benchmark runs).
- Training on N-C-MAPSS (candidate for v2).

### Success metrics (proposed targets — calibrate after baseline)

| Area | Metric | Target |
|---|---|---|
| Data integrity | Fleet counts, tiles, detail and alerts all derive from one source | 100% (automated consistency test) |
| Model (FD001 test, last-cycle eval) | RMSE | ≤ 16 baseline, ≤ 13 stretch |
| Model | NASA asymmetric score | Tracked per release; must not regress > 5% |
| Model | 80% prediction-interval coverage | 75–85% |
| Early warning (train-set replay) | Median lead time of first Critical before failure | ≥ 30 cycles |
| Early warning | False Critical alerts per engine lifetime | ≤ 0.2 |
| Performance | Fleet view API p95 (hot path, 100 engines) | < 100 ms |
| Performance | Engine history API p95 (cold path, 200 rows) | < 150 ms |
| Frontend | Lighthouse performance / accessibility | ≥ 90 / ≥ 95 |
| Credibility | Benchmark page numbers reproducible from `benchmarks/` in CI | Yes |

## 5. Functional requirements

Priority: **P0** = required for v1.0, **P1** = should have, **P2** = nice to have.

### 5.1 Fleet Overview (`/`)
| ID | Requirement | Pri |
|---|---|---|
| F-1 | Show one tile per engine in the selected dataset (FD001 → 100). Tile: ID, current cycle, status, RUL (p50) and mini sparkline of health index. | P0 |
| F-2 | Summary counters (Nominal / Warning / Critical) computed server-side from the same data as the tiles. | P0 |
| F-3 | Filter by status; sort by RUL ascending (default), ID, or cycle. | P0 |
| F-4 | Dataset switcher (FD001–FD004); FD002/FD004 show the six-operating-condition note. | P1 |
| F-5 | Tiles update live via SSE; status changes animate once, respect `prefers-reduced-motion`. | P1 |
| F-6 | "Simulated data · replay at Nx" banner replaces the unconditional LIVE badge. Stale-state badge if no tick for > 10 s. | P0 |

### 5.2 Engine Detail (`/engine/[id]`)
| ID | Requirement | Pri |
|---|---|---|
| E-1 | Header: engine ID, dataset, current cycle, status, RUL p50 with p10–p90 band. | P0 |
| E-2 | Sensor trend chart with selector for the 14 informative sensors; overlays the engine's own baseline band. | P0 |
| E-3 | RUL trajectory chart (predicted RUL vs. cycle with uncertainty band; true RUL line shown for train/test-labelled replay). | P0 |
| E-4 | Recent readings table (cycle-descending; paginated; shows op settings + sensors; status per row). | P0 |
| E-5 | "Why flagged": top contributing sensors (per-sensor deviation from engine baseline and/or model attribution). | P1 |
| E-6 | Partition/query info panel (`partition: engine_id = …` and measured query time) retained as a teaching aid. | P2 |

### 5.3 Alerts (`/alerts`)
| ID | Requirement | Pri |
|---|---|---|
| A-1 | Chronological feed of alerts from the replay clock: severity, engine, rule, sensor/reading/threshold (when sensor-based), time. | P0 |
| A-2 | Rules: status transition (R1), per-engine sensor drift (R2), RUL slope anomaly (R3). Each alert states which rule fired. | P0 (R1,R2) / P1 (R3) |
| A-3 | Filter by severity, engine, rule; deep link to the engine at the alert cycle. | P0 |
| A-4 | Debounce / hysteresis so one engine does not emit more than 1 alert per rule per 5 cycles. | P0 |
| A-5 | Acknowledge alert (single-user, persisted). | P2 |

### 5.4 Benchmark (`/benchmark`)
| ID | Requirement | Pri |
|---|---|---|
| B-1 | Display results from the latest committed benchmark run (JSON): p50/p95/p99 for Redis path vs Cassandra-direct, for fleet status, engine history, sensor fleet-trend. | P0 |
| B-2 | Show methodology, hardware, versions, run date and commit SHA next to the charts. | P0 |
| B-3 | Scale scenarios: 100, 1,000, 10,000 synthetic engines. Clearly labelled as synthetic. | P1 |
| B-4 | Admin-triggered re-run from the UI. | P2 |

### 5.5 Data & Model transparency (`/about`, `/model`) — new
| ID | Requirement | Pri |
|---|---|---|
| M-1 | Data page: dataset provenance, NASA citation, sensor glossary (name, units, what it measures), license caveat. | P0 |
| M-2 | Model card: architecture, training data, preprocessing, metrics (RMSE, score, coverage), known limitations, version, date. | P0 |
| M-3 | Disclaimer visible in footer on every page. | P0 |

### 5.6 Cross-cutting
| ID | Requirement | Pri |
|---|---|---|
| X-1 | Light (Skyline Day) and dark (Glass Cockpit Dark) themes persist per user. | P0 |
| X-2 | Status is never conveyed by color alone (add icon/shape + text). | P0 |
| X-3 | Every data view has loading, empty, error and stale states. | P0 |
| X-4 | Keyboard navigable; WCAG 2.2 AA contrast. | P0 |
| X-5 | Mobile layout usable at 360 px width for Fleet and Alerts. | P1 |

### 5.7 Stretch (v1.x, not committed)
- **Maintenance planner:** pick a window; list engines whose p10 RUL falls inside it; export CSV.
- **Grounded explainer:** a chat panel that answers questions about an engine using API tool calls only (no free-form claims), with the disclaimer always visible.
- **Cross-dataset generalization view:** train on FD001, evaluate on FD003 to show fault-mode shift.

## 6. Status policy (initial; tunable via config)

| State | Rule (applies to current cycle) |
|---|---|
| **Critical** | RUL p10 ≤ 30 cycles |
| **Warning** | not Critical, and (RUL p50 ≤ 70 or RUL p10 ≤ 50) |
| **Nominal** | otherwise |

- Downgrading severity requires 3 consecutive cycles under the lower state (hysteresis).
- During the first 30 cycles (model window warm-up) the UI shows "warming up" and defaults to Nominal.
- RUL is capped at 125 in training (piecewise-linear target); the UI shows "≥ 125" instead of fabricating precision above the cap.
- These thresholds are product assumptions, not dataset facts. Revisit with a cost model: late detection is far more costly than early detection (mirrors the asymmetry of NASA's scoring function).

## 7. UX principles

1. **Instrument-panel minimalism** (existing direction): monospace readouts, structural grids, aviation-style palette.
2. **Glanceable first, drill-down second:** the Fleet view answers "is anything wrong?" in under 5 seconds.
3. **Show uncertainty:** ranges and bands, never a bare point estimate.
4. **Honest labelling:** simulated, replayed, stale, warming up — all visible states.
5. **One source of truth:** counters, tiles, detail and alerts must agree.

## 8. Release plan

| Milestone | Scope | Exit criteria |
|---|---|---|
| **M0 — Truthfulness (≈1 wk)** | Fix G1–G9 in the frontend: remove LIVE claim, align counts, README corrections, add disclaimer and provenance. Introduce typed API client + MSW fixtures built from real FD001 rows. | No contradictions between views. |
| **M1 — Data & API (≈2 wk)** | Docker Compose (Cassandra, Redis, API). Ingest FD001. Endpoints for fleet, engine, readings, sensors. Frontend reads real API. | Fleet shows 100 real engines; contract tests green. |
| **M2 — Model (≈2 wk)** | Baseline (gradient boosting) then sequence model; intervals; ONNX export; model card. | Meets RMSE target on FD001 test. |
| **M3 — Live replay & alerts (≈2 wk)** | Replayer, SSE, status policy, alert rules R1–R2, alerts UI. | Early-warning metrics measured on train replay. |
| **M4 — Benchmark (≈1 wk)** | Load generator, JSON results, benchmark page reads results; CI job. | Numbers reproducible from a clean checkout. |
| **M5 — Breadth (≈2 wk)** | FD002–FD004, operating-condition normalization, "why flagged," a11y/perf pass. | Lighthouse targets met. |

## 9. Risks & mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Cassandra is oversized for ~20k rows (FD001 train) and may look like resume-driven design. | Credibility | State the thesis plainly; benchmark at synthetic scale; ship a lightweight storage adapter (SQLite/Parquet) so the demo runs without the cluster. |
| Vercel frontend cannot reach a local Cassandra. | Deploy blocked | Host API separately; use managed Cassandra-compatible and Redis services (verify current free tiers) or a small VM. |
| Overstated claims (LIVE, latencies, accuracy). | Trust | Measured-only policy; every number links to source/run. |
| Data leakage in evaluation (random row split). | Inflated metrics | Split by engine; scaler fit on train only; unit tests assert no unit overlap. |
| Misuse as a real maintenance tool. | Safety/reputation | Disclaimer on every page; README and model card limitations. |
| Dataset license unspecified on NASA page. | Legal ambiguity | Cite the PHM08 paper, link to source, don't redistribute the raw zip in the repo; download script with checksum. |
| Kaggle mirror may differ from the NASA zip. | Reproducibility | Treat NASA zip as source of truth; verify checksum. |

## 10. Open questions

1. Is Cassandra mandatory (course/portfolio constraint), or is a simpler store acceptable for the deployed demo?
2. Target audience priority: portfolio reviewers or domain users? (Affects how much weight M5 and the stretch items get.)
3. Which hosting budget applies for the API (free tier vs small VM)?
4. Should FD002/FD004 (six operating conditions) be in v1.0 or deferred?
5. Is the 3-state status model enough, or is a numeric Health Index (0–100) wanted on tiles?

## 11. References & inspiration

I searched GitHub and the wider web for related work. I did not find an existing project that combines C-MAPSS, a Next.js frontend and a Cassandra + Redis hot/cold design, so VaneLoop's niche is the production-style architecture around a well-studied dataset. Most related repos are notebook- or Streamlit-based.

| Resource | Why it is useful for VaneLoop |
|---|---|
| [nasa/progpy](https://github.com/nasa/progpy) — NASA's prognostics package (2024 NASA Software of the Year) | Vocabulary (events, state estimation, prediction), prognostics metrics, and a `prog_server` service-oriented pattern to compare our API against. |
| [tilman151/rul-datasets](https://pypi.org/project/rul-datasets) | Standardized C-MAPSS loaders; handy for experiments and to cross-check our ingestion. |
| [ozogxyz/cmapss](https://github.com/ozogxyz/cmapss) | PyTorch Lightning + Hydra experiment layout for config-driven training. |
| [lucadellalib/bayesian-deep-rul](https://github.com/lucadellalib/bayesian-deep-rul) | Bayesian vs. frequentist deep RUL; informs our uncertainty approach. |
| [LahiruJayasinghe/RUL-Net](https://github.com/LahiruJayasinghe/RUL-Net) | Deep RUL architectures; notes that training labels reach zero RUL while test labels need not. |
| [UtkarshPanara/Remaining-Useful-Life-Prediction-for-Turbofan-Engines](https://github.com/UtkarshPanara/Remaining-Useful-Life-Prediction-for-Turbofan-Engines) | CNN approach; discusses limiting RUL targets to roughly 120–130 cycles. |
| [mouradboutrid/TurboGuard](https://turboguard.readthedocs.io/en/latest/) | LSTM autoencoder + forecasting for anomaly detection; informs alert rule R3 and a Streamlit dashboard comparison. |
| [MrArod/Predictive-Maintenance](https://github.com/MrArod/Predictive-Maintenance) | KPI framing (MTTF, RUL, downtime cost), FastAPI + dashboard layout. |
| [SyedaArisha/predictive-maintenance-rag-system](https://huggingface.co/SyedaArisha/predictive-maintenance-rag-system) | FD001 sliding windows (30 steps), piecewise cap 125, RUL gauge UX; a RAG layer if we pursue the grounded-explainer stretch. |
| [Saxena et al., PHM08 — Damage Propagation Modeling](https://data.nasa.gov/dataset/cmapss-jet-engine-simulated-data) | The dataset's primary citation. |
| [Ramasso & Saxena — Performance Benchmarking and Analysis of Prognostic Methods for CMAPSS Datasets](https://ntrs.nasa.gov/archive/nasa/casi.ntrs.nasa.gov/20150007677.pdf) | Guidance for consistent comparison across approaches; use it to frame our metrics. |
| [Arias Chao et al. — N-C-MAPSS](https://www.research-collection.ethz.ch/server/api/core/bitstreams/0d42915a-d8d1-485d-8355-4c66449d1b3c/content) | Higher-fidelity successor dataset; v2 candidate. |
| [agents.md](https://agents.md) and [agentskills.io](https://agentskills.io/specification) | Formats used by the `AGENTS.md` and `SKILLS.md` companion files in this repo. |

## 12. Glossary

- **C-MAPSS:** Commercial Modular Aero-Propulsion System Simulation, NASA's turbofan simulator.
- **Cycle:** one flight/operational cycle; the dataset's time unit.
- **RUL:** Remaining Useful Life, in cycles, from the current cycle until failure.
- **HPC / LPC / LPT:** High-/Low-pressure compressor / Low-pressure turbine.
- **FD001–FD004:** the four sub-datasets (operating conditions × fault modes).
- **Hot / cold path:** Redis current-state reads / Cassandra historical reads.
