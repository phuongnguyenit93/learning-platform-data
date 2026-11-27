# Resource Server Returns Errors So Clients Handle Renewal per the Appropriate Protocol

## 1. Goal: Return the Right Error So the OAuth Client Knows the Next Step

In a **Spring Security OAuth 2.0/OIDC Resource Server** system, access tokens have finite lifetimes and can be revoked early. When a client calls an API with a Bearer token that is no longer accepted, the Resource Server must return the **protocol-correct HTTP status and Bearer challenge** so the client can decide whether to obtain a new token, prompt the user to log in again, or stop.

Example request:

```http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6...
```

If the access token has expired or been revoked, a typical response is:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
Cache-Control: no-store
```

The OAuth client can use the `invalid_token` signal to consider acquiring a new access token via the **OAuth 2.0 Token Endpoint**. If it holds a valid refresh token, it can use the **Refresh Token Grant**. If it has no refresh token, it can request a new access token with an appropriate grant or ask the user to log in.

Crucially, **the Resource Server does not renew access tokens itself**. It only verifies credentials and responds per the protocol. Refresh tokens belong to credential management between the **OAuth client and Authorization Server**; clients never send refresh tokens to APIs.

This lesson explains:

- Distinguishing **401 invalid_token**, **403 insufficient_scope**, **400 invalid_request**, and dependency failures.
- The meaning of `WWW-Authenticate` under RFC 6750.
- When clients should refresh tokens, acquire new tokens, re-authenticate, or avoid retrying.
- Using refresh token rotation, handling `invalid_grant`, and synchronizing concurrent requests.
- Configuring Spring Security Resource Server and OAuth2 Client.
- Safe retries, idempotency, avoiding 401 loops, and avoiding credential leaks.

> **Foundational rule:** The Resource Server must communicate the exact protocol-level reason; the OAuth client is responsible for using the appropriate grant to get a new access token. A 401 does not mean every case can be refreshed, and a 403 is not a default signal to refresh.

## 2. Separation of Responsibilities: Resource Server, Client, and Authorization Server

Three components have distinct roles:

| Component | Responsibility | Must not do |
| --- | --- | --- |
| **OAuth 2.0 Resource Server** | Accept access tokens, verify tokens, check audience/scope, and return 401/403 or valid results. | Accept refresh tokens from callers to exchange for access tokens; mint new tokens itself; leak raw tokens or secrets in errors. |
| **OAuth 2.0 Client** | Store access/refresh tokens per policy, call APIs, handle Bearer challenges, refresh or acquire new tokens, retry requests when safe. | Send refresh tokens to Resource Servers; retry infinitely; put tokens in URLs or logs. |
| **Authorization Server (AS)** | Issue access and refresh tokens per grant/consent/client policy; verify refresh tokens; rotate/revoke; return new tokens or OAuth errors. | Trust a refresh token merely because a client sent it; skip client authentication or required bindings. |

Standard flow when an access token expires:

```mermaid
sequenceDiagram
    participant C as OAuth Client
    participant RS as Resource Server
    participant AS as Authorization Server
    C->>RS: API request + Bearer access token
    RS->>RS: Validate token
    RS-->>C: 401 + WWW-Authenticate: Bearer error="invalid_token"
    Note over C: Client determines token may need renewal
    C->>AS: POST /token, grant_type=refresh_token
    AS->>AS: Validate refresh token + client + policy
    alt Refresh token still valid
        AS-->>C: 200 + new access token (optionally with new refresh token)
        Note over C: Store new tokens securely; replace old refresh token on rotation
        C->>RS: Retry API request with new access token
        RS->>RS: Validate new token
        RS-->>C: 2xx if scope/resource/policy allow
    else Refresh token no longer valid
        AS-->>C: OAuth error, usually invalid_grant
        Note over C: Clear old credentials and require re-authorization
    end
```

The Resource Server **does not need to know where the refresh token lives**. It only receives the access token and decides whether to accept it.

## 3. Bearer Challenges Under RFC 6750

**RFC 6750 — OAuth 2.0 Bearer Token Usage** defines how to transmit Bearer tokens and how Resource Servers signal errors using `WWW-Authenticate`. Common error codes:

| Bearer error | Typical HTTP status | Meaning |
| --- | --- | --- |
| `invalid_request` | **400 Bad Request** | Request uses malformed token syntax or transmits credentials in an invalid/inconsistent way. |
| `invalid_token` | **401 Unauthorized** | Access token rejected: may be expired, revoked, malformed, or invalid per the resource contract. |
| `insufficient_scope` | **403 Forbidden** | Token was accepted, yet lacks the required scope for the resource/action. |

### 3.1. Missing Access Token

Example where the client sent no credential:

```http
GET /api/orders HTTP/1.1
Host: api.example.test
```

Response:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
```

Per RFC 6750, when a request **contains no authentication credentials**, the Resource Server typically returns a Bearer challenge **without** `error="invalid_token"`. The client learns the endpoint requires Bearer credentials and must run the appropriate flow to obtain an access token.

### 3.2. Token Present but Invalid

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
```

`invalid_token` covers multiple cases:

- Token expired (`exp`).
- Token revoked or no longer active.
- JWT signature invalid, wrong issuer/audience, or claim validation failed.
- Opaque token introspection returned `active=false`.
- Token rejected under the token profile/resource contract.

The client does not necessarily know the specific cause. It can attempt to acquire a new token if its grant permits, yet must stop if the error repeats or points to misconfiguration.

### 3.3. Valid Token but Missing Permissions

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope"
```

For instance, a token has `SCOPE_orders:read` yet calls:

```http
POST /api/orders
```

while the endpoint requires `SCOPE_orders:write`.

The client must not automatically refresh **the same authorization grant** hoping the new token will gain extra scopes. To gain new scopes, the client needs an appropriate permission request mechanism, which may require user consent or a new authorization request per AS policy. Refresh token grants are typically capped at the originally granted scopes; they are not an arbitrary privilege-escalation path.

### 3.4. Malformed Bearer Request

Example:

```http
Authorization: Bearer
```

or a request sending multiple conflicting token transport methods. The Resource Server may respond:

```http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer realm="orders-api", error="invalid_request"
```

The client must fix how it transmits credentials. Refreshing tokens will not fix malformed headers.

### 3.5. Quick Decision Table

| Response | Appropriate client action |
| --- | --- |
| 401, no `error`, and request sent no token | Acquire an access token via the configured login/client flow, then send the request. |
| 401, `invalid_token` | May try refreshing/reacquiring **once** if the grant allows; otherwise re-authorize or surface the error. |
| 403, `insufficient_scope` | Check permissions/scopes and policy; do not loop refreshes. |
| 400, `invalid_request` | Fix headers/body/transport per protocol; never refresh just for this error. |
| 429 | Honor `Retry-After` if present and back off; do not refresh tokens automatically. |
| 5xx/503 | Handle service/dependency outage per retry policy; do not assume the access token is invalid. |
| 404 | Check endpoint/resource and resource concealment rules; do not refresh on this status. |

## 4. WWW-Authenticate Is a Protocol Signal, Not a Debug Log

Clients should inspect **HTTP status and Bearer challenge**. `error_description` is optional; clients must not rely on specific English wording to drive logic.

