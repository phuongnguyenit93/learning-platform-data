# Derived Tables, Aliases, and Organizing Multi-Step Queries

When a query requires multiple processing steps, writing every filter, grouping, calculation, and table join inside a single `SELECT` can make the SQL hard to read and verify. MySQL lets you place a `SELECT` statement inside the `FROM` clause. The result of the inner `SELECT` is treated as a table by the outer query; this construct is called a **derived table**.

Derived tables break a query into steps with clear boundaries: the first step builds an intermediate dataset, the next step filters or joins that dataset, and the final step aggregates and formats the output. Aliases name the derived table and its columns, keeping queries readable and avoiding ambiguity across multiple data sources.

This lesson falls within `DATABASE_MYSQL`: mastering JOINs and subqueries, organizing multi-step SQL queries, controlling alias scope, understanding how MySQL optimizes derived tables, and reading `EXPLAIN` to evaluate performance.

## 1. What Is a Derived Table?

A derived table is a subquery appearing in the `FROM` clause. MySQL executes or transforms that subquery to supply a row set to the outer query.

Syntax:

~~~sql
SELECT
    outer_alias.column_name
FROM (
    SELECT
        column_a,
        column_b
    FROM source_table
    WHERE condition
) AS outer_alias;
~~~

The parenthesized block is the query producing the dataset. The name immediately following the closing parenthesis is the mandatory alias of the derived table. The outer query treats that result as a table source exposing the columns projected by the inner `SELECT`.

Example:

~~~sql
SELECT
    customer_totals.customer_id,
    customer_totals.order_count,
    customer_totals.total_amount
FROM (
    SELECT
        customer_id,
        COUNT(*) AS order_count,
        SUM(total_amount) AS total_amount
    FROM orders
    GROUP BY customer_id
) AS customer_totals
WHERE customer_totals.total_amount >= 1000
ORDER BY customer_totals.total_amount DESC;
~~~

The query splits into two logical steps:

1. The derived table `customer_totals` groups orders by `customer_id`, calculating each customer's order count and total amount.
2. The outer query filters customers with a total of at least 1,000 and sorts by total amount descending.

A derived table is not a physical table pre-created in the schema. It is a data source scoped to a single SQL statement. MySQL may materialize its result into an internal temporary structure or transform the query so no physical intermediate table is needed; optimization details are covered later.

## 2. Derived Table Aliases Are Mandatory

MySQL requires every derived table in `FROM` to have an alias. The following example lacks an alias:

~~~sql
SELECT *
FROM (
    SELECT customer_id, COUNT(*) AS order_count
    FROM orders
    GROUP BY customer_id
);
~~~

This statement is invalid because the subquery in `FROM` has not been named.

Correct syntax:

~~~sql
SELECT *
FROM (
    SELECT customer_id, COUNT(*) AS order_count
    FROM orders
    GROUP BY customer_id
) AS customer_summary;
~~~

The `AS` keyword may be omitted:

~~~sql
SELECT *
FROM (
    SELECT customer_id, COUNT(*) AS order_count
    FROM orders
    GROUP BY customer_id
) customer_summary;
~~~

Using `AS` usually makes aliases easier to spot. Pick meaningful names reflecting the data's role, such as `customer_summary`, `monthly_sales`, `latest_payment`, or `active_accounts`, rather than generic names like `t1`, `x`, or `tmp`.

### 2.1. Aliases Let the Outer Query Reference Columns

After naming the alias, the outer query uses the form:

~~~sql
alias_name.column_name
~~~

Example:

~~~sql
SELECT
    monthly_sales.month_start,
    monthly_sales.revenue
FROM (
    SELECT
        DATE_FORMAT(created_at, '%Y-%m-01') AS month_start,
        SUM(total_amount) AS revenue
    FROM orders
    GROUP BY DATE_FORMAT(created_at, '%Y-%m-01')
) AS monthly_sales;
~~~

Qualifying column names with the full alias is especially helpful when a query involves multiple tables sharing columns like `id`, `name`, `created_at`, or `status`.

### 2.2. Source Table Aliases and Derived Table Aliases Are Distinct

In this example:

~~~sql
SELECT
    customer_summary.customer_id,
    customer_summary.total_amount
FROM (
    SELECT
        o.customer_id,
        SUM(o.total_amount) AS total_amount
    FROM orders AS o
    GROUP BY o.customer_id
) AS customer_summary;
~~~

- `o` is the alias of the `orders` table inside the subquery.
- `customer_summary` is the alias of the derived table in the outer query.

The `orders` table alias is scoped strictly inside the subquery. The outer query cannot reference `o.customer_id` once the subquery ends; it sees only the columns exposed by the derived table.

### 2.3. Column Aliases and Output Column Names

Give explicit aliases to computed expressions:

~~~sql
SELECT
    summary.customer_id,
    summary.order_count,
    summary.average_amount
