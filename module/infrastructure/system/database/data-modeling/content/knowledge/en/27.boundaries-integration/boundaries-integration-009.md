# Data Ownership Across Services and Avoiding Uncontrolled Table Sharing

## 1. The Problem: Multiple Services Touching One Table—Who Is Responsible?

Suppose a commerce platform has four services: **Catalog** manages products, **Ordering** manages orders, **Inventory** manages stock, and **Payment** manages charge/refund requests. For convenience, all four services use shared `product` and `orders` tables inside one database. Catalog edits product names; Ordering queries Catalog's table directly to render names in order details; Inventory updates `product.stock_quantity`; Payment writes `orders.payment_status = 'PAID'` after receiving a callback.

This design may work in a small prototype, yet as the system scales, very hard questions arise:

- When `product` needs a schema change, which team holds approval authority and who must update their code?
- Must every update to `stock_quantity` pass through reservation logic and overselling guards?
- Does `payment_status = 'PAID'` mean a charge request was sent or the provider confirmed settlement?
- Who may delete a customer, and which tables are permitted to retain related financial records?
- When reports disagree, which source is authoritative for the true value?

This is a **data ownership** problem, not merely a question of which database holds which tables.

**Core principle:** every **authoritative business fact** needs a single clear owner responsible for its definition, invariants, recording, and lifecycle; other services access it via **governed integration contracts** rather than writing arbitrarily into the owner's tables.

Ownership does not mean each service can read only one kind of data or may never copy anything. A service may maintain a **derived read model / cache** of data owned elsewhere, as long as its source, freshness, sync mechanism, usage rights, and handling of source updates/deletes are explicit.

## 2. Ownership Means Authority Over Semantics and Invariants, Not Just Hosting Servers

A service **owns** data when it holds the authority and responsibility to:

1. Define **entities, business keys, constraints, and business statuses**.
2. Accept or reject commands that mutate facts within its scope.
3. Decide the **commit point** of a fact: `PaymentCaptured` only after payment-provider confirmation, `StockReserved` after inventory accepts the hold.
4. Publish versioned **APIs/events/data contracts** for consumers.
5. Govern schemas, migrations, permissions, retention, and remediation/adjustments for bad data.
6. Explain consistency states and verify data against authoritative sources.

Four concepts to distinguish:

| Concept | Primary Question | Example |
| --- | --- | --- |
| **Business / domain ownership** | Who decides whether a fact is valid? | Inventory decides whether 1 seat / 1 item can be held. |
| **Data storage ownership** | Who manages tables, documents, indexes, and physical migrations? | Inventory team manages the `inventory` schema. |
| **Data contract ownership** | Who commits to field meanings, schemas, and delivery timing? | Catalog publishes `ProductChanged.v2`. |
| **Data stewardship / governance** | Who oversees org-wide quality, permissions, reference sets, and policies? | Data governance partners with domain owners. |

An infrastructure team operating one shared PostgreSQL cluster for multiple services **does not mean** that team defines what "paid order" means. Conversely, a domain owner may run on platform-managed storage while still owning business contracts and decisions.

### Draw Boundaries Around Business Capabilities

Do not draw boundaries around tables first and invent "ProductService because there is a `product` table". Examine capabilities and invariants:

- **Catalog:** product identity, content, classification, publication status.
- **Inventory:** available quantity, reservations, releases, and no-over-allocation rules.
- **Ordering:** order lifecycle, order lines, cancellation/confirmation per order rules.
- **Payment:** charge/refund transactions, provider call idempotency, reconciliation.
- **Customer Identity:** customer identity, permitted contact info, account lifecycle.

Capabilities can share one application while the system is small; ownership boundaries remain valuable even before splitting into microservices.

## 3. Source-of-Truth Map: Who May Write What?

Create an **ownership matrix** before implementing data relationships or integrations.

| Fact | Authoritative Source | Services That May Need to Read | What Not to Do |
| --- | --- | --- | --- |
| Published product name / category | Catalog | Ordering, Search, Recommendation | Ordering directly editing `catalog.product_name`. |
| Available stock and reservations | Inventory | Ordering, Storefront | Storefront decrementing a cached count and declaring stock reserved. |
| Finalized orders and lines | Ordering | Support, Payment, Analytics | Payment directly updating order rows to mark paid. |
| Provider-confirmed capture / refund | Payment | Ordering, Accounting, Analytics | Ordering treating `RefundRequested` as funds refunded. |
| Customer identity and data processing rights | Customer Identity | Ordering, Support | Each service editing master email independently on email-change requests. |
| Daily net revenue KPI | Analytics / Finance with approved definition | Dashboards, management | Each dashboard inventing its own `revenue` from different sources. |

**One source of truth per scoped fact**, not one "enterprise master database for everything". For instance, Catalog owns **current list price**, while Ordering owns **the locked unit price on an order line**. Both values talk about price, yet they are not two copies of the same fact:

- `catalog.current_price`: at what price is the product currently offered?
- `order_line.agreed_unit_price`: what unit price did the customer agree to when placing the order?

Ordering **must preserve the locked price** of the transaction rather than re-reading Catalog and rewriting old orders when list prices change. Visually similar data can be completely valid because **authoritative semantics and point-in-time differ**.

### A Sentence Template for Writing Boundaries

> "Service **X** is the authoritative source for **fact Y** within scope **Z**. Every mutation to Y must go through X's **commands/contracts**; other services may keep **derived copy D** to serve **query Q**, with explicit **lag/retention**."

This template forces design teams to state parts commonly skipped: scope, versioning policy, and derived copies.

## 4. The Shared-Table Anti-Pattern: Sharing Tables Erodes Contracts

A **shared database** is not automatically wrong, yet **multiple services directly accessing and mutating each other's business tables without contracts** is a major hazard.

### Common Failure Pattern

~~~text
Catalog API -------- INSERT / UPDATE -----+
                                          |
Ordering API ------- SELECT / UPDATE -----+--> product (shared table)
                                          |
Inventory worker ---- UPDATE stock -------+
                                          |
