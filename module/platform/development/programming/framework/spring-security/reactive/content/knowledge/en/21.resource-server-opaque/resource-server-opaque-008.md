# Designing Timeouts and Caching Around Token Revocation Requirements

**Module:** Spring Security – reactive (Spring WebFlux)  
**Section:** Resource Server Opaque  
**Goal:** Build a bounded-time token introspection policy with controlled caching and prove via tests that **token revocation takes effect within an agreed time window**, without silently allowing requests when the Bearer token cannot be verified.

**Most important principle:** Token introspection is a **current-state** check at the Authorization Server (AS), yet every AS call consumes network latency and capacity. Caching `active=true` results reduces load while retaining authorization decisions that may **already be stale after revocation**. Choose the cache TTL from your **revocation SLA** and the token's `exp`, rather than setting TTL to the access token's entire lifetime. If stale decisions are unacceptable, set **positive cache TTL = 0** and introspect on every request; even then, account for AS propagation delay and in-flight requests. In all cases, when introspection cannot verify a token due to timeouts, network errors, or AS outages, default to **fail-closed**: never convert an unknown outcome into an authenticated principal.

This lesson covers RFC 7662 mechanics, design formulas, timeouts/circuits/retries, bounded caching, Java 17+ Spring Security WebFlux configuration, a standalone runnable example with exact stdout, fake-clock unit tests, and WebFlux HTTP tests. Example credentials/tokens are test fixtures, not production secrets.

## 1. What Does an Opaque Resource Server Verify?

A client sends a request to the Resource Server:

```http
GET /api/document HTTP/1.1
Host: docs.example.test
Authorization: Bearer opaque-token-value
```

In opaque token mode, `ReactiveOpaqueTokenIntrospector` receives the token string and performs introspection over HTTPS against the AS. Example backend request:

```http
POST /oauth2/introspect HTTP/1.1
Host: idp.example.test
Authorization: Basic <encoded-resource-server-client-credentials>
Content-Type: application/x-www-form-urlencoded

token=opaque-token-value
```

The AS returns the status result:

```json
{
  "active": true,
  "sub": "alice",
  "scope": "docs.read docs.write",
  "client_id": "approved-client",
  "exp": 1790000000
}
```

Spring Security reads the valid response, builds an `OAuth2AuthenticatedPrincipal`, and maps scopes to `SCOPE_docs.read` and `SCOPE_docs.write`. Then WebFlux authorization rules decide whether to enter the handler.

```text
Client
  |
  | Authorization: Bearer <token>
  v
WebFlux SecurityWebFilterChain
  |
  v
ReactiveOpaqueTokenIntrospector.introspect(token)
  |
  | HTTP POST, introspection credentials, TLS
  v
Authorization Server
  |
  | {"active": true, "scope": "docs.read", "exp": ...}
  v
OAuth2AuthenticatedPrincipal, GrantedAuthority SCOPE_docs.read
  |
  v
authorizeExchange.hasAuthority("SCOPE_docs.read")
  |
  +--> 200: active and sufficient permissions
  +--> 401: missing/invalid token
  +--> 403: active but insufficient scope
```

If the token has been revoked, the AS may return:

```json
{"active": false}
```

Per RFC 7662, an `active=false` response can be **HTTP 200 from the introspection endpoint itself**. This **does not mean** the API should return 200: the Resource Server must treat the Bearer token as invalid, typically returning **401** to the API caller. Never log raw Bearer tokens or introspection client secrets.

### 1.1. Opaque Refers to the Verification Method, Not Only String Format

Whether the access token is an unreadable string or a structured JWT, if the Resource Server sends the token to the AS to query `active`, it is using **introspection**. A JWT verified offline via signature can still be revoked before `exp`; therefore, if the system requires early revocation, checking only the JWS signature/`exp` is usually insufficient. You can either introspect JWTs as opaque tokens, or design a dedicated trusted denylist/event/permission-version mechanism.

**Do not confuse with OIDC ID Tokens:** An ID Token serves the Relying Party in authenticating a login event. A Resource Server must require an **access token** with the right audience, issuer, scopes, and policy; never accept an ID Token merely because it also looks like a JWT.

### 1.2. Spring Defaults and Extension Points

Minimal Boot configuration:

```properties
spring.security.oauth2.resourceserver.opaquetoken.introspection-uri=https://idp.example.test/oauth2/introspect
spring.security.oauth2.resourceserver.opaquetoken.client-id=resource-server-client
spring.security.oauth2.resourceserver.opaquetoken.client-secret=issued-secret
```

In WebFlux, `SpringReactiveOpaqueTokenIntrospector` performs the HTTP request reactively. Its contract:

```java
public interface ReactiveOpaqueTokenIntrospector {
    Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
}
```

The minimal configuration does not automatically provide a **bounded cache with a TTL aligned to your revocation SLA**. If you need custom timeouts, retries, caching, or invalidation, declare a `@Bean ReactiveOpaqueTokenIntrospector` or pass an explicit introspector into `oauth2ResourceServer(o -> o.opaqueToken(...))`.

**Do not copy Servlet APIs:** `HttpSecurity`, `OpaqueTokenIntrospector`, and `RestTemplate` belong to the synchronous/Servlet family. For this lesson, use `ServerHttpSecurity`, `SecurityWebFilterChain`, `ReactiveOpaqueTokenIntrospector`, `WebClient`, and Reactor.

## 2. Token Revocation Is a Product Requirement, Not Just a Cache Setting

Before choosing a TTL, answer these questions:

1. Are you revoking a single access token, all tokens for a user, a client ID, a device session, or all permissions of a tenant?
2. After how many seconds at most must a revoked token stop being **accepted at the API**?
3. How long does it take the AS for `active=false` to become visible across **all introspection replicas / regions**?
4. Should requests authenticated **before revocation** and currently in flight be allowed to finish?
5. Do endpoints vary in sensitivity (reading summary data vs. financial transactions or admin actions)?
6. Are revocation/invalidation events authenticated, delivered to every Resource Server instance, and backed by reconciliation?
7. During an IdP outage, is it acceptable to reject requests to auth-protected APIs?
8. Does token introspection return `exp`, `aud`, `sub`, and `scope` with consistent data types and SLAs?
9. How many entries are cached—many short-lived tokens or the same token called repeatedly? What are actual QPS and tail latency?
10. Could a multi-issuer/multi-tenant system accidentally reuse a cache entry across the wrong security domain?

**A token with `exp` 60 minutes away does not justify caching `active=true` for 60 minutes.** `exp` is a hard expiration boundary; revocation before `exp` is precisely what caching can mask.

### 2.1. Revocation Budget Formula

Notation:

- `T_c`: maximum TTL of a cached positive decision.
- `T_as`: delay for the AS to apply/propagate revocation to all introspection nodes.
- `T_event`: invalidation event delay (if event-driven).
- `T_inflight`: completion time for requests already authenticated before revocation.
- `T_margin`: clock skew, scheduling, and safety margin.
- `SLA_revocation`: maximum policy-permitted time before revocation is observed.

Conservative budget model:

```text
window_max ~= T_c + T_as + T_event + T_inflight + T_margin

T_c <= SLA_revocation
       - T_as - T_event - T_inflight - T_margin
```

This is a **guiding calculation**, not a formula guaranteed by Spring Security. Without a reliable upper bound on `T_as` or event latency, you cannot promise a hard SLA using TTL alone.

Hypothetical examples:

| Surface | Revocation SLA | AS + Inflight + Margin | Remaining Max TTL | Approach |
| --- | ---: | ---: | ---: | --- |
| Sensitive admin actions | 1 second | 1 second | 0 seconds | No positive cache; check policy at commit time |
| Internal document API | 12 seconds | 4 seconds | 8 seconds | Max TTL 8 seconds; keep extra headroom |
| Low-sensitivity read-only | 90 seconds | 20 seconds | 70 seconds | TTL below 70 seconds if approved |
| Unmeasured AS propagation | Unbounded | Unknown | Cannot derive | Do not claim a revocation SLA |

**Sample math:** 10s SLA minus 3s AS propagation minus 2s inflight + margin => 5s cache budget.

### 2.2. Per-Entry TTL Must Be Capped by exp

Suppose a request introspects successfully at `now` for a token with `exp`:

```text
entry.validUntil = min(now + positiveCacheTtl, exp)
```

If the cache policy is 5 seconds while the token has 2 seconds left until `exp`, the **effective TTL is only 2 seconds**. If the token's `exp` has passed, never use the principal. If the introspection response lacks `exp` or its `exp` type is not properly understood, a safe policy is **no positive caching**; always re-query the AS on the next request.

TTL should be measured from **the successful introspection**, not from `iat`. Never cache errors/`active=false` and reuse them as authenticated principals.

### 2.3. Why TTL=0 Still Does Not Mean "Absolute Instant Revocation"

Cache TTL=0 makes **new requests** call the AS, yet you still face:

- AS eventual consistency / multi-region replication.
- In-flight requests already authorized prior to revocation.
- Reverse proxies/gateways or upstream auth layers that may hold separate caches.
- Background jobs, long-lived connections, or WebSockets holding authorization from connection start.
- Asynchronous revocation where a successful revoke response does not mean every AS replica is updated yet.

For highly sensitive permissions, you may need user/permission versioning, denylists/re-checks at commit time, session termination, and transaction-level policies rather than checking the token once at HTTP request entry.

## 3. Latency Budget and Timeouts: Tuning for the Real IdP Path

Never let an external introspection call hang for tens of seconds and exhaust thread/connection pools. In Reactor/WebFlux, distinguish these bounds:

| Limit | What It Bounds | Example |
| --- | --- | --- |
| DNS resolution | Resolving the IdP hostname | Environment-appropriate resolver timeout/cache |
| TCP connect | Establishing connection | `CONNECT_TIMEOUT_MILLIS` |
| TLS handshake | Establishing secure channel | TLS timeout + truststore |
| Connection acquire | Waiting for a pooled connection | Pool `pendingAcquireTimeout` |
| Response time | Waiting for HTTP response | Reactor Netty `HttpClient.responseTimeout` |
| **Overall introspection deadline** | Total publisher across network/delegate steps | Reactor `Mono.timeout(Duration)` |
| API request deadline | Authentication + business + response | Ingress/client timeout |
| Retry/timeouts | Multiple attempts and backoff | Total retries must fit inside deadline |
| Bulkhead/circuit | Blast radius when IdP slows/fails | Bounded concurrency, fail-closed |

**Illustrative budget**, not universally suitable for every system:

```text
API p99 goal                  900 ms
Business/response budget      250 ms
IdP introspection total       550 ms
Reserve                       100 ms

TCP connect ceiling           150 ms
Response wait ceiling         350 ms
Whole introspection deadline  550 ms
Automatic retry               OFF
```

`Mono.timeout` bounds from subscription to Mono completion; it does not replace network pool/TLS timeouts, though it provides a clear overall ceiling. `HttpClient.responseTimeout` bounds waiting specifically for the response. A connection can spend time waiting on the pool/DNS/TLS before reaching the response phase; hence an **overall deadline** is essential.

### 3.1. Timeouts Differ from Invalid Tokens

- Introspection yields `active=false`: **invalid token**, typically API 401.
- AS unreachable, DNS/TLS error, deadline exceeded, AS 429/5xx: **token state unknown**, hence fail-closed—never treat as authenticated.
- AS rejects introspection client credentials: configuration/operational failure, **not** proof the user token is inactive.
- Active token lacking `SCOPE_docs.write`: API **403** per authorization policy.

**Do not promise every timeout automatically returns 503.** The HTTP status for dependency errors depends on Spring Security exception translation/custom handlers. If you need HTTP 503 (service unavailable) instead of 401/500, implement a controlled mapping and test it at the ingress. What must never change is that requests with an **unverified** Bearer token must never enter protected handlers.

### 3.2. Retries Can Make Outages Worse

Never blindly retry `active=false`, invalid tokens/clients, or 4xx errors. For 429/502/503/network timeouts, a short retry with backoff/jitter may be considered, provided you:

- Keep total attempts + delays **within** the deadline.
- Respect provider policies and `Retry-After`.
- Prevent retry storms when the IdP is overloaded.
- Never create fail-open/stale-after-expiry bypasses when a circuit breaker opens.
- Emit reason-tagged metrics and disable retries by default until measurements justify them.

If the AS goes down for several minutes, the safe posture is for the protected API to reject/stop serving temporarily, never extending cache TTLs indefinitely just to keep 200 rates up.

## 4. Cache Design: Positive-Only, Bounded, and Revocable

| Introspection Result | Should It Be Cached? | Notes |
| --- | --- | --- |
| `active=true`, principal/scopes accepted by AS | **Possibly** | Max TTL per SLA, capped by `exp` |
| `active=false` | Not in this sample | Negative caching has its own risks and requires explicit design |
| Timeout, DNS/TLS/network error | No | Unknown whether token is active or revoked |
| AS 401/403 from wrong introspection credentials | No | Server-to-server failure |
| AS 429/5xx | No | Dependency unavailability is not authenticated |
| Empty Mono / malformed response | No | No valid principal |
| Cached principal past `validUntil` | No | Must re-introspect |
| Token `exp` has passed | No | Never exceed hard expiry |
| Trusted revocation event | Invalidate entry when possible | Event delivery/races must be tested |
| Token from another issuer/tenant | Never share | Partition namespaces and policies |

### 4.1. Ban Unbounded Last-Known-Good Patterns

```java
// ANTI-PATTERN: EXTREMELY DANGEROUS for protected data.
return idp.introspect(token)
    .onErrorResume(ex -> Mono.just(lastKnownGoodPrincipal));
```

This turns an AS outage into a **revocation bypass**. Likewise, `Mono.cache()` or a map caching entire Monos per token without size/TTL/error policies can:

- Cache errors or cache successes indefinitely.
- Keep plaintext tokens as keys in heap/logs.
- Grow cardinality until memory exhaustion.
- Mix results across different AS instances/tenants.
- Prevent invalidation after revocation.
- Conflate network errors with invalid tokens.

