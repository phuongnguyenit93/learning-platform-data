# 28.1. Error Classification Across Authorization, Callback, Token, and UserInfo

In **Spring Security OAuth 2.0/OIDC Client**, a generic "OAuth login failed" message is not enough to identify the root cause. An error at the Authorization Endpoint when a user denies consent, a callback `state` mismatch, an `invalid_grant` returned by the Token Endpoint, and an HTTP 401 from UserInfo can all cause the login screen to fail. However, they occur at **different trust boundaries, processing steps, and areas of responsibility**.

This lesson builds a **stage-based error classification** across protocol codes, HTTP statuses, exception types, responsible systems, and recovery actions. The content applies to Spring Security OAuth2 Client/OIDC Relying Party on **Spring MVC/Servlet** and **Reactive WebFlux**, with configuration examples, safe handling patterns, diagrams, test cases, logging/metrics, dashboards, and runbooks.

> **First rule:** Before reading `error`, HTTP 400, HTTP 401, or an exception, identify **which request is failing and which system returned the error**. An HTTP 401 at the UserInfo Endpoint is not the same as an HTTP 401 from the Reports API; an `invalid_grant` when exchanging an authorization code is not the same as an `invalid_grant` when refreshing a token.

## 1. OAuth2/OIDC Error Flow Map

```mermaid
sequenceDiagram
    autonumber
    actor User as User
    participant Browser as Browser
    participant RP as Spring Security OAuth2/OIDC Client
    participant Session as Session / Authorized Client Store
    participant OP as Authorization Server / OP
    participant UI as UserInfo Endpoint

    User->>Browser: Choose Sign In
    Browser->>RP: GET /oauth2/authorization/company
    Note over Browser,RP: A — Authorization initiation
    RP->>Session: Save OAuth2AuthorizationRequest (state, PKCE, nonce)
    RP-->>Browser: 302 to authorization_endpoint
    Browser->>OP: User authentication + consent
    Note over Browser,OP: B — Authorization decision
    OP-->>Browser: Redirect ?code=... or ?error=...
    Browser->>RP: GET /login/oauth2/code/company
    Note over Browser,RP: C — Callback correlation
    RP->>Session: Restore request + verify state
    RP->>OP: POST /token, code + client auth + PKCE
    Note over RP,OP: D — Token exchange
    OP-->>RP: Tokens or OAuth2 error
    RP->>RP: Verify ID Token (signature, iss, aud, nonce)
    Note over RP,RP: E — OIDC ID Token validation
    opt UserInfo is used
      RP->>UI: GET /userinfo with Bearer access token
      Note over RP,UI: F — UserInfo
      UI-->>RP: Claims or error
    end
    RP->>Session: Save Authentication and OAuth2AuthorizedClient
    RP-->>Browser: Login success or failure handler
```

In the lesson title, the four points to distinguish are **authorization**, **callback**, **token**, and **UserInfo**. However, in real-world observability we also need:

- **ID_TOKEN_VALIDATION:** the token endpoint may return HTTP 200 and only then does the RP detect an invalid JWT/issuer/nonce.
- **PROVIDER_DISCOVERY/JWKS:** metadata, TLS, or signing key errors can appear before or during login.
- **AUTHORIZED_CLIENT_PERSISTENCE:** token/session storage failures are RP storage errors, not provider errors.
- **TOKEN_REFRESH:** uses the same Token Endpoint but has a different grant, lifecycle, and action.
- **RESOURCE_SERVER_API:** errors calling an API after login do not mean OAuth2 Login failed.

### 1.1. Stage Table

| Stage | Actor | Key Inputs | Typical Errors |
|---|---|---|---|
| Authorization initiation | RP | `registrationId`, scopes, redirect URI, authorization request | Missing ClientRegistration; session store failure |
| Authorization decision | OP + Browser | OP session, consent, authorization request | `access_denied`, `invalid_scope` |
| Callback correlation | RP | `code`/`error`, `state`, saved authorization request | Missing request, state mismatch, replay |
| Token exchange | RP → Token Endpoint | Code, client authentication, redirect URI, PKCE verifier | `invalid_grant`, `invalid_client` |
| ID Token validation | RP | JWT signature, issuer, audience, nonce | Invalid JWT, wrong `iss`/`aud` |
| UserInfo | RP → UserInfo | Access token, UserInfo claims | 401 `invalid_token`, `sub` mismatch |
| Authorized client persistence | RP → local/DB store | Registration, principal, token | DB unavailable, wrong key |
| Token refresh | RP → Token Endpoint | Refresh token, client auth | `invalid_grant`, rotation race |
| Downstream API | RP → Resource Server | Bearer access token | 401 `invalid_token`, 403 `insufficient_scope` |

### 1.2. Two-Axis Classification

**Stage axis:**

```text
AUTHORIZATION_INITIATION
AUTHORIZATION_RESPONSE
CALLBACK_CORRELATION
TOKEN_EXCHANGE
ID_TOKEN_VALIDATION
USERINFO
AUTHORIZED_CLIENT_PERSISTENCE
TOKEN_REFRESH
RESOURCE_SERVER_CALL
```

**Category axis:**

```text
USER_DENIED
CLIENT_CONFIGURATION
INVALID_REQUEST
PROTOCOL_VALIDATION
SECURITY_REJECTION
REMOTE_PROVIDER_FAILURE
NETWORK_OR_TLS
TIMEOUT
RATE_LIMIT
SESSION_OR_STORAGE
ACCOUNT_MAPPING
INTERNAL_ERROR
```

For example:

```text
stage=AUTHORIZATION_RESPONSE
category=USER_DENIED
protocolError=access_denied
action=show_safe_message
```

Versus:

```text
stage=TOKEN_EXCHANGE
category=CLIENT_CONFIGURATION
protocolError=invalid_client
action=alert_integration_owner
```

This is an **application-designed operational taxonomy**, not new OAuth2 error names. Always keep the original OAuth2 error code and the received stage separate.

## 2. Anatomy of an OAuth2 Error

### 2.1. Error Authorization Response

The Authorization Server may redirect the browser back to the RP:

```http
HTTP/1.1 302 Found
Location: https://portal.example.test/login/oauth2/code/company?error=access_denied&state=EXAMPLE_STATE
```

### 2.2. Token Endpoint Error

