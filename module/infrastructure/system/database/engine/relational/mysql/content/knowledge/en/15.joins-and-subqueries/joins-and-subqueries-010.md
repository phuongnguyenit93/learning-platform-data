# IN, NOT IN, and the NULL Trap in Subqueries

When finding customers who have placed an order, you can use `IN` with a subquery to check whether `customer_id` appears in the orders set. When finding customers who have never placed an order, `NOT IN` looks like the natural symmetric choice. Yet if the subquery returns even a single `NULL` value, `NOT IN` can return zero customers even though many customers have never placed an order.

The cause lies in SQL's three-valued logic: `TRUE`, `FALSE`, and `UNKNOWN`. In SQL, `NULL` represents an unknown or missing value; comparing against `NULL` typically yields `UNKNOWN` rather than `TRUE` or `FALSE`. This lesson belongs to the **DATABASE_MYSQL** module and focuses on the semantics of `IN`, `NOT IN`, how `NULL` propagates through subqueries, and safe ways to write anti-joins.

## 1. IN Tests Membership in a Set of Values

`IN` checks whether the left-hand expression equals any value in the right-hand list or result set.

```sql
SELECT customer_id, full_name
FROM customers
WHERE customer_id IN (101, 205, 309);
```

This query returns customers whose ID belongs to the list. You can use a subquery to produce the value set dynamically:

```sql
SELECT customer_id, full_name
FROM customers
WHERE customer_id IN (
    SELECT customer_id
    FROM orders
    WHERE status = 'PAID'
);
```

Meaning: retrieve customers whose `customer_id` appears in at least one paid order. Duplicate values in the subquery result do not alter membership outcomes; `IN` only needs to know whether at least one matching value exists.

A subquery used with `IN` must return one column when comparing a single expression. MySQL also supports multi-column tuple comparisons in applicable contexts, though basic examples usually use a single column.

## 2. NOT IN Is the Negation of IN

`NOT IN` checks that the left-hand expression does not equal any value in the right-hand set:

```sql
SELECT customer_id, full_name
FROM customers
WHERE customer_id NOT IN (
    SELECT customer_id
    FROM orders
);
```

The usual goal is finding customers without orders. If `orders.customer_id` is always `NOT NULL`, this query can express the intent accurately. However, if that column allows `NULL`, carefully examine semantics before using it.

Logically, `IN` is equivalent to equality with at least one element (`= ANY`); `NOT IN` is equivalent to inequality with every element (`<> ALL`). Therefore, the outcome depends both on whether a matching value exists and on whether the right-hand set contains `NULL`.

## 3. SQL Has Three Logical Values

In SQL, conditional expressions are not restricted to `TRUE` and `FALSE`. When a comparison cannot be resolved because of `NULL`, the result is `UNKNOWN`.

Example:

```sql
SELECT
    10 = 10 AS is_equal,
    10 = 20 AS is_not_equal,
    10 = NULL AS compare_with_null,
    NULL = NULL AS compare_two_nulls;
```

In MySQL output, the results are `1`, `0`, `NULL`, and `NULL` respectively. `NULL = NULL` is not `TRUE`: two unknown values are not assumed equal.

In a `WHERE` clause, only rows whose predicate evaluates to `TRUE` are kept. Both `FALSE` and `UNKNOWN` are discarded:

```sql
SELECT customer_id
FROM customers
WHERE customer_id = NULL;
```

This query returns zero rows even if the column contains `NULL`. To check for null values, you must write:

```sql
SELECT customer_id
FROM customers
WHERE customer_id IS NULL;
```

This forms the foundation for understanding why a single `NULL` in a subquery can alter `NOT IN` results.

## 4. The NULL Trap in NOT IN

Suppose `orders.customer_id` contains some rows with `NULL`. When running:

```sql
SELECT customer_id, full_name
FROM customers
WHERE customer_id NOT IN (
    SELECT customer_id
    FROM orders
);
```

For a customer whose ID does not match any row in orders, MySQL must evaluate whether that ID differs from every value in the set. When the set contains `NULL`, comparing against `NULL` yields `UNKNOWN`; consequently, the entire `NOT IN` condition evaluates to `UNKNOWN` instead of `TRUE`.

As a result, customers who have never placed an order are also dropped from the output. This is a common logic bug: the SQL is valid and raises no errors, yet returns an empty or incomplete result set.

### Runnable Example

Create test data:

```sql
CREATE TEMPORARY TABLE demo_customers (
    customer_id INT PRIMARY KEY,
    full_name VARCHAR(50) NOT NULL
);

CREATE TEMPORARY TABLE demo_orders (
    order_id INT PRIMARY KEY,
    customer_id INT NULL
);

INSERT INTO demo_customers VALUES
    (1, 'An'),
    (2, 'Binh'),
    (3, 'Chi');

INSERT INTO demo_orders VALUES
    (101, 1),
    (102, NULL);
```

Test `NOT IN`:

```sql
SELECT customer_id, full_name
FROM demo_customers
WHERE customer_id NOT IN (
    SELECT customer_id
    FROM demo_orders
);
```

