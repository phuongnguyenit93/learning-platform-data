# Index Merge and Trade-Offs Against Composite Indexes

When a query filters on multiple columns, MySQL can read multiple separate indexes and merge the matching rows, or read a single composite index containing multiple columns in the same B-tree. The first strategy is called Index Merge; the second uses a composite index.

Index Merge helps leverage existing single-column indexes, especially for certain `AND` or `OR` conditions. Composite indexes typically provide a more direct access path when the workload repeats a stable multi-column filtering pattern. Neither choice is universally better: the decision depends on `WHERE` predicates, column order, selectivity, `ORDER BY`, `LIMIT`, actual row counts, index size, and write cost.

This lesson falls within the scope of `DATABASE_MYSQL`: reading execution plans, understanding how the optimizer merges multiple indexes, designing composite indexes with leftmost-prefix ordering, measuring performance with `EXPLAIN`, and balancing read speed against `INSERT`, `UPDATE`, and `DELETE` costs.

## 1. What is Index Merge?

Index Merge is a MySQL access method. For a single table, the optimizer can perform multiple range scans on different indexes and combine the discovered row IDs into one result set.

There are three primary algorithms:

- **Intersection**: takes the intersection of row ID sets, typically suited for `AND` conditions.
- **Union**: takes the union of row ID sets, typically suited for `OR` conditions.
- **Sort-Union**: collects row IDs from range scans, sorts them, and deduplicates them to produce a union.

Index Merge does not create a new index, nor does it physically join two B-trees into a persistent storage structure. It is an execution strategy for a query. The component indexes remain separate indexes on the table.

Index Merge only combines range scans of the **same table** within a query block. It does not merge indexes across multiple tables in a `JOIN` into one combined index.

### 1.1. Conceptual example

Suppose a `ticket` table has two separate indexes:

- `idx_ticket_customer` on `customer_id`.
- `idx_ticket_status` on `status`.

With the condition:

~~~sql
SELECT ticket_id, customer_id, status
FROM ticket
WHERE customer_id = 42
  AND status = 'OPEN';
~~~

The optimizer can:
1. Read `idx_ticket_customer` to get tickets with `customer_id = 42`.
2. Read `idx_ticket_status` to get tickets with `status = 'OPEN'`.
3. Compute the intersection between the two row ID sets.
4. Fetch the rows to return.

That is Index Merge intersection if the optimizer chooses this strategy.

An `OR` query:

~~~sql
SELECT ticket_id, customer_id, status
FROM ticket
WHERE customer_id = 42
   OR status = 'OPEN';
~~~

Can use Index Merge union:
1. Get row IDs from the `customer` index.
2. Get row IDs from the `status` index.
3. Union the two sets and eliminate duplicate row IDs.
4. Read the corresponding rows.

The optimizer may choose another plan if its cost is lower, such as using only one index or scanning the whole table.

## 2. Preparing a practice table

Create a table with single-column indexes:

~~~sql
CREATE TABLE ticket (
    ticket_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    priority TINYINT UNSIGNED NOT NULL,
    created_at DATETIME(6) NOT NULL,
    title VARCHAR(200) NOT NULL,
    PRIMARY KEY (ticket_id),
    KEY idx_ticket_customer (customer_id),
    KEY idx_ticket_status (status),
    KEY idx_ticket_priority (priority),
    KEY idx_ticket_created (created_at)
) ENGINE = InnoDB;
~~~

Single-column indexes allow the optimizer to consider each predicate independently. To observe Index Merge, you need a sufficiently large dataset with representative value distribution. On a table with only a few rows, a full table scan can be cheaper than multiple range scans; therefore, small examples only illustrate syntax and do not guarantee `EXPLAIN` will choose Index Merge.

Check existing indexes:

~~~sql
SHOW INDEX FROM ticket;
~~~

Check row counts and distribution:

~~~sql
SELECT
    status,
    COUNT(*) AS ticket_count
FROM ticket
GROUP BY status
ORDER BY ticket_count DESC;
~~~

Selectivity indicates how many rows a predicate filters relative to the total row count. A predicate returning most of the table may not warrant using an index because reading the index and then accessing rows can cost more than scanning the table.

## 3. Intersection: merging by set intersection

Index Merge intersection may be considered when `WHERE` contains `AND` conditions, each able to use an index range scan.

Example:

~~~sql
EXPLAIN
SELECT ticket_id, customer_id, status
FROM ticket
WHERE customer_id = 42
  AND status = 'OPEN';
~~~

