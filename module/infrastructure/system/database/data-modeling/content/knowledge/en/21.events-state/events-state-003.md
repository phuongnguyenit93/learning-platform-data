# Distinguishing Domain Events, Integration Events, and Storage Change Records

## 1. Three Kinds of Information May Describe the Same Change, Yet Answer Different Questions

Suppose an e-commerce platform hands an order over to a shipping carrier. Three records might appear in the system simultaneously:

1. **Domain event**: `OrderHandedToCarrier` — fulfillment confirms the order was handed over to the carrier.
2. **Integration event**: `OrderShipmentConfirmed.v1` — the fulfillment service publishes to subscribed systems that the order has been handed over, along with data defined by the integration contract.
3. **Change Data Capture record (commonly called a CDC record)**: the database records that a row in the `orders` table changed `fulfillment_status` from `READY` to `SHIPPED`.

All three may relate to the same progression, yet they cannot be treated as three equivalent ways of writing the same thing:

- **Domain event** answers: *What business fact occurred within a domain boundary?*
- **Integration event** answers: *What business fact or outcome is communicated to other systems, under what contract?*
- **Storage change record** answers: *What technical record in the storage engine was inserted, updated, or deleted?*

Conflating them can tightly couple systems to table layouts, leak intermediate states externally, expose unnecessary data, or cause historical reports to misinterpret the meaning of an `UPDATE`.

In data modeling, distinguishing these three helps decide **which entity is the source of truth**, where business constraints live, the structure of shared messages, identifying keys, indexes, and how schemas evolve over time.

## 2. Comparing Characteristics and Scope of Use

| Criterion | Domain event | Integration event | Storage change record / CDC |
| --- | --- | --- | --- |
| **Unit of meaning** | A confirmed occurrence within the business domain. | A business notification published to consumers outside the source boundary. | A row/column change or write operation recorded at the storage layer. |
| **Example** | `OrderHandedToCarrier`. | `OrderShipmentConfirmed.v1`. | `UPDATE orders SET fulfillment_status='SHIPPED'`. |
| **Origin** | Domain/aggregate business logic after rules are satisfied. | Publishing component, often mapped from an outcome/domain event. | Transaction log mechanism, trigger, or change-capture tool. |
| **Consumers** | Logic and components inside the domain boundary; sometimes internal projections. | Other systems: notifications, reconciliation, analytics, partners. | Data sync, replicas, search indexes, data pipelines, outbox relays. |
| **Contract** | Internal ubiquitous language, invariants, and aggregate boundaries. | More public contract: versioning, access permissions, compatibility, latency. | Depends on storage schema and CDC tool metadata. |
| **Ordering** | Can be ordered within an aggregate; not globally by default. | Depends on partition key, broker, and publishing contract. | Typically log/offset ordered within a specific source; not synonymous with system-wide business order. |
| **Audit value** | Strong if semantics and history are reliably preserved. | Useful for tracing cross-system exchanges. | Accurate about recorded technical changes; may lack business reason. |
| **Data to store** | Enough data to understand the fact and protect invariants in its context. | Minimal, stable data permitted for sharing and sufficient for consumers. | Before/after images or change-log representation depending on database and configuration. |

**Important boundary:** a domain event does not have to be persisted forever; it may exist only during a transaction's execution flow. Only when **the event sequence is the primary source of truth for reconstructing state** is it called event sourcing. Likewise, having a message broker, an outbox table, or a CDC pipeline does not automatically turn a system into an event-sourced system.

## 3. Domain Events: Describing Facts and Rules Inside the Domain

A **domain event** should have a name expressing something that *has occurred* and been recognized, rather than a technical operation name. For example:

- `OrderPlaced`: a purchase request has been accepted as an order.
- `PaymentCaptured`: a payment collection has been confirmed by an authoritative source.
- `OrderHandedToCarrier`: physical handover to the shipping carrier has been confirmed.
- `RefundApproved`: a refund approval decision has passed; does not mean funds have reached the customer's account.
- `RefundCompleted`: the refund actually succeeded per defined criteria.

