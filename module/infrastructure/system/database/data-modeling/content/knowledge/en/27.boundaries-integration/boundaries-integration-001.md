# Context-Specific Data Models Instead of One Model for Every System

## Learning Objectives

An enterprise may use words like **customer**, **product**, **order**, **price**, **inventory**, and **status** across multiple departments. However, those words do not necessarily carry the same meaning, the same lifecycle, or the same constraint rules in every workflow. A data model that tries to serve every system with **one entity, one set of attributes, and one shared status set** often becomes confusing, full of optional columns, prone to rule conflicts, and hard to change independently.

One approach is to **design a separate data model for each business context** (*bounded context*), and then clarify how contexts **exchange events, requests, and identifiers** through integration contracts. The goal is not to create as many databases as possible, but to keep **data semantics and ownership clear**, while coordinating reliably enough when a business process spans multiple contexts.

This lesson belongs to the **Boundaries and Integration** chapter of the **DATABASE_DATA_MODELING** module. In line with the module's goals, learners practice translating business requirements into clear data models—from entities, relationships, and constraints to normalization, keys, indexes, and physical schemas—while comparing relational, document, graph, and analytical models to choose structures that are easy to evolve and verify. This lesson emphasizes **semantic boundaries and data ownership** during system integration.

After completing this lesson, you will be able to:

1. Explain **bounded context**, **ubiquitous language within a context**, and how they differ from table, package, service, or physical database boundaries.
2. Recognize the signs of an **overly ambitious global model**: a single shared entity with multiple meanings, one status enum for every workflow, and shared tables with multiple writing teams.
3. Build separate models for **Product Catalog, Sales, Inventory, Billing, and Fulfillment**, even when contexts may reference the same external business code.
4. Distinguish **local keys**, **cross-context reference identifiers**, and **constraints enforced within the same database**.
5. Design integration contracts—**synchronous APIs**, **asynchronous events**, and **anti-corruption layers (ACL)**—without exposing internal tables.
6. Identify transaction boundaries, local invariants, **eventual consistency**, **transactional outbox**, **inbox/idempotency**, late-arriving events, and compensation mechanisms in multi-context workflows.
7. Distinguish **context-specific operational models** from **integrated read models / analytical layers** built to serve queries across multiple sources.
8. Create checklists and tests to evaluate when to split models, when to share contracts, and when **not** to split a system.

> **Scope note:** The examples use PostgreSQL SQL and modern Java for illustration. They help demonstrate structure, keys, contracts, and integration risks; they are **not** a complete microservices platform or proof that a message broker, distributed transactions, retry mechanisms, and operational monitoring are already in place.

## 1. Why Does a Global Data Model Often Fail?

### 1.1. The Same Name Does Not Mean the Same Business Entity

Consider an online store with the following departments:

| Context | Familiar Term | Meaning in That Context |
| --- | --- | --- |
| **Catalog** | Product | Definition of what is offered for sale: description, SKU, category, publication status |
| **Sales** | Product in an order | Snapshot of the item, accepted price, tax/discount, and quantity **at checkout** |
| **Inventory** | Stock item | Allocatable units of goods, warehouse location, available stock, and reserved portion |
| **Billing/Payments** | Order, amount | Receivable obligation, payment documents, collection transactions, and refunds |
| **Fulfillment** | Delivery order | Packages/shipments to pack, track, deliver, and confirm |
| **Identity/Accounts** | User | Login identity, authentication methods, access permissions |

A **product** in Catalog may be renamed from "A5 Notebook" to "A5 Hardcover Notebook". An order purchased last month still needs to display **the name and price at the time of the transaction**, rather than changing with the current catalog. A discontinued product may still have inventory to process returns. A paid order may not be fully delivered yet; payment status and fulfillment status are **two different concepts**.

If you force everything into:

~~~~text
UNIVERSAL_PRODUCT(id, name, price, quantity, reserved, published,
                  warehouse, paid, shipped, status, ...)

UNIVERSAL_ORDER(id, customer_id, payment_status, picking_status,
                shipment_status, accounting_status, ...)
~~~~

you will face hard questions: who is allowed to edit `price`, is `price` the list price or the accepted order price, is `quantity` system-wide stock or the quantity of a single order line, and which process should `status` prioritize? **More columns do not create a unified definition** when the underlying concepts differ.

### 1.2. What Kind of Coupling Does a Global Model Create?

| Symptom | Design Consequence |
| --- | --- |
| Multiple systems INSERT/UPDATE the same table | Hard to determine who owns the invariants and who is responsible when data is wrong |
| One status enum must add values for every workflow | Every service must redeploy when one department introduces a new status |
| Columns apply to only some systems | Many NULLs with different meanings; validation rules become complex |
| A foreign key from one system points deep into another system's internal table | Internal structural changes cause cascading impacts |
| Changing a schema requires sign-off from multiple teams | Release velocity becomes coupled to one large schema |
| Reports freely JOIN operational tables across every team | Different semantics get mixed up; hard to guarantee timing and data permissions |
| One "shared domain" library contains every entity | Teams are forced to upgrade the same conceptual version despite different needs |

The issues above **do not prove that every shared table is bad**. A rarely changing reference table governed by a single party, such as currency codes or an agreed country catalog, can still be reasonably shared. The problem lies in **multiple independent contexts assigning meanings and write permissions** to a model without a clear owner.

### 1.3. Example: Multiple Perspectives on "Customer"

In Identity, a user may represent a login account, verified email, and permissions. In Sales, the **buyer** is the person placing the order; contact name and shipping address may be recorded specifically for that order. In Billing, the **bill-to party** is the party obligated to pay, which may be a different company from the recipient. In customer support, a **contact** may be an authorized representative.

You should not default to putting everything into one global `CUSTOMER` table with one ID and every column required. There may be **identity mapping relationships**, yet "the same person" does not guarantee "the same business role" or "permission to use the same personal data".

## 2. Bounded Context: The Boundary of Meaning and Rules

### 2.1. Definition

A **bounded context** is a scope within which **a model, terminology, and business rules have a clear, consistent meaning**. Within that context, terms such as Order, Customer, Stock, Paid, or Available have definitions agreed upon by the responsible team.

The word "Order" may refer to:

- **SalesOrder** in Sales: a purchase commitment, accepted prices, and placement/confirmation status.
- **FulfillmentRequest** in Fulfillment: a request to prepare and deliver specific item lines.
- **Invoice** in Billing: a document or payment obligation governed by accounting rules.

These entities may be linked via **order_id**, but **they do not need the same attributes, the same primary key, or the same lifecycle**.

**A bounded context does not automatically equal one microservice**, one SQL schema, or one org team. A monolith can have multiple well-isolated context modules; a large context might require multiple deployment processes. What you must verify are **language, invariants, ownership, and contracts**.

### 2.2. Ubiquitous Language Within Each Context

A Sales team might define:

> An order is **confirmed** when prices and purchase terms are finalized, and all required steps under Sales policy have succeeded.

A Billing team might define:

> A receivable is **settled** when the payment gateway or accounting ledger confirms the transaction under Billing rules.

A Fulfillment team might define:

> A package is **delivered** when there is valid delivery confirmation.

The three concepts "confirmed", "settled", and "delivered" should not be collapsed into a single generic **status = DONE** value. When you need to display "order completed", an aggregation layer must **precisely define** the condition combining these statuses, rather than forcing every context to write to a shared `status` column.

### 2.3. Signals for Finding Boundaries

A few practical questions:

1. **Who decides** whether a record is valid? Does Catalog or Sales decide the price payable for a placed order?
2. **What changes together?** Stock locks and inventory reservations must be updated atomically; marketing descriptions do not need to be in the same transaction.
3. **When does a word change meaning?** "Available" in Catalog may mean allowed to be displayed; in Inventory it means the allocatable quantity.
4. **Is there a separate lifecycle?** A Sales order is finalized while a Shipment is still in transit.
5. **Are there different access control requirements?** Authentication secrets in Identity should not live in Sales's buyer copy.
6. **Can it change independently?** The warehouse team updates the reservation algorithm without migrating every Sales table.

Do not draw boundaries just because "one noun equals one microservice". Boundaries must reflect **real rules and collaboration patterns**, not merely an org chart.

### 2.4. Example Context Diagram

~~~~mermaid
flowchart LR
    C["Catalog\nProduct definition"] -->|"Product quote / published data"| S["Sales\nOrders and locked prices"]
    S -->|"OrderSubmitted"| I["Inventory\nStock reservation and availability"]
    I -->|"InventoryReserved / Rejected"| S
    S -->|"OrderConfirmed"| B["Billing\nPayment obligation"]
    S -->|"OrderConfirmed"| F["Fulfillment\nDelivery request"]
    B -->|"PaymentSettled"| S
    F -->|"ShipmentDelivered"| S
    S -.->|"Events for reporting"| R["Reporting / Read model"]
    B -.->|"Events for reporting"| R
    F -.->|"Events for reporting"| R
~~~~

The arrows represent **intent to exchange information**, not an assertion that a specific workflow is already implemented or that `OrderConfirmed` must always occur in the exact sequence shown. The order of reservation, payment collection, confirmation, and shipping must be **finalized according to each system's business policy**.

## 3. Separate Data Models for Five Contexts

### 3.1. Catalog: Truth About Items Offered for Sale

A Catalog model might include:

~~~~text
CATALOG_PRODUCT(
  product_id,
  sku,
  display_name,
  category_id,
  publication_status,
  current_list_price,
  currency_code,
  catalog_version
)
~~~~

Catalog owns rules such as unique SKU per market, display name, category, and which products may appear in the catalog. **current_list_price** is the current list price, not by default the final price a customer accepted in a past transaction.

### 3.2. Sales: Truth About Placed Orders

A Sales model might include:

~~~~text
SALES_ORDER(
  order_id,
  buyer_ref,
  order_status,
  submitted_at,
  order_currency
)

SALES_ORDER_LINE(
  order_line_id,
  order_id,
  catalog_product_ref,
  product_name_snapshot,
  quantity,
  accepted_unit_price,
  discount_snapshot,
  line_currency
)
~~~~

**catalog_product_ref** is a reference identifier to the product concept in Catalog. However, the finalized name, price, and discount belong to **Sales's order data**; when Catalog changes a name or list price, an already accepted order line must not necessarily be rewritten.

