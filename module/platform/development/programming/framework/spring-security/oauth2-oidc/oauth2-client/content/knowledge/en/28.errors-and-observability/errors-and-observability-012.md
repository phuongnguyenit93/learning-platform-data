# 28.12. Step-by-Step Troubleshooting Workflow for the OAuth/OIDC Flow

## 1. Diagnostic Mindset: Identify the First Failing Step

In a **Spring Security OAuth 2.0 OIDC Client** application, messages like "Unable to sign in", "Unable to retrieve token", "Insufficient permissions", or "Session lost" are merely outward symptoms. The true root cause may lie in `ClientRegistration`, browser redirects, the authorization request, the Token Endpoint, ID Token verification, UserInfo, authority mapping, the session store, the Resource Server, or the refresh token.

Do not start by disabling CSRF or elevating client permissions. Answer three questions instead:

1. **How far did the flow get?** Did it redirect to the OpenID Provider (OP)? Did the callback reach the RP? Was the Token Endpoint called?
2. **Where was the first failing step?** Find an HTTP status, OAuth error code, or Spring Security event with confirming evidence.
3. **What category is the error?** Misconfiguration, session/identity correlation mismatch, provider authorization refusal, cryptographic/signature failure, Resource Server permission, or temporary outage?

For example, two situations both show `/login?error`:

~~~text
Scenario A
  Browser -> OP -> callback RP
  RP cannot find the authorization request in session
  => State/session/cookie error, HAS NOT reached Token Endpoint yet

Scenario B
  Browser -> OP -> callback RP
  RP sends code + code_verifier to Token Endpoint
  OP returns invalid_client
  => Client authentication/registration error
~~~

Fixing the client secret does not help Scenario A; adjusting `SameSite` cookies does not help Scenario B. Therefore, diagnostics must follow **chronological order and component boundaries**.

### Lesson Objectives

After this lesson, you will be able to:

- Read the complete map of Authorization Code + OIDC Login, from `/oauth2/authorization/{registrationId}` to API requests.
- Distinguish errors across `state`, PKCE, `redirect_uri`, `invalid_grant`, `invalid_client`, `iss`, `aud`, `nonce`, JWKS, and UserInfo.
- Understand why login succeeds yet HTTP 401/403 still occurs, or why the browser keeps losing its session.
- Pinpoint issues with access tokens, refresh tokens, Resource Servers, Session/Authorized Client Stores, and logout.
- Collect logs, metrics, and traces **without recording raw tokens, codes, client secrets, or cookies**.
- Write runbooks, checklists, integration tests, and escalation paths suitable for both Servlet and Reactive applications.

> **Scope:** This lesson focuses on Spring Security OAuth2 Client/OIDC Login, especially Authorization Code Flow with PKCE. Specific APIs/Javadoc depend on the Spring Security and Spring Boot version branch in use. Never run tests using real production tokens or ask users to paste passwords/ID Tokens into tickets.

## 2. End-to-End Flow Map

~~~mermaid
sequenceDiagram
    autonumber
    actor Browser
    participant RP as Spring Boot OAuth2/OIDC Client
    participant Store as Session / Authorized Client Store
    participant OP as OpenID Provider
    participant UI as UserInfo Endpoint
    participant API as Resource Server
    Browser->>RP: GET /private
    RP-->>Browser: Redirect to login
    Browser->>RP: GET /oauth2/authorization/company
    RP->>Store: Save authorization request, state, nonce, and PKCE verifier
    RP-->>Browser: 302 to OP Authorization Endpoint
    Browser->>OP: Authorization Request + code_challenge
    OP-->>Browser: Login / consent / MFA
    OP-->>Browser: Redirect callback: code + state
    Browser->>RP: GET /login/oauth2/code/company
    RP->>Store: Load authorization request, verify state
    RP->>OP: POST Token Endpoint: code, client auth, code_verifier
    OP-->>RP: ID Token, Access Token, optional Refresh Token
    RP->>RP: Validate ID Token signature, iss, aud, exp, nonce
    opt UserInfo required
        RP->>UI: Bearer Access Token
        UI-->>RP: UserInfo claims
        RP->>RP: UserInfo sub MUST match ID Token sub
    end
    RP->>Store: Save Authentication + Authorized Client
    RP-->>Browser: Session cookie + success redirect
    Browser->>RP: GET /private + session cookie
    RP->>Store: Restore SecurityContext
    RP->>API: Send right Access Token to API
    API-->>RP: 200, 401, 403 or 5xx
~~~

### 2.1. Quick Diagnostic Table

| Stage | Expected input/output | Errors to look for |
| --- | --- | --- |
| 0. Security filter | Protected URL initiates login | Matcher, chain ordering, entry point |
| 1. Registration | Correct provider/client ID | Issuer, client secret, redirect, scopes |
| 2. Login initiation | 302 to Authorization Endpoint | Wrong `registrationId`, missing state/PKCE |
| 3. OP authorization | User login/consent, redirects with code | `access_denied`, `login_required`, `invalid_scope` |
| 4. Callback | Code + state reach the right RP | Session/cookie, state mismatch, proxy |
| 5. Token exchange | Access Token + ID Token | `invalid_grant`, `invalid_client`, PKCE, outage |
| 6. ID Token validation | OIDC principal verified | JWT signature/JWKS, `iss`, `aud`, `nonce`, clock |
| 7. UserInfo | Claim `sub` matches ID Token | 401/403, missing claims, subject mismatch |
| 8. Authorization | `OidcUser` and authorities | Role mapping, tenant policy, CSRF |
| 9. Persistence | Session and authorized client saved | Cookie, Redis/JDBC, multi-node, principal key |
| 10. API call | Bearer token matches resource | 401 `invalid_token`, 403 scope/ACL, 503 |
| 11. Refresh | New token saved properly | `invalid_grant`, rotation race, failure handler |
| 12. Logout | RP/OP sessions handled properly | `end_session_endpoint`, back-channel, revocation |

## 3. Collecting Evidence Without Leaking Credentials

This information is usually sufficient to pinpoint where failure occurred:

~~~text
timestamp_utc=2026-11-16T03:30:00Z
environment=staging
application_version=build-2026-11-16
registration_id=company
provider_alias=company-oidc
stage=token_exchange
error_code=invalid_grant
http_status=400
correlation_id=diag-7e2d
duration_ms=430
~~~

This is an illustrative format, **not a default log format**.

### 3.1. Do not log the following fields

- Access Token, Refresh Token, ID Token, client secret, private keys.
- Raw values of authorization code, PKCE `code_verifier`, OAuth2 `state`, or OIDC `nonce`.
- `Authorization` header, `Cookie`, `Set-Cookie`, CSRF tokens, Bearer tokens in URLs.
- Raw Token Endpoint request/response, full UserInfo payload, or serialized `OAuth2AuthorizedClient`.
- Session IDs, Back-Channel Logout Tokens, complete exception traces containing request parameters.

