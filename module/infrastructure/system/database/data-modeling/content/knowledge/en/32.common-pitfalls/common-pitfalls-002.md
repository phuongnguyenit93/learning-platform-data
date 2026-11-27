# Collapsing Java Classes, Storage Tables, and DTOs into a Single Model

## Learning Objectives

After this lesson, you will be able to:

- Recognize the **one-model-for-every-layer anti-pattern** when a single Java class simultaneously serves as domain object, ORM entity, request/response DTO, and integration payload.
- Explain why **the same business concept** does not mean the Java representation, storage relation, and exchange payload share the same **grain, lifecycle, write ownership, or compatibility contract**.
- Analyze failures around **invariants, mass assignment, data leakage, lazy loading, N+1 queries, JSON cycles, transactions, NULLs, money, time, and schema evolution**.
- Redesign the responsibilities of **aggregates/domain models, persistence models, command/query DTOs, integration events, and analytical facts** without introducing pointless pass-through layers.
- Write illustrative Java 17, PostgreSQL, and decoupled mapper code while properly preserving identity, tenant isolation, monetary precision, and optimistic versioning.
- Build an incremental refactoring plan for a system currently exposing entities directly through its API, maintaining backward compatibility without rewriting the codebase from scratch.
- Evaluate exceptions: when a simple CRUD tool **can use fewer layers**, and when separation is mandatory due to risk or semantic divergence.
- Test those boundaries through domain unit tests, API security tests, contract tests, transaction/concurrency tests, migration checks, and reporting reconciliation.

The **DATABASE_DATA_MODELING** module builds the skill of translating business requirements into clear data models—entities, relationships, constraints, normalization, keys, indexes, and physical schemas—while comparing relational, document, graph, and analytical storage. In the **Common Pitfalls** chapter, this lesson focuses on a pervasive mistake: **turning a single Java class into the sole canonical structure and forcing the database, HTTP API, and integration messages to conform to it**.

This does not mean "everywhere must always have the exact same five layers." You separate when **responsibilities and semantics differ**; conversely, a very simple CRUD tool may keep several representations close together. The real issue lies in **accidentally sharing write ownership, lifecycles, and contracts**, not in annotation names or class counts.

## 1. Scenario: One Order Class Used for Everything

Suppose Sales manages customer orders. According to illustrative business requirements:

1. Each Order belongs to exactly one tenant; an Order has multiple OrderLines.
2. Each line has a SKU, a positive quantity, and a **unit price in VND locked at placement time**.
3. A DRAFT Order can add lines. A CONFIRMED Order must not have lines modified through normal commands.
4. Total amount is the sum of quantity × unitPriceVnd across all valid lines.
5. Clients can issue commands to create and confirm orders, but **must never set status, total amount, tenant, or permissions directly**.
6. The API displays orders to their owners; the OrderConfirmed event for Inventory/Notification should publish only what consumers need.

A deceptively quick approach:

~~~java
// WRONG EXAMPLE: anti-pattern illustration, do not copy into production.
@Entity
@Table(name = "orders")
public class Order {
    @Id
    public UUID id;

    public UUID tenantId;
    public UUID customerId;
    public String status;
    public long totalVnd;
    public String customerPhone;
    public String internalRiskNote;
    public long version;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    public List<OrderLine> lines;
}

// WRONG EXAMPLE: framework binds the entire entity from JSON and returns the entity directly.
@PostMapping("/orders")
public Order create(@RequestBody Order incoming) {
    return orderRepository.save(incoming);
}
~~~

The snippet uses JPA/Spring annotations to illustrate the flawed structure, **not as a complete runnable application**. Notable defects:

- A client can try sending **status=CONFIRMED**, an **arbitrary totalVnd**, a **different tenantId**, or **internalRiskNote**; if binding and save do not block them, data integrity and authorization are bypassed. This is **mass assignment / over-posting**.
- There is no confirm() behavior guarding against empty orders, invalid states, or locked prices. **Public fields** allow mutation from anywhere.
- Returning the entity over HTTP can leak **customerPhone** and **internalRiskNote** into JSON responses or logs unless explicitly blocked.
- Accessing **lines** outside a transaction can trigger a LazyInitializationException, or cause **N+1 queries** when listing many Orders.
- A bidirectional Order ↔ OrderLine association can trigger **serialization cycles** as the JSON mapper traverses both sides.
- Renaming database columns or refactoring JPA relationships risks altering the API response structure even when API consumers requested no change.
- An entity may be **detached**, yet the API layer treats it as a "live business object" that can simply be mutated and saved.

In Spring/JPA, many mechanisms exist to restrict fields, permissions, and serialization; proper annotations can mitigate some risks. Still, **no single annotation solves the broader separation of semantics and lifecycles**.

## 2. Signs of the Anti-Pattern

| Codebase Symptom | Why It Is Concerning | Question to Ask |
| --- | --- | --- |
| Controller accepts **@RequestBody OrderEntity** | Grants write access to persistence fields outside the use case | Which fields is the client allowed to modify? |
| Controller returns **List<OrderEntity>** directly | Response depends on ORM mappings and object graph | Could this leak fields, cause N+1 queries, or throw lazy exceptions? |
| Domain service merely calls **setStatus("CONFIRMED")** | Invariants are replaced by arbitrary setters | Who checks prior state and order lines? |
| Entity holds dozens of reporting/read-only fields | Mixes read needs with business decisions | Do facts/KPIs share the same grain as the aggregate? |
| Every new SQL column becomes a JSON API field | Storage refactors destabilize contracts | Do consumers actually need this field? |
| Partner event arrives and triggers **save()** on entity | External callers implicitly write to internal state | Who owns the state? |
| Putting **@NotNull** on the entity for every field | Mixes use-case rules with existence constraints | Do CREATE, UPDATE, and REST responses share the same rules? |
| Using auto-increment DB **id** in every event/public API | Confuses surrogate key with business/external ID | Does the ID survive warehouse moves or reloads? |
| Storing **passwordHash/PII** on entities serialized to JSON | Leaks sensitive data when endpoints or fields expand | Is exposed content controlled by role? |
| Altering OLTP tables just because the UI needs a new field | Designs storage around UI screens instead of invariants/queries | Can a separate read projection or DTO serve this? |

**Seeing @Entity inside a domain package does not automatically prove the design is broken.** Small projects can remain safe with simpler structures. Inspect **actual behavior, write permissions, public contracts, lifecycles, and tests** before deciding to split.

## 3. Why the Same Name "Order" Does Not Mean the Same Model

Distinguish at least five roles:

| Representation | Question It Answers | Grain / Lifecycle | Who Has Authority to Change It? |
| --- | --- | --- | --- |
| **Domain Order** | When can lines be added, confirmed, or canceled? | One Order aggregate, business lifecycle | Commands on the root enforcing invariants |
| **Persistence model** | Which tables, keys, and transactions persist/read it? | One order_header and multiple order_line rows | Controlled repository and migrations |
| **Command DTO** | What action does the caller want, with which inputs? | One HTTP/API request | Authenticated and authorized caller |
| **Response DTO** | Which data may the caller see, and in what shape? | One snapshot serving a read use case | API producer owning the contract |
| **Integration event** | Which committed fact must be broadcast? | One occurrence with eventId and schemaVersion | Authoritative producer |
| **Analytical fact** | At what grain is a measure counted or summed? | E.g., one paid sales line | ETL/BI following source/metric rules |

An Order with **three lines** does not mean an API response needs three separate SQL-shaped payloads; it can return one JSON object containing lines[]. Conversely, a fact table at the **OrderLine** grain must have three rows to SUM by SKU—you cannot use a single Order aggregate row and pretend you have SKU-level grain.

