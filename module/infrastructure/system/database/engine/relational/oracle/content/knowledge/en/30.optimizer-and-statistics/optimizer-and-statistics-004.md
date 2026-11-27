# DBMS_STATS: Gathering Statistics by Table, Schema, or Database

The Oracle Database Cost-Based Optimizer (CBO) uses statistics to estimate row counts, filter condition selectivity, join cardinality, index access costs, and execution costs for SQL statement steps. The **DBMS_STATS** package provides the API to gather, manage, back up, restore, and control optimizer statistics.

Statistics do not alter business data in tables. They describe data characteristics at a point in time, such as row counts, block counts, numbers of distinct values, column value distributions, histograms, and index statistics. When data changes significantly, statistics can become stale; the optimizer may then choose an execution plan that is no longer suitable.

DBMS_STATS allows gathering at multiple scopes:

- **Table:** updates statistics only for a single table, its partitions, or related indexes.
- **Schema:** processes multiple tables/indexes belonging to one schema.
- **Database:** gathers statistics across the entire database as configured.

Choose the smallest scope sufficient for the need, configure sampling and histograms appropriate to the data distribution, and verify the results before concluding that performance improved. Do not run a database-wide gather just because a single SQL statement is slow.

This lesson belongs to the **Optimizer and Statistics** topic of *Database Engine Relational Oracle*. It focuses on:

- The role of optimizer statistics and DBMS_STATS.
- Gathering statistics by table, schema, and database.
- Sampling, histograms, index statistics, degree, and partition granularity.
- Distinguishing GATHER, GATHER STALE, and GATHER AUTO.
- Stale statistics, automatic statistics gathering, and preferences.
- Locking, pending statistics, export/import, and restore.
- Monitoring via the data dictionary and controlling execution plan changes.
- Hands-on SQL/PLSQL lab and common errors.

## 1. What Are Optimizer Statistics?

Optimizer statistics are metadata describing tables, columns, indexes, and certain system components. The CBO uses this information to estimate the cost of SQL execution alternatives.

Example query:

~~~sql
SELECT *
FROM orders
WHERE customer_id = 1001;
~~~

The optimizer needs to estimate:

- How many rows does the ORDERS table have?
- How many distinct values does CUSTOMER_ID have?
- How many orders does a customer typically have?
- Is the CUSTOMER_ID distribution uniform or skewed?
- Is there a suitable index, and is that index selective enough?
- Is reading the index and visiting the table cheaper than a full table scan?

If statistics assume CUSTOMER_ID is uniformly distributed while in reality a few customers have massive order volumes, the optimizer may misestimate cardinality and pick a suboptimal plan.

### Main Categories of Statistics

| Category | Common Information | Purpose |
| --- | --- | --- |
| Table statistics | NUM_ROWS, BLOCKS, AVG_ROW_LEN | Estimate table size and row counts. |
| Column statistics | NUM_DISTINCT, NUM_NULLS, LOW_VALUE, HIGH_VALUE, density | Estimate predicate selectivity. |
| Histogram | Frequency or bucket distribution of column values | Describe skewed data to help estimate specific predicates. |
| Index statistics | BLEVEL, LEAF_BLOCKS, DISTINCT_KEYS, CLUSTERING_FACTOR | Estimate index and table access costs. |
| Partition statistics | Per-partition/subpartition and global statistics | Support partition pruning and partitioned table query estimation. |
| System statistics | CPU/I/O characteristics | Support hardware and I/O cost modeling. |
| Fixed object statistics | Statistics for dynamic performance/fixed tables | Help the optimizer plan dictionary/fixed object queries. |

### Statistics Are Not Live Data

NUM_ROWS can differ from the current row count if statistics have not been refreshed. LOW_VALUE/HIGH_VALUE are statistical values, not data constraints. Histograms describe distribution at collection time; they do not automatically update on every INSERT.

Statistics can become stale or no longer representative of the current workload. Always inspect collection timestamps, modifications since then, and data characteristics.

## 2. DBMS_STATS and Core APIs

DBMS_STATS is a PL/SQL package provided by Oracle to manage optimizer statistics. Commonly used procedures include:

| API | Scope |
| --- | --- |
| GATHER_TABLE_STATS | One table, optionally specifying a partition/subpartition. |
| GATHER_SCHEMA_STATS | Objects belonging to one schema. |
| GATHER_DATABASE_STATS | Database scope. |
| GATHER_DICTIONARY_STATS | Dictionary objects. |
| GATHER_FIXED_OBJECTS_STATS | Fixed tables/dynamic performance views. |
| GATHER_SYSTEM_STATS | System CPU/I/O characteristics statistics. |
| EXPORT_TABLE_STATS / IMPORT_TABLE_STATS | Back up/import statistics for a table. |
| EXPORT_SCHEMA_STATS / IMPORT_SCHEMA_STATS | Back up/import schema statistics. |
| RESTORE_TABLE_STATS | Restore table statistics from history if still within retention. |

DBMS_STATS should be preferred over the legacy ANALYZE ... COMPUTE/ESTIMATE STATISTICS command for standard optimizer statistics management. ANALYZE still serves other purposes such as VALIDATE STRUCTURE, but should not be used as a statistics-gathering workflow in place of DBMS_STATS.

### Execution Privileges

A schema can gather statistics on its own objects with appropriate privileges. Gathering for another schema or the entire database typically requires appropriate administrative privileges. In production environments, broad operations should be handled by DBAs or controlled operational jobs; do not grant administrative privileges just so an application can run arbitrary gathers.

### Checking Package Signatures and Parameters by Version

API signatures, defaults, and certain options can change across Oracle releases. You can inspect the package specification in the database:

~~~sql
DESC DBMS_STATS
~~~

Or query ALL_ARGUMENTS/DBA_ARGUMENTS when you need to confirm parameter names, types, and order. Always consult documentation matching your running database version before putting commands into deployment scripts.

## 3. Gathering Statistics for a Single Table

GATHER_TABLE_STATS is the right API when a specific table has just received a large load, shifted distribution, or needs statistics refreshed after maintenance.

Example syntax:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => 'SALES',
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

Key parameters:

- `ownname`: owner/schema containing the table; object names are typically passed in uppercase if created without quoted identifiers.
- `tabname`: table name.
- `estimate_percent`: sample percentage; AUTO_SAMPLE_SIZE lets Oracle choose automatically.
- `method_opt`: collection policy for column statistics and histograms.
- `cascade`: whether to gather related index statistics; AUTO_CASCADE lets Oracle decide.
- `degree`: parallelism degree; AUTO_DEGREE lets Oracle decide automatically.
- `no_invalidate`: how dependent cursors are handled when statistics change; AUTO_INVALIDATE lets Oracle manage invalidation timing.

