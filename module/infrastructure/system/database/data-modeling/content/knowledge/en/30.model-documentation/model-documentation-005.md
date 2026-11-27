# Consistent Naming Conventions While Preserving Business Language

## Learning Objectives

After this lesson, you can:

- Distinguish **business names** from **technical implementation names**, and understand why following a casing style alone does not mean a data model is semantically clear.
- Build a **glossary** with definitions, scope, authoritative source, and owner within each **bounded context**.
- Name **entities, relationships, keys, states, timestamps, currencies, transaction snapshots, facts/dimensions, APIs, and integration events** clearly.
- Spot generic names such as **customer, status, amount, date, value, data** that risk obscuring grain and business invariants.
- Design consistent physical conventions for PostgreSQL while preserving accurate domain language when representing data across relational, document, graph, and analytics models.
- Perform controlled renames via **expand – migrate – contract**, protecting active APIs, events, caches, ETL pipelines, and consumers.
- Build checklists, data dictionaries, and tests that prove field names accurately express real data.

This lesson belongs to the **Model Documentation** chapter in **DATABASE_DATA_MODELING**. This module builds skills in turning business requirements into entities, relationships, constraints, normalization, keys, indexes, and physical schemas; while comparing relational, document, graph, and analytical models to choose structures that are easy to evolve and verify. **Naming conventions are part of the model contract**, not merely aesthetic rules for source code.

> **Principle:** standardize how names are written, but **do not force different business concepts to share the same word** just to look uniform.

## 1. Syntactically Consistent Names Can Still Be Semantically Wrong

A legacy sales system has three tables:

~~~text
customer:
  id, status, updated_at

order:
  id, customer_id, amount, date

payment:
  id, order_id, amount, date
~~~

The naming style is short and uniform, yet the reader still does not know:

- Is **customer** a person, a CRM profile, a login account, a buyer, or a recipient?
- Is **status** account status, identity verification status, or eligibility to place an order?
- Is **order.amount** the confirmed item subtotal, an amount including fees and taxes, or the actually collected amount?
- Is **payment.amount** the intended charge, a successful capture, or a refund?
- Is **date** the creation date, confirmation date, payment date, message receipt date, or pipeline load date?
- Is **id** globally unique across the entire system, or only within a tenant or a single source system?

A syntactically valid query can still return **wrong revenue** because it sums amounts at the wrong stage or wrong grain. Renaming **amount** to **order_amount** is a small improvement; only when there is a definition stating **which value at which point in time** it actually represents can users trust it.

An example with clearer, purposeful names:

~~~text
sales.orders:
  tenant_id
  order_id
  buyer_account_id
  order_state_code
  confirmed_at
  confirmed_items_amount
  currency_code

billing.payment_captures:
  tenant_id
  capture_id
  order_id
  capture_state_code
  captured_at
  captured_amount
  currency_code
~~~

Readers can see that **a confirmed order** is distinct from **a payment capture**. Even so, they still need a data dictionary to know whether **confirmed_items_amount** includes tax, shipping, or order-level discounts.

### 1.1. Two Distinct Layers of Consistency

| Layer | What does it check? | Example |
| --- | --- | --- |
| **Syntactic** | Casing, abbreviations, singular/plural, suffixes | PostgreSQL lowercase snake_case; timestamps end with _at |
| **Semantic** | Does a name match the measured fact in the right context? | captured_amount is not order_value |
| **Grain and identity** | What does one row represent? Where is the ID unique? | One capture_id identifies one capture |
| **Time and unit** | When and in what unit of measure? | price_at_confirmation, currency_code |
| **Ownership** | Who determines the value and serves it to consumers? | Payment determines successful captures |

Casing naming conventions only protect the first row. The remaining rows require clarifying business meaning, constraints, and tests.

## 2. Ubiquitous Language: Choosing Terms Together with Domain Experts

**Ubiquitous language** is the vocabulary agreed upon and shared by business and engineering within a specific scope. Scope matters greatly: the same word in two bounded contexts can carry two valid yet different meanings.

| Term | Context | Possible intended meaning | Do not assume identical to |
| --- | --- | --- | --- |
| **Customer** | CRM | Customer relationship profile | Login Account |
| **Buyer account** | Sales | Account authorized to place orders | Recipient |
| **Payer** | Payment | Party fulfilling the payment obligation | Buyer |
| **Recipient** | Fulfillment | Person receiving a shipment | Account owner |
| **Product** | Catalog | Published product group/description | Specific SKU |
| **Product variant** | Inventory | Variant sold or stocked individually | Product group |
| **Order** | Sales | A purchase order in the Sales lifecycle | Payment/Invoice |
| **Invoice** | Billing | Accounting/billing document with issuance rules | Copy of an order |
| **Shipment** | Logistics | A parcel/delivery batch with its own tracking ID and state | An order |
| **Revenue** | Finance | Metric recognized under financial policy | Total confirmed orders |

Do not create a single global **customers** table and force every domain to reference it as an identical object. One person may have multiple accounts; the payer may differ from the buyer; the recipient may be a third party.

### 2.1. From Business Statements to Entities and Relationships

The warehouse manager says:

> "One order can be split into three parcels. Each parcel has a tracking number. A parcel can have multiple delivery attempts."

Concepts needed:

- **Order**: a purchase order.
- **Shipment**: a parcel/delivery batch, relationship Order 1:N Shipment.
- **DeliveryAttempt**: a delivery attempt, relationship Shipment 1:N DeliveryAttempt.
- **TrackingNumber**: tracking number issued by the carrier, which may require the carrier to form a unique identifier.
- **DeliveredAt**: successful delivery timestamp, distinct from **ShippedAt** and **LastAttemptedAt**.

If there is only **orders.delivery_date**, the model cannot represent delivery attempts and multiple parcels. **Good naming does not replace relationship design**; it exposes gaps when turning requirements into a model.

### 2.2. Clarify Before Creating a Metric

Business stakeholders ask for "daily new customers." The name **new_customer_count** is not enough because "new" could mean:

- Newly registered account.
- CRM profile appearing for the first time.
- Buyer with their first confirmed order.
- Buyer with their first successful payment.
- A customer merged from two source profiles today.

You can use **registered_account_count** or **first_confirmed_order_buyer_count**, with source, filter states, and timestamp documented. Do not let an old metric keep its name while the BI team silently changes its definition.

## 3. Glossary: Every Important Name Must Have a Findable Definition

A **glossary per bounded context** should include:

| Documentation field | Purpose |
| --- | --- |
| **Vietnamese term** | Term business users actually use |
| **Technical term** | Canonical name in code/schema |
| **Bounded context** | Sales, Billing, Inventory, Fulfillment... |
| **Definition and exclusions** | What is included and what is excluded |
| **Grain** | Which fact a row or value represents |
| **Business/natural key** | Identifier and uniqueness scope |
| **Authority/owner** | System or team with authority to decide |
| **Time/unit** | Event time, snapshot, currency, unit |
| **Data classification** | PII, internal, public, access permissions |
| **Alias/legacy name** | Old name and compatibility window |
| **Version and decision** | Who approved and when meaning changed |

Example glossary entry (illustrative, not written into the lesson YAML):