Reports ----------- SELECT / JOIN --------+
~~~

Suppose Catalog changes `product.status` from `ACTIVE` to two values `PUBLISHED` and `SUSPENDED`. Ordering queries `WHERE status = 'ACTIVE'`; Inventory treats `status != 'DELETED'` as sellable. Each consumer attached **its own semantics** to one physical column, turning a simple migration into a multi-team coordinated rollout.

### Dangerous Coupling Patterns

| Coupling Type | Consequence |
| --- | --- |
| Service A `UPDATE`s B's table | B's permission checks, invariants, and side effects are bypassed. |
| Service A creates direct FKs/JOINs into B's table | B's schema migrations become breaking changes for A. |
| Multiple services deploy migrations on one table | Contested ownership, unclear migration order and rollback. |
| Services use triggers on a shared table to emit events | Consumers depend on hidden side effects; hard to control as rules evolve. |
| Dashboards read OLTP tables with superuser accounts | Adds load, leaks internal data, blocks versioned contracts. |
| A team modifies a table "just adding a column" | Can break strict consumers or mislead defaults. |
| Multiple systems write overlapping statuses | No single source of truth; lost updates and unreconcilable data. |

**Special warning:** granting read-only `SELECT` directly does not eliminate coupling. Consumers still depend on internal columns, code values, JOIN paths, and row lifecycles the owner never promised. Read-only access reduces write-corruption risk—**it does not create a stable semantic contract**.

### When Can a Shared Database Be Acceptable?

- **Modular monolith:** modules share one deployment/transaction unit with clear logical access control, explicit schema owners, and coordinated migrations.
- **Transitional migration phase:** temporarily allowing a consumer to read a legacy table, backed by a dependency register, narrow permissions, a hard sunset date, and a contract replacement plan.
- **Published reference dataset:** exposing owner-managed read views or schemas with contracts, versions, and monitoring—never opening direct access to core operational tables.

State trade-offs explicitly. Never force database-per-service prematurely without reason, yet never treat raw table sharing as a long-term integration interface without ownership.

## 5. Isolation Levels: From Separate Schemas to Separate Databases

Ownership is a **logical** boundary; physical isolation and access controls help enforce that boundary.

| Option | Benefits | Limits and Effort |
| --- | --- | --- |
| Same database, clear module tables/schemas | Easy local transactions, low operational overhead | Must govern roles, migrations, and prevent arbitrary cross-module queries |
| Separate databases on same server/cluster | Separates credentials and some admin/backup privileges | Resource contention remains; cross-database features vary |
| Separate database/cluster per service | Isolates schemas, deployment pipelines, and many resources | Higher infra cost; cross-source JOINs and transactions are harder |
| Service owns store and publishes read models / data products | Consumers read stable shapes; separates OLTP from BI loads | Must govern sync, freshness, permissions, and contract versions |

**Database-per-service is one way to enforce ownership, not the definition of ownership.** If two services share a cluster while strictly following single-owner writes, contract-based communication, and clear migration ownership, boundaries stay clean. Conversely, two physically separate databases where app A logs directly into B and `UPDATE`s B's tables still violate ownership.

### Schema Boundaries in PostgreSQL

One enforcement mechanism is assigning dedicated owner roles per schema. The example below illustrates restricting *DDL privileges* and *data access* when sharing PostgreSQL:

~~~sql
-- Run by an admin/deployment account with appropriate privileges.
CREATE ROLE catalog_owner NOLOGIN;
CREATE ROLE ordering_owner NOLOGIN;

CREATE SCHEMA catalog AUTHORIZATION catalog_owner;
CREATE SCHEMA ordering AUTHORIZATION ordering_owner;

REVOKE ALL ON SCHEMA catalog FROM PUBLIC;
REVOKE ALL ON SCHEMA ordering FROM PUBLIC;

-- Application runtime roles are created/managed via your org's
-- IAM and secrets mechanism; never hardcode passwords in this script.
-- Assume catalog_runtime and ordering_runtime already exist.
GRANT USAGE ON SCHEMA catalog TO catalog_runtime;
GRANT USAGE ON SCHEMA ordering TO ordering_runtime;
~~~

**Note:** **schema** privileges and **table/sequence/function** privileges are two separate layers. `GRANT USAGE ON SCHEMA` **does not automatically grant `SELECT/INSERT/UPDATE` on tables**. Each owner grants only necessary privileges to its own runtime, e.g., on Catalog's table:

~~~sql
-- Executed by catalog_owner or an authorized deployment role.
GRANT SELECT, INSERT, UPDATE, DELETE
ON catalog.product TO catalog_runtime;

-- Do NOT GRANT UPDATE/DELETE on catalog.product to ordering_runtime.
-- Ordering receives derived copies via API/events.
~~~

These statements assume `catalog.product` and both runtime roles already exist; this is an access-control example, not an end-to-end standalone migration. For identity columns/sequences or functions, grant dependent privileges per your actual structure. Runtime accounts should not own all tables and should not hold arbitrary DDL rights.

A simple verification rule: **a service runtime must be rejected by the database if it attempts to mutate a table owned by another service**, even if a developer writes a buggy SQL query by mistake.

## 6. Connecting Services: Synchronous, Asynchronous, or Read Copies?

Not every consumer needs the same access pattern.

| Mechanism | Best Suited For | Trade-off |
| --- | --- | --- |
| **Synchronous API / command** | Immediate owner decision to protect invariants: reserving stock, checking limits, strictly fresh reads | Network latency, timeouts, cascading failures; requires SLOs and meaningful fallbacks |
| **Contracted Query API** | Fetching a single object or filtered list committed by the owner | Cross-service loops risk N+1 calls; needs pagination/caching and load limits |
| **Integration event + local read model** | Consumer needs data for its own queries and tolerates lag | Idempotency, ordering, schema evolution, lag, and correction/deletion handling |
| **Transactional outbox + broker** | Owner must reliably publish a committed fact | Relays/consumers can still retry and see duplicates; requires deduplication |
| **CDC from owner's DB** | Controlled ETL/analytics, migrations, legacy integration | CDC describes storage mutations, not domain events or stable APIs automatically |
| **Read-only published view / data product** | Governed reporting/analytics needing an explicit SQL contract | Owner must manage versions, permissions, query load, and deprecation |