Such details may appear in HAR files, browser DevTools, reverse proxy logs, APM, and debugging tools. Never post an unredacted HAR file to a ticket or public chat. If needed for investigation, sanitize it and retain only metadata under appropriate access controls.

### 3.2. Minimum evidence

| Field | Example |
| --- | --- |
| UTC timestamp and timezone | Correlate events across RP/OP/API |
| Environment/region/pod | Distinguish one node vs. the whole system |
| Build and dependency versions | Detect deployment changes |
| `registrationId` | Identify the exact `ClientRegistration` |
| Failing stage | callback/token/id_token/userinfo/api/refresh |
| HTTP status/error code | Without logging tokens/bodies |
| Correlation ID | Internal ID containing no OAuth state |
| Provider incident/case ID | If the OP has a status page or support ticket |
| Browser/session mode | Container session, Spring Session, Redis |
| Blast radius | Single user/tenant/provider or all |

### 3.3. Things never to do as a "quick fix"

~~~text
State mismatch       -> DO NOT disable state validation
Wrong PKCE verifier  -> DO NOT remove PKCE
JWT signature fail   -> DO NOT accept unsigned JWTs
Issuer mismatch      -> DO NOT rewrite the iss string in the token
TLS error            -> DO NOT disable certificate validation
CSRF 403             -> DO NOT disable CSRF system-wide
API 403              -> DO NOT switch to an admin client automatically
OP 503               -> DO NOT delete all Refresh Tokens
~~~

## 4. Step 0 — Rapid Isolation Before Changing Configuration

Ask questions in order:

1. Does the error occur **before login**, **after login**, during **refresh**, or during **logout**?
2. All users or a single user?
3. All providers or a single `registrationId`?
4. All instances or a single pod/region?
5. Were there any recent changes to domains, proxies, cookies, client secrets, issuers, JWKS, or scopes?
6. Did the browser reach the OP? Did the OP redirect back to the callback?
7. Was the Token Endpoint called?
8. Is the provider experiencing an ongoing incident or rate limit?

| Scope | Investigation priority |
| --- | --- |
| Single user | Consent revoked, account/tenant policy, session |
| Single browser | Cookies, `SameSite`, extensions, stale login tab |
| Single provider | Client registration, OP outage, scopes/secret |
| Single pod | NTP/time skew, container config, session, truststore |
| System-wide after deploy | `SecurityFilterChain`, proxy/base URL, dependencies |
| After scale-out | Shared session/authorization request store, pod affinity |
| After secret rotation | Old/new client credentials, pod rollout |
| After OP key rotation | JWKS cache/`kid`, issuer |

Do not turn this table into an automatic conclusion; use it to order your checks.

## 5. Step 1 — Check ClientRegistration and Discovery

An example Servlet OIDC configuration:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
        provider:
          company-oidc:
            issuer-uri: https://id.example.net/realms/company
~~~

This is a placeholder configuration. `company` is the `registrationId`, `company-oidc` is the provider config key, and `OIDC_CLIENT_ID` is the client ID issued by the OP.

### 5.1. Checklist

| Property | Check |
| --- | --- |
| Registration ID | Matches login initiation URL/callback |
| Client ID | Matches the right OP client and tenant |
| Secret/private key | Correct version, not revoked, not leaked in logs |
| Client authentication method | OP accepts Basic, `private_key_jwt`, mTLS, etc. |
| Grant type | `authorization_code` for OIDC Login |
| Redirect URI | Exact match with the URI at the OP |
| Scopes | Includes `openid`; other scopes match contract |
| Issuer URI | Exact match with the OP's `iss` |
| Authorization/Token Endpoint | From trusted metadata, not guessed |
| JWKS URI | Issuer's signing keys |
| UserInfo URI | Present or not; right provider |

### 5.2. Discovery Metadata

An OIDC provider typically exposes a Discovery endpoint corresponding to the issuer, for example:

~~~text
https://id.example.net/realms/company/.well-known/openid-configuration
~~~

Illustrative payload:

~~~json
{
  "issuer": "https://id.example.net/realms/company",
  "authorization_endpoint": "https://id.example.net/realms/company/authorize",
  "token_endpoint": "https://id.example.net/realms/company/token",
  "jwks_uri": "https://id.example.net/realms/company/jwks",
  "userinfo_endpoint": "https://id.example.net/realms/company/userinfo"
}
~~~

If Discovery returns 404/timeout/TLS failure, inspect the issuer path, DNS, proxy, truststore, and OP status. **Never allow user requests to pick an arbitrary JWKS URL**, as that can turn metadata loading into SSRF or accept attacker-signed JWTs.

### 5.3. Issuer must be an exact trust boundary

~~~text
Configured issuer: https://id.example.net/realms/company
Token issuer:      https://id.example.net/realms/partner

=> Different issuer; the token must be rejected.
~~~

Do not use `contains("example.net")` or alter `iss` via string replacement.

## 6. Step 2 — Did the Browser Start the Authorization Flow Properly?

Default login initiation in Spring Security Servlet:

~~~text
GET /oauth2/authorization/company
~~~

Expected HTTP 302 to the Authorization Endpoint, with parameters:

~~~text
response_type=code
client_id=...
redirect_uri=...
scope=openid ...
state=...
code_challenge=...
code_challenge_method=S256
nonce=... (depending on OIDC flow/config)
~~~

### 6.1. If login initiation returns 404

- Does `company` exist in `ClientRegistrationRepository`?
- Is Spring Security `oauth2Login()` configured?
- Which `SecurityFilterChain` matches the URL?
- Is there a custom `authorizationEndpoint().baseUri(...)`?
- Is the reverse proxy stripping/adding path prefixes properly?

### 6.2. If it redirects to the RP login page instead of the OP

The browser may be hitting a protected route and the entry point is sending it to a custom `/login`. Inspect **the entire redirect chain**, not just the final URL.

### 6.3. If the OP rejects the request immediately

Check the OP's safe error code:

| Error | Investigation direction |
| --- | --- |
| `invalid_client` | Client ID/registration |
| `invalid_scope` | Scope/consent/permission |
| `invalid_request` | Missing/invalid parameter |
| `unauthorized_client` | Grant/client policy |
| `redirect_uri_mismatch` (provider-specific) | Public URL vs. registered URI |

Do not request broad admin permissions just to "get past" an `invalid_scope`.

## 7. Step 3 — Redirect URI and Reverse Proxy

A common topology:

~~~text
Browser:
  https://portal.example.net

Reverse Proxy:
  HTTPS public -> http://app:8080 internal

