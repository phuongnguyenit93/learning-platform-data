# Auto Statistics, Stale Statistics, and When to Update

The Oracle Optimizer relies on optimizer statistics to estimate the number of rows, the number of distinct values, predicate selectivity, data size, and the cost of execution plans. If statistics are missing or no longer reflect the current data, the optimizer may choose an unsuitable join order, join method, access path, or parallelism.

Oracle provides **automatic optimizer statistics collection** to automatically gather statistics for objects with missing or stale statistics. However, “auto statistics” does not mean Oracle immediately gathers stats whenever DML occurs, nor does it mean every data change requires an immediate gather. Oracle tracks the amount of change, evaluates statistics against a stale threshold, and then executes tasks within maintenance windows according to the schedule and allocated resources.

This lesson covers:

- What optimizer statistics include and why update timing matters.
- How Oracle identifies missing or stale statistics.
- STALE_PERCENT, DBA_TAB_MODIFICATIONS, and DBA_TAB_STATISTICS.
- Automatic Optimizer Statistics Collection and maintenance windows.
- How to monitor, enable/disable, and adjust AutoTask.
- Manually calling DBMS_STATS after a bulk load or major data change.
- Gather timing, locking, history, incremental stats, and impact on execution plans.
- A lab to inspect stale stats and practice gathering at the right time.

The examples use Oracle Database 19c. Some view names, preferences, and behaviors may vary by release; consult the documentation for your exact version and test in a non-production environment before changing the production statistics collection schedule.

## 1. What Are Optimizer Statistics?

Optimizer statistics are metadata describing the characteristics of data and objects so the cost-based optimizer (CBO) can estimate SQL execution costs. Statistics are neither business data nor execution plans; they are inputs to the optimizer's plan selection process.

Common categories of statistics:

| Category | Examples | Purpose |
| --- | --- | --- |
| Table statistics | NUM_ROWS, BLOCKS, AVG_ROW_LEN | Estimate table size and row count |
| Column statistics | NUM_DISTINCT, NUM_NULLS, LOW_VALUE, HIGH_VALUE, density | Estimate predicate selectivity |
| Histogram | Frequency, height-balanced, top-frequency, hybrid | Describe skewed distribution of column values |
| Index statistics | LEAF_BLOCKS, DISTINCT_KEYS, CLUSTERING_FACTOR, BLEVEL | Estimate index access cost |
| Partition statistics | Per-partition and global statistics | Optimize queries on partitioned tables |
| System statistics | CPU speed, I/O characteristics | Estimate CPU and I/O costs |

For example, the optimizer needs to choose between:

- Full table scan: reading multiple contiguous blocks.
- Index range scan: reading an index and then accessing the corresponding rows.
- Nested loops join: suitable when the outer row source is small and inner lookups are cheap.
- Hash join: typically suitable when joining larger amounts of data.

If NUM_ROWS, NDV, or histograms do not reflect the current data, cardinality estimates can be wrong. When cardinality is wrong, decisions higher up in the plan tree can also be wrong.

### 1.1. Statistics Do Not Always Need Updating After Every DML

A small INSERT into a table with several million rows may not significantly change the estimates for most queries. Conversely, a DELETE or UPDATE affecting a key group of values can strongly alter the data distribution even if the total row count barely changes.

Therefore, deciding when to gather should consider:

- The percentage of rows changed.
- The type of change: INSERT, UPDATE, or DELETE.
- Whether the data distribution changed significantly.
- Which columns are used in predicates/joins.
- Whether critical queries are sensitive to histograms/cardinality.
- The gather cost and when the workload runs.

## 2. Missing Statistics and Stale Statistics

Two important states:

- **Missing statistics**: the object lacks required statistics or has never had statistics gathered.
- **Stale statistics**: statistics exist, but the amount of data change exceeds the threshold Oracle uses to consider statistics no longer fresh.

Automatic Optimizer Statistics Collection finds objects with missing or stale statistics to re-gather them during the maintenance window.

### 2.1. Default STALE_PERCENT

By default, Oracle considers table statistics stale when the number of rows inserted, updated, or deleted exceeds a percentage threshold of the rows in the table at the time of the most recent gather. The default value of the STALE_PERCENT preference is 10%.

Illustrative example:

- A table has 100,000 rows at the most recent gather.
- STALE_PERCENT is 10.
- More than roughly 10,000 modified rows can cause statistics to be marked stale.

This is an evaluation threshold, not a gather schedule. When the threshold is exceeded, Oracle can mark the stats as stale; AutoTask only gathers when the task runs and the object is eligible.

Do not interpret 10% as a rule that “at exactly 10% Oracle immediately gathers.” Modification counters may not yet be flushed to the dictionary, AutoTask may not have reached a maintenance window yet, the task may be disabled, or the object's statistics may be locked.

### 2.2. What Changes Are Tracked?

Oracle tracks DML changes such as INSERT, UPDATE, and DELETE to evaluate statistics. This information is reflected through modification views such as USER_TAB_MODIFICATIONS, ALL_TAB_MODIFICATIONS, and DBA_TAB_MODIFICATIONS.

Bulk load, truncate, partition maintenance, or exchange partition operations may have their own rules/metadata. After a large operation, do not rely solely on a simple modification count; check statistics at the table, partition, and global levels.

