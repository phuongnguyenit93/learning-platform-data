# Race Conditions When Logging in Multithreaded Java Applications

## 1. Objectives and Context

In Java applications, multiple threads can concurrently write logs to the console, files, or centralized logging systems. When you observe interleaved log lines, incorrect data in logs, missing lines, or one request's trace ID appearing in another request, it is tempting to conclude that "the logger is not thread-safe." That conclusion can be inaccurate: **there are several distinct contention (race) regions** during the creation and writing of a log event.

After this lesson, you will be able to distinguish:

1. **Races on business state read to construct the message:** the logger may faithfully record a snapshot that is already wrong or inconsistent.
2. **Races when manually building or writing a log record:** multiple threads operating on an unsynchronized buffer, writer, formatter, or appender cause content to interleave, corrupt, or be lost.
3. **Observed order inversion:** independent threads have different scheduling orders; asynchronous logging can make the write time differ from the event creation time. This is not automatically a data race or a logger bug.
4. **Context races:** thread pools or asynchronous callbacks using `MDC`/`ThreadLocal` incorrectly cause logs to miss or mix up request identifiers.

The goal is to produce **each log event completely, with the right context, consistent data, and written through an appropriate mechanism**—not to force all threads to emit logs in a global order that does not exist in the program.

## 2. Nature of a Race Condition

A race condition is a situation where the outcome depends on the interleaved execution order of multiple threads. In Java, it is important to separate these concepts:

- **Data race under the Java Memory Model:** conflicting accesses to the same shared variable where at least one access is a write and there is no required happens-before relationship between them. This leads to visibility and correctness issues.
- **Loss of atomicity (lost update / check-then-act):** a multi-step logical operation is interleaved. For example, two threads both read `counter=0` and both write `counter=1` after adding 1, even though the expected total is 2.
- **Interleaving of log content:** a single event is manually split across multiple append/write calls and another event slips in between.
- **Nondeterministic ordering:** two independent events can appear as A then B or B then A; this alone does not prove a buggy race.

The following code example is a read–modify–write operation and is **not atomic**:

~~~java
int old = count;
count = old + 1;
logger.info("count=" + count);
~~~

If `count` is unprotected shared state, calling `logger.info` does not make the preceding two lines thread-safe. Even if each log call itself is thread-safe, the message still reflects a lost-update value.

An important Java rule: one thread reliably observes the effects of another thread only when an appropriate happens-before mechanism is in place, such as `synchronized`/locks, `volatile` where appropriate, atomic operations, or communication through concurrent data structures. Simply "putting `logger.info` between two operations" is not an application synchronization protocol.

## 3. Where Can Races Appear in the Logging Pipeline?

A log record typically passes through the following chain:

~~~text
Business thread
  │
  ├─ Read shared objects / variables
  ├─ Build message, parameters, and throwable
  ├─ Collect thread name / timestamp / MDC / trace context
  │
  └─ Logger API
       ├─ Check level, filter
       ├─ Create event / format
       ├─ Optionally enqueue to async queue
       └─ Appender / Handler / encoder
            └─ Console, file, socket, collector, or backend
~~~

| Location | Symptom | Prevention |
| --- | --- | --- |
| Reading data before the log call | Wrong counter values, fields from different versions | Use `AtomicInteger` for an independent counter; use a lock or immutable snapshot when multiple fields must be consistent |
| Manually concatenating strings into a shared buffer | Two records stick together, missing characters, or interleaved lines | Do not split an event into multiple independent write calls; use a logging framework and appender that support concurrent writes |
| Custom formatter/encoder | Corrupted dates/times, shared `StringBuilder`, or shared cache | Avoid shared mutable state; use immutable `DateTimeFormatter`; synchronize state that is genuinely shared |
| Thread-bound context | Request A gets B's request ID; another thread has no context | Propagate context explicitly, restore/clear in `finally` |
| Async queue | Delayed log output, dropped events when queue is full per policy, hard-to-infer ordering | Understand queue/flush/shutdown policies; measure dropped log counts; preserve event creation timestamps |
| Multiple processes writing to the same file | Overlapping lines or conflicting rotation | Use a multi-process-safe mechanism or have each process write to its own file/stream and aggregate centrally |

