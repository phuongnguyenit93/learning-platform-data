# 28.7. 401, 403, 429, and 5xx Errors from Downstream or Provider

## 1. The Problem: Same 401 or 503, Yet Different Handling Required

Suppose **Employee Portal** is built with **Spring Boot 3, Spring Security 6**, using **OAuth2 Login/OIDC Client** to authenticate users via an OpenID Provider and then using an access token to call the **Orders API**:

~~~text
Browser
  -> Employee Portal (OAuth2/OIDC Client, BFF)
      -> Company OpenID Provider / Authorization Server (AS)
      -> Orders API (OAuth2 Resource Server)
~~~

One morning, the system records:

~~~text
08:35  Orders API -> HTTP 401 Bearer invalid_token
08:40  Orders API -> HTTP 403 Bearer insufficient_scope
08:45  Token endpoint -> HTTP 429 Retry-After: 30
08:50  Orders API -> HTTP 503 Service Unavailable
08:55  Token endpoint -> HTTP 400 invalid_grant
09:00  Portal -> Browser HTTP 401
~~~

If the application applies a blanket rule:

~~~text
Any error => refresh token => retry 5 times => log user out
~~~

it causes several problems:

- **403** may mean insufficient permissions; refreshing the token does not grant additional scopes.
- **429** is rate limiting; retrying immediately worsens the situation.
- **503** is usually a temporary service outage; deleting the authorized client will not fix it.
- **invalid_grant** may result from a rotated/revoked refresh token; endlessly retrying the same credential is dangerous.
- **401 from the Portal** may simply mean the browser is not logged in, completely different from a **401 from the Orders API**.

**Lesson principle:** before deciding to refresh, re-login, retry, delete tokens, or display a message, determine **where the error came from, which request failed, which credential was involved, and which OAuth2 error semantics apply**.

> Context: Java 17+, Spring Security OAuth2 Client with Servlet/RestClient or WebClient, plus Reactor examples for Reactive applications. All illustrative endpoints/token strings are fake. Never infer that all HTTP 4xx/5xx errors are login errors; preserve the boundaries between authentication, authorization, and availability.

## 2. Map of Potential Failure Points

~~~mermaid
flowchart TD
    U["Browser"] --> RP["Portal / OAuth2 Client"]
    RP --> OP["OpenID Provider"]
    OP --> AUTH["Authorization endpoint /authorize"]
    OP --> TOKEN["Token endpoint /token"]
    OP --> UI["UserInfo endpoint"]
    OP --> JWKS["Discovery/JWK Set metadata"]
    RP --> STORE["Authorized Client Store"]
    RP --> API["Orders API / Resource Server"]
    API --> DB["Downstream DB / service dependencies"]
    RP --> U
~~~

An end-to-end request may involve multiple distinct HTTP round-trips:

1. Browser calls Portal.
2. Portal redirects browser to the authorization endpoint.
3. Browser returns authorization code to the callback.
4. Portal calls token endpoint to exchange the code or refresh a token.
5. Portal may call UserInfo endpoint and fetch metadata/JWKS.
6. Portal loads `OAuth2AuthorizedClient` from the store.
7. Portal sends the access token to the Orders API.
8. Orders API calls its database or microservices.

**Each HTTP response has a different sender, trust boundary, and handling action.**

## 3. Quick Classification Table by HTTP Status and Source

| Status/Signal | Where | Initial Interpretation | What Not to Do |
|---|---|---|---|
| **401 Unauthorized** | Resource Server | Access token missing, invalid, expired, revoked, or unacceptable | Do not immediately log out all users |
| **401 Unauthorized** | Authorization Server token endpoint | Likely client authentication error, often with OAuth error `invalid_client` | Do not treat as an expired API access token |
| **401 Unauthorized** | UserInfo endpoint | Access token used to call UserInfo was rejected | Do not skip ID Token/issuer validation |
| **401 Unauthorized** | Portal → Browser | Browser lacks valid authentication or session expired | Do not assume Orders API returned 401 |
| **403 Forbidden** | Resource Server | Request identified, yet lacks sufficient permissions/scope/resource policy | Do not infinitely refresh to escalate permissions |
| **403 Forbidden** | Portal | User is logged in, yet not permitted to use the feature | Do not switch client registrations to bypass RBAC |
| **429 Too Many Requests** | AS/token endpoint | Client/IP/tenant rate limited | Do not retry immediately or trigger a token storm |
| **429 Too Many Requests** | Downstream API | API quota/concurrency/rate limit | Do not delete the authorized client |
| **500 Internal Server Error** | AS/downstream | Server processing error | Do not assume the token is invalid |
| **502 Bad Gateway** | Reverse proxy/gateway | Upstream error response or invalid upstream connection | Do not refresh tokens on status 502 |
| **503 Service Unavailable** | AS/downstream | Temporarily unavailable/overloaded/maintenance | Do not retry indefinitely |
| **504 Gateway Timeout** | Gateway | Upstream timed out | Do not auto-replay non-idempotent requests |
| `invalid_grant` | AS token endpoint | Code/refresh token/grant credential invalid | Do not blindly retry the same one-time credential |
| `invalid_scope` | AS token endpoint | Requested scope invalid/not granted | Do not escalate permissions in the client |

**HTTP status is only the first clue.** Combine it with:

- URL/endpoint and method.
- `WWW-Authenticate` response header if present.
- OAuth2 JSON `error` code from the token endpoint.
- `Retry-After` when present.
- Authorization context and registration ID.
- Request ID/correlation ID.
- Safety of retrying.

## 4. Separating Errors from Portal, Authorization Server, and Resource Server

### 4.1. Portal Returns 401 to the Browser

Example:

~~~http
GET /api/me HTTP/1.1
Host: portal.example.test

HTTP/1.1 401 Unauthorized
~~~

This could mean:

- The browser has no valid session yet.
- The server session expired.
- The API SecurityFilterChain requires authentication.
- The request omitted cookies or bearer credentials per policy.

It does **not** prove the access token stored by the Portal to call the Orders API has expired.

### 4.2. Orders API Returns 401 to the Portal

~~~http
GET /api/orders HTTP/1.1
Host: orders.example.test
Authorization: Bearer <redacted>

HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

The Portal is authenticated with the browser, yet the access token sent to the Orders API was rejected. Handle the **authorized-client/token context** rather than deleting the browser session by default.

### 4.3. Token Endpoint Returns an Error

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.test

HTTP/1.1 400 Bad Request
Content-Type: application/json

{"error":"invalid_grant"}
~~~

This error happened **while requesting a token**, unlike having a token already and having the Orders API reject it.

### 4.4. UserInfo or JWK Endpoint Fails

During OIDC login, token exchange may succeed while UserInfo/JWK fetching fails. Distinguish protocol validation/remote dependencies; never treat every case as a downstream Orders API error.

## 5. Distinguishing HTTP Status from OAuth2 Error Code

The OAuth2 token endpoint typically returns JSON by convention:

~~~json
{
  "error": "invalid_grant",
  "error_description": "Authorization grant is invalid"
}
~~~

In Spring Security, errors are modeled by types such as:

~~~java
org.springframework.security.oauth2.core.OAuth2Error
org.springframework.security.oauth2.core.OAuth2AuthorizationException
~~~

Each error can have `errorCode`, `description`, and `uri`.

**HTTP 400 does not tell the whole OAuth story**, because:

~~~text
400 invalid_grant
400 invalid_scope
400 unauthorized_client
400 unsupported_grant_type
~~~