~~~yaml
term_vi: "Tiền hàng đã xác nhận (Confirmed items amount)"
technical_name: confirmed_items_amount
context: Sales.Order
definition: >
  Net total of order lines at confirmation time,
  after allocating discounts down to lines.
grain: "One order within one tenant"
unit: "Currency unit specified in currency_code"
event_time: confirmed_at
source_of_truth: Sales.Order
excluded:
  - "Shipping fees"
  - "Taxes not yet modeled in this measure"
  - "Payment captures and post-confirmation refunds"
owner: "Sales Team"
~~~

The name **confirmed_items_amount** hints at the meaning, but **the formula and exclusions** are what tell users whether this is the metric they need.

### 3.1. Canonical Terms and Aliases

A legacy system calls the buyer by three names: **client**, **customer**, **buyer**. The process is not a global find-and-replace:

1. List where each name is used and who its consumers are.
2. Verify whether they truly refer to one object or only similar ones.
3. Choose the canonical term **within the context** based on an approved definition.
4. Record legacy aliases in the glossary and provide temporary mapping during migration.
5. Stop creating unnecessary new synonyms.
6. Remove an alias only when no consumers remain and no historical trace is lost.

**Aliases exist for transition, not as an excuse to permanently keep conflicting terms.**

## 4. From Business Language to Names Across Layers

~~~text
User says: "Order is confirmed"

Conceptual:
  Order / OrderConfirmation

Logical:
  Order --contains--> OrderLine
  Order --may be fulfilled by--> Shipment

Physical relational:
  sales.orders, sales.order_lines
  fulfillment.shipments

Java:
  Order, OrderLine, OrderConfirmed

API:
  orderId, confirmedAt, confirmedItemsTotal

Integration event:
  OrderConfirmed, eventId, occurredAt, schemaVersion
~~~

**Do not force every layer to use the same casing style.** Ensure that when two names represent **the same fact**, the mapping preserves semantics. When they represent **two different facts**, they must have two different names.

### 4.1. An Illustrative Set of Conventions

| Object | Convention | Example |
| --- | --- | --- |
| PostgreSQL schema | Domain/context name, lowercase | sales, billing, fulfillment |
| Relational table | Plural, snake_case | orders, order_lines |
| Column | lowercase snake_case | confirmed_at, buyer_account_id |
| Primary key constraint | pk_ + table name | pk_orders |
| Foreign key constraint | fk_ + source + target | fk_order_lines_order |
| Unique constraint | uq_ + grain/condition | uq_capture_source_id |
| Check constraint | ck_ + invariant | ck_order_lines_quantity |
| Index | ix_ + table + target | ix_orders_tenant_confirmed_at |
| Java class/record | PascalCase, singular | Order, OrderLine |
| Java field | camelCase | confirmedAt |
| JSON field | camelCase per contract | orderId, currencyCode |
| Integration event | Past-tense event | OrderConfirmed |
| Analytics fact | fact_ + grain/event | fact_order_line_confirmed |
| Dimension | dim_ + entity/version | dim_product_variant |
| Aggregate | agg_ + metric/grain | agg_confirmed_orders_daily |

These are examples, **not the only valid standard**. A project that has stabilized on singular table names or snake_case JSON can keep its existing convention if it is sufficiently consistent and documented. Do not organize a sweeping rename solely out of personal preference.

### 4.2. Vietnamese and English in the Model

A pragmatic choice in a Java/PostgreSQL environment:

- **Business terms and explanations in Vietnamese** so stakeholders can easily confirm meaning.
- **Technical identifiers in ASCII English**, for example buyer_account_id, shipment_id, confirmed_at.
- **A VI ↔ EN mapping table** in the glossary.
- Abbreviations only when defined and agreed upon, such as id, sku, api, utc.

Avoid mixing **ma_don**, **order_id**, and **idOrder** in the same schema without reason. At the same time, **do not call a recipient a customer** just because you want the whole system to use the same word.

### 4.3. Names That Need Review

- **data**, **info**, **value**, **object**, **type**, **flag** standing alone.
- **status** when there are multiple workflows.
- **date** when there are multiple timestamps.
- **amount** when there are multiple monetary concepts.
- **id1**, **id2**, **ref_no**, **val** without context.
- **new_orders**, **old_customer**, **tmp_v2** lingering long after migration.
- Non-standard abbreviations such as **cust**, **amt**, **prc**, **dt**.

A long name is not automatically good. A name like **on_time_delivered_shipment_count** is long because it must distinguish parcels delivered on time from orders whose parcels were all delivered on time. When a name exceeds DB limits, keep the core meaning and link to the data dictionary; do not shorten it arbitrarily to **cnt1**.

### 4.4. PostgreSQL Identifier Specifics

PostgreSQL folds unquoted identifiers to lowercase. Using quoted MixedCase forces code to preserve exact casing and double quotes in many places. **lowercase snake_case** usually creates less friction.

Common PostgreSQL builds enforce a **63-byte** identifier limit and truncate overly long names. Choose index and constraint names that are both concise and clear, and verify limits in your actual environment. Avoid names colliding with reserved SQL keywords, names prone to collision in the same schema, and conventions tied to auto-generated ORM names.

## 5. Entity and Relationship Names Must Reflect the Right Grain

A table named **payments** does not say on its own whether each row is a payment intent, payment attempt, capture, or refund. They have different lifecycles and relationships.

| Name | Valid grain when used | Suggested key/relationship |
| --- | --- | --- |
| catalog_products | One product group | product_id |
| product_variants | One variant/SKU | variant_id, product_id |
| inventory_balances | One variant at one warehouse at a closed snapshot | (warehouse_id, variant_id) |
| orders | One order belonging to a tenant | (tenant_id, order_id) |
| order_lines | One confirmed order line | (tenant_id, order_id, line_no) |
| payment_attempts | One payment attempt | attempt_id |
| payment_captures | One payment capture | capture_id |
| shipments | One parcel/delivery batch | shipment_id, order_id |
| delivery_attempts | One delivery attempt | attempt_id, shipment_id |

If **product_id** previously meant SKU and now means **product group**, you cannot update all historical order lines to the group ID and lose color/size. **A name change that changes grain must be treated as a model change**, not just string replacement.

### 5.1. Many-to-Many Table Names Must Pick the Right Level

One order line can receive two promotions. The table **order_line_promotions** has grain **(tenant, order, line, promotion)**. If you use **order_promotions**, readers may mistakenly think a promotion applies to the whole order.

If the table also stores **allocated_discount_amount**, there must be a rule that the sum allocated to the line equals the true discount share. Do not JOIN the bridge table and SUM line amounts to get "revenue by promotion" when a line appears twice, unless a clear allocation/counting contract exists.

### 5.2. Do Not Fix Cardinality by Renaming a Column

Initially Orders has a **shipment_id** column because each order has one shipment. Later an order has multiple shipments; the right fix is modeling **Order 1:N Shipment**, not merely renaming the column to **shipment_ids** and stuffing a list into one relational column. Names must evolve together with entities and constraints.

## 6. Key Naming: Distinguishing Physical, Public, and External Source IDs

