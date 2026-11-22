# Queue Full in Java Logging: Handling Saturation and Ensuring Reliability

## 1. What Is a Full Queue?

In **asynchronous logging**, business threads typically do not write the entire event to a file or network themselves. Instead, they create a log event and place it into a **queue**, and a background worker pulls events out to write them to a sink.

```text
Business threads           Logging thread              Destination
      |                          |                           |
      |---- create event ------->|                           |
      |---- enqueue ----------> [bounded queue]               |
      |                          |--- dequeue / format ------>|
      |                          |                           | file/stdout/network
      |
      +-- if queue is full: wait / drop log / timeout / fallback?
```

**Queue saturation (queue full)** occurs when a bounded queue already holds the maximum number of allowed elements, so it cannot accept additional events via a non-blocking enqueue. This usually happens because **the log production rate exceeds the consumption rate**, or because the consumer is stalled.

In **logging reliability**, two distinct questions must be asked:

1. When the queue is full, **can a log call lose events or slow down business logic**?
2. If the queue accepts an event, **has the log actually been written or durably persisted**?

The answer to (2) is **not "yes" by default**. An in-memory queue is merely a buffer; a successful enqueue does not mean the file has finished writing, the collector has acknowledged receipt, or the event can survive a crash.

A full queue is also different from:

- **Logs filtered by level:** Disabling DEBUG may prevent an event from being created at all, which is not a queue error.
- **Sink failure:** A file or collector can fail even when the queue is not full; the queue will fill up if the consumer cannot process events fast enough.
- **OutOfMemoryError:** A bounded queue can fill up before the heap is exhausted. An unbounded queue, on the other hand, easily allows the backlog to grow until memory runs out.
- **Disk full:** Running out of disk space for logs is a sink-level failure; it can lead to a full queue, but it is not the same concept.

## 2. Why Does a Queue Become Full and What Are the Consequences?

Common causes include:

- A burst of WARN/ERROR logs in retry loops or repeated exceptions generating too many events.
- Enabling TRACE/DEBUG service-wide in production, causing each request to emit more logs than expected.
- File write paths throttled by I/O limits, slow rotation, a hung filesystem, or nearly full disk space.
- A slow, disconnected, or rate-limited log shipper, network, or collector.
- Logging worker pauses due to CPU, GC, contention, or an unrecoverable error.
- A single shared queue aggregating multiple log sources, where a noisy source starves important events of space.

The consequences depend on the enqueue policy:

| State | Possible Behavior | Impact |
| --- | --- | --- |
| Queue has space | Fast enqueue, worker writes later | Logs experience latency; crash risk remains before writing |
| Queue full + producer waits | Thread calling the logger blocks | Increases latency, ties up threads, can cascade failures to APIs |
| Queue full + drop event | Logger call returns quickly | Partial log loss, potentially losing data needed for investigation |
| Queue full + bounded wait | Waits until a deadline, then decides | Enforces a latency budget, but still requires timeout handling |
| Queue full + synchronous fallback write | Producer writes directly to the sink | May preserve more logs; slow I/O path returns to the business thread |
| Queue full + spill to durable buffer | Writes through a separate durable queue | Improves resilience, but introduces overhead and other failure limits |

**There is no free policy:** trying to avoid losing any event by blocking indefinitely can bring down the main service; trying to preserve latency by dropping logs can lose critical data. The decision must be based on SLOs, log criticality, and sink capacity.

## 3. The Rate Problem: When Will the Queue Fill Up?

Let:

- `λ`: the rate at which producers generate logs (events/second).
- `μ`: the rate at which the worker and sink consume logs (events/second).
- `C`: queue capacity (number of events).
- `q₀`: number of events currently in the queue at the start.

If `λ > μ` persists, the backlog tends to grow approximately as:

```text
backlog growth per second ≈ λ - μ
remaining slots           ≈ C - q₀
time until full           ≈ (C - q₀) / (λ - μ)
```

Example: a queue has 4,000 slots and currently holds 1,000 events. Producers emit 1,200 events/second, while the consumer writes 900 events/second. There are 3,000 slots remaining; the backlog grows by roughly 300 events/second, so **the queue is estimated to fill up in 10 seconds** if conditions remain unchanged.

This is a simplified model; in practice, rates vary with bursts, event types, stack trace sizes, formatting, GC, and the write path. If the consumer stops making progress (`μ ≈ 0`), the queue will fill up even faster.

