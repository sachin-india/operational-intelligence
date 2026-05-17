"""Base class for all operational graph actions.

An Action is a governed, audited mutation. Every call to run() goes through
the same pipeline in the same order — no shortcuts:

  1. Permission check       → PermissionError + 'aborted' audit if denied
  2. Precondition checks    → PreconditionError + 'aborted' audit if any fail
  3. Execute                → writes to Neo4j (and optionally external systems)
  4. Audit                  → 'success' written on completion
  5. Rollback + audit       → 'failed' written if execute() raises

Subclasses must implement execute() and set name + required_role.
"""

from abc import ABC, abstractmethod
from typing import ClassVar

from core.governance.audit import write_audit
from core.governance.permissions import has_permission
from core.ontology.graph import GraphSession


class PreconditionError(Exception):
    """Raised when a domain-level precondition blocks an action.

    Distinct from PermissionError (which is about who) — PreconditionError
    is about whether the current state of the graph allows the action at all.

    Example: you cannot trigger maintenance on a machine that is already
    under maintenance. That is a state check, not a role check.
    """


class Action(ABC):
    """Base class for all governed actions.

    Minimal subclass example:

        class AnnotateMachine(Action):
            name = "annotate_machine"
            required_role = "operator"

            def __init__(self, machine_id: str, note: str) -> None:
                self.machine_id = machine_id
                self.note = note

            def preconditions(self) -> list[tuple[bool, str]]:
                return [
                    (bool(self.note), "Note cannot be empty"),
                ]

            def execute(self, graph: GraphSession, actor: str, reason: str) -> dict:
                graph.run(
                    "MATCH (m:Machine {machine_id: $mid}) SET m.note = $note",
                    mid=self.machine_id, note=self.note,
                )
                return {"machine_id": self.machine_id, "note": self.note}
    """

    name: ClassVar[str] = ""
    required_role: ClassVar[str] = "operator"

    def preconditions(self) -> list[tuple[bool, str]]:
        """Domain guards that must all pass before execution.

        Return a list of (passes: bool, failure_message: str) tuples.
        Evaluated in order — the first failure aborts the action.
        """
        return []

    @abstractmethod
    def execute(self, graph: GraphSession, actor: str, reason: str) -> dict:
        """The actual work. Override in every subclass.

        Must return a dict describing what was done — this becomes the
        action's return value and can be logged or displayed to the operator.
        """

    def rollback(self, graph: GraphSession) -> None:
        """Called if execute() raises an unexpected exception.

        Override to undo any partial writes. Not called for PermissionError
        or PreconditionError (those abort before execute() runs).
        """

    def run(self, actor: str, reason: str) -> dict:
        """The only public entry point. Do not call execute() directly.

        Args:
            actor:  Identifier of the person or system triggering this action.
            reason: Human-readable justification — stored in the audit log.
        """
        action_name = self.name or type(self).__name__
        payload: dict = {"actor": actor, "reason": reason}

        # 1. Permission check.
        if not has_permission(actor, self.required_role):
            write_audit(
                action_name, actor, reason, payload, outcome="aborted",
                error=f"'{actor}' lacks required role '{self.required_role}'",
            )
            raise PermissionError(
                f"'{actor}' does not have role '{self.required_role}' "
                f"required for '{action_name}'"
            )

        # 2. Precondition checks.
        for passes, message in self.preconditions():
            if not passes:
                write_audit(action_name, actor, reason, payload, outcome="aborted",
                            error=message)
                raise PreconditionError(message)

        # 3. Execute with rollback on unexpected failure.
        with GraphSession.from_env() as graph:
            try:
                result = self.execute(graph=graph, actor=actor, reason=reason)
                write_audit(action_name, actor, reason, payload, outcome="success")
                return result
            except (PermissionError, PreconditionError):
                raise
            except Exception as exc:
                self.rollback(graph)
                write_audit(action_name, actor, reason, payload, outcome="failed",
                            error=str(exc))
                raise
