# Comparing JWT and Opaque Tokens by Latency, Network Dependency, and Revocation in Spring Security Reactive

## 1. Problem to Solve

An API built with **Spring WebFlux** receives `Authorization: Bearer ...` from a mobile app, frontend, or another service. The identity system supports two options:

- **Self-verified JWT access token at the resource server:** the API uses the issuer's public keys/JWKS to verify the signature and claims; it does not need to query the Authorization Server on **every** normal request.
- **Opaque access token verified via introspection:** the API sends the token to the Authorization Server per **RFC 7662**, receives `active` and metadata, and then decides authentication/authorization.

Merely saying "JWT is fast, opaque is easy to revoke" is not enough for design. In practice, you must examine **endpoint P95/P99**, **introspection RTT**, **JWKS cache misses**, **IdP rate limits**, **revocation propagation delay**, **cache TTL**, and operations requiring permissions to take effect immediately.

After this lesson, you can:

1. Diagram the critical path for each verification style and separate **token verification cost** from the network latency of calling business APIs.
2. Calculate introspection load, average latency by cache hit rate, and concurrent in-flight requests using verifiable assumptions.
3. Explain why **JWTs are not strictly network-free** and **cached opaque tokens are not strictly instant-revocation**.
4. Estimate the **revocation exposure window** when locking an account or revoking a token.
5. Configure Spring Security **reactive resource server** properly with `ReactiveJwtDecoder` or `ReactiveOpaqueTokenIntrospector` and scope rules.
6. Design canary experiments and chaos tests to select a token strategy based on **SLOs**, revocation requirements, and IdP reliability.
7. Run a standalone **Java 17+ program** simulating latency/QPS/revocation to understand trade-offs, alongside a Spring Boot WebFlux example capable of connecting to a real IdP.
8. Identify anti-patterns: decoding JWTs without verification, fail-open introspection, caching `active=true` for the token's entire lifetime, and infinite retries when the IdP fails.

**Scope:** this lesson compares **verification strategies** for access tokens at a Resource Server. It is not a lesson on minting JWTs, implementing OAuth2 Login, or storing `OAuth2AuthorizedClient` in an API-calling app. A token's format can be JWT while still being verified via introspection; be precise by distinguishing "JWT local verification" from "online introspection."

## 2. Format Axis vs. Verification Strategy Axis

**Bearer** per RFC 6750 is a way of presenting a credential in a header; **it does not specify whether the credential is a JWT or opaque**.

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer a7R-opaque-token-sample
~~~

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxIn0.sample-signature
~~~

Both are **illustrative strings**, not valid production tokens. A JWS Compact JWT typically has three parts **Base64URL(header).Base64URL(payload).Base64URL(signature)**; the payload **is readable**, not encrypted by default. An opaque token is typically a string that the Resource Server **does not decode to determine permissions**. Both are Bearer credentials: leaking a token risks replay.

| Question | What to Determine |
| --- | --- |
| What format is the token? | Random opaque string, JWT/JWS, or another format |
| Who does the Resource Server trust to verify? | Local crypto + trusted claims vs. Authorization Server via introspection |
| At request time, is an online revocation check required? | Yes, no, or only on specific actions |
| Which API was the token issued for? | `aud`, resource indicators, issuer, client/tenant |
| Which endpoints may the user call? | Scope/authority/role and business policies |

Spring Security WebFlux provides two adapters:

- `oauth2ResourceServer(o -> o.jwt(...))` uses **`ReactiveJwtDecoder`**, typically `NimbusReactiveJwtDecoder`.
- `oauth2ResourceServer(o -> o.opaqueToken(...))` uses **`ReactiveOpaqueTokenIntrospector`**, defaulting to HTTP introspection via `SpringReactiveOpaqueTokenIntrospector`.

If the Authorization Server issues a **JWT** yet the resource server uses `opaqueToken()` to query `active` status on every request, that architecture is **online introspection** and must not be counted as "network-free local JWT." Official Spring Security documentation supports this pattern.

## 3. Verification Critical Path: Before and After Caching

### 3.1. JWT Local Verification

~~~text
Client                  WebFlux Resource Server               Authorization Server
  |                              |                                     |
  | GET /api/orders + Bearer JWT |                                     |
  |----------------------------->|                                     |
  |                         read JWS header/payload                    |
  |                         find trusted signing key                   |
  |                              |                                     |
  |                     cache hit: key available                       |
  |                              |                                     |
  |                     verify signature                               |
  |                     validate iss/exp/nbf/aud                       |
  |                     map scope -> SCOPE_*                           |
  |                     authorize + business                           |
  |<---------------------- 200 / 401 / 403                             |
  |                              |                                     |
  |         cache miss/unknown kid ---> metadata/JWKS fetch ---------->|
  |                              |<------ key material ----------------|
~~~

The **warm path** (trusted verification keys already cached) does not need to send tokens to the IdP. However, the **cold path**, unseen `kid`, key rotation, metadata discovery, or cache expiry can trigger HTTP calls to the issuer/JWKS endpoint. Thus "JWT is always offline" is an overstatement.

**Local validation is still mandatory on every request**: check signature/allowed JWS algorithms, `exp`, `nbf`, `iss`, `aud`, tenant/client, and scopes. Never merely Base64URL-decode the payload and trust `roles`. When a token is revoked at the IdP while its signature remains valid and `exp` has not passed, a local validator **cannot know** about the revocation without an extra revocation-check layer.

### 3.2. Opaque Introspection

~~~text
Client                  WebFlux Resource Server               Authorization Server
  |                              |                                     |
  | GET /api/orders              |                                     |
  | Authorization: Bearer random-string                                |
  |----------------------------->|                                     |
  |                       ReactiveOpaqueTokenIntrospector              |
  |                              | HTTPS POST /introspect              |
  |                              | token=...                           |
  |                              | client authentication               |
  |                              |------------------------------------>|
  |                              |<----- active, scope, exp, aud ------|
  |                        check active and local API policy           |
  |                        map scopes -> SCOPE_*                       |
  |                        authorize + business                        |
  |<---------------------- 200 / 401 / 403                             |
~~~

Per RFC 7662, the Authorization Server returns JSON containing an **`active` boolean**. `active=false` typically indicates the token does not exist, has expired, was revoked, or violates the query policy. `active=true` is an online verification result under the Authorization Server's semantics; it **does not replace** the API's own scope, audience, tenant, and business authorization checks.

Without result caching, usually **every Bearer request** adds a network round trip and Authorization Server processing cost. Multiple requests from one client with the same token still trigger repeated introspection calls unless you implement caching or coalescing.

### 3.3. Do Not Confuse Network Hops

A request from a browser to a Resource Server always incurs network latency even with JWT. The fair comparison is:

~~~text
JWT warm:
client -> API -> local JWT verification -> business -> response

