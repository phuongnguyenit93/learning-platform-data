# WHERE, Comparison Operators, and Combining AND, OR, NOT

The `WHERE` clause filters rows based on conditions before a query returns results. Conditions can compare numbers, strings, dates/times, check for `NULL`, test set membership, or combine multiple expressions with `AND`, `OR`, and `NOT`. Writing conditions correctly ensures queries return accurate business data and helps avoid common pitfalls with `NULL`, operator precedence, and implicit type conversion.

In the `DATABASE_MYSQL` module, `WHERE` is the foundation for SQL queries, joins, conditional updates/deletes, and index optimization. A condition that is logically right but mismatched in data type or unable to leverage an index can still cause errors or slow queries. This lesson uses MySQL 8.x and examples on an orders table.

## Objectives

After this lesson, you will be able to:

- Use `WHERE` to filter rows with comparison operators and conditional expressions.
- Combine multiple conditions using `AND`, `OR`, `NOT`, and parentheses.
- Predict the precedence of logical operators.
- Handle `NULL` properly according to SQL's three-valued logic.
- Use `IN`, `BETWEEN`, `LIKE`, `IS NULL`, and null-safe comparison.
- Avoid bugs caused by implicit type conversion, collations, and date/time conditions.
- Write conditions capable of leveraging indexes and inspect them with `EXPLAIN`.

## 1. What Is WHERE Used For?

`WHERE` determines which rows satisfy a condition. For each row, the expression in `WHERE` can evaluate to `TRUE`, `FALSE`, or `UNKNOWN`. Only rows evaluating to `TRUE` are kept; both `FALSE` and `UNKNOWN` are excluded.

Basic syntax:

```sql
SELECT column_list
FROM table_name
WHERE condition;
```

Example, fetching paid orders:

```sql
SELECT order_id, customer_id, total_amount, status
FROM orders
WHERE status = 'PAID';
```

Conditions can also apply to other statements:

```sql
UPDATE orders
SET status = 'PROCESSING'
WHERE order_id = 1001;

DELETE FROM orders
WHERE status = 'CANCELLED';
```

With `UPDATE` and `DELETE`, a missing or incorrect `WHERE` clause can modify or delete far more rows than intended. Before writing to critical data, run a `SELECT` with the exact same condition to confirm the affected row set.

## 2. Sample Data for Practice

The following examples use an orders table:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    shipping_fee DECIMAL(10, 2) NULL,
    created_at DATETIME(6) NOT NULL,
    paid_at DATETIME(6) NULL,
    note VARCHAR(255) NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_status (status),
    KEY idx_orders_customer (customer_id),
    KEY idx_orders_created (created_at)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;

INSERT INTO orders
    (customer_id, status, total_amount, shipping_fee, created_at, paid_at, note)
VALUES
    (101, 'PAID',       125000.00, 15000.00, '2026-01-05 09:10:00', '2026-01-05 09:12:00', 'Morning delivery'),
    (102, 'PENDING',     89000.00,     NULL, '2026-01-06 10:00:00', NULL,                  NULL),
    (101, 'CANCELLED',  210000.00, 20000.00, '2026-01-07 11:30:00', NULL,                  'Customer changed mind'),
    (103, 'PAID',       350000.00, 25000.00, '2026-01-08 14:00:00', '2026-01-08 14:03:00', 'Priority'),
    (104, 'PROCESSING',  99000.00,     NULL, '2026-01-09 08:15:00', NULL,                  'Awaiting confirmation'),
    (102, 'REFUNDED',   125000.00, 15000.00, '2026-01-10 16:45:00', '2026-01-06 10:05:00', NULL);
