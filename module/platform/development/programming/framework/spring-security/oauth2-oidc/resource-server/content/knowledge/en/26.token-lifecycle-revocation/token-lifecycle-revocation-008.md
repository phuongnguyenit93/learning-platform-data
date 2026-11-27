# Refresh Tokens Are the Responsibility of the Client and Authorization Server

In OAuth 2.0, **access tokens** and **refresh tokens** serve two different purposes. An access token is sent by the OAuth client to the **Resource Server** to access APIs. A refresh token is sent by the OAuth client to the **Authorization Server** to request a new access token when the current access token expires or is no longer usable. Refresh tokens are not credentials for calling business APIs, and the Resource Server is not responsible for exchanging them for access tokens.

This boundary is critical in a **Spring Security OAuth 2.0 / OIDC Resource Server** system. When an access token expires, the Resource Server must reject the request per the Bearer contract, typically with **401 Unauthorized** and an appropriate challenge. The OAuth client decides whether it can refresh or must ask the user to re-authenticate. The Authorization Server validates the refresh token, checks the client and authorization policy, and either issues a new access token or rejects the grant.

You can picture it as:

```text
OAuth Client                         Authorization Server
     |                                        |
     | 1. Request access token                |
     |--------------------------------------->|
     | 2. access_token + refresh_token        |
     |<---------------------------------------|
     |
     | 3. Authorization: Bearer access_token
     v
Resource Server
     |
     | 4. Verify access token / scope
     | 5. Return data or 401/403
     |
     | 6. If needed, client calls token endpoint
     |    with refresh_token
     +---------------------------------------> Authorization Server
     |                                        |
     | 7. New access_token and optionally     |
     |    new refresh_token                   |
     |<---------------------------------------+
```

**Key takeaway:** The Resource Server processes the current request's access token. The OAuth client manages the lifecycle of the tokens it holds. The Authorization Server decides whether a refresh token is still valid and whether to issue new tokens.

> **Illustrative context:** The Orders API runs Spring Boot 3.x / Spring Security 6.x as an OAuth 2.0 Resource Server. A web frontend or BFF acts as an OAuth client logging in via the Authorization Code flow. Access tokens are sent to the Orders API using `Authorization: Bearer ...`. Endpoint names, client IDs, and values in examples are illustrative only.

## 1. Access Tokens and Refresh Tokens Have Different Responsibilities

| Property | Access token | Refresh token |
|---|---|---|
| Purpose | Access Resource Server / API | Request a new access token from the Authorization Server |
| Sent to | Resource Server | Authorization Server token endpoint |
| Who holds/manages it in the flow | OAuth client receiving the token | OAuth client receiving the token |
| Who validates it | Resource Server via JWT validation or introspection | Authorization Server |
| Usage scope | Specific resource/audience, scope, and lifetime | Token endpoint, client/grant, and AS policy |
| May carry permissions | Yes, via scope/claims or introspection metadata | Never used directly as API authorization |
| Sent in API requests? | Yes, as Bearer if audience matches | **No** |
| Upon expiration | Client requests a new token; API rejects expired tokens | Client needs a new authorization grant or AS re-issuance flow |
| Revocation | May need introspection, denylist, or short TTL for rapid effect | AS can invalidate the refresh token / token family |
| Sensitivity | Replayable Bearer credential | Longer-lived credential, usually higher impact if leaked |

### 1.1. Access Tokens Are Credentials for the Resource Server

Example client calling the Orders API:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer ACCESS_TOKEN
Accept: application/json
```

The Resource Server verifies the token according to the configured token type:

- For **JWTs**, verify signature with a trusted key, issuer, audience, timestamps, token profile, and other validators.
- For **opaque tokens**, call the configured introspection endpoint and verify `active` along with required metadata.
- After authentication, enforce scope, tenant, ownership, and business permissions.

The Resource Server does not need the client's refresh token to perform any of those steps.

### 1.2. Refresh Tokens Are Credentials for the Token Endpoint

When an access token expires, the client may send:

```http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_CLIENT_ID_AND_SECRET

grant_type=refresh_token&
refresh_token=REFRESH_TOKEN
```

This is a **client → Authorization Server** request, not a **client → Orders API** request.

The Authorization Server validates at least the following per grant and policy:

- Does the refresh token exist, remain unexpired, and remain unrevoked?
- Was the refresh token issued to the calling client?
- Is client authentication valid if the client is confidential?
- Was the token issued under an active grant/session?
- Are the requested scopes/resources within the permitted boundaries?
- Are rotation, reuse detection, inactivity, and absolute lifetime policies satisfied?

If valid, the AS issues a new access token and optionally a new refresh token.

### 1.3. Never Treat a Refresh Token as a Second Access Token

Refresh tokens are often opaque strings and may be long-lived. That does not make them "a stronger Bearer token" for calling APIs.

A Resource Server must never accept:

```http
GET /api/orders HTTP/1.1
Authorization: Bearer REFRESH_TOKEN
```

If a refresh token is accidentally sent to an API, the Resource Server must reject it under the access-token validation/introspection contract. Never try calling the token endpoint with it, never store it in the security context as an access token, and never guess token types from string length or format.

## 2. Three Roles in the Refresh Token Lifecycle

### 2.1. OAuth Client

The client is responsible for:

- Receiving and protecting access/refresh tokens appropriate to the client type.
- Sending access tokens to the right Resource Server/audience.
- Detecting when an access token is no longer usable.
- Sending refresh tokens to the right Authorization Server token endpoint.
- Performing client authentication when required.
- Handling refresh token rotation and storing new tokens safely.
- Preventing concurrent requests from refreshing the same token in a way that triggers reuse detection.
- Prompting the user to re-authenticate when refresh fails and no other valid grant exists.
- Keeping refresh tokens out of URLs, API requests, logs, traces, and analytics.

### 2.2. Authorization Server

The AS is responsible for:

- Issuing refresh tokens only in permitted grants, clients, and flows.
- Binding refresh tokens to the client, authorization grant, user/session, and policy.
- Verifying refresh tokens upon receiving `grant_type=refresh_token`.
- Authenticating clients when required and bounding scopes/resources.
- Performing rotation or sender-constraining per security policy.
- Detecting refresh token reuse when rotation is enabled.
- Revoking refresh tokens / token families when necessary.
- Enforcing expiry, inactivity timeouts, absolute lifetimes, and consent policies.
- Auditing events and protecting the token store.

### 2.3. Resource Server

The Resource Server is responsible for:

- Accepting **access tokens** intended for the API.
- Verifying signatures/claims or introspecting tokens.
- Returning 401 when the access token is missing or invalid.
- Returning 403 when the token is valid but lacks sufficient permissions.
- Never accepting refresh tokens to access resources.
- Never calling the token endpoint to refresh a caller's token.
- Never asking callers to pass refresh tokens in API requests.
- Never storing callers' refresh tokens in sessions or databases just to serve API access, unless the application genuinely acts as an OAuth client/BFF in a separate outbound flow.

| Actor | What it must do | What is not its default responsibility |
|---|---|---|
| OAuth client | Decide when to refresh, send refresh grants, persist new tokens | Assert a refresh token is still active without asking the AS |
| Authorization Server | Verify refresh tokens, issue/rotate/revoke | Let Resource Servers guess token state |
| Resource Server | Verify access tokens and authorization | Exchange an API caller's refresh token for an access token |

## 3. The Refresh Token Grant in OAuth 2.0

RFC 6749 Section 6 describes the refresh token grant. The client sends a token endpoint request with `grant_type=refresh_token` and the previously received refresh token.

### 3.1. Basic Request

```http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic b3JkZXJzLWJmZjpwYXNzd29yZA==