Opaque no-cache:
client -> API -> HTTPS introspection to IdP -> business -> response
                  ^ extra critical-path hop

JWT cold/JWKS miss:
client -> API -> JWKS fetch to IdP -> local verify -> business -> response
                  ^ occasional critical-path hop

Opaque cached:
client -> API -> cached introspection lookup -> business -> response
                  ^ extra hop avoided on cache hit; state may be stale
~~~

Never add browser->API network time to **only one** option; to compare latency, measure the exact same request path, business workload, client region, and load level.

## 4. Three-Way Comparison Table

| Criterion | JWT Local Signature Verification | Opaque + Uncached Introspection | Opaque + Cached Introspection |
| --- | --- | --- | --- |
| Extra call to IdP on warm request | Typically **0** | Typically **1** | 0 on hit, 1 on miss |
| CPU at API | Parse JWS, verify signature + claims | Parse introspection response + local policy | Cache lookup + local policy |
| Additional network RTT | None on warm path | Yes on critical path | Only on miss |
| Tail latency | Usually steadier on key cache hit | Depends on IdP/network tail | Bimodal distribution: hit/miss |
| QPS to IdP | Periodic JWKS/metadata, not 1:1 with requests | Roughly bearer QPS | Roughly miss QPS |
| Impact of IdP outage | Warm keys can keep verifying within policy/key-cache limits | Authentication usually fails | Hits use cache until TTL; misses fail closed |
| Revocation before `exp` | Unknown without online revocation | Visible once IdP updates state | Stale-positive window up to TTL |
| Token payload confidentiality | JWT JWS claims readable by bearer holder | Opaque string reveals no claims directly | Same for opaque string, though cache holds metadata |
| Horizontal API scaling | Easy to scale local verification | Scaling depends on IdP latency/capacity | Needs shared or local cache design |
| Scopes/roles after token issuance | Usually a snapshot in JWT | IdP can return updated metadata | May be stale up to cache TTL |
| Audience/issuer checking | JWT validators at API | Relies on IdP contract + API validator | Same as introspection, plus cache consistency checks |
| Determinism on disconnect | Depends on JWKS cache/key rotation | Usually denies when unable to introspect | Depends on hit/miss path and fail-closed policy |

Cells saying "typically" reflect common behavior, **not a library performance guarantee**. Real latency depends on signing algorithms, token sizes, JWKs/caches, the IdP database, networking, connection pools, GC, and concurrency.

## 5. How to Quantify Latency Without Inventing Benchmarks

### 5.1. Simple Budget Model

Let:

- `L_app`: business handler latency **excluding token verification**.
- `L_jwt`: local JWT verification on a key cache hit.
- `L_intro`: added overhead of calling introspection, including network RTT/TLS connection reuse, IdP processing, and response parsing/validation.
- `h`: introspection **cache hit** ratio, from 0 to 1.
- `λ`: Bearer requests/second on checked APIs.
- `T`: positive introspection cache TTL.
- `L_cache`: cache read cost (not necessarily zero).

Expected formulas for the **illustrative model**:

~~~text
JWT_warm_average       ≈ L_app + L_jwt
Opaque_no_cache_avg    ≈ L_app + L_intro
Opaque_cached_avg      ≈ L_app + h * L_cache + (1-h) * L_intro

Introspection_QPS_no_cache ≈ λ
Introspection_QPS_cached   ≈ λ * (1-h)

InFlight_introspection ≈ λ_miss * L_intro_seconds
~~~

The in-flight formula uses **Little's Law** and assumes steady arrival rates, no queue overload, and a consistent introspection latency definition. Production planning also needs baseline networking/application overhead, timeouts, concurrency caps, GC, and retries. Averages cannot predict **P95/P99**: at a 90% cache hit rate, the 10% taking the miss path can completely dominate P95/P99.

### 5.2. Numerical Example — All **Assumptions**, Not Measured Results

Assume:

| Variable | Simulated Value |
| --- | --- |
| `λ` | 1,200 protected requests/second |
| `L_app` | 5.0 ms |
| `L_jwt` | 0.7 ms |
| `L_intro` | 22.0 ms |
| `h` when caching opaque | 90% |
| `L_cache` | 0 ms to simplify formula; always > 0 in practice |
| `T` positive cache | 10 seconds |
| Remaining JWT `exp` lifetime | 300 seconds |

From that:

~~~text
JWT warm expected             = 5.0 + 0.7 = 5.7 ms
Opaque no cache expected      = 5.0 + 22.0 = 27.0 ms
Opaque 90% hit expected       = 5.0 + 0.1*22.0 = 7.2 ms

IdP calls/sec no cache        = 1200
IdP calls/sec with 90% hit    = 1200 * (1 - 0.90) = 120

In-flight no-cache expected   = 1200 * 0.022 = 26.4
In-flight cached expected     = 120  * 0.022 = 2.64
~~~

This does **not** prove real JWTs always take 0.7 ms, IdPs always take 22 ms, or cache hits are always 90%. Benchmark using **your own system's** tokens, JWS algorithms, IdP, and network. If introspection P99 is 300 ms, requests on the cache-miss path can suffer severe tail latency even when the mean looks great.

### 5.3. P50/P95/P99: Look at the Distribution, Not Just the Mean

With a 90% hit rate, if the 10% miss requests have far higher latency than hits, P50 sits near the hit path while P95 sits in the miss cohort. A dashboard displaying only the 7.2 ms average above hides the experience of the **slowest 10% of requests**.

When benchmarking, report separately:

- `jwt_verify_duration` (with cached JWKS, cold JWKS, and key rotation).
- `introspection_http_duration` (connect, TLS, server processing, read).
- `introspection_cache_hit_rate`, positive/negative hits.
- End-to-end response latency P50, P95, P99; request rate and error rate.
- Concurrency/in-flight requests, connection pool queuing, timeouts, and retry attempts.
- Distinct token cardinality: 1,000 QPS from 10 users sharing tokens differs drastically from 1,000 QPS with 1,000 unique tokens.
- Token TTL, session/authorization propagation, and revocation lag.

### 5.4. Throughput and Saturation

At 1,200 QPS, if each introspection holds a connection for ~22 ms, the model predicts an average of **26.4 concurrent in-flight introspection requests**. However, if the IdP slows to 200 ms, in-flight requests jump to **240** even at constant traffic. Once connection pools or IdP queues saturate, latency grows non-linearly; client timeouts, circuit breakers, and backpressure become mandatory.

Never compare two architectures at low QPS and claim they will scale identically at 10x peak load.

## 6. Standalone Java 17: Computing Trade-offs

`TokenTradeoffModel.java` below **uses only JDK 17**, requiring no Spring, IdP, or network. It computes expectations from the assumptions in Section 5 and prints deterministic output using `Locale.ROOT`.

~~~java
import java.util.Locale;

public final class TokenTradeoffModel {

