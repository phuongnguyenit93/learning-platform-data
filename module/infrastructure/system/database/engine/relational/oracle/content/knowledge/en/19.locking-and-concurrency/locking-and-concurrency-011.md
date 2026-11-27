# ORA-01555 and the Relationship Between Query Duration and Undo in Oracle Database

`ORA-01555: snapshot too old` is an error that occurs when Oracle no longer has the undo information needed to reconstruct the data version as of a query's snapshot time. The error commonly appears in long-running queries while other sessions continuously modify data, though query duration is not the sole factor. The volume of undo generated, undo tablespace size, retention policy, and how applications manage transactions all affect the ability to preserve older versions.

To understand and resolve this error, you need to grasp the interplay of three factors:

- **Query duration:** the longer a query runs, the more time there is for the data versions it needs to change and for older undo to be reused.
- **Undo generation:** the heavier the INSERT/UPDATE/DELETE workload, the faster undo is generated, causing undo space to turn over more quickly.
- **Undo retention and capacity:** Oracle must retain undo long enough and have enough space for the query to reconstruct data as of its initial snapshot.

A 30-minute query does not automatically hit ORA-01555. If the data rarely changes and the required undo remains intact, the query can succeed. Conversely, a short query can still hit the error if the required undo is reused too early or there is severe undo pressure.

This lesson explains snapshots and consistent reads, how undo is used during queries, the relationship between query duration and undo retention, common root causes, monitoring via `V$UNDOSTAT`, undo tablespace sizing guidance, the effect of COMMIT inside cursor loops, and an investigation workflow for ORA-01555.

## 1. What is ORA-01555?

### 1.1. Meaning of the error

Oracle message:

```text
ORA-01555: snapshot too old: rollback segment number ... with name ...
too small
```

Specific details may vary by version and context. The core meaning is that Oracle needed an older version of a block to satisfy a consistent snapshot, but the necessary undo record was no longer available.

Example:
1. Query A starts at snapshot SCN 100.
2. Query A needs to read a row's value as of SCN 100.
3. Transaction B modifies that row and commits after SCN 100.
4. Oracle needs B's undo to reconstruct the old value for A.
5. If that undo is overwritten before A reads the block, Oracle cannot reconstruct the version at SCN 100.
6. A may receive ORA-01555.

### 1.2. This is an error about snapshot reconstruction capability

ORA-01555 does not mean:
- The table is corrupted.
- The query has invalid syntax.
- The reading transaction read uncommitted data.
- Another session is holding a row lock causing the query to wait.
- The undo tablespace is necessarily full.

The error means the undo information required for consistent read is no longer available. The root cause may be query duration, high undo generation, small undo space, retention falling short of target, or unsuitable cursor/transaction usage.

### 1.3. Why does Oracle need undo during SELECT?

A regular SELECT must return data as it existed at the statement's snapshot. While the query runs, other sessions can UPDATE or DELETE blocks that the query has not reached yet.

Oracle uses undo to reconstruct versions matching the initial snapshot. As a result, a long-running SELECT can read consistent data even while writers keep committing changes.

If the needed undo is reused before the query reads the corresponding block, snapshot reconstruction fails and ORA-01555 can occur.

## 2. Snapshots, SCN, and consistent read

### 2.1. Snapshot of a SELECT statement

Under the default READ COMMITTED isolation, each SQL statement has a logical snapshot as of when the statement begins. You can visualize it as:

```text
Time ----------------------------------------------------------->

SCN 100            SCN 110              SCN 120
  |                   |                    |
  |                   |                    +-- Transaction B COMMITs
  |                   +----------------------- Query A starts
  +------------------------------------------- Older version

Query A reads snapshot at SCN 110:
- Sees changes committed before the snapshot.
- Does not see changes committed after the snapshot.
- Uses undo to reconstruct old versions when blocks have changed.
```

SCN (*System Change Number*) is a logical sequence number Oracle uses to order changes and snapshots. SCN is not simply wall-clock time in seconds.

### 2.2. A long query retains its initial snapshot

Suppose Query A takes 20 minutes to scan a table. It starts at SCN 110. Over those 20 minutes, many other transactions update and commit data.

Query A still must see versions consistent with SCN 110. It does not switch to a newer snapshot mid-statement simply because other transactions committed.

This keeps SELECT results consistent, while also imposing the requirement to retain undo for as long as the query still needs to read older versions.

### 2.3. Undo reconstructs prior versions

