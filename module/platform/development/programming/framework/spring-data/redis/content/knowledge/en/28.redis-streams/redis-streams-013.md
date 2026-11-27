# At-Least-Once Processing and Idempotent Consumer Design

**Redis Streams** is a Redis data structure that stores records with ordered IDs. Unlike Redis Pub/Sub, which pushes messages instantaneously to connected subscribers, a Stream can retain messages so consumers can read them later. With **consumer groups**, Redis also tracks records delivered to consumers that have not yet been acknowledged with `XACK`.

As a result, applications using **Spring Data Redis** can build *at-least-once* processing pipelines: if a consumer receives a message and dies before acknowledging it, a consumer can retrieve the pending message and attempt to continue processing. However, **redelivery means a single message can be processed multiple times**. To avoid charging twice, sending two emails, or double-counting totals, handlers must be designed to be **idempotent**.

This lesson aims to explain the `XADD → XREADGROUP → business processing → XACK` path, how to recover pending messages, and how to combine deduplication keys with business data transactions. Examples use Spring Data Redis, Java 21, and PostgreSQL for an operation requiring consistency.

## 1. What Does At-Least-Once Guarantee?

Common delivery semantics:

| Semantics | Meaning | Impact on consumer |
| --- | --- | --- |
| **At-most-once** | Delivered once or not at all; messages can be lost on failure | Low broker duplicate risk, yet risk of skipping |
| **At-least-once** | Unfinished messages can be redelivered until acknowledged, while the system retains them and recovery exists | Handler must tolerate duplicate processing |
| **Exactly-once effect** | Business effect applied once for the same logical event | Requires idempotency, transactions, or appropriate coordination protocols |

In Redis Streams, consumer groups use a **Pending Entries List (PEL)** to track message delivery. This supports building at-least-once behavior, though actual results still depend on the application **recovering pending entries**, retention settings, and Redis data durability. Simply creating a group and calling `XREADGROUP` does not automatically guarantee every event will succeed.

Idempotency is the property:

\[
f(f(s,e),e)=f(s,e)
\]

where `s` is business state and `e` is an event. Processing the same event `e` again does not change the final outcome compared to processing it once.

Examples:

- `SET order:101:status PAID` with the same state can have an idempotent final effect, assuming no extra side effects.
- `INCR total_paid` or `UPDATE balance = balance + 100` is **not idempotent**; running twice adds twice.
- Sending an email, calling a payment gateway, or writing an external notification **does not become idempotent** just because the Redis operation uses the same message.

Therefore, proper design must examine **business effects**, not merely count how many times a callback runs.

## 2. Message Lifecycle in a Consumer Group

Suppose a system has stream `billing:payments` and group `billing-workers`. The publisher writes a payment event to the stream:

~~~redis
XADD billing:payments * eventId evt-101 invoiceId inv-42 amountCents 125000
~~~

Redis generates a **Stream ID**, e.g., `1731500000000-0`. This ID differs from the business `eventId` created by the publisher:

- **Stream ID** identifies a specific entry in the Redis Stream, used for `XACK`, `XPENDING`, `XCLAIM`, or `XAUTOCLAIM`.
- **`eventId`** identifies the business event under the cross-system contract; the same event republished may get a new Stream ID while retaining the same `eventId`.

Create the group before workers start:

~~~redis
XGROUP CREATE billing:payments billing-workers 0 MKSTREAM
~~~

ID `0` lets the group read existing entries currently stored in the stream from the start. Creating the group with `$` starts from **new messages arriving after group creation**, skipping older entries during normal reading.

Worker reads new messages:

~~~redis
XREADGROUP GROUP billing-workers worker-a COUNT 10 BLOCK 2000 STREAMS billing:payments >
~~~

`>` means the consumer group wants entries **not yet delivered to any consumer in the group**. Redis adds newly delivered messages to the group's PEL, associated with the owning consumer.

Once business work completes:

~~~redis
XACK billing:payments billing-workers 1731500000000-0
~~~

`XACK` removes the entry from the group's PEL. It is **not a command to delete the message from the stream itself**. The entry can remain until trimmed or deleted by storage policies.

