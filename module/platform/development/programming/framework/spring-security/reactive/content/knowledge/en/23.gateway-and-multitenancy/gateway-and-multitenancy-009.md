# Coordinating Rate Limiting, Timeouts, and Identity Service Protection

**Module:** Spring Security – reactive / Spring WebFlux  
**Section:** Gateway and Multi-tenancy  
**Goal:** Protect the Identity Provider (IdP)/Authorization Server when the gateway faces heavy traffic, while preserving tenant isolation, limiting the right callers, honoring revocation, and never bypassing authentication when the identity service experiences temporary errors.

## 1. Summary and Responsibility Model

**Rate limiting, timeouts, bulkheads, and circuit breakers are four complementary mechanisms that cannot replace one another.** A multi-tenant gateway should have:

1. **Pre-auth throttling:** rate-limit raw requests before tokens are decoded or introspection calls reach the IdP. Use only signals that do not require tenant authentication, such as source connection/IP recorded by a trusted ingress. Never trust Internet-supplied tenant HTTP headers.
2. **Authentication:** verify Bearer tokens using `ReactiveJwtDecoder` and trusted JWKS or using `ReactiveOpaqueTokenIntrospector` (e.g., `SpringReactiveOpaqueTokenIntrospector`) over HTTPS introspection. If verification fails, **issue no principal**.
3. **Post-auth quotas:** enforce tenant/user/route limits using **verified claims** from `JwtAuthenticationToken` or the introspection principal. Quota keys must be namespaced by issuer/tenant and, when needed, subject/client.
4. **Outbound IdP protection:** cap in-flight calls, apply a shared IdP rate cap, enforce connect/response/total deadlines, retry selectively, and use fail-closed circuit breakers.
5. **Downstream protection:** apply separate timeouts and circuits for business upstreams; backend authorization must still verify resource owner/tenant.

```text
Internet -> CDN/WAF -> Trusted Ingress
                           |
                           v
                 +-------------------------+
                 | Spring Cloud Gateway    |
                 | (1) coarse pre-auth cap |
                 | (2) JWT/introspection   |------> IdP/AS
                 | (3) trusted tenant      |        /introspect
                 | (4) tenant/user quotas  |        JWKS metadata
                 | (5) routing/bulkhead    |
                 +------------+------------+
                              |
                        business calls
                              v
                     Tenant-aware services
                     own resource ACL checks
```

**An architectural detail often overlooked:** placing a limiter **after** introspection allows 10,000 requests carrying junk tokens to hit the IdP 10,000 times before the limiter even knows who the tenant is. Conversely, limiting only by IP can falsely lump 100 corporate users behind one NAT as a single "user," while a single tenant spanning many source IPs can exhaust the IdP budget. Both pre-auth and post-auth layers are necessary.

## 2. Trust Boundaries and Rate-Limit Key Selection

| Layer | Signal Source | Immediately Trustworthy? | What It Is Used For |
| --- | --- | --- | --- |
| Managed reverse proxy | Remote socket address / verified client IP | Conditionally: trusted ingress must be configured | Coarse pre-auth abuse detection |
| Self-sent `X-Forwarded-For` from Internet | Arbitrary header | **No** | Never use as IP identity unless stripped/replaced by proxy |
| `X-Tenant-Id` / path tenant | Caller-controlled | **No** | Only compare against verified tenant; never pick token decoder/quota directly |
| Base64-decoded JWT payload | Signature, issuer, and audience unverified | **No** | Never use claims to grant privileges or select IdP URLs |
| `JwtAuthenticationToken` from trusted decoder | Verified JWT | Conditionally: add tenant allowlist/domain policy | Post-auth tenant/user quota |
| `OAuth2AuthenticatedPrincipal` from introspection | AS returned active and valid claims | Conditionally: check AS/tenant contract | Post-auth opaque token quota |
| `X-Verified-Tenant` header written by Gateway | Gateway assertion | Trust only when backend receives over mTLS/private ingress | Routing and backend metadata; does not replace ACLs |
| Redis/bucket state | Cluster-wide limit state | Trust per topology, TLS/auth, and fail policy | Global tenant quota |

How to construct keys post-auth:

```text
preAuthKey  = trustworthy-network-peer-or-ingress-class
tenantKey   = trustedIssuerId + ":" + verifiedTenant
subjectKey  = trustedIssuerId + ":" + verifiedTenant + ":" + verifiedSubject
idpKey      = trustedIssuerId
routeKey    = tenantKey + ":" + routeId
```

**Never** treat a bare subject as unique across all issuers; multiple tenants can have `sub=alice`. For `client_credentials`, the token represents an **application client**, not an end user: use `client_id` or service identity per token contract. In production, keys must be normalized, length-prefixed/delimiter-escaped, and cardinality-bounded; never use raw access tokens as bucket keys without strict necessity and data protection.

### 2.1. Forwarded headers and multi-tenancy

Spring Cloud Gateway 2025.0 changed starter/configuration prefix names. For Gateway Server WebFlux, `spring.cloud.gateway.server.webflux.trusted-proxies` specifies which proxies' headers are trusted. **Never use a `.*` regex toward the Internet**. If the real client IP cannot be determined, use the peer address and coarse global limits rather than trusting `X-Forwarded-For`. Tenant identity **must never** be derived from IPs or network headers; multiple tenants can share a NAT.

### 2.2. Multi-issuer must not mean arbitrary metadata discovery

When each tenant has its own IdP, select the `ReactiveJwtDecoder`/authentication manager from an **operator-approved issuer registry**. Patterns like `JwtIssuerReactiveAuthenticationManagerResolver` are safe only when the resolver/manager is restricted to an issuer allowlist and verifies issuer/audience after signature validation. Never use `iss` from an unverified JWT to automatically fetch an arbitrary URL over HTTP: attackers can turn the gateway into an SSRF client and trigger JWKS fetch storms.

## 3. Choosing the Right Bearer Authentication Model

| Mechanism | When Is the IdP Path Called? | Early Revocation Capability | Protection Point |
| --- | --- | --- | --- |
| Offline JWT Resource Server | Local verify for most requests; JWKS/discovery on cache miss/key rotation | Unaware of revocations before `exp` without extra mechanism | Cache public keys, timeout JWKS fetches, issuer/audience checks |
| Opaque introspection | Often calls AS per request/positive-cache miss | Can observe `active=false` from AS | Pre-auth limiter, IdP bulkhead/timeout, cache TTL aligned with revocation SLA |
| OAuth2 Client outbound token | AS token endpoint on grant/refresh/rotation | Depends on AS policy | Refresh dedupe, limited retries, secret management |
| OIDC browser login | Browser login/consent and server token exchange | Separate OP SSO/local session lifecycle | state/nonce/PKCE, CSRF, login-specific rate controls |

