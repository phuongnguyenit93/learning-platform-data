# GROUP BY and Choosing the Aggregation Grain in PostgreSQL

In real-world applications, data is often stored at a very detailed level: **one row per order**, **one row per order line item**, **one row per payment**, or **one row per event**. Yet users ask different questions: "What is monthly revenue?", "How many orders does each store have?", "How many times did each customer buy?", or "How does the system-wide total compare to regional totals?"

In PostgreSQL, **`GROUP BY`** gathers rows sharing the same grouping key values into groups. Aggregate functions such as `COUNT`, `SUM`, `AVG`, `MIN`, and `MAX` are evaluated **for each group**. However, writing valid `GROUP BY` syntax is only part of the problem. What determines whether a report is **right or wrong** is choosing the **aggregation grain** (i.e., what each output row represents) that matches the business question.

For example, from an orders table:

- `GROUP BY tenant_id` → **one row per tenant**.
- `GROUP BY tenant_id, region` → **one row per tenant–region pair**.
- `GROUP BY date_trunc('month', created_at)` → **one row per month** according to the chosen time zone convention.
- Without `GROUP BY`, using only `SUM(...)` → **one overall total**.
- `GROUP BY ROLLUP(...)` or `GROUPING SETS(...)` → **multiple aggregation levels in one result**, such as regional details, tenant subtotals, and a system-wide grand total.

If the wrong grain is chosen, the query may still run and produce plausible-looking numbers, yet **miscount orders**, **double-count revenue after a JOIN**, **skew averages**, or **mix data across tenants**.

This lesson belongs to the **Data Aggregation** chapter of the *Database Engine Relational PostgreSQL* module. After completing it, you will be able to explain `GROUP BY` semantics, choose grouping keys based on the question, use `HAVING`/`FILTER`, handle `NULL`s, aggregate by date/month, distinguish `GROUPING SETS`/`ROLLUP`/`CUBE`, avoid JOIN row-multiplication bugs, and evaluate how PostgreSQL executes aggregate queries.

> **Scope:** Examples use modern PostgreSQL, a dedicated `agg_lab` schema, and synthetic data. The table creation and seed statements are for hands-on practice on a test database. Do not treat table names or figures in this lesson as production data.

## 1. What Is Aggregation Grain (*Grain*)?

Before writing SQL, finish this sentence:

> "**Each row in the result represents ...**"

For example:

| Question | One Result Row Represents | Suggested Grouping Key |
|---|---|---|
| How many paid orders exist across the system? | The entire qualifying set of orders | No `GROUP BY` needed |
| How many paid orders does each tenant have? | One tenant | `tenant_id` |
| Revenue by region within each tenant? | One tenant–region pair | `tenant_id, region` |
| Monthly revenue per tenant? | One tenant–month pair | `tenant_id, month_bucket` |
| Paying customers by channel per month? | One month–channel pair | `month_bucket, channel` |
| A report with details, subtotals, and grand total? | Multiple clearly labeled levels | `GROUPING SETS` or `ROLLUP` |

**Source data grain** differs from **result grain**. If the source data already has one row per **line item**, `COUNT(*)` after a `JOIN` is no longer the number of orders. This is a very common cause of inaccurate reports.

### 1.1. Mental Model: From Detail Rows to Groups

```text
Raw data: each row = one order
    |
    | WHERE status = 'paid'
    v
Keep only paid orders
    |
    | GROUP BY tenant_id, region
    v
Each group = one tenant / region pair
    |
    | COUNT(*), SUM(total_amount)
    v
Each result row = order count + revenue for that group
    |
    | HAVING ..., ORDER BY ...
    v
Report delivered to the user
```

`GROUP BY` does not inherently know which orders are "completed" or which amount column counts as "revenue." Those rules must be expressed in `WHERE`, aggregate functions, `FILTER` clauses, or the data model.

### 1.2. Don't Start with the SELECT Column List

An error-prone habit is listing every seemingly useful column in `SELECT` and then "adding all of them to `GROUP BY` until the SQL stops throwing errors." If the question calls for **one row per tenant**, adding `order_id` to `GROUP BY` turns each order into its own group, preventing the expected tenant-level aggregation.

Instead:

1. Identify the **entity being counted/summed** (orders, line items, customers, payment transactions).
2. Identify the **filters** (paid only, time range, tenant, access control).
3. Identify the **grouping keys** (tenant, region, month, channel).
4. Choose the appropriate **aggregate function** for each metric.
5. Check whether any `JOIN` changes the grain of the input data.

## 2. Preparing the Practice Dataset

We will create an `orders` table where **each row is one order**. Each order has a tenant, customer, timestamp, region (possibly unknown), sales channel, status, and total amount. Then we will add `order_items` to illustrate JOIN risks.

### 2.1. Creating the Orders Table

```sql
CREATE SCHEMA IF NOT EXISTS agg_lab;

CREATE TABLE agg_lab.orders (
    order_id BIGINT PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    customer_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    region TEXT,
    channel TEXT NOT NULL
        CHECK (channel IN ('web', 'store')),
    status TEXT NOT NULL
        CHECK (status IN ('paid', 'pending', 'cancelled')),
    total_amount NUMERIC(12, 2) NOT NULL
        CHECK (total_amount >= 0)
);
```

`NUMERIC` is chosen for the sample amounts to avoid floating-point rounding errors in ordinary addition. In a real system, you also need to align on currency units, taxes, discounts, shipping fees, and the exact definition of "revenue."

### 2.2. Inserting Data

```sql
INSERT INTO agg_lab.orders
    (order_id, tenant_id, customer_id, created_at,
     region, channel, status, total_amount)
VALUES
    ( 1, 10, 101, '2026-01-05 10:00:00+07', 'north', 'web',   'paid',      300),
    ( 2, 10, 102, '2026-01-07 11:00:00+07', 'north', 'store', 'paid',      180),
    ( 3, 10, 101, '2026-01-12 12:00:00+07', 'south', 'web',   'pending',   240),
    ( 4, 10, 103, '2026-02-02 08:30:00+07', 'south', 'web',   'paid',      120),
    ( 5, 10, 104, '2026-02-07 14:00:00+07', 'north', 'web',   'cancelled', 500),
    ( 6, 10, 102, '2026-02-15 15:00:00+07', NULL,    'store', 'paid',       90),
    ( 7, 10, 101, '2026-03-05 09:00:00+07', 'south', 'store', 'paid',      250),
    ( 8, 20, 201, '2026-01-08 10:00:00+07', 'north', 'web',   'paid',      400),
    ( 9, 20, 202, '2026-01-11 16:00:00+07', 'south', 'store', 'paid',      160),
    (10, 20, 201, '2026-02-01 09:00:00+07', 'south', 'web',   'pending',   350),
    (11, 20, 203, '2026-02-20 17:00:00+07', NULL,    'web',   'paid',       80),
    (12, 20, 201, '2026-03-06 13:00:00+07', 'north', 'store', 'paid',      230);
```

In total there are **12 orders**: **9 `paid`**, **2 `pending`**, and **1 `cancelled`**. When this lesson refers to "paid order revenue," we use `status = 'paid'` and sum `total_amount` for those rows. This is a lab convention, not an accounting definition for all businesses.

The paid orders:

| tenant_id | order_id | region | total_amount |
|---:|---:|---|---:|
| 10 | 1 | north | 300 |
| 10 | 2 | north | 180 |
| 10 | 4 | south | 120 |
| 10 | 6 | `NULL` | 90 |
| 10 | 7 | south | 250 |
| 20 | 8 | north | 400 |
| 20 | 9 | south | 160 |
| 20 | 11 | `NULL` | 80 |
| 20 | 12 | north | 230 |

Note that the timestamps include a `+07` offset. A `TIMESTAMPTZ` value represents an exact point in time; when grouping by local day or month, you must choose the business time zone consistently.

### 2.3. One-to-Many Detail Table for Later Examples

```sql
CREATE TABLE agg_lab.order_items (
    item_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL
        REFERENCES agg_lab.orders(order_id),
    category TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    line_total NUMERIC(12, 2) NOT NULL
        CHECK (line_total >= 0)
);

INSERT INTO agg_lab.order_items
    (item_id, order_id, category, quantity, line_total)
VALUES
    ( 1,  1, 'device',  1, 200),
    ( 2,  1, 'addon',   1, 100),
    ( 3,  2, 'device',  1, 180),
    ( 4,  4, 'addon',   2, 120),
    ( 5,  6, 'service', 1,  90),
    ( 6,  7, 'device',  1, 200),
    ( 7,  7, 'addon',   1,  50),
    ( 8,  8, 'device',  2, 360),
    ( 9,  8, 'service', 1,  40),
    (10,  9, 'addon',   2, 160),
    (11, 11, 'service', 1,  80),
    (12, 12, 'device',  1, 150),
    (13, 12, 'addon',   2,  80);
```

With this data:

- `orders` has **one row per order**.
- `order_items` has **one row per line item**.
- An order can have **multiple line items**: `order_id=1` has two lines, and `order_id=8` has two lines.
- The `line_total` values of each `paid` order in the lab add up to `orders.total_amount`.
- `pending`/`cancelled` orders in the example have no item rows; this is for illustration, not a mandatory rule of real sales databases.

To inspect the data without relying on memory:

```sql
SELECT status, COUNT(*) AS so_don
FROM agg_lab.orders
GROUP BY status
ORDER BY status;
```

## 3. Simple GROUP BY: One Group per Value

Let's answer: **How many paid orders does each tenant have, and what is their total amount?**

```sql
SELECT
    tenant_id,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id
ORDER BY tenant_id;
```

Expected result:

| tenant_id | paid_orders | paid_amount |
|---:|---:|---:|
| 10 | 5 | 940 |
| 20 | 4 | 870 |