### 2.3. STALE_PERCENT Is a Preference

You can view the current preference:

~~~sql
SELECT DBMS_STATS.GET_PREFS(
           'STALE_PERCENT',
           'HR',
           'EMPLOYEES'
       ) AS stale_percent
FROM dual;
~~~

Replace HR and EMPLOYEES with the actual owner/table. If the table does not have its own preference, the returned value may be inherited from a higher level or the default.

Set a custom threshold for a single table:

~~~sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => 'HR',
        tabname => 'EMPLOYEES',
        pname   => 'STALE_PERCENT',
        pvalue  => '15'
    );
END;
/
~~~

A 15% threshold makes Oracle wait for a larger percentage of changes before considering the table stale. Only increase the threshold when you understand the workload and accept that statistics may remain outdated longer. Lowering the threshold can cause more frequent gathers, consuming more resources.

Do not change STALE_PERCENT database-wide just to solve a single table with special behavior. Use a narrowly scoped table preference and document the reason.

## 3. Viewing Statistics and Stale Status

Oracle provides dictionary views to inspect current statistics.

### 3.1. USER_TAB_STATISTICS

~~~sql
SELECT
    table_name,
    num_rows,
    blocks,
    sample_size,
    last_analyzed,
    stale_stats,
    stattype_locked
FROM user_tab_statistics
ORDER BY table_name;
~~~

Key columns:

- NUM_ROWS: estimated number of rows at the time of gather.
- BLOCKS: number of blocks recorded in statistics.
- SAMPLE_SIZE: number of rows used as the sample.
- LAST_ANALYZED: timestamp when statistics were gathered.
- STALE_STATS: YES/NO indicating whether Oracle considers statistics stale.
- STATTYPE_LOCKED: statistics lock status, if locked.

The USER_TAB_STATISTICS view only displays objects in the current schema. DBAs can use DBA_TAB_STATISTICS; users with appropriate privileges can use ALL_TAB_STATISTICS.

### 3.2. Viewing Statistics for a Single Table

~~~sql
SELECT
    owner,
    table_name,
    partition_name,
    num_rows,
    blocks,
    sample_size,
    last_analyzed,
    stale_stats,
    stattype_locked
FROM dba_tab_statistics
WHERE owner = 'HR'
  AND table_name = 'EMPLOYEES'
ORDER BY partition_name NULLS FIRST;
~~~

For non-partitioned tables, PARTITION_NAME is usually NULL. For partitioned tables, there may be statistics per partition as well as global statistics for the table; check the exact statistics level that queries use.

### 3.3. Viewing Column Statistics

~~~sql
SELECT
    column_name,
    num_distinct,
    num_nulls,
    density,
    histogram,
    num_buckets,
    last_analyzed
FROM dba_tab_col_statistics
WHERE owner = 'HR'
  AND table_name = 'EMPLOYEES'
ORDER BY column_name;
~~~

If queries filter on STATUS or DEPARTMENT_ID, column statistics and histograms on these columns can directly affect cardinality estimates.

### 3.4. Viewing Index Statistics

~~~sql
SELECT
    index_name,
    blevel,
    leaf_blocks,
    distinct_keys,
    clustering_factor,
    num_rows,
    last_analyzed
FROM dba_ind_statistics
WHERE owner = 'HR'
  AND table_name = 'EMPLOYEES';
~~~

Fresh table statistics combined with outdated index statistics can still cause the optimizer to misestimate index access costs. DBMS_STATS with an appropriate cascade setting can gather index statistics as well.

## 4. DBA_TAB_MODIFICATIONS and Modification Counters

DBA_TAB_MODIFICATIONS records the volume of DML changes that Oracle tracks for a table/partition. Commonly used columns include:

- INSERTS
- UPDATES
- DELETES
- TIMESTAMP
- TRUNCATED
- DROP_SEGMENTS
- TABLE_OWNER, TABLE_NAME, PARTITION_NAME

### 4.1. Viewing Modification Counters

~~~sql
SELECT
    table_owner,
    table_name,
    partition_name,
    inserts,
    updates,
    deletes,
    timestamp,
    truncated
FROM dba_tab_modifications
WHERE table_owner = 'HR'
  AND table_name = 'EMPLOYEES'
ORDER BY partition_name;
~~~

USER_TAB_MODIFICATIONS is the choice when you only need to inspect the current schema.

### 4.2. Why May Data Not Be Updated Immediately?

Modification information may be recorded asynchronously and not yet flushed into the dictionary view at the moment you query it. Therefore, an empty result or low counts do not necessarily mean no DML occurred.

To synchronize monitoring information before inspecting:

~~~sql
BEGIN
    DBMS_STATS.FLUSH_DATABASE_MONITORING_INFO;
END;
/
~~~

This procedure flushes modification monitoring information for the database. It does not gather statistics for all tables. Afterward, re-query DBA_TAB_MODIFICATIONS and DBA_TAB_STATISTICS.

Execution privileges and visibility scope depend on the account. In production environments, DBAs need to weigh the impact and required privileges before running a database-wide operation.

### 4.3. Modification Counters Are Not a DML Audit Table