The Token Endpoint typically returns an error JSON payload:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{
  "error": "invalid_grant",
  "error_description": "Example provider message"
}
```

### 2.3. Fields to Understand

| Field | Meaning | Security Notes |
|---|---|---|
| `error` | OAuth2 error code or provider-specific extension | Can be used for classification; size/characters must be bounded |
| `error_description` | Description provided by the provider | Do not display verbatim to users; may contain PII/untrusted content |
| `error_uri` | Reference URI explaining the error | Do not automatically fetch arbitrary URIs provided by a response |
| `state` | Binds the authorization response to the previous request | Do not use as a tracing ID; do not log its value |
| HTTP status | Status of the request to an endpoint | Not sufficient on its own to determine stage/root cause |

**Do not expose the full OAuth2 error response or callback URL to the frontend.** URLs may contain a code, state, or data that should not be recorded in telemetry.

### 2.4. Three Easily Confused Error Groups

**Authorization Endpoint** according to OAuth2 can use:

```text
invalid_request
unauthorized_client
access_denied
unsupported_response_type
invalid_scope
server_error
temporarily_unavailable
```

**Token Endpoint** commonly uses:

```text
invalid_request
invalid_client
invalid_grant
unauthorized_client
unsupported_grant_type
invalid_scope
```

**Bearer Resource Server** according to RFC 6750 defines the codes:

```text
invalid_request
invalid_token
insufficient_scope
```

The UserInfo Endpoint can use Bearer-style errors because it is a protected resource. Business APIs can also use these error codes, but they are **not part of the login flow**.

## 3. Authorization Initiation: Errors Before Leaving the RP

The user clicks:

```text
GET /oauth2/authorization/company
```

Spring Security needs to resolve the `ClientRegistration`, create the authorization request, store `state` and PKCE/nonce if needed, and then redirect to the OP's Authorization Endpoint.

### 3.1. Typical Errors

| Symptom | Suggested Root Cause |
|---|---|
| Registration not found | URL uses provider ID instead of registration ID, missing configuration |
| Discovery failure | Wrong `issuer-uri`, invalid TLS/DNS/metadata |
| Wrong Authorization Endpoint URI | Registration points to the wrong issuer/provider |
| Redirect URI has wrong public host | Reverse proxy forwarded headers are incorrect |
| Cannot save authorization request | Session/Redis store failure, serialization, or timeout |
| Custom request resolver exception | Invalid scope, state, redirect, or code customization |
| Tenant/issuer not allowed | Backend proactively blocks dynamic provider due to trust policy |

Some errors appear **at startup** due to discovery/ClientRegistration initialization rather than when a user clicks login. Therefore, the runbook needs a category for `PROVIDER_DISCOVERY`/configuration.

### 3.2. Spring Security Components

**Servlet:**

- `ClientRegistrationRepository`.
- `OAuth2AuthorizationRequestRedirectFilter`.
- `OAuth2AuthorizationRequestResolver`.
- `AuthorizationRequestRepository<OAuth2AuthorizationRequest>`.
- `HttpSessionOAuth2AuthorizationRequestRepository`.

**Reactive:**

- `ReactiveClientRegistrationRepository`.
- `OAuth2AuthorizationRequestRedirectWebFilter`.
- `ServerOAuth2AuthorizationRequestResolver`.
- `ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest>`.
- `WebSessionOAuth2ServerAuthorizationRequestRepository`.

If using `SecurityWebFilterChain`, do not use Servlet `HttpSessionOAuth2AuthorizationRequestRepository` instead of the WebSession repository.

### 3.3. Indicators

- The browser has not reached the OP yet.
- There is no callback `code` or `error` from the OP yet.
- The Token Endpoint has not been called yet.
- RP trace/logs only reach the request resolver/config/session store.

If the browser has reached the OP and the OP displays "invalid redirect URI", this is usually **Authorization Endpoint validation**, not an RP callback creation error.

### 3.4. How to Handle

- Check `registrationId` and `provider` in YAML; they are different.
- Check the issuer URI, HTTPS, discovery, and provider metadata.
- Register the exact callback URI at the OP; do not use overly broad wildcards.
- Only trust forwarded headers from trusted reverse proxies.
- Check the session store and cookie TTL.
- If the error is a static configuration issue, alert the owning team instead of telling users to retry repeatedly.
- Do not use an issuer URL supplied by the browser to dynamically discover endpoints without trust/SSRF controls.

## 4. Authorization Decision: OP Denial or Unmet Policy

At this stage, the browser has reached the OP. The OP handles authentication, MFA, policy, consent, and returns an authorization response.

### 4.1. `access_denied`

Example:

```http
GET /login/oauth2/code/company?error=access_denied&state=EXAMPLE_STATE HTTP/1.1
Host: portal.example.test
```

`access_denied` can mean:

- The user clicked "Cancel/Deny".
- The user declined consent.
- The OP applied a conditional access policy.
- The account is not permitted to use the Client or scope.
- An authentication/MFA requirement was not completed.
- The provider groups multiple reasons under the same code.

**Do not always assume the user clicked Cancel.** Look for additional categories or OP audit events when needed, but do not automatically treat this as a broken system.

### 4.2. Authorization Error Codes

| Code | Meaning | Action Group |
|---|---|---|
| `access_denied` | Resource owner or OP denied authorization | Safe message; user may retry |
| `invalid_request` | Request has missing/invalid/duplicate parameters | Fix request/config |
| `unauthorized_client` | Client is not permitted to perform this authorization method | Check OP Client policy |
| `unsupported_response_type` | OP does not support the response type | Check `response_type=code` |
| `invalid_scope` | Scope is not granted/invalid | Adjust scope/consent |
| `server_error` | OP internal failure | Monitoring/SLO/incident |
| `temporarily_unavailable` | OP temporarily unavailable | Backoff, limit retries |

### 4.3. Provider Error Codes May Differ from the Standard

Some OPs add proprietary error codes for MFA, device, session, tenant policy, identity federation, or administration. Do not write a controller that only accepts a fixed set of codes and returns 500 for any unfamiliar code. How to handle:

1. Record `protocolErrorCode` against a sanitized allowlist.
2. Map common codes to stable categories.
3. For unrecognized codes, use `PROVIDER_SPECIFIC`/`UNKNOWN`.
4. Return a safe UX message and correlation ID.
5. Do not display raw `error_description` or fetch arbitrary `error_uri` values.

### 4.4. Should You Retry Immediately?

When a user denies consent, **do not** automatically redirect back to the OP in an infinite loop. With `temporarily_unavailable`, you can let the user manually retry or apply backoff. With `invalid_scope` and `unauthorized_client`, user retries will not resolve the issue until the ClientRegistration/OP policy is changed.

## 5. Callback: Did the OP Report an Error or Did the RP Reject the Response?

The standard callback usually follows the pattern:

```text
/login/oauth2/code/{registrationId}
```

Here there are at least two cases:

```text
Branch A — OP already decided an error:
  callback ?error=access_denied&state=...
  -> error originated from Authorization Endpoint / consent

Branch B — OP returned a code:
  callback ?code=...&state=...
  -> RP cannot find saved request or state does not match
  -> error occurred at callback correlation
