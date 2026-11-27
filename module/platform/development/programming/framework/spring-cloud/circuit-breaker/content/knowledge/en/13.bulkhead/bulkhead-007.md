# Bulkhead in Reactive Applications: Version-Dependent Support

## Why Does Reactive Still Need Bulkhead?

In a Spring WebFlux application, a request is typically processed using a `Mono` or `Flux` pipeline. The non-blocking model keeps threads from blocking on I/O, but it does not automatically cap the number of active requests. When a dependency slows down, many subscriptions can remain active simultaneously, holding onto memory, connections, buffers, and other resources. Without a concurrency limit, a degraded dependency can still exhaust the calling application's resources.

Bulkhead caps the amount of work allowed through a protected region. In reactive applications, the key is limiting concurrent subscriptions or work without blocking the event loop. Resilience4j provides `SemaphoreBulkhead`, which is suited for controlling the number of active calls; `ThreadPoolBulkhead` is meant for running a supplier on a dedicated thread pool, which is typically useful for blocking tasks or legacy synchronous APIs.

Bulkhead and Circuit Breaker solve two different problems:

| Mechanism | Question answered | Effect |
| --- | --- | --- |
| Bulkhead | How many calls are allowed to be active at once? | Caps concurrency and isolates resources. |
| Circuit Breaker | Is the dependency failing or running slowly above a threshold? | Blocks new calls once there is sufficient evidence of dependency degradation. |
| Timeout / TimeLimiter | How long will the application wait for a call at most? | Caps wait duration. |

Combining all three mechanisms limits active subscriptions, detects failing dependencies, and terminates waiting within an appropriate deadline. Bulkhead does not replace timeouts; a call holding a permit for too long can still tie up all concurrency capacity.

## Distinguishing the Two Resilience4j Bulkhead Types

Resilience4j has two main Bulkhead types:

| Type | How it limits | Characteristics in reactive usage |
| --- | --- | --- |
| `SemaphoreBulkhead` | Grants permits for up to `maxConcurrentCalls` concurrent calls. | Can be applied directly to `Mono` or `Flux` with `BulkheadOperator` without switching threads. |
| `ThreadPoolBulkhead` | Runs the supplier on a dedicated pool with bounded threads and queue. | Returns `CompletionStage`; suited for isolating blocking tasks or synchronous suppliers. Should not be used merely to move a non-blocking WebClient pipeline onto another pool. |

With WebFlux and `WebClient`, it is usually best to start with `SemaphoreBulkhead`. It caps the number of subscriptions entering the pipeline while I/O remains reactive. Choose `ThreadPoolBulkhead` when you need to isolate a blocking library, such as legacy JDBC or a synchronous HTTP client, so blocking work does not execute on the event loop.

## Support Depends on Stack and Version

There are three layers to distinguish when evaluating reactive support:

1. **Spring Cloud Circuit Breaker abstraction:** provides `ReactiveCircuitBreakerFactory` and `ReactiveCircuitBreaker` to create and run circuit breakers on `Mono` or `Flux`.
2. **Resilience4j Reactor integration:** provides reactive operators such as `CircuitBreakerOperator` and `BulkheadOperator` to compose directly with Reactor publishers.
3. **Starter auto-configuration:** determines which factory is created, which default configuration is applied, and whether Bulkhead is attached automatically to calls.

Do not infer that having `ReactiveCircuitBreakerFactory` guarantees Bulkhead is active in the pipeline. The abstraction contract and auto-configuration behavior can vary across Spring Cloud release trains, Spring Boot versions, imperative/reactive starters, and Resilience4j configuration. Some combinations provide Bulkhead integration at the factory; others require the application to apply the operator directly.

Before implementing, verify the exact version in use:

- Confirm the application uses WebFlux/Reactor and the appropriate reactive starter.
- Inspect the runtime dependency graph for the Resilience4j Reactor module (`resilience4j-reactor`) and required Bulkhead artifacts.
- Read the Spring Cloud Circuit Breaker documentation for your exact release train to check whether the reactive factory applies Bulkhead automatically and which default Bulkhead type it selects.
- Verify configuration properties for your exact version instead of copying properties from another release train.
- Confirm runtime behavior via metrics: active concurrent calls, rejection counts, and Circuit Breaker state.

