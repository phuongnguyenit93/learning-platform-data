# Custom RateLimiter and Failure Policies When the Rate-Limit Store Fails

## 1. The Problem: Rate Limiting Must Work Across Multiple Gateways

In a microservices system, clients call APIs through **Spring Cloud Gateway Server WebFlux**. The Gateway picks a route via predicates, runs a filter chain, may rewrite paths/headers, uses `lb://service-id` to discover backends, and forwards requests. To shield the system from a user, partner, or application sending too many requests, we place **rate limiting** right at the entry point:

~~~text
Client → Gateway → RequestRateLimiter → orders-service
                            │
                            └── Redis / quota store
~~~

At small scale, an in-RAM counter seems sufficient. Yet with three Gateway replicas, if each replica grants 100 requests/minute without a shared store, the same client can receive roughly **300 requests/minute** when traffic spreads across all three replicas. Thus, rate-limiting policies enforcing **cluster-wide quotas** typically require a distributed store or coordinator.

A harder question is: **what happens when Redis or the quota store loses connectivity?** Every option has a trade-off:

- **Fail-open:** keep letting requests through, preserving availability at the risk of losing limits.
- **Fail-closed:** refuse to forward requests when remaining quota cannot be verified, reducing abuse risk while tying API availability to the quota store.
- **Degraded/bounded fallback:** grant a tight temporary fallback budget, though harder to reason about since multiple replicas can hand out budgets concurrently.

This lesson belongs to the **Traffic Limiting** chapter of **SPRING_CLOUD_GATEWAY**. You will learn how to write a custom `RateLimiter`, choose a safe `KeyResolver`, return appropriate status codes, and test Redis outages. These concepts connect closely with authentication, routes/filters, service discovery, circuit breakers, retries, TLS, and observability.

> **Scope:** Examples use **Spring Cloud Gateway Server WebFlux**. Never take Gateway Server MVC APIs and apply them to WebFlux: the two variants use different filters, configs, and key resolver types. The Java sample in section 7 is for learning and must be built and tested against your exact Spring Boot and Spring Cloud BOM before production use.

## 2. Distinguish Three Independent Decisions

When a request hits the Gateway, at least three questions arise:

| Decision | Component | What If It Fails? |
| --- | --- | --- |
| **Who may call the API?** | Spring Security, JWT/session auth, and authorization | Typically **401** or **403** |
| **Has the caller exceeded quota?** | `RequestRateLimiter` + `RateLimiter` | Defaults to **429 Too Many Requests** when quota truly runs out |
| **Can quota even be checked?** | Redis, quota service, or distributed cache | **Not equivalent to exceeding quota**; needs a dedicated outage policy |

Never collapse all three outcomes into a single 429 error. If Redis disconnects, the server **does not know** how many tokens the client spent. Returning 429 misleads the client into thinking it exceeded its limit, when the real fault is unavailable quota infrastructure. Under fail-closed, **503 Service Unavailable** usually communicates this far more clearly.

A request should only be forwarded when **authenticated and authorized** and satisfying the active quota policy (or an explicitly allowed fallback). Rate limiting never replaces authorization; authorization never grants unlimited quota.

### 2.1. Processing Flow Diagram

~~~mermaid
flowchart TD
    C["Client request"] --> S{"Authenticated / authorized?"}
    S -->|"No"| A["401 / 403"]
    S -->|"Yes"| K["KeyResolver builds quota key"]
    K --> E{"Trustworthy key?"}
    E -->|"No"| D["Reject per empty-key policy"]
    E -->|"Yes"| R["RateLimiter checks quota store"]
    R --> Q{"Result?"}
    Q -->|"Quota remains"| F["Forward to backend"]
    Q -->|"Quota exhausted"| T["429 Too Many Requests"]
    Q -->|"Store error / timeout"| P{"Outage policy?"}
    P -->|"Fail-closed"| U["503 Service Unavailable"]
    P -->|"Fail-open"| F
    P -->|"Bounded degrade"| B["Local emergency budget"]
    B -->|"Budget remains"| F
    B -->|"Exhausted"| U
~~~

**Note:** Actual runtime execution order depends on Spring Security `WebFilter`s and route `GatewayFilter` ordering. This diagram shows the **desired logical decision sequence**, not a guarantee that filters always execute in that order if misconfigured.

## 3. What Do `RequestRateLimiter`, `KeyResolver`, and `RateLimiter` Do?

In Gateway Server WebFlux, `RequestRateLimiter` is a **GatewayFilter Factory**. It resolves a key, asks a `RateLimiter` whether the request may continue, and then:

1. If `RateLimiter.Response.isAllowed()` is `true`, the request continues down the chain.
2. If `isAllowed()` is `false`, the filter typically completes the response with **429** (status code is configurable).
3. Response headers emitted by the limiter can be added to the HTTP response.
4. If the limiter call signals an **error**, define an appropriate error handler and policy; never treat every error as `isAllowed=false`.

