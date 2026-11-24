# Properly Awaiting Asynchronous Events in Spring Application Events Testing

When a Spring application uses `@Async @EventListener` or an `ApplicationEventMulticaster` configured with an asynchronous executor, calling `ApplicationEventPublisher.publishEvent(...)` **does not mean every listener has finished processing**. A test reading state right after publishing can fail intermittently: passing on fast machines, failing on slow CI. "Fixing" it with `Thread.sleep(1000)` only makes tests slow, flaky, and masks real bugs.

**Properly awaiting** means: identifying an observable listener outcome, registering observation hooks before publishing, waiting **with a bounded timeout**, distinguishing success/failure/timeout, and releasing resources even if assertions fail. Common tools are `CountDownLatch`, `CompletableFuture`, `BlockingQueue`, and `Awaitility` when polling final state. Each tool fits a different test type.

This lesson explains async event semantics, provides a Java 17+ integration test suite with Spring Test/JUnit 5 running a real `@Async @EventListener`, tests completion conditions and exceptions, and clarifies pitfalls involving threads, transactions, retries, ordering, and test lifecycles.

## 1. Understanding What `publishEvent()` Actually Confirms

In Spring Framework, `publishEvent(event)` is the event-publishing API. It does not return a `Future` representing completion of **all listeners**. Semantics depend on configuration:

| Configuration | Where Does the Listener Run? | When `publishEvent` Returns, What Do You Know? |
| --- | --- | --- |
| Regular `@EventListener`; default multicaster | On the publishing thread | Synchronous listeners invoked in this multicast finished or an exception propagated |
| `@Async @EventListener` with `@EnableAsync` | Method submitted to `TaskExecutor` | Task was normally scheduled; **not guaranteed listener finished** |
| Custom `SimpleApplicationEventMulticaster.setTaskExecutor(...)` | Listeners supporting async execution run on executor | Cannot treat return as completion of all listeners |
| `@TransactionalEventListener(AFTER_COMMIT)` | Registers callback per transaction phase; may run later | If transaction has not committed, listener has not necessarily run |
| Event sent to broker/outbox | Outside Spring event bus or out of process | Internal publish completion is not downstream consumer ack |

Spring Framework dispatches synchronously by default. `@Async` is **a configuration change**; it does not mean "all application events are async by default." Similarly, when a custom multicaster uses an executor, not every listener can be pushed onto another thread; some transactional listeners must execute on the caller thread to register transaction synchronization.

~~~text
Test thread
   |
   +-- publishEvent(JobRequested)
   |       |
   |       +-- Spring listener adapter
   |               |
   |               +-- @Async proxy: submit task
   |                               |
   +-- publishEvent() returns      |       [TEST NOT CONCLUDED YET]
   |                               |
   +-- test awaits specific signal |
                                   +-- worker thread runs listener
                                           |
                                           +-- write DB/call service
                                           +-- update result
                                           +-- report completed/failed
   |
   +-- assertion once result is observed
~~~

An async listener can also throw an exception that the `publishEvent` caller **never sees directly**. For `@Async` `void` methods, Spring routes uncaught exceptions to `AsyncUncaughtExceptionHandler` or default logging. Hence a test checking "publish does not throw" **does not** prove the listener succeeded.

## 2. Five Principles for Non-Flaky Async Tests

1. **Pick the right signal:** `started` means the listener began; `completed` means the tested processing finished. Never conflate the two signals.
2. **Register before publishing:** create latches/futures/queues, spies, or `eventId`-keyed records **before** calling `publishEvent`, avoiding listeners finishing faster than the test sets up observation.
3. **Always use a bounded timeout:** `await(5, SECONDS)`, `future.get(5, SECONDS)`, or `Awaitility.await().atMost(...)`; never call unbounded `get()`/`join()` in tests.
4. **Report failures too, not just completion:** a completion latch placed in `finally` only proves the task exited, not that processing succeeded. Capture exceptions and assert results.
5. **Clean up state and release workers:** clear test data, release gates in `finally`/`@AfterEach`, and close contexts/executors per lifecycle so suites do not leak threads or affect subsequent tests.

**Signals should reflect business behavior**. If a listener updates a DB record, verify the DB state is actually visible; if it calls a gateway, check gateway invocations or acknowledgements; if it executes side-effect-free logic, tests can use a `CompletableFuture<Result>` in a probe/fixture to report outcomes.

