# Introspection, Active Status, and Revocation Visibility Lag

In **Spring Security OAuth 2.0 / OIDC Resource Server**, the question "Has this Access Token been revoked?" is not simply a matter of checking a flag in a database. An Authorization Server may have already recorded a revocation request, yet a Resource Server temporarily continues accepting the token due to **introspection caching**, **state synchronization lag**, **multiple replicas**, or **requests that already passed authentication before the revocation occurred**.

For **opaque Access Tokens**, the Resource Server typically queries the Authorization Server via **OAuth 2.0 Token Introspection** per **RFC 7662**. In the response, the **`active`** field is a JSON boolean:

- **`active: true`**: The Authorization Server indicates that the token is active in the current introspection context. The Resource Server still needs to validate issuer, audience/resource, scope, and per-record permissions.
- **`active: false`**: The Resource Server **must not use the token to create a successful Authentication**. It cannot determine on its own whether the token expired, was revoked, never existed, or whether the introspecting caller is unauthorized to view the details.
- **No valid response received** due to timeout, TLS error, HTTP 5xx, or invalid schema: there is insufficient evidence that the token is active. **Fail closed**, never grant access by default.

The key point of the **Lifecycle and Revocation** chapter is **revocation visibility lag**: the time between when state is revoked at the source and when Resource Servers actually stop accepting new requests carrying that token. You cannot claim "revocation blocks immediately" if positive caching remains or Authorization Server consistency has not been established.

This lesson uses **Java 17+, Spring Boot 3.x, and Spring Security 6.x**, primarily with a **Servlet Resource Server** and an extension for **WebFlux**. We move from RFC 7009/RFC 7662, timelines, and sources of staleness to Spring Security configuration, caching, revocation SLAs, error handling, and practical testing. URLs and tokens in examples are illustrative values.

## 1. Three Lifecycles That Must Be Viewed Together

A system has at least three lifecycles:

1. **Token lifecycle at the Authorization Server (AS):** issuance, active state, expiration, revocation, or invalidation by grant/session/issuer policy.
2. **Authentication result lifecycle at the Resource Server (RS):** extracting Bearer token, introspecting, building principal/authorities, caching, TTL expiry, and re-introspecting.
3. **Request and business lifecycle:** security filter checking the token, endpoint checking scope, service checking owner/tenant, database transaction executing, and returning a response.

~~~text
Client                     Resource Server                  Authorization Server
  |                               |                                   |
  | Authorization: Bearer T       |                                   |
  |------------------------------>|                                   |
  |                               | POST /oauth2/introspect           |
  |                               |---------------------------------->|
  |                               |                                   |
  |                               | 200 {"active":true,...}           |
  |                               |<----------------------------------|
  |                               |                                   |
  |                               | Authentication + authorization    |
  | 200 OK                        |                                   |
  |<------------------------------|                                   |
  |                               |                                   |
  |     AS receives revoke(T) request and updates state               |
  |                               |                                   |
  | Authorization: Bearer T       |                                   |
  |------------------------------>|                                   |
  |                               | Cache hit or re-introspect?       |
  |                               |                                   |
  |                               | 200 {"active":false} if visible   |
  |                               |<----------------------------------|
  | 401 Unauthorized              |                                   |
  |<------------------------------|                                   |
~~~

The diagram shows the ideal path when the RS **already observes the new state**. If a stale active cache exists, the final request **may still temporarily pass authentication**.

### 1.1. An Active Token Does Not Automatically Mean Sufficient Permissions

Example introspection response:

~~~json
{
  "active": true,
  "sub": "person-42",
  "client_id": "orders-web",
  "scope": "orders.read",
  "aud": ["orders-api"]
}
~~~

This token does not by itself authorize:

- Calling `POST /api/orders` when the endpoint requires `orders.write`.
- Viewing another tenant's orders despite having `orders.read`.
- Using a token intended for `billing-api` at `orders-api`.
- Operating when the local account or tenant has been locked.

**Introspection returns credential state; authorization decides whether the request or resource may be accessed.**

## 2. RFC 7662: What Does Active Status Mean Precisely?

**RFC 7662 — OAuth 2.0 Token Introspection** allows an authorized party to query token state and related metadata.

### 2.1. Introspection Request over HTTPS

~~~http
POST /oauth2/introspect HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded
Accept: application/json
Authorization: Basic BASE64_OF_RESOURCE_SERVER_CREDENTIALS

token=OPAQUE_ACCESS_TOKEN_VALUE&token_type_hint=access_token
~~~

| Component | Meaning |
| --- | --- |
| Form parameter `token` | The token sent by the API client to the RS; it is a **Bearer secret**. |
| `token_type_hint` | Optional hint to help the AS locate the token; not proof that the token is active. |
| Authorization Basic | The **RS's credentials for calling the AS**, distinct from the user's Access Token. |
| Introspection URI | A trusted configured endpoint, never derived from unverified requests or tokens. |

Introspection requires **HTTPS**, TLS certificate/hostname verification, bounded timeouts, and credential protection. The AS may require mTLS or another client authentication method besides Basic; follow the contract. Never log form bodies containing Access Tokens or Basic headers.

### 2.2. HTTP 200 with active=true

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "active": true,
  "scope": "orders.read orders.write",
  "client_id": "orders-web",
  "token_type": "Bearer",
  "sub": "person-42",
  "iss": "https://identity.example.test/realms/demo",
  "aud": ["orders-api"],
  "iat": 1893452400,
  "nbf": 1893452400,
  "exp": 1893456000
}
~~~

`active: true` indicates the AS considers the token active **in the current introspection context**. Other fields depend on the token profile and AS contract:

- `scope`: granted scopes; in Spring Security typically mapped to authorities prefixed with `SCOPE_`.
- `sub`: subject, not automatically equivalent to a local user authorized across all tenants.
- `client_id`: OAuth client that received the token, not automatically a user ID.
- `aud`: intended resources for the token. If the API expects `orders-api`, validate audience when the contract provides this field.
- `iss`: issuer/token provider per contract; never implicitly trust a new issuer from a token.
- `exp`, `iat`, `nbf`: time metadata, normally NumericDate (Unix epoch seconds).

Do not assume every AS returns all fields beyond `active`. **If an API needs a field to check resource binding but the AS does not provide it, do not silently skip the validator**; align the contract or change the authentication model.

### 2.3. HTTP 200 with active=false

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"active":false}
~~~