### 3.1. `KeyResolver`

`KeyResolver` provides:

~~~java
public interface KeyResolver {
    Mono<String> resolve(ServerWebExchange exchange);
}
~~~

Examples of keys include **authenticated user ID**, **client/application ID**, **tenant ID**, or a normalized composite key:

~~~text
quota-key = tenant-42 | principal-123 | route-orders-read
~~~

`PrincipalNameKeyResolver` is the default mechanism documented for Gateway WebFlux; it reads the `Principal` name from the exchange. When no key is resolved, the Gateway **denies by default**. Properties governing empty keys can vary in namespace across releases; check configuration properties for your running version rather than silently collapsing all anonymous traffic into one shared key.

### 3.2. `RateLimiter`

A `RateLimiter` bean provides a reactive decision:

~~~java
Mono<RateLimiter.Response> isAllowed(String routeId, String id);
~~~

Where:

- `routeId` identifies the route being processed by the Gateway.
- `id` is the caller key produced by `KeyResolver`.
- The response carries a **boolean allowed** flag and a map of **response headers**.

A custom `RateLimiter` can support tenant-specific quotas, per-route costs, sliding windows, fixed windows, or external quota services. Regardless of algorithm, **keys, state storage, timeouts, and failure policies** matter just as much as the quota math.

### 3.3. Never Use `RequestRateLimiter` YAML Shortcut Syntax

Per Gateway docs, `RequestRateLimiter` requires **expanded configuration**; the example below is **invalid**:

~~~yaml
# WRONG: do not use shortcut notation for RequestRateLimiter.
filters:
  - RequestRateLimiter=10, 20
~~~

Use `name: RequestRateLimiter` with `args`, referencing Spring beans via SpEL such as `"#{@myLimiter}"`.

## 4. Token Bucket and Built-In `RedisRateLimiter` Parameters

WebFlux Gateway ships with `RedisRateLimiter` using the **token bucket** algorithm; it is a solid baseline before building a custom limiter.

~~~text
Bucket capacity:  6 tokens
Refill:           2 tokens / second
Each request:     1 token

Enough tokens   → allow through, deduct tokens
Lack of tokens  → HTTP 429 (normal when quota store is healthy)
~~~

| Parameter | Example | Meaning |
| --- | ---: | --- |
| `replenishRate` | 2 | Tokens replenished per second |
| `burstCapacity` | 6 | Maximum tokens in the bucket |
| `requestedTokens` | 1 | Token cost of one request |

With these numbers, a full bucket can accept up to six near-simultaneous requests, then needs time to refill. That is **not** a rigid "strictly two requests per calendar second" cap, nor does it mean exactly one second later two more requests are guaranteed if bucket state differed.

Per Spring documentation, rates slower than 1 request/second can be expressed with matching token parameters—such as `replenishRate=1`, `requestedTokens=60`, and `burstCapacity=60` for roughly one request/minute.

### 4.1. `RedisRateLimiter` on Gateway Server WebFlux 5.x

~~~yaml
server:
  port: 8080

spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-quota
              uri: http://localhost:9091
              predicates:
                - Path=/api/orders/**
              filters:
                - name: RequestRateLimiter
                  args:
                    key-resolver: "#{@authenticatedUserKeyResolver}"
                    redis-rate-limiter.replenishRate: 2
                    redis-rate-limiter.burstCapacity: 6
                    redis-rate-limiter.requestedTokens: 1
                - StripPrefix=1
~~~

### 4.2. `RedisRateLimiter` on Gateway Server WebFlux 4.2/4.3

Same `routes` list placed under the older namespace:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders-quota
          uri: http://localhost:9091
          predicates:
            - Path=/api/orders/**
          filters:
            - name: RequestRateLimiter
              args:
                key-resolver: "#{@authenticatedUserKeyResolver}"
                redis-rate-limiter.replenishRate: 2
                redis-rate-limiter.burstCapacity: 6
                redis-rate-limiter.requestedTokens: 1
            - StripPrefix=1
~~~

These examples assume a **`KeyResolver` bean**, reactive Redis client, and route security producing a trustworthy `Principal`. Use the single route namespace matching your version; never duplicate routes under both old and new prefixes.

Reactive Redis dependency per Gateway/Spring Boot version guides (e.g., Boot 3.x):

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis-reactive</artifactId>
</dependency>
~~~

Pick the Gateway starter matching your Boot/Cloud BOM: newer versions use `spring-cloud-starter-gateway-server-webflux`, while many 4.x releases use `spring-cloud-starter-gateway`. Never add the Servlet MVC starter to a project meant to run Server WebFlux.

### 4.3. `KeyResolver` from Authenticated Principal

~~~java
package demo.gateway.quota;

import java.security.Principal;

import org.springframework.cloud.gateway.filter.ratelimit.KeyResolver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class QuotaKeyConfig {

    @Bean
    KeyResolver authenticatedUserKeyResolver() {
        return exchange -> exchange.getPrincipal()
                .map(Principal::getName)
                .filter(name -> !name.isBlank());
    }
}
~~~

In production, **Spring Security** must authenticate the caller before using the principal, and you must specify how tenant IDs and route IDs combine as well as how anonymous callers are handled. Never read `user` from a query parameter, `X-User-Id`, or `X-Api-Key` supplied by the client and treat it as verified identity.

### 4.4. Why You Must Not Assume the Built-In Limiter Fails Closed on Redis Errors

Some versions/implementations of Spring Cloud Gateway's `RedisRateLimiter` handle Lua/Redis execution errors by returning an **allowed** decision (fail-open) with an unknown remaining count. That prevents Redis from becoming a hard availability dependency for traffic, yet **allows quota bypass during Redis failures**.

**Exact behavior depends on the Spring Cloud Gateway version you deploy.** Read the matching implementation, watch logs/metrics, and **run live fault injection**. Never simply wrap:

~~~java
// INSUFFICIENT TO GUARANTEE fail-closed:
redisRateLimiter.isAllowed(routeId, key)
    .onErrorResume(error -> Mono.just(
        new RateLimiter.Response(false, java.util.Map.of())));
~~~

If the inner implementation **already catches the error and emits `allowed=true`**, the outer `onErrorResume` **never sees the error**. To enforce fail-closed reliably, you must control a quota access path where you own the **error semantics**, or have an independently tested health/degraded-mode check.

## 5. Choosing Quota Keys: A Security Decision More Important Than Algorithm Choice

| Key Strategy | Pros | Risks |
| --- | --- | --- |
| Principal ID after JWT/session auth | Ties quota to a real user | Principal names can collide across tenants unless tenant is included |
| Verified OAuth2 client ID | Suits machine-to-machine APIs | One client shared by many end users shares one quota |
| Tenant ID + route group | Caps overall contract quota | One noisy user in a tenant can impact colleagues |
| Client IP **verified by trusted proxy** | Works for unauthenticated requests | NAT/CDNs collapse users onto one IP; XFF is spoofable if edge fails to sanitize |
| Header/username read directly from query | Convenient for labs | Clients rotate values to bypass rate limiting |

Production designs often layer **multiple quota tiers**:

~~~text
System-wide:     protect total Gateway / backend capacity
Per-tenant:      1,000 req/min contract
Per-principal:   50 req/min
Per-route:       POST /payments stricter than GET /products
Trusted IP:      pre-login anti-abuse protection
~~~

Avoid putting raw sensitive data into Redis keys or logs. Use clear namespaces and **HMACs or low-sensitivity internal identifiers** where PII protection applies. Hashing short or predictable IDs with plain unsalted SHA-256 does not protect identities from brute-force reversal.

**Route ID note:** Per-route counters differ from tenant-wide counters. If you rename a route ID in a deployment, quota keys incorporating `routeId` shift and accidentally reset limits. Plan migrations and decide whether quotas are per-route or cross-route.

## 6. Designing Fail-Open, Fail-Closed, and Bounded Degradation

### 6.1. Decision Matrix by API Class

| API / Risk Profile | Policy When Quota Store Fails | Rationale / Conditions |
| --- | --- | --- |
| Public catalog GET, cached with upstream protection | **Controlled fail-open** | Prioritizes availability, backed by ingress/LB global limits |
| Authenticated internal dashboard reads | **Bounded fallback** or fail-closed | Avoids total lockout while curbing multi-replica amplification |
| Payment POST, password reset, OTP issuance | **Fail-closed** or ultra-tight fallback | Abuse causes direct financial/security damage |
| Paid partner API / contractual quota | Usually **fail-closed** or metered fallback | Cannot lose usage accounting; requires contract alignment |
| System health endpoints | Dedicated policy, isolated from user quotas | Health checks must reflect operational state without infinite load |

These are **architectural suggestions**, not Spring Cloud Gateway defaults. Each product must weigh SLAs, resilience, abuse cost, internal networking, and operational ownership.

### 6.2. Fail-Open Must Still Be Bounded

Naive fail-open ("if Redis fails, return `allowed=true`") risks **disabling rate limiting system-wide** right during an attack. When choosing fail-open:

1. Limit degraded-mode duration and fire immediate alerts.
2. Keep edge/WAF limits or independent global connection/request caps active.
3. Restrict sensitive endpoints or lower limits per class.
4. Never treat lost quota visibility as `remaining=unlimited`.
5. Track requests admitted during degraded mode to assess overages post-incident.

### 6.3. Fail-Closed Must Distinguish Store Errors from Quotas

When Redis is **healthy** and requests exceed quota: return **429 Too Many Requests**. When Redis **cannot answer** within the deadline and policy requires rejection: return **503 Service Unavailable** or a consistent infrastructure error code—never pretend it is 429.

Do not convert every exception into `RateLimiter.Response(false)` forgetting that the filter defaults to **429** for `false`. In custom limiters, **propagate typed errors** so the WebFlux error-handling layer returns 503.

### 6.4. Bounded Local Fallback and the Multi-Replica Problem

Suppose Redis is down and each Gateway replica applies a fallback budget of **5 requests/second**:

~~~text
2 Gateway replicas  → can admit 10 requests/second
10 Gateway replicas → can admit 50 requests/second
~~~

That is a **per-replica** cap, no longer a **cluster-wide** quota. Autoscaling during an outage can unintentionally inflate traffic. Bounded fallbacks need:

- Cluster-wide budgets divided by max expected replicas or pre-allocated via leases before outages.
- Short TTLs, global caps, and clean rejoin/reconciliation logic.
- Protections preventing a client from hopping replicas for extra budget.
- Concurrent and scale-out testing, not just single-instance local tests.

## 7. Custom RateLimiter: Atomic Fixed-Window Redis and Fail-Closed

To illustrate an implementation that **directly owns the Redis error path**, we build a `RateLimiter` using Redis Lua: each key gets **3 requests in a 10-second window starting from the first request**. This is a **TTL-based fixed window triggered on first request**, **distinct from the built-in `RedisRateLimiter`'s token bucket**.

The pedagogical advantage is that a single Redis script increments the counter and sets the TTL **atomically**; all Gateway replicas sharing Redis share one counter. The drawback is that bursts straddling two window boundaries can exceed the limit within a rolling 10-second span. If your problem requires an exact sliding window, weighted token buckets, or cost-based quotas, pick the matching algorithm.

### 7.1. Java Implementation for Gateway WebFlux

Create `AtomicRedisWindowLimiter.java` in the lab Gateway project. The code targets Spring Cloud Gateway WebFlux and reactive Spring Data Redis on Java 17+:

~~~java
package demo.gateway.quota;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;

import org.springframework.cloud.gateway.filter.ratelimit.RateLimiter;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

public final class AtomicRedisWindowLimiter
        implements RateLimiter<AtomicRedisWindowLimiter.Config> {

    // Fixed config for lab; never read quota limits from requests.
    public static final class Config {
    }

    private static final long LIMIT = 3;
    private static final Duration WINDOW = Duration.ofSeconds(10);
    private static final Duration STORE_DEADLINE =
            Duration.ofMillis(300);

    private final ReactiveStringRedisTemplate redis;
    private final DefaultRedisScript<Long> script;

    public AtomicRedisWindowLimiter(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
        this.script = new DefaultRedisScript<>();
        this.script.setResultType(Long.class);
        this.script.setScriptText(
                "local n = redis.call('INCR', KEYS[1]); "
                + "if n == 1 then "
                + "  redis.call('PEXPIRE', KEYS[1], ARGV[1]); "
                + "end; "
                + "return n;");
    }

    @Override
    public Class<Config> getConfigClass() {
        return Config.class;
    }

    @Override
    public Config newConfig() {
        return new Config();
    }

    @Override
    public Map<String, Config> getConfig() {
        // Demo does not define per-route custom configs.
        return Map.of();
    }

    @Override
    public Mono<RateLimiter.Response> isAllowed(
            String routeId, String id) {

        // routeId is provided by Gateway; id is resolved by KeyResolver.
        String key = "gw:quota:demo:" + sha256(routeId + "|" + id);

        return redis.execute(
                    script,
                    List.of(key),
                    List.of(Long.toString(WINDOW.toMillis())))
                .next()
                .switchIfEmpty(Mono.error(
                        new IllegalStateException("Redis script empty")))
                .map(count -> {
                    long remaining = Math.max(0, LIMIT - count);
                    return new RateLimiter.Response(
                            count <= LIMIT,
                            Map.of("X-RateLimit-Remaining",
                                    Long.toString(remaining)));
                })
                .timeout(STORE_DEADLINE)
                // Important: store failures do NOT turn into 429.
                .onErrorMap(error -> new ResponseStatusException(
                        HttpStatus.SERVICE_UNAVAILABLE,
                        "Quota store temporarily unavailable",
                        error));
    }

    private static String sha256(String value) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException(error);
        }
    }
}
~~~

Key highlights of this class:

- `RateLimiter.Response(true, ...)` admits requests **within quota**, `false` when **quota is exhausted**.
- The Lua script combines `INCR` and `PEXPIRE` so all replicas share one Redis counter; `PEXPIRE` runs only when the key is freshly created.
- If Redis errors, emits empty, or exceeds the deadline, `onErrorMap` throws `ResponseStatusException(503)` rather than returning `allowed=false`. That yields **unambiguous fail-closed (not 429)** through standard WebFlux error handling.
- `getConfigClass`, `newConfig`, and `getConfig` satisfy the `RateLimiter` contract; this demo uses static constants rather than per-route/per-tenant YAML configs.
- SHA-256 hashing avoids exposing raw caller names in Redis keys, though it **does not guarantee anonymity** for guessable IDs. Production should consider keyed HMACs and clear key/namespace rules.

**Academic scope:** This is a conceptual skeleton, not built or tested inside this repo; APIs depend on your Gateway/Spring Data Redis version. At high scale, benchmark, test Redis Cluster hash-slots/TTLs, bound key cardinality, verify script semantics in your version, and align HTTP client timeouts. Do not drop this example straight into production as a finished library.

### 7.2. Declaring Beans and `KeyResolver` for the Lab Environment

To run `curl` without standing up an IdP/JWT server, the snippet below reads a **client-sent header** `X-Lab-Key`. This is **intentionally insecure** and strictly for a localhost lab; production must swap in a resolver backed by an **authenticated** principal or API key.

~~~java
package demo.gateway.quota;

import org.springframework.cloud.gateway.filter.ratelimit.KeyResolver;
import org.springframework.cloud.gateway.filter.ratelimit.RateLimiter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import reactor.core.publisher.Mono;

@Configuration
public class LabQuotaConfiguration {

    @Bean("atomicQuotaLimiter")
    RateLimiter<AtomicRedisWindowLimiter.Config> atomicQuotaLimiter(
            ReactiveStringRedisTemplate redis) {
        return new AtomicRedisWindowLimiter(redis);
    }

    @Bean("labKeyResolver")
    KeyResolver labKeyResolver() {
        return exchange -> Mono.justOrEmpty(
                        exchange.getRequest()
                                .getHeaders().getFirst("X-Lab-Key"))
                .filter(key -> !key.isBlank())
                .filter(key -> key.matches("[A-Za-z0-9_-]{1,64}"));
    }
}
~~~

If `X-Lab-Key` is missing or malformed, the resolver emits no key; `RequestRateLimiter`'s default config **rejects empty keys**. Never collapse all unidentified requests into `"anonymous"` and assume each user is accurately isolated.

### 7.3. Wiring the Custom `RateLimiter` into a WebFlux 5.x Route

~~~yaml
server:
  port: 8080

spring:
  data:
    redis:
      host: localhost
      port: 6379
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-quota-lab
              uri: http://localhost:9091
              predicates:
                - Path=/api/orders/**
                - Method=GET,POST
              filters:
                - name: RequestRateLimiter
                  args:
                    rate-limiter: "#{@atomicQuotaLimiter}"
                    key-resolver: "#{@labKeyResolver}"
                - StripPrefix=1
~~~

For WebFlux **4.2/4.3**, keep `routes` identical and move it under `spring.cloud.gateway.routes`; no Java bean reference changes are needed:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders-quota-lab
          uri: http://localhost:9091
          predicates:
            - Path=/api/orders/**
            - Method=GET,POST
          filters:
            - name: RequestRateLimiter
              args:
                rate-limiter: "#{@atomicQuotaLimiter}"
                key-resolver: "#{@labKeyResolver}"
            - StripPrefix=1
~~~

`RequestRateLimiter` does **not** read `redis-rate-limiter.replenishRate` or `burstCapacity` when referencing this custom bean: `AtomicRedisWindowLimiter` uses its own Java fixed-window constants. Never declare both assuming they combine.

### 7.4. What Changes for Intentional Fail-Open?

In section 7.1's custom limiter, you can swap the error branch with:

~~~java
// Illustrates fail-open policy ONLY; DO NOT use by default on sensitive APIs.
.onErrorResume(error -> {
    // Increment limiter_store_error metric and trigger ops alert.
    return Mono.just(new RateLimiter.Response(
            true, Map.of("X-RateLimit-Mode", "degraded")));
});
~~~

When failing open, keep edge limits and degraded-mode monitoring active. **Never leak raw exceptions or Redis hostnames in responses.** If a bounded fallback is needed, build a local counter with max TTL/size and per-replica budgets accounting for autoscaling—never just slap `.onErrorResume(... allowed=true)`.

## 8. Response Headers and Statuses Must Be Transparent

| Situation | Suggested Status | What It Communicates |
| --- | --- | --- |
| Quota available, backend succeeds | Typically backend **2xx** | Request was forwarded |
| Quota genuinely exhausted | **429 Too Many Requests** | Client should slow down or wait per policy |
| Missing key when policy requires a key | Per empty-key config (usually **403**) | Insufficient identity to resolve quota |
| Redis misses deadline and policy is fail-closed | **503 Service Unavailable** | Quota infrastructure temporarily unavailable |
| Redis errors under fail-open | Status returned by backend | Request passed through in degraded mode |
| Backend unavailable after quota passed | Other **5xx**/503 per error | Not quota exceeded |