## 3. `CountDownLatch`: Waiting for a Listener or Opening a Control "Gate"

A common latch waits for the listener to signal completion:

~~~java
CountDownLatch done = new CountDownLatch(1);

@Async
@EventListener
public void onEvent(JobRequested event) {
    try {
        process(event);
    } finally {
        done.countDown();
    }
}
~~~

This is an **illustrative excerpt**, not a standalone Java class. With `finally`, the test knows the method reached its end regardless of success or failure. If the test needs to confirm success, record the outcome or error separately.

In the test:

~~~java
publisher.publishEvent(new JobRequested("job-1"));
assertTrue(done.await(5, TimeUnit.SECONDS),
    "Async listener did not finish");
~~~

Do not use:

~~~java
publisher.publishEvent(new JobRequested("job-1"));
Thread.sleep(1000);
assertEquals("DONE", repository.findStatus("job-1"));
~~~

The `Thread.sleep` snippet is an **anti-pattern**: it waits unnecessarily if the listener finishes in 10 ms, yet still fails if CI needs 1500 ms. Sleep also fails to distinguish an unscheduled task, an exception, a deadlock, or a downstream timeout.

### Two Latches: `started` and `release`

To prove a listener **genuinely runs asynchronously**, use one latch signaling method entry and one latch acting as a wait gate:

~~~text
test: publish -> await(started) -> assert(!finished) -> release
                   ^                                     |
                   |                                     v
worker:        countDown(started) -> await(release) -> process -> complete
~~~

This avoids unstable timing assertions like "`publishEvent` must return in under 20 ms." The test controls a clear logical condition: **until released, the listener cannot finish**. Section 6's complete test uses this technique.

## 4. `CompletableFuture`: Capturing Success, Errors, and Timeouts

`CompletableFuture<T>` is helpful when you want both the final result and any failure cause:

~~~java
CompletableFuture<String> result = new CompletableFuture<>();

// Inside listener:
try {
    String status = process(event);
    result.complete(status);
} catch (Exception ex) {
    result.completeExceptionally(ex);
    throw ex;
}

// In test, with timeout:
String actual = result.get(5, TimeUnit.SECONDS);
assertEquals("DONE", actual);
~~~

This is an **excerpt**, assuming `process` throws `RuntimeException` or handles checked exceptions appropriately. Do not share a single `CompletableFuture` across all events when tests emit multiple events closely together: bind futures to specific IDs.

Outcomes when waiting via `get(timeout, unit)`:

| Outcome | Meaning |
| --- | --- |
| Returns `T` | Future completed successfully |
| Throws `ExecutionException` | Future completed exceptionally; inspect `getCause()` |
| Throws `TimeoutException` | Not completed before timeout; **does not prove the task failed** |
| Throws `InterruptedException` | Waiting thread was interrupted; preserve interrupt contract |

**`CompletableFuture.join()` accepts no direct timeout parameter**; in tests prefer `get(5, TimeUnit.SECONDS)`. `orTimeout(...)` can configure a limit on the future, yet it mutates that future's completion state; it is not the only option and does not replace cancellation/resource cleanup.

Important note: `@Async @EventListener` does not make `ApplicationEventPublisher.publishEvent` return a `CompletableFuture`. The future in the example is a **test probe/application contract you design**, not the event publisher's return value. Spring also does not support using an **async event listener's return value** to auto-publish a new event; to do that, call `ApplicationEventPublisher` explicitly inside the listener.

## 5. Awaitility and Eventual Assertions: When Observing Final State

If a listener writes to a DB, cache, or repository state, sometimes you should not put latches into business code solely for tests. In that case use **Awaitility** to repeat assertions until the state becomes accurate:

~~~groovy
// additional test dependency (build.gradle excerpt):
testImplementation 'org.awaitility:awaitility:4.2.0'
~~~

~~~java
// Excerpt inside a JUnit test:
await()
    .atMost(Duration.ofSeconds(5))
    .pollInterval(Duration.ofMillis(50))
    .untilAsserted(() ->
        assertEquals("DONE", statusRepository.findStatus("job-1"))
    );
~~~

