# Do Not Perform Slow I/O on the Instrumentation Call Thread

When using **Java Instrumentation** to monitor methods, measure duration, record traces, or collect metrics, a small piece of code (*probe/hook*) is typically inserted directly into the application's execution path. **The probe runs directly on the thread calling the instrumented method**; it is not automatically offloaded to a separate thread. If the probe calls the filesystem, network, console logging, database, or waits for an exporter, the monitoring latency is **added directly to business latency**.

Therefore, for performance-sensitive code paths, the fundamental rule is: **do not perform slow I/O, retries, or wait for queue capacity inside the hook**. The hook only collects a minimal amount of required information and passes the data to a **bounded buffer** or updates lightweight counters. A dedicated worker handles encoding, flushing, file writing, network exporting, and retries off the application thread.

However, **asynchronous does not mean zero cost or zero loss**. If the queue is unbounded, it can lead to an `OutOfMemoryError`. If the queue is full and the producer calls `put()`, the application thread is blocked. If the worker dies and no one detects it, telemetry is silently lost. This article clarifies the architecture, overload choices, a runnable Java 17+ example, and how to verify the actual cost.

## 1. Identify the Instrumentation Call Thread Correctly

Imagine an agent inserting a hook into `OrderService.submit()`:

```text
REQUEST THREAD
  |
  v
OrderService.submit()
  +-- Probe.enter()     <- same request thread
  +-- business logic
  +-- Probe.exit()      <- same request thread
  |
  v
HTTP response
```

If `Probe.exit()` waits 200 ms for a file/network write to finish, the request can also be delayed by 200 ms. When an instrumented method executes multiple times within a single request, the overhead repeats multiple times. Inside a code region holding a lock, a blocked thread also forces other threads to wait for the lock, causing a cascading effect.

A more suitable path:

```text
REQUEST THREAD
   |
   +-- timestamp / event ID / primitive fields
   |
   +-- boundedQueue.offer(event)
           |             |
         accepted        full
           |             |
           v             v
      bounded queue    drop/sample/counter
           |
           v
EXPORTER THREAD
   |
   +-- format / batch / compress
   +-- file or network I/O
   +-- flush / retry / error report
```

Distinguish between **two durations**: the cost for the hook to return control to the business thread (*capture/enqueue latency*) and the time from when an event is generated until it is stored/exported (*delivery latency*). Decoupling I/O bounds the first component, though it may increase the second component.

### 1.1. Slow I/O Is Not Just Writing Files

Operations to avoid in a latency-sensitive hook:

- `Files.writeString(...)`, `FileOutputStream.write(...)`, `BufferedWriter.flush()`, `FileChannel.force(...)`, and file rotation;
- `System.out.println(...)` / `System.err.println(...)` — consoles/pipes may have locks, buffers, and slow consumers;
- synchronous logging from SLF4J/Logback/Log4j, or async appender configurations that **fall back to blocking the caller** when full;
- HTTP/gRPC, socket write, DNS lookup, TLS handshake, exporter, JDBC/database;
- calling `Future.get()`, `CompletableFuture.join()`, `Thread.sleep()`, `CountDownLatch.await()`, `Thread.join()`, or `BlockingQueue.put()` on the hot path;
- serializing the entire request, dumping large stack traces, building heavy JSON, deep reflection, or loading uninitialized classes/helpers;
- acquiring shared locks for a long time, or waiting on a logger/formatter lock that may be held by another worker.

Not all of the operations above are file/network I/O, but they can all **prolong the time the business thread is held up**. Analyze them from the perspective of tail latency and blocking potential rather than just API names.

## 2. Anti-pattern: Synchronous I/O in the Hook

Example **only illustrating behavior to avoid**, not a standalone program:

```java
static void onExit(String method) throws java.io.IOException {
    java.nio.file.Files.writeString(
        java.nio.file.Path.of("trace.log"),
        method + System.lineSeparator(),
        java.nio.file.StandardOpenOption.CREATE,
        java.nio.file.StandardOpenOption.APPEND
    );
}
```

