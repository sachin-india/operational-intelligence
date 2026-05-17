"""Integration tests for the @governed decorator and audit log.

Requires the Docker Postgres container to be running:
    docker compose -f infra/docker-compose.yml up -d
"""

import pytest

from core.governance import (
    AuditLog,
    SessionLocal,
    clear_registry,
    create_tables,
    governed,
    register_actor,
)


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    """Create tables once for this module."""
    create_tables()


@pytest.fixture(autouse=True)
def clean_state():
    """Reset actor registry and wipe audit rows before each test."""
    clear_registry()
    with SessionLocal() as session:
        session.query(AuditLog).delete()
        session.commit()
    yield
    clear_registry()


# ---------------------------------------------------------------------------
# A minimal governed function used across tests
# ---------------------------------------------------------------------------

@governed(action_name="test_action", required_role="engineer")
def sample_action(machine_id: str, actor: str, reason: str) -> dict:
    return {"machine_id": machine_id, "status": "done"}


@governed(action_name="failing_action", required_role="operator")
def always_fails(actor: str, reason: str) -> None:
    raise RuntimeError("something went wrong")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_success_outcome_written_to_audit_log():
    register_actor("alice", "engineer")
    sample_action("M1", actor="alice", reason="testing")

    with SessionLocal() as session:
        log = session.query(AuditLog).one()

    assert log.action_name == "test_action"
    assert log.actor == "alice"
    assert log.reason == "testing"
    assert log.outcome == "success"
    assert log.error is None
    assert log.created_at is not None


def test_aborted_outcome_written_when_permission_denied():
    register_actor("charlie", "operator")  # too low for 'engineer' action

    with pytest.raises(PermissionError):
        sample_action("M1", actor="charlie", reason="trying anyway")

    with SessionLocal() as session:
        log = session.query(AuditLog).one()

    assert log.outcome == "aborted"
    assert log.actor == "charlie"
    assert "engineer" in log.error


def test_failed_outcome_written_when_function_raises():
    register_actor("alice", "operator")

    with pytest.raises(RuntimeError):
        always_fails(actor="alice", reason="testing failure path")

    with SessionLocal() as session:
        log = session.query(AuditLog).one()

    assert log.outcome == "failed"
    assert "something went wrong" in log.error


def test_payload_is_stored_in_audit_log():
    register_actor("alice", "engineer")
    # Use keyword arg so the decorator captures it in payload (positional args are not captured)
    sample_action(machine_id="M99", actor="alice", reason="payload test")

    with SessionLocal() as session:
        log = session.query(AuditLog).one()

    assert log.payload.get("machine_id") == "M99"