If the optimizer chooses intersection, traditional `EXPLAIN` typically displays:

- `type = index_merge`.
- `key` lists multiple indexes used.
- `Extra` shows something like `Using intersect(idx_ticket_customer,idx_ticket_status)`.

Index names and formatting may vary by query, version, and `EXPLAIN` format.

### 3.1. How intersection works

Logically:

- Set A: row IDs found from `idx_ticket_customer`.
- Set B: row IDs found from `idx_ticket_status`.
- Result: A ∩ B.

Only rows satisfying both conditions are returned. In InnoDB, secondary indexes store the primary key, so the engine can use the primary key to identify rows during the merge.

Intersection can save reading rows that do not satisfy all conditions, yet it must read multiple indexes and combine row ID sets. If one index is already selective enough, or combining produces many intermediate row IDs, merge cost can exceed the benefit.

### 3.2. When can intersection be useful?

- The table has multiple single-column indexes matching the `AND` predicates.
- Each predicate filters down to a relatively small set of rows.
- No matching composite index exists, or the workload varies across many predicate combinations.
- The optimizer estimates merge cost to be lower than other access paths.

### 3.3. Why composite indexes often win for stable AND patterns

For `customer_id = 42 AND status = 'OPEN'`, you can create:

~~~sql
CREATE INDEX idx_ticket_customer_status
ON ticket (customer_id, status);
~~~

One composite B-tree allows seeking on prefix `customer_id` followed by `status`. Instead of reading two separate indexes and intersecting two row ID sets, MySQL can perform a single range/ref access on the composite index.

This typically reduces merge work and index structure accesses. Still, the optimizer chooses by cost; you cannot assert a composite index always wins if data distribution, table size, or workload differs.

## 4. Union: merging by OR

Index Merge union suits certain `OR` conditions where each branch can use a separate index.

Example:

~~~sql
EXPLAIN
SELECT ticket_id, customer_id, status
FROM ticket
WHERE customer_id = 42
   OR status = 'OPEN';
~~~

If the optimizer chooses union, `Extra` may display:

~~~text
Using union(idx_ticket_customer,idx_ticket_status)
~~~

Logically:

- Set A: row IDs for `customer_id = 42`.
- Set B: row IDs for `status = 'OPEN'`.
- Result: A ∪ B.

A row satisfying both conditions appears only once in the query result. Index Merge union merges row IDs rather than concatenating two potentially overlapping row lists.

### 4.1. Can a composite index solve OR across two different columns?

Composite index:

~~~sql
CREATE INDEX idx_ticket_customer_status
ON ticket (customer_id, status);
~~~

can serve queries by `customer_id`, or `customer_id` combined with `status`. However, it does not have `status` as its leftmost prefix. Thus, a query filtering only `status = 'OPEN'` cannot use this composite index as a direct range lookup by `status`.

With the condition:

~~~sql
WHERE customer_id = 42
   OR status = 'OPEN'
~~~

a composite index `(customer_id, status)` does not automatically replace two single-column indexes. The optimizer may still use Index Merge with single-column indexes, another access path, or a table scan.

This is why workloads with many `OR` conditions across independent columns may still require individual indexes, even when the table already has several composite indexes.

### 4.2. OR on the same column

Not every `OR` requires Index Merge.

~~~sql
SELECT ticket_id
FROM ticket
WHERE status = 'OPEN'
   OR status = 'PENDING';
~~~

Can be written more clearly as:

~~~sql
SELECT ticket_id
FROM ticket
WHERE status IN ('OPEN', 'PENDING');
~~~

The optimizer can typically represent multiple values on the same index as multiple ranges. Inspect `EXPLAIN` before concluding this is Index Merge.

## 5. Sort-Union: union after sorting row IDs

Sort-Union also merges results from multiple range scans, but must collect row IDs and sort them before producing the merged result.

A query having range-style `OR` branches on different columns can be a candidate:

~~~sql
EXPLAIN
SELECT ticket_id, priority, created_at
FROM ticket
WHERE priority BETWEEN 3 AND 5
   OR created_at >= '2025-01-01 00:00:00';
~~~

If the optimizer chooses sort-union, `Extra` may display:

~~~text
Using sort_union(idx_ticket_priority,idx_ticket_created)
~~~

This is a candidate example, not a guarantee MySQL will pick sort-union. Outcome depends on statistics, selectivity, row counts, version, and cost model. A query may use union, sort-union, a single index, or a full scan.

### 5.1. Why can sort-union be expensive?

