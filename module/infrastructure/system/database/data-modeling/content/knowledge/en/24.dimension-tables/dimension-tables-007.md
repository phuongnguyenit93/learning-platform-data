# Transaction Identifiers as Degenerate Dimensions

## Learning Objectives

In the **DATABASE_DATA_MODELING** module, a sound data model must translate business questions into well-defined structures with keys, constraints, and verifiability. In analytical modeling, we typically separate **fact tables** holding events/measurements from **dimension tables** holding descriptive context. However, not every attribute used for filtering or grouping requires its own dimension table.

A **degenerate dimension** (abbreviated **DD**) is an important pattern: **a transaction or business document identifier stored directly in the fact table for filtering, grouping, counting, or tracing, without a separate dimension table holding solely that identifier**.

After this lesson, you will be able to:

1. Explain degenerate dimensions and recognize `order_number`, `invoice_number`, `ticket_number`, and similar transaction identifiers.
2. Distinguish **transaction identifiers** from **fact-row keys**, **surrogate keys**, **foreign keys to dimensions**, and **true dimensions with descriptive attributes**.
3. Decide when to keep an identifier directly in the fact, when to introduce a document-level fact, or when to build a meaningful separate dimension.
4. Design star schemas and SQL queries for **drill-through**, `COUNT(DISTINCT)`, and monetary aggregations without duplicating data.
5. Handle identifiers unique only per tenant/store/year, identifiers that change over time, duplicate loads, and sensitive data.
6. Assess physical impacts on indexes, partitioning, storage, access control, and scalability.

## 1. Opening scenario: where does the order number live in a star schema?

Suppose the business wants to answer:

- Total booked merchandise value by month and product category?
- Which line items belong to a given order?
- How many **orders** (distinct from how many **order lines**) occurred in a period?
- When a customer reports "order `ORD-101` has the wrong price," can we immediately locate the fact rows for reconciliation?

The business process is **order confirmation**. One order has multiple product lines, so we choose the grain:

~~~text
fact_order_lines:
    ONE ROW = one item line (order_number, line_no)
    of a confirmed order, within a defined tenant scope.
~~~

Illustrative fact table:

| tenant_id | order_number | line_no | date_key | product_key | quantity | booked_amount |
|---|---|---:|---|---:|---:|---:|
| T01 | ORD-101 | 1 | 2026-11-01 | 501 | 2 | 200,000 |
| T01 | ORD-101 | 2 | 2026-11-01 | 502 | 1 | 50,000 |
| T01 | ORD-102 | 1 | 2026-11-02 | 501 | 1 | 80,000 |
| T02 | ORD-101 | 1 | 2026-11-02 | 503 | 1 | 70,000 |

Assume all amounts are in VND and `order_number` **is unique only within one tenant**. Then:

- There are **4 fact rows**.
- There are **3 distinct orders by `(tenant_id, order_number)`**.
- Total `booked_amount` is **400,000 VND**.
- Order `ORD-101` for `T01` has **2 item lines**; `T02` also has `ORD-101`, which is a **different order**.

In this structure, `date_key` and `product_key` reference dimensions describing dates and products. Meanwhile, `order_number` is **stored directly in the fact** to identify and trace the document. If there are no independent descriptive attributes belonging in a `dim_order` table, `order_number` is a **degenerate dimension**.

## 2. Definition and nature of a degenerate dimension

A degenerate dimension has these traits:

1. **Carries business identification semantics**: order number, invoice number, support ticket number, shipment tracking code, transaction code.
2. **Has analytical value**: used for filtering, grouping, drill-through, document counting, and source reconciliation.
3. **Lives inside the fact**: avoids creating a dimension table just to hold a single `(order_key, order_number)` row and joining back to it.
4. **Usually has high cardinality**: each document has its own identifier within its scope.
5. **Is not necessarily a unique key of a fact row**: an order number can repeat across multiple item lines; an invoice number repeats across multiple invoice lines.

In short:

> **A degenerate dimension is an attribute playing a dimensional role for filtering, grouping, and traceability, stored directly in the fact table because no standalone descriptive dimension table is needed.**

The term *degenerate* **does not imply poor data quality**. It names an intentional design pattern in dimensional modeling.

### Common examples

| Process / fact | Candidate DD identifier | Fact grain | Use |
|---|---|---|---|
| Order lines | `order_number` | One item line of an order | Order lookup, distinct order count |
| Invoice lines | `invoice_number` | One invoice line | Drill-through from reports to invoices |
| Payment transactions | `payment_transaction_id` | One payment event | Reconciliation and deduplication |
| Support tickets | `ticket_number` | One ticket event or state at chosen grain | Look up all events for one ticket |
| Shipment lines | `shipment_number` | One parcel or shipment line | Group lines belonging to the same shipment |
| Receipt lines | `receipt_number` | One item line on a receipt | Basket analysis, receipt audit |

**Verify identifier scope:** `receipt_number = 0001` may appear across multiple stores or years. In that case, the **complete tracing identifier** is a tuple such as `(store_id, fiscal_year, receipt_number)`, not `receipt_number` alone.

## 3. How does a degenerate dimension differ from a regular dimension?

A **regular dimension** might hold:

~~~text
dim_product(
    product_key,
    product_id,
    product_name,
    category_name,
    brand_name
)
~~~

`product_key` in the fact references a product descriptive record. Attributes like `category_name` and `brand_name` support hierarchical analysis and sometimes need version history (*SCD Type 2*).

If we created:

~~~text
dim_order(
    order_key,
    order_number
)
~~~

merely to replace `order_number` in the fact with `order_key`, we would add **an extra table and an extra JOIN** while gaining zero business descriptive attributes. In this case, keeping `order_number` directly in the fact is simpler and makes drill-through effortless.

### Comparison

| Criterion | Descriptive dimension | Degenerate dimension |
|---|---|---|
| Examples | Product, customer, store, date | Order number, invoice number, ticket number |
| Where does it live? | Separate `dim_*` table | Column directly in `fact_*` |
| Role | Analytical attributes, hierarchies, descriptions | Identification, document grouping, traceability |
| Key in fact | Usually foreign key `product_key`, `customer_key` | Identifier value like `order_number` |
| Attribute history | May need Type 1/Type 2 | Transaction codes themselves usually remain immutable; descriptive history belongs to other entities/processes |
| Cardinality | Low to high | Typically very high |
| Needs separate table? | Yes, when real descriptive attributes require governance | No, if the identifier stands alone with no other reason to split |

**There is no rule saying "a long identifier must become a dimension."** Splitting out a table must be justified by semantics, constraints, or real workload needs.

## 4. Distinguishing three easily confused key concepts

In data design, these concepts can appear together:

| Concept | Example | Question it answers |
|---|---|---|
| **Business document ID / DD** | `order_number = 'ORD-101'` | Which business order is this? |
| **Business key of a fact row** | `(tenant_id, order_number, line_no)` | Is this fact row unique at the declared grain? |
| **Dimension surrogate key** | `product_key = 501` | Which dimension record/version does the fact reference? |
| **Fact surrogate key (optional)** | `fact_row_key = 1000123` | Is a separate technical ID needed for loads, storage, or referencing? |
| **OLTP source key** | `orders.id = 87342` | How does the transactional source identify the record? |

These keys **may share values or map to each other**, yet should never be assumed to share the same role.

### Example: one order number appearing multiple times is valid

~~~text
(T01, ORD-101, line_no=1, product=P1)
(T01, ORD-101, line_no=2, product=P2)
~~~

Because the grain is **item line**, `(T01, ORD-101)` repeating twice is **valid**. The dependency:

~~~text
(tenant_id, order_number, line_no) → line-item details at confirmation
~~~

holds, whereas:

~~~text
(tenant_id, order_number) → product_key
~~~

is usually **false** because an order has multiple products.

Do not place `UNIQUE(tenant_id, order_number)` on a line-item fact. That blocks multi-line orders. Conversely, **do enforce** uniqueness on `(tenant_id, order_number, line_no)` when the grain requires it.

### A DD is not a surrogate key

An `order_number` issued by a business source might look like `HN-2026-000123`. It is a **business identifier**, not an auto-generated warehouse surrogate key. If the fact also has an auto-incrementing `fact_row_key`, **both columns can coexist**: `fact_row_key` for technical operations; `order_number` for business semantics and drill-through.

**Do not use a surrogate key to mask business duplicates.** Even with `fact_row_key`, you still must verify whether a source line was loaded twice.

## 5. Practical design: orders, order lines, and real dimensions

Suppose the company has multiple tenants and some `order_number` values collide across tenants. Priority reports:

- Booked merchandise value by date, product, and customer segment.
- Order counts per tenant.
- Locating lines of an order when reconciling against the source.
- Reconciling per-order totals against order-level data.

### 5.1. Grain declaration

~~~text
fact_order_lines:
    One row per (tenant_id, order_number, line_no)
    at the moment an order is successfully confirmed.
~~~

`tenant_id` and `order_number` together form the **document identifier within business scope**. If a source reuses order numbers by year or store, include `store_id`, `fiscal_year`, or another global key per verified rules.

### 5.2. Star schema diagram

~~~mermaid
flowchart LR
    D["dim_date"] --> F["fact_order_lines"]
    C["dim_customer"] --> F
    P["dim_product"] --> F
    F --> O["DD: tenant_id + order_number"]
    F --> M["Measures: quantity, booked_amount"]
~~~

In the diagram, **`order_number` does not connect to `dim_order`**. It remains a column for drill-through and grouping by order. `date_key`, `customer_key`, and `product_key` are foreign keys referencing **descriptive dimensions**.

### 5.3. Illustrative PostgreSQL DDL

A simplified example assuming:

- An `order_number` does not change after the order is confirmed.
- `(tenant_id, order_number, line_no)` is the immutable business key of the line-confirmation event.
- Line unit price and discount are locked; amounts share one reporting currency in summation queries.
- More complex dimension history (SCD Type 2) is designed separately if needed.

~~~sql
CREATE TABLE dim_date (
    date_key DATE PRIMARY KEY
);

CREATE TABLE dim_product (
    product_key BIGINT PRIMARY KEY,
    product_code VARCHAR(40) NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    category_name VARCHAR(100) NOT NULL
);

