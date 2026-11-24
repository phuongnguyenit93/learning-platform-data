# Waiting for Bounded Conditions Instead of Fixed `Thread.sleep`

In asynchronous and parallel processing tests, results often do not appear immediately after a method call. A task might run on an executor, an event listener might be invoked after an event is published, a message consumer might process a message after a broker delivers it, or data might only become visible after another transaction commits.

A common approach is calling `Thread.sleep(500)` and then checking the result. This waits for a fixed duration without knowing whether the work has finished. If the task finishes in 50 ms, the test wastes the remaining time. If the task needs 700 ms, the test still fails even though the system works properly. On CI, varying machine load and thread scheduling can turn a sleep duration that seemed sufficient locally into a source of flaky tests.

Instead, tests should wait for a meaningful condition and set a maximum deadline. The condition can be a status transitioning to `COMPLETED`, a record appearing in a repository, a callback being invoked, a queue receiving a message, or a future completing. When the deadline expires, the test fails with clear diagnostic information. When the condition is satisfied early, the test continues immediately.

## 1. Why does fixed `Thread.sleep` make tests unstable?

For example, a service starts a background task to generate a report:

```java
reportService.generateAsync(reportId);

Thread.sleep(500);

assertThat(reportRepository.findById(reportId)).isPresent();
```

This test snippet assumes 500 ms is always enough for the task to finish. However, actual execution time depends on many factors:

- Whether the executor has an idle thread or is busy processing other tasks.
- Whether the CI machine is experiencing high CPU or I/O load.
- Whether the task calls a database, HTTP service, or message broker.
- Whether the transaction has committed and data is visible from another connection.
- When the OS scheduler grants CPU time to the test thread and background thread.

`Thread.sleep` does not synchronize the two threads, does not confirm the task ran, and does not guarantee data is safely published between threads. It only pauses the current thread.

Two illustrative scenarios:

```text
Task completes after 50 ms:
Test:   start ---------------- sleep 500 ms ---------------- assert
Worker:       start -- done
                              ^ test waits ~450 ms unnecessarily

Task completes after 700 ms:
Test:   start ---------------- sleep 500 ms -- assert (too early)
Worker:       start -------------------------------- done
```

Condition-based waiting repeats the check until the condition becomes true or the deadline expires. The test therefore adapts to the actual completion time within the chosen bound.

## 2. Waiting for conditions with Awaitility

Awaitility is a Java library for writing assertions on asynchronous state in a readable way. Instead of writing loops manually, tests describe the target condition and maximum deadline.

Add the dependency to test configuration:

```groovy
testImplementation 'org.awaitility:awaitility'
```

Example waiting for a record to be created:

```java
import static org.awaitility.Awaitility.await;
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.TimeUnit;

@Test
void waitsUntilBackgroundTaskCreatesReport() {
    reportService.generateAsync("report-42");

    await()
            .atMost(2, TimeUnit.SECONDS)
            .untilAsserted(() ->
                    assertThat(reportRepository.findById("report-42"))
                            .isPresent());
}
```

`untilAsserted(...)` runs the assertion repeatedly until it succeeds or the deadline expires. If the repository does not yet contain the data on the first check, Awaitility keeps waiting. Once the record appears, the test finishes immediately.

Another form is waiting for a value matching a matcher:

```java
await()
        .atMost(3, TimeUnit.SECONDS)
        .until(
                () -> reportRepository.findStatusById("report-42"),
                equalTo(ReportStatus.COMPLETED));
```

Here, `findStatusById` is called repeatedly until it returns `COMPLETED`. `equalTo` is a Hamcrest matcher. You can use `untilAsserted` with AssertJ if you want to keep all assertions in the same style.

### Choosing a polling interval

By default, Awaitility checks the condition at a configured polling interval. You can explicitly specify the wait intervals between checks:

```java
await()
        .pollDelay(20, TimeUnit.MILLISECONDS)
        .pollInterval(50, TimeUnit.MILLISECONDS)
        .atMost(2, TimeUnit.SECONDS)
        .untilAsserted(() ->
                assertThat(jobService.status("job-17"))
                        .isEqualTo(JobStatus.DONE));
```

- `pollDelay` is the wait time before the first check.
- `pollInterval` is the interval between subsequent checks.
- `atMost` is the total maximum deadline for the condition to become true.

Do not set polling too aggressively if the condition queries a database, HTTP service, or external system. Polling every few milliseconds can create unnecessary load and cause the test to interfere with the system under test. Choose a cycle suited to the update speed and the cost of reading state.

### Waiting for multiple conditions

A task might only be considered complete when both its status and result are ready:

```java
await()
        .atMost(3, TimeUnit.SECONDS)
        .untilAsserted(() -> {
            assertThat(jobService.status("job-17"))
                    .isEqualTo(JobStatus.DONE);
            assertThat(resultRepository.findByJobId("job-17"))
                    .isPresent();
        });
```

Placing related assertions inside the same `untilAsserted` ensures the test waits until all required state is satisfied together. If you only check the status, the test might continue before the result has finished writing.

## 3. Using meaningful and observable conditions

The awaited condition should reflect what the test actually cares about. For example, if the requirement is that a message was saved, wait for the record to appear; if the requirement is that a callback ran, wait for the callback; if the requirement is that a task finished, wait for the terminal status.

Some common conditions:

| Asynchronous work | Condition to wait for |
|---|---|
| Background record creation | Repository returns the record with the target id. |
| Message processing | Message has status `PROCESSED` or corresponding result appears. |
| Sending notification | Notification is recorded or mock collaborator receives the invocation. |
| File creation | File appears and has expected size/content. |
| Background job | Status transitions to `COMPLETED` or `FAILED`. |
| Cache update | Cache returns the new value. |
| WebSocket/SSE | Client receives the expected event. |
| Batch-processing consumer | Processed item count reaches the expected threshold. |

Avoid waiting on conditions that do not prove the outcome, such as "500 ms has passed" or "thread is in RUNNABLE state". Thread state is usually an implementation detail, not a business contract of the application.

## 4. Waiting for callbacks with CountDownLatch

Polling is not always needed. If an API provides a callback or the test controls the completion point, a synchronization primitive such as `CountDownLatch` is often more accurate and efficient.

Example of a component invoking a callback upon completion:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

@Test
void waitsForAsyncCallback() throws InterruptedException {
    CountDownLatch completed = new CountDownLatch(1);
    AtomicReference<ReportResult> result = new AtomicReference<>();

    reportService.generateAsync("report-42", value -> {
        result.set(value);
        completed.countDown();
    });

    assertThat(completed.await(2, TimeUnit.SECONDS))
            .as("report callback should complete within the deadline")
            .isTrue();
    assertThat(result.get().reportId()).isEqualTo("report-42");
}
```

`await(timeout, unit)` returns `false` if time expires before the latch opens. Thus the test can fail right at the deadline assertion instead of waiting indefinitely.

`CountDownLatch` also provides a visibility guarantee: actions on a thread before calling `countDown()` happen-before actions after another thread successfully returns from `await()`. Therefore, data written to `AtomicReference` before `countDown()` can be read after `await()` returns `true`.

If the callback can fail, store the exception as well and open the latch in every completion branch:

```java
CountDownLatch completed = new CountDownLatch(1);
AtomicReference<ReportResult> result = new AtomicReference<>();
AtomicReference<Throwable> failure = new AtomicReference<>();

reportService.generateAsync("report-42", (value, error) -> {
    if (error != null) {
        failure.set(error);
    } else {
        result.set(value);
    }
    completed.countDown();
});

assertThat(completed.await(2, TimeUnit.SECONDS)).isTrue();
assertThat(failure.get()).isNull();
assertThat(result.get()).isNotNull();
```

In real callback designs, ensure the callback is invoked exactly once for both success and error. If the callback is never invoked when a task fails, the test will just time out, making it hard to distinguish a business error from a forgotten callback bug.

## 5. Waiting for CompletableFuture with a timeout

If an asynchronous API returns `CompletableFuture`, you can directly use `get(timeout, unit)`. This waits directly on the future representing the work without polling external state.

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

@Test
void waitsForFutureResult() throws Exception {
    CompletableFuture<ReportResult> future = reportService.generateAsync("report-42");

    ReportResult result = future.get(2, TimeUnit.SECONDS);

    assertThat(result.reportId()).isEqualTo("report-42");
    assertThat(result.status()).isEqualTo(ReportStatus.COMPLETED);
}
```

If the future does not complete within the deadline, `get` throws `TimeoutException`. If the work fails, `get` throws `ExecutionException` and the original exception is in `getCause()`.

```java
assertThatThrownBy(() -> future.get(2, TimeUnit.SECONDS))
        .isInstanceOf(ExecutionException.class)
        .hasCauseInstanceOf(ReportGenerationException.class);
```

If the test needs to confirm that a timeout occurs, you can use `assertThrows(TimeoutException.class, ...)`. Note that `get(timeout, unit)` only bounds the wait time of the calling thread. It does not automatically cancel the background task on timeout. If work needs to stop, define a clear cancellation policy and verify the result of `future.cancel(true)` along with the task's interrupt behavior.

