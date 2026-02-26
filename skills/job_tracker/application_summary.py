"""Application truth-table summary and metrics derived from it."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from skills.job_tracker.types import Event, FunnelMetrics, FunnelRates

ATS_DOMAINS = {"myworkday.com", "workday.com", "greenhouse.io", "lever.co", "icims.com", "icims.eu", "ashbyhq.com"}

STATUS_PRIORITY = {
    "Applied": 10,
    "In Review": 20,
    "OA": 30,
    "Interviewing": 40,
    "Offer": 50,
    "Rejected": 60,
    "Withdrawn": 70,
}


@dataclass(slots=True)
class SummaryMessageRow:
    message_id: str
    thread_id: str
    date: datetime
    from_domain: str
    subject: str
    extracted_company_name: str
    extracted_company_domain: str
    role_title: str
    role_title_confidence: float
    application_key: str


def _rate(num: int, den: int) -> float:
    return round((num / den * 100.0), 2) if den else 0.0


def _is_ats_domain(domain: str) -> bool:
    return domain in ATS_DOMAINS or any(domain.endswith(d) for d in ATS_DOMAINS)


def _normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s.lower())).strip()


def _extract_company_name_from_subject(subject: str) -> str:
    patterns = [
        r"\brole at ([A-Z][A-Za-z0-9& .'-]{1,64})",
        r"\bposition at ([A-Z][A-Za-z0-9& .'-]{1,64})",
        r"\bat ([A-Z][A-Za-z0-9& .'-]{1,64})",
    ]
    for p in patterns:
        m = re.search(p, subject)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip(" .,-|").lower()
    return ""


def _fallback_app_id(row: SummaryMessageRow) -> str:
    if row.role_title_confidence >= 0.6 and row.extracted_company_domain and row.role_title:
        return f"key:{_normalize_text(row.extracted_company_domain)}|{_normalize_text(row.role_title)}"
    seed = f"{row.from_domain}|{row.subject[:80].lower()}|{row.application_key}"
    return f"hash:{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:12]}"


def _application_id(row: SummaryMessageRow) -> str:
    if row.thread_id:
        return f"thread:{row.thread_id}"
    return _fallback_app_id(row)


def _status_from_events(events: list[Event]) -> str:
    event_types = {e.type for e in events}
    if "withdrawn" in event_types:
        return "Withdrawn"
    if "rejection" in event_types:
        return "Rejected"
    if "offer" in event_types:
        return "Offer"
    if "interview_invite" in event_types or "round_update" in event_types:
        return "Interviewing"
    if "oa" in event_types:
        return "OA"
    if "status_update" in event_types:
        return "In Review"
    if "application_received" in event_types:
        return "Applied"
    return "Applied"


def _evidence_rank(ev: Event) -> tuple[int, float, datetime]:
    event_rank = {
        "withdrawn": 7,
        "rejection": 6,
        "offer": 5,
        "interview_invite": 4,
        "round_update": 4,
        "oa": 3,
        "status_update": 2,
        "application_received": 1,
    }
    return (event_rank.get(ev.type, 0), float(ev.confidence), ev.occurred_at)


def build_application_summary_rows(messages: list[SummaryMessageRow], events: list[Event]) -> list[dict[str, str]]:
    by_app_messages: dict[str, list[SummaryMessageRow]] = defaultdict(list)
    by_app_events: dict[str, list[Event]] = defaultdict(list)
    msg_to_app: dict[str, str] = {}

    for row in messages:
        app_id = _application_id(row)
        by_app_messages[app_id].append(row)
        msg_to_app[row.message_id] = app_id

    for ev in events:
        msg_id = str(ev.evidence.get("message_id", ""))
        app_id = msg_to_app.get(msg_id)
        if not app_id:
            thread_id = str(ev.evidence.get("thread_id", "")).strip()
            app_id = f"thread:{thread_id}" if thread_id else f"key:{_normalize_text(ev.application_key)}"
        by_app_events[app_id].append(ev)

    rows: list[dict[str, str]] = []
    for app_id in sorted(set(by_app_messages.keys()) | set(by_app_events.keys())):
        msgs = sorted(by_app_messages.get(app_id, []), key=lambda m: m.date)
        evs = sorted(by_app_events.get(app_id, []), key=lambda e: e.occurred_at)
        if not msgs and not evs:
            continue

        thread_id = msgs[0].thread_id if msgs else ""
        message_count = len(msgs)

        # Domain/name resolution with ATS handling.
        non_ats_domains = [m.from_domain for m in msgs if m.from_domain and not _is_ats_domain(m.from_domain)]
        company_domain = Counter(non_ats_domains).most_common(1)[0][0] if non_ats_domains else ""
        if not company_domain:
            extracted_domains = [m.extracted_company_domain for m in msgs if m.extracted_company_domain]
            company_domain = Counter(extracted_domains).most_common(1)[0][0] if extracted_domains else (msgs[0].from_domain if msgs else "")

        company_name = ""
        if msgs and _is_ats_domain(msgs[0].from_domain):
            names = [_extract_company_name_from_subject(m.subject) for m in msgs]
            names = [n for n in names if n]
            if names:
                company_name = Counter(names).most_common(1)[0][0]
        if not company_name:
            extracted_names = [m.extracted_company_name for m in msgs if m.extracted_company_name]
            company_name = Counter(extracted_names).most_common(1)[0][0] if extracted_names else ""
        if not company_name and company_domain:
            parts = company_domain.split(".")
            company_name = parts[-2] if len(parts) >= 2 else company_domain

        role_candidates = sorted(
            [m for m in msgs if m.role_title],
            key=lambda m: (m.role_title_confidence, m.date),
            reverse=True,
        )
        role_title = role_candidates[0].role_title if role_candidates else ""

        status = _status_from_events(evs)
        last_event_date = evs[-1].occurred_at if evs else (msgs[-1].date if msgs else datetime.utcnow())

        if evs:
            evidence = sorted(evs, key=_evidence_rank, reverse=True)[0]
            evidence_from_domain = str(evidence.evidence.get("from_domain", ""))
            evidence_subject = str(evidence.evidence.get("subject", ""))[:160]
            evidence_event_type = evidence.type
            evidence_stage = evidence.stage
            evidence_confidence = f"{float(evidence.confidence):.2f}"
        else:
            evidence_from_domain = msgs[-1].from_domain if msgs else ""
            evidence_subject = msgs[-1].subject[:160] if msgs else ""
            evidence_event_type = ""
            evidence_stage = ""
            evidence_confidence = ""

        event_counts = Counter(e.type for e in evs)
        rows.append(
            {
                "application_id": app_id,
                "thread_id": thread_id,
                "company_name": company_name,
                "company_domain": company_domain,
                "role_title": role_title,
                "current_status": status,
                "last_event_date": last_event_date.isoformat(),
                "evidence_from_domain": evidence_from_domain,
                "evidence_subject": evidence_subject,
                "evidence_event_type": evidence_event_type,
                "evidence_stage": evidence_stage,
                "evidence_confidence": evidence_confidence,
                "message_count": str(message_count),
                "event_counts_json": json.dumps(dict(sorted(event_counts.items())), separators=(",", ":")),
            }
        )

    rows.sort(key=lambda r: (r["company_domain"], r["role_title"], r["last_event_date"]))
    return rows


def compute_metrics_from_application_summary(rows: list[dict[str, str]]) -> tuple[FunnelMetrics, FunnelRates]:
    applications = len(rows)
    replies = sum(1 for r in rows if r["current_status"] != "Applied")
    no_replies = sum(1 for r in rows if r["current_status"] == "Applied")

    def _event_count(r: dict[str, str], event_type: str) -> int:
        try:
            payload = json.loads(r.get("event_counts_json", "{}"))
        except json.JSONDecodeError:
            return 0
        return int(payload.get(event_type, 0))

    has_oa = lambda r: _event_count(r, "oa") > 0
    has_interview = lambda r: (_event_count(r, "interview_invite") + _event_count(r, "round_update")) > 0

    oa = sum(1 for r in rows if r["current_status"] in {"OA", "Interviewing", "Offer", "Rejected", "Withdrawn"} and has_oa(r))
    interviews = sum(
        1
        for r in rows
        if r["current_status"] in {"Interviewing", "Offer", "Rejected", "Withdrawn"} and has_interview(r)
    )
    offers = sum(1 for r in rows if r["current_status"] == "Offer")
    rejected = sum(1 for r in rows if r["current_status"] == "Rejected")
    withdrawn = sum(1 for r in rows if r["current_status"] == "Withdrawn")

    metrics = FunnelMetrics(
        applications=applications,
        replies=replies,
        no_replies=no_replies,
        oa=oa,
        withdrawn=withdrawn,
        interviews=interviews,
        offers=offers,
        rejected=rejected,
    )
    rates = FunnelRates(
        reply_rate_pct=_rate(metrics.replies, metrics.applications),
        oa_rate_from_replies_pct=_rate(metrics.oa, metrics.replies),
        interview_rate_from_oa_pct=_rate(metrics.interviews, metrics.oa),
        offer_rate_from_interviews_pct=_rate(metrics.offers, metrics.interviews),
        rejection_rate_from_interviews_pct=_rate(metrics.rejected, metrics.interviews),
        application_to_offer_pct=_rate(metrics.offers, metrics.applications),
    )
    return metrics, rates


def write_application_summary_csv(path: str, rows: list[dict[str, str]]) -> str:
    out = Path(path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "application_id",
        "thread_id",
        "company_name",
        "company_domain",
        "role_title",
        "current_status",
        "last_event_date",
        "evidence_from_domain",
        "evidence_subject",
        "evidence_event_type",
        "evidence_stage",
        "evidence_confidence",
        "message_count",
        "event_counts_json",
    ]
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return str(out)


def build_company_console_summary(rows: list[dict[str, str]]) -> list[str]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        grouped[r["company_domain"] or "<unknown>"].append(r)
    lines = ["Application summary by company_domain"]
    for domain, domain_rows in sorted(grouped.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        roles_count = len({(r["role_title"] or "").strip().lower() for r in domain_rows})
        status_counts = Counter(r["current_status"] for r in domain_rows)
        breakdown = ", ".join(f"{k}:{status_counts[k]}" for k in sorted(status_counts.keys(), key=lambda s: STATUS_PRIORITY.get(s, 0), reverse=True))
        lines.append(f"- {domain} | roles_count={roles_count} | {breakdown}")
    return lines