Do not confuse the **command** `CapturePayment` with the **event** `PaymentCaptured`. A command can be rejected due to wrong amount, exceeded limit, or invalid state. An event describes the outcome after conditions are accepted.

### Placing Events at the Right Consistency Boundary

Suppose the `Order` aggregate manages packing completion and handover state. A rule might be:

> Accept `OrderHandedToCarrier` only if the order is in `READY`, has a valid handover receipt code, and has not already recorded handover for the same parcel.

The system must enforce this invariant within the same consistency scope as the corresponding change. The order of domain events belonging to one order can be represented by `order_version` or `sequence_no`, but different orders do not implicitly share a single business order.

If **handover** operations are actually managed in an independent `Shipment` aggregate, `ShipmentHandedOver` may fit better; do not force every event into the `Order` aggregate. Base the decision on business constraints and data ownership.

An illustrative internal domain event:

~~~json
{
  "event_id": "242093fc-144d-4b3b-a027-a3cc09adb73e",
  "event_type": "OrderHandedToCarrier",
  "aggregate_type": "Order",
  "aggregate_id": "ORD-842",
  "aggregate_version": 12,
  "occurred_at": "2026-11-20T03:05:00Z",
  "actor_type": "STAFF",
  "actor_id": "STAFF-18",
  "payload": {
    "shipment_id": "SHP-331",
    "carrier_id": "CARRIER-07",
    "handover_receipt_id": "HND-945",
    "warehouse_id": "WH-HCM-02"
  }
}
~~~

The purpose of this event is to express a fact within the domain context. `aggregate_version` here is the logical version of the order, not a Kafka offset or a database-wide sequence number. `occurred_at` is the time handover was confirmed by an authoritative source; log persistence or message emission time may be later.

### What Domain Events Do **Not** Guarantee on Their Own

Good naming does not by itself guarantee valid transactions, event ordering, history persistence, replayability, or exactly-once consumer processing. Those are responsibilities of transaction design, storage mechanisms, data constraints, and message handling.

## 4. Integration Events: Shared Contracts Between Systems

An **integration event** is typically produced when a service needs to publish a confirmed outcome so other systems can react. Consumers may be notification services, customer support services, shipping partners, or analytics platforms.

Unlike internal domain events, an integration event is a **data interface that other consumers depend on**. Therefore, when naming and choosing the payload, evaluate:

1. **Stable semantics:** consumers clearly understand the published fact, the condition under which the event is emitted, and whether it is a terminal event or merely a workflow milestone.
2. **Data contract:** event name, version, message identifier, subject, timestamps, required/optional fields, enums, currency, and units of measure.
3. **Sharing permissions:** never publish internal internals, personal profiles, or confidential information if consumers do not need them.
4. **Compatibility:** the publisher can evolve its internal DB without forcing every consumer to change immediately.
5. **Delivery:** specify idempotency, retries, late-arrival tolerance, which key governs ordering, and error handling.

Example integration message transformed from the domain event above:

~~~json
{
  "message_id": "c8d3d1cf-dc59-4ccd-8ff7-50489db160a7",
  "event_type": "OrderShipmentConfirmed",
  "schema_version": 1,
  "occurred_at": "2026-11-20T03:05:00Z",
  "published_at": "2026-11-20T03:05:04Z",
  "subject": {
    "type": "Order",
    "id": "ORD-842"
  },
  "data": {
    "order_id": "ORD-842",
    "shipment_id": "SHP-331",
    "carrier_code": "CARRIER-07",
    "handover_at": "2026-11-20T03:05:00Z"
  }
}
~~~

The message does not need to include `actor_id`, `warehouse_id`, or internal receipt codes if consumers are not permitted or do not need to know them. `message_id` identifies the communication message; it can reuse the domain event ID if publishing is one-to-one, though that is **not mandatory** and requires consistent retry rules. `published_at` is assigned by the publisher component; in an outbox system, an outbox row may exist before the message is actually published.