The query fails to return `Binh` and `Chi`, even though neither customer has a matching order. Because the subquery set contains `NULL`, the predicate for unmatched IDs evaluates to `UNKNOWN`.

If you exclude `NULL` from the inner set:

```sql
SELECT customer_id, full_name
FROM demo_customers
WHERE customer_id NOT IN (
    SELECT customer_id
    FROM demo_orders
    WHERE customer_id IS NOT NULL
);
```

Now the result includes `Binh` and `Chi`. This is a valid fix once you have confirmed that `NULL` in `orders.customer_id` does not represent a customer to match against.

## 5. Simple Truth Table for IN and NOT IN

Suppose the left-hand expression is `2` and consider these right-hand sets:

| Right-Hand Set | `2 IN (set)` | `2 NOT IN (set)` | Explanation |
|---|---|---|---|
| `(1, 3)` | `FALSE` | `TRUE` | No matching value and no NULL |
| `(1, 2, 3)` | `TRUE` | `FALSE` | Matching value exists |
| `(1, NULL, 3)` | `UNKNOWN` | `UNKNOWN` | No match, but an unknown element exists |
| `(2, NULL)` | `TRUE` | `FALSE` | Matching value exists; IN is already determined TRUE |
| Empty set | `FALSE` | `TRUE` | No elements exist to match or violate |

If the left-hand expression is `NULL` and the right-hand set is non-empty, the membership test is generally `UNKNOWN`; if the right-hand set is empty, `IN` is `FALSE` and `NOT IN` is `TRUE` by empty-set quantifier rules.

Two key takeaways:

- A single `NULL` in the right-hand set is enough to turn `NOT IN` for an unmatched value into `UNKNOWN`.
- If a matching value exists, `IN` is `TRUE` and `NOT IN` is `FALSE`, even when the set also contains `NULL`.

## 6. NOT EXISTS Is Usually a Safer Choice for Anti-Joins

When the business requirement is "retrieve parent rows for which no related child row exists," `NOT EXISTS` usually expresses this directly and avoids the `NULL` trap in child results.

```sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
```

MySQL evaluates each customer and keeps them if the subquery finds no orders satisfying the join predicate. A row with `orders.customer_id IS NULL` never makes `o.customer_id = c.customer_id` evaluate to `TRUE`, so it never blocks unrelated customers from appearing.

`EXISTS` only cares whether the subquery returns at least one row. Thus, `SELECT 1` suffices; there is no need to select actual columns from the child table.

### Note When the Outer Column Can Be NULL

When `c.customer_id` is a `NOT NULL` primary key, the example above never encounters an outer `NULL` key. If the outer expression can be `NULL`, `NOT EXISTS` using `=` treats no row as equal to `NULL`, so that outer row may be retained.

If business rules require excluding outer rows with `NULL` keys, state it explicitly:

```sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE c.customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM orders AS o
      WHERE o.customer_id = c.customer_id
  );
```

If business rules treat `NULL` on both sides as the same value, MySQL provides the null-safe equality operator `<=>`:

```sql
WHERE NOT EXISTS (
    SELECT 1
    FROM child_rows AS ch
    WHERE ch.reference_code <=> parent_rows.reference_code
)
```

Use `<=>` only when business rules genuinely equate two `NULL` values. For standard foreign keys, `NULL` usually indicates no link exists rather than a key that matches `NULL` in the parent table.

## 7. Anti-Join with LEFT JOIN ... IS NULL

Another way to find parent rows without child rows is a `LEFT JOIN` followed by filtering for rows where no child record matched:

```sql
SELECT c.customer_id, c.full_name
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL;
```

`order_id` is a primary key and cannot be `NULL`, so `o.order_id IS NULL` indicates no matching `orders` row exists. Choose a child-table column guaranteed `NOT NULL` as the unmatched sentinel; avoid testing a nullable child column, which could confuse matched rows containing `NULL` with unmatched rows.

`NOT EXISTS` and `LEFT JOIN ... IS NULL` typically express the same anti-join when the join condition and checked column are chosen accurately. The optimizer can transform them into similar execution plans. Pick whichever reads more clearly, then verify performance with `EXPLAIN` on real data.

## 8. When Is NOT IN Safe to Use?

`NOT IN` is not always wrong. It is appropriate when both conditions are guaranteed:

1. The subquery set cannot contain `NULL`.
2. The left-hand expression cannot be `NULL`, or business rules explicitly define how outer `NULL`s are handled.

For example, if `orders.customer_id` is declared `NOT NULL` and `customers.customer_id` is a `NOT NULL` primary key, this query has clear semantics:

```sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders AS o
);
```

If the child column is nullable yet you still want to use `NOT IN`, filter `NULL`s inside the subquery:

```sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE c.customer_id IS NOT NULL
  AND c.customer_id NOT IN (
      SELECT o.customer_id
      FROM orders AS o
      WHERE o.customer_id IS NOT NULL
  );
```

