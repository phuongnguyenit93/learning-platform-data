# Measuring Logging Overhead in Java Applications

## 1. What Is Logging Overhead?

**Logging overhead** is the additional resources and time an application must spend to create, process, transport, and store logs. When a business thread executes `logger.debug(...)` or `logger.info(...)`, costs can arise even if the final record never appears in a file. The cost depends on whether the logger is enabled, how the message is constructed, context capture, filters, formatters, queues, appenders, and the speed of the destination sink.

An application can use "asynchronous logging" and still incur significant cost on the request thread: level checks, argument evaluation, event construction, MDC copying, memory allocation, and enqueueing. Moving file/socket writes to a worker reduces some blocking operations on the request path; it does not make logging cost zero.

The goal of **measuring logging overhead** is to determine with evidence:

- How much extra **CPU, allocation, and time** does each log event or each request cost?
- How does logging affect **request throughput, p95/p99 latency, GC, and resource utilization**?
- Does the cost come from **logger calls, message construction, formatting, queues, or sinks**?
- When logging too much, does the system **block producers, drop events, grow backlog**, or lose logs on shutdown?
- Does raising the level to DEBUG/TRACE for investigation exceed operational limits, and which configuration reduces cost while preserving sufficient observability?

**There is no single universal "Java logging overhead" number.** The same log call can be nearly negligible if filtered out early, or very expensive with heavy formatters, costly arguments, synchronous writes to a slow sink, or a full queue.

## 2. Breaking Down the Path of a Log Event

```text
[Application calls logger]
          │
          ▼
  1. Evaluate Java arguments
          │
          ▼
  2. Check level/filter
          │
          ▼
  3. Create/capture log event
          │       (timestamp, thread, MDC/trace, exception...)
          ▼
  4. Format/serialize (timing depends on framework)
          │
          ├── Synchronous logging ──► 5a. Appender / file / socket
          │                                      │
          └── Asynchronous logging ─► 5b. Queue ─► Consumer ─► Sink
                                          │
                              Full queue: block / drop / fallback
          │
          ▼
  6. Collector / transport / index / backend storage
```

To measure accurately, you must define the **measurement boundary**. There are at least four distinct quantities:

| Quantity | Time span or resource measured | Meaning and limitations |
| --- | --- | --- |
| **Call-site cost** | From before calling the logger until the log API returns | Directly affects the business thread, including Java argument evaluation |
| **Event-processing cost** | Event creation, MDC, filtering, formatting, dispatch | Can be split between producer and consumer |
| **Sink cost** | Appender transferring the event to file/socket/collector | Does not automatically mean data is durable or indexed |
| **End-to-end delivery lag** | From event creation until observable in the backend | Includes queue, transport, retries, batching, ingestion |

**If you only measure the time for `logger.info(...)` to return in async logging**, you have only measured the producer-side cost under test conditions; you have not measured worker CPU, I/O, and the time to push logs to the backend.

### Example of the Same Call Having Different Costs

```java
// SLF4J snippet; requires SLF4J + backend in the application.
logger.debug("orderId={}", orderId);
```

With DEBUG disabled, the backend usually only needs a level check and avoids most event-creation work. However, **Java evaluates all argument expressions** before invoking the method:

```java
// The buildLargeSnapshot() method is still called even when DEBUG is disabled.
logger.debug("snapshot={}", buildLargeSnapshot());
```

To avoid expensive argument evaluation when the level is disabled:

```java
if (logger.isDebugEnabled()) {
    logger.debug("snapshot={}", buildLargeSnapshot());
}
```

This is a snippet, not a standalone program. Appender-side filters can still discard the event even when `isDebugEnabled()` returns `true`. With SLF4J 2.x, the fluent API and suppliers allow deferring some argument evaluations; verify the actual backend/API rather than assuming every overload is lazy.

## 3. Metrics to Measure

Measure **direct cost** and **service impact** in parallel. A single number like "logger.info takes 20 ns" does not tell you whether the backend can keep up with writes or whether request p99 increases.