```

Both "appear on the callback", but they are handled differently.

### 5.1. Required Checks

The RP must preserve and verify:

- `state` bound to the previously created request.
- Session/WebSession still holds the corresponding `OAuth2AuthorizationRequest`.
- Registration ID/issuer and flow have not been swapped.
- PKCE verifier is preserved for token exchange.
- OIDC nonce is preserved for ID Token validation.
- The authorization request has not already been consumed/replayed.
- Redirect URI matches the original context.
- The callback only uses an endpoint registered with the OP.

Do not grab a `code` from a query parameter and send it arbitrarily to the Token Endpoint while bypassing the authorization request/state.

### 5.2. `authorization_request_not_found`

A common error is Spring failing to find the authorization request saved before the redirect. Possible causes:

- The session expired between initiation and callback.
- The browser did not send the cookie due to SameSite/domain/path.
- The user opened multiple tabs and a custom/session repository caused the earlier flow to be overwritten.
- A load balancer routed the callback to a pod that does not have the local session.
- Spring Session Redis timed out/went down.
- App restarted with in-memory sessions.
- Custom repository dropped `state`/nonce/PKCE attributes.
- Callback was called directly without ever initiating login.

Do not "fix" this by disabling state validation. Fix session architecture, cookie configuration, and repository behavior.

### 5.3. `invalid_state` or State Mismatch

If the callback state does not match the saved authorization request, Spring must reject the flow. This may be due to multiple tabs, a lost cookie, or an attempted login CSRF/callback injection.

Good log:

```text
stage=CALLBACK_CORRELATION
category=SECURITY_REJECTION
reason=state_mismatch
registrationId=company
correlationId=internal-random-id
```

Unsafe log:

```text
state=actual-secret-value
code=actual-authorization-code
Cookie=actual-session-id
```

### 5.4. SameSite and POST Callbacks

Authorization Code Flow typically uses a top-level GET callback, which is compatible with many `SameSite=Lax` configurations. If the OP uses `response_mode=form_post`, the browser may perform a cross-site POST; Lax cookies may be blocked.

You need to check response mode, cookie `Secure`/`SameSite`, domain/path, HTTPS proxy, and CSRF policy. Do not enable `SameSite=None` for all cookies by default or disable CSRF application-wide without evaluation.

### 5.5. A Callback with `code` Does Not Guarantee Login Success

A code may be expired, already used, mismatched to the Client, or mismatched to the verifier. It is only an input to the Token Endpoint, not proof that the user is Authenticated at the RP.

## 6. Token Endpoint: Authorization-Code Exchange

After a valid callback, the RP calls the Token Endpoint:

```http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Authorization: Basic EXAMPLE_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
code=EXAMPLE_CODE&
redirect_uri=https%3A%2F%2Fportal.example.test%2Flogin%2Foauth2%2Fcode%2Fcompany&
code_verifier=EXAMPLE_CODE_VERIFIER
```

The values above are placeholders. Do not write real codes, verifiers, or Client credentials to logs. The OP may require a Client authentication method other than `client_secret_basic`, such as `private_key_jwt` or mTLS.

### 6.1. Token Endpoint Errors

| Error | Meaning | What to Investigate |
|---|---|---|
| `invalid_request` | Missing/invalid token request parameter | Code, redirect URI, grant, verifier, encoding |
| **`invalid_client`** | Invalid client authentication | Client ID/secret, key, mTLS, auth method |
| **`invalid_grant`** | Authorization grant is invalid/expired/used/wrong Client | Code expiry, replay, PKCE, redirect URI |
| `unauthorized_client` | Client is not permitted to use the grant | OP grant permissions |
| `unsupported_grant_type` | Requested grant is not supported | `authorization_code`, registration |
| `invalid_scope` | Invalid scope | Consent, scope restrictions |

You may encounter HTTP 400 or 401 depending on the error and OP policy. Do not use HTTP status alone to conclude the error type.

### 6.2. `invalid_grant` During Code Exchange

Commonly caused by:

- Code expired.
- Code already used.
- Code does not belong to the configured Client.
- Redirect URI mismatch.
- PKCE `code_verifier` mismatch or missing.
- Callback replayed.
- Token Endpoint/registration points to a different tenant/issuer.

Do not display "Wrong password" for `invalid_grant`. The OP handles password/MFA during the user authentication stage; the RP must not guess from a token error code.

### 6.3. `invalid_client` Is Usually an Operational Error

Check:

- Client secret expired/rotated out of sync.
- Wrong `client_authentication_method`.
- Client ID points to the wrong tenant.
- Broken mTLS certificate or private_key_jwt.
- Secret manager returned the wrong environment.
- Client disabled at the OP.

If the error occurs for many users after a deployment, alert the integration owner. Asking users to change their password is usually unrelated.

### 6.4. Network, TLS, Timeout, 429, and 5xx

A token request can fail before receiving OAuth2 JSON:

| Symptom | Error Group | Action |
|---|---|---|
| DNS failure | Network | Check DNS/egress |
| TLS handshake | Security/Network | Check CA/hostname/mTLS; do not disable TLS verification |
| Connect timeout | Network/Dependency | Appropriate timeout/backoff |
| Read timeout | Dependency | Observe latency/availability |
| HTTP 429 | Rate limit | `Retry-After` and quota policy |
| HTTP 500/503 | OP outage | Circuit breaker/incident |
| HTML error page | Proxy/WAF/contract | Do not parse as valid JSON |
| Unexpected JSON schema | Protocol/dependency | Compare provider docs/version |

### 6.5. Retrying an Authorization Code Is Very Sensitive

An authorization code is **single-use**. If the Token Endpoint finishes processing it but the response is lost due to a timeout, retrying with the old code may return `invalid_grant`. Do not apply blind retries like an idempotent GET. When safe recovery is not possible, ask the user to start a new Authorization Code Flow.

## 7. Token Endpoint Returns HTTP 200 Yet OIDC Login Still Fails

Sample token response:

```json
{
  "access_token": "EXAMPLE_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 300,
  "id_token": "EXAMPLE_ID_TOKEN"
}
```

Spring may receive a valid HTTP response and then discover:

- Missing or wrong type for `access_token`/`token_type`.
- OIDC flow missing `id_token` when required.
- ID Token JWT parse error, invalid signature, or no matching signing key.
- `iss` differs from the configured provider issuer.
- `aud` does not contain the RP's Client ID.
- `exp`/`iat` invalid according to policy.
- `nonce` does not match the request when nonce is used.
- `azp`/hash claims conditions per OIDC are not satisfied when applicable.

**Do not log these as Token Endpoint `invalid_grant` when the Token Endpoint returned success.** Use stage **ID_TOKEN_VALIDATION** with category `SECURITY_REJECTION` or `DEPENDENCY_JWKS`.

### 7.1. A Valid JWT Signature Is Not Enough

An ID Token signed by a trusted OP but with `aud` set to another Client must not be used to authenticate the current RP. Likewise, `iss` must match the expected issuer, not just compare arbitrary hostnames.

### 7.2. `nonce` Is Different from `state`

- `state` binds the authorization response/callback to the authorization request.
- PKCE verifier binds the authorization code to the Client that initiated it.
- OIDC `nonce` binds the ID Token to the authentication request when the flow uses it.
- Issuer/audience/signature validation verifies that the token came from the right source and is for the right Client.

Do not disable one mechanism because another is enabled.

### 7.3. JWKS Rotation or Discovery Failure

The RP may fail to fetch signing keys when the OP rotates keys, the network fails, or metadata is wrong. This is a **dependency failure at the validation step**, not the OP returning an OAuth2 error.

Distinguish between:

```text
stage=ID_TOKEN_VALIDATION
dependency=JWKS
category=NETWORK_OR_TLS
```

and:

```text
stage=ID_TOKEN_VALIDATION
category=SECURITY_REJECTION
reason=invalid_signature
```

Do not accept an ID Token without signature verification when JWKS is unavailable.

## 8. UserInfo: HTTP, Bearer, Response, and Identity Binding

After obtaining an access token and ID Token, the RP **may** access the UserInfo Endpoint to retrieve claims. Calling UserInfo depends on the flow, scopes, provider metadata, and `OidcUserService`—**it is not mandatory for every OIDC Login**.

Example:

```http
GET /userinfo HTTP/1.1
Host: login.example.test
Authorization: Bearer EXAMPLE_ACCESS_TOKEN
Accept: application/json
```

### 8.1. UserInfo Error Table

| Error Group | Indicator | Root Cause |
|---|---|---|
| Bearer rejection | HTTP 401 `invalid_token` | Token expired/revoked/wrong resource, issuer, or policy |
| Permission | HTTP 403 / `insufficient_scope` | Insufficient scopes/consent |
| Network/TLS | Timeout, TLS, DNS | OP/proxy/network |
| HTTP dependency | 429, 5xx | Rate limit/outage |
| Response encoding | HTML instead of JSON, JSON parse error | Proxy, provider contract |
| Required claims | Missing `sub` | UserInfo response breaks contract |
| **Identity mismatch** | UserInfo `sub` differs from ID Token `sub` | Security rejection; must reject |
| Optional claims | Missing `email`/`name` | May be valid depending on scope/provider |
| Account mapping | Unique constraint, ownership | Application/DB error, not a UserInfo HTTP error |

### 8.2. UserInfo `sub` Must Match ID Token

Example:

```json
{
  "id_token_claims": {
    "iss": "https://login.example.test",
    "sub": "user-A",
    "aud": "portal-client"
  },
  "userinfo_response": {
    "sub": "user-B",
    "name": "Another user"
  }
}
```

You must not use `user-B`'s UserInfo as belonging to `user-A`. An OIDC RP must enforce subject matching and not map to another user simply because email or name matches.

### 8.3. UserInfo 401 Is Different from Downstream API 401

UserInfo belongs to the OIDC OP. If it is the source of claims needed to build the OIDC principal, a failure can cause login to fail.

The downstream Reports API is a business Resource Server that can return 401 **after the user has successfully logged in**. This error is usually an access token/permission/connection issue and does not necessarily force a portal logout.

### 8.4. Missing Optional Claims Are Not a Security Failure

UserInfo may omit `email`, `phone_number`, `picture`, or `name` if scope/consent/provider does not grant them. If the application requires email for business logic, design a separate onboarding/verification step. Do not treat every missing email as an invalid ID Token signature.

### 8.5. Claims from UserInfo Do Not Automatically Become Admin Roles

A UserInfo response containing `groups=["admin"]` does not automatically mean the user should be granted `ROLE_ADMIN` in every tenant. There must be a controlled claim-source contract, trusted issuer, account mapping, and authorization policy.

### 8.6. Is Not Calling UserInfo an Error?

**Not automatically.** Some flows only need claims from the ID Token; the framework may skip calling UserInfo based on configuration. If you observe zero UserInfo traffic, check whether an endpoint and invocation condition apply before declaring an incident.

## 9. Authorized Client Storage and Session Are Separate Errors

After OIDC login, Spring may store:

- `SecurityContext`/`Authentication` in the local session.
- `OAuth2AuthorizedClient` containing access token/refresh token in a repository/service.
- External identity mapping in the business database.

Errors that can occur:

- Redis/session store unavailable.
- JDBC authorized client service fails to save.
- Inconsistent principal name/registration ID.
- Two instances using separate in-memory stores.
- Incorrect schema migration.
- Session cookie expires immediately after login.

Do not log these errors as "UserInfo timeout" or "Token Endpoint invalid_grant" simply because the symptom is that the user cannot enter the application.

### 9.1. Saving Under the Right Key

`OAuth2AuthorizedClientService` typically looks up by `(registrationId, principalName)`. A record may exist, but the service queries with a different principalName because account mapping changed.

Example:

```text
Login saves: ("company", "oidc-sub-3")
Worker queries: ("company", "account-42")
=> Not found
```

Fix mapping/ownership; do not randomly pick a principal or use another user's token.

### 9.2. WebSession/HttpSession Is Not the Same as Token Service

Spring Session Redis can share sessions, but it does not automatically turn `InMemoryOAuth2AuthorizedClientService` into a distributed database. With multiple pods, you must verify both the **authorization request session store** and the **authorized client token store**.

## 10. Token Refresh: Same Token Endpoint, Different Lifecycle

After login, Spring `OAuth2AuthorizedClientManager` can request a new access token via the Refresh Token Grant:

```http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Authorization: Basic EXAMPLE_CLIENT_AUTH
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=EXAMPLE_REFRESH_TOKEN
```

### 10.1. `invalid_grant` During Refresh

Usually related to:

- Refresh token expired/revoked.
- User revoked consent.
- Refresh token rotation.
- Incompatible Client/tenant change.
- Token reuse/replay detection.
- Multiple jobs concurrently refreshing the same token.

**One error code, two contexts:**

| Where is `invalid_grant`? | Likely Causes | Action |
|---|---|---|
| Authorization-code exchange | Code expired/reused, PKCE, redirect URI | Initiate new login or fix protocol/config |
| Refresh Token Grant | Token revoked/expired/rotated | Clean up the right authorized client, reconnect when needed |

### 10.2. Refresh Rotation Race

```mermaid
sequenceDiagram
    participant A as Pod A
    participant B as Pod B
    participant DB as Shared Token Store
    participant OP as Token Endpoint
    A->>DB: Read RT-1
    B->>DB: Read RT-1
    A->>OP: refresh_token=RT-1
    OP-->>A: AT-2 + RT-2
    A->>DB: Write RT-2
    B->>OP: refresh_token=RT-1
    OP-->>B: invalid_grant / reuse detection
