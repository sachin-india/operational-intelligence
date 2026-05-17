"""Unit tests for core/ontology/base.py.

These tests exercise Pydantic validation and Cypher generation without
connecting to Neo4j. They cover both valid and invalid cases.
"""

import pytest
from pydantic import ValidationError

from core.ontology.base import LinkType, ObjectType


# ---------------------------------------------------------------------------
# Minimal concrete types used across tests
# ---------------------------------------------------------------------------

class Machine(ObjectType):
    __label__ = "Machine"
    __primary_key__ = "machine_id"

    machine_id: str
    tool_wear: float
    temperature_c: float


class FailureMode(ObjectType):
    __label__ = "FailureMode"
    __primary_key__ = "failure_id"

    failure_id: str
    failure_type: str


class HasFailure(LinkType):
    __rel_type__ = "HAS_FAILURE"
    __source_label__ = "Machine"
    __target_label__ = "FailureMode"
    __source_pk__ = "machine_id"
    __target_pk__ = "failure_id"


# ---------------------------------------------------------------------------
# ObjectType — valid instantiation
# ---------------------------------------------------------------------------

def test_valid_object_instantiates():
    m = Machine(machine_id="M1", tool_wear=45.2, temperature_c=298.5)
    assert m.machine_id == "M1"
    assert m.tool_wear == 45.2
    assert m.temperature_c == 298.5


# ---------------------------------------------------------------------------
# ObjectType — validation errors
# ---------------------------------------------------------------------------

def test_wrong_field_type_raises_validation_error():
    with pytest.raises(ValidationError):
        Machine(machine_id="M1", tool_wear="not_a_float", temperature_c=298.5)


def test_missing_required_field_raises_validation_error():
    with pytest.raises(ValidationError):
        Machine(machine_id="M1", tool_wear=45.2)  # temperature_c missing


def test_extra_field_raises_validation_error():
    with pytest.raises(ValidationError):
        Machine(machine_id="M1", tool_wear=45.2, temperature_c=298.5, unknown="x")


# ---------------------------------------------------------------------------
# ObjectType — label and primary key
# ---------------------------------------------------------------------------

def test_neo4j_label_returns_declared_label():
    assert Machine.neo4j_label() == "Machine"


def test_neo4j_label_defaults_to_class_name_when_not_set():
    class Unnamed(ObjectType):
        item_id: str

    assert Unnamed.neo4j_label() == "Unnamed"


def test_primary_key_returns_configured_field():
    assert Machine.primary_key() == "machine_id"


# ---------------------------------------------------------------------------
# ObjectType — Neo4j serialisation
# ---------------------------------------------------------------------------

def test_to_neo4j_props_returns_full_dict():
    m = Machine(machine_id="M1", tool_wear=45.2, temperature_c=298.5)
    assert m.to_neo4j_props() == {
        "machine_id": "M1",
        "tool_wear": 45.2,
        "temperature_c": 298.5,
    }


def test_merge_cypher_contains_label_and_merge_keyword():
    m = Machine(machine_id="M1", tool_wear=45.2, temperature_c=298.5)
    cypher, params = m.merge_cypher()
    assert "MERGE" in cypher
    assert "Machine" in cypher


def test_merge_cypher_params_have_correct_pk_and_props():
    m = Machine(machine_id="M1", tool_wear=45.2, temperature_c=298.5)
    _, params = m.merge_cypher()
    assert params["pk_val"] == "M1"
    assert params["props"]["tool_wear"] == 45.2
    assert params["props"]["temperature_c"] == 298.5


# ---------------------------------------------------------------------------
# LinkType — valid instantiation and metadata
# ---------------------------------------------------------------------------

def test_valid_link_instantiates():
    link = HasFailure(source_id="M1", target_id="F1")
    assert link.source_id == "M1"
    assert link.target_id == "F1"


def test_link_rel_type():
    assert HasFailure.rel_type() == "HAS_FAILURE"


def test_link_merge_cypher_contains_labels_and_rel_type():
    link = HasFailure(source_id="M1", target_id="F1")
    cypher, params = link.merge_cypher()
    assert "Machine" in cypher
    assert "FailureMode" in cypher
    assert "HAS_FAILURE" in cypher
    assert params["source_id"] == "M1"
    assert params["target_id"] == "F1"


# ---------------------------------------------------------------------------
# LinkType — validation errors
# ---------------------------------------------------------------------------

def test_link_missing_target_id_raises_validation_error():
    with pytest.raises(ValidationError):
        HasFailure(source_id="M1")


def test_link_extra_field_raises_validation_error():
    with pytest.raises(ValidationError):
        HasFailure(source_id="M1", target_id="F1", extra="x")