```

`status` is declared `NOT NULL`; `shipping_fee`, `paid_at`, and `note` can be `NULL`. These columns help observe the difference between ordinary comparisons and `NULL` checks.

## 3. Basic Comparison Operators

| Operator | Meaning | Example |
|---|---|---|
| `=` | Equal to | `status = 'PAID'` |
| `<>` or `!=` | Not equal to | `status <> 'CANCELLED'` |
| `>` | Greater than | `total_amount > 100000` |
| `>=` | Greater than or equal to | `total_amount >= 100000` |
| `<` | Less than | `total_amount < 100000` |
| `<=` | Less than or equal to | `total_amount <= 100000` |

Example filtering orders with an amount greater than or equal to 100,000:

```sql
SELECT order_id, total_amount
FROM orders
WHERE total_amount >= 100000;
```

Finding orders not in cancelled status:

```sql
SELECT order_id, status
FROM orders
WHERE status <> 'CANCELLED';
```

Because `status` in the sample table is `NOT NULL`, the query above classifies every row. If the column allows `NULL`, rows with `status IS NULL` are not returned because `NULL <> 'CANCELLED'` evaluates to `UNKNOWN`. You must explicitly decide whether to keep rows without a status.

### 3.1. String Comparison and Collation

String comparison is governed by the character set and collation of the column or expression. The collation determines comparison rules such as case sensitivity, accent sensitivity, and character ordering.

Example with a case-insensitive collation:

```sql
SELECT order_id, status
FROM orders
WHERE status = 'paid';
```

The result may match `PAID` if the collation of `status` is case-insensitive, such as one ending in `_ci`. If you need a case-sensitive comparison, use an appropriate collation or an explicit binary expression. Never assume all string columns follow the same rules; inspect the actual column collation.

```sql
SHOW FULL COLUMNS FROM orders;
```

### 3.2. Numeric Comparison and Avoiding Unwanted Type Casting

Comparing a numeric column against a numeric literal of the same type is straightforward and can leverage an index:

```sql
SELECT order_id
FROM orders
WHERE customer_id = 101;
```

Avoid comparing a numeric column to a non-numeric string or relying on implicit conversion:

```sql
-- Avoid relying on implicit type conversion:
SELECT order_id
FROM orders
WHERE customer_id = 'customer-101';
```

MySQL may convert an operand to perform the comparison; the result may differ from expectations, raise warnings, or prevent the optimizer from using indexes effectively. Bind the proper data type from your application and use properly typed literals in SQL.

## 4. Combining Conditions with AND

`AND` evaluates to `TRUE` only when all component conditions are `TRUE`.

Example fetching paid orders with a total amount of at least 100,000:

```sql
SELECT order_id, status, total_amount
FROM orders
WHERE status = 'PAID'
  AND total_amount >= 100000;
```

You can add multiple conditions:

```sql
SELECT order_id, customer_id, total_amount
FROM orders
WHERE status = 'PAID'
  AND customer_id = 101
  AND total_amount BETWEEN 100000 AND 200000;
```

Every condition must be true for a row to be retained. If any condition is `FALSE` or `UNKNOWN`, the `AND` result cannot be `TRUE`.

## 5. Combining Conditions with OR

`OR` evaluates to `TRUE` if at least one component condition is `TRUE`.

Example fetching pending or processing orders:

```sql
SELECT order_id, status
FROM orders
WHERE status = 'PENDING'
   OR status = 'PROCESSING';
```

You can use `OR` to combine two sets of criteria:

```sql
SELECT order_id, status, total_amount
FROM orders
WHERE status = 'PAID'
   OR total_amount >= 300000;
```

The query above fetches paid orders or orders with a total of 300,000 or more, even if unpaid. Read the condition accurately as "at least one branch is true."

### 5.1. OR Can Expand the Row Set

A common mistake is using `OR` when you actually want both conditions to be true:

```sql
-- This query fetches PAID orders or high-value orders.
WHERE status = 'PAID' OR total_amount > 300000
```

If the requirement is orders that are both `PAID` and high-value, you must use `AND`:

```sql
WHERE status = 'PAID' AND total_amount > 300000
```

Before running a query on real data, state the condition in plain words: "all conditions are true" corresponds to `AND`; "at least one condition is true" corresponds to `OR`.

## 6. Negation with NOT

`NOT` inverts logical results: `TRUE` becomes `FALSE`, `FALSE` becomes `TRUE`, while `UNKNOWN` remains `UNKNOWN`.

Example fetching orders that are not `CANCELLED`:

```sql
SELECT order_id, status
FROM orders
WHERE NOT (status = 'CANCELLED');
```

With a `NOT NULL` `status` column, this is equivalent to `status <> 'CANCELLED'`. If the column allows `NULL`, both forms exclude `NULL` rows because the result is unknown.

Negating a group of conditions:

```sql
SELECT order_id, status, total_amount
FROM orders
WHERE NOT (
    status = 'CANCELLED'
    OR total_amount < 100000
);
```

By De Morgan's laws, the expression above is equivalent to:

```sql
WHERE status <> 'CANCELLED'
  AND total_amount >= 100000
