# Outbox and Compensation When Coordinating Databases with External Systems

A business flow in a Spring Data R2DBC application often needs to modify data in a database and then notify other systems. For example, when creating an order, the application needs to save the order into PostgreSQL and send an `OrderCreated` event to a message broker so inventory, billing, or notification services can continue processing.

If the application writes to the database and publishes a message via two independent operations, there is always a window where one succeeds and the other fails. The database might commit while the broker never receives the message; or the message might be sent while the database transaction rolls back. This is the *dual write* problem.

Transactional Outbox solves the coordination between a database transaction and event emission: the application writes business data alongside an outbox record inside the same R2DBC transaction. A separate relay reads committed outbox rows and publishes messages. Thus, if the transaction commits, the information to emit is durably saved in the database; if the transaction rolls back, neither business data nor the outbox row exists.

When a workflow spans multiple databases or independent services, a single service's local transaction cannot roll back the entire system. In that case, a long-running workflow such as a Saga is needed, using local steps and *compensating* actions (*compensation*) to restore the business to an acceptable state when a step fails.

Outbox and Saga solve related but distinct problems: Outbox guarantees reliable event forwarding from a single local database; Saga coordinates multiple business steps across independent resources and handles failures via compensation or forward recovery.

## 1. The Dual Write Problem

Suppose an order-creation API must:

1. Insert the order into the database.
2. Publish `OrderCreated` to the broker.

Deceptively simple code:

```java
return orderRepository.save(order)
        .flatMap(saved -> eventPublisher.publish(
                new OrderCreated(saved.id(), saved.orderCode()))
                .thenReturn(saved));
```

These two operations do not automatically form one atomic transaction. The database transaction manages only the database resource; the broker may be a separate system with its own protocol and transaction boundary.

### 1.1. Database Commits but Publish Fails

```text
Application                 Database                Message broker
    |                           |                          |
    |---- INSERT order -------> |                          |
    |---- COMMIT ------------> |                          |
    |                           |                          |
    |---- publish event ---------------------------------> X
    |                           |                    network/error
```

The order exists, yet no event was published. Inventory or billing never learns the new order was created. If the API returns an error and the client retries, the application may create a duplicate order unless an idempotency key is present.

### 1.2. Publish Succeeds but Database Rolls Back

```text
Application                 Database                Message broker
    |                           |                          |
    |---- publish event ---------------------------------> |
    |                           |                    accepted
    |---- INSERT order -------> |                          |
    |---- COMMIT ------------> X
    |                      constraint/error                |
```

Consumers receive `OrderCreated`, yet cannot find the order in the database. This is an event describing state that was never committed.

### 1.3. Why Not Just Use @Transactional?

`@Transactional` with `R2dbcTransactionManager` manages transactions on the configured `ConnectionFactory`. It does not automatically encompass a message broker or external HTTP service.

Even if publishing code runs inside a `@Transactional` method, sending a message does not automatically roll back when the database transaction fails. Conversely, rolling back the database does not retract a message the broker already accepted.

Some systems support distributed transactions or multi-resource transaction protocols, but you should not assume a standard R2DBC transaction provides atomic commits across a database and a broker. In modern service architectures, Outbox and Saga are usually far easier to operate than coupling multiple resources into a distributed transaction.

## 2. How Does Transactional Outbox Work?

An outbox is a table inside the same database as the business data. Within a single transaction, the application writes:

- Business records, such as `orders`.
- Event records to publish, such as `outbox_events`.

After the transaction commits, a relay reads unpublished outbox records and publishes them to the broker. Once the broker acknowledges successful publication, the relay marks the record as published.

```text
HTTP request
    |
    v
Reactive service
    |
    |---- R2DBC transaction ---------------------------+
    |                                                  |
    |   INSERT orders                                  |
    |   INSERT outbox_events                           |
    |                                                  |
    +---------------- COMMIT --------------------------+
                                                       |
                                                       v
                                                Outbox relay
                                                       |
                                                       v
                                                Message broker
                                                       |
                                                       v
                                                Consumer services
```

If the transaction rolls back, both the order and the outbox event roll back. If commit succeeds and the application crashes before publishing, the outbox row persists so the relay can send it after restarting.

### 2.1. What Does an Outbox Guarantee?

Provided business data and the outbox row are written in the same local transaction:

- No order commits without its corresponding outbox record due to a failure between the two INSERTs.
- No outbox event commits when the business record in the same transaction rolled back.
- The relay can resume after restarts because pending state is durably persisted.
- Publishing can be retried without forcing the client to re-execute order creation.

An outbox does not automatically guarantee exactly-once message delivery. A relay can publish successfully and crash before marking `PUBLISHED`; once the lease expires, the event may be published again. Hence, consumers need idempotency.

### 2.2. Critical Requirement: Same Database Transaction

The order repository and outbox repository must share the same database resource and the same reactive transaction manager. If orders are written via `ordersConnectionFactory` while the outbox is written via `auditConnectionFactory`, a single `R2dbcTransactionManager` does not provide atomicity across both connection factories.

When an outbox lives in a separate database, it no longer solves dual writes this way. Place the outbox in the same database that owns the business data, or design a suitable Saga/forwarding pattern.

## 3. Designing the Outbox Table

An outbox row needs enough information for the relay to know which event to emit, which aggregate it belongs to, and its current delivery status.

PostgreSQL schema example:

```sql
CREATE TABLE outbox_events (
    id UUID PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(120) NOT NULL,
    aggregate_sequence BIGINT NOT NULL,
    event_type VARCHAR(160) NOT NULL,
    event_version INTEGER NOT NULL DEFAULT 1,
    payload TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    locked_by UUID,
    locked_until TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    last_error TEXT,
    CONSTRAINT uq_outbox_aggregate_sequence
        UNIQUE (aggregate_type, aggregate_id, aggregate_sequence),
    CONSTRAINT ck_outbox_status
        CHECK (status IN ('PENDING', 'PROCESSING', 'PUBLISHED', 'DEAD'))
);

CREATE INDEX idx_outbox_pending
    ON outbox_events(next_attempt_at, created_at, id)
    WHERE status = 'PENDING';

CREATE INDEX idx_outbox_expired_lease
    ON outbox_events(locked_until, created_at, id)
    WHERE status = 'PROCESSING';
```

