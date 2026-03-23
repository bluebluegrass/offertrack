"""OfferTracker API server."""

from __future__ import annotations

import base64
import binascii
import csv
import json
import os
import secrets
import shutil
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from fastapi import FastAPI, HTTPException, Query, Request
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
from skills.job_tracker.sources.gmail_readonly import SCOPES

SUPPORTED_MAIL_PROVIDERS = {"gmail", "outlook"}
OUTLOOK_SCOPES = ["openid", "profile", "email", "offline_access", "Mail.Read"]


class ScanRequest(BaseModel):
    start_date: str
    end_date: str
    title: str = "Job Search Summary"
    email: str = ""
    credentials_path: str = "credentials.json"


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
    session_id, session_payload = _require_session(request)

    if not payload.start_date or not payload.end_date:
        raise HTTPException(status_code=400, detail="start_date and end_date are required")

    provider = _normalize_provider(session_payload.get("provider"))

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

    transient_out = Path(tempfile.mkdtemp(prefix="scan_", dir=str(runtime_root)))

    try:
        run_kwargs: dict[str, object] = {
            "source": provider,
            "start": payload.start_date,
            "end": payload.end_date,
            "email": None,
            "out_dir": str(transient_out),
            "title": payload.title,
            "ai_classify": True,
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
    except Exception as exc:  # noqa: BLE001
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
    summary = _read_json(transient_out / "ai_result_summary.json")
    application_rows = _read_csv_rows(transient_out / "ai_application_table.csv")
    message_rows = _read_csv_rows(transient_out / "ai_message_classification.csv")
    sankey_image_data_url = _read_png_data_url(transient_out / "ai_sankey.png")

    # Keep scan artifacts transient: remove generated files immediately after response payload is built.
    shutil.rmtree(transient_out, ignore_errors=True)
    if token_dir.exists():
        shutil.rmtree(token_dir, ignore_errors=True)
    if runtime_root.exists() and not any(runtime_root.iterdir()):
        runtime_root.rmdir()

    return {
        "ok": True,
        "base_path": "",
        "summary": summary,
        "application_rows": application_rows,
        "message_rows": message_rows,
        "sankey_image_data_url": sankey_image_data_url,
    }
