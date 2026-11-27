# Immediate Revocation Limits for JWTs Verified Locally by Resource Servers

## 1. Core Problem: A Cryptographically Valid JWT May Still Be Unrevoked Locally

In an **OAuth 2.0/OpenID Connect Authorization Server** system built with **Spring Security, Spring Authorization Server, and Spring Boot**, the Authorization Server (AS) can issue signed **JWT access tokens**. A Resource Server (RS) only needs to fetch public keys from JWKS and verify the signature and claims such as `iss`, `aud`, `exp`, `nbf`, and `scope` to allow or reject a request.

This **local (offline) validation** approach has benefits: fewer requests to the AS, lower latency, and easy horizontal scaling across many APIs. However, when the AS revokes an access token via the Revocation Endpoint or an administrator locks an account, the already-issued JWT **does not change its payload or signature**, and an offline Resource Server **does not automatically learn** that new state.

Example:

- 09:00: AS issues a JWT access token with `exp` at 09:15.
- 09:03: the user logs out and the client calls `POST /oauth2/revoke` to revoke the token.
- 09:07: someone holding a copy of the old JWT sends a request to the RS, which only validates signature, `iss`, `aud`, and `exp`.
- Without an additional revocation-state check layer, the RS **can still accept the JWT** until the token expires, subject to clock skew and other authorization checks.

This is **not a bug in JWT signatures**. A signature proves the token was not tampered with and was signed by a valid key; it carries no dynamic information about post-issuance revocation decisions at the AS.

In the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, the goal is to learn how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server with Spring Security and Spring Authorization Server in a Spring Boot application. This lesson belongs to the **Revocation** chapter and focuses on **the limits of immediate revocation when Resource Servers validate JWTs locally** and how to choose policies matching your security requirements.

### Learning Outcomes

After this lesson, you will be able to:

1. Distinguish **token revocation at the AS**, **offline JWT validation at the RS**, **token introspection**, and **logout/session invalidation**.
2. Explain why HTTP 200 from the Revocation Endpoint **does not mean** every RS immediately blocked the JWT.
3. Evaluate the limits of short access token TTLs, `jti`-based denylists, introspection, authorization versions, and push-event invalidation.
4. Design hybrid models that keep JWT signature validation while checking revocation state at APIs when necessary.
5. Configure Spring Security 6.x and Spring Authorization Server 1.5.x samples without disabling signature, issuer, audience, or expiration checks.
6. Define target revocation latency, observe propagation/cache delays, and write tests across multiple RS instances.

**Example Scope:** Spring Boot 3.x, Spring Security 6.x, and Spring Authorization Server 1.5.x on the Servlet stack. Newer versions may differ in APIs; before bringing sample code into production, verify against your actual dependencies, APIs, and security policies.

## 2. Two Different Sources of Truth

### 2.1. A JWT Is a Snapshot of Permissions at Issuance Time

A JWT access token may contain:

```json
{
  "iss": "https://auth.example.com",
  "sub": "user-184",
  "aud": ["orders-api"],
  "iat": 1794820200,
  "exp": 1794821100,
  "jti": "at-9f2b7c32",
  "scope": "orders.read"
}
```

The values above are illustrative, not a real token. A local RS can check:

| Check | Data Source | Detects Revocation After Issuance? |
| --- | --- | --- |
| JWT signature | Known public JWK/JWKS | **No** |
| `iss` (issuer) | JWT claim + trusted issuer config | **No** |
| `aud` (audience) | JWT claim + API audience | **No** |
| `exp`/`nbf` | JWT claim + RS clock | **No**; only checks time-based expiration |
| `scope`/roles | Signed claims + RS policy | **No**; roles/scopes may be stale |
| `jti` not revoked | Denylist or state outside JWT | **Yes, if the RS actually queries an updated source** |
| Introspection `active` | Current AS/token state | **Yes, subject to AS freshness and caching** |

The deciding factor is **whether the RS queries or synchronizes fresh state somewhere outside the JWT**. Signature, timestamps, and immutable claims alone cannot reveal a newly issued revocation command.

### 2.2. The Authorization Server Holds Authorization/Token State

Spring Authorization Server uses `OAuth2AuthorizationService` to save and look up `OAuth2Authorization`, including the authorization grant, token metadata, and token state. When a revocation is processed, state at the AS is updated per implementation/policy.

Two common implementations:

- `InMemoryOAuth2AuthorizationService`: suitable for development or tests; state is not durably shared across nodes by default.
- `JdbcOAuth2AuthorizationService`: persists authorizations in a database; better suited for multiple AS instances accessing shared state when transactions, indexes, and operations are designed properly.

Note: **a database storing revoked tokens does not automatically participate in local JWT verification at an RS**. The RS must use introspection, a shared denylist, an event stream, or another state-checking mechanism if it needs to alter decisions before `exp`.

## 3. Diagram: What Happens When a JWT Is Revoked?

```mermaid
sequenceDiagram
    autonumber
    participant Client as OAuth Client
    participant AS as Authorization Server
    participant State as OAuth2AuthorizationService
    participant RS as Resource Server (JWT offline)
    Client->>AS: POST /oauth2/token (valid grant)
    AS->>State: Save authorization/token state
    AS-->>Client: JWT access token (exp 09:15)
    Client->>RS: GET /orders + Bearer JWT
    RS->>RS: Verify signature + iss/aud/exp/scope
    RS-->>Client: 200
    Client->>AS: POST /oauth2/revoke (09:03)
    AS->>State: Mark token as revoked
    AS-->>Client: 200 OK
    Note over AS,RS: No automatic revocation message is sent to offline RS
    Client->>RS: Resend old JWT (09:07)
    RS->>RS: Signature and exp are still valid
    RS-->>Client: May still return 200 without external state check
```

**Two events are not equivalent**:

- **AS revocation succeeds:** the AS no longer considers this token valid per its revocation state and policy.
- **RS rejects immediately:** happens only when the RS has already observed the revocation state or when the token expires/fails another policy.

A complete logout workflow must consider token state, browser/BFF sessions, and how the RS validates tokens.

## 4. What Does RFC 7009 Specify?

