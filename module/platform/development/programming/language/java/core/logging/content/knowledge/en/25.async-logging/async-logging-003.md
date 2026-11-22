# Log Consumers in Asynchronous Logging

## 1. What Is a Log Consumer?

In **synchronous logging**, the thread handling business logic typically performs part or all of the logging work before continuing: creating the event, formatting the message, invoking the appender, and writing to the console, a file, or another destination. If the output is slow, the wait time can directly impact request latency.

In **asynchronous logging**, the business thread (producer) places a **log event** into a queue. One or more background threads (consumers) take events from the queue and forward them to the logging destination (sink/appender). A consumer is an **internal log-event consumer component**; it is not necessarily a Kafka consumer or RabbitMQ consumer processing business messages.

```text
Request thread A ── creates log event ─┐
Request thread B ── creates log event ─┼──► [Bounded log queue]
Worker thread  C ── creates log event ─┘           │
                                                   ▼
                                      [Log consumer / worker]
                                                   │
                                        Format / serialize
                                                   │
                                                   ▼
                                      [File / stdout / socket]
                                                   │
                                        (possibly via collector)
                                                   ▼
                                         [Log lookup system]
```

The consumer is responsible for **reading, processing, and handing off log events**; the exact design depends on the framework. Decoupling writes from business threads avoids making every request wait on the logging destination as long as the system has enough consumption capacity. However, the queue is still bounded: when logs are generated faster than they can be written over an extended period, the system must **wait, drop, or redirect** events according to the chosen policy.

Lesson objectives: understand the consumer processing flow, log ordering and reliability, behavior when the queue is full or the sink fails, how to shut down safely, and how to observe the consumer in a Java application.

## 2. What Does a Consumer Actually Do?

A typical processing cycle:

1. **Wait for an event** from the queue. The consumer may wait via `BlockingQueue.take()`, a ring buffer mechanism, or a logging framework-specific API; it does not need to continuously spin in a loop checking for emptiness.
2. **Receive the exact log event object** prepared by the producer. Information to preserve includes the event timestamp, log level, logger name, message/arguments, logging thread name, trace context (trace/span ID), and exception details if present.
3. **Format or encode** the event into the format required by the sink: plain text, JSON, binary format, or network-transmissible event. Part of the formatting work may already have been completed on the producer depending on the implementation.
4. **Forward to the appender/sink**: write to a file, stdout, or a centralized destination. A consumer may forward logs to a child appender; that appender may have its own buffer.
5. **Handle outcomes and errors**: track failures, retry capability, event loss, and queue congestion; never assume that dequeuing an event means it has been successfully written to disk.
6. **Finish on shutdown**: stop accepting new events per the system contract, process the remaining events in the queue, and ask the sink to flush/close within an appropriate timeout.

An important distinction:

| Milestone | What has happened | What is **not** yet guaranteed |
| --- | --- | --- |
| Calling `logger.info(...)` | Producer invoked the logging API | The sink has received the data |
| Successfully enqueued | Log is in the in-memory queue | The consumer has processed it |
| Consumer dequeues | Consumer owns the event for processing | File write succeeded |
| Appender reports written | Destination accepted it per its API | Data is durable across power loss |
| Flush/close completed | Corresponding buffers flushed/closed per contract | All external collectors/backends have indexed it |

Therefore, avoid phrasing this loosely as “logged” when you need to distinguish **enqueue**, **write**, **flush**, or **durable persistence**.

## 3. Data to Capture Before Handing Off to the Consumer

The asynchronous boundary changes the **execution thread**. When the producer creates a log event, it may be handling a request with its own `ThreadLocal`/MDC; the consumer usually runs on a different thread. If the consumer simply reads `MDC.get(...)` on its own thread, it may get an **empty or wrong context**.

Information that must be captured or safely transferred with the event:

- **Occurrence timestamp**: record the timestamp at the producer, avoiding using the time the consumer writes to the file as the event timestamp, because queuing can introduce delay.
- **Log level and source**: `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`, logger name, and class if needed.
- **Message/arguments**: ensure mutable objects are not modified before the consumer formats them. Depending on the framework, you may need to pre-format the message or copy the necessary data.
- **Request context**: `trace_id`, `span_id`, request ID, permitted tenant ID, and required MDC fields.
- **Exception**: preserve the stack trace, exception type, and cause chain using the safe event-capture mechanism provided by the framework.
- **Thread name/caller data**: capture at the producer if you want to know which thread logged the event; the consumer thread name is **not** the original request thread name.

Semantically incorrect example:

```java
// Illustrative code: consumer runs on a different thread than the producer.
String requestId = MDC.get("requestId"); // May be null or belong to the wrong request.
```

The principled approach is to capture `requestId` when the producer creates the event, or use an async logging integration that supports MDC snapshots. In the pure Java program later in this lesson, `traceId` is an immutable field passed directly into `LogEvent` to demonstrate this mechanism.

**Do not treat the log context as the default execution environment of the consumer thread.** If the consumer writes its own administrative logs, they must have their own context and must not accidentally carry the trace ID of a previous request.

## 4. Queues, Write Ordering, and Number of Consumers

### Bounded Queues and the Producer–Consumer Relationship

A **bounded** queue has a fixed capacity. If multiple producers generate logs faster than the consumer writes them, the queue will fill up. A bound is necessary to prevent a log burst from causing the application to exhaust the heap.

A FIFO queue with **a single consumer** retrieves events in the order they were successfully enqueued. However:

- Multiple concurrent producers may enqueue in a different order than their log creation timestamps.
- Log file order reflects the order in which the appender received/wrote events, not a proof of happens-before ordering of business operations across all threads.
- Multiple consumers or multiple queues/sinks can produce different output orders.
- If the sink performs retries or batching, the **order written/acknowledged at the backend** may differ from the queue dequeue order.
- The fact that a log event has been dequeued by the consumer does not mean the request has finished; the producer may continue running in parallel.

To reconstruct causality, you need timestamps, parent/child spans, request/message IDs, and source code; do not infer it solely from the position of log lines.

### Single Consumer or Multiple Consumers?

| Model | Pros | Risks / Things to Check |
| --- | --- | --- |
| Single queue, single consumer | Simple, FIFO by dequeue, easy shutdown | Slow writes bottleneck the entire queue |
| Single queue, multiple consumers | Can speed up if the sink supports parallelism | Can lose completion order, I/O contention |
| Multiple queues by sink or partition | Isolates certain workload types | Hard to determine global order, must handle multiple shutdown states |

Do not blindly increase the number of consumers just because the queue is long. If the actual sink only writes sequentially to a single file/stream or is IOPS-limited, adding threads can increase contention rather than throughput.

## 5. Slow Consumers and Queue-Full Policies

Let `λ` be the log generation rate (events/second) and `μ` be the consumer processing rate. Over a sustained period where `λ > μ`, the number of queued events tends to grow until it hits the limit. A queue helps absorb **short-term spikes**; it does not solve a persistently slow sink.

Policies to understand clearly:

| Policy | When Full | Consequence |
| --- | --- | --- |
| **Block producer** (backpressure) | Producer waits for consumer to free space | Preserves accepted events along the normal path, but increases latency / reduces business throughput |
| **Drop events** | Producer/adapter discards a portion of logs per configuration | Does not block business logic, but loses observability; drops must be counted |
| **Temporary synchronous write** | Logging thread performs the write work | May preserve more events, but causes sudden latency spikes for requests |
| **Timed wait then fail/drop** | Wait up to a configured duration | Bounds wait time, but requires a plan for unaccepted logs |

There is no “optimal” policy for every system. Audit/compliance logs have their own retention requirements and should not rely on a standard logging queue for durability. For operational logs, dropping `DEBUG`/`INFO` under overload may be acceptable, while still accounting for the risk of losing `WARN`/`ERROR` due to crashes, shutdown timeouts, or sink failures.

