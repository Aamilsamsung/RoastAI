# User-owned social connections and autonomous replies

## What changed

Signed-in Google/password users have their own bot enablement, emergency stop, preferences, connections, conversations and activity. Owner account 0 and its existing environment-configured integrations/history are preserved. Snapchat collaboration is still owner-only and requires its own approval.

Official Instagram OAuth, Facebook Page OAuth with explicit Page selection, and WhatsApp Business Embedded Signup are implemented. One connected account per platform per user is currently supported. Personal Instagram accounts, personal Facebook inboxes, ordinary WhatsApp accounts, WhatsApp Web and Snapchat friend-DM automation are not supported. The WhatsApp implementation is for Cloud API registration, not Business App coexistence-only onboarding.

Authorization, account identity and webhook subscription are verified before saving a connection. Tokens are encrypted on the backend using Fernet with a key derived from a random encryption secret. They are not returned to browsers, saved in browser storage, or written to application logs. Single-use, ten-minute OAuth states bind callbacks to the authenticated account. Facebook candidate Page tokens remain encrypted and expire after ten minutes. One platform account cannot be attached to multiple RoastAI workspaces, and legacy owner accounts cannot be claimed by personal users.

Signed incoming webhook events route by registered account ID to the corresponding user. Conversation IDs include the connected account ID. Event deduplication is stable across reconnects. The worker uses that user's saved voice, languages and controls, applies generation/cooldown limits, and checks authorization, stop state and messaging age before replying. Events older than 23 hours are not processed for automatic replies. Ambiguous sends are marked failed/uncertain and never retried blindly.

## Backend environment on Render

Add these to **roastai-backend**, never the frontend:

| Variable | Value | Secret? |
|---|---|---|
| BACKEND_URL | `https://roastai-backend-ir7y.onrender.com` | No |
| FRONTEND_URL | `https://roastai-frontend.onrender.com` | No |
| SOCIAL_TOKEN_ENCRYPTION_KEY | Random, at least 32 characters; preserve across deployments | **Yes** |
| INSTAGRAM_CLIENT_ID | Instagram product's app/client ID | No |
| INSTAGRAM_CLIENT_SECRET | Instagram product's app secret | **Yes** |
| META_APP_ID | Meta app ID for Facebook/WhatsApp onboarding | No |
| META_APP_SECRET | Corresponding Meta app secret | **Yes** |
| META_VERIFY_TOKEN | Random verification secret used in the Meta webhook dashboard | **Yes** |
| FACEBOOK_LOGIN_CONFIG_ID | Optional Facebook Login for Business configuration ID | No |
| WHATSAPP_SIGNUP_CONFIG_ID | WhatsApp Embedded Signup configuration ID | No |
| INSTAGRAM_API_VERSION | `v23.0` or a supported version configured for your app | No |
| FACEBOOK_API_VERSION | `v23.0` or a supported version configured for your app | No |
| WHATSAPP_API_VERSION | `v23.0` or a supported version configured for your app | No |
| SOCIAL_DELIVERY_APPROVED | Keep `false` until controlled delivery tests are authorized and pass | No |
| DRY_RUN | Keep `true` for rollout | No |

For a new Blueprint installation, Render generates SOCIAL_TOKEN_ENCRYPTION_KEY. For the existing manual services, add a random secret in the Render dashboard. You can generate it locally with `python -c "import secrets; print(secrets.token_urlsafe(32))"`; save it directly in your secret manager/Render, not chat or Git. Changing or losing it makes existing saved social tokens unreadable. Back it up separately from encrypted database backups. Reconnect accounts after any necessary key replacement; no automatic destructive token migration is performed.

The new variables are not automatically created by pushing source code to the existing manual services. All credential-related fields remain blank in repository templates. GOOGLE_CLIENT_ID is unrelated to Meta credentials and remains configured separately.

## Meta application setup

Create/configure your app at https://developers.facebook.com/apps/ using the relevant business messaging products. Complete the business verification/App Review/Advanced Access required for connecting customer-owned accounts outside your app's developer/tester roles. Publish real privacy, data-deletion and support policies as required by Meta; this deployment does not invent legal policy URLs.

### Instagram

Configure the Instagram Login product and these permissions:
- `instagram_business_basic`
- `instagram_business_manage_messages`

Register the exact valid OAuth redirect URI:
`https://roastai-backend-ir7y.onrender.com/oauth/instagram/callback`

