# Out-of-Order Logs in Java Logging

## 1. Understanding the Phenomenon

Suppose an order request has the following business steps: receive request → check inventory → process payment → complete. Readers usually expect logs to appear in that same order. However, on the dashboard, you might see:

```text
10:00:00.105 INFO  payment completed order=42
10:00:00.103 INFO  payment started order=42
```

This situation is called **out-of-order logging**. Seeing two lines reversed in the UI **is not sufficient proof** that the business logic processed the payment successfully before starting it. You must distinguish between **when the event occurred**, **when the logger created the event**, **when the appender wrote it**, and **when the collection system displayed it**.

Java Logging can use JUL, SLF4J with Logback, Log4j 2, or a bridge to OpenTelemetry. These frameworks typically pass a log event through one or more layers: logger, filter, appender, queue, file/console/network, Collector, and backend. Each layer can add latency or alter the **order observed by the user**.

The goal of this article is to understand when log reordering is normal, when it reflects a race condition or log loss, and how to record enough evidence to reconstruct a meaningful order.

## 2. Six Types of Order to Distinguish

| Order | Definition | Example |
| --- | --- | --- |
| **Business** | Required relationship between processing steps | Must authenticate before accepting payment |
| **Execution** | Order of actions on one or more threads | Thread A runs before or after thread B |
| **Event creation** | Time when the logger generates the log event | Calling `logger.info(...)` |
| **Enqueue** | Time when the event is accepted into an asynchronous queue | `AsyncAppender` receives the event |
| **Sink write** | Order in which the appender sends events to console/file/remote | File writer writes event 2 before event 1 |
| **Display/ingest** | Order in which the Collector/backend receives and sorts records | Dashboard sorts by ingestion time |

```text
Thread A ─ logger.info(A) ─┐
                          ├─> Logger/Filter ─> Queue ─> Appender ─> Sink
Thread B ─ logger.info(B) ─┘                                    │
                                                           Collector
                                                                │
                                                        Export / Retry
                                                                │
                                                          Backend UI
```

Seeing a log first on the dashboard only tells you **how the backend sorted the records**. It does not by itself prove that the log was created before all other logs.

A good diagnostic question must be scoped: *"Within the same request and the same log file, why did the event with sequence 2 appear before sequence 1?"* That question is much more accurate than *"Why are the logs across the whole system out of order?"*

## 3. Thread Scheduling and the Java Memory Model

Within a single thread executing sequentially, method call order is determined by program order:

```java
log.info("STEP 1: validate");
validateOrder();
log.info("STEP 2: reserve");
reserveStock();
log.info("STEP 3: done");
```

This is an **illustrative snippet inside a class that already declares a logger and business methods**, not a standalone program compiled directly with `javac`. Without exceptions or other control-flow changes, the call to STEP 1 occurs before STEP 2 and then STEP 3 **within the same thread**. However, if those events are written to sinks with different latencies, the centralized display order may still differ from the call order.

With multiple threads, there is no natural total order for all actions:

```text
Time ────────────────────────────────────>
Thread A: A1 --------- A2 ------ A3
Thread B:     B1 --- B2 ------------ B3
```

The scheduler can interleave A and B. In practice, you might observe A1, B1, B2, A2... without any bug. Only when the application has a specific requirement on a before/after relationship—for example, A2 must complete before B2—do you need an appropriate synchronization mechanism.

**Happens-before** in the Java Memory Model describes ordering/visibility guarantees established by rules such as program order, `synchronized`, `volatile`, `Thread.start()`, `Thread.join()`, and concurrency utilities. It does not automatically make every queue, disk, stream, and network respect a global display order.

### 3.1. Submitting First Does Not Guarantee Completing First

`CompletableFuture` can run tasks concurrently:

```java
CompletableFuture<Void> a =
        CompletableFuture.runAsync(() -> log.info("task A"));
CompletableFuture<Void> b =
        CompletableFuture.runAsync(() -> log.info("task B"));
CompletableFuture.allOf(a, b).join();
```

The snippet above belongs to a class with an SLF4J logger and requires importing `java.util.concurrent.CompletableFuture`. A is submitted before B, but B may execute first. `allOf(...).join()` only waits for both to complete.

If the business logic requires A before B, you must express the dependency:

```java
CompletableFuture<Void> sequential =
        CompletableFuture.runAsync(() -> log.info("task A"))
                .thenRun(() -> log.info("task B"));
sequential.join();
```

