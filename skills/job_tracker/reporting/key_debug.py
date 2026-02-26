"""Application key quality debug outputs."""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

STAGE_RANK = {
    "Applied": 1,
    "OA": 2,
    "Interview": 3,
    "Rejected": 3,
    "Offer": 4,
    "Withdrawn": 0,
    "": 0,
}

RESPONSE_EVENT_TYPES = {"interview_invite", "oa", "rejection", "offer", "round_update"}


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_applications_debug_rows(message_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in message_rows:
        grouped[r["built_application_key"]].append(r)

    out: list[dict[str, str]] = []
    for key, rows in grouped.items():
        rows_sorted = sorted(rows, key=lambda x: x["date"])
        first_seen = rows_sorted[0]["date"] if rows_sorted else ""
        last_seen = rows_sorted[-1]["date"] if rows_sorted else ""
        message_count = len(rows)
        classified_count = sum(1 for r in rows if r["ignored"] == "false" and r["event_type"])
        ignored_count = sum(1 for r in rows if r["ignored"] == "true")

        max_stage = "Applied"
        has_response = False
        has_oa = False
        has_interview = False
        has_offer = False
        has_rejection = False
        has_withdrawn = False

        for r in rows:
            st = r["stage"]
            if STAGE_RANK.get(st, 0) > STAGE_RANK.get(max_stage, 0):
                max_stage = st
            et = r["event_type"]
            if et in RESPONSE_EVENT_TYPES:
                has_response = True
            if st == "OA":
                has_oa = True
            if st == "Interview":
                has_interview = True
            if st == "Offer":
                has_offer = True
            if st == "Rejected" or et == "rejection":
                has_rejection = True
            if st == "Withdrawn" or et == "withdrawn":
                has_withdrawn = True

        newest_subjects = [r["subject"][:90] for r in sorted(rows, key=lambda x: x["date"], reverse=True)]
        top_subjects = newest_subjects[:3] + [""] * max(0, 3 - len(newest_subjects))

        # Use the most common metadata values for key-level display.
        def common(field: str) -> str:
            c = Counter((r.get(field, "") for r in rows if r.get(field, "")))
            return c.most_common(1)[0][0] if c else ""

        out.append(
            {
                "application_key": key,
                "key_source": common("key_source"),
                "company_domain": common("extracted_company_domain"),
                "company_name": common("extracted_company_name"),
                "role_title": common("extracted_role_title"),
                "role_title_source": "parsed" if common("extracted_role_title") else "unknown",
                "first_seen": first_seen,
                "last_seen": last_seen,
                "message_count": str(message_count),
                "classified_message_count": str(classified_count),
                "ignored_message_count": str(ignored_count),
                "max_stage_reached": max_stage,
                "has_response": "1" if has_response else "0",
                "has_oa": "1" if has_oa else "0",
                "has_interview": "1" if has_interview else "0",
                "has_offer": "1" if has_offer else "0",
                "has_rejection": "1" if has_rejection else "0",
                "has_withdrawn": "1" if has_withdrawn else "0",
                "top_subject_1": top_subjects[0],
                "top_subject_2": top_subjects[1],
                "top_subject_3": top_subjects[2],
            }
        )

    out.sort(key=lambda r: (r["company_domain"], r["role_title"], r["first_seen"]))
    return out


def build_company_collisions_rows(app_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in app_rows:
        grouped[r["company_domain"]].append(r)

    out: list[dict[str, str]] = []
    for company_domain, rows in grouped.items():
        distinct_keys = len(rows)
        total_messages = sum(int(r["message_count"]) for r in rows)
        missing_role = sum(1 for r in rows if not r["role_title"].strip())
        pct_missing = (missing_role / distinct_keys) if distinct_keys else 0.0

        max_row = max(rows, key=lambda x: int(x["message_count"])) if rows else None
        max_messages = int(max_row["message_count"]) if max_row else 0

        notes = []
        if pct_missing > 0.5:
            notes.append("ROLE_EXTRACTION_WEAK")
        if max_messages > 10 and (not (max_row or {}).get("role_title", "").strip()):
            notes.append("MERGE_SUSPECT")

        out.append(
            {
                "company_domain": company_domain,
                "distinct_application_keys": str(distinct_keys),
                "total_messages": str(total_messages),
                "keys_missing_role_title": str(missing_role),
                "pct_keys_missing_role_title": f"{pct_missing:.2f}",
                "max_messages_in_single_key": str(max_messages),
                "example_application_key_with_max_messages": (max_row or {}).get("application_key", ""),
                "example_role_title_for_that_key": (max_row or {}).get("role_title", ""),
                "notes": "|".join(notes),
            }
        )

    out.sort(key=lambda r: (-int(r["total_messages"]), r["company_domain"]))
    return out


def build_role_extraction_debug_rows(message_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    out = []
    for r in message_rows:
        # application seed message: any classified message (current app creation behavior)
        if not r.get("event_type"):
            continue
        out.append(
            {
                "gmail_message_id": r["gmail_message_id"],
                "date": r["date"],
                "from_domain": r["from_domain"],
                "subject": r["subject"][:160],
                "thread_id": r["thread_id"],
                "extracted_company_domain": r["extracted_company_domain"],
                "extracted_company_name": r["extracted_company_name"],
                "extracted_role_title": r["extracted_role_title"],
                "role_title_confidence": r["role_title_confidence"],
                "built_application_key": r["built_application_key"],
                "key_source": r["key_source"],
                "matched_rule_id": r["matched_rule_id"],
                "event_type": r["event_type"],
                "stage": r["stage"],
                "confidence": r["confidence"],
                "ignored": r["ignored"],
                "ignore_reason": r["ignore_reason"],
            }
        )
    out.sort(key=lambda r: (r["date"], r["gmail_message_id"]))
    return out


def write_key_debug_outputs(message_rows: list[dict[str, str]], debug_dir: str) -> dict[str, str]:
    base = Path(debug_dir).expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)

    app_rows = build_applications_debug_rows(message_rows)
    company_rows = build_company_collisions_rows(app_rows)
    role_rows = build_role_extraction_debug_rows(message_rows)

    app_path = base / "applications_debug.csv"
    company_path = base / "company_collisions.csv"
    role_path = base / "role_extraction_debug.csv"

    _write_csv(
        app_path,
        [
            "application_key",
            "key_source",
            "company_domain",
            "company_name",
            "role_title",
            "role_title_source",
            "first_seen",
            "last_seen",
            "message_count",
            "classified_message_count",
            "ignored_message_count",
            "max_stage_reached",
            "has_response",
            "has_oa",
            "has_interview",
            "has_offer",
            "has_rejection",
            "has_withdrawn",
            "top_subject_1",
            "top_subject_2",
            "top_subject_3",
        ],
        app_rows,
    )

    _write_csv(
        company_path,
        [
            "company_domain",
            "distinct_application_keys",
            "total_messages",
            "keys_missing_role_title",
            "pct_keys_missing_role_title",
            "max_messages_in_single_key",
            "example_application_key_with_max_messages",
            "example_role_title_for_that_key",
            "notes",
        ],
        company_rows,
    )

    _write_csv(
        role_path,
        [
            "gmail_message_id",
            "date",
            "from_domain",
            "subject",
            "thread_id",
            "extracted_company_domain",
            "extracted_company_name",
            "extracted_role_title",
            "role_title_confidence",
            "built_application_key",
            "key_source",
            "matched_rule_id",
            "event_type",
            "stage",
            "confidence",
            "ignored",
            "ignore_reason",
        ],
        role_rows,
    )

    return {
        "applications_debug": str(app_path),
        "company_collisions": str(company_path),
        "role_extraction_debug": str(role_path),
    }


def build_key_debug_console_summary(message_rows: list[dict[str, str]]) -> list[str]:
    app_rows = build_applications_debug_rows(message_rows)
    company_rows = build_company_collisions_rows(app_rows)

    lines: list[str] = []
    lines.append("Key debug summary")
    lines.append("top 10 companies by total_messages:")
    for r in company_rows[:10]:
        lines.append(f"- {r['company_domain']}: {r['total_messages']}")

    lines.append("top 10 application_keys by message_count:")
    top_keys = sorted(app_rows, key=lambda x: (-int(x["message_count"]), x["application_key"]))[:10]
    for r in top_keys:
        lines.append(f"- {r['application_key']}: {r['message_count']}")

    missing_role = sum(1 for r in app_rows if not r["role_title"].strip())
    total_keys = len(app_rows)
    lines.append(f"applications with missing role_title: {missing_role}/{total_keys}")

    thread_fallback = sum(1 for r in app_rows if r["key_source"] == "thread_fallback")
    pct_fallback = (thread_fallback / total_keys * 100.0) if total_keys else 0.0
    lines.append(f"percent of keys built via thread_fallback: {pct_fallback:.1f}%")

    return lines
