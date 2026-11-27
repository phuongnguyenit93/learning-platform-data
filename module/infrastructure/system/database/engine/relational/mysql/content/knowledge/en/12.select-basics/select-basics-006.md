# DISTINCT and the Cost of Deduplicating Data

`DISTINCT` removes duplicate rows from `SELECT` results. This clause is useful when you need to list a unique set of values or value combinations, but deduplication can consume memory, CPU, and I/O. On large tables, a query with `DISTINCT` may have to read a huge number of rows, store intermediate results, or sort before returning a small number of rows.

In the **DATABASE_MYSQL** module, understanding `DISTINCT` helps you write accurate queries, identify duplicates according to collation, avoid masking `JOIN` bugs, and evaluate cost using indexes and execution plans. This lesson focuses on deduplication semantics, cases where costs arise, how to leverage indexes, and alternative query patterns when the real goal is checking existence or counting unique values.

## 1. How Does DISTINCT Remove Duplicates?

`DISTINCT` applies to the entire list of expressions in `SELECT` and retains one row for each distinct combination of result values.

For example, the `orders` table has many orders sharing the same status:

```sql
SELECT status
FROM orders;
```

If there are 10,000 orders across only 5 statuses, the query above may return thousands of repeated rows. Adding `DISTINCT`:

```sql
SELECT DISTINCT status
FROM orders
ORDER BY status;
```

The result contains each status only once.

### 1.1. DISTINCT Across Multiple Columns

When there are multiple expressions in the select list, MySQL compares the entire combination of values. For example:

```sql
SELECT DISTINCT customer_id, status
FROM orders
ORDER BY customer_id, status;
```

If a customer has 20 `PAID` orders and 3 `PENDING` orders, the result has at most two rows for that customer: `(customer_id, 'PAID')` and `(customer_id, 'PENDING')`.

This is not equivalent to retrieving a unique value for each column individually. `DISTINCT customer_id, status` keeps distinct pairs; the same `customer_id` can appear multiple times if `status` differs.

### 1.2. DISTINCT Does Not Pick an Arbitrary Representative Row

`DISTINCT` only eliminates rows that have identical values across all selected expressions. It does not automatically pick the latest row, the row with the largest value, or the most recently updated row.

The following example does not mean "get the latest order for each customer":

```sql
SELECT DISTINCT customer_id, order_id, created_at
FROM orders;
```

Because `order_id` typically differs for each order, nearly every row remains distinct. If you need the latest order per customer, you must define a row-selection rule using window functions, subqueries, or appropriate aggregation; do not add `DISTINCT` hoping MySQL will choose for you.

## 2. NULL, Collation, and How Duplicates Are Determined

### 2.1. NULL in DISTINCT

In standard SQL comparisons, `NULL = NULL` does not return `TRUE`; it returns `UNKNOWN`. However, when deduplicating results, MySQL treats `NULL` values as duplicates for the purpose of `DISTINCT`.

Example:

```sql
SELECT DISTINCT manager_id
FROM employees;
```

If many employees have no assigned manager (`manager_id IS NULL`), the result contains only one `NULL` row.

This is useful when listing existing values, though remember `NULL` is not a real identifier. If you need to count employees without a manager, use `COUNT(*)` with `manager_id IS NULL`, rather than inferring counts from `DISTINCT` output.

### 2.2. Collation Determines Whether String Values Are Duplicates

For strings, equality is governed by the character set and collation of the expression. With a case-insensitive collation, two strings such as `'Admin'` and `'admin'` may be considered equal. With an accent-insensitive collation, certain accented and unaccented strings may also be treated as equivalent.

Illustrative example:

```sql
SELECT DISTINCT email
FROM imported_contacts;
```

If the `email` column uses a case-insensitive collation, addresses differing only in letter case may be collapsed in the result. Exact rules depend on the collation, including accent handling and trailing-space handling (`PAD SPACE` vs. `NO PAD`).

