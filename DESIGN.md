# Design Note — Health Device Data Monitoring System

> Since the scope is intentionally open-ended, I constrained V1 to a reliable end-to-end monitoring pipeline with explicit assumptions, realistic edge cases, and interpretable detection. I prioritized correctness and usability over complex modeling, and documented key tradeoffs and what I intentionally left out.

> *Disclaimer: This system is for exercise purposes only. It is not clinical decision support and all thresholds are illustrative. Always defer to qualified clinical judgment.*

## Problem Statement

Adults aged 65 and older often use consumer health devices at home — blood pressure monitors, pulse oximeters, smart scales, wearable heart rate trackers — but the data from these devices usually lives in disconnected silos. A clinician reviewing a patient's status before a visit has no unified view, no trend detection, and no early warning when something is going wrong between appointments.

This system ingests time-series data from multiple consumer health devices, processes it into a clean and queryable format, runs clinical analysis to detect concerning patterns, and generates structured alerts for clinician review. The goal is to catch deterioration early — before it becomes an ER visit.

## Assumptions

**Patient population.** All patients are adults aged 65–90. Their clinical baselines differ based on conditions (hypertension, heart failure, COPD, diabetes). The system's thresholds and analysis logic are calibrated for this population, not the general adult population.

**Device-side assumptions.** Devices transmit readings via Bluetooth to a phone app, which syncs to a cloud backend. We assume the data arrives as timestamped JSON records with device ID and metric values. We do NOT assume the data arrives cleanly — Bluetooth sync bugs, sensor faults, and missing days are modeled explicitly. Detailed hardware or firmware design is out of scope.

**Data frequency.** Different devices produce data at very different rates. A blood pressure monitor generates 2–3 readings per day (manual), while a wearable heart rate tracker sends a reading every 5 minutes (continuous). The system handles this heterogeneity by normalizing everything to daily aggregates for analysis, while preserving raw readings in storage.

