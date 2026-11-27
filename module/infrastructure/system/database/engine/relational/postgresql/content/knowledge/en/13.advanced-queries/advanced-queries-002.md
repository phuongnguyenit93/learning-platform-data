# WITH and Query Organization Using CTEs in PostgreSQL

A SQL query does not always consist of just one table, one `JOIN`, and one `WHERE` condition. In real-world reporting, we often need multiple steps: fetch completed orders, compute line-item totals, aggregate by customer, select high-revenue customers, and finally format the result for the application. Trying to cram everything into a deeply nested `SELECT` may still run, but it becomes very hard to read, verify, and modify.

PostgreSQL supports **Common Table Expressions (CTEs)** via the `WITH` clause. A CTE lets you name an intermediate result within the scope of **a single SQL statement**, so each step can be presented as a clear sub-problem. When traversing hierarchical data (department trees, parent–child categories, graph paths), PostgreSQL also provides `WITH RECURSIVE`.

Quick example:

```sql
WITH completed_orders AS (
    SELECT order_id, customer_id
    FROM cte_lab.orders
    WHERE status = 'completed'
),
order_totals AS (
    SELECT
        o.customer_id,
        o.order_id,
        SUM(i.quantity * i.unit_price) AS total_amount
    FROM completed_orders AS o
    JOIN cte_lab.order_items AS i
        ON i.order_id = o.order_id
    GROUP BY o.customer_id, o.order_id
)
SELECT
    customer_id,
    COUNT(*) AS completed_order_count,
    SUM(total_amount) AS completed_revenue
FROM order_totals
GROUP BY customer_id
ORDER BY completed_revenue DESC, customer_id;
```

The two names `completed_orders` and `order_totals` immediately show the two processing stages. However, **a CTE is not automatically a temporary table written to disk**, nor does it automatically make a SQL query faster. PostgreSQL may fold the CTE into the parent plan or materialize its result depending on version, properties, and reference count. This is a crucial point when using CTEs for advanced queries.

After this lesson, you will know how to:

1. Write standard CTEs, name output columns, and compose multiple CTEs in dependency order.
2. Distinguish CTEs from subqueries, views, temporary tables, and transactions.
3. Use CTEs to structure filtering, `JOIN`s, aggregates, window functions, and parameterized SQL.
4. Explain *folding/inlining* and *materialization* since PostgreSQL 12, and intentionally use `MATERIALIZED`/`NOT MATERIALIZED`.
5. Write safe `WITH RECURSIVE` queries for hierarchical data and graphs with cycles.
6. Understand `SEARCH`/`CYCLE` (PostgreSQL 14+), recursion termination mechanisms, and result ordering.
7. Use `WITH` in `INSERT`, `UPDATE`, `DELETE`, and `MERGE` where supported; understand the limits of data-modifying CTEs via `RETURNING`.
8. Verify results and read `EXPLAIN (ANALYZE, BUFFERS)` before optimizing.

The examples target modern PostgreSQL; minimum major versions are noted for specific features. Check your server version before applying them to a running project.

## 1. Concept of a CTE: Naming Intermediate Results

A CTE is an auxiliary query declared with `WITH` and referenced in the main statement as a named row source.

Basic structure:

```sql
WITH cte_name AS (
    SELECT ...
)
SELECT ...
FROM cte_name;
```

In the syntax sketch above, `...` marks where valid SQL goes. `cte_name` exists only within the **scope of the statement** containing `WITH`.

Standalone runnable example without creating any table:

```sql
WITH numbers AS (
    SELECT 10 AS a, 20 AS b
)
SELECT
    a,
    b,
    a + b AS total
FROM numbers;
```

Result:

| a | b | total |
| ---: | ---: | ---: |
| 10 | 20 | 30 |

This is not a `CREATE TABLE numbers` statement. Once `SELECT` finishes, a subsequent statement like `SELECT * FROM numbers;` will not find that CTE, unless an actual table or view with that name exists in the resolution scope.

### 1.1. Why name the steps?

When a problem involves multiple transformations, we can express it as:

```text
orders + order_items
          |
          v
    order_totals
          |
          v
  completed_totals
          |
          v
   customer_revenue
          |
          v
     SELECT result
```

Each CTE is a way to name an intermediate result to express **intent**, helping to:

- Read the SQL through clearly named small parts.
- Avoid repeating a long expression within one query level.
- Separate filtering, joining, grouping, and presentation logic.
- Easily extract a step as a standalone query for verification.
- Reuse a CTE multiple times within the same statement when genuinely needed.

However, a CTE **does not create a persistent data contract**. A CTE definition is not stored like a view and is not shared across two separate SQL statements.

## 2. Preparing the Practice Dataset

To make examples runnable without depending on previous lessons, we create the `cte_lab` schema with customers, orders, order items, a category tree, a graph, and job tables.

**Note:** only run DDL/DML on an authorized lab database. The data creation statements only need to be run once; re-running `INSERT` with the same primary keys will cause duplicate-key errors.

### 2.1. Customers, orders, and order items

```sql
CREATE SCHEMA IF NOT EXISTS cte_lab;

CREATE TABLE cte_lab.customers (
    customer_id bigint PRIMARY KEY,
    customer_name text NOT NULL,
    region text
);

CREATE TABLE cte_lab.orders (
    order_id bigint PRIMARY KEY,
    customer_id bigint NOT NULL
        REFERENCES cte_lab.customers(customer_id),
    ordered_at date NOT NULL,
    status text NOT NULL
        CHECK (status IN ('completed', 'pending', 'cancelled'))
);

CREATE TABLE cte_lab.order_items (
    order_id bigint NOT NULL
        REFERENCES cte_lab.orders(order_id),
    line_no integer NOT NULL CHECK (line_no > 0),
    product_code text NOT NULL,
    quantity integer NOT NULL CHECK (quantity > 0),
    unit_price numeric(12, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no)
);
```

Insert sample data:

```sql
INSERT INTO cte_lab.customers
    (customer_id, customer_name, region)
VALUES
    (1, 'An', 'Bac'),
    (2, 'Binh', 'Nam'),
    (3, 'Chi', 'Nam'),
    (4, 'Dung', NULL);

INSERT INTO cte_lab.orders
    (order_id, customer_id, ordered_at, status)
VALUES
    (1001, 1, DATE '2026-10-01', 'completed'),
    (1002, 1, DATE '2026-10-02', 'pending'),
    (1003, 2, DATE '2026-10-03', 'completed'),
    (1004, 3, DATE '2026-11-01', 'completed'),
    (1005, 2, DATE '2026-11-02', 'cancelled');

INSERT INTO cte_lab.order_items
    (order_id, line_no, product_code, quantity, unit_price)
VALUES
    (1001, 1, 'BOOK-SQL', 2, 100.00),
    (1001, 2, 'NOTE-A5',  1,  50.00),
    (1002, 1, 'PEN-BLUE', 3,  30.00),
    (1003, 1, 'BOOK-PG',  1, 300.00),
    (1004, 1, 'MUG-01',  4,  25.00),
    (1005, 1, 'BAG-01',  1,  80.00);
```

Reference table of totals per order:

| order_id | customer_id | status | total from items |
| ---: | ---: | --- | ---: |
| 1001 | 1 | completed | 250.00 |
| 1002 | 1 | pending | 90.00 |
| 1003 | 2 | completed | 300.00 |
| 1004 | 3 | completed | 100.00 |
| 1005 | 2 | cancelled | 80.00 |

Customer 4 has no orders yet. This is useful for verifying `LEFT JOIN` with aggregated data.

In this lesson, `completed` is used as the reporting condition for finished orders; it is **not a universal accounting revenue definition**. Real systems also need to handle refunds, discounts, taxes, and revenue recognition milestones.

### 2.2. Category tree

```sql
CREATE TABLE cte_lab.categories (
    category_id bigint PRIMARY KEY,
    category_name text NOT NULL,
    parent_id bigint
        REFERENCES cte_lab.categories(category_id)
);

INSERT INTO cte_lab.categories
    (category_id, category_name, parent_id)
VALUES
    (10, 'Products', NULL),
    (11, 'Books', 10),
    (12, 'Accessories', 10),
    (13, 'Tech Books', 11),
    (14, 'Services', NULL),
    (15, 'Training', 14);
```

Diagram:

```text
10 Products
├── 11 Books
│   └── 13 Tech Books
└── 12 Accessories

14 Services
└── 15 Training
```

### 2.3. Graph with cycles

```sql
CREATE TABLE cte_lab.graph_edges (
    from_id bigint NOT NULL,
    to_id bigint NOT NULL,
    PRIMARY KEY (from_id, to_id)
);

INSERT INTO cte_lab.graph_edges (from_id, to_id)
VALUES
    (1, 2),
    (2, 3),
    (3, 1),
    (1, 4),
    (4, 5);
```

The graph has a cycle `1 → 2 → 3 → 1` and a branch `1 → 4 → 5`. This helps explain why a recursive CTE without a proper stopping condition can produce unbounded output.

## 3. A Simple CTE for Filtering Data

Requirement: retrieve completed orders, including ID, customer name, and order date.

```sql
WITH completed_orders AS (
    SELECT
        order_id,
        customer_id,
        ordered_at
    FROM cte_lab.orders
    WHERE status = 'completed'
)
SELECT
    o.order_id,
    c.customer_name,
    o.ordered_at
FROM completed_orders AS o
JOIN cte_lab.customers AS c
    ON c.customer_id = o.customer_id
ORDER BY o.order_id;
```

Result:

| order_id | customer_name | ordered_at |
| ---: | --- | --- |
| 1001 | An | 2026-10-01 |
| 1003 | Binh | 2026-10-03 |
| 1004 | Chi | 2026-11-01 |

`completed_orders` acts like a row source with columns `order_id`, `customer_id`, and `ordered_at` in the final `SELECT`.

### 3.1. CTE name vs. table alias

```sql
WITH completed_orders AS (
    SELECT order_id, customer_id
    FROM cte_lab.orders
    WHERE status = 'completed'
)
SELECT o.order_id
FROM completed_orders AS o
ORDER BY o.order_id;
```

Here:

- `completed_orders` is the CTE name.
- `o` is the alias for that CTE source in `FROM`.
- `o.order_id` is an output column of the CTE, not necessarily preserving positions from the underlying table.