If you need character-by-character distinction for codes, choose an appropriate data type and collation at the schema level. Avoid arbitrarily wrapping columns in `BINARY()` in queries to alter comparison behavior, as expressions can impair index usage and data semantics.

You can inspect a column's collation:

```sql
SHOW FULL COLUMNS FROM imported_contacts;

SELECT
    COLUMN_NAME,
    CHARACTER_SET_NAME,
    COLLATION_NAME
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'imported_contacts';
```

### 2.3. DISTINCT Compares Expression Outputs

`DISTINCT` deduplicates based on the returned values, not necessarily the raw source column values.

```sql
SELECT DISTINCT LOWER(email) AS normalized_email
FROM imported_contacts;
```

The query above collapses addresses after applying `LOWER()`. If you need to preserve index usage and frequently search by normalized values, consider normalizing data on write or using an appropriately indexed column or generated expression. Do not assume an ordinary index on `email` automatically serves every query containing `LOWER(email)`.

## 3. Cost of Deduplicating Data

To return unique rows, MySQL must track which values have already been seen. Depending on the query, indexes, statistics, and version, the optimizer can choose different strategies.

Common costs include:

- **Reading data:** enough relevant rows must be read to determine the unique result set, unless an index allows skipping duplicate groups.
- **Storing intermediate results:** an internal temporary table may be used to record seen rows.
- **Sorting:** sorting may be required to eliminate duplicates or satisfy `ORDER BY`.
- **CPU and memory:** comparing values, checking duplicates, and maintaining intermediate structures consume resources.
- **Extra I/O:** if intermediate data exceeds memory thresholds or requires reading many pages, the query can incur substantial I/O.

Not every `DISTINCT` creates a temporary table or filesort. The optimizer may leverage an index or choose another plan. Inspect the execution plan and benchmark on representative data rather than inferring cost from syntax alone.

### 3.1. DISTINCT on Large Tables

Suppose the `page_views` table has hundreds of millions of views, but only a few thousand distinct `page_id` values:

```sql
SELECT DISTINCT page_id
FROM page_views;
```

Without a suitable index, MySQL may have to read a massive number of rows and perform deduplication over a huge dataset. Returning few rows does not mean the query cost is low.

### 3.2. DISTINCT Combined with ORDER BY and LIMIT

```sql
SELECT DISTINCT customer_id
FROM orders
ORDER BY customer_id
LIMIT 20;
```

MySQL needs to find 20 unique `customer_id` values in the requested order. If the data has many duplicates, it may have to read far more than 20 rows to collect 20 distinct values. `LIMIT` does not mean MySQL reads only 20 source rows.

If a matching index provides the order and groups identical values contiguously, the engine can skip many duplicate entries and stop earlier. This is one reason the right index can dramatically cut `DISTINCT` cost.

## 4. When Do Indexes Help Deduplicate Efficiently?

B-tree indexes store values in sorted order. When the columns in `DISTINCT` align with the index order, MySQL can read values by group and skip duplicate entries without materializing the entire result set.

### 4.1. Index on the DISTINCT Column

Example:

```sql
CREATE INDEX idx_orders_customer
    ON orders (customer_id);

EXPLAIN
SELECT DISTINCT customer_id
FROM orders;
```

The `idx_orders_customer` index orders entries by `customer_id`. MySQL can leverage the index to read unique values. In some plans, `EXPLAIN` displays `Using index for group-by` in the `Extra` column when using a Loose Index Scan.

Merely having an index on the column does not guarantee this plan will be chosen. The optimizer also weighs selectivity, the number of distinct values, statistics, and the cost of reading the index versus scanning the table.

### 4.2. Composite Indexes and Leftmost Prefix

Suppose you frequently list customers who have orders in a given status:

```sql
CREATE INDEX idx_orders_status_customer
    ON orders (status, customer_id);

EXPLAIN
SELECT DISTINCT customer_id
FROM orders
WHERE status = 'PAID';
```

With an equality condition on `status` and `customer_id` immediately following in the index, MySQL has the opportunity to read the `PAID` index slice in customer order. This composite index can support both filtering and deduplication efficiently.

