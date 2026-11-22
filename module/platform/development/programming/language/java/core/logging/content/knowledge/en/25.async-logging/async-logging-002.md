# Log Queues in Java Asynchronous Logging

## 1. What is a log queue and why is it needed?

When a Java application calls `logger.info(...)`, writing to a console, file, socket, or log collection system can take time due to message formatting, internal locks, and especially I/O. If every log call waits for the output to complete, a slow logging destination can increase request latency.

A **log queue** is an intermediate queue that holds *log events* waiting to be processed by one or more logging threads. In an asynchronous logging architecture, business threads (*producers*) typically create/enqueue events into the queue, while background threads (*consumers/workers*) dequeue events and pass them to the target appender.

```text
Request thread A ─┐
Request thread B ─┼─> create LogEvent ─> [ Bounded queue ] ─> worker ─> appender ─> stdout/file/remote
Task thread C    ─┘                         ^          ^
                                         enqueue    dequeue
```

The main goal is to **decouple the time an application generates a log from the time the log is actually written**, thereby reducing wait time on the business execution path when the consumer keeps up. However, enqueuing can still be slow or blocked when the queue is full; therefore, "async" does not mean "never blocks," "zero log loss," or "durably persisted on disk."

Distinguish three points in time:

1. **Log created**: the framework receives the `logger.info(...)` call, evaluates the level/filter, and prepares the event.
2. **Log accepted into the queue**: the producer has successfully submitted the event, but the consumer may not have written it to the destination yet.
3. **Log processed by the appender**: the consumer has passed the event to the appender; stdout itself, the OS buffer, or the network may still not have durably stored it.

For most async appenders, the queue is only an **in-process temporary buffer**; it is not a durable queue like Kafka or a storage acknowledgment mechanism.

## 2. What should a log event carry?

A log event typically contains: a timestamp, severity/level (`TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`), logger name, message and arguments, exception/stack trace if present, thread name, and context such as `requestId`/`trace_id` in MDC or ThreadContext.

Each event is the unit passed through the queue. **Queue capacity is usually measured by the number of events, not bytes.** Two events can consume vastly different amounts of memory: a short line of text compared to an exception with a large stack trace or serialized objects.

An important issue when crossing threads: request context stored in the **producer's** `ThreadLocal`/MDC may not exist on the worker thread. Async frameworks typically take a snapshot of the relevant fields before enqueuing. Do not let the consumer read `MDC.get(...)` from the background thread and assume it is the original request's context. Similarly, passing mutable objects as log arguments can cause discrepancies if their values change before the message is formatted; log the necessary snapshot values instead.

The log example below preserves the request's trace context at the time the event was created:

```text
2026-11-10 10:15:20.125 INFO  [http-42] trace_id=4bf92f3577b34da6a3ce929d0e0e4736 order=813 Created order
```

Here, the timestamp, thread name, and trace ID reflect **when the event was created**, even though the file-writing thread may process it several milliseconds later.

## 3. How do bounded queues, producers, and consumers work?

The basic model consists of the following steps:

1. The logger determines whether the event passes the level/filter threshold.
2. If it does, the framework prepares the event and attempts to **enqueue** it.
3. The queue maintains the order of accepted events according to its mechanism.
4. The worker **dequeues** the event and performs I/O with the target appender.
5. When the application shuts down, the system must have a way to stop accepting new events, process the remaining backlog, and stop the worker.

In Java, `BlockingQueue<E>` is an intuitive way to learn the producer–consumer model. `ArrayBlockingQueue` provides a FIFO queue with a fixed capacity. `LinkedBlockingQueue` also supports a capacity, but using its no-argument constructor sets a very large default limit; it should not be casually treated as "safely unbounded."

| `BlockingQueue` API | When space/data is available | When the queue is full or empty |
| --- | --- | --- |
| `offer(event)` | Inserts immediately, returns `true` | Returns `false` if it cannot insert immediately |
| `put(event)` | Inserts successfully | Waits until space is available; can be interrupted |
| `offer(event, timeout, unit)` | Inserts and returns `true` | Waits up to timeout, then returns `false` |
| `poll()` | Returns the head event or `null` | Returns `null` immediately if empty |
| `take()` | Removes and returns the head event | Waits until an event is available |
| `poll(timeout, unit)` | Removes and returns the head event | Waits up to timeout, then returns `null` |

