# What I Learned Building Operational Context Graphs

*A practitioner's reflection on building the AI4I and SECOM demos.*

---

## 1. The Core Distinction (In Under 5 Minutes)

**Passive knowledge graph (Track A):** A queryable map. Nodes and relationships describe what exists and how entities relate. You can ask "which machines have the most failures?" and get an answer. But the graph is inert — it doesn't watch the world, it doesn't act.

**Operational context graph (Track B):** A GPS, not a map. The same graph structure, but it knows the current state, can compute derived context (risk scores), and can take governed actions that write back to the world with a full audit trail.

The four-layer test for whether something is an operational graph:

| Layer | Question | AI4I | SECOM |
|---|---|---|---|
| **Semantic** | Are entities and relationships explicitly typed? | ToolRun, Machine, FailureMode | Lot, YieldOutcome, SPCAlarm |
| **Kinetic** | Do functions compute derived context from the graph? | PredictFailureRisk | PredictYieldRisk |
| **Action** | Are mutations governed with preconditions and audit? | TriggerMaintenance | HoldLot |
| **Governance** | Is every action attributed, reasoned, and logged? | Postgres audit_log | Postgres audit_log |

If any layer is missing, you have a knowledge graph, not an operational one. A graph with functions but no governance is just a fancy ETL. A graph with governance but no functions is a permissions system with extra steps.

---

## 2. Both Demos, End-to-End

### AI4I — Predictive Maintenance

**The dataset:** 10,000 machine sensor readings (temperature, torque, RPM, tool wear) with five explicit failure mode labels. Real-world data from a milling-style machine.

**What Track A gives you:**
- Browse the 3-tier machine hierarchy (L/M/H quality variants)
- See which failure modes cluster on which machine types
- Run arbitrary Cypher: `MATCH (m:Machine)-[:HAS_RUN]->(r:ToolRun)-[:HAS_FAILURE]->(f) RETURN m.machine_type, f.failure_name, count(*)`

**What Track B adds:**
- `PredictFailureRisk`: scores each ToolRun 0–1 against four documented rules (tool wear, heat dissipation, power, overstrain) with `risk_factors` showing exactly which rules fired
- `TriggerMaintenance`: governed action requiring `engineer` role; checks the run isn't already scheduled; writes `maintenance_scheduled=true` to Neo4j + appends to `mes_mock.jsonl` + audits to Postgres
- FastAPI at `:8000`; Streamlit at `:8501` (Track A) and `:8502` (Track B)

**The end-to-end story:** Run LOT_05000 has tool wear 225 min. The risk function scores it 0.4 (approaching TWF threshold). An engineer clicks "Trigger Maintenance" in the UI → the action checks preconditions → writes to Neo4j → appends to the MES mock → the audit log records `eng_alice` at `2026-05-17T02:27:09Z` with reason `"high tool wear observed"` and outcome `success`. If she tries again: `PreconditionError: ToolRun 'RUN_05000' already has maintenance scheduled`.

### SECOM — Semiconductor Yield

**The dataset:** 1,567 wafer lot runs with 590 sensor features and binary pass/fail labels. Real timestamps (July–October 2008). Heavily imbalanced: 6.6% failure rate. ~4.5% missing sensor readings.

**The harder entity design problem:** AI4I's failure modes were named in the data. SECOM's failure signal is *implicit* — it lives in the deviation pattern across 590 features. This required deriving the `SPCAlarm` entity type by applying 3σ control limits, which produced 440 alarm-feature nodes and 6,115 (lot, alarm) relationship events.

**What Track A gives you:**
- See that failing lots average ~7 SPC alarms vs ~3.5 for passing lots
- Drill into individual lots to see which sensors alarmed and by how many sigmas
- The "SPC Alarm Deep Dive" page shows which alarm features co-occur most often in failing lots — this is a graph query that would require a 590-column join in SQL

**What Track B adds:**
- `PredictYieldRisk`: scores each Lot on alarm count + max sigma deviation + missing data rate. LOT_0001 scores 0.85 (8 alarms, 5.1σ peak)
- `HoldLot`: governed action; checks lot exists and isn't already held; writes `lot_on_hold=true` to Neo4j + MES mock + audit
- FastAPI at `:8001`; Streamlit at `:8503` (Track A) and `:8504` (Track B)

---

## 3. When Is This Pattern Worth Its Complexity?

**Use it when all three are true:**
1. Entities have meaningful structural relationships (not just foreign keys)
2. Decisions require checking state across multiple entity types simultaneously
3. Actions must be governed, attributed, and auditable for compliance or safety

**Don't use it when:**
- Your data is flat tabular records with no cross-entity queries
- Your "actions" are fire-and-forget API calls with no precondition checks
- Your team doesn't have the bandwidth to maintain a graph schema
- A SQL view + dashboard would answer the actual questions being asked

**The honest cost:** Two databases to maintain (Neo4j + Postgres), a graph schema to evolve, and a Function/Action layer to keep aligned with the schema. This is real overhead. In the demos it took ~3,300 lines of Python. A SQL + Flask + Grafana solution for the same queries would be maybe 600 lines.

The operational graph earns that overhead only when the multi-hop graph queries and governance requirements are real, not aspirational.

---

## 4. Mapping a New Dataset Into the Vocabulary

The exercise that matters: given a new factory dataset, how do you map it?

**Step 1 — Find your primary entity.** What is the "thing" that operations runs against? In AI4I: a machine run. In SECOM: a wafer lot. In a real fab: a lot, a wafer, or a chamber run depending on granularity.

