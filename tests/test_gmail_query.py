from skills.job_tracker.sources.gmail_readonly import _strict_query_suffix


def test_strict_query_includes_soft_rejection_phrases():
    query = _strict_query_suffix().lower()
    assert "candidate rejection" in query
    assert "journey has come to an end" in query
    assert "application has come to an end" in query