These are **Java APIs used to illustrate policies**, not a guarantee that all logging frameworks use `BlockingQueue` directly. For example, Log4j 2 `AsyncLogger` uses a *ring buffer/LMAX Disruptor*, while some async appenders use a blocking queue.

### 3.1. Does FIFO guarantee all logs appear in exact chronological order?

A FIFO queue ensures the consumer retrieves events **in the order they were successfully placed into the queue**. With a single sequential producer, enqueue order generally matches call order. However, when multiple requests/threads log concurrently, ordering across threads depends on scheduling, event creation/submission timing, and the number of consumers; **write order cannot be treated as the absolute order of all events in a distributed system**.

Furthermore, if events are copied across different queues, multiple appenders, multiple services, or network outputs, log order at the backend can change. Timestamps, trace IDs, and correlation fields remain essential.

### 3.2. Why must a queue usually be bounded?

If producers generate logs faster than consumers write them for an extended period, the backlog grows. A bounded queue caps the memory reserved for pending events while forcing the system to explicitly decide what to do when full. A practically unbounded queue can cause GC pressure, heap growth, and ultimately an `OutOfMemoryError`. A queue that is too small can cause producers to block or drop logs even during short bursts.

## 4. When the queue is full: what are the options and trade-offs?

**Backpressure** is how the system responds when the log generation rate exceeds the write capacity. No single policy fits every application.

| Policy | When the queue is full | Benefits | Costs/Risks |
| --- | --- | --- | --- |
| **Block producer** | Waits until space is available | Fewer dropped events solely due to a full queue | Increases request latency, reduces throughput, can stall thread pools |
| **Drop new events** | Does not enqueue, increments drop count | Protects response time | Loses some observability data; must monitor drop counts |
| **Drop by priority/level** | Typically discards `TRACE`/`DEBUG`/`INFO` first, keeps `WARN`/`ERROR` longer | Preserves critical signals during bursts | Event stream is incomplete; `INFO` logs are sometimes still essential |
| **Fallback to synchronous processing** | Some events are written directly on the caller thread | Chance to continue writing when the queue is congested | Highly variable latency, risk of contention and I/O errors on business threads |
| **Wait with timeout** | Waits briefly, then decides to drop/fallback | Caps maximum wait time | Must clearly design the post-timeout policy |

Choose **blocking** when preserving logs during short-term load spikes is a priority and the service can tolerate added latency. Choose **metered dropping** when the primary function must maintain responsiveness and mandatory data has a separate mechanism. For audit trails, financial transactions, or events that must be guaranteed persisted, **do not use an in-memory async log queue as the sole storage mechanism**; you need durable writes, success acknowledgments, and a dedicated retry policy.

"Drop low levels, keep ERROR" also does not guarantee zero loss: process crashes, full disks, network failures, and abrupt shutdowns can still lose events at any level. Even a blocking policy only partially addresses queue-full scenarios.

## 5. Java 17+ example: simulating a bounded log queue

This is a **standalone, compilable, and runnable standard Java program** that does not require SLF4J/Logback. It intentionally holds the worker in a waiting state to demonstrate a queue capacity of 2: two events are accepted, the third is rejected; then the worker processes the accepted events and receives a stop signal. In real applications, use a logging framework's async appender rather than building your own logging system.

Save as `QueueLogDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;

public class QueueLogDemo {
    private record LogEvent(int number, String message) {}

    // Used only as a stop signal in this demonstration.
    private static final LogEvent STOP = new LogEvent(-1, "stop");

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<LogEvent> queue = new ArrayBlockingQueue<>(2);
        CountDownLatch startConsumer = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            try {
                startConsumer.await();
                while (true) {
                    LogEvent event = queue.take();
                    if (event == STOP) {
                        return;
                    }
                    System.out.println(
                            "sink: " + event.number() + " " + event.message());
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "log-writer");
        worker.start();

        System.out.println("enqueue 1: "
                + queue.offer(new LogEvent(1, "A")));
        System.out.println("enqueue 2: "
                + queue.offer(new LogEvent(2, "B")));
        System.out.println("enqueue 3: "
                + queue.offer(new LogEvent(3, "C")));

        startConsumer.countDown();
        queue.put(STOP); // Wait for space to place the stop signal after accepted events.
        worker.join();   // Wait for the worker to finish processing before exiting.
        System.out.println("shutdown: drained");
    }
}
```

