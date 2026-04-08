# Health Device Data Monitoring System

A system that ingests, processes, and analyzes time-series readings from consumer health devices (blood pressure monitors, pulse oximeters, smart scales, heart rate trackers) to generate clinician-facing alerts for adults aged 65+.

Built as a take-home exercise for xHealth Group — Project A.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the full pipeline
python main.py
```

That's it. The pipeline generates synthetic data, processes it, runs clinical analysis, and outputs alerts to the `output/` directory.

## What It Does

The system runs a five-stage pipeline end to end:

**Stage 1 — Data Generation.** Creates synthetic data for 20 patients across 4 device types over 30 days. The data includes realistic edge cases: missing readings, sensor faults, duplicate syncs, time gaps from device disconnection, and gradual calibration drift. Patients have different clinical profiles (healthy, hypertension, heart failure, COPD, diabetes) with appropriately different baselines.

**Stage 2 — Ingestion.** Validates each reading against physical limits, catches sensor faults, deduplicates Bluetooth sync errors, and stores everything to SQLite. Faulty readings are tagged but not dropped — in healthcare, silent data loss is worse than noisy data.

**Stage 3 — Processing.** Filters faults, detects time gaps, computes daily aggregates per patient per device type, and calculates rolling statistics (7-day mean, std, z-scores). Each device type has its own aggregation logic — for example, resting heart rate uses the 25th percentile of daily readings to naturally filter out exercise periods.

**Stage 4 — Analysis.** Runs three layers of clinical detection. Layer 1 checks single readings against clinical thresholds (e.g., SpO2 < 90%, BP > 180/120). Layer 2 detects trends using rolling windows (e.g., weight gain > 2kg in 7 days). Layer 3 correlates signals across multiple devices (e.g., weight gain + elevated BP + rising HR = possible heart failure decompensation).

**Stage 5 — Alert Generation.** Prioritizes and deduplicates alerts, then outputs a structured JSON file and a clinician-readable text summary.

## Output Files

After running `python main.py`, you'll find these in `output/`:

| File | Description |
|------|-------------|
| `health_monitoring.db` | SQLite database with all patients, devices, and readings |
| `alerts.json` | Structured alerts (machine-readable) |
| `alert_summary.txt` | Clinician-readable summary grouped by patient and severity |

## Project Structure

```
├── main.py              # Entry point — runs the full pipeline
├── config.py            # Clinical thresholds and system parameters
├── models.py            # Data models: Patient, Device, Reading + SQLite ops
├── data_generator.py    # Synthetic data with edge cases
├── ingestion.py         # Validation, deduplication, storage
├── processing.py        # Cleaning, aggregation, rolling stats
├── analyzer.py          # Three-layer clinical analysis
├── alert_engine.py      # Alert prioritization and output
├── DESIGN.md            # Design decisions, assumptions, and tradeoffs
├── requirements.txt     # numpy, pandas
└── output/              # Generated outputs (after running main.py)
```

## Design Decisions

The system is designed to be **modular** — adding a new device type (e.g., glucose monitor) only requires changes to `config.py`, `data_generator.py`, `processing.py`, and `analyzer.py`. The ingestion layer, alert engine, and orchestrator are device-agnostic.

Key tradeoffs and what was intentionally left out are documented in [DESIGN.md](DESIGN.md).

## Requirements

Python 3.9+ with numpy and pandas. No other dependencies. SQLite is included in Python's standard library.