This is a PostgreSQL example; UUID types, `TIMESTAMPTZ`, partial indexes, and claim syntax in later sections must be adapted if using a different database system.

### 3.1. Column Meanings

| Column | Meaning |
|---|---|
| `id` | Unique event ID; used as the idempotency key at consumers |
| `aggregate_type` | Aggregate type, e.g., `Order` |
| `aggregate_id` | ID of the order/customer/payment the event describes |
| `aggregate_sequence` | Event order within an aggregate if business logic requires ordering |
| `event_type` | Event name, e.g., `OrderCreated` |
| `event_version` | Schema version of the payload |
| `payload` | Serialized event data snapshot |
| `occurred_at` | Timestamp when the business event occurred |
| `created_at` | Timestamp when the outbox row was written |
| `status` | `PENDING`, `PROCESSING`, `PUBLISHED`, or `DEAD` |
| `attempts` | Number of times the relay has claimed/attempted delivery |
| `next_attempt_at` | Earliest timestamp eligible for retry |
| `locked_by` | Worker currently holding the lease |
| `locked_until` | Lease expiration; once expired, another worker may reclaim it |
| `published_at` | Timestamp when the relay recorded successful publication |
| `last_error` | Filtered/length-bounded error details |

Not every application needs all of these columns. For simple workloads, you can start with ID, type, payload, timestamps, and status. If multiple workers run, a claim/lease mechanism is needed to avoid processing the same row concurrently.

### 3.2. Storing Full Payload vs. Only Aggregate ID

Two common approaches exist:

- **Event snapshot:** stores the complete payload consumers need as of the moment the event occurred.
- **Pointer event:** stores only aggregate ID/version; consumers fetch current data from the source service.

Snapshots let consumers understand the state that occurred even if the order changes afterward. Pointer events are smaller, though consumers may read newer state rather than state as of event creation.

For events like `OrderCreated`, the payload should usually contain enough data for consumers to process without immediately calling back to the source service. Never serialize an entire persistence entity if it contains internal fields, secrets, or data outside the public event contract.

### 3.3. Versioning Event Schemas

Include `event_version` or a version field in the envelope so consumers know how to interpret the payload. When adding new fields, prefer backwards-compatible changes: old consumers ignore unknown fields; new producers still include required fields expected by old consumers during rolling deployments.

Never change the meaning of an existing field while keeping the same version if consumers could interpret it differently. For breaking changes, emit a new event type/version or use controlled upcasters/adapters.

## 4. Writing Business Data and Outbox in the Same R2DBC Transaction

This is the most critical step for ensuring atomicity. The business repository and outbox repository must share the same `ConnectionFactory` and transaction manager.

Outbox entity example:

```java
@Table("outbox_events")
public record OutboxEventEntity(
        @Id UUID id,
        @Column("aggregate_type") String aggregateType,
        @Column("aggregate_id") String aggregateId,
        @Column("aggregate_sequence") Long aggregateSequence,
        @Column("event_type") String eventType,
        @Column("event_version") Integer eventVersion,
        String payload,
        @Column("occurred_at") Instant occurredAt,
        @Column("created_at") Instant createdAt,
        String status,
        Integer attempts
) {
}
```

Service example:

```java
@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final R2dbcEntityTemplate ordersEntityTemplate;
    private final ObjectMapper objectMapper;

    public OrderApplicationService(
            OrderRepository orderRepository,
            R2dbcEntityTemplate ordersEntityTemplate,
            ObjectMapper objectMapper) {
        this.orderRepository = orderRepository;
        this.ordersEntityTemplate = ordersEntityTemplate;
        this.objectMapper = objectMapper;
    }

    @Transactional(transactionManager = "ordersTransactionManager")
    public Mono<OrderEntity> placeOrder(CreateOrderCommand command) {
        OrderEntity draft = OrderEntity.from(command);

        return orderRepository.save(draft)
                .flatMap(saved -> {
                    UUID eventId = UUID.randomUUID();
                    Instant occurredAt = Instant.now();

                    return serializeEvent(saved, eventId, occurredAt)
                        .flatMap(payload -> {
                            OutboxEventEntity event = new OutboxEventEntity(
                                    eventId,
                                    "Order",
                                    saved.id().toString(),
                                    saved.version(),
                                    "OrderCreated",
                                    1,
                                    payload,
                                    occurredAt,
                                    occurredAt,
                                    "PENDING",
                                    0);

                            return ordersEntityTemplate.insert(event)
                                    .thenReturn(saved);
                        });
                });
    }

    private Mono<String> serializeEvent(
            OrderEntity order, UUID eventId, Instant occurredAt) {
        return Mono.fromCallable(() -> objectMapper.writeValueAsString(
                new OrderCreatedEvent(
                        eventId,
                        order.id(),
                        order.orderCode(),
                        order.version(),
                        occurredAt)))
                .onErrorMap(JsonProcessingException.class,
                        EventSerializationException::new);
    }
}
```

This is structural sample code; constructors, version fields, and exception classes must match your real domain. The example assumes one event is emitted per aggregate version; if a single version emits multiple events, use a per-event sequence. `eventId` is generated once and reused identically in both the payload and the outbox row. Inject a `Clock` instead of `Instant.now()` so timestamps remain testable. Serialization can run synchronously for small payloads; for large payloads or blocking serializers, consider threading and resource impact.

### 4.1. Why `flatMap` and `thenReturn` Matter

The outbox-saving publisher must be chained into the publisher returned by the method. If you call `outboxRepository.save(event).subscribe()` inside the service, it starts an independent subscription and may execute outside the original transaction.