| Name | Specific meaning |
| --- | --- |
| **order_pk** | Internal row key if a separate surrogate is used |
| **order_id** | Order identifier within the defined scope |
| **public_order_id** | Identifier published through APIs/events |
| **order_number** | Display code, possibly issued per tenant/year |
| **buyer_account_id** | Account placing the order |
| **source_system** | External system issuing the identifier |
| **source_order_id** | ID at the source, unique only within the declared source scope |
| **processor_capture_id** | Capture ID issued by the payment processor |
| **tracking_number** | Shipment tracking number; check carrier scope |

A system may choose order_id itself as the public UUID, in which case public_order_id is unnecessary. **Do not create multiple IDs just for a template**; split only when source, scope, or lifecycle differs.

**A UUID does not grant access permission.** A caller who knows orderId must still prove authorization to view the object by tenant and owner. Otherwise, a hard-to-guess public identifier can still leak via logs or URLs.

### 6.1. Composite Keys and Tenants

An order_id may be unique only within a tenant. In that case the business key is **(tenant_id, order_id)**; FKs from order lines should carry both columns to prevent cross-tenant references. A field name alone does not express full scope, so **constraints and the data dictionary** must protect it.

If an ID from a partner can be reused across years, UNIQUE(source_order_id) is wrong. You must include **source_system, tenant, or effective period** depending on the source contract.

## 7. Time: Suffixes Must Express Meaning

| Name | Represented value | Suggested type |
| --- | --- | --- |
| **created_at** | When the record was created in the storage system | TIMESTAMPTZ |
| **confirmed_at** | When the order was confirmed | TIMESTAMPTZ |
| **captured_at** | When capture succeeded according to Payment | TIMESTAMPTZ |
| **shipped_at** | When the parcel was handed over to the carrier | TIMESTAMPTZ |
| **delivered_at** | When the parcel was successfully delivered | TIMESTAMPTZ |
| **observed_at** | When a sensor measured at the source | TIMESTAMPTZ |
| **received_at** | When the system received the message | TIMESTAMPTZ |
| **loaded_at** | When ETL loaded the warehouse | TIMESTAMPTZ |
| **business_date** | Business date by timezone and rules | DATE |
| **effective_from / effective_to** | Validity interval of a dimension version | TIMESTAMPTZ or DATE per contract |
| **processing_duration_ms** | Processing duration, not a timestamp | BIGINT/NUMERIC |

**created_at is not synonymous with occurred_at.** An old order imported today has **confirmed_at** from last month and **loaded_at** today. An event has **observed_at** at 23:59 UTC and **received_at** at 00:04 UTC the next day; reporting by occurrence date must not use the receipt date.

For **business_date**, you must specify whose timezone applies. One absolute instant can fall on two different calendar dates in two timezones.

### 7.1. Transaction-Time Snapshots vs. Current Values

- **current_list_price**: current catalog list price.
- **unit_price_at_confirmation**: price locked on the line at confirmation.
- **shipping_address_at_confirmation**: address accepted at confirmation.
- **current_default_address**: current default address.
- **customer_segment_at_purchase**: customer segment at purchase time.
- **current_customer_segment**: current segment.

These fields do not need to be "synchronized to match." When Catalog changes a price, **unit_price_at_confirmation** on historical documents preserves its historical meaning. When a customer changes their default address, do not automatically rewrite the recipient of an already handed-over shipment.

### 7.2. NULL, Effective Intervals, and End Times

A **delivered_at = NULL** field can represent "not yet delivered" by contract, rather than simultaneously representing UNKNOWN and FAILED. When distinction is needed, use explicit states and rules.

For SCD Type 2, use half-open intervals **[effective_from, effective_to)**. A version is valid at from but not at to; avoid closed BETWEEN bounds that cause an event on the boundary timestamp to match two versions.

## 8. Money, Quantities, Ratios, and Aggregation

| Name | Grain/meaning | Avoid confusing with |
| --- | --- | --- |
| **unit_price_at_confirmation** | Locked unit price on the line | current_list_price |
| **line_gross_amount** | Line total before discount | Order total |
| **line_discount_amount** | Discount allocated down to the line | Unallocated order-level discount |
| **line_net_amount** | Line net amount after discount | Collected amount |
| **confirmed_items_amount** | Total item amount on one confirmed order | Captured amount / revenue |
| **captured_amount** | Collected amount at one-capture grain | Payment attempt amount |
| **refunded_amount** | Refunded amount at one-refund grain | Original order value |
| **on_hand_quantity** | Inventory on hand at snapshot time | Sum of inbound/outbound lines |
| **distinct_buyer_count** | Distinct buyers in the evaluated set | Sum of group distinct counts |
| **average_unit_price** | Total amount divided by total quantity | AVG of group AVGs |

A NUMERIC(18,2) column named **amount** without **currency_code** still risks summing VND with USD. For ratios such as **conversion_rate**, store numerator and denominator or aggregate appropriately; do not sum percentages. For gauges or inventory balances, do not SUM across time as you would transaction flows.

**Revenue** should only be used when the organization has clearly defined recognition rules. Do not treat every SUM(order.amount) as revenue.

### 8.1. Count Names Must Match What COUNT Counts

An Order has three OrderLines:

- **order_line_count = 3**.
- **distinct_order_count = 1**.
- **sold_unit_quantity** can equal the sum of quantity if units are compatible.

COUNT(*) after JOIN order_lines **counts lines**, not orders. Even if you alias it as **order_count**, the number is still wrong. You must fix the query or pre-aggregate, not just rename the alias.

### 8.2. Measures Must Express Units

Names like **distance_meters**, **duration_seconds**, **temperature_celsius**, **weight_kg**, **memory_bytes** help prevent unit confusion. If the system allows kg/box/piece, use **quantity + unit_code** or a documented conversion unit; do not call every quantity quantity_pieces.

## 9. States and Booleans: One Column Must Not Carry Multiple Lifecycles

An order can simultaneously have:

- **order_state_code = CONFIRMED**.
- **payment_state_code = PARTIALLY_CAPTURED**.
- **fulfillment_state_code = NOT_STARTED**.
- **fraud_review_state_code = APPROVED**.

Collapsing all of these into **status = PROCESSING** loses information and easily creates invalid states. Name states after the owner of each lifecycle, not after a convenient label in a single API response.

Boolean **is_active** is also frequently ambiguous: has the account verified email, is it unlocked, has it placed an order in 90 days, or does it have an active contract? You can use **email_verification_state**, **account_access_state**, and **last_order_at** if those are genuinely independent facts.

A name such as **is_delivered** derived from **delivered_at** or an authoritative event should not become a second independently updated source of truth. If a read projection is needed, document that it is derived, along with its owner and freshness.

## 10. PostgreSQL Example: Order Model with Consistent Names and Constraints

Assumptions:

- One row in **sales.orders** is a confirmed order within a tenant; afterward its current state may transition to CANCELLED.
- One row in **sales.order_lines** is an order line identified by **(tenant_id, order_id, line_no)**.
- **confirmed_items_amount** is the sum of **line_net_amount** across lines, after allocated discounts; this example excludes taxes and shipping fees.
- Each Order has a single **currency_code** across its lines. Buyer account is not synonymous with recipient.

~~~sql
CREATE SCHEMA sales;

