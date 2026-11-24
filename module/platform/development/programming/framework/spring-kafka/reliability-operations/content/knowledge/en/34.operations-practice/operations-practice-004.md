# Synchronizing Kafka with a Database in Spring Kafka: Transactions, Inbox, Outbox, and Recovery

## 1. Real-World Problem

A **Spring Kafka** application rarely just consumes or produces messages. It also **reads and writes a database** to update business state. When both systems participate in one processing flow, the most important question is:

> If Kafka succeeds while the database fails, or the database commits while Kafka has not confirmed yet, how does the system avoid losing data and avoid creating duplicate business side effects?

For example, a payment service receives a `PaymentApproved` event:

```text
                    Kafka topic
                 payment-approved
                        |
                        v
                @KafkaListener
                        |
                        v
                PostgreSQL
              payments / ledger
                        |
                        v
               Kafka topic
              payment-completed
```

In an ideal run:

1. The consumer receives the event from Kafka.
2. The application validates it and updates PostgreSQL tables.
3. The database commits.
4. The consumer commits the offset.
5. The application sends the resulting event to Kafka.

However, the process can crash at **any step**. A network timeout also does not prove the operation on the other side failed. Therefore, implementing "Kafka-database synchronization" is never as simple as adding `@Transactional` to a listener.

**Lesson goal:** build a data model and operational workflow that withstand retries, replays, rebalances, crashes, duplicates, and infrastructure outages while understanding the limits of "exactly once" claims.

**Example scope:** Spring Boot 3.x, Spring Kafka 3.x, Java 17+, PostgreSQL, and a Kafka broker compatible with this stack. Code snippets are illustrative components to be integrated with matching configuration, DTOs, and schemas in a real project.

## 2. Three Synchronization Directions to Distinguish

| Direction | Scenario | Primary Risk | Common Pattern |
|---|---|---|---|
| **Kafka → Database** | Consume events to update business tables | DB commits, offset uncommitted → redelivery | Idempotent consumer + **transactional inbox** |
| **Database → Kafka** | Persist an order, then emit an event | DB commits, Kafka send fails → lost event | **Transactional outbox** + publisher/CDC |
| **Kafka → Database → Kafka** | Consume command, persist state, emit result | Failures anywhere across the three boundaries | Inbox + DB transaction + outbox |

A solution that works for one direction is often insufficient for another. For example, `enable.idempotence=true` improves Kafka producer reliability for client/broker retries, but **does not** combine PostgreSQL and Kafka into one atomic transaction.

### 2.1. Guarantees the System Must Preserve

For an event with `eventId=evt-101`, we typically require:

- **No lost events:** once the source accepts an event, there is eventually a path to process or recover it.
- **No duplicate business effects:** delivering `evt-101` twice must not credit money twice.
- **Restartability:** mid-flight crashes must not force operators to patch offsets or data manually.
- **No silent conflicts:** two payloads sharing the same event ID must not be ignored as harmless duplicates.
- **Reconcilability:** ability to locate pending, processed, failing, or forwarded events.
- **Bounded retries:** transient errors retry under limits; invalid data does not retry forever.
- **Operational ownership:** knowing whether to inspect the DB, Kafka group, DLT, or outbox during an incident.

Requirements should be written as **business invariants**, not judged merely by a single successful listener execution.

## 3. Why Is There No Native Atomic Commit Between Kafka and a DB?

Kafka manages records, consumer group offsets, and Kafka transactions within Kafka. PostgreSQL manages tables, row locks, and transactions over JDBC. The two systems have **separate transaction coordinators and failure domains**.

Suppose you write:

```java
@Transactional
public void process(PaymentEvent event) {
    paymentRepository.apply(event);
    kafkaTemplate.send("payment-completed", event.id(), json);
}
```

`@Transactional` normally binds to a chosen `PlatformTransactionManager`, such as the PostgreSQL datasource transaction manager. It **does not automatically make** the Kafka send an atomic part of the JDBC transaction.

Two common orderings both leave a "gap":

**DB first, Kafka second:**

```text
DB COMMIT ------------------------> SEND KAFKA
      |                                  |
      +---- process dies here -----------+
               DB has data
               Kafka lacks event
```

**Kafka first, DB second:**

```text
SEND KAFKA -----------------------> DB COMMIT
      |                                  |
      +---- process dies here -----------+
             Another consumer sees event
             DB not updated
```

Even if both operations execute back-to-back in code with tiny latency, a crash can still land squarely inside that window. Never design around "both calls are so fast it probably won't happen."

### 3.1. Why Don't Kafka Transactions Solve the DB Part?

Kafka provides **transactional producers** and Kafka-to-Kafka exactly-once mechanisms within supported boundaries. Yet a Kafka transaction does not coordinate an atomic commit with PostgreSQL.

Even when an application runs a Kafka transaction alongside a DB transaction, commit order still matters; if the first commit succeeds and the second fails, the two systems diverge. Transaction synchronization patterns can narrow the failure window, but they are **not XA/2PC atomicity between Kafka and a database**.

**Practical recommendation:** when business state lives in a DB, treat the database as the source of truth for effects and use an idempotent inbox/outbox to communicate with Kafka under a well-defined **eventual consistency** model.

## 4. Case 1: Kafka → Database

Suppose topic `payment-approved.v1` contains:

```json
{
  "eventId": "evt-101",
  "sourceSystem": "payments",
  "paymentId": "pay-701",
  "version": 4,
  "status": "APPROVED"
}
```

The consumer must update the `payment_projection` table in PostgreSQL.

### 4.1. Common Failure: DB Commits, Crash Before Offset Commit

```text
1. KafkaConsumer polls offset 120
2. Listener updates PostgreSQL
3. PostgreSQL COMMIT succeeds
4. JVM dies before Kafka offset commit
5. Rebalance/restart
6. Kafka redelivers offset 120
7. Listener sees event evt-101 again
```

This is expected behavior in **at-least-once** designs, not a Kafka bug. To guarantee business state changes only once, the consumer must be **idempotent**.

### 4.2. Opposite Risk: Committing Offset Before DB Completes

```text
1. KafkaConsumer polls offset 120
2. Offset is committed as processed
3. Database transaction fails
4. JVM dies
5. Restart resumes at offset 121
6. Event at offset 120 may be skipped
```

Therefore, never commit or acknowledge offsets before business work finishes and the DB transaction commits, unless a separate mechanism durably captures the event elsewhere.

### 4.3. Safe Consumer Principles

For a record listener writing to a database:

1. Disable Kafka client auto-commit.
2. Execute business work inside **a single DB transaction** in the service.
3. Insert an **inbox key** (event ID) and update business tables **within that same DB transaction**.
4. Return normally from the listener only after the DB transaction commits; the container commits offsets per ack policy.
5. If the offset commit fails, Kafka may redeliver; the inbox skips duplicates.
6. If the DB transaction fails, let the exception propagate to the Spring Kafka error handler; never ack as succeeded.
7. For permanently invalid data, route to DLT/quarantine under explicit rules; do not retry infinitely.

## 5. Configuring the Spring Kafka Consumer for DB Processing

Example `application.yml` for a record listener:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}

    consumer:
      group-id: payment-projection-v1
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      enable-auto-commit: false
      auto-offset-reset: earliest
      properties:
        "[max.poll.records]": 100
        "[max.poll.interval.ms]": 300000

    listener:
      ack-mode: record
      concurrency: 3
```

This example targets a **single cluster** and uses String payloads for illustration. Timeout, poll, and concurrency values must be tuned against real load.

Key points to understand:

- `enable-auto-commit: false` disables the Kafka client's periodic auto-commit, while the Spring Kafka listener container still commits offsets according to **ack mode and error handling**.
- `ack-mode: record` means the container manages commits after record processing according to container semantics; the listener method must return normally only after required work completes.
- `auto-offset-reset: earliest` applies only when the group has **no valid committed offset**; it does not reset the group on every restart.
- `concurrency: 3` does not process three records from the same partition concurrently or guarantee 3x throughput; distribution depends on partition count and assignment.
- `max.poll.interval.ms` must accommodate maximum listener blocking/retry time; exceeding it triggers a rebalance.
- For records produced by a **Kafka transactional producer**, you can set `isolation.level=read_committed` if you must skip aborted transactions; this does not create atomicity with the DB.

### 5.1. Why Listeners Must Not Swallow Exceptions

Wrong:

```java
@KafkaListener(topics = "payment-approved.v1")
public void onEvent(String json) {
    try {
        service.process(json);
    } catch (Exception ex) {
        log.error("Processing failed", ex);
        // Returns normally: the container may treat processing as succeeded.
    }
}
```

If business effects did not commit yet the listener returns normally, the offset may be committed per policy and the event is lost at the business layer.

The right way is to **let exceptions propagate to the error handler**, or use a durable recovery mechanism and treat a record as complete only after recovery is confirmed:

```java
@KafkaListener(topics = "payment-approved.v1")
public void onEvent(String json) throws Exception {
    PaymentEvent event = mapper.readValue(
            json, PaymentEvent.class);

    service.applyEvent(event);
    // Return only after the service transaction has completed.
}
```

`mapper` is a Jackson `ObjectMapper`, and `service` is a Spring-managed bean. If `applyEvent` has `@Transactional`, the call must go **through the Spring proxy**, not a self-invocation on the same object that bypasses the proxy.

## 6. Transactional Inbox: Storing Event Identity Alongside Business Updates

A **transactional inbox** is a table recording processed event identities. It must share the **exact same database transaction** as the business mutation. Marking an event processed in an external cache/Redis outside the DB transaction invites this failure:

```text
Redis SET eventId=processed
          |
          v
