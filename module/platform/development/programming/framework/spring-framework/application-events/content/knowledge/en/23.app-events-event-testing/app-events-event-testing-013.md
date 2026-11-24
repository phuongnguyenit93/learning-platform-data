# Non-Flaky Async Listener Testing in Spring Framework Application Events

## 1. The Problem: Async Listeners Make Tests Randomly Green and Red

In Spring Framework, application events are often used to decouple tasks like sending notifications, updating metrics, auditing, or calling other services from the main business flow. When a listener runs asynchronously, `applicationEventPublisher.publishEvent(event)` can **return before the listener finishes**. If a test immediately inspects the database, an `AtomicReference`, a log, or a mock without awaiting an appropriate signal, outcomes depend on OS thread scheduling and CI load.

An easily flaky test:

```java
publisher.publishEvent(new OrderPlaced("ORD-42"));
verify(notificationGateway).send("ORD-42"); // May be too early!
```

This is an **illustrative failure pattern** with Mockito, not a standalone program. The test may pass on a laptop because the executor runs fast, yet fail on slow CI. Adding `Thread.sleep(1000)` does not fix the root cause: 1 second may be too short or wasteful while the test still holds a race condition.

Under the **Event Testing** group, the goal of **non-flaky async listener testing** is building tests **synchronized by an observable event**, verifying real handler outcomes, ensuring errors are not swallowed, and cleaning up every thread/resource after each test.

A reliable test must distinguish:

1. **Publisher called `publishEvent`**: the Java call finished.
2. **Task was submitted**: the executor accepted work, not necessarily started.
3. **Listener started**: the handler reached its start marker.
4. **Listener finished**: work inside the handler's scope actually completed.
5. **External side effects finished**: e.g., an email was truly sent; if the handler only enqueues a job, this state belongs to another system.

Never use a signal from milestone (1) to assert milestone (4) or (5).

## 2. Two Common Async Approaches in Spring Events

### 2.1. Asynchronous Multicaster

Spring defaults to `SimpleApplicationEventMulticaster` with synchronous dispatch on the thread calling `publishEvent`. When configuring `setTaskExecutor(...)`, `ApplicationListener`s supporting asynchronous execution can run in a pool:

```java
@Bean(name = "applicationEventMulticaster")
ApplicationEventMulticaster eventMulticaster(
        ThreadPoolTaskExecutor eventExecutor) {

    SimpleApplicationEventMulticaster multicaster =
        new SimpleApplicationEventMulticaster();
    multicaster.setTaskExecutor(eventExecutor);
    return multicaster;
}
```

This is an **integration configuration snippet** requiring corresponding Spring imports. If a listener throws an exception on a worker, the exception does not automatically return to the publisher once `publishEvent` has returned. You can configure `SimpleApplicationEventMulticaster.setErrorHandler(...)` to receive/record errors, while designing a separate retry mechanism when needed.

Since Spring Framework 6.1, listeners can decide whether they support async execution via `ApplicationListener.supportsAsyncExecution()`. Certain listeners depending on transaction synchronization must register on the proper thread/context and are not simply dispatched asynchronously by the multicaster.

### 2.2. `@Async @EventListener`

A bean method can also be proxied to run asynchronously:

```java
@Async("eventExecutor")
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    notificationGateway.send(event.orderId());
}
```

This is an **integration pattern** requiring `@EnableAsync`, an executor named `eventExecutor`, and related beans. `@Async` routes through a Spring async proxy; the actual executor used for `@Async` may **differ** from the executor configured on the multicaster.

For async methods returning `void`, failures have no future returned to the caller to call `get()` on; an `AsyncUncaughtExceptionHandler`, logging/metrics, or a corresponding test signal is required. Therefore, tests should not write:

```java
assertThrows(IllegalStateException.class,
    () -> publisher.publishEvent(new OrderPlaced("ORD-42")));
```

and conclude the async listener did not fail just because `assertThrows` failed. Failures can happen **after** the publish call returns.

### Comparison Table

