# SECOM Semiconductor Manufacturing Dataset

**Source:** UCI Machine Learning Repository, Dataset ID 179
**Citation:** McCann, M. & Johnston, A. (2008). SECOM. UCI Machine Learning Repository.
**Time range:** July 19 – October 17, 2008

## Raw data (`raw/secom.csv`)

Downloaded via `ucimlrepo` (id=179). 1,567 rows × 592 columns.

| Column | Description |
|---|---|
| class | Quality outcome: -1 = PASS, 1 = FAIL |
| timestamp | Production timestamp (DD/MM/YYYY HH:MM:SS) |
| Attribute 1 – Attribute 590 | Sensor/process feature readings |

**Class distribution:** 1,463 PASS (93.4%) / 104 FAIL (6.6%)
**Missing value rate:** ~4.5% overall; 8 features >80% missing; 52 features fully observed.

Note: class=-1 means PASS (not a defect). The convention is inverted from intuition
because 1 originally denoted the anomaly class in the fault-detection framing.

## Refined data (`refined/`)

Produced by `demos/secom/pipeline.py`. Four files:

| File | Description | Rows |
|---|---|---|
| `lots.csv` | One row per wafer lot run, with summary stats | 1,567 |
| `yield_outcomes.csv` | PASS / FAIL outcome type nodes | 2 |
| `spc_alarms.csv` | One row per sensor feature with ≥1 alarm; includes control limits | 440 |
| `lot_alarm_links.csv` | One row per (lot, feature) crossing 3σ limits | 6,115 |

### SPC alarm logic

For each of the 590 sensor features:
1. Compute population mean and std across all 1,567 lots (ignoring NaN).
2. Control limits: UCL = mean + 3σ, LCL = mean − 3σ.
3. Any individual lot reading outside [LCL, UCL] generates a TRIGGERED_ALARM link.
4. Features with std = 0 or <10 valid readings are excluded.

This mirrors the Statistical Process Control (SPC) approach used in real fabs.

## Refresh

```bash
uv run python -m demos.secom.data.download   # fetch raw from UCI
uv run python -m demos.secom.pipeline        # raw → refined
```
