# Log Loss When the Queue Is Full in Asynchronous Logging (Java)

## 1. Where Does the Problem Occur?

Asynchronous logging decouples business processing threads from log output operations: the application thread creates a log event and places it into a bounded buffer; one or more workers read from the buffer and write to the console, a file, or a centralized service.

~~~text
Application thread
      |
      v
  creates LogEvent
      |
      v
  Bounded Queue / RingBuffer
      |
      v
  Logging worker
      |
      v
  File / stdout / network / log collector
      |
      v
  Log search and storage system
~~~

When the log production rate exceeds the consumption rate, the number of pending items grows. At a certain threshold, the logging framework must decide whether to **block the calling thread, discard some events, or use an alternative write path**. The handling depends on the framework and configuration; **a full queue does not automatically mean log loss**.

For example: an application produces 6,000 events/second, while the appender can only write 4,000 events/second. If the buffer is initially empty and holds 8,000 events, the backlog grows by roughly 2,000 events/second. After about 4 seconds of sustained overload, the queue can fill up. This is an approximation that ignores rate fluctuations, event creation/writing overhead, and worker startup time.

In practice, there are other ways logs can be lost even when the queue is not full: level filters, sampling, file or network write errors, sudden process crashes, failure to flush on shutdown, a congested collector, or expired retention policies. Therefore, it is necessary to isolate the exact stage where log loss occurs.

## 2. Why Does Asynchronous Logging Easily Bottleneck at the Queue?

Queues have a finite size to prevent unbounded memory consumption. Common scenarios include:

- **Burst:** a sudden spike in requests or exceptions; log production surges for a few seconds.
- **Sustained overload:** the average enqueue rate exceeds the actual write capacity; no matter how large the queue is, it will eventually fill up if this persists.
- **Slow appender:** slow disk, full storage, stalled stdout, congested log collection agent, or unstable network.
- **Overly heavy logs:** excessive DEBUG/TRACE lines, long stack traces, CPU-intensive JSON conversion or serialization, generating large payloads per event.
- **Stuck or stopped worker:** I/O errors, deadlocks, shutdown without enough time to drain the queue, or the JVM being killed.

Queue length reflects the **backlog**, not the number of durably persisted logs. Successfully enqueuing an event only means a logging worker has the opportunity to process it later; it does not confirm that the event has been written to the destination.

## 3. Four Policy Groups When the Queue Is Full

| Policy | Behavior | Primary Impact |
| --- | --- | --- |
| **Block / backpressure** | Calling thread waits until space is available in the queue | Reduces drops due to a full queue, but increases latency and can slow down requests |
| **Drop / discard** | Discards new events or events based on priority level | Keeps the business path responsive, but loses observability data |
| **Timed offer** | Waits for a timeout and returns failure if still full | Bounds wait time; still requires handling rejected logs |
| **Fallback / synchronous write** | Routes the event to a backup appender or processes it on the calling thread when appropriate | Can preserve logs in some cases, but increases overhead and the backup target can also fail |

No policy can simultaneously guarantee **zero log loss** and **no latency impact** when incoming log volume exceeds consumption capacity over an extended period. If logs are not discarded and cannot be written faster, pressure must push back onto the producer.

Three points in time should be distinguished:

1. **Before enqueue:** events may be dropped by level/filter/sampling or by a discard policy when nearly full.
2. **At enqueue:** a `put` operation may wait; an `offer` may return `false`; the framework may switch to a fallback.
3. **After enqueue:** the worker may still encounter I/O errors, the process may terminate, or the log collector may fail to receive the data.

Do not use the log count shown on a dashboard as the sole evidence to conclude the queue is full; measure the number of events **produced, accepted, discarded, and actually delivered to the destination**.

## 4. Java 17+ Example: Full Queue and Discarded Events