### 4.2. What Properties Does a Safer Positive Cache Need?

- **Bounded size:** `maximumSize`/eviction to stop attackers from flooding with endless distinct tokens.
- **Positive-only:** cache only verified `onNext` outputs of `delegate.introspect(token)`; errors are never cached.
- **TTL:** `min(now + maxAge, token.exp)` and check the deadline on every hit.
- **TTL = 0 option:** disable positive caching for endpoints requiring fresh checks.
- **No raw bearer keys:** keys use an HMAC digest with a dedicated secret to limit token exposure in heap/cache debugging; principals remain sensitive data.
- **Isolation:** partition by issuer/AS/tenant and client registration; this sample uses a single AS.
- **Trusted invalidation:** entries can be evicted when the AS sends a trusted revocation event, provided events reach every pod.
- **Failure behavior:** no stale-on-error; once an entry expires while the AS is down, requests are not authenticated.
- **Concurrency:** simultaneous cache misses for the same token can cause a stampede; production needs bounded single-flight/backpressure/circuit breakers when metrics indicate it.

### 4.3. Caffeine and Token Expiry

`Caffeine.expireAfterWrite(maxAge)` puts a physical-time ceiling on entries. However, **each token has its own `exp`**. Store `validUntil` separately and check it on hit:

```text
Caffeine physical expiration: at most policy maxAge
Entry validUntil: min(now + policy maxAge, exp)
Allowed cache hit: clock.now < validUntil
```

If `maxAge=0`, do not call `cache.put`. Multi-pod deployments with local Caffeine caches each have their own stale windows; local `invalidate(token)` does not broadcast automatically. If the Revocation API supplies only `jti`/session IDs, maintain a reverse index or denylist by trusted ID (never send raw Bearer tokens over event buses).

## 5. Standalone Java 17: Calculating the TTL Budget with Exact Stdout

Run a Spring-free program to understand the formula. This is an arithmetic model, **not** a replacement for real introspection.

Save `RevocationBudgetDemo.java`:

```java
import java.time.Duration;
import java.time.Instant;

public class RevocationBudgetDemo {
    static Duration cacheBudget(
            Duration sla, Duration asPropagation,
            Duration inflightAndMargin) {

        Duration remain = sla.minus(asPropagation)
            .minus(inflightAndMargin);

        return remain.isNegative()
            ? Duration.ZERO : remain;
    }

    static Duration actualEntryTtl(
            Instant now, Instant exp, Duration maxTtl) {

        Duration remaining = Duration.between(now, exp);
        if (remaining.isNegative() || remaining.isZero()) {
            return Duration.ZERO;
        }
        return remaining.compareTo(maxTtl) < 0
            ? remaining : maxTtl;
    }

    public static void main(String[] args) {
        Duration budget = cacheBudget(
            Duration.ofSeconds(10),
            Duration.ofSeconds(3),
            Duration.ofSeconds(2));

        Instant now = Instant.parse("2026-01-01T00:00:00Z");
        Duration entry = actualEntryTtl(
            now, now.plusSeconds(2), budget);

        System.out.println("cacheBudget=" + budget);
        System.out.println("entryTtl=" + entry);
        System.out.println("strict=" +
            cacheBudget(Duration.ofSeconds(1),
                Duration.ofSeconds(2), Duration.ZERO));
    }
}
```

Run with JDK 17+:

```bash
javac RevocationBudgetDemo.java
java RevocationBudgetDemo
```

**Exact stdout:**

```text
cacheBudget=PT5S
entryTtl=PT2S
strict=PT0S
```

**Explanation:** A 10s revocation SLA minus 3s AS propagation and 2s inflight/margin leaves a 5s cache budget. Yet a token with only 2s left to live can be cached for at most 2s. A 1s SLA when AS propagation takes 2s leaves zero budget: TTL must be 0, and even then a hard SLA cannot be guaranteed if the AS takes 2s.

## 6. Complete Illustrative Java 17+ Spring Boot WebFlux Project

The project includes a Bearer-only WebFlux Resource Server, a `ReactiveOpaqueTokenIntrospector` with `WebClient` timeouts, and a Caffeine positive-cache wrapper. Tests cover fake-clock logic and `WebTestClient` HTTP calls; no real Authorization Server is required to run the sample tests.

```text
opaque-cache-timeout/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/opaque/
    │   │   ├── OpaqueApplication.java
    │   │   ├── RevocationBoundIntrospector.java
    │   │   ├── SecurityConfig.java
    │   │   └── DocumentController.java
    │   └── resources/application.properties
    └── test/java/demo/opaque/
        ├── RevocationBoundIntrospectorTests.java
        └── OpaqueHttpTests.java
```

**Dependency baseline:** Spring Boot 3.5.7, Java 17+, and Maven 3.9+. In real production deployments, select a currently supported release and apply security patches rather than pinning tutorial versions indefinitely. Do not add `spring-boot-starter-web`, because this lesson uses WebFlux/reactive rather than Servlet.

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>opaque-cache-timeout</artifactId>
    <version>1.0.0</version>
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
            <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
        </dependency>
        <dependency>
            <groupId>com.github.ben-manes.caffeine</groupId>
            <artifactId>caffeine</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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
```

`src/main/resources/application.properties`:

```properties
spring.application.name=opaque-cache-timeout
server.port=8080

# IdP/credentials placeholder: replace with real approved endpoint, ID, and secret.
demo.introspection.uri=https://idp.example.invalid/oauth2/introspect
demo.introspection.client-id=resource-server-training
demo.introspection.client-secret=${INTROSPECTION_CLIENT_SECRET:training-not-valid}

# Demo figures, not default choices for every product.
demo.introspection.connect-ms=150
demo.introspection.response-ms=350
demo.introspection.deadline-ms=550
demo.introspection.cache-ms=2000
demo.introspection.max-entries=10000
```

`demo.introspection.cache-ms=0` disables the positive cache. Do not assume disabling the cache solves AS eventual consistency or in-flight requests. The client secret here is **only for authenticating the Resource Server to the AS introspection endpoint**, not a token or user password. In production, use a secret manager and HTTPS trust configuration.

`src/main/java/demo/opaque/OpaqueApplication.java`:

```java
package demo.opaque;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OpaqueApplication {
    public static void main(String[] args) {
        SpringApplication.run(OpaqueApplication.class, args);
    }
}
```

### 6.1. RevocationBoundIntrospector.java

The wrapper uses Caffeine and a token HMAC fingerprint. It does not implement the introspection protocol; `delegate` is a real introspector or a test fake that verifies `active`.

`src/main/java/demo/opaque/RevocationBoundIntrospector.java`:

```java
package demo.opaque;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.HexFormat;
import java.util.Objects;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;

import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2TokenIntrospectionClaimNames;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;

import reactor.core.publisher.Mono;