Both CTEs and table aliases provide names in SQL, but they play different roles. A CTE holds a **query definition**; a table alias assigns a **reference name for one usage of a source** within a query block.

## 4. Specifying a Column Name List for a CTE

You can specify output column names right after the CTE name:

```sql
WITH sample_metrics(metric_name, metric_value) AS (
    SELECT 'orders'::text, COUNT(*)::numeric
    FROM cte_lab.orders
)
SELECT metric_name, metric_value
FROM sample_metrics;
```

Single-row result:

| metric_name | metric_value |
| --- | ---: |
| orders | 5 |

The list `(metric_name, metric_value)` assigns **column names** to the CTE result by position. This is helpful when:

- Expressions inside the CTE lack clear aliases.
- You want to declare the column interface right at the CTE header.
- You need readable column names for a recursive CTE.

However, if the column name list does not match the meaning of the expressions, SQL will still run and produce confusing output. Column names do not alter the **order or values** produced by the inner `SELECT`.

Example:

```sql
WITH n(x, y) AS (
    SELECT 5, 9
)
SELECT x, y, x + y AS total
FROM n;
```

Returns `x=5`, `y=9`, `total=14`.

## 5. Multiple CTEs: Breaking a Problem into Steps

CTEs are very helpful when multiple dependent transformation steps are required. CTEs are separated by commas:

```sql
WITH
completed_orders AS (
    SELECT order_id, customer_id
    FROM cte_lab.orders
    WHERE status = 'completed'
),
order_totals AS (
    SELECT
        co.order_id,
        co.customer_id,
        SUM(i.quantity * i.unit_price) AS total_amount
    FROM completed_orders AS co
    JOIN cte_lab.order_items AS i
        ON i.order_id = co.order_id
    GROUP BY co.order_id, co.customer_id
),
customer_revenue AS (
    SELECT
        customer_id,
        COUNT(*) AS order_count,
        SUM(total_amount) AS revenue
    FROM order_totals
    GROUP BY customer_id
)
SELECT
    c.customer_id,
    c.customer_name,
    cr.order_count,
    cr.revenue
FROM customer_revenue AS cr
JOIN cte_lab.customers AS c
    ON c.customer_id = cr.customer_id
ORDER BY cr.revenue DESC, c.customer_id;
```

Result:

| customer_id | customer_name | order_count | revenue |
| ---: | --- | ---: | ---: |
| 2 | Binh | 1 | 300.00 |
| 1 | An | 1 | 250.00 |
| 3 | Chi | 1 | 100.00 |

Customer Dung has no orders and therefore no row in `customer_revenue`; if business logic requires **every customer with 0 revenue**, you must reverse the JOIN direction in the final query (Section 7).

### 5.1. Reading the dependency chain top-down

```text
completed_orders
       |
       v
  order_totals
       |
       v
customer_revenue ---- customers
       |                  |
       +-------- JOIN ----+
                  |
                  v
                result
```

In a non-recursive `WITH`, an earlier CTE can be referenced by subsequent CTEs in valid order. You cannot arbitrarily create circular references between two CTEs and expect PostgreSQL to infer recursion; when recursion is needed, you must use `WITH RECURSIVE` and follow its rules.

### 5.2. Do not over-split just because WITH is available

A CTE that merely writes `SELECT * FROM table` without clarifying intent sometimes only inflates SQL line count. An effective structure gives each CTE a **distinct semantic step**: filtering valid rows, computing per-order totals, aggregating by customer, ranking, or classifying.

From the name `customer_revenue`, a reader should immediately know that one row represents revenue **for one customer**, without having to read 40 lines of SQL to guess.

## 6. CTEs vs. Subqueries: Same Problem, Different Presentation

A subquery in `FROM` can also create a row source:

```sql
SELECT
    t.order_id,
    t.total_amount
FROM (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS total_amount
    FROM cte_lab.order_items
    GROUP BY order_id
) AS t
WHERE t.total_amount >= 100
ORDER BY t.order_id;
```

Written with a CTE:

```sql
WITH totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS total_amount
    FROM cte_lab.order_items
    GROUP BY order_id
)
SELECT order_id, total_amount
FROM totals
WHERE total_amount >= 100
ORDER BY order_id;
```

Both express the exact same requirement on this dataset:

| order_id | total_amount |
| ---: | ---: |
| 1001 | 250.00 |
| 1003 | 300.00 |
| 1004 | 100.00 |

### 6.1. Comparison table

| Aspect | CTE with WITH | Derived table in FROM |
| --- | --- | --- |
| Scope | One statement containing `WITH`. | One query level containing the subquery. |
| Naming processing steps | Clear, grouped at the top of the statement. | Named after the subquery in `FROM`. |
| Reusing in multiple places in one statement | Reference the same CTE name multiple times. | Often requires repeating or restructuring the subquery. |
| Recursion | Supported by `WITH RECURSIVE`. | Regular derived tables cannot reference themselves recursively. |
| Performance | Depends on optimizer/materialization. | Depends on optimizer and optimization conditions. |

There is no general rule that a CTE is **always** faster or slower than a subquery. SQL structure, reference count, function types, and PostgreSQL version can all produce different plans.

## 7. Combining CTEs with LEFT JOIN to Keep Unmatched Rows

Requirement: show **all customers**, including those with no completed orders, with 0 revenue.

```sql
WITH completed_totals AS (
    SELECT
        o.customer_id,
        SUM(i.quantity * i.unit_price) AS completed_revenue
    FROM cte_lab.orders AS o
    JOIN cte_lab.order_items AS i
        ON i.order_id = o.order_id
    WHERE o.status = 'completed'
    GROUP BY o.customer_id
)
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(t.completed_revenue, 0) AS completed_revenue
FROM cte_lab.customers AS c
LEFT JOIN completed_totals AS t
    ON t.customer_id = c.customer_id
ORDER BY c.customer_id;
```

Result:

| customer_id | customer_name | completed_revenue |
| ---: | --- | ---: |
| 1 | An | 250.00 |
| 2 | Binh | 300.00 |
| 3 | Chi | 100.00 |
| 4 | Dung | 0 |

Key takeaways:

- The CTE `completed_totals` has **one row per customer_id with completed orders and matching items**.
- `customers LEFT JOIN completed_totals` retains every customer.
- Customer Dung has no right-hand row, so `completed_revenue` on the right is SQL NULL.
- `COALESCE(..., 0)` only converts it to 0 in the **displayed result**, without creating a row inside the CTE.

If a completed order has no line items, the current CTE using `JOIN` will **omit that order**. If requirements dictate counting itemless orders, you need to `LEFT JOIN` `order_items` and define the amount formula for empty orders. This illustrates why CTEs help **layer meaning**, but do not automatically make a query right if JOIN conditions are wrong.

### 7.1. COUNT(*) after LEFT JOIN

To count actual orders, do not use `COUNT(*)` on customer rows LEFT JOINed to orders when orders may be missing. Count a `NOT NULL` right-side key such as `o.order_id`:

```sql
SELECT
    c.customer_id,
    COUNT(o.order_id) AS order_count
FROM cte_lab.customers AS c
LEFT JOIN cte_lab.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

The results are `2, 2, 1, 0`. A CTE on the right side can pre-compute one row per customer, reducing the risk of row multiplication in a report combining multiple one-to-many sources.

## 8. CTEs Help Reuse Output Expressions in the Outer Level

In PostgreSQL, an alias defined in `SELECT` cannot be referenced directly in `WHERE` of the **same query level**.

Invalid example:

```sql
-- Wrong intent: total_amount is a SELECT alias at the same level.
-- SELECT order_id,
--        SUM(quantity * unit_price) AS total_amount
-- FROM cte_lab.order_items
-- GROUP BY order_id
-- WHERE total_amount > 100;
```

Besides the alias error, an aggregate `SUM(...)` cannot be placed directly in `WHERE` at the grouping level; simple group filtering cases should use `HAVING`.

Written with a CTE:

```sql
WITH order_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS total_amount
    FROM cte_lab.order_items
    GROUP BY order_id
)
SELECT order_id, total_amount
FROM order_totals
WHERE total_amount > 100
ORDER BY total_amount DESC, order_id;
```

In the outer level, `total_amount` is a **source column of the CTE**, so it can be used in `WHERE`. Results are orders 1003 (300) and 1001 (250).

If the requirement is simply filtering groups with totals over 100, you can also write:

```sql
SELECT
    order_id,
    SUM(quantity * unit_price) AS total_amount
FROM cte_lab.order_items
GROUP BY order_id
HAVING SUM(quantity * unit_price) > 100
ORDER BY total_amount DESC, order_id;
```

A CTE is not the only right way. Pick `HAVING` for short aggregate expressions, or a CTE when the grouped result feeds multiple subsequent steps.

## 9. Combining CTEs with Window Functions

A CTE can produce an aggregated dataset, and then the outer query can use window functions to assign rankings.

Example ranking customers by completed revenue:

```sql
WITH revenue AS (
    SELECT
        o.customer_id,
        SUM(i.quantity * i.unit_price) AS total_revenue
    FROM cte_lab.orders AS o
    JOIN cte_lab.order_items AS i
        ON i.order_id = o.order_id
    WHERE o.status = 'completed'
    GROUP BY o.customer_id
),
ranked AS (
    SELECT
        customer_id,
        total_revenue,
        DENSE_RANK() OVER (
            ORDER BY total_revenue DESC
        ) AS revenue_rank
    FROM revenue
)
SELECT
    c.customer_name,
    r.total_revenue,
    r.revenue_rank
FROM ranked AS r
JOIN cte_lab.customers AS c
    ON c.customer_id = r.customer_id
