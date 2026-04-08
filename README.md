# Health Pipeline

This is an End-to-end monitoring pipeline for consumer health device data. It ingests time-series readings from blood pressure monitors, pulse oximeters, smart scales, and heart rate trackers, detects clinical concerns, and generates alerts for clinician review. Designed for adults 65+.

## Quick Start

```bash
pip install -r requirements.txt
python main.py
```

Sample outputs are in `output/` if you want to inspect results without running it.

## Problems it solves

Generates synthetic patient data (20 patients × 4 devices × 30 days, ~100K readings) with realistic edge cases — sensor faults, Bluetooth duplicates, time gaps, calibration drift — and runs it through a 5-stage pipeline:

1. **Data generation** — synthetic patients with different clinical profiles
2. **Ingestion** — validate, tag faults, deduplicate, store to SQLite
3. **Processing** — daily aggregation, gap detection, rolling statistics
4. **Analysis** — three detection layers: threshold checks → trend detection → cross-device correlation
5. **Alerts** — prioritize, deduplicate, output JSON + clinician summary

Design rationale, assumptions, and tradeoffs are in [DESIGN.md](DESIGN.md).

## Output

| `output/alerts.json` | Structured alerts (machine-readable) |
| `output/alert_summary.txt` | Clinician summary by patient and severity |
| `output/health_monitoring.db` | SQLite with all patients, devices, readings |

## Structure

├── main.py                           # Entry point
│   ├── config.py                     # Thresholds, parameters
│   ├── models.py                     # Patient, Device, Reading + DB ops
│   ├── data_generator.py             # Synthetic data with edge cases
│   ├── ingestion.py                  # Validation, dedup, storage
│   ├── processing.py                 # Cleaning, aggregation, rolling stats
│   ├── analyzer.py                   # Three-layer analysis
│   └── alert_engine.py               # Prioritization and output
├── DESIGN.md                         # Assumptions, tradeoffs, decisions
└── requirements.txt
```

## Requirements

Python 3.9+, numpy, pandas.