`thenRun` runs after the previous stage completes normally. This fixes the execution relationship, not as a trick to change log formatting. If task A fails, stage B may not run; that is semantics you need to account for.

## 4. Java 17+ Example: Source 1 → 2, Output 2 → 1

The following program demonstrates **two independent logging paths**, each with a queue and a writer. The producer sends event 1 before event 2, but the slow path intentionally waits for the fast path to finish. As a result, the output displays event 2 before event 1. This is a **conceptual model**, not a production logger.

Create `LogOrderDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;

public class LogOrderDemo {
    private record Event(int sequence, String message) {}

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<Event> slow = new ArrayBlockingQueue<>(1);
        BlockingQueue<Event> fast = new ArrayBlockingQueue<>(1);
        CountDownLatch fastWritten = new CountDownLatch(1);

        // Same producer: event 1 is sent before event 2.
        slow.put(new Event(1, "order-created"));
        fast.put(new Event(2, "payment-started"));
        System.out.println("source: 1 then 2");

        Thread slowWriter = new Thread(() -> {
            try {
                Event event = slow.take();
                fastWritten.await();
                System.out.println("slow-sink: "
                        + event.sequence() + " " + event.message());
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "slow-writer");

        Thread fastWriter = new Thread(() -> {
            try {
                Event event = fast.take();
                System.out.println("fast-sink: "
                        + event.sequence() + " " + event.message());
                fastWritten.countDown();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "fast-writer");

        slowWriter.start();
        fastWriter.start();
        slowWriter.join();
        fastWriter.join();
    }
}
```

Compile/run with JDK 17 or later:

```bash
javac --release 17 LogOrderDemo.java
java LogOrderDemo
```

**Exact stdout under normal execution without external interruption:**

```text
source: 1 then 2
fast-sink: 2 payment-started
slow-sink: 1 order-created
```

Why is the result deterministic? Both queues already hold their events before the threads start. `fastWriter` prints event 2 and calls `countDown()`. `slowWriter` must `await()` before printing event 1. The two sinks are **two separate paths**. Neither FIFO queue reorders items internally.

The key takeaway is: **"event 1 was created first" does not mean "event 1 will reach every destination before event 2"**. If a thread is interrupted before releasing the latch, the demo may not complete as shown; it intentionally illustrates only normal ordering and does not handle full timeout/termination logic of a real application.

### 4.1. What If There Is Only One FIFO Queue?

A single FIFO `BlockingQueue` with a single worker returns items that were **successfully enqueued** in enqueue order. With a sequentially processing sink, dequeue order generally reflects the order in which the appender was called. However:

- Two producers can enqueue in a different order than the business order you expect.
- If two appenders have separate queues, there is no shared FIFO between them.
- Dropping logs due to a full queue creates gaps in the sequence, not reordering.
- Batching, buffering, or downstream transport can still make the order seen at the backend differ from the source.
- A FIFO within a single JVM does not establish an ordering contract across multiple JVMs/pods/services.

Therefore, before concluding that a queue is "out of order", you must verify exactly **which queue, which items, how many consumers, and which sink**.

## 5. Logback AsyncAppender and the Limits of FIFO

Example `src/main/resources/logback-spring.xml` for a Spring Boot application using SLF4J/Logback:

```xml
<configuration>
    <appender name="FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/application.log</file>
        <rollingPolicy
            class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/application.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
            <maxHistory>7</maxHistory>
        </rollingPolicy>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level [%thread] %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ASYNC_FILE"
              class="ch.qos.logback.classic.AsyncAppender">
        <queueSize>1024</queueSize>
        <discardingThreshold>0</discardingThreshold>
        <neverBlock>false</neverBlock>
        <maxFlushTime>10000</maxFlushTime>
        <appender-ref ref="FILE"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="ASYNC_FILE"/>
    </root>
</configuration>
```

This is a configuration for a project that already has Logback and a writable `logs` directory. It **has only a single path from root through ASYNC_FILE to FILE**, avoiding having the file receive one copy directly and another via the queue.

Explanation:
- `AsyncAppender` has a bounded queue and a single worker. The queue preserves the **enqueue order of accepted events**; it does not infer business order across threads.
- `queueSize=1024` is the number of events, not bytes.
- `discardingThreshold=0` disables early discarding of lower-level events when the queue is nearly full; it **does not guarantee zero-loss** on crashes, sink errors, or shutdown.
- `neverBlock=false` lets the producer wait when the queue is full. Changing it to `true` can drop new events when no space remains.
- `maxFlushTime=10000` limits how long to wait for the worker to drain the queue when the appender stops; any remaining backlog may be lost if the timeout is exceeded.
- `%d` displays the event's timestamp, which is not necessarily the time the event is flushed to the file.