grant_type=refresh_token&
refresh_token=REFRESH_TOKEN_VALUE
```

For confidential clients, the Authorization Server typically authenticates the client via its registered method, such as HTTP Basic in the illustration. The client secret must be protected like a server-side credential.

For public clients, there is no safe client secret to keep. The AS must identify the client via registration and apply appropriate refresh token protections, such as rotation or sender-constrained refresh tokens per OAuth 2.0 Security Best Current Practice.

### 3.2. Successful Response

Example:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "NEW_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 600,
  "refresh_token": "NEW_REFRESH_TOKEN",
  "scope": "orders.read orders.write"
}
```

Fields to understand:

- `access_token`: the new access token for calling Resource Servers.
- `token_type`: the token type, typically `Bearer`.
- `expires_in`: the access token's lifetime in seconds, if returned by the AS.
- `refresh_token`: the new refresh token if the AS issues/rotates one.
- `scope`: granted scopes; the client must honor the returned permissions rather than assuming they always match the prior request.

Not every response is required to return a new refresh token in every implementation. However, if the AS uses **refresh token rotation**, the client must replace the old token with the new one upon success.

### 3.3. A Refresh Grant Is Not a New Authorization Code Flow

The refresh token grant reuses a previously issued grant. It does not require the user to re-enter their password or open a browser on every refresh.

If the refresh token expires, is revoked, is reused, or becomes invalid, the client generally must restart the appropriate authorization flow (e.g., Authorization Code + PKCE) to obtain a new grant. Never try to "refresh a refresh token" by sending it to a Resource Server.

## 4. Why Should a Resource Server Not Refresh Tokens?

A Resource Server accepts requests from many different OAuth clients. By default, it does not own:

- The caller's client registration.
- The caller's client secret or private key.
- The refresh token.
- The original consent and authorization grant.
- The session/browser context needed for re-authentication.
- Authority to change client scopes or resources.

If a Resource Server accepts refresh tokens and calls the token endpoint itself, it assumes an OAuth client role without clear boundaries or governance.

### 4.1. Risks If an API Accepts Refresh Tokens

**Credential exposure:** refresh tokens typically outlive access tokens. If they appear in access logs, traces, or API gateways, the blast radius of an incident is much larger.

**Confused deputy:** the Resource Server might exercise a caller's credentials under the wrong client identity or audience, especially when multiple clients or tenants share an API.

**Broken permission boundaries:** the API may not know which client, grant, user, or resource the refresh token belongs to.

**Refresh token replay:** if multiple API instances refresh the same token concurrently, rotation/reuse detection can invalidate the entire token family.

**Session management issues:** the Resource Server does not own the browser/mobile client's authorization session and should not control their login flows.

**Poor auditability:** refreshing inside an API obscures which client requested the new token and under which grant.

### 4.2. The Proper Contract Between Client and API

```text
Client
  |
  | Authorization: Bearer access_token
  v
Resource Server
  |
  | 200 / 401 / 403
  v
Client decides next step
  |
  +-- access token still usable -> continue
  |
  +-- expired/invalid -> call AS token endpoint
  |
  +-- refresh rejected -> start authorization flow again
```

The Resource Server returns the verification result. The client coordinates refreshes. The AS decides whether the refresh grant is accepted.

### 4.3. Exception: An Application Acting as Both Resource Server and OAuth Client

A backend may simultaneously:

- Accept inbound access tokens to protect its own API.
- Use its own separate OAuth client registration to call downstream APIs.
- Store authorized clients and refresh tokens **for its own outbound grants**.
- Refresh outbound access tokens using Spring OAuth2 Client.

These are two separate roles within one application. It **does not** permit the backend to take an inbound caller's refresh token and use it as the service's refresh token or forward it downstream.

## 5. Expired Access Tokens: How Do the API and Client Handle Them?

Suppose an access token expires at 10:00. The client calls the Orders API at 10:01:

```http
GET /api/orders/42 HTTP/1.1
Authorization: Bearer EXPIRED_ACCESS_TOKEN
```

For JWTs, the decoder checks `exp` and rejects. For opaque tokens, introspection can return `active=false`. The Resource Server typically responds:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Cache-Control: no-store
```

The client can then attempt a refresh according to its policy.

### 5.1. The Resource Server Does Not Send Login Redirects

An API should not return a 302 redirect to `/login` or the OpenID Provider simply because an access token expired. Callers can be mobile apps, CLIs, backend services, or SPAs; each handles login differently.

For Bearer APIs, 401 and `WWW-Authenticate` tell the client that authentication was rejected. The client decides whether to refresh or prompt the user to re-authenticate via its authorization flow.

### 5.2. Clients Must Not Blindly Refresh on Every 401

A 401 can stem from:

- An expired access token.
- Wrong signature, issuer, or audience.
- A revoked token.
- A token not meant for this resource.
- A malformed token.
- Rejection by a gateway or another authentication layer.

A client may attempt **one controlled refresh** when the failure matches an access-token issue and refresh policy allows it. If the newly obtained token still gets 401, do not loop refreshes endlessly. Wrong audience or issuer is usually a configuration/client bug that refreshing the same grant cannot fix.

### 5.3. 403 Is Not a Default Refresh Signal

If an access token is valid yet lacks `orders.write`, the API may return 403. Refreshing a token does not automatically add new scopes. The AS can only grant new scopes if the authorization grant, consent, and policy permit them.

Clients must not react to every 403 with a refresh/login loop. Surface the authorization error or follow the appropriate permission-request workflow.

## 6. Step-by-Step Client Refresh Flow

A common flow:

```mermaid
sequenceDiagram
    autonumber
    participant App as OAuth Client
    participant API as Orders Resource Server
    participant AS as Authorization Server

    App->>API: Request + access token A1
    API-->>App: 401 invalid_token
    App->>AS: POST token endpoint, refresh_token=R1
    AS->>AS: Validate R1, client, grant, scope and policy
    AS-->>App: access token A2 + refresh token R2
    App->>App: Atomically replace A1/R1 with A2/R2
    App->>API: Retry request + access token A2
    API->>API: Verify A2 and authorize
    API-->>App: API response