RP authorization request redirect_uri:
  https://portal.example.net/login/oauth2/code/company

Registered redirect URI at OP:
  https://portal.example.net/login/oauth2/code/company
~~~

If the RP sends `http://app:8080/login/oauth2/code/company`, the OP may return `redirect_uri_mismatch`.

### 7.1. Symptoms

- Scheme `http` instead of `https`.
- Internal host instead of public host.
- Missing or extra path prefix.
- Wrong port.
- Trailing slash or URL encoding mismatch.
- Callback redirect loop between HTTP and HTTPS.

### 7.2. Forwarded headers

Spring Boot has configuration for trusted proxy forwarding:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

This is only an **infrastructure-dependent configuration example**. The proxy must strip spoofed `Forwarded`/`X-Forwarded-*` headers sent by browsers and supply only trusted values. Never trust arbitrary `X-Forwarded-Host` headers from the internet, or you risk host spoofing/open redirects.

### 7.3. Exact redirect URI

Any mismatch in the following parts can cause the OP to reject the request:

~~~text
scheme | hostname | port | path | trailing slash
~~~

Do not open broad wildcard redirects just to work around configuration issues. Fix the URI to match the exact public route and register it on the proper client/OP.

## 8. Step 4 — Did OP Authentication and Consent Complete?

At the OP, the user may encounter MFA, conditional access, account lockouts, tenant policies, or consent screens. Some errors occur directly on the OP page; the RP **has not received a callback yet** and cannot log a failure event.

| OP error | Common cause | Action |
| --- | --- | --- |
| `access_denied` | User declined or OP policy blocked | Respect the denial |
| `login_required` | No SSO session during silent login | Prompt for interactive login |
| `consent_required` | Consent not granted yet | Use an approved consent flow |
| `interaction_required` | OP requires user interaction | Open a valid interactive flow |
| `invalid_scope` | Wrong/disallowed scope | Fix registration/scopes |
| `temporarily_unavailable` | Temporary OP error | Degrade gracefully and retry appropriately |

### 8.1. Inspect the callback path instead of collecting raw HARs

Browser DevTools can show:

- Did the OP redirect back to the RP?
- Was the callback HTTP status 200/302/400/404?
- Was the cookie sent or blocked due to `SameSite`/`Secure`/`Domain`?
- Did the reverse proxy rewrite the path?

Never upload a HAR containing `code`, `state`, cookies, or tokens. Use sanitized evidence.

## 9. Step 5 — Callback, State, and Authorization Request Repository

Default callback:

~~~text
GET /login/oauth2/code/company?code=...&state=...
~~~

The RP must load the corresponding authorization request and verify `state` before exchanging the authorization code. In default Servlet setups, the authorization request is usually stored in the HTTP session.

### 9.1. Callback 404

Check the callback matcher, `SecurityFilterChain`, OP registered URI, proxy rewrites, `registrationId`, and custom redirection base URI.

### 9.2. State mismatch / authorization request not found

Causes:

- Browser did not send the RP session cookie.
- Misconfigured `SameSite`/`Secure`/`Domain`/`Path` cookie attributes.
- Session timed out while the user completed MFA/consent.
- Login started on Node A, callback hit Node B without the session.
- Browser had multiple tabs/attempts and an old callback was replayed.
- Custom `AuthorizationRequestRepository` or session serialization bug.
- User started login on one domain and the callback landed on a different domain.

**Do not disable state validation.** `state` protects correlation, login CSRF, and mix-up mitigation.

### 9.3. State is distinct from nonce

- `state`: binds the authorization response to the original request, mitigating CSRF/mix-up.
- `nonce`: binds the ID Token to the OIDC authentication request per flow/policy.
- `code_verifier`: secret used at the Token Endpoint to prove PKCE possession.

Never substitute these three values for one another or log their raw values.

## 10. Step 6 — PKCE and the Token Endpoint

Authorization Code Flow with PKCE:

~~~text
RP generates high-entropy code_verifier
    |
    +-> code_challenge = BASE64URL(SHA256(code_verifier))
    |
    +-> Sends code_challenge in authorization request
    |
OP returns code at callback
    |
RP sends the same code_verifier to Token Endpoint
    |
OP verifies challenge/verifier and grant
~~~

Illustrative HTTP POST:

~~~http
POST /oauth2/token HTTP/1.1
Host: id.example.net
Content-Type: application/x-www-form-urlencoded
Authorization: Basic REDACTED_CLIENT_AUTH

grant_type=authorization_code&
code=REDACTED_CODE&
redirect_uri=https%3A%2F%2Fportal.example.net%2Flogin%2Foauth2%2Fcode%2Fcompany&
code_verifier=REDACTED_VERIFIER
~~~

The authentication method may be `client_secret_basic`, `private_key_jwt`, mTLS, or another mechanism matching the client registration; do not assume every OP uses Basic.

### 10.1. Token Endpoint `invalid_grant`

Causes:

- Code expired or already used.
- Code was issued to a different client.
- `redirect_uri` does not match the authorization request.
- PKCE `code_verifier` is wrong or missing.
- OP revoked/invalidated the grant.
- Callback was sent twice.

Always identify the **grant type**. `invalid_grant` during authorization code exchange is different from `invalid_grant` during refresh token exchange.

### 10.2. Token Endpoint `invalid_client`

Check client ID, secret rotation, private key/certificate, client authentication method, tenant/realm, deployment pods still holding an old secret, secret manager sync, and clock skew when using JWT client assertions.

Do not infinitely retry rejected credentials.

### 10.3. 429, 502/503/504, and timeouts

These may be transient OP/network failures. Use bounded retries, `Retry-After`, backoff, and jitter. However, an Authorization Code is **single-use**: if a timeout occurs after the OP already processed the code, retrying may return `invalid_grant`. Do not resend the code indefinitely; starting a fresh flow may be required.

### 10.4. Token response contents

OIDC Authorization Code Login typically requires:

~~~text
access_token = present
token_type = Bearer (if using Bearer)
id_token = present
expires_in = expiry duration
refresh_token = optional
scope = actual granted scopes (if present in response)
~~~

Do not assume the OP issues a Refresh Token solely because `offline_access` was in the requested scope.

## 11. Step 7 — ID Token Validation

The RP only accepts OIDC Authentication when the ID Token satisfies all constraints:

| Constraint | Cause when failing |
| --- | --- |
| JWS signature and allowed algorithm | Wrong key/alg/signature |
| `kid` from trusted JWKS | Stale JWKS cache or key rotation |
| Exact `iss` match | Wrong issuer/tenant/realm |
| `aud` contains client ID | Token intended for another client |
| `azp` when conditionally required | Authorized party mismatch |
| `exp`/`iat` | Expired, clock skew |
| `nonce` if used | Does not match authentication request |
| `auth_time`, `at_hash`, `c_hash` when applicable | Flow/policy condition not met |