The standalone example below uses `ArrayBlockingQueue` to accurately simulate the behavior of a **non-blocking strategy**: the producer calls `offer()`, receives `false` when the queue is out of space, and increments a `dropped` counter. To keep the output reproducible, the test does not start a worker; this is a model of the queue mechanism, not a production logging implementation.

Create **QueueOverflowDemo.java**:

~~~java
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class QueueOverflowDemo {
    public static void main(String[] args) {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(2);
        int accepted = 0;
        int dropped = 0;

        for (String event : List.of("event-1", "event-2", "event-3")) {
            // offer() does not wait: returns false when the queue is full.
            if (queue.offer(event)) {
                accepted++;
            } else {
                dropped++;
            }
        }

        System.out.println("accepted=" + accepted + ", dropped=" + dropped);
        System.out.println("queue=" + queue);

        // Simulate the worker consuming one event.
        System.out.println("consumed=" + queue.poll());
        System.out.println("retry=" + queue.offer("event-4"));
        System.out.println("queue=" + queue);
    }
}
~~~

Compile and run:

~~~bash
javac QueueOverflowDemo.java
java QueueOverflowDemo
~~~

Deterministic output of the example:

~~~text
accepted=2, dropped=1
queue=[event-1, event-2]
consumed=event-1
retry=true
queue=[event-2, event-4]
~~~

Explanation: the queue has a capacity of two elements, so `event-1` and `event-2` are accepted. When `event-3` arrives, `offer` returns `false`: if the producer ignores this return value, **`event-3` is lost right at the enqueue point**. After `event-1` is consumed, the queue has one slot free and accepts `event-4`. Removing an element **does not recover** `event-3`.

This is also a common bug in custom-built code: calling `queue.offer(event)` while ignoring the return value. If a discard policy is chosen, the discarded-event counter must be incremented at the exact point where the decision to drop the event is made.

## 5. Comparing offer(), put(), and offer(timeout)

With `java.util.concurrent.BlockingQueue`, the options have different semantics:

~~~java
// A. Non-blocking: false if full.
boolean accepted = queue.offer(event);

// B. Block until space is available (or interrupted).
queue.put(event);

// C. Wait up to 100 ms; false if still full when time expires.
boolean acceptedInTime =
        queue.offer(event, 100, java.util.concurrent.TimeUnit.MILLISECONDS);
~~~

The snippet above only illustrates the three methods on existing `queue` and `event` variables; **it is not a standalone compilable program**. `put()` and `offer(timeout)` can throw `InterruptedException`; calling code must handle this properly, typically by restoring the interrupt flag with `Thread.currentThread().interrupt()` and stopping or transitioning state appropriately. Do not swallow the interrupt exception and silently continue.

For production logging, consider the following:

- Unbounded blocking can slow down requests, cause timeouts, or stall the application if the downstream appender stops consuming; in some cases, recursive logging or lock contention can cause deadlocks.
- Timed `offer` bounds the wait time, but **still has a failure branch** that must be counted or handled with a fallback.
- Dropping reduces impact on requests but causes loss of trace data, which is especially dangerous if critical events are not properly classified.
- Synchronous fallback only helps when the backup destination is still operational; even a successful write to an appender API does not guarantee the data is durably persisted on disk or a centralized server.

Do not modify a framework's queue mechanism solely based on this example: logging libraries include additional level-based policies, specialized buffers, and dedicated shutdown procedures.

## 6. Logback AsyncAppender: Logs Can Be Dropped Even Before Full

With **Logback Classic AsyncAppender**, pay attention to an easily overlooked detail: the default configuration can **discard TRACE, DEBUG, and INFO events when the queue has less than about 20% remaining capacity**. This is a pre-full pressure-relief strategy, not a random Java bug.

Key properties:

| Logback Property | Meaning |
| --- | --- |
| queueSize | Maximum number of events that can wait (default 256) |
| discardingThreshold | Remaining-capacity threshold at which low-level events begin to be dropped; set to 0 to disable this early-discard behavior |
| neverBlock | Default `false`: blocks the calling thread when the queue is full; `true`: discards events when they cannot be enqueued |
| maxFlushTime | Maximum wait time, in milliseconds, for the worker to drain the queue on stop; `0` means wait indefinitely |

