# RoastAI v2 — Render deployment edition

Existing Next.js/TypeScript v2 purple workspace and FastAPI backend, with Gemini reply + English meaning in a single call. Official WhatsApp Cloud API and Instagram Messaging API only. No mock provider, scraping, browser sessions or WhatsApp Web.

## Architecture and operating scope

Two public Render web services plus private Render PostgreSQL. The frontend browser calls the backend origin through `NEXT_PUBLIC_API_URL`; Gemini and Meta credentials exist only in the backend environment. An owner enters the separately generated `ADMIN_TOKEN` into the workspace login; it stays in React memory, is sent as a Bearer credential over HTTPS, and is cleared on sign-out or reload. Never distribute it to untrusted users. Owner access uses ADMIN_TOKEN; friends use email/password accounts with isolated Studio conversations, activity and preferences. Social integrations remain exclusively in the owner workspace. Changing the token in Render revokes existing access.

The existing Studio, Conversations, Activity, Platforms and Settings remain. Studio changes save before generation so modes, intensity, voice, profanity and language controls apply immediately. Manual Studio generation works with Bot OFF for testing; emergency stop blocks it. Bot ON/OFF controls automatic social replies. Explicit Start resets emergency stop. Save cannot turn a paused bot back on.

Settings, messages, audit activity, webhook jobs and sender cooldown history survive restarts. Conversation threads display the full loaded page and offer Load older messages; history is retrieved in validated 100-message cursor pages. Startup and pre-deploy run versioned Alembic migrations. The baseline migration adopts the old v2 SQLite schema without deleting rows. The uploaded ZIP contained **no database file**, so it had no existing conversation records to transfer; existing databases outside the ZIP can be imported as described below. Original in-memory settings never persisted, so those cannot be recovered from an old stopped process.

## 1. Local development

Use Python 3.12 and Node.js 22 (Node 24 also tested).

```bash
cd backend
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell instead: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
cp .env.example .env
# Windows: copy .env.example .env
# Edit .env: GEMINI_API_KEY, ADMIN_TOKEN (random 32+ chars), FRONTEND_URL
python -m alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

In a second terminal:

```bash
cd frontend
cp .env.example .env.local
# Windows: copy .env.example .env.local
npm ci
npm run dev
```

Open http://localhost:3000. Enter the backend `ADMIN_TOKEN`. If it is empty in development, the backend accepts unauthenticated requests (never allowed in production). Local SQLite is `backend/roastbot.db` when launched from `backend`; keep that file when upgrading. Do not launch from a different working directory if preserving the same relative SQLite path. You can use an absolute `sqlite:////absolute/path/roastbot.db` URL.

`setup.bat` and `start_windows.bat` remain supported. Setup copies both local environment templates. `build_windows.bat` runs tests and the production build. Add credentials before launching.

Local production check:

```bash
cd frontend
npm ci
npm run typecheck
npm run build
npm start
```

`npm start` binds `0.0.0.0` and uses `PORT`, or 3000 locally. After deployment changes you can still use `npm run dev` and local SQLite; maintain separate local and Render environment values.

## 2. GitHub setup