Example row value:

```text
Before UPDATE and already committed:
    BALANCE = 5,000

Session B UPDATEs and has not yet COMMITted:
    BALANCE = 4,000

Session B COMMITs:
    BALANCE = 4,000

Query A has snapshot before UPDATE:
    Oracle needs version BALANCE = 5,000
    -> uses undo to reconstruct the old value
```

After COMMIT, undo is not immediately erased. It may still be needed by queries holding older snapshots and by Flashback features. However, undo space is finite, and Oracle can reuse extents per its undo management policy.

### 2.4. Queries do not need undo for every block

If a block has not changed after the query's snapshot, Oracle can read the current block without reconstructing an old version from undo. Undo is only required when a block contains changes newer than the snapshot and Oracle must roll back its logical state for reading.

Therefore, a long query reading nearly static data may never see ORA-01555. A short query over rapidly changing data may carry higher risk than expected.

## 3. Relationship between query duration and undo

### 3.1. Query duration determines how long versions must be kept

A query starts at time T0. If the query is still running at T1, it may read blocks for the first time at T1 while needing to see their state at T0.

Transactions committing between T0 and T1 generate undo needed to reconstruct the T0 version. That undo must remain available until the query finishes reading the corresponding block.

Thus, the longer a query runs, the longer old undo may need to be retained.

### 3.2. Undo generation determines space consumption rate

Undo generation is the rate at which the database creates undo from data-modifying transactions. Heavy UPDATE/DELETE/INSERT workloads generate undo much faster than mostly-read workloads.

Examples:
- Reporting system reading a rarely modified table: undo needed for snapshots can be retained easily.
- OLTP system with heavy UPDATEs across millions of rows: undo can be generated and reused very rapidly.
- A batch job updating a large table while a report scans that table: the two workloads compete directly over undo retention time.

The same 15-minute query may run fine during off-peak hours yet fail with ORA-01555 during peak DML hours.

### 3.3. Qualitative relationship

You can model the risk by comparing:

```text
How long the query needs an old snapshot
                |
                v
      Undo must remain available
                |
                v
    Compare against actual retention
                |
                v
  Undo generation and tablespace size
```

If a query needs an older version longer than Oracle can retain the necessary undo, ORA-01555 risk rises.

No single duration threshold applies to every system. Evaluate query duration, modified data, undo rate, and undo retention capacity together.

### 3.4. Query duration is not the only cause

| Scenario | Risk |
| --- | --- |
| Long query, minimal DML, sufficiently large undo tablespace | Can still succeed |
| Long query, continuous DML, small undo tablespace | Higher risk |
| Short query, a data region updated extremely rapidly | Can still fail |
| Short query, nearly static data | Usually low risk |
| Query needs snapshot older than actual retention | May fail to reconstruct version |

Do not draw conclusions from runtime alone. Correlate query details with undo statistics from the exact failure window.

## 4. UNDO_RETENTION and undo retention capability

### 4.1. What is UNDO_RETENTION?

`UNDO_RETENTION` is a parameter in seconds setting the target duration Oracle tries to retain undo under Automatic Undo Management.

Example:

```sql
ALTER SYSTEM SET undo_retention = 1800;
```

The value 1800 corresponds to 30 minutes. This configuration example requires DBA privileges; do not run it carelessly in production.

`UNDO_RETENTION` is not simply a timer guaranteeing all undo is always kept for that exact number of seconds in every case. Actual undo retention also depends on tablespace size, autoextend mode, workload, and RETENTION GUARANTEE.

### 4.2. Undo retention target vs. actual retention

Distinguish:

- **UNDO_RETENTION:** the configured target.
- **TUNED_UNDORETENTION:** the retention value Oracle dynamically adjusts based on workload and capacity, as reported in V$UNDOSTAT.
- **Actual retention of needed undo:** depends on whether the extent is still retained and has not been reused when the query needs it.

Setting a high UNDO_RETENTION does not create extra disk space by itself. If the undo tablespace is small and the workload generates undo rapidly, actual retention can fall short of expectations.

### 4.3. Without RETENTION GUARANTEE

When the undo tablespace is in NOGUARANTEE mode (the common default), Oracle prioritizes keeping DML running. Under space pressure, the system can reuse undo whose retention target has not yet expired if needed.

This keeps DML flowing, but can deprive a long query of needed undo and trigger ORA-01555.

### 4.4. With RETENTION GUARANTEE enabled

