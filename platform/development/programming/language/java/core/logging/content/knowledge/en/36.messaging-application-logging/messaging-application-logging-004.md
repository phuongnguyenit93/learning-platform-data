# Topics and Partitions in Messaging Application Logging (Java/Kafka)

## 1. Lesson Objectives

In a message-processing application, a log line such as “message received” is usually **not enough to investigate errors**. When multiple producers and consumers run concurrently, the same type of message can arrive from multiple topics, partitions, and consumer groups; a record can also be reprocessed after a retry, restart, or rebalance.

**Topic and partition** are critical context when logging messaging applications, especially with **Apache Kafka**. Recording the right metadata helps determine: which stream a message belongs to, which partition it is in, what its offset is, whether it has been acknowledged by the broker or how far the consumer has processed it, and why the same record appears multiple times in the logs.

This lesson uses Kafka as the primary example because Kafka has explicit concepts of **topic, partition, and offset**. Systems such as RabbitMQ, JMS, or SQS have their own queue/topic models, delivery tags, message IDs, and acknowledgement mechanisms; **do not apply Kafka's offset/partition rules to every broker**.

After this lesson, you will be able to:
- Distinguish `topic`, `partition`, `offset`, message key, consumer group, and message/trace ID.
- Understand **ordering within a single partition**, the limitations when analyzing multi-partition logs, and the impact of retries/rebalances.
- Know which events to log in the producer, consumer, processing flow, commit, and dead-letter topic (DLT).
- Write a Java 17+ example that produces logs with controlled metadata **without exposing the message payload**.
- Integrate metadata from the Kafka Producer/Consumer APIs and recognize common pitfalls with offset commits.
- Design logging fields, metrics, tracing, security, and tests suitable for production environments.

## 2. What Are Topic, Partition, and Offset?

### 2.1. A Topic Is a Logical Stream

A **Kafka topic** is the name of a stream of records, such as `orders.events`, `payments.status`, or `inventory.updated`. Producers write records to a topic; consumers subscribe to read from that topic. A topic can be divided into multiple partitions to scale storage and processing.

`Topic` does not necessarily match the business event name inside the payload. A single topic can contain multiple event types, distinguished by the application's schema, type, or headers. Therefore, a log event may contain all three:
- `topic=orders.events` — the Kafka destination name;
- `event_type=order_created` — the message type within the application;
- `event=message_processed` — the action the program is logging.

These three fields are **not synonymous**. Using distinct, clear names prevents confusing a “Kafka event” with a “log event”.

### 2.2. A Partition Is a Sub-Log of a Topic

A topic can have multiple independent partitions. Each partition maintains a sequence of records ordered by offset:

```text
Topic: orders.events

Partition 0: [offset 7] -> [offset 8] -> [offset 9] ...
Partition 1: [offset 2] -> [offset 3] -> [offset 4] ...
Partition 2: [offset 5] -> [offset 6] -> [offset 7] ...
```

The same offset `7` can exist in multiple partitions. Therefore, **logging only `offset=7` lacks context**. A Kafka record is located in the stream by the triple:

```text
(topic, partition, offset)
```

For example, `(orders.events, 0, 7)` is different from `(orders.events, 2, 7)`. When analyzing consumer logs, you also need `group_id` and `client_id` to know **who is processing** that record. The same record can be read by multiple different consumer groups, so the group is not a mandatory part of the record's address, but it is essential for diagnostics.

### 2.3. An Offset Is a Position Within a Partition

`Offset` is the position of a record within a Kafka partition, not a business ID and not a topic-wide counter. A record's offset is assigned by the broker per partition log; the producer typically learns the exact offset after receiving metadata from the callback/Future when the send completes successfully.

Do not misinterpret it:
- An offset is **not** a global ordering across partitions.
- An offset does **not** indicate that the message was successfully processed by the application.
- An offset does **not** tell you which consumer read the record, because multiple groups can read it.
- An increasing offset does not mean all records still exist or are visible: retention, compaction, and transaction visibility can cause gaps in observed positions.
- `offset_b - offset_a` is **not always equal to the number of messages the application processed**, especially if there are gaps or some records are not returned to the consumer.

For a Kafka consumer, a **committed offset** normally represents **the next position to read**, not the offset of the last processed record. If you finish processing record offset `7` and want to resume from `8` on recovery, commit the value `8` for that partition (provided earlier offsets in the processing flow have completed according to policy).

## 3. Ordering Is Scoped Only to Each Partition

Kafka preserves append order within **each partition**. This is useful when messages related to the same entity (such as an order) must be processed in order. However:
- There is **no total ordering** between partition 0 and partition 1.
- Logs from two consumers or two threads can interleave based on when they are written to the sink.
- A consumer can receive records ordered within a partition, yet the application may process them in parallel and complete them **out of order**.
- Retries, delays, DLTs, read-committed isolation, or increasing the partition count can complicate business ordering requirements.

For example, two lines appear in chronological order in the collector:

```text
INFO event=message_processed topic=orders.events partition=1 offset=2
INFO event=message_processed topic=orders.events partition=0 offset=7
```

You **cannot infer** that the record in partition 1 occurred “earlier across the whole topic” just because its log line reached the collector first. To trace a single entity, you need a consistent routing/partition key or a safe business/correlation ID.

### 3.1. Keys and Partition Selection

A producer can provide a `key`. With an appropriate partitioner, records with the same key are typically routed to the same partition, which helps preserve relative ordering **if** the partition count/partitioner, key format, and processing mechanism are maintained consistently.

Do not claim that “all records with the same key always stay in one partition”:
- Increasing the partition count can change how keys are distributed for new records.
- A custom partitioner may follow different rules.
- A null key, an explicit partition, or a different producer version/configuration can change distribution.
- A consumer application that processes concurrently does not preserve completion order without coordination.

For logging, you usually **do not need to print the raw key**. A key might be an email, user ID, account number, phone number, or sensitive string. When correlation is needed, use a server-generated correlation ID or a policy-compliant pseudonym; hashing alone does not automatically make data anonymous.

## 4. Consumer Groups, Assignment, and Rebalancing

A Kafka consumer group uses `group.id` so multiple consumers can coordinate to process the partitions of subscribed topics. Under normal operation, **each partition is assigned to at most one member at a time within the same group**, distributing the workload. Another group can independently read all partitions.

Example:

```text
Topic orders.events: P0, P1, P2

Group orders-workers:
  Consumer A -> P0, P1
  Consumer B -> P2

Group analytics-workers:
  Consumer C -> P0, P1, P2
```

When A/B scale up or down, fail, or when topic/metadata changes occur, Kafka may **rebalance** and assign partitions to different members. Consequently, the same `topic, partition, offset` can appear in logs from different `client_id`/instances after a retry or rebalance.

Distinguish these identifiers:
- `consumer_group`: an independent group that processes and commits offsets.
- `client_id`: identifies a Kafka client for diagnostics/metrics; not necessarily a permanently unique identifier.
- `instance_id` or hostname/pod ID: helps identify which process handled the work across scaling/restarts; must follow privacy policy.
- `member_id`: Kafka's membership identifier, which can change across rebalances.
- `generation`/assignment epoch: useful when investigating fencing and rebalances, though it often requires specific APIs/configuration.

**Log assignment/revocation events** concisely: group name, number of partitions assigned/revoked, and reason/endpoint when available. Do not log large objects or full Kafka configurations/credentials.

A system can reprocess a record after the consumer completes business logic but **before it commits** the offset. This is a property of at-least-once delivery, not automatically a sign that the broker created a new record. Use `(topic, partition, offset, group)` to investigate duplicate processing and verify business **idempotency**.

## 5. Designing a Message-Oriented Logging Schema

Recommended fields for a message-processing event (choose based on need; not all are mandatory):

| Field | Example | Meaning/Notes |
| --- | --- | --- |
| `event` | `message_received`, `message_processed`, `message_failed` | **Processing stage**; avoid substituting message type |
| `messaging_system` | `kafka` | Distinguishes the broker system |
| `topic` | `orders.events` | Stream name; avoid topics containing PII if possible |
| `partition` | `0` | Partition index according to the broker |
| `offset` | `7` | Record position **within this partition** |
| `consumer_group` | `orders-workers` | Processing group; important when debugging duplicates |
| `client_id`/`instance_id` | `orders-worker-2` | Specific instance; may change on restart |
| `message_type` | `order_created` | Business event type |
| `trace_id`/`correlation_id` | `trace_01` | Connects producer, consumer, and traces |
| `result` | `OK`, `RETRYABLE`, `FAILED` | Outcome of the **specific stage** |
| `attempt` | `2` | Processing attempt count **tracked by the application**, not inferred from offset |
| `error_type` | `VALIDATION_ERROR` | Stable error category, containing no secrets |
| `duration_ms` | `13` | Processing duration, using a monotonic clock |
| `next_commit_offset` | `8` | Value intended to be committed **after eligible processing completes** |

These fields help separate three states:
1. **Received**: the consumer fetched the record from poll; it has not necessarily been processed successfully yet.
2. **Processed**: business processing code has completed according to the application's contract.
3. **Committed**: the consumer has committed the next position for the group (if the commit succeeded).

Do not use the same event name `message_success` for every stage, as it is easy to misinterpret. A successful producer callback only indicates the corresponding send/ack result; **it does not guarantee that a downstream business consumer has processed it**.

### 5.1. Text and JSON Formats

Concise text:

```text
INFO event=message_processed topic=orders.events partition=0 offset=7 group=orders-workers result=OK trace_id=trace_01
```

Structured JSON (example):

```json
{
  "event": "message_processed",
  "messaging_system": "kafka",
  "topic": "orders.events",
  "partition": 0,
  "offset": 7,
  "consumer_group": "orders-workers",
  "result": "OK",
  "trace_id": "trace_01"
}
```