**JWT/JWKS cache ≠ introspection active cache.** A JWKS cache holds **public keys** to verify signatures and says nothing about revocation status. Caching an opaque introspection `active=true` result caches a **security decision**, creating a stale window after revocation. If your revocation SLA is tight, positive caching must be very short or zero while still measuring AS propagation and in-flight requests.

In WebFlux, `SpringReactiveOpaqueTokenIntrospector` is a `ReactiveOpaqueTokenIntrospector` implementation using HTTP introspection. Example Boot properties:

```properties
spring.security.oauth2.resourceserver.opaquetoken.introspection-uri=https://trusted-idp.example.org/oauth2/introspect
spring.security.oauth2.resourceserver.opaquetoken.client-id=resource-server
spring.security.oauth2.resourceserver.opaquetoken.client-secret=secret-from-manager
```

Never hardcode demo values into production. `active=false` from introspection can arrive as **HTTP 200 with a JSON body**, yet the Resource Server must reject the token when handling the API request.

### 3.1. How does pre-auth limiting actually protect the IdP?

Without pre-auth admission control, an attacker can send 5,000 random Bearer tokens per second. With opaque tokens, every token could trigger a network introspection call unless the auth layer stops it first. A pre-auth cap of 200 requests/s per trusted source **reduces the chance** of saturating the IdP, though it is insufficient against distributed multi-IP botnets; combine it with global edge protection, WAF, and per-AS concurrency/QPS caps. Never claim a local IP Map "blocks all DDoS."

### 3.2. Tenant-wide vs. per-user quotas

A `issuer|tenant|sub` key caps **each user within a tenant**; it **does not** cap the tenant's aggregate quota if the tenant has 100,000 users. Production needs **all of these simultaneously**:

- Global edge/IdP safety limit.
- Tenant-wide bucket `issuer|tenant`.
- Per-user/client bucket `issuer|tenant|sub`.
- Per-route cost/priority (reading metadata differs from refresh/password reset).

These policies are independent AND conditions; never replace tenant-wide caps by merely prepending the tenant to the subject key.

## 4. Rate Limiter, Bulkhead, and Timeout: Each Cuts a Different Risk

| Tool | What It Limits | When Triggered | What It Does Not Solve |
| --- | --- | --- | --- |
| Token bucket / RedisRateLimiter | Requests or tokens per second and burst | 429 when tokens exhausted | In-flight call count if latency spikes |
| Fixed-window counter | Requests inside a fixed window | 429 per key | Boundary bursts, multi-pod global quotas |
| Semaphore / bulkhead | Concurrent outbound requests | Fail-fast when no slots remain | Requests/s when AS responds very fast |
| Connect timeout | TCP connect/TLS handshake | Fails if connection takes too long | Total request deadline |
| Response timeout | Waiting for server response | Fails on slow responses | Pool acquisition/DNS/queuing |
| Reactor `Mono.timeout` | Entire publisher from subscription | Error/cancel after deadline | Retry/error-mapping policy |
| Circuit breaker | Fail-fast after repeated dependency failures | Open/half-open | JWT validation, quota fairness |
| Conditional retry | Explicitly identified transient errors | Retries within budget | 401 invalid tokens, idempotency, storms |

### 4.1. Little's Law for the IdP

Average concurrent calls approximately equal `λ × W`. Suppose 80 introspection calls/s and 250ms average latency: average in-flight is ~20. If the AS slows to 2,000ms, in-flight calls jump to **160** at the exact same QPS. Hence a QPS limiter cannot replace a bulkhead; timeouts free slots, but you still need an overall request upper bound, cancellation, and monitoring.

### 4.2. Total deadline before choosing retries

Suppose an API has a 1,500ms p99 budget:

```text
Ingress + preauth / routing         50ms
Authentication / introspection     350ms
Business upstream                  800ms
Response serialization             100ms
Reserve                            200ms
TOTAL                             1500ms
```

If the IdP consumes 350ms, the authentication budget is exhausted. Do not retry 3 times at 350ms each and still expect to meet the SLO. Configure separate connect/response/total timeouts for the IdP and for the backend. `spring.cloud.gateway.server.webflux.httpclient.response-timeout` governs the Gateway's outbound proxy; it **does not automatically apply** to a custom `WebClient` calling introspection/JWKS.

### 4.3. How should rate limits fail?

**429** means the request was rejected by a quota/policy, optionally adding `Retry-After` when a valid value applies. **401** indicates missing/invalid Bearer tokens. **403** means authenticated but lacking granted permissions/tenant. **503** is commonly used when a dependency or breaker is unavailable. **504** typically indicates a gateway/upstream timeout; actual status codes depend on Spring exception handlers and Gateway configuration. **Never claim every IdP error always returns 503**, but all unverified protected requests **must never return a 2xx success**.

If the Redis quota service goes down, never automatically set `allow=true` for every tenant. Choose a reviewed fallback: coarse local limits + capped load shedding, or fail-closed by tier. Never treat a Redis timeout as proof that a token is invalid.

## 5. IdP Protection Across Caching, Refresh, and Retries

### 5.1. JWT key rotation, key caching, and timeouts

With `issuer-uri`, Spring Security performs discovery/JWKS to validate JWTs and can cache the JWK Set. If a new key `kid` appears during an AS outage, the gateway has no basis to verify the unknown JWT. Never accept tokens by disabling signature checks. Providing both `issuer-uri` and `jwk-set-uri` appropriately can reduce startup coupling to the IdP, while still requiring `iss`/`aud`/`exp` validation and rotation management.

### 5.2. Opaque token positive caching and revocation SLAs

When introspection returns active:

```text
cacheValidUntil = min(
    introspectionCompletedAt + approvedPositiveTtl,
    tokenExp
)
```

A 60s cache TTL creates a window where a newly revoked token can remain accepted for nearly 60s after the previous check, plus AS propagation and in-flight time. If the revocation SLA is 5s, never arbitrarily cache for 60s just to raise the hit ratio. When the AS is down, never treat an expired cache entry as an authenticated principal. Never cache network errors, never cache `active=false` as a principal, and never use unbounded `Mono.cache()`. Manage tenant namespaces, max entries, time bounds, and cross-pod invalidation.

### 5.3. Retries and circuit breakers must not fail open

Never retry invalid signatures, expired tokens, `active=false`, or invalid client secrets; those are not transient errors. For 429/502/503/network resets, allow **at most 1 retry** per backoff/jitter policy within the total deadline, accounting for AS QPS impact. Open circuit => fail-fast/dependency error, **never** `return Mono.just(anonymousOrAdminPrincipal)`. For payment/business-write POSTs, never retry without an idempotency key and transaction policy.