```

A shared JDBC/Redis store **does not automatically guarantee single-flight refresh**. You may need per-connection locking/optimistic versioning, avoid overwriting newer tokens with stale writes, and avoid retrying the same refresh token indefinitely.

### 10.3. A Refresh Error Is Not Always a Login Error

A user may still have a valid Corp portal session while their Calendar refresh token has been revoked. Usually you should mark the Calendar connection as `RECONNECT_REQUIRED` rather than logging the user out of the entire portal, unless security policy requires it.

## 11. Resource Server API Errors: Separate from UserInfo Errors

A downstream API may return:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

or:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

| Error | Origin | Handling Direction |
|---|---|---|
| `invalid_client` | Token Endpoint | Client credentials/config |
| `invalid_grant` | Token Endpoint | Authorization code or refresh |
| `invalid_token` | UserInfo Endpoint | Access token used for UserInfo |
| `invalid_token` | Reports API | Access token used for Reports API |
| `insufficient_scope` | UserInfo/API | Token permissions/scopes |
| ID Token wrong `iss` | RP validator | OIDC security, not API |
| Missing `state` | RP callback handler | Session/flow correlation |

### 11.1. HTTP 401 Is Not Always Due to an Expired Token

A Resource Server can reject a token due to issuer, audience, signature, revocation, DPoP/mTLS proof, or policy. Do not assume that simply refreshing the token will fix it.

### 11.2. HTTP 403 Should Not Be Retried Indefinitely

If an API requires a scope that was not granted, refreshing with the same scope will not add permissions. You need user consent/scopes or the appropriate policy. Do not pick a token from another ClientRegistration to bypass permissions.

## 12. Summary of Root Causes by Responsible Party

| Owner or System | Error Group | Examples |
|---|---|---|
| User | Cancelled consent, incomplete authentication | `access_denied` |
| RP configuration | Wrong registration/redirect/Client secret | `invalid_client`, `invalid_request` |
| RP security validation | State/nonce/issuer/audience mismatch | Callback rejected, ID Token invalid |
| OP/AS | Policy, outage, metadata issue | `temporarily_unavailable`, 5xx |
| Network/proxy | DNS/TLS/timeouts, forwarded headers | Redirect mismatch, TLS failure |
| Session/token store | Redis/JDBC unavailable, wrong key | `authorization_request_not_found`, missing authorized client |
| UserInfo | Bearer rejection, invalid response | 401, invalid `sub` |
| Account mapping | Business identity/ownership | Duplicate external identity, tenant isolation |
| Resource Server | Access token/scope rejection | 401/403 after successful login |

The stage and the owner can differ. For example, a callback fails, but the root cause is the session store on the RP; UserInfo returns 401, but the root cause is the Token Endpoint issuing a token for the wrong resource due to provider configuration.

## 13. Spring Security Exception Types

Common classes:

- **`OAuth2Error`**: describes `errorCode`, `description`, and `uri`.
- **`OAuth2AuthenticationException`**: OAuth2-related authentication error containing `OAuth2Error`.
- **`OAuth2AuthorizationException`**: authorization/token lifecycle error containing `OAuth2Error`.
- **`AuthenticationException`**: Spring Security authentication error hierarchy.
- **`WebClientResponseException`** or HTTP client exceptions: errors when calling remote API/Token/UserInfo depending on implementation.
- Transport/TLS/timeout errors from the HTTP client, Redis, or JDBC.

**There is no single exception type for every stage.** Exceptions can be wrapped. Stage classification should be based on the **instrumentation/request location** rather than matching exception text alone.

### 13.1. Example Mapper for OAuth2Error

```java
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;
import org.springframework.security.oauth2.core.OAuth2Error;