**RFC 7009 — OAuth 2.0 Token Revocation** defines the Revocation Endpoint so clients can ask the AS to invalidate tokens they no longer need.

### 4.1. Endpoint Request and Response

The client sends an HTTP POST, typically with `application/x-www-form-urlencoded`, appropriate client authentication, and parameters:

```http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_CLIENT_CREDENTIALS_PLACEHOLDER
Content-Type: application/x-www-form-urlencoded

token=TOKEN_PLACEHOLDER&token_type_hint=access_token
```

- `token`: required, the value of the token to revoke.
- `token_type_hint`: optional, e.g., `access_token` or `refresh_token`; merely a lookup hint for the server, not proof the token is of that type.
- The endpoint must be protected with HTTPS/TLS and proper client authentication/authorization. Never log raw tokens, `Authorization` headers, or request form bodies.

**Success response:**

```http
HTTP/1.1 200 OK
Cache-Control: no-store
Pragma: no-cache
```

Per RFC 7009, the server returns **HTTP 200** both when the token was successfully revoked **and when the client submits an invalid token**. This is intentional to avoid turning the endpoint into a token-probing tool; the response body carries no proof of token existence or propagation reach. Errors such as `invalid_client` can still occur if client authentication fails; do not assume every request must return 200.

### 4.2. Revoking Access Tokens vs. Refresh Tokens

RFC 7009 requires implementations to support revoking **refresh tokens** and recommends supporting revoking **access tokens**. Cascading to related tokens depends on policy:

| Action | Expected Consequence | Do Not Infer |
| --- | --- | --- |
| Revoke refresh token | AS must not use that refresh token to issue new tokens | Previously issued JWT access tokens vanish from all RS instances |
| Revoke access token | AS records the token as revoked per implementation/policy | Every offline JWT RS will call back to the AS to verify |
| Revoke refresh token when AS supports access token revocation | RFC recommends AS also invalidate access tokens in the same grant | Every AS/RS implements cascading identically |
| Revoke access token | AS may revoke same-grant refresh token per policy | Cascading is mandatory and needs no testing |

An HTTP 200 only speaks to protocol handling; clients and RSs **must not** treat it as proof that all related tokens lost access everywhere.

### 4.3. What Does "Immediately Invalidated" Mean in a Distributed System?

RFC 7009 describes a token as invalidated once the AS processes the revocation, while explicitly noting **propagation delay** among components aware of revocation state. With self-contained tokens and offline RS checks, the AS cannot force an RS to re-read state merely by updating its database.

Therefore distinguish:

1. **Validity under AS policy:** the token is marked inactive.
2. **When the RS notices:** depends on introspection, caching, events, or TTLs.
3. **In-flight requests:** a request authenticated by the RS before revocation may complete after revocation unless the system implements cancellation/re-checks.

Never claim "every API stops accepting the token at the exact moment logout is clicked" without synchronous design and strong assumptions about networks, caches, and in-flight requests.

## 5. Why Does Local JWT Verification Not Detect Revocation?

### 5.1. What Does the Resource Server Verify?

A typical JWT flow looks like:

```mermaid
flowchart TD
    A["HTTP Authorization: Bearer JWT"] --> B["BearerTokenAuthenticationFilter"]
    B --> C["JwtAuthenticationProvider / JwtDecoder"]
    C --> D{"Valid signature with JWK?"}
    D -->|"No"| X["401 invalid_token"]
    D -->|"Yes"| E{"Valid issuer, audience, nbf, exp?"}
    E -->|"No"| X
    E -->|"Yes"| F{"Valid API scope/role/policy?"}
    F -->|"No"| Y["403 forbidden"]
    F -->|"Yes"| G["Allow request processing"]
    Note["No revocation lookup step unless configured"] -.-> C
```

A JWT is signed and **immutable** data. The AS can mutate the `OAuth2Authorization` record, yet the RS does not automatically execute `OAuth2AuthorizationService.findByToken(...)` or call the revocation endpoint during decoding.

Nor is JWKS a token database. It distributes public keys for verifying signatures; it does not contain a list of revoked access tokens.

### 5.2. Risk Window Without State Checks

Suppose a token has `T_remaining` time left at revocation. For an RS that only validates the JWT with no state check:

```text
Approximate remaining acceptance window =
  max(0, JWT expiration time - revocation time)
  + RS clock skew tolerance (if any).
```

If 12 minutes remain on the JWT and the RS uses no additional revocation mechanism, an attacker holding the token has an **access window potentially spanning nearly 12 minutes**, plus clock tolerance. This is a **security limitation of the offline architecture**, not a Spring flag you can toggle to magically update already-signed tokens.

Documentation should say "the RS may still accept the JWT" rather than "the RS will definitely let it through": the token can still be rejected by audience, scope, IP policy, resource ownership, or other checks.

### 5.3. Logout, Revocation, and Session Termination Are Not the Same

| Event | Direct Change | Impact on JWT Access Tokens at Offline RS |
| --- | --- | --- |
| User logs out of web app/BFF | Clears local session/cookie or browser session | Does not invalidate JWT access tokens |
| OIDC RP-Initiated Logout | Ends login session at the OP per OIDC | Not synonymous with rejecting all JWT access tokens |
| Revoke refresh token | Blocks refreshing from that token | Old JWT access tokens may remain valid |
| Revoke access token at AS | Updates AS token state | Offline RS does not see the change automatically |
| Disable user/tenant | Updates user/tenant/policy state | Offline RS may still rely on old claims snapshot |
| Remove public JWK or rotate keys | Affects signature verification | Can break many valid tokens sharing the key; depends on caching and old keys |

In token-theft incidents, handle **both refresh tokens and access tokens**, as well as application sessions, per your threat model and incident response policy.

## 6. Architectures to Reduce Acceptance Time of Revoked JWTs

No single option fits every system. Design must begin from **the maximum allowed acceptance window after revocation** and the availability characteristics of the state-checking system.