RETENTION GUARANTEE instructs Oracle never to overwrite unexpired undo solely due to space shortage. This protects undo for queries/Flashback up to the configured retention.

In exchange, if no usable undo space remains and extents cannot be allocated, new DML can fail, for example with:

```text
ORA-30036: unable to extend segment by ... in undo tablespace ...
```

Therefore, RETENTION GUARANTEE is an operational trade-off. Size the undo tablespace, monitor free space, configure autoextend, and forecast workload before enabling it.

### 4.5. Autoextend vs. fixed-size undo tablespaces

Under Automatic Undo Management:
- An undo tablespace with AUTOEXTEND can grow up to MAXSIZE to meet undo retention demands.
- A fixed-size undo tablespace must operate within allocated space; Oracle tunes retention based on the space actually available.
- Even with autoextend, MAXSIZE or filesystem/storage limits can still stop the tablespace from growing.
- Without adequate space, target retention may not be achieved unless guarantee is used.

Check file configuration:

```sql
SELECT tablespace_name,
       file_name,
       bytes,
       autoextensible,
       maxbytes
FROM   dba_data_files
WHERE  tablespace_name = (
    SELECT value
    FROM   v$parameter
    WHERE  name = 'undo_tablespace'
);
```

Requires DBA privileges or read privileges on the corresponding dictionary/dynamic performance views.

## 5. Estimating required undo capacity

### 5.1. Estimation principle

An initial estimate is commonly based on:

\[
\text{Undo space} \approx
\text{Undo generation rate}
\times
\text{Desired retention}
\]

Where:
- Undo generation rate is the amount of undo produced per second.
- Desired retention is how long undo must be kept, in seconds.
- Add headroom for active transactions, workload spikes, overhead, and other demands.

If using undo blocks per second:

\[
\text{Undo bytes} \approx
\text{Undo blocks/second}
\times
\text{DB block size}
\times
\text{Retention seconds}
\]

This is an estimation model for capacity planning, not an exact sizing formula for every database. Use real workload telemetry and appropriate sizing tools.

### 5.2. Simple calculation example

Suppose:
- Average peak-hour undo generation: 2 MB/second.
- Longest reporting query needing snapshot: 1,800 seconds (30 minutes).
- Desired headroom for workload variance: 25%.

Base estimate:

\[
2 \text{ MB/s} \times 1800 \text{ s} = 3600 \text{ MB}
\]

Adding headroom:

\[
3600 \times 1.25 = 4500 \text{ MB}
\]

The estimate is roughly 4.5 GB. The DBA must also account for active undo, peak rates, long transactions, concurrent workloads, growth, and physical storage limits.

### 5.3. Use peak hours, not just daily averages

If a system runs a batch job at 1:00 AM with light DML during the day, the 24-hour average may be far lower than undo generation during the batch window. Use peak or appropriate percentiles aligned with operational needs to avoid under-sizing.

Check:
- When reporting queries start.
- When DML batches start.
- Undo generation during each window.
- Actual query duration and day-to-day variance.
- Maximum expandable undo tablespace capacity.

### 5.4. Large capacity does not replace other measures

Enlarging the undo tablespace extends how long undo can be retained and lowers premature reuse risk, yet:
- Queries may still run unnecessarily long.
- DML may still generate undo at extreme rates.
- MAXSIZE or storage limits can still be reached.
- Long transactions still pin active undo.
- Bugs from cursor/commit patterns are not fixed solely by adding disk space.

Combine sizing with query tuning, workload scheduling, and sound transaction design.

## 6. Common causes of ORA-01555

### 6.1. Long-running queries

Queries scanning large tables, joining many tables, or sorting/aggregating huge volumes may hold a snapshot for a long time. Meanwhile, other sessions continue modifying data and generating undo.

Inspect execution plans, predicates, indexes, partition pruning, statistics, and actual data volume. Reducing query runtime generally shortens how long undo must be preserved.

### 6.2. Insufficiently sized undo tablespace

If undo capacity is small relative to the undo generated by the workload, old extents can be reused quickly. Long queries become more likely to lose needed versions.

Check:
- Allocated size.
- AUTOEXTEND and MAXSIZE.
- Free space.
- Undo generation rate.
- UNDO_RETENTION and TUNED_UNDORETENTION.
- RETENTION GUARANTEE vs. NOGUARANTEE.

### 6.3. Excessive concurrent DML