Use a real JSON encoder rather than manually concatenating raw headers/payloads. When logging `topic` or `trace_id` from external data, validate/escape the format properly; do not trust strings containing CR/LF, control characters, or excessive length.

## 6. Standalone Java 17+ Example: Logging Topic/Partition/Offset Without Exposing Payload

This example uses **plain JDK and JUL** to demonstrate event design; **it does not connect to a real Kafka cluster**. We simulate record metadata from two partitions; one record fails processing and requires a retry. Goal: log metadata safely, distinguish outcomes, and prove that the payload is not printed.

Create the file **`TopicPartitionLogDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class TopicPartitionLogDemo {
    record Message(String topic, int partition, long offset,
                   String traceId, String payload) {}

    enum Outcome { OK, RETRYABLE }

    static String format(Message m, Outcome outcome) {
        if (!"orders.events".equals(m.topic())
                || m.partition() < 0 || m.offset() < 0) {
            throw new IllegalArgumentException(
                    "Invalid record metadata");
        }

        String trace = m.traceId() != null
                && m.traceId().matches("[A-Za-z0-9_-]{1,32}")
                ? m.traceId() : "invalid";

        return "event=" + (outcome == Outcome.OK
                    ? "message_processed" : "message_failed")
                + " topic=" + m.topic()
                + " partition=" + m.partition()
                + " offset=" + m.offset()
                + " group=orders-worker"
                + " outcome=" + outcome
                + " trace_id=" + trace;
    }

    public static void main(String[] args) {
        Logger log = Logger.getAnonymousLogger();
        log.setUseParentHandlers(false);
        log.setLevel(Level.INFO);

        List<String> entries = new ArrayList<>();
        Handler capture = new Handler() {
            @Override
            public void publish(LogRecord r) {
                if (isLoggable(r)) {
                    entries.add(r.getMessage());
                    System.out.println(r.getLevel().getName()
                            + " " + r.getMessage());
                }
            }
            @Override public void flush() {}
            @Override public void close() {}
        };
        capture.setLevel(Level.ALL);
        log.addHandler(capture);

        try {
            log.info(format(new Message(
                    "orders.events", 0, 7, "trace_01",
                    "password=FAKE_SECRET"), Outcome.OK));
            log.info(format(new Message(
                    "orders.events", 1, 2, "trace_02",
                    "token=FAKE_SECRET"), Outcome.OK));
            log.warning(format(new Message(
                    "orders.events", 0, 8, "trace_03",
                    "email=private@example.invalid"),
                    Outcome.RETRYABLE));

            if (entries.size() != 3
                    || entries.stream().anyMatch(x ->
                        x.contains("FAKE_SECRET")
                        || x.contains("private@")
                        || x.contains("password")
                        || x.contains("token="))) {
                throw new AssertionError("Unsafe event");
            }

            System.out.println("captured=" + entries.size());
            System.out.println("payload_leaked=false");
        } finally {
            log.removeHandler(capture);
            capture.close();
        }
    }
}
```

Compile and run with JDK 17+:

```bash
javac TopicPartitionLogDemo.java
java TopicPartitionLogDemo
```

**Deterministic standard output:**

```text
INFO event=message_processed topic=orders.events partition=0 offset=7 group=orders-worker outcome=OK trace_id=trace_01
INFO event=message_processed topic=orders.events partition=1 offset=2 group=orders-worker outcome=OK trace_id=trace_02
WARNING event=message_failed topic=orders.events partition=0 offset=8 group=orders-worker outcome=RETRYABLE trace_id=trace_03
captured=3
payload_leaked=false
```

Explanation:
- The two partitions have **distinct, independent** offsets; the log line with `partition=1 offset=2` appearing between two partition 0 events does not establish a global order.
- `format` allows only an approved topic, checks that partition/offset are non-negative, and accepts trace IDs only within a restricted character set and length.
- `payload` contains fake sensitive strings, yet **is never included in the log message**; the check at the end of the program confirms no leak.
- `Outcome.RETRYABLE` produces `event=message_failed` at WARNING level; this demonstration **does not yet implement retries, DLT, or offset commits**.
- The JUL logger and local handler are for testing; `finally` removes the handler without altering the JVM-wide root logger.

Note: `payload` and `traceId` here are defined for demonstration; in production, log event fields as structured logging with a schema/encoder instead of manual string concatenation. Do not treat a regex allowing a trace ID as proof of “no PII”; IDs should be generated with privacy-by-design and source verification.

## 7. Kafka Producer: Logging Accurate Topic/Partition/Offset After Send

With the Kafka Java client, a `ProducerRecord<K,V>` contains a topic, key, value, and optionally an explicit partition. Metadata after a successful send is returned via a callback/Future as `RecordMetadata`, which includes `topic()`, `partition()`, and `offset()`.