    record Inputs(int requestsPerSecond,
                  double businessMs,
                  double jwtVerifyMs,
                  double introspectionMs,
                  double cacheHitRate,
                  int cacheTtlSeconds,
                  int jwtRemainingSeconds) {
    }

    private TokenTradeoffModel() {
    }

    public static void main(String[] args) {
        Inputs input = new Inputs(
                1200, 5.0, 0.7, 22.0, 0.90, 10, 300);

        double jwt = input.businessMs() + input.jwtVerifyMs();
        double opaque = input.businessMs()
                + input.introspectionMs();
        double missRate = 1.0 - input.cacheHitRate();
        double opaqueCached = input.businessMs()
                + missRate * input.introspectionMs();

        long rawIdpQps = input.requestsPerSecond();
        long cachedIdpQps = Math.round(
                input.requestsPerSecond() * missRate);

        double inFlight = rawIdpQps
                * input.introspectionMs() / 1000.0;
        double inFlightCached = cachedIdpQps
                * input.introspectionMs() / 1000.0;

        System.out.printf(Locale.ROOT,
                "jwt_warm_avg_ms=%.1f%n", jwt);
        System.out.printf(Locale.ROOT,
                "opaque_no_cache_avg_ms=%.1f%n", opaque);
        System.out.printf(Locale.ROOT,
                "opaque_cached_avg_ms=%.1f%n", opaqueCached);
        System.out.printf(Locale.ROOT,
                "idp_qps_no_cache=%d%n", rawIdpQps);
        System.out.printf(Locale.ROOT,
                "idp_qps_cached=%d%n", cachedIdpQps);
        System.out.printf(Locale.ROOT,
                "intro_in_flight_no_cache=%.1f%n", inFlight);
        System.out.printf(Locale.ROOT,
                "intro_in_flight_cached=%.2f%n", inFlightCached);
        System.out.println("cache_stale_bound_s="
                + input.cacheTtlSeconds());
        System.out.println("jwt_local_revocation_bound_s="
                + input.jwtRemainingSeconds());
    }
}
~~~

Run from the directory where the file is saved:

~~~bash
javac TokenTradeoffModel.java
java TokenTradeoffModel
~~~

**Stdout computed directly from the code:**

~~~text
jwt_warm_avg_ms=5.7
opaque_no_cache_avg_ms=27.0
opaque_cached_avg_ms=7.2
idp_qps_no_cache=1200
idp_qps_cached=120
intro_in_flight_no_cache=26.4
intro_in_flight_cached=2.64
cache_stale_bound_s=10
jwt_local_revocation_bound_s=300
~~~

`cache_stale_bound_s` is solely the **maximum stale window caused by one positive cache TTL layer** in an idealized model: it excludes IdP propagation, clock skew, network outages, multiple cache layers, or policies attempting stale-on-error. `jwt_local_revocation_bound_s` is solely the **remaining JWT lifetime** assuming no denylist, token version, introspection, or online policy. Never treat these two figures as production SLAs without measuring.

Vary `cacheHitRate`, `introspectionMs`, and `requestsPerSecond` to explore sensitivity. Even a 99% cache hit rate is unsafe if the organization requires revoking permissions in **under 2 seconds**.

## 7. Network Dependency and Availability: "Offline JWT" Has Limits Too

### 7.1. Opaque No-Cache: IdP Is on the Critical Path

With introspection, the resource server must:

1. Resolve DNS/TCP/TLS to the IdP over a trusted network.
2. Authenticate using client credentials (or the IdP-specified method).
3. Send the token over HTTPS and receive a valid response.
4. Check `active`, map scopes, and verify resource server constraints.
5. Proceed to business logic only if authentication/authorization pass.

If the IdP loses connectivity, the resource server **cannot verify new/uncached tokens**. By safe design, **fail closed**—never convert a network timeout into "token active." Define 503/502 infrastructure responses where appropriate; framework defaults may map errors differently per exception handling. Never force every introspection timeout into 401 `invalid_token`, because that error does not mean the token was revoked.

### 7.2. JWT Warm: No Per-Request IdP Call Needed

While cached JWKs remain valid, local JWT verification can continue authenticating even during brief IdP downtime. However:

- Tokens signed with a **new key** the API does not yet hold can fail when JWKS refresh fails.
- The first request may require metadata/JWK discovery depending on configuration.
- Public key rotation or key removal that fails to propagate promptly can cause failures or security gaps.
- If JWTs require an online revocation/policy service per request, the architecture **becomes network-dependent again**.
- If the issuer uses JWE encryption unsupported by the decoder, the local JWT path will not work merely because the token looks like a JWT.
- If `aud` or `iss` is wrong, verifying the signature is insufficient to accept the token.

Therefore, the accurate statement is: **local JWT verification with a trusted key cache reduces IdP dependency on the warm path**, not "JWTs are permanently independent of the IdP."

### 7.3. Availability Budget Example Assuming Independence

Suppose the resource server achieves 99.9% availability and the introspection service achieves 99.9%, assuming **two independent failure modes** and that every uncached opaque request must succeed at both.

~~~text
A_joint = A_api * A_introspection
        = 0.999 * 0.999
        = 0.998001
        = 99.8001 %
~~~

This is a **simplified model**, not a measured SLA. In reality, failures can be **correlated** (shared region, DNS, network, or certificate infrastructure), and the API also depends on databases/caches/downstream services. Never multiply arbitrary probabilities and treat the product as an exact forecast. The takeaway is that every online dependency on the critical path consumes part of your **availability budget**.

On the warm JWT path, if the IdP goes down while JWKS remains validly cached, the IdP is not a per-request dependency during that interval; still measure cold starts, key rotation, and revocation policies separately.

### 7.4. Retries, Circuit Breakers, and Timeouts

For introspection, decisions must be clear:

| Scenario | Recommended Action |
| --- | --- |
| Valid `active=false` | Reject token; **never retry** hoping for `active=true` |
| IdP returns HTTP 401 to introspection client | Check secret/auth method; never retry infinitely with the same secret |
| Timeout | Enforce short deadline, circuit breaker/rate limiting; fail closed |
| 429 | Respect rate limits and retry budgets; avoid token storms |
| Transient 503 | **Strictly bounded** retries may be used when token lookup is safe on IdP; never hold requests indefinitely |
| Introspection JSON fails schema | Never treat token as active |
| JWKS key rotation | Manage cache/refresh and monitoring; never disable JWT signature validators |
| Invalid JWT signature | 401; never fall back to "decode payload" |

**Never use `retryWhen(Retry.indefinitely())` for introspection.** If the IdP slows down, stacked retries across WebClient, gateways, service meshes, and IdP proxies multiply load and prolong the outage itself. Fail-closed is a security requirement; handle 5xx UX and client retries under a separate contract.

## 8. Token Revocation: Comparing Effective Latency