These counters serve optimizer statistics, not detailed transaction history. They do not tell you which user modified which row or the old/new values. Do not use DBA_TAB_MODIFICATIONS as a replacement for business auditing.

## 5. Automatic Optimizer Statistics Collection

Oracle has an automated maintenance task named **auto optimizer stats collection**. This task checks for objects with missing or stale statistics and gathers statistics according to internal policies during maintenance windows.

### 5.1. When Does the Task Run?

In Oracle 19c, automated maintenance tasks are scheduled within maintenance windows. Default windows are typically defined on a daily/weekly schedule and can be adjusted by the DBA. Auto optimizer stats collection uses the time/resources allocated in the window; it does not necessarily run immediately when a table becomes stale.

High-level flow:

~~~text
DML / bulk load / partition maintenance
                |
                v
Oracle records modification metadata
                |
                v
Statistics are evaluated as missing or stale
                |
                v
Maintenance window starts
                |
                v
Auto Optimizer Stats Collection selects eligible objects
                |
                v
DBMS_STATS gathers statistics
                |
                v
Dictionary statistics are updated
                |
                v
Optimizer uses new statistics for eligible hard parses
~~~

This is a conceptual flow. Object selection, sample size, parallelism, and execution order are managed by Oracle based on database state and configuration.

### 5.2. Auto Stats Is Usually Enabled by Default

Check the client status:

~~~sql
SELECT
    client_name,
    status,
    window_group
FROM dba_autotask_client
ORDER BY client_name;
~~~

Look for the client named AUTO OPTIMIZER STATS COLLECTION. STATUS indicates whether the task is enabled or disabled.

### 5.3. Checking Tasks by Maintenance Window

~~~sql
SELECT
    window_name,
    optimizer_stats,
    window_active
FROM dba_autotask_window_clients
ORDER BY window_name;
~~~

The DBA_AUTOTASK_WINDOW_CLIENTS view shows which clients are enabled in each window and whether the window is currently active. Column names may differ across releases; if the view in your installation has a different structure, check ALL_TAB_COLUMNS or the Reference for your exact version.

### 5.4. Checking the Maintenance Window Schedule

~~~sql
SELECT
    window_name,
    repeat_interval,
    duration,
    enabled,
    active
FROM dba_scheduler_windows
ORDER BY window_name;
~~~

A disabled window or overly short duration can affect when the task runs. Do not modify schedules based on guesswork; review the workload schedule, maintenance windows, Resource Manager plan, and backup/ETL schedules.

### 5.5. Checking AutoTask History

You can view the execution history of automated maintenance tasks:

~~~sql
SELECT
    client_name,
    window_name,
    window_start_time,
    window_duration,
    job_status
FROM dba_autotask_job_history
ORDER BY window_start_time DESC;
~~~

If the view or columns differ from your version, check dictionary metadata. You can use DBA_AUTOTASK_CLIENT_HISTORY and Scheduler job run details views for additional information.

The history helps answer:

- Did auto stats run in the most recent window?
- Did the job complete or fail?
- Did the window have enough time?
- Was the task disabled or resource-constrained?
- Did the object's statistics change after the job ran?

## 6. Maintenance Windows and Update Timing

A maintenance window is a time interval the database allocates for automated maintenance tasks. Auto stats competes for resources with other tasks and running workloads; Resource Manager can limit the resources available to maintenance tasks.

### 6.1. Why Not Gather Immediately After Every DML?

Gathering statistics consumes CPU and I/O and may read large amounts of data. If statistics were gathered continuously after every small batch, the database could spend too many resources on statistics instead of business workloads.

Oracle uses modification tracking and maintenance windows to balance:

- Statistics fresh enough for the optimizer.
- Collection overhead grouped into appropriate periods.
- Multiple objects processed in a single maintenance pass.
- Primary workload resources kept under control.

### 6.2. Maintenance Windows Do Not Guarantee Every Table Is Gathered

A stale object may not be gathered immediately if:

- Auto optimizer stats collection is disabled.
- The corresponding window is disabled or did not run.
- The window ran out of time before the object was processed.
- Object statistics are locked.
- The object is outside the task's scope or has special conditions.
- The job failed or hit resource limits.

Therefore, inspect the stale status, task status, windows, and job history instead of just waiting.

### 6.3. Choosing When to Gather Manually

Manual gathering is usually appropriate when:

- A large volume of data was just loaded right before a critical workload window.
- A table was just truncated/reloaded or its data distribution changed drastically.
- An ETL job or partition exchange just completed.
- A new table was created and is about to be queried in production.
- There is evidence that outdated statistics are causing wrong cardinality estimates.
- Plans need to be tested before opening a workload or deploying a release.

Avoid broad manual gathering during peak hours without a reason and resource assessment. For very large tables, estimate the duration, parallelism, I/O, and impact on cursor plans before running.

## 7. Using DBMS_STATS for Manual Updates

DBMS_STATS is the primary package for gathering and managing optimizer statistics. Use AUTO_SAMPLE_SIZE instead of manually picking a sample percentage unless there is a specific requirement.

### 7.1. Gathering Statistics for a Single Table

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => 'HR',
        tabname          => 'EMPLOYEES',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => DBMS_STATS.AUTO_CASCADE,
        degree           => DBMS_STATS.AUTO_DEGREE,
        no_invalidate    => DBMS_STATS.AUTO_INVALIDATE
    );
