# Choosing Defaults and Per-ID Configuration via BulkheadProvider

Bulkhead limits how much work is allowed to run concurrently so that a dependency or a group of requests does not exhaust the application's resources. In Spring Cloud CircuitBreaker with Resilience4j, BulkheadProvider is the component that supplies Bulkhead configuration for protected calls. You can select the application-wide default Bulkhead type, declare a baseline policy for IDs, and override it with specific configuration per dependency.

This lesson focuses on choosing between SemaphoreBulkhead and FixedThreadPoolBulkhead, configuring via Resilience4jBulkheadProvider, associating configuration with IDs created by the Circuit Breaker factory, and verifying that concurrency limits behave as intended.

## 1. What Does BulkheadProvider Do?

Spring Cloud CircuitBreaker provides an abstraction to create Circuit Breakers and apply accompanying resilience mechanisms. When using Resilience4j, Resilience4jBulkheadProvider supplies Bulkhead configuration for calls. You can customize the provider with a Customizer<Resilience4jBulkheadProvider> bean.

The two commonly used methods are:

- **configureDefault(...)**: defines the baseline Bulkhead configuration for IDs that do not have a specific configuration.
- **configure(..., "id")**: registers configuration for one or more specific IDs.

IDs must be stable and must match the IDs passed to the factory when creating the Circuit Breaker. For example, a catalog-read configuration only applies to calls created via factory.create("catalog-read"). If the code calls factory.create("catalog"), the catalog-read configuration will not be selected.

The provider centralizes Bulkhead policies in one place for easier management. Instead of creating semaphores or thread pools manually in each service, the application can declare limits per dependency and let Spring Cloud CircuitBreaker apply them whenever calls pass through the corresponding factory.

## 2. Selecting the Default Bulkhead Type

Resilience4j supports two main Bulkhead types:

| Type | Protection mechanism | Best suited when |
|---|---|---|
| SemaphoreBulkhead | Uses a semaphore to limit concurrent calls; does not create a dedicated thread pool | Non-blocking calls or applications that want to keep execution on the current thread |
| FixedThreadPoolBulkhead | Runs tasks in a dedicated thread pool with bounded threads and queue | Synchronous/blocking tasks need to be isolated from request-handling resources |

Spring Cloud CircuitBreaker Resilience4j defaults to FixedThreadPoolBulkhead. You can choose SemaphoreBulkhead as the default type using the property:

~~~yaml
spring:
  cloud:
    circuitbreaker:
      resilience4j:
        enableSemaphoreDefaultBulkhead: true
~~~

When this property is enabled, the provider uses a semaphore as the default Bulkhead type. If not enabled, the default mechanism is the thread-pool Bulkhead.

No single option is right for every application. Semaphore caps concurrency without offloading work to another pool, which suits reactive pipelines or already non-blocking calls. Thread-pool Bulkhead isolates blocking work, but creates additional threads and a queue; pool and queue sizes must be chosen carefully.

With WebFlux, do not push non-blocking I/O into a thread-pool Bulkhead just to enforce a concurrency limit. Semaphore is usually better suited for capping concurrent subscriptions while preserving the reactive model. For a synchronous SDK or blocking task, a thread-pool Bulkhead can isolate the work, though the client still needs timeouts and the pool must be bounded.

## 3. Default Configuration with configureDefault

You can declare a bean to set a baseline configuration for every ID without a dedicated configuration:

~~~java
import java.time.Duration;

import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4jBulkheadConfigurationBuilder;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4jBulkheadProvider;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import io.github.resilience4j.bulkhead.BulkheadConfig;
import io.github.resilience4j.bulkhead.ThreadPoolBulkheadConfig;

@Configuration
public class BulkheadConfiguration {

    @Bean
    Customizer<Resilience4jBulkheadProvider> defaultBulkheadProvider() {
        return provider -> provider.configureDefault(id ->
            new Resilience4jBulkheadConfigurationBuilder()
                .bulkheadConfig(BulkheadConfig.custom()
                    .maxConcurrentCalls(25)
                    .maxWaitDuration(Duration.ZERO)
                    .build())
                .threadPoolBulkheadConfig(ThreadPoolBulkheadConfig.custom()
                    .coreThreadPoolSize(4)
                    .maxThreadPoolSize(8)
                    .queueCapacity(20)
                    .keepAliveDuration(Duration.ofSeconds(20))
                    .build())
        );
    }
}
~~~

The baseline configuration above illustrates a limit of 25 concurrent calls for semaphore and a thread pool with 4 core threads, up to 8 max threads, and a queue of 20 elements. These values are examples only. When the application selects SemaphoreBulkhead, bulkheadConfig is used; when it selects FixedThreadPoolBulkhead, threadPoolBulkheadConfig is used.

