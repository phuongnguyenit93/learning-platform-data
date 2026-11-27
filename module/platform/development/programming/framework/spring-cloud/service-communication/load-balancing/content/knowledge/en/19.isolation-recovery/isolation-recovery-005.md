# Integrating Spring Cloud Circuit Breaker at the HTTP Client Boundary

In a microservices architecture, `order-service` commonly calls `inventory-service` via RestClient, WebClient, or OpenFeign using the service ID `inventory-service`. Spring Cloud LoadBalancer selects a `ServiceInstance` based on discovery, health checks, and routing algorithms. However, if all of inventory slows down, returns continuous 5xx errors, or its underlying database is overloaded, **continuing to send every request** to inventory can exhaust the caller's threads, connection pools, and timeout budgets, triggering cascading failures.

**Spring Cloud Circuit Breaker** provides an abstraction API to isolate faults at the **dependency call boundary**. It observes outcomes across multiple calls to an operation group; when the failure rate or slow-call rate gets high enough, the breaker can temporarily stop permitting calls, fail fast, or switch to a controlled fallback. After a wait period, a limited number of probe requests are allowed through to evaluate recovery.

This lesson in the **Isolation and Recovery** chapter covers the mechanics and how to attach Circuit Breaker directly around HTTP clients; examples for RestClient, WebClient, and OpenFeign; Resilience4j configuration; fallbacks that preserve data semantics; retry/timeout coordination; observability; and testing.

## 1. Why Is Circuit Breaker Needed Even When Using LoadBalancer?

~~~mermaid
flowchart LR
    U["User"] --> O["order-service"]
    O --> CB["Circuit Breaker: inventoryRead"]
    CB --> LB["Spring Cloud LoadBalancer"]
    LB --> A["inventory replica A"]
    LB --> B["inventory replica B"]
    LB --> C["inventory replica C"]
~~~

Suppose `inventory-service` has three instances A/B/C, yet all are slow due to a shared database. Even if LoadBalancer picks another instance, the outcome may still be a timeout. If the caller increases retry counts, even more requests hit the database. A circuit breaker can detect repeated failed/slow calls and temporarily **block new calls** to curb cascading pressure.

Keep responsibility boundaries distinct:

| Component | Role | What it does not guarantee automatically |
|---|---|---|
| Discovery | Supplies the list of known instances | Every instance's business APIs are healthy |
| `HealthCheckServiceInstanceListSupplier` | Probes/filters instances via health endpoints | `/stock` responds fast and accurately |
| Spring Cloud LoadBalancer | Selects one `ServiceInstance` for a call | Deciding to stop calling an entire failing dependency |
| Spring Cloud Circuit Breaker | Permits/rejects calls based on outcome statistics | Selecting a new replica or rolling back transactions |
| Retry | Retries transient errors per policy | Limiting load if repeated excessively |
| HTTP timeout/TimeLimiter | Limits wait duration | Detecting error frequency to transition OPEN |
| Bulkhead | Caps concurrent calls | Selecting instances or routing |

For instance, if one replica dies, health checks or discovery can drop it from the list while remaining replicas keep serving. **Do not use one service-wide breaker as a substitute for filtering out a single dead replica**, because a shared breaker can temporarily block healthy replicas too.

## 2. Three States: CLOSED, OPEN, HALF_OPEN

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: Failure rate / slow-call rate exceeds threshold
    OPEN --> HALF_OPEN: Wait duration elapsed and probe call arrives
    HALF_OPEN --> CLOSED: Probe calls meet criteria
    HALF_OPEN --> OPEN: Probe calls still fail or are too slow
~~~

- **CLOSED**: requests are allowed through to the HTTP client; the breaker records outcomes in a sliding window.
- **OPEN**: new requests fail fast, typically with `CallNotPermittedException` (Resilience4j); no HTTP attempt goes to the backend for blocked requests.
- **HALF_OPEN**: the breaker allows a bounded number of probe requests to decide whether to return to CLOSED or OPEN.

A Circuit Breaker does not necessarily open after the first error. For example:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventoryRead:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
~~~

If fewer than five calls have been recorded, `minimumNumberOfCalls` is not yet reached to apply the failure-rate threshold. Once enough samples exist, three failures out of five calls equals a 60% rate and can open the breaker if no exclusion rule applies:

\[
\mathrm{failureRate}=\frac{\mathrm{failedCalls}}{\mathrm{recordedCalls}}\times100\%.
\]

Note that the call count seen by the breaker **does not always equal HTTP attempt count**, as it depends on where retry sits relative to the breaker.

## 3. Choosing the Protection Boundary: Service or Operation?

Place the breaker in the adapter/gateway responsible for calling a dependency, rather than embedding breaker logic inside controllers or every DTO mapper:

~~~text
OrderController
  -> OrderService (business workflow)
      -> InventoryGateway (dependency boundary)
          -> CircuitBreaker(inventoryRead)
              -> LoadBalanced HTTP client
                  -> Selected ServiceInstance
~~~

Breaker IDs must be stable and meaningful. Common options:

| Scope | Example ID | When appropriate? | Risk |
|---|---|---|---|
| One service ID | `inventory-service` | Multiple operations share failure profile | One broken API blocks every API in the service |
| One operation | `inventoryRead`, `inventoryReserve` | Reads/writes have different SLOs and fallbacks | More breakers to monitor |
| One instance | Per replica | Only with genuine outlier isolation mechanisms | High cardinality, hard lifecycle management |
| One request | Random ID each time | **Inappropriate** | Loses statistical history, breaker effectively useless |

The usual recommendation is starting **per operation or operation group sharing the same error handling**. For instance, `inventoryRead` and `inventoryReserve` may need different policies: reading stock for display can use cache, whereas reserving stock must fail safe without guessing outcomes.

Wrapping an entire checkout flow covering inventory, pricing, and payment in a single breaker lets a pricing outage block healthy inventory steps too. The goal is isolating **dependencies**, not eroding independence between steps.

## 4. Spring Cloud Dependencies and Abstractions

Spring Cloud Circuit Breaker provides `CircuitBreakerFactory` for blocking code and `ReactiveCircuitBreakerFactory` for Reactor. Resilience4j is a common implementation; adding the matching starter lets Spring auto-create the factory bean from configuration.

**For RestClient/OpenFeign or blocking calls:**

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
</dependency>
~~~

**For WebClient/reactive:**

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
</dependency>
~~~

To select instances by service ID, add `spring-cloud-starter-loadbalancer` (or an appropriate transitive dependency). HTTP client choices:

- `spring-boot-starter-web` for Spring MVC apps with RestClient;
- `spring-boot-starter-webflux` for WebClient;
- `spring-cloud-starter-openfeign` for Feign declarative clients.

These are **stack variants**—projects do not need both circuit-breaker starters at once. Use compatible Spring Boot BOM and Spring Cloud BOM versions and cross-check your release train documentation.

## 5. Load-Balanced RestClient Wrapped with CircuitBreaker

Example of `order-service` calling inventory via a logical REST URL.

**Registering RestClient:**

