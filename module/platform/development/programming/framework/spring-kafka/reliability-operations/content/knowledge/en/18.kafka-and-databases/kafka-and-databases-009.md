# Outbox pattern

The **Transactional Outbox Pattern** solves the data consistency problem when an application must **both write to a database and emit an event to Kafka**. The core idea is not to try committing a database transaction and publishing to Kafka as two separate operations. Instead, the application writes the **business change** and an **outbox event** into the **same database transaction**. A separate publisher component reads committed outbox events and sends them to Kafka.

In Spring Kafka Reliability Operations, this is a foundational pattern because Kafka transactions and database transactions are normally **not part of one atomic transaction**. Kafka transactions group Kafka operations together, but cannot automatically roll back a committed PostgreSQL or MySQL write. Outbox moves the initial consistency boundary into a single database where business state and the intent to emit an event can commit atomically.

Outbox does not guarantee the publisher sends an event **strictly once**: if Kafka receives the event and the publisher crashes before marking the outbox row as sent, the event can be published again. Hence the practical model is **atomic database write + eventual at-least-once Kafka publication + idempotent consumer**.

## 1. The dual-write problem

Suppose Order Service needs to:

1. Save an order to the database.
2. Publish an `OrderCreated` event to Kafka for Inventory Service, Billing Service, and Analytics Service to process.

Direct implementation:

~~~java
@Transactional
public void createOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(
        Order.from(command)
    );

    kafkaTemplate.send(
        "orders.created",
        order.getId().toString(),
        toJson(order)
    );
}
~~~

At a glance, the `@Transactional` annotation looks like it covers both actions. However, if the method's transaction manager is **JpaTransactionManager**, it primarily manages the database transaction; `KafkaTemplate.send()` does not automatically become part of the same atomic database transaction.

At least two failure windows exist:

**Database commit succeeds, Kafka publish fails:**

~~~text
INSERT orders ------------------> DB commit succeeds
                                         |
                                  Kafka send fails
                                         |
                                         v
                               Order exists in DB
                               but downstream receives no event
~~~

**Kafka publish succeeds, database rolls back:**

~~~text
Kafka broker acknowledges OrderCreated
                  |
             DB commit fails
                  |
                  v
       Downstream sees an order
       not yet in the source of truth
~~~

Reversing the order of the two operations does not solve the problem; it only shifts the failure window. Even with Kafka producer idempotence or producer retries, the application can still end up with one system committed and the other uncommitted.

That is the **dual-write** problem.

## 2. How does outbox change the design?

Instead of writing to the database and sending to Kafka inside the request transaction, Order Service writes to two tables **in the same database**:

~~~text
HTTP request: Create order
           |
           v
    BEGIN DB TRANSACTION
           |
           +-- INSERT orders
           |
           +-- INSERT outbox_events
           |
           v
       COMMIT DB
           |
           v
       Response success

        Afterward:

Outbox publisher / CDC
           |
           v
    Read committed outbox
           |
           v
      Publish Kafka
           |
           v
    Downstream consumer
~~~

If the database commits:

- The order row exists.
- The outbox row exists with the intent to publish `OrderCreated`.

If the database rolls back:

- The order row does not exist because the transaction failed.
- The outbox row does not exist either.

Both tables live inside one transactional database under the same transaction manager. Sending to Kafka happens **afterward**, without holding an HTTP request connection/transaction open waiting on the Kafka broker.

In return, events are emitted **asynchronously**, so there is usually a delay between the DB commit and Kafka publication. That is **eventual consistency** which downstream consumers must accept.

## 3. Three properties to distinguish

| Property | How does outbox address it? | Condition |
|---|---|---|
| Atomicity between business state and event intent | Written in the same database transaction | Same datasource and genuinely the same DB transaction |
| Durability of event intent | Outbox row persists after commit | Reliable database WAL/backups/retention |
| Publication to Kafka | Publisher or CDC transfers outbox rows | Retries, monitoring, and operations in place |
| Exactly-once publication | **Not guaranteed by outbox alone** | Needs extra deduplication/transactions matched to scope |
| Exactly-once downstream business effects | Not guaranteed automatically | Idempotent consumer/inbox |
| Per-aggregate event ordering | Achievable if designed properly | Keys, sequences, and publisher ordering |
| Ultra-low latency | Not guaranteed | Poll interval, CDC lag, backlog |
| Consistency across separate databases and HTTP APIs | Not guaranteed automatically | Sagas, idempotency, or additional orchestration |

In particular, **having written an outbox row** does not mean **the event has appeared in Kafka**. Separate states and metrics are required for each stage.

## 4. Designing the outbox table

An illustrative PostgreSQL schema:

~~~sql
CREATE TABLE orders (
    id UUID PRIMARY KEY,
    customer_id UUID NOT NULL,
    status VARCHAR(32) NOT NULL,
    total_amount NUMERIC(18, 2) NOT NULL,
    version BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE outbox_events (
    id UUID PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(128) NOT NULL,
    aggregate_version BIGINT,
    event_type VARCHAR(150) NOT NULL,
    schema_version INTEGER NOT NULL,
    topic_name VARCHAR(200) NOT NULL,
    event_key VARCHAR(200) NOT NULL,
    payload TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'NEW',
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ,
    next_attempt_at TIMESTAMPTZ,
    claimed_until TIMESTAMPTZ,
    claimed_by VARCHAR(100),
    claim_version BIGINT NOT NULL DEFAULT 0,
    last_error TEXT
);

CREATE INDEX idx_outbox_ready
    ON outbox_events (status, next_attempt_at, created_at);

CREATE INDEX idx_outbox_aggregate
    ON outbox_events (aggregate_type, aggregate_id, aggregate_version);
~~~

This is an example schema for a **polling publisher**. With pure **CDC/Debezium**, the outbox table can often be simpler: each row is an immutable event read from the transaction log, not necessarily needing status/lease/attempts columns.

### 4.1. Meaning of each field

- **id:** stable event identifier across publish/retry attempts; typically a UUID or unique ID.
- **aggregate_type:** business entity category, such as `Order`.
- **aggregate_id:** entity ID; commonly used as the Kafka partition key.
- **aggregate_version:** version/sequence number helping enforce per-aggregate ordering.
- **event_type:** `OrderCreated`, `OrderCancelled`, or `PaymentAuthorized`.
- **schema_version:** supports contract evolution.
- **topic_name:** publish destination, ideally restricted via allowlist/configuration rather than trusting client input.
- **event_key:** stable partition key.
- **payload:** event snapshot decided by the service at DB write time.
- **status:** lifecycle state for a polling publisher.
- **attempts/next_attempt_at:** retries with backoff.
- **claimed_until/claimed_by/claim_version:** lease/fencing mechanism preventing multiple publisher workers from claiming one row simultaneously.
- **last_error:** sanitized operational error info, free of secrets.

Not every system needs every column. The schema should reflect your actual delivery method and ordering, retry, and cleanup requirements.

## 5. Writing business state and outbox in one Spring transaction

Spring Boot example using Spring Data JPA:

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final OutboxEventRepository outboxRepository;
    private final ObjectMapper objectMapper;

    public OrderApplicationService(
            OrderRepository orderRepository,
            OutboxEventRepository outboxRepository,
            ObjectMapper objectMapper) {
        this.orderRepository = orderRepository;
        this.outboxRepository = outboxRepository;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public UUID createOrder(CreateOrderCommand command) {
        UUID orderId = UUID.randomUUID();
        Order order = Order.create(orderId, command);
        orderRepository.save(order);

        OrderCreated event = new OrderCreated(
            orderId,
            order.getCustomerId(),
            order.getTotalAmount(),
            order.getVersion()
        );

        OutboxEvent outbox = OutboxEvent.newEvent(
            UUID.randomUUID(),
            "Order",
            orderId.toString(),
            order.getVersion(),
            "OrderCreated",
            1,
            "orders.events",
            orderId.toString(),
            serialize(event)
        );

        outboxRepository.save(outbox);
        return orderId;
    }

    private String serialize(OrderCreated event) {
        try {
            return objectMapper.writeValueAsString(event);
        }
        catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                "Cannot create outbox event payload", ex
            );
        }
    }
}
~~~

The example uses illustrative domain classes/repositories. Core requirements:

1. The `@Transactional` method genuinely passes through a Spring proxy with an active **database transaction**.
2. `OrderRepository` and `OutboxEventRepository` share **the same datasource/transaction manager**.
3. If payload serialization fails, the method throws an exception to roll back the entire transaction.
4. `KafkaTemplate.send()` is not called as a step required to succeed before the database commits.
5. If the DB transaction commit fails, neither the order nor the outbox event is considered to exist.

With multiple databases or a repository using a connection outside the transaction, the two saves are no longer atomic. One `@Transactional` annotation does not create atomicity across independent datasources.

### 5.1. Events should reflect committed state

Event payloads should be constructed from data within the same transaction. Do not let the publisher re-read an order minutes later and build `OrderCreated` from its **current** state, as the order may already have changed status or version.

For instance, `OrderCreated` must record **the state at order creation time**, not state after it was later `Cancelled`. The straightforward approach is storing the immutable payload in the outbox row inside the transaction.

## 6. Why not just use @TransactionalEventListener(AFTER_COMMIT)?

A common technique:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderCreated(OrderCreated event) {
    kafkaTemplate.send("orders.events", event.orderId(), event);
}
~~~

The listener runs only after the database transaction commits successfully, avoiding publishing events **before** the DB commits. However, it is **not a durable outbox** if the event exists only in memory.

If the process crashes right after DB commit before the callback executes, or the callback tries publishing to Kafka and fails with no persistent store for the intent, the event can be lost.

**The outbox row** is the durable record allowing another publisher to continue after a restart. You can use `AFTER_COMMIT` to wake the publisher earlier (as an optimization), but never as a replacement for polling/CDC backed by a durable database outbox.

## 7. Two ways to move outbox rows to Kafka

There are two main strategies:

### 7.1. Polling publisher

A job operated by the application or a dedicated service:

1. Finds unpublished or retry-eligible outbox rows.
2. Claims a leased batch when running multiple workers.
3. Sends events to Kafka.
4. Awaits broker acknowledgement for the producer send.
5. Marks the outbox row published.
6. If sending fails, increments attempts and schedules a retry.

Advantages: requires no CDC/log-streaming infrastructure; easy to start when you already have an application database. Limitations: polling adds DB load, requires claim/retry/cleanup/ordering design, and latency depends on polling intervals.