Sales must ensure that each `order_line` belongs to a local order, quantities are valid, totals follow policy, and state transitions are permitted. Those invariants differ from whether Catalog allows the product to appear on the search page.

### 3.3. Inventory: Truth About Quantities and Reservations

An Inventory model might include:

~~~~text
STOCK(
  warehouse_id,
  stock_product_ref,
  on_hand_qty,
  reserved_qty
)

STOCK_RESERVATION(
  reservation_id,
  external_order_line_ref,
  warehouse_id,
  stock_product_ref,
  reserved_qty,
  reservation_status,
  expires_at
)
~~~~

Within the agreed unit of measure and inventory policy scope:

\[
\text{available}=\text{on\_hand\_qty}-\text{reserved\_qty}.
\]

Inventory owns the invariant of **never reserving beyond allocatable capacity** under warehouse rules. Sales should not directly UPDATE `reserved_qty` by accessing Inventory tables; Sales sends a **stock reservation request** and receives a success/failure result.

### 3.4. Billing: Truth About Documents and Money

A Billing model might include:

~~~~text
INVOICE(
  invoice_id,
  external_order_ref,
  bill_to_party_id,
  invoice_amount,
  currency_code,
  invoice_status,
  issued_at
)

PAYMENT(
  payment_id,
  invoice_id,
  gateway_transaction_ref,
  settled_amount,
  settled_at,
  payment_status
)
~~~~

An order may have **multiple payments**, refunds, or split invoices according to business rules. Do not assume the Order–Invoice relationship is always 1:1 without verification. Billing defines when funds are **collected**, based on authoritative payment gateway events or accounting ledger records; Sales only consumes the outcome relevant to the ordering workflow.

### 3.5. Fulfillment: Truth About Packages and Delivery

A Fulfillment model might include:

~~~~text
SHIPMENT(
  shipment_id,
  external_order_ref,
  shipping_address_snapshot,
  shipment_status,
  dispatched_at,
  delivered_at
)

SHIPMENT_LINE(
  shipment_line_id,
  shipment_id,
  external_order_line_ref,
  packed_qty
)
~~~~

One `SalesOrder` may generate multiple `Shipments` due to split warehouses or multi-batch delivery. Conversely, one `Shipment` may consolidate lines according to operational rules. Therefore, you should not attach **shipment_status** and **tracking_number** directly to a `SalesOrder` table and assume one order has one package.

### 3.6. Summary of Differences

| Context | Core Question | Example Invariant | Data from Other Contexts |
| --- | --- | --- | --- |
| Catalog | Which items can be offered for sale? | Valid SKU / catalog version | Pricing policy or taxonomy synced if needed |
| Sales | What did the customer agree to buy, at what price? | Line belongs to order; locked price does not change arbitrarily | `product_ref`, quote, `buyer_ref` |
| Inventory | Is there enough stock to allocate? | Reserved quantity does not exceed available stock per warehouse rules | `product_ref`, `order_line_ref` |
| Billing | Which amounts were invoiced and collected? | Do not record the same gateway transaction twice | `order_ref` and receivables per contract |
| Fulfillment | Which goods need to be packed/delivered? | Shipment has valid lines and quantities | `order_ref`, `line_ref`, finalized delivery address |

**Shared reference keys link objects at the business level; they do not turn sub-models into one global SQL entity.**

## 4. Data Ownership and Transaction Boundaries

### 4.1. Who Is the Source of Truth?

A generally useful design principle:

> **Every critical business state needs a single party responsible for deciding and protecting its invariants.** Other parties may use or store a copy with clear provenance, but must not arbitrarily modify owned state.

For example:

- Catalog is the authoritative source for **current display name and list price**.
- Sales is the authoritative source for **the price accepted on an order**.
- Inventory is the authoritative source for **allocatable capacity and reserved stock**.
- Billing is the authoritative source for **settled payment transactions**.
- Fulfillment is the authoritative source for **package delivery status**.

These are **non-conflicting** scopes. Sales keeping a copy of the product name at purchase time is not "improperly denormalized duplicate data" when it is a **snapshot with its own historical meaning**. Conversely, Sales directly modifying stock counts and treating its copy as real inventory creates an ownership conflict.

### 4.2. Logical Boundaries Do Not Force Every Context into a Separate Database

Deployment options include:

| Option | Example | Points to Control |
| --- | --- | --- |
| **Modular monolith** | Same process, separate Sales and Inventory packages | Clear module APIs; prevent layers from arbitrarily reading/editing each other's tables |
| **Same DB, separate schemas/roles** | `sales.orders` and `inventory.stock` in PostgreSQL | Schema owners, GRANT privileges, independent migrations, avoid arbitrary cross-schema FKs or JOINs |
| **Separate database per context** | Sales DB and Inventory DB | External ID references, API/event contracts, handling eventual consistency |
| **One context with multiple apps** | API and worker operating on the same Inventory model | Coordinate write permissions and invariants within the same ownership boundary |

Do not decide on "one database per context" before understanding **semantics and invariants**. Physical separation can increase deployment independence, but it also increases integration, observability, and consistency overhead; physical co-location can still protect logical boundaries if rigorously governed and access-controlled.

**Note:** PostgreSQL schemas do not automatically prevent an application role from accessing another schema. If two modules use the same superuser-like account and modify each other's tables, simply naming schemas differently **does not** guarantee ownership.

### 4.3. Local Invariants vs. Cross-Context Invariants

A **local invariant** can be checked within a single transaction of the owning context, for example:

- In Sales: every `order_line` belongs to a valid `sales_order`; `quantity > 0`.
- In Inventory: `on_hand_qty >= 0`, `reserved_qty >= 0`, and `reserved_qty <= on_hand_qty`.
- In Billing: a payment gateway transaction code cannot be recorded twice within its proper identifier scope.

A requirement like "**do not confirm an order unless enough stock is reserved and payment is valid**" spans **multiple contexts**. You cannot simply add a SQL `CHECK` constraint to a Sales table to guarantee that Inventory/Billing states in other databases are always instantaneously synchronized.

You must define:

1. **Who orchestrates** the process or makes the final confirmation decision.
2. **Which messages/attestations** count as valid reservation and payment results.
3. **Pending**, **failed**, **expired**, or **cancelled** states of the workflow.
4. How to handle **duplicates, late arrivals, timeouts, and compensating actions**.
5. What is **eventually consistent** and what must be checked immediately inside the owning context.

You do not need to make the entire system distributed to model invariants properly; rather, you must know **which invariants cannot be delegated to a foreign key or an enum in a global table**.

## 5. Local Keys and Cross-Context References

### 5.1. Two Types of Identifiers to Distinguish

A **local key** identifies a row inside a context's own model, such as `sales.order_line_id` as the PK of a Sales order line.

An **external reference identifier** is a code a context uses to recognize an object owned by another context, for example:

~~~~text
Sales.order_line.catalog_product_ref = Catalog.product_id
Inventory.stock.stock_product_ref    = Catalog.product_id
Billing.invoice.external_order_ref   = Sales.order_id
~~~~

All three reference fields may carry the same UUID value in wire contracts, but each party uses it for **a different purpose**. It **does not** make `SalesOrderLine`, `CatalogProduct`, and `StockItem` a single object.

A well-formed UUID **does not prove** that the product is still for sale, that the price is confirmed, or that stock exists in the warehouse. Those questions must be answered through **the owning party's rules and contracts**.

### 5.2. Do Not Default to Cross-Context Foreign Keys

In the **same database**, it is technically possible to create an FK between the Sales and Catalog schemas. However, that FK creates **schema and data lifecycle coupling**: Catalog struggles to modify or delete a record without affecting Sales, even though Sales must retain purchased order history while Catalog may discontinue products.

With **separate databases**, standard SQL foreign keys cannot directly protect rows in another database. In that case:

- Sales stores **catalog_product_ref** and a **snapshot** of accepted data.
- Sales checks purchase eligibility via an **API/quote** or Catalog data synchronized under contract.
- Sales retains a **source reference** for traceability rather than treating it as an internal FK.
- Verification and reconciliation mechanisms detect unresolvable references, depending on history retention policies.

This does not mean "FKs are always bad". **Internal FKs within a context are a powerful tool** for protecting local relationships. For a modular monolith with fixed ownership, a physical cross-module FK can sometimes be a deliberate trade-off. What matters is **evaluating change cost and write ownership**, rather than treating an existing FK as proof that two concepts belong in the same bounded context.

### 5.3. Scoped Identifiers

If an SKU is only unique **per tenant** or **per market**, a reference containing only `sku` is ambiguous. The contract may require:

~~~~text
ProductReference(
  tenant_id,
  catalog_id,
  product_id
)
~~~~

Which fields are actually needed depends on the agreed identifier semantics. Do not add fields endlessly; however, **never drop the scope** just because every code is formatted as a String.

### 5.4. Identifier Mapping When Contexts Have Their Own IDs

Some Billing systems issue their own `customer_account_id`, while Identity issues `identity_user_id`. You should not assume the two UUIDs must be identical. A mapping relation might have:

~~~~text
BILLING_ACCOUNT_LINK(
  billing_account_id,
  source_system,
  external_party_ref,
  verified_at
)
~~~~

Whether the rule is **one-to-one, one-to-many, or many-to-many** must come from business rules: one enterprise may have multiple login accounts; one person may represent multiple companies. Identity mapping can be a **governed business entity**, not an implicit JOIN by email.

## 6. PostgreSQL: One Illustrative Database While Models Stay Context-Separated

This SQL snippet is only an **illustrative schema in a single fresh PostgreSQL database**, not a requirement that every system share a database. Tables are placed in four schemas to **expose ownership boundaries**. The key point is: **local FKs inside each schema**, while references to other contexts are expressed through reference codes and integration contracts.

### 6.1. Catalog and Sales Schemas

~~~~sql
CREATE SCHEMA catalog;
CREATE SCHEMA sales;
CREATE SCHEMA inventory;
CREATE SCHEMA billing;