Helpful headers:

- `X-RateLimit-Remaining`: remaining quota units **per the active algorithm**, not an absolute access guarantee. In custom code, emit only after a successful Redis decision.
- `Retry-After`: recommended wait time, usually in **seconds** or HTTP-date; compute from **actual remaining window/TTL**, never hardcode blindly.
- `RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset`: use only when matching the exact standard semantics supported by your version to avoid misleading clients.
- `X-RateLimit-Mode: degraded`: handy in internal tests; consider **hiding defensive-state internals** from external clients in production.

**Never reflexively return `Retry-After: 10` on every limiter error.** For Redis-driven fixed windows, read remaining TTL to be accurate; during a Redis outage, you do not know when the store will recover. Clients should apply exponential backoff with jitter per their own retry policies instead of hammering the system.

### 8.1. Distinguishing Gateway 429s from Backend 429s

A downstream service can also emit 429. Trace route IDs, filter decision sources, and internal response headers to separate them:

~~~text
429 Gateway quota → backend NEVER receives the request
429 Backend quota → Gateway forwarded the request; backend rejected it
~~~

When retries are enabled, avoid infinite retry loops on 429 quota rejections. Also bound retries on 503s caused by Redis errors, since Redis itself is already overloaded or unavailable.

## 9. Hands-On: Verifying the Custom Limiter with Two Processes

