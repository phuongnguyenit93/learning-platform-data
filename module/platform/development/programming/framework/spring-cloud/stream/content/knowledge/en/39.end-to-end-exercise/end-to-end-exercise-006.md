# Coordinating Database and Events with Transactional Outbox

A Spring Cloud Stream service often has to perform two tasks when handling a business command: updating its database and emitting an event for other systems. For example, the Order Service creates an order and emits `OrderCreated` so Inventory Service reserves stock and Billing Service prepares payment.

If a service writes to the database and sends an event directly, those two operations span two independent systems. The database may commit while the broker fails to receive the event, or the broker may receive the event while the database rolls back. This is the **dual-write** failure. Transactional outbox solves this by recording the business change and an outbox row inside the **same database transaction**. A separate relay reads the outbox and sends events to Kafka, RabbitMQ, or Pulsar via a binder.

This exercise builds an end-to-end flow for the **SPRING_CLOUD_STREAM** module: using Supplier/Function/Consumer, bindings, and binders; keeping events consistent with database state; handling retries, duplicates, per-aggregate ordering, schema versions, observability, and failure testing. The focus is integrating Spring Cloud Stream with database transactions without assuming a single local transaction can span both a database and a broker.

## 1. Dual Writes Create Two Inconsistency Windows

Suppose a service runs:

~~~java
@Transactional
public Order createOrder(CreateOrder command) {
    Order order = orderRepository.save(Order.from(command));
    streamBridge.send("orders-out-0", new OrderCreated(order.getId()));
    return order;
}
~~~

This code looks reasonable, yet the database transaction and broker publish do not automatically form an atomic unit.

| Failure sequence | Outcome |
| --- | --- |
| Database commits, then broker is unavailable | Order exists without an event |
| Broker receives event, then database rolls back | Consumers process a nonexistent order |
| Broker receives event, but response is lost | Producer is unsure whether it sent; retries can create duplicates |
| Process dies after DB commit but before send | Event is never published without a recovery mechanism |
| Process dies after send but before recording outcome | Restart may send the event again |

Do not fix this merely by swapping the order of the two calls. Sending first and then committing the database still leaves a window where the database rolls back after the event already reached the broker.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Order Service
    participant D as Database
    participant B as Message Broker
    C->>A: Create order
    A->>D: INSERT order
    D-->>A: Commit DB
    A->>B: Publish OrderCreated
    B--xA: Broker timeout
    Note over D,B: Order exists but event may not have been published
~~~

Transactional outbox replaces two independent operations with a single database transaction for the data owned by the service.

## 2. The Transactional Outbox Idea

Inside a single database transaction, the service:

1. Saves the business change, such as creating an `Order`.
2. Inserts an outbox row describing the event to publish.
3. Commits both together.

An independent relay reads committed outbox rows, converts them into Spring `Message` objects, and sends them to an output binding via `StreamBridge`. Once delivery is confirmed per binder semantics, the relay marks the row as sent.

~~~mermaid
flowchart TD
    A[HTTP command / use case] --> S[Order Service]
    S --> T[DB transaction]
    T --> O[(orders table)]
    T --> X[(outbox_event table)]
    O --> C{Commit}
    X --> C
    C --> R[Outbox relay]
    R --> M[StreamBridge]
    M --> B[(Kafka / RabbitMQ / Pulsar)]
    B --> K[Downstream Consumer]
    K --> I[(Inbox / dedup table)]
    I --> P[Business side effect]
~~~

If the transaction rolls back, both the `Order` and outbox row roll back. If the transaction commits, the event stays safely in the database for the relay to send later, even if the broker is temporarily unavailable.

**An outbox does not create a distributed transaction between database and broker.** It guarantees that saving business state and recording the intent to emit an event are atomic inside the database, then uses retries to transfer the event to the broker. The relay may produce duplicates, so consumers still require idempotency.

## 3. Transaction Boundaries and Component Responsibilities

| Component | Transaction or lifecycle | Responsibility |
| --- | --- | --- |
| Command service | Local database transaction | Write business row and outbox row together |
| Outbox table | Same database as business data | Store immutable events to be published |
| Relay/CDC connector | Reads committed outbox rows | Forward events to the broker |
| Spring Cloud Stream binder | Connects output binding to broker | Serialization, routing, send, and broker-specific options |
| Consumer | Local database transaction | Deduplicate events and update projection/business data |
| Retention job | Separate transaction/maintenance | Clean up completed events per retention policy |

The command service should never call the broker while holding an open database transaction. A long-running database transaction holds locks longer and still fails to make broker publishing atomic.

Similarly, the relay must not hold database row locks while waiting on broker network I/O. It should claim a batch in a short transaction, commit the claim, publish outside that transaction, and update status in a new transaction.

## 4. Event Contracts Must Stay Stable

Before designing the outbox table, define the event contract. An event should carry enough metadata for consumers to understand its source, order, and version:

| Field | Meaning | Example |
| --- | --- | --- |
| `eventId` | Unique event identifier, preserved across all retries | UUID |
| `aggregateType` | Type of aggregate emitting the event | `Order` |
| `aggregateId` | Aggregate identifier | `order-1024` |
| `aggregateSequence` | Monotonically increasing sequence per aggregate | `17` |
| `eventType` | Event name per contract | `OrderCreated` |
| `schemaVersion` | Payload version | `1` |
| `occurredAt` | Timestamp when the business event occurred | ISO-8601 UTC |
| `payload` | Event data snapshot | `orderId`, `customerId`, `total` |
| `correlationId` | Links to request/workflow | UUID |
| `trace context` | Distributed tracing context if available | `traceparent` |

Example payload:

~~~json
{
  "orderId": "order-1024",
  "customerId": "customer-42",
  "total": 129.50,
  "currency": "USD",
  "aggregateSequence": 17
}
~~~

Events should describe **what happened** (`OrderCreated`, `OrderCancelled`) rather than forcing consumers to query current state to guess what changed. If the relay delivers late after the order changed again, the payload snapshot still reflects the data at the moment the event was created.

Do not include passwords, access tokens, sensitive payment details, or full entity graphs in the payload. Expose only fields consumers are authorized to receive.

## 5. Designing the Outbox Table

A practical PostgreSQL schema:

~~~sql
CREATE TABLE outbox_event (
    id                  UUID PRIMARY KEY,
    aggregate_type      VARCHAR(120) NOT NULL,
    aggregate_id        VARCHAR(200) NOT NULL,
    aggregate_sequence  BIGINT NOT NULL,
    event_type          VARCHAR(200) NOT NULL,
    schema_version      INTEGER NOT NULL,
    payload             JSONB NOT NULL,
    occurred_at         TIMESTAMPTZ NOT NULL,
    status              VARCHAR(16) NOT NULL DEFAULT 'PENDING',
    attempts            INTEGER NOT NULL DEFAULT 0,
    next_attempt_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    lock_token          UUID,
    locked_until        TIMESTAMPTZ,
    published_at        TIMESTAMPTZ,
    last_error          VARCHAR(2000),
    CONSTRAINT ck_outbox_status
        CHECK (status IN ('PENDING', 'IN_FLIGHT', 'RETRY', 'SENT', 'FAILED')),
    CONSTRAINT uq_outbox_aggregate_sequence
        UNIQUE (aggregate_type, aggregate_id, aggregate_sequence)
);

CREATE INDEX ix_outbox_ready
    ON outbox_event (next_attempt_at, occurred_at, id)
    WHERE status IN ('PENDING', 'RETRY');

CREATE INDEX ix_outbox_aggregate_order
    ON outbox_event (aggregate_type, aggregate_id, aggregate_sequence)
    WHERE status <> 'SENT';

CREATE INDEX ix_outbox_expired_lease
    ON outbox_event (locked_until, occurred_at)
    WHERE status = 'IN_FLIGHT';
~~~

Column notes:

- `id` is the event ID and serves as the deduplication key on consumers.
- `aggregate_sequence` helps detect out-of-order events. If one aggregate update emits multiple events, the sequence must still be unique per aggregate; you can combine aggregate version + event index.
- `payload` stores an immutable JSON snapshot. You can use JSON Schema, Avro, or Protobuf instead of JSON depending on your contract.
- `status` describes the relay lifecycle, not the business state of the `Order`.
- `attempts`, `next_attempt_at` support backoff retries.
- `lock_token`, `locked_until` coordinate row claims across multiple relay instances.
- `published_at` is set only after send confirmation per configured binder semantics.
- `last_error` holds truncated diagnostic details stripped of sensitive data.

The unique constraint on `aggregate_sequence` assumes one sequence per event. If one business version can emit multiple events, add `event_index` and enforce a unique key on `(aggregate_type, aggregate_id, aggregate_version, event_index)`.

This table schema targets a **polling relay**. If using Debezium CDC with its default Outbox Event Router structure, the schema and row lifecycle differ; the CDC section below covers that separately.

## 6. Writing Business Data and Outbox in the Same Transaction

Example command service using Spring Boot, Spring Data/JDBC, and a single datasource:

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final OutboxRepository outbox;
    private final ObjectMapper objectMapper;

    public OrderApplicationService(
            OrderRepository orders,
            OutboxRepository outbox,
            ObjectMapper objectMapper) {
        this.orders = orders;
        this.outbox = outbox;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public UUID createOrder(CreateOrder command) {
        Order order = orders.save(Order.create(
                command.customerId(),
                command.total(),
                command.currency()));

        // Domain aggregate allocates a monotonically increasing sequence in the same transaction.
        long aggregateSequence = order.nextEventSequence();
        UUID eventId = UUID.randomUUID();
        OrderCreated event = new OrderCreated(
                eventId,
                order.getId(),
                command.customerId(),
                command.total(),
                command.currency(),
                aggregateSequence,
                Instant.now());

        try {
            String json = objectMapper.writeValueAsString(event);
            outbox.insert(
                    eventId,
                    "Order",
                    order.getId().toString(),
                    aggregateSequence,
                    "OrderCreated",
                    1,
                    json);
        }
        catch (JsonProcessingException ex) {
            throw new IllegalStateException("Cannot serialize OrderCreated", ex);
        }

        return order.getId();
    }
}
~~~

Both `orders.save(...)` and `outbox.insert(...)` must participate in the **same local database transaction**. When the method commits, both persist; if a runtime exception occurs before commit, both roll back.

Example event DTO:

~~~java
public record OrderCreated(
        UUID eventId,
        UUID orderId,
        UUID customerId,
        BigDecimal total,
        String currency,
        long aggregateSequence,
        Instant occurredAt) {
}
~~~

The outbox repository can use JDBC to write `JSONB`:

~~~java
@Repository
public class OutboxRepository {

    private final JdbcTemplate jdbc;

    public OutboxRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(
            UUID eventId,
            String aggregateType,
            String aggregateId,
            long sequence,
            String eventType,
            int schemaVersion,
            String payloadJson) {

        jdbc.update("""
            INSERT INTO outbox_event (
                id, aggregate_type, aggregate_id, aggregate_sequence,
                event_type, schema_version, payload, occurred_at
            )
            VALUES (?, ?, ?, ?, ?, ?, CAST(? AS jsonb), now())
            """,
            eventId, aggregateType, aggregateId, sequence,
            eventType, schemaVersion, payloadJson);
    }
}
~~~

If using JPA and `JdbcTemplate` together, verify both use the same `DataSource` and transaction manager. If they point to separate databases or independent transaction managers, the two inserts are no longer atomic.

### `@Transactional` Rollback Rules

By default, Spring rolls back on `RuntimeException` and `Error`, whereas checked exceptions do not automatically roll back a transaction. The example above wraps serialization failures in `IllegalStateException`. If a method lets checked exceptions escape, declare `rollbackFor` appropriately.

Never swallow an exception from `outbox.insert` and return success. When writing to the outbox fails, the business transaction must fail under the same policy.

## 7. Never Send to the Broker Directly Inside the Command Transaction

The following is not a transactional outbox:

~~~java
@Transactional
public UUID createOrder(CreateOrder command) {
    Order order = orders.save(Order.create(command));
    streamBridge.send("orders-out-0", new OrderCreated(...));
    return order.getId();
}
~~~

Even though the `send` call sits inside a `@Transactional` method, the database transaction manager does not automatically enlist Kafka/RabbitMQ/Pulsar producers. The broker can receive the event before the database commits. If the DB rolls back, consumers already received an invalid event.

Also avoid relying solely on `@TransactionalEventListener(phase = AFTER_COMMIT)` to publish events without an outbox. If the process crashes after the database commits but before the listener publishes, the event is lost. You can use an after-commit callback to **wake up the relay**, while the outbox row itself must be persisted inside the original transaction.

## 8. Relay Flow: Claim, Publish, Mark Sent

