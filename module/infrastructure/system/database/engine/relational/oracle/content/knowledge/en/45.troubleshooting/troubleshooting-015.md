# Sudden Query Slowdowns Due to Statistics, Bind Variables, or Plan Changes

A SQL statement that ran stably for weeks can suddenly slow down after gathering statistics, after rapid data growth, when the application passes different bind values, or when Oracle spawns a child cursor with a different execution plan. Symptoms typically appear as rising latency, increased CPU/I/O, higher buffer gets, longer wait times, or slowdowns isolated to a subset of users.

When investigating, distinguish three related yet distinct root causes:

- **Statistics changed or no longer representative:** the optimizer misestimates cardinality and picks a different access path or join method.
- **Bind variables and data skew:** identical SQL text with bind values that vary widely in selectivity; bind peeking or adaptive cursor sharing can produce multiple child cursors/plans.
- **Execution plan change:** cursor invalidation, optimizer environment shifts, object/index changes, or a new plan with higher actual execution cost.

Do not start by creating indexes or flushing the shared pool. First identify the exact SQL, child cursor, actual executed plan, runtime metrics, and changes occurring near when the slowdown started. Only then choose a targeted recovery or tuning action.

## 1. Identifying Symptoms and Preserving Evidence

### 1.1. Capture Specific Symptoms

Record:

- Start time of the slowdown and timezone.
- Affected endpoint, batch job, or business operation.
- Whether a single SQL statement slowed down or many slowed down together.
- Whether all users are affected or only specific bind values/tenants.
- p50/p95/p99 latency, throughput, and error rate before vs. after the incident.
- `SQL_ID`, module, action, service, instance, and session if available.
- Recent changes around that time: stats gathering, code deployments, DDL, index creations/drops, partition maintenance, parameter changes, patches, or data surges.

A query that is slow for one large customer yet fast for small customers points toward selectivity/binds. If all SQL slows down simultaneously, check CPU, I/O, locks, network, connection pools, and background load before assuming plan regression.

### 1.2. Never Compare Only Total Elapsed Time

Counters in `V$SQL` accumulate per cursor. When comparing, normalize per execution and check execution counts. A cursor with high total elapsed time might simply have executed far more often.

Key metrics:

| Metric | Question |
|---|---|
| `EXECUTIONS` | How many times has the cursor run? |
| `ELAPSED_TIME` | What is the total accumulated elapsed time? |
| `CPU_TIME` | What is the total CPU time? |
| `BUFFER_GETS` | How many logical reads occurred? |
| `DISK_READS` | How many physical reads were recorded? |
| `ROWS_PROCESSED` | How many rows did the cursor process? |
| `PLAN_HASH_VALUE` | Which plan hash does the cursor use? |
| `CHILD_NUMBER` | Which child cursor number is this for the `SQL_ID`? |
| `IS_BIND_SENSITIVE` / `IS_BIND_AWARE` | Did Oracle mark the cursor as bind-sensitive/aware? |

`ELAPSED_TIME`, `CPU_TIME`, `BUFFER_GETS`, and `DISK_READS` are cumulative totals over the cursor's lifetime. Dividing by `EXECUTIONS` yields an approximate mean; measuring request percentiles requires APM or application-layer tracing.

### 1.3. Obtain SQL_ID with Proper Context

Prefer getting `SQL_ID` from APM, application traces, `V$SESSION`, licensed SQL Monitor, or correlation-ID logs. Avoid searching via `SQL_TEXT LIKE '%...%'` and picking a similar-looking SQL statement by mistake.

If a session is currently running, inspect:

```sql
SELECT sid,
       serial#,
       username,
       service_name,
       module,
       action,
       sql_id,
       sql_child_number,
       event,
       wait_class,
       seconds_in_wait
FROM v$session
WHERE username IS NOT NULL
  AND sql_id IS NOT NULL
ORDER BY seconds_in_wait DESC;
```

`V$SESSION` shows state at the moment of the query. A request may have finished before the DBA checks; collect `SQL_ID` and timing from the application while the slowdown is happening.

## 2. Identifying Active Cursors and Execution Plans

### 2.1. List Child Cursors for a SQL_ID

```sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       optimizer_env_hash_value,
       executions,
       ROUND(elapsed_time / 1e6, 3) AS elapsed_seconds,
       ROUND(elapsed_time / NULLIF(executions, 0) / 1e3, 3)
           AS avg_elapsed_ms,
       ROUND(cpu_time / NULLIF(executions, 0) / 1e3, 3)
           AS avg_cpu_ms,
       ROUND(buffer_gets / NULLIF(executions, 0), 1)
           AS buffers_per_exec,
       ROUND(disk_reads / NULLIF(executions, 0), 1)
           AS reads_per_exec,
       rows_processed,
       is_bind_sensitive,
       is_bind_aware,
       last_active_time
FROM v$sql
WHERE sql_id = :sql_id
ORDER BY child_number;
```

