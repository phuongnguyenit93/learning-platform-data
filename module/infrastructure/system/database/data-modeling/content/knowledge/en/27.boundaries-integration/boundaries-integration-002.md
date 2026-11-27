# Relationship Between Domain Models, Storage Models, and Exchange Models

## Learning Objectives

After completing this lesson, you will be able to:

- Distinguish the **domain model**, **storage/persistence model**, and **exchange/integration model** by responsibility, authoritative source, and stability.
- Explain why a single aggregate may be stored across multiple tables or documents while being exposed through multiple API DTOs, commands, and integration events of **different shapes**.
- Translate business invariants into domain behavior combined with keys, transactions, versions, and constraints at the storage layer.
- Design domain ↔ storage and domain → exchange mappings for identities, currency, timestamps, statuses, and derived data.
- Distinguish commands from events, API requests from persistence rows, and domain events from CDC and analytical facts.
- Use the transactional outbox, consumer idempotency, and anti-corruption layers to integrate across bounded contexts without confusing ownership.
- Evaluate relational, document, graph, and analytical choices; plan migrations/schema versions without breaking consumers.
- Test boundaries against business errors, concurrent writes, retries, late-arriving data, and contract changes.

In **DATABASE_DATA_MODELING**, data modeling is not just listing entities, relationships, keys, and indexes. You also need to know **who holds authority to change business truth**, **how data is stored to be accurate and performant**, and **what other systems are allowed to know or request**. A common mistake is using the exact same Java class as the domain entity, ORM entity, and JSON API payload, and then publishing that raw object as an event message. Doing so causes table refactorings to break APIs, exposes unnecessary data, and leaks storage column semantics to consumers.

In the **Boundaries and Integration** chapter, the goal is not creating extra layers for elegance: **the three models must stay consistent in meaning without needing to share the same structure**.

## 1. One Order, Three Perspectives

Consider a sales workflow: a customer creates an Order; Sales confirms it; Inventory reserves stock; Payment collects funds; Notification reports the outcome; Analytics aggregates totals.

| Question | Responsibility | Model |
| --- | --- | --- |
| Can an empty Order be confirmed? | Sales enforces Order rules | **Domain** |
| Where are the Order and its lines stored, and with what keys? | Sales repository/database | **Storage** |
| What command does the client send to confirm, and what result does it receive? | Sales REST API | Synchronous **Exchange** |
| How does Inventory learn that an Order was just confirmed? | Producer/consumer with an event contract | Asynchronous **Exchange** |
| How many orders were paid by product/month? | Analytics with explicit grain and metrics | **Read/analytical model** |

Executing an UPDATE of `status` from `DRAFT` to `CONFIRMED` is how the state transition is **stored**. Calling `confirm()` is conditional **domain behavior**. `OrderConfirmed` is a **fact that occurred** after commit. A `FactPaidOrderLine` row is a **measurement** for analytics; it has no authority to change Order status.

~~~~mermaid
flowchart TB
    CLIENT["Client / API request"] --> APP["Application service<br/>auth + use case"]
    APP --> DOMAIN["Domain model<br/>Order aggregate"]
    DOMAIN <-->|"Repository mapping"| DB[("Storage<br/>order_header + order_line")]
    APP --> OUT[("Outbox in same transaction")]
    OUT --> BUS["Event broker"]
    BUS --> ACL["Consumer adapter / ACL"]
    ACL --> INV["Inventory / Notification<br/>separate domain model"]
    DB --> READ["Read model / Analytics"]
~~~~

This diagram depicts **logical** boundaries. A monolith can still apply them without splitting into microservices. Conversely, even with many services, letting them mutate each other's internal tables fails to establish safe boundaries.

## 2. Comparing the Three Models by Responsibility

| Criterion | Domain Model | Storage Model | Exchange Model |
| --- | --- | --- | --- |
| Goal | Express concepts, behavior, and invariants | Durable writes/reads, transactions, performance | Transmit intent or facts across boundaries |
| Units | Entity, value object, aggregate, domain service | Table/row, document, index, partition, edge | Request, response, command, integration event |
| Core Question | Which behaviors are valid? Who decides? | Which keys, constraints, and atomic writes? | What must the receiver know, and how are fields interpreted? |
| Changes with | Business rules | Workload and data layout | Client/consumer contracts |
| Consistency | Invariants within root/context scope | Constraints, locks, isolation, versions | Never publish uncommitted facts; safe retries |
| Visibility | Mostly internal to the bounded context | Typically private to the data owner | Intentionally published |
| Order Example | `addLine()`, `confirm()`, `totalVnd()` | `order_header`, `order_line`, `outbox_event` | `ConfirmOrderRequest`, `OrderView`, `OrderConfirmedV1` |

An `Order` class might hold a `List<OrderLine>`, while storage uses **one header row and multiple line rows**. An API might return `totalVnd` as a string while storage holds a `BIGINT`. An event carries `eventId`, `schemaVersion`, and `correlationId`—fields that are **not necessarily business attributes of Order**.

Do not force everything into a single DTO just to save lines of code. At the same time, do not create pointless mapping layers: each layer should address genuine differences in **semantics, access control, or change lifecycle**.

## 3. Bounded Contexts and Authoritative Sources

Identical words can carry different meanings:

- **Sales:** `Order` is a purchase commitment containing status and locked prices.
- **Inventory:** `Reservation` is a time-bounded hold on a SKU quantity in a warehouse.
- **Payment:** `PaymentAttempt` is one attempt to collect payment; an Order may have multiple attempts.
- **Fulfillment:** `Shipment` is a package or delivery batch; there may be multiple Shipments for one Order.
- **Analytics:** `FactOrderLine` is a fact record at sales-line grain, not a behavioral aggregate.

| Rule/Fact | Authoritative Source | What Outsiders Are Permitted to Do |
| --- | --- | --- |
| Can the Order be CONFIRMED? | Sales/Order | Send command; read published outcomes |
| Can the warehouse hold the SKU? | Inventory | Send `ReserveStock`; receive Reserved/Rejected |
| Has payment been CAPTURED? | Payment | Consume events / query by contract |
| Was the Shipment delivered successfully? | Fulfillment | Submit evidence; read confirmed status |
| Total value of goods sold per month? | Analytical model with explicit metrics | Aggregate/reconcile; never mutate operational sources |