In the example above, `eventId` is generated in the application before insertion. For an entity without `@Version`, Spring Data may treat a non-null ID as an existing entity when calling `save`. Using `R2dbcEntityTemplate.insert(event)` makes it explicit that this is always a fresh insert. Another option is implementing `Persistable` or appropriate newness detection if you want to keep the repository abstraction.

The proper chain is:

```java
return orderRepository.save(draft)
        .flatMap(saved -> outboxRepository.save(toOutbox(saved))
                .thenReturn(saved));
```

The transaction manager observes completion or error of the returned publisher. If saving to the outbox emits an error, the error signal exits the pipeline and the transaction can roll back both the order and the outbox row.

### 4.2. Do Not Publish to the Broker Inside the Order-Writing Transaction

Do not hold a database connection/transaction open while waiting on broker network I/O:

```java
// Do not use this approach as a transactional outbox.
return orderRepository.save(order)
        .flatMap(saved -> broker.publish(toEvent(saved))
                .thenReturn(saved));
```

Broker publication does not participate in the R2DBC transaction. If the broker is slow, the connection stays pinned; if publication succeeds and the database commit fails, consumers still receive the event. Write only the outbox row inside the transaction; let the relay publish after the transaction commits.

### 4.3. Verifying the Same Transaction Manager and ConnectionFactory

Example:

```java
@EnableR2dbcRepositories(
        basePackages = "com.example.orders.repository",
        entityOperationsRef = "ordersEntityTemplate",
        transactionManagerRef = "ordersTransactionManager")
class OrdersR2dbcConfiguration {
}
```

`OrderRepository` and `OutboxEventRepository` must belong to the same repository group, or at least share the matching template/resource. Both `ordersEntityTemplate` and `ordersTransactionManager` must inject the same `ordersConnectionFactory` bean.

If the outbox repository is accidentally scanned under a different database group, code will still compile while atomicity is silently lost. Testing rollback is an essential verification step.

### 4.4. Testing Rollback When Outbox Insert Fails

Write an integration test where the outbox insert violates a constraint or uses a test double that emits an error before commit. After the method errors, query the order from an independent transaction and verify the order does not exist.

Tests must use a real database and the configured transaction manager. Mocked repositories do not prove two writes share the same transaction.

## 5. Designing the Outbox Relay to Read and Publish

The relay's responsibilities are:

1. Find events due for processing.
2. Claim events so other workers do not process them simultaneously.
3. Commit the claim/lease state.
4. Publish events to the broker.
5. Upon broker acknowledgement, mark events as published.
6. On failure, schedule a retry or transition to a dead-letter state.

Do not hold a database transaction open while calling the broker. One pattern is claiming a batch in a short transaction, committing the lease, and then publishing outside the transaction.

### 5.1. Processing States

| Status | Meaning |
|---|---|
| `PENDING` | Waiting to publish or due for retry |
| `PROCESSING` | Claimed by a worker currently holding a lease |
| `PUBLISHED` | Broker acknowledged and relay recorded completion |
| `DEAD` | Exceeded max attempts or hit an error requiring manual handling |

Leases let another worker reclaim events if the original worker dies. `locked_until` is the claim expiration; `locked_by` ensures only the worker currently owning the claim can update the state.

### 5.2. Claiming a Batch in PostgreSQL

An atomic approach uses `FOR UPDATE SKIP LOCKED` so multiple workers claim distinct rows:

```sql
UPDATE outbox_events AS e
SET status = 'PROCESSING',
    locked_by = :workerId,
    locked_until = CURRENT_TIMESTAMP
        + (:leaseSeconds * INTERVAL '1 second'),
    attempts = e.attempts + 1
FROM (
    SELECT id
    FROM outbox_events
    WHERE (
        status = 'PENDING'
        AND next_attempt_at <= CURRENT_TIMESTAMP
    ) OR (
        status = 'PROCESSING'
        AND locked_until < CURRENT_TIMESTAMP
    )
    ORDER BY created_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT :batchSize
) AS claimed
WHERE e.id = claimed.id
RETURNING e.id, e.aggregate_type, e.aggregate_id,
          e.aggregate_sequence, e.event_type, e.event_version,
          e.payload, e.attempts, e.locked_by;
```

This SQL is PostgreSQL-specific. `SKIP LOCKED` lets workers skip rows already locked by another worker. `UPDATE ... RETURNING` claims rows and returns their data for publishing in one step. For other databases, use an equivalent claim/lease mechanism.

### 5.3. Claiming Inside a Short Transaction

Example using `DatabaseClient`:

```java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<List<ClaimedOutboxEvent>> claimBatch(
        UUID workerId, int batchSize, int leaseSeconds) {

    return databaseClient.sql(CLAIM_SQL)
            .bind("workerId", workerId)
            .bind("batchSize", batchSize)
            .bind("leaseSeconds", leaseSeconds)
            .map((row, metadata) -> new ClaimedOutboxEvent(
                    row.get("id", UUID.class),
                    row.get("event_type", String.class),
                    row.get("aggregate_id", String.class),
                    row.get("payload", String.class),
                    row.get("attempts", Integer.class)))
            .all()
            .collectList();
}
```

The reactive method completes after fetching the batch. The transaction manager commits the lease before the outer publisher continues publishing. When using `DatabaseClient` alongside `@Transactional`, ensure the client uses the same `ConnectionFactory` as the manager.

A single UPDATE statement is atomic in the database; a short transaction remains useful for managing connection resources and consistency when claiming involves additional statements.

### 5.4. Publishing After Claim Commit

```java
public Mono<Void> dispatchOnce() {
    return claimService.claimBatch(workerId, 100, 60)
            .flatMapMany(Flux::fromIterable)
            .concatMap(this::publishOne)
            .then();
}

private Mono<Void> publishOne(ClaimedOutboxEvent event) {
    return brokerPublisher.publish(event)
            .then(outboxStore.markPublished(event.id(), workerId))
            .onErrorResume(error -> outboxStore.scheduleRetry(
                    event.id(), workerId, error));
}
```

