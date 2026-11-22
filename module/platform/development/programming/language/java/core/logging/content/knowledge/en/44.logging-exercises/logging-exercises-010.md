# Java Logging Performance Measurement — Hands-On Project from JDK 17 to Production Pipelines

## 1. Objectives and Final Deliverable

When developing Java services, logging can consume CPU time, allocate many intermediate objects, increase GC pressure, cause I/O blocking, or push events into asynchronous queues. At the same time, you cannot simply delete logs to get nice benchmark numbers: they serve incident investigation, monitoring, and sometimes mandatory auditing.

This **Performance Measurement** lesson in the **Java Core Logging Hands-On Project** aims to build a runnable measurement with clearly bounded results, and then extend it into a methodology for evaluating logging in production.

After this lesson, learners will be able to:

- Distinguish the costs of **message construction**, **level checking**, **log event creation**, **formatting**, **file writing**, **queuing**, and **transport**.
- Run a standalone Java 17 program comparing five logging modes.
- Apply warm-up, multiple trials, and median calculation without mistaking the results for a full JMH benchmark.
- Verify the number of events actually written, instead of claiming high throughput caused by dropping events.
- Interpret throughput, p95/p99 latency, allocation, GC, disk usage, queue depth, and ingestion lag.
- Design experiments for SLF4J/Logback, MDC, JSON encoders, AsyncAppender, and agent/collector pipelines.
- Build a performance budget, report reproducible results, and articulate trade-offs between performance, privacy, and reliability.

**Principle:** conclusions are only valid for the measured workload, system, and boundary; a few nanoseconds from a tight loop do not describe the full cost of a logging pipeline in production.

## 2. What Costs Are Included in Each Logger Call?

~~~text
Application business logic
          |
          v
Check effective logging level
          |
          v
Evaluate arguments / create message
          |
          v
Build LogRecord / ILoggingEvent
          |
          v
Capture MDC and exception context
          |
          v
Serialize text / structured JSON
          |
          +------ synchronous appender ------+
          |                                  |
          +------ async queue + worker ------+
                                             |
                                             v
                                     stdout / file
                                             |
                                             v
                                      host agent
                                             |
                                             v
                                    collector / index
~~~

A measurement must clearly select its boundary:

| Boundary | What is measured? | What is not proven? |
| --- | --- | --- |
| Java logger call | Time of the call on the caller thread | Whether the backend stored the event |
| Appender/memory handler | Provider creates the event and invokes the handler | Whether JSON/file/network works |
| Local file | Bytes written/flushed per file handler semantics | Disk durability across power loss or collector ingestion |
| Async enqueue | Caller puts the event into the queue | Whether the queue drained or did not drop |
| Collector ACK | Server received per protocol | May not be searchable yet |
| Backend query | Event was ingested/searchable | Does not automatically prove completeness in all cases |

**Do not treat the return time of `logger.info()` on an async appender as end-to-end time.** The app can enqueue very quickly while the queue grows, disk fills up, or the collector drops events.

## 3. Metrics That Must Be Collected with Proper Units

| Metric | Meaning | Interpretation risk |
| --- | --- | --- |
| operations/s | Benchmark operations completed per second | Does not automatically equal log records/s |
| log records/s | Events actually processed in a stage | May not have reached storage yet |
| elapsed ms | Duration of one trial | JIT/GC/scheduler noise |
| p50, p95, p99 | Latency percentiles of operations/requests | Not the median of trial durations |
| CPU utilization | CPU resources of app/agent | I/O waits can be slow with low CPU |
| allocation MB/s | Object allocation rate | Can impact GC and latency |
| GC pause | Stop-the-world time or related GC activity | Coinciding GC is not always the root cause |
| bytes/s | File/stdout/network data rate | Affected by encoding/compression |
| queue depth | Async backlog | Empty queue does not prove remote storage |
| drop count | Events discarded intentionally or due to overload | High throughput due to drops is a failed result |
| ingestion lag | Time from event emission to backend queryability | Depends on batching and index refresh |

A report must state **scope**, **denominator**, and **event definition**. For example, 10,000 calls/s with DEBUG disabled is not equal to 10,000 INFO records/s to a JSON file.

## 4. Establish a Performance Budget Before Optimizing

Do not measure out of curiosity for the highest number. Document system criteria first:

- How much **p99 latency** increase is the proposed logging allowed to add according to the SLO?
- How many events at INFO/WARN/ERROR does each request generate under normal load?
- When a dependency fails and generates many stack traces, how much does log volume increase?
- What sampling/drop policy can diagnostic logs use; are there alerts on dropped event counters?
- Does audit/compliance require durability and zero drops?
- What are the limits on disk quota, agent spool, network throughput, and retention?
- If the collector is unresponsive for 5 minutes, will the app block or continue serving requests?
- Is there a requirement that privacy-sensitive fields must not leave the application?