public final class RevocationBoundIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private static final String HMAC = "HmacSHA256";

    private record Entry(
        OAuth2AuthenticatedPrincipal principal,
        Instant validUntil
    ) {}

    private final ReactiveOpaqueTokenIntrospector delegate;
    private final Duration deadline;
    private final Duration maxAge;
    private final Clock clock;
    private final byte[] hmacKey = new byte[32];
    private final Cache<String, Entry> cache;

    public RevocationBoundIntrospector(
            ReactiveOpaqueTokenIntrospector delegate,
            Duration deadline,
            Duration maxAge,
            long maxEntries,
            Clock clock) {

        this.delegate = Objects.requireNonNull(delegate);
        this.clock = Objects.requireNonNull(clock);
        this.deadline = Objects.requireNonNull(deadline);
        this.maxAge = Objects.requireNonNull(maxAge);

        if (deadline.isZero() || deadline.isNegative()
                || maxAge.isNegative() || maxEntries < 0) {
            throw new IllegalArgumentException(
                "Timeout, TTL or capacity is invalid");
        }

        new SecureRandom().nextBytes(hmacKey);

        Duration physicalTtl = maxAge.isZero()
            ? Duration.ofMillis(1) : maxAge;

        this.cache = Caffeine.newBuilder()
            .maximumSize(maxEntries)
            .expireAfterWrite(physicalTtl)
            .build();
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        return Mono.defer(() -> {
            String key = cacheKey(token);
            Instant now = clock.instant();

            Entry cached = cache.getIfPresent(key);
            if (cached != null
                    && now.isBefore(cached.validUntil())) {
                return Mono.just(cached.principal());
            }

            if (cached != null) {
                cache.invalidate(key);
            }

            // Do not use stale entries on errors or AS outages.
            return delegate.introspect(token)
                .timeout(deadline)
                .switchIfEmpty(Mono.error(
                    new BadOpaqueTokenException(
                        "Empty introspection response")))
                .flatMap(principal -> {
                    Instant checkedAt = clock.instant();
                    Object raw = principal.getAttribute(
                        OAuth2TokenIntrospectionClaimNames.EXP);
                    Instant exp = expiry(raw);

                    if (exp != null
                            && !checkedAt.isBefore(exp)) {
                        return Mono.error(
                            new BadOpaqueTokenException(
                                "Introspection token expired"));
                    }

                    // Missing exp or TTL=0 => do not positive-cache.
                    if (!maxAge.isZero() && exp != null) {
                        Instant until = checkedAt.plus(maxAge);
                        if (exp.isBefore(until)) {
                            until = exp;
                        }
                        if (checkedAt.isBefore(until)) {
                            cache.put(key, new Entry(principal, until));
                        }
                    }

                    return Mono.just(principal);
                });
        });
    }

    // Only trusted code already holding the token may call this method.
    // Never send raw tokens over the revocation event bus.
    public void invalidate(String token) {
        cache.invalidate(cacheKey(token));
    }

    private static Instant expiry(Object value) {
        if (value instanceof Instant t) {
            return t;
        }
        if (value instanceof Number t) {
            return Instant.ofEpochSecond(t.longValue());
        }
        return null;
    }

    private String cacheKey(String token) {
        Objects.requireNonNull(token, "token");
        try {
            Mac mac = Mac.getInstance(HMAC);
            mac.init(new SecretKeySpec(hmacKey, HMAC));
            return HexFormat.of().formatHex(
                mac.doFinal(token.getBytes(
                    StandardCharsets.UTF_8)));
        }
        catch (GeneralSecurityException ex) {
            throw new IllegalStateException(
                "Cannot compute HMAC key", ex);
        }
    }
}
```

**QA of the wrapper design:**

1. `Mono.defer` checks the cache at subscription time rather than capturing state once at Mono assembly time.
2. `cache.getIfPresent` accepts an entry only when `now < validUntil`; if stale, it invalidates and re-queries the AS.
3. `delegate.introspect(token)` performs active verification. The wrapper caches only **successful principals**, never inactive/error/empty outcomes.
4. `Mono.timeout(deadline)` enforces a deadline on cache misses. Timeouts emit an error and **never** return a temporary principal.
5. `maxAge=Duration.ZERO` bypasses positive caching while still enforcing the timeout.
6. Tokens with `exp` as `Instant` or numeric epoch seconds are supported. If `exp` is absent, nothing is cached; depending on policy, you may reject responses lacking `exp` altogether.
7. The Caffeine cache enforces `maximumSize`, `expireAfterWrite`, and `validUntil` bounded by `exp`. Keys never store raw token strings—only an HMAC digest with a per-process random key. Cached principals/claims remain sensitive data.
8. `invalidate(token)` clears only the **local instance** when trusted code actually possesses the token. Do not rely on it for multi-pod invalidation; `jti`/subject events need a reverse index/version and separate consistency design.
9. The sample does not coalesce concurrent cache misses (*single-flight*). Cold starts can trigger multiple introspection calls for the same token; in production, evaluate metrics, bulkheads, and bounded deduplication if needed.
10. Positive caching is a decision **intentionally accepting a stale window**. When a token is revoked right after a cache miss, the entry remains usable up to TTL. If your threat model forbids that, set TTL to 0.

### 6.2. SecurityConfig.java with Network Timeouts

`src/main/java/demo/opaque/SecurityConfig.java`:

```java
package demo.opaque;

import java.time.Clock;
import java.time.Duration;

import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    ReactiveOpaqueTokenIntrospector introspector(
            @Value("${demo.introspection.uri}") String uri,
            @Value("${demo.introspection.client-id}") String id,
            @Value("${demo.introspection.client-secret}") String secret,
            @Value("${demo.introspection.connect-ms}") int connectMs,
            @Value("${demo.introspection.response-ms}") long responseMs,
            @Value("${demo.introspection.deadline-ms}") long deadlineMs,
            @Value("${demo.introspection.cache-ms}") long cacheMs,
            @Value("${demo.introspection.max-entries}") long maxEntries) {

        HttpClient transport = HttpClient.create()
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, connectMs)
            .responseTimeout(Duration.ofMillis(responseMs));

        // Use this WebClient only to call the admin-configured introspection URI.
        WebClient asClient = WebClient.builder()
            .clientConnector(new ReactorClientHttpConnector(transport))
            .defaultHeaders(headers -> headers.setBasicAuth(id, secret))
            .build();

        // Spring Security 6.5: constructor accepting WebClient.
        ReactiveOpaqueTokenIntrospector actualAs =
            new SpringReactiveOpaqueTokenIntrospector(
                uri, asClient);

        return new RevocationBoundIntrospector(
            actualAs,
            Duration.ofMillis(deadlineMs),
            Duration.ofMillis(cacheMs),
            maxEntries,
            Clock.systemUTC());
    }

    @Bean
    SecurityWebFilterChain security(
            ServerHttpSecurity http,
            ReactiveOpaqueTokenIntrospector introspector) {

        return http
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/public")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/document")
                    .hasAuthority("SCOPE_docs.read")
                .pathMatchers(HttpMethod.POST, "/api/document")
                    .hasAuthority("SCOPE_docs.write")
                .pathMatchers(HttpMethod.GET, "/api/whoami")
                    .authenticated()
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(opaque ->
                    opaque.introspector(introspector)))
            .formLogin(form -> form.disable())
            .httpBasic(basic -> basic.disable())
            // Only for Bearer header-only APIs. If cookie auth is used,
            // re-evaluate and retain CSRF on the corresponding routes.
            .csrf(csrf -> csrf.disable())
            .build();
    }
}
```

**Why 3 timeouts?** `CONNECT_TIMEOUT_MILLIS` bounds TCP connect. `HttpClient.responseTimeout` bounds waiting for the response. The wrapper's `Mono.timeout` bounds the **entire introspection attempt** so waiting on the connection pool or TLS cannot stretch indefinitely. In production, add pool acquire timeouts, TLS handshake timeouts, DNS settings, and connection limits matching your infrastructure.

**Careful with Basic:** `defaultHeaders.setBasicAuth(id, secret)` is used solely **server-to-server** when the Resource Server calls the introspection endpoint. Inbound API traffic from the Internet still **does not** accept HTTP Basic; thus `httpBasic.disable()` is completely consistent.

If the IdP uses `private_key_jwt`/mTLS instead of Basic, replace the client authentication mechanism here. Never use this secret-bearing Basic `WebClient` for user-supplied URIs; that creates SSRF and credential leak risks.

### 6.3. Controller Simulating Only a Business Request

`src/main/java/demo/opaque/DocumentController.java`:

```java
package demo.opaque;

