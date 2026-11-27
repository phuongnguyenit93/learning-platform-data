# Measuring Real Benefits, Table-Opening Overhead, and Partition Count

Partitioning splits a logical table into multiple physical partitions according to declared rules. This organization can help MySQL skip irrelevant data (partition pruning), manage data lifecycles, and drop an expired data region faster than deleting row by row. However, partitioning also increases metadata and structural management work. Having many partitions can increase table-opening overhead, query planning cost, file management overhead, and maintenance work.

This lesson belongs to the **Partitioning** section of MySQL. The goal is to measure whether partitioning improves your real workload, quantify table-opening overhead, and choose an appropriate partition count. You will compare partitioned vs. unpartitioned tables, read pruning plans, measure latency and I/O, monitor metadata, and evaluate limits and operational costs before deciding to deploy.

## 1. When Does Partitioning Deliver Benefits?

Partitioning helps when the partition split aligns with how the application queries or manages data. Common scenarios:

- Large event tables queried by time ranges; daily or monthly partitions can let queries read only the relevant intervals.
- Data with fixed retention periods; old partitions can be dropped or truncated under retention policies instead of deleting millions of rows.
- Maintenance tasks can be scoped to a single partition, such as periodic verification or data loading.
- Some workloads reduce pages read when partition pruning eliminates most partitions before accessing indexes.

Partitioning usually helps little if queries do not filter on the partition key, the table is not large enough for scan cost to matter, or existing indexes already satisfy the workload well. It also does not replace indexes. Each partition still needs indexes suited to queries.

For example, partitioning by `created_at` can fit monthly reports:

```sql
SELECT order_id, customer_id, total_amount
FROM orders
WHERE created_at >= '2026-03-01'
  AND created_at <  '2026-04-01';
```

The query can read only March's partition if the condition is compatible with the partitioning expression. If the application frequently looks up orders by `customer_id` without bounding `created_at`, MySQL may have to inspect all partitions.

## 2. Partition Pruning: Benefits Must Show Up in the Execution Plan

**Partition pruning** is the process by which the optimizer identifies which partitions can contain matching rows and eliminates the remaining partitions from the statement's access scope. This is the primary mechanism that yields query benefits from partitioning.

Suppose a table is partitioned monthly with `RANGE COLUMNS(created_at)`:

```sql
CREATE TABLE orders_by_month (
    order_id BIGINT NOT NULL,
    created_at DATETIME NOT NULL,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id, created_at),
    KEY ix_customer_created (customer_id, created_at),
    KEY ix_status_created (status, created_at)
) ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (created_at) (
    PARTITION p2026_01 VALUES LESS THAN ('2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN ('2026-03-01'),
    PARTITION p2026_03 VALUES LESS THAN ('2026-04-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
```

For InnoDB partitioned tables, every column used in the partitioning expression must appear in every unique key. That is why the example uses primary key `(order_id, created_at)` instead of a unique key with only `order_id`. This is a design constraint to account for before choosing the partition key.

Check which partitions are selected:

```sql
EXPLAIN PARTITIONS
SELECT order_id, customer_id, total_amount
FROM orders_by_month
WHERE created_at >= '2026-03-01'
  AND created_at <  '2026-04-01';
```

In the result, the `partitions` column shows which partitions the plan intends to access. More detail can be seen with:

```sql
EXPLAIN FORMAT = JSON
SELECT order_id, customer_id, total_amount
FROM orders_by_month
WHERE created_at >= '2026-03-01'
  AND created_at <  '2026-04-01';
```

If the condition spans multiple months, multiple partitions are listed. If the condition does not constrain the partition key, all partitions that could contain matching rows usually must be considered.

### Writing Conditions So Pruning Can Work

Prefer half-open range predicates on the partition key:

```sql
WHERE created_at >= '2026-03-01'
  AND created_at <  '2026-04-01'
```

Avoid wrapping the partition column inside a function unless necessary:

```sql
-- Can make pruning harder to recognize depending on expression and version
WHERE DATE(created_at) = '2026-03-15'
```

Range predicates both avoid time-boundary bugs and keep the partition column in a direct comparison form. Also avoid unnecessary casts or data type conversions that prevent the optimizer from resolving partition ranges.

Pruning is a per-query property. Having a partitioned table does not mean every query on that table reads only a single partition.

## 3. Partitioning Does Not Replace Indexes

Each partition of an InnoDB table has its own index structures. Indexes on a partitioned table are local per partition; MySQL does not provide a shared global index spanning all partitions.

