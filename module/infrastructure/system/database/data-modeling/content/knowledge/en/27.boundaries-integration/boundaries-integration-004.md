# Selecting Data to Publish and Avoiding Exposure of Internal Storage Structures

## Learning Objectives

After completing this lesson, you will be able to:

- Distinguish the **storage model**, **domain model**, **read model**, and **integration contract**; avoid treating internal column names or document structures as public APIs.
- Determine **which consumers need which data, for what purpose, at what permission level, and with what freshness** before creating endpoints, events, or shared tables.
- Design **DTOs/API responses**, **integration events**, and **read projections** with clear fields, types, units, semantics, identifiers, and access controls.
- Use **field allowlists, explicit mappings, object-level authorization checks**, and public IDs to prevent data leaks and internal-key coupling.
- Publish changes via a **transactional outbox** and distinguish it from opening tables, sharing databases, or forwarding raw CDC rows to consumers.
- Build schema evolution plans with **backward compatibility, versioning, contract tests, observability, reconciliation, and deprecation**.
- Compare how boundaries are maintained when data lives in a relational database, document database, graph database, or analytical system.

This lesson belongs to the **Boundaries and Integration** chapter of **DATABASE_DATA_MODELING**. When turning business requirements into data models, we need entities, relationships, constraints, keys, indexes, and physical schemas; however, when exposing data to APIs or external services, **the internal model must not become a permanent promise to every consumer**. The goal is to let internal structures evolve while preserving external business contracts and access controls.

## 1. Scenario: An Order Table Used Directly as an API

A sales application has internal tables:

~~~~text
orders_internal
  order_pk                 -- BIGINT, database surrogate key
  tenant_id                -- business/tenant scope
  public_order_id          -- UUID for customers and external systems
  customer_pk              -- internal key of customer profile
  workflow_state           -- granular internal processing state
  total_amount             -- locked amount on the order
  currency
  confirmed_at
  risk_score               -- anti-fraud score
  agent_note               -- staff note
  row_version
  updated_at

order_lines_internal
  order_pk, line_no
  product_pk               -- internal FK
  product_name_at_order    -- locked name snapshot
  quantity
  unit_price_at_order      -- locked price snapshot

payment_attempts
  payment_attempt_pk
  provider_reference
  internal_error_detail
  ...
~~~~

A developer writes a simple endpoint:

~~~~text
GET /orders/901
    -> SELECT * FROM orders_internal WHERE order_pk = 901
    -> serialize the entire database row to JSON
~~~~

This looks fast to build, yet creates multiple problems:

1. **Unnecessary data leakage:** `risk_score`, `agent_note`, and internal keys appear in the response.
2. **Storage model exposure:** consumers learn `order_pk`, `workflow_state`, SQL column names, and FK relationships.
3. **Refactoring coupling:** renaming columns, splitting tables, or migrating to a document store easily breaks all clients.
4. **Broken authorization boundaries:** knowing `order_pk` does not prove the caller is allowed to read the order; the endpoint must check tenant and owner.
5. **Semantic mismatch:** the price stored on an order line differs from current list price; internal workflow states are not necessarily suitable public states.
6. **Hard versioning:** every database change accidentally becomes an external contract change.

A sound design places an **intentional publishing layer** between the storage engine and data consumers:

~~~~text
            INSIDE ORDER DOMAIN
   +----------------------------------+
   | orders_internal / order_lines    |
   | payment / fulfillment state      |
   | domain rules, transactions       |
   +----------------+-----------------+
                    |
              mapping + policy
                    |
   +----------------+-----------------+
   | Public API DTO                   |
   | Integration events               |
   | Purpose-built read projections   |
   +--------+------------+------------+
            |            |
         Customer     Logistics / Analytics
         API client   (separate contracts)
~~~~

**External callers may depend only on published contracts**, never arbitrarily accessing internal tables, columns, or keys. Maintaining this boundary preserves the storage model's ability to evolve.

## 2. Four Models That Should Not Be Collapsed Into One

| Layer | Answers the Question | Examples | Who May Change It? |
| --- | --- | --- | --- |
| **Storage model** | How are data, keys, and indexes stored? | `orders_internal`, `order_pk`, FK tables | Database-owning team |
| **Domain model** | What are the business invariants and transitions? | Confirm order, cancel order, lock price, refund | Business domain & owning service team |
| **Integration/public contract** | What may consumers see, and with what meaning? | `OrderView`, `OrderShippingStarted` v1 | Contract owner in coordination with consumers |
| **Consumer read model** | What structure does the consumer need for fast queries? | Order list, dashboard, search document | Consumer team or projection team |

You can maintain a **normalized relational table** as the authoritative source, a **DTO** for customers, a minimal **event** for shipping, and a **fact** for reporting. Those structures are not copies "synced to match identically"; each has **distinct semantics, freshness, scope, and ownership**.

### 2.1. Authoritative Source Does Not Mean Exporting the Entire Source

An **authoritative source** establishes the true value of a business fact. It does not mean every field at the source may be published.

For example:

- The Order service is authoritative for **order status** and **confirmed prices**.
- The Customer service is authoritative for **current default address**.
- The Payment service is authoritative for **capture/refund**.
- An **order_detail_view** table may be a read copy; it has no authority to invent a new transaction price.

Even when Order holds a locked shipping address, Analytics does not automatically gain the right to receive the full street address. **Authority to decide a value and authority to share a value are two distinct decisions.**

### 2.2. A Published Contract Is a Product with a Lifecycle

A good contract is treated as a consumer-facing interface:

- Has a **name, version, field descriptions, and examples**.
- Defines **access controls**, tenant scope, and permitted purpose.
- Specifies **schema evolution rules**, error states, missing data, and time/money semantics.
- Defines **SLOs** for availability, latency, and freshness when synchronized.
- Has an **owner**, tests, and change notification workflows.

Adding a JSON serializer alone does not establish any of these guarantees.

## 3. Inventory Consumers Before Deciding What to Publish

The same order has multiple consumers:

| Consumer | Needs to Know | Should Not Receive by Default | Freshness & Authorization |
| --- | --- | --- | --- |
| **Order-owning customer** | Order ID, understandable status, locked price, item lines | Risk score, staff notes, database keys | Read after authentication & ownership check |
| **Customer support app** | Status, permitted handling reasons, required contact details | Full payment logs, unrelated sensitive info | Role- and purpose-based authorization |
| **Shipping service** | Order ID, delivery instructions, recipient & address **scoped to delivery execution** | Cost price, `risk_score`, payment details | Needed at parcel creation time, narrow privileges |
| **Payment service** | Payment intent, authoritative amount and currency, request ID | Logistics notes, full customer directory | Idempotency and clear transaction evidence |
| **Operations dashboard** | Order counts/statuses by bucket, processing latency | Individual customer addresses and phone numbers if unneeded | Can use lagging aggregated data |
| **Analytical warehouse** | Events/facts with defined grain, measures, required dimensions | Raw OLTP table dumps | Lineage, PII/retention policies, and watermarks |

