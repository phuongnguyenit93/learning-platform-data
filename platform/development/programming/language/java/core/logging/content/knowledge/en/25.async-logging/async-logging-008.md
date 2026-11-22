# Async Logging Latency in Java Core Logging

## Learning Objectives

This lesson belongs to the **Asynchronous Logging** group. After completing it, you will be able to:

- Distinguish between **the latency of a log call** and **the latency from event occurrence until the log is written, shipped, or searchable**.
- Describe the roles of queues, background worker threads, output devices, log collectors, and indexing systems in logging latency.
- Explain why async logging typically reduces business thread blocking time, yet does not guarantee that logs appear earlier or are never lost.
- Measure p50/p95/p99 latency, queue depth, blocked enqueue time, throughput, and dropped log counts; choose appropriate backpressure policies.
- Configure, test, and troubleshoot async logging latency in Java 17+ with libraries such as Logback and Log4j 2.

There is no single "async logging latency" figure for every system. You must define **from where to where you are measuring**, what the load is, what the log retention requirements are, and whether the output is a file, console, or network.

## 1. Async Logging Shifts Where the Application Waits

With synchronous logging, a log call typically performs most of the appender's work directly on the business thread: creating the event, formatting it, and writing it to the output according to the appender's mechanism. The call can slow down when I/O or locks are slow.

With asynchronous logging, the business thread typically creates/captures the log event and places it into a **queue or ring buffer**. One or more workers then take the event to encode and forward it to the appender/sink. The business thread can return early, but the log **is not necessarily written yet** when the logging method returns.

```text
SYNC:
Business thread -> log event -> format/write sink -> return to business

ASYNC:
Business thread -> capture event -> enqueue -> return to business
                                      |
                                      v
                              background worker
                                      |
                                format / write
                                      |
                              file / stdout / network
                                      |
                                collector / index
```

Key distinctions:

- **Reduces caller latency:** calling `logger.info(...)` usually does not have to wait for the sink to complete each event, provided the queue has space and producer-side processing is lightweight.
- **Does not guarantee lower end-to-end latency:** logs may sit in the queue for a long time, wait on I/O, wait to be shipped, or wait to be indexed; under overload, the producer can still be blocked.
- **Does not mean durable:** a successful enqueue usually only means the event has been accepted into memory. A process crash, an incomplete shutdown, or a sink/collector failure can lose unprocessed logs.

