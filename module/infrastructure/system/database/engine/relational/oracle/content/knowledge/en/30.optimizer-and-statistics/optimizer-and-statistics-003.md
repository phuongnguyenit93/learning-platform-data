# Table, Column, Index Statistics, and System Information

The Oracle Database Optimizer uses statistics to estimate how many rows will be read, how many block accesses are required, and the CPU and I/O costs of each execution alternative. From those estimates, the optimizer selects the access path, join order, join method, and appropriate query transformations.

Statistics therefore directly affect execution plan quality. A table with millions of rows whose statistics still record only a few thousand rows can cause the optimizer to choose inappropriate nested loops or index access. A column with heavily skewed data distribution that only has a distinct value count can lead to wrong cardinality estimates. An index with a high clustering factor can require far more table block reads than expected when accessed via the index.

In Oracle, two categories of information should be distinguished:

- **Optimizer statistics:** describe data size, distribution, and I/O/CPU characteristics so the optimizer can estimate cost. This category is managed primarily through the `DBMS_STATS` package.
- **Runtime statistics and monitoring metrics:** reflect actual execution activity such as logical reads, physical reads, elapsed time, actual row counts, and execution counts. They are observed via execution plans, dynamic performance views, and monitoring tools.

Optimizer statistics are not runtime measurements of a SQL statement. Good statistics help the optimizer predict better, but estimates still need to be compared against actual statement behavior.

## 1. Categories of Statistics in Oracle

Optimizer statistics can be grouped into the following main categories:

| Category | Contents | Primary Impact |
|---|---|---|
| Table statistics | Row count, block count, average row length, empty block count | Estimate table size and full table scan cost |
| Column statistics | Number of distinct values, NULL count, min/max, density, and histograms | Estimate predicate selectivity and cardinality |
| Index statistics | BLEVEL, leaf blocks, distinct keys, clustering factor | Estimate cost of index range scan, index access, and table lookup |
| Partition statistics | Per-partition/subpartition statistics and global statistics | Estimate queries with partition pruning and table-wide queries |
| System statistics | System CPU speed and I/O characteristics | Compare costs of CPU, single-block I/O, and multiblock I/O |
| Dictionary/fixed object statistics | Data dictionary and fixed table statistics | Help the optimizer estimate administrative and internal queries |

These categories complement one another. Table statistics can be accurate while a missing or wrong column histogram still causes the optimizer to misestimate predicates. Good column statistics paired with stale index statistics can still cause index access costs to be misjudged. System statistics do not describe a specific table; they describe the characteristics of the execution environment.

## 2. Viewing Table Statistics

Table statistics describe the physical and logical scale of a table. Common attributes include:

| Attribute | Meaning |
|---|---|
| `NUM_ROWS` | Number of rows recorded at gather time |
| `BLOCKS` | Estimated number of blocks containing table data |
| `EMPTY_BLOCKS` | Number of empty blocks recorded depending on gathering method |
| `AVG_ROW_LEN` | Average row length in bytes |
| `SAMPLE_SIZE` | Number of rows sampled when gathering statistics |
| `LAST_ANALYZED` | Timestamp of the most recent statistics collection |
| `STALE_STATS` | Indicates whether statistics are marked as stale |
| `GLOBAL_STATS` | Indicates whether statistics are global or aggregated from lower-level statistics, depending on object type |
| `STATTYPE_LOCKED` | Indicates which statistics types are locked, if any |

Commonly used views:

- `USER_TAB_STATISTICS`: table, partition, and subpartition statistics in the current schema.
- `ALL_TAB_STATISTICS`: statistics for tables whose metadata the current user can access.
- `DBA_TAB_STATISTICS`: database-wide statistics, requiring appropriate privileges.
- `USER_TABLES`, `ALL_TABLES`, `DBA_TABLES`: table metadata along with several familiar statistics attributes.

Example of viewing global statistics for tables in the current schema:

```sql
SELECT table_name,
       num_rows,
       blocks,
       avg_row_len,
       sample_size,
       last_analyzed,
       stale_stats,
       stattype_locked
FROM user_tab_statistics
WHERE partition_name IS NULL
  AND subpartition_name IS NULL
  AND object_type = 'TABLE'
ORDER BY table_name;
```

For partitioned tables, rows with `PARTITION_NAME` or `SUBPARTITION_NAME` hold statistics at the corresponding level. Rows without a partition name generally represent global table statistics. When inspecting, make sure you know whether you are looking at global statistics or a specific partition's statistics.

`NUM_ROWS` and `BLOCKS` are values used by the optimizer from the most recent gather; they do not necessarily equal the current row and block counts. A table that has just received bulk inserts may have grown dramatically while its statistics retain the old numbers until refreshed.