CREATE TABLE catalog.product (
    product_id UUID PRIMARY KEY,
    sku VARCHAR(40) NOT NULL UNIQUE,
    display_name VARCHAR(160) NOT NULL,
    current_list_price NUMERIC(18, 2) NOT NULL
        CHECK (current_list_price >= 0),
    currency_code CHAR(3) NOT NULL DEFAULT 'VND'
        CHECK (currency_code = 'VND'),
    publication_status VARCHAR(20) NOT NULL
        CHECK (publication_status IN ('DRAFT', 'ACTIVE', 'ARCHIVED'))
);

CREATE TABLE sales.sales_order (
    order_id UUID PRIMARY KEY,
    buyer_external_ref UUID NOT NULL,
    submitted_at TIMESTAMPTZ NOT NULL,
    order_status VARCHAR(20) NOT NULL
        CHECK (order_status IN (
            'DRAFT', 'SUBMITTED', 'CONFIRMED', 'CANCELLED'
        ))
);

CREATE TABLE sales.order_line (
    order_line_id UUID PRIMARY KEY,
    order_id UUID NOT NULL
        REFERENCES sales.sales_order(order_id),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    catalog_product_ref UUID NOT NULL,
    product_name_at_purchase VARCHAR(160) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    accepted_unit_price NUMERIC(18, 2) NOT NULL
        CHECK (accepted_unit_price >= 0),
    currency_code CHAR(3) NOT NULL DEFAULT 'VND'
        CHECK (currency_code = 'VND'),
    UNIQUE (order_id, line_no)
);
~~~~

**What is protected:**

- `sales.order_line.order_id` is an FK to **sales.sales_order**: both belong to **Sales**.
- Each sales line has a unique `line_no` within the order, `quantity > 0`, and a non-negative `accepted_unit_price`.
- `catalog_product_ref` is a **reference to Catalog**, with no SQL FK from Sales to `catalog.product`.
- `product_name_at_purchase` and `accepted_unit_price` are **data finalized by Sales**, not defined by Catalog's current price/name.

**What is not yet protected by DDL:** Whether the item was actually allowed by Catalog to be sold at checkout, whether the quote had expired, whether the buyer was eligible to order, or whether the quantity was accepted by Inventory. Those invariants require corresponding rules and contracts.

### 6.2. Inventory and Billing Schemas

~~~~sql
CREATE TABLE inventory.stock (
    warehouse_code VARCHAR(40) NOT NULL,
    catalog_product_ref UUID NOT NULL,
    on_hand_qty INTEGER NOT NULL CHECK (on_hand_qty >= 0),
    reserved_qty INTEGER NOT NULL CHECK (reserved_qty >= 0),
    PRIMARY KEY (warehouse_code, catalog_product_ref),
    CONSTRAINT ck_inventory_not_over_reserved
        CHECK (reserved_qty <= on_hand_qty)
);

CREATE TABLE inventory.stock_reservation (
    reservation_id UUID PRIMARY KEY,
    source_request_id UUID NOT NULL UNIQUE,
    warehouse_code VARCHAR(40) NOT NULL,
    catalog_product_ref UUID NOT NULL,
    external_order_line_ref UUID NOT NULL,
    reserved_qty INTEGER NOT NULL CHECK (reserved_qty > 0),
    reservation_status VARCHAR(20) NOT NULL
        CHECK (reservation_status IN (
            'HELD', 'COMMITTED', 'RELEASED', 'EXPIRED'
        )),
    FOREIGN KEY (warehouse_code, catalog_product_ref)
        REFERENCES inventory.stock(warehouse_code, catalog_product_ref)
);

CREATE TABLE billing.invoice (
    invoice_id UUID PRIMARY KEY,
    external_order_ref UUID NOT NULL,
    invoice_amount NUMERIC(18, 2) NOT NULL
        CHECK (invoice_amount >= 0),
    currency_code CHAR(3) NOT NULL DEFAULT 'VND'
        CHECK (currency_code = 'VND'),
    invoice_status VARCHAR(20) NOT NULL
        CHECK (invoice_status IN (
            'ISSUED', 'PARTIALLY_PAID', 'PAID', 'VOID'
        ))
);

CREATE TABLE billing.payment (
    payment_id UUID PRIMARY KEY,
    invoice_id UUID NOT NULL
        REFERENCES billing.invoice(invoice_id),
    gateway_transaction_ref VARCHAR(100) NOT NULL UNIQUE,
    settled_amount NUMERIC(18, 2) NOT NULL
        CHECK (settled_amount >= 0),
    settled_at TIMESTAMPTZ,
    payment_status VARCHAR(20) NOT NULL
        CHECK (payment_status IN (
            'PENDING', 'SETTLED', 'FAILED'
        ))
);
~~~~

In Inventory, a `STOCK` row is keyed by **(warehouse_code, catalog_product_ref)**: one product can have stock across multiple warehouses. `external_order_line_ref` references Sales at the **integration contract** level, without creating an FK to `sales.order_line`.

In Billing, `invoice` references the external order via `external_order_ref`; **we do not place `UNIQUE(external_order_ref)`** because the design does not assume an order has only one invoice. `payment.invoice_id` is a **local** FK to `billing.invoice`. `gateway_transaction_ref` is unique within this example's assumed scope; real systems must verify whether the gateway code is unique **per provider/tenant**.

### 6.3. Illustration: Catalog Updates Must Not Mutate Order Snapshots

~~~~sql
INSERT INTO catalog.product
    (product_id, sku, display_name, current_list_price, publication_status)
VALUES
    ('00000000-0000-0000-0000-000000000101',
     'NOTE-A5', 'A5 Notebook', 100000, 'ACTIVE');

INSERT INTO sales.sales_order
    (order_id, buyer_external_ref, submitted_at, order_status)
VALUES
    ('00000000-0000-0000-0000-000000000201',
     '00000000-0000-0000-0000-000000000301',
     TIMESTAMPTZ '2026-10-01 09:00:00+07',
     'SUBMITTED');

INSERT INTO sales.order_line
    (order_line_id, order_id, line_no, catalog_product_ref,
     product_name_at_purchase, quantity, accepted_unit_price)
VALUES
    ('00000000-0000-0000-0000-000000000202',
     '00000000-0000-0000-0000-000000000201',
     1,
     '00000000-0000-0000-0000-000000000101',
     'A5 Notebook', 2, 90000);

-- Later, Catalog updates the product currently on sale.
UPDATE catalog.product
SET display_name = 'A5 Hardcover Notebook',
    current_list_price = 120000
WHERE sku = 'NOTE-A5';

SELECT
    c.display_name AS current_catalog_name,
    c.current_list_price,
    l.product_name_at_purchase,
    l.accepted_unit_price
FROM sales.order_line AS l
JOIN catalog.product AS c
    ON c.product_id = l.catalog_product_ref
WHERE l.line_no = 1;
~~~~

Illustrative output:

| current_catalog_name | current_list_price | product_name_at_purchase | accepted_unit_price |
| --- | ---: | --- | ---: |
| A5 Hardcover Notebook | 120000 | A5 Notebook | 90000 |

The **cross-schema JOIN SELECT is solely for illustration and comparison in a test database**; it is not a contract Sales is permitted to depend on when running independently. In a product with separate databases, both parties will need an approved API/projection or data-reading workflow.

**Do not assume 90000 is automatically valid:** this is an **example order's accepted price**, perhaps due to a promotion, quote, or specific policy. A real system must validate pricing acceptance conditions. The key takeaway is that **Catalog.current_list_price should not overwrite Sales.accepted_unit_price**.

### 6.4. Inventory Must Enforce Invariants Where It Owns Them

When a reservation request arrives at Inventory, you should not let Sales read current stock and decrement quantities itself, because data can change concurrently.

A conditional update inside Inventory:

~~~~sql
-- Executed inside an Inventory transaction.
-- The values below illustrate a request to reserve 2 units.
INSERT INTO inventory.stock
    (warehouse_code, catalog_product_ref, on_hand_qty, reserved_qty)
VALUES
    ('WH-HN',
     '00000000-0000-0000-0000-000000000101',
     10, 0);

UPDATE inventory.stock
SET reserved_qty = reserved_qty + 2
WHERE warehouse_code = 'WH-HN'
  AND catalog_product_ref =
      '00000000-0000-0000-0000-000000000101'
  AND on_hand_qty - reserved_qty >= 2
RETURNING warehouse_code, catalog_product_ref,
          on_hand_qty, reserved_qty;
-- If enough stock is available: one row returned, reserved_qty = 2.
-- If insufficient: no rows returned.
~~~~

A conditional UPDATE like the one above protects the **availability check and reservation increment** on the locked/updated stock record inside the transaction. However, this is **not yet a complete reservation workflow**:

- Creating/updating `STOCK_RESERVATION` must be synchronized **within the same transaction**.
- Idempotency on `source_request_id` is required to handle resent messages.
- Limits on reservation attempts, expiration, release/commit of stock, and impacts of inbound/outbound stock movements must be defined.
- **Reservation** must be distinguished from **actual stock issue** to avoid double-counting inventory.

These are invariants belonging to Inventory; they do not require a shared `UNIVERSAL_ORDER` table to be protected.

## 7. Integrate by Contract, Not by Internal Tables

Two contexts may need to exchange data without sharing an **entity type or SQL schema**. Contracts can take the form of:

1. **Synchronous API:** one party queries/commands and receives an immediate result, e.g., Sales asking Catalog to calculate a quote or Inventory to reserve stock.
2. **Asynchronous event:** one context announces **what has happened**, e.g., `OrderSubmitted` or `PaymentSettled`.
3. **Read model / projection:** one context stores data synchronized from elsewhere strictly to serve queries or decisions within an agreed scope.
4. **Files or batch exchange:** suited to certain partner integrations or reporting flows, still requiring a clear contract.

Choose the form based on **purpose, required consistency, acceptable latency, and error-handling capability**, not because a technology is trendy.

### 7.1. Synchronous API: Request/Response Is the Contract, Not Shared Database Access

Suppose Sales needs a valid price quote for a product. The logical contract might be:

~~~~text
GET QUOTE
Input:
  buyer_ref
  product_ref
  quantity
  requested_at

Output:
  quote_id
  accepted_eligible_product_ref
  quantity
  unit_price
  currency_code
  quote_version
  valid_until
  availability_or_eligibility_status
~~~~

