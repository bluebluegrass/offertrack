"""OfferTracker API server."""

from __future__ import annotations

import base64
import binascii
import csv
import io
import json
import os
import secrets
import shutil
import tempfile
import time
from pathlib import Path
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from api.auth_session import (
    COOKIE_NAME,
    SESSION_TTL_SECONDS,
    create_session_id,
    create_state,
    delete_session_payload,
    load_session_payload,
    save_session_payload,
    sign_session_cookie,
    verify_session_cookie,
    verify_state,
)
from skills.job_tracker.pipeline import run
from skills.job_tracker.sources.gmail_readonly import SCOPES, fetch_messages as fetch_gmail_messages
from skills.job_tracker.sources.outlook_graph import fetch_messages as fetch_outlook_messages

SUPPORTED_MAIL_PROVIDERS = {"gmail", "outlook"}
OUTLOOK_SCOPES = ["openid", "profile", "email", "offline_access", "Mail.Read"]


class ScanRequest(BaseModel):
    start_date: str
    end_date: str
    title: str = "Job Search Summary"
    email: str = ""
    credentials_path: str = "credentials.json"
    scan_mode: Literal["fast", "enhanced"] = "fast"
    max_messages: int | None = None


class ScanCompareRequest(BaseModel):
    start_date: str
    end_date: str
    title: str = "Job Search Summary"
    email: str = ""
    credentials_path: str = "credentials.json"
    max_messages: int | None = None


class ExportFixtureRequest(BaseModel):
    start_date: str
    end_date: str
    email: str = ""
    credentials_path: str = "credentials.json"
    max_messages: int | None = None


app = FastAPI(title="OfferTracker API", version="0.2.0")

allowed_origins_raw = os.getenv("ALLOWED_ORIGINS", "*").strip()
if allowed_origins_raw == "*" or not allowed_origins_raw:
    allowed_origins = ["*"]