### No One-to-One Mapping Required

Domain events and integration events do not have to correspond one-to-one:

- One domain event may produce **multiple** integration events tailored to different consumer groups or contracts.
- Multiple internal changes may emit only **one** event publishing an aggregated outcome once a workflow reaches a clear milestone.
- Some domain events are **never published** externally, such as internal risk assessments.
- An integration event may reflect the outcome of a workflow coordinated across multiple domains; identify the authoritative publisher and completion condition.

This approach decouples internal data models from external contracts. For example, splitting the `orders` table into `orders` + `shipments` does not have to alter the meaning of `OrderShipmentConfirmed.v1`, as long as contract data and guarantees are still met.

## 5. Storage Change Records and CDC: Describing What the Database Wrote

**Change Data Capture (CDC)** captures data modifications, typically from transaction logs (such as WAL or binlog), and sometimes via triggers or other techniques. It can report **which table, which row key, and which INSERT/UPDATE/DELETE operation** the storage engine recorded, along with log-position metadata and before/after data images if supported by the source and configuration.

The following example is a **simplified representation, not the standard format of every CDC tool**:

~~~json
{
  "source": "orders-db",
  "table": "orders",
  "operation": "UPDATE",
  "primary_key": {
    "order_id": "ORD-842"
  },
  "before": {
    "fulfillment_status": "READY",
    "shipment_id": null
  },
  "after": {
    "fulfillment_status": "SHIPPED",
    "shipment_id": "SHP-331"
  },
  "transaction_position": "illustrative-log-position-1904"
}
~~~

Depending on the DBMS and tool, CDC may provide only an **after image**, partial `before`, or no `before`; some tools emit **snapshot records** during initial sync. A snapshot reading an existing row **does not mean** the business just created that entity at snapshot time. Offset/log position has meaning only within that specific source and should not be used to infer business timestamps or system-wide ordering.

### Why Is CDC Different From a Domain Event?

An update setting `fulfillment_status = SHIPPED` does not tell you whether this change was:

- A legitimate business handover;
- Staff manually correcting bad data;
- A batch job syncing from a legacy system;
- A snapshot re-ingestion job;
- Or a technical step where workflow preconditions had not been met.

Before/after column values alone cannot convey **meaning** and **reason**. If you need to know which receipt accompanied the handover, who confirmed it, and when it occurred, that data must be modeled where the data source can validate it.

CDC remains very useful for syncing data warehouses, building search indexes, feeding analytics pipelines, or relaying an **outbox**. However, if consumers directly ingest CDC from business tables, they become coupled to table names, column layouts, migrations, and internal data. That is a trade-off that must be accepted intentionally.

### What About Audit Logs?

**Audit logs** generally focus on who modified what, when, from which value to which value, and under what authority. Audit logs can be generated by the application or the database, sharing some fields with CDC, but their goal is accountability and compliance. An audit log is not implicitly a domain event, nor does it necessarily carry enough data to replay full business state. CDC can assist in building an audit log, but requirements around identity, integrity, evidence, and retention usually demand dedicated design.

## 6. Seeing All Three in One Business Flow

The logical diagram below depicts **one implementation option**, not a mandatory workflow for every architecture:

~~~mermaid
flowchart TD
    C["Command: ConfirmHandover"] --> D["Order/Shipment business logic"]
    D --> V{"Constraints valid?"}
    V -->|No| X["Reject command"]
    V -->|Yes| E["Domain event: OrderHandedToCarrier"]
    E --> TX["DB transaction: update state + write outbox"]
    TX --> WAL["DB transaction log"]
    TX --> O["Committed outbox row"]
    O --> P["Publisher / relay"]
    WAL -.-> P
    P --> I["Integration event: OrderShipmentConfirmed"]
    I --> N["Notification service"]
    I --> A["Analytics / downstream services"]
~~~

