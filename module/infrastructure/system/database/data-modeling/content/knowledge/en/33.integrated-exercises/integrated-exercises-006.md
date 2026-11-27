# Choosing Physical Models and Indexes from Real Queries

An ERD can be completely accurate in entities and relationships yet still produce a slow, bloated, hard-to-operate system if physical modeling decisions are made by guesswork. An index with “the right column name” may fail to help queries using `LIMIT` and `ORDER BY`; a well-normalized table may be ill-suited for summing revenue across hundreds of millions of rows on every dashboard load. Conversely, indexing every column makes writes, `VACUUM`, backups, and migrations expensive.

This integrated exercise belongs to the **DATABASE_DATA_MODELING** module and the **Integrated Exercises** chapter. Your task is to **read real queries and usage workloads, identify grains and constraints, and then choose the right tables, keys, indexes, partitions, and read models**. We will work through a multi-tenant retail platform combining order lookups, paginated lists, processing queues, product searches, revenue reports, sensor event streams, JSONB metadata, and inventory updates.

Learning objectives:

1. Turn a list of queries into a **workload matrix** with frequency, selectivity, row counts, SLAs, and priorities.
2. Propose a physical model **without breaking business invariants**: grain, PK/FK/UNIQUE, tenant isolation, and lifecycles.
3. Choose and justify **single/composite B-tree, partial, covering `INCLUDE`, expression, GIN, and BRIN** indexes aligned with predicates, joins, sorts, and ranges.
4. Know when to **reuse existing indexes**, and when to use keyset pagination, partitioning, or derived aggregate tables.
5. Design experiments using **`EXPLAIN (ANALYZE, BUFFERS)`**, representative data, and write metrics to validate proposals.
6. Articulate trade-offs across **write overhead, contention, storage, security, migrations, and evolvability**.
7. Complete a full design exercise with worked answers, not merely copy a list of `CREATE INDEX` statements.

> **Principle:** Start from “which query, in what scope, over how many rows, returning what columns, within what latency budget?”, never from “which columns does this table have so I can index them?”.

## 1. Prompt: a growing multi-tenant retail platform

A sales platform serves many stores (tenants). Core operational data:

- **Customer:** one customer within a tenant.
- **Product:** one product within a tenant, with SKU, category, and active status.
- **SalesOrder:** an order with status, buyer, creation timestamp, and payment timestamp.
- **OrderLine:** one item line in an order, with quantity and unit price locked at sale time.
- **StockBalance:** on-hand and reserved quantities per tenant, warehouse, and SKU/product.
- **DeviceEvent:** sensor readings from warehouse devices, with timestamp and metric type.
- **Order metadata:** flexible source attributes, where fields rarely filtered on may live in JSONB.

### 1.1. Scale assumptions — not production measurements

| Metric | Exercise assumption | Design implication |
| --- | ---: | --- |
| Total tenants | 2,000 | Most queries require `tenant_id` |
| Customer | 2 million rows | Lookups by ID/email |
| Product | 500,000 rows | SKU, category, availability |
| SalesOrder | 20 million rows | Lookups, recent lists, status |
| OrderLine | 60 million rows | 3 lines/Order on average |
| New Orders | 100,000/day | Indexes increase `INSERT` cost |
| DeviceEvent | 800,000/day | Append-heavy data, range queries |
| Largest tenant | 30% of Orders | Skew, hot tenant, and hotspots |
| Order retention | Per approved policy | Impacts partitioning/archival |
| Refunds/partial captures | Out of v1 scope | Revenue KPIs must state limits |

These numbers are **hypothetical assumptions to practice design reasoning**, not benchmarks or SLO commitments. In real projects, replace them with measured workload data, actual sizes, growth rates, and per-tenant distributions.

### 1.2. Invariants that must never be traded for speed

- An Order and every referenced Line/Customer/Product must **belong to the same tenant**.
- Each Order has a technical key `(tenant_id, order_id)` and a tenant-unique display code.
- Each Line is identified by `(tenant_id, order_id, line_no)`; two Lines with the same Product can be valid.
- Line unit price is **locked in integer VND**; never update historical lines with current Product prices.
- Identical `(tenant_id, source_system, source_order_ref)` when present must not create duplicate imported orders from the same source.
- When reserving stock, `reserved` cannot exceed `on_hand` at the owning `StockBalance`; indexes never replace transactions.
- Tenant A's data must never leak to Tenant B via queries, caches, exports, or read models.

Index design must preserve these invariants. Never downgrade a composite FK to a single-column FK just because a one-column JOIN looks shorter; never drop a `UNIQUE` constraint over write overhead if it enforces a mandatory business rule.

## 2. Workload matrix — mandatory input before designing

The product team provides the core queries. The p95 targets below are likewise hypothetical values for designing tests.

| Code | Query or command | Relative frequency | Result size | Illustrative target |
| --- | --- | --- | --- | --- |
| Q1 | Open one Order and its Lines by ID | Very high | 1 Order, a few Lines | p95 < 80 ms |
| Q2 | 50 most recent Orders of a Customer | Very high | 50 rows/page | p95 < 150 ms |
| Q3 | 100 oldest PENDING Orders for processing | High | 100 rows | p95 < 150 ms |
| Q4 | PAID Orders within a date range | Medium | 100-row pages | p95 < 300 ms |
| Q5 | Lookup Order by partner source reference | High | 0..1 rows | p95 < 100 ms |
| Q6 | Active Products in a Category | High | 30 rows/page | p95 < 150 ms |
| Q7 | Top best-selling Products in a period | Medium | 10–100 groups | Dashboard < 2 s or mart |
| Q8 | Read latest 500 points of a Device | High | 500 rows | p95 < 200 ms |
| Q9 | Filter Orders by flexible metadata | Low | Rows/page | p95 < 700 ms |
| Q10 | High-concurrency ReserveStock | High, with hot SKUs | 1 balance | Zero oversell; p95 per SLA |
| Q11 | Staff order lookup by `order_code` | High | 0..1 Order | p95 < 100 ms |
| Q12 | End-of-day stock report over 12 months | Low | 12–365 days | Grain-safe Warehouse/OLAP |

**High frequency alone does not set priority:** Q10 is a write path protecting inventory and may outrank read queries called more often. Reporting queries running a few times a day that scan entire tables and choke OLTP may also require offloading to a separate read model.

### 2.1. Information-gathering checklist per query

Do not write down SQL alone. For each Qx, capture:

1. **Filter:** equality, `IN`, range, `LIKE`, JSON containment, or full-text search?
2. **Join:** join keys, 1–N fanout risk?
3. **Sort/limit:** exact `ORDER BY`, `LIMIT`, how deep can `OFFSET` go?
4. **Projection:** which columns are needed? Is `SELECT *` used or can it be narrowed?
5. **Cardinality:** how many rows match for the largest tenant, not just the average?
6. **Skew:** can one Customer have 1 million Orders? Is one SKU a hot key?
7. **Freshness:** must reads see writes immediately, or is replica lag acceptable?
8. **Security:** where is the tenant filter applied and enforced?
9. **SLO and budget:** p95/p99, rows read, buffers, write overhead, disk?
10. **Measurement source:** app logs, query stats, `EXPLAIN` plans, tracing?

Without these answers, picking indexes is guesswork. **An index is a testable hypothesis**, not an acceptance criterion.

## 3. Proposed relational schema for OLTP

We use PostgreSQL with tenant-scoped composite keys. For clarity, IDs in the example are application-assigned; generating tenant-unique IDs is a separate system responsibility.

### 3.1. Customer and Product

~~~sql
CREATE TABLE customers (
    tenant_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    email_normalized TEXT NOT NULL,
    customer_name TEXT NOT NULL,
    archived_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, customer_id),
    UNIQUE (tenant_id, email_normalized)
);

CREATE TABLE products (
    tenant_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    category_id BIGINT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (tenant_id, product_id),
    UNIQUE (tenant_id, sku)
);
~~~

**Each table already gets B-trees from PK and UNIQUE.** Put those into your index inventory before proposing new ones. For example, looking up Product by `(tenant_id, sku)` already uses the existing unique index; creating a second identical index is redundant.

In practice, `email_normalized` works as a unique key only if email normalization and account policies are settled. Never treat `lower(email)` as a universal solution for all email address rules.

### 3.2. SalesOrder, OrderLine, and StockBalance

