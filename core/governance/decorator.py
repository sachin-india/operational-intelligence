"""The @governed decorator.

Wraps any function with:
  1. A permission check before execution.
  2. An audit log write for every call outcome (success, failed, aborted).

The decorated function must accept `actor` and `reason` as keyword arguments.
Both are forwarded to the function AND written to the audit log.
Call governed functions with keyword arguments to ensure all params are
captured in the audit payload (positional args are not recorded).
"""

import functools
from typing import Any, Callable

from core.governance.audit import write_audit
from core.governance.permissions import has_permission


def governed(action_name: str, required_role: str = "operator") -> Callable:
    """Decorator factory that adds governance to a function.

    Args:
        action_name:   Human-readable name written to the audit log.
        required_role: Minimum role an actor must have to execute the function.

    Usage:
        @governed(action_name="trigger_maintenance", required_role="engineer")
        def trigger_maintenance(machine_id: str, actor: str, reason: str) -> dict:
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, actor: str, reason: str, **kwargs: Any) -> Any:
            payload: dict = {**kwargs}

            # 1. Check permission before doing anything.
            if not has_permission(actor, required_role):
                write_audit(
                    action_name, actor, reason, payload, outcome="aborted",
                    error=f"'{actor}' lacks required role '{required_role}'",
                )
                raise PermissionError(
                    f"'{actor}' does not have role '{required_role}' "
                    f"required for '{action_name}'"
                )

            # 2. Execute the function, audit the result.
            try:
                result = func(*args, actor=actor, reason=reason, **kwargs)
                write_audit(action_name, actor, reason, payload, outcome="success")
                return result
            except PermissionError:
                raise  # already audited above
            except Exception as exc:
                write_audit(
                    action_name, actor, reason, payload, outcome="failed",
                    error=str(exc),
                )
                raise

        return wrapper

    return decorator