maxWaitDuration(Duration.ZERO) means calls do not wait for a semaphore slot once concurrency is full; they are rejected immediately. With thread-pool Bulkhead, queueCapacity determines how many tasks can wait in the queue. A larger queue increases the risk of higher latency and holding requests for too long. Do not treat a queue as a way to increase throughput: it only holds work waiting until a thread becomes free.

Even if the application only uses one Bulkhead type, configure the corresponding section properly and be clear about which type is active. Placing both configs in the builder allows switching the default type via property without rewriting the entire policy.

## 4. Per-ID Configuration with configure

When a dependency requires a concurrency limit different from the rest of the application, use configure with the specific ID.

For example, Catalog Service can handle many concurrent read requests, while Payment Service needs tighter limits because each request consumes connections and affects transactions:

~~~java
@Bean
Customizer<Resilience4jBulkheadProvider> perDependencyBulkheads() {
    return provider -> {
        provider.configure(builder -> builder
            .bulkheadConfig(BulkheadConfig.custom()
                .maxConcurrentCalls(40)
                .maxWaitDuration(Duration.ZERO)
                .build())
            .threadPoolBulkheadConfig(ThreadPoolBulkheadConfig.custom()
                .coreThreadPoolSize(6)
                .maxThreadPoolSize(10)
                .queueCapacity(30)
                .keepAliveDuration(Duration.ofSeconds(20))
                .build()),
            "catalog-read");

        provider.configure(builder -> builder
            .bulkheadConfig(BulkheadConfig.custom()
                .maxConcurrentCalls(8)
                .maxWaitDuration(Duration.ZERO)
                .build())
            .threadPoolBulkheadConfig(ThreadPoolBulkheadConfig.custom()
                .coreThreadPoolSize(2)
                .maxThreadPoolSize(4)
                .queueCapacity(4)
                .keepAliveDuration(Duration.ofSeconds(20))
                .build()),
            "payment-authorize");
    };
}
~~~

In this example:

- catalog-read is permitted up to 40 concurrent calls under SemaphoreBulkhead; if ThreadPoolBulkhead is selected, it uses this ID's dedicated pool and queue.
- payment-authorize is permitted at most 8 concurrent calls under SemaphoreBulkhead, or uses the smaller pool when ThreadPoolBulkhead is selected.
- Calls without a specific configuration continue using the configuration from configureDefault.

Values should be calculated based on the actual capacity of the dependency and the application. For example, if there are 5 application instances and each allows 40 concurrent calls to Catalog, total concurrent calls can reach roughly 200. Account for system-wide concurrency, not just the limit on a single instance.

Do not configure the same ID in multiple customizer beans with conflicting limits. When multiple configurations target the same ID, determining the final effective configuration becomes confusing and order-dependent. Maintain a single owner for each ID's policy.

## 5. Linking IDs with CircuitBreakerFactory

Provider configuration is looked up by the ID the application passes to the factory. Example:

~~~java
@Service
public class CatalogService {
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final CatalogClient catalogClient;

    public CatalogService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            CatalogClient catalogClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.catalogClient = catalogClient;
    }

    public Product findProduct(String productId) {
        return circuitBreakerFactory.create("catalog-read").run(
            () -> catalogClient.fetch(productId)
        );
    }
}
~~~

Here, the ID catalog-read is used to look up the corresponding Circuit Breaker and Bulkhead configuration. Calls executed through the factory receive the Bulkhead mechanism supplied by the provider alongside other resilience settings.

If the ID in the provider is catalog-read while the service creates catalog-service, the per-ID configuration will not match. Declare IDs as shared constants:

~~~java
public final class ResilienceIds {
    private ResilienceIds() {}

    public static final String CATALOG_READ = "catalog-read";
    public static final String PAYMENT_AUTHORIZE = "payment-authorize";
}
~~~

Use ResilienceIds.CATALOG_READ in both the configuration and the factory call to avoid typos.

## 6. How Do Default and Specific Configurations Work Together?

A policy typically has three layers:

1. **Default Bulkhead type:** choose Semaphore or FixedThreadPool via Spring Cloud CircuitBreaker configuration.
2. **Baseline configuration:** configureDefault sets general limits for IDs without explicit overrides.
3. **Per-ID configuration:** configure sets distinct limits for a specific dependency.

For instance, the application chooses SemaphoreBulkhead as default and sets a baseline concurrency of 25. The catalog-read ID is raised to 40, while payment-authorize is lowered to 8. All other IDs use the baseline limit.

Do not interpret configureDefault as settings that get added on top of every per-ID configuration. It supplies configuration when no per-ID configuration exists. A per-ID configuration is an independent policy for that ID.

Also distinguish between the two kinds of defaults:

- enableSemaphoreDefaultBulkhead determines which default Bulkhead type Spring Cloud CircuitBreaker uses.
- configureDefault determines the default Bulkhead parameters such as concurrent call count, wait duration, or pool/queue sizes.

