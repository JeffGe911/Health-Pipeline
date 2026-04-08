"""
analyzer.py — Three-layer clinical analysis engine.

Layer 1: Clinical Threshold Alerts (immediate)
  - Single readings that exceed dangerous clinical thresholds
  - Example: SpO2 < 90%, BP > 180/120

Layer 2: Trend Detection (pattern-based)
  - Rolling window analysis to catch gradual deterioration
  - Example: weight gain > 2kg in 7 days, rising resting HR

Layer 3: Cross-Device Correlation (multi-signal)
  - Combines signals from multiple devices to detect compound patterns
  - Example: weight gain + BP increase + HR increase = heart failure flag

Design choice: we use rule-based + statistical methods instead of ML models.
At this stage, interpretability matters more than model complexity. A clinician
needs to understand WHY an alert fired. Rules with z-scores are transparent.
ML models can be layered on top later once there's enough labeled data.
"""

import numpy as np
import pandas as pd

import config


class Alert:
    """Simple alert data structure."""
    def __init__(self, patient_id, device_type, severity, alert_type, message, details=None):
        self.patient_id = patient_id
        self.device_type = device_type
        self.severity = severity
        self.alert_type = alert_type
        self.message = message
        self.details = details or {}

    def to_dict(self):
        return {
            "patient_id": self.patient_id,
            "device_type": self.device_type,
            "severity": self.severity,
            "alert_type": self.alert_type,
            "message": self.message,
            "details": self.details,
        }


# ═══════════════════════════════════════════════════════════════════
# LAYER 1: Clinical Threshold Checks
# These fire immediately when a single reading crosses a danger line.
# ═══════════════════════════════════════════════════════════════════

def check_bp_thresholds(daily_df: pd.DataFrame) -> list:
    """Check blood pressure against clinical thresholds."""
    alerts = []
    t = config.THRESHOLDS["blood_pressure"]

    for _, row in daily_df.iterrows():
        pid = row["patient_id"]
        date_str = str(row["date"])[:10]

        # Hypertensive crisis
        if row["systolic_max"] >= t["systolic_crisis"]:
            alerts.append(Alert(
                pid, "blood_pressure", config.SEVERITY_CRITICAL,
                "threshold_bp_crisis",
                f"Hypertensive crisis: systolic {row['systolic_max']:.0f} mmHg on {date_str}",
                {"systolic": row["systolic_max"], "date": date_str}
            ))
        # Stage 1 hypertension (persistent)
        elif row["systolic_mean"] >= t["systolic_high"]:
            alerts.append(Alert(
                pid, "blood_pressure", config.SEVERITY_WARNING,
                "threshold_bp_high",
                f"Elevated BP: mean systolic {row['systolic_mean']:.0f} mmHg on {date_str}",
                {"systolic_mean": row["systolic_mean"], "date": date_str}
            ))
        # Hypotension
        if row["systolic_mean"] <= t["systolic_low"]:
            alerts.append(Alert(
                pid, "blood_pressure", config.SEVERITY_WARNING,
                "threshold_bp_low",
                f"Low BP: mean systolic {row['systolic_mean']:.0f} mmHg on {date_str}",
                {"systolic_mean": row["systolic_mean"], "date": date_str}
            ))

    return alerts


def check_spo2_thresholds(daily_df: pd.DataFrame) -> list:
    """Check pulse oximeter readings against oxygen saturation thresholds."""
    alerts = []
    t = config.THRESHOLDS["pulse_oximeter"]

    for _, row in daily_df.iterrows():
        pid = row["patient_id"]
        date_str = str(row["date"])[:10]

        if row["spo2_min"] <= t["spo2_critical"]:
            alerts.append(Alert(
                pid, "pulse_oximeter", config.SEVERITY_CRITICAL,
                "threshold_spo2_critical",
                f"Critical SpO2: minimum {row['spo2_min']:.1f}% on {date_str}",
                {"spo2_min": row["spo2_min"], "date": date_str}
            ))
        elif row["spo2_min"] <= t["spo2_low"]:
            alerts.append(Alert(
                pid, "pulse_oximeter", config.SEVERITY_WARNING,
                "threshold_spo2_low",
                f"Low SpO2: minimum {row['spo2_min']:.1f}% on {date_str}",
                {"spo2_min": row["spo2_min"], "date": date_str}
            ))

    return alerts


def check_hr_thresholds(daily_df: pd.DataFrame) -> list:
    """Check heart rate against bradycardia/tachycardia thresholds."""
    alerts = []
    t = config.THRESHOLDS["heart_rate_tracker"]

    for _, row in daily_df.iterrows():
        pid = row["patient_id"]
        date_str = str(row["date"])[:10]

        if row["resting_hr"] >= t["resting_hr_high"]:
            alerts.append(Alert(
                pid, "heart_rate_tracker", config.SEVERITY_WARNING,
                "threshold_hr_high",
                f"Elevated resting HR: {row['resting_hr']:.0f} bpm on {date_str}",
                {"resting_hr": row["resting_hr"], "date": date_str}
            ))
        elif row["resting_hr"] <= t["resting_hr_low"]:
            alerts.append(Alert(
                pid, "heart_rate_tracker", config.SEVERITY_WARNING,
                "threshold_hr_low",
                f"Low resting HR: {row['resting_hr']:.0f} bpm on {date_str}",
                {"resting_hr": row["resting_hr"], "date": date_str}
            ))

    return alerts


