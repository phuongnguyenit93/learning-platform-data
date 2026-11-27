# ORDER BY, NULL Ordering, and Deterministic Sorting Requirements

`ORDER BY` sorts the rows in a query result by one or more expressions. You can specify ascending (`ASC`) or descending (`DESC`) direction, control the position of `NULL` values using expressions, and add secondary keys so results have a stable order.

In MySQL, `NULL` is considered smaller than all non-`NULL` values when sorting: `ASC` places `NULL` first, whereas `DESC` places `NULL` last. If business rules require a different position, specify it explicitly in `ORDER BY`. Especially when using `LIMIT`, pagination, or priority-based processing, you must establish a deterministic order by appending a unique tie-breaker column, typically the primary key.

## 1. Basic Syntax of ORDER BY

General syntax:

```sql
SELECT column_list
FROM table_name
WHERE condition
ORDER BY expression [ASC | DESC], expression [ASC | DESC];
```

- `ASC` sorts in ascending order and is the default if no direction is given.
- `DESC` sorts in descending order.
- You can sort by multiple columns or expressions. MySQL evaluates the earlier expression first; if two rows tie on that expression, it evaluates the next expression.
- `ORDER BY` appears near the end of the query, after `WHERE`, `GROUP BY`, and `HAVING` when those clauses are present.

Example sorting products by ascending price:

```sql
SELECT id, name, price
FROM products
ORDER BY price ASC;
```

Sorting by descending price:

```sql
SELECT id, name, price
FROM products
ORDER BY price DESC;
```

You can omit `ASC` since it is the default direction:

```sql
SELECT id, name, price
FROM products
ORDER BY price;
```

## 2. Sorting by Multiple Columns

When sorting by multiple expressions, priority runs from left to right. For example, displaying orders by status and then by creation time:

```sql
SELECT id, status, created_at
FROM orders
ORDER BY status ASC, created_at DESC, id DESC;
```

MySQL evaluates them in order:

1. Groups rows by `status` ascending.
2. Within the same status, places the newest `created_at` first.
3. If two rows share the same status and creation timestamp, orders by `id` descending.

Sort directions can vary across columns. This is useful when you want to prioritize a group in a business order while sorting timestamps or IDs in the opposite direction.

Example prioritizing pending orders first, then confirmed orders, and sorting newest first within each group:

```sql
SELECT id, status, created_at
FROM orders
ORDER BY
    CASE status
        WHEN 'pending' THEN 1
        WHEN 'confirmed' THEN 2
        WHEN 'shipped' THEN 3
        WHEN 'cancelled' THEN 4
        ELSE 5
    END ASC,
    created_at DESC,
    id DESC;
```

`CASE` expresses an explicit business order without relying on alphabetical order of status strings.

## 3. Default Ordering of NULL in MySQL

MySQL treats `NULL` as smaller than non-`NULL` values when sorting. Therefore:

| Statement | Position of NULL |
| --- | --- |
| `ORDER BY column ASC` | Start of results |
| `ORDER BY column DESC` | End of results |

Example with task due dates:

```sql
CREATE TABLE tasks (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(150) NOT NULL,
    due_at DATETIME NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

INSERT INTO tasks (title, due_at) VALUES
    ('Write documentation', '2026-11-20 09:00:00'),
    ('Review schema', NULL),
    ('Test queries', '2026-11-19 15:00:00'),
    ('Update examples', NULL);
```

Sorting due dates ascending:

```sql
SELECT id, title, due_at
FROM tasks
ORDER BY due_at ASC;
```

The two tasks without a due date (`NULL`) appear before scheduled tasks. When sorting descending:

```sql
SELECT id, title, due_at
FROM tasks
ORDER BY due_at DESC;
```

Later due dates appear first, and `NULL` rows sit at the end.

Do not assume MySQL handles `NULL` identically to every other database management system. When migrating applications between databases, check the target engine's `NULL` sorting rules.

## 4. Explicitly Placing NULL First or Last

MySQL's default puts `NULL` first for `ASC` and last for `DESC`. However, business logic sometimes requires `NULL` in the opposite position, such as unscheduled tasks appearing after scheduled tasks regardless of sort direction.

### 4.1. NULL Last When Sorting Ascending

```sql
SELECT id, title, due_at
FROM tasks
ORDER BY
    due_at IS NULL ASC,
    due_at ASC,
    id ASC;
```

The expression `due_at IS NULL` returns `0` for non-`NULL` values and `1` for `NULL` values. Sorting this expression ascending places rows with due dates (`0`) before rows without due dates (`1`).

