"""Tests for the AI4I raw→refined pipeline output."""

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

REFINED = Path(__file__).parent.parent.parent.parent / "demos" / "ai4i" / "data" / "refined"


@pytest.fixture(scope="module")
def machines() -> pd.DataFrame:
    return pd.read_csv(REFINED / "machines.csv")


@pytest.fixture(scope="module")
def tool_runs() -> pd.DataFrame:
    return pd.read_csv(REFINED / "tool_runs.csv")


@pytest.fixture(scope="module")
def failure_modes() -> pd.DataFrame:
    return pd.read_csv(REFINED / "failure_modes.csv")


@pytest.fixture(scope="module")
def run_failure_links() -> pd.DataFrame:
    return pd.read_csv(REFINED / "run_failure_links.csv")


# ---------------------------------------------------------------------------
# File existence
# ---------------------------------------------------------------------------

def test_all_refined_files_exist():
    for name in ("machines.csv", "tool_runs.csv", "failure_modes.csv", "run_failure_links.csv"):
        assert (REFINED / name).exists(), f"{name} is missing"


# ---------------------------------------------------------------------------
# machines.csv
# ---------------------------------------------------------------------------

def test_machines_row_count(machines):
    assert len(machines) == 3


def test_machines_columns(machines):
    assert set(machines.columns) == {"machine_id", "machine_type"}


def test_machines_types_are_l_m_h(machines):
    assert set(machines["machine_type"]) == {"L", "M", "H"}


def test_machines_ids_format(machines):
    for mid in machines["machine_id"]:
        assert mid.startswith("MACHINE_"), f"Bad machine_id: {mid}"


def test_machines_no_nulls(machines):
    assert machines.isnull().sum().sum() == 0


# ---------------------------------------------------------------------------
# tool_runs.csv
# ---------------------------------------------------------------------------

def test_tool_runs_row_count(tool_runs):
    assert len(tool_runs) == 10_000


def test_tool_runs_required_columns(tool_runs):
    required = {
        "run_id", "machine_id", "product_id",
        "air_temp_k", "process_temp_k", "rotational_speed_rpm",
        "torque_nm", "tool_wear_min", "machine_failure", "event_time",
    }
    assert required.issubset(set(tool_runs.columns))


def test_tool_runs_no_nulls_in_key_cols(tool_runs):
    key_cols = [
        "run_id", "machine_id", "air_temp_k", "process_temp_k",
        "rotational_speed_rpm", "torque_nm", "tool_wear_min",
        "machine_failure", "event_time",
    ]
    assert tool_runs[key_cols].isnull().sum().sum() == 0


def test_tool_runs_run_id_format(tool_runs):
    sample = tool_runs["run_id"].head(10)
    for rid in sample:
        assert rid.startswith("RUN_"), f"Bad run_id: {rid}"
        assert len(rid) == 9, f"run_id wrong length: {rid}"


def test_tool_runs_machine_id_values(tool_runs):
    assert set(tool_runs["machine_id"].unique()).issubset(
        {"MACHINE_L", "MACHINE_M", "MACHINE_H"}
    )


def test_tool_runs_numeric_columns_non_negative(tool_runs):
    for col in ("air_temp_k", "process_temp_k", "rotational_speed_rpm", "torque_nm", "tool_wear_min"):
        assert (tool_runs[col] >= 0).all(), f"Negative values in {col}"


def test_tool_runs_event_time_iso8601(tool_runs):
    first = tool_runs["event_time"].iloc[0]
    dt = datetime.fromisoformat(first)
    assert dt.year == 2024
    assert dt.month == 1
    assert dt.day == 1


def test_tool_runs_event_time_interval(tool_runs):
    t0 = datetime.fromisoformat(tool_runs["event_time"].iloc[0])
    t1 = datetime.fromisoformat(tool_runs["event_time"].iloc[1])
    assert (t1 - t0).seconds == 6 * 60


def test_tool_runs_run_ids_unique(tool_runs):
    assert tool_runs["run_id"].nunique() == len(tool_runs)


# ---------------------------------------------------------------------------
# failure_modes.csv
# ---------------------------------------------------------------------------

def test_failure_modes_row_count(failure_modes):
    assert len(failure_modes) == 5


def test_failure_modes_ids(failure_modes):
    assert set(failure_modes["failure_id"]) == {"TWF", "HDF", "PWF", "OSF", "RNF"}


def test_failure_modes_no_nulls(failure_modes):
    assert failure_modes.isnull().sum().sum() == 0


# ---------------------------------------------------------------------------
# run_failure_links.csv
# ---------------------------------------------------------------------------

def test_run_failure_links_columns(run_failure_links):
    assert set(run_failure_links.columns) == {"source_id", "target_id"}


def test_run_failure_links_target_ids_valid(run_failure_links):
    assert set(run_failure_links["target_id"].unique()).issubset(
        {"TWF", "HDF", "PWF", "OSF", "RNF"}
    )


def test_run_failure_links_source_ids_are_run_ids(run_failure_links):
    for sid in run_failure_links["source_id"].head(20):
        assert sid.startswith("RUN_"), f"Bad source_id: {sid}"


def test_run_failure_links_non_empty(run_failure_links):
    assert len(run_failure_links) > 0