**Note:** SLF4J is a logging facade; the concrete thread safety of writing to a destination depends on the logging provider, appender, encoder, and configuration. Popular loggers and handlers are designed to accept concurrent calls, but you cannot infer from that that every custom appender, writer, and logged object is safe. Never casually share a `StringBuilder` or `SimpleDateFormat` across threads.

## 4. Hands-on 1: The Logger Writes Correctly, Yet the Logged Data Is Wrong

This is a standalone Java 17 example using only the standard JDK library. Both threads read the counter as `0` before being allowed to write; each thread then performs a non-atomic addition. `AtomicInteger` performs the same work safely.

**File: RaceLogDemo.java**

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class RaceLogDemo {
    private static final Logger LOG = Logger.getLogger("RaceLogDemo");

    public static void main(String[] args) throws InterruptedException {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        // StreamHandler writes to stdout with a fixed format for easy inspection.
        StreamHandler handler = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getMessage() + System.lineSeparator();
            }
        });
        handler.setLevel(Level.INFO);
        LOG.addHandler(handler);

        try {
            demonstrateLostUpdate();
            demonstrateSplitLogRecord();
        } finally {
            handler.flush();
            LOG.removeHandler(handler);
        }
    }

    private static void demonstrateLostUpdate() throws InterruptedException {
        int[] unsafeCounter = {0};
        AtomicInteger atomicCounter = new AtomicInteger();

        CountDownLatch bothHaveRead = new CountDownLatch(2);
        CountDownLatch allowWrites = new CountDownLatch(1);

        Runnable task = () -> {
            int oldValue = unsafeCounter[0];
            bothHaveRead.countDown();

            try {
                allowWrites.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }

            unsafeCounter[0] = oldValue + 1;
            atomicCounter.incrementAndGet();
        };

        Thread t1 = new Thread(task, "worker-1");
        Thread t2 = new Thread(task, "worker-2");
        t1.start();
        t2.start();

        bothHaveRead.await();
        allowWrites.countDown();
        t1.join();
        t2.join();

        LOG.info("unsafeCounter=" + unsafeCounter[0]);
        LOG.info("atomicCounter=" + atomicCounter.get());
    }

    private static void demonstrateSplitLogRecord()
            throws InterruptedException {
        // Intentionally demonstrates the bug: a single event is written in two fragments.
        StringBuilder sharedSink = new StringBuilder();
        CountDownLatch aWrotePrefix = new CountDownLatch(1);
        CountDownLatch bWroteLine = new CountDownLatch(1);

        Thread a = new Thread(() -> {
            sharedSink.append("A: begin ");
            aWrotePrefix.countDown();
            try {
                bWroteLine.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }
            sharedSink.append("end\n");
        }, "writer-A");

        Thread b = new Thread(() -> {
            try {
                aWrotePrefix.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }
            sharedSink.append("B: complete\n");
            bWroteLine.countDown();
        }, "writer-B");

        a.start();
        b.start();
        a.join();
        b.join();

        // Replace newlines with the literal "\n" so record boundaries are clearly visible.
        LOG.info("sharedSink=" + sharedSink.toString()
                .replace("\n", "\\n"));
    }
}
~~~

Run in the directory containing the file, with JDK 17 or newer:

~~~bash
javac RaceLogDemo.java
java RaceLogDemo
~~~

**stdout output:**

~~~text
unsafeCounter=1
atomicCounter=2
sharedSink=A: begin B: complete\nend\n
~~~

**Analysis:**