This example uses `concatMap` to process sequentially within a worker. You can introduce bounded concurrency if the broker and database can handle it, factoring in per-aggregate ordering and lease duration. `markPublished` should update the row only if `locked_by` still matches the current worker; otherwise, the worker lost its lease.

### 5.5. Schedulers and Subscriptions at Application Boundaries

`dispatchOnce()` returns a publisher and runs only when subscribed to. You can use a scheduler or lifecycle component to manage a single application-level subscription. Retain the `Disposable` to stop the relay on shutdown, handle errors on each polling cycle, and avoid creating duplicate overlapping subscriptions.

Do not call `subscribe()` inside business services to detach an operation from a transaction. The relay is an independent background process and thus needs a root subscription owned by its lifecycle.

## 6. Error Handling, Retries, and Dead-Letter State

Publishing can fail due to temporary broker unavailability, timeouts, authentication issues, quotas, or invalid payloads. The relay must distinguish retryable errors from errors requiring manual intervention.

### 6.1. Retrying with Exponential Backoff

A common retry schedule:

```text
delay = min(maxDelay, baseDelay * 2^(attempt - 1)) + jitter
```

Example:

| Attempt | Illustrative base delay |
|---:|---:|
| 1 | 1 second |
| 2 | 2 seconds |
| 3 | 4 seconds |
| 4 | 8 seconds |
| 5 | 16 seconds |

Jitter keeps multiple workers from retrying simultaneously after a broker outage. Actual values must reflect SLAs, timeouts, and broker capacity.

### 6.2. Updating Retry State

PostgreSQL SQL example:

```sql
UPDATE outbox_events
SET status = CASE
        WHEN attempts >= :maxAttempts THEN 'DEAD'
        ELSE 'PENDING'
    END,
    next_attempt_at = CURRENT_TIMESTAMP
        + (:delaySeconds * INTERVAL '1 second'),
    locked_by = NULL,
    locked_until = NULL,
    last_error = :safeError
WHERE id = :eventId
  AND status = 'PROCESSING'
  AND locked_by = :workerId;
```

The `locked_by` predicate prevents an old worker from overwriting the row after its lease was reclaimed by another worker. `safeError` should be truncated and scrubbed of credentials/PII; never store massive stack traces in the outbox table.

### 6.3. Mark Published Only After Broker Acknowledgement

Transition to `PUBLISHED` only after the broker client confirms publication per its semantics. If marked before sending, the process could crash after the update and lose the event.

However, if the broker already accepted the event and the application crashes before marking it, the relay will resend after the lease expires. This is an intentional duplicate under the at-least-once model.

### 6.4. Dead-Letter State and Manual Operations

Events move to `DEAD` after reaching maximum attempts or encountering an error classified as non-retryable. Operational tooling should allow operators to:

- Inspect event type, aggregate ID, event ID, and redacted error details.
- View attempt count and last attempt timestamp.
- Verify whether consumers/brokers already received the event when possible.
- Trigger a retry after resolving the root cause.
- Mark as skipped only when permitted by business policy and with an audit record.

Do not delete dead events immediately. They serve as evidence of an undelivered business operation and may be needed for investigation.

### 6.5. Lease Duration and Heartbeats

Leases must exceed the expected processing time of an event/batch, or be renewed while the worker is actively working. If leases are too short, another worker may reclaim an event while the original worker is still publishing, increasing duplicates.

For slow publications, renew leases periodically with a conditional update checking `locked_by`. If a worker crashes, the lease expires and the event is reclaimed. Consumer idempotency remains the final safeguard.

## 7. Delivery Semantics: At-Least-Once and Idempotency

Outbox relays typically provide *at-least-once delivery*: an event may be delivered one or more times, while the relay keeps trying until it succeeds or moves to a state requiring attention.

Do not advertise end-to-end exactly-once delivery simply because a broker supports transactions or the outbox has unique IDs. Spanning the database, relay, broker, consumer, and target database crosses multiple boundaries. A crash at the right instant can trigger redelivery.

### 7.1. Using a Stable Event ID

Every event needs a unique ID generated when writing the outbox row. On retry, the relay resends the exact same event ID rather than generating a new one. Consumers use that ID to recognize duplicates.

An envelope might contain:

```json
{
  "eventId": "8e4f9e10-7b0f-4a2d-9c6a-9a4b6d8d5f10",
  "eventType": "OrderCreated",
  "eventVersion": 1,
  "aggregateType": "Order",
  "aggregateId": "order-1042",
  "aggregateSequence": 1,
  "occurredAt": "2026-11-15T08:30:00Z",
  "payload": {
    "orderCode": "ORD-001042",
    "totalAmount": "250000.00"
  }
}
```

This is an illustrative payload. Choose ID types, timestamps, and decimal encodings per your actual contract. For currency, decimal strings usually avoid binary floating-point representation issues in JSON consumers.

### 7.2. Consumer Inbox / Processed Messages Table

Consumers can record processed events in the same database as their business mutations:

```sql
CREATE TABLE processed_messages (
    consumer_name VARCHAR(120) NOT NULL,
    message_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, message_id)
);
```

Upon receiving an event, the consumer executes within a single transaction:

1. Insert `(consumer_name, message_id)`.
2. If the key already exists, treat the event as a duplicate and skip business processing.
3. If the new insert succeeds, update business data.
4. Write any downstream outbox event if further events must be emitted.
5. Commit the transaction.
6. Acknowledge the message only after the transaction completes successfully per broker integration semantics.

### 7.3. Safely Inserting Idempotency Keys

With PostgreSQL:

```sql
INSERT INTO processed_messages (consumer_name, message_id)
VALUES (:consumerName, :messageId)
ON CONFLICT DO NOTHING;
```

Check `rowsUpdated`: if 1, the message is new; if 0, the message was already processed. This avoids attempting a duplicate insert and catching a constraint exception inside a PostgreSQL transaction, because a constraint violation can put the current transaction into an aborted state until rollback.

### 7.4. Consumer Processing and Inbox in the Same Transaction

