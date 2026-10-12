# Cost model — no invented usage

Observed deployment: two free Render web services and a free PostgreSQL instance. Fixed hosting charges are currently zero, with sleeping services and expiring database limitations. No paid resources were provisioned. Permanent production hosting/database pricing must be confirmed at purchase time.

Configured source default and tested runtime: gemini-3.5-flash-lite. Gemini 3.8 Flash returned 503; the same credentials succeeded with Flash-Lite. Flash-Lite standard pricing is $0.30 per million input tokens and $2.50 per million output tokens including thinking. The following original 3.8 pricing is included only as an alternative-model comparison. Actual runtime model is included in the new provider status/usage diagnostics; confirm it from deployed evidence. Google's official standard pricing on 2026-10-12 lists USD $0.75 per million input tokens and $3.75 per million output tokens including thinking through 2026-12-31; from 2027-01-01 those become $1.50 and $7.50. Free-tier usage is free within project eligibility/limits. Source: https://ai.google.dev/gemini-api/docs/pricing . No grounding, cache, tools or images are requested by RoastAI.

Use measured SDK counters, not visible reply characters:

`monthly AI USD = N * (mean_input_tokens * 0.30 + (mean_output_tokens + mean_thinking_tokens) * 2.50) / 1,000,000`

The new usage object records input, visible output, thinking and total tokens plus attempts. Missing counters remain unknown. Failed/timeout attempts may incur upstream usage not returned to the app; Google billing is authoritative. Budget a retry allowance separately. The 1536 output cap includes model reasoning budget effects; it is not measured average usage.

At the start of this audit no successful generation had been measured. The first repaired live Flash-Lite request succeeded: provider 3400 ms, backend 3515 ms, test-client wall 10.520 s; 219 input, 33 visible output and 393 thinking tokens (645 total), one attempt. Standard paid equivalent $0.0011307 per request, or $11.307 per 10,000 identical-usage requests. This initial low-thinking sample is not a representative average; later minimal-thinking samples should be used for budgeting. The reproducible baseline failed with HTTP 502 after 14.957 seconds. Actual monthly traffic and Google billing tier remain unknown; these are paid-equivalent estimates, not a bill or SLA.

Illustration only: 10,000 successful requests at 500 input tokens and 300 output+thinking tokens cost $9.00 at Flash-Lite standard paid rates, before retries/hosting/taxes/Meta messaging fees. This is an assumption, not observed RoastAI usage. Multiply by your actual completed usage sample and expected volume. Configure Google project quotas/budget alerts; public signup shares the owner's AI quota. Meta fees and commercial onboarding restrictions depend on account, geography and provider terms and must be reviewed separately.

## Measured minimal-thinking smoke run

46 successful safe-prompt cases recorded mean input 211.33 tokens and mean total 256.54 tokens. Returned billable output inferred from total minus input averaged 45.22 tokens; SDK thoughts_token_count was absent, not invented as zero. At $0.30/$2.50 per million tokens, paid-equivalent cost is approximately $0.00017644 per successful request, or $1.76 per 10,000 requests with identical average usage. This uses short, fresh conversations; real long histories/custom voice raise input usage. Initial faster/failed quota tests are retained separately. Prompt calibration changed afterward and needs final measurements. Free-tier eligibility and billing remain project-dependent.

## Final calibrated prompt measurement

12 production cases after calibration passed: nine modes, intensity endpoints and custom voice. Mean input 290.42 tokens; billable output inferred from total minus input 38.17 tokens. Median AI stage 1.083 seconds; pooled-client median end-to-end 1.476 seconds (range 1.309–2.917). Paid-equivalent $0.00018254 per request, or approximately $1.83 per 10,000 identical-usage successful requests. This excludes failed/ambiguous attempts, longer histories, hosting, tax and integration costs. It is not a monthly bill or an uptime/latency guarantee. See FINAL-LATENCY-COST.json.
