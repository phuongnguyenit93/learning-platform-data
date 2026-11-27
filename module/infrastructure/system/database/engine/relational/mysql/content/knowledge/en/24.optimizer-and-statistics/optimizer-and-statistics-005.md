# ANALYZE TABLE and When to Update Statistics

The MySQL Optimizer needs to estimate how many rows each query step will read, how many rows remain after filtering, and the cost of each access path. These estimates depend on table statistics, index statistics, and histograms. If statistics are stale or do not reflect the current data distribution, the optimizer can choose the wrong index, a suboptimal `JOIN` order, or a more expensive plan.

`ANALYZE TABLE` instructs MySQL to re-collect statistics for a table and its indexes. For InnoDB, this operation typically refreshes estimated cardinality by sampling index pages. It can be run manually after substantial data changes, after creating or altering indexes, or when execution plan estimates diverge markedly from actual row counts.

However, running `ANALYZE TABLE` does not guarantee a query will run faster. New statistics can lead the optimizer to choose a different plan—sometimes better and sometimes worse. Therefore, identify the right timing, capture before-and-after execution plans, and evaluate operational load.

Within the **DATABASE_MYSQL** module, this lesson explains the role of optimizer statistics, InnoDB persistent statistics, automatic recalculation, index page sampling, histograms, and the decision process for when to run `ANALYZE TABLE`.

## 1. Why Does the Optimizer Need Statistics?

When receiving a query, MySQL must decide how to read the data. For a `JOIN` query, the optimizer may consider:

- Reading table A first and then looking up matching rows in table B.
- Reading table B first and then joining to table A.
- Using the `PRIMARY KEY`, a secondary index, or a full table scan.
- Using a nested-loop join with repeated lookups.
- Applying filter predicates before or after a `JOIN` step.
- Using temporary tables or filesort for certain operations.

The optimizer estimates cost using statistics and a cost model. A key element is cardinality: the estimated number of distinct values in a column or key prefix.

Example orders table:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    region_code CHAR(2) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_tenant_status (tenant_id, status),
    KEY idx_region (region_code),
    KEY idx_created_at (created_at)
) ENGINE = InnoDB;
```

Query:

```sql
SELECT order_id, total_amount
FROM orders
WHERE tenant_id = 42
  AND status = 'PENDING';
```

If the optimizer estimates only 20 matching rows, using the index can be very cheap. If in reality 500,000 rows match, another plan may be better. When cardinality or data distribution does not match reality, optimizer decisions can go wrong.

### 1.1. Statistics Are Not Business Data

Optimizer statistics are estimation metadata, not exact per-query row counts. `Cardinality` in `SHOW INDEX` is typically an estimate of distinct values. The optimizer uses them to compare costs, not as data constraints.

Distinguish:

| Component | Role |
|---|---|
| Table data | Actual business rows |
| Index | Data access structure |
| Index statistics | Cardinality and key-prefix distribution estimates |
| Histogram | Description of a single column's value distribution |
| Execution plan | Plan chosen by the optimizer based on query, statistics, and cost model |

`ANALYZE TABLE` updates statistics; it does not modify data, create new indexes, or change the query's `WHERE` logic.

## 2. What Does ANALYZE TABLE Do?

Basic syntax:

```sql
ANALYZE TABLE orders;
```

MySQL returns details about the table, operation, and status. For InnoDB, `ANALYZE TABLE` re-collects index statistics, including estimated cardinality of key parts. The optimizer uses the updated statistics during subsequent plan compilation.

You can analyze multiple tables in one statement:

```sql
ANALYZE TABLE orders, customers, order_items;
```

You can specify partitions in a partitioned table if you only need to refresh statistics for selected partitions:

```sql
ANALYZE TABLE orders PARTITION (p2025, p2026);
```

This example assumes `orders` is a partitioned table with two partitions named `p2025` and `p2026`; it does not apply to the non-partitioned `orders` table from the earlier example. Verify syntax and partition names on your running MySQL version before automating.

### 2.1. Returned Result

The output typically includes these columns:

| Column | Meaning |
|---|---|
| Table | Name of the analyzed table |
| Op | Operation performed, typically `analyze` |
| Msg_type | Message type such as `status`, `note`, or `error` |
| Msg_text | Outcome or error text |

Inspect `Msg_type` and `Msg_text` to confirm the operation succeeded. Do not merely check that the application threw no exception; read the output of the administrative statement.

### 2.2. ANALYZE TABLE Is Not OPTIMIZE TABLE

The two commands serve different purposes:

| Command | Primary Purpose |
|---|---|
| ANALYZE TABLE | Update optimizer statistics |
| OPTIMIZE TABLE | Reorganize or rebuild the table/indexes depending on storage engine and version; may reclaim or defragment storage space |
| CHECK TABLE | Check table structure and engine-specific consistency issues |
| REPAIR TABLE | Repair tables for certain storage engines; not a standard InnoDB data repair command |

Do not run `OPTIMIZE TABLE` just because an execution plan shows wrong cardinality. First verify whether the problem actually lies in statistics.

## 3. InnoDB Statistics: Persistent vs. Transient

InnoDB manages statistics in two primary modes:

- **Persistent statistics:** stored in MySQL system tables and preserved across restarts.
- **Transient statistics:** computed temporarily rather than persisted like persistent stats; may be recalculated when a table is opened or across the table lifecycle.

In modern MySQL versions, persistent statistics are enabled by default for InnoDB. Check:

```sql
SELECT
    @@GLOBAL.innodb_stats_persistent
        AS innodb_stats_persistent,
    @@GLOBAL.innodb_stats_auto_recalc
        AS innodb_stats_auto_recalc,
    @@GLOBAL.innodb_stats_persistent_sample_pages
        AS persistent_sample_pages;