```

This equivalence must be understood alongside `NULL` logic: if the columns are nullable, both expressions can still evaluate to `UNKNOWN` and exclude those rows. If you want to keep `NULL` rows, add a separate condition.

## 7. Precedence of AND, OR, NOT

In MySQL, `NOT` has higher precedence than `AND`, and `AND` has higher precedence than `OR`. Thus, the condition:

```sql
WHERE status = 'PAID'
   OR status = 'PENDING'
  AND total_amount >= 100000
```

is interpreted as:

```sql
WHERE status = 'PAID'
   OR (status = 'PENDING' AND total_amount >= 100000)
```

It is not equivalent to:

```sql
WHERE (status = 'PAID' OR status = 'PENDING')
  AND total_amount >= 100000
```

The two queries can return different row sets. In the first example, every `PAID` order is selected regardless of total amount; only the `PENDING` branch requires a total amount of at least 100,000. In the second example, both `PAID` and `PENDING` must meet the amount threshold.

**Good practice:** use parentheses to reflect logical grouping according to business intent, even when you already know operator precedence. Parentheses make queries easier to read, review, and maintain.

```sql
SELECT order_id, status, total_amount
FROM orders
WHERE (status = 'PAID' OR status = 'PENDING')
  AND total_amount >= 100000;
```

## 8. Three-Valued Logic and NULL

SQL does not only have `TRUE` and `FALSE`. When a comparison expression has a `NULL` operand, the result is typically `UNKNOWN`.

| Expression | Result |
|---|---|
| `NULL = NULL` | `UNKNOWN` |
| `NULL <> 10` | `UNKNOWN` |
| `10 = 10` | `TRUE` |
| `10 <> 20` | `TRUE` |
| `NOT UNKNOWN` | `UNKNOWN` |

In `WHERE`, only rows where the condition is `TRUE` are kept. Therefore:

```sql
SELECT order_id
FROM orders
WHERE paid_at = NULL;
```

cannot find rows where `paid_at` is `NULL`. You must use:

```sql
SELECT order_id
FROM orders
WHERE paid_at IS NULL;
```

Finding orders that already have a payment timestamp:

```sql
SELECT order_id, paid_at
FROM orders
WHERE paid_at IS NOT NULL;
```

### 8.1. Truth Table for AND, OR, NOT

In the table below, `U` stands for `UNKNOWN`:

| A | B | A AND B | A OR B |
|---|---|---|---|
| TRUE | TRUE | TRUE | TRUE |
| TRUE | FALSE | FALSE | TRUE |
| TRUE | U | U | TRUE |
| FALSE | TRUE | FALSE | TRUE |
| FALSE | FALSE | FALSE | FALSE |
| FALSE | U | FALSE | U |
| U | TRUE | U | TRUE |
| U | FALSE | FALSE | U |
| U | U | U | U |

`NOT TRUE = FALSE`, `NOT FALSE = TRUE`, `NOT U = U`.

For example, with nullable `shipping_fee`:

```sql
SELECT order_id
FROM orders
WHERE shipping_fee > 10000;
```

Rows with `shipping_fee IS NULL` are excluded because the comparison yields `UNKNOWN`. If business rules treat an unspecified shipping fee as 0:

```sql
SELECT order_id
FROM orders
WHERE shipping_fee IS NULL
   OR shipping_fee = 0;
```

Do not automatically treat `NULL` as 0. `NULL` usually means unknown, not provided, or not applicable; only combine it with 0 when business logic explicitly defines it that way.

### 8.2. Null-Safe Comparison with `<=>`

MySQL provides the `<=>` operator for null-safe comparison:

```sql
SELECT
    NULL <=> NULL AS both_null,
    NULL <=> 10 AS null_vs_number,
    10 <=> 10 AS same_number;
```

The results are `1`, `0`, and `1` respectively. Unlike `=`, `<=>` returns TRUE when both operands are `NULL` and FALSE when only one side is `NULL`.

Example finding rows whose `note` equals a parameter value, even when the parameter is `NULL`:

```sql
SELECT order_id, note
FROM orders
WHERE note <=> NULL;
```

In application queries, `<=>` is useful when a null-safe comparison is needed. If you simply want to find missing values, `IS NULL` is easier to read and expresses intent more clearly.

## 9. IN and NOT IN

`IN` tests whether an expression matches any value in a list:

```sql
SELECT order_id, status
FROM orders
WHERE status IN ('PAID', 'PROCESSING', 'PENDING');
```

This condition is equivalent to combining multiple equality comparisons with `OR`:

```sql
WHERE status = 'PAID'
   OR status = 'PROCESSING'
   OR status = 'PENDING'
