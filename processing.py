"""
processing.py — Data cleaning, gap detection, and feature computation.

Takes validated readings from the database and prepares them for analysis.
Main responsibilities:
  1. Filter out sensor faults (keep them in DB but exclude from analysis)
  2. Detect time gaps (device disconnection periods)
  3. Compute rolling statistics per patient per device type
  4. Compute daily aggregates (for weight trend, resting HR, etc.)

This layer works with pandas DataFrames for efficient time-series operations.
The output feeds directly into the analyzer.
"""

import json
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

import config


def load_readings_to_df(conn, device_type: str = None) -> pd.DataFrame:
    """Load readings from SQLite into a pandas DataFrame for processing."""
    query = "SELECT * FROM readings WHERE quality_flag != 'sensor_fault'"
    if device_type:
        query += f" AND device_type = '{device_type}'"
    query += " ORDER BY patient_id, timestamp"

    df = pd.read_sql_query(query, conn)

    # Parse metrics JSON into separate columns
    if not df.empty:
        metrics_df = pd.json_normalize(df["metrics"].apply(json.loads))
        df = pd.concat([df.drop(columns=["metrics"]), metrics_df], axis=1)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["date"] = df["timestamp"].dt.date

    return df


def detect_gaps(df: pd.DataFrame, device_type: str) -> pd.DataFrame:
    """
    Detect significant time gaps per patient. A gap is defined differently
    per device type based on expected sampling frequency.

    Returns a DataFrame of detected gaps with patient_id, start, end, duration.
    """
    # Expected max interval between readings (hours)
    expected_intervals = {
        "blood_pressure": 18,       # should get at least one reading per day
        "pulse_oximeter": 18,
        "smart_scale": 36,          # might skip a day
        "heart_rate_tracker": 2,    # continuous device, 2hr gap = notable
    }

    max_gap_hours = expected_intervals.get(device_type, 24)
    gaps = []

    for patient_id, group in df.groupby("patient_id"):
        group = group.sort_values("timestamp")
        times = group["timestamp"].values

        for i in range(1, len(times)):
            delta_hours = (times[i] - times[i-1]) / np.timedelta64(1, 'h')
            if delta_hours > max_gap_hours:
                gaps.append({
                    "patient_id": patient_id,
                    "device_type": device_type,
                    "gap_start": times[i-1],
                    "gap_end": times[i],
                    "gap_hours": round(delta_hours, 1),
                })

    return pd.DataFrame(gaps)


def compute_daily_aggregates(df: pd.DataFrame, device_type: str) -> pd.DataFrame:
    """
    Compute daily-level summaries per patient. Different aggregations
    depending on device type.

    For blood pressure: daily mean systolic/diastolic
    For pulse oximeter: daily min SpO2, mean heart rate
    For smart scale: daily weight (usually just one reading)
    For heart rate tracker: daily resting HR (use lower quartile during non-active hours)
    """
    if df.empty:
        return pd.DataFrame()

    if device_type == "blood_pressure":
        daily = df.groupby(["patient_id", "date"]).agg(
            systolic_mean=("systolic", "mean"),
            systolic_max=("systolic", "max"),
            diastolic_mean=("diastolic", "mean"),
            pulse_mean=("pulse", "mean"),
            reading_count=("reading_id", "count"),
        ).reset_index()

    elif device_type == "pulse_oximeter":
        daily = df.groupby(["patient_id", "date"]).agg(
            spo2_mean=("spo2", "mean"),
            spo2_min=("spo2", "min"),
            heart_rate_mean=("heart_rate", "mean"),
            reading_count=("reading_id", "count"),
        ).reset_index()

    elif device_type == "smart_scale":
        daily = df.groupby(["patient_id", "date"]).agg(
            weight_kg=("weight_kg", "mean"),  # usually 1 reading, mean handles >1
            reading_count=("reading_id", "count"),
        ).reset_index()

    elif device_type == "heart_rate_tracker":
        # Resting HR = 25th percentile of all readings in the day
        # This filters out activity periods naturally
        daily = df.groupby(["patient_id", "date"]).agg(
            resting_hr=("heart_rate", lambda x: np.percentile(x, 25)),
            hr_mean=("heart_rate", "mean"),
            hr_max=("heart_rate", "max"),
            total_steps=("steps", "sum"),
            reading_count=("reading_id", "count"),
        ).reset_index()
    else:
        return pd.DataFrame()

    daily["date"] = pd.to_datetime(daily["date"])
    return daily


def compute_rolling_stats(daily_df: pd.DataFrame, value_col: str,
                          window: int = config.ROLLING_WINDOW_DAYS) -> pd.DataFrame:
    """
    Compute rolling mean and std per patient for a given metric.
    Used for trend detection and z-score anomaly flagging.
    """
    results = []
    for patient_id, group in daily_df.groupby("patient_id"):
        group = group.sort_values("date").copy()
        group[f"{value_col}_rolling_mean"] = group[value_col].rolling(window, min_periods=3).mean()
        group[f"{value_col}_rolling_std"] = group[value_col].rolling(window, min_periods=3).std()

        # Z-score: how far is today's value from the rolling mean?
        mean_col = f"{value_col}_rolling_mean"
        std_col = f"{value_col}_rolling_std"
        group[f"{value_col}_zscore"] = (
            (group[value_col] - group[mean_col]) / group[std_col].replace(0, np.nan)
        )

        results.append(group)

    if results:
        return pd.concat(results, ignore_index=True)
    return daily_df


def process_all(conn):
    """
    Run full processing pipeline across all device types.
    Returns processed DataFrames and detected gaps.
    """
    print("\n[Processing] Starting...")

    processed = {}
    all_gaps = []

    for dtype in config.SUPPORTED_DEVICES:
        df = load_readings_to_df(conn, dtype)
        if df.empty:
            print(f"  {dtype}: no data")
            continue

        # Detect gaps
        gaps = detect_gaps(df, dtype)
        if not gaps.empty:
            all_gaps.append(gaps)

        # Daily aggregates
        daily = compute_daily_aggregates(df, dtype)

        # Rolling stats on key metrics
        if dtype == "blood_pressure":
            daily = compute_rolling_stats(daily, "systolic_mean")
        elif dtype == "pulse_oximeter":
            daily = compute_rolling_stats(daily, "spo2_min")
        elif dtype == "smart_scale":
            daily = compute_rolling_stats(daily, "weight_kg")
        elif dtype == "heart_rate_tracker":
            daily = compute_rolling_stats(daily, "resting_hr")

        processed[dtype] = {"raw": df, "daily": daily}
        print(f"  {dtype}: {len(df):,} readings → {len(daily)} daily records")

    gap_df = pd.concat(all_gaps, ignore_index=True) if all_gaps else pd.DataFrame()
    if not gap_df.empty:
        print(f"  Time gaps detected: {len(gap_df)}")

    print("[Processing] Complete.")
    return processed, gap_df