Example:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token", error_description="The access token is invalid"
```

Error descriptions should be safe, stable strings. Never return:

```http
WWW-Authenticate: Bearer error="invalid_token", error_description="JWT kid=prod-key-7 not found at https://internal-idp.svc/keys; token=eyJ..."
```

Never let `error_description` contain:

- Raw access tokens or refresh tokens.
- Client secrets, Basic headers, private keys, or private certificate material.
- Internal JWKS/introspection URIs, hostnames, pods, or namespaces.
- Stack traces or unsanitized exception messages.
- Payload claims containing PII or unnecessary tenant metadata.

Clients should branch on `error="invalid_token"` rather than parsing description strings for words like "expired," "revoked," or "signature."

### 4.1. Realm and error_uri

`realm` can be a stable resource name like `orders-api`. It does not have to be the issuer URL or introspection endpoint. If using `error_uri`, point only to public API documentation:

```http
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token", error_uri="https://docs.example.test/auth-errors"
```

Never put access tokens or refresh tokens in URLs; query strings get logged in proxy logs, browser history, referrers, and analytics.

### 4.2. Missing Token and Invalid Token Differ

Clients must distinguish:

```text
No Authorization header sent
  → Resource Server requires Bearer authentication
  → Client obtains access token per configured grant.

Bearer token sent but rejected
  → Resource Server returns invalid_token
  → Client attempts replacement; if impossible, re-authorize or report error.
```

Never turn every 401 into "refresh immediately." A request without a token may simply be a client configuration bug or a misrouted public/private endpoint call.

## 5. The Refresh Token Grant Lives at the Token Endpoint

A **refresh token** is a credential used with the Authorization Server to get new access tokens. Under OAuth 2.0, clients send token requests to the **Token Endpoint**, never sending refresh tokens to Resource Servers.

Example form request:

```http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-authentication-if-required>

grant_type=refresh_token&refresh_token=<refresh-token-value>
```

For public clients, client identification may use `client_id` per AS requirements paired with appropriate refresh token protections. For confidential clients, client authentication follows registration (e.g., client secret, mTLS, or `private_key_jwt`). Never hardcode secrets in mobile apps or SPAs.

Example successful response:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<new-access-token>",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "<new-refresh-token>",
  "scope": "orders:read"
}
```

The AS may **omit a new `refresh_token`** in some configurations. When refresh token rotation is enabled, the response typically includes a new refresh token and the client must replace the old one per policy.

### 5.1. Refresh Tokens Are Not Access Tokens

| Credential | Where used? | Sent to Resource Server? |
| --- | --- | --- |
| Access token | `Authorization: Bearer` when calling APIs. | **Yes**. |
| Refresh token | Token Endpoint with `grant_type=refresh_token`. | **No**. |
| ID token | Used by OIDC clients to verify user authentication per OIDC contract. | Never used instead of access tokens for APIs. |
| Client assertion | Client authentication to AS in token requests. | Never used as an API Bearer access token. |

Resource Servers must never accept refresh tokens in `Authorization: Bearer`. Refresh tokens often carry authority to mint new access tokens and therefore have higher sensitivity and a different usage boundary.

### 5.2. How Must Clients Replace Tokens?

After a successful refresh:

1. Update the new access token.
2. Update `expires_at`/`expires_in` and scope from the response.
3. If the AS returned a new refresh token, **persist the new token safely and invalidate the old copy in local state** per rotation policy.
4. Only use the new credentials after persistence succeeds.
5. Retry the API request if the operation is safe to replay.

Never keep a new refresh token solely in RAM while other workers still read the old refresh token. With rotation, that causes the AS to detect reuse and revoke the entire token family.

## 6. When Should Clients Refresh?

There are two common approaches.

### 6.1. Proactive Refresh Before Access Token Expiration

The client records expiration (e.g., `expires_in` from the token response) and refreshes ahead of a safety buffer:

```text
refreshAt = expiresAt - safetyWindow
```

For example, with a 60-minute token, a client might start refreshing a few minutes early depending on latency, clock skew, and UX. Actual values must reflect policy, not a fixed constant for every app.

Advantages:

- Reduces API 401s caused by expiration.
- Can refresh in the background while the app is active.
- Smoother user experience.

Drawbacks:

- Wastes token endpoint traffic if refreshing too early.
- Client must manage timers, clocks, and concurrency.
- Tokens can be revoked before expiry; proactive refresh does not replace 401 handling.

### 6.2. Reactive Refresh on `invalid_token`

The client calls the API, receives 401 `invalid_token`, and attempts a refresh if it holds a refresh token. This reacts directly to what the Resource Server observes, at the cost of extra latency on the first request after rejection.

Clients must avoid:

- Refreshing on every HTTP 401 even when no token was sent.
- Refreshing when the actual cause is wrong audience, issuer, or client configuration.
- Retrying requests indefinitely if the new access token is still rejected.
- Refreshing when the API returns 403 `insufficient_scope`.

### 6.3. Combining Both

A production client typically:

1. Uses token response lifetimes to refresh proactively before expiration.
2. Still handles 401 `invalid_token` because tokens can be revoked or policies can change.
3. Refreshes/retries at most once per request flow.
4. If the new token is still rejected, stops and reports an error or triggers re-authorization.

**Never rely solely on client-side `exp` decoding to conclude a token is valid.** Clients can read time hints for scheduling, yet the Resource Server and AS remain the authorities validating credentials under trust policies.

## 7. What If the Client Has No Refresh Token?

Not every OAuth grant issues refresh tokens.

| Client / grant | How to get a new access token on expiry |
| --- | --- |
| Authorization Code (user-delegated) | Use the refresh token if issued by AS and valid; otherwise re-run the authorization flow as needed. |
| Authorization Code + PKCE for public clients | May receive refresh tokens per policy; must protect them and follow rotation/sender constraints. |
| Client Credentials (machine-to-machine) | Typically request a new access token via the client credentials grant; do not assume a refresh token exists. |
| Device Authorization | May use a refresh token if issued by AS; if expired/revoked, re-authorize on the device. |
| SPA / BFF | Architecture-dependent: BFF can hold refresh tokens server-side; public SPAs must apply appropriate protections. |

### 7.1. Client Credentials: Requesting a New Access Token

Example:

```http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <workload-client-auth>

grant_type=client_credentials&scope=reports:read
```

The client obtains a new access token using the workload's registration and credentials. Never try sending a refresh token if the AS did not issue one and the grant does not use refresh tokens.

### 7.2. Authorization Code: Refresh or Re-Login

If a refresh token expires or is revoked, the client must re-run the configured authorization flow. For browser applications, that typically redirects the user to the Authorization Server to log in and consent again; for a BFF, the server manages the session and appropriate redirect.

Never ask users to paste refresh tokens into forms, support tickets, or chat.

## 8. Handling Errors at the Token Endpoint

Refresh requests can fail too. Common OAuth errors:

| Token endpoint error | Meaning | Client action |
| --- | --- | --- |
| `invalid_grant` | Refresh token invalid, expired, revoked, reused after rotation, or mismatched grant/client. | Stop retrying the same refresh token; clear old credentials and re-authorize when appropriate. |
| `invalid_client` | Client authentication failed or client unrecognized. | Stop and report configuration/credential error; do not treat merely as an expired user session. |
| `invalid_scope` | Requested scope invalid or exceeds allowed bounds. | Fix request per grant/consent; do not retry identical requests indefinitely. |
| `unauthorized_client` | Client not authorized to use this grant. | Check client registration and AS policy. |
| `unsupported_grant_type` | AS does not support the requested grant. | Fix configuration/protocol; do not retry. |
| HTTP 429/5xx/timeout | Rate limit or service error. | Bounded backoff; retain token state per policy without using tokens known to be invalid. |