Requires `import static org.awaitility.Awaitility.await;`, `java.time.Duration`, and the repository fixture. Each poll must be a read **with little or no side effects**. Never repeat `submitOrder()` or `publishEvent()` inside `untilAsserted`: doing so emits multiple events from the test itself and can cause duplicate side effects.

### Choosing Latch, Future, or Awaitility

| Goal | Suitable Tool | Pitfall |
| --- | --- | --- |
| Waiting for a "started" signal | `CountDownLatch` | Started does not mean succeeded |
| Waiting for an event's result or exception | `CompletableFuture<T>` | Must propagate/map results to the right `eventId` |
| Receiving items from an event stream | `BlockingQueue<T>.poll(timeout)` | One `poll` takes one element, not all |
| Waiting for final DB state | `Awaitility.untilAsserted` | Avoid polling inside a transaction seeing an old snapshot |
| Waiting for N known tasks | `CompletableFuture.allOf(...).get(timeout)` | Fail-fast/late errors must be collected separately |
| Simulating controlled order/races | `started` + `release` latches | Must release gates in `finally` |
| Checking a mock call occurred | Mockito `verify(..., timeout(...))` | Invocation does not prove work finished |

`Awaitility` fits when business outcomes are externally observable; latches/futures help when you must control **exact execution timing** or verify failures. For critical integration tests, you can combine them: a future signals "listener finished," then query the database to verify real persisted data.

## 6. Complete Java 17+ Integration Test Suite: Real `@Async` Listener Execution

The following example uses **Spring Framework 6.2.x**, JUnit 5, and a `ThreadPoolTaskExecutor` with **one worker thread** to control ordering in the fixture. It does **not** turn the executor synchronous: the listener genuinely runs through the `@Async` proxy. Each event has its own `eventId` and a `Work` object holding a started signal, release gate, completion future, and uncaught-error future.

There are four tests:

1. Publisher returns while listener is still blocked; after release, the future completes.
2. Listener throws an exception: publisher receives no async exception, yet both the future and `AsyncUncaughtExceptionHandler` record the error.
3. Timeout-bounded await is verified without hanging the suite; afterward, release and confirm completion.
4. Multiple events: `CompletableFuture.allOf` awaits all tasks without relying on sleep.

### 6.1. `settings.gradle` and `build.gradle`

`settings.gradle`:

~~~groovy
rootProject.name = 'async-event-waiting-tests'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation platform('org.springframework:spring-framework-bom:6.2.9')
    testImplementation 'org.springframework:spring-context'
    testImplementation 'org.springframework:spring-aop'
    testImplementation 'org.springframework:spring-test'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Framework's `spring-context` module includes `ApplicationEventPublisher`, `@EventListener`, `@EnableAsync`, and `ThreadPoolTaskExecutor`. `spring-aop` powers async proxying, while `spring-test` provides `@SpringJUnitConfig`. In a Spring Boot project, let Boot manage Spring versions rather than forcing incompatible standalone modules.

### 6.2. File `src/test/java/example/events/AsyncEventWaitingTest.java`

~~~java
package example.events;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.lang.reflect.Method;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(AsyncEventWaitingTest.Config.class)
class AsyncEventWaitingTest {

    @Autowired ApplicationEventPublisher publisher;
    @Autowired Probe probe;

    @AfterEach
    void releaseAnyBlockedWorkers() {
        // If an assertion fails midway, do not leave workers stuck.
        probe.releaseAll();
    }

    @Test
    void waitsForActualCompletionNotMerelyPublication() throws Exception {
        Work state = probe.register("one");

        try {
            publisher.publishEvent(new WorkRequested("one", false));

            assertTrue(state.started.await(5, TimeUnit.SECONDS));
            // Worker has started, yet is waiting on the release gate.
            assertFalse(state.completed.isDone());
        } finally {
            state.release.countDown();
        }

        String threadName = state.completed.get(5, TimeUnit.SECONDS);
        assertTrue(threadName.startsWith("events-"));
        assertFalse(state.uncaught.isDone());
    }