One way to integrate with **SLF4J + Kafka Client** (this is an abridged snippet, not a standalone runnable file; `producer`, `orderId`, `serializedEvent`, and `LOG` are already initialized):

```java
import org.apache.kafka.clients.producer.ProducerRecord;

// Integration snippet inside an event-sending method; Kafka Producer and LOG already exist.
ProducerRecord<String, String> record =
        new ProducerRecord<>(
                "orders.events", orderId, serializedEvent);

try {
    producer.send(record, (metadata, error) -> {
        if (error != null) {
            LOG.error(
                "event=message_send_failed topic={} error_type={}",
                record.topic(),
                error.getClass().getSimpleName());
            return;
        }

        LOG.info(
            "event=message_send_succeeded topic={} "
            + "partition={} offset={}",
            metadata.topic(),
            metadata.partition(),
            metadata.offset());
    });
} catch (RuntimeException error) {
    LOG.error("event=message_send_rejected topic={} error_type={}",
            record.topic(), error.getClass().getSimpleName());
    throw error;
}
```

Key takeaways:
1. Before `send`, the producer knows the topic and possibly the key; if no partition is specified, **do not guess** the partition/offset from the key. Partition selection can depend on the partitioner, metadata, or client configuration.
2. `send(...)` is asynchronous; the callback with `error == null` provides the corresponding broker/producer result. You can log `send_requested` at invocation time, but **do not call it “successfully stored”**.
3. If `send` fails synchronously or the callback receives an error, log the failure event with topic and error type; avoid printing the payload or credentials.
4. `acks`/idempotence/retries determine producer guarantees; a successful callback does not mean a downstream consumer has processed the record.
5. `RecordMetadata.offset()` is the offset in the partition of the sent record, not the offset committed by a consumer.

**Privacy:** `serializedEvent` may contain PII, and `orderId` used as the key could be a personal identifier. **Do not log raw keys/values** in the callback just for debugging; use metadata and approved correlation IDs.

A single business request may send multiple records to different topics. Connect them via `trace_id`/`correlation_id` or an application event ID; **do not use offset as a system-wide transaction ID**.

## 8. Kafka Consumer: Distinguishing Receive, Process, and Commit

Kafka `ConsumerRecord<K,V>` provides:
- `topic()`: the topic from which the record was received.
- `partition()`: the partition.
- `offset()`: the record's position within the partition.
- `key()` and `value()`: the payload/key, which may be sensitive.
- `headers()`: additional metadata, which may contain trace context or producer-supplied data and should not be dumped in full.
- `timestamp()`: the timestamp attached to the record according to its timestamp type; not synonymous with when the consumer processed it.

Example **integration snippet** using the Kafka client, SLF4J, and a hypothetical business handler:

```java
import java.time.Duration;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;

// consumer, LOG, and processMessage are already defined in the application.
ConsumerRecords<String, byte[]> records =
        consumer.poll(Duration.ofMillis(500));

for (ConsumerRecord<String, byte[]> record : records) {
    LOG.debug(
        "event=message_received topic={} partition={} offset={}",
        record.topic(), record.partition(), record.offset());

    long started = System.nanoTime();
    try {
        processMessage(record.value()); // Actual business logic.
        long durationMs =
            java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - started);

        LOG.info(
            "event=message_processed topic={} partition={} "
            + "offset={} duration_ms={}",
            record.topic(), record.partition(),
            record.offset(), durationMs);

        // Only mark the offset as complete when business logic succeeds.
        // The commit strategy is outside this abridged snippet.
    } catch (Exception error) {
        LOG.warn(
            "event=message_failed topic={} partition={} "
            + "offset={} error_type={}",
            record.topic(), record.partition(), record.offset(),
            error.getClass().getSimpleName());

        // Apply an appropriate retry/pause/seek/DLT policy.
        // Do not commit past a failed record.
        throw error;
    }
}
```

This is **not a complete consumer loop**: it omits client initialization, group subscription, commit strategy, lifecycle management, rebalancing, and full error handling. The key lessons are:
- `poll()` returning a record does not prove the business handler succeeded.
- `message_processed` should be logged **only after** the handler completes according to its contract.
- If processing fails, log `message_failed` with topic/partition/offset so the failing record can be located.
- If the handler runs side effects asynchronously, **you cannot claim it is processed** merely because a task was submitted to an executor.
- When catching and retrying, distinguish retryable from non-retryable errors by policy; do not treat every error as retryable.

### 8.1. Manual Commit: “Next Offset” and Safety Conditions

If the consumer **commits offsets manually** (`enable.auto.commit=false`), after safely processing record `offset=7` on `partition=0`, the value committed to resume from the next record is typically `8`.

With the Kafka Java client, an **illustrative snippet** for a single partition processed contiguously up to offset `7`:

```java
import java.util.Map;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;

// Valid only when all records before the next position
// have completed per the processing contract and the consumer owns the assignment.
TopicPartition tp = new TopicPartition("orders.events", 0);
consumer.commitSync(Map.of(tp, new OffsetAndMetadata(8L)));
```

