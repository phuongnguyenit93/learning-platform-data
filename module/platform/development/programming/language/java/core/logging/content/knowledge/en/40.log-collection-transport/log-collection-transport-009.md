# Buffering During Network Outages in Java Logging

## 1. Why do logs need buffering when the transport path is interrupted?

A Java service can generate thousands of logs per second while the remote collection system is temporarily unable to receive data: network disconnection, DNS failure, TLS handshake failure, overloaded collector, backend maintenance, or endpoints returning 429/503. If every `logger.info` call had to wait for a network request, the business application could slow down severely. If unsent logs were dropped immediately, the investigation trail would vanish right when the system runs into an incident.

**Buffering during network outages** is the mechanism of temporarily holding logs in a bounded queue or storage, applying retry/backoff, and draining them when the destination recovers. A proper system must also answer: **what happens when the buffer is full, does data survive a process crash, do retries cause duplicates, do logs contain private data, and how do we know events were lost?**

~~~text
Java application
    |
    v
Logger / encoder
    |
    v
Bounded buffer (RAM or disk)
    |                      |
    | backend offline      | backend online
    v                      v
  retry later          send -> ACK
    |                      |
    +--> metrics/drop      +--> remove/checkpoint
              |
              v
       monitoring/alert
~~~

This lesson belongs to the **Log Collection and Transport** group of the **Java Core Logging** module. Rather than focusing on simple `logger.info` syntax, it dives into transport mechanisms, resource bounds, and end-to-end reliability.

### Learning Objectives

- Distinguish buffering, retry, acknowledgment (ACK), durability, and retention.
- Understand that buffers at the Java JVM, local file, log agent/collector, and broker levels provide different guarantees.
- Choose a bounded queue and overflow policy: block, reject/drop-new, drop-old, low-level shedding, or disk spill.
- Explain at-most-once, at-least-once, duplicates, and ACK ambiguity.
- Write a standalone Java 17 program that simulates an offline network, a full buffer, and delayed drain.
- Calculate buffer capacity and backlog drain rate when the network recovers.
- Use retries with timeouts, exponential backoff, jitter, and permanent error handling.
- Understand the limitations of Logback `AsyncAppender`, OpenTelemetry Collector, Fluent Bit, and `KafkaProducer`.
- Design metrics, runbooks, failure/recovery tests, security, and privacy controls.

## 2. Where logs can be buffered

Not every queue serves the same purpose.

| Layer | Storage | Survives network outage? | Survives restart? |
| --- | --- | --- | --- |
| Queue inside Java application | JVM RAM | Yes, within capacity | Not guaranteed on its own |
| Logback AsyncAppender | RAM queue | Decouples caller from slow appenders | Not guaranteed after a JVM crash |
| stdout and container runtime log | Node file/runtime | Can serve as a source for a collector to re-read | Depends on node/rotation/volume |
| Local rolling FileAppender | Local file | Keeps logs on disk when remote target fails | Depends on filesystem, flush, retention |
| Collector in-memory queue | Collector RAM | Yes, until full or retry budget exhausted | Not guaranteed |
| Collector persistent queue | Disk spool | Yes, if capacity and policy allow | Recoverable if the volume remains intact |
| Kafka producer buffer.memory | Client RAM | Yes, while waiting to send | Does not protect unACKed records on process death |
| Kafka broker storing ACKed records | Broker storage | Depends on cluster/quorum/retention | Follows broker durability/replication |
| Transactional outbox | Database transaction | Can hold events until a publisher sends them | Follows DB durability |

A local log file **is not automatically a reliable spool**. If the collector does not know how far it has sent, and lacks checkpoints and ACKs, the file is merely a dataset for manual recovery or custom re-reading.

A RAM buffer is also **not durable data**. When a pod or JVM is killed, any items not yet transferred can vanish. A durable queue mechanism must write data to disk/DB before reporting accepted per contract, and provide recovery logic.

### Choosing a buffer by goal

- **Reduce request latency:** use async logging or write to stdout and handle transport at another layer; watch for the risk of a full queue blocking callers.
- **Tolerate collector/backend network outages:** use an agent/collector with a queue and retries, considering persistent storage.
- **Survive a JVM crash:** write events to a durable store/spool before reporting them as saved per requirements.
- **Protect mandatory audit trails:** prefer a dedicated transactional/outbox/audit store; best-effort logging does not replace business commits.

## 3. Buffering, retry, ACK, and delivery semantics

You must distinguish:

~~~text
EVENT_CREATED
     |
     v
BUFFER_ACCEPTED  <- may only be in RAM
     |
     v
SEND_ATTEMPT
     |
     +--> failure -> retry_wait
     |
     v
REMOTE_ACKNOWLEDGED
     |
     v
