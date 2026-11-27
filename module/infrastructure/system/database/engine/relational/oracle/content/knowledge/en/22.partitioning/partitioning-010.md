# Partition-Level Statistics and Incremental Statistics in Oracle Database

For partitioned tables, the optimizer requires sufficiently accurate statistics at multiple levels to estimate row counts, choose join orders, determine access paths, and leverage partition pruning. DBAs can gather statistics for individual partitions, for the entire table, or at both levels. On a massive table where only a few partitions change daily, scanning the entire table to recompute global statistics can consume excessive time and resources.

Oracle supports **incremental statistics** to reduce this workload. When incremental statistics are enabled on a partitioned table, Oracle maintains synopses (statistical summaries) for partitions. When a partition changes and its statistics are gathered, Oracle can combine the synopses with partition statistics to update global statistics without rescanning all data in unchanged partitions.

Distinguish three levels of information:

- **Partition statistics:** describe data within an individual partition.
- **Global statistics:** describe the entire partitioned table as one logical object.
- **Incremental statistics:** a mechanism for maintaining certain global statistics from partition synopses, reducing cost when only part of the data changes.

This lesson explains why the optimizer needs partition-level statistics, how to inspect and gather partition/global statistics, how to enable incremental statistics using DBMS_STATS, how synopses support global statistics, workflows for new or modified partitions, monitoring stale statistics, and operational considerations.

## 1. Why Do Partitioned Tables Need Multi-Level Statistics?

### 1.1. Partition pruning is only part of the execution decision

Suppose table SALES is partitioned monthly on SALE_DATE. Query:

```sql
SELECT product_id,
       SUM(amount)
FROM   sales
WHERE  sale_date >= DATE '2026-03-01'
AND    sale_date <  DATE '2026-04-01'
GROUP  BY product_id;
```

The optimizer can eliminate partitions outside March 2026 via partition pruning. Yet after determining which partition to read, the optimizer still needs statistics to estimate row counts, block counts, predicate selectivity, and join/aggregate costs.

Partition pruning narrows the data scope to access; statistics help the optimizer choose how to process that scope.

### 1.2. Partition statistics

Partition statistics describe a single partition. For example, a March partition has:
- Row count.
- Block count.
- Average row length.
- Column statistics.
- Histograms if gathered.
- Last analyzed timestamp and stale status.

Partitions can have very different data distributions. A new partition may contain more rows than older partitions; a regional partition may contain a concentrated subset of values. Looking only at overall statistics can prevent the optimizer from estimating accurately when a query accesses a single specific partition.

### 1.3. Global statistics

Global statistics describe the entire partitioned table. They are useful when:
- Queries access multiple partitions.
- Predicates do not directly constrain the partition key.
- The optimizer needs overall estimates for joining with other tables.
- Queries aggregate data across the entire table.
- Cardinality estimates across many partitions are needed.

Example query filtering on PRODUCT_ID without constraining SALE_DATE:

```sql
SELECT *
FROM   sales
WHERE  product_id = 500;
```

The query may have to examine many partitions. Global statistics on PRODUCT_ID across the whole table can be crucial for overall estimation.

### 1.4. Partition statistics and global statistics complement each other

| Statistics level | Scope | Typically useful when |
| --- | --- | --- |
| Partition | One partition | Queries partition-prune down to one or a few partitions |
| Subpartition | One subpartition in a composite-partitioned table | Queries and access strategies need finer subpartition-level statistics |
| Global | Entire table | Queries span multiple partitions or need table-wide estimates |

Do not assume global statistics always replace partition statistics or vice versa. The optimizer may require both depending on predicates, partition pruning, partitioning type, and query plan.

## 2. Types of Statistics on Partitioned Tables

### 2.1. Table-level statistics

At the table level, Oracle stores aggregate metrics such as:
- NUM_ROWS: estimated row count.
- BLOCKS: analyzed block count.
- AVG_ROW_LEN: average row length.
- Column statistics and histograms.
- LAST_ANALYZED: collection timestamp.
- GLOBAL_STATS: indicator of global statistics origin/generation per dictionary rules.
- STALE_STATS: staleness status per monitoring mechanisms and configured thresholds.

For a partitioned table, the table-level row represents global statistics.

### 2.2. Partition and subpartition statistics

