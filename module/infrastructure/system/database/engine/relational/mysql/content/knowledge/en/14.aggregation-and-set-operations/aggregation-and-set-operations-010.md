# INTERSECT, EXCEPT, and Version Support Conditions

`INTERSECT` and `EXCEPT` are two set operations used to compare the results of two `SELECT` queries. `INTERSECT` returns rows that appear in both results; `EXCEPT` returns rows that appear in the left result but not in the right result. They complement `UNION`, which combines rows from multiple queries.

In MySQL, the version milestone is crucial: **`INTERSECT` and `EXCEPT` are supported starting in MySQL 8.0.31**. MySQL 8.0.30 and earlier do not support these operators; statements using them will fail with a syntax error. Starting in 8.0.31, you can choose `DISTINCT` or `ALL` to control whether duplicate row occurrences are removed or preserved. Check the version of every environment before deploying these queries to an application.

## 1. Set Operations in SQL

Set operations operate on the results of multiple structurally compatible queries:

| Operator | Meaning | Rows returned |
| --- | --- | --- |
| `UNION` | Union of two result sets | Rows appearing on the left or right; removes duplicates by default |
| `UNION ALL` | Union preserving multiplicity | All rows from both sides, including duplicates |
| `INTERSECT` | Intersection of two result sets | Rows appearing on both sides |
| `EXCEPT` | Difference of two result sets | Rows appearing on the left but not on the right |

Examples of business goals:

- `UNION`: list of customers who have orders or support tickets.
- `INTERSECT`: customers who have both a paid order and a high-priority support ticket.
- `EXCEPT`: customers who have a paid order but do not have a high-priority support ticket.

These operators compare all selected columns by corresponding position. They do not infer join keys between two tables like `JOIN`.

## 2. MySQL Version Support Conditions

`INTERSECT` and `EXCEPT` were introduced in MySQL 8.0.31. They can be used on MySQL 8.0.31 and later, including the MySQL 8.4 series. On MySQL 8.0.30 and earlier, this syntax is not supported.

Check the version:

```sql
SELECT VERSION() AS mysql_version;
```

If an application runs across multiple environments, check the version of every server that may execute the query—including primary, promotable replicas, staging environments, and ETL jobs. Do not assume production supports a feature based solely on your local development machine.

The following syntax runs only on MySQL 8.0.31 or later:

```sql
SELECT customer_id
FROM paid_orders
INTERSECT
SELECT customer_id
FROM priority_tickets;
```

On older versions, MySQL raises a syntax error at the `INTERSECT` operator. Similarly, `EXCEPT` is not recognized as a set operation.

## 3. INTERSECT: Retrieving the Intersection of Two Results

`INTERSECT` returns rows present in both the left and right queries.

Example: find customers who have both a paid order and a high-priority support ticket:

```sql
SELECT customer_id
FROM orders
WHERE status = 'paid'

INTERSECT

SELECT customer_id
FROM support_tickets
WHERE priority = 'high'
ORDER BY customer_id;
```

The result contains only `customer_id` values satisfying both conditions. In its default form, duplicates are removed.

`INTERSECT` does not require both queries to read from the same table. Both sides can query tables, views, or other query expressions, provided the column counts and corresponding data types are compatible.

### 3.1. INTERSECT Compares the Entire Row

When multiple columns are selected, MySQL compares the full row by column position:

```sql
SELECT customer_id, region_code
FROM current_customers

INTERSECT

SELECT customer_id, region_code
FROM eligible_customers;
```

A row appears in the output only if both `customer_id` and `region_code` match a row on the right side. If you only want to intersect by `customer_id`, select only that column on both sides.

Output column names are taken from the first `SELECT` query. Therefore, place meaningful aliases on the first side if the result will be consumed further in application code or nested queries.

## 4. EXCEPT: Retrieving Rows Only in the Left Query

`EXCEPT` returns rows present in the left result that are absent from the right result. Operand order is significant; swapping the two queries can completely change the output.

Example: find customers who have a paid order but no high-priority support ticket:

```sql
SELECT customer_id
FROM orders
WHERE status = 'paid'

EXCEPT

SELECT customer_id
FROM support_tickets
WHERE priority = 'high'
ORDER BY customer_id;
```

