# Fallback Always Runs Due to Default TimeLimiter or Full Queue

When an endpoint repeatedly returns a fallback response even though the downstream service is healthy, the cause may lie in caller-side protection policies. Two common causes are TimeLimiter using a default timeout shorter than actual response times, or ThreadPoolBulkhead running out of both workers and queue slots. Either can route calls to the fallback before the caller receives a normal result.

You must distinguish between these two scenarios. A timeout usually means the task started but did not finish within the deadline. A full queue usually means the new task was rejected before the original Supplier ran. Looking only at the fallback response leads teams to conclude the dependency is failing or the Circuit Breaker is OPEN, when the actual cause is a local timeout or concurrency limit.

This lesson explains how to trace the effective TimeLimiter configuration, recognize queue saturation, read exceptions and events, tune timeouts and thread pools, and write tests verifying that the fallback only triggers under the intended conditions.

## 1. Why Can a Fallback Appear on Every Request?

A fallback is an alternative execution branch invoked when a protected call ends with an error that the adapter forwards to the fallback function. That error does not necessarily originate from the remote service.

A call can enter the fallback because:

- The Circuit Breaker is OPEN and rejects the request with `CallNotPermittedException`.
- TimeLimiter exceeds its wait duration and raises a timeout.
- ThreadPoolBulkhead cannot accept the task because workers and the queue are full.
- Semaphore Bulkhead is out of permits.
- The HTTP client encounters a connection or response error.
- Code inside the Supplier itself throws an exception.

Therefore, fallback execution does not prove the Circuit Breaker is OPEN. The Circuit Breaker may still be CLOSED while TimeLimiter or Bulkhead rejects the call. If the fallback always executes, inspect the original exception and each policy's events before modifying failure rate thresholds.

~~~mermaid
flowchart TD
    A[Request enters Circuit Breaker] --> B{Admission and state}
    B -- Circuit Breaker OPEN --> C[CallNotPermittedException]
    B -- Bulkhead queue full --> D[BulkheadFullException]
    B -- Accepted --> E[Supplier starts]
    E --> F{Completes within timeout?}
    F -- No --> G[TimeoutException]
    F -- Yes --> H[Result or HTTP error]
    C --> I[Fallback]
    D --> I
    G --> I
    H --> J{Successful outcome?}
    J -- No --> I
    J -- Yes --> K[Return original result]
~~~

The diagram shows three distinct rejection causes that can all lead to the fallback. Diagnose by error type and actual state, not solely by the response body.

## 2. Identify Fallbacks Caused by TimeLimiter

TimeLimiter bounds how long the caller waits for an asynchronous operation to complete. If the operation exceeds `timeoutDuration`, the call is treated as a timeout and the fallback may be invoked.

For example, the inventory service typically responds in 1.5 seconds, but the effective TimeLimiter configuration only permits 1 second. Most requests will time out even though Inventory Service returns valid responses after 1.5 seconds.

Common symptoms:

- The Supplier or HTTP task has started.
- Logs show the call start timestamp without a result before the deadline.
- Exceptions or events indicate a timeout.
- The elapsed time until the caller receives the fallback closely matches `timeoutDuration`.
- Background tasks or HTTP requests may keep running after the caller receives the fallback, depending on the cancellation mechanism.

An explicit configuration example:

~~~yaml
resilience4j:
  timelimiter:
    instances:
      inventory:
        timeoutDuration: 3s
        cancelRunningFuture: true
~~~

In this example, the caller waits at most three seconds for the operation under instance `inventory`. `cancelRunningFuture` requests cancelling the Future on timeout. Whether cancellation actually stops the running work depends on the Future, executor, and HTTP client; do not treat this property as a guarantee that the server has stopped processing.

## 3. Check the Effective Timeout Instead of Just Reading Config Files

An application may omit `timeoutDuration` for an instance and still inherit a timeout from a default configuration. Effective values can come from:

- Library or adapter defaults.
- The `configs/default` configuration group.
- Specific instances in `application.yml`.
- A Java Customizer configuring defaults on the factory.
- A Java Customizer configuring a specific ID.
- The active profile or externally loaded environment configuration.

Exact defaults vary by version and integration approach. Do not assume every Spring Cloud CircuitBreaker application shares the same default timeout. Check dependency versions, active profiles, and the instance configuration actually used by the factory.

