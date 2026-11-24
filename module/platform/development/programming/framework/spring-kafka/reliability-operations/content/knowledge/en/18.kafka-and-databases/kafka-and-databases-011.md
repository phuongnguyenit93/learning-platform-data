# Idempotency Key for DB Writes

In a Spring Kafka system, a Kafka record can be reprocessed by a consumer after a database write has already succeeded. For example, a listener updates a balance and commits the database, then the process stops before committing the Kafka offset. After a restart or rebalance, Kafka redelivers the same record. If the listener performs the debit/credit operation a second time, business data becomes corrupted.

An **idempotency key** is a stable identifier for **one business operation**, allowing the application to recognize that the operation was already applied and avoid writing to the database a second time. For Kafka consumers writing to a database, a solid design typically combines:

1. A stable `eventId` or business operation ID preserved across retries and replays.
2. A **unique constraint** in the database to prevent race conditions between consumers.
3. An inbox/processed-events table or an inherently idempotent business constraint.
4. A **shared database transaction** wrapping both the processed marker and the business mutation.
5. Returning success to the Spring Kafka listener only after the database transaction completes.

Idempotency does not prevent the broker from redelivering a record. It ensures multiple executions of the same logical operation do not produce unintended duplicate side effects.

## 1. Why can Kafka redeliver a record?

With a standard Kafka consumer, the database transaction and the consumer offset commit are two separate steps:

~~~mermaid
sequenceDiagram
    participant K as Kafka
    participant L as Spring Kafka listener
    participant DB as Database
    K-->>L: Event OrderPaid, eventId=E1
    L->>DB: BEGIN, write order, COMMIT
    DB-->>L: Succeeded
    Note over L: Process crashes before committing Kafka offset
    K-->>L: Redeliver event E1
    L->>DB: Without dedup, may write a second time
~~~

Common causes include:

- Process dying after DB commit, before offset commit.
- Consumer group rebalance while the processed offset is not yet committed.
- Network timeout leaving commit progress uncertain.
- Listener retrying after throwing an exception.
- Non-blocking retry topic routing the record to another flow.
- Dead Letter Topic (DLT) replay after fixing a bug.
- Upstream producer resending the same business operation.

This is a natural consequence of **at-least-once delivery**. Do not try to eliminate redelivery completely; design database updates so they can be repeated safely.

## 2. Choosing the right idempotency key

An event may carry several IDs with different meanings:

~~~json
{
  "eventId": "7c53afbb-9e6c-4e84-8df7-dbd3419d39be",
  "eventType": "OrderPaid",
  "orderId": "ord-913",
  "paymentId": "pay-550",
  "amount": 290000,
  "currency": "VND",
  "occurredAt": "2026-11-15T08:12:00Z"
}
~~~

Here:

- `orderId` identifies the aggregate: one order can have multiple valid events.
- `paymentId` identifies one payment, which may fit a specific operation.
- `eventId` identifies one event emitted by the producer; it should stay unchanged across retries and replays.
- Kafka `topic + partition + offset` identifies a physical record on the broker, not the full lifecycle of a business operation.

Comparison table:

| Key | When suitable? | Limitation |
|---|---|---|
| `eventId` | Deduplicating one event across retries, DLT, and republishes | Producer must emit a stable, unique ID per contract |
| `paymentId + operationType` | Applying a specific payment action only once | Each operation type must be clearly defined |
| `orderId` | A single one-time action for an order | Wrongly blocks other valid events for the same order |
| `topic + partition + offset` | Recognizing one source Kafka record | Republish or replay gets a new offset |
| Kafka record key | Routing by aggregate | Not necessarily unique per operation |
| Random UUID generated in consumer | Unsuitable | Every retry generates a new key |
| Hash of full payload | Secondary check to detect conflicting data | Two distinct events could have identical payloads |

Example of the same order having three completely valid events:

~~~text
evt-101: OrderCreated  / orderId=ord-913
evt-102: OrderPaid     / orderId=ord-913
evt-103: OrderShipped  / orderId=ord-913
~~~