can each require different actions.

Conversely, a server may return HTTP 500 with a body that is not OAuth2 error JSON; do not try to parse it and assume `invalid_grant`.

### 5.1. Common OAuth2 Token Errors

| OAuth2 error | Common Causes | How to Handle |
|---|---|---|
| `invalid_grant` | Code expired/used, wrong redirect URI, refresh token revoked/rotated | Do not blindly retry same credential; consider reauthorization |
| `invalid_client` | Invalid Client ID/secret/mTLS/private_key_jwt | Check config/secrets/rotation |
| `unauthorized_client` | Client not permitted to use the grant | Fix policy/registration |
| `invalid_scope` | Requested scope invalid | Fix requested scopes/consent/config |
| `unsupported_grant_type` | AS does not support the grant | Fix grant/AS capability |
| `invalid_request` | Missing or invalid parameter | Fix request converter/protocol |
| `temporarily_unavailable` | AS temporarily unable to serve request | Budgeted retry depending on context |

Do not display raw `error_description` to users if it contains internal details or tokens/credentials; messages from external systems are **untrusted data**.

## 6. 401 from Resource Server: Understanding Bearer Authentication

A Resource Server may return:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders", error="invalid_token"
~~~

Possible causes:

1. Access token expired.
2. Token was revoked or is no longer valid.
3. Wrong issuer.
4. Wrong audience/resource indicator.
5. Invalid signature/algorithm/key.
6. Authorization header was not sent.
7. Header was stripped by a proxy/interceptor.
8. Another token type (e.g., ID Token) was sent by mistake.
9. Resource Server lacks config/keys/clock sync.

**Not every 401 can be fixed by refreshing the token.**

### 6.1. WWW-Authenticate Is an Important Signal

RFC 6750-style examples:

~~~http
WWW-Authenticate: Bearer error="invalid_token"
~~~

or:

~~~http
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.read"
~~~

The header helps distinguish an invalid token from insufficient permissions within the Bearer scheme. However, the header may be missing, incomplete, or carry multiple authentication challenges.

**Do not rely solely on whether a string contains `invalid_token`** while ignoring scheme, origin, status, and trust context.

### 6.2. When Should an Old Authorized Client Be Removed?

If a trusted Resource Server returns **401 Bearer invalid_token** for the sent token, the application can:

- Mark the authorized client as no longer valid.
- Remove the corresponding cache/authorized-client entry per policy.
- Call `OAuth2AuthorizedClientManager` to issue/refresh a new token.
- Retry **once within limits** for safe requests when reauthorization succeeds.

However, consider:

- Was the token actually revoked, or is the API misconfigured for issuer/audience?
- Will a new token with the same scope/audience solve it?
- Does a refresh token exist and remain valid?
- Are multiple requests refreshing concurrently?

Never automatically log out the browser on a downstream API 401.

### 6.3. If 401 Lacks Bearer invalid_token

Example:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="internal"
~~~

This is not proof that the OAuth2 access token is invalid. The request may have hit the wrong endpoint/proxy, or the API may require a different authentication scheme.

Analyze the exact downstream authentication contract.

### 6.4. If a New Token Still Returns 401

Do not loop:

~~~text
401 -> refresh -> 401 -> refresh -> 401 -> ...
~~~

Stop after the budget and check issuer, audience, scope, clock skew, client registration, JWKS, Resource Server config, and log correlation.

## 7. 403 from Resource Server: Difference Between Authentication and Authorization

Example:

~~~http
GET /api/admin/audit HTTP/1.1
Authorization: Bearer <valid-access-token>

HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope",
                  scope="admin.read"
~~~

Common interpretation: the token was recognized, yet **lacks sufficient scope/permissions** for the resource.

### 7.1. A Valid Access Token Does Not Mean Every API Allows Access

The Resource Server checks:

- Scope/authority.
- Role/tenant membership.
- Resource ownership.
- Business policy.
- Authentication assurance/step-up policy if applicable.

A token with `orders.read` does not automatically grant `admin.read`.

### 7.2. Why Doesn't Refreshing Automatically Add Scopes?

A refresh token normally obtains a new token for the grant and already-approved permissions. It does not expand user consent or authorization on its own:

~~~text
Old AT: scope=orders.read
Refresh: still issued scope=orders.read
Admin API: requires admin.read
=> 403 still persists
~~~

Solutions usually lie in:

- Requested scopes/IdP client permissions.
- User consent/reauthorization.
- Application RBAC.
- Resource Server policy or resource ownership.

Never "fix" a 403 by switching to a higher-privilege service token and bypassing user authorization.

### 7.3. 403 Is Not Always insufficient_scope

An API may return 403 because:

~~~text
tenant membership suspended
resource belongs to another user
business feature not licensed
IP/network policy
account or document access denied
~~~

When a Bearer challenge is absent, do not assume scope is wrong. Check the API contract and safe audit logs.

### 7.4. UX for 403

Appropriate message:

~~~text
You are signed in, but you do not have permission to perform this action.
Contact your administrator if you need access.
~~~

Never trigger a login loop just because an API returned 403.

## 8. 429 Too Many Requests: Rate Limiting from AS and Downstream

Token endpoint example:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
Content-Type: application/json
~~~

Or Orders API:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: Wed, 18 Nov 2026 10:30:00 GMT
~~~

`Retry-After` typically takes two forms:

1. **Delta-seconds** — number of seconds to wait.
2. **HTTP-date** — timestamp when retrying is allowed.

**429 does not prove the access token is invalid.** It signals that the server is enforcing rate limits by IP, client ID, tenant, subject, endpoint, or quota policy.

### 8.1. Why Do OAuth2 Clients Easily Cause Token Storms?

A common mistake:

~~~text
Every WebClient request calls the manager.
Authorized-client store fails to persist the token.
Every request asks for a new token.
Token endpoint returns 429.
Client retries immediately.
More requests produce more 429s.
~~~

Possible causes:

- Not reusing unexpired `OAuth2AuthorizedClient` entries.
- Constantly changing `principalName` causing cache misses.
- Misconfigured token expiry/skew.
- Multiple pods refreshing concurrently.
- Success handler failing to persist the token.
- Polling jobs running too frequently or retrying without jitter.

### 8.2. 429 at AS Differs from 429 at API

| Source of 429 | Typical Quota Scope | Handling Direction |
|---|---|---|
| Authorization/token endpoint | OAuth client, IP, tenant, token grants | Reduce token issuance/refresh frequency; apply backoff |
| UserInfo endpoint | User/tenant/API quota | Reuse validated data when valid and per privacy policy |
| JWKS/discovery endpoint | Metadata fetch rate | Cache metadata/JWK and use exponential backoff |
| Orders API | Business API requests | Limit concurrency, cache responses, respect quota |

Never delete an authorized-client token just because the Orders API rate limited a request.

### 8.3. Retry-After Is a Server Hint, Not License for Infinite Retries

When parsing `Retry-After`:

- Parse seconds or HTTP-date per standard.
- Reject negative/invalid values.
- Cap maximum wait against the **overall request deadline** and SLA.
- Add jitter so all replicas do not wake up simultaneously.
- Verify the request is safe to retry.
- Avoid blocking request threads unnecessarily long.

If Retry-After is 1 hour while the UI request deadline is 5 seconds, return a "try again later" error instead of holding the request for an hour.

## 9. 5xx from Downstream or Provider: Availability, Not Credential Semantics

Some cases:

~~~text
500 Internal Server Error
502 Bad Gateway
503 Service Unavailable
504 Gateway Timeout
~~~

| Status | Usually Reflects | Initial Action |
|---|---|---|
| 500 | Server encountered a processing error | Monitor; bounded retry possible if request is safe |
| 502 | Gateway received bad upstream response | Check proxy/upstream; safe retry if appropriate |
| 503 | Overload/maintenance/unavailable | Respect Retry-After, backoff, circuit breaker |
| 504 | Gateway timeout | Determine whether request may already have been processed before retrying |

### 9.1. 5xx Does Not Prove Token Expiration

Wrong:

~~~text
Orders API returns 503
  -> remove authorized client
  -> force user login
~~~

Better:

~~~text
Orders API returns 503
  -> classify as downstream availability issue
  -> limited safe retry / circuit breaker
  -> show temporary unavailability if needed
  -> preserve browser login and valid token
~~~

### 9.2. 502/504 Can Originate at a Proxy

When the app calls:

~~~text
Portal -> API Gateway -> Orders Service
~~~

HTTP 504 can happen due to a gateway timeout even though Orders Service received the request and even committed to the database.

Therefore, **never auto-retry payment POSTs, order creation, or password changes** merely because a gateway returned 504.

### 9.3. Token Endpoint 503 During Login

When the browser callback brings an authorization code and the Portal sends it to the token endpoint:

~~~http
POST /oauth2/token
grant_type=authorization_code
code=<one-time-code>
~~~

If the token endpoint or connection fails/times out, you cannot be sure the code was not consumed. An authorization code is a **one-time credential**. Retrying the same code must follow contract/idempotency and policy; the safe approach is usually to fail the flow and start a new authorization request rather than replaying endlessly.

### 9.4. Refresh Token Rotation and Network Timeouts

Similarly:

~~~text
Client sends RT1
AS accepts and rotates RT1 -> RT2
Response lost due to network timeout
Client retries RT1
AS detects reuse/invalid_grant
~~~

You cannot assume RT1 is still valid merely because the client never received the response. Retry design must account for rotation and refresh-token family policies.

## 10. Request Idempotency Determines Retryability

HTTP method is a useful signal, though not sufficient on its own:

| Request Type | Auto-Retry | Notes |
|---|---|---|
| Read-only GET with no side effects | Usually yes | Still requires budget/rate limit |
| HEAD | Usually yes | Never retry indefinitely |
| Idempotent PUT per API contract | Possibly | Requires business confirmation |
| DELETE | May be state-idempotent | API contract/side effects must be checked |
| POST creating orders/charges | Usually **no** without idempotency key | Timeout may have already persisted data |
| Token endpoint `authorization_code` | Do not blindly retry | One-time code |
| Token endpoint `refresh_token` with rotation | Do not blindly retry | May trigger reuse detection |
| Client Credentials token request | Bounded retry when transient | Avoid token storms and rate limits |

### 10.1. Idempotency Key for Business Operations

A resource-creating API may support:

~~~http
POST /api/orders
Idempotency-Key: stable-operation-uuid
~~~

If the server implements proper idempotency semantics, the client can retry within budget while avoiding duplicate creation. **Adding the header on the client alone does not guarantee idempotency** if downstream does not implement it.

### 10.2. Authentication Retry Differs from Business Retry

A 401 invalid_token before request execution may allow retrying once a fresh token is obtained. Yet for non-idempotent requests, you must know whether the Resource Server actually rejected the request before any side effects; do not generalize blindly across custom middleware/proxies.

## 11. Decision Tree Before Handling Errors

~~~text
HTTP operation failed
    |
    v
Which endpoint returned error?
    |
    +-- Portal to browser
    |     401 -> browser authentication/session flow
    |     403 -> Portal authorization
    |
    +-- Authorization Server / token endpoint
    |     OAuth2 error -> classify invalid_grant/client/scope...
    |     429 -> rate limit, respect backoff
    |     5xx -> transient availability, grant-safe retry policy
    |
    +-- UserInfo / Discovery / JWK Set
    |     401 -> endpoint token/config
    |     429/5xx -> metadata/userinfo dependency handling
    |
    +-- Downstream Resource Server
          401 + Bearer invalid_token?
             -> narrowly invalidate/re-authorize correct client
          403 / insufficient_scope?
             -> permissions/consent/RBAC; do not refresh loop
          429?
             -> quota, throttle, Retry-After, no token deletion
          5xx?
             -> availability/retry if idempotent; no token deletion
~~~

**No single global exception handler can auto-heal all errors using HTTP status alone.** The handler needs endpoint type, request metadata, and potentially the OAuth2 error code.

## 12. OAuth2AuthorizedClient States to Understand

An `OAuth2AuthorizedClient` binds:

~~~text
ClientRegistration
principalName
accessToken
refreshToken (if present)
~~~

The authorized-client manager can:

1. Load an existing authorized client.
2. Check whether the access token is expired or near expiry.
3. Use the refresh token when policy/provider permits.
4. Save the new authorized client.
5. Return the authorized client or report an error.

**Expiration metadata does not guarantee the Resource Server still accepts the token.** The token may be revoked or have the wrong audience.

### 12.1. Token Still Valid by Expiry, Yet API Returns 401

May be caused by token revocation, Resource Server switching issuers, wrong audience, or the client sending the wrong token. Never "fix" this by bumping `expiresAt` in the store.

### 12.2. Token Expired, Yet Browser Is Still Logged In

The browser session/Authentication can remain valid even when the Orders API access token expired. The manager can refresh the token without forcing the user to log in again if the refresh grant is valid.

### 12.3. Invalid Refresh Token Does Not Always Log Out All Sessions

If one authorized client hits `invalid_grant`, handle it per registration/principal—possibly prompting reauthorization for that client. Never wipe all of the user's clients/tokens or all tenants unless policy requires it.

## 13. Authorized-Client Failure Handlers and Cleanup Scope

Spring Security provides extension points such as:

~~~java
org.springframework.security.oauth2.client
    .OAuth2AuthorizationFailureHandler
~~~

and integrations for OAuth2 Client HTTP requests capable of reacting to **OAuth2AuthorizationException** or 401/403 depending on configuration.

Goal:

~~~text
Failure of specific authorized client
  -> decide whether it is invalid
  -> remove/update that registration + principal entry
  -> do not delete unrelated authorized clients
~~~

### 13.1. A 401 from Resource Server Is Not Automatically OAuth2AuthorizationException

A WebClient HTTP call returning 401 usually raises:

~~~java
WebClientResponseException.Unauthorized
~~~

or the corresponding exception for the HTTP client stack. A token endpoint grant failure from the provider, on the other hand, can raise:

~~~java
OAuth2AuthorizationException
~~~

Do not assume a manager failure handler will automatically see all downstream 401s if the HTTP integration is not wired properly.

### 13.2. Watch Out for Success/Failure Persistence

If a custom manager replaces `setAuthorizationSuccessHandler(...)` without saving the new token, every request can ask for a token again → token endpoint 429.

If a custom failure handler deletes authorized clients by provider alias instead of registration/principal, it can wipe tokens across multiple OAuth clients/tenants.

### 13.3. Do Not Call Remove on a Mere 503

An availability error from the Orders API does not indicate a bad token. Deleting the authorized client on 503 usually just generates extra token endpoint traffic and login failures.

## 14. WWW-Authenticate: Read Carefully, Never Trust Blindly

Bearer authentication challenges commonly include parameters:

~~~http
WWW-Authenticate: Bearer realm="orders", error="invalid_token",
                  error_description="The access token expired"
~~~

or:

~~~http
WWW-Authenticate: Bearer realm="admin", error="insufficient_scope",
                  scope="admin.read"
~~~

Fields:

| Field | Meaning |
|---|---|
| Scheme `Bearer` | Authentication scheme associated with OAuth Bearer |
| `realm` | Resource protection realm (if present) |
| `error` | Bearer error code |
| `error_description` | Developer-oriented description; not trusted text for UI display |
| `scope` | Required/advised scope in insufficient_scope |

### 14.1. Multiple Challenges May Be Present

~~~http
WWW-Authenticate: Basic realm="legacy"
WWW-Authenticate: Bearer realm="orders", error="invalid_token"
~~~

HTTP header parsing follows quoting/escaping rules; a naive `split(",")` breaks if quoted text contains commas.

If making automated decisions from Bearer errors, use a parser aware of HTTP authentication grammar, cap header length, and pick the right challenge from a **trusted resource server**.

### 14.2. Never Let Untrusted Headers Drive Security Policy

An untrusted external API can return any `WWW-Authenticate` header it wants. Never let a user-supplied URL force your app to wipe tokens across all tenants or redirect logins to an unfamiliar issuer.

## 15. Retry-After: Parsing Delta-Seconds or HTTP-Date

Examples:

~~~http
Retry-After: 20
~~~

or:

~~~http
Retry-After: Wed, 18 Nov 2026 10:30:00 GMT
~~~

An illustrative helper:

~~~java
package com.example.oauth.errors;

import java.time.Clock;
import java.time.Duration;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Optional;

public final class RetryAfterParser {
    private RetryAfterParser() {}

    public static Optional<Duration> parse(
        String header,
        Clock clock
    ) {
        if (header == null || header.isBlank()) {
            return Optional.empty();
        }

        String raw = header.trim();
        try {
            long seconds = Long.parseLong(raw);
            if (seconds < 0) {
                return Optional.empty();
            }
            return Optional.of(Duration.ofSeconds(seconds));
        } catch (NumberFormatException ignored) {
            // Could be an HTTP-date.
        }

        try {
            ZonedDateTime date = ZonedDateTime.parse(
                raw, DateTimeFormatter.RFC_1123_DATE_TIME);
            Duration wait = Duration.between(
                clock.instant(), date.toInstant());
            return Optional.of(
                wait.isNegative() ? Duration.ZERO : wait);
        } catch (RuntimeException ignored) {
            return Optional.empty();
        }
    }
}
~~~

**This is a syntax helper**, not a policy enforcer. Callers must clamp an upper bound, apply an overall deadline, jitter, retry budget, and cancellation. If a server returns an excessively large Retry-After, return an error to the user/job scheduler rather than waiting forever.

### 15.1. Do Not Use Thread.sleep in HTTP Request Threads for Minute-Long Waits

If 429 forces a long wait, consider:

- Returning an appropriate HTTP 429/503 with a message to the caller.
- Scheduling a background retry via a queue/job scheduler.
- Client-side rate limiting.
- In-flight concurrency caps.

With Reactor, use non-blocking delay/backoff and avoid `Thread.sleep()` on the event loop.

## 16. Classify Errors by Endpoint to Preserve Context

A domain model helps avoid acting on status codes alone:

~~~java
package com.example.oauth.errors;

public enum DependencyKind {
    AUTHORIZATION_SERVER_TOKEN,
    OIDC_USERINFO,
    OIDC_DISCOVERY_OR_JWKS,
    DOWNSTREAM_RESOURCE_SERVER,
    PORTAL_SESSION_OR_AUTHENTICATION
}
~~~

~~~java
package com.example.oauth.errors;

public enum FailureCategory {
    TOKEN_REJECTED,
    INSUFFICIENT_PERMISSION,
    CLIENT_CONFIGURATION,
    GRANT_INVALID,
    RATE_LIMITED,
    TRANSIENT_DEPENDENCY,
    PERMANENT_REQUEST_ERROR,
    UNKNOWN
}
~~~

A result record for observability/policy:

~~~java
public record DependencyFailure(
    DependencyKind dependency,
    FailureCategory category,
    int httpStatus,
    String registrationId,
    String safeErrorCode,
    boolean retryable
) {}
~~~

This is an **application DTO**, not a built-in Spring type. For errors with no HTTP response (DNS failure, TLS failure, timeout), use a nullable status or an `OptionalInt` field rather than forcing `httpStatus=500`.

### 16.1. Why Is Dependency Kind Needed?

~~~text
401 + DOWNSTREAM_RESOURCE_SERVER
  => inspect Bearer token/Resource Server auth

401 + AUTHORIZATION_SERVER_TOKEN
  => inspect client authentication/invalid_client

401 + PORTAL_SESSION_OR_AUTHENTICATION
  => inspect browser session/login entry point
~~~

Same 401 status, completely independent handling paths.

## 17. RestClient on Servlet: Capturing HTTP Status from the Exact Source

Spring Framework 6.1+ provides `RestClient`. When `retrieve()` encounters 4xx/5xx statuses, it can throw `RestClientResponseException` or its subclasses depending on the case.

Orders API example with an idempotent **GET**:

~~~java
package com.example.portal.orders;

import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

@Service
public final class OrdersGateway {
    private final RestClient orders;

    public OrdersGateway(RestClient.Builder builder) {
        this.orders = builder
            .baseUrl("https://orders.example.test")
            .build();
    }

    public String getOrders(String accessToken) {
        try {
            return orders.get()
                .uri("/api/orders")
                .headers(h -> h.setBearerAuth(accessToken))
                .retrieve()
                .body(String.class);
        } catch (RestClientResponseException ex) {
            int status = ex.getStatusCode().value();

            if (status == 401) {
                // Signal only: token/authentication was rejected by the API.
                throw new OrdersApiUnauthorizedException(ex);
            }
            if (status == 403) {
                throw new OrdersApiForbiddenException(ex);
            }
            if (status == 429) {
                throw new OrdersApiRateLimitedException(ex);
            }
            if (status >= 500 && status <= 599) {
                throw new OrdersApiUnavailableException(ex);
            }
            throw ex;
        }
    }
}
~~~

`OrdersApiUnauthorizedException`, `OrdersApiForbiddenException`, `OrdersApiRateLimitedException`, and `OrdersApiUnavailableException` are **application exception types you define**. The example shows classification by the **Orders API** source, not OAuth2 token endpoint handling.

### 17.1. Do Not Return Raw Exceptions to the Frontend

`RestClientResponseException` can carry response bodies containing sensitive info or untrusted text. In logs/error responses, include only status, allowlisted host, safe error code, request ID, and category.

### 17.2. Extracting WWW-Authenticate and Retry-After

~~~java
var headers = ex.getResponseHeaders();
String challenge = headers != null
    ? headers.getFirst("WWW-Authenticate")
    : null;
String retryAfter = headers != null
    ? headers.getFirst("Retry-After")
    : null;
~~~

This is a fragment inside a catch block. **Never log raw challenge/response bodies verbatim** without redaction and length limits; do not use `split(",")` for complex Bearer challenges.

## 18. WebClient: Classifying WebClientResponseException

In Spring WebFlux or Servlet using WebClient:

~~~java
org.springframework.web.reactive.function.client.WebClientResponseException
~~~

Default `retrieve()` typically emits an exception for 4xx/5xx responses.

