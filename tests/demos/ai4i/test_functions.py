"""Unit tests for PredictFailureRisk function."""

import pytest

from demos.ai4i.track_b.functions import PredictFailureRisk

fn = PredictFailureRisk()

# Sensor readings that shouldn't trigger any rule.
_SAFE = {
    "air_temp_k": 298.0,
    "process_temp_k": 308.0,     # diff = 10 K (above 8.6)
    "rotational_speed_rpm": 1500.0,
    "torque_nm": 40.0,
    "tool_wear_min": 50.0,
    "machine_id": "MACHINE_M",
}


def _override(**kw):
    return {**_SAFE, **kw}


# ---------------------------------------------------------------------------
# Basic interface
# ---------------------------------------------------------------------------

def test_returns_required_keys():
    result = fn.compute(_SAFE)
    assert "risk_score" in result
    assert "risk_level" in result
    assert "risk_factors" in result


def test_safe_inputs_give_low_risk():
    result = fn.compute(_SAFE)
    assert result["risk_level"] == "low"
    assert result["risk_score"] < 0.2
    assert result["risk_factors"] == {}


# ---------------------------------------------------------------------------
# TWF: Tool Wear Failure
# ---------------------------------------------------------------------------

def test_twf_critical_at_200_min():
    result = fn.compute(_override(tool_wear_min=200.0))
    assert "TWF" in result["risk_factors"]
    assert result["risk_factors"]["TWF"] == "critical"
    assert result["risk_score"] >= 0.35


def test_twf_approaching_at_150_min():
    result = fn.compute(_override(tool_wear_min=155.0))
    assert result["risk_factors"].get("TWF") == "approaching"


def test_no_twf_below_150_min():
    result = fn.compute(_override(tool_wear_min=100.0))
    assert "TWF" not in result["risk_factors"]


# ---------------------------------------------------------------------------
# HDF: Heat Dissipation Failure
# ---------------------------------------------------------------------------

def test_hdf_triggers_when_both_conditions_met():
    result = fn.compute(_override(
        air_temp_k=299.0,
        process_temp_k=305.0,  # diff = 6 K < 8.6
        rotational_speed_rpm=1300.0,  # < 1380
    ))
    assert "HDF" in result["risk_factors"]


def test_hdf_does_not_trigger_with_high_rpm():
    result = fn.compute(_override(
        air_temp_k=299.0,
        process_temp_k=305.0,  # diff < 8.6
        rotational_speed_rpm=1500.0,  # >= 1380 — no HDF
    ))
    assert "HDF" not in result["risk_factors"]


def test_hdf_does_not_trigger_with_large_temp_diff():
    result = fn.compute(_override(
        air_temp_k=298.0,
        process_temp_k=310.0,  # diff = 12 K > 8.6 — no HDF
        rotational_speed_rpm=1300.0,
    ))
    assert "HDF" not in result["risk_factors"]


# ---------------------------------------------------------------------------
# PWF: Power Failure
# ---------------------------------------------------------------------------

def test_pwf_triggers_on_low_power():
    # Very low torque × rpm → power well below 3500 W
    result = fn.compute(_override(torque_nm=5.0, rotational_speed_rpm=500.0))
    assert "PWF" in result["risk_factors"]


def test_pwf_triggers_on_high_power():
    # Very high torque × rpm → power above 9000 W
    result = fn.compute(_override(torque_nm=100.0, rotational_speed_rpm=2000.0))
    assert "PWF" in result["risk_factors"]


def test_pwf_safe_in_normal_range():
    # torque=40, rpm=1500 → power ≈ 40 * 1500 * (2π/60) ≈ 6283 W — safe
    result = fn.compute(_override(torque_nm=40.0, rotational_speed_rpm=1500.0))
    assert "PWF" not in result["risk_factors"]


# ---------------------------------------------------------------------------
# OSF: Overstrain Failure
# ---------------------------------------------------------------------------

def test_osf_triggers_on_machine_l():
    # L threshold = 11000; tool_wear=200, torque=60 → 12000 > 11000
    result = fn.compute(_override(
        tool_wear_min=200.0, torque_nm=60.0, machine_id="MACHINE_L"
    ))
    assert "OSF" in result["risk_factors"]


def test_osf_does_not_trigger_on_machine_h_same_values():
    # H threshold = 13000; 200 * 60 = 12000 < 13000 — no OSF
    result = fn.compute(_override(
        tool_wear_min=200.0, torque_nm=60.0, machine_id="MACHINE_H"
    ))
    assert "OSF" not in result["risk_factors"]


# ---------------------------------------------------------------------------
# risk_level thresholds
# ---------------------------------------------------------------------------

def test_risk_level_high_when_score_gte_0_5():
    # Trigger TWF-critical + one more rule
    result = fn.compute(_override(
        tool_wear_min=220.0,   # TWF critical: +0.4
        torque_nm=5.0,          # PWF (low power): +0.35
        rotational_speed_rpm=100.0,
    ))
    assert result["risk_level"] == "high"
    assert result["risk_score"] >= 0.5


def test_risk_score_capped_at_1():
    # Trigger all rules simultaneously.
    result = fn.compute({
        "air_temp_k": 299.0,
        "process_temp_k": 305.0,   # HDF
        "rotational_speed_rpm": 100.0,  # HDF + low power → PWF
        "torque_nm": 5.0,              # PWF
        "tool_wear_min": 250.0,        # TWF critical + OSF
        "machine_id": "MACHINE_L",
    })
    assert result["risk_score"] <= 1.0