Breakdown of each clause:

- `FROM agg_lab.orders`: selects the source data at one-row-per-order grain.
- `WHERE status = 'paid'`: keeps only paid orders.
- `GROUP BY tenant_id`: forms two groups, tenant 10 and tenant 20.
- `COUNT(*)`: counts the number of **rows** in each group, which here equals the number of orders.
- `SUM(total_amount)`: sums the amounts of orders in each group.
- `ORDER BY tenant_id`: orders the output. `GROUP BY` **does not guarantee output order**.

This is a correct example because the business question, source grain, filter, and grouping key all align.

### 3.1. Multi-Column GROUP BY: Finer Granularity

If you want **one row per tenant and per region**:

```sql
SELECT
    tenant_id,
    region,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id, region
ORDER BY tenant_id, region NULLS LAST;
```

Result:

| tenant_id | region | paid_orders | paid_amount |
|---:|---|---:|---:|
| 10 | north | 2 | 480 |
| 10 | south | 2 | 370 |
| 10 | `NULL` | 1 | 90 |
| 20 | north | 2 | 630 |
| 20 | south | 1 | 160 |
| 20 | `NULL` | 1 | 80 |

Adding `region` to the grouping key makes the output **more granular**, not "more accurate" in every scenario. When a report requires one row per tenant, `region` should not be in the final `GROUP BY`.

### 3.2. Changing the Grain Changes the Output Row Count

With the nine `paid` orders in the lab:

| Query Pattern | Result Grain | Expected Row Count |
|---|---|---:|
| `SUM(total_amount)` | All paid orders | 1 |
| `GROUP BY tenant_id` | One tenant | 2 |
| `GROUP BY region` | One region, including the NULL group | 3 |
| `GROUP BY tenant_id, region` | One tenant–region pair | 6 |
| `GROUP BY order_id` | One order | 9 |

If you asked for "totals per tenant" and the query returns nine rows, a detail key such as `order_id` was likely included in `GROUP BY`.

## 4. SELECT Rules, GROUP BY, and Unaggregated Column Errors

A standard aggregate query may select:

1. **Grouping expressions** defined in `GROUP BY`.
2. Results of **aggregate functions** such as `COUNT(*)`, `SUM(total_amount)`.
3. Certain other expressions that PostgreSQL can prove are functionally dependent on the grouping keys, subject to supported limits.

Valid example:

```sql
SELECT tenant_id, SUM(total_amount)
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id;
```

Grain error example:

```sql
-- Invalid: region can have multiple values within the same tenant.
-- SELECT tenant_id, region, SUM(total_amount)
-- FROM agg_lab.orders
-- GROUP BY tenant_id;
```

PostgreSQL typically reports an error like:

```text
column "orders.region" must appear in the GROUP BY clause
or be used in an aggregate function
```

The corresponding SQLSTATE is usually `42803` (`grouping_error`).

**Do not fix this error by blindly adding `region` to `GROUP BY`** if the original requirement is still one row per tenant. Decide instead:

- If **tenant–region detail** is needed, group by both.
- If **one row per tenant** is needed, remove `region` from SELECT, or apply a meaningful aggregate over region values, such as `COUNT(DISTINCT region)`.
- If only one representative record is needed, define an explicit selection rule rather than using `MIN(region)` arbitrarily.

### 4.1. GROUP BY an Expression

You do not have to group by raw columns only. You can group by expressions:

```sql
SELECT
    lower(channel) AS channel_key,
    COUNT(*) AS order_count
FROM agg_lab.orders
GROUP BY lower(channel)
ORDER BY channel_key;
```

In the lab, `channel` already contains normalized `web`/`store` values, but real-world cases might use `lower`, `date_trunc`, `COALESCE`, or a bucketing expression.

**Note:** Two distinct raw values can collapse into the **same grouping key** after applying an expression. Define your normalization policy up front rather than letting an expression accidentally merge semantically distinct groups.

### 4.2. GROUP BY Column Position in SELECT

PostgreSQL accepts positional syntax:

```sql
SELECT tenant_id, region, SUM(total_amount)
FROM agg_lab.orders
GROUP BY 1, 2
ORDER BY 1, 2;
```

Here `1` and `2` refer to the first and second expressions in the SELECT list. Although concise, this style can be brittle: adding or reordering SELECT columns can silently alter the GROUP BY semantics.

In documentation and critical queries, writing `GROUP BY tenant_id, region` explicitly is usually clearer.

### 4.3. Functional Dependency on a PRIMARY KEY

PostgreSQL allows selecting non-grouped columns when the grouping columns include the **table's primary key** and the functional dependency is recognized:

```sql
SELECT
    order_id,
    customer_id,
    total_amount
FROM agg_lab.orders
GROUP BY order_id;
```

Because `order_id` is the `PRIMARY KEY` of `orders`, each group contains at most one order, so `customer_id` and `total_amount` are uniquely determined by that key. However, this query does **not actually aggregate multiple orders**, because each order forms its own group.

Do not assume this rule extends arbitrarily to every unique index, JOIN, or expression that humans "know is unique." PostgreSQL has specific rules for recognizing functional dependencies; for summary reports, use a clear-grain `GROUP BY` and explicit aggregate functions.

## 5. Logical Order: WHERE, GROUP BY, HAVING, SELECT, ORDER BY

To avoid confusing row filters with group filters, visualize the logical flow:

```text
FROM / JOIN
    |
    v
WHERE                -- filter input rows
    |
    v
GROUP BY             -- form groups by key
    |
    v
Aggregate functions  -- COUNT, SUM, AVG... per group
    |
    v
HAVING               -- filter entire groups after aggregation
    |
    v
SELECT               -- format output expressions
    |
    v
ORDER BY             -- sort returned results
    |
    v
LIMIT / OFFSET       -- limit and paginate results
```

This is a **logical model for understanding SQL**, not a claim that PostgreSQL's physical executor always runs each step strictly in that sequence. The optimizer may push predicates, choose `HashAggregate`/`GroupAggregate`, and vary execution strategies while preserving query semantics.

### 5.1. WHERE Filters Rows Before Grouping

```sql
SELECT tenant_id, SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id;
```

`pending` and `cancelled` orders **never enter the input** of the aggregation.

### 5.2. HAVING Filters Groups Based on Aggregate Results

To find tenants whose **paid revenue is at least 900**:

```sql
SELECT
    tenant_id,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id
HAVING SUM(total_amount) >= 900
ORDER BY tenant_id;
```

The result contains only **tenant 10** with 940, since tenant 20 has 870.

Do not write:

```sql
-- Wrong clause: WHERE cannot filter on the SUM of an entire group.
-- SELECT tenant_id, SUM(total_amount)
-- FROM agg_lab.orders
-- WHERE SUM(total_amount) >= 900
-- GROUP BY tenant_id;
```

### 5.3. Placing a Condition in WHERE vs. HAVING

The following two queries are **not equivalent**:

```sql
-- A: Exclude small orders before summing.
SELECT tenant_id, SUM(total_amount) AS amount_large_orders
FROM agg_lab.orders
WHERE status = 'paid'
  AND total_amount >= 200
GROUP BY tenant_id;

-- B: Sum all paid orders, then keep tenants whose total >= 200.
SELECT tenant_id, SUM(total_amount) AS total_paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id
HAVING SUM(total_amount) >= 200;
```

In A, `total_amount >= 200` is a **per-order condition**. In B, `SUM(total_amount) >= 200` is a **per-tenant total condition**.

Some conditions involving only grouping keys produce the same result in either `WHERE` or `HAVING`; generally, put row-filtering conditions in `WHERE` to state intent clearly and reduce the volume of data aggregated.

### 5.4. ORDER BY Is a Separate Step

`GROUP BY tenant_id` does not guarantee tenants are returned in ascending order. If you want revenue descending and deterministic tie-breaking:

```sql
SELECT tenant_id, SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id
ORDER BY paid_amount DESC, tenant_id ASC;
```

PostgreSQL lets you reference the `paid_amount` alias in `ORDER BY`. When groups tie on total amount, `tenant_id` acts as a tie-breaker to keep ordering deterministic for the same dataset.

## 6. COUNT, SUM, AVG, MIN, MAX: Right Function, Right Denominator

### 6.1. COUNT(*) and COUNT(column) Are Not the Same

`COUNT(*)` counts **rows**. `COUNT(expr)` counts **rows where `expr` is not NULL**.

In the lab, `region` has two paid orders with an unknown region:

```sql
SELECT
    COUNT(*) AS so_don_paid,
    COUNT(region) AS so_don_co_vung,
    COUNT(*) - COUNT(region) AS so_don_chua_co_vung
FROM agg_lab.orders
WHERE status = 'paid';
```

Result:

| so_don_paid | so_don_co_vung | so_don_chua_co_vung |
|---:|---:|---:|
| 9 | 7 | 2 |

If the goal is counting orders, never use `COUNT(region)` when `region` allows NULL. It skips the two orders without a region and returns the wrong count.

### 6.2. COUNT(DISTINCT): Counting Distinct Values

In tenant 10, paid orders belong to customers 101, 102, 103, 102, and 101. Thus there are 5 orders, but only 3 distinct paying customers.

```sql
SELECT
    tenant_id,
    COUNT(*) AS paid_orders,
    COUNT(DISTINCT customer_id) AS paying_customers
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id
ORDER BY tenant_id;
```

Result:

| tenant_id | paid_orders | paying_customers |
|---:|---:|---:|
| 10 | 5 | 3 |
| 20 | 4 | 3 |

`COUNT(DISTINCT customer_id)` avoids double-counting the same customer within **a single group**, but if the same customer appears in multiple groups, summing per-group distinct counts can **double-count customers**.

### 6.3. SUM and AVG Ignore NULL, but Have Different Denominators