~~~java
return webClient.get()
    .uri("/api/orders")
    .retrieve()
    .bodyToMono(String.class)
    .onErrorMap(
        WebClientResponseException.Unauthorized.class,
        ex -> new OrdersApiUnauthorizedException(ex))
    .onErrorMap(
        WebClientResponseException.Forbidden.class,
        ex -> new OrdersApiForbiddenException(ex))
    .onErrorMap(
        WebClientResponseException.TooManyRequests.class,
        ex -> new OrdersApiRateLimitedException(ex));
~~~

The application must preserve HTTP source context and enforce token/authorization/retry policies at the right layer. Never do `onErrorResume(e -> Mono.empty())` for all errors, as that hides incidents and misleads callers into thinking "no data exists".

### 18.1. Non-Blocking Retry for GET on 503/429

Bounded example:

~~~java
import java.time.Duration;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

Mono<String> result = webClient.get()
    .uri("/api/orders")
    .retrieve()
    .bodyToMono(String.class)
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(250))
            .maxBackoff(Duration.ofSeconds(2))
            .jitter(0.5)
            .filter(ex ->
                ex instanceof WebClientResponseException
                    .TooManyRequests
                || ex instanceof WebClientResponseException
                    .ServiceUnavailable
                || ex instanceof WebClientResponseException
                    .BadGateway
                || ex instanceof WebClientResponseException
                    .GatewayTimeout)
    );
~~~

This only demonstrates retrying transient statuses for **GET**. Production needs:

- Overall deadline/timeout and cancellation.
- Priority for valid `Retry-After` headers.
- Rate limiter/circuit breaker and retry-storm prevention.
- Never retrying OAuth one-time grant requests under the same logic.
- Never retrying 401/403 without a clear authorization resolution mechanism.

### 18.2. Retry Filters Must Be Narrow

Never use:

~~~java
.retryWhen(Retry.max(100))
~~~

for all exceptions. 403, invalid_client, and invalid_scope will never turn into successes via retries; excessive retries cause load amplification.

### 18.3. Reactive Error Signals Without HTTP Status

Network errors such as DNS, connection reset, or TLS handshake failures may have no HTTP status. `WebClientRequestException` reflects request/transport failures, distinct from `WebClientResponseException` which carries an HTTP response.

Do not map all transport exceptions to `401` or `503` and lose the true error source.

## 19. OAuth2 WebClient/RestClient Integration and Automatic Token Handling

On Servlet, Spring Security provides:

~~~java
ServletOAuth2AuthorizedClientExchangeFilterFunction
~~~

for WebClient; on Spring Security 6.4+, there is:

~~~java
OAuth2ClientHttpRequestInterceptor
~~~

for RestClient.

An integration can attach the right Bearer token managed by `OAuth2AuthorizedClientManager` and plug into authorization failure handlers depending on version/configuration.

**Do not assume the framework automatically retries downstream 401s or deletes tokens in every setup.** Verify:

1. Is the filter/interceptor attached to the HTTP client actually being used?
2. Is the ClientRegistration ID accurate?
3. Do the Manager and AuthorizedClientRepository/Service share the same storage?
4. Are authorization success/failure handlers configured?
5. Are 401/403 responses from the Resource Server actually routed into the failure policy?

### 19.1. Explicit Registration Selection

~~~text
Orders API -> orders-client
Admin API  -> admin-client
~~~

Never use a default authorized client across all hosts. Sending a Bearer token meant for Orders to an attacker-controlled URL leaks credentials even when the HTTP request succeeds.

### 19.2. Login Authentication Differs from Downstream Tokens

`oauth2Login()` authenticates the browser/OIDC principal. `oauth2Client()` and the manager handle authorized clients. A downstream API 401 does not by default mean clearing the browser's `SecurityContext`.

## 20. Token Refresh Failure and Reauthorization

A sequence:

~~~mermaid
sequenceDiagram
    actor Browser as Browser
    participant Portal as Portal/OAuth2 Client
    participant Store as Authorized Client Store
    participant AS as Authorization Server
    participant API as Orders API

    Browser->>Portal: GET /orders
    Portal->>Store: Load existing authorized client
    Store-->>Portal: AT1, RT1
    Portal->>API: GET /orders Bearer AT1
    API-->>Portal: 401 Bearer invalid_token
    Portal->>Store: Mark/remove specific invalid authorized client by policy
    Portal->>AS: Refresh/reauthorize if supported
    AS-->>Portal: AT2, RT2 or OAuth error
    Portal->>Store: Persist AT2/RT2 if successful
    Portal->>API: Optional one bounded retry with AT2
    API-->>Portal: 200 OK or error
    Portal-->>Browser: Response
~~~

In practice the manager/provider chain normally checks expiry before calling the API; the diagram illustrates **when a token is unexpectedly rejected by the API**.

### 20.1. If Refresh Fails with invalid_grant

A revoked/expired/rotated refresh token cannot be reused. Typically you need to:

- Clean up the exact authorized-client entry.
- Notify the user to reauthorize the client or sign in per UX policy.
- Preserve other unrelated sessions/clients if permitted.
- Never retry the same refresh token indefinitely.

### 20.2. If Refresh Fails with HTTP 503

This is an Authorization Server outage and does not prove the refresh token is invalid. You can keep the record per policy and ask to try again later rather than deleting credentials immediately.

### 20.3. Token Invalid Due to Wrong Audience

If refreshing issues a new AT with the same wrong audience, retrying still returns 401. Fix client/AS/resource indicator configuration or use the right registration. **Never force users to log out to mask configuration bugs.**

## 21. 429 and 5xx: Resilience Patterns

Appropriate measures:

| Pattern | Purpose | Notes |
|---|---|---|
| **Timeout/deadline** | Never wait on a dependency forever | Include both per-call and end-to-end deadlines |
| **Exponential backoff** | Reduce pressure during transient failures | Cap retry count |
| **Jitter** | Prevent all pods from retrying simultaneously | Especially critical for 429/503 |
| **Rate limiter** | Proactively stay within quota | Per client/tenant/API |
| **Bulkhead/concurrency limit** | Keep one slow dependency from exhausting all threads | Configure per dependency |
| **Circuit breaker** | Temporarily stop calling a down dependency | Never use to bypass auth |
| **Caching** | Reduce requests | Cache only permitted data with right TTL |
| **Queue/deferred retry** | Avoid holding HTTP requests open long | Requires idempotency and deduplication |
| **Single-flight token refresh** | Reduce refresh concurrency | Key by registration/principal/tenant |

### 21.1. Never Configure a "Fail-Open" Circuit Breaker for Authorization

When the Authorization Server/Resource Server stops responding, never allow sensitive APIs just because the breaker is open.

~~~text
Dependency unavailable != permission granted
~~~

### 21.2. One Shared Breaker Across All IdPs Can Cause Cross-Outages

In multi-provider/multi-tenant apps, scope breakers/rate limiters to the right **dependency identity** instead of one global breaker. An outage on IdP A should not block IdP B if they are independent.

### 21.3. Caching Is Not a Cure-All for Errors

Orders API 503 can be served via stale cached reads **only when** data contracts, consistency, authorization, and privacy policies allow it. Never return cached data belonging to another user/tenant or sensitive data whose access was revoked.

## 22. Rate-Limiting the Token Endpoint: Avoiding Thundering Herds

Suppose 100 pods simultaneously see an AT expire at `12:00:00`:

~~~text
12:00:00 -> 100 pods refresh at once
12:00:01 -> AS returns 429 to several pods
12:00:01 -> all retry immediately
12:00:02 -> AS remains overloaded
~~~