A partitioned table can have a statistics row for each partition. A composite-partitioned table also has subpartition statistics.

RANGE-HASH table example:

```sql
CREATE TABLE sales_demo (
    sale_id     NUMBER NOT NULL,
    sale_date   DATE NOT NULL,
    product_id  NUMBER NOT NULL,
    amount      NUMBER(12,2)
)
PARTITION BY RANGE (sale_date)
SUBPARTITION BY HASH (product_id)
SUBPARTITIONS 4
(
    PARTITION p2026_01 VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN (DATE '2026-03-01'),
    PARTITION pmax     VALUES LESS THAN (MAXVALUE)
);
```

In this example:
- Partitions divide data by SALE_DATE ranges.
- Each partition is subdivided into four subpartitions by HASH(PRODUCT_ID).
- Statistics can be managed at the table, partition, and subpartition levels.

### 2.3. Column statistics and histograms

Column statistics help the optimizer estimate predicates such as:

```sql
SELECT *
FROM   sales_demo
WHERE  product_id = 500;
```

If PRODUCT_ID values are skewed, histograms can improve selectivity estimates. On a partitioned table, distribution within a single partition can differ from the global distribution. Choose a `METHOD_OPT` tailored to the workload and avoid creating histograms indiscriminately without reason.

### 2.4. Index statistics are also important

The optimizer also uses index statistics such as:
- NUM_ROWS.
- DISTINCT_KEYS.
- LEAF_BLOCKS.
- CLUSTERING_FACTOR.
- BLEVEL.

Partitioned indexes maintain statistics at global/partition levels depending on index type and collection method. When evaluating plans on a partitioned table, do not inspect only `USER_TAB_STATISTICS`; also check `USER_IND_STATISTICS` and index metadata if queries rely on indexes.

## 3. Viewing Existing Statistics

### 3.1. USER_TAB_STATISTICS

Inspect table, partition, and subpartition statistics in the current schema:

```sql
SELECT table_name,
       partition_name,
       subpartition_name,
       num_rows,
       blocks,
       avg_row_len,
       last_analyzed,
       global_stats,
       stale_stats
FROM   user_tab_statistics
WHERE  table_name = 'SALES_DEMO'
ORDER  BY partition_name, subpartition_name;
```

The table-level row has empty PARTITION_NAME and SUBPARTITION_NAME; the remaining rows represent partitions or subpartitions. Check exact columns and values against the dictionary reference for your running Oracle version.

### 3.2. DBA_TAB_STATISTICS

DBAs can inspect across schemas:

```sql
SELECT owner,
       table_name,
       partition_name,
       subpartition_name,
       num_rows,
       blocks,
       last_analyzed,
       stale_stats
FROM   dba_tab_statistics
WHERE  owner = 'APP'
AND    table_name = 'SALES'
ORDER  BY partition_name, subpartition_name;
```

Without DBA privileges, use `USER_TAB_STATISTICS` or `ALL_TAB_STATISTICS` according to granted scope.

### 3.3. Viewing index statistics

```sql
SELECT index_name,
       table_name,
       partition_name,
       num_rows,
       distinct_keys,
       leaf_blocks,
       clustering_factor,
       last_analyzed,
       visibility
FROM   user_ind_statistics
WHERE  table_name = 'SALES_DEMO'
ORDER  BY index_name, partition_name;
```

Review index statistics alongside table statistics to understand access paths. For partitioned indexes, inspect the relevant global and partition rows.

### 3.4. Viewing partition structure

```sql
SELECT partition_name,
       partition_position,
       high_value,
       num_rows,
       last_analyzed
FROM   user_tab_partitions
WHERE  table_name = 'SALES_DEMO'
ORDER  BY partition_position;
```

`USER_TAB_PARTITIONS` provides partition metadata. `HIGH_VALUE` is commonly exposed as `LONG` in some dictionary views, restricting direct filtering or manipulation. Use appropriate views and metadata utilities when extracting complex partition boundaries.

### 3.5. Identifying stale statistics

Statistics can be marked stale when recorded data modifications exceed the `STALE_PERCENT` threshold. A common default is 10%, though it can be adjusted via preferences and statistics management settings.