**“Not actively dropping when the queue is full” does not mean “never losing logs.”** Data still sitting in RAM can vanish if the JVM/process is killed, the JVM crashes, the machine loses power, or the appender fails to flush in time.

## 6. Java 17 Example: Single Consumer Writing Logs from a Bounded Queue

The following standalone program simulates a single-producer, single-consumer mechanism. The producer places events into an `ArrayBlockingQueue` of capacity 2; the consumer uses `take()` to wait and writes to stdout on the `log-consumer` thread. When closing the logger, the producer sends a special stop object (*poison pill*) **after all enqueued events**; the consumer finishes processing all preceding events and then stops.

The example is intentionally simple to make the consumer’s behavior clear. This is **not** a production logging library; it lacks retries, durable queuing, and full sink-failure handling.

Save as **`AsyncLogConsumerExample.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class AsyncLogConsumerExample {
    private record LogEvent(String level, String traceId, String message) {
    }

    // Use the same distinct object instance to signal the consumer to stop.
    private static final LogEvent STOP = new LogEvent("", "", "");

    private static final class AsyncLogger implements AutoCloseable {
        private final BlockingQueue<LogEvent> queue = new ArrayBlockingQueue<>(2);
        private final Thread consumer = new Thread(this::consume, "log-consumer");
        private boolean stopped;

        AsyncLogger() {
            consumer.start();
        }

        // Synchronize log()/close() so STOP is not inserted before an already-accepted log call.
        synchronized void log(String level, String traceId, String message)
                throws InterruptedException {
            if (stopped) {
                throw new IllegalStateException("Logger already closed");
            }
            // Queue full -> calling thread waits until the consumer takes an event.
            queue.put(new LogEvent(level, traceId, message));
        }

        private void consume() {
            try {
                while (true) {
                    LogEvent event = queue.take(); // Wait; no busy-spinning.
                    if (event == STOP) {           // Compare against the exact sentinel.
                        break;
                    }
                    System.out.printf(
                        "[%s] %s trace_id=%s | %s%n",
                        Thread.currentThread().getName(),
                        event.level(),
                        event.traceId(),
                        event.message()
                    );
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                System.err.println("Consumer interrupted; logs may be lost");
            } finally {
                System.out.flush();
            }
        }

        @Override
        public synchronized void close() throws InterruptedException {
            if (stopped) {
                return;
            }
            stopped = true;
            queue.put(STOP);   // Placed after all successfully enqueued events.
            consumer.join();   // Wait for the consumer to read STOP and exit.
        }
    }

    public static void main(String[] args) throws InterruptedException {
        String traceId = "4bf92f3577b34da6a3ce929d0e0e4736";

        try (AsyncLogger logger = new AsyncLogger()) {
            logger.log("INFO", traceId, "Request accepted");
            logger.log("WARN", traceId, "Downstream latency increased");
            logger.log("ERROR", traceId, "Gateway timeout");
        }
    }
}
```

Run with JDK 17+:

```bash
javac --release 17 AsyncLogConsumerExample.java
java AsyncLogConsumerExample
```

Exact stdout output during normal execution:

```text
[log-consumer] INFO trace_id=4bf92f3577b34da6a3ce929d0e0e4736 | Request accepted
[log-consumer] WARN trace_id=4bf92f3577b34da6a3ce929d0e0e4736 | Downstream latency increased
[log-consumer] ERROR trace_id=4bf92f3577b34da6a3ce929d0e0e4736 | Gateway timeout
```

Because there is only one producer and one consumer with a FIFO queue, **the order of the three lines is deterministic**; when the consumer runs between `log()` calls may vary, but it does not change the order in which events are enqueued. `close()` does not print an extra line for the sentinel.

How to read the code:

- `LogEvent` is an immutable `record` that captures `traceId` when the producer calls `log()`.
- `queue.put(...)` demonstrates **backpressure**: it does not drop when the queue is full, but the producer may have to wait. If the producer thread is interrupted while waiting, the call may fail to enqueue.
- `take()` waits for events; the consumer does not burn CPU with a continuous polling loop.
- The `STOP` sentinel is a distinct object checked with `==` to avoid mistaking a normal message for a stop command.
- `synchronized` prevents races between `log()` and `close()`, so in-flight `log()` calls complete before `STOP` is enqueued. This pattern can cause contention with multiple producers and is only meant for teaching the mechanism.
- `join()` makes the program wait for the consumer to stop instead of exiting as soon as the producer logs the last line.
- `System.out.flush()` requests flushing the `PrintStream` buffer; it is **not equivalent** to `fsync` and does not guarantee that a collector or disk has durably persisted the data.

**Important limitation of the example:** if the consumer dies unexpectedly or the destination hangs, the producer/`close()` can wait indefinitely; `close()` being interrupted while sending `STOP` also needs a more careful cleanup strategy. Real systems need a shutdown timeout with an explicit policy, dead-worker detection, sink error reporting, and interruption handling. Do not copy this prototype to replace Logback/Log4j2 in production.

## 7. Integrating Consumers with a Java Logging Framework

In real applications, you should use a framework that already handles basic concurrency and lifecycle management. For example, **Logback** provides `AsyncAppender`: request threads write events into a queue, and the appender’s worker forwards events to a **child appender** such as `FileAppender`. The worker does not necessarily write to the filesystem directly; it can invoke an appender that has its own formatter/buffer.

Example **`logback.xml`** configuration (requires Logback in the application; not used standalone with the pure Java program above):

```xml
<configuration>
    <appender name="FILE" class="ch.qos.logback.core.FileAppender">
        <file>logs/app.log</file>
        <append>true</append>
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] trace=%X{trace_id} %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ASYNC" class="ch.qos.logback.classic.AsyncAppender">
        <queueSize>1024</queueSize>
        <discardingThreshold>0</discardingThreshold>
        <neverBlock>false</neverBlock>
        <maxFlushTime>5000</maxFlushTime>
        <appender-ref ref="FILE"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="ASYNC"/>
    </root>
</configuration>
```

Meaning of the options in the example:

- `queueSize`: event queue capacity.
- `discardingThreshold=0`: disables `AsyncAppender`’s proactive discarding of lower-level events based on remaining capacity; this does not mean logs are preserved across all failures.
- `neverBlock=false`: when the queue is full, enqueuing may block the producer; consider the latency impact.
- `maxFlushTime=5000`: limits how long to wait for the worker to finish on stop (per the behavior of the Logback version in use). On timeout or abrupt termination, remaining logs may not be written.
- `appender-ref`: the worker forwards events to `FILE`; write permissions and disk-full conditions still affect consumption speed.

The `%X{trace_id}` pattern is only useful if the application/instrumentation **actually puts `trace_id` into the event’s MDC**. Across different OpenTelemetry/Logback library versions, the key name may be defined or mapped differently; verify the actual emitted logs. When configuring a JSON logger, keep the trace ID as a dedicated field rather than only interpolating it into the message string.

**Log4j2** also provides asynchronous logging configurations (e.g., async loggers or async appenders), with its own queue/ring-buffer algorithms and queue-full policies. Do not copy Logback property names over to Log4j2. When choosing a mechanism, read the documentation **for your exact framework version** regarding queue size, drop behavior, blocking, location info, and shutdown.

## 8. Flush, Shutdown, and Consumer Reliability

A controlled shutdown procedure typically includes:

1. Stop or finish producers and in-flight requests that generate logs.
2. Prevent new events from entering the queue after the defined stop point.
3. Signal the consumer to exit after processing already-accepted events, or use the framework’s stop API.
4. Wait for the consumer to drain within the allotted time; record the number of remaining events if the timeout expires.
5. Flush/close the sink per contract, then close the collector/exporter if it is part of the application lifecycle.

Two cases must be distinguished:

- **Normal shutdown:** there is an opportunity to drain, flush, and close resources. If the shutdown timeout is shorter than the time needed to consume the backlog, logs may be dropped.
- **Process kill, crash, out-of-memory, or power loss:** there is no guarantee that shutdown hooks will run, the consumer may not finish writing, and in-memory buffers may be lost; `finally` is not a guarantee in these situations either.

If logs are business data whose storage must be proven, design a **durable event store/outbox** or a dedicated transactional and acknowledgment mechanism. In-memory logging queues are typically aimed at observability and do not provide exactly-once semantics by default.

Never assume “the consumer dequeued the event = the event was saved by the backend.” When the destination fails mid-write and retries, log **loss** or **duplication** can occur; detectability depends on the sink and event format.

### When the Sink Fails to Write

The consumer may encounter `IOException`, disk full, permission denied, socket reset, error responses, timeouts, or blocked I/O. The handling strategy depends on the nature of the sink:

- Report errors through a channel that does not depend on the failing appender itself (e.g., status manager, metrics, or cautious stderr).
- Use bounded retries/backoff if appropriate, while controlling memory, duplicates, and ordering.
- Distinguish transient errors from permanent errors, and track the time from event creation to write.
- Have a policy for when the sink does not recover: block producers, drop with counters, degrade, or stop the service if required by the system.
- Avoid logging consumer errors **back into the same failing queue** in a way that creates an infinite logging loop.

## 9. Capturing Trace/MDC Without Corrupting Context

Systems handling concurrent requests may use MDC to record `trace_id`, `span_id`, and `request_id`. The consumer is usually a shared worker across many requests, so these fields must be attached **per event**, rather than reading the worker thread’s current MDC and applying it to everything.

A data-correct flow:

```text
Request A has trace_id=A
    -> producer captures event {message, trace_id=A, ...}
    -> queue
    -> consumer writes event A, trace_id=A

Request B has trace_id=B
    -> producer captures event {message, trace_id=B, ...}
    -> queue
    -> consumer writes event B, trace_id=B
```

Things to verify in Java:

- Does the async logging framework **capture MDC, thread name, and exceptions** at enqueue time?
- Does application code clear/restore MDC at the end of a request or after a task in a thread pool?
- Does instrumentation propagate trace context properly across HTTP, gRPC, executors, and message headers?
- Do logs in the sink include `timestamp`, `service`, `level`, `trace_id`, and `span_id` fields together for querying?
- Does the consumer avoid storing tokens, passwords, cookies, Authorization headers, or personal data just for “easy debugging”?

Having a shared `trace_id` across log lines helps **correlate** them; to reconstruct relationships between operations, also inspect spans and parent/link relationships in the tracing backend.

## 10. Measuring Consumer Health and Tuning Capacity

Useful signals:

| Metric | Meaning |
| --- | --- |
| `queue_depth` / `queue_capacity` | How full the queue currently is |
| `enqueued_total`, `written_total` | Events accepted and events successfully processed per the adapter’s definition |
| `dropped_total` | Events discarded (break down by reason/level if cardinality is acceptable) |
| `enqueue_block_duration` | Time producers had to wait to submit logs |
| `consumer_lag` | Elapsed time from event timestamp to consumer processing |
| `sink_write_duration` | Latency of the write destination |
| `sink_error_total` | Write errors by sink/exception type |
| `shutdown_pending` | Events remaining when stop times out |
| `consumer_alive` / worker state | Whether the consumer is still running or stopped due to an error |

These metrics are a **recommended observability model**; exact names and availability depend on the framework/collector. Do not put `trace_id` or `request_id` into metric labels, as they have very high cardinality.

How to tune with evidence:

1. Measure normal log rates, short-term spikes, log volume by level, and sink latency.
2. Choose a queue size large enough to absorb expected spikes within your memory budget; avoid picking a huge size just to mask a slow sink.
3. Decide the queue-full behavior upfront based on how critical the logs are: blocking, dropping, or another mechanism.
4. Check business latency when the queue is full; record lost/delayed events.
5. Load test burst scenarios, nearly full disks, unresponsive sinks, restarts, and shutdowns under load.

