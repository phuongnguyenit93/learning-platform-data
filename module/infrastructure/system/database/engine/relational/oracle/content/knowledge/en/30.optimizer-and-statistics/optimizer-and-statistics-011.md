# Pending Statistics, Locking Statistics, and Restoring Old Statistics

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** Optimizer and Statistics  
> **Objective:** Understand the optimizer statistics lifecycle in Oracle; gather pending statistics to test before publishing; enable pending statistics in a test session; publish or delete pending statistics; lock and unlock statistics to control automatic collection; restore old statistics from history or a statistics table; and evaluate impacts on execution plans, cursor invalidation, and production operations.

## 1. Why Manage the Statistics Lifecycle?

The Oracle Optimizer uses statistics to estimate row counts, predicate selectivity, block counts, value distributions, and access path costs. From these estimates, the optimizer chooses execution plans for SQL statements.

Statistics can change after:

- Bulk data loads or deletions.
- Changes in column value distributions.
- Index creation or modification.
- Partitions being added, truncated, exchanged, or loaded.
- Automatic statistics gathering runs.
- A DBA or application invoking DBMS_STATS.

A new set of statistics generally helps the optimizer reflect current data more accurately. However, new statistics can also cause certain SQL statements to pick worse plans, especially when histograms, cardinality, bind values, or multi-column correlations affect estimates.

Oracle provides mechanisms to control statistics changes:

1. **Pending statistics:** gather new statistics without publishing them to all sessions yet.
2. **Statistics lock:** lock an object's statistics to prevent normal gathers from overwriting them.
3. **Statistics history and restore:** retain history, then restore statistics as of an earlier point in time.
4. **Statistics table export/import:** store an independent copy of statistics for backup or migration.

These mechanisms serve different purposes. Pending statistics provide a staging/testing area; locks block updates to statistics; restore reverts statistics metadata to an earlier version. None of these mechanisms rolls back table data.

## 2. Published Statistics vs. Pending Statistics

Normally, after DBMS_STATS gathers statistics, the new statistics are published and become the active set used by sessions under standard configuration.

Pending statistics decouples two steps:

- Gather: compute and store the new statistics in a pending state.
- Publish: promote those pending statistics to official statistics.

While pending statistics remain unpublished, regular sessions continue using published statistics. A test session can set OPTIMIZER_USE_PENDING_STATISTICS to test plans against the pending set.

Diagram:

~~~text
Currently published statistics
          |
          | DBMS_STATS.GATHER_TABLE_STATS
          | with PUBLISH = FALSE
          v
Pending statistics
          |
          +---- Test session enables
          |     OPTIMIZER_USE_PENDING_STATISTICS = TRUE
          |             |
          |             v
          |       Evaluate execution plans
          |
          +---- If accepted
          |       PUBLISH_PENDING_STATS
          |             |
          |             v
          |       New statistics are published
          |
          +---- If rejected
                  DELETE_PENDING_STATS
                          |
                          v
                  Published statistics remain unchanged
~~~

Pending statistics are useful when you need to validate new plans on a representative workload before affecting the entire system.

## 3. Setting the PUBLISH Preference

DBMS_STATS has a PUBLISH preference that determines whether gathered statistics are automatically published or stored as pending.

By default, PUBLISH is typically TRUE. You can change the preference at the table level:

~~~sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => 'APP',
        tabname => 'ORDERS',
        pname   => 'PUBLISH',
        pvalue  => 'FALSE'
    );
END;
/
~~~

After setting PUBLISH = FALSE, the next statistics gather on the ORDERS table creates pending statistics instead of automatically publishing them.

Check the preference:

~~~sql
SELECT DBMS_STATS.GET_PREFS(
           pname   => 'PUBLISH',
           ownname => 'APP',
           tabname => 'ORDERS'
       ) AS publish_preference
FROM dual;
~~~

Preferences can be set at different scopes via the DBMS_STATS API, though you should use the narrowest scope fitting your testing goal. Do not change the database-wide preference just to test one table.

### 3.1. A Preference Is Not a Statistics State

PUBLISH = FALSE only governs how the next gather behaves. It does not convert currently published statistics into pending statistics, nor does it delete published statistics.

To create pending statistics, you must run a gather operation after setting the preference.

### 3.2. Reverting the Preference to Default