### 11.1. JWT signature fails after JWKS rotation

~~~text
ID Token header: kid=op-key-new
RP JWKS cache:   op-key-old
~~~

Check the trusted issuer, JWKS URI, key rotation announcement, key cache refresh, TLS, proxy, NTP, and configuration drift across pods. Never accept `alg=none`, bypass signature validation, or fetch keys from arbitrary `jku`/`x5u` JWT header URLs.

### 11.2. Issuer vs. audience mismatch

~~~text
registrationId = company
clientId = portal-web
Configured issuer = https://id.example.net/realms/company
ID Token iss = https://id.example.net/realms/partner
ID Token aud = reports-api

=> Do not accept this token as an OIDC login for portal-web.
~~~

The `aud` of an ID Token is the **client ID**, not the Spring `registrationId`. Do not treat an Access Token for Reports API as an ID Token for Portal.

### 11.3. Clock skew

A pod with significant clock drift can treat valid `exp` timestamps as expired or `iat` timestamps as in the future. Check NTP, UTC, epoch seconds, and a tight clock-skew policy. Do not arbitrarily extend expired tokens.

### 11.4. Nonce mismatch

If `nonce` does not match, investigate login attempt/session correlation, stale tabs, custom provider flows, or token substitution. Never disable nonce verification.

## 12. Step 8 — UserInfo Endpoint and `sub` Equality

UserInfo is a protected endpoint; the RP uses the Access Token to retrieve additional claims when supported by the OP and required by framework/config.

~~~http
GET /userinfo HTTP/1.1
Host: id.example.net
Authorization: Bearer REDACTED_ACCESS_TOKEN
~~~

| Symptom | Check |
| --- | --- |
| 401 | Invalid Access Token / wrong issuer/audience |
| 403 | Insufficient scope/policy |
| 5xx/timeout | UserInfo outage |
| Missing `email` claim | Privacy, consent, or data absent |
| `sub` differs from ID Token | Token substitution/mix-up; reject UserInfo |
| Invalid response format | OP contract, signed/encrypted UserInfo |

### 12.1. Mandatory OIDC Core rule

`sub` in the UserInfo response **MUST exactly match** `sub` in the ID Token.

~~~text
ID Token: sub = alice-123
UserInfo: sub = bob-456

=> Claims from the UserInfo response must not be used.
~~~

Never assume two users are the same person solely because their emails match.

### 12.2. Missing claims are not automatically protocol errors

Requesting `openid profile email` does not guarantee `email` is always returned. If email is required by business logic, handle verification UX or reject onboarding explicitly. Never force `email_verified=true` when the claim is absent.

## 13. Step 9 — Login Succeeded, Yet Authorization Fails

OIDC Login success only proves the user was authenticated by the OP and the RP accepted the OIDC protocol. It **does not grant admin privileges or API scopes**.

Points to verify:

- Internal account mapping uses **issuer + subject**, not email alone or raw `sub`.
- Does tenant policy reject the user?
- Does `GrantedAuthoritiesMapper`/`OidcUserService` map permitted roles correctly?
- Do `@PreAuthorize`, URL matchers, or ACLs expect a different role?
- Is an HTTP POST/PUT/DELETE missing a CSRF token?
- Is the 403 coming from the RP or a downstream Resource Server?

### 13.1. Authentication differs from authorization

~~~text
Authentication:
  ID Token validated -> user is Alice according to issuer A

Application authorization:
  Is Alice allowed to view tenant X's reports?

Resource Server authorization:
  Does the Access Token have audience/scope for Reports API?
~~~

Never blindly map an arbitrary provider claim `admin` to `ROLE_ADMIN`. Require trusted issuer + schema + allowlist policy.

### 13.2. RP HTTP 403 after POST

If GET works fine but POST returns 403, check CSRF before concluding roles are missing. Do not disable CSRF app-wide in production to test.

## 14. Step 10 — Session Cookie and SecurityContext

Common symptom: login callback succeeds, the browser lands on the application page, and the next request redirects back to login.

~~~text
Browser:
  Cookie: JSESSIONID=<redacted>

RP:
  HttpSession -> SecurityContext -> Authentication
~~~

WebFlux/Spring Session may use the `SESSION` cookie depending on configuration.

### 14.1. Checklist

1. Did the login response include `Set-Cookie`?
2. Did the browser accept the cookie, or reject it due to `Secure`/`SameSite`/`Domain`/`Path`?
3. Did the next request send the right cookie?
4. Does the HTTP session/`WebSession` exist?
5. Was the `SecurityContext` persisted?
6. Was the cookie rotated after authentication (normal session fixation protection)?
7. Did the callback hit a different node than the one that started login?
8. Is the Redis/JDBC session store shared and serializing properly?
9. Did the session TTL expire during prolonged user MFA/consent?
10. Did a filter or logout handler inadvertently invalidate the session right away?

### 14.2. SameSite and response mode

GET authorization callbacks and `form_post` callbacks can exhibit different cookie behavior. Check browser cookie exclusion reasons in DevTools and `SameSite`/`Secure` policy without logging raw cookie values.

### 14.3. Multi-instance

~~~text
Begin OAuth login -> Pod A holds authorization request
Callback         -> Pod B does not see state
Next request     -> Pod C does not see SecurityContext
~~~

A shared session store or sticky affinity architecture may be required. Never treat a single localhost login as proof that the flow works across multiple pods.

## 15. Step 11 — Authorized Client Store and Principal Key

Spring Security Servlet:

~~~text
OAuth2AuthorizedClientService
OAuth2AuthorizedClientRepository
~~~

Reactive:

~~~text
ReactiveOAuth2AuthorizedClientService
ServerOAuth2AuthorizedClientRepository
~~~

`OAuth2AuthorizedClient` holds the registration, principal, Access Token, and Refresh Token if issued; it is not synonymous with `HttpSession` even though it may sometimes be stored in the session.

### 15.1. When to suspect store issues?

- Login succeeds, but restarts lose the delegated connection.
- Token refresh succeeds, yet the next request still uses the old token.
- Background schedulers cannot find the user's token.
- One instance uses an in-memory store while another instance lacks the record.
- Saving used `sub` as the principal key while loading used email.
- A custom success handler fails to persist the new Refresh Token.
- Redis/JDBC failure prevents saving the authorization result.

### 15.2. Safe metadata to inspect

~~~text
registrationId=company
principalKeyAlias=internal-account-123
authorizedClientExists=true
accessTokenExpiryBucket=less_than_5_minutes
refreshTokenPresent=true
storeType=encrypted-jdbc
rowVersion=8
~~~