CREATE TABLE dim_customer (
    customer_key BIGINT PRIMARY KEY,
    customer_code VARCHAR(40) NOT NULL,
    customer_segment VARCHAR(100)
);

CREATE TABLE fact_order_lines (
    tenant_id VARCHAR(30) NOT NULL,
    order_number VARCHAR(60) NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),

    confirmed_date DATE NOT NULL REFERENCES dim_date(date_key),
    customer_key BIGINT NOT NULL REFERENCES dim_customer(customer_key),
    product_key BIGINT NOT NULL REFERENCES dim_product(product_key),

    quantity NUMERIC(18,3) NOT NULL CHECK (quantity > 0),
    unit_price_at_order NUMERIC(18,2) NOT NULL
        CHECK (unit_price_at_order >= 0),
    line_discount_amount NUMERIC(18,2) NOT NULL
        CHECK (line_discount_amount >= 0),
    booked_amount NUMERIC(18,2) NOT NULL,

    PRIMARY KEY (tenant_id, order_number, line_no),
    CHECK (line_discount_amount <= quantity * unit_price_at_order),
    CHECK (
        booked_amount =
            quantity * unit_price_at_order - line_discount_amount
    )
);
~~~

This is **illustrative DDL for a simplified scope**. With multiple currencies, add `currency_code` and a conversion policy; with post-confirmation price adjustments, decide between updating snapshots or recording **separate adjustment events**. Composite primary keys affect index size; measure on your actual DBMS and workload.

**Core point:** omitting a code-only `dim_order` does **not** eliminate keeping an `orders` table in OLTP or `fact_orders` in the analytics warehouse when genuine order-level KPIs exist.

## 6. Querying DDs: drill-through, aggregation, and document counts

### 6.1. Drill-through from a KPI to document lines

Suppose a dashboard flags an anomalous booked amount for an order:

~~~sql
SELECT
    f.tenant_id,
    f.order_number,
    f.line_no,
    f.confirmed_date,
    p.product_code,
    p.product_name,
    f.quantity,
    f.unit_price_at_order,
    f.line_discount_amount,
    f.booked_amount
FROM fact_order_lines AS f
JOIN dim_product AS p
  ON p.product_key = f.product_key
WHERE f.tenant_id = 'T01'
  AND f.order_number = 'ORD-101'
ORDER BY f.line_no;
~~~

Here the analyst does not need an extra JOIN to `dim_order` just to read the order number. The DD lets you **drill from monthly/channel summaries down to document identifiers**, then inspect each line.

When linking back to the operational source page, applications can use verified identifiers to look up `orders`; never build URLs blindly from unvalidated strings or assume source IDs always equal display codes.

### 6.2. Order totals

~~~sql
SELECT
    tenant_id,
    order_number,
    SUM(booked_amount) AS booked_merchandise_amount,
    COUNT(*) AS line_count
FROM fact_order_lines
GROUP BY tenant_id, order_number
ORDER BY tenant_id, order_number;
~~~

With the sample data:

| tenant_id | order_number | booked_merchandise_amount | line_count |
|---|---|---:|---:|
| T01 | ORD-101 | 250,000 | 2 |
| T01 | ORD-102 | 80,000 | 1 |
| T02 | ORD-101 | 70,000 | 1 |

If you only wrote `GROUP BY order_number`, the two `ORD-101` orders from different tenants would **erroneously merge into one**. A DD must include or travel with its **complete identification scope**.

### 6.3. Counting orders, not lines

~~~sql
-- Count item lines:
SELECT COUNT(*) AS order_line_count
FROM fact_order_lines;

-- Count distinct orders across all tenants (broadly portable SQL):
WITH distinct_orders AS (
    SELECT DISTINCT tenant_id, order_number
    FROM fact_order_lines
)
SELECT COUNT(*) AS order_count
FROM distinct_orders;
~~~

For the 4 sample rows, the results are **4 item lines** and **3 orders**, respectively.

In PostgreSQL, you can write:

~~~sql
SELECT COUNT(DISTINCT (tenant_id, order_number)) AS order_count
FROM fact_order_lines;
~~~

If your DBMS does not support `COUNT(DISTINCT (a, b))` tuple syntax like PostgreSQL, use the `SELECT DISTINCT ...` CTE above. **Never concatenate two codes without escaping** before taking `COUNT(DISTINCT)`; for instance, `'A' || 'BC'` and `'AB' || 'C'` both yield `'ABC'`.

### 6.4. Counting by time and category has a trap

~~~sql
SELECT
    f.confirmed_date,
    p.category_name,
    COUNT(DISTINCT (f.tenant_id, f.order_number))
        AS orders_with_category,
    SUM(f.booked_amount) AS booked_amount
FROM fact_order_lines AS f
JOIN dim_product AS p
  ON p.product_key = f.product_key
GROUP BY f.confirmed_date, p.category_name;
~~~

`orders_with_category` means **number of orders having at least one line in that category**. If an order contains both "Books" and "Accessories," it is counted in **both categories**. Therefore, never sum `orders_with_category` across categories to obtain company-wide order counts when multiple categories can share an order.

`booked_amount` can be summed by category **provided each fact line binds to exactly one category via the chosen dimension version**, shares currency, and has no multiplying JOINs. With SCD Type 2, facts must point to the product version valid at transaction time.