Compile and run on JDK 17 or later:

```bash
javac --release 17 QueueLogDemo.java
java QueueLogDemo
```

Exact stdout when running the program above:

```text
enqueue 1: true
enqueue 2: true
enqueue 3: false
sink: 1 A
sink: 2 B
shutdown: drained
```

**Why is the output deterministic?** The worker waits on the `CountDownLatch` before taking elements. Meanwhile, the main thread calls `offer` three times on a queue of capacity 2, so the third call returns `false`. After releasing the latch, a single worker reads the two events in FIFO order. `STOP` is placed after the two accepted events, and `join()` waits for the worker to finish.

The example above demonstrates **dropping when the queue is full** via `offer(false)`; it is not a production shutdown pattern: `queue.put(STOP)` can also block indefinitely if the worker is stuck, terminates abnormally, or the sink fails. Real applications need timeouts, interrupt handling, drop counters, worker error reporting, and bounded drain times. Also, "drained" in this example only means the consumer finished printing the events via `System.out`, not that the content was durably saved to disk.

If `offer` is replaced with `put`, the third call will **block** until the worker takes an event; with the latch in this example, calling `put` before releasing the latch would wait forever. This illustrates why **blocking enqueues can cause deadlocks or amplify incidents** if thread relationships are not carefully designed.

## 6. Logback: configuring a queue with AsyncAppender

For Spring Boot applications using **SLF4J + Logback**, `ch.qos.logback.classic.AsyncAppender` is a common way to place a queue in front of a logging appender. Example `src/main/resources/logback-spring.xml`:

```xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level [%thread] %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ASYNC" class="ch.qos.logback.classic.AsyncAppender">
        <queueSize>1024</queueSize>
        <discardingThreshold>0</discardingThreshold>
        <neverBlock>false</neverBlock>
        <includeCallerData>false</includeCallerData>
        <maxFlushTime>10000</maxFlushTime>
        <appender-ref ref="STDOUT"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="ASYNC"/>
    </root>
</configuration>
```

In this configuration:

- `STDOUT` remains responsible for formatting and writing; `ASYNC` manages the queue/worker. The root logger references only `ASYNC` to avoid synchronously writing a duplicate copy of the same event.
- `queueSize=1024` is the capacity in **events**, not bytes.
- `discardingThreshold=0` disables `AsyncAppender`'s **mechanism for discarding lower-level logs when the queue is nearly full**. It **does not guarantee zero log loss**, as shutdowns, crashes, sink errors, or other settings can still cause losses.
- `neverBlock=false` allows producers to wait when the queue is **completely full**. During sustained high traffic, `logger.info(...)` calls can become as slow as synchronous logging.
- `includeCallerData=false` avoids the overhead of capturing caller location data (class/file/line) when not needed.
- `maxFlushTime=10000` gives the worker up to roughly 10 seconds to flush when the appender stops; if it cannot drain everything within that time, remaining events may be lost. This is a shutdown wait limit, **not per-log latency**.

**Logback defaults to remember:** The default `queueSize` is **256**. When the queue has only about **20% remaining capacity**, `AsyncAppender` by default may discard `TRACE`, `DEBUG`, and `INFO` events; `WARN` and `ERROR` are prioritized when the queue is nearly full. `neverBlock` defaults to `false`. If your application needs to keep `INFO` logs during bursts, you must consider `discardingThreshold=0` alongside potential backpressure; do not just increase the queue size and assume drops will no longer occur.

To prioritize preserving latency over waiting on the queue:

```xml
<neverBlock>true</neverBlock>
```

When the queue is full, producers do not wait and new events may be dropped. Enable this only if you understand and monitor the log loss rate. Under both policies, actual throughput is still bounded by the target appender (especially stdout when a log shipper or storage destination is bottlenecked).