One `SQL_ID` can have multiple child cursors. If child cursors show different `PLAN_HASH_VALUE`s, the same SQL text is executing under multiple plans. Compare average elapsed time, buffers/exec, reads/exec, and execution counts across children.

Do not conclude the child with the highest average is automatically a bad plan if it processes dramatically different bind values or row volumes. Compare executions with comparable bind values, row counts, and workloads.

### 2.2. View SQL Text and Plan Hash

```sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       sql_fulltext
FROM v$sql
WHERE sql_id = :sql_id
ORDER BY child_number;
```

Preserve exact SQL text and `SQL_ID` when comparing. If an application concatenates literals instead of binding, every value produces a distinct SQL text and `SQL_ID`, driving up parsing and complicating comparison.

### 2.3. View the Actual Execution Plan

Once `SQL_ID` and child number are known:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        :sql_id,
        :child_number,
        'ALLSTATS LAST +PEEKED_BINDS +PREDICATE +ALIAS +OUTLINE'
    )
);
```

`DISPLAY_CURSOR` reads the cursor plan from the shared pool. `ALLSTATS LAST` shows runtime row-source statistics for the last execution that collected stats. Unless execution statistics were enabled for the cursor, `A-Rows`, `Buffers`, or operation timings may be incomplete.

To capture runtime statistics during a controlled execution, use the hint:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id, order_date, total_amount
FROM app.orders
WHERE customer_id = :customer_id
  AND status = :status;
```

Right after running it in the same session, call `DISPLAY_CURSOR` for the matching `SQL_ID`/child. The hint adds minor overhead and should be used selectively; never add it to all production SQL just for passive observation.

### 2.4. Why EXPLAIN PLAN Is Not Enough

`EXPLAIN PLAN` generates an estimated plan rather than proving which plan a cursor actually ran. Results can diverge due to:

- Bind values and bind peeking.
- Child cursors / adaptive cursor sharing.
- Session optimizer environment.
- Statistics or histograms at parse time.
- Adaptive plans and runtime decisions.
- Cursors previously loaded under a different environment.

When a query is genuinely slow, prioritize `DBMS_XPLAN.DISPLAY_CURSOR` with the exact `SQL_ID` and child number. Use `EXPLAIN PLAN` to explore expected plans, not as sole proof of an active regression.

## 3. Reading Plans to Pinpoint Regressions

### 3.1. Compare Operations and Access Paths

Common shifts:

| Old Plan | New Plan | Questions to Check |
|---|---|---|
| `INDEX RANGE SCAN` | `TABLE ACCESS FULL` | What percentage of the table does the query need? Did selectivity/statistics change? |
| `NESTED LOOPS` | `HASH JOIN` | How did outer rows and estimated cardinality change? |
| `HASH JOIN` | `NESTED LOOPS` | Are there excessive repeated lookups or expensive index accesses? |
| Fewer partitions pruned | Scanning many partitions | Do predicates still leverage the partition key properly? |
| Index access filtering early | Filtering after reading many rows | Did implicit conversion or functions disable index access? |
| Minimal sort/temp | Sort/hash spilling to TEMP | Did row count, memory grant/workarea, or concurrency change? |

A full table scan is not inherently bad. When a query returns a large fraction of a table, a full scan can be cheaper than index lookups. Evaluate actual row counts, buffers, reads, CPU, and elapsed time rather than reacting solely to operation names.

### 3.2. Compare E-Rows and A-Rows

In `DBMS_XPLAN`, `E-Rows` is the optimizer's estimated row count; `A-Rows` is the actual observed row count. Large discrepancies are major diagnostic clues.

Example:

| Operation | E-Rows | A-Rows | Interpretation |
|---|---:|---:|---|
| Filter status | 100 | 80,000 | Optimizer severely underestimated actual rows. |
| Join customers/orders | 5,000 | 4,800 | Estimate is reasonably accurate. |
| Inner index lookup | 1 | 80,000, Starts=80,000 | Repeatedly executed lookup; examine total buffers and join method. |

These numbers are illustrative. In nested loops, `Starts` shows how many times an operation executed; always read `A-Rows` alongside `Starts` to gauge total work. Cardinality errors at lower nodes often cause suboptimal join orders or join methods higher in the plan.

### 3.3. Predicate Information

Check whether predicates act as `access` predicates or only `filter` predicates. Common reasons predicates lose efficiency:

