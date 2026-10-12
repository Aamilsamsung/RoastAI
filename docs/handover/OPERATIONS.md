# Reproducible setup, backup and transfer

## Local development

Use Python 3.12 and Node 22. In `backend`, create a virtual environment, install `requirements-dev.txt`, and copy `.env.example` to `.env`. Keep ENVIRONMENT=development and SQLite for local work. Generate your own ADMIN_TOKEN; supply Gemini credentials in that file or the process environment. Run `uvicorn app.main:app --host 0.0.0.0 --port 8000`. Migrations run at startup.

In `frontend`, run `npm ci`; create `.env.local` with `NEXT_PUBLIC_API_URL=http://localhost:8000`, then `npm run dev`. Production checks: `npm run build && npm run typecheck`; backend checks: `python -m compileall -q app migrations scripts && python -m pytest -q`. Tests use disposable SQLite, mocked provider/network responses, and no customer messages. Real PostgreSQL test: set TEST_POSTGRES_URL to a disposable test database and run `pytest tests/test_postgres.py -q`. Never point it at production.

## Current Render deployment

Repository: Aamilsamsung/RoastAI, branch main. Existing services were created manually with root directory blank:

| Setting | Backend | Frontend |
|---|---|---|
| Build | `cd backend && pip install -r requirements.txt` | `cd frontend && npm ci && npm run build` |
| Start | `cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1` | `cd frontend && npm start` |
| Health | `/health` | `/` |
| Public origin | https://roastai-backend-ir7y.onrender.com | https://roastai-frontend.onrender.com |

The repo Blueprint instead uses backend/frontend root directories and correspondingly omits `cd`. Do not combine those settings. NEXT_PUBLIC_API_URL must be the backend HTTPS origin at build time. FRONTEND_URL must exactly match the frontend origin. Database and backend are in Oregon. Keep database external IP allowlist closed. Keep one backend instance for this release.

The existing services' configured custom health-check paths were blank during inspection. `/health` exists, and backend `/` now aliases the same health check. Explicitly set `/health` in the backend Dashboard before sale. The available connector cannot modify that service setting; the Blueprint already has it.

Free web services sleep. Their Render-owned wake-up interstitial cannot be replaced by app HTML before the app starts. Free PostgreSQL currently expires 2026-11-04 16:43 UTC. A sale-ready business needs a deliberate persistent database plan and uptime decision; no paid upgrade was made.

## Environment and secrets

All variables and defaults are in root/backend `.env.example` and frontend `.env.example`. Required production backend: ENVIRONMENT=production, persistent PostgreSQL DATABASE_URL, HTTPS FRONTEND_URL, random 32+ character ADMIN_TOKEN, GEMINI_API_KEY, GEMINI_MODEL and AI_PROVIDER. Frontend: NEXT_PUBLIC_API_URL, NODE_ENV=production. PORT is supplied by Render.

Secrets: DATABASE_URL, ADMIN_TOKEN, GEMINI_API_KEY, META_APP_SECRET, META_VERIFY_TOKEN, all *_ACCESS_TOKEN variables. Non-secrets: GOOGLE_CLIENT_ID, model/provider names, public URLs, account/phone/profile IDs, API versions, timeouts and flags. Account IDs may still be business-private. No Google client secret is required for the implemented ID-token sign-in.

Defaults: AI_MAX_ATTEMPTS=2, AI_ATTEMPT_TIMEOUT_SECONDS=12, AI_TIMEOUT_SECONDS=30, SOCIAL_DELIVERY_APPROVED=false, DRY_RUN=true, BOT_ENABLED=false. Do not enable live delivery until controlled allowlisted tests have passed and the owner explicitly approves it.

## Backup and restore

Use PostgreSQL `pg_dump`/`pg_restore` from Render's authorized private-network shell or an explicitly authorized restricted client. Never open the database to 0.0.0.0/0 just to run a backup. Set DATABASE_URL privately; do not print it, include it in filenames, or upload it to GitHub.