~~~text
Publisher                   Redis Streams                 Consumer
    |                            |                            |
    +-- XADD ------------------->| entry stored in stream     |
    |                            |                            |
    |                            |<----- XREADGROUP (>) ------+
    |                            |------ message ------------>|
    |                            |     entry added to PEL     |
    |                            |                            |
    |                            |                    Business processing
    |                            |                            |
    |                            |<--------- XACK ------------+
    |                            |     entry removed from PEL |
~~~

**Key takeaway:** ACK confirms group processing progress, whereas stream data and business effects have separate lifecycles.

## 3. Pending Entries List and Why Messages Get Redelivered

The PEL tracks delivered-but-unACKed entries. For each pending entry, Redis can track the owning consumer, idle time, and delivery count.

Inspection commands:

~~~redis
XPENDING billing:payments billing-workers
XPENDING billing:payments billing-workers - + 10
~~~

The first gives a summary of pending count, ID range, and per-consumer distribution. The extended form shows ID, consumer, idle time, and delivery count. **Pending does not automatically mean failure**: a message currently being processed normally is also pending until ACKed.

### Four Critical Scenarios

| Failure timing | Possible state | Recovery behavior |
| --- | --- | --- |
| Before `XREADGROUP` delivers message | Entry undelivered, not in PEL | A worker in the group can read it as a new message |
| After receipt, before business write | Entry pending, no side effect yet | Consumer retrieves and processes it |
| After business write succeeds, before `XACK` | Side effect occurred; entry stays pending | **Risk of duplicate processing** |
| After `XACK` succeeds | Entry no longer pending | Group does not automatically redeliver due to missing ACK |

The third scenario is why idempotency is required. For example:

~~~text
1. Worker A receives event evt-101.
2. Worker A adds 125,000 to total paid.
3. Database commit succeeds.
4. Worker A loses power before XACK.
5. Redis still holds entry in PEL.
6. Worker B claims entry and reprocesses it.
7. If code adds the money again -> business state is wrong.
~~~

You cannot solve this by moving `XACK` ahead of the commit:

~~~text
XACK succeeds
    |
    v
Worker crashes before updating database
    |
    v
Message no longer pending; business effect never occurred
~~~

The default rule for consumers with durable effects is **ACK after business effects complete and commit**. You must then accept possible reprocessing and make handlers idempotent.

## 4. Two Layers of Identifiers for Deduplication

Do not use consumer name, Redis connection ID, or receipt timestamp as an idempotency key. They change on worker restarts and do not represent the event.

There are two levels of deduplication:

| Key | What it detects | Limitation |
| --- | --- | --- |
| **Stream ID** | Same Redis entry redelivered after crash/claim | Fails to recognize the same event republished by producer as a new entry |
| **Business `eventId`** | Same logical event redelivered or republished under a different Stream ID | Requires producer to keep `eventId` stable on retries and never reuse an `eventId` for a different event |

For instance, a producer unsure whether `XADD` succeeded retries:

~~~text
Stream ID 1731500000000-0   eventId=evt-101
Stream ID 1731500000005-0   eventId=evt-101
~~~

The two entries are two separate Redis records, yet represent one logical event. Deduplicating by Stream ID treats them as two events; deduplicating by `eventId` catches the duplicate.

**`eventId` must remain stable across retries**. If a producer generates a fresh UUID every time it resends the same operation, consumers have no general way to recognize two payloads as one logical event. At the same time, a repeated `eventId` with a different payload is a contract violation that should be detected, not silently accepted.

## 5. An Approach That Looks Right Yet Can Lose Business Work

Suppose a consumer marks events processed in Redis:

~~~redis
SET processed:evt-101 1 NX EX 86400
~~~

If the command succeeds, the consumer proceeds to write to the database. If the key already exists, the consumer skips it.

This helps in simple problems, yet is **insufficient** for critical business operations when the deduplication marker and side effects live in two different resources.

~~~text
SET processed:evt-101 1 NX EX 86400  -> succeeds
                     |
                 Worker crashes
                     |
             Database not updated yet
                     |
        Retry sees processed key already exists
                     |
                 Skips processing
                     |
          Business update permanently lost
~~~

Reversing the order does not fully solve it either:

~~~text
Database update succeeds
         |
      Worker crashes
         |