### 9.1. Prepare a Minimal Backend

Create a standalone Spring Boot WebFlux backend on port `9091` with `spring-boot-starter-webflux`:

~~~yaml
# Echo backend application.yml
server:
  port: 9091
~~~

~~~java
package demo.orders;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}

@RestController
class OrdersController {
    @GetMapping("/orders/{id}")
    Map<String, String> read(@PathVariable String id) {
        return Map.of("id", id, "servedBy", "orders-backend");
    }
}
~~~

The backend needs no awareness of quotas. When Gateway's `RequestRateLimiter` rejects, requests **never reach** this endpoint—a key signal when analyzing logs.

### 9.2. Start Redis for the Lab

With Docker and a Redis image:

~~~bash
docker run --rm --name quota-redis-lab \
  -p 127.0.0.1:6379:6379 redis:7
~~~

Without Docker, run local Redis or a managed test Redis. **Never expose Redis to the internet** or share an unsecured production Redis without ACLs/TLS. When the Gateway runs inside its own Docker container, `localhost` inside that container does not point to the Redis host; use proper DNS/hostnames.

Start the backend and Gateway in two terminals from their respective Maven project directories:

~~~bash
./mvnw spring-boot:run
~~~

Examples here assume dependencies, Java sources, and configs match your release; this article **does not claim to have executed a live build or test run**.