**Choose by business meaning, not protocol convenience.** Calling Inventory via API to reserve stock invokes authoritative decision-making. Displaying product titles on a list screen can use a local projection without calling Catalog per line if lag is acceptable. End-of-period financial reporting can use a dedicated pipeline and reconciliation rather than joining three live OLTP databases.

### Rules for Synchronous APIs

- Expose semantically meaningful operations like `ReserveStock`, not an arbitrary `PATCH /stock_quantity`.
- The owner validates permissions, idempotency, and invariants; callers never decide on the owner's behalf.
- Enforce timeouts/circuit breakers and distinguish **known failure** from **unknown outcome due to timeout**.
- Avoid holding a DB transaction open across network waits whenever cleaner boundaries exist.
- When one request fans out across services, design availability and fallbacks explicitly: a stale catalog label may be tolerable, whereas stale inventory availability must **never** confirm a stock reservation.

## 7. Derived Data May Be Copied, Never Promoted to a Second Source of Truth

Ordering often needs product names, images, and categories on order screens. Joining `catalog.product` directly on every request or calling Catalog per line increases coupling and latency.

Solution: Ordering keeps `catalog_product_projection` (a read model), fed by Catalog via integration events or a contracted sync mechanism.

~~~text
Catalog (authoritative):
  product_id = P-108
  display_name = "Wireless Headphones"
  catalog_version = 12
  sellable = true

Ordering local projection (derived):
  product_id = P-108
  display_name = "Wireless Headphones"
  catalog_version = 12
  sellable = true
  applied_at = 2026-11-22T01:00:00Z
~~~

On an admin screen, values in the projection may lag behind Catalog. Treat that as an **expected consistency property**, not a surprise bug.

When a user places an order, however, **pricing and sale eligibility must be finalized via authoritative workflows**, and actual stock holds are decided by Inventory. Never rely on `sellable = true` in a lagging projection to assert Inventory has reserved stock.

### Distinguish "Copies" from "Distinct Facts"

| Field in Ordering | Who Is Responsible? | Proper Update Mechanism |
| --- | --- | --- |
| `product_display_name_current` | Catalog; Ordering holds only a projection | Apply `ProductChanged`/refresh from Catalog |
| `agreed_product_name_at_order` | Ordering preserves what was presented/locked on the order | Written once per transaction snapshot and amendment policy |
| `agreed_unit_price_minor` | Ordering per accepted quote/terms | Never overwritten when Catalog changes prices |
| `stock_reserved` | Inventory confirms reservations; Ordering reflects outcome | Driven by reservation ID and owner-published status |
| `payment_confirmed` | Payment confirms from payment provider | Reflects only accepted confirmation events |

**Values that look identical can belong to entirely different facts.** Current name is a projection; locked name is transaction evidence. Recognizing this prevents corrupting historical records when master data changes.

## 8. Cross-Service References: Stable IDs Instead of Cross-DB Foreign Keys

Inside one relational database, FKs guarantee parent existence and enforce referential rules. Across two independent services' databases or shards, however, **a DBMS-enforced transactional FK spanning boundaries usually does not exist**.

Reference design shifts from "an FK to the other table" to **identifier contracts + validation at decision points + lifecycle state synchronization**.

### Identifiers and Namespaces

A `product_id` must be stable within its published scope. If IDs are unique only per tenant, references must carry `tenant_id + product_id`. If unique only per source system, add a namespace. Never use product names or emails as business FKs if they can change.

Ordering table example:

~~~sql
CREATE TABLE ordering.customer_order (
    tenant_id        UUID NOT NULL,
    order_id         UUID NOT NULL,
    customer_id      UUID NOT NULL,
    placed_at        TIMESTAMPTZ NOT NULL,
    status           VARCHAR(24) NOT NULL,
    PRIMARY KEY (tenant_id, order_id)
);

CREATE TABLE ordering.order_line (
    tenant_id         UUID NOT NULL,
    order_id          UUID NOT NULL,
    line_no           INTEGER NOT NULL CHECK (line_no > 0),
    product_id        UUID NOT NULL,
    agreed_unit_minor BIGINT NOT NULL CHECK (agreed_unit_minor >= 0),
    currency          CHAR(3) NOT NULL,
    quantity          NUMERIC(18, 3) NOT NULL CHECK (quantity > 0),
    product_name_at_order TEXT NOT NULL,
    PRIMARY KEY (tenant_id, order_id, line_no),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES ordering.customer_order(tenant_id, order_id)
);
~~~

- The **internal Ordering FK** between `order_line` and `customer_order` fits because both share an owner and DB transaction.
- `product_id` is an **external business reference** to Catalog, with no direct FK to `catalog.product`. Referential validity is checked through contracts and checkout rules.
- `product_name_at_order` and `agreed_unit_minor` are **locked attributes** of the order line, not projections kept synced with every Catalog price/name edit.

If Catalog retires a product, Ordering normally **must not delete historical order lines**. The owner needs events/statuses/tombstones so Ordering rejects new orders for that SKU while still displaying past orders per policy.

### When Strong Consistency Is Required

If a business invariant states "each seat can be sold only once", it is **insufficient** for Ordering to read an available-seat snapshot and insert a row on its own. Reservations must be accepted atomically by the seat owner using locks, unique constraints, or concurrency control where seat inventory lives.

If system-wide email uniqueness is required, one identity/registry owner must enforce it. Two services independently running `SELECT NOT EXISTS` against separate databases and inserting an email can both succeed concurrently.

## 9. Write-Flow Example: Ordering Does Not Directly Mutate Stock or Payment