```

These variables are read at `GLOBAL` scope. You can use `SHOW VARIABLES` to inspect the server's active configuration.

### 3.1. Persistent Statistics

When persistent stats are enabled, InnoDB stores statistics in system tables such as:

- `mysql.innodb_table_stats`
- `mysql.innodb_index_stats`

Inspect table statistics:

```sql
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
```

Inspect index statistics:

```sql
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
```

In `innodb_index_stats`, rows with `stat_name` like `n_diff_pfxNN` represent estimated distinct values for leading index prefixes. This is a key input for the optimizer when estimating composite index selectivity.

These tables are for observation. Do not manually `UPDATE`/`DELETE` rows in them to force the optimizer to pick a plan. To update statistics, use `ANALYZE TABLE` or supported MySQL mechanisms.

### 3.2. Transient Statistics

If persistent stats are disabled for a table or server-wide, InnoDB uses transient stats. Statistics may be recalculated when a table is opened and are not preserved across restarts like persistent stats.

This can cause execution plans to change between table opens or after restarts if sampling produces different estimates. For systems needing stable plans, persistent stats are generally easier to manage and monitor.

### 3.3. Table-Level Configuration

You can configure statistics options for a table using table options:

```sql
ALTER TABLE orders
    STATS_PERSISTENT = 1,
    STATS_AUTO_RECALC = 1,
    STATS_SAMPLE_PAGES = 64;
```

Meaning:

| Option | Meaning |
|---|---|
| STATS_PERSISTENT | Enable/disable persistent stats for the table, or use `DEFAULT` |
| STATS_AUTO_RECALC | Enable/disable automatic statistics recalculation for the table |
| STATS_SAMPLE_PAGES | Number of index pages sampled when computing persistent stats for the table |

Table-level options override global defaults. Use `SHOW CREATE TABLE orders` to inspect current table options.

Do not raise `STATS_SAMPLE_PAGES` arbitrarily. Sampling more pages can improve estimates for unevenly distributed data, but it also makes `ANALYZE TABLE` slower and heavier on I/O.

## 4. Automatic Statistics Recalculation

When `innodb_stats_auto_recalc` is enabled, InnoDB can automatically recalculate persistent statistics when enough rows change relative to table size.

The default threshold is commonly about 10% of the table's rows modified since the previous calculation. This is an automatic trigger threshold, not a guarantee that statistics update instantaneously after one specific `INSERT`/`UPDATE`/`DELETE`.

Recalculation can run asynchronously in the background. Therefore, after a large batch import, an application may see updated data while the optimizer does not immediately use new statistics.

Check settings:

```sql
SHOW VARIABLES LIKE 'innodb_stats_auto_recalc';
SHOW VARIABLES LIKE 'innodb_stats_persistent';
```

### 4.1. When Might Auto Recalc Not Be Enough?

- A table was just bulk-loaded and critical queries need good plans right after import.
- Data distribution shifted significantly even though the modified row percentage has not crossed the threshold.
- One column's skew changed sharply despite a small total row change.
- Multiple cardinality-sensitive queries require intentional statistics updates.
- You are investigating a plan regression and need a clean statistics baseline.

In these scenarios, run `ANALYZE TABLE` manually after data stabilizes and before evaluating execution plans.

### 4.2. Should You Disable Auto Recalc?

Disabling automatic updates can be useful in systems that must tightly control when plans can change. However, if data changes continuously without a scheduled `ANALYZE TABLE` replacement, statistics will grow progressively stale.

If you set:

```sql
ALTER TABLE orders
    STATS_AUTO_RECALC = 0;
