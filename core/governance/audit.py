"""Shared audit-log writer used by both the @governed decorator and Action.run()."""

from core.governance.db import SessionLocal
from core.governance.models import AuditLog


def write_audit(
    action_name: str,
    actor: str,
    reason: str,
    payload: dict,
    outcome: str,
    error: str | None = None,
) -> None:
    """Append one row to the audit_log table.

    outcome must be one of: 'success' | 'failed' | 'aborted'
    """
    with SessionLocal() as session:
        session.add(
            AuditLog(
                action_name=action_name,
                actor=actor,
                reason=reason,
                payload=payload,
                outcome=outcome,
                error=error,
            )
        )
        session.commit()
