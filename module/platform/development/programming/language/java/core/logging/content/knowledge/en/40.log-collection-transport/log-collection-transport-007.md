# Batched Log Shipping in Java: Batching, Flushing, Retries, and Data Loss Control

## 1. What is Batched Shipping?

**Batched shipping** (batched log shipping / batched exporting) is a mechanism that **groups multiple log records into a single batch** before sending them from an application, agent, or collector to a log-receiving system. Instead of opening/writing a network request for every single event, the shipping component accumulates records by count or size and sends the entire batch when a threshold is reached or a wait timeout expires.

Example shipping flow:

```text
Java application
  |
  | INFO/WARN/ERROR events
  v
Logging API / appender / OpenTelemetry log bridge
  |
  v
Bounded queue or buffer
  |
  +---- enough records / bytes -------> create batch
  |                                        |
  +---- time limit reached ----------------+
  |                                        |
  +---- forceFlush/shutdown ---------------+
                                           |
                                           v
                                    Exporter / sender
                                           |
                                 HTTP/gRPC/OTLP/TLS
                                           |
                                           v
                               Collector / log storage
                                           |
                                       Dashboard
```

Batching aims to **reduce the number of network calls, syscalls, and header/protocol overhead**, increase compression opportunities, and improve throughput. In return, records may **wait longer in the buffer**, consume memory, be rejected/dropped when full, and be lost if the process terminates abruptly before sending.

Objectives of this article in the **Collection and Transport** group:
- Understand that a batch is a shipping unit, not a single large log event concatenated by the application.
- Distinguish batching in the JVM, logging backend, agent, and OpenTelemetry Collector.
- Choose count thresholds, byte limits, timeouts, max queue size, concurrency, and flushing strategies.
- Design retry/backoff, avoid duplicates, and analyze at-most-once/at-least-once guarantees.
- Know when you need a disk-backed queue, durable storage, circuit breaker, and shutdown drain.
- Configure OpenTelemetry Java Logs SDK, Collector, and Grafana Alloy/Loki in practice.
- Run a Java 17+ example simulating failure, bounded queue, size/time triggers, and force flush.
- Test, observe, and troubleshoot shipping issues without exposing sensitive data.

## 2. Do Not Confuse Batching with Async Logging

**Async logging** and **batched shipping** are two different design decisions:

| Mechanism | Question Addressed | Can It Exist Without the Other? |
| --- | --- | --- |
| Async logging | Which thread handles logging/I/O work? | Yes. An async worker can still send each record individually |
| Batching | How many records are sent in a single export? | Yes. A batcher can be synchronous, blocking the calling thread |
| Queue | Where are pending records held and how are they bounded? | Yes. A batch buffer can live in-process without a general-purpose async queue |
| Retry | How are failed sends retried? | Yes. A batcher can fail/drop immediately, or the exporter can retry |
| Compression | How are the bytes sent over the wire compressed? | Yes. A batch can be uncompressed, and a single payload can still be compressed |
| Durable buffering | Do records survive a process crash/restart? | Yes or no. An in-memory queue has no durability |

For example, a synchronous JUL `Handler` can wait for 100 records and then call an HTTP API. That is **batching, but the producer is blocked** during the send. Conversely, Logback's `AsyncAppender` typically lets a worker thread process events; simply attaching an `AsyncAppender` **does not prove** that the network destination receives batches of exactly 100 events per request.

Do not mechanically stack multiple layers of queues/batching. A system can queue records in the JVM, sidecar/agent, Collector, and exporter, making total latency larger than expected and making it hard to pinpoint where logs are lost.

## 3. Components in the Collection and Transport Pipeline

Responsibilities can be divided as follows:

```text
[Application]
 logger -> encoder/LogRecordProcessor -> batch/queue A
                                            |
                                            v
[Agent / runtime]
 receives stdout, file, or OTLP -> buffer/batch B
                                            |
                                            v
[OpenTelemetry Collector]
 receiver -> memory_limiter -> batch processor -> exporter queue
                                            |
                                            v
[Backend]
 Loki / log storage system / SIEM
```

### 3.1. Batching Inside the Java Application

The OpenTelemetry Logs SDK provides `BatchLogRecordProcessor`. The application can export `LogRecord`s received by the SDK in batches. Advantage: reduces the number of export calls; drawback: logs are buffered in process memory, so a crash/kill can lose unexported records.

For applications using JUL/SLF4J/Logback, **a matching bridge/appender/instrumentation is required** for events to flow into the OpenTelemetry Logs SDK. Merely declaring SDK properties **does not automatically guarantee** that every `logger.info(...)` call in Java is collected by OTel.

### 3.2. Batching in the Agent or Collector

An agent reads files/stdout or receives logs from the SDK; it may have its own buffer, retry, disk spool, and export mechanism. The Collector has a `batch` processor to group telemetry before the exporter, serving logs, metrics, and traces in their respective pipelines.

Advantage of this layer: multiple applications share transport handling, making it easier to manage networking, auth, retries, and backend changes. Keep in mind that data leaving the JVM is **not guaranteed to have been persisted by the backend**; failures can still happen at the agent/collector/exporter.

### 3.3. Batching at the Destination Client

For example, Grafana Alloy `loki.write` has `batch_size` and `batch_wait`. An agent can group log lines and send them to Loki when enough bytes accumulate or the wait time expires. Here, `batch_size` is **byte size**, whereas OTel Java's `max.export.batch.size` is **the number of log records**. Mixing up these two units when tuning configuration can cause major misconfigurations.

## 4. When Is a Batch Sent?

Three common trigger types:

1. **By record count:** accumulate up to `maxBatchCount` (e.g., 512 records), then send.
2. **By total bytes:** when size approaches/reaches `maxBatchBytes` (e.g., 1 MiB), send to avoid oversized requests.
3. **By time:** even if the batch is not full, send after `maxWait` or `scheduleDelay` to bound latency during low traffic.