The result is the directional difference `orders` minus `support_tickets`. `EXCEPT` does not mean "differs in any column"; it excludes left-hand rows if a matching row exists on the right side.

Example reversing the order:

```sql
SELECT customer_id
FROM support_tickets
WHERE priority = 'high'

EXCEPT

SELECT customer_id
FROM orders
WHERE status = 'paid';
```

The second query finds customers with a high-priority ticket who have no paid order. That is a different set from the previous example.

## 5. DISTINCT and ALL: Handling Duplicate Rows

In MySQL, `DISTINCT` is the default for `INTERSECT` and `EXCEPT`. You can write it explicitly:

```sql
SELECT customer_id FROM orders
INTERSECT DISTINCT
SELECT customer_id FROM support_tickets;
```

Or use `ALL` to preserve occurrence counts under multiset/bag semantics:

```sql
SELECT customer_id FROM orders
INTERSECT ALL
SELECT customer_id FROM support_tickets;
```

Differences:

- `INTERSECT DISTINCT`: each shared row appears only once.
- `INTERSECT ALL`: the number of times a row appears in the result equals the smaller count of occurrences between the two sides.
- `EXCEPT DISTINCT`: returns each left-hand row once if that row does not appear on the right side.
- `EXCEPT ALL`: remaining occurrences equal the left-hand count minus the right-hand count, clamped at a minimum of 0.

`ALL` matters when inputs can contain multiple identical rows, such as logs, events, or un-deduplicated transaction data.

## 6. Occurrence Counting Examples with INTERSECT ALL and EXCEPT ALL

Use literal queries to observe occurrence counts clearly:

```sql
(
    SELECT 1 AS item_id
    UNION ALL SELECT 1
    UNION ALL SELECT 1
    UNION ALL SELECT 2
)
INTERSECT ALL
(
    SELECT 1 AS item_id
    UNION ALL SELECT 1
    UNION ALL SELECT 3
)
ORDER BY item_id;
```

The value `1` appears three times on the left and twice on the right, so the result contains two rows of `1`. Values `2` and `3` do not appear on both sides and are not returned.

With `EXCEPT ALL`:

```sql
(
    SELECT 1 AS item_id
    UNION ALL SELECT 1
    UNION ALL SELECT 1
    UNION ALL SELECT 2
)
EXCEPT ALL
(
    SELECT 1 AS item_id
    UNION ALL SELECT 1
    UNION ALL SELECT 3
)
ORDER BY item_id;
```

The left side has three `1` rows and the right side has two `1` rows, leaving one `1` row in the output. Row `2` appears only on the left and is retained. Row `3` appears only on the right and is not added to the output.

When `DISTINCT` is used or the keyword is omitted, results are deduplicated. Do not pick `ALL` or `DISTINCT` out of habit; determine whether the input represents a mathematical set or a multiset whose multiplicity carries meaning.

## 7. Structural Requirements of the Two Queries

Both sides of `INTERSECT` or `EXCEPT` must return the same number of columns. Corresponding columns must have combinable/comparable data types.

Valid column count example:

```sql
SELECT customer_id, region_code
FROM current_customers
INTERSECT
SELECT customer_id, region_code
FROM archived_customers;
```

Invalid example due to mismatched column counts:

```sql
-- Wrong: the left side returns two columns, the right side returns only one
SELECT customer_id, region_code
FROM current_customers
INTERSECT
SELECT customer_id
FROM archived_customers;
```

Column names do not need to match; the operation pairs columns by position. However, choose columns with matching business meaning to avoid comparing unrelated data.

If data types differ, MySQL may convert them to a common result type. To prevent unexpected implicit conversions, use explicit `CAST()`:

```sql
SELECT CAST(customer_code AS CHAR(20)) AS customer_key
FROM legacy_customers

INTERSECT

SELECT CAST(customer_id AS CHAR(20)) AS customer_key
FROM current_customers;
```

The example above makes sense only if string codes and numeric IDs genuinely represent the same key domain. In real designs, it is better to standardize types at the source or convert using well-defined rules.

## 8. NULL in Set Operations