**Do not** hardcode `8L` in a real application. Typically, you compute `record.offset() + 1` from the last safely processed offset **per TopicPartition**, and do not commit the highest read position when an earlier record has not been processed.

Incorrect example: a batch contains offsets 7, 8, and 9 on partition 0; record 8 fails, record 9 succeeds; committing 10 can cause the consumer group to skip offset 8 upon restart. You must maintain a *contiguous processed frontier* per partition, or stop/pause/seek/retry using an appropriate strategy. With concurrency or rebalances, offset tracking must also account for in-flight records and partition revocation.

**Auto commit** can periodically commit polled positions without waiting for application side effects to finish, depending on how processing is structured; do not equate “committed” with “downstream fully processed”. Designing at-least-once, exactly-once, or transactional processing requires evaluating the entire data path, not inferring correctness from commit logs alone.

### 8.2. When to Log Commits

You can distinguish:
- `commit_attempted`: the code begins sending the commit.
- `commit_succeeded`: the Kafka client confirms the commit succeeded for the group.
- `commit_failed`: the commit failed; inspect assignment/rebalance state.

A log line `commit_succeeded topic=... partition=... next_offset=8` indicates that the group's position was saved; it is **not** an event proving that business side effects in a database are durable, unless the application has built an appropriate contract and commit ordering.

## 9. Rebalancing and “The Same Record Processed Twice”

Rebalancing occurs when membership or assignment changes. The Kafka Java client provides `ConsumerRebalanceListener` with callbacks so the application can react when partitions are revoked or assigned.

Example **integration snippet** (Kafka Java client + SLF4J, not a complete program):

```java
consumer.subscribe(
    java.util.List.of("orders.events"),
    new org.apache.kafka.clients.consumer.ConsumerRebalanceListener() {
        @Override
        public void onPartitionsRevoked(
                java.util.Collection<
                    org.apache.kafka.common.TopicPartition> partitions) {
            LOG.info(
                "event=partitions_revoked group={} count={}",
                "orders-workers", partitions.size());

            // Stop/wait for work on the revoked partitions,
            // commit the completed frontier if still valid,
            // and release related state according to design.
        }

        @Override
        public void onPartitionsAssigned(
                java.util.Collection<
                    org.apache.kafka.common.TopicPartition> partitions) {
            LOG.info(
                "event=partitions_assigned group={} count={}",
                "orders-workers", partitions.size());
        }
    });
```

Callbacks have different contracts depending on the protocol/assignor; in cooperative rebalancing, only a **subset** of partitions may be revoked. Do not write logic assuming every rebalance revokes all partitions. If you need to log each assigned partition, create a structured field with bounded count/length or an event per assignment, avoiding printing huge configuration objects.

The same triple `(topic, partition, offset)` can appear in the logs of two consumer instances at different times because:
- Consumer A processed it but crashed before committing; Consumer B re-read it after a rebalance.
- A commit failed, or the consumer reset/seeked its position.
- The application retried a record at the same offset without advancing position.
- Another consumer group independently read the same record.

Do not attribute every such case to a **duplicate broker record**. Distinguish **the same Kafka record being reprocessed** from **a producer sending two distinct records** (different offsets, possibly sharing a business event ID).

## 10. Retries and Dead-Letter Topics: How to Correlate Them

A failed message can be:
- Retried at the same partition/offset before advancing.
- Handled by pausing the partition (`pause`), retrying with backoff, and resuming.
- Routed to a retry topic or dead-letter topic (DLT) according to framework/policy.
- Discarded or marked as a business failure when an approved audit mechanism is in place.

When routed to **another topic**, the new record gets a **new topic/partition/offset**. Therefore, you cannot link the original record and the DLT record by offset alone.

Example events:

```text
WARN event=message_failed topic=orders.events partition=0 offset=8 error_type=VALIDATION_ERROR trace_id=trace_03
INFO event=message_routed_to_dlt source_topic=orders.events source_partition=0 source_offset=8 dlt_topic=orders.events.dlt trace_id=trace_03
INFO event=message_received topic=orders.events.dlt partition=1 offset=52 trace_id=trace_03
```

This is sample data, not a live Kafka run. Note that **the DLT send must succeed before logging “routed”**; if it has not yet been acknowledged by the broker, the event should be `dlt_send_requested` or `dlt_send_failed`. For high-reliability systems, consider atomicity across processing/commit/DLT send or an appropriate transactional/outbox pattern.

An attempt count should live in **application-managed state** or explicit framework metadata; a Kafka offset is **not** a retry count. Some newer APIs expose delivery-count-related metadata in specific contexts, but do not assume every record has a counter and never infer retry counts from offset gaps.

## 11. Metrics, Consumer Lag, and Cardinality

Access logs on every message are helpful for investigation, but high-partition systems can also generate a huge volume of events. Do not turn **offset** into a metric/histogram label: it is a continuously changing value that causes cardinality explosion.