Example error response:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "error": "invalid_grant",
  "error_description": "The refresh token is invalid"
}
```

Never write raw refresh tokens to logs or show them to users. Clients can branch on the machine-readable `error`; never depend on `error_description`.

### 8.1. `invalid_grant` Does Not Mean Blindly Looping Login

`invalid_grant` is a broad error category. Depending on the system, it can stem from:

- Expired refresh token.
- Revoked refresh token.
- Token rotation issued a new token, yet the client reused the old one.
- Refresh token does not belong to the current client/grant.
- User/admin revoked the grant or consent.

The client should stop retrying that credential, clear/mark the state invalid per policy, and start a new authorization flow if user interaction is needed. If a race condition caused it, fix refresh synchronization rather than forcing users to log in repeatedly.

## 9. Refresh Token Rotation and Synchronizing Concurrent Requests

With **refresh token rotation**, the AS issues a new refresh token on every successful use and invalidates the old one. This helps detect stolen credentials being reused.

Example:

```text
Initially:
  Access A1 + Refresh R1

Successful refresh:
  Access A2 + Refresh R2
  R1 can no longer be used

Subsequent requests:
  Client must use R2, not R1
```

### 9.1. A Common Race Condition

Suppose three requests simultaneously detect access token A1 expired:

```mermaid
sequenceDiagram
    participant R1 as Request 1
    participant R2 as Request 2
    participant R3 as Request 3
    participant S as Shared Token Store
    participant AS as Authorization Server
    R1->>S: Read A1/R1
    R2->>S: Read A1/R1
    R3->>S: Read A1/R1
    R1->>AS: Refresh with R1
    R2->>AS: Refresh with R1
    R3->>AS: Refresh with R1
    AS-->>R1: A2/R2; R1 rotated
    AS-->>R2: invalid_grant (reuse/old token)
    AS-->>R3: invalid_grant or reuse detected
    R1->>S: Write A2/R2
```

Depending on the AS, reusing an old token can **revoke the entire token family** or grant. Therefore, clients need **single-flight refresh** or per-grant/session locking.

### 9.2. Single-Flight Pattern

```text
Request 1 ─┐
Request 2 ─┼─> Shared refresh operation (one per grant)
Request 3 ─┘          |
                     v
              POST token endpoint once
                     |
                     v
          Atomically store new token pair
                     |
                     v
           Release all waiting requests
```

Design:

1. Use a lock/lease scoped to **client registration + principal/session/grant**—never lock the entire application needlessly.
2. After acquiring the lock, **re-read the token store**; another request may have already refreshed.
3. If a new access token is already present, do not refresh a second time.
4. If refresh is still needed, send the current token to the AS.
5. Persist both the new access token and refresh token **atomically**.
6. Release waiting requests only after the update completes.
7. If the process crashes between response and token persistence, handle rotation recovery per AS capabilities; never assume the old refresh token still works.

In multi-pod deployments, an in-JVM lock is insufficient. Use an appropriate shared coordination/token store such as database transactions, distributed locks, or a single BFF/session owner, accounting for failure modes.

### 9.3. Atomic Persistence

If the new access token is saved without the new refresh token (or vice versa), state becomes inconsistent. One transaction/record update should swap both together:

```text
authorized_client:
  registration_id
  principal_or_session_id
  access_token_ciphertext
  access_token_expires_at
  refresh_token_ciphertext
  refresh_token_version
  updated_at
```

This is a **conceptual schema**, not Spring's default schema. Token data must be encrypted, access-controlled, retention-bounded, and audited.

## 10. Retrying Requests After Refresh: Only Once and Safely

A straightforward client algorithm:

```text
1. Send request with current access token.
2. If not 401 invalid_token:
     handle response normally.
3. If 401 invalid_token:
     acquire lock and check token store.
4. If token was already refreshed by another request:
     use new token.
   If not:
     refresh or reacquire per grant.
5. If refresh fails:
     stop; re-authorize or report error.
6. Retry request at most once with new access token.
7. If still 401/403:
     stop and report error; do not loop.
```

### 10.1. Do Not Retry 403 `insufficient_scope`

A valid token lacking scope normally cannot be fixed by a standard refresh token grant. To obtain new permissions, the client needs an appropriate authorization/consent request. Retrying with the same token only wastes traffic without changing permissions.

### 10.2. Do Not Retry Every 401

A 401 may occur because:

- No token was sent.
- Token has wrong audience/issuer.
- Token has invalid signature.
- Token was revoked.
- Resource Server is misconfigured.
- Gateway/AS dependency errors were mapped to 401 by custom handling.

A client can try refreshing once on `invalid_token`, yet must stop if the new token is also rejected. If no credentials were sent, fix token acquisition; if the audience is wrong, fix registration/resource targets rather than refreshing endlessly.

### 10.3. HTTP Methods and Idempotency

| Request | Safe to retry after refresh? | Notes |
| --- | --- | --- |
| GET | Usually yes, if there is no request body or side effects. | Verify the actual API has no side effects on GET. |
| HEAD | Usually yes. | Per endpoint contract. |
| OPTIONS | Usually yes. | CORS/preflight may not require Bearer tokens. |
| PUT | Yes if idempotent per API contract and body is replayable. | Ensure the server did not partially process before returning 401. |
| DELETE | Possible per idempotent contract; still guard side effects. | Do not retry if uncertain whether the first request took effect. |
| POST | **Never blindly auto-retry**. | Use `Idempotency-Key`/operation IDs and verify the first request was rejected before creating side effects. |
| Streaming upload | Depends on whether the body can be replayed. | Often non-replayable; design resumable uploads or acquire fresh tokens beforehand. |

### 10.4. Idempotency-Key for POST

Example:

```http
POST /api/orders HTTP/1.1
Authorization: Bearer <new-access-token>
Idempotency-Key: 2e7f7b8c-...
Content-Type: application/json

{"productId":"P-100","quantity":1}
```

If the client must retry due to auth refresh, the same logical operation must reuse **the exact same `Idempotency-Key`** per server contract. The server must store idempotency outcomes and ensure two submissions do not create duplicate orders.

Never attach a key and claim the API supports idempotency if the server does not implement it.

## 11. Resource Servers Should Not Control Refresh Token Lifecycles

Anti-pattern design:

```java
// WRONG credential boundary: Resource Server accepts refresh token
// from API request and calls token endpoint on caller's behalf.
@PostMapping("/api/orders")
public Mono<?> create(
        @RequestHeader("Authorization") String bearer,
        @RequestHeader("X-Refresh-Token") String refreshToken) {
    // ...
}
```

Do not add:

- An `X-Refresh-Token` header.
- A `refresh_token` query parameter.
- A request body field containing a refresh token so "the API renews itself."
- Resource Server logic storing every user's refresh token just to handle 401s.

That conflates the Resource Server with the OAuth client, heightens leak exposure, and passes refresh tokens across unnecessary services.

**If the architecture is a Backend-for-Frontend (BFF)**, the BFF can act as an OAuth client, hold refresh tokens server-side, and call Resource Servers with access tokens. Even then, BFF and Resource Server remain **two separate logical responsibilities**; refresh tokens are never forwarded to API resources.

## 12. Configuring Spring Security Resource Server to Return Bearer Challenges

In a Servlet application, configure OAuth2 Resource Server:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.http.HttpMethod;
import org.springframework.security.oauth2.server.resource.web
        .BearerTokenAccessDeniedHandler;
import org.springframework.security.oauth2.server.resource.web
        .BearerTokenAuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ResourceServerSecurityConfiguration {

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        BearerTokenAuthenticationEntryPoint entryPoint =
                new BearerTokenAuthenticationEntryPoint();
        entryPoint.setRealmName("orders-api");

        BearerTokenAccessDeniedHandler deniedHandler =
                new BearerTokenAccessDeniedHandler();
        deniedHandler.setRealmName("orders-api");

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders:read")
                        .requestMatchers(HttpMethod.POST, "/api/orders/**")
                            .hasAuthority("SCOPE_orders:write")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .authenticationEntryPoint(entryPoint)
                        .accessDeniedHandler(deniedHandler)
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
```

