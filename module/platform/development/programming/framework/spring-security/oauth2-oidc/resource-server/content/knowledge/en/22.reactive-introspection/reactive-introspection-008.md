# Reactive Caching and Single-Flight Deduplication

In a **Spring Security OAuth 2.0 / OIDC Resource Server** using **Spring WebFlux**, an API can receive hundreds or thousands of concurrent HTTP requests carrying **the same opaque Bearer Access Token**. If every request has to call the **Authorization Server token introspection endpoint**, the Resource Server can generate massive numbers of identical HTTP requests, increasing latency, network overhead, and load on the identity provider.

There are two distinct layers to this problem:

1. **Caching introspection results** for a safe duration: a verified `active: true` result can be reused briefly, provided caching never exceeds token expiration or privilege revocation limits.
2. **Coalescing in-flight calls (single-flight, request coalescing)**: if 50 concurrent requests need to introspect *the same token* while the cache is cold, only one introspection call should execute per instance while the remaining waiters share that result.

In reactive programming, both concerns revolve around **`Mono` subscription timing**, how `Mono.cache()` shares subscriptions, error/cancellation lifecycles, and memory bounds. A careless "cache it to go fast" solution can **reuse revoked tokens, cache 503 errors, mix up authorities between two tokens, leak Bearer tokens via cache keys, or lose the Reactor Context**.

This lesson walks from **RFC 7662**, `ReactiveOpaqueTokenIntrospector`, `Mono.cache`, TTLs, Caffeine, HMAC token fingerprints, cancellation, retries, and multi-instance behavior through **single-flight design and testing**. Examples use **Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring WebFlux, and Reactor 3.x**; domains, tokens, scopes, and keys are illustrative. This lesson covers **reactive introspection**, not REST endpoint response caching or a general user-profile cache.

## 1. Starting from the Opaque Access Token Authentication Flow

A client calls:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.test
Authorization: Bearer OPAQUE_ACCESS_TOKEN_VALUE
Accept: application/json
~~~

When the Resource Server is configured for **opaque tokens**, the overall flow is:

~~~text
HTTP request / Bearer token
            |
            v
Spring Security WebFlux
            |
            v
Reactive Authentication
            |
            v
ReactiveOpaqueTokenIntrospector.introspect(token)
            |
            | HTTPS POST /oauth2/introspect
            | token=...
            v
Authorization Server
            |
            +--- {"active":false} -> token rejected
            |
            +--- {"active":true, ...}
                      |
                      v
              OAuth2AuthenticatedPrincipal
                      |
                      v
              Authentication / authorities
                      |
                      v
              authorizeExchange / method security
                      |
                      v
              Owner / tenant / domain policy
~~~

RFC 7662 defines the introspection response with an **`active` JSON boolean field**. Example:

~~~json
{
  "active": true,
  "sub": "external-person-42",
  "client_id": "orders-web",
  "scope": "orders.read orders.write",
  "aud": ["orders-api"],
  "iss": "https://identity.example.test/realms/demo",
  "exp": 1893456000
}
~~~

Conversely, an unacceptable token:

~~~json
{"active": false}
~~~

**HTTP 200 from introspection does not mean the token is active.** The HTTP client can receive 200 with `active:false`, because the introspection request succeeded at the protocol level while the token itself was judged unusable.

### 1.1. Why Can `active:true` Never Be Cached Indefinitely?

A token can:

- **Expire** at `exp`.
- Be **revoked** before `exp` by an Authorization Server workflow.
- Become invalid because the underlying grant/session/client changed under issuer policy.
- Be denied introspection by the current Resource Server, causing the endpoint to return `active:false`.
- Remain active at the IdP while the local account, tenant membership, or record permissions **have changed**.

Retaining an `active:true` result for too long means the Resource Server may accept a token the Authorization Server already revoked. **Every second of cache TTL is a trade-off between performance and revocation lag**, never a risk-free optimization.

### 1.2. What Data Is Actually Cached?

When implementing introspection caching, the right output to store is **metadata already verified by a standard introspector**, such as `OAuth2AuthenticatedPrincipal` and corresponding authorities for **that specific token**, strictly time-bounded.

Never cache wholesale:

- `ServerWebExchange` or the HTTP request.
- One subscriber's `SecurityContext` reused for another subscriber.
- Sessions, cookies, Authorization headers, or a global "current user" principal.
- An owner/tenant decision for a **mutable record** applied across future requests.

Spring Security must still create/maintain **per-request authentication** and run post-introspection authorization checks. Caching must never turn a broad scope into access across all records.

## 2. Two Distinct Goals: Result Caching and Single-Flight

Suppose within 10 milliseconds, 30 HTTP requests arrive with the same Bearer token `T`.

**No cache, no single-flight:**

~~~text
Request 01 -- introspect(T) --\
Request 02 -- introspect(T) ---\
Request 03 -- introspect(T) ----> Authorization Server
 ...                            /
Request 30 -- introspect(T) ---/

30 introspection requests for the same token T
~~~

**Plain result cache only, uncoordinated cache misses:**

~~~text
Cache(T) = miss
   |
   +-- R1 checks: miss -> starts upstream call
   +-- R2 checks: miss -> starts upstream call
   +-- R3 checks: miss -> starts upstream call
   ...

Once the first call finishes, hits begin,
but the parallel calls have already been sent.
~~~

**Single-flight plus caching:**

~~~text
                  Cache lookup by token T
                        |
                        +-- Valid cached result -> return result
                        |
                        +-- Miss
                              |
                              v
                        In-flight lookup(T)
                              |
                 +------------+-------------+
                 |                          |
           No active call              Existing Mono
                 |                          |
                 v                          v
           Create 1 Mono               Share Mono
           store in map                     |
                 |                          |
                 +------------+-------------+
                              |
                              v
                    Only 1 introspection call
                              |
                              v
                  N subscribers receive same signal
~~~

| Concept | Solves | Does not solve by itself |
| --- | --- | --- |
| **Result cache** | Reduces introspection calls **after a result exists**, within TTL. | "Cache stampede" when many requests arrive simultaneously on a miss. |
| **Single-flight** | Coalesces concurrent calls for the same key while one call is in flight. | Long-lived result reuse after the call finishes, without a cache. |
| **Timeout/bulkhead** | Bounds introspection duration and concurrency. | Does not determine token validity or permission scope. |
| **Revocation invalidation** | Shrinks the window for using stale active results. | Does not replace JWT/opaque authentication or domain authorization. |

For introspection, caching and single-flight are often designed **together** with separate policies: the cache TTL can be very short while single-flight still prevents bursts when the TTL expires.

## 3. Reactor: Assembly, Subscription, and Sharing One Publisher

In Reactor, `Mono` is typically a **cold Publisher**: creating the `Mono` does not send the HTTP request; **subscribing** triggers the work.

