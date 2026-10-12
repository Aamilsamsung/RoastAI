# Cost model — no invented usage

Observed deployment: two free Render web services and a free PostgreSQL instance. Fixed hosting charges are currently zero, with sleeping services and expiring database limitations. No paid resources were provisioned. Permanent production hosting/database pricing must be confirmed at purchase time.

Configured source default: gemini-3.8-flash. Actual runtime model is included in the new provider status/usage diagnostics; confirm it from deployed evidence. Google's official standard pricing on 2026-10-12 lists USD $0.75 per million input tokens and $3.75 per million output tokens including thinking through 2026-12-31; from 2027-01-01 those become $1.50 and $7.50. Free-tier usage is free within project eligibility/limits. Source: https://ai.google.dev/gemini-api/docs/pricing . No grounding, cache, tools or images are requested by RoastAI.

Use measured SDK counters, not visible reply characters:

`monthly AI USD = N * (mean_input_tokens * 0.75 + (mean_output_tokens + mean_thinking_tokens) * 3.75) / 1,000,000`

The new usage object records input, visible output, thinking and total tokens plus attempts. Missing counters remain unknown. Failed/timeout attempts may incur upstream usage not returned to the app; Google billing is authoritative. Budget a retry allowance separately. The 1536 output cap includes model reasoning budget effects; it is not measured average usage.

No successful live generation had been measured at the start of this audit. The reproducible baseline failed with HTTP 502 after 14.957 seconds. Until a successful sample is captured, a measured monthly cost is BLOCKED.

Illustration only: 10,000 successful requests at 500 input tokens and 300 output+thinking tokens cost $15.00 at current standard paid rates, before retries/hosting/taxes/Meta messaging fees. This is an assumption, not observed RoastAI usage. Multiply by your actual completed usage sample and expected volume. Configure Google project quotas/budget alerts; public signup shares the owner's AI quota. Meta fees and commercial onboarding restrictions depend on account, geography and provider terms and must be reviewed separately.