There are also:
- **Manual flush/forceFlush:** the application/SDK requests pushing pending data via an API with a deadline.
- **Shutdown:** attempt to drain before closing the processor/exporter.
- **Backpressure/queue pressure:** may force a send, block, drop, or reject records, depending on the implementation.
- **Retry timer:** after an error, retry according to a backoff or schedule managed by the exporter.

In a "size or time, whichever comes first" policy:

```text
t=0ms:  event A -> queue 1/3
t=100:  event B -> queue 2/3
t=200:  event C -> queue 3/3 -> send batch A,B,C
t=300:  event D -> queue 1/3
...
t=1300: D has fewer than 3 records, timeout reached -> send D
```

This diagram illustrates a batcher using **the age of the first record**. Real implementations may measure the timer from the last export, on a fixed tick, or from the first enqueue; **do not infer semantics from the name `timeout` alone**. The Java example in Section 8 uses the age of the first stored record and a simulated clock for deterministic results. OTel SDK/Collector follow their own implementation timer rules.

### A Trigger Is Not a Hard Limit

Specifically in **OpenTelemetry Collector**:
- `send_batch_size` is a **send trigger threshold**, which may not be a strict upper bound on an output batch.
- `send_batch_max_size` is what limits the number of records/data points/spans in a batch and splits larger sets into smaller batches.
- `timeout` is the time-based trigger.

This differs from the custom API in our example, where `maxBatch` acts as a hard cap on records per send. Always check the exact configuration documentation **for the specific component** you are editing.

## 5. Parameters and How to Choose Them

| Parameter | Impact | If Too Small | If Too Large |
| --- | --- | --- | --- |
| `max_batch_count` | Events per send | Many requests and overhead | Heavy batches, hard to retry/split |
| `max_batch_bytes` | Max payload; distinguish pre- vs. post-compression | Poor connection efficiency | 413/payload cap errors, memory spikes |
| `max_wait` | Delay before sending a partial batch | High overhead on low traffic | Logs appear late on dashboards |
| `max_queue_records` | In-memory backlog capacity | Early drops/blocks on bursts | Higher heap/GC, OOM when sink is down |
| `export_timeout` | Deadline per send attempt | False timeouts on slow networks | Workers stuck too long during outages |
| `max_retries` / retry budget | Retry effort duration | Easy log loss on transient errors | Queue bloat and slow recovery |
| `backoff_initial/max` | Retry cadence | Retry storms/backend pressure | Slow recovery after outage |
| `concurrent_exports` | Number of in-flight batches | Low throughput | Reordering, memory, and backend pressure |
| `compression` | Reduces bytes on the wire | Uncompressed wastes bandwidth | Heavy compression costs CPU, needs compatibility |

There is no "universal optimal" configuration for all services. You need to measure traffic rate, record size, acceptable latency, memory, network cost, receiver limits, and failure behavior.

### Estimation Example

Suppose a service emits **10,000 log records/second**, with an average payload size of **400 bytes** before compression:
- Raw payload is about **4,000,000 bytes/second** (roughly 4 MB/s, excluding metadata).
- If batching **500 records/batch**, steady load ideally requires **20 batches/second**.
- Each batch averages **200,000 bytes of payload**; on the wire there are also envelope/headers/encoding and compression.
- A queue with a max of **5,000 records** holds about **2 MB of raw payload**, but **actual heap usage is larger** due to object headers, `String`s, collections, serialization, and runtime overhead.

These numbers are for **capacity estimation only**, not benchmark results. If the sink stops for 30 seconds, a 10,000 records/s source can create a **300,000-record backlog** if load is not shed. A 5,000-record queue cannot hold all of it. Making the in-memory queue infinitely larger does not solve the problem; you need backpressure, disk buffering, throughput headroom, a drop policy, or a durable storage path if required.

### Byte-Based Sizing Often Matters More Than Count

If individual records vary widely in size (stack traces, JSON, blobs), limiting only to `500 records` can produce either a 50 KB batch or a 20 MB batch. For receivers with request-size limits, combine count + byte thresholds or use an exporter that enforces valid payload limits. In particular: batch bytes **before compression** do not necessarily equal payload bytes after encoding/compression.

## 6. Three Critical Milestones: Emit, Enqueue, and Confirmed Export

A log event passes through several stages:

```text
(1) Application emitted event
       |
       v
(2) Accepted by local queue
       |
       v
(3) Export attempt started
       |
       +--> timeout/error -> retry/drop/fallback per policy
       |
       v
(4) Exporter reports success
       |
       v
(5) Receiver/collector processed, then persisted in backend
       |
       v
(6) Queryable on dashboard
```

**Do not equate these milestones.**
- `logger.info(...)` returning does not prove the event entered the queue.
- Queue acceptance does not prove the exporter has sent it.
- Calling `send()` does not prove the remote endpoint ACKed it.
- The exporter reporting success **does not necessarily** prove the backend has indexed, durably stored, and made it immediately queryable.
- An event not showing up on a dashboard could be due to ingestion delay, filters, permissions, timestamps, or retention—not necessarily because the client failed to log.

In multi-step systems, design metrics at each stage and clearly define which milestone counts as `sent`, `accepted`, `exported`, or `delivered`. Do not label a newly enqueued request as `published_successfully`.

### At-Most-Once, At-Least-Once, and Exactly-Once

- **At-most-once:** no retry after an ambiguous failure/timeout, reducing duplicates at the cost of potential event loss.
- **At-least-once (when backed by sufficient persistence/ack/retry):** keeps retrying until an ACK is received per policy, which can produce duplicate records.
- **Exactly-once:** requires a very specific end-to-end contract with the receiver, idempotency/deduplication, transactions, or a suitable protocol; **it does not exist by default just because batching/retries are enabled**.

