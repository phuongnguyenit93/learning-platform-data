# B+tree Structure and Key-Based Lookup Mechanism

In InnoDB, regular indexes are organized using a **B+tree** structure. The tree keeps keys in order, divides data into multiple pages, and allows MySQL to traverse from the root page through intermediate pages to the required leaf page. Instead of sequentially reading the entire table, the engine can locate the region containing the target key and read only a subset of relevant pages.

To understand why an index makes a query fast, you need to grasp three things: the contents of each B+tree level, the difference between a clustered index and a secondary index, and how query predicates match key order. An index does not automatically make every query faster; effectiveness depends on the keys being searched, the range to read, the number of matching rows, and whether the pages are already in the buffer pool.

In the `DATABASE_MYSQL` module, this knowledge is the foundation for designing indexes, reading `EXPLAIN`, understanding primary/secondary key lookups, choosing column order in composite indexes, and evaluating read/write costs. Examples use InnoDB and MySQL syntax.

## 1. How does a B+tree solve the lookup problem?

If a table has millions of records without a suitable index, MySQL may have to scan much or all of the data to find rows matching a condition. This is a table scan. With a B+tree, keys are sorted and hierarchically organized across multiple pages; each step down the tree narrows the key region to search.

Imagine an index with numeric keys:

```text
                         [ 40 | 80 ]              root
                        /    |     \
                       /     |      \
             [10 | 20 | 30] [50 | 60 | 70] [90 | 100 | 110]
                  leaf          leaf          leaf
```

The root holds separator keys to direct traversal to child pages. When searching for key 60, the engine compares it against 40 and 80, takes the middle branch, and searches within the leaf page containing the corresponding key range.

This is only a logical diagram. In InnoDB, each node is an index page; a single page can hold many keys and many pointers, rather than one key per node. The tree can have multiple intermediate levels as data grows.

### Why is it called a B+tree?

In a B+tree structure, navigation keys reside in internal nodes and index data resides at the leaf level. All leaf pages sit at the same depth, giving the path from root to leaf a consistent number of levels. Leaf pages are linked in key order to support range traversal and index scans.

For InnoDB:

- Root pages and intermediate pages contain separator keys along with pointers to child pages.
- Leaf pages of a clustered index contain the full table records.
- Leaf pages of a secondary index contain the secondary key along with the clustered key needed to locate the row.
- Leaf pages are linked in key order, making sequential reading of consecutive values efficient.

## 2. Pages are the critical unit of storage and I/O

InnoDB does not read individual index values from disk independently. Index data is stored in pages. The default page size is typically 16 KiB, though it can be configured when initializing the instance; supported sizes depend on configuration and version.

One page can hold multiple index records. The number of records depends on key width, data stored in the leaf, page management overhead, and fill factor. Therefore:

- Wider keys mean each page generally holds fewer entries.
- Smaller entries allow one page to serve more keys.
- Pages holding more entries typically increase internal node fan-out.
- High fan-out allows the tree to need fewer levels to manage the same number of keys.

Conceptual illustration:

```text
Narrow keys: [k1 k2 k3 k4 k5 k6 k7 k8 ...]
Wide keys:   [long-key-1] [long-key-2] [long-key-3] ...
             fewer entries on the same page
```

This is a conceptual model; you cannot deduce the exact number of entries per page solely from data types. You must also account for actual lengths, nullable flags, record headers, the page directory, and other internal components.

### The buffer pool keeps frequently used pages in memory

InnoDB uses the buffer pool to cache data pages and index pages. When a page to be read is already in the buffer pool, the engine can access it in memory without reading from storage again. If the page is not present, InnoDB must read the page from the tablespace into the buffer pool.

Thus, index performance depends not only on the number of comparisons in the tree, but also on:

- Whether root/intermediate/leaf pages are in the buffer pool.
- How many leaf pages the query must read.
- Whether a secondary lookup requires reading additional clustered pages.
- Whether accessed pages have locality or are randomly scattered.
- Whether the buffer pool has enough space for the working set or must constantly evict pages.

## 3. Path from root to leaf

A B+tree lookup typically consists of the following steps:

1. Start at the index's root page.
2. Compare the search key against separator keys in the page.
3. Choose the child pointer corresponding to the key range.
4. Read the next intermediate page if the tree has multiple levels.
5. Repeat until reaching the leaf page containing the key or where the key could reside.
6. Find the entry in the leaf page; if it is a range scan, continue to the next leaf page in key order.