| Option | How It Works | Revocation Freshness | Cost / Trade-offs |
| --- | --- | --- | --- |
| Offline JWT + short TTL | RS checks JWT only; token expires quickly | Delay at most roughly remaining lifetime + clock skew | Very fast, minimal AS dependency; **not immediate revocation** |
| JWT + per-request online introspection | RS asks AS/token-state service if `active` | Reflects revoke once AS updates state; subject to network latency and in-flight requests | Higher latency/QPS; depends on AS availability |
| JWT + introspection cache | RS caches `active` result | Adds cache validity duration to delay | Reduces QPS but introduces stale active cache |
| JWT + distributed denylist | RS checks `jti`/token hash in shared store after verifying JWT | Depends on update and cache/store query latency | Requires reliable storage, consistent keys/TTLs, fail-closed |
| JWT + push revocation events | AS emits events; RS updates local denylist | Eventual consistency; bus latency, consumer lag, restart/replay | Fast when healthy; no hard immediacy during partitions |
| JWT + authorization version | JWT carries version; RS checks latest version | Timely if RS queries shared state per request; delayed if cached | Requires designing version scope and bulk revocation authority |
| Opaque/reference + introspection | Token is a reference; RS queries AS for state | Convenient for checking `active`/revocation | Trades off latency, AS availability, and caching |
| DPoP/mTLS-bound access token | RS requires proof of private key possession | Limits reuse of stolen tokens | **Does not** invalidate tokens after revocation on its own |

**Quick selection rule:** if business requirements tolerate tokens remaining usable briefly after revocation, short-TTL JWTs may suffice. If an access token must be blocked before expiry, the RS needs **an additional live state source**: introspection, a denylist, or a policy state check. For strict SLAs, the architecture must also specify caching, retries, timeouts, failover, and data consistency guarantees.

### 6.1. Option A — Short-Lived Access Tokens, Managed Refresh Tokens

Pick a relatively short access token TTL—e.g., a few minutes per risk assessment. Clients use refresh tokens to obtain new ones; the AS blocks refreshes when users log out or refresh tokens are revoked.

```mermaid
flowchart LR
    C["OAuth Client"] -->|"JWT AT: short TTL"| RS["Offline Resource Server"]
    C -->|"Refresh token when needed"| AS["Authorization Server"]
    AS -->|"Check refresh token state"| S[("OAuth2AuthorizationService")]
    C -.->|"Logout/revoke refresh"| AS
    AS -.->|"Block next refresh"| C
    RS -.->|"Old JWT may still be accepted until exp"| C
```

Pros: keeps APIs fast without per-request AS introspection. Cons: **does not guarantee immediate access token rejection**. After revoking the refresh token, an old JWT access token held by an attacker can still be used until expiration, even if the legitimate client deleted it.

Example `TokenSettings` configuration for a `RegisteredClient`:

```java
import java.time.Duration;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

TokenSettings tokenSettings = TokenSettings.builder()
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .refreshTokenTimeToLive(Duration.ofDays(7))
        .reuseRefreshTokens(false)
        .build();
```

This is only a **token policy** example, not a recommendation to grant 7-day refresh tokens to every client. TTLs and rotation depend on client type, grant, device, security policy, and detection design. `reuseRefreshTokens(false)` issues a new refresh token in refresh flows, and **does not automatically revoke previously issued JWT access tokens at offline RSs**.

**Never pick TTLs by gut feeling**: for sensitive sessions, quantify the attacker's remaining usage window; for flaky networks, factor in refresh latency and AS load.

### 6.2. Option B — Per-Request Introspection, Even When Token Format Is JWT

Per **RFC 7662**, the Resource Server calls the AS's Token Introspection Endpoint to ask whether the token is `active`. A response may include:

```json
{
  "active": true,
  "scope": "orders.read",
  "client_id": "orders-web",
  "sub": "user-184",
  "exp": 1794821100
}
```

After the token is revoked and the AS updates state, the response is typically:

```json
{
  "active": false
}
```

This is an **illustrative JSON sample**, not a guarantee that the AS returns all those claims or that databases replicate instantaneously across nodes. For inactive tokens, the AS should not disclose sensitive token details beyond what the standard permits.

Key point: **JWT access tokens can still be introspected**. Spring Security Resource Server can use `opaqueToken` configuration to send the token string to the Introspection Endpoint regardless of whether the token itself is structured as a JWT or opaque string.

Spring Boot 3.x / Spring Security 6.5 configuration example:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: orders-api-introspector
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

In the Java security chain:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/actuator/health").permitAll()
            .anyRequest().hasAuthority("SCOPE_orders.read"))
        .oauth2ResourceServer(oauth -> oauth
            .opaqueToken(Customizer.withDefaults()));
    return http.build();
}
```

The feature is named `opaqueToken` because the RS uses the **introspection** protocol rather than decoding JWTs locally. The token can still be a JWT. In this setup, **the RS trusts the AS's inspection result** and does not by default run local JWT signature/issuer/audience validators like `jwt()` does. You must test that AS introspection actually validates the token, checks revoked state, issuer, audience/resource, scopes, and permissions properly. Also restrict who may call introspection and protect credentials with a secret manager and TLS.

**Conditions for detecting revocation:** token state at the AS must support marking tokens inactive, the RS must actually call introspection with the right token, and no `active=true` cache may exceed acceptable bounds. If custom AS introspection ignores revocation state, switching the RS to introspection solves nothing.

### 6.3. Option C — Denylist by jti or Fingerprint

Keep offline JWT signature validation, while the RS performs **one extra step** to check revocation state:

1. The AS issues access tokens with a unique `jti`; RSs follow the `iss + jti` convention.
2. On revocation, the AS identifies the `jti` or token fingerprint and writes a "revoked" entry to a shared store.
3. Before allowing a request, the RS checks whether the `jti` is revoked.
4. The store retains the entry at least until every RS rejects the JWT via `exp` plus clock tolerance.

```mermaid
flowchart TD
    C["Client sends Bearer JWT"] --> RS["Resource Server"]
    RS --> SIG{"Valid signature + iss/aud/exp?"}
    SIG -->|"No"| DENY["401 invalid_token"]
    SIG -->|"Yes"| KEY["Extract issuer + jti from verified token"]
    KEY --> STORE[("Shared revoked-jti store")]
    STORE --> REVOKED{"Present in denylist?"}
    REVOKED -->|"Yes"| DENY
    REVOKED -->|"No"| SCOPE{"Scope + resource policy satisfied?"}
    SCOPE -->|"Yes"| ACCEPT["Allow request"]
    SCOPE -->|"No"| FORBIDDEN["403 forbidden"]
    AS["Authorization Server"] -->|"Revoke event / atomic record"| STORE
