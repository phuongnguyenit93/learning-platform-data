# API and Event Contracts as Purposeful Projections

## Learning Objectives

In the **DATABASE_DATA_MODELING** module, we practice turning business requirements into clear data models—from entities, relationships, and constraints to physical schemas. However, when data crosses **the boundary of a system or business domain**, the critical question is no longer "how many columns can we export?" but rather: **what does the consumer actually need to know, to do what work, and under what semantic and timing guarantees?**

An **API contract** or **event contract** can be viewed as a **purposeful projection** of business truth. It selects only the required information, may rename, standardize types, aggregate, hide fields, fix timestamps, and constrain evolution. It is **not an unconditional copy of an internal entity, table, or document**.

After completing this lesson, you will be able to:

1. Distinguish **internal models**, **API queries**, **integration events**, and **read models**.
2. Design projections around **purpose, consumer, owner, grain, timing, and access rights**.
3. Publish identifiers, statuses, timestamps, and monetary amounts with semantics clear enough to verify.
4. Explain why APIs return **current state**, while events typically announce **facts that have occurred**.
5. Choose how to manage compatibility, versioning, idempotency, ordering, outbox, and replay.
6. Write OpenAPI/JSON Schemas, mapping SQL, and contract/security tests.
7. Reduce cross-team coupling when evolving relational, document, graph, and analytical schemas.

## 1. What Does "Purposeful Projection" Mean?

In relational algebra, the projection \(\pi_A(R)\) selects attributes \(A\) of relation \(R\). Projection at an **integration boundary** goes further: it can **JOIN, compute, filter by permissions, transform names and types, map statuses, and select historical versions**.

~~~~text
Internal model (source of truth)
   ├── Tables/documents, keys, dependencies, and constraints
   ├── Status history, technical metadata
   └── Sensitive or internal-only fields
                  |
                  | Filter by purpose and permissions
                  | Select, transform, aggregate, name
                  | Define grain, semantics, time, version
                  v
          API / Integration event
                  |
                  v
         Consumer with a stable contract
~~~~

You can picture it as:

\[
C=\operatorname{Project}_{P,V,S}(M),
\]

where \(M\) is the source model, \(P\) is the **purpose**, \(V\) is the **version and temporal semantics**, \(S\) is the **sharing/authorization scope**, and \(C\) is the published contract. This is a **mental model**, not a formal new operator in relational algebra.

### Why Not Publish the Raw Entity?

Suppose the Orders system has:

~~~~text
orders(
    id, tenant_id, public_order_number, customer_id,
    status_code, confirmed_at, currency_code,
    version, internal_risk_score, payment_token_ref,
    created_by_service, deleted_at
)
~~~~

If an API serializes this entire row:

- Consumers become coupled to `status_code`, `version`, and technical fields that may change during refactoring.
- Data like `internal_risk_score` or payment references may leak beyond approved purposes.
- Every table/ORM change can force mass consumer updates.
- Consumers infer statuses, money, and timestamps on their own without a business contract.

Instead, a projection might return only **order ID, display status, confirmation date, order lines, and booked goods value**. Internal table changes do not necessarily alter this interface.

## 2. Start from Consumer Needs

Suppose the same Orders system has three consumers:

| Consumer | Job to Be Done | Sufficient Information | Likely Suitable Interface |
|---|---|---|---|
| Customer portal | Open the **current status** of an order | ID, status, date, lines, amounts | **Query API** |
| Fulfillment | Know **an order was just confirmed** to start processing | Event ID, order ID, timestamp, required references | **Integration event** |
| Data warehouse | Compute **booked goods value** by date and product | Line-level grain, purchase-time price, historical dimensions | **Fact projection** from source/events |

The three consumers do not need the same JSON. For instance, Fulfillment might receive only a confirmation notice with `orderId`, then call an authorized API to fetch details when starting work. If Fulfillment must **operate autonomously when the Orders API is unavailable**, the event contract may need additional vetted data. That choice depends on autonomy, latency, and security requirements.

Before defining fields, build a table:

| Aspect | Question to Answer |
|---|---|
| **Purpose** | What decision or action will the consumer make? |
| **Owner** | Which system/bounded context owns the business truth? |
| **Grain** | What does one response, one event, or one read-model row represent? |
| **Timing** | Current state, at confirmation time, or at receipt time? |
| **ID** | Stable identifier scoped per tenant, store, or globally? |
| **Latency** | Is eventual consistency acceptable? |
| **Minimal data** | Which fields are truly used; which must not be shared? |
| **Versioning** | Who deploys first; will historical data be replayed? |
| **Protection** | Permissions, retention, sensitive data, replay, and derived copies? |
| **Verification** | Which tests prove the data has the right semantics? |

## 3. Running Example: Internal Orders Model

Suppose the Orders service owns:

~~~~text
orders(
    id, tenant_id, public_order_number, customer_id,
    status_code, confirmed_at, currency_code,
    row_version, internal_risk_score
)

order_items(
    order_id, line_no, product_id, quantity,
    unit_price_at_order, discount_amount
)

order_status_history(
    order_id, sequence_no, old_status, new_status, changed_at
)
~~~~

Assumed rules:

- `orders.id` is a stable internal identifier; `public_order_number` is a display code and may be unique only per `tenant_id`.
- An `order_items` row has grain `(order_id,line_no)`.
- Unit price and discount in this example are **snapshots at confirmation**, not current catalog prices.
- `status_code` holds granular technical statuses, which may need mapping to published statuses.
- Internal fields such as risk score are **not** returned merely because they exist in the DB.