~~~sql
CREATE TABLE sales_orders (
    tenant_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    order_code TEXT NOT NULL,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('DRAFT','PENDING','PAID','CANCELLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    paid_at TIMESTAMPTZ,
    total_amount_vnd BIGINT NOT NULL CHECK (total_amount_vnd >= 0),
    source_system TEXT NOT NULL DEFAULT 'INTERNAL',
    source_order_ref TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    PRIMARY KEY (tenant_id, order_id),
    UNIQUE (tenant_id, order_code),
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES customers(tenant_id, customer_id)
        ON DELETE RESTRICT,
    CHECK (status <> 'PAID' OR paid_at IS NOT NULL)
);

CREATE TABLE order_lines (
    tenant_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_vnd BIGINT NOT NULL CHECK (unit_price_vnd >= 0),
    PRIMARY KEY (tenant_id, order_id, line_no),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES sales_orders(tenant_id, order_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, product_id)
        REFERENCES products(tenant_id, product_id)
        ON DELETE RESTRICT
);

CREATE TABLE stock_balances (
    tenant_id BIGINT NOT NULL,
    warehouse_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    on_hand INTEGER NOT NULL CHECK (on_hand >= 0),
    reserved INTEGER NOT NULL DEFAULT 0 CHECK (reserved >= 0),
    PRIMARY KEY (tenant_id, warehouse_id, product_id),
    FOREIGN KEY (tenant_id, product_id)
        REFERENCES products(tenant_id, product_id),
    CHECK (reserved <= on_hand)
);
~~~

**Scope notes:**

- An Order has 0..N Lines while DRAFT; business rules may require 1..N upon confirmation. The FK from Line → Order **does not automatically force an Order to have Lines**.
- `total_amount_vnd` is a stored total; if the business requires it to always match `SUM(Line)`, enforce a single controlled write path and reconciliation checks. `CHECK` cannot verify sums across rows.
- A PAID Order has `paid_at`, yet status alone does not form a complete ledger for refunds, chargebacks, or split payments.
- `StockBalance` tracks **one warehouse × one product × one tenant**, not company-wide stock.

### 3.3. Time-series records for query Q8

~~~sql
CREATE TABLE device_events (
    tenant_id BIGINT NOT NULL,
    device_id BIGINT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    event_id UUID NOT NULL,
    metric_code TEXT NOT NULL,
    value_num NUMERIC(18, 5) NOT NULL,
    PRIMARY KEY (tenant_id, device_id, observed_at, event_id)
);
~~~

This key protects **one event per tenant/device/timestamp/ID**, without guaranteeing `event_id` uniqueness across timestamps. If a source corrects `observed_at` and replays the same `event_id`, add **source-event deduplication rules** when exactly-once effects are required. `NUMERIC` illustrates fixed-precision measurements; if floating-point tolerances are acceptable, weigh the storage/accuracy trade-offs of `DOUBLE PRECISION` against measurement needs.

### 3.4. Relationship diagram

~~~mermaid
erDiagram
    CUSTOMERS ||--o{ SALES_ORDERS : places
    SALES_ORDERS ||--o{ ORDER_LINES : contains
    PRODUCTS ||--o{ ORDER_LINES : sold_as
    PRODUCTS ||--o{ STOCK_BALANCES : stocked_in
~~~

Lines represent relationships; choosing **access indexes** still depends on predicates, sorts, and workload. Not every FK edge needs a new index duplicating a PK; check the actual lookup directions.

## 4. Q1 — Opening an Order and all its Lines by ID

Detail read API:

~~~sql
SELECT tenant_id, order_id, order_code, customer_id,
       status, total_amount_vnd, created_at
FROM sales_orders
WHERE tenant_id = 11 AND order_id = 600001;

SELECT line_no, product_id, quantity, unit_price_vnd
FROM order_lines
WHERE tenant_id = 11 AND order_id = 600001
ORDER BY line_no;
~~~

### 4.1. Index choice

- `SalesOrder` already has **`PRIMARY KEY (tenant_id, order_id)`**.
- `OrderLine` already has **`PRIMARY KEY (tenant_id, order_id, line_no)`**.

With `tenant_id` and `order_id` fixed, the `OrderLine` index follows the exact key prefix and reads rows already ordered by `line_no`. **Do not run `CREATE INDEX (order_id)`** for this query; an index on `order_id` alone also drops the tenant prefix.

### 4.2. Things to verify

- Queries actually include `tenant_id` enforced by the authorization layer.
- Real distribution of Lines per Order; if an Order can hold hundreds of thousands of Lines, does the endpoint need pagination?
- If joining `Product` to fetch current names, are you accidentally replacing the **sale-time snapshot name**?
- If `OrderLine` lives on a different shard from `SalesOrder`, DDL FKs above do not operate like single-database PostgreSQL FKs.

**Q1 decision:** use the two existing PKs; add zero indexes. Knowing **why not to create an index** is just as important in physical design.

## 5. Q2 — 50 most recent Orders of a Customer: composite index and keyset

Access path filters tenant and customer, then sorts by timestamp and ID:

~~~sql
SELECT order_id, status, total_amount_vnd, created_at
FROM sales_orders
WHERE tenant_id = 11
  AND customer_id = 9001
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

The primary key `(tenant_id, order_id)` cannot efficiently fetch **the 50 newest Orders of a Customer** because `customer_id` is absent before the sort. Create an index:

~~~sql
CREATE INDEX idx_orders_customer_recent
ON sales_orders (
    tenant_id,
    customer_id,
    created_at DESC,
    order_id DESC
)
INCLUDE (status, total_amount_vnd);
~~~

### 5.1. Explaining column order

1. `tenant_id` and `customer_id` are **equality predicates**.
2. `created_at` and `order_id` match **`ORDER BY DESC`** and pagination.
3. `order_id` acts as a deterministic tie-breaker when multiple Orders share `created_at`.
4. `status` and `total_amount_vnd` are projection-only columns placed in **`INCLUDE`** rather than key sort columns.

While a B-tree supports leftmost-prefix lookups, never assume an index on `(tenant_id, customer_id, created_at)` optimizes every `WHERE` filtering `created_at` **without `customer_id`**. Column order must match critical query shapes.

### 5.2. Deep OFFSET and keyset pagination

Page 1 can use `LIMIT 50`. For deep pages:

~~~sql
SELECT order_id, status, total_amount_vnd, created_at
FROM sales_orders
WHERE tenant_id = 11
  AND customer_id = 9001
ORDER BY created_at DESC, order_id DESC
LIMIT 50 OFFSET 100000;
~~~

Even with a matching index, `OFFSET 100000` still walks past a large number of rows before returning 50. For long feeds or histories, use **keyset pagination** anchored on the last row of the previous page:

~~~sql
SELECT order_id, status, total_amount_vnd, created_at
FROM sales_orders
WHERE tenant_id = 11
  AND customer_id = 9001
  AND (created_at, order_id) <
      ('2026-11-20 00:00:00+00'::TIMESTAMPTZ, 600000)
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

The tuple `<` comparison works because both `created_at` and `order_id` sort descending. With mixed sort directions or `NULL`s, write the matching cursor predicate rather than copying this formula blindly.

Keyset pagination avoids scanning/skipping thousands of rows, yet **does not guarantee snapshot consistency across pages** when new rows arrive or mutate. If the UI needs an unchanging list across a session, define cutoffs, isolation, or snapshot policies.

### 5.3. INCLUDE does not guarantee an Index Only Scan

PostgreSQL uses an Index Only Scan when all needed columns reside in the index **and** heap pages are marked all-visible in the visibility map. Frequently updated tables may still perform heap fetches. `INCLUDE` also enlarges the index, increasing write and maintenance costs. **Never add `INCLUDE` purely because “covering” sounds fast**; measure index size, heap fetches, latency, and update workload.

**Q2 decision:** test composite index `(tenant_id, customer_id, created_at DESC, order_id DESC)`; keep `INCLUDE` only if measured benefits outweigh costs.

## 6. Q3 — Oldest PENDING Orders: partial index and queue queries

Staff process batches of PENDING Orders FIFO:

~~~sql
SELECT order_id, created_at
FROM sales_orders
WHERE tenant_id = 11
  AND status = 'PENDING'
ORDER BY created_at ASC, order_id ASC
LIMIT 100;
~~~

If only a small fraction of Orders are PENDING, indexing every status wastes space and update cost. Proposed:

~~~sql
CREATE INDEX idx_orders_pending_fifo
ON sales_orders (tenant_id, created_at ASC, order_id ASC)
WHERE status = 'PENDING';
~~~

### 6.1. Why is a partial index beneficial?

- Contains only Orders matching **`status = 'PENDING'`**.
- Ordered by tenant and creation time to match FIFO.
- When an Order transitions from PENDING to PAID/CANCELLED, its entry drops out of the partial index.
- The query **must allow the optimizer to prove it satisfies the predicate**; prepared statements using a parameterized status with a generic plan may skip the partial index when the runtime value is unknown at plan time.

If PENDING represents a large share of the table, or queries filter other statuses too, compare a general index:

~~~sql
CREATE INDEX idx_orders_status_fifo_candidate
ON sales_orders (tenant_id, status, created_at ASC, order_id ASC);
~~~

This is an **alternative candidate**—do not create both without measuring. Pick one based on status distribution, write cost, and real queries.

### 6.2. Reading a queue does not claim work

If multiple workers poll the queue, `SELECT` followed by a separate `UPDATE` lets **two workers grab the same Order**. For queues where skipping locked rows is acceptable, **`FOR UPDATE SKIP LOCKED`** helps handle contention. The snippet below only illustrates row locking, **without performing a claim**:

~~~sql
BEGIN;

SELECT tenant_id, order_id
FROM sales_orders
WHERE tenant_id = 11
  AND status = 'PENDING'
ORDER BY created_at ASC, order_id ASC
LIMIT 20
FOR UPDATE SKIP LOCKED;

-- End of test: release locks without mutating state.
ROLLBACK;
~~~

This snippet **intentionally runs `ROLLBACK`** to demonstrate locking without faking a business transition. In production, add a **`PROCESSING`** state with lease/owner expiration—or a dedicated jobs table—and perform selection and claiming inside the **same transaction**. `SKIP LOCKED` yields a deliberately incomplete view suited for contended queues, **never** for general reporting queries.

**Q3 decision:** a partial index fits when PENDING is rare and the predicate is constant; work-claiming must be designed at the transaction/state-machine layer, not inferred from an index.

## 7. Q4 — PAID Orders in a date range: range and sort

Operations views Orders paid during a week:

~~~sql
SELECT order_id, customer_id, paid_at, total_amount_vnd
FROM sales_orders
WHERE tenant_id = 11
  AND status = 'PAID'
  AND paid_at >= '2026-11-01 00:00:00+00'::TIMESTAMPTZ
  AND paid_at <  '2026-11-08 00:00:00+00'::TIMESTAMPTZ
ORDER BY paid_at DESC, order_id DESC
LIMIT 100;
~~~

Candidate when PAID is a fixed predicate and other queries do not need all statuses:

~~~sql
CREATE INDEX idx_orders_paid_recent
ON sales_orders (tenant_id, paid_at DESC, order_id DESC)
WHERE status = 'PAID';
~~~

**Why a half-open range?** Including start-of-day and excluding end-of-day prevents timestamp-precision boundary bugs and stitches adjacent periods cleanly. UTC bounds here should be mapped from **business dates** in the approved timezone; never assume every store operates on UTC days.

### 7.1. Difference between Q2 and Q4

- Q2 has equality on **`customer_id`** and sorts by **`created_at`**.
- Q4 does not filter customer; it filters tenant, paid status, and range **`paid_at`**.
- Q2's composite index cannot substitute for Q4 even though both query `SalesOrder`.

If Q4 runs rarely and reads from a replica/analytics store, OLTP may need no dedicated index. If Q4 powers a tight-SLA operational API, a dedicated index may justify its cost.

### 7.2. Range predicates affect trailing columns

In a composite B-tree, leading equality predicates narrow the scan, followed by the `paid_at` range. Columns appearing **after the range column** do not narrow scanned rows the way leading equalities do; `order_id` here mainly aids ordering/tie-breaking. Reordering to `(tenant_id, order_id, paid_at)` hurts when `order_id` is absent from `WHERE`.

**Q4 decision:** test a partial B-tree on `(tenant_id, paid_at DESC, order_id DESC)` vs a general index and measure state-transition write overhead.

## 8. Q5 and Q11 — Identifier lookups: UNIQUE constraints are already indexes

Partner calls back using source reference:

~~~sql
SELECT order_id, status
FROM sales_orders
WHERE tenant_id = 11
  AND source_system = 'PARTNER_A'
  AND source_order_ref = 'EXT-90001';
~~~

Create scoped uniqueness:

~~~sql
CREATE UNIQUE INDEX ux_orders_external_source
ON sales_orders (
    tenant_id, source_system, source_order_ref
)
WHERE source_order_ref IS NOT NULL;
~~~

**Meaning:** a non-null reference is unique **within the same `tenant_id` and `source_system`**. `NULL` may repeat for internal orders. Retry protection must also compare the **payload for the same reference**; identical ID with a different payload is a conflict to surface, never silently returning success for the wrong order.

Q11 lookup by order code:

~~~sql
SELECT order_id, customer_id, status
FROM sales_orders
WHERE tenant_id = 11 AND order_code = 'O-1001';
~~~

`UNIQUE(tenant_id, order_code)` already exists in `CREATE TABLE`, so **do not add another index** on those two columns.

### 8.1. When does a partial unique index get in the way?

The partial unique index in Q5 cannot serve as a standard `FOREIGN KEY` target via a table-level `UNIQUE` constraint. If another table needs to reference an Order by source reference, consider referencing **`PK(tenant_id, order_id)`** or designing an authoritative registry/mapping table. Never alter reference keys just to “reuse an existing index” when it breaks semantics.

### 8.2. Expression indexes only when queries actually use the expression

If code lookups must be case-insensitive, one approach normalizes values on the write path and enforces `UNIQUE` on the normalized column. If queries must run `LOWER(order_code)`, an expression index matching that expression can work, subject to collation, policy, and whether two codes differing only by case may coexist.

**Do not** pre-create indexes for `LOWER`, `UPPER`, `substring`, and every variant before concrete queries and normalization contracts exist.

**Q5/Q11 decision:** indexes enforcing uniqueness simultaneously serve lookups; eliminate redundant indexes without weakening idempotency or tenant scope.

## 9. Q6 — Active Products in a Category: partial index and prefixing

The app displays 30 active products for a Category:

~~~sql
SELECT product_id, sku, product_name
FROM products
WHERE tenant_id = 11
  AND category_id = 501
  AND is_active = TRUE
ORDER BY product_id ASC
LIMIT 30;
~~~

Candidate when active products form a moderate subset and this query runs frequently:

~~~sql
CREATE INDEX idx_products_active_category
ON products (tenant_id, category_id, product_id)
WHERE is_active = TRUE;
~~~

The index groups valid Products by tenant/category in `product_id` order. For large categories, the API can use keyset pagination on `product_id`:

~~~sql
SELECT product_id, sku, product_name
FROM products
WHERE tenant_id = 11
  AND category_id = 501
  AND is_active = TRUE
  AND product_id > 70000
ORDER BY product_id ASC
LIMIT 30;
~~~

An alternative index when **both active and inactive items are queried frequently** is:

~~~sql
-- Comparison candidate; do not create alongside partial index without reason.
CREATE INDEX idx_products_category_status_candidate
ON products (tenant_id, category_id, is_active, product_id);
~~~

### 9.1. Should a boolean column be indexed on its own?

An index on **`is_active`** alone has poor selectivity when most Products are active. Still, a partial index **restricted to active** and prefixed with tenant/category can be effective for that specific query. Evaluate against row counts per Category and tenant—**never jump to conclusions from `BOOLEAN` type alone**.

### 9.2. Looking up a Product by SKU

~~~sql
SELECT product_id, product_name
FROM products
WHERE tenant_id = 11 AND sku = 'SKU-2026-A';
~~~

`UNIQUE(tenant_id, sku)` already exists; no second index needed.

### 9.3. Substring search on Product name

~~~sql
SELECT product_id, product_name
FROM products
WHERE tenant_id = 11
  AND product_name ILIKE '%headphones%';
~~~

Standard B-trees cannot efficiently handle **leading wildcards**. PostgreSQL can use the **`pg_trgm`** extension and GIN/GiST trigram indexes where appropriate, weighing extension permissions, search language, update rate, query term length, and feature priority.

~~~sql
-- Candidate test only where extensions are permitted:
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX idx_products_name_trgm_candidate
ON products USING GIN (product_name gin_trgm_ops);
~~~

This index can be large and does not include `tenant_id` directly in the key. If search is a core multi-tenant feature needing ranking and language rules, evaluate a dedicated search index/service. Do not add a trigram index for a rare backlog query.

**Q6 decision:** partial B-tree for active category browsing if benchmarks support it; SKU lookup reuses existing `UNIQUE`; fuzzy search is a **separate requirement branch**, not crammed into a generic B-tree.

## 10. Q7 — Top best-selling Products: when indexes are not enough

Business query:

> Within tenant 11, find the top 10 Products with the highest **line-item value across PAID Orders** this week.

Assuming v1 has no refunds and the measure is **gross line amount**, not net revenue after discounts/taxes/refunds.

~~~sql
SELECT l.product_id,
       SUM(l.quantity::NUMERIC * l.unit_price_vnd)
           AS gross_line_amount_vnd,
       SUM(l.quantity) AS units_sold
FROM sales_orders AS o
JOIN order_lines AS l
  ON l.tenant_id = o.tenant_id
 AND l.order_id = o.order_id
WHERE o.tenant_id = 11
  AND o.status = 'PAID'
  AND o.paid_at >= '2026-11-01 00:00:00+00'::TIMESTAMPTZ
  AND o.paid_at <  '2026-11-08 00:00:00+00'::TIMESTAMPTZ
GROUP BY l.product_id
ORDER BY gross_line_amount_vnd DESC
LIMIT 10;
~~~

### 10.1. How much can existing indexes help?

- **`idx_orders_paid_recent`** helps locate PAID Orders in the `paid_at` window.
- PK **`order_lines(tenant_id, order_id, line_no)`** helps look up each Order's Lines.
- Yet to compute top Products, the query must **read all matching Lines, `GROUP BY` Product, and `SUM`**. A plain index on `product_id` cannot precompute weekly sums.
- With millions of Lines in the window, probing Order by Order can cause heavy random lookups; the optimizer may pick scans/hash joins depending on statistics.

### 10.2. Why not index the computed line amount?

Gross line amount of a single **Line** equals `quantity × unit_price`. Yet **top Products over a date range** sums across **many Lines** filtered by Order status and `paid_at`. An expression index on `quantity * unit_price` on `order_lines` **does not pre-aggregate totals by Product/period**.

This is a **read-model** problem, not just an indexing problem.

### 10.3. If the Dashboard needs sub-two-second latency at scale

Create a daily summary table at the grain:

> One row = one `tenant` × `business_sale_date` × `product_id`.

~~~sql
CREATE TABLE product_sales_daily (
    tenant_id BIGINT NOT NULL,
    business_sale_date DATE NOT NULL,
    product_id BIGINT NOT NULL,
    gross_line_amount_vnd NUMERIC(24, 0) NOT NULL DEFAULT 0,
    units_sold BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, business_sale_date, product_id)
);
~~~

Read query:

~~~sql
SELECT product_id,
       SUM(gross_line_amount_vnd) AS gross_line_amount_vnd,
       SUM(units_sold) AS units_sold
FROM product_sales_daily
WHERE tenant_id = 11
  AND business_sale_date >= DATE '2026-11-01'
  AND business_sale_date <  DATE '2026-11-08'
GROUP BY product_id
ORDER BY gross_line_amount_vnd DESC
LIMIT 10;
~~~

The PK `(tenant_id, business_sale_date, product_id)` slices the tenant's date window cleanly. The query still groups and sorts, yet reads **one row per day per Product** instead of every raw Line. For high-write real-time dashboards, consider materialized views or OLAP projections with an explicit **freshness SLA** and correction mechanism.

### 10.4. Correct numbers matter more than speed

Never double-count a Line on event replays. When Orders cancel or refund, define exact delta updates to the summary table with **event idempotency**. If a Product changes Category, as-sold vs as-current results differ; add proper versioning/snapshots if needed.

If **net revenue** is requested, explicitly define discounts, taxes, refunds, fees, shipping, and recognition dates—never label a gross sum `net_revenue`.

**Q7 decision:** real query inspection reveals the need for an aggregated read table or OLAP mart; never slap arbitrary B-trees onto `OrderLine` and promise top-N SLA compliance.

## 11. Q8 — Latest 500 Device samples: B-tree, BRIN, and partitioning

Time-series query:

~~~sql
SELECT observed_at, event_id, metric_code, value_num
FROM device_events
WHERE tenant_id = 11
  AND device_id = 8008
  AND observed_at >= '2026-11-20 00:00:00+00'::TIMESTAMPTZ
ORDER BY observed_at DESC, event_id DESC
LIMIT 500;
~~~

We already have PK **`(tenant_id, device_id, observed_at, event_id)`**. PostgreSQL uses a B-tree for the PK and can **scan backward** across `(observed_at, event_id)` when `tenant_id` and `device_id` are fixed by equality. Thus a second index on the same columns with `DESC` **is likely completely redundant**.

### 11.1. When `metric_code` is filtered frequently

~~~sql
SELECT observed_at, event_id, value_num
FROM device_events
WHERE tenant_id = 11
  AND device_id = 8008
  AND metric_code = 'temperature'
  AND observed_at >= '2026-11-20 00:00:00+00'::TIMESTAMPTZ
ORDER BY observed_at DESC, event_id DESC
LIMIT 500;
~~~

The existing PK reads by device/time and filters `metric_code` afterward. If a device emits many metric codes and queries target one metric, test:

~~~sql
CREATE INDEX idx_events_device_metric_recent
ON device_events (
    tenant_id, device_id, metric_code,
    observed_at DESC, event_id DESC
);
~~~

The new index pays off when it cuts scanned rows significantly; if each device only emits one metric or metric-filtered queries are rare, index overhead may exceed gains.

### 11.2. BRIN for time-range scans with physical correlation

A batch job reading **all events for one day across all devices** has a different access pattern:

~~~sql
SELECT tenant_id, device_id, observed_at, metric_code, value_num
FROM device_events
WHERE observed_at >= '2026-11-20 00:00:00+00'::TIMESTAMPTZ
  AND observed_at <  '2026-11-21 00:00:00+00'::TIMESTAMPTZ;
~~~

If events insert roughly in `observed_at` order and the table is huge, a **BRIN** index on `observed_at` stays tiny compared to B-tree and skips out-of-range page ranges:

~~~sql
CREATE INDEX idx_events_time_brin_candidate
ON device_events USING BRIN (observed_at)
WITH (pages_per_range = 64);
~~~

BRIN relies on **physical correlation between data and heap block location**; it does not provide per-device ordering like B-tree. Late events, backfills, or interleaved writes across devices/tenants widen block-range min/max bounds, forcing more blocks to be read; always measure real effectiveness.

### 11.3. When to partition by time?

If you need monthly deletion/archival, date-range scans, and steady data growth, evaluate **`RANGE` partitioning by `observed_at`**. Separate prototype:

~~~sql
CREATE TABLE device_events_partitioned (
    tenant_id BIGINT NOT NULL,
    device_id BIGINT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    event_id UUID NOT NULL,
    metric_code TEXT NOT NULL,
    value_num NUMERIC(18,5) NOT NULL,
    PRIMARY KEY (tenant_id, device_id, observed_at, event_id)
) PARTITION BY RANGE (observed_at);

CREATE TABLE device_events_2026_11
PARTITION OF device_events_partitioned
FOR VALUES FROM ('2026-11-01 00:00:00+00')
           TO   ('2026-12-01 00:00:00+00');

CREATE TABLE device_events_2026_12
PARTITION OF device_events_partitioned
FOR VALUES FROM ('2026-12-01 00:00:00+00')
           TO   ('2027-01-01 00:00:00+00');
~~~

The PK includes **`observed_at`**, satisfying PostgreSQL's partitioned-table PK/UNIQUE requirement. However, it does not enforce `event_id` uniqueness **across different timestamps**. If source-wide `event_id` uniqueness is required, maintain a separate dedup registry keyed by source ID or a system supporting global uniqueness. Never compromise correctness just for easier partition drops.

A single November partition **does not hold all events**: provision partitions covering the full range or define a default partition and out-of-range timestamp policy. Account for late events, skewed device clocks, and archived old partitions.

### 11.4. Do not shard by timestamp if decisions are local to a device

If writes/operations on a device stream enforce cross-time invariants for that device, sharding by day spreads one device across multiple owners. Physical monthly partitioning **inside one DB** can preserve device-level ownership; in truly distributed setups, evaluate shard keys and protocols separately.

**Q8 decision:** recent per-device series queries start with the existing PK; add a metric-specific index only if justified; BRIN/time partitioning address **different range/retention queries** and must be tested at scale.

## 12. Q9 — Filtering JSONB metadata: GIN or typed column?

Some partners send custom metadata. An API filters Orders with `sales_channel = affiliate`:

~~~sql
SELECT order_id, created_at, total_amount_vnd
FROM sales_orders
WHERE tenant_id = 11
  AND metadata @> '{"sales_channel":"affiliate"}'::JSONB
ORDER BY created_at DESC
LIMIT 50;
~~~

### 12.1. GIN for JSONB containment

If flexible containment filters are common, PostgreSQL can use GIN:

~~~sql
CREATE INDEX idx_orders_metadata_containment_candidate
ON sales_orders USING GIN (metadata jsonb_path_ops);
~~~

**`jsonb_path_ops`** is an operator class supporting JSONB containment (`@>`); do not assume it supports every JSON operator equally. If the app frequently tests **key existence** (`?`) or diverse operators, evaluate the appropriate operator class (e.g., `jsonb_ops`) and re-measure index size/plans.

A GIN index on `metadata` **never replaces tenant filters or authorization**. Queries must still filter `tenant_id`, and the optimizer may combine indexes or pick another plan if containment has low selectivity.

### 12.2. When only one attribute is queried frequently

If `sales_channel` is a stable, important business dimension for queries and reporting, consider **promoting it to a typed column**:

~~~sql
ALTER TABLE sales_orders
ADD COLUMN sales_channel TEXT;

-- After definition, backfill, and compatible writers:
CREATE INDEX idx_orders_channel_recent_candidate
ON sales_orders (tenant_id, sales_channel, created_at DESC, order_id DESC);
~~~

Adding the column here is a **design option**, omitting live data migration steps. Production rollout requires expand/backfill/validate/contract, JSON-to-column sync rules, `NULL`/`UNKNOWN` handling, and legacy writer compatibility.

### 12.3. When no JSONB index is needed

If Q9 is very rare and Orders are already narrowed by `tenant_id` plus a tight date window, scanning/filtering that subset may be cheaper than maintaining a large GIN index. Having a JSONB column does not automatically require a GIN index. Especially when JSONB updates frequently, index maintenance overhead can be substantial.

**Q9 decision:** weigh flexibility, predicate selectivity, and write overhead; use GIN for diverse containment, typed column + B-tree for key stable dimensions, or no index until gains are measured.

## 13. Q10 — ReserveStock: indexes cannot cure race conditions

Command `ReserveStock` for tenant 11, warehouse 7, Product 101, quantity 2:

~~~sql
UPDATE stock_balances
SET reserved = reserved + 2
WHERE tenant_id = 11
  AND warehouse_id = 7
  AND product_id = 101
  AND on_hand - reserved >= 2
RETURNING on_hand, reserved;
~~~

The PK **`(tenant_id, warehouse_id, product_id)`** already locates **the exact balance row**. Adding indexes on `reserved` or `on_hand` does not help this update: the guard condition must be checked **on the current row after acquiring the write lock**, not by scanning the table for `reserved`.

### 13.1. Explaining correctness

If two requests simultaneously try to reserve the last two units, neither may “`SELECT` 2 remaining” and compute a new balance from a stale read. A conditional `UPDATE` inside the `StockBalance` owner's transaction lets only a valid command update the row; the competing request receives **0 `RETURNING` rows** and is rejected or retried per policy.

Still, a single balance `UPDATE` **is not enough to block duplicate `operation_id` retries**. In a complete design:

1. Insert `StockReservation` with `UNIQUE(tenant_id, operation_id)`.
2. Only when the reservation is new, run the conditional `UPDATE`.
3. If balance is insufficient, roll back the new reservation.
4. If `operation_id` already exists, verify payload and return the idempotent result without incrementing `reserved` again.
5. Commit/roll back reservation and balance in the same transaction or equivalent atomic protocol.

### 13.2. Hot rows are a modeling problem, not a missing index

When thousands of requests concurrently mutate the same hot SKU balance, B-tree lookup is already fast, yet transactions still **contend for the lock on that single row**. Adding indexes increases update work without increasing concurrent throughput for the invariant.

Model/business-level mitigations to evaluate:

- Split stock by warehouse when warehouses hold independent physical inventory.
- Pre-allocate reservation quotas/escrows whose total never exceeds real stock.
- Serialize/queue by SKU when SLAs and business rules allow.
- Offload reads to a read model to reduce contention on the write owner.
- Trim unnecessary secondary updates inside the critical transaction.

**Never split a shared stock pool across multiple shards that can independently sell** without a safe quota/transfer protocol. This is a textbook case where **correctness comes before throughput**.

**Q10 decision:** the PK suffices for lookup; address contention through ownership/write-protocol design, not indexes on quantity columns.

## 14. B-tree technical rules for design grading

These rules are starting points for proposing candidates—**never substitutes for the optimizer or benchmarks**.

### 14.1. Equality, range, sort, and tie-breaker

For query:

~~~sql
SELECT order_id, created_at
FROM sales_orders
WHERE tenant_id = 11
  AND customer_id = 9001
  AND created_at >= '2026-11-01'::TIMESTAMPTZ
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

`(tenant_id, customer_id, created_at DESC, order_id DESC)` fits because leading equalities narrow the prefix, followed by time range/order. `(created_at, tenant_id, customer_id)` may walk across many tenants just to find 50 Orders for one Customer, especially under skew.

### 14.2. A composite index does not replace every single-column index

An index `(tenant_id, customer_id, created_at)` works well for queries filtering `tenant + customer`, yet is **not automatically efficient** for queries filtering only `tenant + created_at`. PostgreSQL may pick different plans, but never assume the third column works like the second when skipping prefix columns.

### 14.3. Backward scans and mixed sort directions

B-trees can scan backward: an ASC PK `(tenant, device, time, event_id)` serves `ORDER BY time DESC, event_id DESC` once both prefix columns are fixed by equality. However, `ORDER BY time DESC, event_id ASC` cannot be satisfied simply by reversing a uniform scan; consider a mixed-direction index or measure sort/incremental-sort cost in the real plan.

### 14.4. INCLUDE and Index Only Scans

`INCLUDE` columns do not participate in key ordering or range searches; they only sit at leaf pages for projection. They enlarge the index and do not always yield Index Only Scans on frequently updated tables, because PostgreSQL must check the visibility map. If `SELECT *` fetches many unindexed columns, `INCLUDE`ing a couple usually fails to produce an Index Only Scan.

### 14.5. Partial indexes bind queries to predicates

If an index has `WHERE status='PENDING'`, the query must prove that predicate at plan time. Queries binding `status = $1` with a generic prepared plan may not use the partial index even when runtime passes `'PENDING'`. Test **exact application SQL and plan modes**, not just hand-typed console literals.

### 14.6. Child-side FK indexes are not automatic

Parent PK/UNIQUEs provide lookup indexes for FK validation, yet PostgreSQL **does not automatically index child-side FK columns**. When deleting/updating parents or querying from parent to child, child indexes can matter. On `OrderLine`, PK `(tenant_id, order_id, line_no)` already leads with the Order reference so no separate `(tenant_id, order_id)` index is needed. Conversely, querying Lines **by Product** may benefit from `(tenant_id, product_id, order_id)` if workload warrants it.

### 14.7. Correctness before speed

A `UNIQUE` index also serves lookups, yet must never be dropped if business rules forbid duplicates. An FK must never be removed for “faster blind writes.” Partial uniqueness with `NULL`s or soft deletes requires clear scope and state definitions before writing DDL.

## 15. Summary matrix of index decisions per query

| Query | First candidate | Why | What must be measured |
| --- | --- | --- | --- |
| Q1 Order by tenant + ID | `PK(tenant, order)` | Equality on PK | Heap reads and network |
| Q1 Lines of Order | `PK(tenant, order, line_no)` | Prefix + order | Lines/Order skew |
| Q2 recent Customer orders | `(tenant, customer, created_at DESC, order_id DESC)`, selective `INCLUDE` | Equality + order + LIMIT | Sort, buffers, index size |
| Q3 pending FIFO | Partial `(tenant, created_at, order_id) WHERE PENDING` | Few entries, FIFO order | Pending ratio, status churn |
| Q4 paid recent | Partial `(tenant, paid_at DESC, order_id DESC) WHERE PAID` | Date range + order | Hot days, UPDATE overhead |
| Q5 external ref | Unique `(tenant, source, ref) WHERE ref IS NOT NULL` | Idempotent business key | Duplicates/conflicts, NULLs |
| Q6 active category | Partial `(tenant, category, product_id) WHERE active` | Category paging | Active ratio, hot categories |
| Q6 lookup SKU | Existing `UNIQUE(tenant, sku)` | Identity lookup | Redundant indexes |
| Q7 top Product by period | Daily mart per tenant/date/product | `GROUP BY` + `SUM` over many Lines | Freshness and corrections |
| Q8 recent device events | `PK(tenant, device, time, event_id)` | Backward B-tree scan | Device skew, metric filter |
| Q8 all-device time range | `BRIN(time)` or time partition | Append/range/retention | Correlation, late data |
| Q9 metadata containment | GIN JSONB, or typed column B-tree | Real predicates | Size, selectivity, writes |
| Q10 reserve stock | `PK(tenant, warehouse, product)` | Atomic single-row update | Lock contention |
| Q11 lookup `order_code` | Existing `UNIQUE(tenant, order_code)` | Equality lookup | Avoid duplicate indexes |
| Q12 closing stock snapshot | `FactInventoryDaily`/columnar | Semi-additive over time | Period-end selection, never `SUM` |

This is a **post-analysis candidate list**, not a script to run blindly. Many entries are conditional, some reuse existing indexes, and some switch **read models** instead of adding indexes.

## 16. When to choose partitioning, BRIN, GIN, or analytical models?

### 16.1. Partitioning solves management and pruning, not every index need

Monthly partitioning helps when most queries/retention rules filter by date across billions of events. Tenant partitioning helps route/co-locate some workloads, yet must confront skew: a 30%-share tenant creates a hot partition/shard.

**Never split a small table into thousands of partitions** just because there are 2,000 tenants; partition counts add metadata, planning overhead, and maintenance cost. Pick partition keys from **queries, data lifecycle management, and invariants**, not merely an obvious column.

In PostgreSQL, PK/UNIQUE constraints on partitioned tables impose rules tied to the partition key. If a table partitions by `created_at` while the business key `source_event_id` must be unique regardless of date, add a dedicated dedup registry—never claim global uniqueness from partition-local indexes.

### 16.2. BRIN fits physically correlated data

BRIN stays compact on append-only time tables with wide range scans and strong correlation between timestamps and heap block order. With heavy late-arriving data or historical updates, BRIN degrades; check heap blocks read and recheck work rather than admiring index size alone.

### 16.3. GIN for structured or text search with matching operators

GIN helps JSONB containment, arrays, or text search under the right operator class. In return, it adds update cost, storage, and combined-filter interactions with `tenant_id`. A critical, schema-stable business field often deserves a typed column and B-tree instead of staying buried in JSONB.

### 16.4. OLTP differs from OLAP

**OLTP** needs accurate commits, keyed lookups, per-aggregate updates, and low latency. **OLAP** needs wide fact scans/aggregations, columnar compression, date partitioning, and versioned dimensions.

Never force an `Orders` table tuned for `INSERT`/`UPDATE` to serve every BI query via 20 indexes. Equally, never route inventory reservation decisions through a lagging analytics dashboard to save OLTP load. Separate **sources of truth** and **read models** with explicit freshness SLAs.

### 16.5. Document and graph models as conditional choices

- **Document:** embedding Lines in Order can speed up whole-order reads when Lines share Order's lifecycle, provided you measure document size, write contention, cross-document Product queries, and logical Customer/Product integrity.
- **Graph:** justified when queries primarily traverse multi-hop relationships like ownership/permissions/dependencies, not merely because a schema has FKs. Verify node/edge grain, acyclicity, and path multiplicities; B-trees on Order usually remain better for ID lookups.
- **Analytical column store:** suited for `SUM`/`GROUP BY` over hundreds of millions of rows, requiring ETL/CDC, reconciliation, versioning, and late-data handling specs.

**Technology selection must follow query patterns and invariants**, never fashion or because a diagram has many lines.

## 17. Reading EXPLAIN: turning indexes into falsifiable hypotheses

A physical choice should only be accepted with workload evidence. In PostgreSQL, **`EXPLAIN`** shows the optimizer's plan, while **`EXPLAIN ANALYZE`** executes the statement and records actual runtime metrics.

Example test for Q2:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, status, total_amount_vnd, created_at
FROM sales_orders
WHERE tenant_id = 11
  AND customer_id = 9001
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

### 17.1. Which parts of the plan should you inspect?

| Signal | Interpretation | Follow-up question |
| --- | --- | --- |
| **Seq Scan** | Sequential scan of table or partition | Is the table tiny and cheap to scan, or missing an index? |
| **Index Scan** | Walks index, may fetch heap | How many rows read and how much random heap I/O? |
| **Index Only Scan** | Reads columns from index; may still heap-fetch | Is the visibility map clean enough? |
| **Bitmap Index/Heap Scan** | Collects TIDs then scans heap pages | Is the predicate selective enough? |
| **Sort / Incremental Sort** | Extra sort step | Does the index match `ORDER BY` and directions? |
| **Hash Join / Nested Loop / Merge Join** | Join strategies | Are join keys, fanout, and pre-filtering sound? |
| **estimated rows vs actual rows** | Cardinality estimation accuracy | Are stats stale, or is skew/column correlation missed? |
| **shared hit/read, temp read/write** | Buffer hits and I/O | Any disk spill or excessive block reads? |
| **loops and Rows Removed by Filter** | Loop count and discarded rows | Is it scanning wide and filtering late? |
| **Planning Time / Execution Time** | Single-run timings | Does it represent production p95? |

**Hypothetical interpretation** example (not actual command output):

~~~text
Before Q2 index:
  Sort -> Seq Scan on sales_orders
  Filter tenant_id/customer_id
  Many rows discarded, must sort before LIMIT.

After Q2 index:
  Limit -> Index Scan using idx_orders_customer_recent
  Index Cond: tenant_id=11 AND customer_id=9001
  Little or no sort needed, stops near LIMIT 50.

Must verify:
  Actual rows, buffers, latency, index size,
  heap fetches, behavior on the largest tenant.
~~~

If the optimizer still picks `Seq Scan` on a 20-row test table, that is likely the right plan. Never force an index just because you created it.

### 17.2. A plan good on average can fail on a hot tenant

The average of 20 million Orders / 2,000 tenants hides the 30%-share tenant. Q2 for a normal Customer with 20 Orders behaves differently from an enterprise Customer with 500,000 Orders. Test:

- Small, medium, and largest tenants.
- Customers with few vs huge Order counts.
- Rare PENDING vs high PENDING ratio.
- Recent time windows vs long historical scans.
- Freshly built index vs after sustained data churn.

Use test data that **preserves real skew and correlations**, not uniform random distributions across 20 million rows.

### 17.3. Statistics and plan caching

After loading representative data, refresh statistics so the optimizer sees the distribution:

~~~sql
ANALYZE sales_orders;
ANALYZE order_lines;
ANALYZE products;
ANALYZE device_events;
~~~

Avoid running `ANALYZE` recklessly during peak traffic if it strains resources; schedule it as part of benchmarking. Correlated columns like `tenant_id`/`status`/`customer_id` can mislead estimates if single-column stats miss correlations; inspect distributions and actual plans.

Prepared statements switch between **custom and generic plans**. A partial index on `status = 'PENDING'` might be skipped when planning `status = $1` generically. Benchmark with **real application statements**, bind parameters, and realistic plan modes—never rely solely on literal console queries.

### 17.4. Measuring index size and usage frequency

~~~sql
-- Run only after creating the index in a test environment.
SELECT pg_size_pretty(
    pg_relation_size('idx_orders_customer_recent'::REGCLASS)
) AS index_size;

-- Stats reflect only the observed window since last reset;
-- never absolute proof an index is unnecessary.
SELECT relname, indexrelname,
       idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes
WHERE relname IN ('sales_orders','order_lines','products')
ORDER BY relname, indexrelname;
~~~

**`idx_scan = 0`** can happen due to a short observation window, recent stats reset, or rare periodic jobs; never `DROP` blindly. For **`UNIQUE`/PK**, the index enforces constraints even when active reads are rare.

`pg_stat_statements`, if installed and permitted, helps inspect query workloads, though it is not always enabled. Check query logs/APM and access traces before concluding an index is unused.

## 18. Designing A/B comparison experiments

Evidence-based indexing weighs **read gains** against **write, storage, operational, and data-drift costs**.

### 18.1. A/B process in a test environment

1. **Freeze SQL and inputs:** queries Q1–Q12, tenant distributions, status churn patterns, date ranges.
2. **Measure baseline:** plans, actual rows, buffers, p50/p95/p99, rows scanned/sorted.
3. **Add one candidate index group at a time** per hypothesis. Never dump all indexes at once and guess which helped.
4. **Run `ANALYZE` as appropriate**, re-test across bind values and hot tenants.
5. **Measure write paths:** `INSERT` Order, `UPDATE` status, `UPDATE` metadata, `ReserveStock`; track WAL, index growth, and CPU.
6. **Test stability:** larger datasets, concurrency, warm/cold caches, and plan stability.
7. **Keep, tune, or drop:** record evidence-backed decisions, not “query felt faster.”
8. **Test rollback:** failing indexes must drop safely without touching constraint-backing indexes.

### 18.2. Experiment results template

| Metric | Baseline | Candidate A | Candidate B | Notes |
| --- | --- | --- | --- | --- |
| Q2 p95 (ms) | Not measured | Not measured | Not measured | Hypothetical target < 150 |
| Q2 Buffers read | Not measured | Not measured | Not measured | Same data/conditions |
| Q3 p95 (ms) | Not measured | Not measured | Not measured | Partial vs general |
| Order INSERT p95 | Not measured | Not measured | Not measured | Write overhead |
| Status UPDATE p95 | Not measured | Not measured | Not measured | Partial index churn |
| Database/index size | Not measured | Not measured | Not measured | Total footprint |
| WAL/replication lag | Not measured | Not measured | Not measured | Operational cost |

**Unmeasured metrics must read “Not measured.”** Never invent fake numbers as if you ran `EXPLAIN`/benchmarks; thresholds in this lesson are study hypotheses.

### 18.3. Total cost of ownership is the true metric

An index speeding a query from 200 ms to 20 ms while slowing 100,000 daily `INSERT`s, heavy `UPDATE`s, and replica lag may not be worth keeping if that query runs three times a week.

Conversely, a `UNIQUE` index adds write overhead yet serves as a **guard against duplicate money/orders** and cannot be dropped for throughput. Index tuning must never break invariants.

### 18.4. Testing skewed and shifting data

An index great this week can lose effectiveness if:

- 90% of Orders move PENDING → PAID hourly, causing heavy partial index churn.
- A new tenant has 100× the median Order count.
- A Product category grows huge and pagination shifts to deep pages.
- Metadata becomes a primary filter and GIN swells.
- Many Device events arrive late, widening BRIN min/max ranges.
- Reports switch from gross line amount to net after refunds, requiring a different fact model.

Designs need **review triggers**, never assuming an index stays optimal across the entire product lifecycle.

## 19. Write overhead, contention, and redundant indexes

### 19.1. Every index is a structure to maintain

One `INSERT` into `SalesOrder` may update:

- `PK(tenant_id, order_id)`.
- `UNIQUE(tenant_id, order_code)`.
- Partial `UNIQUE` external reference if non-null.
- Customer recent index.
- PENDING FIFO index if created PENDING.
- PAID index if status and `paid_at` match predicate.
- JSONB index if present.
- Any additional indexes.

Every index incurs I/O, WAL, cache, vacuum, backup, and sometimes lock/latency costs. **There are no “free indexes”**; adding 10 indexes to rescue 2 queries can be a local optimization that degrades the overall write path.

### 19.2. Status UPDATEs impact partial indexes

When an Order transitions PENDING → PAID:

- Its entry in `idx_orders_pending_fifo` leaves the predicate.
- An entry in `idx_orders_paid_recent` may be inserted.
- Other indexes may require maintenance depending on updated columns.
- High transition rates can cause bloat/overhead.

Never assume a partial index is always small and cheap in every workload; measure **predicate membership ratio and membership churn rate**.

### 19.3. Are INCLUDE columns cold or hot?

If `total_amount_vnd` updates constantly during DRAFT, `INCLUDE(total_amount_vnd)` on Q2's index adds work on every edit. A leaner alternative:

~~~sql
-- Minimal candidate to compare against INCLUDE.
CREATE INDEX idx_orders_customer_recent_min_candidate
ON sales_orders (
    tenant_id, customer_id, created_at DESC, order_id DESC
);
~~~

Do not keep both **`idx_orders_customer_recent`** and **`_min_candidate`** simultaneously. Pick one after benchmarking heap fetches, write p95, index size, and price churn.

### 19.4. Prefix-overlapping indexes and limits of pruning

An index `(tenant_id, customer_id, created_at)` covers some `tenant + customer` lookups, potentially making `(tenant_id, customer_id)` redundant. Still check:

- Shorter indexes are smaller, aiding simple lookups and cache residency.
- SQL variants may differ in `ORDER BY`/`INCLUDE`.
- A `UNIQUE` index is not equivalent to a non-unique one if enforcing a constraint.
- Child-side FKs and parent `UPDATE`/`DELETE` paths may rely on a dedicated index.

Never drop index A purely because “A is a prefix of B” without measuring and checking constraints.

### 19.5. Hot rows are not cured by secondary indexes

`ReserveStock` updates a single `StockBalance` row, yet concurrent transactions still contend for that row's lock. Indexing `reserved` or `on_hand` **does not increase concurrent hot-key commits**; it may even slow `UPDATE`s.

When inventory invariants must hold, choose physical strategies alongside **ownership, per-source escrow/partitioning, transactions, and idempotency**. Measure p95 under real contention.

## 20. Rolling out indexes on large tables without breaking production

Even a well-designed index can disrupt the app if deployed carelessly.

### 20.1. Standard CREATE INDEX vs CONCURRENTLY

In PostgreSQL, standard `CREATE INDEX` blocks concurrent writes during the build. `CREATE INDEX CONCURRENTLY` is worth considering on live tables, trading off a more complex build that still consumes I/O and CPU—it does not mean “zero impact.”

~~~sql
-- Candidate live-deployment command:
-- DO NOT run inside a PostgreSQL transaction block.
CREATE INDEX CONCURRENTLY idx_orders_customer_recent_live
ON sales_orders (
    tenant_id, customer_id, created_at DESC, order_id DESC
);
~~~

This statement is an **alternative** to Q2's index—never create it alongside an existing `idx_orders_customer_recent` serving the same purpose. In real rollouts, manage naming and versioning to avoid collisions.

**`CREATE INDEX CONCURRENTLY` cannot run inside `BEGIN`/`COMMIT`.** If the build fails due to a `UNIQUE` duplicate or operational error, it can leave behind an invalid index; inspect system catalogs and plan cleanup/retries. Never assume a failed DDL leaves everything clean.

### 20.2. Multi-step migration

A safe rollout path:

1. Capture real workload, snapshots/backups, and pre-change baselines.
2. Test index builds on staging with realistic skew and scale.
3. Budget disk/WAL, replication lag, and maintenance windows.
4. Build indexes appropriately (`CONCURRENTLY` when needed and supported).
5. Verify index validity (`indisvalid`) and run `ANALYZE` as appropriate.
6. Re-check query plans with bind parameters across multiple tenants.
7. Monitor `INSERT`/`UPDATE`/replication post-rollout, not just read latency.
8. Keep an observation window before dropping legacy indexes that might still be needed.
9. Prepare runbooks for stalled builds, disk pressure, replica lag, or invalid indexes.
10. Update the ADR and define revisit triggers.

If **changing a shard key or partition key**, that is no longer a simple `CREATE INDEX`: plan backfills, routing, fencing, reconciliation, and preventing split-brain writers.

### 20.3. Dropping indexes safely too

Evaluate `DROP INDEX CONCURRENTLY` to avoid write stalls when removing unused regular indexes on live PostgreSQL, noting its restrictions and that it **cannot run inside a transaction block**. Never drop a `UNIQUE`/PK backing index as “redundant” without auditing its constraint; verify evidence that it no longer protects a business rule.

### 20.4. Operational safety

Document owners, timing, timeouts, disk budgets, and abort procedures. A new index can push **replicas into lag**, spike WAL, and degrade writes even when test `SELECT`s speed up. SLOs cover data freshness and writes, not just `SELECT` latency.

## 21. Complete two-round design exercise

Instead of memorizing index lists, work iteratively in two rounds.

### 21.1. Round A — minimal baseline design

For Section 2's workload, propose adding only what PK/UNIQUE do not already cover:

| Decision | Initial status | Rationale |
| --- | --- | --- |
| Order/Line/Product/Stock PKs | Keep | Identity and Q1/Q10 lookups |
| OrderCode/ProductSKU UNIQUEs | Keep | Business keys Q11/Q6 |
| `idx_orders_customer_recent` | Test adding | Q2 very frequent |
| `idx_orders_pending_fifo` | Test adding | Q3 FIFO when PENDING is rare |
| `idx_orders_paid_recent` | Test adding | Q4 and candidate helper for Q7 |
| `ux_orders_external_source` | Add once invariant approved | Q5 uniqueness/dedup |
| `idx_products_active_category` | Test adding | Q6 active browsing |
| `idx_events_device_metric_recent` | Hold off | Main Q8 does not filter metric |
| `idx_orders_metadata_containment` | Hold off | Q9 rare, needs measurement |
| BRIN/time partition | Evaluate separately | Q8 retention/time scans differ from recent device |
| `product_sales_daily` | Design projection prototype | Q7 large aggregate dashboard |

Round A favors **fewer indexes, intact invariants, and critical queries**. “Hold off” is a deliberate, reasoned decision—not an oversight.

### 21.2. Round B — tuning from measurements

Assuming **no measurements exist yet**, a design review poses these hypotheses:

- Q2 still sorts: check index direction/predicates and actual SQL.
- Q3 generic prepared plan skips partial index: test literal predicate or compare a general index.
- Q4 heavy status writes: measure partial index churn cost.
- Q7 too many Lines: move to daily aggregate and document freshness SLA.
- Q8 filters `metric_code` heavily: test index with `metric_code` before timestamp.
- Q9 becomes critical: test GIN vs promoted typed `sales_channel`.
- Q10 high lock waits: revisit ownership/escrow; never add pointless indexes.

Never record “improved by X×” for unmeasured hypotheses.

### 21.3. Presenting choices in a design review

Every proposed index or projection should carry a concise card:

~~~text
Candidate:
  idx_orders_customer_recent

Supports:
  Q2, 50 most recent Orders of one Customer in a tenant.

Query shape:
  Equality tenant_id + customer_id;
  ORDER BY created_at DESC, order_id DESC;
  LIMIT 50; keyset pagination.

DDL:
  B-tree (tenant_id, customer_id, created_at DESC, order_id DESC)
  INCLUDE(status,total_amount_vnd) if evidence supports it.

Expected benefit:
  Fewer rows read, avoids wide sort.

Expected cost:
  Index storage/WAL, INSERT and UPDATE overhead.

Test:
  EXPLAIN (ANALYZE, BUFFERS) on small/large tenants,
  p95/p99, heap fetches, insert/update p95.

Decision status:
  PROPOSED — unmeasured; do not mark PASS yet.
~~~

This turns “I think this index is good” into a **falsifiable hypothesis**.

## 22. Self-study problems with solution guides

### Exercise 1. Redundant index for Order detail

**Prompt:** Order has `PK(tenant_id, order_id)`. A colleague proposes `CREATE INDEX(order_id)` just to read one Order by tenant and ID. Should you agree?

**Guide:** Not by default. The composite PK already serves equality on both columns, preserving tenant scope and identity. `Index(order_id)` adds write cost with no proven query needing it.

### Exercise 2. Recent orders and key order

**Prompt:** Q2 filters `tenant_id`, `customer_id`, and sorts `created_at DESC, order_id DESC`. Choose between A=`(created_at, tenant_id, customer_id)` and B=`(tenant_id, customer_id, created_at DESC, order_id DESC)`.

**Guide:** B fits better with leading equalities followed by sort/limit. A may scan across many tenants/customers over time. Confirm with real plans and workload.

### Exercise 3. Deep OFFSET

**Prompt:** A customer has 500,000 Orders and requests page 3,000 with `LIMIT 50`. Can adding `INCLUDE` alone solve it?

**Guide:** No. Deep `OFFSET` still skips past huge row counts. Use a keyset cursor `(created_at, order_id)` matching a deterministic sort; consider snapshots/cutoffs when new data arrives.

### Exercise 4. Partial or general status index?

**Prompt:** Only 2% of Orders are PENDING, and the FIFO query always hardcodes `status='PENDING'`. Which index?

**Guide:** Test partial `(tenant_id, created_at, order_id) WHERE status='PENDING'`. If queries use generic prepared parameters or status churn is high, benchmark and compare a general `(tenant_id, status, created_at, order_id)` index.

### Exercise 5. Source reference and uniqueness

**Prompt:** Two partners independently issue reference `X-100`. One partner sends the same reference twice. Which columns belong in the unique key?

**Guide:** Under exercise assumptions, `(tenant_id, source_system, source_order_ref)` when non-null. On retries with the same ID, verify payloads match; same ID with a different payload is a conflict. Never use a global `UNIQUE(reference)`.

### Exercise 6. Active Products and category

**Prompt:** Active Products are 20%, and an API fetches active items in category 501 ordered by `product_id`. Is a single index on `is_active` optimal?

**Guide:** Evaluate `(tenant_id, category_id, product_id) WHERE is_active`; a bare boolean index poorly serves tenant/category equality and `product_id` order. Measure on the largest categories.

### Exercise 7. Arbitrary substring name search

**Prompt:** Q6 changes to `product_name ILIKE '%headphones%'`. Will a standard B-tree`(product_name)` perform well?

**Guide:** Not for leading wildcards. Test `pg_trgm` GIN/GiST if extensions are allowed, or a dedicated search service; evaluate language rules, selectivity, and write cost.

### Exercise 8. Top Products in a period

**Prompt:** Does an index on `order_lines(product_id, unit_price_vnd)` directly return the top 10 Products by monthly revenue?

**Guide:** No. Per-product totals must group sold Lines in the month and join Order dates/statuses. At scale, test a daily fact/aggregate with explicit grain and freshness; indexes aid joins/filters but do not replace `SUM`.

### Exercise 9. Reading recent DeviceEvents

**Prompt:** `PK(tenant_id, device_id, observed_at, event_id)`. Query filters tenant+device, `ORDER BY observed_at DESC, event_id DESC LIMIT 500`. Do we strictly need a separate `DESC` index?

**Guide:** No. PostgreSQL can scan the B-tree backward when both trailing columns share the `DESC` direction. Inspect plans before creating duplicate indexes.

### Exercise 10. BRIN with late-arriving data

**Prompt:** `DeviceEvent` continuously backfills past months; is `BRIN(observed_at)` always effective?

**Guide:** No. BRIN relies on correlation between timestamp and physical block order; late data/backfills widen min/max ranges, increasing block rechecks. Measure and compare against B-tree/partitioning.

### Exercise 11. Dominant JSONB filter

**Prompt:** `sales_channel` becomes a filter in 70% of Order queries. Is keeping it in `metadata` with one generic GIN always best?

**Guide:** No. Evaluate promoting to a typed column + B-tree on `(tenant, channel, time)`; weigh migration/dual-write costs and benchmark GIN vs typed index on real workload.

### Exercise 12. Hot stock row

**Prompt:** A hot SKU has high p99 update latency despite fast PK lookups. Will `CREATE INDEX(reserved)` fix it?

**Guide:** It will not cure row lock contention. Address concurrency, ownership, business-approved escrow/quotas, and per-transaction work. The PK already finds the row.

### Exercise 13. Multiplying numbers via JOIN

**Prompt:** An Order has 4 Lines and 3 PaymentAttempts. Joining both and summing `amount_attempt` yields how many rows and what error?

**Guide:** It produces `4 × 3 = 12` rows, multiplying each Attempt fourfold. Pre-aggregate both child sets to `(tenant_id, order_id)` before joining, distinguishing succeeded attempts from duplicate callbacks.

### Exercise 14. Large tenant and partition strategy

**Prompt:** 30% of Orders belong to one tenant, and a team plans 2,000 hash partitions (one per tenant). Will it stay balanced and easy to manage?

**Guide:** No. The hot tenant stays hot; 2,000 partitions add planning, metadata, and maintenance overhead. Measure skew, query scope, routing, partition count, and ways to split hot tenants without breaking transactions/uniqueness.

### Exercise 15. INCLUDE under frequent updates

**Prompt:** Q2's index `INCLUDE`s `total_amount_vnd`, yet DRAFT Orders edit `total_amount` constantly and Index Only Scans rarely trigger. Keep `INCLUDE`?

**Guide:** Only if measured gains exceed costs. Compare against a narrower index without `INCLUDE`, measuring heap fetches, write p95, size, and cache impact; consider dropping `INCLUDE`.

### Exercise 16. Stale stats and skewed plans

**Prompt:** A query runs fast for small tenants yet crawls for large tenants. An index exists—can we mark it PASS?

**Guide:** Not yet. Benchmark under skew/hot tenants, inspect estimated vs actual rows, plan caches, and statistics. Validate tail latency under real workload rather than hiding behind averages.

### Exercise 17. Building indexes in production

**Prompt:** A new index must be built on 20 million Orders. The team puts `CREATE INDEX CONCURRENTLY` inside a migration `BEGIN`/`COMMIT` block. Is that valid?

**Guide:** Invalid in PostgreSQL. Isolate the DDL outside transactions, budget disk/WAL/replication, and prepare runbooks for invalid-index checks and rollback/forward-fix.

### Exercise 18. Unique event ID across time partitions

**Prompt:** Events partition monthly, and the PK includes `observed_at`. Will the PK block the same `event_id` arriving with a timestamp in next month's partition?

**Guide:** Not if the unique key includes timestamp. Enforce time-independent source-ID deduplication at the owner/registry or via an engine supporting global constraints.

### Exercise 19. Warehouse inventory snapshots

**Prompt:** End-of-day stock is 20 units and a corrected snapshot shows 18 units. Is a dashboard adding `20 + 18 = 38` as “stock” right?

**Guide:** No. Those are two versions of the same snapshot grain. Pick the valid version per cutoff/version; across time, use semi-additive logic rather than summing point-in-time balances like transaction deltas.

### Exercise 20. Duplicate indexes with identical keys

**Prompt:** `PK(tenant_id, order_id)` exists alongside a new index `(tenant_id, order_id)` with another name. The team says “a separate index reads faster than PK.” What should you do?

**Guide:** Disprove the assumption with query plans and the index inventory. With identical key and order, the PK already provides the B-tree lookup. A duplicate index merely adds disk/write overhead unless a distinct proven requirement exists.

## 23. Physical design grading rubric

A submission can be scored on the **100-point** scale below; this is an illustrative study rubric, not company policy.

| Category | Max points | Passing bar |
| --- | ---: | --- |
| Query and workload understanding | 20 | Covers Q1–Q12, filters/sorts/limits/joins, skew, SLOs |
| Grain and invariants | 15 | Accurate keys/tenant/units/lifecycles; intact FKs/UNIQUEs |
| B-tree/partial/covering index choices | 20 | Right key order, reuses existing indexes, avoids duplicates |
| BRIN/GIN/partition/OLAP choices | 15 | Matches query patterns, understands limits |
| `EXPLAIN` and benchmark evidence | 15 | Plans/rows/buffers, multi-tenant skew, write costs |
| Rollout and operations | 10 | Index builds, retries, WAL, rollback, monitoring |
| Trade-off explanations | 5 | Justifies why certain indexes were **not** added |

**Critical disqualifier:** even with a high score, a design **fails** if it drops tenant isolation, removes required uniqueness, or relies on stale caches for inventory oversell checks. P0 invariants cannot be traded for p95 speedups.

### 23.1. What a review-ready solution contains

Learners must submit:

1. Workload matrix with clearly labeled hypothetical frequencies and scales.
2. Physical DDL or physical entity diagram with key scopes.
3. Each index proposal listing owning query, DDL, expected benefit, and cost.
4. List of indexes **not added** because existing PK/UNIQUEs cover them.
5. Explanation of which queries need projections/warehouses instead of indexes.
6. `EXPLAIN`/benchmark plan with real measurements or marked **NOT RUN**.
7. Invariants, access controls, history, and migration risks to protect.
8. Final GO / TEST MORE / REJECT recommendation with conditions and owners.

## 24. Pre-deployment checklist for physical choices

- [ ] Defined **one row** for every table/fact, keys, cardinalities, and tenant/source scopes.
- [ ] Real SQL shapes capture `WHERE`/`JOIN`/`ORDER BY`/`LIMIT` and bind patterns.
- [ ] Estimated row counts/frequencies, data skew, hot keys, and SLOs.
- [ ] Inventoried existing PK/UNIQUE/indexes; avoided redundant indexes.
- [ ] B-tree column order aligns with equality/range/order, sort directions, and tie-breakers.
- [ ] Partial index predicates align with how queries are actually planned.
- [ ] `INCLUDE` is justified by write/index-only benchmarks, not guesswork.
- [ ] GIN/BRIN/partitions target matching workloads and are tested against late/skewed data.
- [ ] Q7/Q12 specify measure grain, additivity rules, and sources of truth; never `SUM` snapshots blindly.
- [ ] Heavy queries or dashboards evaluated for separate read models with freshness SLAs.
- [ ] Stock/Payment/Order invariants retain proper owners, transactions, and idempotency.
- [ ] Queries/caches/indexes never leak cross-tenant data; negative auth tests exist.
- [ ] `EXPLAIN (ANALYZE, BUFFERS)` on representative data saved, labeling real tests vs hypotheses.
- [ ] Read p95/p99 weighed against `INSERT`/`UPDATE` p95, WAL, replica lag, and index size.
- [ ] Migration plan covers `CREATE INDEX CONCURRENTLY` where needed, invalid-index cleanup, and rollback.
- [ ] Plan exists to monitor stats and revisit choices as workload/schema/scale shift.
- [ ] Unmeasured items labeled **PROPOSED/NOT RUN** rather than claiming production SLOs are met.

## 25. Key takeaways

- **Choose physical models from real queries**, not from column lists.
- **PK/UNIQUE constraints already create indexes:** many ID lookups have paths built in; extra indexes may be redundant.
- **Composite indexes must align equality, range, sort, and tie-breaker**; keyset pagination avoids deep `OFFSET` scans.
- **Partial indexes** shine when predicates are fixed and subsets are small, yet status churn or generic prepared plans can change outcomes.
- **`INCLUDE`** can cut heap fetches at the cost of larger indexes; Index Only Scans still depend on visibility.
- **BRIN** relies on physical correlation, **GIN** on operators/operator classes, and **partitioning** on pruning and lifecycle operations—none replace B-trees or constraints everywhere.
- **Top aggregates over millions of Lines are a read-model problem:** use proper grains and marts, not indexes on summed columns.
- **Hot inventory rows are a concurrency/ownership problem**, not a missing index.
- **An `EXPLAIN` plan alone is not proof of production performance**; claim p95 targets only after measuring representative workloads.
- **Optimization is a system-wide balance:** query latency, write throughput, disk/WAL, migrations, security, and evolvability.

A strong physical design is not the one with the most indexes or the prettiest `EXPLAIN` in a lab. It is the one that **justifies every choice from real queries, protects business invariants, measures both benefits and costs, and adapts safely as data and requirements evolve**.
