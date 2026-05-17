"""Download the SECOM Semiconductor Manufacturing dataset from UCI.

Run once to populate data/raw/, then commit those files.
The raw files are committed so future runs do not need network access.

Usage:
    uv run python -m demos.secom.data.download
"""

from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).parent / "raw"


def download() -> None:
    from ucimlrepo import fetch_ucirepo

    print("Fetching SECOM dataset from UCI (id=179)...")
    dataset = fetch_ucirepo(id=179)

    # ucimlrepo returns everything in dataset.data.original for this dataset.
    df: pd.DataFrame = dataset.data.original

    print(f"Shape: {df.shape}")
    print(f"Columns[:5]: {list(df.columns[:5])}")
    print(f"class distribution: {df['class'].value_counts().to_dict()}")
    print(f"Missing rate: {df.isna().mean().mean():.1%}")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(RAW_DIR / "secom.csv", index=False)
    print(f"Saved secom.csv  ({df.shape[0]} rows × {df.shape[1]} cols) → {RAW_DIR / 'secom.csv'}")


if __name__ == "__main__":
    download()