Standard handlers:

- `BearerTokenAuthenticationEntryPoint` handles authentication failures and Bearer challenges.
- `BearerTokenAccessDeniedHandler` handles access denied in Bearer resource-server flows.
- Spring Security usually configures appropriate handlers automatically with `oauth2ResourceServer`; the example above sets the realm explicitly.

This code uses the **Servlet stack** (`HttpSecurity`, `SecurityFilterChain`). If the project uses WebFlux, use `ServerHttpSecurity`, `SecurityWebFilterChain`, and the matching reactive handlers; never mix Servlet APIs.

### 12.1. 401 When Token Is Missing and `invalid_token` When Token Is Invalid

With default Bearer handling, the Resource Server can:

- Missing Bearer credential: return 401 with realm challenge.
- Invalid Bearer credential: return 401 with `error="invalid_token"`.
- Valid token lacking scope: return 403 and `insufficient_scope` challenge where semantically appropriate.

Never build custom error bodies containing `exception.getMessage()` or raw tokens. If customizing handlers, preserve HTTP semantics and test `WWW-Authenticate`.

### 12.2. JWT and Opaque Token Configurations Are Two Verification Choices

JWT:

```java
.oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
```

Opaque:

```java
.oauth2ResourceServer(oauth2 ->
        oauth2.opaqueToken(Customizer.withDefaults()))
```

Configure strictly according to your actual token contract. One endpoint should not automatically try JWT and then fall back to opaque when JWT fails. If a system accepts multiple token types, design a resolver/route policy with a trusted discriminator and test negative cases.

## 13. Spring WebFlux Resource Server

