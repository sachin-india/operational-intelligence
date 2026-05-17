"""Integration tests for HoldLot action."""

import json

import pytest

from core.actions.base import PreconditionError
from core.governance.db import SessionLocal
from core.governance.permissions import clear_registry, register_actor
from core.ontology.graph import GraphSession
from demos.secom.track_b.actions import HoldLot, MES_MOCK_PATH
from sqlalchemy import text

_TEST_LOT = "LOT_0001"


@pytest.fixture(autouse=True)
def reset_state():
    clear_registry()
    register_actor("eng_bob", "engineer")
    register_actor("op_carol", "operator")

    with GraphSession.from_env() as g:
        g.run(
            """
            MATCH (lot:Lot {lot_id: $lid})
            REMOVE lot.lot_on_hold, lot.hold_actor, lot.hold_reason, lot.hold_at
            """,
            lid=_TEST_LOT,
        )

    yield

    with GraphSession.from_env() as g:
        g.run(
            """
            MATCH (lot:Lot {lot_id: $lid})
            REMOVE lot.lot_on_hold, lot.hold_actor, lot.hold_reason, lot.hold_at
            """,
            lid=_TEST_LOT,
        )


def test_precondition_fails_for_nonexistent_lot():
    action = HoldLot(lot_id="LOT_ZZZZ")
    with pytest.raises(PreconditionError, match="not found"):
        action.run(actor="eng_bob", reason="test")


def test_permission_denied_for_operator():
    action = HoldLot(lot_id=_TEST_LOT)
    with pytest.raises(PermissionError, match="engineer"):
        action.run(actor="op_carol", reason="test")


def test_successful_hold_sets_node_property():
    action = HoldLot(lot_id=_TEST_LOT)
    result = action.run(actor="eng_bob", reason="SPC alarms exceeded threshold")

    assert result["lot_id"] == _TEST_LOT
    assert result["actor"] == "eng_bob"
    assert "held_at" in result

    with GraphSession.from_env() as g:
        rows = g.run(
            "MATCH (lot:Lot {lot_id: $lid}) RETURN lot.lot_on_hold AS held",
            lid=_TEST_LOT,
        )
    assert rows[0]["held"] is True


def test_successful_hold_writes_to_mes_mock():
    action = HoldLot(lot_id=_TEST_LOT)
    action.run(actor="eng_bob", reason="yield risk review")

    assert MES_MOCK_PATH.exists()
    with MES_MOCK_PATH.open() as f:
        lines = f.readlines()
    last = json.loads(lines[-1])
    assert last["lot_id"] == _TEST_LOT
    assert last["event"] == "lot_held"


def test_successful_hold_writes_audit_log():
    action = HoldLot(lot_id=_TEST_LOT)
    action.run(actor="eng_bob", reason="audit test")

    with SessionLocal() as db:
        row = db.execute(
            text(
                "SELECT outcome, action_name FROM audit_log "
                "WHERE actor = 'eng_bob' AND action_name = 'hold_lot' "
                "ORDER BY id DESC LIMIT 1"
            )
        ).fetchone()
    assert row is not None
    assert row.outcome == "success"


def test_precondition_fails_if_already_held():
    HoldLot(lot_id=_TEST_LOT).run(actor="eng_bob", reason="first hold")

    with pytest.raises(PreconditionError, match="already on hold"):
        HoldLot(lot_id=_TEST_LOT).run(actor="eng_bob", reason="duplicate")