    @Test
    void asyncExceptionIsObservableWithoutEscapingPublisher()
            throws Exception {
        Work state = probe.register("fail");

        try {
            // Does not throw from listener body at publish time:
            // listener only runs after release on the worker thread.
            publisher.publishEvent(new WorkRequested("fail", true));
            assertTrue(state.started.await(5, TimeUnit.SECONDS));
        } finally {
            state.release.countDown();
        }

        ExecutionException exception = assertThrows(
            ExecutionException.class,
            () -> state.completed.get(5, TimeUnit.SECONDS)
        );

        IllegalStateException root = assertInstanceOf(
            IllegalStateException.class,
            exception.getCause()
        );
        assertEquals("boom:fail", root.getMessage());

        Throwable asyncError = state.uncaught.get(5, TimeUnit.SECONDS);
        assertInstanceOf(IllegalStateException.class, asyncError);
        assertEquals("boom:fail", asyncError.getMessage());
    }

    @Test
    void timeoutIsBoundedAndDoesNotLeaveWorkerBlocked()
            throws Exception {
        Work state = probe.register("slow");
        publisher.publishEvent(new WorkRequested("slow", false));

        try {
            assertTrue(state.started.await(5, TimeUnit.SECONDS));
            // Gate is still closed, so completion definitely cannot happen yet.
            assertThrows(
                TimeoutException.class,
                () -> state.completed.get(100, TimeUnit.MILLISECONDS)
            );
        } finally {
            state.release.countDown();
        }

        assertTrue(state.completed.get(5, TimeUnit.SECONDS)
            .startsWith("events-"));
    }

    @Test
    void waitsForAllKnownEvents() throws Exception {
        Work first = probe.register("a");
        Work second = probe.register("b");

        try {
            publisher.publishEvent(new WorkRequested("a", false));
            publisher.publishEvent(new WorkRequested("b", false));

            // Fixture has one worker; event a is holding the gate.
            assertTrue(first.started.await(5, TimeUnit.SECONDS));
            first.release.countDown();

            assertTrue(second.started.await(5, TimeUnit.SECONDS));
            second.release.countDown();

            CompletableFuture.allOf(
                first.completed, second.completed
            ).get(5, TimeUnit.SECONDS);

            assertTrue(first.completed.isDone());
            assertTrue(second.completed.isDone());
        } finally {
            first.release.countDown();
            second.release.countDown();
        }
    }

    record WorkRequested(String id, boolean fail) { }

    static class Work {
        final CountDownLatch started = new CountDownLatch(1);
        final CountDownLatch release = new CountDownLatch(1);

        final CompletableFuture<String> completed =
            new CompletableFuture<>();

        final CompletableFuture<Throwable> uncaught =
            new CompletableFuture<>();
    }

    static class Probe {
        private final ConcurrentHashMap<String, Work> states =
            new ConcurrentHashMap<>();

        Work register(String id) {
            Work result = new Work();
            if (states.putIfAbsent(id, result) != null) {
                throw new IllegalArgumentException("duplicate id: " + id);
            }
            return result;
        }

        Work require(String id) {
            Work state = states.get(id);
            if (state == null) {
                throw new IllegalArgumentException("unknown id: " + id);
            }
            return state;
        }

        void releaseAll() {
            states.values().forEach(w -> w.release.countDown());
        }
    }

    static class AsyncWorkerListener {
        private final Probe probe;

        AsyncWorkerListener(Probe probe) {
            this.probe = probe;
        }

