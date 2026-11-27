# Star Schema, Snowflake Schema, and Multiple Fact Tables Sharing Dimensions

A retail system can quickly answer **"Which products are in this order?"** using a relational model built for transactions. Analytical questions, however, are fundamentally different:

- What is revenue by **day, product, and store**?
- How is returned quantity changing across categories?
- Is end-of-day inventory at each store sufficient relative to sales velocity?
- When combining sales, returns, and inventory facts, how do we avoid **double-counting revenue** or **summing inventory incorrectly across time**?

To answer those questions, analytical data models typically use **fact tables**, **dimension tables**, and three notable structural patterns:

1. **Star schema:** a central fact table linked directly to descriptive dimensions, usually denormalized/flattened to reduce JOIN hops.
2. **Snowflake schema:** one or more dimensions normalized into sub-level tables, such as Product → Category → CategoryGroup.
3. **Fact constellation (galaxy schema):** multiple business processes maintain separate fact tables while sharing conformed dimensions like Date, Product, and Store.

This lesson belongs to the **Analytical Modeling** chapter of the **DATABASE_DATA_MODELING** module. Its goal is to translate reporting requirements into models with explicit **grain**, keys, constraints, history, and aggregation rules, while understanding trade-offs across transactional relational, document, graph, and analytical data warehouse models. SQL examples illustrate concepts on PostgreSQL and do not represent every optimization feature of specialized analytical warehouses.

> **Starting point:** Before drawing a star, put into words "what one row of the fact represents". Without defining grain, every downstream JOIN, count, and sum risks being wrong—even if the query runs fast.

## 1. Foundations: Facts, Dimensions, and Grain

### 1.1. Fact Table

A **fact** records an **event**, **measured state**, or **workflow progression** at a defined level of detail. It typically contains:

- Foreign keys referencing dimensions: date, product, store, customer.
- **Measures**: quantity sold, sales amount, refund amount, stock on hand.
- Transaction identifiers for lineage; for instance, `order_id` can act as a **degenerate dimension** when only a business identifier is needed without a full Order dimension table.

For example, one row of **`fact_sales_line`** might mean:

> "One merchandise line recorded as successfully sold within an order, at a point in time, for a specific product, store, and customer."

One row of this fact does **not** represent "an order" (since an order has multiple lines), nor does it represent "an entire day's revenue" (since multiple lines can occur on the same day).

### 1.2. Dimension Table

A **dimension** provides context to **filter, group, roll up, and label** facts:

- **DimDate:** day, month, quarter, year, day of week.
- **DimProduct:** product code, name, brand, category, category group.
- **DimStore:** store code, city, sales region.
- **DimCustomer:** segment, customer tier, market; may carry personal data protection requirements.

Dimensions typically use a **surrogate key** independent of the business code. For instance, product code `P-001` may carry multiple distinct `product_key` values across historical versions when using **Slowly Changing Dimension Type 2 (SCD2)**.

### 1.3. Grain Is the Contract of the Fact

| Fact | What One Row Represents | Example Dimension Keys | Typical Measures |
| --- | --- | --- | --- |
| Sales | **One successfully sold line item** | `sales_date`, `product`, `store`, `customer` | `quantity`, `net_sales_amount` |
| Returns | **One return line/event** | `return_date`, `product`, `store` | `returned_quantity`, `refund_amount` |
| Daily inventory | **One product at one store at end of day** | `snapshot_date`, `product`, `store` | `units_on_hand` |
| Sales target | **One store for one month** | `target_month`, `store` | `target_amount` |
| Fulfillment progress | **One order across delivery milestones** | `order_date`, `ship_date`, `delivery_date` | processing days, final status |

Measures at different grains cannot be combined as though they carry the same meaning. An end-of-day inventory fact is not a sales event. A monthly target fact must not be multiplied across every order line in that month.

### 1.4. Distinguishing Three Common Fact Types

- **Transaction fact:** each occurrence of a transaction/event creates a new row, such as a sales line or a refund. Suitable for summing across days when measures are additive and currency/deduplication rules hold.
- **Periodic snapshot fact:** captures state at regular intervals, such as end-of-day inventory. Measures can be **summed across products/stores at the same point in time** but generally **must not be summed across multiple days**.
- **Accumulating snapshot fact:** one row per process with a start and completion, updating milestones such as `ordered_at`, `packed_at`, `shipped_at`, and `delivered_at`. Do not confuse it with an event fact: updating a milestone must not be counted as a brand-new order.

In analytical modeling, **row count** is not a KPI. KPIs depend on grain, metric definitions, event filtering, and aggregation rules.

## 2. Star Schema

### 2.1. Shape and Semantics

Example sales process:

~~~mermaid
flowchart LR
    D["DimDate"] --> F["FactSalesLine"]
    P["DimProduct"] --> F
    S["DimStore"] --> F
    C["DimCustomer"] --> F
~~~

Dimensions surround the fact table like points of a star. The fact stores keys referencing each dimension instead of repeating full product names, store names, and customer segments on every transaction row.

Conceptual example:

~~~text
FactSalesLine(
    sales_line_key,
    order_id,
    line_no,
    sales_date_key,
    product_key,
    store_key,
    customer_key,
    quantity,
    gross_amount,
    discount_amount,
    net_sales_amount
)

DimProduct(
    product_key,
    product_code,
    product_name,
    brand_name,
    category_name,
    category_group_name,
    ...
)
~~~

What makes it a **"star"** is not whether SQL has four JOINs or five JOINs, but that **the fact carries dimension keys** and **dimensions express analytical context**. Dimensions can hold rich descriptive attributes, hierarchies, and history.

### 2.2. Why Are Dimensions Commonly Flattened?

If every Product has a Brand, Category, and CategoryGroup, storing those descriptive names together in `DimProduct` allows a revenue-by-category query to require only:

~~~sql
SELECT p.category_name,
       SUM(f.net_sales_amount) AS net_sales
FROM fact_sales_line AS f
JOIN dim_product AS p ON p.product_key = f.product_key
GROUP BY p.category_name;
~~~

This query illustrates the access pattern; full DDL appears later.

**Common advantages:**

- Intuitive for BI users: the sales fact joins directly to the product dimension.
- Queries filtering or grouping by classification attributes avoid cascading JOINs across hierarchy tables.
- Can store a **historical attribute snapshot** of the Product inside each dimension version.
- Optimizes columnar reads/scans/joins in many warehouse engines when facts grow massive.

**Trade-offs:**

- Category/Brand names repeat across many `DimProduct` rows.
- Reclassifications require explicit history rules or properly scoped updates.
- Wide dimensions can increase storage footprint and maintenance effort.
- Not every repeated attribute in a dimension is a normalization flaw: the goal here is **controlled analytical query optimization**, not merely achieving the highest normal form.

### 2.3. Star Schema Does Not Mean Abandoning Data Integrity

Facts must reference valid dimensions. When the warehouse uses foreign keys for enforcement, every `product_key` must exist in `DimProduct`. Some analytical platforms treat FKs only as **metadata** without full enforcement; in that case, pipelines and data tests must assume responsibility for referential integrity.

When the source has not yet identified a Product at fact load time, establish an explicit policy:

- Quarantine/hold the fact and resolve upstream source data.
- Create an **Unknown/Not yet identified** dimension record with a dedicated surrogate key.
- Reprocess/backfill when the **late-arriving dimension** arrives.

