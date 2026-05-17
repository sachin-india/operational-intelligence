"""Download the AI4I 2020 Predictive Maintenance dataset from UCI.

Run once to populate data/raw/ai4i2020.csv, then commit that file.
The raw file is committed so future runs do not need network access.

Usage:
    uv run python -m demos.ai4i.data.download
"""

from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).parent / "raw"


def download() -> None:
    from ucimlrepo import fetch_ucirepo

    print("Fetching AI4I 2020 Predictive Maintenance dataset from UCI (id=601)...")
    dataset = fetch_ucirepo(id=601)

    # Combine features and targets into one flat DataFrame.
    df: pd.DataFrame = pd.concat(
        [dataset.data.features, dataset.data.targets], axis=1
    )

    # Some ucimlrepo versions strip UDI / Product ID into metadata —
    # restore them if they are available there.
    if "UDI" not in df.columns and hasattr(dataset.data, "original"):
        df = dataset.data.original.copy()

    output = RAW_DIR / "ai4i2020.csv"
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False)
    print(f"Saved {len(df):,} rows → {output}")
    print(f"Columns: {list(df.columns)}")


if __name__ == "__main__":
    download()