A large batch UPDATE/DELETE can generate substantial undo. If the batch runs alongside long reports, it can force older undo to be reused sooner.

Possible solutions include:
- Scheduling batches during low-reporting windows.
- Splitting workloads into reasonable batches.
- Optimizing DML statements.
- Using partition exchange or suitable data loading strategies if business rules allow.
- Increasing undo space after proper sizing.

Do not split batches mechanically if doing so breaks atomicity or alters business results.

### 6.4. Committing too frequently inside a cursor loop

A risky pattern is opening a cursor to read data and continuously updating related data and COMMITting inside the loop:

```sql
-- Illustrative anti-pattern to avoid using indiscriminately
FOR r IN (
    SELECT employee_id, salary
    FROM employees
) LOOP
    UPDATE employees
    SET salary = salary + 100
    WHERE employee_id = r.employee_id;

    COMMIT;
END LOOP;
```

The cursor may still need to read data as of its initial snapshot while repeated commits allow older undo to become reusable. In some patterns, especially when the cursor reads blocks modified by the loop's own workload, this raises ORA-01555 risk.

Not every COMMIT in a loop is guaranteed to fail. Risk depends on the cursor, data, fetching behavior, DML volume, and retention. Still, committing row-by-row increases overhead, fragments business transactions, and can cause consistency issues.

### 6.5. Long transactions and active undo

An uncommitted transaction pins active undo. Long, large transactions increase undo demand and tablespace pressure. However, active undo cannot be reused like expired undo; distinguish undo held by unfinished transactions from committed undo still needed for consistent reads.

Monitor long transactions and check whether applications keep transactions open while waiting on users or external services.

### 6.6. Sharp spikes in undo generation

A system may run smoothly for hours and then suddenly spike undo generation due to:
- Batch imports.
- Mass updates.
- Periodic purges.
- Data synchronization from external systems.
- Re-running jobs or migrations.

A snapshot started before such a spike is at risk if older undo is reused while the query is still executing.

## 7. Two-session example and query duration

### 7.1. Scenario

- Session A starts a query scanning a large table at SCN T0.
- Session B updates many rows and runs COMMIT repeatedly.
- Session A later reads blocks that B modified.
- Oracle needs undo to reconstruct the T0 version.
- If the corresponding undo still exists, A proceeds.
- If that undo has already been reused, A may receive ORA-01555.

Diagram:

```text
Time --------------------------------------------------------------->

Session A:  |---------------- Query snapshot T0 --------------------|
            starts                                     needs block later

Session B:       UPDATE + COMMIT  UPDATE + COMMIT  UPDATE + COMMIT
                       |               |                |
                       v               v                v
Undo:            generates undo  generates undo   generates undo
                       |               |                |
                       +------ pressure to reuse old undo ------+

Query A needs old undo to reconstruct version T0.
If that undo is reused before needed -> ORA-01555.
```

### 7.2. B committing does not automatically fail A

B's commit does not automatically break A's query. Oracle usually retains needed undo according to retention and available space. The error happens only when the specific undo A needs is no longer available at the moment A needs to reconstruct an older version.

### 7.3. Testing in a learning environment

You can create a large table in a test schema, run a sufficiently long SELECT in Session A, and run batch UPDATE/COMMIT in Session B. Outcomes depend on speed, undo size, row counts, and storage. A small environment may not reproduce the error even though the theoretical model is sound.

Never intentionally stress undo in production to trigger ORA-01555. Keep tests resource-bounded in an isolated database.

## 8. Monitoring undo with V$UNDOSTAT

### 8.1. Important columns

`V$UNDOSTAT` provides undo statistics over time intervals. Commonly used columns:

| Column | Meaning |
| --- | --- |
| BEGIN_TIME, END_TIME | Statistics interval |
| UNDOBLKS | Number of undo blocks used/generated during the interval |
| TXNCOUNT | Number of transactions during the interval |
| MAXQUERYLEN | Longest observed query duration, in seconds |
| TUNED_UNDORETENTION | Oracle's dynamically tuned undo retention value |
| SSOLDERRCNT | Count of snapshot too old errors during the interval |
| NOSPACEERRCNT | Count of undo space errors during the interval |
| UNXPSTEALCNT | Count of attempts/steals of unexpired undo extents per statistics |

View names and accessibility may depend on version, CDB/PDB architecture, and privileges. DBAs should consult the Data Dictionary Reference for the running release.

### 8.2. Querying recent statistics

