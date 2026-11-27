# Mapping Timeout, Isolation, and Fallback Intent When Migrating Off Hystrix

## Objectives

When migrating a legacy Spring Cloud application off Netflix Hystrix to Spring Cloud CircuitBreaker with Resilience4j, you should not merely rename configuration properties. Hystrix bundles multiple capabilities into a single command: timeout, thread/semaphore isolation, circuit breaking, and fallback. In the new architecture, these responsibilities are typically configured as distinct mechanisms such as Circuit Breaker, TimeLimiter, Bulkhead, and HTTP client timeouts.

After this lesson, you will be able to:

- Identify the intent behind Hystrix timeout, thread isolation, and semaphore isolation.
- Map those intents to TimeLimiter, Bulkhead, and HTTP client-layer timeouts.
- Migrate fallbacks from `getFallback()` to Spring Cloud CircuitBreaker callbacks or fallback methods.
- Distinguish intent-equivalent configurations from properties that have no one-to-one mapping.
- Plan the migration, test behavior, and monitor load after leaving Hystrix.

## Migration Mindset: Preserve Intent, Redesign the Mechanism

A Hystrix command typically combines the following responsibilities:

- Execute the dependency operation.
- Enforce a timeout.
- Isolate via a thread pool or semaphore.
- Track failures to open/close the circuit.
- Invoke a fallback when the operation fails or is rejected.

Spring Cloud CircuitBreaker provides the abstraction for the protected call. When using Resilience4j, each capability is expressed through its own configuration. Therefore, a single Hystrix property often needs to be broken down into one or more new requirements.

| Intent in Hystrix | Mechanism Commonly Used After Migration | What to Verify |
|---|---|---|
| `execution.isolation.thread.timeoutInMilliseconds` | TimeLimiter and HTTP client timeouts. | Caller stops waiting on time; whether actual I/O is canceled. |
| `execution.isolation.strategy=THREAD` | ThreadPoolBulkhead or a bounded dedicated executor. | Pool, queue, rejection, and context propagation. |
| `execution.isolation.strategy=SEMAPHORE` | SemaphoreBulkhead. | Concurrent call limit and wait time to acquire a permit. |
| `execution.isolation.semaphore.maxConcurrentRequests` | `bulkhead.maxConcurrentCalls`. | This is a caller-side concurrency limit, not a thread count. |
| `execution.isolation.thread.*` pool/queue | `thread-pool-bulkhead` or dedicated executor. | `queueCapacity` does not have identical semantics to every Hystrix queue limit. |
| `getFallback()` | Fallback function of `CircuitBreaker.run` or `fallbackMethod`. | Which exceptions trigger the fallback and what response type is returned. |
| `circuitBreaker.requestVolumeThreshold` | `minimumNumberOfCalls`. | Statistical window and sample counting behavior. |
| `circuitBreaker.errorThresholdPercentage` | `failureRateThreshold`. | Ignored exceptions and applied threshold. |
| `circuitBreaker.sleepWindowInMilliseconds` | `waitDurationInOpenState`. | Duration before allowing `HALF_OPEN` probes. |

This is an intent-based mapping. Not every Hystrix property has an equivalent Resilience4j property. Identify the behavior the application needs to preserve and select the right new mechanism rather than copying names and values verbatim.

## Timeout: Separating Wait Limits from I/O Limits

In Hystrix, `execution.isolation.thread.timeoutInMilliseconds` generally bounds how long a command executes under thread isolation. When migrating to Spring Cloud CircuitBreaker, you can configure TimeLimiter per instance:

```yaml
resilience4j:
  timelimiter:
    instances:
      catalog:
        timeoutDuration: 800ms
        cancelRunningFuture: true
```

With Spring Cloud CircuitBreaker Resilience4j, TimeLimiter is integrated into the factory according to the integration's configuration. You can disable TimeLimiter globally with `spring.cloud.circuitbreaker.resilience4j.disable-time-limiter: true`, or scope it per instance/group with `disable-time-limiter-map` if your version supports it. Disabling TimeLimiter does not disable the Circuit Breaker.

TimeLimiter bounds waiting time according to the execution mechanism provided by the integration. It does not guarantee that an underlying socket, JDBC statement, or blocking task stops immediately upon timeout. Consequently, you must configure timeouts on the client performing I/O:

- HTTP connect timeout limits connection establishment time.
- HTTP response/read timeout limits waiting for response data.
- JDBC connection acquisition timeout limits waiting to obtain a connection from the pool.
- Query/statement timeout limits query execution time at the database driver or ORM level.
- Request deadline limits total elapsed time across multiple hops.

Example configuring a `WebClient` using Reactor Netty:

```java
import java.time.Duration;

import reactor.netty.http.client.HttpClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class CatalogClientConfiguration {
    @Bean
    WebClient catalogWebClient() {
        HttpClient httpClient = HttpClient.create()
                .responseTimeout(Duration.ofMillis(700));

        return WebClient.builder()
                .baseUrl("http://catalog-service")
                .clientConnector(new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
```

The example above sets a response timeout; in production, configure connect timeout and pool acquire timeout as well according to the client and version in use. If using `RestClient` or `RestTemplate`, configure timeouts in the corresponding HTTP request factory.

### Overall Deadline

Do not set the same long timeout at every layer. If the Gateway waits 2 seconds, order-service should not start a new inventory call with a 2-second timeout when the request has already spent 1.5 seconds. Propagate or compute the remaining deadline and only start the operation if sufficient budget remains.

For example, a request with a 1,500 ms deadline might allocate 200 ms for Gateway processing, up to 900 ms for order-service to call its dependency, and the remainder for response processing/serialization. Values must be based on SLAs and measured latencies. Per-call TimeLimiter does not replace an overall deadline.

## Isolation: Thread Pools and Semaphores Are Not the Same

Hystrix provides two primary isolation strategies:

- **THREAD:** the command runs on a separate thread pool. Its purpose is to isolate a blocking dependency from request-handling threads and bound concurrent work.
- **SEMAPHORE:** the command runs on the caller's thread but must acquire a permit. Its purpose is to limit concurrency without creating a separate thread pool.

In Resilience4j, these two intents are typically mapped as follows:

| Hystrix | Resilience4j | Behavior |
|---|---|---|
| Thread isolation | ThreadPoolBulkhead | Has its own pool and queue; tasks can be queued and executed on workers. |
| Semaphore isolation | SemaphoreBulkhead | Limits permits; creates no new thread pool. |

SemaphoreBulkhead example:

```yaml
resilience4j:
  bulkhead:
    instances:
      catalog:
        maxConcurrentCalls: 24
        maxWaitDuration: 0
```

ThreadPoolBulkhead example:

```yaml
resilience4j:
  thread-pool-bulkhead:
    instances:
      legacy-catalog:
        coreThreadPoolSize: 4
        maxThreadPoolSize: 8
        queueCapacity: 16
        keepAliveDuration: 20ms
```

SemaphoreBulkhead corresponds to limiting concurrent calls. ThreadPoolBulkhead fits when a blocking operation must be isolated on a separate executor. Do not switch every call to ThreadPoolBulkhead out of habit: a reactive application needs to keep I/O non-blocking and avoid running blocking code on the event loop.

### Queue Limits Are Not Always Equivalent

A Hystrix thread pool has properties such as `coreSize`, `maxQueueSize`, and `queueSizeRejectionThreshold`. Resilience4j ThreadPoolBulkhead has `coreThreadPoolSize`, `maxThreadPoolSize`, and `queueCapacity`. These values serve related goals, but queueing, rejection, and threshold-adjustment behavior are not identical.

A large queue only keeps requests waiting longer; it does not make the dependency faster. Choose a small queue based on the deadline, concurrency limits, and processing time. If a request exceeds its deadline while still queued, the work may still run after the caller no longer needs the result.

Hystrix can configure a separate semaphore limit for fallbacks via `fallback.isolation.semaphore.maxConcurrentRequests`. Do not assume Resilience4j automatically creates the same fallback quota. If the fallback can generate significant load, bound it separately with an appropriate semaphore, executor, or rate limit.

## Circuit Breaker: Mapping Windows and Thresholds

Several Hystrix Circuit Breaker properties map closely in intent to Resilience4j:

| Hystrix | Resilience4j | Notes |
|---|---|---|
| `requestVolumeThreshold` | `minimumNumberOfCalls` | Minimum samples before evaluating thresholds. |
| `errorThresholdPercentage` | `failureRateThreshold` | Failure rate percentage to open the circuit. |
| `sleepWindowInMilliseconds` | `waitDurationInOpenState` | Wait time in `OPEN` before allowing probes. |
| `metrics.rollingStats.timeInMilliseconds` | `slidingWindowType: TIME_BASED` and `slidingWindowSize` | Requires unit conversion and verifying bucket/window division. |
| `forceOpen` / `forceClosed` | Equivalent forced states if supported by the integration/version | Do not assume identical operational behavior or override precedence. |

Resilience4j configuration example:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      catalog:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallRateThreshold: 60
        slowCallDurationThreshold: 700ms
        waitDurationInOpenState: 8s
        permittedNumberOfCallsInHalfOpenState: 3
```

Hystrix and Resilience4j do not necessarily compute rolling statistics the same way. Do not convert `rollingStats.timeInMilliseconds` into an arbitrary `slidingWindowSize` and expect identical state-transition rates. Choose window type, size, minimum calls, and thresholds based on real traffic, then run the same failure scenarios to calibrate.

## Fallback: Moving from getFallback() to Explicit Callbacks

In Hystrix, fallbacks are typically implemented via `getFallback()` on the command or a fallback method attached to it. When migrating to Spring Cloud CircuitBreaker, the fallback callback is passed directly at the call site:

```java
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class CatalogGateway {
    private final RestClient restClient;
    private final CircuitBreaker catalogBreaker;

    public CatalogGateway(
            RestClient.Builder builder,
            CircuitBreakerFactory<?, ?> factory) {
        this.restClient = builder.baseUrl("http://catalog-service").build();
        this.catalogBreaker = factory.create("catalog");
    }

    public Product findById(String id) {
        return catalogBreaker.run(
                () -> restClient.get()
                        .uri("/products/{id}", id)
                        .retrieve()
                        .body(Product.class),
                error -> Product.unavailable(id));
    }
}
```

`Product` and `Product.unavailable` are example types. The fallback callback receives the cause as a `Throwable`; the application can classify the cause to return cached data, an unavailable response, or propagate the error to the caller. With Resilience4j annotations, you can use `@CircuitBreaker(name = "catalog", fallbackMethod = "findFallback")`, though that is a Resilience4j annotation and still depends on Spring AOP proxies.

Do not treat every error with the same fallback:

- Circuit Breaker is `OPEN`: return cached data or a dependency-unavailable error.
- Timeout/connectivity failure: return degraded data if business rules allow.
- Validation error or business HTTP 4xx: preserve the error semantics rather than converting it into default data.
- Programming or configuration errors: usually propagate the error and fix the root cause rather than hiding it.

Hystrix has the concept of errors excluded from statistics such as `HystrixBadRequestException`. When moving to Resilience4j, specify which exceptions should not increase the failure rate using `ignoreExceptions` or an appropriate predicate. Note that ignoring an exception in statistics does not guarantee the fallback will not run; fallback behavior still depends on the call path and API being used.

### Bounding Fallbacks Separately

Fallbacks can become overloaded too. If every failing request calls a cache, secondary database, or another service, the fallback source can become a new bottleneck. You should:

- Limit fallback concurrency separately from the primary dependency.
- Set short timeouts and bounded queues for the fallback source.
- Never call the failing dependency again via another route.
- Return a structured error if no safe data can be returned.
- Monitor fallback rate and fallback-specific failures.

## Practical Configuration Mapping

The table below is a checklist for migrating common intents. Resilience4j property names must match the instance ID used in the Spring Cloud CircuitBreaker factory.

| Hystrix Configuration | New Configuration/Design | Action Required |
|---|---|---|
| `execution.timeout.enabled` | Enable/disable integration TimeLimiter | Use `disable-time-limiter` only when truly needed; still configure HTTP client timeouts. |
| `execution.isolation.thread.timeoutInMilliseconds` | `resilience4j.timelimiter.instances.<id>.timeoutDuration` | Convert duration, then verify cancellation and I/O timeouts. |
| `execution.isolation.strategy=THREAD` | `resilience4j.thread-pool-bulkhead.instances.<id>` | Choose pool, queue, rejection, and context propagation. |
| `execution.isolation.strategy=SEMAPHORE` | `resilience4j.bulkhead.instances.<id>` | Choose `maxConcurrentCalls` and `maxWaitDuration`. |
| `execution.isolation.semaphore.maxConcurrentRequests` | `bulkhead.maxConcurrentCalls` | Align concurrency limits with upstream capacity. |
| `fallback.isolation.semaphore.maxConcurrentRequests` | Separate Bulkhead for fallback | Do not share quota with primary calls if load profiles differ. |
| `fallback.enabled` | Intentional fallback callback/method | Explicitly decide which errors trigger fallback and which propagate to the caller. |
| `circuitBreaker.requestVolumeThreshold` | `minimumNumberOfCalls` | Choose window and minimum sample size. |
| `circuitBreaker.errorThresholdPercentage` | `failureRateThreshold` | Test actual failure rate after migration. |
| `circuitBreaker.sleepWindowInMilliseconds` | `waitDurationInOpenState` | Choose open duration based on dependency recovery speed. |
| `threadpool.<key>.coreSize` | `coreThreadPoolSize` | Do not copy numbers blindly if queue model and load changed. |
| `threadpool.<key>.maxQueueSize` | `queueCapacity` | Choose a bounded queue based on deadlines and latency. |

No single property replaces an entire Hystrix command. A command using THREAD isolation may require ThreadPoolBulkhead, TimeLimiter, HTTP client timeouts, Circuit Breaker, and a fallback. Migration is complete when behavior and resource bounds match operational goals, not when every configuration number has been copied over.

## Example Post-Migration Configuration

An illustrative configuration for the `catalog` dependency:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      catalog:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 8s
        permittedNumberOfCallsInHalfOpenState: 3
  timelimiter:
    instances:
      catalog:
        timeoutDuration: 800ms
        cancelRunningFuture: true
  bulkhead:
    instances:
      catalog:
        maxConcurrentCalls: 24
        maxWaitDuration: 0
  thread-pool-bulkhead:
    instances:
      legacy-catalog:
        coreThreadPoolSize: 4
        maxThreadPoolSize: 8
        queueCapacity: 16
```

