# User-owned social connection validation

This report supersedes the earlier owner-only bot restriction. Existing production records and owner integrations are preserved.

| Area | Result | Evidence |
|---|---|---|
| Python syntax and backend workflows | PASS | compileall; 118 pytest tests passed, one real PostgreSQL test skipped locally |
| Production frontend | PASS | Next.js build and TypeScript passed using deployed backend API origin |
| Browser workflows | PASS | 64 headless Chromium checks, including personal bot controls, persistence, mobile panels and labelled WhatsApp SDK flow |
| Instagram OAuth | PASS in local tests | Owner-bound single-use state, permission and identity verification, subscription acknowledgment, encrypted token isolation and safe failures |
| Facebook Page OAuth | PASS in local tests | Verified permissions/tasks, encrypted user-specific candidates, explicit Page selection, cross-user rejection and subscription failure handling |
| WhatsApp Embedded Signup | PASS in local tests | User-bound state, token app/scopes, WABA phone ownership, registration/subscription acknowledgments; untrusted SDK event origins rejected |
| Autonomous worker | PASS in local tests | Per-user settings/history, stopped and replaced connection cancellation, expiry/window checks, cooldown/rate limits, deduplication and dry-run enforcement |
| Provider transport errors | PASS | Controlled errors exclude credentials for HTTP and malformed/failed JSON responses |
| PostgreSQL migration/runtime | Pending CI | Real PostgreSQL integration test includes additive 0005 migration, encryption ownership constraints and one-use state |
| Live deployment/API verification | Pending release | Verify exact commit on both services and authenticated personal controls after deployment |
| Real Meta OAuth and delivery | BLOCKED | Meta app credentials, approved permissions, owned test accounts and controlled acceptance are required |
| Physical-phone SDK behavior | NOT TESTED | Narrow-screen Chromium testing is not physical-device or Safari testing |

The Meta/Google SDK success cases and upstream replies in browser/provider tests are explicitly labelled local fixtures. They are not production fake responses and are not evidence of actual Meta approval or customer delivery. SOCIAL_DELIVERY_APPROVED remains false. No paid resources, account permission grants or live customer sends were enabled.

The New roast control now stays disabled while a previous request is completing its history refresh, preventing silent ignored clicks. Logout invalidates pending OAuth states and Page selections; already connected autonomous bots keep their user-selected state. Local browser fixtures use unique temporary databases and verify their run ID rather than reusing stale services.

See SOCIAL-CONNECTIONS.md for exact external setup, supported account types, operational limits and acceptance steps.
