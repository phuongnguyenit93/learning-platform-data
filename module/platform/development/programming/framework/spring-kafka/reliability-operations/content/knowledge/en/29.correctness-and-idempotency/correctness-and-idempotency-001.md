# Duplicate delivery

In **Spring Kafka Reliability Operations**, **Duplicate delivery** is the situation where a Kafka record is received and processed by a consumer more than once. This is normal behavior that can occur in distributed systems, especially when a consumer uses **at-least-once delivery**, when a process crashes between business processing and offset commit, during consumer group rebalances, during retries, or when operators replay records.

A record being redelivered does not necessarily mean Kafka stored two copies. Usually, it is **the same record being read again because the broker has not seen the processed offset committed**, or because the application actively retries/recovers. If the business handler performs non-idempotent side effects, re-reading can cause double charges, duplicate orders, double inventory updates, or duplicate notifications.

The operational goal is not to assume duplicates will never happen. The goal is to design consumers to **tolerate an event being redelivered**, protect side effects with idempotency, clearly understand offset/ack/transaction boundaries, and be able to prove the outcome after recovery.

> **Kafka delivery and business side effects are two different things.** Assume a record can be redelivered; only consider a business operation complete when the side effect and the processing marker have been durably persisted within the same consistency boundary.

## 1. What is duplicate delivery?

Suppose the topic orders.events has a record:

~~~text
topic       = orders.events
partition   = 2
offset      = 1042
event_id    = evt-7f91
event_type  = OrderPaid
~~~

The consumer receives the record, updates the database, and then the process is killed before Kafka offset 1043 is committed. When the consumer restarts or the partition is assigned to another member, Kafka still sees the previous committed offset and can redeliver the record at offset 1042.

~~~text
Attempt 1:
  poll offset 1042
  database update succeeds
  process crashes before offset commit

Attempt 2:
  consumer starts / partition reassigned
  re-poll offset 1042
  database update runs again
~~~

Kafka may have only **one physical record** at that partition/offset. The duplicate appears at the **delivery/processing layer** because the same record is redelivered.

It is necessary to distinguish:

- **Duplicate production**: the producer sends the same business event as multiple Kafka records.
- **Duplicate delivery**: the same Kafka record is received again by the consumer.
- **Duplicate processing**: the handler executes business logic multiple times for the same event.
- **Duplicate side effect**: an external system records the business action multiple times.
- **Duplicate output**: the consumer emits multiple output records due to redelivery or retry.

These phenomena are related, but handled differently. An idempotent producer can reduce duplicates from producer retries; consumer idempotency protects side effects upon repeated delivery.

## 2. Why can Kafka redeliver a record?

Kafka stores the **committed offset** per consumer group. That offset represents the next position the consumer group will read, not a separate confirmation flag for each business side effect.

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant DB as Database
    participant K as Kafka
    C->>K: poll record offset 1042
    K-->>C: record 1042
    C->>DB: update business state
    DB-->>C: commit success
    Note over C: Process crashes here
    C->>K: Restart and poll from committed offset
    K-->>C: record 1042 again
    C->>DB: same business update again
~~~

Common causes:

1. Process crash after the business transaction commits but before the offset commits.
2. Pod termination while the listener is still processing.
3. Consumer group rebalance causing the partition to move to another member.
4. Network failure leaving the client uncertain whether the commit request succeeded.
5. Listener throws an exception and the error handler retries the record.
6. Database transaction rollback or uncertain commit outcome.
7. Kafka transaction abort leaving input offsets uncommitted.
8. Operator resets offsets or replays from an older offset.
9. Retry topic/DLT recovery creates an additional delivery path.
10. Producer sends the same business event multiple times with different Kafka offsets.

A correct application must accept some of these cases instead of relying on favorable timing.

## 3. Delivery guarantees are not the same as business exactly-once

| Guarantee | What is protected | What is not automatically protected |
|---|---|---|
| At-most-once | Records are not reprocessed via commit-before-processing | Records can be lost if a crash occurs after commit before the side effect |
| At-least-once | Records are retried/redelivered per policy | Handlers/side effects may run multiple times |
| Kafka producer idempotence | Reduces duplicate records from producer retries within the protocol/session | Consumer side effects or duplicate business events from multiple sends |
| Kafka transactions/EOS | Atomicity of Kafka output records and consumed offsets within the transaction scope | Database/HTTP/email side effects outside Kafka |
| Business idempotency | Same business event is applied at most once per key/policy | Does not automatically guarantee broker delivery or all external systems |

**At-least-once** is the common choice for business processing because it prioritizes not losing data. In return, the consumer must tolerate redelivery.

At-most-once can avoid repetition by committing the offset before processing, but a crash after commit will cause the record to be skipped. Do not choose at-most-once just so dashboards show no duplicates if the business cannot accept losing records.