In set operations performing duplicate comparison, MySQL treats corresponding `NULL` values as equal for row-matching purposes. This differs from standard SQL `=` comparisons, where `NULL = NULL` returns `UNKNOWN`.

Example:

```sql
SELECT NULL AS value
INTERSECT
SELECT NULL AS value;
```

The result has one `NULL` row, because both sides contain the same row under set-operation rules.

EXCEPT example:

```sql
SELECT NULL AS value
EXCEPT
SELECT NULL AS value;
```

The result is empty because the `NULL` row on the left also exists on the right.

When replacing set operations with `JOIN`, `EXISTS`, or `NOT EXISTS`, pay attention to this difference. `a.col = b.col` does not match two `NULL` values; for null-safe comparison in MySQL, use the `<=>` operator.

## 9. Collation and String Comparison Rules

String rows are compared according to the character set and collation of the expressions. Under a case-insensitive collation, strings differing only in case can be treated as duplicates when `INTERSECT DISTINCT` or `EXCEPT DISTINCT` deduplicates.

Illustrative example:

```sql
SELECT _utf8mb4'A' COLLATE utf8mb4_0900_ai_ci AS label
INTERSECT
SELECT _utf8mb4'a' COLLATE utf8mb4_0900_ai_ci AS label;
```

With the `utf8mb4_0900_ai_ci` collation on MySQL 8.0, comparisons are case-insensitive and accent-insensitive; the two values are treated as equivalent in the set operation. If business rules require case sensitivity, choose an appropriate collation, such as an available `_as_cs` collation on your version.

When the two sides use incompatible collations, MySQL may raise an error or require explicit conversion rules. You can specify a collation explicitly on both sides, ensuring character sets are compatible and understanding the impact on comparison semantics.

## 10. Precedence When Combining Multiple Operators

MySQL applies the following precedence rules:

1. `INTERSECT` has higher precedence than `UNION` and `EXCEPT`.
2. `UNION` and `EXCEPT` share the same precedence; without parentheses, they associate from left to right.
3. Use parentheses to make the intended evaluation order explicit and prevent misreading.

Example:

```sql
SELECT id FROM set_a
UNION
SELECT id FROM set_b
INTERSECT
SELECT id FROM set_c;
```

Because `INTERSECT` has higher precedence, this is equivalent to:

```sql
SELECT id FROM set_a
UNION
(
    SELECT id FROM set_b
    INTERSECT
    SELECT id FROM set_c
);
```

If you want the union of A and B first, and then subtract C, write it explicitly:

```sql
(
    SELECT id FROM set_a
    UNION
    SELECT id FROM set_b
)
EXCEPT
SELECT id FROM set_c;
```

Do not rely on memory when an expression involves three or more operators. Use parentheses and query formatting to express the exact combination order.

## 11. ORDER BY and LIMIT with Set Results

`ORDER BY` and `LIMIT` at the end of the expression apply to the final set result:

```sql
SELECT customer_id FROM orders
INTERSECT
SELECT customer_id FROM support_tickets
ORDER BY customer_id DESC
LIMIT 20;
```

This query returns at most 20 shared IDs, sorted descending. Without `ORDER BY`, result ordering is not guaranteed.

If you want `ORDER BY` or `LIMIT` to apply to individual operands, wrap each query block in parentheses:

```sql
(
    SELECT customer_id
    FROM orders
    ORDER BY created_at DESC
    LIMIT 100
)
INTERSECT
(
    SELECT customer_id
    FROM support_tickets
    ORDER BY created_at DESC
    LIMIT 100
)
ORDER BY customer_id;
```

In this example, each side limits its input set before computing the intersection; the trailing `ORDER BY customer_id` sorts the intersection result. Distinguish these two meanings clearly: limiting each source before intersecting is not equivalent to intersecting everything and then limiting.

## 12. Comparing with JOIN, EXISTS, and NOT EXISTS

`INTERSECT` and `EXCEPT` express set operations over entire rows. In many cases, equivalent queries can be written with `EXISTS` or `NOT EXISTS`, especially when comparing a single key.

### 12.1. Replacing INTERSECT DISTINCT with EXISTS