**A shared database does not grant shared ownership.** Running two bounded contexts on the same PostgreSQL instance does not mean Inventory may edit `order_header`. Contexts should communicate through published APIs, events, or read models. When multiple aggregates genuinely require a shared local transaction, state dependencies and boundaries explicitly instead of silently merging them into a giant root.

`Order` typically holds `customerId` and `skuId` as **identity references**, rather than embedding the full `Customer` or `Product` aggregate. When purchase-time pricing is needed, store a **snapshot of the locked unit price**, because current Catalog prices must not rewrite past commitments. When a source's identity is unique only per tenant or partner, every mapping must preserve that namespace.

## 4. Domain Invariants Differ from Storage Constraints

Suppose Sales policy states:

1. Only an Order in `DRAFT` status with at least one line can be confirmed.
2. Line `quantity` is a positive integer; VND unit price is non-negative per this example's policy.
3. The total equals the sum of `quantity × unitPriceVnd` across all lines.
4. Once an Order is `CONFIRMED`, lines cannot be edited via normal operations.
5. Two confirm requests targeting the same version must not produce two successful state transitions.

| Rule | Domain | Storage | Exchange |
| --- | --- | --- | --- |
| Quantity > 0 | `OrderLine` constructor | `CHECK(quantity > 0)` | Input schema validation |
| Edit lines only in DRAFT | Aggregate root | Root version/lock on all write paths | Do not expose arbitrary `setLines` |
| Unique Order ID | `OrderId` | `PK(tenantId, orderId)` | Namespaced, stable `orderId` |
| Total matches lines | `totalVnd()` | Updated in same transaction; reconciliation checks | Only publish verified totals |
| No duplicate confirmation | State transition guard | Conditional UPDATE, optimistic version | Idempotency key for retries |
| No over-allocation | **Inventory** | Reservation transaction in Inventory | Separate `StockReserved` event |

**Domain validation does not replace concurrency control.** Two JVMs can simultaneously load a `DRAFT` Order and both see `confirm` as valid. The database must prevent two transactions from committing updates based on a stale version. Conversely, standard `CHECK` constraints cannot express every multi-row rule or hierarchical approval policy. The three layers reinforce each other.

## 5. Java 17 Example: A Domain Model Independent of SQL/HTTP

The abbreviated code below uses integer VND amounts. Multi-currency systems should define `Money(value, currency)` with dedicated scale/rounding rules; never use `double` for money.

~~~~java
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

record OrderId(UUID value) {
    OrderId { Objects.requireNonNull(value); }
}

record OrderLine(UUID lineId, UUID skuId,
                 int quantity, long unitPriceVnd) {
    OrderLine {
        Objects.requireNonNull(lineId);
        Objects.requireNonNull(skuId);
        if (quantity <= 0 || unitPriceVnd < 0) {
            throw new IllegalArgumentException("Invalid line");
        }
    }
    long amountVnd() {
        return Math.multiplyExact((long) quantity, unitPriceVnd);
    }
}

enum OrderStatus { DRAFT, CONFIRMED, CANCELLED }

record OrderConfirmed(UUID eventId, OrderId orderId,
                      long orderVersion, Instant occurredAt,
                      long totalVnd) {}

final class Order {
    private final OrderId id;
    private final UUID customerId;
    private final List<OrderLine> lines = new ArrayList<>();
    private OrderStatus status;
    private long version;

    private Order(OrderId id, UUID customerId,
                  OrderStatus status, long version) {
        this.id = Objects.requireNonNull(id);
        this.customerId = Objects.requireNonNull(customerId);
        this.status = Objects.requireNonNull(status);
        if (version < 0) throw new IllegalArgumentException("version");
        this.version = version;
    }

    static Order newDraft(OrderId id, UUID customerId) {
        return new Order(id, customerId, OrderStatus.DRAFT, 0);
    }

    // Repository restores persisted data; does not replay commands/events.
    static Order restore(OrderId id, UUID customerId,
            OrderStatus status, long version, List<OrderLine> stored) {
        var order = new Order(id, customerId, status, version);
        for (var line : List.copyOf(stored)) {
            Objects.requireNonNull(line);
            if (order.lines.stream()
                    .anyMatch(x -> x.lineId().equals(line.lineId()))) {
                throw new IllegalArgumentException("Duplicate line");
            }
            order.lines.add(line);
        }
        if (status == OrderStatus.CONFIRMED && order.lines.isEmpty()) {
            throw new IllegalArgumentException("Invalid persisted order");
        }
        order.totalVnd();
        return order;
    }

    void addLine(OrderLine line) {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Not editable");
        }
        Objects.requireNonNull(line);
        if (lines.stream().anyMatch(
                x -> x.lineId().equals(line.lineId()))) {
            throw new IllegalArgumentException("Duplicate line");
        }
        Math.addExact(totalVnd(), line.amountVnd());
        lines.add(line);
        version++;
    }

    OrderConfirmed confirm(UUID eventId, Instant occurredAt) {
        if (status != OrderStatus.DRAFT || lines.isEmpty()) {
            throw new IllegalStateException("Cannot confirm");
        }
        Objects.requireNonNull(eventId);
        Objects.requireNonNull(occurredAt);
        long total = totalVnd();
        status = OrderStatus.CONFIRMED;
        version++;
        return new OrderConfirmed(eventId, id, version, occurredAt, total);
    }

    long totalVnd() {
        long total = 0;
        for (var line : lines) {
            total = Math.addExact(total, line.amountVnd());
        }
        return total;
    }

    List<OrderLine> lines() { return List.copyOf(lines); }
    OrderId id() { return id; }
    UUID customerId() { return customerId; }
    OrderStatus status() { return status; }
    long version() { return version; }
}
~~~~

