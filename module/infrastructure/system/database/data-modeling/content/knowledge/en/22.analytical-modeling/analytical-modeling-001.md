# Distinguishing OLTP Transactional Needs from OLAP Analytical Needs

## Learning Objectives

After this lesson, you will be able to:

- Distinguish **OLTP** (*Online Transaction Processing*) and **OLAP** (*Online Analytical Processing*) based on **business goals, query types, consistency levels, and workload characteristics**, rather than just database product names.
- Translate a requirement such as "placing an order must not oversell inventory" into a transactional model, and a requirement such as "revenue by category over 12 months" into an analytical model with clear **grain, facts, dimensions, and metrics**.
- Explain why normalization, keys, constraints, indexes, and transactions typically serve OLTP, while event tables, star schemas, columnar storage, partitioning, and aggregations serve many types of OLAP.
- Recognize measurement traps: double-counting on JOINs, wrong recognition timestamps, pricing by current catalog instead of transaction-time price, mixing statuses, and late updates.
- Design a data pipeline from operational systems to analytics using batch/CDC with quality checks, idempotency, late-arriving event handling, and history management.
- Choose an appropriate architecture when you only have a single database, need a read replica, a data warehouse, a near-real-time model, or a hybrid approach (*HTAP*).

In the **DATABASE_DATA_MODELING** module, the same business domain may require **two different ways of looking at data**. The sales system must accurately accept or reject an order the moment a customer clicks "Place Order". Meanwhile, the business team wants to view trends in order counts, customer counts, and sales value by time, category, or channel. Those two needs are not necessarily best served by the same schema, the same set of indexes, and the same query strategy. This is the meaning of distinguishing **OLTP** from **OLAP** in the **Analytical Modeling** chapter.

## 1. Start from the Business Question, Not the Database Product

Suppose a retailer has a website receiving thousands of cart, order placement, inventory reservation, and refund commands. Management simultaneously asks:

- **"Can customer A place an order for two units of product P right now?"** You must check quantity and reserve inventory atomically, then record the order and respond.
- **"In the last 90 days, how much did paid sales grow compared to the previous 90 days, broken down by category at the time of sale?"** You must read a large volume of transactions, group by date and category, compare periods, and protect KPI semantics.
- **"As of 9:00 AM today, how many products are at risk of running out of stock?"** This may be a near-real-time operational problem; you need to determine how exact the figures must be for users and what latency is acceptable.

The first two questions represent two types of processing:

- **OLTP:** executes **specific business state changes**, typically reading/writing a small number of records, requiring transactions and constraints so operational state does not become corrupted.
- **OLAP:** answers **questions involving aggregation, comparison, segmentation, and historical analysis**, typically reading many rows/columns over long periods, primarily read-heavy.

OLTP/OLAP are **ways of describing workloads and processing goals**, not permanent labels for PostgreSQL, MySQL, a document database, or a data warehouse. A PostgreSQL instance can still run aggregate queries; a warehouse can ingest data frequently. What matters is the primary workload, the ability to preserve invariants, and the cost when those workloads run together.

## 2. Comparison Table of Decisive Differences

| Aspect | OLTP — Operational Transactions | OLAP — Analytical Queries |
| --- | --- | --- |
| Typical questions | "Is this order confirmed?", "Is there enough stock?" | "How do sales change by month, region, and category?" |
| Primary operations | Controlled INSERT/UPDATE/DELETE; point reads, narrow range reads | Filtering, JOIN, GROUP BY, window functions, aggregations across many records |
| Object of interest | A single order, account, inventory reservation, payment session | A set of transactions, segments, time series, distributions |
| Write path | Many short, concurrent transactions | Batch, micro-batch, stream/CDC ingestion; historical corrections per policy |
| Consistency | Invariants must hold when the transaction commits | Figures usually have a **defined freshness lag**; must be semantically accurate and reconcilable |
| Data volume per query | Typically small and keyed by predicates | Can be very large, spanning many days/months/years |
| Performance goals | Fast command response, write throughput, low contention | Fast reads and aggregations, supporting many concurrent report users |
| Common data design | Business entities, appropriate normalization, foreign keys, constraints | Facts/dimensions, star schema, wide tables, aggregate tables, columnar |
| Indexes/access strategy | PK, UNIQUE, B-tree aligned with query paths and write conditions | Partition pruning, columnar scan, compression, clustering/sort keys, materialized aggregates |
| History | Current state and history required for operations/auditing | Long history, snapshots, events, time-varying dimensions |
| Primary risks | Lost update, write skew, deadlock, partial writes, invariant violations | Double-counting, ambiguous KPI definitions, late data, wrong grain or wrong history |

Do not interpret "OLAP tolerates stale lag" from the consistency row as "OLAP accepts wrong data." **Analytical results must still be exact with respect to the data, cutoff timestamp, and KPI definition they publish.** What can differ from OLTP is the latency between transaction commit and when the analytical copy reflects it.

## 3. OLTP Example: Recording an Order Correctly Under Concurrency