| Mechanism | Where Does the Listener Run? | What Must the Test Wait For? |
| --- | --- | --- |
| Default multicaster | Publisher thread | Can assert after the call if the listener is genuinely synchronous |
| `SimpleApplicationEventMulticaster` with `TaskExecutor` | Worker for listeners supporting async | Listener completion signal and error reporting channel |
| `@Async @EventListener` | Spring Async executor | Handler signal and `AsyncUncaughtExceptionHandler` or future per contract |
| `@TransactionalEventListener` | Bound to a transaction phase | **Real** commit/rollback, then inspect callback |
| Handler only enqueues a job | May finish very quickly | Must await the consumer/job if the test requires final results |

**Important:** `@TransactionalEventListener(phase = AFTER_COMMIT)` does not mean async. It means the callback binds to the commit phase. To test a handler that both runs post-commit and offloads work to another thread, verify **both boundaries**: real commit and async task completion.

## 3. Why `Thread.sleep` and Immediate Assertions Are Often Flaky

### Anti-pattern 1: Fixed Sleep

```java
publisher.publishEvent(event);
Thread.sleep(500);
assertEquals(1, repository.count());
```

This is an **illustrative failure pattern**. If CI is overloaded or downstream takes over 500 ms, it fails despite correct logic. If the handler needs only 5 ms, the test wastes most of its time sleeping. Sleep also fails to communicate **what condition is being awaited**.

### Anti-pattern 2: Polling Without a Timeout

```java
while (!notificationGateway.isDone()) {
    // Waits forever if handler fails or is never invoked.
}
```

Without a deadline, the test can hang forever; busy looping also burns CPU. Proper polling requires an **explicit condition, bounded timeout, clear failure message, and memory visibility**. Awaitility is a common tool when final state has no direct callback.

### Anti-pattern 3: Verifying Only Publish

```java
verify(publisher).publishEvent(any(OrderPlaced.class));
```

This only proves **the publisher-calling layer sent the call**, not that the multicaster registered listeners, handlers executed, or side effects finished.

### Anti-pattern 4: Sharing Plain Mutable Variables Across Threads

```java
boolean handled = false; // No cross-thread visibility guarantee.
// Worker sets handled=true; test thread reads immediately or spins.
```

This is a **failure-illustration snippet**. Never use an unsynchronized `boolean` field as a cross-thread signal. Use `CountDownLatch`, `CompletableFuture`, `BlockingQueue`, `AtomicReference`, or abstractions with proper synchronization semantics. Signals must be emitted **only after** the state to assert has been written.

## 4. Choosing the Right Test Tool for the Job

| Tool | Best Suited For | Advantages | Caveats |
| --- | --- | --- | --- |
| `CountDownLatch` | Knowing how many times a handler must reach a milestone | Exact wait, `await(timeout)`, easy race control | Cannot reset; create fresh per test, handle interrupts |
| `CompletableFuture<T>` | Receiving either a result or an exception per event | `get(timeout)`, `completeExceptionally`, keyed by event ID | Must complete on both success/fail; avoid dangling futures |
| Awaitility | Final outcomes observed in DB/cache/mock/repository | `untilAsserted(...)` with deadline and sensible polling | Does not prove async error paths on its own; avoid unobservable conditions |
| `StepVerifier` | Reactive pipelines `Mono`/`Flux` | Verifies subscriptions, terminal signals, and virtual time where fitting | Does not replace testing side effects outside the pipeline |
| `BlockingQueue` | Events processed multiple times or ordered result extraction | `poll(timeout)`, avoids shared unsynchronized data | Must define ordering expectations if multiple workers exist |

**Rule:** synchronize **by behavior**, not by guessed elapsed time. A timeout is the **maximum allowed wait limit**, not a mandatory delay before asserting. If a handler finishes in 10 ms, `await(10, SECONDS)` usually returns immediately; it does not sleep for 10 full seconds.

With `CountDownLatch`, `countDown()` and `await()` establish proper happens-before semantics, so the test thread sees updates performed before `countDown()` once `await` returns successfully.

## 5. Test Model That Controls Race Conditions

A solid async test often uses three signals:

```text
Test thread                                      Executor thread
    |                                                   |
    +--> publishEvent(OrderPlaced)                      |
    |       |                                           |
    |       +--> submit task --------------------------> |
    |                                                   +--> entered.countDown()
    +--> entered.await(timeout)                         |
    |                                                   +--> release.await(timeout)
    +--> assert listener is still waiting (if needed)   |
    +--> release.countDown() --------------------------> +--> run business logic
    |                                                   +--> result is recorded
    |                                                   +--> finished.countDown()
    +--> finished.await(timeout)                        |
    +--> assert results                                 |
```

The `entered` signal tells the test the listener started running. The `release` signal is a **control gate**: it lets the test verify "publisher returned, listener has not finished yet" without sleeping. The `finished` signal lets the test read results after the completion milestone.

To prevent deadlocks when assertions fail, **always release the gate in `finally`**; otherwise, a failing test can leave workers blocked and hang context shutdown. Section 6's demo uses one thread, bounded gates, and `try-with-resources` to tear down the Spring context.

## 6. Runnable Example: JUnit 5 + Spring 6.1 + Asynchronous Multicaster

We will test the **asynchronous multicaster** directly. This is a Java 17+ project without Spring Boot, a database, or external service calls. It includes:
- `SimpleApplicationEventMulticaster` running `@EventListener` on `ThreadPoolTaskExecutor`.
- `Probe` with `CountDownLatch`, `AtomicReference`, and an error hook via `ErrorHandler`.
- Test 1 verifies the handler runs on a worker, remains blocked after publish returns, and completes cleanly once released.
- Test 2 verifies exceptions from an async handler are observed via `ErrorHandler`, **not** assuming they are rethrown to the publisher.

Each test builds **its own application context**. That keeps latches and results from an earlier test from leaking into the next. We do not need to swap global beans or call sleep.

### 6.1. Directory Structure

```text
async-event-tests/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/AsyncEventListenerTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'async-event-tests'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.21'

    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.3'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

test {
    useJUnitPlatform()
}
```

### 6.2. Complete Test File

`src/test/java/demo/AsyncEventListenerTest.java`:

```java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ApplicationEventMulticaster;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import static org.junit.jupiter.api.Assertions.*;

class AsyncEventListenerTest {

    record OrderPlaced(String eventId, boolean shouldFail) {}

    static final class Probe {
        final CountDownLatch entered = new CountDownLatch(1);
        final CountDownLatch release = new CountDownLatch(1);
        final CountDownLatch finished = new CountDownLatch(1);
        final CountDownLatch errorReported = new CountDownLatch(1);

        final AtomicReference<String> processed = new AtomicReference<>();
        final AtomicReference<String> handlerThread = new AtomicReference<>();
        final AtomicReference<Throwable> error = new AtomicReference<>();

        void captureError(Throwable failure) {
            error.set(failure);
            errorReported.countDown();
        }
    }

    static final class OrderListener {
        private final Probe probe;

        OrderListener(Probe probe) {
            this.probe = probe;
        }

        @EventListener
        public void on(OrderPlaced event) {
            probe.handlerThread.set(Thread.currentThread().getName());
            probe.entered.countDown();

            try {
                if (!probe.release.await(15, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Listener gate timed out");
                }
                if (event.shouldFail()) {
                    throw new IllegalArgumentException("simulated failure");
                }
                probe.processed.set(event.eventId());
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                    "Listener was interrupted", interrupted
                );
            } finally {
                probe.finished.countDown();
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TestConfig {

        @Bean
        Probe probe() {
            return new Probe();
        }

        @Bean
        OrderListener orderListener(Probe probe) {
            return new OrderListener(probe);
        }

        @Bean
        ThreadPoolTaskExecutor eventExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(8);
            executor.setThreadNamePrefix("event-worker-");
            return executor;
        }

        @Bean(name = "applicationEventMulticaster")
        ApplicationEventMulticaster applicationEventMulticaster(
                ThreadPoolTaskExecutor eventExecutor, Probe probe) {
            SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();
            multicaster.setTaskExecutor(eventExecutor);
            multicaster.setErrorHandler(probe::captureError);
            return multicaster;
        }
    }

    @Test
    void waitsForRealCompletionWithoutSleeping() throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(TestConfig.class)) {

            Probe probe = context.getBean(Probe.class);
            try {
                context.publishEvent(new OrderPlaced("EVT-1", false));

                assertTrue(
                    probe.entered.await(10, TimeUnit.SECONDS),
                    "Listener did not start before timeout"
                );
                assertEquals(
                    1L, probe.finished.getCount(),
                    "Handler must still be blocked by release gate"
                );
                assertNull(probe.processed.get());
            } finally {
                // Release even if the assertions above fail.
                probe.release.countDown();
            }

            assertTrue(
                probe.finished.await(10, TimeUnit.SECONDS),
                "Listener did not complete before timeout"
            );
            assertEquals("EVT-1", probe.processed.get());
            assertTrue(
                probe.handlerThread.get().startsWith("event-worker-")
            );
            assertNull(probe.error.get());
        }
    }

    @Test
    void recordsAsyncExceptionViaErrorHandler() throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(TestConfig.class)) {

            Probe probe = context.getBean(Probe.class);
            probe.release.countDown();

            // Do not use assertThrows with publishEvent here.
            context.publishEvent(new OrderPlaced("EVT-2", true));

            assertTrue(
                probe.finished.await(10, TimeUnit.SECONDS),
                "Failing listener did not finish"
            );
            assertTrue(
                probe.errorReported.await(10, TimeUnit.SECONDS),
                "Async failure did not reach ErrorHandler"
            );
            assertNotNull(probe.error.get());
            assertNull(probe.processed.get());
        }
    }
}
```