The relay consists of three distinct steps:

1. **Claim:** claim a batch of `PENDING`/`RETRY` rows in a short database transaction, assigning a lock token and lease.
2. **Publish:** send messages via `StreamBridge` outside any database transaction.
3. **Mark sent:** after broker confirmation succeeds, update status to `SENT` in a separate database transaction.

~~~mermaid
sequenceDiagram
    participant R as Outbox Relay
    participant D as Database
    participant S as StreamBridge
    participant B as Broker
    R->>D: Claim batch + lock token
    D-->>R: Claimed rows
    Note over R,D: Claim transaction committed
    R->>S: send(output binding, event)
    S->>B: Publish
    B-->>S: Broker acknowledgement
    S-->>R: Send success
    R->>D: UPDATE status = SENT
    D-->>R: Commit status
~~~

**Never hold a database transaction or row lock during network publishing.** If the relay waits seconds on the broker while holding locks, database transactions stay open too long and block other workers.

### Why Are Lock Tokens and Leases Needed?

Multiple relay instances may run concurrently. Row claiming must ensure two instances do not process the same row under normal conditions. Leases allow another worker to reclaim a row if a process dies.

Lock tokens prevent a stale worker from overwriting status after its lease expired and another worker reclaimed the row.

## 9. Claiming Batches with PostgreSQL `SKIP LOCKED`

Example SQL:

~~~sql
WITH candidates AS (
    SELECT e.id
    FROM outbox_event e
    WHERE (
          e.status IN ('PENDING', 'RETRY')
          OR (e.status = 'IN_FLIGHT' AND e.locked_until < now())
      )
      AND e.next_attempt_at <= now()
      AND (e.locked_until IS NULL OR e.locked_until < now())
      AND NOT EXISTS (
          SELECT 1
          FROM outbox_event earlier
          WHERE earlier.aggregate_type = e.aggregate_type
            AND earlier.aggregate_id = e.aggregate_id
            AND earlier.aggregate_sequence < e.aggregate_sequence
            AND earlier.status <> 'SENT'
      )
    ORDER BY e.occurred_at, e.id
    LIMIT :batch_size
    FOR UPDATE SKIP LOCKED
)
UPDATE outbox_event e
SET status = 'IN_FLIGHT',
    lock_token = :lock_token,
    locked_until = now() + (:lease_seconds * interval '1 second'),
    attempts = attempts + 1
FROM candidates c
WHERE e.id = c.id
RETURNING e.*;
~~~

Explanation:

- `FOR UPDATE SKIP LOCKED` lets multiple relays claim from a queue-like table without blocking on rows locked by other workers.
- `LIMIT` bounds the batch so claim transactions stay fast.
- `lock_token` uniquely identifies this claim attempt.
- `locked_until` sets when the lease expires.
- The claim condition includes expired `IN_FLIGHT` rows; omitting this branch would leave rows stranded in `IN_FLIGHT` if a process dies mid-publish.
- `NOT EXISTS` prevents claiming a newer event for the same aggregate while an earlier one is not yet `SENT`.

PostgreSQL documents `SKIP LOCKED` as suitable for multiple consumers reading queue-like tables, while noting that query results present an inconsistent view and should not be used for general business queries.

The ordering predicate in this example causes a `FAILED` event on an aggregate to block subsequent events on that aggregate. This is the safe default when strict business order is required. If business policy allows skipping a manually resolved event, define an audited `SKIPPED` state and explicit query predicate rather than treating `FAILED` as `SENT`.

## 10. Claim Repository and Short Transactions

Example repository using `NamedParameterJdbcTemplate` since the claim SQL uses named parameters:

~~~java
@Repository
public class OutboxClaimRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public OutboxClaimRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public List<ClaimedOutboxEvent> claim(
            int batchSize,
            int leaseSeconds,
            UUID lockToken) {

        MapSqlParameterSource parameters = new MapSqlParameterSource()
                .addValue("batch_size", batchSize)
                .addValue("lease_seconds", leaseSeconds)
                .addValue("lock_token", lockToken);

        return jdbc.query(CLAIM_SQL, parameters,
                (rs, rowNum) -> new ClaimedOutboxEvent(
                        rs.getObject("id", UUID.class),
                        rs.getString("aggregate_type"),
                        rs.getString("aggregate_id"),
                        rs.getLong("aggregate_sequence"),
                        rs.getString("event_type"),
                        rs.getInt("schema_version"),
                        rs.getString("payload"),
                        rs.getTimestamp("occurred_at").toInstant(),
                        lockToken));
    }
}
~~~

This is an illustrative skeleton. In real implementations, populate `CLAIM_SQL` with the SQL above, use a mapper handling `JSONB`, and verify `RETURNING` column names. The claim method must be invoked through the Spring bean proxy so the transaction commits upon method return.

If a relay claims a large batch but publishes slowly, the lease may expire before the worker finishes. Choose small batches, set leases longer than expected publish durations, and consider lease renewal for in-flight work. Never pick an arbitrarily short lease.

## 11. Configuring the Output Binding for `StreamBridge`

The relay is an event source outside a function input, so it can use `StreamBridge` to send to an output binding.

Explicit binding declaration:

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: orderEvents-out-0
      bindings:
        orderEvents-out-0:
          destination: orders.events
          content-type: application/json
~~~

`output-bindings` provisions the binding at application startup. Without it, `StreamBridge` creates the binding dynamically on the first `send`; for production relays, explicit declarations surface destination or configuration errors earlier.

Example message construction:

~~~java
EventEnvelope envelope = new EventEnvelope(
        row.id(),
        row.aggregateType(),
        row.aggregateId(),
        row.aggregateSequence(),
        row.eventType(),
        row.schemaVersion(),
        row.occurredAt(),
        objectMapper.readTree(row.payload()));

Message<EventEnvelope> message = MessageBuilder
        .withPayload(envelope)
        .setHeader("eventId", row.id().toString())
        .setHeader("aggregateId", row.aggregateId())
        .setHeader("eventType", row.eventType())
        .setHeader("schemaVersion", row.schemaVersion())
        .build();

boolean accepted = streamBridge.send("orderEvents-out-0", message);
if (!accepted) {
    throw new IllegalStateException("Output binding rejected the event");
}
~~~

Envelope DTO:

~~~java
public record EventEnvelope(
        UUID eventId,
        String aggregateType,
        String aggregateId,
        long aggregateSequence,
        String eventType,
        int schemaVersion,
        Instant occurredAt,
        JsonNode payload) {
}
~~~