```

build a manual statistics refresh procedure tied to data events, maintenance schedules, or plan estimate alerts. Do not disable auto recalc just to prevent a single plan change without a replacement mechanism.

## 5. Index Page Sampling and Statistics Accuracy

InnoDB does not necessarily read the entire index to compute cardinality. It samples a set of index pages and estimates distinct value counts across the full structure.

This saves time but introduces margin of error, especially when data is unevenly distributed or different index regions hold vastly different value concentrations.

For example, a table with one million orders:

- 70% of orders belong to tenant 1.
- 20% belong to tenant 2.
- The remaining 10% are split across thousands of tenants.

If sampled pages fail to capture tenant 1's region accurately, cardinality or distribution estimates can be skewed. A plan built on bad estimates can pick an unsuitable index or `JOIN` order.

### 5.1. Increasing Sample Pages

You can raise the global variable:

```sql
SET GLOBAL innodb_stats_persistent_sample_pages = 64;
ANALYZE TABLE orders;
```

Or configure per table via `STATS_SAMPLE_PAGES`. Increasing sample pages can stabilize statistics, though it does not guarantee exact accuracy and increases read overhead.

Changes via `SET GLOBAL` apply only to the running instance. To persist configuration across restarts, manage the setting in the MySQL option file or via the server's supported persistent configuration mechanism.

When testing a change, you should:

1. Record the baseline configuration value.
2. Measure `ANALYZE TABLE` execution time.
3. Compare cardinality before and after.
4. Compare execution plans of critical queries.
5. Measure latency/throughput of a representative workload.
6. Keep the new setting only once benefits are confirmed.

### 5.2. Statistics Can Fluctuate

Because of sampling, two consecutive `ANALYZE TABLE` runs on the same table can yield slightly different cardinalities. For queries near a break-even point between two access paths, small variations can cause the optimizer to pick a different index.

If a plan changes after `ANALYZE TABLE`, do not immediately conclude the new statistics are wrong. Compare:

- Optimizer estimates.
- Actual row counts.
- Per-iterator execution time.
- Iteration counts of nested-loop lookups.
- I/O and cache state.
- Consistency of results across multiple runs.

## 6. Histograms: Per-Column Distribution Statistics

Index statistics typically provide cardinality for index keys and prefixes. However, cardinality does not fully describe value distribution.

For example, a `status` column with 4 values:

| status | Share of Rows |
|---|---:|
| PENDING | 75% |
| PAID | 20% |
| CANCELLED | 4% |
| FAILED | 1% |

Knowing only that there are 4 distinct values does not tell the optimizer that `PENDING` accounts for 75% while `FAILED` accounts for 1%. Histograms describe this distribution to estimate filter predicate selectivity.

MySQL has supported histogram statistics since MySQL 8.0.2. Histograms are managed separately from index statistics and must be created/updated using `ANALYZE TABLE` with `UPDATE HISTOGRAM`.

### 6.1. Creating a Histogram

```sql
ANALYZE TABLE orders
    UPDATE HISTOGRAM ON status
    WITH 100 BUCKETS;
```

You can update multiple columns in the same statement:

```sql
ANALYZE TABLE orders
    UPDATE HISTOGRAM ON status, region_code
    WITH 100 BUCKETS;
