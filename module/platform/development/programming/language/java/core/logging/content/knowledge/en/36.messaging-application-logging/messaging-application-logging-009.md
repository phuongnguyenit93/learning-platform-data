# Duplicate Message Logs in Java Messaging Applications

## 1. The Problem: Why Does a Message Appear Multiple Times in Logs?

In asynchronous systems, a message may be redelivered to a consumer after a processing error, timeout, restart, or when the acknowledgement/commit step has not completed. Therefore, lines like the following do not necessarily indicate a bug:

```text
INFO event=message_received eventId=evt-100 attempt=1
INFO event=message_received eventId=evt-100 attempt=2
```

This may be **two deliveries of the same logical event**. However, there are also cases where **a single delivery** causes a logger, appender, or collector to emit **two identical lines**. These two phenomena must be distinguished before attempting to "remove duplicate logs."

In this article, **duplicate message logging** refers to analyzing and handling repeated log records in applications that use message queues, message brokers, or event-driven architectures. The focus is on:
- Distinguishing **message redelivery**, **duplicate business event**, **duplicate log emission**, and **duplicate downstream ingestion**.
- Accurately recording **message ID, delivery attempt, consumer, outcome, and correlation ID**.
- Avoiding logging **a successful business processing** for every delivery when a message is redelivered.
- Designing **idempotent consumers** and ack/commit policies to prevent repeated business side effects.
- Investigating duplicate logs from Logback/Log4j 2, logger additivity, multiple handlers/appenders, and collectors.
- Reducing noise, cost, and sensitive data in logs while preserving an audit trail of processing.

> **Key takeaway:** Having two identical lines in a log does not by itself prove that business logic executed twice. Conversely, having only one log line does not prove that duplicate side effects were avoided. You must correlate the **logical event**, **delivery attempt**, **processing outcome**, and **log output destination**.

## 2. Four Types of "Duplicates" That Are Easily Confused

| Duplicate Type | Symptoms | Common Causes | What to Check |
| --- | --- | --- | --- |
| **Message redelivery** | Same `eventId` received again, different attempt | Missing ack/commit, timeout, restart, requeue | Broker metadata, delivery attempt, ack timing |
| **Duplicate logical message** | Producer emits multiple messages representing the same action | Send retries, outbox replay, publisher bug, client double-send | Business key/event ID, producer idempotency |
| **Duplicate log emission** | One logger call emits two lines through the same pipeline | Additivity, multiple handlers/appenders attached, double instrumentation | Logger tree, appender refs, handler count |
| **Duplicate log ingestion** | One log event stored multiple times by collector/index | Forwarder resend, retry after lost ACK, multiple agents tailing the same file | Agent pipeline, document/event ID at sink |

A message broker may provide product-specific ordering or delivery guarantees, but you should never assume that **every consumer processes messages exactly once**. In an *at-least-once* model, redelivery is a normal occurrence that must be handled.

**Example:** A consumer finishes saving an invoice to the database but crashes before committing the offset. Upon restart, the broker may redeliver that message. Two `message_received` log lines are expected; the more critical question is **whether the invoice was created twice**.

Conversely, if a request produces only one delivery and `logger.info(...)` is called once, yet both the root logger and a child logger reference the console appender, the output can be duplicated. Fixing idempotency in the consumer will not resolve this type of issue.

## 3. Receive, Process, Ack, and Redelivery Flow

A common processing flow:

```text
Producer -> Broker -> Consumer
                         |
                         v
                   Receive message
                         |
                         v
                  Identify event ID
                         |
                +--------+--------+
                |                 |
           Unprocessed        Processed
                |                 |
                v                 v
       Apply business effect   Skip effect
                |                 |
                v                 v
        Commit durable state   Record duplicate
                |                 |
                +--------+--------+
                         |
                         v
                  Ack / commit
                         |
                    Broker state
```

**Duplicate window:** The consumer succeeds in processing the business logic, but **ack/commit fails or has not occurred yet**. The broker does not know the consumer has processed the message and may redeliver it. Thus, a single event can have **multiple valid deliveries**.

**Lost-processing window:** The consumer acks/commits **before** durable processing completes, and then crashes. The broker may consider the message done while the business work is incomplete. You should never move ack to the beginning just to make redelivery logs disappear.

The typical design order aims for:
1. Validate the message and idempotency key.
2. Apply business changes and record the processed marker **within the same feasible transaction boundary**.
3. Commit the transaction durably.
4. Ack/commit the message after the transaction completes.
5. If step 4 fails, accept the redelivery and **skip the side effect via the idempotency mechanism**.

