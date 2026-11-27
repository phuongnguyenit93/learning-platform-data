# Scalar Subqueries and the At-Most-One-Row Constraint

## Objectives

After this lesson, you will be able to:

- Identify a scalar subquery and distinguish it from subqueries that return multiple rows or multiple columns.
- Explain the behavior when a subquery returns 0, 1, or more than 1 row.
- Handle `Subquery returns more than 1 row` and multi-column subquery errors.
- Guarantee a subquery returns at most one row using unique keys, aggregate functions, or `ORDER BY ... LIMIT 1`.
- Write correlated scalar subqueries in `SELECT`, `WHERE`, and other expressions.
- Handle `NULL`, verify uniqueness, and choose between scalar subqueries, `IN`, `EXISTS`, or `JOIN`.
- Evaluate performance using indexes and `EXPLAIN`.

## 1. What Is a Scalar Subquery?

A scalar subquery is a subquery used wherever a single value is expected. It must return exactly one column and must not return more than one row. The value of that row becomes the result of the expression.

For example, fetching the name of customer 101:

```sql
SELECT
    (SELECT full_name
     FROM customers
     WHERE customer_id = 101) AS customer_name;
```

If `customer_id` is a primary key, the subquery can find at most one customer. The result is that customer's name; if no customer with ID 101 exists, the scalar result is `NULL`.

Scalar subqueries can appear in many places that take a single expression:

- Inside a `SELECT` list to compute a result column.
- Inside `WHERE` or `HAVING` conditions to compare against a value.
- Inside arithmetic expressions, `CASE`, `COALESCE()`, or assignments.
- Inside `INSERT` or `UPDATE` statements where statement context and rules allow.

Example:

```sql
SELECT product_id, product_name, price
FROM products
WHERE price > (
    SELECT AVG(price)
    FROM products
);
```

The subquery computes the average price across all products; the outer query selects products priced above that scalar value.

## 2. Row and Column Rules for Scalar Subqueries

A scalar subquery must return one column. For row counts, there are three cases:

| Rows Returned by Subquery | Behavior |
|---:|---|
| 0 rows | The scalar value evaluates to `NULL` |
| 1 row | The value of the single column in that row |
| More than 1 row | MySQL raises error `1242: Subquery returns more than 1 row` |

If a subquery returns more than one column in a scalar context, MySQL raises error `1241: Operand should contain 1 column(s)`.

### 2.1. Zero Rows: Result Is NULL

```sql
SELECT
    (SELECT full_name
     FROM customers
     WHERE customer_id = -1) AS customer_name;
```

If there is no customer with ID `-1`, the expression returns `NULL`. The outer query can still return a row because the subquery is just one expression in the `SELECT` list.

### 2.2. Exactly One Row: Returns the Value

```sql
SELECT
    (SELECT full_name
     FROM customers
     WHERE customer_id = 101) AS customer_name;
```

If exactly one customer matches, the expression evaluates to that row's `full_name`.

### 2.3. Multiple Rows: Error 1242

```sql
SELECT
    (SELECT status
     FROM orders
     WHERE customer_id = 101) AS one_status;
```

A customer can have multiple orders, so the subquery may return multiple statuses. In a scalar context, MySQL neither picks one row automatically nor concatenates values; the statement fails with error 1242.

### 2.4. Multiple Columns: Error 1241

```sql
-- Invalid in a scalar context
SELECT (
    SELECT customer_id, full_name
    FROM customers
    WHERE customer_id = 101
);
```

A scalar subquery may return only one column. If you need multiple columns from a related row, use `JOIN` or a row-returning construct rather than forcing multiple columns into a scalar expression.

### 2.5. One Row with a NULL Value Also Yields NULL

If a subquery finds one row whose selected column is `NULL`, the scalar result is also `NULL`. Therefore, seeing a scalar result of `NULL` alone cannot definitively distinguish between two scenarios:

- No matching row was found.
- One row was found, and its column value is `NULL`.

If business logic needs to tell them apart, also check `EXISTS()` or return a presence indicator alongside the value via `JOIN`.

## 3. Guaranteeing At Most One Row with Unique Keys

The cleanest approach when business logic expects a single record is expressing that rule in the schema via `PRIMARY KEY` or `UNIQUE`.

Example:

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(255) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_email (email)
) ENGINE = InnoDB;
```

Lookup by primary key:

```sql
SELECT
    (SELECT full_name
     FROM customers
     WHERE customer_id = 101) AS customer_name;