```sql
SELECT begin_time,
       end_time,
       undoblks,
       txncount,
       maxquerylen,
       tuned_undoretention,
       ssolderrcnt,
       nospaceerrcnt,
       unxpstealcnt
FROM   v$undostat
ORDER  BY begin_time DESC;
```

Inspect rows around the time the query failed. If `SSOLDERRCNT` rose in that interval, that confirms snapshot-too-old errors occurred in that statistics window.

### 8.3. Comparing query duration and tuned retention

```sql
SELECT begin_time,
       end_time,
       maxquerylen,
       tuned_undoretention,
       ssolderrcnt,
       undoblks
FROM   v$undostat
ORDER  BY begin_time DESC;
```

If `MAXQUERYLEN` exceeds `TUNED_UNDORETENTION` in relevant intervals, that is a strong signal to investigate. Do not treat this comparison as sole proof of root cause, because the query may not have needed undo across its entire span or another specific factor may apply.

### 8.4. Estimating undo generation rate

`UNDOBLKS` gives the number of undo blocks per statistics interval. You can estimate blocks/second using the interval length:

```sql
SELECT begin_time,
       end_time,
       undoblks,
       ROUND(
           undoblks /
           NULLIF((end_time - begin_time) * 86400, 0),
           2
       ) AS undo_blocks_per_second
FROM   v$undostat
ORDER  BY begin_time DESC;
```

To convert to bytes/second, multiply by the corresponding database block size. For example:

```sql
SELECT value AS db_block_size
FROM   v$parameter
WHERE  name = 'db_block_size';
```

This is an interval-level estimate; workload may spike sharply within an interval. Inspect multiple intervals and focus on peak workloads.

### 8.5. Checking undo tablespace capacity

```sql
SELECT tablespace_name,
       file_name,
       bytes / 1024 / 1024 AS size_mb,
       autoextensible,
       maxbytes / 1024 / 1024 AS max_size_mb
FROM   dba_data_files
WHERE  tablespace_name = (
    SELECT value
    FROM   v$parameter
    WHERE  name = 'undo_tablespace'
);
```

To view undo extents by status:

```sql
SELECT tablespace_name,
       status,
       COUNT(*) AS extent_count,
       SUM(bytes) / 1024 / 1024 AS size_mb
FROM   dba_undo_extents
GROUP  BY tablespace_name, status
ORDER  BY tablespace_name, status;
```

Common statuses:
- ACTIVE: undo currently used by active transactions.
- UNEXPIRED: committed undo still within retention under current management.
- EXPIRED: undo eligible for reuse.

Do not interpret a single extent-status snapshot as the entire history. Examine trends and correlate with failure timestamps.

### 8.6. Checking undo parameters

```sql
SELECT name,
       value
FROM   v$parameter
WHERE  name IN (
    'undo_management',
    'undo_tablespace',
    'undo_retention'
);
```

If the database uses Automatic Undo Management, `UNDO_MANAGEMENT` is typically AUTO. In modern configurations, verify the exact undo tablespace of the container/PDB running the query.

### 8.7. Access privileges

Views `V$UNDOSTAT`, `V$PARAMETER`, `DBA_DATA_FILES`, and `DBA_UNDO_EXTENTS` may require DBA or dictionary-read privileges. Never grant SYSDBA to application accounts just for diagnostics. Have a DBA run the queries or grant least-privilege read access per policy.

## 9. Ordered investigation and remediation for ORA-01555

### 9.1. Identify the failing query and timestamp

Collect:
- SQL_ID or SQL text.
- Start time and error time.
- Query duration.
- Tables/partitions and data ranges read.
- Concurrent jobs or DML batches running at the time.
- Session, module, and action if recorded by the application.

Do not start by raising UNDO_RETENTION before knowing which query and workload caused the problem.

### 9.2. Correlate undo statistics

Check `V$UNDOSTAT` around the error time:
- Did `SSOLDERRCNT` increase?
- What was `MAXQUERYLEN`?
- Was `TUNED_UNDORETENTION` lower than query duration?
- Did `UNDOBLKS` spike?
- Did `UNXPSTEALCNT` increase?
- Did `NOSPACEERRCNT` record space shortages?

These indicators guide investigation rather than providing an automatic verdict. Correlate them with the query and tablespace state.

### 9.3. Reduce query runtime

