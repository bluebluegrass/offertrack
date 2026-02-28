# OfferTracker Migration: Render -> Hetzner VPS + Coolify (Zero-Downtime)

This playbook migrates only the FastAPI API to Coolify on a Hetzner VPS while keeping Render live for rollback.

## Chosen deploy method

Use `Dockerfile` deploy in Coolify for predictable runtime and start behavior.

- Python runtime on Render log: `3.14.3`
- Added local Docker assets:
  - `Dockerfile`
  - `.dockerignore`

## Current API runtime details from repo

- Render build command: `pip install -r requirements.txt`
- Render start command: `uvicorn api.server:app --host 0.0.0.0 --port $PORT`
- FastAPI app target: `api.server:app`
- Health endpoint: `GET /health`

## Migration safety strategy

- Deploy staging first on Coolify.
- Verify staging health and auth callbacks.
- Attach production domain in Coolify before DNS cutover.
- Cut DNS with low TTL.
- Keep Render running unchanged for at least 48 hours.
- Roll back by changing DNS back to Render target.

## Phase 1: Prepare local repo

From your local machine:

```bash
cd /Users/simona/Documents/Job-tracker
git add Dockerfile .dockerignore docs/MIGRATE_RENDER_TO_COOLIFY.md scripts/ops
git commit -m "Add Coolify migration runbook and Docker deploy files"
git push origin main
```

Verification:

```bash
git log -1 --name-only
```

Expected files include `Dockerfile`, `.dockerignore`, `docs/MIGRATE_RENDER_TO_COOLIFY.md`, and `scripts/ops/*`.

## Phase 2: Provision Hetzner VPS (Ubuntu LTS)

Create one server in Hetzner Cloud:

- Image: Ubuntu 24.04 LTS
- Type: CX22 or similar (2 vCPU, 4 GB RAM)
- Volume: default disk is fine to start
- Network: public IPv4 enabled
- SSH key: your local public key
- Name: `offertracker-coolify-01`

After server creation, connect as root:

```bash
ssh root@<VPS_IP>
apt update && apt -y upgrade
reboot
```

Reconnect and harden:

```bash
ssh root@<VPS_IP>
adduser simona
usermod -aG sudo simona
rsync --archive --chown=simona:simona ~/.ssh /home/simona
```

Firewall:

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 8000/tcp
ufw --force enable
ufw status verbose
```

Verification:

```bash
ssh simona@<VPS_IP> 'whoami && sudo -n true && ufw status'
```

Expected:

- user is `simona`
- sudo works
- ports `22`, `80`, `443`, `8000` are allowed

## Phase 3: Install Coolify (official)

Run on VPS:

```bash
ssh simona@<VPS_IP>
curl -fsSL https://cdn.coollabs.io/coolify/install.sh | bash
```

Verification:

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
curl -I http://<VPS_IP>:8000
```

Expected:

- Coolify containers running
- HTTP response from `:8000`

## Phase 4: DNS for staging first

In DNS provider for `simona.life`, create:

- `A` record: `api-staging.offertracker.simona.life` -> `<VPS_IP>`
- TTL: `300` (or lowest available)

Verification from local machine:

```bash
dig +short api-staging.offertracker.simona.life
```

Expected: returns `<VPS_IP>`.

## Phase 5: Configure Coolify app (staging)

In Coolify UI:

1. Add GitHub source and authorize your repo.
2. Create project `offertracker`.
3. Create application from repo branch `main`.
4. Build pack type: `Dockerfile`.
5. Exposed port: `8080`.
6. Domain: `api-staging.offertracker.simona.life`.
7. Health check path: `/health`.

Set environment variables (names match Render):

- `OPENAI_API_KEY`
- `ALLOWED_ORIGINS`
- `GOOGLE_OAUTH_CREDENTIALS_JSON`
- `GOOGLE_REDIRECT_URI`
- `MS_CLIENT_ID`
- `MS_CLIENT_SECRET`
- `MS_TENANT_ID`
- `MS_REDIRECT_URI`
- `FRONTEND_BASE_URL`
- `SESSION_SECRET`
- `TOKEN_ENCRYPTION_KEY`
- `SESSION_STORE_DIR`

Recommended staging values:

- `ALLOWED_ORIGINS=https://offertracker.simona.life`
- `GOOGLE_REDIRECT_URI=https://api-staging.offertracker.simona.life/api/auth/google/callback`
- `MS_REDIRECT_URI=https://api-staging.offertracker.simona.life/api/auth/outlook/callback`
- `FRONTEND_BASE_URL=https://offertracker.simona.life`
- `SESSION_STORE_DIR=/tmp/offertracker_sessions`

Deploy app.

Verification from local machine:

```bash
curl -i https://api-staging.offertracker.simona.life/health
```

Expected: HTTP 200 and `{"status":"ok"}`.

Check logs in Coolify UI and with:

```bash
ssh simona@<VPS_IP> "docker ps --format 'table {{.Names}}\t{{.Status}}'"
```

## Phase 6: Prepare production cutover

Record current Render DNS target before changing anything:

```bash
dig +short api.offertracker.simona.life
dig api.offertracker.simona.life CNAME +short
```

Add production domain in same Coolify app:

- `api.offertracker.simona.life`

Verification before DNS switch:

```bash
curl -i http://<VPS_IP>/health -H 'Host: api.offertracker.simona.life'
```

Expected: app responds with health payload.

## Phase 7: DNS cutover (safe + reversible)

Change DNS record for `api.offertracker.simona.life` to VPS.

- If currently CNAME to Render, replace with `A -> <VPS_IP>`.
- Set TTL to `60` or `300`.

Verification:

```bash
bash scripts/ops/wait_for_dns.sh api.offertracker.simona.life <VPS_IP> 30 10
curl -i https://api.offertracker.simona.life/health
```

Expected:

- DNS resolves to VPS
- HTTPS health returns 200

## Phase 8: 48-hour rollback window

Keep Render service up and unchanged for 48 hours.

Continuous health monitor (local):

```bash
bash scripts/ops/health_loop.sh https://api.offertracker.simona.life/health 60
```

If incident happens, rollback:

1. Restore DNS for `api.offertracker.simona.life` back to previous Render target.
2. Verify:

```bash
curl -i https://api.offertracker.simona.life/health
```

3. Keep Coolify running for diagnostics.

## Required user actions and pause points

Pause and continue only after you complete each:

1. Hetzner server created and SSH working.
2. Coolify installation completed.
3. Staging DNS record created and resolving.
4. Staging env vars set in Coolify.
5. OAuth callback URLs updated for staging (if testing auth flow).
6. Production DNS switched.

## Notes

- There is no database, so rollback is DNS-only.
- Existing sessions can reset during cutover, which is expected.