If the query does not constrain the leading column of the index, the composite index may not be suitable for serving `DISTINCT` on trailing columns. The leftmost-prefix rule must be considered when designing column order.

### 4.3. Covering Indexes

If an index contains all returned columns and filter columns, MySQL can read results directly from the index without additional lookups into the clustered index per row (index-only/covering access).

For instance, `idx_orders_status_customer` can cover a query that selects only `customer_id` and filters by `status`. Reducing table lookups can lower I/O, especially when the table has many wide columns.

However, adding indexes increases storage size, `INSERT`/`UPDATE`/`DELETE` overhead, and maintenance effort. Add indexes only for important queries, rather than creating a new index for every individual `DISTINCT` statement.

## 5. Reading Execution Plans to See Where DISTINCT Spends Cost

Use `EXPLAIN` to inspect the plan chosen by the optimizer:

```sql
EXPLAIN
SELECT DISTINCT customer_id
FROM orders
WHERE status = 'PAID'
ORDER BY customer_id;
```

Columns and indicators to examine:

| Component | Meaning During Analysis |
|---|---|
| type | Access type such as range, ref, or ALL |
| possible_keys | Indexes the optimizer may consider |
| key | Index actually chosen |
| rows | Estimated number of rows to examine |
| Extra | Indicators such as Using temporary, Using filesort, or Using index for group-by |

Common interpretations:

- `Using index for group-by` can indicate the optimizer uses a Loose Index Scan to extract value groups from the index.
- `Using temporary` indicates an internal temporary table in the plan; evaluate its actual size and runtime.
- `Using filesort` indicates an extra sorting step is needed; this name does not necessarily mean data is written to a file on disk.
- `type = ALL` indicates a table scan; for small tables or queries needing most of the data, a scan may still be the cheapest option.

`EXPLAIN ANALYZE` on supported versions executes the `SELECT` and reports actual timing and row counts across iterators:

```sql
EXPLAIN ANALYZE
SELECT DISTINCT customer_id
FROM orders
WHERE status = 'PAID';
```

Use the actual figures to compare input rows, output rows, and time spent at each step. `EXPLAIN ANALYZE` executes the query; run it only after confirming the statement is safe and the test data is appropriate.

## 6. DISTINCT Can Mask JOIN Bugs

One of the most harmful anti-patterns is adding `DISTINCT` to remove rows multiplied by a `JOIN`, when the real issue is a faulty `JOIN` condition or a misunderstood one-to-many relationship.

For example, each customer has multiple orders:

```sql
SELECT DISTINCT
    c.customer_id,
    c.full_name
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
```

If the goal is merely to retrieve customers who have at least one `PAID` order, an `EXISTS` query expresses the intent more accurately:

```sql
SELECT
    c.customer_id,
    c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
```

`EXISTS` only checks whether a matching row exists; it does not produce an output row for every order. The MySQL optimizer can transform this query into a semi-join or equivalent strategy depending on query structure and version.

If you truly need order details, do not use `DISTINCT` to wipe out important data. Decide whether you want one row per order, an aggregation per customer, or one representative order selected by a deterministic rule.

### 6.1. Check JOIN Cardinality Before Adding DISTINCT

When results duplicate, check row counts before deduplicating:

```sql
SELECT
    c.customer_id,
    COUNT(*) AS joined_rows
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
GROUP BY c.customer_id
HAVING COUNT(*) > 1;
```

If a customer has multiple rows, that may be a legitimate one-to-many relationship in the data. If row counts explode unexpectedly, inspect the `JOIN` condition, foreign keys, and uniqueness of the joined table.

## 7. When to Use DISTINCT, GROUP BY, or EXISTS?

These constructs serve different goals, even though some queries can return identical outputs.