import org.springframework.http.MediaType;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DocumentController {

    @GetMapping(value = "/public",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping(value = "/api/document",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> readDocument() {
        return Mono.just("document-visible");
    }

    @PostMapping(value = "/api/document",
                 produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> updateDocument() {
        // Demo only, does not mutate real data.
        return Mono.just("document-updated");
    }

    @GetMapping(value = "/api/whoami",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> whoami() {
        return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication().getName());
    }
}
```

A real Resource Server must still check tenant/owner and business permissions in the service/repository. `SCOPE_docs.read` indicates the token carries the "read documents" permission type, **not** that the user may read every document. Never log raw tokens or full introspection JSON; `whoami` returns only the protected name.

## 7. Unit Tests: Timeouts, Cache TTL, Token Expiry, and Revocation Stale Window

The tests use `MutableClock` to advance time manually. TTL lengths are verified **without multi-second sleeps**, avoiding flakiness. The AS timeout case uses `Mono.never()` with a 70ms deadline.

`src/test/java/demo/opaque/RevocationBoundIntrospectorTests.java`:

```java
package demo.opaque;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class RevocationBoundIntrospectorTests {

    static class MutableClock extends Clock {
        private final AtomicReference<Instant> now =
            new AtomicReference<>(
                Instant.parse("2026-01-01T00:00:00Z"));

        @Override
        public ZoneId getZone() {
            return ZoneOffset.UTC;
        }

        @Override
        public Clock withZone(ZoneId zone) {
            return this;
        }

        @Override
        public Instant instant() {
            return now.get();
        }

        void advance(long seconds) {
            now.updateAndGet(t -> t.plusSeconds(seconds));
        }
    }

    private static OAuth2AuthenticatedPrincipal active(
            Instant expiry) {
        return new DefaultOAuth2AuthenticatedPrincipal(
            "alice",
            Map.of("sub", "alice", "scope", "docs.read",
                "exp", expiry),
            List.of(new SimpleGrantedAuthority("SCOPE_docs.read")));
    }

    private static OAuth2AuthenticatedPrincipal withoutExp() {
        return new DefaultOAuth2AuthenticatedPrincipal(
            "alice", Map.of("sub", "alice"),
            List.of(new SimpleGrantedAuthority("SCOPE_docs.read")));
    }

    private static RevocationBoundIntrospector wrapper(
            ReactiveOpaqueTokenIntrospector delegate,
            Clock clock, Duration ttl) {
        return new RevocationBoundIntrospector(
            delegate, Duration.ofMillis(70), ttl,
            100, clock);
    }

    @Test
    void repeatedPositiveHitCallsAsOnlyOnce() {
        MutableClock c = new MutableClock();
        AtomicInteger calls = new AtomicInteger();

        ReactiveOpaqueTokenIntrospector as = token -> {
            calls.incrementAndGet();
            return Mono.just(active(
                c.instant().plusSeconds(60)));
        };

        var cache = wrapper(as, c, Duration.ofSeconds(5));
        assertEquals("alice", cache.introspect("A")
            .block().getName());
        assertEquals("alice", cache.introspect("A")
            .block().getName());
        assertEquals(1, calls.get());
    }

    @Test
    void afterPolicyTtlExpiresIntrospectsAgain() {
        MutableClock c = new MutableClock();
        AtomicInteger calls = new AtomicInteger();

        ReactiveOpaqueTokenIntrospector as = token -> {
            calls.incrementAndGet();
            return Mono.just(active(
                c.instant().plusSeconds(60)));
        };

        var cache = wrapper(as, c, Duration.ofSeconds(2));
        cache.introspect("A").block();
        c.advance(3);
        cache.introspect("A").block();
        assertEquals(2, calls.get());
    }

    @Test
    void tokenExpCapsCacheEntryBeforePolicyTtl() {
        MutableClock c = new MutableClock();
        AtomicInteger calls = new AtomicInteger();

        ReactiveOpaqueTokenIntrospector as = token -> {
            calls.incrementAndGet();
            return Mono.just(active(
                c.instant().plusSeconds(1)));
        };

        var cache = wrapper(as, c, Duration.ofSeconds(10));
        cache.introspect("A").block();
        c.advance(2);
        cache.introspect("A").block();
        assertEquals(2, calls.get());
    }

    @Test
    void revocationCanRemainCachedUntilTtlExpires() {
        MutableClock c = new MutableClock();
        AtomicInteger calls = new AtomicInteger();
        AtomicBoolean revoked = new AtomicBoolean(false);

        ReactiveOpaqueTokenIntrospector as = token -> {
            calls.incrementAndGet();
            return revoked.get()
                ? Mono.error(new BadOpaqueTokenException("inactive"))
                : Mono.just(active(
                    c.instant().plusSeconds(60)));
        };

        var cache = wrapper(as, c, Duration.ofSeconds(2));
        cache.introspect("A").block();
        revoked.set(true);

        // A cache hit right after revocation: stale window is accepted.
        assertEquals("alice", cache.introspect("A")
            .block().getName());
        assertEquals(1, calls.get());

        c.advance(3);
        StepVerifier.create(cache.introspect("A"))
            .expectError(BadOpaqueTokenException.class)
            .verify();
        assertEquals(2, calls.get());
    }

    @Test
    void zeroTtlChecksRevokedStateOnNextRequest() {
        MutableClock c = new MutableClock();
        AtomicInteger calls = new AtomicInteger();
        AtomicBoolean revoked = new AtomicBoolean(false);

        ReactiveOpaqueTokenIntrospector as = token -> {
            calls.incrementAndGet();
            return revoked.get()
                ? Mono.error(new BadOpaqueTokenException("inactive"))
                : Mono.just(active(
                    c.instant().plusSeconds(60)));
        };

        var cache = wrapper(as, c, Duration.ZERO);
        cache.introspect("A").block();
        revoked.set(true);
        StepVerifier.create(cache.introspect("A"))
            .expectError(BadOpaqueTokenException.class)
            .verify();
        assertEquals(2, calls.get());
    }

    @Test
    void missingExpNeverPositiveCaches() {
        MutableClock c = new MutableClock();
        AtomicInteger calls = new AtomicInteger();
        ReactiveOpaqueTokenIntrospector as = token -> {
            calls.incrementAndGet();
            return Mono.just(withoutExp());
        };

        var cache = wrapper(as, c, Duration.ofSeconds(5));
        cache.introspect("A").block();
        cache.introspect("A").block();
        assertEquals(2, calls.get());
    }

    @Test
    void inactiveErrorNeverBecomesCachedSuccess() {
        MutableClock c = new MutableClock();
        AtomicInteger calls = new AtomicInteger();

        ReactiveOpaqueTokenIntrospector as = token -> {
            calls.incrementAndGet();
            return Mono.error(
                new BadOpaqueTokenException("inactive"));
        };

        var cache = wrapper(as, c, Duration.ofSeconds(5));

        StepVerifier.create(cache.introspect("bad"))
            .expectError(BadOpaqueTokenException.class)
            .verify();
        StepVerifier.create(cache.introspect("bad"))
            .expectError(BadOpaqueTokenException.class)
            .verify();
        assertEquals(2, calls.get());
    }

    @Test
    void emptyIntrospectionFailsClosed() {
        MutableClock c = new MutableClock();
        ReactiveOpaqueTokenIntrospector as = token -> Mono.empty();

        var cache = wrapper(as, c, Duration.ofSeconds(5));
        StepVerifier.create(cache.introspect("empty"))
            .expectError(BadOpaqueTokenException.class)
            .verify();
    }

    @Test
    void timeoutFailsClosedInsteadOfReturningPrincipal() {
        MutableClock c = new MutableClock();
        ReactiveOpaqueTokenIntrospector as = token -> Mono.never();

        var cache = wrapper(as, c, Duration.ofSeconds(5));
        StepVerifier.create(cache.introspect("slow"))
            .expectError(TimeoutException.class)
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void trustedLocalInvalidateForcesNewIntrospection() {
        MutableClock c = new MutableClock();
        AtomicInteger calls = new AtomicInteger();

        ReactiveOpaqueTokenIntrospector as = token -> {
            calls.incrementAndGet();
            return Mono.just(active(
                c.instant().plusSeconds(60)));
        };

        var cache = wrapper(as, c, Duration.ofSeconds(5));
        cache.introspect("A").block();
        cache.invalidate("A");
        cache.introspect("A").block();
        assertEquals(2, calls.get());
    }

    @Test
    void distinctBearerStringsCannotReuseOneEntry() {
        MutableClock c = new MutableClock();
        AtomicInteger calls = new AtomicInteger();

        ReactiveOpaqueTokenIntrospector as = token -> {
            calls.incrementAndGet();
            return Mono.just(active(
                c.instant().plusSeconds(60)));
        };

        var cache = wrapper(as, c, Duration.ofSeconds(5));
        cache.introspect("A").block();
        cache.introspect("B").block();
        cache.introspect("A").block();
        assertEquals(2, calls.get());
    }

    @Test
    void expiredIntrospectionResponseIsRejected() {
        MutableClock c = new MutableClock();
        ReactiveOpaqueTokenIntrospector as = token ->
            Mono.just(active(c.instant().minusSeconds(1)));

        var cache = wrapper(as, c, Duration.ofSeconds(5));
        StepVerifier.create(cache.introspect("expired"))
            .expectError(BadOpaqueTokenException.class)
            .verify();
    }
}
```

**Why is having a "stale" cache hit in the revocation test right?** Because a policy with TTL > 0 means the system accepts a window without querying the AS. Tests must never hide that fact. Turn the observation into an SLO and prove the actual window is <= the approved limit.

`StepVerifier` tests timeouts directly at the wrapper layer and does **not** prove the controller returns HTTP 503 or 401. To verify dependency failure status codes, add global exception mapping/entry point configuration and integration tests against a mock/staging AS rather than guessing the status.

## 8. WebTestClient Integration: Bearer Resource Policy Without External AS

We use a `@TestConfiguration` providing a fake `@Primary ReactiveOpaqueTokenIntrospector` for learning Bearer tokens: `reader-demo` has `SCOPE_docs.read`; `writer-demo` has `SCOPE_docs.write`; other tokens fail with `BadOpaqueTokenException`. The real `SecurityWebFilterChain` executes, yet tests **do not call a network introspection endpoint**, so they are not an AS end-to-end test.

`src/test/java/demo/opaque/OpaqueHttpTests.java`:

```java
package demo.opaque;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Import(OpaqueHttpTests.FakeAs.class)
class OpaqueHttpTests {

    @Autowired
    WebTestClient client;

    @TestConfiguration
    static class FakeAs {

        @Bean
        @Primary
        ReactiveOpaqueTokenIntrospector testingIntrospector() {
            ReactiveOpaqueTokenIntrospector fake = token -> {
                if (!token.equals("reader-demo")
                        && !token.equals("writer-demo")) {
                    return Mono.error(
                        new BadOpaqueTokenException("inactive"));
                }

                String scope = token.equals("reader-demo")
                    ? "docs.read" : "docs.write";

                OAuth2AuthenticatedPrincipal principal =
                    new DefaultOAuth2AuthenticatedPrincipal(
                        "alice",
                        Map.of("sub", "alice",
                            "scope", scope,
                            "exp", Instant.now().plusSeconds(60)),
                        List.of(new SimpleGrantedAuthority(
                            "SCOPE_" + scope)));
                return Mono.just(principal);
            };

            return new RevocationBoundIntrospector(
                fake, Duration.ofMillis(550),
                Duration.ofSeconds(2), 100,
                Clock.systemUTC());
        }
    }

    @Test
    void publicRouteCanBeCalledAnonymously() {
        client.get().uri("/public")
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void missingBearerIs401() {
        client.get().uri("/api/document")
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void activeReaderCanRead() {
        client.get().uri("/api/document")
            .headers(h -> h.setBearerAuth("reader-demo"))
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo(
                "document-visible");
    }

    @Test
    void readScopeCannotWrite() {
        client.post().uri("/api/document")
            .headers(h -> h.setBearerAuth("reader-demo"))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void writerCanPostWithoutCsrfBecauseOnlyBearerHeaderIsAccepted() {
        client.post().uri("/api/document")
            .headers(h -> h.setBearerAuth("writer-demo"))
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo(
                "document-updated");
    }

    @Test
    void writeScopeCannotRead() {
        client.get().uri("/api/document")
            .headers(h -> h.setBearerAuth("writer-demo"))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void inactiveTokenReturns401() {
        client.get().uri("/api/document")
            .headers(h -> h.setBearerAuth("inactive-demo"))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void cookieAloneCannotAuthenticateBearerApi() {
        client.get().uri("/api/document")
            .cookie("access_token", "reader-demo")
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void basicAuthCannotReplaceBearer() {
        client.get().uri("/api/document")
            .headers(h -> h.setBasicAuth("alice", "password"))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void whoamiUsesIntrospectedPrincipal() {
        client.get().uri("/api/whoami")
            .headers(h -> h.setBearerAuth("reader-demo"))
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("alice");
    }
}
```

Run from the project root:

```bash
mvn test
```

**Target: 22 tests** (12 wrapper unit + 10 HTTP), when files are created properly with matching JDK/dependencies. These tests are **sample code for learners to run**; this lesson **does not claim Maven was executed in your repository**. HTTP tests use a fake AS returning in-memory principals; wrapper tests verify timeouts/caching. To verify the RFC 7662 contract, networking/TLS, client credentials, and a real AS, run separate staging/sandbox tests.

### 8.1. Assumptions This Test Suite Does Not Prove

- Does the real AS return `active=false` for revoked tokens across every node within SLA?
- Does `WebClient` send `token=...` form data and HTTP Basic client credentials to the right URI?
- Do TCP connect, pool acquire, TLS, and response timeouts work accurately through proxies?
- Do IdP 429/500/malformed JSON responses or revocations between requests fail closed?
- Does cache behavior hold up when 10,000 callers hit concurrently with the same token?
- Do revocation events reach every pod without ordering races?
- Are wrong issuers/audiences/tenants rejected by the introspection contract?
- How are timeout exceptions mapped by the security handler into HTTP 503/5xx/401?

Cover those points with integration tests against an AS sandbox / real mock HTTP server, browser/ingress environments, and load tests. **Never** flip fail-closed to fail-open just so an endpoint keeps returning 200 during an AS failure.

## 9. Running with curl, Comparing Cache and Latency

Start the app:

```bash
java -version
mvn -version
mvn spring-boot:run
```

Test public and missing Bearer:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/document
curl -i -H 'Authorization: Bearer invalid-token' \
  http://localhost:8080/api/document
```

Expect public 200; protected without Bearer 401. A request carrying Bearer `invalid-token` against the unconfigured demo endpoint `idp.example.invalid` will trigger a dependency error and **must not** enter the handler. Do not claim the response will always be specifically 401 or 503 when the AS is unreachable, since exception translation must be verified in practice.

Once you have an organization-approved sandbox AS, replace `demo.introspection.uri`, `client-id`, and `client-secret` and obtain a **real opaque access token** for testing. Call:

```bash
# Illustrative only: replace placeholder with a valid token from the sandbox AS.
curl -i -H 'Authorization: Bearer <VALID_OPAQUE_ACCESS_TOKEN>' \
  http://localhost:8080/api/document
```

`<VALID_OPAQUE_ACCESS_TOKEN>` is a placeholder; there is no token issuance endpoint in this project. A Resource Server **does not issue tokens itself**. To exercise the happy path offline, run `mvn test` with the fake AS principal. On PowerShell, you may need `curl.exe`.

Never put Bearer tokens or client secrets into URL queries, access logs, debugging screenshots, or shell history; in real environments use HTTPS and keep secrets in a secure env/manager.

### 9.1. Estimating Load

Suppose 1,000 requests per second hit the protected API:

- 100% cache miss -> roughly 1,000 introspection attempts/s, before retries.
- 70% cache hit -> roughly 300 misses/s.
- Actual figures depend on token uniqueness, TTL, evictions, simultaneous cold misses, cluster distribution, and retries.

**This is solely an arithmetic example.** Boosting hit rates by stretching TTL from 2 seconds to 30 minutes violates your revocation SLA unless business approves it. During an IdP outage, retrying every request can trigger a retry storm and slow AS recovery.

### 9.2. Essential Metrics

| Metric | Question |
| --- | --- |
| `introspection.duration` p50/p95/p99 | How much latency does the IdP add on cache misses? |
| `introspection.timeout.count` | Are deadlines being exceeded frequently? |
| `introspection.outcome` by category | Active/inactive, invalid client, 429, 5xx, TLS? |
| `introspection.inflight` | Bottlenecks / bulkhead pressure? |
| `cache.hit/miss/eviction` | How much load is the cache absorbing? |
| `cache.ttl.configured` | Was TTL raised without review? |
| `revocation.observed.latency` | How long after revocation does the API reject the token? |
| `event.delivery.lag/dropped` | Is the invalidation mechanism reliable? |
| `auth.401` and `authz.403` | Missing credentials or missing permissions? |
| `api.latency.protected/public` p99 | How much does introspection lengthen API latency? |
| IdP QPS/429/5xx | Can AS capacity handle peaks and miss storms? |

Never use raw tokens, user names, or session IDs as metric labels (cardinality and privacy). Never log full introspection bodies or `Authorization` headers. If trace correlation is needed, use dedicated IDs and redaction; even a token HMAC fingerprint requires retention and access controls.

## 10. Scenario-Based Policies

### 10.1. Sensitive Privilege Administration

`POST /api/admin/change-policy`: choose cache TTL 0, check admin permissions at the authorization layer, and optionally verify policy version or state at commit time. When the AS is unavailable, reject the operation; never fall back to last-known-good. If the AS cannot propagate revoked state in under 1 second, change the architecture/SLA agreement rather than pretending negative TTLs exist.

### 10.2. Low-Sensitivity Read-Only API

If the product accepts a 30-second revocation window and AS + inflight margin <= 5 seconds, positive cache TTL can be at most 25 seconds under the model; choose a lower value for headroom. If `exp` has 3 seconds left, the entry lives only 3 seconds. Monitor `revocation.observed.latency`, not just cache hit ratios.

### 10.3. Multi-Pod Cluster

Each pod holds a local Caffeine cache; a revocation event hitting one pod does not affect other pods. Use authenticated event fan-out with sequence/version numbers and reconciliation, or a reviewed shared cache/denylist. If delivery cannot be guaranteed, TTL remains the safety net. **Never publish raw Bearer tokens** on a bus solely for invalidation.

### 10.4. IdP Outage

When the AS disconnects for 2 minutes and positive cache TTL is 2 seconds, previously cached active entries may remain valid until TTL expires. Afterward, requests requiring verification must **fail**; never extend the cache to 2 minutes automatically. The UI can receive a dependency error per exception handler; SREs should alert and restore the IdP/network rather than opening access.

### 10.5. Token exp Shorter Than TTL

`maxAge=10s` while the token has 1s until `exp`: effective TTL <= 1s. If the token is already expired when the introspection response reaches the Resource Server, the wrapper must reject it and never cache it.

## 11. Common Design Mistakes

| Anti-Pattern | Why It Is Dangerous | Replace With |
| --- | --- | --- |
| Caching `active=true` until `exp` hours away | Revocation has no early effect | SLA-based TTL, capped by `exp` |
| Never asking security for revocation SLA | Arbitrary TTL selection | Explicit SLO/SLI, measured AS propagation |
| `Mono.cache()` holding errors forever | Caches failures, leaks/memory issues | Positive-only bounded cache |
| Returning `lastKnownGood` past TTL on timeout | **Fail-open** | Fail-closed, no stale-on-error |
| Synthesizing a mock principal when circuit breaker opens | Bypasses authentication | Dependency failure, deny |
| Caching raw bearer string as key | Heap/log secret exposure | HMAC digest, limited retention |
| Setting only response timeout | Pool/DNS/TLS stalls drag on | Total Mono deadline and per-stage limits |
| Retrying 3 times on every error | Inflates p99, overloads IdP | Bounded retries only on recoverable errors |
| Skipping `exp` check on cache hit | Expired token stays active | Per-entry `validUntil` |
| One shared cache across issuers/tenants | Crosses trust boundaries | Namespace/partition policy |
| Revocation event reaches only one pod | Other pods stay stale | Fan-out, reconciliation, TTL |
| Calling `block()`/`RestTemplate` on event loop | Reactor starvation | `WebClient` and reactive APIs |
| Treating `active=false` HTTP 200 as API success | Invalid tokens let through | Spring introspector verifies active |
| Calling mock-principal tests a network test | Leaves TLS/latency/AS untested | Unit + HTTP + sandbox integration |
| Removing scope check after seeing 403 | Authorization bypass | Investigate `SCOPE_` and resource ownership |
| Using opaque auth with cookie fallback | CSRF threat no longer bearer-only | Separate chains, keep CSRF for browsers |
| Sharing client secret on general `WebClient` | SSRF/token leakage | Dedicated `WebClient` to trusted AS |
| Disabling cache and promising instant revoke | Ignores AS propagation/inflight | Commit-time recheck + version/denylist per policy |

## 12. Pre-Production Checklist

1. Define the revocation SLA for every endpoint and token category.
2. Measure AS propagation across nodes/regions; never promise an SLA without an upper bound.
3. Choose `T_cache` from SLA minus AS/inflight/margin, not from token lifespan.
4. Cap TTL by `exp`; never positive-cache when `exp` is missing or ambiguous.
5. Cache only `active=true` results verified by the introspector; never cache timeouts, 5xx, or inactive as principals.
6. Fail closed when the AS is unreachable; never return stale-after-TTL or default authenticated principals.
7. Create a dedicated `WebClient` for introspection with HTTPS, trusted URIs, and client auth/secret store.
8. Set TCP connect, response, pool, TLS, and total timeouts derived from your API latency budget.
9. Bound retries strictly to appropriate errors within the deadline, avoiding thundering herds.
10. Use a bounded positive-only cache with max entries, secure HMAC keys/retention, and invalidation.
11. Across multiple pods/issuers/tenants, design cache namespacing and event fan-out/reconciliation.
12. Never cache `active` results on admin/transactional APIs where staleness is unacceptable.
13. Always enforce authn/authz: 401 for invalid tokens, 403 for missing scopes, and owner/tenant checks in services.
14. Exempt from CSRF only APIs that are truly Bearer-header-only; session/cookie routes still need CSRF.
15. Unit-test TTL/expiry/revocation with a fake clock, timeouts/errors with `StepVerifier`, and 401/403/200 with `WebTestClient`.
16. Staging-test RFC 7662 with a sandbox IdP for invalid client, 429/5xx, timeouts, mTLS/TLS, multi-region and load.
17. Maintain dashboards for latency, cache hit/miss, invalidation lag, and observed revocation latency without logging secrets.
18. Document who is authorized to adjust TTL and the emergency procedure to disable caching during an access incident.

## 13. Self-Assessment Questions

**Question 1.** Must an opaque token Resource Server strictly receive a "non-JWT" token?  
**No.** "Opaque" in Spring describes **introspection**; JWTs can be introspected to check revoked state if policy requires it.

**Question 2.** Why does `exp` 30 minutes away not allow positive-caching for 30 minutes?  
Because the token can be revoked **before `exp`**. A long cache lets a revoked token keep working until the cache entry expires.

**Question 3.** Revocation SLA 10s, AS 3s, inflight/safety 2s; maximum TTL?  
Under the illustrative budget, **5 seconds**, subject to real safety margins and AS measurements.

**Question 4.** Cache TTL is 10s while the token has 2s left until `exp`; what is the entry TTL?  
**At most 2 seconds**; capped by `exp`.

**Question 5.** Does positive-cache TTL=0 guarantee every request after revocation immediately returns 401?  
**Not strictly.** AS eventual consistency and in-flight requests still exist.

**Question 6.** Must `{"active":false}` from the AS return HTTP 401 from the introspection endpoint?  
No. RFC 7662 can return HTTP 200 with `active=false`; the Resource Server API treats the Bearer token as invalid.

**Question 7.** When introspection times out, may an expired-TTL cached principal be returned to avoid 5xx?  
Not under a **fail-closed** policy; there is no proof the token is still active.

**Question 8.** Is unbounded `Mono.cache()` suitable for token validation?  
No. It can retain successes/errors/raw tokens too long or exhaust memory; use a positive-only bounded cache with expiry and invalidation.

**Question 9.** Why is an overall deadline needed when `HttpClient.responseTimeout` is already set?  
Because pool/DNS/connect/TLS and pre-response steps take time too. An overall deadline bounds the entire publisher.

**Question 10.** Can a token revoked right after an AS check still call the API while cached?  
Yes, within the **accepted stale window** when TTL > 0. If unacceptable, disable caching and implement stricter re-checks/permissions.

**Question 11.** Does local `invalidate(token)` clear entries across every pod?  
No. Each process has its own cache; you need event propagation or a shared strategy plus reconciliation.

**Question 12.** What do the two sample test classes verify?  
Unit tests verify wrapper timeouts/TTL/revocation; HTTP tests verify Spring Security Bearer routing/authorization with a fake IdP, **not** replacing an AS sandbox.

**Question 13.** What does an active token lacking `SCOPE_docs.write` receive on a POST?  
**403 Forbidden**, because authentication succeeded while authorization was insufficient.

**Question 14.** Does an AS returning 5xx mean the token is inactive?  
You do not know whether the token is active. It is a dependency failure and must never become an authenticated principal.

### Official Documentation

- Spring Security 6.5 – Reactive Resource Server Opaque Tokens: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/opaque-token.html
- Spring Security 6.5 – OAuth2 WebFlux Overview: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/index.html
- Spring Security 6.5 API – `ReactiveOpaqueTokenIntrospector`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html
- Spring Security 6.5 API – `SpringReactiveOpaqueTokenIntrospector`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.html
- RFC 7662 – Token Introspection: https://www.rfc-editor.org/rfc/rfc7662
- RFC 7009 – Token Revocation: https://www.rfc-editor.org/rfc/rfc7009
- RFC 6750 – Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750
- Reactor Netty – HttpClient timeouts: https://projectreactor.io/docs/netty/release/reference/http-client.html
- Project Reactor – Mono.timeout: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Caffeine – Expiration/Eviction: https://github.com/ben-manes/caffeine/wiki/Eviction

**Summary:** An Opaque Resource Server depends on introspection to know `active`. Timeouts must stay inside the latency budget, outages must **fail closed**, and success caching must be **positive-only, bounded, and capped by both `exp` and the revocation SLA**. If revoked tokens remaining usable during a stale window is unacceptable, disable positive caching while still addressing AS consistency and in-flight requests. Use WebFlux `ReactiveOpaqueTokenIntrospector` with `WebClient` timeouts, verified by fake-clock tests and an AS sandbox before production.