After testing, consider restoring the original preference. If PUBLISH was previously TRUE, you can reset it:

~~~sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => 'APP',
        tabname => 'ORDERS',
        pname   => 'PUBLISH',
        pvalue  => 'TRUE'
    );
END;
/
~~~

If your environment uses centrally managed custom preferences, restore them according to DBA standards rather than making arbitrary assumptions.

## 4. Gathering Pending Statistics

Example of gathering statistics for ORDERS:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => 'APP',
        tabname          => 'ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => DBMS_STATS.AUTO_CASCADE,
        no_invalidate    => DBMS_STATS.AUTO_INVALIDATE
    );
END;
/
~~~

If the table's PUBLISH preference is FALSE, the results are stored in the pending state.

Notable parameters:

- ESTIMATE_PERCENT: sampling percentage; AUTO_SAMPLE_SIZE lets Oracle choose an appropriate method.
- METHOD_OPT: policy for collecting column statistics and histograms.
- CASCADE: whether to gather index statistics; AUTO_CASCADE lets Oracle decide.
- NO_INVALIDATE: invalidation policy for cursors dependent on statistics.
- GRANULARITY: important for partitioned tables, determining global/partition/subpartition statistics levels.
- DEGREE: parallelism degree during gather, requiring consideration of system load.

Do not apply the exact same parameter set to every table without accounting for workload, partitioning, and data distribution.

### 4.1. Viewing Pending Table Statistics

In the schema owning the table:

~~~sql
SELECT table_name,
       num_rows,
       blocks,
       avg_row_len,
       sample_size,
       last_analyzed,
       global_stats,
       user_stats
FROM user_tab_pending_stats
WHERE table_name = 'ORDERS';
~~~

Views by privilege scope include USER_TAB_PENDING_STATS, ALL_TAB_PENDING_STATS, and DBA_TAB_PENDING_STATS. Use the view matching the privileges of the inspecting account.

Pending index statistics can be viewed via USER_IND_PENDING_STATS or the corresponding ALL/DBA views.

If the view returns no rows for ORDERS, either no pending statistics exist yet, the PUBLISH preference was not set as expected, or the gather did not produce a pending set.

### 4.2. Comparing Published and Pending

You can inspect published table statistics:

~~~sql
SELECT table_name,
       num_rows,
       blocks,
       avg_row_len,
       sample_size,
       last_analyzed,
       stale_stats,
       stattype_locked
FROM user_tab_statistics
WHERE table_name = 'ORDERS';
~~~

Then query USER_TAB_PENDING_STATS to compare NUM_ROWS, BLOCKS, AVG_ROW_LEN, and SAMPLE_SIZE.

Do not compare only NUM_ROWS. Histograms, column density, index statistics, extended statistics, and partition/global statistics can also cause plans to change.

### 4.3. Pending Statistics Are Not a Backup

A pending set is only an unpublished set of statistics. It does not replace stats history or an export backup. Because pending stats can be deleted or overwritten by another gather, do not treat them as a long-term backup of old statistics.

## 5. Testing Pending Statistics in a Dedicated Session

To make the optimizer use pending statistics in a test session:

~~~sql
ALTER SESSION SET optimizer_use_pending_statistics = TRUE;
~~~

This parameter takes effect in the current session. Other sessions continue using published statistics per normal configuration.

Next, run SQL statements representative of the workload being evaluated. Example:

~~~sql
SELECT /* test_pending_orders */
       customer_id,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_amount
FROM app.orders
WHERE status = 'OPEN'
  AND order_date >= DATE '2026-01-01'
GROUP BY customer_id;
~~~

Inspect the execution plan and runtime statistics if possible:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST'
    )
);
~~~

To obtain actual row counts, collect runtime plan statistics appropriately in the test environment, such as via the GATHER_PLAN_STATISTICS hint or an approved runtime statistics configuration.

### 5.1. Comparing Old and New Plans

A practical workflow:

1. Record the SQL's plan and runtime using published statistics.
2. In the test session, enable OPTIMIZER_USE_PENDING_STATISTICS.
3. Re-run the same SQL with representative bind values and data.
4. Record estimated rows, actual rows, join order, access paths, buffer gets, and elapsed time.
5. Repeat with key bind values.
6. Compare results against plan baselines/SQL Plan Management if used by the system.

