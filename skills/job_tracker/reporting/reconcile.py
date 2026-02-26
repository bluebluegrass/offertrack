"""Reconciliation report between message-level and application-level OA counts."""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

from skills.job_tracker.types import Event

STAGE_RANK = {
    "Applied": 10,
    "OA": 20,
    "Interview": 30,
    "Offer": 40,
    "Rejected": 90,
    "Withdrawn": 95,
}

EVENT_TYPES = [
    "oa",
    "interview_invite",
    "rejection",
    "offer",
    "application_received",
    "round_update",
    "withdrawn",
    "interview_reminder",
]


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _stage_rank(stage: str) -> int:
    return STAGE_RANK.get(stage, 0)


def _max_stage(events: list[Event]) -> str:
    if not events:
        return "Applied"
    return max(events, key=lambda e: _stage_rank(e.stage)).stage


def _pick_evidence(events: list[Event]) -> list[Event]:
    ranked = sorted(
        events,
        key=lambda e: (_stage_rank(e.stage), float(e.confidence), e.occurred_at),
        reverse=True,
    )
    return ranked[:3]


def _build_reconcile_rows(events: list[Event], audit_rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]], int, int, Counter, Counter]:
    by_app: dict[str, list[Event]] = defaultdict(list)
    for ev in events:
        by_app[ev.application_key].append(ev)

    audit_by_key = {row.get("application_key", ""): row for row in audit_rows}
    msg_counter = Counter(ev.type for ev in events)

    app_stage_counter = Counter()
    for key, app_events in by_app.items():
        app_stage_counter[_max_stage(app_events)] += 1

    rows: list[dict[str, str]] = []
    false_rows: list[dict[str, str]] = []

    for key, audit in sorted(audit_by_key.items(), key=lambda kv: (kv[1].get("company_domain", ""), kv[1].get("role_title", ""), kv[0])):
        counted_oa = int(audit.get("counted_oa", "0") or "0")
        if counted_oa != 1:
            continue

        app_events = by_app.get(key, [])
        max_stage = _max_stage(app_events)
        max_stage_rank = _stage_rank(max_stage)
        oa_event_count = sum(1 for ev in app_events if ev.type == "oa")

        reasons: list[str] = []
        if oa_event_count > 0:
            reasons.append("has_oa_event")
        if max_stage_rank >= STAGE_RANK["OA"]:
            reasons.append("max_stage>=OA")
        if not reasons:
            reasons.append("legacy_flag")

        evidence = _pick_evidence(app_events)
        row = {
            "application_key": key,
            "company_domain": audit.get("company_domain", ""),
            "role_title": audit.get("role_title", ""),
            "max_stage_reached": max_stage,
            "counted_oa": "1",
            "oa_event_count": str(oa_event_count),
            "why_counted_oa": "|".join(reasons),
            "evidence_event_type_1": "",
            "evidence_stage_1": "",
            "evidence_confidence_1": "",
            "evidence_date_1": "",
            "evidence_domain_1": "",
            "evidence_subject_1": "",
            "evidence_event_type_2": "",
            "evidence_stage_2": "",
            "evidence_confidence_2": "",
            "evidence_date_2": "",
            "evidence_domain_2": "",
            "evidence_subject_2": "",
            "evidence_event_type_3": "",
            "evidence_stage_3": "",
            "evidence_confidence_3": "",
            "evidence_date_3": "",
            "evidence_domain_3": "",
            "evidence_subject_3": "",
        }
        for idx, ev in enumerate(evidence, start=1):
            row[f"evidence_event_type_{idx}"] = ev.type
            row[f"evidence_stage_{idx}"] = ev.stage
            row[f"evidence_confidence_{idx}"] = f"{float(ev.confidence):.2f}"
            row[f"evidence_date_{idx}"] = ev.occurred_at.isoformat()
            row[f"evidence_domain_{idx}"] = str(ev.evidence.get("from_domain", ""))
            row[f"evidence_subject_{idx}"] = str(ev.evidence.get("subject", ""))[:160]

        rows.append(row)
        if oa_event_count == 0:
            false_rows.append(row.copy())

    computed_oa_apps = len(rows)
    oa_messages = msg_counter.get("oa", 0)
    return rows, false_rows, computed_oa_apps, oa_messages, msg_counter, app_stage_counter


def write_reconcile_outputs(path: str, events: list[Event], audit_rows: list[dict[str, str]]) -> dict[str, object]:
    base = Path(path).expanduser().resolve()
    base.parent.mkdir(parents=True, exist_ok=True)
    false_path = base.parent / "oa_false_positives.csv"

    rows, false_rows, computed_oa_apps, oa_messages, msg_counter, app_stage_counter = _build_reconcile_rows(events, audit_rows)
    fieldnames = [
        "application_key",
        "company_domain",
        "role_title",
        "max_stage_reached",
        "counted_oa",
        "oa_event_count",
        "why_counted_oa",
        "evidence_event_type_1",
        "evidence_stage_1",
        "evidence_confidence_1",
        "evidence_date_1",
        "evidence_domain_1",
        "evidence_subject_1",
        "evidence_event_type_2",
        "evidence_stage_2",
        "evidence_confidence_2",
        "evidence_date_2",
        "evidence_domain_2",
        "evidence_subject_2",
        "evidence_event_type_3",
        "evidence_stage_3",
        "evidence_confidence_3",
        "evidence_date_3",
        "evidence_domain_3",
        "evidence_subject_3",
    ]
    _write_csv(base, fieldnames, rows)
    _write_csv(false_path, fieldnames, false_rows)

    return {
        "reconcile_csv_path": str(base),
        "oa_false_positives_csv_path": str(false_path),
        "computed_oa_apps": computed_oa_apps,
        "oa_messages": oa_messages,
        "msg_count_by_event_type": msg_counter,
        "app_count_by_max_stage": app_stage_counter,
    }


def build_reconcile_console_summary(
    msg_counter: Counter,
    app_stage_counter: Counter,
    computed_oa_apps: int,
    oa_messages: int,
) -> list[str]:
    lines = ["Reconciliation summary", "msg_count_by_event_type:"]
    for event_type in EVENT_TYPES:
        lines.append(f"- {event_type}: {msg_counter.get(event_type, 0)}")

    lines.append("app_count_by_max_stage:")
    for stage in ["Applied", "OA", "Interview", "Offer", "Rejected", "Withdrawn"]:
        lines.append(f"- {stage}: {app_stage_counter.get(stage, 0)}")

    lines.append(f"computed_oa_apps={computed_oa_apps} vs oa_messages={oa_messages}")
    return lines
