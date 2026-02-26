from datetime import datetime, timezone

from skills.job_tracker.classifiers.rules import classify_message_with_meta
from skills.job_tracker.metrics import compute_funnel
from skills.job_tracker.types import NormalizedMessage


def _msg(msg_id: str, sender: str, subject: str, snippet: str, thread_id: str, minute: int) -> NormalizedMessage:
    return NormalizedMessage(
        id=msg_id,
        date=datetime(2026, 2, 10, 10, minute, tzinfo=timezone.utc),
        from_email=sender,
        subject=subject,
        snippet=snippet,
        thread_id=thread_id,
    )


def test_noise_filters_and_distinct_application_counting():
    msgs = [
        _msg("m1", "candidate@gmail.com", "Accepted: Interview with X", "calendar notification", "t1", 1),
        _msg("m2", "noreply@recruitmentsurvey.example.com", "Your feedback is important to us", "survey", "t1", 2),
        _msg("m3", "noreply@company.com", "Reminder: Your interview for Data Analyst is on Thursday", "Reminder: tomorrow at 3pm", "t2", 3),
        _msg("m4", "careers@companya.com", "Thanks for applying", "Application received", "t3", 4),
        _msg(
            "m5",
            "recruiting@companya.com",
            "Availability Request for Hiring Manager Interview",
            "Please share availability",
            "t3",
            5,
        ),
        _msg("m6", "recruiting@companya.com", "Reminder: Your interview for Data Analyst is on Thursday", "tomorrow at", "t3", 6),
    ]

    emitted = []
    has_interview = {}
    for m in msgs:
        d = classify_message_with_meta(m)
        for e in d.events:
            if e.type == "interview_reminder" and not has_interview.get(e.application_key, False):
                continue
            if e.stage == "Interview":
                has_interview[e.application_key] = True
            emitted.append(e)

    metrics, _, _, _ = compute_funnel(emitted)

    # Distinct applications, not email count.
    assert metrics.applications == 1
    assert metrics.replies == 1
    assert metrics.interviews == 1

    # Smoke check ignore behavior on known noise rows.
    assert classify_message_with_meta(msgs[0]).ignored is True
    assert classify_message_with_meta(msgs[1]).ignored is True
