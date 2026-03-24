from datetime import date
import time

from skills.job_tracker.sources.gmail_readonly import fetch_messages


class _FakeExecute:
    def __init__(self, payload):
        self._payload = payload

    def execute(self):
        delay = self._payload.get("_delay", 0)
        if delay:
            time.sleep(delay)
        return self._payload


class _FakeMessages:
    def __init__(self, payloads):
        self._payloads = payloads

    def get(self, *, userId, id, format, metadataHeaders=None):
        assert userId == "me"
        payload = dict(self._payloads[id])
        payload["_format"] = format
        payload["_metadata_headers"] = metadataHeaders
        return _FakeExecute(payload)


class _FakeUsers:
    def __init__(self, payloads):
        self._messages = _FakeMessages(payloads)

    def messages(self):
        return self._messages


class _FakeService:
    def __init__(self, payloads):
        self._users = _FakeUsers(payloads)

    def users(self):
        return self._users


def test_fetch_messages_by_ids_keeps_input_order_for_gmail(monkeypatch, tmp_path):
    credentials_path = tmp_path / "credentials.json"
    credentials_path.write_text("{}", encoding="utf-8")
    token_path = tmp_path / "gmail_token_me.json"
    token_path.write_text("{}", encoding="utf-8")

    payloads = {
        "m1": {
            "id": "m1",
            "threadId": "t1",
            "internalDate": "1700000000000",
            "snippet": "snippet-1",
            "payload": {
                "headers": [
                    {"name": "From", "value": "jobs1@example.com"},
                    {"name": "Subject", "value": "Subject 1"},
                    {"name": "Date", "value": "Mon, 01 Mar 2026 10:00:00 +0000"},
                ],
                "body": {},
            },
            "_delay": 0.05,
        },
        "m2": {
            "id": "m2",
            "threadId": "t2",
            "internalDate": "1700000001000",
            "snippet": "snippet-2",
            "payload": {
                "headers": [
                    {"name": "From", "value": "jobs2@example.com"},
                    {"name": "Subject", "value": "Subject 2"},
                    {"name": "Date", "value": "Mon, 02 Mar 2026 10:00:00 +0000"},
                ],
                "body": {},
            },
            "_delay": 0.0,
        },
    }

    monkeypatch.setattr(
        "skills.job_tracker.sources.gmail_readonly._load_gmail_service",
        lambda *args, **kwargs: _FakeService(payloads),
    )
    monkeypatch.setattr("skills.job_tracker.sources.gmail_readonly.MESSAGE_FETCH_MAX_WORKERS", 2)
    monkeypatch.setattr("skills.job_tracker.sources.gmail_readonly.MESSAGE_FETCH_RETRY_BASE_SLEEP_SEC", 0.0)

    rows = fetch_messages(
        email=None,
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 23),
        credentials_path=str(credentials_path),
        token_dir=str(token_path),
        max_messages=10,
        include_body=False,
        message_ids=["m1", "m2"],
        allow_interactive_auth=False,
    )

    assert [row["id"] for row in rows] == ["m1", "m2"]
    assert [row["subject"] for row in rows] == ["Subject 1", "Subject 2"]
