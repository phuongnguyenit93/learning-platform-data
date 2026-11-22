# Exporting Measurements via Counters, Event Queues, or JFR Events Based on Your Goal

> **Goal:** Design the observability data path after Java instrumentation has measured an event. Know how to choose a **counter** when aggregated metrics are needed, a **bounded event queue** when detailed records must be processed asynchronously, or a **Java Flight Recorder (JFR) Event** when JVM-correlated diagnostic/timeline data is needed. Understand hot-path overhead, event loss, backpressure, cardinality, privacy, collection conditions, and how to verify each option using Java 17+.

This lesson belongs to the **Probe Design** group. A *probe* is the point in a program where we record an occurrence, such as a method completing, an RPC call failing, or an operation running too slowly. **Exporting measurements** is a separate decision: routing information from the probe to an appropriate storage/consumption mechanism. A probe can emit a counter, a queue event, or a JFR Event, but you should not arbitrarily multiply the signal by three and count them as three business events.

## 1. Start from the Question to Answer, Not from the API

Suppose an agent inserts an observation point around `OrderService.checkout()`. At the end of the method, the agent knows:

```text
operation = checkout
status    = success or failure
duration  = elapsed time
thread    = current thread
```

Operators may want very different outputs:

1. **“How many checkout transactions failed in the last minute?”** → Needs a **counter** and a rate calculation over a time window.
2. **“Which transactions failed, which consumer processed them, and where were they sent?”** → Needs **detailed event records** and a sink capable of ingesting them.
3. **“On which thread did the slow operation occur, and near which GC/lock/I/O events?”** → Needs a **diagnostic timeline**, where JFR has an advantage because it shares the JVM data ecosystem.

If every method invocation is turned into a log line or a synchronously sent remote record, instrumentation can slow down the very application it is observing. If only a counter is kept, you can lose the context needed to investigate a specific failure. Therefore, before choosing an API, explicitly write down: **the goal, required resolution, data volume, overhead budget, acceptable data loss, and data consumers**.

```text
Method execution
      |
      v
  Very short probe
      |
      +--> LongAdder/AtomicLong --> snapshot/exporter --> metrics backend
      |
      +--> bounded queue --> consumer/batch/exporter --> event backend
      |
      +--> jdk.jfr.Event.commit() --> JFR recording/stream --> JMC/.jfr
```

The first arrow **does not mean a counter automatically emits HTTP metrics**. The second arrow **does not mean putting into a queue means successful delivery**. The third arrow **does not mean JFR automatically sends data to an external service**. Distinguish between **in-process recording**, **exporting out of the JVM**, and **reaching the final destination**.

## 2. Quick Decision Table

| Criterion | Counter (`LongAdder`, `AtomicLong`) | Event Queue (`BlockingQueue`/ring buffer) | JFR Event (`jdk.jfr.Event`) |
| --- | --- | --- | --- |
| Data unit | Count/sum/aggregated value | Record of each individual observation | Event with timestamp, duration, fields, thread metadata |
| Best suited for | Throughput, errors, retry counts, total time | Sending detailed records, batching, consumer integration | Profiling, latency, correlation with GC/locks/threads/JVM |
| Cost at the probe | Usually low; increases with many labels/counters | Object allocation and enqueue; can consume memory and drop events | Depends on enabled/threshold/stack trace/payload |
| Memory bound | Number of counters and dimension cardinality | Must be **bounded**; predefined capacity | Buffer/recording size/age depends on configuration |
| When consumer is slow | Scrapes/captures stale values; counter updates keep running | Queue full → drop, block producer, or another policy | Recording/stream/buffer experiences pressure; limits must be configured |
| Keeps individual events? | **No** | Yes if enqueue/consume succeeds; not durable by default | Yes when the event is recorded and data is still retained |
| Time-based querying | Based on periodic snapshots and deltas | Based on timestamp + backend | Native JFR timeline and analysis tools |
| Delivery guarantees | Not a message delivery mechanism | Depends on consumer/sink; an in-RAM queue is not an audit log | Not a message queue or durable audit log |
| Caveats | Counter cardinality, non-atomic snapshots | Backpressure, overload, shutdown, duplicates/loss | Recording config, thresholds, sensitive data, versions |
| When measurement is off | Can skip incrementing selective counters | Do not enqueue | JFR Event has `isEnabled()`/`shouldCommit()` |

**Practical rule:** Choose the cheapest option that still answers the question. If you only want to count frequency, do not retain entire request objects; if you need to diagnose slow methods inside the JVM, do not build a complex queue system when a conditionally enabled JFR Event is enough.

## 3. Design a Common Data Schema Before Choosing a Sink

Data at the probe should usually have a **minimal logical schema**:

| Field | Meaning | Should it be kept every time? |
| --- | --- | --- |
| `name` | Measurement name, e.g. `checkout.completed` | Yes, but use a stable list of names |
| `outcome` | Success, failure, timeout | Yes if needed for breakdown |
| `elapsedNanos` | Duration measured via `System.nanoTime()` | Can be aggregated, used in a histogram, or recorded in an event |
| `timestamp` | Time when the event occurred | Needed for queues/events; counters usually use scrape time |
| `component` | Component name, endpoint template, or operation | With bounded cardinality |
| `traceId`/`spanId` | Trace correlation when truly needed | Do not put in counter labels; may be sensitive |
| `thread` | Thread context | Useful in JFR/diagnostics, rarely used for counters |
| `errorKind` | Categorized error group | Prefer stable categories over raw messages |

