# ORA-01555, ORA-30036, and Checking UNDO Demand

## 1. The Role of UNDO in Oracle Database

UNDO stores the information Oracle needs to reverse uncommitted changes, recover transactions during rollback or instance recovery, and supply prior data images for read consistency. UNDO also supports Flashback features such as Flashback Query and Flashback Table within retention limits.

When a transaction modifies a data block, Oracle writes an undo record describing the before-image value. Redo protects changes needed for recovery; undo supplies the information to roll back and reconstruct the version of data a query must see at its SCN.

Example:

~~~sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;
~~~

While the transaction remains uncommitted, Oracle retains undo so it can roll back. Another query may need the pre-UPDATE version to avoid seeing uncommitted changes. After `COMMIT`, undo may still be needed for queries that started earlier or for Flashback within the retention window.

UNDO therefore serves both active transactions and queries reading past points in time. These two demands compete for the same tablespace capacity.

## 2. Automatic Undo Management and the UNDO Tablespace

Modern Oracle Databases use Automatic Undo Management (AUM). The DBA creates one or more undo tablespaces and configures the database/instance to use the appropriate tablespace. Oracle automatically manages undo segments and extents.

Check current configuration:

~~~sql
SHOW PARAMETER undo;

SELECT name,
       value,
       isdefault,
       issys_modifiable
FROM v$parameter
WHERE name IN ('undo_management',
               'undo_tablespace',
               'undo_retention',
               'db_block_size')
ORDER BY name;
~~~

Check undo tablespaces:

~~~sql
SELECT tablespace_name,
       status,
       contents,
       retention,
       block_size
FROM dba_tablespaces
WHERE contents = 'UNDO';
~~~

Check datafiles:

~~~sql
SELECT tablespace_name,
       file_id,
       file_name,
       ROUND(bytes / 1024 / 1024, 2) AS size_mb,
       autoextensible,
       ROUND(maxbytes / 1024 / 1024, 2) AS max_size_mb,
       increment_by
FROM dba_data_files
WHERE tablespace_name = (
    SELECT value
    FROM v$parameter
    WHERE name = 'undo_tablespace'
)
ORDER BY file_id;
~~~

In RAC, each instance can use its own undo tablespace. Check parameters per instance using `GV$PARAMETER` and inspect undo metrics by `INST_ID`. Never assume a failing instance has the same undo utilization as the other instances.

In multitenant architectures, verify whether you are connected to CDB root or a PDB. Depending on shared undo vs. local undo mode and CDB configuration, a PDB may have its own undo tablespace. Check the current container, database properties, and undo parameters in the right container before making changes.

~~~sql
SHOW CON_NAME;

SELECT property_name,
       property_value
FROM database_properties
WHERE property_name = 'LOCAL_UNDO_ENABLED';
~~~

## 3. Distinguishing ORA-01555 and ORA-30036

Both errors can occur when workload demands exceed current undo capacity, yet they describe different situations.

| Error Code | Meaning | What Oracle Cannot Complete |
| --- | --- | --- |
| ORA-01555: snapshot too old | Undo needed to reconstruct data at the query's SCN has been overwritten or is unavailable | Query cannot continue consistent reads |
| ORA-30036: unable to extend segment by ... in undo tablespace | Oracle cannot allocate the next extent for an undo segment in the undo tablespace | Transaction cannot obtain more undo space to keep modifying data |

ORA-01555 typically causes read queries to fail. ORA-30036 typically causes transactions needing additional undo to fail. Space pressure can underlie both: if Oracle must reuse undo earlier than needed, long queries hit ORA-01555; if no free or extensible extents remain, transactions hit ORA-30036.

Do not handle both errors with the same reflex action. Inspect workload, extent states, retention guarantee, autoextend settings, and storage capacity before changing configuration.

## 4. ORA-01555: Snapshot Too Old

### 4.1. How It Occurs

A query needs to see data at the read-consistent SCN established when the query started. While the query runs, other transactions may update or delete blocks the query has not reached yet.

When a block has been modified after the query's SCN, Oracle uses undo to reconstruct its earlier version. If the required undo record has been reused or no longer exists, Oracle cannot build the version at that SCN and returns ORA-01555.

Example:

1. A report starts at 09:00 and needs consistent data at SCN S.
2. The report runs slowly while scanning a large table.
3. The OLTP application continuously updates/deletes those same blocks.
4. Undo holding the before-images is overwritten to serve newer transactions.
5. By 09:40, the report needs an undo record that is gone.
6. The query fails with ORA-01555.

This is a problem with how long undo survives for consistent reads, not necessarily that the entire undo tablespace is full.

### 4.2. Common Causes

- Queries run longer than the actual time undo is retained.
- High undo generation rate due to concurrent DML.
- Undo tablespace is undersized for workload and target retention.
- Datafiles cannot autoextend or have reached `MAXSIZE`.
- Large transactions or batch DML modifying massive numbers of blocks.
- PL/SQL opening a cursor and issuing `COMMIT` while continuing to `FETCH` from that cursor.
- Queries reading tables undergoing heavy concurrent modifications.
- A Flashback Query requesting data older than retained undo.

Never diagnose ORA-01555 solely from the `UNDO_RETENTION` parameter. Inspect `TUNED_UNDORETENTION`, `MAXQUERYLEN`, `SSOLDERRCNT`, and undo consumption during the exact error window.