Processed key not written yet
         |
Retry updates database a second time
~~~

To ensure the **processed marker and business data mutation succeed together or roll back together**, place them inside the **same transaction in the business data store**, when that store supports appropriate transactions.

Redis supports Lua scripts or transactions for data residing entirely inside Redis, yet those cannot automatically span a PostgreSQL transaction and an HTTP call to an external system.

## 6. Idempotent Design Using Unique Constraints in the Database

Business example: each `PaymentReceived` event adds an amount to an invoice's payment total. Adding twice produces the wrong total. We use PostgreSQL and store a deduplication marker keyed uniquely by **handler + eventId**.

### 6.1. Illustrative Schema

~~~sql
CREATE TABLE invoice_totals (
    invoice_id VARCHAR(100) PRIMARY KEY,
    total_paid_cents BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE processed_events (
    handler_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (handler_name, event_id)
);
~~~

`handler_name` lets multiple consumer/handler types share an `eventId` independently. If one event updates multiple projections, each handler records its own completion marker.

In projects using other SQL databases, conflict-ignoring insert syntax differs. The example below uses PostgreSQL's `ON CONFLICT DO NOTHING`.

### 6.2. Service Applying Side Effects Alongside the Deduplication Marker

~~~java
package com.example.redis.streams;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PaymentProjectionService {

    private static final String HANDLER = "invoice-payment-projection";

    private final JdbcTemplate jdbc;

    public PaymentProjectionService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void apply(String eventId, String invoiceId, long amountCents) {
        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("eventId is required");
        }
        if (invoiceId == null || invoiceId.isBlank() || amountCents <= 0) {
            throw new IllegalArgumentException(
                "Invalid payment event"
            );
        }

        int inserted = jdbc.update(
            """
            INSERT INTO processed_events (handler_name, event_id)
            VALUES (?, ?)
            ON CONFLICT DO NOTHING
            """,
            HANDLER, eventId
        );

        if (inserted == 0) {
            // This handler already committed the same eventId earlier.
            return;
        }

        int updated = jdbc.update(
            """
            UPDATE invoice_totals
            SET total_paid_cents = total_paid_cents + ?
            WHERE invoice_id = ?
            """,
            amountCents, invoiceId
        );

        if (updated != 1) {
            // Exception rolls back the marker INSERT as well.
            throw new IllegalStateException(
                "Invoice not found: " + invoiceId
            );
        }
    }
}
~~~

This example requires the app to have `JdbcTemplate`, a `PlatformTransactionManager` for PostgreSQL, and `apply` invoked through a Spring proxy so `@Transactional` takes effect. Spring Boot with the JDBC starter and a configured `DataSource` typically provides these. Self-invocation inside the same bean bypasses proxy-based transactions.

### Why Does This Prevent Duplicates Across Two Workers?

Suppose worker A and worker B process the same `eventId` nearly simultaneously:

1. Both try to `INSERT` key `(handler_name, event_id)`.
2. PostgreSQL's `PRIMARY KEY` constraint ensures only one transaction can commit that marker.
3. The winning transaction updates the invoice and commits both changes.
4. The other transaction sees the conflict and does not add the amount again.
5. If the winning transaction rolls back due to an invoice update error, the marker rolls back too; a subsequent retry gets to perform the business update.

The key mechanism is not a pre-check `SELECT EXISTS`, because check-then-insert can race. **The database unique constraint plus transaction** forms the consistency boundary here.

Note: in this example, incrementing `total_paid_cents` once still assumes each invoice already has an `invoice_totals` row. If the invoice does not exist, the transaction fails and the Redis entry still needs retry or incident handling. In production systems, also verify currency, version, event type, and business invariants.

## 7. Handling Messages with Spring Data Redis and ACKing After Commit

Suppose Redis already has the consumer group:

~~~redis
XGROUP CREATE billing:payments billing-workers 0 MKSTREAM
~~~

Group creation runs once during infrastructure provisioning, not unconditionally on every processing pass. If the group already exists, Redis returns a corresponding error; bootstrap code must handle that case without masking connection or configuration errors.

Batch-polling example using `StringRedisTemplate` and `StreamOperations`:

~~~java
package com.example.redis.streams;

