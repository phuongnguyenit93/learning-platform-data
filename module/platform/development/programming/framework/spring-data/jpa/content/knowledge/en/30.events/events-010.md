# Designing Idempotent Event Handlers in Spring Data JPA

## 1. The problem: an event can be delivered multiple times

In an event-driven system, a broker, webhook, or background job can redeliver the same event when a consumer loses its connection, times out, restarts, or has already `COMMIT`ted data without yet acknowledging (`ACK`) the sender. Therefore, receiving a message twice does not necessarily represent two distinct business actions.

For example, the event `PointsEarned(eventId=E1, accountId=10, points=7)` asks to add 7 points to an account. If the handler runs the addition twice, points increase by 14 instead of 7. The goal is: **processing the same logical event repeatedly still produces a single business outcome**.

Idempotency can be expressed as `apply(apply(state, E), E) = apply(state, E)`. This **does not mean** the broker delivers only once; the consumer may still receive multiple copies, yet the committed database effect appears only once per deduplication key.

Distinguish the following concepts:

| Concept | Meaning |
| --- | --- |
| *At-least-once delivery* | Events can arrive multiple times; exactly-once receipt must not be assumed. |
| *Deduplication* | Recognizing that an `eventId` has already been handled by this consumer. |
| *Idempotent effect* | Re-running the same event does not alter the already-committed outcome. |
| *Exactly-once end-to-end* | A stronger guarantee requiring reasoning across the entire system from producer to all external effects; a dedup table in JPA alone does not provide this guarantee. |

## 2. Defining boundaries and identity keys

Before writing code, answer four questions:

1. **What defines a single event?** The producer must assign a stable `eventId` when creating a logical event. Every redelivery/retry keeps the same ID; the consumer must never generate a new UUID upon receipt.
2. **Who applies the effect?** Two independent business consumers may both need to process E1. Use a composite key `(consumer_name, event_id)` rather than a globally shared `event_id` alone.
3. **Which effects must be atomic?** The "processed" marker and the business changes must sit in the **same database transaction**. If the business logic rolls back, the processed marker rolls back too.
4. **When to acknowledge?** ACK or mark the message successful **after the DB transaction commits successfully**. If the handler throws an error, do not ACK success; let retry or dead-letter handling follow policy.

Do not use `existsBy...()` followed by `save()` as two separate steps to enforce uniqueness. Two concurrent threads can both observe "does not exist yet." You need a **real UNIQUE constraint in the database** and an atomic claim-for-processing operation. Caches or in-memory `Set`s can only serve as secondary optimizations because they lose state on restart and are not synchronized across instances.

Business keys and `eventId` also differ: one order can emit multiple valid events (created, paid, canceled). Using only `orderId` as the dedup key would wrongly drop distinct events. Conversely, if a producer issues a fresh ID for the same retried business transaction, deduping by `eventId` alone will miss the logical duplicate; when needed, the producer must supply a stable business transaction ID and corresponding uniqueness rules.

## 3. Safe processing flow with a single database

With PostgreSQL and Spring Data JPA, a verifiable implementation looks like this:

1. Validate input data and preserve `eventId`.
2. Start a `@Transactional` transaction.
3. Attempt to insert the `(consumer_name, event_id)` marker using `INSERT ... ON CONFLICT DO NOTHING` backed by a unique index.
4. If the inserted row count is `0`, this is a duplicate already committed by another transaction: exit without altering business data.
5. If the inserted row count is `1`, update business data inside **that transaction**.
6. Commit; only after the transactional method returns successfully should you ACK the message.

Contention on the same `eventId` is arbitrated by the database through the unique constraint. On PostgreSQL, when two transactions try to insert the same key, the second transaction may wait for the first transaction's outcome: if the first commits, the second inserts nothing; if the first rolls back, the second can insert and execute the business logic. There is no need to rely on in-process Java locks.

| Failure point | State and recovery |
| --- | --- |
| Failure before inserting marker | No changes; redelivery can try again. |
| Marker inserted, business update fails | Entire transaction rolls back, including marker; retries are not skipped. |
| DB committed, ACK unsent or lost | Broker may redeliver; insert returns `0`, avoiding double addition. |
| Two copies arrive concurrently | Unique constraint guarantees at most one transaction wins processing for that key. |
| New event with a different ID | Processed as a new event; business state concurrency must still be protected. |