REMOVE_FROM_QUEUE / CHECKPOINT
~~~

**Buffer accepted** does not mean the remote side has stored it. **Network send returned** does not mean an async send succeeded. An **ACK** from a collector may only prove the collector received it, not necessarily that the remote index durably persisted it. To establish an accurate SLA, you must define which layer issues the ACK.

| Model | Meaning | Trade-off |
| --- | --- | --- |
| Best effort | Attempts to send when possible, no guarantee for every event | Simple, may lose events |
| At-most-once | Per contract scope, does not resend after one attempt | Fewer duplicates, loses events on failure |
| At-least-once | Retries under designed conditions until ACKed | May produce duplicates |
| Exactly-once | Effectively once per specific protocol/transaction | Cannot be achieved with retry + queue alone |

**ACK ambiguity:** if the backend persisted the event but the ACK response is lost, the sender will time out and may resend. If you delete the event before ACK, there is a risk of loss. If you keep it until after ACK, there is a risk of duplication.

~~~text
Sender                        Receiver
  |--- event_id=evt-7 --------->|
  |                            | persist evt-7
  |<---------- ACK ------------X  response lost
  |--- retry evt-7 ------------>|
  |                            | evt-7 may be duplicated
~~~

Use a stable `event_id` across attempts and deduplication/idempotent ingestion at the destination if supported. A correlation ID does not replace `event_id`: hundreds of logs within the same request can share the same correlation ID.

## 4. Full queue: a decision you cannot skip

A buffer must bound the number of items and/or total bytes; an unbounded queue during a network outage can cause an `OutOfMemoryError` or fill up the disk.

| Overflow policy | Advantage | Risk |
| --- | --- | --- |
| Block producer | Reduces temporary log loss | Slow requests, cascading failure |
| Bounded wait then reject | Bounds latency | Events rejected on timeout |
| Drop-new | Preserves older logs | Loses the newest information |
| Drop-old | Preserves recent logs | Loses the root cause at outage start |
| Shed DEBUG/TRACE | Reduces load by prioritizing critical events | Does not retain full detail |
| Spill to disk | Extends outage tolerance | Disk quota, latency, persistence, security |
| Fail business operation if audit cannot be saved | Protects audit invariants when designed properly | Reduces availability |

**Do not drop silently.** If enqueue is rejected, the caller/collector must record the rejected count, outcome, and alert. A remote log line reporting "dropped event" can also be lost when that remote path is failing; metrics and alerts need to be sufficiently independent.

`INFO` does not automatically mean less important data; an audit event might use `INFO`. Classify logs by purpose and business requirements, not just level.

### Measuring a queue by item count alone is not enough

A 100-byte event and a 50 KB event both count as one item, yet consume vastly different amounts of memory. If a Collector's `queue_size` is measured in requests/batches, you must know how many logs each batch contains. If a heap queue stores Java Strings/objects, overhead beyond the raw payload is also significant.

Do not use an unbounded `ConcurrentLinkedQueue` to avoid blocking and consider it safe. Without backpressure, the system merely shifts the failure from the network to RAM/GC.

## 5. Complete Java 17 demo: network outage, hold up to three events, drain on recovery

This program uses **pure JDK 17** and JUL `Logger` for local diagnostics. `FakeSender` simulates an offline/online remote endpoint: no real network, Kafka, Maven, Logback, or server required. `BoundedBuffer` uses `ArrayDeque` for a **single-threaded** model with `capacity=3`; the fourth event is rejected.

**File: NetworkBufferDemo.java**