Diagram:

```text
       Root page
           |
           v
   Intermediate page
           |
           v
       Leaf page  <---->  Leaf page  <---->  Leaf page
        keys 10-19          20-29              30-39
```

Within each page, InnoDB uses an internal structure to search records in key order. When a page contains many records, the engine does not need to walk every row from the start like a table scan; the page directory and record organization help locate the appropriate region.

### Balanced tree and page access count

A B+tree keeps all leaves at the same depth. As the number of keys grows, the tree expands by splitting pages and may add levels. Tree height usually grows slowly relative to the number of keys because one internal page can point to many child pages.

You should not interpret this to mean every lookup always reads exactly three pages. The actual number of pages depends on tree height, whether pages are already in the buffer pool, the index type, and whether the query needs one or multiple leaf pages.

## 4. Clustered index: leaf pages contain the entire row

In InnoDB, the clustered index determines how row data is organized. If a table has a primary key, the primary key is the clustered index. Leaf pages of the clustered index contain the columns of the row.

Example:

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL,
    email VARCHAR(254) NOT NULL,
    full_name VARCHAR(120) NOT NULL,
    city VARCHAR(80) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;

INSERT INTO customers (customer_id, email, full_name, city, created_at)
VALUES
    (105, 'linh@example.test', 'Linh Nguyen', 'Da Nang', '2026-01-10 09:00:00'),
    (106, 'minh@example.test', 'Minh Tran', 'Ho Chi Minh City', '2026-01-12 10:30:00'),
    (107, 'an@example.test', 'An Pham', 'Da Nang', '2026-01-15 14:15:00');
```

For the query:

```sql
SELECT customer_id, email, full_name, city, created_at
FROM customers
WHERE customer_id = 105;
```

MySQL can traverse directly down the primary key's clustered B+tree to the leaf page containing the row `customer_id = 105`. Because the leaf page already holds the entire row, no additional lookup into another index is required to fetch the remaining columns.

### How is the clustered key chosen?

InnoDB rules:

1. Use the primary key if the table defines a primary key.
2. If there is no primary key, choose the first unique index where all key columns are `NOT NULL`.
3. If no suitable key exists, generate a 6-byte hidden row ID and a hidden clustered index.

Therefore, the clustered index is not always a single column named `id`; it can be a composite primary key or a suitable unique key. When designing new tables, explicitly declare a primary key to identify rows and control the clustered key.

## 5. Secondary index: two-step lookup

A secondary index is a B+tree independent of the clustered index. Leaf pages of a secondary index store the indexed column values and the clustered key used to locate the row in the clustered index.

Example creating an index on email:

```sql
CREATE UNIQUE INDEX uq_customers_email
ON customers (email);
```

Query:

```sql
SELECT customer_id, full_name, city
FROM customers
WHERE email = 'linh@example.test';
```

Typical path:

```text
1. Find email in the secondary B+tree
              |
              v
2. Get customer_id from the secondary leaf entry
              |
              v
3. Find customer_id in the clustered B+tree
              |
              v
4. Read the full row from the clustered leaf page
```

This is commonly called a secondary-to-clustered lookup or double lookup. The second step can incur extra page accesses if the clustered page is not already in the buffer pool.

If the primary key has multiple columns, the secondary index must carry the clustered key components needed to locate the row. If a primary key component is already included in the secondary key, InnoDB does not need to store that component redundantly in the entry.

### Secondary indexes are not fixed physical pointers

A secondary index stores the clustered key, not a fixed physical address of the row. When a clustered record moves because page organization changes, the engine can still locate the row via the clustered key. This helps indexes remain valid when B+trees rebalance and pages are reorganized.

## 6. Covering index: when clustered index lookup is not needed

A query can be served entirely from a secondary index if every column needed for filtering, sorting, and returning is present in the index entry. That case is called a covering index.

Example creating an index:

```sql
CREATE INDEX idx_customers_city_created
ON customers (city, created_at);
```

Query:

```sql
SELECT city, created_at, customer_id
FROM customers
WHERE city = 'Da Nang'
ORDER BY created_at, customer_id;
```

The columns `city` and `created_at` are explicitly declared in the index; `customer_id` is the primary key, so InnoDB automatically appends it to the secondary index entry to locate the row. Therefore, the query can still be served completely from the index without redundantly declaring `customer_id` in the index column list. In `EXPLAIN`, a common indicator is `Using index` in the `Extra` column.

Compare with the query:

```sql
SELECT city, created_at, customer_id, full_name
FROM customers
WHERE city = 'Da Nang'
ORDER BY created_at, customer_id;
```

`full_name` is not in the index. If the secondary index is used, InnoDB needs to look up the clustered record to retrieve this column. The optimizer may still choose a table scan if it estimates that to be lower cost.

Do not add every column to an index just to create a covering index. Overly wide indexes increase storage size, reduce fan-out, and increase `INSERT`/`UPDATE`/`DELETE` costs. Balance the lookups saved against the cost of maintaining the index.

## 7. Equality lookups and range scans

### Equality lookup

An equality condition searches for a single value or a group of rows sharing the same key value:

```sql
SELECT customer_id, email
FROM customers
WHERE email = 'linh@example.test';
```

With a unique index on `email`, the optimizer can use a unique lookup to find at most one row. With a nonunique index, the same value can lead to multiple entries in leaf pages.

### Range scan

A range condition specifies an interval of keys:

```sql
SELECT customer_id, email, created_at
FROM customers
WHERE created_at >= '2026-01-01'
  AND created_at <  '2026-02-01'