### 6.5. Counting orders absent from a line-item fact

A line-item fact **contains no orders without lines**. If the business needs to count **all created orders**, including drafts or zero-item orders, `COUNT(DISTINCT order_number)` on a line-item fact **is insufficient**.

In that case, you may need `fact_orders` at the **one-order** grain, or order data from the source with appropriate statuses. Never alter the definition of "order count" merely because the line-item fact happens to be available.

## 7. When do you need an order-level fact or order-level dimension?

This is a key design decision. **Not needing a dimension solely to hold an order number** does not mean all order-level data belongs on every item line.

### Case A — Document code needed only for lookup

If `order_number` is used to find item lines, count orders, and reconcile, yet **has no independent descriptive attributes requiring a JOIN**, keeping it as a DD in `fact_order_lines` makes sense.

~~~text
fact_order_lines(
    tenant_id, order_number, line_no,
    date_key, product_key, customer_key,
    quantity, booked_amount
)
~~~

### Case B — Measurements exist at the order level

For example, total shipping fee, order-wide discount, or parcel count belong to the **order grain**:

~~~text
fact_orders(
    tenant_id, order_number,
    confirmed_date_key, customer_key, channel_key,
    order_shipping_fee, order_level_discount
)
~~~

Grain of `fact_orders`: **one confirmed order** per tenant, or one order at another chosen milestone.

In `fact_order_lines`, the grain remains **one item line**. Never copy order-wide `order_shipping_fee` onto **every line** and `SUM` it; a three-line order with a 30,000 fee would sum to 90,000 if added directly.

If fees must be allocated to individual products, establish an explicit allocation rule, name it `allocated_shipping_fee`, and verify:

\[
\sum_{\text{lines of an order}}
\text{allocated\_shipping\_fee}
=\text{order\_shipping\_fee}.
\]

### Case C — Business descriptive attributes exist at the document level

If orders carry `order_type`, `sales_channel`, `promotion_group`, approval group, or descriptive hierarchies used consistently, several options exist:

- If attributes **depend on the order-level event**, consider placing them on an **order-level fact**.
- If attributes are few and stable, compact FKs like `order_type_key` or `channel_key` can live **directly on the line-item fact** once order-level dependency is verified, weighing repetition costs.
- If an **order entity** has a rich descriptive set, its own lifecycle, and must be shared across multiple facts, consider a real `dim_order`; however, evaluate high cardinality and ETL/JOIN costs.
- If `status` transitions multiple times, choose between **current status**, **status event fact**, or **accumulating snapshot** per reporting question. Do not turn an order-number dimension into a dumping ground for status versions lacking clean grain.

**There is no rule saying "having two extra attributes forces creating `dim_order`."** Choose structures based on business events, analytical attributes, history needs, and workload.

### Quick decision table

| Question | If the answer is "yes" | Typical suitable choice |
|---|---|---|
| Only need code for filtering, grouping, drill-through? | No separate descriptive attributes needed | **DD directly in the fact** |
| Are there genuine order-level measures? | Measures do not belong to a single item line | **Order-level fact** |
| Is there a shared descriptive attribute set with own history? | Many order attributes need governance | Consider an **order dimension** with clear justification |
| Do multiple status transitions need counting? | One order produces many events | **Status event fact** |
| Need to track packing/shipping/return dates? | Multiple workflow milestones | **Accumulating snapshot** at matching grain |
| Want faster code lookups? | Issue may simply be indexing | Measure and add **indexes** before adding unnecessary tables |

## 8. One identifier can play different roles across facts

**Sharing `order_number` does not give all tables the same grain.**

~~~text
fact_order_lines:
    one row per (tenant_id, order_number, line_no)

fact_payment_transactions:
    one row per payment_transaction_id
    (each transaction may reference order_number)

fact_shipments:
    one row per shipment_id
    (one order can have multiple shipments)

fact_return_lines:
    one row per return_id + return_line_no
    (a return line may reference order_number/line_no)
~~~

In `fact_order_lines`, `order_number` is a DD grouping item lines. In `fact_payment_transactions`, it may be a **parent link/reference attribute** kept directly for order lookup, while the payment fact's key remains `payment_transaction_id`. `shipment_number` can likewise serve as a DD on the shipment fact.

### Trap when joining multiple facts on the same DD

Suppose order `T01/ORD-101` has:

- **3 item lines**.
- **2 payment transactions**.
- **2 shipments**.

Joining all three detail facts directly on `(tenant_id, order_number)` yields:

\[
3\times2\times2=12\text{ rows}.
\]

Then:

- Each item line repeats \(2\times2=4\) times.
- Each payment transaction repeats \(3\times2=6\) times.
- Each shipment repeats \(3\times2=6\) times.

**Monetary amounts and counts get multiplied**, even though the DD used for joining is completely valid.

### Proper solution: aggregate to a common grain first

~~~sql
WITH lines_by_order AS (
    SELECT tenant_id, order_number,
           SUM(booked_amount) AS booked_amount
    FROM fact_order_lines
    GROUP BY tenant_id, order_number
),
payments_by_order AS (
    SELECT tenant_id, order_number,
           SUM(payment_amount) AS captured_amount
    FROM fact_payment_transactions
    WHERE transaction_type = 'CAPTURE'
    GROUP BY tenant_id, order_number
)
SELECT
    l.tenant_id,
    l.order_number,
    l.booked_amount,
    p.captured_amount
