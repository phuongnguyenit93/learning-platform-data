# Appender Throughput in Java Logging

## 1. What is Appender Throughput?

An **appender** is the component of a logging backend that receives a log event and forwards it to a destination such as the console, a file, the network, or a collector. **Appender throughput** is the rate of events an appender can process over a period of time, typically expressed in **events/second** or **bytes/second**.

In a Java system using SLF4J with Logback or Log4j 2, a `logger.info(...)` call may pass through a logger, filters, and an encoder/layout before reaching the appender. The output path can be synchronous on the application thread or asynchronous via a queue/ring buffer.

~~~text
Application threads
        |
        v
logger.info/debug/error(...)
        |
        v
    Logger + filter
        |
        v
  Async queue (if any)
        |
        v
 Appender + layout/encoder
        |
        +---> stdout / console
        +---> file / disk
        +---> network / collector
~~~

If an appender writes 6,000 events/second, with each event averaging 500 bytes, the output data throughput is approximately 3,000,000 bytes/second (3 MB/s in decimal). This figure does not include additional bytes from protocols, metadata, network headers, or extra formatting.

**Key point:** appender throughput is the processing rate at **the point being measured**. A fast return from `logger.info(...)` does not by itself prove that the log was successfully written at the destination. When using async logging, the method can return immediately after enqueuing, while the worker has not yet written a single event.

## 2. Throughput Figures That Must Not Be Conflated

| Metric | Measurement Point | What It Does Not Establish |
| --- | --- | --- |
| Producer call rate | Number of times the application calls the logger per second | How many events pass the level/filter checks? |
| Accepted/enqueued rate | Number of events accepted into the logging system's queue per second | Has the appender processed them or the sink written them? |
| Appender processed rate | Number of events the appender finishes processing per second | Is the data durable or confirmed by the collector? |
| Sink confirmed rate | Number of events confirmed by the destination system according to its protocol | Under what guarantees can they be read back or recovered after a failure? |
| Output bandwidth | Number of bytes encoded/written/transferred per second | How many events and what is their size distribution? |

For example: the root logger only enables WARN, yet the code calls `logger.debug(...)` 500,000 times/second. Most of those calls may be discarded before constructing a full event. You cannot call 500,000 the throughput of `FileAppender`.

Conversely, `AsyncAppender` can accept 100,000 events in a short burst while the underlying `FileAppender` can only write 10,000 events/second. The remaining events sit in the queue; if this condition persists, the queue will fill up. You need to count created, accepted, processed, dropped, and sink-confirmed events.

## 3. Peak Throughput vs. Sustainable Throughput

**Peak/burst throughput** is the highest rate observed within a short window. **Sustainable throughput** is the rate that can be maintained long enough without the backlog growing uncontrollably, while keeping latency and resource usage within desired thresholds and meeting the zero-log-loss policy.

A result like "1 million events/second" might only measure the rate of **pushing into RAM**, not the sustainable write rate. Async configurations are especially good at absorbing bursts thanks to their queues, but under sustained load higher than the destination's capacity, that advantage runs out.

To interpret throughput, always describe:

- Backend and version: JUL, Logback Classic, Log4j 2 Core, and related bridges/bindings.
- Appender type: console, `FileAppender`, `RollingFileAppender`, network, `AsyncAppender`, or custom destination.
- Payload: short single-line text, JSON, MDC/ThreadContext, stack trace, Unicode size.
- Number of producer threads, number of workers, number of output destinations, and fan-out configuration.
- Measurement window, JVM warm-up, CPU quota, memory, disk/network, and collector load.
- Queue-full policy, flush timing, and the exact definition of "written."

Do not compare benchmarks that only measure the Logger API against benchmarks that write to a file and `fsync` as if they were measuring the same operation.

## 4. Basic Formulas and Metrics

Use monotonically increasing counters at each stage. Given two timestamps t0 and t1 with a window length of Δt seconds:

~~~text
produced_rate  = (produced[t1]  - produced[t0])  / Δt
accepted_rate  = (accepted[t1]  - accepted[t0])  / Δt
processed_rate = (processed[t1] - processed[t0]) / Δt
discarded_rate = (discarded[t1] - discarded[t0]) / Δt

output_bytes_per_second = (bytes[t1] - bytes[t0]) / Δt
average_bytes_per_event = Δbytes / Δprocessed
~~~