### 8.1. Three Commonly Confused Concepts

- **Token expiration:** `exp` is reached; time validation no longer permits using the token.
- **Token revocation:** the IdP or policy marks a token inactive **before `exp`**; some verification channel is needed for the API to learn this.
- **Permission/account status change:** a user is locked or loses a role; this may affect existing tokens **only if IdP/introspection and policies are designed** to update metadata or return inactive. There is no universal guarantee that `scope` claims update instantaneously after an admin edits a role.

### 8.2. Revocation Timeline

~~~text
T0: Authorization Server issues token, exp = T0 + 15 minutes
T1: Security team revokes token immediately upon detecting leak

Opaque introspection NO CACHE:
    request after T1 -> IdP returns active=false (after propagation)
    -> API rejects without waiting for exp

Opaque introspection CACHE positive 30 seconds:
    request before T1 caches active=true
    request after T1 may still hit cache
    -> API may accept during remaining TTL window
    -> once cache expires, re-introspects and sees inactive

JWT local-only (no denylist, online check):
    signature/iss/nbf/aud/exp remain valid
    -> API may accept until exp,
       even though IdP marked revoked at T1
~~~

**Limitation:** An IdP does not necessarily synchronize revocations instantaneously across every region; DB/event propagation, issuer policies, and intermediate cache layers also add delay. When calling opaque "near-real-time," measure `T_revocation_to_first_401` in your real system rather than just reading TTL settings.

### 8.3. Revocation Window Formulas

Notation:

- `D_as`: delay for the IdP/introspection endpoint to reflect revocation.
- `D_cache`: remaining positive cache validity after T1.
- `D_jwt`: remaining lifetime until token `exp`, accounting for clock skew.
- `D_events`: delay for denylist/token version/push revocation events, if present.

Under a **non-fail-open model**, approximate bounds are:

~~~text
Opaque no cache:
  revoke_exposure ≈ D_as + small propagation/network delay

Opaque cached:
  revoke_exposure ≲ D_as + D_cache
  (assuming no stale-on-error and finite TTL)

JWT local-only:
  revoke_exposure ≲ D_jwt
  (can be shortened by a denylist/online check)

JWT with revocation event:
  revoke_exposure depends on D_events + local policy/cache
  (not solely dependent on exp)
~~~

These inequalities are **simple models**. A cache refresh occurring just before IdP propagation finishes can extend the stale window by another TTL; clock skew, replication, and stale-while-error can delay it further. Real SLAs must account for **the Authorization Server contract and all cache layers**.

### 8.4. Is a Short Token TTL Perfect Revocation?

No. A 5-minute JWT access token caps maximum exposure to `exp` plus clock skew in a local-only model, yet 5 minutes still fails a requirement like "account lockouts must take effect in under 10 seconds." Conversely, an opaque token can carry a longer TTL yet be revoked and introspected promptly—provided the endpoint and state sync are fast enough.

Short-lived JWTs require a **refresh token** mechanism so UX does not force constant re-logins. Refresh tokens are usually held by the OAuth2 Client/Authorization Server with dedicated revocation and rotation rules. **Never** repurpose an ID Token as an access token to tweak TTLs arbitrarily.

## 9. Caching Introspection: Optimizing Latency While Expanding the Stale Window

### 9.1. RFC 7662 Permits Caching, Does Not Require It

RFC 7662 Section 4 states that a resource server **may cache** introspection responses while weighing performance/security trade-offs; **if the response includes `exp`, it must not be cached past `exp`**. Therefore:

~~~text
ttl_effective = min(
    configured_positive_cache_ttl,
    max(0, token_exp - now - allowed_clock_skew)
)
~~~

This is a suggested policy expression. For tokens without `exp`, set a dedicated security upper bound; never cache indefinitely. Never use an unvalidated `expires_at` or `exp` to justify a long TTL.

### 9.2. Cache Hit Rate Depends on More Than TTL

Hit rates depend on:

- Requests per token within the TTL.
- Unique tokens per second.
- Pod-local cache vs. shared Redis.
- Sticky vs. round-robin load balancing.
- Eviction policy / memory size.
- Actual remaining `exp` lifetime.
- Cache key normalization and issuer/audience partitioning.
- Token refresh rates introducing fresh tokens.
- Negative caching, token brute-forcing, and cache penetration.

Consider two systems both at 1,200 requests/s:

- System A has 12 service clients reusing stable tokens heavily within 10 seconds -> cache hit rate can be high.
- System B has 1,200 users each using a distinct token once -> cache hit rate is low despite identical QPS.

Never extrapolate a hit rate measured in a single-user test to production with millions of unique tokens.

### 9.3. Cache Tiers and Placement

| Storage Option | Latency | Consistency | Key Considerations |
| --- | --- | --- | --- |
| No cache | Adds IdP RTT per request | Latest state from IdP | High load; fails closed when network drops |
| JVM-local cache | Very fast hits | Each pod keeps its own TTL | Rollouts/scaling cause cold misses; revocations can linger across pods |
| Redis/shared cache | Hits incur network hop | Shared TTL, event-invalidatable | Redis becomes a new dependency needing TLS/auth/availability |
| CDN/edge introspection cache | Rarely appropriate without strict key/permission controls | Risk of sharing token metadata/PII | Use only with specialized security design |
| Cache token verdict until exp | Low IdP QPS | Revocation lags like local JWT | Loses most near-real-time revocation benefit |

**Cache keys must never expose raw tokens** in observability keys. When storing keys, use HMAC/SHA-256 with a dedicated secret key per your threat model to prevent collisions and cache poisoning, and restrict cache read permissions. Cached values may hold claims/PII; protect sensitive data and enforce absolute TTLs.

### 9.4. Do Not Use Mono.cache() as a System-Wide Cache

~~~java
// Anti-pattern if expecting a cache shared across multiple requests:
@Override
public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
    return delegate.introspect(token).cache();
}
~~~

Each method invocation creates a **new `Mono`**, so `cache()` only memoizes that single publisher instance rather than building a global token-keyed cache. Cross-request caching requires a component with keying, eviction, TTLs, concurrency control, negative/positive policies, and invalidation.

### 9.5. Caching Negative Responses and Network Errors

`active=false` may be cached very briefly to absorb brute-force/garbage-token load **only if policy permits**. Never cache network timeouts or HTTP 503 as long-lived `active=false`—those are IdP outages, not invalid-token verdicts. Also never cache errors and automatically **allow tokens** during upstream outages unless approved by an extraordinary security review; default to fail closed.

### 9.6. Calculating Cache TTL Trade-offs

Suppose a requirement states "a revoked token must be blocked in **no more than 15 seconds**":