You do not need to specify every parameter in every call. In most cases, start with AUTO_SAMPLE_SIZE, method_opt with SIZE AUTO, and let Oracle manage cascade/degree/invalidation by policy.

### Gathering a Table in the Current Schema

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'CUSTOMERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt => 'FOR ALL COLUMNS SIZE AUTO',
        cascade => TRUE
    );
END;
/
~~~

CASCADE TRUE requests gathering index statistics alongside the table. If the table has many indexes or the workload is resource-sensitive, consider AUTO_CASCADE or targeted gathering.

### Gathering a Single Partition

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => 'SALES',
        tabname => 'ORDERS',
        partname => 'P_2026_10',
        granularity => 'PARTITION',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt => 'FOR ALL COLUMNS SIZE AUTO'
    );
END;
/
~~~

PARTNAME specifies the partition; GRANULARITY controls which partition/global statistics levels are collected. For partitioned tables, choose granularity based on the workload and how the optimizer uses global/partition statistics. Do not assume gathering a single partition automatically produces all required global statistics in every configuration.

### Re-Gathering After a Bulk Load

After loading a large volume of data into a table, old statistics may no longer be representative. You can run a gather on the table once loading finishes:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => 'STAGING',
        tabname => 'FACT_SALES',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt => 'FOR ALL COLUMNS SIZE AUTO',
        cascade => DBMS_STATS.AUTO_CASCADE
    );
END;
/
~~~

If loading by partition, consider incremental statistics and gathering the relevant partition instead of scanning a massive table in full.

## 4. Gathering Statistics by Schema

GATHER_SCHEMA_STATS gathers statistics for tables and related statistical objects within a schema. This is the right option when multiple tables in the same schema have just been loaded, changed significantly, or need scheduled maintenance updates.

Example:

~~~sql
BEGIN
    DBMS_STATS.GATHER_SCHEMA_STATS(
        ownname          => 'SALES',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => DBMS_STATS.AUTO_CASCADE,
        degree           => DBMS_STATS.AUTO_DEGREE,
        options          => 'GATHER AUTO',
        no_invalidate    => DBMS_STATS.AUTO_INVALIDATE
    );
END;
/
~~~

### Key Parameters

- OWNNAME: schema to gather; not the database name.
- ESTIMATE_PERCENT: sampling for table statistics; AUTO_SAMPLE_SIZE lets Oracle choose.
- METHOD_OPT: column statistics and histogram policy.
- CASCADE: whether to gather index statistics with tables.
- DEGREE: parallelism for the gather job.
- OPTIONS: object selection scope, such as GATHER, GATHER STALE, GATHER EMPTY, or GATHER AUTO.
- NO_INVALIDATE: cursor invalidation policy after statistics change.

GATHER_SCHEMA_STATS does not create a schema snapshot or gather all dictionary metadata. It processes statistical objects in the schema according to the chosen options and current state.

### Gathering All Required Objects in a Schema

If you want to gather all tables in a schema, use OPTIONS => 'GATHER':

~~~sql
BEGIN
    DBMS_STATS.GATHER_SCHEMA_STATS(
        ownname => 'SALES',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt => 'FOR ALL COLUMNS SIZE AUTO',
        cascade => DBMS_STATS.AUTO_CASCADE,
        options => 'GATHER'
    );
END;
/
~~~

This command can be resource-intensive if the schema is large. Before running it, review the number of tables, partitions, data volume, and maintenance window.

### Processing Only Stale or Missing Objects

~~~sql
BEGIN
    DBMS_STATS.GATHER_SCHEMA_STATS(
        ownname => 'SALES',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt => 'FOR ALL COLUMNS SIZE AUTO',
        options => 'GATHER AUTO'
    );
END;
/
~~~

GATHER AUTO lets Oracle choose which objects need gathering based on statistics status. GATHER STALE targets objects identified as stale; GATHER EMPTY targets objects with no statistics yet. Choose options by goal rather than always gathering everything.

### Gathering the Current Schema

~~~sql
BEGIN
    DBMS_STATS.GATHER_SCHEMA_STATS(
        ownname => USER,
        options => 'GATHER AUTO'
    );
END;
/
~~~

USER returns the current schema name. For stored procedures or jobs running under a different owner, confirm the effective user and privileges before using it.

## 5. Gathering Database-Wide Statistics

GATHER_DATABASE_STATS has a broad scope, suited to database administration plans or after major changes across multiple schemas. It is not the default choice for a single problematic table.

~~~sql
BEGIN
    DBMS_STATS.GATHER_DATABASE_STATS(
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => DBMS_STATS.AUTO_CASCADE,
        degree           => DBMS_STATS.AUTO_DEGREE,
        options          => 'GATHER AUTO',
        no_invalidate    => DBMS_STATS.AUTO_INVALIDATE
    );
END;
/
~~~

Database-wide gathering can read huge data volumes, consume CPU/I/O, and affect active workloads. Run it in a maintenance window, monitor duration and resources, and clearly define the object scope processed.

### When to Use GATHER_DATABASE_STATS?

- After a migration or bulk load impacting multiple schemas.
- When deploying a new database and broad initial statistics collection is needed.
- Under a tested administrative schedule with an appropriate maintenance window.
- When a DBA needs to synchronize statistics status across multiple schemas after major infrastructure or data changes.

Do not reflexively run a database gather when a single SQL statement is slow. First inspect the plan, relevant table statistics, and data changes.

### GATHER_DICTIONARY_STATS

Dictionary statistics serve queries on data dictionary objects. Oracle provides a dedicated procedure:

~~~sql
BEGIN
    DBMS_STATS.GATHER_DICTIONARY_STATS;
END;
/
~~~

This is an administrative task, typically performed per Oracle recommendations or after major changes affecting the dictionary. Do not substitute it by arbitrarily gathering individual SYS tables.

### GATHER_FIXED_OBJECTS_STATS

Fixed tables are internal structures accessed via dynamic performance views, usually named V$. A dedicated API is provided:

~~~sql
BEGIN
    DBMS_STATS.GATHER_FIXED_OBJECTS_STATS;
END;
/
~~~

Fixed object statistics should be gathered once a representative workload is running, because activity figures and observed row counts vary with operating state. It is not necessary to run it immediately after database startup with near-zero workload.

### GATHER_SYSTEM_STATS

