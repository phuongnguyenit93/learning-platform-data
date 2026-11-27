# CQRS and Event Sourcing with GCP Data Services

An order processing system may need to record orders accurately, update inventory, display the latest status to customers, and generate revenue reports. If all read and write operations share a single data model and a single transaction, the application easily runs into bottlenecks as query diversity, asynchronous workflows, and scaling demands grow. **CQRS (Command Query Responsibility Segregation)** separates how state-changing operations are handled from how queries are served. **Event sourcing** is an approach that persists state as a sequence of immutable business events rather than storing only the latest state.

In the **GCP Architecture Design** chapter of the **CLOUD_PROVIDERS_GCP** module, this lesson combines data services such as Cloud SQL, Spanner, Firestore, BigQuery, and Cloud Storage with Pub/Sub, Dataflow, Cloud Run, or GKE to build write flows, event emission, and read-model updates. The goal is to design an architecture capable of auditing history and scaling reads without mistaking a message broker for a durable event store, and without overlooking consistency, duplicate delivery, or security requirements.

After this lesson, learners will be able to:

- Distinguish command, query, domain event, integration event, event store, and projection.
- Explain why CQRS and event sourcing are independent choices that do not have to be adopted together.
- Select GCP services for write models, event stores, event buses, and read models based on load, consistency, and cost requirements.
- Design a transactional outbox to prevent dual-write bugs when both writing to a database and publishing to Pub/Sub.
- Design event schemas, aggregate versions, optimistic concurrency, and idempotent projectors.
- Handle ordering, at-least-once delivery, replay, rebuilds, and projection lag.
- Apply CQRS in Java/Spring with Cloud SQL or Spanner, Pub/Sub, and Firestore/BigQuery.
- Recognize scenarios where event sourcing should not be used and how to adopt patterns incrementally from a monolith.
- Protect sensitive data, monitor SLOs, and plan operations and incident recovery.

## 1. Distinguishing CQRS and Event Sourcing

### 1.1. What is CQRS?

In traditional CRUD applications, the same entity/model is used both to update data and to serve many kinds of queries. CQRS separates those responsibilities:

- **Command side (write side):** receives intents to change state such as `PlaceOrder`, `CancelOrder`, or `ReserveInventory`; validates business rules and persists results to the authoritative data source.
- **Query side (read side):** answers questions such as “what status is this order in?” or “what are the top 10 best-selling products?” using a read model optimized for queries.

CQRS does not strictly require two databases, two microservices, or asynchronous processing. A monolith can separate command handlers and query handlers while still sharing one database. When read and write requirements diverge substantially, it can expand into separate storage models and services.

Examples:

| Operation | Responsibility | Appropriate Model |
|---|---|---|
| Create order | Command | Order aggregate validating pricing and inventory |
| Cancel order | Command | Validating current state and cancellation rights |
| View order details | Query | Document/row optimized by `orderId` |
| List customer orders | Query | Indexed by `customerId` and timestamp |
| Monthly revenue report | Query | Analytical/aggregate tables in BigQuery |

The goal of CQRS is choosing the right storage and query patterns, not splitting every operation dogmatically in small applications.

### 1.2. What is Event Sourcing?

In a conventional state-update model, an `orders` table stores the current state, e.g., `status=PAID`. Event sourcing stores the sequence of business events that occurred:

1. `OrderPlaced`
2. `PaymentAuthorized`
3. `OrderPaid`
4. `OrderShipped`

Current state is reconstructed by applying events in order for the aggregate. Events must describe **what has happened**, not a future command.

Examples:

| Command | Resulting Event | State After Apply |
|---|---|---|
| PlaceOrder | OrderPlaced | CREATED |
| AuthorizePayment | PaymentAuthorized | PAYMENT_AUTHORIZED |
| CapturePayment | OrderPaid | PAID |
| ShipOrder | OrderShipped | SHIPPED |

The event store is the **source of truth** for state in an event-sourced design. Current-state tables, caches, or read documents can be regenerated from the event sequence if the event store is complete and projection rules remain compatible.

### 1.3. Two Independent Patterns

| Model | CQRS | Event Sourcing | When to Use |
|---|---|---|---|
| Simple CRUD | No | No | Small apps, simple queries, or low mutation complexity |
| CQRS with state-based writes | Yes | No | Multiple read models needed without storing every domain event |
| Event-sourced aggregate | Optional | Yes | Business audit/replay needed, multiple consumers, full change history |
| CQRS + event sourcing | Yes | Yes | Event-backed write model; multiple projections serving reads |

**There is no rule saying “if you use CQRS, you must use event sourcing”.** A transactional outbox on a CRUD table can publish integration events to build read models without turning the write model into event sourcing.

## 2. Foundational Concepts

| Concept | Meaning | Responsibility |
|---|---|---|
| Command | Request to change state; may be rejected | Validate, authorize, enforce invariants |
| Aggregate | Consistency boundary for a group of business data | Decide valid events based on current state |
| Domain event | A business event that occurred | Record an immutable fact, e.g., `OrderPaid` |
| Event store | Durable event repository keyed by aggregate and version | Atomic append, concurrency, replay |
| Integration event | Public contract across services/bounded contexts | Schema compatibility and distribution |
| Event bus | Message transport channel | Fan-out, retries, subscriptions, delivery |
| Projection | Function transforming events into query-friendly data | Idempotency, versioning, rebuilds |
| Read model | Table/document/index serving queries | Optimize latency, shape, and search |
| Snapshot | Materialized state at a given version | Speed up aggregate hydration |
| Checkpoint | Consumer/projection progress marker | Restart and resume processing |

An internal domain event does not automatically correspond one-to-one with an external integration event. You may need to transform, strip sensitive data, or combine events to keep integration contracts stable.

### 2.1. Aggregates and Invariants