`c.customer_id IS NOT NULL` is only needed if the outer column can be `NULL` and business rules exclude those rows. On a `NOT NULL` primary key, that check is redundant, though it can clarify intent for readers.

Do not rely solely on current data. If the schema allows `NULL`, a future row can silently alter `NOT IN` query results. A `NOT NULL` constraint is a durable guarantee compared to assumptions about existing data.

## 9. IN, EXISTS, and Performance

`IN` fits well when checking whether a value belongs to a result set:

```sql
SELECT c.customer_id
FROM customers AS c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM orders AS o
    WHERE o.status = 'PAID'
);
```

`EXISTS` fits well when asking whether at least one related row exists:

```sql
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
```

Both queries above can be transformed by the optimizer into a semijoin or an equivalent strategy. Never claim `EXISTS` is always faster than `IN` or vice versa. Performance depends on indexes, row counts, selectivity, MySQL version, and the execution plan.

For anti-joins, compare `NOT EXISTS` and `NOT IN` only after confirming nullability and business semantics. `NOT EXISTS` generally preserves intent more reliably when the subquery column is nullable.

Useful indexes for these examples:

```sql
CREATE INDEX idx_orders_customer_status
    ON orders (customer_id, status);
```

Index column order should align with actual query predicates. For queries filtering `status` first and joining by `customer`, `(status, customer_id)` might fit better. Inspect `EXPLAIN` rather than creating indexes by fixed formula.

## 10. Checking Data Types and Collations in Subqueries

Both sides of a comparison should have compatible data types. If one side is numeric and the other is a string, MySQL can perform implicit conversion. With string identifiers, this can strip leading zeros or produce unexpected comparison outcomes.

Pattern to avoid:

```sql
SELECT c.customer_code
FROM customers AS c
WHERE c.customer_code IN (
    SELECT o.customer_id
    FROM orders AS o
);
```

If `customer_code` is `VARCHAR` while `customer_id` is an integer, revisit the data model. Textual codes should compare against textual values under matching normalization rules; numeric IDs should use numeric types on both sides.

For strings, character sets and collations affect comparisons. For instance, a case-insensitive collation treats `ABC` and `abc` as equal. Pick collations matching the business rules for codes or names.

Avoid wrapping indexed columns in `CAST()` or conversion functions inside join predicates whenever possible. Prefer standardizing schema types or converting input parameters to match the column type so the optimizer can use indexes effectively.

## 11. Reading Execution Plans

For `IN`, `EXISTS`, or `NOT EXISTS` queries, use `EXPLAIN` to inspect which tables MySQL accesses, which indexes it chooses, and its row estimates:

```sql
EXPLAIN
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
```

Verify:

- Whether `orders` uses an index on `customer_id`.
- Whether estimated rows to read look reasonable.
- Whether the subquery transforms into an antijoin or another strategy.
- Whether any unnecessary full table scan occurs.

In MySQL 8.0.18 and later, `EXPLAIN ANALYZE` executes the query and reports actual row counts and timings. Run it only in suitable environments, since it actually executes the statement rather than merely describing the plan.

## 12. Checklist to Avoid the NULL Trap

Before using `NOT IN` with a subquery, verify:

1. Does the column returned by the subquery allow `NULL`?
2. Can the subquery produce `NULL` via `LEFT JOIN`, expressions, or `UNION`?
3. Can the outer expression be `NULL`?
4. If `NULL` appears, should business logic treat it as "no link," "unknown," or a matchable value?
5. Can `NOT EXISTS` express the intent more clearly?
6. If using `LEFT JOIN ... IS NULL`, is the checked child column guaranteed `NOT NULL`?
7. Do both sides share compatible data types, signedness, character sets, and collations?
8. Do indexes and execution plans handle the expected data volume?

## 13. Hands-On Exercises

Use the `demo_customers` and `demo_orders` tables from the example section:

1. Run `IN` to find customers with orders; insert a child row with `customer_id = NULL` and observe the result.
2. Run `NOT IN` to find customers without orders; observe how a single `NULL` in the subquery changes the result.
3. Replace `NOT IN` with `NOT EXISTS`; explain why a child row with `NULL` does not suppress customers who have no orders.
4. Rewrite it using `LEFT JOIN ... IS NULL`, checking primary key `order_id` for unmatched rows.
5. Try adding `WHERE customer_id IS NOT NULL` to the `NOT IN` subquery and compare results.
6. Test an outer expression with a `NULL` value; explain the difference between `NOT IN` and `NOT EXISTS` when the outer key is nullable.
7. Compare `EXPLAIN` output for `IN`, `EXISTS`, and `NOT EXISTS` after adding an appropriate index.
8. Test an empty inner set and record the outputs of `IN` and `NOT IN`.

You have completed this lesson when you can explain why `NOT IN` can return an empty set simply because the subquery contains `NULL`, know when to filter `NULL`s versus using `NOT EXISTS` or an anti-join, and verify correct results with test data. Always decide `NULL` handling from business semantics rather than patching SQL just to make errors go away.