- `CountDownLatch` forces both threads to read `unsafeCounter[0]` before either thread can write. As a result, both write the value `1`, losing one update. The main thread calls `join()` before logging, so it observes the final result. This is an intentional schedule setup to reproduce the bug; without the latches, the bug might appear intermittently.
- `AtomicInteger.incrementAndGet()` is an atomic read-modify-write operation for that variable, so the result is `2`.
- The `sharedSink` section intentionally splits one event from thread A into two `append` calls. Thread B completes an event in between, producing `"A: begin B: complete\nend\n"`. The latches make **interleaving between record-assembly steps** reproducible. This part proves that the event is not constructed atomically as a whole; by itself, it is not a stress test for concurrent `append` calls corrupting `StringBuilder`'s internal structure.
- In the demo, `Logger` is only called from `main` after the threads have joined. The logger did not cause the two bugs above; it faithfully recorded the incorrect data produced by application code.

**Proper fix:** remove the shared `int` counter or protect it with a common lock, or replace it with `AtomicInteger` when only a single counter is needed. For logging, each event should be constructed as a complete object/event and passed to the logger in a single call using a thread-safe appender; do not let multiple threads assemble a shared record through separate `append` calls.

## 5. Creating Consistent Log Events While Data Is Changing

### 5.1. A Single Counter Field: Use Atomic Operations Appropriately

~~~java
AtomicInteger processed = new AtomicInteger();

int after = processed.incrementAndGet();
logger.info("processed=" + after);
~~~

The snippet above sits inside a method where `logger` and `processed` are already declared. The `after` value is the exact result of the increment just performed. However, multiple threads can still **call the logger in an order different from the increment order**. For example, thread A gets `after=1` and pauses, while thread B gets `after=2` and logs first. Looking at the printed lines, you may see `"2"` before `"1"`; that alone does not prove `AtomicInteger` is broken.

### 5.2. Multiple Related Fields: Capture a Snapshot Under the Same Protection

Suppose an order's state consists of `status` and `quantity`, which must be read from the **same version**. Reading the two fields via two separate calls could observe data stitched together from two different updates.

~~~java
record OrderSnapshot(String status, int quantity) {}

final class OrderState {
    private String status = "NEW";
    private int quantity = 0;

    synchronized void update(String newStatus, int newQuantity) {
        status = newStatus;
        quantity = newQuantity;
    }

    synchronized OrderSnapshot snapshot() {
        return new OrderSnapshot(status, quantity);
    }
}
~~~

Where `state` and `logger` are available:

~~~java
OrderSnapshot snapshot = state.snapshot();
logger.info("status=" + snapshot.status()
        + ", quantity=" + snapshot.quantity());
~~~

These two snippets are illustrations to be placed in an appropriate program context. `snapshot()` reads both fields under the **same lock** that `update()` uses and returns an immutable record. You can format and log **after releasing the lock**, reducing lock hold time and avoiding blocking business threads on slow console or file I/O.

For more complex consistency requirements, you can design state as an immutable object, swap the reference safely (for example with `AtomicReference`), and log the captured snapshot. Simply marking individual fields `volatile` does not automatically turn reading multiple fields into a consistent snapshot.

### 5.3. Avoid Logging Mutable References That Are Formatted Later

An async pipeline may retain arguments or objects until the encoder processes them. If an object mutates before formatting, the log may differ from its state at the time of the API call. How much and when the formatter evaluates arguments depends on the framework, configuration, and event type; never assume every provider deep-copies objects.

**Risk:**

~~~java
logger.info("order=" + mutableOrder);
~~~

**More controllable approach:**

~~~java
OrderSnapshot snapshot = state.snapshot();
logger.info("order status=" + snapshot.status()
        + ", quantity=" + snapshot.quantity());
~~~

Read the snapshot safely, convert the values to log into `String`/primitive/immutable DTOs according to application policy, and hand a single event to the logger. If using a supplier/lazy-logging API, remember that the lambda may read mutable variables or objects when invoked; a supplier does not automatically provide a consistent snapshot. Capture an immutable value before creating the supplier.

## 6. Logging from Multiple Threads Without Breaking Records

### 6.1. One Logger Call per Event

Use the logging framework's API instead of concatenating fragments into a shared output stream:

~~~java
// Threads can call this concurrently on a properly configured logger.
logger.info("worker=" + Thread.currentThread().getName()
        + " processed=" + processedId);
~~~

