# 18.5 Capturing Receive, Start, End, and Result via Logs or Custom Events

## 1. Goal: reconstruct an I/O journey instead of only knowing "the request was slow"

In a Java application with HTTP handlers, message consumers, worker pools, file writes, database calls, or downstream HTTP calls, an operation can experience both **waiting before processing** and **time spent executing work**. Logging only "started processing" and "finished processing" misses queuing/dispatch; logging only one total duration hides where the slowdown occurred.

To query and diagnose **I/O and latency**, capture four consistent components per operation/attempt:

1. **RECEIVED:** when the application accepts/receives work at the defined boundary.
2. **STARTED:** when a worker actually starts executing that work.
3. **ENDED:** when the operation is considered complete at the measurement boundary, including error paths.
4. **RESULT:** success/failure/timeout/cancelled/rejected status and safe observable error metadata.

You can record the three timestamps plus the result in **structured logs**, a **custom JFR event**, or both. Choosing between them depends on online query needs, overhead, detail level, retention, and cross-system correlation requirements.

After this lesson, you will be able to design schemas, compute queue-to-start/work/end-to-end latencies, attach correlation IDs, measure accurately with `System.nanoTime()`, record all outcome branches in `try/finally`, create a Java 17+ custom JFR event, and read events back to verify evidence.

**The first thing to define:** Is "received" when the service receives the request/message or when the job is enqueued? Is "ended" when the I/O callback finishes or when the response is flushed? If different services or code paths use different boundaries, comparing metrics can be meaningless even when timestamps are valid.

## 2. Four milestones and measurement boundaries

```text
Client / upstream
       |
       v
  [RECEIVED] t_recv     Service received/accepted the work
       |
       | waiting for dispatch / queue / permit / worker
       |
  [STARTED] t_start     Worker begins the work to measure
       |
       | executing I/O, compute, internal retries within scope
       |
  [ENDED]   t_end       Operation outcome has been determined
       |
       +---- RESULT     SUCCESS / ERROR / TIMEOUT / CANCELLED / REJECTED ...
       |
       v
     response / ack / downstream outcome (depending on boundary)
```

### 2.1. RECEIVED: at which boundary?

Examples:

- **HTTP server:** when the entry handler or middleware receives the request after container dispatch; this is not when the first packet hits the NIC.
- **Message consumer:** when the message-delivery callback runs, or when the system enqueues a job to process it.
- **Worker queue:** when the job is accepted at the producer and about to be submitted, possibly before entering the queue itself.
- **File I/O:** when the application accepts the read/write request, not necessarily when the syscall begins.

Attach `requestId` / `operationId` and capture the timestamp **immediately upon receipt**. For retried jobs, add `attempt` or `attemptId` so two runs sharing a business ID are not stitched together by mistake.

If the goal is to measure **pure queue wait time**, also capture `enqueuedAt` and `dequeuedAt`. In this lesson, `t_start - t_recv` is called **wait-to-start** because it may include authentication, context setup, dispatch, and queue waiting; it must not be assumed to equal exact "queue time."

### 2.2. STARTED: true start of processing

`t_start` must be taken when the work **is actually executed by a worker**, not when calling `executor.submit(...)`. Those two moments diverge under heavy load. With async APIs, creating a `CompletableFuture` also does not guarantee I/O has started.

If a semaphore or rate limiter is used, define explicitly whether STARTED comes before or after acquire; if before, permit wait falls into work duration, whereas if after, it falls into wait-to-start. Either is fine as long as it is documented and consistent.

### 2.3. ENDED: exact definition of completion

With synchronous I/O, ENDED can be when the read/write method returns or throws. With asynchronous I/O, ENDED is when the callback/completion signals that **the entire operation you intended to measure** is finished, not when registering a callback or returning an incomplete future.

If "writing a file" only writes into the OS page cache, method completion **does not mean data was `fsync`ed to durable storage**. If durability is your target, place the milestone on the API guaranteeing durability. Likewise, a serialized response is not necessarily fully transmitted to the client yet.

### 2.4. RESULT: status paired with ENDED

`result` should use a clear vocabulary, for example:

| Result | Meaning | Useful additional fields |
| --- | --- | --- |
| `SUCCESS` | Work succeeded per contract | status/code, bytes/rows count, downstream status |
| `ERROR` | Work ended in failure | normalized exception type, error code |
| `TIMEOUT` | Exceeded configured deadline | deadline, timeout type, caller/downstream |
| `CANCELLED` | Deliberately cancelled or interrupted | reason, cancelling party |
| `REJECTED` | Rejected before starting | queue full, overload, rate limit |
| `UNKNOWN` | Final outcome undetermined | Do not silently convert to SUCCESS/ERROR |

Avoid logging full exception stack traces on every event at very high rates; store normalized `errorType` and error codes, keeping detailed stacks where appropriate. Never write tokens, passwords, request bodies, or PII into logs or JFR.

Normally, **ENDED + RESULT live in one structured-log record or one custom event committed after completion**. A separate fourth log line named RESULT is unnecessary if outcome is attached to ENDED. However, ensure result holds the final value rather than a leftover `PENDING`.

## 3. Three intervals to compute

When all three timestamps belong to **the same process/JVM** and come from a monotonic clock:

- `waitToStart = t_start - t_recv`
- `work = t_end - t_start`
- `endToEnd = t_end - t_recv`
- Invariant check: **`endToEnd = waitToStart + work`** when timestamps share the same clock/unit and are handled cleanly.

Hypothetical example, with all timestamps in **milliseconds on a shared monotonic clock**, solely for hand calculation:

| Operation | `t_recv` | `t_start` | `t_end` | Wait-to-start | Work | End-to-end | Result |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `r-101` | 1.000 | 1.012 | 1.060 | 12 ms | 48 ms | **60 ms** | SUCCESS |
| `r-102` | 2.000 | 2.080 | 2.110 | 80 ms | 30 ms | **110 ms** | ERROR |

Interpretation:

- `r-101` took 60 ms total, mostly in execution (48 ms).
- `r-102` took 110 ms total even though work was only 30 ms; most of it occurred before the worker started (80 ms).
- An `ERROR` result can return very quickly; never equate "error" with "slow" or "success" with "fast."
- Two requests can overlap in time, so you cannot add their end-to-end durations to infer wall-clock time of the system.

When retries occur, distinguish **single-attempt latency** from **logical request latency**. Three attempts of 30 ms, 40 ms, and 50 ms with 100 ms backoff between them do not yield 120 ms end-to-end; retry wait belongs to the request journey even though it sits outside each attempt's work.

## 4. Choosing the right clock: timestamps to join logs, nanoTime to measure duration

### 4.1. Wall clock: `Instant.now()` / `System.currentTimeMillis()`

The wall clock ties to UTC/Unix epoch. It is used for:

- placing an event on a timeline to correlate with HTTP access logs, traces, GC/JFR;
- finding when an incident occurred;
- presenting times to operators.

For example, `2026-01-01T10:00:00.000Z` is a UTC instant; it can be displayed in `Asia/Ho_Chi_Minh` when needed. However, wall clocks can jump due to NTP, virtualization, or system clock changes, and `currentTimeMillis()` has millisecond resolution. **Never rely solely on the difference of two wall-clock timestamps to measure short latencies.**

### 4.2. Monotonic elapsed clock: `System.nanoTime()`

`nanoTime()` returns monotonic clock ticks meant for **measuring elapsed time**, not epoch time. Absolute values have no calendar meaning and may be negative, yet differences between two calls within **the same JVM/process** meaningfully measure duration:

```java
// Illustrative fragment, not a standalone program.
long receivedNano = System.nanoTime();
// ... once the worker actually starts:
long startedNano = System.nanoTime();
// ... when the operation finishes:
long endedNano = System.nanoTime();

long waitNanos = startedNano - receivedNano;
long workNanos = endedNano - startedNano;
long totalNanos = endedNano - receivedNano;

double totalMillis = totalNanos / 1_000_000.0;
```

This avoids wall-clock adjustments producing negative durations or sudden jumps. Nanosecond units **do not mean hardware has one-nanosecond accuracy**. Never compare raw `nanoTime` values across **two different JVMs or two different machines**; subtract only timestamps from the same process/clock domain.

When a request travels from a gateway to another service, propagate `traceId`/`spanId`, record clock-synchronized UTC timestamps, and use distributed tracing to connect spans. Inside each service, measure durations with its local monotonic clock. Never subtract service B's `nanoTime` from service A's `nanoTime`.

### 4.3. Recording both clocks without confusion

Each milestone can capture a pair:

```text
receivedAtEpochMs     = System.currentTimeMillis()
receivedAtMonotonicNs  = System.nanoTime()     (JVM-internal use only)
```

The two calls do not execute at the exact same instant; a tiny offset is normal. Keep capture ordering consistent and do not assume wall-timestamp deltas **must exactly equal** `nanoTime` deltas. Log UTC time and computed durations, but there is rarely a reason to persist raw `nanoTime` values long-term unless specifically needed.

**Units:** `1 ms = 1,000,000 ns`; use `long` for `...Nanos` and convert via `double millis = nanos / 1_000_000.0` for display. Never name a field `latencyMs` while storing nanoseconds in it.

## 5. Designing a minimal structured-log schema

An investigative log record should never be just `"started processing..."`. It needs stable, filterable fields:

| Field | Suggested type | Meaning |
| --- | --- | --- |
| `timestamp` or `epochMs` | ISO-8601 UTC / epoch milliseconds | Wall-clock time when logged |
| `phase` | Enum-like string | `RECEIVED`, `STARTED`, `ENDED` |
| `requestId` | String | Correlation ID for logical request |
| `attemptId` / `attemptNo` | String / integer | Distinguish retries |
| `operation` | String | Bounded-cardinality operation name, e.g., `file.write` |
| `result` | String | `PENDING`, `RUNNING`, `SUCCESS`, `ERROR`, ... |
| `errorType` / `errorCode` | Optional string | Error classification without secrets/sensitive messages |
| `waitToStartNanos` | long, on STARTED/ENDED | Time from receive to start |
| `workNanos` | long, on ENDED | Time from start to end |
| `totalNanos` | long, on ENDED | End-to-end across chosen boundary |
| `threadName` | Optional string | Useful when investigating executors |
| `traceId` / `spanId` | Optional string | Cross-service telemetry linking |
| `bytes` / `status` | Optional long / int | Meaningful I/O outcome |