A large queue can delay hitting the ceiling, but it also **increases the volume of unwritten logs**, consumes heap, and lengthens drain time during shutdown.

## 11. Common Implementation Pitfalls

| Symptom | Possible Cause | Mitigation |
| --- | --- | --- |
| Requests suddenly slow down despite async logging | Queue is full and producers are blocked; sink is too slow | Measure enqueue wait, queue depth, sink rate; review overload policy |
| `DEBUG`/`INFO` logs missing under load | Framework proactively discards when space is low | Check discard policy, count dropped logs, adjust to requirements |
| Last logs lost before process exit | Appender not stopped/drained or timeout too short | Manage logging lifecycle, shutdown budget, and output readback |
| Logs missing trace ID or having wrong ID | Reading MDC on consumer instead of capturing on producer; lost context | Snapshot context in the event, verify instrumentation |
| Logs appear out of timestamp order | Multiple producers, buffering, retries, or multiple consumers | Distinguish enqueue order, event time, and backend ingestion |
| High CPU from consumer | Busy-spinning, heavy formatter, or suboptimal serialization | Use proper waiting mechanisms, measure CPU/allocations, profile formatter |
| Duplicate logs after network error | Sink/adapter retries without knowing whether prior write succeeded | Use event ID/dedup if backend supports it; clarify semantics |
| Consumer dies while application keeps running | Uncaught exception swallowed or no worker health check | Monitor worker liveness, error status, bounded recovery mechanism |
| Heap grows continuously | Unbounded queue or retaining too many large log events | Use a bounded queue, limit event size and logging volume |
| Recursion when reporting logging errors | Error handler logs back through the same failing appender | Route alerts to an independent channel, avoid self-logging loops |

## 12. Testing the Consumer: What Needs to Be Proven?

- **FIFO where guaranteed:** with one producer and one consumer, enqueuing 1–2–3 must result in events being written in order 1–2–3. With multiple producers, do not assert global ordering from timestamps.
- **Queue full:** intentionally slow down the sink and emit more logs than capacity. Verify that the producer blocks/drops as configured; also measure business latency.
- **Context snapshot:** two requests with different trace IDs; even though the consumer shares a single thread, each log line still carries its corresponding producer’s ID.
- **Sink failure:** simulate write exceptions/timeouts/disk full, and verify alerts, drops/retries, and worker state per contract.
- **Shutdown under load:** enqueue a set of identified events and call stop properly; compare accepted events against events actually written after drain. Also test shutdown timeouts.
- **Repeated start/stop:** do not leak threads beyond the application lifecycle, do not spawn duplicate consumers, and do not hang when the appender has not started or has already stopped.
- **Searchability:** verify JSON logs have `timestamp`, `level`, `service`, and `trace ID`/`span ID` in the right fields; exceptions retain full details.

Avoid writing tests that merely see “a log line appeared” and conclude the consumer is safe. Test under pressure, failure, and shutdown as well.

## 13. Design Principles to Remember

The log consumer is **the component that delivers already-created events to the storage/query destination**. The producer is responsible for creating logs with the right context; the queue buffers rate differences; the consumer performs the write work and is subject to sink behavior. The most important decisions are:

- Choose a **bounded queue** and an explicit queue-full policy; async does not eliminate I/O limits.
- Capture event details at log emission time, especially timestamp, thread name, exception, and trace/MDC.
- Do not infer business ordering or data durability solely from dequeue order and a successful enqueue call.
- Monitor queue depth, lag, write errors, drops, and block time to know whether async logging is still reducing latency.
- Proactively stop, drain, and flush within the framework’s capabilities; understand that logs in RAM can be lost if the process dies abruptly.
- Use Logback/Log4j2 for your exact version and verify the actual configuration, rather than writing a custom logging worker without error handling.

**Remember:** the consumer moves logging cost off business threads **as long as processing capacity is sufficient**. The reliability of the entire logging pipeline still depends on the queue, overload policy, sink, shutdown mechanism, and error observability.