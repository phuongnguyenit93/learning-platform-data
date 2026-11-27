# Domain Events to Express Business-Meaningful Changes

## Learning Objectives

After this lesson, you will be able to:

- Explain a **domain event** as a business fact that has occurred, distinct from commands, current state, and CRUD operations.
- Identify events worth modeling via business language, aggregate boundaries, invariants, and the downstream effects of a change.
- Design event names, payloads, identifiers, timestamps, versions, and causal links clearly enough to persist, publish, and verify.
- Distinguish **domain events**, **integration events**, **audit logs**, **outbox messages**, and **event sourcing**.
- Persist aggregate state changes and outbound events within the same transaction when using a relational database.
- Handle duplicate messages, lost responses, out-of-order delivery, and event schema evolution across multi-service systems.
- Choose storage structures for events in relational, document, graph, or analytical stores without blurring business ownership.

In the **DATABASE_DATA_MODELING** module, data design is not only choosing entities, keys, relationships, and indexes; it must also express **what changed and why that change matters**. A row updated from `DRAFT` to `CONFIRMED` is a storage detail. The **`OrderConfirmed`** event is business information: a specific order was confirmed according to Sales rules. This distinction keeps models meaningful, easy to integrate, and testable as requirements evolve.

## 1. A Domain Event Is Something That Happened

A **domain event** represents a noteworthy fact within the domain, arising **after** a business behavior succeeds. Event names are usually in the past tense:

- `OrderConfirmed` — an order has been confirmed.
- `StockReserved` — an inventory source has reserved a quantity of stock.
- `PaymentAuthorized` — the payment system has accepted an authorization.
- `SubscriptionCancelled` — a subscription plan has been cancelled.
- `ShipmentDelivered` — a parcel has been confirmed delivered.

An event typically carries the identity of the involved object, enough data to explain the change, when it occurred, and a unique identifier for that **event occurrence**. It does not ask consumers to mutate the emitting aggregate's data directly.

| Component | Question answered | Example |
| --- | --- | --- |
| **Command** | Who wants the system to do what? | `ConfirmOrder(orderId)` |
| **Aggregate** | Who has authority to validate and execute? | `Order` in Sales |
| **State transition** | How did the state change? | `DRAFT` -> `CONFIRMED` |
| **Domain event** | What business fact was just produced? | `OrderConfirmed` |
| **Integration event** | What fact must be published under an external contract? | `SalesOrderConfirmed` v1 |
| **Reaction** | What does a consumer do based on that fact? | Create a reservation request, update a projection |

An event is not a request. **`ReserveStock`** is a command asking Inventory to grant a hold; **`StockReserved`** is an event published by Inventory after the hold has succeeded. Never name a request message `StockReserved` and act as if the warehouse already completed the work.

## 2. When Should a Domain Event Be Emitted?

Not every column `UPDATE` makes a useful domain event. A strong candidate usually meets one or more criteria:

1. **Named in the business language:** staff say "order was confirmed", "stock was reserved", or "ticket was rejected", rather than "record was updated".
2. **Marks a lifecycle milestone:** after that point, permitted actions, obligations, or business status change.
3. **Interesting to multiple downstream activities:** notifications, analytics, inventory, accounting, post-sales workflows.
4. **Needs an explanatory trail:** why a benefit was granted, who approved it, which policy applied.
5. **Has an exact occurrence condition:** created only when the state transition succeeds and invariants have been protected.

Examples:

| Action | Should a domain event be created? | Rationale |
| --- | --- | --- |
| Confirming an order from `DRAFT` | Yes: `OrderConfirmed` | Business commitment milestone; triggers downstream obligations |
| Cancelling an order per policy | Yes: `OrderCancelled` | Triggers compensation and notifications |
| User opens the order detail page | Usually no | This is a query, not a domain state change |
| Repository runs `UPDATE version` | Not automatically | Incrementing `version` is a technical mechanism, not an independent business fact |
| Fixing whitespace in an internal label | Depends on domain | Worth an event only if semantically meaningful or audited |
| A seat hold expires | Potentially: `ReservationExpired` | Requires an explicit expiration decision/transition |