ORDER BY r.revenue_rank, c.customer_id;
```

On the current data:

| customer_name | total_revenue | revenue_rank |
| --- | ---: | ---: |
| Binh | 300.00 | 1 |
| An | 250.00 | 2 |
| Chi | 100.00 | 3 |

Note that `DENSE_RANK` assigns tied values the same rank without skipping subsequent rank numbers. When exactly one row per group is needed, use an explicit tie-breaking rule or `ROW_NUMBER()` with a deterministic `ORDER BY`, rather than expecting an arbitrary order.

### 9.1. Filtering on window results

You cannot use the alias `revenue_rank` in `WHERE` of the same query level that computes the window function. By placing the ranking in the `ranked` CTE, the outer query can filter on it:

```sql
WITH revenue AS (
    SELECT
        o.customer_id,
        SUM(i.quantity * i.unit_price) AS amount
    FROM cte_lab.orders AS o
    JOIN cte_lab.order_items AS i
        ON i.order_id = o.order_id
    WHERE o.status = 'completed'
    GROUP BY o.customer_id
),
ranked AS (
    SELECT
        customer_id,
        amount,
        ROW_NUMBER() OVER (
            ORDER BY amount DESC, customer_id
        ) AS row_num
    FROM revenue
)
SELECT customer_id, amount, row_num
FROM ranked
WHERE row_num <= 2
ORDER BY row_num;
```

The result returns the top two customers by revenue: Binh and An. This is a useful pattern for `top N` after aggregation and multi-stage ranking reports.

## 10. Referencing the Same CTE Multiple Times

Suppose we need to compare each completed order against the average total of all completed orders.

```sql
WITH completed_totals AS (
    SELECT
        o.order_id,
        SUM(i.quantity * i.unit_price) AS total_amount
    FROM cte_lab.orders AS o
    JOIN cte_lab.order_items AS i
        ON i.order_id = o.order_id
    WHERE o.status = 'completed'
    GROUP BY o.order_id
),
stats AS (
    SELECT AVG(total_amount) AS average_amount
    FROM completed_totals
)
SELECT
    t.order_id,
    t.total_amount,
    s.average_amount,
    t.total_amount > s.average_amount AS above_average
FROM completed_totals AS t
CROSS JOIN stats AS s
ORDER BY t.order_id;
```

The CTE `completed_totals` is referenced in `stats` and in the final query. The SQL is easy to read because the total calculation appears only once.

For performance, PostgreSQL may materialize a CTE referenced multiple times by default, if eligible and on a supported version. Read the `MATERIALIZED` section to understand when computing once is beneficial versus when it blocks pushing filters down to source tables.

## 11. CTEs and the PostgreSQL Optimizer: Not Stored as Temp Tables by Default

This is a key aspect of CTEs in modern PostgreSQL.

Before PostgreSQL 12, a `SELECT` CTE usually acted as an **optimization fence**: PostgreSQL did not automatically fold it into the parent query to optimize across the boundary like many subqueries.

Starting in **PostgreSQL 12**, **non-recursive, side-effect-free `SELECT` CTEs meeting eligibility conditions** can be *folded/inlined* into the parent query. Typical defaults are:

- **CTE referenced once:** PostgreSQL can fold it into the parent query, enabling joint optimization.
- **CTE referenced multiple times:** PostgreSQL typically materializes it to avoid recomputing the result, when eligible.
- **Recursive CTEs or CTEs with side effects:** do not belong to the group that can be freely folded like pure `SELECT` CTEs.

Note: the above describes the general principle; inspect the actual plan with `EXPLAIN`.

### 11.1. Predicate pushdown example

```sql
WITH all_orders AS (
    SELECT *
    FROM cte_lab.orders
)
SELECT order_id, status
FROM all_orders
WHERE order_id = 1003;
```

If PostgreSQL folds the CTE into the parent query, `order_id = 1003` can be optimized as if reading `cte_lab.orders` directly. The primary key index on `order_id` can be considered by the planner.

Do not imagine PostgreSQL is forced to build the entire orders list and only then filter `order_id` just because the syntax uses `WITH`.

### 11.2. MATERIALIZED: requesting a computation boundary

Since PostgreSQL 12:

```sql
WITH all_orders AS MATERIALIZED (
    SELECT *
    FROM cte_lab.orders
)
SELECT order_id, status
FROM all_orders
WHERE order_id = 1003;
```

`MATERIALIZED` tells PostgreSQL not to fold an eligible CTE into the parent query. The CTE is evaluated as an intermediate result set for statement execution. This can be useful to:

- Avoid recomputing an expensive calculation when referenced multiple times.
- Control optimization boundaries when the optimizer chooses an unfavorable plan.
- Preserve single-evaluation semantics for certain eligible `SELECT` logic.

However, it can also force PostgreSQL to process **more rows than necessary** before the outer query's filter is applied.

### 11.3. NOT MATERIALIZED: allowing folding for optimization

```sql
WITH all_orders AS NOT MATERIALIZED (
    SELECT *
    FROM cte_lab.orders
)
SELECT order_id, status
FROM all_orders
WHERE order_id = 1003;
```

`NOT MATERIALIZED` lets PostgreSQL fold an eligible `SELECT` CTE into the parent query even when the CTE is referenced multiple times. This can allow pushing `WHERE` closer to the base table.

Trade-off: if the same CTE contains expensive expressions and is used multiple times, folding may cause the work to be **repeated**. Do not choose `NOT MATERIALIZED` thinking "NOT means definitely faster".

These hints do not turn recursive CTEs or CTEs with volatile functions/side effects into pure expressions that can be arbitrarily folded; PostgreSQL still enforces restrictions to preserve semantics.

### 11.4. Example of multiple references and filter pushdown

Suppose a CTE covers all orders, but each branch only wants one customer:

```sql
WITH base AS NOT MATERIALIZED (
    SELECT order_id, customer_id, status
    FROM cte_lab.orders
)
SELECT a.order_id AS order_of_customer_1,
       b.order_id AS order_of_customer_2
FROM base AS a
CROSS JOIN base AS b
WHERE a.customer_id = 1
  AND b.customer_id = 2;
```

PostgreSQL gets the opportunity to optimize each reference with its own predicate. However, `CROSS JOIN` itself produces row pairs between the two sets, so the output row count is the product of matching rows (in our dataset there are 2 orders for customer 1 and 2 orders for customer 2, giving 4 pairs). A CTE does not change join cardinality.

A `MATERIALIZED` version may have to compute `base` once and then filter during two scans of the CTE. On large datasets with selective filters, that can be a significant cost.

## 12. Reading EXPLAIN to Spot Materialization

Example:

```sql
EXPLAIN
WITH base AS MATERIALIZED (
    SELECT order_id, customer_id, status
    FROM cte_lab.orders
)
SELECT order_id
FROM base
WHERE customer_id = 1;
```

The plan may contain entries like `CTE base` and `CTE Scan on base`. This reflects that the CTE was treated as an intermediate source.

Compare:

```sql
EXPLAIN
WITH base AS NOT MATERIALIZED (
    SELECT order_id, customer_id, status
    FROM cte_lab.orders
)
SELECT order_id
FROM base
WHERE customer_id = 1;
```

The plan may show a direct scan of the `orders` table with the filter applied right at the scan, with no separate `CTE Scan`.

### 12.1. EXPLAIN vs. EXPLAIN ANALYZE

| Tool | Purpose | Note |
| --- | --- | --- |
| `EXPLAIN SELECT ...` | View the estimated plan. | Does not execute the query as `ANALYZE` does. |
| `EXPLAIN (ANALYZE, BUFFERS) SELECT ...` | Execute and measure timing, rows, and buffers. | Actually runs the query; can consume resources. |
| `EXPLAIN (ANALYZE, BUFFERS) UPDATE ...` | Measure DML. | **Actually modifies data**; only test inside a controlled lab transaction and roll back if appropriate. |

On tiny lab tables, the planner may pick a sequential scan because reading a few rows is cheaper than using an index. Do not infer whether `MATERIALIZED` is good or bad from a handful of example rows.

### 12.2. Do not make CTE hints a default habit

If you have not observed an actual bottleneck, start with CTEs that express logic **clearly**. Then measure. Only when you have evidence should you test `MATERIALIZED` or `NOT MATERIALIZED` and compare:

- Total rows read.
- Cost of recomputing expressions when a CTE is used multiple times.
- Filter pushdown behavior.
- Execution *loops* and actual row counts.
- Memory/temporary files needed for materializing/sorting/hashing.
- Execution time on representative data and workloads.

A query with a good plan must still be verified for correct business output; `EXPLAIN` is no substitute for logic testing.

## 13. CTEs and Volatile or Side-Effecting Functions

Not every function in PostgreSQL is pure. Functions are classified by volatility attributes such as `IMMUTABLE`, `STABLE`, and `VOLATILE`. Some functions alter state or return different values across calls.

Example:

```sql
WITH one_random_value AS MATERIALIZED (
    SELECT random() AS value
)
SELECT
    a.value AS first_read,
    b.value AS second_read
FROM one_random_value AS a
CROSS JOIN one_random_value AS b;
```

The CTE `one_random_value` produces one row containing a value from `random()`; both references read the same materialized CTE result within the statement. This differs from calling `random()` independently twice in the select list:

```sql
SELECT
    random() AS first_value,
    random() AS second_value;
```

The two calls can return different values. Do not build business logic with external side effects based on assuming "the SQL function will definitely be called N times" without understanding volatility and execution plans.

**Best practice:** use CTEs to express data relationships and calculations. If an operation depends on sequential side effects, design explicit transaction/command flows instead of hiding side-effecting functions inside `SELECT`.

## 14. WITH RECURSIVE: Handling Hierarchical Data

A regular CTE cannot reference itself in its own definition. When traversing trees or graphs, you need `WITH RECURSIVE`.

Simple example generating a number sequence:

```sql
WITH RECURSIVE numbers(n) AS (
    SELECT 1

    UNION ALL

    SELECT n + 1
    FROM numbers
    WHERE n < 5
)
SELECT n
FROM numbers
ORDER BY n;
```

Result:

| n |
| ---: |
| 1 |
| 2 |
| 3 |
| 4 |
| 5 |

In a recursive CTE:

1. **The initialization part** (*non-recursive term / anchor*) produces the initial rows, here `SELECT 1`.
2. **The recursive part** (*recursive term*) uses the previous iteration's output to produce the next rows, here `SELECT n + 1 FROM numbers`.
3. `UNION ALL` combines the initial rows and newly generated rows.
4. The condition `WHERE n < 5` causes the process to stop after producing 5.

### 14.1. Visualizing the iterations

```text
Initialize:
  working set = {1}
  result      = {1}

Pass 1:
  from {1} produce {2}
  result = {1,2}

Pass 2:
  from {2} produce {3}
  result = {1,2,3}

Pass 3:
  from {3} produce {4}

Pass 4:
  from {4} produce {5}

Next pass:
  n < 5 is no longer true for 5
  working set empty -> stop