**Clinical thresholds.** All threshold values come from published clinical guidelines (AHA for blood pressure, WHO for SpO2). They are centralized in `config.py` and can be adjusted without changing pipeline code.

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                     DATA GENERATION                              │
│  Synthetic patients, devices, readings with realistic edge cases │
└──────────────────────┬───────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│                      INGESTION LAYER                             │
│  Schema validation → Sensor fault detection → Deduplication      │
│  → SQLite storage                                                │
│                                                                  │
│  Key decision: faulty readings are tagged, NOT dropped.          │
│  In healthcare, silent data loss is worse than noisy data.       │
└──────────────────────┬───────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│                    PROCESSING LAYER                               │
│  Filter faults → Detect time gaps → Daily aggregation            │
│  → Rolling statistics (mean, std, z-score) per patient           │
│                                                                  │
│  Each device type has its own aggregation logic.                 │
│  HR tracker uses 25th percentile for resting HR.                 │
│  Scale uses 7-day delta for trend detection.                     │
└──────────────────────┬───────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│                     ANALYSIS ENGINE                               │
│                                                                  │
│  Layer 1: Clinical Thresholds (immediate danger)                 │
│    BP > 180/120, SpO2 < 90%, resting HR > 100 bpm               │
│                                                                  │
│  Layer 2: Trend Detection (gradual deterioration)                │
│    Weight gain > 2kg/7d, rising resting HR trend, z-score        │
│    anomalies vs. patient's own rolling baseline                  │
│                                                                  │
│  Layer 3: Cross-Device Correlation (compound signals)            │
│    Weight up + BP up + HR up = possible heart failure             │
│    decompensation → CRITICAL compound alert                      │
└──────────────────────┬───────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│                      ALERT ENGINE                                 │
│  Prioritize → Deduplicate → Output structured JSON               │
│  + Clinician-readable summary report                             │
└──────────────────────────────────────────────────────────────────┘
```

## Data Model

Three-layer hierarchy: **Patient → Device → Reading**.

A patient can have multiple devices. Each device generates a stream of timestamped readings with flexible key-value metrics. This mirrors the real world where one elderly patient might use a blood pressure cuff at home and wear a Fitbit.

The `metrics` field is stored as JSON rather than fixed columns, because different device types have different measurements. A blood pressure reading has `{systolic, diastolic, pulse}`, while a scale reading has `{weight_kg}`. This keeps the schema extensible — adding a new device type doesn't require a schema migration.

Quality flags (`ok`, `sensor_fault`, `duplicate`) travel with each reading through the entire pipeline, so downstream processing can make informed decisions about which data to trust.

## Edge Cases and How They're Handled

**Sensor faults** (physically implausible values like SpO2 = 200% or BP = 0/0). Detected at ingestion using physical-limit rules in `config.py`. Tagged as `sensor_fault` but still stored — a pattern of frequent sensor faults from one device is itself a clinically useful signal (device may need replacement).

**Duplicate readings** (Bluetooth sync bugs sending the same measurement twice). Detected by comparing readings from the same device within a 60-second window with identical metrics. Only the first is kept.

**Missing days** (patient forgot to measure, device was off). Detected as time gaps in the processing layer. Gaps over 48 hours generate an INFO-level alert so the care team knows the patient may need a check-in. We do NOT impute missing values — fabricating health data is dangerous.

**Gradual drift** (scale calibration shifting over time). Modeled in the data generator. The rolling z-score analysis in Layer 2 would flag readings that suddenly deviate from the patient's own baseline.

**Activity-elevated heart rate** (normal HR increase during exercise shouldn't trigger alerts). Handled by using the 25th percentile of daily HR readings as "resting HR" — this naturally filters out exercise periods without needing an explicit activity classifier.

## Key Tradeoffs

**Rules + statistics over ML models.** A machine learning model could theoretically detect subtler patterns, but at this stage, rule-based detection with z-scores is the right call. Clinical thresholds are well-established for these vital signs, interpretability is critical (clinicians need to understand WHY an alert fired), and there is no labeled training data yet. ML is a natural future extension once the system has accumulated enough data with clinician feedback labels.

**Batch processing over real-time streaming.** The clinical decision cycle for this population is hours to days, not seconds. A patient's blood pressure reading at 8 AM doesn't need sub-second processing. Batch analysis on daily aggregates is simpler, more maintainable, and sufficient for the use case. A streaming architecture (e.g., Kafka + Flink) would add complexity without proportional clinical value at this stage.

**Daily aggregation over raw-reading analysis.** Analyzing every 5-minute heart rate reading individually would generate noise. Aggregating to daily summaries (mean systolic, min SpO2, resting HR percentile) compresses the signal while preserving clinical relevance. Raw readings are still in the database for drill-down if needed.

**Structured JSON output over a dashboard UI.** The system's value is in its detection logic and data quality, not in a visualization layer. Building a dashboard would consume significant time for cosmetic polish. The JSON output is machine-readable and can feed into any downstream system — an EHR alert queue, a Slack integration, a clinician portal. The text summary serves as a human-readable fallback.

**Alert fatigue mitigation.** In clinical systems, low-signal alerts can overwhelm clinicians and cause them to ignore real emergencies. V1 addresses this through severity-based prioritization (CRITICAL / WARNING / INFO) and deduplication of repeated triggers for the same patient and alert type. Future work would add persistence-based escalation — requiring a concerning pattern to persist across multiple days before upgrading severity — to further reduce noise.

## What I Chose Not to Build

**No real-time streaming pipeline.** Not needed for the clinical decision cadence. Would add Kafka/Redis/etc. complexity for minimal clinical benefit at this scale. Noted as a future extension.

**No ML models.** No labeled data exists yet. Rules + z-scores are sufficient, interpretable, and trustworthy for V1. The system is designed so that an ML layer could be plugged in alongside (not replacing) the rule-based layer.

**No frontend / dashboard UI.** Time is better spent on data quality and detection logic. Output is structured JSON + readable text.

**No authentication or access control.** Out of scope for the exercise, but in production this system would need HIPAA-compliant access controls, audit logging, and encryption at rest.

**No device firmware integration.** The exercise specifies this is out of scope. The system assumes clean-enough data arrives via API and handles the rest.

## Modularity (Plug-In / Plug-Out Design)

Every layer is a standalone module with a clear interface. To add a new device type (e.g., continuous glucose monitor), you would:

1. Add its config to `config.py` (thresholds and physical limits)
2. Add its generation logic to `data_generator.py`
3. Add its aggregation logic to `processing.py` (`compute_daily_aggregates`)
4. Add its threshold checks to `analyzer.py`

No other modules need to change. The ingestion layer, alert engine, and main orchestrator are device-agnostic.

Similarly, to add a new detection rule (e.g., "SpO2 dropping while resting HR rises"), you add one function to `analyzer.py` and call it from `analyze_all`. The alert engine picks it up automatically.

## Future Extensions

With more time and data, natural next steps would include: supervised ML models trained on clinician-labeled alert outcomes for smarter prioritization; a real-time ingestion layer using a message queue for continuous wearable streams; patient-specific adaptive thresholds that learn individual baselines over time instead of relying on population-level guidelines; integration with EHR systems (HL7 FHIR) for richer clinical context; and a clinician-facing web dashboard with drill-down capabilities.