Example plan template:

~~~yaml
experiment: java-logging-performance
baseline: "same business workload, same host configuration"
candidate: "one logging change at a time"
primarySli: "request p99 latency"
secondary:
  - "throughput"
  - "allocation bytes/operation"
  - "GC pauses"
  - "log records delivered"
  - "agent queue depth"
gates:
  - "required logs complete according to contract"
  - "synthetic secrets absent from every tested sink"
  - "performance regression within approved budget"
~~~

This YAML is a **measurement plan template**, not an executable Java/Logback configuration. Acceptance thresholds must be validated by the SLO owner and actual baseline data, rather than setting a fixed number for all services.

## 5. Initial Java 17 Experiment Matrix

Start with a single-threaded program, synthetic inputs, and an isolated logger:

| Mode | Activity | Purpose |
| --- | --- | --- |
| BASELINE | Loop + checksum, no logger call | Measure minimal workload |
| DISABLED_EAGER | Build message then call JUL logger at disabled FINE | Observe argument evaluation cost even when log is not emitted |
| DISABLED_GUARDED | Check `isLoggable(FINE)` before building message | Test guard benefit for expensive messages |
| ENABLED_MEMORY | INFO + handler that only counts LogRecords | Isolate provider cost from file/JSON |
| ENABLED_FILE | INFO + FileHandler + UTF-8 line formatter | Explore file output cost |

**The modes do not perform identical work**: BASELINE does not build messages, the memory handler does not format JSON, and FILE performs disk I/O; this is intentional to separate layers. To fairly compare two frameworks or two appenders, keep **the same event count, payload, formatter, and sink**.

The first benchmark uses 20,000 operations for the first four modes and 2,000 for file to avoid excessive disk load during the lab. Do not directly compare `medianMs` between two modes with different N; `ops/s` is only a preliminary indicator.

## 6. Environment Requirements and How to Run

You only need **JDK 17 or higher**, with `javac` and `java` on your PATH. The program uses `java.util.logging` (JUL) bundled with the JDK, requiring no Maven or internet access.

Before running, record:

~~~bash
java -version
javac -version
~~~

Choose a machine with minimal background workload; record OS, CPU, RAM, JDK vendor, heap flags, and filesystem type. On Windows, antivirus/file indexing can affect file I/O; in containers, CPU quotas, memory limits, and ephemeral storage can skew numbers.

**Do not use real user data or production tokens.** All `requestId` values in the lab are synthetic strings; output goes into a temporary file deleted by the program after verification.

## 7. Hands-On Program: LoggingPerformanceLab.java

The following example uses **JUL Logger + Handler + FileHandler**. Each mode is warmed up for 2 rounds, measured for 5 rounds, sorted by duration, and the median is taken. Event count is verified after each round; for file output, the program verifies exact line count N and positive bytes after closing the handler.

Create **LoggingPerformanceLab.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Locale;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.stream.Stream;

public final class LoggingPerformanceLab {
    enum Mode {
        BASELINE,
        DISABLED_EAGER,
        DISABLED_GUARDED,
        ENABLED_MEMORY,
        ENABLED_FILE
    }

    private static final int RECORDS = 20_000;
    private static final int FILE_RECORDS = 2_000;
    private static final int WARMUP_ROUNDS = 2;
    private static final int MEASURE_ROUNDS = 5;
    private static volatile long blackhole;

    private record Measurement(long nanos, long events, long bytes) {}

