# Automatic Integration When resilience4j-bulkhead Is on the Classpath

## Lesson Objectives

Spring Cloud CircuitBreaker can automatically integrate Resilience4j's Bulkhead when the resilience4j-bulkhead library is present on the classpath. Thanks to this mechanism, calls created through the CircuitBreaker factory can have their concurrent executions bounded without manually decorating every Supplier with a Bulkhead everywhere.

However, automatic integration does not mean the application automatically knows the right limits. The development team still needs to choose the bulkhead type, set thread or concurrent call limits, decide how rejections are handled, and observe actual load.

After this lesson, you will be able to:

- Explain the classpath condition that activates Spring Cloud CircuitBreaker's Bulkhead integration.
- Recognize the default FixedThreadPoolBulkhead behavior and how to select SemaphoreBulkhead.
- Disable automatic integration when the application does not want the Spring Cloud–provided Bulkhead.
- Configure SemaphoreBulkhead and ThreadPoolBulkhead in application.yml.
- Customize default or per-breaker configuration using Resilience4jBulkheadProvider.
- Distinguish Bulkhead integration for synchronous calls versus reactive pipelines.
- Handle scenarios where the bulkhead rejects calls and monitor resource-isolation effectiveness.

## 1. Condition for Activating Automatic Integration

Spring Cloud CircuitBreaker supports Resilience4j Bulkhead. When the resilience4j-bulkhead dependency is on the classpath, Spring Cloud CircuitBreaker automatically wraps calls made through the Resilience4j implementation with a Bulkhead.

The Maven dependency can be declared as follows if the project does not already pull in this library transitively:

    <dependency>
        <groupId>io.github.resilience4j</groupId>
        <artifactId>resilience4j-bulkhead</artifactId>
    </dependency>

With Gradle:

    implementation("io.github.resilience4j:resilience4j-bulkhead")

The example assumes dependency versions are managed by a BOM compatible with your project's Spring Boot, Spring Cloud, and Resilience4j versions. If dependency management is not yet configured, pick a compatible version set and manage it centrally rather than adding an arbitrary version manually.

Spring Cloud CircuitBreaker provides Resilience4j starters for synchronous and reactive applications:

| Application Model | Starter |
| --- | --- |
| Non-reactive calls | spring-cloud-starter-circuitbreaker-resilience4j |
| Reactive calls with Reactor | spring-cloud-starter-circuitbreaker-reactor-resilience4j |

Do not assume that merely declaring a starter guarantees Bulkhead is enabled in every setup. The integration condition stated in the Spring Cloud documentation is that resilience4j-bulkhead is on the classpath. Inspect the dependency tree or runtime classpath to see whether the library is actually loaded.

Example of a call through the factory:

    CircuitBreaker breaker = circuitBreakerFactory.create("inventory");

    InventoryResponse response = breaker.run(
        () -> inventoryClient.find(sku),
        error -> InventoryResponse.unknown(sku)
    );

When Bulkhead integration is active, Spring Cloud CircuitBreaker applies the bulkhead mechanism to calls executed through the factory. This does not mean every Java method in the application is automatically throttled or bounded. A method is only protected if it flows through the corresponding CircuitBreaker execution path.

## 2. Default Behavior and the Two Bulkhead Types

Resilience4j provides two main implementations:

| Type | Mechanism | Impact |
| --- | --- | --- |
| FixedThreadPoolBulkhead | Uses a fixed thread pool and a bounded queue. | Isolates work in a dedicated pool; bounds thread count and waiting tasks. |
| SemaphoreBulkhead | Uses a semaphore to grant execution permits. | Limits concurrent calls; does not automatically offload work to a separate thread pool. |

With the Spring Cloud CircuitBreaker Resilience4j integration for non-reactive calls, the default is FixedThreadPoolBulkhead. It uses a bounded pool and queue to control how much work can run or wait.

If you want to use SemaphoreBulkhead as the default for non-reactive calls, set:

    spring:
      cloud:
        circuitbreaker:
          resilience4j:
            enableSemaphoreDefaultBulkhead: true

SemaphoreBulkhead checks the remaining permit count. When a permit is available, the call runs on the current thread within the semaphore boundary. When permits are exhausted, the call can be rejected immediately or wait up to the configured duration.

Do not confuse SemaphoreBulkhead with FixedThreadPoolBulkhead. Semaphore only limits concurrency; it does not create a thread pool to offload blocking work. If you need thread and queue isolation, choose a thread-pool bulkhead and size the pool appropriately.

## 3. Disabling Automatic Bulkhead Integration

