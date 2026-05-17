"""SECOM raw → refined data pipeline.

Reads data/raw/secom.csv and produces four clean CSV files in data/refined/:
  lots.csv            — 1,567 lot nodes with summary stats
  yield_outcomes.csv  — 2 outcome type nodes (PASS / FAIL)
  spc_alarms.csv      — one node per sensor feature that ever crossed 3σ
  lot_alarm_links.csv — (lot_id, alarm_id, sensor_value, sigma_deviation)
                        one row per (lot, feature) pair where the feature crossed 3σ

Run:
    uv run python -m demos.secom.pipeline

Done when:
  - All four refined CSVs exist and are non-empty
  - Key columns have no null values
  - A sample of rows validates against the Pydantic Lot schema
  - event_time column contains valid ISO 8601 strings

Key design decisions:
  - class=-1 → yield_pass=True (pass), class=1 → yield_pass=False (fail)
  - SPC limits: mean ± 3σ computed per feature across all lots (population stats)
  - Features with std=0 or all-NaN are excluded from SPC alarm nodes
  - lot_alarm_links only includes rows where |sigma_deviation| > 3.0
"""

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from pydantic import ValidationError

RAW_DIR = Path(__file__).parent / "data" / "raw"
REFINED_DIR = Path(__file__).parent / "data" / "refined"

_SPC_SIGMA = 3.0  # control limit threshold


def run() -> None:
    REFINED_DIR.mkdir(parents=True, exist_ok=True)

    raw = _load_raw()
    _validate_raw(raw)

    feature_cols = [c for c in raw.columns if c.startswith("Attribute")]
    spc_stats = _compute_spc_stats(raw, feature_cols)
    alarm_links = _compute_alarm_links(raw, feature_cols, spc_stats)

    lots_df = _build_lots(raw, alarm_links)
    alarm_features = spc_stats[spc_stats["has_alarms"]]

    _write_lots(lots_df)
    _write_yield_outcomes()
    _write_spc_alarms(alarm_features)
    _write_lot_alarm_links(alarm_links)
    _validate_refined(lots_df)

    print("SECOM pipeline complete.")
    print(f"  lots:            {len(lots_df):,} rows  "
          f"({lots_df['yield_pass'].sum()} pass / {(~lots_df['yield_pass']).sum()} fail)")
    print(f"  yield_outcomes:  2 rows")
    print(f"  spc_alarms:      {len(alarm_features):,} rows")
    print(f"  lot_alarm_links: {len(alarm_links):,} rows")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_raw() -> pd.DataFrame:
    path = RAW_DIR / "secom.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"Raw data not found at {path}. "
            "Run: uv run python -m demos.secom.data.download"
        )
    return pd.read_csv(path)


