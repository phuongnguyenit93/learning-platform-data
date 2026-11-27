# Index Range Scan, Ref Lookup, and Full Index Scan

When MySQL executes a query, the optimizer selects a data access path based on filter conditions, column order in indexes, statistics, and estimated cost. A query may enter a B-tree at a starting position and read a range of keys, locate rows by equality comparison on a non-unique index, or read every entry of an index. These three methods are commonly represented in `EXPLAIN` by the corresponding access types `range`, `ref`, and `index`.

Understanding the difference between an **index range scan**, a **ref lookup**, and a **full index scan** makes reading execution plans much more accurate. In particular, do not confuse access type `index` with `Extra` `Using index`: one describes how the index is accessed, while the other describes whether the query can obtain all needed columns from the index.

In the `DATABASE_MYSQL` module, this lesson focuses on how B-trees serve these three access types, conditions for using composite indexes, reading `EXPLAIN`, and verifying actual row counts.

## 1. InnoDB indexes and B-tree structure

Common InnoDB indexes are organized as B-tree/B+tree structures. Nodes in the structure store keys in sorted order, allowing MySQL to find a starting position faster than scanning every row.

In this lesson's example, the `orders` table has a composite index starting with `customer_id`. A single-column index on `customer_id` can also serve lookups on that column, yet if an existing composite index already satisfies the query, there is no need to create a duplicate-prefix index.

MySQL can:

- Locate a specific `customer_id` value.
- Locate a range of `customer_id` values from low to high.
- Read all entries in index order.

An index speeds up access when query conditions match the key structure. It also carries costs: extra disk space, `INSERT`/`UPDATE`/`DELETE` maintenance overhead, and potentially increased random writes. Therefore, select indexes based on real queries rather than indexing every column.

## 2. Three access types to distinguish

In tabular `EXPLAIN`, the `type` column indicates the access method chosen by the optimizer for each table reference.

| Access type | How it accesses | Common scenarios |
|---|---|---|
| `range` | Reads one or more key intervals in an index | `BETWEEN`, greater/less comparisons, prefix `LIKE`, some `IN` predicates |
| `ref` | Finds entries with a key value equal to a reference value, usually via a non-unique index | Column compared for equality against a literal or a column from a preceding table |
| `index` | Scans the entire index in index order | No bounding predicate, yet the index can satisfy query columns or sort order |

These access types differ in how much they read:

- `range` restricts reading to defined key intervals.
- `ref` locates by equality and can return multiple rows sharing the same value.
- `index` reads every entry of an index, though it does not necessarily read every row in the clustered table.

The optimizer does not pick an access type from SQL syntax alone. Data volume, selectivity, available indexes, column order, and statistics all influence the decision.

## 3. Index range scan: reading a key interval

A range scan is used when `WHERE` conditions define one or more intervals on an index. For example, the `orders` table has an index on `customer_id` and `created_at`:

~~~sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer_created (
        customer_id,
        created_at
    )
) ENGINE=InnoDB;
~~~

Query fetching orders for a customer within a time window:

~~~sql
SELECT order_id, customer_id, created_at
FROM orders
WHERE customer_id = 42
  AND created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00';
~~~

With index `(customer_id, created_at)`, MySQL can seek to the `customer_id = 42` key section and then read the `created_at` interval from the start of January until before the start of February. In `EXPLAIN`, the access type can typically be `range` because the conditions form an interval on the index.

The equality condition on the leading column narrows the scope; the range condition on the next column defines the span to read. This is a query pattern well suited to a composite index.

### Forms of conditions that can produce a range

Common examples:

~~~sql
-- Numeric range
WHERE order_id BETWEEN 1000 AND 1999

-- Inequality comparison
WHERE created_at >= '2026-01-01'

-- Several discrete values
WHERE status IN ('PAID', 'SHIPPED')

-- String prefix search
WHERE customer_code LIKE 'CUS-2026%'
~~~

Range eligibility depends on data type, collation, index, and the specific expression. An `IN` list may be converted into multiple key intervals; the optimizer may merge or handle them via another plan.