System statistics describe CPU/I/O characteristics used by the optimizer in its cost model. Gathering or setting system statistics is a specialized task; perform it only under DBA procedures, with a representative workload and clear understanding of NOWORKLOAD/WORKLOAD modes for your version. Do not confuse system stats with table stats.

## 6. Choosing the Gather Scope

| Scenario | Typically Appropriate API | Notes |
| --- | --- | --- |
| A single table after bulk load | GATHER_TABLE_STATS | Can gather related indexes and partitions. |
| A single newly loaded partition | GATHER_TABLE_STATS with PARTNAME | Choose GRANULARITY and incremental stats. |
| Many stale tables in one schema | GATHER_SCHEMA_STATS with GATHER STALE/AUTO | Avoid scanning unrelated schemas. |
| Multiple schemas after a major migration | GATHER_DATABASE_STATS | Requires maintenance window and resource monitoring. |
| Slow dictionary queries after major changes | GATHER_DICTIONARY_STATS | A DBA task. |
| V$ and fixed object queries need statistics | GATHER_FIXED_OBJECTS_STATS | Gather when a representative workload is active. |
| Optimizer cost model needs tuning to hardware | GATHER_SYSTEM_STATS | Requires measurement process and DBA evaluation. |

A sound workflow starts from the specific objects in the execution plan, checks for stale/missing statistics, and expands scope only when evidence warrants it.

## 7. Sampling, estimate_percent, and method_opt

Gathering statistics can read all data or use sampling. DBMS_STATS provides AUTO_SAMPLE_SIZE so Oracle selects an appropriate sampling approach. In most cases, this is a good starting point; there is no need to hardcode a small percentage just to make gathering faster.

### ESTIMATE_PERCENT

- AUTO_SAMPLE_SIZE: Oracle automatically picks the sampling method/size to produce reliable statistics.
- A specific number from 0 to 100: requests an operator-chosen sample percentage.
- NULL in these APIs can have version-specific semantics; check documentation instead of guessing.

Example:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => 'SALES',
        tabname => 'ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE
    );
END;
/
~~~

Too small a sample can miss rare values or skewed distributions, causing inaccurate cardinality estimates. A 100% sample is not automatically best: it can consume far more I/O/CPU without materially changing plans. Measure and start with AUTO_SAMPLE_SIZE before intervening.

### BLOCK_SAMPLE

BLOCK_SAMPLE controls sampling by blocks instead of by rows. Block sampling can be faster in some cases, but if data is physically clustered by block, the sample may not represent the overall distribution well. Do not enable it just to reduce gather time; consider physical layout and data distribution.

### METHOD_OPT and Histograms

METHOD_OPT determines which columns receive column statistics and histograms:

~~~sql
method_opt => 'FOR ALL COLUMNS SIZE AUTO'
~~~

SIZE AUTO lets Oracle decide which columns need histograms based on workload/usage info and data characteristics. This is usually wiser than creating histograms on every column.

Common forms:

- FOR ALL COLUMNS SIZE 1: gather column stats without creating histograms.
- FOR ALL COLUMNS SIZE AUTO: Oracle decides histograms automatically.
- FOR COLUMNS SIZE 254 STATUS: request a histogram on STATUS with the specified maximum bucket count.
- FOR COLUMNS SIZE REPEAT STATUS: repeat the previous histogram choice for the column per version semantics.

Example:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => 'SALES',
        tabname => 'ORDERS',
        method_opt => 'FOR ALL COLUMNS SIZE AUTO'
    );
END;
/
~~~

### What Are Histograms Used For?

Suppose ORDERS.STATUS has 90% CLOSED rows and 10% OPEN rows. If the optimizer assumes a uniform distribution across values, it may misestimate the row count for:

~~~sql
SELECT *
FROM orders
WHERE status = 'OPEN';
~~~

Histograms supply value distribution info so the optimizer can better estimate specific predicates. Common histogram types include frequency, top-frequency, height-balanced, and hybrid; which type is created depends on version, number of distinct values, sampling, and Oracle's decision logic.

### Do Not Create Histograms Mechanically Across All Columns

Histograms can help certain queries, but also cause the optimizer to choose different plans based on literal/bind values, affecting adaptive cursor sharing and plan stability. Histograms are unnecessary on every column, especially uniformly distributed columns or columns unused in key predicates.

Prefer SIZE AUTO, monitor the workload, and specify histograms manually only after proving data skew and query need.

### Column Usage and Workload

Oracle tracks how columns are used in predicates/joins/grouping to inform histogram decisions under SIZE AUTO. Gathering stats immediately after table creation before the workload runs may lack usage info. On new systems, run a representative workload before re-gathering if usage-based histograms are needed.

## 8. Index Statistics, Cascade, and Granularity

### CASCADE

CASCADE determines whether to gather statistics on related indexes when gathering table stats:

- TRUE: gather index stats alongside the table.
- FALSE: do not request gathering index stats.
- DBMS_STATS.AUTO_CASCADE: let Oracle decide by policy.

Example:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => 'SALES',
        tabname => 'ORDERS',
        cascade => DBMS_STATS.AUTO_CASCADE
    );
END;
/
~~~

Index stats such as LEAF_BLOCKS, BLEVEL, DISTINCT_KEYS, and CLUSTERING_FACTOR affect index access cost estimates. If an index was just rebuilt or data changed heavily, consider re-gathering table/index stats within the needed scope.

### DEGREE

DEGREE controls parallelism during gathering. You can specify an explicit number, DEFAULT, or AUTO_DEGREE depending on version. Parallel gathering reduces duration for some workloads, but increases CPU/I/O contention and can affect production queries.

Do not set a very high degree without measuring load. If gathering runs in a maintenance window, size parallelism to available resources and Resource Manager limits.

### GRANULARITY for Partitioned Tables

Granularity options can include:

- AUTO: Oracle selects the appropriate level.
- GLOBAL: global statistics only.
- PARTITION: per-partition statistics.
- SUBPARTITION: per-subpartition statistics.
- GLOBAL AND PARTITION: both global and partition statistics.
- ALL: all applicable levels, including subpartitions where supported.

Exact option names and detailed behavior depend on partitioning type/version; check package documentation. For large partitioned tables, global stats and partition stats serve different query patterns. Queries filtering on the partition key benefit from partition stats; queries spanning many partitions may need global stats.

### INCREMENTAL Statistics

For large partitioned tables, incremental statistics can reduce the cost of maintaining global statistics by using synopses per partition. Configure via table preferences:

~~~sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => 'SALES',
        tabname => 'FACT_SALES',
        pname => 'INCREMENTAL',
        pvalue => 'TRUE'
    );
END;
/
~~~

When incremental is enabled, gathering a partition updates synopses and helps compute global stats without re-scanning every partition. Effectiveness depends on partitioning, statistics type, Oracle version, and data loading method. Also inspect INCREMENTAL_LEVEL, INCREMENTAL_STALENESS, and related preferences as needed.

## 9. GATHER, GATHER STALE, GATHER EMPTY, and GATHER AUTO

OPTIONS values in GATHER_SCHEMA_STATS/GATHER_DATABASE_STATS select which objects to gather:

| OPTIONS | General Meaning |
| --- | --- |
| GATHER | Gather statistics for the specified object scope, including objects that already have stats. |
| GATHER STALE | Select objects whose statistics are determined to be stale. |
| GATHER EMPTY | Select objects that do not yet have statistics. |
| GATHER AUTO | Let Oracle select objects needing gathering, including stale/empty cases per API rules. |

Example:

~~~sql
BEGIN
    DBMS_STATS.GATHER_SCHEMA_STATS(
        ownname => 'SALES',
        options => 'GATHER STALE'
    );
END;
/
~~~

GATHER STALE is useful for periodic jobs or after many tables change. GATHER EMPTY is useful when initializing statistics on objects lacking stats. GATHER AUTO is the standard automated option for maintenance; still monitor actual runtime and scope.

### GATHER_TABLE_STATS Does Not Use Schema/Database OPTIONS

Do not copy the OPTIONS parameter from GATHER_SCHEMA_STATS into GATHER_TABLE_STATS if the API signature does not support it. For a specific table, call GATHER_TABLE_STATS directly. To check stale status beforehand, query dictionary views or let schema/database gather select objects.

### GATHER AUTO Does Not Mean Everything Gets Gathered

Oracle may skip objects that do not need gathering or have locked stats. Do not conclude a gather failed just because some tables do not get a newer LAST_ANALYZED. Check operation output, object status, preferences, and lock status.

## 10. Stale Statistics and Data Modification Tracking

Statistics are considered stale when data has changed sufficiently since the last gather according to Oracle's threshold/policy. Stale statistics do not guarantee plans are wrong; they are a signal to consider refreshing.

Oracle tracks DML modifications on monitored tables. Insert/update/delete counts are recorded and can be viewed via DBA_TAB_MODIFICATIONS or USER_TAB_MODIFICATIONS depending on privileges.

### Viewing Table Statistics Timestamps and Status

~~~sql
SELECT table_name,
       num_rows,
       blocks,
       last_analyzed,
       stale_stats,
       stattype_locked
FROM user_tab_statistics
ORDER BY table_name;
~~~

STALE_STATS and STATTYPE_LOCKED may be NULL or vary depending on object, partition, and version. For other schemas, use ALL_TAB_STATISTICS/DBA_TAB_STATISTICS.

### Viewing Recorded DML Modifications

~~~sql
SELECT table_name,
       inserts,
       updates,
       deletes,
       timestamp,
       truncated,
       drop_segments
FROM user_tab_modifications
ORDER BY timestamp DESC;
~~~

This view provides change information since the most recent stats gather per the monitoring mechanism. Numbers may not appear instantaneously in the view; Oracle aggregates monitoring info internally.

If you need to flush monitoring info for inspection:

~~~sql
BEGIN
    DBMS_STATS.FLUSH_DATABASE_MONITORING_INFO;
END;
/
~~~

This procedure flushes in-memory monitoring info to dictionary views. It is an observation aid, not a stats gather, and does not update NUM_ROWS or histograms.

### STALE_PERCENT Threshold

DBMS_STATS provides the STALE_PERCENT table preference to adjust the change threshold at which statistics are marked stale. The default is typically 10% in common configurations, though it can be altered at table/schema/global levels and behavior depends on version.

Example:

~~~sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => 'SALES',
        tabname => 'ORDERS',
        pname => 'STALE_PERCENT',
        pvalue => '15'
    );
END;
/
~~~

Do not raise or lower thresholds merely to reduce gather frequency. Small tables, append-only tables, skewed tables, or tables changing heavily by partition may require different policies.

### STALE_STATS vs. Missing Statistics

- EMPTY: object has no statistics yet.
- STALE: statistics exist, but enough changes have occurred to cross the threshold.
- FRESH: current statistics are not marked stale by monitoring.

FRESH does not guarantee histograms or samples represent every query. If data distribution shifts without monitoring marking stats stale, plans may still need manual review.

## 11. Automatic Optimizer Statistics Gathering

Oracle includes an automatic maintenance task to collect optimizer statistics for objects that need them. In common versions, the task's display name is **auto optimizer stats collection** and is run by the Scheduler during maintenance windows.

The task selects objects with stale or missing statistics. It reduces the need for DBAs to manually gather entire schemas/databases on fixed schedules, but does not replace monitoring special tables or sensitive workloads.

### Checking Automatic Task Status

~~~sql
SELECT client_name,
       status,
       window_group
FROM dba_autotask_client
WHERE client_name = 'auto optimizer stats collection';
~~~

Window information:

~~~sql
SELECT window_name,
       window_group,
       enabled
FROM dba_scheduler_windows
ORDER BY window_name;
~~~

Task/window names and dictionary access privileges depend on version. Query DBA_AUTOTASK_CLIENT/DBA_AUTOTASK_WINDOW_CLIENTS and Scheduler views to verify rather than assuming the task is always running.

### Viewing Gather Operations History

~~~sql
SELECT operation,
       target,
       start_time,
       end_time,
       status
FROM dba_optstat_operations
ORDER BY start_time DESC;
~~~

DBA_OPTSTAT_OPERATIONS provides optimizer statistics operation history. You can view task details if needed:

~~~sql
SELECT *
FROM dba_optstat_operation_tasks
ORDER BY start_time DESC;
~~~

View column structures can vary between releases; run DESC to check before building monitoring scripts.

### Should You Disable Automatic Stats Gathering?

Do not disable automatic optimizer stats collection just because one gather caused slowness. First identify the object, window, duration, and resource usage. If adjustments are needed, a DBA can tune the maintenance window, preferences, or per-object policies. Disabling the task system-wide can leave many tables stale for extended periods and cause poor plans.

## 12. DBMS_STATS Preferences

DBMS_STATS allows setting preferences to control statistics collection at global, database, schema, or table scope. Preferences keep policies consistent without passing every parameter in each command.