An aggregate should not mechanically mirror every database table. It is the boundary of rules requiring immediate consistency. For example, an order cannot transition from `CANCELLED` to `SHIPPED`; the handler must inspect the order's event stream before appending `OrderShipped`.

A transaction checking stock across multiple warehouses may span beyond a single aggregate. Do not assume event sourcing creates distributed transactions across every service. Use workflows/Sagas, reservations, compensation, or adjust aggregate boundaries if business rules demand it.

### 2.2. Event Metadata

An event should contain at least:

~~~json
{
  "eventId": "evt-2d7a...",
  "eventType": "OrderPaid",
  "schemaVersion": 2,
  "aggregateType": "Order",
  "aggregateId": "ord-1042",
  "aggregateVersion": 3,
  "occurredAt": "2026-11-19T08:15:00Z",
  "commandId": "cmd-8ab1...",
  "correlationId": "req-719...",
  "causationId": "evt-bb33...",
  "payload": {
    "paymentReference": "pay-ref-123",
    "currency": "VND",
    "amountMinor": 259000
  }
}
~~~

These IDs are illustrative only. Do not rely solely on event timestamps for ordering, as producer clocks can skew. `aggregateVersion` enforced by the event store detects conflicts and preserves ordering within an aggregate.

## 3. General CQRS + Event Sourcing Architecture on GCP

~~~mermaid
flowchart LR
    Client[Client / API caller] --> Command[Command API - Cloud Run]
    Command --> Store[(Event store - Cloud SQL / Spanner)]
    Store --> Relay[Outbox relay / CDC]
    Relay --> Bus[Pub/Sub topic]
    Bus --> P1[Projection worker]
    Bus --> P2[Analytics stream]
    P1 --> Read[(Firestore / Cloud SQL read model)]
    P2 --> Flow[Dataflow]
    Flow --> BQ[(BigQuery)]
    Read --> Query[Query API - Cloud Run]
    Query --> Client
    Store --> Archive[(Cloud Storage backup / archive)]
~~~

The layers have clear responsibility boundaries:

1. **Command API:** authenticates, validates inputs, enforces policies and aggregate logic.
2. **Event store:** transactionally appends events with version control; stores authoritative history.
3. **Outbox/relay:** moves events out of the database post-commit without dropping facts.
4. **Pub/Sub:** distributes integration events to multiple independent consumers.
5. **Projection:** updates read models, supporting reprocessing and duplicate suppression.
6. **Query API:** serves data from projections; never treats projections as the source of truth for commands.
7. **Analytics:** uses Dataflow/BigQuery for aggregation; never places BigQuery on the hot invariant-checking write path.

An event store should not merely be a Pub/Sub topic. Pub/Sub is a transport service holding messages according to retention/seek policies; it does not inherently provide a lossless business history store for the entire domain lifetime, per-aggregate optimistic concurrency, or full replay of every version from the beginning. The event store must be designed separately.

## 4. Mapping Each Component to GCP Services

| Role | Commonly Considered Services | Evaluation Points |
|---|---|---|
| Command API | Cloud Run service, GKE | Auth, timeouts, concurrency, transactions, SLA |
| Transactional write/event store | Cloud SQL PostgreSQL/MySQL, Spanner | ACID, optimistic concurrency, throughput, regions, and cost |
| Document-shaped event data | Firestore | Document transactions, hot documents, query patterns |
| Outbox relay | Cloud Run Jobs/service, GKE worker, CDC/Datastream where fitting | Polling, claiming, checkpointing, retries |
| CDC | Spanner change streams, Datastream for supported sources | Row changes, latency, retention, schema mapping |
| Event distribution | Pub/Sub | At-least-once delivery, ordering keys, retries, DLQ |
| Projection worker | Cloud Run, Cloud Run functions, GKE, Dataflow | Idempotency, checkpoints, throughput |
| Operational read model | Firestore, Cloud SQL, Spanner | Query patterns, indexes, latency, consistency |
| Analytics read model | BigQuery | Scan cost, ingest latency, BI/aggregates |
| Archive / snapshot export | Cloud Storage | Durability, lifecycle, access control, backups |
| Observability | Cloud Logging, Monitoring, Trace | Lag, errors, correlation, SLOs |

### 4.1. Cloud SQL for Write Models and Event Stores

Cloud SQL fits Java/Spring systems with relational domain models requiring clear transactions and write scales that do not yet demand Spanner. A minimal event store has an `events` table with a unique key on (`aggregate_id`, `version`) and transactional appends.

Advantages include SQL, JDBC/Spring Transactions, migration tooling, and widespread operational familiarity. Watch connection pooling, instance HA/backups, single-instance throughput, storage, read replicas, and partitioning/archiving strategies as events grow.

### 4.2. Spanner for High-Scale Transactions and Multi-Region Distribution

Spanner provides a distributed transactional database with strong consistency and configurable scaling. It fits when data volume, throughput, or multi-region availability requirements make Cloud SQL a critical bottleneck.

You can store events by aggregate and sequence in Spanner, design primary keys to avoid hotspots, and use an outbox or change streams to propagate changes elsewhere. **Spanner change streams are CDC capturing row/column mutations**—they do not by themselves define which events are business facts, nor do they replace long-term event storage. Change streams have finite retention; do not use them as the complete event-sourcing history.

### 4.3. Firestore for Document-Based Read Models

Firestore fits projections queried by document key, collection, or index, such as `order-summary/{orderId}` or `customer-orders/{customerId}/...`. It can serve mobile/web clients and APIs retrieving denormalized documents.

Manage read/write/index costs, security rules, transaction limits, document size, hot documents, and schema/version evolution as projections change. Firestore real-time listeners drive UI updates—**not an event store**. Triggers from Firestore document changes can arrive more than once without ordering guarantees; handlers must be idempotent if used to update projections.

### 4.4. BigQuery for Analytical Read Models