**A domain event must accurately describe a fact.** If a timer merely crosses a deadline while the system has not updated the hold record, do not implicitly claim resources were released without an actual enforcement mechanism. You can compute an "expired" status at read time or run an atomic `ExpireReservation` command and then emit `ReservationExpired`.

### Name Events After the Business, Not After SQL

Avoid vague names like `EntityUpdated`, `OrderTableChanged`, or `DataSaved` because they do not state what meaningful change occurred. `OrderConfirmed` is clearer than `OrderStatusChanged`: listeners immediately know a specific business step happened without inferring it from old/new value pairs.

In some infrastructures, Change Data Capture (CDC) emits messages for table `INSERT`/`UPDATE`/`DELETE` operations. CDC is useful for shipping data changes, yet **a CDC message is not automatically a domain event**: one business change may touch multiple rows, and a single `UPDATE` does not necessarily represent a user-meaningful fact.

## 3. The Aggregate Decides Whether an Event Occurs

An aggregate root is responsible for enforcing local invariants. For example, `Order` manages status, line items, and locked-in pricing details; only the root has authority to decide when it can be confirmed.

Business assumptions for our example:

- Only a `DRAFT` Order may be confirmed.
- An Order must have at least one line with a valid quantity.
- Once `CONFIRMED`, lines and locked-in unit prices can no longer be edited.
- One successful confirmation creates exactly **one `OrderConfirmed` fact for that transition**.
- Two competing requests cannot both confirm based on the same stale version.

Flow of responsibility:

~~~mermaid
flowchart LR
    C["Command: ConfirmOrder"] --> A["Order aggregate root"]
    A -->|"validate invariants"| D{Valid?}
    D -->|"No"| E["Domain error, no OrderConfirmed"]
    D -->|"Yes"| S["Order transitions to CONFIRMED"]
    S --> V["Record domain event OrderConfirmed"]
    V --> P["Repository + transaction"]
    P --> O["State + outbox commit together"]
    O --> B["Publish integration event after commit"]
~~~

Crucial point: **instantiating an event object in memory does not mean the event has durably occurred**. If the transaction saving `Order` fails and rolls back, `OrderConfirmed` must never be published as a committed fact. The application service/repository must control the commit boundary and trigger external effects only after data is durably persisted.

### A Domain Event Does Not Grant Permission to Mutate Other Aggregates

Upon receiving `OrderConfirmed`, Inventory may decide to process a stock reservation request. It must not directly update status columns on `Order` in Sales's database. Likewise, Sales cannot assume stock is reserved just because it emitted `OrderConfirmed`; it must receive an authoritative outcome issued by Inventory.

If the business rule states "an Order may only be confirmed once inventory has reserved sufficient stock," change the workflow: reserve stock first, obtain reservation proof, and then confirm; or introduce an intermediate state like `AWAITING_STOCK`. Never treat an asynchronous domain event as a guarantee that all subsequent steps already succeeded.

## 4. Designing Domain Event Structure

An event should be **immutable** and have stable enough semantics to be understood later. Common fields:

| Field | Meaning | Notes |
| --- | --- | --- |
| `eventId` | Unique identifier of this event occurrence | Distinct from `aggregateId`, `requestId`, and message broker IDs |
| `eventType` | Name of the business fact | E.g., `OrderConfirmed`; avoid table names |
| `aggregateId` | Which root changed | Should include namespace/tenant when identifier scope requires it |
| `aggregateVersion` | Root's version after applying the change | Helps detect ordering, though not global cross-aggregate order |
| `occurredAt` | When the business event was confirmed | Usually UTC; requires policy on clocks and recording time |
| `payload` | Facts interested consumers need to know | Document clear semantics, units, and data types |
| `schemaVersion` | Event contract version when published externally | Supports compatibility as payloads evolve |
| `correlationId` / `causationId` | Groups steps of one workflow / links the triggering event | Useful for tracing; does not replace `eventId` |
| `producer` | Source responsible for publishing the message | Important when multiple systems use similar event names |

Not every internal domain event needs all these fields. Within a single bounded context, compact types suffice, whereas externally published **integration events** typically need a full envelope, versioning, and operational conventions.