PostgreSQL UPDATE fails / rolls back
          |
          v
Kafka redelivers event
          |
          v
Redis reports already processed -> business update lost
```

Thus, an inbox table inside the same DB holding business state is a direct, reliable choice for many systems.

### 6.1. PostgreSQL Schema

```sql
CREATE TABLE processed_kafka_events (
    source_system VARCHAR(80) NOT NULL,
    event_id VARCHAR(160) NOT NULL,
    payload_hash CHAR(64) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source_system, event_id)
);

CREATE TABLE payment_projection (
    payment_id VARCHAR(120) PRIMARY KEY,
    current_version BIGINT NOT NULL,
    status VARCHAR(40) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Where:

- `(source_system, event_id)` is the idempotency key for the **message event**.
- `payload_hash` detects **same ID with different content**, without replacing the original content itself.
- `payment_id` is the **business entity** key, not a substitute for the event ID.
- `current_version` helps reject stale updates when events represent snapshots rather than additive deltas.

`payload_hash` should be computed from a **canonical payload** or consistent byte representation. Hashing alone does not resolve semantic differences if JSON field ordering varies. If exact comparison is needed, store or retrieve the original payload version in secure audit storage.

### 6.2. DTO and Data Constraints

```java
public record PaymentEvent(
        String sourceSystem,
        String eventId,
        String paymentId,
        long version,
        String status,
        String payloadHash
) {
}
```

This event represents a **snapshot state** of a payment. If an event is actually a delta like `AddBalance(100)`, you cannot blindly apply "higher version overwrites snapshot" logic.

`payloadHash` in this example assumes upstream generates it per contract or the application recomputes it from a trusted canonical payload. **Never blindly trust hashes embedded in messages** if external sources could forge them.

### 6.3. Transactional Service Protecting Business Effects

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public final class PaymentProjectionService {

    private final JdbcTemplate jdbc;

    public PaymentProjectionService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void applyEvent(PaymentEvent event) {
        validate(event);

        int inserted = jdbc.update("""
                INSERT INTO processed_kafka_events (
                    source_system,
                    event_id,
                    payload_hash
                ) VALUES (?, ?, ?)
                ON CONFLICT (source_system, event_id)
                DO NOTHING
                """,
                event.sourceSystem(),
                event.eventId(),
                event.payloadHash());

        if (inserted == 0) {
            String existingHash = jdbc.queryForObject("""
                    SELECT payload_hash
                      FROM processed_kafka_events
                     WHERE source_system = ?
                       AND event_id = ?
                    """,
                    String.class,
                    event.sourceSystem(),
                    event.eventId());

            if (!event.payloadHash().equals(existingHash)) {
                throw new ConflictingEventException(
                        "Same event ID has different payload");
            }

            return; // Exact replay of the same event: no-op.
        }

        jdbc.update("""
                INSERT INTO payment_projection (
                    payment_id,
                    current_version,
                    status
                ) VALUES (?, ?, ?)
                ON CONFLICT (payment_id) DO UPDATE
                  SET current_version = EXCLUDED.current_version,
                      status = EXCLUDED.status,
                      updated_at = CURRENT_TIMESTAMP
                WHERE payment_projection.current_version
                      < EXCLUDED.current_version
                """,
                event.paymentId(),
                event.version(),
                event.status());
    }

    private static void validate(PaymentEvent event) {
        if (event == null
                || event.sourceSystem() == null
                || event.sourceSystem().isBlank()
                || event.eventId() == null
                || event.eventId().isBlank()
                || event.paymentId() == null
                || event.paymentId().isBlank()
                || event.payloadHash() == null
                || event.payloadHash().length() != 64
                || event.version() < 0) {
            throw new InvalidPaymentEventException(
                    "Invalid payment event");
        }
    }
}
```

`ConflictingEventException` and `InvalidPaymentEventException` are application-defined `RuntimeException`s. Production validation should also add a `status` allowlist and field-length/source checks. The snippet focuses on transactions and idempotency.

**Mandatory requirement:** `JdbcTemplate` must use the exact `DataSource` and `PlatformTransactionManager` managed by `@Transactional`. If the inbox lives in database A and the projection in database B without a shared transaction, the atomicity shown here no longer holds.

### 6.4. Why Insert the Inbox Row Before Updating the Projection?

`INSERT ... ON CONFLICT DO NOTHING` is atomic via PostgreSQL's unique constraint. When two consumers race on the same event ID, one transaction wins the insert; the other waits on or observes the outcome of the competing transaction per database semantics. Only the winning transaction proceeds to the business update.

If the business update fails and rolls back, **the inbox insert rolls back too**, so Kafka redelivery can still reprocess the event.

```text
BEGIN
  INSERT inbox(eventId)
  UPDATE payment_projection
COMMIT

If UPDATE fails:
  ROLLBACK inbox + projection
  Kafka redelivery -> safe to retry
```

Never update an in-memory cache like `seenEvents.add(eventId)` before the database and expect the cache to roll back when PostgreSQL rolls back.

### 6.5. Distinguishing Duplicates from Stale Versions

Example:

```text
eventId=evt-101, paymentId=P-9, version=4  -> apply
eventId=evt-102, paymentId=P-9, version=3  -> inbox records it, projection keeps v4
eventId=evt-101, paymentId=P-9, version=4  -> duplicate event, no-op
eventId=evt-101, paymentId=P-9, version=8  -> same event ID conflict, fail
```

For **snapshot state**, a "highest version wins" policy can work. For **ledger or financial deltas**, never skip `v3` just because `v4` arrived earlier when each delta is cumulative. In that case, detect sequence gaps, hold/quarantine out-of-order events, and apply them in strict business order.

**One business entity has many valid events**: deduplicating solely by `paymentId` would wrongly drop legitimate updates. The inbox key identifies the **event occurrence**, whereas the projection table is keyed by the business entity.

## 7. Spring Kafka Listener Invoking the Transactional Service

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public final class PaymentProjectionListener {

    private final ObjectMapper mapper;
    private final PaymentProjectionService service;

    public PaymentProjectionListener(
            ObjectMapper mapper,
            PaymentProjectionService service) {

        this.mapper = mapper;
        this.service = service;
    }

    @KafkaListener(
            topics = "payment-approved.v1",
            groupId = "payment-projection-v1")
    public void onMessage(String json) throws Exception {
        PaymentEvent event =
                mapper.readValue(json, PaymentEvent.class);

        service.applyEvent(event);
    }
}
```

Operational flow:

```text
Kafka poll
   |
   v
Listener parses event
   |
   v
Spring @Transactional service
   |
   +-- INSERT inbox
   |
   +-- UPDATE projection
   |
   +-- DB COMMIT
   |
   v
Listener returns normally
   |
   v
Container commits offset according to AckMode
```

Between `DB COMMIT` and `offset commit`, a failure window still exists. We **do not eliminate it** with the code above; we design the inbox so redelivery is safe.

### 7.1. Is Manual Acknowledgment Better?

You can use `AckMode.MANUAL`/`MANUAL_IMMEDIATE` and call `Acknowledgment.acknowledge()` **after** the transactional service returns. However, manual ack does not make the two commits atomic either.

```java
@KafkaListener(
        topics = "payment-approved.v1",
        containerFactory = "manualAckFactory")
public void onMessage(
        String json,
        Acknowledgment ack) throws Exception {

    PaymentEvent event =
            mapper.readValue(json, PaymentEvent.class);

    service.applyEvent(event);
    ack.acknowledge();
}
```

This requires `manualAckFactory` to be properly configured for manual ack mode. Never call `acknowledge()` in a `finally` block, and never ack before DB commit. Even when `acknowledge()` is called, crashes, rebalances, or commit failures still require idempotency.

For straightforward record-by-record DB processing listeners, `AckMode.RECORD` is usually easier to reason about than ad-hoc manual acks.

## 8. Crash Scenarios Table: Kafka → DB

| Failure Point | DB Committed? | Offset Committed? | After Restart | Protection Mechanism |
|---|---|---|---|---|
| Before starting DB transaction | No | No | Event reread | Retry |
| After inbox insert, before business update; transaction rolls back | No | No | Event reread | Same DB transaction |
| After business update, before DB commit; transaction rolls back | No | No | Event reread | DB atomicity |
| After DB commit, before offset commit | Yes | No | Event may be reread | Inbox idempotency |
| Offset commit succeeded | Yes | Yes | Usually continues at next offset | Commit policy + audit |
| DB commits, process dies while offset commit outcome unknown | Yes | Unknown | May replay or advance | Inbox idempotency |
| DLT publish / offset recovery fails | Depends on error | Depends on container | May retry/replay | Proper recoverer failure + monitoring |

**Core principle:** "Kafka redelivered the event" must never cause a second business side effect. This requires DB unique constraints and transactions, not just an "already processed" log line.

## 9. Retries, Poison Messages, and DLT

When the business service throws an exception, the listener container delegates handling to the configured error handler.

Not every error should be retried:

- **Transient:** lost DB connection, deadlock, brief broker/network blip → bounded retry with backoff.
- **Permanent:** JSON missing required fields, unsupported event version, same event ID with different payload → quarantine/DLT or fail per policy.
- **Unknown:** code bugs, widespread schema mismatches → usually fail/alert rather than hiding behind `catch(Exception)`.

Example `DefaultErrorHandler`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.util.backoff.FixedBackOff;

@Bean
DefaultErrorHandler paymentErrorHandler(
        KafkaTemplate<Object, Object> dltKafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(dltKafkaTemplate);

    DefaultErrorHandler handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L)
    );

    handler.addNotRetryableExceptions(
            InvalidPaymentEventException.class,
            ConflictingEventException.class
    );

    return handler;
}
```

`InvalidPaymentEventException` and `ConflictingEventException` are application-defined business classes. `dltKafkaTemplate` must target the proper DLT cluster, topic, serializers, and ACLs. This snippet illustrates policy, **not every DLT publish guarantee**.

### 9.1. Offsets After DLT

Once the recoverer handles a failing record per error handler semantics, the container can advance past the failing message and commit the offset as configured. That means:

- The record is **no longer processed in the main flow**.
- The DLT/quarantine must become an **owned recovery path**.
- If DLT publishing fails, let the handler/recoverer fail visibly rather than logging and dropping the record.
- If DLT records are replayed, the replay must respect idempotency and business ordering.

Do not assume DLT means "zero data loss" without verifying send results, topic retention, and retrieval procedures.

### 9.2. Deserialization Errors Occur Before the Listener

If the Kafka value deserializer cannot construct an object, the listener method is **never invoked**. Spring Kafka provides `ErrorHandlingDeserializer` to route deserialization failures into the container's error handling path. Therefore, tests that only mock `@KafkaListener` miss real payload failure modes.

For untrusted JSON, payload size limits, trusted packages/type headers, and schema compatibility are separate concerns that must be designed explicitly.

## 10. Case 2: Database → Kafka

Suppose a REST API receives an order creation command:

```text
POST /orders
    |
    v