This is a snippet inside a method where `logger` and `processedId` are already declared. Each call represents a complete event. With SLF4J, parameterized logging syntax is commonly used:

~~~java
// SLF4J snippet example; requires the corresponding dependency and backend.
log.info("worker={} processed={}",
        Thread.currentThread().getName(), processedId);
~~~

Using placeholders defers part of the formatting cost when the level is disabled, but it **does not fix reading shared data**. `processedId` must still be captured correctly before logging.

Avoid writing a single event across multiple separate operations:

~~~java
// Demonstrates the bug: the same output is used by multiple threads.
sharedWriter.write("order=" + orderId);
sharedWriter.write(" status=" + status);
sharedWriter.write("\n");
~~~

If another thread writes in between, fragments can interleave. Even if each individual `write` is synchronized, **the entire three-write sequence is not protected as a single atomic operation**. In practice, send one complete event to the logger/appender or, if a custom writer is unavoidable, wrap the entire logical operation under the same lock.

### 6.2. If You Must Write a Custom Appender/Handler

Lock only the **necessary scope** to protect shared mutable components (writer, formatter, buffer, rotation state). Here is a conceptual structure for an in-memory sink:

~~~java
final class LineSink {
    private final StringBuilder buffer = new StringBuilder();

    public synchronized void appendLine(String line) {
        buffer.append(line).append('\n');
    }

    public synchronized String snapshot() {
        return buffer.toString();
    }
}
~~~

This `LineSink` class can be placed in a Java 17 file of the same name if declared package-private; the synchronized methods protect adding **an entire line** at once, while `snapshot()` shares the same lock to read a consistent copy. For production needs, avoid rolling your own file appender or rotation when the framework already provides them.

Do not wrap an entire HTTP/request handler in `synchronized` just to control log ordering; doing so serializes business work, increases latency, and does not solve cross-service context propagation. Also avoid holding an application lock during network or file logging calls if the sink can block for a long time or call back into application code.

### 6.3. Another Process Writing to the Same File

Thread safety within a single JVM **does not imply** safety when multiple JVMs or processes share the same file. Rotation, renaming, buffering, file locking, and append semantics depend on the filesystem, OS, and provider. The easiest operational approach is for each process to write to its own stdout or separate file, then collect logs via an agent or collector. If file sharing is mandatory, use a multi-process mechanism documented by your logging provider and test it in a realistic environment.

## 7. Log Ordering: What Is Guaranteed?

Consider two threads:

~~~text
Thread A: update A1 → log A1 → update A2 → log A2
Thread B: update B1 → log B1
~~~

Without a happens-before constraint between A and B, the output can easily be:

~~~text
A1
B1
A2
~~~

or:

~~~text
B1
A1
A2
~~~

`A1` appearing before `A2` typically reflects the same thread invoking them sequentially in an ordered processing pipeline, but you should not generalize this example into a **global display-order guarantee** for every appender or async pipeline. Ordering between two independent threads is not a reliable business order.

Distinguish these timestamps and stages:

- Event creation in the business thread.
- Event handoff to the queue (if async).
- Worker taking the event from the queue.
- Formatter/encoder writing bytes to the sink.
- Collector receiving and indexing the event.

Timestamps usually reflect event creation time, though this depends on the provider and configuration. Clocks across machines can drift; equal or very close timestamps do not imply causality. To trace execution flow, use trace IDs / span IDs or task IDs alongside meaningful business events; if required, assign sequence numbers within a well-defined narrow scope (such as per order) using an atomic counter.

**Even an atomic sequence number does not force log lines to appear in ascending order**: a thread that obtains a smaller number can still reach the appender later than a thread with a larger number.

## 8. MDC/ThreadLocal and Request Mix-Ups in Thread Pools

MDC (Mapped Diagnostic Context) typically stores key/value pairs attached to a thread, such as `request_id`, `trace_id`, or `user-safe-operation-id`. When an `ExecutorService` reuses threads, context from a previous task can linger if cleanup is forgotten. Conversely, context from the calling thread is not automatically transferred to worker threads.

Below is a snippet using SLF4J MDC in an application with an MDC-capable SLF4J backend; it is not a standalone program:

~~~java
import java.util.Map;
import org.slf4j.MDC;

// On the thread creating the task:
Map<String, String> captured = MDC.getCopyOfContextMap();

executor.execute(() -> {
    Map<String, String> previous = MDC.getCopyOfContextMap();
    try {
        if (captured == null || captured.isEmpty()) {
            MDC.clear();
        } else {
            MDC.setContextMap(captured);
        }

        log.info("processing task");
    } finally {
        if (previous == null || previous.isEmpty()) {
            MDC.clear();
        } else {
            MDC.setContextMap(previous);
        }
    }
});
~~~

Explanation:

1. Capture a **copy** of the context on the calling thread before submitting the task.
2. On the worker, save the previous context so nested call scopes are not corrupted.
3. Apply the required context, log, and restore in `finally` even if an exception occurs.
4. If the original context was empty, call `clear` to avoid retaining stale values from a previous task.

For systems using OpenTelemetry, Reactor, or frameworks with official context propagation mechanisms, prefer those mechanisms over manually wrapping every task. MDC does not automatically create spans, propagate `traceparent` across services, or act as a security boundary.

**Common failure scenario:** request A runs on `worker-3`, sets `request_id=A`, and forgets to clean up. Request B is scheduled onto `worker-3` and logs without setting `request_id`; B's logs carry label A. This is context corruption caused by thread lifecycle and scoping, not evidence of the appender mixing bytes.

## 9. Asynchronous Logging: Queues, Buffers, and Backpressure

Async logging decouples event creation from sink writes to reduce I/O wait on the request path. It introduces additional contention factors:

- **Queue capacity:** when full, depending on the provider and policy, producers may block, drop events, fall back to synchronous logging, or apply another strategy. Do not assume "async never drops logs" or "always drops."
- **Event consistency:** mutable parameters, exceptions, and MDC must be captured into the event at the right time according to backend behavior. Do not guess whether the provider retains references or copies them without verifying.
- **Flush and shutdown:** on application shutdown, allow the worker to flush pending events as supported by the provider's capabilities and configuration; do not assume bytes are on disk or at the collector merely because `logger.info` returned.
- **Ordering:** a single FIFO queue orders items already enqueued, but competing producers have no global "business" order. Multiple queues, partitions, batched network transport, or collectors further prevent display order from matching the exact moment each thread called the logger.
- **Backpressure:** monitor queue utilization, dropped events, flush errors, and write latency, and decide how critical logs should be handled by priority.

If you require durable, strictly ordered, lossless transaction records, **standard application logs do not replace a transaction log, the outbox pattern, or a dedicated audit store**. That is a transactional and data-durability problem distinct from operational logging.

## 10. Debugging Race Conditions in Logging

When you see anomalous behavior, classify it before changing code:

| Observation | Likely Cause to Investigate | Practical Check |
| --- | --- | --- |
| Two requests share the same `request_id` incorrectly | MDC leak between tasks or reused IDs | Send two consecutive requests on a pool of size 1; log at scope entry and exit |
| Counter in logs jumps or is lower than task count | Lost update or inconsistent snapshot | Inspect increment logic, `synchronized`/atomics, and where snapshots are taken |
| One line contains half of two different threads' data | Custom writer/appender assembling a record across multiple writes | Audit shared writers/buffers and per-event atomicity boundaries |
| Log prints `"2"` before `"1"` | Thread with 2 reached the logger first; async pipeline | Separate update order, enqueue order, output order, and happens-before constraints |
| Logs disappear under higher load | Full queue, filters, sampling, sink/collector errors | Check backend config, dropped counts, and flush/error metrics |
| Log lines scramble during file rotation | Multiple processes/appenders or unsynchronized rotation | Check file ownership, process count, and multi-process support |
| Object value in log differs from when logger was called | Mutable object changed before formatting | Capture an immutable snapshot; check when the provider formats events |

### A Practical Investigation Workflow