Mitigations:

1. Reasonable clock skew, not overly large.
2. Persist authorized clients in a shared store per architecture.
3. Avoid generating random principalNames that cause cache misses.
4. Lock/single-flight per authorized-client key when needed.
5. Retry with exponential backoff and jitter.
6. Respect Retry-After and client quotas.
7. Set concurrency budgets/overall deadlines.
8. Follow token reuse policies securely.

### 22.1. Never Overwrite with an Old Refresh Token After Rotation

If Pod A receives RT2 while Pod B holds stale RT1, Pod B must not overwrite the store with RT1 just because it finished later. Use appropriate optimistic concurrency/version guards.

## 23. Browser UX and API Errors: Avoid Login Redirect Loops

A BFF might see:

~~~text
Browser GET /orders
Portal calls Orders API
Orders API returns 401
~~~

You do not necessarily redirect the browser to the IdP immediately. You can:

- Try obtaining a new authorized client if policy permits.
- If the refresh token is invalid, notify that re-login/reauthorization is required.
- If Orders API is misconfigured, return a service-unavailable error and alert ops.

### 23.1. API Clients and Browser Clients Have Different Entry Points

A JSON API route should normally return machine-readable 401/403 per contract, not an unexpected HTML login page/302 to fetch calls if the frontend does not handle redirects.

A browser page can redirect to login. Choose `AuthenticationEntryPoint` and access-denied handling per security chain/route.

### 23.2. Messages by Source

| Scenario | Friendly Message |
|---|---|
| Invalid browser session | "Your session has expired. Please sign in again." |
| User lacks permission | "You do not have permission to perform this action." |
| Token needs reauthorization | "Service access needs to be reauthorized." |
| API rate limited | "The system is handling high request volume. Please try again shortly." |
| Dependency unavailable | "The service is temporarily unavailable. Please try again later." |

Never display raw access tokens, client IDs/secrets, stack traces, or `error_description` containing internal details.

## 24. Deliberately Choosing the HTTP Status Returned to the Browser

The Portal is an independent HTTP server. A downstream 401 **does not force** the Portal to return 401 to the browser:

~~~text
Browser is authenticated to Portal.
Orders API rejects server-managed token.
Portal's browser authentication may still be valid.
~~~

Per the API contract, the Portal can return 502/503 or an application error code after exhausting its reauthorization policy, expressing a **downstream dependency failure** rather than "browser not logged in".

Conversely, if the browser session expired, returning 401/login redirect is appropriate. If the user is authenticated yet forbidden from calling the resource, 403 makes sense.

**Do not map every downstream 401 to a browser 401**, because the frontend may clear the session or enter a login loop that cannot solve the underlying error.

## 25. Observability: What to Record for Diagnosis

A safe log event:

~~~json
{
  "timestamp": "2026-11-16T04:30:00Z",
  "service": "employee-portal",
  "operation": "orders.read",
  "dependency": "orders-api",
  "dependencyKind": "DOWNSTREAM_RESOURCE_SERVER",
  "registrationId": "orders-client",
  "httpStatus": 401,
  "oauthErrorCode": "invalid_token",
  "attempt": 1,
  "retryScheduled": false,
  "correlationId": "req-a17"
}
~~~

This is an **illustrative instrumentation schema**, not fields Spring Boot logs automatically.

### 25.1. Do Not Log Credentials

Never write:

~~~text
Authorization: Bearer <real-access-token>
Authorization: Basic <client-secret>
Cookie: JSESSIONID=<real-session>
refresh_token=<real-refresh-token>
authorization_code=<real-code>
id_token=<real-id-token>
client_secret=<real-client-secret>
~~~

Be especially careful with HTTP wire logging, proxy logs, full request/response dumps, and exception messages. Token endpoint bodies routinely contain secrets and one-time credentials.

### 25.2. PII and High-Cardinality Labels

Metric labels such as full email, subject, raw user ID, URLs with query params, access tokens, or correlation IDs pose security risks and high cardinality costs. Prefer:

~~~text
dependencyKind
registrationId (allowlisted)
safe error code
httpStatus
tenant tier / low-cardinality tenant group when appropriate
~~~

Correlation ID belongs in controlled log/tracing attributes, not as a high-cardinality metric label.

## 26. Metrics to Track

| Metric (example names) | Interpretation |
|---|---|
| `oauth.token.request.count` | Token requests by grant/registration |
| `oauth.token.request.error` | Token endpoint errors by OAuth code |
| `oauth.token.refresh.count` | Refresh frequency |
| `oauth.authorized_client.cache_hit` | Whether tokens are being reused |
| `http.client.response.status` | 401/403/429/5xx per dependency |
| `http.client.retry.count` | Retry attempts and outcomes |
| `http.client.retry_exhausted` | Retry budget exhausted |
| `rate_limit.observed` | Quota hits |
| `circuit_breaker.state` | CLOSED/OPEN/HALF_OPEN per dependency |
| `oauth.resource.invalid_token` | Resource Server Bearer rejections |
| `oauth.resource.insufficient_scope` | Resource Server permission rejections |
| `idp.discovery.failure` | Metadata/JWK dependency issues |

These are **suggested metrics**, not guaranteed default names in Micrometer/Spring Boot. Instrument using your observability tooling while avoiding unbounded cardinality.

### 26.1. Distinguish Error Rate from Retry Rate

A request may retry 3 times and then succeed. Measuring only **final failures** hides pressure placed on the IdP. Track metrics for:

- Attempts.
- Retries.
- Success after retry.
- Retry exhaustion.
- Per-dependency latency.
- Queue depth/rate-limit delay.

### 26.2. Correlate Login and Downstream

A browser flow spans multiple request IDs:

~~~text
browser request ID
oauth state correlation (do not log raw unless needed)
token endpoint attempt ID
downstream request ID
distributed trace ID
~~~

Never put raw `state`/nonce/tokens into tracing. Use separately generated correlation IDs and safe mappings.

## 27. Tracing Across IdP and Downstream Boundaries

An illustrative trace:

~~~text
HTTP GET /orders                          420 ms
  OAuth2AuthorizedClientManager            35 ms
    AuthorizedClientStore load             10 ms
    Token endpoint refresh                 22 ms
  Orders API GET /api/orders              350 ms
    HTTP 503
  Retry decision                           1 ms
  Response to browser                      ...
~~~

When multiple external dependencies exist, instrumentation should reveal:

- Slow authorized-client storage?
- Slow token refreshes?
- IdP discovery/JWK fetch timeouts?
- Downstream API 5xx or timeouts?
- App-induced retry storms?

Never put access tokens, refresh tokens, or client secrets into span attributes. When recording URLs, use route templates or URLs stripped of query params/secrets.

### 27.1. Do Not Log Raw OAuth Response Bodies

AS `error_description` can inadvertently contain user details/client internals. Log only sanitized OAuth error codes and controlled internal messages.

## 28. Distinguish Infrastructure Errors Without an HTTP Response

Not every failure has a status code:

~~~text
DNS resolution failure
TLS handshake/certificate failure
Connection refused/reset
Connect timeout
Read timeout
Proxy authentication failure
Connection pool exhaustion
~~~

Never map these to `401` or `invalid_grant`. With timeouts, the request may have reached the server and been processed—especially dangerous for POSTs/token rotation.

### 28.1. TLS Errors Require Fixing Trust/Config

