"""Integration tests for TriggerMaintenance action.

Requires live Neo4j (and Postgres for audit) — both via docker-compose.
"""

import json
from pathlib import Path

import pytest

from core.actions.base import PreconditionError
from core.governance.permissions import clear_registry, register_actor
from core.ontology.graph import GraphSession
from demos.ai4i.track_b.actions import MES_MOCK_PATH, TriggerMaintenance

_TEST_RUN = "RUN_00001"  # guaranteed to exist after the load step


@pytest.fixture(autouse=True)
def reset_state():
    """Reset governance registry and undo maintenance state before each test."""
    clear_registry()
    # Register test actors.
    register_actor("eng_alice", "engineer")
    register_actor("op_bob", "operator")

    # Ensure the test run has no maintenance_scheduled property.
    with GraphSession.from_env() as g:
        g.run(
            """
            MATCH (r:ToolRun {run_id: $rid})
            REMOVE r.maintenance_scheduled,
                   r.maintenance_actor,
                   r.maintenance_reason,
                   r.maintenance_at
            """,
            rid=_TEST_RUN,
        )

    yield

    # Cleanup after each test: remove any maintenance state we set.
    with GraphSession.from_env() as g:
        g.run(
            """
            MATCH (r:ToolRun {run_id: $rid})
            REMOVE r.maintenance_scheduled,
                   r.maintenance_actor,
                   r.maintenance_reason,
                   r.maintenance_at
            """,
            rid=_TEST_RUN,
        )


# ---------------------------------------------------------------------------
# Precondition: ToolRun must exist
# ---------------------------------------------------------------------------

def test_precondition_fails_for_nonexistent_run():
    action = TriggerMaintenance(run_id="RUN_ZZZZZ")
    with pytest.raises(PreconditionError, match="not found"):
        action.run(actor="eng_alice", reason="test")


# ---------------------------------------------------------------------------
# Permission: requires engineer role
# ---------------------------------------------------------------------------

def test_permission_denied_for_operator():
    action = TriggerMaintenance(run_id=_TEST_RUN)
    with pytest.raises(PermissionError, match="engineer"):
        action.run(actor="op_bob", reason="test")


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------

def test_successful_execution_sets_node_property():
    action = TriggerMaintenance(run_id=_TEST_RUN)
    result = action.run(actor="eng_alice", reason="high tool wear observed")

    assert result["run_id"] == _TEST_RUN
    assert result["actor"] == "eng_alice"
    assert "scheduled_at" in result

    with GraphSession.from_env() as g:
        rows = g.run(
            "MATCH (r:ToolRun {run_id: $rid}) RETURN r.maintenance_scheduled AS ms",
            rid=_TEST_RUN,
        )
    assert rows[0]["ms"] is True


def test_successful_execution_writes_to_mes_mock():
    before_size = MES_MOCK_PATH.stat().st_size if MES_MOCK_PATH.exists() else 0

    action = TriggerMaintenance(run_id=_TEST_RUN)
    action.run(actor="eng_alice", reason="inspection due")

    assert MES_MOCK_PATH.exists()
    with MES_MOCK_PATH.open() as f:
        lines = f.readlines()
    last = json.loads(lines[-1])
    assert last["run_id"] == _TEST_RUN
    assert last["event"] == "maintenance_scheduled"
    assert last["actor"] == "eng_alice"


def test_successful_execution_writes_audit_log():
    from sqlalchemy import text
    from core.governance.db import SessionLocal

    action = TriggerMaintenance(run_id=_TEST_RUN)
    action.run(actor="eng_alice", reason="audit test")

    with SessionLocal() as db:
        row = db.execute(
            text(
                "SELECT outcome, action_name FROM audit_log "
                "WHERE actor = 'eng_alice' ORDER BY id DESC LIMIT 1"
            )
        ).fetchone()
    assert row is not None
    assert row.outcome == "success"
    assert row.action_name == "trigger_maintenance"


# ---------------------------------------------------------------------------
# Precondition: already scheduled
# ---------------------------------------------------------------------------

def test_precondition_fails_if_already_scheduled():
    action = TriggerMaintenance(run_id=_TEST_RUN)
    action.run(actor="eng_alice", reason="first scheduling")

    action2 = TriggerMaintenance(run_id=_TEST_RUN)
    with pytest.raises(PreconditionError, match="already"):
        action2.run(actor="eng_alice", reason="duplicate attempt")
