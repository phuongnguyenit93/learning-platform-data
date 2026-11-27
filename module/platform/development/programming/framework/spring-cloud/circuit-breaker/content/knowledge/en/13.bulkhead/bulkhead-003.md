# ThreadPoolBulkhead, Thread Pool Size, and Bounded Queue

When a service calls multiple downstream dependencies, a slow dependency can exhaust processing threads and stall other calls. **ThreadPoolBulkhead** isolates a group of calls with a dedicated thread pool and a bounded queue. As a result, both the number of concurrently running tasks and the number of queued tasks have a hard ceiling; once capacity is exhausted, new calls fail fast instead of continuing to consume resources unboundedly.

In the **SPRING_CLOUD_CIRCUIT_BREAKER** module, Bulkhead works alongside Circuit Breaker to limit cascading failures when a dependency is slow or unavailable. Circuit Breaker decides whether to keep calling a dependency based on outcomes and failure rates; ThreadPoolBulkhead limits concurrent tasks and isolates execution resources. The two mechanisms address different aspects of fault tolerance.

## 1. What Problem Does ThreadPoolBulkhead Solve?

Suppose the Order service calls the Inventory service. When Inventory responds in 50 ms, processing threads are freed quickly. When Inventory slows down and each request takes 8 seconds, many Order service threads can be held up. If all dependency calls share an unbounded executor, queued tasks accumulate, memory usage rises, and unrelated features can be affected.

ThreadPoolBulkhead creates a dedicated execution region for a group of calls. It bounds:

- The number of threads allowed to run tasks for that dependency group.
- The number of tasks that can wait in the queue.
- The lifetime of idle threads above the core pool size, depending on executor configuration.
- The number of accepted tasks before the system rejects new requests.

Processing flow diagram:

~~~mermaid
flowchart TD
    A[Incoming request] --> B[ThreadPoolBulkhead]
    B --> C{Space available in pool or queue?}
    C -->|Yes| D[Run or enqueue]
    C -->|No| E[Fail fast]
    D --> F[Dedicated thread pool]
    F --> G[Call dependency service]
    G --> H[Result or error]
    E --> I[BulkheadFullException]
~~~

When both the pool and the queue are full, ThreadPoolBulkhead rejects new tasks. This is intentional protective behavior: the system signals that it currently has no capacity to accept more work rather than accepting additional requests and letting them wait indefinitely.

## 2. Thread Pool and Queue Parameters

Resilience4j ThreadPoolBulkhead provides the following commonly used parameters:

| Property | Meaning | Considerations |
| --- | --- | --- |
| `coreThreadPoolSize` | Core thread count of the pool | Choose based on normal concurrent tasks and CPU/memory resources |
| `maxThreadPoolSize` | Maximum number of threads the pool can scale up to | Set a ceiling so one dependency cannot exhaust application resources |
| `queueCapacity` | Maximum number of tasks allowed to wait | Use a bounded queue to limit memory usage and wait time |
| `keepAliveDuration` | How long idle threads above the core count are kept before being reclaimed | Choose based on load variability and thread creation cost |

Example configuration:

~~~yaml
resilience4j:
  thread-pool-bulkhead:
    configs:
      default:
        coreThreadPoolSize: 4
        maxThreadPoolSize: 8
        queueCapacity: 20
        keepAliveDuration: 20ms
    instances:
      inventory:
        baseConfig: default
~~~

In this example, the pool maintains 4 core threads and can expand up to 8 threads. When threads are busy, up to 20 tasks can wait in the queue. Once all 8 threads are running and all 20 queue slots are occupied, the next task is rejected.

With this illustrative configuration, the theoretical limit of tasks accepted concurrently or waiting in the bulkhead is 8 running tasks plus 20 queued tasks, or 28 tasks. This is an admission limit at a given point in time, not throughput per second. Completion time still depends on dependency latency and per-task processing time.

## 3. How Pool Scaling and Queueing Work

For a thread pool with a core thread count, maximum thread count, and bounded queue, behavior typically follows these steps:

1. When a task arrives and the running thread count is below `coreThreadPoolSize`, the executor creates a thread to run the task.
2. Once core threads are busy, new tasks are placed into the queue if space remains.
3. When the queue is full, the executor can create additional threads beyond the core count, up to `maxThreadPoolSize`.
4. When the pool has reached its maximum and the queue is also full, new tasks are rejected.
5. When load drops, threads above the core count can be reclaimed after `keepAliveDuration`.

Example with 4 core threads, max 8 threads, and a queue of 20:

| Scenario | Running tasks | Queued tasks | Behavior |
| --- | ---: | ---: | --- |
| Low load | 2 | 0 | Two threads process tasks |
| Core threads exhausted | 4 | 6 | New tasks wait in the queue |
| Queue full | 4 | 20 | Pool can scale up additional threads up to 8 |
| Pool and queue full | 8 | 20 | New tasks are rejected |
| Load drops | 3 | 0 | Tasks complete; threads above core count may be reclaimed after idle time |