### EventId, AggregateId, and RequestId Are Different

An `Order` keeps a fixed `orderId` across its entire lifecycle. A user may send `ConfirmOrder` with a `requestId` for safe retries. Upon commit, the system emits an `OrderConfirmed` domain event with an `eventId`. The broker may attach an infrastructure-generated `messageId`. These four identifiers serve distinct roles:

~~~text
orderId    = identifier of the business object
requestId  = identifier of the caller's intent/command for idempotency
eventId    = identifier of a single fact that occurred
messageId  = identifier of the infrastructure transport packet (may change on redelivery)
~~~

When the same `requestId` is retried due to a timeout, do not create another `OrderConfirmed` if the command already succeeded. When the system re-sends **the same committed event**, preserve the exact `eventId` so consumers recognize the duplicate.

### Choose Payloads Intentionally

For `OrderConfirmed`, the payload might carry `orderId`, `tenantId`, total amount, currency, confirmation timestamp, and version. If Inventory needs SKU/quantity breakdown, consider a dedicated **integration event or fulfillment command** with an explicit contract. Do not automatically attach the entire `Customer`, payment method, personal address, and internal `Order` objects: bloated payloads leak sensitive data, resist evolution, and couple consumers to internal domain structures.

Monetary amounts should use exact decimal types or decimal strings paired with currency. Timestamps must specify time zones. Optional fields, units of measure, and the semantics of "locked-in" values must be documented.

## 5. Java 17 Example: Order Recording an Event on Confirm

The following snippet illustrates only the domain logic. Repositories and transactions are designed in the next section; there is no message publishing inside the aggregate:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

interface DomainEvent {
    UUID eventId();
    UUID aggregateId();
    long aggregateVersion();
    Instant occurredAt();
}

record OrderConfirmed(
        UUID eventId,
        UUID aggregateId,
        long aggregateVersion,
        Instant occurredAt,
        BigDecimal totalAmount,
        String currency
) implements DomainEvent {
    OrderConfirmed {
        Objects.requireNonNull(eventId);
        Objects.requireNonNull(aggregateId);
        Objects.requireNonNull(occurredAt);
        Objects.requireNonNull(totalAmount);
        Objects.requireNonNull(currency);
        if (aggregateVersion <= 0) throw new IllegalArgumentException("version");
    }
}

enum OrderStatus { DRAFT, CONFIRMED, CANCELLED }

// Aggregate root; unit prices and line items were validated when adding lines.
final class Order {
    private final UUID id;
    private final String currency;
    private final List<BigDecimal> lineTotals = new ArrayList<>();
    private final List<DomainEvent> pendingEvents = new ArrayList<>();
    private OrderStatus status = OrderStatus.DRAFT;
    private long version;

    // Repository reconstitutes persisted state and data without emitting new events.
    Order(UUID id, String currency, OrderStatus loadedStatus,
          long loadedVersion, List<BigDecimal> persistedLineTotals) {
        this.id = Objects.requireNonNull(id);
        this.currency = Objects.requireNonNull(currency);
        this.status = Objects.requireNonNull(loadedStatus);
        if (loadedVersion < 0) throw new IllegalArgumentException("version");
        this.version = loadedVersion;
        for (BigDecimal amount : Objects.requireNonNull(persistedLineTotals)) {
            if (amount == null || amount.signum() < 0) {
                throw new IllegalArgumentException("Invalid persisted line");
            }
            lineTotals.add(amount);
        }
    }

    void addLineTotal(BigDecimal amount) {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Order is no longer editable");
        }
        if (amount == null || amount.signum() < 0) {
            throw new IllegalArgumentException("Invalid line total");
        }
        lineTotals.add(amount);
        version++;
    }

    void confirm(UUID eventId, Instant occurredAt) {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Only draft orders can be confirmed");
        }
        if (lineTotals.isEmpty()) {
            throw new IllegalStateException("Cannot confirm an empty order");
        }
        BigDecimal total = lineTotals.stream()
            .reduce(BigDecimal.ZERO, BigDecimal::add);
        status = OrderStatus.CONFIRMED;
        version++;
        pendingEvents.add(new OrderConfirmed(
            eventId, id, version, occurredAt, total, currency));
    }

    UUID id() { return id; }
    OrderStatus status() { return status; }
    long version() { return version; }
    List<DomainEvent> pendingEvents() {
        return List.copyOf(pendingEvents);
    }
}
~~~