Extract the ZIP. Push the **contents of RoastAI/** as the repository root, so `render.yaml`, `frontend/` and `backend/` are directly at the root.

```bash
git init
git add .
git commit -m "Prepare RoastAI v2 for Render"
git branch -M main
git remote add origin https://github.com/YOUR_ACCOUNT/RoastAI.git
git push -u origin main
```

The ignore file excludes credentials, SQLite data, node_modules, build output and virtual environments. Commit `package-lock.json`, all migrations, and both `.env.example` templates. Never commit `.env` or `.env.local`.

## 3. Render Blueprint setup

1. Render Dashboard → New → Blueprint → connect the GitHub repository → select `render.yaml`.
2. Review the resources: two Free web services and Free PostgreSQL in Oregon. Free web services sleep after inactivity. Render serves its own startup page until the frontend starts; the app then shows Connecting to HUB while the backend wakes. Free PostgreSQL expires after 30 days: migrate or export your data before expiry. This is a free trial deployment, not permanent production storage.
3. Supply prompted values: backend `GEMINI_API_KEY`, backend `FRONTEND_URL`, frontend `NEXT_PUBLIC_API_URL`. Use the actual HTTPS origins assigned by Render, without trailing slash or `/api`.
4. Expected URL shapes are `https://roastai-backend.onrender.com` and `https://roastai-frontend.onrender.com`. Names may receive unique suffixes. If the final URLs are not known during Blueprint creation, enter valid placeholder HTTPS origins, then immediately replace them with the assigned service URLs and redeploy both services. Do not use placeholder domains for operation.
5. Database connection is injected by the Blueprint. `ADMIN_TOKEN` is generated by Render. Copy it privately from the backend Environment page and enter it into the frontend login.
6. Confirm backend `https://YOUR_BACKEND.onrender.com/health` returns `{"status":"ok"}`.
7. After updating frontend `NEXT_PUBLIC_API_URL`, deploy the frontend again: Next.js embeds this public variable at **build time**. A process restart alone does not change it.
8. Backend `FRONTEND_URL` must exactly match the frontend browser origin, including `https://`. Redeploy the backend after changing it.
9. Keep Bot OFF and dry-run ON while configuring Meta. Test real Studio generation, then a signed test webhook. Enable live delivery only after confirming permissions and delivery.

For manual service creation use these exact settings:

| Setting | Backend | Frontend |
|---|---|---|
| Service type | Web Service | Web Service |
| Runtime | Python | Node |
| Root directory | `backend` | `frontend` |
| Build command | `pip install -r requirements.txt` | `npm ci && npm run build` |
| Pre-deploy command | None; migrations run on startup | None |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1` | `npm start` |
| Health check | `/health` | `/` |
| Plan | Free | Free |
| Region | Oregon | Oregon |
| Instances | **1** | 1 |

Use one backend worker and one instance. The database advisory lock prevents overlapping queue consumers during rolling deploys, but this release is not designed for horizontally scaled workers. Starter supports pre-deploy migrations. Free services sleep and are unsuitable for timely social webhook handling.

## 4. Environment variables and secrets

Root `.env.example` inventories everything. Runtime reads `backend/.env` locally; Next reads `frontend/.env.local`. On Render, configure the appropriate service Environment tab.

| Variable | Service | Production value/default | Secret? |
|---|---|---|---|
| `ENVIRONMENT` | Backend | `production` | No |
| `DATABASE_URL` | Backend | Render PostgreSQL **internal connection string** | **Yes** |
| `FRONTEND_URL` | Backend | Actual frontend HTTPS origin | No |
| `CORS_ORIGINS` | Backend | Optional comma-separated exact origins; defaults to FRONTEND_URL | No |
| `ADMIN_TOKEN` | Backend | Generated random token, at least 32 characters | **Yes** |
| `GEMINI_API_KEY` | Backend | Google AI Studio key | **Yes** |
| `GEMINI_MODEL` | Backend | `gemini-3.8-flash`; use a model enabled for your project | No |
| `AI_PROVIDER` | Backend | `gemini` | No |
| `AI_TIMEOUT_SECONDS` | Backend | `30` | No |
| `RATE_LIMIT_PER_MINUTE` | Backend | `20` Studio generations per minute | No |
| `NEXT_PUBLIC_API_URL` | Frontend | Actual backend HTTPS origin | No; visible in browser |
| `NODE_ENV` | Frontend | `production` | No |
| `NODE_VERSION` | Frontend | `22.22.0` | No |
| `NEXT_TELEMETRY_DISABLED` | Frontend | `1` | No |
| `PYTHON_VERSION` | Backend | `3.12.14` | No |
| `META_VERIFY_TOKEN` | Backend | Random webhook verification token you choose | **Yes** |
| `META_APP_SECRET` | Backend | Meta app secret for HMAC signatures | **Yes** |
| `WHATSAPP_ACCESS_TOKEN` | Backend | Supported long-lived/system-user access token | **Yes** |
| `WHATSAPP_PHONE_NUMBER_ID` | Backend | WhatsApp Business phone number ID | No |
| `WHATSAPP_API_VERSION` | Backend | `v23.0` or a supported version for your app | No |
| `INSTAGRAM_ACCESS_TOKEN` | Backend | Token matching the chosen Instagram login flow | **Yes** |
| `INSTAGRAM_ACCOUNT_ID` | Backend | Professional Instagram account ID | No |
| `INSTAGRAM_API_VERSION` | Backend | `v23.0` or a supported version for your app | No |
| `INSTAGRAM_LOGIN_TYPE` | Backend | `instagram` or `facebook` | No |
| `BOT_ENABLED` | Backend | `false` initial default | No |
| `DRY_RUN` | Backend | `true` initial default | No |
| `ROAST_MODE` | Backend | `savage` | No |
| `ROAST_INTENSITY` | Backend | `7` (1–10) | No |
| `PROFANITY_LEVEL` | Backend | `light` (`off`, `light`, `heavy`) | No |
| `CUSTOM_INSTRUCTIONS` | Backend | Empty; max 2000 chars | No |
| `REPLY_DELAY_SECONDS` | Backend | `0` in environment template (0–60) | No |
| `COOLDOWN_SECONDS` | Backend | `10` (0–3600) | No |
| `MAX_REPLY_LENGTH` | Backend | `300` (50–1000) | No |
| `INPUT_LANGUAGE` | Backend | `auto` | No |
| `REPLY_LANGUAGE` | Backend | `same` or a supported language | No |
| `SCRIPT_MODE` | Backend | `roman` or `native` | No |
| `OLLAMA_BASE_URL` | Backend | Optional reachable private Ollama URL; local template uses loopback | No |
| `OLLAMA_MODEL` | Backend | `gemma4:4b`; optional local provider | No |

`PORT` is provided by Render; do not set it yourself. Only `NEXT_PUBLIC_API_URL` belongs in the frontend. Never define `NEXT_PUBLIC_GEMINI_API_KEY`, Meta tokens or a public admin token. Browser owners intentionally enter the admin credential themselves; it is never embedded into the app bundle or returned by the API.

Bot preference environment values are **initial defaults**. Once stored, saved database preferences take precedence. Use the UI to change them, including dry-run. Changing `DRY_RUN` in Render does not overwrite a saved preference. The Blueprint starts safely with bot disabled and dry-run enabled.

## 5. PostgreSQL and existing data

Create Render PostgreSQL in the backend's region. Use its internal URL for DATABASE_URL. The Blueprint denies external database connections by default. Production refuses SQLite rather than silently saving conversations on an ephemeral filesystem. Configure backups appropriate to the purchased database plan and test restoration.

Migrations run before deploy and also safely check the current revision on startup. `alembic current` should report `0002 (head)`.

If you have an older `roastbot.db` outside the uploaded ZIP, back it up before migration. To transfer it, migrate an **empty PostgreSQL database before starting the backend**, set DATABASE_URL to the destination, then from `backend`:

```bash
python -m alembic upgrade head
python -m scripts.import_sqlite /absolute/path/to/roastbot.db
```

All available messages, activity, processed IDs, saved settings and webhook jobs are imported in a single transaction with original IDs and timestamps. Nonempty destinations are refused. Sequence values are repaired. Since startup writes a preference row and system log, do this before the first app startup. If the destination already started, create a fresh destination for import and switch to it after verifying counts; do not delete existing production records to bypass the guard. To import from your computer, temporarily permit your IP in Render database access and use the external connection string with its prescribed TLS options; remove that access afterward. Alternatively run the import where Render private networking is available.

## 6. Gemini configuration

Create your own key in Google AI Studio and set it on the backend only. Gemini is the default provider. Generation uses the Google SDK `models.generate_content`: one request asks for `REPLY:` and `MEANING:`, with minimal thinking and 480 output tokens. Gemini 2.5 Flash uses thinking_budget=0 if you select that model. A missing/blocked response, quota error, timeout or invalid format produces a sanitized UI error and audit event; no fake reply is substituted. Model access and billing depend on your Google project. Confirm your selected model supports the configured thinking control.

Optional Ollama support remains, using a server-side reachable URL and bounded response timeout. An Ollama instance on your laptop is not accessible through Render's loopback address.

## 7. WhatsApp Cloud API

Use a Meta developer app with the WhatsApp product, supported Business configuration, phone number ID and a token with messaging permissions. Configure `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_API_VERSION`, `META_VERIFY_TOKEN` and `META_APP_SECRET` on the backend. Subscribe the app to the relevant WhatsApp Business Account and `messages` webhook field. Text-message webhook events generate a contextual reply. The sender's actual message ID deduplicates deliveries. Status updates and unsupported media are ignored. This release replies to incoming text; it does not implement unsolicited campaigns or template messaging outside Meta's allowed response window.

## 8. Instagram Messaging API

Use a professional Business/Creator account and approved messaging permissions.

- `INSTAGRAM_LOGIN_TYPE=instagram`: Instagram Login token; send endpoint uses `graph.instagram.com/{version}/{account_id}/messages`. Typical messaging permission is `instagram_business_manage_messages`.
- `INSTAGRAM_LOGIN_TYPE=facebook`: Facebook Login/Page token and linked professional account; send endpoint uses `graph.facebook.com/{version}/{account_id}/messages`. Configure the relevant Page/Instagram subscriptions and `instagram_manage_messages`/Page permissions for that flow.

Set the matching token, account ID and API version. Complete Meta's required login/subscription setup outside this single-owner console; this release does not host an OAuth onboarding flow for other customers. The callback accepts Instagram `object=instagram` messaging events and skips message echoes to prevent reply loops. Account IDs, permission requirements, review, tester roles and allowed messaging windows are governed by your actual Meta app configuration. Test with an eligible account before turning off dry-run.

## 9. Meta webhook configuration

Callback: **`https://YOUR_BACKEND.onrender.com/webhook/meta`** for both supported products. Verify token: the exact backend `META_VERIFY_TOKEN`.

GET validates the token and returns the challenge as plain text. POST requires the correct `X-Hub-Signature-256` HMAC using `META_APP_SECRET`; no bypass mode. Signed events are persisted before the response. An internal async worker processes the durable queue. Duplicate message IDs return acceptance count zero. Keep the single backend service running continuously.

Dry-run generates and records a reply without sending to Meta. Live replies are recorded as outgoing only after Meta accepts delivery. Bot OFF, per-platform OFF, sender cooldown, emergency stop and changed delivery settings cancel or skip delivery. Emergency stop is checked again after AI generation and before sending; an HTTP request already sent to Meta cannot be recalled.

Failed jobs are retained as `failed`; crash-interrupted sends are marked `uncertain` to avoid accidentally resending an already delivered message. They are not automatically retried. Inspect `webhook_jobs` and Activity; reconcile with Meta delivery evidence before manually retrying a failed/uncertain item. A queue acknowledgement is not a claim of successful delivery. This is a deliberate at-most-once attempt policy, not a guarantee of exactly-once third-party delivery.

## 10. Troubleshooting

- Frontend can't connect: check NEXT_PUBLIC_API_URL has HTTPS backend origin, no `/api` suffix; rebuild frontend. Check backend FRONTEND_URL matches frontend origin.
- Workspace 401: use the backend ADMIN_TOKEN, not Gemini or Meta credentials. Reload clears it; re-enter it. Rotate compromised tokens.
- Backend fails startup: check production PostgreSQL URL, 32+ character admin token, HTTPS frontend URL and migration logs.
- `/health` fails: database connectivity or schema problem. Verify database and backend regions/internal connection string.
- Studio 502: check Gemini model access, key, quota and billing. Errors are sanitized so secrets do not enter logs.
- Studio 409: emergency stop or a setting/stop action changed while generation ran. Reset with Start when intended and retry.
- Studio 429: wait for the one-minute generation window. General API limits also apply. Limits are per process and reset after restart; sender cooldown persists in messages.
- Meta verification fails: exact callback URL, verify token, challenge and deployed backend required.
- Meta POST 403: wrong app secret/signature. Never disable signature checks.
- No social reply: inspect Bot ON, platform switch, dry-run, cooldown, Activity and webhook job status. Check official account permissions/subscriptions/token validity and messaging windows.
- Platform says Configured but send fails: configuration status is not a network/authentication probe. Real provider success needs valid credentials and an eligible recipient.
- History after upgrade: don't switch local working directories or overwrite roastbot.db. In production use PostgreSQL; never SQLite on Render ephemeral storage.
- Mobile: the original sidebar becomes top navigation with accessible icon labels. Emergency stop remains visible.

## 11. Validation

```bash
cd backend
python -m compileall -q app migrations scripts
python -m pytest -q
python -m alembic upgrade head
python -m alembic current
cd ../frontend
npm ci
npm run typecheck
npm run build
npm audit --omit=dev
```

Tests use isolated SQLite databases and substitute provider calls **only inside tests**, never in runtime. They cover request/auth/CORS validation, persistence, controls, history, safe errors, webhook verification/deduplication, dry-run, actual send-function invocation, in-flight emergency cancellation and limits. See `VALIDATION.md` for the checks completed and explicit external limitations.

## 12. Production limitations requiring external work

Supply Gemini/Meta credentials, supported model access, account permissions, app review and subscriptions. No live provider calls can be verified without those. Complete a real dry-run and live delivery smoke test on your Render account. This archive is deployable configuration and validated application code, not proof of a completed cloud deployment. Shared admin access is intentional for one owner; OAuth social customer onboarding and high-volume queue infrastructure are future additions. Backups, credentials rotation and ongoing operations belong to the deployment owner.

## Official references

- Render Next.js: https://render.com/docs/deploy-nextjs-app
- Render Blueprints: https://render.com/docs/blueprint-spec
- Gemini models: https://ai.google.dev/gemini-api/docs/models
- Gemini thinking: https://ai.google.dev/gemini-api/docs/generate-content/thinking
- Meta Instagram messaging: https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/messaging-api
- WhatsApp Cloud API: https://developers.facebook.com/docs/whatsapp/cloud-api

## PostgreSQL integration check

GitHub Actions includes a separate PostgreSQL 16 service and a real database integration job. It checks migrations, original SQLite import, repaired sequences, saved settings, concurrent preference updates, webhook deduplication and restart handling. The CI password is disposable test configuration, not a production credential. This workflow has not been executed on your GitHub account yet.

To run it locally against a disposable PostgreSQL database, set `TEST_POSTGRES_URL` and run `python -m pytest tests/test_postgres.py -q` from backend. The test creates a randomly named isolated schema, sets its connection search_path exclusively to that schema, and drops that same schema afterward. Use a test database with schema-creation permissions. Without TEST_POSTGRES_URL, it is explicitly skipped; a skipped test is not proof of PostgreSQL runtime validation.

## HUB connection screen

The initial connection state and Next.js route-loading boundary show **Connecting to HUB** with the existing RoastAI flame branding, purple orbit and indeterminate loading bar. Motion respects the reduced-motion preference. Initial API requests can wait up to 90 seconds for backend startup; normal actions retain the 45-second timeout. The interface transitions to authentication or the workspace when the real requests complete, with no fake progress percentage. Network failures eventually show an actionable error.

This is the application's own loading UI. A Render platform cold-start page displayed before the frontend server can return HTML is controlled by Render and cannot be replaced by React code. The free services specified in this Blueprint can sleep after inactivity.

Free resources were created on 2026-10-05. Frontend: https://roastai-frontend.onrender.com. Backend: https://roastai-backend-ir7y.onrender.com. Backend DATABASE_URL and Gemini credentials still require configuration; resource creation is not proof of a healthy deployment. The free Render database expires on 2026-11-04; export or migrate data before that date.

## Friend accounts

Friends select Sign up on the access screen, enter an email and a password of at least 12 characters, and receive their own private workspace. Passwords use salted scrypt hashes; session bearer tokens are random, stored hashed in PostgreSQL, expire after 24 hours, and are revoked on sign-out. The browser holds tokens in memory only; reloading requires login. Account history, activity and settings are filtered by the authenticated user at the backend. No client-supplied owner ID is trusted. Legacy records remain in owner workspace 0. Social bot start/stop/emergency controls require owner access; friends may use Studio with independent settings. Authentication has IP-based cooldown protection.

Email verification and password recovery email are not implemented; accounts can sign in immediately, and forgotten passwords currently need a future recovery flow. Public signup consumes the configured owner's Gemini quota, bounded by per-user generation limits and shared IP limits; configure Google quota controls before distributing widely. No per-user Meta account connection is implemented. Free Render database expiration still applies to all account data.