        @Async("eventsExecutor")
        @EventListener
        public void onWork(WorkRequested event) {
            Work state = probe.require(event.id());
            state.started.countDown();

            try {
                if (!state.release.await(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                        "gate timed out:" + event.id()
                    );
                }

                if (event.fail()) {
                    throw new IllegalStateException(
                        "boom:" + event.id()
                    );
                }

                state.completed.complete(
                    Thread.currentThread().getName()
                );
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                state.completed.completeExceptionally(ex);
                throw new IllegalStateException(
                    "listener interrupted", ex
                );
            } catch (RuntimeException ex) {
                state.completed.completeExceptionally(ex);
                throw ex;
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync(proxyTargetClass = true)
    static class Config implements AsyncConfigurer {

        // AsyncConfigurer is initialized very early. Do not inject
        // complex dependencies into exception-handling configuration.
        private final Probe probe = new Probe();

        @Bean
        Probe probe() {
            return probe;
        }

        @Bean
        AsyncWorkerListener workerListener(Probe probe) {
            return new AsyncWorkerListener(probe);
        }

        @Bean("eventsExecutor")
        ThreadPoolTaskExecutor eventsExecutor() {
            ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(16);
            executor.setThreadNamePrefix("events-");
            return executor;
        }

        @Override
        public AsyncUncaughtExceptionHandler
                getAsyncUncaughtExceptionHandler() {
            return (Throwable ex, Method method, Object... args) -> {
                if (args.length == 1
                        && args[0] instanceof WorkRequested event) {
                    probe.require(event.id()).uncaught.complete(ex);
                }
            };
        }
    }
}
~~~

### 6.3. Running the Tests and Expected Outcomes

With the Gradle wrapper included in the project:

~~~bash
./gradlew test --tests "example.events.AsyncEventWaitingTest"
~~~

On Windows PowerShell:

~~~powershell
./gradlew.bat test --tests "example.events.AsyncEventWaitingTest"
~~~

**There is no fixed stdout printed by the four tests themselves**; what matters are the JUnit 5 assertions. Expected outcomes when the configuration works properly:

| Test | Expected Observable Result |
| --- | --- |
| `waitsForActualCompletionNotMerelyPublication` | Listener reports started; completion absent while gate is closed; opening gate lets future return a thread name starting with `events-` |
| `asyncExceptionIsObservableWithoutEscapingPublisher` | Publish does not throw listener's error; future throws `ExecutionException` with cause `IllegalStateException("boom:fail")`; async uncaught handler also receives the error |
| `timeoutIsBoundedAndDoesNotLeaveWorkerBlocked` | `get(100, MILLISECONDS)` throws `TimeoutException` while gate is closed; after release, future completes |
| `waitsForAllKnownEvents` | `allOf(...).get(timeout)` completes after both work units are released and processed |

The tests do not measure execution duration to infer async via millisecond thresholds, do not need `Thread.sleep`, and do not depend on log text. `@AfterEach` releases any held gates if an assertion fails, preventing workers from holding resources indefinitely.

**Why use a single worker in the fixture?** So the multi-event test has a clearly controlled sequence. This is not a promise that production `@Async` always processes in order. With multi-worker executors, start and completion orders can differ. In practice, assert **result sets** or total successes whenever ordering is not a business requirement.

**Why not return a Future directly from the listener?** `@Async @EventListener` methods typically declare `void`; `publishEvent` does not collect listener return values. `Probe` is an intentional testing channel tying `eventId` to completion signals. For production code that must return results to callers, an explicit service method returning `CompletableFuture` may fit better than fire-and-forget events.

## 7. Verifying Exceptions and True Completion Criteria

A `done.countDown()` latch in `finally` reports exiting `try`, yet does not tell whether `process()` succeeded. Avoid the following test:

~~~java
// Semantically WRONG if done counts error branches too:
publisher.publishEvent(event);
assertTrue(done.await(5, TimeUnit.SECONDS));
// From this you MUST NOT infer an email was sent or DB updated.
~~~

In the complete test, `completed.completeExceptionally(ex)` lets JUnit inspect `ExecutionException.getCause()`. Simultaneously, `getAsyncUncaughtExceptionHandler()` proves exceptions from `void` async methods are handled **outside** the publisher's return path.

Identify the **actual completion point**:

- `listener.started`: the method entered its body.
- `repository.save(...)` called: invocation happened; transaction may not have committed yet.
- `gateway.send(...)` returned: meaningful only per gateway's contract; end client may not have received it yet.
- DB transaction commit: data persisted per isolation/transaction policy.
- Broker ack: broker acknowledged per acks mode; consumer may not have processed it yet.
- Future complete success: application-defined outcome finished.

If a listener has multiple steps and only the first signals the latch, the test can pass while later steps fail. Therefore, place the `completed` signal **after** all operations to prove, while recording exceptions in every possible failure branch.

### When Verifying Side Effects via Mockito

A JUnit/Mockito example might use:

~~~java
verify(notificationGateway, timeout(5000))
    .sendReceipt("ORD-1");
~~~

This is an **excerpt** requiring an injected `notificationGateway` mock and `import org.mockito.Mockito.timeout`. Mockito's `timeout` mechanism waits until the invocation occurs (or expires), yet **invocation does not guarantee the method finished all side effects**. When verifying final state/acks, await the corresponding observable outcome.

## 8. `@Transactional` and `@TransactionalEventListener` Complicate Wait Timing

### 8.1. Publishing Inside a Transaction and Awaiting an Async Listener Can Deadlock

~~~text
test/service thread:
  BEGIN TX
  UPDATE order = PAID             [not committed yet]
  publish OrderPaid
  future.get(timeout)             [waiting for listener]

async listener worker:
  SELECT order from another transaction
  waits for data/lock or reads old state
  cannot complete under test conditions

test/service thread has not committed because it is waiting on future
~~~

This bug cannot be fixed merely by increasing the timeout. If the listener's side effect needs committed data, **never wait for it inside the still-open source transaction**. Finish the transaction before waiting, or use a transaction-phase listener and test transaction boundaries actively.

### 8.2. Awaiting `AFTER_COMMIT` Requires Actually Committing

With `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`, the callback binds to successful commit. In Spring TestContext, an `@Transactional` test normally **rolls back at the end of the test**, so the after-commit callback never runs while the test remains inside that transaction.

A pattern using `TransactionTemplate` in a non-`@Transactional` test:

~~~java
transactionTemplate.executeWithoutResult(status -> {
    service.writeData();
    publisher.publishEvent(new OrderPaid("O-1"));
}); // transaction commits here if not rolled back

// Only after transaction committed, await observable async outcome:
await()
    .atMost(Duration.ofSeconds(5))
    .untilAsserted(() ->
        assertEquals("SENT", deliveryRepository.findStatus("O-1"))
    );
~~~

This is an **excerpt** requiring `transactionTemplate`, `service`, `publisher`, `deliveryRepository`, and Awaitility. When using a test-managed transaction, Spring provides `TestTransaction.flagForCommit()` and `TestTransaction.end()` where appropriate, though commit boundaries must be controlled explicitly.

**Note:** configuring a custom multicaster executor does not mean every `@TransactionalEventListener` runs on a pool thread. Some transactional listeners must run on the caller thread to register synchronization. To run business work asynchronously **after commit**, design the callback/async executor and security/tracing context explicitly, then test the final execution path.

### 8.3. Async Does Not Automatically Carry Transactions, `SecurityContext`, or MDC

JDBC transactions, `SecurityContextHolder`, and MDC are typically thread-bound in imperative environments. `@Async` switches to another executor thread; they do not propagate fully without a propagation mechanism. If a listener checks user permissions, consider `DelegatingSecurityContextAsyncTaskExecutor`; if trace correlation is needed, use appropriate context propagation or verified correlation IDs in the event payload.

With the reactive stack, Reactor subscriber Context and `TransactionalEventPublisher` have separate mechanics; you cannot copy JDBC thread-local assumptions onto R2DBC.

## 9. Avoiding Flaky Tests with Multiple Events and Multiple Listeners

### 9.1. Use a Unique ID per Event

A single test can publish the same event type multiple times. With a global `CountDownLatch` or future, an earlier event's signal can let a later event's test "false-pass." Attach independent `eventId`s so every outcome is traceable:

~~~text
event-101 -> future-101
event-102 -> future-102
event-103 -> future-103
~~~

When multiple tests run in parallel, use suite-wide unique IDs or isolated contexts/probes. Never use `Thread.sleep` to "wait for old events to finish" before the next test.

### 9.2. Do Not Assume Ordering with Multi-Threaded Executors

`@Order` orders listener invocations for the same event per dispatch semantics; **it does not guarantee completion order of async work**. If multiple listeners write to the same state, define concurrent behavior explicitly. Tests should await all relevant tasks and compare result sets when order does not matter.

If business rules **genuinely require ordering**, enforce it in the processing mechanism—single-threaded executor/partitioning per key, sequencer, or workflow orchestration—rather than tweaking tests to expect a lucky order.

### 9.3. Counting Completed Events Accurately

With N known tasks, `CountDownLatch(N)` can wait for N completions. However, if a listener is invoked more than N times, the latch reaches 0 and the test can still pass unless you verify **exact event IDs, uniqueness, and side effects**. Similarly, `allOf` tracks only registered futures; it does not prove unexpected events never occurred.

When verifying "exactly one invocation," use mock invocations/counters keyed by event ID and `verifyNoMoreInteractions` or matching assertions; remember another async listener might still be running, so ensure the suite reaches a steady state before checking no extra events arrived.

## 10. Timeouts, Cancellation, and Cleanup: Three Different Concerns

A timeout does not automatically stop a listener.

| What Happens in Test | Consequence |
| --- | --- |
| `future.get(timeout)` throws `TimeoutException` | Test thread stops waiting; worker may still be running |
| `latch.await(timeout)` returns `false` | Not enough signals before deadline; task may finish late |
| `future.cancel(true)` | May send interrupt/cancellation; task has not necessarily stopped |
| Executor shutdown | Depending on config, may wait for or interrupt running tasks |
| Task exception | Must be recorded and asserted; never misinterpret as a timeout |

Put release/cleanup in `finally` to prevent the whole suite from hanging when one assertion fails. If tests place a latch inside a listener, ensure the listener cannot hold a thread forever when the test context closes. In production, enforce timeouts on client I/O (HTTP, JDBC, brokers) as well, not only test timeouts.

**Do not use `assertTimeoutPreemptively` mechanically with thread-bound transactions/contexts.** JUnit may execute test code on a separate thread, losing Spring TestContext transaction or security `ThreadLocal` state. For async events, placing timeouts directly on the awaited signal and letting the framework clean up lifecycles normally is usually clearer.

## 11. Does `@RecordApplicationEvents` Solve Waiting for Listeners?

Spring TestContext supports `@RecordApplicationEvents` and `ApplicationEvents` to inspect application events published during a test. They are useful for confirming **an event was emitted** and checking payloads.

However, an event appearing in the recorded list **does not prove async listeners finished processing**. For instance, a test can assert `OrderCreated` was published while an `@Async` email listener is still waiting for pool scheduling. Therefore:

- **Testing event emission:** use `ApplicationEvents`, event spies, or suitable publisher fixtures.
- **Testing async handling:** await completion/side effects with a timeout.
- **Testing commit:** explicitly conclude the transaction before checking after-commit behavior.
- **Testing errors:** await an error channel/handler, not just that `publishEvent` did not throw.

When all four stages must be proven, write separate, clearly named assertions so failures immediately pinpoint publication, scheduling, business handling, or transactions.

## 12. Difference Between Deterministic Tests and a Fake Synchronous Executor

A shortcut is replacing the executor with `SyncTaskExecutor`. This can help for isolated business-logic unit tests, yet **changes execution semantics**:

~~~java
@Bean("eventsExecutor")
TaskExecutor eventsExecutor() {
    return new SyncTaskExecutor();
}
~~~

This snippet is **for test mode only**, requiring `TaskExecutor` and `SyncTaskExecutor` imports. When applied, async work can run on the caller thread; `publishEvent` can block until processing completes, and exception/transaction/security contexts can differ from production. Never use a synchronous test executor as **proof** that the real async pipeline has no races, deadlocks, propagates context, or loses no events.

A solid testing strategy typically includes:

1. Pure business-logic unit tests, with no async needed.
2. Integration tests using a real async executor and timeout-bounded signals (as in section 6).
3. System tests with a real database/broker or Testcontainers when high observability/durability is required, covering failures, retries, duplicates, and shutdown.

## 13. Diagnostic Table When Async Event Tests Are Flaky

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| DB assertion right after `publishEvent` randomly passes/fails | Listener has not finished | Await final state with a timeout |
| Test hangs forever | `get()`/`join()` without deadline or gate never released | Use `get(timeout)`, `finally`, check deadlocks |
| Publish returns yet email never sends | Async listener failed or task lost | Check `AsyncUncaughtExceptionHandler`, outcomes/queue, and delivery contract |
| Latch signals done yet business assertion fails | `countDown` in `finally` fires even on errors | Record failures separately and assert success |
| `@Transactional` test misses after-commit listener | Test transaction uncommitted, rolls back by default | Commit explicitly with `TransactionTemplate`/`TestTransaction` |
| Test passes with `SyncTaskExecutor` yet fails on prod pool | Different threading/timing semantics | Use a real async executor in integration tests |
| Listener runs synchronously despite `@Async` | Missing `@EnableAsync`, self-invocation, unproxied call | Inspect beans/proxies/executor threads |
| Listener errors yet `assertThrows` around publisher misses it | Exception occurs on worker thread | Expose result/error future or `AsyncUncaughtExceptionHandler` |
| Consecutive events cross-contaminate results | Shared probe/global latch without IDs | Per-event correlation keys, reset fixtures |
| Test depends on completion order of two listeners | Pool scheduling has no ordering guarantee | Assert result sets or implement real ordering |
| `await().untilAsserted(...)` still misses DB changes | Test holds an open transaction snapshot/lock | Read after commit; verify isolation and transaction boundaries |
| Tasks get rejected at runtime/shutdown | Executor queue full/shutting down | Test rejection policies, logging, and draining |

**Never inflate timeouts dramatically just to hide an identifiable race or deadlock.** Reasonable timeouts should suffice for normal CI, while failure reasons must be logged and described clearly; long waits only make root causes harder to find.

## 14. Application Checklist

- [ ] Distinguished synchronous listeners, `@Async`, and custom multicaster executors.
- [ ] `@EnableAsync` is enabled and listeners are genuinely proxied by Spring.
- [ ] Latches/futures/spies are registered before publishing, bound to unique event IDs.
- [ ] Asserting true completion conditions (result, DB state, gateway ack), not just listener started.
- [ ] Bounded timeouts used everywhere; no `Thread.sleep` as test synchronization.
- [ ] Success, exceptional completion, and timeout distinguished cleanly.
- [ ] No tasks left stuck when assertions fail: release in `finally` and shut down executors per lifecycle.
- [ ] No assumed completion order across multiple worker threads.
- [ ] Never awaiting after-commit work inside an uncommitted source transaction.
- [ ] Async exceptions verified via handlers/observable outcomes.
- [ ] Tests do not accidentally run under a synchronous executor differing from production.
- [ ] For eventual state, polling is read-only and executes after proper commit.
- [ ] `ApplicationEvents` recording publication is not treated as proof consumers finished.
- [ ] No assumption that `@Async` adds retries or durability to events.

## 15. Self-Check Questions

**Question 1:** Why does `publishEvent(...)` returning not prove an `@Async @EventListener` finished?

Because the publisher normally just hands the invocation to an async proxy/executor while the worker continues afterward. Spring does not return an aggregate `Future` for listeners.

**Question 2:** Why is `Thread.sleep(1000)` not a proper waiting strategy?

Because 1000 ms can be too long when tasks are fast and too short when CI is slow. It fails to explain why a test failed and causes flaky tests.

**Question 3:** Does a `done` latch counted down in `finally` prove the listener succeeded?

No. It can count down to 0 even when an exception occurred. A result/error channel like `CompletableFuture` or side-effect verification is required.

**Question 4:** How does `CompletableFuture.get(5, SECONDS)` differ from `join()`?

`get(timeout, unit)` enforces a wait limit and distinguishes `TimeoutException` from `ExecutionException`; `join()` takes no direct timeout argument and throws `CompletionException` on failure.

**Question 5:** Why shouldn't you await an after-commit listener inside an unfinished `@Transactional` test?

Because the callback requires transaction commit before executing, while the test may hold the transaction open waiting for that very callback. TestContext also typically rolls back after the test.

**Question 6:** When is Awaitility better than a latch?

When observing final state (e.g., DB status `SENT`) without injecting test-only latches into business code. Polling assertions should be side-effect-free and timeout-bounded.

**Question 7:** Is enabling `SyncTaskExecutor` in tests enough to prove an async system is safe?

No. It bypasses threading, transaction/context boundaries, and races of production executors. At least one integration test with a real async executor is needed.

**Remember:** **Properly awaiting asynchronous events means waiting for a verifiable completion signal, with a timeout and an explicit error path.** `CountDownLatch` controls timing, `CompletableFuture` carries results/errors, and `Awaitility` observes eventual state. Never treat `publishEvent` returning or an arbitrary sleep as proof a listener succeeded.

## References

- [Spring Framework – Application Events and Asynchronous Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework – Task Execution and Scheduling, @Async](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework – EnableAsync and AsyncConfigurer API](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/scheduling/annotation/AsyncConfigurer.html)
- [Spring Framework – SimpleApplicationEventMulticaster API](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework – TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
- [Spring Framework – Test Execution Events](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/test-execution-events.html)
- [Awaitility documentation](https://github.com/awaitility/awaitility/wiki/Usage)