Common preferences:

| Preference | Purpose |
| --- | --- |
| ESTIMATE_PERCENT | Default sample percentage. |
| METHOD_OPT | How column stats/histograms are collected. |
| DEGREE | Parallelism level. |
| CASCADE | Index stats gather policy. |
| GRANULARITY | Table/partition/subpartition stats level. |
| STALE_PERCENT | Change threshold for marking stale. |
| INCREMENTAL | Enable incremental statistics for partitioned tables. |
| PUBLISH | Automatically publish new stats or keep them pending. |
| NO_INVALIDATE | Cursor invalidation policy. |

### Viewing a Preference

~~~sql
SELECT DBMS_STATS.GET_PREFS(
           pname => 'METHOD_OPT',
           ownname => 'SALES',
           tabname => 'ORDERS'
       ) AS method_opt
FROM dual;
~~~

You can use GET_PREFS to inspect a specific object's preference; returned values may be inherited from a higher level if the object has no override.

### Setting a Table Preference

~~~sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => 'SALES',
        tabname => 'ORDERS',
        pname => 'METHOD_OPT',
        pvalue => 'FOR ALL COLUMNS SIZE AUTO'
    );
END;
/
~~~

The preference is stored for the object and affects future gathers; it does not immediately gather stats when SET_TABLE_PREFS is called.

### Setting a Schema Preference

~~~sql
BEGIN
    DBMS_STATS.SET_SCHEMA_PREFS(
        ownname => 'SALES',
        pname => 'ESTIMATE_PERCENT',
        pvalue => 'DBMS_STATS.AUTO_SAMPLE_SIZE'
    );
END;
/
~~~

Pvalue is a string; valid values must match the preference and release. For package constant expressions, verify how the API interprets the preference on your running version. When unsure, set values via the specific API or check GET_PREFS afterward.

### Deleting a Preference Override

~~~sql
BEGIN
    DBMS_STATS.DELETE_TABLE_PREFS(
        ownname => 'SALES',
        tabname => 'ORDERS',
        pname => 'METHOD_OPT'
    );
END;
/
~~~

DELETE_TABLE_PREFS removes the table-level override so the object inherits the schema/global preference. Do not confuse deleting a preference with deleting table statistics.

## 13. Locking and Unlocking Statistics

You can lock statistics on a table/schema/database so automatic or regular gathers cannot modify them. Locking stats is occasionally useful for very static tables or tightly plan-controlled systems, but leaving stats locked too long can cause the optimizer to rely on outdated figures.

### Locking Table Statistics

~~~sql
BEGIN
    DBMS_STATS.LOCK_TABLE_STATS(
        ownname => 'SALES',
        tabname => 'ORDERS'
    );
END;
/
~~~

### Unlocking

~~~sql
BEGIN
    DBMS_STATS.UNLOCK_TABLE_STATS(
        ownname => 'SALES',
        tabname => 'ORDERS'
    );
END;
/
~~~

Corresponding APIs exist for schema/database scope, such as LOCK_SCHEMA_STATS, UNLOCK_SCHEMA_STATS, LOCK_DATABASE_STATS, and UNLOCK_DATABASE_STATS. Use broad locks only with a clear governance plan.

### Checking Lock Status

~~~sql
SELECT table_name,
       stattype_locked,
       last_analyzed,
       stale_stats
FROM user_tab_statistics
ORDER BY table_name;
~~~

STATTYPE_LOCKED shows the type of statistics locked in metadata. Check both table and partition levels when working with partitioned tables.

### FORCE When Gathering

Some gather APIs accept a FORCE parameter to allow the operation even when stats are locked. FORCE is an intentional override; do not use it to bypass a lock without understanding why the lock was placed. Before forcing, confirm the owner, scope, and recovery plan.

## 14. Pending Statistics: Testing Before Publishing

Pending statistics allow gathering new statistics without immediately publishing them as active default statistics. DBAs can test execution plans in a session with OPTIMIZER_USE_PENDING_STATISTICS enabled before publishing.

### Enabling Pending Stats Mode

~~~sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => 'SALES',
        tabname => 'ORDERS',
        pname => 'PUBLISH',
        pvalue => 'FALSE'
    );
END;
/
~~~

### Gathering New Statistics

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => 'SALES',
        tabname => 'ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt => 'FOR ALL COLUMNS SIZE AUTO'
    );
END;
/
~~~

Because PUBLISH=FALSE, the new statistics are kept in a pending state instead of immediately replacing published stats.

### Using Pending Stats in a Test Session

~~~sql
ALTER SESSION SET optimizer_use_pending_statistics = TRUE;

EXPLAIN PLAN FOR
SELECT *
FROM sales.orders
WHERE customer_id = 1001;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

This session can generate plans based on pending stats. Compare against plans with OPTIMIZER_USE_PENDING_STATISTICS=FALSE and against actual execution in a test environment.

### Publishing Pending Stats

~~~sql
BEGIN
    DBMS_STATS.PUBLISH_PENDING_STATS(
        ownname => 'SALES',
        tabname => 'ORDERS'
    );
END;
/
~~~

Once published, pending statistics become published stats. You can reset the PUBLISH preference to TRUE so subsequent gathers auto-publish:

~~~sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => 'SALES',
        tabname => 'ORDERS',
        pname => 'PUBLISH',
        pvalue => 'TRUE'
    );
END;
/
~~~

### Deleting Pending Stats

If test results are unsatisfactory:

~~~sql
BEGIN
    DBMS_STATS.DELETE_PENDING_STATS(
        ownname => 'SALES',
        tabname => 'ORDERS'
    );
END;
/
~~~

Pending stats enable controlled testing; they do not automatically guarantee better execution plans. Use a representative SQL workload and compare runtime metrics, not just EXPLAIN PLAN.

## 15. Exporting, Importing, and Restoring Statistics

Before a major change, you can export statistics into a statistics table to store a snapshot. This is an explicit backup independent of stats history.

### Creating a Statistics Table

~~~sql
BEGIN
    DBMS_STATS.CREATE_STAT_TABLE(
        ownname => 'SALES',
        stattab => 'STATS_BACKUP'
    );
END;
/
~~~

A statistics table is a table managed by DBMS_STATS to hold statistics metadata. It does not contain copies of business data.

### Exporting Table Statistics

~~~sql
BEGIN
    DBMS_STATS.EXPORT_TABLE_STATS(
        ownname => 'SALES',
        tabname => 'ORDERS',
        stattab => 'STATS_BACKUP',
        statid => 'ORDERS_BEFORE_CHANGE',
        cascade => TRUE
    );
