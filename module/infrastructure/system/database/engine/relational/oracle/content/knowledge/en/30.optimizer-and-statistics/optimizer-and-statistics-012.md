# Impact of Statistics After Bulk Loads, Data Changes, or Upgrades

In Oracle Database, the Cost-Based Optimizer (CBO) uses statistics to estimate row counts, predicate selectivity, data block accesses, and the cost of each execution plan alternative. Consequently, after a bulk data load, major data changes, or an Oracle upgrade, outdated statistics can cause the CBO to choose an unsuitable execution plan.

Statistics do not modify business data and do not guarantee that a SQL statement will always keep the same execution plan. They supply input information to the CBO. When this information changes, or when optimization algorithms change after an upgrade, execution plans and CPU, I/O, and memory consumption can change accordingly.

## 1. Types of Statistics Affecting Execution Plans

Oracle maintains several categories of statistics. Identify the relevant category before gathering or troubleshooting.

| Statistics Category | Key Information | Common Impact |
|---|---|---|
| Table statistics | Row count (**NUM_ROWS**), block count (**BLOCKS**), average row length (**AVG_ROW_LEN**) | Estimates table size, full table scan cost, and join cost |
| Column statistics | Number of distinct values (**NUM_DISTINCT**), NULL count, density (**DENSITY**), low/high values | Estimates selectivity of column predicates |
| Histograms | Frequency distribution of values within a column | Improves estimates when data is skewed or some values are far more common than others |
| Index statistics | Leaf block count, tree height (**BLEVEL**), clustering factor, distinct keys | Estimates cost of index access and retrieving rows from the table |
| Partition statistics | Row counts and data distributions per partition, plus table-wide statistics | Affects partition pruning, join estimates, and partitioned table query plans |
| System statistics | System CPU and I/O characteristics | Affects how the CBO compares CPU cost against I/O cost |
| Dictionary and fixed object statistics | Characteristics of data dictionary objects and fixed objects | Can affect internal SQL statements, dictionary queries, and administrative operations |

Table or column statistics can be accurate on total row count yet still describe data distribution poorly. For example, a **STATUS** column has 10 million rows, but 95% of rows carry **CLOSED**, while the remaining 5% are split across many other statuses. If the CBO sees only the number of distinct values without proper distribution information, it may significantly misestimate a **STATUS = 'CLOSED'** predicate.

## 2. After Bulk Data Loads

### Why Old Statistics Become Unsuitable

Suppose the **ORDERS** table had 1 million rows before a load. After a load, the table has 80 million rows, mostly consisting of orders for a new month. If statistics still describe the pre-load state, the CBO may:

- Underestimate the table's row count.
- Choose nested loops for a join over a large dataset where a hash join would fit better.
- Choose an index range scan when too many rows must be read, or choose a full table scan when the filter predicate is actually very selective.
- Misestimate sort, hash join, parallel execution, or intermediate processing costs.
- Produce a different plan for the same SQL statement when the new data has a different distribution from the old data.

Common scenarios include direct-path inserts, **INSERT /*+ APPEND */**, CTAS (**CREATE TABLE AS SELECT**), SQL*Loader loads, batch loads, truncate-and-reload, or partition exchange with a staging table.

### When to Gather Statistics

Gather or verify statistics after the load finishes and data has reached the state the application will query. If gathered mid-load, statistics may describe a transient state while subsequent batches continue altering row counts and data distributions.

For a non-partitioned table, table and index statistics can be gathered with **DBMS_STATS.GATHER_TABLE_STATS**:

~~~sql
BEGIN
  DBMS_STATS.GATHER_TABLE_STATS(
    ownname          => 'APP',
    tabname          => 'ORDERS',
    estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
    method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
    cascade          => DBMS_STATS.AUTO_CASCADE,
    degree           => DBMS_STATS.AUTO_DEGREE,
    no_invalidate    => DBMS_STATS.AUTO_INVALIDATE
  );
END;
/
~~~

Notable parameters:

- **AUTO_SAMPLE_SIZE** lets Oracle choose an appropriate sampling method automatically.
- **METHOD_OPT** governs how column statistics and histograms are collected. **SIZE AUTO** lets Oracle consider histograms based on column characteristics and usage tracking.
- **CASCADE** controls gathering index statistics alongside table statistics. **AUTO_CASCADE** lets Oracle decide.
- **DEGREE** controls parallelism during collection.
- **NO_INVALIDATE** controls cursor invalidation after statistics change. **AUTO_INVALIDATE** delegates the timing decision to Oracle.

Do not blindly create histograms on every column or assign a fixed bucket count across all tables. Histograms help for skewed columns, yet they can also alter estimates and execution plans. Choose **METHOD_OPT** according to actual data characteristics and workload.

### Partitioned Tables and Partition Exchange Loads