Sort-Union needs to:
1. Collect row IDs from the range scans.
2. Sort the row IDs.
3. Deduplicate row IDs.
4. Access rows to retrieve output columns.

If each branch returns many rows, the intermediate row ID set can be large. Sorting consumes CPU and memory; in some situations temporary disk storage may occur.

For queries with a small `LIMIT`, sort-union may still have to collect and sort many row IDs before returning enough rows. An access path with matching order can stop early more efficiently.

### 5.2. Do not confuse sort-union with result ORDER BY

Sort-Union sorts row IDs to merge row sets. It does not guarantee results are ordered by `created_at`, `priority`, or business columns required by the application.

For deterministic output order:

~~~sql
SELECT ticket_id, priority, created_at
FROM ticket
WHERE priority BETWEEN 3 AND 5
   OR created_at >= '2025-01-01 00:00:00'
ORDER BY created_at DESC, ticket_id DESC;
~~~

The outermost `ORDER BY` remains the requirement ensuring order. If the access path does not supply the needed order, MySQL may have to use filesort.

## 6. What is a composite index?

A composite index (multi-column index) is an index containing two or more columns. InnoDB stores values according to the declared column order in the B-tree.

Example:

~~~sql
CREATE INDEX idx_ticket_customer_status_created
ON ticket (customer_id, status, created_at);
~~~

Key order is:

1. `customer_id`.
2. `status` within `customer_id`.
3. `created_at` within the `(customer_id, status)` pair.

A composite index can serve multiple query patterns starting with the index's leftmost prefix.

### 6.1. Leftmost-prefix principle

With index:

~~~sql
(customer_id, status, created_at)
~~~

Prefixes typically usable for seeking are:

- `customer_id`.
- `customer_id, status`.
- `customer_id, status, created_at`.

Queries filtering only on `status` or only on `created_at` lack a matching leftmost prefix.

| Filter condition | Usability of the composite index above |
|---|---|
| `customer_id = 42` | Yes, uses leading column |
| `customer_id = 42 AND status = 'OPEN'` | Yes, uses first two columns |
| `customer_id = 42 AND status = 'OPEN' AND created_at >= ...` | Yes, uses prefix and range on date column |
| `status = 'OPEN'` | Cannot locate directly via leftmost prefix |
| `created_at >= ...` | Cannot locate directly via leftmost prefix |
| `status = 'OPEN' AND created_at >= ...` | Lacks `customer_id` prefix, so usually needs another index |

The optimizer may choose to scan the entire index in some situations, which differs from an efficient range lookup via the leftmost prefix. Do not misread the leftmost-prefix rule as saying trailing columns are completely useless: they can still help covering or be leveraged by other optimization mechanisms, though they do not produce a direct lookup like having the leading column.

### 6.2. Equality first, range after

With query:

~~~sql
SELECT ticket_id, created_at
FROM ticket
WHERE customer_id = 42
  AND status = 'OPEN'
  AND created_at >= '2025-01-01 00:00:00'
  AND created_at <  '2025-02-01 00:00:00';
~~~

Index:

~~~sql
(customer_id, status, created_at)
~~~

matches the two leading equality conditions and the trailing date range. MySQL can seek to the exact customer/status group and then read the `created_at` range.

The equality-first, range-after rule is a helpful starting point, not an absolute formula. Also consider `ORDER BY`, `GROUP BY`, other queries sharing the same index, and selectivity.

### 6.3. A range generally limits using trailing columns to narrow scope

With index `(customer_id, created_at, status)`, the query:

~~~sql
WHERE customer_id = 42
  AND created_at >= '2025-01-01'
  AND status = 'OPEN'
~~~

can use `customer_id` and the `created_at` range for positioning. The `status` column after the range generally cannot form a smaller contiguous range the way an equality column before the range can; however, it can still be checked from the index or assist covering/Index Condition Pushdown depending on the plan.

Therefore, if `status` is an equality predicate that always accompanies `customer_id` before a date range, `(customer_id, status, created_at)` is usually a better candidate. Confirm with `EXPLAIN` and real data.

## 7. Comparing Index Merge intersection vs. composite index

Suppose the workload frequently runs:

~~~sql
SELECT ticket_id, created_at
FROM ticket
WHERE customer_id = 42
  AND status = 'OPEN';
~~~

Two approaches:

**Approach A: single-column indexes and Index Merge**

~~~sql
KEY idx_ticket_customer (customer_id),
KEY idx_ticket_status (status)
~~~

The optimizer can read both indexes and intersect row IDs.

**Approach B: composite index**