### 7.2. Change Data Capture (CDC)

A CDC connector such as **Debezium** reads committed changes from the database transaction log (e.g., PostgreSQL WAL) and turns outbox inserts into Kafka records. The Debezium Outbox Event Router can route events based on aggregate/event metadata.

Advantages: eliminates periodic polling queries against the outbox table, typically achieves lower latency, and derives commit order from the database log. Limitations: requires operating the connector, Kafka Connect, database replication slots/log retention, snapshots, and schema evolution; still requires handling duplicates on connector restarts.

| Criterion | Polling publisher | CDC/Debezium |
|---|---|---|
Event source | Query outbox table | Database transaction log |
| Initial setup | Usually simpler | Adds connector and CDC infrastructure |
| DB load | Direct queries/claims/updates | Reads WAL/binlog; replication/log overhead |
| Latency | Depends on poll interval/backlog | Usually close to commit time, still has lag |
| Retries | Managed by application | Managed by connector/Kafka Connect per contract |
| Published state | Can store `SENT` | Does not necessarily require a row flag |
| Ordering | Depends on claiming and worker scheduling | Depends on commit-log order and Kafka mapping |
| Duplicates | Yes | Possible during recovery/restart |
| Operational concerns | Leases, retry rows, cleanup | Replication slots, connector offsets, snapshots, WAL retention |

Neither approach eliminates the need for stable event IDs and idempotent consumers.

## 8. Polling publisher: why are claims and leases needed?

Suppose an application has three replicas running a scheduler scanning:

~~~sql
SELECT *
FROM outbox_events
WHERE status = 'NEW'
ORDER BY created_at
LIMIT 100;
~~~

Without locking/claiming, all three replicas can read the same 100 rows and publish concurrently, producing unnecessary duplicates.

One solution uses PostgreSQL **FOR UPDATE SKIP LOCKED** in a short transaction to claim rows, then commits the claim before sending to Kafka.

Conceptual example:

~~~sql
WITH picked AS (
    SELECT id
    FROM outbox_events
    WHERE
        (status = 'NEW'
         OR (status = 'IN_PROGRESS' AND claimed_until < now()))
        AND (next_attempt_at IS NULL
             OR next_attempt_at <= now())
    ORDER BY created_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT 50
)
UPDATE outbox_events AS o
SET
    status = 'IN_PROGRESS',
    claimed_by = :worker_id,
    claimed_until = now() + INTERVAL '2 minutes',
    claim_version = claim_version + 1
FROM picked
WHERE o.id = picked.id
RETURNING o.*;
~~~

Effect:

- Only one transaction claims a locked row.
- An `IN_PROGRESS` row with an expired lease can be reclaimed after a crash.
- `claim_version` prevents an old worker from overwriting a row after its lease moved to another worker.

**Do not hold database transactions and row locks open while waiting on Kafka sends.** If Kafka sending takes seconds, holding DB locks reduces throughput or causes lock contention. Claim in a short transaction, commit the claim, send to Kafka outside the DB transaction, then update status in another transaction.

### 8.1. Leases do not eliminate duplicates by themselves

Suppose worker A claims a row, sends to Kafka successfully, and stops before marking `SENT`. Once the lease expires, worker B reclaims the row and sends it again.

Leases prevent multiple workers from processing **concurrently under normal conditions**, but cannot tell for sure whether Kafka already persisted a record when a worker crashes.

This is why event IDs and idempotent consumers remain necessary.

## 9. Publisher: only mark SENT after Kafka acknowledgement

Application-layer logic example:

~~~java
@Component
public class OutboxPublisher {

    private final OutboxStore outboxStore;
    private final KafkaTemplate<String, String> kafkaTemplate;

    public OutboxPublisher(
            OutboxStore outboxStore,
            KafkaTemplate<String, String> kafkaTemplate) {
        this.outboxStore = outboxStore;
        this.kafkaTemplate = kafkaTemplate;
    }

    @Scheduled(fixedDelayString = "${outbox.poll.delay.ms:500}")
    public void publishPending() {
        List<ClaimedOutboxEvent> batch =
            outboxStore.claimReadyRows(50);

        for (ClaimedOutboxEvent event : batch) {
            try {
                ProducerRecord<String, String> record =
                    new ProducerRecord<>(
                        event.topicName(),
                        event.eventKey(),
                        event.payload()
                    );

                record.headers().add(
                    "event-id",
                    event.id().toString().getBytes(StandardCharsets.UTF_8)
                );

                kafkaTemplate.send(record)
                    .get(30, TimeUnit.SECONDS);

                outboxStore.markSent(
                    event.id(),
                    event.claimVersion()
                );
            }
            catch (Exception ex) {
                outboxStore.scheduleRetry(
                    event.id(),
                    event.claimVersion(),
                    ex
                );
            }
        }
    }
}
~~~

The **OutboxStore** and **ClaimedOutboxEvent** interfaces are illustrative abstractions; the application must implement SQL claiming, retry/lease management, and concurrency control. The code uses synchronous future waits to highlight the confirmation boundary; production can use async callbacks with bounded concurrency if claim/state transitions are managed properly.

To prevent errors from losing events:

- **markSent** runs only after the Kafka producer future reports success.
- If the producer send fails, the row must remain eligible for retry.
- If the producer send times out, the outcome may be **unknown**: do not delete the outbox row, and accept possible duplicate publishes.
- Guard `markSent`/`scheduleRetry` with `claim_version` so an old worker cannot overwrite a newer worker's result.
- Do not let failed rows hang permanently if a worker dies; leases must support reclamation.
- Never write sensitive raw payloads into `last_error` or logs.

### 9.1. Fencing updates on claimed rows

Update logic example:

~~~sql
UPDATE outbox_events
SET
    status = 'SENT',
    published_at = now(),
    claimed_by = NULL,
    claimed_until = NULL
WHERE id = :event_id
  AND claim_version = :claim_version
  AND status = 'IN_PROGRESS';
~~~

If affected rows equals 0, the worker may have lost its lease or the row already transitioned. Log/emit a metric and do not relax the `WHERE` clause just to "force it to succeed."

Similarly in `scheduleRetry`, updates must check `claim_version`. If a send actually succeeded after the claim expired due to a long timeout, another worker may still republish; version checks protect **database state**, not single-publish uniqueness.

## 10. Critical failure windows

| Failure point | Database state | Kafka state | Expectation |
|---|---|---|---|
| Failure before DB commit | Both order and outbox roll back | No corresponding event from outbox | Safe to retry request by request ID |
| DB commits, publisher has not run yet | Order and outbox committed | No event yet | Publisher will send shortly |
| Publisher claims then crashes | Outbox `IN_PROGRESS` | Unknown, likely unsent | Lease expires, another worker reclaims |
| Kafka send clearly fails | Outbox not `SENT` | Event unconfirmed | Retry with backoff |
| Kafka wrote record, response lost | Outbox not `SENT` | Event may already exist | Retry may produce duplicate |
| Kafka ack succeeds, `markSent` fails | Outbox not `SENT` | Event exists | Retry may produce duplicate |
| `markSent` succeeds | Outbox `SENT` | Broker acknowledged per config | Eligible for policy-based cleanup |
| Consumer updates DB, Kafka offset commit fails | Outbox event reached Kafka | Downstream may replay | Idempotent consumer |

The distinction between **never losing publish intent** and **never publishing duplicate events** is central to design. Outbox solves the first at the DB commit boundary. The second must be handled at the consumer/semantic layer.

## 11. Why is a polling publisher usually at-least-once?

Suppose:

~~~text
Publisher reads row E-42
      |
      v
Kafka send(E-42) succeeds
      |
      v
Process crashes before UPDATE status='SENT'
      |
      v
Publisher restarts
      |
      v
Sees E-42 is not SENT
      |
      v
Kafka send(E-42) again
~~~

There is no shared atomic commit between updating DB `status='SENT'` and a Kafka producer send in a standard polling outbox design. Thus the safe behavior is accepting **at-least-once delivery** and preventing duplicates with a stable event ID.

Never mark `SENT` **before** Kafka confirmation to avoid duplicates. That trades duplicates for **event loss** if the Kafka publish fails after the DB status changed.

In reliability engineering, **duplicates controllable via idempotency** are generally far better than **silent loss** that cannot self-heal.

## 12. Consumer idempotency via the inbox pattern

An outbox on the producer should be paired with an **inbox/dedup** on critical consumers. The consumer records processed event IDs in the same database transaction as its business side effect.

PostgreSQL example:

~~~sql
CREATE TABLE processed_events (
    event_id UUID NOT NULL,
    consumer_name VARCHAR(100) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (event_id, consumer_name)
);
~~~

The key combines `event_id` and `consumer_name` so two different services can process the same event without blocking each other.

Illustrative Spring service:

~~~java
@Service
public class InventoryEventProcessor {

    private final JdbcTemplate jdbc;
    private final InventoryRepository inventoryRepository;

