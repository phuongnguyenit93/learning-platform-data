# Table/Index Statistics and Related Metadata Sources

The MySQL optimizer does not read every row in a table to decide a plan for each query. It relies on metadata and statistics to estimate the number of rows to be read, predicate selectivity, index access cost, `JOIN` cost, and sort cost. If statistics do not accurately reflect current data, the optimizer may choose an inefficient plan even when appropriate indexes exist.

In MySQL, relevant information lives across multiple sources:

- Structural metadata in `INFORMATION_SCHEMA` and `SHOW` commands.
- InnoDB table and index statistics in `mysql.innodb_table_stats` and `mysql.innodb_index_stats`.
- Per-column histograms in `INFORMATION_SCHEMA.COLUMN_STATISTICS`.
- Actual runtime measurements in Performance Schema and `sys` schema views.
- Estimates and execution metrics in `EXPLAIN` and `EXPLAIN ANALYZE`.

These sources serve different purposes. `Cardinality` in `SHOW INDEX` is an estimate of distinct values; InnoDB's `TABLE_ROWS` is also an estimate. They do not replace `COUNT(*)` or runtime metrics. This lesson explains how to read each source properly, update statistics, and use them to diagnose query plans.

## 1. Why Does the Optimizer Need Statistics?

Suppose an `orders` table has several million rows and indexes:

~~~sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(14, 2) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer (customer_id),
    KEY idx_orders_status (status),
    KEY idx_orders_created (created_at)
) ENGINE = InnoDB;
~~~

The following two queries can have vastly different costs:

~~~sql
SELECT order_id
FROM orders
WHERE customer_id = 1001;

SELECT order_id
FROM orders
WHERE status = 'PENDING';
~~~

If `customer_id = 1001` matches only 20 rows, the customer index can be an excellent access path. If `status = 'PENDING'` matches 70% of the table, scanning the index and then reading rows can be more expensive than scanning the table or choosing another plan.

The optimizer needs to estimate:

- Total rows and number of data pages.
- Distinct value counts for columns or index prefixes.
- Fraction of rows matching predicates.
- Whether data distribution is uniform or skewed.
- Intermediate row counts after each `JOIN` step.
- Number of rows needing sorting, grouping, or materialization.
- Whether the query can be fully covered by an index.

Good statistics help the optimizer predict costs closer to reality. Stale or overly coarse statistics can cause the optimizer to misjudge selectivity and choose the wrong access path.

## 2. Distinguishing Structural Metadata, Optimizer Statistics, and Runtime Metrics

Not everything labeled "statistics" is the same kind of data.

| Category | Typical Sources | Information Provided | Used For |
|---|---|---|---|
| Structural metadata | SHOW CREATE TABLE, INFORMATION_SCHEMA.COLUMNS | Column types, NULLability, defaults, constraints | Understanding the schema |
| Index metadata | SHOW INDEX, INFORMATION_SCHEMA.STATISTICS | Index columns, ordering, uniqueness, estimated cardinality | Understanding indexes and selectivity |
| InnoDB statistics | mysql.innodb_table_stats, mysql.innodb_index_stats | Estimated row/page counts and distinct values | Optimizer cost estimation |
| Histograms | INFORMATION_SCHEMA.COLUMN_STATISTICS | Per-column value distribution | Estimating column predicates |
| Runtime metrics | Performance Schema, sys | Read/write counts, wait times, index usage | Observing real workloads |
| Query plan | EXPLAIN, EXPLAIN ANALYZE | Estimates and iterator metrics | Evaluating a specific query |

A single query analysis may require reading both metadata and runtime metrics. For example, `SHOW INDEX` shows that an index exists and its estimated cardinality; Performance Schema shows whether that index was actually used during the observation window.

## 3. Table Metadata in INFORMATION_SCHEMA.TABLES

`INFORMATION_SCHEMA.TABLES` provides metadata about tables along with size and row-count statistics.

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE,
    TABLE_ROWS,
    AVG_ROW_LENGTH,
    DATA_LENGTH,
    INDEX_LENGTH,
    DATA_FREE,
    CREATE_TIME,
    UPDATE_TIME
FROM information_schema.tables
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME;
~~~

Key columns of interest:

| Column | Meaning |
|---|---|
| TABLE_SCHEMA | Database containing the table |
| TABLE_NAME | Table name |
| ENGINE | Storage engine |
| TABLE_ROWS | Estimated row count for InnoDB |
| AVG_ROW_LENGTH | Estimated average row length |
| DATA_LENGTH | Data size; for InnoDB primarily reflects the clustered index |
| INDEX_LENGTH | Secondary index size reported by engine metadata |
| DATA_FREE | Reported free space in the tablespace |
| CREATE_TIME | Creation timestamp if provided by the engine |
| UPDATE_TIME | Metadata update timestamp if provided by the engine; not always populated or exact across all engines |

### 3.1. InnoDB TABLE_ROWS Is Not an Exact Count