### 9.3. Send Four Consecutive Requests with the Same Lab Key

Within 10 seconds of the first request, run:

~~~bash
for i in 1 2 3 4; do
  echo "Call $i"
  curl -sS -o /dev/null -D - \
    "http://localhost:8080/api/orders/42" \
    -H "X-Lab-Key: demo-tenant" |
    grep -i -E '^(HTTP/|X-RateLimit-Remaining:)'
done
~~~

**Expected outcome if all four run inside one TTL window, Redis is healthy, and no other traffic hits that key:**

| Request | Redis Counter After Request | Outcome |
| ---: | ---: | --- |
| 1 | 1 | Allowed; backend typically returns 200 |
| 2 | 2 | Allowed |
| 3 | 3 | Allowed |
| 4 | 4 | **429 Too Many Requests** |

Once the window TTL expires, the next call passes again. With another key like `X-Lab-Key: demo-other`, quota is tracked independently in the lab. **Swapping keys arbitrarily to grab fresh quota is a vulnerability in real products**: that is why client-supplied headers are strictly for local testing.

Try calling without a key:

~~~bash
curl -i "http://localhost:8080/api/orders/42"
~~~

Under default `deny-empty-key`, the Gateway rejects before calling the backend. Status is typically **403**, distinct from 429 quota exhaustion. Check your version's `deny-empty-key` / `empty-key-status-code` properties when changing policies.

### 9.4. Test Redis Store Failure: Fault Injection

Strictly in the lab environment, stop the Redis container:

~~~bash
docker stop quota-redis-lab
~~~

Then call the same endpoint again:

~~~bash
curl -i "http://localhost:8080/api/orders/42" \
  -H "X-Lab-Key: demo-tenant"
~~~

With section 7.1's custom limiter, when the Redis call fails or times out, `onErrorMap` emits **503 Service Unavailable** through standard WebFlux error handling. The request is **not** forwarded to the backend. If you see a different code, check custom exception handlers, filter ordering, and actual Gateway configuration.