Thus, merely setting `neverBlock=false` is **not enough** to keep INFO/DEBUG events when the queue is nearly full; you must also check `discardingThreshold`.

Example **logback.xml** to reduce log loss caused by queue policies in an application that accepts backpressure:

~~~xml
<configuration>
  <appender name="FILE" class="ch.qos.logback.core.FileAppender">
    <file>logs/application.log</file>
    <encoder>
      <pattern>%d{ISO8601} %-5level [%thread] %logger{36} - %msg%n</pattern>
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

Prerequisites: the project has the appropriate Logback Classic dependency on the classpath; the XML snippet is framework configuration, **not compiled with javac**. The `logs/application.log` path requires valid storage and write permissions. A root level of `INFO` still filters out `DEBUG`/`TRACE` from the start; `discardingThreshold=0` **does not re-enable** log levels already disabled by the level filter.

The configuration above means: do not proactively drop low-level events just because the queue is nearly full; if full, the producer waits for space. However:

- When the appender writes slowly, request processing time still increases.
- `maxFlushTime=10000` allows up to about 10 seconds to drain on stop; once expired, unwritten logs may remain. Choose a value aligned with the system's graceful shutdown window.
- This configuration does not prevent log loss if the process is forcefully killed, the machine crashes, file I/O fails, or the downstream collector goes down.
- If `neverBlock=true` is set, the framework prioritizes not blocking the producer and **may lose events when the queue is full**, even if `discardingThreshold=0`.

To investigate the root cause, inspect Logback's internal status/logs, queue occupancy, appender write latency, the shutdown sequence, and the actual line count in the file.

## 7. Log4j 2: Distinguishing Async Appender and Async Logger

Log4j 2 has two different asynchronous modes:

- **Async Appender** uses a queue to forward logs to target appenders on a worker thread.
- **Async Logger** uses the LMAX Disruptor/ring buffer mechanism. Configuration parameter names and behavior across the two components are not identical.

For **Log4j 2 Async Appender**, the `blocking` attribute defaults to `true`; when the queue is full, producers normally wait according to the queue policy. If `blocking=false` is chosen, Log4j 2 can route events to an error appender when configured; without an effective fallback path, logs can be lost. `bufferSize` and `errorRef` can be configured as needed.

Example Log4j 2 configuration for blocking mode when the queue is full:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
  <Appenders>
    <File name="FILE" fileName="logs/application.log">
      <PatternLayout pattern="%d{ISO8601} %-5p [%t] %c - %m%n"/>
    </File>
    <Async name="ASYNC" bufferSize="8192" blocking="true"
           shutdownTimeout="10000">
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

This is a **log4j2.xml** for a project with the corresponding Log4j 2 Core dependency. Do not apply Logback properties such as `neverBlock` or `discardingThreshold` directly to Log4j 2 XML.

Log4j 2 also supports the global property **log4j2.asyncQueueFullPolicy** for async components. According to the Log4j 2.x documentation:

- **Default:** blocks the calling thread when the queue is full to wait for enqueue.
- **Discard:** drops events with a priority no higher than the configured threshold; **log4j2.discardThreshold** defaults to `INFO`, so TRACE/DEBUG/INFO may be discarded when full.

Only use `Discard` after clearly identifying which logs are acceptable to lose. When upgrading across major Log4j versions, verify property names against the documentation for the exact version in use. Queue policies cannot handle file storage failures or collector errors after dequeue.

## 8. Sizing the Queue Based on Real Load

Increasing `queueSize` can absorb a burst, but **does not increase write throughput**. Formula for estimating time to fill under roughly steady rates:

~~~text
t_full ≈ (capacity - current_backlog) / (produced_per_second - consumed_per_second)
         (applies only when produced_per_second > consumed_per_second)