```bash
pg_dump --format=custom --file=roastai-backup.dump "$DATABASE_URL"
pg_restore --list roastai-backup.dump > roastai-backup-manifest.txt
sha256sum roastai-backup.dump > roastai-backup.sha256
```

Encrypt backups, restrict access, and retain them separately from the service/database account. They contain personal messages, email addresses, password hashes and session records. Verify restore into a NEW empty disposable database, not production:

```bash
pg_restore --exit-on-error --no-owner --no-acl --dbname="$RESTORE_DATABASE_URL" roastai-backup.dump
```

Confirm schema revision, counts of every table, account isolation, message/history reads and a restart. Record recovery duration and verify a second backup after deployment. Do not use `--clean` against production. Switching the production database or removing data requires owner approval. Full current-schema backups include users, sessions, login challenges, generation requests and provider state, not merely legacy messages. The existing SQLite importer is only for legacy v2 owner data into an EMPTY destination; it is not a modern full-account backup tool. Actual production backup/restore rehearsal remains unverified without an authorized database shell.

## Integration blockers and controlled acceptance

Google: create a Web OAuth client, authorized JavaScript origin `https://roastai-frontend.onrender.com`, and set backend GOOGLE_CLIENT_ID. Configure consent/test users or publish the app. Existing password accounts explicitly link their matching Google account in Settings. No client ID was present during the live audit.

Meta: configure owned WhatsApp phone ID/access token, owned Instagram account/token and login type, or Facebook Page ID/Page token; set matching API versions, META_APP_SECRET and META_VERIFY_TOKEN. Subscribe to messages at backend `/webhook/meta`. Complete the provider's required app review/permissions and verify ownership using its dashboard/API. First use an owner-controlled test sender only. Check signature rejection, echo rejection, wrong-account rejection, duplicate delivery, cooldown, dry-run and emergency-stop cancellation. Messages outside official allowed windows/types must not be sent. Current missing credentials mean live integration acceptance is BLOCKED, not passed.

Snapchat: only allowlisted Public Profile brand–creator collaboration; no general friend DM bot. Obtain messaging allowlist approval and a token/brand profile UUID. Renew tokens externally. Test against an owner-controlled creator. Do not claim ordinary Snapchat integration.

## Transfer checklist

- Buyer confirms intended use, ownership/provenance of code and branding, and any required assignment/licence agreement.
- Transfer repository and deployment/database ownership through provider-supported processes; confirm buyer access before revoking seller access. New permissions/transfers need explicit approval.
- Buyer creates their own Gemini/Meta/Snap/Google credentials; rotate all transferred secrets and ADMIN_TOKEN. Revoke old sessions deliberately, with approval and notification.
- Transfer OAuth consent/domain settings, Meta app/business/Page ownership, webhook registrations and approved permissions; these are not transferred by copying source code.
- Restore an encrypted backup to buyer infrastructure; verify counts, isolation, stable restart and recovery. Agree on retention/deletion and support responsibilities.
- Confirm permanent database storage, billing limits, budget alerts, uptime needs, privacy/terms, account recovery policy and incident contact.
- Deliver a tagged commit, environment template, architecture, test evidence, dependency inventory, known limitations and measured costs. Run acceptance with buyer-owned test accounts before approving live delivery.

## Browser acceptance reproduction

Install the separate browser test dependencies with `cd tests/browser && npm install && npx playwright install chromium`. Start from a frontend production build with `NEXT_PUBLIC_API_URL=http://127.0.0.1:8123 npm run build`. Set PYTHON_EXECUTABLE to your backend virtualenv Python and run `npm test` in tests/browser. It launches local backend/frontend ports 8123/8124 and uses an explicitly labelled local test provider. It verifies workflows and UI, not live Gemini quality. Delete only its disposable backend/tests/browser-fixture.db before a fresh rerun. This helper is not a production entry point. The production Render frontend rebuilds with its HTTPS API origin.