```java
@Transactional(transactionManager = "inventoryTransactionManager")
public Mono<Void> handle(OrderCreatedEvent event) {
    return inboxStore.recordIfNew("inventory", event.eventId())
            .flatMap(isNew -> {
                if (!isNew) {
                    return Mono.empty();
                }

                return inventoryService.reserveFor(event)
                        .then();
            });
}
```

`recordIfNew` must insert the idempotency key through the same database and `ConnectionFactory` as the inventory operation. If the consumer writes the inbox to one database and inventory to another, atomicity is lost again.

### 7.5. Acknowledge After Commit

If a message is acknowledged before the consumer transaction commits, the process can crash after ack and before commit; the broker will not redeliver and the business update is lost. If commit finishes yet ack fails, the broker redelivers; inbox deduplication safely handles the duplicate.

Exact ack mechanics depend on the broker and framework integration. Verify that reactive listeners acknowledge only after the publisher completes successfully and the transaction has committed.

## 8. Ordering and Event Sequences

Not every event requires global ordering. However, a single aggregate may require events to be processed in order, for example:

```text
OrderCreated (sequence 1)
OrderPaid    (sequence 2)
OrderShipped (sequence 3)
```

If `OrderShipped` arrives before `OrderPaid`, the consumer might transition state incorrectly.

### 8.1. Generating Per-Aggregate Sequences

You can use the aggregate's version or a dedicated sequence incremented inside the same transaction. A unique constraint `(aggregate_type, aggregate_id, aggregate_sequence)` prevents creating two events with the same sequence.

Do not rely solely on timestamps for strict ordering: two events can share the same timestamp or clocks can skew across instances.

### 8.2. Broker Partition Keys

If the broker supports key-based partitioning, use `aggregate_id` as the partition key so events for the same aggregate land in the same partition. This preserves ordering within a partition per broker semantics.

A partition key does not automatically guarantee the relay publishes in exact sequence if multiple workers claim and publish in parallel. You must limit each aggregate to one in-flight event at a time or design consumers to detect sequence gaps.

### 8.3. Handling Sequence Gaps at Consumers

A consumer can store the last processed sequence per aggregate. Upon receiving a sequence higher than the next expected one, temporarily hold/retry the event or request replay of the missing event. Upon receiving an older already-processed sequence, skip it via idempotency.

This strategy adds complexity; apply it only when ordering is a true business invariant. For many independent events, serializing the entire relay is unnecessary.

## 9. Outbox Cleanup and Retention

The outbox table grows continuously. Define how long published events are retained and the retention policy for dead events.

### 9.1. Do Not Delete Immediately After Publishing

Keep published events for a period to:

- Investigate emitted events.
- Reconcile with brokers and consumers.
- Retry or replay via operational procedures.
- Analyze duplicates and delivery latency.

After the retention period, archive or delete in batches. Never run a giant delete during peak hours on a large table.

### 9.2. Batch Cleanup

PostgreSQL example:

```sql
DELETE FROM outbox_events
WHERE id IN (
    SELECT id
    FROM outbox_events
    WHERE status = 'PUBLISHED'
      AND published_at < CURRENT_TIMESTAMP - INTERVAL '14 days'
    ORDER BY published_at
    LIMIT 1000
);
```

Run repeatedly in batches until all aged-out rows are cleared. A 14-day retention window is only an example; pick one based on audit, replay, and storage requirements.

### 9.3. Archiving Dead Events

Dead events require longer retention or separate archiving until an operational decision is made. If you delete dead events without an audit record, the organization may lose evidence explaining why downstream services missed a business event.

### 9.4. Partitioning at High Volume

For high-volume outboxes, consider time-based partitioning or an archive strategy suited to your database. Partition keys must remain compatible with unique constraints and how the relay claims events. Do not add partitioning before measuring actual volume and overhead.

## 10. Observability for the Outbox Relay

An outbox can silently accumulate a backlog if the relay stops or the broker becomes unavailable. Monitor at least:

- Row counts for `PENDING`, `PROCESSING`, `PUBLISHED`, `DEAD`.
- Age of the oldest pending event.
- Duration from `occurred_at` to `published_at`.
- Average attempt count and retry distribution.
- Expired lease count and reclaimed events.
- Publish success/failure rate.
- Batch size, poll duration, and relay throughput.
- Consumer lag and duplicate rate if exposed by the broker.

### 10.1. Backlog Alerting

Useful alerts:

- Pending count increasing steadily.
- Pending event older than SLA.
- Dead events appearing or spiking rapidly.
- Repeated lease expirations.
- Relay failing to publish within a defined window.
- Rising publish latency.

Watching pending count alone may not be enough; one critical event can remain stuck even while total backlog looks small. Monitor oldest pending age.

### 10.2. Correlation and Tracing

Include `eventId`, `aggregateId`, `correlationId`, trace context, and saga ID in envelopes and logs per policy. Never put access tokens or secrets in payloads. When the relay publishes, create a producer span and propagate trace context via headers using standard broker instrumentation.

## 11. When Are Sagas and Compensation Needed?

Outbox solves reliably forwarding events from one local database to a broker. It does not make multiple databases commit or roll back atomically together.

For example, creating an order might involve:

1. Order service creates the order.
2. Inventory service reserves stock.
3. Payment service authorizes or captures payment.
4. Shipping service creates a shipment order.

Each service owns its own database. If payment fails after inventory reserved stock, you cannot roll back inventory's database transaction using order service's transaction manager. A compensating business action is needed: releasing the reserved stock.

A Saga is a sequence of local transactions where each step may emit the next event/command. When a step fails, the Saga triggers compensation for completed steps according to business rules.

### 11.1. Sagas Are Not Distributed Rollbacks

Compensation does not erase history as if an operation never occurred. It executes a new business action to undo or mitigate the effect of an earlier action.

Examples:

| Completed action | Possible compensating action |
|---|---|
| Reserve inventory | Release reservation |
| Authorize payment | Void authorization |
| Capture payment | Refund payment |
| Create shipment label | Cancel label if carrier permits |
| Send email | Cannot be recalled; can send a follow-up correction |
| Ship package | May require a return workflow; delivery cannot be "rolled back" |