```

`NOT IN` negates set membership:

```sql
SELECT order_id, status
FROM orders
WHERE status NOT IN ('CANCELLED', 'REFUNDED');
```

### 9.1. Beware When a NOT IN List Contains NULL

If a `NOT IN` list contains `NULL`, the result can become `UNKNOWN` for values that do not match any element. For example:

```sql
SELECT 1
WHERE 1 NOT IN (2, NULL);
```

No rows are returned because comparing against `NULL` makes the result unknown. This is a common bug when the list comes from a subquery whose returned column may contain `NULL`:

```sql
-- May eliminate all rows other than matching values if the subquery returns NULL.
SELECT o.order_id
FROM orders AS o
WHERE o.customer_id NOT IN (
    SELECT b.customer_id
    FROM blocked_customer AS b
);
```

If you use `NOT IN`, ensure the subset contains no `NULL`:

```sql
SELECT o.order_id
FROM orders AS o
WHERE o.customer_id NOT IN (
    SELECT b.customer_id
    FROM blocked_customer AS b
    WHERE b.customer_id IS NOT NULL
);
```

Or use `NOT EXISTS`, which clearly expresses "no matching row" and avoids the `NULL` trap in the subset:

```sql
SELECT o.order_id
FROM orders AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_customer AS b
    WHERE b.customer_id = o.customer_id
);
```

If `o.customer_id` can also be `NULL`, explicitly decide whether you want to keep those rows. In the sample table, `customer_id` is `NOT NULL`.

## 10. BETWEEN and Range Conditions

`BETWEEN low AND high` tests whether a value falls within a range inclusive of both endpoints. It is equivalent to:

```sql
value >= low AND value <= high
```

Example:

```sql
SELECT order_id, total_amount
FROM orders
WHERE total_amount BETWEEN 100000 AND 200000;
```

Rows with values equal to exactly 100,000 or 200,000 are selected. If you want a half-open interval, write `>=` and `<` explicitly.

### 10.1. Filtering Dates/Times with Half-Open Intervals

For `DATETIME` or `TIMESTAMP` columns, use an inclusive start and exclusive end interval to filter a day or month:

```sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00';
```

This captures every timestamp in January, including the final microseconds of January 31. Avoid writing `BETWEEN '2026-01-01' AND '2026-01-31'` for columns with a time component because the upper bound is usually interpreted as the start of January 31, missing the rest of that day.

## 11. LIKE and Wildcards

`LIKE` matches strings against a pattern:

- `%` matches zero or more characters.
- `_` matches exactly one character.

Example finding notes starting with "Morning":

```sql
SELECT order_id, note
FROM orders
WHERE note LIKE 'Morning%';
```

Finding notes containing the word "delivery":

```sql
SELECT order_id, note
FROM orders
WHERE note LIKE '%delivery%';
```

### 11.1. Escaping Wildcard Characters

If you need to search for literal `%` or `_` characters, use an escape character:

```sql
SELECT order_id, note
FROM orders
WHERE note LIKE '%!_%' ESCAPE '!';
```

The example above finds notes containing an underscore. The `!` character is declared as the escape character, so the `_` immediately following it is treated as a literal underscore rather than a wildcard. Choosing an explicit escape character avoids depending on how SQL literals interpret backslashes in configurations with `NO_BACKSLASH_ESCAPES`.

### 11.2. LIKE and Indexes

Prefix conditions such as `name LIKE 'An%'` can use a range scan on an appropriate index. Conditions with a leading wildcard such as `name LIKE '%An%'` generally cannot use a B-tree index for a direct range lookup because the starting point of the string is unknown. For substring/word search in long text, consider `FULLTEXT` or an appropriate search engine rather than adding an ordinary B-tree index.

## 12. Date/Time Conditions and Data Types

MySQL supports comparing date/time values against properly formatted literals:

```sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= '2026-01-08 00:00:00'
  AND created_at <  '2026-01-10 00:00:00';
```

The literals here represent date/time values; for `TIMESTAMP` columns, results are also affected by the session timezone when MySQL interprets and returns values. For `DATETIME`, values are compared as calendar date/times without automatic timezone conversion.

Do not wrap an indexed column in a function if you can filter with a direct range instead:

```sql
-- Typically cannot leverage a range index on created_at:
SELECT order_id
FROM orders
WHERE DATE(created_at) = '2026-01-08';

