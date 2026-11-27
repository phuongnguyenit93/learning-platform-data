# Designing Composite Indexes Around Filtering, JOINs, and Sorting

A composite index is a B-tree containing multiple columns in a defined order. It is especially valuable when queries frequently combine multiple WHERE conditions, join tables via JOIN, and return results ordered by ORDER BY. Choosing the right column order helps MySQL jump straight to a narrow key range, reduce rows read, and potentially avoid an extra sort step.

A composite index is not simply dumping every column that appears in a SQL query into one index. A B-tree is ordered from left to right. The leading column, subsequent columns, and the placement of range predicates determine how far the optimizer can narrow the search. If ordered poorly, the index still exists yet may only be partially usable, fail to assist JOINs as intended, or fail to satisfy ORDER BY.

In the **DATABASE_MYSQL** module, index design must balance read performance, write overhead, storage size, and contention when concurrent transactions update rows. This lesson explains how to analyze workload, order key parts for WHERE, JOIN, and ORDER BY, verify with EXPLAIN, and decide whether to extend an index into a covering index.

## 1. Composite Indexes Work by Column Order

Suppose you have the index:

```sql
CREATE INDEX idx_tenant_status_created
    ON orders (tenant_id, status, created_at);
```

The B-tree is ordered by:

1. tenant_id
2. Within the same tenant_id, ordered by status
3. Within the same tenant_id and status, ordered by created_at

Consequently, this index can effectively support predicates based on a leftmost prefix:

- tenant_id = ?
- tenant_id = ? AND status = ?
- tenant_id = ? AND status = ? AND created_at >= ?

However, it generally cannot form an efficient contiguous search range for queries filtering only on status or only on created_at because the leading key part tenant_id is unconstrained.

Example:

```sql
-- Can use the leftmost prefix
SELECT *
FROM orders
WHERE tenant_id = 42;

-- Can use the first two key parts
SELECT *
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID';

-- No predicate on the leading key part
SELECT *
FROM orders
WHERE status = 'PAID';
```

The third query might still be served by a full index scan, an index skip scan in certain versions and qualifying conditions, or another index. However, you should not design on the assumption that every key part can be used independently.

### 1.1. Column Order Is a Design Decision

The following two indexes are not equivalent:

```sql
CREATE INDEX idx_a ON orders (tenant_id, status, created_at);
CREATE INDEX idx_b ON orders (status, tenant_id, created_at);
```

Both contain the same three columns, yet their key spaces are organized differently. If most queries always filter on tenant_id first, idx_a may fit better. If the workload often filters on status without tenant_id, idx_b may be more helpful for those queries.

There is no rigid rule that the highest-cardinality column must always go first. Consider query predicates, prefixes used, selectivity, row counts per tenant/status, JOINs, and sort orders to be served.

## 2. Start from Workload Rather Than a Column List

Before creating an index, gather actual queries:

- Which WHERE conditions appear most frequently?
- Which conditions always appear together?
- Which columns are used for JOINs?
- Do queries have ORDER BY or LIMIT?
- Are there GROUP BY, DISTINCT, or time ranges?
- How many rows do queries read vs return?
- What is the table's INSERT/UPDATE/DELETE frequency?

A good index usually serves a group of structurally similar queries. An overly wide index may help one query while inflating storage and maintenance overhead for every write operation.

Example orders table:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id)
) ENGINE = InnoDB;
```

Sample workload:

| Query | Key columns | Goal |
|---|---|---|
| Tenant's pending orders list | tenant_id, status | Filtering |
| Customer's orders by time | customer_id, created_at | Filtering and sorting |
| Tenant's orders JOIN customer | tenant_id, customer_id | Filtering and JOIN |
| Tenant's latest orders | tenant_id, created_at | Filtering, ORDER BY, LIMIT |
| Order count by status | tenant_id, status | Filtering and GROUP BY |

Do not try to force a single index to serve everything when column orderings and access patterns conflict. Multiple specialized indexes may be needed, but each index must bring enough benefit to justify its write cost.

## 3. Design Key Parts for WHERE Conditions

A pragmatic principle is to place applicable equality predicates before range predicates, and then consider columns needed for sorting or additional access.

Example:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = 42
  AND status = 'PENDING'
  AND created_at >= '2026-01-01'
  AND created_at <  '2026-02-01';
```