There are at least five issues:

1. The write executes **on the thread calling `onExit`**; the filesystem can be unpredictably slow due to disk saturation, remote file servers, quotas, or flushes.
2. Opening/updating the file on every event creates overhead and contention when multiple threads write concurrently.
3. If an `IOException` is thrown and escapes the hook, **business logic can fail due to a telemetry error**; inside a `finally` block, this error can also mask the original business exception.
4. The logger/formatter may allocate many objects, increasing GC pressure and causing tail latency even when I/O is usually fast.
5. Heavy writing reduces throughput, causing request backlogs to grow, which in turn generates even more logs — an incident-amplifying feedback loop.

**Using `BufferedWriter` directly in the hook is not enough.** The buffer may have to flush when full, hold locks, or wait on I/O. What matters is that **the write happens on another thread**, not merely that there is a buffer behind the API.

### 2.1. Do Not Assume Every Logger Is Async

`logger.info("duration={}", duration)` may be very cheap in one configuration; it can also be synchronous or block when the appender/queue is full. If you construct the message before the logger checks the level, heavy formatting still occurs on the caller thread.

In instrumentation, you must inspect the **actual exporter/appender configuration**: bounded or unbounded, overflow policy when full, internal synchronization, whether the logger itself can re-trigger the hook, and shutdown behavior.

## 3. What Work Belongs in the Hook?

A hook should have **small cost and a clear boundary**:

| Task | Recommendation |
| --- | --- |
| Measure duration | Use `System.nanoTime()` to compute elapsed time; do not format timestamps into complex strings in every hook. |
| Capture a few primitives/IDs | Snapshot a few fields; avoid accessing lazy getters that might trigger I/O. |
| Sampling check | Check early before allocating an event. |
| Create a small record | Keep only necessary data; do not hold references to an entire large request/context. |
| Enqueue | Use a bounded queue and an operation that **does not wait for capacity**, such as `offer(event)`. |
| Queue full | Follow an intentional policy: drop, sample/aggregate, or a dedicated mechanism for mandatory data. |
| Counters | `AtomicLong`/`LongAdder` or an appropriate mechanism; verify contention under load. |
| Format/encode, I/O, retry | Offload to the consumer thread. |
| Flush/drain/join | Only perform on a lifecycle thread, never inside the instrumentation point. |

Hook code needs a **fast exit path** when tracing is disabled, when the exporter fails, or when sampling skips the event. Avoid letting instrumentation code use the same logging infrastructure being instrumented, which causes **instrumentation recursion**.

### 3.1. Exceptions in Probes Can Be Dangerous

If an agent inserts a probe in `finally` to ensure an event is recorded even when the business method throws, the probe itself **must not throw a telemetry error that replaces the business exception**. For example:

```java
// Illustrative snippet inside a method; businessOperation, probe, and eventId
// are defined at the actual integration site.
long started = System.nanoTime();
try {
    businessOperation();
} finally {
    long elapsedNs = System.nanoTime() - started;
    probe.tryRecord(eventId, elapsedNs);
}
```

This is **not a standalone Java file**. `tryRecord` must follow its own failure policy, must not send HTTP requests or write files synchronously, and must not arbitrarily throw `IOException` to the caller. Nor should it unconditionally `catch(Throwable)` and swallow critical errors like `VirtualMachineError` just to protect telemetry.

## 4. Queue Operations: Do Not Confuse `offer` with `put`

Java SE 17 `ArrayBlockingQueue` is a **bounded buffer** with a fixed capacity. Common operations:

| API | When queue is full | Impact on caller |
| --- | --- | --- |
| `offer(event)` | Returns `false` if it cannot be added immediately because the queue is full | Does not wait for queue space; suitable for best-effort telemetry. |
| `put(event)` | **Waits** until space becomes available | Can prolong business execution indefinitely if the worker stops draining. |
| `offer(event, timeout, unit)` | May wait up to the timeout | The timeout is added to business latency. |
| `add(event)` | Throws `IllegalStateException` when full | Unsuitable if the error is not managed. |
| Unbounded queue | Backlog can grow without limit | Can keep event object graphs alive, causing GC pressure/OOM. |

Note carefully: **`ArrayBlockingQueue.offer` is not a wait-free/lock-free algorithm**. It does not wait for **capacity**, but its implementation uses an internal lock; multiple producers can experience brief contention. If an ultra-low latency budget is required, benchmark it and consider an SPSC/MPSC/ring buffer or per-thread buffers.

**A queue only absorbs bursts**; it does not solve a sustained throughput mismatch. If producers generate events faster than the consumer processes them, a bounded queue will fill up and the system must execute its overflow policy.

## 5. Choosing an Overload Policy

| Policy | Trade-off | Use case |
| --- | --- | --- |
| **Drop newest** | Loses new events when the queue is full; simple, caller does not wait for capacity | Best-effort metrics/traces. |
| **Drop oldest** | Keeps fresher data but loses older history; harder to preserve ordering | State tracking that prioritizes the most recent events. |
| **Sampling** | Captures only a representative subset; reduces event volume | Very high-frequency hot methods. |
| **Aggregation** | Does not retain individual events; only counts/summaries/histograms | Statistical metrics. |
| **Coalescing** | Merges multiple updates for the same key | Progress/state where every intermediate change is not required. |
| **Backpressure/block** | Preserves data, but the producer must wait | Only when latency impact is acceptable under the business contract. |
| **Durable journal** | Requires durable write design, I/O cost/failure rules | Mandatory audit/events that must not be lost. |

**You cannot simultaneously demand "never block under any circumstances", "never lose a single event", and "use bounded memory" if downstream can stall indefinitely.** This is an architectural trade-off. If the data is legal, payment, compliance, or mandatory audit data, do not silently drop it to protect latency; design an appropriate durable boundary directly into the business architecture.

Distinguish three counters: **accepted** means entered the queue, **dropped** means discarded, and **persisted/exported** means successfully processed according to the destination's definition. Accepted **does not mean saved to a file/service**. With an exporter that retries, you must also account for duplicates/at-least-once delivery.

## 6. Runnable Java 17+ Example: Decoupling Instrumentation and I/O

The complete example below does not require bytecode weaving, because it calls `onMeasurement(id)` to **simulate a hook inserted into a method by an agent**. The program focuses solely on **the hook not writing files**, a bounded queue, and a separate worker.

To verify overflow **deterministically**, the consumer uses a `CountDownLatch` **only for the test** to temporarily pause draining events while `main` sends five events into a queue of capacity two. The first two events enter the queue successfully, and the next three events are dropped immediately. After the measurement calls finish, `close()` from `main` releases the worker to write the file.

Structure:

```text
buffered-probe-demo/
└── BufferedProbeDemo.java

Appears after running:
└── probe-events.log
```

### 6.1. `BufferedProbeDemo.java`

