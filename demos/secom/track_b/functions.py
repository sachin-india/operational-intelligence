"""SECOM Track B — PredictYieldRisk function.

Rule-based yield risk scoring based on SPC alarm pattern.

The key insight from the SECOM dataset: failing lots tend to trigger more
3σ SPC alarms and have higher sigma deviations than passing lots. This function
uses that structural fact to produce a risk score without any ML model.

Rules:
  1. Alarm count   — more alarms = higher risk (primary signal)
  2. Severity      — maximum absolute sigma deviation across all alarms
  3. Missing data  — high sensor_na_rate = unreliable reading, slight penalty

Risk levels:
  high   risk_score >= 0.6
  medium risk_score >= 0.3
  low    risk_score <  0.3
"""

from typing import ClassVar

from core.functions.base import RuleBasedFunction

# Calibrated from SECOM dataset: failing lots average ~7 alarms; passing ~3.5
_HIGH_ALARM_COUNT = 8       # >= this → high alarm penalty
_MEDIUM_ALARM_COUNT = 4     # >= this → medium alarm penalty
_HIGH_SIGMA = 5.0           # max |sigma_dev| >= this → severity penalty
_HIGH_NA_RATE = 0.15        # sensor_na_rate >= this → data quality penalty


class PredictYieldRisk(RuleBasedFunction):
    """Score a single Lot's yield risk from its SPC alarm summary.

    Expected inputs dict keys:
        n_spc_alarms     int    — number of 3σ violations for this lot
        sensor_na_rate   float  — fraction of sensor readings that were NaN
        max_sigma_dev    float  — maximum |sigma_deviation| across all alarms
                                  (0.0 if no alarms; pass from graph query)

    Returns:
        risk_score   float  — 0.0 (no risk) to 1.0 (maximum risk)
        risk_level   str    — "low" | "medium" | "high"
        risk_factors dict   — which rules fired and why
    """

    name: ClassVar[str] = "predict_yield_risk"

    def compute(self, inputs: dict) -> dict:
        n_alarms = int(inputs.get("n_spc_alarms", 0))
        na_rate = float(inputs.get("sensor_na_rate", 0.0))
        max_sigma = float(inputs.get("max_sigma_dev", 0.0))

        factors: dict[str, object] = {}
        score = 0.0

        # --- Alarm count contribution (up to 0.5) ---
        if n_alarms >= _HIGH_ALARM_COUNT:
            factors["high_alarm_count"] = n_alarms
            score += 0.5
        elif n_alarms >= _MEDIUM_ALARM_COUNT:
            factors["medium_alarm_count"] = n_alarms
            score += 0.25
        elif n_alarms > 0:
            score += 0.1

        # --- Severity contribution (up to 0.35) ---
        if max_sigma >= _HIGH_SIGMA:
            factors["high_severity"] = round(max_sigma, 2)
            score += 0.35
        elif max_sigma >= _HIGH_SIGMA * 0.7:
            factors["medium_severity"] = round(max_sigma, 2)
            score += 0.15

        # --- Missing data contribution (up to 0.15) ---
        if na_rate >= _HIGH_NA_RATE:
            factors["high_na_rate"] = round(na_rate, 3)
            score += 0.15

        score = round(min(score, 1.0), 3)

        if score >= 0.6:
            risk_level = "high"
        elif score >= 0.3:
            risk_level = "medium"
        else:
            risk_level = "low"

        return {
            "risk_score": score,
            "risk_level": risk_level,
            "risk_factors": factors,
        }