~~~mermaid
sequenceDiagram
    participant U as Client
    participant O as Ordering
    participant I as Inventory
    participant P as Payment
    U->>O: PlaceOrder(request_id, lines)
    O->>O: Save Order PENDING with idempotency
    O->>I: ReserveStock(reservation_key, items)
    I->>I: Check stock and reserve at owner
    I-->>O: ReservationConfirmed(reservation_id)
    O->>P: RequestCapture(payment_key, amount)
    P-->>O: PENDING / request accepted
    Note over O,P: Timeout does not prove capture failed
    P-->>O: PaymentCaptured(ref, amount) once confirmed
    O->>O: Transition Order CONFIRMED per contract
~~~

Each service writes only the data it owns:

- Ordering writes Order state and `request_id` receipt.
- Inventory writes reservations and available stock with an idempotent `reservation_key`.
- Payment writes capture intent, provider outcomes, and reconciliation history with `payment_key`.

If reservation fails, Ordering can transition the Order to `REJECTED`. If Payment fails, Ordering can request releasing the reservation. If Payment **times out**, reconcile status with the provider before retrying or compensating—never issue a brand-new capture without an idempotency key assuming the prior attempt failed.

**Crucial point:** these steps do not share one ACID transaction. If business requirements cannot tolerate intermediate states, revisit source-of-truth boundaries, distributed transaction protocols, or reservation mechanics. Never slap the label "Saga" on a workflow and assume all invariants are magically guaranteed.

## 10. Publishing Integration Events: Business Contracts Differ from CDC Records

A domain owner can publish events with clear meaning for consumers.

Example when Catalog updates a product:

~~~json
{
  "event_id": "ff6c6a7a-7726-4dca-9a04-4ea32c28d219",
  "event_type": "CatalogProductChanged",
  "schema_version": 2,
  "tenant_id": "00000000-0000-4000-8000-000000000001",
  "product_id": "d3b37c4f-0e7c-4407-bdf8-6bc9c108c65a",
  "aggregate_version": 17,
  "occurred_at": "2026-11-20T10:05:00Z",
  "recorded_at": "2026-11-20T10:05:02Z",
  "payload": {
    "display_name": "Wireless Headphones",
    "category_code": "AUDIO",
    "sellable": true
  }
}
~~~

**Example contract:** this event is a **full-state update of Catalog's published fields** at aggregate version 17. `aggregate_version` increments per product stream, not as a schema version or global system sequence. If an event carried only a **delta** relative to the prior version, consumers would need different logic: never skip version 16 and blindly apply patch 17.

An integration event contract must document:

| Component | Rule |
| --- | --- |
| **Commit point** | When Catalog commits an accepted change. |
| **Identity** | `tenant_id + product_id` identifies the entity; `event_id` identifies the event. |
| **Version** | `schema_version` of the message, `aggregate_version` of the product. |
| **Data** | Only fields consumers are permitted to receive; no internal columns or secrets. |
| **Timestamps** | `occurred_at` and `recorded_at` have clear meanings. |
| **Duplicates / late arrivals** | Idempotent consumers with explicit out-of-order policies. |
| **Delete / unpublish** | Explicit events or tombstones, not merely going silent. |
| **Compatibility** | Old/new readers supported per policy; backed by contract tests. |

### Domain Events, Integration Events, and CDC Are Not Identical

- **Domain event:** meaningful occurrence inside Catalog, emitted per source business rules.
- **Integration event:** message Catalog intentionally publishes for external consumers; may merge, split, hide fields, and version independently.
- **CDC:** storage mutation such as an `UPDATE` on a Catalog row; typically exposes table/column structures and log positions without explaining business intent.

You can use CDC as a transport for an outbox or analytics pipeline, yet **never turn every column mutation into a public business contract**. If the owner changes physical tables, integration consumers should not have to rewrite code simply because one internal column was split into two.

## 11. Transactional Outbox: Keeping Owner Data and Publishing Intent Consistent

A common bug:

~~~text
1. UPDATE catalog.product
2. COMMIT
3. publish CatalogProductChanged
~~~

If the app crashes between steps 2 and 3, Catalog updated while consumers never find out. If it publishes before commit and the transaction rolls back, consumers act on an unaccepted change.

A **transactional outbox** closes this gap by writing business data and **a publishing intent record** in the same local transaction.

~~~sql
CREATE TABLE catalog.outbox_event (
    event_id           UUID PRIMARY KEY,
    tenant_id          UUID NOT NULL,
    aggregate_id       UUID NOT NULL,
    aggregate_version  BIGINT NOT NULL CHECK (aggregate_version > 0),
    event_type         VARCHAR(120) NOT NULL,
    schema_version     SMALLINT NOT NULL CHECK (schema_version > 0),
    payload            JSONB NOT NULL
                       CHECK (jsonb_typeof(payload) = 'object'),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at       TIMESTAMPTZ,
    UNIQUE (tenant_id, aggregate_id, aggregate_version, event_type)
);

CREATE INDEX ix_catalog_outbox_pending
    ON catalog.outbox_event (created_at, event_id)
    WHERE published_at IS NULL;
~~~

Logical execution flow:

~~~text
BEGIN TRANSACTION AT CATALOG
  - check permissions, product_version, and invariants
  - UPDATE catalog.product with expected_version
  - INSERT catalog.outbox_event with committed aggregate_version
COMMIT

OUTBOX RELAY / CDC
  - read committed events
  - send messages to broker, retrying on errors
  - record publish status per chosen protocol
~~~

An outbox ensures **publishing intent is not lost between commit and publish**, assuming storage/relays operate reliably. It **does not guarantee end-to-end exactly-once**: a relay can publish successfully and crash before updating `published_at`, causing redelivery.

Consumers must deduplicate; if a consumer triggers another side effect like calling a payment API, add idempotency to **that operation itself**. Never treat a committed outbox row as proof that target services applied it successfully.

## 12. Consumers Reading Derived Copies: Deduplication, Versions, and Consistency

Suppose Ordering maintains a Catalog projection for fast display.