FROM (
    SELECT
        customer_id,
        COUNT(*) AS order_count,
        AVG(total_amount) AS average_amount
    FROM orders
    GROUP BY customer_id
) AS summary;
~~~

Without aliases on expressions, resulting column names can be awkward to reference or inconsistent with what readers expect. Defining aliases inside the subquery establishes a clean column interface for the outer query.

### 2.4. Column Alias Lists on Derived Tables

MySQL also supports placing a column name list after the derived table alias. This is useful when you want to rename output columns at the derived table boundary:

~~~sql
SELECT
    customer_summary.customer_id,
    customer_summary.order_count
FROM (
    SELECT customer_id, COUNT(*)
    FROM orders
    GROUP BY customer_id
) AS customer_summary (customer_id, order_count);
~~~

The column alias list must match the number of columns returned by the subquery. While this syntax works, placing aliases directly in the inner `SELECT` is usually easier to read because the output name sits right beside the expression producing it.

## 3. Derived Tables Operate Within Query Scope

A derived table defines its own column set. The outer query can only reference columns projected by the inner `SELECT`.

Example:

~~~sql
SELECT summary.customer_id, summary.total_amount
FROM (
    SELECT
        customer_id,
        SUM(total_amount) AS total_amount
    FROM orders
    GROUP BY customer_id
) AS summary;
~~~

The outer query cannot reference `orders.created_at` because that column was not projected by the derived table.

If the outer query needs to filter by month, expose the month column from the subquery:

~~~sql
SELECT
    monthly_summary.customer_id,
    monthly_summary.month_start,
    monthly_summary.total_amount
FROM (
    SELECT
        customer_id,
        DATE_FORMAT(created_at, '%Y-%m-01') AS month_start,
        SUM(total_amount) AS total_amount
    FROM orders
    GROUP BY
        customer_id,
        DATE_FORMAT(created_at, '%Y-%m-01')
) AS monthly_summary
WHERE monthly_summary.month_start >= '2025-01-01';
~~~

Design guideline: a derived table should expose all columns needed by subsequent steps without blindly forwarding every column from the source tables.

### 3.1. Duplicate Column Names

If a derived table outputs two columns with the same name, referencing them becomes ambiguous or MySQL rejects the query because column names inside a derived table must be unique.

Avoid:

~~~sql
SELECT *
FROM (
    SELECT
        c.id,
        o.id
    FROM customer AS c
    JOIN orders AS o ON o.customer_id = c.id
) AS joined_data;
~~~

Use distinct aliases instead:

~~~sql
SELECT *
FROM (
    SELECT
        c.id AS customer_id,
        o.id AS order_id
    FROM customer AS c
    JOIN orders AS o ON o.customer_id = c.id
) AS joined_data;
~~~

Unique column names keep the derived table interface clean and prevent misreferencing columns.

## 4. Using Derived Tables to Split Multi-Step Queries

Derived tables are particularly helpful when a later step consumes aggregated or computed outputs from an earlier step.

### 4.1. Step 1: Aggregate, Step 2: Filter Aggregated Results

You cannot directly use an aggregate alias in the `WHERE` clause of the same `SELECT` because `WHERE` is evaluated before group aggregation. A derived table introduces a boundary so the outer query can filter aggregated results.

~~~sql
SELECT
    customer_summary.customer_id,
    customer_summary.total_amount
FROM (
    SELECT
        customer_id,
        SUM(total_amount) AS total_amount
    FROM orders
    GROUP BY customer_id
) AS customer_summary
WHERE customer_summary.total_amount >= 5000;
~~~

This can also be written using `HAVING` in the same `SELECT`:

~~~sql
SELECT
    customer_id,
    SUM(total_amount) AS total_amount
FROM orders
GROUP BY customer_id
HAVING SUM(total_amount) >= 5000;
~~~

Both express the same goal. Use `HAVING` when you only need to filter groups right at the aggregation step. Use a derived table when the aggregated result also needs to be joined with another source, further computed, paginated, or treated as an independent dataset.

### 4.2. Step 1: Compute Metrics, Step 2: Classify

~~~sql
SELECT
    customer_metrics.customer_id,
    customer_metrics.order_count,
    customer_metrics.revenue,
    CASE
        WHEN customer_metrics.revenue >= 10000 THEN 'GOLD'
        WHEN customer_metrics.revenue >= 5000 THEN 'SILVER'
        ELSE 'STANDARD'
    END AS customer_tier
FROM (
    SELECT
        customer_id,
        COUNT(*) AS order_count,
        SUM(total_amount) AS revenue
    FROM orders
    WHERE status IN ('PAID', 'SHIPPED')
    GROUP BY customer_id
) AS customer_metrics
ORDER BY customer_metrics.revenue DESC;
~~~

The inner step computes metrics per customer. The outer step uses those metrics to assign tiers. This structure avoids repeating the `SUM` expression in multiple places.