`Order` encapsulates **business behavior**, with no unrestricted setters for mutating `status`/`total`. Version increments in memory as behavior executes, yet the repository must retain the **originalVersion** loaded from storage and compare against it when writing `finalVersion`. The `restore` method does not increment version or emit events, and its visibility should be restricted.

**The `OrderConfirmed` returned by `confirm` is only an in-memory object.** It cannot be treated as durably occurred if the transaction saving `Order` rolls back. The aggregate must not send HTTP requests, emails, or publish messages directly. The application/repository must persist the state alongside the publishing intent in a transaction before treating the event as a committed fact.

## 6. Storage Model: One Aggregate Spanning Multiple Tables

~~~~sql
CREATE SCHEMA IF NOT EXISTS sales;

CREATE TABLE sales.order_header (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    customer_id UUID NOT NULL,
    status VARCHAR(16) NOT NULL
        CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')),
    currency_code CHAR(3) NOT NULL DEFAULT 'VND'
        CHECK (currency_code = 'VND'),
    total_vnd BIGINT NOT NULL DEFAULT 0 CHECK (total_vnd >= 0),
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    confirmed_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, order_id),
    CHECK (status <> 'CONFIRMED' OR confirmed_at IS NOT NULL)
);

CREATE TABLE sales.order_line (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    line_id UUID NOT NULL,
    sku_id UUID NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_vnd BIGINT NOT NULL CHECK (unit_price_vnd >= 0),
    PRIMARY KEY (tenant_id, order_id, line_id),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES sales.order_header (tenant_id, order_id)
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
        REFERENCES sales.order_header (tenant_id, order_id)
);

CREATE INDEX orders_by_customer
    ON sales.order_header (tenant_id, customer_id, created_at DESC);

CREATE INDEX outbox_unpublished
    ON sales.outbox_event (created_at, event_id)
    WHERE published_at IS NULL;
~~~~

The FK protects the existence of an `Order` for every `OrderLine`. `CHECK` constraints enforce positive quantities and non-negative prices. However, a `CHECK` on `order_header` **cannot natively verify a sum across multiple child rows** in standard SQL. If you materialize `total_vnd` for performance, every write path editing lines must update the total in the same transaction or rely on purpose-built triggers/procedures/reconciliation. Never allow external scripts to bypass the root arbitrarily.

### Confirmation Transaction and Outbox Write

Suppose the repository loads a `DRAFT` Order at version 6, invokes `confirm()`, and obtains version 7; lines already exist and have been validated:

~~~~sql
BEGIN;

UPDATE sales.order_header
SET status = 'CONFIRMED',
    total_vnd = :verified_total_vnd,
    confirmed_at = :occurred_at,
    version = :new_version
WHERE tenant_id = :tenant_id
  AND order_id = :order_id
  AND status = 'DRAFT'
  AND version = :expected_version
  AND :new_version > :expected_version
RETURNING version;

-- If not exactly 1 row: ROLLBACK, do not write outbox.
-- verified_total_vnd is computed from the aggregate's lines.

INSERT INTO sales.outbox_event (
    event_id, tenant_id, aggregate_id, aggregate_version,
    event_type, schema_version, occurred_at, payload
) VALUES (
    :event_id, :tenant_id, :order_id, :new_version,
    'sales.order-confirmed', 1, :occurred_at,
    jsonb_build_object(
        'orderId', :order_id,
        'totalVnd', :verified_total_vnd_text,
        'currency', 'VND'
    )
);

COMMIT;
~~~~

Only COMMIT when the UPDATE returns exactly one row and the outbox INSERT succeeds. Both the `BIGINT` total and the string total in the payload must come from **the same domain calculation**; never accept two independent totals from the client. If a command also modifies `OrderLine` rows in the same use case, those changes must be persisted inside this same transaction, guarding the initial `expectedVersion`.

Committing `Order` and the outbox together prevents the failure mode where an Order is `CONFIRMED` but a crash loses **the intent to publish the event**. It **does not by itself guarantee** that the broker or consumers receive or apply the event exactly once. Moreover, a transaction in Sales **cannot span** Inventory or Payment residing in separate databases.

## 7. Mapping Domain ↔ Storage and Domain → DTO

| Domain | Storage | Rule |
| --- | --- | --- |
| `OrderId` | `order_header.order_id` UUID | Preserve ID, paired with `tenant_id` |
| Referenced `CustomerId` | `order_header.customer_id` UUID | Do not embed `Customer` aggregate |
| `OrderStatus` | `order_header.status` VARCHAR | Map valid statuses; do not invent ad-hoc enum values |
| `OrderLine` | Multiple `order_line` rows | Validate identity, quantity, unit price on load |
| `totalVnd` | `total_vnd` BIGINT | If cached, must stay synchronized with line sum |
| `Version` | `order_header.version` | `expectedVersion` on load, `finalVersion` after command |
| `OrderConfirmed` | `outbox_event` | Map internal event to published contract |
| `confirmedAt` | `order_header.confirmed_at` | Business timestamp, not consumer receipt time |

The **write path** uses the repository to load the aggregate, invoke behavior, and commit. The **read path** can map SQL/query models directly to DTOs for display without rehydrating the entire aggregate when no state mutation is intended.

~~~~java
import java.util.List;
import java.util.UUID;

record OrderLineView(UUID skuId, int quantity, String unitPriceVnd) {}

record OrderView(UUID orderId, String status, String totalVnd,
                 String currency, List<OrderLineView> lines) {
    OrderView { lines = List.copyOf(lines); }
}

final class OrderViewMapper {
    static OrderView fromDomain(Order order) {
        var views = order.lines().stream()
            .map(line -> new OrderLineView(
                line.skuId(), line.quantity(),
                Long.toString(line.unitPriceVnd())))
            .toList();
        return new OrderView(
            order.id().value(),
            order.status().name(),
            Long.toString(order.totalVnd()),
            "VND",
            views);
    }
}
~~~~

This example serializes VND integer amounts as **strings** to avoid precision loss in JavaScript clients for integers exceeding safe limits. Real contracts must specify unit, currency, scale, and rounding rules. Renaming column `total_vnd` does not force clients to rename field `totalVnd`.

