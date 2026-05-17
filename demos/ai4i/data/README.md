# AI4I 2020 Predictive Maintenance Dataset

**Source:** UCI Machine Learning Repository, Dataset ID 601
**Citation:** Matzka, S. (2020). AI4I 2020 Predictive Maintenance Dataset. UCI Machine Learning Repository.

## Raw data (`raw/ai4i2020.csv`)

Downloaded via `ucimlrepo` (id=601). 10,000 rows, 14 columns.

| Column | Description |
|---|---|
| UDI | Row index (1–10000) |
| Product ID | Product identifier with quality prefix (L/M/H) |
| Type | Machine quality variant: L (low), M (medium), H (high) |
| Air temperature [K] | Air temperature in Kelvin |
| Process temperature [K] | Process temperature in Kelvin |
| Rotational speed [rpm] | Rotational speed in RPM |
| Torque [Nm] | Torque in Newton-metres |
| Tool wear [min] | Cumulative tool wear in minutes |
| Machine failure | 1 if any failure occurred, else 0 |
| TWF | Tool Wear Failure |
| HDF | Heat Dissipation Failure |
| PWF | Power Failure |
| OSF | Overstrain Failure |
| RNF | Random Failure |

## Refined data (`refined/`)

Produced by `demos/ai4i/pipeline.py`. Four files:

| File | Description | Rows |
|---|---|---|
| `machines.csv` | One row per machine type (L/M/H) | 3 |
| `tool_runs.csv` | One row per sensor reading with clean IDs and synthetic timestamps | 10,000 |
| `failure_modes.csv` | One row per failure type | 5 |
| `run_failure_links.csv` | One row per (run, failure) pair where the failure occurred | varies |

## Refresh

```bash
uv run python -m demos.ai4i.data.download   # fetch raw from UCI
uv run python -m demos.ai4i.pipeline        # raw → refined
```