In the diagram, the dashed line from the transaction log to the relay shows **one implementation option**: CDC can watch changes on the outbox table to trigger publishing. The relay can also poll the outbox table directly. CDC can separately capture changes on the `orders` table for data synchronization; that stream serves a different purpose from publishing integration messages. Never treat a successfully published message as proof that every consumer has finished processing it.

### Consistency Rules to Establish

If writing to the `orders` table succeeds but the process crashes before sending a message directly, other systems may never learn that state changed. If sending happens before commit, a message may describe a change that never got persisted. This is the **dual-write** problem.

A **transactional outbox** solves the “write data and write publishing intent” part inside the same database transaction. A relay then delivers unpublished messages. Duplicate sends during relay retries can still happen, so consumers must process idempotently. A system should never claim “exactly once” end-to-end across database, broker, and all consumers solely from using an outbox.

## 7. Physical Design Example: State, Outbox, and CDC

A system using current state as its source of truth can store an `orders` table and an `integration_outbox` table. This design **does not require event sourcing**:

~~~sql
CREATE TABLE orders (
    order_id             VARCHAR(64) PRIMARY KEY,
    fulfillment_status   VARCHAR(24) NOT NULL,
    shipment_id          VARCHAR(64),
    shipped_at           TIMESTAMPTZ,
    version              BIGINT NOT NULL DEFAULT 0
                         CHECK (version >= 0)
);

CREATE TABLE integration_outbox (
    message_id           UUID PRIMARY KEY,
    aggregate_id         VARCHAR(64) NOT NULL,
    aggregate_version    BIGINT NOT NULL CHECK (aggregate_version > 0),
    event_type           VARCHAR(100) NOT NULL,
    schema_version       SMALLINT NOT NULL CHECK (schema_version > 0),
    occurred_at          TIMESTAMPTZ NOT NULL,
    payload              JSONB NOT NULL
                         CHECK (jsonb_typeof(payload) = 'object'),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at         TIMESTAMPTZ,
    UNIQUE (aggregate_id, aggregate_version, event_type)
);

CREATE INDEX ix_outbox_pending
    ON integration_outbox (created_at, message_id)
    WHERE published_at IS NULL;
~~~

The `integration_outbox` table stores **messages scheduled for publication**. It does not hold all domain events by itself, is not necessarily sufficient to reconstruct order state, and is **not an event store**. The `aggregate_version` field in the example must be incremented and checked atomically whenever updating the order. The unique constraint above assumes each aggregate version emits at most one message of the same `event_type`; if publishing rules permit multiple messages of the same type, choose a different business key.

Write flow inside a single transaction:

~~~text
BEGIN TRANSACTION
  Read Order and check version/lock inside the same transaction
  Check: current status allows handover, receipt is not duplicated
  UPDATE orders:
    fulfillment_status = SHIPPED
    shipment_id = SHP-331
    shipped_at = valid occurred_at
    version = version + 1
  INSERT integration_outbox:
    stable message_id for this publication
    event_type = OrderShipmentConfirmed
    payload per schema_version = 1
COMMIT
~~~

Under concurrent updates, use `SELECT ... FOR UPDATE` or `UPDATE ... WHERE version = expected_version` and check the affected row count; a failed operation must be re-evaluated against the new state. Guarding against duplicate command submissions may require a separate **idempotency key**, such as a unique constraint on `source_system` and `handover_receipt_id`. A `UNIQUE` constraint on version does not fully replace business rules against duplicate receipts.

After commit:

1. The relay reads unpublished outbox rows, or a CDC tool captures `INSERT` operations on the outbox table.
2. The relay sends the payload under the `OrderShipmentConfirmed.v1` contract to the broker or target API.
3. Once the broker acknowledges receipt, the relay sets `published_at` or updates its checkpoint. If the relay crashes between steps, the message may be redelivered.
4. Consumers store processed `message_id` values within the required scope and update their own data in an appropriate transaction so redelivery causes no duplicate side effects.

