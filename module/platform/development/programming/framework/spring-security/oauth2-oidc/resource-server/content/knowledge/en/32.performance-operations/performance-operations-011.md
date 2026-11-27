# Issuer Outage Drills and Identifying Remaining Required Dependencies

An OAuth 2.0 Resource Server must know which Authorization Server issued a token and how to verify it. When the issuer goes down, the impact depends on the access token type and how the Resource Server is configured:

- **JWT access tokens** can be verified locally using signatures and public keys fetched from JWKS. When the key is still cached, a brief metadata/JWKS server outage does not necessarily fail current requests.
- **Opaque access tokens** usually require calling the introspection endpoint to check whether the token is still active. If the endpoint is unreachable and no explicitly designed cache exists, the Resource Server cannot verify the token and must reject protected requests.
- **Discovery metadata** is typically a startup or decoder-bootstrap dependency when using `issuer-uri` discovery. It is not a mandatory per-JWT request.
- **Token endpoint, authorization endpoint, UserInfo, and logout endpoint** do not normally sit on the Resource Server's access-token verification path. They may be required by other system roles, but should not be assumed to be runtime dependencies of the Resource Server.

This lesson guides controlled outage drills, observing real application behavior, and classifying dependencies by lifecycle. The goal is knowing when the service can keep serving, when it must fail closed, and what to configure so it starts and operates safely while the identity provider is unavailable.

> **Operational principle:** Never skip token verification when the issuer fails. JWTs can continue verifying with trusted cached keys; opaque tokens may be accepted only if introspection or a valid cache confirms state. Whenever trustworthy verification evidence is absent, reject the request.

## 1. Identify the Issuer and Its Dependencies

Before shutting down a service in a drill, map the Resource Server's dependencies. A system often exposes many endpoints under one IdP, yet not every endpoint sits on the request path.

### 1.1. Common Identity Endpoints

| Endpoint | Purpose | Does the Resource Server Need It Directly? |
| --- | --- | --- |
| OIDC Provider Configuration | Discovery metadata, publishing issuer and `jwks_uri` | Needed if using discovery to find JWKS; not needed per JWT request |
| OAuth Authorization Server Metadata | Metadata per RFC 8414 | Same: needed if using the corresponding discovery path |
| JWKS endpoint | Serves public keys to verify JWT signatures | Needed when loading/refreshing signing keys; not needed per request if keys are cached |
| Token introspection endpoint | Checks opaque token status | Usually needed per request unless an explicitly designed introspection cache exists |
| Token endpoint | Issues access tokens to OAuth2 Clients | Not a default dependency of a JWT/opaque Resource Server |
| Authorization endpoint | Login/consent/authorization codes | Not a default Resource Server dependency |
| UserInfo endpoint | Fetches OIDC profile info | Not needed to verify standard access tokens |
| Revocation endpoint | Clients request token revocation | Not an endpoint the Resource Server calls per request to verify |
| End-session/logout endpoint | Ends OIDC sessions | Not on the standard access token verification path |

The key distinction is that **the Resource Server verifies already-issued tokens**, whereas an OAuth2 Client or OIDC relying party may need those other endpoints to request tokens, log users in, or fetch profiles.

### 1.2. Dependencies by Phase

| Phase | JWT Resource Server | Opaque-Token Resource Server |
| --- | --- | --- |
| Application startup | May need discovery metadata if configured with `issuer-uri` and decoder runs discovery at init; discovery can be avoided with direct `jwk-set-uri` | Needs introspection URI and client authentication configured; usually does not call the endpoint just to build the introspector |
| First JWT verification | Needs matching public key; may fetch JWKS | Needs introspection endpoint to return `active=true` |
| Subsequent requests | Signature/issuer/time/audience usually checked locally using loaded keys | Usually calls introspection again unless cached |
| Unknown `kid` encountered | May need to refresh JWKS to find a new key | Not applicable |
| Key rotation | Needs updated JWKS and key overlap | Not applicable in the JWT signing sense |
| Revocation | Usually not seen immediately while token is unexpired without extra denylist/introspection | Can be reflected on the next introspection, depending on cache |
| Issuer outage | Tokens with cached keys can keep working until expiry or a new key is needed | New requests usually fail if introspection cannot run and no valid cache exists |

### 1.3. Foundational Dependencies Still Required

Even while the IdP is unreachable, the Resource Server still depends on:

- Correct issuer, audience, JWKS/introspection URI, and trust policy configuration.
- DNS, network routes, and TLS trust whenever connecting to identity endpoints.
- Synchronized system clocks to evaluate `exp`, `nbf`, `iat`, and clock skew.
- Key/token caches with explicit lifecycles and bounds.
- HTTP request handling, thread pools, connection pools, and logging/metrics.
- Business resource access and other downstream dependencies.

Do not lump everything into a single "IdP down" state. For instance, a metadata endpoint failure while the JWKS cache is still valid is very different from an introspection endpoint failure affecting every opaque token.

## 2. JWT Verification Model During Issuer Downtime