Some actions cannot be fully compensated. Those cases call for forward recovery, manual intervention, or business statuses that clearly represent incomplete processing.

### 11.2. When Is Outbox Alone Enough?

Use Outbox when a single service updates its own database and needs to emit events to a broker. Examples:

- Creating a customer and emitting `CustomerRegistered`.
- Updating an order and emitting `OrderStatusChanged`.
- Recording an inventory adjustment and notifying the warehouse system.

If there is no multi-step workflow requiring coordination or compensation, do not introduce a Saga just to publish an event.

### 11.3. When Is a Saga Needed?

Consider a Saga when:

- A business process spans multiple services or databases.
- Each step can commit independently.
- No suitable distributed transaction is available.
- Failure at a later step requires compensating earlier steps.
- Timeouts, retries, progress tracking, and intermediate business states are needed.

## 12. Orchestration vs. Choreography

Two common Saga implementation styles:

### 12.1. Orchestration

A Saga orchestrator / process manager persists state and decides the next step.

```text
              Saga Orchestrator
                     |
          +----------+----------+
          |          |          |
          v          v          v
      Inventory   Payment    Shipping
      Service     Service    Service
```

The orchestrator sends commands, receives outcomes, updates saga state, and decides whether to advance or compensate.

Advantages:

- Business flow is visible in one place.
- Timeouts, retries, and compensation are easier to coordinate.
- Saga state can be observed centrally.

Disadvantages:

- The orchestrator carries additional responsibility and must operate reliably.
- If over-centralized, workflow changes can make the orchestrator complex.

### 12.2. Choreography

Services react to each other's events without a central orchestrator:

```text
OrderCreated
    |
    v
InventoryReserved
    |
    v
PaymentAuthorized
    |
    v
ShipmentCreated
```

Each service updates its local database and emits the next event via its outbox.

Advantages:

- Less direct coupling between services.
- No central coordinator driving every step.

Disadvantages:

- Overall flow is scattered across multiple consumers.
- Harder to observe overall status when there are many branches.
- Compensation and timeouts can become hard to reason about if event choreography is undocumented.

### 12.3. Which to Choose?

Short workflows with few branches may suit choreography. Workflows with many steps, timeouts, compensation, or progress-visibility requirements are usually easier to manage with orchestration. Both styles can be combined, provided a single source of truth exists for saga state.

## 13. Designing Saga State and Compensation

A saga needs a stable ID, current status, data required to resume after restarts, and step history.

Example tables:

```sql
CREATE TABLE saga_instances (
    saga_id UUID PRIMARY KEY,
    saga_type VARCHAR(100) NOT NULL,
    business_key VARCHAR(120) NOT NULL,
    status VARCHAR(30) NOT NULL,
    current_step VARCHAR(100) NOT NULL,
    state_payload TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ
);

CREATE TABLE saga_step_history (
    id UUID PRIMARY KEY,
    saga_id UUID NOT NULL REFERENCES saga_instances(saga_id),
    step_name VARCHAR(100) NOT NULL,
    action_type VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    command_id UUID,
    result_payload TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Status names might include `STARTED`, `RUNNING`, `COMPENSATING`, `COMPLETED`, `FAILED`, `MANUAL_REVIEW`. Naming conventions must be explicit and state transitions strictly controlled.

### 13.1. State Machine Example

```text
STARTED
   |
   v
RESERVING_INVENTORY
   |
   +---- failure --------------------+
   |                                 |
   v                                 v
AUTHORIZING_PAYMENT             FAILED
   |
   +---- failure --------------------+
   |                                 |
   v                                 v
CREATING_SHIPMENT             COMPENSATING_INVENTORY
   |                                 |
   v                                 v
COMPLETED                       COMPENSATED
```

This is a simplified flow. Real systems may need payment-compensation states, retries, timeouts, and manual review.

### 13.2. Compensating in Reverse Order

If steps completed in order A → B → C and step D fails, compensation typically runs C → B → A. However, exact ordering depends on business dependencies. A compensation step itself can fail and must be independently retryable.

### 13.3. Compensation Must Be Idempotent

If a `ReleaseReservation` command is delivered twice, inventory must not release stock twice and corrupt counts. Use the command ID / saga ID as an idempotency key, check reservation state, and write the inbox record in the same transaction as the inventory mutation.

### 13.4. A Timeout Does Not Mean the Prior Step Failed

A service may have committed while its response or event was delayed or lost. When the orchestrator times out, never assume the operation did not happen. Query status by command ID / idempotency key or issue a compensating command aware of current state.

## 14. Outbox and Inbox in Each Saga Service

Each service participating in a Saga should use a local transaction to:

- Write the business mutation.
- Write an inbox record to deduplicate incoming commands/events.
- Write the next outgoing outbox event/response.

```text
Incoming event/command
          |
          v
       Consumer
          |
          |---- local R2DBC transaction ----------------+
          |                                             |
          |  INSERT inbox message (dedupe)              |
          |  UPDATE local business state                |
          |  INSERT next outbox event                   |
          |                                             |
          +---------------- COMMIT ---------------------+
                                                        |
                                                        v
                                                 Local outbox relay
                                                        |
                                                        v
                                                    Broker
