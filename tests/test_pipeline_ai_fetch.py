from datetime import datetime, timezone
from pathlib import Path

from skills.job_tracker import pipeline


def _raw_message(message_id: str, *, body: str) -> dict[str, object]:
    return {
        "id": message_id,
        "thread_id": f"thread-{message_id}",
        "date": datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc),
        "from_email": "Recruiter <jobs@example.com>",
        "subject": f"Subject {message_id}",
        "snippet": f"Snippet {message_id}",
        "body": body,
    }


def test_run_gmail_ai_fetches_metadata_then_full_bodies(tmp_path, monkeypatch):
    credentials = tmp_path / "credentials.json"
    credentials.write_text("{}", encoding="utf-8")
    out_dir = tmp_path / "out"
    calls: list[dict[str, object]] = []

    def fake_fetch_messages(**kwargs):
        calls.append(kwargs)
        if kwargs["include_body"] is False:
            assert kwargs.get("message_ids") is None
            return [_raw_message("m1", body=""), _raw_message("m2", body="")]
        assert kwargs["include_body"] is True
        assert kwargs["message_ids"] == ["m1", "m2"]
        return [_raw_message("m1", body="Full body 1"), _raw_message("m2", body="Full body 2")]

    monkeypatch.setattr(pipeline, "fetch_messages", fake_fetch_messages)
    monkeypatch.setattr(pipeline, "classify_messages_with_llm", lambda **kwargs: [])
    monkeypatch.setattr(pipeline, "build_application_rows", lambda rows: [])
    monkeypatch.setattr(
        pipeline,
        "build_ai_result_summary",
        lambda rows: {
            "applications": 0,
            "interviews": 0,
            "no_response": 0,
            "rejections_total": 0,
            "rejections_with_interview": 0,
            "rejections_without_interview": 0,
            "offers": 0,
        },
    )
    monkeypatch.setattr(pipeline, "write_relevant_emails_csv", lambda path, messages: str(Path(path)))
    monkeypatch.setattr(pipeline, "write_ai_message_classification_csv", lambda path, rows: str(Path(path)))
    monkeypatch.setattr(pipeline, "write_ai_application_table_csv", lambda path, rows: str(Path(path)))
    monkeypatch.setattr(pipeline, "write_ai_result_summary_json", lambda path, summary: str(Path(path)))
    monkeypatch.setattr(pipeline, "render_ai_sankey", lambda summary, title, path: str(Path(path)))
    monkeypatch.setattr(pipeline, "render_sankey", lambda metrics, title, path: None)

    seen_bodies: list[str] = []

    def fake_write_relevant(path, messages):
        seen_bodies.extend([m.body for m in messages])
        return str(Path(path))

    monkeypatch.setattr(pipeline, "write_relevant_emails_csv", fake_write_relevant)

    pipeline.run(
        source="gmail",
        start="2026-03-01",
        end="2026-03-23",
        out_dir=str(out_dir),
        credentials_path=str(credentials),
        ai_classify=True,
        allow_interactive_auth=False,
    )

    assert len(calls) == 2
    assert calls[0]["include_body"] is False
    assert calls[1]["include_body"] is True
    assert seen_bodies == ["Full body 1", "Full body 2"]


def test_run_outlook_ai_fetches_metadata_then_full_bodies(tmp_path, monkeypatch):
    out_dir = tmp_path / "out"
    calls: list[dict[str, object]] = []

    def fake_fetch_messages(**kwargs):
        calls.append(kwargs)
        if kwargs["include_body"] is False:
            assert kwargs.get("message_ids") is None
            return [_raw_message("m1", body=""), _raw_message("m2", body="")]
        assert kwargs["include_body"] is True
        assert kwargs["message_ids"] == ["m1", "m2"]
        return [_raw_message("m1", body="Full body 1"), _raw_message("m2", body="Full body 2")]

    monkeypatch.setattr(pipeline, "fetch_outlook_messages", fake_fetch_messages)
    monkeypatch.setattr(pipeline, "classify_messages_with_llm", lambda **kwargs: [])
    monkeypatch.setattr(pipeline, "build_application_rows", lambda rows: [])
    monkeypatch.setattr(
        pipeline,
        "build_ai_result_summary",
        lambda rows: {
            "applications": 0,
            "interviews": 0,
            "no_response": 0,
            "rejections_total": 0,
            "rejections_with_interview": 0,
            "rejections_without_interview": 0,
            "offers": 0,
        },
    )
    monkeypatch.setattr(pipeline, "write_ai_message_classification_csv", lambda path, rows: str(Path(path)))
    monkeypatch.setattr(pipeline, "write_ai_application_table_csv", lambda path, rows: str(Path(path)))
    monkeypatch.setattr(pipeline, "write_ai_result_summary_json", lambda path, summary: str(Path(path)))
    monkeypatch.setattr(pipeline, "render_ai_sankey", lambda summary, title, path: str(Path(path)))
    monkeypatch.setattr(pipeline, "render_sankey", lambda metrics, title, path: None)

    seen_bodies: list[str] = []

    def fake_write_relevant(path, messages):
        seen_bodies.extend([m.body for m in messages])
        return str(Path(path))

    monkeypatch.setattr(pipeline, "write_relevant_emails_csv", fake_write_relevant)

    pipeline.run(
        source="outlook",
        start="2026-03-01",
        end="2026-03-23",
        out_dir=str(out_dir),
        ai_classify=True,
    )

    assert len(calls) == 2
    assert calls[0]["include_body"] is False
    assert calls[1]["include_body"] is True
    assert seen_bodies == ["Full body 1", "Full body 2"]
