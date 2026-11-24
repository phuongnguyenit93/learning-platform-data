# Inbox pattern

## 1. What problem does the inbox pattern solve?

In a system using Spring Kafka and a database, a consumer often receives a Kafka event and writes changes to a database. Difficulty arises when **the database transaction** and **the Kafka offset commit** are two independent operations.

Consider a consumer processing `PaymentConfirmed`:

~~~text
Kafka topic: payments.confirmed
            |
            v
       @KafkaListener
            |
            v
      Write orders to DB
            |
            v
      Commit Kafka offset
~~~

If the database commits successfully but the application crashes before the Kafka offset is committed, the record can be redelivered after the consumer restarts. If processed naively a second time, the system may record the payment twice, double-count revenue, or emit unwanted extra events.

The **Inbox pattern** solves this by writing a marker identifying the processed event into **the same database transaction** as the business side effect. When the record is redelivered, the consumer checks that marker and skips the already-completed side effect.

Core principle:

> Recording that an event was processed and updating business data must commit or roll back together in a single database transaction.

An inbox does not stop Kafka from delivering a record multiple times. It ensures multiple deliveries of the same event produce **the same business effect** in the database, provided the idempotency key and transaction boundary are designed properly.

## 2. Why does at-least-once require an inbox?

### 2.1. Two systems do not commit atomically

A simple listener:

~~~java
@KafkaListener(topics = "payments.confirmed", groupId = "billing-service")
public void onPayment(PaymentConfirmed event) {
    orderRepository.markAsPaid(event.orderId());
}
~~~

If Spring Kafka commits the offset after the listener returns normally, the sequence can be:

~~~mermaid
sequenceDiagram
    participant K as Kafka broker
    participant L as Spring Kafka listener
    participant D as Database
    K-->>L: Record offset 41
    L->>D: UPDATE orders
    D-->>L: DB commit succeeds
    Note over L: Process crashes here
    Note over K: Offset 42 not committed yet
    K-->>L: After restart: redelivers offset 41
    L->>D: UPDATE orders a second time
~~~

This is the classic failure window of **at-least-once delivery**. Kafka does not promise the listener runs only once. It prioritizes not skipping uncommitted records.

Choosing to commit the offset **before** the database transaction to avoid duplicates opens the opposite window: Kafka advances past the record while the database has not been updated yet. A crash then loses business processing.

An inbox tolerates redelivery without repeating database effects. It does not turn the two commits into an XA transaction.

### 2.2. Other sources of duplicates

Even if a listener rarely crashes, duplicates still happen due to:

- Consumer rebalancing before committing offsets.
- Kafka offset commit failures or timeouts.
- Listener throwing an exception after a side effect already committed.
- Kafka producer resending the same business event after a timeout.
- Events replayed with a new group ID or operational tooling.
- Multiple topics, services, or consumer groups receiving one logical event.
- Old and new application versions running simultaneously during a rollout.

Inbox is therefore an **idempotent consumer** mechanism, not merely a fix for rare crash cases.

## 3. Structure of an inbox

### 3.1. Minimal inbox table

With PostgreSQL, you can create a table:

~~~sql
CREATE TABLE consumer_inbox (
    consumer_name VARCHAR(120) NOT NULL,
    event_id UUID NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Meaning:

- `consumer_name`: logical consumer/handler name. It distinguishes business flows that may process the same event for different purposes.
- `event_id`: **stable** event identifier supplied by the producer or defined by the integration contract.
- `event_type`: aids tracing and data handling.
- `processed_at`: timestamp when the database recorded successful processing.

**The primary key or unique constraint is the heart of the design.** Checking "does it exist yet?" with a `SELECT` followed by an `INSERT` **is not safe** when two transactions run concurrently. Both can see "not found." A database unique constraint is the only reliable boundary against duplicate inserts.

### 3.2. Idempotency keys must be scoped

Suppose event `evt-123` can be processed by two handlers:

~~~text
billing-projection / evt-123 -> update order status
loyalty-points     / evt-123 -> add customer points
~~~

If the inbox uses only `event_id` as a shared unique key across both flows, the first handler blocks the other. Including `consumer_name` in the unique key lets each business flow execute once independently.

`consumer_name` does not have to equal the Kafka `group.id`. Consumer groups can change during migrations or replays, whereas the idempotency boundary belongs to **business purpose**. Choose an appropriate scope and keep it stable across deployments.

### 3.3. Event ID differs from offset

A Kafka record has a transport identifier consisting of topic, partition, and offset:

~~~text
topic=payments.confirmed, partition=2, offset=1045
~~~

This triple uniquely identifies a record's position in the Kafka log, but does not equal a business event ID. The same business event may be sent twice by a producer at different offsets; deduplicating only by `topic-partition-offset` fails to recognize them as the same business event.

For well-contracted events, prefer a stable `eventId` in the payload/header. If the source provides no event ID at all, you can use the Kafka triple as a key against **redelivery of the same Kafka record**, while explicitly documenting its limitation: it does not catch duplicates published at another offset, and requires topic/cluster namespacing.

## 4. Both writes must live in the same database transaction

### 4.1. Correct sequence

~~~mermaid
flowchart TD
    A[Kafka record arrives at listener] --> B[BEGIN DB transaction]
    B --> C{Inbox INSERT succeeded?}
    C -->|Already exists| D[Duplicate: skip side effect]
    D --> E[COMMIT DB transaction]
    C -->|New insert| F[Execute business change]
    F -->|Succeeded| E
    F -->|Exception| G[ROLLBACK DB transaction]
    E --> H[Listener completes successfully]
    H --> I[Container commits Kafka offset per AckMode]
    G --> J[Throw exception for retry/recovery]
~~~

If the event is new:

1. The listener starts a database transaction through the service.
2. The service inserts the inbox key.
3. Since the insert is new, the service applies the business change.
4. The database commits **both the inbox and the business change**.
5. The listener returns normally.
6. Spring Kafka may advance the offset per its acknowledgment mode.

If the event was already processed:

1. The inbox insert conflicts with the existing key.
2. The service does not execute the side effect again.
3. The listener returns normally.
4. The container can commit the current offset to move past the duplicate record.

If the side effect fails, **the inbox INSERT must roll back as well** so the next delivery can reprocess it. Never leave an inbox row in a "processed" state when the business change did not persist.

### 4.2. Do not split into two transactions

Wrong example:

~~~java
public void process(PaymentConfirmed event) {
    inboxRepository.markProcessed(event.eventId()); // Separate transaction
    orderService.applyPayment(event);               // Separate transaction
}
~~~

If the first step commits and the second fails, redelivery sees the event already in the inbox and skips it, even though the order was never updated. The inbox then becomes a mechanism for **dropped processing**.

The reverse is also unsafe: updating the database in the first transaction and writing the inbox in the second. Crashing between the two transactions still causes duplicate effects.

## 5. Complete example with PostgreSQL and Spring Kafka

### 5.1. Illustrative schema

Example service receiving `PaymentConfirmed` to update orders:

~~~sql
CREATE TABLE orders (
    order_id VARCHAR(80) PRIMARY KEY,
    status VARCHAR(30) NOT NULL,
    paid_amount_cents BIGINT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE consumer_inbox (
    consumer_name VARCHAR(120) NOT NULL,
    event_id UUID NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);

INSERT INTO orders(order_id, status)
VALUES ('order-42', 'PENDING');
~~~

The `orders` table is a minimal example. Production may add business constraints, audit fields, and payment identifiers.

### 5.2. Event with a stable ID

~~~java
package com.example.events;

import java.util.UUID;

public record PaymentConfirmed(
    UUID eventId,
    String paymentId,
    String orderId,
    long amountCents
) {}
~~~

The producer must keep `eventId` unchanged when resending **the same logical event**. If the producer generates a fresh UUID on every retry, the inbox treats each as a distinct event and cannot deduplicate as intended.

`paymentId` can serve as an additional business idempotency key—for instance, ensuring a payment is recorded once even if the source emitted two event IDs. Idempotency contracts must reflect business semantics rather than relying solely on producer mechanics.

### 5.3. Spring Boot consumer configuration

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: billing-inbox
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.events
        spring.json.value.default.type: com.example.events.PaymentConfirmed
    listener:
      ack-mode: record
~~~

`enable-auto-commit: false` lets the Spring Kafka listener container coordinate commits based on processing results. With `ack-mode: record`, the container commits after each record listener completes normally.

This config covers only the consumer side. Database connections, pools, and transaction managers must be configured separately per your Spring Boot/JDBC setup. If the same application has both `KafkaTransactionManager` and a database transaction manager, specify the transaction manager used for the inbox explicitly.

### 5.4. Database transaction manager

When using JDBC with a `DataSource`, you can declare an explicitly named manager:

~~~java
@Configuration
public class DatabaseTransactionConfiguration {

    @Bean("dbTransactionManager")
    public PlatformTransactionManager dbTransactionManager(
        DataSource dataSource
    ) {
        return new DataSourceTransactionManager(dataSource);
    }
}
~~~

This bean controls the database transaction. Do not replace it with `KafkaTransactionManager` expecting SQL `INSERT`/`UPDATE` operations to form a database transaction.

If the application uses JPA, `JpaTransactionManager` can be used; ensure all inbox and business operations participate in **the same** database transaction manager.

### 5.5. Service performing insert-if-absent and side effects

~~~java
@Service
public class PaymentInboxService {

    private static final String CONSUMER_NAME = "billing-projection";

    private final JdbcTemplate jdbc;

    public PaymentInboxService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(transactionManager = "dbTransactionManager")
    public void apply(PaymentConfirmed event) {
        int inserted = jdbc.update(
            """
            INSERT INTO consumer_inbox (
                consumer_name, event_id, event_type
            )
            VALUES (?, ?, ?)
            ON CONFLICT (consumer_name, event_id)
            DO NOTHING
            """,
            CONSUMER_NAME,
            event.eventId(),
            "PaymentConfirmed"
        );

        if (inserted == 0) {
            // This event already completed for this consumer logic.
            return;
        }

        int updated = jdbc.update(
            """
            UPDATE orders
            SET status = 'PAID',
                paid_amount_cents = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE order_id = ? AND status = 'PENDING'
            """,
            event.amountCents(),
            event.orderId()
        );

        if (updated != 1) {
            throw new IllegalStateException(
                "Order cannot transition to PAID: " + event.orderId()
            );
        }
    }
}
~~~

This uses PostgreSQL SQL with `ON CONFLICT ... DO NOTHING` and Java text blocks; the project requires a Java version supporting text blocks. Key points:

- The unique constraint decides whether the event has already been processed.
- The inbox `INSERT` and order `UPDATE` run in **the same transaction** via `@Transactional`.
- Duplicate events return early without updating the order a second time.
- If the `UPDATE` fails, the exception rolls back the newly inserted inbox row as well.
- When both the `UPDATE` and transaction commit succeed, the inbox record becomes durable proof of processing.

The `status = 'PENDING'` condition is only an illustrative rule. A real system must distinguish an order already paid by **the same payment** from an invalid state caused by a different event. Never assume every `updated == 0` is a duplicate.

### 5.6. Keep the listener thin

~~~java
@Component
public class PaymentListener {

    private final PaymentInboxService service;

    public PaymentListener(PaymentInboxService service) {
        this.service = service;
    }

    @KafkaListener(
        topics = "payments.confirmed",
        groupId = "billing-inbox"
    )
    public void onPayment(PaymentConfirmed event) {
        service.apply(event);
    }
}
~~~

The listener calls a separate Spring bean so `@Transactional` runs through the proxy. When `apply()` returns normally, the database transaction has committed along the normal synchronous call path; only then does the listener return so the container advances the Kafka offset.

If the database errors, the exception propagates through the listener to the Spring Kafka error handler. Never catch the exception, log it, and return normally, or the container may treat the record as succeeded and commit the offset.

### 5.7. Runtime execution flow

~~~text
Kafka: PaymentConfirmed(eventId = e1, orderId = order-42)
      |
      v
Listener -> PaymentInboxService.apply()
      |
      v
BEGIN DB transaction
  INSERT inbox(billing-projection, e1) -> inserted 1
  UPDATE orders(order-42) -> PAID
COMMIT DB
      |
      v
Listener returns
      |
      v
Spring Kafka commits offset
~~~

If the record is redelivered:

~~~text
Kafka: PaymentConfirmed(eventId = e1)
      |
      v
BEGIN DB transaction
  INSERT inbox(billing-projection, e1)
    ON CONFLICT DO NOTHING -> inserted 0
  Skip business update
COMMIT DB
      |
      v
Listener returns -> offset can advance
~~~

## 6. Why is INSERT before UPDATE still safe?

One might worry that "INSERT inbox before UPDATE" marks the event processed before the side effect succeeds. That is only dangerous if the two operations **commit separately**.

Inside a single database transaction, neither change is committed externally until the transaction completes. If the `UPDATE` fails and the transaction rolls back, the inbox row disappears too.

~~~text
Transaction T1:
  INSERT inbox e1    (uncommitted)
  UPDATE orders      (exception)
  ROLLBACK T1
       |
       +-- inbox e1 does not exist
       +-- orders is not partially updated
~~~

Thus, the safety guarantee comes from **atomic database commit**, not the order of `INSERT`/`UPDATE` by itself.

If the service makes an external call such as an HTTP payment charge between two SQL statements, a database rollback cannot undo the HTTP request already sent. An inbox alone does not guarantee exactly-once for side effects outside that transaction; you need external-service idempotency keys, workflows/sagas, or dedicated design.

## 7. Concurrent duplicates and unique constraints

### 7.1. Why is SELECT before INSERT insufficient?

Concurrency-unsafe pattern:

~~~java
if (!inboxRepository.existsById(eventId)) {
    orderService.apply(event);
    inboxRepository.save(eventId);
}
~~~

Two listeners in different consumer groups or two concurrent threads processing the same event can both read "not found," both run the side effect, and only then attempt to write the inbox.

~~~text
T1: SELECT inbox e1 -> not found
T2: SELECT inbox e1 -> not found
T1: UPDATE order
T2: UPDATE order
T1: INSERT inbox e1
T2: INSERT inbox e1 -> conflict (too late)
~~~

If the side effect happens outside the transaction or transaction boundaries are split, the data may already have been updated twice.

### 7.2. Atomic INSERT with uniqueness

With `INSERT ... ON CONFLICT DO NOTHING`, the database serializes key contention. If T1 inserted `e1` and has not committed yet, T2 waits or resolves the conflict according to T1's transaction outcome:

- T1 commits: T2 inserts nothing and observes a duplicate.
- T1 rolls back: T2 can insert `e1` and perform processing itself.
- If a transaction hits a deadlock/timeout or other DB error, the listener must throw so it retries; do not treat every SQL error as a duplicate.

This pattern is safer than "SELECT then INSERT" because the database makes the first-processing decision atomically.

### 7.3. Additional business keys when producers may emit different event IDs for duplicates

Suppose a payment `pay-99` is sent as two events with IDs `e1` and `e2`:

~~~text
eventId = e1, paymentId = pay-99
eventId = e2, paymentId = pay-99
~~~

An inbox keyed by event ID will treat `e1` and `e2` as two distinct events. If business rules require "a payment must be recorded only once," add a unique constraint on `payment_id` or an appropriate ledger transaction ID, or design producers to keep event IDs stable.

**An inbox deduplicates by the chosen key.** It cannot automatically recognize two payloads with different IDs as the same business action.

## 8. Kafka offset commit comes after database commit

A common setup is `enable-auto-commit=false` and a suitable container ack mode, such as `RECORD`.

Sequence:

~~~mermaid
sequenceDiagram
    participant B as Kafka broker
    participant L as Listener container
    participant S as Inbox service
    participant D as Database

    B-->>L: Record offset 70
    L->>S: apply(event)
    S->>D: BEGIN + INSERT inbox
    S->>D: UPDATE business data
    S->>D: COMMIT DB
    D-->>S: Commit OK
    S-->>L: Service returns
    L->>B: Commit next offset 71
    B-->>L: Commit result
~~~

**The committed offset is the next position to read**. After processing offset 70, Kafka typically commits offset 71.

If the DB commit succeeds and the Kafka commit fails, record 70 may be redelivered. Because the inbox row already exists, the business update does not run again.

If the DB commit fails, the service throws an exception and the listener does not report success. The error handler can retry or recover per policy.

Never call `Acknowledgment.acknowledge()` before the database transaction commits. Doing so lets the Kafka offset advance before side effects are durably persisted.

## 9. Critical crash window table

| Failure point | Inbox state | Business state | On redelivery |
|---|---|---|---|
| Before starting DB transaction | Absent | Unchanged | Processed as new |
| After inbox `INSERT`, before `UPDATE` | Rolled back with DB transaction | Uncommitted | Reinserted and reprocessed |
| After `UPDATE`, before DB `COMMIT` | Rolled back with DB transaction | Uncommitted | Reprocessed |
| After DB `COMMIT`, before Kafka offset `COMMIT` | Present | Committed | Duplicate skipped |
| After Kafka offset `COMMIT` | Present | Committed | Normally not redelivered in same group, unless replayed intentionally |
| Kafka commit timeout with unknown outcome | Present | Committed | If redelivered, skipped by inbox |
| Producer resends stable event ID at another offset | Present | Committed | Duplicate skipped |

Key takeaway: Kafka can still invoke the listener multiple times. For a given event ID and consumer logic, only the first attempt is allowed to execute the database side effect; subsequent attempts merely confirm it already completed.

## 10. How does Inbox differ from Outbox?

Their names sound similar, yet their data directions are opposite.

| Pattern | Direction | Primary problem | Transaction boundary |
|---|---|---|---|
| **Inbox** | Kafka → consumer → DB | Prevent repeated side effects on redelivery | Inbox row + business update in the same DB transaction |
| **Outbox** | DB → Kafka | Prevent losing events to publish after DB commit | Business update + outbox row in the same DB transaction |

### 10.1. Inbox receives from Kafka

~~~text
Kafka -> Listener -> DB transaction
                      |
                      +-- INSERT inbox(eventId)
                      +-- UPDATE domain table
~~~

If the database commits while the Kafka offset stays uncommitted, redelivery is deduplicated by the inbox.

### 10.2. Outbox publishes to Kafka

~~~text
Business API -> DB transaction
                  |
                  +-- UPDATE domain table
                  +-- INSERT outbox(event)
                         |
                         v
                  Outbox publisher -> Kafka
~~~

If the outbox publisher sends the event and crashes before marking it sent, it can republish. Hence downstream consumers typically need an inbox/idempotency.

### 10.3. Using both in the same service

When a consumer both updates a database and must emit a follow-up Kafka event, you can use:

~~~mermaid
flowchart LR
    K[Kafka input] --> L[Listener]
    L --> T[Database transaction]
    T --> I[Inbox]
    T --> D[Domain tables]
    T --> O[Outbox]
    O --> P[Outbox publisher]
    P --> Q[Kafka output]
~~~

Within **the same DB transaction**, the service inserts into the inbox, updates domain tables, and inserts into the outbox. If the transaction rolls back, all three roll back together. The outbox publisher sends the output record afterward; if it sends duplicates, downstream uses the event ID to deduplicate.

This combined pattern bridges a Kafka input into a database and out to another Kafka message without relying on XA across Kafka and SQL. It remains at-least-once at transport boundaries, so idempotency stays essential.

## 11. Designing an inbox with PENDING / PROCESSED states

Some applications run long or multi-stage jobs. An inbox table can be designed with statuses:

~~~sql
CREATE TABLE consumer_inbox_jobs (
    consumer_name VARCHAR(120) NOT NULL,
    event_id UUID NOT NULL,
    status VARCHAR(20) NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMPTZ,
    error_message TEXT,
    PRIMARY KEY (consumer_name, event_id),
    CHECK (status IN ('PENDING', 'PROCESSING', 'PROCESSED', 'FAILED'))
);
~~~

In this case, **never treat "row already exists" as "business work already finished."**

If the listener writes `PENDING`, commits the offset, and another worker processes later, the inbox acts as a **durable work queue**, no longer a simple `PROCESSED` marker. You must add:

- Worker claims/leases or locks to prevent concurrent processing of the same job.
- Retries, timeouts, and recovery for stuck `PROCESSING` jobs.
- Durability before committing the Kafka offset.
- Distinguishing `PENDING`/`PROCESSING`/`PROCESSED` when duplicates arrive.
- Job limits and backpressure when workers fall behind.

If you only need a short idempotent database update, an inbox schema storing only completed events within **a single transaction** is usually much simpler.

## 12. Choosing the deduplication key

No single key fits every flow. Define when two business events are considered "the same."

### 12.1. Event ID

Suitable when the producer guarantees a unique `eventId` that stays unchanged across retries of the same event.

~~~text
consumer_name = billing-projection
event_id      = 3fef7c3a-...
~~~

### 12.2. Business operation ID

When recording payments, `paymentId` or `transactionId` from a payment provider can serve as an additional constraint. An operation ID represents an action that must not be applied twice, even if the upstream provider generated two distinct message IDs.

### 12.3. Source topic-partition-offset

You can use:

~~~text
source_cluster + topic + partition + offset
~~~

This helps when the source lacks an event ID and the goal is deduplicating **the exact same Kafka record** on redelivery. However, if the same business event is republished at a new offset, this key changes and cannot prevent logical duplicates.

### 12.4. Event version and sequential updates

One aggregate can have multiple valid events:

~~~text
Order-42 Created, version 1
Order-42 Paid,    version 2
Order-42 Shipped, version 3
~~~

Never use `orderId` alone as the inbox key, because it would block subsequent valid events. Use event IDs or `(aggregateId + eventVersion)` pairs if producers maintain proper version semantics.

If strict ordering and late-event handling are needed, an inbox alone is insufficient; enforce version/state transitions in the database.

## 13. Transaction isolation and write contention

### 13.1. READ COMMITTED is usually enough for unique inserts

In PostgreSQL, a unique constraint and `INSERT ... ON CONFLICT DO NOTHING` provide an atomic barrier against inserting the same key twice. `SERIALIZABLE` is not strictly required merely to enforce inbox uniqueness.

However, complex domain updates may require specific isolation, optimistic locking, row locking, or business constraints. An inbox only guarantees one event ID does not run its side effect twice; it does not resolve races between **two different events** updating the same order concurrently.

### 13.2. Deadlocks and transient SQL errors

If the database returns a deadlock, serialization failure, or timeout, the transaction may roll back. The listener must propagate the exception so Spring Kafka retries appropriately.

Do not catch every `DataAccessException` and treat it as a duplicate. Valid duplicates are determined by the atomic insert/unique constraint result; other database errors must be classified and handled.

### 13.3. One event seen by different consumers simultaneously

Within one Kafka group, a partition is normally owned by one consumer at a time. Yet the same logical event can still arrive via multiple groups, retry topics, replays, or duplicate publishes. Unique constraints protect the database even when two independent transactions try to process the same event simultaneously.

## 14. Spring @Transactional pitfalls

### 14.1. Self-invocation

With proxy-based Spring transactions, a `@Transactional` method called from another method **on the same object** can bypass the proxy, so transaction advice never runs.

Example not to rely on:

~~~java
@Service
public class InboxHandler {

    public void onEvent(PaymentConfirmed event) {
        applyInTransaction(event); // Internal call on same object
    }

    @Transactional
    public void applyInTransaction(PaymentConfirmed event) {
        // INSERT inbox + UPDATE business
    }
}
~~~

Extract the transactional service into a separate bean called by the listener through a Spring proxy, or use `TransactionTemplate` for explicit boundaries.

### 14.2. Picking the wrong transaction manager

An application may have `KafkaTransactionManager` alongside `JpaTransactionManager` or `DataSourceTransactionManager`.

If `@Transactional` does not specify a manager, it may pick an unintended default manager. Inbox and domain updates must share **the same database transaction**; using `KafkaTransactionManager` does not manage JDBC/JPA transactions.

Specify the manager explicitly on the service or intentionally configure the default transaction manager.

### 14.3. Checked exceptions and rollback rules

By default, Spring `@Transactional` normally rolls back on unchecked exceptions and `Error`. For checked exceptions, configure `rollbackFor` if rollback is desired.

~~~java
@Transactional(
    transactionManager = "dbTransactionManager",
    rollbackFor = Exception.class
)
public void applyWithCheckedException(PaymentConfirmed event)
        throws Exception {
    // INSERT inbox + UPDATE domain
}
~~~

Never catch an exception and return normally before Spring decides on rollback. If intentionally recovering from an error, ensure data remains consistent and never mark an event `PROCESSED` while side effects remain incomplete.

### 14.4. Async threads

Spring transaction synchronization is normally thread-bound. If a service starts a database transaction and dispatches side effects to an executor thread, do not assume that task joins the same transaction.

~~~java
@Transactional(transactionManager = "dbTransactionManager")
public void unsafe(PaymentConfirmed event) {
    inboxRepository.insert(event.eventId());
    executor.execute(() -> orderRepository.markPaid(event.orderId()));
}
~~~

The listener thread's transaction may commit the inbox row before the background task runs the `UPDATE`. If the task fails or the process stops, redelivery is misidentified as a duplicate and skipped.

If async processing is mandatory, use a durable queue/job state with proper leases, retries, and recovery semantics rather than a raw in-memory background task.

## 15. Error handling, retries, and DLT

### 15.1. Database exceptions must propagate out of the listener

When the service throws an exception, the container hands the record to the error handler. `DefaultErrorHandler` can retry per `BackOff` or recover the record after exhausting retries.

Basic example:

~~~java
@Bean
public DefaultErrorHandler defaultErrorHandler(
    KafkaTemplate<Object, Object> kafkaTemplate
) {
    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(kafkaTemplate);

    FixedBackOff backOff = new FixedBackOff(1_000L, 3L);

    return new DefaultErrorHandler(recoverer, backOff);
}
~~~

This example creates a bounded retry policy and a DLT-publishing recoverer. Wire the error handler into the actual listener container factory and configure matching serializers/ACLs/DLT topics.

If a record fails due to temporary database unavailability, retrying makes sense. If the payload permanently violates schemas or domain rules, infinite retries accomplish nothing; classify it as non-retryable and route to recovery.

### 15.2. Inbox when a record goes to the DLT

If the database change fails and the transaction rolls back, no `PROCESSED` inbox row exists either. After retries exhaust, the error handler can publish the record to the DLT and let the container advance the source offset per policy.

Do not confuse:

- A record **successfully processed by business logic**: inbox holds a `PROCESSED` marker alongside the side effect.
- A record **routed to the DLT**: does not necessarily have a `PROCESSED` inbox entry; requires dedicated investigation/replay.

If the DLT is replayed after fixing the bug, the event can be reprocessed with the same event ID. If the earlier database side effect actually committed, the inbox blocks duplicates. If the DB had rolled back, the inbox permits fresh processing.

### 15.3. DLT publishing can also fail

If publishing to the DLT fails, never silently treat the record as safely recovered. Check send results, timeouts, recoverer behavior, and source offset commits.

Never insert an inbox row to "stop a failing record from coming back" without storing the error in a durable, operated recovery store. That would silently drop events from the pipeline.

### 15.4. Retry topics and ordering

With non-blocking retries, failing records move to retry topics while subsequent records on the source topic continue. This can alter business completion order.

An inbox prevents duplicate processing by event ID, **not out-of-order execution**. If two distinct events must apply in version, state-machine, or aggregate order, enforce dedicated update conditions and domain constraints.

## 16. Inbox with batch listeners

Batch listeners receive multiple records per invocation and may write to the database in batches. An inbox remains valuable, though partial-failure handling must be explicit.

Suppose a batch contains:

~~~text
A: eventId=e1
B: eventId=e2
C: eventId=e3
~~~

Two approaches exist:

**One database transaction for the entire batch:** insert inbox and update domain for A, B, and C, then commit together. If one item fails, roll back the entire batch and retry. Database side effects are never partially committed; larger batches increase lock duration and transaction time.

**One database transaction per record:** process each item via a separate transactional service. When item B fails, A may already be committed and C untouched. The error handler must know which item failed—for instance via `BatchListenerFailedException`—to manage offset progress accurately. A may be redelivered, and the inbox skips the duplicate.

Do not assume a batch has a single offset: a batch can span multiple partitions, and committed offsets must be tracked per topic-partition. If processing items in parallel within a batch, never commit past incomplete records.

## 17. Combining with Kafka transactions and Exactly-once

Kafka provides producer transactions and coordinates output Kafka records with source consumer offsets in consume–process–produce. That supports **Kafka-scoped** exactly-once semantics when transactions and consumer isolation are configured properly.

An inbox solves a different problem: **idempotent database side effects** when a Kafka record is redelivered.

~~~text
Kafka input
    |
    v
Spring Kafka listener
    |
    +--- Database transaction:
    |       INSERT inbox
    |       UPDATE business state
    |
    +--- Kafka offset commit
~~~

This path has no single transaction spanning both SQL and Kafka, yet the inbox enables at-least-once processing without repeating database side effects for the chosen key.

If the consumer both updates SQL and sends Kafka output, combine inbox + outbox in the same DB transaction. Never merely enable `KafkaTransactionManager` and claim database and Kafka commit atomically like XA.

## 18. Inbox retention and cleanup

An inbox grows steadily as processed event volume increases. You need a retention policy, yet **purging the inbox too early strips away idempotency protection**.

Example:

~~~text
Day 1: e1 is processed and inbox records e1
Day 7: cleanup deletes e1
Day 8: e1 is replayed from Kafka / DLT
Day 8: inbox no longer has e1 -> business logic may run a second time
~~~

Retention should be based on:

- Kafka topic retention and realistic replay windows.
- Retention of DLT and retry topic records.
- Likelihood of producers resending older events.
- Business window requiring duplicate protection.
- Audit requirements, storage cost, and personal data rules.
- Migrations or historical data backfills.

If the system allows multi-year replays, you cannot keep inbox entries for one week and still promise unbounded deduplication. You may need long-term idempotency key storage, searchable archives, or durable domain-level unique constraints.

### 18.1. Avoid storing unnecessary sensitive payloads

An inbox usually only needs consumer scope, event ID, type, and processed timestamp. There is rarely a need to store full payloads or sensitive data in this table.

If auditing/reconciliation is needed, store minimal metadata and enforce retention/access controls per security requirements. An inbox table storing every event's full payload expands security risk surface and storage cost.

### 18.2. Optimizing large tables

At high throughput:

- Match primary key/unique index column order to query patterns.
- Monitor `INSERT` latency, index size, and lock contention.
- Separate reporting queries from the hot transactional inbox table.
- Partition or prune tables when volume truly demands it.
- Be cautious with database partitioning because some engines restrict uniqueness across partitions.
- Set alerts on abnormal storage growth.

Never drop the unique constraint for speed, because it is the inbox's primary duplicate-prevention mechanism.

## 19. Observability for the inbox

Tracking both Kafka and the database shows whether records were processed fresh, skipped as duplicates, or failed.

| Signal | Meaning |
|---|---|
| Inbox insert success | Count of events received and processed for the first time |
| Inbox conflict / duplicate count | Number of times already-processed events were redelivered |
| DB transaction commit/rollback | Outcome of atomic inbox + domain update |
| Business processing duration | Latency of side effects |
| Inbox insert latency | Index/lock/contention health |
| Consumer lag by partition | Kafka consumption progress |
| Kafka offset commit errors | Potential upcoming redeliveries |
| Listener retries | Transient DB/downstream errors |
| DLT publication success/failure | Recovery status when events cannot be processed |
| Replay count | Intentionally re-read events |

For tracing, log `eventId`, consumer name, topic, partition, offset, outcome (`processed`/`duplicate`/`failed`), and correlation ID.

Avoid using event ID as a metric label because of high cardinality. Keep event IDs in structured logs or traces, and limit metric labels to low-cardinality values like consumer, event type, and outcome.

If duplicate counts spike suddenly, investigate crash/rebalances, offset commit failures, producer replays, and offset policy changes; do not assume every duplicate indicates an inbox bug.

## 20. Common design mistakes

**Putting inbox INSERT and business UPDATE in two transactions:** if one commits and the other rolls back, the system either drops processing or repeats side effects.

**SELECT before INSERT without a unique constraint:** vulnerable to race conditions when two concurrent transactions process the same event.

**Using unstable event IDs:** producer generates a new UUID on every retry, so the inbox cannot deduplicate the business event.

**Inbox key containing only orderId:** blocks subsequent valid events for the same order.

**Using Kafka offset as business event ID:** fails to stop duplicates published at other offsets.

**Acknowledging Kafka before DB commit:** crashing after ack lets the group skip records not yet persisted durably.

**Catching exceptions and returning normally:** Spring Kafka may commit the offset even when the database failed.

**Calling `@Transactional` via self-invocation:** the database transaction may never open as expected.

**Using `@Transactional` with `KafkaTransactionManager`:** does not turn JDBC/JPA updates into a database transaction.

**Catching unique constraint errors and rolling back incorrectly:** use an atomic `INSERT` returning duplicate status cleanly; do not treat every SQL exception as a duplicate.

**Dispatching side effects to an async executor after writing inbox:** committing the inbox before side effects persist increases risk of dropped work.

**Treating any inbox row as duplicate even when status is not `PROCESSED`:** easily skips unfinished jobs in multi-state inbox designs.

**Purging inbox entries before the DLT replay window:** older redelivered records can re-run side effects.

**Assuming an inbox protects non-idempotent HTTP side effects:** database rollbacks do not undo external API calls already made.

**Assuming an inbox guarantees ordering:** one aggregate can have multiple event IDs arriving out of order unless version/state checks exist.

## 21. Testing process for the Inbox pattern

Do not test only the happy path. Actively inject faults right at commit boundaries.

### 21.1. First processing

1. Generate an unseen event ID.
2. Send the record to the test topic.
3. Verify the domain row updates properly.
4. Verify the inbox row holds the expected consumer name and event ID.
5. Verify the Kafka offset commits after the listener finishes.

### 21.2. Redelivery with the same event ID

1. Resend the event with the same event ID at a different offset.
2. Verify the inbox `INSERT` indicates a duplicate.
3. Verify the business side effect does not run a second time.
4. Verify the consumer advances past the duplicate record cleanly.

### 21.3. Database rollback

1. Inject an error after the inbox `INSERT` and before business `UPDATE`/commit.
2. Verify the database transaction rolls back.
3. Verify no `PROCESSED` inbox row remains for that event.
4. Verify domain state was not modified.
5. Let the retry succeed; verify inbox and domain commit together.

### 21.4. Crash after DB COMMIT, before offset commit

1. Let the listener complete the DB transaction.
2. Stop the process in a controlled way before the source offset commits.
3. Restart the consumer with the same group ID.
4. Verify the event is redelivered.
5. Verify the inbox skips the duplicate and domain state is not updated twice.

### 21.5. Two consumers processing a duplicate concurrently

1. Emit the same event ID through two independent test consumer paths.
2. Have two DB transactions contend on the same unique key.
3. Verify only one transaction applies the business update.
4. Verify the other transaction observes a duplicate or retryable error cleanly without double effects.

### 21.6. DLT and replay

1. Make an event fail permanently until retries exhaust.
2. Verify the record lands in the DLT per policy.
3. Fix the data/root cause in the test environment.
4. Replay the event with the same event ID.
5. If business work had not committed earlier, verify it succeeds now.
6. If the side effect had already committed, verify the inbox prevents repetition.

Integration tests can use Testcontainers for Kafka and PostgreSQL, or equivalent test infrastructure. The goal is verifying **database state and Kafka offsets**, not just listener invocation counts.

## 22. When is the Inbox pattern suitable?

An inbox is especially suitable when:

- A Spring Kafka consumer updates a SQL database.
- Records carry a stable event ID.
- Business logic cannot tolerate repeated side effects on Kafka redelivery.
- The database enforces transactions and unique constraints.
- The application needs replay/recovery from Kafka or DLTs.
- Deduplication scope can be defined per consumer logic.

A simple inbox alone may not be enough when:

- The primary side effect is an HTTP call or system without idempotency support.
- One event must coordinate multiple resources that cannot commit together.
- Business rules enforce strict version ordering and events can arrive out of order.
- Multi-day retries are needed without holding work inside the listener container.
- The consumer runs long background tasks needing independent leases/recovery.
- Inbox retention is shorter than possible replay horizons.

In those cases, use the inbox as part of a broader architecture: durable job queues, outboxes, sagas, business idempotency keys, state machines, or reconciliation depending on requirements.

## 23. Production rollout principles

1. **Every event has a stable ID**; define consumer scope clearly.
2. **Use database unique constraints**, never just `SELECT` existence checks.
3. **Insert the inbox and mutate domain state in the same database transaction**.
4. Treat an event as `PROCESSED` only once that transaction commits successfully.
5. Let the listener return normally **after the database commit**, then let the container commit the offset.
6. Never acknowledge early or swallow exceptions causing Kafka to advance offsets wrongly.
7. Keep the transactional service on a Spring bean called via proxy and select the right database transaction manager.
8. Add business keys when two distinct event IDs can represent the same operation.
9. Route permanent failures to DLT/confirmed recovery; never write `PROCESSED` inbox rows for unhandled failures.
10. When emitting Kafka output after a DB update, consider combining **inbox + outbox**.
11. Retain inbox records long enough for replay horizons, DLTs, and business requirements.
12. Monitor duplicate counts, DB rollbacks, Kafka commit failures, and consumer lag.
13. Test crashes after DB commit before Kafka offset commit, as well as concurrent duplicates.

**Conclusion:** The Inbox pattern does not try to prevent Kafka from delivering an event multiple times. It ensures an event with a stable identifier produces its business side effect only once within a database transaction guarded by a unique constraint. In Spring Kafka, the standard design is **commit database first, commit offset second**, accepting redelivery and using the inbox to make redelivery safe. When Kafka outputs, HTTP side effects, long-term replays, or async processing are also involved, extend the architecture with outboxes, idempotency keys, and corresponding recovery mechanisms.