This is a simplified model: `lineTotals` stands in for `OrderLine` to keep focus on **event generation**. In a production application, `OrderLine` needs validated identity/quantity/price and the repository must reconstitute them fully. The reconstitution constructor neither increments `version` nor emits events. `version` increments in memory on each mutation; when persisting, the repository must compare against the **originally loaded version** and persist the **aggregate's final version**, rather than comparing against the newly incremented version. If a unit of work spans multiple mutations, data rows and the final version must be written atomically.

When `Order.confirm()` fails due to invalid status or an empty order, no `OrderConfirmed` is created. When it succeeds, the new event sits in **`pendingEvents`** until the repository finishes writing. The application service can load the root, invoke the command, and save state + outbound events in the same transaction; on rollback, discard the uncommitted instance and reload state if retrying.

In this example, the event's `UUID` and `Instant` are passed in from the orchestration layer to support determinism and testing. Avoid calling the system clock arbitrarily everywhere and assuming every step of a command sees the same timestamp. When business rules require `occurredAt` from the DB at commit time or an authoritative time source, design that rule into the repository.

**Note:** Never treat a newly constructed event as "already sent." The root does not call HTTP, message brokers, email, or write directly to another aggregate's database. Transactions and post-commit publishing mechanisms handle that.

## 6. Domain Events, Integration Events, Audit Logs, and Event Sourcing

These are four related concepts, yet they are not synonymous:

| Concept | Primary purpose | Who owns the structure? | Must it live long-term? |
| --- | --- | --- | --- |
| **Domain event** | Expresses a fact that just occurred inside the domain model | Emitting bounded context/aggregate | Not necessarily the source of truth to rebuild state |
| **Integration event** | Announces stable facts to other systems/contexts | Producer's integration contract | Durable enough for delivery and retries per SLA |
| **Audit log** | Traces who did what, when, and which decision was made | Audit/compliance policy | Depends on retention and traceability rules |
| **Event sourcing** | Uses an event sequence as the source of truth to rebuild state | Aggregate's event stream model | Yes: must remain stored and replayable by design |

An internal `OrderConfirmed` domain event can be mapped to `SalesOrderConfirmedV1` for external publication. You need not expose every internal attribute of `OrderConfirmed`; an integration payload is usually a **stable contract** for external consumers.

If a system merely stores the current `orders` table alongside an outbox for message delivery, that is **not event sourcing**. Even adding a transition history table for auditing is not enough to call it event sourcing. Event sourcing requires stored events to be the authoritative source for reconstructing state, complete with versioning policies, replay, schema compatibility, and side-effect suppression during rebuilds.

### One Change Can Produce Multiple Events, or None Published Externally

One command can generate multiple business facts—such as `InvoiceIssued` and `PaymentDueScheduled` if those are two well-defined independent milestones. Conversely, a domain event used only for internal rules with no external consumers does not need to become an integration event.

Do not force a "one `UPDATE` = one event" or "one command = one event" rule in every case. The deciding criterion is **the meaning of the business fact that occurred**, not the number of SQL statements.

## 7. Persisting State and Outbox in the Same PostgreSQL Transaction

A common risk is:

~~~text
UPDATE orders -> COMMIT succeeds
Process crashes before publishing OrderConfirmed
=> Database has a confirmed order, while other systems never receive the event.
~~~

Reversing the order to "publish first, then COMMIT" does not fully solve it either: `OrderConfirmed` could be published before the transaction rolls back. **Transactional outbox** closes this gap by storing **aggregate state and the intent to publish a message** in the same local transaction.

A simple schema:

~~~sql
CREATE SCHEMA IF NOT EXISTS sales;

CREATE TABLE sales.orders (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    status VARCHAR(16) NOT NULL
        CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')),
    total_amount NUMERIC(19, 2) NOT NULL
        CHECK (total_amount >= 0),
    currency_code CHAR(3) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    PRIMARY KEY (tenant_id, order_id)
);