```

### 6.1. Step 1: Store Access and Refresh Tokens in the Right Place for the Client

The client stores the token pair in a protection tier suited to its architecture:

- BFF / server-side application: server-side authorized-client store, encrypting sensitive data, with proper access controls and backups.
- Native mobile app: OS secure storage protected by the platform keystore/keychain.
- SPA: consider a BFF to avoid holding long-lived refresh tokens in JavaScript-accessible storage. If the SPA holds tokens, maintain a browser/XSS threat model and mitigations per OAuth security BCP.

Never send refresh tokens in requests to the Orders API.

### 6.2. Step 2: Call the Right Token Endpoint

The client sends the refresh token to the token endpoint of **the exact issuer/authorization server** that issued the grant. Never derive the endpoint from an arbitrary URL returned by an API, an unverified JWT claim, or a query parameter.

### 6.3. Step 3: AS Verifies the Grant

The AS validates the refresh token and client. If a refresh token belonging to client A is sent by client B, the request must be rejected. If the token is revoked, expired, or invalid, the AS refuses to issue a new access token.

### 6.4. Step 4: Replace the Token Pair Atomically

If the response includes a new refresh token, the client must update **both the access token and refresh token** as a single logical unit. Never save the new access token while forgetting the new refresh token, and never keep using the old refresh token after rotation succeeds.

### 6.5. Step 5: Retry the API Request with Control

The client resends the request with the new access token. Retry only a bounded number of times, prevent loops, and evaluate whether the request is safe to replay.

For POST/PUT/PATCH requests with side effects, use idempotency keys or proper semantics. If the first response was lost after the server already executed the action, retrying can duplicate side effects. Refresh tokens do not solve idempotency.

## 7. Refresh Token Rotation

**Refresh token rotation** is a mechanism where the AS issues a new refresh token upon a successful refresh and invalidates the old one.

Example:

```text
Initially:
  Access token A1
  Refresh token R1

Successful refresh:
  Access token A2
  Refresh token R2

After rotation:
  R1 = invalid
  R2 = current
```

Rotation reduces how long a stolen refresh token remains usable. It is especially critical for public clients that cannot safely keep a client secret.

### 7.1. Rotation Response

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "A2",
  "token_type": "Bearer",
  "expires_in": 600,
  "refresh_token": "R2",
  "scope": "orders.read"
}
```

The client must store `R2` and stop using `R1`. Keeping `R1` around "just in case" can trigger reuse detection or fail at the AS.

### 7.2. Reuse Detection

Suppose an attacker steals `R1`. The legitimate user refreshes first:

```text
R1 -> refresh succeeds -> R2
R1 is invalidated
```

Later the attacker reuses `R1`. The AS detects that an already-used refresh token was presented again. Depending on policy/implementation, the AS can revoke the associated **token family/grant** to prevent the attacker from continuing to use `R2`.

This may force the legitimate user's session to log in again as well. That is an intentional security response to signs of token replay.

### 7.3. Rotation Requires Server-Side State at the AS

A rotation implementation typically associates tokens with:

- Token family / grant ID.
- Client ID.
- Subject or user/session.
- Token generation / parent relationship.
- Active / used / revoked status.
- Issued-at, expiry, and inactivity timestamps.
- Sender constraint, if present.

Refresh tokens must be protected in the token store; storing hashes or equivalent protected forms limits exposure if the database is read. Exact storage depends on the AS implementation.

## 8. Race Conditions When Multiple Requests Refresh Concurrently

A common bug in SPAs, BFFs, and mobile apps: multiple API requests receive 401 nearly simultaneously and all use `R1` to refresh.

```text
Request A -> 401 -> refresh R1
Request B -> 401 -> refresh R1
Request C -> 401 -> refresh R1

AS receives:
  R1 -> success, issue R2
  R1 -> reuse/replay
  R1 -> reuse/replay

Possible result:
  token family revoked
  other requests fail
  user must log in again
```

### 8.1. Single-Flight Refresh

The client should enforce a **single-flight/mutex** per authorized client/session:

1. The first request notices a refresh is needed and acquires the lock.
2. Concurrent requests wait for the refresh outcome instead of calling the AS with `R1`.
3. The first request refreshes successfully and persists `A2/R2` atomically.
4. Waiting requests read the new token from the store.
5. API retries proceed only after the token pair update completes.
6. If refresh fails, all waiting requests receive the re-authentication-required state together.

Never use a single global lock across all users in the system. Scope the lock to the client/session/authorization grant, and coordinate across instances when running multiple application replicas.

### 8.2. Atomic Token Pair Update

Pseudocode:

```text
refreshIfNeeded(authorizedClient):
    acquire lock for (registrationId, principal/session)

    reload latest authorized client from store
    if latest access token is still valid:
        return latest access token

    response = call AS refresh grant with latest refresh token

    if response successful:
        atomically persist:
            new access token
            new expiry
            new refresh token if returned
        return new access token

    if response invalid_grant:
        remove/revoke local authorized-client state as policy requires
        require reauthentication

    release lock
```

The crucial detail is **reloading after acquiring the lock**. Another request may have already refreshed and updated the token while the current request was waiting.

### 8.3. Multi-Instance BFFs

If a BFF runs across multiple pods, an in-memory mutex only protects one pod. Options include:

- Sticky session routing if feasible and sufficiently reliable.
- Distributed locks per authorized-client/grant.
- Compare-and-set / versioned updates in the persistent token store.
- A refresh coordinator with clear ownership.
- Conflict handling when two instances see the same generation.

Never let two pods concurrently use a rotating refresh token without coordination.

## 9. When a Refresh Request Fails