Stale does not mean statistics are definitely severely inaccurate. It is a signal to evaluate or re-gather. Conversely, non-stale statistics can still misrepresent data distributions if workloads or value distributions shift significantly.

You can flush monitoring information before checking status:

```sql
BEGIN
    DBMS_STATS.FLUSH_DATABASE_MONITORING_INFO;
END;
/
```

This updates monitoring metadata in the dictionary. Consider privileges and overhead on large systems.

## 4. Gathering Partition Statistics with DBMS_STATS

### 4.1. GATHER_TABLE_STATS

Oracle provides the `DBMS_STATS` package to gather statistics. Do not use `ANALYZE TABLE COMPUTE STATISTICS` for modern optimizer statistics management; use `DBMS_STATS`.

Example of gathering statistics for the entire table:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'SALES_DEMO',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        granularity      => 'AUTO',
        cascade          => DBMS_STATS.AUTO_CASCADE,
        no_invalidate    => DBMS_STATS.AUTO_INVALIDATE
    );
END;
/
```

Parameters:
- OWNNAME and TABNAME: schema and table.
- ESTIMATE_PERCENT: sample percentage; `AUTO_SAMPLE_SIZE` lets Oracle choose.
- METHOD_OPT: column statistics and histogram policy.
- GRANULARITY: level of statistics to gather.
- CASCADE: how to handle related index statistics.
- NO_INVALIDATE: controls cursor invalidation after publishing statistics.

### 4.2. GRANULARITY

Common `GRANULARITY` values:

| Value | Meaning |
| --- | --- |
| AUTO | Oracle selects statistics levels suited to the partitioning type and configuration |
| ALL | Gathers statistics at all relevant levels, including global and partition/subpartition as applicable |
| GLOBAL | Gathers global statistics only |
| PARTITION | Gathers partition statistics |
| SUBPARTITION | Gathers subpartition statistics |
| DEFAULT | Uses version default behavior |

Exact options and behavior can differ by release and partitioning type. For composite-partitioned tables, `AUTO` is usually a practical choice to let Oracle decide appropriate levels.

### 4.3. Gathering statistics for a single partition

If only partition `P2026_01` changed:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'SALES_DEMO',
        partname         => 'P2026_01',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        granularity      => 'PARTITION',
        cascade          => DBMS_STATS.AUTO_CASCADE,
        no_invalidate    => DBMS_STATS.AUTO_INVALIDATE
    );
END;
/
```

This focuses on the specified partition. On very large tables, gathering statistics for modified partitions can be far cheaper than scanning the entire table.

### 4.4. Gathering global statistics

When global statistics need updating:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'SALES_DEMO',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        granularity      => 'GLOBAL',
        cascade          => DBMS_STATS.AUTO_CASCADE,
        no_invalidate    => DBMS_STATS.AUTO_INVALIDATE
    );
END;
/
```

With incremental statistics enabled and synopses available, Oracle can compute global statistics from partition summaries instead of scanning every row across the whole table. If synopses are missing or unusable, gathering may have to read more data than expected.

### 4.5. Gathering statistics for a subpartition

For composite-partitioned tables, specify the `SUBPARTITION` and matching `GRANULARITY`:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'SALES_DEMO',
        partname         => 'SYS_SUBP123',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        granularity      => 'SUBPARTITION',
        cascade          => DBMS_STATS.AUTO_CASCADE
    );
END;
/
```

The subpartition name is illustrative only. Retrieve the exact name from `USER_TAB_SUBPARTITIONS` or `DBA_TAB_SUBPARTITIONS`. Never guess Oracle-generated names.

## 5. What Are Incremental Statistics?

### 5.1. The problem with traditional global statistics gathering

Suppose table SALES has 120 monthly partitions, each holding tens of millions of rows. Each day, only the current month's partition changes.

If updating global statistics required scanning the entire table every time, cost would scale with total data volume even when only one partition changed.

Incremental statistics are designed to lower the cost of maintaining global statistics for partitioned tables experiencing localized changes.

### 5.2. Synopses

When incremental statistics are enabled, Oracle maintains synopses for partitions. A synopsis can be thought of as a compact summary of a partition's data, especially useful for aggregating the number of distinct values (NDV) across the entire table.

When global statistics are needed, Oracle combines partition synopses with partition statistics to aggregate the result. This avoids rescanning all data in unchanged partitions just to calculate global NDV.