`SUM(expr)` adds non-NULL values, while `AVG(expr)` averages **non-NULL** values. In the lab table, `total_amount` is `NOT NULL`, so `AVG(total_amount)` equals total amount divided by the group's order count.

```sql
SELECT
    tenant_id,
    SUM(total_amount) AS paid_amount,
    COUNT(*) AS paid_orders,
    ROUND(AVG(total_amount), 2) AS avg_order_value
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id
ORDER BY tenant_id;
```

Result:

| tenant_id | paid_amount | paid_orders | avg_order_value |
|---:|---:|---:|---:|
| 10 | 940 | 5 | 188.00 |
| 20 | 870 | 4 | 217.50 |

For a nullable column, `AVG(column)` **does not divide by `COUNT(*)`**—it divides by `COUNT(column)`. If business logic treats missing values as 0, express that policy explicitly with `COALESCE`, while recognizing that substituting 0 changes the statistical meaning.

### 6.4. MIN and MAX

```sql
SELECT
    tenant_id,
    MIN(total_amount) AS min_paid_order,
    MAX(total_amount) AS max_paid_order,
    MIN(created_at) AS first_paid_at,
    MAX(created_at) AS last_paid_at
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id
ORDER BY tenant_id;
```

`MIN`/`MAX` find extrema based on the expression's data type and comparison rules—they do not "return the whole row" holding that extremum. For example, `MAX(total_amount)` returns the highest amount, not the `order_id` of the largest order. If you need the full row with the maximum value, use a suitable strategy such as `ORDER BY ... LIMIT 1`, `DISTINCT ON`, or a window function.

### 6.5. Aggregating Without GROUP BY: One Overall Row

```sql
SELECT
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount,
    ROUND(AVG(total_amount), 2) AS avg_paid_order
FROM agg_lab.orders
WHERE status = 'paid';
```

Result:

| paid_orders | paid_amount | avg_paid_order |
|---:|---:|---:|
| 9 | 1810 | 201.11 |

This is **a single global group**, not "all rows share the same tenant." When the goal is a system-wide total, there is no need to `GROUP BY tenant_id` and sum manually when a direct aggregate expresses the intent clearly.

### 6.6. When No Rows Match

```sql
SELECT
    COUNT(*) AS row_count,
    SUM(total_amount) AS total,
    AVG(total_amount) AS average
FROM agg_lab.orders
WHERE status = 'paid'
  AND tenant_id = -1;
```

The result is **one row** with `row_count=0`, while `SUM` and `AVG` are `NULL` (since there are no values to sum or average).

If you add `GROUP BY tenant_id` to the same filter, the query usually returns **zero rows** because no groups exist. Distinguish:

- **No GROUP BY:** one global group even when the input is empty; `COUNT(*) = 0`.
- **With GROUP BY on a column key:** zero groups when no rows match.

If the API truly wants an amount of 0 instead of `NULL`:

```sql
SELECT COALESCE(SUM(total_amount), 0) AS total
FROM agg_lab.orders
WHERE tenant_id = -1;
```

This `COALESCE` is a presentation/business decision; **never replace `NULL` with 0 blindly** on metrics where "no data" means something different from zero.

## 7. GROUP BY and NULL: The "Unknown" Group

In PostgreSQL, when grouping on a nullable column, rows with `NULL` in the grouping key are **gathered into a single group**.

```sql
SELECT
    region,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY region
ORDER BY region NULLS LAST;
```

Result:

| region | paid_orders | paid_amount |
|---|---:|---:|
| north | 4 | 1110 |
| south | 3 | 530 |
| `NULL` | 2 | 170 |

Distinguish this from `NULL = NULL` in ordinary expressions: `NULL = NULL` evaluates to unknown, whereas **`GROUP BY` places NULL values of the same key into one group** per SQL grouping semantics.

### 7.1. Relabeling NULL for Display

```sql
SELECT
    COALESCE(region, '(unspecified)') AS region_label,
    COUNT(*) AS paid_orders
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY COALESCE(region, '(unspecified)')
ORDER BY region_label;
```

This is reasonable if you want readers to see a clearer label. However, if the data contains a **real region value** equal to the literal string `'(unspecified)'`, `COALESCE` will merge it with the `NULL` group.

When labels might collide, keep raw `region` as the grouping key and relabel only at display time:

```sql
SELECT
    COALESCE(region, '(unspecified)') AS region_label,
    COUNT(*) AS paid_orders
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY region
ORDER BY region NULLS LAST;
```

Two distinct `region` groups remain separate in `GROUP BY region`, even if their display labels match. Applications may also want to return the raw key or a distinguishing code in the API.

### 7.2. Do Not Use COUNT(region) to Count Orders in the NULL Group

```sql
SELECT
    region,
    COUNT(*) AS rows_in_group,
    COUNT(region) AS nonnull_region_values
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY region
ORDER BY region NULLS LAST;
```

In the `region=NULL` group, `COUNT(*)=2` whereas `COUNT(region)=0`. When you want order counts per region, `COUNT(*)` matches the one-row-per-order grain.

### 7.3. NULL in GROUPING SETS Has Another Meaning

When building subtotal/grand total reports using `ROLLUP` or `GROUPING SETS`, PostgreSQL also places `NULL` in columns that **do not participate in that aggregation level**. Then a `NULL` cell can mean either:

1. The region is genuinely **unspecified** in the data.
2. The region was **rolled up** to compute a tenant subtotal.

These two cases must be distinguished using the **`GROUPING()`** function, covered later. Using `COALESCE(region,'All')` alone cannot tell them apart.

## 8. FILTER: Multiple Conditional Metrics in the Same Group

Suppose a report needs **one row per tenant** with order counts by status and the amount of paid orders.

A readable pattern in PostgreSQL is attaching `FILTER (WHERE ...)` to each aggregate:

```sql
SELECT
    tenant_id,
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_orders,
    COUNT(*) FILTER (WHERE status = 'pending') AS pending_orders,
    COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled_orders,
    COALESCE(
        SUM(total_amount) FILTER (WHERE status = 'paid'),
        0
    ) AS paid_amount
FROM agg_lab.orders
GROUP BY tenant_id
ORDER BY tenant_id;
```

Expected result:

| tenant_id | all_orders | paid_orders | pending_orders | cancelled_orders | paid_amount |
|---:|---:|---:|---:|---:|---:|
| 10 | 7 | 5 | 1 | 1 | 940 |
| 20 | 5 | 4 | 1 | 0 | 870 |

The advantage of `FILTER` is that each aggregate explicitly states **which subset of rows it operates on**.

### 8.1. FILTER vs. WHERE

If you write:

```sql
SELECT
    tenant_id,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id;
```

then `pending` and `cancelled` rows are excluded from **the entire** aggregation.

With `COUNT(*) FILTER (WHERE status = 'paid')`, those rows stay in the group's input set; only **that specific function** skips rows not matching the condition. That lets you compute `paid_orders`, `pending_orders`, and `all_orders` simultaneously.

### 8.2. FILTER Combined with DISTINCT

```sql
SELECT
    tenant_id,
    COUNT(DISTINCT customer_id)
        FILTER (WHERE status = 'paid') AS paying_customers,
    COUNT(DISTINCT customer_id)
        FILTER (WHERE status = 'pending') AS pending_customers
FROM agg_lab.orders
GROUP BY tenant_id
ORDER BY tenant_id;
```

The sets of customers across the two statuses **can overlap**. Therefore, never add the two distinct counts together to derive the tenant's total unique customers.

### 8.3. CASE WHEN Is an Equivalent Pattern for Many Counts

On other SQL systems, you may encounter:

```sql
SELECT
    tenant_id,
    SUM(CASE WHEN status = 'paid' THEN 1 ELSE 0 END)
        AS paid_orders,
    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END)
        AS pending_orders
FROM agg_lab.orders
GROUP BY tenant_id;
```

When rows exist and conditions are simple, this yields the same counts as `COUNT(*) FILTER`. However:

- `COUNT(*) FILTER` directly expresses "count rows matching the condition."
- `SUM(CASE ... ELSE 0 END)` is arithmetic addition; check its behavior when there are no input rows.
- For summing money, `SUM(CASE WHEN ... THEN total_amount ELSE 0 END)` can produce 0 when no orders have that status **if the group has rows from other statuses**. `SUM(...) FILTER` can return NULL when no rows match, so consider `COALESCE`.

Do not pick a syntax because it feels faster; prioritize clarity first and measure the execution plan if a workload has issues.

## 9. Aggregating by Day, Month, and Time Zone

You must usually choose the **time granularity** before writing `GROUP BY`: hour, day, week, month, quarter, or year?

### 9.1. Grouping by Local Day

Because `created_at` is `TIMESTAMPTZ`, to report by calendar date in Vietnam:

```sql
SELECT
    (created_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS local_order_date,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY
    (created_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
ORDER BY local_order_date;
```

`AT TIME ZONE 'Asia/Ho_Chi_Minh'` converts the `TIMESTAMPTZ` instant to a local wall-clock timestamp; casting to `date` extracts the corresponding calendar day.

Do not blindly write `created_at::date` across systems assuming it gives Vietnam dates: casting `TIMESTAMPTZ` depends on the session's time zone. If tenants span multiple time zones, establish a clear reporting policy.

### 9.2. Grouping by Month

```sql
SELECT
    date_trunc(
        'month',
        created_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AS month_local,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY
    date_trunc(
        'month',
        created_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
ORDER BY month_local;
```

Result on the lab data:

| month_local | paid_orders | paid_amount |
|---|---:|---:|
| 2026-01-01 00:00:00 | 4 | 1040 |
| 2026-02-01 00:00:00 | 3 | 290 |
| 2026-03-01 00:00:00 | 2 | 480 |