A **quote** is a **business contract**, not necessarily a direct snapshot of `Catalog.current_list_price`. The actual price may depend on the customer, quantity, market, and time.

Sales uses this result according to policy:

- Verify the quote matches the **buyer, product, quantity, and currency**.
- Lock `accepted_unit_price` when the order qualifies.
- Respect `valid_until` or explicit price-locking rules.
- Handle cases where the API does not respond, returns an error, or the quote changes.

If Sales must read Catalog tables directly and know column structures and internal JOINs to compute quotes itself, boundaries start leaking. An owned API allows the provider to change how it stores data while preserving a **versioned contract**.

### 7.2. Events: Facts That Happened, Not Ambiguous Commands

An **integration event** should clearly express an occurrence within the owning context's scope:

- **OrderSubmitted:** the order has been recorded as submitted by Sales. Does not automatically mean paid.
- **InventoryReserved:** Inventory has reserved the quantity under warehouse rules.
- **PaymentSettled:** Billing has confirmed the payment under collection rules.
- **ShipmentDelivered:** Fulfillment confirms delivery under delivery rules.

Do not call everything **EntityUpdated** and force consumers to guess the business meaning from a dump of entity columns. In particular, **OrderSubmitted** does not mean **OrderConfirmed**; the two moments can be separated by stock reservation and payment collection.

An illustrative event contract:

~~~~json
{
  "eventId": "00000000-0000-0000-0000-000000000401",
  "eventType": "sales.order-submitted",
  "schemaVersion": 1,
  "aggregateId": "00000000-0000-0000-0000-000000000201",
  "occurredAt": "2026-10-01T02:00:00Z",
  "sourceContext": "sales",
  "payload": {
    "orderId": "00000000-0000-0000-0000-000000000201",
    "lines": [
      {
        "orderLineId": "00000000-0000-0000-0000-000000000202",
        "productRef": "00000000-0000-0000-0000-000000000101",
        "quantity": 2,
        "acceptedUnitPrice": {
          "amount": "90000.00",
          "currency": "VND"
        }
      }
    ]
  }
}
~~~~

**Elements to design before publishing:**

- **eventId** uniquely identifies each message so consumers can deduplicate.
- **aggregateId** indicates which object the event belongs to; it does not guarantee ordered broker delivery without a partition/ordering policy.
- **occurredAt** is the business timestamp of the event; the broker receipt time may differ.
- **schemaVersion** helps manage contract evolution.
- **amount + currency** avoids unitless monetary numbers; using decimal strings in JSON prevents precision loss in consumers using floating-point types.
- **payload** carries only data needed for the contract, without copying entire internal tables or sensitive personal data.

An Inventory consumer might only need `orderLineId`, `productRef`, `quantity`, and warehouse parameters; copying `acceptedUnitPrice` into the payload **does not automatically grant** Inventory the right to modify prices or treat price as its own source of truth. If pricing is not needed, an event contract dedicated to stock reservation can omit it.

### 7.3. Events Differ from Commands

A **command** usually expresses a **request for action**:

~~~~text
ReserveStock(
  request_id,
  order_line_ref,
  product_ref,
  warehouse_ref,
  quantity
)
~~~~

An **event** expresses a **fact already recorded by the owning context**:

~~~~text
StockReserved(
  reservation_id,
  request_id,
  order_line_ref,
  quantity,
  reserved_at
)
~~~~

A past-tense event name alone does not prove business correctness; the state must already be committed according to Inventory rules. Never emit a `StockReserved` event **before the reservation transaction succeeds** and hope consumers treat stock as guaranteed.

### 7.4. Synchronous or Asynchronous?

| Criterion | Synchronous API | Asynchronous Event/Message |
| --- | --- | --- |
| Interaction | Caller waits for result within a single request | Publisher does not wait for all consumers to process |
| Best suited for | Needing an immediate decision at the moment of action | Broadcasting events, updating projections, long-running workflows |
| Availability coupling | Callee generally must be reachable at call time | Can reduce temporal coupling if broker and storage are designed properly |
| Failure modes | Timeouts, retries, circuit breakers, failed responses | Delays, redelivery, out-of-order delivery, dead-lettering, processing failures |
| Consistency level | Sees the result of the invoked operation, but does not automatically provide distributed transactions | Typically eventually consistent across contexts |
| Safeguards needed | Quotas, timeouts, idempotent requests, contracts | Event IDs, replay, ordering, idempotent handlers, outbox/inbox |

There is no single choice for every business flow. You may use a synchronous API to validate a quote before checkout, and asynchronous events to notify Billing/Fulfillment after Sales records a valid state.

### 7.5. Anti-Corruption Layer (ACL): Translating Meaning During Integration

An **anti-corruption layer** is a translation layer between an **external contract** and an **internal model** to prevent another vendor's or context's model from leaking directly into local business code.

For example, suppose Sales receives a response from a Catalog provider:

~~~~json
{
  "item_code": "NOTE-A5",
  "title": "A5 Notebook",
  "list_price_minor": 100000,
  "sellable": true
}
~~~~

Suppose **list_price_minor** in this contract represents **the smallest currency unit of VND**, and pricing policy confirms VND has no fractional sub-units in the channel under consideration. Sales must translate that content into its own **ProductQuote**:

~~~~text
External catalog.item_code
    → Sales.CatalogProductRef (governed mapping)

External sellable
    → Input signal for offer eligibility
      (not necessarily sufficient to finalize an order)

External list_price_minor
    → Reference list price per currency unit contract
      (not yet accepted_unit_price)
~~~~

An ACL must handle **semantics, units, nulls, versions, value domains, and errors**, not merely rename JSON fields. If one party uses "customer" for the **billing account** and the other uses it for the **buyer**, copying the entire object directly does not produce the same meaning.

### 7.6. Java: Separate Domain Types Between Two Contexts

Two contexts can define distinct ID types both backed by UUID but with different domain names:

~~~~java
// Illustrative code; each part lives in its corresponding context package.
package catalog.domain;

import java.util.UUID;

public record ProductId(UUID value) {
    public ProductId {
        java.util.Objects.requireNonNull(value);
    }
}
~~~~

~~~~java
package sales.domain;

import java.util.UUID;

public record CatalogProductRef(UUID value) {
    public CatalogProductRef {
        java.util.Objects.requireNonNull(value);
    }
}

public record OrderId(UUID value) {
    public OrderId {
        java.util.Objects.requireNonNull(value);
    }
}
~~~~

**Java note:** The two `public record` declarations in the second snippet illustrate **two separate source files in the same package**, not syntax to paste into a single `.java` file. The goal is to show that Sales uses **CatalogProductRef** without having to import the entire **CatalogProduct entity**.

Instead of making Sales depend directly on a **CatalogProductJpaEntity** with internal fields and annotations, define a contract:

~~~~java
// Package sales.application.port
import java.math.BigDecimal;
import java.time.Instant;

record PriceQuote(
    CatalogProductRef productRef,
    BigDecimal unitPrice,
    String currencyCode,
    String quoteId,
    Instant validUntil
) {}

interface PricingPort {
    PriceQuote quoteFor(
        CatalogProductRef productRef,
        int quantity
    );
}
~~~~

**Sales** owns `PricingPort` according to its needs; the integration adapter performs the call to Catalog and maps the result to `PriceQuote`. If Catalog changes its storage technology or internal fields while keeping a compatible contract, Sales does not have to rewrite its entire domain.

In real implementations, you must check **quote validity, currency, version, buyer context, pricing race conditions**, and access boundaries. Type safety helps reduce identifier-mixing bugs, but it does not replace business checks at transaction time.

## 8. Local Transactions and Cross-Context Eventual Consistency

### 8.1. Why One SQL Transaction Cannot Span Every Context

If Sales, Inventory, and Billing use separate databases, a `BEGIN/COMMIT` transaction in Sales **does not** atomically commit stock reservations and payments in other databases.

For example:

1. Sales writes the order in the `SUBMITTED` state.
2. Inventory reserves stock successfully.
3. Billing payment collection fails.

If Sales updates to `CONFIRMED` right at step 1, users may see a "confirmed" order that does not yet meet business conditions. The design must have **intermediate states** and transition rules driven by trusted events.

An illustrative process state diagram:

~~~~mermaid
stateDiagram-v2
    [*] --> SUBMITTED
    SUBMITTED --> STOCK_HELD: StockReserved
    SUBMITTED --> CANCELLED: StockRejected / timeout policy
    STOCK_HELD --> CONFIRMED: PaymentSettled
    STOCK_HELD --> CANCELLING: PaymentFailed / timeout policy
    CANCELLING --> CANCELLED: StockReleased / resolution
    CONFIRMED --> [*]
    CANCELLED --> [*]
~~~~

This is **one hypothetical policy**. If the business collects payment only after delivery or allows backorders, the state machine will differ. What matters is that **each event and transition condition has clear meaning**, rather than using one shared `status` column written arbitrarily by multiple services.

### 8.2. Sagas and Compensating Actions

A **saga** coordinates multiple local transactions into a long-running workflow with **next steps** and appropriate **compensating actions** when failures occur. In our example:

~~~~text
Sales.SubmitOrder
    → Inventory.ReserveStock
    → Billing.CollectPayment
    → Sales.ConfirmOrder

If Billing fails after stock was already held:
    → Inventory.ReleaseReservation
    → Sales.CancelOrder
~~~~

**Compensating a transaction is not necessarily an exact SQL rollback to the previous state.** Some real-world actions cannot simply be undone: a parcel has already shipped, funds have settled, an invoice has been issued. They require **business-meaningful compensating events or workflows** (refunds, credit memos, product recalls), not deleting rows across databases.

### 8.3. Eventual Consistency Does Not Mean Local Invariants May Be Violated

In the window between events, Sales may not yet know that Inventory has finished reserving stock. The projection status in Sales can **lag** and must expose freshness or a pending state.

However, the invariant **reserved_qty ≤ on_hand_qty** must be protected by Inventory immediately inside its own reservation transaction. **Eventual consistency across contexts** is not a license to **write negative stock in Inventory** and hope a background job fixes it later.

### 8.4. Do Cross-Context Queries Need Immediate Consistency?

A dashboard showing:

~~~~text
Order status: Submitted
Stock status: Reserved
Payment status: Pending
Shipment status: Not created
~~~~