Example defining a default config and an instance-specific override for `inventory`:

~~~yaml
resilience4j:
  timelimiter:
    configs:
      default:
        timeoutDuration: 4s
        cancelRunningFuture: true
    instances:
      inventory:
        baseConfig: default
        timeoutDuration: 6s
      payment:
        baseConfig: default
        timeoutDuration: 2s
~~~

In this configuration, `inventory` has a six-second timeout and `payment` has a two-second timeout; both inherit the `cancelRunningFuture` policy from `default`.

If a Java Customizer also configures TimeLimiter, verify the ordering and precedence rules between customizers and properties for your version. Do not simply edit a YAML file and assume the new value is guaranteed to take effect.

Log the breaker ID, expected timeout, and actual duration at startup or in configuration metrics. When needed, enable Spring Boot's configuration inspection endpoint in a protected environment and verify the bound properties. Never expose administrative endpoints or sensitive configuration details to the public Internet.

## 4. Configure TimeLimiter in Java

Spring Cloud CircuitBreaker with Resilience4j allows configuration via `Resilience4JConfigBuilder`:

~~~java
import java.time.Duration;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.timelimiter.TimeLimiterConfig;

import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JConfigBuilder;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CircuitBreakerConfiguration {

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> inventoryTimeout() {
        return factory -> factory.configure(
                builder -> builder
                        .timeLimiterConfig(
                                TimeLimiterConfig.custom()
                                        .timeoutDuration(Duration.ofSeconds(6))
                                        .cancelRunningFuture(true)
                                        .build()
                        )
                        .circuitBreakerConfig(
                                CircuitBreakerConfig.ofDefaults()
                        )
                        .build(),
                "inventory"
        );
    }
}
~~~

This configuration sets a six-second timeout for ID `inventory`. If the inventory call has a p99 response time around four seconds, six seconds can be a reasonable starting point to evaluate; also factor in the outer request deadline and budget for downstream steps.

You can set a default configuration for all IDs via `configureDefault`, then customize IDs with different SLAs individually. Avoid forcing an overly short timeout across every dependency simply because one dependency responds quickly.

TimeLimiter is normally applied explicitly to `Future`- or `CompletionStage`-based calls. For synchronous APIs returning `T` directly and reactive `Mono`/`Flux` calls, how the adapter enforces time limits can differ. Verify the exact overload and implementation in use before concluding which TimeLimiter wraps the call.

## 5. Distinguish Caller Timeout from Actual HTTP Duration

Example of a call returning a `CompletionStage`:

~~~java
CompletionStage<Inventory> result = circuitBreaker.run(
        () -> CompletableFuture.supplyAsync(
                () -> inventoryClient.fetch(sku),
                inventoryExecutor
        ),
        error -> CompletableFuture.completedFuture(
                Inventory.unavailable(sku)
        )
);
~~~

TimeLimiter can complete the caller branch with a timeout when the `CompletionStage` fails to finish within the deadline. However, `CompletableFuture.cancel(true)` does not guarantee interrupting a running computation. The HTTP client may also continue performing I/O if cancellation does not propagate to the transport.

During investigation, record at least three milestones:

1. Supplier or HTTP request starts.
2. Caller receives timeout and fallback.
3. Background task or HTTP response actually finishes.

If milestone 2 occurs before milestone 3, work continues running after the timeout. This can exhaust thread pools and connection pools even though callers have already received fallbacks.

Do not retry immediately merely because the caller timed out unless you have determined whether the previous request was already processed by the server. For order creation or payment operations, use idempotency keys and status lookup mechanisms to avoid duplicate side effects.

## 6. Identify Fallbacks Caused by a Full ThreadPoolBulkhead Queue

`ThreadPoolBulkhead` limits the number of tasks that can run concurrently and the number allowed to wait. When all workers are busy and the queue reaches `queueCapacity`, new tasks are rejected.

Example configuration:

~~~yaml
resilience4j:
  thread-pool-bulkhead:
    instances:
      inventory:
        coreThreadPoolSize: 4
        maxThreadPoolSize: 8
        queueCapacity: 12
        keepAliveDuration: 20ms
~~~

In this example:

- The pool maintains at least four workers.
- The pool can scale up to eight workers.
- At most twelve tasks can be queued per `queueCapacity`.
- When workers are busy and the queue is full, new tasks can be rejected with `BulkheadFullException`.

A task rejected due to a full queue has usually never started executing. Consequently, a counter placed inside the Supplier may remain at 0 while the fallback is invoked immediately.

Common symptoms:

- The fallback appears very quickly, shorter than `timeoutDuration`.
- The exception is `BulkheadFullException` or the adapter's corresponding rejection error.
- Queue depth reaches `queueCapacity`.
- Active workers stay near `maxThreadPoolSize`.
- The original Supplier does not start for rejected requests.
- The remote service may still be healthy, yet the caller has no local slot to dispatch requests.

This indicates overload or admission-control limits on the caller application. Increasing `timeoutDuration` does not resolve a full queue. Increasing `queueCapacity` does not make the dependency faster either; it merely allows more requests to wait and can increase latency.

## 7. Distinguish ThreadPoolBulkhead from Semaphore Bulkhead

Not every Bulkhead has a queue:

| Mechanism | Bounded Resource | When Limit Is Reached |
|---|---|---|
| ThreadPoolBulkhead | Worker threads and task queue | Rejects when both workers and queue are full |
| Semaphore Bulkhead | Number of concurrent call permits | Rejects or waits for a permit per `maxWaitDuration` |
| HTTP connection pool | Connections and pending acquire requests | Waits for a connection or raises acquire timeout/rejection |

If the application uses a Semaphore Bulkhead, there is no worker queue like `ThreadPoolBulkhead`. Rejection errors can still trigger the fallback, but the cause is permit exhaustion rather than `queueCapacity`.

Spring Cloud CircuitBreaker with Resilience4j can select a default Bulkhead implementation depending on configuration and version. Some versions let you enable Semaphore Bulkhead by default via property:

~~~yaml
spring:
  cloud:
    circuitbreaker:
      resilience4j:
        enableSemaphoreDefaultBulkhead: true
~~~

Confirm whether this property is supported in your Spring Cloud version. When Semaphore Bulkhead is enabled, thread-pool settings like `coreThreadPoolSize` and `queueCapacity` are no longer the default limiting mechanism for that call.

Do not tune `queueCapacity` when the application is actually using Semaphore Bulkhead. First verify which Bulkhead type is created for that ID.

## 8. Read Exceptions and Events to Distinguish the Two Causes

Record the exception types and events emitted by each policy. The following table serves as a diagnostic guide; exact wrapper or exception names may vary by adapter and version:

| Indicator | TimeLimiter Timeout | ThreadPoolBulkhead Full Queue |
|---|---|---|
| Typical exception | `TimeoutException` or timeout wrapper | `BulkheadFullException` or rejection exception |
| Did Supplier start? | Usually yes | Usually no for rejected tasks |
| Time to fallback | Close to `timeoutDuration` | Usually very fast once queue is full |
| Queue depth | May be normal | Reaches `queueCapacity` |
| Active workers | May be normal or high | Usually at limit |
| HTTP request | May have been sent | Usually not sent for rejected tasks |
| Primary remediation | Tune deadline or reduce latency | Tune concurrency, pool, queue, and admission control |

You can register listeners on Circuit Breaker and Bulkhead to record events. Example with Resilience4j core:

~~~java
bulkhead.getEventPublisher()
        .onCallRejected(event ->
                log.warn("Bulkhead rejected call: name={}",
                        event.getBulkheadName()));

circuitBreaker.getEventPublisher()
        .onCallNotPermitted(event ->
                log.warn("Circuit breaker rejected call: name={}",
                        event.getCircuitBreakerName()));
~~~

For `ThreadPoolBulkhead`, use the event publisher and metrics of the running implementation to track accepted, completed, and rejected tasks. Specific listener APIs differ from Semaphore Bulkhead; use the interface matching the instance type.

For TimeLimiter, monitor timeout counts and `CompletionStage` completion duration. Attach an operation ID or correlation ID to link logs from call start to fallback and actual background task completion.

## 9. Check Policy Ordering and Local Errors

Decorators can be composed in different orders depending on the factory, customizer, and implementation. Ordering dictates which layer receives an exception first and which metric records the failure.