### 4.2. NULL First When Sorting Descending

```sql
SELECT id, title, due_at
FROM tasks
ORDER BY
    due_at IS NULL DESC,
    due_at DESC,
    id DESC;
```

Sorting the `IS NULL` flag descending puts `NULL` rows first; within each group, `due_at` is sorted descending.

### 4.3. Summary Table for Controlling NULL Placement

| Goal | ORDER BY |
| --- | --- |
| Ascending, NULL first (default) | `column ASC` |
| Ascending, NULL last | `column IS NULL ASC, column ASC` |
| Descending, NULL last (default) | `column DESC` |
| Descending, NULL first | `column IS NULL DESC, column DESC` |

In real queries, append a unique secondary key after these expressions to break ties among rows with equal values:

```sql
ORDER BY due_at IS NULL ASC, due_at ASC, id ASC;
```

## 5. Why Is Deterministic Ordering Needed?

If multiple rows have identical values across all expressions in `ORDER BY`, MySQL makes no guarantee about the relative order among those rows. Results can shift between runs due to execution plans, indexes, new data, statistics, or server version.

Example:

```sql
SELECT id, title, created_at
FROM articles
ORDER BY created_at DESC
LIMIT 10;
```

If multiple articles share the same `created_at`, the query does not define which article comes first among tied timestamps. When using `LIMIT 10`, the boundary between the 10th and 11th row can change.

Add a column or combination of columns guaranteed to be unique:

```sql
SELECT id, title, created_at
FROM articles
ORDER BY created_at DESC, id DESC
LIMIT 10;
```

Here, `id` is the primary key so every row has a distinct order. Ordering by `created_at` remains the primary criterion; `id` only breaks ties when creation timestamps are equal.

A deterministic order requires this property: for any two rows in the result set, the combination of sort expressions must distinguish them. Using the primary key as the final sort expression is usually the simplest and most reliable way.

## 6. ORDER BY Is Not the Table's Physical Order

If a query has no `ORDER BY`, SQL does not guarantee row order. An observed order may coincidentally resemble insertion order, primary key order, or an index order, but that is not a contract of the query.

Example:

```sql
SELECT id, title
FROM articles;
```

You cannot rely on this output order to display newest articles, process FIFO queues, or paginate. Whenever order is required, specify `ORDER BY` in the outermost query.

Even if a subquery or view includes `ORDER BY`, the outer query still needs its own `ORDER BY` if the application requires ordered results. Ordering is not automatically preserved across query transformations.

## 7. ORDER BY with Expressions and Aliases

MySQL allows sorting by columns, `SELECT`-list aliases, or expressions:

```sql
SELECT
    id,
    quantity,
    unit_price,
    quantity * unit_price AS line_total
FROM order_items
ORDER BY line_total DESC, id ASC;
```

You can also use the expression directly:

```sql
SELECT id, quantity, unit_price
FROM order_items
ORDER BY quantity * unit_price DESC, id ASC;
```

Aliases make statements easier to read when expressions are long or returned as output columns. If an alias shares the same name as a source column, name resolution rules can cause confusion; choose distinct aliases and clear names.

Avoid relying on numeric column positions in `ORDER BY`:

```sql
-- Valid but hard to maintain
SELECT id, title, created_at
FROM articles
ORDER BY 3 DESC;
```

If someone later changes the column order in `SELECT`, the meaning of `ORDER BY 3` changes too. Writing `ORDER BY created_at DESC` is much clearer.

## 8. How Collation Affects String Sorting

When sorting text columns, MySQL uses the expression's collation to compare strings. Collation determines distinctions such as case sensitivity, accent sensitivity, and language-specific rules.

Example:

```sql
SELECT id, display_name
FROM customers
ORDER BY display_name ASC, id ASC;
```

If the collation is case-insensitive, `An` and `an` may be considered equivalent in comparison. If the collation is accent-insensitive, certain accented and unaccented variants may share the same sort weight. In such cases, add `id` as a secondary key so the result has a deterministic order.

You can specify a collation on the sort expression:

```sql
SELECT id, display_name
FROM customers
ORDER BY display_name COLLATE utf8mb4_0900_as_cs ASC, id ASC;
```

The collation `utf8mb4_0900_as_cs` is an example on MySQL 8.0; select a collation actually available in your version and compatible with the column's charset. Forcing a different collation can alter sort order and affect index usability, so verify with `EXPLAIN`.

## 9. ORDER BY with LIMIT