If deduplication keys only on `orderId`, the second and third events will be wrongly discarded. The idempotency key must represent **one operation**, not just the affected entity.

## 3. Scope of the key: one event can serve multiple handlers

A single `OrderPaid` business event can be processed by multiple consumer groups:

~~~text
orders.paid
  |
  +-- payment-projection   -> update payment database
  +-- loyalty-projection   -> calculate loyalty points
  +-- analytics-projection -> write analytics data
~~~

If all three handlers share the same processed-events table with `eventId` as the sole primary key, the second and third handlers will see the first handler's marker and skip their own work.

Therefore, schemas commonly use a composite key:

~~~text
(handler_id, event_id)
~~~

If event IDs are only unique per tenant, you may need:

~~~text
(tenant_id, handler_id, event_id)
~~~

`handler_id` is a stable identifier for **the logical business job**, not a random pod or consumer instance ID. If `handler_id` changes on every redeploy, old markers no longer deduplicate. If a handler's semantics intentionally change, use a dedicated versioning/migration strategy.

## 4. Two approaches to idempotent database writes

### Approach A: SQL statements with business preconditions

Some mutations are nearly idempotent by nature:

~~~sql
UPDATE orders
   SET status = 'PAID'
 WHERE order_id = :order_id
   AND status = 'PENDING_PAYMENT';
~~~

If the order is already `PAID`, this update causes no further state change. However, **0 rows updated does not prove the event was already processed**: the order might not exist yet, might have been cancelled, or might be in an invalid state. Business validation is still required.

For additions/subtractions, retries are usually dangerous:

~~~sql
-- If run twice, adds twice.
UPDATE wallets
   SET balance = balance + :amount
 WHERE wallet_id = :wallet_id;

-- Without a unique business constraint, may create two fees.
INSERT INTO payment_fees(payment_id, amount)
VALUES (:payment_id, :fee_amount);
~~~

### Approach B: Inbox / processed events table

Use a table recording processed events. On each received record:

1. Start a database transaction.
2. Attempt to insert the idempotency key guarded by a unique constraint.
3. If the key already exists, skip the mutation because the operation already committed.
4. If the key is new, update the business data.
5. Commit **both marker and mutation in the same transaction**.

~~~mermaid
flowchart TD
    A["Receive Kafka event"] --> B["BEGIN DB transaction"]
    B --> C{"INSERT key with unique constraint"}
    C -->|Already exists| D["Do not repeat side effect"]
    C -->|New| E["Write business data"]
    E --> F{"Write succeeded?"}
    F -->|Yes| G["COMMIT marker + business state"]
    F -->|No| H["ROLLBACK all"]
    D --> I["Listener returns success"]
    G --> I
    H --> J["Listener throws exception for Kafka retry"]
~~~

Crucially, **never commit the marker before the business write**. If the marker exists while the business write never completed, redelivery gets skipped mistakenly and processing is lost.

## 5. PostgreSQL schema with a unique constraint

Example table serving multiple Kafka handlers:

~~~sql
CREATE TABLE processed_kafka_event (
    handler_id       VARCHAR(120) NOT NULL,
    event_id         UUID NOT NULL,
    source_topic     VARCHAR(255),
    source_partition INTEGER,
    source_offset    BIGINT,
    processed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (handler_id, event_id)
);
~~~

The composite primary key protects against concurrent consumers. Source topic, partition, and offset help investigation, though they are not the primary key for **business deduplication**.

Atomic insert query:

~~~sql
INSERT INTO processed_kafka_event (
    handler_id,
    event_id,
    source_topic,
    source_partition,
    source_offset
)
VALUES (
    :handler_id,
    :event_id,
    :topic,
    :partition,
    :offset
)
ON CONFLICT (handler_id, event_id) DO NOTHING;
~~~

PostgreSQL returns the affected row count: `1` if inserted fresh; `0` if the key already exists. When two transactions contend for the same key, the database's unique index arbitrates so only one marker commits. The other transaction may wait on the first transaction's commit or rollback outcome.