~~~java
import reactor.core.publisher.Mono;

Mono<String> source = Mono.defer(() -> {
    System.out.println("Executing introspection-like work");
    return Mono.just("active");
});

// Lambda inside defer has not executed yet.

source.subscribe(System.out::println);
source.subscribe(System.out::println);
~~~

With a cold `source`, two subscriptions run the code inside `defer` twice. If that inner block is `WebClient.post().retrieve().bodyToMono(...)`, it can send **two network requests**.

### 3.1. Why `Mono.just` Is Not a Deferred HTTP Call

~~~java
// createResult() runs immediately before Mono.just().
Mono<Result> eager = Mono.just(createResult());

// createResult() runs at subscription time.
Mono<Result> deferred =
    Mono.fromCallable(() -> createResult());

// Publisher is constructed at subscription time.
Mono<Result> deferredPublisher =
    Mono.defer(() -> makeReactiveRequest());
~~~

`Mono.fromCallable` defers synchronous work; it **does not make it non-blocking**. For reactive introspection, prefer `WebClient`/a reactive HTTP client; never call `block()` or `Future.get()` on the event loop just to simplify caching.

### 3.2. Using `Mono.cache()` to Share a Single Execution

~~~java
Mono<OAuth2AuthenticatedPrincipal> shared =
    delegate.introspect(token).cache();
~~~

When **multiple subscribers share the same `shared` instance**, `Mono.cache()` can share the upstream subscription and replay the **terminal signal** to later subscribers. This is the foundation for **single-flight**.

However, storing `shared` in an application cache without eviction carries risks:

- `cache()` with no TTL can **retain results indefinitely** for the `Mono`'s lifetime.
- It can also **cache errors** or empty completions; a 503 error must not become a long-lived verdict.
- A cached `active:true` does not automatically detect a newly revoked token.
- Accidentally sharing a `Mono` across **different tokens** can mix authorities.

Therefore, parameterless `Mono.cache()` fits sharing work **over a very short scope or within one controlled request**. Introspection caching **across HTTP requests** needs **TTLs, size bounds, and proper keys**.

### 3.3. A Local `Mono.cache()` Does Not Coalesce Across Requests

Example:

~~~java
public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
    return delegate.introspect(token).cache();
}
~~~

Each method invocation creates **a different `Mono`**. If 30 HTTP requests call this method, you get 30 separate cached Monos, each firing an upstream request. **Single-flight requires a shared key-indexed registry/cache**, not just appending `.cache()` at the end of a method.

## 4. Cache Keys: Must Bind to the Specific Token and Security Namespace

Tokens with the same `sub` do not necessarily share the same permissions or status:

~~~text
Token A:
  sub = person-42
  scope = orders.read
  aud = orders-api
  exp = 10:05

Token B:
  sub = person-42
  scope = orders.write
  aud = orders-api
  exp = 10:15
~~~

Keying the cache by `sub` would let token A inherit token B's `orders.write` metadata. That is a **critical privilege escalation bug**.

| Cache key | Suitable? | Reason |
| --- | --- | --- |
| `sub` or email | **No** | Multiple tokens for the same user differ in scope, audience, expiration, and revocation. |
| `client_id` | **No** | One OAuth client holds many Access Tokens. |
| `tenant_id` | **No** | Does not identify an individual token. |
| Full raw token in metric labels/logs | **No** | Leaks the Bearer credential. |
| Keyed HMAC fingerprint of token + issuer/resource namespace | **Suitable** | Avoids exposing the raw token directly in cache keys and isolates trust contexts. |

### 4.1. Why Use HMAC Instead of Plain Logging or Unkeyed Hashes?

A Bearer Access Token is a secret. Even though opaque tokens typically have high entropy, never assume every issuer mints tokens with enough entropy to prevent dictionary reversal of an **unkeyed hash**.

A cache key can be:

~~~text
HMAC-SHA256(
    secretKey,
    introspectionEndpointId + "\0" +
    resourceId + "\0" +
    rawAccessToken
)
~~~

The HMAC secret is managed by the application and never carelessly shared with JWT signing keys or OAuth client secrets. The resource/issuer namespace prevents reusing results from one introspection policy on another API or tenant.

**Never place raw tokens, HMAC digests, or secrets into logs or metric labels**: even though HMAC is hard to invert, a stable digest can still serve as a tracking identifier or enable unwanted correlation. Keep the cache private and restrict heap dumps and observability access.

### 4.2. The Namespace Must Be Server-Controlled

Never use a client-supplied issuer URL or unverified `X-Issuer` header to choose the introspection endpoint or cache namespace. The introspection endpoint and **resource audience** must originate from controlled configuration or a vetted multi-issuer routing mechanism.

If the same token string is introspected against two different Authorization Servers or two resource policies, the cache must never share results across those security domains.

## 5. Cache TTL: Always Set Security-Meaningful Time Bounds

For an active token:

~~~json
{
  "active": true,
  "scope": "orders.read",
  "aud": ["orders-api"],
  "exp": 1893456000
}
~~~

A baseline cache TTL:

~~~text
effectiveTtl = min(
    configuredPositiveMaxTtl,
    tokenExpiration - now - safetyMargin
)
~~~

If `exp` is absent or time metadata is unusable, the conservative choice is **not caching the success result**, while still coalescing concurrent in-flight requests for the same call.

### 5.1. TTL Selection Examples

| Token / Policy | Positive max TTL | Remaining token life | Max cache TTL before safety margin |
| --- | --- | --- | --- |
| Low-sensitivity read API | 10 seconds | 15 minutes | 10 seconds |
| Low-sensitivity read API | 10 seconds | 3 seconds | 3 seconds |
| Sensitive admin API | 0 seconds | 15 minutes | Do not reuse completed results. |
| No `exp`, allowed by contract | Special policy | Unknown | Do not cache by safe default. |
| Expired token | 10 seconds | 0 seconds | 0 seconds; token must be rejected per validator/issuer contract. |

**These numbers are illustrative trade-offs**, not RFC 7662 or Spring Security defaults. The system must define a **revocation SLA**: how long is a revoked token tolerated in the design? TTL must never exceed that bound.

### 5.2. Distinguish Cache TTL from Access Token Expiration

A token with `exp` 30 minutes away does not mean you may cache `active:true` for 30 minutes. The Authorization Server can revoke the token before `exp`; the cache only knows the state as of the **previous introspection**.

A cached active result can go stale:

~~~text
12:00:00 introspect token-A -> active=true; cache TTL 5s
12:00:02 Authorization Server revokes token-A
12:00:03 cache hit -> API may still see token as active
12:00:06 cache miss -> introspect -> active=false -> 401
~~~

This design accepts a **revoked-token window** bounded by TTL, network, clock, and replication lag. Never promise "opaque token revocation takes effect instantaneously" when positive caching is enabled.