```

**The denylist must be trustworthy**:

- Shared cache/store across all RS instances; data scoped by issuer/region.
- Never purge entries before the JWT expires across all RSs, including clock skew.
- Writes must be confirmed durable before declaring the token blocked per SLA.
- If the store is unreachable, fail closed on sensitive endpoints; never allow access simply because "entry not found" when the lookup timed out.
- Enforce size bounds, rate limits, and key schemas; avoid storing raw bearer tokens in logs/stores unnecessarily.
- If `jti` is omitted or non-unique, design a migration/fingerprint scheme and ensure lookups never collide across tokens.

Using `jti` does not make `jti` itself a secret, though it can act as a correlation ID; avoid spraying it freely into metrics/logs. For token hashes, use a strong digest of **the entire raw token** or an indexing HMAC; never store plaintext tokens as a "convenient cache key".

### 6.4. Option D — Push Revocation Events and Local State Cache

The AS publishes an event when a token/authorization is revoked; RS instances or an edge authorization service consume the event and update a local cache.

Pros: low API verification latency when reading from a local cache. Cons: **eventual consistency**. An RS disconnected from the bus can keep accepting old tokens; events lost during deployments can leave local state stale indefinitely.

To operate reliably:

- Events include an ID, issuer, token identifier, revoke/expiration timestamps, and version.
- Consumers are idempotent, support durable replay/offsets, and resync after restarts.
- Monitor consumer lag and when each RS catches up to the high-water mark.
- If blocking within seconds is required, define behavior when an RS lags beyond SLA (fail-closed or fall back to online lookup).
- Never publish raw access tokens over a message broker when a hash/ID suffices.

**When the AS emits an event is not when every RS receives it.** Never guarantee zero delay based on push events alone.

### 6.5. Option E — Authorization/Session Version

The AS stores a version or permission-change timestamp per user, client, or authorization. JWTs carry a claim such as `authz_version`, and the RS compares it against the current version.

Example:

```json
{
  "sub": "user-184",
  "authz_version": 12,
  "aud": ["orders-api"],
  "exp": 1794821100
}
```

When the user is locked or all sessions are revoked, increment the version to 13. The RS reads current state, sees token version 12, and rejects it.

**Design note:** if the RS fetches the version from a 60-second cache, detection delay can still be 60 seconds. Per-user versions revoke many tokens at once but may log out all devices; per-authorization/client/session versions target more precisely at higher complexity. Never use one global version for all accounts when only a single session needs revoking.

### 6.6. When Should You Choose Opaque Tokens?

If per-request token state enforcement is mandatory and the AS/Introspection Service can handle the load, **opaque/reference tokens** are often easier to govern: the token value merely references state at the AS. The RS introspects rather than trusting self-contained claims.

However:

- Introspection can still be cached and introduce delay.
- AS outages/timeouts require a defined failure policy.
- APIs must ensure `active` reflects the true state of the right token and client/resource.
- Opaque tokens do not eliminate bearer-token theft risks; TLS and proper scopes/TTLs are still required.
- Switching JWT → opaque affects API configuration, monitoring, scaling, and authorization.

## 7. Defining a Revocation Time Commitment (Revocation SLA)

### 7.1. Defining "Revoked Within N Seconds" Precisely

An SLA should state explicitly:

> After a revoke event is confirmed by the AS at time T0, every new request beginning authentication at an RS within scope X must be rejected no later than T0 + N seconds, except under conditions enumerated in the failure model.

Do not interpret this as "every in-flight request is aborted immediately" unless APIs support aborting transactional work or re-checking at commit time.

A latency budget breakdown when using events/caching:

```text
T_observed_revoke =
  T_AS_commit
  + T_event_propagation
  + T_RS_consumer_lag
  + T_lookup_cache_staleness
  + T_clock_tolerance / processing effects
```

This breaks down latency sources **for measurement and budgeting**, not as a hard upper-bound guarantee; delays may overlap, and network partitions are unbounded without fail-safes. With TTL-only approaches, JWT acceptance delay depends on remaining lifetime rather than event propagation.

### 7.2. Grouping Requirement Tiers

| Business Goal | Suggested Design | What Must Be Tested |
| --- | --- | --- |
| Tolerates a few minutes' delay | Short-TTL JWT + revoke refresh | Max window from revoke to `exp`, RS clock skew |
| Block before expiration within tens of seconds | Shared denylist/introspection with small cache TTL or push + fallback | Cache staleness, propagation lag, RS failure mode |
| Block at new request time | Introspection/live state check or central authorization decision | AS availability, latency, revoke commit races, in-flight requests |
| Emergency cross-region revocation | Architecture-dependent: central authoritative state + fail-closed + revoke propagation | Region isolation, event replay, data replication, chaos testing |

"Offline JWT + zero state calls + immediate per-token revocation" is not a feasible combination. To learn of a change after a JWT was signed, the RS must receive new state from elsewhere or the token must expire.

### 7.3. Cache Delay Is Part of the Security Contract

If introspection returns `active=true` and the RS caches it for 5 minutes, a token revoked immediately after the cache entry is populated can stay accepted for nearly 5 minutes. **Introspection cache lifetime must not be conflated with access token TTL.**

For a system requiring a 30-second SLA:

- Caching `active=true` with a TTL longer than 30 seconds is generally unsuitable without reliable invalidation.
- Propagation delay, multi-node sync, and timeouts must still fit within the budget.
- Negative `active=false` caching also needs its own policy to avoid lingering errors if state can change via special flows; normally revoked tokens should be treated as terminal.
- Choose fail-open vs. fail-closed per endpoint security requirements and document behavior when the AS or cache fails.

### 7.4. Do Not Ignore In-Flight Requests

A request might pass the JWT validator at 09:02:59, the AS revokes at 09:03:00, and the request writes data at 09:03:05. If business rules must prevent any data mutation post-revocation, validating the token at request entry is insufficient: you need a transaction-level authorization check or distributed coordination at commit time.

This is a stronger guarantee than "every new request after N seconds is rejected." Avoid promising the two as if they were identical.

## 8. Spring Authorization Server: Revocation Endpoint and Token State

### 8.1. Participating Components

Spring Authorization Server exposes the Revocation Endpoint per RFC 7009. By default, the endpoint is typically `POST /oauth2/revoke`; the path can be changed via `AuthorizationServerSettings`.

| Component | Responsibility |
| --- | --- |
| `OAuth2TokenRevocationEndpointFilter` | Receives revocation requests on the AS SecurityFilterChain |
| `OAuth2TokenRevocationAuthenticationConverter` | Reads token, token type hint, and client context |
| `OAuth2TokenRevocationAuthenticationProvider` | Processes revocation with authenticated client and authorization/token state |
| `OAuth2AuthorizationService` | Saves/looks up authorizations and token states |
| `OAuth2TokenRevocationEndpointConfigurer` | Allows customizing request converters, providers, and handlers |
| `OAuth2TokenIntrospectionEndpointFilter` | Handles introspection, a separate endpoint |
| `OAuth2TokenGenerator` | Generates tokens on valid grants; does not propagate revocations to RSs |

These components orchestrate changes to **state at the AS**. They do not automatically wire a revocation-state lookup into every Resource Server's `JwtDecoder`.

### 8.2. Default AS Configuration

The example below illustrates setting up the AS `SecurityFilterChain` along with issuer and revocation paths:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain authorizationServerChain(HttpSecurity http)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, Customizer.withDefaults())
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}

@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .tokenRevocationEndpoint("/oauth2/revoke")
            .tokenIntrospectionEndpoint("/oauth2/introspect")
            .build();
}
```