Separate them as follows:

| Information | Should it be a log field? | Should it be a metric label? |
| --- | --- | --- |
| `topic` | Yes, if needed | Yes, when the topic set is bounded |
| `partition` | Yes, for investigation | Possibly, if partition count is reasonable; watch cardinality |
| `offset` | Yes, for tracing a record | **No**, usually far too many values |
| `consumer_group` | Yes | Yes, if the group set is finite |
| `trace_id`, `message_id` | Yes, per policy | **No** as a general label |
| `error_type` | Yes | Yes, when it is a finite enum |
| `duration_ms` | Yes, on processing events | As an observation/histogram; do not use raw duration as a label |

### Consumer Lag

A commonly used concept per partition for a group:

```text
consumer_lag ~= log_end_offset - committed_next_offset
```

For example, if the log end offset is 110 and the group has committed next offset 108, the lag is roughly 2 positions. Distinguish `logEndOffset` from high watermark / last stable offset depending on isolation level and measurement tooling; in some retention or transactional scenarios, the offset difference does not equal the exact number of visible records or pending business events.

Increasing lag can stem from:
- The producer generating records faster than the consumer processes them.
- A hot partition due to skewed key distribution.
- The consumer stalling on retry/backoff or I/O waits.
- Frequent rebalances or a blocked poll loop.
- Delayed commits, making lag based on committed offset appear large even though application processing has progressed further.

**Near-zero lag does not prove business processing is completely succeeding** if the code auto-commits before side effects finish. Combine metrics for processed/error counts, commit success, retries, DLT, processing latency, and queue/backpressure.

### Reducing Log Volume

In production, you often do not need INFO logs for every successful message at very high throughput. You can:
- Log aggregates/metrics for successes, while keeping contextual WARN/ERROR logs per policy.
- Sample success logs at a controlled rate/interval, while retaining necessary failures/audits.
- Attach MDC within the processing scope so important business logs still carry topic/partition/offset.
- Bound sampling/dropping and track dropped event counts. Do not let sampling distort absolute error counts.

## 12. Tracing and MDC: Attaching Context at the Right Time

In Java, SLF4J MDC or Log4j ThreadContext lets all application logs within a message-processing block carry:
`topic`, `partition`, `offset`, `consumer_group`, `trace_id`.

Example **SLF4J MDC** integration:

```java
// Within the processing scope of an actual ConsumerRecord.
java.util.Map<String, String> old =
        org.slf4j.MDC.getCopyOfContextMap();

try {
    org.slf4j.MDC.put("kafka.topic", record.topic());
    org.slf4j.MDC.put("kafka.partition",
                      Integer.toString(record.partition()));
    org.slf4j.MDC.put("kafka.offset",
                      Long.toString(record.offset()));

    processMessage(record.value());
} finally {
    if (old == null) {
        org.slf4j.MDC.clear();
    } else {
        org.slf4j.MDC.setContextMap(old);
    }
}
```

This snippet requires an SLF4J provider and `record`/`processMessage` to be defined; copying and restoring the context prevents polluting the MDC of the next message on a reused thread. Do not put raw keys/payloads, Authorization headers, full header maps, or personal data into MDC.

If messages are processed on another thread, worker pool, or virtual thread, **MDC is not automatically propagated in all cases**; you need a context-propagation mechanism supported by your framework/libraries. With the Kafka client, `ConsumerRecord`/KafkaConsumer must not be shared carelessly across threads; take an immutable metadata snapshot when dispatching a task.

**OpenTelemetry** defines semantic conventions for messaging. Fields such as `messaging.destination.name`, `messaging.destination.partition.id`, `messaging.consumer.group.name`, and `kafka.offset` can be attached to spans depending on the conventions version; not all of them are automatically log fields. Map your internal log schema to trace attributes in a controlled way, and note that some conventions are still in Development status and may change names/semantics across versions.

### Trace Context via Message Headers

Trace context is commonly injected into headers by the producer and extracted by the consumer. However, headers are external input that may come from untrusted sources; do not copy all of them into logs. Accept only the required headers, validate format/size, and use standard OpenTelemetry propagators; a trace ID is **not** an authorization token.

In environments with multiple async hops or DLT/retry topics, connect spans using appropriate contexts/links. Do not infer from a trace ID that a consumer committed successfully; that is a separate event/metric.

## 13. Logging Security for Topics and Partitions

Metadata may look harmless, yet still requires review:
- **Topic name** can reveal business domains, tenants, or environments. If topics are dynamically created from emails/tenant IDs, topic names may contain PII.
- **Key** is very often a user ID, email, or account number; do not log the raw key.
- **Value/payload** can contain tokens, orders, payment details, or personal records; do not dump it in full even on error.
- **Headers** can contain trace context, routing info, and secrets. Log only a specific allowlist.
- **Consumer group/client ID** can contain hostnames or tenants; check sensitivity and value cardinality.
- **Exception message/stack trace** can expose record contents or configuration; review how exceptions are constructed and formatted.