**Never silently drop facts** simply because a dimension lookup missed, especially for financial transactions requiring reconciliation.

## 3. Snowflake Schema

### 3.1. Partially or Fully Normalizing Dimensions

Instead of placing every classification tier inside `DimProduct`, split them out:

~~~mermaid
flowchart LR
    F["FactSalesLine"] --> P["DimProduct"]
    P --> B["DimBrand"]
    P --> C["DimCategory"]
    C --> G["DimCategoryGroup"]
    F --> D["DimDate"]
    F --> S["DimStore"]
    F --> U["DimCustomer"]
~~~

Under this design, a Brand or Category holds its own row referenced by multiple Products.

**Difference from star schema:** The fact retains the **exact same grain** and measures. Snowflaking primarily changes **how descriptive attributes are organized within dimensions**, rather than "normalizing" the fact to a different grain.

### 3.2. Example Snowflake Dimension DDL

This is an **alternative design** to the flattened `DimProduct`, not a requirement to deploy both in parallel:

~~~sql
CREATE TABLE dim_category_groups_sf (
    category_group_key BIGINT PRIMARY KEY,
    category_group_code TEXT NOT NULL UNIQUE,
    category_group_name TEXT NOT NULL
);

CREATE TABLE dim_categories_sf (
    category_key BIGINT PRIMARY KEY,
    category_code TEXT NOT NULL UNIQUE,
    category_name TEXT NOT NULL,
    category_group_key BIGINT NOT NULL
        REFERENCES dim_category_groups_sf(category_group_key)
);

CREATE TABLE dim_brands_sf (
    brand_key BIGINT PRIMARY KEY,
    brand_code TEXT NOT NULL UNIQUE,
    brand_name TEXT NOT NULL
);

CREATE TABLE dim_products_sf (
    product_key BIGINT PRIMARY KEY,
    product_code TEXT NOT NULL,
    product_name TEXT NOT NULL,
    category_key BIGINT NOT NULL
        REFERENCES dim_categories_sf(category_key),
    brand_key BIGINT NOT NULL
        REFERENCES dim_brands_sf(brand_key)
);
~~~

If the fact references the snowflaked `dim_products_sf`, a revenue query by category group looks like:

~~~sql
-- Assumes fact_sales_line.product_key references dim_products_sf.
SELECT cg.category_group_name,
       SUM(f.net_sales_amount) AS net_sales
FROM fact_sales_line AS f
JOIN dim_products_sf AS p ON p.product_key = f.product_key
JOIN dim_categories_sf AS c ON c.category_key = p.category_key
JOIN dim_category_groups_sf AS cg
  ON cg.category_group_key = c.category_group_key
GROUP BY cg.category_group_name;
~~~

This example set **illustrates an alternative strategy**. Do not run the query above against a schema whose FK points to the star-schema `DimProduct` without adapting the model and keys accordingly.

### 3.3. Why Choose Snowflake?

Reasonable scenarios include:

- The organization has a **centrally governed, shared category/brand taxonomy**.
- Higher classification levels carry **their own attributes** or are shared by other dimensions.
- You need to curb heavy duplication of large attribute sets or frequent hierarchy restructuring.
- A dimension has huge cardinality and upper-tier fields need independent lifecycle management.

Costs to accept:

- Queries and BI semantic models traverse more JOINs.
- Query plans can become more complex depending on engine, indexing/clustering, and data distribution.
- Updating the Category hierarchy can **reinterpret history** if Category uses Type 1 while reports require point-in-time classification at sale.
- Extra FKs, load ordering, key checks, and cross-table history rules are needed.

Never conclude "star is always faster" or "snowflake always saves space" without benchmarking on your engine and representative data. Columnar storage, join algorithms, caching, dimension row counts, and query patterns determine actual performance.

## 4. When Multiple Processes Exist: Fact Constellation (Galaxy)

An enterprise routinely measures multiple distinct processes. Sales, returns, inventory, payments, shipments, and sales targets **should not be crammed into one giant fact table** merely because they all touch Product.

~~~mermaid
flowchart TB
    D["Shared DimDate"]
    P["Shared DimProduct"]
    S["Shared DimStore"]
    C["DimCustomer"]
    F1["FactSalesLine"]
    F2["FactReturnLine"]
    F3["FactInventoryDaily"]
    D --> F1
    D --> F2
    D --> F3
    P --> F1
    P --> F2
    P --> F3
    S --> F1
    S --> F2
    S --> F3
    C --> F1
~~~

All three facts share Date, Product, and Store under **consistent definitions**, yet each operates at its own grain:

| Process | Fact | Grain | Role of Date | Primary Dimensions |
| --- | --- | --- | --- | --- |
| Sales | `FactSalesLine` | One successfully sold line item | Sale date | Date, Product, Store, Customer |
| Returns | `FactReturnLine` | One return line/event | Return recognition date | Date, Product, Store |
| Inventory | `FactInventoryDaily` | One Product at one Store at end of day | Snapshot date | Date, Product, Store |

**Shared dimensions (conformed dimensions)** do not mean every fact must contain every dimension key. Store inventory without a Customer key is completely normal; inventing a dummy Customer just to complete the star is usually a grain error.

### 4.1. Conditions for a Dimension to Truly Be "Conformed"

`DimProduct` is genuinely conformed only when reporting teams agree on:

1. **Identity:** Product `P-001` in sales and returns refers to the exact same business product code.
2. **Scope:** Is the code globally unique across the enterprise or scoped to a tenant/system?
3. **Semantics:** Does one product represent a SKU, variant, bundle, or product line?
4. **Attributes:** Category, Brand, hierarchies, and NULL conventions are defined consistently.
5. **History:** When a Product changes Category, are historical facts viewed under the **old** or **current** classification?
6. **Keys:** If using versioned surrogate keys, ETL resolves the proper version for each event's timestamp.
7. **Data quality:** Source code mapping, unknown records, duplicates, naming standardization, and code-change handling.

Two tables both having a column named **`product_id`** is not enough proof of a conformed dimension. If system A treats a "product" as a SKU while system B treats it as a SKU family, joining directly on code or dimension produces wrong results.

### 4.2. Role-Playing Dimensions

Date is the classic example:

- `FactSalesLine` has **`sales_date_key`**.
- `FactReturnLine` has **`return_date_key`**.
- `FactInventoryDaily` has **`snapshot_date_key`**.

All three keys can reference the same `DimDate`, yet **each date's role differs**. When reporting sales and refunds by **recognition date**, users must know `sales_date` is when the sale occurred and `return_date` is when the return occurred. When computing what percentage of a month's sold orders were later returned, you need a **cohort by original sale date**—not same-month returns divided by same-month sales mislabeled as a cohort return rate.

A fulfillment fact may also use multiple Date roles within **the same row**: `order_date_key`, `ship_date_key`, `delivered_date_key`. The BI layer can expose them as separate role-playing date dimensions even though all keys point to one physical table.

## 5. PostgreSQL DDL for a Minimal Galaxy Model

For a testable illustration, assume:

- All monetary amounts are in **VND**; multi-currency systems require currency codes and exchange-rate/conversion rules.
- Sales lines are recorded upon valid completed sales, excluding draft carts.
- Returns are **separate events** with positive `refund_amount`; never delete the original sales line.
- Store on `FactReturnLine` is the **attributable original selling store**, not necessarily the physical return drop-off branch. If drop-off branch analysis is needed, add `return_processing_store_key` with distinct semantics.
- Inventory snapshots capture end-of-day quantities using the same business timezone rule.

### 5.1. Star Dimension Tables

~~~sql
-- PostgreSQL: training example, not a complete production DDL suite.
CREATE TABLE dim_date (
    date_key INTEGER PRIMARY KEY,               -- e.g. 20261010
    calendar_date DATE NOT NULL UNIQUE,
    calendar_year SMALLINT NOT NULL,
    calendar_month SMALLINT NOT NULL
        CHECK (calendar_month BETWEEN 1 AND 12),
    day_of_month SMALLINT NOT NULL
        CHECK (day_of_month BETWEEN 1 AND 31)
);

CREATE TABLE dim_product (
    product_key BIGINT PRIMARY KEY,             -- surrogate version
    product_code TEXT NOT NULL,                 -- stable business identifier
    product_name TEXT NOT NULL,
    brand_name TEXT NOT NULL,
    category_name TEXT NOT NULL,
    category_group_name TEXT NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    is_current BOOLEAN NOT NULL,
    CHECK (valid_to IS NULL OR valid_to > valid_from),
    CHECK ((valid_to IS NULL) = is_current)
);

-- Each product code has at most one current version.
CREATE UNIQUE INDEX uq_dim_product_current
ON dim_product (product_code)
WHERE is_current;

CREATE TABLE dim_store (
    store_key BIGINT PRIMARY KEY,
    store_code TEXT NOT NULL UNIQUE,
    store_name TEXT NOT NULL,
    city_name TEXT NOT NULL,
    region_name TEXT NOT NULL
);

CREATE TABLE dim_customer (
    customer_key BIGINT PRIMARY KEY,
    customer_code TEXT NOT NULL UNIQUE,
    customer_segment TEXT NOT NULL
);
~~~

**`DimProduct`** in this example stores multiple Type 2 versions. `product_key` distinguishes **versions**, while `product_code` identifies the product **across versions**. The partial unique index only prevents two versions from being **simultaneously current**; it **does not prevent historical effective intervals from overlapping**. The system needs additional interval-overlap checks and transactional ETL/merge logic.

**`DimStore`** and **`DimCustomer`** are simplified to Type 1 here. If region or customer segment attributes require history, they may also need versioning like Product, adjusting keys and fact lookup pipelines accordingly.

### 5.2. Sales Transaction Fact

~~~sql
CREATE TABLE fact_sales_line (
    sales_line_key BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,                   -- degenerate dimension
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    sales_date_key INTEGER NOT NULL
        REFERENCES dim_date(date_key),
    product_key BIGINT NOT NULL
        REFERENCES dim_product(product_key),
    store_key BIGINT NOT NULL
        REFERENCES dim_store(store_key),
    customer_key BIGINT NOT NULL
        REFERENCES dim_customer(customer_key),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    gross_amount NUMERIC(16, 2) NOT NULL CHECK (gross_amount >= 0),
    discount_amount NUMERIC(16, 2) NOT NULL CHECK (discount_amount >= 0),
    net_sales_amount NUMERIC(16, 2) NOT NULL
        CHECK (net_sales_amount >= 0),
    UNIQUE (order_id, line_no),
    CHECK (net_sales_amount = gross_amount - discount_amount)
);
~~~

This assumes a sales line has positive quantity, non-negative gross and discount amounts, and **`net_sales_amount = gross_amount − discount_amount`**. If the business involves taxes, fees, allocated coupons, price overrides/cancellations, or negative adjustment lines, redefine the measures rather than blindly retaining this `CHECK`.

**`order_id`** is assumed globally unique across the system. If order IDs are unique only within a tenant or store, both `UNIQUE` and `COUNT(DISTINCT order_id)` queries must include **`tenant_id` or a globally qualified transaction identifier**.

### 5.3. Returns Fact and Daily Inventory Snapshot Fact

~~~sql
CREATE TABLE fact_return_line (
    return_line_key BIGINT PRIMARY KEY,
    return_reference TEXT NOT NULL,
    original_sales_line_key BIGINT NOT NULL
        REFERENCES fact_sales_line(sales_line_key),
    return_date_key INTEGER NOT NULL
        REFERENCES dim_date(date_key),
    product_key BIGINT NOT NULL
        REFERENCES dim_product(product_key),
    store_key BIGINT NOT NULL
        REFERENCES dim_store(store_key),
    returned_quantity INTEGER NOT NULL
        CHECK (returned_quantity > 0),
    refund_amount NUMERIC(16, 2) NOT NULL
        CHECK (refund_amount >= 0)
);

CREATE TABLE fact_inventory_daily (
    snapshot_date_key INTEGER NOT NULL
        REFERENCES dim_date(date_key),
    product_key BIGINT NOT NULL
        REFERENCES dim_product(product_key),
    store_key BIGINT NOT NULL
        REFERENCES dim_store(store_key),
    units_on_hand INTEGER NOT NULL,
    inventory_cost_amount NUMERIC(16, 2),
    PRIMARY KEY (snapshot_date_key, product_key, store_key)
);
~~~

Here **`units_on_hand`** may be 0 or negative if the system allows recording negative stock discrepancies; if policy forbids negative stock, add **`CHECK(units_on_hand >= 0)`**. Do not add a `CHECK` merely because "stock is usually non-negative" if operations legitimately log negative adjustments.

Linking to `original_sales_line_key` provides return lineage. However, FKs **do not automatically prove**:

- `returned_quantity` does not exceed sold quantity minus prior returns;
- `product_key` and `store_key` on the return match attribution rules relative to the original sale;
- each return line from the source is loaded exactly once;
- `refund_amount` complies with pricing/tax refund policies.

Those rules require **source natural keys, ETL validation, business controls, and reconciliation**—some spanning across facts.

### 5.4. Index by Queries, Not by Diagram Aesthetics

~~~sql
CREATE INDEX idx_sales_date_product_store
ON fact_sales_line (sales_date_key, product_key, store_key);

CREATE INDEX idx_sales_product_date
ON fact_sales_line (product_key, sales_date_key);

CREATE INDEX idx_return_date_product_store
ON fact_return_line (return_date_key, product_key, store_key);

CREATE INDEX idx_return_original_sale
ON fact_return_line (original_sales_line_key);
~~~

These B-tree indexes illustrate PostgreSQL indexing for date/product filtering. On columnar/MPP warehouses, optimization relies on **partition pruning, clustering, sorting, compression, or partition/cluster keys**, not copying every OLTP index verbatim.

Measure with **`EXPLAIN (ANALYZE, BUFFERS)`** on representative data and workloads—checking scanned bytes, cardinality estimates, JOIN strategies, sort/hash spills, latency, and load overhead. Optimization decisions should rest on real query plans, not just whether star or snowflake diagrams appear to have fewer JOINs.

## 6. Small Dataset to Verify Grain and Metrics

Example for product `P-001` at store `HCM-01`; all monetary measures are in VND.

~~~sql
INSERT INTO dim_date
(date_key, calendar_date, calendar_year, calendar_month, day_of_month)
VALUES
    (20261010, DATE '2026-10-10', 2026, 10, 10),
    (20261011, DATE '2026-10-11', 2026, 10, 11);