END;
/
~~~

Meaning:

- AUTO_SAMPLE_SIZE: Oracle chooses an appropriate sample.
- METHOD_OPT: specifies how column statistics and histograms are collected.
- AUTO_CASCADE: Oracle decides whether to gather index statistics appropriately.
- AUTO_DEGREE: Oracle chooses the parallel degree.
- AUTO_INVALIDATE: Oracle manages invalidation of dependent cursors using an automatic policy.

Parameters may behave differently depending on version and workload. Do not assume that gathering with the highest degree is always faster; parallel gather can contend for I/O and CPU.

### 7.2. Gathering Schema Statistics

~~~sql
BEGIN
    DBMS_STATS.GATHER_SCHEMA_STATS(
        ownname          => 'HR',
        options          => 'GATHER AUTO',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => DBMS_STATS.AUTO_CASCADE,
        degree           => DBMS_STATS.AUTO_DEGREE
    );
END;
/
~~~

GATHER AUTO targets objects with missing or stale statistics according to DBMS_STATS rules. It is more suitable than unnecessarily gathering the entire schema after every deployment. Even so, assess the schema scope and duration before running in production.

### 7.3. GATHER STALE and GATHER EMPTY

DBMS_STATS supports the following options:

- GATHER: gather across the requested scope.
- GATHER AUTO: gather objects with missing or stale statistics and apply related automatic decisions.
- GATHER STALE: gather objects evaluated as stale.
- GATHER EMPTY: gather objects that do not yet have statistics.

Example:

~~~sql
BEGIN
    DBMS_STATS.GATHER_SCHEMA_STATS(
        ownname => 'HR',
        options => 'GATHER STALE'
    );
END;
/
~~~

Read the DBMS_STATS Reference for the exact OPTIONS supported by the procedure you are using. GATHER AUTO and GATHER STALE are not completely synonymous; AUTO can apply additional automatic logic for missing/stale objects.

### 7.4. Gathering Database Statistics

~~~sql
BEGIN
    DBMS_STATS.GATHER_DATABASE_STATS(
        options          => 'GATHER AUTO',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => DBMS_STATS.AUTO_CASCADE,
        degree           => DBMS_STATS.AUTO_DEGREE
    );
END;
/
~~~

This is a broad-scope operation. Do not run it just to “refresh everything” if only one table or schema has an issue. Prefer gathering only the necessary objects with a resource plan.

### 7.5. Verifying After Gathering

~~~sql
SELECT
    table_name,
    num_rows,
    sample_size,
    last_analyzed,
    stale_stats
FROM user_tab_statistics
WHERE table_name = 'EMPLOYEES';
~~~

Also check column/index statistics and the execution plans of critical SQL statements. A new LAST_ANALYZED timestamp alone does not prove plans improved; you must compare cardinality estimates and runtime.

## 8. Gathering Statistics After Bulk Loads and ETL

Bulk loads can change data distribution very quickly. Waiting for the next maintenance window may be too late if the application begins querying immediately after the load.

### 8.1. After a Direct-Path Load

After SQL*Loader direct path, INSERT /*+ APPEND */, CTAS, or bulk ETL, check whether statistics were automatically collected during the load operation. Some operations support online statistics gathering for table statistics, but you should not assume all column histograms, index statistics, and global/partition statistics are complete.

After the load:

1. Check LAST_ANALYZED and STALE_STATS.
2. Check NUM_ROWS and partition/global statistics.
3. Inspect execution plans of critical queries.
4. Manually gather any missing statistics if needed.

### 8.2. After Truncate and Reload

TRUNCATE resets the row count to 0 but is unlike row-by-row DELETE. When reloading a table, old statistics may not reflect the new row count. If the workload runs immediately after reload, gather statistics appropriately once data loading completes.

### 8.3. After Partition Exchange

Partition exchange is commonly used to load data quickly into a partition. Statistics at the partition, global table, and index partition levels need to be reviewed. For large partitioned tables, incremental statistics can help update global stats without re-scanning every partition.

### 8.4. Incremental Statistics

For partitioned tables, incremental statistics use synopses to help maintain global statistics from partition statistics. You can configure the preference:

~~~sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => 'DW',
        tabname => 'SALES',
        pname   => 'INCREMENTAL',
        pvalue  => 'TRUE'
    );
END;
/
~~~

Incremental statistics are useful when data is loaded by partition and only some partitions change. You need to verify granularity, synopses, global stats, and workload before enabling; not every type of partition maintenance benefits equally.

## 9. Histograms and Data Distribution Changes

The table stale threshold is primarily based on modification volume, but cardinality estimates also depend on value distribution. A column with significant skew may require a histogram.

For example, the ORDER_STATUS column:

- 95% of rows are CLOSED.
- 4% of rows are PAID.
- 1% of rows are PENDING.

A query with WHERE status = 'PENDING' has a very different selectivity than status = 'CLOSED'. If the optimizer only assumes uniform distribution, estimates can be wrong.

### 9.1. METHOD_OPT

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname    => 'APP',
        tabname    => 'ORDERS',
        method_opt => 'FOR ALL COLUMNS SIZE AUTO'
    );
