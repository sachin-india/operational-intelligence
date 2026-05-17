"""Role-based permission model.

Three roles in ascending order of privilege:
  operator < engineer < supervisor

An actor with role 'engineer' can do anything that requires 'operator'
or 'engineer', but not 'supervisor'. A 'supervisor' can do everything.

For the demo, actors are registered in memory. In a real system this
would be backed by an IAM service.
"""

ROLE_HIERARCHY: list[str] = ["operator", "engineer", "supervisor"]

_ACTOR_ROLES: dict[str, str] = {}


def register_actor(actor: str, role: str) -> None:
    """Assign a role to an actor. Raises ValueError for unknown roles."""
    if role not in ROLE_HIERARCHY:
        raise ValueError(f"Unknown role '{role}'. Valid roles: {ROLE_HIERARCHY}")
    _ACTOR_ROLES[actor] = role


def get_role(actor: str) -> str:
    """Return the actor's role, defaulting to 'operator' if not registered."""
    return _ACTOR_ROLES.get(actor, "operator")


def has_permission(actor: str, required_role: str) -> bool:
    """Return True if the actor's role is at least as privileged as required_role."""
    actor_role = get_role(actor)
    if actor_role not in ROLE_HIERARCHY or required_role not in ROLE_HIERARCHY:
        return False
    return ROLE_HIERARCHY.index(actor_role) >= ROLE_HIERARCHY.index(required_role)


def clear_registry() -> None:
    """Remove all registered actors. Used in tests to reset state."""
    _ACTOR_ROLES.clear()
