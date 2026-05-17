"""Load SECOM refined data into Neo4j.

Reads four refined CSVs and bulk-merges them into Neo4j using UNWIND batches.
Idempotent: safe to run multiple times (MERGE, not CREATE).

Run:
    uv run python -m demos.secom.load

Done when:
  - Neo4j contains 1,567 Lot nodes, 2 YieldOutcome nodes, ≤590 SPCAlarm nodes
  - 1,567 HAS_OUTCOME relationships, N TRIGGERED_ALARM relationships
"""

from pathlib import Path

import pandas as pd

from core.ontology.graph import GraphSession

REFINED = Path(__file__).parent / "data" / "refined"

_BATCH_SIZE = 200


def load() -> None:
    with GraphSession.from_env() as g:
        _create_indexes(g)
        n_outcomes = _load_yield_outcomes(g)
        n_alarms = _load_spc_alarms(g)
        n_lots = _load_lots(g)
        n_has_outcome = _load_has_outcome_links(g)
        n_triggered = _load_triggered_alarm_links(g)

    print("SECOM Neo4j load complete.")
    print(f"  YieldOutcome nodes:    {n_outcomes}")
    print(f"  SPCAlarm nodes:        {n_alarms}")
    print(f"  Lot nodes:             {n_lots:,}")
    print(f"  HAS_OUTCOME rels:      {n_has_outcome:,}")
    print(f"  TRIGGERED_ALARM rels:  {n_triggered:,}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _create_indexes(g: GraphSession) -> None:
    g.run("CREATE INDEX lot_id IF NOT EXISTS FOR (n:Lot) ON (n.lot_id)")
    g.run("CREATE INDEX outcome_id IF NOT EXISTS FOR (n:YieldOutcome) ON (n.outcome_id)")
    g.run("CREATE INDEX alarm_id IF NOT EXISTS FOR (n:SPCAlarm) ON (n.alarm_id)")


def _load_yield_outcomes(g: GraphSession) -> int:
    df = pd.read_csv(REFINED / "yield_outcomes.csv")
    rows = df.to_dict("records")
    g.run(
        """
        UNWIND $rows AS row
        MERGE (n:YieldOutcome {outcome_id: row.outcome_id})
        SET n += row
        """,
        rows=rows,
    )
    return len(rows)


def _load_spc_alarms(g: GraphSession) -> int:
    df = pd.read_csv(REFINED / "spc_alarms.csv")
    rows = df.to_dict("records")
    g.run(
        """
        UNWIND $rows AS row
        MERGE (n:SPCAlarm {alarm_id: row.alarm_id})
        SET n += row
        """,
        rows=rows,
    )
    return len(rows)


def _load_lots(g: GraphSession) -> int:
    df = pd.read_csv(REFINED / "lots.csv")
    total = 0
    for start in range(0, len(df), _BATCH_SIZE):
        batch = df.iloc[start : start + _BATCH_SIZE].copy()
        batch["yield_pass"] = batch["yield_pass"].map({"True": True, "False": False, True: True, False: False})
        batch["n_spc_alarms"] = batch["n_spc_alarms"].astype(int)
        g.run(
            """
            UNWIND $rows AS row
            MERGE (n:Lot {lot_id: row.lot_id})
            SET n += row
            """,
            rows=batch.to_dict("records"),
        )
        total += len(batch)
    return total


def _load_has_outcome_links(g: GraphSession) -> int:
    df = pd.read_csv(REFINED / "lots.csv", usecols=["lot_id", "yield_pass"])
    df["outcome_id"] = df["yield_pass"].map(
        {True: "PASS", False: "FAIL", "True": "PASS", "False": "FAIL"}
    )
    total = 0
    for start in range(0, len(df), _BATCH_SIZE):
        batch = df.iloc[start : start + _BATCH_SIZE].to_dict("records")
        g.run(
            """
            UNWIND $rows AS row
            MATCH (lot:Lot          {lot_id:     row.lot_id})
            MATCH (out:YieldOutcome {outcome_id: row.outcome_id})
            MERGE (lot)-[:HAS_OUTCOME]->(out)
            """,
            rows=batch,
        )
        total += len(batch)
    return total


def _load_triggered_alarm_links(g: GraphSession) -> int:
    df = pd.read_csv(REFINED / "lot_alarm_links.csv")
    total = 0
    for start in range(0, len(df), _BATCH_SIZE):
        batch = df.iloc[start : start + _BATCH_SIZE].to_dict("records")
        g.run(
            """
            UNWIND $rows AS row
            MATCH (lot:Lot      {lot_id:  row.lot_id})
            MATCH (alm:SPCAlarm {alarm_id: row.alarm_id})
            MERGE (lot)-[r:TRIGGERED_ALARM {alarm_id: row.alarm_id}]->(alm)
            SET r.sensor_value    = row.sensor_value,
                r.sigma_deviation = row.sigma_deviation
            """,
            rows=batch,
        )
        total += len(batch)
    return total


if __name__ == "__main__":
    load()
