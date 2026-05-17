"""AI4I Track B — TriggerMaintenance action.

Governed action that schedules preventive maintenance for a ToolRun.

Preconditions:
  1. The ToolRun must exist in the graph.
  2. Maintenance must not already be scheduled for this run.

Execute:
  - Sets maintenance_scheduled = true (+ actor/reason/timestamp) on the ToolRun.
  - Appends one JSON record to the mock MES output file (mes_mock.jsonl).

Rollback:
  - Removes all maintenance_* properties from the ToolRun node.

Required role: engineer  (operators cannot self-approve maintenance work orders)
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar

from core.actions.base import Action
from core.ontology.graph import GraphSession

MES_MOCK_PATH = Path(__file__).parent.parent / "data" / "mes_mock.jsonl"


class TriggerMaintenance(Action):
    """Schedule preventive maintenance for a given ToolRun."""

    name: ClassVar[str] = "trigger_maintenance"
    required_role: ClassVar[str] = "engineer"

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id

    def preconditions(self) -> list[tuple[bool, str]]:
        with GraphSession.from_env() as g:
            rows = g.run(
                "MATCH (r:ToolRun {run_id: $run_id}) RETURN r.maintenance_scheduled AS ms",
                run_id=self.run_id,
            )

        if not rows:
            return [(False, f"ToolRun '{self.run_id}' not found in graph")]

        already = rows[0].get("ms") is True
        return [(not already, f"ToolRun '{self.run_id}' already has maintenance scheduled")]

    def execute(self, graph: GraphSession, actor: str, reason: str) -> dict:
        ts = datetime.now(timezone.utc).isoformat()

        # Write derived state back to the graph node.
        graph.run(
            """
            MATCH (r:ToolRun {run_id: $run_id})
            SET r.maintenance_scheduled = true,
                r.maintenance_actor     = $actor,
                r.maintenance_reason    = $reason,
                r.maintenance_at        = $ts
            """,
            run_id=self.run_id,
            actor=actor,
            reason=reason,
            ts=ts,
        )

        # Write to mock MES (append-only; simulates a real system writeback).
        record = {
            "event": "maintenance_scheduled",
            "run_id": self.run_id,
            "actor": actor,
            "reason": reason,
            "scheduled_at": ts,
        }
        MES_MOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        with MES_MOCK_PATH.open("a") as fh:
            fh.write(json.dumps(record) + "\n")

        return record

    def rollback(self, graph: GraphSession) -> None:
        graph.run(
            """
            MATCH (r:ToolRun {run_id: $run_id})
            REMOVE r.maintenance_scheduled,
                   r.maintenance_actor,
                   r.maintenance_reason,
                   r.maintenance_at
            """,
            run_id=self.run_id,
        )