```java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

public final class BufferedProbeDemo {
    private BufferedProbeDemo() {}

    private record Event(int id) {}

    public static void main(String[] args) throws Exception {
        Path path = Path.of("probe-events.log");
        try (BoundedProbe probe = new BoundedProbe(path, 2)) {
            for (int id = 1; id <= 5; id++) {
                probe.onMeasurement(id);
            }
            System.out.println("[caller] accepted=" + probe.accepted()
                    + " dropped=" + probe.dropped());
        }
        List<String> saved = Files.readAllLines(path, StandardCharsets.UTF_8);
        System.out.println("[after-close] persisted=" + saved.size());
        System.out.println("[after-close] events=" + String.join(",", saved));
    }

    private static final class BoundedProbe implements AutoCloseable {
        private final ArrayBlockingQueue<Event> queue;
        private final AtomicLong accepted = new AtomicLong();
        private final AtomicLong dropped = new AtomicLong();
        private final AtomicBoolean closing = new AtomicBoolean();
        private final CountDownLatch writerReady = new CountDownLatch(1);
        private final CountDownLatch allowDrain = new CountDownLatch(1);
        private final Thread writer;
        private final Path path;
        private volatile IOException failure;

        BoundedProbe(Path path, int capacity)
                throws IOException, InterruptedException {
            this.path = path;
            this.queue = new ArrayBlockingQueue<>(capacity);
            this.writer = new Thread(this::writeLoop, "probe-writer");
            writer.start();
            writerReady.await(); // Initialize once, NOT inside the instrumentation point.
            if (failure != null) {
                throw failure;
            }
        }

        void onMeasurement(int id) {
            if (closing.get()) {
                dropped.incrementAndGet();
                return;
            }
            if (queue.offer(new Event(id))) {
                accepted.incrementAndGet();
            } else {
                dropped.incrementAndGet(); // Full: drop event, do not wait for I/O.
            }
        }

        long accepted() { return accepted.get(); }
        long dropped() { return dropped.get(); }

        private void writeLoop() {
            try (BufferedWriter out = Files.newBufferedWriter(
                    path, StandardCharsets.UTF_8)) {
                writerReady.countDown();
                allowDrain.await(); // Only to test a controlled full-queue scenario.
                while (true) {
                    Event event = queue.poll(50, TimeUnit.MILLISECONDS);
                    if (event != null) {
                        out.write("hit-" + event.id());
                        out.newLine();
                    }
                    if (closing.get() && queue.isEmpty()) {
                        break;
                    }
                }
                out.flush();
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                failure = new IOException("Writer interrupted", interrupted);
            } catch (IOException io) {
                failure = io;
            } finally {
                writerReady.countDown(); // Even if opening the file fails.
            }
        }

        @Override
        public void close() throws IOException, InterruptedException {
            closing.set(true);
            allowDrain.countDown();
            writer.join(); // May wait for I/O: call ONLY OUTSIDE the instrumentation point.
            if (failure != null) {
                throw failure;
            }
        }
    }
}
```

**Note:** The Java 17 code above is a standalone program. It creates a log file in the working directory; `Files.newBufferedWriter` by default **overwrites the existing file** if you run it again. Use a dedicated test directory, not a file containing data you need to keep.

### 6.2. Why Doesn't the Hook Wait for I/O Here?

The `onMeasurement(int id)` method only:

1. Checks the `closing` state.
2. Creates a small record containing the integer `id`.
3. Attempts `queue.offer(...)`, **without waiting for capacity**.
4. Increments `accepted` or `dropped`.

It **does not** call `Files.writeString`, `newBufferedWriter`, `flush`, `logger.info`, `sleep`, `await`, or `join`. All waiting/file-opening/file-writing operations live on the **writer thread** or the **lifecycle/main thread**. Therefore, a slow worker causes **queue full + drop** rather than forcing the request thread to wait until the writer finishes writing.

To be precise: `ArrayBlockingQueue.offer` **still uses an internal lock**; the hook is not completely wait-free, and there is still overhead from record allocation, counters, and memory barriers. The goal of this design is to **avoid waiting on I/O/downstream**, not to promise zero overhead.

`CountDownLatch allowDrain` in the worker is only there to intentionally create a reproducible full queue. **Do not put a latch like that in a production consumer**; a real consumer should continuously poll and write events with a batch/retry policy.

### 6.3. Compile and Run Commands

Use JDK 17 or newer:

```bash
javac --release 17 BufferedProbeDemo.java
java BufferedProbeDemo
```

