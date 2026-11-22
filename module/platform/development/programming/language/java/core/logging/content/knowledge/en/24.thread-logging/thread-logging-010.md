# Concurrency Testing for Logging in Java

## 1. Why Does Logging Need Concurrency Testing?

In a Java application, multiple requests, `ExecutorService` tasks, callbacks, and workers can invoke a logger simultaneously. Although common logging backends have mechanisms to support concurrent calls, **configuration, custom appenders, buffers, formatters, and context propagation** can still introduce bugs. A feature that works correctly on a single thread does not necessarily log accurately when dozens of threads are active at the same time.

Typical failure examples:

- Two threads concurrently modify a shared `StringBuilder` before logging, causing messages to be interleaved or corrupted.
- A custom appender stores records in an `ArrayList` without synchronization: the resulting size or collected data can be wrong under contention.
- A `request_id` or `trace_id` value in `ThreadLocal`/MDC is retained after a request completes and appears in another request's logs when a thread pool reuses the thread.
- Context is not propagated to a `CompletableFuture` or executor, so asynchronous logs are missing `trace_id`.
- An async appender with a bounded queue drops records under high load; a check running immediately after `logger.info(...)` reads the sink too early and reports missing logs.
- A test assumes an absolute ordering of logs from different threads, causing flaky failures even though both the application and the logger are correct.

The goal of **logging concurrency testing** is to prove observable invariants: every event requested to be logged is represented according to policy, without corruption or misattributed context, and the system flushes/outputs logs properly under the chosen load. You must distinguish unintentional record loss due to bugs from **intentional** filtering or dropping by log level, sampling, or overload policies.

## 2. Properties to Verify

| Property | What to Check | What Not to Assume |
| --- | --- | --- |
| **Completeness** | For an unfiltered synchronous sink, capture exact `threads × eventsPerThread` records | Async/sampling always retains 100% of logs |
| **No duplicates** | Each event key `(workerId, sequence)` appears once | Counting total records equal to expected proves no duplicates |
| **No data corruption** | Message, level, payload, timestamp, and event ID match original values | Multiple threads can safely mutate a shared mutable payload |
| **Correct context** | `request_id`, `trace_id`, `span_id` belong to the task that emitted the log | `ThreadLocal`/MDC automatically follows across new threads |
| **No context leakage** | After a task finishes, the previous request's values are restored or cleared | Executor threads are always fresh |
| **Meaningful ordering** | If the sink has a per-producer ordering contract, verify that ordering | There is a fixed global order across threads |
| **Shutdown and flush** | Queued records are processed after completion/flush signals per contract | Returning from a logger call means the backend has finished writing |
| **Overload handling** | Correct blocking, backpressure, retry, drop behavior, or dropped-event count | Every async configuration is lossless |

Do not check `size()` alone. If one event appears twice and another is missing, the total count can still match. Verify by **unique identifier and per-event content**, and only then check the total count.

### Distinguishing Thread Safety from Log Ordering

Thread safety means concurrent operations uphold the object's contract and do not corrupt state; it **does not mean** two threads are scheduled in the same order on every run. Given two threads A and B:

```text
Thread A: A1 -> A2
Thread B: B1 -> B2
```

The sink might observe `A1, B1, B2, A2` or `B1, A1, A2, B2`. If each thread logs synchronously and sequentially, you can usually verify per-thread ordering according to the sink's contract. Once logs pass through an async queue, batching, multiple partitions, or a distributed pipeline, you must read the **specific ordering contract** before asserting the order observed at the storage destination.

## 3. Designing a Reliable Test

A repeatable concurrency test should include the following parts:

1. **Isolate the sink:** use a test-only appender/event receiver; do not depend on the console, a shared log file, or state from other tests.
2. **Synchronize the start point:** use `CountDownLatch` or `CyclicBarrier` so workers become ready together and start simultaneously, increasing the chance of triggering real contention. Merely spawning threads without a start gate can accidentally execute nearly sequentially.
3. **Unique identifiers:** attach `workerId` and `sequence` to each event; attach a distinct request/trace ID per worker or request.
4. **Safe collection:** a mock sink can use `ConcurrentLinkedQueue` or appropriate synchronization; the test itself must not introduce a data race that skews measurements.
5. **Bounded wait for completion:** collect results via `Future.get(timeout)`, latches, and/or backend flush mechanisms; fail with diagnostic information on timeout instead of hanging indefinitely.
6. **Post-completion verification:** check total count, uniqueness, individual fields, context, and guaranteed ordering constraints.
7. **Resource cleanup:** shut down the executor, stop/close the appender, restore logger configuration, and clear/restore MDC in `finally`.