~~~sql
KEY idx_ticket_customer_status (customer_id, status)
~~~

The optimizer can use a single index range across both conditions.

| Criterion | Index Merge intersection | Composite index |
|---|---|---|
| Storage structure | Multiple single-column indexes | One multi-column B-tree |
| Lookup method | Separate range scans then row ID intersection | One range/ref access on composite prefix |
| Merge cost | Has a row ID combining step | Usually no need to intersect multiple row ID sets |
| Flexibility | Can reuse single-column indexes across many combinations | Depends on column order and leftmost prefix |
| `ORDER BY` | Usually hard to supply required business sort order | Can support order if prefix and sort direction match |
| Covering | Depends on indexes and read columns | Can cover the query with one index |
| Write cost | Maintains each single-column index | Maintains composite index; may replace some single indexes if workload permits |
| Storage | Multiple separate B-trees | One wider B-tree |
| When suitable | Predicates vary, each column needs its own index | Repeated, stable `AND` pattern with clear access order |

A composite index usually wins on stable `AND` queries because it locates rows via a single B-tree structure. Yet if the application also runs many queries filtering solely on `customer_id` or solely on `status`, single-column indexes may still hold independent value.

## 8. Comparing Index Merge union vs. composite index

With an `OR` condition:

~~~sql
WHERE customer_id = 42
   OR status = 'OPEN'
~~~

two single-column indexes can enable Index Merge union.

Composite index `(customer_id, status)` lacks leftmost prefix `status`. It does not directly replace the `status` index for that `OR` branch.

| Query pattern | Suitable index to evaluate |
|---|---|
| `customer_id = ?` | `customer` index or composite starting with `customer_id` |
| `status = ?` | `status` index or composite starting with `status` |
| `customer_id = ? AND status = ?` | Composite `(customer_id, status)` |
| `customer_id = ? OR status = ?` | Two single indexes and Index Merge union; can also test rewrites after verifying semantics |
| `status = ? AND created_at in range` | Composite `(status, created_at)` |
| `customer_id = ? AND status = ? AND created_at in range` | Composite `(customer_id, status, created_at)` |

One composite index cannot optimize every predicate permutation. Column order decides which prefixes are usable. If a workload has two independent query groups, two different composite indexes may be needed, weighed against write cost and disk usage.

## 9. Index Merge and rewriting OR queries with UNION

Some `OR` queries can be rewritten as `UNION` branches to unlock separate access paths. However, do not substitute mechanically because deduplication semantics differ.

Example:

~~~sql
SELECT ticket_id, customer_id, status
FROM ticket
WHERE customer_id = 42
   OR status = 'OPEN';
~~~

Can be written:

~~~sql
SELECT ticket_id, customer_id, status
FROM ticket
WHERE customer_id = 42

UNION

SELECT ticket_id, customer_id, status
FROM ticket
WHERE status = 'OPEN';
~~~

`UNION` removes duplicate rows across all output columns by default. Meanwhile, an `OR` condition in a single `SELECT` returns each table row at most once. With the same projection and same table, `UNION DISTINCT` generally preserves similar row semantics, though deduplication overhead must be accounted for.

If `UNION ALL` is used, a row matching both branches can appear twice:

~~~sql
SELECT ticket_id, customer_id, status
FROM ticket
WHERE customer_id = 42

UNION ALL

SELECT ticket_id, customer_id, status
FROM ticket
WHERE status = 'OPEN';
~~~

This is not equivalent to `OR` when rows match both conditions.

If fetching IDs in each branch and joining back, check unique keys and deduplication logic. Rewrites can also alter `ORDER BY`, `LIMIT`, and execution plans. Use them only after measuring benefits and verifying identical results on edge-case data.

## 10. Composite indexes can cover queries

A covering index contains all columns required for filtering and returning results, allowing MySQL to read data from the index without accessing clustered records in certain plans.

Example:

~~~sql
CREATE INDEX idx_ticket_customer_status_created
ON ticket (customer_id, status, created_at);
~~~

Query:

~~~sql
SELECT ticket_id, created_at
FROM ticket
WHERE customer_id = 42
  AND status = 'OPEN';
~~~

In InnoDB, secondary indexes store the primary key. Because `ticket_id` is the primary key, the composite index can contain `customer_id`, `status`, `created_at`, and `ticket_id`—enough to serve this query without reading `title` or other columns from the main row. `EXPLAIN` can display `Using index` if the plan is covering.

Index Merge across two single-column indexes may still have to access clustered records to check columns and fetch output data. An appropriate composite index can reduce random lookups and I/O.

