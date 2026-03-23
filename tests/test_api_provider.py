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
        with open(f"{kwargs['out_dir']}/metrics.json", "w", encoding="utf-8") as f:
            f.write('{"metrics": {"applications": 0, "interviews": 0, "rejected": 0, "offers": 0, "no_replies": 0}}')
        with open(f"{kwargs['out_dir']}/application_summary.csv", "w", encoding="utf-8") as f:
            f.write("company_name,role_title,current_status,evidence_subject\n")

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
    assert captured["ai_classify"] is False
    assert captured["max_messages"] == 300
    assert response.json()["sankey_image_data_url"] == ""


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


def test_scan_enhanced_mode_enables_ai(monkeypatch):
    captured: dict[str, object] = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        with open(kwargs["ai_result_summary_path"], "w", encoding="utf-8") as f:
            f.write("{}")
        with open(kwargs["ai_application_table_path"], "w", encoding="utf-8") as f:
            f.write("company,position,application_date,current_status,evidence_subject\n")
        with open(kwargs["ai_message_classification_path"], "w", encoding="utf-8") as f:
            f.write("date,company,event_type,subject\n")
        with open(f"{kwargs['out_dir']}/metrics.json", "w", encoding="utf-8") as f:
            f.write('{"metrics": {"applications": 0, "interviews": 0, "rejected": 0, "offers": 0, "no_replies": 0}}')
        with open(f"{kwargs['out_dir']}/application_summary.csv", "w", encoding="utf-8") as f:
            f.write("company_name,role_title,current_status,evidence_subject\n")

    monkeypatch.setattr(
        server,
        "_require_session",
        lambda request: ("session-5", {"provider": "gmail", "token_json": {"access_token": "x"}}),
    )
    monkeypatch.setattr(server, "run", fake_run)
    monkeypatch.setattr(server, "_resolve_credentials_path", lambda requested_path: "credentials.json")
    client = TestClient(server.app)

    response = client.post(
        "/api/scan",
        json={
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "scan_mode": "enhanced",
        },
    )

    assert response.status_code == 200
    assert captured["ai_classify"] is True
    assert captured["max_messages"] == 300


def test_scan_compare_returns_summary_and_application_diffs(monkeypatch):
    def fake_run(**kwargs):
        ai_mode = kwargs["ai_classify"]
        if ai_mode:
            with open(kwargs["ai_result_summary_path"], "w", encoding="utf-8") as f:
                f.write(
                    '{"applications": 2, "interviews": 1, "rejections_total": 0, "offers": 0, "no_response": 1}'
                )
            with open(kwargs["ai_application_table_path"], "w", encoding="utf-8") as f:
                f.write(
                    "company,position,application_date,current_status,evidence_subject\n"
                    "OpenAI,Data Platform Engineer,2026-02-01,Interview,Interview invitation\n"
                    "Google,Analytics Engineer,2026-02-03,Applied,Application received\n"
                )
            with open(kwargs["ai_message_classification_path"], "w", encoding="utf-8") as f:
                f.write("date,company,event_type,subject\n")
        else:
            with open(f"{kwargs['out_dir']}/metrics.json", "w", encoding="utf-8") as f:
                f.write('{"metrics": {"applications": 2, "interviews": 0, "rejected": 0, "offers": 0, "no_replies": 2}}')
            with open(f"{kwargs['out_dir']}/application_summary.csv", "w", encoding="utf-8") as f:
                f.write(
                    "company_name,role_title,current_status,evidence_subject\n"
                    "OpenAI,Data Platform Engineer,Applied,Application received\n"
                    "Netflix,Data Engineer,Applied,Thanks for applying\n"
                )

    monkeypatch.setattr(
        server,
        "_require_session",
        lambda request: ("session-6", {"provider": "gmail", "token_json": {"access_token": "x"}}),
    )
    monkeypatch.setattr(server, "run", fake_run)
    monkeypatch.setattr(server, "_resolve_credentials_path", lambda requested_path: "credentials.json")
    client = TestClient(server.app)

    response = client.post(
        "/api/scan/compare",
        json={
            "start_date": "2026-02-01",
            "end_date": "2026-03-23",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["fast"]["summary"]["interviews"] == 0
    assert payload["data"]["enhanced"]["summary"]["interviews"] == 1
    assert payload["data"]["summary_diff"]["interviews"] == {"fast": 0, "enhanced": 1, "delta": -1}
    assert payload["data"]["application_diff"]["fast_count"] == 2
    assert payload["data"]["application_diff"]["enhanced_count"] == 2
    assert payload["data"]["application_diff"]["missing_in_fast"] == [
        {
            "company": "Google",
            "position": "Analytics Engineer",
            "enhanced_status": "Applied",
        }
    ]
    assert payload["data"]["application_diff"]["extra_in_fast"] == [
        {
            "company": "Netflix",
            "position": "Data Engineer",
            "fast_status": "Applied",
        }
    ]
    assert payload["data"]["application_diff"]["status_changed"] == [
        {
            "company": "OpenAI",
            "position": "Data Platform Engineer",
            "fast_status": "Applied",
            "enhanced_status": "Interview",
        }
    ]