- If worst-case introspection replication lag is 5 seconds and positive cache TTL is 30 seconds, **you cannot meet** 15 seconds.
- With a 3-second cache TTL and 5-second replication lag, you still must check schedulers, propagation, and tails, yet the 8-second theoretical sum leaves headroom for jitter.
- With a local JWT carrying a 10-minute access token TTL and no revocation check, you cannot meet 15 seconds by shrinking the JWKS cache TTL. The JWKS cache stores **public keys**, not per-token active decisions.

Measure worst-case and P99 in practice rather than trusting theoretical numbers alone.

## 10. Spring Boot 4.1.x Example: Same API, Two Strategies

This demo creates **one** WebFlux application with **two mutually exclusive profiles**: `jwt` and `opaque`. Both use the same `GET /api/data` endpoint requiring `SCOPE_data.read`; only how the resource server verifies the Bearer token changes.

**End-to-end prerequisites:** you need a real Authorization Server issuing JWTs for the `jwt` profile or opaque tokens/introspection credentials for the `opaque` profile. The demo does not mint tokens, never puts hardcoded "admin" tokens into production, and never pretends to verify an IdP offline.

### 10.1. Maven pom.xml

Uses Java **17+**, Maven, Spring Boot **4.1.2**, Spring Reactive Web, Spring Security, and resource server. In Spring Boot 4, the standard OAuth2 Resource Server starter is `spring-boot-starter-security-oauth2-resource-server`.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>token-strategy-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security-oauth2-resource-server</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Never** mix in Servlet's `spring-boot-starter-web` when building WebFlux. Do not add OAuth2 Client registrations just for an API to receive Bearer tokens; an OAuth2 Client requests and sends tokens to call APIs, unlike a Resource Server.

### 10.2. Profile-Based Configuration

File `src/main/resources/application.properties`:

~~~properties
server.port=8080
~~~

File `src/main/resources/application-jwt.properties`:

~~~properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=${JWT_ISSUER_URI}
spring.security.oauth2.resourceserver.jwt.audiences=${JWT_API_AUDIENCE}
~~~

File `src/main/resources/application-opaque.properties`:

~~~properties
spring.security.oauth2.resourceserver.opaquetoken.introspection-uri=${INTROSPECTION_URI}
spring.security.oauth2.resourceserver.opaquetoken.client-id=${INTROSPECTION_CLIENT_ID}
spring.security.oauth2.resourceserver.opaquetoken.client-secret=${INTROSPECTION_CLIENT_SECRET}
~~~

The `${...}` notations during authoring are converted to standard Spring `$...` property placeholders when saving Knowledge. **These are runtime environment variables to supply**, not real secrets. `JWT_ISSUER_URI` is the access token's issuer; `JWT_API_AUDIENCE` is the audience meant for this API. The introspection URI must use HTTPS and credentials issued specifically by the Authorization Server to the resource server.

Activate **only one** profile (`jwt` or `opaque`) per run so you do not register two catch-all `SecurityWebFilterChain` beans. In production, use a secrets manager instead of keeping client secrets in source files.

### 10.3. Complete Java File

Create `src/main/java/com/example/tokenstrategy/TokenStrategyApplication.java`:

~~~java
package com.example.tokenstrategy;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class TokenStrategyApplication {

    public static void main(String[] args) {
        SpringApplication.run(TokenStrategyApplication.class, args);
    }

    private static ServerHttpSecurity common(ServerHttpSecurity http) {
        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers("/healthz").permitAll()
                        .pathMatchers("/api/data")
                                .hasAuthority("SCOPE_data.read")
                        .anyExchange().denyAll())
                .httpBasic(basic -> basic.disable())
                .formLogin(form -> form.disable());
    }

    @Bean
    @Profile("jwt")
    SecurityWebFilterChain jwtChain(ServerHttpSecurity http) {
        return common(http)
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }

    @Bean
    @Profile("opaque")
    SecurityWebFilterChain opaqueChain(ServerHttpSecurity http) {
        return common(http)
                .oauth2ResourceServer(oauth2 ->
                        oauth2.opaqueToken(Customizer.withDefaults()))
                .build();
    }

    @RestController
    static class Api {

        @GetMapping(value = "/healthz",
                produces = MediaType.APPLICATION_JSON_VALUE)
        Mono<Map<String, String>> healthz() {
            return Mono.just(Map.of("status", "UP"));
        }

        @GetMapping(value = "/api/data",
                produces = MediaType.APPLICATION_JSON_VALUE)
        Mono<Map<String, String>> data() {
            return Mono.just(Map.of("result", "DATA_OK"));
        }
    }
}
~~~

**Why split the code by profile?**

- `@Profile("jwt")` creates a chain using `ReactiveJwtDecoder` and trusted JWKS. That is the local verification branch.
- `@Profile("opaque")` creates a chain using `ReactiveOpaqueTokenIntrospector` and an introspection URI. That is the online validation branch.
- Both enforce the exact same `hasAuthority("SCOPE_data.read")` policy, so latency comparisons are not skewed by differing authorization logic.
- `/healthz` is public to check the process without a token; sending a deliberately invalid Bearer token to a public route can still be rejected by the auth filter, so test health **without attaching `Authorization`**.
- `formLogin`/`httpBasic` are disabled, leaving Bearer auth only. No cookie/session login is declared. The demo exposes **GET**; do not assume CSRF is always disabled or unnecessary on other APIs.
- No issuers, secrets, or roles are hardcoded; Spring Boot loads configuration by profile.
- No `.block()` calls; the controller returns reactive `Mono` types.
- `Map.of` does not guarantee JSON key ordering, so tests should assert the `result` field.

**Limitation:** the program compiles once compatible Spring Boot/Security dependencies are resolved, yet **verifying real Bearer tokens** requires an IdP's issuer/JWKS or introspection endpoint. Do not infer that running `mvn spring-boot:run` without an IdP benchmarks JWT vs. opaque performance.

### 10.4. Running the JWT Profile

Assuming a valid JWT has been issued by the IdP for the proper audience and scope:

~~~bash
export SPRING_PROFILES_ACTIVE=jwt
export JWT_ISSUER_URI='https://issuer.example.com/realms/company'
export JWT_API_AUDIENCE='api.example.com'
./mvnw spring-boot:run
~~~

The address above is an **illustrative issuer** and must be replaced with a real issuer. Verify behavior:

~~~bash
curl -i http://localhost:8080/healthz
curl -i http://localhost:8080/api/data
curl -i -H "Authorization: Bearer $JWT_ACCESS_TOKEN" \
  http://localhost:8080/api/data
~~~

When `JWT_ACCESS_TOKEN` has a valid signature, issuer, audience, timestamps, and `scope=data.read`, the last endpoint returns HTTP **200** with `{"result":"DATA_OK"}`. Missing token -> typically **401**; valid token lacking `SCOPE_data.read` -> typically **403**. Tampered JWT signature or wrong audience -> **401**.

**`JWT_ACCESS_TOKEN`** is merely an environment variable name to set with a real credential; never print tokens to the screen or commit them to Git.

