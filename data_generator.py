"""
data_generator.py — Synthetic data generator for consumer health devices.

Simulates 20 patients (ages 65-90) with 4 device types over 30 days.
Deliberately injects realistic edge cases that a production system must handle:
  - Missing readings (patient forgot / device off)
  - Sensor fault values (implausible readings)
  - Duplicate readings (Bluetooth sync bugs)
  - Time gaps (device disconnected for days)
  - Gradual drift (scale calibration shift)
  - Clinically abnormal patterns (for testing detection logic)

Each patient gets a clinical profile that shapes their "normal" baselines,
so the generated data has realistic inter-patient variability.
"""

import random
import uuid
from datetime import datetime, timedelta
from typing import List

import numpy as np

import config
from models import Patient, Device, Reading


# ── Patient Profile Templates ────────────────────────────────────────────
# These define realistic baselines for different clinical profiles.
# A "healthy" 70-year-old has different normals than someone with heart failure.

PROFILES = [
    {
        "label": "healthy",
        "conditions": [],
        "bp_baseline": (120, 75),
        "spo2_baseline": 97,
        "resting_hr": 68,
        "weight_kg": 72,
        "weight": 0,
    },
    {
        "label": "hypertension",
        "conditions": ["hypertension"],
        "bp_baseline": (145, 92),
        "spo2_baseline": 96,
        "resting_hr": 75,
        "weight_kg": 85,
        "weight": 1,
    },
    {
        "label": "heart_failure",
        "conditions": ["heart_failure", "hypertension"],
        "bp_baseline": (138, 85),
        "spo2_baseline": 93,
        "resting_hr": 82,
        "weight_kg": 90,
        "weight": 2,  # flag: will inject weight gain trend
    },
    {
        "label": "copd",
        "conditions": ["copd"],
        "bp_baseline": (125, 78),
        "spo2_baseline": 91,
        "resting_hr": 78,
        "weight_kg": 65,
        "weight": 0,
    },
    {
        "label": "diabetes_hypertension",
        "conditions": ["diabetes", "hypertension"],
        "bp_baseline": (140, 88),
        "spo2_baseline": 96,
        "resting_hr": 72,
        "weight_kg": 95,
        "weight": 1,
    },
]


def generate_patients(n: int = config.NUM_PATIENTS, seed: int = config.RANDOM_SEED) -> List[Patient]:
    """Generate n patients with assigned clinical profiles."""
    rng = random.Random(seed)
    patients = []
    for i in range(n):
        profile = rng.choice(PROFILES)
        p = Patient(
            patient_id=f"PAT-{i+1:04d}",
            age=rng.randint(65, 90),
            conditions=profile["conditions"],
        )
        # Attach profile data for device generation (stored as temp attribute)
        p._profile = profile
        patients.append(p)
    return patients


def generate_devices(patients: List[Patient], seed: int = config.RANDOM_SEED) -> List[Device]:
    """Each patient gets all 4 device types. In production, this would be dynamic."""
    devices = []
    device_models = {
        "blood_pressure": "Omron BP5250",
        "pulse_oximeter": "Masimo MightySat",
        "smart_scale": "Withings Body+",
        "heart_rate_tracker": "Fitbit Charge 6",
    }
    sampling_notes = {
        "blood_pressure": "2-3x daily, manual",
        "pulse_oximeter": "spot check 3-4x daily",
        "smart_scale": "1x daily, morning",
        "heart_rate_tracker": "continuous, 5-min intervals",
    }

    for p in patients:
        for dtype in config.SUPPORTED_DEVICES:
            d = Device(
                device_id=f"DEV-{p.patient_id}-{dtype[:2].upper()}",
                patient_id=p.patient_id,
                device_type=dtype,
                model_name=device_models[dtype],
                sampling_note=sampling_notes[dtype],
            )
            devices.append(d)
    return devices


