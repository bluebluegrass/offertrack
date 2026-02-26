from skills.job_tracker.ai_classifier import build_application_rows, build_ai_result_summary


def test_build_application_rows_groups_by_company():
    rows = [
        {
            "gmail_message_id": "m1",
            "thread_id": "t1",
            "date": "2026-02-01T10:00:00+00:00",
            "is_job_related": "true",
            "company": "companya",
            "position": "data analyst",
            "event_type": "application",
            "status": "Applied",
            "subject": "Thanks for applying",
            "from_email_address": "jobs@companya.com",
        },
        {
            "gmail_message_id": "m2",
            "thread_id": "t1",
            "date": "2026-02-03T10:00:00+00:00",
            "is_job_related": "true",
            "company": "companya",
            "position": "analytics engineer",
            "event_type": "interview",
            "status": "Interviewing",
            "subject": "Interview confirmation",
            "from_email_address": "recruiting@companya.com",
        },
    ]
    app_rows = build_application_rows(rows)
    assert len(app_rows) == 1
    assert app_rows[0]["company"] == "companya"
    assert app_rows[0]["application_date"] == "2026-02-01"
    assert app_rows[0]["current_status"] == "Interviewing"


def test_build_application_rows_picks_terminal_status():
    rows = [
        {
            "gmail_message_id": "m1",
            "thread_id": "t2",
            "date": "2026-02-01T10:00:00+00:00",
            "is_job_related": "true",
            "company": "companya",
            "position": "analytics engineer",
            "event_type": "interview",
            "status": "Interviewing",
            "subject": "Interview",
            "from_email_address": "careers@companya.com",
        },
        {
            "gmail_message_id": "m2",
            "thread_id": "t2",
            "date": "2026-02-05T10:00:00+00:00",
            "is_job_related": "true",
            "company": "companya",
            "position": "analytics engineer",
            "event_type": "rejection",
            "status": "Rejected",
            "subject": "Application update",
            "from_email_address": "careers@companya.com",
        },
    ]
    app_rows = build_application_rows(rows)
    assert len(app_rows) == 1
    assert app_rows[0]["current_status"] == "Rejected"


def test_build_application_rows_falls_back_to_sender_domain_company():
    rows = [
        {
            "gmail_message_id": "m1",
            "thread_id": "t3",
            "date": "2026-02-02T09:00:00+00:00",
            "is_job_related": "true",
            "company": "",
            "position": "data engineer",
            "event_type": "application",
            "status": "Applied",
            "subject": "Thanks for applying",
            "from_email_address": "jobs@companya.com",
        }
    ]
    app_rows = build_application_rows(rows)
    assert len(app_rows) == 1
    assert app_rows[0]["company"] == "companya"


def test_build_application_rows_merges_canonical_company_variants():
    rows = [
        {
            "gmail_message_id": "m1",
            "thread_id": "t5",
            "date": "2025-09-15T10:00:00+00:00",
            "is_job_related": "true",
            "company": "companygroup inc",
            "position": "data engineer",
            "event_type": "interview",
            "status": "Interviewing",
            "subject": "Interview",
            "from_email_address": "hiring@companygroup.com",
        },
        {
            "gmail_message_id": "m2",
            "thread_id": "t6",
            "date": "2025-09-20T10:00:00+00:00",
            "is_job_related": "true",
            "company": "companygroup llc",
            "position": "data engineer",
            "event_type": "offer",
            "status": "Offer",
            "subject": "Offer",
            "from_email_address": "recruiting@companygroup.com",
        },
        {
            "gmail_message_id": "m3",
            "thread_id": "t7",
            "date": "2025-09-22T10:00:00+00:00",
            "is_job_related": "true",
            "company": "companygroup",
            "position": "",
            "event_type": "interview",
            "status": "Interviewing",
            "subject": "Call",
            "from_email_address": "hiring@companygroup.com",
        },
    ]
    app_rows = build_application_rows(rows)
    assert len(app_rows) == 1
    assert app_rows[0]["company"] == "companygroup"


def test_build_application_rows_merges_group_suffix_variant():
    rows = [
        {
            "gmail_message_id": "m1",
            "thread_id": "tx1",
            "date": "2026-02-04T10:00:00+00:00",
            "is_job_related": "true",
            "company": "xebia group",
            "position": "",
            "event_type": "application",
            "status": "Applied",
            "subject": "Confirmation of application",
            "from_email_address": "careers@xebia.com",
        },
        {
            "gmail_message_id": "m2",
            "thread_id": "tx1",
            "date": "2026-02-06T10:00:00+00:00",
            "is_job_related": "true",
            "company": "xebia",
            "position": "analytics engineer",
            "event_type": "rejection",
            "status": "Rejected",
            "subject": "Update on your application",
            "from_email_address": "careers@xebia.com",
        },
    ]
    app_rows = build_application_rows(rows)
    assert len(app_rows) == 1
    assert app_rows[0]["company"] == "xebia"
    assert app_rows[0]["current_status"] == "Rejected"