Never `SELECT` and print raw tokens into logs. With multiple providers, namespace the identity key by issuer/`sub` and tenant policy, not email alone.

## 16. Step 12 — Resource Server 401/403

A browser OIDC login can succeed at the RP while an API still rejects the Bearer Access Token.

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="reports.read"
~~~

| HTTP/API error | Common meaning | What to check |
| --- | --- | --- |
| 401 `invalid_token` | Expired, revoked, wrong issuer/`aud` | Access Token and Resource Server validation |
| 403 `insufficient_scope` | Missing required scope | Granted scopes/consent/Resource Server policy |
| 403 business ACL | User/tenant/entity unauthorized | Business authorization, not changing tokens |
| 404 | Route/resource missing or hidden | API path/domain/routing |
| 429 | Rate limit | `Retry-After`/backoff |
| 503 | API outage | Do not refresh Access Token infinitely |

### 16.1. Audience is the API boundary

An Access Token valid for UserInfo is not automatically valid for Reports API. Nor is an ID Token issued for the RP client usable as an API Bearer Token. Verify the right registration, requested/granted scopes, token audience, and receiving endpoint.

### 16.2. WebClient and the risk of sending tokens to the wrong host

Inspect `ServletOAuth2AuthorizedClientExchangeFilterFunction` or `ServerOAuth2AuthorizedClientExchangeFilterFunction`:

- Is the right `clientRegistrationId` or authorized client selected per request?
- Is a default OAuth2 Client attached to a `WebClient` that calls arbitrary URLs?
- Is the user/tenant authorized to use that token?
- Could an absolute URI/redirect cause the token to be sent to another host?
- Does the failure handler process Bearer errors properly?

Never accept a user-supplied URL and automatically attach an admin Bearer Token: that is an SSRF/token-exfiltration risk.

## 17. Step 13 — Refresh Token and `invalid_grant`

When an Access Token expires, the manager can refresh it if a Refresh Token is present and supported by the provider. `invalid_grant` here does not necessarily mean the same thing as `invalid_grant` during authorization code exchange.

### 17.1. Main causes

- Refresh Token expired or user revoked consent.
- Provider rotated the Refresh Token and a request reused the old token.
- Two concurrent requests loaded the same old Refresh Token.
- OP detected replay and revoked the token family.
- Token saved under the wrong principal/registration.
- Background job reading an out-of-sync store.

### 17.2. Illustrative race

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant Store as Authorized Client Store
    participant OP as Token Endpoint
    A->>Store: Load R1
    B->>Store: Load R1
    A->>OP: Refresh R1
    OP-->>A: Access A2, Refresh R2
    A->>Store: Save R2, version 2
    B->>OP: Refresh R1
    OP-->>B: invalid_grant
    Note over B,Store: B must not mistakenly delete A's R2 record
~~~

Solutions can include single-flight refresh per connection key, optimistic locking, or conditional delete/update depending on persistence. Never retry R1 indefinitely.

### 17.3. If Token Endpoint returns 503

This may be an outage; **do not wipe out all Refresh Tokens**. Use bounded retries, exponential backoff, jitter, and circuit breakers; preserve connection state appropriately.

### 17.4. Success/failure handlers

`DefaultOAuth2AuthorizedClientManager` is commonly used inside Servlet requests; `AuthorizedClientServiceOAuth2AuthorizedClientManager` is useful in background/non-request contexts. They invoke success/failure handlers to save or remove authorized clients based on the outcome.

When customizing handlers, verify you do not accidentally skip saving the new token, delete a newer record refreshed concurrently by another request, or infinitely retry permanent errors like `invalid_grant`.

## 18. Step 14 — Logout and Remaining Sessions

Different state layers exist:

~~~text
RP local HttpSession
OP SSO session
OAuth2AuthorizedClient in DB/Redis
Access Token at Resource Server
Refresh Token at Authorization Server
~~~

### 18.1. Local Logout

Usually only invalidates the local RP session. The OP SSO session may still be active, so the user signing in again may not be prompted for a password.

### 18.2. RP-Initiated Logout

When supported by the OP, Spring Security provides `OidcClientInitiatedLogoutSuccessHandler` (Servlet) or `OidcClientInitiatedServerLogoutSuccessHandler` (Reactive). Verify `end_session_endpoint`, `id_token_hint`, and the registered `post_logout_redirect_uri`. Never guess `issuer + "/logout"`.

### 18.3. Back-Channel Logout

If supported by the OP, it sends a signed `logout_token` server-to-server to:

~~~text
POST /logout/connect/back-channel/{registrationId}
~~~

The RP must verify the Logout Token and correlate the OP's `sid`/`sub` to the local session via a session registry. An OP `sid` is not the RP `JSESSIONID`. Verify cookie names, registry sharing across multiple nodes, and OP endpoint registration.

### 18.4. Token revocation is a separate step

`OAuth2AuthorizedClientService.removeAuthorizedClient(...)` only removes the local entry. Revoking tokens at the Authorization Server per RFC 7009 or provider policy is a separate mechanism. A JWT Access Token may remain accepted by APIs until expiration without introspection, a denylist, or a revocation strategy.

## 19. Quick Diagnostic Decision Tree

~~~mermaid
flowchart TD
    A["OAuth/OIDC error reported"] --> B{"Before or after login?"}
    B -->|Before| C{"Redirected to OP?"}
    C -->|No| D["Registration, SecurityFilterChain, login URL"]
    C -->|Yes| E{"OP called back RP?"}
    E -->|No| F["redirect_uri, scopes, user/OP policy"]
    E -->|Yes| G{"State matches and session exists?"}
    G -->|No| H["Cookie, SameSite, proxy, cluster"]
    G -->|Yes| I{"Token exchange succeeded?"}
    I -->|No| J["client auth, PKCE, invalid_grant, outage"]
    I -->|Yes| K{"ID Token valid?"}
    K -->|No| L["JWKS, iss, aud, nonce, exp"]
    K -->|Yes| M{"UserInfo/authorities valid?"}
    M -->|No| N["sub equality, missing claims, role policy"]
    M -->|Yes| O["Session and authorized client store"]
    B -->|After| P{"API, refresh, or logout?"}
    P -->|API| Q["invalid_token / insufficient_scope / API outage"]
    P -->|Refresh| R["revoked, rotation race, OP outage"]
    P -->|Logout| S["RP session vs OP session vs revocation"]
~~~

The decision tree only establishes **the order in which to gather evidence**. Every branch still requires logs/correlation across the OP, RP, and Resource Server to confirm the root cause.

## 20. Spring Security Logging: Enable Briefly, Never Leak Tokens

Example temporary configuration in staging/canary:

~~~yaml
logging:
  level:
    org.springframework.security: INFO
    org.springframework.security.oauth2: DEBUG
    org.springframework.web.client: INFO
    reactor.netty.http.client: INFO
