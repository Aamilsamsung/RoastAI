# RoastAI production launch audit — 25 October 2026

## Decision

Not ready for a public paid launch. This is the initial audit and first implementation tranche, not completion of all nine launch phases. Preserve the existing application and existing production data. Source baseline: `27aa0da92e257799dfc79af15ff839295f272117`.

## Direct evidence from this session

- Connected GitHub repository confirmed. Created development branch `launch/production-readiness-20261025`.
- Render workspace explicitly confirmed by owner. Frontend `srv-db1t7prtqb8s73ejksd0` and backend `srv-db1t7mlg1s2s73bma1o0` both report the baseline commit as their latest live deploy. Both track `main` with automatic deployment on commit. No production configuration was changed.
- Frontend: https://roastai-frontend.onrender.com/ . Backend: https://roastai-backend-ir7y.onrender.com/ . These remain the existing release, not this branch.
- PostgreSQL `dpg-db1t7abtqb8s73ejj6p0-a` is available, PostgreSQL 16, free plan, no external IP allowlist entries. Its expiration is **4 November 2026, 16:43 UTC / 22:13 IST**. This is a launch blocker requiring an owner-approved permanent-storage decision. No database upgrade, dump or destructive operation was performed.
- Both services use free compute. Live service configuration has an empty HTTP health-check path even though the repository Blueprint specifies paths. Configure the actual backend service with `/health` at approved deployment; editing YAML alone does not verify live settings.
- Metrics query returned empty data; no capacity, latency percentile or memory-use conclusion can be drawn. Recent backend error-log query returned no entries; this does not establish absence of errors.
- Backend health first timed out at 45 seconds, then succeeded with HTTP 200 in the longer observation. This is consistent with free-instance cold starts; it does not independently prove their cause.
- Live public `/api/auth/config` returned HTTP 200 with a configured Google client ID. This supersedes the older report that it was absent; it does not verify consent-screen settings or a real Google sign-in.
- Two new random QA accounts were registered using `example.invalid` emails and random in-memory passwords. Existing production rows were not removed. Successful login and settings reads for both; anonymous settings returned 401. One real Gemini generation returned HTTP 200 in 2.49 seconds, reply and English meaning present, one provider attempt, 297 input / 45 output / 342 total SDK tokens. Thinking tokens were absent, not measured as zero.
- The first QA account read its two messages; the second account read zero for that exact conversation. Logout returned 200 and reuse of that session returned 401. This is a narrow real smoke test, not exhaustive live QA. Additional login-issued QA sessions expire under the existing 24-hour policy; no credentials were printed or committed.

## Baseline and new validation

Fresh dependency install succeeded. Initial backend baseline was 108 passed, 15 failed, 1 skipped; all 15 failures were local SOCKS proxy support missing from the workspace. Installing `httpx[socks]` only in the temporary test environment produced **123 passed, 1 skipped** before source changes. No production dependency workaround was necessary.

After changes, **128 passed, 1 skipped** locally. One Starlette/httpx deprecation warning remains; it is not a failed test. The skipped real PostgreSQL integration requires `TEST_POSTGRES_URL`; the extended real PostgreSQL job passed in GitHub CI run 40221129512 on e223ccdd87c56999c23d09ae20ba9c82ebd2b5e0. This uses disposable infrastructure, not production data. The new SQLite tests cover missing-admin rejection, shared-status privacy, quota replay, failure release, user isolation, expiry/cancellation/past-due fallback, calendar-month rollover, and concurrent last-slot reservations. AI/social responses in these automated tests are mocked unless explicitly described above as a real live request.

Frontend Next.js 16.4.3 production build and TypeScript check passed. Production npm audit reports zero vulnerabilities after upgrade; baseline 16.3.8 reported one critical package with three advisories. The direct-package Python scan was clean, but the full dependency-resolution scan found PYSEC-2026-4320 in pinned certifi 2026.7.22. The branch upgrades it to 2026.10.19; the full resolved-requirements scan subsequently reported no known vulnerabilities. CI now audits the full resolved requirements on every run. Pattern scan of tracked files found no recognizable Google API keys, GitHub tokens or private-key headers; this is not a complete historical secret scan or a penetration test.

Local Playwright could not run because no Chromium binary was installed and download attempts returned invalid archives. The new browser CI job successfully installed Chromium and passed 65 desktop/mobile checks against the isolated mock-provider backend on e223ccdd (run 40221129512). Do not reuse historical browser reports as evidence for this branch. Physical-device and Safari verification remain outstanding.

## Implemented in this branch