-- Prefer a range condition:
SELECT order_id
FROM orders
WHERE created_at >= '2026-01-08 00:00:00'
  AND created_at <  '2026-01-09 00:00:00';
```

A range condition keeps the indexed column unmodified on one side of the comparison and is usually much easier for the optimizer to utilize.

## 13. WHERE Conditions and Indexes

`WHERE` determines the row set to read; indexes can help MySQL locate matching rows without scanning the entire table. However, index usage depends on cardinality, statistics, number of rows returned, column order in composite indexes, data types, and expression shape.

### 13.1. Equality Condition on an Indexed Column

With index `idx_orders_customer(customer_id)`:

```sql
EXPLAIN
SELECT order_id, status, total_amount
FROM orders
WHERE customer_id = 101;
```

The optimizer can choose an index lookup/range on `customer_id`. Inspect the `key`, `type`, `rows`, and `filtered` columns in `EXPLAIN`; do not judge solely by a single `type` value.

### 13.2. Combining AND with a Composite Index

If queries frequently filter by customer and status, a composite index may be appropriate:

```sql
CREATE INDEX idx_orders_customer_status
ON orders (customer_id, status);
```

The query:

```sql
SELECT order_id, total_amount
FROM orders
WHERE customer_id = 101
  AND status = 'PAID';
```

can use both parts of the index. Column order matters: an index on `(customer_id, status)` typically supports queries filtering on `customer_id` alone or on both `customer_id` and `status`; it is not equivalent to an index on `status` alone when the query does not filter on `customer_id`.

### 13.3. OR and Indexes

`OR` can cause the optimizer to choose multiple range scans or a different access path. For example:

```sql
EXPLAIN
SELECT order_id
FROM orders
WHERE customer_id = 101
   OR status = 'PENDING';
```

If each branch has its own index, MySQL may consider Index Merge. However, Index Merge is not always faster than a table scan or another index. Check `EXPLAIN` and actual row counts rather than blindly splitting `OR` into `UNION` without verifying results and performance.

### 13.4. Avoid Transforming Columns in WHERE

An expression such as:

```sql
WHERE YEAR(created_at) = 2026
```

generally cannot use range access on a standard index on `created_at`. Replace it with a range:

```sql
WHERE created_at >= '2026-01-01'
  AND created_at <  '2027-01-01'
```

Similarly, avoid `CAST(indexed_column AS ...)`, `LOWER(indexed_column)`, or arithmetic on the column when aiming for a range lookup. If you must query by an expression, consider a functional index or an indexed generated column after verifying version support and workload fit.

## 14. Using WHERE Safely in Applications

Do not concatenate user input directly into SQL strings. Use prepared statements to pass values as parameters:

```java
String sql = """
    SELECT order_id, status, total_amount
    FROM orders
    WHERE customer_id = ?
      AND status = ?
      AND total_amount >= ?
    """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, customerId);
    statement.setString(2, status);
    statement.setBigDecimal(3, minimumAmount);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            // Read results by the required columns.
        }
    }
}
```

Prepared statements separate data from SQL structure, reducing SQL injection risk and avoiding literal escaping bugs. Placeholders represent values only; you cannot use `?` to bind table names, column names, operators, or `ASC`/`DESC` keywords. Any dynamic structural parts must be chosen from an allowlist.

For optional filters, construct the SQL structure in a controlled way and bind each value. Avoid mechanically using the `WHERE (? IS NULL OR column = ?)` pattern on large tables because the `OR` expression can impair index usage; consider building distinct SQL queries for each filter combination.

## 15. Common WHERE Mistakes

| Mistake | Why It Is Wrong | Fix |
|---|---|---|
| `column = NULL` | Comparing with NULL yields `UNKNOWN` | Use `IS NULL` or `<=>` when null-safe equality is needed |
| Mixing AND/OR without parentheses | `AND` has higher precedence than `OR` | Use parentheses to make condition grouping explicit |
| `NOT IN` given a list containing NULL | Result can evaluate to `UNKNOWN` | Filter out NULL in the subquery or use `NOT EXISTS` |
| `BETWEEN` with end date at 00:00 | Misses the remainder of the final day | Use `>= start AND < next_start` interval |
| Arbitrarily comparing numbers with strings | Triggers implicit type conversion | Bind proper types, check warnings and schema |
| Expecting `LIKE '%text%'` to use B-tree | Leading wildcard prevents range prefix | Consider FULLTEXT or an appropriate search solution |
| Wrapping an indexed column in a function | Can make the predicate non-sargable | Pre-compute bounds and compare directly against the column |
| Running UPDATE/DELETE without verifying WHERE | Can affect unintended rows | Run SELECT with the same condition, check row count, and use transactions when appropriate |

## 16. Workflow for Writing and Checking Conditions

When writing a query with multiple conditions, follow this sequence:

1. State the requirement in plain words, identifying mandatory and alternative conditions.
2. Identify which columns are nullable, along with data types and string collations.
3. Group logic with parentheses; use `AND` for simultaneous conditions and `OR` for alternatives.
4. Check edge cases: boundary values, `NULL`, empty strings, empty/special `IN` lists, and day-boundary timestamps.
5. Run the query on sample data to verify results.
6. Use `EXPLAIN` to inspect the access path, chosen index, and estimated row count.
7. For `UPDATE`/`DELETE`, run a `SELECT` with the same `WHERE` beforehand and confirm the change scope.

Example requirement: fetch orders from customer 101 or 102 that are in paid status and have a total amount of 100,000 or more:

```sql
SELECT order_id, customer_id, status, total_amount
FROM orders
WHERE customer_id IN (101, 102)
  AND status = 'PAID'
  AND total_amount >= 100000;