**Increasing the queue size only delays saturation**; it does not fix a sustained `λ > μ` condition. A large queue also retains many objects:

```text
event data memory ≈ number of events in queue × average size per event
```

Example: 8,000 events × 1 KiB ≈ 7.8 MiB of data, **excluding overhead for objects, references, strings, and context data**. Events with exception stack traces or large payloads can be much heavier.

## 4. Java 17: Simulating a Full Queue with ArrayBlockingQueue

To understand the full-queue condition properly, start with an `ArrayBlockingQueue` that has a **fixed capacity**. This is a standalone program simulating only the producer enqueue and consumer dequeue steps, not a complete logging backend.

Save the file **`QueueFullDemo.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class QueueFullDemo {
    public static void main(String[] args) {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(2);

        boolean first = queue.offer("INFO app-started");
        boolean second = queue.offer("DEBUG cache-check");
        boolean third = queue.offer("WARN retry");

        System.out.println("first accepted: " + first);
        System.out.println("second accepted: " + second);
        System.out.println("third accepted: " + third);
        System.out.println("depth: " + queue.size());

        System.out.println("consumer 1: " + queue.poll());
        System.out.println("consumer 2: " + queue.poll());
        System.out.println("depth after drain: " + queue.size());
        System.out.println("retry accepted: " + queue.offer("WARN retry"));
    }
}
```

Compile and run:

```bash
javac QueueFullDemo.java
java QueueFullDemo
```

`stdout` output:

```text
first accepted: true
second accepted: true
third accepted: false
depth: 2
consumer 1: INFO app-started
consumer 2: DEBUG cache-check
depth after drain: 0
retry accepted: true
```

Because only a single thread operates on the queue, the output order is **deterministic**:

1. The 2-slot queue accepts the first two events.
2. The third `offer` immediately returns `false` because the queue is full.
3. The simulated consumer calls `poll()` to drain the events.
4. Once space is available, the new `offer` is accepted.

**If `false` is ignored, the third event is lost on the producer side.** A production logging system must explicitly define what to do with rejected events and measure how many are dropped. Avoid "infinite retries" without bounds, because a congested sink can cause the retry loop itself to generate extra load.

This demo program does not prove that logs were written to disk: `poll()` only removes strings from the queue, and printing to the terminal is not a durability guarantee either.

## 5. BlockingQueue Operations and Overflow Policies

Java provides several APIs with different semantics:

| API | When Queue Is Full | Usage Guidance |
| --- | --- | --- |
| `offer(event)` | Returns `false` immediately | Non-blocking; must count drops or fall back |
| `put(event)` | Blocks until space is available or interrupted | Prioritizes not dropping due to a full queue, but can stall requests |
| `offer(event, timeout, unit)` | Waits up to timeout, then returns `false` if still full | Bounds latency; define a clear policy when the timeout expires |
| `add(event)` | Throws `IllegalStateException` if full | Usually unsuitable as the default for writing logs |
| `remainingCapacity()` | Returns a snapshot of remaining slots | Reference metric only; cannot replace checking the enqueue result |

### 5.1. Dropping New Events: drop-new

```java
// Integration example code: queue is a BlockingQueue<LogEvent>,
// droppedEvents is a counter, and event is an immutable snapshot.
if (!queue.offer(event)) {
    droppedEvents.increment();
}
```

Pros: low waiting overhead, queue does not grow unboundedly. Cons: important events can be lost, including WARN/ERROR if all levels share the same queue without a prioritization mechanism.

**The counter must be independent** of the saturated logging pipeline itself. If you use `logger.warn("Dropped event")` to record drops, that warning may also be dropped or make the situation worse.

### 5.2. Blocking the Producer: block

```java
// Integration example code; will not run standalone without queue/event.
try {
    queue.put(event);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // The policy for handling the un-enqueued event must be explicitly decided.
}
```

Strengths: reduces event loss caused by a temporarily full queue while the consumer continues processing. Weaknesses:

- A logger call running on a **request thread** can block while holding locks or while on a critical request path.
- Many blocked requests cause worker starvation, timeouts, retries, and cascading failures.
- If the consumer can permanently no longer write or has stopped, `put` may make no progress.
- `InterruptedException` should not be silently swallowed; restore the interrupt flag and handle the unaccepted event.

