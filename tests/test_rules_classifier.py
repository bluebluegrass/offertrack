from datetime import datetime, timezone

from skills.job_tracker.classifiers.rules import classify_message, classify_message_with_meta, get_application_key_info
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


def test_candidate_per_diem_is_not_an_interview():
    msg = _msg(
        "Expense Report: Candidate Per Diem - Processed",
        (
            "Your Expense Report, Candidate Per Diem has been audited by SIRVA. "
            "Total amount Approved:150.00 USD"
        ),
        sender="system@sirva.com",
    )
    decision = classify_message_with_meta(msg)
    assert decision.ignored is True
    assert not decision.events


def test_teal_job_tracker_marketing_is_ignored():
    msg = _msg(
        "Track the Status of Every Job Application with Teal",
        (
            "Stay on top of every opportunity. "
            "Keep every opportunity organized in one private dashboard, "
            "with clear visibility into next steps and follow-ups. "
            "No more scattered notes or missed connections."
        ),
        sender="hello@tealhq.com",
    )
    decision = classify_message_with_meta(msg)
    assert decision.ignored is True
    assert not decision.events
    assert decision.rule_id == "ignore:non_employer_tool_marketing"


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


def test_pulsepoint_application_receipt_is_classified_and_keys_to_company_not_intermediary_domain():
    msg = _msg(
        "Your application for Sr. Data Analyst, Customer Reporting (Remote, International) at PulsePoint",
        (
            "Thank you for your interest in a career at PulsePoint. "
            "We have received your application for Sr. Data Analyst, Customer Reporting (Remote, International)."
        ),
        sender="recruiting@webmd.com",
    )
    decision = classify_message_with_meta(msg)
    key_info = get_application_key_info(msg)
    assert decision.ignored is False
    assert decision.events and decision.events[0].type == "application_received"
    assert decision.events[0].stage == "Applied"
    assert key_info.company_name == "pulsepoint"
    assert key_info.application_key == "pulsepoint sr data analyst customer reporting remote international"


def test_pulsepoint_sql_test_request_is_classified_as_oa():
    msg = _msg(
        "Simeng: Sr. Data Analyst, Customer Reporting (Remote, International) @ PulsePoint",
        (
            "If you're interested in moving forward, can you please complete a SQL test as a next step? "
            "It will only take 45 minutes."
        ),
        sender="riley@pulsepoint.com",
    )
    decision = classify_message_with_meta(msg)
    assert decision.ignored is False
    assert decision.events and decision.events[0].type == "oa"
    assert decision.events[0].stage == "OA"


def test_pulsepoint_sql_test_failure_is_classified_as_rejection():
    msg = _msg(
        "SQL Test Update",
        (
            "Thank you for taking the time to complete the SQL test. "
            "Unfortunately you did not pass so we won't be able to proceed further with your candidacy for the role."
        ),
        sender="talent@pulsepoint.com",
    )
    decision = classify_message_with_meta(msg)
    assert decision.ignored is False
    assert decision.events and decision.events[0].type == "rejection"
    assert decision.events[0].stage == "Rejected"
    assert decision.rule_id.startswith("rejection:")


def test_free_domain_interview_reply_is_ignored():
    msg = _msg(
        "Re: Cadence Solutions Interview Confirmation",
        "Thanks, this works for me.",
        sender="candidate@gmail.com",
    )
    decision = classify_message_with_meta(msg)
    assert decision.ignored is True
    assert decision.rule_id == "ignore:free_domain_interview_reply"
    assert not decision.events


def test_ashby_subject_extracts_employer_not_platform_name():
    msg = _msg(
        "Thank you for your Application to Dune",
        "We received your application.",
        sender="no-reply@ashbyhq.com",
    )
    key_info = get_application_key_info(msg)
    assert key_info.company_name == "dune"


def test_teamtailor_mail_subject_extracts_employer_not_platform_name():
    msg = _msg(
        "Update on your application for Podimo",
        "We have an update about your application.",
        sender="algirdas.zalatoris@podimo.teamtailor-mail.com",
    )
    key_info = get_application_key_info(msg)
    assert key_info.company_name == "podimo"