### 4.3. Errors Caused by Committing Inside a Cursor Fetch Loop

A classic anti-pattern:

~~~sql
DECLARE
    CURSOR c_orders IS
        SELECT order_id
        FROM orders
        WHERE status = 'NEW';
BEGIN
    FOR r IN c_orders LOOP
        UPDATE orders
        SET status = 'PROCESSED'
        WHERE order_id = r.order_id;

        COMMIT;
    END LOOP;
END;
/
~~~

The cursor reads a dataset at a read-consistent SCN while the transaction repeatedly commits and generates undo pressure. Depending on cursor/fetch behavior, this leads to ORA-01555 or unpredictable behavior. Committing per row also adds high overhead and breaks transaction atomicity.

Better design:

- Use a single set-based `UPDATE` whenever possible.
- If batching is required, use an explicit batch key and close the cursor before committing each batch.
- Use keyset pagination or a staging table to chunk work.
- Commit only at designed batch boundaries, never inside the fetch loop of the same cursor.
- Persist batch progress reliably for safe resumption.

Set-based example:

~~~sql
UPDATE orders
SET status = 'PROCESSED'
WHERE status = 'NEW';

COMMIT;
~~~

If the row count is too large for a single transaction, split into independent batches based on a stable key. Each batch's filter condition must not mutate the result set of an open cursor.

### 4.4. ORA-01555 Does Not Mean the Undo Tablespace Is Full

An undo tablespace can still have free space while older undo was reused before a long query needed it. Conversely, a tablespace can appear full while short queries succeed because they do not need older overwritten undo.

Distinguish:

- **Free space:** unallocated extents or allocatable capacity.
- **Expired undo:** undo past the required retention window that can be reused.
- **Unexpired undo:** undo still within the target retention window.
- **Active undo:** undo belonging to currently active transactions; cannot be reused arbitrarily.

Counts across these extent states explain why Oracle reuses undo or fails to allocate more.

## 5. ORA-30036: Unable to Extend Segment in Undo Tablespace

### 5.1. How It Occurs

A transaction runs `INSERT`, `UPDATE`, `DELETE`, or another undo-generating operation. Oracle needs to allocate an additional extent for an undo segment but cannot obtain space from the tablespace.

Possibilities:

- The undo tablespace has no sufficient free extents left.
- Datafiles do not have `AUTOEXTEND` enabled.
- Datafiles have reached `MAXSIZE`.
- The underlying filesystem or ASM disk group is out of space.
- The tablespace is constrained by storage quotas or policy.
- Active transactions hold large amounts of undo.
- Retention Guarantee protects unexpired undo so Oracle cannot reuse it for new transactions.

The message usually looks like:

~~~text
ORA-30036: unable to extend segment by 8 in undo tablespace 'UNDOTBS1'
~~~

The block count in the message reflects the requested extent allocation. Do not infer total needed capacity from that single extent number alone.

### 5.2. Impact of RETENTION GUARANTEE

An undo tablespace has a retention attribute:

- **NOGUARANTEE:** Oracle may reuse unexpired undo when space is needed for new transactions. This prioritizes allowing DML to continue, though long queries may lose needed undo and hit ORA-01555.
- **GUARANTEE:** Oracle will not reuse unexpired undo before retention expires. This protects undo for long queries and Flashback within target retention, yet if space runs out and cannot extend, DML fails with ORA-30036.

Check:

~~~sql
SELECT tablespace_name,
       retention
FROM dba_tablespaces
WHERE contents = 'UNDO';
~~~

Change guarantee:

~~~sql
ALTER TABLESPACE undotbs1 RETENTION GUARANTEE;
~~~

Or:

~~~sql
ALTER TABLESPACE undotbs1 RETENTION NOGUARANTEE;
~~~

This setting directly trades off protecting old queries against allowing new write transactions. Never enable `GUARANTEE` to fix ORA-01555 without sizing sufficient capacity first. Likewise, never switch hastily to `NOGUARANTEE` when applications depend on Flashback Query or long-running reports.

### 5.3. UNDO_RETENTION Is Not an Absolute Guarantee in Every Configuration

`UNDO_RETENTION` is a target duration in seconds that Oracle tries to retain committed undo. That value does not automatically guarantee all undo survives for that period.

Under `NOGUARANTEE`, when space is tight, Oracle reuses unexpired undo to serve new transactions. Only Retention Guarantee forbids overwriting unexpired undo, at the risk of DML running out of space.

Oracle automatically tunes retention under Automatic Undo Management. `TUNED_UNDORETENTION` in `V$UNDOSTAT` reports the actual tuned retention based on workload and capacity. Therefore, never inspect only the `UNDO_RETENTION` parameter and assume long queries are protected.

## 6. Diagnosing in Sequence

When encountering ORA-01555 or ORA-30036, first identify the database, instance, PDB, undo tablespace, and error timestamp. Preserve alert logs, application logs, `SQL_ID`, and transaction/request IDs if available.

### 6.1. Identify the Right Undo Tablespace

~~~sql
SHOW CON_NAME;
SHOW PARAMETER undo_tablespace;
SHOW PARAMETER undo_retention;

SELECT name,
       value
