# Testing Concurrency, Full Bulkheads, and Rejected Queues

## Goal of Bulkhead Testing

In a Spring Cloud application using Circuit Breaker, a Bulkhead limits the number of calls allowed to run concurrently so that a slow dependency cannot exhaust the application's resources. When testing, you need to prove three behaviors: the number of running calls does not exceed the limit; calls exceeding the limit wait or are rejected according to configuration; and resources are released when calls complete or are cancelled.

Tests that only invoke methods sequentially usually fail to catch Bulkhead misconfigurations. To test concurrency limits, you must create multiple simultaneous calls and control when they start and finish. Using `CountDownLatch`, `CyclicBarrier`, or `Phaser` makes tests deterministic instead of relying on `Thread.sleep()` and hoping threads execute at the right instant.

Resilience4j's two Bulkhead types have different behaviors to verify:

| Type | Limit | When overloaded |
| --- | --- | --- |
| `SemaphoreBulkhead` | Number of calls currently holding permits, via `maxConcurrentCalls`. | Can reject immediately or wait up to `maxWaitDuration` to acquire a permit. |
| `ThreadPoolBulkhead` | Number of workers and queue slots, via `coreThreadPoolSize`, `maxThreadPoolSize`, and `queueCapacity`. | When both workers and queue are full, new tasks are rejected. |

Do not use a single test for both types. A semaphore controls active concurrent calls; `ThreadPoolBulkhead` also has a queue and executes suppliers on a separate pool. What you assert must match the Bulkhead type used in the application.

## Distinguishing Limits Before Writing Tests

With `SemaphoreBulkhead`, `maxConcurrentCalls = 3` means at most three calls can hold permits at one time. If `maxWaitDuration` is 0, a fourth call arriving while all three permits are in use is rejected immediately. If a wait duration greater than 0 is configured, the calling thread may wait for a permit during that window before being rejected. Do not use such blocking waits on a WebFlux event-loop thread.

With `ThreadPoolBulkhead`, you must consider both worker count and queue capacity together. For example, `coreThreadPoolSize = 2`, `maxThreadPoolSize = 2`, `queueCapacity = 4` allows two running tasks and up to four queued tasks. Once both workers are busy and all four queue slots are occupied, the next task is rejected. If `maxThreadPoolSize` is greater than `coreThreadPoolSize`, creating extra workers depends on whether the queue is full and on executor policy.

`queueCapacity` is not a lifetime limit on the total number of calls received by the application. It limits only waiting tasks. When a worker finishes, a queued task moves into execution and a queue slot is freed.

## Testing SemaphoreBulkhead with Multiple Threads

The example below holds the first call inside the supplier using a latch. Once the first call has acquired a permit, the test invokes the supplier a second time on the test thread. Because the limit is one permit and wait duration is 0, the second call must be rejected.

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;

import io.github.resilience4j.bulkhead.Bulkhead;
import io.github.resilience4j.bulkhead.BulkheadConfig;
import io.github.resilience4j.bulkhead.BulkheadFullException;
import org.junit.jupiter.api.Test;

class SemaphoreBulkheadConcurrencyTest {

    @Test
    void rejectsCallWhenAllPermitsAreOccupied() throws Exception {
        Bulkhead bulkhead = Bulkhead.of(
            "catalog",
            BulkheadConfig.custom()
                .maxConcurrentCalls(1)
                .maxWaitDuration(Duration.ZERO)
                .build()
        );

        CountDownLatch firstCallEntered = new CountDownLatch(1);
        CountDownLatch releaseFirstCall = new CountDownLatch(1);
        ExecutorService caller = Executors.newSingleThreadExecutor();

        Supplier<String> protectedCall = Bulkhead.decorateSupplier(
            bulkhead,
            () -> {
                firstCallEntered.countDown();
                await(releaseFirstCall);
                return "catalog-data";
            }
        );

        try {
            Future<String> first = caller.submit(protectedCall::get);

            assertTrue(firstCallEntered.await(2, TimeUnit.SECONDS));

            assertThatThrownBy(protectedCall::get)
                .isInstanceOf(BulkheadFullException.class);

            releaseFirstCall.countDown();
            assertThat(first.get(2, TimeUnit.SECONDS)).isEqualTo("catalog-data");
            assertThat(bulkhead.getMetrics().getAvailableConcurrentCalls())
                .isEqualTo(1);
        } finally {
            releaseFirstCall.countDown();
            caller.shutdownNow();
        }
    }