### 5.3. Bounded Wait

```java
// Integration snippet requiring queue, event, and droppedEvents.
try {
    boolean accepted =
            queue.offer(event, 20, TimeUnit.MILLISECONDS);
    if (!accepted) {
        droppedEvents.increment();
    }
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    droppedEvents.increment();
}
```

You need to import `java.util.concurrent.TimeUnit` and declare the variables according to your system. **20 ms is only an example**, not a universal recommended threshold. The wait time must fit within your business p95/p99 latency budget.

Note: increasing the timeout does not increase sink throughput. Nor does a timeout guarantee that the event has finished writing; it only bounds the time spent **waiting to enter the queue**.

### 5.4. Do Not Decide Based on Checking size() Before Calling put()

A common mistake:

```java
// Prone to race conditions when there are multiple producers:
if (queue.remainingCapacity() > 0) {
    queue.put(event);
}
```

After the check, another producer can take the slot. `put` can still block. Always rely on the return value or outcome of `offer`, `put`, or `offer(timeout)` to make decisions.

## 6. Java 17: Demonstrating put() Waiting When the Queue Is Full

The example below creates a queue with capacity 1, pre-populates one element, and then has a second producer thread call `put()`. The main thread keeps the queue full until it calls `take()` on the first element; only then can the producer insert the new event.

Save the file **`BlockingQueueLogDemo.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;

public class BlockingQueueLogDemo {
    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(1);
        queue.put("INFO first");

        CountDownLatch producerStarted = new CountDownLatch(1);
        Thread producer = new Thread(() -> {
            try {
                producerStarted.countDown();
                queue.put("ERROR second");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "log-producer");

        producer.start();
        producerStarted.await();

        System.out.println("queue full: " + (queue.remainingCapacity() == 0));
        System.out.println("third accepted: " + queue.offer("DEBUG third"));

        String first = queue.take(); // Free up a slot for the waiting producer.
        producer.join();

        System.out.println("taken first: " + first);
        System.out.println("taken second: " + queue.take());
    }
}
```

Compile and run:

```bash
javac BlockingQueueLogDemo.java
java BlockingQueueLogDemo
```

`stdout` output when not externally interrupted:

```text
queue full: true
third accepted: false
taken first: INFO first
taken second: ERROR second
```

Here, `CountDownLatch` only guarantees that the producer has entered the start of its work; **it does not guarantee that the scheduler has advanced it to the exact `put` call** before main checks the queue. What matters is still guaranteed: the queue is initially full, `offer("DEBUG third")` fails, and `ERROR second` can only be accepted after `take()`. `join()` ensures that main does not print the subsequent lines before the producer finishes.

This example simulates **producer blocking**, not actual log writing. It shows that "choosing to block" can delay the producer until the consumer frees a slot; the actual wait duration depends on the health of the sink.

## 7. Overflow Policies and Reliability Trade-offs

### 7.1. Drop-new

**Drop-new** rejects incoming events when the queue is full. This can be reasonable for high-volume DEBUG/TRACE logs, but dangerous if all events share the same policy.

Pros: keeps producer latency low. Trade-off: loses the newest information, potentially dropping the very error event that just occurred.

### 7.2. Drop-oldest

Some designs evict older events to make room for new ones. This prioritizes recency but can erase the sequence of events **leading up to an error**. `BlockingQueue` does not natively provide a global drop-oldest policy via `offer` alone; if you implement one, it must be synchronized/race-safe to avoid corrupting ordering or losing events unintentionally.

Do not assume "dropping the oldest is safe." In particular, audit or transaction logs may require strict order preservation.

### 7.3. Level-Based Discarding or Sampling

Reduce load before the queue fills up by disabling TRACE/DEBUG, sampling repetitive INFO logs, rate-limiting a recurring error pattern, or separating channels with different priorities. Distinguish **intentional filtering** from **overload-induced log loss** so metrics remain clear.

WARN/ERROR logs are not protected merely by having a higher level if the backend chooses to drop all events when the queue is full; you must understand the actual discarding and enqueue mechanics.

### 7.4. Synchronous Fallback

Some backends have a policy where, if enqueueing fails, **the producer writes synchronously itself** or switches to another appender. This can save some logs, but it brings slow I/O back onto the business thread. If the sink is hung, the "fallback" is no longer fast.