FROM v$parameter
WHERE name IN ('undo_tablespace', 'undo_retention');
~~~

In RAC:

~~~sql
SELECT inst_id,
       name,
       value
FROM gv$parameter
WHERE name IN ('undo_tablespace', 'undo_retention')
ORDER BY inst_id, name;
~~~

When running in CDB/PDB, check inside the exact container hosting the workload. Never take figures from CDB root and apply them to a PDB without knowing the CDB's undo mode.

### 6.2. Check Datafile Capacity and Autoextend

~~~sql
SELECT tablespace_name,
       file_id,
       file_name,
       ROUND(bytes / 1024 / 1024, 2) AS size_mb,
       autoextensible,
       ROUND(maxbytes / 1024 / 1024, 2) AS max_size_mb,
       increment_by
FROM dba_data_files
WHERE tablespace_name = (
    SELECT value
    FROM v$parameter
    WHERE name = 'undo_tablespace'
)
ORDER BY file_id;
~~~

Check total allocated size:

To filter by tablespace type, join `DBA_DATA_FILES` with `DBA_TABLESPACES`:

~~~sql
SELECT d.tablespace_name,
       ROUND(SUM(d.bytes) / 1024 / 1024, 2) AS allocated_mb
FROM dba_data_files d
JOIN dba_tablespaces t
  ON t.tablespace_name = d.tablespace_name
WHERE t.contents = 'UNDO'
GROUP BY d.tablespace_name
ORDER BY d.tablespace_name;
~~~

Check free extents:

~~~sql
SELECT tablespace_name,
       ROUND(SUM(bytes) / 1024 / 1024, 2) AS free_mb,
       COUNT(*) AS free_extent_count,
       ROUND(MAX(bytes) / 1024 / 1024, 2) AS largest_free_extent_mb
FROM dba_free_space
WHERE tablespace_name = (
    SELECT value
    FROM v$parameter
    WHERE name = 'undo_tablespace'
)
GROUP BY tablespace_name;
~~~

For bigfile tablespaces, autoextend, and ASM, check both datafile limits and underlying storage capacity. Room left under `MAXBYTES` does not mean the disk group has space for the file to grow.

### 6.3. Check Undo Extent States

~~~sql
SELECT tablespace_name,
       status,
       COUNT(*) AS extent_count,
       ROUND(SUM(bytes) / 1024 / 1024, 2) AS size_mb
FROM dba_undo_extents
WHERE tablespace_name = (
    SELECT value
    FROM v$parameter
    WHERE name = 'undo_tablespace'
)
GROUP BY tablespace_name, status
ORDER BY status;
~~~

Meaning:

| STATUS | Meaning |
| --- | --- |
| ACTIVE | Undo currently in use by active transactions |
| UNEXPIRED | Committed undo still within the retention period |
| EXPIRED | Undo past retention and eligible for reuse |

If `ACTIVE` dominates, check long transactions or massive DML transactions. If `UNEXPIRED` dominates and the tablespace uses `RETENTION GUARANTEE`, review target retention and expansion capacity. If plenty of `EXPIRED` undo exists yet ORA-30036 still occurs, examine extent allocation, segment state, file limits, and the alert log rather than relying solely on total MB.

### 6.4. Read V$UNDOSTAT

`V$UNDOSTAT` is the primary source for analyzing undo workload over time intervals. The view stores statistics in intervals, typically 10 minutes each, over a recent history window.

~~~sql
SELECT begin_time,
       end_time,
       undoblks,
       txncount,
       maxquerylen,
       maxqueryid,
       tuned_undoretention,
       ssolderrcnt,
       nospaceerrcnt,
       unxpstealcnt,
       expstealcnt,
       activeblks,
       unexpiredblks,
       expiredblks
FROM v$undostat
ORDER BY begin_time DESC
FETCH FIRST 36 ROWS ONLY;
~~~

Key columns:

| Column | Meaning |
| --- | --- |
| `BEGIN_TIME`, `END_TIME` | Statistics collection interval |
| `UNDOBLKS` | Number of undo blocks generated during the interval |
| `TXNCOUNT` | Number of transactions during the interval |
| `MAXQUERYLEN` | Duration of the longest query in seconds |
| `MAXQUERYID` | SQL ID of the longest query if available |
| `TUNED_UNDORETENTION` | Oracle's tuned undo retention in seconds |
| `SSOLDERRCNT` | Number of snapshot too old errors in the interval |
| `NOSPACEERRCNT` | Number of out-of-undo-space errors in the interval |
| `UNXPSTEALCNT` | Times Oracle stole/reused unexpired undo extents |
| `EXPSTEALCNT` | Times expired extents were reused |
| `ACTIVEBLKS` | Number of active undo blocks |
| `UNEXPIREDBLKS` | Number of unexpired undo blocks |
| `EXPIREDBLKS` | Number of expired undo blocks |

Interpretation:

- Rising `SSOLDERRCNT` around the failure time signals ORA-01555 investigation.
- Rising `NOSPACEERRCNT` shows undo space exhaustion; correlate with ORA-30036 and storage.
- Rising `UNXPSTEALCNT` shows Oracle had to reuse unexpired undo; long queries are at risk.
- `MAXQUERYLEN` exceeding `TUNED_UNDORETENTION` is a risk signal, though not proof by itself that a specific query will definitely fail.
- Rapidly rising `UNDOBLKS` shows high undo generation rate; compare against capacity and target retention.