Do not look solely at cost estimates. Cost is an internal optimizer estimate, not actual runtime. Cross-check actual rows, logical I/O, CPU, elapsed time, and concurrency.

### 5.2. Disabling Pending Statistics in the Session

After testing, reset the session parameter to FALSE:

~~~sql
ALTER SESSION SET optimizer_use_pending_statistics = FALSE;
~~~

Or close the test session. Never leave a session using pending statistics outside testing, as its behavior may differ from production application sessions.

### 5.3. Pending Statistics Do Not Simulate Every Production Factor

Plans are also influenced by:

- Bind values and bind peeking/adaptive cursor sharing.
- Optimizer parameters.
- System statistics.
- SQL Plan Baselines and SQL Profiles.
- Dynamic sampling.
- Schema/object metadata.
- Statistics on joined tables and related indexes.
- Concurrency, cache, and workload.

Therefore, a test session using pending statistics is a useful control step, not a replacement for thorough workload testing and release procedures.

## 6. Publishing or Deleting Pending Statistics

Once the new statistics have been evaluated and accepted:

~~~sql
BEGIN
    DBMS_STATS.PUBLISH_PENDING_STATS(
        ownname => 'APP',
        tabname => 'ORDERS'
    );
END;
/
~~~

After publishing, the pending set becomes official statistics. Normal sessions can begin using the new statistics according to cursor invalidation and optimizer rules.

If the new plan is undesirable, delete the pending statistics:

~~~sql
BEGIN
    DBMS_STATS.DELETE_PENDING_STATS(
        ownname => 'APP',
        tabname => 'ORDERS'
    );
END;
/
~~~

Deleting pending statistics does not delete currently published statistics.

### 6.1. Publishing Is Not a Rollback

PUBLISH_PENDING_STATS updates official statistics. If the workload subsequently degrades, you can use stats history to restore an earlier version if still within retention, or import from a statistics backup table.

Do not confuse DELETE_PENDING_STATS with RESTORE_TABLE_STATS: one deletes the pending set; the other restores statistics saved in history.

### 6.2. Post-Publish Verification

After publishing:

- Verify LAST_ANALYZED and the new statistics in USER_TAB_STATISTICS.
- Confirm the pending view no longer holds unpublished rows for that object.
- Run a verification workload from a session with pending stats disabled.
- Monitor SQL plans, elapsed time, buffer gets, and errors.
- Watch for increased cursor invalidations/parses if the NO_INVALIDATE policy triggers cursor changes.

Do not publish a statistics set merely because row counts or sample sizes look reasonable. Base the decision on plans and workload performance.

## 7. Statistics Lock: Locking Statistics to Prevent Gather Overwrites

A statistics lock prevents ordinary gather operations from modifying a locked object's statistics. It is commonly used when a DBA has verified a stable set of statistics and wants to prevent automatic statistics gathering or other jobs from overwriting it.

Lock a table's statistics:

~~~sql
BEGIN
    DBMS_STATS.LOCK_TABLE_STATS(
        ownname => 'APP',
        tabname => 'ORDERS'
    );
END;
/
~~~

Unlock:

~~~sql
BEGIN
    DBMS_STATS.UNLOCK_TABLE_STATS(
        ownname => 'APP',
        tabname => 'ORDERS'
    );
END;
/
~~~

Broader-scope APIs include LOCK_SCHEMA_STATS/UNLOCK_SCHEMA_STATS and LOCK_DATABASE_STATS/UNLOCK_DATABASE_STATS. Use broad scopes only under clear operational policy; locking an entire schema or database can affect many objects and statistics jobs.

### 7.1. Checking Lock Status

Inspect table statistics:

~~~sql
SELECT table_name,
       stattype_locked,
       last_analyzed,
       stale_stats
FROM user_tab_statistics
WHERE table_name = 'ORDERS';
~~~

STATTYPE_LOCKED indicates the statistics lock status by type. Partition/subpartition views provide corresponding status fields depending on the object.

You can check index/table metadata via the corresponding USER/ALL/DBA views. If the object is partitioned, check at the table, partition, and subpartition levels; do not assume a lock at one level means every other level shares the same state.

### 7.2. Locking Statistics Does Not Lock Data

