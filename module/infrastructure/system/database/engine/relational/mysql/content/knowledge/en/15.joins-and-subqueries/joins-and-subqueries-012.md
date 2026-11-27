# LATERAL Derived Tables and Version Support

A derived table is a subquery placed in the `FROM` clause. Although the optimizer can merge or materialize a derived table depending on the query, a regular derived table cannot directly reference peer tables in the same `FROM` clause. Starting in MySQL 8.0.14, the `LATERAL` keyword allows a derived table to reference tables appearing before it in the same query block.

This capability is useful when each parent row needs its own subquery evaluation—for example, retrieving the three most recent orders for every customer, computing metrics from related rows, or running calculations based on columns of the current row. `LATERAL` explicitly expresses the correlation between the outer table and the subquery.

In the `DATABASE_MYSQL` module, `LATERAL` connects concepts across `JOIN`s, derived tables, correlated queries, indexes, and execution plans. This lesson covers version requirements, reference scoping, `JOIN` syntax, use cases, alternatives, and what to measure before deploying to production.

## 1. Regular Derived Tables and Reference Limitations

A derived table is a `SELECT` query placed in `FROM` and given an alias like a table within the scope of the enclosing query.

Example: order totals per customer:

```sql
SELECT
    c.customer_id,
    c.full_name,
    totals.order_count,
    totals.total_amount
FROM customers AS c
JOIN (
    SELECT
        customer_id,
        COUNT(*) AS order_count,
        SUM(total_amount) AS total_amount
    FROM orders
    GROUP BY customer_id
) AS totals
  ON totals.customer_id = c.customer_id;
```

The derived table `totals` aggregates the entire `orders` table by `customer_id` on its own. It does not directly reference `c.customer_id` from the outer query.

If you attempt to write a correlated predicate inside a regular derived table:

```sql
SELECT
    c.customer_id,
    recent.order_id
FROM customers AS c
JOIN (
    SELECT order_id
    FROM orders
    WHERE orders.customer_id = c.customer_id
    ORDER BY created_at DESC
    LIMIT 3
) AS recent;
```

MySQL raises an error because alias `c` belongs to the outer query block and is not in scope inside a regular derived table. This is the limitation `LATERAL` solves.

## 2. MySQL Versions Supporting LATERAL

MySQL supports lateral derived tables starting in **MySQL 8.0.14**.

| Version | LATERAL Derived Tables |
|---|---|
| MySQL 5.7 | Not supported |
| MySQL 8.0.11–8.0.13 | Not yet supported |
| MySQL 8.0.14 and later | Supported |
| MySQL 8.4 | Supported |

MySQL 8.0.14 is the milestone that introduced this feature. If an application runs MySQL 5.7 or MySQL 8.0.13 or earlier, queries containing `LATERAL` will not run under this syntax. You must either use a backward-compatible alternative or plan a server upgrade.

Check server version and distribution:

```sql
SELECT
    VERSION() AS mysql_version,
    @@version_comment AS distribution;
```

Do not infer support solely from a JDBC driver or ORM version. Check the target database server, because SQL statements are ultimately executed by the database server. For MariaDB or MySQL-compatible services, check the documentation for that specific product and version; do not assume syntax, optimizer behavior, or feature availability matches MySQL.

## 3. LATERAL Derived Table Syntax

Basic template:

```sql
SELECT ...
FROM parent_table AS p
JOIN LATERAL (
    SELECT ...
    FROM child_table AS c
    WHERE c.parent_id = p.parent_id
) AS related ON TRUE;
```

Components:

- `LATERAL` immediately precedes the parenthesized derived table.
- The derived table can reference columns from tables appearing before it in the same `FROM` clause.
- The derived table requires an alias, such as `related`.
- `ON TRUE` is commonly used when the entire correlation condition already lives inside the subquery.
- Use `JOIN LATERAL` or `CROSS JOIN LATERAL` to keep only parent rows with matching results; use `LEFT JOIN LATERAL` to retain parent rows without matches too.

`LATERAL` is not an independent `JOIN` type. It permits a derived table to contain correlated references; how rows are matched is still governed by `INNER`, `CROSS`, or `LEFT JOIN`.

## 4. Reference Scope and Table Ordering

A lateral derived table can reference tables appearing earlier in the `FROM` list or to the left of the corresponding `JOIN`. Therefore, place the table supplying the correlation values before the derived table:

```sql
SELECT
    c.customer_id,
    c.full_name,
    recent.order_id
FROM customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 1
) AS recent ON TRUE;
```

Here, `recent` references `c.customer_id`, because `customers AS c` appears before the lateral derived table.

You cannot reference a table that appears later as though it were already in scope:

```sql
-- Illustrating invalid reference scope
SELECT ...
FROM LATERAL (
    SELECT ...
    WHERE child.parent_id = p.parent_id
) AS x
JOIN parent_table AS p ON TRUE;
```

Alias `p` is not yet in scope when the derived table is declared. Reorder the `FROM` clause so the referenced table comes first.

In typical queries, place lateral derived tables on the right side of the `INNER JOIN`, `CROSS JOIN`, or `LEFT JOIN` they depend on. MySQL has specific scoping rules for `RIGHT JOIN`; if you need that construct, verify the exact rules for your running version. Rewriting joins in left-to-right order usually makes queries easier to read.

## 5. Primary Example: Fetching the N Latest Orders per Customer

Suppose we have two tables:

```sql
CREATE TABLE customers (
    customer_id BIGINT PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL
) ENGINE = InnoDB;

CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
) ENGINE = InnoDB;
```

Requirement: fetch up to the three newest orders for each customer.

```sql
SELECT
    c.customer_id,
    c.full_name,
    recent.order_id,
    recent.created_at,
    recent.total_amount
FROM customers AS c
LEFT JOIN LATERAL (
    SELECT
        o.order_id,
        o.created_at,
        o.total_amount
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 3
) AS recent ON TRUE
ORDER BY
    c.customer_id,
    recent.created_at DESC,
    recent.order_id DESC;
```

For each `customers` row, the subquery finds orders with the same `customer_id`, sorts newest first, and returns at most three rows. Thus `LIMIT 3` applies individually per customer.

`LEFT JOIN` preserves customers without orders. For a customer with no matching orders, columns from `recent` are `NULL`. If you use `JOIN LATERAL` or `CROSS JOIN LATERAL`, customers without matching orders are omitted from the result.

### 5.1. Why Is a Deterministic ORDER BY Needed?

Sorting solely by `created_at DESC` may not suffice if multiple orders share the exact same timestamp. Add `order_id DESC` as a tie-breaker to make ordering deterministic.

If you omit `ORDER BY`, MySQL has no obligation to pick the newest rows. If you omit `ORDER BY` on the outer query, final display order is not guaranteed either, even though the subquery used ordering to pick the top 3.

### 5.2. Adding Filters Inside the Subquery

You can filter for paid orders only:

```sql
SELECT
    c.customer_id,
    c.full_name,
    paid.order_id,
    paid.created_at,
    paid.total_amount
FROM customers AS c
LEFT JOIN LATERAL (
    SELECT
        o.order_id,
        o.created_at,
        o.total_amount
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 3
) AS paid ON TRUE
ORDER BY c.customer_id, paid.created_at DESC, paid.order_id DESC;
```

`status = 'PAID'` applies before `ORDER BY` and `LIMIT`, so the result is each customer's three newest paid orders—not the three newest orders overall subsequently filtered for `PAID`.

## 6. LEFT JOIN LATERAL and Handling Parent Rows Without Matches

Compare two approaches:

```sql
-- Keeps only customers with at least one order
SELECT c.customer_id, x.order_id
FROM customers AS c
JOIN LATERAL (
    SELECT o.order_id
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC
    LIMIT 1
) AS x ON TRUE;

-- Keeps all customers, even when they have no orders
SELECT c.customer_id, x.order_id
FROM customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC
    LIMIT 1
) AS x ON TRUE;
```

In the second query, customers without orders still appear with `x.order_id IS NULL`. If you want to add further conditions on the lateral result, carefully decide whether they belong inside the subquery or in `ON`.

For instance, placing `x.total_amount > 0` in the outer `WHERE` removes `NULL`-extended rows, effectively making `LEFT JOIN` behave like an inner join for that predicate. To preserve customers without matching results, filter inside the lateral derived table or place the condition appropriately in `ON`.

## 7. Using LATERAL to Compute Multiple Related Metrics per Parent Row

A correlated scalar subquery works well when you need a single value. When you need multiple metrics computed from the same child row set, a lateral derived table can return multiple columns in one declaration.

Example computing order count, total order value, and latest order date per customer:

```sql
SELECT
    c.customer_id,
    c.full_name,
    stats.order_count,
    stats.total_amount,
    stats.last_order_at
FROM customers AS c
LEFT JOIN LATERAL (
    SELECT
        COUNT(*) AS order_count,
        SUM(o.total_amount) AS total_amount,
        MAX(o.created_at) AS last_order_at
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
) AS stats ON TRUE;
```

The subquery is an ungrouped aggregate, so it returns one summary row even when there are no orders. When no child rows match, `COUNT(*)` returns 0, while `SUM()` and `MAX()` return `NULL`.

You can use `COALESCE(stats.total_amount, 0)` if business rules want to display zero total. Convert `NULL` to 0 only when both carry the exact same meaning in the report.

Never assume packing multiple calculations into one lateral subquery is always faster. The optimizer, indexes, parent row count, and child row count dictate cost. Compare it against a whole-table aggregated derived table when statistics are needed for nearly every customer.

## 8. LATERAL Enables Row-Dependent Calculations

Another use case is computing derived values from multiple columns of the current row and reusing those outputs in the query:

```sql
SELECT
    p.product_id,
    p.product_name,
    p.unit_price,
    pricing.discount_rate,
    p.unit_price * (1 - pricing.discount_rate) AS final_price
FROM products AS p
CROSS JOIN LATERAL (
    SELECT
        CASE
            WHEN p.unit_price >= 1000 THEN 0.15
            WHEN p.unit_price >= 500 THEN 0.10
            ELSE 0.05
        END AS discount_rate
) AS pricing;
```

This example illustrates expressing a set of calculations dependent on the outer row. For simple expressions, writing them directly in `SELECT` works fine; `LATERAL` is more helpful when the computation involves multiple expressions, benefits from grouping into a readable unit, or pairs with a subquery actually fetching related rows.

Do not use `LATERAL` merely to wrap a trivial addition. The query structure should clarify dependencies or enable reusing intermediate calculations.

## 9. Comparing LATERAL with Scalar Subqueries, EXISTS, and Derived Tables

| Need | Typically Suitable Construct | Characteristics |
|---|---|---|
| Fetch one value from a child table | Scalar correlated subquery | Returns a single value; must guard against multiple rows |
| Check whether related rows exist | `EXISTS` | Returns boolean without retrieving child columns |
| Aggregate data across all groups | Derived table + `GROUP BY` | Can aggregate the entire child table in one pass |
| Fetch multiple related rows per parent row | `LATERAL` derived table | Subquery can reference parent row data |
| Fetch top N rows per group | `LATERAL` + `ORDER BY`/`LIMIT` or window function | Picks N rows per group |
| Rank within partitions | `ROW_NUMBER`/`RANK`/`DENSE_RANK` | Ranks over a queried dataset |

### 9.1. LATERAL vs. Scalar Correlated Subquery

Example fetching the latest order timestamp:

```sql
SELECT
    c.customer_id,
    c.full_name,
    (
        SELECT MAX(o.created_at)
        FROM orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS last_order_at
FROM customers AS c;
```

A scalar subquery fits well because only one value is returned. If you need `order_id`, `created_at`, and `total_amount` together from the exact same latest order, a lateral query with `ORDER BY ... LIMIT 1` can fetch all columns from that single row.

### 9.2. LATERAL vs. EXISTS

If you only need to know whether a customer has a `PAID` order without returning individual order columns:

```sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
```

`EXISTS` directly expresses existence checking and is usually the simplest option. `LATERAL` fits when you need columns or multiple rows from the subquery.

### 9.3. LATERAL vs. Window Functions

MySQL 8.0 supports window functions. You can solve top-N-per-group using `ROW_NUMBER()`:

```sql
WITH ranked_orders AS (
    SELECT
        o.customer_id,
        o.order_id,
        o.created_at,
        o.total_amount,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.created_at DESC, o.order_id DESC
        ) AS rn
    FROM orders AS o
)
SELECT
    c.customer_id,
    c.full_name,
    r.order_id,
    r.created_at,
    r.total_amount
FROM customers AS c
LEFT JOIN ranked_orders AS r
  ON r.customer_id = c.customer_id
 AND r.rn <= 3
ORDER BY c.customer_id, r.created_at DESC, r.order_id DESC;
```

Both approaches can return the same result while generating different execution plans:

- `LATERAL` can perform a bounded index lookup per customer, which helps when the customer set is small and well-indexed.
- Window functions rank a large set of orders and join with customers, fitting well when processing most or all of the table.
- Measure on real data to choose the better plan. There is no universal rule that `LATERAL` always beats window functions or vice versa.

### 9.4. Alternatives on MySQL 5.7

MySQL 5.7 has neither `LATERAL` nor window functions. For fetching strictly one newest row per customer, you can use a scalar correlated subquery to pick that row's key and `JOIN` back:

[[FENCE]]sql
SELECT
    c.customer_id,
    c.full_name,
    o.order_id,
    o.created_at,
    o.total_amount
FROM customers AS c
LEFT JOIN orders AS o
  ON o.order_id = (
      SELECT o2.order_id
      FROM orders AS o2
      WHERE o2.customer_id = c.customer_id
      ORDER BY o2.created_at DESC, o2.order_id DESC
      LIMIT 1
  );
[[FENCE]]

The subquery returns a single `order_id` per customer; the outer `JOIN` fetches the remaining columns from that exact row. For top N greater than 1, MySQL 5.7 requires another approach, such as correlated rank counting or ranking in the application layer. Those workarounds can be expensive on large tables; consider upgrading to MySQL 8.0 for `LATERAL` or window functions, and measure plans on realistic data.

## 10. Indexes and Optimizing LATERAL Queries

`LATERAL` does not automatically make a query fast. Because the subquery typically depends on each parent row, indexes on the correlation column and sort order often determine most of the cost.

For the query fetching the three newest orders per customer:

```sql
CREATE INDEX idx_orders_customer_recent
    ON orders (customer_id, created_at DESC, order_id DESC);
```

The index leads with `customer_id` to locate a customer's slice of orders, then aligns with `created_at DESC, order_id DESC`. MySQL 8.0 supports descending indexes. With only an index on `(customer_id)`, the server may still need to sort each customer's orders.

Guidelines:

1. Place the equality correlation column (`customer_id`) first in the index.
2. Append the `ORDER BY` columns next.
3. If filtering by predicates like `status = 'PAID'`, evaluate whether adding `status` to the composite index pays off based on selectivity and access patterns.
4. Include returned columns in the index only when covering benefits are substantial and storage/write costs are acceptable.
5. Avoid creating near-duplicate indexes when one well-designed composite index serves your primary queries.

Example index including `status`:

```sql
CREATE INDEX idx_orders_customer_status_recent
    ON orders (
        customer_id,
        status,
        created_at DESC,
        order_id DESC
    );
```

This index can satisfy equality on `customer_id` and `status`, then scan in timestamp order. However, it is not equivalent to the previous index for queries that do not filter on `status`, because `status` sits between the prefix and sort columns. Check your workload before choosing between them.

## 11. Reading Execution Plans and Assessing Cost

Start with `EXPLAIN`:

```sql
EXPLAIN
SELECT
    c.customer_id,
    recent.order_id,
    recent.created_at
FROM customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id, o.created_at
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 3
) AS recent ON TRUE;
```

Inspect:

- Which access path reads the outer `customers` table.
- Whether the subquery uses an index starting with `customer_id`.
- Estimated rows read from `orders` per correlation key.
- Whether filesort or temporary tables occur.
- Signs of rematerializing the lateral derived table per outer row; exact display varies by version and `EXPLAIN` format.

On supported versions, `EXPLAIN ANALYZE` executes the `SELECT` and reports actual timings and row counts:

```sql
EXPLAIN ANALYZE
SELECT
    c.customer_id,
    recent.order_id
FROM customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 3
) AS recent ON TRUE;
```

`EXPLAIN ANALYZE` runs the real query. Only use it on safe `SELECT` queries, appropriate datasets, and after considering system load.

### 11.1. Estimating Subquery Executions

If the outer query returns 50,000 customers, the subquery may be evaluated for a vast number of parent rows. Conversely, if the outer query filters down to 20 customers and an index fetches three orders apiece instantly, `LATERAL` can be very efficient.

Therefore, filter the parent row set as early as possible when filtering does not alter semantics:

```sql
SELECT
    c.customer_id,
    recent.order_id,
    recent.created_at
FROM customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id, o.created_at
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 3
) AS recent ON TRUE
WHERE c.created_at >= '2026-01-01'
  AND c.status = 'ACTIVE';
```

With a suitable index on `customers`, MySQL can prune outer rows before running the correlated lateral step.

