# OfferTracker Deployment (Render + GoDaddy)

This repo is preconfigured for:
- Web app: `offertracker.simona.life`
- API: `api.offertracker.simona.life`

## 1) Push code to GitHub

```bash
git add -A
git commit -m "Prepare Render deployment for simona.life"
git push origin main
```

## 2) Deploy on Render (Blueprint)

1. Open Render dashboard.
2. Create `New +` -> `Blueprint`.
3. Select this GitHub repo.
4. Render reads `render.yaml` and creates:
   - `offertracker-web` (static)
   - `offertracker-api` (python)

## 3) Set Render environment variables

In `offertracker-api` service settings:
- `OPENAI_API_KEY` = your key (set in Render UI only, never in git)
- `ALLOWED_ORIGINS` should be `https://offertracker.simona.life`

`offertracker-web` already has:
- `VITE_API_BASE_URL=https://api.offertracker.simona.life`

## 4) Add custom domains in Render

- In `offertracker-web` -> Custom Domains: add `offertracker.simona.life`
- In `offertracker-api` -> Custom Domains: add `api.offertracker.simona.life`

Render will show target hostnames to use in DNS.

## 5) Configure GoDaddy DNS

In GoDaddy DNS zone for `simona.life`:
- Add CNAME `offertracker` -> Render target for `offertracker-web`
- Add CNAME `api` -> Render target for `offertracker-api`

Wait for DNS propagation.

## 6) Verify

- `https://api.offertracker.simona.life/health` -> `{"status":"ok"}`
- `https://offertracker.simona.life` opens app

## 7) Gmail OAuth note (important)

Current Gmail connect uses installed-app OAuth style.
For stable public deployment, migrate to web OAuth redirect flow in Google Cloud credentials.