PowerShell also uses those two commands when `javac` and `java` are on `PATH`. `--release 17` enables the `Event` record and concurrent APIs in the code while ensuring Java 17 classfile/source targeting.

**Verified stdout on Zulu/OpenJDK 24.0.2 with code compiled using `javac --release 17`:**

```text
[caller] accepted=2 dropped=3
[after-close] persisted=2
[after-close] events=hit-1,hit-2
```

Contents of `probe-events.log` after closing:

```text
hit-1
hit-2
```

Result analysis:

- The constructor starts the `probe-writer` thread and waits for the worker to open the file **during setup**, not in the hook.
- The worker is held after `writerReady` by `allowDrain` **only to test the congestion scenario**.
- The two calls `onMeasurement(1)` and `onMeasurement(2)` enter the two-slot queue.
- The three calls with IDs 3, 4, and 5 hit a full queue → `offer` returns `false` → `dropped` increments without writing to the file on the caller.
- After the hook calls finish, `try-with-resources` calls `close()` to release the latch and run `writer.join()` on the main thread. The worker writes the two events and exits; only then does `main` read the file.
- Empirical totals for accepted, dropped, persisted: **2, 3, 2**. This is not a throughput benchmark, but an overflow policy check.

**Do not infer from this result that exactly two events will always be persisted in a real application.** When the worker runs normally, it can consume concurrently with the producer, so the accepted/dropped ratio depends on load and scheduling.

## 7. Lifecycle, Shutdown, and Worker Failures in Production

The demo uses **a single producer on the main thread** and only calls `close()` **after all `onMeasurement` calls have completed**. This is an important premise for draining accurately without modeling hundreds of producers.

### 7.1. Race When Multiple Producers Are Active

If the application is instrumented across multiple threads:

```text
producer A: sees closing=false
                                     manager: closing=true
                                     writer: queue is empty, exits
producer A: enqueues successfully
                                     -> event has no consumer left
```

Simply using `AtomicBoolean closing` **does not make the check+offer pair atomic**. A real system must have a lifecycle protocol: stop accepting new hook invocations, wait for active/enqueuing producers, establish a drain boundary, and only then allow the consumer to close. You can use a phaser, an in-flight counter with a barrier, or another specialized mechanism; do not copy a single-producer demo into a multi-producer service without adding coordination.

### 7.2. Closing the Pipeline May Have to Block

`writer.join()`, `flush()`, and closing the file can take a long time. Therefore, only do them on a **shutdown/control thread**, not inside instrumented business methods. The demo uses `join()` without a timeout to clearly illustrate ordering; production needs a **shutdown timeout and an expiration policy**, such as reporting the number of unpersisted events or allowing the service to stop with a known loss.

Making the writer a daemon thread helps the process exit easily, but it can lose undrained data; leaving it as a non-daemon thread without a timeout can also keep the JVM alive when downstream hangs. Both choices require an operational policy.

### 7.3. Error State Must Not Disappear

In the example, the worker stores `IOException` in `failure` and `close()` reports it. If the writer fails early, producers can keep enqueuing until the queue is full. **Production must detect errors earlier**, expose a health state, stop/reconfigure the producer, or fall back according to policy. Do not rely on "finding out the file failed only at shutdown".

Useful metrics: writer status, last successful export, dropped-on-full, permanently-failed, retry-count, backlog, consumer throughput, and un-flushed data at close.

## 8. Batching, Retries, and Bounded Resources

Moving I/O to another thread **does not make downstream faster**. If producers generate `λ` events/second and the worker can only write `μ` events/second with `λ > μ` sustained, the backlog grows at roughly `λ - μ` until the queue is full.

Illustrative example:

```text
Producer: 50,000 events/second
Consumer: 30,000 events/second
Backlog grows: 20,000 events/second
Queue capacity: 10,000 items

In an idealized model, an empty queue fills up in about 0.5 seconds.
```