    private static final class CountingHandler extends Handler {
        long count;

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                count++;
            }
        }

        @Override public void flush() {}
        @Override public void close() {}
    }

    private static final class PlainLineFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            return record.getMessage() + "\n";
        }
    }

    private static String makeMessage(int value) {
        return "event=work_done requestId=req-"
                + (value & 1023) + " value=" + value;
    }

    private static Measurement runOnce(Mode mode, int n)
            throws Exception {
        Logger logger = Logger.getLogger("perf.lab." + mode.name());
        logger.setUseParentHandlers(false);

        boolean disabled = mode == Mode.DISABLED_EAGER
                || mode == Mode.DISABLED_GUARDED;
        logger.setLevel(disabled ? Level.WARNING : Level.INFO);

        Handler handler = null;
        CountingHandler counting = null;
        Path file = null;

        try {
            if (mode == Mode.ENABLED_MEMORY) {
                counting = new CountingHandler();
                counting.setLevel(Level.ALL);
                handler = counting;
                logger.addHandler(handler);
            } else if (mode == Mode.ENABLED_FILE) {
                file = Files.createTempFile("log-perf-", ".log");
                FileHandler output =
                        new FileHandler(file.toString(), false);
                output.setEncoding(StandardCharsets.UTF_8.name());
                output.setFormatter(new PlainLineFormatter());
                output.setLevel(Level.ALL);
                handler = output;
                logger.addHandler(handler);
            }

            long checksum = 0L;
            long start = System.nanoTime();
            for (int i = 0; i < n; i++) {
                checksum += (i & 1023);

                switch (mode) {
                    case BASELINE -> {
                        // Shared loop overhead, no logging.
                    }
                    case DISABLED_EAGER ->
                            logger.fine(makeMessage(i));
                    case DISABLED_GUARDED -> {
                        if (logger.isLoggable(Level.FINE)) {
                            logger.fine(makeMessage(i));
                        }
                    }
                    case ENABLED_MEMORY, ENABLED_FILE ->
                            logger.info(makeMessage(i));
                }
            }

            if (handler != null) {
                handler.flush();
            }
            long nanos = System.nanoTime() - start;
            blackhole = checksum;

            long events = counting == null ? 0L : counting.count;
            long bytes = 0L;

            if (mode == Mode.ENABLED_FILE) {
                logger.removeHandler(handler);
                handler.close();
                handler = null;

                bytes = Files.size(file);
                try (Stream<String> lines =
                             Files.lines(file, StandardCharsets.UTF_8)) {
                    events = lines.count();
                }
            }

            if ((mode == Mode.ENABLED_MEMORY
                    || mode == Mode.ENABLED_FILE) && events != n) {
                throw new IllegalStateException(
                        "Record count mismatch: " + events);
            }
            if (mode == Mode.ENABLED_FILE && bytes == 0L) {
                throw new IllegalStateException("Empty output file");
            }
            if ((mode == Mode.BASELINE || disabled) && events != 0L) {
                throw new IllegalStateException(
                        "Unexpected event from disabled logger");
            }
            return new Measurement(nanos, events, bytes);
        } finally {
            if (handler != null) {
                logger.removeHandler(handler);
                handler.close();
            }
            if (file != null) {
                Files.deleteIfExists(file);
            }
        }
    }

    private static void benchmark(Mode mode) throws Exception {
        int n = mode == Mode.ENABLED_FILE
                ? FILE_RECORDS : RECORDS;

        for (int i = 0; i < WARMUP_ROUNDS; i++) {
            runOnce(mode, n);
        }

        long[] times = new long[MEASURE_ROUNDS];
        Measurement last = null;
        for (int i = 0; i < MEASURE_ROUNDS; i++) {
            last = runOnce(mode, n);
            times[i] = last.nanos();
        }
        Arrays.sort(times);
        long median = times[MEASURE_ROUNDS / 2];
        double ms = median / 1_000_000.0;
        double throughput = n * 1_000_000_000.0
                / Math.max(1L, median);

        System.out.printf(Locale.ROOT,
                "mode=%s ops=%d medianMs=%.3f "
                + "opsPerSec=%.1f events=%d bytes=%d%n",
                mode.name(), n, ms, throughput,
                last.events(), last.bytes());
    }

    public static void main(String[] args) throws Exception {
        for (Mode mode : Mode.values()) {
            benchmark(mode);
        }
        System.out.println("sanity=PASS");
    }
}
~~~

Run commands:

~~~bash
javac LoggingPerformanceLab.java
java LoggingPerformanceLab
~~~

**Stdout characteristics:** If all checks pass, the program prints **6 lines**: five mode lines in enum order and one **`sanity=PASS`** line. Below is an **output structure template, NOT real measurements**. Ellipses represent values that will vary by machine and environment.

~~~text
mode=BASELINE ops=20000 medianMs=... opsPerSec=... events=0 bytes=0
mode=DISABLED_EAGER ops=20000 medianMs=... opsPerSec=... events=0 bytes=0
mode=DISABLED_GUARDED ops=20000 medianMs=... opsPerSec=... events=0 bytes=0
mode=ENABLED_MEMORY ops=20000 medianMs=... opsPerSec=... events=20000 bytes=0
mode=ENABLED_FILE ops=2000 medianMs=... opsPerSec=... events=2000 bytes=...
sanity=PASS
~~~

This exercise does not require fixed timing in stdout: **`System.nanoTime`, disk I/O, and JIT cause the numbers to vary**. The sanity line only verifies the lab invariants, not that all records were stored by a collector.

### How the Program Works