### 5.3. Safety Margin

Subtracting a small margin before `exp` avoids serving near-expiry cache hits due to latency and clock skew. Never add arbitrary clock skew that makes a token **live longer**:

~~~text
ttl = min(maxTtl, exp - now - margin)
~~~

if the result is zero or negative, do not cache. If the Authorization Server evaluates `exp` and `active` under its own clock policy, synchronize clocks properly rather than turning a local cache into a token-extension mechanism.

## 6. Do Not Cache Every Outcome Under the Same Policy

| Introspection outcome | Should result be kept? | Recommendation |
| --- | --- | --- |
| **`active:true`**, contract-valid metadata | Short caching allowed. | TTL `min(policy, exp)`; right resource/audience. |
| **`active:false`** | **Very short** negative cache only if evaluated. | Do not cache long by default; guard against junk-token DoS. |
| Introspection timeout / TLS / DNS | **Never** cache as token status. | Fail closed, metrics/alerts; controlled retries. |
| Upstream HTTP 429/503/5xx | **Never** cache as inactive. | Classify upstream outage; backoff/circuit breaker. |
| HTTP 401 on introspection client credentials | **Never** treat user token as invalid. | Investigate client secret/mTLS/configuration. |
| JSON missing `active` or `active:"true"` | **Never** treat as valid principal. | Protocol error; fix integration. |
| Active token, wrong audience | **Never** grant access to this resource. | Reject per resource policy; never share another API's cache. |
| Active token, local account locked | Token may be active, domain still denies. | Revalidate local account/tenant per security policy. |

### 6.1. Why Does Error Caching Cause Outages?

If you write:

~~~java
Mono<OAuth2AuthenticatedPrincipal> shared =
    delegate.introspect(token).cache();
~~~

and retain `shared` in a registry for long periods, a single `503` error gets replayed to every subsequent request even after the Authorization Server recovers.

`BadOpaqueTokenException` from an inactive token also differs from a transport error; **never treat all exceptions as `active=false`**. With TTL-based Reactor caching, set **error TTL = 0** unless an explicit negative-caching policy exists.

### 6.2. Do Not Cache Authentication Independently of Authorization

An `OAuth2AuthenticatedPrincipal` may carry `scope`, `client_id`, `sub`, and `aud`. Yet whether the user may read **order 42** can change immediately in the database:

~~~text
Introspection cached: active=true, scope=orders.read
Domain database: permission on order 42 was just revoked
~~~

Domain authorization must evaluate current data per policy. Introspection caching **never replaces** checking account status, tenant membership, ownership/ACLs, or transaction constraints.

## 7. Designing a Reactive Cache with Reactor and Caffeine

A practical **single-instance** design:

1. `Concurrent`/atomic cache lookup by **HMAC token key**.
2. On a miss, create only **one shared `Mono`** for that key.
3. The publisher invokes `delegate.introspect(token)` **on subscription**.
4. `Mono.cache(ttlForValue, ttlForError, ttlForEmpty)` shares **in-flight work** and retains only success results for a short TTL.
5. Caffeine caps **entry count** and **entry lifetime**, preventing unbounded registry growth.
6. The HTTP introspection timeout lives **inside the shared source**, so a hung call does not stall batches of subscribers indefinitely.

Dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    implementation 'com.github.ben-manes.caffeine:caffeine'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Spring Boot dependency management generally aligns compatible versions for common libraries; if a project pins versions manually, ensure Caffeine, Reactor, and Spring Security are compatible.

### 7.1. `TokenCacheKey`: Generating Fingerprints with HMAC

Java example:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class TokenCacheKey {

    private final byte[] hmacSecret;
    private final String namespace;

    public TokenCacheKey(byte[] hmacSecret, String namespace) {
        if (hmacSecret == null || hmacSecret.length < 32) {
            throw new IllegalArgumentException(
                "Use a randomly generated HMAC secret of at least 32 bytes");
        }
        if (namespace == null || namespace.isBlank()) {
            throw new IllegalArgumentException(
                "Trusted introspection namespace required");
        }
        this.hmacSecret = hmacSecret.clone();
        this.namespace = namespace;
    }

    public String forToken(String token) {
        if (token == null || token.isBlank()) {
            throw new IllegalArgumentException("Token is empty");
        }

        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(
                new SecretKeySpec(hmacSecret, "HmacSHA256"));

            mac.update(
                namespace.getBytes(StandardCharsets.UTF_8));
            mac.update((byte) 0); // Separate namespace and token

            byte[] digest = mac.doFinal(
                token.getBytes(StandardCharsets.UTF_8));

            return HexFormat.of().formatHex(digest);
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException(
                "HMAC-SHA256 is unavailable", ex);
        }
    }
}
~~~

**Production usage notes:**

- `hmacSecret` must be a **random secret**, loaded from a secure secret manager/config—never derived from short passwords or client input.
- `namespace` is server-configured, e.g., `"issuer-demo|orders-api|rs-client-v1"`, never taken from Bearer headers.
- Create a fresh `Mac` per call because `Mac` is not safe to share arbitrarily across threads.
- Never log digests or tokens in production.
- An HMAC key does not encrypt tokens in the heap; reactive closures can still retain the raw token briefly.

### 7.2. `SingleFlightCachingIntrospector`

The following is a **`ReactiveOpaqueTokenIntrospector` decorator**. `delegate` must be a standard introspector that checks `active`; the cache must never replace that verification.

~~~java
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;