- Functions wrapping columns, e.g., `TRUNC(order_date) = :day`, when the index is on `order_date`.
- Implicit conversions caused by mismatched bind data types.
- Inconsistent string vs. numeric comparisons.
- Leading wildcards like `LIKE '%abc'` incompatible with standard B-tree indexes.
- Complex `OR` conditions or expressions lacking matching function-based indexes.
- Predicates not aligned with partition keys, preventing partition pruning.

Do not immediately create a function-based index upon seeing a function in a predicate. First verify semantics, selectivity, actual SQL, and whether rewriting the predicate lets it use existing access paths cleanly.

### 3.4. Buffers, Reads, CPU, and TEMP

- High `Buffers` indicates heavy logical block processing, often from reading too many rows, repeated lookups, or large intermediate joins.
- High `Reads` indicates physical I/O; cache warmth and storage latency strongly affect runtime.
- High CPU with low reads points to heavy row processing, expressions/functions, sorts, hashes, or parsing.
- High `TEMP` points to sort/hash spills or massive intermediate datasets.
- High elapsed time with low CPU points to waits, blocking, I/O, or network delays.

Always read runtime plans alongside wait events and application metrics. Rising latency with an unchanged plan hash can still be caused by slow storage, cold cache, locking, or increased concurrency.

## 4. Statistics and How They Influence the Optimizer

### 4.1. What Optimizer Statistics Contain

The Oracle optimizer uses statistics to estimate cost and cardinality. Key components:

- Table statistics: row counts, block counts, table size.
- Column statistics: distinct value counts, `NULL` counts, density, and histograms.
- Index statistics: leaf blocks, clustering factor, blevel, and distinct keys.
- Partition/global statistics: per-partition and table-wide stats.
- System statistics: CPU/I/O characteristics used in cost calculations.

Statistics are not business data; they are statistical summaries helping the optimizer pick plans. When data shifts, stale stats skew cardinality; when stats are freshly gathered, plans can flip even though SQL text never changed.

### 4.2. Check When Statistics Were Gathered

```sql
SELECT owner,
       table_name,
       num_rows,
       blocks,
       sample_size,
       last_analyzed,
       stale_stats,
       stattype_locked
FROM dba_tab_statistics
WHERE owner = 'APP'
  AND table_name = 'ORDERS';
```

For partitioned tables, this view returns rows at table, partition, and subpartition levels. Inspect both global and partition stats. `NUM_ROWS` is a statistical value, not guaranteed to equal the exact live row count.

Inspect key columns:

```sql
SELECT column_name,
       num_distinct,
       num_nulls,
       density,
       histogram,
       num_buckets,
       last_analyzed
FROM dba_tab_col_statistics
WHERE owner = 'APP'
  AND table_name = 'ORDERS'
ORDER BY column_name;
```

Inspect indexes:

```sql
SELECT index_name,
       status,
       visibility,
       blevel,
       leaf_blocks,
       distinct_keys,
       clustering_factor,
       last_analyzed
FROM dba_indexes
WHERE owner = 'APP'
  AND table_name = 'ORDERS'
ORDER BY index_name;
```

Without `DBA_` privileges, query `ALL_TAB_STATISTICS`, `ALL_TAB_COL_STATISTICS`, and `ALL_INDEXES` within your visible scope.

### 4.3. Stale or Unrepresentative Statistics

Statistics go stale after substantial data modifications. Yet stale stats do not guarantee a bad plan, and non-stale stats can still be unrepresentative if value distributions shifted abruptly.

Check for:

- Sharp row count jumps/drops after bulk loads or purges.
- A few new values dominating the distribution.
- Data shifting from uniform to skewed.
- New partitions containing very different data than older ones.
- Rebuilt indexes or structural table changes.
- Statistics gathered with a different sample/estimate size than before.
- Histograms created, dropped, or altered in bucket counts.

Never gather stats across an entire schema simply because one query slowed down. Scope to involved objects, compare timestamps, and compare plans before and after.

### 4.4. Histograms and Data Skew

Histograms tell the optimizer how column values are distributed. Without a histogram, the optimizer assumes a roughly uniform distribution based on NDV/density. If one status accounts for 99% of rows and another 0.1%, a uniform assumption fails badly.

Histogram types and generation depend on Oracle version, bucket count, `METHOD_OPT`, and workload. `SIZE AUTO` lets Oracle decide on histograms based on column usage and stats policies; not every column should have a histogram.

Check histograms:

```sql
SELECT column_name,
       histogram,
       num_distinct,
       density,
       num_buckets,
       last_analyzed
FROM dba_tab_col_statistics
WHERE owner = 'APP'
  AND table_name = 'ORDERS'
  AND column_name IN ('STATUS', 'CUSTOMER_ID');
```

Inspect endpoints if needed:

```sql
SELECT endpoint_number,
       endpoint_value,
       endpoint_actual_value
FROM dba_tab_histograms
WHERE owner = 'APP'
  AND table_name = 'ORDERS'
  AND column_name = 'STATUS'
ORDER BY endpoint_number;
```