else:
    allowed_origins = [item.strip() for item in allowed_origins_raw.split(",") if item.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _read_png_data_url(path: Path) -> str:
    if not path.exists():
        return ""
    raw = path.read_bytes()
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _normalize_compare_text(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _read_summary_for_mode(transient_out: Path, *, ai_mode: bool) -> dict[str, int]:
    if ai_mode:
        payload = _read_json(transient_out / "ai_result_summary.json")
        return {
            "applications": int(payload.get("applications", 0)),
            "interviews": int(payload.get("interviews", 0)),
            "rejections_total": int(payload.get("rejections_total", 0)),
            "offers": int(payload.get("offers", 0)),
            "no_response": int(payload.get("no_response", 0)),
        }

    payload = _read_json(transient_out / "metrics.json")
    metrics = payload.get("metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}
    return {
        "applications": int(metrics.get("applications", 0)),
        "interviews": int(metrics.get("interviews", 0)),
        "rejections_total": int(metrics.get("rejected", 0)),
        "offers": int(metrics.get("offers", 0)),
        "no_response": int(metrics.get("no_replies", 0)),
    }


def _read_application_rows_for_mode(transient_out: Path, *, ai_mode: bool) -> list[dict[str, str]]:
    if ai_mode:
        rows = _read_csv_rows(transient_out / "ai_application_table.csv")
        return [
            {
                "company": r.get("company", ""),
                "position": r.get("position", ""),
                "current_status": r.get("current_status", ""),
                "evidence_subject": r.get("evidence_subject", ""),
            }
            for r in rows
        ]

    rows = _read_csv_rows(transient_out / "application_summary.csv")
    return [
        {
            "company": r.get("company_name", ""),
            "position": r.get("role_title", ""),
            "current_status": r.get("current_status", ""),
            "evidence_subject": r.get("evidence_subject", ""),
        }
        for r in rows
    ]


def _build_application_index(rows: list[dict[str, str]]) -> dict[tuple[str, str], dict[str, str]]:
    index: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        key = (_normalize_compare_text(row.get("company", "")), _normalize_compare_text(row.get("position", "")))
        index[key] = row
    return index


def _compare_application_rows(
    fast_rows: list[dict[str, str]],
    enhanced_rows: list[dict[str, str]],
) -> dict[str, object]:
    fast_index = _build_application_index(fast_rows)
    enhanced_index = _build_application_index(enhanced_rows)

    missing_in_fast: list[dict[str, str]] = []
    extra_in_fast: list[dict[str, str]] = []
    status_changed: list[dict[str, str]] = []

    for key, enhanced_row in enhanced_index.items():
        fast_row = fast_index.get(key)
        if fast_row is None:
            missing_in_fast.append(
                {
                    "company": enhanced_row.get("company", ""),
                    "position": enhanced_row.get("position", ""),
                    "enhanced_status": enhanced_row.get("current_status", ""),
                }
            )
            continue
        if _normalize_compare_text(fast_row.get("current_status", "")) != _normalize_compare_text(
            enhanced_row.get("current_status", "")
        ):
            status_changed.append(
                {
                    "company": enhanced_row.get("company", ""),
                    "position": enhanced_row.get("position", ""),
                    "fast_status": fast_row.get("current_status", ""),
                    "enhanced_status": enhanced_row.get("current_status", ""),
                }
            )

    for key, fast_row in fast_index.items():
        if key in enhanced_index:
            continue
        extra_in_fast.append(
            {
                "company": fast_row.get("company", ""),
                "position": fast_row.get("position", ""),
                "fast_status": fast_row.get("current_status", ""),
            }
        )

    return {
        "fast_count": len(fast_rows),
        "enhanced_count": len(enhanced_rows),
        "missing_in_fast": missing_in_fast,
        "extra_in_fast": extra_in_fast,
        "status_changed": status_changed,
    }


def _build_summary_diff(fast_summary: dict[str, int], enhanced_summary: dict[str, int]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for key in ("applications", "interviews", "rejections_total", "offers", "no_response"):
        fast_value = int(fast_summary.get(key, 0))
        enhanced_value = int(enhanced_summary.get(key, 0))
        out[key] = {
            "fast": fast_value,
            "enhanced": enhanced_value,
            "delta": fast_value - enhanced_value,
        }
    return out


def _run_scan_mode(
    *,
    payload: ScanRequest,
    provider: str,
    session_id: str,
    session_payload: dict[str, object],
    request: Request,
    scan_mode: Literal["fast", "enhanced"],
) -> tuple[dict[str, object], dict[str, object]]:
    token_json = session_payload.get("token_json")
    if not token_json:
        raise HTTPException(status_code=401, detail=f"{_provider_label(provider)} session token is missing. Reconnect.")

    runtime_base = (
        os.getenv("OFFERTRACK_RUNTIME_DIR", "").strip()
        or os.getenv("GMAIL_RUNTIME_DIR", "").strip()
        or "/tmp/offertracker_runtime"
    )
    runtime_root = Path(runtime_base).expanduser().resolve() / session_id
    token_dir = runtime_root / "tokens"
    token_dir.mkdir(parents=True, exist_ok=True)
    token_filename = "outlook_token_session.json" if provider == "outlook" else "gmail_token_session.json"
    token_path = token_dir / token_filename
    token_path.write_text(json.dumps(token_json), encoding="utf-8")
    transient_out = Path(tempfile.mkdtemp(prefix=f"scan_{scan_mode}_", dir=str(runtime_root)))
    ai_classify = scan_mode == "enhanced"
    resolved_max_messages = payload.max_messages if payload.max_messages is not None else 300

    try:
        run_kwargs: dict[str, object] = {
            "source": provider,
            "start": payload.start_date,
            "end": payload.end_date,
            "email": None,
            "out_dir": str(transient_out),
            "title": payload.title,
            "ai_classify": ai_classify,
            "max_messages": resolved_max_messages,
            "token_dir": str(token_path),
            "relevant_emails_path": str(transient_out / "relevant_emails.csv"),
            "ai_message_classification_path": str(transient_out / "ai_message_classification.csv"),
            "ai_application_table_path": str(transient_out / "ai_application_table.csv"),
            "ai_result_summary_path": str(transient_out / "ai_result_summary.json"),
            "ai_sankey_path": str(transient_out / "ai_sankey.png"),
            "allow_interactive_auth": False,
        }
        if provider == "gmail":
            run_kwargs["credentials_path"] = _resolve_credentials_path(payload.credentials_path)
        run(**run_kwargs)
        result_payload = {
            "summary": _read_summary_for_mode(transient_out, ai_mode=ai_classify),
            "application_rows": _read_application_rows_for_mode(transient_out, ai_mode=ai_classify),
            "message_rows": _read_csv_rows(transient_out / "ai_message_classification.csv") if ai_classify else [],
        }
        meta = {
            "scan_mode": scan_mode,
            "max_messages": resolved_max_messages,
            "artifacts_dir": str(transient_out),
        }
        return result_payload, meta
    finally:
        try:
            if token_path.exists():
                refreshed = json.loads(token_path.read_text(encoding="utf-8"))
                updated_payload = dict(session_payload)
                updated_payload["token_json"] = refreshed
                save_session_payload(session_id, updated_payload)
        except Exception:  # noqa: BLE001
            pass
        token_path.unlink(missing_ok=True)


def _export_fixture_rows(
    *,
    payload: ExportFixtureRequest,
    provider: str,
    session_id: str,
    session_payload: dict[str, object],
) -> tuple[list[dict[str, object]], int]:
    token_json = session_payload.get("token_json")
    if not token_json:
        raise HTTPException(status_code=401, detail=f"{_provider_label(provider)} session token is missing. Reconnect.")

    runtime_base = (
        os.getenv("OFFERTRACK_RUNTIME_DIR", "").strip()
        or os.getenv("GMAIL_RUNTIME_DIR", "").strip()
        or "/tmp/offertracker_runtime"
    )
    runtime_root = Path(runtime_base).expanduser().resolve() / session_id
    token_dir = runtime_root / "tokens"
    token_dir.mkdir(parents=True, exist_ok=True)
    token_filename = "outlook_token_session.json" if provider == "outlook" else "gmail_token_session.json"
    token_path = token_dir / token_filename
    token_path.write_text(json.dumps(token_json), encoding="utf-8")
    resolved_max_messages = payload.max_messages if payload.max_messages is not None else 300

    try:
        fetch_kwargs: dict[str, object] = {
            "email": payload.email or None,
            "start_date": _parse_date(payload.start_date),
            "end_date": _parse_date(payload.end_date),
            "token_dir": str(token_path),
            "max_messages": resolved_max_messages,
            "include_body": True,
        }
        if provider == "gmail":
            fetch_kwargs["credentials_path"] = _resolve_credentials_path(payload.credentials_path)
            fetch_kwargs["allow_interactive_auth"] = False
            fetch_kwargs["max_body_chars"] = 4000
            rows = fetch_gmail_messages(**fetch_kwargs)
        else:
            rows = fetch_outlook_messages(**fetch_kwargs)
        return rows, resolved_max_messages
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        try:
            if token_path.exists():
                refreshed = json.loads(token_path.read_text(encoding="utf-8"))
                updated_payload = dict(session_payload)
                updated_payload["token_json"] = refreshed
                save_session_payload(session_id, updated_payload)
        except Exception:  # noqa: BLE001
            pass
        token_path.unlink(missing_ok=True)
        if token_dir.exists():
            shutil.rmtree(token_dir, ignore_errors=True)
        if runtime_root.exists() and not any(runtime_root.iterdir()):
            runtime_root.rmdir()


def _parse_date(raw: str):
    from datetime import date

    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid ISO date: {raw}") from exc


def _fixture_csv_response(
    *,
    provider: str,
    rows: list[dict[str, object]],
    start_date: str,
    end_date: str,
) -> Response:
    stream = io.StringIO()
    writer = csv.DictWriter(
        stream,
        fieldnames=["id", "thread_id", "date", "from_email", "subject", "snippet", "body"],
    )
    writer.writeheader()
    for row in rows:
        raw_date = row.get("date")
        if hasattr(raw_date, "isoformat"):
            rendered_date = raw_date.isoformat()
        else:
            rendered_date = str(raw_date or "")
        writer.writerow(
            {
                "id": row.get("id", ""),
                "thread_id": row.get("thread_id", ""),
                "date": rendered_date,
                "from_email": row.get("from_email", ""),
                "subject": row.get("subject", ""),
                "snippet": row.get("snippet", ""),
                "body": row.get("body", ""),
            }
        )

    filename = f"{provider}_fixture_{start_date}_{end_date}.csv"
    return Response(
        content=stream.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _resolve_credentials_path(requested_path: str) -> str:
    requested = requested_path.strip() if requested_path else ""
    if requested:
        candidate = Path(requested).expanduser().resolve()
        if candidate.exists():
            return str(candidate)

    env_path = os.getenv("GOOGLE_OAUTH_CREDENTIALS_PATH", "").strip()
    if env_path:
        candidate = Path(env_path).expanduser().resolve()
        if candidate.exists():
            return str(candidate)

    raw_json = os.getenv("GOOGLE_OAUTH_CREDENTIALS_JSON", "").strip()
    raw_b64 = os.getenv("GOOGLE_OAUTH_CREDENTIALS_B64", "").strip()
    if not raw_json and raw_b64:
        try:
            raw_json = base64.b64decode(raw_b64).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError) as exc:
            raise HTTPException(status_code=500, detail="Invalid GOOGLE_OAUTH_CREDENTIALS_B64") from exc

    if raw_json:
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=500, detail="Invalid GOOGLE_OAUTH_CREDENTIALS_JSON") from exc
        if not isinstance(parsed, dict) or ("installed" not in parsed and "web" not in parsed):
            raise HTTPException(
                status_code=500,
                detail="Google credentials JSON must contain 'installed' or 'web'",
            )
        temp_dir = Path(os.getenv("GOOGLE_OAUTH_TMP_DIR", "/tmp/offertracker")).expanduser().resolve()
        temp_dir.mkdir(parents=True, exist_ok=True)
        out = temp_dir / "credentials.json"
        out.write_text(json.dumps(parsed), encoding="utf-8")
        return str(out)

    fallback = Path(requested or "credentials.json").expanduser().resolve()
    return str(fallback)


def _load_oauth_client_config(credentials_path: str) -> dict[str, object]:
    path = Path(credentials_path).expanduser().resolve()
    if not path.exists():
        raise HTTPException(status_code=500, detail=f"Google OAuth credentials missing: {path}")
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="Google OAuth credentials JSON is invalid") from exc
    if "web" not in config:
        raise HTTPException(status_code=500, detail="Google OAuth client must be a web application config")
    return config


def _frontend_base_url() -> str:
    return os.getenv("FRONTEND_BASE_URL", "https://offertracker.simona.life").rstrip("/")


def _frontend_redirect_url(*, auth: str, message: str = "") -> str:
    query = {"auth": auth}
    if message:
        query["message"] = message
    return f"{_frontend_base_url()}/?{urlencode(query)}"


def _google_redirect_uri(request: Request) -> str:
    explicit = os.getenv("GOOGLE_REDIRECT_URI", "").strip()
    if explicit:
        return explicit
    proto = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
    host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc)).split(",")[0].strip()
    return f"{proto}://{host}/api/auth/google/callback"