import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.core.StreamOperations;
import org.springframework.data.redis.core.StreamReadOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class PaymentStreamConsumer {

    private static final Logger log =
        LoggerFactory.getLogger(PaymentStreamConsumer.class);

    private static final String STREAM = "billing:payments";
    private static final String GROUP = "billing-workers";

    private final StreamOperations<String, String, String> streams;
    private final PaymentProjectionService projection;

    public PaymentStreamConsumer(
            StringRedisTemplate redis,
            PaymentProjectionService projection) {
        this.streams = redis.opsForStream();
        this.projection = projection;
    }

    // Invoked from a lifecycle-managed worker, not inside an HTTP request.
    public int pollOnce(String consumerName) {
        List<MapRecord<String, String, String>> records = streams.read(
            Consumer.from(GROUP, consumerName),
            StreamReadOptions.empty()
                .count(10)
                .block(Duration.ofSeconds(2)),
            StreamOffset.create(STREAM, ReadOffset.lastConsumed())
        );

        if (records == null || records.isEmpty()) {
            return 0;
        }

        for (MapRecord<String, String, String> record : records) {
            try {
                Map<String, String> data = record.getValue();
                String eventId = data.get("eventId");
                String invoiceId = data.get("invoiceId");
                long amountCents = Long.parseLong(
                    data.get("amountCents")
                );

                // @Transactional method: marker + side effect
                // commit or roll back together in PostgreSQL.
                projection.apply(eventId, invoiceId, amountCents);

                // ACK ONLY AFTER apply() returns successfully.
                streams.acknowledge(STREAM, GROUP, record.getId());
            } catch (Exception error) {
                // Do not ACK on processing error.
                // Entry remains pending for recovery to decide retry/DLQ.
                log.warn(
                    "Failed stream entry id={} in group={}",
                    record.getId(), GROUP, error
                );
            }
        }

        return records.size();
    }
}
~~~

Imports and APIs illustrate the Spring Data Redis 3.x style. `StringRedisTemplate` uses string serializers for keys/values/hashes; writers and readers must agree on encoding and field formats. If the stream uses binary payloads or a custom serializer, adjust `MapRecord` types and deserialization accordingly.

**Do not wrap the `XREADGROUP` wait and entire poll loop in PostgreSQL's `@Transactional`.** Transactions should cover only the database update; ACK runs after the transactional method finishes. This avoids holding DB transactions/connections open while Redis waits for messages.

### One Poll Loop Is Not a Complete Consumer System

`pollOnce` is the processing core, invoked by a worker with its own lifecycle. Production apps must:

- Start workers only when consumer groups and connections are ready.
- Use a stable `consumerName` or manage per-instance identity; multiple workers in the same group need distinct names.
- Stop polling loops on app shutdown; bound block duration so shutdown finishes cleanly.
- Cap in-flight messages and DB/Redis resource consumption.
- Provide a separate mechanism for **old pending entries**, since `ReadOffset.lastConsumed()` in a consumer group fetches new messages rather than scanning all pending entries.

Spring Data Redis also provides `StreamMessageListenerContainer` and `StreamReceiver` for continuous listening. When using a listener container, **disable auto-ack** if business rules require ACKing only after commit; auto-ACKing too early loses retry capability.

## 8. Why Is `ReadOffset.lastConsumed()` Insufficient for Recovery?

In Redis CLI, consumer groups use:

~~~redis
XREADGROUP GROUP billing-workers worker-a STREAMS billing:payments >
~~~

`>` targets entries **not yet delivered**. An entry previously delivered to `worker-a` and unACKed sits in the PEL; calling `>` repeatedly will not re-read that pending entry.

There are two recovery paths:

1. **Read the consumer's own pending entries** by passing an ID other than `>` to `XREADGROUP`, such as `0`, to process entries already pending for that consumer.
2. **Claim pending entries from an old consumer** with `XCLAIM` or `XAUTOCLAIM`, suited when an old worker died or can no longer finish.

Example re-reading `worker-a`'s own pending entries:

~~~redis
XREADGROUP GROUP billing-workers worker-a COUNT 10 STREAMS billing:payments 0
~~~

With ID `0`, Redis returns pending entries for that consumer by ID range, not never-delivered entries. Distinguish this clearly from `>`.