CREATE TABLE sales.outbox_event (
    event_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    aggregate_id UUID NOT NULL,
    aggregate_version BIGINT NOT NULL CHECK (aggregate_version > 0),
    event_type TEXT NOT NULL,
    schema_version INTEGER NOT NULL CHECK (schema_version > 0),
    occurred_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ,
    FOREIGN KEY (tenant_id, aggregate_id)
        REFERENCES sales.orders (tenant_id, order_id)
);

CREATE INDEX outbox_unpublished
    ON sales.outbox_event (created_at, event_id)
    WHERE published_at IS NULL;

CREATE INDEX outbox_aggregate_sequence
    ON sales.outbox_event (tenant_id, aggregate_id, aggregate_version);
~~~

This schema assumes the Outbox stores only Order events. If an outbox is shared across multiple aggregate types, an FK to a single `orders` table no longer works; replace it with producer + `aggregateType` identifiers and dedicated integrity rules. The `outbox_unpublished` index helps fetch pending records, though it does not by itself guarantee global system-wide ordering.

### Transaction to Confirm an Order

Suppose the application service loaded a `DRAFT` Order at version 4 with valid lines, called `confirm()`, and obtained version 5. In the repository, the new state and constructed event must be persisted together:

~~~sql
BEGIN;

UPDATE sales.orders
SET status = 'CONFIRMED',
    total_amount = :verified_total_amount,
    version = :new_version
WHERE tenant_id = :tenant_id
  AND order_id = :order_id
  AND status = 'DRAFT'
  AND version = :expected_version
  AND :new_version > :expected_version
RETURNING version;

-- Proceed only if UPDATE returned exactly 1 row.
-- If 0: ROLLBACK, do not insert into outbox.
-- :new_version is the actual returned version.

INSERT INTO sales.outbox_event
    (event_id, tenant_id, aggregate_id, aggregate_version,
     event_type, schema_version, occurred_at, payload)
VALUES
    (:event_id, :tenant_id, :order_id, :new_version,
     'SalesOrderConfirmed', 1, :occurred_at,
     jsonb_build_object(
         'orderId', :order_id,
         'tenantId', :tenant_id,
         'totalAmount', :total_amount_text,
         'currency', :currency_code
     ));

COMMIT;
~~~

In this example, `:expected_version` is the version when the repository loaded the Order; `:new_version` is the final version produced by the aggregate and must match the event's version. `:verified_total_amount` and `:total_amount_text` come from **the same domain-computed and validated result**, never raw from the client. If a command edits lines alongside confirming, those edits must persist in the same transaction. In this example confirming an order that already had lines, `version` increments once (`4` -> `5`). When multiple behaviors within one unit of work bump `version`, SQL writes the final version; emitted events may carry distinct versions, and not every version necessarily produces an integration event.

**Database-level guarantee:** either both Order and outbox record commit, or both roll back. This **does not automatically guarantee** the broker received or consumers processed the event. A forwarding process (outbox relay) must still read the outbox and publish with retries.

### Why Is "Exactly Once" Easily Misunderstood?

The relay might publish successfully and then crash before marking `published_at`. Upon restart, it sends **the same `eventId`** again; the broker or consumer may see two copies. Outbox solves lost publishing intent caused by two separate transactions, yet typically delivers **at-least-once** publication—not exactly-once business effects across every downstream system.

Consumers must make their side effects **idempotent**, or combine a local transaction with a processed-events tracking table.

## 8. Consumers: Idempotency, Ordering, and Ownership

Suppose `SalesOrderConfirmed` triggers Inventory to process a stock reservation. Inventory holds the authority to decide whether stock can be reserved based on available quantities and its own policies.

~~~mermaid
sequenceDiagram
    participant O as Sales / Order
    participant DB as Sales DB + Outbox
    participant B as Broker
    participant I as Inventory
    O->>DB: COMMIT Order CONFIRMED + event
    DB-->>O: Commit OK
    DB->>B: Publish SalesOrderConfirmed
    B->>I: Deliver eventId = E42
    I->>I: Dedup + reserve stock in transaction
    I-->>B: Ack after commit
    B->>I: Redelivery eventId = E42
    I->>I: Already processed E42, do not reserve again