```

PostgreSQL evaluates recursive CTEs using **iteration over a working table**, not stack-based function recursion as in imperative programming languages. Understanding this model explains why cycles in data can cause iteration to run indefinitely without a guard.

### 14.2. UNION ALL vs. UNION

`UNION ALL` keeps all generated rows. `UNION` deduplicates rows across steps based on the entire output tuple.

```sql
WITH RECURSIVE numbers(n) AS (
    SELECT 1
    UNION
    SELECT n + 1
    FROM numbers
    WHERE n < 5
)
SELECT n FROM numbers ORDER BY n;
```

For this simple sequence, both return 1–5. On a graph, deduplication can terminate certain searches that **only output node IDs**. However, if the recursive row also includes an ever-increasing `depth`, revisiting the same node still has a different `depth`, so `UNION` will not necessarily stop cycles.

**Do not treat `UNION` as a general-purpose cycle-prevention mechanism.** For real graphs, explicitly track visited nodes or use the `CYCLE` clause on supported versions.

## 15. Traversing a Parent–Child Category Tree with a Recursive CTE

The `cte_lab.categories` table has a `parent_id` column referencing the parent row's `category_id`. To list the full tree along with depth:

```sql
WITH RECURSIVE category_tree AS (
    SELECT
        category_id,
        category_name,
        parent_id,
        0 AS depth
    FROM cte_lab.categories
    WHERE parent_id IS NULL

    UNION ALL

    SELECT
        child.category_id,
        child.category_name,
        child.parent_id,
        parent.depth + 1
    FROM cte_lab.categories AS child
    JOIN category_tree AS parent
        ON child.parent_id = parent.category_id
)
SELECT
    category_id,
    category_name,
    parent_id,
    depth
FROM category_tree
ORDER BY depth, category_id;
```

Result:

| category_id | category_name | parent_id | depth |
| ---: | --- | ---: | ---: |
| 10 | Products | NULL | 0 |
| 14 | Services | NULL | 0 |
| 11 | Books | 10 | 1 |
| 12 | Accessories | 10 | 1 |
| 15 | Training | 14 | 1 |
| 13 | Tech Books | 11 | 2 |

Key points:

- The anchor selects all root nodes (`parent_id IS NULL`), not just a single root.
- The recursive term fetches child nodes where `child.parent_id = parent.category_id`.
- `depth` increments by 1 at each downward step.
- `ORDER BY depth, category_id` establishes an intentional output order; **do not rely on the internal emission order** of a recursive query.

### 15.1. What happens to nodes not reachable from root trees?

If a cluster of rows cannot be reached from the `parent_id IS NULL` anchor, the query above will not list them. For instance, in data without an FK or with a rootless cycle among nodes, those nodes will not appear in a root-seeded tree.

When auditing hierarchical data quality, you may need to:

- Check for orphan nodes whose parent cannot be found.
- Check for cycles.
- Compare the set of all `category_id`s in the table against those reachable from the roots.

A recursive CTE helps discover/traverse relationships, but does not replace business constraints on tree structure.

### 15.2. Fetching only the subtree under one category

```sql
WITH RECURSIVE subtree AS (
    SELECT
        category_id,
        category_name,
        parent_id,
        0 AS depth
    FROM cte_lab.categories
    WHERE category_id = 11

    UNION ALL

    SELECT
        c.category_id,
        c.category_name,
        c.parent_id,
        s.depth + 1
    FROM cte_lab.categories AS c
    JOIN subtree AS s
        ON c.parent_id = s.category_id
)
SELECT category_id, category_name, depth
FROM subtree
ORDER BY depth, category_id;
```

Result:

| category_id | category_name | depth |
| ---: | --- | ---: |
| 11 | Books | 0 |
| 13 | Tech Books | 1 |

When the anchor is node 11, `depth` is counted **from that node**, not as absolute depth from the system root. How depth is defined is a report design decision that should be documented clearly.

## 16. Building Paths in a Tree

To display "Products / Books / Tech Books", you can accumulate the path across recursive steps:

```sql
WITH RECURSIVE category_paths AS (
    SELECT
        category_id,
        category_name,
        parent_id,
        category_name::text AS display_path,
        ARRAY[category_id] AS id_path
    FROM cte_lab.categories
    WHERE parent_id IS NULL

    UNION ALL

    SELECT
        c.category_id,
        c.category_name,
        c.parent_id,
        p.display_path || ' / ' || c.category_name,
        p.id_path || c.category_id
    FROM cte_lab.categories AS c
    JOIN category_paths AS p
        ON c.parent_id = p.category_id
    WHERE NOT c.category_id = ANY(p.id_path)
)
SELECT
    category_id,
    display_path,
    id_path
FROM category_paths
ORDER BY id_path;
```

Notable result:

```text
10 | Products                     | {10}
11 | Products / Books             | {10,11}
13 | Products / Books / Tech Books | {10,11,13}
12 | Products / Accessories       | {10,12}
14 | Services                     | {14}
15 | Services / Training          | {14,15}
```

`id_path` is a `bigint[]` holding the IDs traversed so far. `ANY` checks whether the current node has already appeared in the path, **preventing cycles along a path**.

### 16.1. Preventing cycles even in tree models

A self-referencing foreign key only guarantees that `parent_id` points to an existing node; it **does not guarantee an acyclic structure**. For example, a node could become its own parent without extra constraints, or multiple nodes could form a loop.

In production systems, validate against cycles when updating parent–child relationships rather than relying solely on `WHERE NOT ... ANY(path)` in read queries. A cycle guard in a recursive CTE is a **read-time safeguard**, not proof that the entire data model is always a valid tree.

### 16.2. What role does path ordering play?

`ORDER BY id_path` sorts rows lexicographically by the sequence of IDs in the path, approximating a depth-first traversal of the tree. It is an **output sorting rule** based on the path rather than a guarantee of PostgreSQL's physical processing order.

If you need to sort by name, priority, or a node's display-order field, store that attribute and build a sort path from those components instead of assuming IDs always reflect the desired UI order.

## 17. Graphs with Cycles: Preventing Infinite Loops

The `cte_lab.graph_edges` table contains the cycle `1 → 2 → 3 → 1`. If you write:

```sql
-- DO NOT RUN on this lesson's graph_edges without a guard:
-- WITH RECURSIVE walk(node_id) AS (
--     SELECT 1::bigint
--     UNION ALL
--     SELECT e.to_id
--     FROM cte_lab.graph_edges AS e
--     JOIN walk AS w
--         ON e.from_id = w.node_id
-- )
-- SELECT * FROM walk;
```

then the query will keep generating 1, 2, 3, 1, 2, 3, ... indefinitely under that logic.

### 17.1. Using a path array to block visited nodes

```sql
WITH RECURSIVE walk AS (
    SELECT
        1::bigint AS node_id,
        ARRAY[1::bigint] AS visited,
        0 AS depth

    UNION ALL

    SELECT
        e.to_id,
        w.visited || e.to_id,
        w.depth + 1
    FROM walk AS w
    JOIN cte_lab.graph_edges AS e
        ON e.from_id = w.node_id
    WHERE NOT e.to_id = ANY(w.visited)
)
SELECT
    node_id,
    visited,
    depth
FROM walk
ORDER BY visited;
```

Valid paths from node 1:

```text
1
1 -> 2
1 -> 2 -> 3
1 -> 4
1 -> 4 -> 5
```

The step `1 → 2 → 3 → 1` is not generated because node 1 is already in `visited`.

**Important:** this condition prevents loops **within each individual path**; it does not guarantee each node appears **only once in the entire result** if the graph has multiple distinct paths leading to the same node. If you need a deduplicated set of reachable nodes, consider `SELECT DISTINCT node_id` outside or an algorithm suited to the problem.

### 17.2. Adding a depth limit

```sql
WITH RECURSIVE walk AS (
    SELECT
        1::bigint AS node_id,
        ARRAY[1::bigint] AS visited,
        0 AS depth

    UNION ALL

    SELECT
        e.to_id,
        w.visited || e.to_id,
        w.depth + 1
    FROM walk AS w
    JOIN cte_lab.graph_edges AS e
        ON e.from_id = w.node_id
    WHERE w.depth < 10
      AND NOT e.to_id = ANY(w.visited)
)
SELECT *
FROM walk
ORDER BY depth, node_id;
```

`w.depth < 10` is a safety cap on the maximum number of edges in generated paths; it **does not replace cycle checks** in branching graphs or special logic. Maximum depth should reflect business rules rather than an arbitrary constant.

Beyond depth, you may also need node/path count limits via application logic, appropriate timeouts, workload monitoring, and pagination or targeted search instead of enumerating all paths in a large graph.

## 18. SEARCH and CYCLE in PostgreSQL 14+

PostgreSQL 14 introduced `SEARCH` and `CYCLE` clauses for recursive CTEs, letting you express traversal order and cycle detection declaratively.

### 18.1. CYCLE automatically creates marker and path columns

```sql
WITH RECURSIVE walk(node_id) AS (
    SELECT 1::bigint

    UNION ALL

    SELECT e.to_id
    FROM cte_lab.graph_edges AS e
    JOIN walk AS w
        ON e.from_id = w.node_id
)
CYCLE node_id SET is_cycle USING cycle_path
SELECT
    node_id,
    is_cycle,
    cycle_path
FROM walk
ORDER BY cycle_path;
```

PostgreSQL automatically adds:

- `is_cycle`: a flag indicating a row was detected as a repeated node along the path.
- `cycle_path`: the tracked path information used to detect cycles.

Once a row is flagged as a cycle, PostgreSQL does not expand it further under `CYCLE` semantics. However, **the cycle row itself may still appear** in the output, so if you only want non-cyclic paths:

```sql
WITH RECURSIVE walk(node_id) AS (
    SELECT 1::bigint
    UNION ALL
    SELECT e.to_id
    FROM cte_lab.graph_edges AS e
    JOIN walk AS w
        ON e.from_id = w.node_id
)
CYCLE node_id SET is_cycle USING cycle_path
SELECT node_id, cycle_path
FROM walk
WHERE NOT is_cycle
ORDER BY cycle_path;
```

On PostgreSQL 13 or older, this standard `CYCLE` syntax is unavailable; use a path array/predicate as in Section 17.

### 18.2. SEARCH to generate a traversal-order key

```sql
WITH RECURSIVE category_tree AS (
    SELECT category_id, category_name, parent_id
    FROM cte_lab.categories
    WHERE parent_id IS NULL

    UNION ALL

    SELECT c.category_id, c.category_name, c.parent_id
    FROM cte_lab.categories AS c
    JOIN category_tree AS t
        ON c.parent_id = t.category_id
)
SEARCH DEPTH FIRST BY category_id SET traversal_order
SELECT
    category_id,
    category_name,
    traversal_order