Run with JDK 17+ and Gradle installed:

```bash
gradle test
```

The target outcome is **2 passing tests**. No fixed stdout is quoted because JUnit/Gradle formatting varies by version and logging level. Under default configuration, Gradle reports the `test` task successful when both methods pass.

### 6.3. Why Is This Example Immune to Common Race-Condition Flakiness?

1. The `applicationEventMulticaster` bean uses an executor instead of the default synchronous multicaster. `OrderListener` handles only `OrderPlaced`, so tests do not confuse Spring lifecycle events with the event under test.
2. `Probe.entered` counts down when the handler begins; `Probe.release` pauses the handler at a test-controlled gate. Therefore, after `entered.await(...)` and before `release.countDown()`, the test knows the handler has not finished yet. There is no assumption that "within 100 ms the handler will definitely run."
3. The listener writes `processed` before `finished.countDown()`. Once `finished.await(...)` succeeds, the test can safely read `processed` via `AtomicReference` and the latch's synchronization.
4. Exceptions from the async handler are forwarded by the multicaster to `ErrorHandler`; the test separately awaits `errorReported` because `finished.countDown()` sits in the handler's `finally` block and can run **before** the error handler receives the exception.
5. The `release` gate is opened in `finally` in test 1. If initial assertions fail, the executor is not left hanging indefinitely. The handler itself also has a 15-second gate timeout, preventing permanent deadlocks.
6. `try-with-resources` closes the context; the Spring-managed `ThreadPoolTaskExecutor` is shut down with the bean lifecycle. Tests avoid static singleton probes, so results and latches are never shared across tests.

**Timeouts are not eliminated entirely:** even correct tests need bounded timeouts to avoid hanging when code breaks. Heavily loaded CI can make a 10-second timeout insufficient. Choose timeouts based on environment characteristics, and when a failure happens, know **which milestone** was being awaited. The difference is that an await deadline creates no intentional race like sleeping and immediately asserting.

### 6.4. Limitations of the Demo

- The demo tests that async errors are **observed** by `ErrorHandler`; `setErrorHandler(probe::captureError)` does not retry work automatically. Production needs dedicated error handling, retries, idempotency, and alerting.
- Test 2 does not assert an exact exception class across all proxy configurations. You can inspect root causes if your system contract requires it; here we assert a `Throwable` was received to avoid coupling to how the framework wraps exceptions.
- The test has no DB; it does not prove commit/rollback. When post-commit testing is needed, write a separate transaction integration test.
- The test verifies the handler ran on a worker thread because the thread name has prefix `event-worker-` set by the executor. Never rely on thread names as a production business condition.
- The test uses one listener and one executor. If multiple listeners subscribe to an event or a listener spawns child tasks, add observation points for each branch that must finish.