Synopses are internal metadata managed by Oracle. Never directly update or delete internal `SYS` tables holding synopses.

### 5.3. Incremental is not simply gathering a partition

Gathering statistics for a single partition is one operation. Incremental statistics is the mechanism that maintains synopses and assists in updating global statistics efficiently.

Running `GATHER_TABLE_STATS` with `PARTITION` alone does not automatically prove global statistics have been updated. Clarify your goals:
- Updating partition statistics.
- Updating global statistics.
- Maintaining synopses for modified partitions.
- Confirming global statistics reflect new data.

### 5.4. Conditions and limitations

Incremental statistics apply to partitioned tables. Effectiveness depends on:
- The table's `INCREMENTAL` preference.
- Synopses having been created for the required partitions.
- Appropriate granularity and gather operations.
- Partition maintenance operations.
- Oracle version and supported statistics features.

Enabling incremental statistics for the first time may require gathering across many or all partitions to build initial synopses. Initial setup cost can therefore be substantial. The biggest payoff typically appears in subsequent updates when only a subset of partitions change.

## 6. Enabling Incremental Statistics

### 6.1. Setting the table-level preference

Incremental statistics can be enabled for a table:

```sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => USER,
        tabname => 'SALES_DEMO',
        pname   => 'INCREMENTAL',
        pvalue  => 'TRUE'
    );
END;
/
```

The preference is bound to the table, not a global parameter applied automatically to every table. This controls rollout scope.

### 6.2. Checking the preference

```sql
SELECT DBMS_STATS.GET_PREFS(
           pname   => 'INCREMENTAL',
           ownname => USER,
           tabname => 'SALES_DEMO'
       ) AS incremental_pref
FROM dual;
```

A result of `TRUE` confirms the incremental preference is enabled for the table under `DBMS_STATS` configuration.

### 6.3. Initializing statistics and synopses

After enabling incremental, gather statistics so Oracle creates/maintains synopses:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'SALES_DEMO',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        granularity      => 'ALL',
        cascade          => DBMS_STATS.AUTO_CASCADE,
        no_invalidate    => DBMS_STATS.AUTO_INVALIDATE
    );
END;
/
```

On large tables, the first run can be resource-intensive because synopses must be generated for partitions lacking them. Schedule and monitor it like a major maintenance task.

### 6.4. Incremental gathering after one partition changes

Suppose partition `P2026_03` receives new data. An illustrative workflow:

Step 1 — gather partition statistics:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'SALES_DEMO',
        partname         => 'P2026_03',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        granularity      => 'PARTITION',
        cascade          => DBMS_STATS.AUTO_CASCADE
    );
END;
/
```

Step 2 — update global statistics:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'SALES_DEMO',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        granularity      => 'GLOBAL',
        cascade          => DBMS_STATS.AUTO_CASCADE
    );
END;
/
```

When incremental statistics are configured and synopses are complete, Oracle can use synopses to compute global statistics without rescanning all unchanged partitions. Verify behavior and gather duration on your operating release.

In some maintenance schedules, `GRANULARITY AUTO` can be used to let Oracle decide which levels to update. Verify global and partition statistics afterward rather than relying solely on procedure completion.

### 6.5. Disabling the incremental preference

If you no longer wish to use incremental statistics:

```sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => USER,
        tabname => 'SALES_DEMO',
        pname   => 'INCREMENTAL',
        pvalue  => 'FALSE'
    );
END;
/
```

Disabling the preference does not immediately purge all internal synopses. Manage statistics using `DBMS_STATS` APIs and supported procedures; never delete `SYS` data directly.

## 7. How Incremental Statistics Assist Global Statistics

### 7.1. Avoiding rescanning unchanged partitions

Example of a table with 36 partitions:

```text
P01 P02 P03 P04 ... P34 P35 P36
 |   |   |   |       |   |   |
has has has has     has has newly
syn syn syn syn     syn syn changed

