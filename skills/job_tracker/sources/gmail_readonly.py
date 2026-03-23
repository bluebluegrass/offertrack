"""Gmail read-only source adapter."""

from __future__ import annotations

import base64
import email.utils
import html
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def safe_email(email: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", email)


def _build_query(start_date: date, end_date: date) -> str:
    day_after = end_date + timedelta(days=1)
    return f"after:{start_date.strftime('%Y/%m/%d')} before:{day_after.strftime('%Y/%m/%d')}"


def _quote_token(token: str) -> str:
    return f"\"{token}\"" if " " in token else token


def _strict_query_suffix() -> str:
    application_subject_keywords = [
        "application",
        "applying",
        "thanks for applying",
        "interview",
        "availability",
        "schedule",
        "next steps",
        "hiring manager",
        "phone screen",
        "assessment",
        "hackerrank",
        "codility",
        "take-home",
        "offer",
        "not moving forward",
        "regret to inform",
        "rejected",
    ]
    rejection_anywhere_keywords = [
        "candidate rejection",
        "journey has come to an end",
        "application has come to an end",
    ]
    exclude_subject_keywords = [
        "newsletter",
        "digest",
        "invoice",
        "receipt",
        "statement",
        "reservation confirmation",
        "payment",
        "security alert",
    ]
    exclude_domains = ["substack.com", "medium.com", "airbnb.com"]

    include_subject = [f"subject:{_quote_token(k)}" for k in application_subject_keywords]
    include_anywhere = [_quote_token(k) for k in rejection_anywhere_keywords]
    include_any = " OR ".join(include_subject + include_anywhere)
    exclude_subject = " ".join(f"-subject:{_quote_token(k)}" for k in exclude_subject_keywords)
    exclude_from = " ".join(f"-from:{d}" for d in exclude_domains)
    special = (
        "(-from:linkedin.com OR subject:application OR subject:interview) "
        "(-from:bizreach.co.jp OR subject:application OR subject:interview)"
    )
    return f"({include_any}) {exclude_subject} {exclude_from} {special}"


def _header_map(headers: list[dict[str, str]]) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for header in headers:
        mapped[header.get("name", "").lower()] = header.get("value", "")
    return mapped


def _parse_header_date(raw: str) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    parsed = email.utils.parsedate_to_datetime(raw)
    if parsed is None:
        return datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _internal_ms_to_datetime(raw: str | int | None, fallback: datetime) -> datetime:
    if raw is None:
        return fallback
    try:
        ms = int(raw)
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    except (TypeError, ValueError):
        return fallback


def _decode_b64url(data: str) -> str:
    if not data:
        return ""
    padded = data + ("=" * ((4 - (len(data) % 4)) % 4))
    try:
        return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
        return ""


def _strip_html(text: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(no_tags)).strip()


def _extract_body_text(payload: dict[str, Any]) -> str:
    mime = str(payload.get("mimeType", "")).lower()
    body_data = str(payload.get("body", {}).get("data", ""))
    parts = payload.get("parts", []) or []

    if mime.startswith("text/plain"):
        return _decode_b64url(body_data).strip()
    if mime.startswith("text/html"):
        return _strip_html(_decode_b64url(body_data))

    plain_candidates: list[str] = []
    html_candidates: list[str] = []
    for p in parts:
        if not isinstance(p, dict):
            continue
        extracted = _extract_body_text(p)
        p_mime = str(p.get("mimeType", "")).lower()
        if not extracted:
            continue
        if p_mime.startswith("text/plain"):
            plain_candidates.append(extracted)
        elif p_mime.startswith("text/html"):
            html_candidates.append(extracted)
        else:
            plain_candidates.append(extracted)

    if plain_candidates:
        return "\n".join(plain_candidates).strip()
    if html_candidates:
        return "\n".join(html_candidates).strip()
    return _decode_b64url(body_data).strip()


def _load_gmail_service(credentials_path: Path, token_path: Path, *, allow_interactive_auth: bool) -> Any:
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError("Missing Google API dependencies. Install requirements.txt") from exc

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif allow_interactive_auth:
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            try:
                creds = flow.run_local_server(port=0)
            except (PermissionError, OSError):
                # Fallback for restricted environments where localhost bind is blocked.
                creds = flow.run_console()
        else:
            raise RuntimeError("Gmail token missing/expired. Reconnect Gmail to continue.")
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return build("gmail", "v1", credentials=creds)


def fetch_messages(
    *,
    email: str | None,
    start_date: date,
    end_date: date,
    credentials_path: str,
    token_dir: str,
    max_messages: int = 2000,
    gmail_query_mode: str = "strict",
    include_body: bool = False,
    allow_interactive_auth: bool = True,
) -> list[dict[str, Any]]:
    credentials = Path(credentials_path).expanduser().resolve()
    if not credentials.exists():
        raise RuntimeError(f"Credentials file not found: {credentials}")

    token_candidate = Path(token_dir).expanduser()
    if token_candidate.is_file():
        token_path = token_candidate.resolve()
    else:
        email_part = safe_email(email or "me")
        token_path = token_candidate.resolve() / f"gmail_token_{email_part}.json"
        if not email and Path("token.json").exists():
            token_path = Path("token.json").resolve()
        elif not email and token_candidate.exists():
            existing = sorted(token_candidate.glob("gmail_token_*.json"))
            if existing:
                token_path = existing[0].resolve()
    service = _load_gmail_service(credentials, token_path, allow_interactive_auth=allow_interactive_auth)
    date_query = _build_query(start_date, end_date)
    if gmail_query_mode == "strict":
        query = f"{date_query} {_strict_query_suffix()}".strip()
    else:
        query = date_query
    print(f"Gmail query ({gmail_query_mode}): {query}", flush=True)

    out: list[dict[str, Any]] = []
    page_token = None

    while len(out) < max_messages:
        batch_size = min(500, max_messages - len(out))
        response = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=batch_size, pageToken=page_token)
            .execute()
        )

        stubs = response.get("messages", [])
        if not stubs:
            break

        for stub in stubs:
            if include_body:
                raw = (
                    service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=stub["id"],
                        format="full",
                    )
                    .execute()
                )
            else:
                raw = (
                    service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=stub["id"],
                        format="metadata",
                        metadataHeaders=["From", "To", "Subject", "Date"],
                    )
                    .execute()
                )
            headers = _header_map(raw.get("payload", {}).get("headers", []))
            header_date = _parse_header_date(headers.get("date", ""))
            occurred = _internal_ms_to_datetime(raw.get("internalDate"), header_date)
            body = _extract_body_text(raw.get("payload", {})) if include_body else ""
            if len(body) > 20000:
                body = body[:20000]

            out.append(
                {
                    "id": str(raw.get("id", "")),
                    "thread_id": str(raw.get("threadId", raw.get("id", ""))),
                    "date": occurred,
                    "from_email": headers.get("from", ""),
                    "subject": headers.get("subject", ""),
                    "snippet": raw.get("snippet", ""),
                    "body": body,
                }
            )
            if len(out) >= max_messages:
                break

        print(f"Fetched {len(out)}/{max_messages} message metadata...", flush=True)
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return out