~~~~mermaid
flowchart LR
    O["Orders domain\norders + items + history"] --> A["GET /orders/{id}\nCurrent status"]
    O --> E["OrderConfirmed\nFact that occurred"]
    O --> F["fact_order_lines\nSnapshot at confirmation"]
    A --> UI["Customer portal"]
    E --> W["Fulfillment"]
    F --> BI["Data warehouse"]
~~~~

There **do not necessarily** have to be three full copies of the data. The three arrows represent **three projections with distinct purposes and semantics**.

## 4. API Projection: Return What the Consumer Needs at Query Time

Example `GET /v1/orders/{orderId}` for callers authorized to view the order.

### 4.1. Illustrative Response JSON

~~~~json
{
  "orderId": "ord_87342",
  "orderNumber": "ORD-2026-00123",
  "status": "CONFIRMED",
  "confirmedAt": "2026-11-21T09:15:30Z",
  "currency": "VND",
  "items": [
    {
      "lineNo": 1,
      "productCode": "BOOK-01",
      "quantity": 2,
      "unitPrice": "100000.00",
      "discountAmount": "0.00"
    },
    {
      "lineNo": 2,
      "productCode": "PEN-02",
      "quantity": 1,
      "unitPrice": "50000.00",
      "discountAmount": "10000.00"
    }
  ],
  "bookedAmount": "240000.00"
}
~~~~

Assuming **a single currency VND**, excluding tax or shipping fees:

\[
\text{bookedAmount}
=\sum_i(\text{quantity}_i\times\text{unitPrice}_i-\text{discountAmount}_i)
=240.000.
\]

`bookedAmount` is the **value of ordered goods after line discounts**, not by default collected cash, accounting revenue, or net value after returns. Monetary fields use **decimal strings** to avoid depending on how consumers handle binary floating-point numbers; applications must parse them under currency rules rather than concatenating strings.

### 4.2. Contract Mapping Table

| Published Field | Source / Transformation | Stable Meaning |
|---|---|---|
| `orderId` | Stable public ID mapped from `orders.id` | API identifier, never reused |
| `orderNumber` | `public_order_number` | Display document code, explicit namespace |
| `status` | Mapped from `status_code` | Meaningful status set for consumers |
| `confirmedAt` | `confirmed_at` | Business confirmation milestone, not read time |
| `items[]` | Projection of each `order_items` ordered by `line_no` | Each line appears once |
| `currency` | `currency_code` | Unit of monetary fields |
| `bookedAmount` | Line sum per published formula | Never confused with paid/shipped amounts |
| Unpublished | Risk score, token references, technical metadata | Not serving the purpose or unauthorized |

The API can change its ORM layer, internal schema, or intermediate storage calculations **without** forcing consumers to change code, as long as contract semantics remain intact.

### 4.3. Abbreviated OpenAPI

~~~~yaml
openapi: 3.0.3
info:
  title: Orders Query API
  version: 1.0.0
paths:
  /v1/orders/{orderId}:
    get:
      summary: Fetch an order within the caller's authorized scope
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Projection of current order status
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/OrderView"
        "401":
          description: Unauthenticated
        "404":
          description: Not found within authorized scope
components:
  schemas:
    OrderView:
      type: object
      required: [orderId, orderNumber, status, currency, items, bookedAmount]
      properties:
        orderId:
          type: string
        orderNumber:
          type: string
        status:
          type: string
          description: Published status per business documentation
        confirmedAt:
          type: string
          format: date-time
          nullable: true
        currency:
          type: string
          minLength: 3
          maxLength: 3
        bookedAmount:
          type: string
          description: Ordered goods value, decimal string in currency
        items:
          type: array
          items:
            $ref: "#/components/schemas/OrderItem"
    OrderItem:
      type: object
      required: [lineNo, productCode, quantity, unitPrice, discountAmount]
      properties:
        lineNo:
          type: integer
          minimum: 1
        productCode:
          type: string
        quantity:
          type: integer
          minimum: 1
        unitPrice:
          type: string
        discountAmount:
          type: string
~~~~

This is an **abbreviated example**, omitting `securitySchemes`, timeouts, rate limits, full error codes, pagination/caching policies, and SLAs. Real APIs must include those details.

`confirmedAt` is not in `required`, yet if returned it may be `null`. If the business requirement is "**always present, though nullable**", place it in `required`. **Omitted**, `null`, empty string, and empty array do not automatically mean the same thing.

### 4.4. Authorization and Freshness

A query API typically reflects **state at the time of the query**; `status` may change from `CONFIRMED` to `SHIPPED` between two GET calls.

The contract must specify:

- Whether reads hit primary, cache, or replica, and what lag is acceptable.
- Whether the caller is authorized to view the resource within the tenant. **Knowing an ID does not grant permission.**
- When unauthorized, whether to return `403`, `404`, or another policy to avoid leaking resource existence.
- Whether `items[]` is complete or paginated, and whether ordering is guaranteed.
- Caching, `ETag`, version, or optimistic concurrency rules if writes exist.

## 5. Event Projection: Announcing What Has Happened

An **integration event** usually expresses a **confirmed business fact**: "Order `ord_87342` was confirmed at time X". It differs from the **command** `ConfirmOrder` ("please confirm the order"). Events are typically named in the past tense, such as `OrderConfirmed`, `PaymentCaptured`, or `ShipmentDispatched`.

### 5.1. Example Event Envelope + Payload

~~~~json
{
  "eventId": "7c2fd18a-ec77-47a9-a0a2-54a25e278d17",
  "eventType": "order.confirmed",
  "schemaVersion": 1,
  "tenantId": "T01",
  "aggregateId": "ord_87342",
  "aggregateVersion": 4,
  "occurredAt": "2026-11-21T09:15:30Z",
  "correlationId": "workflow_20261121_001",
  "payload": {
    "orderId": "ord_87342",
    "orderNumber": "ORD-2026-00123",
    "confirmedAt": "2026-11-21T09:15:30Z",
    "currency": "VND",
    "bookedAmount": "240000.00"
  }
}
~~~~