def _outlook_redirect_uri(request: Request) -> str:
    explicit = os.getenv("MS_REDIRECT_URI", "").strip()
    if explicit:
        return explicit
    proto = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
    host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc)).split(",")[0].strip()
    return f"{proto}://{host}/api/auth/outlook/callback"


def _first_env_value(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def _ms_oauth_config() -> dict[str, str]:
    client_id_keys = ("MS_CLIENT_ID", "MICROSOFT_CLIENT_ID", "AZURE_CLIENT_ID")
    client_secret_keys = (
        "MS_CLIENT_SECRET",
        "MS_CLENT_SECRET",  # backward-compatible typo fallback
        "MICROSOFT_CLIENT_SECRET",
        "AZURE_CLIENT_SECRET",
    )
    tenant_id_keys = ("MS_TENANT_ID", "MICROSOFT_TENANT_ID", "AZURE_TENANT_ID")

    client_id = _first_env_value(*client_id_keys)
    client_secret = _first_env_value(*client_secret_keys)
    tenant_id = _first_env_value(*tenant_id_keys) or "common"
    if not client_id:
        checked = ", ".join(client_id_keys)
        raise HTTPException(status_code=500, detail=f"MS_CLIENT_ID is not configured (checked: {checked})")
    if not client_secret:
        checked = ", ".join(client_secret_keys)
        raise HTTPException(status_code=500, detail=f"MS_CLIENT_SECRET is not configured (checked: {checked})")
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "tenant_id": tenant_id,
    }


