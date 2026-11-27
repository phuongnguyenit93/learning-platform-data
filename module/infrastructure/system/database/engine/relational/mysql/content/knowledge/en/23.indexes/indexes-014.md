# Indexes

## Maintenance Costs on INSERT/UPDATE/DELETE and Avoiding Redundancy

Indexes help MySQL find rows, join tables, and sort data faster, yet every index is also a B-tree structure that must be maintained whenever data changes. An `INSERT` statement may have to add entries to the clustered index and every secondary index; an `UPDATE` may have to update entries if indexed key columns change; a `DELETE` must mark/delete corresponding entries and let InnoDB purge old versions when safe. Therefore, indexes are not free: the more indexes you have, the greater the write cost, storage footprint, buffer pool pressure, and maintenance work.

The design goal is to retain indexes with measurable query benefits while eliminating duplicate or low-value indexes. This must be grounded in actual workload, foreign key constraints, execution plans, and index usage metrics; never drop an index solely because its name or definition resembles another index.

### 1. Every index is a B-tree that must be maintained

InnoDB stores table data inside the clustered index. Each secondary index has its own B-tree, with leaf entries containing the indexed columns and the primary key to locate the row in the clustered index. Whenever data changes, InnoDB must keep all related structures consistent.

Example:

```sql
CREATE TABLE orders (
    id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_customer (customer_id),
    KEY idx_status (status),
    KEY idx_created (created_at)
) ENGINE = InnoDB;
```

A new row is not merely written into the clustered index by `id`. InnoDB must also insert entries into `idx_customer`, `idx_status`, and `idx_created`. As the number of indexes grows, each insert can trigger additional position searches, page modifications, redo/undo logging, and potential page splits.

Indexes also consume buffer pool pages and tablespace disk space. Larger indexes mean a larger working set; a write-heavy workload can evict other useful pages from the buffer pool and raise I/O. The cost does not lie solely in the duration of the write statement itself.

### 2. Cost of INSERT

For every row inserted into InnoDB:

1. InnoDB inserts the record into a clustered index leaf page in primary key order.
2. For each secondary index, InnoDB creates an entry containing the key-part values and the primary key.
3. Affected pages are modified in the buffer pool and necessary redo/undo records are generated.
4. If a page lacks room, the B-tree may reorganize pages or perform a page split.
5. On commit, required logs are processed according to durability policies; dirty data pages may be flushed later.

If a table has 1 clustered index and 8 secondary indexes, one insert can touch up to 9 index structures. That does not mean it always performs 9 synchronous disk writes: many changes stay in the buffer pool, group commit, and background flushing batches I/O. Still, every related index must be logically updated.

Inserting in increasing clustered key order generally achieves better locality than random keys, because new rows append near the end of the B-tree. Random keys can scatter inserts across many pages, increasing page splits and page reads. Secondary indexes also exhibit their own write distribution depending on their key values.

### 3. Cost of UPDATE

Not every `UPDATE` modifies every secondary index. InnoDB only needs to update indexes affected by changed key values, alongside the clustered record and related structures.

| Type of `UPDATE` | Typical index work required |
| --- | --- |
| Modifying unindexed columns, primary key unchanged | Modifies clustered record; secondary indexes without those columns normally do not change entries |
| Modifying a column belonging to a secondary index | Replaces old entry with new entry in that index; clustered record also changes |
| Modifying the primary key | Moves clustered record position and updates locator key across secondary indexes |
| Modifying multiple columns across multiple indexes | Updates all indexes with affected key parts |

Example:

```sql
-- total does not belong to any index in the first example.
UPDATE orders
SET total = total + 10
WHERE id = 1001;

-- status belongs to idx_status so the secondary index entry must change.
UPDATE orders
SET status = 'shipped'
WHERE id = 1001;
```

Updating an unindexed column still modifies the clustered record and generates logs; it is not free. However, it typically avoids modifying every secondary index. Conversely, if an indexed column changes, InnoDB must preserve B-tree order and update entry placement to match the new value.