def _validate_raw(df: pd.DataFrame) -> None:
    required = ["class", "timestamp"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Raw CSV is missing columns: {missing}")

    assert set(df["class"].unique()).issubset({-1, 1}), \
        "Unexpected values in 'class' column (expected -1 or 1)"

    feature_cols = [c for c in df.columns if c.startswith("Attribute")]
    assert len(feature_cols) == 590, \
        f"Expected 590 feature columns, got {len(feature_cols)}"

    print(f"Raw validation passed: {len(df):,} rows, {len(df.columns)} columns, "
          f"{len(feature_cols)} feature columns.")


def _compute_spc_stats(raw: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    """Compute mean/std/UCL/LCL for each sensor feature across all lots."""
    stats = []
    for col in feature_cols:
        series = raw[col].dropna()
        if len(series) < 10:
            continue
        mean = series.mean()
        std = series.std()
        if std == 0 or np.isnan(std):
            continue
        ucl = mean + _SPC_SIGMA * std
        lcl = mean - _SPC_SIGMA * std
        attr_num = int(col.split(" ")[1])
        alarm_id = f"SPC_ATTR_{attr_num:03d}"
        stats.append({
            "alarm_id": alarm_id,
            "feature_name": col,
            "population_mean": round(mean, 6),
            "population_std": round(std, 6),
            "upper_control_limit": round(ucl, 6),
            "lower_control_limit": round(lcl, 6),
        })

    df = pd.DataFrame(stats)
    # We'll fill total_alarm_count and has_alarms after computing links.
    df["total_alarm_count"] = 0
    df["has_alarms"] = False
    return df


def _compute_alarm_links(
    raw: pd.DataFrame,
    feature_cols: list[str],
    spc_stats: pd.DataFrame,
) -> pd.DataFrame:
    """For each (lot, feature) pair, record if the reading crossed 3σ.

    Mutates spc_stats in-place to add total_alarm_count and has_alarms columns.
    """
    # Build lookup: feature_name → (alarm_id, mean, std)
    feature_lookup: dict[str, dict] = {
        row["feature_name"]: row
        for _, row in spc_stats.iterrows()
    }

    records = []
    for row_idx, row in raw.iterrows():
        lot_id = f"LOT_{int(row_idx) + 1:04d}"
        for col in feature_cols:
            val = row[col]
            if col not in feature_lookup or pd.isna(val):
                continue
            s = feature_lookup[col]
            sigma_dev = (val - s["population_mean"]) / s["population_std"]
            if abs(sigma_dev) > _SPC_SIGMA:
                records.append({
                    "lot_id": lot_id,
                    "alarm_id": s["alarm_id"],
                    "sensor_value": round(float(val), 6),
                    "sigma_deviation": round(float(sigma_dev), 4),
                })

    links = pd.DataFrame(records) if records else pd.DataFrame(
        columns=["lot_id", "alarm_id", "sensor_value", "sigma_deviation"]
    )

    # Update alarm counts back into spc_stats (mutates the passed DataFrame).
    counts = links.groupby("alarm_id").size() if not links.empty else pd.Series(dtype=int)
    spc_stats["total_alarm_count"] = spc_stats["alarm_id"].map(counts).fillna(0).astype(int)
    spc_stats["has_alarms"] = spc_stats["total_alarm_count"] > 0

    return links


def _build_lots(raw: pd.DataFrame, alarm_links: pd.DataFrame) -> pd.DataFrame:
    feature_cols = [c for c in raw.columns if c.startswith("Attribute")]

    alarm_counts = (
        alarm_links.groupby("lot_id").size().rename("n_spc_alarms")
        if not alarm_links.empty else pd.Series(name="n_spc_alarms", dtype=int)
    )

    rows = []
    for idx, row in raw.iterrows():
        lot_id = f"LOT_{int(idx) + 1:04d}"
        ts = _parse_timestamp(str(row["timestamp"]))
        na_rate = round(row[feature_cols].isna().mean(), 4)
        n_alarms = int(alarm_counts.get(lot_id, 0))
        yield_pass = bool(int(row["class"]) == -1)

        rows.append({
            "lot_id": lot_id,
            "event_time": ts,
            "yield_pass": yield_pass,
            "sensor_na_rate": na_rate,
            "n_spc_alarms": n_alarms,
        })

    return pd.DataFrame(rows)


def _parse_timestamp(ts_str: str) -> str:
    """Convert '19/07/2008 11:55:00' to ISO 8601."""
    try:
        return datetime.strptime(ts_str, "%d/%m/%Y %H:%M:%S").isoformat()
    except ValueError:
        return datetime.strptime(ts_str, "%m/%d/%Y %H:%M").isoformat()


def _write_lots(df: pd.DataFrame) -> None:
    df.to_csv(REFINED_DIR / "lots.csv", index=False)


def _write_yield_outcomes() -> None:
    pd.DataFrame([
        {"outcome_id": "PASS", "outcome_label": "Passed quality control"},
        {"outcome_id": "FAIL", "outcome_label": "Failed quality control"},
    ]).to_csv(REFINED_DIR / "yield_outcomes.csv", index=False)


def _write_spc_alarms(df: pd.DataFrame) -> None:
    cols = [
        "alarm_id", "feature_name",
        "population_mean", "population_std",
        "upper_control_limit", "lower_control_limit",
        "total_alarm_count",
    ]
    df[cols].to_csv(REFINED_DIR / "spc_alarms.csv", index=False)


def _write_lot_alarm_links(df: pd.DataFrame) -> None:
    df.to_csv(REFINED_DIR / "lot_alarm_links.csv", index=False)


def _validate_refined(lots_df: pd.DataFrame) -> None:
    from demos.secom.schema import Lot

    sample = lots_df.head(20)
    errors: list[str] = []
    for _, row in sample.iterrows():
        try:
            Lot(
                lot_id=row["lot_id"],
                event_time=row["event_time"],
                yield_pass=bool(row["yield_pass"]),
                sensor_na_rate=float(row["sensor_na_rate"]),
                n_spc_alarms=int(row["n_spc_alarms"]),
            )
        except ValidationError as exc:
            errors.append(f"Row {row['lot_id']}: {exc}")

    if errors:
        raise ValueError("Schema validation failed:\n" + "\n".join(errors))

    datetime.fromisoformat(str(sample.iloc[0]["event_time"]))
    print("Refined schema validation passed (20-row sample).")


if __name__ == "__main__":
    run()