BigQuery fits revenue reporting, funnel analysis, cohorts, or large time-series datasets. Use Pub/Sub/Dataflow, Datastream, or batch pipelines to load events/read models into BigQuery.

BigQuery is not designed for ultra-low-latency single-order state reads/writes, immediate invariant checks, or OLTP-style transactional updates. Separate transactional query APIs from analytics queries so scan latency and costs stay off the main request path.

### 4.5. Cloud Storage for Archives and Backups

Event exports, snapshots, manifests, schemas, and backups can be stored in Cloud Storage per policy. GCS provides durable object storage, not atomic versioned appends per aggregate. When using GCS as an archive, establish immutable file formats, checksums, partitioning, catalogs, and procedures to restore files into event stores or read models.

## 5. Designing the Event Store

A minimal event store must solve four problems: atomic appends, per-aggregate ordering, preventing invalid concurrent writes, and auditable replay.

### 5.1. PostgreSQL Schema Example

~~~sql
CREATE TABLE domain_events (
    event_id         UUID PRIMARY KEY,
    aggregate_type   VARCHAR(100) NOT NULL,
    aggregate_id     VARCHAR(128) NOT NULL,
    aggregate_version BIGINT NOT NULL CHECK (aggregate_version > 0),
    event_type       VARCHAR(120) NOT NULL,
    schema_version   INTEGER NOT NULL CHECK (schema_version > 0),
    occurred_at      TIMESTAMPTZ NOT NULL,
    command_id       VARCHAR(128) NOT NULL,
    correlation_id   VARCHAR(128),
    payload          JSONB NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_aggregate_version
        UNIQUE (aggregate_type, aggregate_id, aggregate_version),
    CONSTRAINT uq_aggregate_command
        UNIQUE (aggregate_type, aggregate_id, command_id)
);

CREATE INDEX idx_events_replay
    ON domain_events (aggregate_type, aggregate_id, aggregate_version);
~~~

The unique constraint on command only fits if each command emits at most one event. If a single command emits multiple events, design a separate idempotency table or use `command_id + event_index`. Do not blindly copy the constraint above when a domain has multi-event commands.

The key element is `UNIQUE (aggregate_type, aggregate_id, aggregate_version)`: two handlers reading version 5 and both attempting to append version 6 cannot both commit. The failing handler must reload the aggregate and return a conflict error or retry the command per policy—never overwrite arbitrarily.

### 5.2. Appends and Optimistic Concurrency

A command-handling sequence:

1. Receive command carrying `commandId` to prevent retries from causing duplicate effects.
2. Load the aggregate's events/snapshot.
3. Apply events to reconstruct state and obtain current version.
4. Validate authorization, state transitions, and invariants.
5. Produce one or more new events with sequential next versions.
6. Within one database transaction, append events and insert corresponding outbox rows.
7. Commit; the relay subsequently publishes integration events.
8. Return `aggregateId`, `newVersion`, or an expected read token.

To block duplicate commands, persist `commandId` in a durable idempotency store with a unique constraint inside the same transaction as the event append. Checking “have I seen this command?” in a cache alone is insufficient because two concurrent requests can both pass the check.

### 5.3. Source of Truth and Current State

In pure event sourcing, the event store is the source of truth. An `aggregate_current_state` table may act as a projection/materialized state to speed up loading, but must never be ad-hoc mutated into a competing source of truth without synchronization rules.

If choosing CRUD + CQRS, the write table remains the source of truth while the outbox emits integration events. Document clearly which model is implemented; do not label every audit table or CDC feed as event sourcing.

## 6. Avoiding Dual Writes with a Transactional Outbox

This is a common design mistake:

~~~text
1. UPDATE orders SET status = 'PAID' ...; COMMIT;
2. Publish OrderPaid to Pub/Sub;
~~~

If the process crashes after commit and before publish, the database records the order as paid while read models/consumers never receive the event. Reversing the order—publishing before commit—is equally dangerous: subscribers may process an event for a transaction that later rolls back.

### 6.1. Outbox Persisted in the Same Transaction

Instead of publishing directly, the command handler writes state/events and an outbox record within **the same database transaction**:

~~~sql
CREATE TABLE outbox_events (
    event_id        UUID PRIMARY KEY,
    aggregate_id    VARCHAR(128) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_type      VARCHAR(120) NOT NULL,
    payload         JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at    TIMESTAMPTZ,
    attempts        INTEGER NOT NULL DEFAULT 0
);
~~~

~~~mermaid
sequenceDiagram
    participant C as Client
    participant H as Command handler
    participant DB as Cloud SQL / Spanner
    participant R as Outbox relay
    participant P as Pub/Sub
    participant W as Projection
    C->>H: PayOrder(commandId)
    H->>DB: BEGIN; event/state + outbox; COMMIT
    DB-->>H: Commit OK
    H-->>C: Accepted + aggregateVersion
    R->>DB: Read unprocessed outbox
    R->>P: Publish OrderPaid
    P-->>R: Publish acknowledged
    R->>DB: Mark published/checkpoint
    P-->>W: Deliver event (may repeat)
    W->>W: Deduplicate + apply
~~~

Rules:

- Outbox records must include a stable ID, `eventType`, `aggregateId`, version, and `schemaVersion`.
- Return command success only after the event + outbox transaction commits.
- The relay retries failed publishes with backoff, metrics, alerts, and retry limits.
- Outbox rows are deleted/archived per retention policy once safely checkpointed.
- Publishing may succeed while the relay crashes before marking `published_at`: the next run may republish. Consumers **must be idempotent**.

A transactional outbox prevents dropped events between database commit and message publication, yet **does not provide end-to-end exactly-once business processing**.

### 6.2. Polling Relay or CDC