When using the **built-in `RedisRateLimiter`** instead of the custom limiter, **never assume** identical behavior: some versions fail open as warned in section 4.4. Record actual behavior and inspect your exact version's source.

### 9.5. Extend to Two Gateway Replicas

Run Gateways A and B on different ports pointing to **the same Redis and identical limiter configs**. Alternate calls across A and B with **the same quota key** within one window. Because the custom Redis script holds cluster-wide state, total admitted requests **must not exceed `LIMIT=3`** for that key/route within the window (excluding calls from another window).

Note that each HTTP request receives its `routeId`. If A and B have **different route IDs**, hashing `routeId + "|" + id` creates **two separate quota keys** and invalidates the test. Ensure route IDs, namespaces, and policies match before claiming cluster-wide quotas.

## 10. Testing Failure Modes Beyond Redis Down

Shutting Redis down completely is not the only failure mode. A solid policy must test:

| Failure Scenario | What to Confirm |
| --- | --- |
| Redis stalls slowly without closing connections | A **deadline** prevents hanging requests indefinitely |
| Wrong Redis DNS/TLS/ACL/authentication | Store errors are classified properly, not misreported as 429 |
| Redis script missing or fails to execute | Custom limiter never silently permits outside policy |
| Redis Cluster switches primary/slots | Keys partition and retry safely without double-counting decisions |
| Redis disconnects for 15 seconds then recovers | Degraded mode clears and metrics/alerts normalize |
| Redis stays up while p99 latency spikes | Quota checks do not become a performance bottleneck |
| Gateway autoscales during an outage | Local fallback does not multiply cluster-wide limits with replica count |
| One user sends thousands of random keys | Redis key cardinality is bounded to prevent memory exhaustion |
| Two concurrent requests share one key | Atomic Lua/transactions yield accurate counts with zero lost updates |
| Policy rolls from v1 to v2 | Changing route ID, namespace, window, or TTL does not unintentionally reset quotas |

For observability, emit metrics such as:

- `rate_limit_decision_total{route,decision="allow|deny"}`
- `rate_limit_store_error_total{route,reason="timeout|connection|script"}`
- `rate_limit_degraded_total{route,policy="open|closed|local"}`
- `rate_limit_store_latency_seconds` histogram
- `rate_limit_denied_total{route}` and 429/503 status counts

Labels must stay **low-cardinality**. Never put principal IDs, API keys, raw tokens, or personal IPs into metric labels; use access-controlled logs if tracing is needed. Also track the **backend requests / ingress requests** ratio to detect silent quota bypasses.

## 11. Operational and Security Pitfalls

### 11.1. IP from `X-Forwarded-For` Is Not Guaranteed to Be the Real Client

A client can inject `X-Forwarded-For` itself. If the Gateway takes the leftmost element as the quota key without ingress/WAF **sanitizing headers and blocking bypass paths**, attackers spoof IPs to evade limits. Verify proxy trust boundaries before keying by IP; prefer authenticated principals/client IDs whenever feasible.

### 11.2. Enforcing Limits on a Specific Route While Missing Fallback Routes

If `/api/payments/**` has a strict limiter while a catch-all `/api/**` route lacks a limiter or wins route priority, callers can slip past the policy. Audit route order, predicates, and equivalent paths/methods.

### 11.3. CORS Preflights and Health Checks

Browsers send `OPTIONS` before JSON POSTs. If quotas count preflights like mutations, or Security blocks `OPTIONS`, frontends hit confusing CORS errors. Design preflight policies deliberately without "opening all OPTIONS indiscriminately"; health probes need separate policies too.

### 11.4. Retries Do Not Mean Extra Free Quota

A client request may be retried by the Gateway or backend. If the limiter runs **once** before the retry filter while the backend sees multiple attempts, client-level quotas may fail to cap total backend calls. Conversely, if the limiter re-runs on every attempt, one client request gets charged multiple times. Define **whether quotas count HTTP client requests or backend attempts** and verify filter order and retry metrics.

### 11.5. Overly Broad Fail-Closed Can Cause Cascading Outages

If every API—including health/readiness probes—fails closed when Redis errors, a quota-store hiccup can mark the Gateway unhealthy and cause cluster-wide traffic churn. Separate readiness/liveness, fallbacks, and admin policies. Even so, **never** fail open on payment or security-sensitive APIs just for convenience.

### 11.6. Hardening the Quota Store

Redis needs private networking, ACLs, TLS where appropriate, sensible timeouts, and HA/failover. Manage keys/TTLs/namespaces to prevent memory exhaustion, and use atomic scripts for distributed counters. Never store raw Bearer tokens or secrets in Redis quota keys; never accept arbitrary query parameters as production identity.

### 11.7. Bucket4j / Local Cache Does Not Equal Cluster-Wide Quotas