## 4. Offset is the next position to read

Kafka offsets are sequential numbers per partition. When a consumer has processed offset 1042 and wants to continue from 1043, the committed offset is typically **1043**.

~~~text
Last processed record: 1042
Committed position:    1043
Next record to read:   1043
~~~

The committed offset typically represents the next position, not that the record at that exact offset has already been processed. Offsets are scoped per **partition**, not a global order across the entire topic. A consumer can commit progress for partition 0 while partition 1 is still processing an older record.

When a batch contains multiple records, do not commit an offset past a record that has not been successfully processed in the same partition.

## 5. The crash window that creates duplicates

There are two boundaries that typically cannot be committed atomically when using a standard database and Kafka:

~~~text
A. Business side effect first, Kafka offset second:
   DB commit -> crash -> offset uncommitted -> redelivery
   => duplicate side effect if not idempotent

B. Kafka offset first, business side effect second:
   offset commit -> crash -> DB uncommitted -> record not redelivered
   => lost business operation
~~~

At-least-once usually chooses A because duplicates can be handled via idempotency; data loss is usually much harder to recover from.

Do not reverse the order to B just to avoid duplicates. Design proper business idempotency and transaction boundaries instead.

## 6. Spring Kafka AckMode affects commit timing

The Spring Kafka container manages acknowledgments and offset commits via **AckMode**. When Kafka auto-commit is disabled and the container manages commits, common modes include:

| AckMode | General behavior |
|---|---|
| RECORD | Commits after the listener successfully processes each record |
| BATCH | Commits after all records from the poll batch are successfully processed |
| TIME | Commits when the configured interval has elapsed after processed records |
| COUNT | Commits when the configured number of processed records is reached |
| COUNT_TIME | Combines count and time thresholds |
| MANUAL | Listener calls acknowledge; container commits according to the appropriate batch semantics |
| MANUAL_IMMEDIATE | Commits immediately when acknowledge is called on the consumer thread; calling from another thread may alter actual timing |

The default container AckMode is typically BATCH when the container manages commits and auto-commit is disabled; verify your version and application configuration.

AckMode does not turn a business side effect and a Kafka offset into a shared transaction with the database. If the DB commits and the process crashes before the Kafka commit, duplicates can still occur.

## 7. RECORD and BATCH create different windows

With RECORD:

~~~text
poll [100, 101, 102]
listener(100) -> success -> commit position 101
listener(101) -> success -> commit position 102
listener(102) -> crash
restart -> re-read from committed position
~~~

With BATCH:

~~~text
poll [100, 101, 102]
listener(100) -> success
listener(101) -> success
listener(102) -> success
batch completes -> commit position 103
~~~

If the process crashes before the batch commit, some or all records in the batch may be redelivered even though their business side effects have already completed.

BATCH can widen the redelivery scope when a batch has not yet committed, in exchange for lower commit overhead. Choosing AckMode is a trade-off between throughput, commit cost, and the size of the duplicate window.

## 8. MANUAL acknowledgment does not mean exactly-once

Example:

~~~java
@KafkaListener(topics = "orders.events")
public void consume(
        ConsumerRecord<String, OrderEvent> record,
        Acknowledgment acknowledgment) {

    orderService.apply(record.value());

    acknowledgment.acknowledge();
}
~~~

This order represents at-least-once: the side effect succeeds first, followed by acknowledgment. If the process dies between the two steps, the record may be redelivered.

Do not acknowledge before the durable side effect completes unless you are willing to accept business data loss:

~~~java
// Dangerous if the side effect can fail after acknowledge.
acknowledgment.acknowledge();
orderService.apply(record.value());
~~~

With MANUAL/MANUAL_IMMEDIATE, you need to understand the consumer thread, AckMode, async acknowledgments, and version-specific semantics. Do not call acknowledge arbitrarily from worker threads unless the supporting mechanism is configured and well understood.

## 9. Consumer group rebalances can cause redelivery

When a consumer leaves the group, its partitions can be assigned to another consumer. If a record was already processed but its offset was not committed, the new member can read it again.

Some causes of rebalance:

- Deployment/rolling restart.
- Pod killed or node failure.
- Consumer heartbeat/session timeout.
- Exceeding max.poll.interval.ms.
- Scaling consumer instances.
- Network interruption.
- Changes in subscription or assignment strategy.

~~~mermaid
sequenceDiagram
    participant A as Consumer A
    participant K as Group Coordinator
    participant B as Consumer B
    A->>K: owns partition 2
    A->>K: processes offset 1042
    Note over A: DB committed, Kafka offset not committed
    A--xK: leaves group / heartbeat timeout
    K->>B: assigns partition 2
    B->>K: joins and fetches from committed offset
    K-->>B: offset 1042 redelivered
~~~

Graceful shutdown and fast listener processing help shrink this window, but they do not eliminate crash/network ambiguity. Idempotency is still required.