**This is a partial example**; a real application still needs signing keys, a client repository, an authentication/login chain, authorization services, token policies, and related flow configurations. Never replace the entire revocation provider with a `@PostMapping("/oauth2/revoke")` controller just to "flip state" while skipping authentication, token ownership, and RFC semantics.

### 8.3. Protecting AS State in Multi-Node Deployments

For an AS cluster:

- Use an authorization-state backend with durability and consistency meeting your targets, rather than each node keeping a separate `InMemoryOAuth2AuthorizationService`.
- Verify transaction commit before considering revocation persisted; do not rely solely on a handler having sent an HTTP response.
- Verify `OAuth2TokenIntrospectionEndpointFilter` reads the updated state after revocation.
- If using events/outbox, design commit and event publication so crashes between steps never drop a revocation event.
- If revoking access tokens concurrently with refresh flows, test races between the two operations so extra tokens are not issued against policy.
- Maintain client authentication, HTTPS, and log redaction at both Revocation and Introspection Endpoints.

In Spring Authorization Server, whether a token marked inactive by the AS returns inactive **must be tested in practice via introspection**; never assume that because a JSON JWT still has a valid signature, introspection will behave as expected when using custom persistence/providers.

### 8.4. Limits of Customizing the Success Handler

`OAuth2TokenRevocationEndpointConfigurer` lets you replace the response handler or authentication provider. **The success handler runs at the protocol response stage** and does not guarantee every RS has seen the change. To synchronize denylists/events, integrate into an application service handling revocation with proper transactional/outbox semantics, and define the **acknowledgment point** for your SLA.

Avoid fire-and-forget revocation events while returning a message claiming "token blocked across all APIs" without downstream confirmation. Never log raw tokens to construct event payloads.

## 9. Spring Security Example: JWT Validator Combined with a Denylist

The pattern below targets an architecture of **JWT signature validation at the RS + checking revoked state by `jti` in a shared store**. This example intentionally separates the storage API and is not built-in Spring Authorization Server code.

### 9.1. State Lookup Interface

```java
public interface RevokedJwtLookup {

    // True when token for issuer and jti has been marked revoked.
    // Implementation needs explicit timeouts, fail-closed handling
    // for sensitive endpoints, and must not log raw tokens.
    boolean isRevoked(String issuer, String jti);
}
```

Implementations may use Redis, a database, or a dedicated authorization-state service. **Never default** `isRevoked(...)` to returning `false` on Redis timeouts; that creates a silent fail-open bug.

### 9.2. Validator Combining Signature, Claims, and Revocation

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Bean
JwtDecoder jwtDecoder(RevokedJwtLookup revokedLookup) {
    String issuer = "https://auth.example.com";
    String audience = "orders-api";

    NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri("https://auth.example.com/oauth2/jwks")
            .build();

    OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
        boolean valid = jwt.getAudience() != null
                && jwt.getAudience().contains(audience);
        return valid
                ? OAuth2TokenValidatorResult.success()
                : invalid("Token is not intended for orders-api");
    };

    OAuth2TokenValidator<Jwt> revocationValidator = jwt -> {
        String jti = jwt.getId();
        if (jti == null || jti.isBlank()) {
            // Under a policy requiring jti, missing jti is invalid.
            return invalid("Token has no jti");
        }
        return revokedLookup.isRevoked(issuer, jti)
                ? invalid("Token has been revoked")
                : OAuth2TokenValidatorResult.success();
    };

    decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(issuer),
            audienceValidator,
            revocationValidator
    ));

    return decoder;
}