### Why is a range scan usually better than a full scan?

When a condition matches only a small portion of data, reading a narrow index interval is generally cheaper than reading the whole table. However, `range` is not always fast: if a condition matches most of the table, the optimizer may choose a table scan or index scan because random access across many rows costs more.

## 4. Ref lookup: searching by equality on a non-unique index

Access type `ref` typically appears when MySQL uses a non-unique index to find rows whose key value equals a reference value.

In the `orders` table from the previous section, `idx_orders_customer_created` is a non-unique index with `customer_id` in the leading position. One customer can have multiple orders, so many entries can share the same `customer_id` value.

Query:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42;
~~~

A customer can have multiple orders, so `customer_id` is not unique. MySQL locates the key region with value `42` in the index and reads all matching entries. In `EXPLAIN`, the access type can be `ref`.

A `ref` lookup does not mean reading exactly one row. Because the index is non-unique, one value can map to many rows. The estimated row count in the `rows` column helps gauge how many entries or rows the optimizer expects to process.

### Ref in JOINs

`ref` frequently appears when a table is accessed using a value from a preceding table in the join order:

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    o.order_id,
    o.created_at
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE c.customer_id = 42;
~~~

If the optimizer reads `customers` first and uses `customer_id` to probe `orders`'s index, the `orders` table can use a `ref` lookup on `idx_orders_customer_created`. In joins, this is how related rows are located from the current row of the preceding table.

### Distinguishing ref and eq_ref

If a join condition looks up by `PRIMARY KEY` or `UNIQUE NOT NULL` and each preceding row matches at most one row, `EXPLAIN` may show `eq_ref` instead of `ref`.

| Access type | Characteristics |
|---|---|
| `ref` | Lookup via a non-unique index or a unique key that can contain `NULL` in an applicable context; may match multiple rows |
| `eq_ref` | Lookup via `PRIMARY KEY` or `UNIQUE NOT NULL` for each row combination from preceding tables; at most one matching row |

Do not call every equality lookup `ref`. Read `type` in `EXPLAIN` to distinguish `ref`, `eq_ref`, `const`, and other types.

## 5. Full index scan: reading every entry of an index

A full index scan is typically shown as `type = index`. MySQL reads every entry in an index in key order rather than seeking to one value or a small interval.

For example, given an index on `customer_id`:

~~~sql
SELECT customer_id
FROM orders
ORDER BY customer_id;
~~~

The optimizer may choose to read all of `idx_orders_customer_created` because the index already contains `customer_id` and provides the required order. If the index satisfies all query columns, MySQL may avoid accessing clustered records for each row.

A full index scan still reads every entry of the index. It is not a small lookup just because the word `index` appears in the access type. Still, if the index is narrower than full rows and the query needs only columns inside the index, reading the entire index can require less I/O than scanning the entire clustered table.

### Full index scan is not the same as full table scan

| Read method | Typical EXPLAIN type | Data read |
|---|---|---|
| Full table scan | `ALL` | Scans rows of the table/clustered index |
| Full index scan | `index` | Scans all entries of a secondary index or selected index |
| Index range scan | `range` | Scans one or more entry intervals |
| Ref lookup | `ref` | Looks up entries matching a reference value |

In InnoDB, the `PRIMARY KEY` is the clustered index. Scanning the entire clustered index is essentially reading all rows of the table; `EXPLAIN` may represent this as a table scan. Secondary indexes are typically smaller because they contain only the secondary key and primary key to locate rows.

## 6. Distinguishing type = index from Extra = Using index

This is one of the easiest points to confuse when reading `EXPLAIN`.

- `type = index` means the access method is scanning the entire index.
- `Extra = Using index` means the query is satisfied using data in the index (covering index), without needing to read additional columns from clustered records for that query.

`Using index` can appear alongside different access types such as `range`, `ref`, or `index`. It is not synonymous with a full index scan.

Covering lookup example:

~~~sql
SELECT customer_id
FROM orders
WHERE customer_id = 42;
~~~

If index `idx_orders_customer_created` is used, the query can use `ref` and `Extra` may show `Using index` because the returned column is already in the index.

Full covering index scan example:

~~~sql
SELECT customer_id
FROM orders
ORDER BY customer_id;
~~~

This query can use `type = index` and `Extra = Using index` because it reads every entry of the index while needing no additional columns from clustered records.

Therefore, read `type`, `key`, `rows`, and `Extra` together. Looking only at the words `Using index` and concluding the query performs a range lookup is incorrect.

## 7. Composite indexes and the leftmost prefix rule

A composite index contains multiple columns in their declared order:

~~~sql
CREATE INDEX idx_orders_customer_created_status
    ON orders (customer_id, created_at, status);
~~~

Column order matters. The B-tree is sorted by `customer_id` first, within the same `customer_id` sorted by `created_at`, and then `status`.

This index typically supports:

- Conditions on `customer_id`.
- Conditions on `customer_id` and `created_at`.
- Conditions on `customer_id`, `created_at`, and `status`.

It is usually ineffective for lookups solely on `status`, because `status` is not the leading column. Similarly, conditions solely on `created_at` do not leverage the first prefix directly the way queries on `customer_id` do.

Example:

~~~sql
-- Can use prefix customer_id
WHERE customer_id = 42

-- Can use prefix customer_id and range on created_at
WHERE customer_id = 42
  AND created_at >= '2026-01-01'

-- Column status after a range on created_at typically does not continue narrowing the range like a new equality prefix
WHERE customer_id = 42
  AND created_at >= '2026-01-01'
  AND status = 'PAID'
~~~

The optimizer can still use `status` for further filtering via Index Condition Pushdown or post-read filtering, depending on the plan. However, `status` appearing in the index does not mean it is always used to bound the range.

## 8. Which conditions prevent using an index range?

A condition can be difficult to evaluate as a range if the expression is not sargable or data types are incompatible.

Example wrapping a column in a function:

~~~sql
-- May not use a range on created_at
WHERE DATE(created_at) = '2026-01-15'
~~~

Rewrite as a half-open interval:

~~~sql
WHERE created_at >= '2026-01-15 00:00:00'
  AND created_at <  '2026-01-16 00:00:00'
~~~

Example string search with a leading wildcard:

~~~sql
-- A B-tree generally cannot locate a prefix when the wildcard is at the start
WHERE customer_code LIKE '%2026'
~~~

Whereas `LIKE` with a fixed prefix can use a range:

~~~sql
WHERE customer_code LIKE 'CUS-2026%'
~~~

Implicit type conversion can also hinder index usage, especially when column and literal have different types or collations. Bind parameters using the type matching the column and avoid `CAST` on indexed columns unless necessary.

## 9. Range scans and ORDER BY order

An index can both filter and supply order, depending on index structure and how columns are constrained.

With index `(customer_id, created_at)`:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC;
~~~

Because `customer_id` is fixed by equality, rows within that customer's slice are ordered by `created_at`. MySQL can read the index in the appropriate direction to return ordered results, depending on version and index direction.

If the query filters a `created_at` range and then `ORDER BY status`, an index on `(customer_id, created_at, status)` does not necessarily satisfy a global `status` order. After a range on a middle column, trailing columns typically do not provide the desired global sort order.

If `EXPLAIN` shows `Extra = Using filesort`, MySQL requires an extra sorting step. `Filesort` is the name of MySQL's sorting algorithm; it does not definitely imply data is always written to disk.

## 10. Reading EXPLAIN to recognize access types

Run tabular `EXPLAIN`:

~~~sql
EXPLAIN
SELECT order_id, customer_id, created_at
FROM orders
WHERE customer_id = 42
  AND created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00';
~~~

Columns to pay attention to:

| Column | Meaning |
|---|---|
| `type` | Access type, e.g., `range`, `ref`, `index`, or `ALL` |
| `possible_keys` | Indexes the optimizer considers as candidates |
| `key` | Index actually selected |
| `key_len` | Length of the key portion used in the access condition; depends on type, `NULL`, and charset |
| `ref` | Value or column compared against the key |
| `rows` | Estimated number of rows to read |
| `filtered` | Estimated percentage of rows remaining after additional filter conditions |
| `Extra` | Additional info such as `Using index`, `Using index condition`, `Using where`, or `Using filesort` |

Do not judge a query solely by the single word `type`. A range scan can read millions of entries if the interval is too wide; a full index scan can be very cheap if the index is small and covering; a `ref` lookup can return very many rows if the value has low selectivity.

### Meaning of key_len

`key_len` indicates the length of the key portion the optimizer uses in the access condition. For composite indexes, this value helps check how far into the leading index parts are utilized. However, you cannot mechanically deduce column count just by dividing `key_len` by declared lengths: data types, nullable flags, charset, and prefix lengths all affect it.

### Extra Using index condition

`Using index condition` typically represents Index Condition Pushdown (ICP): part of the predicate is evaluated directly on index entries before reading clustered records. ICP can reduce row accesses, but differs from a covering index:

- `Using index`: query data is fully satisfied from the index.
- `Using index condition`: the index helps evaluate predicates early, yet reading full rows may still be needed to fetch other columns.

## 11. EXPLAIN FORMAT=TREE and EXPLAIN ANALYZE

In MySQL 8.0, `FORMAT=TREE` can be used to view the operator tree:

~~~sql
EXPLAIN FORMAT=TREE
SELECT order_id, customer_id, created_at
FROM orders
WHERE customer_id = 42
  AND created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00';
~~~

In tree output, operations may be phrased more descriptively as `Index range scan`, `Index lookup`, or `Covering index scan`. Descriptive names in the tree do not always match tabular `EXPLAIN` access type labels verbatim; understand the underlying operation.

In MySQL 8.0.18 and later, `EXPLAIN ANALYZE` executes the query and adds actual row counts, loop counts, and timings per iterator:

~~~sql
EXPLAIN ANALYZE
SELECT order_id, customer_id, created_at
FROM orders
WHERE customer_id = 42
  AND created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00';
~~~

`EXPLAIN ANALYZE` runs the actual `SELECT` statement. Use it on test data or after evaluating load and impact; do not treat it as a plan-only read command.

Compare estimated rows with actual rows:

- If actual rows are much larger, statistics or selectivity assumptions may be wrong.
- If a range scan reads many rows only to discard nearly all of them, revisit the index and predicates.
- If a full index scan reads few bytes and avoids table accesses, it may be a good plan.
- If a `ref` lookup repeats many times inside a nested loop, the total number of lookups can be large even when each individual lookup is fast.

## 12. Practice comparing the three access types

Using the `orders` table from the beginning. Index `idx_orders_customer_created` already has `customer_id` first, so it can support both lookups by `customer_id` and ranges on `created_at`. There is no need to create an additional index containing only `customer_id` if the composite index already serves the workload; duplicate-prefix indexes increase storage and write costs.

### Test A: ref lookup

~~~sql
EXPLAIN
SELECT order_id, customer_id
FROM orders
WHERE customer_id = 42;
~~~

The non-unique composite index allows multiple orders to share the same `customer_id`. The optimizer may select `type = ref`. Because InnoDB stores the primary key inside secondary indexes, the index can satisfy both `order_id` and `customer_id`; `Extra` may display `Using index`.

### Test B: range scan

~~~sql
EXPLAIN
SELECT order_id, customer_id, created_at
FROM orders
WHERE customer_id = 42
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01';
~~~

The optimizer can use `range` on composite index `idx_orders_customer_created`. If another index is chosen, check `key` and `key_len` to understand the decision.

### Test C: full index scan

~~~sql
EXPLAIN
SELECT customer_id
FROM orders
ORDER BY customer_id;
~~~

