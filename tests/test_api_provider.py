from fastapi.testclient import TestClient

import api.server as server


def test_auth_status_disconnected_returns_connected_false(monkeypatch):
    monkeypatch.setattr(server, "_session_from_request", lambda request: None)
    client = TestClient(server.app)

    response = client.get("/api/auth/status")

    assert response.status_code == 200
    assert response.json() == {"connected": False}


def test_auth_status_legacy_session_defaults_to_gmail(monkeypatch):
    monkeypatch.setattr(
        server,
        "_session_from_request",
        lambda request: ("session-1", {"token_json": {"access_token": "x"}}),
    )
    client = TestClient(server.app)

    response = client.get("/api/auth/status")

    assert response.status_code == 200
    assert response.json() == {"connected": True, "provider": "gmail"}


def test_auth_status_outlook_provider_is_normalized(monkeypatch):
    monkeypatch.setattr(
        server,
        "_session_from_request",
        lambda request: ("session-2", {"provider": "OUTLOOK", "token_json": {"access_token": "x"}}),
    )
    client = TestClient(server.app)

    response = client.get("/api/auth/status")

    assert response.status_code == 200
    assert response.json() == {"connected": True, "provider": "outlook"}


def test_scan_dispatches_to_outlook_source(monkeypatch):
    captured: dict[str, object] = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        with open(kwargs["ai_result_summary_path"], "w", encoding="utf-8") as f:
            f.write("{}")
        with open(kwargs["ai_application_table_path"], "w", encoding="utf-8") as f:
            f.write("company,position,application_date,current_status,evidence_subject\n")
        with open(kwargs["ai_message_classification_path"], "w", encoding="utf-8") as f:
            f.write("date,company,event_type,subject\n")

    monkeypatch.setattr(
        server,
        "_require_session",
        lambda request: ("session-3", {"provider": "outlook", "token_json": {"access_token": "x"}}),
    )
    monkeypatch.setattr(server, "run", fake_run)
    monkeypatch.setattr(
        server,
        "_resolve_credentials_path",
        lambda requested_path: (_ for _ in ()).throw(AssertionError("should not resolve gmail credentials for outlook")),
    )
    client = TestClient(server.app)

    response = client.post(
        "/api/scan",
        json={
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "email": "",
        },
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert captured["source"] == "outlook"


def test_scan_missing_token_uses_provider_aware_message(monkeypatch):
    monkeypatch.setattr(
        server,
        "_require_session",
        lambda request: ("session-4", {"provider": "gmail"}),
    )
    client = TestClient(server.app)

    response = client.post(
        "/api/scan",
        json={
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "email": "",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Gmail session token is missing. Reconnect."
