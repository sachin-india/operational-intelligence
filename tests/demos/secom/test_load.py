"""Integration tests: verify Neo4j graph state after SECOM load."""

import pytest

from core.ontology.graph import GraphSession


@pytest.fixture(scope="module")
def graph():
    with GraphSession.from_env() as g:
        g.verify_connectivity()
        yield g


def test_lot_node_count(graph):
    rows = graph.run("MATCH (n:Lot) RETURN count(n) AS cnt")
    assert rows[0]["cnt"] == 1_567


def test_yield_outcome_node_count(graph):
    rows = graph.run("MATCH (n:YieldOutcome) RETURN count(n) AS cnt")
    assert rows[0]["cnt"] == 2


def test_spc_alarm_node_count(graph):
    rows = graph.run("MATCH (n:SPCAlarm) RETURN count(n) AS cnt")
    assert rows[0]["cnt"] == 440


def test_has_outcome_rel_count(graph):
    rows = graph.run("MATCH ()-[r:HAS_OUTCOME]->() RETURN count(r) AS cnt")
    assert rows[0]["cnt"] == 1_567


def test_triggered_alarm_rel_count(graph):
    rows = graph.run("MATCH ()-[r:TRIGGERED_ALARM]->() RETURN count(r) AS cnt")
    assert rows[0]["cnt"] == 6_115


def test_yield_outcome_ids(graph):
    rows = graph.run("MATCH (n:YieldOutcome) RETURN n.outcome_id AS oid ORDER BY oid")
    ids = {r["oid"] for r in rows}
    assert ids == {"PASS", "FAIL"}


def test_lot_has_expected_properties(graph):
    rows = graph.run(
        "MATCH (lot:Lot {lot_id: 'LOT_0001'}) RETURN lot"
    )
    assert len(rows) == 1
    props = rows[0]["lot"]
    assert props["event_time"] == "2008-07-19T11:55:00"
    assert isinstance(props["yield_pass"], bool)
    assert 0.0 <= props["sensor_na_rate"] <= 1.0
    assert props["n_spc_alarms"] >= 0


def test_fail_lots_count(graph):
    rows = graph.run(
        """
        MATCH (lot:Lot)-[:HAS_OUTCOME]->(out:YieldOutcome {outcome_id: 'FAIL'})
        RETURN count(lot) AS cnt
        """
    )
    assert rows[0]["cnt"] == 104


def test_triggered_alarm_has_properties(graph):
    rows = graph.run(
        """
        MATCH (lot:Lot)-[r:TRIGGERED_ALARM]->(alm:SPCAlarm)
        RETURN r.sigma_deviation AS sigma_dev, r.sensor_value AS val
        LIMIT 1
        """
    )
    assert len(rows) == 1
    assert abs(rows[0]["sigma_dev"]) > 3.0
    assert rows[0]["val"] is not None