`StreamBridge` uses Spring Integration's send mechanism. Per current Spring Cloud Stream documentation, `send` runs on the calling thread by default; async sending can be enabled via `setAsync(true)`. For an outbox relay, prefer a send path with clear confirmation semantics so rows are marked `SENT` only after broker acknowledgment.

## 12. Distinguishing `StreamBridge` Send Results from Broker Acknowledgement

This is the single most critical point in a polling relay.

- The boolean returned by `StreamBridge.send(...)` indicates whether the binding/channel accepted the send attempt.
- That is not always equivalent to the broker confirming durable persistence.
- The Kafka binder producer has a `sync` property, defaulting to `false`. When the relay needs to wait for send results, configure synchronous publishing and an appropriate timeout.
- With RabbitMQ or Pulsar, verify the publisher confirm or send-completion mechanism for your binder and version.

Example Kafka output configuration:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          orderEvents-out-0:
            producer:
              sync: true
              message-key-expression: headers['aggregateId']
              configuration:
                acks: all
~~~

`sync: true` instructs the Kafka binder to publish synchronously; `sendTimeoutExpression` can specify per-message acknowledgment timeouts if needed. `acks: all` requires broker acknowledgment per the configured replication policy. Replication factor, `min.insync.replicas`, and ISR must still be properly configured.

Do not enable `StreamBridge.setAsync(true)` in the relay and immediately mark `SENT` based solely on the returned boolean. If sending asynchronously, use the binder's confirmation callback mechanism to update status only after completion; if the callback fails or never arrives, keep the row eligible for retry.

When using multiple binders, select the right binder for the output binding via the corresponding `StreamBridge` overload or explicit binding configuration. Never assume a binding name picks the right cluster when multiple binders are present.

## 13. Kafka Key and Per-Aggregate Ordering

To send events of the same order to the same Kafka partition, use the aggregate ID as the message key. Example:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          orderEvents-out-0:
            producer:
              message-key-expression: headers['aggregateId']
~~~

When `aggregateId` is stable, events for the same order consistently route to the same partition under the partitioner. Kafka guarantees ordering only within a single partition; it does not guarantee global order across partitions.

The relay must also avoid sending sequence 18 before sequence 17 for the same aggregate. Using `SKIP LOCKED` alone without an aggregate ordering guard could let worker A claim sequence 17 while worker B claims sequence 18 and publishes it first.

Changing the topic's partition count can alter key-to-partition mapping. If strict historical ordering is required, plan partition migration and consumer cutover carefully.

## 14. Publishing and Marking `SENT` in Two Separate Transactions

After publishing is confirmed, update the row:

~~~sql
UPDATE outbox_event
SET status = 'SENT',
    published_at = now(),
    lock_token = NULL,
    locked_until = NULL,
    last_error = NULL
WHERE id = :event_id
  AND status = 'IN_FLIGHT'
  AND lock_token = :lock_token;
~~~

Check the affected row count. If it is `0`, the lease may have expired and another worker reclaimed the event. The stale worker must not overwrite the newer state.

**Never mark `SENT` before publishing.** If the database commits `SENT` and the process dies before the broker receives the event, the event is lost from the relay.

Conversely, a duplicate window still exists:

1. The broker receives and confirms the event.
2. The relay process dies before committing `SENT`.
3. The lease expires.
4. Another relay republishes the event.

This is **at-least-once** behavior. You cannot eliminate this window using two independent database and broker transactions alone. Consumers must be idempotent.

## 15. Scheduling Retries and Handling Publish Errors

When the broker experiences transient errors or send timeouts, retain the row for retry. Example status update:

~~~sql
UPDATE outbox_event
SET status = CASE
        WHEN attempts >= :max_attempts THEN 'FAILED'
        ELSE 'RETRY'
    END,
    next_attempt_at = :next_attempt_at,
    lock_token = NULL,
    locked_until = NULL,
    last_error = :sanitized_error
WHERE id = :event_id
  AND status = 'IN_FLIGHT'
  AND lock_token = :lock_token;
~~~

A retry policy should include:

- Exponential backoff.
- Jitter so multiple relay instances do not retry in lockstep.
- Max attempts or max age limits per SLA.
- Broker send timeouts.
- Alerts when rows transition to `FAILED` or backlog grows persistently.
- Operator tooling to replay after fixing root causes.

Avoid tight retry loops while the broker is unavailable; that can exhaust connections, CPU, and database capacity. Never store full stack traces or sensitive payloads in `last_error`; store sanitized exception class, error code, and safe diagnostics.

An event that cannot serialize due to a broken schema will rarely heal on its own. Transition the row to `FAILED`, raise an alert, and fix the schema/mapper or resolve manually. Never delete failed events just to make dashboards look clean.

## 16. Complete Relay Skeleton

The following example illustrates transaction boundaries. Claim/mark/retry repository methods must reside in separate `@Transactional` beans to avoid self-invocation bypassing transaction proxies.

~~~java
@Component
public class OutboxRelay {

    private final OutboxClaimRepository claims;
    private final OutboxStateRepository state;
    private final StreamBridge streamBridge;
    private final ObjectMapper objectMapper;

    public OutboxRelay(
            OutboxClaimRepository claims,
            OutboxStateRepository state,
            StreamBridge streamBridge,
            ObjectMapper objectMapper) {
        this.claims = claims;
        this.state = state;
        this.streamBridge = streamBridge;
        this.objectMapper = objectMapper;
    }

    @Scheduled(fixedDelayString = "\${outbox.relay.delay:500}")
    public void publishBatch() {
        UUID token = UUID.randomUUID();
        List<ClaimedOutboxEvent> batch =
                claims.claim(50, 60, token);

        for (ClaimedOutboxEvent row : batch) {
            publishOne(row);
        }
    }

