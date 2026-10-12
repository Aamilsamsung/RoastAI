# RoastAI implementation and acceptance report — 2026-10-12

This report concerns the actual Aamilsamsung/RoastAI source and the frontend/backend services on Render, not a recreated demo. Core fixes are deployed; externally blocked commercial requirements are not represented as completed. See the evidence JSON files in this directory. The deployed prompt was tested at commit c56285491e12636126451a6a2a2b2ec42ccb20b9; subsequent handover/error-display updates retain the same provider and prompt behavior.

## Root causes and corrections

1. The two audit failures were ServerError events. A new authenticated QA request reproduced HTTP 502 after 14.957 seconds. Enhanced safe diagnostics proved Gemini 3.8 Flash returned HTTP 503 on both bounded attempts. The same backend credentials succeeded on Gemini 3.5 Flash-Lite, proving the tested generation failure was model-specific upstream unavailability, not a missing key or the application's reply parser. This does not establish the cause of Google's capacity decision or guarantee future uptime.
2. The SDK's default retry policy could include nested retries. Retry attempts are now explicitly controlled: normally one generation returning reply and English meaning, at most two attempts for transient failures. Invalid-key, permission, unavailable-model and quota errors are surfaced without blind retries. Request IDs, durations, model, attempts and SDK token counters are recorded without secrets/raw upstream error strings.
3. Credential presence was conflated with health, and Bot ON was described as live. Provider status now reflects a recent successful/unavailable/quota-limited/setup-error observation, expiring after ten minutes. Bot enabled, dry-run enforcement and configuration are separate concepts.
4. New roast formerly reused one `roast-me` thread. New conversations have separate IDs; existing history remains readable. Message pair, activity and idempotent result are stored atomically. A replay returns the durable result; simultaneous duplicate submissions start only one generation.
5. Repeated preference writes and history requests added unnecessary round trips. Unchanged Studio settings no longer trigger a save. Answers are shown before dashboard/history refresh completes. Errors remain visible until dismissed. Lost/protocol-invalid responses keep their pending request IDs for safe recovery; obsolete account responses are rejected, and sign-out clears private drafts. Copy uses a real selection fallback when the modern API is denied, with no fake success.
6. All intensity values reached the provider, but some actual samples were similar. Explicit gentle/pointed/sharp/cutting guidance and mode distinctions were added. Final endpoint samples differed qualitatively. This is not a statistical guarantee of monotonically increasing severity on every input.
7. Password hashing is versioned and upgraded on login while preserving legacy hashes. Validation responses no longer echo submitted secrets. Invalid authentication is subject to IP limits. Google audience/issuer/verified-email/subject and nonce/replay tests were expanded. User ownership remains server-derived.
8. Meta event parsing now rejects missing/mismatched configured account IDs. SOCIAL_DELIVERY_APPROVED=false enforces dry-run independently of saved UI settings. No real customers were contacted or live social sends enabled. App access-log query strings are redacted so Meta verification tokens are not written by Uvicorn. The inherited pip installer was patched to 26.2.1 after its advisory scan; patched environment and frontend production audits reported zero known vulnerabilities.

The final browser suite also verified a dropped-response retry, malformed-response retry, clipboard fallback, saved mobile settings after reload, and account-switch isolation; 40 checks passed.

## Acceptance matrix