Only P36 needs re-gathering.
Oracle updates P36's synopsis and combines partition synopses
to maintain global statistics.
```

This is the main benefit of incremental statistics on large tables with partition-localized changes.

### 7.2. Global NDV

One of the hardest statistics to aggregate across partitions is a column's NDV. You cannot simply sum the NDVs of individual partitions because the same value can appear in multiple partitions.

Example:

| Partition | PRODUCT_ID values | NDV |
| --- | --- | ---: |
| P1 | 10, 20, 30 | 3 |
| P2 | 20, 30, 40 | 3 |
| P3 | 30, 40, 50 | 3 |

Total table-wide NDV is 5, not 9. Synopses help Oracle estimate/maintain global NDV without rescanning every row in every partition.

### 7.3. Other types of statistics

Incremental statistics do not mean every global statistic is handled solely via synopses in the exact same way. Oracle can aggregate many metrics from partition statistics and synopses; exact support depends on version, statistic type, and configuration.

In particular, inspect separately:
- Histograms and value distributions.
- Extended statistics.
- Global/local index statistics.
- Newly added or recently exchanged partitions.
- Columns with severe data skew.

Do not infer that enabling incremental automatically makes every global histogram accurately reflect every new distribution. Check dictionary statistics and execution plans for critical workloads.

### 7.4. Incremental does not replace gathering partition statistics

If data in a partition changes without updating partition statistics, its synopsis may not reflect the new data. Your workflow must gather modified partitions before relying on global incremental statistics.

## 8. New Partitions and Partition Maintenance Operations

### 8.1. ADD PARTITION

When a new partition is added, it may initially be empty or loaded later. After loading:
- Gather partition statistics.
- Ensure synopses are created/maintained if incremental is enabled.
- Update global statistics according to the appropriate workflow.
- Verify partition stats and global stats.

Example:

```sql
ALTER TABLE sales_demo
ADD PARTITION p2026_04
VALUES LESS THAN (DATE '2026-05-01');
```

After loading data into the partition, gather statistics for that partition. Do not assume `ADD PARTITION` alone generates complete statistics for data loaded later.

### 8.2. TRUNCATE or DROP PARTITION

When truncating or dropping a partition, overall table row counts and data distributions change. Check:
- Do partition statistics still reflect reality?
- Do global statistics need updating?
- Was the dropped/truncated partition's synopsis removed/adjusted appropriately?
- Do local/global indexes need maintenance?

`DBMS_STATS` and Oracle handle certain metadata linked to partition maintenance, but exact procedures depend on the operation and version. Inspect stats after every major PMOP.

### 8.3. EXCHANGE PARTITION

`EXCHANGE PARTITION` is commonly used for fast data loading by swapping metadata between a staging table and a partition. Staging table statistics can be useful in preparing the partition post-exchange.

A typical workflow considers:
1. Load data into the staging table.
2. Gather table statistics on the staging table.
3. Perform `EXCHANGE PARTITION` meeting constraint/index requirements.
4. Use appropriate `DBMS_STATS` APIs to transfer/copy stats if supported for that scenario, or gather partition stats after exchange.
5. Update global incremental statistics.
6. Verify partition/global stats and plans.

`DBMS_STATS` provides procedures to copy statistics between tables/partitions in appropriate scenarios. Check the signature and limitations of `COPY_TABLE_STATS` for your exact version; never copy internal dictionary rows manually.

### 8.4. New partitions without synopses

If incremental statistics were recently enabled or a new partition lacks a synopsis, the next global gather may need to build missing synopses and read more data. This is why incremental statistics should be initialized before expecting subsequent gathers to process only changed partitions.

## 9. Stale Statistics and Collection Schedules

### 9.1. STALE_PERCENT

Oracle uses modification monitoring on changed row counts to determine when statistics may be stale. The `STALE_PERCENT` preference sets the percentage change threshold. A common default is 10%.

View the preference:

```sql
SELECT DBMS_STATS.GET_PREFS(
           'STALE_PERCENT',
           USER,
           'SALES_DEMO'
       ) AS stale_percent
FROM dual;
```

The stale threshold is an operational signal, not a guarantee that the optimizer always needs a gather immediately upon reaching the threshold or can always rely on stats below the threshold.

### 9.2. GATHER STALE

You can instruct `DBMS_STATS` to gather statistics for stale objects per policy:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'SALES_DEMO',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        granularity      => 'AUTO',
        options          => 'GATHER STALE',
        cascade          => DBMS_STATS.AUTO_CASCADE
    );
END;
/
```

