# 16.9. Distinguishing Live Event Processing from File Reading; Consumer Latency and Overhead

Java Flight Recorder (JFR) records JVM and application events without requiring manual log statements everywhere. When building a JFR analysis program, a key architectural decision is whether to **consume events continuously while the JVM is running** or **read a saved recording file**. Both use JFR data, yet they differ in when data arrives, operational overhead, completeness of evidence, and consumer lifecycle.

In this lesson, "live event processing" means **JFR event streaming** using `RecordingStream` or `EventStream` reading an active repository. It does **not** mean `Event.commit()` invokes a callback synchronously on the same thread like a conventional Java listener. Event streaming still goes through buffers and flushes; **near real-time does not mean instantaneous**.

This lesson focuses on Java 17+ and the `jdk.jfr` / `jdk.jfr.consumer` APIs: choosing active vs. passive streams, distinguishing file reading, measuring latency, managing callbacks, and comparing practical costs.

## 1. Separating Three Parts: Event Source, Storage, and Consumer

A JFR event is emitted when the JVM or application code marks an activity: GC pause, CPU load, file read, allocation sample, or a custom event. JFR captures only events that are currently **enabled** and satisfy settings such as threshold, period, or stack-trace configuration.

Conceptual model:

```text
JVM / application emits event
         │
         ▼
JFR records enabled events
         │ (thread-local buffers, buffer/chunk layers)
         ▼
JFR recording/repository ───────────┬────────────────────┐
         │                           │                    │
         ▼                           ▼                    ▼
 EventStream reads               Dump/stop recording  RecordingStream
 active repository                   │                creates recording
         │                           ▼                    │
         ▼                      .jfr file             streams events
 onEvent / onFlush                   │                    │
         │                           ├── RecordingFile    ▼
  aggregate/alert                    └── EventStream.openFile
                                         │
                                         ▼
                                   offline analysis
```

The diagram illustrates **API roles**, not three completely independent data pipelines: `RecordingStream` creates its own recording for the current JVM and registers a consumer, whereas `EventStream.openRepository()` is a passive consumer reading a repository without configuring a new recording. Events are delivered to consumers in **batches** after flushes.

File reading and streaming are not distinguished by "whether callbacks are used". `EventStream.openFile(path)` **also** invokes `onEvent(...)`, yet its source is an **existing file**; it does not follow new JVM events like a live repository stream.

## 2. Four Core APIs and When to Use Each

| Java 17+ API | Source | Who controls JFR recording? | When to use |
| --- | --- | --- | --- |
| `new RecordingStream()` | The **current**, running JVM. | The stream itself can `enable/disable` events, set periods/thresholds, and manage the recording. | Building an in-process app/agent that needs live signal detection while running. |
| `EventStream.openRepository()` | The JFR repository of the **current** JVM; also has an overload taking a repository directory. | This consumer **does not start a recording itself**; data comes from a recording configured elsewhere by the JVM/app. | Passively listening to events already enabled by another recording. |
| `EventStream.openFile(Path)` | A `.jfr` file. | File is already created; does not modify the recording source. | Using callbacks/filters/aggregations over archived data. |
| `new RecordingFile(Path)` | A `.jfr` file. | File is already created; consumer iterates sequentially. | Running an analysis loop with explicit control over memory and read state. |

`RecordingFile.readAllEvents(path)` is convenient for small files because it returns `List<RecordedEvent>`, yet **must not be used on large recordings**: the list and event objects can consume huge heap memory. Replace it with `RecordingFile` + `hasMoreEvents()/readEvent()` or `EventStream.openFile()`.

An extended case exists: `RemoteRecordingStream` (via JMX/supported remote connectors) lets a consumer run outside the target JVM. That adds serialization, network, access-control, and remote-side processing costs. **Do not equate** reading a `.jfr` file copied to an analysis machine with remote live streaming; a saved file can be processed offline even after the source JVM has exited.

### Difference between "active" and "passive" streams

`RecordingStream` is **active**: it creates a recording for the current JVM and can control event settings:

```java
try (var stream = new jdk.jfr.consumer.RecordingStream()) {
    stream.enable("jdk.CPULoad")
          .withPeriod(java.time.Duration.ofSeconds(1));
    stream.onEvent("jdk.CPULoad", event -> {
        double percent = 100.0 * event.getFloat("jvmUser");
        System.out.printf("JVM user CPU: %.2f%%%n", percent);
    });
    stream.start();
}
```

