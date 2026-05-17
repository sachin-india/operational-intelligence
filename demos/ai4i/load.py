"""Load AI4I refined data into Neo4j.

Reads four refined CSVs and bulk-merges them into Neo4j using UNWIND batches.
Idempotent: safe to run multiple times (MERGE, not CREATE).

Run:
    uv run python -m demos.ai4i.load

Done when:
  - Neo4j contains 3 Machine nodes, 10,000 ToolRun nodes, 5 FailureMode nodes
  - 10,000 HAS_RUN relationships, N HAS_FAILURE relationships
"""

from pathlib import Path

import pandas as pd

from core.ontology.graph import GraphSession

REFINED = Path(__file__).parent / "data" / "refined"

_BATCH_SIZE = 500


def load() -> None:
    with GraphSession.from_env() as g:
        _create_indexes(g)
        n_machines = _load_machines(g)
        n_failure_modes = _load_failure_modes(g)
        n_tool_runs = _load_tool_runs(g)
        n_has_run = _load_has_run_links(g)
        n_has_failure = _load_has_failure_links(g)

    print("AI4I Neo4j load complete.")
    print(f"  Machine nodes:      {n_machines}")
    print(f"  FailureMode nodes:  {n_failure_modes}")
    print(f"  ToolRun nodes:      {n_tool_runs:,}")
    print(f"  HAS_RUN rels:       {n_has_run:,}")
    print(f"  HAS_FAILURE rels:   {n_has_failure:,}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _create_indexes(g: GraphSession) -> None:
    g.run("CREATE INDEX machine_id IF NOT EXISTS FOR (n:Machine) ON (n.machine_id)")
    g.run("CREATE INDEX run_id IF NOT EXISTS FOR (n:ToolRun) ON (n.run_id)")
    g.run("CREATE INDEX failure_id IF NOT EXISTS FOR (n:FailureMode) ON (n.failure_id)")


def _load_machines(g: GraphSession) -> int:
    df = pd.read_csv(REFINED / "machines.csv")
    rows = df.to_dict("records")
    g.run(
        """
        UNWIND $rows AS row
        MERGE (n:Machine {machine_id: row.machine_id})
        SET n += row
        """,
        rows=rows,
    )
    return len(rows)


def _load_failure_modes(g: GraphSession) -> int:
    df = pd.read_csv(REFINED / "failure_modes.csv")
    rows = df.to_dict("records")
    g.run(
        """
        UNWIND $rows AS row
        MERGE (n:FailureMode {failure_id: row.failure_id})
        SET n += row
        """,
        rows=rows,
    )
    return len(rows)


def _load_tool_runs(g: GraphSession) -> int:
    df = pd.read_csv(REFINED / "tool_runs.csv")
    total = 0
    for start in range(0, len(df), _BATCH_SIZE):
        batch = df.iloc[start : start + _BATCH_SIZE]
        rows = batch.to_dict("records")
        for row in rows:
            row["machine_failure"] = bool(row["machine_failure"])
        g.run(
            """
            UNWIND $rows AS row
            MERGE (n:ToolRun {run_id: row.run_id})
            SET n += row
            """,
            rows=rows,
        )
        total += len(rows)
    return total


def _load_has_run_links(g: GraphSession) -> int:
    df = pd.read_csv(REFINED / "tool_runs.csv", usecols=["run_id", "machine_id"])
    total = 0
    for start in range(0, len(df), _BATCH_SIZE):
        batch = df.iloc[start : start + _BATCH_SIZE].to_dict("records")
        g.run(
            """
            UNWIND $rows AS row
            MATCH (m:Machine {machine_id: row.machine_id})
            MATCH (r:ToolRun  {run_id:     row.run_id})
            MERGE (m)-[:HAS_RUN]->(r)
            """,
            rows=batch,
        )
        total += len(batch)
    return total


def _load_has_failure_links(g: GraphSession) -> int:
    df = pd.read_csv(REFINED / "run_failure_links.csv")
    rows = df.rename(columns={"source_id": "run_id", "target_id": "failure_id"}).to_dict("records")
    if not rows:
        return 0
    g.run(
        """
        UNWIND $rows AS row
        MATCH (r:ToolRun    {run_id:     row.run_id})
        MATCH (f:FailureMode {failure_id: row.failure_id})
        MERGE (r)-[:HAS_FAILURE]->(f)
        """,
        rows=rows,
    )
    return len(rows)


if __name__ == "__main__":
    load()