Do not add every `SELECT` column to an index just to make it covering. Overly wide indexes:
- Consume storage.
- Reduce entries per page.
- Increase cache pressure.
- Increase `INSERT`/`UPDATE`/`DELETE` costs.
- Can increase index build and maintenance time.

Only create covering indexes for important, frequent queries with measurable gains.

## 11. Column order in composite indexes

Column order must follow query patterns, not merely whichever column has the highest cardinality.

### 11.1. Equality columns and range column

For the query:

~~~sql
WHERE customer_id = ?
  AND status = ?
  AND created_at >= ?
  AND created_at < ?
~~~

Candidate:

~~~sql
(customer_id, status, created_at)
~~~

Two equality columns first, range column after.

### 11.2. Queries needing ORDER BY

~~~sql
SELECT ticket_id, created_at
FROM ticket
WHERE customer_id = 42
  AND status = 'OPEN'
ORDER BY created_at DESC
LIMIT 20;
~~~

Index:

~~~sql
(customer_id, status, created_at)
~~~

can support filtering on the first two columns and accessing by `created_at`. Whether it satisfies `DESC` direction and avoids filesort depends on MySQL version, index definition, sort direction, and `ORDER BY` columns. On MySQL versions supporting descending indexes, you can evaluate:

~~~sql
CREATE INDEX idx_ticket_customer_status_created_desc
ON ticket (customer_id, status, created_at DESC);
~~~

Do not create both `ASC` and `DESC` without workload evidence requiring them. MySQL can scan indexes backward in many cases.

### 11.3. Low-selectivity columns

A `status` column with few values such as `OPEN`, `CLOSED`, `PENDING` typically has low cardinality. That does not mean it must always go last or is not worth indexing. If `status` is combined with `customer_id` and date, its position should serve actual query patterns and filter ordering.

A composite index can still be effective even if its leading column does not have the highest cardinality, provided predicates on that column are always present and isolate the relevant data group.

### 11.4. Leftmost prefix and other queries

Index `(customer_id, status, created_at)` can serve queries on `customer_id` alone, but does not directly serve `status`-only or `created_at`-only queries like an index starting with those columns.

If the workload has important `status`-only queries, you may still need `idx_ticket_status` or a composite index starting with `status`. Do not drop a single-column index merely because you added a composite index containing that column in second position.

## 12. Why does the optimizer not always choose Index Merge?

The optimizer estimates the cost of multiple access paths and chooses the plan predicted to be cheapest. Index Merge may not be chosen when:

- A single index already filters selectively enough.
- A full table scan is cheaper because conditions return many rows.
- Reading multiple indexes and merging row IDs is expensive.
- A composite index provides a better range.
- Index statistics do not reflect actual data.
- Predicates are non-sargable or cannot convert to usable range scans.
- `ORDER BY` or `LIMIT` makes another access path more favorable.

Non-sargable example:

~~~sql
SELECT ticket_id
FROM ticket
WHERE YEAR(created_at) = 2025;
~~~

Applying `YEAR` to the column can prevent a standard B-tree index on `created_at` from being used as a time range. Write a half-open interval:

~~~sql
SELECT ticket_id
FROM ticket
WHERE created_at >= '2025-01-01 00:00:00'
  AND created_at <  '2026-01-01 00:00:00';
~~~

The predicate can locate the range directly on `created_at`.

### 12.1. Updating statistics

After loading large datasets or shifting distributions, refresh statistics:

~~~sql
ANALYZE TABLE ticket;
~~~

Statistics help the optimizer estimate cardinality and cost. `ANALYZE TABLE` does not guarantee a specific plan will be chosen; it simply updates information used for decisions.

## 13. Reading EXPLAIN to recognize Index Merge

Example:

~~~sql
EXPLAIN
SELECT ticket_id
FROM ticket
WHERE customer_id = 42
  AND status = 'OPEN';
~~~

In tabular `EXPLAIN`, watch:

| Column | Meaning |
|---|---|
| `type` | If `index_merge`, the optimizer uses the Index Merge access method |
| `key` | May list multiple indexes used |
| `rows` | Estimated rows to read |
| `filtered` | Estimated percentage of rows remaining after conditions |
| `Extra` | May show `Using intersect(...)`, `Using union(...)`, or `Using sort_union(...)` |

If `type` is not `index_merge`, the query is not wrong. The optimizer may pick `ref`, `range`, `index`, or `ALL` depending on cost.

### 13.1. EXPLAIN FORMAT=TREE