# ═══════════════════════════════════════════════════════════════════
# LAYER 2: Trend Detection
# Uses rolling statistics to catch gradual deterioration patterns.
# ═══════════════════════════════════════════════════════════════════

def check_weight_trend(daily_df: pd.DataFrame) -> list:
    """
    Detect rapid weight gain/loss over a 7-day window.
    >2kg gain in 7 days is a classic heart failure decompensation signal.
    """
    alerts = []
    t = config.THRESHOLDS["smart_scale"]

    for pid, group in daily_df.groupby("patient_id"):
        group = group.sort_values("date")
        if len(group) < 3:
            continue

        weights = group["weight_kg"].values
        dates = group["date"].values

        for i in range(len(group)):
            # Look back 7 days
            current_date = dates[i]
            window_start = current_date - pd.Timedelta(days=7)
            mask = (dates >= window_start) & (dates <= current_date)
            window = weights[mask]

            if len(window) >= 2:
                delta = window[-1] - window[0]
                if delta >= t["weight_gain_7d_kg"]:
                    alerts.append(Alert(
                        pid, "smart_scale", config.SEVERITY_CRITICAL,
                        "trend_weight_gain",
                        f"Rapid weight gain: +{delta:.1f}kg over 7 days (ending {str(current_date)[:10]})",
                        {"weight_delta_kg": round(delta, 2), "date": str(current_date)[:10]}
                    ))
                    break  # one alert per patient for this pattern
                elif abs(delta) >= t["weight_loss_7d_kg"]:
                    alerts.append(Alert(
                        pid, "smart_scale", config.SEVERITY_WARNING,
                        "trend_weight_loss",
                        f"Rapid weight loss: {delta:.1f}kg over 7 days (ending {str(current_date)[:10]})",
                        {"weight_delta_kg": round(delta, 2), "date": str(current_date)[:10]}
                    ))
                    break

    return alerts


def check_hr_trend(daily_df: pd.DataFrame) -> list:
    """Detect sustained resting HR increase over 7-day window."""
    alerts = []
    t = config.THRESHOLDS["heart_rate_tracker"]
    window = t["resting_hr_trend_window"]
    threshold = t["resting_hr_trend_threshold"]

    for pid, group in daily_df.groupby("patient_id"):
        group = group.sort_values("date")
        if len(group) < window:
            continue

        # Compare last 3 days avg vs first 3 days avg in the last 7-day window
        recent = group.tail(window)
        first_half = recent.head(3)["resting_hr"].mean()
        last_half = recent.tail(3)["resting_hr"].mean()
        delta = last_half - first_half

        if delta >= threshold:
            alerts.append(Alert(
                pid, "heart_rate_tracker", config.SEVERITY_WARNING,
                "trend_hr_rising",
                f"Rising resting HR: +{delta:.1f} bpm over last {window} days",
                {"hr_delta": round(delta, 1)}
            ))

    return alerts


def check_zscore_anomalies(daily_df: pd.DataFrame, value_col: str,
                           device_type: str) -> list:
    """Flag days where a metric deviates significantly from patient's rolling baseline."""
    alerts = []
    zscore_col = f"{value_col}_zscore"

    if zscore_col not in daily_df.columns:
        return alerts

    anomalies = daily_df[daily_df[zscore_col].abs() > config.ZSCORE_THRESHOLD]

    for _, row in anomalies.iterrows():
        direction = "above" if row[zscore_col] > 0 else "below"
        alerts.append(Alert(
            row["patient_id"], device_type, config.SEVERITY_INFO,
            "zscore_anomaly",
            f"Unusual {value_col}: {row[value_col]:.1f} ({direction} baseline, z={row[zscore_col]:.1f}) on {str(row['date'])[:10]}",
            {"value": round(row[value_col], 2), "zscore": round(row[zscore_col], 2), "date": str(row["date"])[:10]}
        ))

    return alerts


# ═══════════════════════════════════════════════════════════════════
# LAYER 3: Cross-Device Correlation
# Combines signals from multiple devices for compound clinical patterns.
# ═══════════════════════════════════════════════════════════════════