```

Example of Inventory service receiving `ReserveInventory`:

1. Insert inbox key `(inventory, commandId)`.
2. If already present, ignore duplicate.
3. Check and reserve stock within the local database transaction.
4. Write `InventoryReserved` or `InventoryReservationRejected` into the outbox.
5. Commit.
6. Acknowledge command after commit.

If reservation fails due to insufficient stock, that is a valid business outcome rather than a technical error to retry forever. The service emits a rejected event so the orchestrator can decide to cancel or compensate earlier steps.

## 15. Order Placement Saga Example

Suppose the workflow comprises:

1. Order service creates order in `PENDING` state.
2. Inventory service reserves stock.
3. Payment service authorizes payment.
4. Shipping service creates shipment.
5. Order service transitions order to `CONFIRMED`.

### 15.1. Initializing the Saga in Order Service

Inside a single transaction on the order database:

- Insert order `PENDING`.
- Insert saga instance `STARTED`.
- Insert outbox command/event `ReserveInventory`.
- Commit.

The relay publishes the command after commit. If the broker is temporarily unavailable, the outbox retains the command for retry.

### 15.2. Inventory Service Processing

Inside a transaction on the inventory database:

- Deduplicate the command via inbox.
- Reserve quantity if sufficient.
- Write outbox `InventoryReserved` or `InventoryRejected`.
- Commit, then acknowledge the message.

### 15.3. Payment Service Processing

Upon receiving `InventoryReserved`, payment service authorizes payment. If successful, write `PaymentAuthorized`; if failed, write `PaymentRejected`. Payment requests must carry an idempotency key so retries never create duplicate charges or authorizations.

### 15.4. Shipping Service Processing

Once payment is authorized, shipping service creates the shipment. If successful, emit `ShipmentCreated`. If it fails, the Saga initiates compensation.

### 15.5. Compensating When Payment Fails

If inventory was reserved but payment is declined:

1. Orchestrator transitions saga to `COMPENSATING`.
2. Sends `ReleaseInventory` with a stable command ID.
3. Inventory service handles it idempotently and emits `InventoryReleased`.
4. Orchestrator updates the order to `PAYMENT_FAILED` or an appropriate business status.
5. Saga finishes as `COMPENSATED` or `FAILED` per convention.

Orders do not necessarily get deleted. Preserve status and history for auditing, customer support, and reconciliation.

### 15.6. Compensating When Shipping Fails After Payment Capture

If funds were already captured, compensation may involve a refund. A refund is a new transaction and can itself fail or take time. The Saga needs states such as `REFUND_PENDING`/`REFUND_FAILED` along with retries/manual review, rather than assuming payment vanished immediately.

## 16. Retries, Timeouts, and Poison Messages

Not all errors should be retried the same way.

| Error category | Example | Typical action |
|---|---|---|
| Transient | Broker unavailable, network reset | Retry with backoff/jitter |
| Overload | Rate limit, service busy | Retry per `Retry-After` or backoff |
| Business | Insufficient stock, payment declined | Emit business outcome; trigger compensation if needed |
| Data/schema | Incompatible payload, missing required field | Dead-letter, investigate, or upcast |
| Permanent | Invalid credentials, unsupported event type | Alert and manual intervention; do not retry infinitely |
| Unknown outcome | Timeout after downstream may have committed | Query by idempotency key or resend idempotent command |

### 16.1. Bounding Retries

Configure max attempts, max elapsed time, and backoff caps. Infinite retries grow backlogs and repeatedly waste resources on broken events. Too few retries push transient blips into dead-letter state unnecessarily.

### 16.2. Poison Messages

An unparseable payload or one persistently violating schema can cause relays/consumers to fail repeatedly. Log the event ID, version, type, and redacted error; move to dead-letter per retry policy. Maintain a workflow to fix, transform, and replay.

### 16.3. Do Not Retry Business Errors Like Network Errors

For instance, a declined payment is a business outcome; immediately retrying the exact same card details is unlikely to succeed and may trigger unwanted behavior. Emit the failure outcome so the Saga decides the next step.

### 16.4. Retries Must Preserve Idempotency Keys

Every retry of the same logical command must carry the exact same command ID / idempotency key. Generating a new key on each retry makes downstream systems treat it as a new transaction and execute it multiple times.

## 17. Outbox Polling vs. Change Data Capture

There are two common ways for a relay to detect new outbox rows.

### 17.1. Polling Relay

The relay periodically queries pending rows, claims them in batches, and publishes. Advantages:

- Easy to understand and implement using only R2DBC + a broker client.
- Does not require reading database transaction logs.
- Easy to tune batch size, retries, and leases.

Disadvantages:

- Introduces polling latency.
- Continuous queries generate database load.
- Requires managing claims, leases, and multiple workers.
- Outbox table needs appropriate indexes and retention cleanup.

### 17.2. CDC Relay

Change Data Capture reads the database transaction log/binlog/WAL to detect committed outbox rows. A connector forwards changes to the broker.

Advantages:

- Can reduce polling queries against the database.
- Aligns closely with event-driven streams and leverages database logs.
- Can achieve high throughput at large scale.

Disadvantages:

- Requires operating connectors and managing transaction log retention.
- Snapshot, offset, and schema-evolution setups are more complex.
- Depends on specific database and connector versions.
- Requires understanding CDC ordering, duplicate, and recovery semantics.

### 17.3. Choosing by Scale and Operational Capability

Polling fits moderate volumes where you want retry control in code and lack CDC infrastructure. CDC fits when you already run a connector platform, have high throughput, or need low latency. Both still require idempotent consumers because duplicates and replays can happen.

## 18. Common Limitations and Design Pitfalls

### Writing Order and Outbox in Two Separate Transactions

If the order commits first and the outbox insert fails, dual-write risk remains. Both operations must share the same local transaction and `ConnectionFactory`.

### Publishing to the Broker Inside the Database Transaction

The broker is not part of the R2DBC transaction. Publishing successfully before a database rollback emits false events while pinning database connections during network waits.

### Calling subscribe Inside a Service to Save Outbox Rows

A detached publisher may execute outside the transaction. Chain with `flatMap`/`then` and return the publisher to the transaction manager.

### Marking PUBLISHED Before Broker Acknowledgement

The process can crash after updating and before publishing, losing the event. Mark only after acknowledgement per broker semantics.

### Assuming Outbox Delivers Exactly Once

The relay can publish and crash before marking. Design for at-least-once delivery and idempotent consumers.

### Consumer Processing Business Logic First, Then Writing Inbox in Another Transaction

If the process crashes between the two operations, duplicates can re-apply business changes. Inbox and business updates must share the same local transaction.

### Acknowledging Messages Before Consumer Commit

Messages can be lost if the process crashes prior to commit. Acknowledge only after the transaction completes successfully.

### Too-Short Leases or Missing Leases

Another worker can claim a row while the previous worker is still publishing. Choose an appropriate lease duration, renew when needed, and still tolerate duplicates.

### Missing Retention / Cleanup

Unbounded outbox growth slows down indexes and claim queries over time. Implement retention, archiving, and batch cleanup.

### Using Timestamps to Guarantee Ordering

Timestamps do not guarantee per-aggregate sequence order. Use aggregate sequences/versions and partition keys when ordering is an invariant.

### Treating Compensation as a Database Rollback

Compensation is a new business action that can fail and cannot erase external effects. Design retries and manual review.

### Not Handling Timeouts with Unknown Outcomes

Downstream may have committed while the response was lost. Use idempotency keys and status queries instead of issuing new commands.

## 19. Testing Outbox and Saga

Outbox/Saga workflows require integration tests because correctness depends on transactions, databases, brokers, and crash timing.

### 19.1. Testing Atomicity of Outbox Writes

Test both scenarios:

- Order insert and outbox insert succeed: both exist after commit.
- Order insert succeeds while outbox insert fails: neither exists after rollback.

Verify state using an independent transaction. Do not merely assert that the method emits an error.

### 19.2. Testing Relay Retry After Restart

1. Write a pending outbox row.
2. Claim the row.
3. Simulate a broker error.
4. Verify the row returns to pending with a future `next_attempt_at`.
5. Spin up a new relay worker or wait for the lease to expire.
6. Verify the event is published once the broker recovers.

### 19.3. Testing the Post-Publish Crash Window

Simulate the broker accepting an event while the relay has not yet marked it published. When the event is reclaimed, the consumer must handle the duplicate without applying business changes a second time.

### 19.4. Testing Multiple Relay Workers

Run two workers claiming concurrently and verify the same row is never claimed by both while its lease is active. Then verify expired leases can be reclaimed.

### 19.5. Testing Idempotent Consumers

Send the same message ID twice. Verify business state changes only once and the inbox contains only one row for `(consumer_name, message_id)`.

### 19.6. Testing Saga Compensation

Run a workflow where inventory reservation succeeds and payment fails. Verify:

- Saga transitions to compensation.
- `ReleaseInventory` is emitted.
- Inventory returns to the expected state.
- Order carries the appropriate failure business status.
- Redelivering the event does not release stock twice.

### 19.7. Testing Failed Compensation

Simulate the compensating service being temporarily unavailable. The Saga must stay in an incomplete state, retry, or transition to manual review; never mark `COMPENSATED` without confirmation.

### 19.8. Testing Event Schema Evolution

Consumers must handle both the current payload version and older versions still active in the system. Test optional fields, defaults, unknown fields, and upcasting if used.

## 20. Implementation Process in Spring Data R2DBC Applications

1. Define local transaction boundaries and external systems requiring events.
2. If coordinating multiple services/databases, design the state machine and compensation upfront.
3. Create the outbox table in the same database that owns the business data.
4. Create an entity/repository or custom store for the outbox.
5. Ensure business repositories and outbox repositories share the same `ConnectionFactory` and reactive transaction manager.
6. In the service, write business state and outbox events within a single transactional reactive pipeline.
7. Never publish directly to the broker inside the business transaction.
8. Choose polling relay or CDC; define claiming, leases, retries, and retention.
9. Publish with stable event IDs, event type/version, and aggregate sequences if needed.
10. Mark published after broker acknowledgement; tolerate duplicates in crash windows.
11. On consumers, write the inbox/dedup key and update business state in the same local transaction.
12. Acknowledge messages after commit; verify broker integration semantics.
13. For Sagas, persist saga state, step history, timeouts, and compensation progress.
14. Design idempotent compensation and manual recovery for irreversible steps.
15. Monitor backlog, oldest event age, retries, dead events, duplicates, and saga duration.
16. Test atomicity, crash windows, multi-worker claims, duplicate consumers, and compensation failures.

## 21. Quick Checklist

- [ ] Identified dual-write risks between the database and brokers/other services.
- [ ] Business row and outbox row are written in the same local R2DBC transaction.
- [ ] Both repositories share the same `ConnectionFactory` and transaction manager.
- [ ] Events include stable IDs, type, version, aggregate identity, and appropriate payload.
- [ ] Payloads exclude secrets and out-of-contract internal data.
- [ ] Relay reads only committed events.
- [ ] Claims/leases prevent multiple workers from processing the same row during an active lease.
- [ ] Publishing happens outside the business write transaction.
- [ ] Events are marked published only after broker acknowledgement.
- [ ] Retries use backoff, jitter, attempt limits, and a dead-letter policy.
- [ ] Leases expire and can be reclaimed after worker crashes.
- [ ] Consumers write inbox/idempotency keys and business updates in the same transaction.
- [ ] Messages are acknowledged after consumer commit.
- [ ] Per-aggregate ordering is guaranteed if required by business rules.
- [ ] Outbox includes retention, cleanup, and replay workflows.
- [ ] Metrics track pending age, backlog, attempts, and dead events.
- [ ] Saga state and compensation are durably persisted when workflows span multiple services.
- [ ] Compensation is idempotent and handles failures of compensation itself.
- [ ] Timeouts handle cases where downstream committed yet the response was lost.
- [ ] Integration tests cover rollbacks, duplicates, restarts, multiple workers, and compensation.

Transactional Outbox enables a service to record business data and event-emission intent in the same R2DBC transaction, after which a relay delivers events to the broker under at-least-once semantics. Inboxes and idempotent consumers handle duplicates; leases, retries, dead-letter states, and retention enable the relay to recover from failures. When a business workflow spans multiple databases or independent systems, Sagas add a state machine and compensating actions around each local transaction. Together, these two patterns do not create a magical distributed rollback, yet provide an observable, testable, and recoverable way to coordinate when parts of a system fail.
