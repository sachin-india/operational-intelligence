"""Integration tests: verify Neo4j graph state after ai4i load."""

import pytest

from core.ontology.graph import GraphSession


@pytest.fixture(scope="module")
def graph():
    with GraphSession.from_env() as g:
        g.verify_connectivity()
        yield g


def test_machine_node_count(graph):
    rows = graph.run("MATCH (n:Machine) RETURN count(n) AS cnt")
    assert rows[0]["cnt"] == 3


def test_tool_run_node_count(graph):
    rows = graph.run("MATCH (n:ToolRun) RETURN count(n) AS cnt")
    assert rows[0]["cnt"] == 10_000


def test_failure_mode_node_count(graph):
    rows = graph.run("MATCH (n:FailureMode) RETURN count(n) AS cnt")
    assert rows[0]["cnt"] == 5


def test_has_run_relationship_count(graph):
    rows = graph.run("MATCH ()-[r:HAS_RUN]->() RETURN count(r) AS cnt")
    assert rows[0]["cnt"] == 10_000


def test_has_failure_relationship_count(graph):
    rows = graph.run("MATCH ()-[r:HAS_FAILURE]->() RETURN count(r) AS cnt")
    assert rows[0]["cnt"] == 373


def test_machine_ids_correct(graph):
    rows = graph.run("MATCH (m:Machine) RETURN m.machine_id AS mid ORDER BY mid")
    ids = [r["mid"] for r in rows]
    assert ids == ["MACHINE_H", "MACHINE_L", "MACHINE_M"]


def test_failure_mode_ids_correct(graph):
    rows = graph.run("MATCH (f:FailureMode) RETURN f.failure_id AS fid ORDER BY fid")
    ids = {r["fid"] for r in rows}
    assert ids == {"TWF", "HDF", "PWF", "OSF", "RNF"}


def test_tool_run_has_expected_properties(graph):
    rows = graph.run(
        "MATCH (r:ToolRun {run_id: 'RUN_00001'}) RETURN r"
    )
    assert len(rows) == 1
    props = rows[0]["r"]
    assert props["machine_id"] == "MACHINE_M"
    assert props["event_time"] == "2024-01-01T00:00:00"
    assert isinstance(props["air_temp_k"], float)
    assert props["tool_wear_min"] >= 0


def test_graph_path_machine_to_failure(graph):
    rows = graph.run(
        """
        MATCH (m:Machine)-[:HAS_RUN]->(r:ToolRun)-[:HAS_FAILURE]->(f:FailureMode)
        RETURN count(*) AS cnt
        """
    )
    assert rows[0]["cnt"] == 373
