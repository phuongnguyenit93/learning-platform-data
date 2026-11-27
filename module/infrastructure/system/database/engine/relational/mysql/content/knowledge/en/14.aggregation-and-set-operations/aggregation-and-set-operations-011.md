# ORDER BY/LIMIT in Set Queries and Their Scope

When combining results from multiple `SELECT` statements, you often need to sort or retrieve only the first few rows. In MySQL, `ORDER BY` and `LIMIT` can apply to the entire combined set result, or individually to each `SELECT` branch if that branch is enclosed in parentheses. Placing these clauses in the wrong position can cause the query to return a completely different set of rows than the business requirement specifies.

For example, a report asks for the 10 newest events across two data sources. There are two distinct requirements: taking the 10 newest events after combining both sources, or taking the 10 newest events from each source and then combining them. Both use `UNION ALL`, `ORDER BY`, and `LIMIT`, yet their scopes differ.

In the **DATABASE_MYSQL** module, understanding query block boundaries, parenthesization rules, result ordering, set-result column aliases, and deterministic top-N queries is essential for writing semantically accurate set queries.

## 1. What Is a Set Query?

A set operation combines the results of two or more query blocks. MySQL supports these operators:

| Operator | Meaning | MySQL Version |
|---|---|---|
| `UNION` or `UNION DISTINCT` | Combines rows and removes duplicate rows | Available since MySQL versions prior to 8.0 |
| `UNION ALL` | Combines rows and retains duplicate rows | Available since MySQL versions prior to 8.0 |
| `INTERSECT` | Retains only rows appearing in both results | MySQL 8.0.31 and later |
| `EXCEPT` | Retains rows in the left result that are absent from the right result | MySQL 8.0.31 and later |

Query blocks in a set operation must return the exact same number of columns, and corresponding columns must have compatible data types. Column names for the set result come from the first `SELECT` list.

Example combining customers from two sources:

```sql
SELECT customer_id, full_name
FROM online_customers
UNION ALL
SELECT customer_id, full_name
FROM store_customers;
```

`UNION ALL` retains duplicate rows, even when the same customer appears in both sources. If `UNION` (which defaults to `UNION DISTINCT`) is used, MySQL removes duplicate rows across all result columns.

## 2. Trailing ORDER BY and LIMIT Apply to the Entire Combined Result

If you place `ORDER BY` and `LIMIT` after the final query block, those clauses apply to the combined result:

```sql
SELECT order_id AS event_id, created_at AS event_time
FROM online_events
UNION ALL
SELECT event_id, created_at
FROM archived_events
ORDER BY event_time DESC, event_id DESC
LIMIT 10;
```

The logical sequence is:

1. Read rows from `online_events`.
2. Read rows from `archived_events`.
3. Combine the two result sets with `UNION ALL`.
4. Sort the entire combined result by `event_time` descending, then by `event_id` descending.
5. Return only the first 10 rows.

The output contains at most 10 of the newest events across both sources combined—not 10 rows from each source.

With `UNION DISTINCT`, duplicate removal occurs as part of the set operation before the final limit is applied. For example:

```sql
SELECT product_id FROM online_products
UNION
SELECT product_id FROM store_products
ORDER BY product_id
LIMIT 20;
```

MySQL removes duplicate `product_id` values between the two results, sorts the remaining distinct values, and takes at most 20 rows.

## 3. Per-Branch ORDER BY and LIMIT Inside SELECT Branches

If you want to limit each source before combining, wrap each query block in parentheses:

```sql
(SELECT order_id AS event_id, created_at AS event_time
 FROM online_events
 ORDER BY created_at DESC, order_id DESC
 LIMIT 10)
UNION ALL
(SELECT event_id, created_at
 FROM archived_events
 ORDER BY created_at DESC, event_id DESC
 LIMIT 10);
```

Each branch selects at most 10 of the newest rows from its own source. The combined set result can contain up to 20 rows.

Note: `ORDER BY` inside each branch determines which rows are kept by that branch's `LIMIT`. It does not guarantee the final display order of the combined result. If the final result needs to be sorted, add an outer `ORDER BY` as well:

```sql
(SELECT order_id AS event_id, created_at AS event_time, 'online' AS source_name
 FROM online_events
 ORDER BY created_at DESC, order_id DESC
 LIMIT 10)
UNION ALL
(SELECT event_id, created_at, 'archive'
 FROM archived_events
 ORDER BY created_at DESC, event_id DESC
 LIMIT 10)
ORDER BY event_time DESC, source_name ASC, event_id DESC
LIMIT 10;
```