**By default, Logback** can drop `TRACE`, `DEBUG`, and `INFO` events when the queue has about 20% remaining capacity. Thus, seeing sequence 1 then 3 while missing 2 may be *log loss* due to discarding, not "event 2 is still somewhere in the queue". You need to monitor queue occupancy, sink errors, dropped event counts, and drain time.

### 5.1. Why Can Logs Still Arrive Late Even With Async Enabled?

`logger.info(...)` can return as soon as the event is enqueued. The worker writes to the file later and can be affected by disk contention, encoding, filesystem behavior, or flushing. When multiple requests log concurrently, request B's producer may finish its business logic while the worker is still writing request A's logs.

If the queue is full and the policy blocks producers, the logging call itself alters business execution scheduling because the calling thread must wait. Therefore, measure latency in both the application and the log pipeline during analysis.

## 6. Log4j 2: AsyncAppender vs. AsyncLogger

In Log4j 2:

- **AsyncAppender** is an intermediary appender that stores events in a blocking queue and invokes target appenders on a background thread.
- **AsyncLogger** uses an **LMAX Disruptor/ring buffer** to hand off logging to asynchronous processing; it requires compatible configuration and dependencies.
- Synchronous and asynchronous loggers can be mixed, but you must understand the routing path and the impact of introducing multiple async layers.

Example `src/main/resources/log4j2.xml` with an AsyncAppender:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <File name="FILE" fileName="logs/application.log" append="true">
            <PatternLayout
                pattern="%d{yyyy-MM-dd HH:mm:ss.SSS} %-5p [%t] %c - %m%n"/>
        </File>
        <Async name="ASYNC_FILE" bufferSize="1024" blocking="true">
            <AppenderRef ref="FILE"/>
        </Async>
    </Appenders>
    <Loggers>
        <Root level="info">
            <AppenderRef ref="ASYNC_FILE"/>
        </Root>
    </Loggers>
</Configuration>
```

This example only illustrates the routing. Production setups must consider rolling policies, retention, failure handling, queue-full policies, and file permissions. Enabling `AsyncAppender` alone does not turn a Logger into an `AsyncLogger`; the two implementations are different.

Log4j 2 provides queue-full policies, batching, and error handling on the background thread. You should not claim that an async appender **guarantees order across all destinations**; local contracts and the network/backend layers must be verified separately.

## 7. Multiple Appenders and Separate stdout/stderr Streams

A root logger can send the same event to both console and file:

```xml
<root level="INFO">
    <appender-ref ref="CONSOLE"/>
    <appender-ref ref="ASYNC_FILE"/>
</root>
```

This is an **illustrative Logback snippet in a configuration that already defines both appenders**. The console may process synchronously while the file uses a queue. The same event can appear on the console before it appears in the file; subsequent events traveling different routes will also have different latencies.

`System.out` and `System.err` are **two separate streams**. Terminals, IDEs, or container runtimes may read and merge them on different schedules. Two calls:

```java
System.out.println("A");
System.err.println("B");
```

execute sequentially on a single thread, but when displayed through a mechanism that merges the two streams, you should not treat the final position of A/B as a strong guarantee of execution timing. If you need an easily controllable local ordering source, send events that must be compared to the same sink/stream with explicit metadata.

### 7.1. File Buffering and Multiple Processes

Appenders, Java buffers, the OS page cache, and transport layers can delay when bytes become visible to a reader. A flush at one layer does not necessarily mean **durably persisted** at a remote backend.

If multiple JVMs/pods write to the same file or push logs to the same index, logs from different instances can interleave, and rotation/tailing can cause delays, missing lines, or duplicate reads. Never share a file without supported ownership/locking/rotation mechanisms. In container deployments, each instance typically writes to stdout and a collector attaches source-identifying metadata.

## 8. Timestamps Can Be Misleading

Consider two events:

```text
2026-11-10T10:00:00.123Z INFO A step=1
2026-11-10T10:00:00.123Z INFO A step=2
```

They share the same millisecond timestamp. If the UI only displays millisecond precision, **you cannot reliably deduce the order** from the displayed timestamp alone. Even if the raw data has higher precision, the formatting pattern discards that detail when rendering.

### 8.1. Clocks Across Services Are Not Perfectly Synchronized

Services A and B run on two machines with different wall-clock times. A actually sends a request to B first, but B's clock may lag behind, making B's timestamp earlier than A's. Using UTC standardizes representation, but **does not fix clock skew**.

System clocks can be synchronized or stepped; `System.currentTimeMillis()` is not a monotonic clock intended for measuring duration. Within the same JVM, `System.nanoTime()` is suitable for computing **elapsed time** between two calls. Do not compare absolute `nanoTime()` values across two processes, because its origin has no global meaning.

### 8.2. Timestamp and ObservedTimestamp in OpenTelemetry

The OpenTelemetry Logs Data Model distinguishes:

- `Timestamp`: time when the event occurred at the **source**, when known.
- `ObservedTimestamp`: time when the collection system **observed** the record.

For example, event A occurs in a service at 10:00:00.100, but the Collector only sees it at 10:00:00.350 due to queuing/retries. Event B occurs at 10:00:00.200, but the Collector sees it at 10:00:00.220. If the dashboard sorts by **ObservedTimestamp**, B may appear before A. If it sorts by **Timestamp**, A appears before B. This is an illustrative example without factoring in clock skew.

You need to check **the actual sort field used by the backend**; do not assume every dashboard uses the source timestamp. Switching to sorting by timestamp still does not establish a total order when clocks are skewed or multiple events share the same timestamp.

## 9. Distributed Tracing Helps Reconstruct Causality

In a distributed system:

```text
Service A                      Service B
    A1 receive request
    A2 send HTTP ──────────────> B1 receive HTTP
                                B2 process
    A3 receive response <─────── B3 return response