## 7. Testing `@Async @EventListener` Properly

With `@Async("eventExecutor") @EventListener`, tests must enable `@EnableAsync` and provide the exact executor used by the proxy. Simply adding the annotation without enabling Spring Async lets the method run synchronously and pass tests **without ever testing async**.

Integration configuration:

```java
@Configuration
@EnableAsync
class AsyncConfig {
    @Bean(name = "eventExecutor")
    ThreadPoolTaskExecutor eventExecutor() {
        ThreadPoolTaskExecutor e = new ThreadPoolTaskExecutor();
        e.setCorePoolSize(2);
        e.setMaxPoolSize(2);
        e.setQueueCapacity(20);
        e.setThreadNamePrefix("async-listener-");
        return e;
    }
}

@Component
class EmailListener {
    @Async("eventExecutor")
    @EventListener
    public void on(OrderPlaced event) {
        emailGateway.send(event.orderId());
    }
}
```

This is an **integration pattern**, not a standalone runnable file. It requires imports for `@Configuration`, `@EnableAsync`, `@Bean`, `@Component`, `@Async`, and `@EventListener`; `OrderPlaced` and `EmailGateway` must also be defined and registered as beans.

When testing `@Async`:
- Place the completion signal **where the side effect occurs** (fake email gateway or listener instrumentation), rather than waiting for the publisher to return.
- If the async method returns `void`, use `AsyncUncaughtExceptionHandler`/an error recorder or test-specific probe to observe failures; exceptions do not become publisher exceptions.
- If a method is invoked via a Spring proxy with a valid return type like `CompletableFuture`, you can call `future.get(timeout, unit)` in a layer receiving the future; however, `@EventListener` callbacks do not automatically return that future to the publisher.
- Avoid calling the listener method directly on a newly constructed `new EmailListener(...)` and claiming `@Async` was tested: without a proxy, the annotation has no effect.
- If using a custom executor, configure it per the qualifier in `@Async("...")`; do not assume it is `SimpleApplicationEventMulticaster`'s executor.

## 8. Testing with `CompletableFuture` Keyed by Event ID

With multiple concurrent events, a shared `CountDownLatch(1)` can report a pass prematurely: event B finishes while the test is waiting for event A. **Bind signals to individual events**.

Illustrative test probe example:

```java
public final class CompletionProbe {
    private final ConcurrentMap<String, CompletableFuture<String>> outcomes =
        new ConcurrentHashMap<>();

    public CompletableFuture<String> expect(String eventId) {
        CompletableFuture<String> fresh = new CompletableFuture<>();
        if (outcomes.putIfAbsent(eventId, fresh) != null) {
            throw new IllegalStateException("Duplicate expectation");
        }
        return fresh;
    }

    public void succeeded(String eventId, String result) {
        CompletableFuture<String> future = outcomes.get(eventId);
        if (future == null) {
            throw new IllegalStateException("Unexpected event: " + eventId);
        }
        future.complete(result);
    }

    public void failed(String eventId, Throwable cause) {
        CompletableFuture<String> future = outcomes.get(eventId);
        if (future == null) {
            throw new IllegalStateException("Unexpected event: " + eventId);
        }
        future.completeExceptionally(cause);
    }
}
```

This is an **integration class** requiring `java.util.concurrent.*` imports and probe lifecycle management; not the main demo file. Register the expectation **before publishing**:

```java
CompletableFuture<String> result = probe.expect("EVT-42");
publisher.publishEvent(new OrderPlaced("EVT-42", false));

assertEquals(
    "email-scheduled",
    result.get(10, TimeUnit.SECONDS)
);
```

This assumes the listener or fake gateway calls `probe.succeeded("EVT-42", "email-scheduled")` once work reaches the tested milestone. If the listener fails, it must call `probe.failed(...)` or report through a separately asserted error channel; never let tests just time out with no diagnostic context. Clean up the expectation map after tests or create a fresh probe per test to prevent memory leaks.