Correctness checks on a synchronous receiver should be deterministic on every run. Only then should you add stress tests that increase thread count, event volume, scheduling pressure, and enable various async/queue configurations to uncover rare bugs. Stress tests raise the probability of exposing defects; a few passing runs do not strictly prove the system is free of race conditions.

## 4. Standalone Java 17 Example: Testing Event Emission from Multiple Threads

The example below simulates a **logging core and test sink** using only the JDK, without depending on SLF4J/Logback. The recorder uses `ConcurrentLinkedQueue`, and events are immutable `record` instances. `ThreadLocal` acts as the request context; each worker emits 500 events, and eight workers pass through a shared start gate. The program verifies the count, each identifier, and the context, then prints **a single PASS line only after all checks succeed**.

Save as `ConcurrentLoggingCheck.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class ConcurrentLoggingCheck {
    private static final int WORKERS = 8;
    private static final int EVENTS_PER_WORKER = 500;
    private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();
    private static final ConcurrentLinkedQueue<Event> EVENTS =
            new ConcurrentLinkedQueue<>();

    record Event(int worker, int sequence, String requestId, String message) {}

    private static void emit(int worker, int sequence) {
        String requestId = REQUEST_ID.get();
        EVENTS.add(new Event(
                worker, sequence, requestId, "event-" + sequence));
    }

    private static void verify() {
        int expected = WORKERS * EVENTS_PER_WORKER;
        if (EVENTS.size() != expected) {
            throw new AssertionError(
                    "Expected " + expected + " events, got " + EVENTS.size());
        }

        boolean[][] seen = new boolean[WORKERS][EVENTS_PER_WORKER];
        for (Event event : EVENTS) {
            int w = event.worker();
            int s = event.sequence();
            if (w < 0 || w >= WORKERS || s < 0 || s >= EVENTS_PER_WORKER) {
                throw new AssertionError("Unexpected event id: " + event);
            }
            if (seen[w][s]) {
                throw new AssertionError("Duplicate event: " + w + "/" + s);
            }
            seen[w][s] = true;

            if (!("req-" + w).equals(event.requestId())) {
                throw new AssertionError("Wrong context: " + event);
            }
            if (!("event-" + s).equals(event.message())) {
                throw new AssertionError("Corrupt message: " + event);
            }
        }

        for (int w = 0; w < WORKERS; w++) {
            for (int s = 0; s < EVENTS_PER_WORKER; s++) {
                if (!seen[w][s]) {
                    throw new AssertionError("Missing event: " + w + "/" + s);
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        CountDownLatch ready = new CountDownLatch(WORKERS);
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(WORKERS);

        try {
            List<Future<?>> futures = new ArrayList<>();
            for (int worker = 0; worker < WORKERS; worker++) {
                final int w = worker;
                futures.add(pool.submit(() -> {
                    REQUEST_ID.set("req-" + w);
                    try {
                        ready.countDown();
                        if (!start.await(10, TimeUnit.SECONDS)) {
                            throw new AssertionError("Start timeout");
                        }
                        for (int s = 0; s < EVENTS_PER_WORKER; s++) {
                            emit(w, s);
                        }
                    } finally {
                        REQUEST_ID.remove();
                        if (REQUEST_ID.get() != null) {
                            throw new AssertionError("Context not cleared");
                        }
                    }
                    return null;
                }));
            }

            if (!ready.await(10, TimeUnit.SECONDS)) {
                throw new AssertionError("Workers not ready");
            }
            start.countDown();

            for (Future<?> future : futures) {
                future.get(10, TimeUnit.SECONDS);
            }

            verify();
            System.out.println(
                    "PASS events=4000 workers=8 perWorker=500 context=correct");
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
```

Compile and run with Java 17 or later:

```bash
javac ConcurrentLoggingCheck.java
java ConcurrentLoggingCheck
```

Stdout output when all verifications succeed:

```text
PASS events=4000 workers=8 perWorker=500 context=correct
```

Because the program waits for all `Future`s and prints only after `verify()`, stdout does not depend on scheduler ordering. If any event is missing, duplicated, has the wrong request ID, or has a corrupted message, the test throws `AssertionError` and does not print the PASS line. If a worker throws an error, `Future.get` surfaces it as an `ExecutionException` on the main thread; a timeout also fails the test. The `finally` block releases the start gate and requests executor shutdown, preventing workers from remaining stuck when the test fails.

