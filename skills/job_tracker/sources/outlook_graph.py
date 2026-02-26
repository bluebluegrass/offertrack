"""Outlook (Microsoft Graph) read-only source adapter."""

from __future__ import annotations

import html
import json
import os
import re
import time
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

SCOPES = ["openid", "profile", "email", "offline_access", "Mail.Read"]
GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class GraphAuthError(RuntimeError):
    """Raised when Graph API auth fails and caller may need refresh/reconnect."""


def safe_email(email: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", email)


def _iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _date_bounds(start_date: date, end_date: date) -> tuple[datetime, datetime]:
    start_dt = datetime.combine(start_date, dt_time.min).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date + timedelta(days=1), dt_time.min).replace(tzinfo=timezone.utc)
    return start_dt, end_dt


def _parse_graph_datetime(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    candidate = raw.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _strip_html(text: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(no_tags)).strip()


def _resolve_token_path(token_dir: str, email: str | None) -> Path:
    token_candidate = Path(token_dir).expanduser()
    if token_candidate.is_file():
        return token_candidate.resolve()
    email_part = safe_email(email or "me")
    return (token_candidate / f"outlook_token_{email_part}.json").resolve()


def _load_token_payload(token_path: Path) -> dict[str, Any]:
    if not token_path.exists():
        raise RuntimeError("Outlook token missing. Reconnect Outlook to continue.")
    try:
        payload = json.loads(token_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid Outlook token JSON: {token_path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Invalid Outlook token payload: {token_path}")
    return payload


def _token_expired(token_payload: dict[str, Any], *, skew_seconds: int = 60) -> bool:
    now = int(time.time())
    expires_at = int(token_payload.get("expires_at", 0) or 0)
    if expires_at > 0:
        return now >= max(expires_at - skew_seconds, 0)

    expires_in = int(token_payload.get("expires_in", 0) or 0)
    obtained_at = int(token_payload.get("obtained_at", 0) or 0)
    if expires_in > 0 and obtained_at > 0:
        return now >= max((obtained_at + expires_in) - skew_seconds, 0)
    return False


def _first_env_value(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def _ms_oauth_config() -> dict[str, str]:
    client_id = _first_env_value("MS_CLIENT_ID", "MICROSOFT_CLIENT_ID", "AZURE_CLIENT_ID")
    client_secret = _first_env_value(
        "MS_CLIENT_SECRET",
        "MS_CLENT_SECRET",  # backward-compatible typo fallback
        "MICROSOFT_CLIENT_SECRET",
        "AZURE_CLIENT_SECRET",
    )
    tenant_id = _first_env_value("MS_TENANT_ID", "MICROSOFT_TENANT_ID", "AZURE_TENANT_ID") or "common"
    if not client_id or not client_secret:
        raise RuntimeError(
            "MS_CLIENT_ID and MS_CLIENT_SECRET are required to refresh Outlook tokens. "
            "Accepted aliases include MICROSOFT_CLIENT_ID/AZURE_CLIENT_ID and "
            "MICROSOFT_CLIENT_SECRET/AZURE_CLIENT_SECRET."
        )
    return {"client_id": client_id, "client_secret": client_secret, "tenant_id": tenant_id}


def _refresh_access_token(token_payload: dict[str, Any]) -> dict[str, Any]:
    refresh_token = str(token_payload.get("refresh_token", "")).strip()
    if not refresh_token:
        raise RuntimeError("Outlook token expired and refresh_token is missing. Reconnect Outlook.")

    cfg = _ms_oauth_config()
    token_url = f"https://login.microsoftonline.com/{cfg['tenant_id']}/oauth2/v2.0/token"
    body = urlencode(
        {
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": " ".join(SCOPES),
        }
    ).encode("utf-8")
    req = UrlRequest(
        token_url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=20) as resp:
            refreshed = json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        detail = raw[:300] if raw else str(exc)
        raise RuntimeError(f"Outlook token refresh failed: {detail}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Outlook token refresh failed: {exc}") from exc

    if not isinstance(refreshed, dict) or not refreshed.get("access_token"):
        raise RuntimeError("Outlook token refresh response is missing access_token.")

    now = int(time.time())
    merged = dict(token_payload)
    merged.update(refreshed)
    merged["obtained_at"] = now
    expires_in = int(merged.get("expires_in", 0) or 0)
    if expires_in > 0:
        merged["expires_at"] = now + expires_in
    return merged


def _graph_get_json(url: str, access_token: str) -> dict[str, Any]:
    req = UrlRequest(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        if exc.code in {401, 403}:
            raise GraphAuthError(raw or str(exc)) from exc
        raise RuntimeError(f"Graph request failed ({exc.code}): {raw[:300]}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Graph request failed: {exc}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError("Graph response is not a JSON object")
    return payload


def _build_messages_url(*, start_dt: datetime, end_dt: datetime, include_body: bool, page_size: int) -> str:
    select_fields = [
        "id",
        "conversationId",
        "receivedDateTime",
        "from",
        "subject",
        "bodyPreview",
    ]
    if include_body:
        select_fields.append("body")
    filter_expr = (
        f"receivedDateTime ge {_iso_utc(start_dt)} and "
        f"receivedDateTime lt {_iso_utc(end_dt)}"
    )
    query = urlencode(
        {
            "$select": ",".join(select_fields),
            "$top": str(page_size),
            "$orderby": "receivedDateTime desc",
            "$filter": filter_expr,
        }
    )
    return f"{GRAPH_BASE}/me/messages?{query}"


def _extract_from_email(raw: dict[str, Any]) -> str:
    from_block = raw.get("from")
    if not isinstance(from_block, dict):
        return ""
    email_block = from_block.get("emailAddress")
    if not isinstance(email_block, dict):
        return ""
    return str(email_block.get("address", ""))


def _extract_body(raw: dict[str, Any]) -> str:
    body_block = raw.get("body")
    if not isinstance(body_block, dict):
        return ""
    content = str(body_block.get("content", ""))
    content_type = str(body_block.get("contentType", "")).lower()
    if content_type == "html":
        return _strip_html(content)
    return content.strip()


def _normalize_message_row(raw: dict[str, Any], *, include_body: bool) -> dict[str, Any]:
    body = _extract_body(raw) if include_body else ""
    if len(body) > 20000:
        body = body[:20000]
    return {
        "id": str(raw.get("id", "")),
        "thread_id": str(raw.get("conversationId", raw.get("id", ""))),
        "date": _parse_graph_datetime(str(raw.get("receivedDateTime", ""))),
        "from_email": _extract_from_email(raw),
        "subject": str(raw.get("subject", "")),
        "snippet": str(raw.get("bodyPreview", "")),
        "body": body,
    }


def _fetch_graph_messages(
    *,
    access_token: str,
    start_dt: datetime,
    end_dt: datetime,
    include_body: bool,
    max_messages: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    next_url = _build_messages_url(start_dt=start_dt, end_dt=end_dt, include_body=include_body, page_size=min(200, max_messages))

    while next_url and len(out) < max_messages:
        payload = _graph_get_json(next_url, access_token)
        items = payload.get("value", [])
        if not isinstance(items, list):
            raise RuntimeError("Graph response missing message list")

        for item in items:
            if not isinstance(item, dict):
                continue
            out.append(_normalize_message_row(item, include_body=include_body))
            if len(out) >= max_messages:
                break

        next_candidate = payload.get("@odata.nextLink", "")
        next_url = str(next_candidate) if next_candidate and len(out) < max_messages else ""
    return out


def fetch_messages(
    *,
    email: str | None,
    start_date: date,
    end_date: date,
    token_dir: str,
    max_messages: int = 2000,
    include_body: bool = False,
) -> list[dict[str, Any]]:
    if max_messages <= 0:
        return []

    token_path = _resolve_token_path(token_dir, email)
    token_payload = _load_token_payload(token_path)
    access_token = str(token_payload.get("access_token", "")).strip()

    if not access_token:
        raise RuntimeError("Outlook access_token is missing. Reconnect Outlook to continue.")

    if _token_expired(token_payload):
        token_payload = _refresh_access_token(token_payload)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(json.dumps(token_payload), encoding="utf-8")
        access_token = str(token_payload.get("access_token", "")).strip()

    start_dt, end_dt = _date_bounds(start_date, end_date)

    try:
        rows = _fetch_graph_messages(
            access_token=access_token,
            start_dt=start_dt,
            end_dt=end_dt,
            include_body=include_body,
            max_messages=max_messages,
        )
    except GraphAuthError:
        token_payload = _refresh_access_token(token_payload)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(json.dumps(token_payload), encoding="utf-8")
        rows = _fetch_graph_messages(
            access_token=str(token_payload.get("access_token", "")),
            start_dt=start_dt,
            end_dt=end_dt,
            include_body=include_body,
            max_messages=max_messages,
        )

    rows.sort(key=lambda r: r["date"])
    return rows