Each sink has a different representation. A counter for `checkout.completed` might have two `LongAdder`s: success and error. A queue might hold an `Observation(operation, outcome, elapsedNanos, timestamp)` record. A JFR Event can store `operation`, `outcome`, and use the duration from `Event.begin()`/`end()` instead of adding unnecessary custom fields.

**Do not put user information, URLs with unique identifiers, full SQL, exception messages containing internal data, or request bodies into all channels by default.** Just because a field can technically be recorded does not mean it should be. Classify PII/secrets, bound labels, and define retention/deletion policies.

### A Common Semantic Bug: Counting on Both Enter and Exit

If a probe increments a counter on method entry and increments again on method exit, and both are named `requests_total`, the dashboard may count **two** for a single request. Define the unit clearly:

- `requests_started_total`: incremented at the start.
- `requests_completed_total`: incremented upon completion, including errors if defined that way.
- `requests_failed_total`: incremented exactly once for an actual failure.

You must also define whether a retried call counts as one **attempt** or one **business transaction**. The sink cannot fix an incorrect measurement definition on its own.

## 4. Option A — Counters for Aggregated Metrics

### 4.1. `LongAdder` and `AtomicLong`

In Java 17+, two commonly used classes are:

```java
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;

LongAdder completed = new LongAdder();
LongAdder failed = new LongAdder();
AtomicLong active = new AtomicLong();

completed.increment();
failed.increment();
active.incrementAndGet(); // At start.
active.decrementAndGet(); // At end, even when throwing an exception.
```

This is an **API illustration**, not a standalone program. `AtomicLong` provides single-variable read/update operations with atomic semantics; it is useful for gauges such as active in-flight requests or cases requiring updates with a clear linear order. `LongAdder` distributes write contention to increase throughput when multiple threads increment concurrently, making it suitable for **high-frequency counters**.

`LongAdder.sum()` is **not an atomic snapshot** while threads are still updating it. During a read, some in-flight increments may not yet be included in the returned value. This is usually acceptable for aggregated telemetry; it is **not suitable as an exact point-in-time transaction ledger**.

Similarly, `LongAdder.sumThenReset()` is **not safe as an atomic window-closing operation** when multiple producers are still writing. Resetting while updates are occurring can make results hard to interpret. For metrics, many systems keep counters **monotonically increasing** and compute deltas between two scrapes while handling process restarts/resets.

### 4.2. From Total Count to Rate

The counter `orders_completed_total` is 12,000 at 30 seconds and 15,000 at 60 seconds. If there was no reset between the two timestamps:

```text
delta count = 15,000 - 12,000 = 3,000
elapsed     = 60 - 30 = 30 seconds
rate        = 3,000 / 30 = 100 per second
```

In practice, use actual measurement timestamps (do not assume scrapes always happen on exact second boundaries), handle restarts, and distinguish units. **A standalone counter cannot answer p95/p99 latency percentiles.** To get a latency distribution, you need histograms/buckets or another data format; summing total duration and dividing by count gives the **mean**, not p99.

### 4.3. Labels and Cardinality

Counters can be split along stable dimensions:

```text
method_calls_total{operation="checkout", outcome="success"}
method_calls_total{operation="checkout", outcome="error"}
method_calls_total{operation="refund", outcome="success"}
```

This is a **metrics format example**, not Java syntax. Do not use `requestId`, raw URLs, user IDs, or exception messages as labels. One million requestIds can create one million time series, exhausting memory and breaking the collection system. In an agent, design a **bounded** mapping table from class/method to operation name instead of creating a new counter for every dynamic combination.

### 4.4. Counters Do Not Come with a "Free" Exporter

`LongAdder` only stores numbers in-process. To get a dashboard, you need a collector/scraper/exporter. Choosing an HTTP endpoint, the OpenTelemetry SDK, or a metrics backend is **additional implementation work**. You should not write:

```text
completed.increment()  → data is already in Prometheus
```

unless you have actually wired up an exporter and verified that the backend receives the metrics.

## 5. Option B — Event Queues When Individual Records Are Needed

### 5.1. Why Do Queues Appear in Instrumentation?

A detailed event may require JSON serialization, batching, compression, file writing, or network transmission. If the agent does all of that directly inside the request-serving method, real latency will increase and exporter errors can leak into business logic.

Decouple producer and consumer:

```text
Business processing thread
    │
    ├─ create small event, without heavy objects
    ├─ queue.offer(event) (non-blocking)
    └─ return control to the application
                  |
                  ▼
           Bounded queue
                  |
                  ▼
      Dedicated worker / batch
                  |
                  ▼
      file / gateway / telemetry backend
```

**The queue accepting an event** does not mean **the sink received it**. You need to track at least `accepted`, `dropped`, `exported`, and `exportFailed` (with clear definitions), rather than only counting successful `offer` calls and claiming 100% delivery.

### 5.2. Queues Must Be Bounded

`ArrayBlockingQueue<T>(capacity)` is a fixed-size array-backed queue. With `offer(e)`:

- Returns `true` if inserted immediately.
- Returns `false` if full, **without waiting** for space.

With `put(e)`, the producer **blocks** when the queue is full. This is sometimes right for data pipelines where backpressure is allowed to slow upstream, but on the hot path of JVM instrumentation it is usually very dangerous: a slow exporter can stall all request threads.

```java
// Illustrative code inside a queue management class:
if (!queue.offer(observation)) {
    droppedCounter.increment();
}
```

Here `queue`, `observation`, and `droppedCounter` must be declared and managed in the class that owns the sink. You can also use `offer(e, timeout, unit)` when you have a **specific wait budget**, but you must understand that the producer can block up to that timeout. If `LinkedBlockingQueue` is constructed without a capacity argument, its default capacity is huge (`Integer.MAX_VALUE`), making it practically **unbounded in effect** when the consumer stops working.

### 5.3. Choosing a Policy When Full

| Policy | Suitable Scenario | Risk |
| --- | --- | --- |
| **Drop newest** (`offer` returns false) | General telemetry, prioritizing business protection | Loses new events; must increment drop metric |
| **Drop oldest** | Wanting to keep the most recent state | Loses earlier history; needs appropriate structure/synchronization |
| **Block** (`put`) | Producer tolerates backpressure, not on hot path | Increases latency, can deadlock or stall the application |
| **Sample** | Very high event volume where a sample is statistically enough | No longer complete per-request data; must report sampling rate |
| **Batch or coalesce** | Many events of the same kind that can be merged | Loses per-event detail/timing and ordering |
| **Spill to disk** | Need to limit loss during spikes | I/O complexity, recovery, disk quota, and latency |

No single policy fits all types of data. **Observability telemetry is not an audit/payment ledger.** If you need zero-loss guarantees and per-transaction reconciliation, you must design a proper transaction log/durable messaging/ack/replay mechanism; an in-heap `BlockingQueue` is not enough.

### 5.4. Consumers and Lifecycle

A consumer typically runs on a worker thread, drains batches, retries when the exporter fails, and shuts down cleanly. You must check:

- Does `close()` stop accepting new events before draining?
- When the JVM terminates abruptly, events in the queue are **not guaranteed** to have been flushed to disk.
- Retries can cause **duplicates** if the sink succeeded in receiving the batch but the acknowledgment arrived late.
- An internal queue preserves the order of enqueued items, but **ordering across concurrent producers** depends on interleaving; do not treat it as an absolute business event order.
- If the consumer throws an exception and dies, the queue can silently fill up; health signals and lifecycle supervision are needed.
- Reading `queue.size()` helps observe relative pressure, not an atomic transactional snapshot while the queue is continuously changing.

In production, decide whether the consumer thread is a daemon or not, shutdown flush deadlines, retry deadlines, quarantine policies, and maximum send rates; never let shutdown hang forever waiting on a disconnected exporter.

## 6. Option C — JFR Events for JVM-Correlated Diagnostics

**Java Flight Recorder** (`jdk.jfr`) collects events inside the JVM and can correlate them with thread activity, allocations, GC, synchronization, I/O, and other JVM events on the same timeline. Java 17+ provides an API for defining custom events:

```java
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

@Name("demo.CheckoutFinished")
@Label("Checkout Finished")
@Category({"Application", "Checkout"})
public final class CheckoutFinishedEvent extends Event {
    @Label("Operation")
    public String operation;

    @Label("Success")
    public boolean success;
}
```

The snippet above is a standalone Java class that should be saved in a file named `CheckoutFinishedEvent.java` if used on its own. In the hands-on section, a nested event class is used so only a single file is needed.

### 6.1. A Recording Must Be Enabled to Consume JFR Data

`Event.commit()` writes the event to Flight Recorder **when the event is enabled and matches the configuration**; it is not an HTTP/POST call. You need a recording/stream to retrieve the data: use `Recording`, `RecordingStream`, `jcmd JFR.start/JFR.dump`, or JDK Mission Control (JMC) depending on your needs and environment.

Defining an event class **does not mean a `.jfr` file always exists**. There must be an active recording and the event must be enabled. `Event.isEnabled()` indicates whether an active recording has enabled that event type; `Event.shouldCommit()` also evaluates the **duration threshold** to avoid gathering expensive payloads for events that will be discarded.

### 6.2. `isEnabled()`, `begin()`, `end()`, `shouldCommit()`, `commit()`

Typical lifecycle:

```java
// Illustrative code for a WorkEvent event variable and business logic elsewhere:
if (event.isEnabled()) {
    event.begin();
    // Execute the processing block to measure, ensuring end() in finally when needed.
    event.end();
    if (event.shouldCommit()) {
        event.operation = "checkout";
        event.success = true;
        event.commit();
    }
}
```

This illustration is **not** a complete wrapper for business code that can throw exceptions. In a real wrapper, **you must never skip business logic when JFR is disabled**: the task must always execute, and only the observation branch is toggled. `end()` should run in `finally` so that even if application code throws, the duration is closed and the outcome is recorded according to policy.