INSERT INTO dim_product
(product_key, product_code, product_name, brand_name,
 category_name, category_group_name,
 valid_from, valid_to, is_current)
VALUES
    (101, 'P-001', 'Wireless Headphones', 'Brand A',
     'Headphones', 'Audio Devices',
     TIMESTAMPTZ '2026-01-01 00:00:00+07', NULL, TRUE);

INSERT INTO dim_store
(store_key, store_code, store_name, city_name, region_name)
VALUES
    (11, 'HCM-01', 'Downtown Store', 'Ho Chi Minh City', 'South');

INSERT INTO dim_customer
(customer_key, customer_code, customer_segment)
VALUES
    (51, 'C-001', 'RETAIL');

INSERT INTO fact_sales_line
(sales_line_key, order_id, line_no, sales_date_key,
 product_key, store_key, customer_key,
 quantity, gross_amount, discount_amount, net_sales_amount)
VALUES
    (1001, 501, 1, 20261010, 101, 11, 51, 2, 200000, 0, 200000),
    (1002, 502, 1, 20261010, 101, 11, 51, 1, 100000, 0, 100000),
    (1003, 503, 1, 20261011, 101, 11, 51, 3, 300000, 0, 300000);

-- Return 1 unit from sales line 1001, recorded on Oct 11.
INSERT INTO fact_return_line
(return_line_key, return_reference, original_sales_line_key,
 return_date_key, product_key, store_key, returned_quantity, refund_amount)
VALUES
    (2001, 'RET-001', 1001, 20261011, 101, 11, 1, 100000);

INSERT INTO fact_inventory_daily
(snapshot_date_key, product_key, store_key, units_on_hand,
 inventory_cost_amount)
VALUES
    (20261010, 101, 11, 20, 1200000),
    (20261011, 101, 11, 17, 1020000);
~~~

**Expected meaning from the sample data:**

| Date | Sold (Units) | Sales Amount | Returned (Units) | Refund Amount | Closing Stock |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2026-10-10 | 3 | 300,000 | 0 | 0 | 20 |
| 2026-10-11 | 3 | 300,000 | 1 | 100,000 | 17 |

These are **derived results from the sample dataset above**, not benchmarks or real business figures. End-of-day inventory is an independent state measurement: you cannot derive Oct 11 stock solely from sales and returns, because stock movements also include purchase receipts, transfers, cycle counts, non-restockable returns, or other adjustments.

A simple grain check:

~~~sql
-- Transaction fact: 3 sales lines.
SELECT COUNT(*) AS sales_lines,
       SUM(quantity) AS sold_units,
       SUM(net_sales_amount) AS net_sales
FROM fact_sales_line;
-- 3 / 6 / 600000

-- Snapshot fact: one row per day/product/store.
SELECT snapshot_date_key, COUNT(*) AS snapshot_rows
FROM fact_inventory_daily
GROUP BY snapshot_date_key
ORDER BY snapshot_date_key;
-- 1 row per day in this example.
~~~

## 7. "Drill-Across": Aggregate Each Fact Before Combining

When two facts contain multiple rows for the same Product–Store–Date, **directly JOINing two fact tables** typically causes **fan-out**.

Suppose Oct 10 has three sales lines and two return events for the same product/store/day. A direct JOIN on those three keys produces **3 × 2 = 6 rows**. Summing sales or refunds afterward multiplies the measures.

Even when two facts share identical dimension keys, they hold **distinct event identities**. There is no semantic pairing saying "each sales line maps to each return line sharing the same Date, Product, and Store".

### 7.1. SQL Pattern That Easily Goes Wrong

~~~sql
-- INCORRECT DESIGN ILLUSTRATION for summary reporting:
SELECT s.sales_date_key, s.product_key, s.store_key,
       SUM(s.net_sales_amount) AS sales_amount,
       SUM(r.refund_amount) AS refund_amount
FROM fact_sales_line AS s
JOIN fact_return_line AS r
  ON r.return_date_key = s.sales_date_key
 AND r.product_key = s.product_key
 AND r.store_key = s.store_key
GROUP BY s.sales_date_key, s.product_key, s.store_key;
~~~

The query above both **multiplies rows** when multiple transactions exist on both sides and **drops** days with sales but zero returns or days with returns but zero new sales. Never patch this with **`SUM(DISTINCT amount)`**, as two independent events can legitimately share the exact same amount and must both be counted.

### 7.2. Correct SQL Pattern: Aggregate First, Join Later

Choose the report grain:

> **One row per recognition date × stable product code × store**.

Then aggregate each fact **independently** to that exact grain before `FULL OUTER JOIN`ing the results:

~~~sql
WITH sales AS (
    SELECT s.sales_date_key AS date_key,
           p.product_code,
           st.store_code,
           SUM(s.quantity) AS sold_units,
           SUM(s.net_sales_amount) AS sales_amount
    FROM fact_sales_line AS s
    JOIN dim_product AS p ON p.product_key = s.product_key
    JOIN dim_store AS st ON st.store_key = s.store_key
    WHERE s.sales_date_key BETWEEN 20261010 AND 20261011
    GROUP BY s.sales_date_key, p.product_code, st.store_code
),
returns AS (
    SELECT r.return_date_key AS date_key,
           p.product_code,
           st.store_code,
           SUM(r.returned_quantity) AS returned_units,
           SUM(r.refund_amount) AS returned_amount
    FROM fact_return_line AS r
    JOIN dim_product AS p ON p.product_key = r.product_key
    JOIN dim_store AS st ON st.store_key = r.store_key
    WHERE r.return_date_key BETWEEN 20261010 AND 20261011
    GROUP BY r.return_date_key, p.product_code, st.store_code
)
SELECT d.calendar_date,
       COALESCE(s.product_code, r.product_code) AS product_code,
       COALESCE(s.store_code, r.store_code) AS store_code,
       COALESCE(s.sold_units, 0) AS sold_units,
       COALESCE(s.sales_amount, 0) AS sales_amount,
       COALESCE(r.returned_units, 0) AS returned_units,
       COALESCE(r.returned_amount, 0) AS returned_amount
FROM sales AS s
FULL OUTER JOIN returns AS r
  ON r.date_key = s.date_key
 AND r.product_code = s.product_code
 AND r.store_code = s.store_code
JOIN dim_date AS d
  ON d.date_key = COALESCE(s.date_key, r.date_key)
ORDER BY d.calendar_date, product_code, store_code;
~~~

Clearly distinguish:

- **Sales date** is the sale date; **returns date** is the return date. This report compares **cashflow/units recognized on the same calendar day**, not the future return rate of goods sold that day.
- **`product_code`** serves as the grouping key to unify SCD2 versions of the same product. If product codes are unstable or only unique within a tenant, use a **stable, properly scoped business key**.
- **`store_code`** must carry identical meaning in both facts. Here Returns are attributed to the original selling store. If Returns log the processing branch instead, redefine the report or use a separate role-playing dimension.
- After pre-aggregation, each branch has **at most one row per grouping key tuple**; the JOIN cannot multiply detail transactions.

This pattern of aggregating first and joining on conformed dimensions is known as **drill-across** or **multipass SQL**. With multiple facts, first settle the **conformed dimensions** and common reporting grain.