A JWT access token carries a signed header and claims. The Resource Server verifies the signature using the issuer's public key, then validates issuer, audience, timestamps, and contract validators.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant RS as Resource Server
    participant Cache as JWKS cache
    participant AS as Identity Provider

    C->>RS: Bearer JWT
    RS->>Cache: Look up key by kid
    alt Key present in cache
        Cache-->>RS: Trusted public key
        RS->>RS: Verify signature + iss/aud/exp
        RS-->>C: Process request
    else Key missing / refresh needed
        RS->>AS: GET JWKS
        alt Identity Provider online
            AS-->>RS: Fresh JWK Set
            RS->>RS: Verify signature + claims
            RS-->>C: Process request if valid
        else Identity Provider offline
            AS--xRS: Timeout / connection error
            RS-->>C: Authentication failure
        end
    end
~~~

### 2.1. Issuer Validation Is a Local Check

The issuer validator compares the JWT's `iss` claim against the configured trusted issuer. Once the JWT and public key are present, this comparison does not call the issuer endpoint again.

Example:

~~~java
OAuth2TokenValidator<Jwt> issuerValidator =
        new JwtIssuerValidator(
            "https://identity.example.test/realms/shop");
~~~

This validator does not prove the issuer is online; it verifies the token claims to be issued by the exact configured issuer. The signature must still verify against a trusted key.

### 2.2. Audience and Expiration Must Still Be Checked

An outage does not change the token contract. The Resource Server must still check:

- `aud` includes the current resource server.
- `exp` has not passed, accounting for configured clock skew.
- `nbf` has been reached.
- Signature verifies against a trusted key.
- Scopes/authorities suffice for the endpoint.
- Token profile and required claims satisfy policy.

Never drop issuer/audience validators or extend lifetimes just because the IdP is temporarily unavailable.

### 2.3. When Is the JWKS Endpoint Actually Called?

The Resource Server does not need to fetch JWKS on every request. The decoder usually uses a fetched/cached JWK Set to pick keys by `kid`. Fetches/refreshes can occur when:

- The decoder needs to load the key set initially.
- A token carries a `kid` missing from the current key set.
- The cache expires or refresh mechanisms require reloading.
- The application creates a new decoder or context.

Exact caching and refresh behavior depend on the Spring Security version, Nimbus JOSE, and configured cache. During drills, observe actual requests hitting the JWKS endpoint rather than inferring from API request counts.

### 2.4. Tokens Signed with an Older Key Can Still Be Valid

If the JWKS cache holds public key A and a token was signed with private key A, the Resource Server can keep verifying tokens while the JWKS server is offline. This holds only when:

- The cache still holds key A.
- The token has not expired and all other claims remain valid.
- Policy allows continuing to use loaded keys.
- There is no immediate revocation requirement or online denylist.

This is an intentional availability trade-off of JWTs. It is not an instant revocation mechanism.

### 2.5. Tokens with a New `kid` While JWKS Is Offline

If the Authorization Server has begun signing tokens with key B while the Resource Server holds only key A, the decoder must locate key B. While the JWKS endpoint is offline, the decoder has no basis to trust key B and must reject those tokens.

Never accept a token simply because:

- Claims look plausible.
- `iss` matches.
- `sub` is present.
- Another key from the same issuer is cached.

Key selection and signature verification are mandatory. Never fall back to "any public key" or disable signature checks.

## 3. Opaque Token Model During Issuer Downtime

An opaque token does not provide a signed set of claims for the Resource Server to verify on its own like a JWT. The Resource Server calls the introspection endpoint and relies on the Authorization Server's response.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant RS as Resource Server
    participant AS as Introspection endpoint

    C->>RS: Bearer opaque-token
    RS->>AS: POST /introspect
    alt AS returns active=true
        AS-->>RS: active + scope + claims
        RS->>RS: Build Authentication and authorize
        RS-->>C: Process request if permitted
    else AS returns active=false
        AS-->>RS: active=false
        RS-->>C: 401 Unauthorized
    else AS offline
        AS--xRS: Timeout / connection error
        RS-->>C: Cannot verify token
    end
~~~

### 3.1. Opaque Tokens Cannot Be Verified from the Token String Alone

If the introspection endpoint does not reply, the Resource Server does not know whether the token is active, revoked, expired, or scoped for this resource. Thus the safe default is failing closed: protected requests must not authenticate.

An introspection cache reduces direct dependency, but creates a window where the Resource Server keeps trusting stale results after token revocation. Choose TTLs based on revocation requirements and your threat model.

### 3.2. Introspection Caching Is a Security Decision

If `active=true` responses are cached for 60 seconds, a token revoked right after cache insertion may remain accepted for the rest of the TTL. The longer the TTL:

- Better availability during IdP downtime.
- Fewer introspection calls.
- Slower revocation visibility.

Never turn on caching hastily to "fix an outage". Document TTL, cache keys, stored claims, eviction policy, and how inactive tokens are handled. Never cache by unprotected token strings in logs or metrics.

### 3.3. Do Not Apply JWT Cache Policies to Opaque Tokens

A JWKS cache stores public keys used to verify signatures; an introspection cache stores token state and permissions. The two cache types carry different meanings and risks:

| Property | JWKS cache | Introspection cache |
| --- | --- | --- |
| Data | Public JWK Set | Token status and claims |
| Lookup key | JWKS URI/issuer | Token identity or secure hash |
| Used to | Verify signatures | Decide whether token is active |
| Risk when stale | Missing new key or retaining old key | Revoked tokens still treated as active |
| Refresh trigger | TTL, unknown `kid`, cache policy | TTL, request, explicit invalidation |

## 4. Configuring to Reduce Startup Discovery Dependency

In a JWT Resource Server, configuring `issuer-uri` lets Spring Security identify the issuer and run metadata discovery to locate the JWKS URI. Depending on initialization/context wiring, discovery may run when the decoder bean is created, tying application startup to the metadata endpoint.

If you want the Resource Server to know the JWKS URI directly without needing metadata discovery to locate keys, configure both issuer and JWK Set URI:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/shop
          jwk-set-uri: https://identity.example.test/realms/shop/protocol/openid-connect/certs
~~~

With this configuration:

- `jwk-set-uri` explicitly specifies where to fetch the JWK Set.
- `issuer-uri` still supplies the issuer to validate the `iss` claim.
- The decoder does not need discovery metadata solely to locate the JWKS URI.
- Missing keys still require reaching the JWKS endpoint.

This removes one bootstrap dependency without making a JWT Resource Server completely independent of the identity provider in all scenarios.

### 4.1. Direct JWKS URI Does Not Skip Signature Verification

Do not confuse configuring a direct URI with trusting tokens unverified. The decoder still must fetch public JWKs from the trusted URI, select keys matching the JOSE header/`kid`, verify signatures and allowed algorithms, and run issuer/time/audience/custom validators.

Never pull `jwk-set-uri` from request parameters, JWT payloads, or any caller-controlled source.

### 4.2. Distinguish Startup from the First Authenticated Request

Depending on decoder construction and framework lifecycle, HTTP metadata/JWKS fetches can happen at initialization or on the first decode. Tests must record accurately:

- Does the application bind its port and boot while the metadata server is offline?
- Does the context initialize while the JWKS server is offline?
- What does the first protected request with an uncached key return?
- Do requests after keys are cached keep verifying while the JWKS server is offline?

Do not assert `ApplicationContext` startup succeeded and conclude the Resource Server can verify all tokens. Startup, readiness, and token-verification capability are three distinct conditions.

## 5. Phased Outage Drills

A valuable drill alters the exact dependency, sends controlled requests, and records outcomes. Do not simply stop the IdP and stare at an overview dashboard.

### 5.1. Pre-Drill Preparation

Document:

- Token type in use: JWT or opaque.
- Issuer, audience, JWKS URI, or introspection URI.
- How decoders/introspectors are constructed and when remote calls occur.
- JWKS/introspection cache implementation, TTL, and eviction.
- Token lifetimes, clock skew, and key rotation schedules.
- HTTP connect/read timeouts, retry policies, and circuit breakers.
- Liveness/readiness policies and how the load balancer drains instances.
- Baseline latency, error rates, request rates, and IdP call counts.

Prepare dedicated token fixtures:

| Fixture | Purpose |
| --- | --- |
| JWT-A | Signed with key A already published and loaded by the Resource Server |
| JWT-B | Signed with key B to test unknown `kid`/rotation |
| JWT-expired | Verify expired tokens are still rejected |
| JWT-wrong-audience | Verify audience validation is not dropped |
| Opaque-active | Introspection returns active |
| Opaque-revoked | Introspection returns inactive |
| Opaque-unknown | Token absent from the test IdP registry |

Never use production tokens or real user accounts for drills.

### 5.2. Scenario A — Metadata Endpoint Offline Before Startup

Goal: determine whether the application requires metadata discovery to build its decoder.

Steps:

1. Block the test IdP's metadata endpoint.
2. Start the application with the current configuration.
3. Record whether the Spring `ApplicationContext` initializes cleanly.
4. If the context fails to boot, try direct JWKS URI configuration alongside issuer validation.
5. Restart with metadata still offline.
6. Record app startup, readiness, and the first protected request.

Classify results:

| Configuration | Expected Outcome to Verify |
| --- | --- |
| `issuer-uri` using discovery | Startup/decoder init may require metadata depending on initialization style |
| `issuer-uri` + `jwk-set-uri` | May skip discovery for locating JWKS; key fetch still needs JWKS endpoint |
| Direct `jwk-set-uri`, explicit issuer validator | No metadata discovery needed; key and issuer validation still required |

Do not generalize one framework version/configuration's behavior to all applications. Test the exact dependency versions and bean lifecycle you run.

### 5.3. Scenario B — JWKS Offline After Keys Are Loaded

Goal: determine whether the Resource Server can keep verifying JWTs using cached keys.

Steps:

1. Bring metadata/JWKS endpoints online.
2. Send JWT-A to force the decoder to fetch key A.
3. Confirm the request succeeds and the JWKS request occurred.
4. Block the JWKS endpoint while leaving metadata offline or irrelevant.
5. Re-send JWT-A repeatedly over a short interval.
6. Observe success rate, latency, and JWKS refresh attempts.
7. Send JWT-expired and JWT-wrong-audience to verify validators still enforce policy.