For partitioned tables, pay attention to both partition-level and global statistics. A new partition may contain data very different from older partitions. Looking only at global stats, or updating only the new partition while neglecting global stats requirements, can cause the CBO to misestimate queries spanning multiple partitions.

You can use **GRANULARITY => 'AUTO'** so Oracle picks the appropriate statistics level for the partition structure:

~~~sql
BEGIN
  DBMS_STATS.GATHER_TABLE_STATS(
    ownname          => 'APP',
    tabname          => 'SALES',
    estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
    method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
    granularity      => 'AUTO',
    cascade          => DBMS_STATS.AUTO_CASCADE,
    degree           => DBMS_STATS.AUTO_DEGREE
  );
END;
/
~~~

For very large partitioned tables, incremental statistics can update global statistics without re-scanning every partition. Oracle stores synopses to aggregate global statistics. Enable and configure incremental statistics based on your Oracle version, administrative policy, and partition maintenance practices.

~~~sql
BEGIN
  DBMS_STATS.SET_TABLE_PREFS(
    ownname => 'APP',
    tabname => 'SALES',
    pname   => 'INCREMENTAL',
    pvalue  => 'TRUE'
  );
END;
/
~~~

For partition exchange load workflows, inspect statistics on the staging table, target partition, and global table separately after the exchange. Swapping partitions can alter the relationship between actual data and stored statistics. Procedures for copying or recomputing statistics must align with your Oracle version and exchange method; do not assume staging statistics automatically become valid global statistics for the entire table.

## 3. After Operational Data Changes

### Stale Statistics and Change Thresholds

Oracle tracks inserts, updates, and deletes to determine whether table statistics may have gone stale. This status is usually exposed via the **STALE_STATS** column in statistics views. The default stale threshold is typically 10% of rows, though it can be changed via the **STALE_PERCENT** preference at the global, schema, or table level. Check the actual configuration rather than relying on defaults.

You can check a table's preference as follows:

~~~sql
SELECT DBMS_STATS.GET_PREFS(
         pname   => 'STALE_PERCENT',
         ownname => 'APP',
         tabname => 'ORDERS'
       ) AS stale_percent
FROM dual;
~~~

The stale threshold is a signal to consider re-gathering statistics, not a complete measure of statistics quality. A small change in row count can still shift data distribution dramatically. Conversely, a table that grows substantially while maintaining a similar distribution may not require the same handling as a heavily skewed table.

Scenarios requiring attention:

- Many rows are updated from one status to another while total row count barely changes.
- A previously rare value becomes popular.
- New data concentrates in a specific date range or customer segment.
- Correlated columns shift together, such as **COUNTRY** and **POSTAL_CODE**.
- A table has most rows deleted, is truncated, or is reloaded periodically.

### Histograms, Bind Variables, and Skewed Data

Histograms help the CBO describe column value distributions. They are especially helpful when some values occur far more often than others.

However, for SQL using bind variables, the bind value at parse time and mechanisms like bind peeking / adaptive cursor sharing can affect cursors and execution plans. Therefore, do not assume merely adding histograms will make every query better. Test multiple representative bind values, inspect child cursors, and check actual row counts at each step of the execution plan.

When multiple columns are correlated, individual per-column statistics may be insufficient. Extended statistics can describe column groups or expressions matching the workload. For instance, if predicates frequently filter on both **COUNTRY** and **STATE**, consider column group statistics after evaluating benefits and impact:

~~~sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
         ownname   => 'APP',
         tabname   => 'CUSTOMERS',
         extension => '(COUNTRY, STATE)'
       )
FROM dual;
~~~

After creating an extension, re-gather table statistics so the CBO can use the new information. Avoid creating extended statistics indiscriminately without real queries to justify them.

### Locked Statistics

Some systems lock statistics to keep execution plans stable on critical tables. When locked, automatic statistics collection will not update those tables as expected. Check lock status before concluding Oracle skipped a table:

~~~sql
SELECT owner, table_name, stattype_locked
FROM dba_tab_statistics
WHERE owner = 'APP'
  AND table_name = 'ORDERS';
~~~

If statistics need updating, verify the lock reason and governance process before unlocking. You can unlock using:

~~~sql
BEGIN
  DBMS_STATS.UNLOCK_TABLE_STATS(
    ownname => 'APP',
    tabname => 'ORDERS'
  );
END;
/
~~~

Re-lock only if operational policy requires it. Locking statistics can preserve outdated statistics while data continues changing.

## 4. After Upgrading Oracle Database

A version upgrade can change execution plans even when application data and statistics remain unchanged. Common reasons include:

- The new release modifies optimizer behavior or algorithms.
- Default values of certain optimizer parameters change.
- New optimization features are enabled or triggered under different conditions.
- Cardinality estimation, CPU/I/O costing, or handling of specific SQL constructs changes.
- Dictionary statistics, fixed object statistics, or system information no longer accurately reflect the post-upgrade environment.