FROM lines_by_order AS l
LEFT JOIN payments_by_order AS p
  ON p.tenant_id = l.tenant_id
 AND p.order_number = l.order_number;
~~~

The `fact_payment_transactions` table and `payment_amount`, `transaction_type` columns in this query are **illustrative assumptions**, absent from the `fact_order_lines` DDL above. Handle refunds, reversals, currencies, and split payments per KPI policy; never assume `booked_amount = captured_amount`.

**DDs aid linking and drill-across, but never replace matching compatible grains before joining.**

## 9. Uniqueness, scope, and lifecycle of identifiers

### 9.1. Codes unique only within a tenant

Suppose:

~~~text
tenant T01, order_number ORD-101
tenant T02, order_number ORD-101
~~~

Identical display strings do not make two records the same order. The complete key is:

~~~text
(tenant_id, order_number)
~~~

If the source only generates unique order numbers per `(store_id, fiscal_year)`, include **that exact scope**. Multi-country analytics may also require a source-system namespace when multiple systems emit similar ID formats.

**Never infer uniqueness from a handful of sample rows.** Obtain confirmed business requirements and ID-generation rules.

### 9.2. Display codes can change

Not every `order_number` is immutable. Some systems:

- Assign a temporary code at draft creation and issue the official number upon confirmation.
- Renumber invoices at period close or per issuing branch.
- Allow manual code edits outside the main flow to fix errors.
- Merge sources, shifting code namespaces.

For analytical models, define a **stable identifier for deduplication and linkage**, alongside **historical display codes** if needed. You can store:

~~~text
source_system
stable_order_id
order_number_at_confirmation
tenant_id
~~~

`stable_order_id` serves as the immutable source key, while `order_number_at_confirmation` serves as the display DD at event time. This choice must reflect source contracts rather than inventing a "stable" key with no enforcement.

### 9.3. One order with multiple invoices or shipments

One order can produce:

~~~text
ORD-101
    ├── INV-001
    ├── INV-002
    └── SHIP-054, SHIP-055
~~~

Never assign a single `invoice_number` to the entire order when the business allows multiple invoices. Instead, each document type has **its own grain**:

~~~text
fact_invoice_lines(invoice_id, invoice_line_no, ...)
fact_shipments(shipment_id, ...)
fact_order_lines(order_id, line_no, ...)
~~~

Relationships across documents may require **bridge tables** or facts at the appropriate grain. A DD is a **traceability code**, not a promise that all business relationships are one-to-one.

## 10. Is a degenerate dimension an SCD attribute?

Normally a DD is a **transaction identifier at event occurrence**, with no separate descriptive attributes needing versioning. Therefore:

- Do not create Type 2 `dim_order` rows **solely for order-number changes** if that adds no business value.
- To store **order status history**, choose the right pattern: event fact or grain-matched accumulating snapshot.
- To know the **customer or product category at confirmation time**, bind the fact to the **point-in-time dimension version** or a governed attribute snapshot.
- If a code changes, define rules for keeping the **original code**, current code, and mapping instead of blindly running `UPDATE` across all historical data.

For example, an SCD Type 2 `dim_product` has multiple `product_key` values for one `product_code` over time. The line-item fact has:

~~~text
order_number = ORD-101             -- DD, document identifier
product_key  = 205                 -- FK to product version at order time
~~~

Two distinct roles: DD locates the document, while `product_key` explains product attributes under the selected version.

**Note:** if a transaction code embeds personal details or enables looking up individuals, enforce appropriate access controls and retention; being a DD does not exempt data from privacy protections.

## 11. Performance and physical design for high-cardinality DDs

DDs typically have many distinct values because every order/invoice/ticket carries its own code. This significantly affects indexing and storage.

### 11.1. Indexing for drill-through queries

For `fact_order_lines`, the composite primary key `(tenant_id, order_number, line_no)` can accelerate:

~~~sql
WHERE tenant_id = 'T01'
  AND order_number = 'ORD-101'
~~~

because those two columns form the **leading prefix** in a standard PostgreSQL B-tree index. Not every DBMS/storage engine behaves identically; measure on your target engine.

Looking up an order by `order_number` **without tenant** cannot use a tenant-first index effectively—and omitting tenant in queries can also **violate semantics or access permissions**. Verify cross-tenant intent and authorization before adding extra indexes.

### 11.2. Choosing identifier representation

| Option | Benefit | Trade-off |
|---|---|---|
| Keep document code as string | Easy source reconciliation and display | Long strings can enlarge indexes/facts |
| Keep stable numeric source key plus display code | Join/reconcile with sources on stable ID | Requires namespace and mapping governance |
| Generate technical surrogate per fact row | Convenient internal references in some pipelines | Does not replace grain and business keys |
| Encrypt/tokenize ID for restricted access tiers | Reduces raw identifier exposure | Complicates joins/decryption and key management |

Never build a `dim_order` table simply assuming "integer JOINs are always faster than storing strings" without measuring the **total cost** of the dimension table, JOINs, memory, row counts, and query patterns.

### 11.3. Partitioning and clustered storage