public final class SafeOAuthErrorCode {

    private SafeOAuthErrorCode() {}

    public static String classify(Throwable exception) {
        OAuth2Error error = null;

        if (exception instanceof OAuth2AuthenticationException auth) {
            error = auth.getError();
        } else if (exception instanceof OAuth2AuthorizationException authorization) {
            error = authorization.getError();
        }

        if (error == null) {
            return "non_oauth2_error";
        }

        String code = error.getErrorCode();
        if (code == null) {
            return "unknown_oauth2_error";
        }

        return switch (code) {
            case "access_denied" -> "access_denied";
            case "invalid_request" -> "invalid_request";
            case "invalid_client" -> "invalid_client";
            case "invalid_grant" -> "invalid_grant";
            case "invalid_scope" -> "invalid_scope";
            case "temporarily_unavailable" -> "temporarily_unavailable";
            default -> "other_oauth2_error";
        };
    }
}
```

This is a **small classifier example**, not a complete stage classification mechanism. Stage needs to be passed from the call site or a reliably determined context. Error descriptions must not be concatenated into UI output.

## 14. Servlet OAuth2 Login Failure Handler

Spring Security MVC allows configuring an `AuthenticationFailureHandler` in `oauth2Login`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;

@Configuration
public class OidcFailureConfiguration {

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {

        AuthenticationFailureHandler failureHandler =
            (request, response, exception) -> {

                String safeReason = "authentication_failed";

                if (exception instanceof OAuth2AuthenticationException oauth2) {
                    String code = oauth2.getError().getErrorCode();
                    if ("access_denied".equals(code)) {
                        safeReason = "authorization_declined";
                    } else if ("invalid_grant".equals(code)) {
                        safeReason = "token_exchange_failed";
                    }
                }

                // Record redacted metrics/logs here if needed.
                // Do not output exception.message, code/state/tokens.
                response.sendRedirect(
                    request.getContextPath() +
                    "/login?error=" + safeReason
                );
            };

        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(oauth2 -> oauth2
                .failureHandler(failureHandler)
            )
            .build();
    }
}
```

The example demonstrates mapping to **fixed labels** and cannot infer the stage perfectly: `invalid_grant` at the login callback is likely token exchange, whereas in a refresh token flow it requires a different stage. In production, integrate telemetry at the exact step/Client manager.

### 14.1. Failure Handler Does Not Observe Every Initiation Error

`oauth2Login().failureHandler(...)` typically handles authentication failures in the OAuth2 Login filter. However, errors in `OAuth2AuthorizationRequestRedirectFilter`, startup discovery, or an OP error page that does not redirect back to the RP may not pass through it. Therefore, a dashboard built solely from this failure handler can miss pre-callback errors.

### 14.2. Do Not Use a "Fake Login Success" Fallback

Do not do this:

```java
// Do not do this:
// if (stateMismatch || badSignature) { createAuthenticatedUserAnyway(); }
```

When Spring rejects a request because of state, nonce, issuer, audience, or signature, it is a **security rejection** that must be preserved.

### 14.3. Avoid Login Loops

If `/login?error=...` immediately redirects the user back to `/oauth2/authorization/company`, a configuration error can create a redirect loop. You need a public error page, an appropriate message, and user-initiated retry.


## 15. Reactive WebFlux: Error Classification and Routing

In WebFlux, use reactive abstractions such as `SecurityWebFilterChain`, `ServerHttpSecurity`, and `ServerAuthenticationFailureHandler`. Do not mix Servlet `HttpSecurity`/`AuthenticationFailureHandler` into WebFlux.

Example of a failure handler redirecting the user to a fixed URL:

```java
import java.net.URI;

import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.ServerAuthenticationFailureHandler;

@Bean
SecurityWebFilterChain reactiveChain(ServerHttpSecurity http) {

    ServerAuthenticationFailureHandler failureHandler =
        (webFilterExchange, exception) -> {

            var response = webFilterExchange.getExchange().getResponse();
            response.setStatusCode(HttpStatus.SEE_OTHER);
            response.getHeaders().setLocation(
                URI.create("/login?error=authentication_failed")
            );

            return response.setComplete();
        };

    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/", "/login", "/error").permitAll()
            .anyExchange().authenticated()
        )
        .oauth2Login(login -> login
            .authenticationFailureHandler(failureHandler)
        )
        .build();
}
```

This is a directional example: a production implementation should use a built-in redirect handler when appropriate and add logging/metrics without leaking data.

### 15.1. Reactor Context and Token Manager

In WebFlux, Authentication is propagated via Reactive SecurityContext/Reactor context. If a pipeline runs outside an HTTP request, do not assume `ServerWebExchange` and session are always present.

A background job/worker needs a service-based reactive manager if working with `client_credentials` or previously granted authorized clients. Missing Reactive context can cause token/Authentication lookup errors—**not an OP consent denial**.

### 15.2. Do Not Block in the Failure Handler

Do not call `block()` on the Netty event-loop to write an audit record to the database or call external diagnostics. Blocking can exhaust the event-loop and cause many requests to time out. Use reactive storage or a properly managed boundary.

## 16. OIDC UserInfo Customization

When using `OidcUserService`, the application can add mapping from the external user to an internal account. Distinguish between:

1. **UserInfo HTTP error:** The API actually returns 401/403/5xx.
2. **UserInfo validation error:** `sub` does not match ID Token, invalid JSON.
3. **Optional claim absent:** missing email/name even though identity is valid.
4. **Business mapping error:** account ownership, unique constraint, tenant policy.
5. **Storage error:** database/Redis unavailable.