`LIMIT` restricts the number of returned rows. Combined with `ORDER BY`, it is commonly used to fetch top-N results or a page of data:

```sql
SELECT id, title, created_at
FROM articles
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

This query fetches the 20 newest articles in deterministic order. If `ORDER BY` is omitted, the 20 returned rows do not represent "the 20 newest articles" or any business ordering.

You can use `LIMIT offset, row_count`:

```sql
SELECT id, title, created_at
FROM articles
ORDER BY created_at DESC, id DESC
LIMIT 20, 10;
```

This skips the first 20 rows and returns the next 10. Deterministic ordering keeps paginated results stable, though large offsets can still be costly because MySQL must locate and step past all skipped rows.

## 10. Stable Pagination with Keyset Pagination

For large tables, keyset pagination (the seek method) is often more efficient than offset pagination. Instead of skipping a row count, the application sends the last sort-key values from the previous page to retrieve the next rows.

Assuming both `created_at` and `id` are `NOT NULL`, the first page query is:

```sql
SELECT id, title, created_at
FROM articles
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

Suppose the last row on the page has `created_at = '2026-11-18 10:30:00'` and `id = 500`. The next page query is:

```sql
SELECT id, title, created_at
FROM articles
WHERE created_at < '2026-11-18 10:30:00'
   OR (
       created_at = '2026-11-18 10:30:00'
       AND id < 500
   )
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

The condition matches the descending order of the `(created_at, id)` pair: fetching rows that come after the previous page's final key. In applications, pass both cursor values as parameters.

Keyset pagination has several advantages:

- Avoids scanning and discarding thousands of records before the page position.
- Less prone to page drift when new rows are inserted before the cursor position.
- Works well with a matching index on the sort columns.

It still requires a unique ordering and can be affected if a row's sort columns are updated while a user is browsing. If you need a consistent snapshot across multiple pages, consider a transaction snapshot or a fixed cutoff point per business requirements.

The example above assumes the sort columns are non-`NULL`. If columns are nullable, design cursor conditions that match the chosen `NULL` ordering rules; do not use simple `<`/`>` comparisons because comparing against `NULL` evaluates to `UNKNOWN`.

## 11. Indexes and ORDER BY Performance

MySQL can use an index to return results in sorted order without performing a separate sort step if the index structure and query align. Example:

```sql
CREATE INDEX idx_articles_created_id
ON articles (created_at DESC, id DESC);

SELECT id, title, created_at
FROM articles
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

A composite index can satisfy ordering when columns and sort directions match. Filter predicates, index column order, `ASC`/`DESC` directions, collation, and expressions in `ORDER BY` all influence the optimizer's choice.

Inspect the plan:

```sql
EXPLAIN
SELECT id, title, created_at
FROM articles
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

If `Extra` displays `Using filesort`, MySQL must perform an extra sorting pass instead of reading the entire order directly from the index. The name `filesort` does not strictly mean sort data is written to disk; the algorithm can use memory or temporary files depending on size and configuration.

Do not add an index solely to eliminate `Using filesort` without measuring the benefit. Indexes increase storage usage and write overhead. Evaluate using realistic data and `EXPLAIN` or `EXPLAIN ANALYZE` on supported versions.

### 11.1. Composite Indexes and Leftmost Prefix

Suppose a query fetches a customer's orders from newest to oldest:

```sql
SELECT id, status, created_at
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

A suitable index might be:

```sql
CREATE INDEX idx_orders_customer_created_id
ON orders (customer_id, created_at DESC, id DESC);
```

`customer_id` comes first to filter a single customer; the subsequent key parts support timestamp and ID ordering within that group. Actual index usage depends on the execution plan and real data layout.

### 11.2. ORDER BY Expressions and NULL Placement

When writing:

```sql
ORDER BY due_at IS NULL ASC, due_at ASC, id ASC
```

the expression `due_at IS NULL` may cause MySQL to require a separate sort step, even when an index exists on `due_at`. Verify with `EXPLAIN`. If this query pattern is critical and the dataset is large, you can evaluate a generated column or functional index supported by your version, but only after benchmarking performance and checking write overhead.

Do not use `COALESCE(due_at, '9999-12-31')` or an arbitrary sentinel value if that sentinel can legitimately appear in data, alter semantics, or prevent the optimizer from using an index as expected. The `IS NULL` expression states intent more clearly.

## 12. ORDER BY with UNION and Nested Queries

With `UNION`, an `ORDER BY` at the end applies to the combined result set:

```sql
SELECT id, name, created_at, 'customer' AS source_type
FROM customers
UNION ALL
SELECT id, name, created_at, 'supplier' AS source_type
FROM suppliers
ORDER BY created_at DESC, source_type ASC, id DESC;
```

The `SELECT` branches must return compatible column counts. The trailing `ORDER BY` sorts the combined result; do not rely on the ordering of individual branches.

For nested queries, place `ORDER BY` in the outermost query when the application requires final ordering:

```sql
SELECT id, title, created_at
FROM (
    SELECT id, title, created_at
    FROM articles
    WHERE status = 'published'
) AS published_articles
ORDER BY created_at DESC, id DESC;
```

Ordering inside a derived table does not automatically guarantee the ordering of the outer result. Only `ORDER BY` in the outermost query defines the row order returned to the client.

## 13. Common Mistakes and Misconceptions

| Misconception / Mistake | Reality | Fix |
| --- | --- | --- |
| Omitting `ORDER BY` because results look ordered | That order is not guaranteed by SQL | Write `ORDER BY` explicitly |
| `ORDER BY created_at` always defines a unique order | Rows with identical timestamps still tie | Append a unique key such as `id` |
| `ASC` puts NULL last | MySQL puts NULL first under ASC | Use `column IS NULL ASC` to put NULL last |
| `DESC` puts NULL first | MySQL puts NULL last under DESC | Use `column IS NULL DESC` to put NULL first |
| `LIMIT` automatically selects the latest rows | LIMIT has no ordering semantics without ORDER BY | Pair with ORDER BY and a tie-breaker key |
| A view or subquery already has ORDER BY so the outer query doesn't need it | Outer query is not guaranteed to preserve inner order | Put ORDER BY on the outermost query |
| `Using filesort` always means sorting on disk | May sort in memory or use temporary files | Evaluate sort size and execution plan |
| Adding an index always speeds up ORDER BY | Indexes add write overhead and may not match query order | Measure with EXPLAIN/EXPLAIN ANALYZE |

## 14. Process for Designing Reliable ORDER BY Clauses

When writing a query that sorts results, check these items in order:

1. **Identify business ordering:** which columns are primary criteria, ascending or descending?
2. **Decide NULL placement:** use MySQL's default or do you need an `IS NULL` expression?
3. **Add a tie-breaker:** append the primary key or a unique combination to establish a total order.
4. **Check collation and data types:** are strings compared by the desired rules; are dates/times stored in proper types?
5. **Combine LIMIT properly:** always establish deterministic ordering before taking top-N or paginating.
6. **Choose a pagination strategy:** offset for small pages; keyset when datasets are large and ordering fits.
7. **Evaluate indexes:** inspect filter conditions, key part order, and sort directions.
8. **Read the plan:** run `EXPLAIN`, benchmark in practice, and weigh `Using filesort` under load.
9. **Test edge cases:** `NULL`, duplicate values, differing letter case, tied timestamps, and concurrent inserts.

## 15. Practice Exercises

1. Create a `tasks` table with nullable `due_at` and insert at least two `NULL` rows, two rows with identical due dates, and two rows with distinct due dates.
2. Run `ORDER BY due_at ASC` and `ORDER BY due_at DESC`; record the position of `NULL`.
3. Write an ascending query that puts `NULL` last using `due_at IS NULL`.
4. Write a descending query that puts `NULL` first.
5. Create multiple rows sharing the same `created_at`; run `ORDER BY created_at DESC LIMIT 3` and compare against a query adding `id DESC`.
6. Create a composite index on `(customer_id, created_at, id)`; use `EXPLAIN` to inspect a query fetching a customer's newest orders.
7. Compare offset pagination with keyset pagination on a table with many records.
8. Create a name column with a case-insensitive collation; test values with equal sort weights and add a secondary key.
9. Use `UNION ALL` to combine two datasets, then sort at the end of the combined result set.

## 16. Key Takeaways

`ORDER BY` is the only way to request row ordering in query results. MySQL defaults to placing `NULL` first under `ASC` and last under `DESC`; you can invert this behavior explicitly using a `column IS NULL` expression. When multiple rows share identical sort values, their relative order is not guaranteed, so append a unique key such as the primary key to ensure deterministic ordering.

Combine `ORDER BY` with `LIMIT` for top-N queries or pagination; for large datasets, consider keyset pagination. Indexes can satisfy sorting when key-part ordering and query structure align, though expressions, collations, `NULL`s, and sort directions may require an additional sort step. Always define business sorting rules, `NULL` placement, and tie-breakers, and inspect execution plans before deploying queries to production.