### 4.3. Step 1: Find the Most Recent Purchase, Step 2: Fetch Order Details

~~~sql
SELECT
    latest_order.customer_id,
    latest_order.order_id,
    latest_order.created_at,
    latest_order.total_amount
FROM (
    SELECT
        customer_id,
        MAX(created_at) AS latest_created_at
    FROM orders
    GROUP BY customer_id
) AS latest_time
JOIN orders AS latest_order
  ON latest_order.customer_id = latest_time.customer_id
 AND latest_order.created_at = latest_time.latest_created_at;
~~~

The derived table finds the latest order timestamp per customer. The outer query joins back to `orders` to fetch the detail columns of that order.

If a customer has two orders sharing the exact same maximum `created_at`, the query can return multiple rows. If business rules require strictly one order, add a deterministic tie-breaker such as the highest `order_id`, or use `ROW_NUMBER()` in MySQL 8.0.

### 4.4. Structuring a Multi-Step Report

A report can be organized into:

1. Filter valid orders.
2. Aggregate revenue per customer.
3. JOIN with the customer table.
4. Segment customers into revenue tiers.
5. Sort and limit results.

Example:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    s.order_count,
    s.revenue,
    CASE
        WHEN s.revenue >= 10000 THEN 'GOLD'
        WHEN s.revenue >= 5000 THEN 'SILVER'
        ELSE 'STANDARD'
    END AS tier
FROM customer AS c
JOIN (
    SELECT
        customer_id,
        COUNT(*) AS order_count,
        SUM(total_amount) AS revenue
    FROM orders
    WHERE status IN ('PAID', 'SHIPPED')
      AND created_at >= '2025-01-01'
    GROUP BY customer_id
) AS s
  ON s.customer_id = c.customer_id
WHERE c.is_active = 1
ORDER BY s.revenue DESC
LIMIT 50;
~~~

The derived table `s` supplies aggregated figures, while `customer` provides profile attributes. `INNER JOIN` is used because the query only wants customers with qualifying orders. To preserve customers without orders as well, switch to `LEFT JOIN` and handle `NULL` values in aggregated columns.

## 5. Derived Tables Combined with JOINs

Derived tables can sit alongside base tables in `FROM` and be joined just like any data source.

### 5.1. Joining with a Pre-Aggregated Result Set

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(s.revenue, 0) AS revenue
FROM customer AS c
LEFT JOIN (
    SELECT
        customer_id,
        SUM(total_amount) AS revenue
    FROM orders
    WHERE status = 'PAID'
    GROUP BY customer_id
) AS s
  ON s.customer_id = c.customer_id;
~~~

This query retains all customers, including those without PAID orders. Where no derived-table row matches, `s.revenue` is `NULL`; `COALESCE` converts it to 0 for display.

Use `COALESCE` only when business logic equates zero transactions with zero revenue. If you must distinguish "no data" from "sum is zero," leave `NULL` intact.

### 5.2. Filter Conditions in ON vs. WHERE

With `LEFT JOIN`, condition placement can change whether unmatched rows are preserved.

Example preserving all customers while matching only high-revenue summaries:

~~~sql
SELECT
    c.customer_id,
    s.revenue
FROM customer AS c
LEFT JOIN (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
) AS s
  ON s.customer_id = c.customer_id
 AND s.revenue >= 1000;
~~~

If `s.revenue >= 1000` is moved down to `WHERE`, rows without a matching summary are dropped because `NULL >= 1000` evaluates to UNKNOWN. In that case `LEFT JOIN` behaves like an `INNER JOIN` with respect to that condition.

~~~sql
SELECT
    c.customer_id,
    s.revenue
FROM customer AS c
LEFT JOIN (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
) AS s
  ON s.customer_id = c.customer_id
WHERE s.revenue >= 1000;
~~~

Place conditions by intent: predicates restricting which rows pair belong in `ON`; predicates filtering the final result belong in `WHERE`. For outer joins, never move predicates between the two without verifying the effect on unmatched rows.

### 5.3. Multiple Derived Tables in the Same Query

You can join multiple intermediate datasets:

~~~sql
SELECT
    c.customer_id,
    order_summary.order_count,
    payment_summary.paid_count
FROM customer AS c
LEFT JOIN (
    SELECT customer_id, COUNT(*) AS order_count
    FROM orders
    GROUP BY customer_id
) AS order_summary
  ON order_summary.customer_id = c.customer_id
LEFT JOIN (
    SELECT customer_id, COUNT(*) AS paid_count
    FROM payment
    WHERE payment_status = 'SUCCESS'
    GROUP BY customer_id
) AS payment_summary
  ON payment_summary.customer_id = c.customer_id;
~~~

Each derived table has one clear responsibility: aggregating orders and aggregating payments. This avoids row multiplication caused by directly joining two detail tables that each have a one-to-many relationship with the same customer.