For massive facts, partitioning by transaction date helps periodic queries and retention. However:

- `order_number` may span multiple partitions if sources allow **line edits or late arrivals**; define the exact grain and partitioned event timestamp.
- **Global uniqueness across partitions** is not supported identically by every DBMS. For example, PostgreSQL normally requires unique/primary keys on partitioned tables to include the partition key; never just add date to the PK and assume two rows with the same business grain on different dates are valid.
- If global uniqueness of `(tenant_id, order_number, line_no)` across all partitions is strictly needed, pick a sound enforcement strategy: compatible partition keys, a unique registry, controlled ingestion, or DBMS-supported features.
- Tune clustering/indexing only **after** measuring workloads: queries by date, by customer, by order number, and partition sizes.

### 11.4. High cardinality impacts BI

A dimension with tens of millions of order numbers is unsuitable as a **dropdown slicer listing every value** for users. DDs are best suited for:

- Document-code search boxes.
- Drill-through from aggregated figures.
- Grouping or distinct counting where needed.
- Detail inspection tools by ID.

Avoid creating a synthetic dimension merely to populate a multi-million-row dropdown. UIs should provide bounded search, scoped filters, and permission checks.

## 12. Access control and protecting transaction identifiers

Transaction codes sometimes embed organization, store, issue-date, or sequence details usable to look up personal records. Placing DDs directly in facts simplifies tracing while also **exposing identifiers across many rows**.

Practical requirements:

- **Enforce tenant isolation** when viewing or searching orders; prevent arbitrary filters from crossing authorized boundaries.
- **Hide full sensitive identifiers** from groups needing only summary dashboards.
- Restrict detailed data exports without an approved purpose.
- Enforce permissions and audit logging on drill-through actions.
- Define retention and purge policies for facts and report exports containing DDs.
- If tokenizing or hashing, distinguish **true anonymization** from linkable pseudonymization. Simple hashes of structured/guessable IDs rarely provide strong protection.

A DD is a **modeling choice**, not a security control. Layer access controls across the DBMS, semantic layer, application, and pipeline as appropriate.

## 13. Data quality testing and reconciliation

### 13.1. A fact row must be unique at the declared grain

~~~sql
SELECT
    tenant_id,
    order_number,
    line_no,
    COUNT(*) AS occurrences
FROM fact_order_lines
GROUP BY tenant_id, order_number, line_no
HAVING COUNT(*) > 1;
~~~

With an enforced primary key in DDL, this normally returns zero rows. In staging tables or analytical engines that **do not enforce UNIQUE**, run this check before loading.

### 13.2. Prevent conflicting order-level attributes on the same order

By business rule, all lines of a confirmed order must share the same confirmation date and customer:

~~~sql
SELECT
    tenant_id,
    order_number,
    COUNT(DISTINCT confirmed_date) AS confirmed_dates,
    COUNT(DISTINCT customer_key) AS customer_versions
FROM fact_order_lines
GROUP BY tenant_id, order_number
HAVING COUNT(DISTINCT confirmed_date) > 1
    OR COUNT(DISTINCT customer_key) > 1;
~~~

This test is valid **when the business confirms** an order has one confirmation date and one corresponding customer/version at that instant. If ETL assigns the wrong `customer_key` version, discrepancies surface for investigation.

This query does not catch every bug: `COUNT(DISTINCT)` ignores NULLs, and an order could be missing all lines. Pair it with `NOT NULL` constraints, source checks, and order-level reconciliation.

### 13.3. Reconciling metrics per document

~~~sql
WITH fact_totals AS (
    SELECT
        tenant_id,
        order_number,
        COUNT(*) AS fact_lines,
        SUM(booked_amount) AS fact_booked_amount
    FROM fact_order_lines
    GROUP BY tenant_id, order_number
),
source_totals AS (
    SELECT
        tenant_id,
        order_number,
        COUNT(*) AS source_lines,
        SUM(quantity * unit_price_at_order - line_discount_amount)
            AS source_booked_amount
    FROM staging_confirmed_order_lines
    GROUP BY tenant_id, order_number
)
SELECT
    COALESCE(s.tenant_id, f.tenant_id) AS tenant_id,
    COALESCE(s.order_number, f.order_number) AS order_number,
    s.source_lines,
    f.fact_lines,
    s.source_booked_amount,
    f.fact_booked_amount
FROM source_totals AS s
FULL OUTER JOIN fact_totals AS f
  ON f.tenant_id = s.tenant_id
 AND f.order_number = s.order_number
WHERE s.source_lines IS DISTINCT FROM f.fact_lines
   OR s.source_booked_amount IS DISTINCT FROM f.fact_booked_amount;
~~~

`staging_confirmed_order_lines` and its columns are **assumed inputs**; ensure identical scope, currency, confirmation state, formulas, rounding rules, and cutoff timestamp before comparing. `IS DISTINCT FROM` is PostgreSQL syntax that handles NULL comparisons cleanly.

This query catches mismatches at the **full document identifier** level. Reconciling only monthly grand totals can miss **offsetting errors**.

### 13.4. Data reloads must be idempotent

A line-confirmation event can be redelivered. Pipelines must enforce:

~~~text
natural grain key =
    (tenant_id, order_number, line_no)