    private void publishOne(ClaimedOutboxEvent row) {
        try {
            EventEnvelope envelope = new EventEnvelope(
                    row.id(),
                    row.aggregateType(),
                    row.aggregateId(),
                    row.aggregateSequence(),
                    row.eventType(),
                    row.schemaVersion(),
                    row.occurredAt(),
                    objectMapper.readTree(row.payload()));

            Message<EventEnvelope> message = MessageBuilder
                    .withPayload(envelope)
                    .setHeader("eventId", row.id().toString())
                    .setHeader("aggregateId", row.aggregateId())
                    .setHeader("eventType", row.eventType())
                    .setHeader("schemaVersion", row.schemaVersion())
                    .build();

            boolean accepted = streamBridge.send(
                    "orderEvents-out-0", message);

            if (!accepted) {
                throw new IllegalStateException(
                        "StreamBridge rejected the output message");
            }

            // Call only after the binder has provided send confirmation
            // under configured semantics (Kafka sync=true in this example).
            state.markSent(row.id(), row.lockToken());
        }
        catch (Exception ex) {
            state.scheduleRetry(
                    row.id(),
                    row.lockToken(),
                    sanitize(ex));
        }
    }

    private String sanitize(Exception ex) {
        return ex.getClass().getSimpleName() + ": "
                + safeMessage(ex.getMessage());
    }

    private String safeMessage(String value) {
        if (value == null) {
            return "no details";
        }
        return value.length() <= 500
                ? value
                : value.substring(0, 500);
    }
}
~~~

This is an application skeleton. In production:

- Ensure Kafka producer `sync: true` or the binder's equivalent send confirmation.
- Never call `state.markSent` when only channel acceptance is known and broker ack is still pending.
- Handle `InterruptedException` and graceful shutdown properly if the relay uses blocking APIs.
- If a publish outcome is uncertain due to timeout, schedule retry and tolerate duplicates; never assume the broker did not receive it.
- Generate a fresh lease token per batch/claim and update only while the token still matches.
- Add metrics and bound concurrency and batch size.
- For events of the same aggregate, ensure claim queries and dispatch never let a later event jump ahead of an earlier one.

## 17. Why Not Wrap `send` in One Big Transaction?

An apparently simpler option is:

~~~java
@Transactional
public void createAndPublish(...) {
    saveOrder();
    saveOutbox();
    streamBridge.send(...);
}
~~~

This still does not unify the database and broker into a single resource manager. Without XA or a distributed transaction coordinator spanning both, one side can still commit while the other rolls back or times out.

A Kafka transactional producer can atomically commit multiple Kafka records and consumer offsets within a Kafka transaction; it does not automatically enlist a JDBC/JPA database transaction. Transactional outbox avoids holding database transactions open while waiting on the broker and makes eventual delivery explicit.

Some systems synchronize Kafka and database transactions via transaction synchronization or XA under specialized constraints, but that adds significant complexity and does not replace an outbox for crash recovery. Base your architecture on failure models, not on whether a method carries `@Transactional`.

## 18. Consumer Inbox: Preventing Duplicate Processing

The outbox relay can emit duplicates after a crash. Consumers must record processed event IDs within the same transaction as consumer side effects.

Inbox schema:

~~~sql
CREATE TABLE inbox_event (
    consumer_name VARCHAR(120) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Consumer service:

~~~java
@Service
public class OrderProjectionService {

    private final JdbcTemplate jdbc;

    public OrderProjectionService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void apply(EventEnvelope event) {
        int inserted = jdbc.update("""
            INSERT INTO inbox_event (consumer_name, event_id)
            VALUES (?, ?)
            ON CONFLICT DO NOTHING
            """,
            "order-projection",
            event.eventId());

        if (inserted == 0) {
            // Event was already committed in a previous execution.
            return;
        }

        updateProjection(event);
    }

    private void updateProjection(EventEnvelope event) {
        // Update projection/business data inside the same DB transaction.
    }
}
~~~

If the event is a duplicate, `insert` returns `0` and the consumer skips side effects. If `updateProjection` throws, the transaction rolls back both the inbox insert and business update so redelivery can retry cleanly.

Example consumer function:

~~~java
@Bean
public Consumer<EventEnvelope> projectOrder(
        OrderProjectionService service) {
    return service::apply;
}
~~~

Ensure the transactional method sits on a separate bean invoked through a Spring proxy. Never call a private `@Transactional` method or self-invoke assuming the proxy will start a transaction.

The inbox prevents duplicates only within **the same `consumer_name` and database**. If a consumer triggers side effects in an external system outside that database, add an idempotency key or another outbox for that downstream side effect.

## 19. Offset Commits and Consumer Database Transactions

A common Kafka consumer scenario:

1. Consumer receives event E1.
2. Consumer DB transaction inserts into inbox and updates projection.
3. Database commits.
4. Process dies before Kafka offsets are committed.
5. Kafka redelivers E1.
6. The inbox unique key detects E1 was already processed; the consumer skips repeating side effects.
7. Kafka offsets advance once the new handling completes.

This is the **at-least-once delivery + idempotent consumer** pattern. Never claim end-to-end exactly-once merely because Kafka EOS is enabled or a transactional outbox is used. The database and broker still represent two separate transaction boundaries.

If a consumer commits offsets before the database commits, a crash can lose side effects. Configure acknowledgment/transaction modes so offsets are acknowledged only after the service transaction succeeds. Exact settings depend on the binder and listener container.

## 20. Per-Aggregate Event Ordering

Suppose an `Order` emits:

~~~text
OrderCreated(sequence=1)
OrderPaid(sequence=2)
OrderShipped(sequence=3)
~~~

If a multi-worker relay lacks ordering rules, worker A might hold event 1 while worker B sends event 2. A consumer receiving sequence 2 before sequence 1 can enter an invalid state.

Coordinated layers required:

1. Command service allocates monotonically increasing aggregate sequences inside the transaction updating the aggregate.
2. Outbox stores the sequence and event ID.
3. Relay claims only the earliest un-`SENT` event per aggregate when strict ordering is needed.
4. Message key is the aggregate ID so events for the same aggregate hit the same partition (Kafka) or equivalent routing/ordering key.
5. Consumer validates sequences, detects gaps or duplicates, and applies wait/reconcile policies.

There is no global order across all aggregates. Usually ordering is only required per `Order`, `Account`, or `Customer`.

### What If an Earlier Event Becomes `FAILED`?

If sequence 8 is `FAILED` while sequence 9 is published, consumers see a missing transition. There are two options:

- **Strict order:** hold sequence 9 pending until sequence 8 recovers or an operator explicitly marks it skipped.
- **Relaxed order:** allow sequence 9 to proceed, while consumers tolerate out-of-order arrivals and reconcile state.

Never let this behavior emerge accidentally from the claim query.

## 21. Retries, Backoff, and the `FAILED` State

A simple relay state machine:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> IN_FLIGHT: claim
    RETRY --> IN_FLIGHT: retry due
    IN_FLIGHT --> SENT: broker ack + DB update
    IN_FLIGHT --> RETRY: transient error
    IN_FLIGHT --> FAILED: retries exhausted / permanent error
    FAILED --> PENDING: operator replay after fix
    SENT --> [*]
~~~

| State | Meaning |
| --- | --- |
| `PENDING` | Event committed, awaiting relay |
| `IN_FLIGHT` | Claimed by a worker with an active lease |
| `RETRY` | Send failed, waiting until `next_attempt_at` |
| `SENT` | Binder confirmed send per config and DB recorded completion |
| `FAILED` | Requires intervention or quarantine policy |

Example retry delay:

~~~text
delay = min(baseDelay * 2^attempt, maxDelay) + randomJitter
~~~

Retry limits must match SLAs. Broker outages can last a while; failing every row after a couple of short attempts creates massive manual recovery backlogs. Conversely, infinite retries without alerts leave schema-broken events stuck silently.

When replaying `FAILED` rows, preserve the original event ID and payload if the event itself is valid. If the payload must be fixed, emit a new correction/event with a fresh event ID and audit the relationship to the old event; never silently mutate an already-emitted event's content.

## 22. Dead-Letter Queues vs. Outbox `FAILED`

Distinguish two failure locations:

- **Outbox relay cannot send to broker:** the event remains in the database outbox. If the broker is down, a DLT on that same broker may also be unreachable. Keep the row in `RETRY`/`FAILED` and alert.
- **Consumer received the event but cannot process it:** the binder/container can route the record to a Kafka DLT, RabbitMQ dead-letter exchange, or Pulsar dead-letter topic per consumer configuration.

Outbox `FAILED` is a database orchestration state; a DLT is a message broker destination. Do not use the two terms interchangeably.

If an independent quarantine broker exists, failed events can be published there once verified. Even quarantine publishing shares similar duplicate/ack windows and must preserve event ID, source status, and failure reason.

## 23. Outbox Cleanup and Retention

The outbox table grows continuously. Cleanup is necessary, while retaining rows long enough for investigation and replay:

- Only delete or archive `SENT` rows after the agreed retention window.
- Never delete `PENDING`, `IN_FLIGHT`, `RETRY`, or `FAILED` rows.
- Use batched deletes by ID/timestamp to avoid huge transactions.
- Index columns supporting both claims and cleanup.
- Monitor disk growth, autovacuum/bloat (PostgreSQL), backup/restore, and partition pruning at high volume.
- Retain minimal audit trails if compliance requires historical records.

Example batched cleanup:

~~~sql
DELETE FROM outbox_event
WHERE id IN (
    SELECT id
    FROM outbox_event
    WHERE status = 'SENT'
      AND published_at < now() - interval '14 days'
    ORDER BY published_at
    LIMIT 1000
);
~~~

Run in bounded iterations rather than deleting the whole table in one transaction. If events must be retained long-term for replay, archive to appropriate storage or use time-partitioned tables.

## 24. CDC Alternative: Debezium Outbox Event Router

A polling relay is not the only option. With Change Data Capture (CDC), the database writes outbox rows inside transactions, and a connector reads the transaction log/WAL/binlog and streams committed changes to Kafka. Debezium provides an **Outbox Event Router SMT** to transform outbox change records into event messages.

Debezium Outbox Event Router's default layout typically uses:

| Column | Meaning |
| --- | --- |
| `id` | Event ID; placed into message headers for consumer deduplication |
| `aggregatetype` | Topic routing value, e.g., `Order` |
| `aggregateid` | Message key, preserving per-aggregate order inside Kafka partitions |
| `type` | Event type |
| `payload` | JSON or serialized representation of the event |

~~~mermaid
flowchart LR
    A[Order Service] --> T[DB transaction]
    T --> O[(outbox_event INSERT)]
    O --> W[(WAL / binlog)]
    W --> D[Debezium connector]
    D --> SMT[Outbox Event Router SMT]
    SMT --> K[(Kafka topic)]
    K --> C[Spring Cloud Stream consumer]
~~~

Basic SMT configuration in Kafka Connect:

~~~properties
transforms=outbox
transforms.outbox.type=io.debezium.transforms.outbox.EventRouter
~~~

By default, `aggregatetype` determines the topic name, `aggregateid` becomes the Kafka key, `id` becomes a header, and `payload` becomes the message value. You can customize routing fields, topic replacement, event ID/key/payload fields, and placement of additional fields.

### Schema and Lifecycle Differences vs. Polling

Debezium's Outbox Event Router expects outbox rows primarily to be **INSERTed**. Some SMT configurations warn or fail on `UPDATE`; `DELETE` is filtered out by default. Therefore, do not reuse a polling table filled with status/lock updates for CDC without carefully checking SMT settings.

CDC does not require a relay updating `published_at` per row; connector offsets and transaction log positions track capture progress. However, the connector, replication slots, WAL retention, snapshots, schema history, Kafka Connect workers, and monitoring all become critical operational components.

Never delete outbox rows before the connector has captured them; size retention to cover connector outages and snapshot/recovery windows.

## 25. Choosing Polling Relay or CDC?

| Criterion | Polling relay | CDC/Debezium |
| --- | --- | --- |
| Operational components | Application relay + database | Connector, Kafka Connect, database log capture |
| Latency | Tied to poll/batch interval | Near real-time via log capture |
| Database load | Poll/index/update/delete queries | Transaction log reading; requires WAL/binlog config |
| State tracking | Status/leases inside outbox table | Connector offsets and log positions |
| Retry logic | Controlled directly by application | Connector retry/restart and downstream policies |
| Target broker | Can use `StreamBridge` for Kafka/RabbitMQ/Pulsar via binders | Outbox Event Router primarily targets Kafka Connect/Kafka |
| Ordering | Relay must explicitly claim per aggregate | Aggregate ID key routes to same Kafka partition; still verify connector/order config |
| Complexity | Easy to start; must manage leases and duplicates | More infrastructure; suits high throughput and existing CDC platforms |

Choose polling for moderate workloads, simpler deployments, or non-Kafka binders. Choose CDC when your organization already operates Kafka Connect/Debezium, needs high capture throughput, and accepts managing connectors and transaction logs.

Both solve database-side dual writes, yet they carry different failure modes, retention constraints, and operational ownership.

## 26. Integrating Spring Cloud Stream with RabbitMQ and Pulsar

Transactional outbox is not Kafka-specific. The outbox table and business transaction stay identical; the relay can use `StreamBridge` to target the appropriate binder.

However, confirmation and ordering semantics differ:

| Binder | Details to verify |
| --- | --- |
| Kafka | Producer `sync`/`acks`, message keys, partitions, consumer groups, `read_committed` if using Kafka transactions |
| RabbitMQ | Publisher confirms, exchange/queue durability, routing, delivery mode, mandatory returns, dead-letter exchanges |
| Pulsar | Send completion/acks, topic partitions, message keys, subscription types, schemas, and redelivery policies |

Never treat `StreamBridge.send() == true` as universal proof that every broker has durably persisted the message. Verify the confirmation mechanism of your specific binder and mark `SENT` only once sufficiently strong confirmation is received.

If an application configures multiple binders, select the intended binder for the output binding explicitly; avoid accidentally routing events to another default cluster. Preserve the same event ID and aggregate key across binders.

## 27. Schema Evolution and Event Versioning

Outbox rows can outlive an application version in the database. A newer relay may read events produced by an older version, and consumers may lag behind producers.

Requirements:

- Stable `eventType` and explicit `schemaVersion`.
- Payload snapshots must not rely on lazy-loaded JPA entities when the relay runs.
- Compatibility rules for adding, removing, or changing fields.
- Mappers/serializers able to read older versions during retention windows.
- Clear skip/quarantine policies for unknown event types on consumers rather than arbitrary deserialization.
- Compatibility tests pairing newer producers with older consumers and vice versa.

Never store Java class names and use arbitrary reflection to instantiate objects when the relay publishes events. Use an explicit `eventType` allow-list mapped to known schemas/DTOs.

## 28. Trace Context and Correlation

An event written in a transaction and published later may execute on a different thread at a different time. Persist essential correlation metadata in the outbox:

- `eventId`;
- `aggregateId`;
- `correlationId`;
- `causationId` if applicable;
- `occurredAt`;
- Authorized trace context for storage and propagation.

Never store full HTTP request headers or authentication tokens in the outbox. Trace context is observability metadata, not an authentication mechanism.

When the relay sends via `StreamBridge`, construct message headers from persisted fields and let Micrometer/Spring observability instrumentation handle propagation. If enabling async sends, configure context propagation per Spring Cloud Stream documentation.

## 29. Security and Access Control

The outbox stores business data that may be sensitive. Enforce:

- Role-based access so only the command service and relay can read/write the outbox table.
- Consumers must never query the source database directly just to fetch payloads.
- Encrypt sensitive data per database/storage policies.
- Never log full payloads or secrets to logs or metrics.
- Restrict dynamic destinations; never derive topic names directly from user input.
- Assign separate broker ACLs to relay producers and consumers.
- Secure Actuator, metrics, and connection credentials.
- Enforce retention/purging per legal and business requirements.
- Audit all replay and `FAILED` resolution actions.

Events are shared data contracts across services; include only fields downstream needs and is authorized to process.

## 30. Observability: Knowing Whether the Outbox Is Backed Up

Useful metrics:

| Metric | Purpose |
| --- | --- |
| `outbox_pending_count` | Number of waiting events |
| `outbox_oldest_pending_age` | Age of the oldest unsent event |
| `outbox_in_flight_count` | Rows currently claimed by relays |
| `outbox_retry_count` | Total retries over time |
| `outbox_failed_count` | Events requiring intervention |
| `outbox_publish_latency` | Time from claim to broker confirmation |
| `outbox_publish_success_total` | Confirmed published events |
| `outbox_publish_error_total` | Failed send attempts |
| `outbox_lease_expired_total` | Expired leases |
| `consumer_duplicate_total` | Events skipped by inbox as duplicates |
| `consumer_processing_lag` | Event lag from `occurredAt` to `processedAt` |

Structured logs should include `eventId`, `aggregateId`, `eventType`, `sequence`, `destination`, `attempt`, relay instance, send result, and error class. Never use `eventId` as a metric tag due to high cardinality.

Alerts should focus on pending age, `FAILED` counts, retry rates, and stalled relay progress. A large pending count created moments ago can be normal; **oldest pending age** is usually far more informative than raw row count alone.

## 31. Testing Business Data and Outbox Transactions

The primary test must prove both inserts commit and roll back together.

Example scenarios:

| Scenario | Order row | Outbox row |
| --- | --- | --- |
| Command succeeds | Present | Present |
| Validation fails before save | Absent | Absent |
| Order insert succeeds, outbox insert fails | Rolled back | Rolled back |
| Transaction marked rollback-only | Not committed | Not committed |
| Process crashes after DB commit | Present | Present; relay can publish after restart |

Use integration tests against a real database via Testcontainers when relying on `JSONB`, `SKIP LOCKED`, partial indexes, or PostgreSQL-specific SQL. H2 may not accurately reproduce required semantics.

Tests can intentionally throw an exception after the outbox insert and verify both tables remain empty.

## 32. Testing the Relay and Duplicate Windows

| Scenario | Expectation |
| --- | --- |
| Broker unavailable before send | Row stays `RETRY`/`PENDING`, never `SENT` |
| `StreamBridge` rejects message | Not `SENT`; retry/error recorded |
| Kafka sync send receives ack | Only then does row become `SENT` |
| Broker acks, process dies before DB update | Event may be resent; consumer deduplicates |
| Lease expires and another worker claims | Stale token cannot mark `SENT` |
| Two workers claim batches concurrently | Do not claim the same row under normal operation |
| Earlier event of same aggregate is `IN_FLIGHT` | Later event does not jump ahead under strict order |
| Retries exhausted | `FAILED` + alert; row retained |
| Operator replay | Event ID preserved, audited, and duplicates guarded |

Never write tests that merely assert `StreamBridge.send()` returned `true` and assume the broker persisted the event. For Kafka, configure `sync` and test against a real broker to verify send completion/ack; for RabbitMQ/Pulsar, use each binder's corresponding confirmation checks.

## 33. Testing Inbox and Idempotency

Test the consumer with the same event twice:

1. First delivery: inbox insert succeeds, business projection updates.
2. Second delivery: unique constraint blocks insert, consumer skips.
3. Both deliveries combined produce only one side effect.
4. If the first business update fails, the transaction rolls back the inbox insert.
5. On redelivery, the consumer processes successfully.

Beyond sequential duplicates, test duplicates across restarts, concurrent deliveries from two threads, and DLT replays. The database unique constraint is the final synchronization barrier; an in-memory `if (cache.contains(eventId))` check is insufficient.

## 34. End-to-End Exercise

### Step 1: Create the Database Schema

- Create the `orders` table.
- Create `outbox_event` with event ID, aggregate sequence, payload, and relay state.
- Create `inbox_event` in the consumer's database.
- Add indexes for claims, cleanup, and unique constraints.

### Step 2: Implement the Command Service

- Create the `Order` inside a `@Transactional` method.
- Build the `OrderCreated` snapshot.
- Insert the outbox row using the same datasource and transaction manager.
- Do not invoke `StreamBridge` inside this method.
- Test rollback when outbox insertion fails.

### Step 3: Create the Output Binding

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: orderEvents-out-0
      bindings:
        orderEvents-out-0:
          destination: orders.events
          content-type: application/json
      kafka:
        bindings:
          orderEvents-out-0:
            producer:
              sync: true
              message-key-expression: headers['aggregateId']
              configuration:
                acks: all
~~~

This is an illustrative Kafka configuration. For RabbitMQ or Pulsar, swap in the appropriate producer confirmation and key/routing configuration per binder.

### Step 4: Implement the Relay

- Scheduled poll invokes the claim repository.
- Claim a batch using `SKIP LOCKED` and a lock token.
- Commit the claim transaction before sending.
- Send the envelope via `StreamBridge`.
- Mark `SENT` only after broker confirmation.
- On error, schedule retry with backoff.
- Monitor `FAILED` rows and lease expirations.

### Step 5: Implement the Consumer

~~~java
@Bean
public Consumer<EventEnvelope> consumeOrderCreated(
        OrderProjectionService service) {
    return service::apply;
}
~~~

`OrderProjectionService.apply` opens a database transaction, inserts into `inbox_event` first, and then updates the projection. Use `eventId` as the unique deduplication key.

### Step 6: Run Broker and Database Integration Tests

- Create an order; verify both order and outbox commit together.
- Stop the broker before the relay runs; verify the row stays pending/retry.
- Restart the broker; verify the relay publishes the event.
- Kill the relay after broker ack but before marking `SENT`; verify the consumer deduplicates the redelivery.
- Inject sequence 2 before sequence 1 in a simulated test; verify the consumer detects the gap or the relay preserves order.
- Send a payload with an unsupported schema version; verify the quarantine/`FAILED` policy.

### Step 7: Run Multiple Relay Instances

- Start at least two relays.
- Claim batches concurrently.
- Verify lock tokens and leases prevent two workers from handling the same row normally.
- Simulate a dead worker so its lease expires.
- Verify another worker reclaims the row and the old worker cannot update state with the stale token.

## 35. Production Operations Checklist

- Business row and outbox row share the same database transaction.
- Event payload is an immutable snapshot carrying `eventId`, `eventType`, and `schemaVersion`.
- Broker is never called directly inside the command transaction.
- Relay claims via short transactions and publishes outside DB transactions.
- Lock tokens, leases, and expired-lease recovery are implemented.
- Rows are marked `SENT` only after meaningful broker confirmation.
- At-least-once delivery is expected, backed by consumer inbox/idempotency.
- Per-aggregate ordering is enforced where business rules require it.
- Retries use backoff/jitter, with `FAILED` alerts and audited replays.
- Consumer DLTs and outbox relay failures are clearly distinguished.
- Cleanup deletes only `SENT` rows after the retention period.
- CDC connectors retain WAL/binlog long enough if using Debezium.
- Rollbacks, broker outages, crash windows, duplicates, ordering, and scaling have been tested.
- Dashboards track oldest pending age, publish errors, retries, `FAILED` rows, and consumer duplicates.
- Payloads, headers, database credentials, and broker ACLs are secured.

## 36. Common Implementation Pitfalls

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Writing DB then sending to broker inside `@Transactional` | Both systems still commit independently | Write to outbox in the same DB transaction |
| Using an `AFTER_COMMIT` listener without durable storage | Crash after commit can lose the event | Persist outbox row before commit |
| Holding row locks while calling broker | Long DB transactions, lock contention | Claim/commit first, then publish separately |
| Marking `SENT` before sending | Events can be lost | Mark only after confirmation |
| Marking `SENT` when async send is merely enqueued | Broker may not have acked yet | Use sync/confirmation callbacks |
| Omitting event IDs | Duplicates cannot be reliably deduplicated | Unique event ID and inbox unique constraint |
| Inbox insert outside business transaction | Marker can commit while side effect rolls back | Record inbox and side effect in same transaction |
| Multiple workers ignoring aggregate order | Events arrive out of order | Sequences, per-aggregate claiming, and keys |
| Deleting `PENDING`/`FAILED` rows | Loses replay capability | Clean up only `SENT` rows past retention |
| Tight unbounded retries | Overloads failing broker and DB | Backoff, jitter, alerts, and circuit policies |
| CDC connector receiving `UPDATE` on insert-only outbox | SMT may warn or fail | Design CDC-specific table and lifecycle |
| Treating Kafka EOS as DB+broker atomicity | Broken consistency assumptions | Outbox + idempotent consumer |

## 37. References

- [Spring Cloud Stream — Producing and Consuming Messages / StreamBridge](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Framework — @Transactional rollback rules](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Debezium — Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html)
- [PostgreSQL — SELECT locking clause and SKIP LOCKED](https://www.postgresql.org/docs/current/sql-select.html)
- [AWS Prescriptive Guidance — Transactional Outbox Pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html)

Exact APIs, properties, and publisher confirmation behaviors depend on your Spring Cloud Stream release train, Spring Boot version, and binder. Cross-check your application BOM and broker version, and test against a real broker before release. PostgreSQL examples use `JSONB`, `SKIP LOCKED`, and `RETURNING`; if using MySQL or another database, adapt data types, locking syntax, and CDC connectors accordingly.

## Conclusion

Transactional outbox resolves dual writes by recording **business state and event intent within the same database transaction**. A relay or CDC connector then forwards committed events to the broker. A polling relay using `StreamBridge` must claim with leases, publish with confirmation, and mark `SENT` afterward; crashes after broker ack but before DB update can produce duplicates. Consumer inboxes and idempotency handle duplicates within the same transaction as side effects. When ordering matters, combine aggregate sequences, stable keys/routing, and per-aggregate relay coordination. This yields a recoverable, observable eventual-delivery model rather than an automatic distributed exactly-once transaction.