### 7.3. What About "Net Sales After Refunds"?

An example definition is:

~~~text
net_cash_flow_for_period = sales_amount_for_period
                         - refund_amount_for_period
~~~

This represents sales recognized in the period minus refunds recognized **in the same period**. It does **not** necessarily equal accounting revenue under formal standards, which involve taxes, discounts, fees, return rights, cancellations, adjustments, and recognition policies.

Similarly:

~~~text
refund_amount_in_period / sales_amount_in_period
~~~

is a **ratio of period refunds to period sales**, not "the return rate of orders sold during the period". For a **sales-cohort return rate**, link return events back to **`original_sales_line_key`**, define the window from sale date, and specify the denominator.

## 8. Additive, Semi-Additive, and Non-Additive Measures

Classifying measure additivity is essential when combining multiple facts.

| Measure | Property | Appropriate Aggregation | Common Mistake |
| --- | --- | --- | --- |
| Sold quantity | Usually **additive** across date, product, store | `SUM` after filtering valid transactions | Re-counting cancelled lines or multiplying on JOIN |
| Net sales amount | Additive if **same currency and definition** | `SUM` | Summing VND and USD without conversion |
| Refund amount | Additive across valid return events in one currency | `SUM` | Subtracting the same event twice |
| Units on hand | **Semi-additive** | `SUM` across SKU/store at **one point in time** | Summing Oct 10 and Oct 11 to report "two-day stock" |
| Gross margin % | **Non-additive** | Computed from total profit over total revenue | Unweighted `AVG` of per-line margin percentages |
| Distinct order count | Usually non-additive | `COUNT DISTINCT` over the report scope | Summing order counts across products when one order contains multiple products |
| Conversion rate | Non-additive | Total conversions / total eligible sessions | Unweighted `AVG` of group rates |

### 8.1. Inventory Snapshots Must Not Be Summed Over Time

Business-incorrect if aiming for "period-end inventory":

~~~sql
-- Wrong if interpreted as period-end inventory across two days:
SELECT product_key, store_key, SUM(units_on_hand) AS inventory
FROM fact_inventory_daily
WHERE snapshot_date_key IN (20261010, 20261011)
GROUP BY product_key, store_key;
-- Yields 37 from 20 + 17, not the period-end stock balance.
~~~

To fetch the **latest snapshot on or before the reporting date**:

~~~sql
SELECT product_key, store_key, units_on_hand, snapshot_date_key
FROM (
    SELECT i.*,
           ROW_NUMBER() OVER (
               PARTITION BY i.product_key, i.store_key
               ORDER BY i.snapshot_date_key DESC
           ) AS rn
    FROM fact_inventory_daily AS i
    WHERE i.snapshot_date_key <= 20261011
) AS latest
WHERE rn = 1;
-- In this example: 17 units on Oct 11, 2026.
~~~

This is the simplified form when a Product/Store keeps the same surrogate key across both snapshots. If `DimProduct` is SCD2 and **`product_key` changes between days**, period-end stock for a business product must group or partition by the **stable `product_code`** after joining the dimension, alongside checking version-mapping rules. Never use `MAX(product_key)` assuming it represents the latest version.

To compute **daily average inventory**, define the date set, missing-snapshot handling, and weighting; taking `AVG` over present snapshots can skew results if missing days are non-random.

### 8.2. Summing vs. Counting vs. Taking the Final Value

An **order** can contain multiple products. `COUNT(*)` on `FactSalesLine` counts sales lines, whereas `COUNT(DISTINCT order_id)` counts **unique orders within the query scope** (assuming `order_id` is globally unique).

When slicing by category, an order containing products from two categories appears in **both groups**. Adding the two group order counts does not necessarily equal total company orders. Before publishing a dashboard, document whether each measure **is additive across the grouped dimensions**.

## 9. Conformed Dimensions and SCD Type 2 History

### 9.1. Business Keys and Surrogate Keys Play Different Roles

Suppose `P-001` initially belonged to Category "Headphones", and the company later reclassified it to "Personal Devices". To inspect classifications **as of the time of sale**, maintain multiple versions:

| product_key | product_code | category_name | valid_from | valid_to | is_current |
| ---: | --- | --- | --- | --- | --- |
| 101 | P-001 | Headphones | 2026-01-01 | 2026-10-31 | false |
| 102 | P-001 | Personal Devices | 2026-10-31 | NULL | true |

A sale on Oct 10 points to `product_key` **101**. A sale on Nov 05 points to `product_key` **102**, as the pipeline uses **business event time** to resolve the matching version.

Here effective intervals follow **`[valid_from, valid_to)`**: inclusive start, exclusive end. Adjacent rows touch at boundaries without overlapping.

**SCD2 does not automatically solve:**

- Two versions simultaneously valid at the same timestamp.
- Code `P-001` being recycled for a different product.
- Source systems sending a **late** change retroactively effective in the past.
- Queries needing **current category** instead of category at sale date.
- Returns referencing the same Product either as of return date or as of original sale date.

Those cases require explicit versioning rules and corresponding query patterns.

### 9.2. When to Use "Current" vs. "As-Of" Dimensions?

At least two valid questions exist:

1. "What was last year's revenue **by category at the time of sale**?" → group by the dimension version attached to the fact on the sale date.
2. "If we apply **today's category** to all products, how does last year's revenue redistribute?" → traverse from the business key to the current dimension version or current classification lookup table.

Do not mix both approaches on one dashboard and compare numbers without clear labels. When drilling across Sales and Returns, also define whether Returns receive the Product version **as of the original sale date** or **as of the return date**. In section 5's example, Returns used the **original sale's `product_key`** to match classification on the sale transaction—a business choice, not a universal law.

### 9.3. Enforcing SCD2 Consistency

Key assertions:

- Each `product_code` has **at most one** row with `is_current = TRUE`.
- Every row satisfies `valid_to > valid_from` or `valid_to IS NULL`.
- Effective intervals for the same `product_code` **never overlap**.
- Each fact event maps to **exactly one** valid dimension version for its designated timestamp.
- Late-arriving facts must not default to the current version when "as-of event" semantics are required.
- When classifications change retroactively, explicitly decide whether to **restate/backfill facts** or preserve previously published classifications.

In PostgreSQL, enforce non-overlapping intervals via exclusion constraints or transactional write logic. A unique partial index on current rows **is insufficient** to prevent overlaps across historical intervals.

## 10. Snowflake and Dimension History Challenges

In a star schema, an SCD2 `DimProduct` row captures point-in-time snapshots of `category_name` and `brand_name`. In a snowflake schema, Product references a separate Category table; if Category renames via Type 1, historical Products suddenly display **the new Category name** in past reports.

This can be valid if the business wants **current group definitions applied across all history**, but invalid if reports must preserve transaction-time classifications.

To preserve history in a snowflake schema, you can:

- Version **Category** separately and point Product to the **exact Category version**.
- Use time-bounded Product–Category membership relationships.
- Retain classification snapshots on `DimProduct` for "as-of" reporting.
- Provide separate views/marts for "current classification" vs. "historical classification".

Snowflaking does not eliminate history requirements; it usually makes **cross-dimension history rules more complex**. Thus, choosing star vs. snowflake should weigh how Categories, Brands, and store regions evolve—not just bytes saved on repeated strings.