The primary key is especially critical because primary key values are stored inside secondary indexes to locate clustered records. Changing a primary key can cascade entry updates across every secondary index. This is one reason to choose a stable primary key that rarely changes.

### 4. Cost of DELETE and purge

When deleting a row, InnoDB delete-marks the record in the clustered index and corresponding secondary indexes. Undo logs retain information required for rollbacks and consistent reads. Once no active transaction/read view needs the old version, purge threads can remove delete-marked entries and reclaim space for reuse.

Therefore, `DELETE` does not mean every byte of the row and index immediately disappears from files. A long-running transaction can hold an old read view open, preventing purge from cleaning older versions. During bulk deletes, monitor history list length, undo tablespaces, transaction duration, and purge I/O.

Each extra secondary index also has entries that must be handled on deletion. If a table has many wide indexes, deletes can create additional undo/redo work, page modifications, and purge overhead.

### 5. Wide indexes increase costs in multiple places

Index size depends on row count, data types, key-part widths, attached primary keys, page structure, and fill factor. A wide index increases:

- Tablespace size and backup/restore overhead.
- Number of pages needed in the buffer pool for good cache hit rates.
- Bytes read and written during inserts, updates, and deletes.
- Index rebuild cost and DDL duration.
- Likelihood of page splits, page reads, and random I/O under scattered workloads.

For example, a secondary index on `VARCHAR(200)` can be substantially larger than an index on an `INT`, especially with many rows and multi-byte charsets. If the primary key is a long string, the primary key value stored inside every secondary index widens each entry as well.

Do not mechanically add all query columns into a covering index. A covering index can eliminate clustered record lookups for a read query, yet a wide index increases write cost on every row and consumes more buffer pool memory. Weigh read gains against write frequency and actual row counts.

### 6. Duplicate indexes and redundant indexes

Two common concepts:

- **Duplicate indexes:** two indexes sharing the same set of key parts, in the same order and direction, differing only in name or attributes that do not change access purpose.
- **Redundant indexes:** an index that can be replaced for most access needs by another index because it is a compatible leftmost prefix. For instance, index `(customer_id, created_at)` can serve lookups on `customer_id`, making a standalone `(customer_id)` index potentially redundant.

Example:

```sql
CREATE TABLE customer_order (
    id BIGINT NOT NULL PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    created_at DATETIME NOT NULL,
    status VARCHAR(20) NOT NULL,
    KEY idx_customer (customer_id),
    KEY idx_customer_created (customer_id, created_at),
    KEY idx_status (status)
) ENGINE = InnoDB;
```

`idx_customer_created` can be used for queries filtering solely on `customer_id` via its leftmost prefix. Thus `idx_customer` is a removal candidate to inspect. However, the shorter index can be smaller, cache better, or perform better for specific workloads; compare plans and metrics before dropping it.

An index is not automatically redundant merely because its columns appear in another index. Key-part order, `ASC`/`DESC` direction, prefix length, collation, index type, and query predicates all affect substitutability.

### 7. Why leftmost prefix is not an automatic index-deletion rule

With index `(a, b)`, MySQL can generally use the leading `(a)` prefix for lookups. However, index `(a, b)` is not equivalent to index `(b)` because it is not globally ordered by `b`. Similarly, index `(a, b, c)` can serve queries on `(a)` or `(a, b)`, yet does not automatically replace index `(a, c)` for all queries.

Example:

```sql
-- Can use the leftmost prefix of (customer_id, created_at).
SELECT *
FROM customer_order
WHERE customer_id = 42;

-- Cannot use global ordering by created_at from index (customer_id, created_at)
-- if customer_id is not fixed.
SELECT *
FROM customer_order
ORDER BY created_at DESC;
```

Index `(customer_id, created_at)` is ordered by `customer_id` first. Rows across multiple customers are not globally ordered by `created_at` just by scanning that index.

Additionally, an index with a prefix length—such as `name(20)`—stores only part of the string value; it does not necessarily replace a full index for every comparison or sort. Unique indexes, descending indexes, functional indexes, and foreign-key supporting indexes also require individual assessment.