~~~

For example, `capacity` = 8,000 events, initial `backlog` = 0, producer generates 6,000/s, and worker processes 4,000/s: the queue fills in about 4 seconds. Increasing `capacity` to 16,000 buys about 8 seconds; if the bottleneck remains, blocking/dropping still occurs after 8 seconds.

Trade-offs to weigh:

- **Memory footprint:** the queue holds event references and payloads; stack traces, message payloads, or referenced objects can consume far more heap than the element count alone suggests.
- **Observability delay:** a large queue causes logs to arrive at the search system later as the backlog grows.
- **Shutdown duration:** a larger backlog takes longer to drain.
- **Resources and log levels:** trimming noisy DEBUG/TRACE logs, rate-limiting logs inside loops, and avoiding repeated stack traces are usually more effective than growing the queue indefinitely.

To increase consumption capacity, measure the actual bottleneck: encoder, disk, stdout, network, appender, collector, or backend. You can optimize formatting, cut redundant logs, separate streams by log priority, upgrade I/O infrastructure, or choose a more suitable appender type.

## 9. Observing and Alerting Before Logs Are Lost

Add telemetry that is independent of the logging pipeline at risk of overload. If alerts themselves are only written to the same full queue, the alert messages may be lost too.

Signals to monitor:

| Signal | Interpretation |
| --- | --- |
| Queue occupancy = size / capacity | Percentage of the queue currently in use; also track peak values |
| Enqueue reject / discarded events | Number of events rejected or dropped by the discard policy |
| Producer blocked duration | Time threads spend waiting due to backpressure |
| Appender errors / retries | I/O, network, and encoding errors and retry counts |
| Drain rate / backlog age | Write throughput and age of queued events |
| Shutdown flush duration / remaining events | Ability to drain logs during graceful shutdown |

Do not assume every framework provides a built-in `discarded_count` metric: some libraries only expose status or current queue size. Check the actual API, version, and instrumentation options. If you must wrap the enqueue path yourself, place the counter in the branch that **actually drops the event**, avoiding miscounting events that were successfully handled by a fallback.

Alerting suggestions: queue stays above 70–80% over a measurement window, `discarded` rises above 0, producer wait spikes, or the appender emits continuous errors. These thresholds are only starting points and must be tuned against actual load and latency/SLO requirements. In particular, when Logback uses its default early-discard strategy, do not wait until the queue hits 100% before alerting.

## 10. How to Test Log Loss in a Controlled Manner

Run tests in a dedicated environment; never intentionally overload a production logging pipeline:

1. **Establish a baseline:** record the exact framework/version, `queueSize`, drop threshold, blocking setting, output target, shutdown timeout, and log level.
2. **Attach sequential IDs** to each test event (`test-run-id` + sequence number), and track the expected number of generated events.
3. **Short burst:** generate logs faster than the worker for a few seconds; measure max queue depth, reject/drop counts, and logging call latency.
4. **Sustained overload:** maintain a production rate above consumption capacity; verify that the queue hits its ceiling and the block/drop policy activates as configured.
5. **Slow down the appender:** in the test environment, simulate slow file/network writes to observe bottlenecks and backpressure building in the queue.
6. **Drain and shut down:** stop the producer and let the worker drain the queue; test graceful shutdown with a bounded timeout and check for remaining events.
7. **Reconcile results:** match generated sequence IDs against IDs confirmed at the destination (file/collector); distinguish duplicates caused by retries from genuinely missing events. Do not use asynchronous log ordering as the sole criterion if the pipeline can write or ingest out of order.

Example of a sound conclusion: "In test run A, 100,000 events were generated, 1,500 were rejected at enqueue, 98,500 reached the file, and 0 events remain queued," backed by counters and evidence. Concluding "1,500 events were lost because Elasticsearch only shows 98,500" is **insufficient**, because events may still be awaiting ingestion, filtered out, delayed in indexing, or outside the query window.