The operational system stores Order and OrderLine. An order has multiple lines; the customer can only confirm the order when inventory is reserved according to policy. An illustrative relational schema:

~~~sql
CREATE SCHEMA IF NOT EXISTS shop;

CREATE TABLE shop.orders (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    customer_id UUID NOT NULL,
    status VARCHAR(16) NOT NULL
        CHECK (status IN ('DRAFT', 'RESERVED', 'PAID', 'CANCELLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    paid_at TIMESTAMPTZ,
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    PRIMARY KEY (tenant_id, order_id),
    CHECK (status <> 'PAID' OR paid_at IS NOT NULL)
);

CREATE TABLE shop.order_line (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id UUID NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_vnd BIGINT NOT NULL CHECK (unit_price_vnd >= 0),
    PRIMARY KEY (tenant_id, order_id, line_no),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES shop.orders (tenant_id, order_id)
);

CREATE TABLE shop.stock_balance (
    tenant_id UUID NOT NULL,
    warehouse_id UUID NOT NULL,
    product_id UUID NOT NULL,
    available_quantity INTEGER NOT NULL CHECK (available_quantity >= 0),
    version BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, warehouse_id, product_id)
);

CREATE INDEX orders_by_customer
    ON shop.orders (tenant_id, customer_id, created_at DESC);
~~~

**Meaning of the structures:**

- The composite key by tenant protects identifier scope; write paths must verify tenant authorization beyond just having a valid ID.
- Foreign keys ensure order lines belong to an existing order, but **do not automatically** ensure inventory reservation or payment success.
- CHECK validates local constraints such as positive quantity and allowed status values.
- The index by customer serves the query "recent orders of this customer". You should not create indexes on the operational database for every ad-hoc GROUP BY requested by management.
- The purchased price is stored on the order line: changing the Catalog price today does not alter the committed amount of yesterday's order.

### An Inventory Reservation Operation Must Have an Arbitration Point

For a line that needs to reserve two units of stock, you can use a conditional UPDATE inside a transaction:

~~~sql
BEGIN;

UPDATE shop.stock_balance
SET available_quantity = available_quantity - :quantity,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND warehouse_id = :warehouse_id
  AND product_id = :product_id
  AND :quantity > 0
  AND available_quantity >= :quantity
RETURNING available_quantity;

-- If not exactly one row was updated:
-- ROLLBACK, report out-of-stock/record not found; do not record reservation as successful.
-- If there are multiple lines, iterate in a deterministic lock order within the same transaction.
-- Record reservation, update order status, and write to outbox in the same transaction
-- when all data resides in the same database and policy requires it.

COMMIT;
~~~

Two requests both asking for the last remaining units must not simply SELECT `available_quantity` and subtract in application memory. In PostgreSQL, a conditional UPDATE on **the same stock row** protects the check and decrement atomically within the transaction boundary. If inventory is a separate service/database, Order cannot treat its own UPDATE as a distributed transaction; it needs a reservation lease from the authoritative source and an intermediate state.

**OLTP key takeaway:** post-COMMIT state must uphold invariants. The speed of counting all 100 million order lines is not the top priority on the inventory reservation write path.

## 4. OLAP Example: Sales Require a Different Dataset and Semantics

Suppose a manager asks: **"In October, what was the total value of paid goods sold by product category?"** The query may require:

1. Selecting orders that reached the appropriate status by **payment date**.
2. Taking each order line and its **unit price at the time of sale**.
3. Attaching the product category valid at **the time required by the business**, not defaulting to the latest category.
4. Grouping by category and summing sales.
5. Eliminating duplicate records caused by reloads or by JOINing to a payment table with multiple rows.

A direct query on OLTP might look like this (assuming the current category is stored in a Catalog table in the same database):

~~~sql
SELECT p.category_name,
       SUM(l.quantity::BIGINT * l.unit_price_vnd) AS paid_sales_vnd
FROM shop.orders AS o
JOIN shop.order_line AS l
  ON l.tenant_id = o.tenant_id AND l.order_id = o.order_id
JOIN shop.product AS p
  ON p.tenant_id = l.tenant_id AND p.product_id = l.product_id
WHERE o.status = 'PAID'
  AND o.paid_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND o.paid_at <  TIMESTAMPTZ '2026-11-01 00:00:00+07'
GROUP BY p.category_name;
~~~

**`shop.product` is an assumed table for illustration, without DDL shown above.** The query has several limitations:

- If an order was PAID and later refunded, SUM over order lines does not automatically subtract the refunded amount.
- If `product.category_name` changed after the sale, historical transactions get attributed to the **current** category instead of the category **at the time of sale**.
- If you JOIN to a payment table that has multiple payment attempts per order, sales rows can be **multiplied**.
- If a huge volume of orders is scanned concurrently, reporting can contend for CPU, cache, I/O, and resources with OLTP write paths, even though MVCC reduces read/write blocking in many situations.

The SQL itself is not broken: it answers a **specific definition**, namely "line value of orders currently in PAID status, grouped by current product category". However, that definition **might not be** the KPI management is actually asking for. Moving to OLAP starts with **choosing the right measurement model**, and only then optimizing speed.

## 5. Grain: The Most Important Decision Before Building a Fact Table

**Grain** is a complete sentence describing **what one row in a fact table represents**. Choose the grain before listing measures, dimensions, and indexes.

Several candidates:

| Candidate Grain | What Is One Row? | Suitable For | Should Not Infer |
| --- | --- | --- | --- |
| One Order | An order created/paid | Order count, order-level totals, order conversion rate | Product quantities per category without line detail |
| One OrderLine at payment | A line item belonging to an order when payment completes per convention | Quantity sold, sales value by product | Each row is an independent order |
| One PaymentAttempt | A single payment attempt | Success rate by method/gateway | Each attempt is a new purchase |
| One completed RefundLine | A completed refund line for a sold line | Refund value, returned quantity by product | Represents a positive sales transaction |
| One daily InventorySnapshot | Stock state of a product in a warehouse at end of day | Point-in-time stock, trends, and out-of-stock days | SUM of stock across days equals point-in-time stock |

This example chooses two fundamental facts:

- **fact_paid_order_line**: each row represents **one OrderLine recognized as sold once when the order is paid in full**. We assume each order is paid once for the entire order; we exclude split payments, partial captures, or multi-shipment sales. The business key is `(tenantId, orderId, lineNo)`.
- **fact_completed_refund_line**: each row represents **one completed refund line** for a specific sales line, with its own `refundLineId`. A sales line may have multiple refunds per policy.

A declared grain answers what to SUM, what to COUNT, and which JOINs would create duplicates.

### Additive, Semi-Additive, and Non-Additive Measures

| Measure | Property | How to Use |
| --- | --- | --- |
| Quantity sold (sales line) | Usually **additive** across products/time under the same definition | `SUM(quantity)` |
| Sales value VND (sales line) | Additive within the same currency and recognition rules | `SUM(gross_amount_vnd)` |
| End-of-day stock | **Semi-additive**: add across products/warehouses on the same day, do not add across days for current stock | Take snapshot at the appropriate point in time |
| Average order value | **Non-additive**: do not arbitrarily SUM or average precomputed ratios | `SUM(amount) / COUNT(DISTINCT order_id)` |
| Payment success rate | Non-additive | `SUM(successful_attempts) / SUM(total_attempts)`, avoid unweighted AVG of sub-ratios |
| Unique customers | Cannot sum monthly COUNT DISTINCT values to get quarterly unique customers | `COUNT(DISTINCT customer_id)` over the appropriate scope |

There is no single "revenue measure" valid in every context. Accounting may recognize revenue on delivery date, acceptance date, performance obligation allocation, or other rules. This lesson uses **paid goods value**, and does not automatically equate it with accounting revenue.

## 6. Star Schema: Facts and Dimensions Serving Analytics

A typical **star schema** places the fact at the center and dimensions around it. The fact records measured events at the chosen grain; dimensions provide context for filtering/grouping:

~~~mermaid
flowchart TB
    F["fact_paid_order_line<br/>1 sales line when order is PAID"]
    D1["dim_product<br/>name, category at point in time"]
    D2["dim_date<br/>day, month, quarter, year"]
    D3["dim_channel<br/>web, mobile, store"]
    D4["dim_customer<br/>segments with access control"]
    F -->|"product_key"| D1
    F -->|"paid_date_key"| D2
    F -->|"channel_key"| D3
    F -->|"customer_key"| D4
~~~

Differences compared to an ERD for transactional processing:

- Facts intentionally store **dimension surrogate keys** to preserve historical attribute versions.
- Descriptive data is usually grouped inside dimensions, **not necessarily deeply normalized** into many small tables.
- Business keys such as `orderId` and `lineNo` can remain in the fact as **degenerate dimensions** for lineage and order counting, instead of creating `dim_order` solely to hold IDs.
- Facts are typically much larger than dimensions; queries scan many fact rows but only the needed columns. Columnar storage, partitioning, and workload-aligned data organization can be beneficial.

### Concrete Data Example

An order `O-101` has two lines:

| Sales Line | Product | Quantity | Unit Price at Sale | Line Total |
| --- | --- | ---: | ---: | ---: |
| (O-101, 1) | T-shirt | 2 | 100,000 VND | 200,000 VND |
| (O-101, 2) | Cap | 1 | 50,000 VND | 50,000 VND |

After the order is paid, the fact table has **two rows**, not one. Total sales value is 250,000 VND, while **order count = 1**, not 2. If 100,000 VND is later refunded for one T-shirt, the refund fact records a negative/separate row per the published convention, rather than deleting the historical sale as if it never happened.

With a fact where one row is an OrderLine, `COUNT(*)` returns **the number of sales lines**; to count **orders**, use `COUNT(DISTINCT order_id)` within the appropriate tenant scope or a separate fact table at order grain.

## 7. OLAP Schema Example in PostgreSQL

So learners can read familiar SQL syntax, the following example uses PostgreSQL as an **illustrative tool**. In practice, a warehouse may use a dedicated analytical engine with different key types, data types, indexes, and partitioning mechanisms. Do not treat the PostgreSQL configuration here as optimal for every warehouse.

~~~sql
CREATE SCHEMA IF NOT EXISTS mart;

CREATE TABLE mart.dim_product (
    product_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id UUID NOT NULL,
    product_id UUID NOT NULL,
    category_name TEXT NOT NULL,
    product_name TEXT NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    CHECK (valid_to IS NULL OR valid_to > valid_from),
    UNIQUE (tenant_id, product_id, valid_from)
);

CREATE TABLE mart.fact_paid_order_line (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    line_no INTEGER NOT NULL,
    product_key BIGINT NOT NULL REFERENCES mart.dim_product(product_key),
    customer_id UUID NOT NULL,
    paid_at TIMESTAMPTZ NOT NULL,
    paid_date DATE NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    gross_amount_vnd BIGINT NOT NULL CHECK (gross_amount_vnd >= 0),
    load_batch_id UUID NOT NULL,
    PRIMARY KEY (tenant_id, order_id, line_no)
);

CREATE TABLE mart.fact_completed_refund_line (
    tenant_id UUID NOT NULL,
    refund_line_id UUID NOT NULL,
    order_id UUID NOT NULL,
    order_line_no INTEGER NOT NULL,
    product_key BIGINT NOT NULL REFERENCES mart.dim_product(product_key),
    refunded_at TIMESTAMPTZ NOT NULL,
    refunded_date DATE NOT NULL,
    refunded_quantity INTEGER NOT NULL CHECK (refunded_quantity > 0),
    refund_amount_vnd BIGINT NOT NULL CHECK (refund_amount_vnd >= 0),
    load_batch_id UUID NOT NULL,
    PRIMARY KEY (tenant_id, refund_line_id)
);

CREATE INDEX fact_sales_by_date_product
    ON mart.fact_paid_order_line (tenant_id, paid_date, product_key);

CREATE INDEX fact_refund_by_date_product
    ON mart.fact_completed_refund_line (tenant_id, refunded_date, product_key);
~~~

**Choices to understand:**

- `fact_paid_order_line` retains the **business key** `(tenantId, orderId, lineNo)` so load retries do not create duplicate sales rows. If an order can be paid in partial installments, this grain must **be redesigned**; do not force the old key when requirements change.
- `product_key` is a surrogate key pointing to the **selected dimension version**. The source `product_id` column remains in `dim_product` for traceability.
- `paid_date`/`refunded_date` represent the date in the **agreed reporting timezone**. If there are multiple tenants with distinct timezones, the pipeline must apply each tenant's timezone at the exact event timestamp and document the conversion policy. Never silently cast UTC dates as local business dates.
- `gross_amount_vnd` and `refund_amount_vnd` are integer VND amounts, never mixing currencies; the name `gross` here means **paid order-line value per lesson convention**, excluding complex taxes/shipping/discounts.
- Foreign keys in this illustrative example help detect missing `product_key` references; many specialized warehouses do not enforce FKs like OLTP, so data quality must be validated in the pipeline.
- These two indexes are reasonable choices for the sample queries but may not be optimal on columnar storage. Partitioning/clustering should be based on actual volume and query patterns.

### SCD Type 2: Product Categories Changing Over Time

Suppose on Oct 01 product `P` belongs to category "Accessories", and on Oct 15 it is moved to "Devices". If the analytical requirement is **"by category at the time of sale"**, `dim_product` must retain history:

| product_key | product_id | category_name | valid_from | valid_to |
| ---: | --- | --- | --- | --- |
| 101 | P | Accessories | 2026-01-01 00:00+07 | 2026-10-15 00:00+07 |
| 205 | P | Devices | 2026-10-15 00:00+07 | NULL |

The pipeline maps a sale on Oct 10 to `product_key=101` and a sale on Oct 20 to `product_key=205`. Effective intervals follow the **`[valid_from, valid_to)`** convention: inclusive start, exclusive end. You must ensure **no two overlapping versions** exist for the same `(tenantId, productId)`; `UNIQUE` on `(tenantId, productId, valid_from)` above is **not sufficient** to prevent overlaps. This can be checked in ETL or enforced using range constraints where the DBMS supports them.

If the business wants **all historical transactions classified under today's category**, a different query or dimension structure may be suitable. These are **two valid questions that produce different answers**. The designer must explicitly document which one was chosen.

## 8. Writing OLAP Queries with the Right Grain and Point in Time

**Requirement A:** value of paid goods sold by category **at the time of sale**, in October 2026, for a tenant:

~~~sql
SELECT p.category_name,
       SUM(f.quantity) AS items_sold,
       SUM(f.gross_amount_vnd) AS paid_sales_vnd,
       COUNT(DISTINCT f.order_id) AS distinct_orders_in_category
FROM mart.fact_paid_order_line AS f
JOIN mart.dim_product AS p
  ON p.product_key = f.product_key
 AND p.tenant_id = f.tenant_id
WHERE f.tenant_id = :tenant_id
  AND f.paid_date >= DATE '2026-10-01'
  AND f.paid_date <  DATE '2026-11-01'
GROUP BY p.category_name
ORDER BY paid_sales_vnd DESC;
~~~

**Note:** `distinct_orders_in_category` is the count of orders **containing at least one product in that category**; an order purchasing items from two categories is counted in both groups. You must not SUM these counts to conclude the total unique orders for the entire month.

**Requirement B:** "paid goods value minus completed refunds occurring on each day". This is **daily net sales and refund flow by event date**, **not** an accounting revenue metric:

~~~sql
WITH daily_movements AS (
    SELECT tenant_id,
           paid_date AS business_date,
           SUM(gross_amount_vnd) AS amount_vnd
    FROM mart.fact_paid_order_line
    WHERE tenant_id = :tenant_id
      AND paid_date >= DATE '2026-10-01'
      AND paid_date <  DATE '2026-11-01'
    GROUP BY tenant_id, paid_date

    UNION ALL

    SELECT tenant_id,
           refunded_date AS business_date,
           -SUM(refund_amount_vnd) AS amount_vnd
    FROM mart.fact_completed_refund_line
    WHERE tenant_id = :tenant_id
      AND refunded_date >= DATE '2026-10-01'
      AND refunded_date <  DATE '2026-11-01'
    GROUP BY tenant_id, refunded_date
)
SELECT business_date,
       SUM(amount_vnd) AS net_paid_minus_refunded_vnd
FROM daily_movements
GROUP BY business_date
ORDER BY business_date;
~~~

In this example, a sale on Oct 31 and a refund on Nov 02 are recorded on **two different dates**. If the question instead asks "final net value of orders originating in October", you need a **cohort by sale date** and must link refunds back to the original sales line — that is a different metric and cannot be fixed merely by renaming a column. Furthermore, the query only returns **dates with activity**; to display dates with zero transactions, JOIN with `dim_date` or a complete date series and `COALESCE` to 0.

### Common GROUP BY Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| JOINing sales fact with every payment attempt of an order | A single sales line is multiplied several times | Build facts at deliberate grains; aggregate/deduplicate the source beforehand |
| Running `COUNT(*)` on an order-line fact and labeling it "order count" | Counts lines, not orders | `COUNT(DISTINCT order_id)` within scope or use `fact_order` |
| Using `SUM(DISTINCT amount)` to patch double-counting | Distinct transactions with identical amounts are wrongly collapsed | Fix the key/grain and handle the JOIN properly |
| JOINing an SCD2 dimension by `productId` without a timestamp | One fact matches multiple product versions | Link the fact to the version-specific `product_key` |
| Using current price to calculate historical sales value | History changes meaning whenever Catalog updates prices | Use the price snapshot captured on the transaction |
| SUMming end-of-day stock across an entire month | Sums repeated snapshots across time | Use period-end value, defined daily average, or an appropriate metric |
| Unweighted AVG of daily rates | Overall rate is wrong when denominators differ | Sum numerators and denominators first, then divide |

## 9. Architecture for Moving Data from OLTP to OLAP

A common architecture separates the authoritative write path from the analytical path:

~~~mermaid
flowchart LR
    U["Ordering App"] --> T[("OLTP DB<br/>Orders, Stock, Payments")]
    T --> X["Batch/CDC<br/>extract"]
    X --> Q["Raw/Staging<br/>reconcile & dedup"]
    Q --> M["Transform<br/>grains, SCD, metrics"]
    M --> W[("OLAP Store<br/>facts + dimensions")]
    W --> B["Dashboard / BI / SQL"]
    W --> A["Data quality & reconciliation"]
    A -.->|"reconcile discrepancies"| Q
~~~

**There is no rule restricting you to a single transport path.** Options include:

- **Batch ETL/ELT:** hourly/daily extraction and transformation, easy to operate when ultra-low freshness is unnecessary.
- **CDC (Change Data Capture):** reads committed change rows from logs or equivalent mechanisms, supporting near-real-time; requires understanding format, transaction boundaries, ordering, and deletes.
- **Outbox/domain events:** provides business facts like `OrderPaid` and `RefundCompleted` rather than raw row-level UPDATEs; clean contracts, but must ensure no analytically relevant business events are omitted.
- **Read replica:** offloads certain read queries from the OLTP primary, yet typically retains the same schema/storage layout; incurs replication lag and does not inherently solve star schemas, dimension history, or metric definitions.
- **Materialized views/summary tables in the same DB:** effective for suitable scale and SLAs; requires managing refresh schedules, updates, and resource contention.

Combining an initial batch snapshot with subsequent CDC requires a **consistent cutover point**. If you snapshot the entire table while concurrently reading the log without a high-watermark or handoff protocol, the pipeline can lose or duplicate changes sitting right on the boundary between the two phases.

## 10. Data Freshness, Consistency, and Acceptance Thresholds

A reporting requirement must state **up to what point in time the data is fresh**, not simply say "real-time":

| Need | Example Freshness SLA (Illustrative) | Candidate Architecture |
| --- | --- | --- |
| Month-end close | Official period cutoff, reconciled and approved | Versioned batch, snapshot/frozen release |
| Executive dashboard | ~15–60 minute lag if acceptable | Micro-batch or CDC |
| Campaign monitoring | Seconds/minutes lag, acceptable threshold documented | Stream/CDC with projections and monitoring |
| Balance check to authorize a transaction | Must be accurate at authorization time, never rely on a lagging copy | OLTP/source of truth and atomic command |

The lag windows in the table are **examples** to clarify with business owners, not mandatory standards. Freshness is the elapsed time between the source event and when the figure becomes available on the dashboard; **correctness** is whether, when claiming "data as of 10:00", the dataset genuinely covers that exact scope.

A blazing-fast dashboard that silently misses recently arrived transactions, drops refunds, or uses the wrong metric definition is **less trustworthy than** a dashboard delayed by 15 minutes with explicit watermarks and reconciliation.

### Event Time, Processing Time, and Business Date

- **Event time:** when the business action actually occurred (e.g., `paid_at`).
- **Processing time:** when the pipeline received and processed the record.
- **Business date:** the classification date per reporting calendar/timezone/scope.

A transaction paid at 23:59 Vietnam time but delivered to the warehouse via CDC at 00:05 the next day still belongs to the **previous payment date** if the KPI groups by `paid_at`. If a transaction arrives late after a report has already been published, the system needs a policy to either **restate prior periods** or freeze the period and post an adjustment.

## 11. Quality Controls and Idempotency in the Pipeline

Re-running an ETL/CDC job is normal. Each rerun must never inflate sales figures by duplicating rows.

### Required Checks

| Layer | Check | Consequence if Skipped |
| --- | --- | --- |
| Raw ingestion | Source ID, sequence/LSN/offset present, no lost logs, valid schema | Missing data or inability to replay |
| Staging | Deduplicate by key and version; handle tombstones/deletes | Rows double-counted or deletes/updates missed |
| Transform | Clear grain, price snapshots, SCD dimension mapping, timezone | Wrong category grouping or wrong business date |
| Fact load | UNIQUE/merge by grain key; retries do not create new rows | Sales SUM grows when pipeline retries |
| Serving | Watermark, snapshot/version, data lineage | Viewers assume data is complete when it is not |
| Reconciliation | Period/tenant totals and counts compared against settled source | Discrepancies persist undetected |

**Idempotency** in OLAP can be protected using natural keys and version-aware UPSERT/MERGE operations, though you should not assume every fact is insert-only. Cancelled orders, refunds, historical updates, or post-close corrections can produce valid changes; you must choose between updating the fact, recording **adjustment rows**, or rebuilding a partition/period according to metric policy.

### Late-Arriving Events and Late-Arriving Dimensions

For example, an `OrderPaid` event reaches the warehouse before the `ProductVersion` metadata valid at the time of sale:

- **Option 1:** hold the fact temporarily in staging while waiting for the matching dimension version; enforce a timeout and alerting.
- **Option 2:** link to an "unknown/late arriving" dimension member, then backfill the key once source data arrives; ensure official reports do not interpret "unknown" as a real category.
- **Option 3:** create a placeholder dimension row with clear source/default attributes and update it later, if the warehouse architecture permits.

When an event is late relative to its business date, modify only records for **the relevant period** per policy rather than substituting ingestion date for event date. A watermark or "data complete through" indicator must show how far data has actually been processed; you cannot simply report the timestamp of the latest batch while ignoring lagging upstream sources.

### Reconciliation Testing

Suppose after closing day D, OLTP holds 10,000 PAID order lines; the warehouse must contain **10,000 unique sales-line keys** for that day under the same scope and rule version. Next, reconcile `SUM(gross_amount_vnd)`, order count, item quantity, status distribution, and daily refund count. If discrepancies appear, classify them as lag, missing events, mapping errors, adjustment policies, or metric logic — never tweak the dashboard just to make numbers appear to match.

## 12. Performance: Optimizing for the Right Query Pattern

### OLTP: Optimizing the Write Path and Point Queries

- Use PK/UNIQUE/FK/CHECK to protect entity identity, integrity, and local rules.
- Design indexes around hot query paths, such as looking up Order by `orderId` or Customer by tenant.
- Keep transactions short; avoid scanning/grouping millions of rows, sending emails, or making external HTTP calls while holding locks.
- Use optimistic locking or conditional UPDATEs for contended data; verify the affected row count.
- Monitor p95/p99 latency, deadlocks, lock waits, transaction rollbacks, and write throughput.

### OLAP: Optimizing Scans, Filters, and Aggregations

- Keep **grain** fixed, measures well-defined, and dimensions aligned with analytical questions.
- Co-locate frequently co-filtered data using partitioning/clustering/sort keys tailored to the specific engine; avoid overly granular partitions that inflate metadata and operational overhead.
- Favor reading only required columns when columnar storage engines support pruning and compression.
- Consider daily/category summary tables if dashboards query them constantly; design a clear refresh strategy when late data or adjustments arrive.
- Inspect query plans, scan volume, memory spill, query latency, operating cost, and workload distribution.

**Separating workload types does not mean every OLAP query is a full table scan** or every OLTP query reads exactly one row. An OLTP system may fetch a list of hundreds of orders, and an OLAP system may look up a materialized aggregate very quickly. The deciding factor remains **the primary purpose and how data is predominantly organized and queried**.

## 13. Do You Always Need Two Databases?

No. A new project with a few thousand orders per day and a single daily report can start with:

1. OLTP tables properly designed for transactions and invariants.
2. A few controlled aggregate queries, scheduled off-peak if necessary.
3. Materialized views or summary tables with refresh schedules and discrepancy checks.
4. Separating workloads when data volume, user concurrency, or freshness demands begin impacting the system.

Comparing the options:

| Option | When It May Fit | Costs and Limitations |
| --- | --- | --- |
| **Same OLTP DB** | Small dataset, few reports, moderate latency expectations | CPU/I/O contention with transactions, harder to retain proper dimension history |
| **Read replica** | Heavy direct read queries on the same schema | Replication lag, schema remains OLTP-oriented, not a data warehouse |
| **Materialized view / summary table** | Stable KPIs, bounded dimensionality | Refresh overhead and late-data adjustments, extra storage cost |
| **Dedicated warehouse/lakehouse** | Multiple sources, large data, long history, many analytical dimensions | Pipeline, governance, data quality, cost, and latency |
| **HTAP (hybrid transactional/analytical processing)** | Need transactions and analytics close together with suitable engine support | Does not automatically eliminate isolation, resource, or metric modeling trade-offs |

**Do not choose a technology just because a diagram says OLTP or OLAP.** Use correctness, freshness, response time, cost, and operational requirements as your inputs. Some systems need a large warehouse; others only need well-designed summary tables.

## 14. Avoiding Confusion About Ownership and Sources of Truth

An analytical fact is an **interpretation of data that has already happened**, not implicitly an authoritative source for executing an operational command. OLTP aggregates remain responsible for invariants:

- Inventory ensures no overselling beyond available stock at the reservation point.
- Payment governs payment states and idempotency of charge requests.
- Order governs order states and committed price snapshots.
- The warehouse clarifies which data has been ingested, what time window it covers, and which metrics are computed.

When the business wants to use analytics to decide whether to grant a customer promotion, the warehouse can compute **segment scores** and publish versioned outputs. Yet at the moment of issuing a voucher or deducting a quota, the transactional system still needs appropriate checks on eligibility, limits, and current state. An analytics-driven "CustomerQualified" event does not by itself authorize unlimited issuance.

### Access Control and Personal Data

Analytical systems often consolidate multiple sources, increasing data exposure risks:

- Do not copy emails, phone numbers, or full addresses if only `customerId` and segment are needed.
- Enforce access controls by tenant, branch, department, or sensitivity tier.
- Apply pseudonymization/anonymization when analytical goals permit; comply with deletion policies and retention windows.
- Document data lineage, transformation logic, metric versions, and who is authorized to publish reports.
- Verify whether deletions or corrections in source systems propagate properly to analytical copies and affected aggregates.

A fact table that queries fast but fails to protect access boundaries or explain data lineage does not yet meet analytical modeling standards.

## 15. Process for Turning Requirements into OLTP/OLAP Decisions

When receiving a new data requirement, follow this sequence:

1. **Write down the exact question:** is this a decision on one object right now or a comparison across a historical dataset?
2. **Identify the action:** state-changing command, point lookup, operational alert, analytical dashboard, or accounting close?
3. **State the commitments:** post-commit invariants, allowed freshness lag, historical depth, response latency, and query concurrency.
4. **If business state changes:** define the authoritative aggregate/root, locks, constraints, isolation level, and idempotency.
5. **If analytical:** define the **grain**, facts, dimensions, snapshots/SCDs, measure definitions, business date, and status filtering rules.
6. **Identify sources:** transactional tables, domain events, payments, refunds; what happens when upstream data changes or is missing?
7. **Select the delivery mechanism:** direct query, replica, summary table, batch ETL, CDC, warehouse, or HTAP based on actual requirements.
8. **Design verification:** transaction/race-condition tests for OLTP; double-counting, reconciliation, late-data, and KPI tests for OLAP.
9. **Publish the contract:** clarify "data complete through", calculation rules, metric owner, source, and version.

### Table for Translating Requirements into Design

| Prompt | Primary Classification | Suggested Model/Mechanism |
| --- | --- | --- |
| "Order 3 more items if stock remains" | OLTP | Reservation command, conditional UPDATE, transaction |
| "Current payment status of order X" | OLTP/operational read | Order/Payment source of truth, keyed lookup |
| "Sales value by product group each week" | OLAP | Sales-line grain fact, versioned product dim, calendar |
| "Customer repeat purchase rate by quarter" | OLAP | Customer/order fact, cohort and window definitions |
| "Fraud alert before accepting a transaction" | Operational decision using analytical data | Score/rule with defined source and freshness; command still enforces consistency |
| "Daily refund cashflow in executive report" | OLAP | Refund fact, completion date, currency rules, and reconciliation |

## 16. Practice Exercise: Online Learning Platform

**Context:** An online course platform has Course, Student, Enrollment, Payment, and Refund. Each class is capped at 50 seats. A student registers, holds a seat for 10 minutes, pays, and becomes confirmed. The training department wants to see enrollment counts, hold-to-confirmed conversion rates, and sales by instructor over 6 months. A course may be reassigned to a different instructor after going on sale.

### Tasks

1. Classify which questions are OLTP vs. OLAP: reserving the last seat; checking enrollment status; weekly conversion rate; sales by instructor; refunding a student.
2. Write **two invariants** that must be protected inside a transaction when holding/confirming a seat. Indicate who owns them and how to handle two requests competing for the last seat.
3. Design the grain for the enrollment fact, payment fact, and refund fact. Can **one single fact table** serve all three without mixing up measures?
4. When the Course instructor changes, how does reporting "by instructor at time of sale" differ from "by current instructor"? Propose a snapshot or SCD2 dimension solution.
5. A student pays across two payment attempts: the first fails and the second succeeds. If you JOIN Enrollment with both attempts and SUM the course price, what happens to the result?
6. Suppose ETL runs hourly. Could a report at 10:05 miss a payment from 10:01? How should the watermark/freshness be communicated?
7. Propose one reconciliation check for payment counts/amounts and one idempotency test for pipeline reruns.

### Suggested Approach

- **OLTP:** holding a seat, changing enrollment status, checking Payment/Refund, and looking up an active Enrollment. **OLAP:** weekly conversion rate, sales by instructor, holds by segment.
- The 50-seat limit must be enforced by an authoritative seat inventory source; the same student cannot have two active Enrollments if policy forbids it. Use conditional UPDATEs/locking or an atomic reservation protocol — never read seat availability from a lagging dashboard.
- You can define `fact_enrollment_event` at the grain of **one status transition event**, `fact_successful_payment` at **one successful payment**, and `fact_completed_refund` at **one completed refund**. If using a consolidated fact table, each row must carry an explicit `eventType` and unambiguous measures so failed PaymentAttempts are never summed as sales.
- Reporting "instructor at time of sale" requires a snapshot or time-effective dimension; "current instructor" can JOIN to the current roster, but the two results must never be treated as the same KPI.
- JOINing with multiple attempts multiplies the amount unless filtered or aggregated to the proper grain. Only successful payments per the recognition contract enter the paid-value measure.
- With hourly ETL, tables at 10:05 may only contain data processed up to the prior cutoff. Display "data complete through" and monitor for late-arriving events.
- Retrying the same batch must not increase record counts per business key. Reconcile `COUNT(DISTINCT paymentId)` and `SUM(amount)` between the settled payment source and the warehouse for the same tenant, time window/currency, and status policy.

**Extension challenge:** Build two dashboards: one showing "number of people holding seats right now" and another showing "hold → confirmed conversion rate over 30 days". Why might the first dashboard need to query an operational source or very fresh projection, while the second requires historical event data and strict cohort definitions?

## 17. Data Modeling Checklist

- Is the requirement a **command that must protect invariants** or an **aggregate query/metric**? Does it contain both?
- Does the transactional system have keys, transactions, write authorization, idempotency, and concurrency control aligned with its invariants?
- Does the analytical KPI define **grain, measures, dimensions, event timestamp, and valid statuses**?
- How do prices, currencies, categories, customers, and time-varying attributes need snapshots or SCDs?
- Is there any risk of JOIN row multiplication, using `COUNT(*)` at the wrong grain, or mis-aggregating ratios/snapshots?
- When multiple sources participate, are there clear rules for **syncing, retries, late data, deduplication, and reconciliation**?
- Are freshness, watermarks, query SLAs, and impact on the transactional system specified quantitatively?
- Were indexes, partitions, materialized views, columns, and history chosen for actual workloads?
- Does the report protect access controls, tenant scope, personal data, and explain data lineage?
- Was the choice of single DB, replica, warehouse, or HTAP driven by requirements rather than technology trends?

**Conclusion:** **OLTP** optimizes for executing and protecting authoritative business state changes; **OLAP** optimizes for interpreting, aggregating, and comparing data against questions with clear measurement definitions. Both processing styles can coexist within one technology or be separated into distinct systems. The basis of the decision is not the product name, but **invariants and transactions on the write path**, **grain and metrics on the analytical path**, alongside the freshness, quality, traceability, and operational cost the business truly requires.