| Field | Semantic Contract |
|---|---|
| `eventId` | Identifies a **logical event**; retries of the same event must preserve this ID |
| `eventType` | Kind of business occurrence that took place |
| `schemaVersion` | Version of the **event shape/meaning**, not the order version |
| `tenantId` | Data ownership and access scope |
| `aggregateId` | Business object ID linking events belonging to the same order |
| `aggregateVersion` | Meaningful for ordering only if the producer truly guarantees monotonic increments **per order** |
| `occurredAt` | Business time of occurrence, not broker receipt time |
| `correlationId` | Ties steps of a workflow together for tracing; does not replace event ID |
| `payload` | Minimal information for the approved integration purpose |

This event **does not** emit emails, shipping addresses, payment tokens, risk scores, or all order lines because in this example the consumer only needs the event notification and ID to start its workflow. A consumer that must operate independently during API outages might require a broader payload, which demands **separate business justification, authorization, retention, and testing**.

### 5.2. Abbreviated JSON Schema

~~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "OrderConfirmedV1",
  "type": "object",
  "required": [
    "eventId", "eventType", "schemaVersion",
    "tenantId", "aggregateId", "occurredAt", "payload"
  ],
  "properties": {
    "eventId": { "type": "string", "format": "uuid" },
    "eventType": { "const": "order.confirmed" },
    "schemaVersion": { "const": 1 },
    "tenantId": { "type": "string", "minLength": 1 },
    "aggregateId": { "type": "string", "minLength": 1 },
    "aggregateVersion": { "type": "integer", "minimum": 1 },
    "occurredAt": { "type": "string", "format": "date-time" },
    "correlationId": { "type": "string" },
    "payload": {
      "type": "object",
      "required": [
        "orderId", "orderNumber", "confirmedAt",
        "currency", "bookedAmount"
      ],
      "properties": {
        "orderId": { "type": "string", "minLength": 1 },
        "orderNumber": { "type": "string" },
        "confirmedAt": { "type": "string", "format": "date-time" },
        "currency": { "type": "string", "pattern": "^[A-Z]{3}$" },
        "bookedAmount": {
          "type": "string",
          "pattern": "^[0-9]+(\\.[0-9]{1,2})?$"
        }
      }
    }
  }
}
~~~~

`aggregateVersion` and `correlationId` are **optional** here. In JSON Schema, `format` may require enabling **assertion** configuration depending on the validator; do not assume every library rejects malformed UUIDs or date-times. A schema checks **shape**—it does not prove real order state, accurate totals, or that the event was emitted after commit.

### 5.3. Differences Between APIs and Events

| Question | API Query | Integration Event |
|---|---|---|
| What point in time? | Usually **current** or defined snapshot | **Already occurred** at `occurredAt` |
| How received | Consumer actively calls | Consumer subscribes asynchronously |
| State changes | Next GET may differ | Emit a **new event**, never mutate the old one |
| Late-joining consumer | Call API to read latest | Needs replay/backfill if history is required |
| Primary risks | Timeouts, authorization, caching, pagination | Duplicates, out-of-order, lag, replay, DLQ |

**`OrderConfirmed` does not mean "the order is currently CONFIRMED".** The order may have been delivered or cancelled after the event was emitted. Consumers must track downstream events or query the live API when they genuinely need the latest status.

## 6. Domain Events Differ from Integration Events

A **domain event** can represent a state transition inside the Orders bounded context:

~~~~text
OrderAggregateConfirmed(orderId, aggregateVersion, internalContext)
~~~~

Never push internal entities or domain events straight onto a broker if consumers would become coupled to their structure. An **integration event** is mapped to a dedicated published contract:

~~~~text
order.confirmed v1 {
    eventId, tenantId, orderId,
    confirmedAt, currency, bookedAmount
}
~~~~

The mapping layer lets you:

- Change entities/ORMs/schemas without breaking consumers.
- Keep sensitive fields and technical metadata private.
- Decouple the public contract's version lifecycle from internal versions.
- Test event semantics independently of database storage layout.

The term **domain event** does not strictly mean an event that lives only in RAM, and **integration event** does not mandate a specific broker product. The distinction lies in **ownership boundaries and commitments to consumers**.

## 7. Bounded Contexts and Anti-Corruption Layers

Two systems using the same word may assign **different meanings**:

- Orders uses `customerId` to identify the **buyer**.
- Billing needs the party **responsible for payment**, which may be an organization.
- Fulfillment needs the **recipient**, who may differ from the buyer.

If everyone uses `customer_id` assuming the same entity, the JSON validates while the data is wrong. You must:

1. Identify which **bounded context** owns each concept.
2. Name fields by **role**, such as `buyerId`, `billToPartyId`, and `recipientId` when the business distinguishes them.
3. Use an **anti-corruption layer** to translate models from legacy systems or partners rather than scattering ad-hoc mappings across every consumer.
4. Log unmappable or missing data; never assume a one-to-one relationship blindly.
5. Never let consumers read another domain's DB tables directly to fill in missing API fields.

Consumers can maintain a **local read model** of needed data. That is an **intentional copy** with defined lag and rebuild rules, not permission to replicate the entire source database.

## 8. Contract Grain and Identifiers