A larger queue does not mean a healthier system. A long queue can hold many requests in memory and drive up response times. If requests have waited so long that the result is no longer useful, rejecting early can be better than continuing to queue them.

## 4. Why Must the Queue Be Bounded?

An unbounded queue allows the application to accept more work than it can process. When a dependency is slow, queued tasks can grow continuously. Common consequences include:

- Memory is consumed by waiting requests, contexts, and payload data.
- Wait time grows, causing clients to time out before the task even runs.
- When the dependency recovers, a large backlog of requests can trigger a sudden load spike.
- Fresh requests are delayed by old work that has already expired or lost value.

A bounded queue places a clear cap on accepted work. When space runs out, the bulkhead fails fast and the application can return a temporary error, invoke a fallback, or let the caller decide whether to retry later.

Do not set a huge `queueCapacity` merely to reduce rejection counts. Determine the request time budget, average processing rate, and memory available for queued tasks. The queue must be small enough that wait time does not exceed the useful lifetime of a request.

## 5. Using ThreadPoolBulkhead with Resilience4j

You can create a ThreadPoolBulkhead directly via a registry and execute an asynchronous supplier:

~~~java
import io.github.resilience4j.bulkhead.ThreadPoolBulkhead;
import io.github.resilience4j.bulkhead.ThreadPoolBulkheadConfig;
import io.github.resilience4j.bulkhead.ThreadPoolBulkheadRegistry;

import java.time.Duration;
import java.util.concurrent.CompletionStage;

public class InventoryWorker {
    private final InventoryClient inventoryClient;
    private final ThreadPoolBulkhead bulkhead;

    public InventoryWorker(InventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;

        ThreadPoolBulkheadConfig config =
                ThreadPoolBulkheadConfig.custom()
                        .coreThreadPoolSize(4)
                        .maxThreadPoolSize(8)
                        .queueCapacity(20)
                        .keepAliveDuration(Duration.ofMillis(20))
                        .build();

        ThreadPoolBulkheadRegistry registry =
                ThreadPoolBulkheadRegistry.of(config);
        this.bulkhead = registry.bulkhead("inventory");
    }

    public CompletionStage<Inventory> getInventory(String sku) {
        return bulkhead.executeSupplier(
                () -> inventoryClient.get(sku)
        );
    }
}
~~~

`executeSupplier` returns a `CompletionStage<T>` because the task runs on a separate thread pool. The call to `inventoryClient.get(sku)` takes place inside the task scheduled by the bulkhead, not immediately on the thread calling `getInventory`.

This example uses the registry to illustrate the programmatic API. In a Spring Boot application, you can declare configuration in YAML and inject the registry or use the appropriate Spring Cloud CircuitBreaker integration. Do not create a new registry on every request; the registry and bulkhead should be created once and managed as shared application components.

## 6. Handling When Pool and Queue Are Full

When there is no remaining capacity, ThreadPoolBulkhead rejects the task, typically via a `BulkheadFullException` surfaced through the `CompletionStage`. The application should handle this case as a recoverable overload condition rather than treating it as an unknown programming error.

Example:

~~~java
import io.github.resilience4j.bulkhead.BulkheadFullException;

public CompletionStage<InventoryResult> getInventoryResult(String sku) {
    return bulkhead.executeSupplier(() -> inventoryClient.get(sku))
            .thenApply(InventoryResult::available)
            .exceptionally(failure -> {
                Throwable cause = unwrap(failure);
                if (cause instanceof BulkheadFullException) {
                    return InventoryResult.temporarilyUnavailable(sku);
                }
                throw new IllegalStateException(
                        "Unable to retrieve inventory", cause);
            });
}
~~~

The `unwrap` method in the example is an application helper to extract the root cause if the error is wrapped in a `CompletionException` or `ExecutionException`. Implement this helper to match how your project uses CompletionStage. Error handling should distinguish bulkhead rejections from HTTP or business errors returned by the Inventory service.

Do not automatically retry immediately upon receiving `BulkheadFullException`. If the pool and queue are already full, immediate retries only add more pressure. You can return a 503 error or an overload status so the client throttles its rate, or retry after a bounded delay if the API contract permits.

## 7. Combining ThreadPoolBulkhead with Circuit Breaker

ThreadPoolBulkhead and Circuit Breaker can protect the same dependency together:

| Mechanism | What does it protect? | Trigger condition |
| --- | --- | --- |
| ThreadPoolBulkhead | Execution resources and queued task count | Pool and queue have reached their limits |
| Circuit Breaker | Dependency health | Failure rate or slow-call rate exceeds threshold |

Bulkhead limits how many requests can run concurrently. Circuit Breaker monitors outcomes to stop calling a dependency when it repeatedly fails or runs slowly. When combining them, clearly define the order of application and which exception types the Circuit Breaker counts as failures.

If the bulkhead rejects due to internal overload, consider whether rejection exceptions should increment the Circuit Breaker's failure rate. If every rejection is counted as an Inventory service failure, the circuit may open because the local pool is full even while Inventory is healthy. Conversely, if you ignore all rejections without tracking them separately, the application can mask an under-provisioned capacity issue. Track bulkhead rejection counts separately.