### 2.1. How Do Table Statistics Affect Execution Plans?

Suppose a query reads the `ORDERS` table:

```sql
SELECT order_id, order_date, total_amount
FROM orders
WHERE order_date >= DATE '2026-01-01';
```

The optimizer needs to estimate:

1. Roughly how many rows and blocks does the table have?
2. How many rows is the `order_date >= ...` predicate likely to retain?
3. Is reading via an index and visiting table blocks cheaper than scanning the entire table?
4. If the query joins additional tables, which table should it start with?

`NUM_ROWS`, `BLOCKS`, and column/index statistics all contribute to these estimates. If `NUM_ROWS` is too low, the optimizer may underestimate the work required. If `BLOCKS` does not reflect actual size, the full table scan cost may be misestimated.

Do not manually edit statistics just to force the optimizer to pick a plan. If numbers are inaccurate, find the root cause in the gathering process, sampling, partitioning, or workload, and refresh statistics against actual data.

## 3. Column Statistics and Selectivity

Column statistics describe the value distribution of each column. Common attributes include:

| Attribute | Meaning |
|---|---|
| `NUM_DISTINCT` | Estimated number of distinct values |
| `NUM_NULLS` | Estimated number of NULL values |
| `DENSITY` | Density information used by the optimizer when estimating predicates; exact interpretation depends on statistics type and histogram |
| `LOW_VALUE` / `HIGH_VALUE` | Lowest/highest recorded values, stored in internal representation |
| `NUM_BUCKETS` | Number of histogram buckets, if present |
| `HISTOGRAM` | Type of histogram created for the column |
| `AVG_COL_LEN` | Average data length of the column |
| `SAMPLE_SIZE` | Sample size used to collect statistics |

View column statistics in the current schema:

```sql
SELECT table_name,
       column_name,
       num_distinct,
       num_nulls,
       density,
       histogram,
       num_buckets,
       avg_col_len,
       last_analyzed
FROM user_tab_col_statistics
WHERE table_name = 'ORDERS'
ORDER BY column_name;
```

Table names in the data dictionary are typically stored in uppercase if the object was created without double quotes. If an object was created using a quoted identifier, use the exact declared casing.

### 3.1. NUM_DISTINCT and Selectivity Estimation

Selectivity represents the fraction of rows a filter condition is expected to retain. For a nearly uniformly distributed column, you can picture an equality predicate on a specific value retaining roughly one over the number of distinct values. However, this is only an initial intuition; the optimizer uses more information, and you should not assume every cardinality is calculated solely by `1 / NUM_DISTINCT`.

For example, the `ORDER_STATUS` column has 5 distinct values:

| ORDER_STATUS | Rows |
|---|---:|
| NEW | 500,000 |
| PAID | 400,000 |
| SHIPPED | 90,000 |
| CANCELLED | 9,000 |
| RETURNED | 1,000 |

`NUM_DISTINCT = 5` does not say that each value appears in 20% of rows. If the optimizer assumes a uniform distribution while the application frequently queries `RETURNED`, cardinality can be vastly overestimated. Histograms supply additional information about this skew.

### 3.2. Histograms Help Describe Skewed Data

Histograms divide the value domain into buckets to describe data distribution in finer detail. They are especially useful when some values occur far more frequently than others and the workload filters on that column.

Common histogram types:

- **Frequency histogram:** stores frequencies per value when the number of distinct values fits within the bucket count.
- **Top-frequency histogram:** focuses on describing the most common values and the rest of the distribution.
- **Hybrid histogram:** combines frequency and bucket distribution information to improve estimates on skewed data.
- **Height-balanced histogram:** a histogram type found in older versions or configurations; check version context when reading metadata.

Example of a status column with widely varying row counts:

```text
NEW        ##############################
PAID       ########################
SHIPPED    ######
CANCELLED  #
RETURNED   .
```

If a query filters `ORDER_STATUS = 'RETURNED'`, a histogram helps the optimizer recognize that this predicate selects very few rows. If a query filters `ORDER_STATUS = 'NEW'`, the optimizer can judge that most of the table must be read and a full table scan may be more suitable than index access.

Gather histograms via `METHOD_OPT` in `DBMS_STATS`:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => 'APP',
        tabname          => 'ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => DBMS_STATS.AUTO_CASCADE
    );
END;
/
```

`SIZE AUTO` lets Oracle decide which columns need histograms based on column usage information and data distribution. Histograms are not always better. When data changes or different bind values have very different selectivities, histograms can cause different parses to select different plans. Inspect execution plans for the actual workload after changing histograms.

You can request a specific bucket count for a column:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname    => 'APP',
        tabname    => 'ORDERS',
        method_opt => 'FOR COLUMNS ORDER_STATUS SIZE 10'
    );
END;
/
```