Add the webhook callback `https://roastai-backend-ir7y.onrender.com/webhook/meta` with the configured verification token; configure message subscriptions. Use the Instagram product's app ID/secret for INSTAGRAM_CLIENT_ID/INSTAGRAM_CLIENT_SECRET. The app validates Instagram webhook HMAC signatures with this secret, while preserving the legacy META_APP_SECRET signature path.

Users log into RoastAI, open Platforms, choose Connect Instagram and confirm the consent. They authorize a Business/Creator account at Instagram; authorization exchange, long-lived token exchange, identity check and webhook subscription occur server-side. Missing/declined permissions or failed subscription never appear as a successful connection. Long-lived token expiry is shown; reconnect before expiry. Automatic refresh is not implemented yet.

### Facebook Messenger

Configure Facebook Login or Facebook Login for Business with these approved permissions:
- `pages_show_list`
- `pages_messaging`
- `pages_manage_metadata`

Register `https://roastai-backend-ir7y.onrender.com/oauth/facebook/callback` as a valid OAuth redirect URI. Configure Page message webhooks at the shared callback above.

Users authorize at Facebook, return to Platforms, then explicitly choose their Page. Only Pages returned by Meta for their access token with a messaging/management task become candidates; candidate IDs are private to their RoastAI account. No Page token is returned to the browser. Page subscription must succeed before connection is stored. Currently the first 100 returned Pages are supported. Reconnect when authorization expires.

### WhatsApp Business

Configure WhatsApp Business Cloud API and Facebook Login for Business **Embedded Signup** for your Tech Provider/customer onboarding setup. Set its configuration ID in WHATSAPP_SIGNUP_CONFIG_ID. Enable the frontend origin `https://roastai-frontend.onrender.com` in the Meta app's JavaScript SDK/allowed-domain settings and configure the shared webhook.

Required approved token permissions:
- `whatsapp_business_management`
- `whatsapp_business_messaging`

Users open Connect WhatsApp Business, enter the business number's six-digit registration/two-step-verification PIN, and continue through Meta's official signup. The PIN is transient and is never saved. Browser messages are accepted only from the Facebook SDK origins. The backend verifies one-use owner-bound state, token app ID, validity and scopes, then confirms phone-number membership in the authorized WABA. Registration and WABA webhook subscription must both be acknowledged before saving the encrypted token. No customer messages are sent during connection. Registration/subscription are external account changes explicitly described in the consent UI. Coexistence-only/incomplete signups are rejected rather than simulated.

## Controlled acceptance before enabling live delivery

No live sends have been enabled or performed by this build. Configuration presence does not establish App Review approval or successful customer delivery.

1. Use dedicated test Business/Creator accounts, a test Page and a test WhatsApp business number with app roles/approved permissions.
2. Complete each actual OAuth/Embedded Signup; verify the right account label and Page/phone ownership.
3. Have a permitted tester send an incoming message to the connected account. Keep global approval false and dry-run true.
4. Confirm that only the intended RoastAI user sees its conversation, incoming message, generated dry-run reply and activity. Confirm another user sees none of them.
5. Exercise bot pause, emergency stop, disconnect, expiry, duplicate webhook delivery and a delayed event. Verify no unintended AI call or delivery occurs.
6. Ask the operator for explicit approval before changing SOCIAL_DELIVERY_APPROVED or sending a controlled test reply. Platform messaging windows and policies still apply.
7. Confirm provider acceptance and actual receipt with the tester; review revoked permissions and failure handling before onboarding customers.

Disconnect removes local tokens, pauses the user's bot and cancels queued work. It does not revoke provider-side authorization; the user must remove the app in their platform settings to revoke it there. Already submitted messages cannot be recalled. Replacing a connection cancels jobs tied to its old connection ID and retains all history.

## Deployment and remaining boundaries

Migration 0005 only adds social connection/state/candidate tables. It does not drop or overwrite existing user data. Existing PostgreSQL backups should now include these tables; restoration also needs the original encryption secret.

The process still has a single elected queue worker. Free Render web services can sleep, so webhook response times and autonomous processing are not guaranteed continuously available. For a commercial automation service, provision durable PostgreSQL beyond the current free database expiry, always-on compute and measured queue monitoring; do not upgrade paid resources without authorization.

OAuth/live delivery with real Meta credentials, App Review, physical-device SDK behavior, large account inventories, automatic token refresh, provider-side revocation, and business-account deletion callbacks remain external acceptance/operational work. Repository tests use labelled provider fixtures; they do not prove Meta approval or real delivery.

Official references:
- https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/
- https://www.postman.com/meta/messenger-platform-api/documentation/iyp204x/messenger-platform-api
- https://github.com/fbsamples/business-messaging-sample-tech-provider-app