For InnoDB, `TABLE_ROWS` is an estimate. The value can diverge noticeably from the actual row count, especially when data changes continuously or statistics have not been refreshed.

Do not use the following query to determine the exact record count:

~~~sql
SELECT TABLE_ROWS
FROM information_schema.tables
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders';
~~~

If you need the exact row count within the current transaction snapshot, use:

~~~sql
SELECT COUNT(*)
FROM orders;
~~~

`COUNT(*)` may need to scan an index and take time on large tables. InnoDB does not maintain a single exact row counter shared across all transactions because each transaction can see a different snapshot under MVCC.

### 3.2. DATA_LENGTH and INDEX_LENGTH Are Not Business Payload Bytes

For InnoDB, `DATA_LENGTH` typically reflects the clustered index size in pages; `INDEX_LENGTH` reflects secondary index size. This is storage allocation information, not the sum of user-entered data bytes.

These values depend on page size, row format, page fill factor, fragmentation, and how the engine reports them. Do not use them to calculate exact export or backup sizes.

### 3.3. SHOW TABLE STATUS

You can inspect quickly with:

~~~sql
SHOW TABLE STATUS LIKE 'orders';
~~~

The `Rows`, `Data_length`, `Index_length`, and `Data_free` fields must likewise be understood as engine metadata/estimates. For InnoDB, `Rows` is not an exact `COUNT(*)`.

## 4. Column and Table Structure Metadata

When statistics look abnormal, check the schema first. Differences in data types, collations, nullability, or generated expressions can affect predicates and indexes.

### 4.1. INFORMATION_SCHEMA.COLUMNS

~~~sql
SELECT
    COLUMN_NAME,
    ORDINAL_POSITION,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    CHARACTER_SET_NAME,
    COLLATION_NAME,
    EXTRA,
    GENERATION_EXPRESSION
FROM information_schema.columns
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders'
ORDER BY ORDINAL_POSITION;
~~~

This source reveals:
- Actual data type.
- Whether the column allows `NULL`.
- Character set and collation of string columns.
- `AUTO_INCREMENT` or generated attributes in `EXTRA`.
- Expression of a generated column, if any.

### 4.2. SHOW CREATE TABLE

~~~sql
SHOW CREATE TABLE orders;
~~~

This is a convenient way to inspect the full definition, including primary key, unique keys, secondary indexes, foreign keys, engine, and table options.

Index statistics are only meaningful when read alongside the index definition. For instance, the cardinality of the second prefix in a composite index must be interpreted according to actual column order.

## 5. Index Statistics via SHOW INDEX

`SHOW INDEX` lists a table's indexes and cardinality estimates.

~~~sql
SHOW INDEX FROM orders;
~~~

Important columns:

| Column | Meaning |
|---|---|
| Table | Table name |
| Non_unique | 0 if unique, 1 if non-unique |
| Key_name | Index name |
| Seq_in_index | Column position in the index, starting at 1 |
| Column_name | Indexed column; may be NULL for functional key parts |
| Collation | A/D sort order if applicable |
| Cardinality | Estimated number of distinct values for the index prefix |
| Sub_part | Prefix index length if applicable |
| Packed | Packing information if provided by the engine |
| Null | Whether the index column can contain NULL |
| Index_type | Index type, usually BTREE for InnoDB |
| Visible | Whether the index is visible to the optimizer |
| Expression | Expression if it is a functional index |

### 5.1. Cardinality Is an Estimate

Cardinality is not the table row count. It is an estimate of the number of distinct values in the corresponding column or index prefix.

Example index:

~~~sql
CREATE INDEX idx_orders_customer_status
ON orders (customer_id, status);
~~~

`SHOW INDEX` might show two rows:

| Seq_in_index | Column_name | Cardinality |
|---:|---|---:|
| 1 | customer_id | 100000 |
| 2 | status | 450000 |

The second row represents the estimated cardinality of the prefix consisting of `customer_id` and `status`, not `status` alone.

### 5.2. Cardinality Helps Assess Selectivity

Selectivity can be roughly pictured as:

~~~text
selectivity = number of distinct values / number of rows
~~~

For a single column:
- Cardinality close to row count: many distinct values; equality predicates can be highly selective.
- Low cardinality: many rows may share the same value.
- Cardinality of 1: the column has effectively a single value across the sampled data.

This is only an intuitive model. The selectivity of a specific predicate also depends on value distribution. A column with 100 distinct values does not mean each value appears in exactly 1% of rows.

### 5.3. Composite Indexes and Per-Prefix Cardinality

For index `(customer_id, status, created_at)`, cardinality applies to:
- Prefix 1: `customer_id`.
- Prefix 2: `customer_id + status`.
- Prefix 3: `customer_id + status + created_at`.

This information helps the optimizer estimate how selective each prefix is. It does not directly provide standalone cardinality for `status` or `created_at` if those columns do not lead a separate index.

