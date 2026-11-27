# Synchronizing Data Changes with Events Using the Transactional Outbox

In the **Data Correctness** chapter, the transactional outbox solves a common bug in distributed applications: database state changes, yet the event notifying other systems is never published—or an event is published even though the business transaction ultimately rolled back. This pattern writes business changes and the event to be published inside the same transaction, after which a separate publisher dispatches committed events to a queue or event bus.

This lesson belongs to the **CLOUD_SERVERLESS** module, which focuses on developing and deploying serverless applications—especially Java functions triggered by HTTP, messages, or events. Learners handle triggers, state, access permissions, retries, idempotency, cold starts, scaling, and cost to determine when to use FaaS. The transactional outbox lets Java functions synchronize data changes with event streams without relying on a publish call outside the database transaction.

## 1. The Dual-Write Problem

Suppose an HTTP handler receives an order creation request. The application needs to:

1. Write the order to the database.
2. Publish an `OrderCreated` event for inventory, billing, and notification services to process.

If the code executes these as two separate operations, two failure windows open:

**Write database first, publish second**

- The database commit succeeds.
- The process crashes or Lambda times out before publishing.
- The order exists, yet consumers never receive `OrderCreated`.

**Publish first, write database second**

- The event is published and processed by consumers.
- The database transaction fails or rolls back.
- Downstream systems believe the order was created while the source database has no order.

This is the dual-write problem: two independent systems must be updated as though they were one atomic operation, yet no shared transaction spans the database and broker.

~~~mermaid
sequenceDiagram
    participant API as Java handler
    participant DB as Database
    participant BUS as Event broker
    participant C as Consumer
    API->>DB: INSERT order
    DB-->>API: COMMIT
    API->>BUS: Publish OrderCreated
    Note over API,BUS: Process can fail between the two writes
    BUS->>C: Event
~~~

Retrying the publish call does not fully solve the issue. If the process crashes after the broker receives the event but before the application records publish success, a retry can emit the event a second time.

## 2. What Does the Transactional Outbox Solve?

The transactional outbox adds an outbox table or record collection inside the same database as the business data. Within a single transaction:

- Update business tables.
- Insert the event into the outbox.
- Commit both together.

A separate publisher reads committed outbox records and sends them to the broker. Once the broker acknowledges receipt, the publisher updates the record status so it is not resent in the normal flow.

~~~mermaid
flowchart TD
    API["Java application / Lambda"] --> TX["One database transaction"]
    TX --> B["Write business data"]
    TX --> O["Insert outbox event"]
    B --> COMMIT["Commit"]
    O --> COMMIT
    COMMIT --> PUB["Outbox publisher"]
    PUB --> BUS["Queue / EventBridge / Kafka"]
    BUS --> C["Idempotent consumers"]
~~~

If the transaction rolls back, neither the business change nor the outbox event exists. If the transaction commits, both can be discovered later by the publisher, even if the application process terminates immediately after committing.

The transactional outbox guarantees atomicity between business writes and the intent to publish events. It does not create a distributed transaction between database and broker, nor does it guarantee the broker receives events exactly once. The publisher can still send duplicates; consumers still require idempotency.

## 3. Guarantees and Limitations

| Property | Provided by Outbox? | Explanation |
|---|---|---|
| Business state and event record commit together | Yes | Same database transaction |
| Event created only when business transaction commits | Yes | Rollback removes both |
| Event is eventually attempted for publishing | Yes, if the publisher keeps running | Requires retries, monitoring, and handling failed records |
| Broker receives exactly once | No | Crashing after send but before marking published can produce duplicates |
| Consumer processes business effect exactly once | Not automatically | Requires consumer-side inbox/idempotency and transactions |
| Global ordering preserved | No | Requires partition/group keys and publisher ordering |
| Event published instantaneously | No | Latency exists between commit and publisher execution |

The practical model is usually at-least-once delivery paired with idempotent consumers. Systems can achieve an effectively-once business outcome within a defined boundary, but you should not claim every message traverses the entire system strictly once.

## 4. Define the Event Contract Before Creating the Outbox

An outbox stores a business-meaningful event, not merely an arbitrary copy of a database row. An event envelope should include:

| Field | Purpose |
|---|---|
| `eventId` | Stable identifier for deduplication |
| `eventType` | Event type name |
| `schemaVersion` | Payload version |
| `aggregateId` | Related business entity |
| `aggregateVersion` | Change order within the aggregate |
| `occurredAt` | Timestamp when the business event occurred |
| `correlationId` | Correlates workflow steps |
| `causationId` | Command or event that caused the change |
| `payload` | Data consumers need for processing |

Example payload:

~~~json
{
  "eventId": "evt-01J9ORDER42",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "aggregateId": "order-42",
  "aggregateVersion": 1,
  "occurredAt": "2026-11-17T10:15:00Z",
  "correlationId": "request-8f31",
  "payload": {
    "orderId": "order-42",
    "customerId": "customer-17",
    "currency": "VND",
    "totalAmount": 850000
  }
}
~~~

Events should describe facts that happened, such as `OrderCreated` or `PaymentAuthorized`. Avoid naming an event like an imperative command telling a consumer what to do, such as `CreateInvoice`, unless the contract is genuinely a command targeted at a specific owner.

Do not use timestamps as the sole ordering mechanism. If multiple events for the same order must be applied sequentially, the producer must assign an authoritative `aggregateVersion` or sequence.

## 5. Designing the Outbox Table

A common SQL schema:

~~~sql
CREATE TABLE outbox_event (
    event_id           VARCHAR(200) PRIMARY KEY,
    aggregate_type     VARCHAR(120) NOT NULL,
    aggregate_id       VARCHAR(200) NOT NULL,
    aggregate_version  BIGINT NOT NULL,
    event_type         VARCHAR(160) NOT NULL,
    schema_version     INTEGER NOT NULL,
    payload            JSONB NOT NULL,
    occurred_at        TIMESTAMPTZ NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at       TIMESTAMPTZ,
    attempt_count      INTEGER NOT NULL DEFAULT 0,
    next_attempt_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    lease_owner        VARCHAR(160),
    lease_until        TIMESTAMPTZ,
    last_error_code    VARCHAR(120)
);
~~~

Key fields:

- `event_id` is the unique key generated prior to commit.
- `aggregate_type` and `aggregate_id` identify which entity the event belongs to.
- `aggregate_version` preserves ordering within an aggregate.
- `payload` contains the serialized event.
- A null `published_at` indicates the publisher has not yet confirmed completion.
- `attempt_count` and `next_attempt_at` govern retries.
- `lease_owner` and `lease_until` allow multiple publishers to share work.
- `last_error_code` aids troubleshooting without writing secrets to logs.

Index for unpublished events:

~~~sql
CREATE INDEX idx_outbox_ready
ON outbox_event (next_attempt_at, created_at)
WHERE published_at IS NULL;
~~~

Design indexes based on your database and actual queries. As the outbox grows, monitor scanned row counts, index bloat, and cleanup duration.

Do not store credentials, access tokens, or unnecessary personal data in the payload. If an event must reference sensitive data, consider storing an identifier and letting consumers fetch details through an authorized API.

## 6. Writing Business State and Outbox in the Same Transaction

Example with Spring and JPA/JDBC:

~~~java
@Service
public class OrderApplicationService {
    private final OrderRepository orders;
    private final OutboxRepository outbox;
    private final EventSerializer serializer;

    public OrderApplicationService(
            OrderRepository orders,
            OutboxRepository outbox,
            EventSerializer serializer) {
        this.orders = orders;
        this.outbox = outbox;
        this.serializer = serializer;
    }

    @Transactional
    public OrderResult createOrder(CreateOrder command) {
        Order order = Order.create(
                command.customerId(),
                command.items());

        orders.save(order);

        OrderCreated event = OrderCreated.from(order);
        OutboxRecord record = new OutboxRecord(
                event.eventId(),
                "Order",
                order.id(),
                order.version(),
                "OrderCreated",
                1,
                serializer.toJson(event));

        outbox.insert(record);

        return OrderResult.from(order);
    }
}
~~~

`OrderRepository` and `OutboxRepository` must participate in the same transaction manager and same database transaction. If one repository writes to a different database or uses a separate transaction manager, atomicity is lost.

