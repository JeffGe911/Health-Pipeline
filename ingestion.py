"""
ingestion.py — Data ingestion, validation, and storage layer.

This is the first gate in the pipeline. Every reading passes through here
before entering the database. The job is to:
  1. Validate schema (are all required fields present?)
  2. Catch sensor faults (physically implausible values)
  3. Deduplicate (Bluetooth sync bugs that send the same reading twice)
  4. Tag quality flags so downstream processing knows what it's working with
  5. Store to SQLite

Design choice: we validate and tag, but we still STORE faulty readings
with their quality_flag set. This is intentional — in healthcare,
you never silently drop data. A clinician might want to see that a
device had 3 fault readings this week. Deletion would hide that signal.
"""

import json
from datetime import datetime, timedelta
import sqlite3

import config
from models import (
    Patient, Device, Reading,
    init_database, insert_patient, insert_device, insert_reading,
    get_patient_readings
)


def validate_reading(reading: Reading) -> Reading:
    """
    Check a single reading for sensor faults based on physical limits.
    Tags the quality_flag but does NOT drop the reading.
    """
    metrics = reading.metrics
    dtype = reading.device_type
    rules = config.SENSOR_FAULT_RULES

    is_fault = False

    if dtype == "blood_pressure":
        sys_val = metrics.get("systolic", 0)
        dia_val = metrics.get("diastolic", 0)
        if not (rules["systolic_min"] <= sys_val <= rules["systolic_max"]):
            is_fault = True
        if not (rules["diastolic_min"] <= dia_val <= rules["diastolic_max"]):
            is_fault = True

    elif dtype == "pulse_oximeter":
        spo2 = metrics.get("spo2", 0)
        if not (rules["spo2_min"] <= spo2 <= rules["spo2_max"]):
            is_fault = True

    elif dtype == "smart_scale":
        w = metrics.get("weight_kg", 0)
        if not (rules["weight_min"] <= w <= rules["weight_max"]):
            is_fault = True

    elif dtype == "heart_rate_tracker":
        hr = metrics.get("heart_rate", 0)
        if not (rules["hr_min"] <= hr <= rules["hr_max"]):
            is_fault = True

    if is_fault and reading.quality_flag == "ok":
        reading.quality_flag = "sensor_fault"

    return reading


def deduplicate_readings(readings: list) -> list:
    """
    Remove duplicate readings from the same device within a short time window.
    If two readings from the same device have identical metrics and are within
    60 seconds of each other, keep only the first one.

    Returns cleaned list + count of duplicates found.
    """
    # Sort by device_id then timestamp
    sorted_readings = sorted(readings, key=lambda r: (r.device_id, r.timestamp))

    kept = []
    dup_count = 0

    for i, reading in enumerate(sorted_readings):
        if i == 0:
            kept.append(reading)
            continue

        prev = kept[-1]
        if reading.device_id == prev.device_id:
            # Check time distance
            try:
                t_curr = datetime.fromisoformat(reading.timestamp)
                t_prev = datetime.fromisoformat(prev.timestamp)
                delta = abs((t_curr - t_prev).total_seconds())
            except (ValueError, TypeError):
                delta = float("inf")

            # Same metrics + close in time = duplicate
            if delta <= config.DUPLICATE_TIME_WINDOW_SECONDS and reading.metrics == prev.metrics:
                reading.quality_flag = "duplicate"
                dup_count += 1
                continue  # skip storing this one

        kept.append(reading)

    return kept, dup_count


def ingest(patients, devices, readings, db_path=config.DB_PATH):
    """
    Full ingestion pipeline:
      1. Init database
      2. Store patients and devices
      3. Validate each reading
      4. Deduplicate
      5. Store clean readings
    """
    print("\n[Ingestion] Starting...")

    # 1. Init DB
    conn = init_database(db_path)

    # 2. Store patients and devices
    for p in patients:
        insert_patient(conn, p)
    for d in devices:
        insert_device(conn, d)
    conn.commit()
    print(f"  Stored {len(patients)} patients, {len(devices)} devices")

    # 3. Validate readings
    fault_count = 0
    for r in readings:
        validate_reading(r)
        if r.quality_flag == "sensor_fault":
            fault_count += 1

    print(f"  Sensor faults detected: {fault_count}")

    # 4. Deduplicate
    cleaned, dup_count = deduplicate_readings(readings)
    print(f"  Duplicates removed: {dup_count}")

    # 5. Store
    for r in cleaned:
        insert_reading(conn, r)
    conn.commit()

    print(f"  Stored {len(cleaned):,} readings to database")
    print("[Ingestion] Complete.")

    return conn
