"""First-scan relevance filter to remove obvious non-job noise."""

from __future__ import annotations

import csv
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from skills.job_tracker.types import NormalizedMessage

ATS_WHITELIST = {
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "workday.com",
    "myworkday.com",
    "icims.com",
    "icims.eu",
    "smartrecruiters.com",
    "jobvite.com",
    "successfactors.com",
    "teamtailor.com",
    "recruitee.com",
    "hackerrank.com",
    "hackerrankforwork.com",
    "codility.com",
    "codesignal.com",
    "hirevue.com",
}

STRONG_JOB_SIGNALS = [
    "thanks for applying",
    "application received",
    "your application for",
    "interview",
    "availability",
    "schedule",
    "next steps",
    "offer",
    "not moving forward",
    "regret to inform",
    "assessment",
    "coding challenge",
]

INTERVIEW_SCHEDULE_SIGNALS = ["interview", "schedule", "availability", "phone screen", "next steps"]

CALENDAR_VENDORS = {"calendly.com", "zoom.us", "teams.microsoft.com", "microsoft.com"}


@dataclass(slots=True)
class FirstScanDecision:
    keep: bool
    reason: str
    from_domain: str


def extract_domain(from_email: str) -> str:
    m = re.search(r"@([A-Za-z0-9_.-]+)", from_email or "")
    return m.group(1).lower() if m else ""


def _has_any(text: str, needles: list[str]) -> bool:
    s = text.lower()
    return any(n in s for n in needles)


def is_relevant_message(msg: NormalizedMessage) -> FirstScanDecision:
    subject = (msg.subject or "").strip()
    subject_l = subject.lower()
    domain = extract_domain(msg.from_email)

    if subject_l.startswith(("accepted:", "declined:", "tentative:")):
        return FirstScanDecision(False, "calendar_response_subject_prefix", domain)
    if "newsletter" in subject_l or "digest" in subject_l:
        return FirstScanDecision(False, "newsletter_digest_subject", domain)

    has_strong_keyword = _has_any(subject_l, STRONG_JOB_SIGNALS)

    if domain in {"linkedin.com", "bizreach.co.jp"} and not has_strong_keyword:
        return FirstScanDecision(False, "linkedin_bizreach_without_job_signal", domain)

    if domain in ATS_WHITELIST:
        return FirstScanDecision(True, "ats_whitelist_domain", domain)

    if any(domain.endswith(v) for v in CALENDAR_VENDORS):
        if _has_any(subject_l, INTERVIEW_SCHEDULE_SIGNALS):
            return FirstScanDecision(True, "calendar_vendor_with_interview_signal", domain)
        return FirstScanDecision(False, "calendar_vendor_without_interview_signal", domain)

    if has_strong_keyword:
        return FirstScanDecision(True, "strong_subject_signal", domain)

    return FirstScanDecision(False, "no_first_scan_signal", domain)


def apply_first_scan_filter(messages: list[NormalizedMessage]) -> tuple[list[NormalizedMessage], list[dict[str, str]]]:
    kept: list[NormalizedMessage] = []
    rows: list[dict[str, str]] = []
    for msg in messages:
        decision = is_relevant_message(msg)
        if decision.keep:
            kept.append(msg)
        rows.append(
            {
                "gmail_message_id": msg.id,
                "date": msg.date.isoformat(),
                "from_domain": decision.from_domain,
                "subject": (msg.subject or "")[:160],
                "kept_or_dropped": "kept" if decision.keep else "dropped",
                "drop_reason": "" if decision.keep else decision.reason,
            }
        )
    return kept, rows


def write_first_scan_report(path: str, rows: list[dict[str, str]]) -> str:
    out = Path(path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["gmail_message_id", "date", "from_domain", "subject", "kept_or_dropped", "drop_reason"],
        )
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda r: (r["date"], r["gmail_message_id"])))
    return str(out)


def build_first_scan_summary(rows: list[dict[str, str]]) -> list[str]:
    total = len(rows)
    kept_rows = [r for r in rows if r["kept_or_dropped"] == "kept"]
    dropped_rows = [r for r in rows if r["kept_or_dropped"] == "dropped"]

    kept_domain_counter = Counter((r["from_domain"] or "<empty>") for r in kept_rows)
    dropped_domain_counter = Counter((r["from_domain"] or "<empty>") for r in dropped_rows)
    dropped_subject_counter = Counter((r["subject"] or "")[:100] for r in dropped_rows)

    lines = [
        "First-scan summary",
        f"- total fetched: {total}",
        f"- total kept: {len(kept_rows)}",
        f"- total dropped: {len(dropped_rows)}",
        "top 20 kept domains:",
    ]
    for domain, count in kept_domain_counter.most_common(20):
        lines.append(f"- {domain}: {count}")
    lines.append("top 20 dropped domains:")
    for domain, count in dropped_domain_counter.most_common(20):
        lines.append(f"- {domain}: {count}")
    lines.append("top 20 dropped subjects:")
    for subject, count in dropped_subject_counter.most_common(20):
        lines.append(f"- {subject}: {count}")
    return lines