ORDER BY created_at;
```

If there is a suitable index on `created_at`, MySQL can locate the first leaf page in the range and then scan consecutive entries until crossing the upper boundary. Leaf pages are linked in key order, so a range scan avoids re-traversing from the root for every entry.

A range scan can still be expensive if the interval covers most of the table or requires reading many columns not in the index. Having an index does not guarantee a query is always faster than a table scan.

### Prefix search and non-sargable conditions

With an index on strings, a prefix condition such as:

```sql
SELECT customer_id, email
FROM customers
WHERE email LIKE 'linh%';
```

can be converted into a range over values starting with `linh`, depending on collation and pattern form. Conversely, a pattern with a leading wildcard:

```sql
WHERE email LIKE '%@example.test'
```

does not provide a clear starting point on a standard B+tree.

Conditions wrapping a column in a function also commonly prevent standard range lookups:

```sql
-- Typically more index-friendly
WHERE created_at >= '2026-01-01'

-- May not use range access on the created_at index
WHERE DATE(created_at) = '2026-01-01'
```

If you need to search by an expression, consider an indexed generated column or a functional index appropriate for your MySQL version.

## 8. Composite indexes are sorted left-to-right

A composite index is an index consisting of multiple columns. Example:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (order_id)
) ENGINE=InnoDB;

CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at);

INSERT INTO orders (order_id, tenant_id, status, created_at, total_amount)
VALUES
    (1001, 10, 'PAID', '2026-01-03 09:00:00', 250.00),
    (1002, 10, 'NEW',  '2026-01-05 10:00:00', 120.00),
    (1003, 10, 'PAID', '2026-01-08 11:00:00', 450.00),
    (1004, 20, 'PAID', '2026-01-09 12:00:00',  90.00);
```

Entries are sorted in lexicographical order:

1. Compare `tenant_id` first.
2. If `tenant_id` is equal, compare `status`.
3. If the first two columns are equal, compare `created_at`.

Illustration:

```text
(tenant=1, status='NEW',     time=t1)
(tenant=1, status='NEW',     time=t2)
(tenant=1, status='PAID',    time=t1)
(tenant=2, status='NEW',     time=t1)
(tenant=2, status='SHIPPED', time=t3)
```

Because the first column is `tenant_id`, this index works well for queries starting with tenant, such as:

```sql
WHERE tenant_id = 10
```

or:

```sql
WHERE tenant_id = 10
  AND status = 'PAID'
```

and:

```sql
WHERE tenant_id = 10
  AND status = 'PAID'
  AND created_at >= '2026-01-01'
```

By the leftmost prefix rule, a query filtering only `status = 'PAID'` typically cannot use this index as an efficient contiguous range lookup because it does not constrain the leading column `tenant_id`. MySQL may consider alternative strategies such as index skip scan under certain conditions and versions, but you should not design your primary workload around that exception.

## 9. Equality prefix before range key

With composite index `(tenant_id, status, created_at)`, a typically effective query pattern is equality on leading columns followed by a range on the next column:

```sql
SELECT order_id, tenant_id, status, created_at
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at <  '2026-02-01';
```