| Mechanism | How It Works | Pros / Cons |
|---|---|---|
| Polling relay | Worker queries unpublished outbox rows, claims a batch, and publishes | Easy to understand; requires locking, batch sizing, lag monitoring |
| Database CDC | Reads row/table changes from logs or change streams | Eliminates polling; adds connectors, schema mapping, and operational overhead |
| Spanner change streams | Change records written atomically with database transactions | Integrates well with Spanner; retention/connectors must be designed |
| Datastream | CDC/replication from supported databases to destinations like BigQuery/GCS | Strong for replication; publishing domain events requires an explicit transformation pipeline |

Do not treat every mutation in the `orders` table as a business event. An `UPDATE` could stem from a migration, manual operational fix, or batch job. For stable inter-service contracts, emit **outbox domain integration events** explicitly rather than exposing raw row-level CDC to consumers.

### 6.3. Claiming Outbox Rows Safely with Multiple Relays

With Cloud SQL PostgreSQL, `SELECT ... FOR UPDATE SKIP LOCKED` in a short transaction can claim batches so two workers avoid claiming the same rows. Avoid holding a database transaction open across multi-second network publishes, as that raises lock contention; use claim tokens/leases and update status after publishing, or an equivalent checkpointing mechanism.

Duplicates must still be tolerated if a worker loses its lease or a publish success is not recorded. Scaling relay replicas does not replace idempotency.

## 7. Event Distribution with Pub/Sub

Pub/Sub excels at fanning out events to multiple projections/consumers: order tables for APIs, statistics updates, notifications, and analytics pipelines. Give each consumer group its own subscription so acks from one group never drop messages for another.

### 7.1. Delivery Semantics

Pub/Sub defaults to **at-least-once delivery**, so subscribers can receive the same message multiple times due to ack deadlines, retries, or network errors. Never count revenue twice just because two `OrderPaid` messages arrived.

Pub/Sub offers optional **exactly-once delivery** for pull subscriptions within a single region, but that is a delivery/ack guarantee per Pub/Sub-assigned message ID. It does not stop a producer from publishing the same business event as two distinct message IDs, nor does it join downstream database updates into a shared transaction with Pub/Sub. Still deduplicate by `eventId` and enforce idempotency where results are written.

### 7.2. Per-Aggregate Ordering

If a subscriber needs `OrderPlaced`, `OrderPaid`, and `OrderShipped` in order for a single order, you can:

- Set `orderingKey = aggregateId` when publishing.
- Enable message ordering on the subscription.
- Publish messages sharing an ordering key from the same region and coordinate multi-instance publishers.
- Persist `aggregateVersion` and reject or park out-of-order version gaps in the projector.

Pub/Sub does not guarantee global ordering across all aggregates. Ordering keys apply only per key under supported service conditions. When an older message is redelivered, subsequent messages with the same key may also be redelivered. Projectors must handle replay/deduplication.

If using Dataflow to read Pub/Sub, do not assume ordering keys are automatically preserved across an entire Apache Beam pipeline. Implement stateful processing keyed by aggregate/version or add appropriate checkpoints and ordering guards.

### 7.3. Retries, DLQ, and Poison Message Handling

Configure:

- Ack deadlines/lease extensions matching projector processing time.
- Retries with exponential backoff and jitter.
- A dead-letter topic for events exceeding maximum delivery attempts.
- Alerts on oldest unacked message age, backlog size, and DLQ count.
- A workflow to fix bugs and re-drive/republish events with idempotency safeguards.

Poison events caused by incompatible schemas or invalid payloads must be quarantined for investigation rather than retried infinitely, which stalls an ordering key and blocks subsequent events.

## 8. Building Read Models and Idempotent Projectors

A projection transforms events into query-friendly structures:

~~~text
OrderPlaced(orderId, customerId, total) -> order_summary:
  status = CREATED, total = total

OrderPaid(orderId, paidAt) -> order_summary:
  status = PAID, paid_at = paidAt

OrderShipped(orderId, tracking) -> order_summary:
  status = SHIPPED, tracking = tracking
~~~

One event can update multiple projections with different speeds and goals. For instance, `order_summary` for an API needs low latency, while `sales_analytics` in BigQuery requires accurate reporting and can tolerate higher lag.

### 8.1. Idempotency at the Target Database

If the projector writes to Cloud SQL, store a processed-events ledger and projection data in the same transaction:

~~~sql
CREATE TABLE processed_events (
    projector_name VARCHAR(100) NOT NULL,
    event_id       UUID NOT NULL,
    processed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (projector_name, event_id)
);