| Goal | Usually Appropriate Pattern | Reason |
|---|---|---|
| List unique values or combinations | SELECT DISTINCT ... | Directly states deduplication intent |
| Compute counts/sums/averages per group | GROUP BY with aggregates | Each group produces aggregated outputs |
| Only check whether related records exist | EXISTS | Avoids producing duplicate JOIN rows when child columns are unneeded |
| Count unique values | COUNT(DISTINCT expr) | Counts distinct values instead of returning a list |
| Pick the latest row in each group | Window function or deterministic top-per-group query | DISTINCT does not choose representative rows by order |

Do not replace `DISTINCT` with `GROUP BY` merely hoping the query will run faster. The optimizer may use a similar strategy, and `GROUP BY` typically communicates data aggregation intent.

## 8. COUNT(DISTINCT) and Aggregate Variants

`COUNT(DISTINCT expr)` counts the number of distinct non-`NULL` values of an expression:

```sql
SELECT
    COUNT(*) AS order_rows,
    COUNT(customer_id) AS non_null_customer_ids,
    COUNT(DISTINCT customer_id) AS unique_customers
FROM orders;
```

The three numbers answer three different questions:

- `COUNT(*)`: total number of rows.
- `COUNT(customer_id)`: number of rows where `customer_id` is non-`NULL`.
- `COUNT(DISTINCT customer_id)`: number of distinct customers, excluding `NULL`.

MySQL also supports counting distinct combinations of multiple expressions:

```sql
SELECT COUNT(DISTINCT customer_id, status)
FROM orders;
```

This syntax counts distinct value combinations of the listed expressions; combinations containing `NULL` in any expression are skipped. If you need to count groups containing `NULL`, handle them explicitly per business rules rather than substituting a sentinel value that might collide with real data.

Be careful with other aggregates:

```sql
SELECT
    SUM(amount) AS total_amount,
    SUM(DISTINCT amount) AS sum_of_distinct_amounts
FROM orders;
```

`SUM(DISTINCT amount)` adds each distinct `amount` value only once. Two separate orders that both equal `500,000` will contribute `500,000` only once. This is rarely true business revenue; use it only when you genuinely want the sum of the unique set of `amount` values.

## 9. DISTINCT with Expressions, ORDER BY, and LIMIT

`DISTINCT` applies to the selected expressions. If you select a normalized expression, results are deduplicated by the normalized output:

```sql
SELECT DISTINCT DATE(created_at) AS order_day
FROM orders
ORDER BY order_day DESC
LIMIT 30;
```

The query returns up to 30 distinct days that have orders. However, `DATE(created_at)` is an expression on a column; a regular index on `created_at` may not directly accelerate day-level deduplication the way an index on the date expression would. If this query is critical and runs frequently, consider a generated column storing the date or a functional index on the expression where supported by your version.

When combining `DISTINCT` with `ORDER BY`, ensure the sort order is determined by the selected values. MySQL may reject certain `SELECT DISTINCT` queries where `ORDER BY` references an expression not in the select list, because sort order is undefined once duplicate rows are collapsed. Include the sort expression in the select list or structure the query with a derived table to make the rule explicit.

## 10. Ways to Optimize DISTINCT Queries

Start by verifying whether the query truly needs deduplication. If it does, apply the following approaches:

1. **Select only required columns.** Avoid `SELECT DISTINCT *` when you only need a list of IDs or statuses. Wide columns increase the cost of storing and comparing intermediate rows.
2. **Create indexes aligned with filters and distinct keys.** Consider a composite index ordered with equality filter columns first, followed by the columns being deduplicated.
3. **Leverage the leftmost prefix.** Ensure the `DISTINCT` columns can be read in index order, not sitting behind an unconstrained leading index column.
4. **Use covering indexes when appropriate.** If an index covers both filter columns and returned columns, extra clustered index lookups can be avoided.
5. **Replace JOIN with EXISTS when only checking existence.** This eliminates the need to generate and then discard duplicate rows caused by one-to-many relationships.
6. **Apply selective filter predicates.** Reduce the input row count before performing duplicate elimination.
7. **Avoid wrapping columns in arbitrary functions.** If `DISTINCT` on an expression runs frequently, evaluate a pre-normalized column or functional index.
8. **Measure actual plans and metrics.** Use `EXPLAIN`, `EXPLAIN ANALYZE`, Performance Schema, and production-like datasets.