This query performs two limits:

- Each source picks at most 10 events.
- After combining up to 20 rows, the outer query sorts globally and takes at most 10 of the newest events.

Local ordering and global ordering serve different roles. Never omit the outer `ORDER BY` if the application expects a specific final row order.

## 4. Without Parentheses, LIMIT Does Not Apply Per Branch

Compare these two queries.

**Retrieve at most 5 rows from the overall result:**

```sql
SELECT order_id, created_at
FROM online_events
UNION ALL
SELECT event_id, created_at
FROM archived_events
ORDER BY created_at DESC
LIMIT 5;
```

**Retrieve at most 5 rows from each branch:**

```sql
(SELECT order_id, created_at
 FROM online_events
 ORDER BY created_at DESC, order_id DESC
 LIMIT 5)
UNION ALL
(SELECT event_id, created_at
 FROM archived_events
 ORDER BY created_at DESC, event_id DESC
 LIMIT 5);
```

In the first query, `LIMIT 5` sits at the set-operation level, so the total returned row count cannot exceed 5. In the second query, each branch has its own `LIMIT 5`, so the combined output can have up to 10 rows.

Parentheses define query block scope. This is not merely stylistic formatting; it changes the meaning of the SQL statement.

## 5. ORDER BY in a Branch Needs LIMIT for Top-N Selection

Inside a `UNION` branch, `ORDER BY` without `LIMIT` does not guarantee the order of the final output. When a branch is not limited, its internal ordering has no semantic effect on the set operation and the optimizer may drop the unnecessary sort.

If your goal is selecting the newest rows from each source, pair `ORDER BY` with `LIMIT` inside parentheses:

```sql
(SELECT order_id, created_at
 FROM online_events
 ORDER BY created_at DESC, order_id DESC
 LIMIT 100)
UNION ALL
(SELECT event_id, created_at
 FROM archived_events
 ORDER BY created_at DESC, event_id DESC
 LIMIT 100);
```

If you only want to sort all combined rows, place `ORDER BY` after the set operation:

```sql
SELECT order_id, created_at FROM online_events
UNION ALL
SELECT event_id, created_at FROM archived_events
ORDER BY created_at DESC, order_id DESC;
```

The last example assumes the first output column is named `order_id` from the first branch. If that column name is unsuitable, assign an explicit alias in the first `SELECT`.

## 6. Outer ORDER BY Uses Output Column Names from the First SELECT

In a set operation, output column names are determined by the first `SELECT` list. Therefore, the global `ORDER BY` should reference column names or aliases appearing in the first branch.

```sql
SELECT
    order_id AS event_id,
    created_at AS event_time
FROM online_events
UNION ALL
SELECT
    event_id,
    created_at
FROM archived_events
ORDER BY event_time DESC, event_id DESC;
```

Here, the result columns are named `event_id` and `event_time` because they were declared in the first `SELECT`. Aliases in subsequent branches do not determine output column names.

Do not use source table qualifiers to reference columns in the global `ORDER BY`:

```sql
-- Do not use a source table qualifier in the ORDER BY of a set result
SELECT order_id, created_at FROM online_events
UNION ALL
SELECT event_id, created_at FROM archived_events
ORDER BY online_events.created_at DESC;
```

Instead, use the output column name:

```sql
SELECT order_id AS event_id, created_at AS event_time
FROM online_events
UNION ALL
SELECT event_id, created_at
FROM archived_events
ORDER BY event_time DESC;
```

If you need to sort by an expression, include that expression as an output column in every branch with compatible types, or wrap the set operation in a derived table and sort in the outer query.

## 7. ORDER BY and LIMIT Must Define Deterministic Order

`LIMIT` without `ORDER BY` selects an arbitrary set of rows with no guaranteed order. Two executions of the same SQL query can return different rows as data, indexes, execution plans, or server state change.

Do not write a top-N query like this when business rules require the newest records:

```sql
SELECT order_id, created_at
FROM orders
LIMIT 10;
```

Specify the sorting criteria:

```sql
SELECT order_id, created_at
FROM orders
ORDER BY created_at DESC, order_id DESC
LIMIT 10;
```

If multiple rows can share the same `created_at`, add a unique key such as `order_id` to stabilize the order. Across multiple sources, you may also need `source_name` if IDs are only unique within each source.

Example:

```sql
SELECT order_id AS event_id, created_at AS event_time, 'online' AS source_name
FROM online_events
UNION ALL
SELECT event_id, created_at, 'archive'
FROM archived_events
ORDER BY event_time DESC, source_name ASC, event_id DESC
LIMIT 50;
```

If `(source_name, event_id)` is unique, the final order is deterministic even when multiple events occur at the exact same timestamp.

## 8. LIMIT with OFFSET and Pagination

MySQL supports two forms:

```sql
LIMIT row_count OFFSET offset
```

or:

```sql
LIMIT offset, row_count
```

Example: fetch the third page with 20 rows per page:

```sql
SELECT event_id, event_time
FROM (
    SELECT order_id AS event_id, created_at AS event_time
    FROM online_events
    UNION ALL
    SELECT event_id, created_at
    FROM archived_events
) AS all_events
ORDER BY event_time DESC, event_id DESC
LIMIT 20 OFFSET 40;
```

This paginates over the combined result. `OFFSET 40` skips the first 40 rows of the global ordering and returns the next 20 rows.

With large offsets, MySQL still has to locate and skip preceding rows, so queries slow down as data grows. For large datasets with stable ordering, consider keyset pagination: using the last row's values from the previous page as the bookmark for the next page.

Illustrative keyset pagination for descending order by `(event_time, event_id)`:

```sql
SELECT event_id, event_time
FROM (
    SELECT order_id AS event_id, created_at AS event_time
    FROM online_events
    UNION ALL
    SELECT event_id, created_at
    FROM archived_events
) AS all_events
WHERE (event_time, event_id) < (?, ?)
ORDER BY event_time DESC, event_id DESC
LIMIT 20;
```

The two parameters are `event_time` and `event_id` from the last row of the previous page. This works well when the sort pair produces a unique order and data does not shift in ways that break pagination rules. For large set results, inspect the execution plan because derived tables and set operations may still require materialization or sorting.

## 9. UNION DISTINCT vs UNION ALL Changes LIMIT Semantics

`UNION` removes duplicate rows by default; `UNION ALL` keeps all rows. This affects which rows remain before the global `LIMIT` is applied.

```sql
SELECT customer_id FROM online_customers
UNION
SELECT customer_id FROM store_customers
ORDER BY customer_id
LIMIT 100;
```

The query above returns at most 100 unique `customer_id` values. With `UNION ALL`, a customer present in both sources appears twice and consumes two slots out of the 100 rows.

When `LIMIT` is placed inside each branch of a `UNION DISTINCT`, each branch is truncated before deduplication at the set level. This can cause the final output to contain fewer rows than the global limit or miss a value that would have belonged to the overall top-N. Use local limits only when business requirements explicitly call for per-source top-N selection.

## 10. ORDER BY/LIMIT with INTERSECT and EXCEPT

MySQL supports `INTERSECT` and `EXCEPT` starting in MySQL 8.0.31. The scope of `ORDER BY` and `LIMIT` follows the same query-expression rules:

- Clauses at the end of the set operation apply to the entire result.
- To limit individual operands before applying the set operation, enclose the corresponding query block in parentheses.
- To sort the final result, place `ORDER BY` at the outermost level.

Example: find 20 products present in both lists, sorted by ID:

```sql
SELECT product_id FROM current_catalog
INTERSECT
SELECT product_id FROM promoted_products
ORDER BY product_id
LIMIT 20;
```

Example: find current products that are not in the discontinued list:

```sql
SELECT product_id FROM current_catalog
EXCEPT
SELECT product_id FROM discontinued_products
ORDER BY product_id
LIMIT 50;
```

If you limit individual operands before `INTERSECT` or `EXCEPT`, the inputs to the set operation have changed. That is valid only when business rules call for comparing already-limited subsets.

In MySQL, `INTERSECT` has higher precedence than `UNION` and `EXCEPT`. When combining multiple operators, use parentheses to make intent explicit rather than relying on readers memorizing operator precedence. Syntax and `ALL`/`DISTINCT` variants should be verified against your server version.

## 11. Keeping Auxiliary Sort Columns Out of the Displayed Output

A global `ORDER BY` on a set operation sorts by columns of the set-operation result. If you need to sort by an expression that you do not want returned to the application, wrap the set operation in a derived table:

```sql
SELECT event_id, event_time
FROM (
    SELECT
        order_id AS event_id,
        created_at AS event_time,
        priority
    FROM online_events
    UNION ALL
    SELECT
        event_id,
        created_at,
        priority
    FROM archived_events
) AS all_events
ORDER BY priority DESC, event_time DESC, event_id DESC
LIMIT 20;
```