~~~

Do not treat this as a long-term production DEBUG configuration. When elevating log levels:

1. Target a single instance for a short window.
2. Check whether loggers/appenders/HTTP wiretaps mask tokens, codes, state, verifiers, and cookies.
3. Restrict log viewing permissions and retention periods.
4. Do not log Token Endpoint bodies or Authorization headers.
5. Restore the baseline once sufficient evidence is collected.

### 20.1. Spring Security debug mode

`spring.security.debug=true` helps inspect the filter chain, but it also exposes extensive request details. Never enable it broadly in production without verifying redaction, privacy, and retention.

### 20.2. Safe structured event

~~~json
{
  "event": "oauth2_login_failed",
  "registrationId": "company",
  "stage": "callback",
  "reason": "authorization_request_not_found",
  "correlationId": "diag-7e2d",
  "deployment": "canary-04"
}
~~~

Do not include `exception.getMessage()` or raw request query strings in events if they could contain codes/state/tokens.

## 21. Servlet: Illustrative `AuthenticationFailureHandler`

Spring Security allows registering a dedicated `AuthenticationFailureHandler` in OAuth2 Login to record **the error category** without recording credentials.

~~~java
package com.example.security;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;

@Configuration
public class OAuth2DiagnosticConfig {

    private static final Logger LOG =
        LoggerFactory.getLogger(OAuth2DiagnosticConfig.class);

    @Bean
    AuthenticationFailureHandler diagnosticFailureHandler() {
        SimpleUrlAuthenticationFailureHandler fallback =
            new SimpleUrlAuthenticationFailureHandler("/login?error");

        return (request, response, exception) -> {
            LOG.warn("oauth2_login_failed reason={}",
                safeCategory(exception));

            // Do not log exception.getMessage(), raw JWTs,
            // request URI/query, Authorization headers, or cookies.
            fallback.onAuthenticationFailure(request, response, exception);
        };
    }

    private static String safeCategory(
            AuthenticationException exception) {

        if (exception instanceof OAuth2AuthenticationException oauth) {
            String code = oauth.getError().getErrorCode();
            return switch (code) {
                case "invalid_grant", "invalid_client",
                     "invalid_request", "invalid_scope",
                     "access_denied", "temporarily_unavailable" -> code;
                default -> "oauth2_authentication_error";
            };
        }
        if (exception instanceof AuthenticationServiceException) {
            return "authentication_service_error";
        }
        return "authentication_error";
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationFailureHandler diagnosticFailureHandler)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .loginPage("/login")
                .failureHandler(diagnosticFailureHandler))
            .build();
    }
}
~~~

`/login` must be implemented by the application if using a custom login page. The snippet above is **a complete illustrative `SecurityFilterChain`**—do not copy it alongside another chain matching all requests. Beyond this handler, HTTP libraries, proxies, and APM can still capture credentials; review the entire pipeline.

### 21.1. Do not classify every exception as `invalid_grant`

A storage or network failure may not be an `OAuth2AuthenticationException`. Keep a distinct `authentication_service_error` or `provider_unavailable` category instead of falsely attributing it to user consent revocation.

## 22. Exposing Metadata About the Authenticated User

For internal or staging applications, a tightly restricted diagnostic endpoint can expose `registrationId` and a filtered set of authorities.

~~~java
package com.example.web;

import java.util.List;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DiagnosticAuthController {

    @GetMapping("/internal/diagnostic/auth")
    public DiagnosticAuth view(OAuth2AuthenticationToken authentication) {
        String registrationId =
            authentication.getAuthorizedClientRegistrationId();

        List<String> safeAuthorities =
            authentication.getAuthorities().stream()
                .map(a -> a.getAuthority())
                .filter(a -> a.equals("OIDC_USER")
                    || a.equals("ROLE_REPORT_VIEWER"))
                .toList();

        return new DiagnosticAuth(registrationId, safeAuthorities);
    }

    record DiagnosticAuth(
        String registrationId, List<String> authorities) {}
}
~~~

Deploy only with **internal admin authorization**, environment gating, auditing, and a privacy policy. Never return `OidcUser.getClaims()`, ID Tokens, Access Tokens, or session cookies. This example assumes the principal comes from OAuth2 Login; if the app also uses form login or API keys, handle other `Authentication` types safely.

## 23. Reactive/WebFlux: Differs from Servlet in Context and Storage

| Aspect | Servlet | Reactive |
| --- | --- | --- |
| DSL | `HttpSecurity` | `ServerHttpSecurity` |
| Chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Session | `HttpSession` | `WebSession` |
| Authorized client store | `OAuth2AuthorizedClientRepository` / service | `ServerOAuth2AuthorizedClientRepository` / reactive service |
| WebClient token filter | `ServletOAuth2AuthorizedClientExchangeFilterFunction` | `ServerOAuth2AuthorizedClientExchangeFilterFunction` |
| Context | Servlet request/security context | Reactor Context/SecurityContext |

A basic Reactive configuration:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain webFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/", "/login", "/error").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

This is a **Reactive replacement for Servlet**—do not mix both DSLs unless a clear hybrid architecture requires it.

### 23.1. Authentication lost when switching schedulers

Bugs that can arise in code:

- Calling `subscribe()` manually and detaching the pipeline from the request.
- Calling `block()` on the Reactor event loop.
- Spawning manual threads while assuming `ThreadLocal` `SecurityContext` always propagates.
- Failing to compose the `Mono` for saving/removing authorized clients.
- Running a background job with a manager that requires a `ServerWebExchange` when none exists.

Diagnose Reactor Context propagation, reactive transaction lifecycles, and explicit principal passing. For background jobs, consider `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`.

## 24. Observability: Metrics, Logs, and Tracing

### 24.1. Suggested metrics

| Metric | Safe tags |
| --- | --- |
| `oauth2_login_started_total` | registration, environment |
| `oauth2_login_failed_total` | stage, safe error category |
| `oauth2_callback_failed_total` | registration, region |
| `oauth2_token_exchange_duration` | provider, grant type |
| `oauth2_id_token_validation_failures` | issuer alias, reason class |
| `oauth2_userinfo_failed_total` | provider, status class |
| `oauth2_session_missing_total` | region, node class |
| `oauth2_api_invalid_token_total` | API alias |
| `oauth2_api_insufficient_scope_total` | API alias |
| `oauth2_refresh_invalid_grant_total` | provider |
| `oauth2_provider_5xx_total` | provider, endpoint class |

Never use raw subjects, emails, tokens, session IDs, OAuth state, or `jti` as metric labels due to privacy and high cardinality.

### 24.2. Tracing across browser redirects