~~~java
import java.io.IOException;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class NetworkBufferDemo {
    private static final Logger LOG =
            Logger.getLogger("example.logging.transport");

    record Event(String id, String message) { }

    interface Sender {
        void send(Event event) throws IOException;
    }

    static final class FakeSender implements Sender {
        boolean online;
        final Set<String> deliveredIds = new LinkedHashSet<>();

        @Override
        public void send(Event event) throws IOException {
            if (!online) {
                throw new IOException("network offline");
            }
            if (deliveredIds.add(event.id())) {
                LOG.info("REMOTE_ACCEPTED id=" + event.id());
            } else {
                LOG.info("REMOTE_DUPLICATE id=" + event.id());
            }
        }
    }

    static final class BoundedBuffer {
        private final int capacity;
        private final Deque<Event> queue = new ArrayDeque<>();

        BoundedBuffer(int capacity) {
            if (capacity < 1) {
                throw new IllegalArgumentException("capacity");
            }
            this.capacity = capacity;
        }

        boolean offer(Event event) {
            if (queue.size() >= capacity) {
                LOG.warning("BUFFER_REJECTED id=" + event.id());
                return false;
            }
            queue.addLast(event);
            LOG.info("BUFFERED id=" + event.id());
            return true;
        }

        void drain(Sender sender) {
            while (!queue.isEmpty()) {
                Event oldest = queue.peekFirst();
                try {
                    sender.send(oldest);
                    // Only remove after the simulated ACK.
                    queue.removeFirst();
                } catch (IOException error) {
                    LOG.warning("RETRY_LATER id=" + oldest.id());
                    return;
                }
            }
        }

        int pendingCount() {
            return queue.size();
        }
    }

    public static void main(String[] args) {
        Handler output = new Handler() {
            { setLevel(Level.ALL); }

            @Override
            public synchronized void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(record.getMessage());
                }
            }

            @Override
            public void flush() {
                System.out.flush();
            }

            @Override
            public void close() {
                flush();
            }
        };

        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);
        LOG.addHandler(output);

        try {
            BoundedBuffer buffer = new BoundedBuffer(3);
            FakeSender sender = new FakeSender();

            buffer.offer(new Event("evt-1", "login"));
            buffer.offer(new Event("evt-2", "payment"));
            buffer.drain(sender); // Offline: keep evt-1, evt-2.

            buffer.offer(new Event("evt-3", "inventory"));
            buffer.offer(new Event("evt-4", "notification"));
            // evt-4 is rejected: the queue already has three items.

            sender.online = true;
            buffer.drain(sender); // Online: send three items.
            LOG.info("PENDING " + buffer.pendingCount());
        } finally {
            LOG.removeHandler(output);
            output.flush();
            output.close();
        }
    }
}
~~~

**Compile and run:**

~~~bash
javac -encoding UTF-8 NetworkBufferDemo.java
java NetworkBufferDemo
~~~

**Exact stdout:**

~~~text
BUFFERED id=evt-1
BUFFERED id=evt-2
RETRY_LATER id=evt-1
BUFFERED id=evt-3
BUFFER_REJECTED id=evt-4
REMOTE_ACCEPTED id=evt-1
REMOTE_ACCEPTED id=evt-2
REMOTE_ACCEPTED id=evt-3
PENDING 0
~~~

### Explanation

1. The first two events are accepted into the queue while the sender is disconnected.
2. `drain` tries to send `evt-1`; `IOException` prevents the queue from **removing** it, because no ACK was received.
3. `evt-3` is accepted, taking the last slot.
4. `evt-4` is `BUFFER_REJECTED`: it is not in the buffer. In a real product, the caller must handle `false` and increment a separate counter.
5. When `sender.online=true`, `drain` sends `evt-1`, `evt-2`, `evt-3` in FIFO order and the queue becomes empty.
6. `FakeSender` keeps `Set deliveredIds` to illustrate that the receiver can recognize IDs; data in this `Set` is also only in RAM, not durable deduplication.
7. JUL `Logger` is routed through a local stdout `Handler` rather than using the remote sender to report transport errors, avoiding logging errors from the logging system back into the failing system itself.
8. Output order is deterministic because the code uses no threads, schedulers, or real network sockets.

**Limitations:** The demo does not handle thread safety (single-threaded `ArrayDeque`), disk spooling, retry timers/backoff, network timeouts, lost ACKs, process crashes, or durable ingestion. It should only be used to understand the mechanism. A production program needs an appropriate concurrent queue, worker lifecycle, timeouts, metrics, and a full-queue policy.

## 6. Retry with timeout, exponential backoff, and jitter

If the network is unreachable, retrying continuously can create a retry storm. Use **exponential backoff**:

~~~text
attempt 1: immediate
attempt 2: about 1 s
attempt 3: about 2 s
attempt 4: about 4 s
attempt 5: about 8 s
...
cap at max interval, add jitter
~~~

This is an example policy, not a universal default for every exporter. A full-jitter formula:

~~~text
delayCap = min(initialDelay * 2^(attempt - 1), maxDelay)
actualDelay = random(0, delayCap)
~~~

In the implementation, avoid integer overflow, use `ScheduledExecutorService`/a scheduler instead of sleeping on a request thread, and ensure proper worker stop/shutdown.

### Error classification

- Transient: timeout, TCP reset, backend overload, some 429/5xx responses. Retry with timeout/backoff.
- Errors requiring fixes: invalid credentials 401/403, invalid schema, payload too large, wrong TLS certificate. Do not retry forever just because the code caught an `Exception`.
- Rate limiting: inspect `Retry-After` when appropriate.
- Permanent record failure: quarantine/DLQ per policy and increment a counter, preventing a single bad event from blocking the entire queue.
- Retry budget: limit attempts/max elapsed time, and handle aged-out events according to retention and priority.

**Do not retry infinitely on finite resources.** Even if infinite attempts are allowed, disk and heap are still bounded. You need a clear policy for when space runs out, events get too old, or the backlog threatens the application.