### 6.1. Logback and MDC

MDC holds fields like `requestId` or `trace_id` for correlation. Logback's `AsyncAppender` prepares "cheap" fields such as thread name and MDC on the caller side before dispatching, allowing the worker's pattern to still have the correct context. For example, update the pattern to:

```xml
<pattern>%d{HH:mm:ss.SSS} %-5level [%thread] request=%X{requestId} trace=%X{trace_id} - %msg%n</pattern>
```

This is a **pattern replacement** inside an existing appender, not adding another appender. The application must still populate MDC at the start of a request and clear/restore it in a `finally` block or use supported instrumentation; an async queue does not create trace context on its own.

If you enable caller location fields like `%class`, `%method`, `%file`, or `%line`, you should benchmark `includeCallerData` in practice; capturing stack/caller info typically adds overhead on the caller thread. Do not enable it just to make logs look more complete.

### 6.2. When does a Logback queue still cause slowdowns?

In steady state, if events arrive faster than they can be written, the queue gradually fills up. After that:
- With `neverBlock=false`, producers are blocked on enqueue; request latency increases and can impact thread pools.
- With `neverBlock=true`, business throughput may be less affected, but logs are dropped.
- With the default discarding threshold, some lower-level logs are dropped **even before the queue is full**.

Therefore, async configuration does not replace the need to verify actual write speed, log volume, filtering, and retention.

## 7. Log4j 2: How do AsyncAppender and AsyncLogger differ?

**Log4j 2 AsyncAppender** uses a blocking queue to pass log events to a thread that invokes the target appender. Example `log4j2.xml` in an application configured to use Log4j 2 Core:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="STDOUT" target="SYSTEM_OUT">
            <PatternLayout pattern="%d{HH:mm:ss.SSS} %-5p [%t] %c - %m%n"/>
        </Console>
        <Async name="ASYNC" bufferSize="1024" blocking="true">
            <AppenderRef ref="STDOUT"/>
        </Async>
    </Appenders>
    <Loggers>
        <Root level="info">
            <AppenderRef ref="ASYNC"/>
        </Root>
    </Loggers>