Key prerequisite: **the marker and business data reside on the same transactional resource**. Separate databases, HTTP APIs, emails, or outbound messages do not automatically roll back with a JPA transaction.

## 4. Spring Data JPA + PostgreSQL example

Suppose a `PointsEarned` event adds points to an account. This uses Java 17+, Spring Boot 3.x, `spring-boot-starter-data-jpa`, the PostgreSQL JDBC driver, and an SQL migration. The snippets below are files in the same `com.example.events` package; this is the business-processing layer called by a Spring Boot application and message adapter, not a standalone `javac` program.

### 4.1. Schema with UNIQUE constraint

```sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    points BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE processed_event (
    id BIGSERIAL PRIMARY KEY,
    consumer_name VARCHAR(100) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_processed_event_consumer_event
        UNIQUE (consumer_name, event_id)
);

INSERT INTO accounts (id, points) VALUES (10, 100);
```

Manage DDL with Flyway or Liquibase; in deployed environments, set Hibernate `ddl-auto=validate` instead of letting it alter the schema automatically. The `UNIQUE` constraint is mandatory protection, even when running multiple application replicas.

### 4.2. Entities and payload

File `Account.java`:

```java
package com.example.events;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "accounts")
public class Account {
    @Id
    private Long id;

    @Column(nullable = false)
    private long points;

    protected Account() { }
}
```

File `ProcessedEvent.java`:

```java
package com.example.events;

import java.time.Instant;
import java.util.UUID;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

@Entity
@Table(
    name = "processed_event",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_processed_event_consumer_event",
        columnNames = {"consumer_name", "event_id"}
    )
)
public class ProcessedEvent {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "consumer_name", nullable = false, length = 100)
    private String consumerName;

    @Column(name = "event_id", nullable = false)
    private UUID eventId;

    @Column(name = "processed_at", nullable = false)
    private Instant processedAt;

    protected ProcessedEvent() { }
}
```

File `PointsEarnedEvent.java`:

```java
package com.example.events;

import java.util.UUID;

public record PointsEarnedEvent(
    UUID eventId,
    Long accountId,
    long points
) { }
```

`eventId` is created on the producer side and stays unchanged across redeliveries. `points` must be positive per the rules of this event type.

### 4.3. Repositories: atomic claim and update

File `ProcessedEventRepository.java`:

```java
package com.example.events;

import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ProcessedEventRepository
        extends JpaRepository<ProcessedEvent, Long> {

    @Modifying
    @Query(value = """
        INSERT INTO processed_event (consumer_name, event_id, processed_at)
        VALUES (:consumer, :eventId, CURRENT_TIMESTAMP)
        ON CONFLICT (consumer_name, event_id) DO NOTHING
        """, nativeQuery = true)
    int insertIfAbsent(
        @Param("consumer") String consumer,
        @Param("eventId") UUID eventId
    );
}
```

File `AccountRepository.java`:

```java
package com.example.events;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface AccountRepository extends JpaRepository<Account, Long> {

    @Modifying
    @Query("""
        update Account a
           set a.points = a.points + :delta
         where a.id = :accountId
        """)
    int addPoints(
        @Param("accountId") Long accountId,
        @Param("delta") long delta
    );
}
```

`insertIfAbsent()` relies on **PostgreSQL** syntax, returning `1` when inserted and `0` when the key already exists. For other databases, use an equivalent insert-if-absent/unique-constraint mechanism and test real driver behavior.

`addPoints()` uses an UPDATE statement of the form `points = points + delta` so **different** events adding points concurrently do not suffer *lost updates*. This is a JPQL bulk update: it bypasses any `Account` entity state managed in the persistence context; this pattern does not load `Account` and then mutate it in the same transaction. If business rules involve complex invariants or handling already-loaded entities, use row locking or `@Version` with an appropriate retry strategy.

### 4.4. Handler: marker and business logic in the same transaction

File `PointsEarnedHandler.java`:

```java
package com.example.events;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PointsEarnedHandler {
    private static final String CONSUMER = "points-ledger";

    private final ProcessedEventRepository processedEvents;
    private final AccountRepository accounts;

    public PointsEarnedHandler(
            ProcessedEventRepository processedEvents,
            AccountRepository accounts) {
        this.processedEvents = processedEvents;
        this.accounts = accounts;
    }

    @Transactional
    public void handle(PointsEarnedEvent event) {
        if (event == null || event.eventId() == null
                || event.accountId() == null || event.points() <= 0) {
            throw new IllegalArgumentException("Invalid PointsEarnedEvent");
        }

        int inserted = processedEvents.insertIfAbsent(
                CONSUMER, event.eventId());

        if (inserted == 0) {
            return; // Duplicate already processed: do not add points again.
        }
        if (inserted != 1) {
            throw new IllegalStateException("Unexpected insert count");
        }

        int updated = accounts.addPoints(
                event.accountId(), event.points());

        if (updated != 1) {
            // Unchecked error rolls back both marker and business changes.
            throw new IllegalStateException("Account not found");
        }
    }
}
```

`@Transactional` rolls back by default on uncaught `RuntimeException`s. The `handle` method must be invoked through a Spring proxy (for instance from another listener bean); calling `this.handle(...)` inside the same class does not activate the transaction proxy. In this model, code returns only after Spring completes the commit or throws an error. Never swallow a business error and still return normally.

`@Modifying` repository methods execute inside the transaction opened by the service. Calling such a repository directly without a proper transaction will fail or lack atomicity.

### 4.5. Connecting to a message adapter and ACK timing

An adapter (Kafka, RabbitMQ, webhook worker, or polling job) invokes `handler.handle(event)`. With manual acknowledgment, the sequence is:

```java
// Pseudocode inside adapter, not a complete Spring Kafka class:
try {
    handler.handle(event);   // Transaction commits before returning.
    acknowledgeMessage();    // Acknowledge only after handle succeeds.
} catch (Exception ex) {
    triggerRetryOrDeadLetterAccordingToPolicy(ex);
}
```

`acknowledgeMessage` and `triggerRetryOrDeadLetterAccordingToPolicy` merely represent adapter operations; map them to the actual ACK/retry APIs and settings of your broker. Never ACK immediately on receipt and never ACK inside an uncommitted DB transaction. If a message can be redelivered between commit and ACK, the marker turns the redelivery into a no-op.

## 5. Tracing the outcome on the example

Initially `accounts.id=10` has `points=100`. The producer emits an event:

```text
eventId   = 00000000-0000-0000-0000-000000000357
accountId = 10
points    = 7
consumer  = points-ledger
```

- Attempt 1: marker insert succeeds (`1`), UPDATE adds 7, COMMIT. `points=107`; marker table has one row.
- Attempts 2 and 3 with the **same `eventId`**: insert returns `0`, handler exits. `points` remains `107`.
- If the account does not exist, `addPoints` returns `0` and throws; rollback removes the newly inserted marker as well. Once the root cause is fixed, a redelivery can process it.
- Same ID with a different `consumer_name` represents an independent business process; the composite unique key allows it to apply its own effect. Consumer names must remain **business-stable**; changing names casually across deploys can cause old events to be re-applied.

You can verify with:

```sql
SELECT points FROM accounts WHERE id = 10;
-- Expected after three deliveries of the same event: 107

SELECT COUNT(*)
FROM processed_event
WHERE consumer_name = 'points-ledger'
  AND event_id = '00000000-0000-0000-0000-000000000357';
-- Expected: 1
```

The results above are expected outcomes for the described scenario, not output from an actual execution.

## 6. Concurrency, event ordering, and common pitfalls

**Duplicates with the same ID:** the unique constraint protects across multiple JVMs/replicas. Do not use `synchronized`, JVM locks, or caches as the source of uniqueness guarantees.

**Events with different IDs updating the same row:** deduplication alone does not prevent lost updates. For additions, an atomic UPDATE as above fits well. For read-check-write operations (e.g., deducting funds if balance is sufficient), use DB constraints, conditional UPDATEs, row locks (`PESSIMISTIC_WRITE`), or optimistic locking (`@Version`) plus conflict retries.

**Out-of-order events:** idempotency does not create ordering. If `OrderShipped` arrives before `OrderPaid`, enforce valid state transitions, versions/sequences, or transition rules; never equate "never processed" with "allowed to apply." For versioned projections, consider conditional UPDATEs like `WHERE last_version < :incomingVersion` alongside domain checks.

**Same eventId with a different payload:** the simple pattern treats the later arrival as a duplicate. In systems requiring auditing, also store `payload_hash`/`schema_version` and compare them; matching IDs with mismatched contents should be surfaced as a producer contract violation rather than silently accepted.