CREATE TABLE sales.orders (
    tenant_id BIGINT NOT NULL,
    order_id UUID NOT NULL,
    buyer_account_id UUID NOT NULL,
    confirmed_at TIMESTAMPTZ NOT NULL,
    order_state_code TEXT NOT NULL,
    confirmed_items_amount NUMERIC(18, 2) NOT NULL,
    currency_code CHAR(3) NOT NULL,

    CONSTRAINT pk_orders
        PRIMARY KEY (tenant_id, order_id),
    CONSTRAINT ck_orders_state
        CHECK (order_state_code IN ('CONFIRMED', 'CANCELLED')),
    CONSTRAINT ck_orders_items_nonnegative
        CHECK (confirmed_items_amount >= 0)
);

CREATE TABLE sales.order_lines (
    tenant_id BIGINT NOT NULL,
    order_id UUID NOT NULL,
    line_no INTEGER NOT NULL,
    product_variant_id UUID NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price_at_confirmation NUMERIC(18, 2) NOT NULL,
    line_discount_amount NUMERIC(18, 2) NOT NULL,
    line_gross_amount NUMERIC(18, 2)
        GENERATED ALWAYS AS (
            quantity * unit_price_at_confirmation
        ) STORED,
    line_net_amount NUMERIC(18, 2)
        GENERATED ALWAYS AS (
            quantity * unit_price_at_confirmation
            - line_discount_amount
        ) STORED,

    CONSTRAINT pk_order_lines
        PRIMARY KEY (tenant_id, order_id, line_no),
    CONSTRAINT fk_order_lines_order
        FOREIGN KEY (tenant_id, order_id)
        REFERENCES sales.orders(tenant_id, order_id),
    CONSTRAINT ck_order_lines_line_no CHECK (line_no > 0),
    CONSTRAINT ck_order_lines_quantity CHECK (quantity > 0),
    CONSTRAINT ck_order_lines_price
        CHECK (unit_price_at_confirmation >= 0),
    CONSTRAINT ck_order_lines_discount_range
        CHECK (
            line_discount_amount >= 0
            AND line_discount_amount
              <= quantity * unit_price_at_confirmation
        )
);

CREATE INDEX ix_orders_tenant_confirmed_at
    ON sales.orders (tenant_id, confirmed_at DESC);

CREATE INDEX ix_order_lines_product_variant
    ON sales.order_lines (tenant_id, product_variant_id);
~~~

Design rationale:

- **sales** is the context that owns Order, not a generic schema like tables_v2.
- **orders** and **order_lines** separate grain.
- The FK including **tenant_id** enforces same-tenant linkage in the database.
- **buyer_account_id** is not mistaken for recipient.
- **unit_price_at_confirmation** is a snapshot, not current Catalog pricing.
- **line_gross_amount** and **line_net_amount** are derived values for **one line**, not the order total.
- **confirmed_items_amount** on the header has order grain; reconciling it against the sum of lines is a cross-row invariant, not automatically enforced by a CHECK on Orders.
- Constraint names indicate the cause of failure; index names indicate the intended queries.

**Limitations:** this example does not yet create buyer_accounts and product_variants tables, so those UUIDs must be verified by separate sources/contracts or additional FKs in a real system. Do not claim an FK is sufficient when a table from another context is not yet defined. PostgreSQL supports generated stored columns in appropriate versions; if using an older version or another engine, verify support.

### 10.1. Short Data Dictionary Alongside SQL

| Field | Definition | Owner and rules |
| --- | --- | --- |
| **tenant_id** | Enterprise/tenant scope | Scope of PK/FK |
| **order_id** | Stable order ID within tenant | Sales.Order |
| **buyer_account_id** | Account placing the order | Not the recipient |
| **confirmed_at** | Confirmation timestamp | Do not substitute loaded_at |
| **order_state_code** | Current state of Order | Approved enum set |
| **confirmed_items_amount** | Total confirmed item amount | Currency per currency_code, not collected cash |
| **product_variant_id** | Purchased product variant | Per Catalog identity |
| **unit_price_at_confirmation** | Locked historical price | Do not sync with current price |
| **line_discount_amount** | Discount allocated to the line | Must not exceed line_gross_amount |
| **line_net_amount** | Line gross minus discount | Does not automatically include tax/fees |

You can use **COMMENT ON** in PostgreSQL to keep descriptions close to the schema:

~~~sql
COMMENT ON COLUMN sales.orders.confirmed_items_amount IS
    'Total item amount at confirmation, after line discounts; excludes tax and shipping fees.';

COMMENT ON COLUMN sales.orders.buyer_account_id IS
    'Account placing the order; not synonymous with recipient.';

COMMENT ON COLUMN sales.order_lines.unit_price_at_confirmation IS
    'Unit price locked at confirmation; not updated from current Catalog.';
~~~

The example uses plain ASCII comments for compatibility with some older pipelines; a UTF-8 PostgreSQL environment can store accented Vietnamese normally. COMMENT does not replace a glossary with an owner, change history, and formulas.

### 10.2. Verifying Names and Grain with Queries

Query at **order grain**:

~~~sql
SELECT
    tenant_id,
    currency_code,
    COUNT(*) AS currently_confirmed_order_count,
    SUM(confirmed_items_amount) AS confirmed_items_amount
FROM sales.orders
WHERE order_state_code = 'CONFIRMED'
  AND confirmed_at >= $1::TIMESTAMPTZ
  AND confirmed_at <  $2::TIMESTAMPTZ
GROUP BY tenant_id, currency_code;
~~~

The name **currently_confirmed_order_count** highlights the filter: orders that were confirmed earlier but are **currently CANCELLED** are excluded. If you need to count **all orders confirmed during the period regardless of current state**, remove the state filter or use an event fact table and name the metric accordingly.

Query at **order-line grain**:

~~~sql
SELECT
    o.tenant_id,
    o.currency_code,
    COUNT(*) AS order_line_count,
    SUM(l.line_net_amount) AS confirmed_lines_net_amount
FROM sales.orders AS o
JOIN sales.order_lines AS l
  ON l.tenant_id = o.tenant_id
 AND l.order_id = o.order_id
WHERE o.confirmed_at >= $1::TIMESTAMPTZ
  AND o.confirmed_at <  $2::TIMESTAMPTZ
GROUP BY o.tenant_id, o.currency_code;
~~~

**Do not SUM(o.confirmed_items_amount) after joining lines**, because the header amount is repeated for each line. This rule is not fixed by simply renaming the COUNT(*) alias to order_count.

### 10.3. Reconciling Header and Line Semantics

~~~sql
WITH lines_by_order AS (
    SELECT
        tenant_id,
        order_id,
        COUNT(*) AS line_count,
        SUM(line_net_amount) AS lines_net_amount
    FROM sales.order_lines
    GROUP BY tenant_id, order_id
)
SELECT
    o.tenant_id,
    o.order_id,
    o.confirmed_items_amount,
    l.line_count,
    l.lines_net_amount
FROM sales.orders AS o
LEFT JOIN lines_by_order AS l
    ON l.tenant_id = o.tenant_id
   AND l.order_id = o.order_id
WHERE l.order_id IS NULL
   OR o.confirmed_items_amount
        IS DISTINCT FROM l.lines_net_amount;