### 8. Foreign keys and supporting indexes

InnoDB requires referenced columns in a foreign key to have a suitable index; on the child table, MySQL can automatically create an index on foreign key columns if no suitable index exists. If you later add another index sharing the same leading columns and satisfying the constraint, verify whether the MySQL-generated index is still needed before removing it.

Example:

```sql
CREATE TABLE customers (
    id BIGINT NOT NULL PRIMARY KEY,
    name VARCHAR(100) NOT NULL
) ENGINE = InnoDB;

CREATE TABLE orders (
    id BIGINT NOT NULL PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    created_at DATETIME NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
) ENGINE = InnoDB;
```

An index on `orders.customer_id` supports checking and locating child rows during parent-row changes, while also supporting joins from `orders` to `customers`. Never drop the sole index satisfying a foreign key without an eligible replacement index; MySQL may reject the drop or automatically recreate a required index depending on the case.

### 9. Finding redundant indexes using metadata

Start by listing indexes and key parts:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    INDEX_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    SUB_PART,
    COLLATION,
    INDEX_TYPE
FROM information_schema.statistics
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX;
```

Inspect indexes on the same table sharing identical key-part sequences or shorter indexes that are prefixes of longer ones. Also check `SHOW CREATE TABLE` to confirm unique constraints, foreign keys, and other properties:

```sql
SHOW CREATE TABLE orders;
SHOW INDEX FROM orders;
```

MySQL Shell and the `sys` schema provide tools/views to assist index analysis. If `sys.schema_redundant_indexes` is available, you can inspect candidate lists:

```sql
SELECT *
FROM sys.schema_redundant_indexes
WHERE table_schema = DATABASE();
```

This view offers suggestions based on index structure, not an instruction to auto-drop. You must verify differences in uniqueness, foreign keys, prefixes, collations, directions, workload, and version compatibility.

### 10. Checking whether an index is actually used

`sys.schema_index_statistics` aggregates index access counts via Performance Schema when instrumentation and statistics data are enabled:

```sql
SELECT
    table_schema,
    table_name,
    index_name,
    rows_selected,
    rows_inserted,
    rows_updated,
    rows_deleted
FROM sys.schema_index_statistics
WHERE table_schema = DATABASE()
ORDER BY table_name, index_name;
```

View/column names and output can vary by version. Counters typically accumulate since server startup or the last statistics reset; restarts, resets, or instrumentation changes discard history. An index with low read counts over a short observation window is not necessarily useless: it may serve month-end queries, rare reports, migrations, constraints, or incident tasks.

Combine multiple sources:

- `performance_schema` and `sys` to observe access activity over a monitored period.
- Slow query logs and digests to identify expensive or frequent queries.
- `EXPLAIN` to check which index the optimizer picks for specific queries.
- Business schedules to identify seasonal, period-end, backup, audit, or batch queries.
- Foreign key/unique metadata to ensure the index is not enforcing a constraint.

### 11. Invisible indexes for testing before dropping

MySQL 8.0 supports invisible indexes. The index is still maintained as data changes, yet the optimizer excludes it from query plans by default. Thus, you can use invisible indexes to test the effect of removing an index from optimizer consideration prior to physically dropping it.

Example:

```sql
ALTER TABLE customer_order
ALTER INDEX idx_customer INVISIBLE;
```

Then run test workloads, watching slow queries, latency, and execution plans. You can force a test session to consider invisible indexes by enabling:

```sql
SET SESSION optimizer_switch = 'use_invisible_indexes=on';
```

If an important query slows down, restore index usability:

```sql
ALTER TABLE customer_order
ALTER INDEX idx_customer VISIBLE;
```

Only after confirming the index is unnecessary and all constraints are satisfied should you consider dropping it:

```sql
ALTER TABLE customer_order
DROP INDEX idx_customer;
```

Invisible indexes **do not eliminate write costs or storage**: InnoDB still updates and stores the index. They only test optimizer impact. Write maintenance overhead disappears only after dropping the index. Changing visibility is DDL, so account for metadata locks and version-specific behavior.

### 12. Safe index removal workflow

1. **Snapshot current state:** save `SHOW CREATE TABLE`, index lists, foreign keys, and key queries.
2. **Observe a full workload cycle:** cover peak hours, batch jobs, period-end reports, and scheduled tasks.
3. **Identify candidates:** duplicate or redundant indexes by key parts, noting any differences in uniqueness, prefix, direction, and collation.
4. **Check dependencies:** verify foreign keys, unique constraints, `ORDER BY`, `GROUP BY`, joins, and DML statements using the index.
5. **Test invisibility:** switch the index to invisible in an appropriate environment, measure latency, and monitor errors or bad plans.
6. **Restore if needed:** immediately revert to visible if any critical query degrades.
7. **Drop in a planned window:** once confirmed, drop the index during a suitable window; assess metadata locks, I/O, and replication lag.
8. **Re-measure:** compare write throughput, index size, buffer pool usage, query latency, and execution plans post-change.

Do not drop multiple indexes at once unless you can isolate which index caused any regression. Changing one candidate at a time simplifies attribution and rollback.

### 13. Example evaluating an index set for a workload

Suppose a system runs these main queries:

```sql
-- Q1: retrieve a customer's most recent orders.
SELECT id, created_at, total
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 50;

