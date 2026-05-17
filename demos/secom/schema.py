"""SECOM demo entity and link definitions.

Graph schema for the SECOM Semiconductor Yield demo.

Dataset context:
  The SECOM dataset is 1,567 wafer lot runs through a semiconductor production
  line. Each run has 590 sensor readings and a pass/fail outcome. Real timestamps
  exist (July–November 2008). Class labels: -1 = pass, 1 = fail.

Entity design:
  Lot        — 1,567 nodes (one per production run). Primary entity.
               Stores summary stats; detailed sensor values live on SPCAlarm links.
  YieldOutcome — 2 nodes: PASS and FAIL. Categorizes the quality result.
  SPCAlarm   — One node per sensor feature that ever crossed 3σ limits.
               Stores the population mean/std/control limits for that feature.

Link design:
  Lot  -[HAS_OUTCOME]->       YieldOutcome   (which quality result this lot had)
  Lot  -[TRIGGERED_ALARM]->   SPCAlarm       (which sensor crossed 3σ, + value + deviation)
"""

from core.ontology.base import LinkType, ObjectType


class Lot(ObjectType):
    __label__ = "Lot"
    __primary_key__ = "lot_id"

    lot_id: str            # e.g. "LOT_0001"
    event_time: str        # ISO 8601 from real dataset timestamp
    yield_pass: bool       # True = PASS (-1 in raw), False = FAIL (1 in raw)
    sensor_na_rate: float  # fraction of the 590 sensors that were NaN for this lot
    n_spc_alarms: int      # number of sensors that crossed 3σ for this lot


class YieldOutcome(ObjectType):
    __label__ = "YieldOutcome"
    __primary_key__ = "outcome_id"

    outcome_id: str    # "PASS" | "FAIL"
    outcome_label: str # human-readable label


class SPCAlarm(ObjectType):
    __label__ = "SPCAlarm"
    __primary_key__ = "alarm_id"

    alarm_id: str          # e.g. "SPC_ATTR_042"
    feature_name: str      # e.g. "Attribute 42"
    population_mean: float # mean across all non-NaN lot readings
    population_std: float  # std across all non-NaN lot readings
    upper_control_limit: float  # mean + 3 * std
    lower_control_limit: float  # mean - 3 * std
    total_alarm_count: int      # how many lots triggered this alarm


# ---------------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------------

class LotHasOutcome(LinkType):
    __rel_type__ = "HAS_OUTCOME"
    __source_label__ = "Lot"
    __target_label__ = "YieldOutcome"
    __source_pk__ = "lot_id"
    __target_pk__ = "outcome_id"


class LotTriggeredAlarm(LinkType):
    """A lot crossed the 3σ control limit for a specific sensor feature.

    Additional relationship properties (sigma_deviation, sensor_value) are
    written directly via Cypher in the loader — LinkType only carries the
    IDs needed to establish the relationship.
    """

    __rel_type__ = "TRIGGERED_ALARM"
    __source_label__ = "Lot"
    __target_label__ = "SPCAlarm"
    __source_pk__ = "lot_id"
    __target_pk__ = "alarm_id"


# ---------------------------------------------------------------------------
# Static reference data
# ---------------------------------------------------------------------------

YIELD_OUTCOMES: list[YieldOutcome] = [
    YieldOutcome(outcome_id="PASS", outcome_label="Passed quality control"),
    YieldOutcome(outcome_id="FAIL", outcome_label="Failed quality control"),
]