The example above illustrates both Bulkhead types for two different cases. You do not necessarily enable both SemaphoreBulkhead and ThreadPoolBulkhead for the same call. Choose an isolation mechanism appropriate to the execution model and verify decorator order in your integration. If you need to protect a blocking HTTP client, ThreadPoolBulkhead can isolate threads; if you only need to limit concurrency on the caller thread, SemaphoreBulkhead is usually a better fit.

## Command-by-Command Migration Roadmap

Avoid replacing all of Hystrix at once if the system has many dependencies and complex fallbacks. Migrate command by command or by dependency group:

1. **Inventory commands:** record command key, group key, thread pool key, downstream target, timeout, isolation strategy, fallback, and ignored exceptions.
2. **Classify I/O:** determine whether the command is blocking, non-blocking, CPU-bound, or fans out to multiple dependencies.
3. **Choose new boundaries:** assign a Circuit Breaker ID per dependency or operation group with matching failure characteristics.
4. **Map timeouts:** configure timeouts on HTTP/database clients, TimeLimiter, and overall deadlines.
5. **Map isolation:** select SemaphoreBulkhead or ThreadPoolBulkhead; set queue and concurrency based on capacity.
6. **Migrate fallbacks:** preserve data types, statuses, and business semantics; bound load on fallback sources.
7. **Migrate circuit policy:** select sliding window, minimum calls, failure/slow-call thresholds, and `OPEN` duration.
8. **Test failures:** test success, timeout, connection reset, 5xx, rejections, fallback failures, and `HALF_OPEN` recovery.
9. **Compare telemetry:** compare request rate, latency, thread/queue/connection saturation, retries, fallbacks, and Circuit Breaker states.
10. **Roll out in waves:** observe one dependency first, then expand once behavior is stable.

## Post-Migration Behavioral Testing

An integration test suite should prove that the legacy intent is satisfied by the new mechanism:

| Scenario | Outcome to Verify |
|---|---|
| Dependency responds fast | Caller receives real result; Circuit Breaker records success. |
| Dependency exceeds timeout | Caller finishes within timeout/deadline; HTTP client does not hold resources indefinitely. |
| Dependency repeatedly errors | Circuit Breaker opens after sufficient samples reach the threshold. |
| Circuit Breaker `OPEN` | Supplier does not call upstream; fallback or rejection error is handled properly. |
| Semaphore out of permits | New requests are rejected/waited within bounds; no new threads are created. |
| ThreadPoolBulkhead queue full | New tasks are rejected; queue does not exceed capacity. |
| Fallback slow or failing | Fallback has its own timeout/concurrency bounds; does not exhaust caller resources. |
| Dependency recovers | `HALF_OPEN` probes are bounded and the circuit closes after enough successful calls. |

Verify the actual number of upstream HTTP requests as well. If a timeout occurs but the request continues running on a thread or socket, asserting only that the caller received a fallback is insufficient. Observe the connection pool, active threads, and running tasks to confirm resources are released.

## Hystrix Features Not Automatically Replaced

Several Hystrix capabilities have no automatic mapping just by adopting Spring Cloud CircuitBreaker:

- **Request cache:** requires explicitly defining cache keys, request scope, and a caching mechanism; it does not appear automatically when migrating Circuit Breakers.
- **Request collapsing:** requires custom batching or coalescing if supported downstream.
- **Hystrix dashboard/event stream:** migrate to Micrometer, Actuator, and the corresponding observability stack; legacy dashboards cannot read Resilience4j metrics automatically.
- **Thread context propagation:** verify SecurityContext, MDC, tracing, and transaction context when moving to executors/ThreadPoolBulkhead.
- **Fallback semaphore:** requires explicit fallback bounds; do not assume the primary call's Bulkhead automatically limits fallback execution.
- **Command grouping and thread pool keys:** redesign Circuit Breaker IDs, Bulkheads, and executor names around the new dependency boundaries.

If the application uses `HystrixObservableCommand` or RxJava, migrate to `Mono`/`Flux` or `CompletableFuture` according to the application model. Do not call blocking APIs on the Reactor event loop, and do not manually subscribe inside services just to trigger a fallback.

## Post-Migration Monitoring

Metrics to compare before and after migration:

- Success, failure, timeout, and rejected call rates per dependency.
- p50/p95/p99 latency and total request duration.
- Active threads, queue depth, queue wait time, and task rejections.
- Available Bulkhead permits and rejection counts.
- HTTP connection pool active/idle/pending acquire counts and acquire timeouts.
- Fallback counts, fallback success rate, and fallback latency.
- `HALF_OPEN` probe counts, time spent in `OPEN`, and recovery time.
- Logical requests vs. physical requests sent upstream.

Resilience4j can export metrics through Micrometer when the appropriate binder is enabled. Metric names and tags may differ from Hystrix; update dashboards, alerts, and runbooks accordingly. Avoid keeping an old dashboard and swapping only part of its data sources, as that easily misleads operators about system health.

## Common Pitfalls

- **Replacing a Hystrix command solely with `CircuitBreaker.run`:** misses timeouts, isolation, and concurrency limits.
- **Assuming TimeLimiter replaces HTTP timeouts:** the caller may stop waiting while underlying I/O keeps running.
- **Using ThreadPoolBulkhead for every call:** can create unnecessary queues and threads, especially with reactive I/O.
- **Using SemaphoreBulkhead while forgetting connection pool limits:** an available permit does not guarantee the HTTP client has a free connection.
- **Copying queue sizes verbatim:** queue and rejection semantics differ between the two libraries.
- **Sharing one Bulkhead for both dependency and fallback:** fallback sources may have no capacity left when the primary dependency fails.
- **Falling back on every exception to default data:** hides validation errors, programming bugs, or indeterminate business states.
- **Retrying `CallNotPermittedException`:** the Circuit Breaker already rejected the call; immediate retries only create wasted work.
- **Keeping Hystrix dashboards unchanged:** metric names, events, and states are not automatically compatible with Resilience4j.
- **Ignoring context propagation:** logs, traces, or security context can be lost when switching to a separate executor.
- **Comparing only error rates:** overlooks latency, saturation, physical request counts, and cancellation behavior.

Leaving Hystrix is an opportunity to cleanly separate timeout, isolation, Circuit Breaker, and fallback into independently configurable and observable policies. Migrate based on each command's intent, validate resource limits on both caller and upstream, and confirm via failure testing and telemetry before expanding to other dependencies.