</Configuration>
```

`bufferSize` is the maximum number of queued events (the default in current Log4j 2 documentation is 1024). `blocking=true` allows waiting when the queue is full. If changed to `blocking=false`, the exact behavior when full depends on the queue-full policy and `errorRef` if configured; **do not assume events will always be written synchronously or retained**. If the target appender fails on the async thread, the exception generally does not propagate back to the thread that called the logger.

**Log4j 2 AsyncLogger** is a different mechanism: it uses an **LMAX Disruptor/ring buffer**, which can reduce contention across many workloads. It is still a bounded buffer structure and still requires deciding a policy when full. Using `AsyncLogger` globally or mixed with synchronous loggers requires the corresponding Log4j 2 configuration along with a compatible Disruptor dependency. Simply placing `<Async>` in `log4j2.xml` does not switch to `AsyncLogger`.

| Property | Logback AsyncAppender | Log4j 2 AsyncAppender | Log4j 2 AsyncLogger |
| --- | --- | --- | --- |
| Event transfer mechanism | Blocking queue | Blocking queue | Ring buffer via LMAX Disruptor |
| Actual writing thread | Appender worker | Appender worker | Consumer/async logging thread |
| Backpressure | Wait or drop via `neverBlock`; has discard threshold | Blocking/queue-full policy, `errorRef` | Queue-full policy of async components |
| Key considerations | Discard threshold and `maxFlushTime` | Queue/full policy, background appender errors | Dependency, wait strategy, ring-buffer size, and queue-full policy |

Do not stack an **AsyncAppender directly behind an AsyncLogger** without a reason; two additional async layers can introduce extra queues, overhead, and make tracing loss/latency harder. Measure before choosing a mechanism.

## 8. Sizing the queue and identifying bottlenecks

Let:

- `λ` (*lambda*) be the rate at which producers generate events (events/second).
- `μ` (*mu*) be the steady rate at which the consumer/appender processes events (events/second).
- `T` be the burst duration (seconds).
- `Q` be the number of queued events at a given point in time.

If `λ > μ` for a short period, the backlog grows by approximately:

```text
backlog_growth ≈ (lambda - mu) × T
```

For example, if a peak generates **12,000 events/second** and the sink only processes **8,000 events/second** for **2 seconds**, the queue needs to absorb roughly **8,000 events** for that burst alone, assuming it starts empty and these rates hold steady. A capacity of 10,000 might be a starting point for experimentation to leave some headroom; **it is not a default production configuration formula**, because event sizes, GC, traffic spikes, and processing times vary.

If after the burst the producer drops back to **6,000 events/second**, an 8,000 events/second sink will drain the backlog at a net rate of 2,000 events/second; draining 8,000 events takes roughly **4 seconds**. If the producer **sustains** 12,000 events/second while the consumer only reaches 8,000, increasing capacity only delays when the queue fills. You must reduce log volume, improve sink/consumer performance, filter levels, tune the pipeline, or accept a log-loss/backpressure policy.

### 8.1. Memory cost

Queue size does not directly reflect heap usage. For a rough estimate, you need to account for the event object, arguments/exceptions, whether the message is already formatted, the MDC snapshot, and the overhead of the queue itself. For example, **10,000 events × 1 KiB/event ≈ 9.8 MiB** is only an illustrative assumption; a long stack trace or a retained object graph can be much larger. Measure heap and GC under a realistic workload.

### 8.2. Batching and throughput

Consumers may write in batches or appenders may buffer to reduce per-event I/O overhead. However, large batches can increase the time logs sit waiting and the amount of data lost if the process dies. Distinguish between:
- **Event queued**: waiting for the consumer.
- **Event forwarded**: processed by the appender.
- **Buffered/OS flushed**: data has reached the buffer layer or operating system.
- **Durably stored**: the storage destination guarantees persistence at the required level; do not assume this merely because flush was called.

A good goal is achieving required throughput with acceptable log latency, rather than simply increasing queue capacity.

## 9. Observing the queue: what to measure?

A system using an async log queue should expose or derive the following metrics:

| Metric | Operational meaning | Warning signs |
| --- | --- | --- |
| Queue depth / utilization | Pending events / capacity | Consistently near 100% or growing without draining |
| Enqueue rate | Events accepted per second | Bursts exceeding sink capacity |
| Dequeue/processed rate | Events processed by worker per second | Unusually low, I/O bottlenecked |
| Dropped event count/rate | Number of events dropped by policy | Any non-zero value for critical logs |
| Enqueue block duration | Time producers wait on the queue | Request p95/p99 rising with wait time |
| Event age / queue wait time | Difference between creation time and processing time | Logs appearing late, nearing timeout/retention |
| Appender errors/retries | Disk, network, encoder, or endpoint errors | Queue not draining, retry storms |
| Shutdown drain duration | Time to process remaining logs at shutdown | Cut off by timeout, final logs lost |

Reading `queue.size()` in a concurrent environment is only a **point-in-time snapshot**; do not use a single reading as sufficient proof that the system has no drops. Frameworks vary in their built-in statistics: check what metrics/instrumentation are actually supported, or wrap at the operational layer if needed.

Test the following scenarios:
1. Short burst above normal throughput: what percentage does the queue fill to, and how long does it take to drain?
2. Slow or stalled sink: how does request latency fluctuate, and how many logs are lost?
3. Continuous logging of large exceptions: how do heap and GC behave?
4. Stopping the application with a backlog: what is the drain time and the percentage of final logs written?
5. Permission/disk full/network errors: where does the appender report errors, and do operators receive alerts?
6. High multi-producer load: do actual throughput, contention, and log ordering meet requirements?

For systems with `trace_id`, also verify that the context in the event comes from the producer and does not turn into the log worker thread's context.

## 10. Shutdown and log reliability

A sound lifecycle for a bounded queue:

```text
RUNNING (accepting events) -> STOPPING (rejecting new events)
    -> drain remaining queue -> flush appender/sink -> stop worker -> STOPPED
