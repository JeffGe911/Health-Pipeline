"""
main.py — Entry point for the Health Device Data Monitoring system.

Run the full pipeline with one command:
  python main.py

Pipeline stages:
  1. Generate synthetic patient + device + reading data
  2. Ingest: validate, deduplicate, store to SQLite
  3. Process: clean, compute daily aggregates, rolling stats
  4. Analyze: 3-layer clinical detection
  5. Alert: generate clinician-facing outputs

All output goes to the output/ directory.
"""

import os
import time

from data_generator import generate_all
from ingestion import ingest
from processing import process_all
from analyzer import analyze_all
from alert_engine import generate_alerts
import config


def main():
    print("=" * 60)
    print("  Health Device Data Monitoring System")
    print("  xHealth Group — Take-Home Exercise")
    print("=" * 60)

    start = time.time()

    # Ensure output directory exists (handles fresh clone with no output/ folder)
    os.makedirs(os.path.dirname(config.DB_PATH) or "output", exist_ok=True)

    # Clean previous run
    if os.path.exists(config.DB_PATH):
        os.remove(config.DB_PATH)

    # Stage 1: Generate data
    print("\n[Stage 1] Generating synthetic data...")
    patients, devices, readings = generate_all()

    # Stage 2: Ingest
    print("\n[Stage 2] Ingesting data...")
    conn = ingest(patients, devices, readings)

    # Stage 3: Process
    print("\n[Stage 3] Processing data...")
    processed, gap_df = process_all(conn)

    # Stage 4: Analyze
    print("\n[Stage 4] Analyzing data...")
    alerts = analyze_all(processed, gap_df)

    # Stage 5: Generate alerts
    print("\n[Stage 5] Generating alerts...")
    final_alerts = generate_alerts(alerts)

    elapsed = time.time() - start
    print(f"\nPipeline completed in {elapsed:.1f} seconds.")
    print(f"Output files in: output/")
    print(f"  - health_monitoring.db  (SQLite database)")
    print(f"  - alerts.json           (structured alerts)")
    print(f"  - alert_summary.txt     (clinician report)")

    conn.close()


if __name__ == "__main__":
    main()
