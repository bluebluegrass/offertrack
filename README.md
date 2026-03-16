# OfferTracker

OfferTracker is a job application tracking app that scans a connected mailbox, classifies job-related email, summarizes the pipeline, and helps users decide what to do next for each application.

## What It Does

- Connects Gmail or Outlook with read-only OAuth
- Scans a date range and classifies email into job application events
- Builds per-company application rows with statuses like `Applied`, `Interviewing`, `Rejected`, and `Offer`
- Generates a branded Sankey image for the pipeline summary
- Shows message-level classifications and application-level details in the web UI
- Sorts application details by pipeline priority:
  - `Offer`
  - `Interviewing`
  - `Applied`
  - `Rejected`
- Includes a demo mode in the frontend so the dashboard can be reviewed without rescanning
- Gives each application row its own expandable action card with:
  - next-step actions
  - sender / contact route
  - follow-up draft when direct reply is realistic
  - recruiter / hiring manager / LinkedIn / careers-page search shortcuts

## Recent Frontend Features

- Mobile-first dashboard updates for laptop and phone layouts
- Warmer branded UI based on the OfferTracker logo
- Demo Sankey image shown with fake data
- Expandable details per application row instead of separate global action sections
- Sender-aware follow-up guidance:
  - direct follow-up for replyable senders
  - `Find Contact` for `noreply` / system mailboxes
  - `Check ATS` / recruiter search for ATS platforms

## Repository Layout

- `api/`: FastAPI backend endpoints, including auth and scan APIs
- `app/`: app/server support code
- `frontend/`: React + Vite frontend
- `skills/job_tracker/`: parsing, classification, Sankey rendering, and reporting pipeline
- `tests/`: Python test suite
- `output/`: generated scan artifacts and debug outputs

## Quick Start

Install Python and frontend dependencies from the repo root:

```bash
python3 -m pip install -r requirements.txt
cd frontend && npm ci && cd ..
```

Run the backend:

```bash
uvicorn api.server:app --reload
```

Run the frontend:

```bash
cd frontend
npm run dev
```

Build the frontend:

```bash
cd frontend
npm run build
```

## Frontend Notes

- The dashboard starts with demo data by default so the UI can be tested without scanning
- Running a real scan replaces the demo data with live results from the backend
- The Sankey preview is shown directly in the dashboard
- Each row in `Private: Application Details` can be expanded to show row-specific actions and follow-up guidance

## Testing

Run the Python tests from the repo root:

```bash
PYTHONPATH=. pytest -q
```

Run the frontend production build check:

```bash
cd frontend
npm run build
```

## Notes

- Mail access is read-only
- OfferTracker does not need to store raw mailbox content in the frontend flow
- Some follow-up actions are intentionally stateless right now: the UI helps users act immediately without requiring a database