This illustrative snippet uses fully qualified names and can sit inside `main`; the `try` block alone **is not a standalone Java file**, and `start()` blocks until the stream is closed. A complete, time-bounded program appears in the hands-on section below.

`EventStream.openRepository()` is **passive**: it reads events produced by other recordings. By default, the stream starts from the **next flushed event**, rather than replaying all history automatically; to adjust the start point, call `setStartTime(...)` before `start()`, within what the repository still retains. If no recording enables the target event, callbacks will receive nothing.

## 3. Streaming Is Not a Synchronous Callback on `commit()`

Suppose the application calls `event.commit()` at `10:00:00.000`. JFR does not immediately hand that event to readers: it passes through buffers, chunks/flushes, and then the consumer thread parses and runs actions. That introduces latency.

The JDK 17 `EventStream` Javadoc specifies:

- Events are **delivered in batches**; `onFlush(Runnable)` runs after a batch is flushed, making it suitable for publishing accumulated stats.
- Events **within a single batch** are ordered by end time under default ordered mode; **across batches**, there is no absolute global chronological guarantee.
- `start()` processes on the calling thread; `startAsync()` runs callbacks on a dedicated thread—it does not turn callbacks into parallel worker pools.
- `close()` stops the stream and releases resources; it **does not guarantee** all callbacks have finished when returning.
- When retaining event data beyond the callback, understand `setReuse(boolean)`: in reuse mode, the same `RecordedEvent` object may be reused for subsequent events.

**Streaming latency has no fixed SLA purely from picking an API.** It depends on flush intervals, event rates, data volume, CPU/I/O capacity, OS scheduling, consumer count, callback work, and repository write/retention behavior.

## 4. Consumer Latency Must Be Measured from the Right Anchor

Define:

- `t_event_end`: event end timestamp recorded in `RecordedEvent.getEndTime()`.
- `t_visible`: when the event/batch is available for the stream to read.
- `t_callback`: when the callback actually executes and completes minimal extraction.
- `t_action`: when the dashboard/alert/final sink receives the result, if applicable.

These latencies mean different things:

```text
delivery lag   = t_callback - t_event_end
processing lag = t_action - t_callback
end-to-end lag = t_action - t_event_end
```

These are **observability timing metrics**, not the event's own GC/CPU duration. For a long-running duration event, `getEndTime()` is more appropriate than `getStartTime()` when measuring "how long after an operation finished did we observe the event".

Hypothetical example:

| Milestone | Timestamp |
| --- | --- |
| Event finishes | 12:00:00.000 |
| JFR batch becomes readable | 12:00:00.350 |
| Callback processes event | 12:00:00.420 |
| Metric/alert finishes sending | 12:00:00.700 |

Here: delivery lag = **420 ms**, processing lag = **280 ms**, end-to-end lag = **700 ms**. These four timestamps illustrate the math, **not standard JFR latency figures**. If a callback blocks on I/O or locks, `t_callback` slips further and subsequent events are delayed too.

Within a single process, you can estimate `Duration.between(event.getEndTime(), Instant.now())` inside the callback. This is a **wall-clock estimate**, sensitive to system clock adjustments and callback overhead. For remote consumers, source and consumer clocks must be synchronized; clock skew can produce negative or badly skewed measurements. Measure internal processing lag with a monotonic clock (`System.nanoTime()`) around callbacks/queues; **never subtract `nanoTime` values across two different JVMs**.

### File readers have a different kind of latency

In dump/stop → read `.jfr` mode:

```text
event occurs
    → recording write/flush
    → dump or stop produces complete file
    → copy/download file (if different host)
    → consumer opens file, parses, and analyzes
```

**Time-to-insight** depends on dump schedules and file transfers, yet **file-reading throughput** can be very high during continuous offline processing. Never compare "the file consumer reads 100,000 events/s" against "the live stream has 2-second lag" as equivalent metrics. One measures parsing throughput over existing data; the other measures time from event occurrence to observation.

## 5. Where Does the Cost Live?

