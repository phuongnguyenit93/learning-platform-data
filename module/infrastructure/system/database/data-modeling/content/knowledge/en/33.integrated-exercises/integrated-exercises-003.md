# Identifying Keys, Relationships, Attributes, and Invariants for Each Component

Data design begins with deceptively simple questions: **“What does one row represent?”**, **“What makes this object unique?”**, **“Which objects can relate to one another?”**, and **“What must never be allowed to happen?”** Missing even one answer can let a system attach an order to the wrong customer, double-count money on a JOIN, rewrite historical prices when a product changes, refund more than was captured, or ship more units than ordered.

This **integrated exercise** in the **DATABASE_DATA_MODELING** module focuses on translating business requirements into a **verifiable relational model**, then comparing choices against document, graph, and analytical models. Each component requires learners to define **grain, candidate/primary keys, foreign keys, relationships and cardinalities, attributes, constraints, and cross-row invariants**; followed by verification using PostgreSQL SQL and counterexamples. This is a **self-contained exercise** that does not assume other lessons are open.

## 1. Objectives and how to complete the integrated exercise

After this lesson, learners can:

1. Decompose a business description into **entities, events, and snapshot values** without conflating them.
2. State the **single-row grain** before choosing keys or creating tables.
3. Distinguish **business keys, candidate keys, primary keys, surrogate keys, foreign keys**, and per-tenant uniqueness scopes.
4. Clearly specify **1–N, N–M, optional/mandatory relationships** and resolve N–M relationships using associative entities with their own attributes.
5. Classify attributes as **required/optional, time-varying, transaction-time snapshot, derived**, and data requiring history.
6. Translate invariants into **PRIMARY KEY, UNIQUE, FOREIGN KEY, CHECK**, while recognizing invariants that require **transactions, locking, event/idempotency handling, or reconciliation tests**.
7. Test the design using **fixtures featuring cross-tenant ID collisions, partial payments, multiple refunds, split shipments, and historical attribute changes**.
8. Evaluate when to use relational, document, or graph models; assess the impact of indexes, partitioning, and schema changes.

**Working rule:** for each component, first answer *Grain? Key? Relation? Attribute? Invariant?* on your own before checking the hints. The SQL sections are **examples for learners to run in an empty practice PostgreSQL schema**; this lesson does not claim the statements were executed on a production database.

## 2. Running case study: a multi-tenant B2B ordering platform

A hypothetical platform named **OrderHub** serves multiple businesses (**tenants**). Each business manages its own customers and product catalog. Customers place orders with multiple lines, payments can be split across attempts, refunds can be partial, and goods can be delivered across multiple shipments.

The requirements below serve as the **exercise's business contract**, not universal rules for every e-commerce system:

| Code | Business requirement |
| --- | --- |
| R01 | Each **tenant** has a stable internal identifier and a distinct platform-wide display code. |
| R02 | **customer_id**, **product_id**, **order_id**, and child IDs may **collide across two tenants** but never within the same tenant. |
| R03 | Each customer has an **external_customer_code** unique within the tenant; email or display name is **not used as a key** since it can change and is not guaranteed unique. |
| R04 | Each product has a **SKU unique within the tenant**. Current list price may change; finalized orders must preserve the **unit price at placement time**. |
| R05 | An order belongs to exactly **one tenant and one customer** of that tenant; a customer may have many orders. |
| R06 | An order can be **DRAFT**, **PLACED**, or **CANCELLED**. Only **PLACED/CANCELLED** orders that were finalized have a **placed_at** timestamp. A placed order must have at least one line. |
| R07 | An order line has a **line_no unique within the order**, references one product in the same tenant, and has positive integer quantity, locked unit price, and locked discount. |
| R08 | Payment can span multiple **payment attempts**; each attempt belongs to one order, has a tenant-unique idempotency key, and a positive amount. Only **CAPTURED** attempts count as collected cash. |
| R09 | A CAPTURED attempt can have multiple **refunds**, each with a status. Total **SETTLED** refunds on an attempt cannot exceed that attempt's CAPTURED amount. |
| R10 | An order can be delivered via multiple **shipments**. Each shipment has multiple lines; total **dispatched** quantity per order line cannot exceed ordered quantity. |
| R11 | Customer name/address may change. Finalized orders store a **snapshot of shipping details** that does not automatically change with the customer's current profile. |
| R12 | Reports must preserve monetary amounts and quantities across JOINs; orders may be classified by **customer tier effective at placement time** when history is added. |
| R13 | Examples use **VND** only, stored in integer VND units; exchange rates, taxes, fees, or line-level refunds are not modeled. |

Some rules are left unspecified, such as whether an order can be paid before placement or edited after dispatch. **Do not assume unstated requirements exist.** In this lesson we choose explicit conventions to illustrate and clearly flag which rules require confirmation before production rollout.

### 2.1. Challenging edge cases intentionally built into the exercise

- Both tenant 1 and tenant 2 have **customer_id = 10**, **product_id = 100**, and **order_id = 500**.
- Tenant 1's order 500 has **two order lines** and **two successful payment captures**.
- One payment attempt receives **two separate refunds**, both referencing the same attempt.
- Orders can be delivered **partially**, so one order can link to multiple shipments.
- A customer upgrades from **BRONZE** to **GOLD**; historical reports must pick the tier **at order placement time**, not the current tier.

These facts create realistic **negative cases**: JOINs missing `tenant_id`, direct JOINs between two 1–N relationships, confusing a refund with payment status, or joining historical dimensions without time intervals.

## 3. Step 1 — From business nouns to entities and grain

Not every noun becomes a table. **Shipping address at placement** can be a snapshot value on the order; **order total** is a derived calculation; **refund event**, however, has its own identity and lifecycle, so it needs its own entity.

| Component | Proposed entity/dataset | One row represents | Why not merge arbitrarily into another table? |
| --- | --- | --- | --- |
| Business | **tenants** | One business using the platform | Acts as the identity and data isolation boundary |
| Customer | **customers** | One customer within one tenant | One customer places many orders; attributes change |
| Product | **products** | One SKU/product within one tenant | Current price/name is not an order-line snapshot |
| Order | **orders** | One order belonging to one tenant | Has status, owning customer, and placement timestamp |
| Order line | **order_lines** | One line added to an order | One order holds multiple products/quantities with locked prices |
| Payment | **payment_attempts** | One attempt to collect funds for an order | Has retries, idempotency, and independent lifecycle |
| Refund | **refunds** | One refund request/event against an attempt | Multiple refunds can target a single capture |
| Shipment | **shipments** | One delivery parcel/shipment for an order | One order can have multiple shipments, each with status |
| Shipment line | **shipment_lines** | Quantity of an order line allocated to a shipment | Represents an M:N link with quantity |
| Tier history | **customer_tier_history** | One customer tier version effective over a time range | Supports historical AS-OF order classification |

### 3.1. Grain is a stronger contract than table names

Example:

~~~text
orders:
  one row = one order within one tenant
  (tenant_id, order_id) -> customer_id, order_number, status, placed_at...

order_lines:
  one row = one line of one order
  (tenant_id, order_id, line_no) -> product_id, quantity, unit_price_vnd...

refunds:
  one row = one refund with its own refund_id
  (tenant_id, refund_id) -> payment_attempt_id, amount_vnd, status...

shipment_lines:
  one row = one order line allocated to one shipment
  (tenant_id, shipment_id, line_no)
    -> order_id, shipped_qty...
~~~

Arrows here denote **functional dependency determined by keys**, not chronological data flow.

**Essay check:** if you cannot explain whether one row of **payment_attempts** means *one collection attempt*, *one capture transaction*, or *an order's total paid*, do not pick keys or write `SUM` yet.

### 3.2. Entities, attributes, snapshots, and derived measures

| Data item | Design choice | Reason |
| --- | --- | --- |
| Current customer email | Customer attribute, nullable/mutable | Too unstable to be a PK |
| Shipping address at placement | Snapshot on order | Preserves transaction truth even if customer edits address |
| Current list price | Product attribute | Used for quoting new orders |
| Unit price on order line | Immutable snapshot at placement | Used for historical valuation |
| Line amount | Derived: quantity × unit price − discount | Avoids two conflicting sources of truth for line total |
| Order total | Derived from eligible lines | Avoid adding a writable column without sync policy |
| Total captured | Derived from CAPTURED payments | Multiple attempts and retries |
| Total refunded | Derived from SETTLED refunds | Multiple refunds can belong to one capture |
| Shipped quantity | Derived from shipment_lines of dispatched shipments | Split across shipments with state transitions |
| Tier at placement | AS-OF from history table or locked snapshot | Never use current tier for historical analysis |

There is no single “universally right” table split for every system. Choices depend on the **grain, constraints, and query questions** required by the contract, yet those conditions must always be expressed in testable terms.

## 4. Step 2 — Identifying keys and uniqueness scopes

### 4.1. Natural keys and surrogate keys

- **Candidate key:** minimal set of columns sufficient to distinguish rows under business invariants.
- **Primary key:** the candidate key chosen as the primary identifier in the schema.
- **Surrogate key:** system-issued technical ID such as `customer_id`; only sound when issuance/uniqueness policies are enforced.
- **Business key:** externally meaningful code such as SKU or `order_number`; may change depending on contract.
- **Foreign key:** reference from a child key to the matching unique key of a parent, protecting existence and relationship scope.

### 4.2. Proposed key matrix

| Table | PK | Additional business/UNIQUE keys | Critical FKs |
| --- | --- | --- | --- |
| tenants | tenant_id | tenant_code | — |
| customers | (tenant_id, customer_id) | (tenant_id, external_customer_code) | tenant_id → tenants |
| products | (tenant_id, product_id) | (tenant_id, sku) | tenant_id → tenants |
| orders | (tenant_id, order_id) | (tenant_id, order_number) | (tenant_id, customer_id) → customers |
| order_lines | (tenant_id, order_id, line_no) | — | (tenant_id, order_id) → orders; (tenant_id, product_id) → products |
| payment_attempts | (tenant_id, attempt_id) | (tenant_id, idempotency_key); (tenant_id, provider, provider_ref) when present | (tenant_id, order_id) → orders |
| refunds | (tenant_id, refund_id) | Source-dependent: provider_ref/idempotency | (tenant_id, attempt_id) → payment_attempts |
| shipments | (tenant_id, shipment_id) | (tenant_id, shipment_code) | (tenant_id, order_id) → orders |
| shipment_lines | (tenant_id, shipment_id, line_no) | — | Shipment matching order and order_line in same tenant/order |
| customer_tier_history | customer_tier_sk | Non-overlapping over (tenant, customer, valid-time) | (tenant_id, customer_id) → customers |

**Why do composite FKs need `tenant_id`?** If `customers` has key `(tenant_id, customer_id)`, an `orders` row referencing only `customer_id = 10` cannot tell tenant 1's customer apart from tenant 2's. Including `tenant_id` in the FK makes cross-tenant linking impossible via any valid insert.

### 4.3. Sufficient but non-redundant keys

The key **(tenant_id, order_id, line_no)** uniquely identifies an order line because an order has distinct `line_no` values. Once a line has that key, adding `product_id` to the PK does not make it “safer”; it complicates referencing FKs and falsely suggests `product_id` is part of line identity.

Conversely, placing **`UNIQUE(product_id)`** on `products` fails when the same `product_id` is reused across two tenants. Placing a global **`UNIQUE(order_number)`** also violates R02 if order numbers only need to be unique per tenant.