`ENDPOINT_ACTUAL_VALUE` and certain columns depend on data type and release. Frequency, top-frequency, and hybrid histograms interpret endpoints differently; do not read endpoints as a simple flat list without knowing the histogram type.

### 4.5. Extended Statistics for Correlated Columns

When two columns correlate strongly—such as `COUNTRY_CODE` and `POSTAL_REGION`—the optimizer misestimates combined selectivity under independence assumptions. Extended statistics model column groups:

```sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
           ownname   => 'APP',
           tabname   => 'CUSTOMERS',
           extension => '(COUNTRY_CODE, POSTAL_REGION)'
       ) AS extension_name
FROM dual;
```

Then gather statistics accordingly and verify cardinality estimates. Extended statistics are not a blanket fix for every query; create them only when evidence shows correlated columns and significant estimate errors.

### 4.6. Locked Statistics and Pending Statistics

Statistics can be locked at the table or schema level. If stats are not updating as expected, check `STATTYPE_LOCKED` and preferences. Never unlock stats just to force a gather before understanding why they were locked.

Pending statistics let you gather and test stats before publishing them. Example:

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
        cascade          => TRUE
    );
END;
/
```

In a test session, enable pending statistics:

```sql
ALTER SESSION SET optimizer_use_pending_statistics = TRUE;
```

After verifying plans and performance, publish them:

```sql
EXEC DBMS_STATS.PUBLISH_PENDING_STATS('APP', 'ORDERS');
```

Or delete pending stats if unused:

```sql
EXEC DBMS_STATS.DELETE_PENDING_STATS('APP', 'ORDERS');
```

Pending statistics allow session-scoped validation prior to system-wide publication. Verify syntax and privileges for your release. Afterward, restore session settings and table preferences per policy so test flags are not left active unintentionally.

## 5. Bind Variables, Bind Peeking, and Adaptive Cursor Sharing

### 5.1. Why Does the Same SQL Behave Differently with Different Bind Values?

Consider:

```sql
SELECT order_id, order_date, total_amount
FROM app.orders
WHERE status = :status;
```

In production data, `CLOSED` might represent 95% of rows while `ESCALATED` represents 0.2%. Querying `CLOSED` favors a full scan, whereas `ESCALATED` favors an index range scan.

Using identical SQL text with binds lets Oracle share cursors—usually a major benefit—yet under severe data skew, a single plan cannot be optimal for every bind value.

### 5.2. Bind Peeking

During hard parse, Oracle peeks at the initial bind value to estimate selectivity and select a plan. That initial plan fits the peeked value but may be terrible for later bind values with different selectivity.

Example:

1. First request binds `ESCALATED`; optimizer picks an index range scan.
2. The cursor is shared.
3. Subsequent requests bind `CLOSED`, forcing the index plan to read huge row volumes.
4. Latency for `CLOSED` spikes even though SQL text never changed.

Exact behavior depends on histograms, version, and optimizer features. Bind peeking is not inherently bad; it helps the optimizer pick plans informed by real values at parse time.

### 5.3. Adaptive Cursor Sharing

Oracle provides Adaptive Cursor Sharing (ACS) to detect bind-sensitive SQL and, when appropriate, generate separate child cursors/plans for different bind value ranges. A SQL statement transitions from bind-sensitive to bind-aware after Oracle observes sufficient execution feedback.

Check:

```sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       is_bind_sensitive,
       is_bind_aware,
       executions,
       last_active_time
FROM v$sql
WHERE sql_id = :sql_id
ORDER BY child_number;
```

When multiple child cursors have different plans, compare bind distributions and per-child performance. Multiple child cursors are not automatically an error; they may be necessary to handle skew. However, runaway child cursor growth increases memory/parse overhead or signals environment/bind metadata mismatches.

### 5.4. Inspecting Captured Binds and Peeked Binds

`V$SQL_BIND_CAPTURE` provides bind metadata and recently captured values:

```sql
SELECT sql_id,
       child_number,
       name,
       position,
       datatype_string,
       value_string,
       last_captured