## 10. Retries and error handlers also create multiple processing attempts

Spring Kafka can retry a record after a listener exception:

~~~text
Delivery 1 -> listener throws
Retry 1    -> listener throws
Retry 2    -> listener succeeds
~~~

If the listener performs a side effect before throwing, retries can repeat that side effect. For example, a DB update succeeds but a subsequent HTTP call times out; the handler throws, causing the entire record to be redelivered.

Identify the **point of side effect** and the order of operations. Never assume that a listener throwing an exception means no state changes have occurred.

If retries route the record to a retry topic or DLT, each stage can still encounter duplicates due to publish/offset commit failures. Consumers at retry/DLT stages must also have appropriate idempotency.

## 11. Producer idempotence and consumer idempotency

The two mechanisms protect two different boundaries:

| Mechanism | Protection |
|---|---|
| enable.idempotence | Producer retries do not create duplicate appends per Kafka producer semantics |
| Transactional producer | Atomic Kafka writes and offsets within a transaction |
| Consumer inbox/deduplication | A business event does not apply side effects repeatedly |
| Database unique constraint | Prevents two transactions from recording the same event ID |
| External API idempotency key | Downstream API receives the same operation key multiple times but applies it once |

Producer idempotence does not eliminate duplicates caused by the producer application sending the same event twice, producer restarts with application retries, two service instances emitting the same event, consumer redelivery, or operator replays.

Consumer idempotency remains a separate responsibility.

## 12. Kafka transactions and the limits of exactly-once

Spring Kafka can configure a transactional listener container. In Kafka-to-Kafka processing, a transaction can bundle output records and input offsets into the same transaction. Downstream consumers using isolation.level=read_committed will not see output records from aborted transactions.

This achieves **exactly-once semantics within the scope of a Kafka transaction** when configured properly.

However, the transaction does not automatically include:
- JDBC database updates.
- HTTP API calls.
- Email/SMS.
- File/object storage.
- Payment gateways.
- Side effects in systems outside Kafka.

The listener may be invoked again after a transaction abort. If the listener already called an external API before the transaction aborted, that API call does not automatically roll back.

**Kafka EOS does not equate to end-to-end business workflow exactly-once.** Idempotency/outbox/inbox is still required for systems outside the transaction boundary.

## 13. Database inbox pattern

A common approach is storing processed event IDs in the database within the same transaction as the business update.

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(120) NOT NULL,
    event_id VARCHAR(160) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

When receiving a record:

1. Start a DB transaction.
2. Insert the event ID into processed_events.
3. On unique conflict, the event has already been applied; finish without repeating the side effect.
4. If the insert is new, perform the business update.
5. Commit both the marker and the business update in the same transaction.
6. Only after the listener succeeds does the container commit the Kafka offset according to AckMode.

If the DB transaction rolls back, the marker also rolls back. When the record is redelivered, the consumer can retry it.

## 14. SQL insert-if-absent must be atomic

Do not use check-then-act:

~~~java
if (!repository.existsByEventId(eventId)) {
    repository.saveProcessedEvent(eventId);
    orderRepository.apply(event);
}
~~~

Two consumer threads can simultaneously see exists=false and both proceed to insert/apply. This is a race condition.

Use a unique constraint as the arbiter in the database:

~~~sql
INSERT INTO processed_events (
    consumer_name,
    event_id,
    processed_at
)
VALUES (
    :consumerName,
    :eventId,
    CURRENT_TIMESTAMP
)
ON CONFLICT (consumer_name, event_id) DO NOTHING;
~~~

The syntax above is PostgreSQL. MySQL, SQL Server, and other databases have different corresponding syntax. You must check the number of affected rows to know whether the event ID was just claimed or already existed.

If the insert and domain update share the same DB transaction, the unique constraint prevents two concurrent deliveries from both applying the business update.

## 15. Idempotent service example

A repository interface can provide insert-if-absent:

~~~java
public interface ProcessedEventRepository {

    boolean insertIfAbsent(
            String consumerName,
            String eventId
    );
}
~~~

Service:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IdempotentOrderHandler {

    private final ProcessedEventRepository processedEvents;
    private final OrderRepository orders;

    public IdempotentOrderHandler(
            ProcessedEventRepository processedEvents,
            OrderRepository orders) {
        this.processedEvents = processedEvents;
        this.orders = orders;
    }

    @Transactional
    public ProcessingResult handle(OrderEvent event) {

        boolean firstDelivery = processedEvents.insertIfAbsent(
            "orders-projection",
            event.eventId()
        );

        if (!firstDelivery) {
            return ProcessingResult.duplicate();
        }

        orders.apply(event);

        return ProcessingResult.applied();
    }
}
~~~

ProcessingResult, repositories, and OrderEvent are illustrative domain types. What matters is that **the marker and orders.apply execute within the same transaction manager/database transaction**.

