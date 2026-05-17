"""Integration tests for core/actions/base.py.

Requires Docker Neo4j + Postgres to be running:
    docker compose -f infra/docker-compose.yml up -d

Tests verify the full Action.run() pipeline:
  - successful execution writes 'success' to audit log
  - failing precondition raises PreconditionError and writes 'aborted'
  - insufficient permissions raise PermissionError and writes 'aborted'
  - execute() failure calls rollback() and writes 'failed'
"""

import pytest

from core.actions.base import Action, PreconditionError
from core.governance import (
    AuditLog,
    SessionLocal,
    clear_registry,
    create_tables,
    register_actor,
)
from core.ontology.graph import GraphSession


# ---------------------------------------------------------------------------
# Concrete action subclasses used in tests
# ---------------------------------------------------------------------------

class NoOpAction(Action):
    """Executes successfully without touching the graph."""
    name = "no_op_action"
    required_role = "operator"

    def execute(self, graph: GraphSession, actor: str, reason: str) -> dict:
        return {"status": "done", "actor": actor}


class GuardedAction(Action):
    """Has a configurable precondition to test guard logic."""
    name = "guarded_action"
    required_role = "operator"

    def __init__(self, should_pass: bool) -> None:
        self.should_pass = should_pass

    def preconditions(self) -> list[tuple[bool, str]]:
        return [(self.should_pass, "Precondition deliberately failed")]

    def execute(self, graph: GraphSession, actor: str, reason: str) -> dict:
        return {"status": "done"}


class FailingAction(Action):
    """execute() always raises to test rollback and 'failed' audit."""
    name = "failing_action"
    required_role = "operator"
    rollback_was_called: bool = False

    def execute(self, graph: GraphSession, actor: str, reason: str) -> dict:
        raise RuntimeError("deliberate failure in execute")

    def rollback(self, graph: GraphSession) -> None:
        FailingAction.rollback_was_called = True


class EngineerOnlyAction(Action):
    """Requires engineer role to test permission denial."""
    name = "engineer_only_action"
    required_role = "engineer"

    def execute(self, graph: GraphSession, actor: str, reason: str) -> dict:
        return {"status": "done"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    create_tables()


@pytest.fixture(autouse=True)
def clean_state():
    clear_registry()
    FailingAction.rollback_was_called = False
    with SessionLocal() as session:
        session.query(AuditLog).delete()
        session.commit()
    yield
    clear_registry()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_successful_action_returns_result_and_writes_success_audit():
    register_actor("alice", "operator")
    result = NoOpAction().run(actor="alice", reason="routine check")

    assert result["status"] == "done"
    assert result["actor"] == "alice"

    with SessionLocal() as session:
        log = session.query(AuditLog).one()

    assert log.action_name == "no_op_action"
    assert log.actor == "alice"
    assert log.reason == "routine check"
    assert log.outcome == "success"
    assert log.error is None
    assert log.created_at is not None


def test_failing_precondition_raises_and_writes_aborted_audit():
    register_actor("alice", "operator")

    with pytest.raises(PreconditionError, match="Precondition deliberately failed"):
        GuardedAction(should_pass=False).run(actor="alice", reason="testing guard")

    with SessionLocal() as session:
        log = session.query(AuditLog).one()

    assert log.outcome == "aborted"
    assert "Precondition deliberately failed" in log.error


def test_passing_precondition_allows_execution():
    register_actor("alice", "operator")
    result = GuardedAction(should_pass=True).run(actor="alice", reason="all clear")
    assert result["status"] == "done"

    with SessionLocal() as session:
        log = session.query(AuditLog).one()
    assert log.outcome == "success"


def test_permission_denied_raises_and_writes_aborted_audit():
    register_actor("charlie", "operator")  # operator cannot run engineer action

    with pytest.raises(PermissionError):
        EngineerOnlyAction().run(actor="charlie", reason="trying anyway")

    with SessionLocal() as session:
        log = session.query(AuditLog).one()

    assert log.outcome == "aborted"
    assert log.actor == "charlie"
    assert "engineer" in log.error


def test_execute_failure_calls_rollback_and_writes_failed_audit():
    register_actor("alice", "operator")

    with pytest.raises(RuntimeError, match="deliberate failure"):
        FailingAction().run(actor="alice", reason="testing failure path")

    assert FailingAction.rollback_was_called is True

    with SessionLocal() as session:
        log = session.query(AuditLog).one()

    assert log.outcome == "failed"
    assert "deliberate failure" in log.error