FROM v$sql_bind_capture
WHERE sql_id = :sql_id
ORDER BY child_number, position;
```

Bind capture is sampled; it does not record every execution and may not hold the latest value. Some data types are not captured completely. `PEEKED_BINDS` in `DBMS_XPLAN.DISPLAY_CURSOR` reflects the value peeked at hard parse, not necessarily the bind from the most recent slow execution.

Bind values may contain emails, account IDs, tokens, or personal data. Access and share them only within authorized bounds; redact sensitive values in reports.

### 5.5. Verifying Bind Data Types

Applications must bind types matching the target column. If a column is `NUMBER` while JDBC binds a string, Oracle performs implicit conversion. If conversion applies to the column side, index access breaks or data errors occur.

Java example:

```java
String sql = "SELECT order_id FROM app.orders WHERE customer_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, customerId); // CUSTOMER_ID is an integer NUMBER matching the column.
    try (ResultSet rs = ps.executeQuery()) {
        // Read results.
    }
}
```

Do not bind `customerId` with `setString()` merely because input arrived as JSON. Parse and validate in the application layer, then bind the matching SQL type. Align data types, precision, and lengths for `DATE`, `TIMESTAMP`, `VARCHAR2`, and `NUMBER`.

### 5.6. Checking Unshared Child Cursors

`V$SQL_SHARED_CURSOR` exposes reason flags explaining why a child cursor could not be shared. Example:

```sql
SELECT child_number,
       bind_mismatch,
       bind_equiv_failure,
       optimizer_mismatch,
       stats_row_mismatch,
       user_bind_peek_mismatch,
       language_mismatch
FROM v$sql_shared_cursor
WHERE sql_id = :sql_id
ORDER BY child_number;
```

Available columns and column names vary by release. If a column does not exist, inspect the view definition on your release rather than guessing. Flags indicate sharing-failure reasons; read them alongside `V$SQL`, optimizer environment, and bind metadata.

Causes include bind datatype/length mismatches, differing optimizer environments, object/statistics mismatches, authorization differences, and other cursor-sharing conditions. Never purge child cursors merely to reduce counts without fixing the underlying mismatch.

## 6. Checking Plan and Statistics Change History

### 6.1. Correlate Slowdown Time with Stats Updates

```sql
SELECT owner,
       table_name,
       stats_update_time
FROM dba_tab_stats_history
WHERE owner = 'APP'
  AND table_name = 'ORDERS'
ORDER BY stats_update_time DESC;
```

`DBA_TAB_STATS_HISTORY` retains statistics history per retention policy. A stats update matching when the slowdown began is a lead, not sole proof. Compare actual plans, histograms, cardinalities, and live data.

Check oldest available history:

```sql
SELECT DBMS_STATS.GET_STATS_HISTORY_AVAILABILITY AS oldest_available_time
FROM dual;
```

Adjust owner/table as needed. History may be unavailable past retention or after purges.

### 6.2. Compare via AWR If Licensed

In environments with proper Oracle Diagnostics Pack licensing and privileges, AWR helps inspect SQL statistics and plan history across snapshots. Example SQL stats aggregation by snapshot:

```sql
SELECT ss.snap_id,
       sn.begin_interval_time,
       ss.plan_hash_value,
       ss.executions_delta,
       ROUND(ss.elapsed_time_delta / 1e6, 2) AS elapsed_seconds,
       ROUND(ss.cpu_time_delta / 1e6, 2) AS cpu_seconds,
       ss.buffer_gets_delta,
       ss.disk_reads_delta
FROM dba_hist_sqlstat ss
JOIN dba_hist_snapshot sn
  ON sn.snap_id = ss.snap_id
 AND sn.dbid = ss.dbid
 AND sn.instance_number = ss.instance_number
WHERE ss.sql_id = :sql_id
ORDER BY ss.snap_id;
```

Deltas enable period-over-period comparisons. `DBA_HIST_SQLSTAT`, AWR reports, and related historical views fall under the Diagnostics Pack per Oracle licensing; use them only when properly licensed. Without that license, rely on cursor cache, permitted SQL traces, APM, and unlicensed views.

### 6.3. SQL Plan History

Plan history can be queried via `DBA_HIST_SQL_PLAN` when authorized and licensed. Do not rely on a single plan hash if adaptive plans or multiple child cursors exist. Compare operations, predicates, outlines, optimizer environments, and runtime stats.

### 6.4. Check Object and Optimizer Environment Changes

Check timestamps for:

- Indexes created, dropped, marked unusable, or made invisible.
- Partitions exchanged, split, truncated, or moved.
- Column data types or constraints modified.
- Statistics gathered, restored, locked, or published.
- Optimizer parameters or session settings changed.
- Application changes to JDBC driver, bind types, SQL text, or session initialization.
- Database patches/upgrades or `OPTIMIZER_FEATURES_ENABLE` changes.

In `V$SQL`, `OPTIMIZER_ENV_HASH_VALUE` identifies cursors parsed under different optimizer environments. Compare session parameters and module/service settings when the same SQL runs across multiple connection pools.

## 7. Restoring Statistics When Gathering Causes Regressions

### 7.1. Check History First

Oracle retains historical statistics and supports restoring to an earlier timestamp. Before restoring:

1. Identify the exact table, partition, and indexes involved.
2. Record current `LAST_ANALYZED`, histograms, NDV, `num_rows`, and plans.
3. Locate the timestamp prior to the suspected regression-inducing change.
4. Confirm stats history availability and pick the exact timestamp.
5. Test in a non-production environment or with pending statistics if possible.
6. Assess impact on all other SQL using the same object.

Restoring table stats affects every query touching that table. Do not roll back statistics just because one query slowed down if the newer stats accurately reflect real data and the query itself needs fixing elsewhere.

### 7.2. Restore Table Statistics

Example restoring a table's statistics to a prior timestamp:

```sql
BEGIN
    DBMS_STATS.RESTORE_TABLE_STATS(
        ownname         => 'APP',
        tabname         => 'ORDERS',
        as_of_timestamp => TO_TIMESTAMP_TZ(
            '2026-11-14 09:00:00 +07:00',
            'YYYY-MM-DD HH24:MI:SS TZH:TZM'
        ),
        force           => TRUE,
        no_invalidate   => FALSE
    );
