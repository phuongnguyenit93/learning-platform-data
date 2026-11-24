# 16.10. Designing Non-Blocking Consumers and Managing Event Schema Evolution

Java Flight Recorder (JFR) serves both as a JVM diagnostic data source and as a Java API for reading events live or from `.jfr` files. A seemingly simple consumer—registering `onEvent` and sending every event to a database or HTTP endpoint—can quickly become a bottleneck: slow exporters block callbacks, data backs up, and the JVM burns extra CPU, memory, and I/O. Another risk arises when event producers rename fields, change types, or alter units, causing older consumers to throw exceptions, misread values, or break silently.

This lesson focuses on **two design responsibilities**:

1. **Keeping the system unblocked:** JFR callbacks perform only short, bounded work; heavy processing is decoupled through bounded queues with explicit overload policies.
2. **Surviving schema changes:** identify event types by stable names, validate fields defensively when reading, handle older/newer versions, and monitor incompatible schema drift.

The primary APIs belong to the `jdk.jfr` module, package `jdk.jfr.consumer`, available in JDK 17+ (check `Since` for individual methods). This is consumer design guidance; JFR settings, queue capacities, and acceptable loss tolerances must match real SLAs rather than relying on one universal default across all services.

## 1. Where Does the JFR Consumer Actually Run?

Three common reading modes exist:

| API | Scope | Execution model |
| --- | --- | --- |
| `RecordingStream` | Creates a recording and consumes events from the **current JVM** | Register callbacks, then call `start()` or `startAsync()` |
| `EventStream.openRepository(...)` | Reads events from the current JVM's repository or a specified repository path | Streams/tails chunk data from an existing recording source |
| `EventStream.openFile(Path)` / `RecordingFile` | Reads an existing `.jfr` recording file | Used for testing, offline analysis, and bounded file reprocessing |

**`startAsync()` does not spawn one worker per callback.** Per the JDK 21 API, `RecordingStream` callbacks execute on **a single dedicated stream-processing thread**. If a callback waits on the network, queries a DB, logs synchronously, or runs heavy aggregations, it still delays the stream from processing the next batch. With `start()`, the calling thread itself runs callbacks until the stream ends. Async mode merely moves where the callback thread runs; it does not magically supply downstream queues, retries, or backpressure.

`onEvent("fully.qualified.EventName", action)` receives a single matching event type and is generally more efficient than `onEvent(action)` filtering everything manually. `onFlush(Runnable)` fires after a batch is processed, fitting small counter snapshots or batch summaries; still, **avoid long network I/O inside flush callbacks**. `onError` and `onClose` provide visibility into stream errors and lifecycle, not application resource management.

## 2. Bounded-Queue Consumer Architecture

Recommended flow:

~~~text
JFR repository / RecordingStream
          |
          v
onEvent callback (read fields -> validate -> copy compact data)
          |
          +-- invalid schema? -> increment counter, aggregated alert
          |
          v
non-blocking queue.offer(snapshot)   [bounded N]
          |                |
          | success        +-- full -> policy: drop/coalesce/sample/durable fallback
          v
separate worker/exporter
          |
          +-- aggregate / batch / bounded timeout / bounded retry
          v
metrics / storage / external sink

Separate metrics: received, accepted, dropped, invalid,
queue depth, processing lag, export errors, end-to-end latency.
~~~

Distinguish **three buffering layers**:

- **In-memory buffers and disk repository managed by JFR:** `RecordingStream.setMaxAge(Duration)` and `setMaxSize(long)` cap retained recording history; they **do not bound** the size of application-created queues.
- **In-JVM consumer queue:** e.g., an `ArrayBlockingQueue<Snapshot>` of size 128 or 1,024. The application itself owns capacity, overflow policy, and worker threads.
- **Exporter or destination buffers/batches:** HTTP clients, message brokers, databases, telemetry agents, etc., each have their own timeouts, retries, and latencies. Having a bounded queue in layer two **does not guarantee** layer three is bounded.

Never use an unbounded `ArrayList<RecordedEvent>` to "process later". In a long-running diagnostic agent, that is a textbook way to build a secondary memory leak right inside your observability layer.

## 3. Golden Rule for `onEvent`: Copy Fast, Return Fast

A well-behaved callback does the bare minimum:

1. Verify the expected event type.
2. Check that required fields exist and have valid types.
3. Copy only the **essential** fields into a small, immutable snapshot; cap `String`/stack/JSON lengths and avoid retaining sensitive payloads.
4. Call `queue.offer(snapshot)` (non-blocking). Increment `accepted` on success, or apply your chosen overload policy when full.
5. Exit the callback.

Keep out of callbacks: `Thread.sleep`, synchronous HTTP calls, database queries, large file writes, long-held contended locks, multi-MB JSON serialization, O(n²) statistics, retry loops with backoff, or `queue.put` when the queue can fill up.

### 3.1. Risk of `RecordedEvent` reuse

`EventStream` explicitly states that **the same `RecordedEvent` instance may be reused** across events; keeping a reference after the callback returns is unsafe when reuse is active. **Wrong** example:

~~~java
// Illustrative anti-pattern, not a standalone program:
stream.onEvent("lab.OrderEvent", event -> queue.offer(event));
~~~

The worker may read an object already overwritten by the stream, causing values to mutate or mix across events. Two solutions:

- **Preferred:** inside the callback, build an immutable snapshot holding only bounded scalars/`String`s/`Instant`s and enqueue the snapshot. You can then keep `stream.setReuse(true)` to minimize stream allocations.
- **When retaining the full event is truly necessary:** `stream.setReuse(false)` allocates a fresh event object each time. This raises allocation overhead and **still does not solve unbounded queues**. Also account for the retained object graph of nested fields if kept long-term.

Do not assume JFR events hit callbacks instantaneously in strict real time. Events arrive in **batches** with flush/chunk latency and ordering limits. When `setOrdered(false)` is used to skip sorting, downstream logic must handle out-of-order arrivals via timestamps or IDs.

## 4. Policies When Producers Outpace Consumers

Any bounded system must accept **one of three trade-offs**: shed load, drop some events, or spool temporarily to bounded durable storage. You cannot promise "zero loss, zero blocking, and zero extra storage" when sustained event rates exceed export capacity.

| Policy | Mechanism | Best suited for | Trade-off |
| --- | --- | --- | --- |
| **Drop newest** | Discard new snapshot if `offer` returns `false` | Telemetry sampling, CPU/memory metrics tolerant of sample loss | Loses visibility during load spikes; must count drops |
| **Drop oldest** | Evict oldest entry and retry inserting newest | Dashboards prioritizing freshest state | Breaks historical continuity; races across multiple workers require synchronization |
| **Coalesce/aggregate** | Merge by (event type, class, time window) | Counters, histograms, throughput | Loses individual events and per-event stack traces |
| **Adaptive sampling** | Lower frequency or pick a subset | Very high event volumes | Introduces sampling error; dropped events cannot be recovered |
| **Durable spool/replay** | Write to quota-bounded disk files/chunks/queues for worker replay | High-preservation diagnostics | Costs I/O and disk pressure; requires replay/dedup and corruption handling |
| **Block producer** | `put` or infinite retry in callback | Generally **unsuitable** for live JFR consumers | Stalls stream, spikes lag/repository pressure, may impact workload |

**Choose based on event criticality.** For sampled metrics, observable dropping is standard. For mandatory zero-loss auditing or transactions, **JFR streaming should not be the sole storage channel**; critical business events belong on durable systems with acknowledgements. JFR is a diagnostic channel without an exactly-once delivery contract.

### 4.1. Estimating queue and memory budgets

Suppose peak arrival is 10,000 events/s while the worker drains 8,000 events/s for 5 seconds. The backlog grows by roughly (10,000 − 8,000) × 5 = **10,000 snapshots**. A 1,000-slot queue fills up quickly. If each snapshot occupies ~200 bytes on average (including object headers, references, and data), 10,000 snapshots take ~2 MiB; however, 200 bytes is merely an **assumption** and balloons if copying stack traces or long strings.

Therefore:

- Measure **actual snapshot memory footprint** and cap strings/payloads/stacks.
- Fix queue capacities, worker counts, batch sizes, timeouts, and retry budgets.
- Monitor `queue.size()/capacity`, `dropped / received`, and capture-to-processing lag.
- Load-test above downstream capacity, simulating exporter timeouts, full disks, and mid-flight shutdowns.
- Prioritize **reducing data at the source** (enable only useful events, raise thresholds, disable unneeded stack traces, use event filters) before blindly inflating queues.

## 5. Java 17+ Example: RecordingStream + Bounded Queue + Dedicated Worker