An ACK can **be lost** after the receiver has already accepted the batch. The producer sees a timeout and retries, causing the receiver to receive two copies. Therefore, batching combined with retries often requires a **stable event ID** or deduplication policy when duplicates affect business or audit logic.

Do not treat regular logging as a transactional system with exactly-once guarantees. If audit/compliance events require durability, use a dedicated write channel with a designed and verified reliability contract.

## 7. Retry, Backoff, and Backpressure

### 7.1. Failure When Sending a Batch

Suppose an exporter sends 100 records and hits a network timeout:
- You do not know for sure how many records the receiver got, or whether it ACKed right before the connection dropped.
- Dropping the batch risks losing many records at once.
- Retrying the entire batch risks duplicating records the receiver already accepted.
- Retrying continuously without limits grows the queue, consumes resources, and batters an already struggling backend with a retry storm.

A practical production policy:
1. Retry only **recoverable errors** such as timeouts or certain rate-limit/server error statuses, per the backend contract.
2. Use **exponential backoff + jitter**, honoring `Retry-After` if specified by the protocol/backend.
3. Bound retry attempts/elapsed time, total backlog, and concurrent requests.
4. When a receiver returns **HTTP 413 Payload Too Large**, reduce batch size/split the batch or adjust limits; retrying the exact same oversized batch endlessly will not help.
5. For **HTTP 400 schema invalid** or **401/403 auth**, fix the data/config/credentials; do not treat all 4xx codes as retryable.
6. If the retry budget is exceeded, record a **dropped/failed metric**, route to a durable local spool/dead-letter path if architecture permits, or enforce an acceptable log-loss policy.
7. Keep internal exporter error logs **free of sensitive tokens/payloads**, and avoid feedback loops where logging an export error feeds back into the broken exporter.

There is no single list of retryable statuses that applies to every backend; each SDK/exporter/protocol has its own rules. Read the documentation for the tool you operate.

### 7.2. When the Queue Is Full

Main policy categories:

| Policy | Behavior | Risk |
| --- | --- | --- |
| Drop new | Keep old backlog, discard new event | Loses recent errors occurring during overload |
| Drop old | Prioritize recent logs, evict old backlog | Loses preceding event sequence, hindering root-cause analysis |
| Block/backpressure | Wait for space before returning | Slows down requests or causes deadlock if misused |
| Spill to disk | Write backlog to a durable buffer | Adds I/O/disk quota overhead, requires recovery/ACL/retention |
| Fail fast | Return error to caller | Unsuitable if logging failure breaks business requests |

Choose based on **log criticality**. Debug logs can be sampled/dropped; ERROR logs usually need observation priority, but must not create unfair priority inversion that stalls the pipeline. Audit logs need an appropriate durable write path rather than relying on an in-memory queue for all cases.

### 7.3. Disk Spool vs. In-Memory Queue

An in-memory queue is lost when the JVM/agent crashes or the host is killed. A disk spool can preserve backlog across restarts if implemented properly, but requires:
- File/directory permissions and encryption so logs containing private data are not exposed.
- Maximum capacity, retention, cleanup, and recovery when the volume is full/corrupted.
- ACK/offset checkpoint rules to prevent data loss when a batch is sent but a crash occurs before deleting the spool entry.
- Handling potential duplicates after restart, so downstream may need deduplication.
- Avoiding multiple processes writing to the same spool if it is not designed for concurrent access.

Disk buffering does not automatically provide exactly-once delivery; it only improves backlog survival across certain failure modes.

## 8. Standalone Java 17+ Example: Simulating Size/Time Batching, Retries, and Shutdown

The program below uses only JDK 17—no broker, HTTP endpoint, or external libraries required. It uses a **simulated clock** (`nowMs`) for deterministic stdout output. Structure:
- `Event` holds a controlled ID and event type.
- `Pending` holds an event along with its enqueue timestamp.
- `Batcher` has a max queue of **3 records** and max batch of **3 records**.
- `DemoSender` simulates a failure on the first send attempt **before the receiver accepts it**, then succeeds on subsequent calls.
- `offer` triggers a send when count is reached; `onTick` sends when the first record has waited at least 1,000 ms; `flushForShutdown` sends the remainder.
- Enqueueing when the queue is full is **explicitly rejected**, not silently dropped.

Create **`BatchTransportDemo.java`**:

```java
import java.io.IOException;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.stream.Collectors;

public final class BatchTransportDemo {
    record Event(String id, String type) {}
    record Pending(Event event, long queuedAtMs) {}

    interface Sender {
        void send(List<Event> batch) throws IOException;
    }

    static final class DemoSender implements Sender {
        int calls;
        final List<String> receivedIds = new ArrayList<>();

        @Override
        public void send(List<Event> batch) throws IOException {
            calls++;
            if (calls == 1) {
                throw new IOException("simulated_network_failure");
            }
            batch.forEach(event -> receivedIds.add(event.id()));
            System.out.println("exported="
                    + batch.stream().map(Event::id)
                        .collect(Collectors.joining(",")));
        }
    }

    static final class Batcher {
        final Deque<Pending> pending = new ArrayDeque<>();
        final Sender sender;
        final int maxBatch;
        final int maxQueue;
        final long maxDelayMs;
        int accepted;
        int rejected;

        Batcher(Sender sender, int maxBatch,
                int maxQueue, long maxDelayMs) {
            if (maxBatch <= 0 || maxQueue < maxBatch
                    || maxDelayMs <= 0) {
                throw new IllegalArgumentException(
                        "Invalid batch policy");
            }
            this.sender = sender;
            this.maxBatch = maxBatch;
            this.maxQueue = maxQueue;
            this.maxDelayMs = maxDelayMs;
        }

        void offer(Event event, long nowMs) {
            if (pending.size() >= maxQueue) {
                rejected++;
                throw new IllegalStateException("queue_full");
            }
            pending.addLast(new Pending(event, nowMs));
            accepted++;

            if (pending.size() >= maxBatch) {
                tryExport();
            }
        }

        void onTick(long nowMs) {
            if (!pending.isEmpty()
                    && nowMs - pending.peekFirst().queuedAtMs()
                       >= maxDelayMs) {
                tryExport();
            }
        }

        boolean tryExport() {
            int size = Math.min(pending.size(), maxBatch);
            if (size == 0) {
                return true;
            }

            List<Event> batch = pending.stream()
                    .limit(size)
                    .map(Pending::event)
                    .toList();

            try {
                sender.send(batch);
                for (int i = 0; i < size; i++) {
                    pending.removeFirst();
                }
                return true;
            } catch (IOException failure) {
                System.out.println("export_failed_size=" + size);
                return false;
            }
        }

        void flushForShutdown() {
            while (!pending.isEmpty()) {
                if (!tryExport()) {
                    throw new IllegalStateException("unsent_events");
                }
            }
        }
    }

    public static void main(String[] args) {
        DemoSender sender = new DemoSender();
        Batcher batcher = new Batcher(sender, 3, 3, 1_000);

        batcher.offer(new Event(
                "evt01", "order_created"), 0);
        batcher.offer(new Event(
                "evt02", "order_updated"), 100);
        batcher.offer(new Event(
                "evt03", "order_failed"), 200);

        try {
            batcher.offer(new Event(
                    "overflow", "test"), 300);
            throw new AssertionError(
                    "Expected bounded queue rejection");
        } catch (IllegalStateException expected) {
            if (!"queue_full".equals(expected.getMessage())) {
                throw expected;
            }
            System.out.println("queue_full_rejected=true");
        }

        batcher.onTick(999);
        batcher.onTick(1_000);

        batcher.offer(new Event(
                "evt04", "order_retried"), 1_300);
        batcher.onTick(2_299);
        batcher.onTick(2_300);

        batcher.offer(new Event(
                "evt05", "shutdown_notice"), 2_400);
        batcher.flushForShutdown();

        if (!sender.receivedIds.equals(
                List.of("evt01", "evt02", "evt03",
                        "evt04", "evt05"))
                || sender.calls != 4
                || !batcher.pending.isEmpty()
                || batcher.accepted != 5
                || batcher.rejected != 1) {
            throw new AssertionError(
                    "Batch delivery contract failed");
        }

        System.out.println(
                "accepted=" + batcher.accepted);
        System.out.println(
                "rejected=" + batcher.rejected);
        System.out.println(
                "delivered=" + sender.receivedIds.size());
        System.out.println(
                "send_attempts=" + sender.calls);
        System.out.println(
                "queue_remaining=" + batcher.pending.size());
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac BatchTransportDemo.java
java BatchTransportDemo
```

**Exact standard output of the program:**

```text
export_failed_size=3
queue_full_rejected=true
exported=evt01,evt02,evt03
exported=evt04
exported=evt05
accepted=5
rejected=1
delivered=5
send_attempts=4
queue_remaining=0
```

### 8.1. Step-by-Step Analysis

**Phase A — size trigger and first send failure.**

After enqueueing `evt01`, `evt02`, and `evt03`, the queue reaches 3 records and `tryExport()` runs. `DemoSender` intentionally throws `IOException` on the first call. The batcher **does not remove** the three items when the send fails; stdout prints `export_failed_size=3`.

**Phase B — queue full.**

An `overflow` event attempts to enqueue while 3 records are still pending, exceeding `maxQueue=3`, so `offer` throws `IllegalStateException("queue_full")`. The caller logs `queue_full_rejected=true` and the `rejected` counter increments to 1. This event is **not included in delivered**.

**Phase C — retry via tick after timeout.**

`onTick(999)` has not reached the 1,000 ms age of the first event, so nothing is sent. `onTick(1000)` triggers `tryExport`; this time the sender succeeds, confirming batch `evt01,evt02,evt03`, and the three items are removed from the queue.

**Phase D — timeout flush of a partial batch.**

`evt04` is enqueued at `1300`. `onTick(2299)` is under 1,000 ms; `onTick(2300)` meets the threshold, sending the single-element batch `evt04`. A batch **does not need to reach 3 records** once the time trigger fires.

**Phase E — shutdown flush.**

`evt05` is enqueued at `2400` without hitting size or time triggers. `flushForShutdown()` actively sends the remainder. In total, `accepted=5`, `delivered=5`, `send_attempts=4` (1 failure + 3 successes); no pending items remain.

### 8.2. Limitations of the Demo to Understand

This is a **single-threaded, synchronous simulator**, not a production exporter:
- `nowMs` is passed in by the caller; there is no real scheduler. Do not put a test elapsed-clock pattern like this into production expecting timers to fire on their own.
- `ArrayDeque` is **not thread-safe**; do not call `Batcher` from multiple producer threads without synchronization or replacing it with a thread-safe queue/worker architecture.
- `sender.send` is synchronous and can block the caller; larger systems need dedicated worker threads and timeouts.
- The simulated first failure happens **before writing to `receivedIds`**; it does not simulate the case where the receiver accepted the batch but the ACK was lost. Real retries can cause duplicates.
- There is no exponential backoff, jitter, TLS, OTLP, HTTP, WAL, persistent storage, metrics beyond stdout, or lifecycle deadline.
- `flushForShutdown` can throw if the sender does not recover. Production systems need a finite timeout, an appropriate backup/drop policy, and reporting of remaining unsent records.
- The initial timestamp is `0` on the simulated clock; the program does not rely on a real wall clock.
- `Event` holds only safe metadata and no raw message payload/secrets; real log data must be similarly minimized and validated.