```

Bucket count can be chosen within MySQL's supported range, up to 1024. If omitted, MySQL uses a default bucket count. More buckets describe distributions in finer detail at the cost of larger histogram metadata and higher collection overhead.

### 6.2. Viewing Histograms

Histograms are stored in the data dictionary and viewable via `INFORMATION_SCHEMA.COLUMN_STATISTICS`:

```sql
SELECT
    SCHEMA_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    JSON_PRETTY(HISTOGRAM) AS histogram
FROM information_schema.COLUMN_STATISTICS
WHERE SCHEMA_NAME = DATABASE()
  AND TABLE_NAME = 'orders';
```

You can read key histogram properties in the JSON such as histogram type, specified bucket count, last update timestamp, sampling rate, and data buckets. The JSON layout may include extra attributes depending on data type and version.

### 6.3. Singleton and Equi-Height Histograms

MySQL can use two main histogram formats:

- **Singleton:** suitable when distinct values are relatively few; each value is recorded with its cumulative frequency.
- **Equi-height:** divides the distribution into buckets containing roughly equal data volumes; a bucket can cover a range of values.

The optimizer picks the appropriate format based on the number of distinct values and available buckets. You do not manually choose the histogram type in standard statements.

### 6.4. When Do Histograms Help?

Histograms are helpful when:

- A column has a skewed distribution.
- Certain values occur very frequently.
- A column has no standalone index yet appears in `WHERE` predicates.
- The optimizer estimates selectivity poorly from index statistics alone.
- A `JOIN` or filter query plan depends heavily on the fraction of matching rows.

A histogram is a single-column statistic. It does not fully model correlations across multiple columns. For instance, `tenant_id = 42` may have a very different `PENDING` rate from the overall table; separate histograms for `tenant_id` and `status` do not necessarily capture that relationship.

### 6.5. Updating and Dropping Histograms

Histograms do not automatically update simply because table rows change. When column distributions shift significantly, refresh the histogram:

```sql
ANALYZE TABLE orders
    UPDATE HISTOGRAM ON status
    WITH 100 BUCKETS;
```

Drop a histogram when no longer needed or to revert to estimates without it:

```sql
ANALYZE TABLE orders
    DROP HISTOGRAM ON status;
```

Note: `ANALYZE TABLE orders;` updates index statistics for the table, which is not the same as recreating dropped histograms or explicitly refreshing histograms. Manage histograms using `UPDATE HISTOGRAM` and `DROP HISTOGRAM`.

## 7. When Should You Run ANALYZE TABLE?

Do not run `ANALYZE TABLE` after every transaction. Run it when there are signs statistics no longer represent the data or when you need to proactively refresh estimates.

### 7.1. After Bulk Import or Initial Data Load

When creating a new table and loading millions of records, prior statistics may be empty or fail to reflect the new distribution.

Workflow:

```sql
-- Load data using an appropriate import tool or statement.
-- Once the batch finishes:
ANALYZE TABLE orders;
```

Then run `EXPLAIN` for critical queries to verify the optimizer sees the new cardinality.

### 7.2. After Widespread Deletes or Updates

If you delete most old data, update statuses across a large percentage of rows, or migrate rows between groups, prior statistics may no longer hold.

Example:

```sql
DELETE FROM orders
WHERE created_at < '2023-01-01';

ANALYZE TABLE orders;
```

For very large `DELETE` operations, batch the deletes and run `ANALYZE` once after the main change finishes rather than after every small batch.

### 7.3. After Creating or Altering Indexes

DDL that creates an index typically updates metadata/statistics, but if execution plans still display unreasonable estimates, run `ANALYZE TABLE` to re-collect statistics.

```sql
CREATE INDEX idx_tenant_created
    ON orders (tenant_id, created_at);