Use this only when you clearly understand the blocking bounds, sink error handling, duplicate-write risk, and lifecycle of the secondary appender.

### 7.5. Durable Buffers and Dedicated Queues

If a category of logs **must be preserved** for business, security, or audit reasons, do not rely solely on the logging backend's in-memory queue. You may need:

- Records persisted alongside the transaction or via a transactional outbox where appropriate.
- A durable event queue with retry, acknowledgment, retention, and quota policies.
- Access control, integrity protection, and reconciliation processes.
- A policy for handling situations when the durable store itself becomes full or unavailable.

Every solution involves trade-offs in latency, complexity, ordering, and cost. **Never promise "exactly once"** simply because retries exist; retries can produce duplicates, requiring IDs and idempotency on the receiving side.

## 8. Logback AsyncAppender When the Queue Is Full

For applications using **SLF4J + Logback Classic**, `ch.qos.logback.classic.AsyncAppender` places a bounded queue in front of the appender that actually writes logs. Key properties related to reliability include:

- `queueSize`: maximum number of events in the queue.
- `discardingThreshold`: remaining-space threshold at which Logback proactively discards lower-severity events according to AsyncAppender Classic's default policy.
- `neverBlock`: determines whether enqueueing blocks when the queue is full.
- `maxFlushTime`: maximum time the worker waits to drain the queue when the appender stops.
- `includeCallerData`: whether to collect caller data, affecting event processing cost.

Example configuration at `src/main/resources/logback.xml`:

```xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} [%thread] %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ASYNC"
              class="ch.qos.logback.classic.AsyncAppender">
        <queueSize>1024</queueSize>
        <discardingThreshold>0</discardingThreshold>
        <neverBlock>false</neverBlock>
        <maxFlushTime>5000</maxFlushTime>
        <includeCallerData>false</includeCallerData>
        <appender-ref ref="STDOUT"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="ASYNC"/>
    </root>
</configuration>
```

**This is a configuration example for a project with a compatible Logback Classic version**, not a standalone Java program. Meaning:

1. The queue holds **1,024 events**, not 1,024 bytes.
2. `discardingThreshold=0` disables **early discarding** of low-level events based on remaining queue space; it does not make logs durable.
3. `neverBlock=false` allows logger calls to **block when the queue is truly full** until space opens up. This trade-off prioritizes not dropping events due to a full queue while the worker is still running.
4. `maxFlushTime=5000` sets a **5,000 ms** flush budget during appender shutdown. If flushing does not finish in time, pending events can still be lost. With `maxFlushTime=0`, Logback's shutdown mechanism waits indefinitely for the worker to finish.
5. `includeCallerData=false` avoids the overhead of capturing caller location data and does not change the full-queue policy.

In Logback Classic, the default discarding threshold is typically tied to **20% of queue capacity**. When the queue nears capacity, Logback may drop **TRACE/DEBUG/INFO** events first to prioritize higher levels. However:

- `discardingThreshold=0` only disables **early discarding**; it does not prove events will never be lost.
- If `neverBlock=true` is set, enqueueing when the queue is already full can drop **even WARN/ERROR**. Thus, `neverBlock=true` prioritizes latency over log completeness.
- `neverBlock=false` when the worker is stuck can cause **backpressure back onto request threads**.
- JVM crashes, forced kills, sink failures, or insufficient shutdown time can still lose data that has not reached its destination.
- Exact behavior should be verified against your **actual Logback version and appender**.

There is no single `queueSize`/`neverBlock`/`maxFlushTime` combination that fits every system. For example, high-volume operational logs may tolerate sampling/dropping, whereas audit logs require a dedicated durable persistence pipeline.

### 8.1. When neverBlock Is Enabled

A configuration choosing latency over blocking the producer:

```xml
<!-- Placed inside the AsyncAppender above. -->
<neverBlock>true</neverBlock>
```

This is just an **XML snippet**. When the queue is full, producers can return faster by not waiting for a slot, but events that fail to enqueue may be discarded. Do not treat a normal return from a logger method as proof that the log was written.

### 8.2. Does Logback Guarantee Keeping ERROR Logs?

You should not make an absolute guarantee. The early-discarding policy may prioritize WARN/ERROR over DEBUG/INFO, **but** when the queue is full and `neverBlock=true` is selected, a high-severity event can still be rejected. With `neverBlock=false`, producers can block indefinitely if the consumer stops making progress. Neither option protects against crashes or downstream failures.