When you need a correlation identifier beyond offset, generate `message_id`/`correlation_id` at the source with privacy by design. Hashing a raw key does not automatically make it anonymous, especially when the key space is small and easy to guess; use managed pseudonymization if needed.

### Log Injection

A topic, header, error message, key, or client-influenced metadata field can contain control characters, newlines, or long text. If you build plain-text logs by concatenating them, an attacker can forge fake log lines.

Defenses:
1. Log only approved fields, preferring system-controlled topic/config names.
2. Validate length, character set, and type of trace/message IDs.
3. Use a structured JSON encoder with proper escaping; never assemble JSON manually from raw input.
4. Limit the number of headers/fields and event size.
5. Test CR/LF, Unicode, quotes, long payloads, and fake secrets at the collector, not only at the call site.

The Java example in Section 6 accepts only the topic `orders.events` and trace IDs matching a restricted character set and length; the payload is never passed to `format`. This is an **illustrative allowlist pattern**, not a filter for every kind of sensitive data.

## 14. Testing Topic/Partition Logging

### 14.1. Schema Unit Tests

For your custom event-building function:
- Input `topic=orders.events, partition=0, offset=7` produces the exact three fields and types.
- The same offset `7` on partition 0 and partition 1 must be treated as **two distinct records**.
- Negative partitions, negative offsets, and disallowed topics are rejected or safely mapped according to the contract.
- A trace ID containing CR/LF or excessive length is rejected or normalized.
- A payload containing fake tokens/emails does not appear in the event.
- Failure messages use a distinct event name and level, with no message claiming processing completed.

### 14.2. Real Kafka Integration Tests

Use a test broker/Testcontainers or a dedicated test cluster with real producers and consumers:
1. Send records to a topic with at least two partitions, specifying keys/partitions per test setup.
2. Read `RecordMetadata.topic/partition/offset` from the producer callback and verify real Kafka returns the metadata.
3. Have the consumer read `ConsumerRecord.topic/partition/offset`, and check that `message_received` and `message_processed` events match.
4. Inject a controlled processing failure and verify the consumer does not commit past the incomplete offset.
5. Test restarts and rebalances: another instance re-reads the record if uncommitted; verify idempotency.
6. Route to a DLT/retry topic and verify the **new** metadata and correlation back to the source via correlation ID.
7. Intentionally set a trace ID containing newlines/fake secrets; verify it is not printed in logs, MDC, or the collector.
8. Measure lag and verify the meaning of committed *next offset*.
9. Exercise async logging queue/drop/backpressure behavior; distinguish logging errors from Kafka errors.
10. Stop/start the process/collector and verify flushing and behavior while logs are still in RAM.

Never use a production broker or real customer data to test these scenarios.

### 14.3. Reading Logs During an Incident

Scenario: a customer reports that an order event was processed twice.
- Search by a safe application event ID / correlation ID.
- Group logs by `topic + partition + offset + consumer_group`.
- If the **same triple** appears twice in the same group, inspect retries, consumer restarts, commit failures, rebalances, and idempotency.
- If **different offsets** share the same business ID, inspect producer send retries/duplicate events, outbox/transactions, and business logic emitting the message multiple times.
- Compare `message_received`, `message_processed`, and `commit_succeeded` rather than relying on a single log line.
- If a record landed in a DLT, trace back to source metadata and send/commit status; do not assume a DLT record means business processing succeeded.

## 15. Common Pitfalls

| Symptom / Mistake | Why It Is Wrong | How to Fix It |
| --- | --- | --- |
| Logging only `offset=7` | Offsets repeat across topics/partitions | Log the full `topic, partition, offset` |
| Sorting offsets across partitions for global order | There is no global offset | Compare ordering **within each partition** |
| Calling `send()` and logging “published” immediately | Kafka `send()` is usually async | Log requested; log success in callback/Future |
| Logging `message_received` as processed | Polling has not completed business logic | Emit a separate processed event after success |
| Committing the highest offset in a batch despite errors | Can skip unprocessed records | Commit the contiguous completed frontier per partition |
| Treating a commit as DB transaction success | Kafka commit does not guarantee external side effects | Design ordering, idempotency/transactions |
| Assuming duplicate logs mean duplicate Kafka records | Retries/rebalances/other groups can re-read | Group by triple + group/instance |
| Assuming the same key always stays on the same partition | Partitioner/partition count/topic can change | Constrain routing and test when scaling |
| Logging raw payload/key/headers for debugging | Risk of PII, secrets, and log injection | Log metadata + allowlisted event IDs |
| Using offset as a metric label | Unbounded cardinality growth | Keep offset in logs, not as a general label |
| Using lag=0 to conclude business logic is OK | Auto-commit can run before processing finishes | Combine processing, retries, and DLT metrics |
| Not cleaning up MDC after a record | Context leaks across requests/messages | Restore/clear in `finally` |
| Logging too many success events | Increases cost and backlog | Use appropriate aggregation/metrics/sampling |
| Not logging rebalances | Hard to investigate partition ownership changes | Log assigned/revoked and lifecycle events |
| Copying the old offset to DLT as the new offset | DLT has a new topic/partition/offset | Log source location and DLT metadata separately |