~~~

This example assumes every order has at least one line and the header total equals the sum of line net amounts. If the real system has unallocated order-level discounts or header-level taxes/fees, you must **adjust the contract and reconciliation query**, rather than using an appealing name to hide a different formula.

A trustworthy name requires **an approved definition + correct grain + constraints/reconciliation + tests**, not just smooth readability.

## 11. Names in APIs and Events: Preserve Meaning, Do Not Leak Physical Structure

An order read API can expose:

~~~json
{
  "orderId": "550e8400-e29b-41d4-a716-446655440000",
  "status": "CONFIRMED",
  "confirmedAt": "2026-11-22T01:30:00Z",
  "confirmedItemsTotal": {
    "amount": "310000.00",
    "currency": "VND"
  }
}
~~~

Here **confirmedItemsTotal** corresponds to **confirmed_items_amount + currency_code** in the source. JSON uses camelCase while PostgreSQL uses snake_case; **the format differs, but the semantics must match**.

Several rules:

- **orderId** is the public identifier per contract; do not expose **order_pk** or physical FK keys if consumers do not need them.
- **status** in the API can be a mapped public state; do not expose every internal enum like PICKING or WAREHOUSE_RECHECK just because the source column contains them.
- **amount** is a decimal string in this example to preserve decimal digits; precision, scale, and rounding rules must be published.
- **confirmedAt** has an explicit timezone; do not substitute updated_at.
- Do not add **buyerAccountId, email, phone, or risk_score** merely because those columns exist in the source; verify consumer permissions and needs.

An API is **a contract with a longer lifecycle than SQL column names**. When storage changes to a document store, clients do not necessarily need to know if public names and meanings are preserved.

### 11.1. Event Names Based on What Happened

~~~json
{
  "eventId": "c3b26b87-594e-4a98-9ad2-52b8d2ddf04f",
  "eventType": "OrderConfirmed",
  "schemaVersion": 1,
  "orderId": "550e8400-e29b-41d4-a716-446655440000",
  "aggregateVersion": 4,
  "occurredAt": "2026-11-22T01:30:00Z"
}
~~~

The name **OrderConfirmed** states that the Order has reached the business confirmation milestone; it differs from **OrderUpdated**, which usually just signals that a row changed. Distinguish:

| Field | Definition |
| --- | --- |
| **eventId** | Unique event/message ID for deduplication |
| **eventType** | Name of the business action that occurred |
| **schemaVersion** | Event structure/contract version |
| **aggregateVersion** | State version of the source entity |
| **occurredAt** | Timestamp when the business action occurred |
| **publishedAt/receivedAt** | Infrastructure publish/receive timestamp, if needed |

**OrderConfirmed** does not mean Payment has successfully captured funds. The **PaymentCaptured** event belongs to the Payment domain when capture actually succeeds. An order can have multiple payments; do not emit an event named **OrderPaid** just because any single capture arrived if the full amount has not been paid.

Past-tense event names must be paired with reliable publishing mechanisms: do not emit a confirmation event before the transaction actually commits and then later rolls back. You can use a transactional outbox and idempotent consumers for asynchronous integration.

### 11.2. Cross-Bounded-Context Mappings Must Be Documented

~~~text
Sales.Order.buyerAccountId
    -> Billing.PaymentIntent.payerRef
    -> Fulfillment.Shipment.recipientRef
~~~

These are **IDs that may be linked through a workflow**, not proof that they are equal. The payer may differ from the buyer; the recipient may be a third party.

An **anti-corruption layer** translates concepts and checks business rules. If Payment splits **SETTLED** into finer-grained states, Sales should not blindly copy Payment enums into order_state_code without reviewing their meaning.

## 12. Naming in Document, Graph, Time-Series, and Analytics Models

A system can use multiple storage models. **Character casing conventions may vary**, but entity meaning and scope must remain consistent or have a documented mapping.

### 12.1. Document Model: Embedded Names Must Preserve Grain

An Order document:

~~~json
{
  "orderId": "550e8400-e29b-41d4-a716-446655440000",
  "confirmedAt": "2026-11-22T01:30:00Z",
  "currencyCode": "VND",
  "items": [
    {
      "lineNo": 1,
      "productVariantId": "d0b8cb27-84c2-4ca4-985d-33f1705bd6d3",
      "quantity": 2,
      "unitPriceAtConfirmation": "150000.00",
      "lineDiscountAmount": "10000.00"
    }
  ]
}
~~~

The document has **one-Order** grain, whereas each element in **items[]** has **one-order-line** grain. If you add **paymentAttempts[]** and **shipments[]**, do not assume every element shares the same event type or access permissions.

The name **unitPriceAtConfirmation** remains a snapshot even when the document is stored alongside other current fields. If the database uses a technical **_id** field, the API does not necessarily have to expose _id to clients.

### 12.2. Graph: Edge Verbs Must Describe Real Relationships

~~~text
(:BuyerAccount)-[:PLACED]->(:Order)
(:Order)-[:CONTAINS_LINE]->(:OrderLine)
(:Order)-[:FULFILLED_BY]->(:Shipment)
(:Shipment)-[:HAS_ATTEMPT]->(:DeliveryAttempt)
~~~

An edge label like **RELATED_TO** fails to express direction, subject, timing, and meaning. If you want to analyze **individual purchase events**, you cannot assume a single BuyerAccount–PURCHASED–Product edge captures every purchase when the same product is bought multiple times. You may need an **OrderLine** or **PurchaseEvent** node with appropriate ID/time and measures.

Graph edge names must also document cardinality, traversal direction, validity intervals, and permissions; renaming an edge can break consumer traversals.

### 12.3. Analytics: Fact/Dimension Names Must Include Grain

| Table | Grain | Key points to document |
| --- | --- | --- |
| **fact_order_line_confirmed** | One confirmed order line | line_net_amount has currency; Order can have many lines |
| **fact_payment_capture** | One capture | captured_amount is not confirmed_items_amount |
| **dim_product_variant** | One variant or one historical version | variant_key may be a dimension surrogate |
| **dim_customer_version** | One customer attribute version in validity window | effective_from/effective_to |
| **fact_inventory_eod** | One variant × warehouse × business_date | on_hand_quantity must not be summed across days |
| **agg_confirmed_orders_daily** | Day × currency × selected dimensions | metric, status filter, watermark |

Prefixes **fact_**, **dim_**, **agg_** are useful for a warehouse. Not every OLTP table needs these prefixes.

In SCD Type 2, **customer_key** can identify **one dimension version**, distinct from **customer_id** which identifies one business customer. If both are called customer_id, a JOIN can match multiple versions and artificially inflate revenue. The glossary must clearly document both key layers.

### 12.4. Time-Series: Statistic Names Must Specify the Type of Average

In telemetry:

- **observed_at**: timestamp measured by the device.
- **received_at**: timestamp received by the server.
- **bucket_start**: left bound of the bucket, with rule [start,end).
- **sample_count**: count of qualifying samples.
- **temperature_sum_celsius**: sum of sample temperatures in the chosen unit.
- **sample_mean_temperature_celsius**: mean weighted by sample count.
- **time_weighted_mean_temperature_celsius**: used only when the time-weighting calculation is properly designed.
- **max_temperature_celsius**: extremum within the interval, not duration above threshold.