public final class SingleFlightCachingIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private static final Duration MAX_POSITIVE_TTL =
        Duration.ofSeconds(5);
    private static final Duration UPSTREAM_TIMEOUT =
        Duration.ofSeconds(2);

    private final ReactiveOpaqueTokenIntrospector delegate;
    private final TokenCacheKey cacheKeys;
    private final Clock clock;

    // Caffeine manages a shared registry for the whole instance.
    private final Cache<String, Mono<OAuth2AuthenticatedPrincipal>>
        entries = Caffeine.newBuilder()
            .maximumSize(20_000)
            .expireAfterWrite(Duration.ofSeconds(5))
            .build();

    public SingleFlightCachingIntrospector(
            ReactiveOpaqueTokenIntrospector delegate,
            TokenCacheKey cacheKeys,
            Clock clock) {
        this.delegate = Objects.requireNonNull(delegate);
        this.cacheKeys = Objects.requireNonNull(cacheKeys);
        this.clock = Objects.requireNonNull(clock);
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        if (token == null || token.isBlank()) {
            return Mono.error(new BadOpaqueTokenException(
                "Bearer token is missing"));
        }

        return Mono.defer(() -> {
            // Perform registry lookup only at subscription time.
            String key = cacheKeys.forToken(token);

            Mono<OAuth2AuthenticatedPrincipal> shared =
                entries.get(key, ignored ->
                    Mono.defer(() -> delegate.introspect(token))
                        // Timeout lives inside the shared source.
                        .timeout(UPSTREAM_TIMEOUT)
                        // Coalesce concurrent in-flight subscriptions.
                        // Short positive cache; never retain errors/empty.
                        .cache(
                            this::positiveTtl,
                            error -> Duration.ZERO,
                            () -> Duration.ZERO));

            return shared;
        });
    }

    private Duration positiveTtl(
            OAuth2AuthenticatedPrincipal principal) {

        // RFC 7662: exp is typically a NumericDate;
        // Spring converters may represent it as an Instant.
        Object raw = principal.getAttribute("exp");
        Instant expiresAt;

        if (raw instanceof Instant instant) {
            expiresAt = instant;
        } else if (raw instanceof Number seconds) {
            expiresAt =
                Instant.ofEpochSecond(seconds.longValue());
        } else {
            // Without exp per contract: do not retain result long.
            return Duration.ZERO;
        }

        Duration remaining = Duration.between(
            clock.instant().plusSeconds(1), expiresAt);

        if (remaining.isNegative() || remaining.isZero()) {
            return Duration.ZERO;
        }
        return remaining.compareTo(MAX_POSITIVE_TTL) < 0
            ? remaining : MAX_POSITIVE_TTL;
    }
}
~~~

**Design analysis of the code:**

1. `Mono.defer` keeps registry lookup and source construction at **subscription time**, avoiding network work at assembly.
2. Caffeine's `entries.get(key, mappingFunction)` **synchronizes value creation per key**, preventing simultaneous cache misses from creating distinct `Mono` instances within one JVM.
3. `Mono.defer(() -> delegate.introspect(token))` keeps the delegate call inside the reactive chain.
4. `timeout(2s)` bounds the introspection call; it does not turn timeouts into `active:false`.
5. `Mono.cache(valueTtl, errorTtl, emptyTtl)` **shares the in-flight source** and retains only successful results for the duration returned by `positiveTtl`. Errors and empty results get TTL zero.
6. Caffeine's `expireAfterWrite(5s)` caps **how long the entry holding the `Mono` lives** since creation, while `positiveTtl` caps **how long the Publisher's signal is cached** after completion. Both bound lifetime conservatively.
7. `maximumSize` keeps the registry from growing without bound across distinct tokens; eviction may trigger a fresh introspection for that token as an accepted trade-off.

**Limitations of the example:** this provides **best-effort coalescing within one JVM instance**; it does not strictly guarantee "exactly one call" if an entry is evicted or expires while upstream is still running, across multiple instances, or for requests arriving right at expiration. Having a 2s timeout shorter than the 5s entry retention reduces overlap, yet does not act as a distributed lock. Never cite it as proof of exactly-once processing.

### 7.3. Why Avoid Caching Errors Beyond Real Time?

When the Authorization Server returns `active:false`, the standard delegate emits an error such as `BadOpaqueTokenException`. Thanks to:

~~~java
.cache(
    this::positiveTtl,
    error -> Duration.ZERO,
    () -> Duration.ZERO)
~~~

subscribers **already waiting on that same call** share the error, while subsequent subscriptions get to introspect fresh. This avoids **long-lived negative caching** and keeps `503` errors out of the cache.

However, if a client floods invalid tokens at high speed, uncached negative results generate repeated introspection calls over time. Mitigate with **rate limits, quotas, WAF, bounded concurrency**, and—only if truly required—an ultra-short negative TTL **strictly for confirmed inactive verdicts**, never mixed with network outages.

### 7.4. Be Mindful of Raw Tokens Captured in `Mono`

In:

~~~java
Mono.defer(() -> delegate.introspect(token))
~~~

the lambda **retains a reference to the raw token string** until the Publisher and closure can be garbage-collected. Even though the cache key is an HMAC, the cache entry holding the `Mono` can keep the token in heap for several seconds.

For systems with strict credential-retention requirements:

- Keep TTLs very short and minimize caching.
- Restrict heap dumps and instrumentation.
- Drop references to Publishers as soon as no longer needed.
- Consider an **in-flight registry with explicit cleanup** or caching results without retaining closures holding raw tokens.
- Evaluate in-memory secret exposure against your organization's threat model.

HMAC cache keys reduce token exposure **via cache keys**, not all copies of the token in memory.

## 8. Integrating with Spring Security WebFlux

### 8.1. Configuring the Introspection Endpoint

In `application.yml` for WebFlux opaque tokens:

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

Meaning:

- `introspection-uri`: trusted server-side HTTPS endpoint of the Authorization Server.
- `client-id` and `client-secret`: the **Resource Server's credentials for introspection**, not the user's Access Token.
- `active` must be validated by a standard delegate, not merely by checking HTTP 200.

Never commit client secrets to source control. If using mTLS or an introspection auth method other than Basic, configure the HTTP client and reactive introspector per the actual contract.

### 8.2. Wrapping the Delegate as a Bean

Example when you need to configure the decorator explicitly:

~~~java
import java.time.Clock;
import java.util.Base64;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.introspection.NimbusReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;

@Configuration
public class ReactiveIntrospectionConfig {

    @Bean
    ReactiveOpaqueTokenIntrospector reactiveOpaqueTokenIntrospector(
            @Value("${app.introspection.uri}") String uri,
            @Value("${app.introspection.client-id}") String clientId,
            @Value("${app.introspection.client-secret}") String secret,
            @Value("${app.introspection.cache-key-base64}") String key64) {

        ReactiveOpaqueTokenIntrospector delegate =
            new NimbusReactiveOpaqueTokenIntrospector(
                uri, clientId, secret);

        byte[] hmacSecret = Base64.getDecoder().decode(key64);
        TokenCacheKey keys = new TokenCacheKey(
            hmacSecret,
            "issuer-demo|orders-api|rs-client-v1");

        return new SingleFlightCachingIntrospector(
            delegate, keys, Clock.systemUTC());
    }
}
~~~

Corresponding configuration:

~~~yaml
app:
  introspection:
    uri: https://identity.example.test/oauth2/introspect
    client-id: orders-resource-server
    client-secret: ${INTROSPECTION_CLIENT_SECRET}
    # Base64 value of >=32 random bytes, loaded from secret manager.
    cache-key-base64: ${INTROSPECTION_CACHE_HMAC_KEY_BASE64}
~~~

**This is an explicit replacement setup:** when you declare a custom `ReactiveOpaqueTokenIntrospector` bean, Spring Boot auto-configuration backs off. Therefore, the delegate's URL and credentials must genuinely be read from `app.introspection.*` or an equivalent config source—do not assume Boot still injects `spring.security.oauth2.resourceserver.opaque-token.*` into your custom bean.