### How does jitter help?

If hundreds of pods retry at the exact same 5-second mark, a newly recovered backend can be overwhelmed again. Jitter spreads out retry timing. During recovery, you must control **recovery throughput**, not just the retry interval.

## 7. Persistent disk buffer and WAL

A memory queue loses data when the JVM/collector process dies. A disk queue or WAL can help recover pending events after a restart, but it must be implemented and tested properly.

~~~text
Encode event + immutable event_id
    |
    v
Append into disk segment/WAL
    |
    v
Persist according to fsync/durability policy
    |
    v
Network worker sends event
    |
    +--> on ACK: persist checkpoint/progress
    |
    +--> on retryable error: keep pending
    |
    v
Compact fully acknowledged segments
~~~

A production-grade reliable spool requires:

- Record framing with length/version/checksum and handling of partial writes.
- Concurrency control and locking/ownership if multiple processes access it.
- `fsync`/flush policy: a successful `write()` is not guaranteed safe across power loss.
- Checkpoints reflecting ACKed events that can be recovered after a crash.
- Replays that may cause duplicates if a checkpoint was not persisted in time.
- Safe segment compaction/deletion without accidentally removing pending items.
- Disk quota, inode limits, free-space reservation, and overflow policy.
- TTL/retention for sensitive data in the spool; ACLs/encryption when needed.
- Handling corrupted/truncated segments with metrics/alerts rather than silently ignoring them.
- Volume lifecycle: Kubernetes ephemeral storage differs from a persistent volume.

Do not build your own "durable spool" with just `Files.writeString(..., APPEND)`. An append-only file without checkpoints/CRC/recovery does not guarantee proper delivery across crashes. Prefer a maintained collector/agent persistent queue when appropriate.

### Post-ACK race condition

~~~text
1. Backend persists event.
2. ACK arrives at collector.
3. Collector prepares to checkpoint.
4. Collector crashes before durable checkpoint.
5. Restart -> event may be resent.
~~~

Duplicates can still occur even when both the disk buffer and receiver operate correctly. You need a protocol that clearly defines ACKs and idempotency where logs are consumed.

## 8. Buffer sizing and drain time

Estimate the volume of logs generated during an outage:

~~~text
raw_bytes = events_per_second
          × average_encoded_bytes_per_event
          × outage_seconds

required_bytes ≈ raw_bytes × headroom_factor
~~~

For example, 1000 events/s at 500 bytes per event for a 10-minute (600-second) outage: **300,000,000 bytes, about 300 MB of raw data**. In practice, there is also queue/index/chunk overhead and traffic spikes.

A sizing design needs to know:

1. Normal hourly event rate and peak rate; do not rely on a single average.
2. Encoded bytes/event at p95/max percentiles, not Java `String` character count.
3. Desired outage duration to tolerate.
4. RAM/disk quota, reserved free space, and TTL.
5. Backend recovery ingest rate and retry/drain limits.
6. Which event classes must be kept and which can be sampled/dropped.
7. Number of collector instances resending simultaneously.
8. Retention and privacy rules for aged backlogs.

**Calculating drain time:** if after recovery the backend accepts 1100 events/s while the app continues producing 1000 events/s, the net backlog drain rate is 100 events/s. A backlog of 600,000 events will take **6000 seconds (100 minutes)** to clear, assuming constant rates.

A large buffer whose destination lacks capacity exceeding the source rate will never finish draining. You must calculate queue capacity and recovery throughput together.

## 9. Logback AsyncAppender: not a durable network buffer

Logback `AsyncAppender` typically places a RAM queue between business threads and the sink appender.

Example **Logback** config:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ASYNC"
              class="ch.qos.logback.classic.AsyncAppender">
        <queueSize>1024</queueSize>
        <discardingThreshold>0</discardingThreshold>
        <neverBlock>false</neverBlock>
        <maxFlushTime>5000</maxFlushTime>
        <appender-ref ref="CONSOLE"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="ASYNC"/>
    </root>
</configuration>
~~~

This is only a **configuration snippet**, not guaranteed to fit every system.

- `queueSize=1024` counts events, not bytes or outage duration.
- `discardingThreshold=0` disables the default automatic shedding threshold for lower log levels; it does not make the queue unbounded.
- `neverBlock=false` means producers may block when the queue is full, impacting latency.
- `maxFlushTime=5000` bounds how long shutdown waits to drain; events may still remain and be lost on timeout.
- The `ConsoleAppender` target writes to stdout. A disconnected collector in another process is not solved by Logback's RAM queue.
- An abrupt JVM crash can still lose the undrained queue.
- Default `AsyncAppender` may drop some lower-level events near capacity; always test the exact deployed config.

For Log4j 2, async logging has its own queue/Disruptor and overflow semantics; do not copy Logback parameters into Log4j 2. Read the documentation for your exact version.

