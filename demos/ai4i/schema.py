"""AI4I demo entity and link definitions.

These classes define the graph schema for the AI4I Predictive Maintenance demo.
They use the core ObjectType and LinkType base classes so they are automatically
Pydantic-validated and Cypher-aware.

Entity design rationale:
  Machine    — 3 nodes (Type L / M / H). Represents a machine quality category.
  ToolRun    — 10,000 nodes (one per row). Each row is a point-in-time sensor
               reading during one operational run. This is the primary object.
  FailureMode — 5 nodes (TWF / HDF / PWF / OSF / RNF). Categorical failure types.

Link design:
  Machine  -[HAS_RUN]->    ToolRun     (which machine type ran this operation)
  ToolRun  -[HAS_FAILURE]-> FailureMode (which failure type occurred, if any)
"""

from core.ontology.base import LinkType, ObjectType


class Machine(ObjectType):
    __label__ = "Machine"
    __primary_key__ = "machine_id"

    machine_id: str        # e.g. "MACHINE_L"
    machine_type: str      # L | M | H


class ToolRun(ObjectType):
    __label__ = "ToolRun"
    __primary_key__ = "run_id"

    run_id: str            # e.g. "RUN_00001"
    machine_id: str        # FK to Machine
    product_id: str        # original Product ID from dataset
    air_temp_k: float      # air temperature in Kelvin
    process_temp_k: float  # process temperature in Kelvin
    rotational_speed_rpm: float
    torque_nm: float
    tool_wear_min: float   # cumulative tool wear in minutes
    machine_failure: bool  # True if any failure occurred
    event_time: str        # ISO 8601 synthetic timestamp


class FailureMode(ObjectType):
    __label__ = "FailureMode"
    __primary_key__ = "failure_id"

    failure_id: str        # e.g. "TWF"
    failure_name: str      # e.g. "Tool Wear Failure"


# ---------------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------------

class MachineHasRun(LinkType):
    __rel_type__ = "HAS_RUN"
    __source_label__ = "Machine"
    __target_label__ = "ToolRun"
    __source_pk__ = "machine_id"
    __target_pk__ = "run_id"


class RunHasFailure(LinkType):
    __rel_type__ = "HAS_FAILURE"
    __source_label__ = "ToolRun"
    __target_label__ = "FailureMode"
    __source_pk__ = "run_id"
    __target_pk__ = "failure_id"


# ---------------------------------------------------------------------------
# Static reference data
# ---------------------------------------------------------------------------

FAILURE_MODES: list[FailureMode] = [
    FailureMode(failure_id="TWF", failure_name="Tool Wear Failure"),
    FailureMode(failure_id="HDF", failure_name="Heat Dissipation Failure"),
    FailureMode(failure_id="PWF", failure_name="Power Failure"),
    FailureMode(failure_id="OSF", failure_name="Overstrain Failure"),
    FailureMode(failure_id="RNF", failure_name="Random Failure"),
]
