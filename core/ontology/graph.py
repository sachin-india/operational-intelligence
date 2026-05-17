from neo4j import GraphDatabase, Driver

from core.ontology.base import LinkType, ObjectType


class GraphSession:
    """Thin wrapper around the Neo4j driver.

    Handles connect/disconnect and exposes three operations:
    - merge_node   : upsert an ObjectType instance as a Neo4j node
    - merge_link   : upsert a LinkType instance as a Neo4j relationship
    - run          : execute raw Cypher (for queries and traversals)

    Usage:
        with GraphSession.from_env() as g:
            g.merge_node(machine)
            g.merge_link(link)
            rows = g.run("MATCH (m:Machine) RETURN m.machine_id LIMIT 5")
    """

    def __init__(self, uri: str, user: str, password: str) -> None:
        self._driver: Driver = GraphDatabase.driver(uri, auth=(user, password))

    @classmethod
    def from_env(cls) -> "GraphSession":
        from core.config import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER
        return cls(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

    def verify_connectivity(self) -> None:
        self._driver.verify_connectivity()

    def close(self) -> None:
        self._driver.close()

    def __enter__(self) -> "GraphSession":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def merge_node(self, obj: ObjectType) -> dict:
        cypher, params = obj.merge_cypher()
        with self._driver.session() as session:
            result = session.run(cypher, **params)
            record = result.single()
            return dict(record["n"]) if record else {}

    def merge_link(self, link: LinkType) -> bool:
        cypher, params = link.merge_cypher()
        with self._driver.session() as session:
            result = session.run(cypher, **params)
            return result.single() is not None

    def run(self, cypher: str, **params) -> list[dict]:
        with self._driver.session() as session:
            result = session.run(cypher, **params)
            return [record.data() for record in result]