```

Lookup by unique key:

```sql
SELECT
    (SELECT customer_id
     FROM customers
     WHERE email = 'an@example.com') AS customer_id;
```

Because `email` has a unique constraint, an equality predicate on a non-NULL email can match at most one row under the column's collation.

### 3.1. Note on UNIQUE and NULL

In MySQL, a unique index allows multiple rows to hold `NULL` in a nullable column. Therefore, a unique constraint does not guarantee a single row when a query uses `IS NULL` on that column.

Example:

```sql
CREATE TABLE external_accounts (
    account_id BIGINT NOT NULL AUTO_INCREMENT,
    external_code VARCHAR(80) NULL,
    PRIMARY KEY (account_id),
    UNIQUE KEY uq_external_code (external_code)
);

INSERT INTO external_accounts (external_code)
VALUES (NULL), (NULL);
```

Two rows can coexist with `external_code IS NULL`. Thus, the following subquery can return multiple rows:

```sql
SELECT (
    SELECT account_id
    FROM external_accounts
    WHERE external_code IS NULL
);
```

Never assume `UNIQUE` guarantees one row for every predicate. Account for nullability, comparison operators, and all columns of the unique key.

### 3.2. Collation Also Governs Uniqueness

For a unique key on strings, collation determines whether two values are considered equal. If a column uses a case-insensitive collation, `An@example.com` and `an@example.com` can collide on the unique key. This also affects scalar subquery string lookups.

When designing unique keys, clearly specify case/accent sensitivity rules and normalize data consistently in the application.

## 4. Guaranteeing One Row with Aggregate Functions

An aggregate function without `GROUP BY` normally returns one row for the entire input set, even when no source rows match. This is a reliable way to produce a scalar value.

### 4.1. MAX, MIN, AVG, and SUM

```sql
SELECT
    customer_id,
    (SELECT MAX(total_amount)
     FROM orders AS o
     WHERE o.customer_id = c.customer_id) AS largest_order,
    (SELECT AVG(total_amount)
     FROM orders AS o
     WHERE o.customer_id = c.customer_id) AS average_order
FROM customers AS c;
```

Each subquery uses an aggregate function with no `GROUP BY`, so it produces one result row per customer in the outer query.

If a customer has no orders yet:

- `MAX()` and `MIN()` return `NULL`.
- `AVG()` returns `NULL`.
- `SUM()` returns `NULL`.
- `COUNT(*)` returns `0`.

Example:

```sql
SELECT
    (SELECT COUNT(*)
     FROM orders
     WHERE customer_id = 9999) AS order_count,
    (SELECT MAX(total_amount)
     FROM orders
     WHERE customer_id = 9999) AS largest_order;
```

If the customer has no orders, `order_count` is 0 and `largest_order` is `NULL`.

### 4.2. GROUP BY Can Cause a Subquery to Return Multiple Rows

Using an aggregate function does not automatically guarantee one row:

```sql
-- May return multiple rows because it groups by status
SELECT (
    SELECT COUNT(*)
    FROM orders
    WHERE customer_id = 101
    GROUP BY status
);
```

If the customer has orders in multiple statuses, the subquery produces one row per status and triggers error 1242. If you want the total order count, omit `GROUP BY status`. If you want counts per status, use a multi-row query or `JOIN` with a derived table.

### 4.3. HAVING Can Eliminate the Aggregate Row

An aggregate query without `GROUP BY` normally produces one row, yet `HAVING` can still filter out that row:

```sql
SELECT (
    SELECT MAX(total_amount)
    FROM orders
    WHERE customer_id = 101
    HAVING COUNT(*) > 0
);
```

If the customer has no orders, `HAVING COUNT(*) > 0` discards the aggregate row, making the subquery return 0 rows and the scalar evaluate to `NULL`. Keep `HAVING` predicates in mind whenever relying on the single-row property of aggregates.

## 5. Selecting One Row Intentionally with ORDER BY and LIMIT 1

When you need the latest, oldest, highest-priority, or top-ranked record, you can use `ORDER BY ... LIMIT 1`.

Example fetching the latest status for each order:

```sql
SELECT
    o.order_id,
    (
        SELECT h.status
        FROM order_status_history AS h
        WHERE h.order_id = o.order_id
        ORDER BY h.changed_at DESC, h.history_id DESC
        LIMIT 1
    ) AS latest_status
