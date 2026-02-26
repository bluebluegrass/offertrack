"""Session/state helpers for web OAuth on OfferTracker API."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

COOKIE_NAME = "offertrack_session"
STATE_TTL_SECONDS = 10 * 60
SESSION_TTL_SECONDS = 14 * 24 * 60 * 60


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(raw: str) -> bytes:
    padded = raw + ("=" * ((4 - len(raw) % 4) % 4))
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _secret_bytes() -> bytes:
    return os.getenv("SESSION_SECRET", "dev-session-secret-change-me").encode("utf-8")


def _sign_text(text: str) -> str:
    digest = hmac.new(_secret_bytes(), text.encode("utf-8"), hashlib.sha256).digest()
    return _b64url_encode(digest)


def _verify_text_signature(text: str, sig: str) -> bool:
    expected = _sign_text(text)
    return hmac.compare_digest(expected, sig)


def _fernet() -> Fernet:
    raw = os.getenv("TOKEN_ENCRYPTION_KEY", "").strip()
    if raw:
        try:
            return Fernet(raw.encode("utf-8"))
        except Exception:  # noqa: BLE001
            pass

    derived = hashlib.sha256(_secret_bytes()).digest()
    key = base64.urlsafe_b64encode(derived)
    return Fernet(key)


def create_state(*, next_path: str = "/") -> str:
    payload = {
        "nonce": secrets.token_urlsafe(18),
        "ts": int(time.time()),
        "next_path": next_path if next_path.startswith("/") else "/",
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    body = _b64url_encode(raw)
    sig = _sign_text(body)
    return f"{body}.{sig}"


def verify_state(state: str) -> dict[str, Any]:
    try:
        body, sig = state.split(".", 1)
    except ValueError as exc:
        raise ValueError("Malformed OAuth state") from exc
    if not _verify_text_signature(body, sig):
        raise ValueError("Invalid OAuth state signature")
    try:
        payload = json.loads(_b64url_decode(body).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Invalid OAuth state payload") from exc
    if not isinstance(payload, dict):
        raise ValueError("OAuth state payload must be an object")
    ts = int(payload.get("ts", 0))
    if ts <= 0 or int(time.time()) - ts > STATE_TTL_SECONDS:
        raise ValueError("OAuth state expired")
    return payload


def _session_store_dir() -> Path:
    root = Path(os.getenv("SESSION_STORE_DIR", "/tmp/offertrack_sessions")).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _session_path(session_id: str) -> Path:
    return _session_store_dir() / f"{session_id}.bin"


def create_session_id() -> str:
    return secrets.token_urlsafe(32)


def sign_session_cookie(session_id: str) -> str:
    sig = _sign_text(session_id)
    return f"{session_id}.{sig}"


def verify_session_cookie(cookie_value: str | None) -> str | None:
    if not cookie_value:
        return None
    try:
        session_id, sig = cookie_value.split(".", 1)
    except ValueError:
        return None
    if not session_id or not _verify_text_signature(session_id, sig):
        return None
    return session_id


def save_session_payload(session_id: str, payload: dict[str, Any]) -> None:
    data = dict(payload)
    now = int(time.time())
    data["updated_at"] = now
    data.setdefault("created_at", now)
    raw = json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encrypted = _fernet().encrypt(raw)
    _session_path(session_id).write_bytes(encrypted)


def load_session_payload(session_id: str) -> dict[str, Any] | None:
    path = _session_path(session_id)
    if not path.exists():
        return None
    try:
        decrypted = _fernet().decrypt(path.read_bytes())
        payload = json.loads(decrypted.decode("utf-8"))
    except (InvalidToken, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None

    updated_at = int(payload.get("updated_at", 0))
    if updated_at and int(time.time()) - updated_at > SESSION_TTL_SECONDS:
        delete_session_payload(session_id)
        return None
    return payload


def delete_session_payload(session_id: str) -> None:
    path = _session_path(session_id)
    try:
        path.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        return
