# Testing Async Loggers in Java

## 1. Why Do Async Loggers Need a Different Testing Approach?

With synchronous logging, a log call typically invokes the appender on the current thread. With **asynchronous logging**, the thread creating the log event may only place the event into a queue; a background thread picks up the event and forwards it to the appender (console, file, centralized system) later.

Typical processing flow:

```text
Business thread
    logger.info(...)
         |
         v
  create log event + capture required data
         |
         v
      queue/buffer
         |
         v
    worker thread
         |
         v
  appender/encoder/sink
         |
         v
   log destination or storage
```

**Key takeaway:** `logger.info(...)` returning does not mean the log line has reached the sink, has been flushed to a file, or is persisted on disk. A test that "calls `logger.info` and immediately reads the file" may pass on a developer's machine but intermittently fail on CI because the worker has not run yet.

Distinguish three points in time:

1. **Accepted/enqueued:** the log call has been accepted by the logger or placed into the queue; under drop-on-overload modes, some events may be discarded according to configuration.
2. **Processed/delivered to appender:** the worker has delivered the event to the appender; this is usually the appropriate synchronization point for **logging integration tests**.
3. **Persisted/consumed downstream:** the data is actually pushed to a file, network, log collection service, or storage. The appender receiving the event does not guarantee this step succeeded or that the data has been `fsync`ed to disk.

The scope of this lesson is testing asynchronous logging behavior in Java: event content and metadata, background execution, ordering, full-queue handling, error handling, system shutdown, and performance testing. This is **testing the logging mechanism**; there is no need to re-test the entire business operation just to verify a single log statement appears.

## 2. Behavioral Contracts to Define Before Testing

| Aspect | Question to answer | Appropriate verification |
| --- | --- | --- |
| Content | Does `INFO` have the right formatted message and arguments? | Intercept the event at the appender, compare `level` and `formattedMessage` |
| Context | Do `requestId`/`traceId` travel with the event at creation time? | Change MDC on the calling thread after logging, check the snapshot in the event |
| Asynchronous | Does the sink execute on a background thread or on the calling thread? | Record the thread inside `append(...)` and compare with the source thread |
| Ordering | Do two logs from **one producer** preserve order? | Emit two events sequentially, receive them one by one from the sink |
| Concurrency | When multiple producers write together, are events lost or duplicated outside policy? | Each event carries a unique ID; compare the set and count after draining |
| Overload | When the queue is full, does it block, drop, or fall back to sync? | Slow down the sink in a controlled way and observe the configured policy |
| Shutdown | Does stopping the logger wait to process remaining events in the queue? | Send events, call the implementation's `stop/flush` API, check events after stopping |
| Sink error | How does an appender error cause log loss or affect business threads? | Mock a failing sink, check internal logs and the corresponding error-handling mechanism |
| Performance | How do business-thread latency and throughput change? | Separate benchmark with warm-up, fixed load, queue, and drop policy |

**Only write assertions according to the actually configured contract.** For example, if the appender is allowed to drop `DEBUG`/`INFO` when the queue is nearly full, a test cannot blindly require 100% of those events to be present. Conversely, in a functional test with a small but sufficient queue, disable the discard policy and use blocking-when-full mode so the results are meaningful.

### Are async loggers and async appenders the same?

Not completely. Logback typically uses `AsyncAppender`: the front end still creates an `ILoggingEvent`, then offloads the append work to a worker. Log4j2 has both **AsyncLogger** and **AsyncAppender**, with separate configurations and internal mechanisms. The hands-on Java example in this lesson uses **SLF4J + Logback AsyncAppender** to make the producer/consumer boundary visible. When using Log4j2, the same testing principles apply, but you must choose the test appender, lifecycle API, overflow policy, and flush mechanism specific to that implementation; do not copy Logback's `AsyncAppender` class directly to Log4j2.

## 3. Preventing Flaky Tests: Wait for Signals Instead of Guessing Time

Do not write:

```java
logger.info("Order created");
// Wrong: the worker may not have processed the event yet.
assertEquals(1, capturedLogs.size());
```

Also do not "fix" it with:

```java
logger.info("Order created");
Thread.sleep(200); // No guarantee that 200 ms is enough on every machine.
assertEquals(1, capturedLogs.size());
```

`Thread.sleep` makes tests slow and depends on thread scheduling and CI load. There are three better synchronization approaches:

1. **Thread-safe sink + bounded wait.** The test appender puts events into a `BlockingQueue`; the test calls `poll(timeout)`. When an event is received, we know `append(...)` has run. If it times out, the test fails with a clear message instead of hanging indefinitely.
2. **`CountDownLatch`/`CompletableFuture` signals.** Use when you want to wait for an exact number of events or mark that the worker has entered a processing section. The signal must be emitted at **the completion point being verified**, not immediately after enqueuing.
3. **The logger's drain/flush/stop API.** Suitable when testing backlog events during shutdown. You must understand the backend's specific timeouts and guarantees; finishing the worker stop does not mean a remote logging system has received the data.

Avoid reading an `ArrayList` while the worker is modifying it without synchronization; avoid using plain boolean variables shared between threads. `BlockingQueue` and `CountDownLatch` already provide appropriate cross-thread memory visibility guarantees for tests. Set finite timeouts so the entire test suite does not hang if the worker encounters an error.

## 4. Runnable Example: JUnit 5 Testing Logback AsyncAppender

The example below verifies four things in a standalone test:

- Two `INFO` events arrive at the appender completely and in order from the same producer.
- The `{}` placeholder is formatted into the expected message.
- MDC `requestId` is captured at the time of the logger call, not overwritten by a newer value when the worker processes it later.
- The `append(...)` work actually runs on a different thread than the thread that created the event.

The test uses a uniquely named logger, disables appender inheritance from root, controls the queue, and collects events into a `BlockingQueue`. It does not restart or reset the application-wide logger configuration.

### 4.1. Minimal Maven Project Structure

```text
async-logger-test/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── example/
                └── AsyncAppenderTest.java
```

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>async-logger-test</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.16</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>
        </plugins>
    </build>
</project>
```

This example uses only Logback as the SLF4J provider. In a real project, use your managed dependency versions and verify that only one matching SLF4J provider is on the classpath.

### 4.2. Test Appender Signaling When Events Reach the Sink

Create `src/test/java/example/AsyncAppenderTest.java`:

```java
package example;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.LoggerContext;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.classic.AsyncAppender;
import ch.qos.logback.core.AppenderBase;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;

class AsyncAppenderTest {
    record Captured(ILoggingEvent event, String sinkThreadName) {}

    static final class QueueAppender extends AppenderBase<ILoggingEvent> {
        private final BlockingQueue<Captured> received = new LinkedBlockingQueue<>();

        @Override
        protected void append(ILoggingEvent event) {
            // Runs inside the AsyncAppender worker.
            received.add(new Captured(
                    event, Thread.currentThread().getName()));
        }

        Captured awaitEvent() throws InterruptedException {
            return received.poll(5, TimeUnit.SECONDS);
        }
    }