FROM orders AS o;
```

`LIMIT 1` guarantees the subquery returns at most one row. `history_id DESC` acts as a tie-breaker when multiple events share the same `changed_at`, making the result deterministic.

### 5.1. LIMIT 1 Does Not Replace Business Rules

Example:

```sql
SELECT (
    SELECT status
    FROM orders
    WHERE customer_id = 101
    LIMIT 1
);
```

This statement avoids error 1242, but if the customer has multiple orders, MySQL is free to pick any row with no deterministic business ordering. The result can change depending on the execution plan or data state.

If you want the newest order, write:

```sql
SELECT (
    SELECT status
    FROM orders
    WHERE customer_id = 101
    ORDER BY created_at DESC, order_id DESC
    LIMIT 1
);
```

If you want the highest-value order, use `ORDER BY total_amount DESC, order_id DESC LIMIT 1` or `MAX(total_amount)` depending on your goal. `MAX()` returns only the maximum value; `ORDER BY ... LIMIT 1` can retrieve any column from the chosen row.

### 5.2. OFFSET 0 and Limiting Syntax

In subqueries, the standard syntax is `ORDER BY ... LIMIT 1`. `LIMIT 1 OFFSET 0` is equivalent but unnecessary. Using `LIMIT 1` without `ORDER BY` only caps the row count without specifying which row gets selected.

### 5.3. LIMIT 1 Can Mask Duplicate Data

If business rules require an email or external code to be unique, never slap on `LIMIT 1` just to make a query succeed when duplicate data exists. Doing so hides data integrity violations and picks an arbitrary record.

Audit for duplicates and fix the schema with a unique constraint where appropriate. Use `LIMIT 1` only when business logic genuinely wants one row according to a defined ordering, such as the most recent event.

## 6. Correlated Scalar Subqueries

A correlated subquery references columns from the outer query. For each outer row, the inner query uses that row's values to compute its result.

Example fetching the order count for each customer:

```sql
SELECT
    c.customer_id,
    c.full_name,
    (
        SELECT COUNT(*)
        FROM orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS order_count
FROM customers AS c;
```

`c.customer_id` is a reference from the outer query. The subquery is scoped to each customer and returns a single scalar count.

### 6.1. Comparing Against a Group's Own Average

Fetch orders whose total exceeds that customer's own average order amount:

```sql
SELECT
    o.order_id,
    o.customer_id,
    o.total_amount
FROM orders AS o
WHERE o.total_amount > (
    SELECT AVG(o2.total_amount)
    FROM orders AS o2
    WHERE o2.customer_id = o.customer_id
);
```

The subquery computes the average for the outer row's `customer_id`. Because `AVG()` has no `GROUP BY`, each evaluation returns one row. If the average is `NULL`, the `>` comparison evaluates to UNKNOWN and the row is not selected.

### 6.2. Fetching the Latest Row per Group

```sql
SELECT
    c.customer_id,
    c.full_name,
    (
        SELECT o.order_id
        FROM orders AS o
        WHERE o.customer_id = c.customer_id
        ORDER BY o.created_at DESC, o.order_id DESC
        LIMIT 1
    ) AS latest_order_id
FROM customers AS c;
```

Customers with no orders receive `NULL` for `latest_order_id`. Every customer still has a row in the output because the outer query starts from `customers`.

### 6.3. Distinguishing Correlated vs. Non-Correlated Subqueries

A non-correlated subquery does not reference any column from the outer query:

```sql
SELECT product_id, product_name, price
FROM products
WHERE price > (
    SELECT AVG(price)
    FROM products
);
```

A correlated subquery contains outer references such as `o.customer_id = c.customer_id`. The optimizer can transform or optimize certain subquery shapes, so never assume every correlated subquery literally re-executes from scratch for each row. Inspect the execution plan and measure actual performance.

## 7. Scalar Subqueries in SELECT, WHERE, and HAVING

### 7.1. In the SELECT List

```sql
SELECT
    p.product_id,
    p.product_name,
    p.price,
    (SELECT AVG(price) FROM products) AS overall_average_price
FROM products AS p;
```

Each product row displays the overall table average price alongside its own price. Because the subquery is non-correlated, the same value applies across all output rows.

### 7.2. In WHERE

```sql
SELECT product_id, product_name, price
FROM products
WHERE price = (
    SELECT MAX(price)
    FROM products
);
```

This query returns products priced at the maximum price. Multiple products may share the highest price; that causes no error because the scalar subquery returns only one `MAX` value, while the outer query may return multiple rows.

### 7.3. In HAVING

```sql
SELECT
    customer_id,
    SUM(total_amount) AS customer_revenue
FROM orders
GROUP BY customer_id
HAVING SUM(total_amount) > (
    SELECT AVG(customer_total)
    FROM (
        SELECT SUM(total_amount) AS customer_total
        FROM orders
        GROUP BY customer_id
    ) AS customer_totals
);
```

The derived subquery computes revenue per customer; the outer scalar subquery takes the average of those totals. Derived tables require an alias (`customer_totals`) in MySQL.

## 8. NULLs and Comparisons with Scalar Subqueries

If a scalar subquery returns `NULL`, standard comparisons usually evaluate to UNKNOWN:

```sql
SELECT product_id, product_name
FROM products
WHERE price > (
    SELECT MAX(price)
    FROM products
    WHERE category_id = -1
);
```

If there are no products in category `-1`, `MAX(price)` is `NULL`. `price > NULL` is not TRUE, so the query returns zero rows.

### 8.1. Using COALESCE When a Valid Fallback Exists

```sql
SELECT product_id, product_name, price
FROM products
WHERE price > COALESCE(
    (SELECT AVG(price)
     FROM products
     WHERE category_id = 10),
    0
);
```

This example replaces `NULL` with 0. Only use this when 0 is a valid fallback under business rules. Do not apply `COALESCE(..., 0)` mechanically, as it can turn "no data" into a number with a different business meaning.

### 8.2. Distinguishing Missing Rows from NULL Values

Because a scalar subquery returns `NULL` in both cases, you can pair it with `EXISTS`:

```sql
SELECT
    c.customer_id,
    EXISTS (
        SELECT 1
        FROM customer_profiles AS p
        WHERE p.customer_id = c.customer_id
    ) AS profile_exists,
    (
        SELECT p.nickname
        FROM customer_profiles AS p
        WHERE p.customer_id = c.customer_id
    ) AS nickname
FROM customers AS c;
```

If `profile_exists = 0`, no profile exists. If `profile_exists = 1` and `nickname IS NULL`, the profile exists but no nickname has been set yet. To ensure the second scalar subquery does not fail, `customer_profiles.customer_id` must be guaranteed unique, such as by a primary key or unique constraint.

### 8.3. Do Not Use = NULL

If you want to check whether a scalar result is `NULL`, use `IS NULL`:

```sql
SELECT product_id
FROM products
WHERE (
    SELECT MAX(price)
    FROM products
    WHERE category_id = 10
) IS NULL;
```

Never write `= NULL`, because standard equality comparisons with `NULL` return UNKNOWN.

## 9. When to Use Scalar Subquery, IN, EXISTS, or JOIN?

These subquery and join constructs are not interchangeable in every situation:

| Construct | Expected Subquery Output | When to Use |
|---|---|---|
| Scalar subquery | One column, at most one row | Need a single value such as MAX, AVG, name by unique key, or top-1 row |
| `IN (subquery)` | One column, possibly multiple rows | Checking whether a value belongs to a set of values |
| `EXISTS (subquery)` | Checks whether any matching row exists | Only need to know whether a relationship exists |
| `JOIN` | Pairs rows and can return multiple columns | Need data from both tables or row-to-row relationships |

### 9.1. Scalar Subquery vs. IN

Do not use `=` with a subquery that may return multiple rows:

```sql
-- May raise error 1242 if a customer has multiple orders
SELECT customer_id
FROM customers
WHERE customer_id = (
    SELECT customer_id
    FROM orders
    WHERE status = 'PAID'
);
```

If the goal is finding customers with at least one paid order, use `IN`:

```sql
SELECT customer_id, full_name
FROM customers
WHERE customer_id IN (
    SELECT customer_id
    FROM orders
    WHERE status = 'PAID'
);
```

Or use `EXISTS`, which often expresses correlated relationships clearly:

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

### 9.2. Scalar Subquery vs. JOIN

If you need multiple columns from the latest row, writing one scalar subquery per column makes the query hard to read and duplicates logic. Use a derived table or window function depending on your MySQL version.

Example using `ROW_NUMBER()` in MySQL 8.0:

```sql
WITH ranked_history AS (
    SELECT
        h.order_id,
        h.status,
        h.changed_at,
        ROW_NUMBER() OVER (
            PARTITION BY h.order_id
            ORDER BY h.changed_at DESC, h.history_id DESC
        ) AS rn
    FROM order_status_history AS h
)
SELECT
    o.order_id,
    rh.status AS latest_status,
    rh.changed_at AS latest_changed_at
FROM orders AS o
LEFT JOIN ranked_history AS rh
  ON rh.order_id = o.order_id
 AND rh.rn = 1;
```

`JOIN` fits when you need multiple columns from the selected row. Scalar subqueries fit when you need only one value and the expression stays readable.

### 9.3. Beware of NOT IN and NULL

If the subquery inside `NOT IN` returns even one `NULL` value, the check can become UNKNOWN and return no rows as expected. When checking "no related row exists," `NOT EXISTS` is usually easier to reason about:

```sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
```

This is an existence check, not a scalar subquery. Choose the construct based on logical semantics rather than brevity alone.

## 10. Performance and Indexes for Scalar Subqueries

Scalar subqueries can be very efficient when the lookup condition uses an index and reads only one value. However, a correlated subquery over a large outer set can trigger many lookups; always check the execution plan.

### 10.1. Indexing Foreign Key Lookups

Example counting orders per customer:

```sql
SELECT
    c.customer_id,
    (SELECT COUNT(*)
     FROM orders AS o
     WHERE o.customer_id = c.customer_id) AS order_count
FROM customers AS c;
```

An index on `orders(customer_id)` helps locate each customer's orders. InnoDB normally requires an appropriate index for a foreign key, though if there is no constraint or a different schema is used, inspect the actual indexes.

### 10.2. Indexing for Latest-Row Lookups

For the subquery:

```sql
SELECT h.status
FROM order_status_history AS h
WHERE h.order_id = ?
ORDER BY h.changed_at DESC, h.history_id DESC
LIMIT 1;
```

A suitable index might be:

```sql
CREATE INDEX idx_history_order_changed_id
ON order_status_history (order_id, changed_at DESC, history_id DESC);
```

The index places the equality filter column `order_id` first, followed by the sort columns. MySQL 8.0 supports descending indexes; verify the plan and effectiveness on your target version.

### 10.3. Indexing for Grouped MAX

For:

```sql
SELECT MAX(total_amount)
FROM orders
WHERE customer_id = ?;
```

An index `(customer_id, total_amount)` can support finding the maximum value within a customer's range. The optimizer may apply a MIN/MAX optimization strategy when conditions permit, but do not assume every aggregate query reads only a single index entry. Check `EXPLAIN` and measure in practice.

### 10.4. Inspecting the Execution Plan

```sql
EXPLAIN
SELECT
    c.customer_id,
    (
        SELECT h.status
        FROM order_status_history AS h
        WHERE h.order_id = o.order_id
        ORDER BY h.changed_at DESC, h.history_id DESC
        LIMIT 1
    ) AS latest_status
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id;
```

Inspect how outer and inner tables are accessed, which indexes are chosen, estimated row counts, and subquery types. Column and alias names in this example are illustrative; real schemas must have the corresponding keys.

MySQL 8.0.18 and later support `EXPLAIN ANALYZE` for eligible `SELECT` statements. This command actually runs the query to measure row counts and timings, so test on appropriate data and environments before running it on heavy production queries.

### 10.5. When to Switch to JOIN or Pre-Aggregation

If a correlated scalar subquery runs over hundreds of thousands of outer rows and each lookup scans significant data, consider:

- Adding an index for the correlation condition.
- Aggregating child data by key in a derived table and joining it.
- Using window functions to rank rows per group in MySQL 8.0.
- Splitting the query to fetch the target key set first before looking up details.

Do not mechanically rewrite every scalar subquery as a `JOIN`. The optimizer can optimize scalar subqueries well; compare execution plans, actual row counts, and latency before refactoring.

## 11. Common Errors and How to Fix Them

| Error / Situation | Cause | Fix |
|---|---|---|
| `Subquery returns more than 1 row` (1242) | Subquery used in a scalar context returns multiple rows | Verify uniqueness; use an aggregate, `ORDER BY ... LIMIT 1`, `IN`, `EXISTS`, or `JOIN` as appropriate |
| `Operand should contain 1 column(s)` (1241) | Scalar subquery returns multiple columns | Select only one expression or switch to `JOIN` |
| Using `LIMIT 1` gives inconsistent results | Missing `ORDER BY` or unique tie-breaker | Specify complete deterministic business ordering |
| Using `LIMIT 1` to hide duplicates | Data violates uniqueness rules | Audit duplicates and add a unique constraint if appropriate |
| Comparison against a `NULL` subquery returns no rows | Subquery has 0 rows or aggregate returns `NULL`; comparison becomes UNKNOWN | Clarify `NULL` semantics, using `IS NULL`, `COALESCE`, or `EXISTS` as needed |
| `UNIQUE` column yet `IS NULL` subquery returns multiple rows | MySQL allows multiple `NULL`s in a unique index | Enforce `NOT NULL` if business rules require it or handle `NULL` separately |
| Slow correlated subquery | Correlation predicate lacks an index or performs many lookups | Check `EXPLAIN`, add an appropriate index, or compare with `JOIN`/derived table |
| `GROUP BY` makes scalar subquery return multiple rows | Multiple result groups exist | Remove `GROUP BY` if a single whole-set aggregate is needed, or use a multi-row query |

## 12. Workflow for Designing Safe Scalar Subqueries

1. **Identify the needed value:** an aggregate number, a unique attribute, or a top-priority row?
2. **Determine cardinality:** is the condition protected by a primary key or unique key? Could multiple rows match?
3. **Choose how to guarantee at most one row:** unique constraint, ungrouped aggregate, or `ORDER BY ... LIMIT 1` with explicit deterministic ordering.
4. **Handle missing data:** accept `NULL`, substitute a business default via `COALESCE()`, or distinguish absence using `EXISTS`?
5. **Check NULLs in keys:** nullable unique keys can allow multiple `NULL` rows.
6. **Pick the right subquery type:** scalar for one value; `IN` for a set of values; `EXISTS` for existence checks; `JOIN` for multiple columns/rows.
7. **Add appropriate indexes:** prioritize correlation predicates and top-row sort orders.
8. **Check the execution plan:** use `EXPLAIN` and measure on production-scale data.
9. **Test edge cases:** 0 rows, 1 row, multiple rows, `NULL` columns, duplicate data, and ties in sort keys.

## 13. Practice Queries

The following queries use the illustrative schema `customers`, `orders`, and `order_status_history`.

### Exercise 1: Get Total Order Count per Customer

```sql
SELECT
    c.customer_id,
    c.full_name,
    (SELECT COUNT(*)
     FROM orders AS o
     WHERE o.customer_id = c.customer_id) AS order_count
FROM customers AS c
ORDER BY c.customer_id;
```

### Exercise 2: Get the Largest Order Amount per Customer

```sql
SELECT
    c.customer_id,
    (SELECT MAX(o.total_amount)
     FROM orders AS o
     WHERE o.customer_id = c.customer_id) AS largest_order_amount
FROM customers AS c;
```

### Exercise 3: Get the Latest Order ID per Customer

```sql
SELECT
    c.customer_id,
    (SELECT o.order_id
     FROM orders AS o
     WHERE o.customer_id = c.customer_id
     ORDER BY o.created_at DESC, o.order_id DESC
     LIMIT 1) AS latest_order_id
FROM customers AS c;
```

### Exercise 4: Get Products Priced Above the Overall Average

```sql
SELECT product_id, product_name, price
FROM products
WHERE price > (SELECT AVG(price) FROM products);
```

### Exercise 5: Find Customers Without Any Orders

```sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
```

Exercise 5 uses `NOT EXISTS` because the goal is checking for the absence of related rows; there is no reason to force the subquery into a scalar form.

## 14. Pre-Production Checklist

- [ ] Subquery returns exactly one column in every scalar context.
- [ ] Verified the subquery returns at most one row via constraints or query logic.
- [ ] When using `LIMIT 1`, included `ORDER BY` and a unique tie-breaker.
- [ ] Did not use `LIMIT 1` to mask duplicate data that violates business rules.
- [ ] Defined behavior when the subquery returns 0 rows or `NULL`.
- [ ] Accounted for unique keys allowing multiple `NULL`s.
- [ ] Chose scalar, `IN`, `EXISTS`, or `JOIN` according to true semantics.
- [ ] Correlated subqueries have indexes supporting lookup predicates.
- [ ] Inspected `EXPLAIN` and measured against realistic data.
- [ ] Tested 0-row, 1-row, and multi-row cases, including duplicates and `NULL`s.

## 15. Conclusion

A scalar subquery supplies a single value to a SQL expression. It must return one column and at most one row: zero rows yields `NULL`, one row yields the value, multiple rows raises error 1242, and multiple columns raises error 1241.

Use primary key/unique constraints when business rules enforce uniqueness, ungrouped aggregates when a single summary value is needed, or `ORDER BY ... LIMIT 1` when you genuinely want one row by a deterministic ordering. Handle `NULL`s carefully, distinguish scalar subqueries from `IN`/`EXISTS`/JOINs, and inspect correlated subqueries with execution plans so queries remain both accurate and performant.