| Metric | Interpretation | What to watch out for |
| --- | --- | --- |
| `ns/op`, `µs/op` | Average time for a well-defined log operation | Compare matching scenarios; do not extrapolate to p99 |
| `CPU time/op` or CPU% | CPU for creating, filtering, formatting, and transporting logs | Async workers may use separate CPU |
| `bytes allocated/op` | Heap allocation per log call | Can trigger GC even when call-site latency is low |
| `request throughput` | Requests/second under fixed load | Logging can reduce throughput when CPU/I/O saturates |
| `p50/p95/p99 latency` | Business latency distribution | Requires sufficient samples; compare same request type and load |
| `GC pauses` and allocation rate | Memory pressure from creating messages/events | Measure with the same heap and GC configuration |
| `queue_depth` / `queue_capacity` | Backlog level in an async logger | Sustained high queue depth indicates consumer cannot keep up |
| `enqueue_wait` | Time producer is blocked when the queue is full | Can cause spikes in request p99 |
| `dropped_events_total` | Number of logs discarded by policy/overload | Do not treat high throughput as good if logs are lost |
| `sink_write_latency` | Time for appender/consumer to write to destination | Distinct from request latency and enqueue wait |
| `delivery_lag` | Time from event creation until queryable in backend | Depends on collector/transport and clocks |
| `disk/network bytes/sec` | Resource cost at sink/collector | Distinguish appender writes from backend ingestion |

**Event delivery rate** must be interpreted across distinct milestones: *attempted*, *accepted into queue*, *processed by consumer*, *received by sink*, *persisted by backend*. Counting `enqueued_total` cannot substitute for `persisted_total` if the system crashes or loses connectivity.

For measurements to be meaningful, also record the JVM/JDK, CPU core count, heap/GC, logging backend and version, sink type, queue size, batch policy, message size, level distribution, producer count, workload, and run duration.

## 4. Designing a Baseline: How to Compare?

### Need at Least One Baseline

Measure the same business work under controlled configurations:

| Scenario | Configuration | Question |
| --- | --- | --- |
| **A — No test log emitted** | Equivalent business path without calling the logger at the measurement point | Baseline cost of the business work |
| **B — Level disabled** | DEBUG call present, but effective logger level is INFO | Cost of logger check and argument evaluation |
| **C — Level enabled, no-I/O sink** | DEBUG/INFO enabled; handler/appender accepts but does not write to console/file | What do creation, dispatch, and formatting (if any) cost? |
| **D — Level enabled, real sink** | Same message, written to a defined file/stdout/network | Additional cost of real serialization/writing |
| **E — Async, real sink** | With queue/consumer and explicit backpressure policy | How do on-request cost and background cost change? |

Scenario C must be described accurately: a `NullAppender`/`NoOpHandler` only eliminates I/O writes; if it does not run the formatter, the measurement **does not include** formatter cost. When you want to isolate the formatter, add a scenario that passes events through the encoder into a controlled in-memory destination.

When comparing **A and B**, do not alter business logic or data just because logging was removed. For example, do not replace `logger.debug("{}", compute())` with "do nothing" and conclude the entire difference is framework cost: `compute()` was still evaluated in B. State clearly whether you are measuring **total call-site cost** or **logger/backend cost only**.

### Keep Realistic Load Stable

An application test should hold constant: request mix, concurrency, data, environment, endpoints, deployment order, JVM flags, heap/GC settings, connection settings, and downstream/sink speeds. You can run repeated A/B pairs and alternate the order A–B–B–A to reduce CPU thermal or cache effects.

**Do not compare one configuration on a developer machine with another in a production container** and call the difference logging overhead. Execution conditions differ too much.

## 5. Measuring Latency and Throughput Without Formula Mistakes

Suppose under the same fixed load test you observe:

| Metric | Logging OFF | Logging ON |
| --- | ---: | ---: |
| Throughput | 10,000 req/s | 9,200 req/s |
| p95 latency | 15 ms | 17 ms |
| Average CPU | 55% | 68% |

The numbers above are **illustrative** only. In this case:

- Throughput drop relative to OFF: `(10,000 − 9,200) / 10,000 = 8%`.
- p95 increase: `17 − 15 = 2 ms`; relative increase is about 13.3%.
- CPU increased by **13 percentage points**; do not say "CPU increased by 13%" because the relative percentage is `(68 − 55)/55 ≈ 23.6%`.

**Interpretation warning:** two p95 values are percentiles of two observation sets, not that every single request slowed down by exactly 2 ms. Measurements are also affected by jitter, load, GC, JIT, and downstream systems. A difference does not prove causation if non-logging configuration also changed.

If you know the number of **log events actually created/accepted** in the same workload, you can estimate a resource budget:

```text
extra_cpu_time_per_accepted_event
  ≈ (total_cpu_time_logging_on - total_cpu_time_logging_off)
     / accepted_log_events_logging_on
```

This metric is an **estimate of incremental cost per event in that experiment**, not a constant across all levels, message sizes, or concurrency levels. Do not divide by `written` events if events were dropped and you want to estimate the cost per *offered event*. You can report both **per attempted event** and **per delivered event** to avoid hiding the cost of dropped events.

For async loggers, report both **request latency** and **overall CPU/I/O**; if request latency drops while worker CPU surges or the queue builds up, you cannot conclude the solution is better.

## 6. Standalone Java 17: Observing Call-Site Cost

The following code uses the JDK's **`java.util.logging` (JUL)** with no external dependencies. It demonstrates with deterministic counts:

1. When `FINE` is disabled, an **eager argument** is still evaluated by Java before calling the logger.
2. When `FINE` is disabled, a **`Supplier<String>`** is not invoked to build the message.
3. When `FINE` is enabled, the supplier is invoked and the event enters the handler.
4. When `INFO` is enabled with a simple message, the event enters the handler without running the test message-building method.

The program also measures elapsed wall time using `System.nanoTime()`, but **does not claim the timing results are a proper benchmark**: short warmup, single thread, JUL backend, and a no-I/O handler. Timings vary by machine and JVM. The event counts verify the scenario being measured.

Save the file as **`LoggingOverheadDemo.java`**:

```java
import java.util.Locale;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LoggingOverheadDemo {
    private static final int WARMUP = 10_000;
    private static final int OPERATIONS = 50_000;
    private static final Logger LOG = Logger.getLogger("demo.overhead");
    private static int messageBuilds;

    private static final class CountingHandler extends Handler {
        private int delivered;

        CountingHandler() {
            setLevel(Level.ALL);
        }

        @Override
        public void publish(LogRecord event) {
            if (isLoggable(event)) {
                delivered++;
            }
        }

        @Override
        public void flush() {
            // No I/O writes: isolates part of the logger/dispatch cost.
        }

        @Override
        public void close() {
            // No resources to close.
        }

        void reset() {
            delivered = 0;
        }

        int delivered() {
            return delivered;
        }
    }

    private static String buildMessage() {
        messageBuilds++;
        return "payload-" + messageBuilds;
    }

    private static void measure(
            String name,
            Level level,
            Runnable operation,
            CountingHandler sink) {

        LOG.setLevel(level);
        for (int i = 0; i < WARMUP; i++) {
            operation.run();
        }

        messageBuilds = 0;
        sink.reset();

        long start = System.nanoTime();
        for (int i = 0; i < OPERATIONS; i++) {
            operation.run();
        }
        long elapsedNanos = System.nanoTime() - start;

        // stdout contains deterministic counting results.
        System.out.printf("%s | builds=%d | handled=%d%n",
                name, messageBuilds, sink.delivered());

        // stderr contains measurements that vary by JVM/machine/run time.
        System.err.printf(Locale.ROOT, "%s | elapsed_ms=%.3f%n",
                name, elapsedNanos / 1_000_000.0);
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        CountingHandler sink = new CountingHandler();
        LOG.addHandler(sink);

        try {
            measure(
                "disabled-eager", Level.INFO,
                () -> LOG.fine("msg=" + buildMessage()),
                sink);

            measure(
                "disabled-lazy", Level.INFO,
                () -> LOG.fine(() -> "msg=" + buildMessage()),
                sink);

            measure(
                "enabled-lazy", Level.FINE,
                () -> LOG.fine(() -> "msg=" + buildMessage()),
                sink);

            measure(
                "enabled-constant", Level.INFO,
                () -> LOG.info("constant message"),
                sink);
        } finally {
            LOG.removeHandler(sink);
            sink.close();
        }
    }
}
```

