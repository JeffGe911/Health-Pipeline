"""
alert_engine.py — Clinician-facing alert generation and output.

Takes raw alerts from the analyzer and produces:
  1. A structured JSON file (machine-readable, for downstream systems)
  2. A readable text summary grouped by patient and severity
In production, this output would feed into an EHR alert queue,
a Slack channel, or a clinician portal.
"""

import json
import os
from collections import defaultdict
from datetime import datetime

import config


def prioritize_alerts(alerts: list) -> list:
    """
    Sort alerts by severity (CRITICAL first), then by patient.
    Deduplicate similar alerts for the same patient.
    """
    severity_order = {
        config.SEVERITY_CRITICAL: 0,
        config.SEVERITY_WARNING: 1,
        config.SEVERITY_INFO: 2,
    }

    # Deduplicate: for the same patient + alert_type, keep the most severe
    seen = {}
    for alert in alerts:
        key = (alert.patient_id, alert.alert_type)
        if key not in seen or severity_order.get(alert.severity, 3) < severity_order.get(seen[key].severity, 3):
            seen[key] = alert

    deduped = list(seen.values())
    deduped.sort(key=lambda a: (severity_order.get(a.severity, 3), a.patient_id))
    return deduped


def generate_json_output(alerts: list, output_path: str):
    """Write alerts as structured JSON for downstream systems."""
    output = {
        "generated_at": datetime.now().isoformat(),
        "total_alerts": len(alerts),
        "summary": {
            "critical": sum(1 for a in alerts if a.severity == config.SEVERITY_CRITICAL),
            "warning": sum(1 for a in alerts if a.severity == config.SEVERITY_WARNING),
            "info": sum(1 for a in alerts if a.severity == config.SEVERITY_INFO),
        },
        "alerts": [a.to_dict() for a in alerts],
    }

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)


def generate_summary_report(alerts: list, output_path: str):
    """
    Write a human-readable summary report grouped by patient.
    This is what a clinician would scan in the morning to prioritize their day.
    """
    # Group by patient
    by_patient = defaultdict(list)
    for alert in alerts:
        by_patient[alert.patient_id].append(alert)

    lines = []
    lines.append("=" * 70)
    lines.append("  HEALTH DEVICE MONITORING — CLINICIAN ALERT SUMMARY")
    lines.append(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 70)

    # Overall counts
    critical = sum(1 for a in alerts if a.severity == config.SEVERITY_CRITICAL)
    warning = sum(1 for a in alerts if a.severity == config.SEVERITY_WARNING)
    info = sum(1 for a in alerts if a.severity == config.SEVERITY_INFO)

    lines.append(f"\n  TOTAL: {len(alerts)} alerts across {len(by_patient)} patients")
    lines.append(f"  [!!!] CRITICAL: {critical}  |  [!!] WARNING: {warning}  |  [i] INFO: {info}")

    # Critical patients first
    severity_icon = {
        config.SEVERITY_CRITICAL: "[!!!]",
        config.SEVERITY_WARNING: "[!! ]",
        config.SEVERITY_INFO: "[ i ]",
    }

    # Sort patients: those with critical alerts first
    def patient_priority(pid):
        severities = [a.severity for a in by_patient[pid]]
        has_critical = config.SEVERITY_CRITICAL in severities
        return (0 if has_critical else 1, pid)

    sorted_patients = sorted(by_patient.keys(), key=patient_priority)

    for pid in sorted_patients:
        patient_alerts = by_patient[pid]
        patient_alerts.sort(key=lambda a: {config.SEVERITY_CRITICAL: 0, config.SEVERITY_WARNING: 1, config.SEVERITY_INFO: 2}.get(a.severity, 3))

        lines.append(f"\n{'─' * 70}")
        lines.append(f"  PATIENT: {pid}")
        lines.append(f"{'─' * 70}")

        for alert in patient_alerts:
            icon = severity_icon.get(alert.severity, "[?]")
            lines.append(f"  {icon} {alert.message}")

    lines.append(f"\n{'=' * 70}")
    lines.append("  END OF REPORT")
    lines.append("=" * 70)

    report_text = "\n".join(lines)

    with open(output_path, "w") as f:
        f.write(report_text)

    return report_text


def generate_alerts(alerts: list, output_dir: str = "output"):
    """
    Main entry point: prioritize, deduplicate, and write outputs.
    """
    print("\n[Alert Engine] Starting...")

    os.makedirs(output_dir, exist_ok=True)

    # Prioritize and deduplicate
    prioritized = prioritize_alerts(alerts)
    print(f"  After deduplication: {len(prioritized)} alerts (from {len(alerts)} raw)")

    # JSON output
    json_path = os.path.join(output_dir, "alerts.json")
    generate_json_output(prioritized, json_path)
    print(f"  JSON output: {json_path}")

    # Readable report
    report_path = os.path.join(output_dir, "alert_summary.txt")
    report = generate_summary_report(prioritized, report_path)
    print(f"  Summary report: {report_path}")

    # Print the report to console too
    print("\n" + report)

    print("[Alert Engine] Complete.")
    return prioritized