### 5.4. INFORMATION_SCHEMA.STATISTICS

You can query the same metadata through `INFORMATION_SCHEMA`:

~~~sql
SELECT
    INDEX_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    COLLATION,
    CARDINALITY,
    SUB_PART,
    INDEX_TYPE,
    IS_VISIBLE,
    EXPRESSION
FROM information_schema.statistics
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
~~~

`CARDINALITY` here is also an estimate. Do not interpret it as a `COUNT(DISTINCT column)` result.

## 6. InnoDB Persistent Statistics

InnoDB can store table and index statistics persistently in two system tables:

- `mysql.innodb_table_stats`
- `mysql.innodb_index_stats`

When persistent statistics are enabled, statistics are saved and persist across server restarts. This is the common default configuration in MySQL 8.x.

### 6.1. Viewing mysql.innodb_table_stats

~~~sql
SELECT
    database_name,
    table_name,
    last_update,
    n_rows,
    clustered_index_size,
    sum_of_other_index_sizes
FROM mysql.innodb_table_stats
WHERE database_name = DATABASE()
  AND table_name = 'orders';
~~~

Fields:

| Field | Meaning |
|---|---|
| database_name | Schema |
| table_name | Table |
| last_update | Timestamp when statistics were updated |
| n_rows | Estimated row count |
| clustered_index_size | Page count of the clustered index |
| sum_of_other_index_sizes | Total page count of all other indexes |

`clustered_index_size` and `sum_of_other_index_sizes` are page counts, not bytes. You can multiply by `innodb_page_size` to approximate page allocation, though that remains page-allocation metadata rather than exact payload size.

~~~sql
SELECT @@GLOBAL.innodb_page_size;
~~~

### 6.2. Viewing mysql.innodb_index_stats

~~~sql
SELECT
    database_name,
    table_name,
    index_name,
    last_update,
    stat_name,
    stat_value,
    sample_size,
    stat_description
FROM mysql.innodb_index_stats
WHERE database_name = DATABASE()
  AND table_name = 'orders'
ORDER BY index_name, stat_name;
~~~

Common `stat_name` values:

| stat_name | Meaning |
|---|---|
| n_diff_pfxNN | Estimated distinct values for the prefix of NN index columns |
| n_leaf_pages | Estimated number of index leaf pages |
| size | Estimated total number of index pages |

`sample_size` indicates how many pages were sampled to estimate the corresponding statistic. `stat_description` describes the index prefix or property represented by the statistic.

### 6.3. Do Not Edit System Statistics Tables Directly

`mysql.innodb_table_stats` and `mysql.innodb_index_stats` are where InnoDB stores internal state. Use them for reading and diagnostics; do not manually `UPDATE`/`DELETE` them to force optimizer plans.

To update statistics, use `ANALYZE TABLE` and supported sampling settings. Modifying system tables directly can create inconsistent metadata or cause upgrade/recovery issues.

## 7. Persistent Statistics vs. Transient Statistics

InnoDB has two ways to maintain statistics.

### 7.1. Persistent Statistics

Persistent statistics are stored in system tables and survive restarts. This is the common default mode.

Benefits:
- More stable query plans across server restarts.
- Statistics can be proactively managed and updated.
- Avoids re-estimating all transient statistics every time a table is opened.

### 7.2. Transient Statistics

Transient statistics are not durably stored like persistent stats. InnoDB may recalculate them when opening a table or on demand, depending on configuration and engine activity.

Limitations:
- Statistics can change after a restart or when a table is reopened.
- Query plans can shift due to different data samples.
- Sampling can introduce variance between calculations.

### 7.3. Checking Configuration

~~~sql
SHOW GLOBAL VARIABLES LIKE 'innodb_stats_persistent';
SHOW GLOBAL VARIABLES LIKE 'innodb_stats_auto_recalc';
SHOW GLOBAL VARIABLES LIKE 'innodb_stats_persistent_sample_pages';
SHOW GLOBAL VARIABLES LIKE 'innodb_stats_transient_sample_pages';
~~~

Options can be set per table:

~~~sql
ALTER TABLE orders
    STATS_PERSISTENT = 1,
    STATS_AUTO_RECALC = 1,
    STATS_SAMPLE_PAGES = 64;
~~~

- `STATS_PERSISTENT = 1` enables persistent statistics for the table.
- `STATS_PERSISTENT = 0` uses transient statistics.
- `STATS_PERSISTENT = DEFAULT` follows the server setting.
- `STATS_AUTO_RECALC` controls automatic recalculation of persistent stats.
- `STATS_SAMPLE_PAGES` specifies the number of sampled pages for the table's persistent statistics.

Table options and system variables should be verified against the running MySQL version. Changing sampling settings does not automatically recalculate existing stats immediately; `ANALYZE TABLE` may be needed.

## 8. Automatic InnoDB Statistics Recalculation

When persistent statistics and auto recalc are enabled, InnoDB can automatically recalculate statistics once a sufficient amount of data changes. The default threshold is commonly described as roughly 10% of the table's rows having changed.