### Recovery with `XAUTOCLAIM`

`XAUTOCLAIM` (Redis 6.2+) finds and transfers ownership of pending entries idle long enough:

~~~redis
XAUTOCLAIM billing:payments billing-workers worker-b 60000 0-0 COUNT 100
~~~

Meaning:

| Parameter | Role |
| --- | --- |
| `billing:payments` | Stream name |
| `billing-workers` | Consumer group |
| `worker-b` | Consumer taking ownership |
| `60000` | Minimum 60,000 ms idle before claiming |
| `0-0` | Starting ID for PEL scan |
| `COUNT 100` | Target entry count per claim turn |

`XAUTOCLAIM` returns a cursor ID to continue scanning along with the claimed entries. Workers should follow the cursor until the scan pass finishes, then schedule future passes. In newer Redis versions, the response may also include IDs of entries deleted from the stream while still referenced in the PEL.

**Do not set `min-idle` too short.** If a legitimate worker takes 90 seconds while `XAUTOCLAIM` takes over after 5 seconds, two workers execute simultaneously. Idempotency still protects correctness, yet premature claims waste load and cause operational noise.

In systems with variable processing durations, measure p95/p99 processing times and pick `min-idle`, timeouts, and recovery intervals accordingly. Very long jobs may need heartbeats/leases to distinguish slow workers from dead ones.

## 9. Retries, Poison Messages, and Dead Letter Queues

Not every error should retry forever:

- **Transient errors**: database timeouts, Redis network glitches, overloaded downstream services; retries with backoff help.
- **Permanent data errors**: missing `eventId`, malformed money strings, incompatible event schemas; infinite retries will never fix payloads.
- **Conditional business errors**: invoice not created yet or unready state; distinguish event ordering delays from unrecoverable errors.

PEL metadata reports **how many times an entry was delivered**. However, “delivery count” does not equal successful database updates: a delivery might crash before entering the handler, or a handler might fail before touching the DB.

A practical operational policy:

~~~text
Entry pending too long
         |
         v
XAUTOCLAIM to recovery worker
         |
         v
Inspect delivery count / recent errors
         |
      +-- retryable --> reprocess --> commit --> XACK
      |
      +-- unprocessable further
                    |
                    v
           Persist durably to DLQ
                    |
                    v
           Confirm DLQ write succeeded
                    |
                    v
           XACK entry in original group
~~~

The DLQ can also be a separate Redis Stream, such as `billing:payments:dlq`, or a database table storing payloads and failure reasons for human investigation.

**Important:** if writing to the DLQ succeeds and the worker dies before ACKing the original entry, recovery may write to the DLQ a second time. If a deduplicated DLQ is needed, use a dedicated idempotency key or controlled state transition; simply running `XADD DLQ` and `XACK` as two separate commands does not guarantee atomicity.

Never ACK failed messages just to “clean up” the PEL unless you have decided the event may be discarded or is safely persisted downstream.

## 10. Idempotency with Side Effects Outside the Database

The `processed_events` + PostgreSQL transaction approach ensures single execution **for mutations inside that same database transaction**. It does not automatically cover emails, HTTP calls, object storage, or another Redis key.

Suppose a handler does:

~~~text
1. INSERT processed_events
2. UPDATE invoice_totals
3. Send confirmation email
4. COMMIT PostgreSQL
5. XACK Redis
~~~

If the email sends and PostgreSQL rolls back, a retry sends a second email. If the database commits and the app dies before sending the email, the email can be lost even though the event is marked processed.

A common solution is the **transactional outbox**:

~~~text
          Redis Stream event
                 |
                 v
       PostgreSQL Transaction
        /        |          \
       v         v           v
  Processed   Update DB   Outbox row
   marker
        \        |          /
         +-------+---------+
                 |
             COMMIT DB
                 |
                 v
               XACK

         Separate Outbox Publisher
                 |
                 v
       Send email / API / new event
                 |
                 v
       Record send state + retries
~~~

The outbox prevents losing the **intent to execute a side effect**, though the external publisher can still send twice if a response drops after the receiver processed it. Whenever possible, pass an **idempotency key** to target APIs or use unique business keys at the destination. For emails, decide whether occasional duplicates are acceptable or build tracking/deduplication as required.