This is a deliberate configuration; use it only once you understand the distribution and workload predicates. Do not apply an arbitrary bucket count uniformly to all columns across all tables.

### 3.3. Viewing Histograms

`USER_TAB_HISTOGRAMS`, `ALL_TAB_HISTOGRAMS`, and `DBA_TAB_HISTOGRAMS` provide histogram endpoints. Example:

```sql
SELECT table_name,
       column_name,
       endpoint_number,
       endpoint_value
FROM user_tab_histograms
WHERE table_name = 'ORDERS'
  AND column_name = 'ORDER_STATUS'
ORDER BY endpoint_number;
```

`ENDPOINT_VALUE` is an internal endpoint representation in metadata and is not always displayed directly as the original column value. Some versions include `ENDPOINT_ACTUAL_VALUE`; check the data dictionary of your running version before relying on that column. `LOW_VALUE` and `HIGH_VALUE` in column statistics are also stored as RAW and should not be read as plain text strings.

## 4. Multi-Column Statistics and Expression Statistics

Individual column statistics cannot describe every relationship between columns. Suppose the `CUSTOMERS` table has `COUNTRY_CODE` and `STATE_CODE`. If a state belongs to only one country, the two columns are strongly correlated. The optimizer can overestimate or underestimate row counts when seeing predicates on both columns together if it only knows individual column statistics.

Oracle supports **extended statistics** to describe column groups or expressions. Example of creating a column group:

```sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
           ownname   => 'APP',
           tabname   => 'CUSTOMERS',
           extension => '(COUNTRY_CODE, STATE_CODE)'
       )
FROM dual;
```

After creating the extension, re-gather table statistics:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => 'APP',
        tabname          => 'CUSTOMERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO'
    );
END;
/
```

For predicates using expressions, you can create expression statistics. For example, queries frequently filtering with `UPPER(CUSTOMER_NAME)`:

```sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
           ownname   => 'APP',
           tabname   => 'CUSTOMERS',
           extension => '(UPPER(CUSTOMER_NAME))'
       )
FROM dual;
```

Extended statistics provide information to the optimizer; they do not create an index and do not replace checking access paths. If the workload needs an index on an expression, consider a function-based index as a separate design decision.

You can inspect created extensions in `USER_STAT_EXTENSIONS` or the corresponding broader view. Before creating column groups in bulk, observe which columns are actually used together in predicates. `DBMS_STATS.REPORT_COL_USAGE` can help inspect the column usage information Oracle has recorded:

```sql
SELECT DBMS_STATS.REPORT_COL_USAGE('APP', 'CUSTOMERS')
FROM dual;
```

The output helps identify columns frequently appearing in equality predicates, range predicates, or predicate groups. Column usage tracking depends on the workload that has run and the observation window; it does not represent every query that may appear in the future.

## 5. Index Statistics

Index statistics describe index structure and the relationship between key ordering in the index and row placement in the table. Key attributes include:

| Attribute | Meaning |
|---|---|
| `BLEVEL` | Number of branch levels from root to leaf; deeper indexes may have longer paths to leaf blocks |
| `LEAF_BLOCKS` | Number of leaf blocks in the index |
| `DISTINCT_KEYS` | Number of distinct keys recorded; for composite indexes, the number of distinct key combinations |
| `AVG_LEAF_BLOCKS_PER_KEY` | Average number of leaf blocks per key |
| `AVG_DATA_BLOCKS_PER_KEY` | Average number of table blocks accessed per key |
| `CLUSTERING_FACTOR` | Degree of correlation between index key order and physical row placement in table blocks |
| `NUM_ROWS` | Number of rows recorded for the index |
| `LAST_ANALYZED` | Timestamp of the most recent index statistics |

View index statistics for the `ORDERS` table:

```sql
SELECT index_name,
       blevel,
       leaf_blocks,
       distinct_keys,
       avg_leaf_blocks_per_key,
       avg_data_blocks_per_key,
       clustering_factor,
       num_rows,
       last_analyzed,
       stale_stats
FROM user_ind_statistics
WHERE table_name = 'ORDERS'
  AND partition_name IS NULL