## 11. Many-to-Many Dimensions and Bridge Tables

A Product may link to **multiple Campaigns** or multiple tags. Joining `FactSalesLine` to every Campaign of a Product repeats sales lines—a classic **bridge table** scenario.

Example bridge grain:

> One sales line allocated to one campaign with a business-approved weight.

~~~sql
CREATE TABLE dim_campaign (
    campaign_key BIGINT PRIMARY KEY,
    campaign_code TEXT NOT NULL UNIQUE,
    campaign_name TEXT NOT NULL
);

CREATE TABLE bridge_sales_campaign (
    sales_line_key BIGINT NOT NULL
        REFERENCES fact_sales_line(sales_line_key),
    campaign_key BIGINT NOT NULL
        REFERENCES dim_campaign(campaign_key),
    allocation_weight NUMERIC(8, 6) NOT NULL
        CHECK (allocation_weight >= 0 AND allocation_weight <= 1),
    PRIMARY KEY (sales_line_key, campaign_key)
);
~~~

If one sales line belongs to two Campaigns and the business allocates 60%/40%, the two bridge rows carry weights `0.6` and `0.4`. Allocated report query:

~~~sql
SELECT c.campaign_name,
       SUM(f.net_sales_amount * b.allocation_weight)
           AS allocated_sales
FROM fact_sales_line AS f
JOIN bridge_sales_campaign AS b
  ON b.sales_line_key = f.sales_line_key
JOIN dim_campaign AS c ON c.campaign_key = b.campaign_key
GROUP BY c.campaign_name;
~~~

**Limitation:** A row-level `CHECK` only ensures each weight falls in `[0,1]`; it **does not force weights for a `sales_line_key` to sum to 1**. A 100% allocation invariant is a cross-row constraint enforced in pipeline/transaction validation. Also decide how to handle sales lines **with no campaign**: allocate to Unknown/Unassigned or intentionally exclude them from Campaign reports.

If the requirement instead says "each Campaign receives credit for **100%** of influenced sales", do not fabricate artificial 60/40 weights. Campaign-level totals may then **intentionally** count the same transaction multiple times, meaning individual Campaign totals **cannot be summed** to equal total company revenue. Document metric semantics explicitly.

## 12. When Multiple Facts Have Different Dimension Sets

Not every fact can drill across at every grain.

Example:

~~~text
FactSalesLine       : Date, Product, Store, Customer
FactInventoryDaily  : Date, Product, Store
FactStoreTargetMonth: Month, Store
~~~

An "actual sales vs. target by **month, store**" report can:

1. Aggregate `FactSalesLine` from **day and sales line** up to **month–store**.
2. Keep `FactStoreTargetMonth` at **month–store** grain.
3. Join both results on `month_key, store_code`.
4. Compute `actual/target` after joining, with a defined policy when `target = 0`.

**Never** join monthly targets directly onto every sales line in the month and run `SUM(target_amount)`, as the target multiplies by the number of sales lines.

A report for "inventory by Customer" has no natural definition because inventory snapshots have no Customer dimension. If stock must be allocated to customers or segments, build an explicit **allocation or reservation rule**; never fabricate a `customer_key` on inventory facts just to join with sales.

### 12.1. One Generic Fact Table Full of NULLs?

A design like:

~~~text
FactEverything(
  event_type,
  sales_date_key,
  return_date_key,
  snapshot_date_key,
  product_key,
  store_key,
  customer_key,
  sales_amount,
  refund_amount,
  units_on_hand,
  ...
)
~~~

leads to rows filled with **sparse NULL fields**, mixed grains, and nonsensical `SUM`s. An inventory KPI requires "latest snapshot only", whereas sales requires "summing transactions"; merging them invites accidental mis-aggregation.

If a business genuinely has **one unified event type** with compatible grain and measures, a single fact makes sense. Never merge different-grain processes solely to reduce table count.

## 13. Common Errors When Joining Facts and Dimensions

### 13.1. Fan-Out from Non-Unique Dimension Join Keys

A fact has `product_code = P-001`. Joining directly to an SCD2 `DimProduct` on `product_code` without selecting a version turns one fact row into **two rows** when `P-001` has two dimension records.

The proper approach:

- Store the resolved version's **`product_key`** in the fact and join on that key.
- Or during source-to-version lookup, join on **`product_code` + effective interval** and verify each event matches exactly one version.

Never join an SCD2 table on business key and sum money without verifying match cardinality.

### 13.2. Fan-Out from Joining Multiple Facts at Detail Grain

Covered in section 7: Sales and Returns are independent event sets. Aggregate each to a common grain first before joining; never patch with `SUM(DISTINCT amount)`.

### 13.3. Counting Orders by Product

An Order with three lines across three categories appears in all three categories under `COUNT(DISTINCT order_id)` grouped by category. Category order counts **must not be summed** to derive total orders when sets overlap.

### 13.4. Inner JOIN Dropping Facts

When a fact references an unresolved `customer_key` whose dimension record has not yet arrived, an `INNER JOIN` causes revenue to "vanish" from reports. Use governed unknown members, late-arriving dimension handling, or controlled `LEFT JOIN`s; crucially, reconcile **raw fact totals vs. reported fact totals**.

### 13.5. Mixing Units, Currencies, and Timestamps

- Pieces cannot be summed with kilograms.
- VND revenue cannot be summed directly with USD.
- Sales by sale date do not equal Payments by collection date.
- End-of-day inventory cannot be summed across a month.
- Identical Category names in two taxonomies do not guarantee identical groups.

These are **semantic constraints** that PK/FK constraints alone cannot enforce.

## 14. ETL/ELT, Late-Arriving Data, and Reconciliation

Even a sound schema on paper fails if ingestion breaks grain or dimension versioning.

### 14.1. Typical Load Pipeline

~~~mermaid
flowchart LR
    O["Transactional Source"] --> S["Staging / Validation"]
    S --> D["Standardize DimDate / DimProduct / DimStore"]
    D --> M["Point-in-time surrogate key lookup"]
    S --> M
    M --> F["Load FactSales / FactReturns / Inventory"]
    F --> Q["Reconcile grain, amounts, keys, lag"]
    Q --> B["Mart / Dashboard"]
~~~

Invariants to codify as tests:

| Test | What Must Hold |
| --- | --- |
| Source uniqueness | One `source_sale_line_id` produces exactly one fact row at the defined grain |
| Dimension references | Every surrogate FK points to a valid dimension row or governed unknown member |
| SCD2 mapping | Each event resolves to exactly one dimension version valid at event time |
| Fact idempotency | A return event never loads into duplicate rows when a job retries |
| Monetary totals | Fact totals per reconciliation window match source totals after documented adjustments |
| Row counts | Valid source event count matches new fact rows, accounting for documented exclusions |
| Snapshots | Exactly one row per expected date–product–store; missing dates are flagged |
| Conformed dimensions | Product/Store codes and hierarchies remain uniform across all pipelines |
| Freshness | Data updates within the published latency SLA |
| History | Historical facts retain their proper as-of dimension versions |

### 14.2. Duplicate Ingestion and Late-Arriving Facts

If a sales message is replayed, the pipeline must never insert a second `sales_line_key` and **double revenue**. Enforce natural source keys, **idempotent upsert/merge**, or a deduplication table unique on `(source_system, source_event_id)`.