END;
/
~~~

SIZE AUTO allows Oracle to decide on histograms based on workload/column usage and statistics. Avoid mechanically creating histograms on every column with SIZE 254; histograms can make plans depend on bind values and cause plans to flip between queries.

### 9.2. When Row Count Changes Little But Skew Changes Sharply

For example, an UPDATE batch transitions most orders from PENDING to CLOSED. The total row count does not change, but the STATUS distribution shifts significantly. Modification tracking can count the UPDATEs to evaluate staleness, yet the gather decision still depends on thresholds and schedules.

If queries are sensitive to STATUS and plans degrade, the DBA can gather statistics early instead of waiting for the default stale threshold.

## 10. Locking Statistics and Cases Without Automatic Updates

Oracle allows locking statistics to prevent automatic or manual gathers from overwriting an object's statistics.

### 10.1. Checking Lock Status

~~~sql
SELECT
    table_name,
    stattype_locked,
    stale_stats,
    last_analyzed
FROM user_tab_statistics
WHERE stattype_locked IS NOT NULL;
~~~

### 10.2. Locking Table Statistics

~~~sql
BEGIN
    DBMS_STATS.LOCK_TABLE_STATS(
        ownname => 'HR',
        tabname => 'EMPLOYEES'
    );
END;
/
~~~

Locked statistics will not be gathered through normal means. This is useful when preserving verified stats, but it can cause statistics to become outdated if data continues to change.

### 10.3. Unlocking

~~~sql
BEGIN
    DBMS_STATS.UNLOCK_TABLE_STATS(
        ownname => 'HR',
        tabname => 'EMPLOYEES'
    );
END;
/
~~~

After unlocking, the object can be gathered again when stale or on DBA request. Do not lock statistics merely to freeze execution plans without a controlled process and impact evaluation.

### 10.4. When Plan Stability Is Required

If the goal is to control execution plans, evaluate SQL Plan Management (SQL Plan Baselines), SQL patches/profiles, and release controls instead of relying long-term on outdated statistics. Locking stats is a specialized tool, not a comprehensive plan management mechanism.

## 11. Statistics History and Restore Capability

Oracle retains statistics history for a retention period so previous statistics can be restored if a new gather degrades plans.

### 11.1. Viewing Statistics History

~~~sql
SELECT
    table_name,
    stats_update_time
FROM user_tab_stats_history
WHERE table_name = 'EMPLOYEES'
ORDER BY stats_update_time DESC;
~~~

The corresponding DBA/ALL views can be used to inspect objects outside the current schema.

### 11.2. Restoring Statistics by Timestamp

~~~sql
BEGIN
    DBMS_STATS.RESTORE_TABLE_STATS(
        ownname         => 'HR',
        tabname         => 'EMPLOYEES',
        as_of_timestamp => SYSTIMESTAMP - INTERVAL '1' DAY,
        force           => TRUE
    );
END;
/
~~~

This example illustrates restoring stats to a point one day ago; you must select an actual timestamp prior to the problematic gather. FORCE can override lock status in some cases, so do not use it carelessly.

### 11.3. Retention

Check retention:

~~~sql
SELECT DBMS_STATS.GET_STATS_HISTORY_RETENTION
FROM dual;
~~~

It can be adjusted using DBMS_STATS.ALTER_STATS_HISTORY_RETENTION. Increasing retention increases the amount of history metadata stored; choose a duration sufficient for your organization's investigation and statistics rollback procedures.

### 11.4. Restoring Stats Does Not Roll Back Data

RESTORE_TABLE_STATS restores optimizer statistics. It does not roll back INSERT/UPDATE/DELETE operations or recover table data. If data recovery is needed, use appropriate backup/recovery or Flashback mechanisms.

## 12. New Statistics and Execution Plans

When statistics are published, the optimizer can use them for subsequent hard parses. Currently running cursors do not necessarily switch plans immediately; dependent cursors may be invalidated according to the no_invalidate policy.

### 12.1. AUTO_INVALIDATE

DBMS_STATS supports no_invalidate => DBMS_STATS.AUTO_INVALIDATE. This is the default option, usually appropriate so Oracle can manage invalidation gradually instead of forcing immediate mass invalidation.

Avoid setting no_invalidate => FALSE on a large schema without assessing the impact, because invalidating many cursors at once can trigger a hard parse spike.

### 12.2. Checking Plans Before and After

You can retrieve a plan using DBMS_XPLAN:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        sql_id => 'your_sql_id',
        cursor_child_no => 0,
        format => 'ALLSTATS LAST +PEEKED_BINDS'
    )
);
~~~

Compare:

- E-Rows and A-Rows.
- Access paths.
- Join order and join methods.
- Buffers, reads, and elapsed time.
- Bind values, if any.

A plan where E-Rows diverges widely from A-Rows indicates a cardinality estimation issue, though stale statistics are not always the sole cause. You may need to examine predicate correlation, bind sensitivity, skew, dynamic sampling, or SQL transformations.

### 12.3. Pending Statistics

Oracle supports pending statistics to test new stats before publishing them to the entire workload:

~~~sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => 'HR',
        tabname => 'EMPLOYEES',
        pname   => 'PUBLISH',
        pvalue  => 'FALSE'
    );
