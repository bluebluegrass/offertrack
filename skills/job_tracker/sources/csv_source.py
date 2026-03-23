"""CSV source adapter returning normalized raw message dictionaries."""

from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


def load_csv_messages(csv_path: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
    path = Path(csv_path).expanduser().resolve()
    if not path.exists():
        raise ValueError(f"CSV file not found: {path}")

    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader, start=1):
            raw_date = (row.get("date") or "").strip()
            try:
                d = date.fromisoformat(raw_date)
            except ValueError:
                continue
            if d < start_date or d > end_date:
                continue

            company = (row.get("company") or "unknown-company").strip()
            stage = (row.get("stage") or "").strip()
            subject = (row.get("subject") or f"{company} {stage}").strip()
            snippet = (row.get("snippet") or f"Stage update: {stage}").strip()
            body = (row.get("body") or snippet).strip()
            sender = (row.get("from_email") or f"careers@{company.lower().replace(' ', '-')}.com").strip()
            out.append(
                {
                    "id": f"csv-{idx}",
                    "thread_id": (row.get("thread_id") or f"csv-{company.lower().replace(' ', '-')}").strip(),
                    "date": datetime(d.year, d.month, d.day, tzinfo=timezone.utc),
                    "from_email": sender,
                    "subject": subject,
                    "snippet": snippet,
                    "body": body,
                }
            )

    return out