Never draw conclusions from a single row of `V$UNDOSTAT`. Compare multiple intervals before, during, and after the incident.

### 6.5. Calculate Undo Generation Rate

`UNDOBLKS` is the block count generated in the interval. Estimate undo blocks per second:

~~~sql
SELECT begin_time,
       end_time,
       undoblks,
       ROUND(
           undoblks /
           NULLIF((end_time - begin_time) * 86400, 0),
           2
       ) AS undo_blocks_per_sec,
       maxquerylen,
       tuned_undoretention
FROM v$undostat
ORDER BY begin_time DESC
FETCH FIRST 36 ROWS ONLY;
~~~

Multiply `undo_blocks_per_sec` by `DB_BLOCK_SIZE` to estimate bytes/second. Use peak intervals representing busy workloads rather than daily averages, because peak DML rates can be far higher.

### 6.6. Inspect Transactions Holding Undo

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.module,
       s.sql_id,
       t.start_time,
       t.used_ublk,
       t.used_urec
FROM v$transaction t
JOIN v$session s
  ON s.taddr = t.addr
ORDER BY t.used_ublk DESC;
~~~

`USED_UBLK` and `USED_UREC` show how many undo blocks/records a transaction currently holds. Transactions with very large `USED_UBLK` or long lifetimes hold active undo and shrink reusable space.

Identify `SQL_ID`, `MODULE`, username, and start time before considering intervention. Never kill a transaction simply because it is large; doing so can trigger a long rollback and heavy undo/redo recovery load.

### 6.7. Find Long-Running Queries

~~~sql
SELECT sid,
       serial#,
       username,
       module,
       sql_id,
       sql_exec_start,
       ROUND((SYSDATE - sql_exec_start) * 86400) AS elapsed_seconds
FROM v$session
WHERE status = 'ACTIVE'
  AND sql_exec_start IS NOT NULL
ORDER BY sql_exec_start;
~~~

Correlate `SQL_ID` with `MAXQUERYID` in `V$UNDOSTAT`, execution plans, SQL Monitor if licensed, and application request logs. Not every `ACTIVE` session consumes lots of undo; long `SELECT` queries generate minimal undo themselves yet need older undo for consistent reads.

### 6.8. AWR and Diagnostics Pack

`DBA_HIST_UNDOSTAT` and AWR support longer-term historical analysis than `V$UNDOSTAT`. However, using AWR/ASH and certain historical reports/features requires the Oracle Diagnostics Pack or corresponding license.

If your environment lacks that license, rely on dynamic performance views such as `V$UNDOSTAT`, `V$SESSION`, `V$TRANSACTION`, and validly collected logs. Never enable or query licensed features without confirming entitlement.

## 7. Assessing UNDO Demand and Sizing

### 7.1. Factors Determining Capacity

Required undo space depends on:

- Workload undo generation rate, especially peak DML.
- Duration of the longest query needing consistent reads.
- Target retention for Flashback Query/Flashback Table.
- Concurrent transactions and largest single transaction.
- Batch, ETL, and maintenance windows.
- `RETENTION GUARANTEE` vs. `NOGUARANTEE`.
- Autoextend capability and storage limits.
- Headroom for spikes and rollbacks.

Never size undo based solely on total database GB or table row counts. Two databases of identical size can have vastly different undo generation rates.

### 7.2. Initial Estimation Formula

A straightforward estimation method:

~~~text
Undo bytes per second
    = peak undo blocks per second × DB_BLOCK_SIZE

Undo for retention
    = undo bytes per second × target retention seconds

Initial tablespace estimate
    = undo for retention
      + headroom for concurrent active transactions
      + safety margin
~~~

Illustrative example:

- Peak undo generation: 1,500 blocks/second.
- `DB_BLOCK_SIZE`: 8,192 bytes.
- Target retention: 1,800 seconds (30 minutes).
- Active transaction/headroom: 4 GB.
- Safety margin: 25% over the pre-margin total.

Calculation:

~~~text
Undo rate = 1,500 × 8,192 = 12,288,000 bytes/second
Retention volume = 12,288,000 × 1,800
                 = 22,118,400,000 bytes
                 ≈ 20.6 GiB
Base = 20.6 + 4 = 24.6 GiB
Estimate with 25% margin ≈ 30.8 GiB
~~~

This is only an initial sizing estimate. Use representative peak intervals, measure real active transactions, evaluate concurrent workloads, and run Undo Advisor/Enterprise Manager where appropriate. Never treat this example as a default production value.

### 7.3. Choosing Target Retention

`UNDO_RETENTION` must satisfy the longest query and defined Flashback requirements. Example:

- Typical OLTP queries run in seconds.
- Reports run for 20 minutes.
- Batch reconciliation runs for 45 minutes.
- Flashback Query needs a 2-hour lookback window.

If recovery requirements demand 2 hours, setting retention to 20 minutes just because current reports take 20 minutes will fail the recovery goal. Conversely, setting a very long retention without sizing the tablespace triggers ORA-30036 under `RETENTION GUARANTEE` or undo reuse under `NOGUARANTEE`.