ANALYZE TABLE orders;
```

`ANALYZE TABLE` does not create indexes and cannot substitute for proper key-part ordering. If a query filters on `status` while the index only contains `(tenant_id, created_at)`, updating statistics cannot make the index support `status` as a key part.

### 7.4. When EXPLAIN Estimates Diverge Sharply

For example, `EXPLAIN` estimates 100 rows while `EXPLAIN ANALYZE` actually reads 200,000 rows, or vice versa. This warrants investigation:

- Are index statistics stale?
- Is the column skewed?
- Is a histogram present?
- Did data change heavily recently?
- Are multiple columns in the predicates correlated?
- Do data types or collations make predicates hard to estimate?

If stale index stats are suspected, run `ANALYZE TABLE`. If single-column skew is suspected, consider a histogram. If multi-column correlation is the issue, a single-column histogram may not suffice; revisit composite indexes, query structure, and access strategy.

### 7.5. On a Schedule When Workloads Shift

For tables whose data grows or shrinks dramatically each day, you can schedule `ANALYZE TABLE` during a maintenance window. Still, a fixed schedule should not replace observation.

Append-only tables with stable distributions may not need frequent `ANALYZE`. Tables undergoing retention purges, new tenant onboarding, or bulk status transitions may require more frequent refreshes.

## 8. When Is ANALYZE TABLE Not Yet Needed?

There is no need to run it merely because:

- A single `SELECT` query is slow before you have even read `EXPLAIN`.
- The application just inserted a few rows.
- A new index exists that no query has used yet.
- `Cardinality` shown in `SHOW INDEX` does not match exact row count.
- You want to force the optimizer to pick a specific index without finding the root cause.
- You are in peak traffic hours and have not assessed I/O or lock impact.

Before running it, check:

1. Which query is slow and how often does it run?
2. Which index does the current execution plan use?
3. How far do estimated rows diverge from actual rows?
4. How much has the table changed since the last statistics update?
5. Is an appropriate histogram present?
6. Could running `ANALYZE` impact concurrent write workloads right now?

If the root cause is a missing index, non-sargable predicate, flawed `JOIN` condition, or returning excessive data, `ANALYZE TABLE` will not fix the underlying problem.

## 9. Before-and-After Workflow for ANALYZE TABLE

Do not run `ANALYZE` and look only for an `OK` message. Establish a workflow that enables clear comparison.

### Step 1: Capture the Query and Current Execution Plan

```sql
EXPLAIN FORMAT = JSON
SELECT order_id, total_amount
FROM orders
WHERE tenant_id = 42
  AND status = 'PENDING';
```

Record `key`, access type, estimated `rows`, cost, and `JOIN` order if applicable.

### Step 2: Measure Actual Row Counts

On MySQL versions supporting `EXPLAIN ANALYZE` (MySQL 8.0.18 and later), you can run:

```sql
EXPLAIN ANALYZE
SELECT order_id, total_amount
FROM orders
WHERE tenant_id = 42
  AND status = 'PENDING';
```

`EXPLAIN ANALYZE` executes the actual query. Use it only on bounded `SELECT` statements, avoiding unassessed high-cost queries in production.

### Step 3: Record Current Statistics

```sql
SHOW INDEX FROM orders;
```

If more detail is needed, read `mysql.innodb_table_stats` and `mysql.innodb_index_stats` as shown earlier. Do not edit these system tables directly.

### Step 4: Update Statistics

```sql
ANALYZE TABLE orders;
```

If a separate histogram is needed:

```sql
ANALYZE TABLE orders
    UPDATE HISTOGRAM ON status
    WITH 100 BUCKETS;