### 16.1. Wrappers Should Not Swallow Security Errors

```java
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

public final class AuditedOidcUserService
        implements OAuth2UserService<OidcUserRequest, OidcUser> {

    private final OidcUserService delegate = new OidcUserService();

    @Override
    public OidcUser loadUser(OidcUserRequest request) {
        try {
            return delegate.loadUser(request);
        } catch (RuntimeException ex) {
            // Record redacted metric/log category.
            // Do not log raw access token/ID token/UserInfo response.
            throw ex;
        }
    }
}
```

In a real application, the wrapper is wired into the appropriate OIDC user service configuration. This lesson does not assume the class is auto-installed just by being declared. The goal is observability **without bypassing protocol/security errors**.

### 16.2. Optional Profile Differs from Identity Validation

If UserInfo lacks `email`, the app may prompt the user to enter/verify an email separately according to policy. However, if UserInfo `sub` differs from ID Token `sub`, **the response must be rejected**—do not fall back to email or the ID Token and treat an invalid UserInfo response as "non-critical missing data".

## 17. Refresh Errors and Manager Failure Handlers

`OAuth2AuthorizedClientManager` coordinates tokens for outbound APIs. You can configure `OAuth2AuthorizedClientProvider` with authorization code, refresh token, and client credentials as required.

If the Token Endpoint returns `invalid_grant` during refresh:

- Stop using the invalid refresh token.
- Do not retry indefinitely with the same token.
- Check whether the error came from a rotation race or revocation/expiry.
- If required, remove/invalidate the corresponding authorized client by registration/principal.
- Record the external connection state as `RECONNECT_REQUIRED`.
- Prompt reauthorization with appropriate UX.

Some Spring manager implementations have default success/failure handlers. **If you replace `setAuthorizationFailureHandler` only to log without preserving the cleanup policy**, the application may repeatedly reuse an invalid refresh token. Check your exact version and storage implementation.

### 17.1. WebClient Failure Handler Differs from Login Failure Handler

- **OAuth2 Login authentication failure handler:** handles user login callback/Authentication.
- **Authorized client manager authorization failure handler:** handles authorize/refresh errors at the Token Endpoint.
- **WebClient OAuth2 filter authorization failure handler:** can handle OAuth2 error responses from a Resource Server and update/remove the authorized client according to policy.

Do not use a single handler class under the assumption that all three legs share the same semantics.

## 18. UX: Communicate the Right Reason Without Leaking Secrets

| Case | Suggested Message | Action |
|---|---|---|
| User cancelled consent | "You did not complete granting permission." | Retry when ready |
| `state`/session expired | "Your login session has expired. Please start again." | Start a new OAuth2 login |
| OP temporarily down | "The sign-in service is temporarily unavailable." | Try again later |
| Client configuration error | "Unable to complete sign-in. Support code: …" | Contact support |
| ID Token validation failed | "Unable to verify your sign-in session." | Stop flow, investigate |
| UserInfo unavailable | "Unable to load account information right now." | Retry/fallback policy |
| API connection refresh token revoked | "External service needs to be reconnected." | Reconnect the right provider |
| Reports API 403 | "You do not have permission to perform this action." | Permissions/scopes |

Do not expose raw `error_description`, stack traces, internal hostnames, Client secrets, `code`, `state`, tokens, or cookies on the error page.

### 18.1. Independent Correlation ID

`state` is a parameter to prevent OAuth2 flow mix-ups; **do not use it as a support ID/tracing ID**. Generate an independent, non-sensitive correlation ID for users to send to support.

### 18.2. Distinguish User Errors from Incidents

A high volume of `access_denied` from users declining consent may not require an incident alert. Conversely, a surge of `invalid_client` after secret rotation or callback state failures after a deployment is an alarming signal.

## 19. Safe Structured Logging

A suggested event:

```json
{
  "event": "oauth2_login_failure",
  "stage": "TOKEN_EXCHANGE",
  "category": "CLIENT_CONFIGURATION",
  "protocol_error_code": "invalid_client",
  "grant_type": "authorization_code",
  "registration_id": "company",
  "provider_alias": "enterprise-op",
  "http_status": 401,
  "duration_ms": 182,
  "correlation_id": "internal-random-id",
  "outcome": "failure"
}
```

This is an application-defined schema.

### 19.1. Useful Fields

- `stage`, `category`, and `outcome`.
- `registration_id` and `provider_alias` bounded from config.
- `grant_type`: `authorization_code`, `refresh_token`, `client_credentials`.
- Normalized or bounded `protocol_error_code`.
- `http_status`, `duration_ms` when a dependency call occurred.
- `dependency` such as `authorization`, `token`, `userinfo`, `jwks`, `session_store`.
- Independent `correlation_id`.
- `exception_family`, not the full message from the provider.

### 19.2. Never Log

```text
authorization code
state
nonce
code_verifier
access_token
refresh_token
id_token
client_secret
Authorization header
Cookie / Set-Cookie header
full callback URL with query
raw UserInfo profile JSON
untrusted error_description
```

Check reverse proxies, APMs, HTTP client interceptors, request/response body logging, and tracing as well. A filter that redacts at the controller does not stop a proxy from logging the full callback URL.

### 19.3. Choose Low-Cardinality Metric Labels

```text
oauth2.login.failure{stage="callback",registration="company",category="security_rejection"}
oauth2.token.failure{grant="refresh_token",registration="calendar",error="invalid_grant"}
oauth2.userinfo.failure{registration="company",category="network"}
```

Do not use user ID, email, token, state, raw URL, or error description as metric labels. Those values are both sensitive and create huge time-series cardinality.

## 20. Logs, Metrics, and Tracing Answer Different Questions

| Tool | Question Answered | Example |
|---|---|---|
| Metrics | Which errors are spiking, and at which stage? | Refresh `invalid_grant` spiking across cluster |
| Structured logs | Which errors share the same registration/provider? | `company` + `invalid_client` after deploy |
| Distributed traces | Which dependency is slow? | Token Endpoint 4s, UserInfo 100ms |
| Audit events | Who performed link/disconnect? | Internal account created connection |
| Synthetic checks | Is the login flow/provider working? | OIDC test tenant logs in periodically |
| OP admin logs | Why did the provider reject the request? | Client disabled, consent policy |

### 20.1. Browser Redirects Break Traces

Authorization Code Flow sends the browser through the OP and back to the RP. Do not assume a single trace automatically spans all three origins. You can use correlation stored server-side per session/request within the trust boundary; do not put secret tracing headers or state/tokens into the OP's URL.

### 20.2. Do Not Log Token Endpoint Bodies

An HTTP client debug flag can log `refresh_token` or `client_secret` in the form body. Only record status, latency, sanitized error code, and dependency identity.

## 21. Symptom-Based Diagnostic Runbook

First step: **which page did the user see?**

```text
Did not leave Portal
  -> Authorization initiation / configuration / session

Reached OP, failed at OP
  -> Authorization decision / provider policy

OP redirected back to Portal, Portal showed error
  -> Callback correlation / token / ID Token / UserInfo

Portal login succeeded, API failed
  -> Authorized client / refresh / Resource Server
```

