from datetime import date, datetime, timezone
import json
import time

from skills.job_tracker.sources.outlook_graph import GraphAuthError, _ms_oauth_config, _normalize_message_row, fetch_messages


def test_normalize_message_row_extracts_expected_fields():
    row = _normalize_message_row(
        {
            "id": "msg-1",
            "conversationId": "thread-9",
            "receivedDateTime": "2026-02-01T09:30:00Z",
            "from": {"emailAddress": {"address": "recruiter@example.com"}},
            "subject": "Interview invite",
            "bodyPreview": "Please share your availability",
            "body": {"contentType": "html", "content": "<p>Hello <b>there</b></p>"},
        },
        include_body=True,
    )

    assert row["id"] == "msg-1"
    assert row["thread_id"] == "thread-9"
    assert row["from_email"] == "recruiter@example.com"
    assert row["subject"] == "Interview invite"
    assert row["snippet"] == "Please share your availability"
    assert row["body"] == "Hello there"
    assert row["date"] == datetime(2026, 2, 1, 9, 30, tzinfo=timezone.utc)


def test_ms_oauth_config_accepts_aliases_and_typo(monkeypatch):
    monkeypatch.delenv("MS_CLIENT_ID", raising=False)
    monkeypatch.delenv("MS_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("AZURE_CLIENT_ID", "azure-client-1")
    monkeypatch.setenv("MS_CLENT_SECRET", "legacy-secret-1")
    monkeypatch.setenv("AZURE_TENANT_ID", "tenant-1")

    cfg = _ms_oauth_config()

    assert cfg["client_id"] == "azure-client-1"
    assert cfg["client_secret"] == "legacy-secret-1"
    assert cfg["tenant_id"] == "tenant-1"


def test_fetch_messages_refreshes_expired_token(tmp_path, monkeypatch):
    token_dir = tmp_path / "tokens"
    token_dir.mkdir(parents=True, exist_ok=True)
    token_path = token_dir / "outlook_token_me.json"
    token_path.write_text(
        json.dumps({"access_token": "old-token", "refresh_token": "refresh-1", "expires_at": 1}),
        encoding="utf-8",
    )

    calls: list[str] = []

    def fake_refresh(token_payload):
        assert token_payload["access_token"] == "old-token"
        return {"access_token": "new-token", "refresh_token": "refresh-2", "expires_at": 9999999999}

    def fake_fetch(*, access_token, start_dt, end_dt, include_body, max_messages):
        calls.append(access_token)
        return []

    monkeypatch.setattr("skills.job_tracker.sources.outlook_graph._refresh_access_token", fake_refresh)
    monkeypatch.setattr("skills.job_tracker.sources.outlook_graph._fetch_graph_messages", fake_fetch)

    rows = fetch_messages(
        email=None,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        token_dir=str(token_dir),
        max_messages=50,
        include_body=False,
    )

    assert rows == []
    assert calls == ["new-token"]
    persisted = json.loads(token_path.read_text(encoding="utf-8"))
    assert persisted["access_token"] == "new-token"


def test_fetch_messages_retries_on_graph_auth_error(tmp_path, monkeypatch):
    token_dir = tmp_path / "tokens"
    token_dir.mkdir(parents=True, exist_ok=True)
    token_path = token_dir / "outlook_token_me.json"
    token_path.write_text(
        json.dumps({"access_token": "old-token", "refresh_token": "refresh-1", "expires_at": 9999999999}),
        encoding="utf-8",
    )

    calls: list[str] = []

    def fake_refresh(token_payload):
        return {"access_token": "new-token", "refresh_token": "refresh-2", "expires_at": 9999999999}

    def fake_fetch(*, access_token, start_dt, end_dt, include_body, max_messages):
        calls.append(access_token)
        if len(calls) == 1:
            raise GraphAuthError("expired")
        return [
            {
                "id": "m2",
                "thread_id": "t",
                "date": datetime(2026, 1, 2, tzinfo=timezone.utc),
                "from_email": "a@example.com",
                "subject": "Later",
                "snippet": "s2",
                "body": "",
            },
            {
                "id": "m1",
                "thread_id": "t",
                "date": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "from_email": "a@example.com",
                "subject": "Earlier",
                "snippet": "s1",
                "body": "",
            },
        ]

    monkeypatch.setattr("skills.job_tracker.sources.outlook_graph._refresh_access_token", fake_refresh)
    monkeypatch.setattr("skills.job_tracker.sources.outlook_graph._fetch_graph_messages", fake_fetch)

    rows = fetch_messages(
        email=None,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        token_dir=str(token_dir),
        max_messages=50,
        include_body=False,
    )

    assert calls == ["old-token", "new-token"]
    assert [r["id"] for r in rows] == ["m1", "m2"]
    persisted = json.loads(token_path.read_text(encoding="utf-8"))
    assert persisted["access_token"] == "new-token"


def test_fetch_messages_by_ids_keeps_input_order_for_outlook(tmp_path, monkeypatch):
    token_dir = tmp_path / "tokens"
    token_dir.mkdir(parents=True, exist_ok=True)
    token_path = token_dir / "outlook_token_me.json"
    token_path.write_text(
        json.dumps({"access_token": "token-1", "refresh_token": "refresh-1", "expires_at": 9999999999}),
        encoding="utf-8",
    )

    def fake_graph_get_json(url, access_token):
        assert access_token == "token-1"
        if "/m1?" in url:
            time.sleep(0.05)
            return {
                "id": "m1",
                "conversationId": "t1",
                "receivedDateTime": "2026-03-01T10:00:00Z",
                "from": {"emailAddress": {"address": "jobs1@example.com"}},
                "subject": "Subject 1",
                "bodyPreview": "preview 1",
                "body": {"contentType": "text", "content": "body 1"},
            }
        if "/m2?" in url:
            return {
                "id": "m2",
                "conversationId": "t2",
                "receivedDateTime": "2026-03-02T10:00:00Z",
                "from": {"emailAddress": {"address": "jobs2@example.com"}},
                "subject": "Subject 2",
                "bodyPreview": "preview 2",
                "body": {"contentType": "text", "content": "body 2"},
            }
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr("skills.job_tracker.sources.outlook_graph._graph_get_json", fake_graph_get_json)
    monkeypatch.setattr("skills.job_tracker.sources.outlook_graph.MESSAGE_FETCH_MAX_WORKERS", 2)
    monkeypatch.setattr("skills.job_tracker.sources.outlook_graph.MESSAGE_FETCH_RETRY_BASE_SLEEP_SEC", 0.0)

    rows = fetch_messages(
        email=None,
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 23),
        token_dir=str(token_dir),
        max_messages=10,
        include_body=True,
        message_ids=["m1", "m2"],
    )

    assert [r["id"] for r in rows] == ["m1", "m2"]
    assert [r["body"] for r in rows] == ["body 1", "body 2"]