def test_build_application_rows_maps_assessment_vendor_to_hiring_company():
    rows = [
        {
            "gmail_message_id": "m1",
            "thread_id": "t8",
            "date": "2026-02-11T10:00:00+00:00",
            "is_job_related": "true",
            "company": "hackerrank",
            "position": "data analytics engineer",
            "event_type": "application",
            "status": "Applied",
            "subject": "Your coding assessment invitation",
            "from_email_raw": '"ExampleCo Hiring Team" <support@hackerrankforwork.com>',
            "from_email_address": "support@hackerrankforwork.com",
        },
        {
            "gmail_message_id": "m2",
            "thread_id": "t9",
            "date": "2026-02-11T11:00:00+00:00",
            "is_job_related": "true",
            "company": "exampleco",
            "position": "data analytics engineer",
            "event_type": "interview",
            "status": "Interviewing",
            "subject": "Your interview has been scheduled!",
            "from_email_raw": '"ExampleCo @ icims" <workingatexample+x@talent.icims.eu>',
            "from_email_address": "workingatexample+x@talent.icims.eu",
        },
    ]
    app_rows = build_application_rows(rows)
    assert len(app_rows) == 1
    assert app_rows[0]["company"] == "exampleco"
    assert app_rows[0]["current_status"] == "Interviewing"


def test_build_application_rows_ignores_personal_calendar_rsvp_noise():
    rows = [
        {
            "gmail_message_id": "m1",
            "thread_id": "t10",
            "date": "2026-02-11T09:46:42+00:00",
            "is_job_related": "true",
            "company": "exampleco",
            "position": "data analytics engineer",
            "event_type": "interview",
            "status": "Interviewing",
            "subject": "Your interview has been scheduled!",
            "from_email_address": "workingatexample+x@talent.icims.eu",
        },
        {
            "gmail_message_id": "m2",
            "thread_id": "t11",
            "date": "2026-02-11T10:04:02+00:00",
            "is_job_related": "true",
            "company": "gmail",
            "position": "",
            "event_type": "interview",
            "status": "Interviewing",
            "subject": "Accepted: Your interview has been scheduled!",
            "from_email_address": "candidate@gmail.com",
        },
    ]
    app_rows = build_application_rows(rows)
    assert len(app_rows) == 1
    assert app_rows[0]["company"] == "exampleco"


def test_build_application_rows_merges_by_non_intermediary_sender_domain():
    rows = [
        {
            "gmail_message_id": "m1",
            "thread_id": "t12",
            "date": "2026-02-10T10:00:00+00:00",
            "is_job_related": "true",
            "company": "companya technologies",
            "position": "data engineer",
            "event_type": "interview",
            "status": "Interviewing",
            "subject": "Next steps with CompanyA",
            "from_email_raw": '"CompanyA Hiring Team" <recruiting@teamcompanya.com>',
            "from_email_address": "recruiting@teamcompanya.com",
        },
        {
            "gmail_message_id": "m2",
            "thread_id": "t13",
            "date": "2026-02-11T10:00:00+00:00",
            "is_job_related": "true",
            "company": "teamcompanya",
            "position": "",
            "event_type": "application",
            "status": "Applied",
            "subject": "Application received",
            "from_email_raw": '"CompanyA Hiring Team" <recruiting@teamcompanya.com>',
            "from_email_address": "recruiting@teamcompanya.com",
        },
    ]
    app_rows = build_application_rows(rows)
    assert len(app_rows) == 1
    assert app_rows[0]["company"] == "companya"


def test_build_application_rows_does_not_merge_intermediary_vendor_domain():
    rows = [
        {
            "gmail_message_id": "m1",
            "thread_id": "t14",
            "date": "2026-02-10T10:00:00+00:00",
            "is_job_related": "true",
            "company": "companyalpha",
            "position": "engineer",
            "event_type": "application",
            "status": "Applied",
            "subject": "Application received",
            "from_email_raw": '"CompanyAlpha via ATS" <no-reply@greenhouse.io>',
            "from_email_address": "no-reply@greenhouse.io",
        },
        {
            "gmail_message_id": "m2",
            "thread_id": "t15",
            "date": "2026-02-11T10:00:00+00:00",
            "is_job_related": "true",
            "company": "companybeta",
            "position": "engineer",
            "event_type": "application",
            "status": "Applied",
            "subject": "Application received",
            "from_email_raw": '"CompanyBeta via ATS" <no-reply@greenhouse.io>',
            "from_email_address": "no-reply@greenhouse.io",
        },
    ]
    app_rows = build_application_rows(rows)
    assert len(app_rows) == 2
    companies = sorted(r["company"] for r in app_rows)
    assert companies == ["companyalpha", "companybeta"]