Compile and run:

```bash
javac --release 17 LoggingOverheadDemo.java
java LoggingOverheadDemo
```

**Exact stdout** (considering stdout only; `stderr` contains `elapsed_ms` numbers that vary by run):

```text
disabled-eager | builds=50000 | handled=0
disabled-lazy | builds=0 | handled=0
enabled-lazy | builds=50000 | handled=50000
enabled-constant | builds=0 | handled=50000
```

Explanation of results:

- `disabled-eager`: `buildMessage()` is called **50,000 times**, even though `LOG.fine` is blocked by the INFO level, so the handler receives 0 events. Expression evaluation occurs before the logging API.
- `disabled-lazy`: the supplier is not evaluated when FINE is blocked, so both `builds` and `handled` are 0.
- `enabled-lazy`: FINE is enabled; the supplier is evaluated and the handler receives all 50,000 records.
- `enabled-constant`: INFO is enabled; no test payload needs to be built, yet 50,000 `LogRecord` instances are still dispatched to the handler.
- `CountingHandler` **does not write to a file, socket, or console**. The time on `stderr` measures logger calls + dispatch and the demonstration operations, not the total cost of persisting logs in production.
- The `measure` method runs warmup before timing, but each scenario has different code paths and can be affected by JIT/GC/CPU noise. Do not compare `elapsed_ms` numbers as final performance proof.

**Limitations to note:** the example uses counters in a single thread; in a multi-threaded system, measure event counters using a thread-safe design. Do not put `System.out.println` inside the measured path, as that operation distorts the very results you are trying to observe.

## 7. More Reliable Microbenchmarking with JMH

For per-call logger cost, **JMH (Java Microbenchmark Harness)** is more suitable than a hand-written `System.nanoTime()` loop. JMH manages warmup, repeated measurement, JVM forks, and statistics to reduce bias from JIT/initialization.

A benchmark should define precise scenarios, such as:

- Logger **disabled**, constant arguments, no significant allocation.
- Logger **disabled**, expensive eager arguments.
- Logger **disabled**, lazy/supplier arguments.
- Logger **enabled** to a no-op sink, constant message.
- Logger **enabled** to a JSON formatter with a controlled in-memory sink.
- Logger **enabled** to file/stdout/socket, measured as a **system benchmark** outside JMH when I/O and backpressure are the focus.

An **illustrative JMH skeleton**, requiring the `org.openjdk.jmh:jmh-core` dependency and the `jmh-generator-annprocess` annotation processor configured in the build. This is **not a standalone Java file**:

```java
@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 8)
@Fork(2)
public class LoggerCallBenchmark {
    private final java.util.logging.Logger logger =
            java.util.logging.Logger.getLogger("bench.disabled");

    @Setup(Level.Trial)
    public void setUp() {
        logger.setUseParentHandlers(false);
        logger.setLevel(java.util.logging.Level.INFO);
    }

    @Benchmark
    public void disabledFineConstant() {
        logger.fine("constant message");
    }
}
```

The annotations here come from `org.openjdk.jmh.annotations.*`, so JMH imports and configuration are required when using it. Only use the results of this benchmark for a **disabled FINE call-site**; it **does not measure** file writing or network transmission costs.