`date_trunc('month', ...)` truncates timestamps in the same month to the start of that month under the chosen clock. In this example, the output after `AT TIME ZONE` is `timestamp without time zone`; it is a **local month label**, not a `TIMESTAMPTZ` carrying its own offset.

### 9.3. One Row per Tenant–Month

```sql
SELECT
    tenant_id,
    date_trunc(
        'month',
        created_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AS month_local,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id, month_local
ORDER BY tenant_id, month_local;
```

PostgreSQL supports referencing SELECT aliases in `GROUP BY` in appropriate cases. However, if an alias matches an input column name, name resolution rules can be surprising; when clarity matters, repeat the expression or use a CTE to name the bucket.

### 9.4. Using a CTE to Name the Time Bucket

```sql
WITH paid_orders AS (
    SELECT
        tenant_id,
        total_amount,
        date_trunc(
            'month',
            created_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        ) AS month_local
    FROM agg_lab.orders
    WHERE status = 'paid'
)
SELECT
    tenant_id,
    month_local,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM paid_orders
GROUP BY tenant_id, month_local
ORDER BY tenant_id, month_local;
```

The main benefit of a CTE here is **readability and avoiding repeated expressions**. Modern PostgreSQL can inline and optimize many CTEs as part of the overall query; do not assume every CTE forces materialization or is inherently slower.

### 9.5. Monthly Counts and Date Range Filtering

For a "first three months of 2026" report, filter using a **half-open interval**:

```sql
SELECT
    date_trunc(
        'month',
        created_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AS month_local,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
  AND created_at >= TIMESTAMPTZ '2026-01-01 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-04-01 00:00:00+07'
GROUP BY month_local
ORDER BY month_local;
```

Using `>=` start and `<` exclusive end avoids the `"23:59:59.999..."` pitfall with high-precision timestamps. Comparing directly against `created_at` is also generally more index-friendly than wrapping the column in a function inside `WHERE`, depending on the plan.

### 9.6. Grouping by Date Does Not Guarantee Every Month Appears

`GROUP BY` creates groups only for months that **actually have input rows**; it does not fabricate empty months.

If a report must display months 01–12 with 0 when no orders exist, generate a calendar with `generate_series` and `LEFT JOIN` the aggregated results:

```sql
WITH months AS (
    SELECT generate_series(
        DATE '2026-01-01',
        DATE '2026-12-01',
        INTERVAL '1 month'
    )::date AS month_start
),
monthly AS (
    SELECT
        date_trunc(
            'month',
            created_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        )::date AS month_start,
        SUM(total_amount) AS paid_amount
    FROM agg_lab.orders
    WHERE status = 'paid'
    GROUP BY 1
)
SELECT
    m.month_start,
    COALESCE(a.paid_amount, 0) AS paid_amount
FROM months AS m
LEFT JOIN monthly AS a
    ON a.month_start = m.month_start
ORDER BY m.month_start;
```

Here the **12-row calendar** sits on the left side, so months without orders still appear. `COALESCE` turns missing sums into 0 per the report's display rule. Never use `INNER JOIN` if empty months must be preserved.

## 10. GROUP BY After a JOIN: Common Cause of Multiplied Sums

This is the most critical part of choosing the aggregation grain.

`orders` has one-order grain; `order_items` has one-line-item grain. One order has multiple items, so:

```sql
SELECT
    o.order_id,
    o.total_amount,
    i.item_id,
    i.line_total
FROM agg_lab.orders AS o
JOIN agg_lab.order_items AS i
    ON i.order_id = o.order_id
WHERE o.order_id = 1
ORDER BY i.item_id;
```

Result:

| order_id | total_amount | item_id | line_total |
|---:|---:|---:|---:|
| 1 | 300 | 1 | 200 |
| 1 | 300 | 2 | 100 |

In the joined result, `orders.total_amount=300` appears **twice** because order 1 has two items. This is **row duplication from a one-to-many relationship**, not two separate orders.

### 10.1. Broken Aggregation After a JOIN

```sql
SELECT
    o.tenant_id,
    COUNT(*) AS joined_rows,
    SUM(o.total_amount) AS wrong_order_amount
FROM agg_lab.orders AS o
JOIN agg_lab.order_items AS i
    ON i.order_id = o.order_id
WHERE o.status = 'paid'
GROUP BY o.tenant_id
ORDER BY o.tenant_id;
```

Because each order can appear multiple times:

- `COUNT(*)` counts **joined rows**, no longer orders.
- `SUM(o.total_amount)` adds **each order's amount multiple times**, potentially doubling or tripling it.

With the lab data:

| tenant_id | joined_rows | wrong_order_amount |
|---:|---:|---:|
| 10 | 7 | 1490 |
| 20 | 6 | 1500 |

Meanwhile, the true paid order revenue in `orders` by tenant is **940** and **870**. Wrong numbers can still look "plausible" if a reader is unaware of the JOIN's granularity.

### 10.2. COUNT(DISTINCT order_id) Fixes Only the Count

```sql
SELECT
    o.tenant_id,
    COUNT(DISTINCT o.order_id) AS paid_orders,
    SUM(o.total_amount) AS wrong_amount_still
FROM agg_lab.orders AS o
JOIN agg_lab.order_items AS i
    ON i.order_id = o.order_id
WHERE o.status = 'paid'
GROUP BY o.tenant_id
ORDER BY o.tenant_id;
```

`COUNT(DISTINCT o.order_id)` restores the **order count**, but `SUM(o.total_amount)` **remains inflated**. Never fix a wrong-grain query merely by slapping `DISTINCT` onto a count.

In particular, `SUM(DISTINCT o.total_amount)` is **not** a general solution either: if two independent orders happen to have the same total amount, it adds that amount only once, undercounting revenue.

### 10.3. Option 1: Aggregate Directly from the Table at the Right Grain

If you only need order-level revenue:

```sql
SELECT
    tenant_id,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id
ORDER BY tenant_id;
```

Do not join `order_items` when line-item data is unnecessary. This is the simplest way to avoid fanout.

### 10.4. Option 2: Pre-Aggregate Items to Order Grain Before Joining

If you need **both order-level amounts and item quantities**, aggregate the items table to **one row per `order_id`** first:

```sql
WITH item_per_order AS (
    SELECT
        order_id,
        COUNT(*) AS item_lines,
        SUM(quantity) AS units,
        SUM(line_total) AS item_amount
    FROM agg_lab.order_items
    GROUP BY order_id
)
SELECT
    o.tenant_id,
    COUNT(*) AS paid_orders,
    SUM(o.total_amount) AS paid_order_amount,
    SUM(COALESCE(i.units, 0)) AS units,
    SUM(COALESCE(i.item_amount, 0)) AS item_amount
FROM agg_lab.orders AS o
LEFT JOIN item_per_order AS i
    ON i.order_id = o.order_id
WHERE o.status = 'paid'
GROUP BY o.tenant_id
ORDER BY o.tenant_id;
```

Because `item_per_order` has at most **one row per `order_id`**, the JOIN does not duplicate orders. In the lab data, item totals and order totals match per tenant. In production they may differ if order totals include fees, taxes, coupons, refunds, or rounding; never assume those two sums must always be equal.

### 10.5. Option 3: Aggregate Separately and Join at the Result Grain

If you want total orders and total items per tenant, you can split into two independent sub-reports:

```sql
WITH order_totals AS (
    SELECT
        tenant_id,
        COUNT(*) AS paid_orders,
        SUM(total_amount) AS paid_amount
    FROM agg_lab.orders
    WHERE status = 'paid'
    GROUP BY tenant_id
),
item_totals AS (
    SELECT
        o.tenant_id,
        SUM(i.quantity) AS units
    FROM agg_lab.orders AS o
    JOIN agg_lab.order_items AS i
        ON i.order_id = o.order_id
    WHERE o.status = 'paid'
    GROUP BY o.tenant_id
)
SELECT
    a.tenant_id,
    a.paid_orders,
    a.paid_amount,
    COALESCE(b.units, 0) AS units
FROM order_totals AS a
LEFT JOIN item_totals AS b
    ON b.tenant_id = a.tenant_id
ORDER BY a.tenant_id;
```

Both CTEs produce **one row per tenant**, so joining them at the same grain does not multiply metrics. This pattern also fits well when metrics come from separate fact tables or pipelines.

### 10.6. Two One-to-Many Child Tables Create "Fanout Times Fanout"

Suppose each order has multiple `order_items` **and** multiple `payments` records. Joining both child tables directly to `orders` and summing pairs every item with every payment of the same order, generating roughly:

```text
item lines for the order × payment rows for the order
```

This is worse than joining a single child table. The safe pattern is aggregating **items to one row per `order_id`**, payments to **one row per `order_id`**, and then joining those reduced-grain results with `orders`.

Do not assume an outer `SELECT DISTINCT` will fix already-multiplied `SUM`s: once metrics have been summed across duplicated rows, the damage is already done.

### 10.7. LEFT JOIN and Where to Filter the Right Table

To count `device` line items per order, including orders with **no devices**, keep every order:

```sql
SELECT
    o.order_id,
    COUNT(i.item_id) AS device_lines
FROM agg_lab.orders AS o
LEFT JOIN agg_lab.order_items AS i
    ON i.order_id = o.order_id
   AND i.category = 'device'
WHERE o.status = 'paid'
GROUP BY o.order_id
ORDER BY o.order_id;
```

Placing `i.category='device'` inside `ON` keeps orders without device items, returning `COUNT(i.item_id)=0`.

If you move that condition down to `WHERE`:

```sql
-- DIFFERENT MEANING if you want to keep orders without devices:
SELECT o.order_id, COUNT(i.item_id)
FROM agg_lab.orders AS o
LEFT JOIN agg_lab.order_items AS i
    ON i.order_id = o.order_id
WHERE o.status = 'paid'
  AND i.category = 'device'
GROUP BY o.order_id;
```