```

Request/response relationships define meaningful causal milestones. However, log A2 may reach the backend **after** B1 because Collector A is slower. Relying on line order in the backend to claim B1 happened before A2 would be wrong.

Attach **trace ID**, **span ID**, service name, and instance ID to correlate related logs. Parent-child spans show work relationships; child spans can still run in parallel. A trace ID **is not a sequence number** and does not prove a total order of all logs within a trace.

Commonly useful metadata:
- `trace_id`, `span_id`, `request_id`;
- `service.name`, pod/instance, thread, logger name;
- `operation`, `stage`, and `attempt_no`;
- `message_id` or `job_run_id` for queues/schedulers;
- `version` or `sequence` scoped to a specific business entity.

To know whether a business step has committed, check the state/transaction/event store. A `success` line could be logged before commit or written late; it does not replace a high-reliability state record.

## 10. Sequence Numbers: Useful, but Scope Must Be Understood

An **illustrative** method example inside a class with SLF4J and business methods:

```java
public void process(long orderId) {
    log.info("order={} step=1 stage=VALIDATE", orderId);
    validateOrder(orderId);
    log.info("order={} step=2 stage=RESERVE", orderId);
    reserveStock(orderId);
    log.info("order={} step=3 stage=COMPLETE", orderId);
}
```

If a flow executes sequentially and all steps complete normally, the `step` number accurately reflects the logical order. If an exception or branch occurs, log the appropriate stage/status; do not emit a COMPLETE log when an earlier step failed.

With multiple threads, you can assign a sequence using `AtomicLong`:

```java
private static final java.util.concurrent.atomic.AtomicLong NEXT =
        new java.util.concurrent.atomic.AtomicLong();

long sequence = NEXT.incrementAndGet();
log.info("seq={} action={}", sequence, action);
```

This is also an **integration snippet inside a class that has `log` and `action` variables**, not a standalone program. `AtomicLong` generates monotonically increasing numbers within a single JVM, but between `incrementAndGet()` and `log.info()`, a thread can be preempted. Thus, log `seq=12` can be enqueued **before** log `seq=11`. This sequence helps detect allocation order, not guarantee append order. Nor does it act as a shared sequence across multiple JVMs or survive restarts.

If business logic strictly requires ordered processing, the sequence should be assigned by the **owner of the workflow/aggregate** at the appropriate serialization point or transaction. For example, an incrementing version in a database record per order can serve as the basis for reconstructing commit order, while logging simply records that version.

### 10.1. Structured Logs for Querying

An *illustrative* JSON record example:

```json
{
  "timestamp": "2026-11-10T10:00:00.123Z",
  "service": "order-service",
  "instance": "pod-2",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "order_id": "42",
  "step": 3,
  "stage": "PAYMENT",
  "attempt": 1,
  "message": "Payment accepted"
}
```

The custom fields here are **not a mandatory schema** of OTel/Logback/Log4j 2. You must standardize with your actual backend and protect sensitive metadata. Do not build JSON via string concatenation from unescaped input; use an appropriate encoder/structured logging library.

## 11. Collection Pipelines Can Delay or Reorder Logs

A single event may pass through:

```text
Application -> Console/File/OTLP -> Receiver -> Batch -> Exporter
    -> Network -> Retry -> Storage/index -> Query sorting