When implementing JMH:

1. Use multiple forks, sufficiently long warmup, and enough iterations; report dispersion/statistics, not just a single best number.
2. Choose an appropriate baseline; avoid benchmarks where the JVM optimizes away all the work. For constructed data or formatters, use state/`Blackhole` properly.
3. Do not enable console output for millions of log calls in a microbenchmark if the goal is pure logger cost; the terminal can become the main bottleneck.
4. When measuring allocations, use an appropriate JMH profiler, such as `-prof gc` when available in your setup.
5. Separate message lengths, argument types, logger levels, formatter styles, and sink configurations into distinct measurement groups; do not collapse them into one number.
6. Be careful with multi-threaded measurements. Thread count, CPU affinity, GC, and JIT compilation can cause large variance in results.

## 8. Measuring Formatters, Message Size, and Allocation

Besides level checks and dispatch, significant work often lies in **data creation**:

- String concatenation, `String.format`, object/JSON serialization, timestamp formatting, and exception stack traces.
- Copying MDC context, `trace_id`, `span_id`, thread name/caller location.
- Capturing stack traces: can cost much more than an ordinary short message.
- JSON encoders, character escaping, and extra fields of structured logging.
- Large arguments, complex `toString()` methods, or reading database data just to log it.

Design independent scenarios: 20 B, 200 B, 2 KB messages; with/without exceptions; 0/5/20 MDC fields; JSON vs plain text; with and without caller location. Do not test with the same small immutable object and draw conclusions about large real-world log payloads.

**Allocation and GC:** logging cost can show up as increased allocation rate and more frequent GC runs, even when the p50 of a logger call looks small. Track allocation rate, bytes/op, young GC, pause times, and heap occupancy under the same load. Java Flight Recorder (JFR) is a useful tool for investigating allocations, CPU hotspots, and socket/file I/O; choose appropriate events and recording settings to limit profiler overhead.

Do not attribute every GC spike to logging just because it appeared when DEBUG was enabled. Compare before/after, inspect allocation stack traces, and vary request volume to confirm.

## 9. Measuring Sink I/O: Synchronous vs. Asynchronous

### Synchronous Logging

When `FileAppender` or `ConsoleAppender` runs directly on the request thread, logger call time can include formatting and write operations. The speed of the disk/terminal/stdout collector directly affects latency.

Measure at least:

- Time the request thread waits inside the appender/write.
- Request throughput and latency as log volume increases.
- CPU for encoding, file write bytes/sec, disk IOPS, write errors.
- Flush/buffer policies, rotation, and lock contention across threads.
- Backend log ingestion latency if a collector sits downstream.

Writing to `/dev/null` or a no-op sink is not equivalent to real file writes: it removes or alters filesystem and buffering behavior. Writing to a console in an IDE also differs from stdout in a container collected by a log driver.

### Asynchronous Logging

With `AsyncAppender`/async loggers, split the measurement:

```text
Request thread:
  log call ─► create event ─► enqueue ─► return
                                  │
                                  ▼
                        Queue / consumer lag
                                  │
                                  ▼
Background worker:
                      format/write/flush ─► collector
```

Measure **both sides**: call-site latency on the producer and total CPU + I/O + delivery lag on the consumer/sink. When the queue fills up, depending on framework policy, the producer may block, events may be dropped, or processing may fall back to synchronous execution. This makes light-load measurements completely different from high-load measurements.

Essential metrics:

| Metric | Usage |
| --- | --- |
| `events_attempted_total` | Number of calls/events offered for processing |
| `events_enqueued_total` | Number of events accepted into the queue |
| `events_dequeued_total` | Number of events taken by the consumer |
| `events_written_total` | Number of events accepted by the sink per measurement definition |
| `events_dropped_total` | Number of events discarded by policy |
| `enqueue_wait_p99` | Whether producers are blocked when the queue is full |
| `queue_depth` and `consumer_lag` | Whether the worker keeps up with event production rate |
| `sink_error_total` | File/connection write errors or timeouts |
| `shutdown_pending` | Number of events remaining at shutdown |