The engine can locate the starting region at `(10, 'PAID', '2026-01-01')` and scan to the end boundary. Columns after the range column may still be checked via an index condition or filter, but generally cannot continue narrowing the same contiguous range the way an equality prefix does.

Index example:

```sql
-- Index idx_orders_tenant_status_created was created in the previous section.
-- Reuse that index to test equality prefix and range scan.
SHOW INDEX FROM orders;
```

When choosing column order, consider:

- Which columns are usually filtered by equality?
- Which columns are usually used in ranges?
- Does the query require `ORDER BY` on subsequent columns?
- Are the columns frequently filtered together?
- What are the distinct value counts and selectivity of each column?

Do not mechanically apply the rule "the highest-cardinality column always goes first." For composite indexes, the leftmost prefix and actual query patterns usually matter more than a single-column selectivity rule.

## 10. Indexes supporting ORDER BY and GROUP BY

An appropriately ordered index can allow MySQL to read data in the required order without performing a separate filesort step.

Example:

```sql
CREATE INDEX idx_orders_tenant_created
ON orders (tenant_id, created_at);

SELECT order_id, created_at
FROM orders
WHERE tenant_id = 10
ORDER BY created_at, order_id;
```

After fixing `tenant_id`, the remaining entries are sorted by `created_at`; `order_id` is the primary key and is automatically appended by InnoDB to the secondary index entry. The optimizer can leverage that ordering to return results ordered by `created_at, order_id`.

If reverse order is requested, MySQL can use a backward index scan when column order and sort direction align; descending indexes are also supported in MySQL 8.0. However, mixed ASC/DESC directions across multiple columns may require an index defined with matching directions to avoid sorting.

For `GROUP BY`, a matching index can help read values in the same group contiguously. However, having an index does not guarantee eliminating temporary tables or sorting; always inspect the execution plan and `Extra` in `EXPLAIN`.

## 11. Unique indexes and nonunique indexes in leaf pages

A unique index guarantees that no two entries share the same key value according to the index's comparison rules, accounting for `NULL` per MySQL semantics. A nonunique index allows multiple rows to share the same key value.

Example:

```sql
CREATE INDEX idx_customers_city
ON customers (city);
```

`uq_customers_email` was created in the secondary index section and can support unique lookups. `idx_customers_city` can return multiple customers in the same city; the engine traverses all matching entries in the leaf page range.

When many values are duplicated, the secondary index needs the clustered key to distinguish each row. Thus, two rows with the same `city` still have distinct entries thanks to the accompanying clustered key.

## 12. How B+trees change on INSERT, UPDATE, and DELETE

An index is not a read-only structure. Every `INSERT`, `DELETE`, and `UPDATE` that modifies indexed columns requires B+tree maintenance.

### INSERT

When inserting a new key, InnoDB finds the leaf page at the proper position and adds the index record. If the page has room, the record is inserted into that page. If the page is full, the engine may have to perform a page split, distribute records to a new page, and update parent levels as needed.

Inserting monotonically increasing keys tends to concentrate at the trailing end of the index; inserting randomly distributed keys can touch many different leaf pages and increase page splits or uneven page utilization.

### UPDATE

If an `UPDATE` modifies only unindexed columns, InnoDB mainly updates the clustered record. If it modifies an indexed column, the corresponding entry in the index must be updated; structurally, this can be equivalent to deleting the old entry and inserting a new entry.

### DELETE

`DELETE` marks/removes rows according to InnoDB's mechanism and updates related indexes. Space reclamation and reuse occur via purge and page management mechanisms; not every byte is immediately returned to the operating system after a `DELETE` statement.

Therefore, adding indexes benefits `SELECT` at the expense of write cost, storage space, and maintenance overhead. Only create an index when the workload has queries that need it.

## 13. Reading EXPLAIN to see whether a B+tree is used

`EXPLAIN` shows how the optimizer expects to access tables. Example:

```sql
EXPLAIN
SELECT customer_id, full_name, city
FROM customers
WHERE email = 'linh@example.test';
```

With a fixture containing only a few rows, the optimizer may choose a table scan because scanning a tiny table costs less than traversing an index. When evaluating indexes, use data with scale and distribution close to your real workload; do not assume an index must be chosen solely because a query has an equality condition.

Common columns to inspect:

| Column | Meaning |
|---|---|
| `type` | Access type, e.g., `const`, `eq_ref`, `ref`, `range`, `index`, `ALL`. |
| `possible_keys` | Indexes the optimizer considers as candidates. |
| `key` | Index actually chosen; `NULL` means no index was chosen. |
| `key_len` | Length of the key prefix used in the access path. |
| `rows` | Estimated number of rows to read. |
| `filtered` | Estimated percentage of rows remaining after filtering conditions. |
| `Extra` | Additional information such as `Using index`, `Using where`, `Using filesort`. |

Common access types:

- `const`: unique/primary key lookup with a constant, at most one row.
- `eq_ref`: unique lookup for each row combination from preceding tables in a `JOIN`.
- `ref`: lookup by a not-necessarily-unique index value.
- `range`: reading one or more key intervals.
- `index`: scanning the entire index tree.
- `ALL`: table scan.

Do not judge solely by looking at `type`. A `range` over a few hundred entries can be great; an `index` full index scan can still be expensive; `ALL` on a small table is sometimes cheaper than many random lookups.

### EXPLAIN ANALYZE

In MySQL 8.0.18 and later, `EXPLAIN ANALYZE` executes the query and provides actual iterator metrics:

```sql
EXPLAIN ANALYZE
SELECT customer_id, full_name, city
FROM customers
WHERE email = 'linh@example.test';
```

This command can consume as many resources as the real query. Run it on appropriate data and in a safe environment when the query might scan many rows.

## 14. When does the optimizer not choose an index?

The optimizer chooses an access path based on cost estimation. It may skip using an index when:

- The table is small and a table scan is cheaper.
- The condition returns most of the rows, making row-by-row index lookups expensive.
- A column has low selectivity and the index does not meaningfully reduce data read.
- The condition does not align with the leftmost prefix or fails to form a useful range.
- Data types, collations, or implicit conversions make the index difficult to use.
- Index statistics do not accurately reflect current data distribution.

For example, a `status` column has only two values, `ACTIVE` and `INACTIVE`. If 95% of rows are `ACTIVE`, a single-column index on `status` may not help much for queries fetching all `ACTIVE` rows. A composite index by tenant or time may be more useful if it fits the workload.

Do not force the optimizer to use an index just because the index exists. First check cardinality, statistics, actual row counts, and data read cost.

## 15. Index statistics and cardinality

The optimizer needs to estimate how many rows might match a value or range. Index statistics help estimate cardinality (number of distinct values) and data distribution.

Check with:

```sql
SHOW INDEX FROM customers;
```

The `Cardinality` column is an estimate of distinct values in the index prefix, not necessarily an exact figure. For composite indexes, cardinality is reported per key part/prefix.

You can request a statistics update:

```sql
ANALYZE TABLE customers;
```

After major data changes or significant distribution skew, stale statistics can cause the optimizer to pick suboptimal plans. `ANALYZE TABLE` updates statistics; consider its impact on a live system under load and follow operational policies.

## 16. Designing indexes from query patterns

A practical index design workflow:

1. Collect frequently executed queries and queries with high execution time or rows examined.
2. Identify columns used in `WHERE`, `JOIN`, `ORDER BY`, and `GROUP BY`.
3. Determine whether queries need equality, range, or prefix searches.
4. Group conditions that frequently appear together.
5. Design composite indexes following equality prefix, range, and required output order.
6. Evaluate covering potential if there is a clear benefit.
7. Run `EXPLAIN` before and after creating the index.
8. Measure actual timing and row counts with `EXPLAIN ANALYZE` or workload profiling tools.
9. Also evaluate index size and `INSERT`/`UPDATE`/`DELETE` overhead.
10. Drop redundant indexes only after verifying no queries or constraints depend on them.

