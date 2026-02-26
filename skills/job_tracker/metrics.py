"""Compute funnel metrics from distinct applications and provide audit rows."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from skills.job_tracker.types import Event, FunnelMetrics, FunnelRates

STAGE_RANK = {
    "Applied": 1,
    "OA": 2,
    "Interview": 3,
    "Rejected": 3,
    "Offer": 4,
    "Withdrawn": 0,
}

RESPONSE_EVENT_TYPES = {"interview_invite", "oa", "rejection", "offer", "round_update", "withdrawn"}

EVIDENCE_STAGE_PRIORITY = {
    "Offer": 5,
    "Rejected": 4,
    "Interview": 3,
    "OA": 2,
    "Applied": 1,
    "Withdrawn": 1,
}

AUDIT_COLUMNS = [
    "application_key",
    "company_domain",
    "company_name",
    "role_title",
    "first_seen",
    "last_seen",
    "counted_applied",
    "counted_replied",
    "counted_no_replies",
    "counted_oa",
    "counted_interviews",
    "counted_offers",
    "counted_rejected",
    "counted_withdrawn",
    "max_stage_reached",
    "reply_reason",
    "oa_reason",
    "interview_reason",
    "offer_reason",
    "rejection_reason",
    "withdrawn_reason",
    "evidence_1_date",
    "evidence_1_domain",
    "evidence_1_subject",
    "evidence_1_event_type",
    "evidence_1_stage",
    "evidence_1_confidence",
    "evidence_1_gmail_message_id",
    "evidence_1_thread_id",
    "evidence_1_snippet_hash",
    "evidence_2_date",
    "evidence_2_domain",
    "evidence_2_subject",
    "evidence_2_event_type",
    "evidence_2_stage",
    "evidence_2_confidence",
    "evidence_2_gmail_message_id",
    "evidence_2_thread_id",
    "evidence_2_snippet_hash",
    "evidence_3_date",
    "evidence_3_domain",
    "evidence_3_subject",
    "evidence_3_event_type",
    "evidence_3_stage",
    "evidence_3_confidence",
    "evidence_3_gmail_message_id",
    "evidence_3_thread_id",
    "evidence_3_snippet_hash",
]


@dataclass(slots=True)
class ApplicationAggregate:
    key: str
    first_seen: datetime
    last_seen: datetime
    events: list[Event] = field(default_factory=list)
    event_types: set[str] = field(default_factory=set)
    max_stage_reached: str = "Applied"
    has_rejection: bool = False
    has_withdrawn: bool = False
    company_domain: str = ""
    role_title: str = ""


def _rate(num: int, den: int) -> float:
    return round((num / den * 100.0), 2) if den else 0.0


def _stage_rank(stage: str) -> int:
    return STAGE_RANK.get(stage, 0)


def _max_stage(curr: str, new: str) -> str:
    return new if _stage_rank(new) > _stage_rank(curr) else curr


def _company_name_from_domain(domain: str) -> str:
    if not domain:
        return ""
    parts = domain.split(".")
    if len(parts) < 2:
        return parts[0]
    return parts[-2]


def _extract_role_from_key(app_key: str, company_domain: str) -> str:
    key = app_key.strip()
    if company_domain and key.startswith(company_domain):
        role = key[len(company_domain):].strip()
        return role
    return ""


def build_application_aggregates(events: list[Event]) -> dict[str, ApplicationAggregate]:
    apps: dict[str, ApplicationAggregate] = {}
    for e in sorted(events, key=lambda x: x.occurred_at):
        key = e.application_key
        if key not in apps:
            apps[key] = ApplicationAggregate(key=key, first_seen=e.occurred_at, last_seen=e.occurred_at)

        app = apps[key]
        app.first_seen = min(app.first_seen, e.occurred_at)
        app.last_seen = max(app.last_seen, e.occurred_at)
        app.events.append(e)
        app.event_types.add(e.type)
        app.max_stage_reached = _max_stage(app.max_stage_reached, e.stage)

        if e.type == "rejection" or e.stage == "Rejected":
            app.has_rejection = True
        if e.type == "withdrawn" or e.stage == "Withdrawn":
            app.has_withdrawn = True

        domain = str(e.evidence.get("from_domain", ""))
        if domain and not app.company_domain:
            app.company_domain = domain

    for app in apps.values():
        app.role_title = _extract_role_from_key(app.key, app.company_domain)

    return apps


def _select_evidence(events: list[Event]) -> list[Event]:
    ranked = sorted(
        events,
        key=lambda e: (
            EVIDENCE_STAGE_PRIORITY.get(e.stage, 0),
            float(e.confidence),
            e.occurred_at,
        ),
        reverse=True,
    )
    return ranked[:3]


def build_audit_rows(events: list[Event]) -> list[dict[str, str]]:
    apps = build_application_aggregates(events)
    rows: list[dict[str, str]] = []

    for app in apps.values():
        counted_applied = 1

        has_response = bool(app.event_types & RESPONSE_EVENT_TYPES)
        if not has_response and app.event_types == {"application_received"}:
            has_response = False

        counted_replied = 1 if has_response else 0
        counted_no_replies = 1 if counted_replied == 0 else 0

        has_oa_event = "oa" in app.event_types
        has_interview_event = bool({"interview_invite", "round_update"} & app.event_types)
        has_offer_event = "offer" in app.event_types
        counted_oa = 1 if has_oa_event else 0
        counted_interviews = 1 if has_interview_event else 0
        counted_offers = 1 if has_offer_event else 0
        counted_rejected = 1 if (app.max_stage_reached == "Rejected" or app.has_rejection) else 0
        counted_withdrawn = 1 if app.has_withdrawn else 0

        reply_reason = (
            f"response_event:{','.join(sorted(app.event_types & RESPONSE_EVENT_TYPES))}"
            if counted_replied
            else "no_response_event"
        )
        oa_reason = "has_oa_event" if counted_oa else ""
        interview_reason = "has_interview_event" if counted_interviews else ""
        offer_reason = "has_offer_event" if counted_offers else ""
        rejection_reason = "has_rejection_event" if counted_rejected else ""
        withdrawn_reason = "has_withdrawn_event" if counted_withdrawn else ""

        row = {c: "" for c in AUDIT_COLUMNS}
        row["application_key"] = app.key
        row["company_domain"] = app.company_domain
        row["company_name"] = _company_name_from_domain(app.company_domain)
        row["role_title"] = app.role_title
        row["first_seen"] = app.first_seen.isoformat()
        row["last_seen"] = app.last_seen.isoformat()

        row["counted_applied"] = str(counted_applied)
        row["counted_replied"] = str(counted_replied)
        row["counted_no_replies"] = str(counted_no_replies)
        row["counted_oa"] = str(counted_oa)
        row["counted_interviews"] = str(counted_interviews)
        row["counted_offers"] = str(counted_offers)
        row["counted_rejected"] = str(counted_rejected)
        row["counted_withdrawn"] = str(counted_withdrawn)

        row["max_stage_reached"] = app.max_stage_reached
        row["reply_reason"] = reply_reason
        row["oa_reason"] = oa_reason
        row["interview_reason"] = interview_reason
        row["offer_reason"] = offer_reason
        row["rejection_reason"] = rejection_reason
        row["withdrawn_reason"] = withdrawn_reason

        evidence = _select_evidence(app.events)
        for idx, ev in enumerate(evidence, start=1):
            row[f"evidence_{idx}_date"] = ev.occurred_at.isoformat()
            row[f"evidence_{idx}_domain"] = str(ev.evidence.get("from_domain", ""))
            row[f"evidence_{idx}_subject"] = str(ev.evidence.get("subject", ""))
            row[f"evidence_{idx}_event_type"] = ev.type
            row[f"evidence_{idx}_stage"] = ev.stage
            row[f"evidence_{idx}_confidence"] = f"{float(ev.confidence):.2f}"
            row[f"evidence_{idx}_gmail_message_id"] = str(ev.evidence.get("message_id", ""))
            row[f"evidence_{idx}_thread_id"] = str(ev.evidence.get("thread_id", ""))
            row[f"evidence_{idx}_snippet_hash"] = str(ev.evidence.get("subject_snippet_hash", ""))

        rows.append(row)

    rows.sort(key=lambda r: (r["company_domain"], r["role_title"], r["first_seen"]))
    return rows


def compute_metrics_from_audit_rows(rows: list[dict[str, str]]) -> FunnelMetrics:
    def s(col: str) -> int:
        return sum(int(r.get(col, "0") or "0") for r in rows)

    return FunnelMetrics(
        applications=s("counted_applied"),
        replies=s("counted_replied"),
        no_replies=s("counted_no_replies"),
        oa=s("counted_oa"),
        withdrawn=s("counted_withdrawn"),
        interviews=s("counted_interviews"),
        offers=s("counted_offers"),
        rejected=s("counted_rejected"),
    )


def compute_rates(metrics: FunnelMetrics) -> FunnelRates:
    return FunnelRates(
        reply_rate_pct=_rate(metrics.replies, metrics.applications),
        oa_rate_from_replies_pct=_rate(metrics.oa, metrics.replies),
        interview_rate_from_oa_pct=_rate(metrics.interviews, metrics.oa),
        offer_rate_from_interviews_pct=_rate(metrics.offers, metrics.interviews),
        rejection_rate_from_interviews_pct=_rate(metrics.rejected, metrics.interviews),
        application_to_offer_pct=_rate(metrics.offers, metrics.applications),
    )


def compute_funnel(events: list[Event]) -> tuple[FunnelMetrics, FunnelRates, list[str], list[dict[str, str]]]:
    warnings: list[str] = []
    rows = build_audit_rows(events)
    metrics = compute_metrics_from_audit_rows(rows)
    rates = compute_rates(metrics)

    # Per-row consistency check required by contract.
    bad = [r["application_key"] for r in rows if int(r["counted_replied"]) + int(r["counted_no_replies"]) != int(r["counted_applied"])]
    if bad:
        warnings.append(f"reply/no_reply consistency issue for {len(bad)} applications")

    return metrics, rates, warnings, rows