Verify exact behavior on partitioned tables for your release and preferences. If you want to guarantee gathering only one specific partition, specify `PARTNAME` and appropriate `GRANULARITY`.

### 9.3. Automatic statistics gathering

Oracle includes an automatic optimizer statistics gathering task during maintenance windows in standard configurations. DBAs still need to check:
- Does the job run at the right time?
- Are any tables/partitions locked against statistics updates?
- Is the table excluded or configured with unusual preferences?
- Is incremental enabled on the right tables?
- Are new partitions gathered promptly after loads?
- Are job duration and resource consumption acceptable?

Do not assume the auto task handles every partitioned table or every partition-exchange workflow flawlessly.

### 9.4. LOCK_TABLE_STATS

Statistics can be locked using `DBMS_STATS.LOCK_TABLE_STATS`. When stats are locked, automatic gathers may not update them as expected.

Check status:

```sql
SELECT table_name,
       stattype_locked,
       stale_stats,
       last_analyzed
FROM   user_tab_statistics
WHERE  table_name = 'SALES_DEMO';
```

Unlock only when you understand why stats were locked and the governance process:

```sql
BEGIN
    DBMS_STATS.UNLOCK_TABLE_STATS(
        ownname => USER,
        tabname => 'SALES_DEMO'
    );
END;
/
```

Do not lock statistics to freeze plans without evaluating SQL Plan Management or a more suitable plan-control mechanism.

## 10. Pending Statistics and Plan Testing

### 10.1. Why use pending statistics?

When you want to test new statistics before exposing them to the entire workload, use pending statistics. This lets DBAs gather and test new stats in a test session prior to publishing.

Set `PUBLISH` to `FALSE` at the table level:

```sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => USER,
        tabname => 'SALES_DEMO',
        pname   => 'PUBLISH',
        pvalue  => 'FALSE'
    );
END;
/
```

Gather statistics. The new statistics are held in pending state under `DBMS_STATS`.

### 10.2. Using pending statistics in a test session

```sql
ALTER SESSION SET optimizer_use_pending_statistics = TRUE;
```

Run representative SQL, capture runtime plans, and compare against published statistics. Other sessions continue using published statistics by default unless they enable pending statistics.

### 10.3. Publishing or deleting pending statistics

Once testing meets requirements:

```sql
BEGIN
    DBMS_STATS.PUBLISH_PENDING_STATS(
        ownname => USER,
        tabname => 'SALES_DEMO'
    );
END;
/
```

If you decide not to use the pending statistics:

```sql
BEGIN
    DBMS_STATS.DELETE_PENDING_STATS(
        ownname => USER,
        tabname => 'SALES_DEMO'
    );
END;
/
```

After testing, reset the session parameter and `PUBLISH` preference according to established procedures. Pending statistics are a plan-testing mechanism; they do not replace data-quality and statistics validation.

## 11. Statistics and Execution Plans

### 11.1. How do statistics affect the optimizer?

The optimizer uses statistics to estimate:
- Cardinality of each operation.
- Predicate selectivity.
- Number of blocks to read.
- Costs of index access and full scans.
- Join order and join method.
- Costs of sorts, hashes, and aggregations.

On partitioned tables, global and partition statistics can yield different estimates. If one partition has a distribution vastly different from the rest, partition-level statistics can help pruned queries estimate more accurately.

### 11.2. Checking the actual plan

You can capture the runtime plan:

```sql
SELECT /*+ gather_plan_statistics */
       product_id,
       SUM(amount)
FROM   sales_demo
WHERE  sale_date >= DATE '2026-03-01'
AND    sale_date <  DATE '2026-04-01'
GROUP  BY product_id;
```

After fetching results:

```sql
SELECT *
FROM   TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PARTITION +PREDICATE'
    )
);
```

Inspect:
- Partition Start/Stop to understand partition pruning.
- E-Rows and A-Rows to compare estimates against actuals.
- Buffers and Reads to assess read work.
- Predicate Information to identify access/filter conditions.
- Join order and join method if multiple tables are involved.

### 11.3. Comparing before and after gathering

After updating partition/global stats, the same SQL may produce a different plan. That is not automatically better. Compare runtime, buffers, reads, CPU, elapsed time, and result correctness.