Example:

```sql
SELECT order_id, total_amount
FROM orders_by_month
WHERE customer_id = 1001;
```

Without a predicate on `created_at`, MySQL may have to look up `customer_id = 1001` in indexes across many partitions. Index `ix_customer_created` remains helpful within each partition, yet the cost of opening and probing multiple B-trees can exceed a query needing only one partition.

Try adding a time predicate:

```sql
SELECT order_id, total_amount
FROM orders_by_month
WHERE customer_id = 1001
  AND created_at >= '2026-03-01'
  AND created_at <  '2026-04-01';
```

This query can combine time-based pruning with the `(customer_id, created_at)` index inside the selected partition. When designing, base choices on frequent query patterns rather than merely on which column can split partitions.

Key InnoDB constraints to remember:

- Every unique key, including the primary key, must contain all columns of the partitioning expression.
- User-defined InnoDB partitioned tables do not support foreign keys; nor can they be referenced by foreign keys from other tables.
- The partition key and partitioning expression types must align with query data types and comparisons.

These constraints can affect the data model and referential integrity. Verify compatibility before partitioning a table that participates in many foreign key relationships or requires global unique keys.

## 4. Measuring Performance Before and After Partitioning

You cannot conclude partitioning is better merely because a table has multiple partitions or smaller data files. You must measure on the same workload, same data, and equivalent configuration.

A reliable benchmarking process includes:

1. **Choose a representative workload.** Pick critical queries by frequency and cost, including partition-key queries, non-partition-key queries, joins, summary reports, and writes.
2. **Build two equivalent datasets.** One unpartitioned table and one partitioned table; keep column types, data, indexes, and statistics closely matched. If unique key constraints force different index designs, note that difference explicitly in the results.
3. **Warm up or control caches.** Never compare one query on a cold cache against another when all pages are already in the buffer pool.
4. **Run multiple iterations.** Record p50, p95, p99, throughput, and variance; avoid drawing conclusions from a single run.
5. **Measure resource usage.** Track CPU, I/O, rows examined, page reads, temporary tables, lock waits, and number of partitions accessed.
6. **Measure write and maintenance costs.** Test inserts, updates, bulk loads, adding partitions, dropping partitions, and table-opening time.
7. **Test at realistic concurrency.** One single-threaded query running faster does not guarantee higher throughput under multi-session load.

### Creating the Control Table

The unpartitioned control table should have matching column definitions and appropriate indexes. For a fair comparison, you can use the same composite primary key:

```sql
CREATE TABLE orders_unpartitioned (
    order_id BIGINT NOT NULL,
    created_at DATETIME NOT NULL,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id, created_at),
    KEY ix_customer_created (customer_id, created_at),
    KEY ix_status_created (status, created_at)
) ENGINE = InnoDB;
```

Load the exact same dataset into both tables. Refresh statistics after loading:

```sql
ANALYZE TABLE orders_unpartitioned, orders_by_month;
```

Never compare two datasets with different distributions. In particular, monthly row counts, status ratios, customer counts, and data skew can dramatically alter access path selection.

## 5. Measuring Each Query Group

A benchmark should group queries by how they interact with the partition key.

| Query group | Example predicate | What to measure |
| --- | --- | --- |
| Single partition | `created_at` within one month | Selected partitions, rows examined, latency, and page reads. |
| Multi-partition range | `created_at` spanning 6 months | Partitions opened/read, aggregation cost, and latency. |
| No partition key | Filtering only `customer_id` | Multi-partition index probe cost vs. unpartitioned table. |
| Broad data scan | No selective predicate | Cost of opening/reading many partitions, throughput, and I/O. |
| Writes | Inserts by time or random keys | Throughput, page splits, redo, index maintenance, and insert distribution. |
| Joins and aggregates | Join by customer, group by day/month | Join order, actual rows, temporary tables, and partition-opening cost. |

Example monthly query on both tables:

```sql
SELECT COUNT(*) AS order_count,
       SUM(total_amount) AS revenue
FROM orders_by_month
WHERE created_at >= '2026-03-01'
  AND created_at <  '2026-04-01'
  AND status = 'PAID';
```

Run the equivalent query on `orders_unpartitioned`. Use `EXPLAIN PARTITIONS` to confirm pruning, then use `EXPLAIN ANALYZE` to measure actual row counts and runtime:

```sql
EXPLAIN ANALYZE
SELECT COUNT(*) AS order_count,
       SUM(total_amount) AS revenue
FROM orders_by_month
WHERE created_at >= '2026-03-01'
  AND created_at <  '2026-04-01'
  AND status = 'PAID';
```