`ON CONFLICT` syntax is PostgreSQL-specific; other databases like MySQL or SQL Server use different syntax and semantics. Never copy examples verbatim without adapting to your database dialect.

## 6. Spring Kafka and Spring JDBC example

Suppose a listener receives `OrderPaid` and updates `order_projection`. The event ID is a `UUID`.

### DTO

~~~java
public record OrderPaid(
        UUID eventId,
        String orderId,
        String paymentId,
        long amount) {
}
~~~

### Repository claiming the idempotency key

~~~java
@Repository
public class ProcessedEventRepository {

    private final JdbcTemplate jdbcTemplate;

    public ProcessedEventRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public boolean insertIfAbsent(
            String handlerId,
            UUID eventId,
            String topic,
            int partition,
            long offset) {

        int inserted = jdbcTemplate.update("""
            INSERT INTO processed_kafka_event (
                handler_id, event_id,
                source_topic, source_partition, source_offset
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (handler_id, event_id) DO NOTHING
            """,
            handlerId, eventId, topic, partition, offset
        );

        return inserted == 1;
    }
}
~~~

The repository does not commit on its own. It must participate in the transaction opened by the service.

### Service holding the database transaction

~~~java
@Service
public class OrderPaidProjection {

    private static final String HANDLER_ID = "order-paid-projection";

    private final ProcessedEventRepository processedEventRepository;
    private final JdbcTemplate jdbcTemplate;

    public OrderPaidProjection(
            ProcessedEventRepository processedEventRepository,
            JdbcTemplate jdbcTemplate) {
        this.processedEventRepository = processedEventRepository;
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public void apply(
            OrderPaid event,
            String topic,
            int partition,
            long offset) {

        boolean isNew = processedEventRepository.insertIfAbsent(
            HANDLER_ID, event.eventId(), topic, partition, offset
        );

        if (!isNew) {
            return; // Event was already committed previously.
        }

        int updated = jdbcTemplate.update("""
            UPDATE order_projection
               SET status = 'PAID',
                   payment_id = ?,
                   paid_amount = ?
             WHERE order_id = ?
               AND status = 'PENDING_PAYMENT'
            """,
            event.paymentId(),
            event.amount(),
            event.orderId()
        );

        if (updated != 1) {
            throw new InvalidOrderTransitionException(
                "Cannot apply OrderPaid to " + event.orderId()
            );
        }

        // Commit marker and order projection in the same DB transaction.
    }
}
~~~

`InvalidOrderTransitionException` is an application-defined custom exception. If the update hits an invalid state and throws, the Spring database transaction rolls back both the marker and the business write, allowing the error handler to handle it per policy.

### Kafka listener delegating to the service

~~~java
@Component
public class OrderPaidListener {

    private final OrderPaidProjection projection;

    public OrderPaidListener(OrderPaidProjection projection) {
        this.projection = projection;
    }