ORDER BY index_name;
```

### 5.1. BLEVEL and LEAF_BLOCKS

A B-tree index has branch blocks leading to leaf blocks containing keys and rowids. `BLEVEL` describes the number of branch levels; `LEAF_BLOCKS` describes the number of leaf blocks. These values factor into estimating block reads when using the index.

An index with many leaf blocks may be large because the table has many rows or the keys take up substantial space. A higher BLEVEL can lengthen traversal to leaves, but you cannot conclude an index needs rebuilding based solely on a BLEVEL number. Consider index size, workload, growth rate, and actual plans.

### 5.2. DISTINCT_KEYS and Index Selectivity

`DISTINCT_KEYS` indicates the number of distinct keys recorded. If an index has many distinct keys relative to row count, equality predicates on the key can be highly selective. If an index has only a few values repeated across most rows, index access may be less attractive than a full table scan depending on table size and clustering factor.

For composite indexes, column order in the key is critical to index usability. `DISTINCT_KEYS` describes the full key combination; also check individual column statistics and actual predicates to understand the selectivity of leading column subsets.

### 5.3. CLUSTERING_FACTOR

Clustering factor estimates how closely rowids in index key order sit together within table blocks.

- A relatively low value, close to the table's block count, generally indicates that rows with adjacent keys reside in fewer table blocks. An index range scan may need fewer table block reads.
- A relatively high value, close to the table's row count, generally indicates that rowids point across many different table blocks. An index range scan may need many table block accesses.

For example, a table storing orders sequentially by `ORDER_DATE` may have a favorable clustering factor for an index on `ORDER_DATE`. If a table is inserted ordered by `CUSTOMER_ID` while a query performs a range scan on a different column, the corresponding index's clustering factor can be high.

Clustering factor is an estimation metric, not an absolute quality score. It must be evaluated against the block count and row count of that specific table. Do not compare clustering factors of two tables of vastly different sizes to conclude which index is better.

### 5.4. Gathering Index Statistics

When gathering table statistics, the `CASCADE` parameter controls how related index statistics are gathered:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => 'APP',
        tabname          => 'ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => DBMS_STATS.AUTO_CASCADE
    );
END;
/
```

`AUTO_CASCADE` lets Oracle decide whether to gather index statistics. You can use `CASCADE => TRUE` when you explicitly want statistics gathered for related indexes. Do not assume gathering table statistics always guarantees all index statistics are refreshed as expected; check `LAST_ANALYZED` and `STALE_STATS` on the indexes.

## 6. Partition Statistics and Global Statistics

For partitioned tables, Oracle can store statistics at multiple levels:

- **Partition statistics:** describe data within each partition.
- **Subpartition statistics:** describe data within each subpartition if the table is subpartitioned.
- **Global statistics:** describe the entire partitioned table.

Queries reading only one partition after partition pruning can benefit from that partition's statistics. Queries reading multiple partitions or the whole table need accurate global statistics so the optimizer can estimate overall data volume.

You can instruct Oracle to pick appropriate granularity when gathering:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => 'APP',
        tabname          => 'SALES',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        granularity      => 'AUTO',
        cascade          => DBMS_STATS.AUTO_CASCADE
    );
END;
/
```

For very large partitioned tables, you can enable incremental statistics at the table level:

```sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => 'APP',
        tabname => 'SALES',
        pname   => 'INCREMENTAL',
        pvalue  => 'TRUE'
    );
END;
/
```

Incremental statistics use synopses to aggregate global statistics from partitions, reducing the amount of data that must be re-scanned when only some partitions change. Verify support and proper configuration for your Oracle version, partition type, and operational policies. Enabling incremental does not mean queries automatically run faster; the primary benefit is maintaining global statistics efficiently for large tables.

After gathering, inspect both the global row and individual partitions:

```sql
SELECT table_name,
       partition_name,
       num_rows,
       blocks,
       sample_size,
       last_analyzed,
       stale_stats,
       global_stats
FROM user_tab_statistics
WHERE table_name = 'SALES'
ORDER BY partition_name NULLS FIRST;
```

If you gather only a new partition without keeping global statistics appropriately updated, the optimizer may rely on stale global figures. This is an important check after bulk loads, partition exchanges, or creating new partitions.

## 7. System Statistics and CPU/I/O Characteristics

Table, column, and index statistics describe data. **System statistics** describe hardware and I/O characteristics used by the optimizer in its cost model. They help the optimizer compare the costs of operations depending on CPU, single-block reads, and multiblock reads.

Common system statistics values:

| Name | General Meaning |
|---|---|
| `CPUSPEED` | CPU speed measured during workload statistics |
| `CPUSPEEDNW` | CPU speed in no-workload statistics |
| `SREADTIM` | Average single-block read time |
| `MREADTIM` | Average multiblock read time |
| `MBRC` | Average number of blocks per multiblock read |
| `IOSEEKTIM` | I/O seek time component in the no-workload model |
| `IOTFRSPEED` | I/O transfer speed in the no-workload model |

System statistics help the optimizer evaluate whether a full table scan is cheaper or more expensive than index access in a given environment. The same schema and identical data on two systems with different I/O characteristics can yield different plans.

### 7.1. Gathering System Statistics

You can gather system statistics using the no-workload model:

```sql
BEGIN
    DBMS_STATS.GATHER_SYSTEM_STATS('NOWORKLOAD');
