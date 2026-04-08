"""
config.py — Centralized configuration for clinical thresholds and system parameters.

All thresholds are based on published clinical guidelines for adults 65+.
Keeping them here makes it easy to adjust without touching pipeline logic.

DISCLAIMER: For exercise purposes only. This is not clinical decision support
and thresholds are illustrative. Always defer to qualified clinical judgment.
"""

# === Device Types (plug in new devices by adding entries here) ===
SUPPORTED_DEVICES = ["blood_pressure", "pulse_oximeter", "smart_scale", "heart_rate_tracker"]

# === Data Generation Settings ===
NUM_PATIENTS = 20
DAYS_OF_DATA = 30  # one month of monitoring history
RANDOM_SEED = 42

# === Clinical Thresholds (source: AHA / WHO guidelines for 65+) ===
# These drive the Layer 1 immediate alerting logic.

THRESHOLDS = {
    "blood_pressure": {
        "systolic_high": 130,       # Stage 1 hypertension
        "systolic_crisis": 180,     # Hypertensive crisis — immediate alert
        "diastolic_high": 80,
        "diastolic_crisis": 120,
        "systolic_low": 90,         # Hypotension risk (common in elderly on meds)
        "diastolic_low": 60,
    },
    "pulse_oximeter": {
        "spo2_low": 94,             # Below normal — worth watching
        "spo2_critical": 90,        # Severe hypoxemia — immediate alert
        "hr_high": 100,             # Tachycardia
        "hr_low": 50,               # Bradycardia (using 50 for elderly, not 60)
    },
    "smart_scale": {
        "weight_gain_7d_kg": 2.0,   # >2kg in 7 days = heart failure red flag
        "weight_loss_7d_kg": 3.0,   # Rapid loss may indicate dehydration/illness
    },
    "heart_rate_tracker": {
        "resting_hr_high": 100,
        "resting_hr_low": 50,
        "resting_hr_trend_window": 7,       # days to evaluate trend
        "resting_hr_trend_threshold": 10,   # bpm increase over window = concern
    },
}

# === Processing Settings ===
DUPLICATE_TIME_WINDOW_SECONDS = 60   # readings within 60s from same device = likely duplicate
SENSOR_FAULT_RULES = {
    "spo2_max": 100,        # SpO2 physically cannot exceed 100%
    "spo2_min": 50,         # Below 50% is almost certainly sensor error
    "systolic_max": 300,    # Physically implausible BP
    "systolic_min": 40,
    "diastolic_max": 200,
    "diastolic_min": 20,
    "weight_max": 250,      # kg
    "weight_min": 20,
    "hr_max": 250,
    "hr_min": 20,
}

# === Analysis Settings ===
ROLLING_WINDOW_DAYS = 7
ZSCORE_THRESHOLD = 2.5   # flag readings beyond 2.5 std from patient's rolling mean

# === Alert Severity Levels ===
SEVERITY_CRITICAL = "CRITICAL"   # needs immediate clinician attention
SEVERITY_WARNING = "WARNING"     # review within 24 hours
SEVERITY_INFO = "INFO"           # note for next visit

# === Database ===
DB_PATH = "output/health_monitoring.db"