~~~sql
EXPLAIN FORMAT=TREE
SELECT ticket_id, customer_id, status
FROM ticket
WHERE customer_id = 42
   OR status = 'OPEN';
~~~

`TREE` presents iterators and data access paths structurally. It is a helpful way to read more complex plans.

### 13.2. EXPLAIN ANALYZE

~~~sql
EXPLAIN ANALYZE
SELECT ticket_id, customer_id, status
FROM ticket
WHERE customer_id = 42
   OR status = 'OPEN';
~~~

`EXPLAIN ANALYZE` executes the `SELECT` statement and reports actual timings and row counts per iterator. Compare:
- Estimated rows vs. actual rows.
- Loop counts.
- Timing in each iterator.
- Merge and row-access costs.
- Final rows returned.

`EXPLAIN ANALYZE` actually runs the query. Test on representative data and an appropriate environment; do not run it carelessly on overly heavy queries in production.

## 14. Comparing plans by disabling Index Merge in a session

To test whether Index Merge actually helps, you can temporarily disable this strategy in a test session:

~~~sql
SELECT @@SESSION.optimizer_switch;

SET SESSION optimizer_switch = 'index_merge=off';

EXPLAIN
SELECT ticket_id
FROM ticket
WHERE customer_id = 42
  AND status = 'OPEN';

SET SESSION optimizer_switch = 'index_merge=on';
~~~

You can toggle individual branches separately:
- `index_merge_intersection`.
- `index_merge_union`.
- `index_merge_sort_union`.

Example:

~~~sql
SET SESSION optimizer_switch = 'index_merge_intersection=off';
~~~

Disabling Index Merge is solely for comparing plans. Do not assume the alternative plan is faster. Before changing settings, save the current `optimizer_switch` value so you can restore the session accurately. Never use `SET GLOBAL` during routine testing because it affects new sessions.

Optimizer hints can be used when controlling the plan for a specific query is necessary, yet hints are a last resort after understanding the data and cost model. Hints can degrade plans when data changes.

## 15. Storage and write-cost trade-offs

Every index is a data structure that must be stored and maintained.

### 15.1. Multiple single-column indexes

Advantages:
- Each index can serve standalone queries on one column.
- Can be combined via Index Merge when predicates fit.
- Easy to reuse across varied queries.

Costs:
- Every `INSERT` must update all relevant indexes.
- Updating indexed columns can modify multiple B-trees.
- `DELETE` must remove entries from all indexes.
- Consumes storage and buffer pool memory.
- Index Merge may need to read multiple structures and merge row IDs.

### 15.2. Composite index

Advantages:
- A single range scan can handle multiple predicates along a prefix.
- Can support `ORDER BY`/`GROUP BY` if order matches.
- Can become a covering index.
- Can replace redundant single-column indexes if workload allows.

Costs:
- Entries are usually wider than single-column indexes.
- Consumes storage and cache.
- Writes must maintain the composite index.
- Useful only for queries matching the leftmost prefix.
- Changing column order can break support for other queries.

### 15.3. Do not keep every index just because the optimizer can merge

If you keep `idx_customer` and `idx_status` solely for Index Merge intersection while the main workload always filters both `customer_id` and `status`, a composite index can cut read cost. Still, before dropping single-column indexes, check:
- Queries filtering solely on `customer_id`.
- Queries filtering solely on `status`.
- Joins using each column.
- `UNIQUE`/`FK` constraints.
- Reporting queries or background jobs.
- Execution plans of other queries after removal.

An index may serve multiple workloads beyond the query currently being tuned.

## 16. Index Merge does not replace JOIN indexes

Index Merge only merges range scans on the same table. For a `JOIN`:

~~~sql
SELECT
    t.ticket_id,
    c.customer_name
FROM ticket AS t
JOIN customer AS c
  ON c.customer_id = t.customer_id
WHERE t.status = 'OPEN';
~~~

The optimizer picks separate access paths for `ticket` and `customer`, then executes the join. It does not create an Index Merge combining indexes across both tables.

Indexes on `ticket.status`, `ticket.customer_id`, and `customer.customer_id` support different steps. If `ticket` frequently filters `status` and joins on `customer_id`, a composite index can be evaluated based on query order and cardinality. Do not assume single-table Index Merge substitutes for a join-key index.

## 17. Workload-driven design example

Suppose a ticketing system runs these frequent queries:

A. Look up a customer's tickets by status:

~~~sql
SELECT ticket_id, created_at, title
FROM ticket
WHERE customer_id = ?
  AND status = ?
