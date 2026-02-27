# OfferTrack

OfferTrack is a Gmail-powered job search tracker web app.

## Repository Layout

- `job-application-email-tracker/api/`: FastAPI backend (`/health`, OAuth, scan API)
- `job-application-email-tracker/frontend/`: React + Vite frontend
- `job-application-email-tracker/skills/job_tracker/`: core parsing, classification, and metrics pipeline
- `job-application-email-tracker/tests/`: Python test suite

## Quick Start

```bash
cd job-application-email-tracker
python3 -m pip install -r requirements.txt
cd frontend && npm ci && cd ..
```

Run backend:

```bash
cd job-application-email-tracker
uvicorn api.server:app --reload
```

Run frontend:

```bash
cd job-application-email-tracker/frontend
npm run dev
```

## Tests

Run tests from the app directory:

```bash
cd job-application-email-tracker
PYTHONPATH=. pytest -q
```