Suitable index:

```sql
CREATE INDEX idx_orders_tenant_status_created
    ON orders (tenant_id, status, created_at);
```

The optimizer can:

1. Locate the tenant_id = 42 region.
2. Within that region, narrow down to status = 'PENDING'.
3. Scan the created_at range for the target month.

### 3.1. Equality First, Range After

Equality conditions typically allow the B-tree to continue narrowing the range across multiple key parts. Once a range key part is encountered, subsequent parts usually cannot narrow a single contiguous range in the same straightforward manner.

Example index:

```sql
CREATE INDEX idx_tenant_status_date_amount
    ON orders (tenant_id, status, created_at, total_amount);
```

Query:

```sql
SELECT order_id
FROM orders
WHERE tenant_id = 42
  AND status = 'PENDING'
  AND created_at >= '2026-01-01'
  AND total_amount > 1000000;
```

The index can use tenant_id and status as an equality prefix, and created_at as a range. Because total_amount sits after the range, it typically does not form an additional independent search bound to narrow the range. However, depending on the index structure and plan, the total_amount predicate may be evaluated via Index Condition Pushdown (ICP), reducing clustered record reads.

ICP helps filter candidates directly on index entries when possible; it does not mean every key part after a range is used to bound the B-tree search range like an equality prefix.

### 3.2. Ordering Among Equality Columns

If queries always specify both tenant_id = ? and status = ?, either order below can utilize the first two key parts:

- (tenant_id, status, created_at)
- (status, tenant_id, created_at)

Choose the order based on other queries in the workload:

- Do queries with tenant_id and no status need support?
- Are system-wide queries filtering by status important?
- Is data distribution heavily skewed across tenants?
- Must it also serve other JOIN or ORDER BY queries?
- Which index maximizes leftmost prefix reuse?

Column selectivity is one factor, though not the only factor. The leading equality column must align with the query patterns needing support.

### 3.3. IN, IS NULL, and Multi-Value Predicates

An IN condition can be handled by the optimizer as multiple ranges or lookups:

```sql
SELECT order_id
FROM orders
WHERE tenant_id = 42
  AND status IN ('PENDING', 'PAID')
  AND created_at >= '2026-01-01';
```

The index (tenant_id, status, created_at) can still be helpful, though multiple status values can produce multiple lookup ranges. When a global ORDER BY on created_at is required, multiple separate ranges may force the optimizer to merge or sort results.

IS NULL can be used in index search predicates. Still, verify behavior with EXPLAIN instead of treating NULL like a standard equality value in every context.

### 3.4. Avoid Breaking Sargability

A sargable predicate allows the optimizer to use an index to locate the relevant data range.

Unfavorable example:

```sql
SELECT order_id
FROM orders
WHERE DATE(created_at) = '2026-01-15';
```

Applying a function to the column can prevent direct range access on the created_at index. Rewrite as a time range:

```sql
SELECT order_id
FROM orders
WHERE created_at >= '2026-01-15 00:00:00'
  AND created_at <  '2026-01-16 00:00:00';
```

Keep parameter data types compatible with column types; avoid implicit casts or column transformations in expressions when unnecessary.

## 4. Design Composite Indexes for JOINs

With a nested-loop join, MySQL typically reads one row from the outer table and looks up matching rows in the inner table. An index on the inner table's JOIN columns avoids scanning the entire inner table for each outer row.

Example:

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    customer_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (customer_id),
    KEY idx_customers_tenant (tenant_id)
) ENGINE = InnoDB;

CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_tenant_status_created (
        tenant_id,
        status,
        created_at
    ),
    KEY idx_orders_customer_created (
        customer_id,
        created_at
    )
) ENGINE = InnoDB;
```

Query:

```sql
SELECT
    o.order_id,
    o.created_at,
    c.customer_name
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id
WHERE o.tenant_id = 42
  AND o.status = 'PAID'
  AND o.created_at >= '2026-01-01'
  AND o.created_at <  '2026-02-01'
ORDER BY o.created_at DESC;
```

The optimizer can filter orders using idx_orders_tenant_status_created and then look up customers via PRIMARY KEY(customer_id). If the plan chooses customers as the outer table, indexes and predicates on orders may be used differently. Inspect the JOIN order in EXPLAIN.

### 4.1. Indexes for the Inner Table of a JOIN

Two-table example:

```sql
CREATE TABLE order_items (
    item_id BIGINT UNSIGNED NOT NULL,
    order_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT NOT NULL,
    PRIMARY KEY (item_id)
) ENGINE = InnoDB;
```

```sql
SELECT
    o.order_id,
    i.product_id,
    i.quantity
FROM orders AS o
JOIN order_items AS i
    ON i.order_id = o.order_id
WHERE o.tenant_id = 42
  AND o.status = 'PAID';
```

If the optimizer filters orders first and then looks up order_items for each order_id, the index:

```sql
CREATE INDEX idx_items_order_product
    ON order_items (order_id, product_id);
```

can support lookups by order_id. If the query also filters product_id in the same lookup, the second key part can be helpful.

Conversely, if product_id is a highly selective predicate and the optimizer starts from order_items to find orders, the index:

```sql
CREATE INDEX idx_items_product_order
    ON order_items (product_id, order_id);
```

may fit better. These two indexes do not replace one another because their leftmost prefixes differ.

### 4.2. Multi-Column JOINs

If a JOIN condition spans multiple columns:

```sql
CREATE TABLE tenant_orders (
    order_id BIGINT UNSIGNED NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_tenant_customer (tenant_id, customer_id)
) ENGINE = InnoDB;

CREATE TABLE tenant_customers (
    customer_row_id BIGINT UNSIGNED NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    customer_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (customer_row_id),
    UNIQUE KEY uq_tenant_customer (tenant_id, customer_id)
) ENGINE = InnoDB;
```

```sql
SELECT *
FROM tenant_orders AS o
JOIN tenant_customers AS c
  ON c.tenant_id = o.tenant_id
 AND c.customer_id = o.customer_id
WHERE o.tenant_id = 42;
```

UNIQUE KEY uq_tenant_customer itself acts as a composite index on the looked-up table. It both enforces customer_id uniqueness within a tenant and supports lookups across both JOIN columns. If the pair (tenant_id, customer_id) is already a PRIMARY KEY or UNIQUE KEY, do not create a redundant duplicate index. Always inspect existing indexes before adding new ones.

### 4.3. Order Columns Based on the Driving Table

There is no single JOIN column order that works for every plan. Determine:

1. Which table is likely to be the outer (driving) table?
2. Which predicates filter the outer table down to the fewest rows?
3. For each outer row, which columns are used to look up the inner table?
4. Are there additional predicates on the inner table?
5. Could the optimizer reorder the JOIN?

An inner table's index typically starts with the columns used to look it up from the outer table. If there are additional equality predicates on the inner table, consider placing them in subsequent key parts.

Do not create indexes on every JOIN column reflexively. An existing primary key, unique key, or composite index may already satisfy the lookup.

## 5. Combining WHERE, JOIN, and ORDER BY in One Index

This requires balancing multiple goals. A single index can:

- Narrow rows via WHERE.
- Support lookup/JOIN.
- Return rows in ORDER BY sequence.
- Partially or fully cover SELECT columns.

Example querying a tenant's latest orders:

```sql
SELECT
    order_id,
    customer_id,
    created_at,
    total_amount
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at <  '2026-02-01'
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
```

Proposed index for MySQL 8.0:

```sql
CREATE INDEX idx_orders_tenant_status_created_id
    ON orders (
        tenant_id,
        status,
        created_at DESC,
        order_id DESC
    );