## 12. Limitations and Caveats

- **Version:** `LATERAL` derived tables require MySQL 8.0.14 or later.
- **Reference order:** place referenced tables before the lateral derived table in `FROM`.
- **Alias:** every derived table requires an alias.
- **Row counts:** one parent row can expand into multiple result rows if the lateral subquery returns multiple rows.
- **`LEFT JOIN`:** preserves parent rows with no match; derived table columns are `NULL`-extended.
- **`ORDER BY`:** use inside the subquery to define top N; use an outer `ORDER BY` to guarantee final output order.
- **Performance:** lateral queries may be evaluated repeatedly per parent row; add indexes and measure execution plans.
- **`NULL`:** correlation predicates using `=` do not match `NULL` values; if business rules require matching `NULL`s, define semantics explicitly.
- **`RIGHT JOIN`:** has special reference-scoping rules; prefer rewriting in clear left-to-right `JOIN` order when possible.
- **Large datasets:** do not pick `LATERAL` purely for shorter syntax; window functions or pre-aggregation may scale better.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using `LATERAL` on MySQL 5.7 | Server rejects syntax | Check `VERSION()`; use a compatible alternative |
| Forgetting the `LATERAL` keyword | Derived table cannot reference peer outer tables | Add `LATERAL` before the subquery |
| Placing the derived table before the table it references | Alias is not yet in scope | Reorder `FROM`/`JOIN` clauses |
| Omitting the derived table alias | Invalid SQL statement | Add an alias right after the closing parenthesis |
| Using `JOIN LATERAL` when intending to keep parent rows without matches | Parent rows lacking child rows are dropped | Use `LEFT JOIN LATERAL ... ON TRUE` |
| Using `LIMIT` without `ORDER BY` | Selected rows are non-deterministic | Add business ordering and a tie-breaker |
| Putting `ORDER BY` only inside the subquery | Final result order is not guaranteed | Add `ORDER BY` to the outer query |
| Assuming `LATERAL` always beats window functions | Can repeatedly run subqueries across a huge parent set | Compare `EXPLAIN ANALYZE` plans |
| Missing index on the correlation key | Subquery scans too many rows | Design an index starting with the correlation key |

## 14. Comprehensive Practice

Using `customers` and `orders` tables in a lab database:

1. Check server version with `SELECT VERSION()`.
2. Create an index `(customer_id, created_at DESC, order_id DESC)` on `orders`.
3. Write a `JOIN LATERAL` query to get the newest order for each customer.
4. Change it to `LEFT JOIN LATERAL` and insert a customer with no orders to observe `NULL` columns.
5. Change `LIMIT 1` to `LIMIT 3` to fetch the top 3 orders per customer.
6. Add `status = 'PAID'` inside the subquery and confirm the order of filtering, sorting, and limiting.
7. Rewrite the same requirement using `ROW_NUMBER() OVER (PARTITION BY ...)`.
8. Run `EXPLAIN` and `EXPLAIN ANALYZE` to compare access paths and actual row counts.
9. Test with small and large customer sets to see how cost scales with outer row count.
10. Explain when scalar subqueries, `EXISTS`, pre-aggregation, or window functions are clearer and more suitable.

## 15. Summary

- Regular derived tables cannot directly reference other tables in the same `FROM`; `LATERAL` enables correlated references.
- MySQL supports `LATERAL` derived tables starting in version 8.0.14.
- Place `LATERAL` before the subquery and place referenced tables earlier in `FROM`.
- Derived tables require an alias; `ON TRUE` is commonly used when correlation predicates live inside the subquery.
- `JOIN LATERAL` drops parent rows without matches; `LEFT JOIN LATERAL` retains parent rows and pads child columns with `NULL`.
- `LATERAL` fits top-N per parent row, multi-column correlated metrics, and row-dependent calculations.
- Use `ORDER BY` with a tie-breaker before `LIMIT`; add an outer `ORDER BY` when final output order matters.
- Indexes should generally lead with the correlation column, followed by relevant filter and sort columns.
- `LATERAL` may be evaluated per outer row; compare against window functions and pre-aggregation using execution plans.
- Check server version, indexes, outer row counts, and child row counts before deploying.

Use `LATERAL` when a subquery genuinely needs data from a preceding row and must return a related result set for each row. Combining the right `JOIN` type, reference order, and indexes keeps queries clear, semantically accurate, and predictable in cost.