~~~sql
CREATE TABLE ordering.catalog_product_projection (
    tenant_id          UUID NOT NULL,
    product_id         UUID NOT NULL,
    display_name       TEXT NOT NULL,
    category_code      VARCHAR(64) NOT NULL,
    sellable           BOOLEAN NOT NULL,
    catalog_version    BIGINT NOT NULL
                       CHECK (catalog_version > 0),
    projected_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, product_id)
);

CREATE TABLE ordering.processed_integration_event (
    consumer_name  VARCHAR(120) NOT NULL,
    event_id       UUID NOT NULL,
    processed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

A consumer processing full-state `CatalogProductChanged` events:

1. Start a transaction **in the Ordering database**.
2. Attempt to `INSERT (consumer_name, event_id)` into the receipt table. If already committed in a prior transaction, skip re-applying.
3. Read current `catalog_version`. If the incoming message has a higher version, upsert published fields; if lower, ignore the stale message.
4. If versions are **equal yet payloads differ**, record a conflict/investigate; never blindly do "last message wins".
5. Commit both receipt and projection **in the same transaction**. Only then acknowledge the message to the broker.

State-update SQL (run only after the receipt step proves this is new and the payload passed validation):

~~~sql
INSERT INTO ordering.catalog_product_projection (
    tenant_id, product_id, display_name,
    category_code, sellable, catalog_version
)
VALUES (
    :tenant_id, :product_id, :display_name,
    :category_code, :sellable, :catalog_version
)
ON CONFLICT (tenant_id, product_id)
DO UPDATE SET
    display_name = EXCLUDED.display_name,
    category_code = EXCLUDED.category_code,
    sellable = EXCLUDED.sellable,
    catalog_version = EXCLUDED.catalog_version,
    projected_at = now()
WHERE ordering.catalog_product_projection.catalog_version
      < EXCLUDED.catalog_version;
~~~

**Critical condition:** this works only when messages carry **complete full-state** for all projection fields. If Catalog emits **patches**, the consumer must process consecutive versions or fetch a source snapshot to fill gaps. Receiving patch v19 `{"category_code":"AUDIO"}` before v18 cannot infer the remaining fields.

### Freshness of Derived Copies

Projections can lag by seconds or minutes. Define:

- `projection_lag` SLA/SLO per use case.
- Catch-up/refresh procedures when a consumer stops for long periods or messages expire from the broker.
- How to recognize incomplete data when a product-creation event was never seen.
- At critical decisions like reservations or account locks, **never** treat a live cache as proof that the owner's invariants hold.
- When "read-your-writes" is required, use the owner command response, session/version tokens, or wait on the projection up to `aggregate_version` with a timeout.

### Do Not Resurrect Deleted Data with Stale Messages

If Catalog emits `ProductRetired` at version 20, the projection should retain a **tombstone / `sellable=false` and version 20** per policy so a late `CatalogProductChanged` v19 never flips the product back to sellable.

This does not mean keeping all personal data indefinitely: tombstones can retain only minimal IDs/versions while complying with retention and access policies.

## 13. Cross-Service Constraints and Transactions: Keep Decisions at the Right Owner

When a business flow touches multiple sources of truth, the question is no longer "how do we JOIN two tables" but "which invariants must hold immediately, and where?".

| Invariant / Decision | Owner | Core Mechanism |
| --- | --- | --- |
| A seat is never sold twice | SeatInventory | Unique/lock/reservation on `(show_id, seat_id)` in one consistency point |
| Never allocate beyond stock | Inventory | Atomic reservation/update checking remaining available stock |
| One order request never creates two orders | Ordering | Unique/idempotency key and order-creation transaction |
| Never capture twice for one request | Payment + provider | Stable idempotency key, persisted receipt/reconciliation |
| Order only `CONFIRMED` when prerequisites pass | Ordering | State machine driven by Inventory and Payment confirmations with reference IDs |
| Customers cannot register duplicate global identities | Customer Identity | Registry/uniqueness at the identity owner, not scattered local checks |

A `FOREIGN KEY` spanning two databases **is not a general-purpose coordination mechanism**. When strong cross-source consistency is required, consider:

- **Co-locating data needing atomicity under one owner/transaction** if current boundaries were split poorly.
- **Reservations / escrow** so an owner grants resource rights before consumers proceed.
- **Distributed transactions / 2PC** when participants support it and true atomic commit is mandatory; handle coordinator crashes, held locks, and isolation carefully.
- **Sagas** when the workflow can run local transactions with intermediate states, retries, and compensations.
- **Outbox/inbox** to reliably propagate committed facts across services.

### A Saga Is Not a Simultaneous Rollback

~~~mermaid
flowchart TD
    A["Order PENDING"] --> B["Inventory.reserve"]
    B --> C{"Stock reserved?"}
    C -->|"No"| X["Order REJECTED"]
    C -->|"Yes"| D["Payment.requestCapture"]
    D --> E{"Authoritative outcome?"}
    E -->|"Captured"| F["Order CONFIRMED"]
    E -->|"Failed"| G["Inventory.release exact reservation"]
    G --> H["Order FAILED"]
    E -->|"Timeout / unknown"| I["Order PENDING_RECONCILIATION"]
    I --> J["Reconcile provider and reservation"]
    J --> E
~~~

A succeeded capture **cannot be undone via `ROLLBACK` in Ordering**. If the business must return money, that is a brand-new compensating refund operation that can itself fail, arrive late, or require verification. Explicitly model pending, confirmed, and manual-intervention states.

In data modeling, this leads to dedicated tables/states for `reservation_id`, `payment_attempt_id`, `saga_id`, `idempotency_key`, and step histories. Never cram all cross-service evidence into a single `orders.status` string.

## 14. Evolving Schemas and Contracts Without Forcing Simultaneous Service Deployments

A clean boundary lets an owner change internal storage **without breaking consumers**.

### Three Changes to Distinguish

1. **Internal schema change:** Catalog splits `product.description` into multiple internal tables. Consumers remain unaffected as long as API/event contracts hold.
2. **Contract schema change:** Catalog adds `category_code` to `CatalogProductChanged.v2`. Check whether old readers tolerate the new field and how new readers handle v1 events lacking it.
3. **Semantic change:** previously `available` meant "listed in catalog", now it means "Inventory confirms in stock". This changes **authoritative source and business meaning**, not just a field name; design a new contract and owner for stock availability.

### Safe Versioning Workflow

- **Inventory consumers** and the contracts they rely on; never assume "other teams probably don't use this column".
- Specify `event_type`, `schema_version`, required/optional fields, enums, units, timestamps, and semantic descriptions.
- Deploy **dual-capable readers** or valid adapters/upcasters before writers switch, when architecture permits.
- For breaking changes, run **v2 contracts in parallel** during transition and ensure consumers never process two representations of the same occurrence as two separate business events.
- Run **consumer-driven contract tests** and historical replays. Never backfill missing historical values with misleading defaults.
- Publish deprecation schedules and monitor v1 usage; never delete v1 decoders while historical events still need replay.

**Never equate API version with database schema version.** API v2 can run on a redesigned storage schema without altering emitted events. Conversely, changing an analytical KPI definition may require a new metric/projection version even if JSON APIs never changed.

## 15. Splitting a Shared Table Step by Step Instead of a "Big Bang"

Suppose multiple services currently share `public.product` and the team wants to establish Catalog as the formal owner.

### Phase A — Inventory Dependencies

1. Find every `SELECT/INSERT/UPDATE/DELETE` path touching the table—including background jobs, reports, stored procedures, triggers, exports, tests, and support tools.
2. Identify the **truth owner** of each column group. `product_name` belongs to Catalog, while `stock_quantity` belongs to Inventory; one shared table often mixes **two distinct domains**.
3. Map keys and FKs, cross-domain JOINs, required consistency, DB accounts, and write frequencies.
4. Flag fields used to finalize transactions; never replace them hastily with async caches if doing so breaks invariants.

### Phase B — Design Targets and Contracts

1. Create target schemas/tables per owner with stable business keys.
2. Catalog publishes query APIs and events for committed changes; Inventory publishes reservation commands/results.
3. Design projections for read-heavy consumers; retain lineage/`source_version` and tombstones.
4. Define how legacy changes are ingested, deduplicated, and resolved on backfill conflicts.

### Phase C — Shift Write Paths One by One

- **Establish one write owner at a time**, avoiding parallel writes to the same column from two sources.
- Use facades/adapters or route requests to the new owner during transition.
- If syncing from the legacy table, use outbox/CDC with checkpoints and **commit-ordered cursors**. Never use pre-commit sequence IDs as reliable watermarks.
- Ensure initial copies and change streams do not drop transactions committed during handoff.

### Phase D — Shift Read Paths

- Build new projections/read APIs alongside legacy read paths.
- Verify business key counts, record statuses, versions, soft-delete cases, permissions, tenant isolation, and lag.
- Migrate consumers one by one to new contracts, monitoring errors, latency, and drift with clear rollback plans.
- Only after zero legitimate consumers rely on the legacy table should you **revoke DB privileges** and close the migration.

~~~mermaid
flowchart LR
    LEG[("Shared legacy product table")] --> COPY["Backfill + commit-ordered CDC"]
    COPY --> CAT[("Catalog schema: new owner")]
    CAT --> EVT["API / Outbox / Integration event"]
    EVT --> PROJ[("Ordering local projection")]
    PROJ --> CUT["Cut over Ordering reads"]
    LEG -. "Monitor drift until done" .-> CUT
~~~

**Avoid uncontrolled dual writes.** If an app issues two independent writes to Legacy and Catalog and counts success when only one commits, two diverging truths emerge. If dual-write is unavoidable, define strict protocols for owner, idempotency, failure recovery, and commit rules; a safer design is **one authoritative write path** plus derived synchronization.

### Migration Trap: Column-Level Mixed Ownership

Sometimes `public.product.stock_quantity` was really Inventory's data while Catalog owned name/category columns. Moving the whole table to Catalog and letting Catalog govern stock destroys Inventory's invariants. Separate **facts and owners by meaning**, even when doing so reshapes physical tables significantly.

## 16. Observing Data Correctness: Do Not Measure API Latency Alone

A boundary design can run fast while corrupting data if consumers drop events or two services overwrite each other.

| Metric / Check | Question | Action When Wrong |
| --- | --- | --- |
| **Unauthorized cross-schema writes** | Which runtime attempted to write an unowned table? | Block via permissions and investigate caller |
| **Catalog projection lag** | How far behind is the consumer, and at which product version? | Retry, backfill, compare sources, show staleness if needed |
| **Event dedup rate** | How many messages were redelivered/deduplicated? | Verify idempotency, inspect relay |
| **Out-of-order / gap count** | Did v18 arrive before v17, or is a patch missing? | Hold/refresh snapshot; never apply broken patches |
| **Source–projection drift** | Do Catalog's published fields match the projection at matching checkpoints? | Reconcile and rebuild affected items |
| **Orphan external references** | Do `OrderLine`s point to unknown products? | Investigate missing/deleted/backfill; preserve historical orders |
| **Saga pending age** | Are orders stuck awaiting reconciliation, release, or refund? | Workflow recovery and alerting |
| **Idempotency conflicts** | Same business request ID with different payloads? | Reject/investigate; never silently take last write |
| **Schema contract breakage** | Can older readers handle new messages per policy? | Contract tests, canaries, rollback/dual publish |
| **Data access audit** | Who queried sensitive data outside allowed scope? | Audit permissions, revoke, respond to incident |
| **Cross-service synchronous depth** | How many owners does one API request chain synchronously? | Proper semantic batching/caching; reduce fan-out |
| **Consumer freshness SLO** | Are UI/report expectations met? | Publish lag, adjust architecture or SLO |

### Failure Drills to Rehearse

- Catalog commits a rename and the relay crashes before publishing: is the outbox event retried and can consumers rebuild?
- Ordering receives `CatalogProductChanged v19` before v18: does full-state allow skipping v18? If patch-based, how does it recover?
- Inventory API times out even though reservation succeeded: which key retries and which source confirms?
- A customer is soft-deleted while CRM projections still show their name: how does derived-data cleanup run?
- Two workers process the same `event_id` concurrently: do receipt and projection share one transaction?
- A team deploys a Catalog enum migration: do legacy consumers fail parsing or misinterpret statuses?

**Measuring HTTP 200 success rate is not enough.** A system can return 200 consistently while displaying stale data, double-counting revenue, or violating stock invariants.

## 17. Authorization, Tenant Isolation, and Cross-Boundary Data Lifecycle

Ownership carries responsibility for protecting data:

1. **Least privilege:** runtimes access only their own data and granted read contracts. Admin/migration accounts stay separate from runtime roles.
2. **Tenant scope:** IDs, queries, events, and projections must carry tenant keys whenever multi-tenant; enforce checks at both API and DB layers. Shared schemas never excuse skipping cross-tenant checks.
3. **PII minimization:** do not broadcast emails, addresses, or ID numbers in every integration event just so consumers "have them handy". Transmit sensitive data only when justified and authorized.
4. **Retention / erasure:** owners run source workflows, while consumers implement erasure/anonymization on derived copies per contract. `CustomerErasureRequested` is not `ErasureCompleted` until downstream finishes.
5. **Hidden copies:** read models, search indexes, caches, exports, analytics, backups, and message archives can retain data after master records change or delete.
6. **Data lineage:** know which field came from which owner, under which event/schema version, and how to verify correctness in disputes.
7. **Residency and auditing:** if data residency restricts locations, check consumers, brokers, and backups; debug/query access counts as data access too.

### Never Use Immutable Events as Unlimited PII Stores

If events are retained long-term for replay, use **opaque IDs**, references to a governed identity vault, policy-compliant encryption, and minimal sensitive payloads. Retaining history does not exempt you from valid erasure/anonymization mandates; some data-minimization techniques limit replay capability and must be documented upfront.

**Business facts do not require full detailed PII.** Ordering may store `customer_id` and finalized delivery details under contract obligations without copying the entire Customer Identity profile into every event.

## 18. Comparing Relational, Document, Graph, and Analytical Approaches

Decouple ownership from storage engine; the same business boundary works across multiple technologies.

| Model / Engine | How Ownership Is Enforced | Integration Pitfalls |
| --- | --- | --- |
| **Relational** | Separate schemas/DBs per owner; internal FKs, uniques, transactions; published views/APIs | Direct cross-domain JOINs/FKs turn internal schemas into implicit contracts |
| **Document** | Service owns aggregate collections/documents; consumers keep tailored projections | Embedding another owner's document and editing locally causes divergence; missing shard keys cause scatter-gather |
| **Graph** | Services own nodes/edges in their domain; global graph derived via contracts | Cross-owner traversals, unstable IDs, stale edges after deletes/updates |
| **Event store** | Owner appends domain facts, publishes versioned integration events | Consumers mistake internal events for external contracts or trigger side effects on replay |
| **Analytics / warehouse** | Published data products with grain, metrics, lineage, and owners; contracted ingestion | Treating CDC as domain events, joining facts at mismatched grains, mismatched watermarks |

A data warehouse may read from multiple owners for analytics, **yet must never silently edit source values and push them back into OLTP** without owner commands/approvals. A `dim_customer` table serves analytics without holding authority to alter profiles in Customer Identity.

A **global graph** built to detect fraud relationships can combine nodes/edges from several services. The graph owner owns inference logic and freshness, while transaction approval and customer updates remain with the source owners.

## 19. Decision Matrix and Architecture Decision Record

When a new requirement arrives, pick the integration pattern with concrete questions:

| Question | If the Answer Is… | Pattern to Consider |
| --- | --- | --- |
| Need an immediate owner decision to protect invariants? | Yes, e.g., reserving seats or checking credit limits | Synchronous command/API to owner with concurrency & idempotency |
| Need display data with bounded lag tolerance? | Yes, e.g., product titles/categories | Integration event + local projection/cache |
| Need cross-domain reporting and multi-year history? | Yes, without real-time OLTP requirements | Analytical pipeline / data product with grain contracts & reconciliation |
| Does the consumer truly need the owner's physical columns? | No, only business semantics | Published API/event contract; no raw table access |
| Must read directly during a transition window? | Yes, time-boxed and owner-controlled | Read-only published view, least privilege, scheduled retirement |
| Must mutate multiple sources in one business flow? | Yes, and cannot co-locate | Saga/2PC per atomicity needs, verifying compensations |
| Can source records be deleted or retired? | Yes | Lifecycle events/tombstones and erasure propagation |

### Abbreviated Sample ADR

**Context:** Ordering directly JOINs `catalog.product` to display product names. Catalog needs to refactor its schema and migrate engines; Ordering reads suffer high p95 latency during Catalog load spikes.

**Decision:** Catalog owns product names, categories, and publication status; Ordering consumes full-state `CatalogProductChanged` events carrying `aggregate_version` and maintains a read projection. Ordering separately stores **locked names/prices per order line**. Checkout continues validating transaction rules at appropriate owners without treating the projection as an inventory hold.

**Trade-offs:** accepts bounded projection lag under an SLO plus backfill mechanics; gains zero cross-schema JOINs and independent schema migrations. Requires outbox, inbox deduplication, latest-version checks, tombstones, and reconciliation.

**Rejected alternatives:** granting permanent `SELECT` on Catalog tables; running unversioned cron copies of Catalog; letting Ordering update `product.status` directly to "reflect sellability".

**Re-evaluation triggers:** projection lag breaches SLO, event volume overwhelms pipelines, or screens genuinely demand millisecond-fresh reads intolerant of staleness. Re-evaluate from workload data and SLOs, not tech preferences.

## 20. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Multiple services `UPDATE` the same table | Bypassed invariants, unclear source of truth | Single write owner; others use commands/contracts |
| Splitting schemas while sharing a superuser account | Boundaries exist only on diagrams | Separate runtime credentials/privileges; block cross-schema writes |
| Having `SELECT` access and treating tables as stable APIs | Consumers couple to internal schemas and values | Published query/event contracts, tests, deprecation |
| Using caches to confirm stock holds | Inventory may have changed concurrently | Decide at Inventory owner via atomic reservations |
| Updating old order names/prices from current Catalog | Mutates finalized historical records | Separate transaction snapshots from current master projections |
| Sharing `payment_status` column names edited by multiple services | Unclear who confirmed real funds | Payment holds authority; Ordering reflects source-ID-backed outcomes |
| Treating CDC `UPDATE`s as complete business events | Loses intent, actor, commit point, constraints | Integration event contracts with explicit semantics |
| Updating projections then writing receipts in another tx | Retries double-apply updates | Inbox/dedup and projection share one transaction |
| Applying old events with "last message wins" | State regresses to older versions | Version guards, gap policies, conflict detection |
| Publishing before commit or skipping outbox | Emits false events or loses notifications | Write outbox in same source commit; relay post-commit |
| Deleting customer master and cascading deletes to orders/payments | Destroys financial records and reconciliation trails | Per-owner lifecycles, separate retention, controlled pseudonymization |
| Dual-writing legacy and new DBs while ignoring partial errors | Two sources of truth diverge | Single authoritative write path, CDC/outbox, clear cutover milestones |
| Splitting microservices solely because tables were split | Unnecessary distributed transactions and latency | Bounded contexts/ownership first; physical splits later |
| Dashboards joining live production databases directly | Tight coupling, OLTP load, inconsistent snapshots | Data products / analytical marts with lineage and watermarks |
| Thinking "eventual consistency" means skipping verification | Projections drop events unnoticed | Lag monitoring, reconciliation, replay, alerts, clear owners |

## 21. Practice Exercise: Splitting a Shared Table in a Ticketing Platform

**Context:** A ticketing platform has a shared table `public.show_booking` storing event name, seat list, order status, payment status, customer email, and total amount. Catalog, Booking, SeatInventory, Payment, Customer Support, and Analytics all access it directly. When concerts go on sale, two bookings can race for the same seat; Payment callbacks arrive late or duplicated; organizers rename shows; customers request email updates or policy-compliant profile erasure.

### Design Requirements

1. **Build an ownership matrix:** assign owners for show name/status, seat availability, booking lines, confirmed capture/refunds, customer identity, and financial KPIs.
2. **Distinguish facts from copies:** who owns current show name? Who owns the locked show name printed on a ticket? What policies govern current email vs. transaction contact email?
3. **Design keys:** specify `tenant_id`, `show_id`, `seat_id`, `booking_id`, and `payment_attempt_id`; uniqueness scopes and ID reuse rules.
4. **Seat invariant:** design atomic seat locking in SeatInventory using unique constraints, locks, or reservations; explain why two sharded Booking tables cannot protect one seat alone.
5. **Cross-service references:** Booking holds `show_id` and `seat_reservation_id` as external references; which data uses local FKs vs. contracts/lifecycle events?
6. **Screen reads:** choose synchronous API vs. local projection for show titles, seat maps, and payment status. How do users/systems tell when data is stale?
7. **Write flow:** trace Booking `PENDING → SeatReserved → PaymentCaptured → CONFIRMED`; explain handling of timeouts/unknown outcomes and compensations when seat hold or capture fails.
8. **Event contract:** draft `ShowDetailsChanged.v1` with `event_id`, `schema_version`, `aggregate_version`, `occurred_at`, and payload; point out what must not be published.
9. **Outbox/inbox:** propose tables, keys, and transactions to update a show and emit events; show how consumers handle duplicates and out-of-order arrivals.
10. **Splitting the shared table:** plan backfill, CDC tail catch-up, single write owner, shadow reads, reconciliation, cutover, and privilege revocation; explain why two independent write paths are dangerous.
11. **Permissions:** design DB roles so Booking's runtime cannot `UPDATE catalog.show` or `payment.capture`; how do debug and migration roles differ?
12. **Retention:** a customer requests profile deletion while Booking and Payment have legal obligations to keep financial records; how do you separate PII and derived copies across events, caches, and backups?
13. **Verification SQL:** write queries verifying non-duplicated grain, counting orphan external references in read models, and detecting projections lagging behind source versions at a reconciliation checkpoint.
14. **SLOs / monitoring:** list at least eight metrics covering projection lag, retries, conflicts, unauthorized access, pending sagas, data drift, contract errors, and latency.
15. **ADR:** write a short decision record covering owners, contracts, storage models, consistency, rejected alternatives, migration path, and re-evaluation triggers.

### Self-Assessment Rubric

| Criterion | Design Meets Standard When |
| --- | --- |
| **Clear owner** | Every business fact has an authoritative source and defined commit point. |
| **Write rights** | Runtimes cannot directly mutate another owner's data. |
| **Keys / relations** | Local PK/FKs and external references have explicit scopes and namespaces. |
| **Invariants** | Seats are never double-sold; payment requests are never mistaken for captures. |
| **Integration paths** | APIs/events/outbox/read models match consistency needs with retries and dedup. |
| **History** | Finalized records are never overwritten by current master edits; lifecycles are clear. |
| **Migration** | Backfill + catch-up + cutover are reconciled without dual independent write owners. |
| **Operations** | Drift, lag, and contract errors are monitored with recovery paths for missing data. |
| **Privacy** | PII, retention, deletion/tombstones, backups, and per-tenant access are controlled. |

**Conclusion:** data ownership is deciding **who holds authority to confirm truth and protect its invariants**, not merely schema names or database locations. Services must never treat each other's physical tables as unrestricted public interfaces. Define business keys, owners, commit points, and contracts; allow only owners to mutate canonical data; use APIs for authoritative decisions, events/outboxes for committed facts, projections for tailored reads, and reconciliation workflows to manage lag and change. From those boundaries, relational, document, graph, and analytical models can evolve independently while keeping data provenance and correctness verifiable.