Data publication should be driven by three sets of questions:

1. **Needed to complete which action?** If a field is unused, why include it in the contract?
2. **Does the consumer have valid permission and purpose?** Authenticate callers, enforce object-level rights, and respect sensitive-data policies.
3. **At what point in time does the consumer need the fact?** Current state, past confirmation snapshot, or derived lagging state?

Never build a single **UniversalOrder** containing every field and share it with everyone by "hiding what isn't rendered in the UI". Data returned in a response can still be logged, cached, synced to other apps, or inspected via network tools.

### 3.1. Make Field-Level Decisions, Not Table-Level Decisions

| Internal Field | Public Order API | Logistics Contract | Analytics Contract | Reason |
| --- | --- | --- | --- | --- |
| **public_order_id** | Yes | Yes | Yes, per identity policy | Stable public identifier |
| **order_pk** | No | No | No by default | Internal storage key |
| **customer_pk** | No | No | Controlled pseudonymized ID if needed | Do not leak internal keys |
| **workflow_state** | Mapped to public status | Translated to relevant progress/events | Exported with defined status semantics | Internal states can refactor |
| **total_amount, currency** | Yes, as explicit money | Usually no | Yes when serving valid metrics | Distinguish ordered vs. collected |
| **product_name_at_order** | Yes | May need item name | May need product ID and point-in-time attributes | Snapshot does not sync with current name |
| **risk_score** | No | No | Only with approved, controlled need | Business-sensitive information |
| **agent_note** | No | No | No by default | Free text may hold PII or internal remarks |
| **shipping_address_at_confirmation** | Yes when owner needs to view | Authorized carrier only | No by default | PII and differing purposes |
| **provider_secret / token** | No | No | No | Secrets must never be leaked |

**Allowlist principle:** start with **nothing published**, adding fields only upon justified request and approval. This differs from a blocklist like "serialize all columns except `risk_score`", because newly added sensitive columns leak automatically if someone forgets to update the blocklist.

## 4. Designing Public IDs and Preserving Semantic Stability

### 4.1. Internal Keys and Public Identifiers Have Different Roles

A table may use **order_pk BIGINT** as its primary key for JOINs and indexes, while the API uses **public_order_id UUID** for cross-system exchange.

Benefits:

- Decouples external contracts from internal key types and partitioning strategies.
- Prevents APIs from relying on database sequences or specific FK keys.
- Keeps public IDs stable across database migrations or table rebuilds.
- Reduces scale enumeration from sequential IDs, though **it does not replace security**.

**UUIDs are not an authorization mechanism.** A user who knows or guesses a UUID still has no right to read another customer's order. Read paths must verify **tenant and owner/role** using trusted claims from a verified session or token.

If the system has a human-readable **order_number** that may repeat per tenant/year, explicitly document its uniqueness scope. Never conflate **order_pk**, **public_order_id**, and **order_number** as interchangeable keys.

### 4.2. Public Statuses Are Semantic, Not Database Enum Codes

Internal states might include:

~~~~text
CONFIRMED -> PICKING -> PACKED -> IN_TRANSIT -> DELIVERED
                   -> WAITING_WAREHOUSE_RECHECK
                         -> PICKING
CONFIRMED -> CANCELLED
~~~~

Customers may only need:

~~~~text
CONFIRMED, PROCESSING, SHIPPING, DELIVERED, CANCELLED
~~~~

If the API directly exposes **PICKING**, **PACKED**, and **WAITING_WAREHOUSE_RECHECK**, any workflow change can force clients to update. An **intentional mapping** allows internal steps to change while keeping the public promise intact, provided the meaning holds:

| Internal | Public |
| --- | --- |
| CONFIRMED | CONFIRMED |
| PICKING, PACKED, WAITING_WAREHOUSE_RECHECK | PROCESSING |
| IN_TRANSIT | SHIPPING |
| DELIVERED | DELIVERED |
| CANCELLED | CANCELLED |

Mapping is not arbitrary renaming. States that genuinely differ in cancellation rights, delivery obligations, and wait SLAs must be evaluated in the domain. If a new internal state is added without a defined public mapping, the system should **detect the missing mapping** rather than falling back to returning the raw internal value.

## 5. API Contract: A Small, Unambiguous, Sufficient OrderView

Example endpoint for a logged-in customer:

~~~~text
GET /v1/orders/{publicOrderId}
Authorization: Bearer <access-token>

200 OK          -- Order belongs to caller's scope and caller has read access
404 Not Found   -- Does not exist or policy hides existence
401/403         -- Per authentication, authorization, and anti-leakage policy
~~~~

Illustrative response:

~~~~json
{
  "orderId": "550e8400-e29b-41d4-a716-446655440000",
  "status": "PROCESSING",
  "confirmedAt": "2026-11-22T01:00:00Z",
  "total": {
    "amount": "310000.00",
    "currency": "VND"
  },
  "items": [
    {
      "lineId": "1",
      "productNameAtOrder": "A5 Notebook",
      "quantity": 2,
      "unitPriceAtOrder": {
        "amount": "150000.00",
        "currency": "VND"
      }
    }
  ],
  "delivery": {
    "city": "Ho Chi Minh City",
    "countryCode": "VN"
  }
}
~~~~

This is a **hypothetical contract sample**, not a complete schema covering taxes, payments, or discounts. Orders with two lines or different discount rules will follow the published contract structure accordingly.

Key decisions:

- **orderId** is the public ID, not the database primary key.
- **status** uses a documented set of public values.
- **confirmedAt** is an ISO 8601 timestamp with timezone representing the business milestone; never substitute **updated_at**.
- **amount** is a decimal string avoiding JavaScript JSON number precision issues; precision, scale, and rounding rules must be documented. Integer minor units can be chosen instead if agreed in the contract.
- **items[]** is a snapshot of confirmed order lines. It is historical truth and **does not** sync names/prices with current Catalog changes.
- **delivery.city/countryCode** provides just enough information for this screen. Full street addresses, if needed, should be served on an endpoint/field with appropriate access and retention policies.
- Absent: **risk_score**, **agent_note**, **order_pk**, **customer_pk**, and **provider_secret**.
- **lineId** is a line identifier designed for the API; it does not force clients to understand internal composite keys.

