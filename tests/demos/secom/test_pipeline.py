"""Tests for the SECOM raw→refined pipeline output."""

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

REFINED = Path(__file__).parent.parent.parent.parent / "demos" / "secom" / "data" / "refined"


@pytest.fixture(scope="module")
def lots() -> pd.DataFrame:
    return pd.read_csv(REFINED / "lots.csv")


@pytest.fixture(scope="module")
def yield_outcomes() -> pd.DataFrame:
    return pd.read_csv(REFINED / "yield_outcomes.csv")


@pytest.fixture(scope="module")
def spc_alarms() -> pd.DataFrame:
    return pd.read_csv(REFINED / "spc_alarms.csv")


@pytest.fixture(scope="module")
def lot_alarm_links() -> pd.DataFrame:
    return pd.read_csv(REFINED / "lot_alarm_links.csv")


# ---------------------------------------------------------------------------
# File existence
# ---------------------------------------------------------------------------

def test_all_refined_files_exist():
    for name in ("lots.csv", "yield_outcomes.csv", "spc_alarms.csv", "lot_alarm_links.csv"):
        assert (REFINED / name).exists(), f"{name} is missing"


# ---------------------------------------------------------------------------
# lots.csv
# ---------------------------------------------------------------------------

def test_lots_row_count(lots):
    assert len(lots) == 1_567


def test_lots_required_columns(lots):
    required = {"lot_id", "event_time", "yield_pass", "sensor_na_rate", "n_spc_alarms"}
    assert required.issubset(set(lots.columns))


def test_lots_no_nulls_in_key_cols(lots):
    key = ["lot_id", "event_time", "yield_pass", "sensor_na_rate", "n_spc_alarms"]
    assert lots[key].isnull().sum().sum() == 0


def test_lots_lot_id_format(lots):
    sample = lots["lot_id"].head(5)
    for lid in sample:
        assert lid.startswith("LOT_"), f"Bad lot_id: {lid}"
        assert len(lid) == 8, f"lot_id wrong length: {lid}"


def test_lots_lot_ids_unique(lots):
    assert lots["lot_id"].nunique() == len(lots)


def test_lots_yield_pass_distribution(lots):
    pass_count = lots["yield_pass"].sum()
    fail_count = (~lots["yield_pass"]).sum()
    assert pass_count == 1_463
    assert fail_count == 104


def test_lots_sensor_na_rate_bounds(lots):
    assert (lots["sensor_na_rate"] >= 0).all()
    assert (lots["sensor_na_rate"] <= 1).all()


def test_lots_n_spc_alarms_non_negative(lots):
    assert (lots["n_spc_alarms"] >= 0).all()


def test_lots_event_time_iso8601(lots):
    first = lots["event_time"].iloc[0]
    dt = datetime.fromisoformat(first)
    assert dt.year == 2008


def test_lots_event_times_in_expected_range(lots):
    times = pd.to_datetime(lots["event_time"])
    assert times.min().year == 2008
    assert times.max().year == 2008
    assert times.min() < times.max()


# ---------------------------------------------------------------------------
# yield_outcomes.csv
# ---------------------------------------------------------------------------

def test_yield_outcomes_row_count(yield_outcomes):
    assert len(yield_outcomes) == 2


def test_yield_outcomes_ids(yield_outcomes):
    assert set(yield_outcomes["outcome_id"]) == {"PASS", "FAIL"}


def test_yield_outcomes_no_nulls(yield_outcomes):
    assert yield_outcomes.isnull().sum().sum() == 0


# ---------------------------------------------------------------------------
# spc_alarms.csv
# ---------------------------------------------------------------------------

def test_spc_alarms_columns(spc_alarms):
    required = {
        "alarm_id", "feature_name", "population_mean", "population_std",
        "upper_control_limit", "lower_control_limit", "total_alarm_count",
    }
    assert required.issubset(set(spc_alarms.columns))


def test_spc_alarms_non_empty(spc_alarms):
    assert len(spc_alarms) > 0


def test_spc_alarms_all_have_alarms(spc_alarms):
    assert (spc_alarms["total_alarm_count"] > 0).all()


def test_spc_alarms_ucl_above_lcl(spc_alarms):
    assert (spc_alarms["upper_control_limit"] > spc_alarms["lower_control_limit"]).all()


def test_spc_alarms_std_positive(spc_alarms):
    assert (spc_alarms["population_std"] > 0).all()


def test_spc_alarms_id_format(spc_alarms):
    sample = spc_alarms["alarm_id"].head(5)
    for aid in sample:
        assert aid.startswith("SPC_ATTR_"), f"Bad alarm_id: {aid}"


# ---------------------------------------------------------------------------
# lot_alarm_links.csv
# ---------------------------------------------------------------------------

def test_lot_alarm_links_columns(lot_alarm_links):
    assert set(lot_alarm_links.columns) == {"lot_id", "alarm_id", "sensor_value", "sigma_deviation"}


def test_lot_alarm_links_non_empty(lot_alarm_links):
    assert len(lot_alarm_links) > 0


def test_lot_alarm_links_sigma_exceeds_threshold(lot_alarm_links):
    assert (lot_alarm_links["sigma_deviation"].abs() > 3.0).all()


def test_lot_alarm_links_lot_ids_are_valid(lot_alarm_links):
    sample = lot_alarm_links["lot_id"].head(10)
    for lid in sample:
        assert lid.startswith("LOT_"), f"Bad lot_id in links: {lid}"


def test_lot_alarm_links_alarm_ids_are_valid(lot_alarm_links, spc_alarms):
    valid_alarm_ids = set(spc_alarms["alarm_id"])
    link_alarm_ids = set(lot_alarm_links["alarm_id"])
    assert link_alarm_ids.issubset(valid_alarm_ids)


def test_lot_alarm_links_counts_match_lots(lot_alarm_links, lots):
    link_counts = lot_alarm_links.groupby("lot_id").size()
    lots_indexed = lots.set_index("lot_id")["n_spc_alarms"]
    for lot_id, count in link_counts.items():
        assert lots_indexed.get(lot_id, 0) == count, \
            f"n_spc_alarms mismatch for {lot_id}"