1. **BASELINE** still accumulates a checksum, avoiding a completely empty test region.
2. **DISABLED_EAGER** constructs the message before JUL checks the level; FINE is filtered out because the level is WARNING.
3. **DISABLED_GUARDED** checks `isLoggable(FINE)` first, skipping message construction when disabled.
4. **ENABLED_MEMORY** creates a `LogRecord` and the handler only counts; no JSON formatting, no I/O.
5. **ENABLED_FILE** uses a custom `PlainLineFormatter` and UTF-8, writes to a temp file; after flush and close, reads line count to ensure exact N.
6. Opening `FileHandler` is **outside** the timed region; emitting events and flushing are **inside** the timed region; checking and deleting the file are **outside** the timed region.
7. `CountingHandler` is not synchronized for multiple threads; the program **measures sequentially only**. Do not use this handler in production or concurrency benchmarks.
8. The **`blackhole`** variable is a `volatile` field that keeps the checksum as an observable side effect; it does not replace JMH `Blackhole`.
9. Allocation/GC costs are not printed directly; use JFR, a profiler, or JMH with appropriate plugins.
10. Re-run several times and keep real output. Do not report a percentage improvement without checking noise and fairness.

## 8. How to Read Results for Each Mode

Do not just look for the line with the highest `opsPerSec`:

| Mode | How to interpret the numbers? |
| --- | --- |
| BASELINE | Sets the loop baseline, not the full cost of business code |
| DISABLED_EAGER | Shows overhead when strings are still built even though FINE is off |
| DISABLED_GUARDED | Can reduce message construction cost when FINE is off |
| ENABLED_MEMORY | Logger/provider + lightweight handler cost |
| ENABLED_FILE | Includes formatter and local file I/O, typically varies with disk/cache |

**Do not directly compare `medianMs` of ENABLED_FILE (2,000 ops) with ENABLED_MEMORY (20,000 ops)**. Even though `opsPerSec` is normalized by N, the two paths still differ in formatting, sink, and flush, so this is exploratory only.

For a true A/B appender comparison, run both configurations with:

- The same N.
- Equivalent payload/message fields and lengths.
- The same JVM flags and hardware.
- The same level mix and error/stacktrace ratio.
- The same sync/async mode or clearly accounted-for differences.
- The same definition of accepted/delivered events.

**Do not claim "A is X% faster than B" if the workloads differ.**

## 9. Verify Correctness Before Performance

A benchmark can appear fast by skipping work. Therefore, ensure:

- INFO events are received by the counting handler/file in the exact expected count.
- Disabled FINE logs do not leak when logger level is WARNING.
- No root console handler prints extra data that skews timing.
- File appender is closed before counting lines.
- Comparison results do not include stdout inside the timed loop.
- No random inputs or system clock in messages make output hard to reproduce.
- File/handler resources are cleaned up even on exception.
- No real customer data or tokens are in the payload.
- If extended to multi-threading: counters/thread-safety must be correct.
- Do not label bytes flushed only to cache as "durable".

**Observed event counts must be part of the results**, not just time. For async logging, enqueued and drained counts must be reported separately.

## 10. Warm-Up, JIT, and JVM Optimizations

Java HotSpot typically compiles/optimizes code after sufficient execution; early runs can differ significantly from steady state.

Sources of noise:

| Phenomenon | Impact |
| --- | --- |
| JIT compilation mid-trial | Warmup and measurement results differ |
| Dead-code elimination | Workload no longer computes what you think |
| Constant folding | Overly fixed inputs make the benchmark too easy |
| Escape analysis | Allocations differ from real code |
| GC and safepoints | Create elapsed time spikes |
| CPU turbo/thermal scaling | Trials run faster/slower depending on temperature |
| Disk page cache | File writes do not yet reflect persistent media |
| Background tasks | Scheduler/I/O contention |

The lab uses **2 warm-up rounds and 5 measurement rounds** and takes the median. That is a good initial habit, **but does not guarantee high statistical confidence**.

When observing very small `isLoggable` costs, use **JMH** and multiple JVM forks. Do not take a single `System.nanoTime` loop and claim a call costs an exact number of nanoseconds.

## 11. When Should You Use JMH?

JMH (Java Microbenchmark Harness) is meant for very small JVM operations where manual timing easily errs:

- Level checks and disabled logging.
- Parameterized logging versus eager string concatenation.
- `MDC.get`/`put`/map copy costs.
- JSON formatting and structured argument serialization costs.
- A logging wrapper with a consistent mock sink.
- Throwable stacktrace formatting.
- Allocation rate per operation.

Example snippet for a project with JMH dependencies:

~~~java
@State(Scope.Thread)
public class LogCallBench {
    private final org.slf4j.Logger logger =
            org.slf4j.LoggerFactory.getLogger("bench");

    private int value = 42;

    @Benchmark
    public void disabledDebugGuard() {
        if (logger.isDebugEnabled()) {
            logger.debug("value={}", value);
        }
    }
}
~~~

**This is an integration JMH snippet**, not a standalone program: it requires `org.openjdk.jmh.annotations` imports, a JMH runner, SLF4J, and a backend/config. In particular, you must **verify that DEBUG is actually disabled** on the logger used.

