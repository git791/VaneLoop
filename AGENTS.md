# AGENTS.md

Instructions for AI coding agents working on VaneLoop. Humans: see `README.md` and `docs/`.
Claude Code reads `CLAUDE.md`, not this file: create `CLAUDE.md` containing the single line `@AGENTS.md`.

## What this is
VaneLoop is a turbofan fleet health dashboard on **simulated** NASA C-MAPSS data: RUL prediction, status, alerts, and a Cassandra-vs-Redis benchmark. Not for real maintenance decisions.
Specs: `docs/PRD.md` (what/why), `docs/TECHNICAL.md` (how). Read the relevant section before changing behavior.

## Layout
```
frontend/   Next.js 16 (App Router), React 19, Tailwind v4, shadcn/ui, Recharts, Zustand, TanStack Query
api/        FastAPI, Pydantic v2, store adapters (Cassandra, SQLite), policy, openapi.json   [planned]
replayer/   replay + ONNX inference loop                                                    [planned]
ml/         preprocessing, training, eval, configs                                          [planned]
infra/      docker-compose.yml, cassandra/schema.cql                                        [planned]
benchmarks/ scenarios + results/*.json                                                      [planned]
data/raw/   gitignored; fetched by script
```
Only `frontend/` exists today. Create planned directories as the roadmap (PRD §8) reaches them.

## Commands
```bash
# Frontend (from frontend/)
npm install && npm run dev
npm run lint && npm run typecheck && npm test && npm run build

# Backend (from repo root; uv + ruff + pytest)
uv sync
uv run ruff check . && uv run ruff format --check .
uv run pytest -q

# Local stack
docker compose -f infra/docker-compose.yml up -d
uv run vaneloop migrate && uv run vaneloop ingest --dataset FD001
```
Run lint, typecheck and the tests for what you touched before declaring work done. If a command is missing, say so; don't invent one.

## Rules of the road

**Always**
- Get every number shown in the UI from the API. Components never contain hard-coded engine data, counts, alerts or latencies.
- Keep one source of truth: Fleet counts, tiles, engine detail and alerts must agree.
- Label simulated/replayed data honestly. No bare "LIVE" badge; use the connection state (live / reconnecting / stale).
- Show uncertainty (RUL p10–p90) and never convey status by color alone (icon + text too).
- Handle loading, empty, error and stale states for every data view.
- Use TypeScript strict mode. Regenerate API types after changing `api/openapi.json`.
- Add or update tests with the change. Prefer small, focused diffs.

**Ask first**
- Adding a dependency, changing the Cassandra schema, changing status thresholds, or changing public API shapes.
- Anything that touches deployment, secrets, or CI.

**Never**
- Fabricate benchmark numbers, model metrics or sensor data. Benchmark UI renders committed result files only.
- Use `ALLOW FILTERING`, or add a query without a table designed for it. New query → new table (see `docs/TECHNICAL.md` §4).
- Split train/validation by row. Split by engine (unit). Fit scalers on train data only.
- Commit `data/raw/`, `.env*`, tokens or credentials. Use `.env.example`.
- Claim airworthiness, certification, or real-world accuracy. Keep the disclaimer in the footer.
- Edit generated files by hand (`api/openapi.json` generated types, ONNX artifacts, lockfiles) except via their tooling.

## Domain facts agents get wrong
- 21 sensors, 3 operating settings, 26 columns total. `Nf` = physical **fan** speed; `Nc` = **core** speed.
- FD001 informative sensors: s2,3,4,7,8,9,11,12,13,14,15,17,20,21. Other subsets: compute, don't copy.
- Train trajectories run to failure; test trajectories are truncated and labelled by `RUL_FDxxx.txt`.
- RUL target is capped at 125 for training; show "≥ 125" in the UI instead of fake precision.
- There are no wall-clock timestamps in C-MAPSS. Time shown in the UI is the replay clock.
- Display engine ID is `{dataset}-{unit:03d}` (e.g. `FD001-023`); APIs use `(dataset, unit)`.
- Temperatures are °R (Rankine), pressures psia.

## Conventions
- Frontend: server components by default; add `"use client"` only for interactivity (charts, SSE, theme). Server state in TanStack Query; Zustand only for UI state. Tailwind utilities with the existing theme tokens; `tabular-nums` and monospace for readouts.
- Python: type hints, Pydantic models at boundaries, pure functions for policy/metrics, prepared CQL statements only.
- Commits: Conventional Commits (`feat(api): …`, `fix(frontend): …`). PRs: what/why, screenshots for UI, test evidence, link to the PRD requirement ID (e.g. `F-3`).
- Keep this file short. If you learn a repeatable procedure, add a skill (`SKILLS.md`) instead of growing this file.

## Skills
Task-specific procedures live in `.agents/skills/<name>/SKILL.md` (catalog in `SKILLS.md`). Load the matching skill before starting: data ingestion, model training/eval, Cassandra schema changes, API contract changes, fleet UI components, alert-rule tuning, benchmark runs.

## Definition of done
Tests pass; lint/typecheck clean; no new hard-coded data; docs updated if behavior changed (`docs/` and, for schema/API, the ADR or contract); PR references a requirement ID.