FROM category_tree
ORDER BY traversal_order;
```

`SEARCH DEPTH FIRST ... SET traversal_order` creates an auxiliary column used to **sort the output in depth-first traversal order**. You can use `SEARCH BREADTH FIRST` when breadth-first ordering is needed.

Do not assume `SEARCH` forces PostgreSQL to physically read rows in depth-first/breadth-first order. It provides a **result sorting key**; to guarantee stable output order, you must write `ORDER BY traversal_order`.

### 18.3. Is using SEARCH together with CYCLE necessary?

When both cycle control and traversal ordering are needed, they can be combined on supported major versions. However, if `CYCLE` already produces a path suitable for depth-first sorting, adding `SEARCH DEPTH FIRST` can sometimes do redundant work. Select only the columns you actually need and measure on representative data.

## 19. Do Not Use an Outer LIMIT as the Recursion Stopping Guard

Learners sometimes write a recursive CTE without a stopping condition and try:

```sql
-- DO NOT TREAT THIS AS A SAFE DESIGN:
-- WITH RECURSIVE numbers(n) AS (
--     SELECT 1
--     UNION ALL
--     SELECT n + 1 FROM numbers
-- )
-- SELECT n FROM numbers LIMIT 10;
```

In some PostgreSQL plans, a parent query with `LIMIT` may pull only a subset of rows from the recursive CTE, causing a simple example to stop once enough rows are retrieved. However, that is a **plan-dependent execution behavior**, not a way to ensure a recursive query is correct.

Simply adding an `ORDER BY`, `JOIN`, or aggregate to the parent query that needs all rows can force deeper or infinite recursion.

A safe design must have:

- A logical termination condition inside the recursive term.
- Cycle prevention whenever data can form loops.
- Depth/workload bounds aligned with business requirements.
- Timeout/resource monitoring for large graph queries.

A `LIMIT` used to display a page of rows is a presentation requirement, never the sole safety stop for an unbounded algorithm.

## 20. Data Types of Anchor and Recursive Terms

A recursive CTE requires **both branches of `UNION [ALL]` to have compatible data types** in every column.

Example:

```sql
WITH RECURSIVE seq(n, label) AS (
    SELECT
        1,
        'Level 1'::text

    UNION ALL

    SELECT
        n + 1,
        ('Level ' || (n + 1)::text)
    FROM seq
    WHERE n < 3
)
SELECT n, label
FROM seq
ORDER BY n;
```

Returns labels `Level 1`, `Level 2`, `Level 3`.

When building text paths, explicitly casting the anchor to `text` helps prevent type mismatch errors from an `unknown` literal or `varchar(n)` while the recursive branch produces `text`. When storing numeric paths, construct arrays with the exact type:

```sql
SELECT
    ARRAY[1::bigint] AS bigint_path,
    ARRAY[1::bigint] || 2::bigint AS extended_path;
```

A common syntax/type pitfall is an anchor producing `integer[]` while the recursive branch produces `bigint[]`, or an anchor using a length-limited text type while the recursive path grows longer. It is best to **define types deliberately in the anchor**.

## 21. Recursive CTE Performance and Limits of Tree Models

Recursive CTEs work well for moderately sized trees, but large or heavily branching graphs can generate huge numbers of paths.

### 21.1. Indexes for parent–child queries

In the recursive term, the join condition is commonly:

```sql
JOIN cte_lab.categories AS child
    ON child.parent_id = parent.category_id
```

An index on `parent_id` can help once the table is large enough:

```sql
CREATE INDEX idx_categories_parent_id
ON cte_lab.categories (parent_id);
```

For graphs:

```sql
CREATE INDEX idx_graph_edges_to_id
ON cte_lab.graph_edges (to_id);
```

The primary key `(from_id, to_id)` already helps traversals starting from `from_id`; an additional index on `to_id` can help when traversing in reverse. Do not create indexes unconditionally if the workload does not need them.

### 21.2. Questions to ask before using a recursive CTE

1. What is the maximum depth that can be reached?
2. How many children or edges can each node have?
3. Are there cycles, multiple paths, or isolated nodes?
4. Do you want all **paths**, all **unique reachable nodes**, or only the **shortest path**?
5. Is deterministic output ordering or pagination needed?
6. How many times per second is the query called?
7. Are appropriate indexes and execution timeouts in place?

A CTE enumerating **all simple paths** in a highly branching graph can still generate vast row counts even with cycle prevention enabled. If the problem is finding shortest paths on huge graphs or deep network analysis, evaluate specialized algorithms/data structures rather than assuming recursive SQL is optimal.

### 21.3. Alternative tree modeling approaches

| Model | Idea | Trade-off |
| --- | --- | --- |
| Adjacency list (`parent_id`) | Each row stores its parent ID. | Easy to write/update; querying all descendants requires recursion. |
| Materialized path | Each row stores its ancestor path. | Convenient subtree reads; reparenting may require updating many paths. |
| Closure table | Stores ancestor–descendant pairs and depth. | Easy ancestor/descendant queries; higher maintenance cost for relationships. |
| Nested set | Stores interval bounds to represent tree structure. | Convenient for some subtree reads; moving nodes can require costly updates. |

`WITH RECURSIVE` pairs naturally with adjacency lists; if a system queries descendants very frequently at large scale, consider auxiliary storage patterns with clear write and consistency trade-offs.

## 22. Using WITH with UPDATE

`WITH` is not limited to `SELECT`. PostgreSQL allows placing CTEs before data-modifying statements like `INSERT`, `UPDATE`, and `DELETE`; for `MERGE`, check your major version's support and behavior.

Example selecting pending orders for customer 1 and transitioning them to completed:

```sql
WITH target_orders AS (
    SELECT order_id
    FROM cte_lab.orders
    WHERE customer_id = 1
      AND status = 'pending'
)
UPDATE cte_lab.orders AS o
SET status = 'completed'
FROM target_orders AS t
WHERE o.order_id = t.order_id
RETURNING
    o.order_id,
    o.customer_id,
    o.status;
```

On the initial dataset, this SQL updates order 1002 to `completed`. **Do not run it if you want to preserve the numbers from earlier examples**, since completed revenue and completed order counts will change.

To test in the lab and restore the data afterward:

```sql
BEGIN;

WITH target_orders AS (
    SELECT order_id
    FROM cte_lab.orders
    WHERE customer_id = 1
      AND status = 'pending'
)
UPDATE cte_lab.orders AS o
SET status = 'completed'
FROM target_orders AS t
WHERE o.order_id = t.order_id
RETURNING o.order_id, o.status;

ROLLBACK;
```

In a single-user lab with no concurrent writers, rollback restores the initial state. In a real application with concurrent writers, selection and update predicates must handle concurrency, row locking, and retries; a CTE does not do all of that automatically.

### 22.1. Do not assume a CTE always "freezes" the row set

If the `target_orders` CTE is a `SELECT` that the optimizer can fold into the statement, physical execution may differ from imagining "PostgreSQL first builds a separate ID list and only then runs UPDATE".

When a business invariant must not change during a write, design the `UPDATE` with proper predicates and locking. Avoid inferring execution order from the textual order of CTEs.

## 23. Data-Modifying CTEs: Modifying Data and Using RETURNING

PostgreSQL also supports CTEs containing data-modifying statements—typically `INSERT`, `UPDATE`, `DELETE`, and `MERGE` depending on version. A useful pattern is moving processed rows to an archive table in **one atomic SQL statement**.

### 23.1. Setting up standalone jobs tables

To avoid affecting `orders`:

```sql
CREATE TABLE cte_lab.jobs (
    job_id bigint PRIMARY KEY,
    job_status text NOT NULL
        CHECK (job_status IN ('pending', 'running', 'completed')),
    payload text NOT NULL
);

CREATE TABLE cte_lab.jobs_archive (
    job_id bigint PRIMARY KEY,
    job_status text NOT NULL,
    payload text NOT NULL,
    archived_at timestamptz NOT NULL
);

INSERT INTO cte_lab.jobs (job_id, job_status, payload)
VALUES
    (1, 'completed', 'done-A'),
    (2, 'pending',   'queued-B'),
    (3, 'completed', 'done-C');
```

### 23.2. DELETE ... RETURNING then INSERT

```sql
WITH moved AS (
    DELETE FROM cte_lab.jobs
    WHERE job_status = 'completed'
    RETURNING job_id, job_status, payload
)
INSERT INTO cte_lab.jobs_archive (
    job_id, job_status, payload, archived_at
)
SELECT
    job_id,
    job_status,
    payload,
    clock_timestamp()
FROM moved
RETURNING job_id, archived_at;
```

Expected result: completed jobs (1, 3) are deleted from `jobs` and inserted into `jobs_archive`; job 2 remains in the active table.

Explanation:

- The CTE `moved` is not a `SELECT` but a `DELETE`.
- `DELETE ... RETURNING` outputs the deleted rows as a result relation.
- The main `INSERT` receives rows from `moved`.
- Both effects are part of the same statement and are executed by PostgreSQL within the atomic boundary of the transaction.

If a unique key violation occurs in `jobs_archive`, the statement fails and rolls back under transaction rules; you should not assume the deleted rows are permanently lost.

### 23.3. Be careful with ordering and snapshots in DML CTEs

**This is a crucial difference** from imagining "each CTE runs to completion and the next one sees the modified table":

- DML sub-statements in a `WITH` statement may execute in an order you cannot rely on for business logic.
- They share the same statement-level snapshot; do not expect one DML CTE to see rows just modified by another DML CTE by re-scanning the base table.
- **`RETURNING` is the explicit channel to pass modified data** from a DML CTE to another part of the same statement.
- Avoid attempting to modify the same row **twice** in one statement across multiple DML CTEs or between a CTE and the main statement; the outcome is not reliably defined per author intent.
- A data-modifying CTE without `RETURNING` still performs its modification, but produces no output relation for another CTE to read via `FROM moved`.

Do not treat CTE names as a sequential command script like:

```text
step_a definitely finishes updating the base table
     ->