def test_build_application_rows_merges_domain_label_variants_within_same_domain():
    rows = [
        {
            "gmail_message_id": "m1",
            "thread_id": "t16",
            "date": "2026-02-10T10:00:00+00:00",
            "is_job_related": "true",
            "company": "companya",
            "position": "data engineer",
            "event_type": "offer",
            "status": "Offer",
            "subject": "Your CompanyA Offer",
            "from_email_raw": '"CompanyA Hiring Team" <hiring@teamcompanya.com>',
            "from_email_address": "hiring@teamcompanya.com",
        },
        {
            "gmail_message_id": "m2",
            "thread_id": "t17",
            "date": "2026-02-10T11:00:00+00:00",
            "is_job_related": "true",
            "company": "teamcompanya",
            "position": "",
            "event_type": "interview",
            "status": "Interviewing",
            "subject": "Invitation: Recruiter call",
            "from_email_raw": '"CompanyA Hiring Team" <hiring@teamcompanya.com>',
            "from_email_address": "hiring@teamcompanya.com",
        },
    ]
    app_rows = build_application_rows(rows)
    assert len(app_rows) == 1
    assert app_rows[0]["company"] == "companya"


def test_build_ai_result_summary_counts():
    rows = [
        {
            "gmail_message_id": "m1",
            "thread_id": "t1",
            "date": "2026-02-01T10:00:00+00:00",
            "is_job_related": "true",
            "company": "alpha",
            "position": "analyst",
            "event_type": "application",
            "status": "Applied",
            "subject": "Thanks",
            "from_email_address": "jobs@alpha.com",
        },
        {
            "gmail_message_id": "m2",
            "thread_id": "t1",
            "date": "2026-02-03T10:00:00+00:00",
            "is_job_related": "true",
            "company": "alpha",
            "position": "analyst",
            "event_type": "interview",
            "status": "Interviewing",
            "subject": "Invitation: Interview with Alpha @ Tue 10:00",
            "from_email_address": "jobs@alpha.com",
        },
        {
            "gmail_message_id": "m3",
            "thread_id": "t1",
            "date": "2026-02-04T10:00:00+00:00",
            "is_job_related": "true",
            "company": "alpha",
            "position": "analyst",
            "event_type": "rejection",
            "status": "Rejected",
            "subject": "Rejected",
            "from_email_address": "jobs@alpha.com",
        },
        {
            "gmail_message_id": "m4",
            "thread_id": "t2",
            "date": "2026-02-02T10:00:00+00:00",
            "is_job_related": "true",
            "company": "beta",
            "position": "engineer",
            "event_type": "rejection",
            "status": "Rejected",
            "subject": "Rejected",
            "from_email_address": "jobs@beta.com",
        },
        {
            "gmail_message_id": "m5",
            "thread_id": "t3",
            "date": "2026-02-05T10:00:00+00:00",
            "is_job_related": "true",
            "company": "gamma",
            "position": "manager",
            "event_type": "offer",
            "status": "Offer",
            "subject": "Offer",
            "from_email_address": "jobs@gamma.com",
        },
        {
            "gmail_message_id": "m6",
            "thread_id": "t4",
            "date": "2026-02-06T10:00:00+00:00",
            "is_job_related": "true",
            "company": "delta",
            "position": "analyst",
            "event_type": "application",
            "status": "Applied",
            "subject": "Application received",
            "from_email_address": "jobs@delta.com",
        },
    ]
    summary = build_ai_result_summary(rows)
    assert summary["applications"] == 4
    assert summary["interviews"] == 1
    assert summary["no_response"] == 1
    assert summary["rejections_total"] == 2
    assert summary["rejections_with_interview"] == 1
    assert summary["rejections_without_interview"] == 1
    assert summary["offers"] == 1


def test_build_ai_result_summary_does_not_count_generic_future_call_language_as_interview():
    rows = [
        {
            "gmail_message_id": "m1",
            "thread_id": "t20",
            "date": "2026-02-01T10:00:00+00:00",
            "is_job_related": "true",
            "company": "deel",
            "position": "ghostbuster",
            "event_type": "interview",
            "status": "Interviewing",
            "subject": "Deel // Nice to Meet You!",
            "body": "If there is strong alignment we will schedule a call to get to know you better.",
            "from_email_address": "talent@deel.com",
        },
        {
            "gmail_message_id": "m2",
            "thread_id": "t20",
            "date": "2026-02-03T10:00:00+00:00",
            "is_job_related": "true",
            "company": "deel",
            "position": "ghostbuster",
            "event_type": "rejection",
            "status": "Rejected",
            "subject": "Update on your application at Deel",
            "from_email_address": "talent@deel.com",
        },
    ]
    app_rows = build_application_rows(rows)
    assert len(app_rows) == 1
    assert app_rows[0]["current_status"] == "Rejected"

    summary = build_ai_result_summary(rows)
    assert summary["applications"] == 1
    assert summary["interviews"] == 0
    assert summary["rejections_total"] == 1
    assert summary["rejections_with_interview"] == 0
    assert summary["rejections_without_interview"] == 1