This is initial guidance, not a replacement for logs/traces.

### 21.1. 10-Step Diagnostic Procedure

1. Identify the actual **stage**.
2. Identify the **registration ID**, expected issuer, and provider alias.
3. Determine whether the error is at RP, OP Authorization, Token, UserInfo, or API.
4. Distinguish the protocol error code from the HTTP status/exception class.
5. For callbacks: check whether session, saved request, state, or nonce/PKCE was lost.
6. For Token Endpoint: check **grant type** and Client authentication.
7. For ID Token: check signature/issuer/audience/nonce/JWKS; do not skip validation.
8. For UserInfo: check 401/403, JSON, `sub` matching, optional claims.
9. For post-login APIs: check access token scope/audience and authorized client storage.
10. Conclude the owner and action; record the correlation ID/redacted log.

### 21.2. Root Cause → Action Matrix

| Root Cause | Safe Handling |
|---|---|
| User denied consent | Notify and let the user manually retry |
| Missing state/session | Fix cookie/session store/routing; do not bypass |
| Invalid redirect URI | Fix OP registration/public host/proxy |
| `invalid_client` | Check Client credentials/config, alert owner |
| Code `invalid_grant` | Check PKCE/redirect/code reuse, start a new flow |
| Refresh `invalid_grant` | Check rotation/revocation, cleanup/reconnect |
| Invalid ID Token | Stop Authentication; investigate issuer/JWKS/validator |
| UserInfo HTTP 401 | Check access token/endpoint/consent |
| UserInfo `sub` mismatch | Do not use response; investigate security |
| OP 503/timeout | Backoff, monitor, show unavailable message |
| Reports API 403 | Check scope/authorization; do not auto-logout |

## 22. Common Misdiagnoses

### 22.1. "There is `access_denied`, so the system is broken"

The user may have just cancelled consent. Count the `USER_DENIED` category separately instead of mixing it into infrastructure errors.

### 22.2. "`invalid_grant` means wrong password"

Incorrect. This is a Token Endpoint error, usually related to code/refresh/token grant, and does not directly prove the user entered a wrong password.

### 22.3. "UserInfo returned 401, so the ID Token has a bad signature"

Incorrect. ID Token and access token serve different purposes. UserInfo can reject a Bearer access token even when the ID Token is valid.

### 22.4. "API returned 403, so force the user to log in again"

The API may be missing a scope/role or business permission. Forcing re-login with the same token/scopes will not grant extra permissions.

### 22.5. "Session not found, let's disable the state check"

Unsafe. This is the boundary against login CSRF/callback injection. Fix the session store/cookie/route.

### 22.6. "Token Endpoint returned 200, so login definitely succeeded"

Incorrect. ID Token validation, UserInfo subject matching, account mapping, and session persistence can still fail.

### 22.7. "If a UserInfo Endpoint exists, every login must call it"

Incorrect. Many OIDC flows do not require UserInfo depending on configuration/claims.

### 22.8. "OIDC login succeeded, so every API can use that access token"

Incorrect. Resource Servers have different audiences/scopes/policies.

## 23. Stage-by-Stage Testing

### Authorization initiation

- Registration ID does not exist.
- Issuer discovery 404/unavailable.
- Incorrect redirect URI/forwarded headers.
- Authorization request repository fails to save.
- Custom resolver throws an error.
- User cancels consent.

### Callback

- Missing `state`.
- Invalid `state` or `state` does not belong to the session.
- Authorization request expired.
- Replayed callback.
- Multi-tab concurrent flows.
- Callback cookie blocked when `response_mode=form_post`.
- Callback carries an error from the OP and is displayed safely.

### Token Endpoint

- Authorization code already used/expired.
- Wrong Client authentication.
- PKCE verifier mismatch.
- Redirect URI mismatch.
- HTTP 429/500/timeout/TLS.
- Token response missing required fields.
- No infinite retries on code.

### OIDC ID Token

- Invalid signature.
- Wrong `iss`/`aud`.
- Expired token.
- Nonce mismatch.
- JWKS unavailable/rotation.
- Invalid claim type/format.
- Validation is never bypassed.

### UserInfo

- HTTP 401 `invalid_token`.
- HTTP 403 `insufficient_scope`.
- 5xx/timeout/HTML response.
- JSON parse error.
- Missing `sub`.
- **`sub` mismatch with ID Token**.
- Optional `email` missing.
- Business mapping/tenant conflict.

### Token refresh/API

- Refresh token revoked/rotated.
- Concurrent refresh across two pods.
- Access token wrong audience.
- API 401 and 403.
- Client token sent to the wrong HTTP origin.
- External connection fails while portal session remains valid.

## 24. Safe Unit Test for Error Classifier

```java
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SafeOAuthErrorCodeTest {

    @Test
    void accessDeniedUsesFixedCategory() {
        OAuth2Error error = new OAuth2Error(
            "access_denied",
            "Untrusted provider description",
            null
        );

        var exception = new OAuth2AuthenticationException(error);

        assertEquals(
            "access_denied",
            SafeOAuthErrorCode.classify(exception)
        );
    }

    @Test
    void unknownProviderCodeDoesNotLeakDescription() {
        OAuth2Error error = new OAuth2Error(
            "provider_specific_error",
            "Sensitive text from a provider",
            null
        );

        var exception = new OAuth2AuthenticationException(error);

        assertEquals(
            "other_oauth2_error",
            SafeOAuthErrorCode.classify(exception)
        );
    }
}
```

The test only checks the mapper. It does **not** execute browser redirects, state/PKCE, token exchange, JWKS, or UserInfo. `oidcLogin()` in Spring Security Test is also a mock Authentication and does not replace end-to-end protocol testing.

### 24.1. Do Not Depend on Verbatim Framework Exception Text

Messages/stack traces may change across Spring versions and providers. Tests should assert:

- Outcome/stage.
- Standard error code when present.
- No Authentication created when validation fails.
- No credential leakage.
- Proper cleanup/reauthorization.
- Appropriate error UI and support correlation.

## 25. Quick Incident Lookup Table

| Symptom | Suggested Stage | What to Check First |
|---|---|---|
| Login link does not redirect | Initiation | Registration ID, resolver |
| OP reports invalid redirect | Authorization | Public URI and OP whitelist |
| User clicked Cancel | Authorization response | `access_denied` |
| Callback missing request | Callback | Session/cookie/Redis |
| Callback state mismatch | Callback | Flow correlation/multi-tab |
| Token `invalid_grant` at login | Token exchange | Code/PKCE/redirect URI |
| Token `invalid_client` | Token exchange | Client authentication |
| Token 200 but JWT fails | ID Token | Signature/issuer/audience/nonce |
| UserInfo 401 | UserInfo | Access token/scopes |
| UserInfo `sub` mismatch | UserInfo | Reject identity response |
| Missing email | UserInfo/mapping | Optional claims/onboarding |
| Refresh invalid_grant | Refresh | Rotation/revocation |
| Reports API 403 | Downstream API | Scope/role/resource |
| Fails only with multiple pods | Session/storage | Shared session, principal key |
| Fails after secret rotation | Token Endpoint/config | Client secret/key/mTLS |
| Fails after changing registration ID | Storage/config | Persisted token key and callback |