`NimbusReactiveOpaqueTokenIntrospector` and that constructor exist across many Spring Security 6.x versions; newer releases provide other implementations/builders (such as `SpringReactiveOpaqueTokenIntrospector`). Pick the introspector API **for your project's version** while preserving the same security invariants. When finer connect/read timeouts are needed, configure the `WebClient`/HTTP client used by the delegate; the outer `Mono.timeout` is an overall bound, not a substitute for network timeouts.

### 8.3. `SecurityWebFilterChain` for an Opaque-Token API

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ApiSecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            // Example pure Bearer-header API without session cookies
            // for authentication. Configure CSRF separately if web login exists.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(
                    HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(
                    HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
~~~

Spring Security picks the reactive introspector bean matching the configuration. When introspection succeeds, principal/authorities are used to create an Authentication for **every request**. Caching must never bypass `authorizeExchange`, method security, or resource-level authorization.

Example flow:

~~~text
GET /api/orders/42
Bearer token introspected active=true
Authority SCOPE_orders.read
        |
        v
HTTP policy passes
        |
        v
Domain policy checks order 42 belongs to user/tenant
~~~

A cached active result does not prove the user's permission on a specific order has not changed.

## 9. Caching and Reactor Context Must Never Be Mixed

In WebFlux, Spring Security uses the **Reactor Context** to carry `SecurityContext` per subscription. Properly reading the current user:

~~~java
ReactiveSecurityContextHolder.getContext()
    .map(context -> context.getAuthentication());
~~~

However, **never cache `ReactiveSecurityContextHolder.getContext()` in a global variable**:

~~~java
// DO NOT DO THIS in a singleton:
private final Mono<SecurityContext> cachedContext =
    ReactiveSecurityContextHolder.getContext().cache();
~~~

If that publisher is first subscribed under user A's context and cached, user B's request could receive **A's `SecurityContext`**. That is a severe vulnerability.

### 9.1. Cache Token Metadata, Never the Current User

Distinction:

| Data | Cache by token with short TTL? | Warning |
| --- | --- | --- |
| Introspection metadata of a specific token | Allowed under policy. | Key by token fingerprint; bound revocation window. |
| Current `SecurityContext` | **Never** cache across requests. | Each subscription has its own principal. |
| `ServerWebExchange` | **Never**. | Tied to an individual request/response lifecycle. |
| HTTP Authorization header | **Never** as a plain cache value. | Bearer secret; only the delegate should see the token. |
| Record owner/tenant permissions | Separate domain cache if truly needed. | Requires invalidation and proper data/identity keys. |
| JWKS public keys for JWT | Different caching problem. | Does not replace opaque introspection or revocation alerts. |

### 9.2. An Ideal Introspector Does Not Need Request `SecurityContext`

A `ReactiveOpaqueTokenIntrospector` takes a **token string** and uses **trusted configuration** to call the Authorization Server. It should interpret the token using configured client credentials and the introspection endpoint, not by reading a "current HTTP user" from `ReactiveSecurityContextHolder` prior to authentication.

If a custom introspector depends on the request's Reactor Context, analyze carefully how `Mono.cache()` **shares one upstream subscription across callers**. Upstream sees the context of **the first subscriber that triggered it**, whereas later subscribers have different contexts. If introspection truly varies by tenant/resource, **include that verified context in the cache key or separate introspector policies**, never relying on implicit context while coalescing requests for the same token.

### 9.3. Thread Scheduling and Detached Subscriptions

`publishOn` and `subscribeOn` switch execution threads per Reactor semantics while **subscriber context still propagates through a properly composed pipeline**. Conversely:

~~~java
// DO NOT DO THIS.
delegate.introspect(token).subscribe();
return Mono.empty();
~~~

creates a **detached subscription** that can lose request context, mishandle errors, and decouple from main-request cancellation. In Spring WebFlux, **return the `Publisher`** and let the framework subscribe; inside cache loaders use `Mono.defer` and intentional `cache`, never `block()` or manual `subscribe()`.

## 10. Cancellation: Does One Canceling Subscriber Cancel Shared Introspection?

Suppose 20 HTTP requests are awaiting one shared introspection `Mono`:

~~~text
Request A ----\
Request B -----\
Request C ------> shared introspection Mono ---> Authorization Server
Request D -----/
...         ---/
~~~

If A closes the browser tab or cancels mid-flight while B/C/D still need the result, a single-flight design **should not abort upstream just because A left**. `Mono.cache()` fits well here: once subscribed and started, the cache operator retains the upstream subscription for the result and replays it to the remaining waiters.

**Consequence:** even if **all** HTTP request subscribers cancel, the upstream introspection call may keep running until completion or timeout. Therefore, enforce:

- **A timeout on the shared source**.
- Instance-wide limits on concurrent introspection calls.
- Caffeine `maximumSize` and bounded TTLs.
- Metrics on in-flight calls and upstream latency.
- Not keeping credentials in closures longer than necessary.

### 10.1. `Mono.cache` and `Mono.share` Are Not Identical

In Reactor 3.x, these operators have distinct semantics:

| Usage | Primary behavior | Trade-off |
| --- | --- | --- |
| `source.cache()` | Retains terminal signal for the object's lifetime. | Easily holds successes/errors indefinitely. |
| `source.cache(Duration)` | Caches terminal signal for a fixed TTL. | Same TTL for success and error; watch out during outages. |
| `source.cache(valueTtl, errorTtl, emptyTtl)` | Varies cache duration by outcome. | Better when you want short success caching and zero error/empty caching. |
| `source.share()` | Shares an in-flight task per Mono share semantics. | When all subscribers cancel, source may cancel; replay differs from `cache()`. |
| `source.publish().refCount(...)` | Shares a Flux source by subscriber count. | Must handle cancellation/reconnection; not a cache policy replacement. |

No operator is "best for every case." For introspection, choose based on **request coalescing, timeouts, revocation risk, and upstream cost**, then test behavior against your exact Reactor version.

### 10.2. Cancellation Is Never a Reason to Treat a Token as Active

If a request cancels while introspection is pending, never emit a fallback `OAuth2AuthenticatedPrincipal` just to keep execution going. If a later request arrives with the same token, it must either use a genuinely verified result per cache policy or introspect again.

In particular, never write:

~~~java
// DO NOT DO THIS: network/timeout errors must not grant privileges.
return delegate.introspect(token)
    .onErrorResume(error ->
        Mono.just(makeAdminPrincipal()));
~~~

Even `BadOpaqueTokenException` signaling an inactive token must be honored; never catch all exceptions and turn them into `active:true`.

## 11. Retries, Circuit Breakers, and Thundering Herds

### 11.1. Retry Before or After Cache?

If you add retries:

~~~java
delegate.introspect(token)
    .retryWhen(...)
    .cache(...)
~~~

subscribers can share **one retrying upstream sequence**; however, retries can still issue **multiple HTTP calls** for the same token. Single-flight does not mean upstream is called "strictly once" when retries are enabled.

Guidelines:

- **Never retry** `active:false` or security invalid-token rejections.
- Retry only classified **transient** errors, such as timeouts or HTTP 503, within a total time cap.
- Use bounded exponential backoff with jitter when needed to avoid retry storms.
- Never retry HTTP 401 caused by wrong introspection client secrets/mTLS indefinitely.
- Never swallow exceptions and return a default principal.
- Keep the retry budget under the API deadline so requests do not hang too long.

When adding Reactor `Retry`, use `filter` accepting only **known upstream network exceptions**. Never slap a blind `retry(3)` around the entire authentication flow, which retries definitely-invalid tokens, amplifies load, and spikes authentication latency.

### 11.2. Thundering Herd on Simultaneous TTL Expiration

Suppose a popular token T has a 5-second cache TTL:

~~~text
T0: 2,000 requests hit cache
T0+5s: Cache entry expires
T0+5.001s: 400 concurrent requests see cache miss
~~~

An **atomic cache get** paired with a **shared `Mono`** collapses those 400 upstream calls into roughly one call **per instance**, provided the entry was not evicted and shares the namespace.

Yet with 20 instances, each instance can still introspect T once: **20 calls**, not one cluster-wide call. To reduce cluster-wide load further, evaluate a distributed cache or cluster-wide concurrency limits with explicit security trade-offs.

### 11.3. Bounded Concurrency

Tens of thousands of distinct tokens should not all trigger concurrent introspection calls unchecked. Single-flight coalesces **the same token key**; distinct tokens still generate load.

Layer your limits:

- Edge/gateway rate limits per client/IP and policy.
- Connection pool + max concurrent upstream requests.
- Timeouts for connect, response, and total introspection.
- Bulkhead/circuit breaker for upstream errors.
- Caffeine `maximumSize` and eviction.
- Metrics/alerts for authentication latency, 429/5xx, and pending requests.

When limiters saturate, **fail closed** or return service errors per contract; never bypass authentication to preserve throughput.

## 12. Upstream Errors and Distinguishing 401/403

A cache layer must never blur the boundary between authentication and authorization.

| Condition | Conclusion | Typical HTTP |
| --- | --- | --- |
| Missing Bearer token | Unauthenticated. | **401**, Bearer challenge. |
| Introspection returns `active:false` | Token rejected. | **401 invalid_token** with matching handler. |
| Introspection timeout / 503 | Unable to verify credential. | **Fail closed**; status may be 5xx/503 per handler. |
| Active token missing `SCOPE_orders.read` | Authenticated, lacks endpoint permission. | **403 insufficient_scope** for OAuth scope rules. |
| Active token with scope, wrong owner/tenant | Domain policy denies. | **403/404**, not necessarily `insufficient_scope`. |
| Cached active token recently revoked upstream | Positive-cache staleness window. | May pass within TTL; requires accepted risk. |

**Never mechanically mirror the introspection endpoint's HTTP status as the API's HTTP status.** For example, an Authorization Server returning **HTTP 401** when the Resource Server sends a wrong client secret is a **Resource Server credential failure**, not proof the user's token expired.

### 12.1. Never Use Stale-on-Error Blindly for Tokens

An ordinary HTTP cache might serve **stale data when upstream fails**. For token introspection, logic like:

~~~text
Introspection 503 -> reuse old active=true even after TTL expired
~~~

breaks your revocation window bounds. If you ever want **stale-while-revalidate** or fallback caching during an IdP outage, it must be an **explicitly approved security policy** with strict max age, endpoint restrictions, and documented risk—never a safe default. For sensitive endpoints, choose **rejecting tokens whenever verification is unavailable**.

### 12.2. Separating Error Metrics

Separate them:

~~~text
introspection_success_active
introspection_token_inactive
introspection_timeout
introspection_http_401_client_credentials
introspection_http_429_rate_limited
introspection_http_503
introspection_invalid_json
authorization_insufficient_scope
authorization_domain_denied
~~~

Never use raw tokens or HMAC digests as metric labels. Log request correlation IDs per security policy without logging introspection HTTP request bodies containing tokens or Basic Authorization client secrets.

## 13. Multiple Replicas: Local vs. Distributed Caching

### 13.1. Per-JVM Local Cache

Pros:

- Adds no network dependency for the cache itself.
- Caffeine lookups are fast and atomic per key within one instance.
- Keeps token results out of Redis or shared databases.
- Easy to bound memory and entry lifetimes.

Cons:

- Each replica maintains a separate cache.
- The first request for a token on each replica can trigger an introspection call.
- On revocation, invalidation must reach **every replica** to shrink staleness sooner than the TTL.
- Load balancer distribution lowers hit rates if tokens rarely repeat on the same replica.

This is why **in-process single-flight cannot promise cluster-wide exactly-once execution**.

### 13.2. Distributed Caches Require Extra Security Boundaries

If using Redis or a distributed cache, account for:

1. **Encryption in transit and at rest** per policy.
2. Never using raw Access Tokens as keys logged or monitored.
3. Namespaces encoding issuer, introspection client, resource, and policy version.
4. Absolute TTLs never exceeding token expiration or the revocation SLA.
5. How invalidations reach nodes when tokens are revoked or client policies change.
6. Preventing collisions across distinct tokens or Authorization Servers.
7. Never skipping `active`, audience, token type, scope, and domain policy checks.
8. Proper leases and fencing for distributed locks/single-flight if truly used, so dead instances do not wedge keys.
9. Cache outages must never allow unverified tokens through.
10. Restricting access to the cache and PII in introspection responses.

**Distributed caching is not automatically better.** For introspection, many systems prefer a very short local cache + single-flight + upstream rate limits to contain risk rather than managing a complex distributed cache full of authentication metadata.

### 13.3. Keys Scoped by Resource and Policy

Consider the same token T:

~~~text
orders-api introspection:
  active=true, aud=orders-api, scope=orders.read

billing-api introspection:
  active=false (not in audience/introspection scope)
~~~

If a distributed cache is keyed only by token digest without isolating **resource identity**, `billing-api` could mistakenly reuse `orders-api`'s active result. Keys and policies must include explicit namespaces, and **each Resource Server must evaluate its own audience/resource checks**.

## 14. Testing Single-Flight with Reactor Test

Before testing Spring Security HTTP, test **multiple subscribers sharing one `Mono`** directly. JUnit 5 example:

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReactorSingleFlightTest {

    @Test
    void concurrentSubscribersShareOneUpstreamSubscription() {
        AtomicInteger upstreamSubscriptions =
            new AtomicInteger();
        Sinks.One<String> gate = Sinks.one();

        Mono<String> source = Mono.defer(() -> {
            upstreamSubscriptions.incrementAndGet();
            return gate.asMono();
        });

        Mono<String> shared = source.cache();
        List<String> results = new CopyOnWriteArrayList<>();

        // Both subscriptions registered before
        // the source emits a terminal signal.
        shared.subscribe(results::add);
        shared.subscribe(results::add);

        assertEquals(1, upstreamSubscriptions.get());

        gate.tryEmitValue("active");
        assertEquals(
            List.of("active", "active"), results);
    }
}
~~~

This test illustrates **`Mono.cache()` sharing an in-flight source**. It does not verify TTLs, revocation, or Spring Security behavior, and uses unbounded `cache()` solely within a local test object.

### 14.1. Testing Success TTLs and Ensuring Errors Are Not Cached Long

For the Caffeine decorator in Section 7, cover these cases:

| Test | What to prove |
| --- | --- |
| Two subscriptions for the same token while source is pending | Delegate is subscribed only once per instance. |
| Two subscriptions for **different tokens** | Delegate is called separately; principals/authorities never mix. |
| Active token with distant `exp` | Result is shared within configured TTL. |
| Token close to `exp` | TTL does not extend past `exp`. |
| Response missing `exp` | Per example policy, result is not cached after completion. |
| Introspection `active:false` | Waiting subscribers share the error; never becomes a principal. |
| Upstream 503/timeout | Error is not cached long-term; next call can retry fresh. |
| More than `maximumSize` tokens | Cache stays bounded and evicts entries. |
| With `retryWhen` | HTTP introspection call count reflects retry policy; inactive is never retried. |
| Subscriber A cancels, B still waits | B receives result per shared source behavior. |
| All subscribers cancel | Shared source still times out; never hangs forever. |

### 14.2. Testing with a Fake `ReactiveOpaqueTokenIntrospector`

Fixture simulating slow introspection:

~~~java
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;

AtomicInteger calls = new AtomicInteger();
Sinks.One<OAuth2AuthenticatedPrincipal> gate = Sinks.one();

ReactiveOpaqueTokenIntrospector delegate = token ->
    Mono.defer(() -> {
        calls.incrementAndGet();
        return gate.asMono();
    });

OAuth2AuthenticatedPrincipal principal =
    new DefaultOAuth2AuthenticatedPrincipal(
        "person-A",
        Map.of(
            "sub", "person-A",
            "scope", "orders.read",
            "exp", Instant.now().plusSeconds(60)),
        List.of(new SimpleGrantedAuthority(
            "SCOPE_orders.read")));

// Then create SingleFlightCachingIntrospector with
// a test HMAC TokenCacheKey and Clock.systemUTC().
// Two subscriptions for the same opaque token
// both await gate.asMono(), then:
gate.tryEmitValue(principal);
// assert: calls == 1, both receive principal.
~~~

This snippet is an **illustrative fixture**, not a full test method with all assertions. Generate a dedicated test HMAC secret; never copy production secrets. `Mono.defer` ensures `calls` increments on actual delegate subscription rather than lambda creation.

### 14.3. Testing That Errors Are Not Cached

A fake delegate can return:

~~~java
AtomicInteger calls = new AtomicInteger();

ReactiveOpaqueTokenIntrospector delegate = token ->
    Mono.defer(() -> {
        int attempt = calls.incrementAndGet();
        if (attempt == 1) {
            return Mono.error(
                new RuntimeException("simulated timeout"));
        }
        return Mono.just(testPrincipal());
    });
~~~

Here `testPrincipal()` is a test helper returning a valid fixture `OAuth2AuthenticatedPrincipal`. Through a cache with `errorTtl=Duration.ZERO`, the first subscription receives the error; the next call invokes the delegate again and succeeds. **Never** substitute a timeout error with an admin user.

In production-like tests, use the concrete HTTP client/introspection exception classes to verify error classification. A `RuntimeException("simulated timeout")` merely demonstrates that error signals are not cached.

## 15. Testing Spring WebFlux HTTP with `WebTestClient`

`spring-security-test` supports reactive security testing. Example:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOpaqueToken;

webTestClient
    .mutateWith(mockOpaqueToken().authorities(
        new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk();
~~~

**`mockOpaqueToken()` injects a fake Authentication**—it sends no HTTP introspection and does not test `active`. It works well for testing **`authorizeExchange`** or domain policies when fixture order 42 exists. Without a matching controller or data, the actual status may be 404 instead of 200 even when authorization passes.

### 15.1. Testing Real Introspection with a Mock Authorization Server

To test caching/single-flight **at the HTTP boundary**, stand up a fake introspection endpoint:

~~~text
POST /oauth2/introspect
token=active-reader
  -> HTTP 200
     {"active":true,"scope":"orders.read",
      "sub":"person-A","aud":["orders-api"],"exp":...}

token=inactive
  -> HTTP 200 {"active":false}

token=upstream-503
  -> HTTP 503 Service Unavailable
~~~

Procedure:

1. Start WireMock, MockWebServer, or a local HTTP test server.
2. Configure the **real `ReactiveOpaqueTokenIntrospector`** pointing to the test endpoint.
3. Send `Authorization: Bearer active-reader` via **`WebTestClient`**—**without `mockOpaqueToken()`**.
4. Send concurrent requests with the same token; count POST requests received by the mock introspection endpoint.
5. Verify call counts drop per single-flight/cache policy and principal/scopes are accurate.
6. Switch the mock response to `active:false`, advance past TTL via test clock or wait per policy, and confirm **401**.
7. Test a second token sharing `sub` with different scopes; ensure authorities never bleed across.
8. Test timeouts/503s and bad introspection credentials; ensure requests never proceed as authenticated.

**Note:** plain HTTP on localhost without TLS is strictly for isolated test environments. Production connections to the Authorization Server must enforce HTTPS and certificate/hostname verification.

### 15.2. HTTP 401/403 Matrix

| State | Outcome |
| --- | --- |
| No Bearer token to an endpoint requiring authentication | **401**. |
| Introspection returns `active:false` | **401 invalid_token** with matching handler. |
| Active introspection missing `orders.read` | **403**. |
| Active introspection with `orders.read`, order belongs to another tenant | **403/404** per domain policy. |
| Token cached active, just revoked upstream | May be temporarily accepted during TTL; test the bound. |
| Revoked token after cache TTL | Must re-introspect and reject. |
| Introspection service 503 | Fail closed; operational error status depends on handler, never authorization success. |

## 16. Observing Performance Without Leaking Data

Track:

- **Cache hit rate**: cache reuses vs. cache lookups.
- **Single-flight deduplication ratio**: waiting callers vs. upstream introspection calls.
- **Introspection request rate** and p50/p95/p99 latency.
- **In-flight upstream requests** and timeout counts.
- **Cache size**, evictions, and memory/allocation overhead.
- **401 inactive**, **403 insufficient_scope**, Resource Server credential failures, and upstream 429/503s.
- Observable revocation lag in tests and operational checks.

**Never attach tokens or HMAC digests to metric labels.** High-cardinality values inflate cost and can disclose identities/credentials. Use error categories, logical endpoint names, configured issuer IDs, and region/node IDs instead.

### 16.1. Avoid Optimizations That Amplify Load

If the introspection timeout is set too long (e.g., 60 seconds) and many distinct tokens miss the cache, tens of thousands of pending requests can pile up, pinning HTTP connections and memory. Single-flight only helps **repeated identical tokens**; it does not replace max in-flight limits, timeouts, quotas, and circuit breakers.

### 16.2. Measure Before Picking a TTL

Practical questions:

1. How many requests per second use an average Access Token?
2. How many **unique tokens** are active concurrently?
3. What are the mean and p99 HTTP introspection latencies?
4. How many QPS per resource client does the Authorization Server allow?
5. How quickly must revocations take effect?
6. Are there sensitive API operations where active caching should be disabled?
7. How many replicas exist and does the load balancer distribute evenly?

From these metrics, balance short cache TTLs, per-node single-flight, rate limits, and Authorization Server capacity. Never choose a huge TTL merely to mask an under-provisioned or failing introspection endpoint.

## 17. Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling `delegate.introspect(token).cache()` fresh per HTTP request. | Each request creates its own `Mono`, **no cross-request coalescing**. | Use a registry keyed by token fingerprint. |
| Keying cache by `sub` or `client_id`. | Mixes scopes, audiences, and revocation across tokens. | Key by token + namespace. |
| Caching `OAuth2AuthenticatedPrincipal` forever. | Revoked/expired tokens keep working. | Short TTL bounded by `exp` and revocation SLA. |
| Caching all errors via unbounded `Mono.cache()`. | Outages keep replaying even after IdP recovers. | Zero error TTL or explicit error policy. |
| Caching HTTP 503 as `active:false`. | Confuses upstream outages with invalid tokens. | Classify errors, fail closed, separate metrics. |
| Returning a default principal on introspection timeout. | **Fail-open** and unauthorized access. | Never construct Authentication when unverified. |
| Putting raw tokens in logs or cache metrics. | Leaks Bearer credentials. | HMAC token fingerprint; never log keys or digests. |
| Assuming HMAC clears tokens from the heap. | Cache lambdas can still retain raw tokens. | Short TTL, bounded memory, restrict heap dumps. |
| Omitting resource/issuer context from cache namespace. | Reuses one API's active verdict on another API. | Isolate cache by trust domain and audience. |
| Caching `ReactiveSecurityContextHolder.getContext()` in a singleton. | Leaks Authentications across requests. | Cache token metadata, never current user context. |
| Manual `subscribe()` in loader/controller. | Detached subscription; loses context/error/cancel coordination. | `Mono.defer` and composition; let WebFlux subscribe. |
| `block()` waiting on cache futures on the event loop. | Blocks event loop, spikes latency/timeouts. | Use reactive cache APIs / `Mono`. |
| Assuming `Mono.cache` cancels source when callers cancel. | Upstream can keep running with nobody waiting. | Shared-source timeouts and concurrency bounds. |
| Retrying every error. | Retries inactive tokens and bad credentials, adding load. | Retry only transient failures within a budget. |
| Assuming single-flight spans all replicas. | Every node still calls introspection. | Measure cluster QPS; decide local vs. distributed policy. |
| Treating `active:true` as access to every order. | BOLA/IDOR, cross-tenant exposure. | Independent scope + owner/tenant checks. |
| Testing only `mockOpaqueToken()` and assuming caching works. | Helper skips real introspection. | Mock HTTP server + assert POST counts and active transitions. |
| Assuming client disconnect aborts upstream immediately. | Shared source can keep running and holding resources. | Timeouts, eviction, and cancellation tests. |

## 18. Adoption Steps for a Resource Server Project

1. **Confirm the token contract:** opaque Access Token, introspection endpoint, issuer/resource/audience, `scope`, `exp`, `active`, and revocation policy.
2. **Configure WebFlux security properly:** `SecurityWebFilterChain` + `ReactiveOpaqueTokenIntrospector`; HTTP and method authorization still run per request.
3. **Measure real traffic:** token reuse frequency, unique-token cardinality, request concurrency, introspection latency, and error rates.
4. **Pick a revocation SLA:** how long may an active token still be accepted after the AS revokes it? TTL must stay below that limit.
5. **Design safe cache keys:** HMAC token fingerprint plus server-controlled issuer/resource namespace—never key by user or email.
6. **Coalesce concurrent misses:** atomic `Cache.get` returning a shared `Mono`, using `Mono.defer` and outcome-specific `cache` TTLs.
7. **Bound the result cache:** short positive TTL never exceeding `exp`; never cache errors/empty long-term; cap max entries.
8. **Classify upstream failures:** `active:false` differs from timeouts/503s/client-credential 401s; all unverified failures must fail closed.
9. **Design cancellation and retries:** timeout inside the shared source; retry only transients; prevent stampedes during misses.
10. **Isolate business permissions:** local account, tenant, owner, and order state must be checked against live data, never solely from cached principals.
11. **Test single-flight and TTLs:** `StepVerifier`/Sinks to prove one upstream subscription, fake introspectors/HTTP test servers to count calls, and revoked tokens tested before/after TTL.
12. **Evaluate multiple replicas:** local cache QPS, invalidation, and whether a distributed cache is truly justified with its own security boundaries.
13. **Protect observability and secrets:** never log Bearer tokens or introspection credentials; track cache/timeout/401/403 metrics without credentials.

**Remember:** For **reactive introspection**, proper optimization is not merely adding `Mono.cache()`. Distinguish **result caching** from **single-flight in-flight deduplication**, build a **safe token-identity registry**, enforce **short TTLs bounded by `exp` and revocation policy**, **never cache upstream errors as active verdicts**, and **never reuse `SecurityContext` across requests**. `ReactiveOpaqueTokenIntrospector` remains the authentication boundary; `authorizeExchange` and domain policies still govern access to every endpoint and resource.

## References

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662).
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009).
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750).
- [Spring Security — Reactive OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html).
- [Spring Security — ReactiveOpaqueTokenIntrospector API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html).
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html).
- [Spring Security — Reactive Security Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html).
- [Project Reactor — Mono API, cache operators](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html).
- [Project Reactor — Reactor 3 Reference Guide](https://projectreactor.io/docs/core/release/reference/).
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html).
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html).
- [Caffeine — Java Cache library](https://github.com/ben-manes/caffeine).
- [OWASP — API Security Top 10 (2023)](https://owasp.org/API-Security/editions/2023/en/0x00-header/).