If orders.apply throws an exception, the transaction rollback must undo the marker as well. If the marker commits separately before the domain update, a crash could cause redelivery to be treated as a duplicate even though the business update never happened.

## 16. Idempotency keys must be stable

A deduplication key should represent **a single business operation**, not just a single Kafka delivery attempt.

Examples:
- event_id generated once by the producer and preserved across retries.
- payment_operation_id for a payment request.
- order_event_id for a domain event.
- source_system + source_event_id if multiple sources can share overlapping namespaces.

Do not generate a new UUID on each consumer retry; otherwise duplicates cannot be recognized.

Kafka topic/partition/offset can identify a physical record, but when a producer emits the same business event as two records with different offsets, differing offsets cannot detect business duplicates. Conversely, when replaying events to another topic, a stable event ID can preserve deduplication across replays if that is the desired policy.

Choose the key scope carefully: the same event may need to be processed once per consumer application, so the unique key usually consists of consumer_name and event_id.

## 17. Checking event ID and payload consistency

If the same event_id appears with a different payload, do not silently treat it as a valid duplicate.

A good policy:
- Same event_id and same logical content: duplicate delivery, skip side effect.
- Same event_id but different payload: event identity conflict, quarantine/alert.
- Missing or malformed event ID: validation failure per policy.
- Event ID reused after a long time: decide according to retention/business contract.

You can store a schema version or payload fingerprint derived from a canonical representation to detect identity collisions. The fingerprint does not need to expose raw payloads in logs/traces; protect it according to policy since it may enable correlation.

Do not use an unstable hash of JSON serialization if field ordering, whitespace, or schema evolution can give identical content different fingerprints.

## 18. Deduplication retention must cover the replay horizon

If processed_events deletes markers after 7 days while the Kafka topic retains 30 days for replay, an old replayed record can apply its side effect again.

Retention must account for:
- Input topic Kafka retention.
- Maximum consumer outage duration.
- Retry topic retention.
- DLT retention and operator handling time.
- Backup/restore/replay horizon.
- Cross-region disaster recovery.
- Manual backfill and historical reprocessing.
- Business/legal retention policies.

Some systems retain markers permanently or for the business entity lifetime. Some use partitioned/TTL tables with a proven sufficient retention window. Do not pick a TTL just because the dedupe table is growing large.

If markers are deleted, the system is actively allowing events to potentially be reapplied after that point.

## 19. Ordering and duplicates

Idempotency does not automatically guarantee ordering. Kafka only guarantees order within a single partition by append order. If events with the same key go to different partitions, or retry topics alter timing, business ordering can change.

Example:
~~~text
OrderCreated version 1
OrderPaid    version 2
OrderClosed  version 3
~~~

If version 2 is processed twice, the consumer must recognize the duplicate. If version 3 arrives before version 2 due to retry/replay, the consumer must handle out-of-order delivery according to domain policy.

Measures:
- Partition by a stable aggregate key.
- Use an aggregate version/sequence number.
- Conditional updates that only apply newer versions.
- Reject/quarantine version gaps when needed.
- Do not retry an event for a long time and assume subsequent events will wait in order unless the retry strategy guarantees it.

## 20. Conditional updates and optimistic versioning

Another idempotent approach is applying state transitions by version:

~~~sql
UPDATE orders
SET status = :newStatus,
    version = :incomingVersion
WHERE order_id = :orderId
  AND version = :incomingVersion - 1;
~~~

If the update affects zero rows, it may be because:
- The event was already applied (current version >= incoming version).
- The event arrived out of order (version lower than expected).
- The order does not exist.
- A version gap requiring retry or quarantine.

You must distinguish these cases rather than treating every rows-updated=0 as a duplicate. You can read the current state and classify it per domain rules.

A unique event ID and optimistic versioning complement each other: event ID guards against repeated delivery; version guards transition ordering.

## 21. External API side effects

A database inbox only protects side effects inside the same DB transaction. If a listener calls a payment/shipping/email API, the DB transaction cannot roll back an operation already accepted by that external system.

Dangerous example:

~~~java
@Transactional
public void handle(PaymentRequested event) {
    paymentClient.charge(event.amount(), event.cardReference());
    processedEvents.insert(event.eventId());
}
~~~

If the payment API charge succeeds but the response times out before the client learns the result, the DB transaction may roll back and Kafka will redeliver the record. The next invocation may charge again.

Preferred solutions:
- Use a stable idempotency key supported by the downstream API.
- Pass the same key on every retry of the same operation.
- Downstream stores the result by key and returns the prior result on repeated requests.
- Distinguish ambiguous timeouts from failures known not to have executed.
- Have reconciliation to verify whether the operation was executed.

Do not generate a new idempotency key on each retry.

## 22. Outbox pattern for cross-service side effects