def check_cross_device_patterns(processed: dict) -> list:
    """
    Look for compound patterns across device types.
    Example: weight gain + elevated BP + rising HR = possible heart failure decompensation.

    This is a simplified version of what a full clinical decision support system would do.
    In production, you'd use a rule engine or a clinical knowledge graph.
    """
    alerts = []

    # Get patient-level summaries from each device type
    bp_daily = processed.get("blood_pressure", {}).get("daily", pd.DataFrame())
    scale_daily = processed.get("smart_scale", {}).get("daily", pd.DataFrame())
    hr_daily = processed.get("heart_rate_tracker", {}).get("daily", pd.DataFrame())

    if bp_daily.empty or scale_daily.empty or hr_daily.empty:
        return alerts

    # For each patient, check if multiple concerning signals co-occur in the last 7 days
    patients_bp = set(bp_daily["patient_id"].unique())
    patients_scale = set(scale_daily["patient_id"].unique())
    patients_hr = set(hr_daily["patient_id"].unique())
    common_patients = patients_bp & patients_scale & patients_hr

    for pid in common_patients:
        bp = bp_daily[bp_daily["patient_id"] == pid].sort_values("date").tail(7)
        wt = scale_daily[scale_daily["patient_id"] == pid].sort_values("date").tail(7)
        hr = hr_daily[hr_daily["patient_id"] == pid].sort_values("date").tail(7)

        # Signal 1: weight trending up?
        weight_up = False
        if len(wt) >= 3:
            wt_delta = wt["weight_kg"].iloc[-1] - wt["weight_kg"].iloc[0]
            weight_up = wt_delta > 1.5

        # Signal 2: BP elevated?
        bp_up = False
        if len(bp) >= 3:
            bp_up = bp["systolic_mean"].tail(3).mean() > config.THRESHOLDS["blood_pressure"]["systolic_high"]

        # Signal 3: resting HR elevated?
        hr_up = False
        if len(hr) >= 3:
            hr_up = hr["resting_hr"].tail(3).mean() > 85  # above typical resting

        # Compound alert: 2+ signals firing together
        signals = [weight_up, bp_up, hr_up]
        if sum(signals) >= 2:
            triggered = []
            if weight_up: triggered.append("weight gain")
            if bp_up: triggered.append("elevated BP")
            if hr_up: triggered.append("elevated resting HR")

            alerts.append(Alert(
                pid, "cross_device", config.SEVERITY_CRITICAL,
                "compound_deterioration",
                f"Multiple deterioration signals: {', '.join(triggered)} in last 7 days — review recommended",
                {"signals": triggered}
            ))

    return alerts


# ═══════════════════════════════════════════════════════════════════
# MAIN ANALYSIS RUNNER
# ═══════════════════════════════════════════════════════════════════

def analyze_all(processed: dict, gap_df: pd.DataFrame) -> list:
    """
    Run all three analysis layers and return a consolidated list of alerts.
    """
    print("\n[Analysis] Starting...")
    all_alerts = []

    # --- Layer 1: Threshold checks ---
    bp_daily = processed.get("blood_pressure", {}).get("daily", pd.DataFrame())
    spo2_daily = processed.get("pulse_oximeter", {}).get("daily", pd.DataFrame())
    hr_daily = processed.get("heart_rate_tracker", {}).get("daily", pd.DataFrame())

    if not bp_daily.empty:
        all_alerts.extend(check_bp_thresholds(bp_daily))
    if not spo2_daily.empty:
        all_alerts.extend(check_spo2_thresholds(spo2_daily))
    if not hr_daily.empty:
        all_alerts.extend(check_hr_thresholds(hr_daily))

    layer1_count = len(all_alerts)
    print(f"  Layer 1 (thresholds): {layer1_count} alerts")

    # --- Layer 2: Trend detection ---
    scale_daily = processed.get("smart_scale", {}).get("daily", pd.DataFrame())

    if not scale_daily.empty:
        all_alerts.extend(check_weight_trend(scale_daily))
    if not hr_daily.empty:
        all_alerts.extend(check_hr_trend(hr_daily))

    # Z-score anomalies
    if not bp_daily.empty:
        all_alerts.extend(check_zscore_anomalies(bp_daily, "systolic_mean", "blood_pressure"))
    if not spo2_daily.empty:
        all_alerts.extend(check_zscore_anomalies(spo2_daily, "spo2_min", "pulse_oximeter"))

    layer2_count = len(all_alerts) - layer1_count
    print(f"  Layer 2 (trends): {layer2_count} alerts")

    # --- Layer 3: Cross-device correlation ---
    all_alerts.extend(check_cross_device_patterns(processed))

    layer3_count = len(all_alerts) - layer1_count - layer2_count
    print(f"  Layer 3 (cross-device): {layer3_count} alerts")

    # --- Gap alerts ---
    if not gap_df.empty:
        for _, gap in gap_df.iterrows():
            if gap["gap_hours"] > 48:  # only alert on gaps > 2 days
                all_alerts.append(Alert(
                    gap["patient_id"], gap["device_type"], config.SEVERITY_INFO,
                    "device_gap",
                    f"Device offline for {gap['gap_hours']:.0f} hours ({gap['device_type']})",
                    {"gap_hours": gap["gap_hours"]}
                ))

    print(f"  Total alerts generated: {len(all_alerts)}")
    print("[Analysis] Complete.")
    return all_alerts