**Illustrative** JSON log lines with hypothetical timestamps, not program stdout:

```json
{"timestamp":"2026-01-01T10:00:00.000Z","phase":"RECEIVED","requestId":"r-101","attemptNo":1,"operation":"file.write","result":"PENDING"}
{"timestamp":"2026-01-01T10:00:00.012Z","phase":"STARTED","requestId":"r-101","attemptNo":1,"operation":"file.write","result":"RUNNING","waitToStartNanos":12000000}
{"timestamp":"2026-01-01T10:00:00.060Z","phase":"ENDED","requestId":"r-101","attemptNo":1,"operation":"file.write","result":"SUCCESS","waitToStartNanos":12000000,"workNanos":48000000,"totalNanos":60000000,"bytes":4096}
```

Never rely solely on **thread name** to join the three lines: requests can hop threads, threads are reused, and identical names exist across JVMs. Use consistent correlation IDs, and with retries join on `requestId + attemptNo` or a unique `attemptId`.

### 5.1. Where to log so error branches are never missed

An ideal synchronous flow:

```text
ingress:
    capture received
    log RECEIVED
    enqueue/dispatch

worker:
    capture started
    log STARTED
    result = UNKNOWN
    try:
        perform I/O
        result = SUCCESS
    catch timeout:
        result = TIMEOUT
        rethrow/fail per contract
    catch other error:
        result = ERROR
        rethrow/fail per contract
    finally:
        capture ended
        compute wait/work/total
        log ENDED with final result
```

This is **pseudocode**, not runnable Java. For async flows, place ENDED inside the `CompletionStage` (or equivalent) completion callback, not immediately after returning the `Future`. Under cancel/timeout/race conditions, guarantee only one place commits the final outcome per attempt; an `AtomicBoolean.compareAndSet(false, true)` or state machine prevents emitting two ENDED records when timeout and completion race.

### 5.2. Thread pools, MDC, and context propagation

Logging frameworks like SLF4J/Logback can use **MDC** to attach `requestId` and `traceId` to every line. However, MDC typically relies on thread-bound context, so do not assume it propagates automatically from the ingress thread to an `ExecutorService` worker. Pass an explicit context object or configure deliberate context propagation.

Inside the worker, clear MDC in `try/finally` so a previous request's `requestId` does not leak into the next task. With virtual threads or reactive code, choose the corresponding propagation mechanism instead of relying on uncontrolled `ThreadLocal`s.

### 5.3. Prefer logs or custom JFR events?

| Approach | Strengths | Limitations |
| --- | --- | --- |
| Structured logs per phase | Easy to stream, index, alert, and search cross-service by trace ID | Many lines/events, heavy load on logging backends; clock skew |
| One custom JFR event on completion | Packs all milestones, durations, and outcome in one binary record; correlates neatly with JVM events | Requires active recording and dump/collection; not an automatic online query store |
| Logs + custom JFR combined | Logs for online monitoring; JFR for deep diagnostics and JVM correlation | Must keep schemas/IDs consistent; avoid duplicating sensitive payloads |

Using both is not mandatory. When a service already has tracing/metrics, appropriate log levels plus custom JFR events during deep investigations are often sufficient.

## 6. Custom JFR event: storing timeline and result in one record

A subclass of `jdk.jfr.Event` can carry application-defined fields. Use annotations:

- `@Name("demo.IoRequest")`: stable technical event name for filtering when reading files.
- `@Label`: human-friendly display name.
- `@Timestamp(Timestamp.MILLISECONDS_SINCE_EPOCH)`: clarifies that a `long` field holds epoch milliseconds.
- `@Timespan(Timespan.NANOSECONDS)`: clarifies that a `long` field holds nanosecond duration.
- `@StackTrace(false)`: disables default stack capture to reduce overhead when call sites are not needed; can be overridden per recording.

**Key choice about event duration:** In the example, `event.begin()` runs **when the worker starts** and `event.end()` right when work ends. Thus JFR's intrinsic duration mainly represents **worker processing time**, excluding wait-to-start. We store `receivedEpochMs`, `startedEpochMs`, `endedEpochMs`, `waitToStartNanos`, `workNanos`, and `totalNanos` so pre-start time is preserved.

If instead you want JFR duration to represent total end-to-end time, you must call `begin()` at receive and `end()` at completion with a thread-safe lifecycle design across thread handoffs and timeouts. Never change duration semantics without updating the event's name/metadata.

**Threshold trap:** JFR `threshold` filters by **the event's intrinsic duration**. If `begin/end` spans only work, setting `threshold=50 ms` can **drop a request that queued for 800 ms and ran in 2 ms**. In the example, we set `withThreshold(Duration.ZERO)` to retain both demo events; in production investigations, weigh sampling/overhead and set thresholds matching the intended boundary.

## 7. Java 17+ lab: recording logs and custom JFR, then reading them back

The example below creates two simulated requests. Both are received before submission to **a single worker**; the worker processes them sequentially to demonstrate waiting between RECEIVED and STARTED. One request ends in `SUCCESS`, and the other throws a simulated I/O error classified as `ERROR`.

The program **does not perform real file writes**: `Thread.sleep` simulates operation duration to focus on instrumentation technique. Actual timings and wait-to-start values vary per machine.