If a consumer needs to update a database and emit a command to another system, a **transactional outbox** persists the intent to send within the same DB transaction:

~~~text
Kafka input
   |
   v
DB transaction:
  insert inbox event_id
  update domain state
  insert outbox command
   |
   v
commit DB transaction
   |
   v
outbox publisher sends command
   |
   v
downstream idempotency key
~~~

Outbox table example:

~~~sql
CREATE TABLE outbox (
    id VARCHAR(160) PRIMARY KEY,
    aggregate_id VARCHAR(160) NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    payload JSON NOT NULL,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL
);
~~~

The payload in the outbox is business data and must be protected like database business data; do not copy it into spans/logs. The publisher may send the same outbox row multiple times if it crashes after publishing before marking it published. Downstream still needs idempotency.

Inbox + domain update + outbox insert should commit in the same DB transaction. The Kafka offset is committed after the listener transaction succeeds per container configuration.

## 23. Kafka-to-Kafka processing with transactions

If a consumer reads topic A, processes it, and writes to topic B, a Spring Kafka transactional listener can combine output records and input offsets into a Kafka transaction.

~~~text
begin Kafka transaction
  consume input record
  produce output record
  send consumed offset to transaction
commit transaction
~~~

If the transaction aborts, the output record is not visible to read_committed consumers and the input offset has not been committed in the transaction; the record can be redelivered.

This prevents outputs from failed transactions from appearing as committed results. However, the handler can still run again. Business code inside the transaction should not create unprotected external side effects.

If the producer sends an email before transaction commit, a Kafka abort cannot recall that email.

## 24. Error handlers and DLT can deliver duplicates

An error handler can retry, recover, or publish failed records to a DLT. There is also a crash window at the recovery step:

~~~text
1. Publish record to DLT
2. DLT publish succeeds
3. Process crashes before input offset commit
4. Original record is delivered again
5. DLT publish may happen again
~~~

Therefore, the DLT consumer should also be idempotent, and DLT recovery needs a stable identity for the original event. Do not assume that once a record enters the DLT, it cannot be duplicated.

Spring Kafka error handling can use DefaultErrorHandler, DeadLetterPublishingRecoverer, AfterRollbackProcessor, or @RetryableTopic. Details of seek, ack, transactions, and recovery depend on configuration/version; you must understand exactly which record is retried and when offsets are committed.

## 25. Retry topics change timing, not eliminate duplicates

Non-blocking retry uses retry topics to separate retry timing from the main consumer. This can allow subsequent records to continue processing, but:
- Retry records can be republished if offsets are not committed.
- Retry listeners can crash after side effects.
- DLT publication can be repeated.
- Ordering can change between main and retry stages.
- A business event can appear on multiple topics within the same workflow.

Keep the event ID stable across main/retry/DLT. Do not generate new IDs at each stage. Use retry-stage metadata for observability, not the topic name as an idempotency key if the same event can traverse multiple retry topics.

## 26. Consumer concurrency and race conditions

A consumer group can have multiple partitions and multiple listener threads. The same business event can appear in two different Kafka records or be replayed while a previous processing attempt is still running elsewhere.

A non-atomic check-then-act easily races:

~~~text
Thread A: event not processed?
Thread B: event not processed?
Thread A: yes -> apply
Thread B: yes -> apply
~~~

A unique constraint on (consumer_name, event_id) or atomic insert-if-absent ensures only one transaction claims the event.

If processing requires per-aggregate ordering, a stable partition key and database concurrency control must enforce the same invariant. Do not rely on an in-memory HashSet/ConcurrentHashMap to prevent duplicates across a multi-replica cluster.

## 27. Idempotency is not just an in-memory cache

An in-memory set loses data on process restart, is not shared across pods, and does not coordinate with DB transactions. It can only be an optimization, never the source of truth for correctness.

Durable mechanisms:
- Database inbox table with a unique key.
- Business table unique constraint.
- Conditional upsert/version check.
- Downstream API idempotency store.
- Durable outbox/inbox.
- Transactional Kafka offsets/output when all side effects are within Kafka.

A cache can reduce DB lookups, but must not be the sole layer preventing repeated side effects.

## 28. Idempotent upsert for projections

For consumers building a read model, upserting by entity version can be naturally idempotent:

~~~sql
INSERT INTO order_projection (
    order_id,
    status,
    version
)
VALUES (
    :orderId,
    :status,
    :version
)
ON CONFLICT (order_id)
DO UPDATE SET
    status = EXCLUDED.status,
    version = EXCLUDED.version
WHERE order_projection.version < EXCLUDED.version;
~~~

This is a PostgreSQL example. If the same event version is redelivered, the update does not alter state again. Older events arriving after newer events will not overwrite newer state.

However, not every operation is set-state. Incrementing counters, debiting balances, or sending emails require a separate idempotency key; re-running an UPDATE that adds an amount still creates duplicates.