END;
/
~~~

STATID distinguishes multiple snapshots in the same statistics table. To export a schema/database, EXPORT_SCHEMA_STATS and EXPORT_DATABASE_STATS APIs are available depending on version.

### Importing Saved Statistics

~~~sql
BEGIN
    DBMS_STATS.IMPORT_TABLE_STATS(
        ownname => 'SALES',
        tabname => 'ORDERS',
        stattab => 'STATS_BACKUP',
        statid => 'ORDERS_BEFORE_CHANGE',
        cascade => TRUE,
        no_invalidate => DBMS_STATS.AUTO_INVALIDATE
    );
END;
/
~~~

Importing restores the exported statistics for the corresponding object. It does not roll back table data, indexes, or DML; it only changes optimizer statistics.

### Restoring from Statistics History

Oracle maintains stats history within a configured retention period. You can restore table stats to an earlier timestamp:

~~~sql
BEGIN
    DBMS_STATS.RESTORE_TABLE_STATS(
        ownname => 'SALES',
        tabname => 'ORDERS',
        as_of_timestamp => SYSTIMESTAMP - INTERVAL '1' DAY,
        force => TRUE
    );
END;
/
~~~

RESTORE_TABLE_STATS uses timestamps from stats history. If the timestamp falls outside retention or history lacks a matching entry, the operation cannot restore as desired. Verify retention and availability before relying on history in a rollback plan.

### Adjusting Retention

DBMS_STATS provides ALTER_STATS_HISTORY_RETENTION to configure history retention duration. Increasing retention requires considering SYSAUX storage capacity and operational policy:

~~~sql
BEGIN
    DBMS_STATS.ALTER_STATS_HISTORY_RETENTION(31);
END;
/
~~~

The number 31 is an illustrative day count, not a default recommendation for every database. Check GET_STATS_HISTORY_RETENTION and GET_STATS_HISTORY_AVAILABILITY before changing it.

### Cleaning Up the Statistics Table When No Longer Needed

~~~sql
BEGIN
    DBMS_STATS.DROP_STAT_TABLE(
        ownname => 'SALES',
        stattab => 'STATS_BACKUP'
    );
END;
/
~~~

Keep exported backups throughout the plan transition period and drop them only once you confirm rollback is no longer needed.

## 16. Monitoring Statistics in the Data Dictionary

After gathering, inspect metadata to confirm objects were processed, check update timestamps, and verify key attributes.

### Table Statistics

~~~sql
SELECT table_name,
       num_rows,
       blocks,
       avg_row_len,
       last_analyzed,
       stale_stats,
       stattype_locked
FROM user_tab_statistics
ORDER BY table_name;
~~~

For partitioned tables, also inspect PARTITION_NAME and GLOBAL_STATS/USER_STATS if needed. Use ALL_TAB_STATISTICS or DBA_TAB_STATISTICS for broader scope.

### Column Statistics and Histograms

~~~sql
SELECT table_name,
       column_name,
       num_distinct,
       num_nulls,
       density,
       histogram,
       num_buckets,
       last_analyzed
FROM user_tab_col_statistics
WHERE table_name = 'ORDERS'
ORDER BY column_name;
~~~

HISTOGRAM indicates the stored histogram type, and NUM_BUCKETS shows the bucket count. Do not infer histogram quality from bucket count alone; inspect data distribution and query predicates.

### Index Statistics

~~~sql
SELECT index_name,
       blevel,
       leaf_blocks,
       distinct_keys,
       clustering_factor,
       num_rows,
       last_analyzed
FROM user_ind_statistics
WHERE table_name = 'ORDERS'
ORDER BY index_name;
~~~

CLUSTERING_FACTOR reflects the correlation between index key order and row location in the table; it impacts the estimated cost of table access via the index.

### Partition Statistics

~~~sql
SELECT table_name,
       partition_name,
       num_rows,
       blocks,
       last_analyzed,
       stale_stats
FROM user_tab_statistics
WHERE table_name = 'FACT_SALES'
ORDER BY partition_name;
~~~

Distinguish rows where PARTITION_NAME is NULL (global/table-level depending on object) from individual partitions. When checking a partitioned table, do not look only at the single table-level row.

### Gather History

~~~sql
SELECT operation,
       target,
       start_time,
       end_time,
       status
FROM user_optstat_operations
ORDER BY start_time DESC;
~~~

USER_OPTSTAT_OPERATIONS shows optimizer stats operations belonging to the current user if the version provides this view. DBA_OPTSTAT_OPERATIONS covers broader administrative scope.

## 17. Statistics and Execution Plans

Gathering stats can cause the optimizer to choose a different execution plan. That does not mean the new plan is automatically better. Compare plans and runtime metrics across a representative workload.

### Retrieving the Actual Execution Plan

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       *
FROM sales.orders
WHERE customer_id = 1001;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PEEKED_BINDS'
    )
);
~~~

GATHER_PLAN_STATISTICS requests collecting row-source execution statistics for the cursor in the example. DISPLAY_CURSOR with ALLSTATS LAST allows comparing E-Rows (estimated) and A-Rows (actual), along with buffer/elapsed metrics if available. Appropriate privileges on fixed views are required.

### Comparing Before and After Gathering

1. Record SQL_ID, child number, and plan hash value before the change.
2. Gather statistics in a controlled manner or use pending stats.
3. Run a representative workload with appropriate bind values.
4. Retrieve the actual plan and compare E-Rows against A-Rows.
5. Measure elapsed time, buffer gets, physical reads, CPU, and concurrency.
6. Publish stats only if overall results are better or improve the targeted goal.

### NO_INVALIDATE

NO_INVALIDATE controls cursor invalidation after statistics change:

- FALSE: invalidates dependent cursors immediately per API semantics.
- TRUE: does not actively invalidate cursors due to the gather operation.
- AUTO_INVALIDATE: lets Oracle choose when to invalidate.

Do not set TRUE just to avoid parsing if the old plan is no longer suitable; old cursors could keep using plans built on stale stats. AUTO_INVALIDATE is usually a sensible default unless there are special requirements.

### Bind Peeking and Adaptive Cursor Sharing

Histograms and bind variables can affect plan selection. With skewed data, the optimizer may need to differentiate selectivity by bind value; adaptive cursor sharing can create multiple child cursors. After gathering, test multiple representative bind values rather than only one value.

### Statistics Do Not Replace SQL Tuning