LOCK_TABLE_STATS does not block INSERT, UPDATE, or DELETE on ORDERS. It locks modifications to optimizer statistics via DBMS_STATS, not rows or tables for application DML.

Data continues changing while statistics are locked. Over time, NUM_ROWS, NDV, histograms, and clustering assumptions can become stale relative to real data.

Thus, long-term locking may stabilize plans in the short run while causing increasingly inaccurate optimizer estimates as data grows or distributions shift.

### 7.3. Automatic Statistics Gathering and Locked Objects

Automatic statistics gathering normally skips locked objects during standard runs. This is helpful to prevent an automated job from altering curated statistics.

However, if a table experiences large data loads, a stats lock can prevent statistics from reflecting current data. Someone must remain responsible for monitoring and unlocking/gathering when needed.

## 8. Gathering Statistics While an Object Is Locked

DBMS_STATS provides a FORCE parameter on applicable gather procedures to override locks. Example:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => 'APP',
        tabname => 'ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        cascade => DBMS_STATS.AUTO_CASCADE,
        force => TRUE
    );
END;
/
~~~

FORCE = TRUE allows gathering even when statistics are locked. This is an intentional bypass of the lock, not a default usage pattern.

Before using FORCE:

- Identify who/what locked the statistics.
- Confirm the current statistics actually need replacing.
- Record the old set or verify that stats history is still available.
- Assess the impact on execution plans.
- Plan for publishing, testing, and rolling back statistics if needed.

Do not add FORCE merely to silence ORA-20005 job errors without understanding why the lock was placed.

### 8.1. ORA-20005 and Locked Object Statistics

When DBMS_STATS attempts to gather a locked object, it can raise ORA-20005 indicating object statistics are locked. Check STATTYPE_LOCKED and administrative procedures before deciding to UNLOCK or use FORCE.

Do not automatically unlock an entire schema inside an error-handling script. Some locks may have been placed intentionally to protect critical workload plans.

## 9. Statistics History: How Oracle Retains Old Versions

Oracle can maintain a change history of table statistics. When you need to revert to a previous statistics set, DBMS_STATS.RESTORE_TABLE_STATS can restore from stats history provided that version is still within retention and has not been purged.

View table statistics history:

~~~sql
SELECT table_name,
       stats_update_time
FROM user_tab_stats_history
WHERE table_name = 'ORDERS'
ORDER BY stats_update_time DESC;
~~~

DBAs can use DBA_TAB_STATS_HISTORY or an appropriate view to inspect objects in other schemas.

This history is statistics history, not a copy of table data. It stores statistical metadata over time, not rows modified by UPDATE/DELETE.

### 9.1. Checking the Retention Period

You can view the history retention period:

~~~sql
SELECT DBMS_STATS.GET_STATS_HISTORY_RETENTION() AS retention_days
FROM dual;
~~~

You can check the oldest available timestamp:

~~~sql
SELECT DBMS_STATS.GET_STATS_HISTORY_AVAILABILITY() AS oldest_available_time
FROM dual;
~~~

Retention is configurable; do not assume every database retains the same number of days. Stats history uses repository storage in the database—typically associated with SYSAUX—so retention must balance restore capability against space consumption.

### 9.2. Changing Retention

Example setting retention to 45 days:

~~~sql
BEGIN
    DBMS_STATS.ALTER_STATS_HISTORY_RETENTION(45);
END;
/
~~~

Change it only with a capacity plan and operational policy. Increasing retention stores more statistics metadata; reducing retention eliminates the ability to restore older timestamps once purged.

### 9.3. Purging Old History

DBMS_STATS.PURGE_STATS can delete stats history older than a given timestamp:

~~~sql
BEGIN
    DBMS_STATS.PURGE_STATS(
        before_timestamp =>
            SYSTIMESTAMP - INTERVAL '45' DAY
    );
END;
/
~~~

Purging removes the ability to restore from deleted timestamps. Do not run purges arbitrarily before resolving a plan regression incident or without confirming alternative statistics backups exist.

## 10. Restoring Table Statistics to an Earlier Point in Time

Suppose history shows a good prior statistics set was recorded at a known timestamp. You can restore it:

~~~sql
BEGIN
    DBMS_STATS.RESTORE_TABLE_STATS(
        ownname         => 'APP',
        tabname         => 'ORDERS',
        as_of_timestamp => TO_TIMESTAMP_TZ(
            '2026-11-13 18:30:00 +00:00',
            'YYYY-MM-DD HH24:MI:SS TZH:TZM'
        ),
        force           => TRUE
    );
END;
/
~~~

Replace the example timestamp with an actual timestamp retrieved from USER_TAB_STATS_HISTORY/DBA_TAB_STATS_HISTORY and verify the time zone.

RESTORE_TABLE_STATS restores the table's statistics from history. The FORCE parameter allows restoring even when statistics are locked; use it only intentionally and with appropriate privileges.

### 10.1. Restoring Schema or Database Statistics

DBMS_STATS also provides broader-scope restore procedures such as RESTORE_SCHEMA_STATS and RESTORE_DATABASE_STATS. These can affect many objects; determine the exact scope and timestamp before calling them.

Do not run a database-wide restore just to fix a single table. Start by restoring table stats if the issue is isolated to one object and its dependencies.

### 10.2. Restoring Statistics Does Not Restore Data

Suppose ORDERS previously had 1 million rows and now has 5 million rows. Restoring stats to an earlier timestamp may make the optimizer see the old NUM_ROWS, yet the table still contains 5 million rows.

This can help if the new statistics produced a bad plan, yet it can also skew cardinality estimates relative to current data. Verify plans and actual row counts after restoring.

Do not confuse RESTORE_TABLE_STATS with FLASHBACK TABLE, Flashback Query, or point-in-time recovery. Those are separate data recovery mechanisms.

### 10.3. Cursor Invalidation Impact

After statistics change, dependent cursors may need invalidation or be handled according to the NO_INVALIDATE policy. Invalidation can increase hard parses as the workload continues.

DBMS_STATS supports the NO_INVALIDATE policy across many procedures:

- DBMS_STATS.AUTO_INVALIDATE: Oracle decides invalidation timing.
- TRUE: do not invalidate cursors for that operation.
- FALSE: immediately invalidate dependent cursors per API semantics.

Check procedure signatures and behavior for your Oracle release. Do not pass FALSE broadly in production without evaluating the risk of a parse storm.

## 11. Exporting/Importing Statistics via a Statistics Table

Stats history has a retention window and can be purged. For major changes, you can export statistics into a dedicated table to keep an independent backup.

Create a statistics table:

~~~sql
BEGIN
    DBMS_STATS.CREATE_STAT_TABLE(
        ownname => 'APP',
        stattab => 'STAT_BACKUP'
    );
END;
/
~~~

Export statistics for the ORDERS table:

~~~sql
BEGIN
    DBMS_STATS.EXPORT_TABLE_STATS(
        ownname => 'APP',
        tabname => 'ORDERS',
        stattab => 'STAT_BACKUP',
        statid  => 'BEFORE_RELEASE'
    );
END;
/
~~~

When you need to import them back:

~~~sql
BEGIN
    DBMS_STATS.IMPORT_TABLE_STATS(
        ownname => 'APP',
        tabname => 'ORDERS',
        stattab => 'STAT_BACKUP',
        statid  => 'BEFORE_RELEASE',
        cascade => TRUE,
        force   => TRUE
    );
END;
/
~~~

Verify exact parameter names and options against the DBMS_STATS package specification for your release. The statistics table must be created and accessed by an owner/user with appropriate privileges.

Export/import is useful when:

- You want a snapshot prior to a release or data migration.
- Stats history retention is too short.
- You want to transfer statistics between environments under a controlled process.
- You need to restore exported stats after major changes.

A statistics table is not a business data backup and does not replace RMAN/database backups.

## 12. Workflow for Handling Plan Regressions with Statistics

When a SQL statement slows down after gathering statistics:

1. Record the SQL_ID, child cursor, plan hash value, and when the regression began.
2. Identify which object statistics changed around that time.
3. Inspect DBA_TAB_STATS_HISTORY and DBA_OPTSTAT_OPERATIONS.
4. Compare NUM_ROWS, NDV, histograms, index stats, and global/partition stats.
5. Use pending statistics or a clone environment to test a new approach.
6. If the older set is confirmed better, restore from history or import from backup.
7. Monitor cursor invalidation and hard parses after restoring.
8. Re-run a representative workload and verify actual row counts.
9. Continue monitoring after the change to catch recurring plan regressions.