Because there is no `WHERE` clause limiting the scope, the optimizer may read all of `idx_orders_customer_created` in `customer_id` order. Access type may be `index` and `Extra` may contain `Using index`. If the table is small or the optimizer sees a table scan as cheaper, the plan may differ; that does not mean the example is wrong.

`EXPLAIN` results can vary depending on table size, data, statistics, MySQL version, and configuration. Inspect actual plans in your environment rather than expecting a fixed `type`.

## 13. When does the optimizer choose ALL instead of an index?

Having an index does not force the optimizer to use it. Reasons for choosing `ALL` include:

- The filter condition returns most of the rows.
- The table is very small, making sequential scanning cheaper than index lookups followed by clustered record reads.
- The index does not fit the columns or expressions in `WHERE`.
- Cardinality or distribution statistics cause the optimizer to estimate no benefit from the index.
- The query needs many columns absent from the secondary index, making random lookups expensive.

Do not force an index just to make `ALL` disappear from `EXPLAIN`. Compare actual execution time, rows read, and I/O. `FORCE INDEX` should only be used after measuring, understanding why the optimizer chose poorly, and establishing a plan to monitor as data evolves.

## 14. Choosing indexes by query rather than access type label

Several design principles:

1. Place commonly used equality columns at the front of a composite index if query patterns fit.
2. Place range columns after equality prefix columns when queries commonly filter by both.
3. Add returned columns to an index only when covering benefits justify storage and write costs.
4. Check `JOIN` queries to identify indexes on join columns of the inner/lookup table.
5. Evaluate cardinality and data distribution; columns with few distinct values may have low selectivity.
6. Avoid creating duplicate indexes or indexes unused by the workload.
7. Measure both `SELECT` and `INSERT`/`UPDATE`/`DELETE` after adding an index.

There is no rigid rule that the highest-cardinality column must always go first. Equality, range, sorting, joins, prefixes, and overall workload together determine column order.

## 15. Execution plan reading checklist

When inspecting `EXPLAIN`, follow this sequence:

1. Identify which table reference is being read and the join order.
2. Read `type` to see whether the optimizer picked `range`, `ref`, `index`, or `ALL`.
3. Check `key` and `possible_keys` to see which indexes were selected or ignored.
4. Read `key_len` and `ref` to understand how much of the index is actually used.
5. Compare `rows` and `filtered` against expected data scale.
6. Read `Extra`: `Using index`, `Using index condition`, `Using where`, `Using filesort`.
7. Verify whether composite indexes are used according to the leftmost prefix.
8. Use `EXPLAIN ANALYZE` to compare estimated rows with actual rows where appropriate.
9. Evaluate total lookups in joins, not just the cost of a single lookup.
10. Measure both read gains and write costs after changing indexes.

## 16. Practice exercises

1. Create the `orders` table and index `(customer_id, created_at)` as shown in the example.
2. Run `EXPLAIN` for `customer_id = 42`; identify when the optimizer uses `ref`.
3. Add a range condition on `created_at`; observe when the access type switches to `range`.
4. Run `SELECT customer_id ORDER BY customer_id`; observe a full index scan and `Extra` `Using index` if the optimizer chooses the index.
5. Try `SELECT *` without `WHERE`; compare `type ALL` against `type index`.
6. Create composite index `(status, customer_id, created_at)`, then compare queries by `status`, by `customer_id`, and by both.
7. Rewrite `DATE(created_at) = ...` into a time interval; compare the plans.
8. Compare `LIKE 'CUS-2026%'` against `LIKE '%2026'` on an indexed column.
9. Use `EXPLAIN FORMAT=TREE` and `EXPLAIN ANALYZE` to compare estimated plans with actual row counts.
10. Add a column to a covering index, measuring `SELECT` impact and write cost before/after.

You have completed this lesson when you can explain how range scans read key intervals, how `ref` lookups search by equality on an index, and how full index scans read all entries—while distinguishing `type = index` from `Extra Using index`. Use `EXPLAIN` together with real metrics to evaluate plans, rather than treating any access type as universally good or bad in all situations.