Some frameworks distinguish between **AsyncAppender** (offloading calls to another appender onto a worker) and **AsyncLogger** (a dedicated async pipeline design, such as Log4j 2's Disruptor). Both approaches have queues and overload mechanisms; their configuration and cost characteristics vary by implementation.

## 2. Latency Types That Must Be Measured with Clear Boundaries

A log event passes through multiple milestones:

```text
t0                    t1               t2                  t3             t4           t5
| logger call begins | producer returns | worker picks event | sink completed | collector ack | searchable
       ^-- caller --^
       ^----------- dispatch/pickup -----------^
       ^---------------- appender path --------------------^
       ^---------------------- end-to-end visibility --------------------------^
```

Notation:

| Metric | Measurement Boundary | Meaning |
| --- | --- | --- |
| **Caller latency / enqueue latency** | `t1 - t0` | Time the logging call holds the business thread; includes capture, preprocessing, enqueueing, and time blocked when the queue is full. |
| **Time to pickup** | `t2 - t0` | From the start of the log call until the worker receives the event; includes both the time the producer may wait for space and the time spent in the queue. |
| **Queue residence time** | From when the event **actually enters the queue** until the worker takes it | Reflects backlog in the queue, distinct from the total time the producer waited to enqueue. Requires appropriate instrumentation to mark the exact timestamp. |
| **Sink processing latency** | `t3 - t2` | Time the worker spends processing/formatting/writing to the sink; depends on I/O, locks, and batching. |
| **Collector/index latency** | `t5 - t3`, if applicable | Time to ship, ingest, and index so the log becomes queryable. |
| **End-to-end visibility latency** | `t5 - t0` | How long operators must wait from the event occurring until the log can be found. |

The "write completed" milestone also needs a clear definition. `FileOutputStream.write` or an appender completing may only have transferred bytes to the OS cache, **not necessarily fsynced to disk**. A successful network send also does not prove the collector has durably stored/indexed the event. If the goal is **data durability**, you must define the durability confirmation milestone separately; do not treat the time the logger returns as the durable time.

Within the same JVM, use `System.nanoTime()` to measure **elapsed time**. Use wall-clock timestamps such as `Instant.now()` to correlate events with the log pipeline; when comparing timestamps across multiple machines, account for clock skew, time synchronization, timestamps generated by agents/collectors, and batching variance.

An inequality that generally holds for the same event is: the sink completion time cannot precede the time the worker picked up the event. However, the time the caller finishes and the time the worker starts can interleave: the worker may pick up the event right before the producer thread executes the next instruction after `offer/put`.

## 3. What Makes Async Logging Slow?

### 3.1. Cost on the Producer Thread

Even with async logging, the producer may still have to check the log level, evaluate Java arguments, create the event, capture the timestamp/thread name/MDC, determine stack trace/caller data, and publish to the queue. For example:

```java
logger.debug("result=" + expensiveComputation());
```

The expression `expensiveComputation()` is evaluated by Java before calling the logger, even when the DEBUG level is disabled. Parameterized logging such as `logger.debug("result={}", value)` avoids eager string concatenation, but the passed-in value still has to be computed. If the computation is very expensive, check `logger.isDebugEnabled()` or use a lazy supplier mechanism if the framework supports it for that purpose. Async logging does not eliminate the cost of generating log data.

Capturing large stack traces, serializing heavy objects, copying MDC, or capturing caller location makes the producer slower than expected; how much of that cost falls on the producer versus the worker depends on the logging framework and configuration.

### 3.2. Queue and Service Rate

Suppose the producer generates an average of **λ** log events/second, while the worker/sink processes an average of **μ** events/second.

- If `λ < μ` under steady load without large bursts, any backlog can drain.
- If `λ ≈ μ`, a short load spike or slow I/O can cause p99 queue wait time to spike sharply.
- If `λ > μ` for long enough, the queue grows up to its limit (if bounded). After that, the **block, drop, synchronous fallback, or reject** mechanism determines actual behavior, depending on the implementation.

As a hypothetical example, if the sink processes 4,000 events/s while the producer generates 5,000 events/s during a load spike, the backlog grows by roughly 1,000 events/s. An initially empty queue with a capacity of 2,000 events will fill up in about 2 seconds if those rates hold; this is a simplified model that does not account for bursts, variance, or overhead. Increasing the queue size only **delays the time until it fills up**; it does not fix the root cause if the consumption rate remains lower than the log generation rate over time.

Little's Law in steady state gives `L = λ × W`: `L` is the average number of events waiting/processing in the measured scope, `λ` is the effective throughput, and `W` is the average time spent in that scope. Do not apply it mechanically when the system is overflowing or when the numbers include dropped events. For example, if an average of 500 events are waiting in the queue and throughput is 1,000 events/s, the corresponding average wait time is about 0.5 seconds under steady-state conditions.

### 3.3. Causes of Long-Tail Latency

- **Slow sink:** writing to console in containers, files on network drives, fsync/flush, file rolling/rotation, disk saturation, congested stdout collectors, network timeouts, or a slow logging backend.
- **Bursts:** batches of requests/logs exceeding worker speed, especially debug logging inside loops or during cascading errors.
- **CPU/GC:** JSON encoding, exception formatting, object/byte-array allocations, GC pauses, or CPU contention preventing producer and worker threads from being scheduled smoothly.
- **Locks/coordination:** multiple producers competing to publish, a worker serialized at an appender, or contention on a shared appender.
- **Batching:** a sink grouping multiple logs to send at once improves throughput, but can increase the wait time of the last event in a batch or events during low traffic.
- **Downstream pipeline:** collector retries, agent backlogs, brokers, ingest pipelines, and index refreshes cause logs to be present in a file but not yet queryable.

**Async does not turn slow I/O into fast I/O.** It shifts when the cost is paid to the worker and absorbs bursts up to a limit. When log volume is excessive, only reducing unnecessary logging and increasing sink capacity can handle sustained load.

## 4. Backpressure: You Must Choose a Policy When the Queue Is Full

A bounded queue has a finite capacity, which helps cap memory usage. When it is full, common strategies include:

| Handling Strategy | Impact on Caller Latency | Impact on Logs |
| --- | --- | --- |
| **Block/`put` waiting for space** | Callers may wait a long time, even slowing down endpoints | Reduces the risk of losing events at the queue, but does not eliminate sink/shutdown loss. |
| **Drop new events** | Callers return quickly | Loses a portion of logs; requires alert counters and log-level policies. |
| **Drop less important events** | Preserves higher-priority logs, can reduce average latency | Accepts losing DEBUG/INFO; must not be assumed to store every event. |
| **Fallback to synchronous write** | Callers suddenly incur I/O, p99 can spike | Gives a chance to write immediately, though it can still fail if the sink errors. |
| **Reject/report error** | Callers see errors or must handle retries | Depending on the framework and policy, may affect business logic. |

There is no single right strategy for all applications. For debug logs or reproducible statistics, accepting controlled drops with metrics may be reasonable. For mandatory audit logs or business-critical events, standard logging with an in-memory queue does not provide durability guarantees; you must design a dedicated durable storage path according to requirements (transactional outbox, durable message broker, audit store, etc.) if truly needed.

**Operational warning:** A "never block" configuration reduces producer latency in some scenarios, at the cost of potentially losing events when full. A "never drop" configuration usually means the producer can block, and a process crash can still lose in-memory events. Always test the exact policy of the framework and version you are using.

## 5. Java 17 Example: Measuring Caller Latency and Background Processing Time

The pure-JDK program below simulates an async log pipeline with a bounded queue and a slow worker. It measures three durations per event:

- `callerNs`: from before `queue.put` until `put` returns; when the queue is full, it includes time waiting for space.
- `pickupNs`: from when the application starts emitting the event until the worker calls `take`; includes enqueue blocking **and** queue residence, so do not call this queue residence alone.
- `sinkDoneNs`: from event emission until after the worker finishes simulated processing; it does **not** represent the time for the log to reach an indexing system.

The program intentionally uses `Thread.sleep(4)` to simulate a slow sink and avoids `System.out.println` per event because printing to the console could skew the experiment. Timings will vary by OS/JVM, so only the count and check lines are treated as invariant output.

Create the file **`AsyncLoggingLatencyDemo.java`**:

```java
import java.util.Arrays;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.atomic.AtomicInteger;

public class AsyncLoggingLatencyDemo {
    private record Event(int id, long startedNs) {}

    private static long percentile(long[] sortedNs, int percent) {
        int rank = (int) Math.ceil(sortedNs.length * percent / 100.0);
        return sortedNs[Math.max(0, rank - 1)];
    }

    private static double milliseconds(long nanoseconds) {
        return nanoseconds / 1_000_000.0;
    }

    public static void main(String[] args) throws InterruptedException {
        final int total = 40;
        BlockingQueue<Event> queue = new ArrayBlockingQueue<>(8);
        long[] callerNs = new long[total];
        long[] pickupNs = new long[total];
        long[] sinkDoneNs = new long[total];
        AtomicInteger processed = new AtomicInteger();

        Thread worker = new Thread(() -> {
            try {
                for (int i = 0; i < total; i++) {
                    Event event = queue.take();
                    pickupNs[event.id()] =
                            System.nanoTime() - event.startedNs();

                    Thread.sleep(4); // simulate sink processing 1 event

                    sinkDoneNs[event.id()] =
                            System.nanoTime() - event.startedNs();
                    processed.incrementAndGet();
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "async-log-writer");

        worker.start();

        for (int i = 0; i < total; i++) {
            long startedNs = System.nanoTime();
            queue.put(new Event(i, startedNs));
            callerNs[i] = System.nanoTime() - startedNs;
        }

        worker.join();

        if (processed.get() != total) {
            throw new IllegalStateException("Worker did not drain queue");
        }

        Arrays.sort(callerNs);
        Arrays.sort(pickupNs);
        Arrays.sort(sinkDoneNs);

        System.out.println("processed=" + processed.get());
        System.out.println("queueEmpty=" + queue.isEmpty());
        System.out.println("samples=" + callerNs.length);

        System.out.printf("caller_p95_ms=%.3f%n",
                milliseconds(percentile(callerNs, 95)));
        System.out.printf("pickup_p95_ms=%.3f%n",
                milliseconds(percentile(pickupNs, 95)));
        System.out.printf("sink_done_p95_ms=%.3f%n",
                milliseconds(percentile(sinkDoneNs, 95)));
    }
}
```

Compile and run with **JDK 17+**:

```bash
javac AsyncLoggingLatencyDemo.java
java AsyncLoggingLatencyDemo
```

The first three lines of **stdout** are always:

```text
processed=40
queueEmpty=true
samples=40
```

The next three lines have the form `caller_p95_ms=...`, `pickup_p95_ms=...`, `sink_done_p95_ms=...` with actual measurements varying across runs; a fixed millisecond value cannot be given for those lines. `percentile` uses nearest-rank: sorting in ascending order and taking the element at position `ceil(p × N / 100)` (1-based), a simple estimation method suitable for illustration; production monitoring tools may use histograms or other quantile algorithms.

How to read the results:

1. While the queue has space, `put` usually completes quickly. When the sink is slow and the queue is full, many `put` calls may wait, driving up p95 caller latency.
2. `pickup_p95_ms` shows the latency from event emission until the worker receives it, including producer blocking. To measure **queue residence alone**, you need to record a timestamp at the exact moment the event is actually published into the queue, using concurrency-safe instrumentation.
3. `sink_done_p95_ms` also includes worker processing. It does not yet include the collector, log shipping, and indexing.
4. Increasing `Thread.sleep(4)` to `Thread.sleep(20)` typically increases backlog and caller blocking; measured results do not scale by a fixed ratio because OS scheduling and machine load vary.
5. Increasing queue capacity absorbs longer bursts, but does not make the worker process faster; when the sink is continuously too slow, backlog still builds up and memory usage increases.

This is a **standalone runnable simulation**, not a production logger. In practice, use the telemetry from your appender and log collection system to measure the corresponding pipeline. Do not turn the numbers from this example into latency targets.

## 6. Reading Percentiles Correctly

Because log events often have skewed distributions, averages can hide slow spikes. Track **p50, p95, and p99** for caller latency and end-to-end latency over the same time window, along with sample count and drop rate. For example:

| Metric | p50 | p95 | p99 | Hypothetical Meaning |
| --- | ---: | ---: | ---: | --- |
| `log_call_ms` | 0.04 ms | 0.2 ms | 18 ms | Most calls are fast, but the 1% tail hits blocking/GC/contended paths. |
| `pickup_delay_ms` | 2 ms | 80 ms | 900 ms | The worker experiences backlog at certain times. |
| `log_visibility_ms` | 150 ms | 1,400 ms | 8,000 ms | Shipping/indexing also contributes to observed latency. |

The numbers above are **illustrative examples only**, not a benchmark of Logback/Log4j 2 or a system guarantee. Measurement windows must be comparable for valid comparisons; p99 from a window with very few samples can fluctuate wildly. If a percentage of logs has been dropped, quantiles computed **only on the remaining events** can look artificially good; always report `dropped_count` and `drop_rate` alongside them.

**Do not sum the p99 of individual stages and call it the end-to-end p99.** Percentiles do not add linearly: the events causing the tail in each stage may be different. It is better to attach a timestamp or ID to measure end-to-end latency per event, or use telemetry with proper event correlation.

Set SLOs according to usage goals: for example, "log call p99 < 10 ms at target load, 99% of accepted logs appear within 5 seconds, drop rate < 0.01%". This is an example for designing measurements; appropriate values depend on log type, infrastructure cost, and criticality, not a universal threshold for Java.

## 7. Configuring Logback AsyncAppender in Java

For applications using **SLF4J + Logback**, `ch.qos.logback.classic.AsyncAppender` uses a bounded queue and a worker to forward events to a target appender. Example **`logback.xml`** configuration:

```xml
<configuration>
    <appender name="FILE" class="ch.qos.logback.core.FileAppender">
        <file>logs/app.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{ISO8601} [%thread] %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ASYNC" class="ch.qos.logback.classic.AsyncAppender">
        <queueSize>2048</queueSize>
        <discardingThreshold>0</discardingThreshold>
        <neverBlock>false</neverBlock>
        <includeCallerData>false</includeCallerData>
        <maxFlushTime>10000</maxFlushTime>
        <appender-ref ref="FILE"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="ASYNC"/>
    </root>
</configuration>
```

You must add compatible Logback/SLF4J dependencies to the application; the XML file above **does not run on the JDK alone**. The path `logs/app.log` must be writable. Meaning of the properties in Logback Classic:

- `queueSize=2048`: queue capacity in events, not bytes. Setting it too large increases memory usage and the wait time of events at the back of the backlog.
- `discardingThreshold=0`: disables AsyncAppender's mechanism for discarding lower-priority log levels based on remaining queue capacity. With the default configuration, Logback Classic may drop TRACE/DEBUG/INFO when the queue is nearly full (the threshold is typically around 20% remaining capacity). Verify the behavior of the version you are using.
- `neverBlock=false`: when unable to enqueue, the producer is allowed to wait rather than taking the non-blocking drop branch. This can increase endpoint p95/p99 when the sink is slow; it is not an end-to-end zero-loss guarantee.
- `includeCallerData=false`: avoids the cost of computing source location on the hot path. If you need the caller's class/method/line, enable it only after weighing the overhead and re-measuring.
- `maxFlushTime=10000`: on stop, AsyncAppender waits up to about 10 seconds for the worker to drain the queue; if the timeout expires or the process is killed earlier, unwritten events may remain. In Logback, a value of `0` typically means wait indefinitely on stop; the shutdown policy must align with operational goals.

In Logback, an event usually has to "prepare for deferred processing" before going to the worker: required information such as thread name and MDC is captured at the appropriate time, because the producer's context may no longer exist when the worker processes it. If caller data is needed, doing that on the producer can increase caller latency. Details vary across versions/frameworks; measure on your actual configuration.

To compare configurations:

1. Keep log volume, sink configuration, machine, format, and test duration identical.
2. Measure the sync baseline: throughput and p50/p95/p99 of both endpoints and log calls, plus CPU and disk usage.
3. Enable AsyncAppender; re-measure caller latency, queue depth, throughput, drops, and end-to-end visibility.
4. Generate a burst exceeding processing capacity; verify whether actual behavior is **block, discard, or fallback** as configured, and whether alerts fire when the queue is full.
5. Perform a graceful shutdown; verify queue draining within the time budget and reconcile emitted versus written event counts.

If the system writes to stdout in a container, an async appender only shifts the stdout write time to the worker; the stdout runtime, log agent, and downstream log backend can still be slow or lose data. Every benchmark must reflect the real log path.

## 8. Log4j 2 AsyncLogger and Disruptor

Log4j 2 provides an **AsyncLogger** mechanism using a ring buffer structure based on the LMAX Disruptor, alongside **AsyncAppender**. AsyncLogger and AsyncAppender are neither the same type of configuration nor identical in behavior across all versions. A ring buffer helps reduce some contention/publishing overhead under suitable conditions, but it still has finite capacity and requires a policy when the buffer is full.

Points to verify for your Log4j 2 version, configuration options, and deployment:

- Ring buffer size and actual memory footprint.
- Strategy (`wait`, `block`, synchronous write, or `discard`) when the buffer is full.
- Whether location/caller data is captured and its overhead on the producer.
- Behavior when the target appender is slow, when exceptions occur, and during shutdown.
- Real load, tail latency distribution, and log loss.

Do not conclude that "AsyncLogger is always faster than AsyncAppender" or copy configurations between the two frameworks without testing. If using global AsyncLogger or mixed sync/async configurations, check the Disruptor dependency and the corresponding context selector/configuration in the official documentation for the **Log4j 2 version you are running**. Only benchmark after confirming the framework initializes in the intended async mode.

## 9. Meaningful Measurement and Benchmarking

A trustworthy measurement must answer: **what is logged, at what load, through which sink, how much is lost, and what is the impact on business logic?**

### Recommended Metric Set

| Group | Suggested Metrics | Purpose |
| --- | --- | --- |
| Producer | `log_call_duration` p50/p95/p99, blocked enqueue duration | Detect when logging slows down business threads. |
| Queue | queue depth, capacity, high-water mark, occupancy %, wait time | Measure backlog and headroom before filling up. |
| Consumer/sink | events processed/s, sink write duration, bytes/s, errors/retries | Distinguish high producer log rate from slow sink processing. |
| Data integrity | emitted/accepted/written/dropped counts and drop rate | Know whether performance was achieved by keeping or dropping logs. |
| Pipeline | event-to-collector, event-to-searchable, ingest lag | Measure when operators can actually query the logs. |
| Runtime | CPU, GC pauses, allocation, I/O wait, file rotate, throttling | Find the root causes of tail latency. |

Actual metric names depend on the framework. If the framework does not expose queue depth/dropped count, use supported instrumentation mechanisms, MBeans/metrics appenders, or measure at the application/sink level. Avoid writing instrumentation that uses heavy locks or generates extra logs per event; monitoring itself has overhead.

### Test Scenarios

- **Steady state:** run load long enough to warm up the JIT, generate logs with realistic size/volume distributions, and measure latency and throughput.
- **Burst:** briefly spike log volume; measure queue high-water mark and recovery time.
- **Saturation:** sink processes slower than producer; measure block duration/drops and the effect on endpoint p99.
- **Failure/recovery:** simulate disk full, permission denied, unreachable collector, network retries, or file rotation; verify visibility/durability policies.
- **Shutdown/crash:** compare emitted events, remaining queue items, and events that actually reached the sink; graceful shutdown differs from force-kill.
- **Content mix:** small few-byte logs, long JSON, exception stack traces, MDC, and various log levels; measure allocation/CPU/GC.

Keep test conditions fair: equivalent log levels, event sizes, producer counts, queue/sink configurations, and machine resources. Use a profiler/metrics rather than relying solely on the speed of a `logger.info` loop; a benchmark measuring producer throughput can look high simply because it drops many events or leaves an undrained backlog at the end.

### Choosing Queue Size

Roughly estimate capacity from the number of events to absorb during a burst, the sink drain rate, and available memory. For example, a queue of 10,000 events where each event holds an average of 2 KiB of data corresponds to roughly 20 MiB **for the reference payload alone**; in practice, the heap also includes object headers, references, layout/message buffers, retained parameters, and the queue structure itself. Measure heap usage under real payloads.

The `burst arrival - consumer capacity` model is only a starting point. If low p99 visibility is required, an overly large queue can make events wait longer; to increase steady-state capacity, optimize the sink, cut unnecessary logs, batch/ship appropriately, or scale consumption capacity rather than just enlarging the queue.

## 10. Real-World Diagnostic Scenarios

**Scenario A — HTTP endpoint is unusually slow despite using AsyncAppender.** Check log call p99, queue occupancy, and blocked enqueue time. If the queue is continuously near full, the producer is hitting backpressure under `neverBlock=false`. Investigate why the sink is slow, reduce log volume, optimize the appender/disk, or adjust the policy; do not rush to increase the queue indefinitely.

**Scenario B — Endpoint is fast, but logs appear several seconds late.** Low caller latency only proves enqueueing is fast. Compare event timestamps, queue wait, file append, log agent shipping, and index ingest lag. If the file already has the event immediately but the search backend is slow, the bottleneck is downstream of JVM logging.

**Scenario C — p99 looks "clean", but error logs are missing.** Check configured discarding, `neverBlock`, drop counters, log levels/filters, exception appenders, and shutdown behavior. A p99 computed only on successful events can hide lost logs. Reconcile counts using unique event IDs in a test environment; do not use Trace ID as a counter.

**Scenario D — Logs pile up after a GC pause.** GC pauses producer/worker threads, and events may then hit the queue as a burst. Correlate queue depth and caller/visibility p99 charts with GC pauses, allocations, CPU throttling, and I/O saturation to confirm the relationship.

**Scenario E — A crash loses the last few log lines.** The async queue resides in memory; the process stopped before the worker could drain it. Configuring a shutdown hook/graceful stop and an appropriate `maxFlushTime` reduces risk during normal shutdowns, but cannot replace a durable log store when zero data loss is required.

## 11. Implementation and Interpretation Checklist

1. State the SLO explicitly: `logger.info` latency, time until logs appear in the file, time until the collector receives them, or time until they are searchable? What are the acceptable drop rate and durability requirements?
2. Measure sync/async baselines on real workloads; collect p50/p95/p99, throughput, queue occupancy, drops, and endpoint latency. Results must measure through queue drain when comparing log processing.
3. Identify the bottleneck: formatting/capture, queue, worker, file/stdout, collector, or index. Fix the stage where backlog actually forms.
4. Set a bounded queue based on bursts and RAM, and explicitly decide on the overload strategy. Do not trade away log loss for a pretty latency chart without recording it.
5. Test shutdown and crash handling separately, because an enqueued log is different from a durably stored log.
6. Set up alerts for sustained high queue occupancy, drops above threshold, worker errors, and event-to-searchable lag. Test failure paths periodically.
7. If logs must be correlated with traces, capture trace context/MDC at the right time and verify that async events do not carry stale context from another thread.

**Key takeaway:** Async logging usually lets business threads exit log calls earlier under favorable conditions, but the queue and sink still have to process all the events. To evaluate "async logging latency", you must measure **caller latency**, **wait/blocking time**, **time to sink/collector/index**, **drop rate**, and **durability** against real-world requirements.

## References

- [Logback — AsyncAppender](https://logback.qos.ch/manual/appenders.html#AsyncAppender) — queue, discarding threshold, neverBlock, and maxFlushTime.
- [Apache Log4j 2 — Asynchronous Loggers](https://logging.apache.org/log4j/2.x/manual/async.html) — AsyncLogger, AsyncAppender, ring buffer, and trade-offs.
- [Java 17 — BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html) — `put`, `take`, `offer`, and blocking semantics.
- [Java 17 — System.nanoTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()) — measuring elapsed time within a JVM.