Do not restore stats simply because a plan hash value changed. A new plan may be different yet faster; compare performance and workload metrics.

### 12.1. Viewing Statistics Collection Operations

The DBA_OPTSTAT_OPERATIONS and DBA_OPTSTAT_OPERATION_TASKS views provide details on statistics operations depending on release and privileges. You can use them to find when gather jobs ran, which objects were involved, status, and duration.

Example overview query:

~~~sql
SELECT *
FROM dba_optstat_operations
ORDER BY start_time DESC;
~~~

Column names can vary by release; check the Data Dictionary Reference before writing fixed operational scripts.

## 13. Statistics on Partitioned Tables

For partitioned tables, statistics can exist at multiple levels:

- Table/global statistics.
- Partition statistics.
- Subpartition statistics.
- Index and index partition statistics.

A single partition statistics gather can also modify global stats depending on GRANULARITY, INCREMENTAL, and related preferences.

If you restore or lock only table statistics without understanding partition state, the optimizer may continue using global/partition statistics inconsistent with your goal.

### 13.1. Checking Partition Statistics

~~~sql
SELECT partition_name,
       num_rows,
       blocks,
       last_analyzed,
       stale_stats,
       stattype_locked
FROM user_tab_statistics
WHERE table_name = 'ORDERS'
  AND object_type = 'PARTITION'
ORDER BY partition_name;
~~~

Depending on view and release, partition metadata can also be queried via USER_TAB_PARTITIONS or USER_TAB_STATISTICS. Inspect both global rows and partition rows during evaluation.

### 13.2. Gathering with Appropriate GRANULARITY

Example:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname     => 'APP',
        tabname     => 'ORDERS',
        granularity => 'AUTO',
        cascade     => DBMS_STATS.AUTO_CASCADE
    );
END;
/
~~~

GRANULARITY AUTO lets Oracle pick the right collection level based on structure and preferences. Other choices include GLOBAL, PARTITION, SUBPARTITION, and combinations per API/release.

With incremental statistics, Oracle can maintain global statistics from partition synopses to reduce full-table gather overhead. Check the INCREMENTAL preference and partition structure before making changes.

### 13.3. Restoring/Locking Partition Stats

DBMS_STATS provides procedures and parameters to manage statistics at the partition level. When an issue affects only one partition, avoid restoring or gathering the entire table unnecessarily.

Check global stats after modifying partition stats, since global statistics may need to be recomputed or synchronized according to policy.

## 14. Lock, Pending, and Restore: Three Non-Interchangeable Mechanisms

| Mechanism | Purpose | Impact |
|---|---|---|
| Pending statistics | Test new statistics before publishing | Only sessions with optimizer_use_pending_statistics enabled use the pending set |
| Statistics lock | Prevent normal gathers from modifying stats | Statistics are protected; data continues changing |
| Restore statistics | Revert to older stats from history | Replaces current statistics with a saved version |
| Export/import statistics | Back up and reload stats from a statistics table | Stores/restores stats independently of history |

For example, a release might use all three:

1. Export old stats as a backup.
2. Set PUBLISH = FALSE.
3. Gather pending stats.
4. Test pending stats in an isolated session.
5. Publish if plans are good.
6. Lock stats once stabilized if policy requires.
7. If a regression occurs, unlock or restore per procedure and inspect plans.
8. After stabilizing, decide whether to re-lock or let automatic stats gathering manage them.

Do not lock statistics before gathering pending stats if the workflow uses a regular gather without FORCE; the lock can cause the gather to fail. Define the sequence of steps beforehand.

## 15. Common Errors and Notes