    @Test
    @Timeout(15)
    void deliversFormattedMessagesAndMdcOnWorkerThread() throws Exception {
        LoggerContext context =
                (LoggerContext) LoggerFactory.getILoggerFactory();

        Logger logger = context.getLogger(
                "example.async.test." + UUID.randomUUID());
        logger.setAdditive(false);
        logger.setLevel(Level.INFO);

        QueueAppender sink = new QueueAppender();
        sink.setContext(context);
        sink.setName("test-sink");
        sink.start();

        AsyncAppender async = new AsyncAppender();
        async.setContext(context);
        async.setName("test-async");
        async.setQueueSize(64);
        async.setDiscardingThreshold(0);
        async.setNeverBlock(false);
        async.setMaxFlushTime(0);
        async.addAppender(sink);
        async.start();

        Map<String, String> previousMdc = MDC.getCopyOfContextMap();
        logger.addAppender(async);

        try {
            MDC.put("requestId", "req-01");
            logger.info("step {}", 1);

            MDC.put("requestId", "req-02");
            logger.info("step {}", 2);

            Captured first = sink.awaitEvent();
            Captured second = sink.awaitEvent();

            assertNotNull(first, "Event 1 chưa đến sink trong 5 giây");
            assertNotNull(second, "Event 2 chưa đến sink trong 5 giây");

            assertEquals("step 1", first.event().getFormattedMessage());
            assertEquals("step 2", second.event().getFormattedMessage());
            assertEquals(Level.INFO, first.event().getLevel());
            assertEquals(Level.INFO, second.event().getLevel());

            assertEquals("req-01",
                    first.event().getMDCPropertyMap().get("requestId"));
            assertEquals("req-02",
                    second.event().getMDCPropertyMap().get("requestId"));

            // ILoggingEvent holds the name of the thread that CREATED the log.
            // sinkThreadName records the thread actually running append(...).
            assertNotEquals(first.event().getThreadName(),
                    first.sinkThreadName());
            assertNotEquals(second.event().getThreadName(),
                    second.sinkThreadName());
        } finally {
            if (previousMdc == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(previousMdc);
            }
            logger.detachAppender(async);
            async.stop();
            sink.stop();
        }
    }
}
```

Run from the directory containing `pom.xml` with JDK 17+ and Maven:

```bash
mvn test
```

When the test succeeds, Maven reports a successful build with 1 test passed; elapsed time and console line counts vary by environment. JUnit/Surefire reports are placed in `target/surefire-reports/`. If the test fails, the assertion message or timeout indicates what failed; do not assume a fixed stdout ordering for asynchronous execution.

### 4.3. Why Is This Test More Reliable Than Sleep?

- `QueueAppender.append(...)` adds `Captured` to `LinkedBlockingQueue` **after** the worker begins delivering the event to the sink. `poll(5, TimeUnit.SECONDS)` waits for the exact event being observed.
- `AsyncAppender` processes events sequentially from its own queue. The two log calls are made one after another from the same test thread; therefore, the `step 1`, `step 2` order is a reasonable expectation under this configuration. Do not generalize this into a global ordering guarantee across concurrent producers.
- `getFormattedMessage()` gives the event content after `{}` parameters are substituted, while `getMDCPropertyMap()` checks the correlation ID attached to each event.
- `ILoggingEvent.getThreadName()` represents the **source thread** where the logger was called, even when the appender runs asynchronously. We also record `Thread.currentThread().getName()` inside `append(...)` to distinguish the consumer thread. Comparing only `getThreadName()` against the test thread name and concluding the appender ran synchronously would be an invalid test.
- `async.setDiscardingThreshold(0)` prevents the policy from dropping low-level events when the queue nears capacity in this functional example. `async.setNeverBlock(false)` specifies that when the queue is full, the producer waits for space rather than immediately discarding events. This test logs only two events and is not intended to measure backpressure.
- `finally` restores the previous MDC, detaches the async appender from the logger, and stops the worker and sink. `setMaxFlushTime(0)` tells Logback to wait for the worker to finish on stop; use carefully if a sink could hang. `@Timeout(15)` bounds the test duration, though real sink failures still need handling at the application layer.

**Note:** asserting that an event was received at the sink only proves delivery to the appender occurred. It **does not prove** that a file was durably flushed or that a remote log collector acknowledged it.

## 5. Designing Tests When Multiple Threads Log Concurrently

To test concurrent logging, assign a **unique event ID** to each call, such as `producer=3, sequence=7` or an `eventId` key. Use a `CountDownLatch` to create a common starting point; use an `ExecutorService` with a fixed number of producers. After all producers finish and the system has drained via a real mechanism, compare the set of IDs collected at the sink with the expected set of IDs.

A useful scenario:

1. Create 4 producers, each emitting 50 events with IDs formatted like `P0-0` through `P3-49`.
2. Block producers at `startGate.await()`; open the gate once with `startGate.countDown()` so they run concurrently.
3. Wait for all `Future`s using `get(timeout)` and ensure every task completes before wrapping up.
4. Wait for the full event count at the sink (if configured **not to discard**), or call a backend-supported drain/stop.
5. Verify exactly 200 unique IDs with no duplicates; if the implementation guarantees per-producer order, check the sequence order **per individual producer**.

Do not assert a single global order like `P0-0, P1-0, P2-0,...` across all producers: differing scheduler and enqueue timings validly change interleaving order. For implementations that preserve FIFO per queue, verify the order of events enqueued sequentially by a single producer; for multiple producers, check the backend's actual contract.

Do not use a large `CopyOnWriteArrayList` as a sink for throughput benchmarks: every add can copy the underlying array, causing the benchmark to measure **test collector** overhead rather than the async logger. `BlockingQueue` is suitable for functional tests; real benchmarks should use a separately controlled appender/sink whose own overhead is measured.

### Propagating MDC Across Threads

Distinguish two tests:

- **Producer → async logging worker:** an event created by the logger on the business thread can capture the producer's MDC before the worker writes it. The JUnit example above tests this.
- **Producer A → business task B on an `ExecutorService`:** thread B must receive the logging context via the application's context propagation mechanism. An async logger **does not automatically transfer a request's MDC** to thread B for `logger.info` calls made from B. Context propagation must be tested separately at the submission boundary.

When pool threads are reused, run two tasks with different `requestId` values and one task without context, confirming it does not mistakenly pick up an ID from a previous request. Clear or restore each task's MDC in `finally`. Async logger tests do not replace executor context propagation tests.

## 6. Testing a Full Queue: Backpressure, Discarding, and Overload Errors

Normal tests with plenty of queue capacity do not prove a logger is safe when it suddenly receives more logs than the appender can process. Create a **slow/blocking test appender** with a `CountDownLatch` to deliberately hold the worker on one event; then push additional events until the queue fills up.

For Logback `AsyncAppender`, two settings are notable:

- `discardingThreshold` controls the threshold for dropping low-priority events when the queue starts filling up; in Logback, default behavior may drop `TRACE`, `DEBUG`, and `INFO` to reserve space for higher-priority events. `setDiscardingThreshold(0)` disables this threshold-based dropping in lossless tests.
- `neverBlock=false`: when the queue is truly full, the sender waits for space. `neverBlock=true`: the sender attempts a non-blocking enqueue and may drop the event if there is no room. This behavior is distinct from dropping via `discardingThreshold`.

**Controlled backpressure scenario:**

1. Configure queue capacity 1, `discardingThreshold=0`, `neverBlock=false`.
2. Push the first event and wait for a signal indicating the worker has entered the blocked mock appender.
3. Push the second event to occupy the slot in the queue.
4. Send the third event from **a secondary producer** and observe that the enqueue call does not complete while the sink remains blocked.
5. Release the latch so the worker continues, then use `Future.get(timeout)` to confirm the third producer finishes and all three events reach the sink.

Do not make the third log call directly on the test coordinator thread, because it may block and prevent that thread from releasing the latch, causing a deadlock. When checking producer state, use a signal showing the producer started the log call, then observe completion via `Future` or a latch; do not rely solely on a short sleep.

To test a **discard** policy, keep a similarly slow sink but configure `neverBlock=true` or a discard threshold, then compare **received event counts against the actual rule**. Do not hardcode an exact dropped count unless you tightly control when the worker takes items; use latches to shape the exact queue state before submitting the test event.

In production, metrics such as queue utilization, dropped event count, producer block time, and appender errors help explain missing logs. A load test showing fewer logs is not enough to conclude a bug if the system is actively enforcing a discard policy.

## 7. Testing Flush and Shutdown

Things to distinguish:

| Action | Verifiable meaning | What not to infer |
| --- | --- | --- |
| `logger.info(...)` returns | Producer finished submitting the event according to policy | Sink received it or file synced to disk |
| Event received at test appender | Worker invoked the appender with the event | Remote collector received it |
| `stop/flush` succeeds | Backend ran its stop/drain procedure per API and configured timeout | All sinks guarantee crash durability |
| Process is killed abruptly | Events remaining in queue/buffer may be lost | Equivalent to graceful shutdown |

With Logback `AsyncAppender`, `stop()` attempts to process remaining queued events and waits for the worker up to `maxFlushTime`. With a finite limit, the worker may not finish draining before time expires; `maxFlushTime=0` waits without a time limit per Logback's mechanism. This setting is useful in tests whose sink is guaranteed to finish, but should not be set arbitrarily for systems whose sink might hang. Always set timeouts at the test layer and ensure all sink latches are released before stopping.

Shutdown test scenario:

1. Send N events while the appender is running normally, holding some events in the queue in a controlled manner.
2. Allow the worker to resume processing; call `stop()` at the proper lifecycle point and wait for completion.
3. Match all N IDs at the sink, if the configuration forbids discarding and shutdown guarantees draining within the chosen time.
4. Verify no test threads remain hanging; clean up executors, appenders, and MDC in `finally`.

If the target appender is a file, you can create a dedicated temporary file for the test, stop/flush the logger, read it back with `Files.readString(...)`, and delete the temporary file. This is a **file appender integration test**, distinct from in-memory event capture tests. Do not use the entire test suite's console output as an assertion source because logs from libraries and other tests can interleave.

For sudden crashes, "no log loss" is a durability requirement across the entire pipeline (queue, encoder, sink, file/network, receiver) and cannot be proven solely by a unit test calling `stop()`.

## 8. When Should Appender Errors Be Tested?

Async logging decouples logging time from business threads, but it does not make sink errors disappear. Tests should cover:

- Appender throws an exception during append: does the backend catch and report internal errors, or does the worker die? Are subsequent events still processed according to system behavior?
- Slow or temporarily unavailable sink: to what threshold does the queue grow, and how do producers block/drop?
- Faulty message or formatting arguments: does the system handle them as designed, and does logging accidentally mutate business state?
- Restart/stop state: is enqueuing allowed after stopping? What is the actual API behavior?

Do not write a test expecting a `RuntimeException` from the appender to be thrown back onto the thread calling `logger.info`, because in an async design the exception may occur on the worker and be recorded separately by the backend. To test errors, attach a mock appender that throws an exception and observe **the exact status channel, error handler, or metric** provided by the implementation. Avoid catching an arbitrary exception and treating it as the expected response.

## 9. Scoping Performance Tests Properly

Functional tests verify that events are accurate and arrive. Performance tests ask a different question: at a given log generation rate and sink slowness, how does logging affect business threads?

Metrics to measure:

| Metric | Interpretation |
| --- | --- |
| Producer latency p50/p95/p99 | Time a logging call keeps the business thread busy/waiting |
| Throughput | Number of events completed by the appender per unit time |
| Queue depth / capacity | Backlog size and risk of filling the queue |
| Drop count | Number of events discarded by the overload policy |
| Drain duration | Time to drain the backlog during shutdown |
| Memory / allocation | Cost of retaining events, strings, and context in the queue |

Sound methodology:

1. Use the same payload type, log level, format, producer count, and sink for both sync and async variants.
2. Warm up sufficiently before recording numbers; keep benchmarks separate from functional tests.
3. Measure the total number of events **processed by the appender**, not just `logger.info(...)` call counts.
4. Observe behavior when the queue is empty, when it is full, and when the sink is slow; async can be fast under light load but start blocking/dropping under heavy pressure.
5. Use JMH or an appropriate load tool across multiple runs to compare distributions; do not write unit tests like `assertTrue(elapsed < 10 ms)` because schedulers, GC, CI machines, and I/O are unstable.

**Async is not automatically faster in every case.** If the appender is fast and log volume is low, queue overhead, thread context switching, and object allocation may outweigh benefits; if the sink is slow, async reduces producer latency until the backlog exceeds service capacity.

## 10. Common Mistakes When Writing Async Logger Tests

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| Test intermittently fails because log "has not appeared" | Asserting immediately after enqueue | Wait for events via queue/latch with a timeout |
| Test needs multi-second sleeps to pass | Time-based synchronization | Signal at the appender or call supported drain |
| Logs from other tests leak into results | Using root logger or shared sink | Dedicated logger, `additive=false`, cleanup in `finally` |
| Test compares thread names incorrectly | `ILoggingEvent.getThreadName()` is the source thread | Record `Thread.currentThread()` inside the appender |
| MDC shows the last value for multiple events | Mutable object/map or snapshot at the wrong place | Verify event snapshot and propagation at the right boundary |
| Missing logs under high load | `discardingThreshold`, `neverBlock`, or slow sink | Know the policy before asserting all events |
| Test deadlocks when queue is full | Test thread blocks itself before releasing latch | Send blocking calls from a secondary producer, use timeouts, release in `finally` |
| Throughput test is very slow | Test collector has heavy locking/I/O/array copying | Separate functional collector from benchmark sink |
| Test passes but shutdown loses logs | Only checked accepted/enqueued | Test lifecycle drain and realistic timeouts |
| CI hangs when test fails | Unbounded `take()` or unbounded `join()` | Use `poll(timeout)`, `Future.get(timeout)`, and `@Timeout` |

### Diagnostic Workflow for Unstable Tests

- Identify whether the assertion measures **enqueue**, **append**, or **persist**; place the wait point at the right boundary.
- Check logger name, log level, and filter configuration to ensure expected events are actually generated.
- Inspect queue size, discard policy, worker state, and backend exceptions/status.
- Check for MDC leaks, unstopped appenders, unshutdown executors, or shared loggers reconfigured by other tests.
- Repeat runs with low rates, multiple producers, and explicit queue policies; do not arbitrarily increase sleep durations to mask race conditions.

## 11. Async Logger Test Suite Completion Checklist

A valuable test suite should prove that:

- [ ] Events have the right message, level, logger name, and required fields.
- [ ] Tests wait on signals emitted by the **sink**, with explicit timeouts.
- [ ] Execution on a background thread is verified when that is a required behavior.
- [ ] MDC or correlation context is captured at event creation time and does not leak between tasks.
- [ ] Ordering is checked within the scope guaranteed by the backend; no scheduler-dependent cross-producer order is forced.
- [ ] Queue and drop/backpressure policies are explicitly configured for each test.
- [ ] Shutdown/drain for pending events is tested if required by the application.
- [ ] Appenders, MDC, executors, and temporary files are cleaned up after tests even when assertions fail.
- [ ] Performance benchmarks are separated from JUnit assertions dependent on machine timing.

**Remember:** calling the logger only starts an asynchronous event's journey. Reliable tests must define the completion point being verified, use real synchronization signals at that point, and check results against the exact queue, thread, MDC, and shutdown policies chosen by the application.