For example, 60,000 events processed by an appender in 10 seconds means an average processed rate of 6,000 events/s. If 30,000,000 bytes are encoded in the same period, the data throughput is 3,000,000 bytes/s, which is not necessarily the actual disk bandwidth.

Notes when placing counters:

1. **Produced** should reflect requested events, which may include events dropped by level/filter.
2. **Accepted** increments only when enqueued or when the pipeline actually accepts the event.
3. **Processed** must have a clear measurement point, e.g., when the appender has completed publishing/appending according to its implementation.
4. **Confirmed** increments only when the destination provides a defined, meaningful acknowledgment; do not infer `fsync` or durability simply from calling `write()`.
5. **Dropped** must count events discarded due to queue/filter/sampling if policy requires monitoring; do not lump all causes into a single number and conclude the queue is full.

To understand **latency**, separately measure the logger call duration on the caller thread and the time from event creation to destination receipt. High throughput does not imply low p95/p99 latency.

## 5. Queues Determine Burst Tolerance, Not Additional Sink Capacity

Let:

- λ = rate of events **actually enqueued** into the queue (events/s).
- μ = rate at which workers drain/complete events to reduce the backlog (events/s).
- C = queue capacity (events).
- Q0 = initial number of pending events.

If rates are roughly steady and λ is greater than μ:

~~~text
Q(t) ≈ Q0 + (λ - μ) × t
t_full ≈ (C - Q0) / (λ - μ)
~~~

For example, with C = 12,000, Q0 = 0, λ = 9,000/s, and μ = 6,000/s, the queue can fill up in about 4 seconds. Increasing C to 24,000 only extends this to about 8 seconds if the bottleneck remains unchanged. This is an approximate model and does not account for load variance, drops, per-event cost, or producer blocking.

When the queue is full:

- **Block/backpressure:** the caller waits for space, which can increase request latency and cause timeouts.
- **Discard/drop:** events are dropped according to policy; accepted or processed numbers may look good because part of the logs were lost.
- **Fallback:** writes synchronously or routes to another appender depending on framework capabilities; still incurs cost and error risk.
- **Timeout/reject:** the enqueue operation is rejected after a wait timeout.

Therefore, to know whether an appender keeps up with load, look at the **backlog slope** under steady load: if the queue keeps growing over time, accepted input exceeds drain capacity. A nearly empty queue under light load also does not prove the appender has high maximum throughput.

## 6. Bottlenecks That Reduce Throughput

### 6.1. Output Sink and I/O

- **Console/stdout:** can be throttled by container pipes, terminals, collection agents, or the runtime. Printing to the console on every event in a benchmark can cause severe distortion.
- **File:** disk throughput, filesystem, file locking, file rotation, buffering, flush, quota, and data size all have an impact.
- **Network/collector:** RTT, TLS, bandwidth, connection count, retries, indexing speed, and the remote service's ingestion capacity affect final throughput.
- **Database or custom sink:** one transaction per event has a very different cost from batching or a durable queue. Batching improves some transport paths but increases latency and error-handling complexity.

Writing to the OS page cache, flushing a stream, `fsync`ing to the device, and receiving a durable ACK from another system are **different confirmation boundaries**. Do not use a high number at the first boundary to promise durability at the last boundary.

### 6.2. Layout, Encoding, and Event Size

An appender can spend significant CPU just formatting messages, timestamps, JSON, MDC/ThreadContext, stack traces, or caller class/file/line info. An ERROR event with a long stack trace is very different from an 80-byte INFO event.

With SLF4J, code commonly uses parameterization:

~~~java
// Illustrative snippet inside a class that has declared the log field (SLF4J).
log.debug("Order {} state {}", orderId, state);
~~~

This avoids explicit string concatenation when the level is disabled, but expensive arguments are still evaluated before being passed to the method. When there is a real cost, you can guard it beforehand:

~~~java
// buildDiagnosticState() is an application method, not part of SLF4J.
if (log.isDebugEnabled()) {
    log.debug("State: {}", buildDiagnosticState());
}
~~~

Avoid putting large objects or sensitive data into logs; avoid capturing caller location when unnecessary because walking stack frames can be expensive. When comparing benchmarks, keep the pattern/JSON layout and message size equivalent.

### 6.3. Contention, CPU, GC, and Thread Count