The AVG of 5-minute bucket AVGs can be wrong if each bucket has a different sample count. Names must match the aggregation method: store **sum + count** if you need a sample-weighted hourly average.

## 13. Renaming Is a Contract Change, Not Just Find-and-Replace

A legacy Sales system has **customer_id**, which actually means the **buyer account** ID, not a real person or recipient ID. The team wants to rename it to **buyer_account_id**.

### 13.1. Questions Before Migration

- Are the two concepts strictly 1:1 in historical data?
- Was the legacy **customer_id** unique per tenant or system-wide?
- Which names are used by APIs, events, partner CSV exports, caches, and the data warehouse?
- Do ORMs, stored procedures, triggers, and reporting systems depend on the old name?
- How long must the legacy alias remain supported?
- Is any consumer reading customer_id while actually treating it as a **person** ID rather than an account ID?

**If the legacy customer_id represents a person while the new buyer_account_id represents an account, this is not an equivalent rename.** You must design the person–account relationship and a verifiable mapping first.

### 13.2. The Expand – Migrate – Contract Process

1. **Finalize glossary and ADR** for old/new names, scope, and source of truth.
2. **Expand**: add the new column or compatibility view/DTO without removing the old name yet.
3. **Backfill**: map historical data from the authoritative source, logging checkpoints and mismatches.
4. **Switch write path**: write new data using one canonical mapping, avoiding independent dual writes.
5. **Shadow read**: compare results between old and new read paths; check tenant/authorization rules.
6. **Cutover**: migrate consumers in batches while monitoring fallbacks and errors.
7. **Contract**: remove the old name only after no consumers or write paths remain and a rollback/forward-fix plan exists.

Assume a table **legacy_orders** has a UUID customer_id that truly means account ID:

~~~sql
ALTER TABLE legacy_orders
ADD COLUMN buyer_account_id UUID;

-- Valid only after verifying meaning and 1:1 mapping.
UPDATE legacy_orders
SET buyer_account_id = customer_id
WHERE buyer_account_id IS NULL;

-- Reconcile new and old columns during the compatibility window.
SELECT order_id, customer_id, buyer_account_id
FROM legacy_orders
WHERE buyer_account_id IS DISTINCT FROM customer_id;
~~~

This is **an example for a hypothetical legacy table**, not part of the sales.orders DDL in Section 10. Real execution requires batching, checkpoints, concurrency control, and type/mapping checks. A single backfill does not guarantee that new rows from an older application instance continue populating buyer_account_id.

If two write paths exist, there should be only **one authoritative writer**; the other column is derived/reconciled during transition. Bidirectional triggers without clear rules can loop or mask conflicts.

### 13.3. API Renames Can Be Breaking Even When Values Do Not Change

If JSON v1 returns **customerId**, renaming it to **buyerAccountId** can break client deserialization. Similarly, changing the public enum **PROCESSING** to **PICKING** changes both meaning and structure.

You can use API v2, versioned mappings, and a v1 deprecation timeline; run contract tests with actual consumers. Do not assume adding a field is always backward-compatible: clients with strict validators or deserializers may reject unknown fields.

Do not change public IDs merely because the database migrates from VARCHAR to BIGINT or UUID. **Stable public identifiers** can be decoupled from physical keys.

## 14. Data-Protection-Related Names Must Be Especially Clear

A column named **user_info** might hold email, phone, address, notes, or sensitive attributes, making authorization and retention difficult. Separate fields by **business meaning**, for example:

| Name | Semantics | Boundary |
| --- | --- | --- |
| **buyer_account_id** | Ordering account identifier | Not contact information by itself |
| **recipient_phone_at_handover** | Recipient phone at handover | Only authorized delivery parties |
| **current_customer_email** | Current email per Customer | Mutable, requires lookup permission |
| **shipping_address_at_confirmation** | Address locked for the transaction | Snapshot has separate retention policy |
| **fraud_review_score** | Internal risk classification score | Not exposed by default |
| **public_order_id** | ID permitted in external contracts | Does not replace authorization |
| **subject_ref** | Pseudonymous linkage code | Still carries re-identification risk |

A name containing **_hash** does not prove data is anonymized. An unsalted email hash can be dictionary-attacked from an email list; a stable token or UUID can still correlate behavior across systems. **Protection-related names must accurately reflect mechanism and scope**, accompanied by permissions, encryption, auditing, and retention.

### 14.1. Avoid Returning Raw Entities

A serializer that directly returns every SQL column can leak newly added columns like risk_score or agent_note. Public APIs must use purpose-built DTOs/mappers with allowlists.

Naming reviews should ask: **does the consumer genuinely need this field, at what point in time, and with what permission?** A clean name does not make a field eligible for exposure.

## 15. Name Review Process and Documentation Quality

### 15.1. Syntactic Linting Can Be Automated

Example pattern for PostgreSQL identifiers:

~~~text
^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$

Conforming names:
  order_id
  confirmed_at
  line_net_amount
  source_order_id

Needs review:
  OrderID
  order--id
  order__id
  123status
  value1
~~~

Regex only checks **form**; it does not know what **amount** represents, what a row counts, or whether customer and recipient differ. Do not equate "lint pass" with "semantic pass."

### 15.2. New-Field Review Checklist

| Question | Required evidence |
| --- | --- |
| In which context do business users use this term? | Glossary entry and owner |
| What does one row represent? | Grain statement |
| Does the name collide with another term? | Check against existing glossary |
| In what scope is the ID unique? | PK/UK, tenant/source rules |
| Who determines the value? | Source of truth |
| At what time is the field valid? | Current, confirmed_at, effective time |
| What are the unit and rounding rules? | currency, scale, unit |
| What does NULL mean? | Required/unknown/not-yet/withheld |
| Is the field sensitive? | PII classification, permissions, retention |
| Do APIs/events/analytics use this name? | Consumer/version inventory |
| Are there tests verifying meaning? | Constraints, reconciliation, contract tests |

Each bounded context should have a glossary owner. A naming committee should not enforce a single global vocabulary without understanding business workflows. When two teams genuinely own two distinct meanings, build a **mapping** instead of forcing artificial uniformity.

### 15.3. Contract Tests and Data Quality Tests

Useful tests:

- **Schema test:** field/API names match the version; no non-allowlisted columns leak.
- **Enum test:** every internal state has a valid public mapping; unapproved enums are not exposed.
- **Time test:** confirmed_at, captured_at, received_at are not swapped; timezones are preserved.
- **Money test:** currency and scale stay consistent; no precision loss during serialization.
- **Grain test:** UNIQUE prevents duplicate lines/orders; JOINs do not multiply measures.
- **Snapshot test:** changing Catalog price does not modify unit_price_at_confirmation.
- **Metric test:** filters/states match the count/amount name.
- **Security test:** public IDs do not bypass object authorization; PII is not leaked accidentally.
- **Migration test:** aliases/new names reconcile cleanly during the transition window.
- **Rebuild test:** read projections or derived tables recompute from the authoritative source without changing meaning.