Likewise, if all business state resides in Redis, consider a Lua script or atomic Redis operations to check `eventId` and apply effects within scope. Still, Redis transactions do not provide atomicity with PostgreSQL or external systems.

## 11. Duplicate Data, Ordering, and Contention Among Consumers

At-least-once does not mean every event executes in strict business order:

- Redis Streams orders entries by ID, yet multiple consumers in a group process in parallel and finish at different times.
- An older pending event may be claimed after newer events have already completed.
- A producer may emit the same logical event multiple times under different Stream IDs.

Example:

~~~text
evt-10: Set order status = PAID
evt-11: Set order status = REFUNDED
~~~

If `evt-11` finishes before `evt-10`, a handler blindly executing `SET status = ...` can overwrite the status backward to `PAID`. Both events executed **once**, yet the final state is wrong.

Therefore, alongside an idempotency key, some domains need:

- **Version/sequence** per aggregate, e.g., `orderVersion = 12`.
- **Conditional updates** applied only when the next version is valid or when the event is newer.
- **Entity-level partitioning** so events for the same aggregate flow through an ordered lane.
- **Reconciliation** to recover when events arrive late or go missing.

Example version-guarded update in PostgreSQL:

~~~sql
UPDATE order_projection
SET status = :new_status, version = :event_version
WHERE order_id = :order_id
  AND version < :event_version;
~~~

`version < event_version` only illustrates a “latest event wins” model. When events must apply sequentially step by step without skipping intermediate versions, enforce stronger checks such as `version = event_version - 1` and handle gaps.

**Idempotency** handles duplicates of the same event; **ordering/versioning** handles relationships across different events.

## 12. Stream Retention and Deduplication Marker Lifespan

At-least-once only remains meaningful while Redis retains data needed for retries. You can cap stream size with `MAXLEN` or bound by ID/time with trim policies, while accounting for unACKed messages.

Example:

~~~redis
XADD billing:payments MAXLEN ~ 100000 * eventId evt-202 invoiceId inv-50 amountCents 75000
~~~

`~` performs approximate trimming. Trimming can remove an entry from the stream **even while that entry is still unfinished**; depending on commands and versions, the PEL can keep referencing an ID whose payload is gone. Recovery cannot reprocess a deleted payload unless a durable copy exists elsewhere.

Therefore:

1. Size retention longer than expected downtime, `min-idle` claim windows, retry times, and operational limits.
2. Monitor long-lived pending items and processing lag before aggressive trimming.
3. Configure Redis backups, persistence, and replication to match required durability.
4. For events that must never be lost, keep a durable source of truth and log outside volatile memory.

Redis Streams stores entries, yet data durability still depends on AOF/RDB, replication, and server recovery plans. **At-least-once is not a guarantee of zero data loss under every infrastructure setup**.

### How Long Should Idempotency Markers Be Kept?

When using `processed_events`, purging markers too early lets very late retries re-apply effects. Suppose markers expire after 24 hours while an entry stays pending or a producer replays after 72 hours; the handler treats the old event as new.

Marker retention should at least cover:

- The window during which the same `eventId` can still be re-sent.
- Stream retention and retry/DLQ/replay durations.
- Business criticality—for example, payment events may require long-term marker retention.

If the table grows huge, partition it by time and prune under a controlled policy—never purge solely to save disk space and inadvertently reopen double-charging.

## 13. Operating with Multiple Consumer Instances

A consumer group can have many consumers:

~~~text
                  Redis Stream
                billing:payments
                       |
               Group billing-workers
                /       |       \
               v        v        v
           worker-a  worker-b  worker-c
               |        |        |
               +--------+--------+
                        |
                    PostgreSQL
             UNIQUE(handler,eventId)
~~~

Redis distributes new messages in the group per consumer-group mechanics; each new entry is normally delivered to one consumer. When a worker dies, pending entries do not vanish: recovery can claim them onto another worker. Thus, even though an entry usually has **one owning consumer at a time**, two processes can still run business logic concurrently if claims fire too early or connections lag.

PostgreSQL's unique constraint protects state even across multiple app instances. An in-memory semaphore or `seenEventIds` map in one JVM is insufficient because each instance has isolated memory and loses it on restart.