### 10.5. Running the Opaque Profile

Stop the JWT process first, then switch profiles:

~~~bash
export SPRING_PROFILES_ACTIVE=opaque
export INTROSPECTION_URI='https://issuer.example.com/oauth2/introspect'
export INTROSPECTION_CLIENT_ID='resource-server-id'
export INTROSPECTION_CLIENT_SECRET='secret-issued-by-idp'
./mvnw spring-boot:run
~~~

These values are examples; substitute your real introspection URI and credentials. Verify:

~~~bash
curl -i http://localhost:8080/healthz
curl -i http://localhost:8080/api/data
curl -i -H "Authorization: Bearer $OPAQUE_ACCESS_TOKEN" \
  http://localhost:8080/api/data
~~~

If introspection reports active with `data.read` scope, the response is 200 `DATA_OK`; inactive/expired/revoked tokens -> typically **401**; active lacking scope -> typically **403**.

**Important:** the `opaque` profile never tries to decode a token as a JWT, and the `jwt` profile never sends tokens to the introspection endpoint on the warm path. Reusing the exact same app and controller keeps benchmarks focused on **verification strategy** rather than differing business endpoints.

### 10.6. Windows PowerShell

In PowerShell, set variables using `$env:SPRING_PROFILES_ACTIVE="jwt"`, `$env:JWT_ISSUER_URI="..."`, and `$env:JWT_API_AUDIENCE="..."`. Run `.\mvnw.cmd spring-boot:run`. For curl, use `curl.exe` if `curl` is aliased to `Invoke-WebRequest`. Never pass tokens in URLs; when benchmarking, use secret injection rather than exposing secrets in command lines visible in process lists.

## 11. Designing Meaningful Benchmarks

### 11.1. Hold Everything Unrelated Constant

- Identical Spring Boot/Spring Security version, Java version, and container CPU/memory.
- Identical application handlers, JSON serialization, and downstream dependencies.
- Identical network region/zone, HTTP connection pools, and TLS/proxy topology.
- Identical request/response payloads, realistic JWT signing algorithms, and token sizes.
- Identical scope/authority mapping, enforcing production-equivalent audience/issuer checks.
- Identical concurrency/QPS patterns and unique-token ratios.
- Identical GC warmup, JWKS warmup, and IdP introspection warmup.
- Measure cold-starts and JWKS rotation separately; never lump them into warm P99 under one label.
- Run multiple iterations, report confidence intervals, and state exact sample counts.

**Never benchmark** a mock `Mono.just(principal)` introspector against real JWT signature verification; that removes all network/IdP lookups and fails to measure the real question. Conversely, never use different heavy database queries when comparing the two strategies.

### 11.2. Designing Three Workloads

| Workload | Token Distribution | Goal |
| --- | --- | --- |
| A: single hot token | 1 token reused across many requests | Best case for introspection caching; measures reuse |
| B: many tokens | Few requests per user/token | Measures miss rates closer to production |
| C: token rotation/revocation | Tokens rotated/revoked mid-run | Measures stale window, failed requests, key refresh |

Exercise load levels such as 50, 200, 800, and 1,500 QPS **within authorized infrastructure limits**; never run load tests against unapproved third-party IdPs. If the IdP has quotas, coordinate with its owners to avoid causing an outage via rate limiting.

### 11.3. Metrics to Record

| Metric | JWT Local | Opaque No-Cache | Opaque Cached |
| --- | --- | --- | --- |
| End-to-end P50/P95/P99 | Measure | Measure | Measure |
| Token verification duration | Crypto + validators | Network + parse | Cache lookup or network |
| IdP requests/s | JWK/discovery | ~bearer QPS | ~cache misses |
| Cache hit/miss | JWKS cache | 0 / N/A | Positive/negative hits |
| 401/403 errors | Signature/claim/authority | Inactive/authority | Stale/authority |
| IdP 429/5xx/timeouts | Watch JWKS fetches | Direct impact | Misses directly impacted |
| Revocation-to-first-deny | Per `exp` or online check | Per IdP propagation | Per cache TTL + propagation |
| Key rotation failures | Critical | No local JWKS check if introspecting only | No local JWT-JWKS check |
| Connection pool saturation | Minimal on warm JWT path | Yes | Scales with miss rate |

**Measurement hygiene:** never log raw access tokens, bearer headers, introspection client secrets, or PII-bearing JWT claims as metric labels. Use hashed/opaque test IDs when correlating traces.

### 11.4. Chaos Testing an IdP Network Partition

In an authorized test environment:

1. Run warm JWT and opaque requests successfully; record baselines.
2. Block **only the path to the introspection endpoint**.
3. Verify uncached opaque **fails closed**; never silently accept.
4. Verify warm JWT with valid cached keys **can** keep verifying, while still bounded by downstream dependencies.
5. Block the JWKS endpoint and issue a JWT signed with a new key: JWT should fail once the decoder cannot fetch the new key; verify alerts.
6. Enable a 5-second opaque cache TTL; observe cached hits succeeding temporarily while misses fail closed.
7. Revoke a token and measure how long until requests start receiving 401/deny under the IdP mechanism.
8. Restore the IdP, verify half-open circuit breaker recovery, and confirm QPS does not trigger a retry storm.

Never enable fail-open "to hit availability targets" when the security model demands online token checks. If a system accepts stale-on-error, that is an **approved risk decision** with a hard TTL, narrow scope, and auditing—not a Spring Security default.

## 12. Revocation Testing: Must Use a Real Wall Clock

### 12.1. Revoked Token Scenario

In a test environment where the IdP supports token revocation:

~~~text
T0 issue token and call /api/data => 200
T1 call IdP to revoke token / disable account
T2 every second, retry /api/data with old token
T3 first time API rejects token => 401 or policy-specific deny

Observed revocation lag = T3 - T1
~~~

With local-only JWT, as long as signature/issuer/audience/exp remain valid, the API typically **keeps returning 200** until `exp` unless a denylist or online policy exists. With uncached opaque, the API can reject on the very next request once the IdP reflects `active=false`; with cached opaque, it waits on cache TTL or invalidation.

**Never use a side-effecting POST** to probe revocation every second. Use a read-only GET so you do not create duplicate transactions or mutate real data.

### 12.2. Revocation Events Are Not Always Token Revocations

When an admin changes a role, the IdP may leave issued access tokens with their original scope snapshot until they expire. An introspection endpoint may still report `active=true` with the old scopes per policy. Therefore, measure **two separate things**:

- Token revoked -> how long until `active=false`?
- User role/account disabled -> **by what convention** are introspection/JWT authorities updated?

Never promise that opaque tokens update scopes immediately just because introspection is online; it depends on **IdP semantics and the introspection data source**.

### 12.3. JWT Revocation Options

