# Write-ahead or outbox output

In Spring Batch, a processing step typically reads data, transforms it, and writes results to one or more destinations: a database, a message broker, an external API, or a storage system. The challenge arises when a single processing unit must update multiple resources that do not participate in the same transaction. For example, a batch updates an order status in the database and then sends an `OrderProcessed` event to Kafka. If the database commits successfully but the application stops before sending the message, the business state and the event-receiving system become inconsistent. If the message is sent first and the database rolls back, the receiving system may process an event for a change that was never committed.

Write-ahead and transactional outbox are two ways to organize output to close this gap. Both durably record the intent or result to be emitted before performing the external emission step. They solve related problems but are not identical: write-ahead generally emphasizes a write-ahead log and recoverability, whereas outbox is a specific integration pattern in which an event record is saved in the same transaction as business data and another process forwards that event.

## Consistency problem when writing multiple outputs

Suppose a chunk processes 100 transactions. For each transaction, the batch needs to:

1. Update a business record in the database.
2. Send an event to a broker so other services can continue processing.

If the two operations use two independent transactional systems, no call ordering alone guarantees that both succeed together. Sending first and then updating the database creates the risk of emitting an event for uncommitted data. Updating the database first and then sending creates the risk of losing the event after the database commits.

| Operation order | Possible failure point | Consequence |
|---|---|---|
| Send message, then commit database | Message received by broker, but database rolls back | Consumer sees an event that does not match committed state |
| Commit database, then send message | Database commits, process stops before sending | Data changed without an emitted event |
| Write output directly in writer | Writer or chunk retried after partial failure | Duplicate writes or partially completed outputs possible |

The chunk transaction boundary in Spring Batch typically manages resource operations participating in the transaction manager configured for the step. Do not infer that an HTTP call or a broker publish automatically rolls back with the database. You must clearly identify which resources participate in the transaction, which transaction manager coordinates them, and what happens if the process dies between two operations.

## Write-ahead: durable recording before emitting output

Write-ahead is the principle of writing necessary information to durable storage before performing a change or externally observable action. The pre-committed log serves as proof so a process can resume or replay work after a failure.

A write-ahead record may contain:

- A unique identifier for the output or task.
- Event type and the business entity's key.
- Payload or data sufficient to reconstruct the output.
- Processing status, creation timestamp, and attempt count.
- Information needed to determine whether the output has been acknowledged or still needs replay.

General flow:

```text
Read item
   |
   v
Create intent/output record in durable store
   |
   v
Commit write-ahead record
   |
   v
Emit output to external destination
   |
   v
Record sent result or retry needed
```

If the application stops after committing the log but before emitting output, a recovery process can find incomplete records and continue. If the application stops after the destination accepts the output but before the log is marked complete, recovery may resend it. Thus, write-ahead prevents losing track of work, though it does not automatically guarantee the output is emitted only once. The destination or consumer still needs to support idempotency, or a reconciliation mechanism must exist.

Write-ahead log is a broad concept used in databases and many storage systems to guarantee durability and recovery. In a batch application, you can build an application-level task log for output; distinguish this application log from the database's internal WAL. The database WAL protects the durability of database changes, but does not automatically record the intent to send a message to an independent broker.

## Transactional outbox

Transactional outbox applies the write-ahead principle to the problem of updating a database and emitting events. Instead of publishing an event directly inside the business transaction, the application writes a record to an outbox table in the same transaction as the business change. A separate publisher reads unsent records and forwards them to the broker.

For example, when processing an order, the same database transaction will:

1. Update the order status to `PROCESSED`.
2. Insert an `OrderProcessed` event into the `outbox_event` table.
3. Commit both changes.

If the transaction rolls back, neither the order status nor the outbox record exists as a committed change. If the transaction commits, the event is durably saved and the publisher can send it even if the batch stops immediately afterward.

### Designing the outbox table

A simple structure might look like this:

```sql
CREATE TABLE outbox_event (
    event_id       VARCHAR(64) PRIMARY KEY,
    aggregate_id   VARCHAR(64) NOT NULL,
    event_type     VARCHAR(120) NOT NULL,
    payload        TEXT NOT NULL,
    created_at     TIMESTAMP NOT NULL,
    published_at   TIMESTAMP NULL,
    attempt_count  INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_outbox_unpublished
    ON outbox_event (published_at, created_at);
```

`event_id` is a stable identifier so the publisher and consumer can recognize duplicate deliveries. `aggregate_id` links the event to the business entity, such as an order ID. `payload` stores the event body or enough data to construct the message. `published_at` indicates the publisher recorded a successful send; `attempt_count` supports retry tracking. For high-load systems, you can add claim/lease status, `next_attempt_at`, last error details, schema version, and indexes tailored to polling queries.

Do not rely solely on `published_at` as a concurrency lock if multiple publishers run. Workers could read the same unsent row simultaneously. Claim records atomically—for example, using `SELECT ... FOR UPDATE SKIP LOCKED` if the database supports it, or using a lease/claim token column with conditional updates. Syntax and support depend on the database.

