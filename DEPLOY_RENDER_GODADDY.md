# OfferTracker Deployment (Render + GoDaddy)

This repo is preconfigured for:
- Web app: `offertrack.simona.life`
- API: `api.offertrack.simona.life`

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
   - `offertrack-web` (static)
   - `offertrack-api` (python)

## 3) Set Render environment variables

In `offertrack-api` service settings:
- `OPENAI_API_KEY` = your key (set in Render UI only, never in git)
- `ALLOWED_ORIGINS` should be `https://offertrack.simona.life`

`offertrack-web` already has:
- `VITE_API_BASE_URL=https://api.offertrack.simona.life`

## 4) Add custom domains in Render

- In `offertrack-web` -> Custom Domains: add `offertrack.simona.life`
- In `offertrack-api` -> Custom Domains: add `api.offertrack.simona.life`

Render will show target hostnames to use in DNS.

## 5) Configure GoDaddy DNS

In GoDaddy DNS zone for `simona.life`:
- Add CNAME `offertrack` -> Render target for `offertrack-web`
- Add CNAME `api` -> Render target for `offertrack-api`

Wait for DNS propagation.

## 6) Verify

- `https://api.offertrack.simona.life/health` -> `{"status":"ok"}`
- `https://offertrack.simona.life` opens app

## 7) Gmail OAuth note (important)

Current Gmail connect uses installed-app OAuth style.
For stable public deployment, migrate to web OAuth redirect flow in Google Cloud credentials.
