# Health Pipeline

This is an End-to-end monitoring pipeline for consumer health device data. It ingests time-series readings from blood pressure monitors, pulse oximeters, smart scales, and heart rate trackers, detects clinical concerns, and generates alerts for clinician review. Designed for adults 65+.

## Quick Start

```bash
pip install -r requirements.txt
python main.py
```

Sample outputs are in `outputfiles` if you want to inspect results without running it.

## Problems it solves

Sample outputs are included in output/ so the results can be reviewed without running the pipeline first.

What it does

The pipeline generates synthetic patient data for 20 patients across 4 device types over 30 days, which comes out to about 100K readings. The data also includes edge cases such as sensor faults, Bluetooth duplicates, time gaps, and calibration drift.

It then runs the data through five stages:

Data generation — creates patients with different clinical profiles and device readings
Ingestion — validates readings, tags faults, removes duplicates, and stores data in SQLite
Processing — computes daily aggregates, detects gaps, and builds rolling statistics
Analysis — applies three layers of detection: threshold checks, trend detection, and cross-device correlation
Alerts — prioritizes and deduplicates alerts, then outputs JSON and a clinician summary

More detail on assumptions, design decisions, and tradeoffs is in DESIGN.md
.

Output
File	Contents
output/alerts.json	Structured alerts for downstream use
output/alert_summary.txt	Clinician-readable summary by patient and severity
output/health_monitoring.db	SQLite database with patients, devices, and readings
Structure
.
├── main.py
├── health_monitor/
│   ├── config.py
│   ├── models.py
│   ├── data_generator.py
│   ├── ingestion.py
│   ├── processing.py
│   ├── analyzer.py
│   └── alert_engine.py
├── output/
├── DESIGN.md
└── requirements.txt
Requirements

Python 3.9+ with numpy and pandas.