If ERROR logs must be preserved for operations, combine this with independent metrics/alerts and write critical events through an appropriately reliable channel rather than relying solely on log level selection.

## 9. Log4j 2 and Other Backends

**Log4j 2 Async Logger** and **Log4j 2 AsyncAppender** have their own internal asynchronous mechanisms and bounds. For example, Async Logger typically uses a **ring buffer**; the queue/ring-buffer full policy can choose to wait, run logging on the caller thread, or discard depending on configuration and version.

When investigating Log4j 2:

1. Identify whether you are actually using **Async Logger**, **AsyncAppender**, or a combination, as the two behave differently.
2. Check the buffer capacity/element count, queue-full policy, filters, and discard thresholds for your **exact version**.
3. Check whether an event logged from a business thread can be pushed onto a synchronous path under overload.
4. Test throughput, latency, and the number of logs actually reaching the sink; do not infer behavior from the word "Async."
5. Evaluate shutdown and collector connectivity; an event sitting in a ring buffer is still not durably persisted.

Do not copy Logback's `neverBlock`/`discardingThreshold` settings into Log4j 2: the properties and mechanisms are different. For **`java.util.logging` (JUL)**, standard handlers typically process synchronously by design; the queue-logging concepts discussed here only apply if the application or a library adds an asynchronous queue.

## 10. "Enqueued" Does Not Mean "Written"

Log reliability can be viewed in layers:

```text
event created
    |
    v
accepted by in-memory queue
    |
    v
dequeued by logging worker
    |
    v
accepted by local file / stdout / network client
    |
    v
received by collector
    |
    v
persisted / replicated / acknowledged according to the sink
```

Success at one layer **does not automatically prove** success at subsequent layers. For example:

- The logger accepts an event, and then the JVM crashes before the worker dequeues it.
- The worker passes the event to `stdout`, but the container/process terminates before the agent can collect it.
- The HTTP client reports a successful send, but the collector only buffered it in memory and has not persisted it durably.
- Retrying after a timeout can create **duplicate records** even though the initial event actually reached the destination.

For files, calling `write()` or `flush()` does not automatically mean data has been durably synced to the storage device in every scenario; you must distinguish user-space buffers, the OS page cache, and `fsync` when true durability is required.

**Reliability targets must be explicitly stated**: best-effort diagnostic logs, at-most-once, at-least-once with duplicates, or a durable audit workflow. Avoid using the phrase "guaranteed zero log loss" if the implementation is just an in-memory queue with graceful shutdown.

## 11. When a Queue Contains Multiple Log Levels

If all logs share a single queue, a flood of DEBUG/INFO events can crowd out WARN/ERROR. Strategies to consider:

- Lower the log level at the source for overly noisy loggers.
- Apply sampling or rate limiting to repetitive messages.
- Use filters that preferentially drop less critical events before saturation, as supported by the backend.
- Isolate audit/security logs into a separate pipeline with its own queue and durability requirements.
- Avoid exploding exception stack traces for the same error inside retry loops.
- Set explicit limits on both event count and event size; a single large event can exert more memory/I/O pressure than hundreds of short ones.

**Separating queues does not automatically create absolute reliability**: queues may still share the same JVM, disk, network, and collector. Verify whether they are truly independent at critical failure points.

You can prioritize WARN/ERROR logs on a dedicated channel, but if they contain sensitive data, you still need to protect that information before sending it to another sink. High severity does not override privacy requirements.

## 12. Monitoring: Detecting Queue Saturation Before Log Loss Occurs

A well-designed system should measure not only "whether logs exist" but also the production, queuing, and delivery stages:

| Suggested Metric | Meaning |
| --- | --- |
| `logging_queue_depth` | Number of events currently waiting |
| `logging_queue_capacity` | Capacity of the bounded queue |
| `logging_queue_utilization` | Percentage of the queue currently occupied |
| `logging_events_enqueued_total` | Total events accepted by the queue |
| `logging_events_dropped_total{reason,level}` | Total events dropped by reason/level |
| `logging_enqueue_wait_seconds` | Time producers spend waiting during enqueue |
| `logging_sink_write_seconds` | Latency of writing to the sink |
| `logging_sink_failures_total` | Errors writing/sending to the sink |
| `logging_oldest_event_age_seconds` | Age of the oldest event still waiting |
| `logging_worker_alive` | Health/liveness status of the queue worker |