def generate_readings(
    patients: List[Patient],
    devices: List[Device],
    days: int = config.DAYS_OF_DATA,
    seed: int = config.RANDOM_SEED,
) -> List[Reading]:
    """
    Generate time-series readings for all patients and devices.
    This is the core of the data generation — it builds realistic
    patterns WITH deliberate edge cases injected at known rates.
    """
    rng = random.Random(seed)
    np_rng = np.random.RandomState(seed)
    readings = []
    start_date = datetime(2026, 3, 1)

    # Build device lookup by (patient_id, device_type)
    device_map = {(d.patient_id, d.device_type): d for d in devices}

    for patient in patients:
        profile = patient._profile

        for day_offset in range(days):
            current_date = start_date + timedelta(days=day_offset)

            # ── Blood Pressure ──────────────────────────────────
            # 2-3 readings per day, sometimes skipped
            if rng.random() > 0.08:  # 8% chance of missing a full day
                n_readings = rng.choice([2, 2, 3])
                for reading_i in range(n_readings):
                    hour = rng.choice([7, 8, 12, 13, 18, 19, 20])
                    minute = rng.randint(0, 59)
                    ts = current_date.replace(hour=hour, minute=minute)

                    sys_base, dia_base = profile["bp_baseline"]
                    systolic = sys_base + np_rng.normal(0, 8)
                    diastolic = dia_base + np_rng.normal(0, 5)
                    pulse = profile["resting_hr"] + np_rng.normal(0, 5)

                    # Edge case: sensor fault (~2% of readings)
                    quality = "ok"
                    if rng.random() < 0.02:
                        systolic = rng.choice([0, 320, -10])
                        quality = "sensor_fault"

                    metrics = {
                        "systolic": round(systolic, 1),
                        "diastolic": round(diastolic, 1),
                        "pulse": round(pulse, 1),
                    }

                    dev = device_map[(patient.patient_id, "blood_pressure")]
                    readings.append(Reading(
                        reading_id=str(uuid.uuid4())[:12],
                        device_id=dev.device_id,
                        patient_id=patient.patient_id,
                        device_type="blood_pressure",
                        timestamp=ts.isoformat(),
                        metrics=metrics,
                        quality_flag=quality,
                    ))

                    # Edge case: duplicate reading (~3%)
                    if rng.random() < 0.03:
                        dup_ts = ts + timedelta(seconds=rng.randint(2, 30))
                        readings.append(Reading(
                            reading_id=str(uuid.uuid4())[:12],
                            device_id=dev.device_id,
                            patient_id=patient.patient_id,
                            device_type="blood_pressure",
                            timestamp=dup_ts.isoformat(),
                            metrics=metrics,  # same values = sync dup
                            quality_flag="ok",
                        ))

            # ── Pulse Oximeter ──────────────────────────────────
            # 3-4 spot checks per day
            if rng.random() > 0.10:  # 10% missing day
                n_checks = rng.choice([3, 3, 4])
                for _ in range(n_checks):
                    hour = rng.choice([8, 10, 14, 17, 21])
                    ts = current_date.replace(hour=hour, minute=rng.randint(0, 59))

                    spo2 = profile["spo2_baseline"] + np_rng.normal(0, 1.5)
                    spo2 = min(spo2, 100)  # can't exceed 100
                    hr = profile["resting_hr"] + np_rng.normal(0, 6)

                    quality = "ok"
                    # Edge case: cold fingers → false low SpO2 (~3%)
                    if rng.random() < 0.03:
                        spo2 = spo2 - rng.uniform(5, 12)

                    # Edge case: sensor fault (~1.5%)
                    if rng.random() < 0.015:
                        spo2 = rng.choice([0, 110, 200])
                        quality = "sensor_fault"

                    dev = device_map[(patient.patient_id, "pulse_oximeter")]
                    readings.append(Reading(
                        reading_id=str(uuid.uuid4())[:12],
                        device_id=dev.device_id,
                        patient_id=patient.patient_id,
                        device_type="pulse_oximeter",
                        timestamp=ts.isoformat(),
                        metrics={"spo2": round(spo2, 1), "heart_rate": round(hr, 1)},
                        quality_flag=quality,
                    ))

            # ── Smart Scale ─────────────────────────────────────
            # 0-1 reading per day (morning)
            if rng.random() > 0.15:  # 15% skip — common for scales
                ts = current_date.replace(hour=rng.choice([6, 7, 8]), minute=rng.randint(0, 30))

                base_weight = profile["weight_kg"]

                # Edge case: gradual weight gain for heart failure patients
                if profile["weight"] == 2 and day_offset > 18:
                    # Simulate fluid retention — gaining ~0.3kg/day in last 12 days
                    base_weight += (day_offset - 18) * 0.3

                weight = base_weight + np_rng.normal(0, 0.4)

                # Edge case: calibration drift (~5% of readings after day 20)
                if day_offset > 20 and rng.random() < 0.05:
                    weight += rng.uniform(1.5, 3.0)

                dev = device_map[(patient.patient_id, "smart_scale")]
                readings.append(Reading(
                    reading_id=str(uuid.uuid4())[:12],
                    device_id=dev.device_id,
                    patient_id=patient.patient_id,
                    device_type="smart_scale",
                    timestamp=ts.isoformat(),
                    metrics={"weight_kg": round(weight, 2)},
                    quality_flag="ok",
                ))

            # ── Heart Rate Tracker (Wearable) ───────────────────
            # High frequency: every 5 min, but with gaps from not wearing
            if rng.random() > 0.05:  # 5% full day off-wrist
                # Simulate wearing ~16 hours/day (6am to 10pm)
                wear_start = 6
                wear_end = 22

                # Edge case: 3-day device disconnection for some patients
                if patient.patient_id in ["PAT-0003", "PAT-0007"] and 10 <= day_offset <= 12:
                    continue  # gap — device was charging / lost

                for hour in range(wear_start, wear_end):
                    for minute_block in [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]:
                        # Skip some readings (~8%) to simulate wrist-off moments
                        if rng.random() < 0.08:
                            continue

                        ts = current_date.replace(hour=hour, minute=minute_block)
                        # Resting HR during calm hours, elevated during "activity"
                        is_active = (10 <= hour <= 11) or (15 <= hour <= 16)
                        if is_active:
                            hr = profile["resting_hr"] + rng.uniform(20, 50)
                        else:
                            hr = profile["resting_hr"] + np_rng.normal(0, 4)

                        # Edge case: sensor contact loss → implausible value
                        quality = "ok"
                        if rng.random() < 0.01:
                            hr = rng.choice([0, 15, 260])
                            quality = "sensor_fault"

                        steps = rng.randint(0, 30) if is_active else rng.randint(0, 5)

                        dev = device_map[(patient.patient_id, "heart_rate_tracker")]
                        readings.append(Reading(
                            reading_id=str(uuid.uuid4())[:12],
                            device_id=dev.device_id,
                            patient_id=patient.patient_id,
                            device_type="heart_rate_tracker",
                            timestamp=ts.isoformat(),
                            metrics={"heart_rate": round(hr, 1), "steps": steps},
                            quality_flag=quality,
                        ))

    return readings


def generate_all(seed: int = config.RANDOM_SEED):
    """Top-level function: generate patients, devices, and all readings."""
    patients = generate_patients(seed=seed)
    devices = generate_devices(patients, seed=seed)
    readings = generate_readings(patients, devices, seed=seed)

    print(f"  Generated {len(patients)} patients")
    print(f"  Generated {len(devices)} devices")
    print(f"  Generated {len(readings):,} readings")
    print(f"  Date range: 2026-03-01 to 2026-03-{config.DAYS_OF_DATA:02d}")

    return patients, devices, readings