ORDER BY created_at DESC
LIMIT 20;
~~~

Candidate:

~~~sql
CREATE INDEX idx_ticket_customer_status_created
ON ticket (customer_id, status, created_at);
~~~

B. Filter tickets by status and time range:

~~~sql
SELECT ticket_id, customer_id, created_at
FROM ticket
WHERE status = ?
  AND created_at >= ?
  AND created_at < ?
ORDER BY created_at DESC;
~~~

Candidate:

~~~sql
CREATE INDEX idx_ticket_status_created
ON ticket (status, created_at);
~~~

C. Find tickets by customer or status:

~~~sql
SELECT ticket_id
FROM ticket
WHERE customer_id = ?
   OR status = ?;
~~~

You can evaluate two single-column indexes and Index Merge union. The two composite indexes above do not automatically replace every `OR` branch.

Do not create all three indexes immediately. Rank queries by frequency, latency, rows read, and business impact; then determine which indexes are shared and which are redundant.

## 18. Common mistakes

| Misconception or mistake | Cause | How to fix |
|---|---|---|
| Index Merge is always faster than a full scan | Ignoring cost of reading multiple indexes and merging row IDs | Compare actual rows and execution time |
| Having single-column indexes guarantees MySQL will use intersection | Optimizer chooses by cost | Inspect `EXPLAIN`; do not assume |
| A composite index replaces every single-column index | Violates leftmost prefix when querying trailing columns alone | Check the entire workload |
| Index `(a,b)` works well for predicates on `b` alone | `b` is not the leftmost prefix | Create an index starting with `b` if workload needs it |
| Index Merge union is equivalent to `UNION ALL` | Rows matching multiple `OR` branches are returned once | `UNION ALL` can produce duplicates |
| Sort-Union guarantees business `ORDER BY` | It sorts row IDs only to merge them | Declare `ORDER BY` on the outer query |
| Composite index always needs highest-cardinality column first | Looking only at selectivity while ignoring equality/range and workload | Design around predicates and query order |
| Adding more indexes always speeds up `SELECT` | Write cost, storage, and cache pressure rise | Keep only indexes with measurable value |
| `EXPLAIN` `rows` is the exact row count | It is an estimate | Use `EXPLAIN ANALYZE` for actual rows |
| Turning off Index Merge proves composite index is better | Alternative plans may differ and tiny data is unrepresentative | Benchmark on realistic data |
| Index Merge combines indexes across joined tables | Access method applies to one table | Evaluate access paths for each table in the `JOIN` |

## 19. Process for choosing between Index Merge and composite indexes

When encountering a multi-column filter query:

1. Record the actual SQL, execution frequency, and latency requirements.
2. Identify whether the query uses `AND`, `OR`, or mixed condition groups.
3. Inspect existing indexes via `SHOW INDEX`.
4. Run `EXPLAIN` and check whether `type=index_merge` or another access path is used.
5. For intersection, evaluate a composite index ordered by equality, range, and `ORDER BY`.
6. For union, identify independent columns in `OR` and check whether separate single indexes are needed.
7. For sort-union, inspect the row ID set size and sort cost.
8. Evaluate selectivity and statistics; run `ANALYZE TABLE` if needed.
9. Create a candidate index on staging or a data copy.
10. Compare `EXPLAIN FORMAT=TREE` and `EXPLAIN ANALYZE` before/after.
11. Check covering, filesort, temporary operations, actual rows, and timing.
12. Measure write costs and storage size after adding the index.
13. Drop single-column indexes only after confirming no other workload needs them.
14. Monitor plans as data volume and value distribution evolve.

## 20. Practice exercises

### Exercise 1: Observe intersection

Use the `ticket` table with `idx_ticket_customer` and `idx_ticket_status`. Generate enough data and run `customer_id = 42 AND status = 'OPEN'`. Use `EXPLAIN` to see whether the optimizer selects `index_merge` intersection. Record `key` and `Extra`.

### Exercise 2: Observe union

Run `customer_id = 42 OR status = 'OPEN'`. Observe `type` and `Extra`. Create rows matching both conditions to confirm results do not return duplicates.

### Exercise 3: Observe sort-union

Run an `OR` condition between two ranges on `priority` and `created_at`. Use `EXPLAIN` to check for `Using sort_union`. If the optimizer chooses another plan, explain why based on cost and test with another data distribution.

### Exercise 4: Compare against a composite index

Create `idx_ticket_customer_status` on `(customer_id, status)`. Re-run the `AND` query. Compare `type`, `key`, `rows`, `Extra`, and `EXPLAIN ANALYZE` against the earlier Index Merge plan.