### Do not use join when a time bound is needed

`CompletableFuture.join()` waits until the future completes and does not accept a timeout. In tests with a risk of hanging, `get(timeout, unit)` or an API with a suitable deadline is safer. `join()` is appropriate when another guarantee ensures the future will complete and the test does not need its own deadline.

## 6. Waiting for an executor to finish

When a test directly manages an `ExecutorService`, it can call `shutdown()` and then `awaitTermination(timeout, unit)` to wait for submitted tasks to finish:

```java
executor.shutdown();

assertThat(executor.awaitTermination(2, TimeUnit.SECONDS))
        .as("executor should terminate within the deadline")
        .isTrue();
```

If the deadline expires, the test can call `shutdownNow()` in the cleanup block to send interrupts to running tasks. Tasks need to cooperate with interruption; do not assume every task stops immediately upon receiving an interrupt.

`awaitTermination` only confirms the executor terminated after shutdown. If the executor is a shared thread pool of the Spring application context, do not shut it down yourself inside a test method. In that case wait for the task's business condition or let Spring manage the executor lifecycle.

## 7. Testing `@Async` in Spring

Spring `@Async` runs a method on a configured executor. An `@Async` method can return `CompletableFuture`, `Future`, or `void`. With `void`, the caller has no future to wait on; results must be observed through a callback, repository, event, or checkable condition.

Example service returning `CompletableFuture`:

```java
import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
class ReportService {

    @Async
    public CompletableFuture<ReportResult> generateAsync(String reportId) {
        ReportResult result = createReport(reportId);
        return CompletableFuture.completedFuture(result);
    }

    private ReportResult createReport(String reportId) {
        return new ReportResult(reportId, ReportStatus.COMPLETED);
    }
}
```

The application needs async processing enabled:

```java
@Configuration
@EnableAsync
class AsyncConfiguration {
}
```

Tests can inject the bean from the Spring context and await the future:

```java
@SpringBootTest
class ReportServiceAsyncTest {

    @Autowired
    ReportService reportService;

    @Test
    void waitsForAsyncReportResult() throws Exception {
        ReportResult result = reportService.generateAsync("report-42")
                .get(2, TimeUnit.SECONDS);

        assertThat(result.status()).isEqualTo(ReportStatus.COMPLETED);
    }
}
```

The method must be called through the Spring proxy for `@Async` to take effect. Calling an async method from another method on the same instance (self-invocation) usually does not pass through the proxy and may execute synchronously. Therefore, integration tests should obtain the bean from the context rather than calling `new ReportService()` if the goal is to verify Spring's async configuration.

With `@Async void` methods, exceptions are not returned to the caller via a future. Spring uses `AsyncUncaughtExceptionHandler` to handle exceptions from void methods. If you need to assert failures, consider designing the API to return `CompletableFuture` or recording error results in an observable location.

## 8. Waiting for eventual consistency state with Awaitility

Some tasks provide neither a future nor a callback. For example, a message broker delivers a message to a consumer and the consumer updates the database afterward. In that case, waiting for an observable condition from the system is appropriate.

```java
@SpringBootTest
class OrderEventIntegrationTest {

    @Autowired
    ApplicationEventPublisher eventPublisher;

    @Autowired
    OrderRepository orderRepository;

    @Test
    void waitsUntilOrderEventIsProcessed() {
        eventPublisher.publishEvent(new OrderPlaced("order-42"));

        await()
                .atMost(5, TimeUnit.SECONDS)
                .pollInterval(100, TimeUnit.MILLISECONDS)
                .untilAsserted(() ->
                        assertThat(orderRepository.findStatusById("order-42"))
                                .isEqualTo(OrderStatus.PROCESSED));
    }
}
```

The test does not assume how long the listener will take to run. It waits for the business status `PROCESSED` for up to five seconds. If the listener is not registered, throws an exception, or does not update the database, the test fails when the deadline expires.

With brokers or out-of-process systems, use a deadline aligned with the test environment's SLA and ensure fixtures are not shared between tests. A unique id per test helps prevent a test from mistakenly reading a record created by another test.

### Note on transactions in tests

If a test method is annotated with `@Transactional`, the test transaction normally does not commit before the method finishes. An async task running on another thread uses a different transaction and might not see uncommitted data from the test thread. Conversely, data written by the worker might not be seen by the test transaction in the expected way.

When testing asynchronous processing via a database:

- Commit input data before the background task needs to read it.
- Use a separate transaction or explicitly committed fixtures when needed.
- Do not assume the transaction context automatically propagates to an `@Async` thread.
- Clean up data after the test in a way compatible with the worker's transaction.

