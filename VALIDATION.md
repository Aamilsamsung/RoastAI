# RoastAI v2 validation record

Validated on 2026-10-05. This archive preserves the original v2 design and contains production deployment configuration. It is not a claim that a Render deployment or authenticated third-party integration has already succeeded.

| Check | Result |
|---|---|
| Original ZIP inspected | All 22 source/config files inspected; no database or credentials included |
| Original visual identity | Original stylesheet retained verbatim as prefix; flame/sunglasses SVG unchanged |
| Python syntax/imports | compileall and FastAPI import pass |
| Backend tests | **19 passed** with isolated SQLite databases; one real PostgreSQL integration test skipped locally |
| Production frontend build | `next build` passes with configured public API origin |
| TypeScript | `tsc --noEmit` passes |
| Dependency audit | `npm audit --omit=dev`: zero known vulnerabilities |
| Render Blueprint | Validated against published Render JSON schema |
| HTTP health | Running uvicorn `/health` returned 200 and healthy response |
| HTTP frontend | Production `npm start` returned 200; correct port/host arguments |
| API configuration | One centralized fetch wrapper uses NEXT_PUBLIC_API_URL; no hardcoded frontend loopback |
| Route coverage | All API routes referenced by frontend exist in FastAPI |
| Authentication/CORS | Owner token required, configured origin allowed, foreign origin blocked |
| Emergency safety | Tested persisted stop, save cannot restart, in-flight cancellation and rate-limit bypass |
| Persistence/migrations | SQLite migrations idempotent, original records retained, latest 100-message window correct |
| Signed webhooks | Plain-text verification, HMAC rejection, malformed payload rejection, durable enqueue and duplicates tested |
| Social delivery | Dry-run and each real send function invocation tested using test substitutions only |
| Browser smoke test | Login, all navigation, thread selection, 127-message paginated history, mode application, provider error recovery, stop and logout pass |
| Mobile | 390px viewport: no page overflow; Settings responds; emergency stop visible |
| Browser runtime | No page exceptions in tested flow |
| Secrets | No real credentials supplied or included; no provider secrets returned to browser or raw provider errors logged |

The browser test used the actual production Next server and FastAPI server, a disposable SQLite database with sample messages, and no Gemini key. Generation correctly displayed a provider error; it did not substitute a mock response. Backend unit tests substitute external AI and Meta calls only inside tests.

A Starlette TestClient deprecation warning is present in the installed dependency release; tests still pass. No production runtime warning was observed during the HTTP/browser smoke checks.

## Not verified without external infrastructure/credentials

- A live PostgreSQL connection, migrations and data-import execution against Render PostgreSQL. PostgreSQL driver imports and schema/configuration are checked, but a live database server was unavailable in this workspace. Run the migrations and confirm `/health` on the provisioned instance before accepting the deployment.
- Live Gemini model authorization, key validity, quota/billing and quality/latency.
- Meta account permissions, token validity, app review, webhook subscriptions and actual recipient delivery.
- GitHub Actions execution on your repository (workflow included).
- Render cloud deployment, actual assigned origins, real HTTPS CORS end-to-end and backup restore.

## Operating limits

Single-owner access, one backend instance and one uvicorn worker. PostgreSQL advisory locking prevents overlapping queue consumers during rolling deploy. Jobs survive restart; ambiguous in-flight jobs are marked uncertain rather than automatically resent. Failed/uncertain delivery jobs require reconciliation. Emergency stop cannot recall an HTTP send already transmitted to Meta. Status badges describe credential configuration, not a live network probe. Startup uses persisted settings rather than resetting them from environment defaults. No platform OAuth onboarding, multi-tenant isolation, large-scale queues or unsolicited social campaign support is claimed.

Desktop and mobile browser-check captures are in `docs/previews/`. They show test inputs, not live customer data.

HUB update: the Connecting to HUB startup screen was browser-tested with delayed real API requests; desktop loading preview is in `docs/previews/hub-loading.png`. Production build and TypeScript pass. Deployment still awaits explicit Render workspace selection and an accessible Git source repository.

## Google / Facebook update

25 backend tests pass, including nonce replay rejection, explicit existing-account linking, private Google account history and Facebook page/echo filtering. Frontend production build passes. Live Google and Facebook authentication/delivery require owner credentials and platform permissions; not verified. Snapchat supports only approved manual brand–creator collaboration via the official API; ordinary DMs remain unsupported. Real Snapchat access has not been verified. PostgreSQL integration test remains skipped without TEST_POSTGRES_URL.