Before joining multiple detail sources, verify cardinality. If a customer has 3 orders and 4 payments, joining those two detail tables directly can generate 12 rows and inflate `SUM`/`COUNT`. Aggregating each source down to one row per customer before joining keeps fan-out under control.

## 6. Derived Tables vs. CTEs: Two Ways to Organize Multi-Step Queries

MySQL 8.0 supports Common Table Expressions (CTEs) via the `WITH` clause. A CTE names a temporary result set scoped to a single statement.

Derived table:

~~~sql
SELECT
    summary.customer_id,
    summary.revenue
FROM (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
) AS summary
WHERE summary.revenue >= 5000;
~~~

Equivalent CTE:

~~~sql
WITH summary AS (
    SELECT
        customer_id,
        SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
)
SELECT
    summary.customer_id,
    summary.revenue
FROM summary
WHERE summary.revenue >= 5000;
~~~

### 6.1. When to Use a Derived Table

Derived tables fit well when:
- The intermediate set is used only once.
- The logic sits right next to the `JOIN` consuming it.
- The query is concise and alias names remain clear.
- You need compatibility with MySQL 5.7 or earlier, where CTEs are unsupported.

### 6.2. When to Use a CTE

CTEs fit well when:
- The query has multiple stages and each stage benefits from a clear name.
- One logical set must be referenced multiple times in the same statement.
- You want to separate data preparation from the final `SELECT`.
- You need a recursive CTE for hierarchies or relationship chains.

Multi-step example:

~~~sql
WITH paid_orders AS (
    SELECT customer_id, total_amount, created_at
    FROM orders
    WHERE status = 'PAID'
),
customer_summary AS (
    SELECT
        customer_id,
        COUNT(*) AS paid_order_count,
        SUM(total_amount) AS paid_revenue
    FROM paid_orders
    GROUP BY customer_id
),
ranked_customers AS (
    SELECT
        customer_id,
        paid_order_count,
        paid_revenue,
        DENSE_RANK() OVER (ORDER BY paid_revenue DESC) AS revenue_rank
    FROM customer_summary
)
SELECT
    customer_id,
    paid_order_count,
    paid_revenue,
    revenue_rank
FROM ranked_customers
WHERE revenue_rank <= 10
ORDER BY revenue_rank, customer_id;
~~~

CTEs clarify each stage: filtering paid orders, aggregating by customer, ranking, and selecting the top group. CTEs are not inherently faster than derived tables; the optimizer can merge or materialize either depending on structure.

### 6.3. CTEs Can Be Referenced Multiple Times

~~~sql
WITH customer_totals AS (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
)
SELECT
    (SELECT COUNT(*) FROM customer_totals) AS customer_count,
    (SELECT SUM(revenue) FROM customer_totals) AS total_revenue;
~~~

CTEs avoid repeating the same query definition inside one statement. Still, inspect the execution plan to see how MySQL handles the CTE and whether it materializes it.

## 7. Derived Tables and Correlated Subqueries

A standard derived table in `FROM` cannot directly reference an outer table alias at the same level. It is an independent query unless declared `LATERAL`.

The following example is invalid in MySQL because the derived table references `c.customer_id` without `LATERAL`:

~~~sql
SELECT
    c.customer_id,
    recent.order_id
FROM customer AS c
JOIN (
    SELECT order_id
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC
    LIMIT 1
) AS recent;
~~~

To let a subquery in `FROM` reference preceding tables, MySQL supports `LATERAL` derived tables starting in MySQL 8.0.14.

### 7.1. LATERAL Derived Tables

~~~sql
SELECT
    c.customer_id,
    recent.order_id,
    recent.created_at
FROM customer AS c
LEFT JOIN LATERAL (
    SELECT
        o.order_id,
        o.created_at
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 1
) AS recent ON TRUE;
~~~

`LATERAL` allows the derived table to reference `c.customer_id` from the current row of `customer`. For each customer, the subquery finds the newest order and limits to one row.

- `LEFT JOIN LATERAL` preserves customers without orders; `recent` columns will be `NULL`.
- `CROSS JOIN LATERAL` retains only customers for whom the derived table returns a row.
- `ORDER BY` includes `order_id` as a tie-breaker for deterministic selection when timestamps match.

This is a useful pattern for top-N per group. However, it can invoke the subquery repeatedly per left-hand row; provide an appropriate index such as `(customer_id, created_at, order_id)` and verify with `EXPLAIN ANALYZE` on realistic data.

### 7.2. Comparing with a Correlated Subquery in SELECT

Another way to fetch the newest order timestamp:

~~~sql
SELECT
    c.customer_id,
    (
        SELECT MAX(o.created_at)
        FROM orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS latest_order_at
FROM customer AS c;
~~~

This is a scalar correlated subquery in the `SELECT` list. It returns a single value per `customer` row. A `LATERAL` derived table can return multiple columns and multiple rows, whereas a scalar subquery must return a single value (returning multiple rows raises an error in MySQL).

Choose the construct based on how much data you need to return and the execution plan.

## 8. Derived Tables and Ordering

Never assume a derived table preserves the row order of its inner query. SQL guarantees final output order only when the outermost `SELECT` has an `ORDER BY`.

Example:

~~~sql
SELECT *
FROM (
    SELECT order_id, created_at
    FROM orders
    ORDER BY created_at DESC
) AS ordered_orders;
~~~

Do not rely on an inner `ORDER BY` to guarantee the outer query's output order. The optimizer may discard an `ORDER BY` inside a derived table if that order does not affect query semantics.

When the goal is selecting a top-N subset, `ORDER BY` must accompany `LIMIT` inside the subquery:

~~~sql
SELECT *
FROM (
    SELECT order_id, created_at
    FROM orders
    ORDER BY created_at DESC, order_id DESC
    LIMIT 10
) AS latest_orders
ORDER BY latest_orders.created_at DESC, latest_orders.order_id DESC;
~~~

`LIMIT` makes the inner ordering meaningful for choosing which rows belong in the subset. The outermost `ORDER BY` is still required to guarantee final presentation order.

## 9. Derived Tables and LIMIT, DISTINCT, GROUP BY

Certain clauses change how the optimizer handles a derived table. Example:

~~~sql
SELECT *
FROM (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
) AS customer_summary
WHERE revenue >= 1000;
~~~

`GROUP BY` produces one row per group, giving the result set its own aggregate semantics. MySQL cannot simply flatten away `GROUP BY` as it might with a plain filter query.

Features such as `DISTINCT`, `GROUP BY`, `HAVING`, `LIMIT`, `UNION`, window functions, and aggregate functions can prevent a derived table from being merged into the outer query, causing MySQL to materialize the result or use another optimization strategy.

Do not guess the exact strategy from syntax alone. Use `EXPLAIN` to inspect whether the query materializes.

## 10. How MySQL Optimizes Derived Tables: Merge and Materialization

MySQL handles derived tables in two primary ways:

1. **Merge:** folds the subquery into the outer query block so the optimizer can optimize it as one unified query.
2. **Materialization:** executes the subquery and stores its output in an internal temporary table for the outer query to read.

### 10.1. Merging Derived Tables

Example:

~~~sql
SELECT
    d.customer_id,
    d.customer_name
FROM (
    SELECT customer_id, customer_name
    FROM customer
) AS d
WHERE d.customer_id = 10;
~~~

The derived table has no aggregation or special restrictions. The optimizer can merge it, making it logically equivalent to:

~~~sql
SELECT customer_id, customer_name
FROM customer
WHERE customer_id = 10;
~~~

When merged, predicates from the outer query can push down onto the base table, enabling index usage and avoiding an unnecessary temporary table.

### 10.2. Materializing Derived Tables

Example with `GROUP BY`:

~~~sql
SELECT
    d.customer_id,
    d.revenue
FROM (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
) AS d
WHERE d.revenue >= 5000;
~~~

The aggregated output can be materialized for the outer query to read. MySQL may automatically create an internal index on the temporary table if doing so improves access efficiency.

Materialization is not inherently bad. When an intermediate set is heavily aggregated, has far fewer rows than the base table, or is accessed multiple times, storing the intermediate result can make sense.

### 10.3. Constructs That Prevent Merging

The following constructs typically prevent a derived table from being merged:

- Aggregate functions such as `SUM`, `COUNT`, `AVG`, `MIN`, `MAX`.
- `DISTINCT`.
- `GROUP BY`.
- `HAVING`.
- `LIMIT`.
- `UNION` or `UNION ALL`.
- Window functions.
- Subqueries in the derived table's `SELECT` list.
- Certain user-defined variable assignments.

Optimization eligibility rules can evolve across MySQL versions. Consult the manual for your running version if you rely on a specific optimization rule.

### 10.4. MERGE and NO_MERGE Hints

MySQL provides optimizer hints to suggest merging or not merging a derived table or CTE where applicable.

~~~sql
SELECT /*+ NO_MERGE(d) */
    d.customer_id,
    d.revenue
FROM (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
) AS d;
~~~

Or:

~~~sql
SELECT /*+ MERGE(d) */
    d.customer_id,
    d.customer_name
FROM (
    SELECT customer_id, customer_name
    FROM customer
) AS d;
~~~

Hints do not guarantee MySQL will follow your preference in every case. Certain constructs cannot be merged semantically, and the optimizer ignores inapplicable hints. Never add hints before measuring; compare plans and execution times first.

## 11. Derived Condition Pushdown

In certain cases, MySQL can push predicates from the outer query down into a derived table to reduce the number of rows processed. This technique is called derived condition pushdown.

Example:

~~~sql
SELECT *
FROM (
    SELECT
        customer_id,
        status,
        SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id, status
) AS d
WHERE d.customer_id = 10;
~~~

The predicate `customer_id = 10` can be pushed down before the `GROUP BY` step because `customer_id` is a grouping column. MySQL can then aggregate orders solely for customer 10 rather than for all customers.

Predicates on aggregate outputs such as `revenue >= 5000` can be pushed down into `HAVING` rather than `WHERE`, since they depend on post-aggregation values.

Derived condition pushdown has been enhanced across MySQL 8.0 releases; exact support and eligibility depend on version and query shape. Inspect optimizer trace or `EXPLAIN` when verifying.

Not every predicate can be pushed down. Conditions containing incompatible expressions, depending on aggregated values, or altering `LIMIT`/outer-join semantics may not be pushed down.

## 12. Reading EXPLAIN for Derived Tables

`EXPLAIN` reveals whether MySQL plans to access base tables directly, merge, or materialize a derived table.

Example:

~~~sql
EXPLAIN
SELECT
    d.customer_id,
    d.revenue
FROM (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
) AS d
WHERE d.revenue >= 5000;
~~~

You can also view tree format:

~~~sql
EXPLAIN FORMAT=TREE
SELECT
    d.customer_id,
    d.revenue
FROM (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
) AS d
WHERE d.revenue >= 5000;
~~~

Signals to watch for in `EXPLAIN`:

- Whether a `Materialize` or `Materialize with deduplication` step appears.
- Whether the derived table is merged.
- Which access type the source table uses.
- Which index is chosen.
- Estimated row counts at each step.
- Whether a temporary table or filesort occurs.

In MySQL 8.0, `EXPLAIN ANALYZE` executes the `SELECT` statement and reports actual iterator timings and row counts:

~~~sql
EXPLAIN ANALYZE
SELECT
    d.customer_id,
    d.revenue
FROM (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
) AS d
WHERE d.revenue >= 5000;
~~~

`EXPLAIN ANALYZE` actually runs the query. Use it in appropriate environments and avoid running unvetted heavy queries directly on production.

## 13. Optimizing Multi-Step Queries

### 13.1. Project Only Needed Columns

Do not use `SELECT *` inside a derived table if the outer query needs only a few columns:

~~~sql
SELECT d.customer_id, d.revenue
FROM (
    SELECT *
    FROM orders
) AS d;
~~~

Instead write:

~~~sql
SELECT d.customer_id, d.revenue
FROM (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
) AS d;
~~~

Selecting only required columns shrinks intermediate row size, increases covering-index opportunities, and clarifies the contract between steps.

### 13.2. Filter Early When Semantics Remain Unchanged

~~~sql
SELECT d.customer_id, d.revenue
FROM (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    WHERE status = 'PAID'
      AND created_at >= '2025-01-01'
    GROUP BY customer_id
) AS d;
~~~

Filtering unnecessary rows before aggregating reduces the volume of data processed. However, never move an outer predicate inside if doing so alters the semantics of `GROUP BY`, `LIMIT`, outer joins, or aggregate outputs.

### 13.3. Indexing Base Tables

If a query filters by `status` and a date range, then groups by `customer_id`, evaluate indexes such as:

~~~sql
CREATE INDEX idx_orders_status_created_customer
ON orders (status, created_at, customer_id);
~~~

There is no single index column order right for every workload. Base it on filter predicates, cardinality, grouping order, projected columns, and write overhead. `EXPLAIN` verifies whether the optimizer uses the index as intended.

### 13.4. Avoid Repeating the Same Aggregation

If the same aggregated set is referenced multiple times within one statement, consider a CTE or named derived table to avoid duplicating definitions. Keep in mind that CTEs/derived tables may be materialized or merged depending on optimizer strategy. Never assume writing it once automatically means computing it once; inspect the plan.

### 13.5. Do Not Use a Derived Table Merely to Rename Columns

This query:

~~~sql
SELECT d.customer_id
FROM (
    SELECT customer_id
    FROM customer
) AS d;
~~~

adds no meaningful organizational value. Without filtering, grouping, computation, or a needed logical boundary, a direct query is simpler.

## 14. Derived Tables with Window Functions

Window functions compute values across a window of rows while keeping detail rows intact. Derived tables allow filtering window outputs in the outer query, because window aliases cannot be referenced directly in the `WHERE` clause of the same query block.

Example retrieving the top three highest-value orders per customer:

~~~sql
SELECT
    ranked_orders.customer_id,
    ranked_orders.order_id,
    ranked_orders.total_amount,
    ranked_orders.order_rank
FROM (
    SELECT
        customer_id,
        order_id,
        total_amount,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY total_amount DESC, order_id DESC
        ) AS order_rank
    FROM orders
) AS ranked_orders
WHERE ranked_orders.order_rank <= 3
ORDER BY
    ranked_orders.customer_id,
    ranked_orders.order_rank;
