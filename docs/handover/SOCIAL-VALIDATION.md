# User-owned social connection validation

This report supersedes the earlier owner-only bot restriction. Existing production records and owner integrations are preserved.

| Area | Result | Evidence |
|---|---|---|
| Python syntax and backend workflows | PASS | compileall; 123 pytest tests passed, one real PostgreSQL test skipped locally |
| Production frontend | PASS | Next.js build and TypeScript passed using deployed backend API origin |
| Browser workflows | PASS | 65 headless Chromium checks, including personal bot controls, persistence, mobile panels and labelled WhatsApp SDK flow |
| Instagram OAuth | PASS in local tests | Owner-bound single-use state, permission and identity verification, subscription acknowledgment, encrypted token isolation and safe failures |
| Facebook Page OAuth | PASS in local tests | Verified permissions/tasks, encrypted user-specific candidates, explicit Page selection, cross-user rejection and subscription failure handling |
| WhatsApp Embedded Signup | PASS in local tests | User-bound state, token app/scopes, WABA phone ownership, registration/subscription acknowledgments; untrusted SDK event origins rejected |
| Autonomous worker | PASS in local tests | Per-user settings/history, stopped and replaced connection cancellation, expiry/window checks, cooldown/rate limits, deduplication and dry-run enforcement |
| Provider transport errors | PASS | Controlled errors exclude credentials for HTTP and malformed/failed JSON responses |
| PostgreSQL migration/runtime | PASS | Final code release 0fc11c1 passed GitHub run 38400934954; real PostgreSQL test passed in 1.98 seconds, including 0005, encrypted account isolation and single-use state |
| Live deployment/API verification | PASS on connection release | Both services live on final code release 0fc11c1; 44 production checks passed (33 initial + 11 final), including private personal controls, Google configuration, PostgreSQL, missing-setup failures and real Studio generation |
| Real Meta OAuth and delivery | BLOCKED | Meta app credentials, approved permissions, owned test accounts and controlled acceptance are required |
| Physical-phone SDK behavior | NOT TESTED | Narrow-screen Chromium testing is not physical-device or Safari testing |

The Meta/Google SDK success cases and upstream replies in browser/provider tests are explicitly labelled local fixtures. They are not production fake responses and are not evidence of actual Meta approval or customer delivery. SOCIAL_DELIVERY_APPROVED remains false. No paid resources, account permission grants or live customer sends were enabled.

The New roast control now stays disabled while a previous request is completing its history refresh, preventing silent ignored clicks. Logout invalidates pending OAuth states and Page selections; already connected autonomous bots keep their user-selected state. Local browser fixtures use unique temporary databases and verify their run ID rather than reusing stale services.

See SOCIAL-CONNECTIONS.md for exact external setup, supported account types, operational limits and acceptance steps.

Latest live Studio sample: HTTP 200, 10.584 seconds wall time, 10.222 seconds AI stage, one provider attempt, Gemini 3.5 Flash-Lite, 295 input / 51 output / 346 total tokens; thinking-token count unavailable. This is one successful sample, not a latency guarantee or percentile. No Meta account has been connected or contacted by QA.

Final refinements validate original webhook sender IDs and finite/non-future timestamps, refresh only the visible open conversation and discard stale thread responses. Autonomous AI failures now update provider health independently of bot enablement and Meta delivery failures. The final code release SHA matched both live Render services and all three successful CI jobs. Final API checks confirmed settings/history across deployment and revoked both temporary QA sessions. The following handover-only commit changes documentation/evidence, not application code.

Final checks are in SOCIAL-FINAL-DEPLOYMENT.json. Real platform OAuth and controlled live sends remain blocked by external configuration and approval; no customer contact occurred.