Expected: while the decoder holds valid key A in cache and the token is unexpired, JWT-A continues to be accepted. Expired and wrong-audience tokens remain rejected. Outages must not weaken validators.

### 5.4. Scenario C — JWKS Offline When Encountering a New Key

Goal: verify safe behavior if the IdP rotates keys while JWKS is unreachable.

Steps:

1. Have the Resource Server cache only public key A.
2. Have the test IdP begin signing JWT-B with key B, `kid=B`.
3. Block the JWKS endpoint before the Resource Server fetches B.
4. Send JWT-B.
5. Record whether the decoder attempts a JWKS refresh and rejects the request.
6. Re-open JWKS with keys A + B.
7. Re-send JWT-B after the decoder can fetch the new key.

Expected: JWT-B must never be accepted while the Resource Server lacks trusted key B. Once JWKS recovers and the decoder fetches B, the token verifies if claims are valid.

### 5.5. Scenario D — Introspection Endpoint Offline

Goal: quantify IdP impact on opaque-token traffic.

Steps:

1. Confirm Opaque-active is accepted while the introspection server is online.
2. Block the introspection endpoint.
3. Re-send Opaque-active.
4. Send Opaque-revoked and Opaque-unknown.
5. Observe timeouts, status codes, latency, and introspection call counts.
6. Re-open the endpoint and verify traffic recovers.

Without caching: protected requests needing introspection fail while the endpoint is offline. With caching: outcomes depend on remaining entry TTL. Measure and document the exact staleness window rather than merely noting "opaque tokens kept working".

### 5.6. Scenario E — IdP Outage Longer Than Access Token Lifetime

Goal: identify when JWT traffic begins failing naturally.

1. Warm JWKS cache with key A.
2. Disable metadata/JWKS endpoints.
3. Send JWT-A continuously until it expires.
4. Confirm the expired token is rejected even though its signature stays valid.
5. Never extend `exp`, widen clock skew, or remove timestamp validators.
6. Restore the IdP and verify service recovery.

Offline JWT verification does not let tokens live past `exp`. If an outage outlasts token lifetimes, clients cannot obtain fresh tokens and requests eventually fail.

### 5.7. Scenario F — Restarting a Resource Server During an IdP Outage

Goal: contrast availability of running instances with freshly booted instances.

1. Let the Resource Server load key A.
2. Block metadata/JWKS.
3. Restart one instance.
4. Send JWT-A to both the old instance and the new instance.
5. Compare behaviors.

The older instance may still hold JWKS in memory; the new instance typically lacks that cache and cannot verify tokens if it needs to fetch keys while the IdP is offline. If a persistent cache is used, test its integrity, freshness, and lifecycle. Never assume restarts are transparent.

### 5.8. Scenario G — Post-Outage Recovery

1. Restore metadata/JWKS/introspection endpoints.
2. Verify DNS/TLS and health checks.
3. Send valid tokens signed with the current key.
4. Verify an unknown `kid` triggers a JWKS refresh.
5. Send an active opaque token to verify introspection works.
6. Watch retries/circuit breakers return to normal state.
7. Confirm no backlog or threads remain stuck on long timeouts.

Do not stop at seeing the IdP endpoint return HTTP 200; confirm the Resource Server actually uses the dependency and serves valid requests.

## 6. Expected Behavior Matrix During IdP Downtime

| Case | JWT, Key Cached | JWT, Key Unknown | Opaque, Uncached | Opaque, Cached Active Within TTL |
| --- | --- | --- | --- | --- |
| IdP metadata offline | May pass | Unaffected if JWKS URI known and key cached | Introspection still relies on its own endpoint | Relies on introspection cache |
| JWKS offline | May pass until cache/TTL policy forces refresh | Fail closed | Not directly involved | Not directly involved |
| Introspection offline | Not directly involved | Not directly involved | Fail closed | May pass within TTL |
| Expired token | Fail | Fail | Introspection should return inactive | Cache entry must not outlive `exp` |
| Wrong issuer | Fails local validator | Fails local validator | Fails if contract wrapper validates issuer | Cache must not bypass policy |
| Wrong audience | Fails local validator | Fails local validator | Fails if contract requires audience validation | Cache must not bypass policy |
| Signing key removed | Cached key may remain usable per cache policy | Cannot fetch new key while offline | Irrelevant | Irrelevant |

"May pass" cells are not universal guarantees for every implementation. Verify your application's actual cache behavior and policy.

## 7. Timeouts, Retries, and Circuit Breakers

During IdP downtime, the operational hazard is not just 401s. Hanging HTTP calls can tie up servlet threads, connection pools, and request slots, degrading the service even while local JWT handling remains healthy.

### 7.1. Set Finite Timeouts on Remote Identity Calls

Split timeouts by dependency type:

| Dependency | Call Type | Optimization Target |
| --- | --- | --- |
| Metadata discovery | GET, typically bootstrap | Bounded startup and clear error reporting |
| JWKS fetch/refresh | GET, when key needed | Do not stall requests long when key is absent |
| Introspection | POST on request path | Low latency, short bounded timeouts |
| IdP health probe | GET/HEAD or dedicated probe | Avoid heavy load; never tie liveness to IdP |

Connect timeouts bound establishing the connection; read/response timeouts bound waiting for data. Also inspect DNS resolution, TLS handshakes, and connection pool acquisition, as they can stall requests too.

Illustrative policy example:

~~~text
connect timeout: 500 ms
response timeout: 1.5 s
max attempts: 1 or 2 for transient failures
overall protected request budget: 2 s
~~~

These are not universal defaults. Pick values from your latency budget and SLA. Never set an introspection timeout longer than the client or load balancer is willing to wait.

### 7.2. Retry Only Transient Errors

Retries can help a JWKS GET that hits a connection reset or brief 503. However, retries cannot fix:

- `invalid_token` or inactive tokens.
- `invalid_client` from bad credentials.
- `invalid_scope` or policy denials.
- Audience/issuer mismatches.
- Keys absent from JWKS.

Never retry unboundedly or synchronously multiple times per request. If 1,000 concurrent requests need a new key, un-jittered retries can slam the IdP the moment it recovers.

### 7.3. Single-Flight for JWKS Refreshes

When many concurrent requests encounter an unknown `kid`, the decoder/cache should avoid letting all of them download JWKS at once. Check whether your library and cache coalesce refreshes. If not, consider a single-flight or rate-limited refresh layer.

Never fall back to a different public key just to cut refreshes. If the new key has not been fetched, tokens needing it cannot be verified yet.

### 7.4. Circuit Breakers for Introspection

A circuit breaker stops calling a repeatedly failing introspection endpoint, protecting thread/connection pools and shielding the IdP during recovery. When the circuit is open:

- No valid cache entry: reject protected requests.
- Active cache entry within TTL: use only per published cache policy.
- Expired cache entry: never treat stale results as active.
- Circuit half-open: allow a small probe volume to check recovery.

A circuit breaker is not a mechanism to accept all tokens during an outage. It only governs how the dependency is called and how errors surface.

### 7.5. Circuit Breakers for JWKS

JWKS fetches happen far less often than introspection. Timeouts, bounded retries, and caching cover most cases; a circuit breaker helps when unknown `kid`s or refreshes trigger bursts of failing calls. Still, whenever the needed key is absent, there is no valid fallback to verify signatures.

Never configure a circuit breaker in a way that causes the decoder to accept tokens with unverified keys. Failing closed is the right behavior for tokens needing missing keys.

### 7.6. Backoff and Jitter

If retrying transient metadata/JWKS/introspection errors:

- Use exponential backoff with a maximum cap.
- Add jitter so instances do not retry in lockstep.
- Cap total retry time within the request/startup budget.
- Never retry 4xx policy or credential errors.
- Emit metrics for retry counts and circuit state.

When the IdP recovers, avoid having every instance hammer JWKS or health checks together.

## 8. Readiness, Liveness, and Degraded Mode

One critical operational decision is whether an IdP outage should pull instances out of the load balancer.

### 8.1. Liveness Should Not Depend Directly on the IdP

Liveness answers: **is the process alive and able to make progress?** If the IdP is offline while the JVM, servlet container, and application threads remain healthy, liveness should normally keep passing.

If liveness calls the IdP and fails during an IdP outage, the orchestrator may restart every instance repeatedly. That wipes still-useful JWKS caches, increases startup pressure, and complicates recovery.

### 8.2. Readiness Depends on Ability to Serve per Contract

Readiness answers: **should this instance receive new traffic?** There is no single answer for every token type:

- A JWT Resource Server with cached keys can keep serving valid requests even while JWKS is offline.
- A freshly started JWT Resource Server lacking keys while JWKS is unreachable cannot verify protected traffic yet.
- An uncached opaque Resource Server cannot serve protected traffic while introspection is offline.
- Public/health endpoints may stay operational while protected endpoints degrade.

Use a separate dependency status or health group to observe the IdP. Before flipping readiness to DOWN, weigh load-balancer effects: pulling all instances can kill public endpoints and JWT requests that could still verify locally.

### 8.3. Do Not Let Readiness Trigger Restart Loops

Distinguish:

- **Liveness:** is the process healthy; independent of the IdP.
- **Readiness:** which traffic classes can this instance serve; policy must match real behavior.
- **Dependency health:** are metadata/JWKS/introspection reachable.
- **Functional probe:** can a test token or internal request verify per policy.

Do not cram all of these into one single health check. When marking degraded state, expose clear status and route traffic according to actual capability rather than restarting processes over a transient external dependency outage.

### 8.4. Probes Must Not Generate Real Token Traffic

Health checks should never mint fresh production access tokens or continuously call introspection with user tokens. Use dedicated health endpoints, rate-limited probes, or metrics from real traffic. If a probe checks JWKS, account for caching and IdP load.

## 9. Identifying Which Dependencies Remain Required

After the drill, compile an observation-based table. Assign every dependency to one of these groups:

1. **Bootstrap dependency:** needed to configure/initialize decoders or the application context.
2. **On-demand runtime dependency:** needed only on cache misses, unknown keys, or refreshes.
3. **Per-request dependency:** sits on the request path, such as uncached introspection.
4. **Optional/other-role dependency:** needed for OAuth2 Client, login, UserInfo, or logout, but not by the Resource Server to verify tokens.
5. **Infrastructure dependency:** DNS, TLS, clocks, network, caches/storage.

### 9.1. Dependency Matrix

| Dependency | JWT with Issuer Discovery | JWT with Direct JWKS URI | Opaque Token |
| --- | --- | --- | --- |
| OIDC/OAuth metadata | Bootstrap/discovery if used | Not needed to locate JWKS | Not needed for introspection if URI configured directly |
| JWKS | Needed for key load/refresh | Needed for key load/refresh | Unused |
| Introspection | Unused in pure JWT flow | Unused in pure JWT flow | Needed on request path unless cached |
| Token endpoint | Not needed for validation | Not needed for validation | Not needed for validation |
| Authorization endpoint | Not needed for validation | Not needed for validation | Not needed for validation |
| UserInfo | Only if app calls it for profiles | Only if app calls it for profiles | Only if app calls it separately |
| Revocation endpoint | Not automatically called by Resource Server | Not automatically called by Resource Server | Does not automatically replace introspection |
| Clock/NTP | Needed | Needed | Needed if response claims carry `exp` or policy uses time |
| DNS/TLS/network | Needed for remote fetches | Needed for remote fetches | Needed for introspection |

### 9.2. Discovering Real Dependencies Through Observation

Do not rely solely on property names or generic docs. Use a drill to record:

- Outbound HTTP requests by host/path/method.
- Timing of requests: startup, first token, refresh, or every request.
- Cache hits/misses and remaining TTL.
- Request latency and error classes.
- Connections/threads waiting on dependencies.
- Behavior when dependencies go offline and when they recover.

Instrument HTTP clients, MockWebServer/WireMock request recorders, or tracing spans. Never record access tokens, client secrets, or `Authorization` headers in traces.

### 9.3. Questions to Decide Whether a Dependency Is Still Required

For each endpoint, ask:

- If the endpoint is offline at process startup, does the application context boot?
- If the endpoint goes offline after keys are cached, do valid JWT requests keep succeeding?
- When cache TTL expires or a new key appears, how does the service behave?
- Is the endpoint called on every request or only on cache misses?
- Does the endpoint serve the Resource Server or a different application role?
- Can the URI be configured directly while retaining issuer validation?
- Does an instant-revocation requirement forbid caching or stale use?

Record findings as a dependency map, for example:

~~~text
JWT validation:
  metadata: bootstrap only (or not used with direct JWKS URI)
  JWKS: on cache miss / refresh
  issuer/audience/time: local validation
  token endpoint: not required

Opaque validation:
  introspection: per request unless bounded cache is enabled
  token endpoint: not required for validation
  metadata: not required when introspection URI is configured directly
~~~

## 10. Metrics and Logging for Outage Drills

A drill is only useful if you can distinguish authentication failures from dependency failures. HTTP 401 alone does not tell you whether a token is bad or the IdP is unreachable.

### 10.1. Metrics to Track

| Metric | Meaning |
| --- | --- |
| `resource_server_authentication_success_total` | Successful authentications |
| `resource_server_authentication_failure_total` | Failed authentications, grouped by error type |
| `jwks_fetch_total` | JWK Set fetch/refresh count |
| `jwks_fetch_duration` | JWKS fetch latency |
| `jwks_cache_hit_total` / `jwks_cache_miss_total` | Key cache effectiveness |
| `jwks_unknown_kid_total` | Tokens arriving with unknown key IDs |
| `introspection_request_total` | Introspection request count |
| `introspection_duration` | Introspection latency |
| `introspection_failure_total` | Transport/protocol/client-auth failures |
| `introspection_inactive_total` | AS confirmed token inactive |
| `introspection_cache_hit_total` | Cache hits if introspection caching is enabled |
| `identity_dependency_circuit_state` | Circuit breaker state |
| `identity_dependency_timeout_total` | Timeouts per dependency |

These metric names are instrumentation suggestions for your app; not all are emitted by Spring Security out of the box. Emit them via Micrometer interceptors, observation conventions, or decoder/introspector wrappers.

### 10.2. Classifying Errors

Distinguish at least:

- Invalid signature or missing key.
- Issuer/audience/time/token-profile validation failure.
- Inactive opaque token.
- Introspection endpoint timeout/5xx.
- JWKS/metadata fetch timeout/5xx.
- Client authentication failure against the introspection endpoint.
- Local authorization denial due to missing scope/role.

Never put token values, sensitive subjects, client secrets, or `Authorization` headers into metric tags. Keep tag cardinality low; never use tokens, user IDs, or request IDs as labels.

### 10.3. Logging and Tracing

Logs may include the dependency name and configured endpoint path, HTTP status/error category, elapsed time and retry count, cache hits/misses, decoder/introspector state, and correlation or trace IDs.