Choosing streaming vs. file reading does not determine total overhead alone. Separate **JFR capture cost** from **consumer cost**.

| Cost source | Streaming | File reading |
| --- | --- | --- |
| Event creation, stack traces, sampling, thresholds | Present; depends on enabled event types/settings. | Paid when the recording was captured; offline reading does not alter source JVM settings. |
| JFR buffers and repository/chunks | Present per normal JFR operation. | Reads completed chunks in the file. |
| Parsing/instantiating `RecordedEvent` | Continuous during runtime. | Concentrated when analyzing the file. |
| Event sorting | Can add cost when ordered. | Depends on API/analysis pattern and event order. |
| Aggregation/filtering | Runs in callbacks, typically continuously. | Runs in read loops or file event callbacks. |
| Logging, HTTP calls, DB writes per event | Can cause the consumer to fall behind the source. | Still costly, though runnable off-production with controlled batching/retries. |
| Consumer memory/GC | Directly impacts the JVM if consumer is in-process. | Can be offloaded to a separate analysis JVM/host. |
| File storage/transfer | Repository and retention; remote streams add network/serialization cost. | `.jfr` disk size, read/copy/storage I/O, and data security. |

**Event configuration cost matters enormously.** Enabling lots of stack-trace events at threshold 0, or large-payload custom events per request, burdens the producer even if the callback only increments a counter. Never assume a single fixed percentage overhead across all configurations.

**Callback cost easily dwarfs event recording cost.** Calling `System.out.println(event)` on every event, serializing big JSON strings, calling REST APIs, or running synchronous DB queries burns CPU/I/O, holds locks, and stalls the whole consumer pipeline. Extract needed fields, aggregate counters in memory, and flush periodically in batches.

### Retention is not full backpressure

`RecordingStream.setMaxAge(Duration)` and `setMaxSize(long)` cap how much recording data is retained (by age or bytes) while streaming. They bound disk/repository growth, **not** guarantee exactly-once delivery or force producers to throttle for slow consumers. Under overload when old data expires via retention, consumers can miss unread events; additionally, thresholds/sampling and JFR buffers affect which events are captured.

If a system requires **exactly-once auditing or zero record loss**, JFR streams are generally not durable business queues with ACKs/replays. Use a proper business event pipeline with persistence, retries, deduplication, and checkpoints; use JFR for diagnostics and observability.

## 6. Designing Lightweight Callbacks and Managing Batches

A low-latency consumer does minimal work inside `onEvent`:

1. Subscribe only to required events via `onEvent("event.name", ...)`.
2. Inside the callback, extract needed scalar fields immediately and increment counters/sums or push to a **bounded queue**. Avoid retaining full `RecordedEvent` objects unnecessarily.
3. Use `onFlush` to collect and publish batch statistics (with controlled I/O).
4. Bound queue capacity and specify overload policies: drop, coalesce, sample, or throttle collection. Never allow unbounded queues.
5. Track consumer lag, queue depth, error counts, and batch completion timestamps.
6. On shutdown, decide whether remaining queue items/final metrics must drain; JFR stream `close()` alone does not guarantee draining every callback.

### Understanding `setReuse` and `setOrdered`

```java
stream.setReuse(true);   // reduces RecordedEvent allocations; do not retain object after callback
stream.setOrdered(false); // reduces sorting work when chronological order is not needed
```

These are **illustrative lines** placed before `start()` on an `EventStream` or `RecordingStream`, not a complete program. JDK 17 docs note that `RecordedEvent` instances may be **reused by default**; if a callback stores the object for use after returning, you must call `setReuse(false)` before starting or—**even better—immediately copy essential values** into an immutable DTO. Never push references to potentially reused objects onto a queue and read them later, as their fields may change to another event's data.

`setOrdered(false)` skips sorting in some cases, meaning consumers **can no longer rely on event arrival order** to construct timelines. If you must correlate events chronologically, keep ordering enabled and still check timestamps—ordering is guaranteed **within a batch**, not strictly across all batches globally.

### Error handling and lifecycle

Register `onError(Consumer<Throwable>)` to capture callback/parser failures; without a handler, errors may default to printing on `stderr`. Remember that **catching an error does not automatically restart the stream or prevent data loss**. For long-lived consumers, add bounded retry policies, health checks, and alerts.