| Additional Mechanism | Effect | Trade-off |
| --- | --- | --- |
| Short JWT TTL | Bounds how long old tokens stay usable | Higher refresh frequency, UX/IdP load |
| `jti` denylist | Blocks specific tokens before `exp` | Introduces state store/network/cache; IDs must be protected |
| Per-user token version | Invalidates all prior tokens when version increments | Requires online/cache lookup |
| Push revocation events | Updates denylist/policy caches | Event reliability, propagation lag |
| Online introspection for JWT | AS decides active per request | Inherits opaque's latency/availability trade-offs |
| Online checks on high-risk endpoints | Constrains sensitive actions only | Complex policy; must ensure no bypass paths |

**Never rotate the entire signing key** just to revoke one user's access token: that key may sign vast numbers of valid JWTs, and rotation does not guarantee every resource server updates immediately.

## 13. Security When Building an Introspection System

### 13.1. The Token Introspection Endpoint Must Be Secured

Per RFC 7662, the protected resource sends the token in an HTTP POST form, and the resource server authenticates to the introspection endpoint as required by the AS. Ensure:

- HTTPS/TLS with trusted certificates; never use a trust-all SSL context.
- Allowlist only trusted IdP hostnames; never read the introspection URL from tokens or user queries (prevents SSRF).
- Secret manager/mTLS/`private_key_jwt` if supported by the IdP, with rotation and auditing.
- Timeouts, connection pools, and circuit breakers so Netty requests never hang forever.
- Accept only schema-valid boolean `active` responses and metadata belonging to the right issuer/client/audience.
- Never return raw introspection responses or client secrets on public APIs.
- Never put tokens in URLs/query parameters, URL logs, or analytics.
- When caching, protect keys and values (PII), enforce TTLs, eviction, and revocation events.
- Never let API B use API A's introspection permissions to accept tokens from an unrelated namespace.

### 13.2. Local JWT Verification Also Has a Trust Boundary

- Trust only configured issuers and JWK Set URIs; never trust arbitrary `jku`/`x5u` headers in tokens.
- Accept only policy-approved signature algorithms; never accept unsigned tokens.
- Verify `iss`, `aud`, `exp`, `nbf`, and JWT access token profile constraints.
- Protect the JWKS cache and handle key rotation, key revocation, and stale keys by policy.
- Never put sensitive PII or secrets in JWS payloads since clients can read them.
- Never treat an ID Token as an access token unless the resource server contract explicitly allows it.
- Never map `ROLE_ADMIN` from a claim editable by end users.
- Never skip authorization merely because authentication succeeded.

### 13.3. Authentication 401 vs. Authorization 403

| Scenario | Typical HTTP | Meaning |
| --- | --- | --- |
| No Bearer sent to protected route | 401 | Unauthenticated |
| Opaque `active=false` | 401 | Token rejected |
| Invalid JWT signature / expired / wrong audience | 401 | Invalid token |
| Valid token lacking `SCOPE_data.read` | 403 | Authentication passed, authorization denied |
| Introspection endpoint timeout | Infrastructure error / response per handler | Never treat token as valid |
| Post-auth business validation | 4xx/5xx per business logic | Do not automatically blame JWT/opaque auth |

For 401/403 responses, inspect `WWW-Authenticate` to distinguish `invalid_token` from `insufficient_scope` when supplied by the server. Do not rely solely on one Spring Security version's default response body.

## 14. Anti-Patterns and Fixes

### 14.1. "JWT Is 10x Faster Than Opaque" Without Measuring

This claim has no universal validity. RTT, locality, caching, crypto algorithms, payloads, and workloads all vary. Measure under identical SLOs, warm/cold caches, and P95/P99.

### 14.2. "JWT Never Needs the IdP"

JWKS discovery/refresh and key rotation can require the network. Adding online policy/revocation checks can erase the JWT network advantage; measure against your real architecture.

### 14.3. "Opaque Is Always Revoked Instantly"

Revocation can lag due to IdP replication, positive caching, polling intervals, and app retries. Never promise revocation latency without measuring `revocation-to-first-deny`.

### 14.4. "Caching Introspection Until exp Is Optimal"

When `exp` is far away, revoked tokens continue being accepted. RFC 7662 permits caching yet warns about staleness; base TTL on your risk budget.

### 14.5. "Skip Verification When the IdP Times Out"

Never construct an `OAuth2AuthenticatedPrincipal` when token active status is unknown. That is **fail-open** and enables unauthorized access.

### 14.6. "It's a JWT Access Token, So Just Decode It"

Base64URL decoding does not verify the JWS signature, `iss`, `aud`, or `exp`. Use `ReactiveJwtDecoder` with trusted validators.

### 14.7. "HTTP 403 Proves the Token Was Revoked"

No. 403 usually indicates a valid token lacking scopes/authorities; invalid tokens are normally blocked at authentication (401). Test each separately.

### 14.8. "Without Caching, the IdP Will Handle Peak Load Fine"

Introspection can turn 1,000 API RPS into 1,000 extra IdP RPS; perform load/capacity testing and rate limiting. Never accidentally overload a shared corporate IdP.

### 14.9. "Drop Servlet OpaqueTokenIntrospector into WebFlux"

WebFlux requires `ReactiveOpaqueTokenIntrospector` and reactive `ServerHttpSecurity`. Never `block()` on request threads or the event loop.

### 14.10. "Lowering JWKS TTL Makes JWT Revoke Faster"

The JWKS cache holds **public signing keys**, not per-token revocation state. Lowering JWKS TTL increases IdP dependency without solving per-token revocation.

### 14.11. "High Cache Hit Rate Guarantees Fast P99"

A 10% miss rate can dominate P95/P99 despite a low average. Always report hit/miss latencies and tail metrics separately.

### 14.12. "Revoked at T1 Means Introspection Immediately Returns active=false Globally"

Replication/region lag can keep returning `active=true` briefly. Test multi-region behavior and verify the IdP contract.

### 14.13. "Pass Tokens in URLs to Make Benchmarking Easier"

Bearer tokens in URLs easily leak via access logs, browser history, and Referer headers. Use HTTPS headers; during benchmarks avoid printing full `Authorization` headers.

### 14.14. "Benchmarking Throughput with @MockBean Introspector and Calling It a Network Test"

A fake introspector returning `Mono.just(principal)` performs no HTTP and measures no network, rate limits, or IdP state; it is suitable only for testing authn/authz logic.

### 14.15. "Enabling Multiple Catch-All SecurityWebFilterChains to Support Both"

Two catch-all chains without `@Order`/matchers can let one chain swallow requests meant for the other. In this demo we use **mutually exclusive profiles**, or in production configure explicit paths/`securityMatcher` and a clear migration plan.

## 15. Architectural Decision Matrix