Awaitility does not solve database visibility or isolation. It only retries the condition; data must be published and committed properly so the checking thread can observe it.

## 9. Testing asynchronous MVC requests

Spring MVC can return asynchronous responses using `Callable`, `DeferredResult`, or `WebAsyncTask`. With MockMvc, do not sleep before checking the response. Instead, assert that the request entered async processing and then call `asyncDispatch` to complete assertions on the result.

```java
MvcResult result = mockMvc.perform(get("/reports/async"))
        .andExpect(request().asyncStarted())
        .andReturn();

mockMvc.perform(asyncDispatch(result))
        .andExpect(status().isOk())
        .andExpect(content().string("report-ready"));
```

`asyncStarted()` confirms the request left the initial dispatch thread for asynchronous processing. `asyncDispatch(result)` waits for the async result via Spring Test's mechanism and continues verifying the response. If the application uses an independent callback or worker outside Spring MVC's async lifecycle, use a future, latch, or Awaitility to wait for the corresponding condition.

## 10. Testing reactive flows with StepVerifier

With Reactor `Mono` and `Flux`, there is no need to poll state with `Thread.sleep`. `StepVerifier` subscribes to the publisher and synchronizes assertions with reactive signals:

```java
StepVerifier.create(reportService.generate("report-42"))
        .assertNext(result -> {
            assertThat(result.reportId()).isEqualTo("report-42");
            assertThat(result.status()).isEqualTo(ReportStatus.COMPLETED);
        })
        .verifyComplete();
```

If the publisher might not emit a signal, set a time limit:

```java
StepVerifier.create(reportService.generate("report-42"))
        .expectNextCount(1)
        .verifyComplete(Duration.ofSeconds(2));
```

`verifyComplete()` waits for `onComplete`; the overload taking `Duration` limits the total wait time. For infinite publishers, verify the required elements and call `thenCancel()` instead of waiting for completion.

## 11. Visibility and thread safety of awaited conditions

Polling is only useful if the test thread can observe the state updated by the background thread. A regular boolean variable written by a worker and read by the test thread without synchronization can cause a data race:

```java
boolean completed = false;

// Worker thread: completed = true;
// Test thread: await().until(() -> completed);
```

There is no visibility guarantee between the two threads in this example. The test may keep reading the stale value or exhibit inconsistent behavior.

Use an appropriate synchronization mechanism:

- `AtomicBoolean`, `AtomicReference`, or other atomic types for simple state.
- `volatile` when only visibility is needed for a single state variable with no complex read-modify-write operations.
- `CountDownLatch`, `Semaphore`, `CompletableFuture`, or `BlockingQueue` for event synchronization.
- Thread-safe collections or a repository/database with appropriate transaction and isolation settings.

Example using `AtomicBoolean`:

```java
AtomicBoolean completed = new AtomicBoolean(false);

executor.submit(() -> completed.set(true));

await()
        .atMost(1, TimeUnit.SECONDS)
        .untilTrue(completed);
```

Atomic types provide the necessary memory semantics for the test thread to read the update. However, if a condition spans multiple fields that must be mutually consistent, a single atomic boolean might not be enough; publish an immutable result via `AtomicReference` or synchronize the entire state.

## 12. Timeouts, polling, and test execution time

Setting timeouts must be based on reasonable task durations and the environment. Too short a timeout causes random test failures; too long a timeout delays detection of real bugs and slows down the suite.

Some practical guidelines:

1. Choose a deadline large enough relative to normal task duration in the CI environment.
2. Poll infrequently enough to avoid creating unnecessary load, yet fast enough for the test to respond promptly once the condition becomes true.
3. Use a deadline for every wait operation, avoiding unbounded loops.
4. When a test has multiple asynchronous steps, consider an overall deadline so total duration does not exceed acceptable limits.
5. On timeout, the message should state the expected condition and job id for easier diagnosis.

JUnit can set an overall limit on a test method:

```java
@Test
@Timeout(value = 8, unit = TimeUnit.SECONDS)
void processesEventWithinTheOverallDeadline() {
    // The test can use Awaitility with a shorter deadline inside.
}
```

`@Timeout` is the last line of defense. It does not replace specific timeouts on `await`, `Future.get`, `CountDownLatch.await`, or `StepVerifier`, because those APIs pinpoint exactly which operation failed to complete.

## 13. Handling errors while waiting

The awaited condition might throw a temporary exception when state is not yet ready. For example, a repository returns `Optional.empty()` before the worker writes data; writing assertions with `untilAsserted` allows Awaitility to retry the assertion.