Queue size only helps **absorb bursts**; it cannot eliminate a sustained throughput deficit. A queue of 10,000 entries also only bounds the **number of items**, not guaranteeing a memory cost of 10,000 bytes: each event can hold references to a large object graph.

### 8.1. Batching in the Consumer

A worker can take multiple items at once via `drainTo` or a polling loop, then serialize and send them as a batch:

```text
bounded queue -> drain small batch -> encode -> write/send -> flush
```

Batch size and flush interval must be bounded. Large batches can increase throughput but add memory usage and delivery latency. `BufferedWriter.flush()` does not mean `fsync` guaranteeing data is durably on the device; durability also depends on the API/filesystem and collector architecture.

### 8.2. Budgeted Retries

Network/disk retries **belong only in the worker**, with bounded attempts/time, backoff, retryable vs. non-retryable errors, and duplicate handling. Overly long retries stop the worker from draining, causing the queue to keep filling. You need a policy for drops, durable spooling, sampling, or a circuit breaker, rather than defaulting to infinite retries or making the business thread wait.

### 8.3. Avoid Holding Large Object Graphs in the Queue

Do not enqueue an entire `HttpServletRequest`, `Throwable`, `ClassLoader`, user sessions, or large payload arrays just so the worker can extract a few fields later. Holding references can extend the lifetime of the entire graph, causing heap pressure, leaking sensitive information, or reading mutable state that has already changed. Snapshot **a few primitive/immutable identifiers** in the hook and avoid building large JSON/strings; let the worker encode them.

## 9. Real Instrumentation: Class Loading and Recursion

A Java agent can use `ClassFileTransformer` or the Class-File API/bytecode libraries to inject helper calls into methods. However, **the helper code invoked on every method execution still runs on the business thread**. The transformer only decides how to insert the hook; it does not automatically create an async boundary.

Also note that `ClassFileTransformer.transform(...)` runs while the JVM defines/redefines/retransforms classes. Performing slow I/O directly **inside the transform callback** can prolong class loading, causing contention or deadlocks due to classloader locks. Therefore, avoid both types of synchronous work: **I/O in frequently executed hooks** and **I/O in class transformation callbacks**.

### 9.1. Self-Instrumenting the Logger/Exporter Causes Recursion

If the agent also instruments classes of the logger, writer, HTTP client, or the agent's own helpers, a worker processing an event can generate a new event, which is then processed by the worker again — a **logging storm loop**.

Mitigations:

- Exclude packages/classes of the agent, exporter, serializer, and infrastructure used by the agent from the transformer when appropriate.
- When needed, use a `ThreadLocal` reentrancy guard restored in `finally`; the guard also has overhead, so verify it.
- Do not log exporter errors through the same broken logging pipeline.
- Avoid repeated class loading and inaccessible helpers due to module/class-loader boundaries.

### 9.2. Thread Context Does Not Automatically Migrate to the Worker

When an event moves to the worker, the producer's `ThreadLocal` data, request-scoped context, tracing context, or security principal **do not automatically appear** on the consumer thread. If correlation is needed, snapshot **the required IDs** at the hook and pass them in the event. Do not mistakenly read the worker's `ThreadLocal` as if it were the request thread.

## 10. Measuring Overhead and Verifying the System

To prove that decoupling I/O actually works, you must measure against a baseline under the same load and with failure scenarios.

| Metric | Meaning |
| --- | --- |
| Hook duration p50/p95/p99/p99.9 | The cost instrumentation adds to the caller. |
| Request end-to-end latency | Customer-visible impact; compare agent enabled vs. disabled. |
| Queue offer failure / dropped | Rate of events discarded due to overload. |
| Queue occupancy & backlog | Whether the worker keeps up with producers; treat `size()` as a snapshot. |
| Consumer throughput/batch size | Number of events processed and batch efficiency. |
| File/socket write latency | Where I/O actually happens, whether downstream is stalling. |
| Accepted vs persisted/exported | Distinguishes entering the queue from reaching the destination. |
| GC allocation rate, memory | Event objects, buffers, and object graphs kept alive by the queue. |
| CPU, contention, thread stalls | Whether queue locks/atomic counters/workers cause another bottleneck. |
| Failures, retries, shutdown loss | Reliability and behavior during backend failures. |