Create **`IoMilestonesDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.Path;
import java.time.Duration;
import java.util.concurrent.*;
import jdk.jfr.*;
import jdk.jfr.consumer.*;

public final class IoMilestonesDemo {
    @Name("demo.IoRequest")
    @Label("I/O request timeline")
    @StackTrace(false)
    public static class IoRequestEvent extends Event {
        public String requestId;
        public String operation;
        @Timestamp(Timestamp.MILLISECONDS_SINCE_EPOCH) public long receivedEpochMs;
        @Timestamp(Timestamp.MILLISECONDS_SINCE_EPOCH) public long startedEpochMs;
        @Timestamp(Timestamp.MILLISECONDS_SINCE_EPOCH) public long endedEpochMs;
        @Timespan(Timespan.NANOSECONDS) public long waitToStartNanos;
        @Timespan(Timespan.NANOSECONDS) public long workNanos;
        @Timespan(Timespan.NANOSECONDS) public long totalNanos;
        public String outcome;
        public String errorType;
    }
    private record Request(String id, String operation,
                           long receivedEpochMs, long receivedNano,
                           boolean fail) {}
    private static void log(String phase, String id, long epochMs, String result) {
        System.out.printf("phase=%s id=%s epochMs=%d result=%s%n",
                phase, id, epochMs, result);
    }
    private static Request receive(String id, boolean fail) {
        long receivedNano = System.nanoTime();
        long receivedEpochMs = System.currentTimeMillis();
        log("RECEIVED", id, receivedEpochMs, "PENDING");
        return new Request(id, "simulated-file-write",
                receivedEpochMs, receivedNano, fail);
    }
    private static void process(Request request) {
        long startedNano = System.nanoTime();
        long startedEpochMs = System.currentTimeMillis();
        log("STARTED", request.id(), startedEpochMs, "RUNNING");
        IoRequestEvent event = new IoRequestEvent();
        event.begin();
        String result = "SUCCESS";
        String errorType = "";
        try {
            Thread.sleep(25);
            if (request.fail()) throw new IOException("simulated write failure");
        } catch (IOException failure) {
            result = "ERROR";
            errorType = failure.getClass().getSimpleName();
        } catch (InterruptedException failure) {
            Thread.currentThread().interrupt();
            result = "CANCELLED";
            errorType = failure.getClass().getSimpleName();
        } finally {
            event.end();
            long endedNano = System.nanoTime();
            long endedEpochMs = System.currentTimeMillis();
            event.requestId = request.id();
            event.operation = request.operation();
            event.receivedEpochMs = request.receivedEpochMs();
            event.startedEpochMs = startedEpochMs;
            event.endedEpochMs = endedEpochMs;
            event.waitToStartNanos = startedNano - request.receivedNano();
            event.workNanos = endedNano - startedNano;
            event.totalNanos = endedNano - request.receivedNano();
            event.outcome = result;
            event.errorType = errorType;
            event.commit();
            log("ENDED", request.id(), endedEpochMs, result);
        }
    }
    private static void verify(Path path) throws IOException {
        int total = 0, success = 0, error = 0;
        try (RecordingFile file = new RecordingFile(path)) {
            while (file.hasMoreEvents()) {
                RecordedEvent event = file.readEvent();
                if (!"demo.IoRequest".equals(event.getEventType().getName())) continue;
                total++;
                String outcome = event.getString("outcome");
                if ("SUCCESS".equals(outcome)) success++;
                if ("ERROR".equals(outcome)) error++;
                long wait = event.getLong("waitToStartNanos");
                long work = event.getLong("workNanos");
                long endToEnd = event.getLong("totalNanos");
                if (endToEnd != wait + work || wait < 0 || work < 0) {
                    throw new IllegalStateException("Invalid timeline");
                }
            }
        }
        System.out.printf("verified=%d success=%d error=%d%n", total, success, error);
    }
    public static void main(String[] args) throws Exception {
        Path file = Path.of("io-milestones.jfr");
        try (Recording recording = new Recording()) {
            recording.enable(IoRequestEvent.class)
                    .withThreshold(Duration.ZERO).withoutStackTrace();
            recording.start();
            Request a = receive("req-001", false);
            Request b = receive("req-002", true);
            ExecutorService executor = Executors.newSingleThreadExecutor();
            try {
                Future<?> first = executor.submit(() -> process(a));
                Future<?> second = executor.submit(() -> process(b));
                first.get();
                second.get();
            } finally {
                executor.shutdown();
                if (!executor.awaitTermination(5, TimeUnit.SECONDS)) executor.shutdownNow();
            }
            recording.stop();
            recording.dump(file);
        }
        verify(file);
    }
}
```

Compile and run with JDK 17 or newer. `--release 17` checks Java 17 compatibility:

```bash
javac --release 17 IoMilestonesDemo.java
java IoMilestonesDemo
jfr summary io-milestones.jfr
jfr print --events demo.IoRequest io-milestones.jfr
```

`java IoMilestonesDemo` prints **six phase log lines with varying epoch milliseconds**, followed by a summary line. Example output from a JDK 24 run:

```text
phase=RECEIVED id=req-001 epochMs=1793271670097 result=PENDING
phase=RECEIVED id=req-002 epochMs=1793271670107 result=PENDING
phase=STARTED id=req-001 epochMs=1793271670110 result=RUNNING
phase=ENDED id=req-001 epochMs=1793271670164 result=SUCCESS
phase=STARTED id=req-002 epochMs=1793271670164 result=RUNNING
phase=ENDED id=req-002 epochMs=1793271670190 result=ERROR
verified=2 success=1 error=1
```

**Distinguish clearly:** The `epochMs` values above are from *one actual run*, not values you must reproduce. Timestamps and wait durations differ across machines and runs. When this program succeeds, **the final line is expected to remain stable**:

```text
verified=2 success=1 error=1
```

Both `RECEIVED` lines always precede the `STARTED` lines because the example receives both requests before submitting them. The single-thread executor handles `req-001` and `req-002` in order; the second request's work includes the simulated failure. `jfr summary` reported **2 instances** of `demo.IoRequest` in our test run; metadata/byte sizes and JFR tool output formatting may differ by JDK.

### 7.1. Why use a `Request` record?

`Request` stores `id`, `operation`, wall timestamp, and `receivedNano`. It travels with the task to the worker without relying on `ThreadLocal` or automatic MDC propagation across executors. This is the minimal pattern to **avoid dropping the receive boundary** when queuing is involved.

In real systems, context also carries `traceId`, `spanId`, `attemptNo`, deadlines, and non-sensitive metadata. Never pass arbitrary HTTP headers, bodies, or secrets into JFR payloads just for debugging.

### 7.2. Why record ENDED in `finally`?

An operation completes on both success and failure paths. Logging only after `try` means an exception skips ENDED, making it look like the request is still running. `finally` captures the end timestamp, computes all three durations, commits the custom JFR event, and logs ENDED alongside the outcome.

In the demo, `IOException` is **converted to `result=ERROR`** rather than rethrown so the test output remains deterministic. **Real applications should not swallow unexpected errors**: after recording telemetry, propagate the exception or fail the response/future per contract. Save the failure and rethrow after capturing milestones; avoid accidentally reporting SUCCESS to the caller.

For `InterruptedException`, the demo restores the interrupt flag and records `CANCELLED`. In applications with a cancellation protocol, propagate cancellation to the caller and ensure resource cleanup; not every interrupt corresponds to an HTTP client cancellation.

### 7.3. Total-time invariant

The demo captures `receivedNano` before submit, `startedNano` when the worker starts, and `endedNano` in `finally`. Thus:

```text
waitToStartNanos = startedNano - receivedNano
workNanos        = endedNano - startedNano
totalNanos       = endedNano - receivedNano

totalNanos == waitToStartNanos + workNanos
```

This is an algebraic invariant of **three timestamps on the same clock**. `verify` reads the `.jfr` file back and throws if duration fields are negative or fail to sum cleanly. This invariant catches unit mismatches or mixing two clock types.

Note: `workNanos` begins at `startedNano`, whereas JFR's intrinsic duration begins at `event.begin()` (after logging STARTED and allocating the event object). Hence the two durations are very close but **need not be identical**. Never treat that tiny offset as a JFR measurement bug.

### 7.4. Using `RecordingFile` to verify schema and outcomes

When reading a JFR file:

- `RecordingFile` opens the file; the `hasMoreEvents()` / `readEvent()` loop iterates over events in order.
- `getEventType().getName()` matches `demo.IoRequest` exactly so other JVM events do not mix in.
- `getString("outcome")` reads SUCCESS/ERROR; `getLong("waitToStartNanos")`, `getLong("workNanos")`, and `getLong("totalNanos")` read `long` values.
- `@Timestamp` and `@Timespan` are metadata telling tools the **units**. Where needed, you can use `RecordedEvent` APIs to convert annotated fields to `Instant`/`Duration`.
- `errorType` in the demo can be `"IOException"`; avoid logging raw exception messages that may contain secrets.
- `try-with-resources` closes the file reader and recording when finished.

**Do not confuse:** `io-milestones.jfr` contains the program's telemetry; it does not contain all OS I/O, and the demo performs no real I/O besides JFR writing its file. Log lines prove only the boundaries marked by the code itself.

## 8. Logs vs. JFR: choosing by environment

### 8.1. When to prefer logs

Structured logs fit well when you need to:

- look up a request by ID in a log aggregator;
- see which requests were rejected before a worker ever started;
- trigger alerts based on status or time-to-result;
- correlate across multiple services using `traceId` and UTC timestamps;
- investigate failures when no JFR recording exists.

Use a logging framework with a structured JSON encoder in production, avoiding `System.out.printf`. The demo uses stdout solely to run standalone without external dependencies—**not as a production logging recommendation**.

Logging RECEIVED/STARTED/ENDED for millions of requests per second produces huge data volume. Use metrics for distributions/traffic, intentionally sampled detailed logs, and JFR for diagnostic bursts. If sampling, keep sampling consistent per request: avoid logging RECEIVED and dropping ENDED via independent per-line sampling, which inflates unfinished rates.

### 8.2. When to prefer custom JFR events

Custom JFR events fit JVM diagnostics well:

- capturing durations with relatively low overhead when configured properly;
- correlating operations with GC, CPU, allocations, monitor contention, and file/socket events;
- enabling events only during targeted observation windows;
- integrating with JMC/JFR parsers to group events by duration/outcome.