END;
/
~~~

After gathering, statistics can remain in a pending state. You can enable a session to use pending stats during testing:

~~~sql
ALTER SESSION SET optimizer_use_pending_statistics = TRUE;
~~~

After evaluation, publish or delete the pending statistics using the appropriate DBMS_STATS procedures. Once finished, restore the PUBLISH preference to TRUE if that was the original policy. Pending statistics are a controlled testing tool; clearly manage who sees which stats.

## 13. Real-Time Statistics and Automatic Statistics

Oracle Database 19c includes Real-Time Statistics to supplement statistical information during certain conventional DML operations. This feature gives the optimizer fresher information between full statistics gathers.

Real-time statistics do not replace DBMS_STATS or automatic optimizer stats collection:

- The auto stats task still needs to gather/publish full statistics on schedule.
- Real-time statistics have their own support scope and conditions.
- Not all object types, DML, column statistics, or histograms are updated as in a full gather.
- Check NOTES in dictionary statistics and the 19c documentation to see which stats were generated by conventional DML.

Do not assume that enabling real-time statistics means there is no need to gather stats after bulk loads, partition exchanges, or major data changes.

## 14. Controlling AutoTask

Normally, automatic optimizer stats collection should remain active according to the maintenance policy. Only change its state when there is a clear operational plan.

### 14.1. Disabling the Client

~~~sql
BEGIN
    DBMS_AUTO_TASK_ADMIN.DISABLE(
        client_name => 'auto optimizer stats collection',
        operation   => NULL,
        window_name => NULL
    );
END;
/
~~~

This command disables the client for the specified scope. Do not use it in production merely to avoid a job running at an inconvenient time; first examine windows, Resource Manager, job history, and the time-consuming objects.

### 14.2. Re-enabling

~~~sql
BEGIN
    DBMS_AUTO_TASK_ADMIN.ENABLE(
        client_name => 'auto optimizer stats collection',
        operation   => NULL,
        window_name => NULL
    );
END;
/
~~~

After making changes, re-check DBA_AUTOTASK_CLIENT and DBA_AUTOTASK_WINDOW_CLIENTS. If you only disabled it for a single window, pass the exact window name when re-enabling.

### 14.3. Changing Duration/Windows

Scheduler window schedules can be adjusted, but doing so affects multiple automated maintenance tasks. DBAs must coordinate with backup, ETL, batch, and workload schedules. Do not change a window duration based solely on the gather time of a single table.

## 15. Decision Process for When to Gather

A practical workflow:

### Before Gathering

1. Identify the affected SQL/workload.
2. Check LAST_ANALYZED, STALE_STATS, NUM_ROWS, and sample size.
3. Flush modification monitoring if you need to confirm counters.
4. Inspect table/partition/global statistics.
5. Check whether statistics are locked.
6. Check whether the auto stats task and maintenance windows ran recently.
7. Inspect the current execution plans and cardinality estimates.

### Choosing an Action

| Scenario | Recommended Action |
| --- | --- |
| Small table, low DML, stable plans | Wait for AutoTask |
| Table just crossed stale threshold, non-urgent workload | Monitor AutoTask/next window |
| Large bulk load, queries run immediately after load | Gather the specific table/partition before workload |
| Bad plan and large E-Rows discrepancy | Investigate column stats/skew; gather in a controlled manner |
| Statistics are locked | Identify lock reason, coordinate with owner before unlocking |
| Partition exchange | Inspect partition/global/index stats; consider incremental |
| New gather degraded the plan | Compare plans, consider restoring stats or pending stats |
| AutoTask is not running | Check client status, windows, history, and resource plan |

### After Gathering

1. Check LAST_ANALYZED and STALE_STATS.
2. Inspect table, column, index, and partition statistics.
3. Inspect plans with DBMS_XPLAN.
4. Run a representative workload and compare elapsed time/buffers.
5. Monitor hard parses and invalidations.
6. Record the command, timestamp, options, and results.

## 16. Lab: Observing Stale Statistics

This lab uses a dedicated table to avoid affecting business data.

### 16.1. Create the Table

~~~sql
CREATE TABLE lab_stats_orders (
    order_id NUMBER PRIMARY KEY,
    status VARCHAR2(20),
    amount NUMBER(12, 2),
    created_at DATE
);
~~~

### 16.2. Load Data

~~~sql
BEGIN
    FOR i IN 1 .. 10000 LOOP
        INSERT INTO lab_stats_orders (
            order_id,
            status,
            amount,
            created_at
        )
        VALUES (
            i,
            CASE WHEN MOD(i, 10) = 0 THEN 'PENDING' ELSE 'CLOSED' END,
            MOD(i, 5000) + 1,
            DATE '2025-01-01' + MOD(i, 365)
        );
    END LOOP;
    COMMIT;
END;
/
~~~

### 16.3. Gather Baseline Statistics

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'LAB_STATS_ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => DBMS_STATS.AUTO_CASCADE
    );
END;
/
~~~

Verify:

~~~sql
SELECT
    table_name,
    num_rows,
    last_analyzed,
    stale_stats
FROM user_tab_statistics
WHERE table_name = 'LAB_STATS_ORDERS';
~~~

### 16.4. Introduce Changes Exceeding the Threshold

