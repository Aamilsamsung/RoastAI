# Current validation: user-owned social connections

- Backend: Python compileall passed; 123 pytest tests passed, one real PostgreSQL integration test skipped locally. One Starlette/httpx test-client deprecation warning remains.
- PostgreSQL: GitHub Actions run 38399354362 passed the real PostgreSQL 16 integration job (1 test), including additive revision 0005 and encrypted connection/state checks.
- Frontend: Next.js production build and TypeScript passed with the deployed backend origin.
- Browser: 65 headless Chromium checks passed, including live thread refresh, mobile widths 320/390/720, private bot controls and labelled Google/Meta SDK fixtures.
- Blueprint: validated against Render's official JSON schema.
- Live API: 33 authenticated/public production checks passed on connection release 67b1f6a. New QA accounts only; existing data preserved and delivery disabled.
- Actual Meta OAuth/live delivery: BLOCKED by app credentials, permission approvals and controlled account acceptance. No fake production provider results or connected statuses were created.

Read docs/handover/SOCIAL-VALIDATION.md, SOCIAL-LIVE-EVIDENCE.json and SOCIAL-CONNECTIONS.md for scope, current release verification and setup. Earlier audit/latency evidence in docs/handover describes its own tested release and is retained as historical evidence.