However, you should not ignore all exceptions. If query code throws `IllegalStateException` due to misconfiguration or a lost database connection, ignoring errors until timeout can mask the real cause.

Only configure ignoring exceptions when they represent a known, recoverable transient state. For unexpected errors, letting the test fail immediately preserves root-cause information. When using `ignoreExceptions()`, consider its broad scope; you can use a narrower condition to ignore only specific exception types.

If a timeout occurs, Awaitility provides details about the unmet condition. You can add a description with `alias(...)`:

```java
await()
        .alias("order-42 should reach PROCESSED state")
        .atMost(3, TimeUnit.SECONDS)
        .until(() -> orderRepository.findStatusById("order-42"),
                equalTo(OrderStatus.PROCESSED));
```

Condition names make error logs easier to read when a suite has multiple background tasks running concurrently.

## 14. When to use Awaitility, a latch, or a Future?

| Mechanism | Suitable when | Points to note |
|---|---|---|
| Awaitility | State can only be observed via a repository, cache, mock, or another API | Polling has overhead; requires thread-safe conditions and explicit deadlines. |
| `CountDownLatch` | There is a callback or an explicit completion signal point | A latch only counts down and carries no result; store result/error separately and open the latch in every completion branch. |
| `CompletableFuture.get(timeout, unit)` | The API returns a future representing the work | Waiting timeout does not automatically cancel the task; errors are wrapped in `ExecutionException`. |
| `ExecutorService.awaitTermination(...)` | The test owns the executor and wants to wait for it to finish | Only use after `shutdown`; do not shut down Spring's shared executor. |
| `StepVerifier` | The result is a `Mono`/`Flux` | Synchronizes on reactive signals; set a timeout if the publisher might not complete. |
| MockMvc `asyncDispatch` | A Spring MVC controller returns an async result | Uses Spring Test's async lifecycle instead of sleep. |

Prefer waiting directly on the primitive provided by the API. If there is a `CompletableFuture`, wait on the future. If there is a callback, use a latch or future. If only eventual state in a database or external system is available, Awaitility is more suitable.

## 15. Common mistakes

### Replacing `Thread.sleep(500)` with a custom loop without a deadline

Polling without a deadline can still hang a test indefinitely. Every waiting mechanism needs a maximum time limit and a clear failure message.

### Polling too aggressively

Checking the database thousands of times per second does not make the background task faster. It only increases load and can slow down the system under test. Choose a reasonable `pollInterval`.

### Waiting on a non-terminal status

For example, a status already being `STARTED` does not mean the file has finished writing or the message has committed. Wait for a status that reflects the condition the test needs to verify.

### Using plain variables across threads

Without memory visibility, polling might never see updates. Use atomics, volatile, latches, futures, or thread-safe structures.

### Using `Future.get()` without a timeout

Parameterless `get()` can wait indefinitely. Use the overload with a deadline in tests.

### Catching exceptions and continuing to wait in all cases

Only ignore transient errors intentionally. Programming, configuration, or connection errors should be reported immediately so they are not hidden behind generic timeout messages.

### Test transactions hiding worker data

An uncommitted test transaction may not be visible from another thread. Design clear fixtures and commit boundaries when testing async processing via a database.

### Too short or inconsistent timeouts

Timeouts for Awaitility, futures, clients, and JUnit should be arranged consistently. The overall test timeout should exceed the inner operation deadlines by a margin large enough for cleanup and failure message generation.

## 16. Checklist for asynchronous tests

- [ ] The test identifies a specific business condition to wait for.
- [ ] Every wait operation has a maximum deadline.
- [ ] Use Awaitility when only eventual state can be observed.
- [ ] Use a latch or future when the API provides a direct completion signal.
- [ ] Use `StepVerifier` for reactive publishers.
- [ ] Do not use fixed `Thread.sleep` to guess task completion time.
- [ ] State shared between threads has visibility/thread-safety mechanisms.
- [ ] The polling interval matches query cost and update speed.
- [ ] Assertions verify the final outcome, not just that the task started.
- [ ] Unexpected errors are not ignored while waiting.
- [ ] Transactions and commit boundaries fit the thread running the background task.
- [ ] A test-method-level timeout protects the entire test when needed.

Waiting for bounded conditions makes asynchronous tests reflect the true state of the system. Awaitility fits when observing eventual state; latches and futures fit when the API signals completion directly; `StepVerifier` fits reactive publishers. Combining meaningful conditions, safe synchronization, and explicit deadlines helps tests respond immediately when work finishes and fail in a controlled way when work does not complete.