This often provides long-term benefits:
- Read only necessary columns; avoid scanning extra data.
- Use selective predicates and appropriate indexes.
- Check partition pruning.
- Eliminate unnecessary joins.
- Tune sorts, groupings, and subqueries.
- Split reports into meaningful ranges if business requirements allow.
- Inspect execution plans and actual statistics.

Do not split a query if splitting breaks the single consistent snapshot required by the report. If splitting into multiple statements, re-evaluate snapshot semantics.

### 9.4. Adjust workload schedules

If large UPDATE batches overlap with long reports:
- Move batches to low-reporting windows.
- Split batches by key/range.
- Lower batch concurrency when undo generation is excessive.
- Avoid running multiple mass-update jobs simultaneously.
- Monitor impact after schedule changes.

This reduces undo contention without necessarily adding hardware resources.

### 9.5. Increase undo tablespace size

If statistics show undo space is insufficient to retain needed versions:
- Resize existing datafiles or add datafiles.
- Adjust AUTOEXTEND and MAXSIZE.
- Verify filesystem/ASM has enough free capacity.
- Recalculate capacity from undo generation and required retention.
- Monitor after changes.

For example, a DBA can resize a datafile according to environment configuration:

```sql
ALTER DATABASE DATAFILE '/path/to/undo01.dbf'
RESIZE 8G;
```

This is illustrative syntax; file paths, sizes, and resize capability depend on the environment. Never run example commands verbatim in production.

### 9.6. Tune UNDO_RETENTION

You can raise the retention target if queries require longer snapshots:

```sql
ALTER SYSTEM SET undo_retention = 3600 SCOPE=BOTH;
```

3600 is an example for one hour. Before changing it, check undo capacity and peak undo generation. If the tablespace is too small, simply raising the parameter does not guarantee undo will be retained.

### 9.7. Consider RETENTION GUARANTEE

If business requirements strictly mandate retaining undo for the full duration, consider:

```sql
ALTER TABLESPACE undotbs1 RETENTION GUARANTEE;
```

This requires DBA privileges and the exact tablespace name. With guarantee enabled, DML can fail with undo space errors if additional space cannot be allocated. Ensure a capacity plan and close monitoring are in place.

### 9.8. Do not change everything at once

Changing multiple factors simultaneously makes it hard to know which change actually solved the issue. Instead:
1. Capture a baseline.
2. Pick one change supported by evidence.
3. Monitor the same workload.
4. Compare query duration, tuned retention, undo generation, and errors.
5. Adjust further if needed.

## 10. COMMIT inside cursor loops and snapshot too old

### 10.1. Risky pattern

Illustrative example:

```sql
DECLARE
    CURSOR c_emp IS
        SELECT employee_id, salary
        FROM employees
        ORDER BY employee_id;
BEGIN
    FOR r IN c_emp LOOP
        UPDATE employees
        SET salary = salary + 100
        WHERE employee_id = r.employee_id;

        COMMIT;
    END LOOP;
END;
/
```

The cursor reads a dataset while the loop updates and commits row by row. Depending on how the cursor executes, which tables/blocks are read, and undo generation rate, repeated commits can let old undo needed by the cursor be reused before fetching completes.

This pattern can contribute to ORA-01555. It also has other drawbacks:
- Business transactions are fragmented into many commits.
- You cannot roll back the entire batch if a failure occurs mid-way.
- Commit frequency and overhead increase.
- Data is partially updated if the program halts mid-run.

### 10.2. Prefer set-based DML when possible

If the logic is simply adding the same amount to matching rows, use a single UPDATE:

```sql
UPDATE employees
SET salary = salary + 100
WHERE status = 'ACTIVE';

COMMIT;
```

A single DML statement is usually simpler than a cursor loop and avoids keeping a long cursor fetch open while continuously committing.

### 10.3. If batch processing is necessary

When business rules require chunking into batches:
- Select batches by a stable key.
- Commit only after a complete business batch finishes.
- Avoid continuing to fetch from a cursor tied to data being modified across commits inside the loop.
- Consider keyset pagination or pre-staging the list of keys to process.
- Record progress for safe recovery/retries.
- Ensure processing is idempotent if jobs can be rerun.

Batch design balances transaction size, active undo volume, lock hold time, and recoverability. No single batch size fits every application.

### 10.4. COMMIT does not immediately purge all old undo

After COMMIT, a transaction's undo is no longer active for rollback, yet it may still be needed for consistent reads and Flashback. Oracle manages undo lifecycle by status and retention; COMMIT is not an immediate undo-deletion command.