~~~

and apply the right load strategy:

- **Upsert** when sources emit updatable line states, with rules selecting the latest valid version.
- **Idempotent insert** when sources emit immutable events, preventing duplicate copies of the same event.
- **Separate adjustment events** when post-confirmation edit history must be retained.
- **Quarantine** when two records share the business grain yet carry conflicting content without a resolution rule.

Blindly using `ON CONFLICT DO NOTHING` without inspecting content differences can **hide data corruption**. If the true business key includes a version or source system, lock down the grain before applying load rules.

## 14. Connections to relational, document, graph, and analytical models

| Model type | Role of transaction identifiers | Key considerations |
|---|---|---|
| **Relational OLTP** | Primary key of `orders`, `invoices`; foreign key on detail lines | Requires referential integrity and document lifecycle handling |
| **Analytical star schema** | DDs like `order_number` live directly in line-level facts | No ID-only `dim_order` needed; run distinct counts with proper scope |
| **Document** | `order_number` is metadata on an order document embedding a lines array | When flattening to line-level facts, carry order code to each line and verify grain |
| **Graph** | ID of event/order nodes or edge property | Multiple paths reaching the same order do not imply multiple orders |
| **Columnar / data lake** | Document ID stored in Parquet/columnar facts for drill-through | High cardinality affects compression, partitioning, clustering, and distinct counts |

In OLTP, `orders` is a **first-class managed entity** and is never deleted just because analytics uses a DD. The goal of a DD is to **avoid redundant dimension tables in analytical models**, not to erase the order entity from the whole system.

In document stores, an order with an `items[]` array is read as one cohesive object; when flattened into a line-item fact table, `order_number` is intentionally repeated on each item for lookup. That does not violate analytical modeling principles, provided you avoid repeating **order-level totals** onto each line and summing them erroneously.

## 15. Common misconceptions

| Misconception | Why it is wrong | Fix |
|---|---|---|
| "Degenerate dimension means defective data" | *Degenerate* names a design pattern | Understand it as a business identifier stored in the fact |
| "Every dimension must have its own table" | Transaction IDs may have no descriptive attributes to split out | Keep DD directly in the fact |
| "`order_number` is the PK of a line-item fact" | One order has multiple lines | Key must include `line_no` and required scope |
| "Order numbers are globally unique" when unique only per tenant | Accidentally merges orders across tenants | Use complete `(tenant_id, order_number)` |
| "With a DD, no order-level fact is needed" | Order-level KPIs/measures may exist | Design a separate order-level fact when justified |
| "Must build `dim_order` for fast JOINs" | An ID-only table often just adds overhead | Measure, index, and inspect workload first |
| "Sharing a DD lets two facts JOIN directly" | Easily causes many-to-many fanout | Aggregate to a shared grain before joining |
| "`COUNT(*)` equals order count" in a line-item fact | Counts item lines, not documents | `COUNT(DISTINCT)` on full ID |
| "Count orders per category then sum across categories" | One order can span multiple categories | Distinct count over the full requested scope |
| "DDs must have SCD2 history" | Identifiers themselves rarely have versioned attribute sets | History belongs on descriptive dimensions or event facts |
| "Adding a fact surrogate key solves duplicates" | Technical keys do not replace business grain | Enforce natural grain key |
| "Can drop tenant when searching by order number" | Wrong identity scope and possible auth breach | Filter using valid namespace |
| "Keeping DD in the fact permits unrestricted queries" | DDs can be sensitive | Enforce permissions, masking/tokenization, and retention |
| "Fix bugs using `SUM(DISTINCT amount)`" | Two real lines can share the same dollar amount | Fix grain/JOINs; never distinct on measures |

## 16. Practice exercises with solutions

### Exercise 1 — Identifying a degenerate dimension

`fact_invoice_lines(invoice_number, line_no, product_key, date_key, quantity, line_amount)` holds invoice numbers without a `dim_invoice` table. Can `invoice_number` be a DD?

**Solution:** **Yes**, if it is a business document identifier used for lookup/grouping/drill-through and lacks a separate descriptive dimension table. Verify the uniqueness scope of invoice numbers. Since invoices have multiple lines, `invoice_number` is **not** the unique key of the line-item fact.

### Exercise 2 — Counting orders and lines

A fact has 4 rows: `(T01,O1,1)`, `(T01,O1,2)`, `(T01,O2,1)`, `(T02,O1,1)`. How many lines and how many distinct orders exist?

**Solution:** **4 lines** and **3 orders** by `(tenant_id, order_number)`: `(T01,O1)`, `(T01,O2)`, `(T02,O1)`. A standalone `COUNT(DISTINCT order_number)` sees only two codes `O1, O2` and **miscounts**.

### Exercise 3 — Should `dim_order` be created?

A team proposes `dim_order(order_key, order_number)` with no other descriptive attributes solely to "normalize dimensions."

**Solution:** Usually **unnecessary** in a star schema if the fact can hold `order_number` for drill-through/counting. An ID-only table adds ETL and JOIN overhead for no analytical gain. If proven linkage, security, cardinality, or complex history needs exist, evaluate them specifically rather than applying an absolute rule.

### Exercise 4 — Fact key