### 5.4. The IdP itself is a shared resource across tenants

Even when tenant A and tenant B have separate quotas, if they share an IdP, both share its outbound connection pool and token/introspection API. Enforce both a global cap and per-tenant quotas. When tenants have independent IdPs, avoid sharing one circuit breaker that lets an IdP A outage block tenant B; use per-issuer breakers/bulkheads alongside a global safety ceiling. Per-tenant quotas must never exceed the aggregate AS limit committed by operators.

## 6. Standalone Java 17: Calculating Concurrent Slots and Budgets

Save `IdentityCapacityDemo.java`:

```java
public class IdentityCapacityDemo {
    static int estimatedInflight(int qps, int latencyMs) {
        return (int) Math.ceil(qps * latencyMs / 1000.0);
    }

    static int remainingBudget(
            int deadlineMs, int authMs,
            int upstreamMs, int reserveMs) {
        return Math.max(0,
            deadlineMs - authMs - upstreamMs - reserveMs);
    }

    public static void main(String[] args) {
        System.out.println("idpInflight=" +
            estimatedInflight(80, 250));
        System.out.println("idpSlowInflight=" +
            estimatedInflight(80, 2000));
        System.out.println("remainingMs=" +
            remainingBudget(1500, 350, 800, 200));
    }
}
```

Run with JDK 17+:

```bash
javac IdentityCapacityDemo.java
java IdentityCapacityDemo
```

**Exact stdout:**

```text
idpInflight=20
idpSlowInflight=160
remainingMs=150
```

This is a sizing calculation, **not a benchmark**, and does not guarantee p99 or peak concurrency. Measure actual distributions, burstiness, retry amplification, and error budgets before finalizing limits.

## 7. Spring Boot 3.5.7 + Spring Cloud Gateway 4.3 Project: Demo Architecture

We build a local project with 3 concrete mechanisms:

1. A high-precedence `WebFilter` performing **pre-auth coarse IP limiting**, without parsing JWT tenants.
2. Spring Security WebFlux Resource Server verifying a **test-only** HS256 JWT—checking signature, issuer, audience, and expiry—and creating `JwtAuthenticationToken`. There is no IdP network in this demo.
3. A `GatewayFilter` using the **post-authentication** tenant claim, limiting per issuer+tenant+subject, scrubbing untrusted headers, and forwarding to an internal `forward:` controller. All happy-path tests run without an external HTTP backend.

We also add `IdentityCallGuard` with a `Semaphore.tryAcquire()` bulkhead + `Mono.timeout` and unit tests. This class **is presented ready for integration when a real outbound IdP/introspection client exists**; do not pretend it intercepts network JWKS for the JWT demo.

### 7.1. Structure

```text
tenant-gateway-defense/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/gateway/
    │   │   ├── GatewayApplication.java
    │   │   ├── FixedWindowBudget.java
    │   │   ├── IdentityCallGuard.java
    │   │   ├── SecurityConfig.java
    │   │   ├── GatewayRoutes.java
    │   │   └── EchoController.java
    │   └── resources/application.properties
    └── test/java/demo/gateway/
        ├── FixedWindowBudgetTests.java
        ├── IdentityCallGuardTests.java
        └── GatewayHttpTests.java
```