If multiple producers write concurrently to a synchronous appender or a lock-based queue, contention can limit throughput. With async logging, workers still need CPU and memory and can compete with business logic for resources. Allocations of events, `String`s, `byte[]`s, and exceptions increase GC pressure.

Adding worker threads does not automatically increase speed when all workers write to a single file or collector with the same bandwidth limit. Profile CPU, blocking time, GC, disk, and network to find the bottleneck before increasing thread count.

### 6.4. Multiple Appenders and Additivity

A single event may be sent to console, file, and a remote sink. With synchronous appenders, one slow destination can prolong the logger call duration. With multiple async output paths, each destination has its own backlog/latency; FILE throughput does not by itself prove that REMOTE has saved the event.

If a child logger and parent logger attach the same appender while **additivity=true**, events can be written multiple times, unintentionally inflating events/s and cost. Check routing before optimizing.

## 7. Standalone Java 17+ Example: Measuring a Handler's Rate

In Java Core, `java.util.logging` (**JUL**) uses a **Handler** to process and output logs; it is conceptually equivalent to an appender in other frameworks. This example measures the cost of going through the logger, building UTF-8 content, and updating counters on an **in-memory Handler**—never treat these measurements as production file/network throughput.

Create **AppenderRateDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.concurrent.atomic.LongAdder;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class AppenderRateDemo {
    static final class MeteredHandler extends Handler {
        private final LongAdder written = new LongAdder();
        private final LongAdder utf8Bytes = new LongAdder();

        MeteredHandler() {
            setLevel(Level.ALL);
        }

        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) {
                return;
            }

            String line = record.getLevel().getName() + " "
                    + record.getMessage() + "\n";
            utf8Bytes.add(line.getBytes(StandardCharsets.UTF_8).length);
            written.increment();
        }

        @Override public void flush() {}
        @Override public void close() {}

        // Only reset when no thread is currently calling publish().
        void resetMetrics() {
            written.reset();
            utf8Bytes.reset();
        }

        long count() { return written.sum(); }
        long bytes() { return utf8Bytes.sum(); }
    }

    public static void main(String[] args) {
        Logger log = Logger.getLogger("demo.throughput");
        log.setLevel(Level.INFO);
        log.setUseParentHandlers(false);

        MeteredHandler handler = new MeteredHandler();
        log.addHandler(handler);
        try {
            // Warm up JIT/JVM before the main measurement run.
            for (int i = 0; i < 10_000; i++) {
                log.info("warmup");
            }
            handler.resetMetrics();

            int attempted = 50_000;
            long start = System.nanoTime();
            for (int i = 0; i < attempted; i++) {
                log.info("event-" + i);
            }
            long elapsed = System.nanoTime() - start;

            long processed = handler.count();
            double seconds = elapsed / 1_000_000_000.0;

            System.out.println("attempted=" + attempted);
            System.out.println("processed=" + processed);
            System.out.println("matches=" + (processed == attempted));
            System.out.println("utf8Bytes=" + handler.bytes());
            System.out.printf(Locale.ROOT,
                    "rate=%.0f events/sec%n", processed / seconds);
        } finally {
            log.removeHandler(handler);
            handler.close();
        }
    }
}
~~~

Compile/run with JDK 17 or later:

~~~bash
javac AppenderRateDemo.java
java AppenderRateDemo
~~~

The first four output lines are deterministic for the code above:

~~~text
attempted=50000
processed=50000
matches=true
utf8Bytes=838890
~~~

The fifth line has the form **rate=... events/sec**, depending on CPU, JIT, GC, and environment. A run might produce:

~~~text
rate=2541089 events/sec
~~~

**Do not use this sample rate as a production benchmark.** The handler above **does not write data to disk or network**; `processed` means `publish()` computed the bytes and incremented the counter. Setting `setUseParentHandlers(false)` avoids sending every event to the root console. `LongAdder` supports concurrent updates, but `resetMetrics()` is only safe when no thread is actively writing, as in this single-producer example.

`System.nanoTime()` is used to measure elapsed time. The 10,000-event warm-up is excluded from the measurement run, but this is still a **one-shot, single-thread, in-memory test**, not a statistical benchmark. To test the real throughput of a `FileAppender`, replace the destination with a real sink, measure bytes/events reaching the sink, I/O errors, flush behavior, and wait times, and run multiple iterations on production-like infrastructure.