**Key takeaway:** only remove records from the queue after the sender reports success **according to the sender's contract**; have an explicit strategy when the queue is full; flush partial batches by time and before shutdown. However, **success at the sender does not automatically guarantee end-to-end durability**.

## 9. OpenTelemetry Java: BatchLogRecordProcessor

The OpenTelemetry Logs SDK standardizes record processing before exporting via `LogRecordExporter`. There are two main processor families:
- **SimpleLogRecordProcessor:** passes each record to the exporter as soon as it is ready, suitable for low-volume logging or testing; it has no batch-processor style size/time batching.
- **BatchLogRecordProcessor:** groups records into a queue and exports them in batches. The SDK specification requires batching along with `forceFlush`/`shutdown` handling and limit enforcement.

When using **OpenTelemetry Java SDK autoconfigure** or an agent with logs exporter support, common properties are:

```properties
otel.logs.exporter=otlp
otel.blrp.schedule.delay=1000
otel.blrp.max.queue.size=2048
otel.blrp.max.export.batch.size=512
otel.blrp.export.timeout=30000
```

Explanation:
- `otel.blrp.schedule.delay`: scheduling interval for exporting batches, in **milliseconds**.
- `otel.blrp.max.queue.size`: maximum number of log records queued in `BatchLogRecordProcessor`.
- `otel.blrp.max.export.batch.size`: maximum number of records in a single export batch; must be chosen to fit the queue.
- `otel.blrp.export.timeout`: timeout for an export operation, in milliseconds.
- `otel.logs.exporter=otlp`: selects the logs exporter supported by OTel configuration.

This is an **illustrative configuration snippet**; on some SDK/autoconfigure versions, these example values match the published defaults. Do not hardcode one set of defaults across all Java agent/SDK versions or assume any arbitrary appender reads this properties file.

**Important:** These lines alone **do not automatically route JUL/SLF4J into OTel**. You must have the right bridge/instrumentation/Logback appender/Log4j 2 appender version, resource metadata, endpoint/credentials, and network policy. Trace the actual log path: `logger.info` → appender/bridge → SDK → exporter → receiver.

### ForceFlush and Shutdown

`forceFlush` asks the SDK/processor to attempt exporting records received prior to the call, bounded by the API timeout; it is **not a guarantee that the backend has indexed** or durably persisted the data. `shutdown` should flush/close processors and exporters, though it may return an error/timeout if the sink is unresponsive. Do not:
- call `forceFlush` on every log record, as that defeats batching and blocks requests;
- ignore timeout/failure results and report "delivered";
- wait indefinitely in a shutdown hook, preventing the deployment from terminating.

A sensible policy typically flushes during **controlled shutdown**, at the end of certain **FaaS invocations**, or at critical observability boundaries, always with a finite deadline.

## 10. OpenTelemetry Collector: Batch Processor and Exporter

The Collector provides a `batch` processor for logs/spans/metrics. It is placed in the pipeline after steps that may reject/drop data—typically **after `memory_limiter`**—so you do not waste work batching data that will subsequently be dropped.

Example **illustrative OTel Collector configuration** (not runnable as-is without a real receiver, network, and exporter):

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 127.0.0.1:4317

processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 512
    spike_limit_mib: 128
  batch:
    send_batch_size: 512
    send_batch_max_size: 1024
    timeout: 200ms

exporters:
  otlphttp:
    endpoint: https://collector.example.invalid

service:
  pipelines:
    logs:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlphttp]