Do not add Servlet `spring-boot-starter-web`. The **Spring Cloud 2025.0** release train uses the newer `spring-cloud-starter-gateway-server-webflux` starter and the `spring.cloud.gateway.server.webflux` prefix. The chosen versions serve as a learning baseline; production must use a supported release with security patches.

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
    <artifactId>tenant-gateway-defense</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <spring-cloud.version>2025.0.0</spring-cloud.version>
    </properties>
    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-dependencies</artifactId>
                <version>${spring-cloud.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
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
spring.application.name=tenant-gateway-defense
server.port=8080

# JWT decoder/key is created in Java ONLY for the demo.
# Do not configure fake issuer-uri or JWKS endpoints in this project.
```

`src/main/java/demo/gateway/GatewayApplication.java`:

```java
package demo.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GatewayApplication {
    public static void main(String[] args) {
        SpringApplication.run(GatewayApplication.class, args);
    }
}
```

### 7.2. FixedWindowBudget.java: atomic per-key limiter within one process

`src/main/java/demo/gateway/FixedWindowBudget.java`:

```java
package demo.gateway;

import java.time.Clock;
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicBoolean;
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;

public final class FixedWindowBudget {
    private record Window(long resetMs, int count) {}

    private final Clock clock;
    private final Cache<String, Window> entries;

    public FixedWindowBudget(Clock clock, long maxKeys) {
        this.clock = Objects.requireNonNull(clock);
        if (maxKeys < 1) {
            throw new IllegalArgumentException("maxKeys");
        }
        entries = Caffeine.newBuilder()
            .maximumSize(maxKeys)
            .expireAfterWrite(Duration.ofMinutes(2))
            .build();
    }

    public boolean allow(String key, int limit, Duration window) {
        Objects.requireNonNull(key);
        Objects.requireNonNull(window);
        if (limit < 1 || window.toMillis() < 1) {
            throw new IllegalArgumentException("Invalid quota");
        }

        long now = clock.millis();
        long duration = window.toMillis();
        AtomicBoolean granted = new AtomicBoolean(false);

        entries.asMap().compute(key, (k, previous) -> {
            if (previous == null || now >= previous.resetMs()) {
                granted.set(true);
                return new Window(now + duration, 1);
            }
            if (previous.count() < limit) {
                granted.set(true);
                return new Window(
                    previous.resetMs(), previous.count() + 1);
            }
            return previous;
        });
        return granted.get();
    }
}
```

**Explicit limitations:** Fixed windows allow bursts across window boundaries; Caffeine eviction before reset can re-grant quota; state resets on pod restart and is **not distributed**. This is a simple teaching pattern, not a production global/billing quota limiter. Choose `RedisRateLimiter`/edge rate limiting when running multiple replicas.

### 7.3. IdentityCallGuard.java: semaphore + deadline to protect the AS

`src/main/java/demo/gateway/IdentityCallGuard.java`:

```java
package demo.gateway;

import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.Semaphore;
import reactor.core.publisher.Mono;

public final class IdentityCallGuard {
    public static final class Busy extends RuntimeException {
        public Busy() {
            super("Identity calls are saturated");
        }
    }

    private final Semaphore permits;
    private final Duration deadline;

    public IdentityCallGuard(int concurrent, Duration deadline) {
        if (concurrent < 1) {
            throw new IllegalArgumentException("concurrent");
        }
        this.deadline = Objects.requireNonNull(deadline);
        if (deadline.isZero() || deadline.isNegative()) {
            throw new IllegalArgumentException("deadline");
        }
        permits = new Semaphore(concurrent);
    }

    public <T> Mono<T> protect(Mono<T> remoteCall) {
        Objects.requireNonNull(remoteCall);
        return Mono.defer(() -> {
            if (!permits.tryAcquire()) {
                return Mono.error(new Busy());
            }
            return remoteCall.timeout(deadline)
                .doFinally(signal -> permits.release());
        });
    }
}
```

`tryAcquire()` **never blocks** the Netty thread. `doFinally` releases the slot on response, error, timeout, or cancellation. To use it with introspection:

```java
// Fragment; requires a real introspector and an accessToken.
IdentityCallGuard guard =
    new IdentityCallGuard(32, Duration.ofMillis(350));

Mono<OAuth2AuthenticatedPrincipal> principal = guard.protect(
    Mono.defer(() -> actualIntrospector.introspect(accessToken)));
```

Wire the guard **directly onto the outbound path to the IdP**. Wrapping in `Mono.defer` defers the remote call until subscription time. On `Busy`/timeout, fail closed; never synthesize a fallback principal. In real environments, add WebClient connect/response timeouts, pool caps, metrics, circuit breakers, and optionally partition guards per issuer.

### 7.4. SecurityConfig.java: Bearer-only JWT demo, pre-auth limiter

`src/main/java/demo/gateway/SecurityConfig.java`:

```java
package demo.gateway;

import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Duration;
import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.web.server.WebFilter;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {
    static final String ISSUER = "https://issuer.demo.invalid";
    static final String AUDIENCE = "gateway-api";

    // Demo/test ONLY: production uses JWK/trust from the IdP.
    static final SecretKey DEMO_KEY = new SecretKeySpec(
        "gateway-demo-32-byte-minimum-not-production-secret"
            .getBytes(StandardCharsets.UTF_8), "HmacSHA256");

    @Bean
    ReactiveJwtDecoder jwtDecoder() {
        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withSecretKey(DEMO_KEY)
                .macAlgorithm(MacAlgorithm.HS256).build();

        OAuth2TokenValidator<Jwt> aud = jwt ->
            jwt.getAudience().contains(AUDIENCE)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token",
                        "Wrong audience", null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER), aud));
        return decoder;
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/public").permitAll()
                .pathMatchers("/api/**").authenticated()
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults()))
            .formLogin(form -> form.disable())
            .httpBasic(basic -> basic.disable())
            .csrf(csrf -> csrf.disable())
            .build();
    }

    @Bean("ingressBudget")
    FixedWindowBudget ingressBudget() {
        return new FixedWindowBudget(Clock.systemUTC(), 10000);
    }

    @Bean("tenantBudget")
    FixedWindowBudget tenantBudget() {
        return new FixedWindowBudget(Clock.systemUTC(), 10000);
    }

    @Bean
    @Order(Ordered.HIGHEST_PRECEDENCE)
    WebFilter coarsePreAuth(
            @Qualifier("ingressBudget") FixedWindowBudget budget) {
        return (exchange, chain) -> {
            String path = exchange.getRequest().getPath().value();
            if (!path.startsWith("/api/")) {
                return chain.filter(exchange);
            }

            var peer = exchange.getRequest().getRemoteAddress();
            String address = peer == null ? "unknown" :
                peer.getAddress() == null
                    ? peer.getHostString()
                    : peer.getAddress().getHostAddress();

            // 100/minute is a demo rate, not sized for a real IdP.
            if (!budget.allow("ip:" + address, 100,
                    Duration.ofMinutes(1))) {
                exchange.getResponse().setStatusCode(
                    HttpStatus.TOO_MANY_REQUESTS);
                return exchange.getResponse().setComplete();
            }
            return chain.filter(exchange);
        };
    }
}
```

**Ordering:** `@Order(Ordered.HIGHEST_PRECEDENCE)` on `WebFilter` places admission early in the WebFlux chain. Gateway `GlobalFilter`s or route-specific `GatewayFilter`s are not identical to `WebFilter`s; verify ordering using integration tests with a spy on the introspection/JWKS client before production.

CSRF is disabled **only** because the demo accepts **header-only** Bearer authentication and disables WebSession cookies, forms, and HTTP Basic fallbacks. If a product adds a browser BFF/session cookies, split `SecurityWebFilterChain`s and keep CSRF on mutations rather than copying `csrf.disable()` site-wide.

### 7.5. GatewayRoutes.java: quota derived from JwtAuthenticationToken

`src/main/java/demo/gateway/GatewayRoutes.java`:

```java
package demo.gateway;

import java.time.Duration;
import java.util.Set;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.cloud.gateway.route.RouteLocator;
import org.springframework.cloud.gateway.route.builder.RouteLocatorBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Configuration
public class GatewayRoutes {
    private static final Set<String> ALLOWED =
        Set.of("acme", "globex");

    private static Mono<Void> deny(
            ServerWebExchange exchange, HttpStatus status) {
        exchange.getResponse().setStatusCode(status);
        return exchange.getResponse().setComplete();
    }

    @Bean
    GatewayFilter verifiedTenantQuota(
            @Qualifier("tenantBudget") FixedWindowBudget budget) {
        return (exchange, chain) -> exchange.getPrincipal()
            .ofType(JwtAuthenticationToken.class)
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.UNAUTHORIZED, "Bearer JWT required")))
            .flatMap(auth -> {
                String tenant = auth.getToken()
                    .getClaimAsString("tenant_id");

                if (tenant == null || !ALLOWED.contains(tenant)) {
                    return deny(exchange, HttpStatus.FORBIDDEN);
                }

                String key = auth.getToken().getIssuer()
                    + "|" + tenant + "|" + auth.getName();

                if (!budget.allow(key, 2,
                        Duration.ofSeconds(30))) {
                    return deny(
                        exchange, HttpStatus.TOO_MANY_REQUESTS);
                }

                var safeRequest = exchange.getRequest().mutate()
                    .headers(h -> {
                        h.remove("X-Tenant-Id");
                        h.remove("X-Verified-Tenant");
                        h.remove(HttpHeaders.AUTHORIZATION);
                        h.set("X-Verified-Tenant", tenant);
                    }).build();

                return chain.filter(
                    exchange.mutate().request(safeRequest).build());
            });
    }

    @Bean
    RouteLocator routes(
            RouteLocatorBuilder builder,
            GatewayFilter verifiedTenantQuota) {
        return builder.routes()
            .route("orders", r -> r.path("/api/orders")
                .filters(f -> f.filter(verifiedTenantQuota))
                .uri("forward:///__demo_upstream"))
            .build();
    }
}
```

Here the key is **per-user-within-tenant**, not tenant-global. The filter runs only **after** Spring Security's Bearer authentication and accepts only `JwtAuthenticationToken`. It rejects unknown/missing tenants and never falls back to user-supplied headers. The Gateway removes `X-Tenant-Id`, `X-Verified-Tenant`, and raw `Authorization`, then adds the verified tenant for the internal fixture. In a real system where the backend needs a Bearer token, enforce a token relay/exchange policy with the right `aud` rather than mechanically stripping it or blindly forwarding tokens to every upstream.

`forward:///__demo_upstream` is an **in-process internal route**, not a real HTTPS/mTLS proxy. Out-of-process backends must not be directly reachable with `X-Verified-Tenant=admin`; enforce mTLS/service identity and network isolation.