END;
/
```

The timestamp is illustrative; supply an actual timestamp within history retention and the right timezone. `NO_INVALIDATE => FALSE` invalidates dependent cursors per API behavior so cursors reparse against the restored stats. Cursor invalidation increases parse load; choose timing and scope carefully.

Verify parameter names, privileges, and partition/global restore behavior for your Oracle version. `FORCE => TRUE` overrides locked stats if necessary; never set it arbitrarily to bypass lock policies. Restoring statistics does not revert table data, indexes, or DDL—it restores only optimizer statistics metadata.

### 7.3. Post-Restore Verification

- Confirm `LAST_ANALYZED` and statistics reverted to the target timestamp.
- Inspect the new cursor plan after invalidation/reparse.
- Test across multiple representative bind values.
- Measure elapsed time, CPU, buffers, reads, and application latency.
- Watch other SQL accessing the same table for secondary regressions.
- Document the decision and a plan to resume stats gathering after fixing the root cause.

Never run `ALTER SYSTEM FLUSH SHARED_POOL` as a default step. Flushing the entire shared pool triggers mass hard parses across the whole database. Prefer scoped invalidation or DBA-approved operations.

## 8. SQL Plan Management and Plan Control

### 8.1. What Is a SQL Plan Baseline?

SQL Plan Management (SPM) records and enforces accepted execution plans for SQL statements. When the optimizer generates a new plan, baselines ensure verified plans are used rather than switching automatically to an unvalidated plan.

SPM is helpful when:

- A prior plan is proven good.
- Regression followed a stats refresh or environment shift.
- You need controlled rollout and verification of new plans before accepting them.
- You want to prevent unexpected plan flips in critical workloads.

Baselines do not guarantee a SQL statement stays fast forever. An older plan can become suboptimal as data grows or distributions shift; baselines must be monitored and evolved alongside workloads.

### 8.2. Loading a Good Plan from the Cursor Cache

If a known-good cursor/plan is still in the shared pool, load it into the SQL Management Base using `DBMS_SPM`:

```sql
DECLARE
    l_loaded_plans PLS_INTEGER;
BEGIN
    l_loaded_plans := DBMS_SPM.LOAD_PLANS_FROM_CURSOR_CACHE(
        sql_id          => '4abc123def456',
        plan_hash_value => 1234567890
    );
    DBMS_OUTPUT.PUT_LINE('Plans loaded: ' || l_loaded_plans);
END;
/
```

Substitute the real `SQL_ID` and plan hash. Confirm the loaded plan was measured and fits the bind distribution you want to protect. Loading a baseline does not mean every execution uses it instantly; inspect `DBA_SQL_PLAN_BASELINES`, enabled/accepted/fixed flags, and actual executed plans afterward.

### 8.3. Inspecting SQL Plan Baselines

```sql
SELECT sql_handle,
       plan_name,
       enabled,
       accepted,
       fixed,
       reproduced,
       created,
       last_executed