If you do not want to return `priority` in the output, the outer query selects only `event_id` and `event_time` while still sorting by the derived table's column:

```sql
SELECT event_id, event_time
FROM (
    SELECT order_id AS event_id, created_at AS event_time, priority
    FROM online_events
    UNION ALL
    SELECT event_id, created_at, priority
    FROM archived_events
) AS all_events
ORDER BY priority DESC, event_time DESC, event_id DESC
LIMIT 20;
```

The `priority` column must be included in the inner result so the outer query can see it. Column names and positions across the two branches must still be compatible.

## 12. Performance and Execution Plans

A set operation may have to read multiple sources, deduplicate rows, materialize intermediate results, and sort the entire combined set. A global `LIMIT` does not guarantee MySQL reads only the exact number of rows returned; inspect the plan to assess cost.

Example:

```sql
EXPLAIN
SELECT order_id AS event_id, created_at AS event_time
FROM online_events
UNION ALL
SELECT event_id, created_at
FROM archived_events
ORDER BY event_time DESC, event_id DESC
LIMIT 20;
```

On MySQL 8.0.18 and later, you can use `EXPLAIN ANALYZE` to observe actual timing and row counts. Because it executes the query, run it on test data or under controlled load.

Optimization guidelines:

- Add suitable indexes for filter predicates and sort columns in each source.
- Use `UNION ALL` if duplicate removal is unnecessary, avoiding deduplication overhead.
- If only per-source top-N is needed, place `ORDER BY` and `LIMIT` inside parenthesized branches to shrink the number of rows entering the set operation.
- If global top-N is needed, keep `ORDER BY`/`LIMIT` at the outermost level and inspect sorting/materialization in the plan.
- Avoid `SELECT *`; include only needed columns plus required sort keys in the set operation.
- For deep pagination, consider keyset pagination instead of large `OFFSET` values.

Do not assume `LIMIT` automatically makes a query fast. If the server must still read, deduplicate, or sort a massive dataset before identifying the first 20 rows, cost can remain high.

## 13. Checklist for Determining ORDER BY/LIMIT Scope

Before finalizing a set query, verify:

1. Is `ORDER BY` inside a parenthesized query block or at the end of the entire set operation?
2. Should `LIMIT` apply per source or to the combined row count?
3. If using per-source top-N, does the local ordering include a unique tie-breaker?
4. Does the final output also need an outer `ORDER BY` to guarantee display order?
5. Does the global `ORDER BY` reference output column names/aliases from the first `SELECT`?
6. Have you avoided source table qualifiers at the set-result level?
7. Does `UNION` vs `UNION ALL` match whether duplicates must be removed or preserved?
8. If using `INTERSECT`/`EXCEPT`, does the MySQL version support it and do parentheses clarify operator precedence?
9. Does `LIMIT` have a deterministic `ORDER BY` to prevent arbitrary row selection?
10. Does `EXPLAIN` or `EXPLAIN ANALYZE` show acceptable sorting, materialization, and row counts?

## 14. Hands-on Exercises

Suppose you have two tables: `online_events(order_id, created_at, event_type)` and `archived_events(event_id, created_at, event_type)`.

1. Use `UNION ALL` to combine all events from both tables.
2. Add `ORDER BY` and `LIMIT 10` at the end to get the 10 newest events across both sources.
3. Wrap each `SELECT` in parentheses with `ORDER BY ... LIMIT 10` inside to get at most 10 rows from each source.
4. Add an outer `ORDER BY` and `LIMIT 10` to pick the 10 newest rows out of the up-to-20 combined rows.
5. Replace `UNION ALL` with `UNION`; insert duplicate data and compare results.
6. Change an alias in the first `SELECT` and reference it in the global `ORDER BY`; try using a source table name and observe the error.
7. Remove `ORDER BY` from a query with `LIMIT`, run it multiple times, and explain why the row set is not guaranteed.
8. If using MySQL 8.0.31+, test `INTERSECT` and `EXCEPT` with outer `ORDER BY`/`LIMIT`.
9. Use `EXPLAIN` to compare a global top-N query against a query limiting top-N separately per source.

You have completed this lesson when you can accurately identify whether `ORDER BY` and `LIMIT` affect individual branches or the entire result, choose `UNION` vs `UNION ALL`, place parentheses properly, and enforce deterministic top-N ordering. Express scope clearly through query block structure so your SQL output always matches reporting requirements.