```

Several mechanisms create discrepancies:
- Logs from multiple nodes are sent over the network with varying latencies.
- The Collector tails multiple files or stdout/stderr streams concurrently.
- Batching groups logs; different batches have different transit times.
- Exporters retry after transient errors, which can cause older data to arrive late.
- Multiple pipelines/receivers exporting the same event create **duplicates**, not pure reordering.
- Parsers drop the source timestamp and the backend sorts by ingest timestamp instead.
- Queries across multiple partitions/shards have unstable tie-breaking when timestamps are equal.

Do not assume every Collector reorders logs by default. To pinpoint the issue, compare logs at the **stdout/file source** with records at each observable stage, then inspect the specific pipeline. If the source is in order but the dashboard is wrong, start with timestamp mapping, batching, retries, and query sorting.

## 12. Distinguishing Reordered, Missing, and Duplicate Logs

| Symptom | Likely Cause | What to Check |
| --- | --- | --- |
| See `2, 1` with both events present | Reordering / sort method | Event timestamp, sink route, queue |
| See `1, 3` but missing `2` | Drop / filtering / not yet ingested | Queue-full policy, filter, exporter errors |
| See `1, 2, 2` | Duplicate or reprocessing | Appender refs, collector retry, event ID |
| Same message in two traces | May be two valid events | Request/trace/instance ID |
| Timestamp B before A even though A calls B | Clock skew or sorting | Causal trace, source/observed time |
| Multi-line exception stack trace | One event rendered across multiple lines | Layout, throwable, multiline parser |
| Business retry produces identical text | Two executions may both be real | Attempt ID and idempotency |

Do not use regex to strip identical messages in order to "fix ordering". Two valid requests can log the exact same text. Nor should you deduplicate solely by `trace_id`: a single trace usually contains many events.

Another easily confused bug is **wrong MDC**: an async appender's worker thread is not the request thread. You must let the framework snapshot the thread name/MDC at event creation time; do not have the worker read the request's `ThreadLocal`. Wrong context makes logs look like they belong to the wrong request and appear "out of order".

## 13. When Must Order Be Guaranteed by Business Design?

Not every log needs a total order. For general observability, best-effort timestamps with trace/context are usually enough. However, for audits, ledgers, state machines, or per-key event streams, **ordering is a business requirement**.

You may need:
1. A single processing stream or synchronization mechanism per aggregate/key.
2. An incrementing sequence/version at commit time, protected by uniqueness/transactions.
3. A transactional outbox so events are recorded alongside data changes before distribution.
4. Consumers with an appropriate ordering contract per partition/key, combined with idempotency on retry.
5. A durable audit channel with retention, acknowledgment, and recovery policies.

These measures carry throughput and latency costs. Do not turn `AsyncAppender` or `Logger.info` into a mechanism for guaranteeing transaction success. When the exact requirement is "the order of changes on an order", manage it in the **order's** state/transaction, not via the order of log lines on a dashboard.

## 14. Layer-by-Layer Diagnostic Workflow

### Step 1: Pick Two Specific Events

For example, event A with `stage=VALIDATE` and event B with `stage=COMPLETE` for the **same order/request**. Record the service/instance, logger, thread, source timestamp, observed/ingest timestamp, trace ID, and sequence if available.

### Step 2: Ask Whether Business Order Is Actually Wrong

Check the code path, exceptions, retries, and data state. For two threads, check `Future`, `CountDownLatch`, locks, `volatile`, or happens-before relationships. If there is no dependency, non-deterministic order may be valid behavior.

### Step 3: Compare Directly at the Source

Compare event order in the file/stdout of the **exact JVM**, without merging multiple pods. For multiple streams, separate stdout and stderr. Determine whether the logger was called once or multiple times, and whether any filter/drop occurred.

### Step 4: Inspect the Logging Framework

Check the actual backend (Logback or Log4j 2), appender wiring, queues, `AsyncAppender`/`AsyncLogger`, queue size, worker count, queue-full policy, encoder, and flush behavior. If multiple appenders write to the same sink or both stdout and OTLP ingest, separate duplicates before analyzing order.

### Step 5: Compare the Two Timestamps

The source and Collector may use different clocks; source timestamps may collide at display precision. Which field does the query sort on? Is there a stable tie-breaker? Do not treat every negative delta caused by clock skew as proof of business inconsistency.

### Step 6: Trace Through the Collector/Backend

Check receivers, file tail offsets, batch/exporter retries, network delay, timestamp parsing, and query federation. If the source is in order while the backend reverses it, focus on the pipeline.

### Step 7: Reproduce With a Controlled Workload

Generate events with unique IDs (containing no secrets) and known sequences. Compare single-thread/sync sink, multi-thread, single async queue, two independent queues, logging via Collector, and restarts. Measure events created, enqueued, written, and ingested if the system supports it.

## 15. Testing and Measurement

| Scenario | What to Verify | Expectation |
| --- | --- | --- |
| Single producer, single FIFO queue, single worker | Dequeue order | Matches enqueue order of accepted events |
| Two unsynchronized producers | No fixed global order exists | Do not assert B/A order without a dependency |
| Two independent sinks | Display order may differ | Verify local contract for each sink |
| Mandatory flow A → B | Explicit dependency in code | B runs only after a defined point in A |
| Queue full | Documented block/drop policy | Do not confuse missing events with reordering |
| Two services with clock skew | Accurate causal relation | Use trace/sequence, not just timestamps |
| Exporter retry/batch | Ingest delay may occur | Preserve source timestamp and metadata |
| Shutdown with backlog | Known drain/timeout | Do not claim durable persistence without confirmation |

Useful metrics: queue depth/utilization, enqueue wait, event age at sink, drop count, appender errors, exporter retry count, source-to-observed latency, and backend delivery rate. When calculating cross-host latency, account for clock skew.

## 16. Common Anti-Patterns and Wrong Fixes

**Adding `Thread.sleep(...)` between two logs:** may make a single test run look right, but creates no strong dependency; both slow and unreliable.

**Sorting by timestamp and treating it as absolute:** timestamps can collide, suffer from clock skew, or be altered by the pipeline. Sorting aids readability; it does not replace an ordering contract.

**Increasing queue size unboundedly:** backlog grows whenever producers outpace the sink for a sustained period; a huge queue does not guarantee ordered delivery across multiple sinks and can increase heap/GC pressure.

**Disabling async logging system-wide:** may reduce latency at one sink, but does not fix multi-thread scheduling or Collector behavior; in return, it can increase request latency.

**Using a global `AtomicLong` for distributed total order:** only allocates numbers within one JVM, can still be reordered between allocation and enqueue, and is not continuous across restarts.

**Dropping repeated messages:** can lose valid logs from multiple requests. Duplicate logs require distinguishing duplicate routing from business retries.

**Trusting a `success` log as proof of commit:** check the transaction and event store, not just a log line. For audits, use durable data sources.

**Forgetting the difference between flush and durability:** logger return, an empty queue, or an appender flush does not mean the remote backend has persisted the event.

## 17. Checklist for Verifiable Logging Design

1. Define the ordering scope: per thread/request/aggregate or system-wide.
2. Record correlation IDs, including request/trace/span and service instance.
3. Preserve the source timestamp; separate observed/ingest timestamps when the pipeline supports it.
4. Use properly scoped stage/version/sequence fields for mandatory workflows.
5. Verify appender routing and the number of async queues; monitor queue-full/drop events.
6. Verify each source (file/stdout/stderr) before drawing conclusions from a dashboard.
7. Check Collector batching, retries, timestamp mapping, and backend sorting.
8. Test graceful shutdown and scenarios involving backlog, log loss, and duplicates.
9. When strict audit ordering is required, use storage/transactions with explicit contracts.
10. Never use plain log text as a substitute for business state evidence.

**Principle:** to understand which event happened first, you must examine **causality, context, and the ordering guaranteed within a specific scope**. A list of logs displayed on a screen is merely one view after passing through multiple transport layers.

## References

- [Java Language Specification – Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html).
- [Java SE 21 – BlockingQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html).
- [Java SE 21 – CountDownLatch](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html).
- [Java SE 21 – System.nanoTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#nanoTime()).
- [Logback – AsyncAppender](https://logback.qos.ch/manual/appenders-async-sift.html).
- [Apache Log4j 2 – Asynchronous loggers](https://logging.apache.org/log4j/2.x/manual/async.html).
- [Apache Log4j 2 – Delegating/Async appender](https://logging.apache.org/log4j/2.x/manual/appenders/delegating.html).
- [OpenTelemetry – Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/).