### 10.1. Java Flight Recorder (JFR)

Oracle Java 17 guides using JFR to analyze events such as:

- `jdk.FileRead`, `jdk.FileWrite`;
- `jdk.SocketRead`, `jdk.SocketWrite`;
- `jdk.JavaMonitorEnter`, `jdk.JavaMonitorWait`;
- `jdk.ThreadPark`, `jdk.ThreadSleep`.

Inspect **thread name, stack trace, and duration** to distinguish whether a request thread is doing I/O or only the `probe-writer`/exporter thread. JFR configurations have **thresholds**: very short I/O operations may not appear in the recording; "seeing no FileWrite events" **is not definitive proof of no I/O**.

### 10.2. Testing Bad Scenarios

Do not benchmark only "fast disk, healthy network". Test:

1. Backend stops reading, socket write times out.
2. Disk is full or file permissions are insufficient.
3. Queue fills up under a sustained burst.
4. Multiple producer threads contend on the queue/counters.
5. GC under a high allocation rate.
6. Worker fails while the application keeps running.
7. Shutdown while backlog remains and while I/O is stalled.
8. Agent enabled/disabled under the same workload, checking p99/p99.9 rather than just the average.

Decoupling I/O should **improve latency isolation**, while drop/health/durability policies still need explicit evaluation.

## 11. Common Design Mistakes

| Assumption / Behavior | Actual Problem |
| --- | --- |
| "Logging one line at the instrumentation point is always fast." | File/console/network can have tail latency and lock contention. |
| "Loggers are always async." | Depends on the appender; some configurations block the caller when the queue is full. |
| "`ArrayBlockingQueue.offer` is wait-free." | No, it uses an internal lock; it only avoids waiting for queue space. |
| "`BlockingQueue.put` is suitable for a hot hook." | Can wait indefinitely if the consumer is slow or stalled. |
| "An unbounded queue doesn't block so it has no risk." | Easily retains many objects, increasing GC and causing OOM. |
| "Accepted means written to file." | Accepted only means enqueued, not yet persisted. |
| "Making capacity large enough means it will never fill up." | If producers are consistently faster than the consumer, it will eventually fill up. |
| "Never blocking and never losing an event using an in-memory queue." | Cannot be guaranteed under an indefinite downstream outage with finite resources. |
| "Logging in `finally` can freely throw errors." | Can mask the original business exception. |
| "Once it's async, there's no need to track dropped events." | Missing data can skew metrics/traces; drops must be reported. |
| "A daemon worker is always safe." | The process can exit before flushing/draining completes. |
| "Calling `join()` from every hook ensures data is saved." | Forces the business thread to wait for the worker; defeats the async goal. |
| "Keeping the whole Request/Throwable in the queue is cheap." | Can keep large graphs/PII and mutable data alive. |
| "If the consumer fails, producers can just keep enqueuing." | The queue will fill up or accumulate backlog; health checks and fallbacks are needed. |
| "Calling `CompletableFuture.runAsync(...)` per event is enough." | Can exhaust the thread pool, bloat the default queue, and make failure handling hard. |
| "A probe can harmlessly instrument the exporter itself." | Easily causes recursion, exponential event multiplication, and stack overflow. |
| "`close()` at any time drains properly with multiple producers." | Needs a lifecycle barrier to eliminate the check+enqueue race. |
| "No JFR FileWrite events proves the hook does no I/O." | Thresholds/configuration may filter out short I/O operations. |
| "Decoupling I/O gives the hook zero overhead." | There is still event allocation, queue/atomic contention, memory barriers, and GC. |