1. Upgrade Next.js and its lockfile to patched 16.4.3; preserve UI and React versions.
2. Reject anonymous access when `ADMIN_TOKEN` is empty. Previously `not settings.admin_token` granted owner access. Production startup validation reduced exposure in production, but did not make this fail-open behavior acceptable elsewhere.
3. Filter the shared provider observation to public health fields. Other users can no longer obtain request/message IDs or internal exception names from this endpoint.
4. Add additive migration `0006`: subscriptions, UTC monthly usage and idempotent reservation ledger. No existing data is rewritten.
5. Add **opt-in manual-generation** quota enforcement: Free 30, Pro 500, Business 2,500. Quota reservation and request claim commit in one transaction. Concurrent requests cannot exceed the final available slot. Replays do not consume a second allowance. Known failed/cancelled requests release reservations; crashed/ambiguous ones retain them for review. Successful observed SDK counters are aggregated, not treated as a complete provider bill.
6. Add authenticated `/api/billing/usage` and owner-only `/api/admin/billing` read endpoints. No client can promote its own plan. Valid active/cancelled paid periods retain their plan; expired, past-due and unknown states fall back to Free. There is no subscription mutation/payment endpoint.
7. Keep both desktop/mobile Emergency stop buttons enabled during busy generation. Previously `disabled={busy}` blocked the user from invoking the stop precisely while a generation was running. Add a browser regression assertion; backend stop/epoch behavior remains covered by the API tests.
8. Upgrade certifi to 2026.10.19 and add full Python dependency auditing to CI. Add browser CI and extend PostgreSQL integration to test concurrent quota reservations.

`MANUAL_GENERATION_LIMITS_ENABLED=false` by default. This is a foundation, not complete SaaS billing: no checkout, provider webhooks, refund reconciliation, automated subscription synchronization, social-usage accounting, paid feature gating, multi-account Business support, usage UI or full billing administration screen is present. Owner workspace is intentionally exempt. Do not activate the flag as a substitute for completing product policy and all-channel accounting. Paid entitlement rows have no provisioning path until verified billing integration exists.

## Feature classification

“Verified working” below is bounded by the stated test environment; it does not mean the whole product is production-certified.

| Feature | Classification | Evidence / next acceptance |
|---|---|---|
| Email signup/login, settings reads, logout revocation | Verified working | Narrow live two-user API smoke; broader automated tests |
| Real Gemini reply and meaning | Verified working | One fresh production request; all languages/styles not re-certified live |
| Bounded provider retries and durable replay | Verified working | Existing automated tests; one live attempt does not exercise real upstream failure |
| Conversation isolation | Verified working | Exact-thread live denial and automated suite |
| Missing-admin rejection and provider health privacy | Verified working | Branch-local regression tests; not deployed |
| Manual monthly limits and expiry fallback | Verified working | Branch-local SQLite concurrency/state tests; disabled by default |
| New PostgreSQL quota migration/concurrency | Verified working | Real disposable PostgreSQL GitHub CI job passed on e223ccdd; production migration not applied |
| Desktop/mobile browser acceptance on updated frontend | Verified working | 65 Chromium checks passed in CI on e223ccdd; physical devices/Safari outstanding |
| Bot pause/stop, epoch cancellation, dry-run, webhook dedupe/signatures | Verified working | Mocked/controlled automated tests; live customer sends not enabled |
| Google login | Implemented but unverified | Live public auth config confirms a client ID is configured (HTTP 200); real browser/provider sign-in still needs authorized acceptance |
| Instagram/Facebook Pages/WhatsApp OAuth and delivery | Blocked by external setup | Mock-provider tests; app permissions, approved accounts, secure environment and real controlled acceptance required |
| Snapchat collaboration | Blocked by external setup | Existing restricted collaboration adapter; current official API and allowlist acceptance not re-certified; no general friend-DM claim |
| Social automatic token renewal | Incomplete | Expiry checks exist; verify each official renewal/revocation policy before implementation |
| Password reset/email verification | Incomplete | No recovery endpoints/provider |
| Persistent browser login security | Incomplete | Existing sessionStorage bearer sessions last 24 hours; HttpOnly cookie/CSRF/session-management design needed |
| Subscription checkout/webhooks/refunds/reconciliation | Incomplete | Proposed plan foundation only; payments always reported disabled |
| Plan enforcement across social accounts/automation | Incomplete | Manual opt-in enforcement only; one account per platform schema remains |
| Account deletion/export and retention | Incomplete | Conversation clear is not account deletion; lifecycle design required |
| Privacy/terms and customer support policies | Incomplete | Owner business identity and data practices needed |
| Production backups and restoration rehearsal | Blocked by external setup | Private recovery environment/access needed; existing runbook is not a tested backup |
| Monitoring, public load and full security assessment | Incomplete | Empty metrics; advisory/auth tests are not full penetration/load testing |

## Prioritized implementation plan

### P0: protect data and patch the exposed runtime

- Decide and approve durable PostgreSQL hosting before expiry. Take and restore an encrypted backup in a separate recovery database, verify row counts and tenant isolation, record recovery timings. Never open the production database to everyone for convenience.
- Review this branch's isolated Next.js security commit for an expedited approved frontend deployment. Verify the built runtime and live website afterwards. Production remains on the vulnerable dependency until deployment is approved and completed.
- Finish branch CI, review additive migration and rollback compatibility; deploy core security fixes only after explicit approval. Set actual Render HTTP health-check paths.

### P1: establish trustworthy accounts and delivery controls