If `FactReturns` arrives days late, **`return_date_key`** must reflect the return event's business date—not silently shift to the ETL batch run date. Keep a separate **`load_timestamp`** if pipeline latency monitoring is needed.

If an SCD2 `Product` update arrives late with a past effective date, decide how to handle already-loaded facts:

- **Restatement:** remap affected facts to the corrected version if policy demands historical reporting reflect corrected metadata.
- **As-was:** preserve prior assignments to keep published reports immutable.
- **Dual mode:** expose both restated history and as-published history when auditing requires it.

Never automatically point all facts to the current `product_key`, as that erases historical meaning.

### 14.3. Schema Drift and Cross-Department Dimensions

Sales might call a Category "Accessories", while warehouse ops calls it "Add-on Equipment". Merging columns simply named `category_name` without a **canonical code catalog and mapping rules** fractures conformed dimensions.

Establish a **data contract** specifying codes, authoritative owners, definitions, value domains, history policies, update schedules, and exception handling. When upstream sources evolve, trace impacts on downstream facts, dashboards, and shared marts.

## 15. Choosing Star vs. Snowflake Based on Needs

| Criterion | Star | Snowflake | Fact Constellation |
| --- | --- | --- | --- |
| Primary focus | One fact with directly joined dimensions | One fact with further normalized dimensions | **Multiple facts** for distinct processes |
| Grain | Defined by the fact | Defined by the fact | **Each fact has its own grain** |
| JOIN hops for attributes | Usually few | Usually more | Depends on each fact's star/snowflake layout |
| Descriptive duplication | Higher within dimensions | Usually reduced across hierarchy tables | Conformed dimensions prevent fragmented taxonomies |
| Hierarchy history | Can store Type 2 snapshots directly with product | May require cross-dimension history tracking | Must unify history policies across facts |
| BI querying | Accessible for a single domain | Requires understanding hierarchies and JOINs | Requires grain-aware **drill-across** |
| Primary risks | Wide dimensions, taxonomy maintenance | Complex history/JOIN paths | Fact-join fanout, semantically mismatched metric comparisons |
| When to consider | Read-heavy, user-friendly marts | Complex shared taxonomies | Cross-process sales–returns–inventory–target analysis |

**Star and snowflake are dimension design styles**, while **constellation organizes multiple facts sharing dimensions**. They are not mutually exclusive. A galaxy model can use star dimensions for sales and snowflaked hierarchies for category analysis; the essential requirement remains **conformed dimensions and grain**.

### 15.1. Rely on Benchmarks, Not Diagram Shape

On columnar analytical warehouses, JOIN count alone does not tell the whole cost story. A snowflake with tiny dimension tables can run blazingly fast via broadcast/hash JOINs, whereas an overly wide star dimension with poor filtering can underperform.

When deciding, measure:

- Fact and dimension storage size; bytes scanned and rows passing through JOINs.
- Estimated vs. actual cardinality; check for unintended fan-out.
- p50/p95 query latency on critical dashboards.
- Ingestion/update cost for SCD2 and maintaining Category/Brand tables.
- Semantic model complexity and risk of users writing wrong JOINs.
- Access controls, sensitive attribute isolation, and retention policies.

Do not denormalize a dimension just to speed up one dashboard if doing so alters enterprise-wide KPI calculation rules.

## 16. Comparison with Transactional, Document, and Graph Models

Analytical modeling does not replace OLTP goals:

- **Relational OLTP:** optimizes transactional consistency and entity-level mutations. An Order has OrderLine, Payment, and ShippingAddress with PK/FK, state machines, and update constraints.
- **OLAP/star:** reorganizes events into facts and dimensions for multi-slice aggregation. Snapshots, SCDs, and summary tables match analytical objectives.
- **Document:** an Order and its lines can be embedded into one document for single-order reads; large-scale cross-order analytics still requires establishing grain, unnesting arrays, and producing clean events.
- **Graph:** multi-parent Product–Category hierarchies, User–Campaign graphs, or link networks fit nodes/edges; when aggregating money across multiple paths, deduplicate or allocate—never count traversals as revenue.

A document source might look like:

~~~json
{
  "orderId": 501,
  "soldAt": "2026-10-10T10:00:00+07:00",
  "storeCode": "HCM-01",
  "customerCode": "C-001",
  "lines": [
    {"lineNo": 1, "productCode": "P-001", "quantity": 2,
     "grossAmount": 200000, "discount": 0}
  ]
}
~~~

When transforming to a star schema, **each element of `lines`** becomes a `FactSalesLine` event at the defined grain; Product/Store/Customer fields map to conformed dimensions. Counting one document as one sales line distorts multi-line order quantities/products; copying order totals onto every line multiplies order revenue.

In multi-parent graph taxonomies, one Product can reach the same ancestor group via two paths. When using a graph to load or group dimensions, specify whether **group membership is by path existence or per path**. To report once per Product–group, deduplicate to a unique ancestor set; to allocate across branches, apply governed weights.

## 17. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Designing facts before writing grain | Inconsistent columns/keys, ambiguous KPIs | Write one sentence defining a fact row |
| Assuming facts sharing Date/Product/Store can join at detail grain | Fan-out and dropped one-sided groups | Aggregate each fact to a shared grain, then JOIN |
| Using `SUM(DISTINCT amount)` to block duplicates | Drops distinct events with identical amounts | Fix grain and JOIN paths |
| Summing inventory across multiple days | Fabricates meaningless stock totals | Take period-end snapshot or defined average |
| Summing order counts across Categories | Multi-category orders counted repeatedly | `COUNT DISTINCT` at proper scope and check additivity |
| Joining SCD2 on `product_code` without selecting version | Multiplies facts across dimension versions | FK to `product_key` or proper as-of lookup |
| Treating matching column names as proof of conformed dimensions | Mismatched SKUs, tenants, hierarchies, or validity | Standardize codes and semantic contracts |
| Dividing period returns by same-day sales as "cohort return rate" | Wrong cohort and denominator | Join back to original sale and define cohort |
| Putting every event type into `FactEverything` | Mixed grains, sparse NULLs, invalid SUMs | Split facts by process and grain |
| Picking Snowflake solely for higher normal form | Extra JOINs and complex history without benefit | Measure workload and governance overhead |
| Dropping facts because dimensions arrived late | Missing revenue in reports | Unknown member / late dimension with reconciliation |
| Failing to block duplicate loads on pipeline retries | Revenue multiplies with each retry | Unique event IDs, idempotency, and tests |
| Using current Product price to compute past revenue | Rewrites historical revenue | Capture transaction-time price on the fact |
| Omitting currency/timezone specifications | Invalid sums and comparisons | Enforce explicit currency, timezone, and FX rules |
| Storing Category as Type 1 while demanding as-of history | Past reports get reclassified | SCD2/temporal relations or snapshots |
| Counting many-to-many campaign revenue without allocation | Multiplies revenue | Bridge table, weights, or non-additive KPI label |

## 18. Guided Case Exercises

### Exercise 1. Finding Fact Grain

**Prompt:** Order `501` has three lines. A fact table keys on `order_id` and `product_key`, storing `quantity`, `unit_price`, and `discount_amount`. Is the grain guaranteed to be one sales line?