then orders without a device item are dropped by `WHERE`, effectively negating the LEFT JOIN's preservation of left-side rows for this requirement.

## 11. From Simple Groups to Multi-Level Reports

An executive report often needs all three simultaneously:

1. Revenue **per tenant–region**.
2. Subtotal revenue **per tenant**.
3. **Grand total** across all tenants.

Running three separate queries and combining them with `UNION ALL` can work. However, PostgreSQL provides multi-level aggregation constructs designed for this: **`GROUPING SETS`**, **`ROLLUP`**, and **`CUBE`**.

To visualize this easily, think of paid data along two dimensions:

```text
tenant_id                  region
   10                  north / south / NULL
   20                  north / south / NULL
```

Each **aggregation level** corresponds to keeping or dropping dimensions from the grouping key.

| Level | Grouping Key | Example Question |
|---|---|---|
| Detail | `(tenant_id, region)` | How much revenue did tenant 10 generate in south? |
| Tenant subtotal | `(tenant_id)` | What is tenant 10's total revenue? |
| Region subtotal | `(region)` | What is system-wide revenue in north? |
| Grand total | `()` | What is the total across all paid orders? |

`()` is the **empty grouping set**, representing the overall aggregate across no grouping columns.

## 12. GROUPING SETS: Picking the Exact Levels You Want

Syntax:

```sql
SELECT
    tenant_id,
    region,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY GROUPING SETS (
    (tenant_id, region),
    (tenant_id),
    ()
);
```

The query asks PostgreSQL to produce:

- `(tenant_id, region)` groups.
- Groups by `tenant_id` alone.
- One global `()` group.

At the tenant subtotal level, the `region` column in the output is shown as `NULL` because it is **no longer a grouping dimension**. At the grand total level, both `tenant_id` and `region` are `NULL`.

### 12.1. Why You Cannot Rely on NULL Alone to Spot Subtotals

The source data already has orders where `region IS NULL`. Consequently, a row showing:

```text
tenant_id = 10, region = NULL
```

could be either:

- A **real data group** for tenant 10 with an unknown region, revenue 90.
- The **subtotal for tenant 10**, combining all regions, revenue 940.

Both rows display the **same key pair**, yet have **different meanings**. Relying solely on `region IS NULL` to assign an "All regions" label would be wrong.

### 12.2. GROUPING() Distinguishes Real NULLs from Rollup NULLs

PostgreSQL provides the `GROUPING(expression, ...)` function to flag dimensions omitted from the current grouping set:

```sql
SELECT
    tenant_id,
    region,
    GROUPING(tenant_id) AS tenant_is_rolled_up,
    GROUPING(region) AS region_is_rolled_up,
    GROUPING(tenant_id, region) AS grouping_mask,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY GROUPING SETS (
    (tenant_id, region),
    (tenant_id),
    ()
)
ORDER BY grouping_mask, tenant_id NULLS LAST, region NULLS LAST;
```

Meaning:

- `GROUPING(region)=0`: `region` **participates** in the grouping key; if `region` is NULL, it is a **real NULL in the data**.
- `GROUPING(region)=1`: `region` is **rolled up** at a subtotal or grand total level.
- `GROUPING(tenant_id, region)` is a **bitmask**: with this argument order, `region`'s bit has weight 1 and `tenant_id`'s bit has weight 2.

| Grouping set | tenant_is_rolled_up | region_is_rolled_up | grouping_mask |
|---|---:|---:|---:|
| `(tenant_id, region)` | 0 | 0 | 0 |
| `(tenant_id)` | 0 | 1 | 1 |
| `()` | 1 | 1 | 3 |

There is no `(region)` group in the query above, so mask 2 does not appear.

### 12.3. Labeling Aggregation Levels Accurately

```sql
SELECT
    CASE
        WHEN GROUPING(tenant_id) = 1
            THEN 'All tenants'
        ELSE tenant_id::text
    END AS tenant_label,
    CASE
        WHEN GROUPING(region) = 1
            THEN 'All regions'
        WHEN region IS NULL
            THEN 'Unknown region'
        ELSE region
    END AS region_label,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY GROUPING SETS (
    (tenant_id, region),
    (tenant_id),
    ()
)
ORDER BY
    GROUPING(tenant_id, region),
    tenant_id NULLS LAST,
    region NULLS LAST;
```

Here `GROUPING()` drives the labels, so **subtotals are never confused with real NULL regions**. When returning reports to a frontend, also include a structured `level` or `grouping_mask` field so the UI never has to infer semantics from display strings.

### 12.4. Don't Generate Unwanted Aggregation Levels

If a report needs only tenant totals and a grand total without regional breakdowns:

```sql
SELECT
    tenant_id,
    GROUPING(tenant_id) AS is_grand_total,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY GROUPING SETS ((tenant_id), ())
ORDER BY is_grand_total, tenant_id NULLS LAST;
```

`GROUPING SETS` is ideal when the designer knows **exactly which levels are needed**. Do not generate every dimensional combination if a report only uses two or three levels.

## 13. ROLLUP: Hierarchical Aggregation

`ROLLUP(tenant_id, region)` is shorthand for hierarchical grouping sets:

```sql
GROUP BY ROLLUP (tenant_id, region)
```

which is equivalent in grouping sets to:

```sql
GROUP BY GROUPING SETS (
    (tenant_id, region),
    (tenant_id),
    ()
)
```

That is:

```text
tenant + region   -> detail rows
tenant            -> tenant subtotal
()                -> grand total
```

Runnable example:

```sql
SELECT
    tenant_id,
    region,
    GROUPING(tenant_id, region) AS group_level,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY ROLLUP (tenant_id, region)
ORDER BY group_level, tenant_id NULLS LAST, region NULLS LAST;
```

### 13.1. Column Order in ROLLUP Matters

Compare:

```sql
GROUP BY ROLLUP (tenant_id, region)
```

versus:

```sql
GROUP BY ROLLUP (region, tenant_id)
```

The first produces subtotals **by tenant**. The second produces subtotals **by region**, because the intermediate grouping level retains only the **first** expression in the ROLLUP list.

This is not merely "reordering columns"; **the subtotal hierarchy itself changes**.

### 13.2. Three-Dimensional ROLLUP

With `ROLLUP (tenant_id, region, channel)`:

```text
(tenant_id, region, channel)
(tenant_id, region)
(tenant_id)
()
```

This rolls up strictly from right to left (forming a left-to-right hierarchy). If you want subtotals by `channel` without `tenant_id`, this simple `ROLLUP` will not generate them; use `GROUPING SETS` or `CUBE` as appropriate.

### 13.3. When Is ROLLUP a Good Fit?

- Reports with a natural hierarchy: `year → quarter → month`.
- `tenant → region → channel` reports with parent-level subtotals.
- Dashboards requiring "Tenant Total" and "Grand Total" rows.

Do not use ROLLUP when you need a non-hierarchical set of levels; `GROUPING SETS` expresses that requirement more directly.

## 14. CUBE: All Combinations of Aggregation Dimensions

`CUBE (tenant_id, region)` generates **every combination** of the two dimensions:

```text
(tenant_id, region)   -- detail
(tenant_id)           -- tenant subtotal
(region)              -- region subtotal
()                    -- grand total
```

Query:

```sql
SELECT
    tenant_id,
    region,
    GROUPING(tenant_id, region) AS grouping_mask,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY CUBE (tenant_id, region)
ORDER BY grouping_mask, tenant_id NULLS LAST, region NULLS LAST;
```

CUBE is particularly useful in multi-dimensional analytical reports when users want totals **by tenant**, **by region**, and **by tenant–region**.

### 14.1. CUBE Grows Exponentially with Dimensions

With `n` independent analytical expressions, `CUBE` generates up to **`2^n` grouping sets**:

| Dimensions | Grouping Sets |
|---:|---:|
| 1 | 2 |
| 2 | 4 |
| 3 | 8 |
| 4 | 16 |
| 6 | 64 |

With many high-cardinality dimensions, a broad CUBE can produce huge numbers of groups, consume substantial memory, and make results hard to interpret. Do not write `CUBE` thinking "more aggregations are always better"; generate only the levels truly needed.

### 14.2. How to Choose Between GROUPING SETS, ROLLUP, and CUBE

| Need | Suitable Syntax |
|---|---|
| Totals per tenant only | `GROUP BY tenant_id` |
| Tenant–region detail | `GROUP BY tenant_id, region` |
| Detail + tenant subtotal + grand total | `ROLLUP(tenant_id, region)` |
| Detail + tenant subtotal + region subtotal + grand total | `CUBE(tenant_id, region)` |
| Specific custom levels, not necessarily hierarchical | `GROUPING SETS (...)` |

**Choose syntax based on the report structure**, not on which syntax looks more "advanced."

## 15. GROUP BY and DISTINCT Do Not Answer the Same Question

`DISTINCT` removes duplicate output rows; `GROUP BY` defines groups for evaluating aggregates, although `GROUP BY` **without aggregates** sometimes yields the same value set as `SELECT DISTINCT`.

### 15.1. Listing Distinct Regions

```sql
SELECT DISTINCT region
FROM agg_lab.orders
ORDER BY region NULLS LAST;
```

Equivalent in output set:

```sql
SELECT region
FROM agg_lab.orders
GROUP BY region
ORDER BY region NULLS LAST;
```

When you only want a **list of distinct values**, `DISTINCT` is usually clearer in intent. When you want to **count orders per region**, use `GROUP BY region` with `COUNT(*)`.

### 15.2. Do Not Use SELECT DISTINCT to Fix JOIN Row Multiplication