### 7.4. Setting UNDO_RETENTION

Example:

~~~sql
ALTER SYSTEM SET undo_retention = 1800 SCOPE = BOTH;
~~~

1800 seconds equals 30 minutes. Actual values must reflect query duration, workload, storage, and Flashback goals. In RAC, verify scope and configure each instance per policy.

Changing the parameter creates no extra disk space and does not guarantee retention if the tablespace lacks space. Monitor `TUNED_UNDORETENTION` after making changes.

### 7.5. Undo Advisor

Enterprise Manager Undo Advisor uses workload history and target retention to recommend sizing. When running it, select a window representing peak load, including batch and reporting peaks.

Undo Advisor is a decision-support tool; DBAs must still verify:

- Peak undo generation.
- Longest query duration.
- Concurrent active transactions.
- Retention Guarantee setting.
- Datafile autoextend/`MAXSIZE`.
- Storage capacity.
- Flashback objectives.

Never treat an automated recommendation as fixed sizing for all seasonal peaks.

## 8. Resolving ORA-01555

### 8.1. Confirm Timestamp and Failing SQL

Collect:

- Failure timestamp and database/PDB/instance.
- `SQL_ID`, module, action, and request ID.
- Query duration and `MAXQUERYLEN`.
- `SSOLDERRCNT` and `TUNED_UNDORETENTION`.
- `UNXPSTEALCNT` and extent states.
- Peak DML/undo generation in the same interval.

If errors occur only during end-of-day reporting, compare DML load during that window against off-peak hours.

### 8.2. Reduce Query Duration

The longer a query needs undo, the wider the consistent-read window. Options:

- Tune the execution plan and indexes.
- Narrow filter ranges.
- Select only needed columns.
- Split reports by partition/date range.
- Use summary tables or materialized views where appropriate.
- Schedule reports during lower DML periods.
- Reduce network/client fetch delays if the application fetches slowly.

A degraded execution plan can hold a snapshot far longer than normal, triggering ORA-01555 even though the SQL text did not change.

### 8.3. Expand the Undo Tablespace

If metrics show undo space is insufficient for query duration and workload, add capacity by adding a datafile or resizing datafiles in a controlled manner. Check filesystem/ASM capacity first.

Example adding a datafile:

~~~sql
ALTER TABLESPACE undotbs1
ADD DATAFILE '/u02/oradata/DB/undotbs1_02.dbf'
SIZE 8G
AUTOEXTEND ON
NEXT 512M
MAXSIZE 32G;
~~~

Path, size, and `MAXSIZE` are illustrative. With OMF/ASM, follow actual storage configuration. Never add a file if the disk group lacks capacity or the datafile would exceed approved limits.

### 8.4. Increase Retention with Backing Capacity

After confirming the tablespace is large enough, increase `UNDO_RETENTION` to cover long queries or Flashback windows. Monitor `TUNED_UNDORETENTION` and `SSOLDERRCNT` across multiple intervals.

Raising the parameter without adding capacity may fail to fix the error, especially under `NOGUARANTEE` when Oracle must reuse unexpired undo for DML.

### 8.5. Evaluate RETENTION GUARANTEE

Enable guarantee only when business requirements strictly demand guaranteed retention and capacity is sized for peak undo generation, active transactions, and headroom. Under guarantee, new transactions can fail if additional undo cannot be allocated.

### 8.6. Fix Commit Patterns

If an application commits inside a cursor fetch loop, redesign the batch boundaries. Avoid per-row commits and avoid continuing to fetch from a cursor relying on an old snapshot across repeated commits.

## 9. Resolving ORA-30036

### 9.1. Identify the Cause of Space Exhaustion

Inspect simultaneously:

1. Which UNDO tablespace the instance/PDB is using.
2. Allocated/free extents and `ACTIVE`/`UNEXPIRED`/`EXPIRED` blocks.
3. Datafile `AUTOEXTEND` and `MAXSIZE`.
4. Remaining free space on the filesystem/ASM disk group.
5. Whether `RETENTION` is `GUARANTEE` or `NOGUARANTEE`.
6. Large active transactions holding undo.
7. `NOSPACEERRCNT` and `UNDOBLKS` in `V$UNDOSTAT`.

### 9.2. Add or Resize Datafiles

If storage has capacity and sizing confirms more space is needed, a DBA can add a datafile or resize an existing file:

~~~sql
ALTER DATABASE DATAFILE
  '/u02/oradata/DB/undotbs1_01.dbf'
RESIZE 16G;
~~~

Or enable autoextend with a cap:

~~~sql
ALTER DATABASE DATAFILE
  '/u02/oradata/DB/undotbs1_01.dbf'
AUTOEXTEND ON
NEXT 512M
MAXSIZE 32G;
~~~

Resizing succeeds only if underlying storage and file limits allow it. Never set `MAXSIZE UNLIMITED` out of habit; enforce capacity guards at the storage layer.

### 9.3. Relieve Transaction Pressure

Locate large transactions via `V$TRANSACTION` and `V$SESSION`. Contact the application owner to verify the running batch, expected completion time, and whether safe cancellation is possible.

Never kill a session solely to reclaim undo without accounting for rollback. Killing a large transaction forces Oracle to roll back all changes; rollback itself consumes resources and can run for a long time.