def _exchange_outlook_code_for_token(*, code: str, redirect_uri: str) -> dict[str, object]:
    cfg = _ms_oauth_config()
    token_url = f"https://login.microsoftonline.com/{cfg['tenant_id']}/oauth2/v2.0/token"
    body = urlencode(
        {
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "scope": " ".join(OUTLOOK_SCOPES),
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
            token_payload = json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        detail = raw[:300] if raw else str(exc)
        raise HTTPException(status_code=502, detail=f"Outlook token exchange failed: {detail}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail=f"Outlook token exchange failed: {exc}") from exc

    if not isinstance(token_payload, dict) or not token_payload.get("access_token"):
        raise HTTPException(status_code=502, detail="Outlook token response is missing access_token")
    return token_payload


def _is_cookie_secure(request: Request) -> bool:
    configured = os.getenv("COOKIE_SECURE", "").strip().lower()
    if configured in {"true", "1", "yes"}:
        return True
    if configured in {"false", "0", "no"}:
        return False
    proto = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip().lower()
    return proto == "https"


def _session_from_request(request: Request) -> tuple[str, dict[str, object]] | None:
    raw = request.cookies.get(COOKIE_NAME, "")
    session_id = verify_session_cookie(raw)
    if not session_id:
        return None
    payload = load_session_payload(session_id)
    if not payload:
        return None
    return session_id, payload


def _normalize_provider(raw: object) -> str:
    if isinstance(raw, str):
        value = raw.strip().lower()
        if value in SUPPORTED_MAIL_PROVIDERS:
            return value
    return "gmail"


def _provider_label(provider: str) -> str:
    return "Outlook" if provider == "outlook" else "Gmail"


def _require_session(request: Request) -> tuple[str, dict[str, object]]:
    session = _session_from_request(request)
    if not session:
        raise HTTPException(status_code=401, detail="Mailbox is not connected. Please connect and try again.")
    return session


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/auth/status")
def auth_status(request: Request) -> dict[str, str | bool]:
    session = _session_from_request(request)
    if not session:
        return {"connected": False}
    _session_id, session_payload = session
    provider = _normalize_provider(session_payload.get("provider"))
    return {"connected": True, "provider": provider}


@app.get("/api/auth/google/start")
def auth_google_start(request: Request, next_path: str = Query(default="/")) -> RedirectResponse:
    # Google can require PKCE for web OAuth; keep code_verifier in signed state for callback exchange.
    pkce_code_verifier = secrets.token_urlsafe(64)
    credentials_path = _resolve_credentials_path("credentials.json")
    client_config = _load_oauth_client_config(credentials_path)
    redirect_uri = _google_redirect_uri(request)
    oauth_state = create_state(next_path=next_path, pkce_code_verifier=pkce_code_verifier)

    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail="Missing Google OAuth dependencies") from exc

    flow = Flow.from_client_config(client_config, scopes=SCOPES)
    flow.redirect_uri = redirect_uri
    flow.code_verifier = pkce_code_verifier
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=oauth_state,
    )
    return RedirectResponse(url=auth_url, status_code=302)


@app.get("/api/auth/google/callback")
def auth_google_callback(request: Request) -> RedirectResponse:
    error = request.query_params.get("error", "")
    if error:
        message = request.query_params.get("error_description", error)
        return RedirectResponse(url=_frontend_redirect_url(auth="error", message=message), status_code=302)

    state = request.query_params.get("state", "")
    code = request.query_params.get("code", "")
    if not state or not code:
        return RedirectResponse(
            url=_frontend_redirect_url(auth="error", message="Missing OAuth state or code"),
            status_code=302,
        )

    try:
        state_payload = verify_state(state)
    except ValueError as exc:
        return RedirectResponse(url=_frontend_redirect_url(auth="error", message=str(exc)), status_code=302)

    credentials_path = _resolve_credentials_path("credentials.json")
    client_config = _load_oauth_client_config(credentials_path)
    redirect_uri = _google_redirect_uri(request)

    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail="Missing Google API dependencies") from exc

    try:
        flow = Flow.from_client_config(client_config, scopes=SCOPES, state=state)
        flow.redirect_uri = redirect_uri
        pkce_code_verifier = state_payload.get("pkce_code_verifier", "")
        fetch_kwargs = {"code": code}
        if isinstance(pkce_code_verifier, str) and pkce_code_verifier:
            flow.code_verifier = pkce_code_verifier
            fetch_kwargs["code_verifier"] = pkce_code_verifier
        flow.fetch_token(**fetch_kwargs)
        creds = flow.credentials
        token_payload = json.loads(creds.to_json())
    except Exception as exc:  # noqa: BLE001
        return RedirectResponse(url=_frontend_redirect_url(auth="error", message=str(exc)), status_code=302)

    session_id = create_session_id()
    save_session_payload(
        session_id,
        {
            "provider": "gmail",
            "token_json": token_payload,
        },
    )

    response = RedirectResponse(url=_frontend_redirect_url(auth="success"), status_code=302)
    response.set_cookie(
        key=COOKIE_NAME,
        value=sign_session_cookie(session_id),
        httponly=True,
        secure=_is_cookie_secure(request),
        samesite="lax",
        max_age=SESSION_TTL_SECONDS,
        path="/",
    )
    return response