**OPTIMIZER_FEATURES_ENABLE** is an important parameter when analyzing optimizer behavior differences between versions. Do not change this parameter system-wide merely to fix one slow execution plan. First identify affected SQL statements, compare plans, and review upgrade guidance for the target release.

After upgrading, perform statistics tasks according to the documentation for your target Oracle version:

1. Verify dictionary statistics have been updated as recommended by the upgrade procedure. When required, use **DBMS_STATS.GATHER_DICTIONARY_STATS**.
2. Gather fixed object statistics after the system has run a representative workload. **DBMS_STATS.GATHER_FIXED_OBJECTS_STATS** operates on fixed objects; results are more meaningful once the database has real activity rather than right after startup with no workload.
3. Evaluate system statistics when significant hardware or I/O/CPU changes occur, following an approved procedure. Do not mechanically re-gather system statistics simply because of a version upgrade.
4. Identify application schemas and tables that genuinely need statistics updates. Avoid broad re-gathering without assessing execution plan impact.
5. Compare critical SQL statements before and after upgrading. If regressions occur, consider SQL Plan Management, SQL plan baselines, or appropriate statistics restoration options.

A changed execution plan after an upgrade does not automatically prove statistics are wrong. Separate the effects of data, statistics, optimizer parameters, optimizer version, and hardware environment.

## 5. Inspecting Statistics and Execution Plans

### Inspecting Table Statistics

The **DBA_TAB_STATISTICS** view shows row counts, block counts, analysis timestamps, and stale status. Example:

~~~sql
SELECT table_name,
       partition_name,
       num_rows,
       blocks,
       last_analyzed,
       stale_stats,
       global_stats
FROM dba_tab_statistics
WHERE owner = 'APP'
  AND table_name IN ('ORDERS', 'ORDER_ITEMS')
ORDER BY table_name, partition_name NULLS FIRST;
~~~

For accounts without DBA view privileges, use **ALL_TAB_STATISTICS** or **USER_TAB_STATISTICS** matching your access scope.

### Checking Accumulated DML Volume

~~~sql
SELECT table_name,
       partition_name,
       inserts,
       updates,
       deletes,
       timestamp
FROM dba_tab_modifications
WHERE table_owner = 'APP'
  AND table_name = 'ORDERS'
ORDER BY partition_name;
~~~

Monitoring information may not yet be flushed to the view at query time. When cross-checking, you can request a flush:

~~~sql
BEGIN
  DBMS_STATS.FLUSH_DATABASE_MONITORING_INFO;
END;
/
~~~

DML counters show how much changed since the last statistics gather. They do not replace inspecting data distributions and execution plans.

### Comparing Estimated Rows Against Actual Rows

A key indicator of unsuitable statistics is a large discrepancy between CBO-estimated rows (**E-Rows**) and actual rows (**A-Rows**) at plan steps. You can run a test SQL statement with the **GATHER_PLAN_STATISTICS** hint and then inspect the cursor:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       ...
FROM   ...
WHERE  ...;
~~~

~~~sql
SELECT *
FROM TABLE(
  DBMS_XPLAN.DISPLAY_CURSOR(
    sql_id => 'sql_id_here',
    format => 'ALLSTATS LAST +PEEKED_BINDS +OUTLINE'
  )
);
~~~

**ALLSTATS LAST** only displays runtime metrics when the cursor has collected plan statistics, such as via the **GATHER_PLAN_STATISTICS** hint or appropriate runtime statistics settings. Test with representative bind values and comparable workloads. A single execution is not enough to represent all bind values or load scenarios.

When reading the plan, focus on:

- The first step showing a large discrepancy between **E-Rows** and **A-Rows**.
- Filter conditions, join predicates, and partition pruning.
- Execution count of each step (**Starts**).
- Buffer gets, physical reads, elapsed time, and large sort/hash operations.
- Bind values, child cursors, and execution environment differences.

If cardinalities are already reasonable yet runtime remains high, the cause may lie in I/O, contention, parallelism settings, memory, or concurrent workload rather than statistics.

## 6. Controlled Statistics Update Workflow

A safe workflow should capture enough data for comparison and maintain a fallback if execution plans degrade.