### 9.4. Review Retention Guarantee

If the tablespace is in `GUARANTEE` mode, Oracle preserves unexpired undo strictly. When space runs short, new DML fails with ORA-30036. Switching to `NOGUARANTEE` lets Oracle reuse unexpired undo so DML continues, at the cost of long queries/Flashback potentially losing older versions.

Make this change only when the business owner accepts the trade-off and post-change monitoring is in place.

### 9.5. Check Underlying Storage

For filesystems:

- Does the volume have sufficient free space?
- Are filesystem or user quotas enforced?
- Is the filesystem mounted read-only or experiencing I/O errors?

For ASM:

- Does the disk group have usable free space?
- Is a rebalance or disk failure occurring?
- Is file growth constrained by redundancy or reserved space?

Database datafile autoextend cannot exceed underlying storage limits.

## 10. Periodic UNDO Monitoring

### 10.1. Essential Dashboard Metrics

An operational dashboard should display:

- Undo tablespace allocated MB and maximum possible MB.
- Free space/extents.
- `ACTIVE`, `UNEXPIRED`, and `EXPIRED` undo MB.
- Undo blocks per second.
- `TUNED_UNDORETENTION`.
- `MAXQUERYLEN`.
- `SSOLDERRCNT`.
- `NOSPACEERRCNT`.
- `UNXPSTEALCNT`.
- Count and runtime of large transactions.
- Datafile autoextend, `MAXSIZE`, and underlying storage free space.

### 10.2. V$UNDOSTAT Summary Query

~~~sql
SELECT begin_time,
       ROUND(undoblks * 8192 / 1024 / 1024, 2) AS undo_mb,
       maxquerylen,
       tuned_undoretention,
       ssolderrcnt,
       nospaceerrcnt,
       unxpstealcnt,
       expstealcnt
FROM v$undostat
ORDER BY begin_time DESC
FETCH FIRST 24 ROWS ONLY;
~~~

This query assumes a `DB_BLOCK_SIZE` of 8192 bytes. If the database uses another block size, pull the value from `V$PARAMETER` instead of hardcoding `8192`.

### 10.3. Query by RAC Instance

~~~sql
SELECT inst_id,
       begin_time,
       end_time,
       undoblks,
       maxquerylen,
       tuned_undoretention,
       ssolderrcnt,
       nospaceerrcnt,
       unxpstealcnt
FROM gv$undostat
ORDER BY begin_time DESC, inst_id
FETCH FIRST 72 ROWS ONLY;
~~~

RAC metrics must be read per `INST_ID`. Undo pressure on one instance is not automatically relieved by free space in another instance's undo tablespace.

### 10.4. Operational Alerts

Configure alerts when:

- `SSOLDERRCNT` increases.
- `NOSPACEERRCNT` is greater than 0.
- `TUNED_UNDORETENTION` drops below query requirements.
- `UNXPSTEALCNT` rises steadily.
- Datafiles approach `MAXSIZE`.
- Storage/ASM disk groups approach warning thresholds.
- Transactions exceed undo block or duration thresholds.

Base thresholds on workload baselines and SLAs rather than applying one uniform MB threshold to all databases.

## 11. Sample Investigation Scenarios

### Scenario A: 40-Minute Report Fails with ORA-01555

Observations:

- `MAXQUERYLEN` around 2,400 seconds.
- `TUNED_UNDORETENTION` around 1,200 seconds.
- `SSOLDERRCNT` increases in the interval.
- `UNXPSTEALCNT` rises while OLTP batch runs.
- Tablespace has low free space and `NOGUARANTEE`.

Assessment:

- The query needs a snapshot longer than actual retained undo.
- Oracle reuses unexpired undo to serve incoming DML.
- Low free space increases reuse pressure.

Action plan:

1. Tune the report to reduce runtime.
2. Measure peak undo generation during the batch window.
3. Recalculate capacity for required retention.
4. Expand the undo tablespace with appropriate autoextend caps.
5. Set `UNDO_RETENTION` to target once storage is ready.
6. Monitor `TUNED_UNDORETENTION` and `SSOLDERRCNT` afterward.

### Scenario B: Batch UPDATE Hits ORA-30036

Observations:

- `NOSPACEERRCNT` rises.
- `ACTIVE` undo dominates the tablespace.
- One transaction holds very high `USED_UBLK`.
- Datafiles reached `MAXSIZE`.
- Filesystem/ASM still has capacity.

Assessment:

- The transaction needs more undo while the file cannot grow.
- An active transaction holds large amounts of undo.

Action plan:

1. Verify the batch scope and expected completion time.
2. Increase `MAXSIZE` or add a datafile within approved capacity.
3. Monitor transaction progress and undo generation.
4. Optimize batch size and transaction boundaries for future runs.
5. Never kill the transaction before assessing rollback cost.

### Scenario C: ORA-30036 Under RETENTION GUARANTEE

Observations:

- Tablespace is in `GUARANTEE` mode.
- `UNEXPIREDBLKS` is high.
- Datafiles reached `MAXSIZE`.
- New DML fails with ORA-30036.

Assessment:

- Oracle is forbidden from reusing unexpired undo.
- No expansion room remains to allocate extents for active transactions.

Action plan:

1. Confirm whether retention guarantee is a strict business mandate.
2. Calculate space required for retention plus peak DML.
3. Expand datafiles/tablespace if storage permits.
4. If business approves relaxing guarantee, switch to `NOGUARANTEE` via change control.
5. Monitor ORA-01555 and Flashback requirements after the change.

## 12. Actions to Avoid During UNDO Errors

- Never delete undo datafiles using OS commands.
- Never drop an undo tablespace currently in use by an instance.
- Never kill a large transaction without understanding rollback impact.
- Never switch `RETENTION GUARANTEE` to `NOGUARANTEE` just to clear an immediate error without notifying the owner.
- Never set a huge `UNDO_RETENTION` without backing capacity.
- Never configure `AUTOEXTEND UNLIMITED` without storage limits and monitoring.
- Never run unrelated purges or DDL attempting to free undo.
- Never conclude ORA-01555 is solely from a small tablespace before inspecting `V$UNDOSTAT`.
- Never conclude ORA-30036 is solely from retention guarantee before inspecting datafiles and storage.
- Never commit row-by-row inside a cursor fetch loop.
- Never query `DBA_HIST_UNDOSTAT`/AWR without confirming licensing.

## 13. Hands-On Lab

Run this lab in a test schema/database. Never intentionally exhaust undo in production.

### 13.1. Create Test Table

~~~sql
CREATE TABLE undo_lab_data (
    id NUMBER PRIMARY KEY,
    payload VARCHAR2(200),
    updated_at TIMESTAMP
);

INSERT INTO undo_lab_data(id, payload, updated_at)
SELECT level,
       RPAD('A', 100, 'A'),
       SYSTIMESTAMP
FROM dual
CONNECT BY level <= 100000;

COMMIT;
~~~

### 13.2. Open a Long-Running Read Query

Session A:

~~~sql
SELECT COUNT(*)
FROM undo_lab_data a
CROSS JOIN undo_lab_data b;
~~~

In real workloads, queries can run long and need consistent reads while other sessions modify data. In the lab, choose a query and data volume sufficient to observe behavior without needing to crash a small test environment.

### 13.3. Generate Concurrent DML

Session B:

~~~sql
BEGIN
    FOR i IN 1..10000 LOOP
        UPDATE undo_lab_data
        SET payload = RPAD(TO_CHAR(i), 100, 'X'),
            updated_at = SYSTIMESTAMP
        WHERE id = i;
        COMMIT;
    END LOOP;
END;
/
~~~

Observe `V$UNDOSTAT`, `DBA_UNDO_EXTENTS`, and the querying session. Experiment with increasing datafile size/retention in the lab to see the impact on query duration and undo reuse.

### 13.4. Observe Extents

~~~sql
SELECT status,
       COUNT(*) AS extent_count,
       ROUND(SUM(bytes) / 1024 / 1024, 2) AS size_mb
FROM dba_undo_extents
GROUP BY status
ORDER BY status;
~~~

### 13.5. Observe Undo History

~~~sql
SELECT begin_time,
       end_time,
       undoblks,
       maxquerylen,
       tuned_undoretention,
       ssolderrcnt,
       nospaceerrcnt,
       unxpstealcnt
FROM v$undostat
ORDER BY begin_time DESC
FETCH FIRST 12 ROWS ONLY;
~~~

### 13.6. Test Retention Guarantee

Execute only in a lab tablespace:

~~~sql
ALTER TABLESPACE undotbs_lab RETENTION GUARANTEE;
~~~

Observe changes in extent states and allocation behavior under heavy undo workloads. Afterward, restore the recorded original policy:

~~~sql
ALTER TABLESPACE undotbs_lab RETENTION NOGUARANTEE;
~~~

Never test this on a production undo tablespace without approval and sizing.

## 14. Incident Handling Checklist

1. **Identify the exact error:** ORA-01555 or ORA-30036, timestamp, and `SQL_ID`.
2. **Identify the container/instance:** CDB/PDB and RAC `INST_ID`.
3. **Identify the undo tablespace:** `UNDO_TABLESPACE` parameter.
4. **Inspect datafiles:** size, autoextend, `MAXSIZE`, and path.
5. **Inspect storage:** filesystem/ASM free capacity.
6. **Inspect retention mode:** `GUARANTEE` vs. `NOGUARANTEE`.
7. **Read V$UNDOSTAT:** `MAXQUERYLEN`, `TUNED_UNDORETENTION`, `SSOLDERRCNT`, `NOSPACEERRCNT`.
8. **Inspect extents:** `ACTIVE`, `UNEXPIRED`, `EXPIRED`.
9. **Inspect transactions:** `USED_UBLK`, `USED_UREC`, `START_TIME`.
10. **Inspect long queries:** `SQL_ID`, execution time, execution plan.
11. **Correlate DML load:** peak undo generation and batch schedules.
12. **Recalculate sizing:** peak undo rate × retention + active transaction headroom + margin.
13. **Choose remediation:** tune query, fix commit pattern, add space, or adjust retention.
14. **Assess trade-offs:** Guarantee protects queries but risks DML running out of space.
15. **Execute controlled changes:** record before/after values and storage caps.
16. **Monitor post-change:** errors, actual retention, extents, and undo pool.
17. **Verify business outcome:** queries/batches finish cleanly and data is accurate.
18. **Archive evidence:** logs, `SQL_ID`, intervals, and metrics to update baselines.