| Scenario | Leaning Toward | Required Conditions |
| --- | --- | --- |
| Very high API throughput, low latency required | JWT local verification | Valid JWKS/alg/iss/aud; acceptable token TTL and revocation SLA |
| Near-real-time token revocation needed | Opaque uncached introspection | Fast AS propagation, HA endpoint, and latency budget |
| Sensitive API with an online policy service | Introspection or hybrid | Every high-risk path checks online / fails closed |
| Many microservices across multiple regions | JWT for most requests, selective online checks | Key management, TTLs, audience isolation, incident rollback |
| Distant IdP, high RTT, relaxed endpoint SLA | Warm JWT or cached introspection considered | Never drop revocation requirements; measure tails |
| IdP supports introspection but not suitable JWTs | Opaque | Sufficient capacity/HA, client auth/TLS, resource restrictions |
| JWTs issued, yet per-request revocation check required | Introspect JWT via opaque support | Configure by verification method, do not trust format |
| Max 5-second stale permission window allowed | Very short opaque TTL or online policy | Measure IdP replication, TTL, and P99 |
| Concerned about token payload leaking sensitive claims | Opaque or minimal-claim/encrypted JWT profile | Never confuse "opaque" with protection against Bearer theft |
| IdP outage must not halt all endpoints | Warm JWT with local policy where appropriate | Accept revocation lag; measure cold JWKS / rotation |

**There is no one-size-fits-all answer.** For a system with low-sensitivity reads and high-risk account mutations, you might use local JWT for reads and online policy checks for high-risk writes. However, you must prove the online check cannot be bypassed and every token type is scoped to the right audience.

## 16. Production Checklist

1. Determine token format and **verification method** separately; never infer from dots in a string.
2. On WebFlux, use `ServerHttpSecurity`, `ReactiveJwtDecoder`, or `ReactiveOpaqueTokenIntrospector`, never Servlet APIs.
3. Validate JWT signature/trusted algorithms, `iss`, `aud`, `exp`, `nbf`, scopes, and tenants.
4. For introspection, enforce TLS/HTTPS, valid client auth, `active` checks, and audience/resource policies.
5. Know the actual token revocation SLA in seconds and who owns delivering it.
6. Measure verification and API P50/P95/P99 latency; never use illustrative numbers as benchmarks.
7. Track IdP calls/s, cache hit/miss, distinct tokens/s, and retry/timeout metrics.
8. Model capacity/concurrency from peak RPS and RTT, factoring in pool queuing and saturation.
9. For JWTs, test cold JWKS, key rotation, and outages—not only the warm path.
10. For opaque tokens, configure timeouts, circuit breakers, rate-limit handling, and no infinite retries.
11. Fail closed when introspection is unavailable; never synthesize an authenticated principal.
12. When caching introspection, never exceed `exp` per RFC 7662 or your risk budget.
13. Never log raw Bearer tokens, client secrets, sensitive JWT claims, or raw cache keys.
14. Test 200/401/403, revoked, expired, `insufficient_scope`, wrong audience, IdP 503, and JWT key rotation.
15. Verify revocation effectiveness using a real wall clock across regions and cache layers.
16. Align trust boundaries; never use ID Tokens in place of access tokens.
17. Never leave test credentials, fake issuers, or demo profiles enabled in production.
18. Document hybrid architectures so sensitive routes never bypass online checks.
19. Prepare a migration plan when switching between opaque and JWT, especially for unexpired tokens.
20. Revisit the decision whenever IdP SLAs, token TTLs, traffic mix, or risk policies change.

## 17. Self-Check Questions

**Question 1.** Why is warm JWT verification typically faster than uncached opaque introspection?

**Answer:** JWTs can verify signatures and claims locally using cached trusted public keys; uncached opaque introspection typically sends the token over HTTPS to the introspection endpoint and waits for a response.

**Question 2.** Why are JWTs not strictly "offline"?

**Answer:** JWKS discovery, cache misses, key rotation, or online revocation policies can require networking; the advantage is avoiding an IdP call on every warm request.

**Question 3.** At 1,200 QPS and 22ms introspection, what is the average number of in-flight requests in the simple uncached model?

**Answer:** `1200*0.022=26.4` per Little's Law, before accounting for queuing or saturation.

**Question 4.** With 90% introspection caching at 1,200 QPS, what is the estimated QPS reaching the IdP?

**Answer:** `1200*(1-0.90)=120` calls/s under a steady hit ratio model.

**Question 5.** Why does `active=true` not mean the user can access every API?

**Answer:** You must still check resource audience/issuer/tenant and `SCOPE_*`/authorities for the route; authenticated differs from authorized.

**Question 6.** If the opaque introspection cache TTL is 30 seconds, can you guarantee revocation under 10 seconds?

**Answer:** Not when relying solely on a 30-second TTL without event invalidation; plus there is IdP replication lag.

**Question 7.** Why can local JWT validation still accept a recently revoked token?

**Answer:** Signature and claims remain valid until `exp`; a local verifier lacks per-token revocation state.

**Question 8.** Does `Mono.cache()` inside the `introspect` method cache across the whole API?

**Answer:** Not by default; if each invocation creates a new `Mono`, `cache()` applies only to that publisher instance rather than forming a cross-request keyed cache.

**Question 9.** To lower opaque P99, is merely increasing the cache TTL enough?

**Answer:** Not necessarily. You must measure misses/IdP tails, token cardinality, and connection pools, and accept the wider stale window; raising TTL slows down revocation.

**Question 10.** During an IdP outage, may opaque tokens be assumed active automatically?

**Answer:** Not under a safe default policy. Fail closed, classify network outages, monitor and remediate, and avoid infinite retries.

**Question 11.** Is a JWT sent to `opaqueToken()` for introspection still considered "local JWT"?

**Answer:** No. The token has JWT formatting, yet the validation strategy is online introspection, still subject to IdP RTT and availability.

**Question 12.** Should you rotate the system-wide signing key to revoke one person's token?

**Answer:** Usually no. It affects large numbers of valid tokens; consider short TTLs, denylists, token versions, or online introspection/policies instead.

## 18. Official Documentation

- [Spring Security — Reactive OAuth2 Resource Server: JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive OAuth2 Resource Server: Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security — OAuth2 WebFlux Overview](https://docs.spring.io/spring-security/reference/reactive/oauth2/)
- [Javadoc — ReactiveJwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/ReactiveJwtDecoder.html)
- [Javadoc — ReactiveOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html)
- [Javadoc — SpringReactiveOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.html)
- [Javadoc — ServerHttpSecurity](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Boot 4 — OAuth2 Resource Server auto-configuration](https://docs.spring.io/spring-boot/reference/security/oauth2.html)
- [RFC 7662 Section 4 — Token Introspection and Caching](https://www.rfc-editor.org/rfc/rfc7662#section-4)
- [RFC 6750 — OAuth2 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth2 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [Project Reactor — Retry and Backpressure](https://projectreactor.io/docs/core/release/reference/)