## 8. Logback AsyncAppender and the Throughput Problem

Logback Classic is commonly used via SLF4J. An **AsyncAppender** has a queue and a worker that forwards events from the queue to a real appender such as `RollingFileAppender`. Example **logback.xml**:

~~~xml
<configuration>
  <appender name="FILE"
            class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>logs/application.log</file>
    <rollingPolicy
        class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
      <fileNamePattern>logs/application.%d{yyyy-MM-dd}.log</fileNamePattern>
      <maxHistory>7</maxHistory>
    </rollingPolicy>
    <encoder>
      <charset>UTF-8</charset>
      <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
    </encoder>
  </appender>

  <appender name="ASYNC" class="ch.qos.logback.classic.AsyncAppender">
    <queueSize>8192</queueSize>
    <discardingThreshold>0</discardingThreshold>
    <neverBlock>false</neverBlock>
    <maxFlushTime>10000</maxFlushTime>
    <appender-ref ref="FILE"/>
  </appender>

  <root level="INFO">
    <appender-ref ref="ASYNC"/>
  </root>
</configuration>
~~~

Meaning in measurements:

| Parameter | Impact |
| --- | --- |
| `queueSize` | Backlog/burst capacity; increasing the queue does not by itself make `FILE` write faster |
| `discardingThreshold` | Remaining space threshold at which low-level logs start being dropped; `0` disables early discarding |
| `neverBlock=false` | A full queue can block the caller instead of simply dropping events |
| `maxFlushTime` | Time limit to wait for the worker to drain the queue on shutdown; does not increase sustainable write speed |
| `FILE` + encoder | Where actual formatting/file I/O resources are consumed |

According to Logback documentation, by default `AsyncAppender` may drop TRACE, DEBUG, and INFO events when the queue reaches about 20% remaining capacity. If you measure throughput and notice event counts do not match, do not only check whether the queue hit 100%; events may have been dropped earlier. Conversely, setting `discardingThreshold=0` and `neverBlock=false` can increase caller latency when the sink cannot keep up.

The XML example requires the Logback dependency, write permissions for the `logs` directory, an appropriate retention policy, and proper shutdown handling. For audit logs that require durability, an in-memory `AsyncAppender` is not a reliable sole storage mechanism.

## 9. Log4j 2: Async Appender vs. Async Logger

Log4j 2 Core provides:

- **Async Appender:** wraps a target appender using its own queue and worker; incurs contention overhead under many producers.
- **Async Logger:** based on LMAX Disruptor/ring buffer at the logger layer; can achieve different performance characteristics depending on the workload.

Example **log4j2.xml** using Async Appender:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
  <Appenders>
    <File name="FILE" fileName="logs/application.log">
      <PatternLayout pattern="%d{ISO8601} %-5p %c - %m%n"/>
    </File>
    <Async name="ASYNC" bufferSize="8192"
           blocking="true" shutdownTimeout="10000">
      <AppenderRef ref="FILE"/>
    </Async>
  </Appenders>
  <Loggers>
    <Root level="info">
      <AppenderRef ref="ASYNC"/>
    </Root>
  </Loggers>
</Configuration>
~~~

In Log4j 2, **bufferSize** is the queue capacity of the Async Appender. The queue-full policy depends on configuration and **log4j2.asyncQueueFullPolicy**; `Default` typically favors waiting, while `Discard` can drop events based on **log4j2.discardThreshold**. Do not read Logback settings like `neverBlock`/`discardingThreshold` and apply them directly to Log4j 2.

Log4j 2 notes that async logging is useful during bursts and when you want to shorten logger call duration on application threads. However, if the sustained logging rate exceeds the target appender, the queue fills up and the latency reduction disappears. The backend also recommends measuring on the actual application to choose between sync and async.

**Do not stack an Async Appender on top of an Async Logger just to get higher events/s numbers.** Two queues can increase memory usage, latency, and troubleshooting difficulty, while the file/network sink remains the limiting factor. If you must combine them, measure state and completion at each layer.

## 10. Comparing Synchronous vs. Asynchronous Logging