A common error response:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{
  "error": "invalid_grant",
  "error_description": "The refresh token is invalid or expired"
}
```

### 9.1. `invalid_grant`

Possible causes:

- The refresh token expired.
- The token was revoked.
- An already-rotated token was reused.
- The token does not belong to the calling client/grant.
- The grant/session is no longer valid.
- The refresh token is malformed or does not exist.

The client usually needs to clear unusable authorized-client state and restart the authorization flow if the user needs to continue. Never retry the same refresh token indefinitely.

### 9.2. `invalid_client`

Client authentication failed, such as a wrong client secret or the client lacking permission for the grant. This is usually a configuration, client registration, or secret rotation bug. Never ask the user to log in again to mask a wrong client secret in a server-side BFF.

### 9.3. `invalid_scope`

The client requested scopes exceeding the original grant or disallowed by the AS. The client must not retry with broader scopes; it must honor the scopes granted by the AS and follow proper consent/authorization flows.

### 9.4. Timeouts or Dropped Connections: Ambiguous Outcomes

A tricky scenario:

1. Client sends `R1`.
2. AS succeeds, invalidates `R1`, and issues `R2`.
3. The response is lost on the network.
4. The client only sees a timeout, unaware `R2` was already issued.

If the client resends `R1`, the AS may treat it as reuse and revoke the token family.

Therefore, retrying a refresh grant **is not like retrying an idempotent GET**. Choose a strategy suited to the AS: bounded grace/reuse handling, sender-constrained tokens, recovery protocols, or forcing re-authentication when safe recovery is impossible. A client must not assume `R1` is still valid after a timeout.

## 10. Refresh Token Expiry, Inactivity, and Revocation

A refresh token may be subject to multiple time bounds:

| Limit | Meaning |
|---|---|
| Absolute lifetime | Maximum duration since issuance, even if actively used |
| Inactivity/idle timeout | Expires if unused for a configured period |
| Grant/session lifetime | Lifetime of the authorization grant or user session |
| Rotation generation policy | Bound on token family or generation lifecycle |
| Risk-based expiry | AS revokes/expires early under risk policy |
| Administrative revocation | User, admin, or security team revokes the grant or token |

Never assume refresh tokens always live indefinitely longer than access tokens. The AS can enforce short expirations, idle timeouts, or absolute lifetimes.

### 10.1. Revoking a Refresh Token Does Not Necessarily Invalidate Already-Issued Access Tokens Immediately

This is a pivotal point in lifecycle design:

- Revoking a refresh token stops the client from using it to obtain new access tokens.
- Yet previously issued access tokens can stay valid until `exp` if the Resource Server only verifies JWTs offline.
- With opaque token introspection, the AS can return `active=false` for affected access tokens if the AS links them and policy enforces it.
- If JWT access tokens must be revoked nearly immediately, add mechanisms like denylists, token version/session checks, introspection, or short access token lifetimes.

**Never infer "we revoked the refresh token so all existing API access tokens died immediately."** Actual behavior depends on how the AS manages grants and how Resource Servers verify access tokens.

### 10.2. Logout Does Not Mean Revoking All Tokens

Logout may involve multiple actions:

- Deleting session cookies / local application sessions.
- Ending the OIDC RP session or redirecting through the end-session endpoint if supported.
- Revoking refresh tokens/grants via the RFC 7009 revocation endpoint.
- Revoking access tokens if supported by the AS and observable by APIs.
- Clearing token caches / authorized-client state in the BFF.

OIDC logout and OAuth token revocation are related protocols/policies, yet **not automatically equivalent**. Define explicitly whether logout revokes refresh tokens, revokes access tokens, and how long Resource Servers take to observe changes.

## 11. Scopes and Resources During Refresh

A refresh grant is not a license to request arbitrary new scopes.

Under OAuth 2.0, scopes requested during refresh must not exceed those granted in the original authorization grant. The AS may return identical or narrower scopes per policy.

Initial response example:

```json
{
  "access_token": "A1",
  "refresh_token": "R1",
  "scope": "orders.read orders.write"
}
```

On refresh, the client may only continue using scopes granted under the grant. If the new response contains only:

```json
{
  "access_token": "A2",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "orders.read"
}
```

the client must not assume `orders.write` remains available. POST requests needing write permission must handle 403 or updated authorization state.

### 11.1. Audience / Resource Binding

If the AS supports resource indicators or audience-specific access tokens, refresh tokens may be bound to specific resources/grants. Clients must not use a refresh token from one API to mint tokens for an unauthorized resource.

Resource Servers only validate access tokens issued for **their own resource**. They must never accept refresh tokens and try inferring which resource to mint for.

### 11.2. Tenant Binding

In multi-tenant applications, refresh tokens/grants may belong to a specific issuer, tenant, or client context. BFFs must preserve this association during refresh. Never use a refresh token from tenant A to obtain an access token and apply it to tenant B solely because subject/email matches.

## 12. Public Clients, Confidential Clients, and Refresh Token Storage

### 12.1. Confidential Clients

A server-side BFF can hold a client secret or private key per its registration method. Refresh tokens are typically stored server-side and bound to the user session / authorized client.

Safeguards:

- Secret manager/KMS for client credentials.
- Encrypt refresh tokens at rest.
- Restrict read access to the token store.
- Never return refresh tokens to the browser when the BFF can manage them server-side.
- Redact tokens from logs, traces, and errors.
- Delete/revoke tokens on logout or grant revocation per policy.
- Protect backups, exports, and database administrator access.

### 12.2. Public Clients

SPAs and native mobile apps cannot keep a client secret as a server-side secret. When a public client receives a refresh token:

- The AS should enforce rotation or sender-constrained refresh tokens per security policy.
- The client must store tokens appropriately for its platform and threat model.
- Native apps should use OS-provided secure storage.
- SPAs should consider a BFF to keep long-lived refresh tokens out of the JavaScript runtime.
- If an SPA stores tokens in the browser, XSS can read script-accessible storage; HttpOnly cookies/BFF carry different trade-offs requiring CSRF and session security.

Never copy a client secret into a frontend bundle, mobile source, or build-time environment variable and call it a confidential client.

### 12.3. Avoid Storing Refresh Tokens in localStorage by Default

`localStorage` persists across sessions and is readable by any JavaScript on the origin. If an app has an XSS vulnerability, refresh tokens can be exfiltrated and replayed elsewhere, especially if not sender-constrained.

The BFF pattern typically keeps refresh tokens on the server while the browser holds only a protected session cookie. Still, BFFs require CSRF defenses, appropriate Secure/HttpOnly/SameSite cookie flags, session lifecycle management, and logout/revocation.

No single storage option fits every client; base the decision on platform, XSS/CSRF threat model, token lifetime, and sender-constraining support.

## 13. Sender-Constrained Refresh Tokens: DPoP and mTLS

Bearer refresh tokens can be replayed from another device if stolen. OAuth 2.0 Security BCP recommends protecting public-client refresh tokens with **rotation** or **sender-constraining**.

### 13.1. mTLS-Bound Tokens

With mutual TLS, the AS can bind tokens to the client's certificate. When refreshing, the client must prove possession of the matching private key/certificate. An attacker holding only the token string cannot use it without the key material.

mTLS fits workload/server environments capable of managing certificates and private keys.

### 13.2. DPoP

**Demonstrating Proof of Possession (DPoP)** uses a client-side key pair and a per-request proof JWT per protocol. Tokens are bound to the public key thumbprint. On token endpoint and resource requests, the client attaches a DPoP proof per DPoP rules.

DPoP mitigates replay of a stolen token string alone when an attacker lacks the private key. However:

- The client-side private key must still be protected.
- Proofs must carry valid method/URL/time/nonce claims per protocol.
- Both AS and Resource Server must support DPoP.
- Never just add a header named `DPoP` and consider it sender-constrained.
- DPoP does not replace scope, audience, issuer, or object authorization.

### 13.3. Sender Constraints Do Not Replace Refresh Token Rotation in Every Case

Rotation and sender-constraining are distinct safeguards. Depending on the threat model, an AS may apply one or combine both. Understand provider policy and test actual rotation/reuse behavior.

## 14. Spring Security Resource Server: Validating Access Tokens Only

### 14.1. JWT Resource Server

Configuration example:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
          audiences:
            - orders-api
```

