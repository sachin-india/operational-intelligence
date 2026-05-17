"""AI4I Track B — PredictFailureRisk function.

Rule-based failure risk scoring derived from the AI4I 2020 paper's failure
conditions. Each rule corresponds to one of the five documented failure modes.

Rules (from Matzka 2020):
  TWF — tool wear ≥ 200 min (random within 200–240 range)
  HDF — (process_temp - air_temp) < 8.6 K  AND  rpm < 1380
  PWF — shaft power outside [3500 W, 9000 W]
  OSF — tool_wear × torque > machine-type threshold (L:11000 / M:12000 / H:13000)
  RNF — purely random 0.1%; not modelled here (no input signal)

Each triggered rule contributes to risk_score (0.0–1.0). risk_level buckets:
  high   ≥ 0.5
  medium ≥ 0.2
  low    < 0.2
"""

import math
from typing import ClassVar

from core.functions.base import RuleBasedFunction

# Overstrain threshold: tool_wear_min × torque_nm must exceed this per machine type.
_OSF_THRESHOLD: dict[str, float] = {
    "MACHINE_L": 11_000.0,
    "MACHINE_M": 12_000.0,
    "MACHINE_H": 13_000.0,
}

# Contribution of each rule to the overall risk score.
_RULE_WEIGHT = 0.35


class PredictFailureRisk(RuleBasedFunction):
    """Score a single ToolRun's failure risk from its sensor readings.

    Expected inputs dict keys:
        air_temp_k             float  — air temperature in Kelvin
        process_temp_k         float  — process temperature in Kelvin
        rotational_speed_rpm   float  — shaft speed
        torque_nm              float  — torque in Newton-metres
        tool_wear_min          float  — cumulative tool wear in minutes
        machine_id             str    — e.g. "MACHINE_M"  (optional, defaults to M thresholds)

    Returns:
        risk_score   float  — 0.0 (no risk) to 1.0 (maximum risk)
        risk_level   str    — "low" | "medium" | "high"
        risk_factors dict   — which rules fired and why
    """

    name: ClassVar[str] = "predict_failure_risk"

    def compute(self, inputs: dict) -> dict:
        air_temp_k = float(inputs["air_temp_k"])
        process_temp_k = float(inputs["process_temp_k"])
        rpm = float(inputs["rotational_speed_rpm"])
        torque_nm = float(inputs["torque_nm"])
        tool_wear_min = float(inputs["tool_wear_min"])
        machine_id = inputs.get("machine_id", "MACHINE_M")

        factors: dict[str, object] = {}
        score = 0.0

        # --- TWF: Tool Wear Failure ---
        if tool_wear_min >= 200:
            factors["TWF"] = "critical"
            score += _RULE_WEIGHT + 0.05
        elif tool_wear_min >= 150:
            factors["TWF"] = "approaching"
            score += _RULE_WEIGHT * 0.4

        # --- HDF: Heat Dissipation Failure ---
        temp_diff = process_temp_k - air_temp_k
        if temp_diff < 8.6 and rpm < 1380:
            factors["HDF"] = True
            score += _RULE_WEIGHT

        # --- PWF: Power Failure ---
        power_w = torque_nm * rpm * (2 * math.pi / 60)
        if power_w < 3500 or power_w > 9000:
            factors["PWF"] = round(power_w, 1)
            score += _RULE_WEIGHT

        # --- OSF: Overstrain Failure ---
        osf_threshold = _OSF_THRESHOLD.get(machine_id, 12_000.0)
        osf_value = tool_wear_min * torque_nm
        if osf_value > osf_threshold:
            factors["OSF"] = round(osf_value, 1)
            score += _RULE_WEIGHT

        score = round(min(score, 1.0), 3)

        if score >= 0.5:
            risk_level = "high"
        elif score >= 0.2:
            risk_level = "medium"
        else:
            risk_level = "low"

        return {
            "risk_score": score,
            "risk_level": risk_level,
            "risk_factors": factors,
        }