| Area | Status | Evidence / limit |
|---|---|---|
| Real Gemini generation + English meaning | PASS | Repaired model returned actual replies; 46 paced control cases plus 12 final calibrated prompt cases succeeded |
| Mode/intensity/profanity/voice/length controls | PASS | All nine modes, levels 1–10, three profanity settings, voice cue, limits 50/300/1000; final mode/endpoint/voice recheck. Smoke tests, not exhaustive statistical semantics |
| Native/Roman script and language wiring | PASS | English plus nine other languages in both scripts; character-range checks and meaning presence |
| Native-language fluency / translation accuracy certification | NOT TESTED | Requires competent native-speaker review across varied prompts |
| Conversations, settings, messages, activity and refresh | PASS | Automated API tests, local browser workflows and live authenticated QA/API persistence across deployed restarts |
| Concurrent/replayed request protection | PASS | Durable scoped keys, one-generation concurrent test and live replay returned original result without new messages |
| Multi-user isolation and logout | PASS | Second live QA account cannot read A's exact thread, list, activity or custom voice; owner controls forbidden; logout token rejected |
| Hashes, session expiry and Google token validation | PASS | Automated success/failure and legacy upgrade tests; live Google sign-in itself remains blocked |
| Recognizable secret-pattern scan and backend-only provider wiring | PASS | No recognizable Gemini/Meta credential patterns in built frontend; client app reads NEXT_PUBLIC_API_URL only. No raw production secrets retrieved |
| Security penetration test / hostile public load | NOT TESTED | Advisory scans and automated authorization checks are not a penetration/load test |
| Desktop/mobile layout and keyboard controls | PASS | Headless Chromium 1440px desktop, 320/390/720px phone widths: drawers, focus, Escape, scrolling, no overflow, persistent errors; labelled local test provider; 40 browser checks, including recovery/copy/account-switch privacy |
| Physical devices / Safari / authenticated owner's deployed browser | NOT TESTED | Emulator evidence and live API evidence are distinct; no claim of access to the owner's current browser session |
| Official Meta signature, echo, ownership, deduplication and emergency-stop paths | PASS | Controlled automated tests; uncertain/failed deliveries are retained |
| WhatsApp / Instagram / Facebook production delivery | BLOCKED | Missing credentials/account IDs, permissions/ownership acceptance and controlled owner-approved tests |
| Snapchat ordinary friend DM bot | BLOCKED | Not supported by implemented official API; collaboration needs messaging allowlist and owned profile/token |
| Google sign-in | BLOCKED | Backend GOOGLE_CLIENT_ID absent; Web OAuth consent/origin configuration required |
| PostgreSQL migration, import, locking, replay and restart | PASS | Real PostgreSQL GitHub CI job passed; additive 0004 migration deployed and production application/API remained healthy |
| Production backup and restore rehearsal | BLOCKED | Private database prevents direct connector inspection; authorized private-network shell/recovery environment needed. Instructions supplied; access was not widened |
| Permanent storage and always-on uptime | FAIL for commercial launch | Current free database expires 2026-11-04; free services sleep. No paid upgrade was authorized or made |
| Self-service password recovery / email verification | FAIL for broad commercial launch | Not implemented; disclose limitation and choose an email/recovery provider before public commercial onboarding |
| Architecture/setup/licences/cost/transfer docs | PASS | OPERATIONS.md, ARCHITECTURE.md, COSTS.md, licence inventory and transfer checklist delivered; legal provenance/assignments still need owner/buyer confirmation |

## Measured results and costs

Local backend: 88 passed, one real PostgreSQL integration test skipped locally. Real PostgreSQL integration passed in GitHub CI (1 passed); CI also passed frontend build/typecheck/audit and backend suite for the tested release. Final handover CI must be checked against its committed SHA.

The initial 46-case repaired smoke run had median AI-stage 1.189 seconds; range 0.878–4.372 seconds. Test-client wall median 1.586 seconds, range 1.314–15.469 seconds; fresh urllib connections had large transport overhead, while pooled-client observations were normally near 1.6 seconds. These are test-environment observations, not a user-facing SLA.

The final 12 calibrated cases had median AI-stage 1.083 seconds and pooled-client wall median 1.476 seconds (1.309–2.917 seconds). Mean input 290.42 tokens; billable output inferred from total minus input 38.17 tokens. SDK thinking counter was absent; it was not fabricated as zero. At official Flash-Lite standard paid rates, this sample is roughly $1.83 per 10,000 similar successful requests. Actual billing tier, traffic, long histories, failed/ambiguous attempts, taxes, hosting and integration costs remain additional assumptions. See COSTS.md and FINAL-LATENCY-COST.json.

Both provider 429s and application 429s occurred during a too-fast benchmark; they were surfaced without blind retries. All cases passed after paced tests. This establishes cooldown behavior, not unlimited quota. QA accounts/conversations were appended intentionally; no original production rows were deleted. Cleanup of production QA records requires owner approval.

## Remaining sale requirements

RoastAI is now a functioning, tested AI web application and a substantially better handover package. It is not yet a turnkey, fully connected commercial SaaS. Before sale as a reliable ongoing service: establish permanent database storage, rehearse recovery, configure buyer-owned credentials/OAuth/Meta approvals, complete controlled integration acceptance, decide recovery/email-verification policy, and review privacy/terms and IP provenance. Browser-readable session tokens, per-process limits, no automated retention and non-exhaustive security/load testing remain disclosed risks.

The current free infrastructure can support a demo or disclosed source-code sale; do not advertise guaranteed uptime, unrestricted AI quota, approved social delivery, verified Google login or 10/10 completeness. No permissions were broadened, no paid resources created, and no customer messages sent.