**Limitation of this example:** `ConcurrentLinkedQueue` is already a thread-safe concurrent data structure. This test verifies the event emission flow, collection, identification, and assertion strategy; it **does not prove** that the production appender, file encoder, or async queue is thread-safe. For production testing, replace `emit` with real logger calls and collect records at an appender/consumer configured specifically for the test.

## 5. Testing Real Loggers and Appenders

With SLF4J and Logback, calls like `logger.info("request={} seq={}", requestId, seq)` must be verified using data that actually reaches the **final destination**. You can attach a custom test appender to the test's `LoggerContext`. Do not read state from a stdout file shared across tests, especially when the test framework may run tests in parallel.

The snippet below is an **illustrative example** of a test appender for Logback Classic; it requires Logback and SLF4J dependencies, attach/detach appender setup, an appropriate logger, and a JUnit test or application invoking it. It is not a standalone program:

```java
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.AppenderBase;
import java.util.List;
import java.util.Map;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;

record CapturedLog(String message, String threadName, String traceId) {}

final class CapturingAppender extends AppenderBase<ILoggingEvent> {
    private final Queue<CapturedLog> captured =
            new ConcurrentLinkedQueue<>();

    @Override
    protected void append(ILoggingEvent event) {
        event.prepareForDeferredProcessing();
        Map<String, String> mdc = event.getMDCPropertyMap();
        String traceId = mdc == null ? null : mdc.get("trace_id");

        captured.add(new CapturedLog(
                event.getFormattedMessage(),
                event.getThreadName(),
                traceId));
    }

    List<CapturedLog> snapshot() {
        return List.copyOf(captured);
    }
}
```

You must start the appender (`start()`), attach it to the logger under test, and detach and stop it in `finally`/teardown. `captured` is a thread-safe queue; `CapturedLog` is an immutable snapshot of the message, thread name, and trace ID **at append time**. Do not retain references to mutable structures and compare them later, because the data may change by the time the test inspects it. For other backends, use their respective test appender APIs and do not assume Logback semantics apply to every library.

A useful integration test emits sequences with distinct keys, for example:

```text
event=request-7 seq=0
event=request-7 seq=1
event=request-3 seq=0
```

Instead of comparing the entire log file line by line in order, extract `requestId` and `seq`, then verify the exact expected key set, message/level, and context. Across shared threads, the interleaving order between `request-7` and `request-3` is non-deterministic.

If an **async appender** is in use, place the capturing appender **downstream of the async appender** so the test actually exercises the queue. Do not claim logs are missing simply because they have not appeared in the sink immediately after emitting. Wait for a completion condition with a timeout or use the backend's flush/stop mechanism; measure drops if the configuration permits discarding records. When an async queue is configured to drop `INFO` logs under saturation, expecting 100% retention under high load is incorrect; instead, verify priority policy, drop counts, and that critical logs are retained per contract.

## 6. Testing MDC, ThreadLocal, and Context Propagation

In many Java frameworks, MDC stores fields such as `request_id`, `trace_id`, and `span_id` bound to the current thread. Concurrency tests commonly catch two classes of bugs:

- **Lost context:** a request sets MDC on thread A, but a task runs in an executor on thread B without propagating context. Log lines on B lack the IDs even though logs on A have them.
- **Context leakage:** a worker handles request A and is reused for request B; the code fails to clear or restore MDC, causing B's logs to carry A's IDs.

Tests should generate multiple requests with different IDs on the same thread pool, force some tasks to run asynchronously, and verify that **every event belongs to the right request**. After tasks complete, submit another task to the pool and verify no stale MDC values remain; design the execution so all relevant workers are checked, because submitting a single new task does not guarantee it runs on every previously used thread.

The snippet below propagates a **copy of the MDC** when submitting a task to an `Executor`, then restores the previous MDC in `finally`. It requires SLF4J, an externally provided `Executor`, and placement inside a utility class; it is not a standalone program:

```java
import java.util.Map;
import java.util.concurrent.Executor;
import org.slf4j.MDC;

static void executeWithMdc(Executor executor, Runnable task) {
    Map<String, String> captured = MDC.getCopyOfContextMap();

    executor.execute(() -> {
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            if (captured == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(captured);
            }
            task.run();
        } finally {
            if (previous == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(previous);
            }
        }
    });
}
```

Key behaviors to test here are that `captured` is taken at **submission time**, not when the worker starts executing, and that `previous` is restored even if `task.run()` throws an exception. This snippet only propagates the **MDC map**; it does not automatically propagate full OpenTelemetry trace/span context. In instrumented applications, prefer a context-aware executor or the instrumentation solution provided by your stack. Copying MDC also does not replace sensitive-data protection policies: do not place tokens, passwords, or unnecessary personal data into context.