The browser navigates through the OP and returns to the RP, so trace headers are not preserved by default. An internal login attempt ID can aid correlation if stored in the server-side request/session while respecting security boundaries; never inject arbitrary trace context into OAuth protocol parameters in a way that breaks state/nonce behavior.

### 24.3. Health checks

Liveness/readiness probes must not continuously execute Authorization Code Flows or refresh production user tokens. Synthetic login checks should use dedicated provider sandboxes/test clients/test users at approved cadences and privilege levels.

## 25. Retries, Rate Limits, and Circuit Breakers

| Error | Retry policy |
| --- | --- |
| Network timeout | Bounded, recognize unknown outcome |
| HTTP 429 | Honor `Retry-After`, backoff/jitter |
| HTTP 502/503/504 | Bounded retry/circuit breaker |
| `invalid_grant` | Do not infinitely retry the same code/refresh token |
| `invalid_client` | Fix credentials/registration, do not spam Token Endpoint |
| `invalid_scope` | Fix requested scope and consent |
| API 401 `invalid_token` | Handle stale tokens per policy, inspect handlers |
| API 403 `insufficient_scope` | Do not self-elevate privileges |
| JWKS unavailable | Retry/cache per trusted policy; never disable signatures |

Backoff:

~~~text
delay = min(maxDelay, baseDelay * 2^attempt)
delayWithJitter = random(0, delay)
~~~

Circuit breakers and bulkheads should be partitioned per provider/endpoint as needed so a Provider A outage does not block Provider B. For POSTs with side effects or single-use authorization codes, do not blindly auto-retry after a timeout.

## 26. Scenario A — `redirect_uri_mismatch` After Proxy Change

**Symptom:** browser reaches the OP, but the OP rejects the request immediately.

**Failing step:** Authorization Endpoint validation, before the callback.

**Investigation:** compare the scheme, host, port, and path in the RP-sent `redirect_uri` against the OP-registered URI; inspect proxy forwarding/trust configuration.

**Resolution:** align the public URL, trusted forwarded headers, and exact redirect registration. Do not open arbitrary wildcard redirects.

## 27. Scenario B — Lost `state` After Prolonged MFA

**Symptom:** OP login succeeds, RP callback reports authorization request not found.

**Failing step:** callback/session correlation.

**Investigation:** session timeout, browser cookie inclusion reasons, `SameSite`, `Domain`/`Path`, two-tab flows, load balancer/pod routing.

**Resolution:** adjust cookie/session store/TTL per policy. Do not disable state validation.

## 28. Scenario C — `invalid_client` After Client Secret Rotation

**Symptom:** Token Endpoint returns 401/400 with `invalid_client` for all users of one registration.

**Failing step:** client authentication at the Token Endpoint.

**Investigation:** OP secret version, method (`Basic`/`private_key_jwt`/mTLS), pod rollout, secret manager, client ID/tenant.

**Resolution:** rotate and roll out cleanly, never log secrets, and do not retry infinitely.

## 29. Scenario D — Code Exchange `invalid_grant` When Reloading Callback

**Symptom:** login works once, refreshing the callback page causes an error.

**Failing step:** Token Endpoint.

**Investigation:** code is single-use, callback resent by proxy/browser, `redirect_uri`/PKCE.

**Resolution:** do not reuse authorization codes; initiate a new authorization request when needed.

## 30. Scenario E — ID Token Has Wrong Issuer/Audience

**Symptom:** Token Endpoint returns 200, yet Spring Security does not create a session.

**Failing step:** ID Token validation.

**Investigation:** `issuer-uri`, `client-id`, realm/tenant, signing keys/JWKS, and `azp` if applicable.

**Resolution:** fix registration or OP configuration; never modify claims inside a JWT.

## 31. Scenario F — New JWKS Not Yet Loaded by RP

**Symptom:** only ID Tokens signed with the new `kid` are rejected.

**Failing step:** JWT signature verification.

**Investigation:** JWKS fetch, trusted issuer, cache refresh, OP key rotation, proxy/TLS.

**Resolution:** refresh the key cache per trusted provider policy; never skip signature verification.

## 32. Scenario G — UserInfo `sub` Mismatch

**Symptom:** UserInfo returns 200, yet claims are rejected.

**Failing step:** UserInfo identity binding.

**Investigation:** Access Token from another principal/issuer, token substitution, misrouted endpoint.

**Resolution:** reject UserInfo when `sub` differs from the ID Token; fix token/context routing.

## 33. Scenario H — Login Succeeds, API Returns 403

**Symptom:** browser has an OIDC session, yet Reports API rejects requests.

**Failing step:** Resource Server authorization, not necessarily OIDC Login.

**Investigation:** Bearer `WWW-Authenticate`, token audience/scope, entity ACL, tenant policy.

**Resolution:** obtain the proper delegated API scope via approved consent; never swap in admin Client Credentials to bypass permissions.

## 34. Scenario I — Scale-Out Redirects Users Back to Login

**Symptom:** logged in on Pod A, request to Pod B lacks `SecurityContext`.

**Failing step:** Session/Authorized Client persistence.

**Investigation:** Redis/JDBC session, cookie routing, serialization, TTL, in-memory authorized clients.

**Resolution:** design shared state/affinity with multi-node tests, not localhost-only testing.

## 35. Scenario J — Refresh Token Rotation Race

**Symptom:** Request A refreshes successfully, Request B gets `invalid_grant` and deletes the new token.

**Failing step:** Refresh concurrency/persistence.

**Investigation:** two requests loading the same Refresh Token, success/failure handlers, row version.

**Resolution:** single-flight or CAS/optimistic locking; never let a stale request delete another request's fresh record.

## 36. Scenario K — Partial OP Outage

**Symptom:** Token Endpoint returns 503, Resource Server still returns 200 for cached/existing Access Tokens.

**Failing step:** provider availability, not necessarily a revoked grant.

**Investigation:** endpoint/region/provider status, response class, `Retry-After`, and rate limits.

**Resolution:** keep valid credentials, apply backoff/circuit breaker and degraded UX, do not wipe all Refresh Tokens.

## 37. Scenario L — Immediate Re-Login After Logout

**Symptom:** user is not asked to enter a password again.

**Common misunderstanding:** RP local session vs. OP SSO session.

**Investigation:** is RP-Initiated Logout configured, does the OP publish `end_session_endpoint`, is the post-logout URI valid?

**Resolution:** align logout UX/policy with OP capabilities; do not equate local logout with Access Token revocation.

## 38. Stage-by-Stage Test Matrix