```

If the requirement is orders from customer 101, or any high-value order from customer 102, group the conditions differently:

```sql
SELECT order_id, customer_id, status, total_amount
FROM orders
WHERE customer_id = 101
   OR (customer_id = 102 AND total_amount >= 300000);
```

The two queries have different business meanings even though both mention the same two customer IDs. Parentheses express the exact condition branches.

## 17. Practice Exercises

Perform these exercises using the `orders` table from Section 2:

1. Fetch orders with `status = 'PAID'` and `total_amount >= 100000`.
2. Fetch orders with status `PENDING` or `PROCESSING` using `OR`, then rewrite it using `IN`.
3. Fetch orders that are not `CANCELLED` and explain the result if the `status` column allows `NULL`.
4. Fetch orders where `paid_at IS NULL`; retry with `paid_at = NULL` and explain why it does not return the expected result.
5. Use `<=>` to compare a nullable parameter against `note`.
6. Write a `NOT IN` query with a subquery that can return `NULL`, observe the result, and fix it with `NOT EXISTS`.
7. Filter orders across all of January 2026 using a half-open interval; compare with a `BETWEEN` condition whose upper bound is the 31st.
8. Find notes starting with `Morning`, containing `delivery`, and containing the literal `_` character.
9. Write two queries with `AND`/`OR` but different parenthesization; create test data to prove their result sets differ.
10. Run `EXPLAIN` for queries filtering by `customer_id`, by `status`, and by both; try adding an appropriate composite index and compare access paths.
11. Write an `UPDATE` in a lab transaction: run a `SELECT` with the same `WHERE` first, check the row count, update, verify, and commit/rollback.
12. Write a JDBC query using `PreparedStatement` with three filter parameters and verify the bind types.

You have completed this lesson when you can predict the outcome of multi-branch conditions, handle `NULL` properly, choose accurate date/time ranges, and explain which indexes can support which predicates.

## 18. Key Principles to Remember

- `WHERE` retains rows only when the expression evaluates to `TRUE`; `FALSE` and `UNKNOWN` are excluded.
- Use `IS NULL`/`IS NOT NULL` to check for NULL; use `<=>` when null-safe equality is needed.
- `NOT` has higher precedence than `AND`, and `AND` has higher precedence than `OR`; use parentheses to group logic clearly.
- `IN` is equivalent to multiple equality checks joined by `OR`; be careful with `NOT IN` when the subset contains `NULL`.
- `BETWEEN` includes both endpoints; for date/time columns, usually prefer `>= start AND < next_start`.
- String comparisons depend on collation; numeric/date-time comparisons should use matching data types.
- Prefix conditions `LIKE 'text%'` can leverage a B-tree index; leading wildcards generally cannot use a range prefix.
- Keep indexed columns bare in conditions; avoid wrapping them in functions when aiming for range access.
- Use prepared statements for user-supplied values.
- Before `UPDATE` or `DELETE`, verify the target row set with a `SELECT` using the same condition.