FROM dba_sql_plan_baselines
WHERE sql_text LIKE '%FROM app.orders%'
ORDER BY created DESC;
```

The `sql_text` filter is an example and may match multiple statements. In operations, target the exact `sql_handle` or verified SQL text and protect sensitive SQL contents. `REPRODUCED` and related columns depend on Oracle version; check your release's data dictionary.

### 8.4. Accepting or Evolving New Plans

A new plan may genuinely outperform the old one on newer data. Never pin an old plan permanently without review. Use proper testing/evolving workflows to compare performance, bind values, and workloads before accepting new plans. Monitor after evolving so you can revert to the known baseline if regressions appear.

### 8.5. SQL Profiles, SQL Patches, and Hints

SQL Profiles supply auxiliary cardinality/cost information to the optimizer; SQL Patches apply SQL-level hints in specific scenarios. These are advanced DBA tools requiring clear understanding of root cause and version behavior. SQL Tuning Advisor, SQL Tuning Sets, and related tuning features require Oracle Tuning Pack/Diagnostics Pack licenses; verify entitlement before use.

Never create a SQL Profile/Patch just to force a plan hash without validating bind distributions and side effects on other executions. If the issue stems from wrong bind types or broken predicates, fixing the application/SQL is far more sustainable than adding hints.

## 9. Step-by-Step Troubleshooting Procedure

### Step 1: Confirm Scope

Identify the affected query, users, service, module, start time, p95/p99, and blast radius. Determine whether the entire database slowed down or only one SQL/bind group.

### Step 2: Capture SQL_ID and Child Cursors

Record SQL text, `SQL_ID`, child number, plan hash, optimizer environment hash, executions, elapsed/CPU, buffers, reads, and bind-sensitive/aware flags. Save evidence before cursors age out.

### Step 3: Inspect the Runtime Plan

Run `DBMS_XPLAN.DISPLAY_CURSOR` on the slow child cursor. Capture runtime stats if possible; read `E-Rows`/`A-Rows`, `Starts`, buffers, reads, predicates, partition pruning, sort/hash/TEMP, and outline.

### Step 4: Compare Good and Slow Plans

Compare prior and current plan hashes, operations, join order, access paths, and cardinalities. If the plan hash did not change, look elsewhere: cache warmth, I/O, locks, CPU, concurrency, or data volume.

### Step 5: Check Statistics

Inspect `LAST_ANALYZED`, stale stats, histograms, NDV, index stats, and partition stats. Review stats history and gather timestamps. Check stats locks, pending stats, and automatic stats jobs.

### Step 6: Check Binds and Child Cursors

Compare bind datatypes/lengths, peeked binds, captured binds, and `IS_BIND_SENSITIVE`/`IS_BIND_AWARE`. Query `V$SQL_SHARED_CURSOR` to see why child cursors are not shared. Test with both common and rare bind values.

### Step 7: Check Environment Changes

Check DDL, index states, partition maintenance, optimizer parameters, session NLS, JDBC/ORM versions, deployments, and patches. Compare `OPTIMIZER_ENV_HASH_VALUE` and session settings.

### Step 8: Apply a Scoped Fix

Depending on the verified cause:

- Fix bind data types or SQL predicates.
- Gather or adjust targeted statistics.
- Validate with pending stats before publishing.
- Restore statistics selectively if clear evidence and stats history support it.
- Use SQL Plan Baselines to temporarily protect a verified plan.
- Adjust indexes, partitions, or SQL after measuring and testing in an equivalent environment.

### Step 9: Re-Measure and Monitor

Test with representative workloads, bind distributions, and cache states. Compare p50/p95/p99, throughput, error rates, CPU, buffers, reads, TEMP, and DML impact. Monitor through at least one full representative load cycle.

## 10. Other Causes Often Mistaken for Plan Regressions

### 10.1. Blocking and Lock Contention

A query may wait on another transaction even with an unchanged plan. Check `V$SESSION`, `BLOCKING_SESSION`, wait events, and long transactions. If elapsed time jumps while CPU time stays low, waits are likely the culprit.

### 10.2. Cold Cache or Storage Latency

After restarts, failovers, or workload shifts, the buffer cache may be cold. Physical reads climb and queries slow down despite an identical plan hash. Compare reads, I/O latency, and cache state; measure cold and warm runs separately.

### 10.3. Data Growth and Clustering Factor

Table growth or altered insertion order can degrade an index's clustering factor. A previously efficient plan becomes expensive when forced to visit widely scattered blocks.

### 10.4. Unusable/Invisible Indexes or Partition Issues

Indexes can become unusable or invisible, or partitioned indexes invalidated during maintenance. Check `DBA_INDEXES`, `DBA_IND_PARTITIONS`, `DBA_IND_SUBPARTITIONS`, and partition pruning.

### 10.5. Connection Pools and Networking

API latency can rise due to pool exhaustion, slow connection creation, network round trips, or oversized fetches. Measure connection borrow time, execution time, fetch time, and application processing separately.

### 10.6. Parse Storms and Varying SQL Text

When applications concatenate literals, every request generates distinct SQL text, driving hard parses and shared pool pressure. Use properly typed bind variables and inspect `VERSION_COUNT`, child cursors, parse calls, and near-duplicate SQL texts.

## 11. Reflex Actions to Avoid

- Never gather statistics across an entire schema just because one query slowed down.
- Never flush the shared pool or buffer cache in production to "reset plans."
- Never create indexes before inspecting actual plans, cardinalities, and DML overhead.
- Never force `FULL` or `INDEX` hints without testing across representative bind values.
- Never restore old statistics without assessing impact on all other SQL using the table.
- Never purge child cursors or kill sessions merely to clear symptoms.
- Never assume multiple child cursors are always a bug; ACS intentionally creates distinct plans for bind groups.
- Never assume `PEEKED_BINDS` shows the bind value from the latest slow execution.
- Never use AWR/ASH/SQL Tuning Advisor without confirming proper organizational licensing.
- Never paste sensitive bind values into tickets, logs, or broadly shared reports.

## 12. Sample Runbook for a Query Regression

### Initial Capture

1. Record timestamp, service, module/action, endpoint, and user impact.
2. Capture `SQL_ID`, child number, plan hash, and bind group.
3. Save SQL text and `DBMS_XPLAN.DISPLAY_CURSOR` output.
4. Record executions, elapsed/exec, CPU/exec, buffers/exec, reads/exec, and rows processed.
5. Verify whether the query is waiting on locks, I/O, or network.

### Check Recent Changes

1. Inspect `LAST_ANALYZED`, stale stats, histograms, and stats history for involved tables/indexes.
2. Inspect child cursors, bind mismatches, and optimizer environment.
3. Check DDL, index status, partition maintenance, and application deployments.
4. If appropriately licensed for AWR/ASH, compare SQL plans/performance across before and after snapshots.

### Remediate and Validate

1. Choose the smallest change matching the proven root cause.
2. Test in a non-production environment or with pending stats where suitable.
3. If needed, perform scoped stats restore or protect the good plan with SPM.
4. Re-measure across representative bind distributions and concurrency.
5. Monitor the SQL, related workloads, and other queries touching the same objects.
6. Archive before/after plans, metrics, decisions, and completion timestamp.

## 13. Root Cause Report Template

An investigation report should record:

| Field | Content |
|---|---|
| Incident | Start time, service, module, impact level. |
| SQL | `SQL_ID`, sanitized SQL text, child number, bind type/group. |
| Plan before | Plan hash, operations, E-Rows/A-Rows, buffers, reads, elapsed. |
| Plan after | Plan hash, operations, E-Rows/A-Rows, buffers, reads, elapsed. |
| Statistics | Table/column/index stats, histograms, last analyzed, history timestamp. |
| Bind | Bind-sensitive/aware flags, peeked binds, child cursor reasons, data types. |
| Environment | Optimizer env hash, parameter/session settings, version/patch. |
| Root cause | Specific evidence and correlation with regression start time. |
| Remediation | Changes applied, scope, and rollback method. |
| Validation | Workload, bind distribution, p95/p99, CPU, buffers, reads, error rate. |
| Follow-up | Monitoring, owner, observation period, and closure criteria. |

Never include passwords, tokens, customer data, or sensitive bind values in reports. Use masked identifiers and store documents with proper access controls.

## 14. Principles to Remember

- Identify the exact `SQL_ID`, child cursor, and actual executed plan before changing the database.
- Compare per-execution metrics; cursor counters are cumulative.
- Use `DBMS_XPLAN.DISPLAY_CURSOR` to inspect cursor plans rather than relying solely on `EXPLAIN PLAN`.
- Compare `E-Rows` against `A-Rows` alongside `Starts`, buffers, reads, predicates, and TEMP.
- Inspect statistics, histograms, skew, partition/global stats, and gather timestamps.
- Bind peeking can tie an initial plan to the bind value seen at hard parse.
- Adaptive Cursor Sharing can generate multiple child cursors/plans for distinct bind groups.
- Bind the right data types and check for implicit conversions.
- Use stats history and pending stats for targeted testing or restoration when backed by evidence.
- SQL Plan Baselines protect verified plans yet still require monitoring as workloads evolve.
- An unchanged plan hash does not rule out cache, I/O, lock, CPU, or concurrency issues.
- Never flush the shared pool, gather schema-wide stats, or force hints reflexively.
- Verify licensing before using AWR/ASH, SQL Monitor, or SQL Tuning Advisor.
- Re-benchmark with representative data, bind distributions, concurrency, and cache warm-up.

## Conclusion

Sudden query slowdowns must be investigated using evidence from actual cursors and workloads. Statistics changes can shift optimizer cardinality estimates and trigger new plans; bind peeking combined with data skew can require multiple child cursors/plans for a single SQL statement; and object or optimizer environment changes can invalidate cursors or prevent sharing. DBAs should start with `SQL_ID`, child number, plan hash, and runtime statistics, then cross-check `E-Rows`/`A-Rows`, binds, histograms, stats history, and recent changes near the incident window. Once the root cause is clear, validate with pending stats, restore statistics selectively, or protect a verified plan with SQL Plan Management. Finally, consider the incident resolved only after re-testing across representative bind distributions and loads, confirming p95/p99 latency alongside database resources, and monitoring other queries sharing the modified objects.