`start()` blocks the calling thread. `startAsync()` runs callbacks on a dedicated thread; startup code can continue, yet exiting `try-with-resources` closes the stream. A classic mistake is calling `startAsync()` and immediately letting `main` exit: there was no time for event flushes, leading people to think recording is broken.

## 7. Runnable Example 1 — In-JVM Streaming (Java 17+)

The following `LiveCpuStream.java` program creates a `RecordingStream`, enables periodic CPU events, computes event counts and observed delivery lag per batch, and **stops after 10 seconds**. It avoids HTTP calls or per-event logging, printing just one line when `onFlush` sees samples.

```java
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import jdk.jfr.consumer.RecordingStream;

public final class LiveCpuStream {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger samplesInBatch = new AtomicInteger();
        AtomicLong lastDeliveryLagMs = new AtomicLong(-1);

        try (RecordingStream stream = new RecordingStream()) {
            stream.enable("jdk.CPULoad")
                  .withPeriod(Duration.ofSeconds(1));

            stream.setMaxAge(Duration.ofMinutes(1));
            stream.setMaxSize(16L * 1024 * 1024);

            stream.onEvent("jdk.CPULoad", event -> {
                long lag = Duration.between(
                        event.getEndTime(), Instant.now()).toMillis();

                samplesInBatch.incrementAndGet();
                lastDeliveryLagMs.set(lag);
            });

            stream.onFlush(() -> {
                int n = samplesInBatch.getAndSet(0);
                if (n > 0) {
                    System.out.printf(
                            "batchSamples=%d lastDeliveryLagMs=%d%n",
                            n, lastDeliveryLagMs.get());
                }
            });

            stream.onError(error -> error.printStackTrace(System.err));
            stream.startAsync();

            Thread.sleep(10_000);
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac LiveCpuStream.java
java LiveCpuStream
```

**Conditional output:** you may see lines like:

```text
batchSamples=2 lastDeliveryLagMs=428
batchSamples=1 lastDeliveryLagMs=365
```

These are **illustrative numbers**, not fixed stdout: batch counts, event counts, flush times, and lag fluctuate with the JVM, scheduling, and load. You may see fewer samples than expected if a flush does not occur before the stream closes. The 10-second window starts after `startAsync()` and does not guarantee exactly 10 events: `jdk.CPULoad` is periodic and passes through the JFR pipeline. For repeated trials, compare the **latency distribution** over longer windows rather than a single line.

`onFlush` here reads only the sample count of the just-observed batch, not total JFR events produced by the JVM. For stricter time windows, use timestamps/explicit windowing and handle late batches. In production, even printing one line per batch warrants checking frequency and stdout overhead.

## 8. Runnable Example 2 — Creating a File and Reading Offline (Java 17+)

For a controlled comparison, this section **creates a `batch.jfr` file containing 5 custom events**, then reads it via `RecordingFile`. Unlike the live example, once the file is written you can re-analyze it as many times as needed without keeping the source JVM running.

### 8.1. Creating the recording

Create `WriteBatchJfr.java`:

```java
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;

public final class WriteBatchJfr {
    @Name("demo.Batch")
    public static final class BatchEvent extends Event {
        public int units;
    }

    public static void main(String[] args) throws Exception {
        try (Recording recording = new Recording()) {
            recording.enable(BatchEvent.class)
                     .withThreshold(Duration.ZERO);
            recording.start();

            for (int i = 1; i <= 5; i++) {
                BatchEvent event = new BatchEvent();
                event.units = 10 * i;
                event.commit();
            }

            recording.stop();
            recording.dump(Path.of("batch.jfr"));
        }

        System.out.println("Created batch.jfr");
    }
}
```

Compile and run:

```bash
javac WriteBatchJfr.java
java WriteBatchJfr
jfr summary batch.jfr
```

If file creation succeeds, **the Java program's stdout** is:

```text
Created batch.jfr
```

`jfr summary` prints metadata, duration, and event types of the recording depending on JDK version and environment; do not treat it as fixed program stdout. The custom event is named `demo.Batch` with `units=10,20,30,40,50`. Explicitly enabling the type with threshold 0 prevents the example from depending on default sampling or thresholds.