An **event-sourced** system is designed differently: the aggregate's event stream is the source of truth, while the `orders` table (if any) is a projection. It can still use outbox/integration events/CDC; keep each table's role and consistency responsibility distinct.

### Designing Keys and Indexes Around Queries

- `orders.order_id`: business identifier of the order, serving fast current-state lookups.
- `orders.version`: contention control; if updates run with `WHERE order_id = ? AND version = ?`, the primary key index is typically enough to locate the row without adding a separate index on `version` by default.
- `integration_outbox.message_id`: identifier for consumer-side deduplication; if the broker assigns its own ID, define its relationship to this ID for consistent retries.
- `ix_outbox_pending`: supports relay polling of unpublished messages; revisit index overhead under heavy write loads or when using transaction-log-based CDC.
- Indexes for business reporting belong on the appropriate read models—avoid treating the outbox as a long-term analytical store.

## 8. Data Models and Contracts Evolve Differently

**Internal schemas** may change for query optimization: splitting `orders` into `orders` and `shipments`, renaming columns, partitioning by date, or moving state reads to a document database. An integration consumer should not have to modify code just because of those physical changes.

**Domain events** change when the business domain genuinely gains new concepts or needs more data to explain an occurrence. When storing events long-term, version schemas so old and new readers can reconstruct history. If events are only dispatched in memory, evolution mechanics may be simpler, though business semantics must still stay well-defined.

**Integration events** have their own contract lifecycle. For instance, `OrderShipmentConfirmed.v2` may add `carrier_tracking_reference` without altering the meaning of `OrderHandedToCarrier`. Publishers need a compatibility policy: which fields are required vs. optional, how unknown enum values are handled, deprecation windows for old versions, and how changes are communicated.

**CDC records** typically change along with source schema and configuration. When renaming columns or moving tables, downstream CDC pipelines may need mapping updates and snapshot strategies even when business logic has not changed. With CDC from a schema-governed outbox, the impact of business-table migrations is smaller.

| Need | Usually appropriate choice | What must be verified |
| --- | --- | --- |
| Enforcing “already handed over, cannot hand over again” | Domain event/aggregate logic with state constraints. | Consistency boundary, concurrency, idempotency. |
| Notifying customer service that an order shipped | Versioned integration event contract. | When published, required fields, security, retries. |
| Syncing tables to a search engine or analytics warehouse | CDC or data-change pipeline. | Latency, schema drift, snapshots, upserts/deletes. |
| Querying history of business decisions | Persisted domain events or semantically rich business audit. | Timestamps, actors, causes, historical integrity. |
| Preventing lost messages after state updates | Transactional outbox and relay. | Atomic commits, replay, deduplication. |

## 9. Ordering, Time, and Late-Arriving Data

Time fields are easily misused if you do not specify **whose clock they come from**:

| Field | Meaning |
| --- | --- |
| `occurred_at` | When the business occurrence happened according to an authoritative source. |
| `recorded_at` | When the source system persisted the event or change. |
| `published_at` | When the message was published/confirmed published as defined by the publisher. |
| `consumed_at` | When the consumer processed or recorded the message. |
| `source_position` / `offset` | Position of a change or message in a specific log/partition, not a business date/time. |

For example, a driver hands over a package at **10:05**, the offline device syncs at **10:20**, the outbox relay publishes at **10:21**, and analytics consumes it at **10:22**. Reporting handover time using `published_at` shifts the metric by 16 minutes. If device clocks are untrustworthy, the business must define corroborating evidence and trust levels; a source timestamp cannot automatically become absolute truth.

Ordering in a domain event stream may use `aggregate_version`; ordering in CDC records may be a log sequence/transaction position; a broker may only guarantee ordering **within one partition**. These serve different scopes. Never rely on timestamps or offsets from one system to conclude total ordering of events across multiple services.

When a record arrives late, projections must handle it using keys, versions, and business rules. Under *at-least-once* delivery, idempotent consumption is a practical requirement; having `message_id` in the payload is not enough without recording processed IDs atomically alongside the update.