END;
/
```

Or measure during a representative workload window:

```sql
BEGIN
    DBMS_STATS.GATHER_SYSTEM_STATS('START');
END;
/
```

After the system has run a workload representative of normal operations:

```sql
BEGIN
    DBMS_STATS.GATHER_SYSTEM_STATS('STOP');
END;
/
```

The measurement window should reflect the activity the database actually serves, including read/write ratios and common query patterns. Measuring when the database is nearly idle or running an unusual batch job can produce system statistics unrepresentative of normal operations.

You can read individual values via the `DBMS_STATS` API:

```sql
DECLARE
    l_value NUMBER;
BEGIN
    DBMS_STATS.GET_SYSTEM_STATS('SREADTIM', l_value);
    DBMS_OUTPUT.PUT_LINE('SREADTIM = ' || NVL(TO_CHAR(l_value), 'NULL'));

    DBMS_STATS.GET_SYSTEM_STATS('MREADTIM', l_value);
    DBMS_OUTPUT.PUT_LINE('MREADTIM = ' || NVL(TO_CHAR(l_value), 'NULL'));

    DBMS_STATS.GET_SYSTEM_STATS('MBRC', l_value);
    DBMS_OUTPUT.PUT_LINE('MBRC = ' || NVL(TO_CHAR(l_value), 'NULL'));
END;
/
```

Do not directly modify internal tables storing system statistics. Use the Oracle-provided `DBMS_STATS` API and follow controlled change procedures. Re-gathering system statistics can alter the cost model and cause plan changes across many SQL statements, so evaluate impact before and after the change.

### 7.2. System Statistics vs. V$SYSSTAT

Similar naming can cause confusion:

- `DBMS_STATS` system statistics are CPU/I/O metrics for the cost-based optimizer.
- `V$SYSSTAT` contains instance activity counters, such as logical reads, physical reads, or redo size.

Example of checking several runtime counters:

```sql
SELECT name, value
FROM v$sysstat
WHERE name IN (
    'session logical reads',
    'physical reads',
    'physical writes',
    'redo size'
)
ORDER BY name;
```

Values in `V$SYSSTAT` are generally cumulative counters since instance startup or per counter scope. To measure an interval, take two snapshots and compute the difference, watching out for resets due to restarts or instance changes. They do not replace `SREADTIM`, `MREADTIM`, or `CPUSPEED` in optimizer system statistics.

## 8. Dictionary Statistics and Fixed Object Statistics

Beyond business tables, Oracle maintains the data dictionary and fixed tables. These objects are queried during administration, metadata analysis, and internal operations. When their statistics are inappropriate, administrative queries or queries referencing the dictionary can be misestimated by the optimizer.

`DBMS_STATS` provides dedicated procedures:

```sql
BEGIN
    DBMS_STATS.GATHER_DICTIONARY_STATS;
END;
/
```

This procedure gathers statistics for the data dictionary according to Oracle's supported scope and rules. Run it according to operational guidelines for your database version, especially after upgrades or major dictionary changes.

Fixed object statistics can be gathered with:

```sql
BEGIN
    DBMS_STATS.GATHER_FIXED_OBJECTS_STATS;
END;
/
```

Fixed tables typically expose dynamic instance/session information and behave differently from regular business tables. Gather fixed object statistics once the database has a representative workload so estimates reflect realistic operating conditions. Do not run this procedure mechanically on every application deployment.

## 9. Gathering and Maintaining Statistics with DBMS_STATS

`DBMS_STATS` is the standard API for gathering, managing, exporting, importing, and restoring optimizer statistics. Prefer this package over the legacy `ANALYZE` command in standard optimizer statistics management workflows.

### 9.1. Gathering Statistics for a Table

Basic example:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => 'APP',
        tabname          => 'ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => DBMS_STATS.AUTO_CASCADE,
        degree           => DBMS_STATS.DEFAULT_DEGREE,
        granularity      => 'AUTO',
        no_invalidate    => DBMS_STATS.AUTO_INVALIDATE
    );
END;
/
```

Meaning of key parameters:

- `OWNNAME`, `TABNAME`: schema and table to gather.
- `ESTIMATE_PERCENT`: sampling percentage; `DBMS_STATS.AUTO_SAMPLE_SIZE` lets Oracle automatically choose an appropriate sampling method.
- `METHOD_OPT`: how column statistics and histograms are collected.
- `CASCADE`: whether to gather index statistics; `AUTO_CASCADE` lets Oracle decide.
- `DEGREE`: degree of parallelism while gathering.
- `GRANULARITY`: statistics level to collect, especially for partitioned tables.
- `NO_INVALIDATE`: invalidation policy for cursors dependent on the new statistics; `AUTO_INVALIDATE` lets Oracle manage invalidation timing.

