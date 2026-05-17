# Operational Intelligence

A learning project that deeply explores the **operational context graph** pattern — the approach Palantir Foundry's Ontology takes — by building two complete demos on widely-available manufacturing datasets.

## What This Builds

Each demo is built in two tracks:

| Track | What it is | What you get |
|---|---|---|
| **Track A** | Passive knowledge graph | Entities and links loaded into Neo4j; Streamlit UI to browse and run Cypher |
| **Track B** | Operational context graph | Track A + risk-scoring functions + governed actions + audit trail + MES mock writeback |

**Demo 1 — AI4I Predictive Maintenance** (UCI dataset, 10,000 machine runs):
- `Machine → ToolRun → FailureMode` graph
- `PredictFailureRisk` function: scores each run against 4 documented failure rules (TWF/HDF/PWF/OSF)
- `TriggerMaintenance` action: governed, audited, writes to Neo4j + MES mock

**Demo 2 — SECOM Semiconductor Yield** (UCI dataset, 1,567 wafer lots, 590 sensors):
- `Lot → YieldOutcome` + `Lot → SPCAlarm` (3σ control-limit violations)
- `PredictYieldRisk` function: scores each lot on alarm count, max sigma deviation, missing-data rate
- `HoldLot` action: governed, audited, writes to Neo4j + MES mock

## Quick Start

```bash
# 1. Start infrastructure (Neo4j + Postgres)
docker compose -f infra/docker-compose.yml up -d

# 2. Install dependencies
uv sync

# 3. Load data into Neo4j
uv run python -m demos.ai4i.load
uv run python -m demos.secom.load

# 4. Run tests (149 passing)
uv run pytest
```

## Running the UIs

| Service | Command | URL |
|---|---|---|
| AI4I Track A | `uv run streamlit run demos/ai4i/track_a/app.py` | :8501 |
| AI4I Track B UI | `uv run streamlit run demos/ai4i/track_b/app.py --server.port 8502` | :8502 |
| AI4I Track B API | `uv run uvicorn demos.ai4i.track_b.api:app --port 8000` | :8000 |
| SECOM Track A | `uv run streamlit run demos/secom/track_a/app.py --server.port 8503` | :8503 |
| SECOM Track B UI | `uv run streamlit run demos/secom/track_b/app.py --server.port 8504` | :8504 |
| SECOM Track B API | `uv run uvicorn demos.secom.track_b.api:app --port 8001` | :8001 |

## Refreshing the Data

Raw CSVs are committed. Re-download only needed if UCI changes the dataset:

```bash
uv run python -m demos.ai4i.data.download   # → demos/ai4i/data/raw/ai4i2020.csv
uv run python -m demos.ai4i.pipeline        # → demos/ai4i/data/refined/*.csv

uv run python -m demos.secom.data.download  # → demos/secom/data/raw/secom.csv
uv run python -m demos.secom.pipeline       # → demos/secom/data/refined/*.csv
```

## Repository Structure

```
core/                          # Shared framework (reusable across both demos)
  ontology/                    # ObjectType, LinkType, GraphSession (Neo4j)
  actions/                     # Action base class: permission → preconditions → execute → audit → rollback
  functions/                   # Function base class: compute + store derived properties
  governance/                  # RBAC, @governed decorator, audit log (Postgres)

demos/ai4i/                    # Demo 1: Predictive maintenance
  data/raw/                    # ai4i2020.csv (committed)
  data/refined/                # 4 clean CSVs produced by pipeline.py
  schema.py                    # Machine, ToolRun, FailureMode entity definitions
  pipeline.py                  # raw → refined transform
  load.py                      # Bulk loader into Neo4j
  track_a/app.py               # Streamlit: browse graph, run Cypher
  track_b/functions.py         # PredictFailureRisk (rule-based, 4 failure conditions)
  track_b/actions.py           # TriggerMaintenance (governed action)
  track_b/api.py               # FastAPI: /risk, /trigger-maintenance, /audit
  track_b/app.py               # Streamlit: risk dashboard + action button + audit log

demos/secom/                   # Demo 2: Semiconductor yield
  data/raw/                    # secom.csv (committed)
  data/refined/                # 4 clean CSVs produced by pipeline.py
  schema.py                    # Lot, YieldOutcome, SPCAlarm entity definitions
  pipeline.py                  # raw → refined + SPC 3σ alarm computation
  load.py                      # Bulk loader into Neo4j
  track_a/app.py               # Streamlit: browse lots, SPC alarms, yield analysis
  track_b/functions.py         # PredictYieldRisk (rule-based, 3 risk signals)
  track_b/actions.py           # HoldLot (governed action)
  track_b/api.py               # FastAPI: /risk, /hold-lot, /audit
  track_b/app.py               # Streamlit: risk dashboard + hold button + audit log

infra/                         # docker-compose: Neo4j 5 + Postgres 16
notebooks/                     # comparison.ipynb: cross-demo metrics side-by-side
tests/                         # 149 tests, mirrors source layout
docs/                          # Research doc + learnings write-up
```

## Key Design Decisions

See [`docs/learnings.md`](./docs/learnings.md) for a full reflection. The short version:

- **ID harmonization first.** A `run_id` that doesn't match the MES is a broken writeback.
- **Rule-based functions, not ML by default.** Explicit rules are testable, debuggable, and trusted by operators.
- **Governance at action time, not registration time.** Preconditions check live graph state.
- **Core stays general-purpose.** All demo-specific logic lives under `demos/`. `core/` is reused unchanged by both demos.

## Background

Architectural rationale: [`docs/palantir_ontology_live_transformation_report.md`](./docs/palantir_ontology_live_transformation_report.md).

Build specification and progress tracking: [`CLAUDE.md`](./CLAUDE.md).