JFR records only events that are **enabled and satisfy thresholds/sampling/capture settings**. Seeing 0 events never proves the app did not run the operation: the event may be disabled, filtered by threshold, outside the recording window, or not yet dumped.

For custom events with many fields, allocating/writing an object per operation still has cost. On hot paths, check `event.isEnabled()`/`event.shouldCommit()` to skip building expensive payloads, while ensuring **independent durations/metrics/logs still run** when JFR is off. Never store critical operation outcomes solely in JFR if always-on monitoring needs them.

### 8.3. Thresholds and outcomes: avoid dropping queue-delayed requests

To reiterate a common misjudgment:

```text
RECEIVED ---- waitToStart=800 ms ---- STARTED --- work=2 ms --- ENDED
```

If `Event.begin()` is at STARTED and `Event.end()` is at ENDED, a `threshold=50 ms` setting **will not record the event** (intrinsic duration is ~2 ms), even though end-to-end exceeded 800 ms. Having a `totalNanos` field in the schema does not make `threshold` filter on that field.

If your goal is catching requests slowed **by queuing**, consider `threshold=0` and filtering on `totalNanos` afterward, or design a duration event covering the full lifecycle with safe lifetime handling. At very high volumes, use sampling/tail-based strategies or bounded metrics instead of blindly enabling unbounded detail.

## 9. Special asynchronous scenarios

### 9.1. `CompletionStage` and callbacks

Wrong:

```java
// Wrong example: ending right after registering the async operation.
long start = System.nanoTime();
java.util.concurrent.CompletableFuture<String> future = startAsyncIo();
long end = System.nanoTime(); // Only measures Future creation time!
```

This is an **illustrative fragment**; `startAsyncIo()` is undefined, so it is not a standalone program. In principle, the right approach records ENDED **inside the completion path**:

```java
// Conceptual fragment, not a standalone program.
// 'future', 'context', and 'completeOnce' are provided by the application.
future.whenComplete((value, failure) -> {
    long endedNano = System.nanoTime();
    String outcome = (failure == null) ? "SUCCESS" : "ERROR";
    completeOnce(context, endedNano, outcome, failure);
});
```

Callbacks may run on a different thread; **pass context and monotonic timestamps scoped to the same JVM**. If timeout and completion race, `completeOnce` should use an atomic/terminal-state guard so ENDED is recorded once. Also keep boundaries clear: a caller timeout does not automatically cancel underlying I/O; if the caller finishes with TIMEOUT while downstream continues, two separate spans/events may be required.

### 9.2. Requests that never record ENDED

Sometimes `finally` cannot run: process crash, `kill -9`, machine loss, abrupt shutdown, or dropped log pipelines. Seeing RECEIVED without ENDED **is only a signal of a missing terminal record**, not proof of an eternal hang.

To tell them apart:

- check heartbeats/process restarts and time windows;
- verify deadlines/timeouts on both sender and receiver;
- inspect `in_flight` metrics, queues, and executor state;
- log `attemptId` to identify retries;
- monitor log drops and telemetry retention.

A JFR event committed at the end also **vanishes** if the JVM dies before commit or before flushing/dumping the recording. When remote hang detection is needed, logs at RECEIVED/STARTED plus live gauges are more reliable than completion-only events.

### 9.3. Rejected tasks, timeouts, retries

- **REJECTED:** if an executor rejects a task, there may be no STARTED. Record the terminal result at ingress/dispatch with `t_end` at rejection time; `workNanos` may be absent/not applicable. Never fake STARTED using `t_received`.
- **TIMEOUT:** mark according to the relevant deadline. If the operation continues in the background, track caller termination and background completion separately to avoid confusion.
- **CANCELLED:** mark only when cancellation actually occurs; "missing ENDED log" does not mean cancelled.
- **RETRY:** one logical request should have multiple `attemptId`s under one `requestId`, each with its own receive/start/end or per-attempt start per contract.
- **Partial result:** a 1 MB write that writes 900 KB before failing needs an explicit status like `PARTIAL_FAILURE` or `bytesWritten`/`errorCode`, not merely a boolean.

### 9.4. Clock domains across multiple JVMs

For a request traversing gateway → service A → service B, each JVM's monotonic clock has an independent origin. Perform time subtractions only within the same domain. To build cross-service timelines, use roughly synchronized wall clocks and distributed traces with span boundaries, noting possible NTP/scheduling/network skew. To measure exact network round-trip, measure send/receive on the same process for a local duration.

## 10. From data to I/O latency hypotheses

| Signal | Possible explanation | Next checks |
| --- | --- | --- |
| `waitToStart` rises, `work` stays stable | Queue backlog, worker pool saturation, rate limiter, scheduler/dispatch | Queue depth, pool size, active workers, rejected counts |
| `work` rises, `waitToStart` stays stable | Downstream I/O, filesystem, contention, or CPU inside worker | File/socket events, JFR thread stacks, downstream latency |
| `total` rises yet both numbers stay low | Measurement boundary misses where latency occurs, gap after ENDED | Compare ingress/server response time, tracing spans |
| `ERROR`/`TIMEOUT` rises while duration stays small | Fast-fail, validation, circuit breaker, or early deadline | Error codes, downstream status, retry policy |
| RECEIVED present without STARTED | Rejected, queue backlog, shutdown, or missing logs | Dispatcher metrics, queue acceptance, log health |
| STARTED present without ENDED | Hang, process crash, or missing telemetry | Thread dumps/JFR, in-flight metrics, process restarts |
| `work` high only on one path | Different I/O dependency or payload size | Group by operation, endpoint template, payload size |
| JFR has no events while logs show ENDED | JFR disabled, threshold/sampling, wrong recording window | `jfr summary`, event settings, recording window |