```

Across frameworks, specific methods and lifecycles vary. In Logback, `AsyncAppender` attempts to flush the queue when `LoggerContext` stops, up to `maxFlushTime`; past the timeout, remaining events may be discarded. Killing the application with `kill -9`, process crashes, or terminating containers too quickly gives the worker no chance to drain. When deploying in containers, configure a graceful termination period sufficient for realistic backlogs, while avoiding indefinite shutdown hangs if the sink is stuck.

**Do not equate draining with durability:** once the worker has emptied the queue and called the appender, data may still reside in OS buffers, transport layers, or downstream pipelines. For critical logs requiring high durability, distinguish between "sent," "received," and "persisted," and design the collection pipeline to match the required guarantee level.

For exceptions inside the worker:
- Do not silently swallow disk/encoder/transport errors; use appropriate status/error reporting mechanisms, avoiding logging internal errors back into the same failing queue and causing recursion.
- Retry with limits and backoff; retrying indefinitely while holding all events on the heap can still cause OOM.
- During prolonged failures, have an intentional policy for dropping, failing over, or halting the service depending on log criticality.

## 11. Common implementation pitfalls

| Symptom | Likely cause | Remediation |
| --- | --- | --- |
| Async enabled, but p99 latency still spikes during traffic bursts | Queue is full and producers are blocking | Measure queue depth, enqueue wait, sink throughput, and policy. |
| `INFO` logs missing even though code executed | Logback discard threshold, level/filter, or full queue | Check discard configuration, drop counts, and log levels. |
| Increasing `queueSize` endlessly, yet it still fills up | Log generation rate exceeds processing rate over a sustained period | Fix the bottleneck and reduce log volume instead of only expanding the queue. |
| Sharp increase in memory/GC | Events retaining large objects/stack traces, queue too long | Profile heap, shrink payloads, and bound capacity. |
| Final logs lost during rolling restarts | Incomplete drain, shutdown timeout too low | Tune graceful shutdown and monitor remaining events. |
| Duplicate log lines for the same event | Root logger references both async and sync sinks, or multiple collection pipelines | Check appender references, additivity, and collectors. |
| Incorrect `trace_id` or `requestId` | Context not snapshotted properly on enqueue, or MDC not cleared | Inspect the MDC lifecycle on the event-producing thread. |
| Reported as "flushed" but backend is missing logs | OS/network/backend buffering or export failure | Verify the delivery chain and destination acknowledgment policy. |
| Logging worker hits an exception and goes silent | Errors on the async thread do not propagate back to the caller | Enable framework status/error monitoring and check sink failures. |

For logs containing sensitive data, **filter/mask before the event is placed into the queue**. Do not keep tokens, passwords, personal information, or objects containing secrets in the event expecting the consumer to strip them later; the data is already in memory and could be written to another destination.

## 12. How to decide whether to use a log queue

Use async logging when measurements show that log I/O or encoding is impacting request latency or throughput and the application can accept the trade-offs of a queue. For low-volume services, synchronous logging is simpler, makes errors easier to spot, and avoids extra buffering.

Before deploying, you should be able to answer:

1. How many events per second are generated at normal and peak load?
2. How many events/second can the sink write in the slowest scenario?
3. How long are producers allowed to wait when the queue is full?
4. If dropping is necessary, which logs are acceptable to lose and how is loss detected?
5. How much heap does the queue occupy with large events and exceptions?
6. How much time is available to drain during shutdown, and what are the actual durability requirements?
7. Are MDC/trace context and log ordering preserved to the destination?

A proper design does not just "have a queue"—it also has **bounded capacity, a queue-full policy, monitoring for drops/waits, and a time-bounded shutdown process**. A queue is a tool for balancing business latency against observability completeness; choose your configuration based on real measurements.

## References

- [Oracle Java 21 – BlockingQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html).
- [Oracle Java 21 – ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html).
- [Logback manual – AsyncAppender and queue configurations](https://logback.qos.ch/manual/appenders-async-sift.html).
- [Apache Log4j 2 – Async appender](https://logging.apache.org/log4j/2.x/manual/appenders/delegating.html).
- [Apache Log4j 2 – Asynchronous loggers](https://logging.apache.org/log4j/2.x/manual/async.html).
- [Apache Log4j 2 – Performance](https://logging.apache.org/log4j/2.x/manual/performance.html).