-- Q2: filter orders by status.
SELECT id, created_at
FROM orders
WHERE status = 'pending';

-- Q3: look up an order by primary key.
SELECT *
FROM orders
WHERE id = 1001;
```

An initial index set might be:

```sql
PRIMARY KEY (id)
KEY idx_customer (customer_id)
KEY idx_customer_created (customer_id, created_at)
KEY idx_status (status)
```

`idx_customer` is a redundancy candidate because `idx_customer_created` has leftmost prefix `customer_id`. Q1 can use the wider index and Q2 uses `idx_status`; Q3 uses the clustered primary key. Before dropping `idx_customer`, check whether the shorter index is used for its smaller size, constraints, or another workload. Then test invisibility, compare `EXPLAIN` and latency, and decide.

If Q1 needs newest-first ordering, you can evaluate index direction:

```sql
CREATE INDEX idx_customer_created_desc
ON orders (customer_id ASC, created_at DESC);
```

However, do not simultaneously keep `(customer_id)`, `(customer_id, created_at)`, and `(customer_id, created_at DESC)` without verifying which are needed. Every additional index is maintained for every relevant change.

### 14. When should you keep a seemingly rarely used index?

An index with low read counts may still be essential:

- It is a unique index enforcing data uniqueness.
- It supports a foreign key or referential integrity check.
- It serves a rare query with strict latency requirements.
- It is used in batch jobs, reports, migrations, reconciliation, or operational incidents.
- It is used only under specific data distributions or when a particular filter condition appears.

Do not treat `rows_selected = 0` over a brief window as sufficient proof to delete an index. Index usage metrics must be gathered over a representative cycle and cross-referenced against business requirements.

### 15. Responsible index design checklist

1. Every index must correspond to a specific query, constraint, or operational requirement.
2. Assess `INSERT`/`UPDATE`/`DELETE` overhead before adding an index.
3. Prefer short, stable primary keys because they appear inside secondary indexes.
4. Check leftmost prefixes, duplicates, and redundant indexes before creating a new index.
5. Consider index width, prefix length, collation, and `ASC`/`DESC` direction.
6. Do not widen a covering index if read benefits fail to outweigh write and memory costs.
7. Check foreign keys and unique constraints before dropping an index.
8. Observe indexes across a full workload cycle and use invisible indexes to test impact when appropriate.
9. Change one index at a time, re-measuring query latency, write throughput, I/O, and storage.
10. Document why an index was kept or dropped so future maintenance does not recreate redundant indexes.

A good index helps the workload meet requirements at reasonable total cost. Fewer indexes are not automatically better, and more indexes do not guarantee faster queries. Good design balances read speed, write speed, storage, data constraints, and operability; measuring workloads and testing with invisible indexes enables controlled removal of redundant indexes.