~~~sql
INSERT INTO lab_stats_orders (
    order_id,
    status,
    amount,
    created_at
)
SELECT
    10000 + LEVEL,
    'PENDING',
    9999,
    SYSDATE
FROM dual
CONNECT BY LEVEL <= 2500;

COMMIT;
~~~

The added rows represent roughly 25% of the 10,000-row baseline. With the default STALE_PERCENT of 10%, the table is likely to be marked stale once monitoring counters are updated.

### 16.5. Flush and Verify

~~~sql
BEGIN
    DBMS_STATS.FLUSH_DATABASE_MONITORING_INFO;
END;
/
~~~

~~~sql
SELECT
    table_name,
    inserts,
    updates,
    deletes,
    timestamp
FROM user_tab_modifications
WHERE table_name = 'LAB_STATS_ORDERS';
~~~

~~~sql
SELECT
    table_name,
    num_rows,
    last_analyzed,
    stale_stats
FROM user_tab_statistics
WHERE table_name = 'LAB_STATS_ORDERS';
~~~

Observe the counters and STALE_STATS. Results may depend on version, timing, and monitoring state; the key takeaway is understanding that flushing counters does not mean gathering.

### 16.6. Gather Stale Statistics

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'LAB_STATS_ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => DBMS_STATS.AUTO_CASCADE
    );
END;
/
~~~

Check LAST_ANALYZED, NUM_ROWS, and STALE_STATS again. Compare with the baseline.

### 16.7. Test a Custom Threshold

~~~sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => USER,
        tabname => 'LAB_STATS_ORDERS',
        pname   => 'STALE_PERCENT',
        pvalue  => '30'
    );
END;
/
~~~

Perform a DML volume smaller than 30%, flush monitoring, and observe the stale state. After the lab, you can delete the table preference to revert to the inherited value:

~~~sql
BEGIN
    DBMS_STATS.DELETE_TABLE_PREFS(
        ownname => USER,
        tabname => 'LAB_STATS_ORDERS',
        pname   => 'STALE_PERCENT'
    );
END;
/
~~~

## 17. Lab: Inspecting AutoTask and Schedules

The following queries require appropriate dictionary privileges:

~~~sql
SELECT client_name, status, window_group
FROM dba_autotask_client
WHERE LOWER(client_name) LIKE '%optimizer stats%';
~~~

~~~sql
SELECT window_name, optimizer_stats, window_active
FROM dba_autotask_window_clients
ORDER BY window_name;
~~~

~~~sql
SELECT window_name, repeat_interval, duration, enabled, active
FROM dba_scheduler_windows
ORDER BY window_name;
~~~

~~~sql
SELECT client_name, window_name, window_start_time, job_status
FROM dba_autotask_job_history
ORDER BY window_start_time DESC;
~~~

Record the client status, window status, and job history. If your lab lacks DBA view privileges, ask a DBA to provide the output or use corresponding ALL/USER views if available.

Do not disable AutoTask on a shared database for exercises. If you need to test enabling/disabling, only do so in a lab database you administer and re-enable it after observing.

## 18. Common Issues

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Table is stale but not gathered yet | AutoTask has not reached a window or is disabled | Check client, windows, and job history |
| Large DML but STALE_STATS is still NO | Monitoring counters not flushed or threshold not exceeded | Flush monitoring and re-check |
| Recent LAST_ANALYZED but plan is still bad | Statistics do not reflect skew/correlation or SQL has another issue | Inspect column stats, histograms, and cardinality |
| Auto stats does not update the table | Statistics are locked | Check STATTYPE_LOCKED and reason for lock |
| Schema-wide gather takes too long | Scope is too broad | Gather stale objects or only required objects |
| Plan changed after gather | Optimizer used new cardinality/stats and picked a different plan | Compare plan/runtime, check history/pending stats |
| Hard parses increased after gather | Cursors were invalidated | Use AUTO_INVALIDATE and plan timing carefully |
| Queries slow after bulk load | AutoTask has not run or stats are incomplete | Gather table/partition before workload |
| Partition stats fresh but global stats stale | Only gathered partitions without maintaining global stats | Check granularity/incremental statistics |
| Modification counters are 0 | Monitoring metadata not flushed or object was just gathered | Flush and check LAST_ANALYZED |
| Increasing STALE_PERCENT reduces job runs | Higher threshold | Re-evaluate threshold against workload |
| Creating histograms broadly causes plan instability | Inappropriate METHOD_OPT or skew/bind sensitivity | Use SIZE AUTO and test plans |
| Restoring stats did not change data | Restore only recovers statistics | Use recovery/flashback for data if needed |

## 19. Operational Checklist

Before concluding that Auto statistics is not working:

- Rule out unrelated NLS settings; focus on the optimizer statistics dictionary.
- Inspect DBA_TAB_STATISTICS and LAST_ANALYZED.
- Flush modification monitoring when you need to confirm counters.
- Check DBA_TAB_MODIFICATIONS.
- Review table/global STALE_PERCENT preferences.
- Check whether statistics are locked.
- Inspect DBA_AUTOTASK_CLIENT.
- Check DBA_AUTOTASK_WINDOW_CLIENTS and DBA_SCHEDULER_WINDOWS.
- Review DBA_AUTOTASK_JOB_HISTORY and job errors.
- Check the Resource Manager plan and maintenance window duration.
- After gathering, compare execution plans and runtime.
- Document preference or schedule changes so they can be reverted.