The names above are only a **suggested metric model**; not every framework exposes these metrics out of the box. Check your actual instrumentation; if missing, add low-overhead measurements or collect them from the appender/collector.

**Key takeaway:** producer latency can be very low while the queue grows until full, many logs are dropped, or the backend lags by tens of seconds. Comparing "async is faster than sync" without measuring delivery/backlog is insufficient.

## 10. Analyzing Queues, Throughput, and Overload Risk

Suppose the event arrival rate is `λ` and the consumer processing rate is `μ` (in events/s). If `λ > μ` persists, the backlog grows until it hits its limit. A queue only absorbs short bursts; it does not create sustained I/O capacity.

You can calculate a simple budget:

```text
incoming_log_bytes_per_sec ≈ events_per_sec × avg_encoded_bytes_per_event

estimated_buffer_bytes ≈ queue_capacity × avg_in_memory_event_bytes

required_sink_throughput >= sustained_incoming_log_bytes_per_sec
                         (if you do not want backlog to grow continuously)
```

Note that an event's size **in the heap** can be larger than the string written to the sink because of object headers, references, context, and intermediate data. Do not infer heap queue usage directly from JSONL size on disk.

Illustrative example: 20,000 events/s × 300 B/event ≈ 6 MB/s of encoded data, before protocol, collector, indexing, or file rotation overhead. If the sink can only sustain 4 MB/s over time, increasing queue size only delays when it fills up without solving the bottleneck.

During load tests, you must **also report lost events**. A configuration that is "30% faster" while dropping most DEBUG/WARN logs may not meet observability goals.

## 11. Measuring Request Impact in a Real Application

Microbenchmarks reveal mechanisms, while **load tests** answer whether the application can handle the logging load.

Recommended process:

1. Pick an endpoint or workflow with realistic logging (orders, data reads, batch processing). Document the frequency of each log level and event size.
2. Run steady load at low, medium, and near-capacity levels; do not test only when CPU is nearly idle.
3. Establish an OFF/INFO baseline, then enable DEBUG for the target package and repeat the **same request mix**.
4. Record p50/p95/p99, throughput, error rate, CPU, heap, GC, disk/network throughput, and logging queue state.
5. For async logging, verify how many events reached the sink after draining or over a consistent measurement window.
6. Repeat each configuration, interleave run order, and record run-to-run variance. Draw conclusions only when the difference exceeds measurement noise.
7. Test with slow disk/collector, near-full queues, log bursts, and shutdown under load, as this is where overhead usually becomes obvious.

**Comparison conditions:** with *closed-loop* load (clients wait for a response before sending the next request), throughput and concurrency can both shift; with *open-loop* load sent at a fixed arrival rate, latency can accumulate when the server saturates. Document the load model clearly. Percentiles are only comparable when error rates, request types, intervals, and timeout handling match.

To see how logging affects end-to-end latency, use request tracing/metrics at the same measurement points. Do not measure only internal Java methods if socket waits, queuing, or downstream calls dominate latency.

## 12. Using JFR and Profilers to Find Expensive Parts

For a running JVM, **JFR** helps answer "where are CPU/allocations being spent?". Areas to inspect:

- Stack traces containing loggers, formatters, JSON encoders, or exception rendering.
- Allocations of messages/objects/context, especially under DEBUG/TRACE.
- File writes or socket writes and blocking time on request threads.
- Thread states/lock contention around appenders and queues.
- GC pauses and allocation rates at the time logging levels change.
- Async consumer threads: CPU and I/O spent in workers even when request threads return quickly.

**Illustrative** command example for an environment with `jcmd`, permission to attach to the JVM, and JFR supported:

```bash
jcmd <PID> JFR.start name=logging-study settings=profile duration=60s filename=logging-study.jfr
```