Note: a JFR `Event` has an **intrinsic duration** field when using `begin()`/`end()`; you do not need to create a second duration field unless you want to measure a different interval. Custom event fields should be primitives, `String`, `Class`, or `Thread` per the JFR API; complex types such as arbitrary objects, arrays, or enums do not automatically become event payloads.

### 6.3. Thresholds and Stack Traces

Example of a recording that only keeps events slower than 20 ms:

```java
// In the place configuring Recording recording:
recording.enable(CheckoutFinishedEvent.class)
        .withThreshold(java.time.Duration.ofMillis(20))
        .withoutStackTrace();
```

This snippet is configuration inside a program that already has a `Recording` and event class. **A threshold does not change the runtime of the business method**; it filters event storage. In instrumentation that measures many ultra-fast methods, consider thresholds/sampling to avoid generating excessive events. Stack traces help investigation but carry overhead; if you do not need call stacks, disable stack traces for high-frequency events.

### 6.4. `RecordingFile` and `RecordingStream`

- `jdk.jfr.Recording`: manages recordings in-JVM, allowing configuration, start, stop, and dumping to a file.
- `jdk.jfr.consumer.RecordingFile`: reads `.jfr` files; `readAllEvents(Path)` is suitable for **small files** and should not be used to load huge production recordings entirely into memory.
- `jdk.jfr.consumer.RecordingStream`: consumes JFR events from the running JVM via callbacks; requires managing retention/flush/callback lifecycle.
- `jdk.jfr.consumer.EventStream`: API for streaming sources in the corresponding pattern.

Both recording and streaming require accounting for event rate, data age, data size, potential event loss under overload, and access permissions to recordings. JFR is suited for **diagnostic telemetry**; do not assume it is an audit ledger guaranteed to retain every event indefinitely.

## 7. Comparing Overhead on the Hot Path

Instrumentation points often sit directly on the application's critical path. Distinguish the cost components:

```text
Total overhead at probe
    ≈ reading clock/context
    + building payload
    + updating counter / enqueueing / writing JFR event
    + lock/atomic contention
    + allocation/GC caused by probe
    + (if any) synchronous I/O or blocking
```

This is a qualitative model, not a calibrated measurement formula. A few things to check:

**Counter:** `LongAdder.increment()` avoids storing per-event records, so cost is usually low when the number of counters is stable. However, looking up a key in a dynamic label map or stringifying a URL can still cost more than the increment itself.

**Queue:** `offer` does not block when full, but there is still the cost of creating the record, queue synchronization, cache misses, and GC pressure. If you serialize JSON before `offer`, a dropped event has already paid the serialization cost; instead, enqueue a **small, immutable** structure and do heavy work in the consumer when safe.

**JFR:** When an event is disabled, the enabled check can help skip preparing the payload. When enabled, costs relate to commit, fields, stack trace, threshold, buffering, and recording. For events occurring millions of times per second, measure on the actual target JDK and workload.

### Proper Timing

In Java, use `System.nanoTime()` to measure **elapsed intervals**:

```java
long started = System.nanoTime();
try {
    return performWork();
} finally {
    long elapsedNanos = System.nanoTime() - started;
    recordElapsed(elapsedNanos);
}
```

This is an **illustrative snippet** without definitions for `performWork()`/`recordElapsed()`. It does not use `System.currentTimeMillis()` to measure duration, because the wall clock can jump due to time synchronization. With JFR `Event.begin()/end()`, JFR records event duration automatically. When using a queue, timestamps for correlating events can use `Instant.now()`, but you must recognize that **observation time**, **enqueue time**, and **export time** are not the same.

**Preserving exceptions:** If an application method throws an exception, measurement logic in `finally` must not replace the business exception with an exporter error. If your policy allows dropping telemetry, handle observation errors outside the business exception path. If metrics are a mandatory legal/transactional requirement, design them under separate business constraints rather than hiding errors.

## 8. Standalone Java 17+ Example: Three Export Modes with the Same Sample Data

The following experiment demonstrates **three independent sinks**. It does not inject bytecode, uses no Java agent, and requires no external libraries; its purpose is to clarify lifecycle, capacity, and output. The queue section is intentionally **filled before draining** so the drop result is deterministic. In production, the consumer should run asynchronously; therefore, draining the queue synchronously in this program **does not fully simulate** concurrent production behavior.

### 8.1. File `OutputModesDemo.java`

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.atomic.LongAdder;

import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.FlightRecorder;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.StackTrace;
import jdk.jfr.consumer.RecordingFile;

public final class OutputModesDemo {

    private record Observation(int id, String operation) {
    }

    @Name("demo.MeasurementFinished")
    @Label("Measurement Finished")
    @Category({"Demo", "Instrumentation"})
    @StackTrace(false)
    public static final class MeasurementFinished extends Event {
        @Label("Operation")
        public String operation;

        @Label("Success")
        public boolean success;
    }

