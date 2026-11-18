# Gemini and Groq failover

Gemini remains the primary provider by default. Groq is attempted only after an eligible failure and only when its backend key/model are configured. `AI_PROVIDER=groq` reverses the priority and uses Gemini as backup. Ollama remains explicitly local and never silently falls back to a cloud provider.

## Backend Render environment

| Variable | Value | Secret |
|---|---|---|
| GEMINI_API_KEY | Existing Gemini key | Yes |
| GEMINI_MODEL | Existing Gemini model; unchanged by this release | No |
| GROQ_API_KEY | Create in https://console.groq.com/keys and save privately in backend Render Environment | Yes |
| GROQ_MODEL | `openai/gpt-oss-20b` | No |
| AI_PROVIDER | `gemini` (or `groq` for reversed priority) | No |
| AI_FALLBACK_ENABLED | `true` | No |
| AI_TIMEOUT_SECONDS | Existing shared elapsed-time budget; default 30 seconds | No |
| AI_ATTEMPT_TIMEOUT_SECONDS | Existing per-network-attempt limit; default 12 seconds | No |
| AI_MAX_ATTEMPTS | Existing transient-retry cap per provider; default 2 | No |

No key belongs in NEXT_PUBLIC variables, browser bundles or chat. Existing manual Render services require adding the Groq key in their Environment page and saving/deploying. Blueprint `sync: false` does not populate secrets during updates. Missing Groq credentials are displayed as setup needed; the app continues using Gemini. The model default was verified against Groq's official supported-model list on 18 November 2026; models/access can change, so keep GROQ_MODEL configurable.

Reply and English meaning still come from one successful provider call, with the same roast modes, intensity, profanity, custom voice, languages, scripts and maximum reply length. A backup receives the same prompt and recent conversation context. Customer-facing privacy disclosures should cover both providers.

## Failure behavior

Timeouts/network failures, 400/401/403/404 configuration/key/model errors, quota 429, transient 408/500/502/503/504, empty responses and invalid reply/meaning pairs can activate backup. Transient failures may use the existing bounded retries; authentication/quota failures are not retried on the same provider. Explicit provider safety blocks/refusals and unexpected programming errors never trigger backup.

There are no parallel/hedged requests. A healthy primary never calls the backup. With both providers configured, the router reserves time for backup within the shared budget; retry loops do not reset it for each provider. HTTP timeouts apply to network phases, so this is not a strict wall-clock SLA. Successful-provider usage is reported separately from failed attempts; unknown failed-call token usage is not invented or treated as free.

Existing request-ID deduplication applies to the complete failover operation. Lost-response retries reuse the saved successful reply instead of re-running either provider. If both providers fail, no partial message pair is saved. Autonomous social replies use the same failover router and retain stop, account-isolation and delivery-approval controls.

The API's `usage` identifies the answering provider/model, fallback use, all provider outcomes, attempts and available token usage. Health distinguishes primary configuration from the provider that actually answered. The frontend labels successful backup responses as fallback and never exposes either provider's key.

## Rollback

For immediate Gemini-only behavior, set **AI_PROVIDER=gemini** and **AI_FALLBACK_ENABLED=false** on the backend, then save/deploy. Tests verify the backup is not called in this mode. Groq credentials can remain privately configured or be removed.

The source baseline immediately before this integration is commit **ec67d996aecda422f49c389cdf71fb48ca484750**. The integration is isolated in one commit so it can be reverted if requested. Set AI_PROVIDER back to gemini before restoring the old source, because that version does not accept `groq` as a primary provider. This release changes no database schema and does not delete or rewrite conversations, settings, accounts or activity.

## Verification scope

The regression suite covers both failover directions, healthy-primary no-backup behavior, missing credentials, errors/quotas/timeouts, malformed reply pairs, safety refusal, shared budget, Groq HTTP payload/retry/error redaction, usage parsing, actual-provider health, autonomous jobs and API request replay. Provider failures are simulated with labelled test doubles; they are not production fake responses. Real Groq inference and forced live failover require the backend Groq key and have not been claimed without that evidence.

Official API references:
- https://console.groq.com/docs/text-chat
- https://console.groq.com/docs/models
- https://console.groq.com/docs/reasoning
- https://console.groq.com/docs/errors

## Current deployment blocker (18 November 2026)

Before this integration was deployed, the backend was already unable to start because DATABASE_URL points to internal host `dpg-db1t7abtqb8s73ejj6p0-a`, which does not resolve. Render's read-only resource lookup returns 404 for that database and lists no PostgreSQL instances in the confirmed workspace. The frontend responds HTTP 200, but backend health and authenticated/live provider checks are blocked.

Restore access to the intended PostgreSQL database (and restore prior data from an available backup where necessary), then set the correct DATABASE_URL privately on the backend service and redeploy. No database was replaced, recreated, deleted or migrated by this feature. Real Groq inference also requires GROQ_API_KEY. No secret values have been requested in chat or copied into source.

Local validation: 151 backend tests passed; one PostgreSQL integration test skipped locally pending the isolated PostgreSQL CI job. Python compileall and the production frontend build passed. New provider failures use test doubles and HTTP mock transports; this is not a claim of live Groq verification.