Never log raw JWT/opaque tokens, `Authorization` headers, introspection request bodies containing tokens, client secrets, private keys, or Basic Authorization values.

When tracing outbound identity requests, redact headers and bodies at the instrumentation layer. Outage tests must never emit logs containing real test fixture tokens.

## 11. Runbook When the Issuer Goes Down

A runbook should guide operators from symptoms to verifiable actions. Suggested sequence:

### Step 1 — Identify the Failing Dependency

Check metadata, JWKS, and introspection separately. Identify which endpoint is timing out, returning 5xx, or refusing connections, and when it started.

### Step 2 — Identify Token Type and Verification Path

- JWT: does the Resource Server hold a cached key for the current `kid`?
- Opaque: is introspection called on every request? Is caching enabled?
- Is any app acting as both Resource Server and OAuth2 Client and relying on the token endpoint for separate outbound calls?

### Step 3 — Verify Tokens Remain Valid

Confirm signature, issuer, audience, `exp`, `nbf`, scopes, and key trust. Never widen clock skew or relax validators mid-outage to make requests pass.

### Step 4 — Assess Blast Radius

Distinguish older instances with cached JWKS from new instances lacking keys; cached-key JWTs from new-`kid` JWTs; opaque tokens with valid cached active entries from uncached tokens; public endpoints from protected endpoints; and Resource Server validation from outbound OAuth2 Client flows.

### Step 5 — Protect the Service

- Keep finite timeouts.
- Cap retries and engage circuit breakers per policy.
- Do not restart all instances simply because of an IdP outage.
- Never disable authentication or authorization.
- Keep caches within their designed lifecycles; do not flush still-useful key caches without reason.

### Step 6 — Restore the Dependency

Restore DNS/network/TLS or the IdP endpoint. Verify metadata/JWKS/introspection honor their contracts. Send a valid test token and confirm the Resource Server recovers.

### Step 7 — Confirm System Stability

Monitor error rates, latency, JWKS refreshes, introspection calls, circuit state, and thread/connection pools. Verify no retry storm appears once the IdP recovers.

## 12. Scope and Limits of Degraded Mode

Degraded mode must be defined upfront. Never improvise a generic fallback mid-outage.

### 12.1. JWTs with Cached Keys

Degraded mode may keep verifying tokens with trusted cached keys, provided it still:

- Verifies signatures.
- Validates issuer/audience/timestamps.
- Enforces scopes/roles and business authorization.
- Rejects tokens requiring uncached keys.
- Rejects expired tokens.

If the system needs near-real-time revocation, local JWT validation alone cannot satisfy that requirement without an online denylist or introspection. Capture that architectural trade-off in your threat model.

### 12.2. Opaque Tokens with Caching

If introspection caching is permitted:

- TTL must be bounded and short per revocation requirements.
- Never use expired-TTL entries during an outage.
- Cache keys must never expose tokens.
- Inactive responses must be handled consistently.
- Support invalidation on revocation events if the architecture allows.

Without a valid cache entry, an introspection outage causes protected requests to fail. Never construct a fallback authenticated principal from the raw token string.

### 12.3. Never Fall Back from Delegated Identity to Service Identity

An application acting as both Resource Server and OAuth2 Client may call downstream services using Client Credentials. However, if the inbound user token cannot be verified, never switch to a service token to perform the action on the user's behalf.

A service token represents the application, not the user. Using it to complete user actions during an outage can bypass authorization boundaries and cause confused-deputy vulnerabilities.

### 12.4. Never Lower Security Standards to Maintain Availability

Prohibited fallbacks:

- Skipping signature validation.
- Accepting arbitrary issuers or audiences.
- Accepting JWTs with an unfound `kid`.
- Skipping timestamp validation.
- Treating introspection timeouts as `active=true`.
- Accepting expired tokens because the IdP cannot issue fresh ones.
- Elevating scopes/roles or switching to a broad-privilege service token.
- Using metadata/JWKS URLs supplied by the caller.

## 13. Outage Drill Success Criteria

A drill is complete only when evidence answers every question:

| Question | Evidence |
| --- | --- |
| Is metadata a startup dependency? | Startup traces/logs and outbound request records with metadata offline |
| Do cached JWT keys work while JWKS is offline? | Valid JWT passes, expired/wrong-audience still fail, JWKS call count |
| How are new JWT keys handled while JWKS is offline? | Unknown-`kid` token rejected; once JWKS recovers, valid token accepted |
| How are opaque tokens handled while introspection is offline? | Active/inactive fixtures, cache hits/misses, and response codes |
| How do restarts affect caches? | Comparison of old vs. new instances during the same outage |
| Do timeouts protect thread/connection pools? | Latency, active threads, pending connections, and timeout metrics |
| Do readiness/liveness react properly? | Probe outcomes and orchestrator/load-balancer behavior |
| Does recovery avoid retry storms? | Retry rates, circuit states, JWKS/introspection request volume |
| Which dependencies remain truly required? | Dependency map classified by bootstrap/on-demand/per-request/optional |