### 4.4. Keys you should not pick arbitrarily

Do not use **email** as a customer PK, because customers change emails, share emails, or omit them. Do not use **product price** as part of a key because prices change over time. Do not use **`(tenant_id, order_id, product_id)`** as the order line PK if the business allows **the same product on two lines** under different discounts; `line_no` is the stable line identifier.

Some systems use global IDs like UUID/ULID. Even with global IDs, **same-tenant constraints** are still needed on relationships if tenant isolation is required; a global identifier does not by itself enforce ownership or authorization.

## 5. Step 3 — Stating relationships and multiplicities before choosing JOINs

### 5.1. Conceptual entity diagram

~~~mermaid
erDiagram
    TENANT ||--o{ CUSTOMER : owns
    TENANT ||--o{ PRODUCT : sells
    TENANT ||--o{ ORDER : hosts
    CUSTOMER ||--o{ ORDER : places
    ORDER ||--o{ ORDER_LINE : contains
    PRODUCT ||--o{ ORDER_LINE : referenced_by
    ORDER ||--o{ PAYMENT_ATTEMPT : has
    PAYMENT_ATTEMPT ||--o{ REFUND : refunded_by
    ORDER ||--o{ SHIPMENT : ships_in
    SHIPMENT ||--o{ SHIPMENT_LINE : includes
    ORDER_LINE ||--o{ SHIPMENT_LINE : allocated_to
    CUSTOMER ||--o{ CUSTOMER_TIER_HISTORY : classified_as
    TENANT {
        bigint tenant_id PK
        text tenant_code UK
    }
    CUSTOMER {
        bigint tenant_id PK
        bigint customer_id PK
        text external_customer_code UK
    }
    PRODUCT {
        bigint tenant_id PK
        bigint product_id PK
        text sku UK
    }
    ORDER {
        bigint tenant_id PK
        bigint order_id PK
        bigint customer_id FK
        text order_number UK
    }
    ORDER_LINE {
        bigint tenant_id PK
        bigint order_id PK
        integer line_no PK
        bigint product_id FK
    }
    PAYMENT_ATTEMPT {
        bigint tenant_id PK
        bigint attempt_id PK
        bigint order_id FK
    }
    REFUND {
        bigint tenant_id PK
        bigint refund_id PK
        bigint attempt_id FK
    }
    SHIPMENT {
        bigint tenant_id PK
        bigint shipment_id PK
        bigint order_id FK
    }
    SHIPMENT_LINE {
        bigint tenant_id PK
        bigint shipment_id PK
        integer line_no PK
        bigint order_id FK
    }
    CUSTOMER_TIER_HISTORY {
        bigint customer_tier_sk PK
        bigint tenant_id FK
        bigint customer_id FK
    }
~~~

The diagram illustrates **structurally permitted relationships**. The **o{** notation on `order_lines` permits DRAFT orders to have zero lines; the invariant **PLACED orders must have at least one line** cannot be fully expressed via static cardinality notation alone. Likewise, the diagram does not express total refund or total `shipped_qty` caps.

### 5.2. Reading direction and optionality accurately

| Relationship | Parent side | Child side | Additional constraints |
| --- | --- | --- | --- |
| Tenant → Customer | One tenant has 0..N customers | Each customer belongs to 1 tenant | Cannot reference another tenant |
| Customer → Order | One customer has 0..N orders | Each order has 1 customer | Customer cannot be deleted leaving orphan orders |
| Order → OrderLine | DRAFT order has 0..N lines; PLACED at least 1 | One line belongs to 1 order | `line_no` unique within order |
| Product → OrderLine | One product is ordered 0..N times | One line references 1 product | Unit price stays a placement-time snapshot |
| Order → PaymentAttempt | One order has 0..N attempts | One attempt belongs to 1 order | Only CAPTURED counts as collected cash |
| PaymentAttempt → Refund | One attempt has 0..N refunds | One refund belongs to 1 attempt | Total SETTLED cannot exceed CAPTURED |
| Order → Shipment | One order has 0..N shipments | One shipment belongs to 1 order | Delivery workflow governed by business rules |
| Shipment ↔ OrderLine | N–M via `shipment_lines` | One allocation links 1 shipment and 1 order line | Shipment and line must share order/tenant |
| Customer → TierHistory | One customer has 0..N history versions | One version belongs to 1 customer | Non-overlapping valid-time if one tier at any moment |

### 5.3. Resolving N–M relationships that carry attributes

One shipment can contain multiple order lines; one order line can be shipped across multiple shipments. If modeled directly as:

~~~text
shipment.order_line_ids = [1, 2, 3]
order_line.shipment_ids = [700, 701]
~~~

protecting partial shipment quantities and keeping both lists consistent becomes difficult. The associative entity:

~~~text
shipment_lines(
    tenant_id,
    shipment_id,
    order_id,
    line_no,
    shipped_qty
)
~~~

not only connects both sides, but also stores the **relationship attribute: `shipped_qty`**. Never put `shipped_qty` on `product` or `order_line` if a line can be delivered in multiple shipments.

### 5.4. JOINs do not decide result grain on the designer's behalf

If an order has two lines and two payment attempts, joining them on `order_id` yields **four pairs**, not two order lines or two payments. Counting or summing after a JOIN must be explained at the **grain of the pairs**, or each side must be aggregated to the order grain before joining. We will verify this with concrete numbers in Section 11.

## 6. Step 4 — Classifying attributes, timestamps, and derived data

### 6.1. Current data versus snapshots

| Object | Current attributes | Snapshots to preserve on transaction | Consequence if modeled poorly |
| --- | --- | --- | --- |
| Customer | `display_name`, email, default address | `shipping_name`, `shipping_address` at placement | Editing customer alters historical delivery records |
| Product | `sku`, `product_name`, `list_price_vnd` | `product_id`, `unit_price_vnd` on line | Raising product price inflates past sales |
| Order | current `status`, cancellation metadata | `placed_at`, locked line prices/discounts | Cannot distinguish drafts from placed orders |
| Payment | attempt status and provider ID | Identified CAPTURED/reversal events | Retries mistaken for a second collection |
| Customer tier | Current tier | Tier version at `placed_at` or effective history | Prior-period reports shift into new tier |

**Storing snapshot data is not always bad denormalization.** It carries independent business meaning: **the customer's current address** and **the confirmed delivery address for an order** are two distinct facts.

### 6.2. Attribute domains and meaningful NULLs

- **`quantity > 0`**: integer with CHECK.
- **`unit_price_vnd >= 0`**, **`discount_vnd >= 0`**: price can be 0 for promotional freebies.
- **`discount_vnd <= quantity × unit_price_vnd`**: prevents negative line totals in examples.
- **`placed_at = NULL`** for DRAFT: not yet finalized, distinct from a missing timestamp due to import bugs.
- **`provider_ref = NULL`** before gateway returns a reference: distinct from empty string or fabricated values.
- **`currency_code = VND`**: lesson assumption; supporting multiple currencies later requires changing the schema and summation rules.
- **`refund.status = REQUESTED`** must not be treated as cash already returned to the customer.

Do not default **`NULL = 0`** in financial data or use **`UNKNOWN`** strings for every missing field. Zero can be a valid price; an undetermined amount needs an appropriate status/nullability contract.

### 6.3. Computed values should have one source of truth

For one line:

\[
\text{line\_net\_vnd}
= \text{quantity}\times\text{unit\_price\_vnd}
-\text{discount\_vnd}.
\]

For one order:

\[
\text{order\_total\_vnd}
= \sum_{\text{line in order}}\text{line\_net\_vnd}.
\]

Storing order total as a freely editable column creates two ways to read the same fact: from lines and from the total column. If performance requires materializing totals, enforce **same-transaction updates or deterministic rebuild/reconciliation** and declare the authoritative source. In this lesson, order total is derived from lines.

### 6.4. Criteria for choosing timestamp types

| Field | Meaning | Do not equate with |
| --- | --- | --- |
| created_at | When the record was created in the system | When the order was placed |
| placed_at | When the order took effect as placed | When data ingested to warehouse |
| captured_at | When gateway/source recorded valid capture | When the last webhook arrived |
| settled_at | When the refund was confirmed settled | When the refund was requested |
| valid_from / valid_to | Effective interval of customer tier | When database learned of a correction |
| ingested_at | When a replica arrived in another system | Business event time |

In historical reporting, separate **valid time** from **system/knowledge time** when retroactive corrections occur. A report reflecting data **known on Nov 20** differs from one **restated on Nov 23**, even though both measure Nov 20 sales.

## 7. Step 5 — Listing invariants by enforcement layer

Not every invariant can be implemented as a single-row `CHECK` constraint. Assigning the right enforcement mechanism is just as important as writing the invariant statement.

| ID | Invariant | Primary protection | Verification test |
| --- | --- | --- | --- |
| I01 | Tenant codes are unique | `UNIQUE(tenant_code)` | Inserting two tenants with same code fails |
| I02 | Customer/SKU/order_number unique **within tenant** | Composite `UNIQUE` | Same-tenant duplicate fails; cross-tenant succeeds |
| I03 | No order references another tenant's customer | Composite FK | Inserting cross-tenant FK fails |
| I04 | No line references order/product from another tenant | Composite FK | Negative insert |
| I05 | Positive quantity, discount <= gross line amount | `CHECK` on `order_lines` | Insert qty 0 or excessive discount |
| I06 | DRAFT has no `placed_at`; PLACED/CANCELLED has `placed_at` | State-dependent `CHECK` | Test state transitions |
| I07 | PLACED must have at least one line | Transaction/trigger or atomic service command | Reject placing an empty order |
| I08 | Locked prices and shipping snapshot stay unchanged on product/customer edits | Immutability policy, trigger/versioning | Edit product/customer and verify snapshot |
| I09 | Retries with same idempotency key create no extra payment attempt | `UNIQUE` + idempotent command | Replay duplicate request |
| I10 | Only CAPTURED contributes to collected total | Query/ledger semantic contract | Verify FAILED attempt adds 0 paid |
| I11 | Total CAPTURED on an order <= order payable (lesson assumption) | Transaction locking order row and summing | Two concurrent captures |
| I12 | SETTLED refunds only attach to CAPTURED and <= attempt capture amount | Transaction + locking + state check | Two concurrent refunds |
| I13 | Shipment line belongs to the shipment's order | Composite FK including `order_id` | Test mismatched order link |
| I14 | Total `shipped_qty` across dispatched shipments <= ordered quantity | Transaction on dispatch + order/line lock | Two concurrent shipments |
| I15 | A customer has at most one active tier at any point in time | Non-overlapping range constraint/locking | Test overlapping intervals |
| I16 | JOINs do not multiply amounts from facts at different grains | Grain-safe queries + reconciliation | Fixture 2 lines × 2 payments |
| I17 | Tenants only see authorized data | Authorization/RLS/tenant scope | Attempt cross-tenant read |
| I18 | Historical reports use tier effective at `placed_at` | AS-OF JOIN + versioned metadata | Test before/after tier upgrade boundary |

### 7.1. Three enforcement groups to separate

**Group A — Declarative in the database:** PRIMARY KEY, UNIQUE, FOREIGN KEY, NOT NULL, CHECK; rejects invalid states immediately on INSERT/UPDATE.

**Group B — Multi-row or multi-table:** total CAPTURED/REFUND caps, shipment quantity caps, orders having at least one line; typically requires a **transaction with explicitly designed locking/concurrency control**, or trigger/procedure logic properly guarding against race conditions.

**Group C — Temporal or cross-system:** preventing duplicate source event processing, recording retroactive corrections, AS-OF version selection, API tenant isolation, syncing derived read models. These require **event IDs, checkpoints, transaction boundaries, authorization, reconciliation, and monitoring**, not just schema columns.

### 7.2. “State-transition invariants” versus “always-on invariants”

A shipment in **CREATED** status may still be under assembly with tentative allocations. The **dispatched** cap only counts once the shipment moves to **DISPATCHED/DELIVERED**. A **DRAFT** order may start with zero lines; the “order must have lines” invariant applies upon transitioning to **PLACED**.

Without tying invariants to **status and execution timing**, the system may block valid work-in-progress edits or allow invalid final commits.

### 7.3. Constraints are data rules; authorization is an access rule

A composite FK guarantees an order line references a product **in the same tenant**, but it does not stop another tenant's API call from **reading data** if the query omits tenant filtering or has broken policies. Test permissions at the service layer and consider **PostgreSQL Row-Level Security** when architecture fits; never treat FKs as an authentication mechanism.

## 8. Step 6 — PostgreSQL DDL for core components

The statements below are designed to run **sequentially in an empty test schema**. They intentionally illustrate declarative constraints and SQL's limits; certain **multi-row** invariants will be handled afterward via transactions and tests.

### 8.1. Tenant, customer, and product

~~~sql
CREATE TABLE tenants (
    tenant_id BIGINT PRIMARY KEY,
    tenant_code TEXT NOT NULL UNIQUE
);

CREATE TABLE customers (
    tenant_id BIGINT NOT NULL
        REFERENCES tenants(tenant_id),
    customer_id BIGINT NOT NULL,
    external_customer_code TEXT NOT NULL,
    display_name TEXT NOT NULL,
    email TEXT,
    PRIMARY KEY (tenant_id, customer_id),
    UNIQUE (tenant_id, external_customer_code)
);

CREATE TABLE products (
    tenant_id BIGINT NOT NULL
        REFERENCES tenants(tenant_id),
    product_id BIGINT NOT NULL,
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    list_price_vnd NUMERIC(18, 0) NOT NULL
        CHECK (list_price_vnd >= 0),
    PRIMARY KEY (tenant_id, product_id),
    UNIQUE (tenant_id, sku)
);
~~~

**Explanation:** `customer_id` or `product_id` need not be globally unique. Composite PKs and tenant-scoped UNIQUE constraints enforce the boundaries described in R02–R04. `email` is not UNIQUE because the prompt never claims each email belongs to only one customer.

### 8.2. Order and order line

~~~sql
CREATE TABLE orders (
    tenant_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    order_number TEXT NOT NULL,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('DRAFT', 'PLACED', 'CANCELLED')),
    created_at TIMESTAMPTZ NOT NULL,
    placed_at TIMESTAMPTZ,
    shipping_name TEXT,
    shipping_address TEXT,
    currency_code CHAR(3) NOT NULL DEFAULT 'VND'
        CHECK (currency_code = 'VND'),
    PRIMARY KEY (tenant_id, order_id),
    UNIQUE (tenant_id, order_number),
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES customers(tenant_id, customer_id),
    CHECK (
        (status = 'DRAFT' AND placed_at IS NULL)
        OR
        (
            status IN ('PLACED', 'CANCELLED')
            AND placed_at IS NOT NULL
            AND shipping_name IS NOT NULL
            AND shipping_address IS NOT NULL
        )
    )
);

CREATE TABLE order_lines (
    tenant_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_vnd NUMERIC(18, 0) NOT NULL
        CHECK (unit_price_vnd >= 0),
    discount_vnd NUMERIC(18, 0) NOT NULL DEFAULT 0
        CHECK (discount_vnd >= 0),
    line_net_vnd NUMERIC
        GENERATED ALWAYS AS
            (quantity * unit_price_vnd - discount_vnd) STORED,
    PRIMARY KEY (tenant_id, order_id, line_no),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES orders(tenant_id, order_id),
    FOREIGN KEY (tenant_id, product_id)
        REFERENCES products(tenant_id, product_id),
    CHECK (discount_vnd <= quantity * unit_price_vnd)
);
~~~

**What the DDL protects:** customer and product belong to the same tenant; no duplicate `line_no` within an order; non-negative line values; enforced currency; order lines reference existing orders.

**What the DDL does not yet protect:** a PLACED order has at least one line; lines cannot be altered after placement; CANCELLED cannot transition back to DRAFT. These involve **multiple rows or transition history**, requiring write protocols and dedicated tests.

Under this lesson's status rules, placing an order must execute **inside one transaction**: lock the order, verify lines and snapshot fields exist, then update `status`, `placed_at`, and shipping snapshot. All writers modifying lines or placing orders must obey the same locking protocol to avoid race conditions.

### 8.3. Payment attempt and refund

~~~sql
CREATE TABLE payment_attempts (
    tenant_id BIGINT NOT NULL,
    attempt_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    provider TEXT NOT NULL,
    provider_ref TEXT,
    idempotency_key TEXT NOT NULL,
    amount_vnd NUMERIC(18, 0) NOT NULL CHECK (amount_vnd > 0),
    status TEXT NOT NULL CHECK (
        status IN (
            'INITIATED', 'AUTHORIZED', 'CAPTURED', 'FAILED'
        )
    ),
    captured_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, attempt_id),
    UNIQUE (tenant_id, idempotency_key),
    UNIQUE (tenant_id, provider, provider_ref),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES orders(tenant_id, order_id),
    CHECK (
        (status = 'CAPTURED' AND captured_at IS NOT NULL)
        OR
        (status <> 'CAPTURED' AND captured_at IS NULL)
    )
);

CREATE TABLE refunds (
    tenant_id BIGINT NOT NULL,
    refund_id BIGINT NOT NULL,
    attempt_id BIGINT NOT NULL,
    amount_vnd NUMERIC(18, 0) NOT NULL CHECK (amount_vnd > 0),
    status TEXT NOT NULL
        CHECK (status IN ('REQUESTED', 'SETTLED', 'FAILED')),
    settled_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, refund_id),
    FOREIGN KEY (tenant_id, attempt_id)
        REFERENCES payment_attempts(tenant_id, attempt_id),
    CHECK (
        (status = 'SETTLED' AND settled_at IS NOT NULL)
        OR
        (status <> 'SETTLED' AND settled_at IS NULL)
    )
);
~~~

In PostgreSQL, `UNIQUE(tenant_id, provider, provider_ref)` allows multiple rows with `provider_ref = NULL` under standard UNIQUE-with-NULL behavior. That makes sense before the gateway returns a reference. Once `provider_ref` is populated, a tenant cannot reuse the same provider reference for two attempts. The application must also verify webhooks and validate idempotency payloads rather than relying solely on one UNIQUE constraint.

**Refund** does not store its own `order_id` because the order is reachable via `attempt`. This avoids a refund recording a **different `order_id`** from its attempt. If query performance ever requires storing `order_id` on `refunds`, add a composite FK matching `payment_attempts` or an equivalent constraint so conflicting truths cannot arise.

No single-row `CHECK` on `refunds` can compute **the sum of all SETTLED refunds for the same attempt**. The cap invariant must be enforced at state-transition or ledger-posting time.

### 8.4. Shipment and shipment line

~~~sql
CREATE TABLE shipments (
    tenant_id BIGINT NOT NULL,
    shipment_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    shipment_code TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN (
            'CREATED', 'DISPATCHED', 'DELIVERED', 'CANCELLED'
        )
    ),
    dispatched_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, shipment_id),
    UNIQUE (tenant_id, shipment_code),
    UNIQUE (tenant_id, shipment_id, order_id),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES orders(tenant_id, order_id),
    CHECK (
        (status IN ('DISPATCHED', 'DELIVERED')
            AND dispatched_at IS NOT NULL)
        OR
        (status IN ('CREATED', 'CANCELLED')
            AND dispatched_at IS NULL)
    )
);

CREATE TABLE shipment_lines (
    tenant_id BIGINT NOT NULL,
    shipment_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    shipped_qty INTEGER NOT NULL CHECK (shipped_qty > 0),
    PRIMARY KEY (tenant_id, shipment_id, line_no),
    FOREIGN KEY (tenant_id, shipment_id, order_id)
        REFERENCES shipments(tenant_id, shipment_id, order_id),
    FOREIGN KEY (tenant_id, order_id, line_no)
        REFERENCES order_lines(tenant_id, order_id, line_no)
);
~~~

Although `UNIQUE(tenant_id, shipment_id, order_id)` is redundant relative to the PK, it serves as a **composite FK target** for `shipment_lines`, ensuring allocations share the shipment's `order_id`. If you only had an FK on `(tenant_id, shipment_id)` and a separate FK to `order_lines` on `(tenant_id, order_id, line_no)`, a `shipment_line` could satisfy each table independently while **linking two different orders**.

If a DISPATCHED shipment is later returned, do not merely flip it back to CANCELLED and set `dispatched_at = NULL` when the business requires an audit trail of actual dispatch. This simplified exercise only models the sample statuses; production requires explicit **return/reversal entities, shipment events, and state rules**.

### 8.5. Indexes for common queries

~~~sql
CREATE INDEX idx_orders_customer
    ON orders (tenant_id, customer_id, placed_at);

CREATE INDEX idx_order_lines_product
    ON order_lines (tenant_id, product_id);

CREATE INDEX idx_payments_order_status
    ON payment_attempts (tenant_id, order_id, status);

CREATE INDEX idx_refunds_attempt_status
    ON refunds (tenant_id, attempt_id, status);

CREATE INDEX idx_shipments_order_status
    ON shipments (tenant_id, order_id, status);

CREATE INDEX idx_shipment_lines_order_line
    ON shipment_lines (tenant_id, order_id, line_no);
~~~

These are **index candidates**, not mandatory for every workload. PK/UNIQUE constraints already create backing indexes; add extra indexes only to serve **specific filter/JOIN paths** after checking `EXPLAIN`, read/write ratios, and table size.

## 9. Step 7 — Loading fixtures with test scenarios

Create a compact dataset covering **cross-tenant ID collisions, multi-line orders, multiple payments, multiple refunds, and partial deliveries**. Amounts are integer VND with no external dependencies.

### 9.1. Tenants, customers, and products

~~~sql
INSERT INTO tenants (tenant_id, tenant_code) VALUES
    (1, 'SHOP_A'),
    (2, 'SHOP_B');

INSERT INTO customers (
    tenant_id, customer_id, external_customer_code,
    display_name, email
) VALUES
    (1, 10, 'C-001', 'Customer A', 'a@example.test'),
    (2, 10, 'C-001', 'Customer B', 'b@example.test'),
    (2, 20, 'C-020', 'Secondary Customer B', NULL);

INSERT INTO products (
    tenant_id, product_id, sku, product_name, list_price_vnd
) VALUES
    (1, 100, 'SKU-A', 'Toolkit A', 120000),
    (1, 101, 'SKU-B', 'Accessory B', 90000),
    (2, 100, 'SKU-A', 'Toolkit A - tenant B', 100000);
~~~

Two products share **`product_id = 100`** and **`SKU-A`**, yet belong to **different tenants**, which is valid per contract. Likewise, `customer_id = 10` and `external_customer_code = C-001` repeat in tenant 2; this forces every JOIN to include `tenant_id`.

### 9.2. Three orders, four lines

~~~sql
INSERT INTO orders (
    tenant_id, order_id, order_number, customer_id, status,
    created_at, placed_at, shipping_name, shipping_address,
    currency_code
) VALUES
    (
        1, 500, 'ORD-001', 10, 'PLACED',
        TIMESTAMPTZ '2026-11-20 08:30:00+07',
        TIMESTAMPTZ '2026-11-20 09:00:00+07',
        'Recipient A', 'Locked Address A', 'VND'
    ),
    (
        1, 501, 'ORD-002', 10, 'PLACED',
        TIMESTAMPTZ '2026-11-21 08:30:00+07',
        TIMESTAMPTZ '2026-11-21 09:00:00+07',
        'Recipient A', 'Locked Address A - second', 'VND'
    ),
    (
        2, 500, 'ORD-001', 10, 'PLACED',
        TIMESTAMPTZ '2026-11-20 09:30:00+07',
        TIMESTAMPTZ '2026-11-20 10:00:00+07',
        'Recipient B', 'Locked Address B', 'VND'
    );

INSERT INTO order_lines (
    tenant_id, order_id, line_no, product_id,
    quantity, unit_price_vnd, discount_vnd
) VALUES
    (1, 500, 1, 100, 2, 120000, 20000),
    (1, 500, 2, 101, 1, 90000, 0),
    (1, 501, 1, 101, 2, 90000, 10000),
    (2, 500, 1, 100, 1, 100000, 0);
~~~

Verifying line values:

| Tenant / order / line | Calculation | line_net_vnd |
| --- | --- | ---: |
| 1 / 500 / 1 | 2 × 120,000 − 20,000 | 220,000 |
| 1 / 500 / 2 | 1 × 90,000 | 90,000 |
| 1 / 501 / 1 | 2 × 90,000 − 10,000 | 170,000 |
| 2 / 500 / 1 | 1 × 100,000 | 100,000 |
| **Total** | | **580,000** |

Thus: **tenant 1/order 500 = 310,000 VND**, **tenant 1/order 501 = 170,000 VND**, **tenant 2/order 500 = 100,000 VND**. Total ordered quantity is **6 units**, across **4** lines and **3** orders.

### 9.3. Four captures and two refunds

~~~sql
INSERT INTO payment_attempts (
    tenant_id, attempt_id, order_id, provider,
    provider_ref, idempotency_key,
    amount_vnd, status, captured_at
) VALUES
    (
        1, 900, 500, 'DEMO_GATEWAY',
        'TX-900', 'pay-A-900',
        200000, 'CAPTURED',
        TIMESTAMPTZ '2026-11-20 09:05:00+07'
    ),
    (
        1, 901, 500, 'DEMO_GATEWAY',
        'TX-901', 'pay-A-901',
        110000, 'CAPTURED',
        TIMESTAMPTZ '2026-11-20 09:06:00+07'
    ),
    (
        1, 902, 501, 'DEMO_GATEWAY',
        'TX-902', 'pay-A-902',
        170000, 'CAPTURED',
        TIMESTAMPTZ '2026-11-21 09:05:00+07'
    ),
    (
        2, 900, 500, 'DEMO_GATEWAY',
        'TX-900', 'pay-B-900',
        100000, 'CAPTURED',
        TIMESTAMPTZ '2026-11-20 10:05:00+07'
    );

INSERT INTO refunds (
    tenant_id, refund_id, attempt_id,
    amount_vnd, status, settled_at
) VALUES
    (
        1, 800, 900, 30000, 'SETTLED',
        TIMESTAMPTZ '2026-11-21 10:00:00+07'
    ),
    (
        1, 801, 900, 20000, 'SETTLED',
        TIMESTAMPTZ '2026-11-21 11:00:00+07'
    );
~~~

Both refunds belong to **tenant 1's attempt 900**, totaling 50,000 VND, which is under the 200,000 VND captured on that attempt. Payment **`attempt_id = 900`** and `provider_ref = TX-900` also appear in tenant 2 as a distinct transaction; including `tenant_id` in FKs and JOINs is mandatory.

| Metric | Total VND |
| --- | ---: |
| Valid order lines value | 580,000 |
| Total CAPTURED | 580,000 |
| Total SETTLED refunds | 50,000 |
| CAPTURED minus SETTLED refunds | 530,000 |

**Note:** **CAPTURED − SETTLED refunds** is *net cash captured* under these illustrative rules, not automatically “accounting revenue.” A refund settled after the placement date also does not automatically reduce **placement-date gross ordered value** unless the metric contract specifies restatement.

### 9.4. Partial deliveries

~~~sql
INSERT INTO shipments (
    tenant_id, shipment_id, order_id,
    shipment_code, status, dispatched_at
) VALUES
    (
        1, 700, 500, 'SHP-700', 'DISPATCHED',
        TIMESTAMPTZ '2026-11-21 08:00:00+07'
    ),
    (1, 701, 500, 'SHP-701', 'CREATED', NULL),
    (
        1, 702, 501, 'SHP-702', 'DISPATCHED',
        TIMESTAMPTZ '2026-11-22 08:00:00+07'
    ),
    (
        2, 700, 500, 'SHP-700', 'DELIVERED',
        TIMESTAMPTZ '2026-11-21 08:30:00+07'
    );

INSERT INTO shipment_lines (
    tenant_id, shipment_id, order_id, line_no, shipped_qty
) VALUES
    (1, 700, 500, 1, 1),
    (1, 700, 500, 2, 1),
    (1, 701, 500, 1, 1),
    (1, 702, 501, 1, 2),
    (2, 700, 500, 1, 1);
~~~

Lines on shipments in **CREATED** status are only **planned allocations**, not yet dispatched. Under the exercise rules:

| Order | Ordered qty | DISPATCHED/DELIVERED | Planned in CREATED |
| --- | ---: | ---: | ---: |
| Tenant 1 / 500 | 3 | 2 | 1 |
| Tenant 1 / 501 | 2 | 2 | 0 |
| Tenant 2 / 500 | 1 | 1 | 0 |
| **Total** | **6** | **5** | **1** |

Dispatched quantity may be lower than ordered quantity without being an error. The key invariant is **never exceeding ordered quantity** and linking shipments strictly to the matching order/line.

## 10. Step 8 — Verifying keys and relationships with negative tests

Run each failing test **individually** in the test schema; they are **expected to be rejected by the database**. Do not bundle multiple failing INSERTs in one transaction and expect later statements to proceed.

### 10.1. Rejecting a tenant 1 order referencing a tenant-2-only customer

~~~sql
-- Expected FOREIGN KEY error:
-- customer_id 20 exists only in tenant 2.
INSERT INTO orders (
    tenant_id, order_id, order_number, customer_id, status,
    created_at, placed_at, shipping_name, shipping_address
) VALUES (
    1, 599, 'ORD-599', 20, 'DRAFT',
    TIMESTAMPTZ '2026-11-22 09:00:00+07',
    NULL, NULL, NULL
);
~~~

If the FK referenced only `customer_id` without `tenant_id`, the design would permit cross-tenant customer links. The composite FK rejects this.

### 10.2. Rejecting a discount exceeding gross line amount

~~~sql
-- Expected CHECK error: 150000 > 1 * 100000.
INSERT INTO order_lines (
    tenant_id, order_id, line_no, product_id,
    quantity, unit_price_vnd, discount_vnd
) VALUES (1, 500, 99, 100, 1, 100000, 150000);
~~~

### 10.3. Rejecting an allocation from order 501 inside a shipment of order 500

~~~sql
-- Expected FK (tenant_id, shipment_id, order_id) error:
-- tenant 1's shipment 700 belongs to order 500, not 501.
INSERT INTO shipment_lines (
    tenant_id, shipment_id, order_id, line_no, shipped_qty
) VALUES (1, 700, 501, 1, 1);
~~~

Note: order 501 actually has `line_no = 1`. Thus if you only had **separate** FKs to `order_lines` and `shipments`, each reference would look valid individually while **the relationship between them is wrong**. This test proves why a composite FK including `order_id` is necessary.

### 10.4. Rejecting duplicate idempotency keys within the same tenant

~~~sql
-- Expected UNIQUE(tenant_id, idempotency_key) error.
INSERT INTO payment_attempts (
    tenant_id, attempt_id, order_id, provider,
    provider_ref, idempotency_key,
    amount_vnd, status, captured_at
) VALUES (
    1, 999, 500, 'DEMO_GATEWAY',
    'TX-999', 'pay-A-900',
    200000, 'INITIATED', NULL
);
~~~

**UNIQUE** prevents inserting a second row with the same idempotency key, yet the system must still decide: retries with the **same payload** return the prior result, while retries with a **different payload** return a conflict error—never just throwing HTTP 500 or silently dropping requests.

### 10.5. Which test cannot be expected to fail via CHECK?

Inserting a new **SETTLED 180,000** refund for tenant 1's attempt 900 brings total refunds to **230,000 > 200,000**. Under the illustrative DDL, that INSERT **still succeeds at the single-row level**. This is a **multi-row invariant**; never claim “CHECK will block it” without triggers or concurrency-controlled payment protocols. Section 12 shows how to detect and prevent this via transactions.

## 11. Step 9 — Reconciling JOINs and measures at the right grain

### 11.1. Counterexample: joining order lines and payment attempts directly

~~~sql
-- ANTI-PATTERN: do not use to compute sales or total captured cash.
SELECT
    COUNT(*) AS joined_pairs,
    SUM(l.line_net_vnd) AS duplicated_sales_vnd,
    SUM(p.amount_vnd) AS duplicated_captured_vnd
FROM order_lines AS l
JOIN payment_attempts AS p
  ON p.tenant_id = l.tenant_id
 AND p.order_id = l.order_id
WHERE p.status = 'CAPTURED';
~~~

Expected result on the fixture:

| Metric | Wrong JOIN result | Independent source truth |
| --- | ---: | ---: |
| Joined row count | 6 pairs | 4 lines and 4 attempts |
| SUM(line_net_vnd) | 890,000 | 580,000 |
| SUM(CAPTURED amount_vnd) | 890,000 | 580,000 |

In **tenant 1/order 500**, there are **2 lines × 2 attempts = 4 pairs**. Both lines (220,000 and 90,000) get doubled, inflating this order's sales from **310,000** to **620,000**. Both attempts (200,000 and 110,000) are doubled too. The other two orders each have one line and one attempt so they are not multiplied here; overall inflated total becomes **890,000**.

The dangerous trap is that **both wrong sums equal each other**, making a naive “sales equals captured” check PASS. Good design checks **independent source totals before joining**, never using two inflated numbers from the same JOIN to validate one another.

### 11.2. Correct approach: aggregate each side to order grain

~~~sql
WITH line_totals AS (
    SELECT
        tenant_id,
        order_id,
        COUNT(*) AS line_count,
        SUM(quantity) AS ordered_qty,
        SUM(line_net_vnd) AS order_total_vnd
    FROM order_lines
    GROUP BY tenant_id, order_id
),
capture_totals AS (
    SELECT
        tenant_id,
        order_id,
        COUNT(*) AS captured_attempts,
        SUM(amount_vnd) AS captured_vnd
    FROM payment_attempts
    WHERE status = 'CAPTURED'
    GROUP BY tenant_id, order_id
),
refund_totals AS (
    SELECT
        p.tenant_id,
        p.order_id,
        SUM(r.amount_vnd) AS refunded_vnd
    FROM refunds AS r
    JOIN payment_attempts AS p
      ON p.tenant_id = r.tenant_id
     AND p.attempt_id = r.attempt_id
    WHERE r.status = 'SETTLED'
    GROUP BY p.tenant_id, p.order_id
),
shipped_totals AS (
    SELECT
        s.tenant_id,
        s.order_id,
        SUM(sl.shipped_qty) AS dispatched_qty
    FROM shipments AS s
    JOIN shipment_lines AS sl
      ON sl.tenant_id = s.tenant_id
     AND sl.shipment_id = s.shipment_id
     AND sl.order_id = s.order_id
    WHERE s.status IN ('DISPATCHED', 'DELIVERED')
    GROUP BY s.tenant_id, s.order_id
)
SELECT
    o.tenant_id,
    o.order_id,
    COALESCE(l.line_count, 0) AS line_count,
    COALESCE(l.ordered_qty, 0) AS ordered_qty,
    COALESCE(l.order_total_vnd, 0) AS order_total_vnd,
    COALESCE(c.captured_vnd, 0) AS captured_vnd,
    COALESCE(r.refunded_vnd, 0) AS refunded_vnd,
    COALESCE(c.captured_vnd, 0)
      - COALESCE(r.refunded_vnd, 0) AS net_captured_vnd,
    COALESCE(s.dispatched_qty, 0) AS dispatched_qty
FROM orders AS o
LEFT JOIN line_totals AS l
  ON l.tenant_id = o.tenant_id AND l.order_id = o.order_id
LEFT JOIN capture_totals AS c
  ON c.tenant_id = o.tenant_id AND c.order_id = o.order_id
LEFT JOIN refund_totals AS r
  ON r.tenant_id = o.tenant_id AND r.order_id = o.order_id
LEFT JOIN shipped_totals AS s
  ON s.tenant_id = o.tenant_id AND s.order_id = o.order_id
ORDER BY o.tenant_id, o.order_id;
~~~

Expected result:

| Tenant / order | Lines | Ordered (qty) | Order total (VND) | CAPTURED (VND) | Refund (VND) | Dispatched (qty) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 / 500 | 2 | 3 | 310,000 | 310,000 | 50,000 | 2 |
| 1 / 501 | 1 | 2 | 170,000 | 170,000 | 0 | 2 |
| 2 / 500 | 1 | 1 | 100,000 | 100,000 | 0 | 1 |
| **Total** | **4** | **6** | **580,000** | **580,000** | **50,000** | **5** |

All CTEs **`GROUP BY` the same `(tenant_id, order_id)` key** before joining, so each set contributes at most **one row per order**. This is how you prevent fanout across multi-fact aggregations. While PostgreSQL FKs block payment-only rows without a valid order here, cross-service integrations without FKs must still check for orphans.

### 11.3. Counting orders, customers, lines, and events accurately

~~~sql
SELECT
    COUNT(*) AS order_rows,
    COUNT(DISTINCT (tenant_id, order_id)) AS distinct_orders,
    COUNT(DISTINCT (tenant_id, customer_id))
        AS distinct_customers_with_orders
FROM orders;
-- order_rows = 3; distinct_orders = 3;
-- distinct_customers_with_orders = 2.

SELECT COUNT(*) AS line_rows, SUM(quantity) AS units
FROM order_lines;
-- line_rows = 4; units = 6.

SELECT COUNT(*) AS captured_attempt_rows,
       SUM(amount_vnd) AS captured_vnd
FROM payment_attempts
WHERE status = 'CAPTURED';
-- 4; 580000.
~~~

**Two customers have orders**: `(1,10)` and `(2,10)`, even though **`customer_id = 10`** is identical. Doing `COUNT(DISTINCT customer_id)` without `tenant_id` produces **1** incorrectly.

### 11.4. Checking “placed orders must have lines”

~~~sql
SELECT o.tenant_id, o.order_id
FROM orders AS o
WHERE o.status IN ('PLACED', 'CANCELLED')
  AND NOT EXISTS (
      SELECT 1
      FROM order_lines AS l
      WHERE l.tenant_id = o.tenant_id
        AND l.order_id = o.order_id
  );
~~~

Expect **zero rows**. This is an audit check for invalid data; if two transactions can concurrently place an order and delete a line, post-hoc queries do not replace **locking the order before state transitions and line edits**.

### 11.5. Checking CAPTURED exceeding order total

~~~sql
WITH ordered AS (
    SELECT
        tenant_id, order_id,
        SUM(line_net_vnd) AS order_total_vnd
    FROM order_lines
    GROUP BY tenant_id, order_id
),
captured AS (
    SELECT
        tenant_id, order_id,
        SUM(amount_vnd) AS captured_vnd
    FROM payment_attempts
    WHERE status = 'CAPTURED'
    GROUP BY tenant_id, order_id
)
SELECT
    c.tenant_id, c.order_id,
    c.captured_vnd, o.order_total_vnd
FROM captured AS c
LEFT JOIN ordered AS o
  ON o.tenant_id = c.tenant_id
 AND o.order_id = c.order_id
WHERE o.order_id IS NULL
   OR c.captured_vnd > o.order_total_vnd;
~~~

Expect empty output assuming **non-negative order totals and CAPTURED capped at order value**. If the business allows collecting deposits for off-line service fees or over-collecting security holds, this invariant **must be updated** per the new contract rather than treating the query as universal.

### 11.6. Checking settled refunds per attempt

~~~sql
WITH per_attempt AS (
    SELECT
        p.tenant_id,
        p.attempt_id,
        p.status AS payment_status,
        p.amount_vnd AS captured_amount_when_success,
        COALESCE(
            SUM(r.amount_vnd)
                FILTER (WHERE r.status = 'SETTLED'),
            0
        ) AS settled_refund_vnd
    FROM payment_attempts AS p
    LEFT JOIN refunds AS r
      ON r.tenant_id = p.tenant_id
     AND r.attempt_id = p.attempt_id
    GROUP BY
        p.tenant_id, p.attempt_id,
        p.status, p.amount_vnd
)
SELECT *
FROM per_attempt
WHERE settled_refund_vnd > captured_amount_when_success
   OR (
       payment_status <> 'CAPTURED'
       AND settled_refund_vnd > 0
   );
~~~

Expect **zero rows**. Tenant 1's attempt 900: 200,000 captured, 50,000 refunded. Tenant 2/attempt 900: 100,000 captured, 0 refunded. The check must retain **`tenant_id`**; joining only on `refunds.attempt_id = payment_attempts.attempt_id` mixes up the two attempt 900 records.

### 11.7. Checking dispatched quantity per order line

~~~sql
WITH dispatched AS (
    SELECT
        sl.tenant_id,
        sl.order_id,
        sl.line_no,
        SUM(sl.shipped_qty) AS dispatched_qty
    FROM shipment_lines AS sl
    JOIN shipments AS s
      ON s.tenant_id = sl.tenant_id
     AND s.shipment_id = sl.shipment_id
     AND s.order_id = sl.order_id
    WHERE s.status IN ('DISPATCHED', 'DELIVERED')
    GROUP BY sl.tenant_id, sl.order_id, sl.line_no
)
SELECT
    l.tenant_id,
    l.order_id,
    l.line_no,
    l.quantity AS ordered_qty,
    d.dispatched_qty
FROM dispatched AS d
JOIN order_lines AS l
  ON l.tenant_id = d.tenant_id
 AND l.order_id = d.order_id
 AND l.line_no = d.line_no
WHERE d.dispatched_qty > l.quantity;
~~~

Expect **zero rows**. On tenant 1/order 500/line 1, only **1 of 2 is DISPATCHED**; shipment 701 is still **CREATED** so it is excluded from dispatched count. Once shipment 701 is dispatched, the total becomes **2 of 2**, still valid.

## 12. Step 10 — Preserving invariants under concurrent transactions

The `SELECT` checks in Section 11 are useful for detecting discrepancies, yet **post-write detection does not prevent bad writes**. Total amount and quantity invariants must be protected right on the state-mutation path.

### 12.1. Two concurrent refunds can jointly exceed the cap

Suppose an attempt CAPTURED **200,000** and already has a SETTLED refund of **50,000**. Two workers concurrently receive requests to refund **100,000**:

~~~text
Worker A reads: 150,000 remaining -> 100,000 is valid.
Worker B reads: 150,000 remaining -> 100,000 is valid.
Worker A writes SETTLED 100,000.
Worker B writes SETTLED 100,000.
Total = 250,000 > 200,000: invariant violated.
~~~

One way to protect this inside a PostgreSQL database is **serializing cap-checking operations on the same payment attempt**:

~~~sql
BEGIN;

-- Every writer settling a refund must lock the same parent row.
SELECT tenant_id, attempt_id, status, amount_vnd
FROM payment_attempts
WHERE tenant_id = 1 AND attempt_id = 900
FOR UPDATE;

SELECT COALESCE(SUM(amount_vnd), 0) AS already_settled_vnd
FROM refunds
WHERE tenant_id = 1
  AND attempt_id = 900
  AND status = 'SETTLED';

-- Application or stored procedure verifies:
-- 1. payment.status = CAPTURED.
-- 2. refund is REQUESTED and not yet SETTLED.
-- 3. already_settled + requested_amount <= captured amount.
-- 4. refund webhook idempotency/source authenticity verified.
-- Only after PASS, UPDATE refund to SETTLED
-- within this same transaction.

COMMIT;
~~~

**This is a protocol pattern, not a complete procedure**: the conditions written in comments must actually be executed in code; skipping them leaves SQL unable to block oversettlement. All writers must lock the same `payment_attempts` row consistently; if any direct write path bypasses the lock, the race remains.

Under `READ COMMITTED` isolation, the second worker—after acquiring the parent lock—must **re-read the latest committed refund sum** before deciding. When funds live at an **external payment gateway**, an internal DB transaction alone cannot guarantee the refund actually settled; you also need **provider references, webhook idempotency, reconciliation states, and failure handling**.

### 12.2. Two concurrent CAPTURED attempts on the same order

Suppose an order is worth 310,000, with 200,000 already CAPTURED. Two separate attempts both try to capture 80,000. Each worker sees 110,000 remaining and approves, resulting in **360,000 > 310,000**.

Under an order-level cap contract, every CAPTURED writer must **lock the same `orders(tenant_id, order_id)` row**, recompute line totals and CAPTURED attempts, and commit capture only if the new sum does not exceed the cap. If lines can still be edited while payment is underway, **line-editing paths must coordinate on the same order lock** and finalized status.

In systems distributed across multiple databases, **`SELECT FOR UPDATE` on one node does not lock other nodes**; design explicit ownership/consistency boundaries, ledgers, or coordination mechanisms instead of implicitly assuming global transactions.

### 12.3. Two shipments dispatching the same order line

For an order line of **2 units** with **1** already dispatched, two independent CREATED shipments each attempt to dispatch **1** more unit. If both workers read 1 remaining without synchronization, both dispatch, bringing total shipped to **3 > 2**.

A safe single-database protocol:

1. Lock **`orders(tenant_id, order_id)`** or the relevant **`order_lines`** rows in a deterministic order.
2. Re-read total `shipped_qty` across DISPATCHED/DELIVERED shipments.
3. Add the `shipment_lines` about to transition and check **total <= ordered quantity**.
4. Update status and dispatch timestamp inside the **same transaction**.
5. Any path modifying `shipment_lines`, cancelling dispatch, or changing quantity post-placement must follow the same protocol/audit.

If you also want to manage **pre-dispatch stock holds**, create a dedicated reservation/stock allocation entity or adjust the invariant to include **reserved** quantities rather than equating CREATED with dispatched.

### 12.4. Limits of CHECK constraints and application-only validation

`CHECK` only inspects the row being written, whereas **multi-row SUM** rules require coordination. Conversely, validating only inside an HTTP handler is insufficient if batch jobs, webhook consumers, or admin scripts write directly to the database. Establish **controlled write paths** (stored procedures, service commands, or appropriate triggers), write concurrency tests, and verify all mutation paths obey them.

## 13. Extension — Customer tier history and AS-OF JOIN

Suppose a customer upgrades from BRONZE to GOLD. If historical order reports JOIN to the **current tier**, past orders placed while BRONZE get relabeled as GOLD, distorting historical breakdowns. We add a table at the **grain: one customer tier version effective over a valid-time interval**.

### 13.1. DDL, keys, and time intervals

~~~sql
CREATE TABLE customer_tier_history (
    customer_tier_sk BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    tier TEXT NOT NULL
        CHECK (tier IN ('BRONZE', 'SILVER', 'GOLD')),
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES customers(tenant_id, customer_id),
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE INDEX idx_customer_tier_lookup
    ON customer_tier_history (
        tenant_id, customer_id, valid_from
    );
~~~

**`customer_tier_sk`** identifies one version. **`(tenant_id, customer_id)`** identifies the business customer, which is **not unique** in the history table because a customer has multiple versions. Prevent **overlapping** intervals for the same customer if the contract permits at most one tier at any moment.

On PostgreSQL with **`btree_gist`** available and permitted, you can add:

~~~sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE customer_tier_history
ADD CONSTRAINT customer_tier_no_overlap
EXCLUDE USING gist (
    tenant_id WITH =,
    customer_id WITH =,
    tstzrange(valid_from, valid_to, '[)') WITH &&
);
~~~

The interval **`[valid_from, valid_to)`** is half-open: inclusive of start, exclusive of end. A `NULL` `valid_to` represents an unbounded upper end. Exclusion constraints apply only when a customer **cannot hold two tiers simultaneously**; if the business allows multiple tiers across different loyalty programs, add a **`program_id`** dimension or adjust grain rather than turning valid relationships into errors.

### 13.2. Loading history and querying at placement time

~~~sql
INSERT INTO customer_tier_history (
    customer_tier_sk, tenant_id, customer_id,
    tier, valid_from, valid_to
) VALUES
    (
        1001, 1, 10, 'BRONZE',
        TIMESTAMPTZ '2026-01-01 00:00:00+07',
        TIMESTAMPTZ '2026-11-21 00:00:00+07'
    ),
    (
        1002, 1, 10, 'GOLD',
        TIMESTAMPTZ '2026-11-21 00:00:00+07',
        NULL
    ),
    (
        1003, 2, 10, 'SILVER',
        TIMESTAMPTZ '2026-01-01 00:00:00+07',
        NULL
    );

SELECT
    h.tier,
    COUNT(DISTINCT (o.tenant_id, o.order_id)) AS order_count,
    SUM(l.line_net_vnd) AS ordered_value_vnd
FROM orders AS o
JOIN order_lines AS l
  ON l.tenant_id = o.tenant_id
 AND l.order_id = o.order_id
JOIN customer_tier_history AS h
  ON h.tenant_id = o.tenant_id
 AND h.customer_id = o.customer_id
 AND o.placed_at >= h.valid_from
 AND (o.placed_at < h.valid_to OR h.valid_to IS NULL)
WHERE o.status = 'PLACED'
GROUP BY h.tier
ORDER BY h.tier;
~~~

| Tier at placement | Orders | Line value total (VND) |
| --- | ---: | ---: |
| BRONZE | 1 | 310,000 |
| GOLD | 1 | 170,000 |
| SILVER | 1 | 100,000 |

Joining on **`customer_id`** while omitting **`tenant_id`** mixes tenant 1 and tenant 2 tiers. Joining on tenant/customer while omitting the **time-range predicate** matches both BRONZE and GOLD versions for tenant 1's orders 500 and 501, doubling totals.

### 13.3. Testing that every PLACED order matches exactly one version

~~~sql
SELECT
    o.tenant_id,
    o.order_id,
    COUNT(h.customer_tier_sk) AS tier_versions_matched
FROM orders AS o
LEFT JOIN customer_tier_history AS h
  ON h.tenant_id = o.tenant_id
 AND h.customer_id = o.customer_id
 AND o.placed_at >= h.valid_from
 AND (o.placed_at < h.valid_to OR h.valid_to IS NULL)
WHERE o.status = 'PLACED'
GROUP BY o.tenant_id, o.order_id
HAVING COUNT(h.customer_tier_sk) <> 1;
~~~

Expect **empty output**. **0 matches** indicate missing history or gaps; **more than 1 match** indicates overlapping intervals or missing keys in the JOIN condition. `UNIQUE(customer_tier_sk)` is **insufficient** to guarantee this.

### 13.4. Separating retroactive corrections from reproducing published reports

If on Nov 23 the system learns the customer actually became GOLD on Nov 20, distinguish:

- **Valid time:** on what date did the tier take business effect?
- **System/knowledge time:** on what date did the system record that change?

Directly overwriting `valid_from` in a table that only keeps the current version of history destroys reproducibility of prior published reports. When auditability is required, retain **per-run dimension snapshots** or a **bitemporal** model with both time axes. A restated report reflecting the new truth may shift the BRONZE/GOLD split, while **total `line_net_vnd` across all orders remains unchanged**.

## 14. Extension — Choosing the right physical model and data types

### 14.1. When does a relational model shine?

In this scenario, OrderHub needs:

- Composite FKs preventing cross-tenant references.
- Unique keys protecting orders, lines, attempts, and shipments.
- Transactions protecting order placement, capture/refund settlement, and dispatch.
- Verifiable JOINs across orders, lines, payments, refunds, and shipments.

An RDBMS like PostgreSQL is well suited to **enforce relationships and invariants within one database**. Yet choosing an RDBMS does not make a model automatically correct: `CHECK` cannot sum across rows, and no index fixes a wrong-grain JOIN.

### 14.2. If storing orders as documents

A document could embed an order and its lines:

~~~json
{
  "tenant_id": 1,
  "order_id": 500,
  "status": "PLACED",
  "lines": [
    {"line_no": 1, "product_id": 100,
     "quantity": 2, "unit_price_vnd": 120000,
     "discount_vnd": 20000},
    {"line_no": 2, "product_id": 101,
     "quantity": 1, "unit_price_vnd": 90000,
     "discount_vnd": 0}
  ]
}
~~~

Reading an entire order becomes convenient, yet you must still protect:

- Uniqueness of `(tenant_id, order_id)`.
- No duplicate `line_no` **within the `lines` array**.
- `product_id` referencing a product in the same tenant—without native FKs, verify on write paths or via reconciliation.
- Historical prices not overwritten when the document or product catalog updates.
- Payments/refunds/shipments involve asynchronous operations and usually should not all be embedded into **one document mutated freely by multiple services**.

If a pipeline **`unwind`s** both `lines` and `payments` arrays simultaneously, it still generates Cartesian pairs and multiplies amounts just like a bad SQL JOIN. **Changing storage models does not eliminate grain issues.**

### 14.3. When are graphs useful?

If the goal is traversing **customer–company–representative–supplier–order relationship networks** or multi-hop path queries, a graph model can fit well. However, a graph query counting **paths** does not automatically equal **distinct orders**; one order may be reachable along multiple paths.

Define **node/edge keys, relationship cardinalities, tenant boundaries, and edge valid-time**. For payment ledgers with monetary caps and atomic transactions, a graph does not automatically replace the financial invariants described above.

### 14.4. What are the trade-offs of partitioning/sharding by tenant?

Using **`tenant_id`** as the distribution key keeps most of a tenant's orders, lines, payments, and customers co-located. However:

- A **whale tenant** can still create a hot shard even when tenant IDs hash evenly.
- Cross-tenant queries may require fan-out/aggregation across many shards.
- Cross-shard **UNIQUE/FK** enforcement depends on the engine and is not automatically identical to a single PostgreSQL instance.
- When one tenant outgrows a single shard, distributing by **`(tenant_id, order_id or bucket)`** helps scale out but complicates tenant-wide queries.

In this exercise, the composite PK **`(tenant_id, order_id)`** protects **logical identity**—it does not turn PostgreSQL into a multi-node sharded cluster. Choose partition keys based on **workload, transaction locality, load distribution, and operational limits**.

### 14.5. Designing for schema evolution

To add the tier history table after the application is already live:

1. **Expand:** create the new table and any new reference fields; do not drop old columns prematurely.
2. **Backfill:** source tier versions from trusted timestamps; if only current tiers exist, **never fabricate historical BRONZE rows** for earlier dates.
3. **Validate:** verify no-overlap, transaction coverage, match-count = 1, and sales totals by tier.
4. **Catch-up:** apply new tier changes/corrections via versioned events or CDC with idempotency.
5. **Cutover:** switch reports to read AS-OF history, monitoring differences against old definitions.
6. **Contract:** retire old read paths once consumers confirm and rollback plans exist.

Physical schemas can be tuned iteratively from query statistics; conversely, **grain, keys, and business invariants** must be verified before “optimizing” by dropping relationships or duplicating data.

## 15. Integrated practice set: define the model for each component

The exercises below use **contract R01–R13 and the Section 9 fixture**. Before checking each answer, write down at least:

~~~text
PART / ENTITY:
GRAIN:
PRIMARY KEY:
CANDIDATE/BUSINESS KEYS:
FOREIGN KEYS:
RELATION + CARDINALITY:
ATTRIBUTES: required / nullable / snapshot / derived
INVARIANTS: database / transaction / asynchronous
TESTS: positive / negative / reconciliation
~~~

### Exercise 1 — Separating customers and orders in a multi-tenant environment

Two tenants both have `customer_id = 10` and `order_number = ORD-001`. Tenant 1 has `order_id = 500` for customer 10; tenant 2 also has `order_id = 500` for customer 10.

**Requirements:**

1. Propose PK/UNIQUE for `customers` and `orders`.
2. Write the FK from `orders` to `customers` to prevent cross-tenant references.
3. State customer–order cardinality and handling when orders are deleted or customers change names.
4. Why not use **`customer_id`**, **`email`**, or **`order_number` alone** as a global PK?
5. Propose two negative tests.

<details>
<summary>Solution guide for Exercise 1</summary>

- **customers:** grain one customer within a tenant; PK **`(tenant_id, customer_id)`**, UNIQUE **`(tenant_id, external_customer_code)`**, FK `tenant_id` → `tenants`.
- **orders:** grain one order within a tenant; PK **`(tenant_id, order_id)`**, UNIQUE **`(tenant_id, order_number)`**, FK **`(tenant_id, customer_id)`** → `customers`.
- A customer can have many orders, while each order belongs to one customer. Changing `display_name` does not change customer identity and must not automatically modify a **finalized shipping snapshot**.
- Email is mutable/non-unique contact info; `customer_id` and `order_number` are only guaranteed unique per tenant.
- Negative test A: tenant 1 order references `customer_id = 20` which only exists in tenant 2 → **FK rejects**. Negative test B: two orders in tenant 1 share the same `order_number` → **UNIQUE rejects**; same `order_number` across two tenants succeeds.

</details>

### Exercise 2 — Same product appearing multiple times in one order

Order 501 has two lines with the same `product_id = 101` under two different promotional discounts; the lines are assigned **`line_no = 1, 2`**.

**Requirements:**

1. Why is **`(tenant_id, order_id, product_id)`** not a suitable key?
2. Choose `order_lines` PK, FKs, and quantity/discount invariants.
3. Product list price changes from 90,000 to 100,000 after placement; does the old order's price change?
4. Compute `line_net_vnd` for `quantity = 2`, `unit_price = 90,000`, `discount = 10,000`.

<details>
<summary>Solution guide for Exercise 2</summary>

- Two lines can share `product_id`, so PK **`(tenant_id, order_id, product_id)`** would reject valid lines. Use **`(tenant_id, order_id, line_no)`**.
- Composite FKs to `orders` and `products` both include `tenant_id`. **`quantity > 0`**, **`unit_price >= 0`**, **`0 <= discount <= quantity × unit_price`**.
- **`unit_price_vnd` on the line is a transaction snapshot**, unaffected by `product.list_price_vnd`.
- `line_net_vnd` = **2 × 90,000 − 10,000 = 170,000 VND**.
- The invariant **no line edits after PLACED** requires state-transition/transaction logic or audited immutability mechanisms; single-row value `CHECK`s are insufficient.

</details>

### Exercise 3 — Multiple payments, partial refunds, and idempotency

Tenant 1/order 500 totals 310,000. Two CAPTURED payment attempts are 200,000 and 110,000. Attempt 900 has two SETTLED refunds of 30,000 and 20,000. A webhook for refund 800 is delivered three times.

**Requirements:**

1. Define grain/keys for attempts and refunds.
2. Choose UNIQUE constraints to prevent duplicate attempts on retries.
3. Calculate captured, refunded, and net captured amounts.
4. Can a new 180,000 refund on attempt 900 become SETTLED? Why?
5. Which constraints live in DDL, and which rules require transactions/reconciliation?

<details>
<summary>Solution guide for Exercise 3</summary>

- **payment_attempts:** one collection attempt, PK **`(tenant_id, attempt_id)`**, tenant-scoped FK to order; UNIQUE **`(tenant_id, idempotency_key)`**, UNIQUE on provider reference within proper scope.
- **refunds:** one refund record, PK **`(tenant_id, refund_id)`**, FK **`(tenant_id, attempt_id)`**; webhook retries must recognize the same refund ID/provider reference without creating three new refunds.
- CAPTURED = **310,000**, SETTLED refunds = **50,000**, net captured = **260,000 VND** for order 500.
- Attempt 900 captured **200,000**. A new **180,000** refund brings total to **230,000**, so it **cannot be SETTLED**.
- `CHECK` protects `amount > 0` and statuses; `UNIQUE` protects IDs/idempotency; FKs protect attempt existence/tenant match. **Total refund caps** and **order CAPTURED caps** require locked/serialized transactions, concurrency tests, and provider reconciliation.

</details>

### Exercise 4 — Multi-shipment deliveries for a single order line

Tenant 1/order 500/line 1 has `quantity = 2`. Shipment 700 already DISPATCHED 1 unit; shipment 701 is still CREATED with 1 planned unit.

**Requirements:**

1. Describe the `shipment`–`order_line` relationship and associative entity.
2. Choose `shipment_lines` PK and FKs so lines cannot be attached to another order's shipment.
3. How many units are currently dispatched? If 701 dispatches, how many remain undelivered?
4. If a new shipment 703 also attempts to dispatch 1 unit before 701 dispatches, how must concurrency be checked?

<details>
<summary>Solution guide for Exercise 4</summary>

- One shipment holds multiple order lines and one order line can span multiple shipments: **N–M** via `shipment_lines`, carrying attribute **`shipped_qty`**.
- PK can be **`(tenant_id, shipment_id, line_no)`** since a line appears at most once per shipment. FKs **`(tenant_id, shipment_id, order_id)`** → `shipments`, and **`(tenant_id, order_id, line_no)`** → `order_lines`.
- Currently **1/2 dispatched**; CREATED is excluded. If 701 dispatches successfully, **2/2 dispatched**, **0** remaining.
- For competing shipments, every dispatch protocol must lock the same order/order line, sum **already dispatched** plus quantities **about to transition to DISPATCHED**, and commit only if `<= quantity`. Once one shipment claims the remaining unit, the other cannot dispatch under the same rule.

</details>

### Exercise 5 — Joining lines and payments on the same order

Tenant 1's order 500 has two lines with `line_net` 220,000 and 90,000; and two CAPTURED attempts of 200,000 and 110,000.

**Requirements:**

1. How many rows does a direct JOIN of lines and attempts on `(tenant_id, order_id)` produce?
2. What do `SUM(line_net_vnd)` and `SUM(amount_vnd)` equal after that JOIN?
3. Why does the fact that both sums are equal **not** prove reconciliation?
4. Write an SQL strategy that avoids fanout.

<details>
<summary>Solution guide for Exercise 5</summary>

The JOIN produces **2 × 2 = 4 pairs**. Both sides are doubled: `SUM(lines)` = **620,000**, `SUM(CAPTURED)` = **620,000**, whereas independent source truth is **310,000**.

Aggregate **lines to `(tenant_id, order_id)`** and **CAPTURED attempts to `(tenant_id, order_id)`** separately before joining two sets that each have at most one row per order. Or, if merely checking whether an order has at least one payment, use **`EXISTS`** to avoid multiplying rows.

</details>

### Exercise 6 — Time-varying customer tiers

Tenant 1/customer 10:

~~~text
BRONZE: [2026-01-01 00:00 +07, 2026-11-21 00:00 +07)
GOLD:   [2026-11-21 00:00 +07, +infinity)
~~~

Order 500 placed on Nov 20 09:00 +07; order 501 placed on Nov 21 09:00 +07.

**Requirements:**

1. Which tier does each order belong to at placement time?
2. Why is joining solely on `customer_id` insufficient?
3. Write the exact AS-OF condition at the tier transition boundary.
4. Propose two tests for history integrity.
5. If a correction arrives on Nov 23 effective from Nov 20, what must be kept to reproduce prior published reports?

<details>
<summary>Solution guide for Exercise 6</summary>

- Order 500 = **BRONZE**, order 501 = **GOLD**.
- JOIN requires **`tenant_id` + `customer_id` + `placed_at` within `[valid_from, valid_to)`**. Omitting tenant mixes customers; omitting time fans out across both versions.
- Condition: **`placed_at >= valid_from AND (placed_at < valid_to OR valid_to IS NULL)`**.
- Test 1: no two effective intervals for the same customer overlap. Test 2: every PLACED order matches **exactly one** tier at `placed_at`, including exact boundary timestamps.
- For retroactive corrections, retain report-run dimension snapshots/versions or **bitemporal system-time** to separate previously known data from updated truth.

</details>

### Exercise 7 — Choosing which attributes require snapshots

Tenant 1's product SKU-A currently has `list_price_vnd` 120,000. After order 500 is placed, the company raises the product price to 150,000 and the customer updates their default name/shipping address.

**Requirements:**

1. Which fields on the order/line must never automatically update from product/customer?
2. Do product and customer still need to store current price/address?
3. If `order_total_vnd` is materialized for speed, what invariant must be protected?
4. Propose one negative test and one reconciliation test.

<details>
<summary>Solution guide for Exercise 7</summary>

- **Locked `unit_price_vnd`, `discount_vnd`, `quantity`, `shipping_name`, and `shipping_address` snapshot** must never change when current catalog or customer profiles change.
- Product still needs **current `list_price_vnd`** to quote new orders; customer still needs current contact info.
- A materialized order total must equal **`SUM(line_net_vnd)`** of the order/snapshot's lines per contract; every write path must update synchronously or support rebuild/reconciliation.
- Negative test: after changing `product.list_price_vnd`, verify `line_net_vnd` on order 500 **does not change**. Reconciliation: compare materialized order total (if any) against `SUM(line_net_vnd)` by `(tenant_id, order_id)` and report mismatches.

</details>

### Exercise 8 — Evolving a relationship from 1–N to N–M

Version 1 required **one shipment to deliver an entire order**, with no line-level splitting. Version 2 allows splitting lines across multiple shipments and combining multiple lines into one shipment.

**Requirements:**

1. What new grain emerges?
2. Why would adding a `line_no` array onto `shipments` be hard to verify?
3. What new keys and invariants must be established?
4. Outline a migration plan that preserves historical shipments.

<details>
<summary>Solution guide for Exercise 8</summary>

- The new entity is **`shipment_lines`**, at the grain of one order line allocated to one shipment.
- Each allocation carries **`shipped_qty`**, while status may reside on `shipments`; storing an array makes enforcing FKs, avoiding duplicate `line_no`, and checking total shipped quantity difficult in standard RDBMSs.
- PK by tenant/shipment/`line_no`, FKs to same-order shipment and `order_line`, `CHECK (shipped_qty > 0)`; dispatch protocol ensures total dispatched <= ordered quantity.
- Migration: expand new schema; backfill historical shipments into allocations using trusted evidence; reconcile shipped totals per order line; switch writers/readers by version; preserve rollback/lineage; **never guess-split legacy quantities** when source records lack line detail.

</details>

### Exercise 9 — Testing the model after integrating a new source

The system receives refund webhooks from an external service. Webhooks can be retried; refund records may arrive in the analytics warehouse before the payment attempt snapshot syncs. A team proposes joining both sources by **`attempt_id`** and immediately summing all refunds.

**Requirements:**

1. Identify at least three risks in this design.
2. Define source identity, grain, and statuses to store.
3. Distinguish **true orphans** from **late-arriving data**.
4. Propose quality checks before publishing reports.

<details>
<summary>Solution guide for Exercise 9</summary>

- **`attempt_id` may collide across tenants** or providers; JOINs must include namespace/tenant.
- Webhook retries can double-count refunds without **refund event ID/provider reference and idempotency**.
- REQUESTED/FAILED events must not be summed as SETTLED; the business contract must distinguish statuses.
- Late payment snapshots can create **temporarily unmatched refunds**, not necessarily missing attempts. Quarantine/defer or mark pending for retry once upstream catches up.
- Before publishing, verify refund uniqueness by source ID; attempt exists and is CAPTURED in the same tenant; total SETTLED <= CAPTURED; both sources meet checkpoint/watermark policy; reconcile with provider and run/cutoff version.

</details>

### Exercise 10 — Presenting an ADR for model selection

You must choose a design for two requirements:

- An API looking up **a complete order with all its lines** is called constantly.
- Financial reports **by tenant/day** require payment/refund reconciliation and historical tracking.

**Requirements:** compare relational vs document models, state where the source of truth lives, how the read model is built, three mandatory invariants, key indexes, and an incremental rollout plan.

<details>
<summary>Solution guide for Exercise 10</summary>

A sound ADR may choose **relational PostgreSQL as the source of truth** for orders, lines, payments/refunds, and shipments due to FKs, transactions, and reconciliation needs. The order-lookup API can serve a **document-style read model** holding order/line snapshots rebuilt from the source of truth with versions/checkpoints. Daily sales data marts are built from **facts/events with explicit source keys and timestamps**, never summing directly over a multiplying JOIN.

Three minimal invariants: (1) lines belong to the right order/tenant with unique keys; (2) SETTLED refunds never exceed CAPTURED, protected under concurrency; (3) reports preserve measures per grain/cutoff. Key indexes may include **`orders(tenant_id, order_id)`** from PK, **`order_lines(tenant_id, order_id, line_no)`** from PK, and **`payment_attempts(tenant_id, order_id, status)`** for aggregations.

Evolve via **expand → backfill/read model → reconcile → shadow read → cutover → contract**, with idempotency and rollback. The concrete choice depends on workload; neither relational nor document automatically wins in all contexts.

</details>

## 16. Automated verification suite and self-assessment rubric

### 16.1. Baseline data assertions on the fixture

After loading the Section 9 data, run a **`DO`** block to confirm expected counts and totals:

~~~sql
DO $$
DECLARE
    v_order_count BIGINT;
    v_line_count BIGINT;
    v_line_sum NUMERIC;
    v_captured_sum NUMERIC;
    v_refund_sum NUMERIC;
    v_dispatched_qty BIGINT;
BEGIN
    SELECT COUNT(*) INTO v_order_count FROM orders;

    SELECT COUNT(*), COALESCE(SUM(line_net_vnd), 0)
    INTO v_line_count, v_line_sum
    FROM order_lines;

    SELECT COALESCE(SUM(amount_vnd), 0)
    INTO v_captured_sum
    FROM payment_attempts
    WHERE status = 'CAPTURED';

    SELECT COALESCE(SUM(amount_vnd), 0)
    INTO v_refund_sum
    FROM refunds
    WHERE status = 'SETTLED';

    SELECT COALESCE(SUM(sl.shipped_qty), 0)
    INTO v_dispatched_qty
    FROM shipment_lines AS sl
    JOIN shipments AS s
      ON s.tenant_id = sl.tenant_id
     AND s.shipment_id = sl.shipment_id
     AND s.order_id = sl.order_id
    WHERE s.status IN ('DISPATCHED', 'DELIVERED');

    IF v_order_count <> 3
       OR v_line_count <> 4
       OR v_line_sum <> 580000
       OR v_captured_sum <> 580000
       OR v_refund_sum <> 50000
       OR v_dispatched_qty <> 5
    THEN
        RAISE EXCEPTION
            'Fixture mismatch: orders=%, lines=%, line_vnd=%, captured=%, refund=%, shipped=%',
            v_order_count, v_line_count, v_line_sum,
            v_captured_sum, v_refund_sum, v_dispatched_qty;
    END IF;

    RAISE NOTICE
        'PASS: integrated fixture matches expected values';
END $$;
~~~

Re-running the fixture INSERTs in the same schema without cleanup will raise duplicate PK errors; this is **fixed test data**, not a full idempotent ETL. To practice repeatedly, use a dedicated schema and rebuild cleanly; **never run `DROP CASCADE` on a database holding important data**.

### 16.2. Component-by-component checklist

| Component | Keys/attributes | Relationships | Invariants to prove |
| --- | --- | --- | --- |
| Tenant/customer | Properly scoped PK and UNIQUE; email not ID | Customer → tenant | Two tenants sharing local codes never collide |
| Product/catalog | Per-tenant SKU; current price | Product → lines | List price updates never alter line snapshots |
| Order | Composite PK; `placed_at`; address snapshot | Customer 1–N Order | PLACED has lines; snapshots not arbitrarily edited |
| Order line | PK `(tenant, order, line_no)`; price/qty | Order 1–N Lines | Positive qty, valid discount, same-tenant product |
| Payment attempt | Attempt PK, provider/idempotency keys | Order 1–N Attempts | Retries never duplicate capture; total collection obeys policy |
| Refund | Refund PK, status, amount | Attempt 1–N Refunds | Only SETTLED counts; total refunds <= captured |
| Shipment | Shipment PK, status | Order 1–N Shipments | Dispatch transitions run inside transactions |
| Shipment allocation | Shipment-scoped line PK, `shipped_qty` | N–M Shipment–OrderLine | Same order/tenant; total dispatched <= ordered |
| Customer tier history | Version key, effective interval | Customer 1–N versions | No overlap; AS-OF match = 1 |
| Reports | Grain grouping and metric version | JOIN pre-aggregated sources | No fanout, no missing groups, no tenant mixing |

### 16.3. Grading rubric (100-point guide)

| Criterion | Points |
| --- | ---: |
| Correct **grain** and separation of entity/snapshot/derived | 15 |
| Candidate keys, PK/UNIQUE with accurate **tenant scope** | 15 |
| FKs, relationship multiplicities, and N–M associative entities | 15 |
| Attributes, domains, timestamps, NULL semantics, and history | 15 |
| Declarative invariants and concurrency-safe transactional invariants | 20 |
| Reconciliation SQL, grain-safe JOINs, and negative tests | 15 |
| Trade-off explanations and model evolution plan | 5 |
| **Total** | **100** |

A high-scoring submission provides **evidence** for key claims rather than merely listing table names. For example, stating “refunds never exceed captured” must show **where it is checked and how race conditions are prevented**; stating “tenants stay isolated” must show PKs/FKs, queries, and access controls.

### 16.4. Input mutation testing to catch hidden bugs

Beyond the fixed fixture, try controlled mutations:

1. Insert a new product in tenant 2 with the same SKU as tenant 1: **valid**.
2. Insert a product with the same SKU into tenant 1: **UNIQUE rejects**.
3. Add a FAILED payment attempt to order 500: **total CAPTURED unchanged**.
4. Add a REQUESTED (not yet SETTLED) refund: **net captured unchanged**.
5. Edit current customer name: **shipping snapshot on `orders` unchanged**.
6. Change current `list_price_vnd`: **`line_net_vnd` on old orders unchanged**.
7. Add a CREATED shipment: **`dispatched_qty` unchanged**.
8. Insert an overlapping historical tier interval: **exclusion constraint or overlap test errors**.
9. Add a new CAPTURED attempt for order 500: **order line sales remain 310,000**, never multiplied as attempts grow.
10. Try a JOIN omitting `tenant_id`: colliding IDs across tenants allow tests to **catch wrong results or cross-tenant leakage**.

Run each negative/metamorphic test in a permitted environment with fixture rollback/restore; never use production as a sandbox for intentional constraint violations.

## 17. Mistakes to avoid when defining each component

| Mistake | Why is it wrong? | How to fix |
| --- | --- | --- |
| “Every ID must be globally unique.” | Many codes are only unique per tenant or source. | Specify uniqueness scope; choose proper composite keys. |
| “Customer email or name works as a key.” | Can change, be missing, or collide. | Use stable customer identity; treat email as an attribute. |
| “Product has price, so order line needs no price.” | Current prices change, erasing sale-time values. | Store `unit_price`/`discount` snapshots at placement. |
| “An order has many products, so `order_id` is line PK.” | Cannot store multiple lines for one order. | PK includes `line_no` or grain-appropriate `line_id`. |
| “The same product appears at most once per order.” | Multiple promos or fulfillment splits may occur. | Avoid `product_id` as line key unless contract guarantees it. |
| “An FK on `customer_id` suffices for multi-tenancy.” | Easily links a same-ID customer from another tenant. | Include `tenant_id` in FKs and JOINs, plus authorization checks. |
| “Having FKs protects all relationships.” | Can link a shipment to another order's line if keys omit `order_id`. | Composite FKs to the valid relationship pair. |
| “`CHECK` can validate the `SUM` of refunds.” | Row-level `CHECK` cannot see other rows. | Transactions/locking, ledgers, and reconciliation. |
| “Validating at the API layer is enough.” | Webhooks, batch jobs, admin scripts, or other services may write. | Lock down write paths; add DB protections where feasible. |
| “`UNIQUE` idempotency alone guarantees system-wide exactly-once.” | External transactions and webhooks/retries can still repeat. | Source IDs, response replay, state machines, and reconciliation. |
| “Refund REQUESTED counts as money refunded.” | It might fail or remain unsettled. | Separate statuses; sum only SETTLED per contract. |
| “Shipment CREATED counts as delivered.” | May still be packing or cancelled. | Count shipped only on effective statuses. |
| “JOIN two tables then SUM if numbers look right.” | 2 lines × 2 payments multiplies totals. | Aggregate at proper grain before JOINs and reconcile sources. |
| “`COUNT(DISTINCT order_id)` is always right.” | Order IDs can collide across tenants. | `COUNT(DISTINCT (tenant_id, order_id))`. |
| “Customer's current address is delivery history.” | Users can update addresses after ordering. | Snapshot at placement; version if needed. |
| “SCD has `customer_sk` so AS-OF predicates aren't needed.” | Surrogate key assignment can pick the wrong point in time. | Verify matches by business key + valid-time. |
| “No-overlap means history always has a record.” | Gaps or late-arriving records still occur. | Check fact coverage; distinguish missing vs unknown. |
| “Equal totals prove nothing is wrong.” | Errors can cancel out; both sides of a JOIN can double equally. | Compare IDs, per-order/per-tenant groups, and totals. |
| “Adding partitions automatically spreads whale-tenant load.” | Hashing by tenant still places one tenant on one shard. | Measure workload; consider bucketing/dedicated shards. |
| “Schema changes let you delete old data immediately.” | Backfill/catch-up may be incomplete or consumers still read old paths. | Expand → backfill → validate → cutover → contract. |

### 17.1. Distinguishing data errors from valid business exceptions

Not everything unusual-looking is a bug:

- **An order with zero payments** can be valid while awaiting payment.
- **A shipment delivering less than ordered** can be valid due to split deliveries.
- **A REQUESTED refund not yet SETTLED** is not transferred cash.
- **A customer lacking a tier at a timestamp** may need an Unknown status or wait for late dimensions, depending on contract.
- **A product priced at 0** may be a valid promotional freebie.
- **Two tenants sharing the same `order_id`** is valid within the defined scope.

Flagging data as “broken” must stem from **business-confirmed invariants**, not intuition or an overly clean sample dataset.

### 17.2. Short answer template for design reviews

A team can summarize each component in five sentences:

> **Grain:** one row of this table represents ...  
> **Key:** the PK is ...; business codes are unique within ...  
> **Relation:** this table links to ... with cardinality ...; FKs enforce ...  
> **Attributes:** snapshot attributes are ...; derived measures are ...  
> **Invariant:** the database blocks ...; transactions protect ...; reconciliation detects ...

If any of the five sentences is missing, revisit that component before building APIs, writing ETL, or picking a sharding strategy.

## 18. Key takeaways

This exercise centers on **one unified method**: starting from business requirements, define **entities and grain**, pick **keys and uniqueness scopes**, state **relationships and cardinalities**, classify **current, snapshot, derived, and historical attributes**, and finally formalize **invariants with explicit enforcement layers and verification tests**.

In the OrderHub case study, composite keys enforce tenant boundaries; `order_lines` retain locked prices instead of reading current catalog prices; payments/refunds and shipments each have their own grain and must be aggregated **before joining**; concurrent transactions require locking and balance/quantity checks within the same scope; and historical customer tiers require **AS-OF JOINs over `[from, to)` intervals**. A new table, a new index, or a different storage engine never replaces these fundamentals.

In real projects, a reliable sequence is **lock contract & assumptions → draw entities/relationships → design keys & DDL → build fixtures with tough edge cases → run negative/reconciliation tests → protect concurrency → test history & tenant isolation → evaluate performance → deploy with backfill, cutover, and rollback**. A good model does more than store valid records: it **prevents invalid states, explains historical data, and evolves safely**.