~~~

The inner step assigns a rank to each order within a customer's partition. The outer step filters ranks 1 through 3.

MySQL 8.0 supports window functions. If MySQL 5.7 compatibility is required, use alternatives such as correlated subqueries, anti-joins, or appropriate aggregate queries.

## 15. LATERAL Derived Tables and Top-N per Row

MySQL 8.0.14 and later support `LATERAL` derived tables. This allows a derived table to reference tables appearing before it in the `FROM` clause.

Example fetching the two most recent payments for each order:

~~~sql
SELECT
    o.order_id,
    recent.payment_id,
    recent.paid_at,
    recent.amount
FROM orders AS o
LEFT JOIN LATERAL (
    SELECT
        p.payment_id,
        p.paid_at,
        p.amount
    FROM payment AS p
    WHERE p.order_id = o.order_id
    ORDER BY p.paid_at DESC, p.payment_id DESC
    LIMIT 2
) AS recent ON TRUE
WHERE o.created_at >= '2025-01-01'
ORDER BY o.order_id, recent.paid_at DESC;
~~~

The `LATERAL` derived table can read `o.order_id` and return at most two payment rows per order. `LEFT JOIN` preserves orders that have no payments yet.

Index worth evaluating:

~~~sql
CREATE INDEX idx_payment_order_paid
ON payment (order_id, paid_at, payment_id);
~~~