Do not change statistics, indexes, optimizer parameters, and SQL simultaneously if the goal is isolating what caused a plan change. Change one factor at a time while keeping bind values and workloads comparable.

### 11.4. NO_INVALIDATE

The `NO_INVALIDATE` parameter of `DBMS_STATS` controls cursor invalidation after statistics are published. `AUTO_INVALIDATE` lets Oracle select an appropriate invalidation policy.

Do not default to `FALSE` to invalidate all cursors immediately in a high-load system. Account for parse overhead, shared pool impact, and rollout plans.

## 12. Performance and Operational Considerations

### 12.1. Initial incremental setup can be expensive

Enabling `INCREMENTAL` does not instantly create complete synopses for all historical partitions. The first gather may need to read many partitions. Schedule appropriately, monitor I/O/CPU, and avoid overlapping with heavy batch windows.

### 12.2. Do not gather the entire table daily if only one partition changes

For very large daily/monthly tables, design workflows that gather only recently modified partitions and update global statistics via incremental synopses. Repeatedly gathering the whole table wastes resources and prolongs maintenance windows.

### 12.3. New partitions and loaded data

After loads/exchanges, ensure partition statistics and synopses reflect the new data. Otherwise, global statistics may still rely on stale data or lack synopses for new partitions.

### 12.4. Histograms require careful thought

`METHOD_OPT` such as `FOR ALL COLUMNS SIZE AUTO` lets Oracle decide histograms based on workload and data distribution. Do not create histograms on every column just wanting more detail. Unsuitable histograms can make plans overly sensitive to bind values or increase plan instability.

### 12.5. Statistics are not real business data

Gathering statistics does not modify rows, drop partitions, or alter business data. It updates metadata the optimizer uses for planning. Nevertheless, gathering can scan large volumes of data and consume considerable resources.

### 12.6. Global indexes and local indexes

Partitioned tables can have local indexes or global indexes. When partition maintenance operations occur, index statistics and index status must be reviewed separately. Incremental table statistics do not automatically substitute for managing index statistics.

## 13. Recommended Operational Workflow

For a large partitioned table, organize a statistics schedule like this:

1. **Design partitions:** define partition key, interval, and load/retention strategy.
2. **Collect baseline:** gather appropriate table, partition, and index statistics.
3. **Enable incremental:** set `INCREMENTAL` to `TRUE` on tables that benefit.
4. **Initialize synopses:** gather statistics across existing partitions using appropriate granularity.
5. **Load new partition:** load data or exchange partition.
6. **Gather modified partition:** update stats for the specific modified partition/subpartition.
7. **Update global:** use incremental synopses and appropriate granularity.
8. **Check stale:** inspect `USER_TAB_STATISTICS`/`DBA_TAB_STATISTICS`.
9. **Check plans:** inspect partition pruning, A-Rows, E-Rows, buffers, and runtime.
10. **Monitor:** track gather duration, resource consumption, and critical plans.
11. **Tune:** adjust preferences or gather schedules as workloads evolve.
12. **Recover if needed:** use stats history/pending stats per established governance procedures.

There is no single gather schedule for every table. Daily append-only tables may require a different workflow from tables receiving `UPDATE`/`DELETE` across many older partitions.

## 14. Comprehensive Practice Lab

Exercises use the `SALES_DEMO` table from section 2.2. Run in a learning schema.

### Exercise 1 — View partition statistics

```sql
SELECT table_name,
       partition_name,
       subpartition_name,
       num_rows,
       blocks,
       last_analyzed,
       stale_stats
FROM   user_tab_statistics
WHERE  table_name = 'SALES_DEMO'
ORDER  BY partition_name, subpartition_name;
```

Identify the global, partition, and subpartition rows.

### Exercise 2 — Gather partition statistics

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'SALES_DEMO',
        partname => 'P2026_01',
        granularity => 'PARTITION',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE
    );
END;
/
```

Observe `LAST_ANALYZED` and `STALE_STATS`.

### Exercise 3 — Gather global statistics

Use `GRANULARITY GLOBAL`. Compare duration and results against gathering across all levels with `ALL`.

### Exercise 4 — Enable the incremental preference

```sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        USER,
        'SALES_DEMO',
        'INCREMENTAL',
        'TRUE'
    );