Indexes increase write overhead and storage size. Before adding an index, check existing indexes, `INSERT`/`UPDATE`/`DELETE` workloads, and whether one composite index can serve multiple queries.

## 11. Workflow for Analyzing a Slow DISTINCT Query

When a deduplication query is slow, follow this sequence:

1. **Confirm the required output.** Do you need a list of unique columns, unique combinations, a unique count, or just an existence check?
2. **Confirm equality semantics.** Check `NULL` handling, collation, expressions, and data types.
3. **Estimate input scale.** Estimate how many rows satisfy `WHERE` before deduplication and how many distinct values are expected.
4. **Inspect JOINs.** Check whether a one-to-many relationship or faulty `JOIN` condition is multiplying rows.
5. **Review indexes.** Inspect existing indexes, column order, and leftmost prefix alignment.
6. **Run EXPLAIN.** Check `key`, access `type`, `rows`, temporary tables, filesort, and Loose Index Scan indicators.
7. **Measure in practice.** Run `EXPLAIN ANALYZE` on safe `SELECT` statements with representative data.
8. **Rewrite to match intent.** Use `EXISTS`, `GROUP BY`, `COUNT(DISTINCT)`, or window functions where appropriate.
9. **Evaluate new indexes.** Weigh read gains against write overhead, storage, and maintenance.
10. **Verify results.** Compare row counts, value sets, `NULL`s, collation behavior, and edge cases before and after optimization.

## 12. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using DISTINCT to pick the latest row per group | No deterministic rule for picking a representative row | Use ROW_NUMBER() or a time-ordered deterministic query |
| Using DISTINCT to hide a broken JOIN | Duplicates seem gone while relationship errors remain | Check JOIN conditions, cardinality, and use EXISTS if only checking existence |
| Assuming multi-column DISTINCT deduplicates each column independently | Misunderstood tuple semantics | Define the exact tuple that must be unique |
| Using SELECT DISTINCT * | Compares and stores unnecessary columns | Select only required return columns |
| Assuming LIMIT 10 reads only 10 source rows | May read many rows to find 10 distinct values | Evaluate indexes and duplicate density |
| Using SUM(DISTINCT amount) for total revenue | Separate transactions with the same amount get collapsed | Use SUM(amount) at the transaction level |
| Ignoring collation | Strings differing by case or accents may be merged | Choose collation based on business rules |
| Adding indexes without measuring | Increases write cost and storage usage | Read EXPLAIN and benchmark before/after |

## 13. Key Takeaways

- `DISTINCT` removes duplicate rows based on the entire combination of expressions in the select list.
- Multiple `NULL` values collapse into a single `NULL` row in `DISTINCT` results, even though `NULL = NULL` does not evaluate to `TRUE`.
- Collation determines which string values are considered equivalent; changing collation can alter `DISTINCT` output.
- `DISTINCT` may require reading many rows, temporary tables, sorting, CPU, and I/O; returning few output rows does not guarantee a cheap query.
- Appropriately ordered indexes can assist deduplication; watch for `Using index for group-by` and related clues in `EXPLAIN`.
- Multi-column `DISTINCT` deduplicates by tuple, not per individual column.
- When you only need to check whether related rows exist, `EXISTS` usually expresses intent better than `JOIN` plus `DISTINCT`.
- `COUNT(DISTINCT)` ignores `NULL`; `SUM(DISTINCT)` can be wrong when distinct transactions share the same amount.
- Do not use `DISTINCT` to select the latest row or mask incorrect `JOIN` relationships.
- Optimize by narrowing columns, filtering early, designing suitable indexes, and measuring execution plans on representative data.

Use `DISTINCT` when the true objective is retrieving unique rows or combinations. When you clearly understand deduplication semantics and costs, you can choose the right index or query structure to reduce MySQL resource usage while preserving exact business results.
