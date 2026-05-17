"""AI4I raw → refined data pipeline.

Reads data/raw/ai4i2020.csv and produces four clean CSV files in data/refined/:
  machines.csv          — 3 machine type nodes
  tool_runs.csv         — 10,000 sensor-reading nodes with synthetic timestamps
  failure_modes.csv     — 5 failure type nodes
  run_failure_links.csv — (run_id, failure_id) pairs for runs that had failures

Run:
    uv run python -m demos.ai4i.pipeline

Done when:
  - All four refined CSVs exist and are non-empty
  - Key columns have no null values
  - A sample of rows validates against the Pydantic ToolRun schema
  - event_time column contains valid ISO 8601 strings
"""

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

RAW_DIR = Path(__file__).parent / "data" / "raw"
REFINED_DIR = Path(__file__).parent / "data" / "refined"

# Synthetic base timestamp: dataset has no real timestamps.
# Each row is 6 minutes apart → 10,000 rows spans ~41.7 days.
_BASE_TIME = datetime(2024, 1, 1, 0, 0, 0)
_ROW_INTERVAL_MINUTES = 6

_FAILURE_COLS = ["TWF", "HDF", "PWF", "OSF", "RNF"]

_COLUMN_RENAME = {
    "Air temperature": "air_temp_k",
    "Process temperature": "process_temp_k",
    "Rotational speed": "rotational_speed_rpm",
    "Torque": "torque_nm",
    "Tool wear": "tool_wear_min",
    "Machine failure": "machine_failure",
    "Product ID": "product_id",
}


def run() -> None:
    REFINED_DIR.mkdir(parents=True, exist_ok=True)

    raw = _load_raw()
    _validate_raw(raw)
    df = _transform(raw)

    _write_machines(df)
    _write_failure_modes()
    _write_tool_runs(df)
    _write_run_failure_links(df)
    _validate_refined(df)

    print("AI4I pipeline complete.")
    print(f"  machines:          {len(df['machine_id'].unique())} rows")
    print(f"  tool_runs:         {len(df):,} rows")
    print(f"  failure_modes:     5 rows")
    links = _count_links(df)
    print(f"  run_failure_links: {links:,} rows")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_raw() -> pd.DataFrame:
    path = RAW_DIR / "ai4i2020.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"Raw data not found at {path}. "
            "Run: uv run python -m demos.ai4i.data.download"
        )
    return pd.read_csv(path)


def _validate_raw(df: pd.DataFrame) -> None:
    required = [
        "UID", "Product ID", "Type",
        "Air temperature", "Process temperature",
        "Rotational speed", "Torque", "Tool wear",
        "Machine failure", *_FAILURE_COLS,
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Raw CSV is missing columns: {missing}")

    assert set(df["Type"].unique()).issubset({"L", "M", "H"}), \
        "Unexpected values in 'Type' column"
    assert df["Machine failure"].isin([0, 1]).all(), \
        "'Machine failure' must be 0 or 1"
    for col in _FAILURE_COLS:
        assert df[col].isin([0, 1]).all(), f"'{col}' must be 0 or 1"

    numeric = [
        "Air temperature", "Process temperature",
        "Rotational speed", "Torque", "Tool wear",
    ]
    for col in numeric:
        assert df[col].notna().all(), f"Null values found in '{col}'"
        assert (df[col] >= 0).all(), f"Negative values found in '{col}'"

    print(f"Raw validation passed: {len(df):,} rows, {len(df.columns)} columns.")


def _transform(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    df = df.rename(columns=_COLUMN_RENAME)

    df["run_id"] = df["UID"].apply(lambda x: f"RUN_{int(x):05d}")
    df["machine_id"] = "MACHINE_" + df["Type"]
    df["machine_failure"] = df["machine_failure"].astype(bool)
    df["event_time"] = df["UID"].apply(
        lambda x: (_BASE_TIME + timedelta(minutes=(int(x) - 1) * _ROW_INTERVAL_MINUTES)).isoformat()
    )
    return df


def _write_machines(df: pd.DataFrame) -> None:
    machines = (
        df[["machine_id", "Type"]]
        .drop_duplicates()
        .rename(columns={"Type": "machine_type"})
        .sort_values("machine_id")
    )
    machines.to_csv(REFINED_DIR / "machines.csv", index=False)


def _write_failure_modes() -> None:
    records = [
        {"failure_id": "TWF", "failure_name": "Tool Wear Failure"},
        {"failure_id": "HDF", "failure_name": "Heat Dissipation Failure"},
        {"failure_id": "PWF", "failure_name": "Power Failure"},
        {"failure_id": "OSF", "failure_name": "Overstrain Failure"},
        {"failure_id": "RNF", "failure_name": "Random Failure"},
    ]
    pd.DataFrame(records).to_csv(REFINED_DIR / "failure_modes.csv", index=False)


def _write_tool_runs(df: pd.DataFrame) -> None:
    cols = [
        "run_id", "machine_id", "product_id",
        "air_temp_k", "process_temp_k", "rotational_speed_rpm",
        "torque_nm", "tool_wear_min", "machine_failure", "event_time",
    ]
    df[cols].to_csv(REFINED_DIR / "tool_runs.csv", index=False)


def _write_run_failure_links(df: pd.DataFrame) -> None:
    melted = df[["run_id", *_FAILURE_COLS]].melt(
        id_vars="run_id",
        value_vars=_FAILURE_COLS,
        var_name="target_id",
        value_name="occurred",
    )
    links = (
        melted[melted["occurred"] == 1][["run_id", "target_id"]]
        .rename(columns={"run_id": "source_id"})
    )
    links.to_csv(REFINED_DIR / "run_failure_links.csv", index=False)


def _count_links(df: pd.DataFrame) -> int:
    return int(df[_FAILURE_COLS].values.sum())


def _validate_refined(df: pd.DataFrame) -> None:
    from demos.ai4i.schema import ToolRun

    sample = df.head(20)
    errors: list[str] = []
    for _, row in sample.iterrows():
        try:
            ToolRun(
                run_id=row["run_id"],
                machine_id=row["machine_id"],
                product_id=row["product_id"],
                air_temp_k=float(row["air_temp_k"]),
                process_temp_k=float(row["process_temp_k"]),
                rotational_speed_rpm=float(row["rotational_speed_rpm"]),
                torque_nm=float(row["torque_nm"]),
                tool_wear_min=float(row["tool_wear_min"]),
                machine_failure=bool(row["machine_failure"]),
                event_time=str(row["event_time"]),
            )
        except ValidationError as exc:
            errors.append(f"Row {row['run_id']}: {exc}")

    if errors:
        raise ValueError(f"Schema validation failed:\n" + "\n".join(errors))

    # Spot-check event_time format
    datetime.fromisoformat(str(sample.iloc[0]["event_time"]))
    print("Refined schema validation passed (20-row sample).")


if __name__ == "__main__":
    run()