You do not need to default to `ESTIMATE_PERCENT => 100`. A full scan to sample 100% can consume substantial resources and is usually unnecessary because Oracle has automatic sampling mechanisms. Change sampling only with clear measurement-backed justification.

### 9.2. Gathering Statistics for a Schema or Database

You can gather statistics for stale tables in a schema:

```sql
BEGIN
    DBMS_STATS.GATHER_SCHEMA_STATS(
        ownname          => 'APP',
        options          => 'GATHER STALE',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => DBMS_STATS.AUTO_CASCADE,
        degree           => DBMS_STATS.DEFAULT_DEGREE
    );
END;
/
```

Common `OPTIONS` values in schema/database gather procedures include:

- `GATHER`: gather across the specified scope.
- `GATHER STALE`: focus on objects marked as having stale statistics.
- `GATHER EMPTY`: focus on objects with no statistics yet.
- `GATHER AUTO`: let Oracle decide which objects need gathering based on current state and policy.

Verify procedure signatures and options against your running Oracle version. For very large schemas, weigh duration, degree, parallelism, and I/O load before gathering broadly.

### 9.3. Setting Preferences

`DBMS_STATS` supports setting preferences at the table, schema, or database level. This establishes consistent policies without re-passing every parameter on each call.

Example of setting preferences for the `ORDERS` table:

```sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => 'APP',
        tabname => 'ORDERS',
        pname   => 'STALE_PERCENT',
        pvalue  => '10'
    );

    DBMS_STATS.SET_TABLE_PREFS(
        ownname => 'APP',
        tabname => 'ORDERS',
        pname   => 'METHOD_OPT',
        pvalue  => 'FOR ALL COLUMNS SIZE AUTO'
    );
END;
/
```

Commonly managed preferences:

| Preference | Role |
|---|---|
| `STALE_PERCENT` | Data change threshold for considering statistics stale |
| `ESTIMATE_PERCENT` | Sampling policy |
| `METHOD_OPT` | Column statistics and histogram policy |
| `CASCADE` | Index statistics gathering policy |
| `DEGREE` | Parallelism degree used during gathering |
| `GRANULARITY` | Statistics level for partitioned tables |
| `INCREMENTAL` | Enable/disable incremental statistics for eligible partitioned tables |
| `PUBLISH` | Controls whether new statistics are published immediately or kept pending |
| `NO_INVALIDATE` | Cursor invalidation policy after publishing |

You can check preference values using `DBMS_STATS.GET_PREFS`:

```sql
SELECT DBMS_STATS.GET_PREFS(
           pname   => 'STALE_PERCENT',
           ownname => 'APP',
           tabname => 'ORDERS'
       ) AS stale_percent
FROM dual;
```

Table-level preferences can override broader preferences. When diagnosing why a gather behaved unexpectedly, check both the explicitly passed parameters and the active preferences in effect.

## 10. Stale Statistics and Automatic Collection

Statistics can become stale when data changes substantially after the last gather. Oracle tracks modifications such as inserts, updates, and deletes to determine which objects need refreshing. The default threshold is typically 10% change, though it can be adjusted via the `STALE_PERCENT` preference.

You can check stale status:

```sql
SELECT owner,
       table_name,
       partition_name,
       num_rows,
       last_analyzed,
       stale_stats
FROM dba_tab_statistics
WHERE owner = 'APP'
  AND object_type = 'TABLE'
ORDER BY table_name, partition_name;
```

To inspect DML modifications recorded in the monitoring view, flush monitoring information first:

```sql
BEGIN
    DBMS_STATS.FLUSH_DATABASE_MONITORING_INFO;
END;
/
```

```sql
SELECT table_owner,
       table_name,
       inserts,
       updates,
       deletes
FROM dba_tab_modifications
WHERE table_owner = 'APP'
ORDER BY table_name;
```

`DBA_TAB_MODIFICATIONS` is monitoring metadata for tracking changes, not a complete audit log of every DML statement. Counts are updated according to the monitoring mechanism and flush timing; combine it with `STALE_STATS`, `LAST_ANALYZED`, and actual data load activity.

Oracle includes automatic optimizer statistics collection through automated maintenance tasks during maintenance windows. This mechanism typically handles objects needing statistics according to system policy. However, tables experiencing large bulk loads, new partitions, sudden distribution shifts, or sensitive workloads still require monitoring and may need dedicated gathering workflows.