For example, a Bulkhead rejection is a local admission-control failure. It does not necessarily prove Inventory Service is down. If a Bulkhead exception enters the Circuit Breaker and gets recorded as a remote failure, the failure rate can climb and trip the breaker to OPEN even while the dependency is healthy.

Check the following:

- Whether Bulkhead is applied before or after Circuit Breaker.
- Whether TimeLimiter starts timing before or after the task enters the queue.
- Whether `BulkheadFullException` is recorded as a failure by the Circuit Breaker or ignored.
- Which layer attaches the fallback.
- Whether Retry retries full-queue errors or `CallNotPermittedException`.

Do not immediately retry a `BulkheadFullException`. Retrying can add even more waiting tasks and make queue recovery harder. Likewise, do not retry `CallNotPermittedException` while the breaker is OPEN, because calls will continue to be rejected.

If you do not want local errors to affect the remote dependency's failure rate, adjust decorator ordering or exception classification per your version's API. Verify via events and metrics rather than relying solely on YAML declaration order.

## 10. Tune Timeouts According to Latency and Deadlines

Timeouts should be chosen based on SLAs and actual latency distributions. Never set a timeout equal to average latency, because a significant share of requests will be slower than the mean.

A practical approach:

1. Measure p50, p95, and p99 of the dependency under normal and peak load.
2. Identify the overall deadline the caller must satisfy.
3. Reserve budget for steps before and after the dependency call.
4. Set HTTP client and TimeLimiter timeouts within the remaining budget.
5. Test when the dependency is slower than the timeout to observe fallback and cancellation.
6. Monitor timeout rates after deployment and refine based on data.

For instance, suppose the caller has a 5-second deadline. If validation and response processing need around 500 ms, the dependency budget is roughly 4 seconds. If Retry introduces wait intervals, total retry time must also fit inside this budget.

Align timeouts across layers. Connect timeout, response timeout, read timeout, and TimeLimiter do not measure the same span. If TimeLimiter is shorter than the HTTP client timeout, the caller can receive a fallback while the HTTP request keeps running.

## 11. Tune ThreadPoolBulkhead and queueCapacity

The pool needs enough workers to handle target concurrency without exceeding the dependency's load capacity and JVM resources.

A tuning workflow:

- Measure average and p95/p99 task processing duration.
- Estimate required concurrency from traffic rate and latency.
- Set `coreThreadPoolSize` and `maxThreadPoolSize` within the application's thread budget.
- Set a finite `queueCapacity` aligned with the caller deadline.
- Monitor queue wait time, queue depth, and rejection count.
- Verify the HTTP connection pool has enough capacity for the active worker count.
- Shrink the queue or reject early if requests waiting too long will expire before running.

Average concurrency can be estimated using Little's Law:

\[
L = \lambda \times W
\]

If a dependency receives 30 requests per second and each request takes 200 ms on average:

\[
L = 30 \times 0.2 = 6
\]

That yields roughly six concurrent calls on average. This is only a starting point; factor in latency variance and burst traffic when sizing the pool. Do not increase `maxThreadPoolSize` indefinitely, because extra threads raise context switching, stack memory usage, and downstream pressure.

The queue should hold only as many tasks as can finish within the deadline. An oversized queue makes requests wait a long time only to time out anyway, triggering the fallback while tying up resources for extended periods.

## 12. Combine TimeLimiter with ThreadPoolBulkhead

When both TimeLimiter and ThreadPoolBulkhead are enabled, a task can encounter two distinct conditions:

- Rejected from entering the pool because the queue is full.
- Accepted into the pool but failing to complete within the deadline.

These two conditions produce different exceptions and should be monitored separately.

Example dependency-scoped configuration:

~~~yaml
resilience4j:
  timelimiter:
    instances:
      inventory:
        timeoutDuration: 4s
        cancelRunningFuture: true

  thread-pool-bulkhead:
    instances:
      inventory:
        coreThreadPoolSize: 6
        maxThreadPoolSize: 10
        queueCapacity: 8
        keepAliveDuration: 20ms
~~~

This configuration is illustrative. If the queue is full, tasks can be rejected immediately without waiting four seconds. If a task is accepted but takes longer than four seconds, TimeLimiter can trigger the fallback.

Test both paths explicitly:

- Saturate all workers and fill the queue to verify rejection.
- Allow a task to be accepted while deliberately running slower than the timeout to verify timeout handling.

Do not write a single generic test that only asserts the fallback was called. Assert the exception type, whether the Supplier started, queue state, and response duration.

## 13. Checking Reactive Applications

With WebFlux and Reactor, verify how the reactive adapter actually applies timeouts and Bulkheads. Reactive pipelines typically do not use `ThreadPoolBulkhead` to schedule every WebClient request; Semaphore Bulkhead and Reactor operators are better suited for non-blocking concurrency limits.

Example of a direct timeout on a `Mono`:

~~~java
Mono<Inventory> remoteCall = webClient.get()
        .uri("/inventory/{sku}", sku)
        .retrieve()
        .bodyToMono(Inventory.class)
        .timeout(Duration.ofSeconds(3));

return reactiveCircuitBreaker.run(
        remoteCall,
        error -> Mono.just(Inventory.unavailable(sku))
);
~~~

Here, the Reactor timeout emits an error signal if the publisher does not emit a result within the deadline. `ReactiveCircuitBreaker`'s fallback can catch that error. Verify where the timeout sits in the chain and whether the adapter adds a separate TimeLimiter to avoid two competing timeouts.

If using a Semaphore Bulkhead for reactive calls, monitor rejected permits. If using `ThreadPoolBulkhead` to run blocking tasks, isolate the blocking section and bound its workers; do not offload an entire WebClient pipeline onto a thread pool just to work around queue saturation.

For reactive flows, distinguish between:
- Publisher not subscribed due to policy rejection.
- Publisher subscribed but emitting a timeout.
- Publisher cancelled after caller timeout.
- HTTP exchange cancelled vs. server continuing to process.

These cases have different resource implications and require separate metrics.

## 14. Tests to Pinpoint the Exact Cause

Write two independent tests.

### TimeLimiter Test

- Create a `CompletionStage` whose completion time exceeds `timeoutDuration`.
- Increment a counter when the Supplier starts.
- Record the timestamp when the caller receives the fallback.
- Verify the exception or event is a timeout.
- Verify the Supplier started.
- Observe whether the background task keeps running after the fallback.

Mock example:

~~~java
AtomicInteger supplierCalls = new AtomicInteger();

CompletionStage<String> result = circuitBreaker.run(
        () -> CompletableFuture.supplyAsync(() -> {
            supplierCalls.incrementAndGet();
            sleepUninterruptiblyForTest(Duration.ofSeconds(5));
            return "remote-result";
        }, executor),
        error -> CompletableFuture.completedFuture("fallback")
);
~~~

This is a conceptual example; a helper like `sleepUninterruptiblyForTest` should exist only in tests. Use a dedicated executor and controllable timing so the test does not depend on machine load. Do not use this mock snippet in production.

### Full ThreadPoolBulkhead Queue Test

- Configure one worker and a queue capacity of one.
- Hold the first worker with a latch.
- Submit a second task to fill the queue.
- Submit a third task and verify it is rejected.
- Place a counter inside the third Supplier and verify it remains 0.
- Verify the fallback is called due to the rejection error.
- Release the latch and clean up the executor after the test.

~~~java
CountDownLatch releaseWorker = new CountDownLatch(1);
AtomicInteger rejectedSupplierCalls = new AtomicInteger();

CompletableFuture<String> first = submit(() -> {
    releaseWorker.await();
    return "first";
});

CompletableFuture<String> second = submit(() -> "second");

CompletableFuture<String> third = submit(() -> {
    rejectedSupplierCalls.incrementAndGet();
    return "third";
});

// Verify the third task is rejected and the third Supplier has not executed.
releaseWorker.countDown();
~~~

The `submit` helper in the example represents a call passing through the configured `ThreadPoolBulkhead`. In a real test, use the factory API or `ThreadPoolBulkhead` instance and synchronize with latches to ensure the worker and queue are in the desired state before submitting the third task.

Do not use `Thread.sleep` to guess when the queue is full. Use latches, barriers, or event signals to control ordering. Clean up resources in `finally` so tests do not leave hanging workers behind.

## 15. Diagnostic Checklist When Fallback Always Runs

When the fallback runs on almost every request, collect evidence in order:

1. Record the exception class and cause chain received in the fallback.
2. Record the Circuit Breaker, TimeLimiter, and Bulkhead IDs.
3. Confirm whether the Circuit Breaker state is CLOSED, OPEN, or HALF_OPEN.
4. Measure the elapsed time from call start to fallback execution.
5. Compare that duration against the effective `timeoutDuration`.
6. Check whether the Supplier started executing.
7. Check `ThreadPoolBulkhead` active workers, queue depth, `queueCapacity`, and rejection count.
8. Check semaphore permits if using Semaphore Bulkhead.
9. Check HTTP connection pool usage and acquire wait times.
10. Correlate TimeLimiter, Bulkhead, and Circuit Breaker events.
11. Verify decorator ordering to see which policy emits the exception and which records the failure.
12. Re-test slow tasks and full queues as two separate scenarios.

Quick decision table:

| Observation | Likely Cause | Next Action |
|---|---|---|
| Fallback after roughly `timeoutDuration`, Supplier started | TimeLimiter | Check effective timeout and latency |
| Fallback almost instantaneous, Supplier did not start, queue at capacity | ThreadPoolBulkhead | Check workers, queue, and admission limit |
| `CallNotPermittedException`, breaker OPEN | Circuit Breaker | Investigate failure rate and open duration |
| `BulkheadFullException` while remote is healthy | Local limit | Tune concurrency or reduce load |
| `PoolAcquireTimeoutException` | HTTP connection pool | Check `maxConnections` and pending acquires |
| Fallback itself throws an exception | Broken fallback | Investigate dependency and fallback code |

## 16. Common Mistakes

- **Increasing only timeout without checking the queue**: a full queue still rejects immediately.
- **Increasing only `queueCapacity`**: requests wait longer and still time out anyway.
- **Assuming fallback always means Circuit Breaker OPEN**: TimeLimiter and Bulkhead can also trigger fallbacks.
- **Relying on default timeouts without checking versions**: effective defaults can differ across adapters and releases.
- **Not aligning HTTP client timeouts and TimeLimiter**: callers receive fallbacks while HTTP requests continue running.
- **Confusing ThreadPoolBulkhead with Semaphore Bulkhead**: one uses workers/queue while the other bounds permits.
- **Retrying `BulkheadFullException`**: amplifies pressure on an already saturated queue.
- **Counting local admission-control errors toward remote failure rate**: Circuit Breaker can open even when the dependency is healthy.
- **Making the queue too large**: increases wait time and holds requests whose deadlines have already passed.
- **Not tracking Supplier start**: makes it hard to distinguish post-start timeouts from pre-start rejections.
- **Ignoring cancellation checks**: background tasks continue consuming resources after callers receive fallbacks.
- **Testing only the fallback response**: fails to prove which policy actually triggered the fallback.

## 17. Resolution and Prevention Workflow

When troubleshooting a fallback that always runs in Spring Cloud CircuitBreaker with Resilience4j:

1. Collect the original exception, events, and ID of each policy.
2. Determine whether the fallback is triggered by timeout, queue rejection, semaphore rejection, or Circuit Breaker OPEN.
3. Inspect the effective TimeLimiter configuration across `default`, `baseConfig`, instance, active profile, and Java Customizer.
4. Compare timeouts against p95/p99 latency and the overall deadline.
5. Identify which Bulkhead implementation is active before tuning queues or permits.
6. If the `ThreadPoolBulkhead` queue is full, inspect active workers, queue depth, `queueCapacity`, and wait durations.
7. Tune concurrency, bounded queues, HTTP connection pools, and admission control to match dependency capacity.
8. Never blindly retry rejection errors or `CallNotPermittedException`.
9. Test tasks exceeding timeout and tasks rejected by a full queue separately.
10. Monitor fallback counts with causes, timeout rates, rejection rates, and actual task completion times.

A fallback is the shared outcome of multiple failure paths. TimeLimiter triggers it when an operation exceeds its time limit; `ThreadPoolBulkhead` triggers it when no worker or queue slot is available to accept the task. Distinguishing the two causes via exceptions, response times, Supplier execution state, and queue metrics enables tuning the right policy and keeps the Circuit Breaker reflecting true dependency health rather than local resource limits.