When there are many orders, the subquery can execute per order row. An index on `order_id` and payment timestamp helps locate related rows and fetch the top-N quickly. Verify with `EXPLAIN ANALYZE` before deploying at scale.

## 16. Common Mistakes

| Error or Misconception | Cause | Fix |
|---|---|---|
| Derived table triggers a syntax error | Missing alias after the closing parenthesis | Supply an alias for every derived table |
| Outer query cannot find a column | Column was not projected in the subquery `SELECT` | Expose needed columns from the derived table |
| Ambiguous column error | Multiple sources share a column name | Use table aliases and qualified column names |
| Inner table alias unusable in outer query | Alias is scoped only to the inner query block | Reference the derived table alias and its exported column |
| `SELECT` alias unusable in `WHERE` at the same level | `WHERE` runs before the `SELECT` list | Use a derived table/CTE or repeat the appropriate predicate |
| Derived table referencing an outer table errors | Non-`LATERAL` derived table | Use `LATERAL` on MySQL 8.0.14+ when appropriate |
| Inner `ORDER BY` fails to preserve output order | Only the outermost `ORDER BY` guarantees final order | Put `ORDER BY` on the outermost `SELECT` |
| `LEFT JOIN` drops unmatched rows | Right-side predicate placed in `WHERE` | Consider placing match-restricting predicates in `ON` |
| Joining two detail tables inflates `SUM` | Fan-out from one-to-many relationships | Pre-aggregate each source before joining |
| Derived table consumes excessive resources | Materializing a large intermediate set | Filter early, prune columns, check merge/indexes |
| `LIMIT` returns unstable results | `ORDER BY` lacks a unique tie-breaker | Add a unique key to `ORDER BY` |
| Trying to force optimizer to merge an unmergeable query | Contains `GROUP BY`, `LIMIT`, or merge-blocking features | Understand merge rules; do not rely blindly on hints |

## 17. Workflow for Organizing a Multi-Step Query

When a query begins accumulating multiple JOINs, aggregations, and calculations, follow this sequence:

1. Define which columns the final result needs and what entity each row represents.
2. Break the query into logical steps: source filtering, aggregation, joining, classification, ranking.
3. Choose a derived table if the intermediate set is used in one place; choose a CTE if named stages or reuse are helpful.
4. Give meaningful aliases to tables, derived tables, and columns.
5. Verify each derived table returns the expected single row per key expected by the outer query.
6. Check cardinality before joining to avoid row multiplication.
7. Export only needed columns and filter early when semantics are unaffected.
8. If a derived table must reference a preceding outer table, decide between `LATERAL` and a correlated subquery.
9. Place `ORDER BY` on the query block guaranteeing the ordering required by business logic.
10. Inspect merge/materialization, indexes, and row estimates via `EXPLAIN`.
11. Test edge cases: zero matching rows, ties, `NULL`s, and empty groups.
12. Cross-check results against an independent verification query before shipping to the application.

## 18. Hands-On Exercises

### Exercise 1: Aggregate Then Filter

Create an `orders` table with `customer_id` and `total_amount`. Write a derived table calculating total spend per customer, then keep only customers with revenue of at least 5,000. Rewrite it using `GROUP BY`/`HAVING` and compare.

### Exercise 2: Aliases and Column Scope

Write a query joining `customer` with `orders` inside a derived table. Alias `customer_id`, `order_id`, and `revenue`. Try removing one column from the inner `SELECT` and referencing it outside to observe the error.