Explanation: replace `<PID>` with the actual Java process PID; the recording produces a file to open in JDK Mission Control or a compatible analysis tool. Depending on the JVM/JDK, event names and defaults may differ. The `profile` configuration adds more overhead than `default`; measure with and without profiling when you need to know the impact of observation itself.

The absence of logging stacks in CPU samples **does not prove zero overhead**: sampling may miss very short segments; I/O waits, locks, or allocations require different views.

## 13. Distinguishing Frameworks, Versions, and Sink Configurations

A meaningful measurement must state the **actual logging backend running**:

- **SLF4J** is a facade API; a backend like Logback, Log4j2, or a JUL adapter performs the actual filtering and output.
- **Logback** has logger levels, filters, encoders, appenders, and an optional `AsyncAppender`. Queue/discard/neverBlock options change both cost and event-loss probability.
- **Log4j2** has synchronous/asynchronous paths, layouts, and filters, with queue/ring-buffer configurations depending on version. Do not use Log4j2 benchmark numbers to make claims about Logback.
- **JUL** has its own loggers, handlers, and levels; performance is affected by handlers, formatters, and bridges.
- **Spring Boot** has default logging configurations and can use different backend starters; changing `logging.level.*` only adjusts levels and does not replace full appender/sink configuration.

Do not claim "Logback is faster than Log4j2" from two non-equivalent configurations: one writing JSON to console and the other writing plain text to a no-op sink is not a valid comparison. Balance throughput, latency, CPU, allocation, event delivery, format, and overload safety.

## 14. Benchmark Pitfalls That Mislead

| Observed phenomenon | Why it is misleading | How to fix the measurement |
| --- | --- | --- |
| Disabled logger is very fast | All-constant arguments or JIT dead-code elimination | Add scenarios with expensive arguments and realistic input data |
| Debug still consumes CPU even when level is OFF | Evaluating `toString()`/JSON before the logger call | Use lazy evaluation or proper level guards |
| Async is fast but logs disappear | Full queue, discard policy, or missing shutdown drain | Measure attempted/enqueued/written/dropped and backlog |
| Console logging is unusually slow | Terminal/IDE/stdout collector is the bottleneck | Measure console separately and in the real deployment environment |
| File appender shows low overhead in microbenchmark | OS page cache or buffers hide flush/disk cost | Measure under sustained load, rotation, flush, and disk pressure |
| Benchmark results fluctuate constantly | JIT, GC, scheduler, CPU frequency, noise | Enough forks/warmup/iterations, report dispersion, fix environment |
| Great ns/op but bad request p99 | Full queue or lock contention under high load | Load test with concurrency and measure queue wait p99 |
| GC increases after enabling DEBUG | Many message/event/stack trace allocations | JFR/JMH allocation profiler, compare same workload |
| Logger is disabled but messages are still built | Java evaluates arguments before the method call | Verify eager/lazy call-sites using counters or a profiler |
| No logs appear in file after benchmark | Appender filter, sink error, or dropped events | Inspect the pipeline and backend state |
| Comparing CPU% across different machines | Different core counts/capacities, different loads | Use CPU time and a fixed host |
| Fewer logs make the app faster | Observability/retention requirements were altered | Report delivered events and log quality targets |

## 15. Evidence-Based Ways to Reduce Overhead

### Reduce Unnecessary Work at the Call-Site

- Use appropriate log levels; do not enable DEBUG/TRACE broadly when only INFO or WARN is needed.
- When building expensive messages, check the level or use an appropriate supplier/lazy API. Remember Java still evaluates arguments passed as ordinary expressions.
- Avoid excessive logging inside hot loops; consider aggregating/metrics for high-frequency events while keeping detailed logs where needed for investigation.
- Do not call `toString()` on large objects just "to be safe". With structured logging, select meaningful fields instead of serializing the entire object.
- Limit stack traces where they are truly unnecessary; keep causes/stacks for critical errors.

### Optimize Formatters and Output