If the application does not want Spring Cloud CircuitBreaker to apply Bulkhead automatically, you can disable this feature with the property:

    spring:
      cloud:
        circuitbreaker:
          bulkhead:
            resilience4j:
              enabled: false

This property disables Spring Cloud CircuitBreaker's Resilience4j Bulkhead integration. It does not disable the entire circuit breaker, nor does it remove the dependency from the classpath. The circuit breaker can still protect calls as long as CircuitBreaker auto-configuration remains enabled.

Disabling automatic Bulkhead can be appropriate when the application already has its own concurrency-limiting mechanism or is migrating its configuration approach. Before disabling it, verify that another protection layer is in place and measure actual concurrent call counts. Without an alternative safeguard, a slow dependency can consume more threads or connections than expected.

To disable all Resilience4j CircuitBreaker auto-configuration, there is a separate property: spring.cloud.circuitbreaker.resilience4j.enabled=false. Do not use that property if the goal is only to disable Bulkhead.

## 4. Configuring SemaphoreBulkhead via Properties

SemaphoreBulkhead is suitable when you want to cap concurrent calls without creating a dedicated thread pool. Configure instances in application.yml:

    resilience4j:
      bulkhead:
        instances:
          inventory:
            maxConcurrentCalls: 12
            maxWaitDuration: 0

Where:

- maxConcurrentCalls is the maximum number of calls allowed to execute concurrently through the inventory bulkhead.
- maxWaitDuration is the maximum time to wait for a permit once the limit is reached. A value of 0 means no waiting; calls that fail to acquire a permit are rejected immediately.

The instance name inventory must match the id the application passes to factory.create("inventory"). If using the id inventory-read, the configuration must sit under instances.inventory-read.

Example of shared and per-instance configuration:

    resilience4j:
      bulkhead:
        configs:
          default:
            maxConcurrentCalls: 8
            maxWaitDuration: 0
          inventory-policy:
            maxConcurrentCalls: 12
            maxWaitDuration: 100ms
        instances:
          inventory:
            baseConfig: inventory-policy
            maxConcurrentCalls: 10
          pricing:
            baseConfig: default

Configuring instances for each bulkhead allows fine-tuning per dependency. inventory permits up to 10 concurrent calls; pricing inherits the default limit of 8. These values are illustrative only and must be chosen based on dependency capacity, application instance count, and resource budgets.

## 5. Configuring FixedThreadPoolBulkhead via Properties

FixedThreadPoolBulkhead uses a fixed thread pool together with a bounded queue. Example:

    resilience4j:
      thread-pool-bulkhead:
        instances:
          inventory:
            coreThreadPoolSize: 2
            maxThreadPoolSize: 4
            queueCapacity: 10
            keepAliveDuration: 20ms

Key properties:

- coreThreadPoolSize: core thread count of the pool.
- maxThreadPoolSize: maximum number of threads.
- queueCapacity: maximum number of tasks that can wait in the queue.
- keepAliveDuration: how long excess threads are kept when the pool can shrink per configuration.

When all threads are busy and the queue is full, new tasks are rejected. Do not set an overly large queue just to avoid rejections: a long queue increases wait time and can cause requests to expire before they execute.

Size the pool based on blocking duration, dependency capacity, and the application's instance count. For example, if each pod allocates 4 threads to inventory and 6 pods are running, total concurrent calls to inventory can reach roughly 24, excluding other callers. Calculate total load at the system level rather than looking only at a single pod's configuration.

SemaphoreBulkhead and ThreadPoolBulkhead have separate configuration properties. Do not put maxConcurrentCalls under the thread-pool-bulkhead branch or maxThreadPoolSize under the bulkhead branch; properties must match the correct instance type.

## 6. Customizing Default Configuration with a Java Customizer

Spring Cloud CircuitBreaker provides Resilience4jBulkheadProvider to customize Bulkhead and ThreadPoolBulkhead. You can define default configuration across breakers:

    @Bean
    public Customizer<Resilience4jBulkheadProvider> defaultBulkheadCustomizer() {
        return provider -> provider.configureDefault(id ->
            new Resilience4jBulkheadConfigurationBuilder()
                .bulkheadConfig(
                    BulkheadConfig.custom()
                        .maxConcurrentCalls(4)
                        .build()
                )
                .threadPoolBulkheadConfig(
                    ThreadPoolBulkheadConfig.custom()
                        .coreThreadPoolSize(1)
                        .maxThreadPoolSize(2)
                        .build()
                )
                .build()
        );
    }

