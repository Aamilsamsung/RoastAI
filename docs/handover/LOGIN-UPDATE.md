# Account entry and Google sign-in

The brown, ivory and black login page now has separate account tabs, a mobile layout, visible labels, password visibility controls, persistent errors, disabled submission controls and a secondary owner-access path. Google Identity Services uses the existing server-verified audience, issuer, verified email and one-use nonce flow. Challenges refresh after four minutes when verification is idle; duplicate Google callbacks are ignored.

## Activate Google

1. Configure the OAuth consent screen in Google Cloud Console and create a **Web application** OAuth client.
2. Add `https://roastai-frontend.onrender.com` to Authorized JavaScript origins. Add your custom frontend origin if applicable; local development can use `http://localhost:3000`.
3. Set `GOOGLE_CLIENT_ID` on the **backend** Render service to the public client ID ending in `.apps.googleusercontent.com`. Save and allow deployment to finish.
4. Publish the consent screen or add permitted test users while in testing mode. Verify real Google sign-in in your browser.

The ID is public configuration, not an API key. Do not send passwords, client secrets or tokens in chat. No Google client secret or redirect URI is needed for this GIS popup ID-token flow. Existing password users sign in first, then link their matching Google account in Settings; accounts are not silently linked by matching email alone.

Google is integrated but remains unavailable until this external configuration exists. Actual Google account sign-in is not claimed as verified without it.

Instagram Login targets professional Business/Creator account integrations. Google was selected for general account authentication; no misleading Instagram sign-in button was added.

Official references:
- https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid
- https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/

## Validation

Next.js production build and TypeScript check passed. The local headless Chromium suite passed 50 checks, including 10 login/Google UI checks and the 40 existing workflow checks. Google identity verification was a labelled local test double; a real Google account sign-in remains blocked by missing client configuration. Phone widths 320, 390 and 720 pixels were checked for overflow.