Thus, frequent commits are not a general way to reduce undo space usage. Inside a cursor loop, they can even cause older versions needed by the cursor to be reused prematurely.

## 11. Distinguishing ORA-01555 from related errors

| Error | Primary Meaning | Investigation Direction |
|---|---|---|
| ORA-01555 | Undo needed for snapshot is no longer available | Query duration, undo generation, retention, capacity |
| ORA-30036 | Unable to extend segment in undo tablespace | Capacity, autoextend, maxsize, active/unexpired undo, guarantee |
| ORA-00054 | Resource busy with NOWAIT or wait timeout | Lock-holding sessions, DDL/DML, and timeouts |
| ORA-00060 | Deadlock detected | Lock ordering, deadlock graph, transactions |
| ORA-08177 | Serialization conflict in SERIALIZABLE | Transaction conflicts and retry logic |

Do not enlarge the undo tablespace to solve a row lock wait. Do not kill a blocker to solve ORA-01555. Diagnose according to the exact error class.

## 12. Common misconceptions

**"A long-running query will definitely hit ORA-01555."**  
False. Long queries only widen the window needing an older snapshot; if the underlying data rarely changes and sufficient undo remains, the query can still succeed.

**"Just increasing UNDO_RETENTION will fix the error."**  
False. UNDO_RETENTION is a target. Without sufficient space, Oracle may still reuse unexpired undo unless retention guarantee is enabled.

**"ORA-01555 means the undo tablespace is full."**  
Not necessarily. The required undo may have been reused even though free space appears in the tablespace at inspection time.

**"COMMIT immediately erases undo."**  
False. Committed undo may still be needed for consistent reads or Flashback.

**"Expanding the undo tablespace is always the only solution."**  
No. Optimizing queries, reducing concurrent DML, adjusting batch schedules, and fixing cursor/commit patterns can also resolve the root cause.

**"Short queries cannot hit ORA-01555."**  
False. If needed undo is overwritten very quickly or specific conditions occur, short queries still carry risk.

**"RETENTION GUARANTEE is always safer."**  
No. It protects unexpired undo, but can cause DML to fail if the tablespace runs out of space.

**"MAXQUERYLEN greater than TUNED_UNDORETENTION proves the root cause."**  
No. It is an investigative signal. Verify whether the query actually needed undo across that full span and whether data changed.

**"Every snapshot too old error is caused by a cursor loop."**  
False. A cursor loop is just one risky pattern; many other causes also produce the error.

## 13. Diagnostic and capacity planning checklist

When encountering ORA-01555, collect in order:

1. **SQL and timing:** which query failed, when did it start, and how long did it run?
2. **Snapshot and data scope:** which tables/partitions were read, and was data updated while the query ran?
3. **Concurrent workload:** which batches ran, and did DML spike?
4. **V$UNDOSTAT:** SSOLDERRCNT, MAXQUERYLEN, TUNED_UNDORETENTION, UNDOBLKS, UNXPSTEALCNT, NOSPACEERRCNT.
5. **Undo configuration:** UNDO_RETENTION, undo tablespace, autoextend, MAXSIZE.
6. **Undo extents:** how are ACTIVE, UNEXPIRED, and EXPIRED extents trending?
7. **Transaction pattern:** is there a cursor fetch combined with DML/COMMIT inside a loop?
8. **Query plan:** can scans, joins, sorts, or runtime be reduced?
9. **Retention requirement:** how long must undo be retained for queries and Flashback?
10. **Capacity:** does peak undo rate multiplied by target retention fit within the tablespace and storage?
11. **Guarantee trade-off:** is RETENTION GUARANTEE needed, and is there enough space for DML?
12. **Post-change verification:** rerun a comparable workload and compare statistics.

Operational principles:
- Size for peak workloads, not just averages.
- Keep reporting queries within reasonable runtimes.
- Avoid committing row-by-row inside cursor loops unnecessarily.
- Ensure the undo tablespace has adequate size and expansion headroom.
- Do not enable RETENTION GUARANTEE without assessing DML space-exhaustion risk.
- Log errors and timestamps to correlate against batch workloads.

## 14. Practice exercises

### Exercise 1 — Interpreting ORA-01555

A report starts at 09:00 and fails at 09:45. During that window, an UPDATE batch runs from 09:10 to 09:40.

Explain why the query might need old undo and what information to collect to determine the root cause.

### Exercise 2 — Comparing query durations