## 20. Practice Exercises

Use LAB_STATS_ORDERS from Section 16.

### Exercise 1 — Baseline Statistics

Gather statistics for the lab table. Record NUM_ROWS, BLOCKS, SAMPLE_SIZE, and LAST_ANALYZED. Explain the meaning of each column.

### Exercise 2 — Stale Threshold

Insert data exceeding 10% of the baseline. Flush monitoring and then inspect STALE_STATS and USER_TAB_MODIFICATIONS.

### Exercise 3 — Table Preference

Set STALE_PERCENT to 30, perform DML below the threshold, and re-check. Delete the table preference and verify the inherited value.

### Exercise 4 — GATHER AUTO and GATHER STALE

Run each option on the lab schema. Record which objects are gathered and their LAST_ANALYZED timestamps. Explain the difference based on the DBMS_STATS Reference.

### Exercise 5 — Histograms

Create a strongly skewed STATUS distribution. Gather with SIZE AUTO, inspect USER_TAB_COL_STATISTICS, and query common/rare values. Compare estimated rows.

### Exercise 6 — Lock/Unlock Statistics

Lock the lab table's stats, perform DML exceeding the threshold, and observe. Unlock and then gather. Perform this only in the lab schema.

### Exercise 7 — AutoTask

Query the status of auto optimizer stats collection, maintenance windows, and job history. Write a note on when the task could gather the lab table.

### Exercise 8 — Plan Before and After Gather

Run a query filtering on STATUS, inspect DBMS_XPLAN.DISPLAY_CURSOR or EXPLAIN PLAN before and after gather. Compare cardinality, access path, and runtime. Do not draw conclusions solely from plan cost.

## 21. Cleaning Up Lab Data

Run only in the lab schema you created, after completing the exercises:

~~~sql
BEGIN
    DBMS_STATS.DELETE_TABLE_PREFS(
        ownname => USER,
        tabname => 'LAB_STATS_ORDERS',
        pname   => 'STALE_PERCENT'
    );
END;
/

DROP TABLE lab_stats_orders PURGE;
~~~

Do not delete statistics or modify AutoTask for business schemas during lab cleanup. If you modified other preferences, restore their original values before finishing.

## Summary

Automatic Optimizer Statistics Collection identifies objects with missing or stale statistics and gathers them during maintenance windows. Stale does not mean immediate gathering: Oracle relies on modification tracking and STALE_PERCENT, which typically defaults to 10%, while execution timing depends on AutoTask, windows, resources, and object state. DBA_TAB_MODIFICATIONS shows the tracked volume of INSERT/UPDATE/DELETE operations; FLUSH_DATABASE_MONITORING_INFO synchronizes counters before inspection. DBA_TAB_STATISTICS shows LAST_ANALYZED, STALE_STATS, and lock status.

After a bulk load, truncate/reload, partition exchange, or major shift in data distribution, you may need to gather manually before critical workloads instead of waiting for the next window. Use DBMS_STATS with AUTO_SAMPLE_SIZE and appropriate options; consider histograms, index/partition/global stats, incremental stats, and statistics locks. New statistics can change execution plans and invalidate cursors, so compare cardinality estimates, runtime, and history before broad rollout. Auto stats is an essential maintenance mechanism, yet deciding when to gather still requires evaluating the workload and real impact.

## Oracle Reference Documentation

- [Oracle Database SQL Tuning Guide — Gathering Optimizer Statistics (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/gathering-optimizer-statistics.html) — statistics, stale objects, automatic collection, and DBMS_STATS.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_STATS (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_STATS.html) — gather, preferences, history, locking, and restoring statistics.
- [Oracle Database Reference — DBA_TAB_STATISTICS (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_TAB_STATISTICS.html) — table/partition statistics and STALE_STATS.
- [Oracle Database Reference — DBA_TAB_MODIFICATIONS (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_TAB_MODIFICATIONS.html) — modification monitoring counters.
- [Oracle Database Reference — DBA_AUTOTASK_CLIENT (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_AUTOTASK_CLIENT.html) — status of automated maintenance clients.
- [Oracle Database Reference — DBA_AUTOTASK_WINDOW_CLIENTS (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_AUTOTASK_WINDOW_CLIENTS.html) — clients per maintenance window.
- [Oracle Database Reference — DBA_SCHEDULER_WINDOWS (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_SCHEDULER_WINDOWS.html) — maintenance window schedules.
- [Oracle Database Reference — DBA_AUTOTASK_JOB_HISTORY (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_AUTOTASK_JOB_HISTORY.html) — execution history of automated maintenance tasks.
- [Oracle Database SQL Tuning Guide — Real-Time Statistics (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/optimizer-statistics-concepts.html) — optimizer statistics and real-time statistics features.

When deploying on an Oracle release other than 19c, consult the SQL Tuning Guide, DBMS_STATS Reference, and Data Dictionary Reference for your exact version, particularly regarding stale thresholds, AutoTask views, maintenance windows, incremental statistics, and real-time statistics.