The mapper must never silently drop corrupt `OrderLine` rows to construct an apparently valid aggregate. If storage contains an unknown status, duplicate lines, negative prices, or mismatched tenants, raise an alert and handle corrupted data through controlled remediation.

## 8. Synchronous Exchange Model: REST Commands and Responses

An API should not turn storage into a table for external callers to edit. Instead of letting clients send `PATCH status=CONFIRMED`, expose a meaningful command:

~~~~http
POST /v1/orders/6cb1d299-4fd0-4f39-ab95-195db8ffed82/confirm HTTP/1.1
Authorization: Bearer [access-token]
Idempotency-Key: 18f2fe65-b7ee-4d9f-9f9e-65f560125d52
Content-Type: application/json

{}
~~~~

Example response after a successful transaction:

~~~~json
{
  "orderId": "6cb1d299-4fd0-4f39-ab95-195db8ffed82",
  "status": "CONFIRMED",
  "totalVnd": "1250000",
  "currency": "VND",
  "version": 7
}
~~~~

**Idempotency-Key** identifies **the caller's command intent** when retrying after a timeout—not `orderId` and not `eventId`. The system must scope the key to the caller/tenant, operation type, and request payload, persisting the outcome durably for the contract retention window. Retrying with the same key and payload does not trigger a new transition; reusing the same key with a different payload must return a conflict error.

| Scenario | Appropriate Response / Semantics | Mistake to Avoid |
| --- | --- | --- |
| Caller lacks permission to view/confirm Order | Authorization / tenant scope error | Trusting client-supplied `orderId`/`tenantId` blindly |
| Order is `CANCELLED` | Domain conflict | Using a setter to force `CONFIRMED` |
| Order has no lines | Rule violation | Emitting an event and letting consumers validate later |
| Two concurrent confirms on same version | One commits; the other sees conflict / already handled | Uncontrolled state overwrite |
| Client times out after commit | Retry or query using stable key | Treating every retry as a brand-new command |
| Inventory has not yet returned reservation outcome | Appropriate pending/workflow status | Claiming stock is reserved merely because Sales confirmed |

API version **v1** is completely distinct from **Order version=7**. `v1` describes the HTTP contract; `version=7` is an aggregate version supporting optimistic concurrency. Changing API pagination does not necessitate changing `Order`; bumping `Order` from version 7 to 8 does not bump the URL to `v8`.

### An API Request Is Not an Entity

Receiving valid JSON is **input format validation**, not a business decision. The application service authenticates the actor, tenant, and permissions, loads `Order` from the repository, invokes `confirm()`, and saves. An API DTO must not accept a client-supplied `totalMoney` field and bypass the locked line prices.

A response can intentionally omit `customerId`, address details, and internal key structures if the caller is unauthorized to see them or does not need them for the use case.

## 9. Asynchronous Exchange Model: Events and Outbox

From the domain event `OrderConfirmed`, the producer can map an integration event for consumers:

~~~~json
{
  "eventId": "a74acf66-f904-4f90-a82b-1716ad0c7a16",
  "eventType": "sales.order-confirmed",
  "schemaVersion": 1,
  "producer": "sales",
  "tenantId": "8b15ae84-f427-45d4-a949-1a6fcb3f5b17",
  "aggregateId": "6cb1d299-4fd0-4f39-ab95-195db8ffed82",
  "aggregateVersion": 7,
  "occurredAt": "2026-11-22T03:00:00Z",
  "correlationId": "4f77ce91-8352-463d-b4be-29a353a1c029",
  "payload": {
    "orderId": "6cb1d299-4fd0-4f39-ab95-195db8ffed82",
    "totalVnd": "1250000",
    "currency": "VND"
  }
}
~~~~

**Why use an envelope?**

| Field | Role | Do Not Confuse With |
| --- | --- | --- |
| `eventId` | Unique identifier of an emitted occurrence | `orderId`, broker `messageId` |
| `aggregateId` | The Order object that changed | `eventId` |
| `aggregateVersion` | Change sequence of one Order per source policy | System-wide total order |
| `schemaVersion` | Version of the event contract | Order state version |
| `occurredAt` | Business timestamp per authoritative source | `receivedAt`, `publishedAt` |
| `correlationId` | Links steps belonging to the same workflow | Idempotency key or deduplication key |
| `tenantId` / `producer` | Namespace and emitting context | Proof that caller has access rights |
| `payload` | Published facts | Serialization of all internal columns |

**OrderConfirmed ≠ StockReserved ≠ PaymentCaptured.** Sales's event does not prove stock is available or payment has been collected. Inventory receives a fact and independently decides whether to reserve stock under its own rules; if stock is insufficient, it can respond with `StockReservationRejected`. Payment maintains its own transaction lifecycle.

### Commit First, Publish After

~~~~mermaid
sequenceDiagram
    participant S as Sales Application
    participant DB as Sales DB
    participant R as Outbox Relay
    participant B as Broker
    participant N as Notification

    S->>DB: Transaction: Order CONFIRMED + outbox E1
    DB-->>S: COMMIT succeeded
    R->>DB: Read unpublished events
    R->>B: Publish eventId E1
    B->>N: Deliver E1
    N->>N: Dedup + apply local side effect
    N-->>B: ACK after local commit
    B->>N: May redeliver E1
    N->>N: Ignore duplicate side effect
~~~~

If the relay publishes successfully and crashes before marking the row published, the broker/consumer may receive **duplicates of the same eventId**. An outbox typically delivers **at-least-once**, and does not automatically provide end-to-end exactly-once semantics.

A consumer can store `processed_event(consumer_name, eventId)` with a unique key; the processed record and **local business state changes** must commit in the same transaction. If the side effect sends an email or calls a payment gateway outside the transaction, appropriate idempotency/protocols are still needed at the external service. No deduplication table can turn an external HTTP call into a local ACID operation.

### Ordering and Timing