There is no single ack rule for every broker and every processing pattern. Kafka uses offset commits/transactions differently from RabbitMQ acknowledgements or SQS message deletion. However, **never treat reducing log lines as a goal that overrides business correctness**.

### 3.1. Kafka

With a Kafka consumer, logging `message_received` every time `poll` returns a record can produce repeated logs if the record is reprocessed after a rebalance/restart or if the corresponding offset was not committed. Useful fields include:
- `topic`, `partition`, `offset`: the record's position in a specific topic/partition.
- `consumer_group`, `consumer_instance`: consumer context.
- `event_id` or idempotency key: identifier of the **logical event** in the payload/envelope if stably assigned by the producer.

**Do not use only the offset as a business event ID** when the event can be republished to another topic: an offset only identifies a position within a topic partition. Kafka producer idempotence and Kafka transactions can provide guarantees in properly configured Kafka-to-Kafka flows; they **do not automatically guarantee that side effects in external databases or HTTP APIs occur only once**.

### 3.2. RabbitMQ

With RabbitMQ, a message can be redelivered when the channel/connection closes before acknowledgement or when the consumer `nack`s with requeue. Metadata such as the `redelivered` flag is a signal that the message was redelivered, but it is **not an accurate attempt counter** and should not be the sole evidence for a business decision.

`deliveryTag` is scoped to a channel, **not an immutable event ID across deliveries**. You can use an application message ID and a business idempotency key attached by the producer; ack/nack must follow the contract of the channel/client in use.

### 3.3. Amazon SQS or Queues with Visibility Timeout

In visibility-timeout queues, a message can be received by another consumer if the visibility timeout expires before the message is deleted. `receiptHandle` is typically tied to **a single receipt**, so it must not be used as a logical ID for deduplication. If a receive-count field is provided, treat it as **broker metadata** with its own semantics, not an infallible business counter.

With FIFO queues or broker-side deduplication mechanisms, you still need to understand the **time window and boundaries** of broker deduplication and external side effects. Do not treat broker-side deduplication as a substitute for consumer-side idempotency when operations must remain accurate across failures/crashes.

## 4. A Log Event Can Describe Different Stages

Do not log every situation under a generic `Processed message X` message. Use an event type that accurately reflects what happened.

| Log Event | Exact Meaning | When to Emit |
| --- | --- | --- |
| `MESSAGE_RECEIVED` | Consumer received/was delivered a message | When the message arrives at the handler |
| `MESSAGE_VALIDATION_FAILED` | Message violates schema/contract | After validation check |
| `MESSAGE_PROCESSING_STARTED` | Processing started, **does not mean success yet** | Before the business operation |
| `MESSAGE_APPLIED` | Business effect has been committed/recorded per contract | After confirming the processing boundary |
| `MESSAGE_DUPLICATE` | Evidence shows the event was already processed; side effect skipped | When the idempotency store returns duplicate |
| `MESSAGE_PROCESSING_FAILED` | Handler failed | After an error, with a safe error code |
| `MESSAGE_RETRY_SCHEDULED` | Retry/requeue has been requested | When scheduled per application mechanism |
| `MESSAGE_ACK_REQUESTED` | Consumer called the ack/commit API | On call; **does not mean the broker confirmed** |
| `MESSAGE_ACK_CONFIRMED` | Ack/commit confirmed as supported by the API | Only when the client API provides real confirmation |
| `MESSAGE_DEAD_LETTERED` | Message sent to / confirmed in DLQ per contract | Once an appropriate outcome is obtained |

**Event names must match the timing of emission.** For example, `MESSAGE_APPLIED` should not be logged before the database commit succeeds. However, even a post-commit log can be lost if the process crashes between the commit and writing the log. If an **audit event must exist** alongside the business change, store it in the database/outbox within the transaction rather than relying solely on a logger.

When receiving a repeated message, logging `MESSAGE_RECEIVED` multiple times may be **desirable** for investigation. Distinguish it from `MESSAGE_APPLIED`, which represents the business effect expected not to repeat.

## 5. Log Schema for Message Delivery

A structured event can include the following fields:

```json
{
  "event": "message_received",
  "event_id": "evt-100",
  "message_id": "msg-900",
  "consumer": "invoice-projector",
  "destination": "billing.events",
  "delivery_attempt": 2,
  "redelivered": true,
  "trace_id": "trace-demo-42",
  "processing_result": "RECEIVED",
  "timestamp": "2026-11-10T03:00:00Z"
}
```