In WebFlux, configure reactively:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class ReactiveResourceServerConfiguration {

    @Bean
    SecurityWebFilterChain api(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public/**").permitAll()
                        .pathMatchers("/api/orders/**")
                            .hasAuthority("SCOPE_orders:read")
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
```

Spring Security WebFlux provides Bearer authentication/authorization handling for reactive pipelines. When customizing handlers, use APIs from the **server/reactive namespace** for your exact version (e.g., server-side Bearer entry point/access-denied handlers); never pass Servlet handlers into `ServerHttpSecurity`.

**A WebFlux Resource Server does not refresh tokens for callers either.** It receives Bearer access tokens, verifies them with `ReactiveJwtDecoder` or `ReactiveOpaqueTokenIntrospector`, and returns corresponding errors. The reactive OAuth client is where `ReactiveOAuth2AuthorizedClientManager` acquires and refreshes tokens.

## 14. Client-Side Refresh in Spring Security OAuth2 Client

Spring Security OAuth2 Client can manage authorized clients and refresh tokens. Distinguish:

- **Resource Server**: verifies tokens arriving at the API.
- **OAuth2 Client**: uses registrations to acquire tokens for calling other APIs.

### 14.1. Servlet `OAuth2AuthorizedClientManager`

Example configuring a provider supporting authorization code, refresh token, and client credentials:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.web
        .DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web
        .OAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.registration
        .ClientRegistrationRepository;

@Configuration
class OAuthClientConfiguration {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
                OAuth2AuthorizedClientProviderBuilder.builder()
                        .authorizationCode()
                        .refreshToken()
                        .clientCredentials()
                        .build();

        DefaultOAuth2AuthorizedClientManager manager =
                new DefaultOAuth2AuthorizedClientManager(
                        registrations, authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

The `refreshToken()` provider enables the manager to use the authorized client's refresh token when needed per state, expiry, and configuration. The `clientCredentials()` provider obtains access tokens via the corresponding grant; do not assume that flow has refresh tokens.

This configures an **OAuth2 Client in a Servlet web application**, not a Resource Server.

### 14.2. Using `OAuth2AuthorizedClientManager` to Authorize

Example obtaining an authorized client:

```java
OAuth2AuthorizeRequest request =
        OAuth2AuthorizeRequest
                .withClientRegistrationId("orders-client")
                .principal(authentication)
                .build();

OAuth2AuthorizedClient client =
        authorizedClientManager.authorize(request);

if (client == null) {
    throw new IllegalStateException(
            "Could not authorize OAuth2 client");
}

String accessToken =
        client.getAccessToken().getTokenValue();
```

This illustrates Servlet context usage; `authentication` must be an appropriate principal and the manager must be invoked within the configured lifecycle. In a reactive app, never call this synchronous API on the event loop.

### 14.3. `ReactiveOAuth2AuthorizedClientManager`

In WebFlux, use the corresponding reactive client manager/provider. Configuration skeleton:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration
        .ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client
        .AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client
        .ReactiveOAuth2AuthorizedClientService;

@Configuration
class ReactiveOAuthClientConfiguration {

    @Bean
    ReactiveOAuth2AuthorizedClientManager reactiveAuthorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ReactiveOAuth2AuthorizedClientService authorizedClientService) {

        ReactiveOAuth2AuthorizedClientProvider provider =
                ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                        .clientCredentials()
                        .refreshToken()
                        .build();

        var manager =
                new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                        registrations, authorizedClientService);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

These imports/APIs belong to reactive OAuth2 Client; pick the right manager for **service/background contexts** vs. **web exchange contexts** depending on your application. In a WebFlux controller with a user principal and per-request repository, use `DefaultReactiveOAuth2AuthorizedClientManager` with `ServerOAuth2AuthorizedClientRepository`. In services without a `ServerWebExchange`, use the service-backed manager.

**Never call `block()` on `Mono<OAuth2AuthorizedClient>`** on the Netty event loop. Compose results with `flatMap`/`map` and let Reactor manage subscriptions.

### 14.4. A Manager Does Not Automatically Retry Every 401 Request

The authorized-client manager authorizes, re-authorizes, and refreshes via providers. Whether an API request that already received 401 is **replayed** depends on WebClient filters, failure handlers, token stores, and request replayability.

Therefore, test separately:

- Token expired before request: does the manager refresh/reacquire properly?
- Resource Server returns 401 `invalid_token` even though client thinks token is live: does the client handle it per policy?
- Two concurrent requests: does refresh token rotation race?
- 403 `insufficient_scope`: does the client avoid a refresh loop?
- POST/streaming requests: is the body replayable and is idempotency protected?

Never assume a filter automatically handles the entire refresh/retry lifecycle in every Spring Security setup.

## 15. Non-Spring HTTP Clients: Handling Challenges per Protocol

Pseudocode:

```text
response = send(request, currentAccessToken)

if response.status == 401
   and response.WWW-Authenticate contains Bearer error="invalid_token":

    newToken = refreshOrAcquireTokenOnce()

    if newToken is unavailable:
        requireAuthorizationAgainOrFail()
    else if requestCanBeSafelyReplayed:
        response = send(originalRequest, newToken)
    else:
        return explicitRetryRequired(newToken)

return response
```

Pseudocode does not replace a standards-compliant HTTP parser. `WWW-Authenticate` has its own grammar and can carry multiple challenges/parameters; avoid naive substring parsing in production when your HTTP/OAuth client library supports Bearer challenges.

### 15.1. One Retry Is a Useful Limit

Do not do:

```text
while response is 401:
    refresh()
    retry()
```

A loop can:

- Flood the AS with hundreds of token requests.
- Cause lock contention and refresh-token reuse.
- Mask issuer/audience/client configuration bugs.
- Overload both the Resource Server and Authorization Server.

Cap refreshes/retries, emit redacted telemetry, and send the user into the authorization flow when necessary.

### 15.2. Check Which Token the Failed Request Used

Under concurrency, one request might receive 401 for `A1` while another already refreshed to `A2`. Before calling the AS:

1. Read the current token store.
2. If the stored token already differs from the failed request's `A1`, use `A2` and retry safely.
3. If the token is still `A1`, join the shared refresh or perform a single refresh.
4. Never send old `R1` after another request already persisted `R2`.

This prevents redundant refreshes and cuts rotation reuse risks.

## 16. 401 Can Stem from Revocation, Not Just Expiration

A Resource Server can reject an access token before `exp`:

- User/admin revoked consent or session.
- AS revoked the refresh-token family or access-token grant.
- Client registration was disabled.
- Audience/issuer policy changed.
- Introspection reported `active=false`.
- Token signing key was revoked or distrusted.

The client receives `invalid_token` without knowing the exact reason. If the refresh token remains valid, the AS can issue a new access token; if the entire grant was revoked, the AS returns `invalid_grant` and the client must re-authorize.

**Never treat refresh tokens as a way to bypass revocation policies.** The AS is entitled to reject refresh tokens or revoke the whole grant/token family.

### 16.1. Key Rotation Differs from Refresh Token Rotation

Two similarly named mechanisms target different things:

| Mechanism | Target | Goal |
| --- | --- | --- |
| JWT signing-key rotation | Private/public signing keys and JWKS | Replace token-signing keys so Resource Servers update trusted public keys. |
| Refresh token rotation | OAuth grant's refresh token | Replace the refresh token on every use and detect reuse. |
| Access token renewal | New access token | Issue fresh API credentials before/after the old token expires or is rejected. |

JWT signing-key rotation **does not automatically refresh access tokens** on clients. Refresh token rotation **does not automatically rotate JWKS**. Keep tests and runbooks separate.

## 17. Opaque Introspection and Client Renewal

With opaque tokens, the Resource Server calls AS introspection:

```http
POST /oauth2/introspect HTTP/1.1
Host: login.example.test
Authorization: Basic <resource-server-client-credential>
Content-Type: application/x-www-form-urlencoded

token=<caller-access-token>
```

If the AS returns:

```json
{"active": false}
```

the Resource Server rejects the token and typically returns 401 `invalid_token` to the caller. The client can refresh/reacquire a token via the **Token Endpoint**, but never calls introspection directly to determine its own permissions.

### 17.1. Distinguish Caller Token Errors from Resource Server–AS Errors

| Failure | Meaning | Operational action |
| --- | --- | --- |
| Introspection HTTP 200 + `active=false` | Caller token is inactive per AS. | Resource Server returns 401; client considers refresh/re-auth. |
| Introspection HTTP 401 `invalid_client` | Resource Server client credentials are wrong. | Fix secret/certificate/registration; do not force every user to re-login as if tokens expired. |
| Introspection timeout/503 | AS/network unavailable. | Fail closed, classify dependency; may return 5xx/503 per handler. |
| Introspection `active=true`, missing scope | Authentication succeeded, insufficient permissions. | 403. |

Some implementations map authentication dependency errors to 401 under default handlers. If the app must distinguish dependency outages as 503, design explicit exception handling without leaking upstream responses and **never create a principal when introspection fails**.

### 17.2. Clients Must Not Refresh Because of Server Credential Errors

If all opaque token requests fail simultaneously with 401 because the Resource Server is using an outdated client secret, refreshing user tokens will not fix it—it only adds AS load. Monitoring must distinguish:

- `active=false`.
- `invalid_client` from the introspection caller.
- TLS/connection timeouts.
- AS 5xx responses.

Clients may receive a generic response, while operations must have correlation IDs and metrics pinpointing which hop failed.

## 18. OIDC Sessions and Refresh Tokens

OIDC adds an ID token and user authentication context, yet **the access token remains the credential for calling APIs**. A web app may:

1. Log in via the Authorization Code Flow.
2. Receive an ID token and access token, plus optionally a refresh token per policy.
3. Call the Resource Server using the access token.
4. When the access token expires, have the OAuth client/BFF refresh per grant or trigger re-login.

### 18.1. Do Not Use ID Tokens to Call APIs Instead of Access Tokens

Never send:

```http
Authorization: Bearer <OIDC-ID-token>
```

just because it is unexpired and validly signed. Resource Servers expect the access-token profile, issuer, audience/resource, and appropriate scopes. ID tokens usually carry the client ID as `aud`, not the API resource.

### 18.2. BFF Holds Refresh Tokens Server-Side

In a BFF architecture:

```text
Browser ── session cookie ──> BFF
                               |
                               | access token
                               v
                         Resource Server

BFF ── refresh token grant ──> Authorization Server
```

The browser holds only an appropriately configured HttpOnly/Secure/SameSite session cookie; the BFF keeps authorized clients and refresh tokens server-side. The BFF must protect sessions, CSRF, and token stores according to the application's threat model.

Never pass refresh tokens back to JavaScript to let the browser refresh itself when the BFF architecture was chosen to keep credentials server-side.

### 18.3. SPA / Mobile Public Clients

Public clients cannot keep a client secret confidential. If the AS issues refresh tokens to a public client, apply current AS requirements and OAuth security best practices such as:

- Authorization Code + PKCE for login.
- Refresh token rotation or sender-constrained refresh tokens per AS support.
- Secure platform storage on mobile; avoid plaintext `localStorage` when the threat model demands stronger protection.
- XSS/CSRF protections suited to how tokens are held.
- No tokens in logs or analytics.

Public clients must never embed a client secret pretending to be a confidential client.

## 19. Token Responses and Expiration Times

Token endpoints typically return:

```json
{
  "access_token": "<value>",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "<optional-value>",
  "scope": "orders:read"
}
```

Clients should store:

- Access token (protected).
- Retrieval timestamp and `expires_in`.
- Refresh token if issued by AS.
- Associated scope, resource, and client registration.
- Token state version/rotation metadata if needed.

### 19.1. `expires_in` and Clock Skew

`expires_in` is a duration measured from when the AS generated the response per contract. Clients can apply a safety window to avoid sending tokens right at expiration. Client clocks may drift, so avoid relying unconditionally on local wall-clock time.

If a client decodes `exp` from a JWT:

- Use it strictly as a scheduling/UX hint.
- Never trust the payload to grant authorization or ignore 401s.
- Never log the JWT for debugging.
- The Resource Server still validates the token independently.

### 19.2. Never Cache Access Tokens Indefinitely

Token caches must be:

- Expiration-aware.
- Keyed by client registration, principal, session, and resource.
- Invalidated on revocation, `invalid_grant`, or client logout.
- Synchronized on rotation.
- Encrypted and access-controlled.
- Retention-bounded and audited.

Never share one global access token across all tenants or users when the authorization contract requires isolating principals or resources.

## 20. Logout, Revocation, and Token Lifecycle

Logout has different meanings depending on architecture:

- Clearing the client/BFF session.
- Revoking refresh tokens/grants at the AS if a revoke endpoint and policy exist.
- Clearing authorized-client/token caches.
- Revoking server sessions.
- Invalidating access tokens per AS mechanisms (introspection, denylist, short lifetime, or sender-constrained tokens).

**Deleting an access token in the browser does not revoke it at the AS.** Offline JWTs can remain accepted until `exp` if the Resource Server lacks a revocation check/denylist. Opaque introspection can reflect revocation faster depending on caching.

### 20.1. Revoked Refresh Tokens

Once the AS revokes a refresh token:

- The client must stop using the old token.
- Subsequent refreshes may return `invalid_grant`.
- Already-issued access tokens may stay valid until `exp` if the AS/Resource Server lacks immediate revocation.
- If rapid logout/revocation is required, design appropriate token lifetimes, introspection, session versions, or denylists.

### 20.2. Logout Must Not Rely on a Client-Only Flag

A JavaScript flag `loggedOut=true` is not enough to revoke issued credentials. Define server-side session/grant lifecycles and know the exact window during which APIs might still accept old tokens.

## 21. End-to-End Testing of Resource Server and OAuth Client Flows

A strong test suite does not stop at verifying the Resource Server returns 401; it proves **the client handles challenges and refreshes properly**.

### 21.1. Resource Server Matrix

| Case | Request | Token state | Expected result |
| --- | --- | --- | --- |
| RS-01 | Protected endpoint, no Bearer | No credential | 401 + Bearer challenge, usually without `error`. |
| RS-02 | Expired Bearer token | Invalid token | 401 `invalid_token`. |
| RS-03 | Revoked/inactive Bearer token | Invalid token | 401 `invalid_token`. |
| RS-04 | JWT with bad signature | Invalid token | 401; never enters controller/domain. |
| RS-05 | JWT with wrong issuer/audience | Invalid token | 401; does not create `Authentication`. |
| RS-06 | Opaque introspection `active=false` | Inactive | 401. |
| RS-07 | Valid token, missing scope | Authenticated, denied | 403; `insufficient_scope` if appropriate. |
| RS-08 | Valid token, sufficient scope, right tenant | Authenticated, allowed | 2xx per endpoint. |
| RS-09 | Sufficient scope, wrong owner/tenant | Domain denied | 403/404 per contract. |
| RS-10 | Malformed Bearer header | Invalid request | 400/401 per resolver and RFC semantics. |
| RS-11 | Introspection/JWKS unavailable | Unverifiable | Fail-closed; status per dependency policy. |
| RS-12 | Error response | N/A | Contains no raw tokens, secrets, internal JWKS, or stack traces. |

### 21.2. OAuth Client Matrix

| Case | API response | Token endpoint | Expected result |
| --- | --- | --- | --- |
| CL-01 | 401 `invalid_token`, valid refresh token | 200 + new access | Persist new token and retry at most once if replay-safe. |
| CL-02 | 401 `invalid_token`, revoked refresh token | 400 `invalid_grant` | Stop retrying, clear stale credentials, re-authorize as needed. |
| CL-03 | 401 with no Bearer credential | Not called | Acquire access token per flow; do not assume a refresh token exists. |
| CL-04 | 403 `insufficient_scope` | No auto-refresh | Prompt/request appropriate permissions or surface insufficient access. |
| CL-05 | 400 `invalid_request` | No refresh | Fix request/headers. |
| CL-06 | 503 Resource Server unavailable | Do not refresh solely on status | Back off per API policy; preserve dependency classification. |
| CL-07 | 401 after new token already used | Do not refresh a second time | Stop; report issuer/audience/config or session error. |
| CL-08 | Three concurrent 401s on same token | One refresh operation | Single-flight; all three use new token if replay-safe. |
| CL-09 | Refresh token rotation | AS returns R2 | Persist R2 atomically; never reuse R1. |
| CL-10 | POST with `Idempotency-Key` | Refresh succeeds | Replay same logical operation once per contract. |
| CL-11 | Non-replayable POST body | Refresh succeeds | Do not auto-resend; require explicit retry. |
| CL-12 | Client Credentials access token expired | Token endpoint 200 `client_credentials` | Request new access token; do not assume refresh token. |

### 21.3. Combined Matrix

| Token | Endpoint | Resource Server | Client action | Expected |
| --- | --- | --- | --- | --- |
| Expired JWT A | Orders API | 401 `invalid_token` | Refresh token grant | New token + safe retry. |
| Wrong-audience JWT A | Orders API | 401 `invalid_token` | Refresh/reacquire only if it fixes registration; never loop | Stop if new token still fails. |
| Valid JWT A, no read scope | GET Orders | 403 `insufficient_scope` | No auto-refresh | Insufficient permissions. |
| Inactive Opaque B | Legacy API | 401 `invalid_token` | Refresh/reacquire per grant B | Retry once if successful. |
| Active Opaque B, no scope | Legacy API | 403 | No auto-refresh | Different scope/consent policy needed. |
| Client assertion sent to API | Orders API | 401 | Fix OAuth client flow | Do not refresh. |
| Refresh token sent to API | Orders API | 401 | Send proper access token | Never use refresh tokens at resources. |
| Wrong AS introspection secret | Legacy API | Fail-closed; possibly 5xx per handler | Do not refresh user token | Fix server-to-AS credentials. |

## 22. Testing with MockMvc and WebTestClient

### 22.1. MockMvc: Testing 401 and Bearer Challenges

For a Servlet Resource Server, write integration tests through the filter chain:

```java
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ResourceServerBearerErrorTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void missingTokenReturnsBearerChallenge() throws Exception {
        mockMvc.perform(get("/api/orders"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().exists(
                        HttpHeaders.WWW_AUTHENTICATE));
    }

    @Test
    void invalidTokenReturnsInvalidTokenChallenge() throws Exception {
        mockMvc.perform(get("/api/orders")
                        .header(HttpHeaders.AUTHORIZATION,
                                "Bearer invalid-test-token"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        HttpHeaders.WWW_AUTHENTICATE,
                        org.hamcrest.Matchers.containsString(
                                "invalid_token")));
    }
}
```

This test assumes `/api/orders` is protected, a real or test Resource Server decoder rejects `invalid-test-token`, and default Bearer handlers are active. With custom handlers, header assertions must match the app's contract.

### 22.2. Testing 403 When Token Is Valid but Lacks Scope

You can use `jwt()` test support to verify authorization:

```java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;

mockMvc.perform(get("/api/orders")
        .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_profile:read"))))
        .andExpect(status().isForbidden());
```

`jwt()` creates a simulated `Authentication`. This tests **authorization**, not JWT signature, issuer, or audience validation. To test invalid tokens, send a real Bearer value through the decoder.

### 22.3. WebTestClient for WebFlux

For WebFlux, run `WebTestClient` through `SecurityWebFilterChain`:

```java
webTestClient.get()
        .uri("/api/orders")
        .exchange()
        .expectStatus().isUnauthorized()
        .expectHeader().exists("WWW-Authenticate");
```

And with a test Bearer token:

```java
webTestClient.get()
        .uri("/api/orders")
        .headers(headers ->
                headers.setBearerAuth("invalid-test-token"))
        .exchange()
        .expectStatus().isUnauthorized();
```

Ensure the test client is bound to the application's security filters rather than invoking controllers directly.

## 23. Testing Refresh Token Grants with a Mock Authorization Server

Client tests need a mock AS to verify:

1. Client calls exact `POST /oauth2/token`.
2. `Content-Type` is form-urlencoded.
3. `grant_type=refresh_token` is sent properly.
4. Current refresh token goes to the AS, never to the Resource Server.
5. Client authentication matches the registered type and is not leaked.
6. `invalid_grant` stops retries and triggers re-authorization.
7. Refresh rotation persists the new token and never reuses the old one.
8. Two concurrent requests do not produce two refresh calls for the same grant.

Pseudo-test:

```text
Given:
  access token A1 expired
  refresh token R1 valid
  AS mock returns access token A2 and refresh token R2

When:
  client calls GET /api/orders with A1
  Resource Server returns 401 invalid_token
  client refreshes R1
  client retries with A2

Then:
  token endpoint refresh calls = 1
  API retry uses A2
  stored refresh token = R2
  stored refresh token != R1
  retry count for original request <= 1
```

This is a **test scenario**, not an executed test result. In test implementations, use dummy tokens, a mock AS, and a mock Resource Server; never use production tokens.

### 23.1. Testing `invalid_grant`

```text
Given:
  access token A1 rejected
  refresh token R1 revoked

When:
  client POSTs grant_type=refresh_token

Then:
  AS returns invalid_grant
  client does not reuse R1
  client does not loop refresh
  client clears/invalidates stale authorized-client state
  client starts authorization again when appropriate
```

### 23.2. Testing Concurrency

```text
Given:
  three API requests use same expired access token A1
  refresh token R1 is rotating

When:
  all three receive invalid_token concurrently

Then:
  one shared refresh operation occurs
  new token pair A2/R2 is stored atomically
  waiting requests read A2/R2
  R1 is not reused
  each replay-safe request is retried at most once
```

When testing multi-pod deployments, locks and token stores must use an appropriate shared mechanism. A unit test inside a single JVM does not prove distributed coordination works.

## 24. Token Storage Safety

Both access tokens and refresh tokens are bearer credentials in many models; whoever holds them can use them within their granted scope and lifetime. Because refresh tokens can usually mint new access tokens, they demand stronger protection.

### 24.1. Where Never to Store Tokens

Never store raw tokens in:

- Source code, Git repositories, committed YAML, or Docker images.
- Browser URLs or query strings.
- Analytics, crash reports, or frontend console logs.
- Application logs, reverse proxy access logs, or distributed traces.
- Support tickets, chat messages, or screenshots.
- Unencrypted database fields or broadly accessible caches.

### 24.2. Storage by Client Type

| Client | Protection approach |
| --- | --- |
| Server-side confidential client | Secret manager/KMS, encrypted token store, least-privilege service account. |
| BFF | Server-side refresh tokens, secure session cookies, CSRF protection, and session rotation. |
| Native mobile | Secure platform storage like Keychain/Keystore per platform policy; never embed client secrets. |
| Public SPA client | Minimize credential lifetime/scope, consider BFF; enforce XSS/CSRF defenses and refresh rotation/sender constraints. |
| Machine workload | Workload identity/secret manager, short-lived access tokens, credential rotation, and auditing. |

### 24.3. Redaction

Safe logging:

```java
log.info(
        "OAuth token renewal outcome: registration={}, result={}, requestId={}",
        registrationId,
        "success",
        requestId);
```

Never log:

```java
log.error(
        "Refresh failed: accessToken={}, refreshToken={}, clientSecret={}",
        accessToken, refreshToken, clientSecret);
```

For investigation, log correlation IDs, permitted grant/client registration IDs, error categories, and timestamps. Never include long token prefixes or suffixes "for easier identification."

## 25. When Must Clients Require Re-Login / Re-Authorization?

Common cases requiring re-authorization:

- Refresh token expired or revoked (`invalid_grant`).
- User/admin revoked consent or grant.
- Refresh-token family revoked after reuse detection.
- Client registration disabled or policy changed incompatibly.
- New scope requires consent/authorization that refresh grants cannot issue.
- User session or IdP policy demands fresh interaction (MFA, re-authentication).

The client should:

1. Clear or mark credentials stale per policy.
2. Preserve unsent or uncommitted business data safely.
3. Start Authorization Code + PKCE or the appropriate flow when user interaction is needed.
4. Never auto-resend write operations without idempotency.
5. Display a clear message without exposing tokens or internal errors.

Example UI message:

```text
Your session has expired. Sign in again to continue.
```

Never display `invalid_grant` alongside refresh tokens or stack traces to end users.

## 26. Common Design Mistakes

### Mistake 1 — Resource Server Refreshes Caller Tokens Itself

Resource Servers should never accept refresh tokens. Refreshing is the OAuth client's job with the AS.

### Mistake 2 — Client Refreshes on Every 401

A 401 can stem from missing credentials, wrong audience, issuer, signature, or configuration. Refresh only per challenge/policy and cap at one attempt.

### Mistake 3 — Refreshing on 403 `insufficient_scope`

The token is valid yet lacks permissions. Refreshing the same grant will not automatically add new scopes; use proper authorization/consent policies.

### Mistake 4 — Sending Refresh Tokens as API Bearer Credentials

Refresh tokens are not access tokens. Resource Servers must reject them.

### Mistake 5 — Infinite Request Retries

Creates token-endpoint/API loops, overloads systems, and hides configuration bugs. Bound retries.

### Mistake 6 — Retrying POST Without Idempotency

Can create duplicate orders or payments if the first request actually ran or the response dropped. Use `Idempotency-Key` and server-side deduplication per contract.

### Mistake 7 — Ignoring Refresh Token Rotation

A client reusing `R1` after the AS issued `R2` can trigger reuse detection and revoke the token family. Persist new token pairs atomically.

### Mistake 8 — Concurrent Requests Refreshing the Same Token

Causes race conditions. Use per-grant single-flight/locking and re-read the token store after acquiring the lock.

### Mistake 9 — Treating `invalid_grant` as a Network Error

`invalid_grant` is a grant/credential error, not something to retry like a timeout. Stop and re-authorize when needed.

### Mistake 10 — Treating Introspection Client Secret Errors as Expired Tokens

That is a Resource Server–AS error. Refreshing user tokens will not fix the Resource Server's secret.

### Mistake 11 — Returning Expiration Details in `error_description`

Clients only need standard error codes; never expose raw claims, tokens, or JWKS internals.

### Mistake 12 — Relying on Client-Side JWT `exp` as the Security Authority

Clients can schedule refreshes from `expires_in`/`exp`, yet the Resource Server must still validate independently. Client clocks are not authoritative.

### Mistake 13 — Assuming Logout Deletes Tokens Everywhere

Clearing local state does not automatically revoke offline JWTs or refresh grants at the AS. Design revocation and sessions explicitly.

### Mistake 14 — Not Testing the New Token After Refresh

The new token might carry the wrong audience, scope, or resource due to registration bugs. Test the actual retry against the Resource Server, not just that the token endpoint returned 200.

## 27. Illustrative Operational Scenarios

### A. Normal Access Token Expiration

The client sends an expired access token. The Resource Server returns 401 `invalid_token`. The client uses its valid refresh token, receives a new access token, persists state, and retries GET once. The API verifies the new token and returns 2xx when scope/resource match.

### B. Access Token Revoked While Refresh Token Remains Valid

The Resource Server/introspection rejects the access token. The client tries one refresh. The AS can issue a new access token if the grant remains valid. If the AS revoked the whole grant, it returns `invalid_grant` and the client must re-authorize.

### C. Valid Token Missing Scope

The client holds `orders:read` yet calls POST requiring `orders:write`. The Resource Server returns 403 `insufficient_scope`. The client does not refresh the same token repeatedly; it must request appropriate permissions via authorization policy or inform the user they lack access.

### D. Expired Client Credentials Token

A workload receives 401 `invalid_token`. It calls the token endpoint with `grant_type=client_credentials` to get a new access token. It does not assume a refresh token exists; if client authentication fails, it stops and raises an operational error.

### E. Refresh Token Rotation with Three Concurrent Requests

Three API requests share `A1/R1`. The single-flight coordinator sends a single refresh request, receives `A2/R2`, and persists atomically. All three requests proceed with `A2` if replayable. `R1` is never sent again.

### F. Revoked Refresh Token

The AS returns `invalid_grant`. The client stops refreshing, clears stale authorized-client state, and guides the user to re-authorize. `R1` is not retried.

### G. Wrong Audience

The client uses an access token meant for `payments-api` against `orders-api`. The Resource Server returns 401 `invalid_token`. Refreshing the same registration would likely produce another wrong-resource token; the client must fix resource/audience configuration rather than looping refreshes.

### H. Opaque Introspection AS Temporarily Unavailable

The Resource Server cannot verify the token, fails closed, and may return 503 per error handling. Clients handle service availability/backoff; never refresh user tokens merely because the Resource Server's AS is down.

### I. Resource Server Using an Old Introspection Client Secret

The AS returns `invalid_client` to the Resource Server. The API rejects tokens because it cannot verify them, yet the root cause is server credentials. Operations updates the secret; clients do not need to refresh every user session.

### J. POST Order Creation Receives 401

The client refreshes successfully and retries POST. If the API supports `Idempotency-Key`, the retry reuses the same key and the server deduplicates. If unable to guarantee the first request had no side effects or if the body is non-replayable, the client requires an intentional retry.

### K. User Logs Out at the IdP

The refresh grant is revoked. Offline JWT access tokens may remain accepted until `exp` without revocation checks. Logout design must account for token lifetimes, introspection, denylists, and session state.

### L. Browser Using a BFF

The browser sends a session cookie to the BFF. The BFF refreshes tokens server-side and calls Resource Servers with the new access token. Refresh tokens never reach the Orders API or browser JavaScript.

## 28. Flow-Based Test Checklist

The following items are **inputs for a test plan**, not executed results:

- [ ] No Bearer credential sent to protected endpoint → 401 challenge without requiring `invalid_token`.
- [ ] Expired Bearer token → 401 `invalid_token`.
- [ ] Revoked/inactive Bearer token → 401 `invalid_token`.
- [ ] Wrong signature/issuer/audience token → 401; does not enter business handler.
- [ ] Valid token missing scope → 403; client does not loop refreshes.
- [ ] Malformed Bearer request → 400/401 per contract; client fixes request.
- [ ] Valid refresh token → token endpoint returns new access token.
- [ ] Refresh token rotation → client atomically replaces old token with new token.
- [ ] Refresh token `invalid_grant` → does not retry same token; re-authorizes as needed.
- [ ] Expired Client Credentials → requests access token via client credentials grant.
- [ ] Concurrent requests → single-flight refresh, no reuse of old token.
- [ ] GET retry after refresh → at most once.
- [ ] POST retry → includes `Idempotency-Key` and replay-safe contract, or no auto-retry.
- [ ] New access token still returns 401 → stops without looping.
- [ ] AS introspection unavailable → fails closed, never fabricates a principal.
- [ ] Wrong introspection client secret → classified as server-side, not confused with invalid user tokens.
- [ ] Error responses/logs contain no raw access/refresh tokens, client secrets, or stack traces.
- [ ] Logout/revocation → access token and refresh grant behavior matches revocation policy.

## 29. Self-Check Questions

**1. Is the Resource Server responsible for refreshing access tokens?** No. It verifies tokens and returns results; the OAuth client calls the Token Endpoint to refresh or reacquire.

**2. When no token is sent, what should the Resource Server return?** Typically 401 with a Bearer challenge, without necessarily including `error="invalid_token"`.

**3. When a token is expired or revoked, which Bearer error fits?** `invalid_token`, typically HTTP 401.

**4. When a token is valid yet lacks scope?** `insufficient_scope`, typically HTTP 403.

**5. Should clients refresh on every 401?** No. Inspect whether a Bearer credential was sent, the challenge, and the client's grant/policy.

**6. Should clients refresh on 403 `insufficient_scope`?** Not automatically. A different permission/consent/authorization policy is required if permitted.

**7. Where are refresh tokens sent?** To the Authorization Server Token Endpoint with `grant_type=refresh_token`.

**8. Are refresh tokens sent to Resource Servers?** No.

**9. How do Client Credentials clients normally get new tokens?** Resubmit the client credentials grant; do not assume a refresh token exists.

**10. Should `invalid_grant` be retried with the same refresh token?** Never loop infinitely; the token may be expired, revoked, or rotated. Re-authorize when appropriate.

**11. What race condition does refresh token rotation create?** Concurrent requests using the same old token; the AS may detect reuse and revoke the token family. Use single-flight and atomic persistence.

**12. Can POST requests be retried after refresh?** Only when replay-safe, the body can be re-sent, and idempotency is guaranteed.

**13. What if the new token still gets 401?** Stop retrying, inspect issuer/audience/resource/client registration, and prompt re-authorization or report an error.

**14. Does introspection AS returning 401 mean the user's token expired?** Not necessarily; the Resource Server's own client credentials may be wrong.

**15. How does JWT signing-key rotation differ from refresh-token rotation?** One replaces signing keys/JWKS; the other rotates refresh credentials within an OAuth grant.

**16. Does deleting a token in the browser revoke the JWT at the Resource Server?** Not necessarily; offline JWTs can stay valid until `exp` without a revocation mechanism.

**17. Can clients use `exp` to schedule refreshes?** Yes as a hint, yet never in place of Resource Server verification.

**18. Does Spring `OAuth2AuthorizedClientManager` automatically retry every 401 API request?** Do not assume so; the manager/provider handles authorized clients/tokens, while request replay and failure handling must be configured and tested separately.

**19. Why omit detailed `error_description` values from Bearer challenges?** To avoid leaking tokens, keys, internal endpoints, stack traces, and personal data.

**20. Where does a BFF store refresh tokens?** In a protected server-side authorized-client/token store; the browser receives only an appropriate session mechanism.

## 30. Official References

- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** `WWW-Authenticate`, `invalid_request`, `invalid_token`, and `insufficient_scope`. https://www.rfc-editor.org/rfc/rfc6750
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** Token Endpoint and Refresh Token Grant. https://www.rfc-editor.org/rfc/rfc6749
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** protecting refresh tokens, rotation/sender constraints, and modern OAuth security best practices. https://www.rfc-editor.org/rfc/rfc9700
- **RFC 7009 — OAuth 2.0 Token Revocation:** revoking tokens at the Authorization Server. https://www.rfc-editor.org/rfc/rfc7009
- **RFC 7662 — OAuth 2.0 Token Introspection:** token `active` status. https://www.rfc-editor.org/rfc/rfc7662
- **RFC 9110 — HTTP Semantics:** 401/403 status codes and authentication challenges. https://www.rfc-editor.org/rfc/rfc9110
- **Spring Security Reference — Servlet OAuth 2.0 Resource Server JWT:** https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- **Spring Security Reference — Servlet OAuth 2.0 Resource Server Opaque Token:** https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- **Spring Security Reference — OAuth 2.0 Client:** https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html
- **Spring Security Reference — Reactive OAuth 2.0 Client:** https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html
- **Spring Security Reference — WebFlux OAuth 2.0 Resource Server:** https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html
- **Spring Security API — OAuth2AuthorizedClientManager / ReactiveOAuth2AuthorizedClientManager:** consult the Javadoc for your exact Spring Security version.

## 31. Conclusion

The Resource Server must return **protocol-compliant Bearer challenges and HTTP status codes** so clients understand credential state. `401 invalid_token` indicates the access token was rejected; the client can try refreshing/reacquiring once if its grant allows. `403 insufficient_scope` indicates the token authenticated yet lacks required permissions; refreshing the same grant is not a way to escalate scopes. `400 invalid_request` requires fixing the request, while JWKS/introspection dependency failures must be classified separately and **fail closed**.

When refresh succeeds, the client must store the new access token and new refresh token (if rotated) securely, coordinate concurrency with single-flight, and retry requests only when bodies are replayable and business operations are idempotent. If the AS returns `invalid_grant` or the new token is still rejected, the client stops looping and re-authorizes when appropriate.

**Boundary to preserve:** the Resource Server verifies access tokens; the OAuth client manages and renews credentials; the Authorization Server issues, rotates, and revokes tokens. When each side fulfills its role and tests cover statuses, challenges, token endpoints, concurrency, and side effects, the token lifecycle operates safely without leaking refresh credentials or unintentionally escalating access.