**How long to keep markers?** Pruning too early allows old events from DLQs, backups, or replays to be processed again. Retention must span the full redelivery/replay window; monetary operations may require immutable history or permanent business keys. If partitioning/archiving, maintain duplicate detection across archived data as well.

**Catching unique violations inside a JPA transaction:** the `find → save` pattern is unsafe. Catching `DataIntegrityViolationException` and continuing inside the same `@Transactional` can leave the transaction marked rollback-only or the connection in an aborted state (especially on PostgreSQL). `ON CONFLICT DO NOTHING` avoids using exceptions for duplicate control flow; if you use insert-and-catch, handle the exception at a **separate transaction boundary** and inspect the exact failing constraint.

**Retries and poison events:** transient failures (deadlocks, DB disconnects, timeouts) should retry with backoff/jitter and a max-attempt cap; unrecoverable data errors should route to a DLQ/alert per policy. Never mark an event "processed" if business changes did not commit. Track duplicate rates, retries, unrecoverable errors, latency, and ledger table size.

## 7. External side effects outside the database: transactional outbox

Suppose after adding points you also need to send an email or emit a `PointsUpdated` event. Making HTTP calls, sending emails, or publishing messages directly inside `@Transactional` cannot be rolled back by JPA once an external system receives them. After commit, there is also a failure gap if the process crashes before sending.

A **transactional outbox** design is better suited:

1. In the **same transaction** as the marker and points change, insert an `outbox_event` row containing the payload and a stable ID.
2. A separate publisher reads the outbox, sends to the broker, and marks it sent. The publisher can emit duplicates if it crashes between sending and marking.
3. Downstream consumers also need idempotency keyed by the corresponding ID; when calling external services supporting idempotency keys, forward that stable key.

An outbox addresses atomicity between **writing DB state** and **recording the intent to publish a message**; it does not prove the entire pipeline delivers exactly once. For external providers lacking idempotency key support, build dedicated reconciliation, compensation, or state workflows; the `processed_event` table alone cannot guarantee external side effects happen once.

## 8. Mandatory test plan

Run integration tests against **real PostgreSQL** (e.g., Testcontainers); H2 does not prove PostgreSQL `ON CONFLICT` syntax or concurrent locking behavior. Key test cases:

| Case | Action | Invariant to verify |
| --- | --- | --- |
| Single event | Call `handle(E1)` once | Points +7, one marker. |
| Sequential redelivery | Call `handle(E1)` three times | Points only +7, one marker. |
| Concurrent redelivery | Two transactions/threads use the exact same E1, aligned at start | Both complete or retry on transient lock errors; total points only +7, one marker. |
| Business rollback | Invoke E2 for a nonexistent account | No E2 marker left behind, no points added. |
| Retry after rollback | Create a valid account then redeliver the same E2 | Processes successfully once. |
| Two distinct valid events | E3 and E4 for same account, different IDs | Both added in full, no lost update. |
| Crash between commit and ACK | Commit E5 then simulate missing ACK and redeliver E5 | Points not added a second time. |
| Out-of-order/payload mismatch | Stale event version or same ID with different payload | System enforces clear domain/audit rules; does not silently write wrong state. |

For concurrency tests, use a barrier so threads start close together; each handler invocation must run in an independent transaction through the Spring proxy. Then query the **committed DB** to assert point balances and marker counts. Exception tests must verify the transaction actually rolled back before counting markers.

## 9. Production readiness checklist

- Producer uses stable event IDs; contracts clearly specify eventId, consumer scope, schema version, and replay behavior.
- Database enforces a real UNIQUE constraint on the dedup key; marker and business writes commit/roll back together.
- ACK occurs after commit; retry/DLQ distinguishes transient errors from bad input, with monitoring.
- Shared-state updates withstand concurrency across **different events** and enforce ordering rules if needed.
- External side effects use an outbox/idempotency key or appropriate compensating mechanism.
- Retention, migrations, and crash/replay integration tests are maintained.

**Conclusion:** In Spring Data JPA, an idempotent event handler requires combining **stable IDs + DB UNIQUE constraint + atomic claim operation + single transaction covering both marker and business change + post-commit ACK**. Each piece closes a distinct failure window; omitting any piece can cause duplicates to re-apply or valid events to be lost.