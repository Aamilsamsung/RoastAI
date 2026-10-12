# Validation scope — 2026-10-12 audit

82 backend tests passed locally; one PostgreSQL integration test was skipped locally because no disposable PostgreSQL URL was configured. GitHub Actions run 38261079918 passed backend, frontend and the real PostgreSQL integration job; the latter reported 1 passed and checked migrations, legacy imports/sequences, persistence, locking, scoped durable request replay and restart.

29 local headless Chromium browser checks passed at desktop 1440px and mobile 320/390/720px. They use a labelled local test provider, not live Gemini. No horizontal overflow, accessible drawers, Escape, focus containment, retained settings, separate conversations, refresh persistence, persistent errors and skipped redundant preference writes were checked.

46 real production Gemini Flash-Lite safe-prompt cases passed scripted smoke checks after throttling: nine modes, intensity 1–10, three profanity settings, voice cue, max lengths 50/300/1000, and ten languages in native/Roman scripts. See docs/handover/LIVE-BEHAVIOR-EVIDENCE.json. Native-language fluency and statistical severity monotonicity are not certified by these checks. Intensity prompt calibration changed afterward; final verification evidence must be read separately.

Production isolation checks proved anonymous/invalid access rejection, B unable to read A's exact conversation ID/conversations/activity, owner-only bot/Snapchat controls, independent defaults and logout revocation. Google client ID remained missing; live OAuth and platform delivery are blocked.

Frontend npm production audit reported zero vulnerabilities. The initial Python advisory scan found only inherited pip 25.0.1 advisories; patched pip 26.2.1 scan reported zero. These are advisory scans, not penetration testing. Recognizable secret-pattern scan and server-side-only provider wiring are checked separately; no raw provider secrets were retrieved.

No production data was deleted and no social live delivery was enabled. Additive schema migration and controlled QA data were used. Actual owner-history counts and production backup/restore rehearsal remain unverified without owner/database access. Free database expiry, account recovery/email verification and HttpOnly session hardening remain commercial readiness limitations.