## 29. Idempotency for additive operations

Counter example:

~~~sql
UPDATE inventory
SET reserved_quantity = reserved_quantity + :quantity
WHERE sku = :sku;
~~~

This statement is not idempotent: running the same event twice adds twice.

The protection is to claim the event ID and update within the same transaction:

~~~sql
BEGIN;

INSERT INTO processed_events (
    consumer_name, event_id, processed_at
)
VALUES (
    'inventory-reservation', :eventId, CURRENT_TIMESTAMP
)
ON CONFLICT (consumer_name, event_id) DO NOTHING;

-- Only execute the update when the insert successfully claimed the event.
UPDATE inventory
SET reserved_quantity = reserved_quantity + :quantity
WHERE sku = :sku;

COMMIT;
~~~

This is SQL pseudocode; the application must check rows affected by the INSERT before running the UPDATE. If the event ID already exists, skip the update part. If the update fails, roll back the marker as well.

## 30. Handling duplicates requires distinguishing outcomes

Do not treat duplicates as infrastructure errors to retry forever. An event that has already been successfully applied can be handled as a **successful no-op** so the container proceeds to commit the offset.

~~~java
ProcessingResult result = handler.handle(event);

if (result.isDuplicate()) {
    log.info(
        "Duplicate event ignored: eventType={}, consumer={}",
        safeEventType(event),
        "orders-projection"
    );
}
~~~

Logs do not need to record full payloads or PII. You can increment a duplicate count metric by normalized consumer/topic/event type. If a duplicate key has a payload conflict, that is an identity/data integrity incident, not a normal duplicate.

Ensure the duplicate path returns success only when you have verified the marker represents a business transaction that actually committed.

## 31. Observability for duplicate delivery

Suggested metrics:

| Metric | Meaning |
|---|---|
| consumer.records.received | Records received by the listener |
| consumer.events.applied | New business events applied |
| consumer.events.duplicate | Deliveries deduplicated |
| consumer.events.identity_conflict | Same ID with conflicting payload/version |
| consumer.offset.commit.failure | Commit failures |
| consumer.rebalance.count | Group changes |
| consumer.retry.count | Retry attempts |
| consumer.dlt.count | DLT recovery |
| consumer.processing.duration | Processing duration |
| consumer.lag | Backlog |
| inbox.unique_conflict.count | Dedupe constraint hits |
| outbox.publish.retry | Outbox dispatch retries |

These are illustrative metric names; some require custom instrumentation. Do not use event ID, customer ID, or raw keys as metric labels because of high cardinality and potential data exposure.

Structured logs can include topic, partition, offset, allowlisted event type, consumer name, result=duplicate, and an opaque trace ID if policy allows. Do not log payloads.

## 32. Counting duplicates properly

A consumer receiving the same event ID multiple times does not necessarily prove a Kafka delivery failure. The producer may have published the same business event multiple times with different offsets.

Distinguish between:
- **Same topic/partition/offset delivered again**: redelivery of the same Kafka record.
- **Same event_id, different offsets**: producer/application duplicate or replay.
- **Same business key, different event_id**: possibly two valid events or a producer identity bug.
- **Same event_id, different payload**: event identity conflict.

For analysis, you can log/record the event ID as an approved opaque reference alongside topic/partition/offset. Separate privacy/cardinality policies are needed for event IDs.

## 33. Replay and backfill interaction with deduplication

Operators may reset offsets to replay historical records or run a backfill. If the inbox table keeps event IDs long-term, replay may skip them because those events were already processed.

This may be right if the goal is solely to recover consumer position; however, it is wrong if the goal is to **rebuild a projection from scratch**.

Define the mode clearly:
- Normal processing: dedupe by consumer name and event ID.
- Rebuild projection: use a new projection generation/rebuild namespace or build into an empty target.
- Replay to fix a bug: require a policy deciding which events are allowed to be reapplied.
- Reconciliation: compare business state, rather than arbitrarily deleting inbox rows.

Do not delete the entire dedupe table just to backfill. Doing so can cause historical external side effects to run again.

## 34. Retention and partitioning of the inbox table

The inbox table can grow large. Operational strategies:
- Unique index on consumer_name + event_id.
- Time-based partitioning if the database supports it and query/unique semantics permit.
- Archive old markers per retention contract.
- Monitor insert latency and unique-conflict rate.
- Delete in small batches to avoid lock/IO spikes.
- Maintain retention longer than retry/DLT/replay/DR horizons.
- Do not delete markers while events can still be redelivered.

If using partitioned tables, some databases require the partition key to appear in the unique constraint; the design must preserve uniqueness across the entire dedupe scope. Do not partition in a way that breaks unique event ID guarantees.

## 35. Async listeners and duplicates

If a listener submits work to an executor and returns, the container may acknowledge the record before the task completes depending on AckMode:

~~~java
@KafkaListener(topics = "orders.events")
public void consume(OrderEvent event) {
    executor.submit(() -> service.apply(event));
    // Returning from the listener may cause offset commit before task completion.
}
~~~

If the offset commits before task completion, a failed task may not be redelivered. If the task runs and the consumer crashes before commit, duplicates can run concurrently.

When using async:
- Use acknowledgment/lifecycle semantics supported by your Spring Kafka version.
- Only ack after durable completion.
- Keep in-flight tasks bounded.
- Handle rebalance/shutdown and running tasks.
- Protect the DB with unique keys/transactions.
- Do not commit past pending records in a partition.
- Test crashes and task timeouts.

Async does not automatically increase delivery guarantees.

## 36. Concurrency and partition ordering

Kafka only guarantees order within the same partition. If events with the same aggregate key do not always land in the same partition, or retry topics alter timing, a duplicate guard does not solve out-of-order updates.

Use a stable key by aggregate when ordering is needed. Combine:
- Partition key by aggregate.
- Increasing version number.
- Conditional database updates.
- Inbox unique event ID.
- A retry policy aware that moving records to retry topics can alter order.

If event version 4 is processed before version 3, the consumer must detect the gap or ignore older versions per domain policy; do not merely treat every duplicate key as success.

## 37. Manual offset reset and operator replay

Offset resets can cause intentional duplicate delivery. Before replaying:

1. Identify the group/topic/partitions and offset range.
2. Determine whether business side effects have already been applied.
3. Verify the idempotency store still retains the event IDs.
4. Determine whether the replay is for recovery, rebuild, or bug correction.
5. Use an appropriate consumer identity/namespace if reprocessing is needed.
6. Do not reset offsets while consumers are still active if the procedure requires an inactive group.
7. Monitor lag, retries, DLT, and side effects.
8. Keep an audit trail of who, why, and the scope of the replay.

Resetting offsets does not delete records or create new events. It only changes the read position; replay typically causes old records to be redelivered.

## 38. Shutdown and deployment to shrink the duplicate window

Graceful shutdown gives listeners time to finish work within the allowed window, stops the container cleanly per lifecycle, and commits offsets per policy. However, a shutdown timeout shorter than processing duration can cause the pod to be killed between side effect and commit.

Required practices:
- Set termination grace period long enough for reasonable listener draining.
- Stop the container via lifecycle.
- Avoid starting new batches during shutdown if pause/drain is possible.
- Monitor in-flight transactions.
- Do not manually commit if processing is not yet durable.
- Design for idempotency even when graceful shutdown is configured.

Graceful shutdown reduces duplicate frequency; it does not eliminate crashes, node loss, or network partitions.

## 39. Integration testing duplicate delivery

A valuable test should reproduce the window where the side effect committed but the offset did not:

1. Use EmbeddedKafka or Testcontainers.
2. Create a dedicated topic and group.
3. Send an event with a stable event ID.
4. Consumer processes and commits the DB transaction.
5. Stop the consumer before Kafka offset commit completes, or use a test harness controlling acknowledgment.
6. Restart the consumer/reassign the partition.
7. Verify the record is redelivered.
8. Verify the inbox unique key recognizes the duplicate.
9. Verify the business side effect is applied only once.
10. Verify the offset eventually advances after the duplicate no-op.

Do not just mock the repository to return duplicate. You need to test the DB transaction, unique constraint, and Kafka redelivery in an appropriate integration scenario.

## 40. Testing DB rollback and concurrency

Required tests:

**DB rollback:** inbox marker insert succeeds but domain update throws an exception; verify marker rolls back. Upon redelivery, the event can be processed again.

**Concurrent duplicate:** two consumer/test threads process the same event ID simultaneously; verify only one transaction claims and applies the side effect.

**Payload conflict:** same event ID with different payload; verify error/quarantine rather than silently ignoring.

**Retention boundary:** old event replayed after expected retention; verify the dedupe policy behaves explicitly.

**Ordering:** older version arrives after newer version; verify state does not roll back.

**External API timeout:** API already applied the operation but the response was lost; retry uses the same idempotency key and does not repeat the side effect.

## 41. Testing Kafka transactions and retry/DLT

For a transactional listener:
- Cause an exception before transaction commit.
- Verify the transaction aborts and output is not visible to read_committed consumers.
- Verify the input record can be redelivered.
- Verify business side effects outside Kafka are protected separately.
- Test AfterRollbackProcessor/recovery policy.

For retry/DLT:
- Cause listener errors and retries.
- Simulate a crash after DLT publish before input offset commit if the harness permits.
- Verify the DLT can receive duplicates.
- DLT consumer uses inbox/idempotency.
- Verify event ID remains stable across retry metadata.

These tests help distinguish Kafka EOS from business exactly-once.