Do not call the broker directly inside `createOrder` assuming `@Transactional` will roll back a sent message. Spring transactions govern resources enrolled with the transaction manager; they cannot recall an event already accepted by a broker.

### 6.1. Transaction Boundaries

A transaction should encompass:

1. Validating business preconditions.
2. Inserting or updating the aggregate.
3. Assigning the new aggregate version.
4. Serializing the event from confirmed data.
5. Inserting the outbox record.
6. Committing.

Never keep a transaction open while making network calls to a broker. Network calls can stall or time out, holding locks longer and increasing database contention.

If you use a post-commit callback to wake up a publisher for lower latency, treat the callback strictly as an optimization hint. The outbox record remains the durable source of truth; if the callback is lost, polling or CDC publishers must still find the record.

## 7. Constructing Events from Committed Data

Events should accurately reflect committed changes. Two common approaches:

**Snapshot event:** the payload includes all required values at the time the event occurred. Consumers can process it without querying the full aggregate again. Clearly specify which fields belong in the event and avoid sensitive data.

**Reference event:** the payload contains the aggregate ID or resource reference. Consumers fetch current data via an API or database. This shrinks payloads, though data may change before the consumer reads it; if consumers need the state at the moment the event occurred, a bare reference is insufficient.

Do not generate payloads by mechanically serializing an ORM entity. Entities can contain lazy associations, internal fields, or uncommitted state. Use dedicated event DTOs to stabilize contracts.

## 8. Polling Publisher: Reading and Sending Outbox Batches

A simple implementation is a scheduled worker or periodic Lambda:

1. Find unpublished rows whose retry time has arrived.
2. Claim a batch so only this publisher handles them.
3. Commit the claim/lease.
4. Send events to the broker.
5. When the broker acknowledges, mark rows published.
6. On failure, update attempt count and `next_attempt_at`.

The publisher should not hold a database transaction open across the network call. Claim first, commit the lease, publish afterward, and then update the outcome in a separate short transaction.

### 8.1. Claiming with Leases and `SKIP LOCKED`

Conceptual query for PostgreSQL:

~~~sql
WITH candidates AS (
    SELECT event_id
    FROM outbox_event
    WHERE published_at IS NULL
      AND next_attempt_at <= CURRENT_TIMESTAMP
      AND (
          lease_until IS NULL
          OR lease_until < CURRENT_TIMESTAMP
      )
    ORDER BY created_at, event_id
    LIMIT :batch_size
    FOR UPDATE SKIP LOCKED
)
UPDATE outbox_event AS o
SET lease_owner = :worker_id,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '30 seconds',
    attempt_count = attempt_count + 1
FROM candidates AS c
WHERE o.event_id = c.event_id
RETURNING o.*;
~~~

This is a PostgreSQL example; adapt parameter binding and transaction handling to your JDBC/ORM framework. `SKIP LOCKED` allows multiple publishers to claim disjoint rows without blocking on each other's locks.

Leases should exceed normal publish latency while remaining bounded. If a publisher dies, the lease expires and another worker can reclaim the row. If publishing takes longer than the lease, two workers may send the same event; you can renew leases or tune timeouts appropriately, while consumers must still deduplicate.

### 8.2. Marking Published After Broker Acknowledgment

Once the broker confirms the event was accepted, the publisher updates:

~~~sql
UPDATE outbox_event
SET published_at = CURRENT_TIMESTAMP,
    lease_owner = NULL,
    lease_until = NULL,
    last_error_code = NULL
WHERE event_id = :event_id
  AND lease_owner = :worker_id
  AND published_at IS NULL;
~~~

The `lease_owner` condition prevents a stale worker from overwriting the state of a newer worker that reclaimed the row after lease expiration.

A failure window still exists: the broker accepts the event, and the publisher crashes before running the `UPDATE`. Once the lease expires, the event is sent again. This is intentional at-least-once behavior; consumers must handle duplicates safely.

Never mark an event published before broker acknowledgment. Doing so before a broker rejection or network failure drops the event from the retry loop.

## 9. Retrying and Handling Failed Outbox Records

Publish failures can be transient or permanent:

| Failure | Action |
|---|---|
| Timeout / network reset | Retry with backoff |
| Broker throttling | Respect quotas and `retry-after` if provided |
| Authentication / authorization | Alert and fix permissions; do not retry indefinitely |
| Payload exceeds size limit | Transition to attention-required state, fix contract, or use references |
| Invalid schema / config | Quarantine the record and investigate |
| Prolonged broker outage | Retain outbox, alert on backlog, throttle producers if needed |

Backoff with jitter prevents publishers from triggering retry storms:

\[
delay_n = random(0,\ min(maxDelay,\ baseDelay \times 2^n))
\]

Bound retry attempts or total event age, but never delete business events merely because the publisher retried many times. Transition the record to `NEEDS_ATTENTION`, preserve the payload, alert operators, and require intervention. Retention policies must ensure unconfirmed events are never lost.

One failing event should not stall the entire outbox. However, if per-aggregate ordering is mandatory, later versions of that aggregate may need to wait behind the earlier event. This is an explicit trade-off between availability and ordering that must be documented in the design.

## 10. Preserving Event Ordering per Aggregate

Multiple publishers running in parallel can emit events for the same aggregate out of order. For example, version 5 is delayed while version 6 is sent earlier by another publisher.

When ordering matters:

- Use `aggregate_id` as the partition key or message group key.
- Have publishers send the next event for an aggregate only after the broker acknowledges the prior event.
- Prevent multiple publishers from concurrently emitting for the same aggregate.
- Include `aggregate_version` so consumers detect stale events or gaps.
- Accept that a failed event may block subsequent versions for that specific aggregate.

Global ordering is unnecessary if business rules only require per-aggregate ordering. Partitioning by aggregate lets different aggregates publish in parallel.

A claim query can exclude rows that have an unpublished lower version, though the SQL logic must be tested under concurrency. Another approach is sharding publishers by a hash of `aggregate_id` and processing sequentially within each partition.

Broker ordering preserves order only within the scope supported by the broker, such as a message group or partition. It cannot fix events whose producer assigned wrong versions or events replayed out of order.

## 11. CDC Publishers Instead of Polling

Change Data Capture (CDC) reads the database transaction log or change stream to detect new outbox records. Examples:

- Debezium reading PostgreSQL/MySQL transaction logs with an outbox event router.
- DynamoDB Streams emitting change records from an outbox table.
- A managed CDC service streaming database logs to a broker.

CDC reduces continuous polling overhead and can lower latency. However, CDC does not eliminate duplicates, ordering concerns, or schema compatibility issues.

You still must manage:

- Connector offsets/checkpoints.
- Transaction log retention.
- Restarts and resnapshots.
- Schema history.
- Connector lag.
- Permissions to read transaction logs.
- Backpressure when the broker slows down.
- Duplicates when a connector replays after restarting.

If a connector stays down longer than transaction log retention, a resnapshot or dedicated recovery procedure may be required. Never treat CDC as a "turn it on and get exactly-once" service.

### 11.1. Polling or CDC?

| Criterion | Polling Publisher | CDC Publisher |
|---|---|---|
| Initial complexity | Lower | Higher |
| Latency | Tied to polling interval | Typically lower |
| Database query load | Polling/index scans | Reads transaction log/change stream |
| Offset management | Leases and outbox row state | Connector offsets/checkpoints |
| Operations | Workers and retries | Connectors, log retention, and recovery |
| Best fit | Small/medium systems wanting full control | High throughput or low-latency requirements |

No single option fits every system. Starting with polling is reasonable when load is modest; move to CDC when metrics show polling load or latency is no longer acceptable.

## 12. Transactional Outbox with DynamoDB and Lambda

DynamoDB does not use SQL transactions, but `TransactWriteItems` can write multiple items atomically. One request can:

- Update the order item conditioned on version.
- Put an outbox item with a unique `eventId`.
- Commit both or neither.

Example outbox item structure:

~~~json
{
  "PK": "OUTBOX#2026-11-17",
  "SK": "ORDER#order-42#VERSION#7",
  "eventId": "evt-order-42-v7",
  "aggregateId": "order-42",
  "aggregateVersion": 7,
  "eventType": "OrderStatusChanged",
  "schemaVersion": 1,
  "payload": {
    "status": "PAID"
  }
}
~~~