`EXPLAIN ANALYZE` executes the `SELECT` statement. Use it only on appropriate datasets and loads; never run large scan queries casually during peak production hours.

### Measuring Improvement

For each query, you can calculate percentage latency reduction:

\[
\text{Latency improvement} =
\frac{T_{\text{before}} - T_{\text{after}}}{T_{\text{before}}} \times 100\%
\]

If runtime drops from 800 ms to 500 ms, latency improvement is 37.5%. Still, compare throughput and tail latency too; partitioning can speed up one query group while slowing down queries lacking the partition key.

Evaluate the overall workload using weights. For instance, if monthly queries represent 70% of traffic and speed up substantially while non-partition-key point lookups represent 30% and slow down, compute total cost weighted by actual frequency instead of cherry-picking the best result.

## 6. Measuring with Performance Schema and sys Schema

Performance Schema stores statement execution statistics grouped by digest. You can inspect time-consuming or row-heavy queries:

```sql
SELECT
    DIGEST_TEXT,
    COUNT_STAR,
    ROUND(AVG_TIMER_WAIT / 1000000000000, 6) AS avg_seconds,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT,
    SUM_CREATED_TMP_TABLES,
    SUM_NO_INDEX_USED
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST_TEXT IS NOT NULL
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
```

Timers in Performance Schema are expressed in picoseconds in the corresponding fields; the division above converts `AVG_TIMER_WAIT` to seconds. Verify that Performance Schema is enabled and the required consumers/instruments are collecting data.

To inspect per-table I/O wait times:

```sql
SELECT
    OBJECT_SCHEMA,
    OBJECT_NAME,
    COUNT_READ,
    SUM_TIMER_READ,
    COUNT_WRITE,
    SUM_TIMER_WRITE
FROM performance_schema.table_io_waits_summary_by_table
WHERE OBJECT_SCHEMA = DATABASE()
  AND OBJECT_NAME IN ('orders_unpartitioned', 'orders_by_month')
ORDER BY OBJECT_NAME;
```

These counters are cumulative since statistics were initialized or reset. Snapshot values before and after a benchmark interval and compute deltas; never compare cumulative totals directly between two tables with different load histories.

You can use the `sys.statement_analysis` view for a more readable summary, depending on sys schema configuration. When evaluating p95/p99, collect per-execution latencies or use a query monitoring system; digest averages do not replace percentiles.

## 7. Measuring Table-Opening and Metadata Overhead

A partitioned table remains one logical table object, yet the server and storage engine must manage partition definitions, metadata, indexes, and related resources. As partition count grows, opening/initializing required partitions, processing metadata, and planning can cost more. The increase depends on MySQL version, partition type, number of accessed partitions, and query patterns.

Monitor cache variables and file limits:

```sql
SHOW VARIABLES WHERE Variable_name IN (
    'table_open_cache',
    'table_definition_cache',
    'open_files_limit'
);
```

Monitor table-opening status:

```sql
SHOW GLOBAL STATUS WHERE Variable_name IN (
    'Open_tables',
    'Opened_tables',
    'Opened_table_definitions',
    'Open_table_definitions'
);
```

`Opened_tables` and `Opened_table_definitions` are cumulative counters; capture deltas over time and compare under identical load conditions. `Open_tables` and `Open_table_definitions` show how many objects are currently open at inspection time. These metrics do not directly measure per-partition opening latency, yet help detect cache pressure and churn.

### Table-Opening Overhead Experiment

To measure the impact of partition count:

1. Create lab tables with identical schemas and data, varying only partition counts—for example, 12, 60, 240, and 1,200.
2. Keep queries, indexes, MySQL configuration, and total data volume constant.
3. Run queries touching one partition, queries touching multiple partitions, and queries unable to prune.
4. Measure first-run latency after cleanly reopening connections, then measure repeated runs with warm caches.
5. Record latency, partition count in EXPLAIN, cumulative opened table counters, file descriptors, and memory if observable.
6. Repeat at representative concurrency and inspect p95/p99.

Do not rely on a single `Opened_tables` number to claim partitioning slows down table opening. Combine cache metrics, measured execution times, and execution plans. Likewise, raising `table_open_cache` only helps if the cache is the bottleneck; it does not eliminate metadata overhead from an over-partitioned design.

## 8. Partition Count and Scale-Related Costs

There is no universally optimal partition count for every system. Partition count should derive from:

- Total data size and growth rate.
- Time windows commonly read by queries.
- Retention granularity: whether data must be dropped daily, weekly, monthly, or quarterly.
- Number of partitions each query typically accesses.
- Table-opening, planning, metadata, file, and maintenance costs.
- MySQL version and storage engine limits.

MySQL 8.0 supports at most **8,192 partitions per table**, including subpartitions. This is a technical limit, not a recommendation to approach it. Much smaller partition counts can still cause noticeable overhead if every query must inspect most partitions.

Example for 10 years of retained data:

| Granularity | Approximate partitions | Notes |
| --- | ---: | --- |
| Yearly | 10 | Minimal metadata, but retention and fine-grained pruning can be coarse. |
| Quarterly | 40 | Balanced for quarterly querying and retention workloads. |
| Monthly | 120 | Typically fits monthly reporting and monthly retention. |
| Daily | 3,650 | Fine-grained pruning, but partition count and operational overhead rise significantly. |

This example merely illustrates granularity; real choices must reflect query mix and retention policies. If queries mainly read the last 30 days, monthly partitions may open only 1–2 partitions. If strict daily purging is required, daily partitions may be justified despite higher overhead.

### What Can Too Many Partitions Cause?

- Larger partition metadata and extra work when opening tables, checking partitions, or planning queries.
- More local index structures requiring maintenance and statistics updates.
- More files or tablespaces in corresponding storage layouts, raising filesystem and file descriptor demands.
- More complex partition management DDL; adding, dropping, or reorganizing partitions can become time-consuming.
- Non-prunable queries may touch huge numbers of partitions, eroding the benefit of splitting.
- Backup, restore, schema migration, and monitoring tools must process larger partition structures.

A large partition count does not automatically mean poor performance. If the workload consistently prunes down to a single partition and management overhead remains low, the setup can work well. Measure in practice rather than relying solely on numeric thresholds.

## 9. Inspecting Size and Data Distribution by Partition

`INFORMATION_SCHEMA.PARTITIONS` provides per-partition metadata:

```sql
SELECT
    PARTITION_NAME,
    PARTITION_ORDINAL_POSITION,
    PARTITION_METHOD,
    PARTITION_EXPRESSION,
    TABLE_ROWS,
    DATA_LENGTH,
    INDEX_LENGTH,
    DATA_FREE
FROM information_schema.PARTITIONS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders_by_month'
ORDER BY PARTITION_ORDINAL_POSITION;
```

With InnoDB, `TABLE_ROWS` is an estimate, not an exact row count. `DATA_LENGTH`, `INDEX_LENGTH`, and `DATA_FREE` are storage statistic figures; do not treat them as exact business-data byte counts. Combine them with filesystem metrics, Performance Schema, and monitoring tools to spot partitions growing abnormally.

Check total partition count:

```sql
SELECT COUNT(*) AS partition_count
FROM information_schema.PARTITIONS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders_by_month'
  AND PARTITION_NAME IS NOT NULL;
```

Check total estimated storage:

```sql
SELECT
    SUM(DATA_LENGTH) AS data_bytes,
    SUM(INDEX_LENGTH) AS index_bytes,
    SUM(DATA_FREE) AS free_bytes
FROM information_schema.PARTITIONS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders_by_month';
```

Figures may require refreshing statistics via `ANALYZE TABLE`. Running analyze also has a cost and can shift plans; follow appropriate operational procedures.

## 10. Write Overhead and Partition Management

On insert, MySQL must determine the target partition from the partitioning expression and then update that partition's local indexes. If data arrives chronologically and the partition key increases monotonically, inserts can concentrate in the newest partition. If the application writes backdated rows or timestamps are scattered, many partitions may receive concurrent writes.

Partitioning can increase write overhead if:

- Each statement must maintain many local indexes.
- The partition key does not match insertion order, leading to scattered inserts/updates.
- Many partitions create extra metadata and resource open/close churn.
- Queries fail to prune and probe many local indexes.

Partitioning can also lower retention cost. For example, dropping an expired monthly partition can be faster than deleting rows one by one for that period:

```sql
ALTER TABLE orders_by_month
DROP PARTITION p2026_01;
```

This statement deletes all data in partition `p2026_01` and cannot be rolled back like ordinary DML. Run it only after confirming retention rules, backups, and the target partition name. Never run this example on a real table without verifying the data first.

If you need to keep partition `pmax` while adding a new month, reorganize the final partition:

```sql
ALTER TABLE orders_by_month
REORGANIZE PARTITION pmax INTO (
    PARTITION p2026_04 VALUES LESS THAN ('2026-05-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
```

`REORGANIZE PARTITION` may have to move rows residing in the reorganized partition; runtime and locking depend on table structure, version, and data volume. Test on a production-scale clone and provision temporary disk space.

## 11. Building a Decision Matrix

Before finalizing partition count, build a measurement table for each query pattern:

| Metric | Unpartitioned table | Few partitions | Many partitions |
| --- | --- | --- | --- |
| p50/p95/p99 latency | Measure on real workload | Measure on same workload | Measure on same workload |
| Rows examined | EXPLAIN ANALYZE / digest | Same queries | Same queries |
| Partitions accessed | Not applicable | EXPLAIN PARTITIONS | EXPLAIN PARTITIONS |
| Write throughput | Measure at same insert rate | Measure at same insert rate | Measure at same insert rate |
| Opened table counters | Delta over same interval | Delta over same interval | Delta over same interval |
| CPU and I/O | Same load | Same load | Same load |
| Retention cost | Delete or archive | Drop/truncate partition if aligned | Drop/truncate partition if aligned |
| Operational complexity | Existing index/schema count | Partition count and pre-creation schedule | Higher metadata, file, and maintenance load |

Choose the option with the lower overall cost for your workload and data policy. An option that makes reporting queries 30% faster yet doubles p95 point-lookup latency may be wrong if point lookups make up most transactions.

## 12. Deployment and Post-Deployment Monitoring Workflow

1. Collect query digests, frequencies, latencies, rows examined, and current table size.
2. Choose the partition key from query patterns and retention, not merely from a high-cardinality column.
3. Verify unique keys, foreign keys, and InnoDB partitioning constraints.
4. Create a test clone, load data with production-like distribution, and refresh statistics.
5. Run benchmarks controlling cache state, concurrency, query mix, and sufficient duration.
6. Confirm pruning via EXPLAIN and compare actual rows via EXPLAIN ANALYZE.
7. Measure table-opening cost, caches, file descriptors, metadata, and retention operations.
8. Deploy with a migration plan that includes backups, rollback/restore procedures, and post-change monitoring.
9. Schedule future partition creation, monitor any `MAXVALUE` partition if used, and alert on abnormal partition count or storage growth.

Periodically review your query mix. If the application begins querying along different columns or retention rules shift, the value of the old partition key may fade. Partitioning is a long-term operational commitment, not a set-and-forget configuration.

## 13. Common Evaluation Mistakes

- **Measuring only prunable queries.** Also measure queries lacking the partition key because they may inspect every partition.
- **Comparing two different datasets.** Data distribution alters statistics, selectivity, and execution plans.
- **Looking only at average latency.** p95/p99 and throughput reveal the real impact under concurrent load.
- **Assuming more partitions are always better.** Overly small partitions can raise metadata and table-opening costs without commensurate gains.
- **Treating partitions as a replacement for indexes.** Every partition still needs appropriate indexes; without pruning, many local indexes may be probed.
- **Using `DATE(column)` and assuming pruning is guaranteed.** Inspect the execution plan and prefer direct range predicates.
- **Reading `TABLE_ROWS` as an exact count.** InnoDB statistics are estimates and must be interpreted accordingly.
- **Running DROP PARTITION without verification.** This deletes data permanently; confirm the exact partition and backups before running.

## 14. Self-Check Exercises

1. Through what mechanism does partitioning reduce the amount of data read?
2. Why might a query filtering only `customer_id` access every partition if the table is partitioned by `created_at`?
3. How do you confirm partition pruning using `EXPLAIN PARTITIONS`?
4. Why does partitioning not replace secondary indexes?
5. State the unique key and foreign key constraints to check before partitioning an InnoDB table.
6. Design a benchmark comparing a regular table to a monthly partitioned table; which variables must be held constant?
7. What do `Opened_tables` and `Opened_table_definitions` help observe? Why measure deltas?
8. Compare 120 monthly partitions against 3,650 daily partitions for 10 years of data.
9. Why is `TABLE_ROWS` in `INFORMATION_SCHEMA.PARTITIONS` not an exact row count?
10. When is `DROP PARTITION` advantageous over `DELETE`, and what are the data risks?

Partitioning decisions should follow the chain **query mix → partition pruning → actual rows and pages read → latency/throughput → table-opening and metadata overhead → write, retention, and maintenance costs**. Only when total measured benefits outweigh operational costs are the partition count and granularity justified.
