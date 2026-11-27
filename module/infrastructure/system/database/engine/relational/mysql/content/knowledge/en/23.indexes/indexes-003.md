# Composite Indexes, Leftmost Prefix, and Column Order

A composite index is an index created on two or more columns. In MySQL, the order of columns in a composite index determines how the B+Tree sorts keys and which query conditions can leverage the index. Index `(tenant_id, status, created_at)` is not equivalent to `(status, tenant_id, created_at)`, even though both contain the same three columns.

The most important rule is the **leftmost prefix**: MySQL typically exploits a composite index effectively starting from the leftmost column and continuing sequentially across subsequent columns. When designing an index, start from the actual query shape, identify equality-filter columns, range-filter columns, sorting or grouping columns, and then choose an appropriate column order.

## 1. How is a composite index sorted?

Suppose you have an orders table:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id)
) ENGINE = InnoDB;
```

Create a composite index:

```sql
CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at);
```

Index entries are sorted in lexicographical order:

1. Compare `tenant_id` first.
2. If `tenant_id` is equal, compare `status`.
3. If both leading columns are equal, compare `created_at`.

Illustrative key order example:

| tenant_id | status | created_at |
|---:|---|---|
| 10 | CANCELLED | 2026-01-02 09:00:00 |
| 10 | PAID | 2026-01-01 10:00:00 |
| 10 | PAID | 2026-01-03 08:00:00 |
| 10 | PENDING | 2026-01-02 12:00:00 |
| 20 | PAID | 2026-01-01 11:00:00 |

This ordering allows locating a tenant, narrowing further by status, and then scanning chronologically within that tenant and status group. The index is not sorted independently per column; trailing columns only have meaningful order within groups formed by preceding columns.

## 2. The leftmost prefix rule

Given the index:

```sql
INDEX (tenant_id, status, created_at)
```

The leftmost prefixes that can be used to locate key ranges are:

- `(tenant_id)`
- `(tenant_id, status)`
- `(tenant_id, status, created_at)`

Examples of matching queries:

```sql
-- Uses leading tenant_id
SELECT order_id, status
FROM orders
WHERE tenant_id = 10;

-- Uses tenant_id and status
SELECT order_id, created_at
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID';

-- Uses all three columns to filter
SELECT order_id, total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
  AND created_at >= '2026-01-01 00:00:00';
```

A query filtering only on `status` typically cannot locate a contiguous range efficiently with this index because there is no leading `tenant_id` value:

```sql
SELECT order_id
FROM orders
WHERE status = 'PAID';
```

Similarly, a condition solely on `created_at` does not start at the leftmost column. The optimizer may consider other strategies, such as another index, a table scan, or under certain specific conditions a skip scan. You should not design critical queries assuming MySQL will always be able to skip missing leading columns.

That does not mean a composite index serves only a single SQL statement. Index `(tenant_id, status, created_at)` can serve queries by `tenant_id`, by the pair `tenant_id + status`, or by all three columns. This is the benefit of the leftmost prefix when sharing an index across multiple queries that share leading columns.

## 3. Column order: equality first, range after

In many queries, a useful design guideline is to place columns with equality conditions before columns with range conditions, and then consider sorting or grouping columns.

Example:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
  AND created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00'
ORDER BY created_at;
```

Index `(tenant_id, status, created_at)` fits well because MySQL can fix the first two columns using equality conditions, then scan a `created_at` range within that group.

If the index were changed to `(created_at, tenant_id, status)`, the range condition on `created_at` appears on the first column. Subsequent columns may still be evaluated in the index or via Index Condition Pushdown depending on the plan, but they generally cannot continue narrowing a single contiguous range after the first range predicate in the same way.

This guideline is a starting point, not a rigid formula for every index. If queries primarily search by `created_at` system-wide, an index starting with `created_at` may make sense. If another query frequently filters by `status` alone, a separate index might be needed. Design around your workload rather than ordering columns solely by a generic rule like selectivity.

### Equality can involve multiple values

An `IN` condition can produce multiple equality ranges for a column:

```sql
SELECT order_id, created_at
FROM orders
WHERE tenant_id = 10
  AND status IN ('PAID', 'PENDING')
  AND created_at >= '2026-01-01';
```

The optimizer can perform multiple probes or range scans matching the `status` values. Actual cost depends on the number of values in `IN`, statistics, and data. When `IN` contains very many values, inspect the plan and execution time rather than assuming it behaves identically to a single equality.