Two queries both run for 20 minutes:
- Query A reads a rarely modified table.
- Query B reads a table undergoing continuous mass UPDATEs.

Explain why B's ORA-01555 risk can be higher than A's.

### Exercise 3 — Calculating an undo estimate

Peak undo generation is 1.5 MB/second; target retention is 2,400 seconds. Calculate the base undo requirement before headroom.

**Hint:** multiply undo generation rate by retention seconds; then explain why overhead and headroom must be added.

### Exercise 4 — Inspecting V$UNDOSTAT

```sql
SELECT begin_time,
       end_time,
       maxquerylen,
       tuned_undoretention,
       ssolderrcnt,
       undoblks
FROM   v$undostat
ORDER  BY begin_time DESC;
```

Identify intervals with snapshot-too-old errors and compare longest query duration against tuned retention.

### Exercise 5 — Computing undo generation rate

```sql
SELECT begin_time,
       end_time,
       undoblks,
       ROUND(
           undoblks /
           NULLIF((end_time - begin_time) * 86400, 0),
           2
       ) AS undo_blocks_per_second
FROM   v$undostat
ORDER  BY begin_time DESC;
```

Explain why multiple intervals should be observed with attention to peak workloads.

### Exercise 6 — Checking AUTOEXTEND

Use DBA_DATA_FILES to check whether undo datafiles have AUTOEXTEND enabled and what MAXBYTES is set to. Explain the impact if a file has already reached MAXSIZE.

### Exercise 7 — RETENTION GUARANTEE

Suppose a query needs 45 minutes of undo. A DBA sets UNDO_RETENTION to 45 minutes and enables RETENTION GUARANTEE, yet the undo tablespace cannot expand.

Describe the risk to DML and distinguish ORA-01555 from ORA-30036.

### Exercise 8 — Analyzing a cursor loop

Review the cursor UPDATE-then-COMMIT-per-iteration example in section 10. List three risks and propose a set-based or batched alternative.

### Exercise 9 — Optimizing a query

A full-scan SELECT takes 70 minutes. Outline steps to examine the execution plan, predicates, indexes, partition pruning, and unnecessary data before proposing larger undo.

### Exercise 10 — Distinguishing errors

Classify the following scenarios:
- A query reports ORA-01555.
- DML reports ORA-30036.
- An UPDATE waits on another session.
- Two transactions report ORA-00060.

For each scenario, name the views or information to collect.

### Exercise 11 — Evaluating a configuration

Suppose:
- Longest query: 3,000 seconds.
- TUNED_UNDORETENTION: 1,800 seconds.
- Peak undo generation: 2 MB/second.
- Current undo tablespace: 2 GB.

Explain why this configuration is at risk and calculate the base capacity needed for 3,000-second retention before headroom.

### Exercise 12 — Planning remediation

A reporting query fails during the batch window. Propose an ordered remediation plan covering collecting V$UNDOSTAT, tuning the query, adjusting batch schedules, sizing undo, setting retention, and re-verifying. Explain why not to change every setting at once.

## 15. Oracle Reference Documentation

- [Oracle Database Error Messages — ORA-01555](https://docs.oracle.com/en/database/oracle/oracle-database/19/errmg/ORA-01555.html): description of snapshot too old and related details.
- [Oracle Database Concepts — Undo Data](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/undo.html): undo records, undo segments, and consistent reads.
- [Oracle Database Administrator's Guide — Managing Undo](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-undo.html): Automatic Undo Management, UNDO_RETENTION, and retention guarantee.
- [Oracle Database Reference — V$UNDOSTAT](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-UNDOSTAT.html): undo statistics, query durations, and snapshot too old counts.
- [Oracle Database Reference — V$PARAMETER](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-PARAMETER.html): database parameter configuration.
- [Oracle Database Reference — DBA_UNDO_EXTENTS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_UNDO_EXTENTS.html): extent status inside undo tablespaces.
- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgdba/): query analysis and database performance.

When encountering ORA-01555, identify the query's snapshot, query duration, and undo generated during that same interval. Cross-check `MAXQUERYLEN`, `TUNED_UNDORETENTION`, `SSOLDERRCNT`, and undo capacity to pinpoint the cause. Then reduce query runtime or DML pressure, fix transaction patterns if needed, and adjust retention/capacity only after accounting for real workloads. **The goal is to retain enough undo for required snapshots while ensuring the system has sufficient space to keep writing data.**