private static OAuth2TokenValidatorResult invalid(String description) {
    return OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", description, null));
}
```

**Usage:** place these methods in a Resource Server `@Configuration` class (adjust access modifiers/bean wiring per project). This is policy-illustrative code requiring appropriate imports and version-matching dependencies before running. The decoder verifies signatures via JWKS; the composite validator then checks default claims including issuer/timestamps, the API's audience, and revoked state. Real applications also need algorithm constraints, scopes/authorities, and resource-level authorization.

**Critical security ordering:** trust `iss/jti` only after the JWT has been decoded and its signature verified; in this example, the lookup uses a fixed issuer from trusted configuration to namespace keys, rather than an unverified input-selected issuer. Never write a custom base64 parser to grab `jti`, query the store, and grant access before verifying the signature.

**Failure mode note:** if `revokedLookup.isRevoked(...)` throws an I/O error, that does not mean `not revoked`. Enforce a fail-closed policy and proper exception mapping (potentially returning 503 if the authorization-state system is failing); never swallow exceptions and treat the token as valid. Depending on SLA, apply timeouts, bounded retries, and circuit breakers defaulting to **deny** for sensitive APIs.

### 9.3. Writing to the Denylist: TTL and Namespacing

When the AS/Revocation Service receives a verified token:

```text
key    = "revoked:" + hash(issuer) + ":" + hash(jti)
value  = true
expiry = exp + maxResourceServerClockSkew + operationalSafetyMargin
```

In implementation:

- Set TTL based on **the token's own `exp`** plus clock tolerance across all RSs. Never pick an arbitrary 10 seconds for a JWT valid for 15 minutes.
- Use a stable, unique token identifier; if legacy JWTs lack `jti`, consider hashing the entire token after validation.
- Never write verbatim tokens to logs, cache keys, or audit events.
- Test across multiple issuers and `jti` values to prevent namespace collisions.
- Make denylist writes idempotent; repeated revocations must not invert state.
- Never write `revoked=false` on timeout/no response; allow access only on a **reliable negative lookup**.

**This is not a built-in `JwtDecoder` toggle.** Both writing to the denylist at the AS and reading at the RS must be wired into the real flow—do not add a validator at the RS and forget to propagate revocations to the store.

### 9.4. Testing Custom Validators at the Right Layer

When using `SecurityMockMvcRequestPostProcessors.jwt()` in unit tests, Spring Security Test can inject a synthetic authentication without running the actual decoder. Therefore, tests with `jwt()` **do not prove** that a custom `JwtDecoder` executed the revoked-`jti` lookup.

At least two test groups are required:

1. **Decoder/validator unit tests**: generate signed JWTs/fixtures matching your version or test the validator directly, mocking `RevokedJwtLookup` for true/false/timeout; verify issuer/audience/exp.
2. **Real HTTP request integration tests**: call the API with a test JWT signed by the test AS's key, verifying the RS processes the token through `BearerTokenAuthenticationFilter` and the real decoder config. After revocation, new requests must return 401 within SLA.

Never put production tokens in test logs; never print raw JWTs/`Authorization` headers in assertion failures.

## 10. Solutions Commonly Mistaken for Immediate JWT Revocation

### 10.1. Deleting or Rotating JWT Signing Keys

A common suggestion is "delete the old JWK so stored tokens become invalid." This is not a normal way to revoke an individual user's access token:

- Many JWTs are signed with the same private key. If Resource Servers stop trusting that public key, **many valid tokens** will be rejected simultaneously.
- RSs may cache JWKS; removing a public key from the JWKS endpoint **does not guarantee** every RS drops the key from cache immediately.
- Normal rotation keeps the old public key long enough for already-signed unexpired tokens to verify; that very property means normal rotation **does not** revoke a single JWT.
- Abrupt key changes can cause downtime, trigger widespread 401 spikes across APIs, and leave nodes out of sync.

**Key rotation is essential when a signing key is compromised**, requiring an emergency runbook and the ability to force RSs to refresh trust stores/JWK caches. Never use it in place of a `jti` denylist/introspection for a single user's logout.

### 10.2. Deleting Tokens from the Database

Removing a record from `OAuth2AuthorizationService` may prevent the AS from finding the token and make introspection report inactive per implementation; however, JWTs at offline RSs still retain valid payloads and signatures. If the AS changes state but the RS never reads it, API behavior remains unchanged until `exp`.

Moreover, deleting the whole authorization record can destroy audit data, grant tracking, and related tokens. Prefer protocol-compliant revoke/invalidate workflows and retention policies over unassessed direct database deletion.

### 10.3. Logging Out of the Authorization Server

Ending a login cookie/session at the AS does not automatically make Resource Servers reject already-issued JWT access tokens. Distinguish browser sessions, OAuth client/BFF session cookies, refresh tokens, and access tokens. In OIDC, OP logout and token revocation are related problems that **do not substitute for each other**.

### 10.4. Changing Roles or Locking Accounts

JWT claims like `roles`, `scope`, or `tenant_id` are snapshots. If the RS relies solely on signed claims and a user loses a role after token issuance, the RS can continue honoring the old role. When business logic requires current permissions:

- Shorten access token TTLs.
- Check live authorization/account state.
- Use authorization versions/epochs with controlled lookups.
- Use introspection or a policy engine for resource-level authorization.

Never treat "updating a role in the user database" as proof that JWTs stored on clients have been updated.

### 10.5. DPoP or mTLS-Bound Tokens

DPoP and certificate-bound access tokens prevent someone holding only the token value from reusing it without possessing the corresponding key. These are **sender constraints**, not mechanisms to inform the RS that the AS revoked the token. If the private key or client runtime is also compromised, tokens still require dedicated revocation and freshness strategies.

## 11. Choosing an Approach Based on Threat Model

### 11.1. Architectural Questions to Answer

Before choosing JWT vs. opaque tokens, the design team should answer:

1. Which events must block immediately: user logout, lost device, account lock, role change, tenant deprovisioning, client secret compromise?
2. Do we need to revoke **one access token**, an authorization grant, all tokens for a user, or a client/service account?
3. What delay is acceptable after the AS confirms revocation?
4. How many RS instances, regions, CDNs/API gateways, and intermediate caches exist?
5. During a network partition or introspection outage, should APIs reject or temporarily allow?
6. Are there non-idempotent/long-running requests requiring an authorization re-check before commit?
7. Do access tokens have unique `jti`, restricted `aud`, and sensible `exp`?
8. Can the system tolerate the load and latency of per-request lookups?

### 11.2. Illustrative Decision Example

Suppose a public catalog-read API tolerates tokens remaining valid for up to 5 minutes after revocation, while a money-transfer API must verify account/token state close to request time:

| API | Illustrative Control | Why |
| --- | --- | --- |
| Catalog/low-risk read | Short-TTL JWT, offline signature verification | Optimizes throughput; low stale-authorization risk |
| Customer profile | Short-TTL JWT + denylist cache or introspection | Personal data warrants fresher state |
| Payment approval | Online authorization-state check, policy engine, and pre-commit re-check when needed | High impact of data changes; explicit failure modes needed |
| Admin/tenant management | Introspection or distributed denylist, checking tenant/status and current roles | Role/tenant changes must take effect quickly |

This is an illustrative classification, **not** a mandate that every system use this exact design. Organizations must run threat modeling, SLA reviews, compliance checks, and load/failure testing before finalizing.

### 11.3. Measurements Needed

Use safe timestamps:

```text
T_request_revoke     = when AS starts processing revoke
T_committed          = when token state has been committed
T_ack                = when client receives 200
T_rs_last_accept     = last time RS accepted the revoked token
T_rs_first_reject    = first time RS rejected that token
T_event_consumed     = when RS processed the event (if applicable)
```

Actual delay can be measured as `T_rs_first_reject - T_committed` under sufficiently dense test traffic; polling only every 10 seconds cannot pinpoint timing finer than that resolution. Never store raw bearer tokens in telemetry; use test token identifiers with redaction policies.

For event-based caches, monitor consumer lag, cache age, missed events, cache read timeouts, AS introspection latency, 401/403 distributions, and JWT verifier failures by issuer/audience.

## 12. End-to-End JWT Revocation Test Matrix

| ID | Scenario | Expected Result |
| --- | --- | --- |
| R01 | Valid JWT before revocation | RS permits if signature, `iss`, `aud`, `exp`, and scopes match |
| R02 | Revoke access token, RS verifies JWT offline only | Demonstrates RS **may** continue accepting until `exp` without state lookup |
| R03 | Revoke refresh token | Refresh token cannot mint new access tokens; old JWT governed by separate policy |
| R04 | Revoke nonexistent/expired token | RFC 7009 success may be 200; does not disclose token existence |
| R05 | Wrong client authentication at revoke endpoint | No unauthorized revocation, returns appropriate OAuth error |
| R06 | Wrong `token_type_hint` | AS still performs standard lookup; hint is not trusted |
| R07 | Revoke JWT then introspect | Introspection of the same JWT reflects `active=false` once state updates |
| R08 | Valid JWT signature with wrong `aud` | RS rejects even when unrevoked |
| R09 | Invalid issuer/signature/expired JWT | RS rejects even if denylist reports not revoked |
| R10 | Revoked JWT with denylist entry | RS rejects new requests before `exp` |
| R11 | JWT missing `jti` in system requiring jti | Validator rejects or applies defined legacy fingerprint policy |
| R12 | Issuer A's JWT has same jti as Issuer B | Namespacing prevents revocation collisions |
| R13 | Denylist entry expires before JWT | Test catches and prevents replay of revoked token |
| R14 | Idempotent denylist write | Repeated revocation does not reactivate token |
| R15 | Multi-node RS, same revoked token | All nodes observe the same state within SLA |
| R16 | Multi-node AS, same token | Revocation state/introspection consistent per deployment policy |
| R17 | RS partitioned from denylist | Fail-closed/fallback behavior tested, never silent fail-open |
| R18 | Introspection service timeout/503 | RS applies failure policy; never assumes token stays active |
| R19 | Long-lived `active=true` introspection cache | Revoke delay measured and kept within budget |
| R20 | Event bus consumer pauses then recovers | Replays/resyncs events without losing revocation state |
| R21 | Duplicate or out-of-order events | Idempotent consumer and versioning never reactivate token |
| R22 | Browser user logout | Session closed; access/refresh token policies tested independently |
| R23 | User loses role/tenant | Old tokens and authorization-state checks behave within SLA |
| R24 | Short access token TTL | RS rejects after `exp` even if AS is unavailable |
| R25 | RS clock skew within allowed bounds | Token expiry and denylist TTL account for tolerance |
| R26 | Normal key rotation | Issued JWTs continue verifying per policy until expiry |
| R27 | Emergency key compromise | Runbook forcing trust refresh and affected token scope tested |
| R28 | Request passes auth before revoke, commits after | In-flight behavior explicitly defined, not falsely promised blocked |
| R29 | Test using only MockMvc `jwt()` | Not treated as proof `JwtDecoder`/denylist actually executed |
| R30 | Test with real signed JWT and HTTP filter chain | Revoked token rejected at RS per policy |
| R31 | Tokens in logs, traces, audits, test reports | Zero raw bearer/refresh tokens or client secrets |
| R32 | Revocation Endpoint returns 503 | Client assumes token may still exist and retries safely |

### 12.1. Timing and Concurrency Testing

To measure SLA compliance, tests should include:

- Test token TTL long enough to observe revocation before `exp`.
- Multiple client/RS instances, and multiple regions if production is multi-region.
- Mocked or synchronized clocks with consistent timestamp collection.
- Request frequency high enough to measure the post-revoke acceptance window.
- Concurrent revocation and refresh requests to surface race conditions.
- Scenarios where the AS, downstream cache, or event bus loses connectivity.
- Assertions that all RS instances in scope stop accepting the token within SLA, rather than just one node.

For pure offline JWTs, expected test outcomes must document the limitation: tokens may still be accepted before `exp`. **Never alter test outcomes by blocking tokens artificially in a mock and claiming production is solved.**

### 12.2. Testing Without Exposing Credentials

Revocation request bodies contain raw tokens to revoke. In tests:

- Use synthetic tokens issued by a test AS, never production access/refresh tokens.
- Never print `Authorization` headers or `token` form parameters.
- Never attach request/response bodies containing bearer tokens to public tickets/CI artifacts.
- For correlation, use test `jti` values or irreversible HMAC identifiers.
- Protect introspection client secrets with an environment secret manager.

## 13. Runbook When a JWT Compromise Is Detected

Suppose an access token appeared in a gateway debug log.

### 13.1. Priority Actions

1. **Stop the leak source:** disable capture/logging at the exact gateway/filter/APM; preserve incident evidence per procedure.
2. **Determine scope:** issuer, client, subject/authorization, audience, scopes, `jti`, and `exp`; never spread raw tokens in tickets.
3. **Revoke related credentials:** revoke refresh tokens/authorizations and access tokens at the AS per policy; rotate client credentials if exposed.
4. **Block the access token at RSs:** if RSs use introspection/denylists, push state and verify; otherwise rely on TTL or trigger scoped emergency measures.
5. **Audit for abuse:** redacted resource access logs, IP/device patterns, high-risk API operations, and transaction audits.
6. **Monitor until expiration:** verify the token is not accepted unexpectedly and check other tokens in the same authorization.
7. **Remediate root cause:** add redaction, regression tests, TTL/revocation policy updates, and update playbooks.

Never treat HTTP 200 at the Revocation Endpoint as completing all steps above while RSs remain offline.

### 13.2. When Emergency Key Rotation Is Necessary

If a **private signing key** is compromised, impact can include **every token signed with that key**. Plan for:

- Generating/deploying a new secure key; marking the old key untrusted.
- Identifying all RSs that may cache JWKS or use local trust stores.
- Coordinating forced trust-cache refreshes and verifying old JWTs are truly rejected.
- Communicating potential disruption/token re-issuance and watching 401 rates.
- Never merely deleting the key on the AS and assuming all RSs noticed.

This is a signing-key incident response procedure, not a routine action for user logouts or role changes.

## 14. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| "Revoke returning 200 means every API rejects the JWT immediately." | RFC 7009 succeeded at the AS; offline RSs do not automatically learn the new state. |
| "A JWT with a valid signature means it has not been revoked." | Signatures prove integrity/origin only, not revocation status. |
| "Deleting the authorization record deletes the JWT from devices." | Self-contained JWTs still exist; offline RSs may accept until `exp`. |
| "Revoking the refresh token invalidates all old access tokens." | Stopping new refreshes does not mean local RSs block old JWTs. |
| "Logging out of the web app revokes all tokens." | Browser sessions/BFF cookies and access/refresh tokens are distinct states. |
| "Opaque tokens guarantee instant revocation everywhere." | Depends on introspection, state consistency, caching, and failure modes. |
| "`opaqueToken` config only works with true opaque tokens." | Spring can introspect JWTs as token strings too. |
| "Introspection automatically checks audience/resources like `JwtDecoder`." | Test actual AS policy and Resource Server authorization. |
| "Setting a 5-minute TTL means immediate revocation." | Tokens remain usable until `exp`; TTL only bounds the window. |
| "A denylist in one RS's HashMap suffices for a cluster." | Other nodes will not see it; shared state consistency/cache is required. |
| "Redis timeout means the token is not in the denylist." | Lookup failure differs from negative lookup; design fail-closed. |
| "Once a push event is emitted, every node received it." | Eventual consistency, lost events, or lag require recovery mechanisms. |
| "Deleting a JWK is how to revoke one user." | Affects many tokens, and JWKS caching makes it non-instantaneous. |
| "Spring Security Test `jwt()` proves the revoked-jti decoder works." | Mock authentication can bypass the decoder; signed-token integration tests are needed. |
| "Once a token is revoked, all in-flight requests must stop." | Requires additional authorization/transaction checks at commit time. |

## 15. Pre-Production Checklist

**Protocol and Authorization Server**

- [ ] Revocation Endpoint complies with RFC 7009: POST, client authentication, no token leaks.
- [ ] HTTP 200 for revoked or invalid tokens, without disclosing token existence.
- [ ] Access/refresh token revocation and cascading policies are distinguished.
- [ ] Token state is persisted durably/consistently across the AS cluster.
- [ ] Introspection of a revoked JWT genuinely returns `active=false` per implementation.
- [ ] Token, revocation, and introspection endpoints enforce HTTPS and log redaction.

**Resource Server**

- [ ] RS verifies signature, `iss`, `aud`, `exp`, `nbf`, and scope/resource policies.
- [ ] Architecture documents that pure offline JWTs **lack** per-token immediate revocation.
- [ ] If pre-`exp` revocation is required, RS uses introspection, a denylist, or live policy state.
- [ ] Denylist has key namespacing, TTLs, multi-node propagation, and fail-closed policies.
- [ ] Introspection cache TTL fits revocation SLA; AS outages are handled safely.
- [ ] JWKS rotation is never confused with per-token revocation.

**Operations and Testing**

- [ ] A revocation SLA explicitly defines new vs. in-flight requests and region/node scope.
- [ ] Test matrix covers logout, revoke, role changes, client compromise, and refresh races.
- [ ] Tests use real signed JWTs and the HTTP filter chain, not solely security test mock principals.
- [ ] Alerts monitor event lag, cache failures, introspection latency, and revocation propagation.
- [ ] Raw tokens are absent from logs, traces, metric labels, and test artifacts.
- [ ] Incident runbooks document revocation steps, RS enforcement, and emergency key rotation.

## 16. References

- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): requests, 200 responses, token cascading, and implementation notes for self-contained tokens.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active`, introspection responses, and cache state.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token claims and validation.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): `iss`, `aud`, `exp`, `nbf`, `jti`.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): access/refresh token security and authorization protection.
- [Spring Authorization Server 1.5.x — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): Revocation Endpoint, Introspection Endpoint, filters/providers, and extension points.
- [Spring Authorization Server 1.5.x — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `OAuth2AuthorizationService` and token state.
- [Spring Authorization Server 1.5.x — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): `AuthorizationServerSettings` and default endpoint paths.
- [Spring Security 6.5 — Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): local JWT validation and validators.
- [Spring Security 6.5 — Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html): using introspection with opaque tokens **or JWTs**.

**Conclusion:** The Revocation Endpoint changes **token state at the Authorization Server**, whereas a JWT verified locally by a Resource Server remains signed data that may continue to be accepted until expiration. Consequently, **immediate JWT revocation cannot be guaranteed solely via RFC 7009 or deleting records at the AS**. When tokens must be blocked before `exp`, Resource Servers must read updated state via introspection, a denylist, or live authorization policies; every approach needs explicit caching, propagation, and fail-closed modeling. Sound design starts from **target revocation latency, threat models, and tests across every RS**, never from expecting a JWT signature to reflect a new revocation command on its own.