- Choose encoders/patterns/JSON fields that are sufficient; be cautious with location/caller data, which can be expensive.
- Measure the cost of MDC/trace context and fields copied for async events.
- Use buffering/batching when appropriate; understand the trade-off between delivery lag to the backend and data loss if the process crashes.
- Consider an async appender when the sink slows down requests, but configure a bounded queue, full-queue policy, and shutdown drain.
- Set up rotation/retention and monitor file/collector errors so I/O costs do not grow unchecked.
- For high-volume access logs, avoid logging sensitive bodies/headers; use route templates and required fields.

### Do Not Sacrifice Investigability

Optimization should not mean "turn off all WARN/ERROR" or silently drop logs when queues fill up. The goal is to **meet latency/CPU budgets with sufficient operational data**. When tightening filters, document which log classes are excluded and the conditions to re-enable them, ensuring complementary metrics/traces are in place so you do not blind system observability.

## 16. A Verifiable Overhead Measurement Report Template

A report should record:

| Item | What to fill in |
| --- | --- |
| Objective | Example: impact of DEBUG in `com.example.payment` |
| System | JDK 17/21, logging backend/version, heap/GC, CPU, OS/container |
| Workload | Endpoints and request ratios, concurrency, arrival rate, payload |
| Log configuration | Level, message mix, encoder, sink, queue/discard/flush |
| Baseline | OFF/INFO results under the same load |
| Results | Call-site latency, CPU, allocation, p95/p99, throughput |
| Reliability | Run count, variance, failed requests/timeouts |
| Delivery | Attempted/enqueued/written/dropped, backlog, lag |
| Conclusion | Observed cost, evidence-backed cost sources, limitations |
| Decision | Keep INFO, time-box DEBUG, optimize formatter, or change sink |

Example of a controlled conclusion:

> "Under the same test load, enabling DEBUG for the payment package reduced throughput by about 8% and increased p95 by 2 ms. CPU increased by 13 percentage points. No logs were dropped within the checked measurement window. JFR showed that the allocation increase was linked to payload formatting. The test needs to be repeated under high load and behavior verified with a slow sink before long-term adoption."

If you have not run JFR or counted dropped events, **do not write** those statements as facts. The template above only illustrates how to report once sufficient evidence has been gathered.

## 17. Checklist Before Concluding About Logging Overhead

- [ ] Clearly stated whether measuring **call-site**, **event processing**, **sink**, or **end-to-end delivery**, without mixing them.
- [ ] Recorded the exact framework/backend and configuration of levels, filters, encoders, and async policies.
- [ ] Baseline and treatment ran with the same workload, same resources, warmup, and multiple runs.
- [ ] Checked eager vs. lazy message evaluation, without missing argument evaluation costs.
- [ ] Measured CPU/allocations/GC in addition to elapsed wall time.
- [ ] Measured application latency (p50/p95/p99), throughput, and error rate with logging enabled.
- [ ] For async, observed queue depth, enqueue wait, consumer lag, and dropped events.
- [ ] For real sinks, also measured file/stdout/network throughput, write errors, and flush policies.
- [ ] Separated *attempted*, *accepted*, and *delivered* events; did not equate enqueueing with durability.
- [ ] Tested high load, log bursts, slow sinks, and shutdown to observe worst-case behavior.
- [ ] Results include units, run counts, dispersion, and limitations, without overclaiming.
- [ ] Optimizations preserve critical logs and avoid logging sensitive data.

**Remember:** good logging overhead measurement must answer two separate questions: **how many additional application resources does logging consume** and **which log events actually reach their destination**. A low `ns/op` number while the queue is full or logs are dropped is not enough to prove the logging system is operating well.

### References

- [Java 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html)
- [OpenJDK JMH](https://github.com/openjdk/jmh)
- [Java Flight Recorder (JFR)](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder.html)
- [Logback performance](https://logback.qos.ch/performance.html)
- [Apache Log4j2 performance](https://logging.apache.org/log4j/2.x/manual/performance.html)