- Implement verified email/reset flow using hashed single-use short-lived challenges, enumeration-resistant responses, bounded rates and secure mail-provider configuration. Revoke existing sessions after password recovery. Choose provider through secure configuration, not secrets in chat.
- Migrate browser auth to a reviewed HttpOnly cookie strategy with CSRF and exact-origin checks; add session list/revoke-all. Preserve existing accounts and upgrade carefully.
- Review schema/migrations under real PostgreSQL, complete backup recovery, test provider timeout/crash request recovery and retention of request bodies.
- Confirm current official social APIs/scopes. Configure approved owner test accounts and exercise OAuth, disconnect, expiry, signature failures, dedupe and stop in dry-run first. A stop can prevent future initiation; it cannot retract a network send already accepted by a provider.

### P2: commercial foundation

- Choose and approve a payment provider after account-specific eligibility/KYC. Add test-mode subscription creation, raw-body signature verification, durable unique provider-event IDs, server-mapped plans, ordering-safe reconciliation and provider lookup. Never trust frontend success callbacks for entitlements.
- Test successful charge, duplicate/out-of-order events, failure, retry, cancellation, expiration, refund and reconciliation outages. No live checkout until owner approval.
- Extend the ledger to social jobs and all billable provider attempts, enforce integration/automation/account-count features server-side, and add an honest usage/billing UI. Clarify calendar-month versus subscription-anniversary allowances before marketing them.

### P3: UX, privacy and launch gate

- Rerun desktop/320/390/720px browser acceptance, keyboard navigation and real owner-approved Google/Meta flows. Preserve recognizable RoastAI styles. Inspect every dashboard control; no cosmetic redesign was made in this tranche.
- Complete export, deletion, retention, privacy/terms, support/refund policies and monitoring. Run permitted staging load/security assessment. Record measured error rates, resource consumption and recovery objectives.
- Public launch requires all P0/P1 items and advertised features to pass their real acceptance criteria. Paid launch additionally requires all P2 payment/entitlement checks. Keep unverified integrations clearly labelled and automation delivery disabled.

## India payment-provider research

Razorpay documents subscriptions in India with cards, UPI AutoPay and eMandate, and has account activation/KYC requirements. It is a candidate, not confirmation that this owner's account is eligible or approved. Stripe's India site requires requesting an invite; do not assume immediate onboarding. No account was opened or paid service enabled. Owner-specific legal capacity, business category, settlement account, KYC, international-payment eligibility and recurring-payment approval remain unverified.

Sources checked 25 October 2026:
- https://razorpay.com/docs/payments/subscriptions/
- https://razorpay.com/terms/
- https://stripe.com/in
- https://support.stripe.com/questions/how-can-i-open-a-stripe-account-in-india

## Cost model

Current reported Render compute/database plans are free ($0 base compute); this is not a production reliability recommendation and does not include other workspace charges. An illustrative minimum paid stack is two $7/month web instances plus a $6/month database: **$20/month before database storage, bandwidth, backups, workspace costs and taxes**. Render's current pricing page is dynamically rendered and the direct text retrieval omitted prices; the search-indexed official pricing excerpt supports these unit rates, so reconfirm the Dashboard quote before approving any purchase. Smallest instances are not a verified capacity recommendation.

Google's current Gemini 3.5 Flash-Lite standard paid text rates are $0.30 per million input tokens and $2.50 per million output tokens including thinking. Today's single 297/45-token sample implies $0.0002016 per similar successful request, about **$2.02 per 10,000**. This is illustrative, not a workload benchmark; context length, reasoning, retries, failed/ambiguous attempts, rate tier and future pricing can change cost. No exchange rate or tax assumption is silently applied. Social platform, mail, payment processing and monitoring costs are additional.

- https://render.com/pricing
- https://render.com/docs/free
- https://ai.google.dev/gemini-api/docs/pricing

## Final code verification status

All four jobs passed on e223ccdd87c56999c23d09ae20ba9c82ebd2b5e0, including 65 browser assertions. The follow-up emergency-stop UI commit 6ea1df58c4edbdb12c8ae3805760a19831bc454e passed backend, full dependency audit, frontend and real PostgreSQL CI. Its browser regression run is still in progress at report preparation, installing Chromium. Treat the new emergency-stop browser assertion as pending until run 40221316683 completes. Local build/typecheck passed after that UI change.

Follow-up code CI: https://github.com/Aamilsamsung/RoastAI/actions/runs/40221316683

## Review references

- Draft PR: https://github.com/Aamilsamsung/RoastAI/pull/1
- Frontend security commit: ec6a3443a972b82eec69f4adc8de618aa97b2af7
- Emergency-stop UI fix: 6ea1df58c4edbdb12c8ae3805760a19831bc454e (separate follow-up CI required)
- Backend/usage/security/CI commit: e223ccdd87c56999c23d09ae20ba9c82ebd2b5e0
- Code CI: https://github.com/Aamilsamsung/RoastAI/actions/runs/40221129512
- Sanitized session evidence: LAUNCH-EVIDENCE-2026-10-25.json

## Approval boundaries and next gate

No production deployment, paid upgrade, destructive migration, real payment activation or autonomous customer message was performed. Development source commits and CI are authorized. Before production approval, present the exact commits, green CI, migration/backout plan and backup evidence. The imminent database expiry requires its own concrete hosting choice and paid-action approval if applicable.