These two settings answer two different questions: which mechanism to use, and what limits that mechanism applies.

## 7. Choosing Bulkhead Parameters Based on System Capacity

Do not set concurrency solely from the maximum request rate allowed by an API gateway. Consider:

- **Dependency capacity:** the concurrent requests the target service can serve reliably.
- **Latency:** average and p95/p99 call duration.
- **Caller resources:** threads, connection pools, heap, event loop, and CPU.
- **Instance count:** concurrency limit multiplied by instance count yields total load sent to the dependency.
- **Criticality:** critical dependencies may need a dedicated pool to avoid resource starvation by less critical flows.
- **Time budget:** if the queue waits longer than the request deadline, queuing does not improve user experience.

One rough way to estimate concurrent calls is Little's Law:

~~~text
Average concurrency ≈ Throughput × Latency
~~~

If a dependency receives 100 requests/second and each request takes an average of 0.2 seconds, average in-flight calls are roughly 20. Practical limits need reasonable headroom, yet must stay within the dependency's load tolerance.

With ThreadPoolBulkhead, choose coreThreadPoolSize, maxThreadPoolSize, queueCapacity, and keepAliveDuration based on task characteristics. An overly large pool can spawn too many threads; an overly large queue raises wait times; a queue of 0 or a very small queue enables fast failure but may reject more requests during brief spikes.

With SemaphoreBulkhead, maxConcurrentCalls limits concurrent calls. maxWaitDuration controls slot wait time. If a request has a short deadline, waiting long for a slot may leave insufficient time for the dependency to process it. Set Duration.ZERO to reject immediately when full, or a brief wait matching the time budget.

## 8. Coordinating Bulkhead and Circuit Breaker

Bulkhead and Circuit Breaker protect the system in two different ways:

| Mechanism | Question it answers | Action |
|---|---|---|
| Bulkhead | Is a resource slot available to execute this call? | Permit, wait up to a limit, or reject |
| Circuit Breaker | Is the dependency showing an error or slow-call rate above threshold? | CLOSED allows calls, OPEN rejects, HALF_OPEN probes |

Bulkhead can reject calls even while the dependency is healthy, because the application intentionally caps concurrency. Circuit Breaker can be OPEN even while Bulkhead still has slots available, because the dependency is repeatedly failing or slow. When combining them, monitor Bulkhead rejections and Circuit Breaker not-permitted counts separately.

For example, catalog-read has 40 Bulkhead slots. The dependency begins timing out en masse and the Circuit Breaker transitions to OPEN. New requests are then rejected by the breaker before generating additional load on the dependency. In another scenario, the breaker stays CLOSED, but all 40 slots are in use; Bulkhead rejects new calls to protect the application's own resources.

Do not use Bulkhead as a substitute for timeouts. A call can hold a slot for a very long time if the dependency stops responding. Timeouts are required to free work on schedule and feed outcomes back to the Circuit Breaker.

## 9. Semaphore or ThreadPool for Reactive and Blocking?

Choose the Bulkhead type based on the execution model:

| Call model | Usually suitable choice | Notes |
|---|---|---|
| Non-blocking WebClient and Reactor | SemaphoreBulkhead | Caps subscriptions without switching to a separate thread pool |
| Synchronous/blocking HTTP client | ThreadPoolBulkhead or controlled SemaphoreBulkhead | Isolate blocking I/O and configure client timeouts |
| CPU-bound tasks | Pool sized appropriately for CPU | Avoid creating too many threads or deep queues |
| Dependency with low concurrency quota | SemaphoreBulkhead | Directly limits concurrent calls |
| Need to isolate a legacy blocking task | ThreadPoolBulkhead | Dedicated pool and queue with explicit bounds |

In reactive applications, choosing SemaphoreBulkhead does not mean requests run synchronously on the event loop; it simply caps the number of protected in-flight calls. Avoid calling block() inside the pipeline so the event loop does not stall.

ThreadPoolBulkhead is useful for blocking tasks, but remember it introduces additional threads and a queue. If used with a reactive API, verify the adapter and integration behavior of your Spring Cloud CircuitBreaker version. Do not move every Publisher onto a thread pool solely to enforce a concurrency limit.

## 10. Configuration via application.yml and Provider

Spring Cloud CircuitBreaker Resilience4j supports instance configuration via properties in application.yml. Limits for each ID can be declared in the configuration file:

~~~yaml
spring:
  cloud:
    circuitbreaker:
      resilience4j:
        enableSemaphoreDefaultBulkhead: true