**There is no mandatory one-to-one mapping:**

~~~mermaid
flowchart TB
    REQUEST["ConfirmOrderRequest<br/>client command"]
    APP["Application service<br/>auth, transaction"]
    DOMAIN["Domain Order<br/>behavior + invariants"]
    ROWS[("Storage<br/>order_header + order_line")]
    VIEW["OrderView DTO<br/>published fields"]
    OUTBOX[("Outbox event<br/>OrderConfirmedV1")]
    CONSUMER["Inventory / Notification"]
    FACT["FactPaidOrderLine<br/>different grain"]
    REQUEST --> APP
    APP --> DOMAIN
    DOMAIN <-->|"Repository mapping"| ROWS
    APP --> VIEW
    APP --> OUTBOX
    OUTBOX --> CONSUMER
    ROWS --> FACT
~~~

Domain and storage models often live together inside **the same application**, yet cross-boundary exchanges should have independent contracts. The read path can map SQL queries straight to OrderView without rehydrating the aggregate if no state changes.

## 4. Pitfall One: Losing Invariants and Decision Authority

Consider a forged request:

~~~json
{
  "id": "cd6755f2-57cc-48a1-a68a-ef822b629a09",
  "tenantId": "a6389ce1-2bfd-4dbc-9e9c-abdc21ed1509",
  "customerId": "4d9f2611-98c5-4dca-8962-1c45f2b36cb7",
  "status": "CONFIRMED",
  "totalVnd": 100,
  "internalRiskNote": "approved"
}
~~~

If the controller deserializes the request directly into an entity and calls save(), it can inadvertently:

- Allow the caller to **change tenantId** to access another tenant's data if repositories/queries do not block it.
- Allow the caller to **change customerId** after the Order already exists.
- Persist **status=CONFIRMED** with zero OrderLines.
- Persist a total of **100 VND** that disagrees with locked lines.
- Allow editing **internalRiskNote** even though that field belongs strictly to internal risk controls.

This is an **access control and invariant failure**—it is not fixed merely by changing fields from public to private if setters and auto-mappers still copy everything blindly.

### Commands Must Carry Allowed Inputs, Not Every Column

Instead of accepting an OrderEntity, the API can define:

- **CreateOrderRequest:** desired product/SKU and quantity; never accepts client-supplied status or total.
- **AddOrderLineRequest:** SKU/quantity, optional reference price if the domain permits; authoritative unit price is looked up and verified before writing.
- **ConfirmOrderRequest:** idempotencyKey/expectedVersion if required by contract; never accepts totalVnd or an arbitrary status field.
- **OrderView:** orderId, status, money breakdown, and visible lines permitted for the caller's role.

The application extracts actor and tenant from a **trusted security context**, never trusting a bare tenantId in the body. The domain checks rules; storage guards transactions and concurrent writes. **DTO validation is an input filter, not a substitute for domain rules**.

## 5. Pitfall Two: The ORM Graph Becomes the HTTP Contract

In JPA/Hibernate, associations load **lazily** or **eagerly** depending on mapping configuration. If a JSON serializer traverses them, the API shape depends on the persistence context state:

~~~text
GET /orders?status=CONFIRMED
  -> SELECT orders ...                 (1 query)
  -> serializer reads order.lines      (potentially N queries)
  -> serializer reads line.product     (potentially more queries)
  -> line.order points back to order   (potential cycle)
~~~

**N+1** occurs when an initial query fetches N Orders and then fires N (or more) follow-up queries to load each Order's associations. The root issue is not that JPA always runs N+1, but that **letting the serializer decide which data gets loaded** makes performance and access control unpredictable.

Annotations like @JsonIgnore, @JsonManagedReference/@JsonBackReference, or Hibernate module settings address specific symptoms yet leave **the response contract coupled to the ORM graph**. Changing a fetch strategy for database performance can inadvertently alter what consumers receive.

### Designing Intentional Read Paths

A repository can expose:

- **loadForCommand(tenantId, orderId):** rehydrates the aggregate and lines needed to enforce invariants.
- **findOrderSummary(tenantId, orderId):** queries a projection containing only display fields.
- **listOrders(tenantId, pageSize, cursor):** returns summary rows without loading all lines or customer details.
- **findOrderLines(tenantId, orderId):** paginates lines per use case when needed.

Thus **queries are chosen by use case**, not by serializer traversal. You may use JDBC, JPQL projections, native SQL, Spring Data interface projections, or other tools; the goal is explicit **queries, contracts, and permissions**.

## 6. Pitfall Three: Changing Tables Breaks the API, Changing the API Distorts Tables

Eventually the business wants to split a single **order** table into **order_header + order_line**, or add history/partitioned tables for performance. If JSON responses simply serialize entities, splitting tables and changing relation mappings can:

1. Unintentionally rename JSON fields or paths.
2. Trigger lazy exceptions or N+1 loads when fetching lines.
3. Expose technical columns like row_version or deleted_at.
4. Force every client to upgrade in lockstep with database migrations.
5. Prevent the database team from refactoring internals out of fear of breaking the API.

The reverse is equally dangerous: just because the web UI needs a "customer name" field, developers add customer_name to order_header and let every command update it, even though it could come from a read model and customer names evolve under different rules.

**Rule:** persistence schemas are driven by **invariants, transactions, data, and query patterns**; DTOs are driven by **use cases and contracts**. Every change needs explicit mapping and a compatibility plan rather than automatic field copying disguised as synchronization.

## 7. Details With the Same Name but Different Meanings

Many shared-model bugs do not show up in basic CRUD; they surface only when business rules evolve, multiple tenants are onboarded, or external systems integrate.

| Detail | In the Domain | In Storage | In DTOs / Events |
| --- | --- | --- | --- |
| **Identity** | OrderId stable within a scope | May use composite PK/UUID/surrogate key | Public ID and namespace defined by contract |
| **Tenant** | Ownership boundary | Included in keys, FKs, indexes, Row Level Security if used | Client-supplied field never grants authority |
| **Version** | Preserves observed state against stale writes | row_version/optimistic locking | ETag/expectedVersion if needed; event schemaVersion is **different** |
| **Money** | Units, currency, invariants, exact math | BIGINT smallest unit or NUMERIC per policy | Often decimal strings to avoid client precision loss |
| **Timestamp** | confirmedAt is a business occurrence | TIMESTAMPTZ storing Instant per policy | Offset ISO 8601; never substitute receivedAt for occurredAt |
| **NULL** | May mean absent/unknown/not applicable | NULL semantics governed by constraints | Omitted field vs. JSON null can express **two distinct intents** |
| **Status** | State machine and valid commands | Column/constraint protecting stored values | Public versioned status codes, not raw setters |
| **Sensitive info** | Owned and governed data | Encrypted, access-controlled, retention-managed | Exposed strictly per role and purpose |

### 7.1. Public IDs Do Not Equal Physical Primary Keys

A table may use a BIGINT identity internally for storage and join efficiency, while public APIs expose UUID/ULID or stable business IDs. If data migrates to another store, surrogate keys can change; consumers must not depend on them. Every ID must state its uniqueness scope: global, per-tenant, or per-source.

### 7.2. Money Should Not Be a Casual Double

In the domain, 100,000 VND can be stored as a **long integer in VND**, while the API serializes the string "100000". Across multiple currencies, use amount+currency alongside scale and rounding policies; summing two currencies cannot be treated as a single scalar measure. Just because an ORM persists a double field does not make it fit for accounting.