An order contains three product lines. If `PRIMARY KEY(order_number)` is placed on `fact_order_lines`, what happens?

**Solution:** The database rejects inserting more than one line per order code. The key must reflect the grain, such as `(tenant_id, order_number, line_no)`, or a stable line ID paired with a business uniqueness constraint.

### Exercise 5 — Counting orders by product

Order `O1` has two products P1 and P2; order `O2` has only P1. A report shows `orders_with_product` = 2 for P1 and 1 for P2. Can those be summed to 3 orders?

**Solution:** No. There are **2 distinct orders**. `O1` appears in both groups; summing `COUNT(DISTINCT)` across overlapping groups double-counts.

### Exercise 6 — DD and order-level amounts

A three-line order has an order-wide shipping fee of 30,000. If `shipping_fee=30,000` is copied onto each fact row and summed, what is the result? How should this be modeled?

**Solution:** The erroneous sum is **90,000**. Keep the fee in an order-level `fact_orders`, or allocate it down to lines with an explicit rule and reconciliation check confirming allocated fees sum to 30,000. A DD does not turn an order-level measure into a line-level measure.

### Exercise 7 — Joining across two processes

An order has three item lines and two payments. Joining `fact_order_lines` to `fact_payments` on order code produces how many rows, and why can't amounts be summed directly?

**Solution:** \(3\times2=6\) rows. Item lines repeat twice; payments repeat three times. Aggregate each fact to **order grain** before joining, then compare booked vs. paid amounts.

### Exercise 8 — Two invoice-number scopes

Two stores both use invoice `0001` every year. What must you store to reconcile accurately?

**Solution:** Confirm the identifier scope and store full `(store_id, fiscal_year, invoice_number)` or a guaranteed global ID. Never store only `invoice_number='0001'` and take distinct counts across stores/years.

### Exercise 9 — Identifier changing upon confirmation

A draft order has code `TMP-1`, then receives `INV-2026-001` upon confirmation. The system wants to trace history from draft to confirmation. Should `INV-2026-001` be used as the sole stable identifier for all prior events?

**Solution:** Not automatically. You need a **stable source/order ID** or verified mapping linking both codes, retaining the code valid at each transaction if auditing requires it. Display DDs and immutable IDs play different roles.

### Exercise 10 — SCD2 dimension and DD

Product SP01 moves category from "Books" to "Gifts." An older order line must retain its category at purchase time. Should the order number or the dimension be updated?

**Solution:** `order_number` is a DD and unrelated to product classification. The fact must use `product_key` pointing to the `dim_product` version valid at purchase time (SCD2) or a governed descriptive snapshot. Never alter `order_number` to handle category history.

### Exercise 11 — Searchability and high cardinality

A fact has 100 million distinct `order_number` values. Users ask for a dropdown list containing every code to pick from.

**Solution:** That UI pattern is unfit for a high-cardinality DD. Use **targeted search, tenant/date filters, bounded results, and drill-through**. Benchmark appropriate indexes/partitions rather than creating a 100-million-row dimension just for a dropdown.

### Exercise 12 — A fact row with a surrogate key

`fact_order_lines` includes an auto-generated `fact_row_key`. ETL writes two rows with different `fact_row_key` values yet identical `(tenant_id, order_number, line_no)`. Is this valid?

**Solution:** **Not valid** if the grain specifies a unique row for that triple. A surrogate key only guarantees two technical rows have different IDs; it does not prove two valid business events occurred. Inspect the source, deduplicate, and handle conflicting records.

## 17. Checklist when using transaction identifiers as degenerate dimensions

- [ ] Written an explicit **grain statement** for the fact.
- [ ] Verified the code used as a DD is a **business identifier**, not an accidental string that happens to look unique.
- [ ] Defined the **namespace**: tenant, store, year, source system, or global ID.
- [ ] Distinguished the DD from the **fact-row business key**, surrogate keys, and dimension FKs.
- [ ] Evaluated whether a **real** descriptive dimension table is needed or keeping the ID directly in the fact suffices.
- [ ] Verified order-level measures are not **repeated per line** and summed multiple times.
- [ ] Designed **order-level / adjustment / status facts** when KPIs exist at other grains.
- [ ] Verified **`COUNT(DISTINCT)`** uses the full scope and avoids summing distinct counts across overlapping groups.
- [ ] Verified multi-fact JOINs do not create **fanout**; pre-aggregated each fact when needed.
- [ ] Distinguished **display codes** from stable source identifiers and code-change policies.
- [ ] Handled reloads, duplicates, late events, and post-confirmation update rules.
- [ ] Measured the impact of high-cardinality DDs on indexes, storage, search, and BI.
- [ ] Verified tenant access controls, identifier sensitivity, and retention policies.
- [ ] Established drill-through queries and reconciliation workflows by **complete document identifier**.

**Takeaway:** A **degenerate dimension** is a transaction identifier **stored directly in the fact table** for tracing, filtering, grouping, and counting documents, **without needing an ID-only dimension table**. This pattern simplifies star schemas yet **never changes grain**: one order code can accompany multiple fact lines, multiple payments, or multiple shipments. To keep metrics accurate, verify **complete business keys, grain-matched measures, JOIN cardinality, and identifier lifecycles** before physical optimization.
