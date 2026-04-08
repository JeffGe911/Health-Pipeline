"""
models.py — Data model definitions for the health device monitoring system.

Three-layer hierarchy:
  Patient → Device → Reading

This mirrors a real-world structure where one patient can have
multiple devices, and each device generates a stream of timestamped readings.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import sqlite3
import json
import config


@dataclass
class Patient:
    patient_id: str
    age: int
    conditions: list  # e.g., ["hypertension", "heart_failure", "diabetes"]
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Device:
    device_id: str
    patient_id: str
    device_type: str        # one of config.SUPPORTED_DEVICES
    model_name: str         # e.g., "Omron BP5250"
    sampling_note: str      # e.g., "2-3x daily, manual"


@dataclass
class Reading:
    reading_id: str
    device_id: str
    patient_id: str
    device_type: str
    timestamp: str          # ISO format
    metrics: dict           # flexible key-value, e.g. {"systolic": 135, "diastolic": 88}
    quality_flag: str = "ok"  # "ok", "sensor_fault", "duplicate", "gap_filled"


def init_database(db_path: str = config.DB_PATH):
    """Create SQLite tables. Keeps things simple — no ORM overhead for a 3-5 hour project."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            patient_id TEXT PRIMARY KEY,
            age INTEGER,
            conditions TEXT,
            created_at TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            device_id TEXT PRIMARY KEY,
            patient_id TEXT,
            device_type TEXT,
            model_name TEXT,
            sampling_note TEXT,
            FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS readings (
            reading_id TEXT PRIMARY KEY,
            device_id TEXT,
            patient_id TEXT,
            device_type TEXT,
            timestamp TEXT,
            metrics TEXT,
            quality_flag TEXT DEFAULT 'ok',
            FOREIGN KEY (device_id) REFERENCES devices(device_id),
            FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
        )
    """)

    # Index on patient + time for efficient querying by patient window
    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_readings_patient_time
        ON readings(patient_id, device_type, timestamp)
    """)

    conn.commit()
    return conn


def insert_patient(conn, patient: Patient):
    conn.execute(
        "INSERT OR REPLACE INTO patients VALUES (?, ?, ?, ?)",
        (patient.patient_id, patient.age, json.dumps(patient.conditions), patient.created_at)
    )


def insert_device(conn, device: Device):
    conn.execute(
        "INSERT OR REPLACE INTO devices VALUES (?, ?, ?, ?, ?)",
        (device.device_id, device.patient_id, device.device_type,
         device.model_name, device.sampling_note)
    )


def insert_reading(conn, reading: Reading):
    conn.execute(
        "INSERT OR REPLACE INTO readings VALUES (?, ?, ?, ?, ?, ?, ?)",
        (reading.reading_id, reading.device_id, reading.patient_id,
         reading.device_type, reading.timestamp, json.dumps(reading.metrics),
         reading.quality_flag)
    )


def get_patient_readings(conn, patient_id: str, device_type: str = None) -> list:
    """Fetch readings for a patient, optionally filtered by device type."""
    query = "SELECT * FROM readings WHERE patient_id = ?"
    params = [patient_id]
    if device_type:
        query += " AND device_type = ?"
        params.append(device_type)
    query += " ORDER BY timestamp"

    rows = conn.execute(query, params).fetchall()
    return [
        Reading(
            reading_id=r[0], device_id=r[1], patient_id=r[2],
            device_type=r[3], timestamp=r[4], metrics=json.loads(r[5]),
            quality_flag=r[6]
        ) for r in rows
    ]


def get_all_patients(conn) -> list:
    rows = conn.execute("SELECT * FROM patients").fetchall()
    return [
        Patient(patient_id=r[0], age=r[1], conditions=json.loads(r[2]), created_at=r[3])
        for r in rows
    ]