```

Notes:
1. The receiver assumes **OTLP/gRPC** on loopback; verify certificates/network/namespace in real deployments.
2. `memory_limiter` enforces memory limits on the pipeline, not an absolute guarantee that downstream queues will never fill up.
3. `send_batch_size=512` is the **trigger threshold**; `send_batch_max_size=1024` caps exported batch size per config and must not be smaller than the trigger.
4. `timeout=200ms` flushes partial batches by time; exact scheduling depends on the implementation.
5. `otlphttp` points to **example.invalid** intentionally with no real backend; replace with a real endpoint, TLS/auth, and timeout/retry policy.
6. `batch` sits **before the exporter**, while the exporter itself may have its own `sending_queue` and `retry_on_failure`—check the supported config for your specific Collector version/distribution.

The Collector documentation explicitly notes: `send_batch_size` is **not a hard limit**; to cap batch size, use `send_batch_max_size`. If you are trying to fix receiver 413 errors, do not just lower the trigger while forgetting the actual payload limit at the exporter.

### Batching by Metadata and Tenant

Some pipelines need to separate batches by client metadata/tenant or header to avoid mixing data groups. The Collector supports `metadata_keys`/`metadata_cardinality_limit` in the batch processor, but each unique metadata combination creates another batcher and consumes memory. Do not use raw request IDs, tokens, user IDs, or high-cardinality fields as batcher keys; nor should you trust a tenant ID from an unauthenticated client header.

In a multi-tenant system, **data isolation must be enforced by auth/routing/backend policy**, not merely by batch keys or dashboard variables.

## 11. Grafana Alloy and Loki: Batching by Bytes and Time

Grafana Alloy provides the `loki.write` component to ship log entries to Loki. Key `endpoint` parameters include:
- `batch_size`: maximum batch size (e.g., `"1MiB"`), **in bytes**.
- `batch_wait`: wait time before sending a batch (e.g., `"1s"`).
- `url`: Loki push endpoint.
- Other options for TLS, authentication, timeout, retry, or queues depending on version/config.

Example **Alloy configuration snippet** (requires wiring a log source into `loki.write.default.receiver` and setting valid credentials/backend):

```hcl
loki.write "default" {
  endpoint {
    url        = "https://loki.example.invalid/loki/api/v1/push"
    batch_size = "1MiB"
    batch_wait = "1s"
  }
}
```

Do not copy this configuration to a Grafana Loki server expecting it to create an ingester; `loki.write` is a **client/agent component** that needs an upstream log source with an appropriate `forward_to`.

In Grafana Alloy, batch-related metrics may include `loki_write_batch_retries_total`, `loki_write_dropped_entries_total`, `loki_write_sent_entries_total`, and batch/request size histograms. Exact metric names and availability depend on version, deployment, and scrape configuration; verify against actual emitted metrics rather than assuming every metric exists.

### Beware of Multi-Layer Batching

Suppose the Java SDK has a 1-second delay, the Collector has a 200 ms timeout, and Alloy has `batch_wait=1s`. Total latency is **not simply always 2.2 seconds**, because timers and size thresholds can wake early or asynchronously. However, under low traffic, **latency can accumulate** across multiple buffers. Measure end-to-end from event timestamp to searchable time rather than looking only at individual `schedule.delay` values.

## 12. Compression and Payload Limits

Compression usually makes batching much more network-efficient than sending individual records, but keep in mind:
- Compression reduces bytes **on the wire**, not initial object allocation or serialization cost.
- Large batches can cause memory/CPU spikes during serialization or compression.
- Receivers enforce request byte limits or decompressed size limits; 413 errors or rejections can still happen.
- Long stack traces, JSON, and already-compressed binaries have very different compression ratios.
- Do not automatically pick the "smallest" compression algorithm if CPU/latency becomes the bottleneck.

Conceptual comparison table:

| Send Pattern | Pros | Trade-offs |
| --- | --- | --- |
| 1 record/request | Low send latency when unqueued | High request overhead and bandwidth |
| Batch 100 records | Fewer requests, compresses well | Longer pre-send wait, whole-batch retries |
| Batch 1000 records | Even fewer requests | Risk of oversized batches, higher memory |
| Batch with byte + count limits | Adapts to uneven record sizes | Requires accurate pre/post-encoding accounting |
| Batch + compression | Fewer wire bytes on compressible data | Compression CPU/latency, receiver config |

A good benchmark records **uncompressed batch bytes**, **encoded request bytes**, latency, CPU, and receiver error rates. Do not conclude that `batch=1000` is always better than `batch=100` if payloads or network targets change.

## 13. Ordering, Concurrency, and Clocks in Batch Shipping

A batch is typically an ordered collection at the sender, but **display order in the backend has no universal guarantee**:

- Multiple producer threads can enqueue nearly simultaneously; call-site order and queue order can differ.
- Multiple in-flight batches may exist; a later batch can be ACKed before an earlier one.
- Retrying an older batch can deliver events to the backend **after** newer events.
- A collector may attach a late ingestion timestamp or alter sort order.
- Different services have clock skew; timestamps alone do not establish a global total order.
- Restarts or disk replay can re-deliver previously sent events.

Therefore, logs need a **timestamp**, valid source/service/instance fields, and a controlled event ID or correlation ID. For business logic requiring strict ordering, do not rely on log shipping order as a data synchronization mechanism; use a queue/transaction/broker with the appropriate ordering contract.

### Context Propagation with Async/Batch

SLF4J MDC, Log4j `ThreadContext`, or request-scoped data may live on the thread emitting the log. If an exporter worker reads context from its own thread, request IDs will be missing or wrong. The right approach is to **capture immutable fields when creating the `LogRecord`**, and pass them into event/structured attributes. Do not pass references to mutable request objects expecting them to remain valid when the batch is sent seconds later.

## 14. Privacy and Data Safety in Buffers

Batched shipping keeps multiple log events together in memory, on the wire, in agent spools, and in the backend. Risks:
- A single batch can contain tokens, cookies, or sensitive data if the application logs improperly.
- Retries or exporter debug logging can accidentally dump an entire failed batch.
- Disk buffers/backups may retain data longer than primary retention policies.
- Misconfigured multi-tenant batching can mix events across tenants or use the wrong credentials.
- Compression/encryption does not replace minimization/redaction.

Best practices:
1. Log only necessary fields; never include passwords, API keys, `Authorization`, `Cookie`, request bodies, or unnecessary private payloads.
2. Use a structured encoder and enforce field length limits.
3. Redact at the source; filtering at the collector is only **defense-in-depth**, since raw data has already traversed the earlier hop.
4. Connect over TLS, authenticate exporter/receiver, and apply least-privilege backend permissions.
5. Disk spools must have proper ACLs/ownership, quotas, encryption/retention, and cleanup.
6. Never log the full HTTP response body from a collector on error, as responses may contain internal details.
7. Test with fake canary tokens (never real secrets) at both source and backend.
8. Review logs of the **telemetry pipeline itself** to avoid infinite exporter-error feedback loops.

**A large batch does not make a sensitive field less dangerous.** If one log line contains a token, batching and compressing it simply ships that token alongside many other records.

## 15. Monitoring: How to Know Your Batch Pipeline Is Healthy

### 15.1. Golden Signals for Log Pipelines

| Metric/Signal | Meaning | Alert When |
| --- | --- | --- |
| `log_records_emitted_total` | Events created by application | Drops unexpectedly while traffic is normal |
| `queue_size` and `queue_capacity` | Current backlog and limit | Queue is persistently near full |
| `queue_oldest_age_ms` | Oldest unexported event | Exceeds log freshness target |
| `batch_records`/`batch_bytes` | Batch scale | Batches too small (overhead) or too large |
| `export_attempts_total` | Exporter call count | Spikes while receiver is not accepting |
| `export_success_total`/`export_fail_total` | Send outcomes | Failures rise or successes stop |
| `export_retry_total` | Retry count | Backoff storm or prolonged outage |
| `logs_dropped_total` | Records dropped due to queue/full/retry limit | Any unexpected drops on critical logs |
| `export_duration_ms` | Batch send latency | Slow receiver or network |
| `ingestion_lag_ms` | Event time to searchable | Dashboard visibility is delayed |
| Disk spool used/free | Durable buffer utilization | Nearly full, unable to accept more |

These are **descriptive metric names**, not claims that SDK/Collector/Alloy emit these exact names by default. Use the official metrics of your actual component/version, map them to dashboards, and set thresholds based on internal SLOs.

### 15.2. Dashboard for Batch Shipping

An operational dashboard should include:
- Ingress traffic: records/s, bytes/s by service/env.
- Successful exports: records/s, batches/s, average batch size.
- Export failures, retry rate, HTTP/gRPC status codes, and timeouts.
- Queue usage %, oldest record age, disk spool headroom.
- Dropped records by reason and severity where supported by the tool.
- Ingest latency p95/p99 and divergence between accepted vs. exported.
- Backend throttling/429, receiver request size/413, TLS/auth failures.
- Deployment annotations: which batch configs changed near the incident time?
- Runbook/owner links, links to exporter logs, and collector health status.

**Do not monitor only "successful batch count."** For example, 100 batches/s could mean 1 record/batch or 500 records/batch. Measure both record counts and bytes. When sampling or log levels change, a shift in records/s is not necessarily an exporter failure.

### 15.3. End-to-End Freshness Testing

Create a safe canary event with an `event_id` and event timestamp, log it from the application, and wait until the backend can query it. Measure:
- Time from emit to exporter ACK.
- Time from ACK to searchable.
- Total freshness delay.
- Canary loss/duplication across retries, restarts, and collector outages.

A single canary only proves that one test path worked at that moment; it cannot guarantee every log is delivered. For critical observability SLOs, measure continuously and monitor collector health.

## 16. Testing Batched Shipping

### 16.1. Unit Tests Independent of Wall-Clock Time

A reliable approach is to inject a clock or pass `nowMs` as in the demo. Test:
1. Enqueue fewer than `maxBatch`: nothing sent yet.
2. Reach `maxBatch`: sender called once with the exact record set.
3. Below size threshold but past `maxWait`: sends a partial batch.
4. Sender failure: unacknowledged records are not removed.
5. Queue full: throw/drop/block policy actually triggers and updates counters.
6. Successful retry: backlog is cleared once in memory.
7. Shutdown flush: partial-batch records are pushed out.
8. Final batch smaller than threshold preserves order without bogus padding.

Do not test with `Thread.sleep(1000)` hoping the scheduler fires on time; CI environments can be slow or paused. Use a fake clock, fake sender, and test executor for deterministic tests.

### 16.2. Failure Injection and Network Tests

In a test environment:
- Have the sender return timeout, 429, 503, 413, 400, 401/403; verify the corresponding policy.
- Receiver accepts batch but ACK is lost: does retry create duplicates, and how does the backend handle them?
- Vary latency and bandwidth; measure throughput, CPU, heap, and queue depth.
- Kill the JVM or collector **before flush**: verify in-memory data loss matches the contract.
- Restart with a disk spool: verify recovery, duplicates, and checkpoints.
- Collector slower than producer: when queue hits its limit, does the application block/drop per policy?
- Cut network for 30 seconds then restore: measure drain latency and retry-storm behavior.
- Send records with long stack traces: does the batch exceed byte limits?
- Test late timestamps, trace/context propagation, and ordering in the backend.

If using an OTLP exporter and Collector, attach a test receiver instead of the production endpoint, and inspect metadata and exact counts. **Do not interpret the number of enqueued log lines as the number of lines accepted by the backend.**

### 16.3. Stress Tests and Benchmarks

Compare small/medium/large configs under the **same workload**:
- Fixed producer rate; average and percentile record sizes.
- INFO/WARN/ERROR ratio, sampling rate, and log level.
- Network RTT, packet loss, throttling, TLS/compression mode.
- Exporter queue, batch byte limit, `maxWait`, concurrency, retry budget.
- Heap/GC and p95/p99 application latency.
- Backend accepted records/s and end-to-end log freshness.

Increasing batch size can improve throughput within a certain range, but increases latency and heap usage. Do not claim a universal speedup number across environments without measuring.

## 17. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Treating `logger.info` = persisted in backend | Silent event loss | Measure queue/export/ingest stages separately |
| Batching only by count, not by time | Low traffic waits indefinitely or never flushes | Add timeout and shutdown flush |
| `max_wait` too high | Logs appear late on dashboards | Measure freshness, choose per SLO |
| Unbounded queue | OOM and GC pauses during receiver outage | Bound queue, add disk spool/backpressure |
| Silent drop when full | Missing evidence during incidents | Emit dropped metric/alert and explicit policy |
| Immediate tight-loop retries | Retry storm, worsens backend errors | Exponential backoff + jitter |
| Retrying 413/400/429 identically | Unrecoverable errors loop pointlessly | Classify errors and split/fix config |
| No event ID/dedup on retry | Duplicate records when ACKs are lost | Idempotency/dedup per contract |
| `forceFlush` on every event | Defeats batching | Flush only at necessary boundaries |
| Shutdown without deadline | Process hangs or loses buffer | Drain with timeout and report pending count |
| Configuring `send_batch_size` as a hard max | Batches still grow too large | Use `send_batch_max_size` |
| Confusing count and bytes across tools | Wrong payload/request sizes | Check the unit of every parameter |
| Multi-layer batching without measuring | Hidden cumulative latency | Measure end-to-end, minimize layers |
| Using raw user ID as batch metadata key | Memory/cardinality bloat, privacy risk | Use authenticated/bounded tenant keys |
| Async worker reading MDC from its own thread | Wrong correlation IDs | Snapshot context at the call site |
| Tracking only HTTP request count | Unknown number of lost records/batches | Track records, bytes, failures, drops |
| Using in-memory queue for mandatory audit logs | Crash can lose audit trail | Dedicated durable/audit channel |
| Enabling exporter debug to dump batches | Leaks PII/tokens into debug logs | Redact, restrict debug logging and RBAC |

## 18. Production Deployment Checklist

- [ ] Identify all batching layers: JVM, agent, Collector, exporter; know the exact path of every event.
- [ ] Choose count/byte/time triggers; do not confuse trigger thresholds with max batch limits.
- [ ] Configure bounded queues/buffers and an explicit full-queue policy.
- [ ] Bound export timeout, retry attempts/elapsed time, and backoff/jitter.
- [ ] Consider records sent only per the ACK contract; do not conflate enqueue with delivery.
- [ ] Have a plan for ACK ambiguity, duplicates, and ordering if they matter.
- [ ] Implement shutdown flush/drain with a deadline and pending/drop metrics.
- [ ] Verify privacy, TLS/auth, multi-tenancy, disk spool permissions, and retention.
- [ ] Use exact config/version syntax for OTel Java, Collector, and Alloy/Loki.
- [ ] Measure throughput, batch sizes, backlog, drop rate, and end-to-end freshness.
- [ ] Test 429, 503, 413, auth errors, network partitions, crash/restart, and slow receivers.
- [ ] For audit logs, design a durable write path rather than relying on an in-memory queue.
- [ ] Never change batch config solely because one "sent" log line appeared while backend data is missing.
- [ ] Maintain a runbook for full queues, export errors, nearly full spools, or log delays.

## 19. Hands-On Exercises

1. Run `BatchTransportDemo`. Explain why `send_attempts=4` while `delivered=5`, and why `rejected=1` is not in the delivered set.
2. Change `maxBatch=2` and set an appropriate `maxQueue`. Predict the batch order and count before running.
3. Change `maxDelayMs=500`, simulate events arriving closer together than the timeout, and verify early flush behavior.
4. Make `DemoSender` fail **twice**. Design an added retry trigger, deadline, and ensure the queue is not cleared before ACK.
5. Simulate the receiver accepting a batch while the sender times out; explain why retrying causes duplicates and requires an event ID/dedup.
6. Make `maxQueue` smaller than the log emission rate, test drop-new vs. block, and measure the impact on business logic.
7. Add `pending_oldest_age_ms`, `batch_size_records`, and `export_attempts_total` stats to the demo, then sketch a mock dashboard.
8. Measure encoded byte size for 10 short records vs. 10 records with long stack traces. Why is a count threshold insufficient to prevent 413 errors?
9. In an app using the OTel Java SDK, test `otel.blrp.max.export.batch.size` and `otel.blrp.schedule.delay`, and trace which bridge/exporter real logs pass through.
10. Set up a test Collector with `memory_limiter` → `batch` → exporter, and test the effect of `send_batch_size` vs. `send_batch_max_size`.
11. In a test Alloy setup, vary `batch_wait` and `batch_size`, measure request rate and latency to Loki, and verify both credentials and `forward_to` source wiring.
12. Kill the JVM before flush and compare with a controlled shutdown. Assess what can be lost in RAM and when a durable spool is needed.
13. Design retry/backoff honoring `Retry-After` for 429 and batch splitting for 413 in a test environment, with failed/dropped counters.
14. Create a safe canary log and measure emit-to-searchable p95 over several hours; explain why exporter success does not guarantee immediate searchability.

## 20. Key Takeaways

- **Batched shipping** groups multiple log records into one export to reduce overhead and increase throughput, trading off latency, queueing, and memory.
- Exports can be triggered by **size, bytes, time, or flush**; designs must have clear limits and deadlines.
- **Async logging does not automatically mean batching**; retry, compression, and durable buffering are separate mechanisms.
- OpenTelemetry Collector's `send_batch_size` is a **trigger**, while `send_batch_max_size` caps batch size; verify per version.
- Batching reduces request count, but **does not automatically provide at-least-once or exactly-once**; timeouts/ACK loss and retries can still lose or duplicate logs.
- You need a backpressure/drop policy, retry with backoff/jitter, queue/export/drop metrics, shutdown drain, and failure-injection testing.
- Java SDK, Collector, and Alloy/Loki have different count/byte/time parameters; never copy configs without checking units.
- Secure payloads at the source, protect transport/spools, isolate tenants, and never dump batches on error.
- Measure pipeline quality by **records accepted/exported/searchable**, not just logger call counts or successful batch counts.

### References

- OpenTelemetry — *Logs SDK Specification*, Batch LogRecordProcessor, ForceFlush, Shutdown: https://opentelemetry.io/docs/specs/otel/logs/sdk/
- OpenTelemetry Java — *Configure SDK*, `otel.blrp.*` properties: https://opentelemetry.io/docs/languages/java/configuration/
- OpenTelemetry Collector — *Batch processor README* (`send_batch_size`, `send_batch_max_size`, `timeout`): https://github.com/open-telemetry/opentelemetry-collector/tree/main/processor/batchprocessor
- OpenTelemetry Collector — *Processor batch config*: https://github.com/open-telemetry/opentelemetry-collector/blob/main/processor/batchprocessor/config.go
- Grafana Alloy — `loki.write`, `batch_size`, `batch_wait`, and metrics: https://grafana.com/docs/alloy/latest/reference/components/loki/loki.write/
- OWASP — *Logging Cheat Sheet*: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