## 7. Testing Asynchronous Logging and Overload Behavior

An asynchronous logger separates at least two points in time: **when the application call accepts the event** and **when the consumer exports the event to storage**. Results are inconclusive if a test only waits for application threads without waiting for the logging pipeline to finish processing.

Design tests according to policy:

| Configuration / Pipeline | What to Verify |
| --- | --- |
| Unfiltered synchronous sink | All IDs present; no duplicates or corruption; errors reported per contract on write failure |
| Async queue with no drops within target load | After completion/flush, counts and data match; no unexpected backlog remains |
| Bounded async queue with discard | Drops occur according to configuration and are measured; test does not demand retaining droppable logs |
| Retry on transient downstream failure | Retry limit is respected, exits within timeout, and does not duplicate events if contract requires `at-most-once` or dedup |
| Batching or multi-partition pipeline | Ordering is checked only within the scope guaranteed by the backend, typically not global order |
| Shutdown under load | Flushes/closes per policy, does not hang indefinitely, and does not drop committed events if required by contract |

Clearly distinguish **at-most-once**, **at-least-once**, and **exactly-once**. A system with retries can produce duplicate records under `at-least-once` delivery; deduplicating during analysis requires a proper event ID. Tests must not assume `exactly-once` semantics for a pipeline that does not guarantee it.

Avoid `Thread.sleep(1000)` to "wait for logs": on fast machines it wastes time, and on slow CI it can still be too short. Use a `CountDownLatch` at the sink, a backend-supported flush signal, or a bounded deadline with an observable condition. If shutting down an async logger to flush, ensure the appender has stopped before taking a snapshot and that no producers are still writing.

## 8. Failure Scenarios to Reproduce Proactively

| Scenario | Test Expectation |
| --- | --- |
| A worker throws an exception while logging | Does not hang the test; context cleaned up in `finally`; error logged per policy |
| Multiple threads concurrently log long/Unicode messages | No mid-character byte truncation, no interleaved payloads, JSON/text logs remain parseable |
| A formatter/custom encoder shares mutable state | No mixed data; timestamps and formatting remain valid under contention |
| A thread pool processes request A and request B sequentially | No log from B contains `request_id`/trace ID from A |
| `CompletableFuture` runs on a different executor | Context propagates properly when propagation is configured; do not assume it happens automatically |
| Multiple services and trace context | `trace_id` stays consistent per request; `span_id` matches the active span at log emission time |
| Large burst exceeds queue capacity | Backpressure/drop/retry matches contract, with observable metrics |
| Test suite runs in parallel | Tests do not share appenders or mutate the global root logger and pollute each other's results |
| Sampling or `DEBUG`/`INFO` filtering | Assert only events the policy commits to keeping; error/audit logs follow their own policy |

Do not "fix" a failing test by reducing workers until contention disappears, raising timeouts to infinity, removing assertions, or sorting logs by content and claiming you verified actual emission order. If a test is flaky, review start synchronization, completion conditions, ordering assumptions, drop policies, and logger isolation before concluding it is an application race condition.

## 9. Interpreting Results and Integrating into CI

A well-structured test suite should have **three layers**:

1. **Unit tests:** test message formatting logic, MDC enrichment, and filtering/sampling in isolation; use an immutable/thread-safe sink, fixed inputs, and deterministic outcomes.
2. **Integration tests:** start the real logging backend with dedicated configuration and appender; emit concurrently, wait for flush, read serialized logs, and verify fields, messages, and correlation IDs.
3. **Stress/soak tests:** scale up threads, log rate, message size, duration, and backend fault injection; measure throughput, queue size, dropped events, business-thread latency, and memory usage. Heavy suites can run on a separate scheduled pipeline while keeping fast checks on every CI run.

For any test, record the configuration explicitly: JVM/JDK version, thread count, event count, appender type, queue capacity, payload pattern, timeout mechanism, filtering/retention policy, and backend. A failure is actionable for investigation when it reports which event ID was missing, duplicated, had the wrong context, or when the timeout occurred—rather than just printing "expected 4000 but was 3999".

**Completion checklist:** trigger a true concurrent start; collect events safely; verify each ID, message, and context; handle `Future` results with timeouts; distinguish per-thread ordering from global ordering; wait for consumption/flush in async setups; clean up MDC, appenders, and executors; and observe drops according to policy. When these conditions are properly verified, tests will catch logging bugs that only surface under concurrent load and would be missed by sequential tests.