Two events for the same Order may reach a consumer out of order due to retries, multiple partitions, or parallel relays. `aggregateVersion` helps detect stale messages or gaps **within the scope of one Order**, though you must still define rules for missing events and never assume every version bump produces exactly one integration event. You can partition by `aggregateId` or use authoritative source snapshots to rebuild projections. Timestamps alone do not prove global ordering.

## 10. Do Not Confuse Commands, Domain Events, CDC, and Analytical Facts

| Artifact | What Does It Express? | What Does It Mean to Recipients? |
| --- | --- | --- |
| **Command ConfirmOrder** | Desire for the system to perform an action | Not guaranteed to succeed |
| **Domain event OrderConfirmed** | Business fact that just occurred | Only treated as durable after commit |
| **Integration event sales.order-confirmed** | Fact published under a contract outside Sales | Consumers react per agreed semantics |
| **API response OrderView** | An authorized state snapshot for display | Can change due to subsequent commands |
| **Persistence row order_header** | State in physical storage | Must not be equated with the entire aggregate |
| **CDC row update** | Committed table INSERT/UPDATE/DELETE | Not automatically a domain event |
| **Audit record** | Who did what, when, and why per audit policy | Not necessarily a state reconstruction source |
| **Analytical fact** | A measurement at a defined grain | Holds no authority to execute commands |

A command might emit multiple events or zero events if rejected. A single UPDATE might be a small technical step among several mutations in one business transaction. Change Data Capture (CDC) is useful for synchronizing tables, yet an UPDATE that bumps a version without changing business state does not automatically become `OrderConfirmed`.

If a system uses **event sourcing**, the event stream is the source of truth from which state is reconstructed by design; that is a different architectural decision from having an outbox and a few domain events. Do not label an application as event-sourced merely because it stores status history or emits messages.

## 11. Anti-Corruption Layer: Translating Meaning When Integrating Partners

A shipping partner exposes an API:

~~~~json
{
  "shipmentNo": "SHP-1020",
  "state": "DONE",
  "trackingStatus": "SIGNED",
  "eventTime": "2026-11-22T10:00:00+07"
}
~~~~

From `state=DONE` alone, you do not know whether it means **delivered to customer**, **handed over to carrier**, or **ticket closed**. If in the Fulfillment domain `DELIVERED` requires proof of delivery, blindly mapping `DONE → DELIVERED` fabricates a false fact.

An **Anti-Corruption Layer (ACL)** is a semantic translation layer protecting internal models from external vocabulary, IDs, and structures. It must:

1. Identify the partner API source/version, `shipmentNo` identifier scope, and tenant.
2. Consult documentation on `DONE`/`SIGNED` semantics to verify whether delivery actually completed.
3. Convert `eventTime` with its offset into an `Instant`, keeping `receivedAt` separate.
4. Map `externalShipmentId` to the internal `ShipmentId` via a verified relation.
5. Issue a **conditional command**, such as `RecordProofOfDelivery`, so the `Shipment` root validates state transitions itself.
6. Upon encountering an unknown status or missing evidence, return an error, quarantine, or reconcile—never assign `DELIVERED` blindly.

~~~~mermaid
flowchart LR
    EXT["Partner event<br/>DONE / SIGNED"] --> ACL["Adapter / ACL<br/>validate + translate"]
    ACL --> CMD["Internal command<br/>RecordProofOfDelivery"]
    CMD --> DOM["Shipment aggregate<br/>delivery invariants"]
    DOM --> DB[("Repository + transaction")]
~~~~

An ACL also handles:

- **Units:** grams → kilograms, VND → cents or foreign currency as defined; never convert numbers while keeping old labels.
- **Identity:** the same `externalId` can collide between two partners.
- **Statuses:** one external status may correspond to multiple internal statuses depending on supporting evidence.
- **Timestamps:** local datetimes without an offset are ambiguous; never assume UTC.
- **Null/missing:** an omitted field does not default to `0` or mean the value was deleted.
- **Versions:** a partner's v2 response may change field semantics while keeping v1 field names.

ACLs are equally useful when integrating a **legacy system inside the same monolith**; a network boundary is not a prerequisite.

## 12. Cross-Boundary Consistency and Intermediate States

A simple UI action may orchestrate multiple authoritative sources:

~~~~mermaid
sequenceDiagram
    participant U as Customer
    participant S as Sales
    participant I as Inventory
    participant P as Payment
    U->>S: PlaceOrder
    S->>S: Save Order PENDING_STOCK
    S->>I: ReserveStock(requestId, sku, qty)
    I->>I: Transaction reserves stock if available
    I-->>S: StockReserved / Rejected
    S->>S: Transition STOCK_HELD if Reserved
    S->>P: AuthorizePayment(commandId)
    P-->>S: PaymentAuthorized / Rejected
    S->>S: Confirm if conditions pass
    S-->>U: Workflow result
~~~~

This is **one illustrative orchestration**, not the only commercial workflow. Some systems confirm an Order before reserving stock; others require reservation prior to confirmation. Every choice must specify **which state the system commits to at each step**.

You cannot use Sales's local transaction to roll back stock reserved by Inventory in another database. If Payment fails after `ReserveStock`, you need `ReleaseReservation` as an authorized, idempotent compensating command—do not call that a cross-service SQL ROLLBACK.

| Risk | Required Design |
| --- | --- |
| Sales sends `ReserveStock` and times out, unsure if it succeeded? | Stable idempotency key; query status by key/`reservationId` |
| Inventory reserves successfully, but the response is lost | Safe retry without reserving extra stock |
| Payment reports late success after Order was cancelled | Workflow states, refund/compensation policy, reconciliation |
| Events for the same Order arrive out of order | Per-Order sequence/version and gap handling |
| Worker crashes between saving state and sending message | Transactional outbox/inbox or equivalent durable mechanism |
| Two services believe they own the same field | Reassign authoritative source; prohibit arbitrary dual writes |

**Eventual consistency does not mean invariants may be temporarily wrong.** Inventory must enforce its no-over-allocation invariant **at the authoritative source**. Sales's read model may lag in learning about `StockReserved`; that is a copy-freshness issue, not permission for the warehouse to exceed stock limits.