## 26. Scenario Exercises

### Exercise 1: User declines consent

OP redirects `?error=access_denied&state=...`. Where is the error?

**Suggested answer:** Authorization decision; the callback only carries the error information back to the RP. Display "permission not completed" instead of `invalid_grant`.

### Exercise 2: Callback missing authorization request

The browser is redirected back to the Portal by the OP, but Spring reports that the saved request cannot be found.

**Suggested answer:** Callback correlation/session store. Check cookies, TTL, multi-node routing; do not remove state validation.

### Exercise 3: `invalid_grant` right after callback

The code was already used once due to a browser refresh.

**Suggested answer:** The Token Endpoint does not accept code reuse; initiate a new login flow and investigate request retry/replay.

### Exercise 4: `invalid_grant` after one week

A background job refreshes an old token after rotation.

**Suggested answer:** TOKEN_REFRESH, not login. Check stale refresh token/concurrency and reconnect.

### Exercise 5: `invalid_client` after deploy

The secret was just rotated at the OP, but the RP is still using the old secret.

**Suggested answer:** Client authentication/configuration. Alert the owner; do not ask users to reset their passwords.

### Exercise 6: ID Token wrong audience

The token has a valid signature, but `aud=other-client`.

**Suggested answer:** ID_TOKEN_VALIDATION must fail; signature does not replace audience validation.

### Exercise 7: UserInfo `sub` mismatch

ID Token `sub=user-A`, UserInfo `sub=user-B`.

**Suggested answer:** Security rejection; do not map profile B onto user A.

### Exercise 8: UserInfo does not return email

`sub` is valid, but `email` is absent.

**Suggested answer:** Optional claim; requires business mapping/onboarding policy, do not treat it as an invalid token.

### Exercise 9: API returns 403

Portal is logged in; Reports API lacks scope.

**Suggested answer:** Resource Server authorization; do not automatically switch to another provider's token.

### Exercise 10: Callback POST loses cookie

OP uses `form_post`; browser does not send the Lax session cookie.

**Suggested answer:** Check SameSite/response mode/HTTPS; do not bypass callback correlation.

### Exercise 11: JWKS outage

Token Endpoint returns 200, but RP cannot fetch signing keys.

**Suggested answer:** Stage ID_TOKEN_VALIDATION, dependency JWKS. Do not accept unsigned tokens.

### Exercise 12: Error description contains PII

The provider returns an email/user ID in `error_description`.

**Suggested answer:** Redact, use fixed error codes and a correlation ID; do not log verbatim.

### Exercise 13: Two providers mixed up

Login was initiated with `corp`, yet the token request goes to `partner`.

**Suggested answer:** Check state/registration/issuer binding; do not try Token Endpoints one by one.

### Exercise 14: Metrics record state in a label

`oauth2_failures{state="..."}`.

**Suggested answer:** Wrong because it is sensitive and high-cardinality. Only use bounded stage/error category/registration.

### Exercise 15: UserInfo HTTP 401 while ID Token is valid

**Suggested answer:** The access token for UserInfo was rejected. Distinguish Bearer errors from ID Token validation.

### Exercise 16: Logged-in user cannot call Calendar API

The Calendar refresh token was revoked, but the Corp portal session is still valid.

**Suggested answer:** Mark the connection `RECONNECT_REQUIRED` instead of logging out the entire Portal by default.

## 27. Implementation Checklist

- [ ] Separate classification exists for initiation, authorization decision, callback, token, ID Token, UserInfo, refresh, and API.
- [ ] HTTP status, OAuth2 error code, exception type, and stage are stored in separate fields.
- [ ] Authorization `access_denied` is distinguished from provider outages.
- [ ] Callback state/authorization request is always verified.
- [ ] PKCE verifier/nonce/issuer/audience are never bypassed on error.
- [ ] Token `invalid_grant` includes `grant_type` to distinguish code vs. refresh.
- [ ] Invalid authorization codes or refresh tokens are never retried indefinitely.
- [ ] UserInfo `sub` is matched against the ID Token.
- [ ] Missing optional email is not confused with identity mismatch.
- [ ] UserInfo 401 is not confused with post-login Resource Server 401.
- [ ] Dedicated handling exists for DB/session store errors.
- [ ] Failure handlers return fixed messages and do not expose provider descriptions.
- [ ] Pre-redirect initiation is observed, not just the OAuth2 Login callback filter.
- [ ] Timeouts and monitoring are configured for Token Endpoint, JWKS, and UserInfo.
- [ ] Metric labels have low cardinality.
- [ ] Codes/state/nonce/verifiers/tokens/cookies/Client secrets/full callback URLs are never logged.
- [ ] Correlation ID is independent of `state`.
- [ ] Negative tests exist for every stage.
- [ ] A runbook identifies owners and recovery steps.
- [ ] Resource Server API errors do not force local logout outside policy.
- [ ] Multi-provider, multi-instance, and refresh rotation scenarios are tested.
- [ ] No validation is disabled simply to reduce login errors.

## 28. References

1. [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): authorization response and token errors.
2. [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): `invalid_token`, `insufficient_scope`, and `WWW-Authenticate`.
3. [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): redirect, PKCE, token lifecycle.
4. [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636): `code_verifier` and `code_challenge`.
5. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token validation, UserInfo `sub` matching.
6. [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): provider metadata/JWKS/UserInfo.
7. [Spring Security Reference — OAuth2 Login (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): login flow and error handling.
8. [Spring Security Reference — OAuth2 Client (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): authorized clients/managers/refresh.
9. [Spring Security Reference — OAuth2 Login (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html): Reactive OAuth2/OIDC Login.
10. [Spring Security API — OAuth2Error](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/OAuth2Error.html): code/description/URI.
11. [Spring Security API — OAuth2AuthenticationException](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/OAuth2AuthenticationException.html): authentication failures.
12. [Spring Security API — OAuth2AuthorizationException](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/OAuth2AuthorizationException.html): authorization failures.
13. [Spring Security API — OidcUserService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/oidc/userinfo/OidcUserService.html): OIDC user loading.
14. [Spring Security Reference — Observability](https://docs.spring.io/spring-security/reference/servlet/observability/index.html): telemetry by Spring Security version.
15. [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): safe logging without recording secrets.

## 29. Summary

**An OAuth2/OIDC error should not be identified solely by HTTP status or exception message.** Identify the **stage**, **originating endpoint**, **error code**, **grant type**, **ClientRegistration**, **dependency**, and **root-cause category**. An authorization decision can deny consent; a callback can fail due to state/session; the Token Endpoint can reject a code or refresh grant; ID Token validation can reject an invalid issuer/audience/signature; UserInfo can reject an access token or return a mismatched `sub`.

In Spring Security, failure handlers should transition the user to **a safe error state**, rather than bypassing state, PKCE, nonce, ID Token validation, or trying another provider's credentials. Observe using **redacted** structured logs, metrics, and traces, while maintaining security tests for error paths and runbooks so operations teams fix the true root cause.

Properly classifying the four stages **authorization → callback → token → UserInfo** (and related substages) reduces misdiagnosis, prevents dangerous retries, avoids disrupting still-valid login sessions, and preserves OAuth2/OIDC security boundaries even when infrastructure or providers experience outages.