**Do not confuse future completion with actual email delivery:** if the listener merely enqueues an email job, `"email-scheduled"` is an enqueue result. To test delivery, observe a real signal from the worker/transport at the appropriate layer.

## 9. Awaitility: Waiting for Final State Without Direct Callbacks

When outcomes appear in a DB, cache, or fake repository, tests can use Awaitility's `untilAsserted(...)` instead of sleep:

```java
await()
    .atMost(Duration.ofSeconds(10))
    .pollInterval(Duration.ofMillis(50))
    .untilAsserted(() ->
        assertEquals("SENT", emailStatusRepository.findStatus("EVT-42"))
    );
```

This is an **integration snippet** requiring the `org.awaitility:awaitility` dependency, `await()`/`Duration` imports, and repository code. Polling with a timeout ensures the test fails if the outcome never reaches the target state. Pick a sensible poll interval and never insert arbitrary sleeps into business code just to "help tests pass."

Important considerations:
- Wait for **the outcome the business truly cares about**, not just mock call counts if the contract is a DB update.
- If backed by transactions/DB, query in a separate transaction or proper context. A persistence context caching stale entities can make the test keep reading old data.
- If an error handler logs without updating state, Awaitility eventually times out without explaining why. Combine error recorders, logs/traces, and assertion messages.
- Polling too aggressively creates unnecessary load, especially against Testcontainers or real backends.
- With multiple event types, ensure the wait condition matches **the exact event ID** so another event cannot make the test pass accidentally.

## 10. Transactional Event Listeners: Commit Differs from Async

`@TransactionalEventListener` supports `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION`. These are **transaction phases**, not thread-execution guarantees.