step_b SELECTs the base table again and immediately sees new rows
```

If each step needs to see committed changes sequentially, use separate statements in a transaction with appropriate isolation/locking, or pass rows via `RETURNING` using PostgreSQL's supported pattern.

### 23.4. Placement restrictions on data-modifying CTEs

Data-modifying CTEs in PostgreSQL have placement restrictions and must belong to a `WITH` attached at the appropriate top-level statement; you cannot freely place arbitrary DML inside nested subqueries the way you can with `SELECT` CTEs.

Data-modifying queries also involve permissions, triggers, constraints, WAL, locking, and rollback behavior like normal DML; never test them on production just to inspect `EXPLAIN ANALYZE`.

## 24. CTEs in INSERT ... SELECT

Suppose you need to populate a cached reporting table from computable data. A CTE helps express the source dataset before insertion.

In the lab:

```sql
CREATE TABLE cte_lab.customer_revenue_snapshot (
    snapshot_date date NOT NULL,
    customer_id bigint NOT NULL,
    completed_revenue numeric(14, 2) NOT NULL,
    PRIMARY KEY (snapshot_date, customer_id)
);
```

Save a daily snapshot:

```sql
WITH revenue AS (
    SELECT
        o.customer_id,
        SUM(i.quantity * i.unit_price) AS amount
    FROM cte_lab.orders AS o
    JOIN cte_lab.order_items AS i
        ON i.order_id = o.order_id
    WHERE o.status = 'completed'
    GROUP BY o.customer_id
)
INSERT INTO cte_lab.customer_revenue_snapshot (
    snapshot_date, customer_id, completed_revenue
)
SELECT
    DATE '2026-11-14',
    c.customer_id,
    COALESCE(r.amount, 0)
FROM cte_lab.customers AS c
LEFT JOIN revenue AS r
    ON r.customer_id = c.customer_id
RETURNING
    snapshot_date,
    customer_id,
    completed_revenue;
```

This snapshot persists the **result as of when the statement ran** into a real table; unlike the `revenue` CTE, which lives only for the duration of the statement. Re-running with the same `snapshot_date` without an appropriate `ON CONFLICT` clause will cause the primary key to reject duplicate rows.

Furthermore, if source tables change while the snapshot is generated, snapshot semantics follow the SQL statement's isolation level and observation point. Do not label a snapshot table "exact daily history" without defining cutoff rules and how late-arriving transactions are handled.

## 25. CTEs in UPDATE ... FROM and the Risk of Multiple Matching Rows

A CTE can act as the source for `UPDATE ... FROM`:

```sql
WITH amounts AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS amount
    FROM cte_lab.order_items
    GROUP BY order_id
)
SELECT
    o.order_id,
    a.amount
FROM cte_lab.orders AS o
JOIN amounts AS a
    ON a.order_id = o.order_id
ORDER BY o.order_id;
```

If a `orders.total_amount` column is added later and updated via `UPDATE ... FROM amounts`, you must ensure `amounts` has **at most one row per `order_id`**. Here, `GROUP BY order_id` satisfies that condition.

In PostgreSQL, if a target row matches multiple source rows in `UPDATE ... FROM`, which source row supplies the update value is non-deterministic with respect to business intent. **A CTE does not automatically deduplicate rows**. Design keys, aggregations, or ordered representative selection carefully before updating.

A read-only query to check cardinality:

```sql
WITH amounts AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS amount
    FROM cte_lab.order_items
    GROUP BY order_id
)
SELECT order_id, COUNT(*) AS rows_per_order
FROM amounts
GROUP BY order_id
HAVING COUNT(*) <> 1;
```

With the CTE above, the query returns zero rows. On real data, verify grain assumptions rather than assuming data is normalized just because `WITH` is used.

## 26. A CTE Is Not a Transaction

A `SELECT` CTE is only an expression construct of **one statement**; it does not open or close a new transaction.

Distinguish:

```sql
BEGIN;

WITH completed_orders AS (
    SELECT order_id
    FROM cte_lab.orders
    WHERE status = 'completed'
)
SELECT COUNT(*) FROM completed_orders;

SELECT COUNT(*) FROM cte_lab.orders;

COMMIT;
```

The two `SELECT`s are two statements within one transaction. The `completed_orders` CTE exists only in the first statement and cannot be used in the second `SELECT`.

At `READ COMMITTED` isolation level, two statements inside the same transaction can observe different committed snapshots according to PostgreSQL's rules. `WITH` does not create a shared snapshot across multiple separate SQL statements.

If a multi-statement report needs consistency across a single snapshot, choose the appropriate isolation level and transaction design. Conversely, a data-modifying CTE and its main statement belong to the same statement and follow the snapshot/`RETURNING` rules covered earlier.

## 27. CTE, VIEW, MATERIALIZED VIEW, and TEMP TABLE

The names of these tools are easily confused because all of them help structure SQL or hold intermediate results.

| Tool | Lifetime | Stores its own data? | Best fit |
| --- | --- | --- | --- |
| CTE `WITH name AS (...)` | Single SQL statement | Not a persistent storage object; may be materialized **internally at runtime**. | Organizing one complex SQL statement. |
| View `CREATE VIEW` | Schema object until dropped | Typically does not store query results. | Reusing a query interface across multiple statements/services. |
| Materialized view | Schema object until dropped | **Stores results**, requires refresh. | Speeding up aggregate reads when staleness is acceptable. |
| Temporary table | Session/transaction per config | **Creates a temp table and temp data** for its scope. | Multiple statements operating on an intermediate dataset, indexable. |

### 27.1. Comparing with VIEW

```sql
CREATE VIEW cte_lab.v_completed_orders AS
SELECT order_id, customer_id, ordered_at
FROM cte_lab.orders
WHERE status = 'completed';
```

Then across multiple statements:

```sql
SELECT * FROM cte_lab.v_completed_orders;
```

A view provides a named definition stored in the schema that can be shared and permissioned. Still, consider schema dependencies, migrations, and how permissions apply to views; do not assume a view is a materialized data copy.

### 27.2. Comparing with TEMP TABLE

```sql
CREATE TEMP TABLE temp_completed_orders AS
SELECT order_id, customer_id
FROM cte_lab.orders
WHERE status = 'completed';

SELECT COUNT(*) FROM temp_completed_orders;
SELECT * FROM temp_completed_orders ORDER BY order_id;
```

A temporary table here can be used across multiple statements in the session. However, its data is a snapshot taken at creation time and **does not automatically track subsequent changes** to `orders`. It also incurs creation overhead, session management, and may need its own statistics/indexes when large.

When only one `SELECT` is needed, a CTE is usually simpler. When multiple SQL statements need to share an intermediate set, a temp table can be considered, accounting for connection pooling and session lifecycle effects.

### 27.3. A MATERIALIZED CTE is not a MATERIALIZED VIEW

`WITH base AS MATERIALIZED (...)` is a directive on **how to evaluate a CTE within a single statement**. It does not create a persistent named materialized view. `REFRESH MATERIALIZED VIEW` does not apply to CTEs.

The shared word "materialized" relates to the idea of storing intermediate results, but **their scope and lifecycle are completely different**.

## 28. CTEs and Parameterized SQL in Java Applications

Java applications typically use `PreparedStatement` or a data-access library to bind values safely.

Example SQL with PostgreSQL server-side parameter placeholder `$1` when using an appropriate prepared-statement interface:

```sql
PREPARE completed_orders_for_customer(bigint) AS
WITH selected_orders AS (
    SELECT order_id, ordered_at
    FROM cte_lab.orders
    WHERE status = 'completed'
      AND customer_id = $1
)
SELECT order_id, ordered_at
FROM selected_orders
ORDER BY ordered_at DESC, order_id DESC;

EXECUTE completed_orders_for_customer(1);

DEALLOCATE completed_orders_for_customer;
```

In JDBC, the placeholder used by `PreparedStatement` is typically `?`, never concatenating input values directly into the SQL string:

```java
String sql = """
    WITH selected_orders AS (
        SELECT order_id, ordered_at
        FROM cte_lab.orders
        WHERE status = 'completed'
          AND customer_id = ?
    )
    SELECT order_id, ordered_at
    FROM selected_orders
    ORDER BY ordered_at DESC, order_id DESC
    """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, customerId);

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            long orderId = rs.getLong("order_id");
            // Process results appropriately for the application.
        }
    }
}
```

The Java snippet assumes `connection` and `customerId` have been initialized safely by the application. In production, manage transactions, connection pools, timeouts, and connection errors appropriately.

**CTEs do not protect against SQL injection** if the application still concatenates user input into the query string. All user-supplied values must go through proper parameterization; never let unvalidated input control table names, column names, or SQL clauses.

## 29. CTEs and Result Ordering

A common mistake is placing `ORDER BY` inside a CTE and assuming the outer result keeps that order.

```sql
WITH sorted_orders AS (
    SELECT order_id, ordered_at
    FROM cte_lab.orders
    ORDER BY ordered_at DESC
)
SELECT order_id, ordered_at
FROM sorted_orders;
```

Do not rely on the display order of the final query when it **lacks an `ORDER BY` at the outer level**. PostgreSQL can change plans or perform subsequent operations that alter row order.

To guarantee return order:

```sql
WITH selected_orders AS (
    SELECT order_id, ordered_at
    FROM cte_lab.orders
)
SELECT order_id, ordered_at
FROM selected_orders
ORDER BY ordered_at DESC, order_id DESC;
```

### 29.1. ORDER BY and LIMIT inside a CTE have a distinct purpose

If the goal is to pick the **three newest orders** and process them further, placing `ORDER BY ... LIMIT 3` inside the CTE has semantic meaning:

```sql
WITH latest_three AS (
    SELECT order_id, customer_id, ordered_at
    FROM cte_lab.orders
    ORDER BY ordered_at DESC, order_id DESC
    LIMIT 3
)
SELECT
    l.order_id,
    c.customer_name,
    l.ordered_at
FROM latest_three AS l
JOIN cte_lab.customers AS c
    ON c.customer_id = l.customer_id