## 16. Production Implementation Checklist

- [ ] Every key consumer event includes `topic, partition, offset`; includes `group_id` when needed to debug reprocessing.
- [ ] Distinguish `send_requested`, `send_succeeded`, `received`, `processed`, `failed`, and `commit_succeeded`.
- [ ] Log producer metadata **after ACK/callback succeeds**, without guessing partition/offset beforehand.
- [ ] Commit the “next offset” accurately **after** prior records complete; do not skip failed gaps.
- [ ] Have an idempotency/retry/DLT policy and events that correlate source with destination.
- [ ] Log assignment/revocation/rebalance with clear scope; do not treat instance ID as a record identifier.
- [ ] Do not log raw payloads/keys/headers or exceptions containing secrets; use approved correlation IDs.
- [ ] Validate trace/message IDs, encode structured output, and test log injection.
- [ ] Do not use offset/trace ID as metric labels; monitor processing lag and Kafka lag separately.
- [ ] Have tests with real producers/consumers, multi-partition setups, restarts/rebalances, and recovery.
- [ ] Evaluate logging throughput, async queues, retry storms, and storage/retention/collectors.
- [ ] Correlate access/application logs with trace context when possible, while keeping information sources independent.

## 17. Exercises

1. Run `TopicPartitionLogDemo`. Explain why `partition=1 offset=2` cannot be ordered before or after `partition=0 offset=7` in a global order.
2. Add a `message_received` event for record offset 8 and then simulate a processing failure; verify that `message_processed` is not emitted on failure.
3. Pass an invalid topic, a negative offset, or a trace ID containing `\n`; observe the validation contract of `format`.
4. Simulate a duplicate record `(orders.events,0,7)` being reprocessed within the same consumer group; design a log with `attempt` and explain why idempotency is required.
5. With a real Kafka Producer, log `send_requested` before `send` and `send_succeeded` in the callback. On send failure, omit message contents from the log.
6. In a consumer test, process offsets 7 OK, 8 failed, 9 OK. Explain why you must not commit 10 and how to maintain a contiguous frontier.
7. Create a retry/DLT topic in a test environment, inspect the new offset, and verify how to link it back to the source location.
8. Build a dashboard by topic/group/error type; keep offset in logs without using it as a metric label.
9. Trigger a consumer group rebalance, log assigned/revoked events, and demonstrate how the same record can be re-read without a producer sending a new record.
10. Check MDC after two records are processed on the same thread: does context from the first record leak into the second?

## 18. Key Takeaways

- **Topic** is the logical stream; **partition** is the sub-log; **offset** is a position meaningful only within a partition. The triple `(topic, partition, offset)` is the reference anchor for a Kafka record.
- Kafka preserves ordering within **each partition**, with no global order across all partitions; concurrent application processing can also complete out of order.
- **Producer ACK, consumer poll, business processing, and offset commit** are four distinct milestones; log them with distinct event names.
- The same record being re-read or reprocessed after a retry/rebalance does not necessarily mean the broker has a duplicate record; compare the triple, group, and business ID.
- The committed offset is normally the **next offset**; do not commit past a failed processing step.
- Log metadata safely, do not dump keys/values/headers, and do not use offset as a high-cardinality metric label.
- Maintain observability into per-partition lag, rebalances, retries, DLT, and trace paths without exposing payloads.

### References

- Apache Kafka — *Design* (topic/partition, offsets, replication): https://kafka.apache.org/documentation/#design
- Apache Kafka Java Client — `ConsumerRecord`: https://kafka.apache.org/41/javadoc/org/apache/kafka/clients/consumer/ConsumerRecord.html
- Apache Kafka Java Client — `KafkaConsumer`: https://kafka.apache.org/41/javadoc/org/apache/kafka/clients/consumer/KafkaConsumer.html
- Apache Kafka Java Client — `RecordMetadata`: https://kafka.apache.org/41/javadoc/org/apache/kafka/clients/producer/RecordMetadata.html
- Apache Kafka Java Client — `ConsumerRebalanceListener`: https://kafka.apache.org/41/javadoc/org/apache/kafka/clients/consumer/ConsumerRebalanceListener.html
- Apache Kafka Java Client — `OffsetAndMetadata`: https://kafka.apache.org/41/javadoc/org/apache/kafka/clients/consumer/OffsetAndMetadata.html
- OpenTelemetry — *Messaging semantic conventions, Kafka*: https://opentelemetry.io/docs/specs/semconv/messaging/kafka/
- OWASP — *Logging Cheat Sheet*: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