| Aspect | Synchronous | Asynchronous |
| --- | --- | --- |
| Logger call latency | May incur encoding/I/O directly | Usually mostly event creation/enqueuing |
| Short burst handling | Can slow down callers immediately | Queue can absorb part of the burst |
| Sustainable throughput to sink | Limited by sink and overhead | Still limited by sink; overhead may differ |
| Sustained overload | Callers slow down with the sink | Backlog grows, then blocks/drops/falls back |
| Sink error detection | Closer to the calling thread in some backends | May surface later on the worker |
| Shutdown/crash | Need to understand buffering/flushing | Need to drain the in-RAM queue before stopping |

A fair benchmark must hold constant the **payload, logger level, encoder, disk/network, CPU quota, producer count, duration, and queue-full policy**. Comparing `logger.info` latency with sink throughput is comparing two different measurements.

## 11. Designing a Proper Benchmark

### 11.1. Ask a Specific Question

For example: "With 8 business threads and JSON logs averaging 800 bytes each, how many events/s can the FILE appender sustainably write without drops, without unbounded backlog growth, and while keeping request p99 latency within threshold?"

Specify clearly whether "written" means `append()` returned, the file is readable, `fsync` completed, or the collector acknowledged. These confirmation levels differ. Only set a target number if it serves a real SLO.

### 11.2. Create a Representative Workload

- Test INFO, WARN, and ERROR levels; short/long messages; stack traces; JSON; Unicode; and MDC.
- Test 1, 4, 8, and 16 producer threads; keep event generation rules consistent.
- Enable/disable caller location only when requirements are clear and its impact is measured.
- Warm up the JVM/JIT and sink; run multiple sufficiently long iterations; report results with variance (median, percentiles) rather than one lucky number.
- Separate **logger/layout microbenchmarks** from **file/network integration benchmarks**. Use JMH for microbenchmarks when rigorous evaluation is needed, and end-to-end load tests to verify the real destination.
- Attach `testRunId` and sequence numbers, wait for queue drain/flush, and reconcile events that reached the sink. When collector indexing is slow, do not jump to the conclusion that logs were lost.
- Keep infrastructure constant: backend version, CPU limits, heap, disk, rotation, network, collector, and container environment.

### 11.3. Track Speed, Quality, and Resources

| Metric | Why It Is Needed |
| --- | --- |
| Producer/accepted/processed events/s | Know throughput at each stage |
| Output bytes/s | Distinguish event rate from message size |
| Queue size / capacity / oldest age | Know whether the backlog is growing |
| Dropped / rejected / appender errors | Detect log loss, filtering, or I/O errors |
| Caller latency p50/p95/p99 | Measure impact on business logic |
| End-to-end lag to sink | Measure log observability delay |
| CPU, heap, allocations, GC pauses | Find compute and allocation bottlenecks |
| Disk/network throughput, flush/ACK | Find infrastructure bottlenecks |
| Drain time on shutdown | Know whether the queue can drain before stopping |

Do not use `COUNT(*)` across all logs when retries, duplicates, sampling, or collector lag exist to infer the number of unique events written. Reconcile by event ID/test ID and clearly define intentional exclusions.

## 12. Finding Sustainable Throughput via Load Testing

A reproducible process:

1. **Baseline:** run at low load with the queue nearly empty; verify logs have the right format and count.
2. **Step up:** increase producer rate or thread count in clear steps, holding each step long enough.
3. **Observe backlog:** if queue size grows continuously, accepted input exceeds drain rate at that load level.
4. **Check SLOs:** are drop rate, sink errors, p99 latency, CPU/GC, and end-to-end lag within thresholds?
5. **Take the last passing step:** that is an estimate of sustainable throughput under test conditions, not an immutable constant of the framework.
6. **Test burst and recovery:** create a short spike, then reduce load; measure how long the queue takes to return to normal.
7. **Test hard scenarios:** file rotation, slow collector, nearly full disk, network timeouts, graceful shutdown/restart.

If you only run a loop writing 50,000 events in one second and stop, you may accidentally measure only enqueue or cache speed. Sustained load is what reveals the limits of the appender and sink.

## 13. Optimizing Throughput by Root Cause

### 13.1. Reduce Unnecessary Events

Choose logger levels per package, avoid duplicate logs and logging inside hot loops; consider sampling/rate limiting for diagnostic events that may be dropped. For audit, payment, or mandatory-retention logs, **do not use sampling or in-RAM queue logging as a durability guarantee**.

### 13.2. Reduce Per-Event Cost