### 8.2. Reading sequentially without holding all events on the heap

Create `ReadBatchJfr.java`:

```java
import java.nio.file.Path;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public final class ReadBatchJfr {
    public static void main(String[] args) throws Exception {
        int count = 0;
        long totalUnits = 0;

        try (RecordingFile file =
                     new RecordingFile(Path.of("batch.jfr"))) {
            while (file.hasMoreEvents()) {
                RecordedEvent event = file.readEvent();

                if ("demo.Batch".equals(event.getEventType().getName())) {
                    count++;
                    totalUnits += event.getInt("units");
                }
            }
        }

        System.out.printf(
                "count=%d totalUnits=%d%n", count, totalUnits);
    }
}
```

Compile and run **after `batch.jfr` exists**:

```bash
javac ReadBatchJfr.java
java ReadBatchJfr
```

**Stdout when both steps succeed:**

```text
count=5 totalUnits=150
```

This result is deterministic because exactly 5 `demo.Batch` events were emitted. In practice, many other system event types may exist in the file, and the `getEventType().getName()` filter sums only the exercise's events.

This loop scans the file sequentially: each iteration holds one `RecordedEvent` plus two accumulators, without preloading a full list. **That does not mean memory usage is literally one event**, because the JFR parser maintains state, caches, and chunk structures; still, it is far better suited than `RecordingFile.readAllEvents(...)` for large files.

### 8.3. Callbacks from a **file** are still offline

The same file can be read via `EventStream.openFile`. Create standalone `ReadBatchWithCallbacks.java`:

```java
import java.nio.file.Path;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import jdk.jfr.consumer.EventStream;

public final class ReadBatchWithCallbacks {
    public static void main(String[] args) throws Exception {
        AtomicInteger count = new AtomicInteger();
        AtomicLong units = new AtomicLong();

        try (EventStream stream =
                     EventStream.openFile(Path.of("batch.jfr"))) {
            stream.onEvent("demo.Batch", event -> {
                count.incrementAndGet();
                units.addAndGet(event.getInt("units"));
            });

            stream.start();
        }

        System.out.printf("count=%d totalUnits=%d%n",
                count.get(), units.get());
    }
}
```

Compile and run:

```bash
javac ReadBatchWithCallbacks.java
java ReadBatchWithCallbacks
```

**Stdout:**

```text
count=5 totalUnits=150
```

Here `start()` processes the file to completion before printing totals. The callback API resembles a live consumer, yet this remains an **offline file consumer**. If the file does not exist or the format is unsupported, the program may throw `IOException`. Open recordings only from trusted sources and verify read permissions.

## 9. Listening to an Existing Recording Without Starting a New One

A **passive** example reading the current JVM's repository: the code below is a complete program, but it requires **another JFR recording with `jdk.CPULoad` enabled** in order to receive events.

Create `PassiveCpuListener.java`:

```java
import java.time.Duration;
import jdk.jfr.consumer.EventStream;

public final class PassiveCpuListener {
    public static void main(String[] args) throws Exception {
        try (EventStream stream = EventStream.openRepository()) {
            stream.onEvent("jdk.CPULoad", event -> {
                float cpu = event.getFloat("machineTotal");
                System.out.printf("machineCpu=%.1f%%%n", cpu * 100.0);
            });

            stream.startAsync();
            Thread.sleep(Duration.ofSeconds(10).toMillis());
        }
    }
}
```

Compile and run with a recording enabled from the command line:

```bash
javac PassiveCpuListener.java
java -XX:StartFlightRecording=filename=passive.jfr,settings=default,dumponexit=true PassiveCpuListener
```

**Output:** lines like `machineCpu=...%` may appear, though counts and values are non-deterministic because JFR event settings and flush timing depend on the environment. `-XX:StartFlightRecording` creates **the recording at the launcher/JVM level**, while `EventStream.openRepository()` merely listens passively. If you omit the recording flag with no other recording active, do not expect `onEvent` to fire.

`EventStream.openRepository(Path)` takes the path to a **JFR repository directory**, **not an arbitrary `.jfr` file**. To read a saved file, use `openFile(Path)` or `RecordingFile(Path)`. Do not blindly open another JVM's repository without verifying permissions, format, and trust.

## 10. Choosing an Approach by Goal