If a JOIN duplicates an order across two rows, `SELECT DISTINCT o.order_id` only deduplicates the ID list down to one row per order. It **does not fix** a `SUM(o.total_amount)` that already summed repeated rows in an aggregate query.

To calculate revenue properly, preserve the right grain **before summing** or aggregate each fact separately.

### 15.3. DISTINCT Inside COUNT Cannot Be Summed Across Groups

Suppose one customer places an order in January and another in March. That customer is counted **once in each month** in the report:

```sql
SELECT
    date_trunc(
        'month',
        created_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AS month_local,
    COUNT(DISTINCT customer_id) AS unique_customers
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY month_local
ORDER BY month_local;
```

**Adding up each month's `unique_customers`** does not necessarily equal the unique customers for the entire quarter, because the same customer may return in multiple months.

This is an example of a **non-additive** (or *distinct*) measure. When changing to a coarser aggregation level, you must recompute `COUNT(DISTINCT ...)` over the corresponding dataset or use a suitable distinct-count design.

## 16. GROUP BY vs. Window Functions

`GROUP BY` **collapses multiple rows into one row per group**. Window functions with `OVER (PARTITION BY ...)` typically **preserve detail rows** while attaching the corresponding group summary alongside each row.

### 16.1. One Row per Tenant Using GROUP BY

```sql
SELECT
    tenant_id,
    SUM(total_amount) AS tenant_paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id
ORDER BY tenant_id;
```

The result has **two rows**, tenant 10 and tenant 20.

### 16.2. Keeping Every Order Row Alongside the Tenant Total

```sql
SELECT
    order_id,
    tenant_id,
    total_amount,
    SUM(total_amount) OVER (
        PARTITION BY tenant_id
    ) AS tenant_paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
ORDER BY tenant_id, order_id;
```

The result has **nine rows**, with every paid order preserved; every order in tenant 10 carries total 940, and every order in tenant 20 carries 870.

Choose:

- `GROUP BY` when the report needs **one row per tenant**.
- A window function when the report needs **one row per order** enriched with tenant-level metrics.

### 16.3. Ranking Within Each Group

```sql
SELECT
    order_id,
    tenant_id,
    total_amount,
    ROW_NUMBER() OVER (
        PARTITION BY tenant_id
        ORDER BY total_amount DESC, order_id DESC
    ) AS rank_in_tenant
FROM agg_lab.orders
WHERE status = 'paid'
ORDER BY tenant_id, rank_in_tenant;
```

This is a **top-N orders per tenant** problem, not a plain sum. To fetch only the top 2:

```sql
WITH ranked AS (
    SELECT
        order_id,
        tenant_id,
        total_amount,
        ROW_NUMBER() OVER (
            PARTITION BY tenant_id
            ORDER BY total_amount DESC, order_id DESC
        ) AS rn
    FROM agg_lab.orders
    WHERE status = 'paid'
)
SELECT order_id, tenant_id, total_amount, rn
FROM ranked
WHERE rn <= 2
ORDER BY tenant_id, rn;
```

Do not use `GROUP BY tenant_id` and try to pick the largest `order_id` if the goal is **top orders by amount**. An aggregate like `MAX(total_amount)` does not automatically return the full row achieving the maximum.

## 17. Multi-Level Aggregation and Metric Correctness

### 17.1. SUM Is Additive When Groups Are Disjoint

If each order belongs to **exactly one tenant**, the paid revenue of tenants 10 and 20 adds up to system-wide revenue:

```text
940 + 870 = 1810
```

Crucial condition: each order is **counted exactly once**, without JOIN duplication, and the groups do not overlap.

However, in a multi-currency system, you cannot add two amounts in different currencies and call it a "combined total revenue" without explicit conversion rules and exchange rate timestamps.

### 17.2. Averaging Group Averages Is Usually Wrong

In the lab:

- Tenant 10: **5 orders**, average **188.00**.
- Tenant 20: **4 orders**, average **217.50**.

Taking the simple average of those two averages:

```text
(188.00 + 217.50) / 2 = 202.75
```

does **not** equal the true average across all nine orders:

```text
1810 / 9 = 201.111...
```

To re-aggregate AOV from grouped data, you need both **total amount and order count**:

```sql
WITH by_tenant AS (
    SELECT
        tenant_id,
        SUM(total_amount) AS amount,
        COUNT(*) AS order_count
    FROM agg_lab.orders
    WHERE status = 'paid'
    GROUP BY tenant_id
)
SELECT
    SUM(amount) AS all_amount,
    SUM(order_count) AS all_orders,
    ROUND(
        SUM(amount) / NULLIF(SUM(order_count), 0),
        2
    ) AS all_avg_order_value
FROM by_tenant;
```

`NULLIF(...,0)` guards against division by zero. The number **201.11** is the order-weighted average, not an equal-weighted average of the two tenants.

### 17.3. Ratios Also Require the Right Denominator

Paid rate out of total orders per tenant:

```sql
SELECT
    tenant_id,
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_orders,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE status = 'paid')
        / NULLIF(COUNT(*), 0),
        2
    ) AS paid_rate_percent
FROM agg_lab.orders
GROUP BY tenant_id
ORDER BY tenant_id;
```

Since `COUNT(*)` of any existing group is positive, the denominator in this example is non-zero; `NULLIF` still keeps the query resilient if the aggregation structure changes.

In a system-wide report, **do not average the tenant percentages** if you want the rate across all orders; divide total paid orders by total orders.

### 17.4. Distinguish Creation Time from Payment Time

The query:

```sql
WHERE status = 'paid'
GROUP BY date_trunc('month', created_at ...)
```

returns the revenue of orders **currently paid**, grouped by **order creation month**. If the question asks for "revenue recognized in the month payment occurred," the schema needs a `paid_at` column or payment event data as the source, grouped by that timestamp.

This is a classic pitfall: **syntactically valid SQL picking the wrong timestamp column leads to the wrong business definition**.

## 18. Aggregation in Multi-Tenant Environments

In multi-tenant data, `GROUP BY tenant_id` is often a **reporting level**, while `WHERE tenant_id = :tenant` is part of the **access scope**.

For example, a dashboard strictly for tenant 10:

```sql
SELECT
    region,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE tenant_id = 10
  AND status = 'paid'
GROUP BY region
ORDER BY region NULLS LAST;
```

Never assume "simply adding `GROUP BY tenant_id`" prevents leaking another tenant's data. A query without a proper tenant filter can still compute and return figures for other tenants.

In production systems, access scoping must be enforced in the service layer, SQL policies, roles, **Row-Level Security (RLS)** if used, and appropriate infrastructure boundaries. `GROUP BY` is not an authorization mechanism.

### 18.1. Time Zones, Currencies, and Regions as Analytical Dimensions

When tenants operate across different time zones, currencies, or product catalogs, a "monthly total" can lose meaning if:

- Months are truncated in different time zones.
- USD and VND sums are added together.
- A category is renamed over time.
- A `region` name in two tenants refers to completely different geographies.

Define **all grouping dimensions** and normalization rules before aggregating. If you need to group by `currency_code`, add it to the output grain and handle currency conversion as a distinct business step.

## 19. GROUP BY and Performance Limits

`GROUP BY` on large tables can consume significant CPU, RAM, I/O, and wall-clock time. You should understand group cardinality and how PostgreSQL executes aggregations.

### 19.1. HashAggregate and GroupAggregate

A query:

```sql
EXPLAIN
SELECT tenant_id, region, SUM(total_amount)
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id, region;
```

may produce plan nodes such as:

| Plan Node | General Meaning |
|---|---|
| `HashAggregate` | Uses a hash table to gather grouping keys and compute aggregates |
| `GroupAggregate` | Computes aggregates across rows already sorted by the grouping keys |
| `Sort` | Sorts data for an aggregation strategy or `ORDER BY` |
| `Partial Aggregate` / `Finalize Aggregate` | Parallelizes eligible aggregates into partial phases before combining |

Never claim PostgreSQL will **always** pick HashAggregate or GroupAggregate for a given query: the planner chooses based on statistics, estimated group count, indexes, `work_mem`, input size, parallel settings, and PostgreSQL version.

### 19.2. Grouping Key Cardinality

Grouping by `status` produces only a few groups if there are three statuses. Grouping by `customer_id` can yield millions of groups. Grouping by `order_id` forms one group per order and barely reduces row count.

When the number of groups is large:

- Hash tables can consume substantial memory.
- Sort/aggregate steps may spill to disk if memory is insufficient.
- The result set remains large, increasing network transfer cost to the client.
- The report may need stricter filtering, limits, or pre-aggregation tailored to real needs.

**Do not add extra dimensions to GROUP BY if a dashboard only needs higher-level totals.** Extra dimensions and distinct values can expand output cardinality rapidly.

### 19.3. WHERE Should Reduce Data Before GROUP BY

```sql
SELECT tenant_id, SUM(total_amount)
FROM agg_lab.orders
WHERE status = 'paid'
  AND created_at >= TIMESTAMPTZ '2026-01-01 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-04-01 00:00:00+07'
GROUP BY tenant_id;
```

Specifying the time range and status before grouping can shrink the dataset processed, provided those filters reflect the business rule. PostgreSQL may leverage indexes or partition pruning depending on table design.

### 19.4. Indexes Do Not Always Make GROUP BY Faster

For example:

```sql
CREATE INDEX orders_tenant_status_date_idx
ON agg_lab.orders (tenant_id, status, created_at);
```

This index can help queries filtering by tenant, status, and date. However, when statistics indicate a large fraction of the table matches, PostgreSQL may choose a sequential scan followed by HashAggregate instead of reading many index entries—and that can be the faster choice.

If reports frequently inspect only paid orders, a **partial index** matching that predicate can sometimes help:

```sql
CREATE INDEX orders_paid_tenant_date_idx
ON agg_lab.orders (tenant_id, created_at)
WHERE status = 'paid';
```

Indexes are not free: they consume storage and add maintenance overhead on `INSERT`/`UPDATE`. Do not create every illustrative index in production without measuring real workloads.

### 19.5. EXPLAIN ANALYZE and BUFFERS

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    tenant_id,
    region,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id, region;
```

`EXPLAIN (ANALYZE, BUFFERS)` **actually executes the query** to measure runtime and buffer activity. For read-only SELECTs in a lab, this is appropriate; for write statements in live systems, running `ANALYZE` requires caution because it executes the modification.

Key aspects to inspect:

- Estimated vs. actual rows at each plan node.
- Number of output groups from the aggregate node.
- Sort method and any disk spill if present.
- HashAggregate memory usage and batches if shown by the planner.
- Buffer hits/reads and table scan cost.
- Difference with and without selective filters.

### 19.6. work_mem and Concurrent Queries

Sort and hash operations use working memory governed by `work_mem` and related settings depending on node type and version. Do not assume "multiplying `work_mem` by 10 makes the query 10x faster" or "each connection uses at most one allocation of `work_mem`."

A single query can have multiple memory-consuming nodes, and concurrent queries can cause total RAM usage to spike sharply. Server-level parameter changes require workload and concurrency evaluation rather than being a knee-jerk fix for a slow `GROUP BY`.

## 20. Pre-Aggregation, Stored Summaries, and Materialized Views

If dashboards repeatedly run the same expensive report over large datasets, consider **pre-aggregation**.

### 20.1. Creating a Tenant–Month Materialized View

Illustrative example:

```sql
CREATE MATERIALIZED VIEW agg_lab.monthly_paid_summary AS
SELECT
    tenant_id,
    date_trunc(
        'month',
        created_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )::date AS month_start,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id, month_start;
```

A materialized view stores **precomputed results** from the time it was created or refreshed, unlike a standard view which stores only the query definition.

Reading from it:

```sql
SELECT *
FROM agg_lab.monthly_paid_summary
ORDER BY tenant_id, month_start;
```

### 20.2. Freshness Is Part of the Data Contract

If new orders arrive after creating the materialized view, its stored data **does not update automatically**. A refresh workflow is required:

```sql
-- Run in your practice environment when you want to update the figures.
REFRESH MATERIALIZED VIEW agg_lab.monthly_paid_summary;
```

Refreshing can generate load and impact concurrent reads depending on how it is executed. `REFRESH MATERIALIZED VIEW CONCURRENTLY` has specific prerequisites, such as the view already being populated and having a suitable unique index; do not assume adding `CONCURRENTLY` works unconditionally.

**Important:** If order statuses can transition from `pending` to `paid` or be refunded, an incremental summary design must handle **updates, deletions, and adjustments**, not merely newly inserted rows.

### 20.3. Be Careful Changing the Grain of Pre-Aggregated Tables

If a pre-aggregated table stores `(tenant_id, month_start, paid_amount, paid_orders)`, you can compute quarterly paid amount and paid orders by summing months **provided months do not overlap and metric definitions are consistent**.

However, you cannot accurately derive **unique quarterly customers** from monthly `COUNT(DISTINCT customer_id)` values, because customers can buy in multiple months. Distinct metrics require storing finer-grain data or using a dedicated distinct-counting strategy.

## 21. Ensuring Consistent Aggregation Across Transactions and Reports

### 21.1. PostgreSQL Snapshots and Concurrent Changes

A single `SELECT ... GROUP BY` under default `READ COMMITTED` isolation observes row versions consistent with that statement's snapshot. However, if you execute:

```sql
SELECT COUNT(*) FROM agg_lab.orders WHERE status = 'paid';

SELECT SUM(total_amount)
FROM agg_lab.orders
WHERE status = 'paid';
```

as two separate statements, another transaction can commit between them. The order count and total amount could then reflect **two different points in time**.

If figures must come from the exact same snapshot, compute them in **a single SELECT**:

```sql
SELECT
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid';
```

Or use a read-only transaction with an appropriate isolation level for multi-statement reporting:

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT COUNT(*) FROM agg_lab.orders WHERE status = 'paid';
SELECT SUM(total_amount) FROM agg_lab.orders WHERE status = 'paid';

COMMIT;
```

Do not hold reporting transactions open indefinitely: long-lived snapshots prevent old row versions from being reclaimed and can affect vacuuming and resource usage.

### 21.2. Reports Do Not Replace an Accounting Ledger

In the lab, `SUM(total_amount) WHERE status='paid'` returns "the amount of orders currently marked paid." Real-world systems may also require:

- Partial payments.
- Refunds and chargebacks.
- Taxes, discounts, and fees.
- Multiple currencies and exchange rates.
- Revenue recognition events occurring at a different time than order placement.
- Negative offsetting entries or immutable ledgers.

Before elevating a query into an official financial KPI, verify the right fact table and metric definition—never use `GROUP BY` to paper over business-rule discrepancies.

## 22. Common Aggregation Misconceptions

**1. "GROUP BY automatically sorts the output."** No. When a specific order is needed, use `ORDER BY`.

**2. "Just add every SELECT column to GROUP BY to silence the error."** No. That can change the grain from one tenant to one order.

**3. "COUNT(*) and COUNT(region) are always identical."** No. `COUNT(region)` skips rows where `region` is `NULL`.

**4. "Adding monthly COUNT(DISTINCT customer_id) values gives the quarterly customer count."** No, if customers purchase in more than one month.

**5. "The average of per-tenant AVGs equals the system-wide AVG."** No, unless groups are weighted appropriately; compute total amount / total orders.

**6. "WHERE SUM(total_amount) > 1000 is valid."** No, not in a standard query; group aggregate filters belong in `HAVING` or an outer query.

**7. "HAVING and WHERE are always interchangeable."** No. `WHERE` filters rows; `HAVING` filters groups.

**8. "After joining orders and items, COUNT(*) still equals the order count."** No. It counts joined rows.

**9. "After a fanout JOIN, COUNT(DISTINCT order_id) fixes SUM(total_amount) too."** No. You must fix the grain for the monetary metric separately.

**10. "SUM(DISTINCT total_amount) solves all duplicate-counting problems."** No. Two valid orders with the same amount will be undercounted.

**11. "LEFT JOIN with WHERE i.category = ... still preserves orders without items."** Usually no; conditions on the right table can eliminate NULL-extended rows.

**12. "NULL = NULL is true, which is why GROUP BY groups NULLs."** Incorrect explanation. `NULL = NULL` is unknown; `GROUP BY` has its own grouping rule for NULLs.

**13. "In ROLLUP, region=NULL always means missing region data."** No. It may be a subtotal NULL; check with `GROUPING()`.

**14. "ROLLUP(a,b) and ROLLUP(b,a) produce the same subtotals."** No. Column order determines the hierarchy.

**15. "CUBE is cheaper than regular GROUP BY."** Not by default; it computes multiple grouping sets.

**16. "SUM on an empty set returns 0."** In PostgreSQL, `SUM` on an empty set returns `NULL`; `COUNT(*)` returns 0.

**17. "GROUP BY month automatically generates months with no data."** No. You need a calendar table or `generate_series`.

**18. "date_trunc('day', created_at) always gives the tenant's local day."** Not if the column is `TIMESTAMPTZ` and the reporting time zone is not explicitly applied.

**19. "A single GROUP BY query over paid orders gives standard financial revenue."** Only under the stated definition; it does not automatically handle refunds, taxes, or currencies.

**20. "Window SUM OVER replaces GROUP BY without changing row count."** No. Window functions keep detail rows, whereas GROUP BY collapses rows to one per group.

**21. "Grouping by order_id gives customer totals."** No. One-order grain differs from one-customer grain.

**22. "Indexing every grouping key guarantees fast queries."** No. You must consider scan types, cardinality, query plans, and write overhead.

**23. "Materialized views update immediately when source tables change."** No. They require a refresh or an explicit update pipeline.

**24. "GROUP BY tenant_id automatically protects other tenants' data."** No. Isolation requires explicit filters and access-control policies.

## 23. Practice Exercises with Solutions

### Exercise 1 — Totals per Tenant

**Requirement:** count only `paid` orders; return tenant, order count, and total amount. One row per tenant.

**Solution:**

```sql
SELECT
    tenant_id,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id
ORDER BY tenant_id;
```

Result: tenant 10 has 5 orders / 940; tenant 20 has 4 orders / 870.

### Exercise 2 — Adding Region Changes the Grain

**Requirement:** order count and amount per **tenant–region**.

**Solution:**

```sql
SELECT
    tenant_id,
    region,
    COUNT(*) AS orders,
    SUM(total_amount) AS amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id, region
ORDER BY tenant_id, region NULLS LAST;
```

There are **six groups**, including one `region=NULL` group per tenant.

### Exercise 3 — Counting Orders Missing a Region

**Requirement:** calculate paid orders, orders with a region, and orders missing a region.

**Solution:**

```sql
SELECT
    COUNT(*) AS total,
    COUNT(region) AS known_region,
    COUNT(*) - COUNT(region) AS missing_region
FROM agg_lab.orders
WHERE status = 'paid';
```

Result: `9, 7, 2`.

### Exercise 4 — HAVING

**Requirement:** find tenants with a total paid amount of 900 or more.

**Solution:**

```sql
SELECT tenant_id, SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id
HAVING SUM(total_amount) >= 900
ORDER BY tenant_id;
```

Only tenant 10 with 940.

### Exercise 5 — FILTER Across Multiple Statuses

**Requirement:** for each tenant, retrieve total, paid, pending, and cancelled order counts.

**Solution:**