A default customizer is useful when you want a shared policy across multiple breakers. If dependencies have different capacities, you can configure specifically by id:

    @Bean
    public Customizer<Resilience4jBulkheadProvider> inventoryBulkheadCustomizer() {
        return provider -> provider.configure(
            builder -> builder
                .bulkheadConfig(
                    BulkheadConfig.custom()
                        .maxConcurrentCalls(10)
                        .build()
                )
                .threadPoolBulkheadConfig(
                    ThreadPoolBulkheadConfig.custom()
                        .coreThreadPoolSize(2)
                        .maxThreadPoolSize(4)
                        .build()
                ),
            "inventory"
        );
    }

This example configures both bulkhead types for the id inventory. Which implementation is actually used depends on the factory type and the bulkhead selection configuration. There is no need to configure both types if the application only uses one.

When configuration via properties and a Java Customizer coexist, properties take higher precedence than the Customizer. Specifically for instance and shared configs, the Bulkhead Properties Configuration documentation specifies this precedence order:

1. Instance properties.
2. Configuration from Resilience4JBulkheadProvider Customizer.
3. Shared configs properties.

Consequently, modifying a Java Customizer may have no effect on an instance that already has property-based settings. When troubleshooting, inspect both places and determine which configuration source wins.

## 7. Automatic Integration in Reactive Pipelines

With reactive Spring Cloud CircuitBreaker, Bulkhead is applied via ReactiveResilience4jBulkheadProvider to decorate Mono and Flux. The reactive integration of Spring Cloud CircuitBreaker Resilience4j only uses SemaphoreBulkhead.

This means:

- The reactive pipeline keeps its Mono or Flux publisher type.
- The semaphore caps the number of concurrent subscriptions or calls per the configured bulkhead.
- Bulkhead does not offload the pipeline onto a separate fixed thread pool.
- If the property enableSemaphoreDefaultBulkhead=false is set, the reactive provider still uses SemaphoreBulkhead and logs a warning as documented.

You can customize the reactive bulkhead with a Customizer:

    @Bean
    public Customizer<ReactiveResilience4jBulkheadProvider> reactiveBulkheadCustomizer() {
        return provider -> provider.configureDefault(id ->
            new Resilience4jBulkheadConfigurationBuilder()
                .bulkheadConfig(
                    BulkheadConfig.custom()
                        .maxConcurrentCalls(4)
                        .build()
                )
                .build()
        );
    }

To configure a specific id:

    @Bean
    public Customizer<ReactiveResilience4jBulkheadProvider> inventoryReactiveBulkheadCustomizer() {
        return provider -> provider.configure(builder ->
            builder.bulkheadConfig(
                BulkheadConfig.custom()
                    .maxConcurrentCalls(2)
                    .build()
            ),
            "inventory"
        );
    }

In a reactive pipeline, do not manually call block() to wait for a permit. The provider weaves the operator into the publisher. When active calls reach the limit, new calls can be rejected according to the bulkhead policy.

If you need to invoke a blocking API within a reactive pipeline, SemaphoreBulkhead does not free the event loop by itself. Offload the blocking API with subscribeOn(Schedulers.boundedElastic()) as covered earlier, while using the bulkhead to cap concurrency. Both mechanisms serve distinct roles.

## 8. Combining Bulkhead with CircuitBreaker and Fallbacks

Bulkhead and CircuitBreaker guard two different boundaries:

- Bulkhead caps concurrent tasks or allowed workers/queue capacity.
- CircuitBreaker tracks outcomes, failure rates, and slow calls to transition among CLOSED, OPEN, and HALF_OPEN.

A call can be rejected because bulkhead permits are exhausted even while the circuit breaker is CLOSED. Conversely, the breaker can be OPEN even though the bulkhead still has permits available. Distinguish the rejection cause when handling errors.

Example with CircuitBreakerFactory:

    CircuitBreaker breaker = circuitBreakerFactory.create("inventory");

    InventoryResponse response = breaker.run(
        () -> inventoryClient.find(sku),
        error -> {
            if (error instanceof BulkheadFullException) {
                return InventoryResponse.busy(sku);
            }
            if (error instanceof CallNotPermittedException) {
                return InventoryResponse.unavailable(sku);
            }
            return InventoryResponse.unknown(sku);
        }
    );

InventoryResponse.busy, unavailable, and unknown are application-defined states. This example distinguishes concurrency overload at the dependency from an open circuit breaker. In practice, verify the exact exception types emitted by your Resilience4j implementation and version.

A fallback must be fast and must not call the same constrained dependency again. If the bulkhead rejects due to overload, the fallback can return a busy status, serve still-valid cached data, or ask the caller to retry later. Do not immediately retry inside the fallback, as that adds extra load right when the system lacks capacity.