WebFlux security chain:

```java
@Configuration
@EnableWebFluxSecurity
public class OrdersResourceServerConfiguration {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

The Resource Server verifies access tokens using a decoder. There is no `refreshToken()` here because the Resource Server does not manage refresh grants for inbound callers.

### 14.2. Opaque Token Resource Server

Configuration:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/oauth2/introspect
          client-id: ${ORDERS_INTROSPECTION_CLIENT_ID}
          client-secret: ${ORDERS_INTROSPECTION_CLIENT_SECRET}
```

WebFlux chain:

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults())
)
```

The Resource Server sends the **access token** to the introspection endpoint. The client credentials in YAML are **the Resource Server's credentials for calling AS introspection**, not the API caller's refresh token.

### 14.3. Do Not Add a Refresh Endpoint to a Resource Server Just to Fix 401s

A custom endpoint like:

```java
@PostMapping("/api/refresh")
public Mono<TokenResponse> refresh(@RequestBody RefreshRequest request) {
    // Anti-pattern if this is purely a Resource Server.
    return tokenEndpointClient.exchange(request.refreshToken());
}
```

turns the Orders API into an unintended token broker, exposes refresh tokens, and blurs client identity. If the application is a BFF responsible for managing authorized clients, use the OAuth2 Client subsystem with proper session/client binding and dedicated BFF endpoints. Never place generic refresh grants on business APIs.

## 15. When a Backend Is a BFF / OAuth2 Client: Spring Manages Outbound Refresh Tokens

There is one valid case: a Spring application both protects inbound web/API routes and calls downstream services on the user's behalf. In that role it acts as an OAuth2 Client.

Example:

```text
Browser
  |
  | session cookie
  v
BFF (OAuth2 Client)
  |
  | access token A1
  v
Orders downstream API (Resource Server)
  |
  | 401 invalid_token
  v
BFF / OAuth2AuthorizedClientManager
  |
  | refresh token R1 -> Authorization Server
  v
Authorization Server
  |
  | access token A2 (+ rotated refresh token R2)
  v
BFF
  |
  | retry downstream request with A2
  v
Orders downstream API
```

In this architecture, the BFF owns the authorized-client state created from OAuth login/authorization grants. Spring OAuth2 Client can manage the refresh flow for outbound requests.

**This is the BFF's own authorized-client refresh token**, not a refresh token sent by a caller to a Resource Server endpoint.

### 15.1. Dependencies

Example Spring WebFlux application:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
```

If the application also accepts inbound access tokens to protect APIs, add the Resource Server starter and configure both roles on separate routes/chains appropriately.

### 15.2. Client Registration