## 13. Read and Analytical Models: Another Perspective with Its Own Grain

A system can optimize read/analytical paths separately from write paths:

| Need | Appropriate Grain | Source and Limitations |
| --- | --- | --- |
| View current Order status | One `OrderSummary` | Read projection or Order source; state freshness |
| Count how many times Orders were confirmed | One unique `OrderConfirmed` event | Deduplicate `eventId`; define business date |
| Paid goods value by SKU | One eligible sales line | Needs Payment/Order facts, locked unit price snapshot |
| Analyze payment attempt counts | One `PaymentAttempt` | Never count attempts as new orders |
| Delivery duration | One fulfillment instance | Requested/packed/delivered milestones |

**`OrderConfirmed` is not paid revenue.** If you sum `OrderConfirmed` as revenue, uncaptured orders, cancellations, refunds, or partial shipments can distort KPIs. Every fact must clearly define its **grain, measure, timestamp, and recognition state**.

~~~~mermaid
flowchart LR
    SRC["Authoritative Order / Payment source"]
    MSG["Committed events / CDC"]
    STG["Staging<br/>validate, dedup, map grain"]
    MART["Fact + Dimension<br/>historical read model"]
    BI["Dashboard<br/>metric version + freshness"]
    SRC --> MSG
    MSG --> STG
    STG --> MART
    MART --> BI
~~~~

A warehouse can store SCD Type 2 or price snapshots, using columnar storage and partitioning for fast aggregations. This **does not force** OLTP `Order` storage or the `OrderView` API to share the same structure. Read paths can denormalize, while write paths must still follow invariant ownership.

## 14. Comparing Modeling Approaches Across Storage Technologies

The three models—domain, storage, exchange—**do not mandate three separate databases**. The same domain may use relational, document, graph, or analytical storage; storage decisions should rest on invariants and real workloads.

| Storage Type | Candidate Representation | Strengths | What Must Be Evaluated |
| --- | --- | --- | --- |
| **Relational** | `OrderHeader`, `OrderLine`, FK, UNIQUE, CHECK, outbox | Multi-row transactions, constraints, structured queries | Locks/isolation, indexes, contention, schema lifecycle |
| **Document** | An `Order` document holding lines, version, and metadata | Convenient retrieval of members within one aggregate | Document size limits, atomic updates, multi-document changes |
| **Graph** | `Order`/`Customer`/`Product` nodes and edges between them | Multi-hop traversal, paths, rich relationships | Edges do not automatically grant aggregate write authority or global ACID |
| **Analytical/Columnar** | `FactOrderLine`, `DimProduct`, `DimDate`, snapshots | Scans, grouping, compression, long history | Grain, late data, CDC; not a place to enforce write commands |

### 14.1. Relational: One Aggregate Can Span Multiple Tables

An `Order` may consist of a header row and multiple line rows while still forming **one logical aggregate** whose behavior is controlled by its root. The repository uses a transaction to protect joint updates. Conversely, even when two aggregates live in the same database, they do not necessarily belong in the same object graph or the same transaction for every operation.

**Physical relationships do not imply ownership relationships.** An FK from `order_line` to `order_header` indicates that lines belong to the Order, whereas a `customer_id` referencing a `Customer` in another context may only retain an ID and linkage contract; cross-database/cross-service FKs are not always appropriate or enforceable.

### 14.2. Document: One Document Is Not Automatically One Aggregate

A document embedding a bounded list of lines can be convenient when reads/writes target the `Order` and the engine supports required atomic updates. However, if an order accumulates unbounded history or lines are updated concurrently at high frequency, a large document becomes a contention hotspot and wastes bandwidth.

If Inventory and Payment live in different documents or clusters, updating an `Order` document does not automatically ensure stock was reserved or payment collected. Consistency must be grounded in the product's actual transaction capabilities or cross-context workflows.

### 14.3. Graph: Traversal Does Not Mean Mutation Authority

A graph `Customer → Order → Product` helps discover relationship paths. It does not mean the `Customer` aggregate is allowed to mutate every `Order` or `Product` along an edge. The domain still dictates which root owns invariants, while the graph is simply a storage/query model suited to relationship-heavy workloads.

### 14.4. Analytics: Denormalization for Reads, Not Write Authority

A fact table may store snapshots of price, sales region, and customer segment for fast queries. That does not prove those dimensions belong inside the sales write aggregate. On the write path, Sales still protects locked prices and order status; the warehouse simply provides an interpretation with clear versioning, timing, and freshness.

**The design question is not "pick SQL or NoSQL and shape the domain around it"**, but rather "which invariants must hold, which queries dominate, and which engine enforces them safely at appropriate cost".

## 15. Evolving Domain, Storage, and Contracts Independently

Three kinds of changes can happen independently:

1. **Domain change:** adding an approval step or `AWAITING_STOCK` status; requires reviewing behavior and invariants.
2. **Storage change:** splitting tables, adding indexes, partitioning data, changing how totals are stored; API can stay unchanged.
3. **Contract change:** adding API/event fields, updating a public enum, or changing timestamp formatting; must consider existing consumers.

| Change | What Can Stay Stable? | Key Risk |
| --- | --- | --- |
| Partition `OrderLine` from one table into many partitions | Domain `Order` and REST `OrderView` | Repository mapping, keys/transactions |
| Add optional `confirmedAt` field to response | `Order` behavior and schema if already stored | Clients handling unknown fields |
| Event adds `currency` | Domain if `Money` already exists | Legacy consumers and default values |
| Change `CONFIRMED` meaning from Sales-accepted to Payment-captured | **Do not** keep the name while silently changing meaning | Breaks entire workflows and KPIs |
| Change `totalVnd` from VND to thousands of VND while keeping field name | **Incompatible** | Financial errors and corrupted history |
| Analytics switches `dim_product` from Type 1 to Type 2 | Sales domain can stay unchanged | Historical mapping and fact keys |

### 15.1. Expand → Migrate → Contract

When migrating without disrupting multi-version systems:

1. **Expand:** add new columns/tables/contracts in a compatible form; do not delete old fields yet.
2. **Migrate/backfill:** move data, verify counts, keys, monetary amounts, statuses, and NULLs.
3. **Adapt:** if dual-read/dual-write is needed during transition, designate the authoritative source, reconciliation strategy, and conflict handling; avoid uncontrolled parallel writes.
4. **Switch:** route repositories/queries to the new model; measure errors, latency, data drift, and rollback readiness.
5. **Contract:** remove legacy structures only after all required producers and consumers have migrated.

For event contracts, **adding optional fields** is generally less disruptive than removing or renaming required fields, provided consumers ignore unknown fields or handle defaults per contract. Changing the **meaning** or **unit** of a field is a breaking change even if JSON parsers still accept the payload.

### 15.2. Never Serialize an ORM Entity as an API Contract

A JPA/Hibernate entity may contain lazy associations, soft-delete flags, internal audit columns, password hashes, or database-coupled structures. Returning the entity directly can:

- expose data beyond authorization scope;
- trigger N+1 queries as the serializer traverses relationships;
- cause circular references or oversized responses;
- turn internal schema refactorings into breaking API changes;
- let default serializers format timestamps or money contrary to contract.

Dedicated DTOs control published content and insulate callers when domain/storage changes. Still, you do not need a unique DTO for every method if the same contract shares stable meaning, permissions, and lifecycle.

## 16. Cross-Boundary Conventions: IDs, Time, Money, Security

### 16.1. Identifiers and Namespaces

- `orderId`, `paymentAttemptId`, `shipmentId`, `eventId`, and `requestId` play **distinct roles**.
- IDs may be unique only per tenant or per producer. When integrating multiple sources, preserve explicit namespaces or mappings.
- Warehouse surrogate keys are not public business IDs by default. Reloading a dimension and regenerating surrogate keys must not affect external events or APIs.
- Cross-context ID references must validate existence and permissions via protocol; do not assume FKs can always span independent databases.

### 16.2. Distinct Timestamps

| Field | Definition | Do Not Substitute With |
| --- | --- | --- |
| `occurredAt` | Business event confirmed as occurred | Time broker received message |
| `recordedAt` | Source persisted the event | Reporting date in another timezone |
| `publishedAt` | Relay published the message | Domain decision time |
| `receivedAt` | Consumer received the message | `occurredAt` |
| `businessDate` | Calendar/analytical cutoff date | UTC date if policy uses local time |

An order paid at 23:59 Vietnam time and processed by CDC at 00:05 the next day still belongs to the **defined payment date** per `paidAt`, unless a metric explicitly measures processing date. Every contract must specify format, offset, timezone, and correction policy.

### 16.3. Money and Measurements

- Use `amount` + `currency`, explicitly specifying whole VND, minor units, or decimals.
- Avoid `double`/`float` in financial calculations; choose exact types and rounding rules.
- Never sum revenue across two currencies without explicit exchange rates and effective timestamps.
- Do not equate `authorized`, `captured`, `refunded`, `gross`, and `net` merely because all are monetary numbers.
- When a DTO exposes `total`, specify which **status** and which price snapshot that total represents.

### 16.4. Access Control, Tenants, and Sensitive Data

`tenantId` is a **scoping field**, not proof that the caller is authorized. Authenticate producers/callers, verify ownership, and restrict returned fields by role. Never broadcast card numbers, addresses, phone numbers, or HR details into events consumed by many subscribers without clear necessity and authorization.

Outboxes, brokers, logs, warehouses, and backups can retain multiple copies; each location needs retention policies, encryption/access controls, and appropriate deletion/anonymization workflows. An exchange contract that is schema-stable yet leaks personal data is a failed boundary design.

## 17. Testing Boundaries, Not Just Getters/Setters

| Test Level | Scenario | Expected Outcome |
| --- | --- | --- |
| Domain unit | Confirm empty Order | Rejected; no `Confirmed` fact produced |
| Domain unit | `addLine` after `CONFIRMED` | State and version unchanged |
| Domain unit | Negative quantity or `long` overflow on multiplication | Clear error; internal state unmutated |
| Repository integration | Save and reload multi-line Order | Exact IDs, lines, total, state, and version |
| Concurrency integration | Two confirm requests using same `expectedVersion` | At most one transaction succeeds |
| Transaction integration | Outbox INSERT fails after header UPDATE | Order rolled back; no committed event |
| API contract | Client sends unsupported `status`/`total` | Mutating beyond use case is blocked |
| Event contract | Consumer v1 receives payload missing required field | Defined contract error or adapter behavior |
| Consumer integration | Broker redelivers same `eventId` | Business side effect not duplicated |
| ACL integration | Partner sends `DONE` lacking delivery proof | `Shipment` not marked `DELIVERED` |
| Analytics | One Order with three lines, two `PaymentAttempt`s | Revenue not multiplied during JOINs |
| Security | Tenant B caller guesses tenant A `orderId` | Denied; no data leaked |
| Migration | Storage structure changes while API stays unchanged | Contract continues working; reconciliation matches |

**Contract tests do not just verify that JSON parses.** They also verify enum meanings, currency/units, timestamp formats, ID namespaces, idempotency, required/optional fields, unpublished fields, and handling of new versions.

Concurrency tests must run against a **real database with realistic isolation**, because sequential mock repositories hide lost updates, deadlocks, or `UNIQUE` conflicts. If a transaction touches multiple rows, tests must assert the **final state** of all affected tables and the outbox—not just HTTP status codes.

### Suggested Contract Evolution Testing Strategy

An effective technique is **producer/consumer contract tests**. Producers verify new payloads still honor published contracts; consumers verify they can read all supported versions. During migrations, running tests against real production-like datasets reveals more than testing a single neat sample object.

Beyond automated tests, monitor rates of quarantined messages, mapping failures, idempotency conflicts, outbox lag, and data-reconciliation discrepancies to catch real-world failures early.

## 18. Practice Exercise: Hotel Booking