If the starter already applies Bulkhead automatically, do not accidentally add a second `BulkheadOperator`. Two stacked limiters can create two different thresholds, reducing effective capacity and making rejection errors harder to explain. If the abstraction does not expose the reactive Bulkhead configuration you need, you can create a `SemaphoreBulkhead` and apply it manually in the pipeline as shown next.

## Applying SemaphoreBulkhead to Mono

Example creating a Bulkhead that caps concurrent subscriptions to the `catalog` dependency at 24:

```java
import java.time.Duration;

import io.github.resilience4j.bulkhead.Bulkhead;
import io.github.resilience4j.bulkhead.BulkheadConfig;
import io.github.resilience4j.reactor.bulkhead.operator.BulkheadOperator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CatalogBulkheadConfiguration {

    @Bean
    Bulkhead catalogBulkhead() {
        BulkheadConfig config = BulkheadConfig.custom()
            .maxConcurrentCalls(24)
            .maxWaitDuration(Duration.ZERO)
            .build();

        return Bulkhead.of("catalog", config);
    }
}
```

`maxConcurrentCalls` sets the limit on calls granted a permit. `maxWaitDuration(Duration.ZERO)` requests immediate rejection when no permit is left rather than holding a thread waiting. In a reactive pipeline, do not use long wait times in a way that blocks the event loop. The value 24 is only an example; choose it based on connection pools, dependency capacity, memory limits, and latency targets.

Applying the operator to a `Mono`:

```java
Mono<CatalogItem> item = webClient.get()
    .uri("/catalog/{id}", productId)
    .retrieve()
    .bodyToMono(CatalogItem.class)
    .transformDeferred(BulkheadOperator.of(catalogBulkhead));
```

`transformDeferred` creates decoration per subscription. A permit is acquired when a subscription passes through the Bulkhead and released when the publisher completes or the subscription is cancelled per the operator's lifecycle. When permits run out, the publisher emits a Bulkhead rejection error, typically `BulkheadFullException`. The caller must decide how to map this overload error to an appropriate response.

With `Flux`, the application is similar:

```java
Flux<CatalogItem> items = webClient.get()
    .uri("/catalog")
    .retrieve()
    .bodyToFlux(CatalogItem.class)
    .transformDeferred(BulkheadOperator.of(catalogBulkhead));
```

Bulkhead limits subscriptions to the pipeline, not the number of items emitted by a `Flux`. One subscription can emit many items while still holding a single permit until it completes or is cancelled. If you need to cap the number of elements processed concurrently within a stream, consider `flatMap` with an appropriate `concurrency`; that is a different limit from a dependency Bulkhead.

## Combining with ReactiveCircuitBreakerFactory

If Spring Cloud Circuit Breaker provides `ReactiveCircuitBreakerFactory`, the application can use that abstraction for the circuit breaker and place the Bulkhead operator outside the protected publisher:

```java
import io.github.resilience4j.bulkhead.BulkheadFullException;
import io.github.resilience4j.reactor.bulkhead.operator.BulkheadOperator;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import reactor.core.publisher.Mono;

public Mono<CatalogView> find(String productId) {
    Mono<CatalogView> primary = webClient.get()
        .uri("/catalog/{id}", productId)
        .retrieve()
        .bodyToMono(CatalogItem.class)
        .map(CatalogView::available);

    Mono<CatalogView> protectedByCircuitBreaker =
        reactiveCircuitBreakerFactory.create("catalog").run(
            primary,
            error -> Mono.just(CatalogView.unavailable(productId))
        );

    return protectedByCircuitBreaker
        .transformDeferred(BulkheadOperator.of(catalogBulkhead))
        .onErrorResume(BulkheadFullException.class,
            error -> Mono.just(CatalogView.overloaded()));
}
```

In this example, the Bulkhead sits outside the Circuit Breaker–wrapped publisher. When permits are exhausted, the Bulkhead rejects the subscription before the Circuit Breaker pipeline starts; the rejection error is handled separately with `onErrorResume`. As a result, the calling application running out of concurrency capacity is not miscounted as a dependency error. `CatalogView.overloaded()` signals that the application is currently overloaded; it differs from `CatalogView.unavailable()`, which is used when the primary call fails.