**The right name with the wrong data is still a bug**, and a test that only checks JSON has an amount field cannot prove amount came from a successful capture rather than a payment attempt.

## 16. End-to-End Example: "On-Time Delivered Shipments"

Requirement:

> "Report the number of orders delivered on time each day by carrier."

Before naming the metric, clarify:

- Count **Orders** or **Shipments**? One Order can have multiple parcels.
- Does "delivered" mean successfully delivered with proof, or merely handed to the carrier?
- Is "on time" evaluated against **promised_delivery_at** or end of the promised delivery calendar day?
- Group by delivery date or promised date? Which timezone?
- If a shipment has multiple delivery attempts, how is it counted?
- If the carrier changes mid-journey, which carrier is accountable in the report?

Assume stakeholders want **the count of shipments successfully delivered no later than promised_delivery_at**, grouped by delivery date in Vietnam time.

### 16.1. Grain and Names

~~~text
fulfillment.shipments:
  tenant_id
  shipment_id
  order_id
  carrier_id
  promised_delivery_at
  delivered_at
  delivery_state_code

Metric:
  on_time_delivered_shipment_count

Grouping:
  delivered_business_date
  carrier_id
~~~

**Do not call this metric on_time_order_count**, because two on-time shipments for one order would contribute two to the count. If you want to count **orders whose every shipment was delivered on time**, design a separate metric with a coverage condition.

### 16.2. DDL and Constraints

~~~sql
CREATE SCHEMA fulfillment;

CREATE TABLE fulfillment.shipments (
    tenant_id BIGINT NOT NULL,
    shipment_id UUID NOT NULL,
    order_id UUID NOT NULL,
    carrier_id UUID NOT NULL,
    promised_delivery_at TIMESTAMPTZ NOT NULL,
    delivered_at TIMESTAMPTZ,
    delivery_state_code TEXT NOT NULL,
    CONSTRAINT pk_shipments
        PRIMARY KEY (tenant_id, shipment_id),
    CONSTRAINT fk_shipments_order
        FOREIGN KEY (tenant_id, order_id)
        REFERENCES sales.orders(tenant_id, order_id),
    CONSTRAINT ck_shipments_state
        CHECK (delivery_state_code IN (
            'CREATED', 'IN_TRANSIT', 'DELIVERED', 'FAILED'
        ))
);

CREATE INDEX ix_shipments_delivered_carrier
    ON fulfillment.shipments(tenant_id, delivered_at, carrier_id);
~~~

If the system has a **RETURNED** state after previously being DELIVERED, store **delivery event history** instead of assuming the current state always reflects the delivery milestone. **delivered_at** may need to be preserved after a return; do not add a CHECK forcing it to NULL for all non-DELIVERED states without understanding the lifecycle.

### 16.3. Query and Verification Cases