Simplify the layout where possible; avoid repeated stack traces, unnecessary caller file/line info, and oversized payloads. Prefer structured logging for queryable attributes, but measure the actual encoder in use. Do not log tokens, passwords, or unnecessary personal data when testing throughput.

### 13.3. Increase Sink Capacity

If disk is saturated, optimize the write path, device, and rotation. If the collector is limited by ACKs or network, increase ingestion capacity or use buffering/batching within realistic limits, testing retries and durability. If encoding CPU is the bottleneck, optimize the formatter and resources. Do not blindly add workers when all of them share one slow destination.

### 13.4. Choose Async for the Right Cases

Use async when you need to reduce caller latency or absorb bursts and have evaluated the queue-full policy. Increasing the queue to handle short spikes can make sense, but it increases memory usage, log output delay, and flush time. If input exceeds sink capacity long-term, the solution is to reduce input, increase destination capacity, or accept an explicit block/drop policy.

## 14. Common Misconceptions

**"Fast `logger.info` calls mean the appender is fast."** With async, the call may only enqueue. Measure the consumer and sink.

**"A larger queue gives higher sustainable throughput."** A queue buys extra burst tolerance; it does not speed up file or network I/O.

**"No errors means no logs were lost."** Events may be dropped by level/filter, queue-full policy, collector failures, or unflushed buffers. Some frameworks also do not expose a dropped counter out of the box.

**"Adding worker threads always increases throughput."** If a single file or collector is the bottleneck, adding threads can increase contention and overhead.

**"Every event has the same cost."** Large stack traces/JSON have very different bytes/s and encoding CPU compared to small text logs.

**"Enqueued logs are safely stored."** Events in RAM can still be lost if the process crashes, the queue has not drained, or the sink fails. For mandatory durable audits, use a store/transaction/outbox or a dedicated mechanism with matching guarantees.

**"Dashboard row count equals actual event count."** Ingest delay, retries, duplicates, multiline logs, filters, and query windows can skew counts. Use event identifiers to reconcile.

**"A benchmark on one dev machine is enough to pick production config."** CPU quota, disk, collector, network, rotation, and competing load in production differ significantly. Measure in a realistic environment.

## 15. Acceptance Checklist for an Appender Measurement

- [ ] Clearly identified **throughput at logger, queue, appender, or sink**.
- [ ] Included both events/s, bytes/s, and payload size distribution.
- [ ] Verified logger level/filters so dropped events are not miscounted.
- [ ] Measured caller latency, end-to-end lag, CPU/GC, and queue backlog.
- [ ] Documented backend/version, appender, encoder, queue-full policy, and shutdown time.
- [ ] Tested bursts, sustained load, multiple producers, large payloads, rotation, and slow sinks.
- [ ] Reconciled `testRunId`/sequence ID at the destination after drain/flush.
- [ ] Did not use enqueue throughput to promise durable data storage.
- [ ] Identified bottlenecks via metrics/profiling before changing thread counts or queue sizes.
- [ ] Separated mandatory-retention logs from unsuitable discard/sampling policies.

**Remember:** Appender throughput is the **log processing rate at a defined stage**. To optimize Java logging performance responsibly, measure producer rate, appender drain capacity, sink completion, backlog, latency, and event loss rate. Async buffers help ride out bursts; long-term sustainable write capacity depends on the actual processing pipeline and destination.

## References

- [Apache Log4j 2 — Performance](https://logging.apache.org/log4j/2.x/manual/performance.html): layout cost, location information, allocation, and async.
- [Apache Log4j 2 — Asynchronous Loggers](https://logging.apache.org/log4j/2.x/manual/async.html): bursts, sustainable throughput, queue-full policy, and wait strategies.
- [Apache Log4j 2 — Delegating Appenders](https://logging.apache.org/log4j/2.x/manual/appenders/delegating.html): Async Appender, blocking queues, and fallback.
- [Logback Manual — AsyncAppender](https://logback.qos.ch/manual/appenders-async-sift.html): `queueSize`, `discardingThreshold`, `neverBlock`, and `maxFlushTime`.
- [Oracle Java SE 17 — java.util.logging.Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html): processing `LogRecord` with `Handler`.
- [OpenJDK JMH project](https://github.com/openjdk/jmh): Java microbenchmarking tool; use alongside real load tests.