When deploying JMH, configure warmup, measurement, forks, mode, and appropriate profilers; use JMH `Blackhole` or benchmark state to prevent the JVM from eliminating work. For benchmarks involving file/network I/O, explain the overhead separately because it is no longer a simple CPU-only nanosecond experiment.

**JMH throughput of a logger call does not directly equal HTTP request p99 latency.** Two different questions require two different types of tests.

## 12. Disabled Levels Can Still Cost CPU and Memory

In Java, arguments are evaluated before invoking the method:

~~~java
logger.debug("requestSummary={}", expensiveSerialize(request));
~~~

The snippet above uses SLF4J, not JUL. If DEBUG is disabled, the provider may not format the string, but **`expensiveSerialize(request)` has still executed** to produce the argument.

How to guard it:

~~~java
if (logger.isDebugEnabled()) {
    logger.debug("requestSummary={}", expensiveSerialize(request));
}
~~~

**Both are illustrative integration snippets only.** Do not apply them to raw requests containing PII in production. For cheap arguments, adding a guard may yield negligible improvement while complicating code; measure when arguments have real cost.

Also distinguish between:

- Building Strings via concatenation outside the logger.
- Passing objects to a parameterized API for the backend to format when enabled.
- Creating object/array parameters even when the level is disabled.
- Passing a supplier/lazy argument if the API/version supports it.
- Serializing a large record, DTO, or JSON right before the logger call.

**Parameterized logging is a performance tool, not redaction.** Even with placeholders, sensitive data can still be emitted when the level is enabled.

## 13. Measure Logback/SLF4J Directly and Do Not Extrapolate from JUL

The program in Section 7 uses JUL. If your actual project uses SLF4J + Logback or Log4j 2, you must run a dedicated benchmark with the exact backend:

| Backend/stack | Factors to measure |
| --- | --- |
| JUL | `LogRecord`, `Handler`, `Formatter`, `FileHandler` |
| SLF4J facade | API cost and provider binding |
| Logback | `ILoggingEvent`, `PatternLayout`, MDC snapshot, appenders |
| Log4j 2 | Layout, message types, `ThreadContext`, async logger/appender |
| OpenTelemetry | SDK/Exporter/BatchProcessor, OTLP, Collector |
| Agent gateway | Parse, batch, compress, buffer, TLS, transport |

When switching backends, keep the same level mix, schema, payload, output destination, and durability assumptions. Comparing Logback JSON against JUL `CountingHandler` is **comparing two different workloads**, not a meaningful framework race.

Name your report accurately: **"JUL line file test on JDK 17"**, not a generic **"Java logging performance"** without qualifiers.

## 14. How Do MDC and Context Propagation Affect Performance?

MDC helps attach `requestId`/`traceId`, but has costs:

1. Putting/reading keys in `ThreadLocal` or an adapter.
2. Snapshotting the context map when creating a log event.
3. Copying/restoring the map when submitting an `ExecutorService` task.
4. Serializing keys into JSON/text.
5. Cleaning up keys in `finally` when the request/task finishes.

Compare:

~~~text
Scenario A: no MDC
Scenario B: 2 keys (requestId, traceId)
Scenario C: 10 synthetic keys
Scenario D: copy/restore MDC across executor
~~~

To isolate the overhead of **context copy alone**, test the map API separately with JMH. To know the total output impact, have the encoder emit the keys and measure bytes/event and throughput.

If adding 10 MDC keys lengthens the JSON, the difference is not just `ThreadLocal`—it is also serialization, I/O, and indexing cost. **Do not skip MDC cleanup to optimize**: context leakage between request A and B is a correctness/privacy bug.

Avoid putting emails, access tokens, or raw customer objects into MDC. Those values increase log volume and PII leakage risk.

## 15. Formatters, Structured JSON, and Exceptions

A very short INFO event is far different from an ERROR with a stacktrace. Measure with a realistic mix:

| Workload | Characteristics |
| --- | --- |
| Short INFO | `eventCode`, `requestId`, `outcome` |
| INFO with MDC | adds `traceId`/`spanId`, service metadata |
| WARN retry | `attemptNo`, `errorCode`, `dependency` |
| ERROR throwable | class, message, cause, stacktrace per policy |
| Long message | 1–10 KB synthetic string if workload requires |
| JSON special characters | quotes, CR/LF, Unicode, escaping |
| High-cardinality fields | correlation IDs, dynamic exception types |
| Error storm | many simultaneous ERRORs/stacktraces |

A JSON serializer incurs escaping and field-name costs, but provides queryability value. Do not conclude text is better than JSON just because the output is shorter; balance **queryability, privacy, storage, and CPU**.