### 7.3. Tri-State Semantics in PATCH

For updating delivery contact details:

~~~json
{}
~~~

can mean **leave the phone number unchanged**; whereas:

~~~json
{ "phone": null }
~~~

can mean **clear the phone number**, if the domain permits. Meanwhile:

~~~json
{ "phone": "" }
~~~

may be an invalid value. If everything binds to an entity with a nullable phone field followed by save(), many mappers erase the distinction between **omitted / explicit NULL / empty string**. You need a command/patch DTO capable of expressing tri-state intent (e.g., presence flags, JsonNullable, or JSON Patch per contract) and domain policy to enforce what is allowed.

### 7.4. Cached Columns Are Not Free-Form Truth

A total_vnd column kept for read performance is a **derived value**. If the domain exposes a public setter for total and clients supply it, a transaction can persist a total that disagrees with line sums. It requires source rules, calculation logic, and reconciliation—not just an @Column annotation.

## 8. A Standalone Java Domain Model With Behavior

The following Java 17 snippet is a **trimmed domain illustration**, independent of JPA, HTTP, or message brokers. Timestamps and IDs are supplied by the application after validation, with overflow checks included. Real systems may require price books, promotions, taxes, and multiple currencies.

~~~java
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

record OrderId(UUID value) {
    OrderId { Objects.requireNonNull(value); }
}

record OrderLine(int lineNo, UUID skuId, int quantity, long unitPriceVnd) {
    OrderLine {
        Objects.requireNonNull(skuId);
        if (lineNo <= 0 || quantity <= 0 || unitPriceVnd < 0) {
            throw new IllegalArgumentException("Invalid order line");
        }
    }

    long amountVnd() {
        return Math.multiplyExact((long) quantity, unitPriceVnd);
    }
}

enum OrderStatus { DRAFT, CONFIRMED, CANCELLED }

record OrderConfirmed(UUID eventId, OrderId orderId, long orderVersion,
                      Instant occurredAt, long totalVnd) {
    OrderConfirmed {
        Objects.requireNonNull(eventId);
        Objects.requireNonNull(orderId);
        Objects.requireNonNull(occurredAt);
    }
}

final class SalesOrder {
    private final OrderId id;
    private final UUID customerId;
    private final List<OrderLine> lines = new ArrayList<>();
    private OrderStatus status;
    private long version;

    private SalesOrder(OrderId id, UUID customerId,
                       OrderStatus status, long version) {
        this.id = Objects.requireNonNull(id);
        this.customerId = Objects.requireNonNull(customerId);
        this.status = Objects.requireNonNull(status);
        if (version < 0) throw new IllegalArgumentException("version");
        this.version = version;
    }

    static SalesOrder create(OrderId id, UUID customerId) {
        return new SalesOrder(id, customerId, OrderStatus.DRAFT, 0);
    }

    // Only repositories may use this controlled restoration path.
    static SalesOrder restore(OrderId id, UUID customerId,
                              OrderStatus status, long version,
                              List<OrderLine> storedLines) {
        var order = new SalesOrder(id, customerId, status, version);
        for (var line : List.copyOf(storedLines)) {
            Objects.requireNonNull(line);
            if (order.lines.stream()
                    .anyMatch(x -> x.lineNo() == line.lineNo())) {
                throw new IllegalArgumentException("Duplicate line");
            }
            order.lines.add(line); // restore without invoking command
        }
        if (status == OrderStatus.CONFIRMED && order.lines.isEmpty()) {
            throw new IllegalArgumentException("Invalid persisted order");
        }
        order.totalVnd(); // detect overflow in persisted data
        return order;
    }

    void addLine(OrderLine line) {
        requireDraft();
        Objects.requireNonNull(line);
        if (lines.stream().anyMatch(x -> x.lineNo() == line.lineNo())) {
            throw new IllegalArgumentException("Duplicate line");
        }
        Math.addExact(totalVnd(), line.amountVnd()); // check before mutating
        lines.add(line);
        version++;
    }

    OrderConfirmed confirm(UUID eventId, Instant when) {
        requireDraft();
        Objects.requireNonNull(eventId);
        Objects.requireNonNull(when);
        if (lines.isEmpty()) {
            throw new IllegalStateException("Empty order");
        }
        long total = totalVnd();
        status = OrderStatus.CONFIRMED;
        version++;
        return new OrderConfirmed(eventId, id, version, when, total);
    }

    long totalVnd() {
        long sum = 0;
        for (var line : lines) {
            sum = Math.addExact(sum, line.amountVnd());
        }
        return sum;
    }

    List<OrderLine> lines() { return List.copyOf(lines); }
    OrderId id() { return id; }
    UUID customerId() { return customerId; }
    OrderStatus status() { return status; }
    long version() { return version; }

    private void requireDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Not editable");
        }
    }
}
~~~

**Boundary explanation:**

- SalesOrder owns state transitions; there is no status setter in the API.
- OrderLine holds a price snapshot; changing the Catalog price tomorrow does not alter past Order totals.
- totalVnd() is computed from lines, never taken from client-supplied JSON.
- restore() rehydrates from storage and **does not replay addLine/confirm**, since doing so would bump versions and emit fake events.
- confirm() returns an **in-memory domain event**, not yet a published integration event. If the database transaction fails, the fact never committed.
- The example omits tenant inside the root because it focuses purely on Order invariants. The application and repository **must** bind the tenant from the trusted context on every load and save.

If Order accumulates too many behaviors or long-running transactions, revisit aggregate boundaries. Do not use "DTO separation" as an excuse to bundle Inventory and Payment inside SalesOrder.

## 9. Relational Storage Designed Around Grain and Transactions

PostgreSQL can represent one Order aggregate across multiple tables:

~~~sql
CREATE SCHEMA IF NOT EXISTS sales;

CREATE TABLE sales.order_header (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    customer_id UUID NOT NULL,
    status VARCHAR(16) NOT NULL
        CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')),
    total_vnd BIGINT NOT NULL DEFAULT 0 CHECK (total_vnd >= 0),
    row_version BIGINT NOT NULL DEFAULT 0 CHECK (row_version >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    confirmed_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, order_id),
    CHECK (status <> 'CONFIRMED' OR confirmed_at IS NOT NULL)
);

CREATE TABLE sales.order_line (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    sku_id UUID NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_vnd BIGINT NOT NULL CHECK (unit_price_vnd >= 0),
    PRIMARY KEY (tenant_id, order_id, line_no),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES sales.order_header(tenant_id, order_id)
);

CREATE INDEX orders_by_customer
    ON sales.order_header (tenant_id, customer_id, created_at DESC);

CREATE TABLE sales.order_outbox (
    event_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    schema_version INTEGER NOT NULL CHECK (schema_version > 0),
    occurred_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ,
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES sales.order_header(tenant_id, order_id)
);

CREATE INDEX order_outbox_pending
    ON sales.order_outbox (created_at, event_id)
    WHERE published_at IS NULL;
~~~

The **grain** of order_header is one Order keyed by (tenantId, orderId). The grain of order_line is one OrderLine keyed by (tenantId, orderId, lineNo). **One aggregate spanning multiple rows** is completely normal; a JPA entity or SQL row does not define an aggregate one-to-one.

### Which Rules Does the Database Enforce?