Operational signals to monitor:

| Metric | What to detect |
| --- | --- |
| Pending count in group | UnACKed backlog |
| Pending idle p95/p99 or oldest idle | Hung or abandoned workers |
| Delivery attempts/claims | Abnormal retries, chronic errors |
| Message processing latency | Whether to raise `min-idle` or lower concurrency |
| Duplicate `eventId`s skipped | Frequency of duplicate deliveries or publishes |
| Commit errors and ACK errors | Distinguish business errors from broker failures |
| DLQ size and oldest record age | Poison messages needing intervention |
| Stream length/retention | Risk of trimming before recovery |
| Consumer lag and throughput | Ability to keep up with producers |

On Redis, inspect using:

~~~redis
XINFO STREAM billing:payments
XINFO GROUPS billing:payments
XINFO CONSUMERS billing:payments billing-workers
XPENDING billing:payments billing-workers
~~~

`lag` and returned fields can vary by Redis version and group state; never conclude the entire pipeline is healthy from a single number.

## 14. Testing to Prove Idempotency and Recovery

A system must verify both **business guarantees** and **pending message behavior**. Suitable test cases include:

| Case | Expected outcome |
| --- | --- |
| Same `eventId` processed twice in one worker | `total_paid_cents` increments only once |
| Two workers process one `eventId` concurrently | Unique constraint ensures one transaction applies |
| DB error after inserting marker before commit | Transaction rolls back both marker and side effect; retries can run again |
| DB commit succeeds but ACK fails | Retry redelivers; marker stops double-counting; then ACKs |
| Event missing fields or wrong types | Not ACKed as success; routed to retry/DLQ policy |
| New message read without ACK | Entry appears in PEL |
| Old worker dies, idle exceeds threshold | Recovery claims it; handler remains idempotent |
| Same `eventId` published under two Stream IDs | Only one business effect if `eventId` is stable |
| Redis trims payload while entry is pending | Detects missing payload and follows retention/recovery policy |

### 14.1. Testing at the PostgreSQL Transaction Level

Suppose `invoice_totals` already has invoice `inv-test-1` with total `0`:

~~~java
@Test
void duplicateEventDoesNotDoubleApplyPayment() {
    projection.apply("evt-test-1", "inv-test-1", 125000);
    projection.apply("evt-test-1", "inv-test-1", 125000);

    Long paid = jdbc.queryForObject(
        """
        SELECT total_paid_cents
        FROM invoice_totals
        WHERE invoice_id = ?
        """,
        Long.class,
        "inv-test-1"
    );

    assertThat(paid).isEqualTo(125000L);
}
~~~

This test should run against a real test PostgreSQL database, schema, and transaction-configured `PaymentProjectionService`. Do not mock `JdbcTemplate` if the goal is proving unique constraints and rollbacks.

Another test can intentionally emit an event for a nonexistent invoice, catch the exception, then create the invoice and call again with the **same `eventId`**. If the marker rolled back properly, the retry updates the invoice. This proves you did not fall into the trap of “marking processed before performing business work”.

### 14.2. Testing the PEL on Real Redis

With a dedicated test stream:

~~~redis
XADD test:payments * eventId evt-test-2 invoiceId inv-test-2 amountCents 20000
XGROUP CREATE test:payments test-group 0
XREADGROUP GROUP test-group test-worker COUNT 1 STREAMS test:payments >
XPENDING test:payments test-group
~~~

After `XREADGROUP`, pending count increases when an entry is delivered and unACKed. Take the **actual Stream ID** from the `XREADGROUP` response and run:

~~~redis
XACK test:payments test-group <stream-id>
XPENDING test:payments test-group
~~~

After a successful ACK, that entry leaves the PEL. This tests **Redis behavior**, distinct from testing that business totals do not double-count.

With JUnit/Spring Boot, you can start Redis via Testcontainers, create isolated UUID stream/group names, and run equivalent steps through `StringRedisTemplate.opsForStream()`. Avoid hardcoded `Thread.sleep(...)` waits for pending transitions; inspect real state and use bounded polling when awaiting async behavior.

### 14.3. Fault Injection at the Right Spot