A separate Circuit Breaker configuration can share the same instance name as the bulkhead under a different prefix:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
  thread-pool-bulkhead:
    instances:
      inventory:
        coreThreadPoolSize: 4
        maxThreadPoolSize: 8
        queueCapacity: 20
        keepAliveDuration: 20ms
~~~

The two configurations govern two separate mechanisms. The name `inventory` links them to the same dependency, but Circuit Breaker parameters do not live under ThreadPoolBulkhead and vice versa.

## 8. Choosing Pool and Queue Sizes

There is no single set of values that fits every service. When choosing a configuration, consider:

1. **Average and high-percentile processing times.** If each task waits several seconds on Inventory, a large thread count can drive up concurrent connections and load on Inventory.
2. **Dependency capacity.** Limit concurrent calls according to what the dependency can serve reliably.
3. **Caller resource budget.** Each thread carries stack overhead, context switching, and related resources. Do not create many large pools across many dependencies without accounting for total thread count.
4. **Request time budget.** The queue should not hold tasks longer than the deadline within which results remain useful.
5. **Workload nature.** I/O-bound tasks can use different pool sizing than CPU-bound tasks; measure under realistic load to pick thread counts.
6. **Acceptable rejection rate.** Occasional rejections under overload indicate the mechanism is shedding load; sustained rejections signal that capacity or traffic needs review.

One way to start is to choose `coreThreadPoolSize` based on normal concurrency, set `maxThreadPoolSize` modestly higher in a controlled manner, and pick a small queue based on the wait budget. Then measure latency, queue saturation, active thread count, and rejection counts under representative load tests.

Avoid increasing both the pool and the queue just to reduce rejection errors. Doing so can turn an obvious overload failure into high latency and resource exhaustion that are much harder to diagnose.

## 9. Metrics and Diagnostics

Monitor the following metrics for each ThreadPoolBulkhead:

- Active threads and total threads in the pool.
- Tasks currently waiting in the queue and maximum queue capacity.
- Completed tasks and rejected tasks.
- Time spent waiting in the queue and task execution duration.
- Error rate of dependency calls after a task begins executing.
- Related Circuit Breaker state if the two mechanisms are combined.

When rejections increase, distinguish queue saturation caused by traffic spikes from long-running tasks caused by a slow dependency. If the queue is always full and wait times are high, increasing the queue may only make requests wait longer. If active threads stay at maximum while dependency processing time is normal, you may need to re-evaluate the concurrency limit or pool capacity.

Resilience4j can export metrics via Micrometer when the application configures the appropriate integration. You can use Spring Boot Actuator and a monitoring system to track queue usage, pool usage, and rejections. Set alerts for sustained rejection rates, queues consistently near capacity, and wait times exceeding budget.

## 10. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using an unbounded queue | Queued tasks and memory can grow continuously | Set a bounded `queueCapacity` |
| Setting queue too large | Requests wait too long and may time out before running | Size the queue to the time budget |
| Setting `maxThreadPoolSize` too high | Creates too many threads and increases load on the dependency | Cap concurrency based on actual capacity |
| Creating a registry or pool per request | Spawns many executors, wastes resources, and is hard to manage | Use a shared registry/bulkhead |
| Retrying immediately when bulkhead is full | Amplifies pressure at the exact moment the system is overloaded | Fail in a controlled way or retry with backoff |
| Treating BulkheadFullException as a dependency failure | Circuit Breaker may open prematurely | Classify and track rejection errors separately |
| Monitoring only the Circuit Breaker | Misses queue and pool capacity exhaustion | Monitor Bulkhead metrics as well |
| Running blocking tasks on an application-wide shared pool | Slow dependencies affect unrelated work | Isolate executors for appropriate task groups |

## 11. Implementation Workflow

When adding a ThreadPoolBulkhead for a dependency, follow this sequence:

1. Identify the group of calls to isolate and assign a stable bulkhead name.
2. Estimate the concurrent call count that both the dependency and the calling application can tolerate.
3. Configure `coreThreadPoolSize`, `maxThreadPoolSize`, `queueCapacity`, and `keepAliveDuration`.
4. Use a registry or Spring integration to create a shared bulkhead; do not create pools per request.
5. Handle the full pool and full queue case, distinguishing bulkhead rejections from HTTP errors returned by the dependency.
6. Combine with a Circuit Breaker if you need to track failure rates and stop calls when the dependency degrades.
7. Test under load: verify threads do not exceed the maximum, the queue does not exceed capacity, and new tasks are rejected when both are full.
8. Monitor metrics and tune based on latency, wait time, rejection rate, and actual resource usage.

ThreadPoolBulkhead with a bounded thread pool and queue establishes clear limits on running and waiting work. By sizing the pool to dependency capacity, keeping the queue within the time budget, and handling rejections intentionally, a Spring Cloud application can isolate a slow service without letting it consume the resources of the rest of the system.