| Rule | Suggested Mechanism | Limitation |
| --- | --- | --- |
| No duplicate order/line keys | PK/UNIQUE | Does not verify whether the actor has write permission |
| Line must belong to an Order | FK | Does not enforce DRAFT/CONFIRMED rules |
| Quantity > 0, non-negative price | CHECK | Unaware of Catalog pricing rules |
| State transition from DRAFT | Conditional UPDATE + version | Requires every write path to obey the protocol |
| Header total equals line sum | Domain + transaction + reconciliation or suitable triggers | CHECK constraints generally cannot inspect sums of child rows |
| No duplicate events for one occurrence | Event ID and idempotency key | EventId alone fails if retries generate fresh UUIDs |

A request modifying an OrderLine must lock or compare **row_version on the Order root** so a confirmation cannot commit against stale lines while another worker edits them. If only confirm checks header version while scripts freely mutate order_line independently, total/line invariants **are not fully protected**.

### Atomic State Update and Outbox Write

Suppose the repository loads the Order at row_version=6, and domain confirm advances to version=7:

~~~sql
BEGIN;

UPDATE sales.order_header
SET status = 'CONFIRMED',
    total_vnd = :verified_total_vnd,
    confirmed_at = :confirmed_at,
    row_version = :new_version
WHERE tenant_id = :tenant_id
  AND order_id = :order_id
  AND status = 'DRAFT'
  AND row_version = :original_version
  AND :new_version > :original_version
RETURNING row_version;

-- If 0 rows are returned, the application must ROLLBACK and handle the conflict.
-- verified_total_vnd comes from lines verified and guarded by the same
-- transaction/version protocol, never from the client.

INSERT INTO sales.order_outbox (
    event_id, tenant_id, order_id, aggregate_version,
    event_type, schema_version, occurred_at, payload
) VALUES (
    :event_id, :tenant_id, :order_id, :new_version,
    'sales.order-confirmed', 1, :confirmed_at,
    jsonb_build_object(
        'orderId', :order_id,
        'totalVnd', :verified_total_text,
        'currency', 'VND'
    )
);

COMMIT;
~~~

This SQL illustrates **a confirm command assuming lines are already persisted stably**; if the command also adds/edits lines, the repository must write them in the same transaction and keep the root version consistent. Only COMMIT when UPDATE returns **exactly one row** and the outbox INSERT succeeds. If the two writes do not commit together, OrderConfirmed could be published despite a rollback, or the order could confirm without publishing.

The outbox guarantees atomicity **inside the Sales database**, not that Inventory has reserved stock or Payment has captured funds. Consumers still need idempotency because brokers can redeliver messages.

## 10. Persistence Rows and Java DTOs Separated from the Domain

You do not have to create one JPA class per table and reuse it as a DTO. You can define **persistence projections** or records representing SQL row shapes:

~~~java
import java.time.Instant;
import java.util.UUID;

record OrderHeaderRow(
    UUID tenantId, UUID orderId, UUID customerId,
    String status, long totalVnd, long rowVersion,
    Instant confirmedAt) {}

record OrderLineRow(
    UUID tenantId, UUID orderId, int lineNo,
    UUID skuId, int quantity, long unitPriceVnd) {}
~~~

A JDBC/JPA repository can map loaded rows into SalesOrder:

~~~java
import java.util.List;

// Illustrative mapping after the repository has loaded all required rows.
final class OrderPersistenceMapper {
    static SalesOrder restoreDomain(
            OrderHeaderRow header, List<OrderLineRow> rows) {
        var lines = rows.stream().map(row -> {
            if (!row.tenantId().equals(header.tenantId())
                    || !row.orderId().equals(header.orderId())) {
                throw new IllegalStateException("Cross-order row");
            }
            return new OrderLine(
                row.lineNo(), row.skuId(), row.quantity(),
                row.unitPriceVnd());
        }).toList();

        var domain = SalesOrder.restore(
            new OrderId(header.orderId()), header.customerId(),
            OrderStatus.valueOf(header.status()),
            header.rowVersion(), lines);
        if (domain.totalVnd() != header.totalVnd()) {
            throw new IllegalStateException("Stored total mismatch");
        }
        return domain;
    }
}
~~~

This mapper assumes the persistence and domain records live in the same module; a single code block is not a standalone compilable Java project. The repository must also verify **tenant scope, completeness of the line set, transaction state, and load ordering**. A **Stored total mismatch** error must be investigated or repaired via a data-fix workflow—never silently overwrite the stored total and proceed with a critical command.

### Display-Purpose DTOs

~~~java
import java.util.List;
import java.util.UUID;

record OrderLineView(
    UUID skuId, int quantity, String unitPriceVnd) {}

record OrderView(
    UUID orderId, String status,
    String totalVnd, String currency,
    List<OrderLineView> lines) {
    OrderView { lines = List.copyOf(lines); }
}