If a query has non-sargable predicates, bad join order due to conditions, implicit conversions, or unsuitable indexes, gathering stats may not resolve the root cause. Inspect predicate information, access paths, join cardinalities, SQL profiles/baselines, and query structure before drawing conclusions.

## 18. Safe Operational Workflow

A production stats gather should follow a clear plan:

1. Identify the relevant SQL/objects and the objective of the change.
2. Check LAST_ANALYZED, STALE_STATS, modification counts, and current histograms.
3. Confirm whether the object has locked stats or special preferences.
4. Pick the smallest table/schema/database scope.
5. Prefer AUTO_SAMPLE_SIZE and SIZE AUTO unless measurement-backed reasons require otherwise.
6. Export stats or confirm stats history retention is sufficient to restore.
7. If plan risk is high, use pending stats and test before publishing.
8. Choose an appropriate maintenance window, degree, and no_invalidate setting.
9. Monitor the DBMS_STATS operation, CPU/I/O, locks, and cursor behavior.
10. Compare execution plans alongside runtime metrics.
11. If results degrade, import or restore saved stats, then verify cursors/plans after rollback.

### Avoid Continuous Stats Gathering

Do not run gather after every small batch if data changes are not enough to affect plans. Gathering too frequently consumes resources, invalidates caches/cursors, and causes unnecessary plan churn. Base timing on modification monitoring, partition load boundaries, and workload needs.

### Do Not Use Stats Locks to Pin a Single Plan

Locking stats preserves statistics while data keeps changing, pushing stats further from reality. If the goal is execution plan stability, evaluate SQL Plan Management/baselines and manage statistics as two separate tools.

## 19. Comprehensive Lab

Perform this in a learning schema with CREATE TABLE privileges. DDL commands issue an implicit commit in Oracle; do not run schema/database gathers on production just for experimentation.

### Step 1: Create Sample Table

~~~sql
CREATE TABLE lab_orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    order_status VARCHAR2(20) NOT NULL,
    order_amount NUMBER(12,2) NOT NULL,
    created_at DATE DEFAULT SYSDATE NOT NULL,
    CONSTRAINT ck_lab_orders_amount CHECK (order_amount >= 0)
);
~~~

### Step 2: Load Sample Data

~~~sql
BEGIN
    FOR i IN 1 .. 10000 LOOP
        INSERT INTO lab_orders (
            order_id,
            customer_id,
            order_status,
            order_amount,
            created_at
        )
        VALUES (
            i,
            MOD(i, 500),
            CASE WHEN MOD(i, 10) = 0 THEN 'OPEN' ELSE 'CLOSED' END,
            MOD(i * 17, 100000) / 100,
            SYSDATE - MOD(i, 365)
        );
    END LOOP;
    COMMIT;
END;
/
~~~

This sample data has a skewed status distribution. A scale of 10,000 rows is sufficient to observe statistics in a lab schema; do not use row-by-row loops like this to load production data.

### Step 3: Gather Table Statistics

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt => 'FOR ALL COLUMNS SIZE AUTO',
        cascade => DBMS_STATS.AUTO_CASCADE
    );
END;
/
~~~

### Step 4: View Table, Column, and Index Stats

~~~sql
SELECT table_name, num_rows, blocks, last_analyzed, stale_stats
FROM user_tab_statistics
WHERE table_name = 'LAB_ORDERS';

SELECT column_name, num_distinct, num_nulls,
       histogram, num_buckets, last_analyzed
FROM user_tab_col_statistics
WHERE table_name = 'LAB_ORDERS'
ORDER BY column_name;

SELECT index_name, blevel, leaf_blocks, distinct_keys,
       clustering_factor, last_analyzed
FROM user_ind_statistics
WHERE table_name = 'LAB_ORDERS';
~~~

Observe the primary-key index and column statistics. Histograms may or may not appear depending on Oracle's decision, usage, and data.

### Step 5: Modify Data and Check Stale Status

~~~sql
INSERT INTO lab_orders (
    order_id, customer_id, order_status, order_amount, created_at
)
SELECT order_id + 10000,
       customer_id,
       'OPEN',
       order_amount,
       SYSDATE
FROM lab_orders
WHERE order_id <= 3000;

COMMIT;

BEGIN
    DBMS_STATS.FLUSH_DATABASE_MONITORING_INFO;
END;
/

SELECT table_name, inserts, updates, deletes, timestamp
FROM user_tab_modifications
WHERE table_name = 'LAB_ORDERS';

SELECT table_name, num_rows, last_analyzed, stale_stats
FROM user_tab_statistics
WHERE table_name = 'LAB_ORDERS';
~~~

Modification monitoring and the stale flag may update via internal mechanisms, so do not immediately treat a NULL value as an error. You may need to wait/flush monitoring or check via DBA views.

### Step 6: Gather Schema in the Lab Scope

~~~sql
BEGIN
    DBMS_STATS.GATHER_SCHEMA_STATS(
        ownname => USER,
        options => 'GATHER AUTO',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt => 'FOR ALL COLUMNS SIZE AUTO'
    );
END;
/
~~~

This command can gather multiple objects in the lab schema, not just LAB_ORDERS. Before running in a shared schema, check object scope and execution time.

### Step 7: Pending Stats for LAB_ORDERS

~~~sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => USER,
        tabname => 'LAB_ORDERS',
        pname => 'PUBLISH',
        pvalue => 'FALSE'
    );

    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt => 'FOR ALL COLUMNS SIZE AUTO'
    );
END;
/
~~~

Test using pending stats in the session:

~~~sql
ALTER SESSION SET optimizer_use_pending_statistics = TRUE;

EXPLAIN PLAN FOR
SELECT *
FROM lab_orders
WHERE order_status = 'OPEN';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Compare with a session or run using published stats. Once decided, publish or delete pending stats:

~~~sql
BEGIN
    DBMS_STATS.PUBLISH_PENDING_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS'
    );

    DBMS_STATS.SET_TABLE_PREFS(
        ownname => USER,
        tabname => 'LAB_ORDERS',
        pname => 'PUBLISH',
        pvalue => 'TRUE'
    );
END;
/
~~~

If you do not want to publish:

~~~sql
BEGIN
    DBMS_STATS.DELETE_PENDING_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS'
    );
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => USER,
        tabname => 'LAB_ORDERS',
        pname => 'PUBLISH',
        pvalue => 'TRUE'
    );
END;
/
~~~

### Step 8: Export Statistics Snapshot