```

Order analysis:

1. tenant_id is fixed by equality.
2. status is fixed by equality.
3. created_at bounds the range and serves as the primary sort column.
4. order_id acts as a tie-breaker for deterministic ordering.

With the first two key parts fixed, the B-tree can scan the time slice in the desired order. LIMIT 50 allows early termination once enough rows are found if the plan uses index order.

MySQL 8.0 supports descending index key parts. With an ascending index, the B-tree can also be scanned backward when all sort directions align. When ORDER BY mixes ASC and DESC, declaring matching index key directions may be necessary to avoid a sort.

### 5.1. Why Range Columns and ORDER BY Must Be Considered Together

An index can use an equality prefix and then perform a range scan. If ORDER BY starts at the range column and continues along subsequent key parts, the index can supply the desired order.

However, if the query has:

```sql
WHERE tenant_id = 42
  AND status IN ('PAID', 'PENDING')
ORDER BY created_at DESC;
```

an index (tenant_id, status, created_at) produces separate slices per status. The created_at ordering within each slice does not automatically form a global ordering across multiple statuses. The optimizer may need to merge or sort.

If global ORDER BY created_at is the primary goal, an index (tenant_id, created_at) may fit better, though status then becomes a post-read filter. Benchmark both options on real data distributions.

### 5.2. ORDER BY After an Unfixed Column

Suppose the index is:

```sql
CREATE INDEX idx_tenant_status_created
    ON orders (tenant_id, status, created_at);
```

Query:

```sql
SELECT order_id
FROM orders
WHERE tenant_id = 42
ORDER BY created_at DESC;
```

Because status sits between tenant_id and created_at without being fixed to a single value, the index does not provide a global created_at order for the tenant. Rows are grouped by status first, and only ordered by created_at within each group.

Another index may be more suitable:

```sql
CREATE INDEX idx_tenant_created
    ON orders (tenant_id, created_at DESC);
```

You cannot simply see the ORDER BY column present in an index and conclude MySQL will avoid filesort. Preceding key parts also matter.

## 6. Covering Indexes: When Should You Add SELECT Columns?

A covering index contains all columns needed by a query so the engine can return results without reading the clustered record for every row, when predicates and access paths allow.

Example query:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;
```

Filtering and sorting index:

```sql
CREATE INDEX idx_orders_tenant_status_created
    ON orders (tenant_id, status, created_at DESC);
```

This index may require reading the clustered record to fetch total_amount. If the query runs very frequently and 50 clustered record lookups represent a meaningful cost, you can test an extended index:

```sql
CREATE INDEX idx_orders_tenant_status_created_amount
    ON orders (
        tenant_id,
        status,
        created_at DESC,
        total_amount
    );
```

However, if ORDER BY created_at DESC, order_id DESC is needed, placing total_amount ahead of order_id in the index can disrupt the tie-breaker order. In that case, consider:

```sql
CREATE INDEX idx_orders_tenant_status_created_id_amount
    ON orders (
        tenant_id,
        status,
        created_at DESC,
        order_id DESC,
        total_amount
    );
```

This is a larger index. Do not add every SELECT column to an index just to achieve covering. Weigh:

- How many queries benefit and how often they execute.
- Size of the added columns.
- Frequency of INSERT/UPDATE/DELETE.
- Buffer pool and I/O cost.
- Whether changing those columns increases index maintenance overhead.

In InnoDB, secondary indexes automatically carry the primary key to locate rows. Still, if you need to control sort direction or tie-breaker position, you may need to declare the primary key column explicitly in the index.

## 7. ASC/DESC Ordering and Result Stability

MySQL 8.0 supports descending indexes. Example:

```sql
CREATE INDEX idx_orders_recent
    ON orders (
        tenant_id ASC,
        created_at DESC,
        order_id DESC
    );
```

Query:

```sql
SELECT order_id, created_at
FROM orders
WHERE tenant_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 100;
```

The index can serve tenant filtering and latest-first ordering. order_id guarantees deterministic ordering when multiple rows share the same created_at.

If you only ORDER BY created_at while multiple rows share timestamps, relative ordering among ties is not guaranteed. When paginating with LIMIT/OFFSET or keyset pagination, include a unique tie-breaker like order_id to prevent unpredictable ordering shifts.

On MySQL prior to 8.0, DESC syntax in index definitions may be accepted, yet key parts are stored ascending and do not build physical descending indexes as in MySQL 8.0. Verify the target version before relying on mixed-direction indexes.

## 8. Composite Indexes and GROUP BY

An index can support GROUP BY if key part order matches the grouping columns and preceding filter predicates. Example:

```sql
SELECT tenant_id, status, COUNT(*)
FROM orders
WHERE tenant_id = 42
GROUP BY tenant_id, status;
```

An index (tenant_id, status) can support tenant filtering and reading status groups in index order. However, if grouping by status across the entire table while the index starts with tenant_id, the index may not provide a global grouping order.

GROUP BY, DISTINCT, and ORDER BY have their own optimization rules. Inspect Extra, JSON/TREE plans, and actual row counts rather than assuming a composite index automatically eliminates temporary tables or filesorts.

## 9. Index Merge Does Not Replace Composite Index Design

MySQL can use Index Merge to combine multiple single-column indexes in some queries:

```sql
CREATE INDEX idx_orders_tenant ON orders (tenant_id);
CREATE INDEX idx_orders_status ON orders (status);

SELECT order_id
FROM orders
WHERE tenant_id = 42
  AND status = 'PENDING';
```

The optimizer may consider intersecting row ID sets from the two indexes. However, Index Merge carries its own combination and data access overhead. A composite index:

```sql
CREATE INDEX idx_orders_tenant_status
    ON orders (tenant_id, status);
```

usually enables direct lookup of the combined region and can be more efficient.

Not every query performs better with a composite index; single-column indexes may be reused across other workloads. Compare EXPLAIN plans and benchmark.

## 10. Read EXPLAIN to Verify Composite Indexes

Before adding an index, record the baseline plan:

```sql
EXPLAIN FORMAT = JSON
SELECT
    order_id,
    customer_id,
    created_at,
    total_amount
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at <  '2026-02-01'
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
```

Fields to inspect:

| Field | Question |
|---|---|
| access_type / type | Is it using range/ref or doing a full scan? |
| possible_keys | Which indexes are eligible? |
| key | Which index did the optimizer actually choose? |
| key_len | How many key parts are used? |
| rows | What is the estimated row count to read? |
| filtered | What percentage of rows remain after additional filters? |
| Extra | Are there Using filesort, Using temporary, Using index condition, or Using index? |
| cost_info | How did the optimizer's estimated cost change? |

key_len helps deduce how much of a composite index is used for lookup, though you must account for data types, NULLability, and charset. It does not reveal everything evaluated via ICP or WHERE.

After creating the index, inspect the plan again:

```sql
CREATE INDEX idx_orders_tenant_status_created_id
    ON orders (
        tenant_id,
        status,
        created_at DESC,
        order_id DESC
    );

EXPLAIN FORMAT = JSON
SELECT
    order_id,
    customer_id,
    created_at,
    total_amount
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at <  '2026-02-01'
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
```

On MySQL 8.0.18 and later, EXPLAIN ANALYZE can execute the SELECT and show actual rows, loops, and iterator timings:

```sql
EXPLAIN ANALYZE
SELECT
    order_id,
    customer_id,
    created_at,
    total_amount
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at <  '2026-02-01'
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
```

EXPLAIN ANALYZE runs the actual query. Use it only with appropriate SELECT queries and evaluate production impact before running.

## 11. One Index Can Serve Multiple Queries, But Not All Queries

The index (tenant_id, status, created_at) can serve:

- WHERE tenant_id = ?
- WHERE tenant_id = ? AND status = ?
- WHERE tenant_id = ? AND status = ? AND created_at >= ?
- WHERE tenant_id = ? AND status = ? ORDER BY created_at

However, it is not a good choice for every pattern:

- WHERE status = ? without tenant_id.
- WHERE created_at >= ? without the first two key parts.
- WHERE tenant_id = ? ORDER BY created_at if status is not fixed.
- Global ORDER BY created_at without a tenant_id predicate.

A long composite index can cover many prefixes, yet adding key parts makes the index larger and increases write cost. Design around high-impact query groups that can reuse prefixes.

## 12. Common Design Mistakes

| Mistake | Consequence | How to handle |
|---|---|---|
| Putting all WHERE columns in an index in arbitrary order | Optimizer uses only part of the key | Consider equality, range, and leftmost prefix |
| Always putting highest-cardinality column first | Ignores query patterns and prefix reuse | Choose based on actual workload |
| Putting range column before needed equality columns | Key parts after range rarely narrow the lookup | Place suitable equality columns before range |
| Putting ORDER BY column after an unfixed key part | Index fails to provide desired global order | Fix or remove the preceding key part |
| Indexing only the outer table of a JOIN | Repeated inner-table lookups still scan widely | Index JOIN columns on the looked-up table |
| Creating both (a,b) and (b,a) without workload evidence | Increases storage and write overhead | Verify which queries need each leftmost prefix |
| Adding all SELECT columns just to cover | Large index, high write amplification | Measure covering index benefit |
| Assuming Index Merge is always equal to a composite index | Incurs row ID intersection overhead | Compare plans and benchmark |
| Assuming an ORDER BY column in an index avoids filesort | Preceding key parts may break sort order | Check full index ordering |
| Omitting tie-breaker with LIMIT | Ordering across tied rows is unstable | Add unique key to ORDER BY |
| Failing to measure after creating an index | Index may go unused or worsen the plan | Run EXPLAIN, EXPLAIN ANALYZE, and workload tests |

## 13. Composite Index Design Workflow

Follow these steps:

1. **Select representative queries.** Base design on high-frequency or high-impact queries, not a rare one-off statement.
2. **Classify predicates.** Separate equality, IN, IS NULL, range, JOIN, ORDER BY, and GROUP BY.
3. **Identify the driving table.** For JOINs, determine the outer table and inner-table lookup in the current plan.
4. **Choose the equality prefix.** Place essential equality columns first, considering reuse for queries with fewer predicates.
5. **Place ranges sensibly.** Ranges usually follow the equality key parts usable by the query.
6. **Consider sort order.** Place ORDER BY columns next if preceding key parts are fixed and directions match.
7. **Evaluate covering last.** Add SELECT columns only when avoiding clustered lookups yields a large enough gain.
8. **Check for duplicate/redundant indexes.** Reuse existing indexes if their leftmost prefix already covers the need.
9. **Read EXPLAIN.** Check key, key_len, rows, filtered, Extra, and join order.
10. **Benchmark.** Compare latency, throughput, rows examined, CPU/I/O, and DML cost.
11. **Monitor production.** Watch index usage, disk size, lock waits, and plan regressions after deployment.

## 14. Evaluate Write Cost and Index Lifecycle

Every additional secondary index must be maintained on INSERT, DELETE, and whenever indexed columns change. Longer composite indexes grow B-tree size and can reduce entries per page.

Before adding an index, weigh:

- Does the table have high or low write rate?
- Do the indexed columns change frequently?
- Is the index duplicated or already covered by another index?
- Can two single-column indexes be replaced by one composite index while preserving other workloads?
- Does the index significantly slow down imports, updates, or deletes?
- Does index size fit comfortably in the buffer pool and storage?

Do not drop an index based only on a short observation window. An index might serve periodic queries, reports, constraints, or infrequent yet critical business flows.

## 15. End-to-End Example: Filtering, JOIN, and Sorting