This is a **complete program** running in one JVM: it emits custom `lab.OrderEvent` instances, registers a callback, copies **scalar values** into a bounded `ArrayBlockingQueue`, and lets a deliberately slow worker drain them. The callback **never waits** for the worker; when the queue is full, it increments `dropped`. A `.jfr` file is also dumped for the schema exercise later.

Save as **`BoundedJfrConsumerDemo.java`**:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.LongAdder;
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.consumer.RecordingStream;

public final class BoundedJfrConsumerDemo {
    @Name("lab.OrderEvent")
    public static final class OrderEvent extends Event {
        public long orderId;
        public long elapsedMillis;
        public String source;
    }

    private record Snapshot(long id, long durationMillis,
                            String source, Instant timestamp) { }

    public static void main(String[] args) throws Exception {
        var queue = new ArrayBlockingQueue<Snapshot>(128);
        var workerRunning = new AtomicBoolean(true);
        var accepted = new LongAdder();
        var dropped = new LongAdder();
        var invalid = new LongAdder();
        var processed = new LongAdder();
        var streamErrors = new LongAdder();
        var flushes = new LongAdder();

        Thread worker = new Thread(() -> {
            try {
                while (workerRunning.get() || !queue.isEmpty()) {
                    Snapshot value = queue.poll(100, TimeUnit.MILLISECONDS);
                    if (value != null) {
                        // Simulated slow downstream: placed OUTSIDE onEvent.
                        Thread.sleep(2);
                        processed.increment();
                    }
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "jfr-exporter");
        worker.start();

        Path recording = Files.createTempFile("bounded-jfr-", ".jfr");
        try (RecordingStream stream = new RecordingStream()) {
            stream.enable(OrderEvent.class)
                  .withoutThreshold()
                  .withoutStackTrace();
            stream.setMaxAge(Duration.ofMinutes(2));
            stream.setMaxSize(32L * 1024 * 1024);
            stream.setOrdered(false); // Consumer does not require strict ordering.
            stream.setReuse(true);    // DO NOT retain RecordedEvent after callback.
            stream.onFlush(flushes::increment);
            stream.onError(error -> streamErrors.increment());

            stream.onEvent("lab.OrderEvent", event -> {
                if (!event.hasField("orderId")
                        || !event.hasField("elapsedMillis")) {
                    invalid.increment();
                    return;
                }

                Object rawId = event.getValue("orderId");
                Object rawDuration = event.getValue("elapsedMillis");
                if (!(rawId instanceof Number id)
                        || !(rawDuration instanceof Number duration)) {
                    invalid.increment();
                    return;
                }

                String source = "unknown";
                if (event.hasField("source")) {
                    Object raw = event.getValue("source");
                    if (raw instanceof String s) {
                        source = s.substring(0, Math.min(32, s.length()));
                    }
                }

                Snapshot copy = new Snapshot(id.longValue(),
                        duration.longValue(), source, event.getStartTime());
                if (queue.offer(copy)) {
                    accepted.increment();
                } else {
                    dropped.increment();
                }
            });

            stream.startAsync();
            for (long i = 1; i <= 4000; i++) {
                OrderEvent event = new OrderEvent();
                event.orderId = i;
                event.elapsedMillis = i % 20;
                event.source = "training";
                event.commit();
            }

            // Give the stream a chance to flush; this is NOT a guarantee of all 4000 callbacks.
            Thread.sleep(2500L);
            stream.dump(recording);
            stream.close();
            stream.awaitTermination(Duration.ofSeconds(3));
        } finally {
            workerRunning.set(false);
            worker.join();
        }

        System.out.println("Produced=4000");
        System.out.println("Accepted=" + accepted.sum());
        System.out.println("Dropped=" + dropped.sum());
        System.out.println("Invalid=" + invalid.sum());
        System.out.println("Processed=" + processed.sum());
        System.out.println("Stream errors=" + streamErrors.sum());
        System.out.println("Flushes=" + flushes.sum());
        System.out.println("JFR file=" + recording.toAbsolutePath());
    }
}
~~~

Compile and run with JDK 17+ supporting JFR:

~~~bash
javac BoundedJfrConsumerDemo.java
java BoundedJfrConsumerDemo
~~~

The output has a **guaranteed structure** containing `Produced=4000`, `Accepted=...`, `Dropped=...`, `Invalid=...`, `Processed=...`, `Stream errors=...`, `Flushes=...`, and `JFR file=...`. The temporary output file path varies per run; the exact number of events received by the consumer is **non-deterministic** due to delivery, flushing, CPU, and OS scheduling. `Accepted + Dropped` counts **events actually delivered to the callback**, which **does not necessarily equal all 4,000 events `commit()`ted by the producer** in this short demo. `Processed` cannot exceed `Accepted` in normal execution.

To inspect the generated file, use the actual path printed after `JFR file=`:

~~~bash
jfr summary /path/to/bounded-jfr-example.jfr
jfr print --events lab.OrderEvent /path/to/bounded-jfr-example.jfr
~~~

`/path/to/bounded-jfr-example.jfr` is only a **placeholder**, not a filename created by the program. Do not run that command literally without substituting the printed path.

Highlights of this example:

- `queue.offer` returns immediately and is bounded at 128 items; never call `put` inside a callback.
- `setReuse(true)` is safe because every needed value is copied into a `Snapshot` record; `RecordedEvent` is never placed in the queue.
- `setMaxAge` and `setMaxSize` govern **JFR recording** storage, not the queue. The 128-item cap is enforced separately by `ArrayBlockingQueue`.
- The worker simulates an exporter, keeping **I/O out of the callback**. Real exporters also need bounded batching, timeouts, and retries.
- The demo closes the stream after waiting briefly and lets the worker drain the queue. Calling `close()` does not guarantee every event in the JVM passed through the callback; environments requiring guaranteed retention need a dedicated durable/replay pipeline.

**Do not use this demo to extrapolate maximum real-world throughput:** event sizes, JIT warm-up, chunk flushing, and host speed heavily affect numbers. Its purpose is clarifying the callback → queue → worker boundary.

## 6. Backpressure Is a Whole-Pipeline Problem, Not Just One ArrayBlockingQueue

### 6.1. Defining explicit SLOs and overload behavior

For example, a telemetry-only consumer might set **illustrative** operational targets:

- `drop_ratio` near 0 under normal load, while alerting and shedding samples during downstream outages.
- Queue occupancy normally below alert thresholds, with exporter lag tracked via snapshot receipt vs. processing timestamps.
- Exporter calls with bounded timeouts and circuit breakers; retries use backoff and **never loop indefinitely**.
- Once normal load returns, backlog drains without unbounded memory growth.

These are not mandatory JFR SLOs. Service owners must define thresholds from investigative needs and host budgets. If a metric is not measured, never claim a consumer is "non-blocking" solely because the code calls `startAsync`.

### 6.2. Metrics to observe

| Metric | Meaning | Action when abnormal |
| --- | --- | --- |
| `events_received_total` | Events entering callbacks by type | Compare against traffic and recording config |
| `events_accepted_total` | Events successfully enqueued | Catch silent converter/validation drops |
| `events_dropped_total` | Events shed when queue is full per policy | Reduce event volume, fix exporter, tune capacity empirically |
| `events_invalid_total` | Events with missing/wrong-type fields | Investigate schema drift and producer versions |
| `queue_depth` / `queue_capacity` | Backlog and limit | Alert early; avoid sustained full queues |
| `export_errors_total` | Timeouts/failed batches in worker | Investigate sink, retries/circuit breakers |
| `processing_lag_seconds` | Time from event timestamp/callback to processing | Separate slow producer delivery from stalled exporter |
| `stream_error_total` / `stream_restarts` | Errors in callbacks/JFR stream | Protect consumer and restart with backoff |
| `recording_disk_bytes` | Retained JFR data in repository | Review `setMaxAge`, `setMaxSize`, and disk headroom |

Note that **event timestamp** and **callback receipt time** differ. To measure callback → worker processing lag, capture `System.nanoTime()` when constructing the snapshot and subtract when the worker handles it (within the same process only); to measure end-to-end event → sink lag, use event timestamps while watching for cross-host clock skew.

### 6.3. Ordering and duplicate data

Per the `EventStream` API, events arrive in batches; order within a batch may be sorted by end time, yet **there is no absolute global order guarantee across batches**. `setOrdered(false)` can cut overhead, requiring downstream logic to handle timestamps and out-of-order arrivals when time ordering matters.

Never base irreversible business decisions on assuming JFR events are delivered **exactly once**, with sequential IDs, or free of duplicates across file replays. If an exporter needs idempotency, design deduplication keys with explicit scopes/TTLs and test replay behavior. Never treat `EventType.getId()` as a permanent cross-JVM or cross-file identifier.

## 7. How Do JFR Event Schemas Evolve?

In JFR, an **event type** has an identifier name (e.g., `lab.OrderEvent`), field metadata (names, types, annotations/units), and a JVM-internal numeric ID. `@Name` on a custom `Event` sets the machine-readable name; `@Label` is for display. **Consumers should match on the agreed event type name** while checking field shapes/semantics, rather than relying on display labels or numeric IDs across runtimes.

| Producer change | What an old consumer might hit | Compatibility strategy |
| --- | --- | --- |
| Adding optional field `region` | Old consumer still reads old fields | Ignore unknown fields; new consumer applies fallback |
| Removing field `elapsedMillis` | `getLong("elapsedMillis")` throws due to missing field | Check `hasField` first; mark invalid and emit metric |
| Changing type `long` to `String` | Typed getter throws `IllegalArgumentException` | Inspect metadata/`getValue` + `instanceof`; do not parse blindly |
| Changing unit from millis to nanos | Field stays numeric yet means something else; 10⁶× error risk | Introduce a new field name (e.g., `durationNanos`) and convert carefully |
| Changing field semantics while keeping name | Logic bug **cannot be detected automatically** | Create a new event version or explicit schema version contract |
| Renaming the event type itself | Callbacks subscribed to old name stop receiving events | Dual-publish transition or subscribe to both old and new names |
| Class unload/reload changing metadata across chunks | Same name/ID in a different context has a different shape | Process metadata per session/chunk; never cache schemas forever by name alone |

Two versioning strategies:

**Backward-compatible evolution:** keep `@Name("lab.OrderEvent")` and preserve meanings/types of existing fields; add new fields that may be absent in older files. Newer consumers check `hasField("region") ? ... : "unknown"`. Within a single-session stream, live metadata remains the source of truth per event rather than static docs.

**Breaking contract change:** introduce `@Name("lab.OrderEventV2")` with clear field names, types, and units (`durationNanos`) instead of silently altering what `elapsedMillis` means. During migration, consumers can listen to both names and normalize into one internal record, retiring v1 once no legacy files or producers remain.

### 7.1. Validating fields properly

`RecordedEvent` provides `hasField(String)` and `getValue(String)`; `EventType` provides `getField(String)` and `getFields()` for inspecting metadata. `getValue` returns an object (boxed primitive or specialized JFR object); typed getters like `getLong`, `getString`, and `getDuration` are safe **only when the field exists with the expected type/annotations**. `hasField` guards against missing fields, not type mismatches.

~~~java
// Standalone illustration, not a runnable program:
Object raw = event.hasField("durationNanos")
        ? event.getValue("durationNanos")
        : null;
if (raw instanceof Number number) {
    long nanos = number.longValue();
    // Convert to milliseconds only when nanos >= 0 and semantics match.
}
~~~

Treat event schemas as **versioned data contracts**:

- Event names, field names, types, units, and business semantics must be explicitly specified.
- New fields **may be absent** in older files; a `null` value also differs from a nonexistent field.
- When data is required, never silently substitute `0` on a missing field—that fabricates misleading reports. Increment `invalid_schema`, log the type/version, and follow policy.
- Reading `.jfr` files across different JDK versions or vendors may reveal varying system events and fields; never hardcode built-in JFR field lists as an immutable forever contract.
- Do not treat adding an annotation/label as a breaking semantic change; keep matching contract tests.

## 8. `onMetadata`: Detecting Event Type Changes During Consumption

`EventStream.onMetadata(Consumer<MetadataEvent>)` has existed since JDK 16. Register it **before `start()`/`startAsync()`**. A metadata event exposes:

- `getEventTypes()`: list of event types currently in use.
- `getAddedEventTypes()`: types introduced since the previous metadata event (often all known types on the first event).
- `getRemovedEventTypes()`: types removed since the previous metadata event.
- `getConfigurations()`: associated metadata configurations.

Each `EventType` provides `getName()`, `getId()`, and `getFields()`; each `ValueDescriptor` provides `getName()` and `getTypeName()`. You can build a **schema signature** by normalizing `(field name, type, relevant unit/annotation)` per event name and source version. When metadata changes, emit one aggregated event/alert rather than logging metadata for every event.

**Do not substitute `onMetadata` for per-event checks:** metadata can shift across files/chunks, and a present field can still be `null` or typed unexpectedly. Consumers must still validate at read time. For uninterested event types, subscribe by explicit event name rather than parsing every event in the stream.

Avoid heavy I/O inside `onMetadata`. The example below prints compact schema summaries for learning; in production, push schema signatures through a dedicated queue or batched logger.

## 9. Java 17+ Example Reading Old/New Files and Normalizing Schemas

This second example is a **standalone** program. It opens the `.jfr` file generated in section 5 or any file sharing the contract. The consumer supports:

- **v1:** `lab.OrderEvent` with `orderId` and `elapsedMillis`.
- **v2:** `lab.OrderEventV2` with `orderId` and `durationNanos`; optional `source`/`outcome`.

If a duration field is missing, mistyped, or negative, the program increments `invalid` rather than **blindly substituting `duration=0`**. Valid values are normalized to milliseconds. This demonstrates conversion for a known contract, not a universal decoder for arbitrary JFR events.

Create **`JfrSchemaCompatibleReader.java`**:

~~~java
import java.nio.file.Path;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.LongAdder;
import java.util.stream.Collectors;
import jdk.jfr.consumer.EventStream;
import jdk.jfr.consumer.RecordedEvent;

public final class JfrSchemaCompatibleReader {
    private static final Set<String> SUPPORTED =
            Set.of("lab.OrderEvent", "lab.OrderEventV2");
    private static final LongAdder valid = new LongAdder();
    private static final LongAdder invalid = new LongAdder();
    private static final LongAdder totalMillis = new LongAdder();
    private static final LongAdder streamErrors = new LongAdder();

    private static Long number(RecordedEvent event, String field) {
        if (!event.hasField(field)) {
            return null;
        }
        Object raw = event.getValue(field);
        return raw instanceof Number n ? n.longValue() : null;
    }

    private static void consume(RecordedEvent event) {
        Long id = number(event, "orderId");
        Long millis;
        String typeName = event.getEventType().getName();

        if ("lab.OrderEventV2".equals(typeName)) {
            Long nanos = number(event, "durationNanos");
            millis = nanos == null || nanos < 0
                    ? null : TimeUnit.NANOSECONDS.toMillis(nanos);
        } else {
            millis = number(event, "elapsedMillis");
        }

        if (id == null || id < 0 || millis == null || millis < 0) {
            invalid.increment();
            return;
        }

        valid.increment();
        totalMillis.add(millis);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java JfrSchemaCompatibleReader <file.jfr>");
            return;
        }

        try (EventStream stream = EventStream.openFile(Path.of(args[0]))) {
            stream.setOrdered(false);

            stream.onMetadata(metadata -> metadata.getAddedEventTypes()
                .stream()
                .filter(type -> SUPPORTED.contains(type.getName()))
                .forEach(type -> {
                    String fields = type.getFields().stream()
                            .map(f -> f.getName() + ":" + f.getTypeName())
                            .collect(Collectors.joining(", "));
                    System.out.println("Schema " + type.getName()
                            + " {" + fields + "}");
                }));

            stream.onEvent("lab.OrderEvent",
                    JfrSchemaCompatibleReader::consume);
            stream.onEvent("lab.OrderEventV2",
                    JfrSchemaCompatibleReader::consume);
            stream.onError(error -> streamErrors.increment());

            // Bounded file: start() reads synchronously to end of file.
            stream.start();
        }

        System.out.println("Valid=" + valid.sum());
        System.out.println("Invalid=" + invalid.sum());
        System.out.println("Total duration (ms)=" + totalMillis.sum());
        System.out.println("Stream errors=" + streamErrors.sum());
    }
}
~~~

Compile and run:

~~~bash
javac JfrSchemaCompatibleReader.java
java JfrSchemaCompatibleReader /path/to/actual-recording.jfr
~~~

Replace `/path/to/actual-recording.jfr` with **the path printed by `BoundedJfrConsumerDemo`** or a compatible file. Output prints discovered schemas and four counters; **counts and total duration depend on file contents**. For the v1 file created in section 5, only `lab.OrderEvent` will appear; `lab.OrderEventV2` need not exist. If a file lacks both event types, `Valid=0` is a valid filtered result, **not proof the program failed to read the file**.

### 9.1. Example v2 producer (code snippet, not standalone)

~~~java
@jdk.jfr.Name("lab.OrderEventV2")
public static final class OrderEventV2 extends jdk.jfr.Event {
    public long orderId;
    public long durationNanos;   // new unit stated clearly in the name
    public String source;         // may be absent in older recordings
    public String outcome;        // new optional field
}
~~~

This is a **declaration snippet** for upgrading a producer, not a complete standalone Java file. In production, add `@Label`, `@Description`, and `@Timespan` annotations matching semantics, along with clear schema contract docs. When renaming types between v1 and v2, support both during transition so older files remain readable.

### 9.2. Compatibility policies should be codified as tests

| Test | Purpose |
| --- | --- |
| Read v1 fixture file with new consumer | Absent new fields do not crash reader |
| Read v2 fixture file with new consumer | Converts duration ns → ms; handles optional fields |
| Duration field missing/null/wrong type | `invalid` counter increments; no fake `0` metrics created |
| Unknown event type | Intentionally ignored without breaking the stream |
| Multi-JDK/vendor/chunk schemas | Does not lock onto numeric IDs or a single metadata snapshot |
| Corrupt file or missing read permission | Error reported; no fake "0 events" report |
| Reading large files | Consumer memory remains stable; no loading all events into a list |

To block breaking changes early in the pipeline, build CI contract tests against real `.jfr` fixture files, comparing metadata signatures and verifying required fields. **Golden files** must be generated/verified on the JDK versions you support.

## 10. Operations: Errors, Shutdown, and Recovery

### Callback errors must not become stalls

`onError` receives exceptions from stream/action processing. If no handler is registered, implementations may print a default stack trace. Inside the handler, **only increment a counter or emit a lightweight signal**—avoid throwing further exceptions or making synchronous remote logging calls. Field-parsing errors can be caught locally and classified as `invalid_schema` instead of crashing the stream, yet never swallow critical errors and report success.

`onClose` runs when the stream closes. Do not assume `close()` means "all callbacks and exporters have finished": `EventStream.close()` docs explicitly note it does not guarantee all registered actions completed before returning. With `RecordingStream` on JDK 20+, `stop()` waits for remaining recorded events to be consumed; however, **never call `stop()` from inside a callback**, as that can wait forever. In the Java 17+ example here, call `close()` followed by `awaitTermination(timeout)` per contract, then let the dedicated worker drain the queue within a time budget.

### Safe shutdown

Workflow in a real service:

1. Stop accepting new requests or transition the instance to draining state if needed.
2. Stop the JFR stream from an **administrative thread** outside callbacks with an appropriate timeout.
3. Drain remaining queue items within the shutdown budget. If the budget expires, record dropped item counts and apply policy.
4. Flush unsent batches if the exporter supports it, close connections and thread pools, and release stream resources.
5. If forensic data is needed, dump/retain `.jfr` files independently of the telemetry pipeline; do not confuse file retention with exported queues.
6. On restart, do not assume the stream resumes from a previous offset or replays missed events. Replay/deduplication mechanisms must be built separately if required.

With `EventStream.openFile`, file processing has a defined end and can be reopened for replay (watch for duplicates). With a live `RecordingStream`, data comes from batches of the active recording and its retention history; it is **not** a durable queue with consumer offsets or acknowledgements.

### Handling downstream outages

- When the sink slows down, the worker enforces timeouts/circuit breakers; callbacks keep doing fast `offer` or policy-based drops.
- When queues stay full, raise alerts and reduce event volume at the source via settings/thresholds or lower sampling; never "fix" it with infinite retries inside callbacks.
- When the JFR disk repository hits limits, `setMaxAge`/`setMaxSize` can evict old chunks. This is expected retention behavior; events evicted from the repository **do not come back automatically**.
- If multiple consumers read the same JVM, measure combined overhead and duplicate processing. Never spin up a detailed recording per request just because the API allows it.

## 11. Common Pitfalls and Diagnostic Signs

| Symptom | Possible cause | Remediation |
| --- | --- | --- |
| `startAsync()` used, yet JVM CPU/lag still rises | Callback does too much work or too many events enabled | Move heavy work to worker, trim event types/settings, measure callback duration |
| Queue grows continuously | Exporter throughput lower than event arrival rate | Bounded batching/scaling, lower upstream event volume, drop/coalesce policy |
| OOM in telemetry agent | Unbounded queue/list/pending retries, or retaining large stacks/payloads | Bounded queue, max payload, max attempts, measure retained heap |
| Processed count differs from `commit()` count | JFR batching/flush, thresholds, disabled events, queue drops, early shutdown | Measure each stage producer→stream→queue→worker; do not judge from one counter |
| Worker sees fields from a later event | Passed `RecordedEvent` across threads with reuse enabled | Copy scalars in callback, or evaluate disabling reuse with overhead testing |
| `getLong("elapsedMillis")` throws | Schema missing field or type changed | Use `hasField` + typed check; version schemas and count invalids |
| Duration jumps a million-fold after deploy | Field unit switched millis ↔ nanos without changing contract | Version/rename field, convert units explicitly |
| `onMetadata` behaves unexpectedly | Registered after start, file lacks new metadata, or JDK differs | Register before start; inspect `getEventTypes` and file metadata |
| Event name stops triggering callbacks | Producer changed `@Name` or disabled event | Dual-support v1/v2; verify names in `jfr metadata` |
| Event timestamps appear to go "backward" | Batch delivery or `setOrdered(false)` | Rely on timestamps/IDs and handle late events |
| Consumer restart misses a gap of events | Live stream lacks durable offsets/ACKs | Use files/archives and replay design when genuinely needed |
| Logs contain sensitive payloads | Snapshot kept full strings/stacks/error context | Allowlist fields, cap sizes, redact, enforce access control |
| Reading untrusted `.jfr` files | Corrupt file or parser fed unvalidated input | Accept only trusted files, sandbox resources, keep JDK updated |

## 12. Design Checklist and Three Scenario Exercises

**Pre-production consumer checklist:**

- Event types are **allowlisted**; sampling, thresholds, stack traces, and retention are budgeted.
- Every callback has **bounded execution time**, with no long network/DB/lock waits.
- Snapshots are small and immutable, holding neither `RecordedEvent` nor heavy object graphs.
- Queues are bounded with an **explicit overflow policy**, and dropped/invalid counters are exported as metrics.
- Workers/exporters enforce timeouts, bounded retries/backoff, bounded batches, and clean shutdown.
- Event schema status is tracked via metadata and contract tests; old/new field readers verify types and units.
- Tested against v1/v2 files, missing fields, sink outages, queue overflows, large files, and JVM shutdowns.
- Never claim exactly-once or lossless guarantees without a durable ACK/replay mechanism.

**Scenario A:** A callback makes HTTP calls and occasionally stalls for 8 seconds even though `RecordingStream.startAsync()` was called. Why does lag spike? → Callbacks still run on the stream's single event-processing thread; switch to `offer(snapshot)` plus a worker with timeouts/circuit breakers, and accept sample loss or bounded spooling when downstream is unavailable.

**Scenario B:** Older files have `elapsedMillis=15`; a new build stores nanoseconds under the same `elapsedMillis` name. The new consumer reads `15` as 15 ms without throwing. → This is a **silent semantic break** that `hasField` cannot catch. Rename to `durationNanos` or bump the event version, and validate schemas/units.

**Scenario C:** A 128-slot queue stays at 100%; someone bumps it to 2 million slots and the JVM runs out of heap 20 minutes later. → Enlarging the queue only postpones backlog buildup. Inspect arrival rates vs. exporter speed, cut events at the source, batch/scale within budget, or apply drop/coalesce/quota-bounded spooling.

**Learning takeaway:** A safe JFR consumer is a pipeline with **bounded resources and explicit data contracts**. `startAsync` provides the event-receiving thread; `queue.offer` and bounded workers absorb rate mismatches; `setReuse` forces clear object lifecycle ownership; and `onMetadata`, `hasField`, and versioned event types let JFR data evolve across app and JDK releases without corrupting reports.

## Official References

- Java SE 21 — `EventStream`: batch delivery, `onEvent`, `onMetadata`, `onFlush`, `setReuse`, `setOrdered`, `close`: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html
- Java SE 21 — `RecordingStream`: `startAsync`, `enable`, `setMaxAge`, `setMaxSize`, `dump`: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html
- Java SE 21 — `MetadataEvent`: `getAddedEventTypes`, `getRemovedEventTypes`: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/MetadataEvent.html
- Java SE 21 — `RecordedEvent` and `RecordedObject`: `hasField`, `getValue`, typed getters: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html
- Java SE 21 — `EventType`, `ValueDescriptor`: schema metadata: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/EventType.html
- Java SE 17 — `RecordingStream`: APIs applicable to Java 17+ examples: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html
- Java SE 21 — `EventSettings`: event filters, thresholds, and stackTrace: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/EventSettings.html