    public InventoryEventProcessor(
            JdbcTemplate jdbc,
            InventoryRepository inventoryRepository) {
        this.jdbc = jdbc;
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public void handle(OrderCreated event) {
        int inserted = jdbc.update(
            """
            INSERT INTO processed_events(event_id, consumer_name)
            VALUES (?, ?)
            ON CONFLICT DO NOTHING
            """,
            event.eventId(),
            "inventory-service"
        );

        if (inserted == 0) {
            return; // Event was already processed successfully earlier.
        }

        inventoryRepository.reserve(
            event.orderId(),
            event.items()
        );
    }
}
~~~

Prerequisite: **`JdbcTemplate` and `InventoryRepository` must share the same database transaction**. If `reserve` fails, both the `processed_events` insert and the business update must roll back. If the processed marker commits while `reserve` fails, retries will mistake the event for a duplicate and skip the business action.

With `@KafkaListener`:

~~~java
@KafkaListener(
    topics = "orders.events",
    groupId = "inventory-service"
)
public void onOrderCreated(OrderCreated event) {
    inventoryEventProcessor.handle(event);
}
~~~

Once `handle` commits the DB successfully and the listener returns, the container proceeds to commit the consumed offset per `AckMode`. If the Kafka offset commit fails, the record may replay, and the `processed_events` table prevents repeated side effects.

For APIs/side effects outside the database, you also need idempotency keys or a corresponding outbox/saga; a database inbox alone does not prevent repeating an HTTP call.

## 13. Event ID, aggregate ID, and Kafka key

Three values serve distinct purposes:

| Value | Example | Role |
|---|---|---|
| `eventId` | UUID E-42 | Deduplication across retries/replays |
| `aggregateId` | Order O-123 | Groups events belonging to the same entity |
| Kafka key | O-123 | Selects partition; typically preserves per-aggregate ordering |

If the publisher retries E-42, **`eventId` must remain unchanged**. Never generate a new UUID on each send attempt, or consumers will treat them as distinct events and deduplication will fail.

The Kafka key is usually `aggregateId` so events for the same order route to the same partition under a stable topology/partition mapping. Yet sharing a partition is **not enough** to guarantee ordering if the publisher sends events for the same aggregate out of order.

Example of `OrderCreated` version 1 and `OrderCancelled` version 2:

~~~text
Database commit:
  OrderCreated(v1)
  OrderCancelled(v2)

Publisher worker B sends v2 before worker A sends v1
        |
        v
Kafka partition receives v2 then v1
~~~

Kafka preserves the order **appended to the partition**; it cannot correct an application sending out of order.

## 14. Preserving ordering with an outbox

Ordering is the hardest part in a multi-worker outbox. Considerations:

- Use a monotonically increasing **aggregate version** inside the database transaction if business logic requires sequence.
- Serialize events for the same aggregate by version.
- Prevent two independent publishers from claiming and sending two events of the same aggregate in reverse order.
- Use the same Kafka key per aggregate when partition mapping is stable.
- Consumers can inspect versions to detect late or missing events.
- If a Kafka topic increases partition count, key→partition mappings can change; plan migrations if strict historical ordering is mandatory.

Do not treat an **auto-incrementing outbox ID** or **`created_at`** as an absolute guarantee of **DB commit order** under concurrent transactions. Sequence numbers in a DB can be allocated before commit; a transaction with a smaller ID can still commit after a transaction with a larger ID.

With a polling publisher, you may need per-aggregate claiming (at most one in-flight event per aggregate), locking the business row when allocating versions, or another sequencing mechanism. With CDC, commit-log ordering reflects database commit order, though routing to Kafka and parallel consumers still require appropriate keys/partitions.

## 15. Retries for a polling publisher

An outbox row that fails to publish must not be lost. Apply retries with backoff:

~~~text
attempt = 1 -> wait 1s
attempt = 2 -> wait 2s
attempt = 3 -> wait 4s
attempt = 4 -> wait 8s
attempt = 5 -> wait 16s
Afterward -> max 60s or transition to NEEDS_ATTENTION
~~~

Design points:

- Classify transient errors like timeouts/coordinator unavailable separately from permanent errors like bad ACLs/serializers.
- Configure bounded producer delivery timeouts and backoffs.
- Do not spin in a hot retry loop on a row that can never succeed.
- If an event is marked `NEEDS_ATTENTION` or `FAILED`, keep its payload/event ID and fire an alert; **never delete the row**.
- If strict ordering requires version 1 before version 2, a failure on version 1 may force the publisher to hold later versions of the same aggregate.
- Only mark `SENT` with sufficient broker acknowledgement evidence per producer `acks` policy.

A failing outbox row is not a Kafka consumer poison pill. It belongs to the **DB-to-Kafka publisher** failure domain; keep its retries and monitoring separate from Kafka listener error handling.

## 16. CDC with Debezium Outbox Event Router

With PostgreSQL, a Debezium connector can read logical decoding/WAL and emit committed outbox inserts. The Event Router SMT can transform rows into Kafka events based on aggregate metadata.

A CDC-friendly schema typically has these fields:

~~~sql
CREATE TABLE outbox_event (
    id UUID PRIMARY KEY,
    aggregatetype VARCHAR(100) NOT NULL,
    aggregateid VARCHAR(128) NOT NULL,
    type VARCHAR(100) NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

This schema follows the naming commonly used with Debezium Outbox Event Router. If using different column names, adjust connector settings accordingly.

Example Kafka Connect/Debezium configuration fragment:

~~~properties
transforms=outbox
transforms.outbox.type=io.debezium.transforms.outbox.EventRouter
transforms.outbox.table.field.event.id=id
transforms.outbox.table.field.event.key=aggregateid
transforms.outbox.route.by.field=aggregatetype
~~~

Event Router can route events by aggregate type, use aggregate ID as the Kafka key, and carry the event ID for downstream deduplication. Topic naming, payload fields, and envelope/header configuration must match your Debezium version and actual event contract.

CDC operational requirements:

- Database has logical replication or binlog enabled per connector requirements.
- Connector has appropriate read and replication privileges.
- Replication slot/log retention is monitored to prevent unbounded WAL growth if the connector stops.
- Kafka Connect has durable offset storage.
- Snapshot/initial start and schema evolution are handled.
- Event IDs remain stable to tolerate duplicates on connector restarts.

CDC does not mean an insert is **guaranteed to appear only once** in Kafka when a connector crashes or recovers. Design idempotent consumers.

## 17. Do not accidentally run both polling and CDC on the same source

When migrating from polling to Debezium, if both publishers read and send **the same outbox rows**, the same event ID can appear twice or more from two independent pipelines.

When migrating:

1. Identify which publisher source is active.
2. Pick a clear cutover time and checkpoint.
3. Verify connector snapshot behavior.
4. Track published event IDs across both paths.
5. Never delete outbox rows lacking proof they were processed.
6. Rely on idempotent consumers during the transition window.

Do not assume turning off the polling scheduler and enabling CDC is enough without accounting for pending rows and transaction log offsets.

## 18. Do outbox and Kafka transactions complement each other?

Yes, though you must understand each mechanism's scope:

**Outbox** ensures business state changes and event intent sit in the same database transaction.

**Kafka transactions** ensure a group of Kafka operations and, in consume–transform–produce, consumed offsets can commit or abort together.

A transactional Kafka producer inside an outbox publisher can be useful if one outbox row produces multiple Kafka records that must commit atomically. However, the Kafka transaction **does not** include updating the DB status to `SENT`. If the broker commits the Kafka transaction and the DB update to `SENT` does not happen, the row can still be republished after a restart.

~~~text
DB transaction:
  INSERT orders + INSERT outbox
               |
               v
        Outbox publisher
               |
               v
        Kafka transaction commit
               |
               X  No automatic atomic bridge
               |
               v
        DB UPDATE outbox SET status='SENT'
~~~

Do not market outbox + Kafka transactions as an atomic distributed exactly-once commit between database and Kafka. To achieve exactly-once business effects, you still need event IDs and idempotency on consumers.

## 19. What happens when a record is published twice?

Example outbox row:

~~~json
{
  "eventId": "e782a43e-7ca4-4b9c-bc70-2ad583aa0e12",
  "aggregateType": "Order",
  "aggregateId": "O-123",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "payload": {
    "orderId": "O-123",
    "totalAmount": 250000
  }
}
~~~

The publisher sends the event to Kafka, the broker writes it, and the application crashes before `markSent`. After restart, the publisher resends. Consumers can see two records at different Kafka offsets with **the same `eventId`**:

~~~text
Kafka orders.events:
    offset 101: eventId E-42
    offset 125: eventId E-42

Inventory consumer:
    E-42 first time -> insert processed_event, reserve stock
    E-42 second time -> unique constraint, do not reserve stock again
~~~

If a consumer used the Kafka offset as its idempotency key, the duplicate at offset 125 would go undetected. Thus, a stable **business event ID** is the essential deduplication key.

An event ID needs an appropriate uniqueness scope. In multi-tenant systems, a composite key such as `(tenant_id, event_id, consumer_name)` may be used depending on the contract.

## 20. Idempotency of the HTTP command creating the outbox

Not only can the Kafka publisher retry; an HTTP client can also resend `CreateOrder` when a response times out after the DB commit.

If every HTTP request creates a new order and a new outbox event without an idempotency key, a client retry can create **two separate valid orders**.

When an API requires create-once semantics, use a request ID/idempotency key:

~~~sql
CREATE TABLE command_dedup (
    request_id UUID PRIMARY KEY,
    aggregate_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Inside the same database transaction, the service checks/inserts the request ID via a unique constraint; if the request was already processed, it returns the corresponding order ID instead of creating a new order and emitting a new event.

Outbox keeps the order row and event intent consistent, but does not by itself prevent duplicates caused by **clients resending commands**.

## 21. Cleanup and retention

An outbox table that only grows without cleanup causes:

- Continuously growing storage and indexes.
- Slower polling queries.
- Expensive backups/vacuuming/maintenance.
- Longer database restore times.

With a polling publisher, typically only **`SENT` rows** past a safe retention window are cleaned up. Never delete `NEW`, unrecovered `IN_PROGRESS`, or unresolved `FAILED`/`NEEDS_ATTENTION` rows.

Example:

~~~sql
DELETE FROM outbox_events
WHERE status = 'SENT'
  AND published_at < now() - INTERVAL '7 days';
~~~

A 7-day retention is only an example. Account for:

- Investigation/replay windows.
- Kafka retention and downstream consumer lag.
- Backup/snapshot and audit requirements.
- Risk of an outbox row being marked `SENT` erroneously.
- Regulatory or sensitive-data constraints.

With CDC, avoid deleting/updating outbox rows in ways that cause the Event Router to emit unwanted extra events. Many CDC designs use insert-only event tables and managed cleanup; always check connector SMT/filter behavior.

## 22. Polling can lose ordering on large batches

Suppose worker A claims 50 older events and worker B claims 50 newer events. Worker B has a faster broker connection and publishes ahead of worker A.

Then the Kafka log receives the newer events first, even though their `created_at` timestamps are later.

If global ordering is not required, the system may accept this. If per-aggregate ordering is required:

- Claim per aggregate so no two events for the same aggregate are in flight simultaneously.
- Send an aggregate's events in `aggregate_version` order.
- Enforce optimistic version checks at consumers.
- Evaluate CDC to follow commit-log order.
- Do not assume Kafka preserves DB order when publishers send in parallel.

Retries of older versions must also be considered: if version 1 fails to publish, may version 2 be sent or must it wait? Answer based on the downstream contract, not throughput wishes.

## 23. Outbox and microservice sagas

Outbox solves one segment of a distributed workflow, not the whole workflow:

~~~text
Order Service:
   DB commit OrderCreated + outbox event
      |
      v
Kafka
      |
      v
Inventory Service:
   DB reserve + outbox InventoryReserved
      |
      v
Kafka
      |
      v
Billing Service:
   Charge payment + outbox PaymentAuthorized
~~~

Each service uses an outbox to ensure event intent aligns with its local database commit. Yet if Inventory succeeds and Billing fails, the workflow needs a **saga/compensation** or state machine to cancel the reservation, retry charging, or route to manual review.

Outbox is not a distributed transaction across three services; it is a building block enabling each service to emit events reliably from local transactions.

## 24. Security and event payload quality

Outbox payloads can exist simultaneously in the database, Kafka, and DLTs. Avoid copying every column of a business entity into an event unnecessarily.

Helpful practices:

- Include only fields downstream consumers need.
- Tag schema version and event type.
- Exclude passwords, tokens, secrets, or unnecessary sensitive data.
- Apply ACLs and encryption to database/outbox/topics.
- Do not log raw payloads on publish failures.
- Enforce suitable retention/deletion policies.
- Check Kafka record size limits when constructing outbox payloads.
- Normalize timestamps/time zones so consumers interpret them unambiguously.

If events must conform to Avro/JSON Schema/Protobuf contracts, validate payloads before the DB commit. If serialization/validation fails, roll back both the business write and outbox write rather than leaving the publisher with a permanent poison row.

## 25. Observability: monitor all three stages

Do not look only at Kafka records published. An outbox dashboard should track:

| Metric/signal | Question |
|---|---|
| Outbox inserts/sec | At what rate is business logic creating event intent? |
| Pending outbox rows | How many events remain unpublished? |
| Oldest pending age | How long has the oldest event been waiting? |
| Claimed/in-progress count | How many rows are currently being processed by publishers? |
| Expired leases count | Are workers dying or publishes stalling? |
| Publish success/sec | Are events actually being confirmed by the broker? |
| Publish failures by exception | Is the issue broker, ACL, serializer, or topic? |
| Retry attempts/backoff | Is there a retry storm or a stuck row? |
| Outbox → Kafka publish latency | How long from DB commit to Kafka ack? |
| CDC connector lag | Are WAL/binlog and Connect falling behind? |
| Kafka topic consumer lag | Is downstream keeping up? |
| Consumer dedup hits | How many duplicates were caught? |
| Business completion latency | How long until downstream business work finishes? |

In particular, **oldest pending age** is often more important than pending count. A pending row after a 2-second blip is tolerable; a single row unsent for 4 hours warrants an alert even if the pending count is tiny.

Alerts need owners, SLO-backed thresholds, and runbooks. Never put `eventId` into high-cardinality metric labels; log `eventId` in logs/traces alongside correlation IDs.

## 26. Runbook: outbox backlog growing

When pending outbox rows rise or event age breaches SLO:

### Step 1: Scope the issue

- Is polling or CDC in use?
- Is the backlog limited to one tenant/topic/aggregate or affecting the whole publisher?
- How do outbox inserts/sec compare with publish success/sec?
- Is the Kafka producer receiving acknowledgements?

### Step 2: Check the database

- Are ready-row queries using indexes?
- Is there lock contention, long-running DB transactions, or connection pool exhaustion?
- Are many `IN_PROGRESS` leases expiring?
- Are table/index sizes or vacuum/maintenance causing problems?

### Step 3: Check Kafka

- Does the destination topic exist?
- Are producer ACLs valid for the topic?
- How are leader, ISR, and broker health?
- Are producers hitting serialization, record-too-large, or timeout errors?
- Do Kafka keys/event schemas match contracts?

### Step 4: Check the publisher

- Have processes/workers crashed or paused?
- Is lease expiry longer than producer timeouts?
- Is a worker infinitely retrying a failing row and starving others?
- Is excessive concurrency causing reordering or overloading brokers?

### Step 5: Controlled recovery

- Fix ACL/topic/serializer/DB issues.
- Retry rows that still hold intent, keeping `eventId` unchanged.
- Rate-limit backlog draining to avoid overwhelming downstream.
- Watch publish success rate rise and oldest age drop.

### Step 6: Check duplicate and ordering aftermath

- Did any Kafka sends succeed while DB `markSent` failed?
- Are downstream idempotency and consumer lag healthy?
- Did any aggregate versions arrive out of order?
- Is business reconciliation or manual correction required?

## 27. Runbook: Kafka already has the event, yet status is still NEW

Symptom: `eventId` E-42 appears in Kafka, while outbox row E-42 is not `SENT`. This is the expected failure window of an at-least-once publisher.

Actions:

1. Verify `eventId` and `aggregateId` on the Kafka record.
2. Check publisher logs around send/ack/`markSent`.
3. Do not manually delete the outbox row before understanding the state.
4. If letting the publisher retry, keep `eventId` unchanged so consumers deduplicate.
5. Verify whether downstream already executed the side effect.
6. If state reconciliation is needed, record it through an audited procedure.

Never "fix" the publisher by marking `SENT` immediately after `send()` to avoid duplicates: that turns a failed send into event loss.

## 28. Reliability testing for outbox

Valuable test cases:

### 28.1. Database rollback

Force business validation or a DB constraint to fail. Verify both the business row and outbox row roll back.

### 28.2. Database commits while Kafka is unavailable

Create an order while the Kafka broker is temporarily stopped in the test environment. Verify both order and outbox commit, the pending outbox row persists, and the publisher succeeds once Kafka recovers.

### 28.3. Publisher crashes before Kafka send

Claim a row and stop the publisher before sending. Once the lease expires, another worker reclaims and publishes.

### 28.4. Publisher crashes after Kafka ack

Let the Kafka send succeed and kill the process before `markSent`. After restart, the event republishes with **the same `eventId`**; the idempotent consumer does not execute the side effect a second time.

### 28.5. Two competing publishers

Two workers concurrently claim outbox rows. Verify locking/claiming prevents the same row from being active on two workers during a valid lease. Test reclamation after lease expiration.

### 28.6. Per-aggregate ordering

Create `OrderCreated(v1)`, `OrderPaid(v2)`, `OrderCancelled(v3)` in quick succession. Force a retry on v1 and verify whether publisher/consumer preserve ordering/version contracts.

### 28.7. Permanent publish error

Producer lacks ACL, uses a broken serializer, or targets a nonexistent topic. Verify the row is neither deleted nor marked `SENT`, alerts fire, and config-fix/retry recovery works.

### 28.8. CDC restart

With Debezium, stop the connector after events exist and restart it. Verify no event intent is lost and consumers tolerate duplicate/snapshot behavior.

Never use a production cluster to simulate broker outages, lock replication slots, or delete topics. Use controlled test infrastructure/fault injection.

## 29. Common design mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Writing business DB then directly to Kafka | Dual-write gap and inconsistency | Write business row + outbox in one DB transaction |
| Using `@TransactionalEventListener` as a durable queue | Crash after DB commit loses event intent | Persist a durable outbox row |
| Marking `SENT` before Kafka ack | Events lost on send failures | Mark only after successful send result |
| Lacking a stable event ID | Consumers cannot deduplicate duplicates | Generate `eventId` when writing outbox, preserve across retries |
| Multiple publishers `SELECT`ing without lock/claim | Unnecessary duplicate publishes | Appropriate lease + `SKIP LOCKED`/claiming |
| Holding DB row locks during Kafka sends | Lock contention and long transactions | Short claim transaction, send outside DB tx |
| Not reclaiming `IN_PROGRESS` | Crashes leave events stuck forever | Lease expiry and recovery |
| Updating `SENT` without checking claim version | Stale worker overwrites new worker's state | Fencing/version check |
| Treating auto-increment ID as DB commit order | Wrong ordering under concurrency | Aggregate version or CDC commit order |
| Using random keys for the same aggregate | Events scatter across partitions | Key = `aggregateId` when ordering is needed |
| Assuming outbox guarantees strict once-only publish | Crash after ack before mark creates duplicates | Idempotent consumer/inbox |
| Outbox row stores only aggregate ID; publisher reads latest state | Event payload does not reflect state at change time | Store snapshot payload inside the DB transaction |
| Deleting all old rows blindly | Can delete pending/failed events | Clean up by status and retention |
| Not monitoring oldest pending age | Long-stuck events go unnoticed if count is small | Age/SLO-based alerts |
| Running polling and CDC on the same source during cutover | Mass duplicates | Checkpoint-based cutover and dedup |
| Assuming Kafka transactions include outbox status `UPDATE` | No atomicity across the two systems | Accept at-least-once + idempotency |

## 30. Outbox pattern rollout checklist

Before going to production, confirm:

1. Are business rows and outbox rows written in **the same database transaction**?
2. If the transaction rolls back, do both datasets roll back together?
3. Is the event payload constructed from business state at transaction time?
4. Does every event carry a stable `eventId`, `aggregateId`, `eventType`, and `schemaVersion`?
5. Is the publisher polling or CDC, with clear operational ownership?
6. If polling, is claim/lease safe across multiple replicas and crashes?
7. Does Kafka sending wait for acknowledgement before marking `SENT`?
8. If a send result times out/is ambiguous, does the publisher keep the event for safe retry?
9. If Kafka received the event while `markSent` failed, are consumers idempotent?
10. Do Kafka keys support per-aggregate ordering where required?
11. Are versions/sequences or out-of-order handlers present if required by the domain?
12. Does retry/backoff distinguish transient from permanent errors?
13. Does the outbox table have proper indexes and cleanup that deletes only safe records?
14. If CDC, are replication slot/binlog retention and connector offsets monitored?
15. Does downstream have inbox/dedup running in the same DB transaction as side effects?
16. Are metrics tracked for oldest pending age, publish failures, retry rate, and end-to-end business latency?
17. Do runbooks exist for Kafka outages, DB locks, serializer/ACL errors, and publisher crashes?
18. Are failure windows tested at DB commit, Kafka ack, and `markSent`?
19. Are security, sensitive-data, and schema evolution policies defined for outbox payloads?
20. For multi-service workflows, are sagas/compensation designed separately?

**Conclusion:** The outbox pattern closes the dual-write gap by persisting business changes and Kafka event publish intent in the same database transaction. A polling publisher or CDC moves committed events to Kafka with retry capability, though it can still emit duplicates if a crash occurs at the boundary between Kafka acknowledgement and updating outbox state. Therefore, a durable implementation requires stable outbox event IDs, a publisher with safe leases/acks/retries or properly operated CDC, Kafka keys and versions for ordering, consumer idempotency/inboxes, and dashboards detecting backlogs. Outbox builds a foundation for data consistency between Kafka and databases that is **eventual, at-least-once, and recoverable**, rather than an automatic distributed exactly-once promise.