~~~

A local deduplication table in Inventory:

~~~sql
CREATE SCHEMA IF NOT EXISTS inventory;

CREATE TABLE inventory.processed_event (
    consumer_name TEXT NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Consumption pattern inside **a single Inventory transaction**:

~~~text
BEGIN
  INSERT inventory.processed_event(consumer_name, event_id)
    ON CONFLICT DO NOTHING RETURNING event_id

  If 0 rows:
    COMMIT; ACK; finish (this is an already-processed duplicate)

  If 1 row:
    Read payload; validate version/tenant/required data
    Execute appropriate Inventory command, protecting stock with transaction
    Write reservation or rejection result and Inventory outbox
    COMMIT; ACK

If any business operation fails:
  ROLLBACK both the dedup mark and Inventory changes
  Retry or route to error-handling flow per policy
~~~

Mark `processed_event` **only inside the same transaction as the local side effect**. If you mark first and apply the side effect in a separate transaction, a crash marks the event as processed while Inventory remains unchanged. Similarly, only ACK the broker after local results are durable.

An Inventory command failing due to **insufficient stock** is a business outcome, not necessarily a transient system error to retry forever. Inventory can record a `StockReservationRejected` outcome and publish its own event; Sales then decides whether to cancel or backorder per policy.

### Processing Order

`OrderConfirmed` might be emitted before `OrderCancelled`, yet the two messages arrive at a consumer in reverse order due to retries, multiple partitions, or multiple relays. If the receiver's state depends on ordering, use `aggregateVersion`/sequence to detect stale events, gaps, or duplicates and handle them per contract.

- **`eventId`** detects duplicates of a single occurrence.
- **`aggregateVersion`** expresses the change order **of a single aggregate** when assigned consistently.
- **`correlationId`** links steps of a workflow, not sequence order.
- Never infer total ordering across all aggregates from timestamps or broker log positions.

If relays process outbox rows in parallel, an index on `created_at` alone cannot guarantee `OrderConfirmed` is always published before `OrderCancelled`. You can partition messages by `aggregateId` to preserve per-aggregate ordering, or let consumers track versions and buffer missing events.

## 9. Contract Versioning and Event Schema Evolution

Once an event leaves a bounded context, it becomes a contract relied upon by multiple consumers. Arbitrary field changes can break external systems.

An illustrative integration event:

~~~json
{
  "eventId": "e3563fa7-3ab1-4e08-88a1-3f3a884b47aa",
  "eventType": "SalesOrderConfirmed",
  "schemaVersion": 1,
  "producer": "sales",
  "tenantId": "fe8175f8-cc11-4fbe-8536-100f4b613c04",
  "aggregateId": "b188c0f3-83de-49be-8f84-fcdbbfbdc168",
  "aggregateVersion": 5,
  "occurredAt": "2026-11-22T02:00:00Z",
  "correlationId": "f1d3a6a1-9644-4c64-a86c-ae2a4d13b6a3",
  "payload": {
    "orderId": "b188c0f3-83de-49be-8f84-fcdbbfbdc168",
    "totalAmount": "23000000.00",
    "currency": "VND"
  }
}
~~~

Questions to align on:

1. **Are event names and semantics stable?** `SalesOrderConfirmed` must not initially mean customer confirmed and later quietly mean Payment captured funds.
2. **Are new fields optional?** Adding an optional field with a default is far more compatible than renaming or removing required fields.
3. **Did units or rounding rules change?** `totalAmount` is a decimal with explicit `currency`; never switch from VND to thousands of VND while keeping the same field name.
4. **Do consumers ignore unknown fields?** Contracts need explicit rules; never assume every serializer library behaves identically.
5. **Is a new event type/version required?** A breaking semantic change usually calls for a new contract or a transition period.

For long-lived stored events, establish a schema registry, upcasters/adapters, or multi-version support if replay is required. Avoid letting consumers depend directly on the producer's internal classes/entities, because a table refactor should not become a breaking public API change.

### Anti-Corruption Layer at the Boundary

A `CustomerRegistered` event in Customer Management does not necessarily mean the same thing as `BuyerActivated` in Sales. The consumer can use a semantic translation layer to build its own appropriate model rather than copying the producer's object wholesale. ID fields, statuses, effective timestamps, and namespaces must be interpreted by contract, not merely by matching names.

## 10. Event Data, History, and Privacy

When choosing payloads and retention periods:

- Send only data required by the contract; send IDs or authorized data references instead of embedding full personal profiles.
- Enforce topic/queue read permissions and data protection policies matching payload sensitivity.
- Distinguish **`occurredAt`** (when the business fact occurred) from **`recordedAt`/`created_at`** (when the system persisted it) and **`publishedAt`** (when the broker accepted it); they can differ.
- Plan for regulatory erasure/anonymization and audit needs. Once events are distributed across many replicas/backups, they are very hard to scrub later; minimizing sensitive data upfront is the better design choice.
- Do not treat the outbox as a permanent audit archive. An outbox is typically a durable queue with a cleanup policy after successful delivery and after the retry/reconciliation window expires.

**Data consistency and complete history are two different requirements.** An outbox guarantees the intent to publish an event is saved in the same transaction, yet it neither enables rebuilding every past state nor replaces auditing of actors, reasons, and decision sources.

If legal audit trails are required, design an audit trail with subject, timestamp, change request, appropriate immutability/tamper-evidence, and retention period—never dump arbitrary JSON strings and call it compliant auditing.

## 11. Same Event, Multiple Storage Engines

The domain event model does not depend on a single storage technology. Separate the **authoritative write source** from **read/observation models**.

| Option | Representation | What to verify |
| --- | --- | --- |
| **Relational** | Root state in transactional tables; outbox/sometimes event log in separate tables | ACID commits, locks/versions, unpublished index, retention |
| **Document** | Document holding root and pending messages/outbox per DB mechanism, or an event collection | Atomic operation scope, document size limits, avoiding unbounded embedded history |
| **Graph** | Events/relationships linking objects when querying causality and impact chains | Edges do not prove ordering, authority, or business transactions |
| **Analytical/Columnar** | `FactBusinessEvent` with `eventType`, timestamp, `aggregateId`, dimensions | Great for conversion/latency stats; typically a delayed replica |

Example: `SalesOrderConfirmed` is consumed to build an analytical table of confirmed orders per day. The warehouse can use `event_id` for deduplication and a date dimension for aggregation, yet **never use delayed analytical metrics to decide whether an active Order can be confirmed again**.

In a relational database, the outbox table serves **delivery**, the audit table serves **traceability**, and the order table holds **current state**. If you choose event sourcing, the event stream is the state reconstruction source and needs its own versioning/replay model. Different purposes should not be forced into a single table just because all of them include the word "event."

## 12. Testing Events Against Business Outcomes and System Failures

A valuable test suite covers both **when an event must NOT be emitted** and **when messages are redelivered**:

| Scenario | Expected outcome |
| --- | --- |
| `ConfirmOrder` on `DRAFT` with valid lines | Order becomes `CONFIRMED`; `OrderConfirmed` saved in same transaction |
| `ConfirmOrder` on empty `DRAFT` | Rejected; no `OrderConfirmed` committed |
| `ConfirmOrder` again on `CONFIRMED` | No new event created; returns outcome per idempotency policy |
| Two `confirm` requests with same version | At most one transition commits; the other receives conflict/already-processed result |
| Saving Order succeeds but outbox `INSERT` fails | Entire Order change rolls back |
| Commit succeeds, relay crashes before publishing | Outbox row remains for retry |
| Publish succeeds, relay crashes before marking sent | May resend with same `eventId`; consumer does not apply twice |
| Consumer receives version 7 then version 6 | Does not overwrite newer state with stale data; handles per sequence policy |
| Event missing required fields | Fails contract check, isolates or routes to dead-letter handling |
| Inventory lacks stock | Records authoritative rejection; never treats `OrderConfirmed` as `StockReserved` |

When running concurrency tests, do not check only HTTP status codes. Inspect **the final database state**, the count of business side effects, and the exact outbox/`eventId` records actually committed.

## 13. Exercise: Delivery and Customer Notifications

**Context:** A logistics system manages `Shipment` with lifecycle `CREATED` -> `PACKED` -> `DISPATCHED` -> `DELIVERED`, with transitions to `FAILED_DELIVERY` and `RETRYING` per policy. Each `Shipment` has `shipmentId` and an `orderId` referencing an `Order` in Sales. A customer might receive duplicate notifications if a broker redelivers a message, so idempotency must be designed.

### Tasks

1. Identify domain events worth emitting, distinct from commands. Name them after business facts.
2. Choose the root authorized to decide that a `Shipment` was delivered successfully; can `Order` directly modify `Shipment` status?
3. Propose a minimal payload for `ShipmentDelivered`, including identifiers, timestamps, version, and data needed by consumers. Should the full recipient street address be embedded in the message?
4. Describe how to commit `DELIVERED` status and the intent to send notifications in the same transaction.
5. If one `ShipmentDelivered` is delivered twice—and one arrives late after `ShipmentDeliveryCorrected`—how must Notification and Analytics handle it?
6. If a `MarkDelivered` command fails because the `Shipment` is not yet `DISPATCHED`, should `ShipmentDelivered` be emitted? Explain.

### Reference Solution Approach

- Commands include `PackShipment`, `DispatchShipment`, `MarkDelivered`, and `ReportDeliveryFailure`; corresponding events on success could be `ShipmentPacked`, `ShipmentDispatched`, `ShipmentDelivered`, and `ShipmentDeliveryFailed`. Never use `DispatchShipment` as the name of an event that already happened.
- `Shipment` is the aggregate root in Logistics; `orderId` is only a reference back to Sales. Logistics validates state and delivery proof. Sales may consume events to update read models or coordinate post-delivery workflows, without directly mutating the `Shipment` table.
- Payload includes `eventId`, `aggregateId = shipmentId`, `orderId`, `tenantId` where applicable, `aggregateVersion`, `occurredAt`, `deliveryResultCode`, `schemaVersion`, and `correlationId`. Minimize personal data; Notification can look up contact details from an authoritative source or receive an authorized token/ID per contract.
- The transaction updates `Shipment` to `DELIVERED` with version bump and inserts into outbox; the relay publishes post-commit, and consumers deduplicate by `eventId`. If the same command is retried, no new event is emitted for an already-completed transition.
- When `ShipmentDeliveryCorrected` arrives before or after `ShipmentDelivered`, consumers must apply `version`/event sequence and correction rules. Never blindly treat "redelivered old event" as a new delivery; Analytics deduplicates by `eventId` and supports recomputing metrics upon corrections.
- If the prior state is invalid, the command fails and no `ShipmentDelivered` is committed. A false event would mislead Notification, reporting, and post-sales workflows.

### Extension

Explain why an audit table containing `actor`, `fromStatus`, and `toStatus` may still be needed even when the system already has an outbox for `ShipmentDelivered`. The two tables may relate, yet their **purpose, access permissions, and retention periods differ**.

## 14. Domain Event Design Review Checklist

- Does the event name express a **fact that already happened** in business language?
- Which aggregate has authority to emit the event, and which invariants are verified beforehand?
- When a transaction rolls back, is it guaranteed that no phantom integration event is published?
- Do `eventId`, `aggregateId`, `requestId`, `messageId`, `version`, and `correlationId` each have a clearly defined role and scope?
- Does the payload include currency, units, timestamps, schema version, and the minimal necessary data?
- Are internal domain events clearly separated from integration contracts, audit logs, and event sourcing?
- Does the publisher retry safely, and does the consumer deduplicate/handle idempotency in the same transaction as local effects?
- If events arrive late or out of order, does the system have a way to determine valid state?
- Are write paths and ownership of other aggregates respected when reacting to events?
- Do the relational/document/graph/analytical models satisfy queries, retention, security, and evolvability?

**Conclusion:** Domain events let models record **the meaning of change**, not merely that a column was updated. Aggregates decide which facts can occur; transactions turn changes into durable outcomes; integration events carry facts across boundaries; and consumers guard their own consistency and idempotency. Designing this way keeps databases, applications, and integrations expressing the same business rules clearly, verifiably, and with controlled change.