| Need | Preferred option | Rationale |
| --- | --- | --- |
| Monitor GC pauses or CPU events to adapt behavior while JVM runs | `RecordingStream` or suitable consumer stream. | Detects new batches as they arrive; must control lag and callback impact. |
| Recording already started via `jcmd JFR.start`/app; only want to listen without altering capture config | `EventStream.openRepository()` in same JVM with valid repository. | Passive consumer; the source decides which events are recorded. |
| Post-incident investigation after the process has died | `RecordingFile`, `EventStream.openFile`, or JMC. | Archived data can be re-analyzed repeatedly; preserves evidence and comparisons. |
| Aggregating a huge file with limited analyzer heap | `RecordingFile` event-by-event or file event stream. | Avoids holding all events in a single `List`. |
| Dashboard needing metrics pushed to another service | Stream + batch aggregation + bounded queue. | Cuts per-event I/O, though requires backpressure policies and lag monitoring. |
| Reproducible reports, audits, post-incident verification | Saved `.jfr` file with version, settings, timestamps, checksum. | Fixed snapshot for multiple analysts regardless of how long a stream stayed up. |
| Durable event bus with ACKs and per-event retries for business events | Messaging/logging system built for business workflows. | JFR streaming does not replace guaranteed-delivery queues. |

A practical production design often **combines both**: streaming extracts lightweight signals for early alerts; when an anomaly fires, a `.jfr` file with sufficient retention is dumped/saved for deep offline analysis via JMC/`jfr`/APIs. If no recording existed or the target event was disabled upfront, you cannot "reconstruct" missing event history merely by opening a stream afterward.

## 11. Evaluating Cost with Controlled Experiments

Never decide "streaming is faster than files" on intuition. Using the same application, workload, JDK, and event types, compare these configurations:

1. **Baseline:** target events off; measure throughput, p95/p99 latency, CPU, heap/GC, RSS, and disk I/O.
2. **Recording-only:** enable equivalent JFR without running your custom consumer. The delta over baseline primarily reflects capture/chunk/storage overhead.
3. **Lightweight streaming:** add a consumer reading a few fields, incrementing counters, and flushing in batches; measure delivery lag p50/p95/p99 and processing rate.
4. **Streaming with real sink:** add queues and real metric export; measure queue depth, rejected/dropped/coalesced counts, and downstream latency.
5. **Offline read:** save the same recording and process it with `RecordingFile` in a separate JVM; measure read duration, events/s, peak heap, and **consumer** I/O.

Run workloads long enough to clear warm-up/JIT and establish representative event rates; repeat trials to measure variance. Never compare a 1 GB file against a stream with different event filters or time windows. Record exact event settings, thresholds, periods, stack traces, sampling, and retention.

Metrics to report:

| Metric | Purpose | Notes |
| --- | --- | --- |
| Observed event rate (events/s) | Actual load hitting the consumer. | Not necessarily equal to total app occurrences; JFR applies sampling/thresholds. |
| Delivery lag p50/p95/p99 | Delay from event end to callback. | Do not infer from the duration field; use appropriate clocks. |
| Consumer processing time | CPU/wall time for callbacks/aggregation/sink. | Measurable via `nanoTime()` on the same thread. |
| Queue depth, queue drop count | Shows whether downstream keeps up. | Requires bounded queues and overflow metrics. |
| Consumer heap allocation/GC | Detects callbacks creating too many objects. | `setReuse(false)` and payload parsing/logging can spike allocations. |
| Disk I/O, repository size, file size | Quantifies capture and retention cost. | `setMaxAge/Size` is not a zero-loss SLA. |
| Total file read time, offline events/s | Evaluates post-incident file throughput. | Not end-to-end alerting latency. |

### When callbacks become the bottleneck

If the JVM emits an average of **5,000 events/s** and a callback takes **1 ms/event** on average on a single sequential processing thread, the thread's theoretical ceiling is roughly **1,000 events/s** (excluding overhead). The system can fall behind by ~**4,000 events/s** if that rate persists—this arithmetic is a simplified model, not an exact predictor of JFR behavior or drop counts. Fixing it usually requires **fewer events and cheaper per-event work**, not simply throwing more heap at it.