### 7.6. EchoController.java: observing spoofed headers

`src/main/java/demo/gateway/EchoController.java`:

```java
package demo.gateway;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class EchoController {

    @GetMapping(value = "/public",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping(value = "/__demo_upstream",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> echo(
        @RequestHeader(value = "X-Verified-Tenant",
            required = false) String tenant,
        @RequestHeader(value = "X-Tenant-Id",
            required = false) String untrusted,
        @RequestHeader(value = "Authorization",
            required = false) String bearer) {
        return Mono.just("tenant=" + tenant
            + ";untrustedForwarded=" + (untrusted != null)
            + ";bearerForwarded=" + (bearer != null));
    }
}
```

Expected when a caller sends a valid JWT with `tenant_id=acme` alongside header `X-Tenant-Id=globex`:

```text
tenant=acme;untrustedForwarded=false;bearerForwarded=false
```

Direct `GET /__demo_upstream` is blocked by `anyExchange().denyAll()`, though in production that must never replace network policy.

## 8. Java 17 Tests for the Limiter and IdP Concurrency

### 8.1. FixedWindowBudgetTests.java

`src/test/java/demo/gateway/FixedWindowBudgetTests.java`:

```java
package demo.gateway;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class FixedWindowBudgetTests {
    static class MutableClock extends Clock {
        AtomicReference<Instant> now = new AtomicReference<>(
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
            now.updateAndGet(v -> v.plusSeconds(seconds));
        }
    }

    @Test
    void twoAllowedThirdDenied() {
        var clock = new MutableClock();
        var limiter = new FixedWindowBudget(clock, 100);
        assertTrue(limiter.allow(
            "acme|alice", 2, Duration.ofSeconds(30)));
        assertTrue(limiter.allow(
            "acme|alice", 2, Duration.ofSeconds(30)));
        assertFalse(limiter.allow(
            "acme|alice", 2, Duration.ofSeconds(30)));
    }

    @Test
    void nextWindowResetsCounter() {
        var clock = new MutableClock();
        var limiter = new FixedWindowBudget(clock, 100);
        assertTrue(limiter.allow("alice", 1,
            Duration.ofSeconds(10)));
        assertFalse(limiter.allow("alice", 1,
            Duration.ofSeconds(10)));
        clock.advance(10);
        assertTrue(limiter.allow("alice", 1,
            Duration.ofSeconds(10)));
    }

    @Test
    void differentTenantKeysAreIndependent() {
        var limiter = new FixedWindowBudget(
            Clock.systemUTC(), 100);
        assertTrue(limiter.allow("acme|alice", 1,
            Duration.ofSeconds(30)));
        assertTrue(limiter.allow("globex|alice", 1,
            Duration.ofSeconds(30)));
        assertFalse(limiter.allow("acme|alice", 1,
            Duration.ofSeconds(30)));
    }

    @Test
    void invalidQuotaAndCapacityRejectConfiguration() {
        assertThrows(IllegalArgumentException.class,
            () -> new FixedWindowBudget(
                Clock.systemUTC(), 0));
        var limiter = new FixedWindowBudget(
            Clock.systemUTC(), 100);
        assertThrows(IllegalArgumentException.class,
            () -> limiter.allow("key", 0,
                Duration.ofSeconds(1)));
        assertThrows(IllegalArgumentException.class,
            () -> limiter.allow("key", 1,
                Duration.ZERO));
    }
}
```

### 8.2. IdentityCallGuardTests.java

`src/test/java/demo/gateway/IdentityCallGuardTests.java`:

```java
package demo.gateway;

import java.time.Duration;
import java.util.concurrent.TimeoutException;

import org.junit.jupiter.api.Test;
import reactor.core.Disposable;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

class IdentityCallGuardTests {

    @Test
    void normalResponsePasses() {
        var guard = new IdentityCallGuard(
            1, Duration.ofSeconds(1));
        StepVerifier.create(guard.protect(Mono.just("ok")))
            .expectNext("ok")
            .verifyComplete();
    }

    @Test
    void secondInFlightCallFailsFast() {
        var guard = new IdentityCallGuard(
            1, Duration.ofSeconds(5));
        Disposable hold =
            guard.protect(Mono.<String>never()).subscribe();
        try {
            StepVerifier.create(
                    guard.protect(Mono.just("second")))
                .expectError(IdentityCallGuard.Busy.class)
                .verify();
        }
        finally {
            hold.dispose();
        }
        StepVerifier.create(guard.protect(Mono.just("free")))
            .expectNext("free")
            .verifyComplete();
    }

    @Test
    void timeoutDoesNotTurnIntoSuccessfulPrincipal() {
        var guard = new IdentityCallGuard(
            1, Duration.ofMillis(40));
        StepVerifier.create(
                guard.protect(Mono.<String>never()))
            .expectError(TimeoutException.class)
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void invalidGuardConfigurationFails() {
        assertThrows(IllegalArgumentException.class,
            () -> new IdentityCallGuard(
                0, Duration.ofSeconds(1)));
        assertThrows(IllegalArgumentException.class,
            () -> new IdentityCallGuard(
                1, Duration.ZERO));
    }
}
```

These tests verify admission, demo-clock TTLs, concurrency, and timeout behavior locally. They do not verify IdP networking/TLS or Redis distributed limiters. `Semaphore.tryAcquire` does not block; cancellation releases the slot via `doFinally`.

## 9. HTTP Integration Tests: Gateway + Real Local JWTs

`GatewayHttpTests.java` uses `NimbusJwtEncoder` to create signed HS256 JWT fixtures and sends them over the network to Spring Boot `RANDOM_PORT`. `ReactiveJwtDecoder` verifies signature, issuer, audience, and expiry; the GatewayFilter then enforces the tenant. We do not use `mockJwt()` to inject Authentication directly, as that would bypass the real decoder. **The HS256 key is strictly for localhost/tests**—never deploy it to production.

`src/test/java/demo/gateway/GatewayHttpTests.java`:

```java
package demo.gateway;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.List;
import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;

import com.nimbusds.jose.jwk.source.ImmutableSecret;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GatewayHttpTests {

    @Autowired
    WebTestClient client;

    private static String signed(
            String sub, String tenant, String issuer,
            String audience, SecretKey key) {

        Instant now = Instant.now();
        JwtClaimsSet.Builder builder = JwtClaimsSet.builder()
            .issuer(issuer)
            .subject(sub)
            .audience(List.of(audience))
            .issuedAt(now)
            .notBefore(now.minusSeconds(5))
            .expiresAt(now.plusSeconds(900))
            .claim("scope", "orders.read");

        if (tenant != null) {
            builder.claim("tenant_id", tenant);
        }

        return new NimbusJwtEncoder(new ImmutableSecret<>(key))
            .encode(JwtEncoderParameters.from(
                JwsHeader.with(MacAlgorithm.HS256).build(),
                builder.build()))
            .getTokenValue();
    }

    private static String valid(String sub, String tenant) {
        return signed(sub, tenant,
            SecurityConfig.ISSUER,
            SecurityConfig.AUDIENCE, SecurityConfig.DEMO_KEY);
    }

    @Test
    void publicRouteCanBeCalledAnonymously() {
        client.get().uri("/public")
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void missingBearerIs401() {
        client.get().uri("/api/orders")
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void malformedBearerIs401() {
        client.get().uri("/api/orders")
            .headers(h -> h.setBearerAuth("not-a-jwt"))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void wrongIssuerIs401() {
        String jwt = signed("wrong-issuer", "acme",
            "https://untrusted.invalid",
            SecurityConfig.AUDIENCE, SecurityConfig.DEMO_KEY);
        client.get().uri("/api/orders")
            .headers(h -> h.setBearerAuth(jwt))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void wrongAudienceIs401() {
        String jwt = signed("wrong-aud", "acme",
            SecurityConfig.ISSUER,
            "different-api", SecurityConfig.DEMO_KEY);
        client.get().uri("/api/orders")
            .headers(h -> h.setBearerAuth(jwt))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void badSignatureIs401() {
        SecretKey wrong = new SecretKeySpec(
            "bad-signing-key-32-chars-minimum-test-only"
                .getBytes(StandardCharsets.UTF_8),
            "HmacSHA256");
        String jwt = signed("wrong-signature", "acme",
            SecurityConfig.ISSUER,
            SecurityConfig.AUDIENCE, wrong);
        client.get().uri("/api/orders")
            .headers(h -> h.setBearerAuth(jwt))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void missingTenantClaimIs403() {
        client.get().uri("/api/orders")
            .headers(h -> h.setBearerAuth(
                valid("no-tenant", null)))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void tenantOutsideAllowlistIs403() {
        client.get().uri("/api/orders")
            .headers(h -> h.setBearerAuth(
                valid("bad-tenant", "unlisted")))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void forgedTenantHeaderCannotOverrideSignedTenant() {
        client.get().uri("/api/orders")
            .headers(h -> {
                h.setBearerAuth(valid("spoofed", "acme"));
                h.set("X-Tenant-Id", "globex");
                h.set("X-Verified-Tenant", "admin");
            })
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo(
                "tenant=acme;untrustedForwarded=false;" +
                "bearerForwarded=false");
    }

    @Test
    void legitimateTenantGetsVerifiedForwardedHeader() {
        client.get().uri("/api/orders")
            .headers(h -> h.setBearerAuth(
                valid("forwarded", "globex")))
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo(
                "tenant=globex;untrustedForwarded=false;" +
                "bearerForwarded=false");
    }

    @Test
    void quotaAllowsTwoRequestsThen429() {
        String token = valid("quota-test", "acme");
        client.get().uri("/api/orders")
            .headers(h -> h.setBearerAuth(token))
            .exchange().expectStatus().isOk();
        client.get().uri("/api/orders")
            .headers(h -> h.setBearerAuth(token))
            .exchange().expectStatus().isOk();
        client.get().uri("/api/orders")
            .headers(h -> h.setBearerAuth(token))
            .exchange().expectStatus().isEqualTo(429);
    }

    @Test
    void sameSubjectDifferentTenantHasOwnQuota() {
        String acme = valid("same-subject", "acme");
        String globex = valid("same-subject", "globex");

        client.get().uri("/api/orders")
            .headers(h -> h.setBearerAuth(acme))
            .exchange().expectStatus().isOk();
        client.get().uri("/api/orders")
            .headers(h -> h.setBearerAuth(acme))
            .exchange().expectStatus().isOk();
        client.get().uri("/api/orders")
            .headers(h -> h.setBearerAuth(globex))
            .exchange().expectStatus().isOk();
    }

    @Test
    void directInternalEndpointIsDenied() {
        client.get().uri("/__demo_upstream")
            .headers(h -> h.setBearerAuth(
                valid("internal", "acme")))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void cookieAloneIsNotBearerAuth() {
        client.get().uri("/api/orders")
            .cookie("access_token", "irrelevant")
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void basicAuthIsNotBearerJwt() {
        client.get().uri("/api/orders")
            .headers(h -> h.setBasicAuth("alice", "password"))
            .exchange().expectStatus().isUnauthorized();
    }
}
```

Total of **23 sample tests**: 4 for the limiter, 4 for the guard, and 15 HTTP tests. This code is for learners to run themselves; **there is no claim that Maven was executed in your environment**. Unit tests verify local logic; HTTP tests verify the real JWT decoder and local Gateway filters, **without** proving real IdP introspection, JWKS fetching/key rotation, Redis, or multi-pod quotas.

### 9.1. Running on localhost

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

Observe requests requiring no issued JWT:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/orders
curl -i -H 'Authorization: Bearer invalid' \
  http://localhost:8080/api/orders
```

Expect public 200, missing/malformed Bearer 401, unless the coarse pre-auth quota of 100 requests/minute from the same remote peer is exceeded, returning **429 before authentication**. No Authorization Server runs inside the app; signed demo tokens are generated by test helpers. Never ship `DEMO_KEY` or test tokens to production.

## 10. Production: RedisRateLimiter and Gateway Timeouts

### 10.1. Redis-based tenant-wide quota

In multi-replica deployments, use Spring Cloud Gateway 4.3 `RequestRateLimiter` + reactive Redis. Add the dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis-reactive</artifactId>
</dependency>
```