```

These two operations maintain two distinct kinds of statistics: index statistics and column histograms.

### Step 5: Re-Read the Plan and Re-Measure

Re-run `EXPLAIN FORMAT=JSON` and `EXPLAIN ANALYZE` using the same parameters, data conditions, and as similar an environment as possible.

Compare:

| Metric | Before | After |
|---|---|---|
| Chosen index | Recorded | Did it change? |
| Estimated rows | Old estimate | New estimate |
| Actual rows | Actual count | Actual count |
| Loops | Iterator execution count | Did it decrease? |
| Execution time | Before timing | After timing |
| Rows examined | Rows read | Did it decrease? |

Do not compare just a single run. Warm/cold caches, system load, and query parameters can alter timings. Use multiple measurements and a representative workload.

## 10. Histograms and Index Statistics Solve Different Problems

| Criterion | Index Statistics | Histogram |
|---|---|---|
| Target | Index and key prefixes | A single column |
| Primary data | Cardinality, distinct values of key prefixes | Value distribution and frequencies |
| Purpose | Estimate selectivity via index | Estimate filter predicates on a column |
| How updated | ANALYZE TABLE | ANALYZE TABLE ... UPDATE HISTOGRAM |
| Where viewed | SHOW INDEX, mysql.innodb_index_stats | INFORMATION_SCHEMA.COLUMN_STATISTICS |
| Multi-column correlation | Composite indexes carry prefix stats | Does not fully model multi-column correlation |

For example: index `(tenant_id, status)` provides estimated cardinality for prefixes `tenant_id` and `tenant_id + status`. A histogram on `status` describes the frequency of each status across the whole table. These two sources complement each other rather than fully replacing one another.

If `status = 'PENDING'` accounts for 80% of the whole table yet only 2% within `tenant_id = 42`, a single-column `status` histogram cannot capture that correlation. A composite index can supply better information for queries filtering on both `tenant_id` and `status`, depending on statistics quality.

## 11. ANALYZE TABLE and Replication

`ANALYZE TABLE` is written to the binary log by default in standard replication setups, meaning the operation can be replicated to replicas. You can prevent writing the statement to the binary log with:

```sql
ANALYZE NO_WRITE_TO_BINLOG TABLE orders;
```

Or use the equivalent keyword:

```sql
ANALYZE LOCAL TABLE orders;
```

Whether to run on source or replica depends on architecture and operational goals. If servers need independent statistics due to differing data distributions or workloads, manage local execution and replication behavior carefully so operations are not unintentionally logged.

Do not schedule identical `ANALYZE` jobs on source and every replica without understanding binlog propagation and workload impact. Verify replication status and operational policy.

## 12. Operational Impact and Locking During ANALYZE TABLE

`ANALYZE TABLE` is an administrative table operation, not a plain `SELECT`. For InnoDB and MyISAM, it acquires a read lock: reads can proceed while writes must wait while the lock is held. The command also requires a metadata lock and may wait on long transactions or pending DDL using the table. Exact behavior can vary by storage engine and version.

Before running in production:

- Prefer low-traffic windows if the table is large or the system is sensitive to write latency.
- Check for long-running transactions and pending DDL.
- Monitor lock waits, latency, and throughput during execution.
- Process tables in controlled batches rather than analyzing an entire large schema at once.
- Check the returned output and verify status afterward.

`ANALYZE TABLE` does not rebuild the whole table like some `OPTIMIZE` operations, yet it still incurs page reads and statistics updates. Do not treat it as a free command to run continuously.

## 13. Controlled Tuning of Histograms and Sample Pages

### 13.1. Do Not Pick Huge Bucket Counts by Intuition

More buckets can capture finer distribution detail, yet a histogram remains an estimation model. If a column has few distinct values, adding many buckets yields no proportional benefit.

For example, a `status` column with only four values:

```sql
ANALYZE TABLE orders
    UPDATE HISTOGRAM ON status
    WITH 16 BUCKETS;