This is only **illustrative data**, not a real observed event. In production, clearly define:
- `event_id`: durable identifier of the **logical event** from the producer/envelope. This event may be delivered multiple times.
- `message_id`: application/broker-level message ID, which may change if the message is republished; do not assume it equals the event ID.
- `consumer`: name of the handler/subscription/job consuming the event. One event may be **validly processed by multiple different consumers**.
- `destination`: topic, queue, or subscription; use a stable name.
- `delivery_attempt`: sourced from the broker if it has appropriate semantics, or managed by the consumer. **Do not fabricate an attempt count** if no reliable source exists.
- `redelivered`: signal from the broker when supported; does not mean the event has already been processed by business logic.
- `trace_id`/`correlation_id`: for linking with requests/producers/tracing; format and trustworthiness must be controlled.
- `processing_result`: `RECEIVED`/`APPLIED`/`DUPLICATE_SKIPPED`/`FAILED`; use an enum rather than free-form strings.
- `timestamp`: exact time of the stage that emitted the log, typically normalized to UTC.
- `broker_position`: technology-specific, such as Kafka topic/partition/offset; do not use it as a cross-system event ID.

**Do not log raw payloads** by default. Message bodies may contain emails, passwords, access tokens, payment data, private documents, or binary data. Do not log `Authorization`, secret headers, or full message objects just to find duplicates. In many cases, **event ID and metadata are sufficient**.

### 5.1. Three Types of IDs That Must Not Be Interchanged

```text
Business operation:   paymentId=pay-42
Logical event:        eventId=evt-100
Broker delivery #1:   attempt=1
Broker delivery #2:   attempt=2
Log statement/event:  log emitted at each stage
```

- **Business key** (`paymentId`) identifies the business entity/operation; one payment can have **multiple distinct events** (created, authorized, captured). Do not treat all events for the same payment as duplicates.
- **Event ID** identifies a single logical event occurrence and should remain stable when the producer retries the same event.
- **Delivery identity/attempt** identifies a single delivery; it changes on redelivery, with broker-dependent semantics.
- **Log event identity**, if provided by the logging system, serves deduplication at the collector; do not equate it with the business event.

Sometimes two messages have **different event IDs but represent a duplicate send of the same business operation**. In that case, deduplicating solely by event ID is insufficient; the business logic needs an appropriate **idempotency key or uniqueness constraint**, such as `payment_id + operation_type`. Conversely, two different events sharing a resource ID **are not automatically duplicates**.

## 6. Standalone Java 17 Example: Log Every Delivery, Apply the Business Effect Only Once

This example uses **JUL** (`java.util.logging`) built into JDK 17. It simulates three deliveries:
1. `evt-100` is received for the first time and the business effect is applied.
2. `evt-100` is received again; a duplicate is logged and the business effect is **skipped**.
3. `evt-101` is a different event and its business effect is applied.

The `Set` and `Map` in this program live in **single-threaded in-memory state** solely to illustrate the difference between logging deliveries and logging business effects. Do not use this pattern to prove production idempotency across restarts, multiple consumers, concurrency, or failures between processing and marking.