### Exercise 3: Pre-Aggregating Before Joining

A customer has multiple orders and multiple payments. Write a query joining both detail tables directly and observe row multiplication. Then aggregate `orders` and `payment` separately by `customer_id` and join the two derived tables.

### Exercise 4: LEFT JOIN and Condition Placement

Write two queries performing a `LEFT JOIN` to a derived table: one placing the revenue threshold in `ON`, and one placing it in `WHERE`. Compare customers without orders and explain the difference.

### Exercise 5: Derived Table vs. CTE

Write the same report using a derived table and a CTE. Compare readability, logical steps, and `EXPLAIN`. Describe when each approach is preferable.

### Exercise 6: Fetching the Latest Order

Use a derived table to find `MAX(created_at)` per customer and join back to `orders`. Insert two orders sharing the exact same latest `created_at` to observe multiple returned rows. Then use `ROW_NUMBER()` with `order_id` as a tie-breaker.

### Exercise 7: LATERAL Top-N

On MySQL 8.0.14+, use `LEFT JOIN LATERAL` to fetch the two most recent orders per customer. Add a suitable index and inspect `EXPLAIN ANALYZE`. Try dropping the index to compare.

### Exercise 8: Merge and Materialization

Write one derived table that merely selects columns from `customer` and one derived table with `GROUP BY`. Use `EXPLAIN FORMAT=TREE` to observe the difference. Try `MERGE`/`NO_MERGE` hints where appropriate and note whether the optimizer applies them.

### Exercise 9: Filtering and Limiting

Create a derived table picking the 10 newest orders using `ORDER BY`/`LIMIT`. Have the outer query filter or sort further. Inspect `ORDER BY` placement and explain why final presentation order must be declared in the outer query block.

## 19. Pre-Application Checklist for Derived Tables

- [ ] Every derived table has an alias.
- [ ] Exported columns from the subquery suffice for outer steps.
- [ ] Column names inside each derived table are unique.
- [ ] Table and column aliases are clear and meaningful.
- [ ] Alias scoping is understood for each query block.
- [ ] Verified how many rows each derived table emits per key.
- [ ] Avoided fan-out when joining multiple one-to-many sources.
- [ ] Verified whether predicates belong in `ON` or `WHERE`.
- [ ] Used `LATERAL` only when referencing a preceding table and supported by the server.
- [ ] Placed `ORDER BY` in the outer query if final result ordering is required.
- [ ] Used a unique tie-breaker with `LIMIT` or top-N queries.
- [ ] Chose between derived table and CTE based on complexity and reuse.
- [ ] Checked merge/materialization and derived condition pushdown via `EXPLAIN`.
- [ ] Filtered early, pruned columns, and evaluated base-table indexes.
- [ ] Tested empty sets, `NULL`s, tied ranks, and unmatched relationships.

## 20. Conclusion

A derived table is a subquery in the `FROM` clause, named with an alias, supplying a row set to the outer query. It organizes SQL into clear stages: filtering, aggregating, classifying, joining, and ranking. A derived table alias is mandatory, and the outer query sees only the columns exported by the subquery.

During design, control alias scope, enforce unique column names, verify cardinality before joining, and never rely on an inner subquery's ordering to guarantee final output order. MySQL can merge a derived table or materialize its output; `LATERAL` allows referencing preceding tables starting in MySQL 8.0.14. Choose the structure for clarity first, then inspect `EXPLAIN` and realistic data to evaluate performance.

## Official References

- [MySQL 8.4 Reference Manual – Derived Tables](https://dev.mysql.com/doc/refman/8.4/en/derived-tables.html)
- [MySQL 8.4 Reference Manual – Lateral Derived Tables](https://dev.mysql.com/doc/refman/8.4/en/lateral-derived-tables.html)
- [MySQL 8.4 Reference Manual – Optimizing Derived Tables, View References, and CTEs](https://dev.mysql.com/doc/refman/8.4/en/derived-table-optimization.html)
- [MySQL 8.4 Reference Manual – Derived Condition Pushdown Optimization](https://dev.mysql.com/doc/refman/8.4/en/derived-condition-pushdown-optimization.html)
- [MySQL 8.4 Reference Manual – WITH (Common Table Expressions)](https://dev.mysql.com/doc/refman/8.4/en/with.html)
- [MySQL 8.4 Reference Manual – Window Function Descriptions](https://dev.mysql.com/doc/refman/8.4/en/window-function-descriptions.html)
- [MySQL 8.4 Reference Manual – JOIN Clause](https://dev.mysql.com/doc/refman/8.4/en/join.html)
- [MySQL 8.4 Reference Manual – EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)
- [MySQL 8.4 Reference Manual – Optimizer Hints](https://dev.mysql.com/doc/refman/8.4/en/optimizer-hints.html)
