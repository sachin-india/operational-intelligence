from typing import ClassVar

from pydantic import BaseModel


class ObjectType(BaseModel):
    """Base class for all graph object types.

    Subclasses declare their fields as Pydantic fields and set two class-level
    variables to control Neo4j behaviour:

        class Machine(ObjectType):
            __label__ = "Machine"          # Neo4j node label
            __primary_key__ = "machine_id" # Field used in MERGE

            machine_id: str
            tool_wear: float

    extra="forbid" means unknown fields raise a ValidationError immediately,
    which catches schema mismatches at the boundary rather than silently later.
    """

    __label__: ClassVar[str] = ""
    __primary_key__: ClassVar[str] = "id"

    model_config = {"extra": "forbid"}

    @classmethod
    def neo4j_label(cls) -> str:
        return cls.__label__ if cls.__label__ else cls.__name__

    @classmethod
    def primary_key(cls) -> str:
        return cls.__primary_key__

    def to_neo4j_props(self) -> dict:
        return self.model_dump()

    def merge_cypher(self) -> tuple[str, dict]:
        """Return (cypher, params) for a MERGE-then-SET-all-props query."""
        label = self.neo4j_label()
        pk = self.primary_key()
        props = self.to_neo4j_props()
        cypher = (
            f"MERGE (n:{label} {{{pk}: $pk_val}}) "
            f"SET n += $props "
            f"RETURN n"
        )
        return cypher, {"pk_val": props[pk], "props": props}


class LinkType(BaseModel):
    """Base class for directed relationships between two ObjectTypes.

    Subclasses declare the relationship metadata as class variables:

        class HasFailure(LinkType):
            __rel_type__    = "HAS_FAILURE"
            __source_label__ = "Machine"
            __target_label__ = "FailureMode"
            __source_pk__   = "machine_id"
            __target_pk__   = "failure_id"

    The two instance fields (source_id, target_id) carry the primary-key
    values of the nodes to connect.
    """

    __rel_type__: ClassVar[str] = ""
    __source_label__: ClassVar[str] = ""
    __target_label__: ClassVar[str] = ""
    __source_pk__: ClassVar[str] = "id"
    __target_pk__: ClassVar[str] = "id"

    source_id: str
    target_id: str

    model_config = {"extra": "forbid"}

    @classmethod
    def rel_type(cls) -> str:
        return cls.__rel_type__

    def merge_cypher(self) -> tuple[str, dict]:
        """Return (cypher, params) that MERGEs the relationship."""
        cypher = (
            f"MATCH (s:{self.__source_label__} {{{self.__source_pk__}: $source_id}}) "
            f"MATCH (t:{self.__target_label__} {{{self.__target_pk__}: $target_id}}) "
            f"MERGE (s)-[r:{self.__rel_type__}]->(t) "
            f"RETURN r"
        )
        return cypher, {"source_id": self.source_id, "target_id": self.target_id}