Production crashes are hard to reproduce in simple unit tests. In controlled integration tests, inject a hook between **DB commit** and **`XACK`**, intentionally skip ACK, and let recovery reprocess the same `eventId`. Key verification assertions:

~~~text
Times handler received event       >= 2
Times DB effect committed           = 1
Pending after recovery + ACK        = 0
~~~

This provides clear proof of **at-least-once delivery with idempotent effects**. Asserting only that a callback ran once ignores the exact failure mode the system must survive.

## 15. Common Implementation Mistakes

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| Money added or inventory deducted twice | Message redelivered after side effect committed | Deduplicate by `eventId` inside transaction / unique constraint |
| Message gone from pending yet DB unchanged | `XACK` ran before commit or auto-ack was used | ACK after commit; disable auto-ack on containers |
| Only new messages processed while old pending never drains | Worker only reads `>`/`lastConsumed` | Build PEL recovery with pending reads / `XAUTOCLAIM` |
| `SET NX processed` succeeds then worker crashes | Marker written before side effect in another store | Put marker and business mutation in the same transaction |
| Retrying same event still applies twice | Producer generates fresh `eventId` on republish | Define stable `eventId` and retry contract |
| Two instances both update same event | Deduplication used in-JVM `ConcurrentHashMap` | Unique constraints / atomicity in shared storage |
| Pending claimed while original worker still runs | `min-idle` shorter than actual processing latency | Tune threshold to p99 latency; keep handlers idempotent |
| Poison message retries forever | No retry cap or DLQ | Classify errors and write DLQ before ACKing per policy |
| ACK succeeds yet entry stays visible in `XRANGE` | `XACK` does not delete stream entries | Manage retention/trimming separately |
| Pending has ID yet payload cannot be read | Stream trimmed/deleted entry | Protect retention; monitor pending and recovery |
| Old event overwrites newer event state | Parallel processing broke business ordering | Versioning/conditional updates or entity partitioning |
| Email sent twice despite accurate DB marker | Side effect sits outside DB transaction | Transactional outbox and receiver-side idempotency |
| New consumer group misses old history | Group was created with `$` | Choose start offset per requirements; `0` to read old data |
| Worker stops yet messages do not auto-move to another worker | Redis keeps PEL ownership | Recovery claiming with explicit idle threshold and policy |

## 16. Operational Design Pattern

A reliable processing pipeline can be structured into two workers:

~~~text
                          Producer
                             |
                             v
                      XADD stable eventId
                             |
                             v
                     Redis Stream + Group
                        /            \
                       /              \
             New-work worker      Recovery worker
                 XREADGROUP >          XPENDING
                      |                XAUTOCLAIM
                      +-------+--------+
                              |
                              v
                        Validate payload
                              |
                              v
               PostgreSQL transaction:
                 - INSERT dedupe marker
                 - UPDATE business state
                 - INSERT outbox if needed
                              |
                     +--------+--------+
                     |                 |
                  COMMIT             ROLLBACK
                     |                 |
                     v                 v
                    XACK         Keep pending/retry
                     |              or DLQ
                     v
               Done for group
~~~

With this architecture, enforce these rules:

1. **Producer** generates `eventId` once per logical event and keeps it across retries.
2. **Consumer** treats every delivery as potentially duplicate, even the first one it sees.
3. **Database transaction** protects both the deduplication marker and business state changes.
4. **`XACK`** runs only after the handler finishes or confirms the event was already processed earlier.
5. **Recovery worker** handles overdue pending entries with backoff and retry caps.
6. **Poison messages** go to a DLQ or investigation store before leaving the retry loop.
7. **Retention and idempotency windows** span downtime, replays, and business obligations.
8. **Ordering/versioning** is designed explicitly when multiple events touch one entity.
9. **External DB side effects** use outboxes/destination idempotency as required.
10. **Metrics** for pending counts, duplicates, ACK failures, DLQ size, and processing time are monitored continuously.

Redis Streams provides the foundation for **redelivering unacknowledged messages**, while correctness when messages arrive multiple times is the application's design responsibility. Combining consumer groups, PEL recovery, post-commit ACK, and transactional idempotency lets the system handle redeliveries safely without ever assuming a callback runs only once.