final class OrderViewMapper {
    static OrderView fromDomain(SalesOrder order) {
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
~~~

Here **row_version, tenant_id, and internalRiskNote are not automatically exposed in the response**. That is a use-case choice rather than a rule that every API must hide versions. If a client needs optimistic updates, expose expectedVersion or an ETag with **explicit semantics**; published fields are decided by the API contract, not by accidentally residing on a table.

**Meaningful mapping directions:**

~~~text
HTTP input DTO
  → syntax validation + auth + application command
  → domain behavior
  → repository maps domain to persistence writes
  → transaction commit
  → response DTO / integration event

Read-only query
  → SQL projection / read model
  → authorized and formatted response DTO
~~~

There is no need to invoke domain behavior to build a read-only report; nor should a free-form read DTO **write back** into an aggregate.

## 11. Request/Response DTOs Must Describe Behavior, Not Columns

An API can separate requests such as:

~~~java
import java.util.UUID;

record AddOrderLineRequest(UUID skuId, int quantity) {}

record ConfirmOrderRequest(UUID commandId, long expectedVersion) {}
~~~

**AddOrderLineRequest** omits unitPriceVnd when Sales must look up authoritative prices from the price book. If a use case permits negotiated pricing, the request may include a proposed price, yet **the domain/application still requires an approval rule**, never blindly copying it as the locked unit price.

**ConfirmOrderRequest** carries expectedVersion to catch stale reads and commandId/idempotencyKey for safe retries; **it never carries status=CONFIRMED**. The endpoint can look like:

~~~http
POST /v1/orders/6cb1d299-4fd0-4f39-ab95-195db8ffed82/confirm HTTP/1.1
Authorization: Bearer [access-token]
Idempotency-Key: 18f2fe65-b7ee-4d9f-9f9e-65f560125d52
Content-Type: application/json

{
  "expectedVersion": 6
}
~~~

The application layer executes:

1. Authenticate caller and extract tenantId/permissions from the trusted security context.
2. Look up the idempotency key scoped by tenant/caller/command; reject if an existing key is reused with a different payload.
3. Load the Order by tenantId and orderId from the repository, guarding state and version.
4. Invoke **domain confirm()**, never a status setter.
5. Persist state and outbox in the same transaction; verify the updated row count.
6. Return a response containing confirmed state/totals or handle conflicts—never return a JPA entity.

### Why Not Use One DTO for Create, Update, and Read?

| Use Case | Required Fields | Fields the Caller Must Never Supply |
| --- | --- | --- |
| Create order | List of SKUs and intended quantities | status, totalVnd, confirmedAt, tenantId |
| Add line | SKU, quantity, expectedVersion if needed | Arbitrary database row_version, internalRiskNote |
| Confirm order | OrderId in URL, command ID / idempotency key | Client-chosen totalVnd, status, paidAt |
| View details | Permitted lines and totals | Internal fields or PII beyond caller's role |
| List orders | OrderId, status, total, and basic timestamps | No need to load full OrderLine graphs |

Multiple use cases can occasionally share a simple **value object/DTO** when semantics, permissions, and formats match. Yet **overlapping field names do not prove identical contracts**. A CreateRequest with mandatory fields requires different validation than an UpdateRequest where an omitted field means "leave unchanged."

### Put Validation in the Right Layer

- **Transport validation:** valid JSON syntax, parseable UUIDs, integer quantities, allowed fields only.
- **Authorization:** whether the actor is permitted to access that specific Order/tenant.
- **Domain validation:** whether state is DRAFT, lines are valid, totals do not overflow, and transitions are legal.
- **Persistence protection:** UNIQUE, FK, CHECK, transactions, version conditions, and DB privileges.
- **Integration contract validation:** schemaVersion, eventId, currency, timestamps, and required fields carry valid semantics.

Layers may repeat checks for defense-in-depth, while each retains clear ownership; do not dump everything into entity annotations and hope every write path invokes them.

## 12. Integration Events Are Not Entity JSON at save() Time

Suppose Sales wants to announce that an Order was confirmed:

~~~json
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
~~~

The event has an **envelope and consumer-oriented payload**, free of internalRiskNote, physical row_version, lazy ORM proxies, or the entire Customer profile. It represents a **committed fact**, unlike a ConfirmOrder command that may still be rejected.

| Field / Concept | Meaning | Pitfall When Sharing Entities |
| --- | --- | --- |
| eventId | Identifier for the occurrence of the fact | Retries generate a new UUID and consumers process twice |
| aggregateId | Order that changed | Using temporary row or ORM proxy IDs |
| aggregateVersion | Order state version | Confused with JSON schemaVersion |
| schemaVersion | Contract for consumer parsing | Changing fields on DB refactor without versioning |
| occurredAt | Producer business timestamp | Substituting broker receivedAt/publishedAt |
| payload | Minimal published facts | Serializing full Customer/Payment/Address graphs |
| tenantId, producer | Namespace and origin | Letting consumers treat unverified tenantId as authorization |

**Domain events differ from integration events:** a domain OrderConfirmed may remain internal, while a mapper translates it into a versioned, access-scoped integration contract. Renaming Java or ORM classes need not cause breaking event changes if external semantics remain intact.

### Outbox and Consumer Idempotency

A relay may publish an event and crash before marking it sent. Upon restart, it republishes **the exact same eventId**, rather than inventing a new business fact. Consumers should maintain a deduplication/inbox table committed alongside local state changes:

~~~sql
CREATE SCHEMA IF NOT EXISTS integration;

CREATE TABLE integration.processed_event (
    consumer_name TEXT NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Inside one transaction, the consumer attempts to INSERT into processed_event; if it already exists, skip applying local side effects again; if new, process, commit, and ACK. If sending emails or calling payment APIs **outside** the database transaction, you need target-side idempotency or a dedicated durable workflow. A processed_event table alone cannot turn an external HTTP call into an ACID transaction.

### Do Not Treat Every Row Change as a Domain Event

CDC can observe an UPDATE on order_header when:

- The Order is genuinely confirmed;
- a cached total column is recalculated;
- a migration backfills historical rows;
- an audit column is corrected;
- a write operation is retried.

Only business semantics and appropriate contract elements determine **whether an OrderConfirmed event occurred**. Mapping every JPA UPDATE to an "OrderUpdated" event carrying the entire entity leaves consumers unsure how to react and risks duplicate processing or sensitive-data exposure.

## 13. Analytical Facts Are Not Order Classes Copied to a Warehouse

Grain differences expose the limits of "one model":

| Object | Proper Grain | Example Measurement |
| --- | --- | --- |
| Order aggregate | One Order | Confirm/cancel behavior and order total |
| OrderLine storage | One line of an Order | SKU, quantity, snapshot unit price |
| OrderConfirmed event | One valid confirmation | Timestamp and event ID |
| FactPaidOrderLine | One line eligible for payment recognition | Gross/net/quantity by date and SKU |
| FactPaymentAttempt | One payment attempt | Attempt outcome, latency |
| DimProduct SCD2 | One product attribute version per effective interval | Category/name at the chosen point in time |

An Order with three lines corresponds to three FactPaidOrderLine rows. A failed PaymentAttempt **is not** a new order. OrderConfirmed **does not automatically imply** payment collected or accounting revenue recognized.

An example fact model:

~~~sql
CREATE SCHEMA IF NOT EXISTS mart;

CREATE TABLE mart.fact_paid_order_line (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    line_no INTEGER NOT NULL,
    sku_id UUID NOT NULL,
    paid_at TIMESTAMPTZ NOT NULL,
    business_date DATE NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    gross_goods_vnd BIGINT NOT NULL CHECK (gross_goods_vnd >= 0),
    net_paid_goods_vnd BIGINT NOT NULL
        CHECK (net_paid_goods_vnd >= 0),
    source_order_version BIGINT NOT NULL,
    transform_version INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, order_id, line_no),
    CHECK (net_paid_goods_vnd <= gross_goods_vnd)
);
~~~

This is an **illustrative schema where an OrderLine is recognized as paid exactly once**. If a line receives multiple captures or partial refunds, choose another grain—such as **one capture allocation** or a dedicated adjustment fact. Never cram multiple payments onto a single (Order, lineNo) key by overwriting without lineage.

### Wrong Joins Multiply Revenue

Suppose Order O-1 has two lines totaling 300,000 VND, and Payment has two attempts (one failed, one captured). Joining OrderLine to PaymentAttempt and running SUM(lineAmount) without filtering to the right attempt/grain can yield 600,000 VND.

Swapping OrderEntity for OrderDTO fixes nothing if the JOIN remains wrong. You must **declare the grain, pick the authoritative state source, and join only after aggregating accurately**:

~~~sql
-- On the cleaned fact: each PAID line appears exactly once.
SELECT business_date,
       SUM(net_paid_goods_vnd) AS paid_goods_vnd,
       COUNT(DISTINCT order_id) AS paid_orders
FROM mart.fact_paid_order_line
WHERE tenant_id = :tenant_id
  AND business_date >= DATE '2026-11-01'
  AND business_date < DATE '2026-12-01'
GROUP BY business_date
ORDER BY business_date;
~~~

COUNT(*) counts **paid lines**, not Orders. Daily COUNT(DISTINCT order_id) counts Orders with lines recognized on that date; if an Order spans multiple days, review the KPI definition and grain. Business date must follow timezone and cutoff policies, never defaulting to ETL ingest date.

**An analytical model can denormalize for query speed**, yet must never become the authority driving Order updates. Data marts have pipeline lag, corrections, and separate versions; they do not own the confirm command.

## 14. Across Storage Paradigms, the Same Mistake Persists

The single-model anti-pattern is not unique to JPA or SQL:

| Technology | Common "Shared Model" Form | Consequence | Design Direction |
| --- | --- | --- | --- |
| **Relational / JPA** | Table-mapped entity accepted/returned directly over REST | Field leaks, lazy graphs, setters bypassing invariants, migrations breaking APIs | Separate domain/DTO permissions, repositories, and projections |
| **Document database** | Internal JSON document doubles as the API JSON | Old clients/writers overwrite or strip new fields; missing versioning | Document schemas/versions, API DTOs, conditional updates |
| **Graph database** | Nodes/edges auto-exposed as public responses and mutation APIs | Graph leakage, mistaking edge traversal for ownership | Use-case-specific query/response graphs; domain roots remain |
| **Time-series** | One SensorReading class used for both ingestion and daily reports | Conflates raw/event time with aggregated buckets | Raw model, rollup grain, distinct timestamps |
| **Analytical warehouse** | Using ORM OrderEntity as the fact model | Wrong grain, multiplying joins, erased history | Facts/dimensions with explicit grain, metrics, and lineage |

### Document Databases Also Face Versioning Challenges

Old document:

~~~json
{
  "orderId": "O-101",
  "schemaVersion": 1,
  "totalVnd": 200000,
  "lines": [
    { "skuId": "P-1", "quantity": 2, "unitPriceVnd": 100000 }
  ]
}
~~~

A newer document adds discountPerUnitVnd and a reduced totalVnd. If an older writer reads and **replaces the entire document** using a POJO lacking the new field, it can silently erase the discount. Document models need version-aware readers, backward-compatible mappers, optimistic versioning/conditional updates, and rules preventing stale writers from mutating newer schema versions.

### Graphs Do Not Grant Cross-Context Authority

Nodes Customer → Order → Product serve multi-hop relationship queries, yet do not prove Customer has authority to edit all connected Orders and Products. Exposing raw graph nodes as DTOs for clients to PATCH edges can turn a search feature into overly broad mutation rights.

**Takeaway:** choosing relational, document, graph, or analytical engines changes storage and query mechanics—**it never removes the responsibility to separate domain, physical, and exchange models**.

## 15. When Do You Not Need Every Layer?

A small CRUD tool may not need multiple mappers and models. Layer separation is a **boundary-management tool**, not a file-count KPI.

For example, an internal admin utility managing a catalog of **unit-of-measure codes** with code, name, and active:

- All users share the same permission level, with no sensitive data.
- No complex invariants exist beyond unique code and non-empty name.
- No external consumers depend long-term on the API format.
- No independent write paths or multi-step state workflows exist.
- App and database deploy together, data volume is small, and migrations are trivial.

In this case, a data record or projection mirroring the table and DTO may suffice. You still need authorization checks, parameterized SQL, constraints, appropriate concurrency handling, and guardrails against exposing all system columns automatically.

### Decision Matrix for Separation Depth

| Question | If "Yes" | Recommended Action |
| --- | --- | --- |
| Is the API/event consumed by independent clients? | Contracts evolve slower than internal schemas | Separate exchange DTOs with versioning/compatibility |
| Are there PII/secrets or field-level permissions? | Entities are unsafe to serialize directly | Use role-based allowlisted DTOs |
| Are there state machines and transition invariants? | Setters can bypass business rules | Use domain behavior and commands |
| Does one aggregate span multiple tables/documents? | Not 1:1 with persistence model | Explicit repository mapping |
| Do reads and writes have different workloads? | Eager graphs slow lists; write models feel heavy | Dedicated read projections |
| Are multiple bounded contexts integrating? | The same word may mean different things | ACLs and dedicated command/event contracts |
| Are there analytical facts/dimensions? | Different grain and historical semantics | Semantic models independent of ORM entities |
| Do old and new binaries run concurrently during deploys? | Old writers can drop or corrupt new fields | Schema versions and compatibility tests |
| Is it just a small, stable internal CRUD tool? | Extra layers add little value | Keep it simple while guarding auth/constraints |

**Separate for real boundaries, not for pattern names.** A codebase with 15 classes that merely clone Order fields and map back and forth can still be messier than a simple model. Document **reasons for change, write ownership, and mapping rules**—that is where separation creates value.

### Supporting Techniques Are Not Substitutes for Design

- **MapStruct or hand-written mappers:** cut boilerplate, though name-based auto-mapping can miss fields whose meanings diverged.
- **Bean Validation:** useful for format checks and validation groups, yet cannot guard all stateful business transitions.
- **Jackson annotations:** can hide specific fields and break cycles, yet cannot turn a persistence entity into a stable public contract.
- **JPA @Version:** provides ORM optimistic locking, provided every write path (including native SQL and batch jobs) follows the same protocol.
- **CQRS / read projections:** helpful when read and write workloads diverge; does not mandate two databases or event sourcing.
- **Anti-corruption layers:** translate partner semantics rather than merely converting snake_case to camelCase.

## 16. Evolving Legacy Systems Incrementally Without a Rewrite

When legacy code uses OrderEntity for input and output, changing every API and class in one giant PR risks downtime or breaking clients. A sensible path:

### Step 1 — Map Every Path Using the Entity

Trace **flows**, not just class names:

- Which endpoints accept, return, or persist OrderEntity?
- Which schedulers, admin tools, or batch jobs call save()/merge()?
- Which serializers traverse lazy associations or expose raw fields?
- Which consumers parse entity JSON; are older mobile app versions still active?
- Do SQL scripts directly update status, total, or OrderLine rows?
- Which reports SELECT directly from OLTP tables or rely on rows for metrics?

**Output:** a matrix of caller → use case → permissions → current model → risk → owner. There is no need to paste every file into a doc; you need impact visibility so old writers are not overlooked.

### Step 2 — Pin Existing Contracts With Tests

Before modifying endpoints, capture the contract clients **actually rely on**:

~~~text
GET /v1/orders/{id}
  response fields currently used by consumers
  id/status/amount/timestamp formats and null handling
  403/404/409 error behavior per authorization scope

POST /v1/orders
  permitted input fields
  behavior when caller sends forbidden fields
  current retry/idempotency behavior
~~~

If an API previously leaked sensitive fields, **continuing to expose them is not a compatibility obligation**; remediate safely, assess impact, and notify affected consumers appropriately. For legitimate fields, new DTOs should preserve the v1 contract during the transition.

### Step 3 — Separate Response DTOs First, Keeping the Current Schema

Create OrderViewMapper or access-scoped SQL projections. Update controllers to **return only DTOs**, preventing serializers from walking entities. Verify client contracts, SQL query counts, pagination, and PII exposure.

Advantage: you typically achieve major security and evolvability gains **without touching the database**. This step can happen before complex domain aggregate refactoring.

### Step 4 — Separate Command DTOs and Restrict Inputs

Introduce CreateOrderRequest, AddLineRequest, and ConfirmOrderRequest at the application boundary. Enforce:

- input field allowlists per use case;
- tenant/actor derived from security context;
- idempotency/expectedVersion;
- never mapping status or total straight from requests into rows;
- checking state transitions through domain behavior.

**Never use reflection to copy every request field onto an entity**: that merely disguises the same anti-pattern. Explicit write mappers are clearer and easier to review.

### Step 5 — Rehydrate the Domain and Manage Transactions

You can keep existing tables while a new repository maps them to SalesOrder. The domain validates invariants; the repository applies originalVersion/row locks and writes atomically. Remaining write paths must be upgraded or blocked so rules cannot be bypassed.

If legacy totals were stored inaccurately or states look inconsistent, **never silently repair them during a read/load**. Route corrupted records through an audited reconciliation/migration program, keeping data repair separate from customer confirmation commands.

### Step 6 — Separate Integration Events and Read/Analytics Models

Emit integration events **only after commit** using an outbox or equivalent durable mechanism, complete with schemaVersion, consumer authorization, and idempotency. Add grain-appropriate facts and dimensions for analytics instead of deriving gross/paid metrics directly from ORM updates.

### Step 7 — Physical Migration via Expand–Migrate–Switch–Contract

When tables themselves must change:

1. **Expand:** add columns/tables in a form where old and new writers can coexist.
2. **Migrate/backfill:** transform data using documented rules; keep unknown where history is missing.
3. **Switch:** upgrade readers, writers, and consumers, reconcile data, and enable new features once dangerous legacy writers are gone.
4. **Contract:** drop old columns/tables only after verifying zero remaining dependencies and having a recovery plan.

Once records have been written under the new model, rolling back to an old binary unaware of new fields can **erase data**. Safer options may be rolling forward with a hotfix or temporarily pausing writes rather than simply reverting the container image.

### Transition Matrix

| Phase | Legacy JPA Entity | Dedicated DTOs | Dedicated Domain | New DB Schema |
| --- | --- | --- | --- | --- |
| Baseline | Read/write/API | No | No | No |
| Split responses | Still in repositories | **Contracted Read DTOs** | Not yet mandatory | No |
| Split commands | Storage layer only | Read + command DTOs | Initial behavior | No |
| Domain protection | Persistence only | All APIs via DTOs | **Aggregate enforces rules** | Possibly not yet |
| Expand schema | Persistence gets new mappers | Contract unchanged | Semantics preserved | Compatible columns/tables |
| Switch/contract | Never exposed externally | Versioned contracts | Controlled write paths | Reconciled new schema |

Each phase requires **regression tests** and rollout criteria. Do not declare victory simply because a package is named **domain** while controllers still accept entities and admin SQL scripts still bypass invariants.

## 17. Test Suite to Catch Bugs Before Production

| Test Category | Scenario | Expected Result |
| --- | --- | --- |
| **API security** | Client sends another tenantId, internalRiskNote, or status | Unauthorized assignment blocked; no sensitive data leaked |
| **API contract** | GET OrderView, POST ConfirmOrder v1 | Fields, formats, and errors match contract |
| **Serialization** | Entity with bidirectional and lazy associations | Controller returns DTO; no cycles or unexpected N+1 |
| **Domain unit** | Confirm an empty or CANCELLED Order | Rejected; state remains unchanged |
| **Domain unit** | Negative quantity, negative price, long overflow | Clear error before any write |
| **Repository mapping** | Load an Order with multiple lines | Correct ID, tenant, line count, total, and version |
| **Data corruption** | DB total disagrees with SUM(line) | Raises mismatch; never silently reconciles |
| **Concurrency** | Two confirms with the same originalVersion | At most one commits |
| **Transactional outbox** | Outbox INSERT fails after Order UPDATE | Entire Order transaction rolls back |
| **Consumer** | Broker redelivers the same eventId | Side effects are not duplicated |
| **HTTP PATCH** | Missing phone vs. phone=null vs. phone="" | Follows the three defined intents |
| **Read performance** | List 100 Orders with many lines each | Query count and latency bounded; no surprise graph loads |
| **Schema evolution** | Old and new apps reading newly added columns | No data loss or semantic drift |
| **Analytics grain** | Order with two lines and two payment attempts | Totals do not multiply after JOIN |
| **Cross-tenant** | Identical UUIDs assumed across two tenants | Never cross-joined or misread |

### Example Java Domain Unit Test

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class SalesOrderTest {
    @Test
    void cannotConfirmEmptyOrder() {
        var order = SalesOrder.create(new OrderId(UUID.randomUUID()),
                                      UUID.randomUUID());
        assertThrows(IllegalStateException.class, () ->
            order.confirm(UUID.randomUUID(), Instant.now()));
        assertEquals(OrderStatus.DRAFT, order.status());
    }

    @Test
    void confirmsAmountFromLinesNotRequestBody() {
        var order = SalesOrder.create(new OrderId(UUID.randomUUID()),
                                      UUID.randomUUID());
        order.addLine(new OrderLine(1, UUID.randomUUID(), 2, 100_000));
        order.addLine(new OrderLine(2, UUID.randomUUID(), 1, 50_000));
        var event = order.confirm(UUID.randomUUID(),
            Instant.parse("2026-11-22T03:00:00Z"));
        assertEquals(250_000L, event.totalVnd());
        assertEquals(OrderStatus.CONFIRMED, order.status());
    }

    @Test
    void rejectsLineMutationAfterConfirm() {
        var order = SalesOrder.create(new OrderId(UUID.randomUUID()),
                                      UUID.randomUUID());
        order.addLine(new OrderLine(1, UUID.randomUUID(), 1, 10_000));
        order.confirm(UUID.randomUUID(), Instant.now());
        assertThrows(IllegalStateException.class, () ->
            order.addLine(new OrderLine(2, UUID.randomUUID(), 1, 10_000)));
    }
}
~~~

These tests assume JUnit Jupiter is configured in the project and **illustrate domain testing only**. They do not prove the database blocks concurrent writes, REST does not leak PII, or messages are never duplicated; integration and contract tests must complement them.

### Concurrency Tests Require a Real Engine

With an Order at version=6 and status DRAFT:

~~~text
T1 loads Order version=6; T2 loads Order version=6
T1 confirms, UPDATE WHERE version=6 → 1 row
T1 INSERTS outbox, COMMITS
T2 confirms, UPDATE WHERE version=6 → 0 rows
T2 ROLLS BACK, returns conflict or appropriate idempotent result
Conclusion: only one transition commits and one corresponding business event exists
~~~

If T1 and T2 carry **the same idempotency key**, the application should match the request and return the already-processed outcome per contract. If they are two distinct commands, a version conflict is expected. Mock repositories returning the same in-memory entity **do not reflect real locking or isolation**, and cannot verify race safety.

### Post-Deployment Observability

Monitor additional signals:

- Requests carrying unexpected fields or blocked for mass assignment.
- 403/409 rates by endpoint, tenant, and client version.
- Query counts, p95 latency, and lazy-loading exceptions on list endpoints.
- Mismatches between header totals and line sums, orphan lines, and duplicate IDs.
- Optimistic locking conflicts and retry success rates.
- Outbox lag, consumer dead-letter queues, and event duplicates/gaps.
- Dashboard variances vs. source systems for the same tenant, cutoff, and metric version.

A system that already separated DTOs yet still exhibits these errors needs further investigation; **architecture labels alone never guarantee correctness**.

## 18. Hands-On Exercise: Event Ticketing System

### Context

A conference ticketing app currently uses **TicketBookingEntity** simultaneously as JPA entity, REST request/response, and JSON message:

~~~java
// PROBLEMATIC LEGACY CODE: illustrative only, do not use in production.
@Entity
class TicketBookingEntity {
    @Id
    public UUID bookingId;
    public UUID tenantId;
    public UUID customerId;
    public String customerEmail;
    public String status;            // DRAFT/HELD/PAID/CANCELLED
    public long totalPriceVnd;
    public String internalFraudFlag;
    @OneToMany(mappedBy = "booking")
    public List<TicketLineEntity> ticketLines;
}
~~~

Current controller:

~~~java
// PROBLEMATIC LEGACY CODE:
@PutMapping("/bookings/{bookingId}")
TicketBookingEntity save(@RequestBody TicketBookingEntity body) {
    return repository.save(body);
}
~~~

New requirements:

- Customers choose ticket types and quantities; prices are locked from a verified pricing policy.
- Seat capacity per ticket tier is managed by **TicketInventory**. **Booking** must never directly increment or decrement total venue capacity.
- Once Payment confirms collection of the exact amount, Booking may transition to PAID per allowed state rules; never trust status sent by the browser.
- Users can view only their own bookings; fraud analysts view internalFraudFlag through a dedicated use case and role.
- One Booking has multiple TicketLines; a paid Booking cannot have line prices arbitrarily altered.
- Notification requires a BookingPaid event; Analytics needs paid ticket counts by ticket type and unique Bookings per day.
- Older mobile app versions cannot upgrade immediately; changes must roll out incrementally without exposing new internal fields.

### Questions

1. Identify **at least six bugs** or risks in the legacy code, grouped by authorization, invariants, performance, compatibility, and data integrity.
2. Propose a **TicketBooking aggregate**, TicketLine value object, and invariants for DRAFT/HELD/PAID/CANCELLED states. Which bounded context owns the rule **"never oversell capacity"**?
3. Propose a **relational schema** with booking_header, booking_line, tenant composite keys, FKs, CHECKs, and versioning. Describe which writes belong in one transaction vs. cross-context protocols.
4. Design **CreateBookingRequest**, **PayBooking command**, and **BookingView**: which fields are writable, read-only, or excluded?
5. Design the **BookingPaidV1** integration event with eventId, bookingId, occurredAt, currency, paidTotalVnd, and schemaVersion. Why not send the raw TicketBookingEntity?
6. A Payment callback arrives twice; how do you prevent BookingPaid from being recorded twice and prevent duplicate emails? Distinguish local transactions from external side effects.
7. One Booking has two lines: 2 STANDARD tickets at 500,000 VND each and 1 VIP ticket at 1,000,000 VND. What is the total? Can Analytics take COUNT(*) from a ticket-line-grain fact to count **Bookings**?
8. Outline a plan to **separate DTOs first, domain and repositories next, and evolve the schema last**, including at least four mandatory tests.
9. One user sends PATCH with **customerEmail=null** while another request omits customerEmail completely. Do both always mean the same thing? Design a contract to distinguish them.
10. If the data warehouse stores only one row per Booking yet needs revenue broken down by ticketType, what is wrong with the grain and how must it be fixed?

### Reference Solutions

**1. Identifying flaws.** Browsers can tamper with status, total, tenantId, customerId, and internalFraudFlag; responses leak fraud flags and overly broad email data; ticketLines risks lazy exceptions, N+1 queries, and serialization cycles; entity layout breaks on migrations; PUT with entities easily overwrites new fields with NULL; there is no state machine or optimistic version check.

**2. Domain.** TicketBooking root exposes addTicket, requestHold, recordCapturedPayment, and cancel obeying state rules. TicketLine holds ticketType, quantity>0, unitPriceVnd≥0, locked price, and unique lineNo/lineId. PAID bookings reject normal line edits. TicketInventory owns the capacity invariant; Booking receives only a valid **reservation token/confirmation** per contract. Payment owns captured amounts, never unverified client callbacks.

**3. Storage.** booking_header uses PK(tenantId, bookingId), status, totalVnd, rowVersion, and relevant timestamps; booking_line uses PK(tenantId, bookingId, lineNo), FK to header, and CHECKs on quantity/price. When locking prices/totals, write lines and header inside one transaction with version checks. Reserving capacity in TicketInventory and capturing funds in Payment are **separate transactions** requiring idempotent commands, intermediate states, and compensation/reconciliation workflows.

**4. DTOs.** CreateBookingRequest accepts ticketType and quantity; the server resolves prices and authorization. PayBooking has no status=PAID setter and carries appropriate idempotency/expectedVersion fields. BookingView returns only bookingId, ticket lines, amounts, status, and timestamps the user is allowed to see. Exclude internalFraudFlag; include email only when justified by the use case and least-privilege rules.

**5. Events.** BookingPaidV1 publishes a committed fact with a stable eventId, bookingId, tenantId/producer scope, occurredAt, schemaVersion, amount, and currency—never exposing fraud flags or ORM graphs. The event does not automatically mean TicketInventory finalized seat allocation if that is a separate unfinished workflow.

**6. Retries.** Payment callbacks must be authenticated and reconciled against captureId/bookingId/tenantId/amount; persist PAID status and outbox atomically in a transaction. Retrying the same captureId must not record another payment. Notification deduplicates by eventId; if sending email happens outside the transaction, use an idempotency key / delivery state to minimize duplicates per policy.

**7. Calculations.** Total is \(2\times500.000 + 1\times1.000.000 = 2.000.000\) VND. A fact at the **ticket-line grain** has two rows for **one Booking**; COUNT(*) does not count Bookings. To count Bookings, use COUNT(DISTINCT bookingId) within the same tenant and period (with a clear date definition); to count tickets, use SUM(quantity).

**8. Refactoring.** Extract response DTOs to block sensitive fields and lazy graphs; extract request/command DTOs to prevent over-posting; introduce domain behavior and repository/transaction boundaries; then expand schema, migrate, reconcile, switch, and contract. Test mass assignment and cross-tenant access, invalid confirm/pay states, duplicate callbacks, optimistic lock contention, SQL rollback on outbox failure, event contracts, and grain-accurate dashboards.

**9. PATCH.** An omitted field can mean leave unchanged; JSON null can mean clear/delete if business rules permit. The contract must represent tri-state semantics explicitly rather than trusting nullable entity fields.

**10. Grain.** One row per Booking holding a grand total cannot break revenue down across multiple ticketTypes if only one ticketType field exists. You need a **TicketLine-grain fact or an allocation fact** with appropriate price/total snapshots. Joining a one-row Booking fact to multiple ticket lines and calling SUM(totalBooking) directly multiplies revenue.

## 19. Prevention Checklist and Conclusion

Before reusing a single Java class across multiple boundaries, ask:

- **Purpose:** is this class a behavioral aggregate, persistence row, command DTO, response DTO, or event?
- **Grain:** does an object/table/JSON share the exact same **unit of data** everywhere it is reused?
- **Ownership:** who is allowed to change status, price, tenant, email, or internal flags? Could a caller write forbidden fields?
- **Invariants:** do commands pass through the aggregate root, state machine, and transaction—or simply save() a client-supplied object?
- **Concurrent updates:** do all write paths obey the aggregate's optimistic version/locking protocol?
- **Money and time:** do amounts carry explicit currency/units; do timestamps declare authoritative sources and cutoffs?
- **NULL and PATCH:** are omitted, explicit null, and concrete values distinguished according to intent?
- **Security:** could PII, secrets, or internal flags leak into responses, logs, or events via serialization?
- **ORM graph:** could controllers trigger lazy exceptions, N+1 queries, circular references, or over-fetching?
- **Storage:** are PK/FK/CHECK/indexes/partitions driven by invariants and queries rather than blindly mirroring class fields?
- **Mapping:** are conversions verified for IDs, tenant, status, version, and money without silently masking corrupt data?
- **Contracts:** do REST APIs and events declare schemas/versions, backward compatibility, and clear semantic owners?
- **Outbox:** are facts committed before emitting events, and do consumers deduplicate and handle retries safely?
- **Analytics:** do facts use accurate grain, measures, and timestamps; do joins avoid multiplying figures; are lagged read models kept out of OLTP decisions?
- **Evolution:** can tables change while keeping APIs stable; can APIs evolve without breaking migrations; can old writers safely coexist with new data?
- **Separation depth:** are classes separated due to genuine differences in meaning, authority, and lifecycle—or merely to add boilerplate?
- **Testing:** do unit, DB concurrency, API security, contract, consumer idempotency, and data reconciliation tests cover real risks?

**Conclusion:** **A single business concept can take many representations**, and forcing Java classes, storage tables, HTTP DTOs, events, and analytical facts into one shared model routinely conflates **write authority, semantics, grain, and lifecycles**. The fallout goes beyond hard-to-maintain code: bypassed invariants, data leaks, slow queries, schema changes breaking APIs, duplicate events, and wrong reports. The remedy is to **define boundaries first**, place behavior where ownership lives, back storage with constraints and transactions, design purpose-built DTOs/contracts, and validate mappers—while staying pragmatic enough that tiny internal CRUD tools avoid needless class proliferation. The ultimate goal of **DATABASE_DATA_MODELING** is a data model that is **semantically clear, safe, verifiable, and evolvable**, regardless of Java file count.
