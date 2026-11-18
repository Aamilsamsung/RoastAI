# Google sign-in reliability fix — 18 November 2026

## Confirmed causes and changes

The live sign-in server is unavailable because application startup cannot resolve its configured PostgreSQL host. Both public Google configuration and health checks time out. A fresh deployment using saved service configuration still fails. This prevents every database-backed sign-in method and cannot be repaired with a Google client secret.

The previous frontend also renewed its nonce every four minutes while the Google picker could still be open. The new browser test reproduces the timing and verifies that an open picker prevents nonce replacement. Explicit retry after a closed picker creates a fresh challenge; a delayed callback from the old picker is ignored. Concurrent email login is disabled while the picker/verifier is active.

Google SDK loading is now deduplicated, bounded and retryable without a full page reload after a failed script load. Backend outage, missing Web Client ID, invalid client configuration, SDK failure and credential verification have distinct UI states. Public configuration returns only a valid Web Client ID; accidentally entered secrets are not echoed. Whitespace is normalized consistently for token audience verification. Signature, issuer, audience, verified email and single-use nonce checks remain enforced. Existing accounts still require explicit Google linking after password sign-in.

The frontend adds Cross-Origin-Opener-Policy: same-origin-allow-popups for popup compatibility.

## Validation

- Python compilation and 154 backend tests passed; one real PostgreSQL test is reserved for CI.
- 73 headless Chromium checks passed, including simulated backend outage, blocked SDK recovery, picker/nonce timing, stale callback rejection, Google verification failures/success with a labelled SDK fixture, mobile layout and existing Studio/social workflows.
- Real Google account sign-in is BLOCKED until the backend database connection is restored. The test fixture is not evidence of real Google OAuth success.

## Required live configuration

1. On Render's roastai-backend service, DATABASE_URL must point to the intended reachable PostgreSQL database. Restore prior accounts/history from an available backup where necessary; no new empty database has been substituted by this change.
2. Set GOOGLE_CLIENT_ID to the **Web application Client ID**, ending in .apps.googleusercontent.com, on the backend. A Google Client Secret and Gemini/Groq keys cannot be substituted for it.
3. In Google Auth Platform → Clients, authorize the exact JavaScript origin https://roastai-frontend.onrender.com (scheme + hostname, no path). Add any custom frontend origin separately.
4. While the Google app is in Testing, add the intended testers under Audience. Publish/configure branding and required policies for wider use.
5. Save, rebuild and deploy the backend after correcting its environment. Verify /health and /api/auth/config, then perform a real browser sign-in.

No passwords, session cookies, API keys, client secrets or database URLs should be pasted in chat. Store secrets privately in Render.

Official Google reference: https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid
