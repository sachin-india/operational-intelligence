# CLAUDE.md

This file is the working specification for the `operational-intelligence` repo. It is the source of truth for Claude (the AI assistant) when working in this codebase. Humans should read it too — it explains how the project is organized and why.

**Status:** v1.1 draft — under review with Sachin.

---

## 1. Project Purpose

This is a **learning project**. The goal is to deeply understand the **operational context graph** pattern (the approach Palantir Foundry's Ontology takes) by building two parallel demos on widely-available manufacturing datasets.

The user (Sachin) is a beginner in this area, aiming to become an expert. Every decision in this repo should serve **learning first, production-readiness second**. That means:

- Prefer code that is readable and instructive over code that is clever.
- Each step should have an explicit "what you'll learn from this" outcome.
- Where there is a tradeoff between elegance and clarity, pick clarity.

Background research and architectural rationale lives in `docs/palantir_ontology_live_transformation_report.md`. Read it before making schema or architecture decisions.

---

## 2. Definition of Success

This project is "done" when Sachin can do all of the following without reaching back to the codebase or notes:

1. **Explain** the difference between a passive knowledge graph and an operational context graph to another engineer in under 5 minutes, using a concrete example.
2. **Demonstrate** both demos end-to-end: data → graph → derived context → governed action → audit trail → external writeback.
3. **Judge** when the operational-graph pattern is worth its complexity, and when a simpler approach (SQL + REST API + dashboard) would have been sufficient.
4. **Map** any new factory dataset into the object / link / action / function vocabulary in under an hour.
5. **Articulate** the top design decisions that determine whether an operational graph succeeds or fails — ID harmonization, event-time correctness, action safety tiers, and governance-at-action-time.
6. **Run** the demos live for a stakeholder and answer questions about how to apply the pattern to their work.

Tagline: *Build it twice (AI4I and SECOM) so you've earned the right to advocate for it once.*

---

## 3. Repo Structure

```
operational-intelligence/
├── CLAUDE.md                       # This file
├── README.md                       # Human-facing project overview
├── pyproject.toml                  # Python project config
├── .gitignore
├── core/                           # Shared graph engine and frameworks
│   ├── ontology/                   # Object types, properties, links, schema validation
│   ├── actions/                    # Action framework: preconditions, side effects, audit
│   ├── functions/                  # Decision logic: rules + ML model wrappers
│   └── governance/                 # Permissions, role checks, audit log writer
├── demos/
│   ├── ai4i/                       # Demo 1: Predictive maintenance (UCI AI4I 2020)
│   │   ├── data/                   # Raw + refined data + data/README.md
│   │   ├── schema.py               # Entity + link definitions
│   │   ├── pipeline.py             # Raw → refined transform
│   │   ├── track_a/                # Passive knowledge graph
│   │   │   ├── load.py             # Load refined data into Neo4j
│   │   │   ├── app.py              # Streamlit UI
│   │   │   └── README.md
│   │   ├── track_b/                # Operational context graph
│   │   │   ├── functions.py        # predict_failure_risk, etc.
│   │   │   ├── actions.py          # trigger_maintenance, etc.
│   │   │   ├── api.py              # FastAPI action service
│   │   │   ├── app.py              # Streamlit UI with action controls
│   │   │   └── README.md
│   │   └── notebooks/              # Exploratory analysis + learning narrative
│   └── secom/                      # Demo 2: Semiconductor yield (UCI SECOM)
│       ├── data/
│       ├── schema.py
│       ├── pipeline.py
│       ├── track_a/
│       ├── track_b/
│       └── notebooks/
├── infra/
│   ├── docker-compose.yml          # Neo4j + Postgres
│   └── neo4j/                      # Neo4j config + init scripts
├── tests/                          # Mirrors source layout
└── docs/
    └── palantir_ontology_live_transformation_report.md
```

---

## 4. Tech Stack (Pinned)

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | Strong data tooling, type hints, learning-friendly |
| Graph store | Neo4j 5.x (Community, Docker) | Industry-standard graph DB; real Cypher experience |
| Action API | FastAPI | Lightweight, type-safe via Pydantic |
| UI | Streamlit | Fast UI iteration; sufficient for Track A/B comparison |
| Transactional + audit | Postgres 16 (Docker) | Real RDBMS for audit log + transactional state |
| ORM | SQLAlchemy 2.x | Standard, well-documented |
| Schema validation | Pydantic 2.x | Type-safe data contracts |
| Testing | pytest + pytest-asyncio + httpx | Standard Python test stack |
| Orchestration | docker-compose | Single-machine, no cloud dependency |

**Deliberately omitted** (may revisit in later phases, do not add without explicit user approval):
- Kafka / Debezium — streaming is simulated by a Python event-loop replay of the dataset.
- React frontend — Streamlit is sufficient.
- Any cloud services — everything runs locally.
- Heavyweight ML frameworks — start with scikit-learn or simpler.

---

## 5. Core Vocabulary

These terms are used consistently across the codebase, docs, and conversations:

| Term | Definition |
|---|---|
| **Object type** | A graph entity definition (e.g., `Machine`, `Lot`) |
| **Property** | A field on an object (e.g., `Machine.tool_wear`) |
| **Link** | A directed typed relationship (e.g., `Lot ->processedOn-> Tool`) |
| **Action** | A governed mutation with preconditions, side effects, and audit trail |
| **Function** | A decision-logic asset (rule-based or model-backed) returning scores/classifications |
| **Derived property** | A property computed by a function and stored on the object |
| **Track A** | Passive knowledge graph — entities and links only, queryable and visualizable |
| **Track B** | Operational context graph — Track A + derived context + functions + actions + governance + writeback |

---

## 6. Glossary (Beginner-Friendly)

### Tools and libraries used in this project

| Term | Plain explanation |
|---|---|
| **Neo4j** | A database that stores data as a graph (nodes + relationships) instead of tables. We run it in Docker. |
| **Cypher** | Neo4j's query language. Like SQL but for graphs. Example: `MATCH (m:Machine)-[:HAS_FAILURE]->(f) RETURN m, f`. |
| **Pydantic** | A Python library that validates data against a schema. If data doesn't match, it raises an error immediately. We use it for any data crossing a boundary (files, APIs, action inputs). |
| **FastAPI** | A Python framework for building web APIs quickly. Type-safe, auto-generates docs. We use it for the action service in Track B. |
| **Streamlit** | A Python library for building simple web UIs without HTML/CSS. Pure Python in, web page out. We use it for both Track A and Track B UIs. |
| **SQLAlchemy** | A Python library that lets you work with relational databases (like Postgres) using Python classes instead of raw SQL. |
| **pytest** | The standard Python testing framework. |
| **Docker** | A tool that runs software in isolated containers, so you don't pollute your machine with dependencies. |
| **docker-compose** | A tool that runs multiple Docker containers together as a single stack. We use it to start Neo4j and Postgres at the same time. |

### Architectural patterns

| Term | Plain explanation |
|---|---|
| **ETL / Pipeline** | Extract → Transform → Load. The process of moving raw data through cleaning and reshaping into a usable form. |
| **CDC (Change Data Capture)** | A pattern where every change to a database is emitted as a stream of events. Not implemented in this project but mentioned in the research doc. |
| **Idempotency** | A property where doing an operation twice produces the same result as doing it once. Critical for safe retries on flaky networks. |
| **RBAC** | Role-Based Access Control. "User X has role Y, which can perform action Z." |
| **Audit log** | An append-only record of every governed action: who, what, when, why, and the outcome. |
| **Event time vs processing time** | Event time = when something actually happened in the real world. Processing time = when your system got around to handling it. They differ when data is late or out of order. |

### Factory and manufacturing terms

| Term | Plain explanation |
|---|---|
| **MES** | Manufacturing Execution System. The "operating system" of a factory floor — knows what is being made, where, on which machine, by whom. |
| **ERP** | Enterprise Resource Planning. Tracks orders, inventory, suppliers, and finance. |
| **CMMS** | Computerized Maintenance Management System. Tracks equipment maintenance: schedules, work orders, parts. |
| **FDC** | Fault Detection and Classification. Catches abnormal sensor patterns on a tool. |
| **APC** | Advanced Process Control. Continuously adjusts process parameters to stay on-target. |
| **SPC** | Statistical Process Control. Method for detecting when a measurement has drifted outside its statistical limits. |
| **SPC alarm** | A signal that an SPC limit was breached — i.e., something abnormal is happening statistically. |
| **Excursion** | Any deviation from expected behavior; usually triggers a review or hold. |
| **Lot** | A batch of wafers (or units) processed together as a group. |
| **Wafer** | A thin disc of semiconductor material on which hundreds of chips are fabricated. |
| **Tool / Chamber** | A piece of factory equipment that processes wafers. A tool may contain multiple chambers. |
| **Recipe** | The defined process steps and parameters for making a specific thing on a specific tool. |
| **PM (Preventive Maintenance)** | Scheduled maintenance done before failure, to prevent it. |
| **Yield** | Percentage of wafers or chips that pass quality checks. |
| **Hold** | Stopping production movement on a specific lot/wafer until a decision is made. |

---

## 7. Datasets

### AI4I 2020 Predictive Maintenance Dataset
- **Size:** 10,000 records × ~10 columns
- **Source:** UCI Machine Learning Repository
- **Domain:** Generic milling-style machine operations (tool wear, temperature, torque, RPM, failure modes)
- **Entity map:** `Machine`, `ToolRun`, `MaintenanceEvent`, `FailureMode`, `QualityCheckpoint`

### SECOM Semiconductor Manufacturing Dataset
- **Size:** 1,567 records × 590 sensor features
- **Source:** UCI Machine Learning Repository
- **Domain:** Wafer fabrication (high-dimensional sensor data, sparse pass/fail labels)
- **Entity map:** `Lot`, `Wafer`, `ProcessStep`, `SensorReading`, `SPCAlarm`, `YieldOutcome`

Both datasets are downloaded into each demo's `data/raw/` folder. Source URL and license documented in each `data/README.md`. Raw files are committed to the repo (both are small enough).

---

## 8. Build Sequence

Build phases sequentially. Each step has an explicit **Done when** criterion. Do not start step N+1 until step N is done. Mark progress by replacing `[ ]` with `[x]` as steps complete.

### Phase 0 — Foundation
- [x] **0.1** Repo scaffold: directory structure, `CLAUDE.md`, `README.md`, `.gitignore`, `pyproject.toml`.
      **Done when:** `pytest` runs and passes on a trivial test. ✅ 3 scaffold tests passing on Python 3.14.4.
- [x] **0.2** `infra/docker-compose.yml` for Neo4j + Postgres with init scripts.
      **Done when:** `docker compose up -d` brings both up; `cypher-shell` and `psql` connect successfully. ✅ Neo4j 5 + Postgres 16 both healthy.

### Phase 1 — Core (Shared Framework)
- [x] **1.1** `core/ontology/` — base classes for `ObjectType`, `Link`, `Property` using Pydantic.
      **Done when:** Unit tests cover schema validation (valid + invalid cases). ✅ 15 unit tests passing.
- [x] **1.2** `core/governance/` — permission decorator + audit log writer (Postgres).
      **Done when:** A decorated function writes actor, timestamp, reason, and outcome to the audit table. ✅ 13 tests passing (9 unit + 4 integration against live Postgres).
- [x] **1.3** `core/actions/` — base `Action` class with preconditions, commit, and rollback hooks.
      **Done when:** A trivial test action executes, audits, and a failing precondition correctly aborts. ✅ 5 integration tests passing (success, precondition pass/fail, permission denied, rollback on failure).
- [x] **1.4** `core/functions/` — base `Function` class with rule-based and model-backed variants.
      **Done when:** A trivial rule-based function computes and stores a derived property in Neo4j. ✅ 8 tests passing (5 unit + 2 Neo4j integration + 1 stub test).

### Phase 2 — AI4I Demo
- [x] **2.1** AI4I — data download script + raw → refined Pandas pipeline.
      **Done when:** Refined dataset has clean IDs, event timestamps, and validated schema. ✅ 22 pipeline tests passing; 4 refined CSVs (3 machines, 10K tool_runs, 5 failure_modes, 373 links).
- [x] **2.2** AI4I Track A — load entities/links into Neo4j; Streamlit page for query/visualize.
      **Done when:** User can browse Machines, ToolRuns, and FailureModes graphically; run Cypher queries. ✅ 9 Neo4j integration tests; Streamlit app at localhost:8501 (Overview, Machines, Tool Runs, Failure Modes, Cypher Explorer pages).
- [x] **2.3** AI4I Track B — add `predict_failure_risk` function, `trigger_maintenance` action, governance, audit, MES-mock writeback.
      **Done when:** From Streamlit, user can submit a governed maintenance action that writes to the audit log and a mock external system. ✅ 21 tests (15 unit + 6 integration); FastAPI on :8000; Streamlit on :8502 (Risk Dashboard, Score All Runs, Audit Log).

### Phase 3 — SECOM Demo
- [x] **3.1** SECOM — data download + raw → refined pipeline.
      **Done when:** Refined data is loaded with validated schema. ✅ 26 pipeline tests passing; 4 refined CSVs (1,567 lots, 2 outcomes, 440 SPC alarm features, 6,115 alarm links).
- [x] **3.2** SECOM Track A — load entities/links into Neo4j; Streamlit page.
      **Done when:** Lots, Wafers, and sensor readings browsable; representative Cypher queries run. ✅ 9 Neo4j integration tests; Streamlit app at localhost:8503 (Overview, Lots, SPC Alarms, Yield Analysis, Cypher Explorer pages).
- [x] **3.3** SECOM Track B — `predict_yield_risk` function, `hold_lot` action, SPC alarm flow.
      **Done when:** Governed lot-hold action submittable from UI; audit + writeback verified. ✅ 18 tests (12 unit + 6 integration); FastAPI on :8001; Streamlit on :8504 (Risk Dashboard, Score All Lots, SPC Alarm Deep Dive, Audit Log).

### Phase 4 — Comparison & Report
- [x] **4.1** Cross-demo comparison notebook: side-by-side metrics (decision latency, traceability, action safety, operator effort).
      **Done when:** Notebook renders with concrete numbers for both demos. ✅ notebooks/comparison.ipynb — 8 sections, all cells execute cleanly; concrete numbers: AI4I batch 0.03ms/entity, SECOM 0.03ms/entity, 149 total tests.
- [x] **4.2** Final demo write-up in `docs/` reflecting on what was learned.
      **Done when:** Document signed off by user. ✅ docs/learnings.md — 7 sections covering the core distinction, both demos end-to-end, when to use the pattern, dataset mapping guide, 4 critical design decisions, stakeholder demo script, and what surprised me.

---

## 9. Conventions

### Code
- Type hints on every function signature.
- Pydantic models for any external schema (data files, API payloads, action inputs).
- Functions and actions use **snake_case verbs**: `trigger_maintenance`, `predict_failure_risk`.
- Object types use **PascalCase nouns**: `Machine`, `Lot`.
- No global state. Neo4j and Postgres connections are passed via constructor or FastAPI dependency injection.
- One class per file in `core/` modules. Demo `schema.py` may have multiple object types until it grows past ~150 lines.

### Tests
- Every action needs at least: a precondition-pass test, a precondition-fail test, and an audit-trail verification test.
- Integration tests use Docker-Compose Neo4j + Postgres; pytest fixtures reset state between tests.
- Tests mirror source layout under `tests/`.

### Commits
- One logical change per commit.
- Format: `area: short description` (e.g., `core/actions: add governance precondition check`).
- No mixed core + demo changes in one commit.
- Reference build-sequence step in the body when relevant: `Closes step 1.3`.

### Documentation
- Each `track_a/README.md` and `track_b/README.md` answers: what was added, what it teaches, what to try.
- Notebooks live in `demos/<demo>/notebooks/` with cleared outputs (use `nbstripout`).

---

## 10. How to Run

```bash
# One-time setup
docker compose -f infra/docker-compose.yml up -d
pip install -e ".[dev]"

# Verify infra
docker compose -f infra/docker-compose.yml ps

# Per demo
python -m demos.ai4i.pipeline                     # Load data
streamlit run demos/ai4i/track_a/app.py           # Track A UI on :8501
streamlit run demos/ai4i/track_b/app.py           # Track B UI on :8502
uvicorn demos.ai4i.track_b.api:app --reload       # Action API on :8000

# Tests
pytest                                             # All tests
pytest tests/core/                                 # Core only
pytest tests/demos/ai4i/                           # Demo-specific
```

---

## 11. Guidance for Claude

When working in this repo, Claude should:

1. **Build phases in order.** Do not skip ahead. Verify the "Done when" criterion before moving on.
2. **Always build Track A before Track B for a given dataset.** The comparison is the point.
3. **Keep `core/` general-purpose.** If something is demo-specific, it lives in the demo folder. If you find yourself special-casing AI4I or SECOM logic inside `core/`, stop and ask.
4. **All Neo4j writes go through `core/actions/`.** No direct Cypher mutations from demo code, notebooks, or UI. Reads are unrestricted; writes are governed.
5. **Write the test before the action.** Actions mutate state — they need preconditions and audit verified first.
6. **Explain the "why" in notebooks.** The user is learning. Each notebook should narrate what was tried, what worked, what surprised you.
7. **Ask before adding scope.** New libraries, new entity types, new tracks, new tech — confirm before adding. The omission list in Section 4 is intentional.
8. **Update this file as you go.** Tick off completed steps in Section 8. Add a `## Changelog` entry at the bottom for material spec changes.
9. **Use the research doc.** `docs/palantir_ontology_live_transformation_report.md` is the source of truth for the operational-graph pattern. Refer to it; do not reinvent decisions already made there.

---

## Changelog

- **v1.0 (2026-05-16):** Initial draft. Repo layout, tech stack, datasets, and build sequence locked.
- **v1.1 (2026-05-16):** Added Section 2 (Definition of Success) and Section 6 (Beginner-Friendly Glossary). Renumbered subsequent sections.