CREATE TABLE order_summary (
    order_id       VARCHAR(128) PRIMARY KEY,
    status         VARCHAR(32) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    total_minor    BIGINT,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Within one transaction:

1. `INSERT` into `processed_events` with `(projector_name, event_id)`.
2. On conflict, it is likely an already-processed duplicate; skip the update.
3. Check the order's current version.
4. Apply the event to update `order_summary`.
5. Commit before acknowledging the message.

Without an atomic transaction spanning the deduplication ledger and projection state, an event might be marked processed while the read-model update failed. With Firestore, use transactions across related documents (within service limits) or store a `lastAppliedVersion` for idempotent updates. Never assume recording an event ID first and writing projection data in two separate API calls is atomic.

### 8.2. Version Gaps and Reordering

Suppose a projector has applied version 5 of an order and receives version 7 before version 6. Do not jump straight to version 7 if calculations depend on prior history. You can:

- Park version 7 and wait for version 6.
- Query the event store to backfill the missing event.
- Apply an idempotent reducer if the domain permits out-of-order handling.
- Route to a DLQ/repair workflow after a controlled timeout.

Checkpoints should be reasoned about per aggregate and event source; they do not replace per-event idempotency checks.

### 8.3. Diverse Read Models

| Query | Suitable Projection | Service |
|---|---|---|
| Fetch single order status by ID | Small key-value document | Firestore or Cloud SQL |
| Customer order list over time | Indexed by `customerId`/`createdAt` | Firestore / Cloud SQL |
| Current stock per SKU | Aggregate/versioned row | Cloud SQL / Spanner |
| Revenue by day, channel, region | Fact table / aggregates | BigQuery |
| Business audit history lookup | Event view / audit projection | Event store + dedicated API |

Design read models around actual query patterns. Avoid creating one massive denormalized table for all queries if it creates bottlenecks or unmanageable redundancy.

## 9. Eventual Consistency and User Experience

In asynchronous CQRS, the command side may commit in 50 ms while a projector takes several hundred milliseconds or longer to update the read model. A user may complete payment yet briefly see the old status on the list view.

An API should establish a clear contract:

~~~http
POST /orders/ord-1042/pay
Idempotency-Key: cmd-8ab1

HTTP/1.1 202 Accepted
Location: /orders/ord-1042
Retry-After: 1
X-Aggregate-Version: 3
~~~

Status 202 fits when processing is genuinely asynchronous per contract. If the command already committed business state synchronously, returning 200/201/204 per API contract is fine while documenting projection lag.

Strategies:

- **Read-your-writes:** after a command, return the updated state/aggregate version directly from the write path in the response instead of immediately polling a stale read model.
- **Version tokens:** queries can accept `minVersion` and wait briefly up to a timeout for the projection to catch up.
- **Optimistic UI:** show transitional state with a syncing indicator.
- **Polling/SSE/WebSocket:** notify clients once the projection updates.
- **Fallback:** for critical queries, read the write model in a controlled way if the read model lags, weighing cost and CQRS boundaries.

Set explicit SLOs for projection freshness, e.g., “99% of events appear in `order_summary` within 3 seconds” based on real measurements. Avoid saying “real time” without specifying latency percentiles and timeout behavior.

## 10. Replay, Rebuilds, and Snapshots

Event sourcing enables rebuilding state from history, yet replays must be designed and tested.

### 10.1. When is replay needed?

- Creating a new projection from historical events.
- Fixing a reducer bug that corrupted a read model.
- Migrating data to a new schema or read-model service.
- Recovering a projection after data loss.
- Backfilling analytics over a time range.

### 10.2. Safe Rebuild Procedure

1. Verify the event store contains complete history and required schema versions.
2. Create the new read model under a separate name/table/collection rather than overwriting live production data in place.
3. Read events ordered by aggregate and version, running tested reducer code.
4. Catch up on incoming events concurrently or align on a consistent checkpoint.
5. Compare record counts, hashes/summaries, and business invariants between new and old projections.
6. Cut over the query API to the new projection via versioning/aliases/feature flags.
7. Retain a rollback window before retiring the old projection.

If replay triggers side effects like sending emails or charging payments, **never invoke side-effect handlers during replay**. Reducers must be pure deterministic state functions; external effects belong to isolated consumers guarded against replay.

### 10.3. Snapshots

An aggregate with hundreds of thousands of events is expensive to reload from event #1. Store a snapshot at version N and replay only events from N+1 onward.

Snapshots must include aggregate ID, version, schema version, checksum, and materialized state. Snapshots are regenerable optimization data—never a replacement for the event store unless the domain intentionally designs a retention/compaction policy.

### 10.4. Replay Does Not Mean Infinite Pub/Sub Replay

Pub/Sub supports retention/seek/snapshots within service and configuration bounds; it does not store events forever by default. If your domain needs multi-year history, keep an independently recoverable event store or archive. Spanner change streams also have short retention (typically up to 30 days per documentation); never treat them as a long-term replay source.

## 11. Schema Evolution and Event Contracts

Immutable events mean you do not arbitrarily rewrite historical payloads on every model release. You must manage versions and compatibility.

### 11.1. Core Rules

- Name `eventType` with stable business meaning.
- Add new fields in a backward-compatible way whenever possible.
- Readers should tolerate unknown new fields and supply safe defaults for optional fields.
- Never alter the semantics of an existing field while keeping the same `schemaVersion`.
- For breaking changes, introduce a new event version and controlled migrations/upcasters.
- Test replays against multi-version historical payloads, not only the newest events.
- Maintain contract tests between producers and consumers when multiple teams share integration events.

For example, `OrderPlaced.v1` has `totalMinor`; `OrderPlaced.v2` adds `currency`. If historical v1 events lack `currency`, an upcaster may supply a default only when a genuine domain rule holds (e.g., all v1 orders were VND). Never fabricate a default currency if legacy data was multi-currency.

### 11.2. Domain Events vs. Integration Events

Domain events can hold fine-grained details for the aggregate. Public integration events should expose only what consumers need, with explicit contract versioning and PII policies. The outbox relay can translate domain events into integration events before publishing.

When a producer must evolve a schema, identify dependent consumers and coordinate dual-publishing or migration steps. Never let another service query your internal tables directly, as that breaks ownership boundaries.

## 12. Java/Spring: Command Handler and Projector Skeletons

The snippets below illustrate design concepts; repository adapters, DTOs, idempotency DDLs, and error mappings must be implemented fully in a real project.

### 12.1. Aggregate Reducer

~~~java
sealed interface OrderEvent permits OrderPlaced, OrderPaid, OrderShipped {}

record OrderPlaced(String orderId, long totalMinor) implements OrderEvent {}
record OrderPaid(String orderId, String paymentReference) implements OrderEvent {}
record OrderShipped(String orderId, String trackingCode) implements OrderEvent {}

record OrderState(String orderId, String status, long totalMinor, long version) {
    static OrderState empty(String orderId) {
        return new OrderState(orderId, "NONE", 0, 0);
    }
}

final class OrderReducer {
    static OrderState apply(OrderState state, OrderEvent event) {
        return switch (event) {
            case OrderPlaced e -> new OrderState(
                    e.orderId(), "CREATED", e.totalMinor(), state.version() + 1);
            case OrderPaid e -> new OrderState(
                    e.orderId(), "PAID", state.totalMinor(), state.version() + 1);
            case OrderShipped e -> new OrderState(
                    e.orderId(), "SHIPPED", state.totalMinor(), state.version() + 1);
        };
    }
}
~~~

This uses switch pattern matching on supported Java versions, appropriate for modern verified JDKs. Real reducers must validate versions, identities, and transitions—never allow a stray event to transition `NONE -> SHIPPED`.

### 12.2. Command Handler with Spring Transaction

~~~java
@Service
public class PayOrderHandler {
    private final EventStore eventStore;
    private final OutboxRepository outbox;
    private final CommandDedupRepository dedup;

    public PayOrderHandler(
            EventStore eventStore,
            OutboxRepository outbox,
            CommandDedupRepository dedup) {
        this.eventStore = eventStore;
        this.outbox = outbox;
        this.dedup = dedup;
    }

    @Transactional
    public long handle(PayOrder command) {
        // Unique constraint on commandId prevents two concurrent requests from writing.
        dedup.registerOrThrow(command.commandId());

        OrderAggregate order = eventStore.load(command.orderId());
        order.requireCanPay();

        OrderPaid paid = new OrderPaid(
                command.orderId(), command.paymentReference());
        long version = eventStore.append(
                command.orderId(), order.version(), paid);

        outbox.insert(
                command.eventId(), command.orderId(), version,
                "OrderPaid", command.toIntegrationPayload());
        return version;
    }
}
~~~

`EventStore.append` must enforce optimistic concurrency via DB constraints or conditional writes inside the same transaction. Dedup and outbox DDLs must also participate in the event store's transaction. If `eventStore` and `outbox` live in separate databases/services, `@Transactional` on a single `DataSource` will not create an atomic distributed commit—redesign the transaction boundary or use an equivalent guarantee.

Conflicts can map to HTTP 409 or trigger a reload-and-retry per policy; repeating the same `commandId` should return the stored idempotent outcome rather than charging twice.

### 12.3. Idempotent Projector

~~~java
@Service
public class OrderSummaryProjector {
    private final ProcessedEventRepository processed;
    private final OrderSummaryRepository summaries;

    public OrderSummaryProjector(
            ProcessedEventRepository processed,
            OrderSummaryRepository summaries) {
        this.processed = processed;
        this.summaries = summaries;
    }

    @Transactional
    public void onEvent(IntegrationEvent event) {
        // insertIfAbsent returns false when the event was already committed previously.
        if (!processed.insertIfAbsent("order-summary-v2", event.eventId())) {
            return;
        }

        OrderSummary summary = summaries.loadForUpdate(event.aggregateId());
        long expected = summary == null ? 1 : summary.version() + 1;
        if (event.aggregateVersion() != expected) {
            // Roll back the processed event as well so it can be retried/repaired.
            throw new ProjectionVersionGapException(
                    event.aggregateId(), expected, event.aggregateVersion());
        }
        summaries.apply(event);
    }
}
~~~

This is an illustrative skeleton. In production, verify whether `insertIfAbsent` and `apply` share the same transaction/connection, how concurrent rows are locked, how duplicate older versions are handled, and how projections initialize. Acknowledge Pub/Sub **after** the projection transaction commits. On failure, messages retry or move to the DLQ per policy.

## 13. Dataflow and BigQuery for Analytical Read Models

At millions of events per day, a simple projector may not suffice for windowed aggregations, schema conversions, and analytics throughput. Dataflow (Apache Beam) can read Pub/Sub/CDC, parse, enrich, deduplicate, and write to BigQuery or other storage.

### 13.1. Logical Pipeline

~~~mermaid
flowchart LR
    Events[Pub/Sub integration events] --> DF[Dataflow pipeline]
    DF --> Validate[Schema validation + eventId]
    Validate --> Transform[Enrich / window / aggregate]
    Transform --> BQ[BigQuery dataset]
    Validate --> Bad[Invalid events quarantine]
    BQ --> BI[BI / analytics queries]
~~~

Dataflow supports exactly-once processing within the pipeline under matching modes, yet external side effects or sinks lacking matching semantics can still receive duplicates. Never rely on the phrase "exactly-once" to omit idempotency/dedup at database boundaries.

### 13.2. BigQuery Design

An event analytics table can include `eventId`, `eventType`, `aggregateId`, `aggregateVersion`, `occurredAt`, `ingestedAt`, and approved business fields. Partition by event time or ingestion time as fitting, cluster by hot query keys, set retention policies, and monitor scan costs.

When reporting financial figures, decide how duplicate and compensating/correction events are handled. A raw `COUNT(*)` over raw events will be inaccurate if publishers emit duplicates or streams are replayed. Use deduplicated views/tables keyed by `eventId` or versioned projection-backed materialized aggregates.

## 14. Security, Auditing, and Sensitive Data

Long-lived event sourcing increases the risk of retaining sensitive information unnecessarily.

### 14.1. Data Minimization

- Store only fields required for business semantics and replay.
- Never store passwords, access tokens, card PANs, secret keys, or sensitive financial credentials in plaintext.
- Use tokens/references or appropriate encryption for sensitive fields.
- Separate PII from immutable events if regulations require deleting or editing PII.
- Design retention, access controls, legal holds, and data-subject-request workflows before writing events to long-term storage.

“Immutable events” never excuse ignoring legal data-deletion rights. Use crypto-shredding, externalized payloads, redaction/tombstones, or appropriate retention policies depending on data class and compliance rules; review with security/legal teams alongside projection rebuild capabilities.

### 14.2. IAM and Networking

| Component | Least-Privilege Permissions |
|---|---|
| Command service | Write to its domain's event store and outbox |
| Outbox relay | Read/claim outbox rows, publish to the specific Pub/Sub topic |
| Projection worker | Subscriber on its dedicated subscription, write to its specific read model |
| Query service | Read-only access to read models; no event-append rights |
| Dataflow worker | Read subscription and write to the specific BigQuery dataset |
| Auditor | Read-only access to event history per policy; cannot mutate payloads |

Cloud Run/GKE should use dedicated workload identities/service accounts; avoid static JSON keys. Databases use private connectivity, TLS, and IAM database authentication where fitting; keep secrets in Secret Manager. Logs and traces must exclude sensitive event payloads.

### 14.3. Auditing and Evidence

Event sourcing aids business traceability, yet **never replaces Cloud Audit Logs** for infrastructure admin/IAM/API actions. Record who initiated each command, `correlationId`, version, commit timestamp, and event source; never blindly trust client-supplied values for these fields. Servers must authenticate identities and generate trustworthy audit metadata.

## 15. Observability and SLOs for CQRS

A CQRS system can return command success while read models stall; monitoring only the command API is insufficient.

### 15.1. Key Metrics

| Metric | Meaning | Anomaly Signal |
|---|---|---|
| Command latency p95/p99 | Transaction confirmation time | Database contention/locks/quotas |
| Command conflict rate | Version/idempotency conflicts | Hot aggregates, retry storms |
| Outbox oldest unpublished age | Delay before events leave DB | Relay failure or backlog |
| Publish error/retry count | Relay/Pub/Sub issues | IAM, quotas, networking |
| Pub/Sub oldest unacked age | Subscription backlog | Consumer throughput drop |
| Projection lag p95/p99 | Time from event commit to read-model update | Freshness SLO breach |
| Version gap / DLQ count | Missing events or schema errors | Ordering, logic, poison events |
| Replay throughput/checkpoint | Rebuild progress | Rebuild stalled or too slow |
| Read query latency | Query user experience | Indexes/capacity/read-model bottlenecks |
| Duplicate suppression count | Events skipped via idempotency | Retries/publisher duplication |

Cloud Logging/Monitoring/Trace tie a request `correlationId` across commands, database transactions, outbox relays, Pub/Sub messages, and projectors. Avoid high-cardinality labels in metrics systems; keep granular IDs inside access-restricted traces/logs.

### 15.2. Error Budgets and Alerts

Example SLOs:

- 99.9% of valid commands commit within the target time.
- 99% of `order-summary` projections catch up to new events within 3 seconds.
- Zero lost committed events (proven by design, backups, and restore drills).
- 99.9% of query API requests succeed within latency budgets.

Thresholds are illustrative; choose them from business needs and real measurements. Alert when oldest unpublished outbox age climbs, projection lag breaches thresholds, new events enter the DLQ, or version-gap counts keep rising.

## 16. Testing a CQRS + Event Sourcing Strategy

### 16.1. Unit and Domain Tests

- Given event history → When command → Then expected new event(s) or domain error.
- Applying the same event history twice in a reducer yields deterministic state.
- Invalid state transitions are rejected.
- Every business invariant is enforced at the aggregate command boundary.
- Older event schema versions remain readable by reducers/upcasters.

### 16.2. Integration Tests on a Dedicated GCP Project

- Use real Cloud SQL/Spanner to verify atomic appends and version uniqueness.
- Simulate two concurrent commands targeting the same expected version: only one succeeds.
- Crash the relay between publish and mark-published: event is republished, yet projection does not double-apply.
- Deliver version N+2 before N+1: projector does not persist corrupted state.
- Publish duplicate business events with different Pub/Sub `messageId`s: `eventId` dedup still holds.
- Stop a worker so backlog grows, restart it, and measure catch-up.
- Send a schema-invalid poison event to the DLQ and test repair/re-drive.
- Rebuild a projection into new storage and verify invariants before cutover.

Never run full production stream stress/replay tests in a test project without clear budgets and quotas. Use synthetic data or production data sanitized per security policy.

### 16.3. Fault Injection

Test critical failure points:

| Failure Point | Invariant to Preserve |
|---|---|
| DB transaction rollback | No matching event/outbox row is treated as committed |
| Relay crashes before publish | Outbox row remains and is retried |
| Relay crashes after publish | Duplicates possible; projector stays idempotent |
| Projector commits then crashes before ack | Message redelivery causes no double effect |
| Projector receives out-of-order events | Never silently skips version gaps |
| Read store loses data | Can be rebuilt from the event store |
| Incompatible new event schema | Parked/DLQ'd with audit trail; never corrupts data |

## 17. Architecture Example: Order Processing

An e-commerce application requires:

- Never recording a payment twice.
- Clients seeing order status by ID quickly.
- Revenue reporting and customer history not slowing down the write path.
- Ability to explain why an order moved from `CREATED` to `PAID` or `CANCELLED`.

### Step 1: Choose boundaries and events

The `Order` aggregate holds `orderId`, status, total amount, and version. Commands: `PlaceOrder`, `PayOrder`, `ShipOrder`, `CancelOrder`. Events: `OrderPlaced`, `OrderPaid`, `OrderShipped`, `OrderCancelled`.

### Step 2: Choose storage

- Cloud SQL PostgreSQL serves as event store and outbox in one transaction.
- Pub/Sub topic `orders.events` distributes integration events.
- Firestore stores `order-summary` for order status queries.
- BigQuery stores fact tables for analytics via Dataflow.
- Cloud Run runs the command API, query API, and projectors; Cloud Run Jobs handles controlled replays.

This is a reference option; if high transactional scale or multi-region writes are needed, evaluate Spanner. If the app is small and needs no long-term event history, CQRS with CRUD tables + outbox may be simpler.

### Step 3: The `PayOrder` command

1. Client sends `PayOrder` with `commandId`/idempotency key.
2. Server authenticates the user and checks permissions on the Order.
3. Loads event history/snapshot and expected `aggregateVersion`.
4. Verifies payable status and valid payment reference.
5. Commits `OrderPaid` and outbox record in the same transaction.
6. Returns the new version; relay publishes integration event post-commit.

### Step 4: Projections

- `OrderSummary` projector receives `OrderPaid`, checks `eventId`/version, updates the Firestore document.
- Analytics projector routes events via Dataflow/BigQuery with `eventId` deduplication.
- Notification consumer sends email via its own workflow, using an idempotency key so Pub/Sub redeliveries never send twice.

### Step 5: Queries and user experience

Query API reads Firestore, returning status and `lastAppliedVersion`. If a client just sent a command and needs immediate feedback, display committed info from the command response or poll until `lastAppliedVersion` reaches the new version.

### Step 6: Operations and recovery

Monitor command conflicts, outbox lag, Pub/Sub backlogs, projection lag, and query latency. When a projection bug surfaces, deploy the fixed reducer, rebuild the read model into a new collection, reconcile, and switch the alias/query API. Never edit event history to “tidy up” numbers without an explicit correction process.

## 18. When NOT to Use CQRS or Event Sourcing

These patterns carry substantial architectural overhead:

- Multiple storage models and data pipelines to operate, back up, test, and monitor.
- Eventual consistency complicates UI/APIs and read logic.
- Event schemas/versions and replays demand long-term governance discipline.
- Sensitive data is harder to delete or redact inside an immutable event store.
- Duplicates, ordering, and version gaps add extra failure branches.
- Debugging requires correlation IDs and cross-service tracing.
- Large replays consume significant compute, storage I/O, and cost.

Do not adopt event sourcing solely to get an audit table or to emit Pub/Sub on every update. If you only need read replicas, indexing, or straightforward reporting, evaluate SQL/index tuning, materialized views, caching, or CDC first.

A safe incremental path:

1. Start with CRUD and clean domain boundaries.
2. Separate command/query interfaces in code if reads and writes diverge.
3. Add an outbox to emit integration events reliably.
4. Build secondary projections and measure real value.
5. Move only aggregates with strong audit/replay requirements to event sourcing.
6. Mature versioning, snapshots, replay, and observability before scaling across many bounded contexts.

## 19. Design and Implementation Checklist

### Domain and Data

- [ ] Bounded contexts and aggregate invariants are clearly defined.
- [ ] CQRS and event sourcing are chosen independently with business justification.
- [ ] Event store enforces atomic appends, ordering, and optimistic concurrency.
- [ ] Events include `eventId`, `aggregateId`, `aggregateVersion`, `schemaVersion`, and `commandId`.
- [ ] Schema evolution/upcaster strategy and contract testing exist.
- [ ] Retention, PII, and regulatory deletion policies are established.

### Messaging and Projections

- [ ] Dual writes prevented via transaction + outbox or equivalent guarantee.
- [ ] Both relay and projector have retries/backoff, checkpoints, and DLQs.
- [ ] Consumers are idempotent by `eventId`/business key.
- [ ] Ordering/version gaps are handled per aggregate.
- [ ] Each projection has clear data boundaries and ownership.
- [ ] Freshness SLOs and read-your-writes behaviors are defined.

### GCP and Operations

- [ ] Cloud SQL/Spanner/Firestore/BigQuery selected per real read/write patterns.
- [ ] Pub/Sub and change streams are not treated as permanent event stores.
- [ ] IAM and service accounts are separated across command, relay, projector, and query roles.
- [ ] Logs/traces/correlation IDs, metrics, and projection lag alerts are active.
- [ ] Backups, replays, rebuilds, reconciliation, and rollback plans exist.
- [ ] Tested for duplicates, concurrent writes, out-of-order events, replays, and fault injection.
- [ ] Long-term event storage, storage/index, Pub/Sub, Dataflow, and BigQuery costs are estimated.

## 20. Official References

- [Spanner change streams overview](https://cloud.google.com/spanner/docs/change-streams)
- [Spanner transactions](https://cloud.google.com/spanner/docs/transactions)
- [Cloud SQL documentation](https://cloud.google.com/sql/docs)
- [Datastream overview](https://cloud.google.com/datastream/docs/overview)
- [Pub/Sub subscription overview](https://cloud.google.com/pubsub/docs/subscription-overview)
- [Pub/Sub message ordering](https://cloud.google.com/pubsub/docs/ordering)
- [Pub/Sub exactly-once delivery](https://cloud.google.com/pubsub/docs/exactly-once-delivery)
- [Pub/Sub dead-letter topics](https://cloud.google.com/pubsub/docs/dead-letter-topics)
- [Cloud Run documentation](https://cloud.google.com/run/docs)
- [Firestore real-time listeners](https://cloud.google.com/firestore/native/docs/query-data/listen)
- [Firestore triggers with Cloud Run functions](https://cloud.google.com/firestore/native/docs/extend-with-cloud-run-functions)
- [Dataflow streaming modes](https://cloud.google.com/dataflow/docs/guides/streaming-modes)
- [Dataflow and Pub/Sub streaming](https://cloud.google.com/dataflow/docs/concepts/streaming-with-cloud-pubsub)
- [BigQuery documentation](https://cloud.google.com/bigquery/docs)
- [Cloud Storage lifecycle management](https://cloud.google.com/storage/docs/lifecycle)
- [Google Cloud IAM best practices](https://cloud.google.com/iam/docs/using-iam-securely)

**Conclusion:** CQRS lets you optimize write and read paths independently; event sourcing provides a replayable history of business events. On GCP, pairing Cloud SQL or Spanner for transactions, Pub/Sub for distribution, Firestore/Cloud SQL for application-facing projections, and Dataflow/BigQuery for analytics is a viable architecture when requirements genuinely justify the complexity. What determines reliability is strict source-of-truth boundaries, atomic appends/outboxes, idempotency, versioning, data security, and tested recoverability.