Never mark an "outage drill passed" just because one request returned 200. Test valid tokens, invalid tokens, expired tokens, new keys, and introspection failures.

## 14. Practical Scenarios

**A.** The metadata endpoint is offline, yet JWT-A was verified earlier and its public key remains cached. Can requests keep processing?

Yes, if the decoder still holds the trusted key, the token is unexpired, and all validators still execute. Metadata does not need to be called again for every JWT.

**B.** JWKS is offline and JWT-B carries a never-seen `kid`. Can we try verifying with key A?

No. Key A cannot verify token B's signature unless token B was actually signed with the matching private key. If no trusted key is found, fail closed.

**C.** Opaque token introspection times out. Can we assume the token is still active because the previous request succeeded?

Only if an explicitly designed introspection cache permits using an active result still within its TTL. Without a valid cache entry, reject the request.

**D.** The app restarts during an outage and loses its in-memory JWKS cache. Why does the new instance fail while the older instance still passes?

The older instance still holds the downloaded public key; the new instance needs to fetch the key while JWKS is offline. This is a lifecycle/cache difference, not a validator bug.

**E.** A token is still unexpired, yet its key was removed from JWKS. Must a Resource Server caching the old key reject it immediately?

That depends on cache refresh/rotation policy and revocation requirements. Normal JWKS rotation uses an overlap window; emergency key revocation requires an explicit policy and change-distribution mechanism. Never assume all instances receive updates simultaneously.

**F.** A liveness probe calls the metadata endpoint and fails during IdP downtime, causing the orchestrator to restart every instance. Should this stay?

No. Liveness should check internal process health. Observe dependency health separately; restart loops wipe still-useful key caches and worsen outages.

**G.** The introspection circuit breaker opens. Should we return 200 to preserve availability?

No. Without a policy-valid cached active entry, protected requests cannot be authenticated. Circuit breakers only stop repeated calls to a failing dependency.

**H.** The IdP recovered, yet traffic still fails due to the circuit breaker. What should be checked?

Check half-open probes, reset/transition policies, DNS/TLS, client authentication, and response contracts. Confirm the circuit closes after the dependency recovers.

**I.** Does a JWT Resource Server need an active token endpoint to verify access tokens?

No. The token endpoint issues tokens to clients. A JWT Resource Server verifies using public keys and claims; JWKS/metadata may be separate dependencies.

**J.** Can we use a service Client Credentials token to complete a user's request when the inbound token cannot be verified?

No. A service token carries application identity, not user delegation. Never use it to bypass user authorization.

## 15. Operations Checklist

### Before the Drill

- [ ] Finalize scope, environment, timing, and coordinator.
- [ ] Define rollback/abort conditions and dependency restoration steps.
- [ ] Use dedicated test tokens, keys, and accounts.
- [ ] Record token lifetimes, issuer, audience, and JWKS/introspection URIs.
- [ ] Record cache, timeout, retry, circuit breaker, and probe policies.
- [ ] Ensure baseline metrics and traces are ready.

### During the Drill

- [ ] Block each dependency individually: metadata, JWKS, introspection.
- [ ] Test startup and the first authenticated request.
- [ ] Test JWT cached keys, unknown `kid`, expired tokens, and wrong audiences.
- [ ] Test opaque active/inactive tokens and introspection timeouts.
- [ ] Test instance restarts during the outage.
- [ ] Monitor liveness/readiness, threads, connections, latency, and error rates.
- [ ] Never drop validators or enable unsafe fallbacks.

### After the Drill

- [ ] Restore the IdP and confirm Resource Server recovery.
- [ ] Confirm no retry storms or backlogs remain.
- [ ] Produce a dependency map split by bootstrap/on-demand/per-request/optional.
- [ ] Document degraded-mode behavior and stale/cache windows.
- [ ] Document needed config, alert, runbook, or architecture updates.
- [ ] Re-run scenarios after changes to confirm outcomes.

---

## Conclusion

Issuer outage drills reveal exactly when a Resource Server depends on metadata, JWKS, and introspection. With JWTs, issuer/audience/time checks are local; cached public keys can keep the service verifying tokens during brief metadata/JWKS outages. Tokens carrying a new `kid` or instances lacking keys still need JWKS. With opaque tokens, introspection usually sits on the request path; when the endpoint goes offline, protected requests must fail closed unless a TTL-bounded active cache with accepted revocation lag is in place.

Safe operations require finite timeouts, retries with backoff/jitter, circuit breakers that never bypass authentication, IdP-independent liveness, and readiness reflecting real serving capability. After the drill, classify every endpoint as bootstrap, on-demand runtime, per-request, optional for another role, or infrastructure dependency. Evidence from request traces, cache metrics, startup behavior, and restart tests shows which dependencies remain essential and which degraded modes are acceptable.

## References

1. [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
2. [Spring Security — Minimal Dependencies for JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html#oauth2resourceserver-jwt-minimaldependencies)
3. [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
4. [Spring Boot — Actuator Endpoints and Health Groups](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
5. [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414.html)
6. [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517.html)
7. [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html)
8. [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519.html)
9. [Resilience4j — CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker)