Do not re-gather the entire database after every application deployment. Identify changed objects, check statistics status, and gather only within the needed scope. Gathering statistics also consumes CPU and I/O and can affect plans for many SQL statements.

## 11. Pending Statistics and Testing Plans Before Publishing

When a statistics change risks impacting many SQL statements, you can gather them as **pending statistics**. New statistics are not yet published to all sessions. A test session can enable pending statistics to evaluate plans.

Example configuring a table not to publish immediately:

```sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => 'APP',
        tabname => 'ORDERS',
        pname   => 'PUBLISH',
        pvalue  => 'FALSE'
    );

    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => 'APP',
        tabname          => 'ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => DBMS_STATS.AUTO_CASCADE
    );
END;
/
```

In the test session:

```sql
ALTER SESSION SET optimizer_use_pending_statistics = TRUE;
```

Run representative SQL statements and inspect execution plans. Sessions without this parameter enabled continue using published statistics. Once test results are satisfactory, publish them:

```sql
BEGIN
    DBMS_STATS.PUBLISH_PENDING_STATS(
        ownname => 'APP',
        tabname => 'ORDERS'
    );
END;
/
```

If you do not want to use the pending statistics, delete them:

```sql
BEGIN
    DBMS_STATS.DELETE_PENDING_STATS(
        ownname => 'APP',
        tabname => 'ORDERS'
    );
END;
/
```

After finishing, restore the `PUBLISH` preference according to the table's policy. Pending statistics help validate plans before publishing, but tests must represent real bind values, workloads, session settings, and environments. A few isolated SQL statements do not guarantee every query gets a better plan.

## 12. Locking, Archiving, and Restoring Statistics

### 12.1. Lock Statistics

In special cases, a DBA may lock a table's or schema's statistics to prevent automatic gathering from changing them unexpectedly:

```sql
BEGIN
    DBMS_STATS.LOCK_TABLE_STATS(
        ownname => 'APP',
        tabname => 'REFERENCE_CODES'
    );
END;
/
```

Unlock when updates are needed:

```sql
BEGIN
    DBMS_STATS.UNLOCK_TABLE_STATS(
        ownname => 'APP',
        tabname => 'REFERENCE_CODES'
    );
END;
/
```

Locking statistics is a change-control tool, not a long-term fix for cardinality errors. If data changes substantially while statistics remain locked, the optimizer will keep using outdated figures. Document the reason for locking, the owner, and the conditions for unlocking.

### 12.2. Statistics History and Restore

Oracle retains statistics history for a configurable retention period. If new statistics degrade plans, a DBA can restore previous figures if the history snapshot is still within retention.

Example restoring table statistics to an earlier timestamp:

```sql
BEGIN
    DBMS_STATS.RESTORE_TABLE_STATS(
        ownname         => 'APP',
        tabname         => 'ORDERS',
        as_of_timestamp => SYSTIMESTAMP - INTERVAL '1' DAY
    );
END;
/
```

The target timestamp must lie within the available history window. Check the oldest available timestamp with `DBMS_STATS.GET_STATS_HISTORY_AVAILABILITY` and check retention with `DBMS_STATS.GET_STATS_HISTORY_RETENTION`. Increasing retention requires weighing SYSAUX storage capacity and administrative policy.

Restoring statistics only changes optimizer statistics metadata; it does not revert table data to an earlier state and does not undo DML. After restoring, check plans and related cursor state.

### 12.3. Exporting/Importing Statistics Using a Statistics Table

For major changes, you can save a separate statistics snapshot for comparison or transfer to another environment. Create a statistics table once:

```sql
BEGIN
    DBMS_STATS.CREATE_STAT_TABLE(
        ownname => 'APP',
        stattab => 'STATS_BACKUP'
    );
END;
/
```

Export table statistics:

```sql
BEGIN
    DBMS_STATS.EXPORT_TABLE_STATS(
        ownname => 'APP',
        tabname => 'ORDERS',
        stattab => 'STATS_BACKUP',
        statid  => 'ORDERS_BEFORE_CHANGE'
    );
END;
/
```

When re-importing is needed:

```sql
BEGIN
    DBMS_STATS.IMPORT_TABLE_STATS(
        ownname => 'APP',
        tabname => 'ORDERS',
        stattab => 'STATS_BACKUP',
        statid  => 'ORDERS_BEFORE_CHANGE'
    );
END;
/
```

Exported statistics are a metadata copy. When transferring statistics across environments with different structures, data, versions, or CPU/I/O characteristics, do not assume plans will match or remain suitable. Statistics tables should also be protected like administrative data with their own backup and cleanup policies.

## 13. Comparing Optimizer Estimates with Reality