## 12. Self-Check Exercises

**Question 1.** Why should you not call `Files.writeString(...)` directly inside `Probe.onExit()`?

**Answer:** Because the probe runs on the business thread; file I/O can block, increase latency, and even alter the business exception if an error propagates out.

**Question 2.** A queue has capacity two; the worker has not consumed any events yet. What result do five consecutive `offer` calls produce under a drop-newest policy?

**Answer:** Two events are accepted, three events are dropped; that is the scenario the demo verifies. The producer does not wait for capacity.

**Question 3.** How do `offer` and `put` differ when the queue is full?

**Answer:** `offer` returns `false` when it cannot add immediately because the queue is full; `put` waits until space is available or the thread is interrupted. `offer` does not automatically guarantee lock-freedom.

**Question 4.** Can the accepted counter be used to confirm that downstream received all events?

**Answer:** No. You need persisted/exported acknowledgements with clear semantics; accepted only confirms the queue received the event.

**Question 5.** If the worker is slower than the producer rate over a long period, does increasing queue capacity permanently solve the problem?

**Answer:** No. It only absorbs bursts; the backlog still grows until the queue is full if the throughput deficit persists.

**Question 6.** Can `writer.join()` be called during shutdown?

**Answer:** Yes, on a lifecycle thread with a policy/time budget; do not use it in the hook. Production needs to handle hung I/O and unflushed data.

**Question 7.** Is `AtomicBoolean closing` alone sufficient for strictly correct draining when multiple producers are enqueuing?

**Answer:** No. There is a race between the check and `offer`; you must have lifecycle coordination/a barrier or stop in-flight publishers before the worker exits.

**Question 8.** Why should you not enqueue the entire `HttpServletRequest` when you only need a method ID and duration?

**Answer:** It can keep a large object graph alive, contain sensitive data, and mutate while the worker reads it. Snapshot only the small, immutable data needed.

**Question 9.** JFR shows `jdk.SocketWrite` on a request thread from an agent exporting traces. What does that suggest?

**Answer:** The exporter may be performing synchronous I/O on the business path. Inspect the call stack/agent config and move exporting to a bounded worker for isolation.

**Question 10.** Audit data must be complete, but producers must not block and the backend can lose connectivity indefinitely: can a bounded in-memory queue guarantee completeness?

**Answer:** No. You must change the contract and use a durable messaging/journal architecture with explicit failure semantics; you cannot guarantee both zero loss under an indefinite outage and non-blocking behavior with finite RAM.

## 13. Summary and References

**Rules so instrumentation does not degrade business performance:**

1. **Hooks run on the caller thread**, so do not write files, make network calls, flush, retry, or wait for downstream.
2. **Collect only the minimum**, snapshot immutable/primitive fields, sample early, and pass data through a bounded queue.
3. **`offer` does not wait for capacity**, but still has contention; do not advertise it as wait-free and always benchmark.
4. Under overload, **an overflow policy is mandatory**: drop, sample, aggregate, or use a durable architecture suited to the data.
5. **Accepted is different from persisted**; measure drops, queue backlog, consumer throughput, write failures, and shutdown losses.
6. The consumer is responsible for batching/serializing/exporting/retrying, without pushing I/O errors onto the business thread.
7. **Shutdown and class-loader/transformer callbacks must also avoid blocking**, while guarding against instrumentation recursion.
8. Verify with JFR/profilers and p95/p99 latency including downstream failure scenarios.

Official documentation:

- [Java SE 17 — ArrayBlockingQueue, offer/put/timeout semantics](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html)
- [Java SE 17 — BlockingQueue and memory consistency effects](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html)
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [Java SE 17 — java.lang.instrument agent/transformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- [Oracle Java SE 17 — Troubleshoot Performance Issues Using JFR](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [OpenJDK JEP 328 — Java Flight Recorder](https://openjdk.org/jeps/328)