Create `DuplicateMessageLogDemo.java`:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class DuplicateMessageLogDemo {
    private record Message(String eventId, String payload) {}

    private static final class DemoConsumer {
        private final Logger logger;
        private final Set<String> applied = new HashSet<>();
        private final Map<String, Integer> deliveryCounts = new HashMap<>();

        DemoConsumer(Logger logger) {
            this.logger = logger;
        }

        void onDelivery(Message message) {
            String eventId = message.eventId();
            int attempt = deliveryCounts.merge(eventId, 1, Integer::sum);

            logger.info("event=message_received eventId="
                    + eventId + " attempt=" + attempt);

            if (applied.add(eventId)) {
                // Only simulates the business effect in memory.
                logger.info("event=business_applied eventId=" + eventId);
            } else {
                logger.info("event=message_duplicate eventId="
                        + eventId + " attempt=" + attempt
                        + " action=SKIP_BUSINESS");
            }

            // This is NOT an ACK call to the broker.
            logger.info("event=ack_simulated eventId="
                    + eventId + " attempt=" + attempt);
        }

        int uniqueBusinessEffects() {
            return applied.size();
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("lesson.message.duplicate");
        logger.setLevel(Level.INFO);
        logger.setUseParentHandlers(false);

        Handler output = new Handler() {
            @Override
            public void publish(LogRecord record) {
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
        output.setLevel(Level.ALL);
        logger.addHandler(output);

        try {
            DemoConsumer consumer = new DemoConsumer(logger);
            Message first = new Message("evt-100", "private-payload");

            consumer.onDelivery(first);
            consumer.onDelivery(first); // Simulated redelivery.
            consumer.onDelivery(new Message("evt-101", "other-private"));

            System.out.println("uniqueBusinessEffects="
                    + consumer.uniqueBusinessEffects());
        } finally {
            logger.removeHandler(output);
            output.close();
        }
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac DuplicateMessageLogDemo.java
java DuplicateMessageLogDemo
```

**Exact stdout** of the program above:

```text
event=message_received eventId=evt-100 attempt=1
event=business_applied eventId=evt-100
event=ack_simulated eventId=evt-100 attempt=1
event=message_received eventId=evt-100 attempt=2
event=message_duplicate eventId=evt-100 attempt=2 action=SKIP_BUSINESS
event=ack_simulated eventId=evt-100 attempt=2
event=message_received eventId=evt-101 attempt=1
event=business_applied eventId=evt-101
event=ack_simulated eventId=evt-101 attempt=1
uniqueBusinessEffects=2
```

**Correct interpretation:**
- **3 deliveries were simulated**, but only **2 event IDs were treated as applied** in a single run.
- `message_received` for `evt-100` appears twice, which **accurately reflects the two deliveries**; do not remove the second line if the goal is diagnosing redeliveries.
- There is only one `business_applied` for `evt-100`; the second time uses `message_duplicate` and `SKIP_BUSINESS`.
- `attempt` in the demo is a **local counter**, not a Kafka offset, RabbitMQ delivery tag, or broker-guaranteed retry count. It **resets when the JVM restarts**.
- `ack_simulated` is only a simulated log line; the code does not integrate with a message broker and **does not prove the message was acked**.
- `payload` exists on `Message` but is **not emitted in the log**, avoiding content exposure.
- `Handler` writes `record.getMessage()` to stdout and disables parent handlers, so the output has no extra timestamps. The program assumes a single run in a fresh JVM for demonstration.

**Intentional weakness:** `applied.add(eventId)` and the actual business effect are not in the same database transaction; the demo also does not support concurrency. If the application crashes after adding to the set but before the business operation finishes, such a mechanism could wrongly skip the message after recovery (if state were persisted independently). With multiple instances, each instance has its own set. **Do not use an in-memory `Set` as a production idempotency store**.

## 7. Idempotent Consumer: The Solution Lies in Business Logic, Not the Logger

When receiving a message multiple times, the application must ensure that the side effects of **the same logical action** are not duplicated. This is the core idea of *idempotency*.

Examples:
- Creating an invoice: the same idempotency key does not create two invoices.
- Recording a payment: the same `payment_capture_id` does not charge twice.
- Updating a projection: the same event can be received again without incrementing totals a second time.
- Sending an email: the same business request needs an appropriate anti-resend mechanism; checking the database alone is **not enough** if sending the email happens outside the transaction.

### 7.1. Choosing the Right Deduplication Key Scope

There is no single key for every case. A common design is:

```text
dedup_key = (consumer_name, event_id)
```

Why include `consumer_name`: the same event may need to be processed by **multiple different consumers**, such as `invoice-projector` and `analytics-indexer`. Using a system-wide set keyed only by event ID could cause the first consumer to make the other consumers skip valid work.

However, when a producer might generate two event IDs for **the same retried business action**, you need an additional business constraint such as `paymentId + captureOperation` or a unified idempotency key from the API. Determine what constitutes "the same operation" based on the domain model, not merely on message text or timestamps.

Do not use:
- A hash of the entire payload as a unique key: serialization order, metadata, and unstable fields can alter the hash; two messages with identical bodies are not necessarily the same event.
- Timestamps as IDs: multiple events can share a timestamp, or the same event can get a new timestamp on republish.
- `deliveryTag` or `receiptHandle` as a stable event ID: they can change across deliveries.
- Kafka `offset` as an identity across topics or after republishing.
- Trace ID as an idempotency key: a single trace can contain multiple valid events/actions.

### 7.2. Database Transactions and Unique Constraints

With multiple consumer instances, store processing state in a durable system with **atomic** key checking and creation. PostgreSQL example:

```sql
CREATE TABLE processed_message (
    consumer_name TEXT NOT NULL,
    event_id      TEXT NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
```

Inside the business transaction, you can attempt an insert:

```sql
-- Illustrative SQL for PostgreSQL, executed inside a transaction.
INSERT INTO processed_message (consumer_name, event_id)
VALUES ('invoice-projector', 'evt-100')
ON CONFLICT (consumer_name, event_id) DO NOTHING
RETURNING event_id;
```

If the statement returns **one row**, the consumer has claimed the right to perform the **first processing** in this transaction; only then should it run the business updates in the **same transaction** and commit. If it returns **0 rows**, the key already exists, so the business side effect can be skipped and the acknowledgement handled according to policy. The exact outcome also depends on isolation level, locking, and whether the existing record truly corresponds to a completed committed state.

Concise pseudocode:

```text
begin transaction
    inserted = insertDedupKeyIfAbsent(consumerName, eventId)
    if inserted:
        applyBusinessChangesInSameTransaction()
        insertAuditOrOutboxIfRequired()
commit transaction
ackOrCommitBrokerMessage()
```

**Critical rules:**
1. **Do not durably mark as processed and commit before running the business operation.** A crash in between can cause subsequent deliveries to assume processing already succeeded.
2. **Do not perform a separate `SELECT` followed by `INSERT` outside a single atomic step.** Two concurrent consumers could both see "does not exist." Only a unique constraint/atomic upsert or proper locking closes the race.
3. If the business transaction rolls back, the dedup insert must also roll back so that on retry, the consumer is allowed to try again.
4. Broker ACK **after commit** can still be lost; on redelivery, the dedup store recognizes that the event has already completed.
5. For side effects outside the transaction—such as HTTP APIs, emails, or external payment gateways—you need an idempotency key supported by the **target service**, an outbox/worker with retries, or a reconciliation/compensation process. Never claim that a local transaction guarantees exactly-once execution for network side effects.
6. If there is retention/cleanup on the processed messages table, the key retention period must account for the **redelivery window, DLQ redrive, and replay**; deleting keys too early can cause old events to be reapplied.
7. Key uniqueness must be tied to the **version/schema/consumer contract** if an event can be legitimately replayed for a new projection version. Do not let deduplication block intentional rebuilds.

### 7.3. Business Outcomes and Logs Have Different Durability

Suppose the DB commit succeeds, but the JVM crashes before `logger.info("MESSAGE_APPLIED")`. The side effect is real, yet **the success log line may not exist**. Conversely, if the logger prints before commit, a "success" log may be emitted and then the transaction rolls back.

Therefore:
- Technical logs aid investigation, but they can be incomplete.
- Mandatory business audits should have **events persisted durably** in the same transaction or an equivalent contract mechanism.
- Do not use the count of `MESSAGE_APPLIED` log lines as an accounting source of truth if the log pipeline lacks appropriate guarantees.
- The idempotency store/DB constraint is what prevents repeated business side effects in the chosen design, not turning off duplicate logs.

## 8. Logging Retries and Errors Without Creating Misleading Messages

A failed message may be retried by the application or the broker. Log design should avoid calling every delivery "successful."

Example event sequence:

```text
message_received   eventId=evt-100 attempt=1
processing_failed  eventId=evt-100 attempt=1 reason=TEMPORARY_DB_ERROR
retry_requested    eventId=evt-100 attempt=1 policy=BACKOFF
message_received   eventId=evt-100 attempt=2
business_applied   eventId=evt-100 attempt=2
ack_requested      eventId=evt-100 attempt=2
```

This is an **illustrative flow**, not stdout from the demo. Milestones in a real system may differ depending on the transaction and broker.

What to observe:
- `reason` is a **standardized error code**; do not automatically print the entire payload or exception message that might contain tokens or PII.
- `retry_requested` only means a retry was requested; if the scheduler/broker has not confirmed it, do not log as a certainty that the retry was persisted.
- `attempt` can be an app counter, broker metadata, or a framework-managed attempt; indicate the source.
- For transient errors, backoff/jitter and attempt limits help avoid log storms and downstream overload.
- For poison messages that can never be parsed, use a DLQ/quarantine strategy and log a reference instead of dumping the entire message.
- Ensure failure/duplicate logs include `eventId`, `consumer`, and correlation metadata to distinguish different messages that share the same error text.

**Do not log the same exception at every layer.** A framework retry handler, listener method, and global exception handler might all call the logger for the same error. Define which layer owns the failure event and which layers only add context/tracing to avoid tripling log volume.

## 9. Duplicate Logs Caused by Logging Configuration, Not the Broker

Two identical lines do not always come from two deliveries. In Logback/Log4j 2/JUL, a single log event can be routed to **multiple handlers/appenders**.

### 9.1. Logback Additivity

Suppose the logger for package `com.example.consumer` references the console appender, and the root logger also references the same console appender. By default, Logback loggers have **additivity**, so an event can pass through the child logger and propagate up to root, printing one line **twice**.

A sample Logback configuration to avoid duplication when you want a child logger to have its own appender:

```xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.consumer"
            level="INFO" additivity="false">
        <appender-ref ref="CONSOLE"/>
    </logger>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

`additivity="false"` stops propagation to ancestor loggers from this package; it is not a message deduplication mechanism. Understand your appender topology: if you intentionally want a child logger to write to both console and an audit sink at root, disabling additivity indiscriminately can **drop necessary logs**. Adjust according to your system's routing goals rather than applying it blindly.

A similar pitfall in **JUL** is attaching a `Handler` to a child logger while leaving `setUseParentHandlers(true)`, causing the parent to also write the record. In **Log4j 2**, attribute/config names may differ, but you should likewise check additivity and appender references for your version.

### 9.2. Other Causes

- **Attaching the same handler/appender at multiple layers** or initializing the logging configuration multiple times during the lifecycle.
- A listener logs the failure itself while a retry middleware/AOP interceptor also logs the same exception.
- A message is genuinely received by **two listener containers** per broker topology; this may be two valid subscriptions rather than a logger duplicate.
- An agent tails both container stdout and the same log file.
- A forwarder/collector resends a batch after a lost ACK, causing a single raw log record to be indexed twice.
- A misconfigured bridge layer between JUL, SLF4J, and the backend creates loops or unintended emissions.

**How to distinguish:** Attach a logical `eventId` and a correlation/delivery identifier where available, check how many times the listener callback ran, how many times the logger method was invoked, and then compare stdout/file/collector. If the callback ran once but stdout has two lines, suspect the logger/appender. If stdout has only one line but the index has two documents, suspect the collector. If the callback ran twice for one `eventId`, it is likely a redelivery or two subscriptions.

Do not rely solely on timestamps: two similar logs close in time are not enough to conclude that processing ran twice.

## 10. Structured Logging and SLF4J 2.x

With SLF4J 2.x, you can attach fields to an event instead of concatenating long message strings. The snippet below is **integration-only**; it assumes the logger, message, and context variables are already prepared, and that the backend supports emitting key-value fields:

```java
// SLF4J 2.x + compatible backend/encoder.
logger.atInfo()
      .addKeyValue("event", "message_received")
      .addKeyValue("event_id", safeEventId)
      .addKeyValue("consumer", "invoice-projector")
      .addKeyValue("attempt", knownAttempt)
      .addKeyValue("redelivered", redelivered)
      .log("Message received");
```

Where:
- `safeEventId` is an ID validated for syntax/length, not the full payload.
- `knownAttempt` is logged only when the system has a clear source for the count; otherwise omit the field or log unknown per schema.
- `redelivered` comes from the broker/client contract if available; do not guess it from timestamps.
- The backend/encoder must be configured to output key-value pairs; a plain text pattern does not automatically guarantee every field appears.
- If using MDC/ThreadContext, ensure cleanup at the end of the callback and proper propagation across executors/async threads. Do not put raw message bodies or tokens into MDC.
- Structured events help querying, but **do not automatically strip sensitive data**, nor do they solve duplicate deliveries.

Use consistent schemas and field names across consumers, but do not force two backends with different semantics to pretend they share an identical `deliveryAttempt`.

## 11. How Much Logging Is Enough?

If every message is retried 50 times, logging the full payload and stack trace at `INFO` level can significantly increase CPU, heap, storage, collector costs, and dashboard noise.

A reference policy:

| Scenario | Appropriate Log Level / Volume |
| --- | --- |
| Routine event receipt | `DEBUG` or summary `INFO` per observability needs, no raw body |
| Successful processing | One outcome event after commit if genuinely needed |
| Duplicate detected and skipped | Distinct `DUPLICATE_SKIPPED` event with ID and counter |
| Transient retry | Reason code, attempt, and backoff schedule; avoid repeated stack traces |
| Retries exhausted / DLQ | Prominent event with reference, consumer, standardized error, and destination |
| Poison message | Never dump sensitive payload; quarantine/safe identifier |
| Mandatory audit | Per dedicated policy; never sample arbitrarily |

**Sampling:** You can reduce log volume for routine receipt events, but do not blindly sample mandatory audit logs, financial operations, or logs needed for security investigations. A system can keep **metrics counters** for all attempts and selective detailed logs, while clearly documenting which numbers are exact totals and which are sampled.

**Metrics:** Use low-cardinality, stable labels such as consumer, destination, result, and failure reason. **Do not attach `eventId`, request ID, or message ID as metric labels** because cardinality can grow unbounded. Those IDs belong in logs/traces or an appropriate lookup store.

Suggested metrics:
- `message_deliveries_total{consumer,result}`.
- `message_duplicates_skipped_total{consumer}`.
- `message_processing_failures_total{consumer,reason}`.
- `message_processing_duration_seconds`.
- `message_ack_failures_total{consumer}`.
- `message_dlq_total{consumer,reason}`.
- Queue lag/backlog, consumer restarts/rebalances, and storage health.

Do not derive `processed_unique_total = deliveries_total - duplicates_total` if there are also failed, dropped, invalid, or otherwise skipped messages. Define counters by explicit state and verify consistency.

## 12. Debugging Duplicate Logs: Investigation Procedure

### Step 1: Identify Which Level the "Duplicate" Occurs At

Pick a specific `eventId` and identify its consumer/destination. Do not conclude anything from just two text lines with the same message. Inspect timestamps, consumer instance, broker pointer, attempt/source, event type, and correlation ID.

### Step 2: Count Consumer Callbacks

In test/staging, add listener callback counts and observe broker metadata. If the callback is invoked twice, check:
- Was there a redelivery due to ack/commit timeout, rebalance/restart, requeue, or visibility timeout?
- Are two consumers/subscriptions intentionally configured to process the message?
- Did the producer publish two logical events or the same message twice?
- Does the system retry **inside the handler** within the same delivery before the broker knows the outcome?

### Step 3: Verify Side Effects

Check the idempotency table, database unique constraints, external payment/email APIs, and business transactions. Two `MESSAGE_RECEIVED` logs may correspond to a single effect. If there are two effects, investigate the dedup key and atomicity boundaries.

### Step 4: Check the Logger/Appender at the Emission Point

For a single callback, count logger invocations; inspect the logger tree and additivity. Compare logs at console/file before the collector. If output is duplicated inside the JVM, fix the logging configuration or double instrumentation rather than changing the retry policy.

### Step 5: Check the Collection Pipeline

If the JVM emits one record but the collector/index holds two, check for an agent tailing multiple sources, retries/replays, index document IDs, and sink deduplication policies. If the collector uses at-least-once delivery, duplicates in the index may be an artifact of batch retries.

### Step 6: Test Both Failure and Recovery

Perform failure injection: commit the business transaction successfully and then simulate a lost ACK; verify that the redelivery logs `MESSAGE_DUPLICATE` accurately and does not reapply the side effect. Test restarts and multiple instances, independent of any in-memory demo.

## 13. Sample Test Matrix

| Scenario | Outcome to Verify |
| --- | --- |
| One message, one delivery | One business effect; receipt and outcome logs match |
| Redelivery after successful processing | Two `RECEIVED` logs may appear; only one business effect |
| Crash before DB commit | Transaction rolls back; reprocessed cleanly on redelivery |
| Crash after DB commit but before ack | Redelivery recognized as duplicate; side effect not reapplied |
| Two consumer instances process the same event concurrently | Unique constraint/transaction prevents race |
| Producer republishes the same event ID | Same consumer deduplicates per policy |
| Two events with different IDs but same payment operation | Domain idempotency key prevents repeated business effect if truly the same operation |
| Two different consumers receive one event | Each valid consumer processes independently within its own scope |
| Message goes to DLQ and is redriven days later | Dedup key retention is long enough per policy, or intentional replay is handled |
| Message missing ID / invalid ID | Schema validation/failure policy; do not synthesize a new ID and treat it as the original event |
| Event ID contains newlines/control characters | Log escaping/validation prevents forged records |
| Listener runs once but console shows two lines | Check additivity/handler refs/instrumentation |
| Console shows one line but collector has two copies | Check shipper retries/duplicate ingestion |
| Async logging queue full | Metrics/drop policy and audit durability verified |
| Broker ack API fails | No fake `ACK_CONFIRMED` log; appropriate retry/redelivery handling |

Testing must correlate **logs**, **business state**, **dedup store**, and **broker**. A unit test that only counts log lines cannot prove idempotency.

## 14. Common Mistakes

| Mistake | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| Deleting all duplicate logs by `eventId` | Loses trail of retries, errors, and delivery times | Keep event type + attempt; optimize volume appropriately |
| Treating every `message_received` as `processed` | Confuses receipt with business commit | Log each stage accurately |
| Disabling retries just to hide duplicate logs | Can lose messages on consumer errors | Keep proper delivery policy and idempotency |
| Using an in-memory `Set` in production | Loses state on restart; not shared across replicas | Durable store + atomic constraint |
| Check-then-insert without a transaction | Two consumers can process concurrently | Unique key/atomic upsert and business transaction |
| Committing dedup before the business effect | A crash can permanently skip processing | Same transaction; confirm commit before ack |
| Acking before business commit | A crash can cause lost processing | Design ack/commit order per broker |
| Using RabbitMQ `deliveryTag` as a business ID | Tag changes per channel/delivery | Stable event ID / idempotency key |
| Using Kafka offset as an ID across republishes | Offset is only a position within a topic/partition | Producer-assigned event ID |
| Using SQS receipt handle as a dedup key | Changes on redelivery | Stable application event ID |
| Logging raw payloads to find duplicates | Exposes PII/tokens, inflates log volume | Log selected IDs and metadata |
| Enabling sampling on mandatory audits | Can lose required evidence | Separate audit durability from diagnostic sampling |
| Disabling Logback additivity without checking topology | Can drop logs at root/other appenders | Configure according to desired routing |
| Putting message IDs into metrics labels | Extremely high cardinality | Use consumer/result labels; keep IDs in logs |
| Looking only at logs without checking side effects | Misses duplicate charges/emails/invoices | Correlate DB, external APIs, and idempotency records |
| Assuming Kafka EOS guarantees every DB/HTTP effect runs once | Guarantee has boundaries; does not cover external systems | Appropriate downstream idempotency / outbox |

## 15. Self-Check Exercises

**Question 1.** A listener logs two `MESSAGE_RECEIVED` lines with the same `eventId` but `attempt=1` and `attempt=2`. Can you conclude there is a logging bug or that business logic ran twice?

**No.** It may be a valid redelivery. You need to check how many times the business effect was committed, ack/offset evidence, and the callback count.

**Question 2.** `logger.info("Received {}", id)` is called once, but the Logback console prints twice. Where should you check first?

**Logger tree, appender refs, and additivity**; also check for duplicate handlers/instrumentation. Do not change idempotency logic just because output is duplicated.

**Question 3.** A consumer commits to the DB and then crashes before acking. When the message is redelivered, how should it be handled?

Use a durable dedup key scoped by consumer and event, confirm the business change was committed, **skip the duplicate side effect**, and then ack according to broker policy. You can log `MESSAGE_DUPLICATE` to keep evidence of the redelivery.

**Question 4.** Two messages have different `eventId`s but the same `paymentCaptureId` for the same operation. Is deduplicating by event ID alone enough?

**Not necessarily.** If the producer/operation allows the same action to be emitted with two event IDs, you need a domain-level idempotency key or a unique constraint on the payment operation.

**Question 5.** An event is sent to both `billing-projector` and `analytics-projector`. If billing marks the event ID as processed, should analytics skip it?

**No.** The two consumers have independent responsibilities; the dedup scope typically includes `consumer_name + event_id` or an equivalent key.

**Question 6.** Does an in-RAM `deliveryAttempt` counter in one consumer reflect the number of redeliveries across all replicas after a restart?

**No.** It resets with the process lifecycle and does not share state. Distinguish app-local counts from broker-provided attempt metadata, and do not claim it as a global count.

## 16. Checklist for Java Projects

Before concluding that duplicate message logging is handled properly:

1. **Distinguish the four duplicate types**: broker redelivery, logical event duplicate, logger/appender double emission, and collector duplicate ingestion.
2. Have a **stable event ID**, a domain-appropriate business idempotency key, and a clear consumer scope.
3. Log `RECEIVED`, `APPLIED`, `DUPLICATE_SKIPPED`, `FAILED`, retry, and ack events separately; never use a single "processed" message for all states.
4. Record attempt/redelivered and broker position **only when a semantically valid source exists**; never use offset/deliveryTag/receiptHandle as business identity.
5. Implement consumer idempotency using a durable store/unique constraint and a transaction shared with the business change; do not rely on RAM or check-then-act.
6. Understand the crash windows **before commit**, **after commit before ack**, and **after ack**, as well as their loss/duplication consequences.
7. For side effects outside the DB, have an idempotency key at the target service, an outbox/reconcile flow, or an appropriate compensation strategy.
8. Inspect the Logback/Log4j 2/JUL handler tree and routing; avoid unintended output duplication.
9. Ensure the log collector pipeline does not tail the same source multiple times, or has a policy to recognize duplicate ingestion if needed.
10. Keep raw message payloads, credentials, tokens, and personal data out of logs; validate and escape event IDs.
11. Maintain metrics for deliveries/duplicates/failures/retries/DLQ with low-cardinality labels; keep individual IDs in logs/traces.
12. Test concurrency, restarts, DLQ redrive, external failures, offset/ack loss, async queues, and collector retries.
13. Persist mandatory audits via a sufficiently durable mechanism rather than relying on an unconfirmed `logger.info` line.
14. Ensure investigation dashboards distinguish **delivery count**, **logical event count**, and **actual side-effect count**.

**Conclusion:** In Java messaging applications, a message being redelivered and producing multiple log lines is not necessarily an error. You must know whether a log line describes a **delivery**, **business processing**, **retry**, **ack**, or **log emission via appenders/collectors**. Design a clear event schema, durable idempotency, and sufficient stage observability; preserve useful duplicate trails without duplicating side effects or exposing payloads just for debugging.