@app.get("/api/auth/outlook/start")
def auth_outlook_start(request: Request, next_path: str = Query(default="/")) -> RedirectResponse:
    cfg = _ms_oauth_config()
    redirect_uri = _outlook_redirect_uri(request)
    oauth_state = create_state(next_path=next_path)
    query = urlencode(
        {
            "client_id": cfg["client_id"],
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "response_mode": "query",
            "scope": " ".join(OUTLOOK_SCOPES),
            "state": oauth_state,
            "prompt": "select_account",
        }
    )
    auth_url = f"https://login.microsoftonline.com/{cfg['tenant_id']}/oauth2/v2.0/authorize?{query}"
    return RedirectResponse(url=auth_url, status_code=302)


@app.get("/api/auth/outlook/callback")
def auth_outlook_callback(request: Request) -> RedirectResponse:
    error = request.query_params.get("error", "")
    if error:
        message = request.query_params.get("error_description", error)
        return RedirectResponse(url=_frontend_redirect_url(auth="error", message=message), status_code=302)

    state = request.query_params.get("state", "")
    code = request.query_params.get("code", "")
    if not state or not code:
        return RedirectResponse(
            url=_frontend_redirect_url(auth="error", message="Missing OAuth state or code"),
            status_code=302,
        )
    try:
        verify_state(state)
    except ValueError as exc:
        return RedirectResponse(url=_frontend_redirect_url(auth="error", message=str(exc)), status_code=302)

    redirect_uri = _outlook_redirect_uri(request)
    try:
        token_payload = _exchange_outlook_code_for_token(code=code, redirect_uri=redirect_uri)
    except HTTPException as exc:
        return RedirectResponse(url=_frontend_redirect_url(auth="error", message=str(exc.detail)), status_code=302)

    session_id = create_session_id()
    save_session_payload(
        session_id,
        {
            "provider": "outlook",
            "token_json": token_payload,
        },
    )

    response = RedirectResponse(url=_frontend_redirect_url(auth="success"), status_code=302)
    response.set_cookie(
        key=COOKIE_NAME,
        value=sign_session_cookie(session_id),
        httponly=True,
        secure=_is_cookie_secure(request),
        samesite="lax",
        max_age=SESSION_TTL_SECONDS,
        path="/",
    )
    return response