END;
/
```

Use `GET_PREFS` to confirm.

### Exercise 5 — Initialize synopses

Gather statistics with `GRANULARITY ALL`. Record duration, resources, and outcome. Explain why the first run can be expensive.

### Exercise 6 — Modify one partition

Add data to one demo partition, gather partition stats, and then update global stats. Compare duration against a full-table gather in an environment with sufficient data.

### Exercise 7 — Compare global NDV

Create data with overlapping `PRODUCT_ID` values across multiple partitions. Explain why summing partition NDVs cannot simply yield global NDV.

### Exercise 8 — Check stale statistics

Flush monitoring info and inspect `STALE_STATS`. Try changing `STALE_PERCENT` in a test schema and observe how the threshold affects stale status.

### Exercise 9 — View index statistics

Query `USER_IND_STATISTICS` and compare global/local index stats with table stats.

### Exercise 10 — EXCHANGE PARTITION

Create a structurally compatible staging table, gather stats before exchanging, perform the exchange in the demo schema if privileges allow, and then verify partition statistics and global stats. Look up `DBMS_STATS.COPY_TABLE_STATS` if you wish to test transferring statistics per release.

### Exercise 11 — Pending statistics

Set `PUBLISH` to `FALSE`, gather stats, enable `OPTIMIZER_USE_PENDING_STATISTICS` in a test session, and compare plans. Afterward, publish or delete pending stats.

### Exercise 12 — Diagnose a bad plan

A query filters on the partition key yet the optimizer estimates 100x more rows than actuals. Check partition pruning, partition stats, global stats, histograms, binds, and gather timestamps before changing indexes.

## 15. Common Misconceptions

**"Partition pruning means global statistics aren't needed."** False. The optimizer still needs accurate statistics for accessed partitions and for joins/overall estimates.

**"Global statistics always equal the sum of partition statistics."** Not all metrics add up simply; NDV is a clear example because values can repeat across partitions.

**"Incremental statistics automatically gather newly modified partitions."** False. It is a synopsis mechanism supporting global stats maintenance; a proper gather workflow is still required.

**"Simply enabling INCREMENTAL immediately creates synopses for all partitions."** False. Initialization may require gathering across existing partitions.

**"Gathering a single partition definitely updates global stats."** Never assume this. Specify `GRANULARITY` and check the global row after gathering.

**"Stale statistics mean wrong statistics."** Not necessarily. Stale is a signal based on monitoring thresholds, not an absolute accuracy measurement.

**"Incremental applies only to tables without subpartitions."** False. Composite-partitioned tables can have statistics at multiple levels; choose granularity and verify your release.

**"Gathering statistics does not affect workloads."** False. Gathering stats can read large amounts of data, consume CPU/I/O, and impact maintenance windows.

**"The more histograms, the better."** False. Histograms must match actual distributions and workloads.

**"Index stats are automatically handled by incremental table stats."** False. Inspect and manage index statistics separately.

## 16. Oracle Reference Documentation

- [Oracle Database SQL Tuning Guide — Managing Optimizer Statistics](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/managing-optimizer-statistics.html): workflows for collecting and managing optimizer statistics.
- [Oracle Database SQL Tuning Guide — Incremental Statistics](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/optimizer-statistics-concepts.html): optimizer statistics concepts and information related to incremental statistics.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_STATS](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_STATS.html): `GATHER_TABLE_STATS`, `SET_TABLE_PREFS`, `GET_PREFS`, and statistics procedures.
- [Oracle Database Reference — USER_TAB_STATISTICS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_TAB_STATISTICS.html): table, partition, and subpartition statistics.
- [Oracle Database Reference — USER_TAB_PARTITIONS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_TAB_PARTITIONS.html): partition metadata.
- [Oracle Database VLDB and Partitioning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/): partition design and managing partitioned tables.

Partition statistics help the optimizer understand data within individual partitions, while global statistics describe the entire table. For large partitioned tables where only a portion changes each cycle, incremental statistics maintain synopses to support updating global statistics without rescanning all unchanged partitions. Enable incremental selectively, initialize synopses, gather modified partitions after loads/maintenance, update global statistics, and inspect actual execution plans. **Incremental statistics reduce statistics maintenance cost; they do not replace verifying partition statistics, global statistics, and application workloads.**