A very common pitfall: **HTTP 200 from introspection only means the introspection request was processed**, not that the token is valid. When `active:false`, the RS must reject the credential.

RFC 7662 permits such a response when a token:

- Is expired or revoked.
- Does not exist or is unrecognized.
- Is not yet permitted under AS conditions.
- Is not authorized to be disclosed to the introspection caller.

Therefore, the RS **cannot infer the exact reason** from `active:false` alone. Never fabricate details about who revoked it, when, or who owned the token if the AS does not disclose them.

### 2.4. active Must Be a JSON Boolean

| JSON response | Valid type? | Handling |
| --- | --- | --- |
| `{"active":true}` | Yes | May proceed to validate metadata and permissions. |
| `{"active":false}` | Yes | Do not create a successful Authentication. |
| `{"active":"true"}` | No: string | Reject; treat as contract/protocol error. |
| `{"active":"false"}` | No: string | Do not coerce to boolean. |
| `{"active":1}` | No: number | Do not accept. |
| `{"active":null}` | No | Do not accept. |
| `{}` | No: missing required field | Do not accept. |
| Empty body/malformed JSON | No | Do not accept; log integration error. |

If parsing JSON manually, do not use:

~~~java
// DO NOT DO THIS: ambiguous casting.
boolean active = Boolean.parseBoolean(
    String.valueOf(response.get("active")));
~~~

**Prefer Spring Security's standard introspector**. If implementing a custom adapter, preserve semantics: only boolean `true` allows continuation, and mistyped responses must never create a principal.

### 2.5. AS HTTP 401/503 Is Not active=false

| Upstream response | Explanation | RS action |
| --- | --- | --- |
| 200 + `active:true` | Token active per AS. | Validate metadata/authorization. |
| 200 + `active:false` | Token not accepted. | Authentication fails, typically 401 at the API. |
| HTTP 401 from AS introspection | **The RS's own credentials** are invalid/unaccepted. | Do not conclude all user tokens expired; investigate client authentication. |
| HTTP 403 from AS | Permission to query introspection is restricted. | Fail closed and investigate policy. |
| HTTP 429/5xx | AS rate-limited/overloaded/outage. | Fail closed; bounded transient retries. |
| Timeout, DNS, TLS | No verification result available. | Fail closed; never assume token is active. |
| 200 with invalid `active` schema | Contract violation. | Reject and report protocol error. |

AS integration errors must have metrics and logs **separate from inactive tokens**. If all upstream failures are logged as "expired token," operations will miss misrotated client secrets or AS outages.

## 3. RFC 7009: A Revoke Request Does Not Mean Every API Rejects Immediately

**RFC 7009 — OAuth 2.0 Token Revocation** defines an endpoint for requesting token revocation. Example:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_OF_AUTHORIZED_CLIENT_CREDENTIALS

token=ACCESS_OR_REFRESH_TOKEN_VALUE&token_type_hint=access_token
~~~

| Endpoint | Purpose |
| --- | --- |
| **Revocation** | Ask the AS to revoke a token/grant according to granted permissions. |
| **Introspection** | Ask the AS whether a token is currently accepted. |

RFC 7009 designs revocation HTTP success to minimize leaking whether a token exists. A revocation request may receive **HTTP 200 even if the token does not exist or is already invalid**. Thus HTTP 200 from the revoke endpoint **is not proof that every RS has stopped accepting the token**.

### 3.1. Distinguishing Access Token, Refresh Token, and Session

- **Access Token**: credential the client sends to the RS to access resources.
- **Refresh Token**: credential the client uses with the AS to request new Access Tokens.
- **Authorization grant**: authorization relationship that may produce multiple tokens.
- **OIDC Login session**: login session at the OpenID Provider/Relying Party, with a separate lifecycle.

Revoking a Refresh Token **may** cascade to related Access Tokens or grants, depending on the AS and policy. **Never assume "revoking a refresh token" automatically blocks all issued Access Tokens immediately.** Logging out of an OIDC session likewise does not guarantee that all Access Tokens held by clients/RSs have been revoked by the AS.

### 3.2. Four Milestones of a Revocation

~~~text
R0: Client/Admin sends revoke request
    |
R1: AS returns HTTP success for revoke request
    |
R2: Revocation is committed to the source of truth
    |
R3: All introspection backends see active=false
    |
R4: All serving Resource Servers stop accepting new requests
~~~

In systems with asynchronous replication and caches, these milestones **do not necessarily coincide**. You must measure and explicitly define whether you are promising users **R1, R3, or R4**.

## 4. Revocation Visibility Timing Model

Define:

- **`t_request`**: when the revoke request is sent.
- **`t_commit`**: when the revocation state is committed by the AS.
- **`t_visible`**: when introspection across **all relevant backends** consistently returns inactive.
- **`t_cache_expiry(node)`**: when each RS node's positive result is no longer used.
- **`t_last_accept(node)`**: the last time a node accepted a new request with the revoked token.
- **`t_first_deny(node)`**: the first time that node is observed rejecting the token after revocation.

~~~text
AS commits revoke
       |
       |  L_visibility / replication delay
       v
Introspection sees inactive consistently
       |
       |  L_positive_cache / invalidation delay
       v
RS stops returning cached active=true
       |
       |  L_request_in_flight
       v
In-flight work handled by separate policy
~~~

Practical definition:

> **Revocation visibility lag for new requests** is the interval from when the AS commits the revocation until all Resource Servers serving traffic stop authenticating that token under policy.

**Requests that already passed authentication before revocation** are not covered by the same measurement unless the contract explicitly requires aborting in-flight work.

### 4.1. Conditional Estimation Formula

Assume:

1. The AS commits to a maximum **`L_AS`** from commit until all introspection nodes observe the revocation.
2. RS positive cache TTL is at most **`T_cache`**, with no stale-on-error beyond TTL.
3. Every new request passes through the proper authentication mechanism.
4. No gateway or other replica serves stale state longer.

A conservative estimate:

~~~text
L_new_requests ≲ L_AS + T_cache + margin_for_network_and_scheduling
~~~

This is **not an RFC guarantee** and is not a hard bound in every infrastructure. If AS replication is unbounded, a gateway caches for 10 minutes, or a node skips introspection, the formula is insufficient to predict revocation latency.

For in-flight requests, an independent **in-flight transaction/side-effect revalidation** policy is needed.