A scenario that frequently produces "flaky" or **always-failing** tests:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void on(OrderPlaced event) {
    projectionService.update(event);
}
```

This snippet requires a transaction manager and corresponding beans. If a test runs with Spring Test's `@Transactional` where the framework **automatically rolls back at test end**, the `AFTER_COMMIT` listener will not run. The test is not missing a sleep; it is missing a **real commit**.

To test it:
1. Create a real transaction via `TransactionTemplate`, or manage the test transaction with `TestTransaction` when using Spring Test.
2. Publish the event **inside the transaction**.
3. Finish the transaction by committing.
4. After commit, await side effects if dispatched asynchronously; if purely synchronous callbacks, assert after the commit method returns.
5. Assert **both DB state** and listener invocation count/semantics.

Test rollback separately: publish the event and make the transaction roll back; assert `AFTER_COMMIT` did not run and `AFTER_ROLLBACK` (if present) ran per contract. **Do not enable `fallbackExecution=true` just so tests receive events** if production logic requires "only upon successful commit."

A failing `AFTER_COMMIT` callback cannot roll back the already-committed source DB transaction. If a handler needs to write new DB rows post-commit, it may need a new transaction (e.g., `REQUIRES_NEW` via Spring proxy) rather than assuming the old transaction remains fully active.

### Reactive Transactions

With Spring 6.1 and reactive transactions, transaction-bound events must carry `TransactionContext` as their source, typically via `TransactionalEventPublisher`. `StepVerifier` can test `Mono`/`Flux` signals and commit/rollback completion, yet it does not automatically wait for a detached `subscribe()` invoked inside a listener. Avoid letting a test pass via a manually created subscription outside the transaction context.

## 11. Test Data, Parallel Execution, and Isolation

A test using the right latch can still fail intermittently if test data or contexts are shared improperly.

### 11.1. Avoid Shared Static Mutable State

If a test class holds `static CountDownLatch`, `static AtomicReference`, or `static List<Event>` updated by multiple tests, running JUnit in parallel can cause one test's assertions to observe another test's events. Create **a fresh probe per test** or partition by correlation/event ID and clean up properly.

### 11.2. Give Every Event a Distinct Identity

In integration tests, use distinct `eventId` and `orderId` values per test. Do not assert "at least one event was processed" when multiple events may be in flight. Key `CompletionProbe` by `eventId` or query the DB by the test's own key.

### 11.3. Await All Test-Scoped Work Before Teardown

If an async listener is still running when the Spring context/test container shuts down, it can throw exceptions as dependencies are destroyed. If the next test opens the same DB or mock, leftover tasks can interfere.

A safe pattern:
- Publish.
- Wait for completion/exception signals for **all** events belonging to the test.
- Assert.
- Finally release gates, stop executors per context lifecycle, and close DB/test containers.

For executors, consider `setWaitForTasksToCompleteOnShutdown(...)` when designing production/test infrastructure; do not enable indefinite waiting and forget blocked tasks. Explicit timeouts and `finally` cleanup matter more than a single shutdown setting.

### 11.4. Do Not Overuse `@DirtiesContext`

`@DirtiesContext` helps when Spring context state is genuinely mutated between tests, yet slows suites down by recreating contexts. It does not fix data races, persistence context caches, static state, or still-running tasks. Prefer context/fixture isolation at the right layer.

## 12. Mocking and Confirming Real Failures

Mockito can help when a fake gateway records invocations. However, this snippet:

```java
publisher.publishEvent(event);
verify(gateway, times(1)).send(event);
```

is **wrong for async listeners** if `verify` runs before the handler. You can use Mockito `timeout(...)` to wait for the invocation when this is genuinely a contract test:

```java
publisher.publishEvent(event);
verify(gateway, timeout(10_000).times(1)).send(event);
```

This is an **integration snippet** requiring Mockito. However, `timeout(...)` only proves the method was invoked, not necessarily that I/O finished. When testing state/results, use a real-executing fake with a `CompletableFuture` or Awaitility on final state.

**Negative assertions are harder than positive assertions.** For example, "listener was not called on rollback" should not be concluded simply by waiting 200 ms and seeing nothing. Establish a synchronization point—such as transaction rolled back, executor drained relevant tasks, or a reliable DB invariant—before asserting no side effects occurred. Without synchronization, "not observed yet" does not mean "will never happen."

For failures:
- Instrument the handler to record outcomes into the test's `CompletableFuture`.
- Use `ErrorHandler` on async multicasters when handlers throw exceptions.
- Use `AsyncUncaughtExceptionHandler` for `@Async void`.
- Verify both the error signal and that invalid state was not persisted.
- Never rely solely on `assertThrows(...)` around the publisher once listeners cross threads.

## 13. Load/Concurrency Testing and Processing Order

Not every async test needs to assert ordering. With multi-threaded pools, two listeners can complete in a different order than published. If business rules require ordering:
- Model dependencies or use an executor/queue preserving order per appropriate key.
- Attach sequence/aggregate versions to events when needed.
- Test the **ordering contract** with explicit synchronization rather than scheduler luck.
- With Kafka/RabbitMQ or broker systems, ordering depends on partitions/keys, consumer groups, retries, and acknowledgments; that is a separate infrastructure contract.

To test true concurrency, you can use `CyclicBarrier` or `Phaser` so multiple workers start the same phase together; always set timeouts and match participant counts accurately to avoid deadlocks. `CountDownLatch` fits "wait for N tasks to complete," though it does not guarantee simultaneous execution by itself.

Illustrative snippet waiting for N events:

```java
CountDownLatch allDone = new CountDownLatch(eventIds.size());

for (String eventId : eventIds) {
    publisher.publishEvent(new OrderPlaced(eventId, false));
}