Newer Gateway WebFlux versions also integrate **Bucket4j** and persistence adapters. Bucket4j with **local Caffeine** suits labs or per-replica caps, not shared buckets across multiple Gateway processes. Only with **distributed persistence** and verified configs should quotas be considered cluster-wide.

## 12. Pre-Production Checklist

- [ ] Defined quotas per **tenant/user/client/route** and scope (**per-replica vs. global**).
- [ ] `KeyResolver` relies on authenticated identity or trusted-proxy IP; missing-key behavior is explicit.
- [ ] Selected token bucket, fixed window, or sliding window matching allowed burst semantics.
- [ ] Bounded TTLs, key counts, and Redis memory; prevented caller-driven high cardinality.
- [ ] If using the built-in limiter, verified **actual Redis error behavior in your exact version** rather than guessing fail-closed.
- [ ] Defined **fail-open, fail-closed, or bounded degrade** policies per API sensitivity.
- [ ] Fail-closed on store failure returns an infrastructure status (typically 503), never disguised as quota-exceeded 429.
- [ ] Configured quota-store deadlines and bounded retries so requests never hang.
- [ ] If using local fallback, sized budgets against **maximum Gateway replica count**.
- [ ] Redis keys, namespaces, route IDs, and policies are identical across all replicas.
- [ ] Tested concurrent requests across multiple Gateway replicas and route/order changes.
- [ ] Tested Redis down, slow Redis, failover, recovery, and high key cardinality.
- [ ] CORS preflights, health checks, and authentication follow explicit policies.
- [ ] Rate limiting does not replace authentication/authorization, WAF, or capacity protection.
- [ ] Per-route retries/circuit breakers do not unintentionally multiply backend attempts past intended quotas.
- [ ] Metrics/traces distinguish allow, 429, empty key, and store outage without containing secrets/PII.
- [ ] Operational runbook exists: who can toggle fail-open, max duration, rollback, and alerting.

## 13. Self-Check Questions

**1. Why do three Gateway replicas each keeping an in-RAM 10 req/s counter fail to enforce a cluster-wide 10 req/s quota?**

Because their states are independent; the same key can receive up to three separate budgets. A shared store, quota leasing, or controlled budget partitioning is required.

**2. Redis times out and the code returns `RateLimiter.Response(false)`. Why can that be wrong?**

`false` normally makes `RequestRateLimiter` return **429**, even though you do not know whether the client exceeded quota. Under fail-closed, store failures should map to **503** or an appropriate infrastructure status.

**3. Does wrapping `redisRateLimiter.isAllowed(...).onErrorResume(...)` guarantee catching every Redis error?**

No, if the `RedisRateLimiter` implementation **already catches the error internally and returns `allowed=true`**. Inspect the source/version, run fault injection, or build a quota path whose error semantics you control directly.

**4. Why is `X-Lab-Key` in the example appropriate only for localhost?**

Because clients can swap headers to obtain fresh quotas. Production requires an authenticated principal/API key or a client IP verified through a trusted proxy.

**5. During a Redis error, can a 5 req/s fallback on each Gateway count as a global 5 req/s limit?**

No. With four replicas, total throughput can reach 20 req/s. Either allocate a distributed cluster budget or explicitly accept the bounded overshoot.

## 14. References

1. [Spring Cloud Gateway Server WebFlux 5.x — RequestRateLimiter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/requestratelimiter-factory.html): `KeyResolver`, Redis token bucket, custom `RateLimiter`, Bucket4j, and YAML.
2. [Spring Cloud Gateway Server WebFlux 4.3 — RequestRateLimiter](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/gatewayfilter-factories/requestratelimiter-factory.html): route and filter syntax in the 4.3 line.
3. [Spring Cloud Gateway 4.2 — RequestRateLimiter](https://docs.spring.io/spring-cloud-gateway/reference/4.2/spring-cloud-gateway/gatewayfilter-factories/requestratelimiter-factory.html): 4.2 version comparison.
4. [Spring Cloud Gateway — Configuration Properties](https://docs.spring.io/spring-cloud-gateway/reference/5.1/configprops.html): Redis limiter, route, and WebFlux filter properties.
5. [Spring Data Redis — Reactive Redis Support](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html): starting point in Spring Data Redis docs for reactive access and Redis configuration.
6. [RFC 6585 — 429 Too Many Requests](https://www.rfc-editor.org/rfc/rfc6585#section-4): semantics of 429 and `Retry-After`.

**Key takeaway:** Spring Cloud Gateway's `RequestRateLimiter` needs a **trustworthy `KeyResolver`**, an **accurate `RateLimiter`**, and a **quota store suited to multi-replica scope**. **Genuine quota exhaustion** differs from **inability to query quota**. When Redis fails, fail-open, fail-closed, or degraded budgets are **intentional security/operational decisions** that must be explicitly coded, observed, and verified with fault injection—never inferred from default status codes or an `onErrorResume` placed at the wrong layer.