OrderService
    |
    +-- INSERT orders
    |
    +-- KafkaTemplate.send("order-created")
```

A naive implementation:

```java
@Transactional
public void createOrder(Order order) {
    jdbc.update("INSERT INTO orders ...");
    kafkaTemplate.send("order-created.v1", order.id(), payload);
}
```

Risks:

- `send` is asynchronous; the method can return before the broker ACKs.
- The database rolls back while Kafka already emitted the event.
- The database commits, then the app crashes before sending the event.
- The broker ACK is lost; the publisher retries and creates duplicate business events.
- Even if enabled, a Kafka transaction and DB transaction still lack a shared atomic coordinator.

**Common solution:** transactional outbox.

## 11. Transactional Outbox: Principles

An **outbox** is a table holding events to publish to Kafka, written **in the same DB transaction as the business state**.

```text
           HTTP command / business action
                       |
                       v
                 DB transaction
               +---------------+
               | orders        |
               | outbox_events |
               +---------------+
                       |
                    COMMIT
                       |
                       v
             Outbox Publisher / CDC
                       |
                       v
                  Kafka broker
                       |
                       v
                Downstream consumer
```

Sharing the same database transaction means:

- If the business update rolls back, the outbox insert rolls back.
- If the business update commits, the outbox event is durably persisted too.
- If the publisher is down, the outbox keeps the event pending for later delivery.
- If the publisher sends successfully and crashes before marking delivered, the event may be resent. Downstream consumers must be idempotent.
- Events may be published **slightly after** the DB commit, so the system operates under **eventual consistency**.

An outbox **does not by itself create exactly-once publishing**. It guarantees a durable source for retries, typically yielding **at-least-once** behavior.

## 12. PostgreSQL Schema for the Outbox

```sql
CREATE TABLE orders (
    order_id VARCHAR(120) PRIMARY KEY,
    status VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE outbox_events (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id VARCHAR(120) NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    topic_name VARCHAR(160) NOT NULL,
    message_key VARCHAR(160) NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    claimed_until TIMESTAMPTZ NULL,
    claim_token UUID NULL
);

CREATE INDEX idx_outbox_pending
ON outbox_events (next_attempt_at, created_at, event_id)
WHERE published_at IS NULL;
```

Field meanings:

- `event_id`: **stable event identifier**, propagated to Kafka for downstream deduplication.
- `aggregate_id` and `message_key`: typically share the business entity key for stable partition routing.
- `created_at`: supports monitoring event age and ordering in the publisher.
- `published_at`: reflects that the application confirmed delivery per policy.
- `attempts` and `next_attempt_at`: drive bounded retries and backoff.
- `claimed_until` and `claim_token`: coordinate multiple competing publishers via leases.

**Do not store personal data or credentials in payloads unless permitted by the topic contract.** For sensitive payloads, enforce schemas, encryption, retention, and ACLs. The outbox is a data store requiring backups and retention management, not an ephemeral in-memory queue.

### 12.1. Why Does the Outbox Need a Fixed Event ID?

If the publisher generates `UUID.randomUUID()` every time it resends an outbox row, the same business event gets **different IDs** across retries. Downstream consumers cannot tell it is a replay of the same event.

Generate `eventId` when the business transaction creates the event, persist it in the outbox, and reuse **that exact ID** on every publish attempt.

## 13. Writing Business State and Outbox in One Transaction

Example input record:

```java
public record CreateOrderCommand(
        String requestId,
        String orderId
) {
}
```

`requestId` identifies the order creation command. In production, add logic preventing duplicate handling of two requests with the same ID per business contract; `orderId` also has a unique constraint.

### 13.1. Spring Service with `@Transactional`

```java
import java.util.UUID;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public final class OrderCreationService {

    private final JdbcTemplate jdbc;

    public OrderCreationService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void createOrder(
            String orderId,
            String eventPayloadJson) {

        jdbc.update("""
                INSERT INTO orders(order_id, status)
                VALUES (?, 'CREATED')
                """,
                orderId);

        UUID eventId = UUID.randomUUID();

        jdbc.update("""
                INSERT INTO outbox_events (
                    event_id,
                    aggregate_type,
                    aggregate_id,
                    event_type,
                    topic_name,
                    message_key,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                eventId,
                "Order",
                orderId,
                "OrderCreated",
                "order-created.v1",
                orderId,
                eventPayloadJson);
    }
}
```

Here `eventPayloadJson` must be produced by an application-controlled serializer/schema and **should embed that exact generated `eventId`** or allow passing `eventId` in a Kafka header for downstream deduplication. Production code should construct the event DTO, ID, and payload **together in one place** before inserting, avoiding mismatches between the payload and outbox metadata.

### 13.2. Production Extension: Preventing Duplicate Business Commands

If a caller retries `createOrder(orderId)` after a timeout:

- The unique constraint on `orders.order_id` prevents creating two orders.
- Still, the application must decide whether a duplicate request is an **idempotent success** or a **payload conflict**.
- You can add a `processed_commands(request_id PRIMARY KEY, payload_hash, result_reference)` table in the same DB transaction.
- When `requestId` already exists, compare hashes: if identical, return the same result; if different, report a conflict.
- Never swallow all unique-constraint exceptions as "ok," since another bug could trigger a constraint violation.

**Important:** A new `eventId` is generated for **a new business operation**, never on each publisher retry.

## 14. Outbox Publisher: Sending After Commit

An independent publisher reads unpublished rows, sends them to Kafka, awaits the broker ACK (via future), and marks them succeeded.

### 14.1. Outbox DTO

```java
import java.util.UUID;

public record OutboxRow(
        UUID eventId,
        String topicName,
        String messageKey,
        String payloadJson
) {
}
```

### 14.2. Simple Single-Instance Publisher Example

```java
import java.util.List;
import java.util.concurrent.TimeUnit;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public final class SimpleOutboxPublisher {

    private final JdbcTemplate jdbc;
    private final KafkaTemplate<String, String> kafka;

    public SimpleOutboxPublisher(
            JdbcTemplate jdbc,
            KafkaTemplate<String, String> kafka) {

        this.jdbc = jdbc;
        this.kafka = kafka;
    }

    @Scheduled(fixedDelayString = "${app.outbox.poll-ms:1000}")
    public void publishPending() {
        List<OutboxRow> rows = jdbc.query("""
                SELECT event_id, topic_name, message_key, payload_json
                  FROM outbox_events
                 WHERE published_at IS NULL
                   AND next_attempt_at <= CURRENT_TIMESTAMP
                 ORDER BY created_at, event_id
                 LIMIT 100
                """,
                (rs, index) -> new OutboxRow(
                        rs.getObject("event_id", java.util.UUID.class),
                        rs.getString("topic_name"),
                        rs.getString("message_key"),
                        rs.getString("payload_json")
                ));

        for (OutboxRow row : rows) {
            try {
                kafka.send(
                        row.topicName(),
                        row.messageKey(),
                        row.payloadJson()
                ).get(10, TimeUnit.SECONDS);

                jdbc.update("""
                        UPDATE outbox_events
                           SET published_at = CURRENT_TIMESTAMP
                         WHERE event_id = ?
                           AND published_at IS NULL
                        """,
                        row.eventId());

            } catch (Exception failure) {
                // Keep pending to retry; production needs error classification,
                // backoff, logging/metrics, and time limits.
                reportOutboxFailure(row.eventId(), failure);
            }
        }
    }
}
```

`reportOutboxFailure(...)` is an illustrative application method. You must provide its implementation and configure `@EnableScheduling` (if not enabled elsewhere) for scheduling to run.

**Important limitations of this example:**

- Suitable only for **explaining the mechanism or testing a single publisher instance**.
- Lacks atomic claim/lease; running multiple pods concurrently can cause multiple publishers to send the same row.
- Does not update `attempts`, `next_attempt_at`, or classify errors; add these before production.
- Waiting on `future.get(...)` is a simple way to demonstrate "broker ACK before marking"; high-throughput systems may need concurrent/asynchronous publishers with bounded in-flight sends and backpressure.
- `published_at` is updated **after** the Kafka ACK, which is a separate DB transaction. Crashing between ACK and the update can re-emit the event.
- Setting `published_at` does not mean downstream consumers have processed the message.

### 14.3. Why Not Mark Published Before Sending?

Wrong:

```text
1. UPDATE outbox_events SET published_at = NOW()
2. COMMIT
3. KafkaTemplate.send(...)
4. JVM dies before broker receives

=> Outbox is marked sent; event may be lost.
```

Safer order:

```text
1. Read pending event
2. Send to Kafka
3. Wait for broker acknowledgment
4. UPDATE published_at
5. COMMIT update

If crash before (4), event is resent.
Downstream idempotent consumer handles replay.
```

This is a deliberate choice accepting **duplicates** over **loss** when no atomic transaction spans Kafka and the DB.

## 15. Multi-Publisher Outbox: Claim/Lease and SKIP LOCKED

When running multiple publisher pods, a naive `SELECT ... WHERE published_at IS NULL` can let two pods pick up the same row. That does not necessarily lose data if downstream is idempotent, but it creates duplicates and wastes bandwidth.

A common pattern uses **claims with lease expiration**.

### 15.1. Atomic Claim SQL in PostgreSQL

Illustrative example:

```sql
WITH candidates AS (
    SELECT event_id
      FROM outbox_events
     WHERE published_at IS NULL
       AND next_attempt_at <= CURRENT_TIMESTAMP
       AND (
            claimed_until IS NULL
            OR claimed_until < CURRENT_TIMESTAMP
       )
     ORDER BY created_at, event_id
     FOR UPDATE SKIP LOCKED
     LIMIT 100
)
UPDATE outbox_events AS o
   SET claim_token = :claimToken,
       claimed_until = CURRENT_TIMESTAMP + INTERVAL '60 seconds',
       attempts = attempts + 1
  FROM candidates AS c
 WHERE o.event_id = c.event_id
RETURNING
    o.event_id,
    o.topic_name,
    o.message_key,
    o.payload_json;
```

This uses PostgreSQL syntax, where `:claimToken` is a UUID generated by the publisher for **that claim batch**, bound via named parameters. The claim runs in a **short DB transaction** that commits before calling Kafka.

**Never hold row locks or an open DB transaction while waiting for a Kafka ACK.** Doing so holds locks too long, hurts throughput, and increases contention.

### 15.2. Marking After ACK with the Claim Token

```sql
UPDATE outbox_events
   SET published_at = CURRENT_TIMESTAMP,
       claimed_until = NULL,
       claim_token = NULL
 WHERE event_id = :eventId
   AND claim_token = :claimToken
   AND published_at IS NULL;
```

If the updated row count is `0`, the publisher must not assume "the event is marked"—its lease may have expired and another worker may have reclaimed it. Log, emit a metric, and reconcile.

### 15.3. Leases Do Not Eliminate Duplicates

Suppose publisher A claims a row with a 60-second lease, and Kafka takes 80 seconds to send. The lease expires, and publisher B claims and sends it again. Both may publish the same event.

Therefore:

- Lease duration must account for send timeouts and backpressure.
- Downstream consumers still require idempotency.
- Leases can be renewed during long operations if needed.
- Use a stable `eventId` so duplicates are recognizable.
- Outbox state after a send failure must permit retries with backoff; never leave a row stuck permanently in an "in progress" state.

**Claiming reduces contention; it does not prove exactly-once.**

### 15.4. Backoff and Persistently Failing Rows

An outbox row whose payload exceeds topic size limits or fails serialization will fail repeatedly. Do not retry it every 1 ms forever.

Track:

```text
event_id
attempts
next_attempt_at
last_error_code
state = PENDING / CLAIMED / PUBLISHED / QUARANTINED
```

Once a threshold is exceeded, transition the row to `QUARANTINED` and raise an alert, **never deleting it before a handling path exists**. Critical events need a repair/replay runbook.

## 16. CDC Outbox: Debezium Instead of a Poller

Another option is **Change Data Capture (CDC)** reading changes from the database transaction log. For PostgreSQL, tools like Debezium read the WAL via logical replication and stream outbox inserts to Kafka.

```text
Business DB transaction:
    INSERT orders
    INSERT outbox_events
    COMMIT
             |
             v
   PostgreSQL WAL / logical decoding
             |
             v
      Debezium Connector
             |
             v
          Kafka topic
```

Advantages of this pattern:

- The application does not poll tables in a loop.
- Observes database commit order per connector capabilities.
- Reduces polling queries when properly configured.
- Can use Debezium's Outbox Event Router SMT to map outbox columns to Kafka topics and keys.

Yet CDC **is not free**:

- Requires operating Kafka Connect, connectors, and plugin versions.
- A PostgreSQL logical replication slot can retain WAL indefinitely if a connector stalls.
- Requires replication privileges, snapshot strategies, and retention planning.
- Connectors can retry/restart and re-emit events; consumers still need idempotency.
- Topic names, event keys, headers, schemas, and routing SMTs must be versioned.
- Error handling, poison outbox rows, and backup/restore need runbooks.

### 16.1. Choosing Poller vs. CDC

| Criterion | Application Polling | CDC / Debezium |
|---|---|---|
| Initial setup | Simple for small services | Requires Kafka Connect / CDC infra |
| Latency | Driven by poll interval / backoff | Driven by replication log and connector |
| Database load | Pending `SELECT`/`UPDATE` queries | Reads transaction log; still incurs overhead |
| Ordering | Must be explicitly designed, especially with multiple workers | Relies on commit order / connector routing |
| Retry | Application-managed | Managed by connector / Kafka Connect |
| Operations | Service team owns poller | Platform / Connect owner |
| Idempotency | Still required | Still required |
| Monitoring | Pending age, attempts | Connector lag, replication slot, retained WAL |
| Recovery | Replay outbox rows | Connector offsets / snapshot / replay |

There is no universal best choice. If you already run reliable Kafka Connect infrastructure, CDC can fit well. If the system is small and you want minimal infrastructure, a clear, well-tested poller can be simpler.

## 17. Case 3: Kafka → DB → Kafka

Many services consume a message, update a DB, and emit a new event:

```text
Kafka topic A
      |
      v
@KafkaListener
      |
      v
DB transaction
  - inbox event ID
  - business state
  - outbox output event
      |
    COMMIT
      |
      v
Container offset commit (Kafka A)
      |
      v
Outbox Publisher
      |
      v
Kafka topic B
```

This **combines inbox + outbox**.

Such a design covers three primary failure windows:

1. **Before DB commit:** transaction rolls back; Kafka can redeliver the input.
2. **After DB commit, before input offset commit:** input may redeliver; inbox detects duplicate and skips repeating business/outbox writes.
3. **After output Kafka ACK, before marking outbox published:** output may be resent; downstream deduplicates using the stable event ID.

### 17.1. When Both Topics Are on the Same Kafka Cluster

Even when input and output live on the **same Kafka cluster**, if business state must commit in PostgreSQL, you still have to reason about the DB/Kafka failure window. Kafka transactions can support Kafka-to-Kafka exactly-once within their own scope, but they do not automatically expand into an atomic DB+Kafka transaction.

### 17.2. When Topics Are on Different Kafka Clusters

If input comes from Kafka cluster A and output goes to Kafka cluster B, no single Kafka transaction spans offset A and record B. Inbox/outbox is especially valuable here because it makes no cross-cluster transaction assumption.

### 17.3. Writing Outbox Inside the Same Service Transaction

Extending the `applyEvent` service shown earlier:

```java
@Transactional
public void handleAndPlanOutput(PaymentEvent event) {
    // 1. Claim event ID in inbox (unique key).
    // 2. Apply business change.
    // 3. Insert outbox with stable output eventId.
    // 4. Commit everything in the same database transaction.
}
```

Critically, **the output event must only be created when the input is genuinely new or satisfies the output emission policy**. If a listener sees a duplicate input and inserts a fresh outbox UUID, downstream consumers will receive two result events for one business action.

You can derive a deterministic output ID from `(sourceSystem, inputEventId, outputEventType)` when contracts permit, or store an `inputEventId → outputEventId` mapping in the DB. Never derive IDs solely from the current timestamp on each retry.

## 18. From "Exactly Once" to Business Invariants

Common statements evaluated:

| Statement | True by Default? | Conditions |
|---|---|---|
| A Kafka consumer may read a record multiple times | Yes, possible | Uncommitted offsets, rebalances, seeks/replays |
| Producer `enable.idempotence=true` prevents an app from sending an event twice | No | Only addresses certain internal producer retry duplicates |
| `@Transactional` on a service makes DB writes atomic | True within that DB TX | All operations must share the same DB transaction |
| `@Transactional` makes Kafka send + DB atomic | No | Kafka and DB have no shared coordinator by default |
| Kafka transactions support Kafka-to-Kafka EOS | Yes, within configured scope | Same cluster, transaction setup, offset handling |
| An inbox makes database effects idempotent | Yes, by design | Proper event ID, unique key, and shared TX |
| An outbox prevents events from being lost after DB commit | Yes, per model | Durable outbox and operational publisher/recovery |
| An outbox publisher sends strictly once | No | ACK and mark are not atomic; resends can occur |
| A DLT guarantees failed events will eventually succeed | No | Requires a replay owner and monitoring |
| Traces/metrics showing success prove exactly once | No | Requires reconciliation and business evidence |

**Practical goal:** achieve **effectively-once business outcomes** within well-defined data boundaries using at-least-once delivery + idempotent effects + recovery workflows. Never label a system "end-to-end exactly once" without documenting and proving all external side effects.

## 19. Ordering: Same Aggregate and Same Partition

Kafka guarantees record order **within one partition** by log order, not global order across partitions or topics.

Suppose an order has:

```text
OrderCreated(version=1)
OrderPaid(version=2)
OrderCancelled(version=3)
```

If producers use `orderId` as the Kafka key, events for the same order typically land on the same partition under a consistent partitioner. This lets consumers observe log order as long as partitions or routing do not shift. Still:

- Independent producers can emit events out of business order.
- Consumers experience retries, seeks, or batch replays.
- Multi-worker outbox publishers can emit version 3 before version 2.
- Partition count changes or routing changes alter key-to-partition mappings.
- Events from separate sources lack a single global order.

### 19.1. Designing Explicit Ordering

For snapshot events:

- Store `aggregateVersion`.
- Apply only if the incoming version is newer.
- If the version matches yet the payload differs, treat it as a conflict.
- If gaps cannot be skipped, check `version == currentVersion + 1` and hold/retry/quarantine out-of-order events.

For delta events:

- Do not use `MAX(version)` and drop earlier versions.
- Apply strictly in sequence, or prove operations are commutative and associative.
- Consider an inbox + pending-events table per aggregate and a sequenced dispatcher.

### 19.2. Outbox Publish Order

`ORDER BY created_at, event_id` gives predictable selection order, but **does not guarantee Kafka receives events in that order** if multiple publishers run concurrently or target different partitions.

When per-aggregate order is required:

1. Use a stable Kafka message key per aggregate.
2. Anchor business order using `aggregateVersion` or a sequence column.
3. Claim/dispatch by aggregate, or block sending `v+1` while `v` is still pending.
4. Have downstream validate versions and handle out-of-order arrivals.
5. Test concurrent publishing and restarts, not just a single-worker happy path.

## 20. Event ID, Business Key, and Idempotency Key Are Different

A common mistake is overloading one field for every purpose.

| Key | Example | Purpose |
|---|---|---|
| `eventId` | `evt-101` | Deduplicates a redelivered event |
| `aggregateId` | `pay-701` | Identifies entity and per-entity ordering |
| `commandId/requestId` | `req-19` | Deduplicates an API or job command |
| `transactionId` | `bank-txn-88` | Uniqueness for a business transaction |
| `traceId` | `abc...` | Telemetry correlation, **never** business identity |
| Kafka `(topic,partition,offset)` | `payment-approved,2,120` | Record position in a log |

If an event is copied to another topic, its new `topic/partition/offset` changes, so log coordinates are not always suitable as cross-pipeline idempotency keys. A stable `eventId` from the source is usually better.

If the same business transaction is emitted with **two different event IDs**, an event-ID inbox alone will not stop duplicate ledger writes; add business uniqueness such as `UNIQUE(sourceSystem, transactionId)` and a conflict policy.

## 21. Metadata, Schemas, and Fields to Preserve Across the DB

An event persisted in a DB/outbox should never strip metadata needed for recovery:

```json
{
  "eventId": "evt-101",
  "eventType": "PaymentApproved",
  "schemaVersion": 1,
  "aggregateId": "pay-701",
  "aggregateVersion": 4,
  "occurredAt": "2025-05-12T10:00:00Z",
  "sourceSystem": "payments",
  "correlationId": "corr-19",
  "data": {
    "status": "APPROVED"
  }
}
```

Define clear contracts for:

- Is `eventId` globally unique or unique per source?
- Is `occurredAt` event occurrence time or publisher creation time?
- Is version a schema version or aggregate version? **These two are different.**
- Which headers must propagate: trace context, event type, correlation ID?
- On DLT replay, keep the original `eventId` or mint a new one? Usually keep the original identity if it is still the same event.
- Is mutating payload while keeping the same ID allowed? If not, detect conflicting duplicates.
- Are sensitive fields allowed in payloads or headers?

Test schema evolution between producer and consumer versions deployed independently. Never assume all services deploy simultaneously.

## 22. Database Transaction Boundaries and `@Transactional` Pitfalls

Several pitfalls break inbox/outbox designs even when annotations are present:

### 22.1. Self-Invocation Bypassing the Proxy

```java
@Service
public class PaymentService {

    public void handle(PaymentEvent event) {
        saveTransactional(event); // self-invocation can bypass the proxy.
    }

    @Transactional
    public void saveTransactional(PaymentEvent event) {
        // JDBC updates...
    }
}
```

With standard Spring proxy-based transaction management, calling a method on `this` skips the proxy, so `@Transactional` may not take effect as expected.

Fix: have the listener call a separate Spring-managed transactional bean, or use `TransactionTemplate` when an explicit transaction boundary is needed.

### 22.2. Catching Exceptions and Returning Normally

```java
@Transactional
public void apply(PaymentEvent event) {
    try {
        jdbc.update(...);
    } catch (DataAccessException ex) {
        log.warn("Failed", ex);
        // Returning normally may let the transaction commit
        // unless marked rollback-only by another layer.
    }
}
```

If an error requires rollback, rethrow appropriately or mark rollback-only per policy. Never swallow exceptions and treat the event as completed.

### 22.3. Calling HTTP/Kafka Inside a DB Transaction

Waiting for a Kafka ACK or external API while holding DB row locks hurts throughput and increases lock contention. Worse, external side effects do not roll back if the DB rolls back.

Keep outbox writes in a short transaction and let the publisher send asynchronously afterward for cleaner boundaries.

### 22.4. Two DataSources

If the inbox and business tables reside in **two databases or two datasources with separate transaction managers**, `@Transactional` by default manages only one matching manager. Never claim they are atomic without an actual supporting transaction mechanism.

It is much simpler when the inbox and business state live in the same database; otherwise, design explicit consistency checks, compensating actions, and reconciliation.

## 23. Kafka Transactions in Spring Kafka: Using the Right Scope

Spring Kafka supports producer transactions when configured with `transactionIdPrefix` and an appropriate transaction manager.

Example Spring Boot producer transaction config:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: payment-tx-
      acks: all
      properties:
        "[enable.idempotence]": true
```

Actual configuration also depends on instance counts and transactional ID management to avoid unintended fencing. Each instance typically needs a prefix/ID allocation scheme so transactional producers do not overwrite each other.

**Important:** enabling Kafka producer transactions is not enough for a `@KafkaListener` to achieve Kafka-to-Kafka EOS; you also need the proper container setup, transactional producer, offset sending, and downstream isolation levels per contract.

When a DB is the source of truth, an outbox is usually simpler than combining Kafka transactions with JDBC transactions and trying to claim full atomicity.

### 23.1. Kafka EOS Does Not Cover External DBs by Default

A Kafka-to-Kafka topology can commit output records and consumed offsets in the same Kafka transaction, preventing certain duplicate outputs within Kafka. However:

```text
Kafka input offset 120
  -> Kafka output event (transactional)
  -> PostgreSQL UPDATE
```

There is no automatic guarantee that the PostgreSQL `UPDATE` rolls back when the Kafka transaction aborts, or vice versa.

### 23.2. Transaction Synchronization Still Has a Failure Window

Spring offers mechanisms to synchronize transaction managers, yet committing resource A followed by resource B still leaves a failure window between the two commits. Read the documentation for your exact API version and run failure-injection tests; if strict atomicity across Kafka + DB is required, never treat two `@Transactional` annotations as proof.

## 24. Duplicate Delivery Must Be Designed For, Not Tested Once

Common sources of duplicates:

- Kafka consumer restarts before offset commit.
- Rebalances during slow processing.
- Error handler retries of the same record.
- Producer application resends after an ambiguous ACK timeout.
- Outbox publisher crashes after ACK before marking delivered.
- CDC connector restarts or replays.
- Operators resetting consumer group offsets to reprocess.
- Two schedulers or HTTP requests issuing the same business command.
- Replaying the DLT after fixing data issues.

An idempotent system must tolerate at least the redeliveries defined by its contract. For financial side effects, **business unique constraints** act as the final safety net when event IDs are insufficient.

### 24.1. Idempotency vs. Conflicting Duplicates

Two events sharing the same `eventId` with different payloads indicate a data quality bug:

```json
{"eventId":"evt-101","paymentId":"P-1","status":"APPROVED"}
{"eventId":"evt-101","paymentId":"P-1","status":"REJECTED"}
```

Never blindly `ON CONFLICT DO NOTHING` and drop the second event without checking; doing so can hide serious conflicts. Store a payload hash and source/schema version, and quarantine or fail conflicts per policy.

Conversely, if two events share `paymentId` with different `eventId`s, that can be a legitimate state transition. Never deduplicate all events by entity key.

## 25. Reconciliation: Finding Events Stuck Between Two Systems

Inbox/outbox is the recovery design; **reconciliation** detects when recovery stalls.

### 25.1. Pending Outbox Events

```sql
SELECT
    COUNT(*) AS pending_events,
    MIN(created_at) AS oldest_pending_at,
    MAX(attempts) AS max_attempts
FROM outbox_events
WHERE published_at IS NULL;
```

If the oldest pending age breaches SLA, check producer health, Kafka brokers, credentials, serialization, or the publisher scheduler. Do not watch consumer lag alone.

### 25.2. Repeatedly Failing Outbox Events

```sql
SELECT
    event_id,
    aggregate_type,
    aggregate_id,
    event_type,
    attempts,
    next_attempt_at
FROM outbox_events
WHERE published_at IS NULL
  AND attempts >= 10
ORDER BY attempts DESC, created_at
LIMIT 100;
```

If the system uses a `QUARANTINED` state, query that status explicitly. Never delete events merely because they hit a retry cap; confirm a repair/replay workflow exists.

### 25.3. Inbox and Business State

```sql
SELECT COUNT(*) AS processed_event_count
FROM processed_kafka_events;
```

The inbox count shows how many event IDs were committed transactionally. It **does not necessarily equal** the row count of `payment_projection`, because multiple events can update the same payment and stale events can enter the inbox without changing the projection.

For accurate reconciliation, define equations by event outcome:

```text
received_attempts
  = processing_attempts + deserialization_failures
  (depending on specific instrumentation)

unique_events
  = applied
  + stale
  + quarantined
  + pending
  (when categories are mutually exclusive)
```

This is a **conceptual model**; you cannot treat raw client consumed rates as an exact business balance equation when retries, rebalances, and DLTs occur. Verify counting rules at the exact point each counter increments.

### 25.4. Do Not Infer Consistency From Spring Kafka Metrics Alone

A fast listener timer only shows the callback returned quickly. A high Kafka producer send rate only shows the client sent records. Proving consistency requires inspecting the **business source of truth**, inbox/outbox state, and relevant Kafka metadata.

## 26. Observability for Kafka–Database Flows

A reliability dashboard should distinguish:

| Signal | Source | Purpose |
|---|---|---|
| Consumer group lag | Kafka exporter / admin monitoring | Detects backlogs |
| Listener duration/errors | Micrometer Observation | Measures callback execution |
| DB transaction latency | JDBC / pool / DB metrics | Spots DB bottlenecks |
| Inbox duplicate count | Business metric | Tracks redeliveries and replays |
| Inbox conflicting events | Business audit/metric | Detects conflicting payloads |
| Outbox pending count/age | PostgreSQL query/gauge | Spots unsent events |
| Outbox attempts/failures | Publisher metric | Shows active producer retries |
| Kafka producer errors/ACK latency | Kafka client metric / future | Flags outbound Kafka issues |
| DLT published/pending | Recoverer + DLT monitoring | Tracks poison messages |
| End-to-end event age | Timestamp contract + telemetry | Measures real SLO compliance |
| Trace correlation | Micrometer Tracing / OTel | Links consumer → DB → outbox publisher |

### 26.1. Avoiding High-Cardinality Metric Tags

Never use per-record `eventId`, `paymentId`, `orderId`, or Kafka offsets as Prometheus labels; those have unbounded cardinality. Use bounded tags:

```text
application=payment-worker
topic=payment-approved.v1
source=payments
outcome=applied|duplicate|conflict|failed
error_class=validation|transient_db|serialization|unknown
```

Individual event IDs belong in **structured logs/audits** with appropriate retention and access controls. Tracing headers are also not proof of authentication.

### 26.2. Event Age Is Not Listener Duration

An event can wait in Kafka for 20 minutes and then execute in 30 ms inside the listener. A 30 ms listener timer looks normal while end-to-end business latency has already breached its SLO. Track event age, consumer lag, and oldest pending outbox age as well.

## 27. Operations: Where to Investigate Rising Consumer Lag?

When Kafka → DB processing slows down, possible causes include:

1. Producers emit events faster than consumer capacity.
2. The listener is retrying a poison event.
3. PostgreSQL lock waits, slow queries, or exhausted connection pools.
4. Continuous consumer rebalances.
5. Partition skew overloading a single partition.
6. Changed group ID or offset configuration.
7. Paused or stopped listeners.
8. Stalled DLT publishing or error handling.
9. Rising DB unique-constraint conflicts from replays or duplicate upstream data.

Investigation workflow:

```text
Alert: group lag rising
    |
    v
Check partitions / assignment / consumer liveness
    |
    v
Check listener duration and error/retry counters
    |
    +-- DB slow? -> pool/locks/queries/transactions
    |
    +-- Poison record? -> error handler/DLT/quarantine
    |
    +-- Producer rate spiked? -> capacity/partitioning
    |
    +-- Rebalance? -> poll interval/pod lifecycle
    |
    v
Confirm lag drops and business outcomes return to normal
```

Never reset offsets just to "clear lag." Resetting can skip records or replay massive volumes of data. Always have a reprocessing and idempotency plan.

## 28. Operations: Where to Investigate Outbox Backlogs?

When `outbox_pending` grows:

- **Check scheduler/publisher:** is the poller running or paused?
- **Check Kafka destination:** bootstrap servers, topic existence, ACLs, broker availability.
- **Check send failures:** timeouts, message-too-large errors, serialization failures, producer buffer pressure.
- **Check DB:** are pending queries slow, or are row locks/leases stuck?
- **Check claim expiry:** are many rows claimed without an active worker finishing them?
- **Check CDC (if used):** connector status, replication slots, WAL retention, connector offsets.
- **Check throughput:** does outbox insertion rate exceed publish capacity?
- **Check persistently failing payloads:** rows failing repeatedly need quarantine.

A useful runbook:

```text
1. Confirm pending count, oldest age, and attempt counts.
2. Locate representative event IDs in audit records.
3. Correlate producer/connector logs with Kafka cluster status.
4. Fix the root cause without deleting outbox rows.
5. Let the publisher resume/retry with stable event IDs.
6. Watch pending counts drop and downstream receive events.
7. Reconcile business effects; expect possible duplicates from resends.
```

If the publisher emits duplicate events during recovery, that can be expected behavior by design. The goal is **preventing duplicates from becoming duplicate business effects**.

## 29. Operations: Database Unavailable

If the DB goes down:

- Kafka consumer listeners will fail. The error handler can retry with backoff or pause/stop per policy.
- Consumer lag may climb, which is expected when the source of truth is unavailable.
- Never ack uncompleted events just to keep lag low.
- Once the DB recovers, consumer replays may contain duplicates; the inbox protects against them.
- If the producer outbox uses the same DB, the publisher cannot fetch pending events; do not assume Kafka output continues on its own.
- Ensure enough capacity to drain backlogs and tune DB pools to avoid a thundering herd of retries.

You can use exponential backoff, circuit-breaker/consumer pausing, or rate throttling depending on design. No single retry count fits every SLA.

## 30. Operations: Kafka Unavailable

If the input Kafka cluster becomes unreachable, consumers temporarily stop receiving data. Existing DB business state stays intact, though new updates stop arriving.

If the output Kafka cluster is unavailable:

- DB transactions inserting outbox rows can still commit if the business contract allows eventual publishing.
- Pending outbox rows accumulate, requiring alerts and retention capacity.
- Once Kafka recovers, the publisher catches up.
- If output events have a hard delivery deadline, define policies to block certain operations or signal business degradation instead of waiting indefinitely.

Document the **maximum acceptable pending age** and which data must not be exposed externally before downstream confirms receipt.

## 31. Safe Deployments and Schema Migrations

A minor change to an event schema or inbox/outbox table can break consumers and publishers in bulk.

### 31.1. Migrating the Outbox Table

When adding columns:

- Prefer **backward-compatible** migrations with the running application version.
- Apply schema changes before deploying code that reads/writes newly required fields.
- Provide defaults or dual-read logic during transitions if needed.
- Never drop `event_id` or `payload` columns still needed by older publisher instances.
- Verify pending rows written by the previous version can be published by the new version.
- With CDC, verify connectors and SMTs tolerate the schema change.

### 31.2. Migrating Consumer Groups and Offsets

Changing `group.id` creates a **new consumer group** with its own offsets. With `auto.offset.reset=earliest`, the new group may reread retained records. With `latest`, it may miss records produced before startup.

Deployment plans must specify:

- Keep or change the group ID?
- Is backfill or replay required?
- Is inbox retention long enough to deduplicate the replay?
- Are business versions/sequences compatible with older events?
- How will existing DLT records be handled?

### 31.3. Inbox Retention

Do not purge inbox keys too early. If Kafka retention is 30 days while the inbox only keeps 1 day, a message replayed after 7 days will lack a deduplication key.

Key retention must reflect the **real replay window**, DLT replays, and business rules. For financial transactions requiring long-term duplicate protection, business uniqueness and audit records may need retention exceeding Kafka's retention.

### 31.4. Outbox Cleanup

Only clean up rows confirmed published per policy and past their audit/retention window. Never purge pending rows just because they are old.

One approach is archiving published events daily while retaining enough metadata for post-incident reconciliation.

## 32. Unit Testing: Idempotency and Conflicting Duplicates

A minimal test suite should verify:

- New events are applied.
- Same event ID + same payload is treated as a replay and not applied twice.
- Same event ID + different payload throws a conflict.
- DB transactions roll back when business updates fail.
- Stale projection versions do not overwrite newer versions.
- Null or malformed events are never treated as successful.

### 32.1. Unit Testing Validation

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class PaymentEventValidationTest {

    @Test
    void rejectsMissingIdentity() {
        PaymentEvent invalid = new PaymentEvent(
                "payments",
                "",
                "pay-701",
                4L,
                "APPROVED",
                "a".repeat(64)
        );

        assertThrows(
                InvalidPaymentEventException.class,
                () -> PaymentProjectionService.validate(invalid)
        );
    }
}
```

This test requires adjusting the visibility of `validate` in the earlier example (currently `private`) or extracting a validator class to test directly. It is a **conceptual pattern** for contract validation, not a standalone copy-paste class.

### 32.2. Why Mocking the Repository Is Insufficient

Mocking `JdbcTemplate.update(...)` to return `1` or `0` tests branching logic, yet **fails to prove**:

- PostgreSQL unique constraints resolve races between two transactions.
- Inbox and projection roll back together.
- Transaction proxies are actually active.
- Kafka offsets commit properly after DB commit.

These guarantees require integration tests against a database and Kafka broker matching production semantics.

## 33. Integration Tests: Kafka → PostgreSQL

Recommended stack: **Testcontainers Kafka + PostgreSQL**, `spring-kafka-test`, and Spring Boot test. Use Awaitility or bounded synchronization primitives; avoid arbitrary `Thread.sleep(...)`.

### 33.1. Standard Scenario

Fixture:

```text
Kafka topic: payment-approved.v1
Event:
  eventId=evt-101
  sourceSystem=payments
  paymentId=pay-701
  version=4
  status=APPROVED
```

Steps:

1. Initialize the PostgreSQL schema and Kafka topic.
2. Publish event `evt-101`.
3. Wait for the projection DB to reach `APPROVED/version=4`.
4. Republish the exact same `evt-101`.
5. Verify `processed_kafka_events` holds only one row for that key.
6. Verify the projection was not applied twice (for deltas, check totals did not increase again).
7. Verify the listener continues consuming subsequent new events.

### 33.2. Failure After DB Commit Before Offset Commit

This is an essential fault-injection test:

```text
Execution A:
  consume evt-101
  DB transaction COMMIT
  force crash / prevent offset commit

Execution B:
  consumer restarts
  Kafka redelivers evt-101
  inbox conflict -> no-op
  offset committed when listener returns
```

You can simulate this with a test harness controlling container lifecycle, ack mode, and a crash point, or by resetting offsets to the same record and verifying idempotent outcomes. **Resetting offsets simulates replay** rather than proving every production race condition; document the test's exact scope.

### 33.3. Failure Before DB Commit

Trigger an exception after inserting into the inbox but before updating/committing the projection:

```text
BEGIN
  insert inbox evt-101
  throw exception
ROLLBACK
```

Assert the inbox **does not contain the key** and the projection **remains unchanged**. Allow Kafka redelivery and verify subsequent processing succeeds.

### 33.4. Concurrency

Run two listeners/transactions processing the same event ID concurrently and assert the unique constraint protects integrity. This is especially important with multiple pods, partitions, or replays from multiple sources.

Do not conclude a single-consumer test proves concurrency safety.

## 34. Integration Tests: PostgreSQL → Kafka

### 34.1. Happy Path

1. Create an order in a single DB transaction.
2. Confirm both the order and outbox row exist after commit.
3. Run the publisher.
4. Confirm Kafka receives the message with the right `eventId`, `message_key`, and payload.
5. Confirm `published_at` is recorded after ACK.
6. Confirm downstream idempotency if the same event is resent.

### 34.2. Business Transaction Rollback

Simulate an error right after the outbox insert before commit:

```text
BEGIN
  insert orders
  insert outbox
  throw error
ROLLBACK
```

Expected: neither the order nor the outbox row exists. The publisher has nothing to send.

### 34.3. Crash After Broker ACK Before Marking Published

Simulate Kafka receiving the message while stopping the publisher before updating `published_at`.

When the publisher restarts, the same `eventId` may be sent again. Downstream consumers must detect the replay and avoid duplicate business effects.

### 34.4. Kafka Unavailable

Shut down the outbound broker during the test:

- Orders and outbox rows commit per policy.
- The publisher does not mark rows published.
- Pending age and attempts increase per policy.
- Once the broker returns, the publisher delivers the rows.
- Never delete or falsely mark events just to clear alerts.

### 34.5. Multiple Publishers

Run two publishers claiming from the same outbox table. Assert atomic claiming reduces contention and every event is sent at least once; **do not** assert every event appears on Kafka strictly once across all crash scenarios.

## 35. Test Matrix: Failure Windows

| Failure Point | Expected Behavior |
|---|---|
| Consumer crashes before DB transaction | Kafka redelivery, zero business effect |
| Consumer crashes inside DB transaction | DB rollback, safe retry |
| Consumer crashes after DB commit before offset commit | Redelivery, inbox no-op |
| Consumer receives duplicate input event | Duplicate not applied |
| Input shares ID with different payload | Conflict detected |
| Older business event arrives after newer version | Handled per ordering/version policy |
| DB unavailable | Retry/backoff/stop per policy; no false ack |
| Kafka output unavailable | Outbox keeps rows pending |
| Outbox publisher crashes after ACK | Resends same event ID; downstream deduplicates |
| Two publishers claim concurrently | DB claim/lease guards concurrency; duplicates still tolerated |
| Poison event JSON | DLT/quarantine per policy and offset recovery |
| DLT producer fails | Record not silently dropped |
| CDC connector stops | WAL/connector lag rises and alerts fire |
| Kafka group ID changes | Reprocessing plan and offset semantics verified |
| Inbox keys expire past retention | Long-term business uniqueness preserved on old replays |
| New schema / older reader | Compatibility maintained or fail/quarantine |
| Lost tracing/metrics | Business logic keeps running; telemetry gap detected |

A business-grade test suite must verify **database state, Kafka record identity, offset metadata, and recovery behavior**. Asserting only that `@KafkaListener` ran once on the happy path does not prove reliability.

## 36. Anti-Patterns to Avoid

| Anti-Pattern | Risk | Alternative |
|---|---|---|
| Calling `KafkaTemplate.send` inside `@Transactional` and assuming full atomicity | DB and Kafka commits diverge | Transactional outbox |
| Committing/acking offsets before DB commit | Events can be lost | Commit after processing; inbox for replays |
| Swallowing exceptions in listeners | Container treats failures as success | Propagate errors or use durable recovery |
| Using an in-memory `HashSet` for deduplication | State lost on crash; no rollback | Unique inbox key inside DB transaction |
| Keeping the inbox in Redis outside the DB TX | Marked processed while DB rolls back | Inbox in same DB as business effects |
| Deduplicating all events by `paymentId` | Drops legitimate updates | Separate event ID and entity ID |
| Skipping payload checks on duplicate event IDs | Masks conflicting duplicates | Payload hash/canonical check + quarantine |
| Marking outbox published before Kafka ACK | Loses events on send failure | Mark after ACK; allow resends |
| Outbox publisher mints a new event ID per retry | Downstream cannot recognize replays | Stable event ID persisted in outbox |
| Two pollers `SELECT` pending rows without coordination | Duplicate sends and races | Claim/lease + idempotent downstream |
| Holding a DB transaction open while awaiting Kafka send | Long locks, low throughput | Short transactions, async outbox |
| DLT without an owner or retention policy | Poison events forgotten | Runbooks, monitoring, replay workflows |
| Deleting pending outbox rows to shrink backlog | Data loss | Fix root cause and retry/reconcile |
| Retrying schema errors indefinitely | Poison message stalls partition | Non-retryable classification + DLT |
| Treating `enable.idempotence` as business exactly-once | Does not protect DB/app resends | Inbox/outbox/business keys |
| Treating `read_committed` as DB transaction isolation | Misunderstands scope | Separate Kafka transactions from JDBC |
| Using Kafka offsets as unique IDs across topics | Coordinates change on forward/replay | Stable source event ID |
| Using tracing IDs as idempotency keys | Traces are not business identity | Stable event/command IDs |
| Changing consumer groups without a plan | Unexpected replays or skipped records | Migration/reprocessing plan |
| Testing only embedded single-broker happy paths | Misses dual-write crash windows | PostgreSQL + Kafka fault injection |
| Writing payloads/secrets into logs or metric tags | Data leaks, high cardinality | Safe structured metadata + ACLs |

## 37. Practice Exercise: Kafka–PostgreSQL–Kafka Payment Synchronization

Build a `payment-settlement-service`:

- Consume `PaymentApproved` from `payment-approved.v1`.
- Persist payment state and processing history in PostgreSQL.
- Emit `SettlementRequested` to `settlement-requested.v1`.
- Support consumer restarts, producer retries, and multi-pod deployments.

### Part A — Data and Transactions

1. Define distinct event IDs, payment IDs, aggregate versions, and schema versions.
2. Create `processed_kafka_events` with a unique key on source + event ID.
3. Create a `payments` table enforcing version or business state transition rules.
4. Create `outbox_events` storing stable output event IDs, topics, keys, payloads, and pending status.
5. Write inbox, business state, and outbox rows **in a single PostgreSQL transaction**.
6. Verify same input event ID + same payload is a no-op; same ID + different payload triggers a conflict.
7. Add a business unique key preventing two different event IDs from creating the same disallowed side effect.

### Part B — Consumer

8. Configure `enable-auto-commit=false` and `AckMode.RECORD`.
9. Have the listener invoke a Spring-managed `@Transactional` service bean without swallowing exceptions.
10. Add `DefaultErrorHandler` with bounded retries and classify permanent errors.
11. Configure a DLT targeting the right cluster and verify recovery failures are not ignored.
12. Test DB commit followed by uncommitted Kafka offset; replay must not duplicate effects.
13. Test DB rollback; inbox key must roll back so retries can process.

### Part C — Outbox Publisher

14. Build a publisher reading pending rows, sending via `KafkaTemplate` with a stable key, and awaiting ACK.
15. Set `published_at` only after the send future completes successfully.
16. Create a crash case after ACK before marking; verify resends preserve the same event ID.
17. Scale to multiple publishers using `FOR UPDATE SKIP LOCKED` + claim leases.
18. Add attempts/backoff/quarantine for poison outbox rows.
19. Compare a poller against Debezium CDC on latency, infrastructure, and recovery.
20. If per-payment ordering is needed, design `aggregateVersion` and publisher ordering rules.

### Part D — Observability and Operations

21. Dashboard: consumer lag, listener errors/retries, inbox duplicates/conflicts, outbox pending/oldest age, producer ACK failures.
22. Alert if outbox age breaches SLO or Kafka group lag climbs steadily.
23. Write runbooks for PostgreSQL unavailable, outbound Kafka unavailable, and Debezium connector stopped.
24. Audit input/output topic ACLs and avoid writing sensitive data into Kafka headers or logs.
25. Build Kafka + PostgreSQL integration tests covering key crash windows.
26. Test changing `group.id`; explain how inbox retention affects replay.
27. Test receiving event `v5` before `v4`; verify differing policies for snapshot vs. delta events.
28. Build reconciliation ensuring no committed outbox event is permanently forgotten.

**Review Question 1:** The consumer updated PostgreSQL successfully, but the JVM crashed before offset commit. Kafka redelivers the same record. Is this a Kafka bug?

**Answer:** **No.** This is a normal failure window in at-least-once processing. An inbox key sharing the database transaction and idempotent business effects make replay safe.

**Review Question 2:** If the producer sent to Kafka successfully, yet the application crashed before updating `outbox.published_at`, can we delete the row assuming "it was probably sent"?

**Answer:** **No.** There is no atomic commit spanning the broker ACK and the outbox update. The publisher should resend with the same stable event ID as needed; downstream deduplicates, and reconciliation marks it properly.

**Review Question 3:** Do `@Transactional` + `KafkaTemplate` + `enable.idempotence=true` guarantee exactly one business effect across both PostgreSQL and Kafka?

**Answer:** **No.** Each mechanism has its own boundary. Achieving consistency between a DB and Kafka requires designing transaction boundaries, inbox/outbox tables, idempotency, failure recovery, and testing the crash windows.

## 38. References

- [Spring Kafka Reference — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html): Kafka transactions, offsets, and EOS boundaries.
- [Spring Kafka Reference — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html): transactional producers, transaction synchronization, and limitations.
- [Spring Kafka Reference — Receiving Messages](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages.html): listener containers, offset management, and acknowledgments.
- [Spring Kafka Reference — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): `DefaultErrorHandler`, retries/recovery, and DLTs.
- [Spring Kafka Reference — Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html): `KafkaTemplate` and send futures.
- [Spring Boot Reference — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html): Boot consumer, producer, and listener configuration.
- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): `@Transactional`, transaction managers, and boundaries.
- [Apache Kafka — Message Delivery Semantics](https://kafka.apache.org/documentation/#semantics): at-most-once, at-least-once, and exactly-once in Kafka.
- [PostgreSQL — INSERT / ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html): atomic uniqueness and upserts.
- [PostgreSQL — SELECT / SKIP LOCKED](https://www.postgresql.org/docs/current/sql-select.html): row locking and multi-worker queue processing.
- [Debezium — Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html): outbox design with CDC and Kafka Connect.
- [Debezium — PostgreSQL Connector](https://debezium.io/documentation/reference/stable/connectors/postgresql.html): logical decoding, replication slots, and connector operations.
- [Microservices.io — Transactional Outbox](https://microservices.io/patterns/data/transactional-outbox.html): dual-write problem and outbox pattern.
- [Microservices.io — Idempotent Consumer](https://microservices.io/patterns/communication-style/idempotent-consumer.html): handling message redeliveries with unique business keys.