| Component | Grain: What Is One Element? | Key Identifier(s) |
|---|---|---|
| Source `orders` | One current order | `orders.id` |
| `order_items` | One order line | `(order_id,line_no)` |
| API `GET /orders/{id}` | One order with authorized visible lines | Public `orderId` + permissions |
| `OrderConfirmed` | One valid confirmation | `eventId` (event), `aggregateId` (order) |
| `fact_order_lines` | One item line at confirmation | `(order_id,line_no)` per versioning rules |
| `fact_payment_transactions` | One payment transaction | `paymentTransactionId` |

One `orderId` may appear **once in an API response**, **once in a confirmation event**, yet **multiple times in line-item and payment facts**. Never use `orderId` as the unique key across all tables or events.

If `orderNumber='000123'` is unique only per store or tenant, the contract must include a **namespace** like `tenantId`/`storeId`, or a public ID guaranteed globally unique. Never infer global uniqueness from sample data.

Some systems assign a temporary code at creation and an official code upon confirmation; in that case, distinguish the **stable ID** from the **point-in-time display code**. Likewise, never use `eventId` in place of `orderId`: one order can produce many events.

## 9. Money, Time, Statuses, and Absent Values

### 9.1. Currency Units and Formulas

`bookedAmount="240000.00"` is unambiguous only when the contract states:

~~~~text
bookedAmount = sum(quantity × unitPriceAtOrder - lineDiscount)
currency     = VND
taxIncluded  = false per example
shippingFee  = excluded
rounding     = approved policy
~~~~

You can choose **integer minor units** or **decimal strings**; the choice must align with currency rules, rounding policy, and consumer precision capabilities. Avoid `DOUBLE` for monetary amounts requiring exact decimal representation.

### 9.2. Types of Timestamps

| Field | Meaning |
|---|---|
| `confirmedAt` | Order was confirmed in business terms |
| `occurredAt` | Event is deemed to have happened |
| `publishedAt` | Publisher emitted the message |
| `receivedAt` | Consumer/broker received the message |
| `updatedAt` | Current state was modified |

These timestamps **do not necessarily coincide**. For monthly confirmed-order reports, use `confirmedAt` and the approved business timezone rather than the date the consumer received the event.

### 9.3. Status Mapping

The source might have `CREATED`, `VALIDATING`, `PAYMENT_PENDING`, `CONFIRMED`, `ALLOCATING_STOCK`, `SHIPPED`, `DELIVERED`, `CANCELLED`. A UI API might expose fewer statuses: `PENDING`, `CONFIRMED`, `IN_TRANSIT`, `COMPLETED`, `CANCELLED`.

Status collapsing must be approved by the owner. Consumers using exhaustive `switch` statements can break when producers add new enum values; **expanding an enum is not always safe**.

### 9.4. Omitted, Null, and Empty

| Representation | Possible Contract Meaning |
|---|---|
| Field **omitted** | This version/read path does not publish the field |
| `field: null` | Unknown, not applicable, or cleared, **if explicitly defined** |
| `field: ""` | Actual empty string |
| `items: []` | List explicitly known to be empty |
| `amount: "0.00"` | Zero monetary value, **not** missing data |

Never let each consumer turn `null` into `0` or treat `items: []` as an error on its own. Write explicit tests for these cases.

## 10. Prevent Contracts from Leaking Data Beyond Their Purpose

Purposeful projection is also **data minimization**. Internal data such as risk scores, payment token references, PII, addresses, or detailed audit logs do not belong in APIs/events by default.

Before publishing a field, ask:

1. Which **decision or action** does the consumer use this field for?
2. Is the consumer authorized to receive this field within the given **tenant/user scope**?
3. Does the value need to be raw, or is a status bucket or surrogate ID enough?
4. How long will the consumer retain the field, and will it be copied to search, caches, warehouses, logs, or backups?
5. If the value is corrected or a valid erasure request arrives, how will derived copies handle it?

An event can be stored in a broker, sent to a dead-letter queue, replayed, copied to many consumers, and retained long-term. Therefore, the exposure risk of **over-stuffed events** can be especially hard to contain.

**Dropping columns alone is not enough:** if an endpoint lets callers guess someone else's `orderId`, omitting email still does not replace **authorization checks**. Enforce identity, tenant, permission, sensitivity, and retention policies on every read/event path.

## 11. APIs and Events Have Different Operational Contracts

### 11.1. For APIs: Errors, Freshness, and Retries

An API contract should define:

- HTTP method/path, query parameters, and filter semantics.
- Error codes such as `400`, `401`, `403`, `404`, `409` per scenario, plus rules **preventing existence leaks** for unauthorized resources.
- Pagination for large results, with stable sorting or cursors to avoid duplicates/gaps across pages.
- Timeouts, retries, rate limits, and idempotency for write APIs where applicable.
- Freshness when using caches/read replicas; is **read-your-writes** guaranteed?
- `ETag`/version when using optimistic concurrency control.

Two consecutive `GET` calls can return different statuses if the order progressed. That is not a bug if the contract promises **current state** and accurately states staleness bounds.

### 11.2. For Events: At-Least-Once, Duplicates, and Reordering

Many real messaging systems operate under **at-least-once** semantics: an event may be delivered **multiple times** on retries or when a consumer finishes processing but its ACK is lost.

Consumers must anticipate:

- **Duplicate:** the same `eventId` may appear multiple times.
- **Out-of-order:** event version 5 may arrive before version 4 depending on partitioning/routing and processing.
- **Late event:** an event occurred yesterday and arrives today.
- **Poison message:** unparseable or invalid to apply.
- **Replay/backfill:** reprocessing old events to rebuild a read model.

Never claim **exactly-once end-to-end** just because a broker advertises a special transactional mode. Evaluate the entire chain from source DB, publisher, broker, and consumer through **side effects** such as sending emails, calling other APIs, or creating shipping orders.

