"""Unit tests for the permission model. No database required."""

import pytest

from core.governance.permissions import (
    clear_registry,
    get_role,
    has_permission,
    register_actor,
)


@pytest.fixture(autouse=True)
def clean_registry():
    """Reset actor registry before each test."""
    clear_registry()
    yield
    clear_registry()


def test_unregistered_actor_defaults_to_operator():
    assert get_role("unknown_user") == "operator"


def test_register_actor_sets_role():
    register_actor("alice", "engineer")
    assert get_role("alice") == "engineer"


def test_register_invalid_role_raises_value_error():
    with pytest.raises(ValueError, match="Unknown role"):
        register_actor("bob", "admin")


def test_operator_can_do_operator_actions():
    register_actor("charlie", "operator")
    assert has_permission("charlie", "operator") is True


def test_operator_cannot_do_engineer_actions():
    register_actor("charlie", "operator")
    assert has_permission("charlie", "engineer") is False


def test_engineer_can_do_operator_actions():
    register_actor("alice", "engineer")
    assert has_permission("alice", "operator") is True


def test_engineer_can_do_engineer_actions():
    register_actor("alice", "engineer")
    assert has_permission("alice", "engineer") is True


def test_engineer_cannot_do_supervisor_actions():
    register_actor("alice", "engineer")
    assert has_permission("alice", "supervisor") is False


def test_supervisor_can_do_all_actions():
    register_actor("boss", "supervisor")
    assert has_permission("boss", "operator") is True
    assert has_permission("boss", "engineer") is True
    assert has_permission("boss", "supervisor") is True