## 10. OpenTelemetry Collector: sending_queue and file_storage

Some Collector exporters use the exporter helper supporting `sending_queue` and `retry_on_failure`. Enabling a storage extension can provide a persistent queue on disk.

**Reference YAML example** (requires a binary with `otlp` receiver, `batch` processor, `otlp` exporter, and `file_storage` extension; endpoint/volume/certificates are samples):

~~~yaml
extensions:
  file_storage/logqueue:
    directory: /var/lib/otelcol/log-queue

receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317

processors:
  batch:
    timeout: 5s
    send_batch_size: 512

exporters:
  otlp/backend:
    endpoint: logs.example.internal:4317
    tls:
      insecure: false
    sending_queue:
      enabled: true
      storage: file_storage/logqueue
      queue_size: 1000
    retry_on_failure:
      enabled: true
      initial_interval: 5s
      max_interval: 30s
      max_elapsed_time: 10m

service:
  extensions: [file_storage/logqueue]
  pipelines:
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlp/backend]
~~~

### Understanding the configuration correctly

- `sending_queue.queue_size` may count requests/batches by default, **not automatically log records**; some versions allow sizing by items/bytes.
- `storage: file_storage/logqueue` selects a persistent queue on disk, provided the extension is built and declared properly.
- Retrying with `max_elapsed_time=10m` is finite; once exceeded, batches may be dropped per exporter semantics. It does not keep them forever.
- When the queue/disk is full or an I/O error occurs, enqueue can fail and data may be lost if upstream does not handle it.
- The directory must be writable on a suitable volume. Deleting an ephemeral volume will lose the spool.
- Protect the spool with ACLs, restricted access/retention, and encryption where needed.
- Monitor `queue_size`/capacity, `dropped`/`send_failed`, retries, and disk usage.
- Some context added by auth extensions is not persisted across a persistent queue; check how authentication behaves after replay.

**Do not copy directly to production:** replace with real endpoints, TLS/auth, resource limits, and disk quotas, and validate the config against your specific Collector build. Core/minimal Collector builds may lack the `file_storage` extension; a distribution that includes it is usually required.

## 11. Fluent Bit: filesystem buffering

Fluent Bit supports `storage.type filesystem` on inputs along with storage path and queue limit parameters. Example **fluent-bit.conf** to understand the structure:

~~~ini
[SERVICE]
    Flush                   1
    Log_Level               info
    storage.path            /var/lib/fluent-bit/buffer
    storage.sync            normal
    storage.max_chunks_up   128