## 11. Handling Strategies by Log Criticality

**Routine diagnostic logs (DEBUG/INFO):** Controlled dropping can be acceptable to protect business latency, but dropped counts must be tracked and log levels tuned. Prioritize eliminating wasteful logs and optimizing the appender before adding more memory.

**ERROR logs for incident investigation:** Prioritize retention, using blocking/fallback or a dedicated priority path. However, a queue can still be overwhelmed by a flood of errors; do not assume WARN/ERROR logs can never be lost just because the framework prioritizes them by default.

**Mandatory audit, payment, and transaction data:** Do not rely on an in-memory asynchronous queue as the sole source of truth. Use an appropriate durable storage mechanism (database transaction, transactional outbox, durable broker, or dedicated audit system), with acknowledgments, retries, and deduplication per business requirements. Even synchronous logging to a standard appender does not automatically guarantee end-to-end durability.

**Shutdown:** Proactively close the `LoggerContext`/appender after stopping new work, allowing enough time to drain the queue within the container/service graceful termination window. Even with a shutdown hook, account for `kill -9`, power loss, OOM, or hardware failure. Setting `maxFlushTime` to infinity can prevent the system from exiting on time if downstream is stuck; setting it too short can leave the backlog undrained.

## 12. Common Configuration Mistakes and Misconceptions

- **"A full queue definitely means lost logs":** False; a blocking configuration can pause the producer and reduce the risk of drops due to a full queue.
- **"No logs are lost until the queue is 100% full":** False with early-discard policies, such as Logback `AsyncAppender` dropping TRACE/DEBUG/INFO by default as it nears capacity.
- **"Making the queue huge eliminates log loss":** It only extends burst tolerance; it does not solve sustained overload and can increase heap/GC pressure.
- **"No dropped counter means no drops":** Instrumentation may be missing, or logs may be lost at the worker, file, network, or collector stage.
- **"A successful `put` means the log is saved":** It only confirms enqueue, not that the sink has written it.
- **"Disabling discard is always better":** Backpressure can inflate response times, stall requests, or increase deadlock risk on certain calling threads.
- **"A large enough `maxFlushTime` guarantees no log loss":** Unclean shutdowns and I/O errors can still lose events.
- **"Error logs must always share the same policy as DEBUG":** Classify by criticality; data that must be durable requires a dedicated storage architecture.

## 13. Acceptance Checklist

An asynchronous logging system is intentionally configured when it clearly answers the following questions:

- How many events is the queue or ring buffer bounded to, and what are the actual backlog and peak occupancy?
- When nearly full or full, which events are dropped, which threads are blocked, and is there a fallback?
- How are ERROR events, retries, shutdown, and downstream outages handled?
- Can discarded events and backpressure-induced latency be observed without depending on the congested queue itself?
- Have bursts, sustained overload, slow appenders, and shutdown been tested, with sequence IDs reconciled at the destination?
- Has mandatory durable audit data been separated from routine observability logging?

**Conclusion:** Reducing log loss when the queue is full requires combining input log volume control, appender throughput capacity, appropriate block/drop policies, and observability. Anti-drop configuration at the enqueue point only addresses one stage of the log pipeline; strict zero-loss requirements demand a dedicated durable storage mechanism.

## References

- [Logback Manual — AsyncAppender](https://logback.qos.ch/manual/appenders-async-sift.html): `queueSize`, `discardingThreshold`, `neverBlock`, `maxFlushTime`, and shutdown.
- [Apache Log4j 2 — Async Loggers](https://logging.apache.org/log4j/2.x/manual/async.html): async logger model, ring buffer, queue-full policy, and trade-offs.
- [Apache Log4j 2 — Delegating Appenders](https://logging.apache.org/log4j/2.x/manual/appenders/delegating.html): Async Appender, `blocking`, `bufferSize`, `errorRef`, `shutdownTimeout`.