DynamoDB Streams can trigger a Lambda function whenever an outbox item is added. The consumer filters `INSERT` records of the outbox type and publishes or processes the event. Design partition keys, stream view types, retention, and IAM permissions according to workload.

Stream deliveries can be retried; Lambda can reprocess batches or records. Consumers/publishers still require idempotency. If the stream is the sole delivery path and records expire before processing, build alerting and recovery aligned with your storage design.

Never put outbox items in a separate system or table outside `TransactWriteItems` with the business state and assume the operation remains atomic.

## 13. Lambda as Publisher: Concurrency and Database Connections

A scheduled Lambda can poll the outbox, provided execution environments and batch sizes are bounded:

- Reserved concurrency caps total publisher invocations.
- Batch size caps rows claimed per invocation.
- Leases prevent multiple invocations from sending the same rows under normal conditions.
- Connection pools must stay small and be reused across invocations in the same execution environment.
- Timeouts must allow claiming, publishing the batch, and updating status.
- RDS Proxy or suitable connection pooling can ease connection pressure as Lambda scales.

If every Lambda environment opens many connections and publishers scale rapidly, the database can run out of connections even while the broker has plenty of capacity. Calculate total connections from max concurrency, pool size, and other workloads sharing the database.

Do not spawn hundreds of parallel publish threads inside each invocation. Choose concurrency based on broker quotas, database capacity, and ordering constraints.

### 13.1. Scheduled Polling vs. Continuous Workers

**Scheduled Lambda** fits moderate outbox volumes where periodic latency is acceptable. Prevent overlapping invocations if a batch runs longer than the schedule interval.

**Long-lived container workers** fit steady throughput or continuous polling/connection management needs. Workers still need leases, retries, and graceful shutdown.

**Managed CDC connectors** fit organizations with existing CDC infrastructure and low-latency needs. Teams must monitor connector lag and transaction log retention.

## 14. Consumers Still Need an Inbox and Idempotency

Outbox publishers can resend events after crashes. Consumers should use an inbox table or idempotency store with a unique key:

~~~sql
CREATE TABLE inbox_event (
    consumer_name VARCHAR(120) NOT NULL,
    event_id       VARCHAR(200) NOT NULL,
    processed_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Inside a consumer-side transaction:

1. Insert the inbox record with the unique key.
2. If the key already exists and the business operation already completed, treat as duplicate.
3. Update business state.
4. Write a new outbox event if the consumer emits downstream events.
5. Commit.
6. ACK/checkpoint after commit.

Unique keys must distinguish consumers or operations so independent consumers do not block one another. Inbox retention must span all possible retries, DLQ redrives, and event replays.

If a consumer calls an external API, use a provider-supported idempotency key. A local database transaction cannot automatically roll back side effects already executed in an external system.

## 15. Do Not Replace the Outbox with Post-Commit Callbacks

A common pattern is using a callback like `TransactionalEventListener` at `AFTER_COMMIT` and publishing directly. While this lowers latency, a failure window remains:

- The database commit succeeds.
- The process crashes before the callback runs or before the broker receives the event.
- No durable record exists for another publisher to retry.

You may use a post-commit callback to wake a poller or optimize latency, but the outbox record must remain the durable source of truth. If the callback is lost, the poller or CDC must still pick up the event.

## 16. Large Payloads and Sensitive Data

Outbox tables often reside inside the operational database. Oversized payloads increase write amplification, backup size, replication lag, and query costs.

For large payloads:

- Store an immutable object in object storage beforehand or via a managed workflow.
- Store the object reference, checksum, and version in the outbox.
- Ensure the object exists and is protected before the transaction commits the event referencing it.
- Configure lifecycle policies so objects are not deleted while events can still be retried/replayed.
- Have consumers verify checksums and authorization when fetching objects.

If the object upload succeeds but the database transaction rolls back, orphan objects remain and require lifecycle cleanup or garbage collection. If the database commits while the object is missing, consumers cannot process the event. Design upload, reference, and cleanup ordering explicitly.

Never put secrets, bearer tokens, or unnecessary personal data inside events. Outboxes, brokers, and DLQs can retain data far longer than the original request.

## 17. Schema Evolution and Versioning

Events can live in an outbox or broker longer than a single deployment cycle. New consumers must understand old events; new publishers must not emit payloads that break old consumers during rolling deployments.

Best practices:

- Keep `schemaVersion` and `eventType` stable.
- Prefer adding optional fields with defaults.
- Never alter the semantics of existing fields.
- Maintain backward compatibility across the retention/replay window.
- Use upcasters or adapters when schema translation is required.
- Persist the serialized event payload at transaction time rather than re-serializing from current entity state at publish time.

The final point is critical: if a publisher re-reads the current order and builds an old event from newer state, an `OrderUpdated` v5 event could accidentally carry data from version 8. The outbox should persist an event snapshot or immutable versioned reference to preserve semantics at commit time.

## 18. Cleanup, Retention, and Partitioning

An outbox table grows continuously. Establish a cleanup policy:

- Delete or archive only published events past their required retention window.
- Keep unpublished events and records under investigation.
- Never delete events merely because `attempt_count` is high.
- Use batched deletes to avoid massive transactions.
- Consider partitioning by `created_at` under high volume.
- Record audit/metrics before deletion.
- Retain enough data to support business-required replays.

If events are retained in a broker or event archive, clarify whether the outbox also serves as a long-term audit source. You can copy published events to a dedicated archive before cleanup.

Never let cleanup jobs race with publishers and delete rows holding active leases. Filter cleanly on `published_at`, lease state, and cutoff timestamps.

## 19. Security and Access Control

The outbox holds business events and must be protected like production data:

- Grant event insert permissions only to the application role.
- Grant the publisher role only outbox read access and the publish-status update permissions it needs.
- Consumers do not need direct access to the operational outbox database if they receive events via the broker.
- Encrypt the database, backups, and transport channels.
- Restrict payload read permissions.
- Do not log raw payloads containing PII or secrets.
- Audit status modifications, exports, and replay actions.
- Separate database administration privileges from event publishing privileges where appropriate.

Publishers should not have write access to business tables. Least privilege limits blast radius if a publisher is compromised.

## 20. Observing the Outbox and Detecting Backlogs

Essential metrics:

- Count of unpublished rows.
- Age of the oldest unpublished outbox event.
- Publish latency from `created_at` to `published_at`.
- Attempt counts and publish failure rate.
- Count of leased events and expired leases.
- Count of `NEEDS_ATTENTION` or quarantined events.
- Event throughput per second.
- CDC connector lag or polling cycle duration.
- Database connection usage and query latency.
- Consumer lag, duplicate rate, and downstream error rate.

A publisher might report zero errors while the backlog silently grows because publish throughput trails event creation rate. Alerting on the oldest unpublished age is usually more actionable operationally than raw row counts alone.

Logs should carry `eventId`, `aggregateId`, `aggregateVersion`, `eventType`, and publisher/worker ID. Never put `eventId` or `aggregateId` into high-cardinality metric dimensions; keep them in logs and traces.

## 21. Testing Failure Windows

The outbox must be tested at specific crash points:

| Scenario | Expected Outcome |
|---|---|
| Business update fails before commit | No outbox event exists |
| Outbox insert fails | Business update rolls back |
| Commit succeeds, application crashes | Publisher still finds the event |
| Broker rejects publish | Event remains pending and retries |
| Broker accepts event, publisher crashes before marking published | Event may be resent; consumer deduplicates |
| Lease expires while old worker is still running | Old worker cannot overwrite a newer claim |
| Consumer commits but ACK fails | Event redelivers, but side effects do not repeat |
| Two publishers claim concurrently | One row is not normally processed by two workers simultaneously |
| Earlier event version fails | Ordering policy determines whether later events wait |

Integration tests should run against a real database and broker in an isolated environment or test containers. Mocks only verify method-call logic; they do not prove transaction, locking, leasing, or acknowledgment semantics.

## 22. Transactional Outbox Rollout Process

A practical rollout path:

1. Identify business writes that currently publish events directly.
2. Define event contracts, event IDs, and aggregate versions.
3. Create the outbox table and indexes.
4. Insert outbox records inside the same transaction as business writes.
5. Implement the polling publisher or configure CDC.
6. Add leasing/claiming, retries, and attention-required states.
7. Deploy consumer idempotency before shifting traffic.
8. Test crash windows and duplicate deliveries.
9. Canary the publisher for one event type or aggregate subset.
10. Monitor outbox lag, consumer lag, and business reconciliation.
11. Migrate producers incrementally to the outbox.
12. Remove the direct publish path once no dual path remains.

If both the legacy path and outbox publish an event during transition, consumers may receive duplicates. Keep `eventId` stable or use a migration marker to avoid emitting two copies with different identities.

## 23. Common Mistakes

**Write database then publish directly:** Crashing between the two operations loses events. Write the outbox in the same transaction.

**Publish inside the database transaction:** Network calls prolong transactions and the broker does not participate in rollback. Only insert the outbox inside the transaction; publish after commit.

**Using `AFTER_COMMIT` callbacks instead of an outbox:** Callbacks may not run after a process crash. Persist a durable outbox record.

**Marking published before broker acknowledgment:** Events can be lost. Mark published only after acknowledgment.

**Assuming publishers never send duplicates:** Crashing after sending causes duplicates. Consumers must be idempotent.

**Running multiple publishers without leases:** Two workers can send the same row simultaneously. Use row locks, `SKIP LOCKED`, or equivalent claiming.

**Leases that are too short:** Another worker reclaims while the first publish is still running. Configure realistic timeouts/leases and support renewal if needed.

**Ignoring per-aggregate ordering:** Parallel publishers can emit a later version before an earlier one. Use partition keys and per-aggregate serialization.

**Rebuilding outbox payloads from current entities:** Historical events can carry newer state. Store payload snapshots or immutable references at commit time.

**Never cleaning up the outbox:** Tables bloat and indexes/queries degrade. Delete in batches after retention and only for published records.

**Retrying configuration errors infinitely:** `AccessDenied` or bad schemas will not self-heal. Classify errors and move to an attention-required state.

**Lambda publishers opening too many DB connections:** Scale-out can exhaust database connections. Cap concurrency, pool sizes, and batch sizes.

## 24. Production Checklist

- [ ] Business state and outbox records share the same database transaction.
- [ ] Repositories share the same transaction manager and datasource.
- [ ] Event IDs are stable and event contracts include `schemaVersion`.
- [ ] Event payloads accurately reflect state at commit time.
- [ ] Aggregate versions/sequences are assigned consistently.
- [ ] Publishers read only committed events.
- [ ] Publishers claim rows safely under concurrency using locks/leases.
- [ ] Broker acknowledgment occurs before marking published.
- [ ] Crashes after send are assumed capable of producing duplicates.
- [ ] Consumers have an inbox/unique constraint or idempotency store.
- [ ] Per-aggregate ordering is preserved if required by business rules.
- [ ] Retries use backoff, jitter, and error classification.
- [ ] Failed records move to an investigation state rather than being silently deleted.
- [ ] Outbox cleanup deletes only published records past retention.
- [ ] CDC offsets/log retention are monitored if CDC is used.
- [ ] Lambda concurrency and DB connection pools are bounded.
- [ ] Sensitive payloads are protected and never logged raw.
- [ ] Metrics track oldest unpublished age and publish lag.
- [ ] Integration tests cover rollbacks, crashes, duplicates, and ordering.
- [ ] Reconciliation verifies business state against downstream systems.

## Conclusion

The transactional outbox synchronizes data changes with events by persisting business state and event records inside the same database transaction. A separate publisher reads committed records and delivers them to queues or event buses. This eliminates the dual-write gap between databases and brokers while enabling retries after application crashes.

An outbox does not by itself create exactly-once delivery. Publishers can resend after crashes, so consumers require inboxes/idempotency; ordering must be managed via aggregate versions and partition keys. In Java serverless architectures, polling Lambdas, long-lived workers, and CDC can all act as publishers, provided leases, concurrency, database connections, retries, retention, and observability are controlled. When these boundaries are cleanly designed, systems publish events reliably while keeping business state consistent.