1. **Reproduce deterministically:** use `CountDownLatch`/`CyclicBarrier` to force suspect interleavings; avoid relying solely on hard-to-repeat random failures.
2. **Separate three measurement points:** state before creating the event, data inside the created event, and data actually arriving at the sink. Identify which stage introduces the error.
3. **Inspect the actual shared state:** counters, mutable objects, caches, formatters, writers, appenders, queues, `MDC`/`ThreadLocal`; do not sprinkle `synchronized` everywhere.
4. **Verify happens-before:** check whether `join`, `Future.get`, concurrent collections, locks, or atomics are used consistently on both read and write paths.
5. **Keep tests small:** two threads and a few clear events usually pinpoint the cause faster than millions of lines of stress logs.
6. **Test with production-like configuration:** log levels, providers, async appenders, overflow policies, rotation, collectors, and timeouts can change symptoms compared to dev.

Stress tests can uncover issues, but **a single clean run does not prove the absence of races**. Once you identify a suspect interleaving, writing a test that actively reproduces that schedule is far stronger than waiting on luck.

## 11. Preventive Practices in Java Projects

**Data and events:**

- Keep objects with shared state under appropriate synchronization. When multiple properties must be consistent, use an immutable snapshot or a shared lock.
- Put all content for a log entry into a single event; do not concatenate an event via multiple unprotected writes to a shared sink.
- Avoid calling `toString()` on complex mutable objects or ones with side effects on hot paths; pick stable fields and limit sensitive data.
- Use structured logging so attributes like `request_id`, `trace_id`, `thread`, `component`, and `operation` are distinct fields, making analysis easier.

**Logger configuration:**

- Use a provider/appender designed for concurrent logging with documented queue, file-writing, and rotation policies.
- Treat custom appenders, encoders, and formatters as concurrent code: audit shared variables and when events are created or copied.
- Do not confuse **a guarantee against mixing bytes within a single event** with **a global ordering guarantee across all events**.
- With async logging, measure lost/dropped events and event-to-sink latency; actively flush and shut down in line with the application lifecycle.

**Threads and context:**

- Set context at scope entry and restore/clear it in `finally`; ensure async tasks and callbacks carry the proper context.
- Use thread names and thread IDs to aid diagnostics, but do not use them as unique request IDs because pools reuse threads.
- Never log secrets, tokens, or sensitive personal data in MDC, exception messages, or parameters.

## 12. Verification Exercises

1. Run `RaceLogDemo.java` as instructed and explain why `CountDownLatch` reliably reproduces the lost-update bug while `AtomicInteger` produces the correct result.
2. Update `demonstrateSplitLogRecord()` so each thread builds a complete line and calls `LineSink.appendLine()`. Verify that the two independent lines are no longer fragmented, even though the A/B order may vary.
3. Create a pool with one worker and process request A followed by request B; intentionally omit clearing MDC and observe `request_id` leaking across. Fix it with `try`/`finally` and confirm B has its own ID.
4. Create a scenario using state with `status` and `quantity`; perform updates on another thread and compare logging each field separately versus logging `snapshot()` under the same lock.
5. With a real async backend, document its queue size, full-queue policy, shutdown flush behavior, and ordering guarantees; test only in a dedicated test environment to avoid affecting operational logs.

## 13. Key Takeaways

A "race condition when logging" is not just two threads calling `logger.info` at the same time. The issue can lie **before the logger** (reading bad data), **in custom event-writing/formatting code** (shared buffers or appenders), **in context propagation** (MDC mixing requests), or **after enqueuing** (asynchrony and output ordering). The fix must match the root cause: atomics/locks/snapshots for data, complete events and safe sinks for logs, scope cleanup for context, and proper queue/flush configuration for async logging.

### References

- Java 17 java.util.logging.Logger: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- Java 17 StreamHandler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/StreamHandler.html
- Java 17 CountDownLatch: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html
- Java 17 AtomicInteger: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html
- Java 17 Memory Consistency Properties: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html#MemoryVisibility
- SLF4J MDC API: https://www.slf4j.org/apidocs/org.slf4j/MDC.html
- Logback MDC manual: https://logback.qos.ch/manual/mdc.html