```

If a column has millions of distinct values, test several appropriate bucket counts and compare estimated versus actual rows. There is no universal optimal bucket count for every column.

### 13.2. Do Not Raise Sample Pages to Fix Every Discrepancy

Increasing sample pages can improve index cardinality estimates when data is unevenly distributed. However, if the issue is that the optimizer does not know the correlation between two columns, increasing index statistics sample pages will not automatically solve it.

Classify the discrepancy first:

- Wrong index cardinality: check persistent stats and sample pages.
- Skewed single-column distribution: check histograms.
- Multi-column correlation: check composite indexes and query structure.
- Non-sargable condition: rewrite the predicate or use an appropriate generated/functional index.
- Missing index: design indexes around the workload.
- Estimates are accurate yet query is still slow: inspect I/O, CPU, locks, sorting, network, and returned data volume.

## 14. Common Mistakes and Misconceptions

| Mistake | Consequence | Remedy |
|---|---|---|
| Running ANALYZE TABLE after every INSERT | Unnecessary administrative overhead | Trigger based on change volume and plan symptoms |
| Thinking ANALYZE TABLE guarantees faster queries | Optimizer may switch to a different, even worse plan | Compare execution plans before and after |
| Confusing ANALYZE TABLE with OPTIMIZE TABLE | Running unnecessary rebuild/space maintenance | Match the command to the goal |
| Assuming auto recalc updates instantaneously | Plans may still use stale stats for a period | Run ANALYZE explicitly when immediate freshness is needed |
| Thinking cardinality is exact row count | Misinterpreting statistics | Understand it as a sampling-based estimate |
| Setting sample pages to maximum | Wastes I/O without fixing root causes | Raise only when measurements prove benefit |
| Thinking histograms auto-update after DML | Histograms go stale even when index stats refresh | Update histograms separately when distributions shift |
| Using single-column histograms for multi-column correlation | Optimizer still misestimates combined conditions | Evaluate composite indexes and query design |
| Editing mysql.innodb_index_stats directly | Leaves statistics inconsistent | Use ANALYZE TABLE |
| Running bulk ANALYZE during peak hours | Increases I/O or blocks writes | Run in controlled windows |
| Not checking plans after ANALYZE | Missing plan regressions | Compare EXPLAIN and actual execution |

## 15. Checklist for Deciding When to Run ANALYZE TABLE

**Consider running when:**

- A large volume of data was just bulk-loaded into the table.
- A large percentage of rows was just deleted or updated.
- Data distribution changed substantially.
- An index was just created or altered and plans look unreasonable.
- `EXPLAIN` estimates diverge sharply from actual rows.
- Table workloads shift periodically and statistics are no longer representative.

**Hold off when:**

- You do not yet know which query is slow.
- You have not inspected `EXPLAIN`.
- The issue is a missing index or non-sargable predicate.
- Only a small amount of new data was added.
- You have not assessed production I/O or lock impact.
- You want to force a specific index without benchmarking.

**After running:**

- Read `Msg_type` and `Msg_text`.
- Inspect `SHOW INDEX` or persistent stats.
- Re-run `EXPLAIN`.
- Run `EXPLAIN ANALYZE` on eligible `SELECT` queries.
- Compare estimated rows against actual rows.
- Measure latency and real workload performance.
- Check histograms if queries depend on single-column distributions.
- Record timestamp, table, rationale, outcome, and any plan regression.

## 16. Takeaways

- The optimizer uses statistics to estimate cardinality, selectivity, and access path costs.
- `ANALYZE TABLE` refreshes index statistics; it neither creates indexes nor changes business data.
- InnoDB persistent statistics are stored in `mysql.innodb_table_stats` and `mysql.innodb_index_stats`.
- Auto recalc typically triggers when roughly 10% of rows change, though it runs asynchronously and does not update instantaneously.
- `STATS_PERSISTENT`, `STATS_AUTO_RECALC`, and `STATS_SAMPLE_PAGES` allow per-table tuning.
- InnoDB uses sampling to estimate cardinality; raising sample pages can improve accuracy at higher cost.
- Histograms describe single-column distributions and are managed separately via `UPDATE HISTOGRAM`/`DROP HISTOGRAM`.
- Single-column histograms do not fully model multi-column correlations.
- Run `ANALYZE` after bulk loads, major data changes, or when execution plans show severe estimation errors.
- Do not run `ANALYZE` after every transaction or expect it to always speed up queries.
- Compare `EXPLAIN`, `EXPLAIN ANALYZE`, actual rows, and latency before and after.
- Evaluate locks, I/O, replication, and plan regressions when running in production.

`ANALYZE TABLE` is a tool for refreshing the information the optimizer relies on to make decisions. Running it at the right time—combined with persistent statistics, histograms, and execution plan measurement—helps MySQL choose access paths aligned with actual data while avoiding uncontrolled plan churn.

## References

- MySQL 8.0 Reference Manual — ANALYZE TABLE Statement: https://dev.mysql.com/doc/refman/8.0/en/analyze-table.html
- MySQL 8.0 Reference Manual — InnoDB Persistent Statistics: https://dev.mysql.com/doc/refman/8.0/en/innodb-persistent-stats.html
- MySQL 8.0 Reference Manual — InnoDB Statistics Estimation: https://dev.mysql.com/doc/refman/8.0/en/innodb-statistics-estimation.html
- MySQL 8.0 Reference Manual — Optimizer Statistics: https://dev.mysql.com/doc/refman/8.0/en/optimizer-statistics.html