~~~sql
BEGIN
    DBMS_STATS.CREATE_STAT_TABLE(
        ownname => USER,
        stattab => 'LAB_STATS_BACKUP'
    );

    DBMS_STATS.EXPORT_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS',
        stattab => 'LAB_STATS_BACKUP',
        statid => 'BEFORE_TEST_CHANGE',
        cascade => TRUE
    );
END;
/
~~~

If the statistics table already exists from a previous run, do not recreate it; export under a different statid or clean up objects per procedure.

### Step 9: Test Changing Stats and Re-Importing

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS',
        estimate_percent => 100,
        method_opt => 'FOR ALL COLUMNS SIZE 1',
        cascade => TRUE
    );
END;
/
~~~

After observing, import the snapshot:

~~~sql
BEGIN
    DBMS_STATS.IMPORT_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS',
        stattab => 'LAB_STATS_BACKUP',
        statid => 'BEFORE_TEST_CHANGE',
        cascade => TRUE,
        no_invalidate => DBMS_STATS.AUTO_INVALIDATE
    );
END;
/
~~~

Importing only restores statistics; it does not delete the rows inserted in earlier steps. Do not confuse rolling back statistics with rolling back data.

### Step 10: Lock and Unlock Stats

~~~sql
BEGIN
    DBMS_STATS.LOCK_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS'
    );
END;
/

SELECT table_name, stattype_locked
FROM user_tab_statistics
WHERE table_name = 'LAB_ORDERS';

BEGIN
    DBMS_STATS.UNLOCK_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS'
    );
END;
/
~~~

### Step 11: Clean Up Lab Objects

~~~sql
DROP TABLE lab_orders PURGE;

BEGIN
    DBMS_STATS.DROP_STAT_TABLE(
        ownname => USER,
        stattab => 'LAB_STATS_BACKUP'
    );
END;
/
~~~

Run this only after completing the lab and confirming test data/statistics are no longer needed.

## 20. Common Errors and How to Handle Them

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| ORA-20000 unable to analyze table | Insufficient privileges or unsuitable object | Check owner, grants, and object status. |
| ORA-20005 object statistics are locked | Table/schema stats are locked | Verify lock reason; unlock under control or use FORCE if approved. |
| Gather runs slowly | Large table, unsuitable sample/degree, or I/O contention | Review scope, AUTO_SAMPLE_SIZE, partition strategy, and resource limits. |
| Schema gather affects workload | Schema has many objects and gather scope is too broad | Use table scope or GATHER STALE/AUTO; run in maintenance window. |
| Histogram does not appear | SIZE AUTO did not pick column or usage insufficient | Check column usage/skew; specify histogram manually only with evidence. |
| Bad plan after gather | Histogram/cardinality changed or plan invalidation | Compare actual plans; use pending stats, export/import, or restore. |
| STALE_STATS does not change immediately | Monitoring not flushed/aggregated or threshold not crossed | Check USER_TAB_MODIFICATIONS and flush monitoring if needed. |
| Pending stats are not used | Session has not enabled OPTIMIZER_USE_PENDING_STATISTICS | Check session parameter and verify pending stats exist. |
| Gather skips table | Stats are locked or object excluded by scope/options | Check STATTYPE_LOCKED, options, and operation log. |
| Import stats fails | STATTable, STATID, owner, or object mismatch | Verify export snapshot and statown/statid. |
| History restore has no data | Timestamp outside retention or no snapshot | Use exported stats table if prepared. |
| Plan changes right after gather | Cursor invalidated or AUTO_INVALIDATE chose timing | Monitor child cursors, no_invalidate, and plan hash. |
| Database gather causes high load | Database-wide scope and high parallelism | Use window, reduce degree, or gather targeted objects. |

## 21. Self-Check Questions

1. **What is DBMS_STATS used for?** Gathering and managing optimizer statistics at table, column, index, and system scopes.
2. **What does the CBO use statistics for?** Estimating cardinality/selectivity and execution plan costs.
3. **When is GATHER_TABLE_STATS used?** When statistics need updating for a specific table/partition.
4. **How does GATHER_SCHEMA_STATS differ from GATHER_DATABASE_STATS?** One API is limited to a schema; the other has broader database scope.
5. **What are GATHER_DICTIONARY_STATS and GATHER_FIXED_OBJECTS_STATS for?** Statistics on the data dictionary and fixed/dynamic performance objects.
6. **What does AUTO_SAMPLE_SIZE do?** Lets Oracle select appropriate sampling instead of hardcoding a fixed percentage.
7. **What does METHOD_OPT control?** Column statistics and histogram policies.
8. **Does SIZE AUTO mean creating histograms on all columns?** No; Oracle selects automatically based on data/usage.
9. **What does CASCADE control?** Whether to gather index statistics alongside table stats.
10. **When is GRANULARITY important?** For partitioned tables, to select global/partition/subpartition statistics.
11. **What is GATHER STALE?** Selects only objects marked stale per policy.
12. **What is GATHER EMPTY?** Selects objects that do not yet have statistics.
13. **What is GATHER AUTO?** Lets Oracle choose objects needing gathering based on status/policy.
14. **What is STALE_STATS?** An indicator that statistics are stale based on modifications and the stale threshold.
15. **When does AUTO optimizer stats collection run?** During maintenance windows under the automatic maintenance task mechanism.
16. **Does SET_TABLE_PREFS gather stats itself?** No; it sets preferences for future gathers.
17. **What is LOCK_TABLE_STATS used for?** Prevents normal gathers from altering a table's statistics.
18. **How are pending stats useful?** Testing plans with new statistics before publishing to the default workload.
19. **What does EXPORT_TABLE_STATS store?** A snapshot of optimizer statistics in a statistics table, not business data.
20. **Where does RESTORE_TABLE_STATS get its data?** Stats history still within retention.
21. **What does NO_INVALIDATE control?** Timing/policy for invalidating dependent cursors after stats change.
22. **Does gathering stats guarantee a better plan?** No; compare plans and runtime metrics.
23. **Why not gather database-wide just because one query is slow?** The scope is too broad and can cause unnecessary load and plan changes.

DBMS_STATS gives the optimizer representative information to estimate SQL cardinality and cost. Use GATHER_TABLE_STATS for specific objects, GATHER_SCHEMA_STATS for schema scope, and GATHER_DATABASE_STATS for database-wide administration. AUTO_SAMPLE_SIZE and SIZE AUTO are strong starting points; histograms, partition granularity, degree, and cascade should reflect data and workload needs. Monitor stale stats and automatic tasks, use preferences to standardize policies, pending stats for testing, export/history for rollback, and always verify actual execution plans after high-risk changes.