Requirement: fetch the 50 most recent PAID orders for a tenant, displaying the customer name.

```sql
SELECT
    o.order_id,
    o.created_at,
    o.total_amount,
    c.customer_name
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id
WHERE o.tenant_id = 42
  AND o.status = 'PAID'
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT 50;
```

Usable index:

```sql
CREATE INDEX idx_orders_tenant_status_created_id
    ON orders (
        tenant_id,
        status,
        created_at DESC,
        order_id DESC
    );
```

customers already has PRIMARY KEY(customer_id), so customer lookup by customer_id already has a unique index. There is no need to add a duplicate customer_id index on customers.

Expected logical plan:

1. Use equality prefix tenant_id and status to locate the orders slice.
2. Scan in created_at DESC, order_id DESC order.
3. Stop once 50 rows are reached.
4. For each row, look up the customer via PRIMARY KEY.

This is a design hypothesis, not a guarantee that the optimizer will always pick this exact plan. If the tenant has too many PAID orders or most rows are filtered later, a different plan may be cheaper. Use EXPLAIN and benchmarks to verify.

If the query is critical and clustered record lookups on orders are expensive, you can test a covering index after measuring. However, adding total_amount or customer_id increases index size; keep order_id in the proper position if it serves as the ORDER BY tie-breaker.

## 16. Pre-Production Composite Index Checklist

- Target query and representative parameters are identified.
- Equality, range, JOIN, and ORDER BY parts are categorized.
- Key part order follows the workload's leftmost prefix.
- Range columns do not precede essential equality key parts.
- ORDER BY columns are not broken by an unfixed preceding key part.
- Inner-table JOIN index supports lookups from the outer table.
- Checked PRIMARY/UNIQUE/existing indexes to avoid duplicates.
- Evaluated covering index trade-offs and index size cost.
- EXPLAIN shows an appropriate access path.
- EXPLAIN ANALYZE or benchmarks confirm improved actual rows and latency.
- Measured INSERT/UPDATE/DELETE overhead and index size.
- Plan in place to monitor for plan regressions after deployment.

## 17. Key Takeaways

- A composite index is a multi-column B-tree; key part order determines leftmost prefix usability.
- Place applicable equality predicates before ranges; key parts after a range usually cannot continue narrowing the lookup simply.
- Ordering among equality columns should reflect workload, selectivity, and prefix reuse.
- For nested-loop JOINs, inner-table indexes must support lookups on join columns from the outer table.
- For multi-column JOINs, consider a composite index matching the lookup key parts.
- ORDER BY can use an index when preceding key parts are fixed and column order/ASC-DESC directions align.
- Multi-value IN predicates can create multiple ranges; the index is not guaranteed to provide global ordering for trailing columns.
- Covering indexes reduce clustered lookups at the cost of larger indexes and higher write overhead.
- Index Merge is not automatically as efficient as a well-designed composite index.
- EXPLAIN shows the estimated access path; EXPLAIN ANALYZE on SELECT helps compare actual rows, loops, and timings.
- Every index must be evaluated against both read workloads and INSERT/UPDATE/DELETE costs.
- Index design is a hypothesis that must be validated with data and benchmarks.

Effective composite index design starts from actual queries and access orders. Align filter predicates, JOIN columns, and sort order within one B-tree when they share an access pattern; then confirm with execution plans and benchmarks before broad rollout.

## References

- MySQL 8.0 Reference Manual — Multiple-Column Indexes: https://dev.mysql.com/doc/refman/8.0/en/multiple-column-indexes.html
- MySQL 8.0 Reference Manual — ORDER BY Optimization: https://dev.mysql.com/doc/refman/8.0/en/order-by-optimization.html
- MySQL 8.0 Reference Manual — Index Condition Pushdown Optimization: https://dev.mysql.com/doc/refman/8.0/en/index-condition-pushdown-optimization.html
- MySQL 8.0 Reference Manual — EXPLAIN Output Format: https://dev.mysql.com/doc/refman/8.0/en/explain-output.html