~~~java
package com.example.order.http;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class InventoryHttpConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean("inventoryRestClient")
    RestClient inventoryRestClient(
            @LoadBalanced RestClient.Builder builder) {

        return builder.clone()
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

`@LoadBalanced` attaches Spring Cloud LoadBalancer to the builder so callers use a service ID rather than fixed IP/port addresses. Circuit Breaker is not in this builder yet; we **wrap the call at the adapter** to get a dedicated breaker ID and business-aware fallback.

**Gateway protecting an inventory read operation:**

~~~java
package com.example.order.inventory;

import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import java.util.concurrent.TimeoutException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

@Service
public class InventoryGateway {

    private final RestClient restClient;
    private final CircuitBreaker breaker;

    public InventoryGateway(
            @Qualifier("inventoryRestClient") RestClient restClient,
            CircuitBreakerFactory<?, ?> factory) {

        this.restClient = restClient;
        this.breaker = factory.create("inventoryRead");
    }

    public StockView getStock(String sku) {
        return breaker.run(
                () -> {
                    InventoryQuantity stock = restClient.get()
                            .uri("/stock/{sku}", sku)
                            .retrieve()
                            .body(InventoryQuantity.class);

                    if (stock == null) {
                        throw new IllegalStateException(
                                "Missing inventory response body"
                        );
                    }

                    return new StockView(
                            stock.sku(), stock.available(), false
                    );
                },
                cause -> fallback(sku, cause)
        );
    }

    private StockView fallback(String sku, Throwable cause) {
        if (cause instanceof HttpClientErrorException e) {
            // Do not convert 400/401/403/404 into stock UNKNOWN.
            throw e;
        }

        if (cause instanceof CallNotPermittedException
                || cause instanceof ResourceAccessException
                || cause instanceof HttpServerErrorException
                || cause instanceof TimeoutException) {
            return new StockView(sku, null, true);
        }

        if (cause instanceof RuntimeException e) {
            throw e;
        }

        throw new IllegalStateException(
                "Unexpected inventory failure", cause
        );
    }

    public record InventoryQuantity(String sku, int available) {}
    public record StockView(
            String sku,
            Integer available,
            boolean degraded
    ) {}
}
~~~

**Key points:**

- `CircuitBreakerFactory<?, ?>` is an abstraction keeping the adapter from coupling completely to Resilience4j APIs.
- `factory.create("inventoryRead")` fetches a breaker with a consistent ID and configuration; never generate random IDs per request.
- `breaker.run(supplier, fallback)` executes the HTTP call when the breaker permits; on rejection or failure, the fallback runs with the cause.
- RestClient still uses LoadBalancer to select a replica on **permitted** calls.
- `available = null, degraded = true` means **inventory count is unknown**. Never treat UNKNOWN as "in stock" to place orders.
- Rethrowing HTTP 4xx from the fallback in the example **does not undo what the breaker already recorded**. Configure `ignoreExceptions`/`recordException` so business 4xx responses do not open the breaker.
- Do not disguise programming bugs or JSON contract mismatches as valid-looking results.

A read-only fallback can return cached data with `staleAt`/`source` if business rules permit. Conversely, stock-reservation or payment APIs must never invent successful results when the backend fails.

## 6. Classifying Technical vs. Business Errors

| Outcome from inventory | Usually counted as breaker failure? | Appropriate handling |
|---|---|---|
| Connect timeout, connection refused | Yes | Bounded fallback or fail fast |
| HTTP 500/502/503/504 | Yes | Evaluate outage, do not raise retries endlessly |
| HTTP 404 SKU does not exist | Usually no | Return genuine not found |
| HTTP 400 invalid input | Usually no | Fix/validate request |
| HTTP 401/403 | Usually not treated as outage | Handle security, do not mask with fallback |
| HTTP 429 | Depends on overload/rate-limit policy | Honor Retry-After, avoid retry storms |
| JSON contract mismatch | Depends on classification | Report contract error instead of fake data |
| `CallNotPermittedException` when OPEN | No new HTTP attempt sent | Fallback or fail fast |

With Resilience4j, by default many non-ignored exceptions are recorded as failures. If an API commonly returns 404 for a valid business condition, adjust exception classification accordingly. Conversely, if a backend always returns HTTP 200 with `success: false` in the body, the breaker **does not automatically know** it failed; the adapter must decide when to throw a technically meaningful exception or apply custom policy.

## 7. Configuring Resilience4j by Breaker ID

Illustrative `application.yml`:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventoryRead:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 600ms
        slowCallRateThreshold: 80
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
        registerHealthIndicator: true

  timelimiter:
    instances:
      inventoryRead:
        timeoutDuration: 900ms
        cancelRunningFuture: true
~~~

The name `inventoryRead` must match `factory.create("inventoryRead")`. These values are examples for experimentation, not universal production defaults.

| Property | Meaning |
|---|---|
| `slidingWindowType` | Call-count (`COUNT_BASED`) or time-based (`TIME_BASED`) window |
| `slidingWindowSize` | Statistical window size |
| `minimumNumberOfCalls` | Minimum calls before OPEN thresholds apply |
| `failureRateThreshold` | Failed-call percentage threshold |
| `slowCallDurationThreshold` | Threshold classifying a call as slow |
| `slowCallRateThreshold` | Slow-call percentage threshold |
| `waitDurationInOpenState` | Wait duration before recovery probes can run |
| `permittedNumberOfCallsInHalfOpenState` | Maximum probe attempts in HALF_OPEN |
| `registerHealthIndicator` | Integrates health indicator when Actuator and related config are present |
| `timelimiter.instances.<id>` | Timeout managed by Resilience4j TimeLimiter, not transport read timeout |

Spring Cloud CircuitBreaker Resilience4j allows global default, group, and per-ID configuration; official docs state **properties take precedence over Java `Customizer`**, and per-ID settings take precedence over group/default settings for corresponding fields.

### Do Not Count Valid 404s as Outages

If a GET for a non-existent SKU turns into an HTTP 404 exception, Resilience4j may count it as a failure by default. If that is a normal business result, configure `ignoreExceptions` or `recordException` with the exact runtime exception class.

Example with Spring RestClient and HTTP 404:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventoryRead:
        ignoreExceptions:
          - org.springframework.web.client.HttpClientErrorException$NotFound
~~~

Check logs/metrics to confirm the exact exception class: RestClient may throw `HttpClientErrorException`, WebClient throws `WebClientResponseException`, and Feign throws `FeignException`. Avoid overly broad ignore lists that hide real outages.

### TimeLimiter Differs from HTTP Transport Timeouts

Spring Cloud CircuitBreaker Resilience4j docs note that TimeLimiter is enabled by default unless disabled via policy. You can disable it for a specific breaker ID when bounding via transport timeouts and another deadline:

~~~yaml
spring:
  cloud:
    circuitbreaker:
      resilience4j:
        disable-time-limiter-map:
          inventoryRead: true
~~~

Disabling TimeLimiter **does not** disable HTTP client connect/read timeouts. Conversely, `timeoutDuration: 900ms` does not guarantee an executing blocking call or backend transaction stops at 900ms. `cancelRunningFuture` only expresses cancellation intent; check interruption/cancellation behavior of your HTTP transport, thread pool, and context propagation setup.

## 8. Breaker Scope Is Usually Operation, Not Replica

Suppose service ID inventory has three instances A/B/C:

~~~text
A healthy -> request succeeds
B failing -> timeout
C healthy -> request succeeds
A healthy -> request succeeds
B failing -> timeout
...
~~~

If `inventoryRead` is shared across the service ID, failures on B still raise the breaker's failure rate. Once thresholds trip, the breaker can OPEN and block calls that might otherwise have picked healthy A or C.

Therefore:

- Use discovery/health checks/outlier policies to remove a specific broken instance.
- Use per-operation circuit breakers to contain widespread failures from a **dependency** or API class.
- Do not assume a service-ID-level breaker creates separate OPEN/CLOSED state per `ServiceInstance`.
- Once inventory recovers, the breaker needs HALF_OPEN and successful probes; changing the instance list does not necessarily close the breaker immediately.

## 9. WebClient: ReactiveCircuitBreakerFactory Wrapping Mono

With WebClient and Reactor, never call `Mono.block()` on the event loop just to use a blocking breaker. Use `ReactiveCircuitBreakerFactory` with the reactive starter:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
</dependency>
~~~

Load-balanced builder:

~~~java
package com.example.order.config;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class InventoryWebClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }

    @Bean("inventoryWebClient")
    WebClient inventoryWebClient(
            @LoadBalanced WebClient.Builder builder) {

        return builder.clone()
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

Using the reactive breaker in the HTTP adapter:

~~~java
package com.example.order.inventory;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Mono;

@Service
public class ReactiveInventoryGateway {

    private final WebClient client;
    private final ReactiveCircuitBreaker breaker;

    public ReactiveInventoryGateway(
            @Qualifier("inventoryWebClient") WebClient client,
            ReactiveCircuitBreakerFactory<?, ?> factory) {

        this.client = client;
        this.breaker = factory.create("inventoryReadReactive");
    }

    public Mono<StockView> getStock(String sku) {
        Mono<StockView> remote = client.get()
                .uri("/stock/{sku}", sku)
                .retrieve()
                .bodyToMono(InventoryQuantity.class)
                .map(response -> new StockView(
                        response.sku(),
                        response.available(),
                        false
                ));

        return breaker.run(remote, cause -> {
            if (cause instanceof WebClientResponseException e
                    && e.getStatusCode().is4xxClientError()) {
                return Mono.error(cause);
            }

            return Mono.just(new StockView(sku, null, true));
        });
    }

    public record InventoryQuantity(String sku, int available) {}
    public record StockView(
            String sku,
            Integer available,
            boolean degraded
    ) {}
}
~~~

`ReactiveCircuitBreakerFactory.create` uses an operation-based ID; `run` protects the `Mono` and takes a reactive fallback. On permitted calls, WebClient continues using Spring Cloud LoadBalancer to select an instance.

Notes:

- The fallback returns UNKNOWN via `available = null`, without fabricating data.
- Returning `Mono.error(cause)` for 4xx **does not** replace the breaker's exception classification config.
- `retrieve()` converts 4xx/5xx responses into exceptions by default during response handling; `exchangeToMono()` has different semantics.
- Fallbacks must never block the event loop or re-call the failing inventory service.
- Use Reactor Context/observability rather than relying solely on ThreadLocal MDC.
- Bound the overall pipeline with dedicated deadlines/timeouts; timing out or canceling a publisher does not guarantee backend rollback.

## 10. OpenFeign: Built-In Integration with Spring Cloud CircuitBreaker

OpenFeign supports wrapping Feign methods with Spring Cloud CircuitBreaker. When a compatible circuit-breaker starter is on the classpath, enable:

~~~yaml
spring:
  cloud:
    openfeign:
      circuitbreaker:
        enabled: true
~~~

According to Spring Cloud OpenFeign documentation, `spring.cloud.openfeign.circuitbreaker.enabled` defaults to `false`. Enabling this property applies circuit breakers to **Feign client methods** across the application, not just a single method. It is not a `RequestInterceptor` and is not turned on automatically by adding Spring Cloud LoadBalancer alone.

Feign interface:

~~~java
package com.example.order.inventory;

import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@FeignClient(
        name = "inventory-service",
        fallbackFactory = InventoryFeignFallbackFactory.class
)
public interface InventoryFeignClient {

    @GetMapping("/stock/{sku}")
    StockView getStock(@PathVariable("sku") String sku);
}
~~~

DTO returned to caller:

~~~java
package com.example.order.inventory;

public record StockView(
        String sku,
        Integer available,
        boolean degraded
) {
}
~~~

Cause-aware fallback factory:

~~~java
package com.example.order.inventory;

import feign.FeignException;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import org.springframework.cloud.openfeign.FallbackFactory;
import org.springframework.stereotype.Component;

@Component
public class InventoryFeignFallbackFactory
        implements FallbackFactory<InventoryFeignClient> {

    @Override
    public InventoryFeignClient create(Throwable cause) {
        return sku -> {
            if (cause instanceof CallNotPermittedException) {
                return new StockView(sku, null, true);
            }

            if (cause instanceof FeignException error) {
                if (error.status() < 0 || error.status() >= 500) {
                    return new StockView(sku, null, true);
                }

                // Do not mask client errors like 400/401/403/404.
                throw error;
            }

            if (cause instanceof RuntimeException runtime) {
                throw runtime;
            }

            throw new IllegalStateException(
                    "Unexpected inventory failure", cause
            );
        };
    }
}
~~~

`InventoryFeignFallbackFactory` must be a Spring bean. In a lab, add `@EnableFeignClients` on the caller and ensure packages are scanned. Passing `fallbackFactory` on the interface alone is insufficient if dependencies, flags, or beans are misconfigured.

Use `FallbackFactory` when you need to inspect the cause; `fallback` specifies a fixed replacement implementation suited for simpler cases.

**Scope:** if multiple Feign clients have differing needs, weigh enabling circuit breakers for all methods and configuring opt-outs. OpenFeign documentation shows using a prototype `Feign.Builder` to exclude a client from the shared breaker when needed; never generate masses of circuit breakers with random IDs.

## 11. OpenFeign Breaker IDs Are Not Simply the Service ID

Per Spring Cloud OpenFeign documentation, breaker names typically follow:

~~~text
<FeignClientInterface>#<method>(<parameterTypes>)
~~~

For example, a method on `InventoryFeignClient` might look like `InventoryFeignClient#getStock(String)`. In current versions, `spring.cloud.openfeign.circuitbreaker.alphanumeric-ids.enabled` defaults to enabled so IDs work cleanly in configuration properties.

Use `CircuitBreakerNameResolver` to control naming:

~~~java
import org.springframework.cloud.openfeign.CircuitBreakerNameResolver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class FeignCircuitBreakerNaming {

    @Bean
    CircuitBreakerNameResolver circuitBreakerNameResolver() {
        return (feignClientName, target, method) ->
                target.type().getSimpleName()
                        + method.getName();
    }
}
~~~

With this example, the resulting ID is `InventoryFeignClientgetStock` and can be configured as:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      InventoryFeignClientgetStock:
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
~~~

**Verify the actual name in your running version's registry/metrics/logs** rather than copying examples blindly when using default naming. Group breaker configurations and normalized names should also be re-verified when upgrading release trains.

## 12. Fallbacks Must Preserve Business Semantics

| Operation | Potentially valid fallback | Dangerous fallback |
|---|---|---|
| Optional product recommendations | Empty list with degraded flag | Pretending recommendation service is healthy |
| Reference display price | Cache with timestamp, marked stale | Using stale price at checkout without validation |
| Stock lookup | UNKNOWN so UI prompts retry | Returning `available = 0` or `999` as real stock |
| Reserve stock | Fail fast, store idempotency key | Returning "reserved" without confirmation |
| Create payment | Fail safe, query status later | Returning "paid" when outcome is unknown |
| Mandatory audit | Never silently drop events | Unconditional fallback that logs nothing |

An ideal fallback should be **fast, side-effect-free, and avoid immediately calling the failing dependency again**. If falling back to Redis or a secondary service, that fallback also needs its own timeout/concurrency budget and independent monitoring.

An HTTP 200 carrying `degraded: true` may be a sensible representation for display features, yet should not fool monitoring into believing business requests completed at full fidelity. For critical mutations, returning a controlled error is more appropriate.

## 13. Ordering Circuit Breaker, Retry, and Timeout

One way to layer policies:

~~~mermaid
flowchart LR
    A["Business request"] --> D["End-to-end deadline"]
    D --> CB["CircuitBreaker"]
    CB --> R["Bounded retry"]
    R --> LB["Spring Cloud LoadBalancer"]
    LB --> T["HTTP transport timeout"]
    T --> B["Inventory replica"]
~~~

This is **one architectural choice**, not the single automatic order in Spring Cloud. If the breaker **wraps retry**, one logical call with multiple attempts can yield a single breaker outcome. If retry **wraps the breaker**, each attempt can be recorded separately and open the breaker sooner.

Make explicit decisions on:

- Which layer owns retries: Feign, LoadBalancer, resilience layer, or gateway?
- Does the breaker measure logical calls or individual HTTP attempts?
- Which exceptions are retried, ignored, or recorded as failures?
- Does transport timeout bound a single attempt or the entire chain?
- Does the fallback fit inside the same end-to-end deadline?
- **Never retry `CallNotPermittedException`**, as the breaker is actively rejecting calls.
- Retry write operations only when idempotency is guaranteed; timeouts can occur after the backend already committed.

A circuit breaker **does not bound concurrency while CLOSED**. Bulkheads, connection pool limits, timeouts, and load shedding each play distinct roles in preventing cascading failures.

## 14. TimeLimiter, Thread Pools, and Caller Context

TimeLimiter sometimes executes blocking work on an executor. When the caller uses `MDC`, `SecurityContextHolder`, or another `ThreadLocal`-backed holder for correlation IDs and bearer tokens, switching execution threads can cause **context to vanish**.

Example:

~~~text
HTTP thread:
    correlationId = C-123
    SecurityContext = authenticated user
        |
        v
CircuitBreaker / TimeLimiter
        |
        v
Executor thread:
    MDC / SecurityContext may be empty unless propagated
        |
        v
OpenFeign RequestInterceptor or RestClient interceptor
~~~

Mitigations:

- Never store correlation IDs or user details in mutable fields of a singleton HTTP client/breaker.
- For blocking apps using executors, configure context propagation via Spring Security/Micrometer support or a custom executor with explicit copy/restore rules.
- When using `DelegatingSecurityContextExecutorService` or similar wrappers, test clearing context upon task completion to prevent leaks.
- With Reactor/WebClient, prefer Reactor `Context` and tracing instrumentation instead of assuming ThreadLocal survives across all operators.
- Service-to-service tokens can be issued via dedicated client credentials; do not blindly relay user JWTs to every downstream.
- Do not set a 200 ms time limit only to let a fallback make a 5-second network call: fallbacks must also fit within the overall deadline.

Spring Cloud CircuitBreaker provides extension points to configure executors/context-aware executors for the Resilience4j implementation. Pick an executor and propagation strategy compatible with your release train.

## 15. Observing Circuit Breaker State with Actuator and Micrometer

Transitions from CLOSED to OPEN and HALF_OPEN must be **observed and alerted on**, not masked behind "the API still returned HTTP 200 via fallback."

When Spring Boot Actuator, Resilience4j Micrometer integration, and a compatible registry are enabled, circuit breaker metrics/counters become available (exact names vary by version/exporter), for example:

| Metric group | Meaning |
|---|---|
| Circuit breaker state | CLOSED/OPEN/HALF_OPEN per breaker name |
| Calls by outcome | Successful, failed, slow, or not permitted |
| Failure/slow-call rate | Rates computed from the sliding window |
| Not-permitted calls | Calls blocked by the breaker without sending HTTP |
| Retry attempts | Actual attempts sent due to retries |
| HTTP client latency | Transport/operation latency |
| LoadBalancer instance selection | Service ID/instance and outcome when instrumented |
| Fallback count | Counts of degradation, cache fallback, or fail-fast |

Related sample configuration (requires Actuator starter and compatible metrics registry):

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics

resilience4j:
  circuitbreaker:
    instances:
      inventoryRead:
        registerHealthIndicator: true
~~~

`registerHealthIndicator: true` can surface breaker state in health endpoints when supported by the integration. **Never automatically treat an OPEN breaker as a reason for orchestration to restart all of order-service.** One downstream can be down while order-service serves other APIs normally. Readiness/liveness rules must reflect dependency criticality and operational policy.

Useful alerts include: `inventoryRead` breaker staying OPEN too long, rising not-permitted call rates, or UNKNOWN fallback rates exceeding thresholds. Never place dynamic SKUs/user IDs/tenants into metric labels where they cause unbounded cardinality.

### Logging Must Distinguish Rejections from Backend Errors

Two situations look similar to users yet have different causes:

~~~text
Case A: HTTP attempt failed
  inventoryRead CLOSED
  -> LoadBalancer picks inventory B
  -> Request sent
  -> Connect timeout / HTTP 503
  -> Breaker records failure

Case B: breaker is OPEN
  inventoryRead OPEN
  -> CallNotPermittedException
  -> No new HTTP attempt
  -> Fallback UNKNOWN / error
~~~

If every failure is logged as "inventory timeout," operations teams can misdiagnose incidents. Use exception class, breaker state, and trace context to tell them apart; never log access tokens or sensitive payloads.

## 16. Recovery: HALF_OPEN Does Not Lift All Limits

When the OPEN wait expires, Resilience4j can transition states to probe new calls. Permitted probe count is governed by `permittedNumberOfCallsInHalfOpenState`; once those slots are in use or consumed, additional calls may continue being rejected until the next state decision.

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant B as CircuitBreaker
    participant L as LoadBalancer
    participant I as inventory-service

    C->>B: GET /stock (breaker OPEN)
    B-->>C: CallNotPermitted / fallback
    Note over B: waitDurationInOpenState elapses
    C->>B: GET /stock (recovery probe)
    B->>L: Permit one HALF_OPEN probe
    L->>I: HTTP GET /stock
    I-->>L: 200 OK
    L-->>B: Success outcome
    Note over B: Enough good outcomes -> CLOSED
    B-->>C: Real StockView
~~~

The diagram illustrates state transitions; moving from HALF_OPEN to CLOSED depends on **the full probe sample** and failure/slow-call policies, not necessarily a single 200 response.

Operational considerations:

1. Do not set `waitDurationInOpenState` too short when the target needs time to recover: the breaker will probe repeatedly and add load.
2. Do not set it too long if business requires rapid recovery after brief blips.
3. Each **caller** instance maintains its own in-process breaker state. Many caller replicas entering HALF_OPEN near each other can generate a notable probe burst; factor in concurrency limits and recovery capacity.
4. Metrics and tracing should capture state transition timestamps, half-open probes, and fallback counts.
5. One successful call to inventory does not prove the whole backend is stable; require enough samples per policy.
6. If the service recovers yet still responds slower than `slowCallDurationThreshold`, the breaker may stay/re-enter OPEN due to **slow-call rate**, even if every status is 200.

Never rely on restarting the caller to "reset the breaker" as a primary recovery mechanism: that wipes history without fixing the underlying downstream failure.

## 17. Hands-On Lab with Two Inventory Replicas

Goal: prove that an `inventory-service` failure transitions the breaker CLOSED → OPEN, sends zero backend requests while OPEN, and uses HALF_OPEN to probe recovery once inventory returns.

### 17.1. Discovery Configuration on the Caller

Use `SimpleDiscoveryClient` for two replicas:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: order-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

Add breaker settings tailored for the lab:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventoryRead:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 5
        minimumNumberOfCalls: 5
        failureRateThreshold: 50
        waitDurationInOpenState: 8s
        permittedNumberOfCallsInHalfOpenState: 3
  timelimiter:
    instances:
      inventoryRead:
        timeoutDuration: 2s
~~~

These numbers are only for testing with **few requests**, not production thresholds. If requests have retries, the breaker may observe call counts different from HTTP attempt counts; **disable retries or strictly bound attempts** in the lab for clear observation.

### 17.2. Creating an Endpoint Simulating Broken Inventory

Run similar code in each inventory process:

~~~java
package com.example.inventory;

import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoInventoryController {

    private final AtomicBoolean failing = new AtomicBoolean(false);

    @GetMapping("/stock/{sku}")
    public ResponseEntity<InventoryQuantity> stock(
            @PathVariable String sku) {

        if (failing.get()) {
            return ResponseEntity
                    .status(HttpStatus.SERVICE_UNAVAILABLE)
                    .build();
        }

        return ResponseEntity.ok(
                new InventoryQuantity(sku, 12)
        );
    }

    // For local lab environment only, NEVER deploy publicly.
    @PostMapping("/demo/fail")
    public void fail() {
        failing.set(true);
    }

    @PostMapping("/demo/recover")
    public void recover() {
        failing.set(false);
    }

    public record InventoryQuantity(String sku, int available) {}
}
~~~

Run inventory on ports 8081 and 8082. Note each process has its own `AtomicBoolean`, so toggling 8081 does **not** affect 8082.

On the caller, use RestClient + `InventoryGateway` from earlier and create a controller exposing `GET /orders/stock/{sku}` delegating to `gateway.getStock(sku)`. This endpoint must be implemented in the lab; it is not built into Spring Cloud.

### 17.3. Scenario A: All Instances Healthy

~~~powershell
1..6 | ForEach-Object {
    Invoke-RestMethod "http://localhost:8080/orders/stock/SKU-001"
}
~~~

Initial expectation is `degraded: false`, `available: 12`, and the breaker in CLOSED. Check inventory access logs, since `StockView` responses do not include the instance ID.

### 17.4. Scenario B: Both Replicas Return 503

~~~powershell
Invoke-RestMethod -Method Post http://localhost:8081/demo/fail
Invoke-RestMethod -Method Post http://localhost:8082/demo/fail

1..8 | ForEach-Object {
    Invoke-RestMethod "http://localhost:8080/orders/stock/SKU-001"
}
~~~

Once enough calls accumulate and the failure rate crosses the threshold, the breaker can transition to OPEN. The caller receives `degraded: true`, `available: null` when fallback permits. Subsequent calls while OPEN return immediately without **any** new inbound requests appearing in inventory logs.

You can inspect circuit breaker state/counters via Actuator metrics when integration is enabled. Never assert "always OPEN on exact call N" if tests involve retries, custom exception classifiers, differing metrics settings, or concurrent calls.

### 17.5. Scenario C: Backend Recovers

~~~powershell
Invoke-RestMethod -Method Post http://localhost:8081/demo/recover
Invoke-RestMethod -Method Post http://localhost:8082/demo/recover
~~~

After `waitDurationInOpenState` elapses, send a few new requests to trigger HALF_OPEN probes. If outcomes meet criteria, the breaker returns to CLOSED and returns real `StockView` values. If inventory still returns 503, it can transition back to OPEN.

**No caller restart is needed**; the breaker is expected to recover via its state machine and probes. With very low traffic, no new probe runs until a request arrives after the wait period. In multi-replica caller deployments, each process may observe different states.

## 18. Meaningful Testing Strategy

Do not only test "fallback always returns 200 on error." A proper test suite should cover:

1. **Normal path:** backend 200, breaker CLOSED, real data and `degraded = false`.
2. **Error classification:** business 404/400 are not turned into 200 UNKNOWN; breaker metrics do not treat them as outages when ignored by policy.
3. **OPEN path:** after sufficient failures, new calls do not hit the backend and return fallback or fail-fast errors per contract.
4. **HALF_OPEN:** after wait duration, only the permitted number of probes are sent; good results return the breaker to CLOSED.
5. **Failed recovery:** failing probes send the breaker back to OPEN.
6. **Timeouts:** transport timeouts and TimeLimiter/overall deadlines are not conflated; verify no lingering tasks remain after cancellation.
7. **Retry:** check logical call counts and attempt counts; exclude retries when breaker is OPEN.
8. **Fallback safety:** `available = null` is never misinterpreted by the order layer as `available > 0`.
9. **Multi-replica caller:** breaker state is per-process; evaluate alignment of metrics/alerts.
10. **No-instance:** when discovery returns zero instances, handle LoadBalancer and breaker errors cleanly without misleading messages.

You can use WireMock or MockWebServer with Spring Boot tests to simulate HTTP 200, 404, 503, connect failures, and delays; control clocks or use test schedulers to avoid flaky tests. For unit tests covering only `CircuitBreakerFactory` wrappers/fallbacks, stub the HTTP adapter to remove network dependencies.

Do not write assertions relying on exact Round Robin replica sequences when tests involve concurrency/retries, nor expect the very first failed call to open the breaker.

## 19. Common Integration Mistakes

| Symptom | Common cause | Where to check |
|---|---|---|
| Starter added, yet breaker does not protect RestClient | Not calling `factory.create(...).run(...)` | Inspect HTTP gateway method and factory bean |
| WebClient still sends HTTP when expected OPEN | Using a client not wrapped by reactive breaker | Verify the publisher passed to `breaker.run(...)` |
| Feign fallback does not run | `spring.cloud.openfeign.circuitbreaker.enabled` not enabled or fallback is not a bean | Check starter, property, and component scan |
| Resilience4j properties have no effect on Feign | Wrong Feign method breaker ID | Check naming resolver, alphanumeric IDs, and metrics |
| 404 opens the breaker | Exception classifier treats 404 as failure | Configure ignore/record policies for business errors |
| All requests OPEN even though one replica broke | Shared breaker per service ID/operation | Fix health/discovery filtering or isolation strategy |
| OPEN yet inventory access logs show traffic | Another caller instance, another method, or retries/probes | Tag instance/operation IDs to distinguish |
| Breaker never opens | High `minimumNumberOfCalls`, failures unrecorded, or fallback sits inside | Check counters and policy wrapping order |
| Breaker never returns to CLOSED | No probes arriving or probes still fail/slow | Check HALF_OPEN events and thresholds |
| Timeout does not cancel real HTTP request | TimeLimiter only signals timeout/best-effort cancel | Check transport, task lifecycle, and backend work |
| Correlation ID lost when wrapping blocking calls | Executor/thread switch without context propagation | Use context-aware executor/propagation |
| Dashboard shows all HTTP 200 while inventory is down | Fallback masks technical errors | Add degraded metrics; do not equate 200 with full success |
| Retrying while breaker is OPEN | Policy retries every exception | Exclude `CallNotPermittedException` from retry conditions |
| Circuit breaker marks the app unhealthy | Health indicator improperly drives readiness/liveness | Redesign health groups by dependency criticality |

## 20. Pre-Production Checklist

- [ ] Identify HTTP operations to protect and assign stable breaker names.
- [ ] Separate single-instance failures (health/discovery) from dependency/operation outages (breaker).
- [ ] Use `CircuitBreakerFactory` for blocking RestClient and `ReactiveCircuitBreakerFactory` for WebClient.
- [ ] For OpenFeign, verify starter, `spring.cloud.openfeign.circuitbreaker.enabled`, and `fallbackFactory`.
- [ ] Know the exact breaker name of each Feign method when writing Resilience4j config.
- [ ] Derive `minimumNumberOfCalls`, window, failure/slow rates, and wait duration from SLO data.
- [ ] Exclude business 4xx from failure classification when appropriate without masking security/validation errors.
- [ ] Ensure fallbacks return clear semantics and never fake success for reserve/payment operations.
- [ ] Maintain independent transport timeouts, overall deadlines, and retry budgets; never retry breaker-rejected calls.
- [ ] Test TimeLimiter impact on executors, MDC/SecurityContext, and cancellation.
- [ ] Under high concurrency, add bulkhead/pool limits to prevent resource exhaustion while CLOSED.
- [ ] Track state transitions, not-permitted calls, fallback/degraded rates, backend errors, and latency.
- [ ] Account for multiple caller replicas entering HALF_OPEN concurrently and potential probe surges.
- [ ] Ensure an OPEN breaker health indicator does not unintentionally restart the whole application.
- [ ] Test CLOSED/OPEN/HALF_OPEN transitions, exception classes, retries, timeouts, and recovery.
- [ ] Avoid stacking multiple circuit breaker layers around the same operation without clear measurement intent.

## References

- [Spring Cloud Commons — Spring Cloud Circuit Breaker](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-circuitbreaker.html): `CircuitBreakerFactory`, `ReactiveCircuitBreakerFactory`, and extension points for HTTP clients.
- [Spring Cloud CircuitBreaker — Resilience4j Properties](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j/circuit-breaker-properties-configuration.html): default/group/instance config, TimeLimiter, and property precedence.
- [Spring Cloud CircuitBreaker — Default Configuration](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j/default-configuration.html): `Customizer` for blocking/reactive factories.
- [Spring Cloud OpenFeign — Reference](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html): Feign CircuitBreaker support, fallbackFactory, breaker IDs, and enabling integration.
- [Spring Cloud Commons — Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): service IDs, `ServiceInstance`, health checks, retries, and selection.
- [Resilience4j — CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker): sliding windows, failure/slow-call thresholds, and state transitions.

**Conclusion:** Spring Cloud Circuit Breaker works best when placed right at the **HTTP dependency boundary**, wrapping a specific operation of RestClient, WebClient, or OpenFeign. It shields callers from repeatedly waiting on a failing or slow dependency, yet does not replace LoadBalancer, health checks, timeouts, idempotency, or bulkheads. A successful design relies on stable breaker IDs, accurate error classification, honest fallbacks, observable OPEN/HALF_OPEN states, and tested recovery procedures.