resilience4j:
  bulkhead:
    instances:
      catalog-read:
        maxConcurrentCalls: 40
        maxWaitDuration: 0
      payment-authorize:
        maxConcurrentCalls: 8
        maxWaitDuration: 0

  thread-pool-bulkhead:
    instances:
      catalog-read:
        coreThreadPoolSize: 6
        maxThreadPoolSize: 10
        queueCapacity: 30
      payment-authorize:
        coreThreadPoolSize: 2
        maxThreadPoolSize: 4
        queueCapacity: 4
~~~

This configuration demonstrates enabling SemaphoreBulkhead as the default and declaring instance parameters. When SemaphoreBulkhead is selected, the resilience4j.bulkhead section applies; when FixedThreadPoolBulkhead is used, the resilience4j.thread-pool-bulkhead section applies. Verify property binding and the active provider for the library versions in your project.

You can manage policies via properties or a Java Customizer. If the same ID is configured in both places, understand the precedence rules of your Spring Cloud CircuitBreaker/Resilience4j version and verify the actual effective configuration. Avoid declaring the same limit in multiple places unintentionally.

## 11. Handling When Bulkhead Is Full

When no slots remain, Resilience4j can reject calls with the corresponding exception, such as BulkheadFullException for SemaphoreBulkhead or errors from ThreadPoolBulkhead when the queue/thread pool cannot accept more tasks.

The application should map this condition to a meaningful response:

- Return an overload status or ask the caller to retry later if the API permits.
- Do not retry immediately at the same layer, since slots are still full.
- Do not count a Bulkhead rejection as a dependency failure if the call never reached the dependency.
- Record dedicated metrics for rejection counts and slot utilization.
- Consider shedding load or adjusting limits after reviewing actual capacity.

Example exception handling at the API layer:

~~~java
@ExceptionHandler(BulkheadFullException.class)
ResponseEntity<ApiError> handleBulkheadFull(BulkheadFullException error) {
    ApiError body = new ApiError(
        "DEPENDENCY_CAPACITY_LIMIT",
        "System is busy, please try again later"
    );

    return ResponseEntity.status(503).body(body);
}
~~~

The HTTP status returned to the caller must follow the API contract. If this is an application-local capacity limit, 503 can be appropriate to signal that the service cannot accept additional work right now; some APIs may use 429 when limits apply to a specific caller. Never return 200 with fabricated data just to mask a Bulkhead rejection.

## 12. Verifying BulkheadProvider Configuration

After declaring the provider and IDs, verify step by step:

1. The application starts and the Customizer<Resilience4jBulkheadProvider> bean is loaded.
2. The default Bulkhead type matches the enableSemaphoreDefaultBulkhead property.
3. IDs in configure match IDs passed to CircuitBreakerFactory.create(...).
4. IDs without per-ID configuration use settings from configureDefault.
5. IDs with per-ID configuration receive the configured concurrency or thread-pool sizes.
6. When limits are reached, new calls are rejected or wait for the exact configured duration.
7. When a task completes or times out, the slot is freed and subsequent calls can run.
8. Bulkhead and Circuit Breaker metrics are tracked separately.

A concurrency test can use a latch or barrier to hold in-flight tasks open, then send additional calls past the limit and assert rejection. Avoid relying purely on sleep durations, which easily cause flaky tests. Always release latches in a finally block so tests do not leak threads when assertions fail.

Metrics to monitor include concurrent calls, accepted calls, rejected calls, queued tasks, and wait latency. Compare metrics against real traffic to determine whether limits are too tight or too loose.

## 13. Common Mistakes

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Per-ID config has no effect | ID in provider differs from ID in factory | Use shared ID constants and verify names |
| All dependencies share the same limit | Only default configured, no configure calls declared | Add per-ID configuration for dependencies needing distinct policies |
| Bulkhead rejects too many requests | Concurrency too low, queue too small, or traffic spike | Measure latency and capacity before adjusting |
| Requests wait too long despite Bulkhead | maxWaitDuration or queue too large | Reduce wait time and align with deadlines |
| Thread pool spawns too many threads | maxThreadPoolSize set too high or many instances | Compute total threads across all instances |
| Reactive pipeline stalls | Using blocking I/O or blocking the event loop | Keep non-blocking or properly isolate blocking tasks |
| Cannot distinguish Bulkhead and breaker errors | Combined metrics or generic exception handler | Track Bulkhead rejections and Circuit Breaker not-permitted separately |

## Conclusion

Use BulkheadProvider to manage resource-isolation policies by ID. Choose SemaphoreBulkhead for non-blocking calls that need concurrency limits without creating a separate pool; choose FixedThreadPoolBulkhead when blocking tasks must be isolated in a bounded pool and queue. Use configureDefault as the baseline, configure for dependencies with distinct requirements, and keep IDs consistent with the factory. Combine Bulkhead with timeouts and Circuit Breaker, calculate concurrency across all instances, and track rejections separately so the system fails fast when capacity runs out without triggering cascading failures.