## 5. Timeline: Why Can a Request Still Get 200 After a 10:00 Revocation?

Suppose the AS reflects revocation in introspection after at most 300 ms; the RS caches active for 30 seconds; and the token's `exp` is 15 minutes away.

~~~text
09:59:59.900  RS introspects T -> active=true
              Cache positive result for T for 30s

10:00:00.000  AS commits revoke(T)
10:00:00.300  All introspection backends return active=false

10:00:05.000  Client uses T -> RS cache hit
              -> request may still be authenticated

10:00:29.901  Cache TTL expires; RS re-introspects
              -> active=false -> reject
~~~

**The crux:** the AS already knows the token is revoked, but the RS uses an `active:true` result verified **before revocation**.

A scenario can take longer than one cache TTL from revocation:

~~~text
10:00:00.000  AS commits revoke T
10:00:00.050  An AS introspection replica still returns active=true
10:00:00.051  RS just refreshed positive cache for 30s
10:00:00.300  AS finishes syncing; new introspection returns false
10:00:30.052  RS cache finally expires and starts rejecting
~~~

Therefore, you must consider **both AS visibility lag and positive cache refresh timing**. Never look at a single TTL setting and claim every revoked token is blocked within exact TTL seconds.

### 5.1. One Node Returning 401 Does Not Mean the Whole Cluster Returns 401

~~~text
RS Node A: rejects token T after 1s
RS Node B: continues accepting T for 18s more
RS Node C: rejects token T after 4s
~~~

A request through a load balancer hitting A and getting 401 **does not prove B/C have converged**. To measure cluster-wide SLA, probe every serving node/zone or collect reliable telemetry/acknowledgements of cache/decision state across all replicas.

## 6. Sources of Post-Revocation Lag

| Source | Symptom | Control approach |
| --- | --- | --- |
| AS replication lag | Introspection across AS nodes returns different statuses. | Unify datastore/consistency policy; measure `t_visible`. |
| Positive cache at RS | AS returns false but API still returns 200. | Short TTL, invalidation, proper cache keys. |
| Token cache at gateway | Spring never sees every request or gateway pre-accepted it. | Audit gateway auth/cache lifecycle. |
| Distributed cache | Multiple RSs share a stale cached principal. | Cluster-wide TTL/invalidation, namespace by issuer/resource. |
| Local JWT validation | API only checks signature/`exp`, never introspects. | Denylist/epoch/short-lived token/online check. |
| Existing web session | After OIDC logout, session cookie remains valid at RP. | Session invalidation/revalidation. |
| Streaming/WebSocket | Authenticated at start, not re-checked mid-session. | Periodic revalidation or event-driven disconnect. |
| Request already in transaction | Revocation happens after authentication. | Re-check state at domain boundary/commit if needed. |
| Local user/tenant status | AS active but internally locked. | Domain/account/tenant authorization gate. |
| Stale-on-error | AS outage; RS serves cached `active:true` past TTL. | Default fail closed; bounded approved exceptions only. |
| Non-cascading revocation | Refresh Token revoked while old Access Token stays active. | Verify AS semantics and test. |
| Clock skew | Incorrect TTL or `exp` comparison. | Synchronize/monitor clocks, safety margin. |

Optimizing one layer **is insufficient** if another layer still accepts stale tokens.

## 7. Writing Testable Revocation SLOs/SLAs

A requirement saying "tokens must be revoked immediately" is not quantifiable. A better criterion:

> "From the time the AS confirms **commit** of revocation, within at most N seconds, **all new requests beginning authentication** at all production Resource Servers serving traffic must reject that Access Token. In-flight requests are governed by a separate business policy."

The SLA document should define:

- **Start milestone:** user clicks Logout, revocation HTTP 200, or AS commit?
- **End milestone:** first introspection false, one API 401, or all serving nodes stopping acceptance?
- **Token types:** opaque Access Token, JWT, Refresh Token, token exchange, service credentials?
- **Scope:** single cluster/region, multi-region, gateway, API, session/websocket?
- **Failure conditions:** AS unavailable, node network partition, lost cache invalidation?
- **Percentiles and bounds:** p50/p95/p99, worst-case scenario, alert thresholds.
- **In-flight work:** must running transactions be aborted?

### 7.1. Risk-Based Policy

| Operation type | Illustrative policy |
| --- | --- |
| Low-sensitivity reads | May use short positive caching per revocation SLO. |
| User profile | Lower TTL, check local account/tenant status. |
| Payments and privilege management | Per-request introspection or stronger domain revocation gate, possibly no positive cache. |
| WebSocket/SSE | Revalidation during long sessions, or close stream on revoke event. |
| Background jobs | Check permissions/user/tenant at job execution time. |

There is no universal TTL mandated by RFC 7662 or Spring Security for every system; the number of seconds is a security and performance decision.

## 8. JWT and Opaque Tokens Reflect Revocation Differently

### 8.1. Opaque Token Introspection per Request

~~~text
Bearer opaque T
  -> RS
  -> POST introspection(T)
  -> active true/false
  -> Authentication or reject
~~~

Advantage: once the AS sees the revocation and there is no positive cache, the next request can receive the updated state. Disadvantage: depends on network and AS QPS/latency/availability on every authentication.

### 8.2. Opaque Token with Cache

~~~text
Bearer opaque T
  -> Result cache lookup
      hit: use previously verified active result
      miss: POST introspection(T)
~~~

Advantage: reduces QPS/latency. Disadvantage: **revocation stale window** caused by caching. Requires TTL bounded by `exp`, SLO, and invalidation.

### 8.3. Offline-Validated JWT

~~~text
Bearer JWT
  -> JWKS trusted public key
  -> Signature / issuer / audience / exp / nbf
  -> Authentication
~~~

If the RS only decodes the JWT, an AS revocation **does not automatically notify the JWT decoder** that a specific token became invalid before `exp`. If early revocation is required, you can design:

- Short-lived Access Tokens.
- `jti`/fingerprint denylist (with TTL).
- Minimum issuance epoch / token version per user/tenant.
- JWT introspection or online revocation check if supported by the AS.
- Disabling tenant/client/service principal at the domain gate.
- Sender-constrained tokens (mTLS/DPoP) to limit replay; **does not replace revocation**.

### 8.4. Introspection Is Not Strictly Limited to Opaque Format