Example OAuth client configuration:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          orders-bff:
            provider: company-idp
            client-id: ${ORDERS_BFF_CLIENT_ID}
            client-secret: ${ORDERS_BFF_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - orders.read
              - offline_access
        provider:
          company-idp:
            issuer-uri: https://login.example.com
```

`offline_access` is a scope used by some OIDC providers to request refresh token issuance. Consent and actual refresh token issuance depend on OIDC/provider policy; declaring the scope alone does not guarantee the AS always returns a refresh token.

### 15.3. ReactiveOAuth2AuthorizedClientManager

Illustrative reactive configuration:

```java
package com.example.bff.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;

@Configuration
public class OAuth2ClientConfiguration {

    @Bean
    ReactiveOAuth2AuthorizedClientManager authorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ServerOAuth2AuthorizedClientRepository authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .build();

        DefaultReactiveOAuth2AuthorizedClientManager manager =
            new DefaultReactiveOAuth2AuthorizedClientManager(
                registrations,
                authorizedClients
            );

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

This manager must be invoked within the proper **server web request/session context** to load and persist the corresponding authorized client. For background services without a server request, use the appropriate manager/service variant such as `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` with its matching storage/identity context.

`refreshToken()` enables the provider to handle refreshes when an authorized client holds a refresh token and the access token needs authorization/renewal per provider rules. It **does not** make a Resource Server automatically refresh inbound tokens.

### 15.4. WebClient Using the Authorized Client Manager

Example WebClient filter function:

```java
package com.example.bff.client;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class DownstreamWebClientConfiguration {

    @Bean
    WebClient ordersWebClient(
            ReactiveOAuth2AuthorizedClientManager authorizedClientManager) {

        ServerOAuth2AuthorizedClientExchangeFilterFunction oauth =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                authorizedClientManager
            );

        oauth.setDefaultClientRegistrationId("orders-bff");

        return WebClient.builder()
            .filter(oauth)
            .baseUrl("https://orders.internal.example")
            .build();
    }
}
```

Exact configuration depends on how authorized clients are persisted and how principals/registration IDs attach to requests. Ensure outbound requests use the right user/session/client identity. Never use user A's authorized client for user B's request.

### 15.5. When Refresh Fails in OAuth2 Client

The BFF must handle:

- Expired or revoked refresh token: remove the authorized client and prompt the user to log in again.
- Client authentication error: fix registration/secret; do not blame the user.
- AS outage: surface dependency failure; do not fabricate access tokens.
- Successful rotation: persist the new refresh token per authorized-client persistence policy.
- Concurrent requests: coordinate so a rotated refresh token is not reused.
- Downstream 403: do not refresh by default; it usually indicates missing permissions.

Spring OAuth2 Client provides the provider/manager plumbing, yet **does not eliminate the need to govern storage, concurrency, failure handling, and session binding**.

## 16. Servlet OAuth2 Client Also Has an Authorized-Client Manager

In the Servlet stack, corresponding classes typically include:

- `OAuth2AuthorizedClientManager`.
- `DefaultOAuth2AuthorizedClientManager` for web request contexts.
- `AuthorizedClientServiceOAuth2AuthorizedClientManager` for service/background contexts.
- `OAuth2AuthorizedClientProviderBuilder` with `refreshToken()`.
- `OAuth2AuthorizedClientRepository` or `OAuth2AuthorizedClientService` to store authorized clients.

Provider configuration example:

```java
@Bean
OAuth2AuthorizedClientManager authorizedClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientRepository authorizedClients) {

    OAuth2AuthorizedClientProvider provider =
        OAuth2AuthorizedClientProviderBuilder.builder()
            .authorizationCode()
            .refreshToken()
            .build();

    DefaultOAuth2AuthorizedClientManager manager =
        new DefaultOAuth2AuthorizedClientManager(
            registrations,
            authorizedClients
        );

    manager.setAuthorizedClientProvider(provider);
    return manager;
}
```

When invoked to authorize an outbound client, the manager can use the stored refresh token to obtain a new access token. This is the backend's **OAuth2 Client responsibility**, separate from inbound Resource Server authentication.

## 17. How Do Applications Handle 401 and Refresh in Practice?

A client can follow conceptual logic:

```text
send API request with current access token

if response is success:
    return response

if response is 401 and request has a refreshable grant:
    refresh once using AS token endpoint
    atomically store new token pair
    retry request once with new access token
    if retry still fails:
        surface error; do not loop

if response is 403:
    surface authorization error; do not refresh by default

if response is 5xx/network:
    apply API retry policy; do not assume token expired
```

### 17.1. Pseudocode Example

```javascript
async function callOrdersApi(request, tokenStore, authClient) {
  const current = await tokenStore.load();

  const first = await sendRequest(request, current.accessToken);

  if (first.status !== 401) {
    return first;
  }

  // Single-flight lock must be implemented per session/grant.
  const updated = await authClient.refreshIfNeeded(current);

  if (!updated) {
    throw new Error("REAUTHENTICATION_REQUIRED");
  }

  // Retry only once; requests with side effects need an idempotency policy.
  const second = await sendRequest(request, updated.accessToken);

  if (second.status === 401) {
    throw new Error("NEW_ACCESS_TOKEN_REJECTED");
  }

  return second;
}
```

This is pseudocode, not production-ready token storage or locking. It illustrates how the **client** coordinates refreshes and caps retries. You must protect token storage, handle rotation, manage multi-tab/multi-instance concurrency, cancellation, and request idempotency.

### 17.2. Do Not Indiscriminately Refresh Every 401

A client should refresh only when evidence points to an appropriate access-token failure. If the server returned 401 due to wrong audience, unknown issuer, or malformed token, refreshing the same grant may return a token with the same failure. Distinguish misconfiguration from expiration/revocation.

### 17.3. Never Loop Retries

A buggy pattern:

```text
401 -> refresh -> retry -> 401 -> refresh -> retry -> ...
```

Enforce a hard limit: one refresh attempt per request/token generation, then surface the error to the application layer. If the new token is still rejected, investigate issuer/audience/clock/client configuration or session state.

## 18. Refresh Tokens and Multiple Tabs / Browser Requests

An SPA may open multiple tabs. One tab refreshes `R1` to `R2`, while another still holds `R1` in memory. When the second tab refreshes, the AS may detect reuse.

Design options:

- Use a BFF to manage refresh tokens server-side while the browser holds only a session cookie.
- Use a single-flight coordinator sharing refresh state across tabs if the SPA manages tokens directly.
- Use `BroadcastChannel` or a suitable coordination mechanism without sending raw refresh tokens into unsafe channels.
- Store tokens with generation/version metadata and atomic updates.
- When detecting a stale token generation, reload the new token pair instead of refreshing the old token.
- If reuse detection revokes the token family, transition to re-authentication with clear UI feedback.

Never let individual SPA components create independent refresh timers. A centralized auth client cuts down race conditions.

## 19. Refresh Tokens and Service-to-Service Calls

With `client_credentials`, a workload typically requests a new access token via client authentication whenever needed. Under OAuth 2.0, refresh tokens are normally not issued for the client credentials grant; the client simply requests a new access token using its client credentials when the old one expires.

Example:

```http
POST /oauth2/token HTTP/1.1
Authorization: Basic BASE64_SERVICE_CLIENT
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&
scope=orders.export
```

This is not a refresh token grant. The service identity authenticates directly to the AS with its service credentials, or via `private_key_jwt`/mTLS per registration. Do not mint long-lived refresh tokens when the grant/policy does not call for them.

### 19.1. Distinguishing Service Tokens from User-Delegated Tokens

| Case | What the token represents | How new tokens are obtained |
|---|---|---|
| Authorization Code user session | User grant/client | Refresh token if issued by AS and still valid |
| Client Credentials | Service client | Request a new access token using client authentication |
| Device Authorization | User grant/client | Refresh per policy if issued by AS |
| Token Exchange | Subject/actor token per grant | Perform token exchange per contract, not refresh grant |
| On-Behalf-Of / provider-specific | User/service delegation | Follow the provider's protocol and policy |

Never use a user's refresh token to obtain a broader service identity. Keep actor, subject, client, and delegation distinct.

## 20. OIDC and the `offline_access` Scope

In OpenID Connect, `offline_access` is a scope used in some scenarios to request offline access, typically tied to issuing a refresh token. Whether one is issued depends on:

- Whether the provider supports this scope.
- Client registration and grant type.
- Provider consent/prompt requirements.
- Login session and risk policies.
- Whether the client is permitted to hold refresh tokens.

Never assume simply adding:

```yaml
scope:
  - openid
  - offline_access
```

guarantees every OIDC Provider returns a refresh token. Clients must inspect the token response and handle cases where no refresh token is returned.

### 20.1. ID Tokens Are Not Access Tokens

An OIDC client may receive an ID token alongside an access token. The ID token proves the authentication event/claims to the client under OIDC; it is not a substitute for an access token when calling the Orders API.

Likewise, a refresh token is not an ID token and must never be sent to a Resource Server. The three tokens have distinct roles:

| Token | Primary consumer | Purpose |
|---|---|---|
| ID token | OIDC client | User authentication information |
| Access token | Resource Server | Accessing APIs |
| Refresh token | Authorization Server token endpoint | Obtaining new access tokens |

## 21. Revoking Refresh Tokens and Token Endpoint Revocation

RFC 7009 defines the OAuth 2.0 Token Revocation endpoint. Clients can submit tokens to the AS to request revocation per policy.

Example:

```http
POST /oauth2/revoke HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_CLIENT_CREDENTIALS

token=REFRESH_TOKEN_VALUE&
token_type_hint=refresh_token
```

`token_type_hint` is a hint to the AS, not proof. The AS may revoke related tokens per its implementation and policy.

### 21.1. What Must the Client Do on Logout?

- Clear local access/refresh token state.
- Call the revocation endpoint if flow/policy requires it and the client is authorized.
- End the application session.
- For OIDC, call the end-session/logout endpoint if configured and needed.
- Delete the BFF authorized-client record.
- Handle caches/sessions in downstream components per policy.

Deleting tokens from the browser **does not revoke them at the AS**. Conversely, revoking a refresh token **does not necessarily** invalidate already-issued access JWTs immediately on offline Resource Servers.

### 21.2. Does the Resource Server Call the Revocation Endpoint?

Normally **no**. The Resource Server validates inbound access tokens. It does not own refresh tokens and should not revoke a caller's grant merely because a request received 401 or 403.

If the Resource Server detects abuse, it can emit an audit/security event or trigger a dedicated administrative workflow. Grant revocation belongs to administrative/AS policy, not ad-hoc reactions inside request authentication filters.

## 22. Impact of Refresh Token Revocation on JWT and Opaque Access Tokens

### 22.1. JWT Access Tokens

JWTs can be verified offline with public keys. If the AS revokes a refresh token, previously issued JWT access tokens can remain valid until `exp` unless an additional state check exists.

Ways to shrink the risk window:

- Reasonably short access token lifetimes.
- Minimal audience and scopes.
- Proper key and issuer validation.
- Denylists or session/token-version lookups for early-revocation use cases.
- Token introspection instead of offline JWTs when centralized state is required, trading off latency/availability.

### 22.2. Opaque Access Tokens

Resource Servers typically introspect opaque tokens. The AS can return `active=false` after the access token or grant is revoked, depending on AS state and policy.

If the Resource Server caches introspection results, revocation can lag until the cache expires or is invalidated. Cache TTLs must balance latency, capacity, and acceptable revocation delay.

### 22.3. Never Use Refresh Tokens to Check Access Tokens

An architectural anti-pattern is having a Resource Server call the token endpoint with a caller-supplied refresh token when the JWT decoder rejects, just to "see if the session is still alive." That:

- Sends refresh credentials across the wrong service boundary.
- Can unintentionally mint new access tokens.
- Does not solve authenticating the original request.
- Breaks 401/403 semantics.
- Introduces replay and token leakage risks.

The Resource Server must strictly follow the **access-token validation/introspection contract**.

## 23. Protecting Refresh Tokens in Logs, Storage, and Transport

Refresh tokens are sensitive credentials. Protect them at every layer:

### 23.1. Transport

- Send to the token endpoint over HTTPS.
- Verify certificates and hostnames.
- Never pass refresh tokens in URLs/query strings.
- Never send them in business API requests.
- Never follow redirects to hosts outside trust policy on requests carrying tokens.
- Use registered client authentication.
- Never send tokens to issuers/endpoints taken from untrusted inputs.

### 23.2. Storage

- Server-side stores with access controls and encryption at rest.
- OS secure storage for native apps.
- BFF session binding and server-side token stores where appropriate.
- Minimize copies in memory, backups, crash dumps, and debugging tools.
- Delete/rotate old tokens along their lifecycle.
- Isolate tokens per user, client, and tenant.

### 23.3. Logs and Telemetry

Never log:

```text
refresh_token
access_token
Authorization: Bearer ...
Authorization: Basic ...
Cookie/session identifiers
raw token endpoint request/response
```

You can record non-sensitive metadata such as registration ID, grant outcome, error code, latency, rotation event ID, or suitably sanitized token family IDs. Avoid raw tokens or subject PII in metric labels.

### 23.4. Never Put Refresh Tokens in Frontend Errors

If the BFF encounters `invalid_grant`, the browser only needs to know the session must re-authenticate or the action cannot proceed. Never return refresh tokens, client secrets, raw AS error payloads, or introspection details to the frontend.

## 24. Testing the Refresh Token Lifecycle

Separate tests by role.

### 24.1. Resource Server Tests

Resource Server tests should prove:

- Missing access token on a protected endpoint → 401 Bearer.
- Expired access JWT → 401 `invalid_token`.
- JWT with wrong issuer/audience/signature → rejected.
- Opaque token `active=false` → 401.
- Valid access token missing scope → 403.
- Refresh token accidentally sent to API → rejected as an invalid access token.
- Resource Server **never calls the token endpoint** when an inbound access token expires.
- Resource Server never writes tokens to logs or responses.
- API does not issue out-of-contract HTML login redirects.

### 24.2. OAuth Client Tests

Client/BFF tests should prove:

- Expired access token triggers the refresh grant at most once per policy.
- Refresh request goes to the right AS token endpoint.
- Confidential client authentication is performed properly.
- Public clients do not send fake client secrets.
- Token responses are parsed accurately.
- New refresh tokens are persisted when the AS rotates.
- Old refresh tokens are never reused after successful rotation.
- `invalid_grant` transitions the client to appropriate re-authentication.
- `invalid_client` is classified as a configuration error.
- Timeouts with ambiguous outcomes are handled cautiously.
- Concurrent requests do not simultaneously reuse a rotating refresh token.
- 403 does not trigger a refresh loop.
- API retry happens at most once and respects idempotency.

### 24.3. Authorization Server Tests

AS tests should verify:

- Refresh tokens belong to the right client/grant.
- Expired or revoked tokens are rejected.
- Rotation issues a new token and invalidates the old one.
- Reuse detection enforces policy.
- Scopes/resources cannot be escalated illegitimately.
- Mandatory client authentication is enforced.
- Sender-constrained bindings are verified if enabled.
- Logout/revocation updates token families/grants.
- Token family revocation has well-defined blast radius.
- Audit events contain no raw credentials.

### 24.4. Comprehensive Test Matrix

| Scenario | Responsible component | Expected outcome |
|---|---|---|
| Valid access token `A1` | Resource Server | Permitted per scope/policy |
| Expired access token | Resource Server | 401 Bearer `invalid_token` |
| Client receives eligible 401 | OAuth client | May attempt one refresh |
| Valid refresh token `R1` | Authorization Server | Issues new access token |
| Rotation enabled | AS + client | `R1` replaced by `R2`; client persists `R2` |
| `R1` reused | AS | Reuse detection / revocation per policy |
| Expired refresh token | AS | `invalid_grant`; client needs new authorization |
| Wrong client secret | AS | `invalid_client`; fix client configuration |
| Refresh scope exceeds grant | AS | Does not grant out-of-scope permissions |
| New token lacks scope | API / client | Authorizes per new scope; may return 403 |
| Refresh timeout after AS processed | Client + AS policy | Never blindly retry `R1` |
| Two concurrent refresh requests | Client coordination | Single-flight / atomic update |
| Refresh token sent to Orders API | Resource Server | 401; never calls token endpoint |
| Revoke refresh token | AS | Stops issuing new access tokens from that grant |
| Already-issued JWT access token | Resource Server | Stays valid until `exp` without extra status checks |
| Revoked opaque access token | AS introspection + RS | `active=false` per policy |
| BFF logout | BFF + AS | Clears local state and revokes per contract |

## 25. Fake Authorization Server Testing Example

A client integration test can use a mock HTTP server simulating the token endpoint:

```text
POST /oauth2/token
  grant_type=refresh_token
  refresh_token=R1
  Authorization: Basic ...

Response:
  access_token=A2
  refresh_token=R2
  expires_in=600
```

Then verify:

1. Client sends the exact `grant_type`.
2. Refresh token `R1` goes in the form body, not the URL.
3. Client authentication uses the right method.
4. Token response includes `Cache-Control: no-store`/`Pragma: no-cache` per AS.
5. Client persists `A2/R2`.
6. Subsequent outbound requests use `A2`.
7. `R1` never appears in requests after rotation.
8. An `invalid_grant` error deletes/marks the authorized client as needing re-auth per policy.
9. Two concurrent requests trigger only one refresh operation for the same grant/token generation.
10. Tokens never appear in logs or assertion output.

For the Resource Server, the fake token endpoint can be configured to **count requests**. When sending an expired access token to the API, the test must prove the Resource Server makes zero calls to the refresh endpoint; only the configured access-token decoder/introspector runs.

## 26. Common Errors and Diagnostics

| Symptom | Possible cause | Resolution |
|---|---|---|
| API returns 401, client doesn't refresh | Client holds no refresh token or policy disallows refresh | Inspect grant/token response and client state |
| API receives refresh token and returns 401 | Caller sent the wrong token type | Fix client: send only access tokens to the API |
| Refresh returns `invalid_grant` | Expired, revoked, reused, or wrong client/grant | Inspect token family, rotation, and session |
| Refresh returns `invalid_client` | Wrong client secret or auth method | Check registration and secret rotation |
| Still 403 after refresh | New token lacks scope/permission | Check AS grant, scope response, and domain policy |
| Multiple requests unexpectedly log user out | Refresh rotation race / reuse detection | Single-flight and atomic token updates |
| Refresh timeout then all later attempts return `invalid_grant` | AS likely rotated before response dropped | Recovery policy; never blindly retry old token |
| After logout, JWT still calls API | Access JWT remains valid offline | Short TTL, introspection, or revocation strategy |
| BFF refreshes user A's token for user B's request | Wrong authorized-client/session binding | Bind token store strictly by principal/session |
| Resource Server calls token endpoint | Conflated OAuth client and Resource Server roles | Move refresh to client/BFF subsystem |
| Logs contain refresh token | Overly broad HTTP logging/debug capture | Redact and rotate/revoke exposed tokens |
| Multi-tab SPA refresh fails | Shared token state unsynchronized | BFF or cross-tab coordination |
| Token response lacks `refresh_token` | AS did not issue one per policy/consent | Handle missing refresh grant; never assume presence |
| Refresh grant does not change scopes | Client expected AS to grant extra permissions | New authorization/consent flow if broader scopes needed |

## 27. Anti-Patterns to Avoid

### 27.1. Sending Refresh Tokens in the API Authorization Header

Wrong because APIs expect access tokens scoped for the resource. Refresh tokens go solely to the AS token endpoint.

### 27.2. Letting the Resource Server Refresh Caller Access Tokens

Violates role boundaries and risks leaking refresh tokens, client credentials, or grants.

### 27.3. Refreshing on Every 401/403

Wrong because issuer/audience/signature errors or insufficient scopes cannot be fixed by refreshing.

### 27.4. Retrying Refresh Infinitely After Timeouts

Wrong because the AS may have already rotated and invalidated the old token even if the response was lost.

### 27.5. Retaining Old Refresh Tokens After Successful Rotation

Wrong because it can trigger reuse detection and revoke the token family.

### 27.6. Letting Every Request Refresh Independently

Wrong due to race conditions; use single-flight and atomic updates per grant/session.

### 27.7. Storing Refresh Tokens in Logs or localStorage by Default

Wrong because it increases credential theft and replay risk. Choose storage by client type and threat model.

### 27.8. Embedding Client Secrets in SPAs

Wrong because a secret in a frontend bundle is no longer secret.

### 27.9. Treating Logout as Automatic Token Revocation

Wrong; perform explicit token revocation and session termination per contract.

### 27.10. Assuming Refresh Token Revocation Immediately Invalidates JWT Access Tokens

Wrong if the Resource Server only verifies JWTs offline. A dedicated access-token revocation strategy is needed.

### 27.11. Using a User's Refresh Token as a Service Identity

Wrong because it conflates user delegation with workload identity/client credentials.

### 27.12. Accepting an ID Token as an Access Token on Refresh

Wrong because ID tokens, access tokens, and refresh tokens have distinct audiences and purposes.

## 28. Design and Operations Checklist

| Question | Requirement |
|---|---|
| Who sends access tokens to the Resource Server? | The OAuth client |
| Who sends refresh tokens? | The OAuth client to the AS token endpoint |
| Does the Resource Server refresh inbound tokens? | **No** |
| Does the AS verify client/grant/token state? | **Yes** |
| Are refresh tokens bound to client/grant/session? | **Yes** |
| Are expiry, idle timeout, and absolute lifetime defined? | Explicitly defined |
| Do public clients use rotation or sender constraints? | Per OAuth Security BCP |
| Does the client persist rotation responses atomically? | **Yes** |
| Is reuse detection enabled? | Per AS security policy |
| Is single-flight used for concurrent refreshes? | **Yes** |
| Is there a policy for ambiguous timeout outcomes? | **Yes, recovery policy defined** |
| Does 403 trigger a refresh by default? | **No** |
| Does logout revoke refresh tokens/grants? | Per explicit contract |
| Are JWT access tokens usable after refresh revocation? | Defined by TTL/status-check strategy |
| Do refresh tokens appear in logs, traces, or URLs? | **No** |
| Are BFF authorized clients strictly bound to user/session? | **Yes** |
| Do Resource Server tests prove the refresh endpoint isn't called? | **Yes** |
| Are token reuse, rotation, and race conditions tested? | **Yes** |

## 29. References

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): Section 6 Refreshing an Access Token, client authentication, refresh token grant, and scopes.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): protecting refresh tokens, rotation, sender-constrained tokens, and public clients.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): revocation endpoint and token revocation semantics.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): sending access tokens to Resource Servers and Bearer errors.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained tokens via proof-of-possession.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): mTLS and certificate-bound tokens.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): OIDC scopes, authorization code flow, and `offline_access`.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): authorized clients, client managers, and refresh-token providers.
- [Spring Security — Reactive OAuth2 Client](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html): `ReactiveOAuth2AuthorizedClientManager` and WebClient integration.
- [Spring Security — OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): validating inbound access tokens.
- [Spring Security — Reactive Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html): Bearer authentication in WebFlux.

**Conclusion:** Refresh tokens are the **OAuth client's credential toward the Authorization Server**. The client sends them to the token endpoint under the refresh grant; the AS verifies client/grant, checks expiry/revocation/reuse, and issues new access tokens per policy. **The Resource Server only validates access tokens** and returns 401/403 per the API contract; it never accepts callers' refresh tokens and never refreshes them itself. When a backend also acts as a BFF/OAuth client, Spring OAuth2 Client can manage refreshes for **the backend's own outbound authorized clients**, with controlled storage, session binding, rotation, and concurrency. Separating these three roles keeps the token lifecycle auditable, revocable, and operationally safe.