The rows above are **hypotheses**, not sole conclusions. Work duration can combine CPU, locks, network, and scheduling rather than pure I/O. Combine JFR `jdk.FileRead`, `jdk.SocketRead`, `jdk.JavaMonitorEnter`, execution samples, downstream metrics, and traces to verify the cause.

### 10.1. Never substitute averages for tail latency

During p99 incidents, a few requests waiting seconds before start can disappear inside an average of tens of milliseconds. Keep histograms/percentiles for **wait-to-start**, **work**, and **end-to-end**, split by operation and outcome. Never add p99 of two stages to infer end-to-end p99: percentiles are not simply additive. Compute percentiles from directly observed end-to-end distributions.

Use low-cardinality metric labels (`operation`, `result`, service name). Never put `requestId` as a Prometheus metric label—cardinality will explode; request IDs belong in logs, traces, and sampled JFR payloads.

### 10.2. Interpreting numbers when sampling is active

If JFR records only events exceeding a **work duration** threshold, never take the median of those recorded events and claim it is the median of all requests—the sample is biased. Likewise, if logs are sampled independently per phase, "missing ENDED" can simply be sampling rather than in-flight stalls.

Capture configuration must be part of the report: event names, thresholds, sampling rates, recording times, JDK version, and filters applied. Distinguish **telemetry gaps** from **application failures**.

## 11. Reducing overhead and protecting data

Collecting telemetry consumes CPU, allocations, queues, and I/O. A practical strategy:

1. Use always-on metrics/histograms for counts, statuses, and overall end-to-end duration.
2. Emit structured logs at appropriate boundaries, intentionally sampled when volume is high.
3. Use custom JFR events in diagnostic recordings or overhead-tested configurations; never enable all events/stacks unboundedly.
4. Measure log lines/s, bytes/s, `.jfr` size, and logging-sink cost; prevent synchronous logging on hot I/O paths from becoming the new bottleneck.
5. Separate **business outcome** from telemetry write success. A logging backend outage should not turn a business SUCCESS into ERROR unless required by contract.
6. Avoid PII and secrets. `requestId` should not embed direct personal identifiers; never log raw `Authorization` headers, tokens, SQL bind values, or sensitive bodies.
7. Enforce retention and file permissions on JFR recordings: they can contain class names, threads, stacks, file paths, and custom payloads you recorded.
8. For JSON logs, use an encoder library that properly escapes special characters/newlines; stdout in the demo only prints fixed IDs/statuses and does not handle arbitrary input.

If logging fields like `requestId` or `operation` derived from user input, validate/normalize/escape them. Never concatenate untrusted data unescaped into log lines due to log-injection risk.

## 12. Common mistakes

**Mistake 1 — Capturing STARTED at enqueue instead of worker start.** Every request shows near-zero wait-to-start even with huge queues. Place STARTED where the worker truly begins running.

**Mistake 2 — Recording ENDED right after getting a `Future`.** You measured only async submission time, not I/O completion. Move ENDED into the completion callback.

**Mistake 3 — Calling `Instant.now()` twice and subtracting for precise duration.** Wall clocks can jump; measure same-JVM durations with `System.nanoTime()` and use Instant/epoch millis to align timelines.

**Mistake 4 — Subtracting `nanoTime` across two processes.** Monotonic clock origins are not comparable across JVMs. Use distributed tracing/UTC timestamps for cross-service correlation, never cross-process tick subtraction.

**Mistake 5 — Recording END only on SUCCESS.** Exceptions/timeouts/cancellations leave requests open-ended and skew statistics. Record terminal outcomes once in `finally`/completion callbacks.

**Mistake 6 — Recording a fixed result despite errors.** `result=SUCCESS` must reflect meeting the contract, not merely method return. Store clear error types/statuses.

**Mistake 7 — Logging timestamps without `requestId`/`attemptId`.** You cannot reliably join the three phases when multiple requests share or run sequentially on threads. Use context propagation and correlation keys.

**Mistake 8 — Using JFR `event.getDuration()` as end-to-end when `begin()` is at STARTED.** Intrinsic event duration covers only the `begin`/`end` span. Use `totalNanos` or redefine event boundaries for total time.

**Mistake 9 — Setting a work-based threshold that drops queue-slowed requests.** A request with 800 ms wait and 2 ms work is dropped by a 50 ms threshold. Match event boundaries and sampling goals.

**Mistake 10 — Treating `REJECTED` as processed by a worker.** Requests rejected before start have a terminal outcome without valid work duration. Schemas should allow non-applicable fields.

**Mistake 11 — Computing `queue + work` from logs of different attempts.** Verify `requestId + attemptId` and ordering before computing; logs can reach aggregators out of order.