@app.post("/api/auth/logout")
def auth_logout(request: Request) -> JSONResponse:
    session_cookie = request.cookies.get(COOKIE_NAME, "")
    session_id = verify_session_cookie(session_cookie)
    if session_id:
        delete_session_payload(session_id)
    response = JSONResponse({"ok": True})
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return response


@app.post("/api/scan")
def run_scan(payload: ScanRequest, request: Request) -> dict[str, object]:
    request_started = time.monotonic()
    pipeline_started = time.monotonic()
    session_id, session_payload = _require_session(request)

    if not payload.start_date or not payload.end_date:
        raise HTTPException(status_code=400, detail="start_date and end_date are required")

    provider = _normalize_provider(session_payload.get("provider"))
    scan_mode = payload.scan_mode

    try:
        scan_result, scan_meta = _run_scan_mode(
            payload=payload,
            provider=provider,
            session_id=session_id,
            session_payload=session_payload,
            request=request,
            scan_mode=scan_mode,
        )
        pipeline_ms = int((time.monotonic() - pipeline_started) * 1000)
        print(
            "[SCAN PIPELINE] "
            f"provider={provider} scan_mode={scan_mode} max_messages={scan_meta['max_messages']} "
            f"date_range={payload.start_date}..{payload.end_date} pipeline_ms={pipeline_ms}",
            flush=True,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        artifacts_dir = Path(scan_meta["artifacts_dir"]) if "scan_meta" in locals() else None
        if artifacts_dir is not None:
            runtime_root = artifacts_dir.parent
            token_dir = runtime_root / "tokens"
            shutil.rmtree(artifacts_dir, ignore_errors=True)
            if token_dir.exists():
                shutil.rmtree(token_dir, ignore_errors=True)
            if runtime_root.exists() and not any(runtime_root.iterdir()):
                runtime_root.rmdir()

    response_build_ms = int((time.monotonic() - request_started) * 1000)
    print(
        "[SCAN COMPLETE] "
        f"provider={provider} scan_mode={scan_mode} max_messages={scan_meta['max_messages']} "
        f"applications={len(scan_result['application_rows'])} messages={len(scan_result['message_rows'])} total_ms={response_build_ms}",
        flush=True,
    )

    return {
        "ok": True,
        "base_path": "",
        "summary": scan_result["summary"],
        "application_rows": scan_result["application_rows"],
        "message_rows": scan_result["message_rows"],
        "sankey_image_data_url": "",
    }


@app.post("/api/scan/compare")
def compare_scan_modes(payload: ScanCompareRequest, request: Request) -> dict[str, object]:
    print(f"[COMPARE START] POST /api/scan/compare invoked for {payload.start_date} to {payload.end_date}", flush=True)
    session_id, session_payload = _require_session(request)

    if not payload.start_date or not payload.end_date:
        print("[COMPARE ERROR] Missing start_date or end_date", flush=True)
        raise HTTPException(status_code=400, detail="start_date and end_date are required")

    provider = _normalize_provider(session_payload.get("provider"))
    shared_payload = ScanRequest(
        start_date=payload.start_date,
        end_date=payload.end_date,
        title=payload.title,
        email=payload.email,
        credentials_path=payload.credentials_path,
        max_messages=payload.max_messages,
    )

    artifacts_to_cleanup: list[Path] = []
    try:
        fast_result, fast_meta = _run_scan_mode(
            payload=shared_payload,
            provider=provider,
            session_id=session_id,
            session_payload=session_payload,
            request=request,
            scan_mode="fast",
        )
        artifacts_to_cleanup.append(Path(fast_meta["artifacts_dir"]))

        enhanced_result, enhanced_meta = _run_scan_mode(
            payload=shared_payload,
            provider=provider,
            session_id=session_id,
            session_payload=session_payload,
            request=request,
            scan_mode="enhanced",
        )
        artifacts_to_cleanup.append(Path(enhanced_meta["artifacts_dir"]))

        print("[COMPARE SUCCESS] Returning JSON diff payload", flush=True)
        return {
            "ok": True,
            "data": {
                "config": {
                    "provider": provider,
                    "start_date": payload.start_date,
                    "end_date": payload.end_date,
                    "max_messages": fast_meta["max_messages"],
                },
                "fast": fast_result,
                "enhanced": enhanced_result,
                "summary_diff": _build_summary_diff(
                    fast_result["summary"],
                    enhanced_result["summary"],
                ),
                "application_diff": _compare_application_rows(
                    fast_result["application_rows"],
                    enhanced_result["application_rows"],
                ),
            },
        }
    except HTTPException as exc:
        print(f"[COMPARE EXCEPTION] HTTPException {exc.status_code}: {exc.detail}", flush=True)
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"[COMPARE EXCEPTION] Unhandled Exception: {exc}", flush=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        runtime_roots: set[Path] = set()
        for artifacts_dir in artifacts_to_cleanup:
            runtime_roots.add(artifacts_dir.parent)
            shutil.rmtree(artifacts_dir, ignore_errors=True)
        for runtime_root in runtime_roots:
            token_dir = runtime_root / "tokens"
            if token_dir.exists():
                shutil.rmtree(token_dir, ignore_errors=True)
            if runtime_root.exists() and not any(runtime_root.iterdir()):
                runtime_root.rmdir()


@app.post("/api/scan/export-fixture")
def export_scan_fixture(payload: ExportFixtureRequest, request: Request) -> Response:
    session_id, session_payload = _require_session(request)

    if not payload.start_date or not payload.end_date:
        raise HTTPException(status_code=400, detail="start_date and end_date are required")

    provider = _normalize_provider(session_payload.get("provider"))
    rows, _resolved_max_messages = _export_fixture_rows(
        payload=payload,
        provider=provider,
        session_id=session_id,
        session_payload=session_payload,
    )
    return _fixture_csv_response(
        provider=provider,
        rows=rows,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