## 15. Self-Check Questions

**Q1.** What primary purposes does UNDO serve?

**Q2.** Why can a query still need undo even after the undo-generating transaction has committed?

**Q3.** What does ORA-01555 mean?

**Q4.** What does ORA-30036 mean?

**Q5.** Why cannot these two errors be solved by one default action?

**Q6.** How do ACTIVE, UNEXPIRED, and EXPIRED undo differ?

**Q7.** Is UNDO_RETENTION an absolute guarantee?

**Q8.** How does RETENTION GUARANTEE change undo reuse behavior?

**Q9.** Why can RETENTION GUARANTEE lead to ORA-30036?

**Q10.** What key metrics does V$UNDOSTAT provide?

**Q11.** What do SSOLDERRCNT and NOSPACEERRCNT indicate?

**Q12.** What does rising UNXPSTEALCNT suggest?

**Q13.** What are MAXQUERYLEN and TUNED_UNDORETENTION used to evaluate?

**Q14.** What does USED_UBLK in V$TRANSACTION represent?

**Q15.** Why should you avoid committing every row inside a cursor fetch loop?

**Q16.** What is the initial formula for estimating required undo capacity?

**Q17.** Why might raising UNDO_RETENTION without expanding the tablespace fail to solve ORA-01555?

**Q18.** When encountering ORA-30036, why must you inspect ASM/filesystems too?

**Q19.** Why should you not kill a large transaction solely to free undo?

**Q20.** What licensing caveat applies to AWR/DBA_HIST_UNDOSTAT?

<details>
<summary>Answer hints</summary>

1. Rollback, read consistency, instance recovery, and certain Flashback features.
2. Another query may need an older SCN data image for consistent reading.
3. Undo required to build the snapshot at the query's SCN is no longer available.
4. Oracle cannot allocate the next extent for an undo segment in the undo tablespace.
5. One error is missing undo needed for consistent reads; the other is lack of space to allocate new undo.
6. ACTIVE is in use by transactions; UNEXPIRED is still within retention; EXPIRED is past retention and eligible for reuse.
7. Not in every configuration; NOGUARANTEE can reuse unexpired undo under space pressure.
8. Disallows reusing unexpired undo before retention expires.
9. If the tablespace cannot extend and unexpired undo cannot be reused, new transactions may fail to allocate extents.
10. Undo generation, longest query, tuned retention, snapshot-too-old errors, no-space errors, and extent steal counts.
11. Snapshot-too-old error counts and undo out-of-space counts, respectively.
12. Oracle had to steal/reuse unexpired undo extents, risking failures in long queries.
13. Comparing longest query runtime against actual retained undo duration.
14. Number of undo blocks currently held by the transaction.
15. Increases overhead, breaks transaction boundaries, and can trigger snapshot errors for open cursors.
16. Peak undo blocks/second × block size × retention seconds, plus active transaction headroom and safety margin.
17. Oracle can still reuse undo under space pressure when NOGUARANTEE is active.
18. Autoextend depends on underlying storage capacity; datafiles cannot grow if disk is full.
19. Rollback can take a long time and continue consuming heavy resources.
20. AWR/ASH and certain historical views/reports require the Diagnostics Pack license; confirm entitlement first.

</details>

## 16. Official Oracle Documentation

1. [Oracle Database 19c Administrator's Guide — Managing Undo](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-undo.html): Automatic Undo Management, undo retention, undo tablespace, and sizing.
2. [Oracle Database 19c Administrator's Guide — Managing Undo Data](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-undo.html): retention guarantee, undo advisor, and undo operations.
3. [Oracle Database 19c Reference — V$UNDOSTAT](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-UNDOSTAT.html): undo workload, retention, and error counters.
4. [Oracle Database 19c Reference — DBA_UNDO_EXTENTS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_UNDO_EXTENTS.html): ACTIVE, UNEXPIRED, and EXPIRED states.
5. [Oracle Database 19c Reference — V$TRANSACTION](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-TRANSACTION.html): transactions and undo usage.
6. [Oracle Database Error Messages — ORA-01555](https://docs.oracle.com/en/error-help/db/ora-01555/): snapshot too old.
7. [Oracle Database Error Messages — ORA-30036](https://docs.oracle.com/en/error-help/db/ora-30036/): unable to extend segment in undo tablespace.
8. [Oracle Database 19c SQL Language Reference — ALTER TABLESPACE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-TABLESPACE.html): modifying retention guarantee.
9. [Oracle Database 19c Reference — UNDO_RETENTION](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/UNDO_RETENTION.html): retention parameter.

**Principle to remember:** ORA-01555 means a query no longer has sufficient undo to build a consistent snapshot; ORA-30036 means a transaction cannot allocate an undo extent. Diagnose using `V$UNDOSTAT`, `DBA_UNDO_EXTENTS`, `V$TRANSACTION`, datafiles, and storage. Sizing must account for peak undo generation, query/Flashback retention, active transactions, and headroom. `RETENTION GUARANTEE` protects unexpired undo at the risk of DML running out of space; `NOGUARANTEE` prioritizes new transactions at the risk of long queries hitting snapshot too old.
