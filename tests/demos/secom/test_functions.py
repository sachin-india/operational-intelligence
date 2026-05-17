"""Unit tests for PredictYieldRisk function."""

import pytest

from demos.secom.track_b.functions import PredictYieldRisk

fn = PredictYieldRisk()

_SAFE = {
    "n_spc_alarms": 1,
    "sensor_na_rate": 0.05,
    "max_sigma_dev": 3.2,
}


def _override(**kw):
    return {**_SAFE, **kw}


def test_returns_required_keys():
    result = fn.compute(_SAFE)
    assert "risk_score" in result
    assert "risk_level" in result
    assert "risk_factors" in result


def test_zero_alarms_gives_low_risk():
    result = fn.compute({"n_spc_alarms": 0, "sensor_na_rate": 0.0, "max_sigma_dev": 0.0})
    assert result["risk_level"] == "low"
    assert result["risk_score"] < 0.3


def test_high_alarm_count_raises_score():
    result = fn.compute(_override(n_spc_alarms=10, max_sigma_dev=3.1))
    assert result["risk_factors"].get("high_alarm_count") == 10
    assert result["risk_score"] >= 0.5


def test_medium_alarm_count():
    result = fn.compute(_override(n_spc_alarms=5, max_sigma_dev=3.1))
    assert result["risk_factors"].get("medium_alarm_count") == 5


def test_low_alarm_count_contributes_small_score():
    result = fn.compute({"n_spc_alarms": 2, "sensor_na_rate": 0.0, "max_sigma_dev": 0.0})
    assert 0 < result["risk_score"] < 0.3


def test_high_severity_raises_score():
    result = fn.compute(_override(n_spc_alarms=0, max_sigma_dev=6.0))
    assert "high_severity" in result["risk_factors"]
    assert result["risk_score"] >= 0.35


def test_medium_severity():
    result = fn.compute(_override(n_spc_alarms=0, max_sigma_dev=4.0))
    assert "medium_severity" in result["risk_factors"]


def test_no_severity_below_threshold():
    result = fn.compute(_override(n_spc_alarms=0, max_sigma_dev=3.1))
    assert "high_severity" not in result["risk_factors"]
    assert "medium_severity" not in result["risk_factors"]


def test_high_na_rate_contributes_penalty():
    result = fn.compute({"n_spc_alarms": 0, "sensor_na_rate": 0.20, "max_sigma_dev": 0.0})
    assert "high_na_rate" in result["risk_factors"]
    assert result["risk_score"] >= 0.15


def test_risk_level_high_at_0_6():
    result = fn.compute({"n_spc_alarms": 10, "sensor_na_rate": 0.0, "max_sigma_dev": 6.0})
    assert result["risk_level"] == "high"
    assert result["risk_score"] >= 0.6


def test_risk_level_medium():
    # medium alarm count (0.25) + medium severity (0.15) = 0.40 → medium
    result = fn.compute({"n_spc_alarms": 5, "sensor_na_rate": 0.0, "max_sigma_dev": 4.0})
    assert result["risk_level"] == "medium"
    assert 0.3 <= result["risk_score"] < 0.6


def test_risk_score_capped_at_1():
    result = fn.compute({"n_spc_alarms": 20, "sensor_na_rate": 0.5, "max_sigma_dev": 10.0})
    assert result["risk_score"] <= 1.0
