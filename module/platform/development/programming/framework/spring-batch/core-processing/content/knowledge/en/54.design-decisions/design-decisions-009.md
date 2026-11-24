# Choosing Output Transaction vs. Outbox in Spring Batch

When designing the output of a Spring Batch job, a reliability-defining question is: **must results be written solely to a transactional resource, or must events/external system calls also happen after data is written?** The answer directly shapes rollbacks, retries, restarts, duplicate prevention, publication latency, and crash handling between two operations.

For example, a settlement job reads 10,000 transactions, writes ledger entries to PostgreSQL, and publishes a `LedgerPosted` event to a reporting service:

~~~text
Input -> Spring Batch -> PostgreSQL ledger -> Message broker -> Reporting service
~~~

If the writer commits to the database and the app crashes before publishing the event, the accounting entry exists while downstream knows nothing about it. If you reverse the order to publish first and write to the database second, downstream can receive an event for a transaction the database never committed. Wrapping everything in `@Transactional` does not automatically turn PostgreSQL, an HTTP API, and a broker into **one atomic transaction**.

**Core message:** *Output transaction* is the foundation when all changes belong to one transactional resource. *Transactional outbox* is the standard choice when you must **commit business data and record event-publication intent in the same transaction**, then deliver the event asynchronously with retries and idempotency. The two mechanisms **are not mutually exclusive**: outbox **uses the database transaction itself** to protect the initial write.

This lesson belongs to **Spring Batch Core Processing → Design Decisions**, focusing on architecture selection criteria, chunk semantics, *dual-write* risks, Spring Batch 5.x / Java 17+ / PostgreSQL examples, outbox operations, and failure scenarios to test.

## 1. Understanding Both Options Properly

### 1.1. Output Transaction

The writer performs changes on a resource with transactional semantics inside the chunk transaction, such as a database:

~~~mermaid
flowchart LR
    A["Reader"] --> B["Processor"]
    B --> C["Chunk transaction"]
    C --> D["INSERT/UPDATE ledger"]
    D --> E{"Commit"}
    E -->|Success| F["Data committed"]
    E -->|Error| G["Rollback chunk"]
~~~

If the database writer and `PlatformTransactionManager` truly share **the same datasource/transaction**, an error before commit normally rolls back the chunk's changes. Previously committed chunks are **not** rolled back alongside the current chunk.

This model fits when required outputs reside within **one transaction boundary**, such as writing to multiple tables in the same PostgreSQL database or updating a target table with a unique business key.

### 1.2. Transactional Outbox

The writer inserts **both business rows and outbox rows** inside the same database transaction:

~~~mermaid
flowchart LR
    A["Spring Batch chunk"] --> B["DB Transaction"]
    B --> C["Business rows"]
    B --> D["Outbox event PENDING"]
    D --> E["Outbox dispatcher / CDC"]
    E --> F["Broker / API"]
    F --> G["Idempotent consumer"]
~~~

The database commit decides whether **both records exist together or roll back together**. A separate dispatcher reads committed outbox rows and publishes messages. If the dispatcher crashes or the broker is temporarily unavailable, the event remains safely in the database for redelivery.

What outbox **does not guarantee** is atomicity between "broker received the event" and "database marked it `SENT`." If publishing succeeds and the dispatcher crashes right before marking it sent, it will re-send the event. Therefore, outbox typically provides **at-least-once delivery**, not end-to-end exactly-once; consumers must be idempotent.

### 1.3. Not a Strict Binary Choice

| Question | Output transaction | Transactional outbox |
|---|---|---|
| Writing to a single database only? | Usually the direct, simple choice. | Likely unnecessary if there are no external events/side effects. |
| Need to write DB **and** publish to a broker? | DB transaction **does not** cover the broker. | Usually fits if asynchronous delivery is acceptable. |
| Need to call an external HTTP API? | DB transaction cannot roll back API calls. | Can store *delivery intent* so a dispatcher calls the API with an idempotency key. |
| Must downstream receive the event synchronously in the same call? | Does not solve two-system atomicity. | Introduces publication delay; may not fit synchronous immediacy. |
| Replayable without creating duplicates? | Requires an idempotent writer on restart. | Requires unique outbox keys **and** an idempotent consumer. |
| Operational overhead | One writer and transaction manager. | Extra table, dispatcher/CDC, retries, backlog monitoring, cleanup. |

**Short rule:** If you only need durable writes within one database, prioritize transactions and solid writer design. If you must **write to a database and reliably notify another system without losing notification intent**, consider transactional outbox.

## 2. First Define Consistency Requirements

Before choosing technology, ask business questions:

1. **What is the full target set?** Database tables only, or also events, files, emails, HTTP requests, or message brokers?
2. **Can downstream tolerate delivery delay?** Outbox splits work into two phases, resulting in *eventual consistency*.
3. **If an event is delivered more than once, can the receiver defend itself?** You need stable business keys / event IDs.
4. **If the producer crashes, how long must events survive?** Outbox retention and recovery windows must be sized.
5. **Is event ordering required?** Two events for the same account may require strict order, while independent accounts do not.
6. **Must all results become visible simultaneously?** Chunk commits plus outbox can expose **partial** batch data to downstream before the whole job completes.
7. **Who handles multi-hour broker/API outages?** The job may finish DB writes while an outbox backlog accumulates.
8. **Is there source-to-target reconciliation?** A batch `COMPLETED` status does not prove consumers processed all messages.

A reference reporting system may tolerate minutes of lag and duplicate events. A financial system requiring exactly one ledger posting per event needs stronger unique constraints, audits, and reconciliation. "Consistency guarantees" must be expressed as **verifiable invariants**, not merely by naming the architecture "outbox."

## 3. Chunk Transaction Boundaries in Spring Batch

A chunk-oriented step runs the reader, processor, writer, and checkpoints across processing boundaries orchestrated by Spring Batch:

~~~text
Chunk 1: read A,B,C -> process -> write -> COMMIT
Chunk 2: read D,E,F -> process -> write -> ROLLBACK on error
Chunk 3: not yet run, or handled per fault-tolerance policy
~~~

With a JDBC writer using the step's same `DataSource` and `PlatformTransactionManager`, writes within a chunk commit or roll back together:

~~~java
@Bean
Step ledgerStep(
        JobRepository jobRepository,
        PlatformTransactionManager businessTransactionManager,
        ItemReader<LedgerRecord> reader,
        ItemProcessor<LedgerRecord, LedgerRecord> processor,
        ItemWriter<LedgerRecord> writer) {

    return new StepBuilder("ledgerStep", jobRepository)
        .<LedgerRecord, LedgerRecord>chunk(100, businessTransactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
}
~~~

This example assumes `reader`, `processor`, `writer`, and `JobRepository` beans already exist. The key requirement is that **`writer` uses a database connection participating in `businessTransactionManager`**. If the writer opens a separate connection with `autoCommit=true` or calls a service with `REQUIRES_NEW`, chunk rollback will not undo those independently committed operations.

### What Transactions Solve

- Changes within the same database transaction commit or roll back together.
- If the writer throws before commit and rollback works properly, uncommitted chunk rows do not appear at the target.
- Multiple business tables can update together in one transaction, such as `ledger_entry` and `audit_entry`.
- Unique constraints on business keys protect data against duplicates when inputs or restarts replay.

### What Transactions Do Not Automatically Solve

- Previously **committed** chunks do not roll back when a later chunk fails.
- `@Transactional` on a DB-writing service does not pull emails, files, HTTP calls, or brokers into the same transaction.
- Commit outcomes can be **ambiguous** if the process loses its connection right as the database receives `COMMIT`.
- `JobRepository` and the business database may use two different `DataSource`s / transaction managers; metadata/checkpoints and business outputs do not automatically commit atomically together.
- A successful transaction does not prove every business input was valid, complete, or deduplicated; reconciliation is still required.

When outputs live solely in one transactional DB, this model—paired with business keys, replay safety, and output checks—is usually sufficient.

## 4. Example: Choosing Direct Transactions When Writing Only to PostgreSQL

Suppose a job writes ledger postings into:

~~~sql
CREATE TABLE ledger_entry (
    event_id VARCHAR(100) PRIMARY KEY,
    account_id VARCHAR(80) NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
    business_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

`event_id` is a stable source business/event key, not a fresh random UUID per retry.

Writer example using `JdbcBatchItemWriter`:

~~~java
import javax.sql.DataSource;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;

@Bean
JdbcBatchItemWriter<LedgerRecord> ledgerWriter(DataSource businessDataSource) {
    return new JdbcBatchItemWriterBuilder<LedgerRecord>()
        .dataSource(businessDataSource)
        .sql("""
            INSERT INTO ledger_entry(
                event_id, account_id, amount, business_date)
            VALUES (:eventId, :accountId, :amount, :businessDate)
            ON CONFLICT (event_id) DO NOTHING
            """)
        .beanMapped()
        .assertUpdates(false)
        .build();
}
~~~

This example assumes `LedgerRecord` is a JavaBean/record with `eventId`, `accountId`, `amount`, and `businessDate` properties, and the datasource belongs to the step's transaction manager. `ON CONFLICT` is PostgreSQL syntax; other databases use different syntax.

**Why `assertUpdates(false)`?** If an item was already inserted on a prior run and SQL chooses `DO NOTHING`, a subsequent execution may see 0 rows inserted. You do not want 0 affected rows treated as a technical error under this policy. However, `DO NOTHING` **does not prove** the old and new payloads match: if `event_id` matches while `amount` differs, flag a consistency conflict rather than silently ignoring the discrepancy. A production writer can compare stored checksums/contents or use conditional UPSERTs to catch unexpected conflicts.

In this scenario, adding an outbox yields no clear benefit when there are no external events or side effects outside the database. Proper transactions + unique business keys + reconciliation are simpler and cleaner.

## 5. Why "Write DB Then Send Message" Directly Causes Dual Writes

Suppose a writer performs two operations:

~~~java
// Anti-pattern if consistent DB commit and event delivery are required.
ledgerRepository.save(record);
messagePublisher.send("ledger-posted", event);
~~~

Even if the method is wrapped in `@Transactional` for the database, the broker does not automatically join that transaction.

### Sending After Write but Before DB Commit

~~~text
T1  INSERT ledger inside transaction
T2  Broker receives LedgerPosted
T3  DB commit fails -> ROLLBACK

Result: consumer receives event while ledger does not exist.
~~~

The consumer may build reports or send notifications based on a ledger entry that never committed. If an error occurs while the writer runs and Spring Batch retries, the event can even be sent multiple times.

### Sending After Commit

~~~text
T1  INSERT ledger
T2  COMMIT database succeeds
T3  Process crashes
T4  No LedgerPosted event

Result: ledger exists while consumer never receives event.
~~~

Moving the send into an after-commit callback avoids publishing uncommitted data, yet **does not close the crash window between commit and send**. If the system requires guaranteed eventual delivery, an in-JVM `afterCommit` callback alone is normally insufficient.

### Reversing Order: Send Before Write

~~~text
T1  Send event succeeds
T2  DB insert fails

Result: consumer sees event with no underlying record.
~~~

Flipping the order does not eliminate the bug; it merely flips the failure mode. Solving it properly requires a **single source of truth for event-publication intent** committed alongside business state.

## 6. What Problem Does Transactional Outbox Solve?

Transactional outbox splits message publication into two phases:

**Phase A — Inside the Spring Batch Chunk Transaction**

~~~text
BEGIN transaction
  INSERT ledger_entry(...)
  INSERT outbox_event(event_id, payload, status='PENDING')
COMMIT transaction
~~~

If commit fails, **both the business row and the outbox row roll back**. If commit succeeds, **both exist together** for the dispatcher to pick up.

**Phase B — After Commit**

~~~text
Outbox dispatcher
  -> read PENDING events
  -> send to broker/API
  -> after delivery confirmed, mark SENT
~~~

The dispatcher can be a short-interval poller, a dedicated service, or Change Data Capture (CDC) tailing the database transaction log. Both polling and CDC require operational policies, retention, and duplicate handling.

**Core guarantee:** Business state and *publication intent* commit atomically **within one database**. It does not mean downstream consumers have already received the event the moment the batch step becomes `COMPLETED`.

### What Does Outbox Not Solve?

- Does not create an atomic commit between database and broker when the dispatcher sends.
- Does not guarantee consumers receive messages only once.
- Does not automatically preserve per-aggregate ordering if parallel dispatchers are not designed for it.
- Does not make external APIs idempotent; receivers can still produce duplicate side effects.
- Does not undo emails, HTTP calls, or file writes performed before enqueuing.
- Does not ensure whole-batch atomic publication: each **chunk** commits outbox events that can dispatch while the job is still running.

## 7. Designing an Outbox Schema in the Same Business Database

PostgreSQL example for `ledger_entry` and `outbox_event`:

~~~sql
CREATE TABLE ledger_entry (
    event_id VARCHAR(100) PRIMARY KEY,
    account_id VARCHAR(80) NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
    business_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE outbox_event (
    id BIGSERIAL PRIMARY KEY,
    event_id VARCHAR(140) NOT NULL UNIQUE,
    aggregate_key VARCHAR(100) NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    owner_token UUID,
    locked_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMPTZ,
    CONSTRAINT outbox_status_chk
        CHECK (status IN ('PENDING', 'IN_FLIGHT', 'SENT', 'DEAD'))
);

CREATE INDEX idx_outbox_dispatch
    ON outbox_event(status, created_at, id);
~~~

**Important columns:**

| Column | Purpose |
|---|---|
| `id` | Internal surrogate ID of the outbox row, convenient for claiming/batch polling. |
| `event_id` | **Stable** business event ID; unique to prevent duplicate outbox rows on replay. |
| `aggregate_key` | Account/order/entity key used when per-aggregate ordering is needed. |
| `event_type` | Event classification and schema evolution support. |
| `payload` | Message built from committed data; needs schema versioning and sensitive-data protection. |
| `status` | Tracks `PENDING`, `IN_FLIGHT`, `SENT`, `DEAD` per dispatcher rules. |
| `attempt_count` | Claim/publish attempts per design; does not prove how many times consumers processed it. |
| `owner_token`, `locked_until` | Coordinates multiple dispatchers and handles worker crashes. |
| `created_at`, `sent_at` | Measures lag from DB commit to successful publication. |

**The outbox row must share the exact same database transaction as `ledger_entry`.** Writing the outbox to a different datasource, or calling an outbox service using `REQUIRES_NEW`, breaks the core atomicity guarantee. "Having a table named outbox" does not mean you have implemented transactional outbox properly.

### How Should Event Keys Be Chosen?

For example, for a `LedgerPosted` event tied to a business event:

~~~text
event_id = "LEDGER_POSTED:" + sourceEventId
~~~

This ID must remain stable across chunk retries and restarts, never changing with `jobExecutionId` or run timestamps. If the same source event legitimately emits multiple event types, intentionally include event type/sequence or business version in the key.

Never generate a fresh random UUID **every time the writer is invoked** if items can replay: that produces multiple distinct outbox events for the exact same business action. A new UUID can still serve as an internal `id`, provided there is a strong **unique business/event key** to detect duplicates.

## 8. Spring Batch 5 Example: Writing Ledger and Outbox in One Chunk Transaction

Assume `LedgerRecord` has these fields:

~~~java
import java.math.BigDecimal;
import java.time.LocalDate;

public record LedgerRecord(
    String eventId,
    String accountId,
    BigDecimal amount,
    LocalDate businessDate
) {}
~~~

Writer using a `JdbcTemplate` **configured from the same `DataSource`** managed by the step's transaction manager:

~~~java
import java.util.Map;
import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriter;
import org.springframework.jdbc.core.JdbcTemplate;
import com.fasterxml.jackson.databind.ObjectMapper;

public final class LedgerOutboxWriter implements ItemWriter<LedgerRecord> {

    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;

    public LedgerOutboxWriter(JdbcTemplate jdbc, ObjectMapper mapper) {
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    @Override
    public void write(Chunk<? extends LedgerRecord> chunk) throws Exception {
        for (LedgerRecord record : chunk) {
            String eventId = "LEDGER_POSTED:" + record.eventId();

            // 1. Business output inside the chunk transaction.
            jdbc.update("""
                INSERT INTO ledger_entry(
                    event_id, account_id, amount, business_date)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (event_id) DO NOTHING
                """,
                record.eventId(),
                record.accountId(),
                record.amount(),
                record.businessDate()
            );

            // 2. Record intent only; do not call broker directly here.
            String payload = mapper.writeValueAsString(Map.of(
                "eventId", eventId,
                "sourceEventId", record.eventId(),
                "accountId", record.accountId(),
                "amount", record.amount().toPlainString(),
                "businessDate", record.businessDate().toString(),
                "schemaVersion", 1
            ));

            jdbc.update("""
                INSERT INTO outbox_event(
                    event_id, aggregate_key, event_type, payload, status)
                VALUES (?, ?, ?, CAST(? AS jsonb), 'PENDING')
                ON CONFLICT (event_id) DO NOTHING
                """,
                eventId,
                record.accountId(),
                "LEDGER_POSTED",
                payload
            );
        }
    }
}
~~~

In the step configuration:

~~~java
@Bean
Step ledgerOutboxStep(
        JobRepository jobRepository,
        @Qualifier("businessTransactionManager")
        PlatformTransactionManager businessTransactionManager,
        ItemReader<LedgerRecord> reader,
        ItemWriter<LedgerRecord> ledgerOutboxWriter) {

    return new StepBuilder("ledgerOutboxStep", jobRepository)
        .<LedgerRecord, LedgerRecord>chunk(100, businessTransactionManager)
        .reader(reader)
        .writer(ledgerOutboxWriter)
        .build();
}
~~~

For this example to meet its goals, ensure:

1. The writer's `JdbcTemplate` bean is wired to the **exact `businessDataSource`** used by `businessTransactionManager`; with multiple `DataSource`s, qualify explicitly.
2. The writer **never** calls `commit()` manually, never uses `REQUIRES_NEW`, and never calls the broker inside the loop.
3. Both `INSERT`s share the chunk transaction. An error after the first insert and before the second rolls back both when transactions are wired properly.
4. Both `ledger_entry.event_id` and `outbox_event.event_id` have unique constraints guarding restarts and replays.
5. The payload carries a **schema version**; downstream is built to parse that version. Exposing `accountId` and `amount` in the payload assumes security policy permits it.
6. `DO NOTHING` is this example's idempotency choice, **not a substitute for conflict detection**. In production, if the same `sourceEventId` arrives again with different values, detect and handle the mismatch instead of silently succeeding.

### Accepting Reality When the Writer Is Re-Invoked

Spring Batch may retry the writer in a fault-tolerant step or restart the same `JobInstance` after `FAILED`. `write(...)` can therefore receive records already persisted in a prior chunk or before metadata recorded a crash-time commit.

The business table's unique key blocks duplicate ledger rows, and the outbox unique key blocks creating a **second publication intent**. Still, because the dispatcher may deliver the same outbox row multiple times, consumer idempotency remains mandatory.

## 9. Why Not Publish Messages in `ItemWriteListener.afterWrite`?

A common idea:

~~~java
@Override
public void afterWrite(Chunk<? extends LedgerRecord> items) {
    publisher.send(items); // Not a post-commit guarantee.
}
~~~

`ItemWriteListener.afterWrite` typically fires **after the writer completes, but before the chunk transaction commits**. Publishing right there can send messages to the broker even if the subsequent commit fails and rolls back.

Moving publishing to an after-commit callback prevents sending on rollback, yet fails to solve **crashing after commit before the callback/send finishes**. Furthermore, publishing synchronously while holding a DB transaction open prolongs transactions, holds locks, and hurts throughput.

Therefore, when you must never lose notification intent, **do not treat in-JVM callbacks as durable storage**. Use committed outbox records or an equivalent durable queuing mechanism integrated into your consistency design.

## 10. How Does the Dispatcher Fetch Events?

Two common approaches:

**Polling publisher:** A service periodically queries unsent events from the outbox table, publishes them, and updates their status. Pros: straightforward when a database supports it; cons: must manage polling cadence, contention, retries, cleanup, and ordering.

**Change Data Capture (CDC):** A CDC connector tails the database transaction log and streams committed outbox inserts as messages. Pros: eliminates polling queries; cons: requires operating connectors, replication slots/log retention, schema mapping, snapshots/recovery, and handling duplicates/ordering.

Neither approach magically turns a two-resource problem into end-to-end exactly-once. Both rely on **stable event IDs**, dispatcher state management, and consumer idempotency.

### SQL Claiming So Multiple Dispatchers Do Not Grab the Same Event

When multiple dispatcher instances run concurrently, a naive `SELECT ... WHERE status='PENDING'` followed by send creates a race where two workers see the same row. Use transactional claiming with row-level locking. PostgreSQL example:

~~~sql
-- Execute this statement inside a short transaction.
WITH candidate AS (
    SELECT id
    FROM outbox_event
    WHERE status = 'PENDING'
       OR (status = 'IN_FLIGHT' AND locked_until < CURRENT_TIMESTAMP)
    ORDER BY created_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT :batchSize
)
UPDATE outbox_event AS o
SET status = 'IN_FLIGHT',
    owner_token = :ownerToken,
    locked_until = CURRENT_TIMESTAMP + INTERVAL '2 minutes',
    attempt_count = attempt_count + 1
FROM candidate AS c
WHERE o.id = c.id
RETURNING o.id, o.event_id, o.aggregate_key, o.event_type, o.payload;
~~~

This SQL is just **a sample lease-claiming pattern**, not a complete system:

- `FOR UPDATE SKIP LOCKED` avoids blocking on rows locked by other workers; keep the claim transaction short and commit immediately.
- After claiming, the dispatcher **publishes outside the claim transaction** so DB locks are never held across slow broker/network calls.
- `locked_until` allows reclaiming events if a worker crashes; however, when a lease expires, the old worker **might still be mid-send**.
- `owner_token` validates ownership when marking sent. Design lease renewal/timeouts and receiver idempotency.
- `attempt_count` aids retry policies and monitoring, yet **does not prove how many times consumers actually processed the event**.

Once the broker **acknowledges** receipt, the dispatcher marks `SENT` in a short transaction:

~~~sql
UPDATE outbox_event
SET status = 'SENT',
    sent_at = CURRENT_TIMESTAMP,
    owner_token = NULL,
    locked_until = NULL
WHERE id = :outboxId
  AND status = 'IN_FLIGHT'
  AND owner_token = :ownerToken;
~~~

If the updated row count is **0**, another worker may have reclaimed ownership or status changed. Inspect/reconcile rather than assuming the old worker still owns it.

If the broker client sends asynchronously and `send(...)` returns a future, **never mark `SENT` immediately after calling the method**; wait for publisher acknowledgment per contract. If the broker acks but the `markSent` transaction fails, the event may be re-sent. Expect this behavior rather than assuming locks eliminate all duplicates.

### Dispatcher Pseudocode

~~~java
// Pseudocode: repo.claim() and repo.markSent() each use short,
// separate transactions; publisher.sendAndAwaitAck() returns
// only after broker acknowledgment per contract.

void dispatchOne() {
    UUID owner = UUID.randomUUID();
    OutboxEvent event = outboxRepository.claimOne(owner);
    if (event == null) {
        return;
    }

    try {
        publisher.sendAndAwaitAck(
            event.eventId(),
            event.aggregateKey(),
            event.payload()
        );
        outboxRepository.markSent(event.id(), owner);
    } catch (TransientPublishException error) {
        outboxRepository.recordFailure(event.id(), owner, error);
        // Preserve retryability and expose backlog to monitoring.
    }
}
~~~

Interfaces, records, and exceptions in this snippet are **application concepts**, not built-in Spring Batch APIs. Real implementations need backoff rules, timeouts, lease renewal, max attempts, crash handling, and safe logging. Never infinitely retry permanently broken messages to the point of clogging the queue.

### "Mark SENT First, Then Send" Is an Anti-Pattern

~~~text
Mark SENT -> DB commit -> crash -> not sent to broker
~~~

Events can be lost permanently if the dispatcher only polls `PENDING`. The sound rule is **send and await acknowledgment first, then mark sent**—accepting redelivery risk and neutralizing it with idempotency.

## 11. Consumers Need Idempotency

Suppose the dispatcher sends `LedgerPosted(eventId=LEDGER_POSTED:TX-001)`, the broker acks, and the app crashes before updating the outbox to `SENT`. After restart, the event is sent a second time. If the consumer runs:

~~~sql
UPDATE account_summary
SET total = total + :amount
WHERE account_id = :accountId;
~~~

receiving the same event twice adds the amount twice. The consumer must persist a marker that **this event ID was already processed** inside the exact same transaction as the business update, or use another idempotent operation.

PostgreSQL example:

~~~sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(80) NOT NULL,
    event_id VARCHAR(140) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Inside one consumer transaction:

~~~text
BEGIN
  INSERT processed_event(consumer_name, event_id)
    ON CONFLICT DO NOTHING;

  If INSERT creates a new row:
      UPDATE summary for event
  If INSERT creates no row:
      Event already processed -> do not update summary again
COMMIT
ACK message after commit
~~~

Mandatory condition: **the marker insert and the business output update share the exact same database transaction**. If the marker commits first while the summary update fails, the consumer treats the event as processed even though data never updated. If the summary commits before the marker, retries duplicate the update.

### Consumer Example with JdbcTemplate

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class LedgerEventConsumerService {

    private final JdbcTemplate jdbc;

    public LedgerEventConsumerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public boolean apply(
            String consumerName,
            String eventId,
            String accountId,
            java.math.BigDecimal amount) {

        int inserted = jdbc.update("""
            INSERT INTO processed_event(consumer_name, event_id)
            VALUES (?, ?)
            ON CONFLICT DO NOTHING
            """,
            consumerName, eventId
        );

        if (inserted == 0) {
            return false; // Duplicate event, do not apply again.
        }

        int updated = jdbc.update("""
            UPDATE account_summary
            SET total = total + ?
            WHERE account_id = ?
            """,
            amount, accountId
        );

        if (updated != 1) {
            throw new IllegalStateException("ACCOUNT_SUMMARY_MISSING");
        }

        return true;
    }
}
~~~

This example assumes `processed_event` and `account_summary` share the same database/transaction manager, Spring transaction management is active, and `apply(...)` is invoked through a Spring proxy. If the summary update fails, the exception rolls back **both the marker and the summary update**, allowing safe retry.

Consumers must ACK messages per broker API **after** the business transaction commits; exact ACK semantics depend on Kafka, RabbitMQ, or your broker. If a consumer calls an external API outside a transaction, a local DB marker table still cannot guarantee atomicity with that API—you must rely on API-side idempotency keys, remote state checks, or saga/compensation patterns.

**Idempotent consumers** do not merely protect against outbox duplicates: they also protect against broker retries, consumer crashes after commit, redeliveries, and offset replays.

## 12. Failure Matrix: Transaction vs. Outbox

To choose correctly, trace every point where a process can die:

| Failure Point | DB Transaction Only | DB + Transactional Outbox | Extra Caution Needed |
|---|---|---|---|
| Writer fails before commit | Chunk rolls back. | Business row and outbox row both roll back. | Requires genuinely sharing the same transaction. |
| Writer succeeds, commit fails | Do not assume data saved. | Do not assume either saved. | On ambiguous commit outcome, verify by business key. |
| Commit succeeds, process crashes right after | Data is in DB. | Data and `PENDING` event both exist. | Dispatcher can proceed independently. |
| Broker/API unavailable | No publish needed if DB-only. | Events queue up; retried later. | Alerts, retention, backoff, capacity. |
| Broker acks message, dispatcher crashes | N/A if not publishing. | May redeliver same event. | Consumer idempotency. |
| Dispatcher fails to mark `SENT` | N/A. | May redeliver even though broker acked. | Do not treat as a lost-event error. |
| Consumer commits, crashes before broker ACK | N/A. | Broker may redeliver. | Consumer marker + business update in one transaction. |
| Multiple dispatchers | N/A. | Needs claim/lease or CDC coordination. | Locking does not replace idempotency. |
| Job restarts / item replays | Writer needs unique keys to avoid duplicates. | Both business keys and outbox event keys must be stable. | Never derive event IDs from execution ID. |

This matrix holds under the stated technical assumptions. For multi-datasource, file, or non-transactional HTTP writers, analyze each target explicitly. **A `@Transactional` annotation in code does not prove target systems actually commit together.**

## 13. Spring Batch Restart When Outbox Already Holds Events

Suppose a `JobInstance` processes `businessDate=2026-11-15`:

~~~text
JobInstance 410
  |
  +-- JobExecution 8102 FAILED
  |     chunk 1: ledger + outbox COMMITTED
  |     chunk 2: ROLLBACK
  |
  +-- JobExecution 8103 COMPLETED
        restart same instance; resume from checkpoint
~~~

On restart:

- Chunk 1 may already exist in both DB and outbox; never mint new event IDs for the same transaction.
- A record may replay through reader/writer due to checkpoint boundaries or ambiguous commit outcomes. Unique DB business keys and outbox event keys curb duplicates.
- The dispatcher **does not depend directly on `JobExecution`** to know what to publish; it acts on committed outbox rows.
- `JobExecution 8103 COMPLETED` does not mean every outbox event has been broker-acked or consumed.
- Never delete `BATCH_*` metadata and rerun with a random `run.id` to "work around" a tricky restart. Preserve the `JobInstance` and reconcile committed outputs.

### Metadata Repo May Live in a Different Database

If `JobRepository` uses Database A while ledger/outbox uses Database B, checkpoint transactions and business transactions **are not automatically a single atomic transaction**. On a crash, Database B may have committed while metadata in A has not yet recorded full progress.

This is another reason to maintain **idempotent business writers** and **reconciliation**, even when using an outbox. If single-transaction atomicity between repository and output is a strict requirement, wire datasources and transaction boundaries accordingly—never assume naming two transaction managers similarly unifies them.

## 14. Outbox and Whole-Batch Atomicity

An easily overlooked detail: **a Spring Batch chunk transaction is not a job-wide transaction**. With chunk size 100, after chunk 1 the database commits ledger rows and outbox events; the dispatcher may start publishing immediately while the job is still working on chunk 2.

~~~text
T1 chunk 1 commits -> outbox events start dispatching
T2 downstream consumes partial results
T3 chunk 2 fails -> JobExecution FAILED
~~~

If business rules allow incremental streaming output, this is fine. However, if the requirement is **"only publish data after the entire batch reconciles successfully,"** add a **publish gate**:

1. Writer persists ledger or staging rows and outbox intents keyed by `batchKey`.
2. Events are ineligible for dispatch until the batch is approved—or the writer writes staging only without creating publication events yet.
3. A reconciliation step checks counts, sums, business keys, and reject policies.
4. Once passed, a single transaction marks the batch `APPROVED` and inserts the outbox events to publish—or inserts one `BatchPublished` event describing the ready version.
5. The dispatcher publishes only events eligible under status and publication contracts.

Architectural diagram:

~~~mermaid
flowchart TD
    A["Load chunks -> staging by batchKey"] --> B["Reconcile data quality"]
    B --> C{"PASS?"}
    C -->|No| D["Mark FAIL / do not publish"]
    C -->|Yes| E["DB transaction: mark APPROVED\n+ insert BatchPublished outbox event"]
    E --> F["Dispatcher"]
    F --> G["Consumers read approved batch version"]
~~~

**You do not always need one outbox event per item.** If downstream only needs to know the full dataset is ready in the DB, a single `BatchPublished` event per `batchKey/version` can be far simpler than millions of per-item events. Conversely, if consumers process individual transactions with low per-item latency goals, per-item events fit better. Choose **granularity** per contract.

## 15. Ordering, Duplicates, and Schema Evolution

### Event Ordering

Suppose one account has two events:

~~~text
Account A:
  event 1 -> increase balance
  event 2 -> close account
~~~

Parallel dispatchers can deliver event 2 before event 1 if they simply select by `created_at` across independent workers. `ORDER BY created_at` in a polling query **does not guarantee broker/consumer ordering** once multiple dispatchers, retries, or partitions exist.

Options:

- Use `aggregate_key` as the message partition/routing key so the broker preserves per-partition ordering when properly configured.
- Include a monotonically controlled `aggregate_version` or sequence so consumers validate order before applying.
- Allow only one worker to process a given aggregate at a time when strict ordering is required.
- When strict ordering across retries is required, block later-version events until earlier ones are confirmed rather than relying solely on query sorting.

Never rely solely on a raw timestamp to prove total order across concurrent transactions, especially across nodes with independent clocks.

### Event Schema

Payloads should include `eventType`, `schemaVersion`, business/event IDs, and required fields. When schemas evolve, the outbox may still contain `PENDING` events generated under an older version, so consumers must remain backward-compatible or handle versioned migrations.

Never blindly serialize entire JPA/domain entities if they might leak passwords, PII, or internal fields outside the contract. Outbox payloads persist in the DB and flow to brokers; restrict fields, permissions, and retention.

### Duplicates Are Normal State to Handle

Even with rock-solid row-lock claiming on the outbox, duplicates still arise from crashes between publish ACK and `markSent`. Design from day one so delivering the same event twice **never corrupts final business state**.

## 16. Polling vs. CDC?

| Criterion | Polling Publisher | CDC Outbox |
|---|---|---|
| Mechanism | Periodically queries outbox table, claims/leases, sends. | Tails DB transaction log and emits committed changes as events. |
| Initial setup | Easy to understand with SQL/worker infra. | Requires connectors, privileges, and change-stream operations. |
| Latency | Depends on polling interval and backlog. | Can be low, depending on CDC pipeline and load. |
| Database load | Periodic queries, index scans, cleanup. | Log reading plus replication/CDC resource overhead. |
| Multi-worker | Needs claiming, leases, backoff, concurrency handling. | Needs proper connector/partition/ownership setup. |
| Ordering | Must design by aggregate/partition. | Also requires source-to-broker ordering design. |
| Duplicates/replay | Redelivery possible after crashes or lease expiry. | Redelivery possible after failovers or offset recovery. |
| Operations | Monitor backlog, stuck leases, dead events. | Monitor lag, connector health, replication slot/log retention. |

CDC does not exempt consumers from idempotency. Moreover, if CDC tails an outbox table whose `status` updates multiple times, configure it to emit **only the intended business event** (e.g., row insert / event envelope) rather than turning every status update into a downstream message.

## 17. When Should Other Options Be Considered?

### 17.1. Best-Effort Direct Publishing

If dropping a notification does not break correctness, or downstream periodically reconciles full state from the DB anyway, direct publishing may be acceptable. However, **explicitly document the tolerance for lost/drifted events**—never describe it as an exactly-once guarantee.

### 17.2. Broker-Only Output

If the job **only** produces messages and does not commit business state in another DB, broker producer transactions/acks may suffice per contract. That avoids the DB+broker dual-write problem altogether. Even with producer transactions, consumers must still handle replays/offsets and protect final outputs; producer transactions do not automatically make all downstream side effects exactly-once.

### 17.3. Two-Phase Commit (XA/2PC)

Where a single logical transaction must span multiple **XA-capable** resources, JTA/XA and two-phase commit can be evaluated. However:

- Every resource, driver, and broker must properly support XA.
- Setup, transaction recovery, and operations are complex.
- Risks blocking, coordinator failures, and lower throughput.
- Many external APIs and object stores cannot participate in XA.

For most event-driven systems, transactional outbox is simpler to operate and matches eventual consistency—yet that does not mean XA is "always wrong" or outbox is "always right." Base the choice on real atomicity requirements and resource capabilities.

### 17.4. Sagas and Compensation

When a business flow spans multiple services without a global transaction, apply sagas, compensating actions, and idempotency. Outbox can serve as the **durable event emitter** for each saga step, though it does not replace compensation logic.

### 17.5. Files / Object Storage

If outputs are CSVs, Parquet files, or objects on object storage, DB transactions do not automatically roll back files. A clean pattern is:

- Write to a temporary/unlisted path or version hidden from consumers.
- Validate row counts, checksums, and schemas.
- Publish the manifest/pointer only after the file completes and passes quality gates.
- Maintain cleanup for orphaned temp files alongside retry/idempotency.

An outbox is only needed if you must also emit a "file ready" event to another system. Atomic rename depends on the filesystem and source/target locations; never assume an object-storage move is atomic with a DB commit.

## 18. Performance and Operational Cost

### Cost of Transactional Output

Writing within one DB chunk transaction is generally simpler, yet still requires:

- Choosing `chunkSize` to balance commits, memory, lock duration, and rollback cost.
- Capping connection pools and partition concurrency.
- Creating indexes and unique constraints for business keys.
- Configuring timeouts, lock waits, and targeted retries—never infinite retries.
- Monitoring commit/rollback counts and reconciling ambiguous commit outcomes.

### Cost of Outbox

Adding an outbox introduces write amplification: every business write may add an event row, index entries, and transaction log bytes. Also account for:

- Storage for `PENDING`/`SENT` rows, table bloat, index maintenance, and retention.
- Dispatcher throughput and events-per-second limits.
- Broker quotas, publish timeouts, and retry backoffs.
- Monitoring serialization/schema failures and "poison" events.
- Consumer-side duplicate handling.
- Reconciliation cost if source and target drift.

If a job produces tens of millions of events, benchmark throughput across the DB writer, outbox publisher, broker, and consumers together. `JobExecution.COMPLETED` may occur long before the dispatcher drains its backlog; **end-to-end completion speed may be bottlenecked externally**, not in the chunk writer.

### Outbox Must Not Become an "Unbounded SENT Table"

Once events are `SENT` and past required audit/replay windows, archive or purge them per policy:

- Never delete `PENDING` or `IN_FLIGHT` rows awaiting delivery.
- Never purge events still needed for reconciliation or replays.
- Purge in controlled chunks/partitions to avoid massive delete transactions.
- With CDC, check how table cleanup interacts with replication logs and connectors.

Retention schedules should come from SLAs, audit rules, and recovery goals—not merely keeping the table small.

## 19. Monitoring Must Track Two Separate Lifecycles

When using an outbox, there are **two distinct notions of success**:

1. **Batch output persisted:** business rows and event intents committed.
2. **Event delivered/consumed:** dispatcher published events and downstream processed them per contract.

Never display a single `COMPLETED` indicator for both.

| Lifecycle | Signals to Monitor |
|---|---|
| Spring Batch step | `readCount`, `writeCount`, `commitCount`, `rollbackCount`, `BatchStatus`, `ExitStatus`. |
| Business DB outcome | Row counts/sums by business key, unique business IDs, mismatches/rejects. |
| Outbox pending | `PENDING` count, age of oldest unsent event, backlog by event type. |
| Dispatcher | Publish attempts, successes/failures, retries, expired claim leases. |
| Dead-letter / quarantine | `DEAD` event count, normalized failure reasons, incident age. |
| Broker | ACKs/nacks, latency, redeliveries, per-partition consumer lag. |
| Consumer | Deduplicated duplicates ignored, successful applies, business errors, target state. |
| End-to-end | Lag from business DB commit to consumer result; missing/extra counts via reconciliation. |

A safe outbox log entry:

~~~json
{
  "event": "outbox.dispatch.completed",
  "jobName": "dailyLedgerJob",
  "batchKey": "2026-11-15:store-A",
  "jobExecutionId": 8102,
  "outboxId": 12005,
  "eventId": "LEDGER_POSTED:TX-001",
  "eventType": "LEDGER_POSTED",
  "attempt": 2,
  "result": "SENT",
  "durationMs": 48
}
~~~

This is an **application-defined schema**, not a default Spring Batch log. Review event IDs and business keys against data classification rules before logging; never log full payloads containing PII or secrets. If `JobRepository` and the dispatcher live in separate processes, store correlation fields durably or include them in the outbox envelope.

Never put `eventId`, `jobExecutionId`, or unique correlation IDs into regular metric labels, as cardinality explodes. Keep detailed IDs in logs, audits, and traces, while metrics use bounded labels like `eventType`, `status`, and error category.

## 20. Testing Critical Failures

A trustworthy outbox test suite cannot test only the happy path. Inject failures at exact boundaries and inspect **committed database state**, including across restarts.

| Scenario | How to Inject Failure | Invariant to Assert |
|---|---|---|
| Writer DB error before outbox insert | SQL constraint or intentional exception | Zero business rows and zero outbox rows after chunk rollback. |
| Error after business insert, before outbox insert | Throw inside writer between the two statements | Both roll back when sharing the transaction. |
| Error after outbox insert, before commit | Throw after the second statement | Both roll back; zero orphaned intents. |
| Commit succeeds, job process crashes | Halt process right after commit in controlled test | Business row and `PENDING` outbox persist; dispatcher still delivers. |
| Job restarts / replays same event | Re-invoke with same business ID | Zero duplicate ledger or outbox rows. |
| Two writers concurrently process same business event | Concurrency test against DB unique constraint | Exactly one business result and one valid event intent. |
| Broker temporarily offline | Fake publisher throws error | Outbox row retained; retry/backoff and backlog visible. |
| Publish ACK succeeds, `markSent` fails | Fault injection right after ACK | Event may redeliver; consumer applies effect only once. |
| Consumer receives duplicate | Deliver same event ID twice | Business output applied exactly once. |
| Dispatcher crashes while holding lease | Kill worker after claim | Event reclaimed after lease timeout without loss. |
| Two dispatchers run concurrently | Both claim `PENDING` | Zero duplicate consumer business effects; consistent lease ownership. |
| Poison event | Incompatible payload or permanent error | Moves to `DEAD`/quarantine per policy with alerts; never silently disappears. |
| Event ordering | Two events for same aggregate, retry earlier event | Consumer applies in order or detects sequence gap per contract. |
| Reconciliation gate fails | Output count/sum mismatch | `BatchPublished` is never emitted as successful. |

### Testing Real Rollbacks

In an integration test, use a test writer that inserts into `ledger_entry` and throws before inserting into `outbox_event`. Once the chunk rolls back, query the database after the step and assert:

~~~sql
SELECT COUNT(*)
FROM ledger_entry
WHERE event_id = 'TX-TEST-1';

SELECT COUNT(*)
FROM outbox_event
WHERE event_id = 'LEDGER_POSTED:TX-TEST-1';
~~~

Both counts must equal **0** when rollback, datasource/transaction manager wiring, and clean test fixtures are right. Never assert only that Spring Batch reported `FAILED` and assume rollback worked: a writer might accidentally be using its own auto-commit connection.

### Testing Happy Path with Duplicate Delivery

1. Run batch with one event `TX-TEST-1`.
2. Verify DB contains one ledger row and one `PENDING` outbox row.
3. Dispatcher sends event; consumer applies result and commits.
4. Simulate failure right before updating `SENT` on outbox.
5. Let dispatcher redeliver the exact same event ID.
6. Assert consumer output still reflects **exactly one business effect** and the processed-event marker is not duplicated.

This test proves the idempotency required under **at-least-once** outbox delivery, rather than just checking that the dispatcher called the publisher once on the happy path.

### Testing a Batch-Level Publish Gate

Prepare three inputs where one record causes a policy-breaching writer reject or breaks the manifest total sum. After loading, reconciliation must end `FAILED` or fail the quality gate; consumers must **not** receive a successful `BatchPublished` event for that version. If per-item events escaped before the gate ran, the architecture failed the "publish only after the whole batch passes" requirement.

## 21. Choosing Architecture by Scenario

| Scenario | Suitable Starting Approach | What to Verify |
|---|---|---|
| CSV import into one PostgreSQL table | **Output transaction** with JDBC writer, unique keys, reconciliation | Reader/writer share transaction manager; restarts cause zero duplicates. |
| Job writes multiple tables in one database | **Single chunk transaction** | No self-committing delegates; proper constraints. |
| Write DB and emit Kafka events | **DB transaction + outbox** | Stable event IDs, dispatcher, idempotent consumer, backlog monitoring. |
| Write DB and call mandatory partner API | **Outbox/intent + dispatcher** when API supports idempotency/status lookup | Timeout ambiguity, retries, eventual consistency, compensation. |
| Emit events to broker only | Use **broker producer semantics** per requirements | Never confuse broker transactions with separate DB transactions. |
| Write CSV file and publish upon completion | **Temp file + validation + manifest/rename publish** | Storage atomicity/visibility; crash cleanup. |
| Compute whole batch then notify readiness | **Staging + reconciliation gate + `BatchPublished` outbox event** | Zero success events emitted before quality gate passes. |
| Sync multiple DBs or services | Evaluate **outbox, saga/compensation, or XA if all support it** | Concrete latency/atomicity requirements and ops cost. |

### Decision Flow

~~~mermaid
flowchart TD
    A["What does the output actually include?"] --> B{"Single transactional\nresource only?"}
    B -->|Yes| C["Use chunk transaction\n+ idempotent writer"]
    B -->|No| D{"Is asynchronous\ndelivery acceptable?"}
    D -->|Yes| E{"Is there a source-of-truth DB\nto commit intent?"}
    E -->|Yes| F["DB transaction + outbox\n+ at-least-once dispatcher\n+ idempotent consumer"]
    E -->|No| G["Design other durable intent\nor suitable messaging pattern"]
    D -->|No| H["Re-examine atomicity requirements\nXA if universally supported\nor design compensation"]
    C --> I["Test crash/restart\nand reconciliation"]
    F --> I
    G --> I
    H --> I
~~~

**Do not use an outbox merely because your system has a message broker.** If a job only reads data and publishes messages without committing business state to a database, there may be no dual-write problem for an outbox to solve. Conversely, if durable DB + broker consistency is required, direct sending inside `@Transactional` generally fails atomicity.

## 22. Common Mistakes

**"Outbox replaces database transactions."** False: outbox **requires the same transaction** to commit both the business row and event intent. Separate transactions break the initial atomicity guarantee.

**"`@Transactional` around `save()` and `send()` is enough."** False if the broker or API does not join a compatible transaction coordinator. Database rollback does not recall an already-received message.

**"Sending in `afterWrite` guarantees data is committed."** That callback normally runs before chunk commit; publishing there can emit events while the DB can still roll back.

**"Sending in `afterCommit` can never lose an event."** The process can still crash after commit before the callback/send completes. Durable intent is required when eventual delivery is mandatory.

**"A dispatcher lock prevents all duplicates."** Locks reduce claim contention; crashing between publish ACK and `markSent` still produces duplicates. Idempotent consumers remain mandatory for once-only business effects.

**"Just mark `SENT` before sending to avoid duplicates."** Crashing after marking loses the event permanently. Always send and await ACK first, then mark sent, handling redelivery via idempotency.

**"A `COMPLETED` `JobExecution` means every message reached consumers."** Outbox has its own lifecycle; the batch can finish while a backlog remains undispatched. Monitor delivery and reconcile.

**"Generating a fresh UUID on every retry is best."** For an already-processed event, a new UUID defeats unique-event deduplication. Keep event keys stable by business identity.

**"Having an outbox means the ledger needs no unique business key."** Writers can still replay after crashes or restarts; the ledger must protect its own outputs against duplicates.

**"Polling with `ORDER BY created_at` preserves ordering."** Across multiple dispatchers, lease expiries, broker partitions, and retries, order can shift. Enforce explicit sequence/aggregate rules if ordering is an invariant.

**"Per-item outbox events are always better than `BatchPublished`."** False. When publishing only after reconciliation, a single batch-level event or staging pattern is often superior.

**"Deleting all `SENT` events immediately is fine."** Retention and cleanup must respect audits, replays, CDC connectors, and recovery windows; never purge unhandled `PENDING` or `DEAD` rows just to save space.

**"Dumping the entire domain object into the payload is convenient."** It risks leaking sensitive fields and coupling consumers to internal schemas; export only fields defined by a versioned event contract.

## 23. Step-by-Step Implementation Workflow

1. **Document business invariants.** Specify business keys, zero-event-loss rules, acceptable latency, ordering, and duplicate tolerance.
2. **Draw transaction boundaries.** Which resources join the chunk transaction? Do `JobRepository` and the business DB match? Are any operations auto-committing?
3. **Select the output pattern.** Single DB → transaction + idempotent writer. Reliable DB + broker/API → add outbox inside the same transaction.
4. **Define the event contract.** Stable event ID, aggregate key, schema version, allowed payload fields, and consumer deduplication fields.
5. **Protect writers on restart.** Unique constraints / conditional updates, preserved identifying `JobParameters`, and payload conflict checks.
6. **Design the dispatcher.** Claim/lease or CDC, ack confirmation, retry/backoff, dead-letter/quarantine, retention, and concurrency limits.
7. **Design idempotent consumers.** Processed-event markers inside the target business transaction or target-side idempotency keys, ACKing only after commit.
8. **Decide publication granularity.** Per-item events vs. a single post-reconciliation batch event; keep consumers away from unapproved data if atomic batch publication is required.
9. **Add monitoring.** Separate batch persistence from event delivery; track backlogs, pending age, publish errors, and target outcomes.
10. **Test crashes and retries.** Inject faults before/after DB commit, after broker ACK, on lease expiry, consumer redelivery, and job restarts.
11. **Write operational runbooks.** When to replay events, when to quarantine, how to look up events by business key, and how to resolve mismatches without creating duplicates.

## Conclusion

**Choosing output transaction vs. outbox** comes down to choosing **the consistency boundary** for your Spring Batch output. When a job only modifies data within one database transaction, a properly wired transactional writer, unique business keys, and output verification form a simple, robust, easy-to-operate solution. When a job must **persist data and durably notify another system**, transactional outbox closes the crash window between DB commit and message publish by committing *event intent* in the business transaction.

Outbox does not magically deliver end-to-end exactly-once: dispatchers can still redeliver, consumers must be idempotent, and a `COMPLETED` batch does not mean downstream has processed every event. Only when transaction boundaries, retry/restart semantics, event keys, publish gates, ordering, and monitoring are explicitly engineered does either choice deliver the consistency the business requires—rather than merely letting the job finish technically green.