can be completely valid at a point in time between steps. If stakeholders demand "all columns must change at the exact same time", you must determine whether that is:

- **A true transactional invariant** requiring design within a suitable write boundary, or
- **A consistent display requirement** achievable via a projection with progress states, versions, and acceptable lag.

Do not introduce distributed transactions merely because multiple UI labels appear on the same page.

## 9. Transactional Outbox and Inbox: Keeping Contracts Reliable Across Systems

Asynchronous events raise the question: **What if the database update succeeds, but publishing the event fails?** Or conversely, if publishing succeeds but the process crashes before marking the event as sent, the event may be emitted again.

### 9.1. The Dual-Write Problem of Data and Messages

A failure-prone approach:

~~~~text
1. COMMIT Sales.order_status = CONFIRMED.
2. Publish OrderConfirmed to the broker.

If the process crashes between 1 and 2:
    The order is CONFIRMED in Sales
    but Billing/Fulfillment never hears about the event.
~~~~

Reversing the order to send the event before COMMIT also has problems: consumers may process an event whose corresponding state **later fails to commit**. There is no built-in atomic transaction guarantee between PostgreSQL and an independent message broker.

### 9.2. Transactional Outbox

A **transactional outbox** persists an intended event record **in the same database transaction** as the business state change. A separate relay process reads the outbox and delivers events to the broker.

~~~~mermaid
sequenceDiagram
    participant S as Sales
    participant D as Sales DB
    participant R as Outbox Relay
    participant M as Message Broker
    participant I as Inventory Consumer
    S->>D: BEGIN
    S->>D: UPDATE SalesOrder + INSERT OutboxEvent
    S->>D: COMMIT
    R->>D: Read unpublished outbox
    R->>M: Publish event
    M-->>R: Ack (per broker)
    R->>D: Mark published status
    M->>I: Deliver event
    I->>I: Check eventId / handle idempotently
~~~~

**Core guarantee on the Sales side:** The state change and outbox record commit/rollback together. However, this **does not automatically guarantee exactly-once event delivery across all systems**. If the relay publishes successfully and crashes before marking it published, it may republish the event.

### 9.3. PostgreSQL DDL for Sales Outbox

Continuing the schema in Section 6:

~~~~sql
CREATE TABLE sales.outbox_event (
    event_id UUID PRIMARY KEY,
    aggregate_ref UUID NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    schema_version INTEGER NOT NULL CHECK (schema_version > 0),
    occurred_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    published_at TIMESTAMPTZ
);

CREATE INDEX ix_sales_outbox_pending
    ON sales.outbox_event (occurred_at, event_id)
    WHERE published_at IS NULL;
~~~~

Example of **a state transition validated as eligible by the Sales workflow** paired with an outbox insert in the same transaction:

~~~~sql
BEGIN;

WITH changed AS (
    UPDATE sales.sales_order
    SET order_status = 'CONFIRMED'
    WHERE order_id =
        '00000000-0000-0000-0000-000000000201'
      AND order_status = 'SUBMITTED'
    RETURNING order_id
)
INSERT INTO sales.outbox_event
    (event_id, aggregate_ref, event_type,
     schema_version, occurred_at, payload)
SELECT
    '00000000-0000-0000-0000-000000000402',
    order_id,
    'sales.order-confirmed',
    1,
    CURRENT_TIMESTAMP,
    jsonb_build_object('orderId', order_id::TEXT)
FROM changed;

COMMIT;
~~~~

If the UPDATE changes no rows, the `changed` CTE is empty and the outbox INSERT **creates no event**. If the outbox INSERT fails, the transaction rolls back both the UPDATE and the INSERT. This illustrates atomicity **within the Sales DB**.

**Mandatory scope limitation to note explicitly:** This SQL only checks `order_status = SUBMITTED`; it **does not by itself verify** that `StockReserved` and `PaymentSettled` have been received. In a real implementation, logic validating business preconditions must be integrated before transitioning to `CONFIRMED`, along with race-condition protection and late-message handling. **Do not mistake this SQL snippet for a complete order-confirmation workflow.**

### 9.4. Inbox and Consumer Idempotency

A consumer may receive **the same eventId multiple times** due to retries or broker redelivery. If it increments `reserved_qty` on every receipt, stock could be reserved twice.

An **inbox** records processed messages in the receiver's database:

~~~~sql
CREATE TABLE inventory.inbox_message (
    consumer_name VARCHAR(80) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~~

Sample processing flow **within one Inventory transaction**:

~~~~text
BEGIN;

1. Attempt INSERT (consumer_name, event_id) into inventory.inbox_message.
2. If record already exists:
     verify this is a replay of an already-processed message;
     do not increment reserved_qty again.
3. If new:
     validate payload and expected state;
     update stock conditionally if sufficient;
     create reservation tied to unique request_id;
     write Inventory result and outbox if needed.
4. COMMIT everything or ROLLBACK everything on error.
~~~~

Checking `eventId` and updating state **must happen within the same valid transaction boundary**. If you write to the inbox and COMMIT first, then attempt to reserve stock, a subsequent failure leaves a "processed" marker even though the work never completed. Never treat the inbox as an ad-hoc log table written outside the state transaction.

**Idempotency by eventId** protects against re-processing the same message. However, if upstream sends **two different eventIds for the same business request**, the consumer still needs a **business idempotency key** such as `source_request_id`. You must determine whether `request_id` uniqueness is scoped per tenant/source if it is not globally unique.

### 9.5. Ordering, Versions, and Replay

A context might emit:

~~~~text
OrderSubmitted(version=1)
OrderCancelled(version=2)
~~~~

If a consumer receives the cancellation before the submission due to out-of-order delivery, or receives a stale replay of the submission long after cancellation, it must not unconditionally revert the state back to `SUBMITTED`.

Contracts and handlers may need:

- **Aggregate version** or another way to determine state version.
- Rules for **stale, duplicate, and missing** events.
- **Partition/ordering** policies per aggregate when the broker supports and requires them.
- **Replay** rules to rebuild projections without triggering new side effects.
- Feedback, investigation, or reconciliation mechanisms when encountering invalid event sequences.

Do not claim "the broker guarantees strict ordering" without explicitly specifying **ordering scope**, partition keys, and delivery semantics. These conditions belong to integration contracts and implementation, not to a universal table.

### 9.6. What Outbox/Inbox Solves and What It Does Not

| Capability | Supported by Outbox/Inbox | Not Automatically Guaranteed |
| --- | --- | --- |
| DB update + persisting event intent | Same transaction on producer side | Immediate broker delivery to all consumers |
| Relay retries | Can republish after failure | Exactly-once publishing |
| Consumer eventId deduplication | Using inbox PK + proper transaction | Two different eventIds with the same business meaning |
| Processing traceability | Event ID, aggregate ID, timestamp, logs | Correct business outcome if handler logic has bugs |
| Separating Sales/Inventory models | Contracts and ID references | Turning cross-context invariants into a single ACID transaction |

**Section takeaway:** Designing by context requires embracing **realistic integration protocols**. Splitting tables without designing message reliability merely trades "schema coupling" bugs for "integration failure" bugs.

## 10. Versioned Contracts and Independent Change

A primary reason to separate models by context is to allow **internal** changes without forcing everyone to change at once. That only works if integration contracts are also managed responsibly.

### 10.1. Distinguish Internal Table Versions from Contract Versions

Catalog might split its `PRODUCT` table into `PRODUCT`, `PRODUCT_TRANSLATION`, and `PRICE_POLICY`. As long as the quote API or `PublishedProduct` event preserves contract semantics, Sales does not need to know Catalog refactored its internal schema.

Conversely, if Sales directly imports **CatalogProductEntity** or reads internal columns, renaming a single column in Catalog breaks Sales. **Coupling via shared models** defeats the purpose of bounded context separation.

### 10.2. Contract Changes to Classify

| Change | Risk |
| --- | --- |
| Adding an optional field that consumers can ignore | Usually compatible, but must verify real consumers |
| Renaming or removing a required field | Can break consumers |
| Changing `amount` meaning from VND to minor units | **Semantically breaking** even if field name and numeric type are unchanged |
| Changing `OrderConfirmed` from "stock held" to "delivered" | Business-breaking; requires clear event naming and contracts |
| Changing `customer_id` from global scope to tenant-scoped | Can cause misattributed identities or bad deduplication |
| Adding a new enum status | Consumers using `switch` without a fallback branch may crash or misbehave |
| Allowing NULL in a previously non-null field | Can break consumer code assuming non-null |
| Changing timezone or source of `occurredAt` | Can corrupt reports or timeout handling |

Do not check only whether a JSON/Avro/Protobuf schema change is "backward-compatible" according to tooling; **semantic compatibility** is what users and business processes depend on.

### 10.3. Expand–Migrate–Contract on Contracts

When changing `productRef` to a `ProductReference` containing `tenantId` and `productId`, a risk-reducing plan is:

1. **Expand:** Provide the new structure alongside the old structure, or publish a new contract version. Explicitly state how long the old fields remain valid.
2. **Migrate:** Producers and consumers progressively deploy adapters capable of reading both versions or converting cleanly; reconcile IDs per tenant.
3. **Contract:** Remove the old field/version only after relevant consumers have migrated and replay/backfill plans handle historical events.

Never silently mutate an existing payload under the same `eventType`/`schemaVersion` and hope every consumer figures it out.

### 10.4. Contract Tests and Ownership

A contract can be verified through:

- **Producer contract tests:** emitted data conforms to the published schema and constraints.
- **Consumer-driven tests:** consumers verify that the parts they actually rely on remain supported.
- **Mapping/ACL tests:** source fields map to internal meaning with the right units, scope, and history.
- **Compatibility tests:** old-version consumers handle newly compatible messages as planned.
- **Negative tests:** missing fields, new enum values, wrong currency, mismatched tenant IDs, late events, duplicate events.

The deliverable does not have to be a single shared Java DTO library. You can use **language-agnostic schema contracts**, API documentation, payload examples, and contract test suites; each context maps them into **its own internal model**.

## 11. Personal Data, Authorization, and Cross-Context Copies

Separating models not only reduces technical coupling but also enforces the principle of **taking only what is needed**:

- Identity may need authentication credentials or profile information.
- Sales may need `buyer_ref` and a **delivery address snapshot** for a specific order.
- Fulfillment may need recipient name/phone/address to deliver the parcel, without needing login credentials.
- Billing may need invoicing details; it should not automatically receive full browsing history and profile data.

When publishing events, apply **data minimization**: include only fields required by the contract. Do not turn an "OrderSubmitted" event into a dump of every customer column, address, payment method, and sensitive attribute, as doing so spreads sensitive data to all consumers.

### 11.1. Copies Do Not Automatically Grant Ownership

Sales may maintain a read copy of customer names for display; it must specify:

- **Which source is authoritative** for the current name.
- Whether data is updated via event or API and **how much lag** is acceptable.
- When an **immutable snapshot** is required for a transaction, versus a regularly refreshed copy.
- Workflows to edit/delete data according to privacy policies, mandatory retention rules, and applicable legal requirements.

You cannot infer that every copy must be deleted immediately or kept forever: policies depend on law, contracts, and business retention purposes. **Ownership boundaries and data lineage** make those decisions explicit.

### 11.2. Security Does Not Stop at Splitting Databases

Even when each context has its own DB, an overly broad service token allowed to call every API or an event topic broadcasting full PII still creates risk. You must govern:

- Role- and purpose-based access permissions for APIs, commands, and events.
- Local database read/write permissions and migration deployment accounts.
- Sensitive data classification, encryption, and appropriate access audit logs.
- Who is permitted to hold copies, retention periods, and policy-compliant rectification/erasure requests.

These decisions are part of **integration design and data governance**, and cannot be solved merely by renaming tables.

## 12. Integrated Read and Analytical Models Differ from Shared Write Models

An organization still needs reports such as:

- A list of purchased orders, payments, delivery status, and remaining stock.
- Revenue by product and customer segment.
- Late delivery rates and return rates by category.
- Amounts paid where goods have not yet shipped.

You should not conclude that those reports require **a single global operational schema writable by every context**.

### 12.1. Read Models / Projections with Clear Purpose

A read model serving an order-management screen might look like:

~~~~text
ORDER_OVERVIEW_READ_MODEL(
  sales_order_ref,
  submitted_at,
  sales_status,
  payment_summary_status,
  inventory_reservation_status,
  fulfillment_summary_status,
  last_synced_at,
  source_versions
)
~~~~

It is built from published/authorized information:

~~~~mermaid
flowchart LR
    S["Sales events"] --> P["Order Overview Projection"]
    B["Billing events"] --> P
    I["Inventory events"] --> P
    F["Fulfillment events"] --> P
    P --> UI["Order tracking page"]
~~~~

This model **is not the source of truth for payments or inventory**. It is a **lag-tolerant read copy**, annotated with provenance, versions, and update timestamps so users understand its freshness.

When a `PaymentSettled` event arrives late, the projection may not yet show the newly completed payment; if an event is replayed, the handler must be idempotent so it does not double-count amounts. These are properties of an integrated read model, not a reason to move payment write authority into the summary table.

### 12.2. CQRS Does Not Equal Microservices

**Command Query Responsibility Segregation (CQRS)** separates the need to **write to enforce invariants** from **reading tailored to query patterns**. It does not mandate two physical databases or event sourcing.

In our example:

- The Sales **write model** protects orders and locked prices.
- The Inventory **write model** protects stock/reservations.
- The Order Overview **read model** combines statuses for fast UI queries.

A monolith can still design **clearly bounded write models** and **aggregated read projections**. Never create independent services solely because you used the term CQRS.

### 12.3. Conformed Dimensions for Cross-Context Analytics

For analytical reporting, you can build a **shared dimension layer** to standardize:

- Product IDs, category classifications, and taxonomy history.
- Dates aligned to the chosen timezone or fiscal calendar.
- Customer identifiers authorized for analytics.
- Currencies and exchange-rate rules.

Then create separate fact tables:

~~~~text
FACT_SALES_LINE
FACT_PAYMENT
FACT_SHIPMENT
FACT_RETURN_LINE

DIM_DATE
DIM_PRODUCT
DIM_CUSTOMER_ANALYTICS
~~~~

A **conformed dimension** model serves **comparison and querying**; it does not negate that Sales, Billing, and Fulfillment maintain separate write models. Fact tables can also have **different grains**, so each fact must be aggregated to a common analytical grain before joining to avoid fanout.

A shared analytical dimension can be the result of **governed data mapping**, rather than proof that every operational context must share one `CatalogProduct` entity.

### 12.4. Integrated Read Models Do Not Automatically Guarantee Immediate Consistency

A reporting table may record `PaymentSettled` before receiving `OrderConfirmed` due to differing latencies. Therefore you need to:

1. Specify **authoritative source events and fields**.
2. Track **version, occurredAt/processedAt, or offset** when necessary.
3. Define **freshness** SLAs and incomplete-data states.
4. Provide mechanisms to **rebuild/replay** projections or reconcile against sources.
5. Control access permissions and sensitive data within aggregated copies.

Never use a projection as a source to write back into Inventory or Billing unless a dedicated, valid command workflow has been designed.

## 13. Context Mapping: Collaboration Relationships Can Vary

Not every pair of contexts exchanges data under the same relationship style. A context map clarifies **who defines the contract and who must adapt**.

### 13.1. Upstream and Downstream

An **upstream** context publishes data or capabilities consumed by a **downstream** context. For instance, Catalog can be upstream for certain product details; Sales is downstream of the quote API. However, this direction **can reverse per integration flow**: Sales publishes `OrderConfirmed` for Billing to consume.

Do not label a service "always upstream" across the entire enterprise; evaluate **each specific contract**.

### 13.2. Common Relationship Patterns

| Relationship Type | Idea | When to Consider |
| --- | --- | --- |
| **Partnership** | Two teams jointly design/deliver an integration toward a shared goal | Two contexts depend on coordinated release schedules or shared workflows |
| **Customer–Supplier** | Provider considers the contract needs of downstream consumers | An upstream has clearly identified downstream consumers |
| **Conformist** | Downstream adopts the provider's model when it has no influence | Integrating with third-party systems unlikely to change |
| **Anti-Corruption Layer** | Downstream translates external model into local language | Two contexts differ in terminology, units, and invariants |
| **Open Host Service / Published Language** | Upstream publishes a stable, documented, versioned API/protocol | Many consumers require consistent integration |
| **Shared Kernel** | Two teams intentionally share a **small** jointly owned model/contract | Concepts truly share identical meaning, rarely change, and have joint governance |
| **Separate Ways** | No direct integration because cost outweighs benefit | Data does not need synchronization or independent solutions suffice |

These are **decision-making tools**, not a checklist of patterns you must implement everywhere. **Shared Kernel** does not mean building a giant domain library containing all of Catalog, Sales, and Inventory. When used, its scope must be **narrow, genuinely consistent, and governed by change coordination**.

### 13.3. When Should You Use an Anti-Corruption Layer?

Suppose a payment partner reports status **APPROVED**, whereas in the company's Billing context "settled" is recognized only at status **SETTLED**. If you map `APPROVED → Paid` directly, the business might treat an authorization hold as collected revenue before settlement occurs.

The ACL must distinguish:

~~~~text
Provider.APPROVED → Billing.PaymentAuthorized
Provider.SETTLED  → Billing.PaymentSettled
Provider.DECLINED → Billing.PaymentFailed
~~~~

Changes to provider status names can be absorbed inside the adapter, rather than forcing all of Sales and Fulfillment to learn the payment vendor's terminology. **Preventing semantic corruption** matters more than renaming JSON keys to look pretty.

## 14. When to Split and When Not To

Separating models by context brings benefits as well as **communication and consistency costs**. Never invoke "DDD" as an excuse to spin up dozens of databases and message topics for a small problem.

### 14.1. Signals to Split Models

| Signal | Reason |
| --- | --- |
| Same noun has different meanings/keys/lifecycles | A single shared entity causes invariant conflicts |
| Multiple teams need to change independently | A shared schema becomes a migration bottleneck |
| Different data ownership | Must clarify who may write and who may only read |
| Business processes have distinct phases and states | Should not force every process into one `status` |
| Historical snapshots are required | Current updates in one context must not overwrite past data in another |
| External sources/partners have different semantics | ACL prevents external models from leaking deep into internal domains |
| Different reliability, privacy, and retention policies | Data requires separate access/retention boundaries |

### 14.2. Signals to Consider Keeping a Shared Boundary

If two concepts:

- Are always created/modified within the **same mandatory atomic transaction**.
- Share the same owner, the same language, and the same rate of change.
- Offer no clear independent benefit when split.
- Splitting them would force core operations into unnecessary network calls and compensations.

then they likely belong to **the same bounded context or the same aggregate**. For example, `SalesOrder` and `SalesOrderLine` typically live together in the Sales model; if an order line **cannot exist independently**, splitting them into two separate database services creates pointless overhead.

### 14.3. Bad Boundaries at Both Extremes

**Too few boundaries:** An 80-column `UniversalCustomer` written to by Identity, Marketing, Billing, and Sales; a tiny migration waits on every team.

**Too many boundaries:** A small app splits out one service to sum order lines, another to check quantities, and another to store individual attributes, requiring multiple network calls just to create one order.

Sound design **clusters invariants that need strong consistency**, separates models with distinct semantics and ownership, and integrates them via appropriate contracts. Do not measure design quality by **microservice count**.

### 14.4. Quick Decision Table

| Question | If "Yes" | Design Direction |
| --- | --- | --- |
| Do two teams have different definitions for the same name? | Yes | Split domain types/contexts and create mappings |
| Must two tables always update atomically? | Yes | Consider keeping them in the same transaction boundary |
| Does another party only need a few attributes for reading? | Yes | Published API/event or projection; avoid sharing entities |
| Does a step need an immediate answer before finalizing? | Yes | Synchronous API/command with clear timeouts and error handling |
| Can the outcome arrive later but needs broadcasting? | Yes | Events + outbox/inbox/idempotency |
| Is the data for cross-source reporting? | Yes | Read model / analytics layer respecting grain and conformed dimensions |
| Do multiple consumers depend on the payload? | Yes | Contract governance, versioning, and compatibility tests |
| Are identifiers unique only per tenant? | Yes | Carry scope in business keys and contracts |

## 15. Roadmap for Migrating from a Shared Model to Context-Specific Models

A running system may have a `UNIVERSAL_ORDER` table used directly by multiple applications. You do not need to **split everything in one shot**; you can migrate incrementally to reduce data risk.

### Step 1 — Discover Semantics and Write Permissions

- Inventory which teams/APIs/jobs read and write the shared table.
- Document what **each column means to each team**.
- Identify invariants and who holds authority over pricing, stock, billing, and shipping.
- Find fields being overwritten by multiple teams or overloaded with mismatched statuses.

### Step 2 — Draw the Context Map and Define the First Contract

- Delineate Catalog, Sales, Inventory, Billing, Fulfillment, or appropriate real-world boundaries.
- Pick **one low-risk, high-value flow** to extract first—for example, having Sales read Catalog via a quote API instead of reading product tables directly.
- Document contracts, identifiers, units, statuses, versions, and error handling.

### Step 3 — Protect the New Model with Adapters

- Place an API or ACL between consumers and the legacy shared model.
- Prevent new modules from writing directly to the shared table.
- Write tests against production-like data and counterexamples.
- Use telemetry to verify which read/write paths have migrated.

### Step 4 — Split Data Ownership Incrementally

- Gradually move columns/relations into schemas or databases owned by their respective contexts.
- Design business IDs, local IDs, mappings, and retain necessary history.
- If synchronization is needed during transition, define a **single source of truth per attribute**. Never allow both old and new tables to accept arbitrary bidirectional writes without conflict rules.
- Choose verifiable events/CDC/projections when read copies are needed across contexts.

### Step 5 — Run in Parallel, Reconcile, and Shift Traffic

For example, have old Sales and new Sales both feed an **experimental revenue projection**. Compare:

- Order/line counts, locked prices, currencies, and period totals.
- Late, cancelled, modified, and refunded transactions.
- Discontinued products that still appear in historical orders.
- Tenant-mismatched codes and unresolvable source references.

**Reconciliation is not just comparing COUNT:** Two datasets with the same row count but different locked prices or statuses are still wrong.

### Step 6 — Retire Legacy Contracts/Tables on Schedule

- Remove old write paths only after producers and consumers have migrated.
- Monitor event replay, in-flight backlogs, and backfills.
- Announce deprecation dates for legacy APIs/schemas, historical reporting handling, and access rules.
- Never delete data required for retention just because the legacy schema is no longer the primary write source.

### Risks to Track in the Plan

| Risk | Mitigation |
| --- | --- |
| Non-atomic dual writes | Outbox / verifiable sync flows instead of assuming two commits succeed together |
| Unstable source codes | Versioned business IDs/mappings and explicit scope rules |
| Inability to reconstruct history | Define source boundaries and snapshot policies clearly |
| Both sides editing the same data | Assign a single owner; route updates via contracted commands |
| Producer changes payload before consumers migrate | Expand–migrate–contract and contract tests |
| Redelivered or out-of-order events | Idempotency, versioning/ordering, and reconciliation |
| Over-exposed data permissions | ACLs, payload minimization, access controls, and lineage audits |

This is **a suggested roadmap**. Depending on risk, an organization can start with a modular monolith and split deployments later, without jumping straight to microservices or full event-driven architecture.

## 16. Checklist for Validating Data Boundary Design

Before a team declares that it has separated models by bounded context, verify:

1. **Language and scope:** Each context has a mission statement, terminology, and rules that do not contradict themselves within that context.
2. **Ownership:** Every critical business state has a single source of truth and a party responsible for writing/updating it.
3. **No entity mixing:** Differently defined Order, Product, or Customer concepts are not forced into one global class/table just because they share a name.
4. **Invariants and transactions:** Rules that must hold immediately sit inside a transaction boundary that can enforce them; cross-context rules have explicit consistency protocols and intermediate states.
5. **Keys:** Distinguish local PKs, business IDs, external references, and tenant/source scope. Never use display labels or emails as default linking keys.
6. **FKs:** Internal FKs protect local data; any cross-context FK is a deliberate coupling trade-off, not an arbitrary read/write shortcut.
7. **Snapshots:** Prices, addresses, names, or statuses that must be preserved at transaction time are stored with the right semantics and not overwritten by current source updates when history must be kept.
8. **APIs:** Synchronous contracts answer the consumer's exact question, with defined handling for timeouts, errors, and validity conditions.
9. **Events/commands:** Names and payloads accurately represent facts that occurred or actions requested; do not equate "order submitted" with "payment collected".
10. **Versioning:** Contracts have versions and evolution plans; currency units or enum meanings are never changed silently.
11. **ACLs:** External models are translated into local types and semantics; domain code does not depend directly on another context's tables or ORM entities.
12. **Delivery reliability:** Transaction + outbox on the publisher side; idempotency/inbox on the consumer side where needed; handling for retries, late arrivals, and reordering.
13. **Business idempotency:** The same business request arriving under two different `eventId`s does not produce duplicate unwanted side effects.
14. **Sagas:** State transitions, timeouts, compensating actions, and handling for irreversible side effects are explicitly defined.
15. **Read models:** Cross-source reports and projections have clear owners, defined lag, data provenance, and reconciliation; read models never become competing write sources.
16. **Permissions and privacy:** Exchange only necessary data, and govern permissions and retention periods per policy.
17. **Testing:** Tests cover individual invariants, producer/consumer contracts, duplicate/error/lost-message scenarios, and cross-context reconciliation.
18. **Independent change:** One context can evolve its internal schema without requiring consumers to change, provided published contracts remain intact.
19. **Operational limits:** Latency, resilience, and integration overhead are evaluated; do not split physically just for a clean diagram.
20. **Migration plan:** Legacy read/write paths are retired step by step, with no two parties writing the same attribute without conflict rules.

### Matrix: "Which Deliverable Proves Which Boundary?"

| Deliverable | Question Verified |
| --- | --- |
| **Context map** | Which scopes have distinct meanings and who communicates with whom? |
| **Per-context models** | Which entities, keys, invariants, and lifecycles does each context own? |
| **Data ownership matrix** | Where is the source of truth for each field/status? |
| **Integration contracts** | What are the names, versions, schemas, units, and meanings of APIs, commands, and events? |
| **ACL/mapping specification** | By what rules are external values translated into internal models? |
| **Consistency workflow** | How are pending states, failures, timeouts, compensations, and event ordering handled? |
| **Reliability tests** | Do retries, deduplication, replay, outbox/inbox, and conflict handling work properly? |
| **Read-model contract** | Where are projections updated from, and how are lag and lineage interpreted? |
| **Migration plan** | Can we safely transition step by step from a shared schema to independent ownership? |

## 17. Practice Exercises with Answers

### Exercise 1 — Should "Customer" Be One Global Table?

Identity stores login accounts, Sales stores order buyers and shipping addresses, and Billing stores the corporate entities responsible for payment. An architect proposes a single shared `CUSTOMER` table containing login email, shipping address, tax ID, payment history, and marketing status.

**Question:** What is wrong with this proposal? What needs clarification before merging?

**Answer:** Those pieces of data have **different meanings, ownership, history rules, and access requirements**. You need to clarify whether the **identity user, buyer, recipient, and bill-to party** are the same business entity or merely linked by mapping relationships. Shared identifiers/contracts can be used where linkage is genuinely required, but all fields and write permissions should not be forced into a single `CUSTOMER` table if the contexts are independent.

### Exercise 2 — Current Price vs. Locked Order Price

Catalog currently lists P01 at 120,000 VND. Order O100 bought P01 last week at an accepted price of 90,000 VND. A Catalog name/price sync job plans to UPDATE all `SalesOrderLine` rows for P01 to 120,000.

**Question:** Should it do this?

**Answer:** No, if `accepted_unit_price` is **the price of a finalized transaction**. Sales must preserve accepted prices under its own rules; a current list price change in Catalog is not an event that modifies old orders. You can use `current_list_price` for current display and `accepted_unit_price` for history, with clear ownership.

### Exercise 3 — Should Inventory Let Sales Directly UPDATE?

Sales wants to decrement `reserved_qty` in Inventory after a customer clicks buy. The Sales team asks for DB permissions to UPDATE `inventory.stock` directly to save an API round-trip.

**Question:** What are the risks and alternatives?

**Answer:** Sales would bypass ownership boundaries, potentially break reservation invariants, and fail to handle multi-warehouse coordination, retries, or reservation expirations. Instead, send a **ReserveStock command/API** with a stable `request_id`; Inventory checks availability and updates `stock`/`reservation` inside its local transaction, returning the contracted result. Inside a monolith, that call can still be an **in-process module call** rather than a network hop.

### Exercise 4 — Local FK or Cross-Context FK?

Sales has `SalesOrder` and `SalesOrderLine`. `SalesOrderLine.order_id` points to `SalesOrder.order_id`. `SalesOrderLine.catalog_product_ref` points to the product ID in Catalog.

**Question:** Which FK should the Sales DB enforce directly? Must every external reference be a SQL FK?

**Answer:** The FK from **OrderLine to Order** lies inside Sales, so the Sales DB can enforce it directly. `catalog_product_ref` is a **cross-context reference**; if Catalog has its own DB, a standard SQL FK cannot point to it. Offer eligibility must be verified through a contract/API or designed synchronization mechanism; snapshots preserve history.

### Exercise 5 — Does Bounded Context Mean Microservice?

A Java monolith has `Catalog`, `Sales`, and `Inventory` packages with explicit module interfaces; each module manages tables in its own schema and does not read/write another module's data except through internal APIs.

**Question:** Can these be considered bounded contexts despite running in one process?

**Answer:** **Yes**, if each scope has clear language, invariants, models, and ownership. Bounded context is a **semantic and modeling** boundary, not necessarily a process boundary. Splitting deployments is simply a later deployment option.

### Exercise 6 — Avoid One Shared Status Enum

The system proposes `enum UniversalOrderStatus = NEW, PAID, PACKING, DELIVERED, RETURNED` so Sales, Billing, and Fulfillment all write to one field.

**Question:** What is wrong with this?

**Answer:** An order can be **paid while currently being packed**, or **delivered while partially refunded**. One enum cannot simultaneously describe independent processes without losing information or creating hundreds of combinations. Keep **SalesStatus, PaymentStatus, and ShipmentStatus** in their respective owning contexts; an overview projection computes display state using explicitly named rules.

### Exercise 7 — Distinguish Events from Commands

The Inventory team receives a message named `InventoryReserved`, yet the payload actually contains a request saying "please reserve 2 items".

**Question:** Is the name appropriate? How should it be changed?

**Answer:** No. **InventoryReserved** sounds like an accomplished fact. The request should be **ReserveStock** with a `request_id`; only after Inventory successfully commits the reservation should it emit **StockReserved**. If reservation fails, emit **StockReservationRejected** or a failure response with clear semantics.

### Exercise 8 — Synchronous API vs. Asynchronous Events

Sales needs to know whether a quote is still valid **before finalizing checkout**, whereas an overview dashboard only needs to update shipping status a few seconds after an event occurs.

**Question:** Which integration style fits each need?

**Answer:** The quote check fits a **synchronous API/command** with timeouts, error handling, and validity checks; shipping status for the overview page can use **asynchronous events and a projection** if latency is acceptable. Both still require contracts and proper retry/idempotency handling.

### Exercise 9 — Event Published Successfully but Not Marked Published

The relay reads the outbox, publishes `OrderConfirmed` successfully, and crashes before updating `published_at`. After restarting, the relay emits the same event again.

**Question:** Does this prove the outbox pattern is broken? What should the consumer do?

**Answer:** This is an **expected redelivery scenario** in the outbox design, not a reason to abandon outbox. The consumer uses **eventId/inbox** and idempotent processing so side effects are not applied twice. A business idempotency key is also needed if the same request is emitted under two different `eventId`s.

### Exercise 10 — Writing Inbox First and Processing Later

A consumer receives an event, INSERTs into the inbox, and COMMITs; afterward it increments `reserved_qty`. The process crashes in between.

**Question:** What is wrong and how do you fix it?

**Answer:** The inbox recorded "processed" even though stock was never updated; subsequent redeliveries may be ignored. You must record the inbox entry and apply local state changes **within the same transaction**, COMMITting together after processing succeeds; any failure must ROLLBACK both.

### Exercise 11 — Invariants and Eventual Consistency

Sales shows "awaiting stock reservation" for 3 seconds after `OrderSubmitted`, while Inventory has not yet confirmed `StockReserved`.

**Question:** Is the data already wrong? Which invariant must hold immediately?

**Answer:** This can be a valid **pending state** if the contract allows eventual consistency. However, inside Inventory, the invariant **never reserve beyond available stock** must still be enforced immediately when processing the reservation. Sales must not transition to `CONFIRMED` on its own if business rules require reserved stock without a valid confirmation.

### Exercise 12 — Compensation After Payment Failure

Inventory successfully reserves stock, then Billing returns `PaymentFailed`. Sales needs to cancel the order.

**Question:** Does simply rolling back the Sales transaction release the reserved stock?

**Answer:** No. Inventory already COMMITted its own transaction. The saga workflow must request Inventory to **ReleaseReservation** and handle responses, timeouts, or retries; afterward Sales records the appropriate status. Compensation is a **business action**, not a SQL rollback across multiple databases.

### Exercise 13 — Consumer Misinterprets Payment Status

A payment gateway emits `APPROVED` when a card is authorized, and `SETTLED` when funds settle. Billing uses `PAID` for the `SETTLED` state. A mapper converts `APPROVED` directly into `PAID`.

**Question:** What kind of error is this and where should checks be placed?

**Answer:** This is a **contract semantic error**. The ACL in Billing must translate `APPROVED` to `PaymentAuthorized` and `SETTLED` to `PaymentSettled` according to verified rules. Contract tests covering provider statuses help prevent a vendor change from turning into incorrect payment behavior.

### Exercise 14 — Changing Payload While Keeping Name/Version

Previously, a producer emitted `amount = "90000.00"` in VND. After an upgrade, the producer keeps the exact same `eventType`/`schemaVersion` but changes `amount` to **90000 minor units of another currency**, without adding a `currency` field.

**Question:** Is this compatible?

**Answer:** No. Having the same JSON string/number type does not mean having the same semantics. Changing **currency units** is breaking; you must publish a new contract or follow an explicit migration process, include `amount + currency`, and test consumers rather than changing silently.

### Exercise 15 — Using a Read Model as a Write Source

`OrderOverviewProjection` has a `payment_status` column updated by Billing events. A team wants to edit this column directly to "mark payment collected", assuming Billing will automatically catch up.

**Question:** Should they do this?

**Answer:** No. A projection is a **derived, potentially lagging read copy**; Billing owns settlement logic. To collect payment, send a **command to Billing** subject to proper permissions and rules. Editing the projection directly causes displayed data to diverge from the source of truth.

### Exercise 16 — Sharing Data for Reporting Does Not Mean One Shared Write Table

Reports need revenue, collected amounts, and successful delivery rates by date and product. The BI team proposes forcing Sales, Billing, and Fulfillment to share and UPDATE a single `FACT_GLOBAL` table.

**Question:** Is a shared write model necessary?

**Answer:** No. You can keep **separate write facts/events** per Sales, Billing, and Fulfillment and build an **integrated analytical model** with conformed dimensions. You must define the grain, event date, currency, and aggregation method for each fact before comparing to avoid fanout, and never turn `FACT_GLOBAL` into a competing write source.

### Exercise 17 — Tenant-Scoped Keys

Two tenants both have `product_code = NOTE-A5`, representing two different products. Sales sends only `productCode = NOTE-A5` to Inventory.

**Question:** What is the risk and how should the contract be updated?

**Answer:** Inventory could look up the wrong tenant's stock. The contract must carry **tenantId and productId/productCode with explicit identifier scope**, or a truly globally unique system ID. Never use display labels or local SKUs as cross-context identifiers without scope.

### Exercise 18 — When Should You Not Split Further?

`SalesOrder` and `SalesOrderLine` are always updated atomically. Order lines have no independent lifecycle; deleting a draft order must delete its draft lines. One team proposes two separate microservices, feeding each order line through a message broker.

**Question:** Should they split?

**Answer:** There is no compelling reason to split. These are very likely **entities within the same Sales context/aggregate**; splitting adds network, synchronization, and error-handling overhead for an invariant that needs a shared transaction. Prefer a local model with PK/FK and atomic transactions, splitting only for concrete business and operational reasons.

### Exercise 19 — Does Shared Kernel Mean Sharing Every Entity?

Two teams share an immutable `CountryCode` class, and also want to put `Order`, `Payment`, `Stock`, and `User` into a single `domain-common` package.

**Question:** Which part should be accepted and under what conditions?

**Answer:** A value object or term with **truly identical meaning**, low churn, and joint governance can be a small shared kernel. Never turn `domain-common` into **a model of the entire business**. If `Order`/`Payment`/`Stock` have distinct invariants and lifecycles, keep them in their owning contexts and integrate via contracts.

### Exercise 20 — Planning an Incremental Exit from a Shared Table

Three applications concurrently edit `UNIVERSAL_PRODUCT`. The team wants Catalog to own product info, Sales to keep snapshots, and Inventory to own stock—without any system downtime.

**Question:** Outline prioritized steps and acceptance evidence.

**Suggested answer:**

1. Inventory **read/write paths**, column meanings per team, and ownership rules.
2. Publish the context map, IDs, API/events, and consumer ACLs.
3. Block new cross-context writes; transition each team to **a single authoritative write source**.
4. Build Sales snapshots and Inventory stock in their own scopes, with synchronization/migration plans.
5. Reconcile **quantities, locked prices, stock, late events, and error cases**, not just `COUNT`.
6. Shift traffic incrementally while preserving legacy contracts during the compatibility window.
7. Retire legacy tables/access rights **after** consumers have migrated and historical data is handled per policy.

There is no requirement to immediately spin up five microservices; you can start with a **modular monolith**, enforcing clear contracts and ownership before any physical split.

## 18. Summary

| Concept | Key Takeaway |
| --- | --- |
| **Bounded context** | Boundary within which a model, terminology, and invariants have consistent meaning |
| **One word, multiple meanings** | Product/Order/Customer can be distinct models across different contexts |
| **Data ownership** | One party is responsible for a business state; others use contracts or read copies |
| **Local PK/FK** | Protects entities and relationships **inside** the owning context |
| **External reference** | Links identity via contract; not automatically a cross-system FK |
| **Snapshot** | Preserves transaction-time data rather than auto-updating to current state |
| **Synchronous API** | Queries/commands for immediate results; requires timeout and error handling |
| **Integration event** | Announces a fact that occurred, with `eventId`, version, timestamp, and meaningful payload |
| **Command** | Requests an action; does not assume the action has succeeded |
| **ACL** | Translates external models into local language/domain types to prevent conceptual pollution |
| **Eventual consistency** | Cross-context read copies may lag; local invariants must still hold |
| **Saga** | Coordinates local transactions with forward steps and business-level compensations |
| **Transactional outbox** | Saves state and event-publishing intent in the same local transaction |
| **Inbox/idempotency** | Handles redelivered events without repeating side effects |
| **Contract versioning** | Governs both schema compatibility and **semantic compatibility** |
| **Read model/CQRS** | Serves combined queries without becoming a competing write source |
| **Conformed dimension** | Aligns analytical dimensions in the read layer without forcing one shared write model |
| **Shared Kernel** | Share only parts with truly identical meaning, narrow scope, and joint governance |
| **Migration** | Shifts ownership incrementally, reconciles data, and retires legacy contracts in a controlled way |

**Conclusion:** Designing context-specific data models is not abandoning integration; it is **making integration meaningful with explicit contracts**. Catalog defines products offered for sale, Sales owns orders and locked prices, Inventory protects stock and reservations, Billing protects invoices and funds, and Fulfillment protects delivery execution. Each context needs independent keys, invariants, and write authority within its proper scope. Relationships are expressed through **IDs, APIs, commands, events, ACLs, read models, and consistency workflows** rather than forcing the entire system to share one entity or one giant operational table. When these boundaries are proven through testing, reconciliation, and contract governance, the system can **evolve piece by piece while keeping data and business rules verifiable**.