```sql
SELECT
    tenant_id,
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_orders,
    COUNT(*) FILTER (WHERE status = 'pending') AS pending_orders,
    COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled_orders
FROM agg_lab.orders
GROUP BY tenant_id
ORDER BY tenant_id;
```

Tenant 10: `7,5,1,1`; tenant 20: `5,4,1,0`.

### Exercise 6 — Monthly Revenue in Vietnam Time

**Requirement:** group paid orders by local month and sort ascending.

**Solution:**

```sql
SELECT
    date_trunc(
        'month',
        created_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AS month_local,
    SUM(total_amount) AS amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY month_local
ORDER BY month_local;
```

Amount results: month 1 = 1040, month 2 = 290, month 3 = 480.

### Exercise 7 — GROUP BY Inflated After a JOIN

**Question:** why is the following query wrong if the goal is total order amount?

```sql
SELECT o.tenant_id, SUM(o.total_amount)
FROM agg_lab.orders AS o
JOIN agg_lab.order_items AS i
    ON i.order_id = o.order_id
WHERE o.status = 'paid'
GROUP BY o.tenant_id;
```

**Answer:** An order with multiple items repeats `o.total_amount` across multiple joined rows, summing it multiple times. Query `orders` directly, or aggregate items to one row per `order_id` before joining.

### Exercise 8 — Why Not Use SUM(DISTINCT)

**Requirement:** explain why `SUM(DISTINCT o.total_amount)` does not fix fanout in all cases.

**Answer:** If two different orders share `total_amount=100`, `SUM(DISTINCT total_amount)` adds 100 only once even though 200 is needed. `DISTINCT` on **amount values** is not distinct on **order identities**.

### Exercise 9 — Counting Unique Customers

**Requirement:** how many distinct customers placed at least one paid order per tenant?

**Solution:**

```sql
SELECT
    tenant_id,
    COUNT(DISTINCT customer_id) AS paying_customers
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id
ORDER BY tenant_id;
```

Each tenant has **3 customers** in the lab.

### Exercise 10 — Tenant Subtotals and Grand Total with ROLLUP

**Requirement:** aggregate by tenant while also adding a system-wide grand total row.

**Solution:**

```sql
SELECT
    tenant_id,
    GROUPING(tenant_id) AS is_grand_total,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY ROLLUP (tenant_id)
ORDER BY is_grand_total, tenant_id NULLS LAST;
```

The result includes tenant 10, tenant 20, and a grand total row of `9 orders / 1810`. The `is_grand_total` column evaluates to `1` on the total row, helping distinguish it if `tenant_id` could be NULL in another model.

### Exercise 11 — GROUPING() vs. Real NULLs

**Question:** in `ROLLUP(tenant_id, region)`, what can two rows with `tenant_id=10` and `region=NULL` mean?

**Answer:** One row is the **unknown-region** group in the raw data (90), and the other is the **subtotal for tenant 10** (940). Use `GROUPING(region)=0` to identify the real data group and `GROUPING(region)=1` for the subtotal.

### Exercise 12 — CUBE vs. ROLLUP

**Requirement:** in addition to tenant–region details and tenant subtotals, you need **region totals across all tenants**.

**Solution:**

```sql
SELECT
    tenant_id,
    region,
    GROUPING(tenant_id, region) AS mask,
    SUM(total_amount) AS amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY CUBE (tenant_id, region)
ORDER BY mask, tenant_id NULLS LAST, region NULLS LAST;
```

`CUBE` generates `(region)`, whereas `ROLLUP(tenant_id,region)` does not produce that level.

### Exercise 13 — Average Across Two Tenants

**Question:** Why is `(188 + 217.5)/2 = 202.75` not the system-wide AOV?

**Answer:** The two tenants have **different order counts**, 5 and 4. System-wide AOV must be `(940+870)/(5+4) = 1810/9 ≈ 201.11`, which is weighted by order count.

### Exercise 14 — Window Function Preserving Detail Rows

**Requirement:** keep one row per paid order, accompanied by the tenant's total paid amount.

**Solution:**

```sql
SELECT
    order_id,
    tenant_id,
    total_amount,
    SUM(total_amount) OVER (
        PARTITION BY tenant_id
    ) AS tenant_paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
ORDER BY tenant_id, order_id;
```

The output has **9 rows**, rather than two rows as with `GROUP BY tenant_id`.

### Exercise 15 — Empty Month Groups

**Question:** paid orders exist only in months 1–3; how do you ensure the report still lists months 4–12 with 0 revenue?

**Answer:** Generate the month series with `generate_series`, aggregate `orders` by month in a separate CTE, then `LEFT JOIN` the calendar to the aggregated CTE and `COALESCE` missing totals to 0. `GROUP BY` alone never creates groups without input rows.

### Exercise 16 — Grouping by Customer Instead of Order

**Requirement:** in tenant 10, how many paid orders did each customer place?

**Solution:**

```sql
SELECT
    customer_id,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS total_paid
FROM agg_lab.orders
WHERE tenant_id = 10
  AND status = 'paid'
GROUP BY customer_id
ORDER BY customer_id;
```

Result: customer 101 has **2 orders / 550**, customer 102 has **2 orders / 270**, and customer 103 has **1 order / 120**. The aggregation grain is **one customer within tenant 10**.

### Exercise 17 — Cleaning Up the Lab Environment

Once you are certain `agg_lab` contains only objects created for this lesson:

```sql
-- Run only in a practice database and after verifying scope:
-- DROP MATERIALIZED VIEW IF EXISTS agg_lab.monthly_paid_summary;
-- DROP TABLE IF EXISTS agg_lab.order_items;
-- DROP TABLE IF EXISTS agg_lab.orders;
-- DROP SCHEMA IF EXISTS agg_lab;
```

Do not run `DROP SCHEMA ... CASCADE` in a shared database without verifying dependencies; doing so can wipe out data unrelated to this lesson.

## 24. Checklist for Designing a GROUP BY Report

Before shipping a query to a dashboard or API, walk through these questions:

1. **What does one source row represent?** An order, item, payment, or event?
2. **What does one output row represent?** A tenant, tenant–region, month, customer, or subtotal?
3. **Are the right rows filtered in WHERE?** Paid status, time range, tenant scope, product filter?
4. **Are the aggregate functions semantically right?** `COUNT(*)` vs. `COUNT(col)`, `COUNT(DISTINCT)`, `SUM`/`AVG`?
5. **Are any columns nullable?** `COUNT(column)` ignores NULLs; `GROUP BY` creates a NULL group.
6. **Is there a one-to-many or many-to-many JOIN?** If so, parent metrics can be multiplied; reduce grain first.
7. **Are multiple subtotal levels needed?** Choose `GROUPING SETS`, `ROLLUP`, or `CUBE`, and distinguish NULLs with `GROUPING()`.
8. **Which timestamp is the right one?** Order date, payment date, refund date; which time zone?
9. **Should missing groups display 0?** Generate a dimension/calendar table and LEFT JOIN.
10. **Is the metric additive?** `SUM` usually is if groups are disjoint; distinct counts and averages must be recomputed with proper weights.
11. **Are all detail rows needed?** If so, consider window functions instead of `GROUP BY`.
12. **Does the output need sorting?** `GROUP BY` guarantees none; add an explicit `ORDER BY`.
13. **Are there multiple tenants or currencies?** Never mix data across incompatible scopes or currencies.
14. **Has performance been measured?** `EXPLAIN`, cardinality, hash/sort memory, indexes, scanned volume, concurrency cost.
15. **Does the report require snapshot consistency?** Single vs. multiple statements, isolation level, mutable data, and materialization.

## 25. Summary

In PostgreSQL, **`GROUP BY` collapses detail rows into groups defined by grouping keys**, while functions like `COUNT`, `SUM`, and `AVG` compute metrics per group. The grouping keys determine the **aggregation grain**: one row per tenant differs from one row per tenant–region, and differs from one row for the whole system.

Key principles:

- **Choose the grain before writing SQL**; do not add columns to `GROUP BY` just to make errors go away.
- **`WHERE` filters rows; `HAVING` filters groups; `FILTER` scopes individual aggregates.**
- **`COUNT(*)` counts rows; `COUNT(column)` skips NULLs; `COUNT(DISTINCT)` cannot simply be summed across overlapping groups.**
- **JOINs can change the grain** and corrupt `SUM`/`COUNT`; aggregate each table to the right grain before combining metrics.
- **`GROUPING SETS` selects exact levels; `ROLLUP` creates hierarchical subtotals; `CUBE` creates all level combinations.** Use `GROUPING()` to separate rollup NULLs from genuine NULLs in data.
- **Time-based aggregation requires choosing the right timestamp and time zone**; `GROUP BY` does not fabricate empty months.
- **AVG and ratios require the right denominator**—never average averages or sum distinct counts carelessly.
- **`GROUP BY` does not guarantee output order**, nor does it automatically handle access control, snapshot consistency, or I/O optimization.

**Conclusion:** A correct aggregate query is more than SQL that compiles. It must clearly answer: "what is being **counted/summed**, across **which rows**, and what **level** does each report row represent?" Once those three questions are settled, `GROUP BY` becomes a reliable tool for building KPIs, reports, and data analytics in PostgreSQL.

### Official PostgreSQL Documentation

- [SELECT and GROUP BY](https://www.postgresql.org/docs/current/sql-select.html).
- [Aggregate Functions](https://www.postgresql.org/docs/current/functions-aggregate.html).
- [GROUPING() and Grouping Operations](https://www.postgresql.org/docs/current/functions-aggregate.html#FUNCTIONS-GROUPING-TABLE).
- [Date/Time Functions, date_trunc, and AT TIME ZONE](https://www.postgresql.org/docs/current/functions-datetime.html).
- [Window Functions](https://www.postgresql.org/docs/current/tutorial-window.html).
- [EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html).