## 4. How composite indexes support ORDER BY

An index can allow MySQL to return results in sorted order without an extra sort step, provided the query's sort order matches the index order and preceding columns are appropriately fixed.

With index `(tenant_id, status, created_at)`, the following query can read in `created_at` order within one tenant and one status:

```sql
SELECT order_id, created_at
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 20;
```

The first two columns have fixed values; the remainder of the index is sorted by `created_at`. MySQL can traverse the index backward to satisfy descending order when the structure and plan permit.

If you omit the `tenant_id` or `status` condition, the index does not naturally produce a global order by `created_at` alone because rows are grouped by the preceding columns. MySQL may have to perform a filesort or choose another plan.

For mixed multi-column sort orders, such as `ORDER BY created_at DESC, order_id ASC`, pay attention to the sort direction of each index key part. MySQL 8.0 supports descending index key parts; creating an index with matching directions can be useful for queries with mixed sort orders:

```sql
CREATE INDEX idx_orders_tenant_created_order
ON orders (tenant_id, created_at DESC, order_id ASC);
```

Not every `ORDER BY` can be satisfied by an index. Expressions on columns, collation differences, incompatible column ordering, or unfixed leading columns can force MySQL to perform an extra sort. Check `Using filesort` in `EXPLAIN` to see whether the plan includes a filesort step; this term does not necessarily mean data is definitely written to disk.

## 5. Composite indexes and GROUP BY

An index can also help grouping queries if column order aligns with filtering predicates and grouping columns:

```sql
SELECT status, COUNT(*) AS order_count
FROM orders
WHERE tenant_id = 10
GROUP BY status;
```

Index `(tenant_id, status, created_at)` puts `tenant_id` first and `status` next, matching filtering by tenant and grouping by status. However, MySQL has multiple execution strategies for `GROUP BY`; the optimizer may pick another approach depending on cardinality, statistics, and data volume to read.

If a query groups by `status` across all tenants, an index starting with `tenant_id` will not establish a global order by `status`. An index starting with `status` might suit that workload better, at the cost of higher write overhead and storage. Compare real queries before adding an index.

## 6. Covering indexes and Index Condition Pushdown

These two mechanisms are often discussed when analyzing composite indexes, yet they solve two different problems.

### Covering index

An index is covering for a query when it contains all columns required for filtering and returning results. For example, with index `(tenant_id, status, created_at)` created in section 1:

```sql
SELECT tenant_id, status, created_at
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID';
```

The query needs only columns present in the index. In InnoDB, secondary indexes also carry the primary key, so a query also selecting `order_id` can likewise be covered by this index.

### Index Condition Pushdown (ICP)

ICP allows the storage engine to evaluate certain predicates directly on secondary index entries before reading the full row from the clustered index. This can reduce row lookups, though it does not turn a query into a covering index if the query still needs columns outside the index.

For example, create an additional index `(tenant_id, created_at, status)`. The `status` column sits after the range column `created_at`, so it can be checked via ICP before reading the full row:

```sql
CREATE INDEX idx_orders_tenant_created_status
ON orders (tenant_id, created_at, status);

SELECT order_id, total_amount
FROM orders
WHERE tenant_id = 10
  AND created_at >= '2026-01-01'
  AND status = 'PAID';
```

The index can use `tenant_id` and the `created_at` range to locate the span, then check `status` directly on index entries before looking up the clustered index. Because `total_amount` is not in the index, the query still needs to read the full row for entries passing the condition. Watch for `Using index condition` in `EXPLAIN` when ICP is applied.

## 7. Composite index vs. multiple single-column indexes

Suppose an application frequently runs:

```sql
SELECT order_id, created_at
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID';
```

Two separate single-column indexes:

```sql
CREATE INDEX idx_orders_tenant ON orders (tenant_id);
CREATE INDEX idx_orders_status ON orders (status);
```

are not equivalent to one composite index:

```sql
CREATE INDEX idx_orders_tenant_status
ON orders (tenant_id, status);
```

With a composite index, MySQL can directly locate the group matching both `tenant_id` and `status` in the order of a single B+Tree. With two single-column indexes, the optimizer may pick one index, use Index Merge, or choose a table scan depending on cost estimates. Index Merge is not always as cheap as a well-ordered composite index.

However, two single-column indexes can serve independent queries such as finding all orders for a tenant or all orders by status. Composite index `(tenant_id, status)` supports queries by `tenant_id` and by the pair well, but is not a leftmost-prefix choice for queries filtering solely on `status`.

