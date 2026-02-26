from datetime import datetime, timezone

from skills.job_tracker.metrics import compute_funnel
from skills.job_tracker.types import Event


def _event(event_type: str, stage: str, app_key: str, subject_hash: str = "h") -> Event:
    return Event(
        type=event_type,
        stage=stage,
        occurred_at=datetime.now(timezone.utc),
        confidence=1.0,
        evidence={"thread_id": app_key, "message_id": app_key, "subject_snippet_hash": subject_hash, "ats_sender": True},
        application_key=app_key,
    )


def test_compute_funnel_counts():
    events = [
        _event("application_received", "Applied", "a1", "h1"),
        _event("interview_invite", "Interview", "a1", "h2"),
        _event("oa", "OA", "a2", "h3"),
        _event("offer", "Offer", "a2", "h4"),
        _event("rejection", "Rejected", "a3", "h5"),
        _event("withdrawn", "Withdrawn", "a4", "h6"),
    ]
    metrics, rates, warnings, _ = compute_funnel(events)

    assert metrics.applications == 4
    assert metrics.replies == 4
    assert metrics.no_replies == 0
    assert metrics.oa == 1
    assert metrics.interviews == 1
    assert metrics.offers == 1
    assert metrics.rejected == 1
    assert metrics.withdrawn == 1
    assert rates.application_to_offer_pct == 25.0
    assert warnings == []