**Hint:** **Not necessarily.** One Product can appear multiple times in the same Order across promotions, warehouses, or fulfillment batches, so `(order_id, product_key)` is not guaranteed unique per line. You need source line identity like **`(order_id, line_no)`** or `source_sales_line_id` and rules for cancellations/adjustments. Only finalize keys and measures once grain is clear.

### Exercise 2. Choosing Star vs. Snowflake

**Prompt:** 99% of reports need revenue by Category and Brand. `DimProduct` has several million SCD2 rows, and Category structure evolves historically. Should you automatically switch to Snowflake because Category repeats heavily?

**Hint:** Not automatically. Evaluate storage footprint, JOIN overhead, taxonomy churn rate, historical classification policy, and Category sharing. A Star storing versioned classification attributes handles as-of queries cleanly; Snowflake curbs duplication at the cost of cross-table history rules. Benchmark on representative queries, engine, and data.

### Exercise 3. Why Not Join Facts Directly?

**Prompt:** One day has 5 sales lines and 3 return lines for the same Product/Store. Joining directly on Date–Product–Store yields at most how many pairs if all rows match?

**Hint:** **5 × 3 = 15 rows**. Summing sales or refunds on that output duplicates data. Aggregate Sales and Returns separately to one row per Date–Product–Store, then join the aggregated results.

### Exercise 4. Period-End Inventory

**Prompt:** A store records closing stock of 20, 17, and 24 units across three days. What is period-end stock?

**Hint:** Assuming all three snapshots belong to the same Product/Store and day three is period-end, period-end stock is **24**, not 61. If reporting three-day average stock with complete snapshots, use `(20 + 17 + 24)/3` while documenting the formula and missing-day handling.

### Exercise 5. Using Conformed Dimensions

**Prompt:** Sales uses `product_id = 10` for a single SKU; Warehouse uses `product_id = 10` for a product family spanning multiple SKUs. Both name the column `product_id`. Can you drill across immediately?

**Hint:** No. The two fields have **different semantic grains**. Build a SKU–ProductGroup mapping, agree on a shared grain, and align aggregation/Product dimensions before comparing.

### Exercise 6. Type 2 and Wrong JOINs

**Prompt:** Product `P-001` has two SCD2 `DimProduct` rows: one for Jan–Oct and one from Nov onward. A September fact points to the September `product_key`. Why can joining on `product_code` double revenue?

**Hint:** Because `product_code` matches **both versions**, expanding one fact row into two rows. Join on the surrogate `product_key` stored in the fact, or apply effective-date predicates during version resolution.

### Exercise 7. Return Rate

**Prompt:** October shows 100 million in sales and 8 million in refunds. Can you report "8% of October sales were returned"?

**Hint:** No. `8/100` is the **ratio of refunds recorded in October to sales recorded in October**, not necessarily for the same orders. For an October sales-cohort return rate, trace `original_sales_line/order`, choose the unit (line/unit/order), set the return window, and define the denominator.

### Exercise 8. Monthly Targets vs. Sales Lines

**Prompt:** A store has a monthly target of 100 million, and the month contains 1,000 sales lines. Joining the target onto every sales line and running `SUM(target_amount)` returns what?

**Hint:** Repeating 100 million across 1,000 rows yields **100 billion**, which is wrong. Aggregate sales up to month–store first, then join to the target fact at its proper grain.

### Exercise 9. Campaigns and Bridge Tables

**Prompt:** A 100,000 VND sales line belongs to Campaigns A and B. If reports require allocated totals to sum strictly to 100,000, how should the bridge represent this?

**Hint:** For example, A `weight = 0.6` and B `weight = 0.4`; `SUM(amount × weight)` yields 60,000 and 40,000. Validate that weights sum to 1 across **all rows sharing `sales_line_key`**; a row-level `CHECK` only constrains values to `[0,1]`.

### Exercise 10. Late-Arriving Transactions

**Prompt:** On Nov 15, the pipeline receives a sales line with `event_time` Oct 30; the Product changed Category on Nov 01. Which dimension version should the fact point to?

**Hint:** If reporting **by classification at time of sale**, look up the version effective on Oct 30, not the version current on load date. If reporting policy uses current Category, expose an explicit current-mapping view; never mix both modes silently.

### Exercise 11. One Order with Multiple Products

**Prompt:** `COUNT(DISTINCT order_id)` across three Categories yields 30, 40, and 50. Can you state total orders = 120?

**Hint:** Not if one Order contains Products from multiple Categories. The same Order can appear in multiple groups, making the sum of group counts exceed total distinct Orders overall. Define a primary-category assignment rule if each order must belong to strictly one group.

### Exercise 12. Preventing Duplicate Snapshots

**Prompt:** `FactInventoryDaily` has grain date–product–store. A retry job emits two records with identical keys but differing stock quantities. What should the system do?

**Hint:** `PK/UNIQUE` on `(snapshot_date_key, product_key, store_key)` catches duplicates. The pipeline must resolve which record is authoritative (via source version, timestamp, or reconciliation rules), execute a controlled upsert, and log anomalies—never sum two snapshots.

## 19. Analytical Model Acceptance Checklist

Before signing off on a schema or dashboard, verify:

1. **Grain:** every fact has an unambiguous definition statement; source keys prevent duplicate loads.
2. **Conformed dimensions:** drill-across uses unified identifiers, classifications, history rules, units, and tenant scopes.
3. **Measures:** additive, semi-additive, and non-additive properties are classified; valid aggregations are documented.
4. **Fact constellation:** independent facts are never joined at detail grain; each aggregates to the shared reporting grain first.
5. **Date roles:** sale date, return date, snapshot date, and reporting date are clearly distinguished.
6. **SCD:** dimension versions resolve accurately by event timestamp; overlapping intervals and late updates are handled.
7. **Reconciliation:** fact counts, quantities, monetary amounts, and unknown groups match upstream sources per policy.
8. **Multi-valued attributes:** many-to-many Campaigns/Categories use bridges and deduplication/allocation rules to avoid inflation.
9. **Execution:** tested on realistic volume and skew, verifying query plans, indexes/partitions/clustering, load cost, and history.
10. **Interpretation:** dashboards state grain, currency, return/cancellation treatment, freshness lag, and Category history mode.

## 20. Key Takeaways

- **Star schema:** one central fact joined directly to flattened dimensions; generally intuitive and minimizes descriptive JOINs.
- **Snowflake schema:** one or more dimensions split into normalized hierarchy tiers; reduces text duplication at the cost of extra JOINs and history complexity.
- **Fact constellation:** multiple independent facts at **different grains** sharing **conformed dimensions** for cross-process analysis.
- **Grain dictates math.** Never sum inventory across days, sum ratios/COUNT DISTINCT across overlapping scopes, or multiply revenue via many-to-many joins.
- **Drill-across requires multipass SQL:** aggregate each fact to common dimensions and reporting grain, **then** JOIN the results.
- **Conformed means more than matching column names:** standardize identifiers, history policies, tenant scopes, hierarchies, and role semantics.
- **SCD2 and late-arriving data** span the entire source–ETL–fact–dimension pipeline, not merely adding `valid_from`/`valid_to` columns.

A strong analytical model does more than draw three neat diagrams. It lets readers define **exactly what each row represents, at what level tables combine, and when a metric can be summed**, while proving results against source data and business rules.