**Do not dump raw `Throwable` messages** if they may contain URLs/tokens/SQL params. When testing performance, use harmless synthetic exceptions; privacy checks are an independent release gate.

## 16. Synchronous and Asynchronous: Two Types of Latency

**Synchronous logging** can make the caller wait on the formatter/file/stdout. **Asynchronous logging** reduces I/O on the caller by enqueuing events.

| Mode | Advantage | Risk |
| --- | --- | --- |
| Sync appender | Easy to trace I/O path | Caller p99 increases when sink is slow |
| Async bounded queue | Caller returns fast while queue has space | Blocks/drops when full |
| Unbounded queue | Absorbs initial bursts | Memory growth/OOM |
| File-backed spool | Opportunity to retry/recover per policy | Disk full, corruption, cleanup |
| Direct network appender | Fewer operational layers | Network causes coupling/latency |
| stdout + host agent | Decouples transport from JVM | Agent lag/rotation/collector drops |

**An async test must measure caller latency, queue depth, drain rate, dropped count, and ingestion lag.** If you only measure `logger.info()` return time, you measure enqueue time rather than proving logs were stored.

Do not assume async diagnostic logging satisfies mandatory audit requirements. Auditing may require a transaction/outbox or a separate durable store.

## 17. Testing Backpressure with a Slow Sink

Staging experiment:

1. Configure an **intentionally small** async queue.
2. Have a synthetic producer emit events faster than the sink's capacity.
3. Block or slow down the sink using an authorized fixture.
4. Monitor queue depth, enqueue time, blocked thread count, and dropped events.
5. Sustain overload long enough to observe block/backoff/discard policies.
6. Let the sink recover; measure drain time.
7. Reconcile accepted, delivered, dropped, and still-buffered event counts.
8. Clean up workers/queues after the test.

Qualitative model:

~~~text
arrivalRate = generated events per second
drainRate   = events processed per second

if arrivalRate > drainRate persists:
  backlog grows until the queue is full
~~~

This is a qualitative model, not a formula to predict exact p99; batching, bursts, and variable processing times make queuing more complex.

**Increasing queue capacity does not fix insufficient drain rate**—it only delays saturation. You need a log volume budget, output scaling, appropriate sampling for diagnostic events, and alerting.

## 18. Files, Flushing, OS Page Cache, and Rotation

When measuring file I/O:

- **Buffered writes** may return before bytes are truly durable on disk.
- `FileHandler`/`OutputStream` may flush per event; different configs yield different throughput.
- OS **page cache** makes the second run differ from the first.
- SSDs, network filesystems, and container ephemeral volumes behave differently.
- Rolling/renaming/compression can cause spikes.
- A full disk/partition can affect both application logging and business I/O.
- File permissions and ownership determine whether the agent can read new logs after rotation.

Thus, a "FileHandler wrote N lines" measurement is not a durable storage benchmark. If a contract requires `fsync` or an outbox transaction, measure that exact mechanism separately.

**Do not run load generating gigabytes of logs in production** just to get a throughput number; use authorized environments and safe quotas.

## 19. End-to-End: Java → Agent → Collector → Backend

A full-pipeline measurement can use synthetic canary events:

~~~text
JVM event with stable eventId
       |
       v
Local stdout / file
       |
       v
Host agent / DaemonSet
       |
       v
Collector: parse, batch, transform, retry
       |
       v
Backend storage + query
~~~

Procedure:

1. Emit N events with unique `eventId`, timestamp, and clear schema.
2. Agent reads from the right source; avoid collecting both file and stdout to prevent duplicates.
3. Collector processes and sends per contract; measure queue, retries, and parse errors.
4. Query `eventId` in the backend within the approved deadline.
5. Count unique `eventId`s, duplicates, missing, and in-flight events.
6. Compute ingestion lag from `eventTime` to `observedTime`.
7. Test temporary collector unreachability, recovery, and reconciliation.
8. Verify synthetic privacy canary does not leak raw tokens outside policy.

**Do not treat an immediate empty query as a lost event** when the backend has eventual consistency. Poll with a clear deadline, then classify the result as pass, fail, or insufficient evidence.

**Do not use `eventId`/`requestId`/`traceId` as metric labels**: high cardinality. Use them in logs/traces for investigation; keep metrics to bounded labels.

## 20. p95/p99 API Latency and Business Impact

To know if a logging strategy harms users, run a load test keeping the business workload consistent:

| Metric | Role |
| --- | --- |
| API throughput/RPS | Serving capacity |
| Success/error rate | Cannot be "faster because processing failed" |
| p50/p95/p99 latency | Impact on user experience and tail latency |
| CPU/GC/allocation | Investigable sources of overhead |
| Disk/network bytes | Pipeline cost |
| Async queue depth/drops | Evidence of log-loss conditions |
| E2E ingestion lag | Are logs still timely enough for alerts? |
| Business state | Retries, transactions, and audits remain intact |