### 11.3. Handling Duplicates with Inbox and Business Invariants

Sample PostgreSQL DDL:

~~~~sql
CREATE TABLE consumer_inbox (
    consumer_name TEXT NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~~

Illustrative processing flow:

~~~~text
BEGIN TRANSACTION
    Attempt INSERT (consumer_name, event_id) into consumer_inbox

    If key already exists:
        Skip the already-applied business update

    If this is a new event:
        Update read model per semantics and version

COMMIT
ACK once the transaction and required processing complete
~~~~

This is **pseudocode**, not standalone SQL. If updating the inbox and read model occurs **in the same DB transaction**, they commit or roll back together. If the consumer also calls an external system or emits new events, you need separate **idempotency and outbox mechanisms for side effects**. An inbox table alone cannot guarantee an email or payment charge executes only once.

### 11.4. Aggregate Version Does Not Mean Global Order

`aggregateVersion=4` is useful when:

- The producer **genuinely increments version consistently across state transitions of the same order**.
- The consumer knows how to handle receiving 5 before 4 or missing versions.
- Aggregate identifiers are stable within the proper namespace.

It **does not** establish a global ordering across events of two different orders; `occurredAt` is likewise unreliable for sequencing under clock skew.

## 12. Transactional Outbox: Keeping Business State and Intended Messages Together

A common buggy pattern:

~~~~text
1. UPDATE orders SET status = CONFIRMED
2. Database COMMIT succeeds
3. Publish OrderConfirmed to broker
4. Process crashes between step 2 and 3
~~~~

Result: **the order is confirmed in the DB, yet consumers never receive the event**. Sending the event **before** commit is also flawed: a DB rollback broadcasts a notification for an event that never occurred.

The standard solution is a **transactional outbox**:

~~~~mermaid
flowchart LR
    T["Single transaction in Orders DB"] --> U["Update order"]
    T --> X["Write integration_outbox"]
    X --> P["Publisher / CDC"]
    P --> B["Broker"]
    B --> C["Idempotent consumer"]
    C --> R["Read model"]
~~~~

Within **the same source transaction**:

1. Validate transition conditions for `PENDING → CONFIRMED`.
2. Update the order's status, timestamp, and version.
3. Compute finalized values and insert an **outbox row containing the integration event** per published contract.
4. Commit both changes together.

A worker/CDC reader reads committed outbox rows, publishes to the broker, and records completion for retry tracking.

### Illustrative Outbox DDL

~~~~sql
CREATE TABLE integration_outbox (
    event_id UUID PRIMARY KEY,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    schema_version INTEGER NOT NULL CHECK (schema_version > 0),
    occurred_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ
);

CREATE INDEX idx_outbox_unpublished
    ON integration_outbox (created_at, event_id)
    WHERE published_at IS NULL;
~~~~

Illustrative business workflow SQL (`:param` placeholders are **application parameters**):

~~~~sql
BEGIN;

UPDATE orders
SET status_code = 'CONFIRMED',
    confirmed_at = :confirmed_at,
    row_version = row_version + 1
WHERE id = :order_id
  AND status_code = 'PENDING'
RETURNING id, tenant_id, public_order_number,
          confirmed_at, row_version;

-- Application must verify UPDATE returned exactly one row.
-- Line-item/monetary data must be finalized consistently.
-- If UPDATE affected 0 rows: ROLLBACK, do not INSERT event.

INSERT INTO integration_outbox (
    event_id, aggregate_type, aggregate_id,
    event_type, schema_version, occurred_at, payload
)
VALUES (
    :event_id, 'order', :order_id,
    'order.confirmed', 1, :confirmed_at, CAST(:payload AS jsonb)
);

COMMIT;
~~~~

This pattern **does not replace** real transaction logic: you must still enforce permissions, valid transitions, monetary calculations, source data atomicity, and concurrency handling. If `UPDATE` updates no rows, the application must roll back before emitting an event. `row_version` illustrates versioning; column names and update rules must match your real source.

**An outbox does not eliminate duplicate delivery.** The publisher may send successfully and crash before updating `published_at`, causing a resend. Consumers must still be idempotent.

### CDC Does Not Equal Integration Events

CDC (*change data capture*) reads committed changes. However, streaming **raw `orders` rows from WAL/binlog** binds consumers to internal table and column names. You can run CDC **on the outbox table already holding contracted payloads**, or translate CDC through an anti-corruption/contract layer with explicit rules.

## 13. Events into Purposeful Read Models

Fulfillment can build a local projection:

~~~~text
OrderConfirmed
    ↓
Fulfillment read model:
    tenant_id, order_id, confirmed_at, processing_state
~~~~

Example DDL:

~~~~sql
CREATE TABLE fulfillment_order_queue (
    tenant_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    confirmed_at TIMESTAMPTZ NOT NULL,
    processing_state TEXT NOT NULL,
    source_aggregate_version BIGINT,
    PRIMARY KEY (tenant_id, order_id)
);
~~~~

This is **not a copy of every Orders attribute**. It stores only what is needed to manage fulfillment work. This system does not become the owner of original order state just because it holds a table with `order_id`.

### Consistency Bounds to Agree Upon

- **Update lag:** the Orders API already returns `CONFIRMED`, while the Fulfillment queue does not yet have the row. Set lag SLOs, alerts, and handling rules.
- **Duplicates:** never create two jobs for one logical event; enforce event IDs and business invariants.
- **Out-of-order:** never let an older-state event overwrite a newer state.
- **Missing events:** provide replay, reconciliation, or backfill from the owner.
- **Cancelled orders:** an `OrderCancelled` event or owner query must trigger stop-processing rules suited to the actual physical state.
- **Rebuilds:** the consumer must be able to rebuild the projection from event history, trusted snapshots, or supported APIs/bulk exports.

If a consumer must operate autonomously when Orders is down, the projection may retain **more data**; that is a deliberate trade-off on autonomy, **lag, and privacy**, not an excuse to clone the entire database.

## 14. Verifying Projections: Do Not Multiply Measures When Joining

Suppose an order has:

~~~~text
3 order_items
2 payment_transactions
2 shipments
~~~~

Joining all three tables on `order_id` and running `SUM(item_amount)` can produce:

\[
3\times2\times2=12\text{ rows}.
\]

Each order line is repeated **4 times**; booked goods value inflates fourfold. **Valid JSON can still be wrong in business terms.**

### 14.1. Compute `bookedAmount` at Line Grain, Then Aggregate to Order Grain

~~~~sql
WITH amounts_by_order AS (
    SELECT
        order_id,
        SUM(
            quantity * unit_price_at_order - discount_amount
        ) AS booked_amount
    FROM order_items
    GROUP BY order_id
)
SELECT
    o.id AS order_id,
    o.tenant_id,
    o.public_order_number,
    o.status_code,
    o.confirmed_at,
    o.currency_code,
    a.booked_amount
FROM orders AS o
LEFT JOIN amounts_by_order AS a
  ON a.order_id = o.id
WHERE o.id = :order_id
  AND o.tenant_id = :tenant_id;
~~~~

`amounts_by_order` has **one row per order ID**. This example filters by tenant to avoid cross-scope leaks, though it **does not replace caller authorization checks**. `LEFT JOIN` can yield `booked_amount = NULL` when an order has no lines; the contract must decide whether that state is valid or blocked by business rules. Across multiple currencies or versions, compute within matching scope and conversion rules.

### 14.2. Mapping Test

~~~~text
Given:
    Order ord_87342 has two locked lines:
    (2 × 100000 - 0)
    (1 × 50000 - 10000)

When:
    Generate OrderView and OrderConfirmed v1

Then:
    bookedAmount = "240000.00"
    currency = "VND"
    confirmedAt reflects the business confirmation timestamp
    no internalRiskScore or paymentTokenRef present
    both item lines are returned exactly once in the API
~~~~

Checking **JSON types, permissions, and calculated values** requires distinct tests. A contract test that only checks for a string field named `bookedAmount` will miss amounts inflated by a bad JOIN.

## 15. Evolving Contracts Without Breaking Consumers

Internal schema changes are not necessarily contract changes. However, changing the name, type, or **business meaning** of a public field can break consumers.

| Change | Usually Safe for Legacy Consumers? | What Must Be Checked |
|---|---|---|
| Adding an **optional** field to response/event | **Conditionally** | Strict consumers/closed schemas may reject unknown fields |
| Adding a **required** field to request | Usually **breaking** | Old clients do not send the field |
| Removing/renaming an existing field | Usually **breaking** | Old consumers still read the old name |
| Changing `orderId` from string to number | **Breaking** | Loses leading zeros, type, and namespace |
| Changing `bookedAmount` from booked value to collected cash | **Semantically breaking** | Schema validators do not catch it |
| Adding a new `status` value | **Conditionally** | Consumers using exhaustive switches |
| Changing `confirmedAt` to publish time | **Semantically breaking** | Period reports can become inaccurate |
| Adding a new event type | Can be safe | Do wildcard subscribers handle the new event? |
| Changing ordering of `items[]` | Depends on contract | Do consumers rely on ordering? |
| Changing ID/namespace | High risk | Deduplication, permissions, and event linking |

### Pragmatic Versioning

1. Publish schemas and field semantic documentation; adopt a consistent versioning strategy such as `/v1` for APIs and `schemaVersion` in events.
2. Non-breaking changes must be **tested against real consumers**, not merely assumed safe by a "new field is fine" rule.
3. For breaking changes, consider running **v1 and v2 in parallel** during a transition window.
4. Announce deprecation, measure remaining v1 consumer usage, and finalize sunset dates per policy.
5. For long-lived events, plan upfront **how v2 consumers will read v1 events during replay**.
6. When changing **meaning** rather than just renaming, provide real conversion rules; never upcast historical data by guessing.

### Backward and Forward Compatibility

- **New consumer reads old data:** essential for replay/backfill.
- **Old consumer reads new data:** essential if producers deploy first.

The labels `BACKWARD`/`FORWARD` in schema registries can be defined relative to **schema writer–reader** roles; explicitly document **who writes, who reads, and rollout order** to avoid misapplication.

## 16. Multi-Layer Contract Testing

### 16.1. Shape/Schema Tests

Validate OpenAPI/JSON Schema/AsyncAPI at the level of required fields, types, formats, versions, enums, nullable/omitted behavior, decimals, and arrays. When using codegen, test tolerance for unknown fields as well.

### 16.2. Semantic Contract Tests

Verify meaning:

- `bookedAmount` equals the sum from order lines per the confirmed formula.
- `OrderConfirmed` is written only when a valid state transition commits.
- `confirmedAt` is the business timestamp, not consumer receipt time.
- `tenantId` and `orderId` identify the right scope.
- Sensitive data never crosses the boundary.

### 16.3. Consumer-Driven Contracts

Consumers supply examples/expectations for fields they **actually use**; the producer runs tests to see if changes break consumers. However, consumer-driven tests **do not replace** canonical schemas, security checks, or owner sign-off on semantics.

### 16.4. Failure/Recovery Tests

| Scenario | Expected Result |
|---|---|
| DB commit succeeds, publisher crashes before sending | Outbox retains the event for retry |
| Publisher sends successfully, crashes before marking sent | Consumer handles **duplicate event ID** safely |
| Event version 5 arrives before version 4 | Older state never overwrites newer state |
| Consumer is down for one day | Lag is monitored; replay/backfill recovers |
| Replaying v1 on a consumer upgraded to v2 | Readable via old schema support or valid upcaster |
| Caller from another tenant | Cannot view unauthorized resources |
| A new internal field is added to the ORM | Not automatically serialized into API/events |
| Contract shape valid, amounts wrong from JOIN | Caught by semantic tests and reconciliation |
| Source table renamed | Consumers need no changes if contract holds |
| Read model lost | Rebuildable from owner-supported sources |

### 16.5. Operational Monitoring

~~~~text
outbox_unpublished_age_seconds
outbox_pending_events
consumer_lag_seconds
duplicate_event_count
invalid_contract_message_count
dead_letter_count
api_contract_error_rate
data_reconciliation_mismatch_count
projection_rebuild_duration
deprecated_version_consumers
~~~~

Thresholds/SLOs must derive from real requirements. Duplicate events are not automatically an incident under at-least-once delivery, whereas **duplicate side effects must not occur**, and abnormal retry spikes require alerts.

## 17. Workflow for Designing Purposeful Projections

### Step 1 — Identify Questions, Actions, and Consumers

For example: "Fulfillment needs to know **an order was just confirmed** to begin work, without risk scores or payment details." That justifies choosing an **event**.

### Step 2 — Choose Owner and Source of Truth

Which system is responsible for defining "confirmed", amounts, customer, and order lines? Consumers must not join across another domain's DB to invent their own definitions.

### Step 3 — Finalize Grain, IDs, and Timing

Write explicitly: "one event per valid order confirmation", "one API response per current order". Confirm stable IDs, namespaces, timestamps, and acceptable lag.

### Step 4 — Build an Intentional Mapping Table

For each field: **source → transformation rule → type → meaning → permissions → tests**. List fields that must **not** be shared. Never ship raw entities over the network.

### Step 5 — Design Consistency and Failure Handling

How do API caches/replicas behave? Do events have outbox, retries, IDs for deduplication, ordering, and replay? Should consumers receive an initial snapshot or call an API after receiving the event?

### Step 6 — Finalize Evolution and Testing

Document versions, compatibility, and rollout; run shape, semantic, security, consumer-driven, duplicate/late-event, and recovery tests.

### Step 7 — Measure and Review Periodically

Monitor lag, contract errors, replays, projection drift, and legacy-version consumers. When internal schemas evolve, update only the mapping layer as long as **contract semantics remain unchanged**.

## 18. Connections Across Relational, Document, Graph, and Analytical Models

| Internal Model | What Might It Store? | Outward Projection |
|---|---|---|
| **Relational** | `orders`, `order_items`, FKs, FDs, status | API assembles one order; event selects state transitions |
| **Document** | Order with `items[]` array, technical metadata | API trims fields, controls arrays and permissions |
| **Graph** | Order/buyer/product nodes and edges | API returns verified relationships/paths, never dumps entire graph |
| **Analytical** | Facts at event/line/snapshot grain, historical dimensions | Fact projections/events with accurate timing and KPIs |

**Contract boundaries do not vanish when switching DBMSs.** A document having many fields does not force an API to return all of them; a graph traversal yielding multiple paths does not prove multiple events occurred; a data mart holding `orderId` does not mean `OrderConfirmed` events must carry every BI measure.

## 19. Common Misconceptions

| Misconception | Consequence | Fix |
|---|---|---|
| "Just let the API serialize the entity/ORM" | Leaks schema and sensitive fields | Purpose-built independent DTOs/contracts |
| "An event is a DB row that just changed" | Raw CDC binds consumers to tables/columns | Semantically meaningful integration events |
| "Projection is just dropping columns" | Neglects money, status, and permission conversions | Verified explicit mappings |
| "Knowing `orderId` means allowed to view" | Cross-tenant data exposure | Enforce authz and scope checks |
| "`OrderConfirmed` means the order is currently CONFIRMED" | Ignores subsequent transitions | Distinguish past events from current state |
| "`eventId` and `orderId` are the same" | Cannot deduplicate multiple events for one order | Separate event IDs and aggregate IDs |
| "Broker is exactly-once, so skip consumer dedup" | Side effects can still repeat | Idempotency/inbox and side-effect guards |
| "DB commit then publish cannot lose events" | Crash between the two steps | Outbox or equivalent durable mechanism |
| "All events have global order" | Breaks under partitions and parallel consumers | Agree on per-aggregate ordering |
| "Adding a field is always compatible" | Strict clients may fail | Contract tests and schema compatibility checks |
| "Changing meaning while keeping type is safe" | Wrong KPIs while JSON still parses | Semantic versioning and reviews |
| "If `orderId` exists, JOIN every fact" | Many-to-many fanout | Aggregate to shared grain first |
| "Deleting in Orders deletes all events" | Read models, DLQs, backups still hold copies | Data lineage, retention, and purge workflows |
| "Let consumers read source DB for speed" | Breaks ownership boundaries and versioning | Contracted APIs, events, or bulk exports |

## 20. Practice Exercises with Solutions

### Exercise 1 — Choosing API vs. Event

The Customer Portal needs to view the **current status** when a user opens an order; Fulfillment needs to know **an order was just confirmed**. What should each use?

**Solution:** The Portal uses an access-controlled **query API**. Fulfillment can use the **`OrderConfirmed` integration event**. The two contracts serve different timings and purposes.

### Exercise 2 — Selecting Fields

An internal entity contains `orderId`, `confirmedAt`, `internalRiskScore`, `paymentTokenRef`, and `customerEmail`. The consumer only needs to create a fulfillment task keyed by order ID.

**Solution:** Publish the ID, timestamp, and required event metadata; omit risk score, payment token, and email if there is no approved purpose or permission. If details are needed later, use a separate vetted contract.

### Exercise 3 — Three Kinds of Identifiers

An order has `orderId=ord_42`, `orderNumber=HN-2026-0001`, and a distinct `eventId`. How do they differ?

**Solution:** `orderId` identifies the **object**, `orderNumber` is a namespaced display document code, and `eventId` identifies **one logical event**. One order has many events, so never use the order number as an event ID.

### Exercise 4 — Duplicate Event Delivery

An `OrderConfirmed` event is delivered twice due to a lost ACK. May the consumer create two delivery tasks?

**Solution:** No, if business rules permit only one task per order confirmation. Enforce **idempotency** by event ID and business invariants; protect side effects outside the DB with dedicated idempotency keys.

### Exercise 5 — Post-Commit Crash Gap

The DB committed `CONFIRMED`, and the process crashed before publishing. What design prevents losing the event?

**Solution:** **Transactional outbox** persists the state change and intended event record in the same transaction; a publisher retries from the outbox. Consumers must still handle duplicates.

### Exercise 6 — Renaming a Field

A producer renames `confirmedAt` to `approvedAt` in event v1 and drops the old name. Are legacy consumers safe?

**Solution:** Usually **no**. That is a breaking rename; it requires a transition period or a new version. If "approved" also differs in meaning from "confirmed", that is a **semantic** change requiring separate review.

### Exercise 7 — Adding an Optional Field

A producer adds an optional `salesChannel` field to a JSON response. Are old consumers guaranteed to keep working?

**Solution:** Not guaranteed, because strict consumers may reject unknown fields. Check writer/reader schemas, codegen settings, and consumer contract tests before rollout.

### Exercise 8 — JOIN Corrupting KPIs

Order D01 has 3 item lines, 2 payments, and 2 shipments. Joining all of them on order ID and running `SUM(lineAmount)` causes what error?

**Solution:** It produces \(3\times2\times2=12\) rows; each line amount is counted four times. Compute money at **line grain → aggregate to order grain** before joining other sources. Never use `SUM(DISTINCT amount)` as a workaround hack.

### Exercise 9 — Out-of-Order Events

A consumer receives aggregate state version 6, then version 5. Should version 5 overwrite version 6?

**Solution:** No, if this is a **latest-state** projection and the producer guarantees monotonically increasing per-aggregate versions. Handle sequences, gaps, and retries explicitly; if the consumer stores an **append-only event log**, it can record both with timestamps/versions for reconstruction.

### Exercise 10 — Order Number Namespace

Two tenants both have `orderNumber=000123`. A consumer stores `orders_by_number(orderNumber PRIMARY KEY)`. What is wrong?

**Solution:** Missing **namespace**. Use key `(tenantId,orderNumber)` or a globally unique public ID per contract; otherwise orders from different tenants collide and overwrite each other.

### Exercise 11 — Event Time and Reporting

An order is confirmed at `2026-10-31T23:59:00Z` and received by the consumer at `2026-11-01T00:03:00Z`. Which month does a report grouped by **UTC confirmation date** assign it to?

**Solution:** **October**, using `confirmedAt`, not receipt time. Late-arriving data requires an update or closed-period reconciliation process.

### Exercise 12 — Replaying After Schema Upgrade

v1 events were stored for a year, and the producer now emits v2. A new consumer must build a read model from both v1 and v2.

**Solution:** The consumer must support both schemas or apply a valid **upcaster** using version metadata. Simple field renaming is insufficient if v2 changed the **meaning of amounts, statuses, or timestamps**.

## 21. Pre-Publish Contract Checklist

- [ ] Identified **consumers, purpose, and actions** to be taken.
- [ ] Specified **bounded context owner** and source of truth.
- [ ] Distinguished live-state APIs, past-fact events, and read models/facts.
- [ ] Declared **grain**, stable identifiers, and tenant/source namespaces.
- [ ] Documented mapping **field → source/transformation/type/meaning/permissions**.
- [ ] Selected **minimal fields**, excluding unnecessary internal or sensitive data.
- [ ] Defined currencies, units, rounding, and KPI definitions unambiguously.
- [ ] Kept `occurredAt`, `confirmedAt`, `publishedAt`, and `receivedAt` distinct.
- [ ] Defined policies for `null`, omitted fields, empty arrays, and unknown enums.
- [ ] Specified API authn, authz, errors, caching, and pagination/consistency where needed.
- [ ] Included event ID, schema version, aggregate ID, and duplicate/ordering/replay rules on events.
- [ ] Implemented outbox or equivalent reliable emission **after business commit**.
- [ ] Ensured consumer idempotency and handling for side effects, retries, DLQs, and backfills.
- [ ] Reconciled published data against sources and verified JOINs do not multiply measures.
- [ ] Maintained appropriate OpenAPI/JSON Schema/AsyncAPI specs plus shape, semantic, and consumer contract tests.
- [ ] Defined compatibility, version rollout, deprecation, and historical replay policies.
- [ ] Set up monitoring for lag, invalid messages, duplicates, read-model errors, and ownership.
- [ ] Documented data lineage, retention, and propagation of valid corrections/deletions to derived copies.

**Takeaway:** **API and event contracts are purposeful projections of business truth across ownership boundaries**, not raw copies of a table or entity. Good contracts share only what is needed, with stable grain, timing, IDs, and meaning—while protecting data, planning evolution, and backing claims with tests. When internal models change without altering contract semantics, systems can evolve more independently **without sacrificing data correctness**.