ORDER BY l.ordered_at DESC, l.order_id DESC;
```

Here, the inner `ORDER BY ... LIMIT 3` determines **which three orders** are selected; the outer `ORDER BY` determines **the returned row order** after the JOIN. The two clauses serve different purposes.

## 30. Common Mistakes with CTEs

### Mistake 1. Forgetting the comma between two CTEs

```sql
-- Syntax error due to missing comma:
-- WITH a AS (SELECT 1 AS n)
--      b AS (SELECT 2 AS n)
-- SELECT * FROM a;
```

Correct:

```sql
WITH a AS (SELECT 1 AS n),
     b AS (SELECT 2 AS n)
SELECT a.n AS a_value, b.n AS b_value
FROM a CROSS JOIN b;
```

### Mistake 2. Using a CTE in a different statement

```sql
-- Statement 1:
WITH temp_values AS (SELECT 1 AS n)
SELECT n FROM temp_values;

-- Statement 2 no longer has the temp_values CTE:
-- SELECT n FROM temp_values;
```

To reuse a query definition across statements, consider a view or temporary table.

### Mistake 3. Referencing a column missing from the CTE output

```sql
-- Invalid because chosen only outputs order_id, not customer_id:
-- WITH chosen AS (
--     SELECT order_id FROM cte_lab.orders
-- )
-- SELECT customer_id FROM chosen;
```

A CTE only exposes the columns its query actually returns. If `customer_id` is needed in the outer query, select it inside the CTE.

### Mistake 4. Assuming a CTE always runs first and is saved to disk

PostgreSQL 12+ can fold pure `SELECT` CTEs when eligible. `MATERIALIZED` lets you set an evaluation boundary in supported cases. Do not guess the execution plan from syntax alone.

### Mistake 5. Assuming NOT MATERIALIZED always speeds things up

When a CTE is used multiple times and contains expensive expressions, folding it can recompute the work. Compare `EXPLAIN` and workload behavior instead of treating `NOT MATERIALIZED` as an "automatic speedup" hint.

### Mistake 6. Missing a stopping condition in WITH RECURSIVE

Data cycles or unbounded increments can prevent the query from terminating properly. Always design the anchor, recursive term, cycle detection, and resource limits.

### Mistake 7. Believing UNION automatically eliminates all cycles

If the recursive row includes a changing `depth`, each revisit to an old node still forms a distinct tuple across all columns. `UNION` does not replace `CYCLE` or a visited-path array when repeated-node detection is required.

### Mistake 8. Reading recursive output order as a guarantee

Results may look breadth-first, but do not depend on that. Use `ORDER BY` on path, depth, or an appropriate `SEARCH ... SET` column.

### Mistake 9. Putting an outer LIMIT to "fix" an infinite query

Adding a JOIN, ORDER BY, or aggregate in the outer query can force PostgreSQL to pull more rows. Stopping conditions must live inside the recursion logic or cycle-detection mechanism.

### Mistake 10. Assuming WITH makes COUNT(*) after LEFT JOIN automatically right

A CTE does not fix outer join semantics. If the result contains a NULL-extended row for a customer without orders, `COUNT(*)` still counts 1; count a `NOT NULL` right-side key instead.

### Mistake 11. Ignoring grain when joining multiple aggregated CTEs

One CTE has one row per customer; another has one row per order. Joining without matching keys/granularity can multiply totals. Explicitly state what one row represents and verify JOIN key uniqueness.

### Mistake 12. Writing data-modifying CTEs as an imagined sequential script

DML sub-statements are not a sequential script where the next sub-statement re-reads the base table and sees changes. Pass data via `RETURNING`, and avoid modifying the same target row in multiple DML parts of one statement.

### Mistake 13. Naming a CTE the same as a real table without understanding scope

A CTE can shadow an unqualified relation name within the query's scope. Use descriptive names and schema-qualify table names when referring to base tables clearly.

### Mistake 14. Confusing a MATERIALIZED CTE with a materialized view

A CTE does not outlive the statement and has no refresh command. A materialized view is a schema object with stored results and its own refresh mechanism.

### Mistake 15. Creating too many "one-line" CTEs

CTEs clarify logic when each step carries real meaning. Too many trivial steps can make SQL harder to read; prefer domain-meaningful names and a balanced structure.

### Mistake 16. Failing to protect sensitive data

A CTE does not restrict permissions on underlying tables. A `WITH` query can join additional tables and return unintended user data. Select only needed columns, enforce least-privilege roles, and parameterize inputs.

## 31. Workflow for Writing and Verifying a CTE Query

When given a complex reporting requirement, follow this process:

1. **Define the output:** what entity does one row represent, and which fields are needed?
2. **Identify sources of truth:** which tables and relationships supply the data?
3. **Break into semantic steps:** filter valid rows, compute per-order totals, aggregate by customer, rank, format.
4. **Name CTEs clearly:** `completed_orders`, `order_totals`, `customer_revenue` instead of `a`, `b`, `tmp1`.
5. **Check each CTE's grain:** are keys unique? Are there unmatched rows or NULLs?
6. **Check data types:** aggregates, numerics, timestamps, and NULLs.
7. **Cross-check results:** verify row counts, totals, ID sets, and edge cases using hand-calculable samples.
8. **If recursive:** define the anchor, termination condition, cycle detection, depth, and output ordering.
9. **If using DML:** check permissions, transaction boundaries, locking, and `RETURNING`; never experiment on production.
10. **Measure performance:** inspect `EXPLAIN`, reference counts, folding/materialization, indexes, and write overhead.
11. **Add MATERIALIZED hints only when needed:** compare both options under realistic workloads.
12. **Document assumptions:** which statuses count toward revenue, depth limits, time windows, and snapshot/isolation behavior.

The goal is not to maximize the number of CTEs, but to achieve **correct results, readable SQL, and appropriate performance**.

## 32. Practice Exercises

These exercises use the `cte_lab` dataset created in Section 2. If you ran DML examples that modified `orders` or archived jobs, reset the lab data to its initial state before comparing against fixed answers.

### Exercise 1. Order-filtering CTE

Write `WITH completed_orders` to fetch `order_id` and `customer_id` for orders with `status='completed'`, then select the results ordered by `order_id`.

**Expected:** 1001, 1003, 1004.

### Exercise 2. Column naming

Write a CTE `pair(x, y)` containing values 7 and 9, then return `x`, `y`, and their sum.

**Expected:** 7, 9, 16.

### Exercise 3. Per-order totals

Use a CTE aggregating `order_items` to return `order_id` and total amount. Filter for orders with total ≥ 100 in the outer query.

**Expected:** 1001 (250), 1003 (300), 1004 (100).

### Exercise 4. Every customer including those without orders

Create a CTE of `completed` revenue by customer. `LEFT JOIN` from `customers` to return all customers, using `COALESCE` for 0 revenue.

**Expected:** An 250, Binh 300, Chi 100, Dung 0.

### Exercise 5. Top 2 by revenue

Create at least two CTEs: `customer_revenue` and `ranked`. Use `ROW_NUMBER` with a tie-breaker to retrieve the top 2 customers by revenue.

**Expected:** Binh, An.

### Exercise 6. Referencing one CTE twice

Create `completed_totals`, then return each completed order along with the average total across all completed orders and an `above_average` flag.

**Hint:** use a `stats` CTE reading from `completed_totals`, then `CROSS JOIN` it with `completed_totals` in the final query.

### Exercise 7. Comparing MATERIALIZED and NOT MATERIALIZED

Write two versions of a query filtering a single order by `order_id`: one `MATERIALIZED` and one `NOT MATERIALIZED`. Inspect the `EXPLAIN` plans.

**Question:** under what circumstances can a materialization boundary force PostgreSQL to read more rows?

### Exercise 8. Recursive number sequence

Write `WITH RECURSIVE` generating numbers 1–10 with a stopping condition in the recursive term. Return in ascending order.

### Exercise 9. Traversing the entire category tree

Create a recursive CTE starting from nodes with `parent_id IS NULL` returning `category_id`, `category_name`, and `depth`.

**Expected:** categories 10, 14 at depth 0; 11, 12, 15 at depth 1; 13 at depth 2.

### Exercise 10. Listing descendants of Books

Anchor at `category_id = 11`. Return category 11 and all of its descendants.

**Expected:** 11 and 13.

### Exercise 11. Building paths

Build `display_path` from category names from root to child. Predict the path for category 13.

**Expected:** `Products / Books / Tech Books`.

### Exercise 12. Preventing cycles

On `graph_edges`, write a recursive CTE starting from node 1, storing visited IDs in an array and avoiding revisiting already-visited nodes.

**Expected:** paths to nodes 1, 2, 3, 4, 5; does not loop infinitely through 1–2–3–1.

### Exercise 13. Using CYCLE on PostgreSQL 14+

Replace the manual visited array with `CYCLE node_id SET is_cycle USING cycle_path`. Filter out rows flagged as cycles and explain why this is safer than an unguarded query.

### Exercise 14. Data-modifying CTE

On a lab copy of the `jobs` table, move `completed` jobs to `jobs_archive` using `DELETE ... RETURNING` in a CTE and `INSERT ... SELECT` in the main statement.

**Question:** if the archive insert fails, what happens to the delete in the same statement?

### Exercise 15. CTE or VIEW?

A system has a one-off report and a core business query used by 12 services across many statements. Choose CTE or view for each case and explain why.

### Exercise 16. The ORDER BY in CTE pitfall

Write a query selecting the three newest orders using a CTE and then joining customer names. Place `ORDER BY` where needed to select the three orders and guarantee output order.

### Exercise 17. Spotting row multiplication

A CTE `daily_totals` has one row per customer–day; a CTE `customer_tags` has multiple tags per customer. Joining them and calling `SUM(daily_totals.amount)` can multiply totals. Propose how to check and avoid multiplication.

### Exercise 18. Building a multi-level report

Use three CTEs: `eligible_orders`, `order_totals`, and `customer_summary`. Return all customers and their completed revenue, ordered by revenue descending, ID ascending.

**Expected:** Binh 300, An 250, Chi 100, Dung 0.

## 33. Solution Hints

### Solution 1: filtering completed orders

```sql
WITH completed_orders AS (
    SELECT order_id, customer_id
    FROM cte_lab.orders
    WHERE status = 'completed'
)
SELECT order_id, customer_id
FROM completed_orders
ORDER BY order_id;
```

### Solution 2: naming columns

```sql
WITH pair(x, y) AS (
    SELECT 7, 9
)
SELECT x, y, x + y AS total
FROM pair;
```

### Solution 3: per-order totals

```sql
WITH totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS amount
    FROM cte_lab.order_items
    GROUP BY order_id
)
SELECT order_id, amount
FROM totals
WHERE amount >= 100
ORDER BY order_id;
```

### Solution 4: keeping all customers

```sql
WITH revenue AS (
    SELECT
        o.customer_id,
        SUM(i.quantity * i.unit_price) AS amount
    FROM cte_lab.orders AS o
    JOIN cte_lab.order_items AS i
        ON i.order_id = o.order_id
    WHERE o.status = 'completed'
    GROUP BY o.customer_id
)
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(r.amount, 0) AS completed_revenue
FROM cte_lab.customers AS c
LEFT JOIN revenue AS r
    ON r.customer_id = c.customer_id
