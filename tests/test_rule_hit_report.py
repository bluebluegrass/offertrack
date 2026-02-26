from skills.job_tracker.reporting.rule_hit_report import DecisionRow, build_rule_hit_report


def test_rule_hit_report_sections_and_counts():
    rows = [
        DecisionRow(
            message_id="m1",
            date="2026-02-10T10:00:00+00:00",
            from_domain="gmail.com",
            subject="Accepted: Interview with X",
            thread_id="t1",
            application_key="app1",
            ignored=True,
            ignore_reason="calendar_response_prefix",
            event_type=None,
            stage=None,
            confidence=None,
            rule_id="ignore:calendar_response_prefix",
        ),
        DecisionRow(
            message_id="m2",
            date="2026-02-10T10:01:00+00:00",
            from_domain="companya.com",
            subject="Availability Request for Hiring Manager Interview",
            thread_id="t2",
            application_key="app2",
            ignored=False,
            ignore_reason=None,
            event_type="interview_invite",
            stage="Interview",
            confidence=0.9,
            rule_id="interview_invite:schedule_phrases",
        ),
    ]

    md = build_rule_hit_report(rows, topk=5, run_meta={"source": "gmail", "date_range": "2026-02-01..2026-02-23", "max_messages": "500"})
    assert "## A) Run summary" in md
    assert "total_messages_processed: **2**" in md
    assert "## B) Ignored breakdown" in md
    assert "calendar_response_prefix" in md
    assert "## C) Rule hits" in md
    assert "interview_invite:schedule_phrases" in md
    assert "companya.com" in md
