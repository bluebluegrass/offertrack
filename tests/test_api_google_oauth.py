from __future__ import annotations

import json
import sys
from types import ModuleType
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

import api.server as server


def _query(url: str) -> dict[str, list[str]]:
    return parse_qs(urlparse(url).query)


def _install_fake_google_flow(monkeypatch):
    module = ModuleType("google_auth_oauthlib.flow")

    class FakeCredentials:
        def to_json(self) -> str:
            return json.dumps({"access_token": "token-1", "refresh_token": "refresh-1"})

    class FakeFlow:
        last_instance = None

        def __init__(self, *, state: str | None = None):
            self.redirect_uri = ""
            self.code_verifier = ""
            self.state = state
            self.fetch_kwargs = {}
            self.credentials = FakeCredentials()

        @classmethod
        def from_client_config(cls, client_config, scopes, state=None):  # noqa: ANN001
            inst = cls(state=state)
            cls.last_instance = inst
            return inst

        def authorization_url(self, **kwargs):
            state = kwargs.get("state", "")
            return f"https://accounts.google.com/o/oauth2/auth?state={state}", None

        def fetch_token(self, **kwargs):
            self.fetch_kwargs = kwargs

    module.Flow = FakeFlow
    monkeypatch.setitem(sys.modules, "google_auth_oauthlib.flow", module)
    return FakeFlow


def test_google_start_sets_pkce_verifier_in_state(monkeypatch):
    fake_flow_cls = _install_fake_google_flow(monkeypatch)
    monkeypatch.setattr(server, "_resolve_credentials_path", lambda _: "/tmp/credentials.json")
    monkeypatch.setattr(server, "_load_oauth_client_config", lambda _: {"web": {"client_id": "x"}})
    client = TestClient(server.app)

    response = client.get("/api/auth/google/start", follow_redirects=False)

    assert response.status_code == 302
    query = _query(response.headers["location"])
    oauth_state = query["state"][0]
    state_payload = server.verify_state(oauth_state)
    assert state_payload.get("pkce_code_verifier")
    assert fake_flow_cls.last_instance is not None
    assert fake_flow_cls.last_instance.code_verifier == state_payload["pkce_code_verifier"]


def test_google_callback_uses_pkce_verifier_from_state(monkeypatch):
    fake_flow_cls = _install_fake_google_flow(monkeypatch)
    monkeypatch.setattr(server, "_resolve_credentials_path", lambda _: "/tmp/credentials.json")
    monkeypatch.setattr(server, "_load_oauth_client_config", lambda _: {"web": {"client_id": "x"}})
    monkeypatch.setattr(server, "create_session_id", lambda: "sid-123")
    monkeypatch.setattr(server, "sign_session_cookie", lambda session_id: f"signed-{session_id}")
    saved: dict[str, object] = {}
    monkeypatch.setattr(server, "save_session_payload", lambda session_id, payload: saved.update({"id": session_id, "payload": payload}))

    state = server.create_state(next_path="/", pkce_code_verifier="verifier-abc")
    client = TestClient(server.app)

    response = client.get(f"/api/auth/google/callback?state={state}&code=code-123", follow_redirects=False)

    assert response.status_code == 302
    assert fake_flow_cls.last_instance is not None
    assert fake_flow_cls.last_instance.fetch_kwargs.get("code_verifier") == "verifier-abc"
    assert saved["id"] == "sid-123"
    assert saved["payload"] == {
        "provider": "gmail",
        "token_json": {"access_token": "token-1", "refresh_token": "refresh-1"},
    }