| Stage | Positive test | Negative test |
| --- | --- | --- |
| Registration | Valid issuer/client | Unknown `registrationId` |
| Authorization request | Redirect with state/PKCE | Invalid scope/redirect |
| OP consent | User grants consent | `access_denied` |
| Callback | Valid code + state | Missing/wrong state, session expired |
| Token Endpoint | Code exchanged for tokens | `invalid_client`, `invalid_grant`, 503 |
| ID Token | Valid signature/`iss`/`aud`/`exp` | Wrong issuer, audience, nonce, bad signature |
| UserInfo | `sub` matches | `sub` mismatch, missing optional claim |
| Authority mapping | Trusted role mapped | Unknown/foreign admin claim |
| Session | Cookie + `SecurityContext` restored | Wrong `SameSite`, different pod |
| Authorized Client | Save/load/refresh persisted | Wrong principal, stale row |
| Resource Server | 200 with right audience/scope | 401 `invalid_token`, 403 `insufficient_scope` |
| Refresh | Token rotation and atomic save | Race, revoked token, provider down |
| Logout | Proper local/OP/back-channel logout | Wrong `sid`/`sub`, invalid logout token |

### 38.1. Mock authentication is not a protocol integration test

`@WithMockUser`, `oauth2Login()`, or `oidcLogin()` in Spring Security Test are very useful for testing controllers/authorities, yet they may only construct a fake `Authentication` without executing authorization code exchange, PKCE, ID Token verification, and UserInfo requests.

When protocol verification is needed, use a **mock/test OP** with a Token Endpoint, Discovery/JWKS, signed test ID Tokens, and UserInfo, combined with browser/HTTP integration tests.

### 38.2. Do not test with production user credentials

Do not dump raw tokens into CI artifacts. Use test registrations, test users, and controlled fixtures; purge cookies/token traces per retention rules.

## 39. Ordered Incident Handling Checklist

1. Identify registration ID, environment, version, UTC time, and impact scope.
2. Classify the stage: login/callback/token/id_token/userinfo/session/api/refresh/logout.
3. Collect sanitized HTTP status, OAuth error code, and correlation ID.
4. Verify trusted issuer/`ClientRegistration` and OP metadata.
5. Verify Authorization Endpoint redirect and registered `redirect_uri`.
6. Confirm OP login/consent finished and the callback reached the right path.
7. Verify `state`/session/cookie and PKCE verifier correlation.
8. If token exchange fails: distinguish `invalid_grant`, `invalid_client`, and 429/5xx.
9. If ID Token fails: check signature/JWKS, `iss`/`aud`/`nonce`/expiry/clock.
10. If UserInfo fails: verify token/endpoint and exact `sub` match.
11. If 403 occurs after login: distinguish RP CSRF, role/tenant policy, and Resource Server scopes.
12. If session drops: inspect cookies/`SecurityContext`/Redis/multi-instance routing.
13. If API returns 401/403: inspect `WWW-Authenticate`/audience/granted scopes and API logs.
14. If refresh fails: inspect revocation, rotation races, and authorized client persistence.
15. If logout fails: distinguish RP session, OP SSO, and token revocation.
16. Conclude with evidence, add a regression test, restore logging levels, and document postmortem findings.

## 40. References

- Spring Security — OAuth2 Login Servlet: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html
- Spring Security — OAuth2 Login Advanced: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- Spring Security — OAuth2 Client Servlet: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html
- Spring Security — Authorized Clients: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html
- Spring Security — OAuth2 Login Reactive: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html
- Spring Security — OAuth2 Client Reactive: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html
- Spring Security — OIDC Logout Servlet: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html
- Spring Security — OIDC Logout Reactive: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/logout.html
- Spring Security — OAuth2 Login MockMvc Tests: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html
- Spring Boot — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot — Logging: https://docs.spring.io/spring-boot/reference/features/logging.html
- OpenID Connect Core 1.0: https://openid.net/specs/openid-connect-core-1_0.html
- OpenID Connect Discovery 1.0: https://openid.net/specs/openid-connect-discovery-1_0.html
- OpenID Connect RP-Initiated Logout: https://openid.net/specs/openid-connect-rpinitiated-1_0.html
- OpenID Connect Back-Channel Logout: https://openid.net/specs/openid-connect-backchannel-1_0.html
- RFC 6749 — OAuth 2.0 Authorization Framework: https://www.rfc-editor.org/rfc/rfc6749
- RFC 7636 — Proof Key for Code Exchange (PKCE): https://www.rfc-editor.org/rfc/rfc7636
- RFC 6750 — OAuth 2.0 Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750
- RFC 7009 — OAuth 2.0 Token Revocation: https://www.rfc-editor.org/rfc/rfc7009
- RFC 9700 — OAuth 2.0 Security Best Current Practice: https://www.rfc-editor.org/rfc/rfc9700
- RFC 8725 — JSON Web Token BCP: https://www.rfc-editor.org/rfc/rfc8725
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP OAuth2 Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html

## 41. Summary

~~~text
Diagnose OAuth/OIDC in order:

ClientRegistration and issuer metadata
  -> Authorization request (state/PKCE/redirect_uri)
  -> OP login/consent
  -> Callback correlation
  -> Token Endpoint exchange
  -> ID Token signature/iss/aud/nonce/exp
  -> UserInfo sub equality
  -> Authentication + GrantedAuthorities
  -> Session + Authorized Client persistence
  -> Resource Server 401/403 and refresh
  -> Logout local/OP/revocation

At each stage:
  1. Collect redacted metadata.
  2. Identify the first failing step with evidence.
  3. Distinguish config/security/policy/transient outage.
  4. Fix at the right boundary and run regression tests.
  5. Never disable security checks.
~~~

**Most important principles:**

1. **Start from the first failing stage.** A state mismatch before the Token Endpoint cannot be fixed with a client secret; a Resource Server 403 after login does not mean OIDC Login failed.
2. **Do not confuse tokens and servers.** ID Tokens serve RP authentication, Access Tokens target UserInfo/APIs, and Refresh Tokens target the Token Endpoint; each has its own issuer/audience/lifecycle.
3. **Preserve security invariants.** Never disable `state`, PKCE, `nonce`, issuer/audience validation, JWT signatures, TLS, or CSRF just to get HTTP 200.
4. **Log only safe metadata.** Error category, stage, registration alias, UTC time, and correlation ID are usually enough to investigate without leaking tokens/codes/cookies.
5. **Distinguish permanent from transient errors.** `invalid_grant`, `invalid_client`, `invalid_token`, `insufficient_scope`, and HTTP 503 require different decisions.
6. **Verify with integration tests.** Mock user tests cannot replace browser callbacks, OP Token Endpoints, JWKS, UserInfo, and session persistence in multi-instance topologies.

The habit of always asking **"How far did the flow go, which step failed first, and what evidence confirms it?"** enables teams to troubleshoot Spring Security OAuth2/OIDC Client accurately, quickly, and safely while avoiding out-of-scope fixes.