**Mistake 12 — Putting `requestId` into metric labels.** Cardinality explodes; request IDs belong in logs/traces, while metrics use categorical labels.

**Mistake 13 — Ignoring retry/backoff.** A logical request can stretch because retry waits sit outside each attempt's work; measure logical requests and attempts separately.

**Mistake 14 — Mistaking "no JFR events" for "no requests."** The recording may not have started, events may be disabled, thresholds too high, or data missing. Cross-check logs, metrics, and `jfr summary`.

## 13. Self-check quiz

**Question 1.** Monotonic timestamps (same JVM) are `t_recv=1000 ms`, `t_start=1060 ms`, `t_end=1100 ms`. Compute wait-to-start, work, and end-to-end.

*Answer:* 60 ms, 40 ms, and 100 ms. Total 60+40=100 ms.

**Question 2.** A request has 800 ms wait-to-start and 2 ms work. A custom JFR event calls `begin` at STARTED and has `threshold=50 ms`. Is it guaranteed to be recorded?

*Answer:* No. The threshold applies to intrinsic duration (~2 ms work), so it can be dropped despite ~802 ms end-to-end. To investigate queue latency, retain these events or adjust boundaries/sampling.

**Question 3.** An async method returns a `CompletableFuture` after 1 ms, while the I/O completes after 300 ms. When should ENDED be captured?

*Answer:* When the future genuinely completes per contract, not when the method returns the future.

**Question 4.** There are three attempts for the same `requestId`: ERROR, TIMEOUT, SUCCESS. How do you avoid mixing timings across them?

*Answer:* Record `attemptNo` or `attemptId` per attempt and measure attempt boundaries separately; add a logical end-to-end span/request outcome covering the full flow and backoff.

**Question 5.** Why does a log missing ENDED not by itself prove a deadlock?

*Answer:* It may be due to log ingestion failure, sampling, process crash, rejection/abort, lost completion callbacks, or not yet hitting a deadline. Check process/thread/queue/in-flight metrics and additional evidence.

**Question 6.** Across many requests, p99 wait-to-start = 100 ms and p99 work = 300 ms. Is p99 end-to-end guaranteed to be 400 ms?

*Answer:* No. The percentile of a sum does not simply equal the sum of percentiles. Compute end-to-end duration per request and build its own distribution.

**Question 7.** Does logging `ERROR` require logging the full exception message?

*Answer:* No. Store normalized error types/codes, controlled stacks/traces, and strip sensitive content. Full messages can leak secrets.

## 14. Checklist before treating evidence as complete

- [ ] Clearly defined RECEIVED, STARTED, ENDED, and RESULT at business boundaries.
- [ ] Included `requestId`/`operationId`, `attemptId`, and `traceId` where needed.
- [ ] Measured durations via `System.nanoTime()` in one clock domain; UTC timestamps for joining logs.
- [ ] Captured `waitToStartNanos`, `workNanos`, `totalNanos` with consistent units.
- [ ] Verified `total = wait + work` and valid timestamp ordering.
- [ ] Recorded terminal results across SUCCESS, ERROR, TIMEOUT, CANCELLED, and REJECTED where applicable.
- [ ] For async I/O, recorded ENDED in completion callbacks rather than at submission.
- [ ] Did not confuse wait-to-start with pure queue time without enqueue/dequeue markers.
- [ ] For custom JFR events, understood `Event.begin/end`, `threshold`, `commit`, and intrinsic duration.
- [ ] If JFR shows 0 events, verified event enablement, thresholds, recording window, and workload.
- [ ] Measured log/JFR overhead, limited sensitive fields, and enforced retention.
- [ ] Correlated durations and outcomes with system metrics, traces, and JVM JFR events.
- [ ] Avoided using high-cardinality request IDs as metric labels.
- [ ] Able to distinguish in-flight operations, missing telemetry, and real timeouts.

**Remember:** For diagnosing I/O latency, a single "done" timestamp is not enough. Record **receive → start → end + result** on **the same attempt**; use **monotonic time** for durations and **UTC wall-clock** for correlation; separate **wait-to-start** from **work**; and guarantee terminal events/logs are written even on errors. Structured logs excel for online investigation, while custom JFR events bundle timelines and outcomes to align with JVM evidence.

## References

- Oracle JDK 21 — [`Event` API: `begin`, `end`, `commit`, `shouldCommit`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Event.html).
- Oracle JDK 21 — [`jdk.jfr` package, event fields and settings](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html).
- Oracle JDK 21 — [`@Timestamp` annotation, `MILLISECONDS_SINCE_EPOCH`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Timestamp.html).
- Oracle JDK 21 — [`@Timespan` annotation, `NANOSECONDS`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Timespan.html).
- Oracle JDK 21 — [`Recording` API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html) and [`RecordingFile` API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html).
- Oracle — [JFR Event Threshold / `shouldCommit`](https://docs.oracle.com/en/java/javase/21/jfapi/event-threshold.html).
- Oracle JDK 21 — [`jfr` command: `summary`, `print`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html).
- SLF4J — [MDC API](https://www.slf4j.org/apidocs/org/slf4j/MDC.html): managing thread-scoped diagnostic context.
- Oracle Java 17 — [`System.nanoTime()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): elapsed-time measurement, origin has no UTC meaning.