## 42. Runbook when duplicate side effects occur

**Identify**
1. Collect topic, partition, offset, group, event ID, and safe trace correlation.
2. Distinguish same-offset redelivery from same event ID/different offset.
3. Identify consumer stage: main, retry, DLT, or replay.
4. Determine how many times the business side effect ran and which transaction committed.

**Isolate**
5. Check committed offsets and AckMode.
6. Check rebalance, crash, timeout, retry, and deploy timelines.
7. Check inbox marker/unique constraint.
8. Check producer retries and event ID generation.
9. Check external API idempotency/reconciliation.

**Recover**
10. Pause or throttle the consumer if duplicates continue causing harm.
11. Do not reset offsets or delete inbox markers arbitrarily.
12. Reconcile business state using an authorized source-of-truth system.
13. Fix the idempotency/transaction boundary.
14. Perform controlled replay after proving duplicate safety.

**Verify**
15. Side effects are applied only once per event key.
16. Offsets advance and consumer lag decreases.
17. Retry/DLT backlog stabilizes.
18. No remaining duplicate conflicts.
19. Document incident root cause and preventive actions.

## 43. Common anti-patterns

- Using an in-memory Set for deduplication: lost on restart and not shared across replicas.
- Non-atomic check-then-act: two threads can both see the event as unprocessed.
- Committing offset before side effect: a crash can lose the business operation.
- Writing inbox marker outside the transaction of the business update: a crash can mark the event processed even though the side effect never committed.
- Generating a new event ID on retry: duplicates can no longer be recognized.
- Using Kafka offset as the business idempotency key: the same event at different offsets still gets applied twice.
- Assuming idempotent producer solves consumer duplicates: they are two different protection layers.
- Assuming Kafka transactions cover databases/HTTP: transaction scope only covers enlisted resources.
- Deleting inbox markers too early: historical replay can repeat side effects.
- Using retry topics without preserving event identity: deduplication fails across stages.
- Treating duplicate delivery as a broker bug: at-least-once normally permits redelivery.
- Ignoring same event ID with different payload: can mask producer identity conflicts or data corruption.
- Async submit and returning before durable completion: offsets may commit too early.

## 44. Production checklist

**Delivery and offsets**
- [ ] AckMode/auto-commit are clearly understood and configured.
- [ ] Aware that committed offset is the next position to read.
- [ ] Crash window between side effect and offset commit is identified.
- [ ] Rebalance/retry/timeout are treated as sources of redelivery.
- [ ] Do not commit past incomplete records.

**Idempotency**
- [ ] Every business event has a stable ID.
- [ ] Inbox/unique constraint uses atomic insert-if-absent.
- [ ] Inbox marker and DB side effect share the same transaction.
- [ ] Duplicate path is a successful no-op.
- [ ] Same ID/different payload is detected.
- [ ] Retention covers retry/DLT/replay/DR horizons.
- [ ] External APIs receive stable idempotency keys.

**Transactions and retries**
- [ ] Distinguish Kafka EOS from external side effects.
- [ ] Transactional listener/AfterRollbackProcessor are tested.
- [ ] Retry/DLT consumers are also idempotent.
- [ ] Event identity is preserved across retry stages.
- [ ] Ordering/version policy is explicit.

**Operations**
- [ ] Metrics for duplicates, offset commits, rebalances, and lag.
- [ ] Replay/offset-reset runbook exists.
- [ ] Graceful shutdown has sufficient time.
- [ ] Reconciliation exists for external side effects.
- [ ] Do not use in-memory dedupe as source of truth.

**Testing**
- [ ] Test redelivery after DB commit before offset commit.
- [ ] Test DB rollback.
- [ ] Test concurrent duplicates.
- [ ] Test payload conflicts.
- [ ] Test external API timeout/idempotency.
- [ ] Test Kafka transaction abort and retry/DLT.

## 45. Conclusion

**Duplicate delivery** is a natural part of at-least-once Kafka systems. A consumer can successfully process a business side effect and crash before committing the offset; rebalances, retries, transaction aborts, network ambiguity, and operator replays can all cause the same record to be redelivered.

Spring Kafka AckMode, acknowledgment, error handlers, and transactions determine retry/commit timing, but do not automatically make all business side effects exactly-once. **Kafka producer idempotence** protects producer retries; **Kafka transactions** protect atomicity within Kafka; **database inbox/unique constraints, conditional upserts, and external API idempotency keys** protect business effects outside that boundary.

A resilient design requires stable event IDs, atomic deduplication in the same transaction as the business update, sufficient retention, payload conflict handling, and observability that distinguishes redelivery from duplicate business events. In operations, verify offsets, group, retry stage, and side-effect outcomes before replaying. A reliable consumer is not one that has never received a duplicate; it is one that can receive a record again while keeping **business state accurate and applying no unintended repeated side effects**.
