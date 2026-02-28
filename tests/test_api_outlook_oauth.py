from urllib.parse import parse_qs, urlparse

from fastapi import HTTPException
from fastapi.testclient import TestClient

import api.server as server


def _query(url: str) -> dict[str, list[str]]:
    return parse_qs(urlparse(url).query)


def _clear_ms_env(monkeypatch) -> None:
    keys = (
        "MS_CLIENT_ID",
        "MICROSOFT_CLIENT_ID",
        "AZURE_CLIENT_ID",
        "MS_CLIENT_SECRET",
        "MS_CLENT_SECRET",
        "MICROSOFT_CLIENT_SECRET",
        "AZURE_CLIENT_SECRET",
        "MS_TENANT_ID",
        "MICROSOFT_TENANT_ID",
        "AZURE_TENANT_ID",
    )
    for key in keys:
        monkeypatch.delenv(key, raising=False)


def test_outlook_start_requires_client_id(monkeypatch):
    _clear_ms_env(monkeypatch)
    monkeypatch.setenv("MS_CLIENT_SECRET", "secret")
    client = TestClient(server.app)

    response = client.get("/api/auth/outlook/start", follow_redirects=False)

    assert response.status_code == 500
    assert response.json()["detail"].startswith("MS_CLIENT_ID is not configured")


def test_outlook_start_redirects_to_microsoft_oauth(monkeypatch):
    _clear_ms_env(monkeypatch)
    monkeypatch.setenv("MS_CLIENT_ID", "client-123")
    monkeypatch.setenv("MS_CLIENT_SECRET", "secret-123")
    monkeypatch.setenv("MS_TENANT_ID", "contoso-tenant")
    monkeypatch.setenv("MS_REDIRECT_URI", "https://api.example.com/api/auth/outlook/callback")
    client = TestClient(server.app)

    response = client.get("/api/auth/outlook/start", follow_redirects=False)

    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith("https://login.microsoftonline.com/contoso-tenant/oauth2/v2.0/authorize?")
    query = _query(location)
    assert query["client_id"] == ["client-123"]
    assert query["response_type"] == ["code"]
    assert query["redirect_uri"] == ["https://api.example.com/api/auth/outlook/callback"]
    assert query["response_mode"] == ["query"]
    assert query["prompt"] == ["select_account"]
    assert "Mail.Read" in query["scope"][0]
    assert "offline_access" in query["scope"][0]
    assert query["state"][0]


def test_outlook_start_accepts_client_id_alias(monkeypatch):
    _clear_ms_env(monkeypatch)
    monkeypatch.setenv("AZURE_CLIENT_ID", "azure-client-123")
    monkeypatch.setenv("MS_CLIENT_SECRET", "secret-123")
    client = TestClient(server.app)

    response = client.get("/api/auth/outlook/start", follow_redirects=False)

    assert response.status_code == 302
    query = _query(response.headers["location"])
    assert query["client_id"] == ["azure-client-123"]


def test_outlook_start_accepts_legacy_secret_typo(monkeypatch):
    _clear_ms_env(monkeypatch)
    monkeypatch.setenv("MS_CLIENT_ID", "client-123")
    monkeypatch.setenv("MS_CLENT_SECRET", "legacy-secret-123")
    client = TestClient(server.app)

    response = client.get("/api/auth/outlook/start", follow_redirects=False)

    assert response.status_code == 302


def test_outlook_callback_oauth_error_redirects_to_frontend():
    client = TestClient(server.app)

    response = client.get(
        "/api/auth/outlook/callback?error=access_denied&error_description=Denied+by+user",
        follow_redirects=False,
    )

    assert response.status_code == 302
    query = _query(response.headers["location"])
    assert query["auth"] == ["error"]
    assert query["message"] == ["Denied by user"]


def test_outlook_callback_exchange_failure_redirects_error(monkeypatch):
    state = server.create_state(next_path="/")
    monkeypatch.setattr(
        server,
        "_exchange_outlook_code_for_token",
        lambda code, redirect_uri: (_ for _ in ()).throw(HTTPException(status_code=502, detail="bad token")),
    )
    client = TestClient(server.app)

    response = client.get(f"/api/auth/outlook/callback?state={state}&code=abc", follow_redirects=False)

    assert response.status_code == 302
    query = _query(response.headers["location"])
    assert query["auth"] == ["error"]
    assert query["message"] == ["bad token"]


def test_outlook_callback_success_sets_session_cookie(monkeypatch):
    state = server.create_state(next_path="/")
    saved: dict[str, object] = {}

    def fake_save(session_id: str, payload: dict[str, object]) -> None:
        saved["session_id"] = session_id
        saved["payload"] = payload

    monkeypatch.setattr(
        server,
        "_exchange_outlook_code_for_token",
        lambda code, redirect_uri: {"access_token": "token-1", "refresh_token": "refresh-1"},
    )
    monkeypatch.setattr(server, "create_session_id", lambda: "sid-123")
    monkeypatch.setattr(server, "save_session_payload", fake_save)
    monkeypatch.setattr(server, "sign_session_cookie", lambda session_id: f"signed-{session_id}")
    client = TestClient(server.app)

    response = client.get(f"/api/auth/outlook/callback?state={state}&code=abc", follow_redirects=False)

    assert response.status_code == 302
    query = _query(response.headers["location"])
    assert query["auth"] == ["success"]
    assert saved["session_id"] == "sid-123"
    assert saved["payload"] == {
        "provider": "outlook",
        "token_json": {"access_token": "token-1", "refresh_token": "refresh-1"},
    }
    assert "offertracker_session=signed-sid-123" in response.headers["set-cookie"]
