# OfferTrack
A Gmail/Outlook-powered web app for tracking your job application funnel and visualizing outcomes.

## What This Does
OfferTrack helps you understand your job search progress by:

- Connecting to Gmail or Outlook with read-only access
- Scanning a selected date range
- Classifying job-search email events
- Generating summary metrics and a Sankey funnel chart
- Showing application and message-level tables in the UI

## Key Features
- **Read-Only OAuth Access** - Gmail (`gmail.readonly`) and Outlook (`Mail.Read`)
- **Web App Architecture** - FastAPI backend + React/Vite frontend
- **AI Classification Pipeline** - Converts email signals into structured outcomes
- **Sankey Visualization** - Clear funnel view from application to offer/rejection
- **Production Deployment Support** - Render blueprint included
- **Automated Test Coverage** - Python tests for metrics and classification modules

## Installation
Install Python dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Install frontend dependencies:

```bash
cd frontend
npm ci
cd ..
```

## Configuration
Set required backend environment variables:

- `OPENAI_API_KEY`
- `SESSION_SECRET`
- `TOKEN_ENCRYPTION_KEY`

Google credentials options:

- local file: `credentials.json`
- env vars: `GOOGLE_OAUTH_CREDENTIALS_JSON` or `GOOGLE_OAUTH_CREDENTIALS_B64`

Common optional vars:

- `ALLOWED_ORIGINS`
- `GOOGLE_REDIRECT_URI`
- `MS_CLIENT_ID`
- `MS_CLIENT_SECRET`
- `MS_TENANT_ID` (default: `common`)
- `MS_REDIRECT_URI`
- `FRONTEND_BASE_URL`
- `SESSION_STORE_DIR`

Outlook env var aliases (supported by backend):

- Client ID: `MS_CLIENT_ID` or `MICROSOFT_CLIENT_ID` or `AZURE_CLIENT_ID`
- Client Secret: `MS_CLIENT_SECRET` or `MS_CLENT_SECRET` or `MICROSOFT_CLIENT_SECRET` or `AZURE_CLIENT_SECRET`
- Tenant: `MS_TENANT_ID` or `MICROSOFT_TENANT_ID` or `AZURE_TENANT_ID`

Outlook OAuth requires a Microsoft Entra app registration with delegated scopes:

- `Mail.Read`
- `offline_access`
- `openid`
- `profile`
- `email`

## Usage
Run backend:

```bash
uvicorn api.server:app --reload
```

Run frontend:

```bash
cd frontend
npm run dev
```

## API
- `GET /health`
- `GET /api/auth/status`
- `GET /api/auth/google/start`
- `GET /api/auth/google/callback`
- `GET /api/auth/outlook/start`
- `GET /api/auth/outlook/callback`
- `POST /api/auth/logout`
- `POST /api/scan`

## Tests
Run from this directory:

```bash
PYTHONPATH=. pytest -q
```

## Files
- `api/` - backend server and auth/session logic
- `frontend/` - React web application
- `skills/job_tracker/` - pipeline and domain logic
- `tests/` - automated tests
- `render.yaml` - Render deployment config
- `DEPLOY_RENDER_GODADDY.md` - deployment/domain notes

## Outlook Troubleshooting
- `invalid_client`: verify `MS_CLIENT_ID`/`MS_CLIENT_SECRET` match the Entra app.
- `MS_CLIENT_ID is not configured`: verify Render env var has a value (not just key name), then redeploy.
- `AADSTS50011` redirect mismatch: confirm `MS_REDIRECT_URI` exactly matches the callback URL configured in Entra.
- `invalid_request` for `redirect_uri`: check hostname/path/scheme exact match (`offertrack` vs `offertracker`, trailing slash differences).
- `consent_required` or blocked scopes: tenant admin consent may be required for `Mail.Read`.
- Expired/invalid refresh token: reconnect Outlook from the app and retry scan.