Automatic recalculation may happen asynchronously. Therefore:
- Finishing a bulk load does not mean statistics are updated immediately.
- Some queries may run with old estimates for a window of time.
- Recalculation timing depends on engine state and workload.
- You can use `ANALYZE TABLE` to explicitly request an update.

Check table-specific options with:

~~~sql
SHOW CREATE TABLE orders;
~~~

If `STATS_PERSISTENT`, `STATS_AUTO_RECALC`, or `STATS_SAMPLE_PAGES` are explicitly declared, they appear in the table definition. When omitted, the table uses the `DEFAULT` from server configuration. Combine `SHOW CREATE TABLE` with the system variables in the previous section to determine effective settings; do not infer table options solely from metadata views that omit those fields.

### 8.1. Enabling/Disabling Auto Recalc Per Table

~~~sql
ALTER TABLE orders
    STATS_AUTO_RECALC = 0;
~~~

Disabling auto recalc can be useful when you want strict control over when statistics update, but it increases the risk of the optimizer using stale numbers. If disabled, you must maintain an explicit `ANALYZE TABLE` procedure after large data changes.

Re-enable:

~~~sql
ALTER TABLE orders
    STATS_AUTO_RECALC = 1;
~~~

Do not disable auto recalc just to avoid a single plan change without understanding the cause. Evaluate statistical stability, sampling, and the affected queries.

## 9. ANALYZE TABLE: Updating Table and Index Statistics

`ANALYZE TABLE` instructs MySQL to analyze the table and update statistics used by the optimizer.

~~~sql
ANALYZE TABLE orders;
~~~

The output typically returns `Table`, `Op`, `Msg_type`, and `Msg_text`. On normal completion, `Msg_text` is usually `OK`.

After running it, inspect:

~~~sql
SHOW INDEX FROM orders;
~~~

And:

~~~sql
SELECT *
FROM mysql.innodb_table_stats
WHERE database_name = DATABASE()
  AND table_name = 'orders';
~~~

### 9.1. When Should You Run ANALYZE TABLE?

- After bulk loads or large data imports.
- After deleting or updating a large percentage of rows.
- After significant shifts in value distributions.
- After adding or dropping indexes.
- When `EXPLAIN` row estimates differ sharply from reality.
- When the optimizer picks an unusual plan and stale stats are suspected.

You do not need to run `ANALYZE TABLE` after every small `INSERT`/`UPDATE`. InnoDB already has auto recalc; constant re-analysis can generate unnecessary I/O and plan churn.

### 9.2. Does ANALYZE TABLE Produce Exact Statistics?

No. InnoDB still uses page sampling to estimate cardinality. `ANALYZE` refreshes statistics, but results retain margin of error due to sampling and data distribution.

If you need an exact distinct count for a report, compute it directly:

~~~sql
SELECT COUNT(DISTINCT customer_id)
FROM orders;
~~~

This query can incur substantial cost and is not a normal substitute for optimizer statistics.

### 9.3. Operational Impact

`ANALYZE TABLE` reads and updates statistical metadata. For InnoDB, analysis generally permits concurrent DML, though it can still require metadata locks and consume I/O and CPU. On large tables or heavy workloads, run it during suitable windows and monitor latency.

`ANALYZE TABLE` is not the same as `ALTER TABLE` rebuilding indexes. It is not used to repair data or rebuild corrupted indexes.

## 10. Sampling Pages and Cardinality Accuracy

InnoDB estimates cardinality by sampling index pages. If the sample is too small:
- Rare values may not appear in the sample.
- Skewed distributions can be misestimated.
- Cardinality may fluctuate across `ANALYZE` runs.

If you increase sampled pages:
- Estimates tend to be more representative.
- `ANALYZE TABLE` may consume more time and I/O.
- Statistics are typically more stable, though still not exact counts.

Example server-level configuration:

~~~sql
SET GLOBAL innodb_stats_persistent_sample_pages = 64;
~~~

This variable affects persistent stats sampling for tables using the default. You can configure a specific table individually with `STATS_SAMPLE_PAGES`.

Do not pick a page count by guesswork. Test on tables with skewed distributions, compare cardinality and plans before/after, and measure both `ANALYZE` cost and query performance.

## 11. What Is a Histogram?

Index statistics provide cardinality estimates for indexes and index prefixes. However, the optimizer sometimes needs to know a column's value distribution, especially when:
- The column has no index.
- A few values occur very frequently while most values are rare.
- The data distribution is heavily skewed.
- Predicates filter on specific values not well represented by average cardinality.

A histogram is per-column distribution statistics. MySQL stores histograms in the data dictionary and exposes them via `INFORMATION_SCHEMA.COLUMN_STATISTICS`.

A histogram is not an index. It helps the optimizer estimate selectivity; it does not create a physical B-tree access path to locate rows.

### 11.1. Two Common Histogram Types