**Illustrative** production YAML replacing the demo route (never declare both routes with the same predicate without explicit ordering):

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: tenant-orders
              uri: https://orders.internal.example
              predicates:
                - Path=/api/orders/**
              filters:
                - name: RequestRateLimiter
                  args:
                    key-resolver: "#{@verifiedTenantKeyResolver}"
                    redis-rate-limiter.replenishRate: 10
                    redis-rate-limiter.burstCapacity: 20
                    redis-rate-limiter.requestedTokens: 1
```

`redis-rate-limiter.replenishRate` is tokens per second, `burstCapacity` is the burst budget, and `requestedTokens` is the cost per request. Default on exceeded limit → **429**. `KeyResolver` must read the **verified principal**:

```java
@Bean
KeyResolver verifiedTenantKeyResolver() {
    return exchange -> exchange.getPrincipal()
        .ofType(JwtAuthenticationToken.class)
        .flatMap(auth -> Mono.justOrEmpty(
            auth.getToken().getClaimAsString("tenant_id")))
        .filter(tenant -> ALLOWED_TENANTS.contains(tenant))
        .map(tenant -> "trusted-issuer:" + tenant);
}
```

The fragment requires imports for `KeyResolver`, `JwtAuthenticationToken`, `Mono`, and the `ALLOWED_TENANTS` registry. In multi-issuer systems, the key must include the **verified issuer ID**, never a hardcoded `trusted-issuer`. Never use a user query param or `X-Tenant-Id` as the key. By policy, missing keys must be rejected; do not set `deny-empty-key=false` on quota-protected routes.

A per-tenant limiter **does not enforce per-user quotas**. To enforce both, layer independent limiters and define per-route costs; Redis also needs TLS/auth, timeouts, and an availability/fail policy. During a Redis outage, never allow tenants unlimited traffic due to an uncontrolled fallback.

### 10.2. Downstream timeouts at the Gateway

In Spring Cloud 2025.0, use the `spring.cloud.gateway.server.webflux` prefix:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          httpclient:
            connect-timeout: 200
            response-timeout: 750ms
          routes:
            - id: api
              uri: https://backend.internal.example
              predicates:
                - Path=/api/**
              metadata:
                connect-timeout: 200
                response-timeout: 750
```

Global connect timeout is in milliseconds, and global response timeout is a Java `Duration`; per-route metadata response/connect timeouts are expressed in milliseconds. Never confuse these settings with the `WebClient` calling introspection. Both still require an overall API deadline.

### 10.3. IdP WebClient timeouts are configured separately

Fragment:

```java
HttpClient netty = HttpClient.create()
    .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 100)
    .responseTimeout(Duration.ofMillis(250));

WebClient idpClient = WebClient.builder()
    .clientConnector(new ReactorClientHttpConnector(netty))
    .build();

Mono<IdpReply> result = idpClient.post()
    .uri("https://trusted-idp.example.org/introspect")
    .retrieve()
    .bodyToMono(IdpReply.class)
    .timeout(Duration.ofMillis(350));
```

Requires `IdpReply`, imports, and proper client auth. This fragment highlights that **HTTP connect, response, and overall timeouts are distinct**. In production, introspection typically requires Basic/mTLS/`private_key_jwt` client authentication; never send a WebClient carrying IdP secrets to a user-controlled URI to avoid SSRF. Never place access tokens or client secrets in URL queries or HTTP logs.

### 10.4. Circuit breakers and retries in the right place

Gateway's `CircuitBreaker` route filter (Spring Cloud CircuitBreaker/Reactor Resilience4j) protects business upstreams; to circuit-break **IdP introspection**, wrap the outbound IdP client/`ReactiveOpaqueTokenIntrospector` separately. Scope breakers per issuer so an error on tenant A does not trip tenant B. When a circuit is open, **never return a success principal**. For 429/503/backend timeouts, retry selectively with bounded attempts inside the total deadline; never retry business POSTs lacking an idempotency key.

## 11. Mandatory Staging Tests Beyond Local Code

- **Pre-auth ordering:** flood invalid Bearer tokens and spy/mock call counts on `SpringReactiveOpaqueTokenIntrospector` to confirm 429 triggers **before** network introspection.
- **IdP outage/latency:** send issued tokens while introspection returns 429/5xx/timeouts; protected endpoints must fail rather than succeed. Confirm overall deadlines and that bulkheads do not leak slots on cancellation.
- **JWT keys:** key rotation, unknown `kid`, wrong issuer/audience, and JWK fetch timeouts never bypass signatures.
- **Tenant spoofing:** wrong `X-Tenant-Id`, forged `Forwarded`, path tenant mismatch, identical subject across different issuers/tenants, unauthorized tenant.
- **Hierarchical quotas:** tenant total ≤ plan and per-subject ≤ user quota across **N pods**, not just one process.
- **Redis outage:** test the approved fail behavior and metrics/alerts; never silently turn off limits.
- **Long requests:** slow backend p99, open breaker, idempotent retry attempts, 503/504 statuses.
- **Bearer privacy:** no out-of-scope token relay, log redaction, stripping untrusted verified headers, backend mTLS.
- **Revocation:** with opaque positive caching, measure the stale window against the SLA; never claim instant revocation for offline JWTs.
- **Browser/BFF:** CSRF session mutations, SameSite/Origin/CSP if cookie auth is added; the Bearer-only demo lacks those paths.
- **Fairness:** a flooding tenant cannot starve the entire IdP pool, one issuer's outage does not break other issuers, and the global safety budget still holds.

Never extrapolate staging behavior from `mockJwt` or local signed fixtures. In-process forward routes do not test TLS/mTLS on a real gateway → backend connection.

## 12. Observability and Operations

| Metric / SLI | Purpose |
| --- | --- |
| `gateway.requests` by route/status | RPS, 200/401/403/429/503/504 |
| `preauth.rejected` by trusted ingress class | Detect invalid-token floods before the IdP |
| `tenant.quota.rejected` by tier | Fairness/abuse; avoid raw user labels |
| `jwt.verify.duration`, `jwks.fetch.miss` | CPU/JWKS refresh issues |
| `introspection.duration` p50/p95/p99 | IdP cache-miss latency |
| `idp.inflight`, `idp.bulkhead.rejected` | Capacity/saturation |
| `idp.circuit.state`, `idp.retry.attempts` | Prevent retry storms and cross-issuer breakers |
| `redis.ratelimiter.duration`/errors | Distributed quota dependency |
| `gateway.backend.duration`/errors | Distinguish slow downstream from slow IdP |
| `revocation.observed.latency` | Freshness SLA of opaque token cache |
| Reactor Netty pool wait, event loop lag | Contention / degraded p99 |

Never use raw access tokens, client secrets, user emails, IPs, or sensitive tenant IDs as high-cardinality labels without approval. Use route templates, allowlisted issuer IDs, tenant tiers, and bounded correlation IDs for investigation. Maintain clear runbooks for "IdP outage," "Redis outage," "unknown kid," "tenant flood," "expired tokens flood," and emergency TTL/retry reduction.

## 13. Common Mistakes

| Anti-pattern | Consequence | Alternative |
| --- | --- | --- |
| Rate-limiting only after Authentication | Forged tokens already overloaded the IdP | Pre-auth coarse admission |
| Pre-auth keyed by `X-Tenant-Id` | Attacker picks arbitrary tenant buckets | Trusted IP/ingress metadata |
| Post-auth using query tenant/user | Quota spoofing/bypass | Verified `JwtAuthenticationToken` |
| Per-user key only | High-user-count tenant exceeds total plan | Tenant-wide + user quotas |
| Treating local limiter as global | N pods multiply the limit | Redis/distributed limiter |
| Falling back to a default tenant when missing | Cross-tenant data leak | Deny unknown/mismatch |
| Fetching JWKS from unverified token `iss` | SSRF, JWKS fetch storm | Issuer allowlist |
| Mistaking JWKS cache for revocation check | Revoked tokens work until `exp` | Introspection/denylist/events if needed |
| Returning last-known-good forever on IdP timeout | Fail-open | No stale-on-error |
| Retrying invalid tokens / `active=false` | Retry storms and operational noise | Never retry auth failures |
| Unbounded concurrent IdP calls | Pool starvation when AS slows down | Semaphore/bulkhead + deadline |
| Using Gateway httpclient timeout for IdP WebClient | IdP calls still hang | Separate IdP transport limits |
| `permitAll` when circuit opens | Authentication bypass | Fail closed |
| Backend trusts Internet `X-Verified-Tenant` | Header spoofing | Strip, rewrite, and mTLS/private ingress |
| Relaying raw JWTs to every upstream | Token leakage, wrong audience | Explicit token exchange/relay policy |
| Disabling CSRF on web cookie logins | CSRF mutations | Separate chain with CSRF |
| Treating local signed-JWT tests as network IdP tests | Missing TLS, JWKS, revocation coverage | Staging mock-AS and real IdP |
| Logging full tokens/introspection responses | Credential leak | Redaction + safe metadata |

## 14. Production Checklist

1. Define trust boundaries: WAF/ingress → Gateway → IdP/AS → tenant services.
2. Enforce pre-auth coarse throttling early enough to curb JWT/introspection amplification.
3. JWT/opaque Authentication verifies tokens and issuer/audience before reading tenant claims.
4. Enforce post-auth quotas per issuer/tenant/user plus global per-IdP capacity.
5. Prevent header/path/query spoofing; never derive IdP URLs from untrusted issuers.
6. Clearly separate token/JWKS caching from opaque introspection positive-cache/revocation SLAs.
7. Set total IdP deadlines, connect/pool/TLS/response timeouts, bulkheads, and fail-closed circuits.
8. Set separate backend route timeouts/circuits, bounded retries, and idempotency policies.
9. Multi-pod quotas use Redis/trusted distributed limiters, not local Caffeine alone.
10. Strip/rewrite identity headers, block direct backend ingress, enforce mTLS/service identity.
11. Keep CSRF wherever browser cookie auth exists; never copy Bearer-only API settings.
12. Test negative cases (401/403/429), IdP/Redis outages, revocation, wrong issuer/audience.
13. Monitor p99, in-flight calls, quota rejects, unknown keys, retry amplification, and fairness.
14. Maintain runbooks for lowering TTLs, restricting quota edits, and checking Spring Boot/Cloud versions before upgrades.

## 15. Review Questions

**1.** Why is a post-auth tenant limiter insufficient to protect introspection?  
Because unverified tokens can still trigger AS calls before a principal ever exists.

**2.** Should pre-auth limits key off `X-Tenant-Id`?  
No. Clients can spoof or rotate headers arbitrarily.

**3.** Can JWTs avoid hitting the IdP on every request?  
Yes, signatures are verified locally using cached JWKs; this does not provide immediate revocation freshness.

**4.** Does a per-user quota cap the entire tenant?  
No; an independent tenant-wide bucket is required.

**5.** How does a bulkhead differ from a rate limiter?  
A bulkhead caps concurrent in-flight calls while a rate limiter caps request rate; both need timeouts.

**6.** When the IdP fails, can a synthetic fallback principal be issued?  
No. Fail closed; dependency status depends on exception mapping, but protected actions must never return 2xx.

**7.** Does the Gateway backend timeout automatically limit the introspection WebClient?  
No. The IdP client needs its own deadlines.

**8.** Why is `RedisRateLimiter` needed for multi-pod deployments?  
Local limiters apply per pod and do not enforce cluster-wide quotas.

**9.** What should happen for unknown issuers or tenants?  
Deny; never use arbitrary discovery or a default tenant.

**10.** Is CSRF eliminated simply because a site uses OAuth2?  
No. Cookie-auth/browser mutations still need CSRF; the demo is Bearer-header-only.

**11.** Why never retry business POSTs unconditionally?  
Timeouts can occur after upstream already executed the side effect; idempotency is required.

**12.** What do the local tests prove?  
JWT signature/audience/issuer validation, that tenant headers do not override, and 429 after quota. They do not prove Redis, network JWKS, opaque revocation, or multi-replica behavior.

### Official References

- Spring Cloud 2025.0 release (Boot 3.5 compatibility): https://spring.io/blog/2025/05/29/spring-cloud-2025-0-0-is-abvailable/
- Spring Cloud 2025.0 release notes, new starter/prefixes: https://github.com/spring-cloud/spring-cloud-release/wiki/Spring-Cloud-2025.0-Release-Notes
- Spring Cloud Gateway 4.3 starter: https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/starter.html
- Spring Cloud Gateway 4.3 RequestRateLimiter: https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/gatewayfilter-factories/requestratelimiter-factory.html
- Spring Cloud Gateway 4.3 HTTP timeouts: https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/http-timeouts-configuration.html
- Spring Cloud Gateway 4.3 CircuitBreaker: https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/gatewayfilter-factories/circuitbreaker-filter-factory.html
- Spring Security 6.5 Reactive JWT: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
- Spring Security 6.5 Reactive Opaque: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/opaque-token.html
- RFC 7662 – Token Introspection: https://www.rfc-editor.org/rfc/rfc7662
- RFC 6750 – Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750
- Reactor Netty HTTP Client: https://projectreactor.io/docs/netty/release/reference/http-client.html

**In summary:** A multi-tenant gateway protects the IdP effectively through **pre-auth coarse throttling before verification costs**, **post-auth tenant/user quotas on verified identities**, **identity-specific rate/concurrency caps**, total deadlines, and fail-closed circuits. Never derive tenants from self-declared headers, never equate JWK caching with revocation, and never rely solely on local limiters to claim cluster-wide quotas. Run local signed-JWT tests and add staging Redis/IdP/network-failure tests before deployment.