Common workload example:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
  AND created_at >= '2026-01-01'
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
```

A candidate index might be:

```sql
CREATE INDEX idx_orders_tenant_status_created_order
ON orders (tenant_id, status, created_at);
```

This index places equality columns first, followed by the range/sort column. `order_id` is the primary key and is automatically carried in the secondary index entry, so it does not need to be declared again. Whether to append `total_amount` at the end of the index for covering depends on query frequency, index width, and write cost. Do not create a wide covering index just to avoid a single lookup if the benefit does not outweigh the cost.

## 17. Common mistakes

| Mistake | Consequence | How to fix |
|---|---|---|
| Thinking each index entry is a node | Misunderstanding B+tree and page read counts | One page holds multiple entries and child pointers. |
| Thinking clustered index only stores keys | Overlooking that leaf pages contain entire rows | Clustered leaves store the row data. |
| Thinking secondary index points to a fixed physical address | Misunderstanding how InnoDB locates rows | Secondary leaves carry the clustered key to look up the clustered tree. |
| Thinking having an index guarantees a fast query | Ignoring selectivity, range size, and random I/O | Measure with `EXPLAIN` and realistic data. |
| Ignoring leftmost prefix | Composite index fails to serve expected queries | Order columns by equality/range/order patterns. |
| Placing range column too early in a composite index | Subsequent columns may not narrow the range effectively | Consider equality prefix before range. |
| Wrapping indexed column in a function without checking access path | Index range lookup may not be used | Write sargable conditions or create a functional/generated-column index. |
| Selecting many columns outside a covering index | Triggers clustered lookups | Select only needed columns or evaluate a covering index. |
| Creating too many indexes | Slow `INSERT`/`UPDATE`/`DELETE` and wasted storage | Keep only indexes serving real workloads or constraints. |
| Treating cardinality as an exact number | Misjudging selectivity | Treat as an estimate and refresh statistics when needed. |
| Assuming leaf page order is `SELECT` order | Application relies on unguaranteed ordering | Always use `ORDER BY` on the outer query block. |

## 18. Practice exercises

### Exercise A — Observe clustered and secondary indexes

1. Create the `customers` table with primary key `customer_id`.
2. Create a unique secondary index on `email`.
3. Run `SELECT` by primary key and by email.
4. Draw the B+tree traversal path for each query.
5. Explain why lookup by email may require an additional clustered lookup.

### Exercise B — Composite index and leftmost prefix

1. Create index `(tenant_id, status, created_at)`.
2. Run a query filtering only on `tenant_id`.
3. Run a query filtering on `tenant_id` and `status`.
4. Run a query filtering only on `status`.
5. Use `EXPLAIN` to compare access paths and explain leftmost prefix.

### Exercise C — Equality and range

1. Create index `(tenant_id, status, created_at)`.
2. Run equality on the first two columns and range on `created_at`.
3. Replace the range condition with the `DATE(created_at)` function.
4. Compare `EXPLAIN` outputs and identify when index range lookup is affected.

### Exercise D — Covering index

1. Create index `(city, created_at)`.
2. `SELECT` only columns contained in the index.
3. `SELECT` with `full_name` added.
4. Observe `Extra`; explain why `customer_id` is already available via the primary key suffix while `full_name` still requires a clustered lookup.
5. Evaluate whether `full_name` should be added to the index.

### Exercise E — Measure index impact

1. Load test data that is sufficiently large with varied distribution.
2. Run the query before creating the index and record execution time and plan.
3. Create the candidate index and run again.
4. Run `ANALYZE TABLE` and inspect statistics.
5. Also measure `INSERT`/`UPDATE` cost to evaluate the trade-off.

You have completed this lesson when you can explain the root-to-leaf path, distinguish clustered vs. secondary lookups, predict whether a composite index fits a query's conditions, and verify the optimizer's choice with `EXPLAIN`.

## 19. Key principles to remember

- InnoDB organizes regular indexes as B+trees consisting of root, intermediate, and leaf pages.
- All leaf pages are at the same depth; leaf pages are linked in key order to support range scans.
- Pages are the unit of storage and caching; the default page size is typically 16 KiB but can be configured.
- Clustered index leaves hold full row data; secondary index leaves hold the secondary key and the clustered key to locate the row.
- Secondary index lookups may require an extra clustered index lookup; covering indexes can skip that step.
- Composite indexes are ordered left-to-right and follow the leftmost prefix rule.
- Equality prefix before range is typically a useful pattern for composite indexes.
- Indexes can support `ORDER BY`/`GROUP BY`, but you must verify the execution plan.
- `INSERT`/`UPDATE`/`DELETE` must maintain indexes; more indexes increase write cost and storage usage.
- The optimizer chooses indexes based on cost estimates; having an index does not mean it will always be used.
- `EXPLAIN`, `EXPLAIN ANALYZE`, `SHOW INDEX`, and `ANALYZE TABLE` help evaluate access paths and statistics.
- Do not infer result order from the B+tree; use `ORDER BY` when deterministic ordering is required.

By understanding B+tree structure and the path of each lookup type, you can design indexes around how data is stored and how queries execute. Combining leftmost prefix, covering indexes, statistics, and `EXPLAIN` will help you balance read speed with storage and write costs in MySQL.
