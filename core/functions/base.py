"""Base classes for decision-logic functions.

A Function reads input data, computes a result, and optionally writes that
result back to Neo4j as a derived property on a node.

Two variants are provided:

  RuleBasedFunction  — explicit if-then logic. Always start here.
                       Transparent, fast to validate, zero ML dependencies.

  ModelBackedFunction — wraps a trained ML model. Add only after the
                        rule-based baseline is stable and measurable.

Key design principles:
  - compute() is a pure function: same inputs → same outputs, no side effects.
  - Storing the result back to the graph is optional and explicit.
  - Functions never write through the Action governance path — they are
    read-and-annotate operations, not mutations. If a function's output
    triggers a real-world change, that change goes through an Action.
"""

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from core.ontology.graph import GraphSession


class Function(ABC):
    """Base class for all decision-logic functions.

    Minimal subclass example (rule-based):

        class MachineFatigueScore(RuleBasedFunction):
            name = "machine_fatigue_score"

            def compute(self, inputs: dict) -> dict:
                score = inputs["tool_wear"] / 100.0
                return {
                    "fatigue_score": round(score, 3),
                    "risk_level": "high" if score > 0.7 else "low",
                }

    Usage:
        fn = MachineFatigueScore()

        # Compute only (e.g. to show recommendation before operator commits):
        result = fn.run(graph, inputs={"tool_wear": 75.0})

        # Compute and store as derived properties on the node:
        result = fn.run(
            graph,
            inputs={"tool_wear": 75.0},
            node_label="Machine",
            node_id="M1",
            pk_field="machine_id",
        )
    """

    name: ClassVar[str] = ""

    @abstractmethod
    def compute(self, inputs: dict) -> dict:
        """Pure computation — no graph reads or writes allowed here.

        Args:
            inputs: flat dict of values needed for the computation.
        Returns:
            flat dict of derived properties to be stored or returned.
        """

    def store(
        self,
        graph: GraphSession,
        node_label: str,
        node_id: str,
        pk_field: str,
        result: dict,
    ) -> None:
        """Write the computed result back to a Neo4j node as derived properties.

        Uses SET n += props so only the keys in result are updated — existing
        properties on the node are preserved.
        """
        cypher = (
            f"MATCH (n:{node_label} {{{pk_field}: $node_id}}) "
            f"SET n += $props "
            f"RETURN n"
        )
        graph.run(cypher, node_id=node_id, props=result)

    def run(
        self,
        graph: GraphSession,
        inputs: dict,
        node_label: str = "",
        node_id: str = "",
        pk_field: str = "id",
    ) -> dict:
        """Compute and optionally store the result.

        Args:
            graph:       Active GraphSession.
            inputs:      Input values forwarded to compute().
            node_label:  If set, store result on this Neo4j node type.
            node_id:     Primary-key value of the target node.
            pk_field:    Name of the primary-key field (default: "id").

        Returns:
            The computed result dict.
        """
        result = self.compute(inputs)
        if node_label and node_id:
            self.store(graph, node_label, node_id, pk_field, result)
        return result


class RuleBasedFunction(Function, ABC):
    """Function implemented with explicit deterministic rules.

    No additional interface beyond Function — just implement compute()
    using plain Python conditionals. Prefer this over ModelBackedFunction
    until you have a stable, measured baseline.
    """


class ModelBackedFunction(Function, ABC):
    """Function backed by a trained ML model.

    Subclasses must implement compute() to invoke the model.
    Model loading and caching are the subclass's responsibility.

    Only introduce this after the rule-based baseline for the same
    decision is validated and measurable.
    """

    def load_model(self) -> Any:
        """Load and return the trained model object.

        Override in subclasses. Called once; cache the result as an
        instance attribute to avoid reloading on every call.
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement load_model()"
        )