These are **suggested metric names**, not default metrics across all backends. If a framework does not expose them, instrument the appender appropriately or observe them at the collector. Metric label names should have bounded cardinality, such as `route`, `level`, and `reason`; avoid using messages, request IDs, or user IDs as labels due to high cardinality.

Signals to monitor together:

1. Queue depth **growing steadily** even after traffic returns to normal.
2. High utilization sustained for several minutes or rising abnormally fast.
3. Rising drop counts—especially for WARN/ERROR, security, or audit logs.
4. Increasing p95/p99 enqueue wait times driving up request latency.
5. Increasing sink errors, disk usage, collector lag, or network retries.
6. Increasing event age in the queue, meaning logs appear later than when they occurred.
7. A dead worker or a backlog that does not drain even under low load.

**Do not use a congested logger to emit metrics warning that the queue is full**: that alert itself may be blocked or dropped. Metrics, health signals, or admin channels must have an appropriately independent observation path.

## 13. Shutdown, Crashes, and Queue Draining

### 13.1. Graceful Shutdown

When stopping an application, a solid shutdown sequence typically requires:

1. Stop accepting new requests or block new producers at an appropriate boundary.
2. Allow in-flight tasks to complete within a reasonable window.
3. Signal the logging worker to stop accepting new events in an orderly fashion.
4. Drain the queue and flush/close application-owned sinks.
5. Enforce a shutdown timeout and track remaining un-drained events if draining does not finish in time.

The exact lifecycle belongs to the framework/backend. For example, in Logback, `LoggerContext.stop()` participates in stopping appenders; this should run through the application's standard lifecycle. Do not arbitrarily call `System.exit()` while events remain in the queue and expect all logs to appear.

### 13.2. Cases Where Draining Cannot Be Guaranteed

A JVM killed with `kill -9`, a power outage, an OS crash, a severe OOM, or a forcibly terminated container may **not execute shutdown hooks** and will not drain the queue. Therefore, "block when full + flush on shutdown" is still not a durability guarantee.

If you need to preserve transactional or audit data, design an acknowledged write mechanism with recovery capabilities rather than relying entirely on JVM memory.

### 13.3. Avoiding Indefinite Shutdown Hangs

Waiting indefinitely to drain can reduce pending event loss in some cases, but a hung sink can prevent shutdown from ever finishing. Service shutdown SLOs, orchestration timeouts, and failure policies must align. When forcing termination after a deadline, explicitly document that backlogged logs may not have been written.

## 14. Testing Full Queues and Log Loss Scenarios

Test in a non-production environment or against a simulated slow sink with measurable baselines:

| Test Case | What to Verify |
| --- | --- |
| Short burst | Queue grows and drains; does not degrade latency beyond SLO |
| Sustained high load | Queue fills after a period; block/drop/timeout policy behaves as designed |
| 10× slow sink | How long producers block; which logs are dropped; how long recovery takes |
| Completely unresponsive sink | Errors are reported, metrics increment, and request paths remain protected |
| DEBUG burst + ERROR | Whether ERROR is prioritized according to the committed policy |
| Runtime log level change | Whether it unexpectedly increases load or fills the queue |
| Normal shutdown | How much pending backlog drains within the shutdown budget |
| Forced kill | Quantify data loss and verify reconciliation capability |
| Collector recovery | Whether retries cause duplicate logs, out-of-order logs, or backlog spikes |

A practical test scenario:

1. Start a test instance with a small bounded queue and tag events with deterministic IDs.
2. Introduce controlled slowness in the sink; inject a known number of events.
3. Record **events created by producers**, **events accepted by the queue**, **events dropped**, **events acknowledged by the sink**, and **final records actually persisted**.
4. Observe both **request latency** and **enqueue wait time**.
5. Restore the sink and wait for the queue to drain using synchronization signals or real metrics instead of arbitrary `Thread.sleep(...)` calls.
6. Compare counts, missing IDs, and duplicate IDs against the designed policy.

Without ordering guarantees or atomic fan-out, different routes may receive different subsets of events. Never use "the logger was called 1,000 times" as proof that "1,000 records were saved."

## 15. Production Incident Response for a Full Queue

When monitoring indicates the queue is nearing saturation:

1. **Isolate the destination:** check disk latency/disk-full, stdout collector, network, agent, log ingestion service, and errors around the time the backlog began.
2. **Identify the log storm source:** which packages are emitting excessive INFO/DEBUG, whether retry errors are looping, and whether stack traces are bloating.
3. **Measure business impact:** p95/p99 latency, requests blocked in the logger, thread pools, CPU/GC, and drop counts.
4. **Shed load in a controlled manner:** adjust levels on noisy loggers, sample/rate-limit repetitive messages, fix bugs causing log storms; record timestamps when DEBUG is toggled.
5. **Restore consumption capacity:** fix disk/collector/network issues and scale infrastructure where justified.
6. **Consider changing the overflow policy:** if blocking is making the service unresponsive, any alternative must be explicitly accepted along with its log-loss risk.
7. **Post-incident reconciliation:** document the time window of missing logs, affected routes, drop counts, and gather supplementary evidence from independent sources.

Simply increasing `queueSize` on the spot is usually a **delaying tactic** that does not solve a sustained bottleneck. If you have not identified why the sink is slow, a larger queue can overload the heap and mask the incident for longer.

## 16. Common Pitfalls

### "A full queue means all logs were lost"

Not necessarily. With a block policy, producers may wait until a slot opens. With drop-new, only events that fail to enqueue are discarded; events already in the queue can still be written by the worker. Measure each behavior separately.

### "An unbounded queue will never fill up, so it is safe"

An unbounded queue can grow until the JVM runs out of memory; it is not a sustainable reliability strategy. Bound capacity according to your RAM budget and define a clear overflow policy.

### "Blocking means you never lose logs"

Blocking can prevent drops caused by full slots while the consumer is alive, but it does not protect against process crashes, disk failures, collector loss, forced shutdowns, or consumer exceptions. It can also stall requests.

### "With neverBlock=true, WARN/ERROR are still guaranteed safe"

Incorrect for Logback AsyncAppender once the queue is already full. Early discarding typically favors WARN/ERROR, but a non-blocking enqueue policy can still drop high-severity events.

### "Calling the logger means it is saved"

False for async logging: a call may only create an event, or it may be filtered out before reaching the queue. Even a successful enqueue does not prove durable storage.

### "Monitoring queue size alone is enough"

Queue size is just a snapshot. Drop counts, enqueue latency, queue age, sink errors, rates, and backlog recovery reflect the actual impact. A nearly empty queue could mean a healthy sink—or that events are being dropped early.

### "Counting drops using the same failing appender"

The summary warning may also be lost and will generate even more events. Use an independent counter/metric with a separate monitoring path.

### "Adding infinite retries prevents any log loss"

Infinite retries can inflate the queue, cause duplicates, block requests, and generate more error logs. Use retry budgets, backoff, durable storage where appropriate, and idempotency at the receiver.

### "One configuration fits both audit and debug logs"

Unsuitable when requirements differ. DEBUG logs can be sampled or dropped; audit logs may require transactions, durability, retention, access control, and separate reconciliation.

## 17. Pre-Deployment Design Checklist

- [ ] Determine average/peak producer rates, sustainable sink throughput, and event sizes.
- [ ] Choose a **bounded** queue, memory budget, latency limits, and full-queue policy.
- [ ] Clarify which events may be dropped and which require prioritization or durable storage.
- [ ] Verify your actual backend/framework and the exact semantics of `neverBlock`, discarding, timeouts, and flushing.
- [ ] Prevent DEBUG/INFO levels from consuming resources meant for critical business logs without an explicit decision.
- [ ] Instrument metrics: enqueued, dropped, queue depth, oldest age, enqueue latency, sink errors.
- [ ] Test slow sinks, failing sinks, sustained saturation, recovery, shutdown, and forced kills.
- [ ] Distinguish accepted, written, acknowledged, and durable; do not overpromise beyond what the pipeline delivers.
- [ ] Maintain a recovery runbook and a way to reconcile missing/duplicate log counts after an incident.

**Conclusion:** A full queue is a symptom that **the logging pipeline cannot keep up**. Improving reliability requires more than just increasing capacity: you must define explicit policies per event type, measure blocked and dropped logs, understand how the sink fails, and verify shutdown behavior. For data that must be preserved, **an async logger's in-memory queue cannot replace an acknowledged durable write mechanism**.