This is a manual composition approach when the factory does not automatically attach the desired Bulkhead. If your starter version already integrates Bulkhead, choose one place to own the policy and avoid double-wrapping. If you want the Circuit Breaker to record Bulkhead rejections as well, explicitly configure the predicate and understand that the failure rate will then reflect caller-side overload, not just dependency health.

## Why Should You Not Block Waiting for a Permit?

Reactor executes callbacks on schedulers and event loops. If an event-loop thread blocks waiting for a semaphore or waiting on a synchronous task, that thread cannot serve other subscriptions. This defeats the non-blocking model and can create a bottleneck inside the calling application itself.

With `SemaphoreBulkhead`, wait configuration should be short and usually fail-fast. Do not call `block()` to wait for a publisher to obtain a permit; let the rejection error flow through the reactive pipeline and map it to an overload response. If business requirements call for queuing, use a bounded queue and an explicitly designed backpressure mechanism rather than stalling the event loop waiting for a permit.

## When to Use ThreadPoolBulkhead?

`ThreadPoolBulkhead` is useful when you must call a blocking API that cannot yet be migrated to reactive. It runs the supplier on a dedicated thread pool and returns a `CompletionStage`; the result can be converted to a `Mono`:

```java
import java.util.concurrent.CompletionStage;

import io.github.resilience4j.bulkhead.ThreadPoolBulkhead;
import reactor.core.publisher.Mono;

public Mono<CatalogItem> findLegacy(String productId) {
    CompletionStage<CatalogItem> stage = threadPoolBulkhead.executeSupplier(
        () -> blockingCatalogClient.find(productId)
    );

    return Mono.fromCompletionStage(stage);
}
```

`blockingCatalogClient.find` runs on the pool managed by ThreadPoolBulkhead, not directly on the event loop. Bound `coreThreadPoolSize`, `maxThreadPoolSize`, and `queueCapacity`; the queue must be bounded so pressure cannot accumulate indefinitely. When the pool and queue are full, calls are rejected and the application must handle the overload error.

Do not use `ThreadPoolBulkhead` to wrap an already non-blocking `WebClient` call just to "add more asynchronicity." Switching to another pool introduces extra threads, queuing, and context propagation to manage without improving I/O. For a reactive API, `SemaphoreBulkhead` is usually the simpler choice.

Cancelling a reactive subscription does not necessarily stop a blocking task that has already started on the thread pool. Therefore, still configure timeouts on the blocking HTTP client, bound wait durations, and handle late results. Do not rely on the caller cancelling the `Mono` to guarantee that the operation on the target system has stopped.

## Configuration via Spring Cloud and Resilience4j

Resilience4j allows configuring Bulkhead instances by name. Example semaphore bulkhead configuration in `application.yml`:

```yaml
resilience4j:
  bulkhead:
    instances:
      catalog:
        maxConcurrentCalls: 24
        maxWaitDuration: 0ms
```

For ThreadPoolBulkhead, configuration lives under the `thread-pool-bulkhead` section:

```yaml
resilience4j:
  thread-pool-bulkhead:
    instances:
      legacyCatalog:
        coreThreadPoolSize: 4
        maxThreadPoolSize: 8
        queueCapacity: 16
        keepAliveDuration: 20ms
```

Properties and how the starter binds instances to the factory can vary by version. Cross-check the configuration schema and documentation for your exact release train. If you retrieve `Bulkhead` directly from a registry and apply `BulkheadOperator`, make sure the instance name and registry policy match operational intent; do not let the factory simultaneously create another Bulkhead for the same call unintentionally.

## Choosing Concurrency Limits

Do not base `maxConcurrentCalls` solely on the machine's thread count. With WebClient, each request may not occupy its own thread, yet it still consumes connections, buffers, memory, and server-side processing capacity. Base the limit on:

- HTTP client connection limits and how many requests can run concurrently per connection.
- Actual processing capacity and concurrency limits published by the dependency.
- Target response time and latency growth as load increases.
- Response payload sizes, in-memory buffered data, and concurrent subscription count.
- Application instance count. If each instance has its own Bulkhead, total load can equal the per-instance limit multiplied by the instance count.