- **Singleton histogram**: stores frequencies for individual distinct values, well suited when the number of distinct values is relatively small.
- **Equi-height histogram**: divides the value range into buckets with approximately equal row counts, suited when there are more distinct values.

Histograms have a bucket limit. More buckets can describe the distribution in finer detail, but increase metadata size and do not eliminate sampling error.

### 11.2. Creating Histograms

~~~sql
ANALYZE TABLE orders
    UPDATE HISTOGRAM ON status
    WITH 32 BUCKETS;
~~~

You can create histograms for multiple columns:

~~~sql
ANALYZE TABLE orders
    UPDATE HISTOGRAM ON status, customer_id
    WITH 64 BUCKETS;
~~~

Histograms are one-dimensional per column. They do not capture correlation between `customer_id` and `status` like multi-column statistics would.

### 11.3. Viewing Histograms

~~~sql
SELECT
    SCHEMA_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    HISTOGRAM
FROM information_schema.column_statistics
WHERE SCHEMA_NAME = DATABASE()
  AND TABLE_NAME = 'orders';
~~~

You can format the JSON for readability:

~~~sql
SELECT
    COLUMN_NAME,
    JSON_PRETTY(HISTOGRAM) AS histogram_json
FROM information_schema.column_statistics
WHERE SCHEMA_NAME = DATABASE()
  AND TABLE_NAME = 'orders';
~~~

JSON metadata typically contains:
- `histogram-type`.
- `number-of-buckets-specified`.
- `sampling-rate`.
- `last-updated`.
- `null-values`.
- `data-type` and collation info where applicable.
- list of buckets and cumulative frequencies.

Exact layout depends on the histogram type and MySQL version. Do not parse the JSON assuming a single layout without checking `histogram-type`.

### 11.4. Dropping Histograms

~~~sql
ANALYZE TABLE orders
    DROP HISTOGRAM ON status;
~~~

Dropping a histogram does not delete indexes or alter table data. The optimizer stops using a histogram for that column and relies on other available statistics such as index statistics and default estimates.

### 11.5. Histograms Do Not Auto-Update on Every DML

Histograms must be managed explicitly. When data distributions change significantly, an old histogram may no longer be representative. Refresh it with `ANALYZE TABLE ... UPDATE HISTOGRAM` as needed.

Do not confuse InnoDB persistent index statistics auto recalc with histograms automatically rebuilding after every data change.

## 12. When Do Histograms Help?

Consider a `status` column with a skewed distribution:

| status | Share of Rows |
|---|---:|
| CLOSED | 80% |
| OPEN | 15% |
| ESCALATED | 4% |
| RARE | 1% |

If the optimizer only assumes a uniform distribution across four values, it may misestimate predicates like `status = 'RARE'` or `status = 'CLOSED'`.

A histogram gives the optimizer distribution data to make better estimates for eligible predicates.

Create the histogram:

~~~sql
ANALYZE TABLE ticket
    UPDATE HISTOGRAM ON status
    WITH 16 BUCKETS;
~~~

Then compare:

~~~sql
EXPLAIN
SELECT ticket_id
FROM ticket
WHERE status = 'RARE';

EXPLAIN
SELECT ticket_id
FROM ticket
WHERE status = 'CLOSED';
~~~

Observe estimated `rows`, access `type`, and `key`. If the column is indexed, the optimizer still evaluates index access paths and real costs. Histograms assist estimation; they do not force the optimizer to pick an index.

### 12.1. Histograms Do Not Replace Composite Indexes

Suppose the query is:

~~~sql
SELECT ticket_id
FROM ticket
WHERE customer_id = 42
  AND status = 'OPEN';
~~~

A histogram on `status` does not create a composite B-tree on `(customer_id, status)`. Nor does it accurately capture correlation between the two columns.

If the workload needs efficient access on both conditions together, an appropriate composite index can matter more. Histograms and index statistics complement each other but solve different problems.

### 12.2. Watch Out for Multi-Column Correlation

Suppose `status = 'ESCALATED'` occurs only for a specific subset of `customer_id` values. A standalone `status` histogram and standalone `customer_id` statistics cannot necessarily capture this correlation.

The optimizer may misestimate row counts for the combined predicates. In such cases:
- Check actual rows with `EXPLAIN ANALYZE`.
- Evaluate whether a composite index fits.
- Review how predicates and JOINs are written.
- Check statistics after data changes.
- Do not expect single-column histograms to fix every multi-column discrepancy.

## 13. Per-Partition Metadata

For partitioned tables, statistics and storage sizes can be reported per table or per partition in `INFORMATION_SCHEMA.PARTITIONS`.

~~~sql
SELECT
    PARTITION_NAME,
    PARTITION_METHOD,
    PARTITION_EXPRESSION,
    TABLE_ROWS,
    DATA_LENGTH,
    INDEX_LENGTH,
    DATA_FREE