Consider:

- Frequently occurring `WHERE`, `JOIN`, `ORDER BY`, and `GROUP BY` patterns.
- Number of rows to read and condition selectivity.
- Whether an index can be shared across multiple queries.
- Additional `INSERT`, `UPDATE`, `DELETE` overhead and storage space.

## 8. Choosing column order in practice

Do not mechanically apply the rule "the highest-selectivity column always goes first." Index order must serve the queries you need to optimize and leftmost-prefix reuse.

A practical process:

1. Gather important queries and their execution frequency.
2. Record columns filtered by equality, filtered by range, used in joins, sorted, and grouped.
3. Identify queries sharing leading columns so they can share an index.
4. Try placing commonly fixed equality columns first and range columns after; adjust if other queries require a different order.
5. Consider adding columns to support `ORDER BY` or create a covering index when read savings outweigh costs.
6. Verify with `EXPLAIN` or `EXPLAIN ANALYZE`, measure on representative data, and monitor after deployment.

Example of two queries with different shapes:

```sql
-- Query A: fixed tenant and status, scanning by time
SELECT order_id, created_at
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;

-- Query B: searching by customer and time
SELECT order_id, created_at
FROM orders
WHERE customer_id = 2001
  AND created_at >= '2026-01-01'
ORDER BY created_at DESC;
```

A suitable index for A might be `(tenant_id, status, created_at)`, whereas B might need `(customer_id, created_at)`. A single index will not necessarily optimize both. Create the second index only if Query B's frequency and cost justify the write and storage overhead.

## 9. Verifying with EXPLAIN

After creating an index, verify the execution plan rather than merely confirming the index exists:

```sql
EXPLAIN
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
  AND created_at >= '2026-01-01'
ORDER BY created_at DESC
LIMIT 20;
```

Fields commonly worth checking:

- `key`: the index chosen by the optimizer.
- `key_len`: the length of the key prefix used; interpret according to data types, nullability, and key parts utilized.
- `type`: access type such as `ref`, `range`, or `ALL`.
- `rows` and `filtered`: estimated rows and percentage of rows remaining after filtering.
- `Extra`: may show `Using index` (covering), `Using index condition` (ICP), or `Using filesort`.

MySQL 8.0.18 and later supports `EXPLAIN ANALYZE`, which executes the query and reports actual timings and row counts across iterators:

```sql
EXPLAIN ANALYZE
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
  AND created_at >= '2026-01-01'
ORDER BY created_at DESC
LIMIT 20;
```

`EXPLAIN ANALYZE` actually executes the analyzed `SELECT` statement and reports real timings and row counts. Only run it with read queries you can safely execute; in production, account for the extra load generated by the query itself. Compare estimated rows with actual rows to spot skewed statistics or wrong data assumptions.

## 10. Common mistakes

**Changing column order arbitrarily.** `(a, b)` and `(b, a)` have different usability profiles. Determine leading columns based on actual query patterns.

**Checking only that the index exists.** An index existing does not mean the optimizer chooses it. Check `key`, `rows`, `Extra`, and execution time.

**Assuming trailing columns always narrow a range.** Once a range condition is encountered on a column, subsequent columns may still be checked in the index but generally do not continue narrowing the scan range the way an equality prefix does.

**Creating multiple single-column indexes instead of a needed composite index.** The optimizer may use Index Merge, which is not guaranteed to be as efficient as a properly ordered composite index.

**Creating overly wide composite indexes.** Wide indexes increase storage size and write maintenance work. Only add covering columns when read gains have been measured.

**Confusing leftmost prefix with a string prefix index.** Leftmost prefix refers to the leading columns of a composite index. A prefix index like `INDEX(name(20))` stores only the leading characters of a string column; that is a different concept.

## 11. Self-check

1. In what order is index `(tenant_id, status, created_at)` sorted?
2. Why can a query with only `status = 'PAID'` typically not leverage the index above effectively?
3. Why are equality conditions usually placed before range columns?
4. When can a composite index support `ORDER BY created_at` without a filesort?
5. How does a covering index differ from Index Condition Pushdown?
6. How does composite index `(tenant_id, status)` differ from two single-column indexes?
7. Why can you not always pick the highest-cardinality column as the leading column?
8. What information in `EXPLAIN` should you inspect to evaluate a newly created index?