1. **Record the pre-change state.** Save the load timestamp and scope, expected row counts, current statistics, critical SQL statements, execution plans, and representative runtime metrics.
2. **Determine the collection scope.** Distinguish regular tables, partitioned tables, indexes, column stats, and system stats. Check **STALE_STATS**, DML volume, histograms, preferences, and lock status.
3. **Gather once data stabilizes.** Use **DBMS_STATS** with appropriate sample size, method options, granularity, and parallelism. For large partitioned tables, evaluate incremental statistics and global stats requirements.
4. **Evaluate the new statistics.** Check **LAST_ANALYZED**, **NUM_ROWS**, partition stats, index stats, and histograms. Compare values against actual data metrics.
5. **Test execution plans with a representative workload.** Compare **E-Rows** and **A-Rows**, buffer gets, reads, elapsed time, and key bind values.
6. **Roll out under control.** Publish new statistics only when test results are satisfactory. Monitor critical SQL statements after publishing, as cursors may reparse and choose new plans.
7. **Keep a recovery option.** Ensure stats history retention is adequate, know how to restore statistics, and have a plan for handling SQL plan regressions.

### Using Pending Statistics to Test Before Publishing

Pending statistics let you gather statistics without immediately publishing them system-wide. Set the table's **PUBLISH** preference to **FALSE**, gather statistics, and test in a session with **OPTIMIZER_USE_PENDING_STATISTICS** enabled.

~~~sql
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
~~~

In the test session:

~~~sql
ALTER SESSION SET optimizer_use_pending_statistics = TRUE;
~~~

Run SQL with representative bind values and inspect plans and runtime metrics. After evaluation:

- If the new statistics meet requirements, publish via **DBMS_STATS.PUBLISH_PENDING_STATS**.
- If unsatisfactory, delete the pending statistics via **DBMS_STATS.DELETE_PENDING_STATS**.
- Reset the **PUBLISH** preference according to the table's policy once testing finishes.

Publishing example:

~~~sql
BEGIN
  DBMS_STATS.PUBLISH_PENDING_STATS(
    ownname => 'APP',
    tabname => 'ORDERS'
  );

  DBMS_STATS.SET_TABLE_PREFS(
    ownname => 'APP',
    tabname => 'ORDERS',
    pname   => 'PUBLISH',
    pvalue  => 'TRUE'
  );
END;
/
~~~

Pending statistics are a testing mechanism. They do not replace full workload testing and do not guarantee every SQL statement will get a better plan.

### Restoring Statistics When Regressions Occur

Oracle retains statistics history for a configured retention window. If new statistics cause a regression and a suitable snapshot remains in history, you can restore table statistics to an earlier point in time:

~~~sql
BEGIN
  DBMS_STATS.RESTORE_TABLE_STATS(
    ownname         => 'APP',
    tabname         => 'ORDERS',
    as_of_timestamp => SYSTIMESTAMP - INTERVAL '1' DAY
  );
END;
/
~~~

The timestamp in the example is illustrative; choose a timestamp matching a recorded good state still within history retention. Restoring statistics does not mean every cursor will immediately revert to its old execution plan. Inspect cursors, invalidation, and SQL plan baselines afterward.

## 7. Common Mistakes

- **Relying solely on STALE_STATS.** Stale status does not capture data distribution skew. A table may need updated statistics even when DML percentages are low.
- **Gathering statistics before a load completes.** Results reflect only a transient state and quickly become outdated.
- **Neglecting index statistics.** Fresh table stats paired with stale index stats can cause the CBO to miscalculate access costs.
- **Updating only one partition and forgetting global statistics.** This especially affects queries scanning multiple partitions.
- **Creating histograms on every column.** Histograms can improve estimates yet also shift plans and bind variable behavior.
- **Re-gathering schema-wide or database-wide statistics out of habit.** Broad operations can trigger mass reparsing and simultaneous plan flips across many SQL statements.
- **Confusing statistics issues with resource issues.** If cardinality estimates are reasonable yet runtime remains high, investigate I/O, CPU, contention, memory, and concurrent workload.
- **Upgrading and changing multiple optimizer parameters at once.** When regressions occur, isolating the root cause becomes difficult if version, parameters, statistics, and plans all changed simultaneously.

## 8. Operational Checklist

After a bulk load, significant data change, or Oracle upgrade, confirm:

- [ ] Data loading or conversion completed before gathering statistics.
- [ ] Target tables, partitions, indexes, and statistics categories needing updates were accurately identified.
- [ ] **LAST_ANALYZED**, **STALE_STATS**, DML volume, and statistics lock status were checked.
- [ ] Histograms and extended statistics align with actual data distributions and queries.
- [ ] Global statistics were properly handled for partitioned tables.
- [ ] Critical SQL execution plans and estimated/actual row counts were compared.
- [ ] Representative bind values and key workloads were tested.
- [ ] Statistics history or a recovery plan is in place in case of regression.
- [ ] Post-upgrade dictionary/fixed object/system statistics were handled per target release guidance.
- [ ] Clear ownership exists for publishing statistics and post-change monitoring.

Good statistics help the CBO estimate close to real data and select suitable execution plans. Effective outcomes depend on gathering at the right time, with the right scope, understanding data distribution, and validating against real workloads.