Statistics are only useful when estimates align closely with reality. When a SQL statement runs slowly, inspect the execution plan and compare estimated rows against actual rows.

You can instruct Oracle to collect runtime row-source statistics for a SQL statement using a hint:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id,
       total_amount
FROM app.orders
WHERE order_status = 'RETURNED';
```

After running the SQL in the same session, inspect the cursor just executed:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST'
    )
);
```

In the output, watch for:

- `E-Rows`: number of rows estimated by the optimizer.
- `A-Rows`: actual rows at the row source, if runtime statistics were collected.
- `Starts`: number of times the row source was started.
- `Buffers`: logical reads recorded for the row source.
- `Reads`: physical reads recorded, if any.
- `A-Time`: actual elapsed time recorded for the row source per plan format.

If `E-Rows` differs significantly from `A-Rows`, check column statistics, histograms, extended statistics, bind values, predicates, partition statistics, and filter conditions. If estimated rows are close to actuals yet elapsed time remains high, the issue may lie in I/O, contention, join methods, resource allocation, networking, or other runtime factors.

Do not conclude statistics are the sole cause simply because SQL is slow. Also inspect plan hash, optimizer environment, bind peeking, adaptive cursor sharing, any SQL profiles/baselines in use, and data changes since the last gather.

## 14. Practical Workflow When Statistics Are No Longer Appropriate

When a poor plan or cardinality misestimate is detected, investigate in this sequence:

1. **Identify the SQL and actual plan:** obtain SQL ID, child cursor, plan hash, and runtime row-source statistics.
2. **Locate the misestimated step:** compare `E-Rows` with `A-Rows` to pinpoint which predicate or join starts diverging.
3. **Check table statistics:** inspect `NUM_ROWS`, `BLOCKS`, `LAST_ANALYZED`, `STALE_STATS`, and partition/global statistics.
4. **Check column statistics:** inspect `NUM_DISTINCT`, `NUM_NULLS`, `DENSITY`, histograms, and actual data skew.
5. **Check index statistics:** inspect `BLEVEL`, `LEAF_BLOCKS`, `DISTINCT_KEYS`, `CLUSTERING_FACTOR`, and gather timestamps.
6. **Check column correlations:** if multiple predicates reference correlated columns, assess the need for extended statistics.
7. **Check system statistics:** if CPU/I/O costs appear skewed, confirm system statistics reflect the current environment.
8. **Gather within the needed scope:** use `DBMS_STATS` with appropriate sampling, histograms, and cascade settings.
9. **Test before publishing if high risk:** use pending statistics and an isolated session to compare plans.
10. **Monitor after changes:** check representative SQL statements, cursor invalidations, runtime, and overall workload.

Mistakes to avoid:

- Gathering statistics database-wide indiscriminately after every deployment.
- Using `ESTIMATE_PERCENT => 100` for every table without weighing cost.
- Creating histograms on every column or setting the same bucket count for all columns.
- Rebuilding an index simply because `BLEVEL` or `CLUSTERING_FACTOR` looks high without analyzing the workload.
- Checking only global statistics when the problem lies in a partition, or vice versa.
- Modifying Oracle internal tables directly to alter optimizer statistics.
- Treating `V$SYSSTAT` as though it were cost-based optimizer system statistics.
- Locking statistics and forgetting to refresh them when data changes.
- Publishing new statistics without testing affected critical SQL statements.

## 15. Operational Checklist

When managing statistics for a critical business table, a DBA or developer can use the following checklist:

| Area | Question to Answer |
|---|---|
| Table statistics | Do `NUM_ROWS`, `BLOCKS`, and `LAST_ANALYZED` reflect current data? |
| Column statistics | Do filter/join columns have appropriate `NUM_DISTINCT`, `NUM_NULLS`, and histograms? |
| Skew | Are there unusually rare or common values affecting predicates? |
| Column correlation | Do predicates use correlated columns that require extended statistics? |
| Index statistics | Are BLEVEL, leaf blocks, distinct keys, and clustering factor consistent with data structure? |
| Partition | Have partition stats and global stats both been refreshed appropriately? |
| System statistics | Do CPU/I/O statistics represent current hardware and workload? |
| Freshness | Are statistics stale or locked on the object? |
| Execution plan | Are estimated rows close to actual rows at critical steps? |
| Change control | Is there history or an export snapshot to restore if plans regress? |

Statistics are part of database operations. Collecting the right types, at the right scope, and at the right time gives the optimizer sound data for selecting execution plans. When plans misbehave, use dictionary views and runtime plan statistics to pinpoint exact discrepancies, then refresh or test statistics under control. This approach sustains stable performance without relying on guesswork plan forcing or ad-hoc database structural changes.