Clarify **which fields are always present**, which may be **null**, and which are **omitted** based on permissions or status. "No delivery info" could mean not yet collected, unauthorized to view, or shipment not created; never overload an empty string for all three meanings.

### 5.1. Do Not Mistake Data Projection for Access Control

A SQL query selecting seven columns instead of the entire table **reduces exposure surface**, yet **is insufficient** for authorization. Permission checks must run **before or alongside** data retrieval using the authenticated identity—never trusting client-supplied `customerId` or `tenantId`.

Specifically:

- Guard against **BOLA/IDOR**: a caller must not read another user's object simply by changing `orderId` in the URL.
- Guard against **mass assignment**: write endpoints must not auto-bind every request field onto internal entities; clients must not set **risk_score**, **row_version**, or sensitive statuses.
- Never assume an API gateway enforces object-level permissions unless an explicit contract guarantees it.
- Design **404/403** behavior carefully to avoid creating existence-oracle leaks, per system policy.

## 6. PostgreSQL Example: Internal Tables vs. Published Queries

Set up an internal schema sufficient for the example:

~~~~sql
CREATE TABLE orders_internal (
    order_pk BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    public_order_id UUID NOT NULL UNIQUE,
    customer_pk BIGINT NOT NULL,
    workflow_state TEXT NOT NULL
        CHECK (workflow_state IN (
            'CONFIRMED', 'PICKING', 'PACKED',
            'WAITING_WAREHOUSE_RECHECK',
            'IN_TRANSIT', 'DELIVERED', 'CANCELLED'
        )),
    total_amount NUMERIC(18, 2) NOT NULL
        CHECK (total_amount >= 0),
    currency CHAR(3) NOT NULL,
    confirmed_at TIMESTAMPTZ NOT NULL,
    delivery_city TEXT,
    delivery_country_code CHAR(2),
    risk_score NUMERIC(5, 4),
    agent_note TEXT,
    row_version BIGINT NOT NULL DEFAULT 1
        CHECK (row_version >= 1),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE order_lines_internal (
    order_pk BIGINT NOT NULL
        REFERENCES orders_internal(order_pk),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_pk BIGINT NOT NULL,
    product_name_at_order TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_at_order NUMERIC(18, 2) NOT NULL
        CHECK (unit_price_at_order >= 0),
    PRIMARY KEY (order_pk, line_no)
);

CREATE INDEX ix_orders_tenant_customer
    ON orders_internal
       (tenant_id, customer_pk, public_order_id);
~~~~

This DDL is **abbreviated for teaching**, omitting full Customer, Payment, Shipment tables, or order-creation deduplication policies. In multi-tenant environments, verify permissions and uniqueness of **public_order_id**, scope of **customer_pk**, and source business constraints.

**Database privileges** must also align: an API-serving role should not freely update sensitive columns. A data access layer can separate projection reads from transactional writes, though **database views/roles** do not replace per-user authorization checks.

### 6.1. Allowlisted Query and Permission Scope

Suppose the application has obtained:

- **$1**: tenant ID from the authenticated session, never directly from untrusted input.
- **$2**: verified customer PK from the principal or authoritative ownership relation.
- **$3**: public order UUID requested by the client.

SQL to fetch the header:

~~~~sql
SELECT
    o.order_pk,        -- used only inside the service to fetch items
    o.public_order_id,
    o.workflow_state,
    o.confirmed_at,
    o.total_amount,
    o.currency,
    o.delivery_city,
    o.delivery_country_code
FROM orders_internal AS o
WHERE o.tenant_id = $1
  AND o.customer_pk = $2
  AND o.public_order_id = $3::UUID;
~~~~

The resulting **order_pk must never enter the API**; it is strictly an internal join key inside the service. If no row returns, the service cannot automatically conclude "no such order exists", as it may simply be outside caller permissions; the response follows the non-disclosure policy.

Fetch lines **after header permissions have been verified**:

~~~~sql
SELECT
    line_no,
    product_name_at_order,
    quantity,
    unit_price_at_order
FROM order_lines_internal
WHERE order_pk = $1
ORDER BY line_no;
~~~~

If the API must return a **consistent snapshot** while orders and items update concurrently, two separate `SELECT` statements under **READ COMMITTED** can observe different versions. You can use a single joined `SELECT` and map to the DTO, or wrap them in a transaction with an appropriate isolation/snapshot level—depending on real write invariants and lifecycles. **Separating DTOs from storage must never become an excuse to neglect consistency.**

### 6.2. Java Mapping with Records and an Explicit Mapper

Java example with types tailored to the published domain:

~~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

record MoneyView(String amount, String currency) {}

record OrderLineView(
    String lineId,
    String productNameAtOrder,
    int quantity,
    MoneyView unitPriceAtOrder
) {}

record DeliveryAreaView(
    String city,
    String countryCode
) {}

record OrderView(
    UUID orderId,
    String status,
    Instant confirmedAt,
    MoneyView total,
    List<OrderLineView> items,
    DeliveryAreaView delivery
) {}

final class OrderPublicMapper {
    private OrderPublicMapper() {}

    static String publicStatus(String internalState) {
        return switch (internalState) {
            case "CONFIRMED" -> "CONFIRMED";
            case "PICKING", "PACKED", "WAITING_WAREHOUSE_RECHECK"
                -> "PROCESSING";
            case "IN_TRANSIT" -> "SHIPPING";
            case "DELIVERED" -> "DELIVERED";
            case "CANCELLED" -> "CANCELLED";
            default -> throw new IllegalArgumentException(
                "Unmapped internal order state"
            );
        };
    }

    static MoneyView money(BigDecimal amount, String currency) {
        return new MoneyView(
            amount.toPlainString(),
            currency.trim()
        );
    }
}
~~~~

This illustrates **core types and mapping**, not a standalone REST controller. The service must construct **OrderView** from authorized records and verified calculations, after which the serializer emits only fields declared on the DTO.

**Never return an ORM entity directly** hoping annotations will hide a few fields. Entities can accidentally trigger lazy-loaded relations, cyclic object graphs, newly added fields, and internal details unreviewed by the API team. An explicit mapper makes storage/contract differences visible in code reviews and tests.

**Never convert `BigDecimal` to `double`** just to simplify money serialization. When the public contract uses decimal strings as shown here, enforce scale/rounding rules and handle missing or invalid internal values cleanly.

### 6.3. Write Requests Also Need Separate Types

Just like responses, state-changing endpoints should never accept a raw **OrderEntity** from clients. A business command only needs the fields permitted to change by policy:

~~~~json
{
  "reasonCode": "CUSTOMER_REQUEST",
  "idempotencyKey": "cancel-req-991"
}
~~~~

The **Order ID** usually sits in the URL path; the target state and transition rules are decided by the server. Clients must never send **tenant_id**, **risk_score**, **total_amount**, or **workflow_state = DELIVERED** hoping the server "only persists valid fields". Enforce validation and authorization right at the command boundary.

## 7. Choosing Event Contracts: Share Business Events, Not Whole Tables

Logistics needs to know when an order begins shipping; Analytics needs facts to measure confirmation-to-delivery lead time; the Customer App needs display status. A common mistake is publishing an event containing an entire **orders_internal** row:

~~~~json
{
  "eventType": "OrderUpdated",
  "table": "orders_internal",
  "row": {
    "order_pk": 901,
    "tenant_id": 17,
    "workflow_state": "IN_TRANSIT",
    "risk_score": "0.4200",
    "agent_note": "Call customer after review",
    "updated_at": "2026-11-22T03:00:00Z"
  }
}
~~~~

This style couples consumers to database columns, risks leaking internal data, and hides what **actually happened in business terms**: was the order just created, moved to shipping, or was only a staff note edited?

A more intentional event contract:

~~~~json
{
  "eventId": "d6cf7c19-19a1-4fbc-a88b-67e6300a9b11",
  "eventType": "OrderShippingStarted",
  "schemaVersion": 1,
  "orderId": "550e8400-e29b-41d4-a716-446655440000",
  "orderVersion": 8,
  "occurredAt": "2026-11-22T03:00:00Z"
}
~~~~

Characteristics:

- **OrderShippingStarted** clearly names the domain event, not a table UPDATE operation.
- **eventId** lets consumers recognize redeliveries of the same message.
- **schemaVersion** versions the **contract structure**; distinct from **orderVersion**, which tracks **business state version**.
- **orderId** is the stable public ID; never publish internal FKs.
- **occurredAt** is the authoritative transition time, never equated with broker receipt time.
- The event **omits shipping address** when subscribers only need order ID and status. Authorized Logistics can receive a **dedicated secure detail contract** when actually executing delivery.

**Events do not have to be complete snapshots.** A state-transition event carries its own semantics; if consumers must build full projections, event design or snapshot APIs must explicitly define how to obtain consistent state and aligned versions.

### 7.1. CDC and Integration Events Solve Different Needs

**Change Data Capture (CDC)** captures changes at the database log/row/column level. It is great for technical replication, projection building, or warehouse ingestion, yet shipping raw CDC payloads directly to every consumer effectively turns table names, column names, and storage structures into public contracts.

An **integration event** is a **business/observational contract** published by the domain owner. It requires mapping internal changes to external semantics, curated fields, and policy. You can **use CDC as the transport mechanism** reading an outbox or feeding a mapping layer, while **never equating raw CDC records with public events**.

| Aspect | Technical CDC | Intentional Integration Event |
| --- | --- | --- |
| Unit of change | Storage row/document/operation | Named business occurrence |
| Names and fields | Usually mirrors storage schema | Follows consumer contract |
| Database refactoring | Can alter payloads | Shielded by mapper when meaning stays constant |
| Access control | Must restrict raw data and transport channels | Audience-specific field allowlist |
| Projection suitability | Useful with snapshots/checkpoints | Depends on event completeness and semantics |
| Trade-off | Exposes schema; hard to infer business intent across multi-row writes | Must maintain mappings, versions, tests, and delivery |

Regardless of mechanism, **consumers do not automatically gain rights to read all data simply by sharing an internal network**.

## 8. Transactional Outbox: Preserving Atomicity Without Exposing Schema

An Order state change must emit its corresponding event. If the application:

1. COMMITs **workflow_state = IN_TRANSIT**;
2. Then sends a message to the broker;

a crash after step 1 means the event **is never sent**. Conversely, sending before commit can deliver an event for a rolled-back transaction.

A **transactional outbox** persists the intended event in the same transaction as the source mutation.

### 8.1. Illustrative Outbox Table

~~~~sql
CREATE TABLE integration_outbox (
    event_id UUID PRIMARY KEY,
    aggregate_id UUID NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    schema_version INTEGER NOT NULL
        CHECK (schema_version >= 1),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ,
    CONSTRAINT uq_outbox_order_version
        UNIQUE (aggregate_id, aggregate_version)
);
~~~~

This example assumes **each order version transition emits at most one integration event**. If a single version transition can emit multiple independent events, the unique constraint and sequencing must adapt; never apply a constraint that silently drops events.

The outbox table is an **internal publishing structure**, not a table external parties may query directly. The publisher is responsible for dispatching unpublished messages, retrying, and updating publication state.

### 8.2. State Change and Event Write in One SQL Statement

The application transitions status from **PACKED** to **IN_TRANSIT**, supplies an event UUID, and verifies exactly one row changed:

~~~~sql
BEGIN;

WITH changed AS (
    UPDATE orders_internal
    SET workflow_state = 'IN_TRANSIT',
        row_version = row_version + 1,
        updated_at = CURRENT_TIMESTAMP
    WHERE order_pk = $1
      AND workflow_state = 'PACKED'
    RETURNING public_order_id, row_version, updated_at
)
INSERT INTO integration_outbox (
    event_id,
    aggregate_id,
    aggregate_version,
    event_type,
    schema_version,
    payload
)
SELECT
    $2::UUID,
    public_order_id,
    row_version,
    'OrderShippingStarted',
    1,
    jsonb_build_object(
        'eventId', $2::UUID,
        'eventType', 'OrderShippingStarted',
        'schemaVersion', 1,
        'orderId', public_order_id,
        'orderVersion', row_version,
        'occurredAt', to_char(
            updated_at AT TIME ZONE 'UTC',
            'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'
        )
    )
FROM changed;

-- COMMIT only when INSERT returns exactly one row.
-- Otherwise: ROLLBACK, return a valid state-transition/conflict error.
COMMIT;
~~~~

This is an **application protocol example**, not a SQL script that decides on its own to COMMIT when **INSERT** returns 0 rows. The service must inspect row counts, enforce transition rules, and choose COMMIT vs. ROLLBACK. Other business details such as shipment IDs may belong to the Logistics service and its own events—never fabricate them just to fill a payload.

Core property: the **source UPDATE and outbox INSERT** commit or roll back together. After commit, the publisher relays the event through the broker.

**An outbox alone does not guarantee end-to-end exactly-once processing.** The publisher may send successfully and crash before setting **published_at**, causing redelivery. Consumers need idempotency on **eventId** and/or version, plus rules for out-of-order messages. Command transitions at the source also need idempotency if retrying the same request could trigger duplicate business effects.

### 8.3. Fast Read Copies Still Require Contracts

A consumer building **order_cards** might store:

~~~~text
order_cards (projection)
  public_order_id
  customer_public_id
  public_status
  confirmed_at
  total_amount
  currency
  source_order_version
  projected_at
~~~~

This is an access-pattern-optimized read model, **not** an authority that decides order status. If it receives v8 followed by v7, it must not overwrite v8 with v7. For state-only events, ensure consumers have enough fields/versions for safe partial updates; for creation events, you may need snapshots or an authoritative API.

Never use an eventually consistent projection to approve payments, issue refunds, or make sales decisions when business rules demand verified source state.

## 9. Contracts Must Not Accidentally Depend on Physical Storage

Designs that commonly leak storage:

- APIs exposing **order_pk BIGINT** which every consumer saves as an FK.
- DTOs named **order_row**, **deleted_flag**, or **join_table_ids** mirroring internal SQL tables.
- GraphQL schemas auto-generated over all ORM entities, allowing unrestricted traversal without authorization.
- Search APIs returning raw **MongoDB documents** including **_id**, technical metadata, and unreviewed fields.
- Event brokers publishing every table **UPDATE** with full before/after rows.
- Consumers querying the Order database directly via `SELECT` on internal tables instead of versioned contracts.
- Dashboards reading raw **workflow_state** columns and duplicating public status mappings per team.

You can use a storage model to **implement** a contract, but never treat it as the contract itself.

### 9.1. Anti-Corruption Layers and Domain Mapping

When a service participates in a multi-domain architecture, an **anti-corruption layer (ACL)** translates external concepts into local domain concepts rather than importing external names, statuses, and invariants verbatim.

For example, Order calling Payment:

~~~~text
Payment response: capture_status = "SETTLED"
             |
             v
Verified adapter: funds captured successfully
             |
             v
Order business state: paymentRequirementSatisfied = true
~~~~

Never write `orders_internal.workflow_state = payment.capture_status` directly, because those statuses belong to different domains with different lifecycles. If Payment adds **PARTIALLY_SETTLED**, the adapter must handle it per Order business rules instead of silently passing through a new enum value.

Likewise, contracts published by Order to Logistics must respect shipping vocabulary and receiver permissions rather than forcing Logistics to know the table name **order_lines_internal**.

### 9.2. Database Views Can Help, but Are Not a Complete Publishing Layer

An allowlisted **SQL VIEW** can be convenient for internal jobs or read-only integrations within a trusted boundary:

~~~~sql
CREATE VIEW order_public_projection AS
SELECT
    public_order_id,
    confirmed_at,
    total_amount,
    currency,
    CASE
        WHEN workflow_state = 'CONFIRMED' THEN 'CONFIRMED'
        WHEN workflow_state IN (
            'PICKING', 'PACKED', 'WAITING_WAREHOUSE_RECHECK'
        ) THEN 'PROCESSING'
        WHEN workflow_state = 'IN_TRANSIT' THEN 'SHIPPING'
        WHEN workflow_state = 'DELIVERED' THEN 'DELIVERED'
        WHEN workflow_state = 'CANCELLED' THEN 'CANCELLED'
    END AS public_status
FROM orders_internal;
~~~~

**Warning:** this view **contains no user/tenant filter** and **must not be granted public SELECT to arbitrary clients**. Safe usage requires permissions/RLS or an object-authorized service layer. Views reduce coupling to internal column names, yet when **consumers run arbitrary queries against a shared database**, coupling around query load, data freshness, and operational permissions persists.

You can use views for internal transformations within one team, paired with an **API/service boundary** to enforce per-caller authorization and publish contracts. Never treat views as a universal substitute for APIs.

## 10. Versioning: Change Storage Without Forcing Simultaneous Consumer Changes

Suppose v1 of an API returns:

~~~~json
{
  "orderId": "550e8400-e29b-41d4-a716-446655440000",
  "status": "PROCESSING",
  "total": {
    "amount": "310000.00",
    "currency": "VND"
  }
}
~~~~

The Order team wants to migrate its internal database from multiple relational tables to a document store. As long as **orderId, status, and total** retain identical semantics, clients **need not know** about the migration.

Conversely, renaming **status** to **workflowState**, changing **amount** from a decimal string to a **float**, or replacing **PROCESSING** with **PICKING** is a contract change that breaks consumers even if the database never changed.

### 10.1. Distinguish Compatible vs. Breaking Contract Changes

| Change | Typical Impact | Required Action |
| --- | --- | --- |
| Rename internal table, index, or partition | Should not affect API | Maintain mappers and contract tests |
| Add an optional field with clear semantics | Compatible with clients ignoring unknown fields | Test real consumers, document clearly |
| Add a new public enum value | Can break clients using exhaustive enums | Design unknown/fallback handling or version & announce |
| Remove/rename a required field | Usually breaking | New contract version, transition window |
| Change decimal string to JSON number | Breaking and loses precision | New contract, test large amounts and rounding |
| Change **total** meaning from order value to collected cash | Semantically breaking even with identical type | Introduce a newly named field/metric, migrate |
| Switch UTC timestamps to offset-less local time | Breaking / ambiguous | Preserve timezone and standardize |
| Split one large event into multiple events | Affects ordering, dedup, and workflows | Versioning, replay/compatibility, consumer contracts |
| Add a sensitive column to the database | **Must never** auto-appear in APIs | Allowlist mapping and leakage tests |

Never equate **adding a field** with guaranteed safety: strict schema validators, deserializers rejecting unknown properties, or canonical/signed event payloads can still fail. Contracts must declare compatibility direction and consumer flexibility expectations.

### 10.2. Expand–Migrate–Contract Strategy

For example, migrating a public contract from legacy **grandTotal** to **total(amount,currency)**:

1. **Expand:** add the new contract or v2 version in parallel without removing v1.
2. **Migrate:** transition consumers and tests; monitor who still calls v1.
3. **Contract:** retire v1 after deprecation notice, deadline, and real-usage criteria are met.
4. **Cleanup:** remove v1 mappers/fields/supporting storage only after zero active consumers remain.

If two versions must coexist long-term, mappings and tests must verify that **the exact same business truth** is projected accurately in both formats. Avoid maintaining two independent write paths that create dual sources of truth.

### 10.3. Event Version Differs from Aggregate Version

- **schemaVersion = 1**: consumer parses the payload using contract structure v1.
- **orderVersion = 8**: the 8th state mutation of the Order per source rules.
- **sourceCheckpoint/watermark**: how far a stream/projection has processed.
- **effectiveAt**: when a state takes business effect, if different from emission time.

Never implicitly substitute a table's **updated_at** for these milestones. A message may be redelivered, arrive late, or be reconstructed during a migration.

## 11. Safe Patterns for Sharing Data Across Boundaries

### 11.1. API Request/Response

Best when consumers query **on demand** and the owner can enforce authorization at call time.

Define endpoints, rate limits, pagination, error shapes, fields, and policies. For order lists, support **keyset/cursor pagination by public key and stable sort order**, rather than arbitrary `SELECT` over internal columns.

### 11.2. Integration Events

Best when consumers react to **facts that occurred**, maintain projections, or trigger workflows. Events require explicit semantics, IDs, versions, retries, and retention; consumers must tolerate at-least-once delivery when that is the underlying transport guarantee.

**Events do not grant consumers unlimited rights to store data forever.** PII fields, deletion policies, and retention limits apply equally to brokers, dead-letter queues, and read models.

### 11.3. Shared Database / SQL Views

Can serve as a transitional pattern in small systems, batch jobs, or within one governance domain. However, consumers running `SELECT` on source tables may:

- Depend on internal column names and join layouts.
- Read intermediate states lacking complete business semantics.
- Put direct query load onto OLTP storage.
- Struggle with field- and object-level access control.
- Block schema changes or database migrations.

If SQL sharing is necessary, prefer **dedicated published schemas/views, minimal read-only privileges, versioning, and ownership**, paired with a sunset plan before major refactors. Do not assume shared databases are universally forbidden, but explicitly account for coupling cost and access control.

### 11.4. Analytics Exports

Suited to long-term reporting and analysis by product, date, and channel. Declare **fact grain**, measure definitions, recognition timestamps, and classification dimensions.

For example, a **fact_order_line_confirmed** table exported to the warehouse at grain **one confirmed order line**, holding quantity, allocated net amount, currency, `confirmedAt`, and product ID. This is **not** a raw dump of `Orders + Payments + Shipments`: joining multiple 1:N relationships multiplies rows and corrupts revenue.

If consumers only need daily revenue totals, consider **aggregated tables by date × currency** instead of exporting every customer's identity and address.

## 12. Comparing Relational, Document, Graph, and Analytical Sources

| Source Model | What Easily Leaks if Published Directly | What the Contract Should Expose |
| --- | --- | --- |
| **Relational** | PK/FKs, join tables, workflow flags, normalized internals | Business-meaningful DTOs, resources, or events |
| **Document** | `_id`, internal arrays, technical metadata, shifting nested shapes | Use-case schemas, allowlisted projections, public IDs |
| **Graph** | Physical node/edge IDs, internal edge labels, unbounded traversals | Authorized queries answering business questions, never the full graph |
| **Time-series** | Sensitive device IDs, raw samples, internal tags, retention internals | Approved series with clear buckets, units, and freshness |
| **Dimensional/analytical** | Dimension surrogate keys, granular customer data, ETL state | Facts/aggregates with explicit grain, metrics, governance, watermarks |

**Document model:** if an `Order` document embeds payments, shipping logs, and addresses, an API must not return the raw document merely because it sits in one aggregate. **Co-located storage does not imply shared read authorization.**

**Graph model:** a "fetch all neighbors" API can leak personal or internal relationships. Every edge, node, and traversal path needs authorization and purpose limits. Never expose internal graph IDs as long-lived contract identifiers.

**Analytical systems:** publishing aggregates reduces exposure when sufficient, yet **aggregation alone does not guarantee anonymity**; small groups, overlapping filters, or external linkage can still re-identify individuals. Control dimensions, cardinality, query policies, and authorized users.

## 13. Security and Privacy: More Than Filtering a Few Columns

### 13.1. Data Classification and Data Minimization

Before publishing, classify at least:

- **Business-public data:** order status shown to the order owner, public product titles.
- **Identifying/personal data (PII):** addresses, phone numbers, emails, customer IDs, and linkable metadata.
- **Internal sensitive data:** fraud scores, support notes, pricing rules, operational metrics.
- **Secrets/credentials:** payment tokens, API keys, password hashes, secrets, and access tokens.
- **Analytical data:** defined metrics, potentially requiring aggregation or pseudonymization.

Do not inspect field names in isolation. **Data that looks harmless alone can become sensitive when joined with other datasets.** Publishing policies must cover purpose, recipients, retention periods, onward sharing, and deletion.

### 13.2. When Full Addresses Are Required

If a customer must view the address chosen at confirmation, the API can expose **shippingAddressAtConfirmation** strictly to the authorized order owner. However, a broadcast **OrderShippingStarted** event sent to many consumers should not carry the street address when most subscribers only need the order ID and status.

An authorized Logistics service can use a **dedicated channel/contract** to retrieve exact recipient details with service authentication, purpose checks, audit logging, and retention controls. **A multi-subscriber broadcast event is the wrong place to put PII just because one consumer needs it.**

### 13.3. Outputs, Logs, Caches, and Errors Can All Leak Data

Verify:

- **API responses and error bodies:** never expose SQL queries, table names, stack traces, tokens, or internal states.
- **Access logs / APM / tracing:** avoid dumping request/response bodies containing addresses, sensitive prices, or auth headers.
- **Caches and CDNs:** include tenant/user in cache keys, honor privacy rules, TTLs, and invalidation.
- **Dead-letter queues / brokers:** govern payloads, retention, access permissions, replay, and purging.
- **CSV exports / reports:** filter columns/objects, control downloads, add watermarks, and audit access.
- **Backups:** enforce retention periods and policy-compliant data management.
- **Test environments:** avoid copying production data into lower-privilege environments without sanitization/protection.

Trimming DTO fields is essential, yet it is only part of security design. **Authorization, auditing, data partitioning, and operational controls** remain mandatory per risk profile.

## 14. Contract Tests and Reconciliation: Preventing Schema Leaks in Future Refactors

An API can accidentally expose new fields when a developer swaps serializers or adds columns to an entity. Test at the **boundary**, not only at the repository layer.

### 14.1. API Test Categories

| Category | Required Cases |
| --- | --- |
| **Schema allowlist** | JSON contains only contracted fields; no `order_pk`, `customer_pk`, `risk_score`, `agent_note` |
| **Authorization** | Different tenants/users cannot view; invalid tokens denied |
| **Output mapping** | Internal `PICKING`/`PACKED` both map cleanly to `PROCESSING` |
| **Unknown internal state** | Unmapped states fail loudly instead of leaking raw internal values |
| **Money/time** | Decimal strings preserve precision; timestamps include timezone; locked prices ignore Catalog changes |
| **Null/optional** | Missing or restricted delivery info handled per contract |
| **Pagination** | Stable ordering, tenant-scoped, no duplicates or skipped rows |
| **Error shape** | No SQL, stack traces, or sensitive details |
| **Version compatibility** | v1 keeps working across storage refactors; v2 honors documented semantics |

You can assert **exact JSON key sets** against the version's allowlist, verifying sensitive fields stay absent even when populated in the underlying entity. Tests should deliberately populate **agent_note** and **risk_score** to prove mappers never leak them.

### 14.2. Event and Consumer Testing

- **Schema:** valid `eventType`, `schemaVersion`, public IDs, timestamps, and zero non-allowlisted DB fields.
- **Semantics:** events emit only when genuine business transitions occur.
- **Delivery:** duplicate `eventId`s do not repeat side effects; consumers ignore older versions/sequences.
- **Recovery:** a publisher crashing post-commit still dispatches from the outbox; restarts support replay.
- **Backfill:** rebuilding projections from verified sources neither regresses state nor exposes uncontracted fields.
- **Privacy:** projections, logs, and topics have concrete plans when access must be revoked or data erased.

**Passing schema validation does not mean business data is correct.** For instance, an event with a valid decimal string in `amount` containing **today's list price** instead of **the locked order price** is still a severe bug. Test **semantics and authoritative provenance**.

### 14.3. Data Lineage and Operational Metrics

Every contract should be traceable:

~~~~text
Public OrderView.status
  <- mapPublicStatus(orders_internal.workflow_state)
  <- Domain Order state transition

OrderShippingStarted.orderVersion
  <- orders_internal.row_version
  <- UPDATE + transactional outbox (same commit)

Analytics fact_order_line.net_amount
  <- order_lines_internal (locked snapshot)
  <- line-level discount allocation rules
~~~~

For async APIs/events/projections, monitor:

- **End-to-end latency**, not just consumer message processing time.
- **Schema mapping error rates** and unmapped enum states.
- **Outbox oldest pending age**, backlog, retries, and dead-letter counts.
- **Mismatches** between source and projection at matching versions/watermarks.
- **Consumer usage** per contract/version to plan v1 retirement safely.
- **Denied access attempts**, leakage caught by tests/audits, and permission revocation lag.

An event can be delivered cleanly while a consumer relies on an unsupported contract version. **Contract owners** and **consumers** must coordinate releases proactively, not only during incidents.

## 15. Migrating Away from DB-Exposing APIs: Incremental, Reversible Steps

Suppose a legacy API returns nearly raw SQL rows and clients already depend on **order_pk** and **workflow_state**. Do not delete those two fields overnight in a breaking release that takes down clients.

Reference workflow:

1. **Inventory real consumers** using docs, code, controlled access logs, and team outreach. Identify clients still relying on internal IDs/fields.
2. **Classify risk:** prioritize sensitive fields immediately; non-sensitive coupling fields get a deprecation roadmap.
3. **Define the new v2 contract:** public IDs, business statuses, money/time, permissions, errors, pagination, and freshness.
4. **Build dedicated mappers/projections** without changing the authoritative source prematurely.
5. **Run contract tests on both v1 and v2**, covering permissions, historical data, and rare states.
6. **Publish v2** and migrate clients in waves; maintain a server-side legacy ID → public ID mapping during transition if needed.
7. **Observe v1 usage** and discrepancies; coordinate with remaining consumers before setting a hard cutoff.
8. **Sunset v1 per deprecation policy**, revoke access to internal structures, and drop unneeded mappings.
9. **Refactor storage once boundaries stabilize** or run controlled parallel reads; use shadow reads/reconciliation to protect contract promises.

If the legacy API **leaks secrets or unauthorized PII**, security remediation may need to move faster than standard deprecation timelines: block access, revoke tokens, trim data scope, and follow incident response procedures. "Preserving compatibility" never justifies continuing unauthorized data exposure.

### 15.1. Do Not Use Dual-Write to Create Dual Sources of Truth

When migrating from PostgreSQL to a document store, you can maintain a **read projection** in the document store fed by outbox/CDC. **PostgreSQL remains the authoritative source** during the defined phase; the read model never decides prices or statuses.

If both stores accept independent writes and sync mutually without conflict-resolution rules, diverging prices or statuses become irreconcilable. Decide **which system owns write commands and which is a projection**, with explicit cutover and rollback plans.

## 16. Choose Contract Scope with Evidence, Not `SELECT *` Convenience

Suppose there are three ways to serve an order detail page (**purely illustrative numbers**):

| Design | API p95 | Published Data | Risks / Costs |
| --- | ---: | --- | --- |
| Return internal row/entity directly | 68 ms | Unneeded columns, including `risk_score` and `agent_note` | Data leakage, schema coupling, hard to refactor |
| DTO mapper from indexed query | 75 ms | API-approved fields only | Added mapping/test cost; protects boundaries |
| Dedicated read projection for `OrderView` | 48 ms | Approved fields with source version | Faster, yet adds pipeline, lag, reconciliation, rebuilds |

**You cannot pick the first option just because p95 = 68 ms.** It violates boundary and security requirements; baseline safety criteria must be satisfied before optimizing latency.

A projection makes sense if the API genuinely hits a bottleneck or data spans separate stores; however, if a mapped DTO query already meets SLOs under moderate workload, **do not add another replica** just to shave a few milliseconds.

Measurements to track include **read p95/p99, queries per request, write latency, mapping error rate, projection freshness, source load, update fan-out, recoverability, and contract churn**. Good design optimizes the whole system, not a single `SELECT`.

## 17. Pre-Publish Review Checklist for New Fields or Events

| Question | Required Evidence |
| --- | --- |
| Who is the consumer and what is the action? | Use case, owner, intended purpose |
| What is the authoritative source of each field? | Field-level authority and point-in-time semantics |
| Is this field truly necessary? | Consumer-specific allowlist; avoid full entities |
| Is the data sensitive? | Classification, authorization, retention, sharing scope |
| What is the public ID? | Stable identifier independent of physical PK |
| Are object-level permissions enforced? | Tenant, principal, role, BOLA/IDOR test cases |
| What does the field mean? | Status, money, currency, timezone, snapshot vs. current |
| Can values be missing or NULL? | Required/optional rules, absent-data semantics |
| How does the contract evolve? | Schema version, compatibility, consumer tests |
| How is data emitted? | API, outbox/event, CDC, view, export |
| What if events duplicate or reorder? | Event ID, aggregate version, idempotency |
| What if source and copy diverge? | Freshness SLO, watermarks, reconciliation |
| What happens during internal refactors? | Mappers and tests shielding the public contract |
| Can data be purged or revoked? | API/cache/broker/DLQ/warehouse/logs/backups |
| What when no consumers remain? | Deprecation, usage metrics, cleanup of permissions/aux storage |

## 18. Case Study Exercises

### Exercise 1 — Raw Internal Entity JSON

An endpoint uses an ORM library to return the entire `OrderEntity`. Next day the Fraud team adds `riskScore` to the entity; that field immediately appears in the endpoint's JSON even though nobody touched the controller.

**Question:** Which boundary is missing? Propose an immediate fix and a measure to prevent recurrence.

### Exercise 2 — Does a UUID Replace Access Control?

An API replaces sequential numeric IDs with **UUIDs**. One customer copies another customer's order UUID and the `GET` endpoint still returns the order because the service queries solely by UUID.

**Question:** What did the system improve, and what protection is missing? Write the required business query condition.

### Exercise 3 — Shipping Only Needs to Know Ready-to-Ship

Logistics receives the entire `orders_internal` row, including prices, risk score, notes, and customer ID. In reality it only needs order ID, handoff timestamp, and parcel ID; addresses are fetched via a dedicated delivery service when needed.

**Question:** Which event fields should be chosen? Should addresses be broadcast in a shared event to all subscribers?

### Exercise 4 — Changing the Storage Model

The Order team migrates from PostgreSQL (`orders + order_lines`) to a MongoDB document with an `items` array. Existing clients consume a DTO containing only `orderId, status, total, items` with stable semantics.

**Question:** Must the API version change? Which tests should run before switching reads?

### Exercise 5 — Adding a New Workflow State

Internally there are `PICKING` and `PACKED`, both mapped to `PROCESSING`. The warehouse team adds `WAITING_WAREHOUSE_RECHECK`. A public client does not support new enum values.

**Question:** How should this be handled without leaking internal states while preserving business accuracy?

### Exercise 6 — Raw CDC Rows Pushed Straight to a Broker

An analytics consumer subscribes to CDC on `orders_internal` and treats `order_pk`, `workflow_state`, and `updated_at` as its contract. The Order team changes keys, splits statuses, and partitions the table.

**Question:** Why did the consumer break from "just a DB refactor"? What contract or mapping layer should replace it?

### Exercise 7 — Event Redelivered After Crash

A transaction sets an order to `IN_TRANSIT` and commits an outbox row. The publisher sends the message successfully, crashes before updating `published_at`, and re-emits the same event after restarting.

**Question:** Is this a bug proving the outbox useless? What property must the consumer have?

### Exercise 8 — Order Value or Collected Cash?

An API exposes `total` as the **order value at confirmation**. Analytics treats `total` as actual cash collected, even though some orders are paid in installments or refunded.

**Question:** Is the error in data type or semantics? What clearer data contract design is needed?

### Exercise 9 — Fixing a Legacy API That Cannot Be Cut Immediately

API v1 exposes `order_pk`, and several external partners rely on it. The team wants to drop the field tomorrow. No logs currently track client versions.

**Question:** Propose safe steps to eliminate schema leakage while managing the transition.

### Suggested Solutions

1. Missing an **API DTO and allowlist mapping** independent of the ORM entity. Stop serializing the entity directly, publish a response with approved fields only, add contract tests asserting sensitive fields stay absent, and audit endpoint permissions and logs.
2. UUIDs decouple public identifiers from database keys and are harder to guess than sequential IDs, yet **are not authorization**. Queries must restrict by **tenant and owner/authorization relation** from the verified principal, e.g., `WHERE public_order_id = ? AND tenant_id = ? AND customer_pk = ?`.
3. Minimal event fields: `eventId, eventType, schemaVersion, orderId, orderVersion, occurredAt, shipmentId` (if the source holds the valid ID). Full street addresses should flow only over a dedicated contract/channel for authorized carriers; never broadcast unnecessary PII.
4. **Not necessarily**, if the public contract preserves fields and semantics. Test schema/serialization, money/timestamps, permissions, statuses, item/snapshot accuracy, line ordering, p95 latency, error handling, and shadow-read comparisons.
5. Add a boundary mapping to `PROCESSING` if semantically accurate; test business rules and unknown states. Clients still see only committed public statuses. If the new state requires customer-visible action changes, design a properly versioned/compatible public contract.
6. The consumer depended on the **physical schema**, not a business contract. Introduce an adapter transforming CDC into stable published events/entities with public IDs and business-meaningful transitions, or use source-maintained domain APIs/events.
7. **No.** Outbox guarantees publishing intent commits atomically with state, typically yielding **at-least-once** delivery. Consumers must be **idempotent** by event ID, handle versioning/ordering and retries, and never execute side effects twice upon redelivery.
8. The flaw is in **source semantics and metric definition**. `OrderConfirmedAmount` differs from `PaymentCapturedAmount` and `RefundAmount`. Emit capture/refund facts/events from Payment with explicit grain, currency, business timestamps, and net revenue formulas.
9. Inventory consumers, add per-version telemetry, launch v2 with public IDs, build a transitional legacy-ID adapter if needed, run contract tests, issue deprecation notices, migrate partners incrementally, monitor usage, and retire v1. If sensitive data is leaking, remediate security immediately rather than waiting on compatibility timelines.

## 19. Takeaways

**Where data is stored and who is permitted to see it are two separate decisions.** Tables, documents, graph nodes, or warehouse facts are optimized for storage and processing; APIs and integration events must be optimized for **business semantics, access control, and contract stability**.

**Publish minimal yet sufficient data:** select fields by use case and audience, separate public IDs from physical keys, map statuses/money/time unambiguously, and never broadcast raw entities or CDC rows as contracts. When sensitive data must cross boundaries, scope it tightly and enforce access controls rather than sharing by default.

Before exposing any new field across a boundary, answer: **"What does the consumer need to know to do what job, at what point in time is the data valid, who is authorized to read it, and if we change our tables or database, will this promise still hold?"** A verifiable contract lets your data model evolve without dragging every integrated system along with it.