For example, if each instance permits 24 calls and the system runs 5 instances, the dependency can receive up to roughly 120 concurrent calls from this service alone, excluding other callers. Compute system-wide limits and allocate concurrency budgets per dependency.

## Observing and Handling Rejection Errors

Monitor Bulkhead metrics alongside Circuit Breaker metrics:

- Calls currently holding permits and remaining available permits.
- Calls rejected due to no available permits.
- Permit hold time and publisher latency.
- Subscriptions cancelled before completion.
- Circuit Breaker errors, calls rejected while `OPEN`, and dependency failure rate.

`BulkheadFullException` and `CallNotPermittedException` carry different meanings. The first indicates the Bulkhead's concurrency limit is exhausted; the second indicates the Circuit Breaker is blocking calls. You can map them to distinct overload and temporary dependency-unavailable responses so logs, metrics, and clients understand the true cause.

Do not put user IDs, request IDs, or exception messages into metric tags. Use a bounded set of reason tags such as `bulkhead_full`, `circuit_open`, `timeout`, and `dependency_error`; keep detailed diagnostics in logs or traces with correlation IDs.

## Testing Against the Deployed Version

Before going to production, build a simulated dependency that can delay responses and send many concurrent subscriptions. Verify these scenarios:

| Scenario | Expected outcome |
| --- | --- |
| Subscription count below limit | All are granted permits and execute normally. |
| Subscription count exceeds limit | Excess subscriptions are rejected or wait strictly per `maxWaitDuration`. |
| Publisher completes | Permit is released so the next subscription can proceed. |
| Subscription is cancelled | Permit is released according to operator semantics; verify via actual tests. |
| Circuit Breaker `OPEN` | Calls are rejected by the Circuit Breaker and never reach the dependency. |
| Bulkhead full while Circuit Breaker `CLOSED` | Calls are rejected by the Bulkhead; verify this does not inadvertently inflate dependency failure rate unless intended. |
| Using ThreadPoolBulkhead for blocking client | Work executes on the dedicated pool, queue is bounded, and the event loop is not blocked. |

To verify version-specific support, inspect the dependency graph, auto-configuration report, and runtime behavior. Seeing a `ReactiveCircuitBreakerFactory` bean alone is not enough to conclude Bulkhead is applied. Confirm that the operator or factory actually caps subscriptions, rejects when permits are exhausted, and releases permits after completion or cancellation.

## Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Assuming reactive automatically limits concurrency. | Many subscriptions can hold resources simultaneously and cause overload. | Use Bulkhead or appropriate concurrency limits. |
| Assuming `ReactiveCircuitBreakerFactory` always includes Bulkhead automatically. | The pipeline may have no concurrency limit at all. | Verify the right starter, release train, and runtime configuration. |
| Applying both auto Bulkhead and manual `BulkheadOperator`. | Two stacked limiters reject earlier than expected. | Designate a single policy owner or document why multiple layers are needed. |
| Waiting for permits by blocking the event loop. | Stalls other subscriptions. | Fail fast or use a bounded reactive queue. |
| Using ThreadPoolBulkhead for non-blocking WebClient. | Adds unnecessary thread hops and queuing. | Prefer SemaphoreBulkhead operator for reactive pipelines. |
| Treating BulkheadFullException as a dependency failure. | Failure rate can rise because the caller ran out of capacity. | Separate Bulkhead rejections from dependency errors in metrics and predicates. |
| Calculating limits for a single instance only. | Combined concurrency across instances exceeds dependency capacity. | Multiply limits by instance count and account for other callers in the system. |

Reactive Bulkhead can protect an application while preserving a non-blocking pipeline, though exact integration depends on the starter and version. Verify `ReactiveCircuitBreakerFactory` behavior, check the Resilience4j Reactor operator when applying manually, choose SemaphoreBulkhead for reactive subscriptions, and reserve ThreadPoolBulkhead for blocking tasks that require isolation. By separating concurrency limits from dependency failures, the system can control overload without distorting Circuit Breaker metrics.