### Writing business data and outbox in the same transaction

In Spring Batch, writing business data and inserting into the outbox should run on the same database connection/transaction managed by the step's transaction manager. The illustrative example below uses `JdbcTemplate`; domain classes and SQL must be adapted to the actual application.

```java
public record ProcessedOrder(
        String orderId,
        String eventId,
        String eventPayload) {
}

public class OrderAndOutboxWriter
        implements ItemWriter<ProcessedOrder> {

    private final JdbcTemplate jdbcTemplate;

    public OrderAndOutboxWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void write(Chunk<? extends ProcessedOrder> chunk) {
        for (ProcessedOrder item : chunk) {
            jdbcTemplate.update(
                "UPDATE orders SET status = ? WHERE order_id = ?",
                "PROCESSED", item.orderId());

            jdbcTemplate.update("""
                INSERT INTO outbox_event
                    (event_id, aggregate_id, event_type, payload, created_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                item.eventId(),
                item.orderId(),
                "OrderProcessed",
                item.eventPayload());
        }
    }
}
```

The code illustrates the principle: the writer only writes to the database and does not call the broker. For both statements to truly commit or roll back together, `JdbcTemplate` must use the `DataSource` bound to the step's transaction manager. If the writer writes through a different datasource or a different transaction manager, atomicity is no longer guaranteed as shown in the example. In real implementations, verify the active step, datasource, and transaction manager configuration.

`eventId` must remain stable across retries. If each writer call generates a new UUID, a retry can create multiple outbox records for the same business event. You can derive the event ID from the business identifier and event type/version, or persist a pre-generated ID during processing so it stays identical across retries. Adding an appropriate unique constraint helps the database reject duplicates, though conflict-handling logic must still be explicitly designed.

### Publisher relaying the outbox

An independent publisher can run on a schedule or as a background process. It fetches a batch of unsent events, claims them, publishes them to the broker, and marks them sent after receiving appropriate broker confirmation.

```text
Outbox table
    |
    v
Publisher claims a batch of records
    |
    v
Publish each message (with event_id)
    |
    v
Broker acknowledges message receipt
    |
    v
Mark published_at and release claim
```

The order between publishing and updating status is critical. Marking an event as sent before broker confirmation can lose messages on failure. If the broker receives the message but the publisher stops before marking it, the publisher will resend on the next run. Consequently, common implementations prioritize not losing events and accept at-least-once delivery. Consumers must handle duplicate messages safely.

Illustrative pseudo-code:

```java
for (OutboxEvent event : outboxRepository.claimBatch(batchSize)) {
    try {
        brokerPublisher.publish(event.eventId(), event.payload());
        outboxRepository.markPublished(event.eventId());
    } catch (TransientPublishException ex) {
        outboxRepository.recordFailure(event.eventId(), ex.getMessage());
        // Allow the event to be retried according to the retry policy.
    }
}
```

This is a flow sketch, not a complete implementation for every broker. You must verify whether `publish` returns after broker confirmation or merely after queuing the request in a client buffer. With asynchronous APIs, the publisher must wait for the confirmation result before marking the record. Because publishing and updating the outbox live in two independent transactional systems, a failure window between them still exists; an idempotent consumer is a necessary safeguard.

## Idempotent consumers and duplicate message handling

An outbox typically provides at-least-once semantics. A consumer may receive the same `event_id` multiple times when the publisher retries or the broker redelivers. The consumer should record a processed marker in the same transaction as its own business update.

Example inbox table:

```sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(120) NOT NULL,
    event_id      VARCHAR(64) NOT NULL,
    processed_at  TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Upon receiving a message, the consumer starts a transaction, attempts to insert the `(consumer_name, event_id)` pair, and executes the business change only if the insert succeeds. If the key already exists, the message was processed previously and can be acknowledged without re-running business logic. Inserting the processed marker and updating data must share the same transaction; separating them means a failure between the two operations can cause the consumer to skip work or apply it twice.

Idempotency can also be implemented using conditional updates, upserts, or target APIs accepting an idempotency key. Choose keys according to business semantics: the same event resent must carry the same key, whereas two distinct valid events must carry distinct keys.

## Applying in Spring Batch

There are several ways to arrange an outbox around jobs and steps:

- **Write outbox directly in the business step's writer:** suitable when business data and outbox live in the same database and share a transaction. This is usually the simplest option because chunk commit/rollback covers both record types.
- **Use a separate step to relay the outbox:** a subsequent step reads pending outbox records and sends messages. This suits workflows wanting message emission managed as part of the job, though claiming, retries, and status updates require careful handling.
- **Use an independently running publisher:** suitable when events must be emitted continuously without waiting for the next batch run. The publisher can be a background service or scheduled task sharing the outbox table.

Do not call external services directly from an `ItemWriter` and assume chunk rollback will retract that call. An HTTP request already processed by a remote system generally cannot be rolled back by a database. If you must write files, call APIs, or emit messages, consider whether you can write a durable directive into the database first and let a dedicated component execute the output and record the outcome.

### Retry, skip, and restart

Spring Batch can retry an item or chunk depending on configuration, and can restart a job from saved state. This makes safe repeatability an essential requirement:

- Generate stable output identifiers that do not change across retries/restarts of the same event.
- Put a unique constraint on the event key to prevent unintended duplicate outbox rows.
- Ensure transaction rollback removes both business changes and outbox rows when a chunk fails.
- Do not mark outbox rows as sent before receiving appropriate confirmation from the broker.
- Design retries with sensible backoff and limits; persistent failures must be stored for investigation or moved to an intervention state.
- If an item is skipped, define clearly whether an error/skip event should be emitted. Do not automatically emit a success event for an item that did not complete business processing.

For job restarts, Spring Batch's repository stores execution state to coordinate resuming steps, but that repository does not replace a business outbox. Job state indicates how far batch progress reached; the outbox table records events waiting to be forwarded. The two mechanisms serve different purposes and must be kept consistent.

## Event ordering and parallel processing

If events for the same order must be processed in order, the publisher needs to preserve order by `aggregate_id` or a business sequence. Sorting solely by `created_at` may not suffice when concurrent transactions create events or timestamp resolution is coarse. You can store an incrementing sequence per aggregate and then partition messages by aggregate key so the broker preserves ordering within a partition.

When multiple publishers run in parallel, prevent two publishers from emitting the same record under normal conditions. Claiming via row locks, `SKIP LOCKED`, timed leases, or partitioning schemes are options. Leases need timeouts and tokens so an old publisher cannot update status after claim ownership transferred to another worker. Even with proper claiming, a crash after broker receipt can still cause duplicate sends; idempotent consumers remain necessary.

## Operating and maintaining an outbox

An outbox is part of the data path and must be monitored like a queue. Useful metrics include:

- Number of unpublished records.
- Age of the oldest unpublished record.
- Latency from creation to broker confirmation.
- Publish failure rate, attempt counts, and records requiring intervention.
- Event creation rate versus publisher processing rate.

If backlog grows continuously, the publisher is processing slower than the batch creates events or the broker is having issues. Set alerts on backlog age and growth rate, as simple counts may not reflect latency for systems with variable traffic.

Published records can be retained for a period for reconciliation and then purged in batches. Retention policies must account for replay needs, audit requirements, and the maximum window consumers may need for lookups. Do not delete unpublished records or records currently claimed. For large payloads, you can store a reference to immutable data rather than copying full contents, provided the reference remains available throughout retry and replay windows.

## When to choose write-ahead or outbox?

Write-ahead is a general principle useful whenever you need to record intent or progress before performing output that can fail. It fits processes needing recoverability, reconciliation, or replay, even when the output is not a message.

Transactional outbox fits especially well when a database transaction both changes business data and produces events for other systems. It narrows the problem into a manageable local transaction: commit business data and outbox records together; message forwarding happens afterward with retries.

| Criterion | Write-ahead log/record | Transactional outbox |
|---|---|---|
| Goal | Durably record intent or operation for recovery | Bind business changes with events to emit |
| Scope | Broad concept applicable to many output types | Integration pattern commonly used with databases and message brokers |
| Recording | Log written before the action | Outbox record committed alongside business data |
| Replay | Recovery component reads incomplete logs | Publisher reads and sends unpublished outbox rows |
| Remaining issue | May emit duplicates if failure occurs after destination receipt | May emit duplicates if broker accepts but outbox status is not yet updated |
| Required protection | Stable IDs, reconciliation, and safe duplicate handling | Event ID, safe claiming, and idempotent consumers |

If both business data and output reside in the same database, writing them in one transaction may already suffice. If the output target is an external system that does not participate in that transaction, an outbox is usually easier to operate than attempting a distributed transaction. If business requirements demand stronger guarantees, evaluate broker transaction support, acknowledgment mechanisms, idempotency, and end-to-end recovery procedures; do not claim "exactly once" merely because an outbox is used.

## Design checklist before implementation

1. Identify which outputs lie outside the step transaction and describe points where the process could stop.
2. Choose durable storage for output intent; for events arising from database changes, consider transactional outbox.
3. Ensure business changes and outbox records share the same datasource and transaction manager.
4. Define stable event IDs and unique keys aligned with business semantics.
5. Design a publisher with safe claiming, broker confirmation, retries, and permanent-failure handling.
6. Design idempotent consumers that commit processed markers alongside business changes.
7. Specify per-aggregate ordering if business rules require it.
8. Monitor backlog, event age, publish errors, and table size; define a retention policy.
9. Test process-stop scenarios at every boundary: before commit, after commit, before publish, after broker ack, and before marking published.

The goal of write-ahead and outbox is to turn an output action that could easily be lost on process crash into durable, resumable, and reconcilable work. In Spring Batch, an effective implementation starts with placing chunk transaction boundaries properly, writing the outbox alongside business data, and handling forwarding through a retrying publisher and idempotent consumers.