RFC 7662 is a state-query protocol. An AS may allow introspecting a **JWT Access Token**. In Spring Security, the RS chooses the **JWT decode** or **opaque introspection** path via configuration; never let whether a token "contains dots" dynamically alter your trust policy.

| Validation method | Ability to detect early revocation |
| --- | --- |
| JWT local decode | Needs an extra mechanism to revoke before `exp`. |
| Uncached opaque introspection | Once the AS reflects revocation in introspection. |
| Cached opaque introspection | Once cache TTL expires/invalidates and AS reflects revocation. |
| JWT + online check | Shares the visibility, caching, and outage risks of online checks. |

## 9. Configuring a Spring Security Servlet Opaque Resource Server

### 9.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

### 9.2. application.yml

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: https://identity.example.test/oauth2/introspect
          client-id: orders-resource-server
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

`introspection-uri` must be a trusted configured HTTPS endpoint. `client-id` and `client-secret` are credentials **the Resource Server uses to call introspection**, not the user's token. Load the secret from environment/secret manager; never commit it to source code or logs.

### 9.3. SecurityFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http)
            throws Exception {
        http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/api/public/ping")
                    .permitAll()
                .requestMatchers(
                    HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(
                    HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth ->
                oauth.opaqueToken(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

In this chain:

1. Spring Security extracts the Bearer token from the request.
2. `OpaqueTokenIntrospector` calls the AS and checks `active`.
3. Inactive tokens cannot produce a successful `Authentication`.
4. Active tokens with valid metadata produce principal/authorities.
5. `authorizeHttpRequests` enforces endpoint scopes.
6. The domain service checks owner, tenant, account status, and business permissions.

`STATELESS` and disabling CSRF apply only to pure Bearer Authorization header APIs; **do not copy this verbatim for web OIDC Login using session cookies**. `securityMatcher("/api/**")` only secures paths in that chain; if the app has other routes, configure a separate fallback/chain.

### 9.4. Scope Is Distinct from Active Status

~~~json
{"active":true,"sub":"person-42","scope":"orders.read"}
~~~

When a caller sends:

~~~http
POST /api/orders HTTP/1.1
Authorization: Bearer VALID_READ_ONLY_TOKEN
~~~

the token may receive **403 insufficient_scope** because it lacks `orders.write` even though `active:true`. This does not mean the token was revoked.

## 10. Spring Security Components Involved in Introspection

~~~text
HTTP Authorization: Bearer T
                 |
                 v
BearerTokenAuthenticationFilter
                 |
                 v
BearerTokenAuthenticationToken
                 |
                 v
OpaqueTokenAuthenticationProvider
                 |
                 v
OpaqueTokenIntrospector.introspect(T)
                 |
                 +-- active=false -> authentication failure
                 |
                 +-- upstream/schema error
                 |      -> do not create successful Authentication
                 |
                 +-- active=true + valid metadata
                             |
                             v
                  OAuth2AuthenticatedPrincipal
                             |
                             v
                  BearerTokenAuthentication
                             |
                             v
                  AuthorizationFilter
                             |
                             v
                  Controller / Domain authorization
~~~

For opaque tokens, the principal is typically `OAuth2AuthenticatedPrincipal` and the `Authentication` is `BearerTokenAuthentication`, not necessarily `Jwt` or `JwtAuthenticationToken`. Do not coerce opaque principal data into a `Jwt` just because an internal issuer happens to store tokens as JWTs.

Spring Security does not guarantee an **introspection result cache with a fixed TTL across all versions/configurations**. If your application adds a caching decorator, proxy, or gateway token cache, that architecture largely dictates your revocation lag.

## 11. Positive Introspection Caching Requires a Safe TTL

For a token with a reliable `exp`:

~~~text
effectivePositiveTtl = min(
    approvedMaxTtl,
    exp - now - safetyMargin
)
~~~

If the calculated TTL is non-positive, **do not retain the positive result**. If the AS does not return `exp` and the system requires near-real-time revocation, the conservative choice is **not to cache completed active results**. You can still coalesce **in-flight** HTTP introspection calls for the same token to prevent thundering herds.

### 11.1. Trade-Off Examples

| Policy | Remaining token lifetime | Max positive TTL | Meaning |
| --- | --- | --- | --- |
| No positive cache | 15 minutes | 0 seconds | Query AS on every authentication; AS lag still applies. |
| Short cache | 15 minutes | 5 seconds | Accepts a short revocation stale window. |
| Short cache near `exp` | 2 seconds | 5 seconds | Never caches past expiration. |
| Long cache | 30 minutes | 10 minutes | Window where revoked tokens remain accepted can be huge. |
| Missing `exp` | Unknown | 0 under conservative policy | Avoids TTL without an expiration bound. |

These numbers are illustrative only. **RFC 7662 has no blanket rule that every Resource Server must cache for 5 or 60 seconds.** Organizations must choose based on revocation SLOs and AS load limits.

### 11.2. Never Cache by sub or Email

Two Access Tokens belonging to the same person:

~~~text
T1: sub=person-42, scope=orders.read, exp=10:10
T2: sub=person-42, scope=orders.write, exp=10:30
~~~

can be revoked independently. Caching by `sub` would cause token T1 to inadvertently inherit T2's metadata/permissions. **Cache keys must distinguish the specific token** and trust context (issuer/introspection client/resource) when needed.

Never use raw Access Tokens in logs, metrics, or URLs. One approach uses a **secret-keyed HMAC-SHA256 fingerprint** as the internal key, namespaced by issuer/resource:

~~~text
cacheKey = HMAC-SHA256(
    secret,
    trustedIssuerId + "\0" +
    resourceId + "\0" +
    rawAccessToken
)
~~~

The secret must be managed securely. An HMAC key does not purge raw tokens from the heap if the cache retains a closure capturing the token; enforce TTL/memory bounds and control heap dumps.

### 11.3. Positive, Negative, and Infrastructure Errors Are Three Distinct States

| Result | Cache policy |
| --- | --- |
| `active:true` | Cache briefly, TTL bounded by `exp` and revocation SLO. |
| `active:false` | May negative-cache very briefly if approved; limits junk-token DoS. |
| AS timeout/503/429 | **Never cache as inactive or active.** |
| Introspection client credentials HTTP 401 | Integration error; do not infer all user tokens are inactive. |
| Invalid JSON | Protocol error; do not create principal. |
| Active but wrong audience | Do not authorize current resource; do not reuse cached result for another API. |

Long negative caching can cause side effects if token state changes under AS policy (e.g., `nbf`). Most importantly: **never persist an AS outage error as a conclusion that a token is revoked**.

## 12. Java Example for Calculating Positive-Cache TTL

Example utility computing TTL from a principal **already verified by the standard introspector**:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;

public final class PositiveIntrospectionTtl {

    private final Clock clock;
    private final Duration maxTtl;
    private final Duration safetyMargin;

    public PositiveIntrospectionTtl(
            Clock clock,
            Duration maxTtl,
            Duration safetyMargin) {
        if (maxTtl.isNegative() || safetyMargin.isNegative()) {
            throw new IllegalArgumentException(
                "TTL and margin must be nonnegative");
        }
        this.clock = clock;
        this.maxTtl = maxTtl;
        this.safetyMargin = safetyMargin;
    }

    public Duration calculate(
            OAuth2AuthenticatedPrincipal principal) {
        Object raw = principal.getAttribute("exp");
        Instant expiresAt;

        if (raw instanceof Instant instant) {
            expiresAt = instant;
        } else if (raw instanceof Number seconds) {
            expiresAt = Instant.ofEpochSecond(
                seconds.longValue());
        } else {
            // No exp per contract: do not cache.
            return Duration.ZERO;
        }

        Duration remaining = Duration.between(
            clock.instant().plus(safetyMargin),
            expiresAt);

        if (remaining.isNegative() || remaining.isZero()) {
            return Duration.ZERO;
        }

        return remaining.compareTo(maxTtl) < 0
            ? remaining : maxTtl;
    }
}
~~~

Instantiation:

~~~java
PositiveIntrospectionTtl ttl =
    new PositiveIntrospectionTtl(
        Clock.systemUTC(),
        Duration.ofSeconds(5),
        Duration.ofSeconds(1));
~~~

**This is only a TTL calculation helper, not a complete cache.** When implementing a caching decorator, you still must handle bounded entries, concurrent cache misses, single-flight, invalidation, token secrecy, error policies, and expiry. Never apply this utility to unverified caller-supplied claims.

Some introspection adapters represent `exp` as an `Instant`, while others may return a `Number`. Rely on the actual contract; never turn arbitrary strings into expirations via ambiguous casting. Clock synchronization and safety margins are necessary, but never add clock skew in a way that extends permissions past token expiration.

## 13. Invalidation and Single-Flight Can Improve Latency

### 13.1. Push Invalidation After Revocation

If the AS emits a reliable **revocation event**:

~~~text
AS commits revoke(T)
      |
      v
Authenticated revocation event
      |
      v
Resource Server nodes invalidate cache(T)
      |
      v
Next request introspects T -> active=false
~~~

An event system requires:

- Authenticating the event source; never trust unauthenticated public payloads.
- Handling duplicate, late, lost, or out-of-order events.
- Invalidation reaching **all serving replicas/gateways**.
- Cache keys built on controlled token fingerprints/namespaces.
- Observing AS visibility: if the event arrives **before** introspection backends converge, a fresh introspection call might still return `active:true`.
- When the revocation event is authoritative, a temporary **deny tombstone** may be needed to avoid re-caching `active:true` from an AS replica that has not yet seen the revocation.

Simply broadcasting "evict key" does not guarantee instant revocation if an AS backend still reports active.

### 13.2. Single-Flight for Concurrent Callers with the Same Token

~~~text
50 requests with same token T, simultaneous cache miss
          |
          v
One in-flight introspection(T) per instance
          |
          v
50 callers receive the shared result or error
~~~

Single-flight lowers QPS and prevents cache stampedes. However, it **does not change token state** or TTL requirements:

- Coalescing may be per-JVM rather than cluster-wide.
- The shared task needs timeout and concurrency bounds.
- An AS 503 error must never turn into a default principal.
- After completion, any positive cache must still expire per revocation policy.
- Never cache request A's `SecurityContext` to reuse for request B.

In WebFlux, you can use a shared `Mono` keyed by token with a TTL policy; in Servlet, use an appropriate registry/cache/future. **Never call `subscribe`/`block` on the event loop** trying to force a synchronous result.

## 14. AS Outages Must Fail Closed

~~~text
Client -> Resource Server: Bearer T
Resource Server -> AS: introspect(T)
AS: timeout / HTTP 503

Resource Server has no fresh result proving T is active.
Resource Server must not fabricate an arbitrary authenticated principal.
~~~

Dangerous example:

~~~java
// DO NOT DO THIS.
try {
    return introspector.introspect(token);
} catch (Exception failure) {
    return privilegedDefaultPrincipal();
}
~~~

Instead:

1. Configure connect/read/total timeouts.
2. Retry only classified **transient errors**, with backoff and a total time budget.
3. Never endlessly retry `active:false` or HTTP 401 caused by a wrong RS client secret.
4. Bound concurrency when calling the AS, applying rate limits and circuit breakers/bulkheads where appropriate.
5. When verification fails, **never let the request pass as authenticated**.
6. Emit `introspection_unavailable` metrics separately from `token_inactive`.
7. API HTTP responses may map to 5xx/503 service errors per contract, though do not assume every Spring version maps all introspection failures to the exact same status code by default.

### 14.1. Stale-on-Error Requires an Explicitly Approved Policy

If an active cache entry expires during an AS outage, **continuing to serve `active:true` indefinitely** is a time-based fail-open. It prevents revocation from meeting the SLO.

An organization may opt for bounded stale validation on low-sensitivity endpoints for availability, but this requires **risk sign-off, an absolute maximum age, metrics, auditing, and a recovery playbook**. For sensitive APIs, rejecting tokens when the AS cannot verify them is usually the safer decision.

### 14.2. Wrong Introspection Credentials Differ from Revoked User Tokens

If an RS's secret or mTLS certificate expires, the AS may return HTTP 401 for all introspection calls. That **does not prove all user tokens are inactive**. Properly classify upstream client authentication errors and investigate secret rotation, TLS trust, or configuration.

## 15. Multiple Cache Layers and Multiple Resource Server Replicas

~~~text
Client
  |
  v
API Gateway (may cache token validation)
  |
  v
Load Balancer
  |
  +-- RS A (local cache T has 1s left)
  +-- RS B (local cache T has 20s left)
  +-- RS C (no positive cache)
  |
  v
Authorization Server cluster
  +-- introspection node 1
  +-- introspection node 2
  +-- revocation datastore
~~~

A revoked token T may be handled differently across nodes:

- RS A is about to re-introspect.
- RS B still holds an active cache entry.
- RS C hits AS replication lag.
- The gateway may accept the token before the request even reaches Spring.

**Cluster-wide lag depends on the slowest node still serving traffic**, not the first node to return 401.

### 15.1. Local Cache vs. Distributed Cache

| Design | Advantage | Risk |
| --- | --- | --- |
| Local in-memory cache | Fast lookup, no added cache network dependency. | Each node has independent TTL/invalidation. |
| Redis/distributed cache | Shared results, potentially higher hit rate. | Stale metadata spreads widely; needs ACLs, TTL, namespacing, invalidation. |
| No positive cache | No staleness from RS result cache. | Increases AS load/latency/availability dependency. |
| Push revocation invalidation | Can block earlier than TTL. | Event authenticity, ordering, delivery, and AS visibility. |
| Centralized status gate | Can improve consistency. | Adds network dependency; must fail closed. |

Do not forget that **gateways or service meshes** can also authenticate/cache upstream of the RS. Tuning TTL in Spring will not fix a gateway holding a longer active cache.

### 15.2. Cache Trust Namespace

An introspection result must be interpreted within its context:

~~~text
trusted issuer / introspection endpoint
Resource Server client identity
expected audience/resource
token identity
~~~

The AS may return `active:false` when a caller is unauthorized to introspect a token, even if the token is valid at another resource. Never reuse an active result from `orders-api` to authorize `billing-api` solely because the raw token string matches.

## 16. Requests Authenticated Before Revocation Do Not Automatically Roll Back

Example:

~~~text
10:00:00.000  POST /api/transfers starts
10:00:00.020  introspect T -> active=true
10:00:00.050  Scope/tenant checks pass
10:00:00.100  Domain service opens transaction
10:00:00.200  AS revokes T
10:00:00.300  New introspection returns active=false
10:00:01.000  Initial transaction commits
~~~

Revocation can block **new requests**, but does not automatically convert an Authentication established at T+0.020s into a transaction rollback. Depending on the business domain, design:

- Local user/tenant/token revocation epoch checks near write/commit points.
- Appropriate transaction consistency and isolation.
- Idempotency keys for operations with side effects.
- Auditing and status-query endpoints after client timeouts.
- Mechanisms to terminate WebSockets/SSE or background jobs if required.
- Saga/outbox/compensation patterns for operations outside the database transaction.

**Client disconnect is also not revocation.** Closing a browser tab or aborting `fetch` does not automatically send an OAuth revocation request to the AS, nor prove that remote side effects rolled back.

### 16.1. exp Expiring Mid-Processing

JWT/opaque tokens are typically checked for expiration during request authentication. If `exp` arrives while a long-running operation is executing, that operation **does not necessarily stop automatically**. For long-running tasks, define reauthorization policies at sensitive steps.

## 17. Logout, Account Disablement, and Tenant Suspension Differ from Token Revocation

Suppose:

~~~text
Introspection of T: active=true
Local account: SUSPENDED
Tenant membership: REMOVED
~~~

The API **must still reject under domain authorization**, without waiting for the AS to flip `active`. Conversely, logging out on the frontend does not automatically update AS revocation state unless the corresponding workflow runs.

| Event | Change | Watch out for |
| --- | --- | --- |
| Access Token revoked | Specific token no longer accepted by AS. | RS must observe new state via introspection/online gate. |
| Refresh Token revoked | Client can no longer use that Refresh Token. | Old ATs may remain active per AS policy. |
| OIDC logout | OP/RP session ends per logout mechanism. | Do not assume all ATs across all RSs are revoked. |
| Local user disabled | Account disallowed by internal system. | Domain gate must block even if AT is still active. |
| Tenant suspended/revoked | Tenant access halted in SaaS. | Per-request tenant gate/cache invalidation and cluster consistency. |

If an application uses both an **OIDC Login session cookie** and a **Bearer Resource Server API**, test logout/session invalidation and revocation separately; never use a single frontend flag to represent the entire credential lifecycle.

## 18. HTTP 401, 403, and Introspection Errors

### 18.1. Inactive Token

A response following Bearer semantics might look like:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
~~~

This is an **authentication** error; exact Spring Security headers/bodies may vary by exception handler and version.

### 18.2. Active Token Missing Scope

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders.write"
~~~

This is an **authorization** error, not a sign of token revocation. Refreshing an Access Token under the same grant will not automatically add new scopes.

### 18.3. Introspection Outage

~~~text
AS -> RS: HTTP 503, timeout, or TLS failure
RS: unable to verify token
~~~

The RS must **fail closed**. It may return 5xx/503 per API contract when the authentication dependency is unavailable, though do not assume every introspection failure maps to the same HTTP status by default across all Spring versions.

### 18.4. Do Not Leak Internal Causes

Never return raw tokens, `sub`, email, revoking actor, private keys, client secrets, upstream stack traces, or JWKS details to unauthenticated callers. Error bodies should be concise, with technical details recorded in access-controlled audit logs.

## 19. Testing the Transition from Active to Revoked

A test that only stubs:

~~~text
Introspection -> {"active":false}
API -> 401
~~~

is necessary, yet **does not prove revocation lag**. You must test **state transitions, cache TTLs, AS propagation, and multiple nodes**.

### 19.1. Test Matrix

| Test | Expected verification |
| --- | --- |
| T active, sufficient scope | API passes auth and HTTP rules. |
| T active=false from the start | API 401; controller does not execute. |
| T active then revoked | API rejects within the committed latency window. |
| Positive cache warmed | Cache hit before TTL; re-introspects after TTL. |
| Revoke right before cache refresh | Bound includes both AS visibility + TTL. |
| AS returns string `active:"false"` | Does not create principal. |
| AS introspection HTTP 401 | Resource Server credential error; do not treat all tokens as revoked. |
| AS timeout/503 | Fail closed; do not fall back to default principal. |
| T active missing write scope | 403, not confused with inactive. |
| T active but local account locked | Domain policy rejects. |
| Refresh Token revoked | Verify Access Token cascade per actual AS behavior. |
| JWT local decode, AS revokes T | Do not promise automatic detection without online checks. |
| Gateway holds cached active | Inspect TTL outside Spring. |
| Multiple RS replicas | Every serving node meets revocation deadline. |
| Request passes auth then revoked | Outcome follows in-flight/transaction policy. |

## 20. Example Fake OpaqueTokenIntrospector for Testing HTTP Transitions

A fake test introspector helps verify that Spring Security **receives an inactive result and rejects the token** inside the local application:

~~~java
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

public final class SwitchableTestIntrospector
        implements OpaqueTokenIntrospector {

    private final AtomicBoolean active = new AtomicBoolean(true);

    public void setActive(boolean value) {
        active.set(value);
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        if (!"test-access-token".equals(token)
                || !active.get()) {
            throw new BadOpaqueTokenException(
                "Token is inactive in this test");
        }

        return new DefaultOAuth2AuthenticatedPrincipal(
            "person-42",
            Map.of("sub", "person-42", "scope", "orders.read"),
            List.of(new SimpleGrantedAuthority(
                "SCOPE_orders.read")));
    }
}
~~~

Register the fake as an `OpaqueTokenIntrospector` bean **only in the test context**, keeping the defined API security filter chain. Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Import(RevocationTransitionTest.FakeConfig.class)
class RevocationTransitionTest {

    @Autowired MockMvc mvc;
    @Autowired SwitchableTestIntrospector fake;

    @TestConfiguration
    static class FakeConfig {
        @Bean
        SwitchableTestIntrospector fakeIntrospector() {
            return new SwitchableTestIntrospector();
        }
    }

    @Test
    void tokenFailsAfterStateChanges() throws Exception {
        fake.setActive(true);

        mvc.perform(get("/api/orders/42")
                .header(HttpHeaders.AUTHORIZATION,
                    "Bearer test-access-token"))
            .andExpect(status().isOk());

        fake.setActive(false);

        mvc.perform(get("/api/orders/42")
                .header(HttpHeaders.AUTHORIZATION,
                    "Bearer test-access-token"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

**Prerequisites for running the example:** the test application context has a controller for `GET /api/orders/42` returning 200, uses a security chain accepting opaque tokens, and has **no other introspector bean causing ambiguity**. Never deploy this fake to production.

**Limitations:** the fake only simulates an **in-process** active flag; it does not send HTTP introspection requests, does not test cache/AS replication, and does not measure real revocation latency.

## 21. Integration Testing via an HTTP Introspection Server

For real testing, spin up **WireMock/MockWebServer** or an HTTP test server simulating the Authorization Server:

~~~text
POST /oauth2/introspect, token=reader
  -> HTTP 200
     {"active":true,"scope":"orders.read",
      "sub":"person-42","aud":["orders-api"],"exp":...}

POST /oauth2/introspect, token=revoked
  -> HTTP 200 {"active":false}

POST /oauth2/introspect, token=bad-schema
  -> HTTP 200 {"active":"true"}

POST /oauth2/introspect, token=down
  -> HTTP 503 Service Unavailable
~~~

### 21.1. Transition Scenario

1. Set up an AS fixture with mutable token state.
2. Configure the Resource Server to use the fixture's real HTTP introspection endpoint.
3. Have token T return `active:true` with a distant `exp` and appropriate scope.
4. Send `Bearer T` through Spring Security filters, **without using the `opaqueToken()` helper**.
5. Verify the API passes authentication, the fixture receives the POST, and any cache is warmed.
6. At `t_commit`, switch the fixture to `active:false`.
7. Keep sending `Bearer T` periodically; record HTTP statuses and timestamps per node.
8. Verify that after TTL/invalidation, the API returns 401 and the controller does not run.
9. Repeat with delayed AS visibility, 503s, timeouts, and multiple replicas.

**Worst-case timing test:** an AS replica still returns `active=true` just before revocation converges, and the RS refreshes its cache right then. This scenario can create a delay close to **AS visibility lag + one full cache TTL**.

### 21.2. MockMvc opaqueToken() Does Not Call Introspection

~~~java
mockMvc.perform(get("/api/orders/42")
        .with(opaqueToken().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

`spring-security-test`'s `opaqueToken()` creates an already-authenticated test `Authentication`. It is suitable for testing HTTP authorization, but **does not prove `active:false`, cache TTL, or revocation propagation**. To measure revocation, send a raw Bearer token through a real/test introspection server.

## 22. Measuring Revocation Latency Over Time

A measurement test should record:

~~~text
experiment_id
token_fingerprint (internal, not raw token)
issuer/resource/token_type
time_revoke_requested
time_revoke_committed_at_AS (if observable)
time_introspection_first_false
time_last_accepted_request_per_node
time_first_denied_request_per_node
cache_hit/miss, TTL, node, region, gateway
error_category
~~~

### 22.1. Illustrative Probe Schedule

~~~text
T-2s  Issue test Access Token T; exp > test window
T-1s  Warm Resource Server cache
T0    Commit revoke(T) at test AS
T+.1s Probe every RS node with Bearer T
T+.5s Probe every RS node with Bearer T
T+1s  Probe every RS node with Bearer T
T+2s  Probe every RS node with Bearer T
T+5s  Probe every RS node with Bearer T
T+6s  Probe every RS node with Bearer T
T+10s Probe every RS node with Bearer T
~~~

When probing periodically, **the actual transition time lies between the last accept and the first deny**. The value `t_first_deny - t_commit` is an **observed upper bound** under the test schedule, not the exact timestamp. Document the sampling interval, clock synchronization, and network/processing delays.

Probing through a load balancer cannot validate individual replicas unless you know which node actually handled each request.

### 22.2. Essential Metrics

~~~text
introspection_requests_total{outcome=active|inactive|error}
introspection_latency_seconds
introspection_upstream_errors_total{category=...}
introspection_cache_hit_total
introspection_cache_miss_total
introspection_cache_entries
authentication_failures_total{category=...}
authorization_denied_total{category=...}
revocation_visibility_lag_seconds
revocation_effective_denial_lag_seconds
~~~

Never put raw tokens, HMAC fingerprints, emails, `sub`, or full claims into metric labels; they are sensitive and high-cardinality. Use request IDs, configured issuers, and error categories as appropriate for data security.

## 23. Runbook When a Revoked Token Still Calls the API

1. **Identify the exact token/issuer/resource** using safe internal identifiers; never share raw credentials.
2. **Verify the revocation workflow:** was an Access Token or Refresh Token revoked? When did the AS commit? Does revocation cascade?
3. **Query introspection with authorized credentials** from a safe RS/test context to confirm what `active` state the AS currently returns.
4. If the AS still returns `active:true`, investigate AS datastore replication, whether the wrong token was revoked, or grant policies.
5. If the AS already returns `active:false` yet the API succeeds, investigate **positive caches, gateways, security chains**, and specific replicas.
6. Determine whether the request passed authentication **before or after** revocation.
7. Check local account/tenant status and domain authorization.
8. Verify whether an AS upstream outage was turned into a fail-open.
9. Record timestamps, TTLs, last accepted request, and first denied request per node.
10. Feed the root cause back into your SLO/test suite and adjust cache/invalidation policies.

### 23.1. Troubleshooting Table

| Symptom | Priority question |
| --- | --- |
| Revoke endpoint 200 but introspection active=true | Was the right token revoked? What are AS replication/cascade policies? |
| Introspection active=false but API 200 | Does positive cache at RS/gateway still have TTL? Which security chain handled the request? |
| Only some requests return 200 after revocation | Are multiple replicas/regions holding different caches? |
| JWT still works after AS revocation | Does the API have an online revocation check or only local decode? |
| Token still active after logout | Was token revocation called, or only session/frontend state cleared? |
| Account disabled but token active | Is there a local/domain account gate? |
| API returns 403 after revocation | Is it missing scope/domain permission rather than inactive status? |
| All tokens fail with 401 simultaneously | Is there an RS introspection credential issue or AS outage? |
| API hangs when AS is slow | Are connect/read timeouts, retry budgets, and bounded concurrency configured? |
| Active cache persists past `exp` | Miscomputed NumericDate TTL, clock skew, or stale-on-error? |
| Freshly revoked but active nearly 1 TTL later | Did AS visibility lag let the cache refresh just before AS converged? |

## 24. Mistakes to Avoid

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Treating introspection HTTP 200 as valid token. | 200 can still carry `active:false`. | Check the boolean `active` field. |
| Assuming `active:false` always means expired. | Masks revocation/unknown/not permitted. | Do not infer causes beyond what the AS returns. |
| Assuming revoke HTTP 200 means all RSs updated. | Caches/replicas may not have converged. | Measure effective denial end-to-end. |
| Caching `active:true` until a multi-hour `exp`. | Revoked tokens retain access for too long. | Cap TTL by revocation SLO, not just `exp`. |
| Caching by user `sub` instead of token. | Mixes scopes/revocation across distinct tokens. | Key by token identity and trust namespace. |
| Caching 503 as inactive. | Conflates outages with token state, poor recovery. | Separate infrastructure errors from token state. |
| Accepting tokens when AS times out. | Fail-open authentication. | Fail closed; handle service errors properly. |
| Testing only one node. | Other nodes still accept. | Probe all serving replicas/regions. |
| Using only MockMvc `opaqueToken()` to test revocation. | Bypasses HTTP introspection. | Test with an HTTP server transitioning `active`. |
| Forgetting the gateway has its own token cache. | Backend TTL does not govern the whole system. | Audit all authentication layers. |
| Revoking Refresh Token and assuming old AT is invalid. | Cascade varies by AS. | Test actual token lifecycle behavior. |
| Equating OIDC Logout with revoking all ATs. | Login sessions and ATs have distinct lifecycles. | Design session/logout/token revocation separately. |
| Expecting local JWT decoders to detect revocation. | JWT still has valid signature and `exp`. | Use denylist/epoch/online check when needed. |
| Reducing cache TTL without measuring AS visibility. | Upstream lag remains. | Measure `t_visible` and `t_cache_expiry`. |
| Letting an active token read every tenant. | BOLA/cross-tenant leak. | Enforce tenant/owner/domain authorization. |
| Treating client disconnect as token revocation. | Transport state does not alter credential state. | Perform revocation at the AS via the proper flow. |
| Logging tokens for debugging. | Leaks Bearer secrets. | Use error categories, request IDs, and safe auditing. |

## 25. Project Implementation Roadmap

1. **Align the token contract:** Access/Refresh/ID Tokens, issuer, audience, scope, `exp`, revocation, and logout semantics.
2. **Design introspection:** trusted HTTPS URI, Resource Server client authentication, JSON boolean `active`, and required metadata.
3. **Define AS state milestones:** revocation commit and latency until all introspection backends return inactive.
4. **Set measurable revocation SLOs:** start/end milestones, cluster-wide scope, token types, and in-flight request handling.
5. **Configure Spring Security:** standard `OpaqueTokenIntrospector` and Bearer security chain; authentication does not replace authorization.
6. **Bound caching:** short positive TTL never exceeding `exp`, intentional negative caching, never cache outages as state.
7. **Control dependencies:** timeouts, bounded transient retries, and single-flight/rate limits/bulkheads under high load.
8. **Design invalidation:** event authenticity, ordering, and delivery to all RS/gateway replicas when SLA requires it.
9. **Evaluate JWT/web session paths:** offline JWTs, OIDC sessions, tenant disablement, and streams need dedicated policies.
10. **Test transitions and worst cases:** active → revoke → AS false → cache expiry → API deny; include 503s and multiple replicas.
11. **Measure and monitor:** cache hit/miss, introspection errors, last accept, first deny, revocation lag.
12. **Prepare emergency response:** disable user/tenant, invalidate caches/sessions, drain stale nodes, and audit transactions.

**Remember:** `active:false` means **the Resource Server must reject the token at introspection time**, but **AS committing a revocation does not mean all Resource Servers know immediately**. The lag between the two comes from **AS visibility, positive-cache TTL, multiple gateway/replica layers, and in-flight requests**. In Spring Security, maintain the boundary **introspection → Authentication → scope/domain authorization**, **fail closed** when a token cannot be verified, and turn revocation latency into **a measurable, testable, and monitored SLO** rather than an unbacked promise.

## References

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662).
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009).
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750).
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519).
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068).
- [Spring Security — Servlet Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html).
- [Spring Security — OpaqueTokenIntrospector API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenIntrospector.html).
- [Spring Security — OAuth 2.0 Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html).
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [Spring Security — Reactive Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html).
- [Spring Security — Testing OAuth 2.0 with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html).
- [OpenID Connect Back-Channel Logout](https://openid.net/specs/openid-connect-backchannel-1_0.html).
- [OWASP — API Security Top 10 (2023)](https://owasp.org/API-Security/editions/2023/en/0x00-header/).
