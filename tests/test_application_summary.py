import json
from datetime import datetime, timezone

from skills.job_tracker.application_summary import SummaryMessageRow, build_application_summary_rows, compute_metrics_from_application_summary
from skills.job_tracker.types import Event


def _event(event_type: str, stage: str, when_minute: int, msg_id: str, thread_id: str) -> Event:
    return Event(
        type=event_type,
        stage=stage,
        occurred_at=datetime(2026, 2, 2, 12, when_minute, tzinfo=timezone.utc),
        confidence=0.9,
        evidence={
            "message_id": msg_id,
            "thread_id": thread_id,
            "from_domain": "myworkday.com",
            "subject": "Update on your application",
        },
        application_key=thread_id,
    )


def test_summary_terminal_status_rejected_overrides_prior_events():
    thread_id = "t-rej-1"
    messages = [
        SummaryMessageRow(
            message_id="m1",
            thread_id=thread_id,
            date=datetime(2026, 2, 2, 12, 0, tzinfo=timezone.utc),
            from_domain="myworkday.com",
            subject="Thanks for applying",
            extracted_company_name="",
            extracted_company_domain="",
            role_title="senior analytics engineer",
            role_title_confidence=0.9,
            application_key=thread_id,
        ),
        SummaryMessageRow(
            message_id="m2",
            thread_id=thread_id,
            date=datetime(2026, 2, 2, 12, 5, tzinfo=timezone.utc),
            from_domain="myworkday.com",
            subject="Application update",
            extracted_company_name="",
            extracted_company_domain="",
            role_title="senior analytics engineer",
            role_title_confidence=0.9,
            application_key=thread_id,
        ),
        SummaryMessageRow(
            message_id="m3",
            thread_id=thread_id,
            date=datetime(2026, 2, 2, 12, 10, tzinfo=timezone.utc),
            from_domain="myworkday.com",
            subject="Update on your application",
            extracted_company_name="",
            extracted_company_domain="",
            role_title="senior analytics engineer",
            role_title_confidence=0.9,
            application_key=thread_id,
        ),
    ]
    events = [
        _event("application_received", "Applied", 0, "m1", thread_id),
        _event("status_update", "Applied", 5, "m2", thread_id),
        _event("rejection", "Rejected", 10, "m3", thread_id),
    ]

    rows = build_application_summary_rows(messages, events)
    assert len(rows) == 1
    assert rows[0]["current_status"] == "Rejected"
    assert rows[0]["evidence_event_type"] == "rejection"

    payload = json.loads(rows[0]["event_counts_json"])
    assert payload["application_received"] == 1
    assert payload["status_update"] == 1
    assert payload["rejection"] == 1

    metrics, _ = compute_metrics_from_application_summary(rows)
    assert metrics.applications == 1
    assert metrics.rejected == 1
    assert metrics.replies == 1
    assert metrics.no_replies == 0
