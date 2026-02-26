"""Sample source for local demo without OAuth."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any


def load_sample_messages(start_date: date, end_date: date) -> list[dict[str, Any]]:
    _ = (start_date, end_date)
    now = datetime.now(timezone.utc)
    return [
        {
            "id": "sample-1",
            "thread_id": "t1",
            "date": now,
            "from_email": "jobs@companya.com",
            "subject": "Thanks for applying",
            "snippet": "Your application has been received",
            "body": "Your application has been received",
        },
        {
            "id": "sample-2",
            "thread_id": "t1",
            "date": now,
            "from_email": "recruiting@companya.com",
            "subject": "Recruiter screen invitation",
            "snippet": "Schedule your recruiter screen interview",
            "body": "Schedule your recruiter screen interview",
        },
        {
            "id": "sample-3",
            "thread_id": "t2",
            "date": now,
            "from_email": "hiring@company.com",
            "subject": "Online assessment",
            "snippet": "Please complete OA",
            "body": "Please complete OA",
        },
        {
            "id": "sample-4",
            "thread_id": "t2",
            "date": now,
            "from_email": "calendar@company.com",
            "subject": "Interview confirmation",
            "snippet": "Your interview has been scheduled",
            "body": "Your interview has been scheduled",
        },
        {
            "id": "sample-5",
            "thread_id": "t2",
            "date": now,
            "from_email": "recruiting@company.com",
            "subject": "Offer letter",
            "snippet": "We are pleased to offer you",
            "body": "We are pleased to offer you",
        },
        {
            "id": "sample-6",
            "thread_id": "t3",
            "date": now,
            "from_email": "no-reply@ashbyhq.com",
            "subject": "Application update",
            "snippet": "We regret to inform you",
            "body": "We regret to inform you",
        },
        {
            "id": "sample-7",
            "thread_id": "t4",
            "date": now,
            "from_email": "candidate@gmail.com",
            "subject": "Application withdrawn",
            "snippet": "I would like to withdraw my application",
            "body": "I would like to withdraw my application",
        },
    ]