    public static void main(String[] args) throws Exception {
        // A. Counter: keeps total count, does not keep individual events.
        LongAdder counter = new LongAdder();
        for (int i = 0; i < 3; i++) {
            counter.increment();
        }
        System.out.println("counter-total=" + counter.sum());

        // B. Bounded queue: generate load before consumer appears.
        ArrayBlockingQueue<Observation> queue =
                new ArrayBlockingQueue<>(2);
        LongAdder dropped = new LongAdder();

        for (int id = 1; id <= 3; id++) {
            Observation observation = new Observation(id, "checkout");
            if (!queue.offer(observation)) {
                dropped.increment();
            }
        }

        int drained = 0;
        while (queue.poll() != null) {
            drained++;
        }
        System.out.println("queue-drained=" + drained);
        System.out.println("queue-dropped=" + dropped.sum());

        // C. JFR: only run when JVM actually supports Flight Recorder.
        if (!FlightRecorder.isAvailable()) {
            System.out.println("jfr=unavailable");
            return;
        }

        Path recordingFile =
                Files.createTempFile("output-modes-", ".jfr");

        try {
            try (Recording recording = new Recording()) {
                recording.enable(MeasurementFinished.class)
                        .withThreshold(Duration.ZERO)
                        .withoutStackTrace();
                recording.start();

                for (int i = 0; i < 2; i++) {
                    MeasurementFinished event =
                            new MeasurementFinished();
                    if (event.isEnabled()) {
                        event.begin();
                        event.operation = "checkout";
                        event.success = true;
                        event.end();
                        if (event.shouldCommit()) {
                            event.commit();
                        }
                    }
                }

                recording.stop();
                recording.dump(recordingFile);
            }

            long matched = RecordingFile
                    .readAllEvents(recordingFile)
                    .stream()
                    .filter(e -> "demo.MeasurementFinished".equals(
                            e.getEventType().getName()))
                    .count();

            System.out.println("jfr-events=" + matched);
        } finally {
            Files.deleteIfExists(recordingFile);
        }
    }
}
```

**Focus on the fixed behavior:**

- The counter increments **three times**, and no other thread updates it afterward, so `sum()` is guaranteed to equal 3.
- The queue has capacity 2; three consecutive `offer` calls **before draining** cause the third event to be rejected. The first two events are retrieved via `poll()`.
- When JFR is available and the recording is created successfully, the custom event type `demo.MeasurementFinished` is enabled with a zero threshold and without stack traces. The program commits two events, stops/dumps the recording, and counts only custom events with that exact name.
- The temporary `.jfr` file is deleted in `finally` to clean up the lab; if you want to open it in JDK Mission Control, temporarily remove the deletion step and print the file path.
- `RecordingFile.readAllEvents(...)` reads the entire file into memory; it is used here only because the recording is tiny.

### 8.2. Compile and Run

Requires **JDK 17 or newer**, the `jdk.jfr` module, and write permissions to the temporary directory.

```bash
javac --add-modules jdk.jfr -encoding UTF-8 OutputModesDemo.java
java --add-modules jdk.jfr OutputModesDemo
```

The same commands work in PowerShell. `--add-modules jdk.jfr` explicitly requests the module; on many JDK distributions, the module may already be resolved automatically.

**Expected stdout when JFR is supported and there are no environment errors:**

```text
counter-total=3
queue-drained=2
queue-dropped=1
jfr-events=2
```

If JFR is unavailable, the first three lines remain as above and the last line becomes:

```text
jfr=unavailable
```

In environments that cannot create a recording or write files, JFR/I/O operations may throw an exception; in that case, you **must not** pretend the output is `jfr-events=2`. Check filesystem permissions, the JFR repository, `java -version`, and whether the `jdk.jfr` module is present in the runtime image.

### 8.3. Reading Each Output According to Its Purpose

**Counter:** We know the total is 3, but we **do not know** which IDs appeared. That is appropriate if the goal is only the completion count.

**Queue:** We know 2 records were drained and 1 was dropped. If you only read `queue-drained=2` without `queue-dropped=1`, you might mistakenly think the system only received two events. Therefore, **a drop counter is part of the queue design**, not an optional metric.

**JFR:** There are two events in the recording, but this count **is not derived** from the counter or the queue. The experiment explicitly creates two separate JFR events. If you configure `recording.enable(...)` with a high threshold, the number of captured events can differ even though the code created the event objects.

### 8.4. Inspecting JFR with External Tools

To keep the temporary file after running, you can temporarily replace `Files.deleteIfExists(recordingFile)` in the lab code with printing `recordingFile` and skipping deletion. Then:

```bash
jfr print --events demo.MeasurementFinished /path/to/recording.jfr
```

Replace `/path/to/recording.jfr` with the **actual path** printed; it is not a fixed value. The `jfr print` command inspects stored events and fields. For another running JFR environment, you can use `jcmd <pid> JFR.check` or `JFR.dump` if you have appropriate operational permissions. Do not attach to another JVM or enable recordings on production applications without authorization.

## 9. From the Lab to Probes Injected by a Java Agent

The hands-on example in Section 8 calls APIs directly. When moving to instrumentation, you must also solve:

1. **Selecting classes and methods:** use the right class names, class loaders, and modules; avoid instrumenting the agent's own helpers.
2. **Choosing a canonical recording point:** usually once on the exit path, handling both return and throw.
3. **Never blocking the hot path:** metric updates, non-blocking `offer`, and JFR enabled guards can fit; synchronous network I/O does not.
4. **Preventing recursion loops:** if instrumentation wraps a serializer, logger, exporter, or `LongAdder`, the probe itself can re-enter and cause recursion.
5. **Preserving method semantics:** return values, exceptions, `finally`, synchronization, thread context, and class initialization must remain intact.
6. **Using a proper time source:** use monotonic `nanoTime` for duration; do not mix wall clock and `nanoTime` for direct comparison.
7. **Minimizing observed data:** keep only stable operation/outcome and error categories; do not stringify entire input objects.
8. **Having a fast-off path when disabled:** if JFR/event sinks are disabled, skip constructing expensive payloads.

### 9.1. Illustrative Wrapper for Outcomes, Not a Complete Transformer

```java
// Java pseudocode at the application layer where helpers are already defined.
// Not a standalone program and not bytecode injection.
long started = System.nanoTime();
boolean success = false;