ORDER BY c.customer_id;
```

### Solution 5: top 2

```sql
WITH revenue AS (
    SELECT
        o.customer_id,
        SUM(i.quantity * i.unit_price) AS amount
    FROM cte_lab.orders AS o
    JOIN cte_lab.order_items AS i
        ON i.order_id = o.order_id
    WHERE o.status = 'completed'
    GROUP BY o.customer_id
),
ranked AS (
    SELECT
        customer_id,
        amount,
        ROW_NUMBER() OVER (
            ORDER BY amount DESC, customer_id
        ) AS rn
    FROM revenue
)
SELECT
    c.customer_name,
    r.amount
FROM ranked AS r
JOIN cte_lab.customers AS c
    ON c.customer_id = r.customer_id
WHERE r.rn <= 2
ORDER BY r.rn;
```

### Solution 6: average order total

```sql
WITH completed_totals AS (
    SELECT
        o.order_id,
        SUM(i.quantity * i.unit_price) AS amount
    FROM cte_lab.orders AS o
    JOIN cte_lab.order_items AS i
        ON i.order_id = o.order_id
    WHERE o.status = 'completed'
    GROUP BY o.order_id
),
stats AS (
    SELECT AVG(amount) AS average_amount
    FROM completed_totals
)
SELECT
    t.order_id,
    t.amount,
    s.average_amount,
    t.amount > s.average_amount AS above_average
FROM completed_totals AS t
CROSS JOIN stats AS s
ORDER BY t.order_id;
```

The three orders have totals 250, 300, and 100; the average is roughly 216.67. Orders 1001 and 1003 are above average.

### Solution 7: materialization

```sql
EXPLAIN
WITH base AS MATERIALIZED (
    SELECT * FROM cte_lab.orders
)
SELECT order_id
FROM base
WHERE order_id = 1003;

EXPLAIN
WITH base AS NOT MATERIALIZED (
    SELECT * FROM cte_lab.orders
)
SELECT order_id
FROM base
WHERE order_id = 1003;
```

`MATERIALIZED` can create a boundary preventing the `order_id` predicate from being pushed into the source scan in the same way. `NOT MATERIALIZED` allows folding an eligible CTE so the optimizer can consider early filtering. Performance results must be measured on representative data.

### Solution 8: sequence 1–10

```sql
WITH RECURSIVE numbers(n) AS (
    SELECT 1
    UNION ALL
    SELECT n + 1
    FROM numbers
    WHERE n < 10
)
SELECT n
FROM numbers
ORDER BY n;
```

### Solution 9: category tree

```sql
WITH RECURSIVE tree AS (
    SELECT
        category_id,
        category_name,
        parent_id,
        0 AS depth
    FROM cte_lab.categories
    WHERE parent_id IS NULL

    UNION ALL

    SELECT
        c.category_id,
        c.category_name,
        c.parent_id,
        t.depth + 1
    FROM cte_lab.categories AS c
    JOIN tree AS t
        ON c.parent_id = t.category_id
)
SELECT category_id, category_name, depth
FROM tree
ORDER BY depth, category_id;
```

### Solution 10: descendants of category 11

```sql
WITH RECURSIVE branch AS (
    SELECT category_id, category_name, parent_id
    FROM cte_lab.categories
    WHERE category_id = 11

    UNION ALL

    SELECT c.category_id, c.category_name, c.parent_id
    FROM cte_lab.categories AS c
    JOIN branch AS b
        ON c.parent_id = b.category_id
)
SELECT category_id, category_name
FROM branch
ORDER BY category_id;
```

### Solution 11: category path

```sql
WITH RECURSIVE paths AS (
    SELECT
        category_id,
        parent_id,
        category_name::text AS path
    FROM cte_lab.categories
    WHERE parent_id IS NULL

    UNION ALL

    SELECT
        c.category_id,
        c.parent_id,
        p.path || ' / ' || c.category_name
    FROM cte_lab.categories AS c
    JOIN paths AS p
        ON c.parent_id = p.category_id
)
SELECT category_id, path
FROM paths
WHERE category_id = 13;
```

Answer: `Products / Books / Tech Books`. This query assumes the tree has no cycles reachable from roots; for untrusted sources, include a visited path or `CYCLE`.

### Solution 12: graph visited

```sql
WITH RECURSIVE walk AS (
    SELECT 1::bigint AS node_id,
           ARRAY[1::bigint] AS visited
    UNION ALL
    SELECT e.to_id, w.visited || e.to_id
    FROM walk AS w
    JOIN cte_lab.graph_edges AS e
        ON e.from_id = w.node_id
    WHERE NOT e.to_id = ANY(w.visited)
)
SELECT node_id, visited
FROM walk
ORDER BY visited;
```

### Solution 13: CYCLE

```sql
WITH RECURSIVE walk(node_id) AS (
    SELECT 1::bigint
    UNION ALL
    SELECT e.to_id
    FROM cte_lab.graph_edges AS e
    JOIN walk AS w ON e.from_id = w.node_id
)
CYCLE node_id SET is_cycle USING cycle_path
SELECT node_id, cycle_path
FROM walk
WHERE NOT is_cycle
ORDER BY cycle_path;
```

Use only when the server supports `CYCLE` (PostgreSQL 14+).

### Solution 14: moving jobs

```sql
WITH moved AS (
    DELETE FROM cte_lab.jobs
    WHERE job_status = 'completed'
    RETURNING job_id, job_status, payload
)
INSERT INTO cte_lab.jobs_archive (
    job_id, job_status, payload, archived_at
)
SELECT job_id, job_status, payload, now()
FROM moved
RETURNING job_id;
```

If the archive insert fails, the statement errors; changes within the same statement/transaction are not treated as successfully committed. Test on a lab copy because this SQL modifies data.

### Solution 15: CTE or VIEW?

- One-off report: a CTE is usually sufficient to organize multiple steps within a single statement.
- Query definition reused by multiple services: a view can fit if the team wants a named data interface in the schema with versioning and managed permissions. Also weigh parameterization needs and migration lifecycle.

### Solution 16: top three newest orders

```sql
WITH latest AS (
    SELECT order_id, customer_id, ordered_at
    FROM cte_lab.orders
    ORDER BY ordered_at DESC, order_id DESC
    LIMIT 3
)
SELECT
    l.order_id,
    c.customer_name,
    l.ordered_at
FROM latest AS l
JOIN cte_lab.customers AS c
    ON c.customer_id = l.customer_id
ORDER BY l.ordered_at DESC, l.order_id DESC;
```

### Solution 17: preventing row multiplication

Check how many tags each `customer_id` has before joining, comparing `COUNT(*)` and `COUNT(DISTINCT order_id)` at the appropriate grain. If you only need to check whether a customer has a tag, use `EXISTS`; if per-tag metrics are required, aggregate at the right grain before joining and define an allocation policy if one transaction belongs to multiple tags.

Do not use `SUM(DISTINCT amount)` as a general fix: two distinct orders can have the same amount.

### Solution 18: multi-level report

```sql
WITH eligible_orders AS (
    SELECT order_id, customer_id
    FROM cte_lab.orders
    WHERE status = 'completed'
),
order_totals AS (
    SELECT
        e.order_id,
        e.customer_id,
        SUM(i.quantity * i.unit_price) AS amount
    FROM eligible_orders AS e
    JOIN cte_lab.order_items AS i
        ON i.order_id = e.order_id
    GROUP BY e.order_id, e.customer_id
),
customer_summary AS (
    SELECT customer_id, SUM(amount) AS revenue
    FROM order_totals
    GROUP BY customer_id
)
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(s.revenue, 0) AS revenue
FROM cte_lab.customers AS c
LEFT JOIN customer_summary AS s
    ON s.customer_id = c.customer_id
ORDER BY revenue DESC, c.customer_id;
```

## 34. Summary

`WITH` in PostgreSQL lets you **structure a SQL statement into named steps**, clarifying intent and intermediate computations:

- A `SELECT` CTE is scoped to **a single statement**. It does not create a persistent table or view.
- A `WITH` clause can contain **multiple CTEs**; later CTEs build on earlier ones to separate filtering, JOIN, aggregation, and window function logic.
- In PostgreSQL 12+, a pure, non-recursive `SELECT` CTE meeting eligibility rules can be **folded** into the parent query. `MATERIALIZED` and `NOT MATERIALIZED` control certain optimization boundaries, though neither guarantees faster execution on its own.
- `WITH RECURSIVE` uses an **anchor + recursive term**, commonly via `UNION ALL`, to traverse trees and graphs. Termination conditions, cycle guards, and workload limits are essential.
- PostgreSQL 14+ supports `SEARCH` and `CYCLE` to construct traversal-order keys and detect repeated nodes in recursive CTEs; stable output sorting still requires `ORDER BY`.
- `WITH` can be combined with DML. For **data-modifying CTEs**, `RETURNING` is the official channel to pass modified data to the main statement; do not rely on inferred DML execution order from textual placement.
- CTEs do not replace transactions, constraints, indexes, views, or temporary tables. Nor do they automatically fix row-multiplying `JOIN`s, `NULL` bugs, wrong-grain aggregations, or SQL injection.

A good CTE query is one where every CTE name answers the question: **"What meaningful row set does this step transform the data into, at what grain, and how will the next step use it?"** Combined with result verification and `EXPLAIN`, `WITH` becomes a powerful tool for writing advanced PostgreSQL SQL that is both clear and dependable.