**Step 2 — Find your categorical entities.** What stable reference data does the primary entity belong to? AI4I: machine types, failure mode types. SECOM: yield outcomes, alarm feature types. Real fab: tool, recipe, chamber, process step.

**Step 3 — Find your event relationships.** What did one primary entity *do* to a categorical entity? AI4I: `HAS_FAILURE`. SECOM: `TRIGGERED_ALARM`. Real fab: `PROCESSED_ON`, `USED_RECIPE`, `TRIGGERED_SPC_ALARM`.

**Step 4 — Decide what's derived vs. raw.** Raw: sensor readings, timestamps, outcome labels. Derived: risk scores, anomaly flags, SPC limits, predicted yield. Rule: if you compute it from the data, it's derived and belongs as a Function output stored back on the node.

**Step 5 — Define your governed actions.** What can an operator *do* as a result of the derived context? What role is required? What preconditions must hold? What must roll back if it fails?

Time to map a new manufacturing dataset once you've done this twice: under an hour for the schema, another hour for the function logic, half a day for the action + tests.

---

## 5. Top Design Decisions That Determine Success or Failure

### 5.1 ID Harmonization
**The problem:** Every system (MES, CMMS, ERP, graph DB) has its own IDs for the same physical object. If your `run_id` in Neo4j doesn't match the `run_id` in the MES, your writeback is writing to the wrong record.

**What we did:** Synthesized deterministic IDs (`RUN_{UDI:05d}`, `LOT_{idx:04d}`) that are stable and predictable. In a real system, you'd use the source-of-truth ID from whichever upstream system owns it.

**What breaks if ignored:** Actions that succeed in the graph fail silently in the external system because the ID doesn't resolve.

### 5.2 Event-Time Correctness
**The problem:** Processing time (when your pipeline ran) is not event time (when the machine actually ran). SECOM has real timestamps; AI4I required synthetic ones. Storing processing time as event time causes incorrect time-series ordering and invalid trend analysis.

**What we did:** Parsed SECOM's real timestamps to ISO 8601. Synthesized AI4I timestamps at 6-minute intervals from a fixed base — documented clearly that they're synthetic.

**What breaks if ignored:** Queries like "what was the failure rate in Q3 2008?" return nonsense because the timestamps are wrong.

### 5.3 Action Safety Tiers
**The problem:** Not all actions have the same risk profile. Viewing a risk score is read-only. Triggering maintenance creates a work order and commits resources. Holding a lot stops production — wrong application costs thousands of dollars per hour.

**What we did:** Single `required_role` field per action: `operator` (lowest) → `engineer` → `supervisor`. Documented in the action class.

**What breaks if ignored:** Operators can self-approve actions they shouldn't, or engineers can't take actions that require supervisor sign-off.

### 5.4 Governance at Action Time
**The problem:** Pre-authorizing actions ("engineers can trigger maintenance on any run") sounds safe, but the actual guard must fire at call time against current graph state ("is this run already scheduled?"). Static RBAC is necessary but not sufficient.

**What we did:** Two-gate system: `has_permission()` for the role check, `preconditions()` for the state check. Both run at `action.run()` time, not at registration time.

**What breaks if ignored:** Duplicate work orders, conflicting holds, or actions that succeed in a state they should have been blocked in.

---

## 6. How to Explain This to a Stakeholder in 10 Minutes

**Opening frame:** "We built a system that doesn't just store data about what happened — it continuously knows the current risk state of every machine/lot, and lets engineers take governed actions through it with a complete audit trail."

**The GPS vs. map analogy:** "A normal dashboard is a map. It shows you where things are. This is GPS — it knows where you are right now, computes the best path forward, and tells you when to turn. You can still use it as a map, but it also drives."

**The demo script:**
1. Open Track A → show the graph overview → run a Cypher query
2. Switch to Track B → show the risk dashboard pre-sorted by risk score → point out the `risk_factors` (why this specific entity is flagged)
3. Click "Trigger Maintenance" / "Hold Lot" → show the action execute
4. Open the Audit Log → show the actor, reason, timestamp, and outcome
5. Try clicking again → show the precondition block

**The "so what" for their context:** Translate immediately to their work. What is their primary entity? What governed actions do their operators need? What compliance requirement does the audit log satisfy?

---

## 7. What Surprised Me

**The entity design exercise was the most valuable part.** Not the code. The 30 minutes of asking "what is actually a node and what is actually a relationship?" forced clearer thinking about the domain than any amount of dashboard design.

**Track A was underrated.** Before adding functions and actions, the Track A graph for SECOM already showed things that were invisible in the flat CSV: that SPC alarms cluster on specific features across failing lots. That's a structural fact about the data that the graph made visible by having alarm-feature nodes shared across lot-alarm links.

**Rule-based functions are the right starting point.** Not because ML is wrong, but because explicit rules are:
- Testable (15 unit tests on `PredictFailureRisk` run in 0.2 seconds)
- Debuggable (`risk_factors` shows exactly which rule fired and why)
- Trustworthy to operators who can see the logic
- A baseline that tells you whether a model is actually adding value

**The governance boilerplate pays off immediately.** Writing `core/actions/base.py` once meant that both demos got permission checks, precondition evaluation, audit logging, and rollback for free. The cost was one afternoon. The benefit accumulated across every action in both demos.

**ID harmonization is not a technical problem.** It's an organizational one. In these demos, IDs were under our control. In a real factory, five teams own five systems with five ID schemes and none of them are wrong — they're all right for their own system. The graph is only as good as your ability to resolve the same physical entity across all of them.

---

*Built May 2026. AI4I + SECOM datasets, Python 3.14, Neo4j 5, Postgres 16, FastAPI, Streamlit.*
