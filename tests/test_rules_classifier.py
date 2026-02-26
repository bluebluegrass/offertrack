from datetime import datetime, timezone

from skills.job_tracker.classifiers.rules import classify_message, classify_message_with_meta
from skills.job_tracker.types import NormalizedMessage


def _msg(subject: str, snippet: str = "", sender: str = "recruiting@company.com") -> NormalizedMessage:
    return NormalizedMessage(
        id="m1",
        date=datetime.now(timezone.utc),
        from_email=sender,
        subject=subject,
        snippet=snippet,
        thread_id="t1",
    )


def test_offer_classification():
    events = classify_message(_msg("Offer letter for the role"))
    assert events and events[0].stage == "Offer"


def test_rejection_classification():
    events = classify_message(_msg("Update on your application", "We regret to inform you"))
    assert events and events[0].stage == "Rejected"


def test_interview_classification():
    events = classify_message(_msg("Interview confirmation", "Your interview has been scheduled"))
    assert events and events[0].stage == "Interview"


def test_invoice_is_not_an_interview():
    msg = _msg(
        "[CloudVendor] Your invoice for team Alpha is now available",
        "View your invoice and receipt in billing.",
        sender="support@billingvendor.com",
    )
    decision = classify_message_with_meta(msg)
    assert decision.ignored is True
    assert not decision.events


def test_profile_purge_is_not_an_interview():
    msg = _msg(
        "Your candidate profile is about to be purged",
        sender="admin@atsvendor.com",
    )
    decision = classify_message_with_meta(msg)
    assert decision.ignored is True
    assert not decision.events


def test_workday_style_thank_you_but_rejected_snippet_maps_to_rejection():
    msg = _msg(
        "Update on your application for Senior Analytics Engineer",
        (
            "Thank you for your application in relation to the Senior Analytics Engineer position... "
            "we unfortunately have to inform you that ... "
            "we have decided not to progress your application further on this occasion"
        ),
        sender="noreply@myworkday.com",
    )
    decision = classify_message_with_meta(msg)
    assert decision.ignored is False
    assert decision.events and decision.events[0].type == "rejection"
    assert decision.events[0].stage == "Rejected"
    assert decision.rule_id.startswith("rejection:")


def test_journey_phrase_maps_to_rejection():
    msg = _msg(
        "Your Application Journey",
        (
            "Candidate Rejection. "
            "Unfortunately, your journey has come to an end for now."
        ),
        sender="noreply@careers.example.com",
    )
    decision = classify_message_with_meta(msg)
    assert decision.ignored is False
    assert decision.events and decision.events[0].type == "rejection"
    assert decision.events[0].stage == "Rejected"
    assert decision.rule_id.startswith("rejection:")