try {
    Result result = businessOperation();
    success = true;
    return result;
} finally {
    long elapsedNanos = System.nanoTime() - started;
    safeObserve("checkout", success, elapsedNanos);
}
```

`Result`, `businessOperation()`, and `safeObserve(...)` here are **architectural placeholders**. This pattern must be wired carefully into control flow if a method has checked exceptions, multiple return paths, or complex state updates. For a bytecode transformer, use a library/CodeBuilder to produce valid CFGs and stack frames rather than copying this prototype as a complete method.

### 9.2. Safe Placement of `safeObserve`

In an application where business success takes priority, the observation layer should have a predefined error-handling policy:

```java
// Illustrative code inside a helper where queue and dropCounter are already declared.
static void offerSafely(Observation event) {
    if (!queue.offer(event)) {
        dropCounter.increment();
    }
}
```

This is not a standalone Java class. In production, you must decide whether `Observation` is allocated when disabled, how to handle unexpected sink errors, and who owns shutdown. Do not swallow `Throwable` unconditionally in a way that hides `OutOfMemoryError` or severe VM errors; fail-open/fail-closed policies must be agreed upon by operations and business owners.

## 10. Counters, Queues, and JFR Can Be Combined with Clear Responsibilities

Example requirements:

- A dashboard showing throughput/errors per minute.
- Details of a few representative requests during anomalies.
- Correlation with GC/locks on the JVM timeline when latency spikes.

A sensible design might be:

```text
One checkout completes
   │
   ├─ completed_total.increment()         (always enabled)
   ├─ failed_total.increment()            (failure only)
   ├─ queue.offer(error summary)          (failure or sample only)
   └─ JFR duration event                  (only when recording enabled
                                          and exceeds threshold)