| Scenario | Possible Cause | Resolution |
|---|---|---|
| Pending stats not visible | PUBLISH is still TRUE or gather has not run | Check GET_PREFS and USER_TAB_PENDING_STATS |
| Test session still uses old plan | OPTIMIZER_USE_PENDING_STATISTICS not enabled | Check session parameter |
| Other sessions see new plan before publish | Another stats change occurred or wrong session/setting used | Check published stats and session parameters |
| Published pending stats but plan did not change | Different cursor, baseline, bind, optimizer setting, or predicate | Check child cursors and DBMS_XPLAN |
| DELETE_PENDING_STATS did not restore old plan | It only deletes the pending set | Restore from stats history/backup if already published |
| ORA-20005 | Object statistics are locked | Check STATTYPE_LOCKED; decide between unlock or FORCE |
| Gather ran but stats did not change | Object locked, pending preference set, or gather had no eligible data | Check preferences, pending views, and operation history |
| Restore cannot find old timestamp | History exceeded retention or was purged | Use statistics table backup if available |
| Restored stats but SQL is still slow | Other data/plan factors or cursor was not invalidated as expected | Inspect plan, actual rows, invalidation, and binds |
| Stats locked for too long | Data continues changing | Monitor stale stats and schedule unlock/gather |
| Hard parses spiked after publish/restore | Cursor invalidation | Evaluate NO_INVALIDATE and rollout |
| Partition stats do not match global stats | Gathered/restored at different levels | Check granularity, incremental settings, and partition metadata |

## 16. Lab: Testing Pending Statistics

Run only in a lab schema.

### 16.1. Create a Table with a Clear Data Distribution

~~~sql
CREATE TABLE lab_orders AS
SELECT level AS order_id,
       CASE
           WHEN MOD(level, 100) = 0 THEN 'RARE'
           ELSE 'COMMON'
       END AS status,
       MOD(level, 1000) AS customer_id,
       TRUNC(SYSDATE) - MOD(level, 365) AS order_date
FROM dual
CONNECT BY level <= 100000;

CREATE INDEX lab_orders_status_ix
ON lab_orders(status);
~~~

Gather initial statistics and publish:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS',
        cascade => TRUE
    );
END;
/
~~~

### 16.2. Modify Data and Set PUBLISH FALSE

~~~sql
UPDATE lab_orders
SET status = 'RARE'
WHERE order_id BETWEEN 1 AND 20000;

COMMIT;

BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => USER,
        tabname => 'LAB_ORDERS',
        pname => 'PUBLISH',
        pvalue => 'FALSE'
    );
END;
/
~~~

Re-gather:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS',
        cascade => TRUE
    );
END;
/
~~~

Inspect USER_TAB_STATS_HISTORY, USER_TAB_STATISTICS, and USER_TAB_PENDING_STATS to observe the published/pending states.

### 16.3. Compare Two Sessions

Session A (default):

~~~sql
ALTER SESSION SET optimizer_use_pending_statistics = FALSE;

SELECT COUNT(*)
FROM lab_orders
WHERE status = 'RARE';
~~~

Session B (test pending):

~~~sql
ALTER SESSION SET optimizer_use_pending_statistics = TRUE;

SELECT COUNT(*)
FROM lab_orders
WHERE status = 'RARE';
~~~

Inspect the plan for the same query in each session. You may need to gather runtime plan stats and view the corresponding cursor with DBMS_XPLAN.DISPLAY_CURSOR.

### 16.4. Publish or Delete Pending

If accepted:

~~~sql
BEGIN
    DBMS_STATS.PUBLISH_PENDING_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS'
    );
END;
/
~~~

If rejected:

~~~sql
BEGIN
    DBMS_STATS.DELETE_PENDING_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS'
    );
END;
/
~~~

Finally, restore the PUBLISH preference per your desired lab configuration.

## 17. Lab: Locking and Restoring Statistics

### 17.1. Lock Table Statistics

~~~sql
BEGIN
    DBMS_STATS.LOCK_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS'
    );
END;
/
~~~

Verify:

~~~sql
SELECT table_name, stattype_locked, last_analyzed
FROM user_tab_statistics
WHERE table_name = 'LAB_ORDERS';
~~~

Attempt a normal gather and observe the error when statistics are locked.

### 17.2. Unlock

~~~sql
BEGIN
    DBMS_STATS.UNLOCK_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS'
    );
END;
/
~~~

### 17.3. Inspect History and Restore

~~~sql
SELECT table_name, stats_update_time
FROM user_tab_stats_history
WHERE table_name = 'LAB_ORDERS'
ORDER BY stats_update_time DESC;
~~~

Pick an appropriate historical timestamp and call:

~~~sql
BEGIN
    DBMS_STATS.RESTORE_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS',
        as_of_timestamp => TO_TIMESTAMP_TZ(
            '2026-11-13 18:30:00 +00:00',
            'YYYY-MM-DD HH24:MI:SS TZH:TZM'
        ),
        force => TRUE
    );
END;
/
~~~

The timestamp above is only a format example. Replace it with an actual timestamp present in your lab's history.

After restoring, check USER_TAB_STATISTICS, the execution plan, and query results. Remember that the actual row count does not change because only statistics were restored.

## 18. Operational Checklist

- [ ] Record current plans and statistics before making changes.
- [ ] Check stats history retention and the oldest available timestamp.
- [ ] Export critical stats to a statistics table if an independent backup is needed.
- [ ] Use PUBLISH = FALSE at the table scope when testing.
- [ ] Gather pending statistics with appropriate method/estimate/cascade settings.
- [ ] Inspect USER_TAB_PENDING_STATS and USER_IND_PENDING_STATS.
- [ ] Enable OPTIMIZER_USE_PENDING_STATISTICS in an isolated test session.
- [ ] Test representative SQL, bind values, and actual row counts.
- [ ] Publish only after evaluating the workload.
- [ ] Delete the pending set if rejected.
- [ ] Restore the PUBLISH preference per policy.
- [ ] Check STATTYPE_LOCKED before gathering.
- [ ] Lock stats only with a valid reason and a refresh plan.
- [ ] Do not use FORCE to bypass locks without approval/backup.
- [ ] Restore from history using the exact timestamp and object scope.
- [ ] Distinguish restoring statistics from restoring data.
- [ ] Monitor cursor invalidation, hard parses, and plans after changes.
- [ ] For partitioned tables, verify global, partition, and subpartition stats.
- [ ] Document DBMS_STATS changes in runbooks/migrations.
- [ ] Test in a representative environment before operating on production.

## 19. Key Takeaways

- Optimizer statistics affect cardinality estimates and execution plans; changing statistics can make SQL faster or slower.
- Pending statistics allow gathering first, testing in an isolated session, and publishing afterward.
- Setting the PUBLISH preference to FALSE makes the next gather produce pending statistics instead of publishing immediately.
- OPTIMIZER_USE_PENDING_STATISTICS = TRUE enables using pending statistics only within the test session.
- PUBLISH_PENDING_STATS promotes the pending set; DELETE_PENDING_STATS discards the pending set and leaves currently published statistics intact.
- Statistics locks prevent normal gathers from modifying stats; they do not lock data or block DML.
- STATTYPE_LOCKED lets you check lock status; ORA-20005 typically indicates object statistics are locked.
- FORCE = TRUE can bypass locks in eligible DBMS_STATS operations; use it only intentionally.
- USER_TAB_STATS_HISTORY/DBA_TAB_STATS_HISTORY stores prior statistics snapshots according to retention.
- RESTORE_TABLE_STATS restores statistics metadata from history; it does not restore data rows.
- Statistics history retention is configurable and subject to purging; do not assume every historical timestamp remains available.
- Statistics table export/import provides a statistics copy independent of stats history.
- NO_INVALIDATE controls how cursors dependent on statistics are invalidated; assess hard parse impact.
- Partitioned tables require consistent management of global, partition, and subpartition statistics.
- Pending, lock, restore, and export/import are distinct mechanisms; choose based on your goal and establish a clear rollback plan.

### Oracle Documentation to Consult

- [Oracle Database PL/SQL Packages and Types Reference — DBMS_STATS](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_STATS.html) — SET_TABLE_PREFS, GATHER_TABLE_STATS, pending statistics, lock/unlock, restore, and statistics tables.
- [Oracle Database SQL Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/) — Optimizer statistics, cardinality estimates, execution plans, and statistics management.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/) — USER_TAB_STATISTICS, USER_TAB_PENDING_STATS, USER_TAB_STATS_HISTORY, DBA_OPTSTAT_OPERATIONS, and dictionary views.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/) — Automatic maintenance tasks, SYSAUX, and database space management.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_XPLAN](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_XPLAN.html) — Displaying execution plans and runtime plan statistics.

DBMS_STATS signatures, pending-statistics behavior, dictionary columns, and partition options can vary across Oracle releases. Consult the package specification/documentation for your exact version; test publishing, locking, restoring, and cursor behavior in a lab schema before modifying production statistics.