// Each handler calls allDone.countDown() after finishing.
// Structural template; supply allDone in the right scope and avoid double-counting.
assertTrue(allDone.await(10, TimeUnit.SECONDS));
```

If a handler has retries, one logical event can generate multiple attempts. Decide whether the latch counts **attempts** or **completed events**. With fan-out events, one listener finishing its count does not prove the whole workflow finished.

## 14. When to Use Integration Tests vs. Unit Tests?

| Goal | Appropriate Test |
| --- | --- |
| Pure handler logic given an event | Unit test calling handler directly with fake dependencies; no async required |
| Spring registers the listener for the right event type | Spring context integration test |
| Multicaster actually dispatches async and error handler works | Context test with an executor as in section 6 |
| `@Async` proxy and executor qualifier take effect | Spring test enabling `@EnableAsync` |
| DB commits then `AFTER_COMMIT` triggers | Transaction integration test with real commits |
| Queue/broker delivery, retries, and dead-lettering | Integration test with broker/Testcontainers or contract fake |
| Reactive chains and transaction contexts | `StepVerifier`, `Publisher`-based integration tests |
| End-to-end HTTP → DB → event → side effects | End-to-end test with unique IDs and proper completion signals |

**Do not force every unit test to run real async.** Testing handler logic directly is usually fast and easy to debug. Keep just enough integration tests to confirm Spring configuration, dispatch, threading, and error channels behave like production.

## 15. Diagnosing a Flaky Async Test

When a test passes and fails intermittently, check in order:

1. **Is it actually async?** Inspect the executor bean, `@EnableAsync`, proxies, and thread names; do not guess from annotations.
2. **Is the test asserting before the listener finishes?** Switch to `CountDownLatch`, futures, or outcome-based Awaitility.
3. **Are errors being hidden?** Check `ErrorHandler`/`AsyncUncaughtExceptionHandler` and record test-side failures.
4. **Are tasks leaking between tests?** Ensure completion is awaited before teardown and close contexts and executors.
5. **Is shared state thread-safe?** Avoid unsynchronized plain/static global fields.
6. **Is there a register-before-publish race?** With futures keyed by event ID, register expectations **before** publishing.
7. **Is a DB transaction uncommitted or auto-rolled back by the test?** Especially with `AFTER_COMMIT`.
8. **Is stale data being read from the DB?** Clear the persistence context or use an appropriate transaction/query.
9. **Are timeouts adequate for CI?** Base them on test infrastructure SLOs with diagnostics, rather than raising them infinitely.
10. **Is an external dependency flaky?** Use fakes/Testcontainers where fitting; real networks belong in a separate suite.
11. **Does each event have a unique ID?** Prevent old events from accidentally satisfying new test conditions.
12. **Is the test asserting nothing happened?** Establish a "fully drained" milestone before concluding negative assertions.

Add logs with `eventId`, listener name, and thread name for debugging, while never relying on stdout ordering as a pass condition in multithreaded runtimes. When capturing thread dumps on timeout, configure test tooling/CI so failures report blocked threads and pending tasks.

## 16. Pull Request Checklist

- [ ] Clearly identified whether the test targets a sync multicaster, async multicaster, or `@Async`?
- [ ] Asserting **real outcomes**, not merely that `publishEvent` was called?
- [ ] Every wait relies on an observable signal and a bounded timeout?
- [ ] No `Thread.sleep(...)` guessing when a listener finishes?
- [ ] Async errors captured without relying solely on publisher exceptions?
- [ ] If gates are used, released in `finally` even when assertions fail?
- [ ] No latches, futures, or static mutable state shared across tests?
- [ ] Tests use distinct event IDs and register expectations before publishing?
- [ ] Listeners write results before signaling completion?
- [ ] Executors, contexts, and DBs closed so old tasks cannot leak into subsequent tests?
- [ ] With `AFTER_COMMIT`, real commits used and rollbacks tested separately?
- [ ] Enqueuing a job is not confused with final side-effect completion?
- [ ] Tests do not assume cross-worker ordering unless guaranteed by contract?
- [ ] Unit tests used for simple logic; integration tests for dispatch/proxies/transactions?

**Remember:** a non-flaky async listener test never tries to guess "after 500 ms it must be done." It **controls or observes a real completion state**, waits with happens-before primitives and bounded timeouts, captures worker errors too, and cleans up every resource. With Spring Application Events, know precisely which async mechanism is active, because each has different dispatch and error-reporting paths.

## References

- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework 6.1.21 API — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework 6.1.21 API — ApplicationListener](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/ApplicationListener.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [JUnit 5 User Guide — Writing Tests](https://junit.org/junit5/docs/current/user-guide/)
- [Java 17 API — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [Java 17 API — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Awaitility Documentation](https://github.com/awaitility/awaitility/wiki/Usage)