```

The key point is that **each sink retains a different level of detail**. You must not add the `completed_total` counter, the number of queue messages, and the number of JFR events together and treat the sum as total requests. Those numbers can differ **by design** due to filtering, sampling, drops, and thresholds.

Name and document your denominators: for example, `queue_drop_total / queue_attempted_total` is the queue rejection rate, **not the checkout failure rate**. `jfr-events` is the number of events stored/read in a recording, not necessarily equal to the number of method invocations.

## 11. Synchronization, Latency, and GC Cost

### 11.1. Object Allocation Cost

Each queue event is typically an object or a slot in a ring buffer; a JFR event also has a corresponding object when code creates an instance. On the hot path, avoid:

```java
// Example of what NOT to do when drops happen frequently:
String details = expensiveSerializeEntireRequest(request);
queue.offer(new FullEvent(details));
```

`expensiveSerializeEntireRequest` and `FullEvent` are illustrative names. If the queue is already full, serialization work is wasted; if the request contains sensitive data, it also creates an extra copy of that data on the heap.

Instead, keep small fields, approved IDs, and a fixed enum-like status; if expensive processing is needed, do it on the consumer side **after receiving** the record, without passing references to mutable objects that the application will modify later. Capture a small immutable snapshot and enqueue it.

### 11.2. Thread Coordination Cost

Do not spawn **a new thread for every observation**. Use one or a bounded number of workers that batch and flush. A queue with a single consumer preserves the queue's own dequeue order; multiple workers increase throughput, but export completion order can change.

### 11.3. JFR Cost

Do not enable stack traces for every micro-event by default. Use `isEnabled` before expensive payloads, and `shouldCommit` after duration is known to evaluate thresholds. When JFR configuration changes at runtime, events can be toggled between calls; instrumentation must remain functionally correct even as collection changes.

### 11.4. How to Benchmark

Measure multiple variants under the same workload:

```text
baseline: no instrumentation
probe-only: measure and counter only
probe+queue: measure and enqueue/consumer
probe+JFR: measure and Recording enabled with target config
```

Compare p50/p95/p99 latency, throughput, CPU, allocation rate, GC pauses, drop rate, and export delay. Run sufficient warm-up and avoid drawing conclusions from a single short benchmark on a laptop. A tiny queue in the lab is **for creating a reproducible drop scenario**, not a recommendation for capacity 2 in production.

## 12. Limits and Reliability of Each Sink

### Counter

- While the process is alive, updates are held in memory according to the chosen type.
- After a crash, unscraped snapshots can be lost.
- `LongAdder.sum()` is not an atomic snapshot while producers are running; `AtomicLong.get()` is atomic for a single variable, but reading multiple counters sequentially is still not an atomic snapshot across multiple metrics.
- A counter cannot prove which specific event occurred when per-transaction reconciliation is required.

### Event Queue

- `offer(true)` only confirms the event entered the queue at that moment.
- A worker pulling an event from the queue does not guarantee the backend received it.
- A backend ack does not necessarily mean downstream durable processing completed.
- Retries can cause duplicates; crashes can lose in-RAM records.
- If you need at-least-once/dedup/exactly-once delivery with business semantics, you need a proper durable delivery mechanism rather than inferring it from a Java queue.

### JFR Event

- Events are committed according to enabled/threshold configuration and recording limits.
- JFR data has its own retention, buffers, disk repository, and lifecycle.
- JFR captures JVM context much better than a counter, but it is not an unbounded guaranteed transaction log.
- A JFR event does not automatically become a metric alert; you need a consumer/aggregation if you want dashboards or rates.
- Using `String` fields does not mean payloads are redacted; data must be controlled when creating the event.

**Common takeaway:** The export mechanism **does not replace** verifying probe correctness. A counter incremented in the wrong place is still a wrong metric; a queue that delivers 100% of wrong events still produces wrong data; a complete JFR file cannot fix a probe injected into the wrong method.

## 13. Common Pitfalls and How to Read Them Correctly

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| Counter increments but dashboard is empty | Missing exporter/scraper or backend is not receiving | Check metrics export pipeline and scrape interval |
| Counter at scrape time is lower than instantaneous expectation | `LongAdder.sum()` is not an atomic snapshot under concurrent updates | Evaluate rates over windows, do not use as a ledger |
| Time series count grows continuously | Labels contain request/user IDs or raw URLs | Bound cardinality, normalize operations |
| Queue is full, response time increases | Using `put` or synchronous serialization before enqueue | Review drop/sampling/batching and latency budget |
| Queue is not full, but exports are missing | Worker crashed, batch failed, or sink returned errors | Track accepted/exported/failed, acks, and retries |
| Drop = 0, but data is lost after crash | In-memory queue is not durable | Design a durable sink if required |
| Duplicate exported data | Retries after timeout or multiple probes for the same event | Attach event identity/dedup appropriately and avoid double instrumentation |
| JFR Event does not appear | Recording not started, event disabled, threshold too high | Check `isEnabled`, `shouldCommit`, and recording config |
| JFR has events, but parser cannot find them | Wrong event name filter or reading the wrong `.jfr` file | Check `@Name`, file path, and start/stop times |
| JFR causes high overhead | Events too frequent, heavy payload/stack trace | Use thresholds, sampling, disable stack traces, and benchmark |
| Event fields are missing | JFR only supports a limited set of field types | Use primitives/String/Class/Thread, check annotations |
| Agent causes recursion or `StackOverflowError` | Instrumenting the agent's own helpers/exporters or loggers | Exclude agent classes, guard reentrancy, check classloaders |
| Agent swallows or alters business exceptions | Measurement/export error escapes `finally` | Isolate telemetry error policy from the business flow |
| JFR unavailable | Runtime image/JVM lacks JFR or policy blocks it | Check JDK, modules, and repository permissions |
| Method latency increases when measurement is enabled | Producer does heavy work, blocks, or allocates too much | Shrink payload, move work off the hot path, and benchmark |

## 14. Pre-Production Deployment Checklist

1. **Define the question:** rate, distribution, event-by-event, or JVM timeline? Is forensic/audit capability needed?
2. **Define the counting unit:** request, attempt, retry, method call, transaction, or exception?
3. **Choose the recording point:** entry/exit/throw; is duration needed for failed calls too?
4. **Choose the primary sink:** counter for aggregates, queue for event pipelines, JFR for runtime diagnostics.
5. **Design the schema:** stable names, minimal fields, clear units, timestamps/durations.
6. **Bound cardinality:** avoid user IDs, raw URLs, and full exception messages in labels.
7. **Set an overhead budget:** how many nanoseconds/microseconds, allocations, CPU, and event rate?
8. **Choose overflow behavior:** `offer` + drop metric, sampling, batching, or controlled blocking.
9. **Define retention/durability:** how long data must be kept, and what may be lost on crash/restart?
10. **Define errors and retries:** when the sink fails, must the app continue or fail? Who decides?
11. **Define shutdown:** stop producers, bounded drain, flush/close consumers and recordings.
12. **Control privacy:** redaction, access control, and data lifecycle in each backend.
13. **Protect the agent:** do not instrument itself, avoid class-loader recursion and heap exhaustion.
14. **Monitor the tooling itself:** accepted, dropped, consumer failures, exporter latency, and queue depth.
15. **Test intentionally:** normal load, bursts, full queue, disabled JFR, thresholds, crashes, and slow sinks.
16. **Compare with/without agent:** business semantics, p95/p99 latency, CPU, GC, log volume, and recording size.

## 15. Tool Selection Scenarios

**Scenario A — An API gateway needs QPS and error rate.**  
Choose counters partitioned by stable operation/outcome; scrape periodically and compute rates over windows. If latency distribution is needed, add a histogram with reasonable buckets rather than creating an event record for every request just to count.

**Scenario B — Need to send compact details for 1% of failed requests to a collector.**  
Apply controlled sampling and `offer` into a bounded queue. Record attempted/sampled/accepted/dropped counts; have a worker batch and retry according to policy. Publish the sampling rate during analysis.

**Scenario C — A Java server occasionally slows down during GC or lock contention.**  
A custom JFR Event with duration and low-cardinality operation is a good fit. Enable recordings on demand or configure thresholds to correlate on the same timeline with GC/lock/JVM events. Avoid making network calls directly from the slow method.

**Scenario D — Audit every money transfer with exact reconciliation.**  
Do not use counters, in-RAM queues, or JFR as the **single source of truth**. You need durable transaction storage/transactional outbox and guaranteed delivery mechanisms; telemetry only supports observability.

**Scenario E — Debug a rare failure when the remote backend is unavailable.**  
Counters still provide error rates, a JFR recording on the JVM can retain diagnostic context if enabled, while a remote queue may drop during a network outage. Understand data retention and never promise that every event will survive.

**Scenario F — A method is called millions of times per second.**  
Choose counters or sampling/thresholds first; avoid allocations and string formatting on every call. If enabling JFR, benchmark with realistic config; if using a queue, enforce capacity and an admission/drop policy.

## 16. Self-Check Questions

**1. If you need the total error count over 5 minutes, is a queue better than a counter?**  
Not necessarily. A counter is more suitable when you only need aggregates; you still need an exporter and a time-window delta calculation.

**2. Is `LongAdder.sum()` an atomic snapshot while multiple threads are incrementing?**  
No. The value is exact when there are no concurrent updates; under concurrent updates, the result may exclude some in-flight changes.

**3. What does `queue.offer(event)` returning `false` mean?**  
It could not insert immediately because the queue has no remaining space; with a bounded `ArrayBlockingQueue`, `offer` does not block and requires a drop/sampling policy.

**4. Does `queue.offer(event)` returning `true` mean the backend has stored the event?**  
No. It only entered the internal queue; the consumer/exporter may fail or the process may crash.

**5. Should you use `put` inside an instrumented request-serving method?**  
Be very cautious. `put` can block indefinitely when full, increasing latency or causing deadlocks depending on system context.

**6. How does `Event.isEnabled()` differ from `Event.shouldCommit()`?**  
`isEnabled()` indicates the event is enabled in at least one recording; `shouldCommit()` also checks the duration-based threshold to decide whether the event should be written.

**7. Does calling `Event.commit()` send the event to a remote tracing system?**  
Not yet. It submits data to JFR inside the JVM; recordings/streams/collectors are separate components.

**8. Can JFR fields hold arbitrary Java objects or arrays?**  
Not automatically like POJO serialization; supported field types are restricted by the JDK. Use supported types and avoid sensitive data.

**9. A method is counted once in a counter, but there is no JFR Event: is it broken?**  
Not necessarily. JFR may be disabled, have a threshold, or be sampled; different sinks have different semantics.

**10. Can JFR be used as the sole audit log?**  
It should not. JFR is a diagnostic recording with buffers/retention and can drop or omit events under certain conditions; auditing requires different durability guarantees.

**11. Should you measure duration with `System.currentTimeMillis()` or `System.nanoTime()`?**  
Use `nanoTime()` to measure elapsed intervals; use wall clock for timestamps when needed.

**12. Why does the queue demo always drop one event?**  
Because the queue has capacity 2 and three `offer` calls happen **before** draining; the producer and consumer do not run concurrently in the lab.

**13. Why should `RecordingFile.readAllEvents` not be used to read very large production JFR files?**  
Because it loads all events into a list, which can sharply increase memory usage. For large files, use streaming/iterator reading and resource limits.

**14. If you want p99 latency, can you compute `sum(duration)/count`?**  
No. That is the mean; you need a distribution/histogram or raw duration events with an appropriate percentile calculation method.

**15. How do you prevent instrumentation from altering a method's exceptions?**  
Design the probe in `finally` and manage sink errors according to policy, avoiding throwing telemetry exceptions on top of business exceptions.

## 17. Official References

- [JDK 17 — `LongAdder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): increment/sum and the caveat that sum is not an atomic snapshot.
- [JDK 17 — `AtomicLong`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html): atomic integer operations.
- [JDK 17 — `ArrayBlockingQueue`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): bounded buffer, `offer`, `put`, and blocking differences.
- [JDK 17 — `Event`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Event.html): custom JFR events, `isEnabled`, `begin`, `end`, `shouldCommit`, `commit`.
- [JDK 17 — `Recording`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Recording.html): enabling recordings, limits, stopping, and dumping to a file.
- [JDK 17 — `RecordingFile`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): reading events from `.jfr` and limits of `readAllEvents`.
- [JDK 17 — `RecordingStream`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html): streaming custom/JVM events.
- [JDK 17 — `java.lang.instrument.Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): Java agent execution environment.
- [JDK 17 — Flight Recorder API Programmer's Guide](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder-api-programmers-guide.pdf): event creation and consumption model.

**Takeaway:** When you only need **counts**, use counters and an appropriate exporter. When you need **detailed records with a separate pipeline**, use a **bounded queue** with a drop/backpressure/delivery policy. When you need a **diagnostic timeline synchronized with JVM activity**, use a **JFR Event** with configured enabled/threshold/recording settings. All three must preserve business behavior, control overhead, and make explicit what data is **not guaranteed** to survive.