    private static void await(CountDownLatch latch) {
        try {
            if (!latch.await(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timed out waiting for test latch");
            }
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted while waiting", error);
        }
    }
}
```

The test has three critical synchronization points:

1. `firstCallEntered` signals that the first supplier has started and is holding the permit.
2. The second call runs while the permit is guaranteed to be occupied, so rejection does not depend on thread scheduling.
3. `releaseFirstCall` lets the first supplier finish; afterward the test confirms the permit was returned.

`finally` always opens the latch and stops the executor so the test leaves no blocked threads if an assertion fails. In real test suites, use finite timeouts on every wait so a synchronization bug cannot hang the entire build.

## Testing Concurrency Limits with an Active Counter

Besides verifying that a fourth call is rejected, you can launch a group of concurrent calls and measure how many suppliers are executing at the same instant. `AtomicInteger` tracks the current active count and the maximum observed concurrency.

```java
AtomicInteger active = new AtomicInteger();
AtomicInteger maxObserved = new AtomicInteger();

Supplier<String> measuredCall = Bulkhead.decorateSupplier(bulkhead, () -> {
    int now = active.incrementAndGet();
    maxObserved.accumulateAndGet(now, Math::max);
    try {
        await(releaseCalls);
        return "ok";
    } finally {
        active.decrementAndGet();
    }
});
```

In a full test, create multiple callers using an `ExecutorService`, use a latch to start them together, wait for accepted suppliers to enter, and then release the latch. Finally, verify that `maxObserved` does not exceed `maxConcurrentCalls`. When a concurrency test also checks rejected calls, distinguish the number of submitted tasks from the number of suppliers that actually started; rejected tasks must not increment `active`.

Do not set `maxObserved` equal to the number of threads in the test executor. The test executor merely applies concurrency pressure; the Bulkhead is what needs verification. Use more callers than the Bulkhead limit so the test can detect if the configuration was ignored.

## Testing ThreadPoolBulkhead When the Queue Is Full

With `ThreadPoolBulkhead`, you need one running task, one queued task, and then a third task submitted to verify rejection. Use a pool with one worker and one queue slot so the state is predictable:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import io.github.resilience4j.bulkhead.BulkheadFullException;
import io.github.resilience4j.bulkhead.ThreadPoolBulkhead;
import io.github.resilience4j.bulkhead.ThreadPoolBulkheadConfig;
import org.junit.jupiter.api.Test;

class ThreadPoolBulkheadQueueTest {

    @Test
    void rejectsTaskWhenWorkerAndQueueAreFull() throws Exception {
        ThreadPoolBulkhead bulkhead = ThreadPoolBulkhead.of(
            "legacy-catalog",
            ThreadPoolBulkheadConfig.custom()
                .coreThreadPoolSize(1)
                .maxThreadPoolSize(1)
                .queueCapacity(1)
                .build()
        );

        CountDownLatch firstTaskStarted = new CountDownLatch(1);
        CountDownLatch releaseFirstTask = new CountDownLatch(1);

        try {
            CompletableFuture<String> running = bulkhead.executeSupplier(() -> {
                firstTaskStarted.countDown();
                await(releaseFirstTask);
                return "running";
            });

            assertTrue(firstTaskStarted.await(2, TimeUnit.SECONDS));

            CompletableFuture<String> queued =
                bulkhead.executeSupplier(() -> "queued");

            CompletableFuture<String> rejected =
                bulkhead.executeSupplier(() -> "should-not-run");

            assertThatThrownBy(rejected::join)
                .isInstanceOf(CompletionException.class)
                .hasCauseInstanceOf(BulkheadFullException.class);

            releaseFirstTask.countDown();
            assertThat(running.get(2, TimeUnit.SECONDS)).isEqualTo("running");
            assertThat(queued.get(2, TimeUnit.SECONDS)).isEqualTo("queued");
        } finally {
            releaseFirstTask.countDown();
            bulkhead.close();
        }
    }

    private static void await(CountDownLatch latch) {
        try {
            if (!latch.await(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timed out waiting for test latch");
            }
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted while waiting", error);
        }
    }
}
```

With the configuration above, the `running` task occupies the worker and waits on the latch. The `queued` task occupies the single waiting slot. The `rejected` task arrives when both the worker and queue are full, so it must complete exceptionally with `BulkheadFullException` (typically wrapped in `CompletionException` when calling `join()`). After releasing the latch, both accepted tasks must complete.

Return APIs and exception wrapping can vary slightly across Resilience4j versions. When writing tests for a specific version, verify the actual future type and cause; what matters is proving that the third supplier does not run, the queue accepts no extra tasks, and the rejection error is recognized accurately.

## Verifying That Rejected Tasks Do Not Execute

Checking only that the future fails is not enough if you want to be sure the rejected supplier did not execute. Add a counter inside the supplier:

```java
AtomicInteger thirdTaskRuns = new AtomicInteger();

CompletableFuture<String> rejected = bulkhead.executeSupplier(() -> {
    thirdTaskRuns.incrementAndGet();
    return "should-not-run";
});

assertThatThrownBy(rejected::join)
    .isInstanceOf(CompletionException.class)
    .hasCauseInstanceOf(BulkheadFullException.class);
assertThat(thirdTaskRuns).hasValue(0);
```

The counter must be read after the future completes exceptionally. If the supplier runs unexpectedly, the test catches it even if the final response might have been mapped to a fallback.

## Testing Queue Capacity Release

A full queue is only a temporary state. Once a worker finishes, a waiting task is pulled out to run and a queue slot becomes free. Tests should verify that a new task can be accepted after load subsides:

1. Hold the first task in the running state.
2. Submit the second task to fill the queue.
3. Verify that the third task is rejected.
4. Release the first task and wait for the second task to complete.
5. Submit a fourth task and verify that it is accepted.

This catches cases where resources are not released after completion. With `SemaphoreBulkhead`, verify that the available permit count returns to the initial limit. With `ThreadPoolBulkhead`, verify that the pool still accepts new work once workers and queue slots become free.

## Testing SemaphoreBulkhead maxWaitDuration

When `maxWaitDuration` is greater than 0, calls are not necessarily rejected immediately when permits run out. A thread can wait up to the configured duration to acquire a permit. You can test two branches:

- Releasing a permit before the wait expires: the waiting call is allowed to proceed.
- Holding the permit past the wait duration: the waiting call terminates with `BulkheadFullException`.

In synchronous tests, execute the waiting call on a separate executor so the test thread can still release the latch. Measure duration only to confirm there is a bound; do not assert exact millisecond execution times because OS scheduling can delay the test. Do not use a long `maxWaitDuration` on a WebFlux event loop; waiting for a permit can block a thread handling many requests.

## Testing Reactive Pipelines

With `Mono` or `Flux`, you can use `BulkheadOperator` to limit subscriptions. Tests should verify:

- The first subscription acquires a permit when entering the pipeline.
- Excess subscriptions receive a rejection error per Bulkhead policy.
- When the publisher completes, errors, or is cancelled, the permit is released per operator semantics.
- The event loop is never blocked waiting for a permit.

Example illustrating how to apply the operator:

```java
Mono<CatalogItem> protectedCall = webClient.get()
    .uri("/catalog/{id}", productId)
    .retrieve()
    .bodyToMono(CatalogItem.class)
    .transformDeferred(BulkheadOperator.of(catalogBulkhead));
```

In tests, use `StepVerifier` to inspect `onNext`, `onComplete`, or `onError` signals. If you need to hold the first publisher in flight, use `Sinks.One` or `Sinks.Empty` as a control gate instead of `Thread.sleep()`. Subscribe a second time while the permit is held to verify the rejection error. Once you emit completion to the sink, verify that a new subscription can pass through.

Do not call `block()` inside WebFlux application code to wait for a permit. `block()` is occasionally used in test threads, but in reactive tests prefer `StepVerifier` to verify signals and avoid introducing usage patterns that differ from runtime.

## Distinguishing BulkheadFullException and CallNotPermittedException

These two errors reflect two different limits:

| Exception | Originating component | Meaning | Where to investigate |
| --- | --- | --- | --- |
| `BulkheadFullException` | SemaphoreBulkhead or ThreadPoolBulkhead | No permits, workers, or queue slots remain to accept the call. | Concurrency limits, permit hold duration, workers, and queue. |
| `CallNotPermittedException` | Resilience4j Circuit Breaker | The Circuit Breaker is `OPEN` and rejecting new calls. | Failure rate, slow-call rate, statistics window, and open duration. |

Do not lump both together as "dependency failure" in every metric. A Bulkhead may reject because the calling application ran out of capacity, even if the dependency never received the request. A Circuit Breaker rejects because prior outcomes indicated the dependency may be degraded. Keeping the two separate helps pinpoint the exact place to tune.

## Integration Testing with Spring Cloud Circuit Breaker

When using `Resilience4JCircuitBreakerFactory`, confirm whether Bulkhead is applied automatically by the factory according to your version's configuration or whether the application decorates calls manually. Do not manually apply `BulkheadOperator` a second time if the factory already attaches a Bulkhead, unless you intentionally designed two separate limits.

An integration test should:

1. Start the Spring context with the right starter and Resilience4j configuration.
2. Inject the factory or actual service using the factory.
3. Send multiple concurrent calls to a mock dependency that can hold requests with a latch.
4. Count the requests that actually reach the dependency and verify they do not exceed the Bulkhead limit.
5. Send additional requests while the Bulkhead is full and verify the response/exception is a Bulkhead rejection error.
6. Release held requests and verify that subsequent calls are accepted.
7. Verify that the Circuit Breaker keeps its state and metrics independent of Bulkhead rejections per configured policy.

In some versions of Spring Cloud Circuit Breaker Resilience4j, Bulkhead is enabled automatically when the Bulkhead module is on the classpath; properties controlling enablement and Bulkhead type vary by version. Check your release train documentation and condition evaluation report before concluding whether the factory uses `SemaphoreBulkhead` or `ThreadPoolBulkhead`.

## Load Testing and Resource Limits

Concurrency unit tests verify limit correctness in a small scenario. Additional load testing helps observe behavior when traffic rises over a sustained period. Gradually ramp up concurrency, hold dependency latency at different levels, and record:

- Peak number of active concurrent calls.
- Rejected call count and rejection rate.
- Queue size over time and longest-waiting task duration.
- Wait time before execution and actual processing time.
- Active threads, CPU, heap, and connection pool usage.
- p95/p99 latency and dependency error rate.

Do not simply increase queue size to reduce rejections. A large queue can make requests wait past their deadlines, retain many objects on the heap, and inflate p99 latency. Choose limits based on dependency capacity, connection pools, business deadlines, and replica count. If each replica permits 20 concurrent calls and 6 replicas are running, the dependency can receive roughly 120 concurrent calls from that application.

## Common Mistakes When Testing

| Mistake | Why the test is unreliable | How to fix |
| --- | --- | --- |
| Using `Thread.sleep()` hoping tasks are running | Thread ordering varies with machine load and scheduler. | Use latches/barriers to confirm tasks entered the supplier. |
| Submitting only one call at a time | Creates no contention for permits or queue slots. | Use multiple concurrent callers and hold the first task open. |
| Checking submitted task count instead of started supplier count | Rejected tasks were also submitted to the API. | Count inside the supplier and verify rejected tasks do not run. |
| Not releasing latches in `finally` | Failed tests can leave threads hanging and affect later tests. | Always release latches and shut down executors during cleanup. |
| Using an unbounded queue in tests | Cannot reproduce a full-queue scenario. | Configure a small, finite `queueCapacity`. |
| Checking only the final error | Fallbacks can mask the original rejection exception. | Verify exception, counter, supplier execution, and metrics. |
| Confusing `BulkheadFullException` with `CallNotPermittedException` | Misdiagnoses application overload as dependency failure. | Assert the exact error type and track both mechanisms separately. |
| Running reactive tests by blocking the event loop | Does not reflect non-blocking production behavior. | Use `StepVerifier` and sink-controlled publishers. |

## Checklist Before Accepting Tests

- [ ] The test holds at least one call inside the supplier to create a controlled busy state.
- [ ] Accepted concurrent calls do not exceed `maxConcurrentCalls` or worker limits.
- [ ] The test fills the queue and proves the next task is rejected.
- [ ] The rejected task's supplier is never executed.
- [ ] Permits or queue slots are released after tasks finish.
- [ ] New calls are accepted once resources are freed.
- [ ] Bulkhead rejections are distinguished from Circuit Breaker open state.
- [ ] Cleanup always releases latches and stops executors/pools.
- [ ] For reactive code, tests do not block the event loop and verify cancellation/termination.
- [ ] Test configuration matches the exact Bulkhead type actually used at runtime.

Testing concurrency and full-Bulkhead scenarios must prove both the limit and the resource lifecycle. When using latches to control calls, confirming the queue is full before submitting the next task, and verifying that rejected suppliers do not run, tests become more stable and accurately reflect the protection behavior in Spring Cloud Circuit Breaker. Clearly distinguishing Bulkhead rejection errors from Circuit Breaker `OPEN` state also ensures metrics and incident response point to the true root cause.