```sql
SELECT DISTINCT o.customer_id
FROM orders AS o
WHERE o.status = 'paid'
  AND EXISTS (
      SELECT 1
      FROM support_tickets AS t
      WHERE t.priority = 'high'
        AND t.customer_id <=> o.customer_id
  );
```

The `<=>` operator is MySQL's null-safe equality comparison. It matches two `NULL` values, aligning better with set-operation row-comparison semantics. If `customer_id` is declared `NOT NULL`, `=` can be used.

### 12.2. Replacing EXCEPT DISTINCT with NOT EXISTS

```sql
SELECT DISTINCT o.customer_id
FROM orders AS o
WHERE o.status = 'paid'
  AND NOT EXISTS (
      SELECT 1
      FROM support_tickets AS t
      WHERE t.priority = 'high'
        AND t.customer_id <=> o.customer_id
  );
```

This query returns IDs present in orders that are absent from high-priority support tickets. Using `NOT EXISTS` is generally safer than `NOT IN` when the right-hand set can contain `NULL`, because `NOT IN` can evaluate to `UNKNOWN` and unexpectedly filter out all rows.

### 12.3. Why JOIN Is Not Always Equivalent

An `INNER JOIN` can produce multiple rows when either the left or right side has duplicate keys. `INTERSECT DISTINCT` deduplicates the result rows. To replace accurately, verify whether the data has duplicates and whether multiplicity must be preserved.

The `EXISTS` queries above emulate distinct semantics for a single key column. They do not automatically emulate `INTERSECT ALL` or `EXCEPT ALL`; preserving occurrence counts requires computing multiplicities on each side and taking the minimum or subtracting according to ALL rules.

## 13. Alternatives When MySQL Does Not Support INTERSECT/EXCEPT

On MySQL 8.0.30 and earlier, rewrite according to business intent using `EXISTS`/`NOT EXISTS`, `JOIN`, or grouping. Example finding shared IDs:

```sql
SELECT DISTINCT a.customer_id
FROM paid_orders AS a
WHERE EXISTS (
    SELECT 1
    FROM priority_tickets AS b
    WHERE b.customer_id <=> a.customer_id
);
```

Finding IDs only in orders:

```sql
SELECT DISTINCT a.customer_id
FROM paid_orders AS a
WHERE NOT EXISTS (
    SELECT 1
    FROM priority_tickets AS b
    WHERE b.customer_id <=> a.customer_id
);
```

These two patterns assume the goal is a distinct set by `customer_id`. If multiple columns must be compared, include every corresponding column pair in null-safe comparisons. If duplicates must be preserved per `ALL`, build occurrence-counting logic; `DISTINCT` and `EXISTS` discard count information.

Do not mechanically substitute `NOT IN` for `EXCEPT`, especially when columns are nullable. Verify NULL semantics before choosing an equivalent rewrite.

## 14. Performance and Execution Plans

`INTERSECT` and `EXCEPT` are set-operation syntax and are not guaranteed to be faster than `JOIN`, `EXISTS`, or `NOT EXISTS`. MySQL must compare rows from both sides and may require intermediate structures to deduplicate or compute the result.

Inspect queries with `EXPLAIN`:

```sql
EXPLAIN
SELECT customer_id
FROM orders
WHERE status = 'paid'
INTERSECT
SELECT customer_id
FROM support_tickets
WHERE priority = 'high';
```

Things to check:

- Whether indexes support the filter predicates on each side.
- Whether the estimated post-filter row count is excessive.
- Whether expensive materialization, temporary tables, or deduplication steps occur.
- Whether data types or collations force conversions across many rows.
- `EXPLAIN ANALYZE` on supported versions shows actual timing and row counts for each iterator.

Indexes on filter or comparison keys can reduce the number of rows processed. For instance, if you often filter `orders` by `status` and project `customer_id`, evaluate `(status, customer_id)`; if filtering tickets by `priority`, evaluate `(priority, customer_id)`. This is only a starting point: measure on realistic data distributions and consider other queries using the table.

## 15. Pre-Flight Data Checks Before Using Set Operations

Before writing `INTERSECT` or `EXCEPT`, confirm:

1. Both sides return the exact same number of columns.
2. Columns at corresponding positions carry matching meanings.
3. Data types combine cleanly without unintended conversions.
4. Collation comparison rules match business requirements.
5. Whether duplicates must be kept (`ALL`) or a distinct set is needed (`DISTINCT`).
6. What `NULL` means and whether null-safe comparisons are needed when writing alternatives.
7. Combination order of multiple operators is explicitly parenthesized when needed.
8. Whether `ORDER BY`/`LIMIT` applies to the overall result or individual branches.
9. Whether the MySQL version in every environment supports the syntax.

## 16. Common Mistakes and Misconceptions

| Misconception / Error | Reality | Solution |
| --- | --- | --- |
| Every MySQL 8.0 release supports INTERSECT and EXCEPT | Only supported starting in 8.0.31 | Check `VERSION()` on target servers |
| INTERSECT compares only a single key | It compares all selected columns by position | Select only the columns you intend to compare |
| EXCEPT does not depend on operand order | `A EXCEPT B` differs from `B EXCEPT A` | Clearly identify the source set and subtracted set |
| INTERSECT keeps duplicates by default | Default is DISTINCT | Use `ALL` if multiplicity is needed |
| INTERSECT ALL returns all duplicates from both sides | Occurrence count is the minimum between the two sides | Compute multiplicity using bag semantics |
| EXCEPT ALL equals a DISTINCT anti-join | It subtracts right-side counts from left-side counts | Do not use EXISTS if duplicates must be kept |
| NULL never matches NULL | Set operations treat corresponding NULLs as equal when comparing rows | Use `<=>` in alternative queries |
| UNION, EXCEPT, and INTERSECT share precedence | INTERSECT has higher precedence; UNION/EXCEPT share precedence | Use parentheses to clarify intent |
| ORDER BY in the first branch controls final order | Trailing ORDER BY applies to the set; per-branch requires parentheses | Place ORDER BY in the proper scope |
| NOT IN always safely replaces EXCEPT | NULL in the subquery can yield UNKNOWN | Prefer NOT EXISTS with appropriate comparisons |

## 17. Hands-on Exercises

1. Run `SELECT VERSION()` and determine whether the server supports `INTERSECT`/`EXCEPT`.
2. Write two `SELECT` queries with one shared column; use `INTERSECT` to find common values.
3. Reverse the two sides of `EXCEPT` and explain why the result changes.
4. Use `INTERSECT DISTINCT` and `INTERSECT ALL` on data with duplicates; count rows in each result.
5. Use `EXCEPT DISTINCT` and `EXCEPT ALL` with differing occurrence counts on each side.
6. Test two queries containing `NULL`; observe how set operations handle NULL.
7. Test strings differing in case under `_ai_ci` and `_as_cs` collations; compare `INTERSECT` results.
8. Combine `UNION`, `EXCEPT`, and `INTERSECT`; then use parentheses to alter evaluation order.
9. Rewrite an `INTERSECT DISTINCT` query using `EXISTS` and an `EXCEPT DISTINCT` query using `NOT EXISTS`.
10. Use `EXPLAIN` to compare the plan of a set operation against the EXISTS/NOT EXISTS alternative on a sufficiently large dataset.
11. On MySQL 8.0.30 or earlier if a lab environment is available, test the syntax and observe the error; then run on 8.0.31 or later.

## 18. Takeaways

`INTERSECT` retrieves rows present in both queries; `EXCEPT` retrieves rows present in the left query but absent from the right query. MySQL supports both operators starting in version 8.0.31. By default they use `DISTINCT`; `ALL` preserves multiplicity, with `INTERSECT ALL` taking the smaller count between the two sides and `EXCEPT ALL` subtracting right-side counts from left-side counts.

Both queries must return the same number of columns in matching positions with compatible data types. Operations compare entire rows and are affected by data types and collations; corresponding `NULL` values are treated as equal in set comparisons. `INTERSECT` has higher precedence than `UNION` and `EXCEPT`; use parentheses whenever needed to control order. On MySQL older than 8.0.31, you can substitute `EXISTS`/`NOT EXISTS` for distinct semantics, while handling `NULL` and duplicates deliberately. Always verify version support, data, `EXPLAIN`, and actual results before deploying.