Never use `trustAllCertificates` or disable hostname verification to "fix" token endpoint 5xx/timeouts. Broken TLS trust is a security/configuration issue; retries will not heal it.

### 28.2. Proxy 407

`407 Proxy Authentication Required` is proxy authentication, not a resource server Bearer 401. Investigate proxy credentials/network routing.

## 29. OIDC Discovery/JWKS Failures and Proper Classification

An OIDC Provider publishes metadata such as:

~~~text
issuer
authorization_endpoint
token_endpoint
jwks_uri
userinfo_endpoint
~~~

If the discovery/JWKS endpoint returns 429/5xx:

- New logins may fail ID Token verification.
- Check metadata/JWK caches and key rotation policies.
- Bounded retries/backoff may be used for metadata fetches.
- Never drop signature/issuer/audience validation because keys could not be fetched.

### 29.1. Key Rotation and Unseen kid

If an ID Token is signed with a `kid` not yet seen in the JWKS cache, the client may need to refresh JWKS per library mechanics. However, if the JWKS endpoint is returning 503, **never accept an unverified ID Token**. Fail closed and ask users to retry login once the dependency recovers.

### 29.2. UserInfo 401

UserInfo typically accepts an access token:

~~~http
GET /userinfo
Authorization: Bearer <access-token>
~~~

If UserInfo returns 401, inspect token validity/audience/scope/userinfo policy and the OIDC flow. Never fall back to trusting unauthenticated UserInfo JSON or building a principal from unverified claims.

### 29.3. Authorization Endpoint Errors Arrive via Browser

The Authorization Server may redirect back to the callback with:

~~~text
?error=access_denied&state=...
~~~

This is an **OAuth authorization response error** returned by the OP via the browser, not an HTTP 403 from the Orders API. The callback still requires state/issuer/correlation validation. UX can explain that the user declined consent or provider policy disallowed access.

## 30. Incident Runbook: Sudden Spike in Downstream 401s

When dashboards show Orders API 401s spiking:

1. Confirm the **source**: Orders API or Portal route?
2. Inspect `WWW-Authenticate` scheme and Bearer error code.
3. Compare by registration ID/client ID (without logging secrets).
4. Check access token audience/issuer/scope/expiry and clock skew.
5. Check recent config changes at Orders API or IdP.
6. Check whether the manager loads the right authorized client and refreshes properly.
7. Check whether newly issued tokens continue returning 401.
8. With multiple tenants, confirm tokens are not being crossed.
9. Consider rolling back config rather than forcing a mass logout of all users.
10. Monitor retry counts and token endpoint load.

**If fresh tokens keep returning 401, stop the refresh loop.** Fix trust/audience/configuration first.

## 31. Incident Runbook: Sudden Spike in 403s

1. Confirm whether the user is already authenticated.
2. Check Resource Server `insufficient_scope` vs. app-specific policy.
3. Check requested/granted scopes and resource audience.
4. Compare role/tenant membership, ownership, and feature flags.
5. Check recent deploys/policy changes at the API.
6. Never self-escalate scopes or switch to a privileged client.
7. If new consent is needed, send the user through the proper authorization flow.
8. Return meaningful 403s without causing login loops.

A sudden wave of 403s right after a deploy is usually an **authorization policy regression**, not necessarily a token issue.

## 32. Incident Runbook: Token Endpoint 429

1. Identify which token endpoint/registration is being rate limited.
2. Check whether token issuance/refresh rates spiked abnormally.
3. Check authorized-client store hit rates and persistence.
4. Check whether principalName/registration keys are unstable.
5. Check clock skew and token lifetimes.
6. Check whether multiple pods are refreshing the same token concurrently.
7. Reduce concurrency and retries; respect Retry-After.
8. Check whether a recent deploy accidentally dropped caching/repository persistence.
9. If higher quota is needed, work with the IdP after fixing client behavior.
10. Never wipe all tokens to "reset" rate limits.

### 32.1. Token Refresh on Every Request

A telling symptom:

~~~text
Portal RPS = 100
Token endpoint RPS = 100
~~~

Unless a special grant requires it, this signals token reuse issues, expired metadata, broken storage/success handlers, or wrong client registration selection.

## 33. Incident Runbook: 5xx/Timeout

1. Identify upstream: AS, UserInfo, JWKS, Orders API, proxy, or internal DB.
2. Inspect error/latency/concurrency per dependency.
3. Confirm request method and idempotency.
4. Check `Retry-After` or maintenance notices if present.
5. Enable bounded retries/backoff for safe operations.
6. Use circuit breakers/bulkheads if the dependency is overloaded.
7. Never wipe tokens/sessions because of 5xx responses.
8. Protect thread pools, event loops, and connection pools.
9. Return UI/API errors per contract; never mask errors as empty data.
10. Audit retries if a POST may already have created side effects.

If a POST timed out after reaching the server, verify operation status or use an idempotency key rather than replaying arbitrarily.

## 34. Testing with a Mock Downstream HTTP Server

An integration test should simulate responses:

~~~text
Case A:
  GET /orders -> 401 Bearer invalid_token
  Expected: reauthorization policy scoped to current authorized client

Case B:
  GET /admin -> 403 Bearer insufficient_scope
  Expected: no refresh storm; permission error

Case C:
  GET /orders -> 429 Retry-After: 2
  Expected: rate-limit policy/backoff, no token deletion

Case D:
  GET /orders -> 503
  Expected: bounded safe retry, final unavailable if exhausted

Case E:
  POST /orders -> 504
  Expected: no blind replay without idempotency contract
~~~

Test with MockWebServer/WireMock or a suitable fake HTTP server. Never call a production IdP in unit tests.

### 34.1. Token Endpoint Test Must Mock OAuth Errors

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{"error":"invalid_grant"}
~~~

Test expectations:

- Token-response client maps the OAuth error code properly.
- Failure handler affects only the exact registration/principal.
- Same refresh token is not retried blindly.
- Request body containing the refresh token is never logged.

### 34.2. 429 Retry-After Tests

Values:

~~~text
Retry-After: 0
Retry-After: 30
Retry-After: Wed, 18 Nov 2026 10:30:00 GMT
Retry-After: not-a-date
Retry-After: -12
~~~

Test the parser and **policy clamp** separately: no negative/infinite delays, and overall deadlines remain respected.

### 34.3. Testing 5xx with POST

Mock server receives an order-creation POST and returns 504. The test verifies the client **does not resend the request** without an idempotency key/contract.

## 35. Unit Testing Classifier and Retry Policy

A classifier should produce:

| Input | Category | Retry |
|---|---|---|
| Downstream 401 Bearer invalid_token | TOKEN_REJECTED | Retry only after valid token handling, bounded |
| Downstream 403 insufficient_scope | INSUFFICIENT_PERMISSION | No |
| Downstream 429 | RATE_LIMITED | Possibly, respecting Retry-After/budget |
| Downstream 503 GET | TRANSIENT_DEPENDENCY | Possibly |
| Downstream 504 POST without idempotency | TRANSIENT_DEPENDENCY | No auto-replay |
| Token endpoint 400 invalid_grant | GRANT_INVALID | Do not retry same credential |
| Token endpoint 401 invalid_client | CLIENT_CONFIGURATION | No |
| JWKS 503 | TRANSIENT_DEPENDENCY | May retry metadata fetch; fail-closed validation |

### 35.1. Multi-Registration Test

~~~text
Orders authorized client = (orders-client, alice)
Admin authorized client  = (admin-client, alice)

Orders returns 401 invalid_token.