    @KafkaListener(
        topics = "orders.paid",
        groupId = "order-paid-projection")
    public void onMessage(ConsumerRecord<String, OrderPaid> record) {
        projection.apply(
            record.value(),
            record.topic(),
            record.partition(),
            record.offset()
        );
    }
}
~~~

Place `@Transactional` on the service bean invoked by the listener through the Spring proxy. Avoid self-invocation such as calling `this.apply(...)` inside the same class, which prevents transaction advice from running as expected.

When the application has multiple transaction managers (Kafka and database), explicitly specify the database transaction manager, for example:

~~~java
@Transactional(transactionManager = "jdbcTransactionManager")
public void apply(...) {
    // DB write and inbox marker here.
}
~~~

This example is valid only if a bean named `jdbcTransactionManager` exists. Never confuse the Kafka transaction manager with the database transaction manager; a Kafka transaction does not protect two SQL statements in the database.

## 7. Why can't you just SELECT then INSERT?

A common pattern that suffers from a race condition:

~~~java
if (!repository.existsByEventId(eventId)) {
    walletRepository.addBalance(walletId, amount);
    repository.insertProcessedEvent(eventId);
}
~~~

Two threads can both observe that the key does not exist yet:

~~~text
Thread A                            Thread B
SELECT exists -> false             SELECT exists -> false
UPDATE balance +100                UPDATE balance +100
INSERT marker                      INSERT marker
~~~

Without a unique constraint, both can commit. Even with a unique constraint, if the business update already committed in a separate transaction, one thread can apply the side effect before its marker is rejected.

Use atomic database uniqueness and **the same transaction** for both the marker and business mutation. In-memory locks, `synchronized` inside one pod, or local caches do not protect across multiple replicas.

## 8. Do not split marker and side effect into two transactions

Correct model:

~~~text
BEGIN DB TRANSACTION
  INSERT inbox marker
  UPDATE wallet/ledger/order
COMMIT BOTH
~~~

Incorrect model 1:

~~~text
BEGIN
  INSERT inbox marker
COMMIT

BEGIN
  UPDATE business state
  -- error here
ROLLBACK

=> Retry sees the marker while business state was not updated.
~~~

Incorrect model 2:

~~~text
BEGIN
  UPDATE balance
COMMIT

BEGIN
  INSERT inbox marker
  -- process dies before commit
ROLLBACK

=> Retry does not see the marker and adds to balance again.
~~~

If either method is annotated with `@Transactional(propagation = REQUIRES_NEW)`, examine it closely because that propagation splits the commit boundary. Especially avoid calling external APIs while holding a long DB transaction if those APIs do not support idempotency.

## 9. Crash matrix between DB and Kafka offset

In the standard listener model, the service's DB transaction finishes before the listener returns; the Spring Kafka container commits the offset per ack mode afterward. Failure windows:

| Failure point | Database | Kafka offset | Outcome on redelivery |
|---|---|---|---|
| Before claiming marker | Unchanged | Uncommitted | Retried from scratch |
| After marker insert, before DB commit | Transaction rolls back | Uncommitted | Reinserts marker and retries |
| After business mutation, before DB commit | Transaction rolls back | Uncommitted | Safely retried |
| After DB commit, before Kafka offset commit | Marker + mutation committed | May be uncommitted | Inbox detects duplicate |
| After both DB commit and offset commit | Mutation persisted | Progress committed | Normally not re-read |
| DLT replay after DB already processed | Marker still present | New offset on replay topic | Side effect not repeated |

Core idea: the system **accepts that the same record may be redelivered**, because the inbox guarantees the DB mutation runs only once once the marker has committed.

Never submit DB work to a `CompletableFuture` and return immediately from the listener. The container may commit the offset before the DB task finishes, creating a hard-to-recover data loss window.

## 10. Kafka Exactly-Once Semantics does not replace DB idempotency

Spring Kafka supports Kafka transactions to atomically commit Kafka outputs and input offsets in consume–process–produce pipelines. Yet the database is a separate resource. If a listener writes to the DB and the Kafka transaction commit fails, the committed DB write persists.

~~~text
Kafka container transaction starts
  -> DB transaction commits successfully
  -> Kafka offset/output commit fails
  -> Kafka record is redelivered
  -> Without inbox, DB side effect may repeat
~~~

Even when using `@Transactional` on a listener, know **which transaction manager** applies. Two separate resource managers do not automatically merge into an atomic distributed transaction.

Thus, **Kafka-scoped EOS** and **idempotent DB writes** complement each other rather than replacing one another.

## 11. When both writing to a database and emitting Kafka output

If business state is written to the DB and the listener also publishes a new event to Kafka, an inbox alone may not be enough.

For instance, the DB commit succeeds while the Kafka output fails to commit. Redelivery sees the inbox marker and returns early: the database is right, yet **the Kafka output is missing** unless the application regenerates it.

A common solution is the **transactional outbox**:

~~~sql
CREATE TABLE outbox_event (
    id           UUID PRIMARY KEY,
    event_type   VARCHAR(120) NOT NULL,
    aggregate_id VARCHAR(120) NOT NULL,
    payload      JSONB NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ
);
~~~

Within **the same DB transaction**:

~~~text
BEGIN
  INSERT inbox marker if not present
  UPDATE business state
  INSERT outbox event
COMMIT

Outbox publisher:
  read unpublished outbox events
  send to Kafka
  mark as published
~~~

If the publisher sends to Kafka and dies before setting `published_at`, the outbox event can be resent. Downstream consumers must deduplicate using a stable output event ID. Outbox prevents losing publish intent committed alongside business data; it does not mean every physical Kafka send happens strictly once.

## 12. Same event ID with conflicting payloads

Suppose two records arrive:

~~~json
{"eventId":"7c53afbb-9e6c-4e84-8df7-dbd3419d39be","amount":200000}
~~~

~~~json
{"eventId":"7c53afbb-9e6c-4e84-8df7-dbd3419d39be","amount":900000}
~~~

If the consumer only checks the ID, the second record is treated as a duplicate and ignored. That can hide a producer bug or contract violation.

You can additionally store `event_type`, `schema_version`, `payload_hash`, or key business fields in the inbox. When encountering an existing key:

1. If the data matches per contract, it is a normal duplicate.
2. If the payload conflicts in business meaning, log a collision and route to quarantine/DLT.
3. Never silently overwrite the marker or apply both operations.

When using a hash, canonicalize payloads because JSON field ordering or benign metadata can vary without changing business meaning. Hashes serve as supporting evidence, not a substitute for producer-guaranteed event identity.

## 13. Idempotency does not solve ordering

Idempotency answers: **"Has this operation already been processed?"**

Ordering answers: **"Is this new operation valid in the current state?"**

Example:

~~~text
event A, seq=10: OrderCreated
event B, seq=11: OrderPaid
event C, seq=12: OrderCancelled
~~~

If A moves to a retry topic, B can be processed before A. Since they have different IDs, the inbox does not treat B as a duplicate, yet business ordering can still break.

One technique uses optimistic versioning:

~~~sql
UPDATE order_projection
   SET status = :new_status,
       event_sequence = :new_sequence
 WHERE order_id = :order_id
   AND event_sequence < :new_sequence;
~~~

This condition prevents an older event from overwriting a newer event, though if business rules forbid **skipping versions**, check `expected_previous_sequence` explicitly or park events awaiting dependencies.

Systems often need all four together:

- `eventId` for deduplication.
- `aggregateId` to identify the target entity.
- `eventSequence`/version to enforce ordering.
- A business state machine to validate allowed transitions.

## 14. When to use topic/partition/offset as the key?

If upstream lacks a durable event ID, you can use source Kafka coordinates:

~~~text
(handler_id, source_topic, source_partition, source_offset)
~~~

This deduplicates **a physical Kafka record**, not necessarily the same logical event:

- Republishing the event to a new offset goes undetected.
- DLT replays or retry topics get new topics/offsets.
- Deleting and recreating a topic can reuse the same name and offsets in a new lifecycle.
- The same business operation across two separate records is still treated as two operations.

If forced to rely on coordinates, preserve **original topic/partition/offset** in metadata when forwarding and define policies for topic recreation. For payments or critical DB mutations, prioritize a business event/operation ID.

## 15. Retention of idempotency keys

Inbox tables can grow rapidly. Yet deleting markers too early causes a DLT replay weeks later to be treated as a brand-new operation.

Key retention should be based on:

- Kafka topic retention.
- Retry topic and DLT retention.
- Maximum window business allows for replays.
- Likelihood of upstream resends after outages or migrations.
- Audit, financial, and duplicate-control requirements.
- Sharding/partitioning strategy and index maintenance cost.

Options include long-term retention for critical ledgers, time-partitioned inbox tables, archiving old markers to a searchable store, or restricting replays to the protected window. **Do not set TTL to just a few seconds of retry duration** if DLTs can be replayed months later.

When changing `handler_id` or key schemas, plan marker migration to avoid triggering a "wave of new events" because old keys no longer match.

## 16. Redis/cache alone does not guarantee once-only DB writes

Redis `SET NX` can claim a key atomically inside Redis, yet it does not form an atomic transaction with the database:

~~~text
Redis SET NX key -> success
  |
  +-- DB UPDATE fails
  |
Redis still holds key -> retry is wrongly blocked
~~~

Caches also have eviction/TTL, restarts, and replication edge cases. A cache can optimize lookups, but the database unique constraint inside the DB transaction should remain the source of truth when business writes need durable protection.

Avoid `ConcurrentHashMap` or Java `synchronized` for deduplication across pods: they protect only a single JVM and lose state on restart.

## 17. Classifying exceptions with Kafka retries

| Case | Handling |
|---|---|
| Inbox marker exists and operation genuinely committed | Return success; do not rewrite |
| Transient DB deadlock/connection error | Roll back, retry with backoff |
| Payload missing required field or invalid event ID | Non-retryable; DLT/quarantine |
| Invalid business state transition | Roll back marker; classify per business policy |
| Same event ID with different payload | Alert on collision, quarantine |
| DLT publishing fails | Recovery incomplete; never drop record silently |
| Conflict on another business unique constraint | Distinguish duplicate from conflicting data |

With non-transactional Spring Kafka consumers, `DefaultErrorHandler` can retry transient errors and send permanent errors to the DLT. With Kafka transactional listeners, after-rollback handling typically uses `DefaultAfterRollbackProcessor`. No Kafka mechanism replaces a database transaction for atomically persisting the marker and business mutation.

## 18. Batch listeners and concurrency

When processing batches, some records may commit to the DB before a later record fails. When the Kafka batch reprocesses, inbox keys for committed records skip duplicates.

Two transaction boundary styles exist:

- **One DB transaction per record:** process each event through a transactional service; committed records keep their own markers.
- **One DB transaction for the whole batch:** all markers and mutations commit or roll back together; weigh transaction duration, locks, and batch retry semantics.

With multiple consumer instances, the database unique index arbitrates concurrent claims. If two transactions insert the same `(handler_id,event_id)`, one waits to see whether the other commits or rolls back. Set suitable DB timeouts/retries and monitor lock contention.

If using multiple databases/shards, route keys to the right shard or use a global uniqueness mechanism. Per-shard unique indexes do not guarantee uniqueness if the same logical event hits two different shards.

## 19. Designing tests for idempotency

A test suite should cover:

1. Same event ID received twice: business state applies only once.
2. Two threads racing to claim the same key: only one transaction applies the mutation.
3. Failure after marker insert, before DB commit: both marker and side effect roll back.
4. Failure after DB commit, before Kafka offset commit: redelivery is skipped.
5. Replay from DLT keeping the same event ID: creates no new business effects.
6. Two independent handlers receiving the same event ID: each applies its own work accurately.
7. Same event ID with conflicting payload: reports collision rather than ignoring silently.
8. Out-of-order events: version/state machine preserves invariants.
9. DB connection timeout/deadlock: retries do not leave half-written markers.
10. Outbox republished twice: downstream deduplicates output event ID.

These scenarios are **test designs for the learner**; no tests or content QA were run during the authoring of this lesson. Concurrency tests should use a real database or Testcontainers to verify unique indexes, transaction isolation, and SQL dialect.

## 20. Observability and operations

| Metric | Meaning |
|---|---|
| `db_idempotency_new_total` | Number of new business operations applied |
| `db_idempotency_duplicate_total` | Volume of redelivered records skipped |
| `db_idempotency_collision_total` | Same key with conflicting data |
| `db_transaction_rollback_total` | Failures before DB commit |
| Inbox unique key conflict/wait | Contention among consumers |
| Kafka consumer lag and rebalances | Offset progress and redeliveries |
| DLT volume/replay count | Long-lived duplicate exposure |
| Inbox storage/index size | Retention cost |
| Outbox publish failures | DB-to-Kafka paths needing recovery |

An event log can include `eventId`, `handlerId`, `topic`, `partition`, `offset`, and outcome `NEW` / `DUPLICATE` / `FAILED`. Never use event IDs as metric labels due to high cardinality; put them in properly access-controlled traces/logs.

Example:

~~~text
kafka_db_apply handler=order-paid-projection
  eventId=7c53afbb-9e6c-4e84-8df7-dbd3419d39be
  source=orders.paid-2@418
  outcome=DUPLICATE
  mutation=SKIPPED
~~~

If duplicate counts spike suddenly, investigate crashes/rebalances, offset commit failures, retry topics, DLT replays, and upstream duplicates rather than blaming only the broker.

## 21. Runbook when duplicate DB writes are detected

1. Identify the duplicated business operation: event ID, payment ID, order ID, mutation type.
2. Trace all deliveries across topic/partition/offset, consumer group, and retry stages.
3. Verify the producer kept the ID unchanged across retries/republishes.
4. Confirm the unique constraint exists in the production database with the right scope.
5. Confirm marker + business write actually ran in the same DB transaction.
6. Verify Spring `@Transactional` executed through a proxy with the right DB transaction manager.
7. Look for `REQUIRES_NEW`, JDBC auto-commit, async tasks, or network calls splitting commit boundaries.
8. Check whether the handler used `SELECT EXISTS` instead of atomic insert.
9. Check marker retention and late DLT replay cases.
10. Check for same-key conflicting payloads and event ordering issues.
11. If Kafka outputs also exist, inspect the outbox and the DB-commit/Kafka-output-fail window.
12. Remediate duplicated data via an audited business procedure; never manually delete markers and bulk replay.

For ledgers and payments, compensating side effects must follow business rules; never arbitrarily revert a DB write if downstream systems already acted on it.

## 22. Mistakes to avoid

- Using `orderId` as the ID for every event of the same order.
- Generating a new UUID inside the consumer on every received record.
- Using Kafka offset as the business operation ID in every case.
- Checking `exists` in Java without a DB unique constraint.
- Committing the marker in a separate transaction before the mutation.
- Claiming a key in Redis and updating the DB as if those two steps were atomic.
- Letting the listener return before the DB transaction commits.
- Treating `KafkaTransactionManager` as the database transaction manager.
- Ignoring same-key different-payload events without investigation.
- Dropping markers earlier than the DLT replay window.
- Using only an inbox and forgetting an outbox when business state must emit Kafka output.
- Assuming idempotency automatically enforces ordering across distinct events.

## 23. Implementation checklist

- [ ] Idempotency key represents the operation and stays stable across retries/replays.
- [ ] Key scope includes handler/tenant where needed.
- [ ] Durable unique constraint exists in the database.
- [ ] Marker and business mutation commit in the same DB transaction.
- [ ] Transaction rolls back the marker as well if the business write fails.
- [ ] Listener returns success only after the DB commit actually completes.
- [ ] No self-invocation or misconfigured transaction manager.
- [ ] Handling exists for same-key/different-payload collisions.
- [ ] Version/sequence checks exist if ordering matters.
- [ ] Marker retention covers retries, DLT, and manual replays.
- [ ] Inbox/outbox designed if Kafka publishing is needed after DB commit.
- [ ] Logs, metrics, and runbooks cover duplicates/collisions/rollbacks.

**Conclusion:** An idempotency key for DB writes lets a Spring Kafka consumer deliver **non-duplicated business outcomes** on top of at-least-once delivery. Use a stable event or business operation ID, a database unique constraint, and a shared transaction wrapping both the marker and side effect. When Kafka redelivers a record after a crash, retry, or DLT replay, the listener recognizes the duplicate without updating the DB a second time. For Kafka outputs and external effects, add outboxes, target-system idempotency, and ordering controls—Kafka offsets or Kafka transactions do not satisfy those requirements automatically.