FROM information_schema.partitions
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders_partitioned'
ORDER BY PARTITION_ORDINAL_POSITION;
~~~

Per-partition `TABLE_ROWS` in InnoDB is still an estimate. Use this information to understand relative size and row distribution, not as a substitute for `COUNT(*)` per partition condition.

When partitions have skewed distributions, the optimizer may estimate differently across partitions. Verify partition pruning and execution plans with `EXPLAIN`.

## 14. Performance Schema: Measuring Actual Runtime Activity

Optimizer statistics describe data and distributions to predict costs. Performance Schema records runtime events such as read/write counts and wait durations.

Example checking I/O by index:

~~~sql
SELECT
    OBJECT_SCHEMA,
    OBJECT_NAME,
    INDEX_NAME,
    COUNT_READ,
    COUNT_WRITE,
    SUM_TIMER_READ,
    SUM_TIMER_WRITE
FROM performance_schema.table_io_waits_summary_by_index_usage
WHERE OBJECT_SCHEMA = DATABASE()
  AND OBJECT_NAME = 'orders'
ORDER BY COUNT_READ DESC;
~~~

A `NULL` `INDEX_NAME` usually represents operations not tied to a specific index, such as table scans. Exact interpretation requires cross-checking event types and enabled instrumentation.

Performance Schema metrics are cumulative counters over the active collection interval; they are neither cardinality nor optimizer statistics. They can reset on server restart or when summary tables are truncated/reset.

### 14.1. Finding Unused Indexes

The `sys` schema provides a helpful view:

~~~sql
SELECT *
FROM sys.schema_unused_indexes
WHERE object_schema = DATABASE();
~~~

This view helps identify indexes with no recorded usage during the observation window. However, "unused" does not automatically mean redundant:
- The server may have restarted recently.
- Infrequent monthly/quarterly workloads may not have run yet.
- The index may enforce a constraint or support maintenance queries.
- Certain queries may run outside the observed timeframe.

Do not `DROP` an index based on a single read of `schema_unused_indexes`. Observe across a full business cycle and check constraints first.

### 14.2. Per-Table Activity Statistics

~~~sql
SELECT *
FROM sys.schema_table_statistics
WHERE table_schema = DATABASE()
  AND table_name = 'orders';
~~~

`sys` views present Performance Schema data in a more readable form. They assist workload diagnostics and do not replace cardinality statistics used by the optimizer.

## 15. EXPLAIN: How Are Statistics Used in a Plan?

`EXPLAIN` reveals how the optimizer expects to access data.

~~~sql
EXPLAIN
SELECT order_id, total_amount
FROM orders
WHERE customer_id = 1001
  AND status = 'PENDING';
~~~

Fields to inspect:

| Field | Meaning |
|---|---|
| type | Access type such as const, eq_ref, ref, range, index, ALL |
| possible_keys | Indexes the optimizer can consider |
| key | Chosen index |
| key_len | Length of key prefix used |
| rows | Estimated rows to read |
| filtered | Estimated percentage of rows remaining after conditions |
| Extra | Notes such as Using index, Using where, Using filesort |

`rows` and `filtered` are estimates, not actual row counts. They are driven by table statistics, index statistics, histograms, and query predicates.

### 15.1. Comparing Estimated Rows with Actual Rows

On MySQL 8.0.18 and later, `EXPLAIN ANALYZE` executes the query and reports actual metrics per iterator:

~~~sql
EXPLAIN ANALYZE
SELECT order_id, total_amount
FROM orders
WHERE customer_id = 1001
  AND status = 'PENDING';
~~~

Compare:
- estimated rows.
- actual rows.
- loops.
- initialization and execution timing.
- row counts at each iterator.

If estimated rows is 10 yet actual rows is 100,000, the optimizer severely misjudged selectivity. Check statistics, histograms, column correlations, and predicates.

`EXPLAIN ANALYZE` runs the real `SELECT`. Use it in an appropriate environment, especially for heavy queries.

## 16. Optimizer Trace: Understanding Plan Selection Reasons

When `EXPLAIN` does not clearly show why the optimizer picked an access path, you can use optimizer trace in a test session.

~~~sql
SET optimizer_trace = 'enabled=on';

SELECT order_id
FROM orders
WHERE customer_id = 1001
  AND status = 'PENDING';

SELECT TRACE
FROM information_schema.optimizer_trace;

SET optimizer_trace = 'enabled=off';
~~~

The trace can contain:
- Candidate access paths considered.
- Cost estimates.
- Reasons an index or range scan was rejected.
- `JOIN` order decisions.
- Condition transformation steps.

Optimizer trace is detailed diagnostic data and can be very verbose. Enable it only when needed and turn it off right after collection. Do not treat trace output as a stable application API.

## 17. Workflow for Updating and Verifying Statistics

A workflow to apply when a query is unexpectedly slow:

1. Record the SQL, representative parameters, and execution time.
2. Inspect the schema with `SHOW CREATE TABLE`.
3. Inspect indexes with `SHOW INDEX`.
4. Check `TABLE_ROWS`, `DATA_LENGTH`, and `INDEX_LENGTH` to gauge relative scale.
5. Read `mysql.innodb_table_stats` and `mysql.innodb_index_stats`.
6. Check existing histograms in `INFORMATION_SCHEMA.COLUMN_STATISTICS`.
7. Run `EXPLAIN` and record estimated `rows`, `key`, `type`, and `Extra`.
8. Run `EXPLAIN ANALYZE` in an appropriate environment to capture actual rows.
9. If statistics are stale or data changed sharply, run `ANALYZE TABLE`.
10. If a column distribution is skewed, consider `UPDATE HISTOGRAM`.
11. Re-run `EXPLAIN`/`EXPLAIN ANALYZE` and compare.
12. Check runtime metrics in Performance Schema to confirm the index is used in the real workload.
13. Monitor plans post-deployment, since statistics and data continue evolving.

Do not add or drop indexes merely because cardinality is low or high. Consider actual predicates, returned row counts, and read/write costs.

## 18. Common Mistakes

| Misconception or Mistake | Root Cause | Remedy |
|---|---|---|
| Treating TABLE_ROWS as exact row count | InnoDB reports an estimate | Use COUNT(*) when an exact count is needed |
| Thinking cardinality is index row count | Cardinality is estimated distinct values | Read per index prefix |
| Thinking the second row's cardinality is for the second column alone | Composite indexes report prefix statistics | Check SEQ_IN_INDEX and column order |
| Thinking ANALYZE TABLE makes statistics 100% exact | InnoDB uses page sampling | Compare and tune sampling when needed |
| Thinking persistent stats update instantaneously | Auto recalc may run asynchronously | Proactively run ANALYZE after major changes |
| Treating a histogram as an index | Histograms only describe distribution | Create an index if a physical access path is needed |
| Thinking histograms capture multi-column correlation | Histograms are one-dimensional | Evaluate composite indexes and actual rows |
| Thinking histograms auto-update on every DML | Histograms must be managed separately | Refresh when distributions shift |
| Treating Performance Schema as a cardinality source | It records runtime activity | Use the right source for the question |
| Assuming an index absent from usage or listed in sys.schema_unused_indexes is redundant | Observation window may be too short | Monitor a full workload cycle and check constraints |
| Thinking EXPLAIN rows are actual rows | They are estimates | Use EXPLAIN ANALYZE |
| Editing mysql.innodb_index_stats to force the optimizer | Bypasses internal management | Use ANALYZE TABLE and supported settings |
| Thinking ANALYZE TABLE has zero workload impact | It can consume I/O and take metadata locks | Pick an appropriate window and watch load |
| Thinking DATA_LENGTH is payload size | It reflects page/index allocation | Use proper storage/backup sizing tools |

## 19. Practice Exercises

### Exercise 1: Reading Table Metadata

Create an `orders` table with a few thousand rows. Query `INFORMATION_SCHEMA.TABLES` and `SHOW TABLE STATUS`. Compare `TABLE_ROWS` with `COUNT(*)`. Explain why they can differ.

### Exercise 2: Reading Index Cardinality

Create single-column indexes on `customer_id` and `status`, then a composite index on `(customer_id, status)`. Run `SHOW INDEX` and read `Cardinality` by `Seq_in_index`. Identify the cardinality of the one-column and two-column prefixes.

### Exercise 3: Reading InnoDB Persistent Stats

Query `mysql.innodb_table_stats` and `mysql.innodb_index_stats`. Locate `n_rows`, `n_diff_pfxNN`, `n_leaf_pages`, and `size`. Compare page counts with metadata sizes.

### Exercise 4: Updating Statistics

Insert many rows with a `status` distribution totally different from the initial data. Run `EXPLAIN` before and after `ANALYZE TABLE`. Record estimated `rows` and plans.

### Exercise 5: Sampling Pages

In a lab environment, change `STATS_SAMPLE_PAGES` on a table or `innodb_stats_persistent_sample_pages`. Run `ANALYZE TABLE` multiple times and compare cardinality and analysis time. Do not make global production changes just for experiments.

### Exercise 6: Histograms for Skewed Columns

Create `status` data with one dominant value and one rare value. Run `EXPLAIN` for each value before creating a histogram, then `UPDATE HISTOGRAM` and run again. Compare estimated rows.

### Exercise 7: Viewing Histogram Metadata

Query `INFORMATION_SCHEMA.COLUMN_STATISTICS` and use `JSON_PRETTY` to inspect the histogram JSON. Identify `histogram-type`, `sampling-rate`, and bucket count. Then `DROP HISTOGRAM` and confirm metadata changed.

### Exercise 8: Comparing Estimates and Actuals

Run `EXPLAIN ANALYZE` on a query with a skewed predicate. Record estimated rows, actual rows, and loops. Explain why a discrepancy can cause an inefficient `JOIN` order or access path.