## 9. Bulkhead Does Not Replace Timeouts or Overall Load Limits

Bulkhead controls concurrent work, but it does not guarantee each unit of work finishes within a reasonable time. A 4-thread pool can still stay tied up for a long time if the HTTP client has no timeout. Combine:

| Mechanism | Responsibility |
| --- | --- |
| Bulkhead | Caps concurrency and resources dedicated to a dependency. |
| Timeout / TimeLimiter | Caps wait time for each supported call or task. |
| CircuitBreaker | Stops sending new calls when a dependency shows sustained failure. |
| Retry | Retries transient failures within limits and with backoff. |

When calculating limits, account for pod count, thread count, queue capacity, connection pools, and downstream limits. If there are 8 pods and each pod allows 10 concurrent inventory calls, potential total load from the application can reach 80 calls. A reasonable per-pod limit can still overwhelm inventory-service overall.

Do not use a large queue capacity to hold every incoming request. Long queues increase latency, tie up resources, and can cause requests to expire before execution. Failing early with an appropriate fallback is usually easier to control than accumulating a backlog that cannot be drained in time.

## 10. Observing and Verifying Automatic Integration

After adding the dependency and configuration, verify that the application actually creates a Bulkhead for the right id:

- Check the dependency tree or runtime classpath for resilience4j-bulkhead.
- Confirm Spring Cloud CircuitBreaker Resilience4j auto-configuration is enabled.
- Check that bulkhead.resilience4j.enabled is not set to false.
- Confirm which bulkhead type is active: FixedThreadPoolBulkhead or SemaphoreBulkhead.
- Verify the instance configuration name matches factory.create(id).
- Generate load exceeding the limit and observe rejected calls.
- Check fallbacks and logs to distinguish BulkheadFullException from CallNotPermittedException.

Resilience4j provides an event publisher to observe Bulkhead events. Spring Cloud CircuitBreaker allows attaching a customizer after the bulkhead is created, for example:

    @Bean
    public Customizer<Resilience4jBulkheadProvider> bulkheadEventCustomizer() {
        return provider -> provider.addBulkheadCustomizer(
            bulkhead -> bulkhead.getEventPublisher()
                .onCallRejected(event -> log.warn("Bulkhead rejected: {}", event))
                .onCallFinished(event -> log.debug("Bulkhead finished: {}", event)),
            "inventory"
        );
    }

Also monitor running call counts, rejected calls, queue utilization for thread-pool bulkheads, wait times, and dependency latency. If the bulkhead rejects frequently under normal load, the limit may be too low or the dependency is running slowly. If the queue is frequently full, review timeouts, concurrency, and downstream service capacity.

## 11. Practice Exercise: Enabling Integration via Classpath

Create a gateway calling inventory-service through Spring Cloud CircuitBreaker and perform these steps:

1. Check whether resilience4j-bulkhead is on the classpath. If missing, add the dependency and let a compatible BOM manage its version.
2. Create a breaker with the id inventory.
3. Run the application with default configuration and identify which bulkhead implementation is selected.
4. Add a SemaphoreBulkhead configuration with maxConcurrentCalls set to 4 and maxWaitDuration set to 0.
5. Generate concurrent load greater than 4 and observe excess calls being rejected.
6. Try configuring FixedThreadPoolBulkhead with a 2-thread pool and queue capacity of 5 in a non-reactive application.
7. Enable enableSemaphoreDefaultBulkhead to switch the synchronous default to SemaphoreBulkhead.
8. Set bulkhead.resilience4j.enabled to false and verify automatic Bulkhead is no longer applied.
9. In a reactive application, use ReactiveResilience4jBulkheadProvider and confirm the pipeline still uses SemaphoreBulkhead.
10. Enable CircuitBreaker and induce consecutive failures to observe Bulkhead and CircuitBreaker rejecting calls for two distinct reasons.

Upon completion, you should be able to explain why the classpath triggers integration, the default bulkhead type for synchronous calls, semaphore behavior in reactive pipelines, and how to configure per id. You should also distinguish Bulkhead from CircuitBreaker, timeout, and retry so you can choose limits suited to each dependency's actual capacity.

## References

- Spring Cloud CircuitBreaker — Bulkhead pattern supporting: https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j/bulkhead-pattern-supporting.html
- Spring Cloud CircuitBreaker — Bulkhead properties configuration: https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j/bulkhead-properties-configuration.html
- Spring Cloud CircuitBreaker — Configuring Resilience4J Circuit Breakers: https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html