## 10. Common Design Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Emitting `OrderUpdated` for every change | Consumers cannot tell what the change means. | Publish business events at confirmed milestones. |
| Using `status: SHIPPED` from CDC to claim the driver received the parcel | Could be a sync/manual fix and lacks proof. | Define `OrderHandedToCarrier`, receipt evidence, authoritative source, and state transition rules. |
| Putting an entire database row into integration payloads | Exposes internal data and tightly couples schemas. | Use a dedicated DTO/contract, publishing only required fields. |
| Writing DB then sending messages independently without failure protection | DB and consumers diverge; notifications can be lost. | Use an outbox or equivalent architectural guarantee. |
| Treating an outbox as event sourcing | Cannot replay full state because it only holds outbound messages. | Separate source of truth, event store, and outbox if all three are needed. |
| Using one event name for “requested”, “approved”, and “completed” | Systems report success prematurely. | Name events after each milestone's specific confirmation condition. |
| Assuming every broker delivery is a brand-new event | Retries double revenue or delivery counts. | Stable IDs, idempotent consumers, and deduplication keys. |
| Treating a CDC snapshot as a new `OrderCreated` | Miscounts creation times and event totals. | Distinguish snapshots/initial loads from real business history. |
| Treating `schema_version` alone as sufficient for compatibility | Consumers break when field semantics or enums change. | Define evolution rules and test actual contracts. |

When handling sensitive data, all three streams must comply with authorization, retention limits, and deletion/anonymization policies. CDC can replicate personal data to many places; integration events can linger in queues and logs; long-lived domain events can complicate erasure requests. From the initial design, consider reference IDs, minimal fields, encryption, and access scopes.

## 11. Exercise: Translating Requirements Into a Data Model

**Scenario:** an online learning platform has `Enrollment` and `Billing` services. After a learner pays, the system activates course access and sends a notification. The analytics warehouse also wants to sync all enrollment changes.

Observed facts:

- The API receives a payment command, but the payment gateway has not yet confirmed.
- The payment gateway confirms a successful transaction.
- The `payments` table changes `payment_status` from `PENDING` to `CAPTURED`.
- The `Enrollment` service activates learning access for a specific course.
- The `enrollments` table changes `access_status` from `INACTIVE` to `ACTIVE`.
- The `Enrollment` service emits a message to `Notification` to send a welcome email.

**Practice tasks:**

1. Classify each item as a **command, domain event, integration event, CDC record, or processing action**. One progression can produce multiple record types; distinguish their nature instead of labeling arbitrarily.
2. Propose two meaningful domain event names, such as `PaymentCaptured` and `EnrollmentActivated`. Identify the aggregate, subject, emission condition, and authoritative timestamp for each event.
3. Design the integration message `EnrollmentActivated.v1` sufficient for Notification (learner ID, course ID, activation time, message ID), while minimizing unnecessary payment and personal data.
4. Draw the transaction boundary for `Enrollment`: persist state and outbox in the same transaction; explain how to avoid granting access twice if the payment message arrives twice.
5. Propose a CDC pipeline from the `enrollments` table to the analytics warehouse. Describe how to handle initial snapshots, INSERT/UPDATE/DELETE, schema migrations, and late-arriving data.
6. Explain why `UPDATE payments.payment_status` alone is insufficient proof that all course access rights have been activated.

**Self-verification criteria:** the model must clearly separate business facts from physical mutations; identify sources of truth and ownership boundaries; keep integration contracts decoupled from table schemas; handle retries, concurrency, and late arrivals; and allow storage layout changes without forcing public consumers to change.

**Key takeaway:** domain events tell you **what actually happened** inside the domain; integration events tell you **what committed facts/outcomes are shared** across systems; CDC tells you **how data changed** inside a storage engine. Separating these purposes lets you choose relational tables, documents, event streams, or analytical stores that fit the business, carry clear constraints, and can be reliably verified.