### Exercise 9: Runtime Index Usage

Run a representative workload, then read `performance_schema.table_io_waits_summary_by_index_usage` and `sys.schema_unused_indexes`. Identify which indexes were used. Restart the lab or reset summary tables to understand the effect of observation windows.

### Exercise 10: Diagnostic Report

Write a short diagnostic report for a slow query, including:
- Relevant schema and indexes.
- Current table/index statistics.
- Whether histograms exist.
- `EXPLAIN` and `EXPLAIN ANALYZE`.
- Runtime index usage.
- Statistics update or index change actions.
- Before/after measurements.

## 20. Checklist Before Concluding About Statistics

- [ ] Distinguished structural metadata, optimizer statistics, and runtime metrics.
- [ ] Understood that InnoDB `TABLE_ROWS` is an estimate.
- [ ] Checked schema and engine before interpreting statistics.
- [ ] Read `SHOW INDEX` and understood per-prefix cardinality.
- [ ] Inspected `mysql.innodb_table_stats` and `mysql.innodb_index_stats` when needed.
- [ ] Avoided modifying system statistics tables directly.
- [ ] Checked persistent/transient stats and auto recalc settings.
- [ ] Checked sample pages if cardinality is unstable.
- [ ] Ran `ANALYZE TABLE` after large data changes when appropriate.
- [ ] Distinguished index statistics from histograms.
- [ ] Understood that histograms are single-column stats requiring separate updates.
- [ ] Checked `INFORMATION_SCHEMA.COLUMN_STATISTICS` when using histograms.
- [ ] Distinguished Performance Schema from optimizer statistics.
- [ ] Used `EXPLAIN` to read estimates.
- [ ] Used `EXPLAIN ANALYZE` to compare against actual metrics where appropriate.
- [ ] Evaluated multi-column correlations and skewed distributions.
- [ ] Assessed operational impact before running `ANALYZE` or changing settings.
- [ ] Measured actual workload before adding or dropping indexes.

## 21. Conclusion

Statistics enable the MySQL optimizer to estimate costs and choose execution plans. `INFORMATION_SCHEMA.TABLES` provides estimated scale and storage sizes; `SHOW INDEX` and `INFORMATION_SCHEMA.STATISTICS` describe indexes and per-prefix cardinality; `mysql.innodb_table_stats` and `mysql.innodb_index_stats` store persistent InnoDB statistics; histograms describe per-column value distributions; and Performance Schema and `sys` show how workloads actually executed.

No single source replaces the others. Distinguish estimates from exact counts, optimizer statistics from runtime counters, and histograms from physical indexes. After major data changes, run `ANALYZE TABLE` or targeted histogram updates; then compare `EXPLAIN` against `EXPLAIN ANALYZE` to spot estimation gaps. Only change indexes or configuration after measuring read performance, write performance, and operational impact.

## Official References

- [MySQL 8.4 Reference Manual – InnoDB Persistent Statistics](https://dev.mysql.com/doc/refman/8.4/en/innodb-persistent-stats.html)
- [MySQL 8.4 Reference Manual – Configuring Persistent Optimizer Statistics Parameters](https://dev.mysql.com/doc/refman/8.4/en/innodb-persistent-stats.html#innodb-persistent-stats-configuration)
- [MySQL 8.4 Reference Manual – InnoDB Transient Statistics](https://dev.mysql.com/doc/refman/8.4/en/innodb-statistics-estimation.html)
- [MySQL 8.4 Reference Manual – ANALYZE TABLE](https://dev.mysql.com/doc/refman/8.4/en/analyze-table.html)
- [MySQL 8.4 Reference Manual – Optimizer Statistics](https://dev.mysql.com/doc/refman/8.4/en/optimizer-statistics.html)
- [MySQL 8.4 Reference Manual – Optimizer Statistics: Histograms](https://dev.mysql.com/doc/refman/8.4/en/optimizer-statistics.html#optimizer-statistics-histograms)
- [MySQL 8.4 Reference Manual – INFORMATION_SCHEMA TABLES](https://dev.mysql.com/doc/refman/8.4/en/information-schema-tables-table.html)
- [MySQL 8.4 Reference Manual – INFORMATION_SCHEMA STATISTICS](https://dev.mysql.com/doc/refman/8.4/en/information-schema-statistics-table.html)
- [MySQL 8.4 Reference Manual – InnoDB Information Schema Tables](https://dev.mysql.com/doc/refman/8.4/en/innodb-information-schema-system-tables.html)
- [MySQL 8.4 Reference Manual – Performance Schema Table I/O Wait Summary Tables](https://dev.mysql.com/doc/refman/8.4/en/performance-schema-table-wait-summary-tables.html)
- [MySQL 8.4 Reference Manual – EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)
- [MySQL 8.4 Reference Manual – Optimizer Trace](https://dev.mysql.com/doc/refman/8.4/en/optimizer-tracing.html)