Expect:
  Only orders-client/alice entry may be invalidated.
  admin-client/alice entry remains unchanged.
~~~

### 35.2. Multi-Tenant Test

~~~text
ACME Orders API -> 401 invalid_token
GLOBEX Orders API -> 200 OK

Expect:
  No GLOBEX authorized-client cleanup.
  No GLOBEX secret rotation.
  No cross-tenant Bearer token reuse.
~~~

### 35.3. Backpressure/Thundering Herd Test

Simulate multiple concurrent requests seeing a near-expiry token. Confirm caching/single-flight or refresh strategy does not trigger token endpoint calls scaling unboundedly with concurrency.

## 36. Security Pitfalls in Error Handling

**1. Logging raw Authorization headers to debug 401s.** Tokens can be stolen.

**2. Rendering OAuth error_description directly into HTML.** Can leak internals or cause injection when rendered unsafely.

**3. Refreshing tokens on every 403.** Grants no permissions; causes rate limiting.

**4. Retrying 429s with zero delay.** Causes cascading failures.

**5. Retrying every POST after 504.** Duplicates business actions or replays one-time grants.

**6. Deleting all authorized clients on a single invalid_grant.** Breaks unrelated sessions/tenants.

**7. Using a privileged service token to bypass a user 403.** Violates authorization policy.

**8. Accepting unverified ID Tokens during JWKS 503.** Violates the OIDC security boundary.

**9. Confusing Portal 401 with Resource Server 401.** Causes logouts and login loops.

**10. Enabling HTTP wire logging on the token endpoint.** Leaks client secrets, codes, and refresh tokens.

**11. Trusting Retry-After blindly without deadline caps.** Exhausts threads/resources.

**12. Attaching Bearer tokens to untrusted URLs and following redirects.** Enables SSRF/token exfiltration.

**13. Mapping all network failures to invalid_token.** Deletes valid credentials.

**14. Lacking per-dependency metrics.** Makes it hard to tell whether the IdP or Orders API is failing.

## 37. Practice Exercises

### Exercise 1 — Orders API 401 invalid_token

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

**Question:** Should you log out the browser immediately?

**Solution:** Not by default. Identify the authorized client and token rejected by the API; perform bounded cleanup/reauthorization, and inspect issuer/audience if a fresh token still gets 401.

### Exercise 2 — Admin API 403 insufficient_scope

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope",
                  scope="admin.read"
~~~

**Question:** Will continuous refreshes elevate permissions?

**Solution:** No. Check scope/grant/consent and RBAC/resource authorization. Never use a privileged service token to bypass it.

### Exercise 3 — Token Endpoint 401 invalid_client

~~~json
{"error":"invalid_client"}
~~~

**Question:** Should you refresh the access token or fix configuration?

**Solution:** Verify client ID/secret/mTLS/private_key_jwt/rotation and Authorization Server client policy. Retrying with bad credentials will not solve it.

### Exercise 4 — Orders API 429

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 20
~~~

**Question:** Should you delete the access token?

**Solution:** No. Rate limiting comes from the downstream API; apply throttling/backoff, budgets, and appropriate UI.

### Exercise 5 — AS 503 During Refresh

**Question:** Does this prove the refresh token was revoked?

**Solution:** No. This is an availability failure. Retain/clean up only per grounded policy; never delete tokens solely because of 503.

### Exercise 6 — Token Endpoint 400 invalid_grant

Refresh token RT1 was already rotated to RT2 on another node.

**Question:** Retry RT1 again?

**Solution:** Do not blindly retry. Check races, authorized-client versions, token generation storage, and refresh rotation policy.

### Exercise 7 — Order-Creation POST Gets 504

**Question:** Is immediate retry safe?

**Solution:** Do not assume it is safe; the request may already have been processed. Use operation status checks or an idempotency contract.

### Exercise 8 — Portal Returns 401 While Orders API Still Works

**Question:** Is the token necessarily bad?

**Solution:** No. The browser session/authentication may have expired, separate from the downstream OAuth authorized client.

### Exercise 9 — JWKS Endpoint 503

**Question:** Can we temporarily skip ID Token signatures so users can log in?

**Solution:** No. Token verification must fail closed; use proper metadata caching/retries and alert on the IdP outage.

### Exercise 10 — Multi-Tenant Cleanup

ACME Orders API 401; GLOBEX Orders API 200.

**Question:** Wipe all tokens under the same issuer?

**Solution:** No. Clean up only the exact tenant, registration, principal, and token generation if needed.

## 38. Operational Checklist for 401/403/429/5xx

| Question | What to Confirm |
|---|---|
| Which party sent the HTTP response? | Browser-facing Portal / AS / UserInfo / JWKS / Resource Server |
| What is the request method and endpoint? | GET/POST, token endpoint, or business API |
| Is there an OAuth2 error code? | invalid_grant/invalid_client/invalid_scope/... |
| Is WWW-Authenticate present? | Bearer challenge, invalid_token/insufficient_scope |
| Is Retry-After present? | Parse, clamp, enforce deadline |
| Which registration owns the token? | Exact registration+principal+tenant |
| Is the browser session still valid? | Separate from downstream token |
| Is the access token expired? | expiresAt, skew, actual API rejection |
| Is the refresh token still valid? | Rotation/revocation/AS response |
| Are issuer/audience/scopes right? | Resource Server validation |
| Does the user have business permission? | RBAC/tenant/resource ownership |
| Which quota triggered 429? | AS, UserInfo, API, tenant/client/IP |
| Did 5xx come from proxy or service? | Dependency traces/metrics |
| Is the request idempotent? | Never blindly replay POSTs |
| Is retry policy bounded? | Attempts, deadline, jitter/backoff |
| Are circuit breakers/bulkheads in place? | Never fail open authorization |
| Is authorized-client cleanup scoped? | Never wipe an entire provider/tenant |
| Are token endpoint calls spiking abnormally? | Cache/expiry/refresh storm |
| Do logs leak credentials? | Redact headers/bodies/query params |
| Do metrics distinguish dependencies? | Yes |
| Are 401/403/429/5xx tested? | Yes, including negative cases |
| Are incident runbooks and rollbacks ready? | Yes |

## 39. Summary

In **Spring Security OAuth 2.0/OIDC Client**, you must understand both the **HTTP status code** and the **origin of the error**. A **401** from a Resource Server usually involves a Bearer token or API authentication; a **401** at the token endpoint can involve OAuth client authentication; a **401** from the Portal may just be the browser session. A **403** is usually authorization/scope/resource policy—refreshing tokens does not grant permissions. A **429** is quota/rate limiting—requiring `Retry-After`, throttling, and bounded backoff. A **5xx** usually reflects dependency availability—never automatically delete tokens or log users out.

Retry decisions must rest on **idempotency, grant semantics, deadlines, and dependency identity**. Authorization codes and rotating refresh tokens are credentials with single-use/rotation constraints and must never be blindly replayed. Authorized-client cleanup must target the exact **registration/principal/tenant**, avoiding races with newer refresh tokens. Resource Servers also check issuer/audience/scopes; an unexpired token does not guarantee the API accepts it.

Finally, good observability requires **per-dependency metrics, safe OAuth error codes, request correlation, retry/failure rates, and tracing**—without ever logging access tokens, refresh tokens, client secrets, codes, or session cookies. With proper error classification, applications keep user sessions stable during downstream outages, prevent token storms, and preserve the boundaries of **authentication, authorization, token lifecycle, and availability**.