Do not take the **median elapsed time of five trials** and call it p99 API latency. You must collect per-request latency distributions or a properly defined histogram.

Compare baseline/candidate on the same machine/traffic with enough repetitions; if the difference is 2% while noise is 10%, there is no conclusive evidence. Load generator monitoring must also be stable.

## 21. Concurrency and Lock Contention

A single-threaded program **cannot** predict the effects of many request threads writing to an appender simultaneously.

Sources of contention include:

- Synchronized appenders or formatters.
- Multi-producer async queues.
- Shared timestamp formatters, locks, and caches.
- `ThreadLocal`/MDC map snapshots.
- Disk write serialization.
- Worker saturation and backpressure.
- Connection pools or network clients of remote appenders.

A practical matrix:

| Threads | Payload | Objective |
| --- | --- | --- |
| 1 | Short INFO | Single-thread baseline |
| 2 | Short INFO | Coordination overhead |
| 4 | INFO + MDC | Context cost |
| 8 | INFO/WARN/ERROR mix | Allocation/stacktrace |
| 16 or CPU budget | Error burst | Saturation and tail latency |

Use `CountDownLatch`/`CyclicBarrier` to synchronize the start, with timeouts/`finally` cleanup. Do not use `sleep` as the primary measurement. The counting handler in the lab is not thread-safe; if extending to multi-threading, use `LongAdder`/atomic counters or proper thread-safe design.

## 22. Allocation, GC, and Diagnostic Tools

MDC snapshots, JSON encoding, char arrays, `Throwable` formatting, and message building create allocations. GC pressure can increase p99 even when average throughput still looks good.

Useful tools:

- **JFR**: profile CPU, allocations, and GC events when authorized.
- **`jcmd`**: query the JVM with proper permissions in appropriate environments.
- **JDK unified GC logging**: observe collector pauses and counters.
- **JMH GC profilers**: estimate bytes/op in microbenchmarks.
- **APM/metrics**: correlate logger volume with business latency.

Additional example in a lab environment:

~~~bash
java -Xlog:gc=info LoggingPerformanceLab
~~~

This command may print extra GC events to the console; **stdout/stderr will no longer be exactly six lines** as when run without flags. The number of GC events varies with heap and workload. If no GC event occurs during the run, no extra GC lines may appear.

Heap dumps can contain PII/secrets and impact the service; **do not take a production heap dump just to measure logging**.

## 23. Distinguishing Bottlenecks from False Optimizations

Common pitfalls:

| Observation | Misinterpretation | How to verify |
| --- | --- | --- |
| Async queue faster than sync | "logs are stored faster" | Measure actual drain and ACK |
| Disabled logging is fast | "production INFO is also fast" | Measure enabled levels |
| Adding a guard saves CPU | "every parameterized call needs `if`" | Distinguish cheap vs. expensive arguments |
| Logger A writes fewer bytes | "framework A is better" | Normalize schema/payload |
| Sampling increases throughput | "improvement with no trade-off" | Count sampled/dropped events |
| Log file returns fast | "durable across power loss" | Understand flush/fsync semantics |
| Throughput rises when backend fails | "scaling succeeded" | Check buffers, drops, and business SLOs |
| Better p99 when dropping stacktraces | "no observability impact" | Check incident/audit requirements |

**Do not optimize by dropping required data.** A release must pass **both performance gates and correctness/privacy gates** simultaneously.

## 24. Reporting Results Properly

Table template to fill with **real post-run data**:

| Mode | Operations | medianMs | opsPerSec | Events | Bytes | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| BASELINE | 20,000 | *measured* | *measured* | 0 | 0 | Loop/checksum |
| DISABLED_EAGER | 20,000 | *measured* | *measured* | 0 | 0 | FINE off, still builds message |
| DISABLED_GUARDED | 20,000 | *measured* | *measured* | 0 | 0 | FINE off, skips message |
| ENABLED_MEMORY | 20,000 | *measured* | *measured* | 20,000 | 0 | Count handler |
| ENABLED_FILE | 2,000 | *measured* | *measured* | 2,000 | *measured* | File UTF-8 |

The *measured* cells are not pre-populated data. **Do not fabricate benchmark measurements.**

Reference formulas:

~~~text
throughputOpsPerSec = operations / elapsedSeconds

relativeOverheadPercent
  = 100 * (candidateElapsed - baselineElapsed) / baselineElapsed
~~~

Compute relative overhead only when both variants share **the same operations and conditions**. A very small baseline can make percentages very noisy. Report raw values, number of trials, and uncertainty—not just a single percentage.

If local file throughput is unusually high, check disk caching and counting; if no events are observed, the performance result is **invalid**.

