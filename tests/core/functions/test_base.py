"""Tests for core/functions/base.py.

Unit tests: verify compute() logic without any Neo4j connection.
Integration tests: verify that run() stores derived properties in Neo4j.

Requires Docker Neo4j running for integration tests:
    docker compose -f infra/docker-compose.yml up -d
"""

import pytest

from core.functions.base import Function, ModelBackedFunction, RuleBasedFunction
from core.ontology.graph import GraphSession


# ---------------------------------------------------------------------------
# Concrete function used across tests
# ---------------------------------------------------------------------------

class MachineFatigueScore(RuleBasedFunction):
    """Trivial rule: fatigue = tool_wear / 100.0.

    risk_level thresholds:
      >= 0.7  → high
      >= 0.4  → medium
      < 0.4   → low
    """

    name = "machine_fatigue_score"

    def compute(self, inputs: dict) -> dict:
        score = round(inputs["tool_wear"] / 100.0, 3)
        if score >= 0.7:
            risk = "high"
        elif score >= 0.4:
            risk = "medium"
        else:
            risk = "low"
        return {"fatigue_score": score, "risk_level": risk}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEST_MACHINE_ID = "TEST_FN_MACHINE_001"


@pytest.fixture(scope="module")
def graph():
    with GraphSession.from_env() as g:
        yield g


@pytest.fixture(autouse=True)
def clean_test_node(graph):
    """Ensure test node is absent before each test; delete it after."""
    graph.run(
        "MATCH (m:Machine {machine_id: $mid}) DELETE m",
        mid=TEST_MACHINE_ID,
    )
    yield
    graph.run(
        "MATCH (m:Machine {machine_id: $mid}) DELETE m",
        mid=TEST_MACHINE_ID,
    )


# ---------------------------------------------------------------------------
# Unit tests — no Neo4j needed
# ---------------------------------------------------------------------------

def test_low_tool_wear_gives_low_risk(graph):
    result = MachineFatigueScore().compute({"tool_wear": 30.0})
    assert result["fatigue_score"] == 0.3
    assert result["risk_level"] == "low"


def test_medium_tool_wear_gives_medium_risk(graph):
    result = MachineFatigueScore().compute({"tool_wear": 50.0})
    assert result["fatigue_score"] == 0.5
    assert result["risk_level"] == "medium"


def test_high_tool_wear_gives_high_risk(graph):
    result = MachineFatigueScore().compute({"tool_wear": 80.0})
    assert result["fatigue_score"] == 0.8
    assert result["risk_level"] == "high"


def test_boundary_at_70_is_high_risk(graph):
    result = MachineFatigueScore().compute({"tool_wear": 70.0})
    assert result["risk_level"] == "high"


def test_run_without_store_returns_result(graph):
    result = MachineFatigueScore().run(graph, inputs={"tool_wear": 60.0})
    assert result["fatigue_score"] == 0.6
    assert result["risk_level"] == "medium"


# ---------------------------------------------------------------------------
# Integration tests — Neo4j required
# ---------------------------------------------------------------------------

def test_run_with_store_writes_derived_property_to_node(graph):
    # Create the target node
    graph.run(
        "MERGE (m:Machine {machine_id: $mid}) SET m.tool_wear = 75.0",
        mid=TEST_MACHINE_ID,
    )

    MachineFatigueScore().run(
        graph,
        inputs={"tool_wear": 75.0},
        node_label="Machine",
        node_id=TEST_MACHINE_ID,
        pk_field="machine_id",
    )

    rows = graph.run(
        "MATCH (m:Machine {machine_id: $mid}) RETURN m.fatigue_score AS score, m.risk_level AS risk",
        mid=TEST_MACHINE_ID,
    )
    assert len(rows) == 1
    assert rows[0]["score"] == pytest.approx(0.75)
    assert rows[0]["risk"] == "high"


def test_stored_properties_do_not_overwrite_unrelated_fields(graph):
    # Create node with an extra field
    graph.run(
        "MERGE (m:Machine {machine_id: $mid}) SET m.tool_wear = 30.0, m.location = 'fab-1'",
        mid=TEST_MACHINE_ID,
    )

    MachineFatigueScore().run(
        graph,
        inputs={"tool_wear": 30.0},
        node_label="Machine",
        node_id=TEST_MACHINE_ID,
        pk_field="machine_id",
    )

    rows = graph.run(
        "MATCH (m:Machine {machine_id: $mid}) RETURN m.location AS loc, m.fatigue_score AS score",
        mid=TEST_MACHINE_ID,
    )
    assert rows[0]["loc"] == "fab-1"       # existing field preserved
    assert rows[0]["score"] == pytest.approx(0.3)  # derived field added


# ---------------------------------------------------------------------------
# ModelBackedFunction stub test
# ---------------------------------------------------------------------------

def test_model_backed_function_load_model_raises_not_implemented():
    class StubModelFn(ModelBackedFunction):
        name = "stub_model"

        def compute(self, inputs: dict) -> dict:
            return {}

    with pytest.raises(NotImplementedError):
        StubModelFn().load_model()