Never offload heavy tasks onto an executor with an unbounded queue. Even if callbacks return fast, an ever-growing queue still inflates end-to-end latency and can OOM the JVM from the consumer itself. Use bounded queues and bounded in-RAM aggregation.

## 12. Common Misconceptions

- **"`RecordingStream` runs the callback immediately when `Event.commit()` executes."** False: JFR delivers in batches/flushes and on a separate consumer thread in async mode.
- **"Having `onEvent` means live reading."** False: `EventStream.openFile` also uses callbacks yet reads an existing file.
- **"`EventStream.openRepository()` automatically enables the events I want."** False: it requires an externally configured recording/source.
- **"Once `startAsync()` returns, `main` can exit right away."** False: you must keep the stream alive long enough for batches to be delivered.
- **"`close()` guarantees all events were processed."** False: `close` is not a drain/ACK guarantee.
- **"Calling `setMaxSize` helps the consumer keep up with producers."** False: that is a retention cap, not a callback throughput mechanism.
- **"`RecordedEvent` is always safe to enqueue by reference."** False: instances may be reused; copy fields or use `setReuse(false)` when warranted.
- **"`setOrdered(true)` guarantees global timeline order from start to finish."** False: ordering holds within a batch, not strictly across every batch.
- **"`RecordingFile.readAllEvents` is best for every file."** False: on large files it can exhaust heap memory.
- **"File reading uses callbacks so its latency equals live streaming."** False: file dumps/transfers delay when analysis starts.
- **"Receiving zero events means the system generated none."** False: inspect settings, thresholds, sampling, flushes, windows, filters, and recording sources.
- **"JFR is an exactly-once business message bus."** False: it is designed for observability/diagnostics, lacking business event-bus delivery, retry, and checkpoint contracts.
- **"Printing every event is practically free."** False: formatting strings/stacks, console/file I/O, and lock contention can outweigh JFR capture itself.
- **"A consumer on another host never affects the source JVM."** Not quite: reading an already-exported file adds minimal post-capture impact, whereas remote live streaming adds serialization/network/CPU cost, and enabling extra recordings/events always has overhead.

## 13. JFR Consumer Design Checklist

- [ ] Identify the exact source: `RecordingStream`, live repository, `EventStream.openFile`, or `RecordingFile`.
- [ ] Event types are enabled with appropriate thresholds/periods/stack traces; never treat an empty view as zero activity.
- [ ] Time windows and latency requirements are explicit; measure `event end → callback → final action` rather than only counting events.
- [ ] Callbacks stay lightweight; minimize console output, sync I/O, JSON serialization, and per-event DB queries.
- [ ] Memory/queue/retention bounds are set; lag, throughput, and drops are measured with clear overload policies.
- [ ] `RecordedEvent` instances are not retained after callbacks when reuse may occur; copy required fields.
- [ ] Batch/flush semantics, ordering, error handling, `start`/`close` lifecycles, and non-draining stops are well understood.
- [ ] For offline analysis, avoid `readAllEvents` on large files; store recordings and metadata for reproducibility.
- [ ] Compare overhead under identical workloads, settings, and JDKs; separate producer cost from consumer cost.
- [ ] Control access to files, repositories, and remote streams; JFR can expose class names, file paths, arguments, errors, stack traces, and sensitive custom event fields.

**Key takeaway:** JFR streaming enables **continuous observation with latency governed by flushing, buffering, and scheduling**, making it suited for alerts and lightweight metrics. File reading enables **repeatable analysis of a fixed recording**, ideal for deep investigation and post-incident verification. In both modes, actual overhead comes mostly from **event settings, event volume, consumer parsing/aggregation, and I/O**. A well-engineered consumer measures lag explicitly, keeps callbacks light, bounds resources, and never mistakes JFR for a guaranteed business event delivery queue.

### Official References

- [Oracle JDK 17 — RecordingStream](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html)
- [Oracle JDK 17 — EventStream](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html)
- [Oracle JDK 17 — RecordingFile](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html)
- [Oracle JDK 17 — Recording](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Recording.html)
- [OpenJDK JEP 349 — JFR Event Streaming](https://openjdk.org/jeps/349)
- [Inside Java — JFR Event Stream (API and Consumer Costs)](https://inside.java/2022/05/12/sip49/)