~~~sql
SELECT
    s.tenant_id,
    s.carrier_id,
    (s.delivered_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
        AS delivered_business_date,
    COUNT(*) AS on_time_delivered_shipment_count
FROM fulfillment.shipments AS s
WHERE s.delivery_state_code = 'DELIVERED'
  AND s.delivered_at IS NOT NULL
  AND s.delivered_at <= s.promised_delivery_at
  AND s.delivered_at >= $1::TIMESTAMPTZ
  AND s.delivered_at <  $2::TIMESTAMPTZ
GROUP BY
    s.tenant_id,
    s.carrier_id,
    (s.delivered_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE;
~~~

Test cases:

1. One shipment with three delivery attempts, one successful: counts as **one shipment**.
2. One Order with two shipments delivered on time: counts as **two shipments**.
3. delivered_at exactly equals promised_delivery_at: on time if the contract uses **<=**.
4. Delivered one second late: not on time under timestamp rules.
5. Undelivered shipment, delivered_at NULL: not counted.
6. Late-arriving delivery confirmation event: reporting must support updates/reconciliation by event time.
7. Actual delivering carrier differs from initially assigned carrier: requires clear attribution rules.
8. If the requirement changes to "on time by calendar date," update the formula and tests rather than keeping the old name with an ad-hoc meaning.

**The right name is the result of locking down grain and rules**, not a labeling step at the end.

## 17. Decision Log and Glossary Lifecycle

A glossary easily goes stale if schemas and business rules change without updates. A minimal documentation set can include:

- **Context map** for ownership across domains.
- **Conceptual diagram** and key terms.
- **Logical model** with grain, cardinality, business keys, and invariants.
- **Physical schema** with tables, columns, indexes, and constraints.
- **Data dictionary** with meaning, time semantics, units, NULL semantics, and data classification.
- **Metric catalog** with formulas, filter sets, aggregation rules, and owners.
- **API/event contracts** with versions and public identifiers.
- **Decision log/ADR** for name choices, aliases, and rationale for changes.
- **Data quality checks** tied to key promises.

You do not need nine separate documentation tools. You can keep documentation alongside code/migrations and generate structural parts from the schema, but **business definitions must be confirmed by an authoritative stakeholder**.

Short ADR example:

~~~text
ADR-024: Choose buyer_account_id over customer_id in Sales.Order

Context:
  customer_id in legacy Order identifies the ordering account.
  It is neither a CRM person nor a recipient.

Decision:
  Canonical: buyer_account_id
  Legacy alias: customer_id in schema and API v1
  Public v2: buyerAccountId, only for consumers that need it

Consequences:
  - Requires mapping/backfill and verified reader/writer migration.
  - Does not grant permissions to recipient or payer.
  - Do not expose this ID in APIs that do not require it.

Validation:
  - Tenant-scoped FK.
  - Verified mapping from legacy ID to new ID.
  - Remove alias only after v1 consumers are retired.

Owner:
  Sales.Order and Data team.
~~~

### 17.1. Do Not Let Temporary Names Become a Second Source of Truth

When **orders_new** and **orders_old** coexist during a migration, you must define:

- Which source has write authority?
- Which table is a projection?
- Which name/field mappings are equivalent?
- When is the old writer stopped?
- Which order IDs and metrics are reconciled?
- When can the old table/alias be dropped?
- Is there a rollback or forward-fix path?

If both tables receive independent writes for too long, renaming cannot fix conflicts. Lock down ownership and the evolution process.

## 18. Anti-Patterns and Fixes

| Anti-pattern | Risk | Fix |
| --- | --- | --- |
| Every table has **status** | Loses workflow meaning | order_state_code, capture_state_code... |
| **created_at** used for event time | Wrong reporting dates | Separate confirmed_at/occurred_at and loaded_at |
| **amount** everywhere | Confuses locked, captured, refunded money | Event-specific names plus currency |
| **customer_id** for buyer, payer, recipient | Wrong relationships and permissions | Bounded-context-specific terms |
| **is_active** without definition | Conflates verified, unlocked, active | Explicit state model |
| **payment_count** from attempts | Counts failed attempts | attempted_payment_count or capture_count from right source |
| **avg_of_avgs** named average | Wrong aggregation | Sum/count and weighted definition |
| **fact_orders** containing order lines | COUNT(*) misread as order count | fact_order_line and grain contract |
| **current_price** written onto old invoices | Erases transaction history | unit_price_at_confirmation |
| **orderId** is actually an internal PK | Coupling and schema leakage | Stable public ID/mapper |
| **UserData JSON** holding PII everywhere | Hard to authorize and delete | Purpose-minimal schema/DTO |
| Auto-renaming APIs from new DB names | Breaking change | Contract versioning, compatibility |
| **_new / _old / _tmp** kept forever | Unclear authoritative source | Owner, expiry, migration gate |

When a name looks unclear, first check **whether the model has the wrong grain or wrong ownership**. Adding long suffixes only helps when the underlying structure represents the real facts.

## 19. Practice Exercises

### Exercise 1 — Customer vs. Recipient

CRM has Customer, Order has an ordering account, and Logistics has a recipient. The recipient may be a different person. The team wants to name every ID **customer_id** for uniformity.

**Question:** What is wrong with this design? Propose names and mappings.

### Exercise 2 — Ambiguous Amount

An order of 500,000 VND has two PaymentAttempts, and only the second attempt successfully captures 500,000 VND. A report sums `amount` in both the `orders` and `payment_attempts` tables.

**Question:** Which names should be fixed, and which data represents collected cash?

### Exercise 3 — Ambiguous Date

A sensor measures at 23:58 UTC, and the server receives the message at 00:03 UTC the next day. The table has only a **date** column.

**Question:** Which names/timestamps are needed to report measurement date and receipt date separately?

### Exercise 4 — Product vs. SKU

Catalog has a Product "T-shirt" with three sizes; inventory tracks stock by size. Sales stores only product_id on OrderLine.

**Question:** Which entities and FKs should exist? What is lost by using only the group-level Product?

### Exercise 5 — is_active Without Meaning

An account is registered, has not verified email, is not locked, and has made no purchase in 90 days, yet is_active = true.

**Question:** What can be inferred? Choose a different naming/state model.

### Exercise 6 — SUM After JOIN

An order has three lines, with confirmed_items_amount on the header = 310,000 VND. After joining lines, SUM(header amount) = 930,000.

**Question:** Is the root cause naming or grain? How should it be fixed?

### Exercise 7 — Inventory Fact

There are 20 units at the end of Monday and 25 units at the end of Tuesday. A report calculates SUM(on_hand_quantity) = 45 and calls it ending inventory.

**Question:** What is wrong, and what is the correct metric?

### Exercise 8 — Current Price vs. Locked Price

Catalog increases the current list price from 120,000 to 130,000, and a job updates all historical OrderLines so prices are "consistent."

**Question:** Which names help expose the bug, and which owner decides each price?

### Exercise 9 — API Rename

JSON v1 returns customerId; the Sales team wants buyerAccountId, and the values are verified to be the same account ID.

**Question:** Can the name be swapped abruptly? Propose a compatibility plan.

### Exercise 10 — Multi-Dimensional State

Order is confirmed, Payment is 50% captured, and Fulfillment has not started. The system stores status = PROCESSING.

**Question:** Why is this insufficient, and which states should be separated?

### Exercise 11 — Overly Generic Event Name

The producer emits OrderUpdated whenever a note is edited, an order is confirmed, or delivery status changes, attaching the entire SQL row. Logistics does not know when to create a Shipment.

**Question:** How should events be named and payloads scoped?

### Exercise 12 — Two Parcels Delivered

An Order has two Shipments: parcel A is on time, parcel B is late. A report named **on_time_order_count** runs COUNT(*) over on-time shipments.

**Question:** How should the right names and metrics distinguish these?

### Exercise 13 — Silently Changed Metric Meaning

Last week new_customer_count = newly registered accounts; this week = first-time purchasing accounts. The team keeps the name and edits the old glossary definition.

**Question:** What is wrong? How should metric versioning be handled?

### Exercise 14 — Long-Lived Temporary Table Names

Both orders_old and orders_new have active writers, and reports read from both interchangeably. The team plans only to rename them to "get rid of old/new."

**Question:** What decisions are missing before renaming?

### Suggested Solutions

1. Do not merge terms globally. Use **crm_customer_id**, **buyer_account_id**, and **recipient_ref** by context; link only via mappings with clear permissions and meaning.
2. You need **confirmed_items_amount**, **attempt_amount**, **captured_amount**, attempt/capture states, and currency. Collected cash comes from **successful captures** in Payment, not from summing failed attempts or repeating order totals.
3. Separate **observed_at** and **received_at**; group by the corresponding timestamp with the reporting timezone documented.
4. Model Product, ProductVariant, and variant × warehouse inventory; OrderLine needs **product_variant_id**/transaction-time SKU snapshot. Group-level product loses the specific size.
5. **is_active** is too vague. Separate **email_verification_state**, **account_access_state**, **last_order_at**, or approved eligibility criteria; do not infer three meanings from one Boolean.
6. The header measure at Order grain is multiplied by joining lines. Aggregate on **orders** or SUM **line_net_amount** at OrderLine grain; do not use SUM(DISTINCT amount) as a general fix.
7. **on_hand_quantity** is an end-of-period balance, not additive across two days. Ending inventory on Tuesday is **25**; a two-day average is valid only if required and properly defined.
8. **unit_price_at_confirmation** is a Sales.Order snapshot; **current_list_price** belongs to Catalog. Do not sync current prices into historical documents.
9. Public fields are contracts; use v2 or a tested transition mechanism, clear mapping, consumer tracking, and retire v1 only when conditions are met.
10. Separate **order_state_code**, **payment_state_code**, and **fulfillment_state_code** by owner; public status can be a separate mapping with clear semantics.
11. Use domain events such as **OrderConfirmed**, **ShipmentRequested**, and **PaymentCaptured** where appropriate, with eventId/occurredAt/version; do not broadcast PII, internal PKs, or full CDC rows.
12. **on_time_delivered_shipment_count** counts one on-time shipment; **on_time_fulfilled_order_count** must check that all shipments of each order were delivered on time per business coverage and deadline rules.
13. Two different meanings require two metrics such as **registered_account_count** and **first_purchase_buyer_count**, with version, owner, and effective date; do not overwrite historical definitions.
14. Finalize **source of truth, ownership, write paths, backfill/reconciliation, consumers, rollback, and cleanup gates**. Renaming does not resolve conflicting dual writes.

## 20. Key Takeaways

**Good naming conventions have two layers:** a **predictable syntax** (schema, snake_case, suffixes, constraints) and a **business language with clear definitions, grain, context, owner, timestamp, and units**. Without the semantic layer, a clean-looking schema can still lead to wrong JOINs, wrong revenue, or data leaks.

**Do not force different facts into the same name.** Buyer is not Recipient by default, OrderConfirmed is not synonymous with PaymentCaptured, a confirmation snapshot is not a current value, and a Shipment is not an Order. When two contexts have different vocabularies, write a mapping instead of forcing artificial uniformity.

**A name is part of a contract with a lifecycle.** When business rules change, update the glossary, model, API/events, metrics, and tests; migrate with compatibility plans and reconciliation, not just string find-and-replace.

Before approving a name, ask: **"Do business users use this term? What does one row or value represent, at what time, and in what unit? Who has authority over it? Does this name keep its meaning when joined, aggregated, or published to another system?"** Verifiable answers keep a data model understandable, maintainable, and safe to evolve.
