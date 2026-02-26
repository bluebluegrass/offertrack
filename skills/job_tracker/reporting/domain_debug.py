"""Per-message domain/company extraction diagnostics."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_domain_report(path: str, rows: list[dict[str, str]]) -> str:
    out = Path(path).expanduser().resolve()
    fieldnames = [
        "gmail_message_id",
        "date",
        "from_email_domain",
        "from_email",
        "subject",
        "thread_id",
        "ignored",
        "ignore_reason",
        "matched_rule_id",
        "event_type",
        "stage",
        "confidence",
        "extracted_company_name",
        "extracted_company_domain",
        "company_domain_source",
        "role_title",
        "role_title_confidence",
        "application_key",
        "key_source",
    ]
    rows_sorted = sorted(rows, key=lambda r: (r.get("date", ""), r.get("gmail_message_id", "")))
    _write_csv(out, fieldnames, rows_sorted)
    return str(out)


def build_domain_debug_console_summary(rows: list[dict[str, str]]) -> list[str]:
    lines: list[str] = ["Domain debug summary"]
    total = len(rows)
    if total == 0:
        lines.append("no messages processed")
        return lines

    from_counter = Counter(r.get("from_email_domain", "") or "<empty>" for r in rows)
    extracted_counter = Counter(r.get("extracted_company_domain", "") or "<unknown>" for r in rows)
    key_counter = Counter(r.get("application_key", "") for r in rows)

    lines.append("top 30 from_email_domain by message count:")
    for domain, count in from_counter.most_common(30):
        lines.append(f"- {domain}: {count}")

    lines.append("top 30 extracted_company_domain by message count:")
    for domain, count in extracted_counter.most_common(30):
        lines.append(f"- {domain}: {count}")

    unknown_count = sum(1 for r in rows if not (r.get("extracted_company_domain", "").strip()))
    same_as_sender = sum(
        1
        for r in rows
        if (r.get("extracted_company_domain", "").strip() and r.get("extracted_company_domain", "") == r.get("from_email_domain", ""))
    )
    lines.append(f"extracted_company_domain empty/unknown: {unknown_count}/{total} ({(100.0 * unknown_count / total):.1f}%)")
    lines.append(f"extracted_company_domain == from_email_domain: {same_as_sender}/{total} ({(100.0 * same_as_sender / total):.1f}%)")

    lines.append("top 20 application_keys by message_count:")
    for key, count in key_counter.most_common(20):
        lines.append(f"- {key}: {count}")
    return lines