### Exercise 5: Test leftmost prefix

Create index `(customer_id, status, created_at)`. Run four queries:
- `customer_id = ?`
- `customer_id = ? AND status = ?`
- `customer_id = ? AND status = ? AND created_at` in range
- `status = ? AND created_at` in range

Record which cases can seek using the index prefix.

### Exercise 6: OR and UNION

Write the same query using `OR`, `UNION`, and `UNION ALL`. Create rows matching both branches. Compare row counts and explain why `UNION ALL` is not equivalent to `OR`.

### Exercise 7: ORDER BY and LIMIT

Query tickets by `customer_id`, `status`, `ORDER BY created_at DESC LIMIT 20`. Test a composite index including `created_at` and check for filesort. Compare with Index Merge intersection.

### Exercise 8: Write cost

Create a table with multiple single-column indexes, then test replacing some of them with a composite index. Measure batch `INSERT` time, `UPDATE` on indexed columns, and index sizes. Do not conclude solely from `SELECT` speed.

### Exercise 9: Refresh statistics

Significantly change `status` distribution and run `EXPLAIN` before and after `ANALYZE TABLE`. Record estimated `rows` and plan changes.

### Exercise 10: Workload evaluation

Gather at least five real queries for a table. Build a table mapping predicates, `ORDER BY`, `LIMIT`, used indexes, and proposed indexes. Explain which indexes to keep, add, or drop.

## 21. Pre-deployment index checklist

- [ ] Identified whether Index Merge is using intersection, union, or sort-union.
- [ ] Checked `type`, `key`, `rows`, and `Extra` in `EXPLAIN`.
- [ ] Confirmed Index Merge is combining indexes on the same table.
- [ ] Distinguished Index Merge from a composite index.
- [ ] Applied leftmost-prefix when designing column order.
- [ ] Considered equality columns, range columns, and `ORDER BY`.
- [ ] Checked whether `OR` queries require separate single-column indexes.
- [ ] Did not confuse sort-union with final `ORDER BY` ordering.
- [ ] Checked covering index usage and filesort.
- [ ] Inspected actual rows and timings with `EXPLAIN ANALYZE` where appropriate.
- [ ] Refreshed statistics if data distribution changed.
- [ ] Benchmarked on representative data.
- [ ] Evaluated storage footprint and `INSERT`/`UPDATE`/`DELETE` cost.
- [ ] Checked other workloads before dropping single-column indexes.
- [ ] Monitored plans after deployment.

## 22. Conclusion

Index Merge allows MySQL to use multiple separate indexes on the same table and merge row IDs via intersection, union, or sort-union. It is useful when queries combine multiple predicates and existing single-column indexes can serve individual branches. However, reading multiple indexes, merging, and fetching rows can be costly; sort-union additionally requires sorting row IDs.

A composite index stores multiple columns in one B-tree and is often effective for stable `AND` query patterns, especially when column order matches equality, range, and `ORDER BY`. In return, a composite index relies on the leftmost prefix, may not serve queries filtering solely on trailing columns, and increases write/storage costs. Choose based on workload rather than a single universal rule: inspect `EXPLAIN`, measure actual rows, check `ORDER BY`/`LIMIT`, benchmark both reads and writes, and ensure every retained index has a clear purpose.

## Official references

- [MySQL 8.4 Reference Manual – Index Merge Optimization](https://dev.mysql.com/doc/refman/8.4/en/index-merge-optimization.html)
- [MySQL 8.4 Reference Manual – Range Optimization](https://dev.mysql.com/doc/refman/8.4/en/range-optimization.html)
- [MySQL 8.4 Reference Manual – Multiple-Column Indexes](https://dev.mysql.com/doc/refman/8.4/en/multiple-column-indexes.html)
- [MySQL 8.4 Reference Manual – How MySQL Uses Indexes](https://dev.mysql.com/doc/refman/8.4/en/mysql-indexes.html)
- [MySQL 8.4 Reference Manual – EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)
- [MySQL 8.4 Reference Manual – Optimizer Switch](https://dev.mysql.com/doc/refman/8.4/en/switchable-optimizations.html)
- [MySQL 8.4 Reference Manual – ANALYZE TABLE](https://dev.mysql.com/doc/refman/8.4/en/analyze-table.html)
- [MySQL 8.4 Reference Manual – InnoDB Index Types](https://dev.mysql.com/doc/refman/8.4/en/innodb-index-types.html)