**Context:** A booking platform has bounded contexts for Booking, Inventory (RoomAvailability), Payment, and Analytics. A guest reserves a room for three nights, pays, and receives a confirmed Booking. Rates vary seasonally; a Booking may span multiple rooms or be cancelled/refunded. A legacy partner sets `PAID=Y` right after payment **authorization**, before funds are necessarily captured.

### Requirements

1. List entities/value objects of the `Booking` domain, three invariants `Booking` must enforce, and one invariant belonging to `Inventory`.
2. Propose `booking_header` and `booking_night` tables with PKs, FKs, tenant, per-night price snapshots, status, and version. If a guest books **two rooms of the same type for one night**, how do grain and keys change?
3. Sketch the `ConfirmBooking` REST command, response DTO, and `booking.confirmed` integration event with `schemaVersion`. Which fields should not be broadcast to every subscriber?
4. Does `RoomsReserved` from Inventory prove `PaymentCaptured`? If a Payment event arrives late or duplicated, how should Booking handle it?
5. What state should the ACL translate legacy `PAID=Y` into, and what should it do when evidence is missing?
6. If `BookingNight` moves from SQL rows to an embedded list inside a `Booking` document, must domain and API change alongside the schema? What must be checked regarding atomicity, document size, and concurrency?
7. Analytics wants to count confirmed bookings per day and the value of room nights **actually stayed** per day. Do they share the same grain? Can `booking.confirmed.totalVnd` be used directly as stayed revenue?
8. List at least four tests covering last-room contention, command/event retries, rate changes after lock-in, currency mismatches, and cross-tenant access.

### Suggested Solution

**Domain Booking:** `Booking` root with `BookingNight`/`StayPeriod`/`PriceSnapshot`, statuses `DRAFT`, `HELD`, `CONFIRMED`, `CANCELLED`, and guarded methods. `Booking` enforces check-in before check-out, valid night counts, accepted price snapshots, and valid state transitions. **Inventory** enforces never allocating rooms beyond availability per `(hotel, roomType, stayDate)`; `Booking` never decrements Inventory stock directly.

**Storage:** `booking_header(tenantId, bookingId, guestId, status, currency, version)`, `booking_night(tenantId, bookingId, nightLineId, stayDate, roomTypeId, quantity, nightlyPrice)`. If each booking permits only one room type per night, a natural key could use `stayDate+roomTypeId`; when multiple separate allocations exist, `lineId` prevents incorrect merging. Accepted price snapshots do not change when Catalog updates rates the next day.

**Exchange:** `ConfirmBooking` is a command. `BookingConfirmed` is a fact published only after commit, carrying `bookingId`, `tenantId`, `eventId`, `schemaVersion`, `occurredAt`, and verified `amount`/`currency`. Do not broadcast government IDs, card numbers, or full guest profiles to every consumer.

**Coordination:** `RoomsReserved` proves Inventory held rooms per policy, **not** `PaymentCaptured`. Duplicate events require deduplication and command retries require idempotency. If `PaymentConfirmed` arrives late after the booking was cancelled, follow defined reconciliation and refund/compensation rules rather than silently flipping the booking to `CONFIRMED`.

**ACL:** If legacy `PAID=Y` means authorized, map it only to `AUTHORIZED`—never `CAPTURED`. When source documentation is unclear, place it into an undetermined/quarantined state and verify instead of guessing.

**Analytics:** `fact_booking_confirmed` has a grain of one valid confirmation of a Booking; `fact_stayed_room_night` has a grain of one room-night / actual stay unit. Confirmation date and stay date differ; `BookingConfirmed` value is not automatically recognized revenue for services delivered. Cancellations, refunds, and adjustments have separate sources and measures.

## 19. Design Workflow and Handover Checklist

When tasked with "store and share data X", follow this sequence:

1. Write the **business language** and bounded context: what X means and which source is authoritative.
2. Document **invariants and when they must hold**, then identify the responsible aggregate root / domain service.
3. Choose **storage** based on transactions and queries: tables, documents, keys, FKs, CHECKs, versions, indexes, partitions.
4. Implement **repository mappings** for identity, status, and derived data; never expose persistence entities as public contracts.
5. Design **exchange contracts** per consumer/use case: commands, responses, events, `schemaVersion`, and error contracts.
6. Define **synchronous/asynchronous behavior**: commits, outbox, retries, idempotency, ordering, pending states, and compensation.
7. Add **ACLs** for external models with differing semantics, units, or IDs.
8. Separate **read/analytics** by grain, metrics, freshness, permissions, and lineage.
9. Plan independent evolution of domain, storage, and contracts with migrations and tests.
10. Test concurrency failures, late-arriving data, unauthorized callers, and legacy contracts.

Checklist:

- Does the domain expose invariant-protecting behavior, or just setters on data structures?
- Which aggregate/bounded context **owns the decision**, and which sources are merely copies?
- Does storage enforce transactions, constraints, isolation, keys, and controlled write paths?
- Do mappings preserve IDs, tenants, currencies, timestamps, statuses, and versions accurately?
- Are REST DTOs/events designed for consumers' needs rather than raw ORM serialization?
- Are commands, events, CDC, audit records, and analytical facts properly distinguished?
- Do outbox and consumers handle retries, duplicates, out-of-order delivery, and rollbacks?
- Do multi-service protocols define intermediate states and explicit compensation workflows?
- Does the ACL translate **meaning** rather than just renaming fields?
- Can schema migrations roll out without forcing every client to change simultaneously?
- Do read models define grain, metrics, freshness, lineage, and matching privacy controls?
- Have the riskiest boundaries been tested against real data and real database engines?

**Conclusion:** The **domain model** protects **business meaning and invariants**; the **storage model** implements **keys, constraints, transactions, and performance**; and the **exchange model** maintains **stable, semantically explicit, access-controlled contracts** between parties. They can use different types and structures as long as mappings are accurate and decision authority is never swapped. Through clear ownership boundaries, properly scoped transactions, versioned contracts, ACLs, and compatibility tests, a system can integrate multiple data models while remaining evolvable and verifiable.