## 25. Recording Configuration for Reproducibility

Every result should include:

- JDK vendor/version, JVM flags, GC mode, and heap size.
- Host OS, CPU, RAM, VM/container quotas.
- Disk type/filesystem/cache and background load level.
- Logger API/backend version (JUL, SLF4J/Logback, Log4j 2).
- Effective logger level, formatter, encoder, sampling config.
- Message length, event field count, stacktrace ratio, MDC keys.
- Number of threads, warm-up, measurement trials, number of events.
- Sink type: memory/file/stdout/agent/network.
- Flush/batching/queue limits, retry/drop policies.
- Throughput, p95/p99, GC, allocations, disk bytes, and event completeness.
- Backend query path and time window if E2E is included.

Store configs per procedure; **do not copy certificates, tokens, raw payloads, or secrets** into benchmark reports.

## 26. Ordered Extension Exercises

**Exercise A — message size:** increase synthetic message length, measure bytes/s and formatter cost. Keep N reasonable; do not create unboundedly large files.

**Exercise B — disabled logging:** compare eager concat, guarded concat, and parameterized SLF4J. Check whether an expensive serialize call is invoked when DEBUG is disabled.

**Exercise C — JSON:** replace text layout with a JSON encoder, keeping the same event schema and sink. Measure CPU/allocations/bytes, verify escaping/parsing, and do not drop fields just to go faster.

**Exercise D — MDC:** compare 0, 2, and 10 keys, writing JSON. Measure copy/restore across an executor, and test that IDs do not leak between request A and B.

**Exercise E — AsyncAppender:** use a small queue and slow sink, measure enqueue p99, drops, drain, and shutdown flush. Do not treat the queue as durable storage.

**Exercise F — collector outage:** use synthetic event IDs, temporarily interrupt the test collector, measure buffering/retries and end-to-end ingest lag. Reconcile unique events.

**Exercise G — error storm:** increase the ratio of ERRORs with synthetic `Throwable`s, measure GC spikes, CPU, log volume, sampling/rate-limit behavior, and dashboard usability.

**Exercise H — production-like load:** use an accurate business request profile (sanitized data), compare p95/p99 and error rate between two configurations against an approved performance budget.

## 27. Anti-Patterns When Measuring Logging

| Anti-pattern | Why it misleads | Replace with |
| --- | --- | --- |
| Single `System.nanoTime` | JIT/GC/scheduler noise | Warmup, multiple trials, JMH |
| Printing `System.out` in timed loop | Console dominates results | Print outside timed region |
| Comparing disabled vs. enabled and blaming framework | Workloads are not equal | Explain scope and match configs |
| Not checking event count | Drops inflate throughput | Positive correctness checks |
| Treating memory and file as equal | I/O and formatters differ | Same sink/bytes for conclusions |
| Measuring async only at enqueue | Hides backlog/drops | Drain rate + E2E |
| Omitting JVM/OS/config | Not reproducible | Run manifest |
| Using real personal data | PII leakage | Synthetic events |
| Disabling audit for high scores | Missing business evidence | Durable audit design |
| Using INFO avg to predict error storms | Stacktraces and allocations differ | Realistic mix |
| Calling trial median p99 latency | Wrong definition | Per-request samples/histogram |
| Running unbounded stress in production | Outage risk | Staging, quotas, approval |

## 28. Hands-On Acceptance Checklist

A result is acceptable when:

- **LoggingPerformanceLab.java** is a standalone Java 17 program with clear `javac`/`java` commands.
- The program prints five mode lines and one **`sanity=PASS`** line when checks succeed.
- Warm-up, multiple measurement rounds, and a properly defined median are used.
- Enabled modes verify exact event counts; file count and bytes are verified.
- No real user data is logged, and no leftover files are intentionally left behind.
- No fixed stdout timing is claimed; only an illustrative output shape is provided.
- **Disabled level, memory handler, synchronous file**, and full pipeline are clearly distinguished.
- `medianMs` is not compared between two variants with different N as if they were the same workload.
- JMH guidance is provided when true microbenchmarking is needed.
- There is a plan to measure p95/p99, GC/allocations, async drops, and E2E lag.
- A performance budget and correctness/privacy/reliability gates are defined.
- A report records JDK/OS, config, trial count, and measurement limitations.

**Conclusion:** Java Logging performance measurement is about measuring **the right costs in the right places with verification**, not just achieving the highest `ops/s`. Start with the Java 17 JUL lab to observe disabled logging and enabled handler overhead; use **JMH** for micro-operations, and **load/integration/end-to-end tests** to evaluate Logback/JSON/MDC/AsyncAppender and collectors in practice. A solid strategy preserves **accurate logs, zero PII leakage, and mandatory audit completeness** while fitting within CPU, latency, and storage budgets.