[INPUT]
    Name                    tail
    Tag                     app.logs
    Path                    /var/log/app/*.log
    DB                      /var/lib/fluent-bit/tail.db
    storage.type            filesystem

[OUTPUT]
    Name                    http
    Match                   app.logs
    Host                    logs.example.internal
    Port                    443
    URI                     /ingest
    Format                  json
    tls                     On
    Retry_Limit             False
    storage.total_limit_size 1G
~~~

This is a snippet without real credentials/endpoints and is not a verified deployment.

- `storage.type filesystem` enables buffering chunks on disk.
- `storage.max_chunks_up` primarily limits chunks kept in the "up" state in memory, **not total disk capacity**.
- `storage.total_limit_size` bounds the logical queue for the output; when reached, older chunks may be dropped to prioritize newer data per product documentation.
- `Retry_Limit False` may allow unlimited retry attempts, but disk space and log sources remain finite.
- The `tail` input DB checkpoint is not the same as the output spool. If a source file is rotated/deleted before Fluent Bit tails it, the spool cannot recover un-ingested lines.
- Ephemeral volumes can also lose chunks when a pod or node is lost.

To test properly, use a test endpoint returning 503 then 200, and observe the disk queue/chunks, discarded count, retries, and event IDs received after recovery.

## 12. KafkaProducer: buffer.memory is not an outbox

When Java sends logs/events via Kafka, the client producer has a RAM buffer. A sample config:

~~~properties
buffer.memory=33554432
max.block.ms=60000
delivery.timeout.ms=120000
acks=all
enable.idempotence=true
~~~

Values are illustrative only; check your exact Kafka client version.

- `buffer.memory` approximately bounds the RAM used to hold records pending send; it is not a hard cap on all producer allocations.
- `max.block.ms` bounds certain blocking operations waiting on buffer/metadata; timeouts may throw errors.
- `delivery.timeout.ms` sets an upper bound on delivery and reporting the outcome through the producer API per contract.
- `acks=all` is the broker acknowledgment level per replication semantics; it does not prove downstream processing succeeded.
- `enable.idempotence` helps limit duplicates from producer retries within Kafka's scope, without providing end-to-end exactly-once semantics.
- A producer process crash can lose records in RAM not yet acknowledged by the broker.

Callback snippet (requires `kafka-clients`, a logger, and application variables; **not standalone pure JDK**):

~~~java
producer.send(record, (metadata, error) -> {
    if (error == null) {
        logger.info("publish_ack topic={} offset={}",
                metadata.topic(), metadata.offset());
    } else {
        logger.error("publish_failed", error);
    }
});
~~~

Do not print `publish_success` immediately after an async `send` call. Nor should you feed the failing producer's own logger into a failure-logging loop: an error callback creating a new log sent through the same producer can make the queue grow indefinitely. Use bounded local status/metrics.

For audit events requiring durable coupling with a DB transaction, consider a **transactional outbox**: write the event in the same transaction as state, have a publisher relay it in a controlled manner, and have consumers deduplicate by event ID.

## 13. Stacking multiple buffers: more is not always safer

A pipeline might look like:

~~~text
Java AsyncAppender (RAM)
  -> stdout / node log file
  -> Fluent Bit filesystem chunks
  -> OpenTelemetry Collector persistent queue
  -> remote backend
~~~

This can make sense, but it introduces subtle failure modes:

- The app queue is empty while the Collector still holds hours of backlog.
- One layer uses drop-new while another uses drop-old, breaking event sequence preservation.
- Local rolling logs are deleted before the collector tails them.
- Multiple layers retry simultaneously, creating traffic spikes when the backend recovers.
- During a network outage, the app keeps logging normally while the collector disk is already full and dropping events.
- Events are replayed across multiple hops due to ACK ambiguity.
- Each spool holds copies of sensitive data with different retention periods.

Define the purpose of each layer and collect metrics across the entire pipeline. One tested persistent queue can be better than multiple unowned queues with unknown data loss behavior.

## 14. Shutdown, crash, restart, disk full

**Graceful shutdown:** stop accepting new events or apply a policy, drain within a bounded time, flush/close the exporter, and report the pending count. However, shutdown hooks may not run on `kill -9`, OOM, or node power loss.

**Crash recovery:** with a durable spool, restart must verify segments/checksums, read checkpoints, replay pending events, and handle duplicates. A crash after ACK but before a durable checkpoint can replay already-delivered events.

**Disk full:** when a volume can no longer be written to, a persistent queue may reject/drop/block depending on the product's mechanism. You need quotas, reserved space, alerts, and a runbook so the disk buffer never fills the node and impacts the entire application.

**Pod lifecycle:** if the log buffer resides on an ephemeral filesystem, deleting the pod/node can lose it. A `PersistentVolume` does not automatically solve all crash consistency issues; the storage/queue mechanism itself must also support it.

**Retention:** logs in a spool are still managed data that may contain IPs, user IDs, trace IDs, and sensitive information. Avoid infinite retries that hold an event longer than policy allows.

### Diagnostic feedback loop

If a remote appender fails to send and immediately emits an `ERROR` log back through the same remote appender, a loop can form:

~~~text
send fails
  -> log failure
  -> enqueue failure log
  -> send fails again
  -> queue grows faster
~~~

Use metrics or an independent local diagnostic channel, rate-limit it, and never print raw payloads or credentials in error messages.

## 15. Metrics, alerts, and privacy

Illustrative **metric names** you can use:

| Metric | Question |
| --- | --- |
| log_buffer_pending_events | How many events are waiting? |
| log_buffer_pending_bytes | How many bytes are pending? |
| log_buffer_capacity_bytes | Is it close to full? |
| log_buffer_oldest_age_seconds | How long has the oldest event been waiting? |
| log_buffer_rejected_total | How many events were rejected? |
| log_buffer_dropped_total | How many events were dropped? |
| log_delivery_attempts_total | Is there a retry storm? |
| log_delivery_failures_total | Which error types are increasing? |
| log_delivery_ack_total | How many events/batches were ACKed? |
| log_delivery_latency_seconds | How long from creation to ACK? |
| log_spool_used_bytes | How much disk spool space remains? |
| log_spool_corrupt_total | Are there corrupted segments? |

OpenTelemetry Collector exposes exporter queue metrics, such as `otelcol_exporter_queue_size` and `otelcol_exporter_queue_capacity` depending on the release. Always check the unit: requests/batches/items/bytes.

**Alert** when occupancy is high, oldest age exceeds SLA, rejected/dropped > 0 for critical logs, disk quota is high, backend is unavailable for an extended period, retries are continuous, or backlog fails to shrink after coming online.

**Security:** do not log tokens/cookies/passwords into the buffer; redact before enqueueing; configure ACLs/encryption when needed, and restrict retention and query scope. Do not use high-cardinality fields like `user_id`/`event_id`/`correlation_id` as metric labels. Alerts should still function even when remote logging is disconnected, rather than relying solely on querying the broken backend.

## 16. Test matrix for outage and recovery

| Scenario | Required assertion |
| --- | --- |
| Endpoint online | Queue drains and ACKs per contract |
| Short offline | Buffer retains data within capacity |
| Long offline exceeding capacity | Correct overflow policy, rejected/dropped metrics recorded |
| Slow backend | Request latency/backpressure stays within budget |
| HTTP 429 or 503 | Retry/backoff throttles properly |
| HTTP 401/403, invalid schema | No infinite retries, alert/quarantine triggered |
| ACK lost after remote persist | Retries with same `event_id`, duplicates detectable |
| JVM crash | RAM queue is not treated as durable |
| Collector restart | Disk queue recovers if volume/format supports it |
| Pod deleted | Ephemeral storage is not assumed to persist |
| Disk full | Reject/drop/block per policy, never silent |
| Corrupt/truncated spool | Recovery/quarantine, clear status |
| Two processes sharing spool | Ownership/locking prevents file corruption |
| Network flap | Retry jitter/backoff, no busy-loop |
| Shutdown with pending events | Clear deadline/flush/remaining count |
| Oversized payload | Byte limits and controlled error handling |
| PII/token in payload | Redaction before buffering |
| Multiple producer threads | Thread-safety, accurate counts and unmixed IDs |
| Low recovery throughput | Queue age/drain time triggers alert |

### Unit tests for the Java demo

1. Send `evt-1` and `evt-2` into the buffer; `pending=2`.
2. Drain while offline; `pending` stays 2, no items removed.
3. Add `evt-3` successfully; `evt-4` is rejected when `capacity=3`.
4. Switch online; drain; receiver gets `evt-1/2/3` in FIFO order.
5. Verify `evt-4` was not received and `pending=0`.
6. Extend `FakeSender` for a case where `evt-2` is persisted but `IOException` is thrown (lost ACK); retry with the same `event_id` and compare duplicates.

### Integration testing with an endpoint stub

Create a test HTTP server that returns 503, 429, 200, or timeouts on a schedule. Never disconnect shared developer/production networks:

1. Emit N distinct event IDs and record their original timestamps.
2. Take the endpoint offline; verify queue size/bytes/oldest age.
3. Restart the exporter while events are pending to verify disk persistence.
4. Restore the endpoint; count events/duplicates at the receiver.
5. Test overflow, disk quota, and error classification.
6. Verify the volume when a pod/node is replaced.
7. Compare event IDs before/after the outage and calculate loss/duplication stats.
8. Clean up test artifacts and restore configuration.

Do not simulate disk full by filling up a shared CI runner disk. Use a quota-bounded test volume or sandbox.

## 17. Troubleshooting

| Symptom | Possible cause | Remediation |
| --- | --- | --- |
| Logs lost during offline | RAM buffer full/dropped | Check counters and overflow policy |
| Logs lost after restart | Queue only in RAM/ephemeral | Consider durable store, verify volume |
| Duplicate logs | ACK lost/batch retry | `event_id`/dedup, receiver contract |
| JVM requests slowed down | Queue full and blocking producer | Adjust `neverBlock`/overflow/capacity intentionally |
| Disk grows endlessly | Misconfigured spool/retention | Quotas, age limits, compaction, metrics |
| Collector back online but not sending | Wrong TLS/auth, bad payload, retries exhausted | Status/error class, quarantine |
| Fluent Bit missing records | Tail file rotated before ingest | Tail checkpoint and source retention |
| Kafka send timeout | Buffer/metadata/broker unavailable | `buffer.memory`, `max.block`, `delivery.timeout` |
| OTLP `queue_size` low but RAM high | Queue counts batches, other overhead | Sizer, event size, process memory |
| Extremely slow recovery | Destination barely faster than source | Calculate drain throughput and throttle |
| Logging creates its own log storm | Diagnostics sent to same remote sink | Local metrics/status with rate limiting |
| PII persists in spool | Redaction happens too late | Redact before enqueue, ACL/retention |

### Recommended runbook

1. Identify the service/exporter/endpoint and when the outage began.
2. Measure pending queue, oldest event age, disk usage, retry failures, and drop count.
3. Classify the root cause: network/DNS, TLS, credentials, backend, rate limit, or payload.
4. Protect the application using an approved overflow policy; never manually delete a spool containing mandatory audit data.
5. Fix connectivity or backend capacity.
6. Drain with rate limits, monitoring load spikes and duplicates.
7. Reconcile event IDs/trace IDs across the outage window.
8. Update alerts, capacity, retention, backoff, and integration tests.

## 18. Mistakes to avoid

**1. Using an unbounded queue.** A long network outage turns into an OOM; always enforce capacity and monitoring.

**2. Treating async logging as durable.** Logback `AsyncAppender` RAM is lost when the JVM dies.

**3. Treating a single send call as success.** An async API returning a `Future` is not an ACK; you need a callback/contract.

**4. Retrying too fast.** Can cause a storm; use backoff and jitter.

**5. Retrying a permanent error forever.** 401, bad schema, or oversized payloads need alerting/quarantine.

**6. Deleting pending events before ACK.** Can lose events when send fails.

**7. Assuming ACK guarantees exactly-once.** A lost ACK can still lead to duplicates.

**8. Treating a disk queue as infinite.** A full disk or lost ephemeral volume still causes log loss.

**9. Not calculating drain rate.** The buffer will keep growing if the destination is not faster than the source.

**10. Logging remote errors only through the failing remote sink.** Creates a feedback loop.

**11. Not testing crashes or lost ACKs.** The happy path says nothing about guarantees.

**12. Keeping PII logs in the spool forever.** Buffers must still comply with security and retention policies.

## 19. Practice Exercises

**Exercise 1 – Replace drop-new with drop-old.** Modify `BoundedBuffer` so that when full, it drops the oldest event and accepts `evt-4`. Compare which IDs the backend receives and why drop-old can lose the origin of an outage.

**Exercise 2 – Lost ACK.** Have `FakeSender` add `evt-2` to `deliveredIds` and then throw `IOException` once. Retrying with the same ID produces a duplicate; propose a receiver idempotency mechanism.

**Exercise 3 – Concurrent queue.** Replace `ArrayDeque` with `ArrayBlockingQueue` and use `ScheduledExecutorService` for retries; test concurrency, interrupts, and shutdown.

**Exercise 4 – Calculate byte capacity.** With 1000 events/s, 500 bytes/event, a 10-minute outage, and 1.5x headroom, calculate the disk quota; compare with a batch-measured buffer.

**Exercise 5 – OTel `file_storage`.** In a test environment with a Collector supporting the extension, send OTLP logs, stop the backend, restart the collector, then start the backend; verify pending queue, volume, retry deadline, and duplicates.

**Exercise 6 – Fluent Bit.** Tail a file with event IDs and have the HTTP output return 503 then 200. Observe storage chunks, quota, and skipped records.

**Exercise 7 – Kafka.** With a test broker, vary `buffer.memory`/`max.block.ms`/`delivery.timeout.ms` and observe callbacks when the broker is unavailable; do not assume producer RAM survives process death.

**Exercise 8 – Security.** Send a fake token/CRLF through a test pipeline and assert redaction/escaping before entering the buffer, with ACLs and retention in place.

**Exercise 9 – Incident.** Simulate 20 pods going offline simultaneously, design jitter and drain limits, and set up metrics/alerts so a broken backend does not block alerting.

## 20. Key Takeaways

**Buffering during network outages is a trade-off among availability, durability, latency, resources, and loss/duplication.** A memory queue helps with short outages, while a disk spool/persistent queue can preserve logs across restarts when storage and recovery conditions are met—but neither is immune to full disks, retry budgets, corruption, or retention rules. A full queue must have explicit behavior; retries must have timeouts, backoff, jitter, and transient/permanent error classification.

After an outage, ACK ambiguity can cause events to be resent; a stable `event_id` and idempotent ingestion are essential mechanisms. Calculate **backlog drain time**, set up independent metrics/alerts, and test network loss, lost ACKs, disk full, crashes, restarts, shutdowns, and sensitive data handling.

Logback `AsyncAppender`, Kafka producer `buffer.memory`, Fluent Bit filesystem buffering, and OpenTelemetry Collector `sending_queue`/`file_storage` do not share the same durability guarantees. For mandatory audit trails, use a durable event store or an outbox tied to the business transaction rather than relying solely on a logger queue.

### References

- OpenTelemetry Collector Resiliency: https://opentelemetry.io/docs/collector/resiliency/
- OpenTelemetry Collector Exporter Helper: https://github.com/open-telemetry/opentelemetry-collector/tree/main/exporter/exporterhelper
- OpenTelemetry Collector file_storage: https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/extension/storage/filestorage
- Fluent Bit Buffering and Storage: https://docs.fluentbit.io/manual/administration/buffering-and-storage
- Fluent Bit Backpressure: https://docs.fluentbit.io/manual/administration/backpressure
- Logback AsyncAppender: https://logback.qos.ch/manual/appenders.html
- Apache Log4j 2 Async Logging: https://logging.apache.org/log4j/2.x/manual/async.html
- Apache Kafka Producer Configs: https://kafka.apache.org/42/configuration/producer-configs/
- Oracle Java 17 BlockingQueue: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html
- Oracle Java 17 ScheduledExecutorService: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
