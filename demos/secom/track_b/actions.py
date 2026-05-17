"""SECOM Track B — HoldLot action.

Governed action that places a wafer lot on hold pending quality review.
In a real fab, a hold stops the lot from moving to the next process step
until an engineer reviews and releases it.

Preconditions:
  1. The Lot must exist in the graph.
  2. The Lot must not already be on hold.

Execute:
  - Sets lot_on_hold = true (+ actor/reason/timestamp) on the Lot node.
  - Appends one JSON record to the mock MES output file (mes_mock.jsonl).

Rollback:
  - Removes all hold_* properties from the Lot node.

Required role: engineer  (operators cannot self-authorize a lot hold)
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar

from core.actions.base import Action
from core.ontology.graph import GraphSession

MES_MOCK_PATH = Path(__file__).parent.parent / "data" / "mes_mock.jsonl"


class HoldLot(Action):
    """Place a wafer lot on hold pending engineering review."""

    name: ClassVar[str] = "hold_lot"
    required_role: ClassVar[str] = "engineer"

    def __init__(self, lot_id: str) -> None:
        self.lot_id = lot_id

    def preconditions(self) -> list[tuple[bool, str]]:
        with GraphSession.from_env() as g:
            rows = g.run(
                "MATCH (lot:Lot {lot_id: $lot_id}) RETURN lot.lot_on_hold AS held",
                lot_id=self.lot_id,
            )

        if not rows:
            return [(False, f"Lot '{self.lot_id}' not found in graph")]

        already_held = rows[0].get("held") is True
        return [(not already_held, f"Lot '{self.lot_id}' is already on hold")]

    def execute(self, graph: GraphSession, actor: str, reason: str) -> dict:
        ts = datetime.now(timezone.utc).isoformat()

        graph.run(
            """
            MATCH (lot:Lot {lot_id: $lot_id})
            SET lot.lot_on_hold   = true,
                lot.hold_actor    = $actor,
                lot.hold_reason   = $reason,
                lot.hold_at       = $ts
            """,
            lot_id=self.lot_id,
            actor=actor,
            reason=reason,
            ts=ts,
        )

        record = {
            "event": "lot_held",
            "lot_id": self.lot_id,
            "actor": actor,
            "reason": reason,
            "held_at": ts,
        }
        MES_MOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        with MES_MOCK_PATH.open("a") as fh:
            fh.write(json.dumps(record) + "\n")

        return record

    def rollback(self, graph: GraphSession) -> None:
        graph.run(
            """
            MATCH (lot:Lot {lot_id: $lot_id})
            REMOVE lot.lot_on_hold,
                   lot.hold_actor,
                   lot.hold_reason,
                   lot.hold_at
            """,
            lot_id=self.lot_id,
        )
