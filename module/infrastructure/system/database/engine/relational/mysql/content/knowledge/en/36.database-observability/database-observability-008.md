# System Observability

## Reading SHOW ENGINE INNODB STATUS and the Latest Deadlock State

`SHOW ENGINE INNODB STATUS` is one of the most important diagnostic commands when operating MySQL with InnoDB. Its output provides a snapshot of the storage engine's internal state: active transactions, locks and waits, the most recently detected deadlock, I/O activity, redo logs, the buffer pool, and row operation counters. When queries hang, deadlocks occur, or I/O spikes abnormally, this command helps pinpoint which area to investigate next.

The output is quite long and contains many cumulative counters. Do not read it as a complete log or draw conclusions from a single isolated number. Record the capture timestamp, inspect sections relevant to the symptom, compare multiple snapshots over time, and cross-reference with `performance_schema`, `sys` schema, the error log, and execution plans.

### 1. Running SHOW ENGINE INNODB STATUS

In the MySQL command-line client, use `\G` to display the row vertically, making a very long text column much easier to read:

```sql
SHOW ENGINE INNODB STATUS\G
```

`\G` is a MySQL client statement terminator, not part of SQL syntax sent by applications. In JDBC, applications, or tools that accept standard SQL only, run:

```sql
SHOW ENGINE INNODB STATUS;
```

The result usually contains `Type`, `Name`, and `Status` columns; diagnostic details reside in the `Status` column. An account requires the `PROCESS` privilege to view InnoDB status. Without it, request appropriate least-privilege access from a DBA or have an authorized operator run the command.

Save the capture timestamp and MySQL version alongside the output. When comparing two snapshots, note the elapsed interval, application load, and ongoing events to avoid comparing cumulative counters under different contexts.

### 2. Main Sections in the Output

Output can vary by version, configuration, and current activity, though it typically contains these sections:

| Section | Content to Inspect | Used When Investigating |
| --- | --- | --- |
| `BACKGROUND THREAD` | Master thread and background thread activity | Spotting abnormal background activity |
| `SEMAPHORES` | Mutexes, rw-locks, spin rounds, OS waits, and internal contention | Investigating internal InnoDB synchronization waits |
| `LATEST DETECTED DEADLOCK` | Two or more transactions, held/waiting locks, and the rolled-back victim | Analyzing the most recent deadlock |
| `TRANSACTIONS` | Open transactions, states, row lock counts, undo entries, and queries | Finding long transactions, lock waits, and old read views |
| `FILE I/O` | Pending reads/writes, I/O threads, and read/write/flush counts | Investigating I/O load and write queues |
| `INSERT BUFFER AND ADAPTIVE HASH INDEX` | Change buffer and adaptive hash index activity | Assessing secondary index update costs and index lookups |
| `LOG` | LSN, redo log flushes, and checkpoints | Investigating redo/checkpoint pressure |
| `BUFFER POOL AND MEMORY` | Buffer pool pages, free/dirty pages, read-ahead, and flushing | Investigating caching and page I/O |
| `ROW OPERATIONS` | Insert/update/delete/read counters and row processing activity | Observing engine activity trends |

Not every version displays the exact same headings, order, or field set. Read the actual labels in your running server's output.

### 3. Reading LATEST DETECTED DEADLOCK

`LATEST DETECTED DEADLOCK` describes the most recent deadlock detected by InnoDB. This section typically shows:

1. When the deadlock was detected.
2. Participating transactions, transaction IDs, and states.
3. Each transaction's most recent or waiting SQL statement.
4. Locks currently held by each transaction (`HOLDS THE LOCK(S)`).
5. Locks requested by each transaction (`WAITING FOR THIS LOCK TO BE GRANTED`).
6. Associated table, index, lock mode, and record/index entry details.
7. Which transaction was chosen as the victim and rolled back (`WE ROLL BACK TRANSACTION`).

Abbreviated illustrative example:

```text
------------------------
LATEST DETECTED DEADLOCK
------------------------
*** (1) TRANSACTION:
TRANSACTION 81001, ACTIVE 8 sec starting index read
mysql tables in use 1, locked 1
UPDATE account SET balance = balance - 10 WHERE id = 2

*** (1) HOLDS THE LOCK(S):
RECORD LOCKS ... index PRIMARY ... lock_mode X locks rec but not gap

*** (1) WAITING FOR THIS LOCK TO BE GRANTED:
RECORD LOCKS ... index PRIMARY ... lock_mode X locks rec but not gap waiting

*** (2) TRANSACTION:
TRANSACTION 81002, ACTIVE 5 sec starting index read
UPDATE account SET balance = balance + 10 WHERE id = 1

*** (2) HOLDS THE LOCK(S):
RECORD LOCKS ... index PRIMARY ... lock_mode X locks rec but not gap

*** (2) WAITING FOR THIS LOCK TO BE GRANTED:
RECORD LOCKS ... index PRIMARY ... lock_mode X locks rec but not gap waiting

*** WE ROLL BACK TRANSACTION (2)
```

This is an illustrative structural example, not output taken from a live server. When reading real output, match each `HOLDS` and `WAITING` block to its transaction to reconstruct the wait cycle. The final line shows which transaction InnoDB chose to roll back in that deadlock.

`space id`, `page no`, `heap no`, `index`, and record dump details identify the exact lock location at the InnoDB level. For application operators, the table name, index name, SQL statements, and transaction order are usually the most actionable starting points.

### 4. Understanding a Deadlock Cycle Across Two Sessions

A deadlock occurs when transactions form a wait cycle: each transaction holds a resource needed by another, and none can proceed unless one is rolled back.

Suppose an account table:

```sql
CREATE TABLE account (
    id BIGINT NOT NULL PRIMARY KEY,
    balance DECIMAL(12, 2) NOT NULL
) ENGINE = InnoDB;

INSERT INTO account (id, balance)
VALUES (1, 1000.00), (2, 1000.00);
```

Two sessions transfer funds using opposite lock acquisition orders.

**Session A:**

```sql
START TRANSACTION;
UPDATE account SET balance = balance - 100 WHERE id = 1;
-- A holds an X lock on account.id = 1.
```

**Session B:**

```sql
START TRANSACTION;
UPDATE account SET balance = balance - 50 WHERE id = 2;
-- B holds an X lock on account.id = 2.
```

**Session A continues:**

```sql
UPDATE account SET balance = balance + 100 WHERE id = 2;
-- A must wait for the lock on id = 2 held by B.
```

**Session B continues:**

```sql
UPDATE account SET balance = balance + 50 WHERE id = 1;
-- B must wait for the lock on id = 1 held by A.
-- InnoDB detects the cycle and rolls back one transaction.
```

Once the deadlock occurs, one session receives `ERROR 1213 (40001): Deadlock found when trying to get lock; try restarting transaction`. The victim transaction is rolled back in full. The surviving transaction can proceed once locks are released. Which session gets rolled back depends on InnoDB's selection logic; do not assume it is always the session executing the final statement.

Immediately after the incident, run `SHOW ENGINE INNODB STATUS\G` to view the latest deadlock. Correlate rows `id = 1` and `id = 2`, held/waiting locks, and each session's SQL. In this example, the direct cause is two flows updating the same set of rows in opposite orders.

### 5. Distinguishing Deadlocks from Lock Wait Timeouts

Deadlocks and lock wait timeouts both stop a write statement from progressing, but their natures differ:

| Phenomenon | Deadlock | Lock Wait Timeout |
| --- | --- | --- |
| Cause | Wait cycle between transactions | One transaction waits for a lock longer than allowed |
| Detection | InnoDB deadlock detector finds the cycle | Wait exceeds `innodb_lock_wait_timeout` |
| Common error | `1213`, SQLSTATE `40001` | `1205`, SQLSTATE `HY000` |
| Default rollback scope | Entire victim transaction is rolled back | Typically only the statement is rolled back; full transaction rolls back only if `innodb_rollback_on_timeout` is enabled |
| Evidence | `LATEST DETECTED DEADLOCK` section present | May have no deadlock entry; inspect current lock waits or application logs |

Not every long lock wait is a deadlock. One transaction may hold a lock for a long time without forming a cycle; another transaction then waits until timeout. Looking only at `LATEST DETECTED DEADLOCK` can cause you to miss the root cause of a lock wait timeout.

Check related variables:

```sql
SHOW GLOBAL VARIABLES LIKE 'innodb_lock_wait_timeout';
SHOW GLOBAL VARIABLES LIKE 'innodb_rollback_on_timeout';
SHOW GLOBAL VARIABLES LIKE 'innodb_deadlock_detect';
```

Applications must distinguish the two errors to decide how to retry. On a deadlock error, the victim transaction rolled back completely; retry the entire unit of work. On a timeout, verify transaction state according to server configuration and handle explicit rollback before retrying.

### 6. Reading TRANSACTIONS to Find Long Lock-Holding Transactions

The `TRANSACTIONS` section typically lists active transactions, waiting transactions, and internal state. Notable fields include:

- `TRANSACTION ... ACTIVE ...`: transaction ID and active duration.
- `LOCK WAIT`: transaction waiting on a lock.
- `mysql tables in use` / `locked`: tables in use or locked as reported by the engine.
- `lock struct(s)`, `row lock(s)`: lock structures and row locks held by the transaction.
- `undo log entries`: volume of changes to process during rollback/purge.
- `MySQL thread id` and `query id`: helps correlate with connections/processlist.
- `Trx read view`: consistent-read snapshot info in certain states.

Long-running open transactions can hold row locks, block purge from cleaning up old row versions, or hold SQL-level metadata locks. A session showing `Sleep` in the process list can still hold an open transaction if the application started a transaction without committing or rolling back. Do not look only for active queries; also look for long transactions with no current statement.

Near the top or bottom of `TRANSACTIONS`, `History list length` may appear. This indicates the amount of undo history awaiting purge, not the number of locked rows. If this value grows persistently, check old transactions/read views, undo generation rate, purge capacity, and write load. A single snapshot is insufficient to conclude purge is stalled; compare over time.

### 7. Reading FILE I/O and LOG

`FILE I/O` displays InnoDB file read/write activity, including pending reads/writes, I/O threads, and read/write/flush counts. These figures help identify I/O queuing, though many counters are cumulative since startup or reset. Compare two snapshots separated by a time interval to gauge trends rather than reading large cumulative totals as instantaneous load.

In `LOG`, pay attention to fields such as:

- Log sequence number (LSN): current log position.
- Log flushed up to: point up to which redo has been flushed.
- Pages flushed up to or checkpoint LSN: corresponding checkpoint marker.
- Pending log flushes or pending checkpoint writes, if present.
- Log I/O and redo-writing counters.

The gap between the current LSN and checkpoint LSN can reflect redo volume needing processing before checkpoint advances. If checkpoint lags far behind persistently, the system may be under dirty-page flushing or I/O pressure. Do not judge from a single value; correlate LSN growth rate, checkpoint rate, redo capacity, write throughput, and storage latency.

### 8. Reading BUFFER POOL AND MEMORY

The buffer pool caches InnoDB data and index pages. Common metrics in this section include:

| Metric | Practical Meaning |
| --- | --- |
| `Buffer pool size` | Configured/allocated buffer pool size in pages or capacity |
| `Free buffers` | Free pages ready for allocation |
| `Database pages` | Data/index pages currently in the buffer pool |
| `Modified db pages` | Dirty pages not yet flushed completely to tablespaces |
| `Pending reads` | Pending page read requests |
| `Pending writes` | Pending page write requests by reported flush category |
| `Pages made young/not young` | Activity moving pages between LRU young/old sublists |
| `Pages read`, `created`, `written` | Corresponding page activity counters |

A low `Free buffers` ratio does not automatically mean memory exhaustion. InnoDB uses most of the buffer pool to cache useful pages, evicting older pages via LRU as needed. Inspect buffer pool read requests, physical reads, dirty pages, pending I/O, interval hit ratios, and storage latency together.

If `Modified db pages` is high, inspect flush rates and checkpoints. If `Pending reads` rises alongside physical read latency, the workload may require pages not in cache or storage may be saturated. If page reads are high without query speedups, review indexes, working set size, and random access patterns.

### 9. Reading SEMAPHORES and Internal Contention

`SEMAPHORES` describes internal mutexes and rw-locks used by InnoDB threads to synchronize internal data structures. You may see spin rounds, OS waits, signal counts, or waiting thread details.

This section is not SQL row locking. Row locks are logical locks on records/indexes coordinating transactions; semaphores are internal engine synchronization primitives. If OS waits or contention rise, correlate CPU usage, concurrent thread counts, workload patterns, MySQL version, and Performance Schema wait events.

Do not declare an error from a single high `spin rounds` line. Significance depends on sampling interval, CPU, load, and the version's synchronization algorithms. If the issue persists, collect multiple samples and inspect wait summaries before changing configuration.

### 10. Reading INSERT BUFFER, ADAPTIVE HASH INDEX, and ROW OPERATIONS

The `INSERT BUFFER AND ADAPTIVE HASH INDEX` section (naming may vary by version) reports change buffer and adaptive hash index activity. The change buffer can defer certain modifications to secondary index pages not in the buffer pool to merge I/O later; the adaptive hash index is an internal hash structure accelerating repeated B-tree lookups. These metrics are meaningful only in the context of workload and configuration.

`ROW OPERATIONS` reports rates or counters for rows read, inserted, updated, and deleted. This is an engine-level activity indicator, not per-table query statistics. To find which SQL statements generate load, combine Performance Schema statement digests, the slow query log, and the process list.

### 11. Logging Every Deadlock to the Error Log

`SHOW ENGINE INNODB STATUS` retains only the most recent deadlock. When a new deadlock occurs, `LATEST DETECTED DEADLOCK` is replaced by the new event; during frequent deadlocks, earlier evidence can be lost before you capture it.

To record every detected deadlock in the MySQL error log, enable:

```sql
SET GLOBAL innodb_print_all_deadlocks = ON;
```

Check status:

```sql
SHOW GLOBAL VARIABLES LIKE 'innodb_print_all_deadlocks';
```

Once enough data is gathered or the investigation ends, disable it:

```sql
SET GLOBAL innodb_print_all_deadlocks = OFF;
```

This variable preserves more deadlocks in the error log, though log volume can grow rapidly if the application suffers frequent concurrency errors. Monitor log disk usage, access permissions, and retention policy. Runtime changes do not necessarily persist across restarts; to keep settings, update server configuration appropriately.

### 12. Enabling Periodic InnoDB Monitor Output

You can configure InnoDB to write periodic monitor output to the error log:

```sql
SET GLOBAL innodb_status_output = ON;
```

To include detailed lock information in monitor output:

```sql
SET GLOBAL innodb_status_output_locks = ON;
```

When monitoring is no longer needed, disable both to avoid unnecessary log growth:

```sql
SET GLOBAL innodb_status_output_locks = OFF;
SET GLOBAL innodb_status_output = OFF;
```

Periodic monitor output can help during an extended investigation, but should not stay enabled indefinitely without a clear need. Verify error log destination, disk capacity, retention, and filtering beforehand. These are global-scope variables requiring appropriate administrative privileges.

### 13. Using Performance Schema for Active Lock Waits

InnoDB Status is useful for an overall snapshot and the latest deadlock. To query active lock-wait relationships in structured form, MySQL 8.0 provides `performance_schema.data_locks` and `performance_schema.data_lock_waits`.

List locks currently tracked by InnoDB:

```sql
SELECT
    ENGINE_TRANSACTION_ID,
    THREAD_ID,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    INDEX_NAME,
    LOCK_TYPE,
    LOCK_MODE,
    LOCK_STATUS,
    LOCK_DATA
FROM performance_schema.data_locks;
```

View waiting and blocking lock pairs:

```sql
SELECT
    r.ENGINE_TRANSACTION_ID AS waiting_trx,
    r.THREAD_ID AS waiting_thread,
    r.OBJECT_SCHEMA,
    r.OBJECT_NAME,
    r.INDEX_NAME,
    r.LOCK_MODE AS waiting_lock_mode,
    b.ENGINE_TRANSACTION_ID AS blocking_trx,
    b.THREAD_ID AS blocking_thread,
    b.LOCK_MODE AS blocking_lock_mode
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS r
  ON r.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS b
  ON b.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID;
```

If the `sys` schema is available, `sys.innodb_lock_waits` provides an easier-to-read view:

```sql
SELECT
    waiting_pid,
    waiting_query,
    blocking_pid,
    blocking_query,
    locked_table,
    locked_index,
    waiting_lock_mode,
    blocking_lock_mode,
    wait_age
FROM sys.innodb_lock_waits;
```

These views focus on locks existing or waiting at query time. Already-resolved deadlocks will no longer appear in `data_lock_waits`; use `LATEST DETECTED DEADLOCK` or the error log for evidence of past deadlocks.

### 14. Linking Transactions to Connections and SQL Statements

From `THREAD_ID` in Performance Schema, you can locate the processlist ID and current statement info. Example:

```sql
SELECT
    THREAD_ID,
    PROCESSLIST_ID,
    PROCESSLIST_USER,
    PROCESSLIST_HOST,
    PROCESSLIST_DB,
    PROCESSLIST_COMMAND,
    PROCESSLIST_TIME,
    PROCESSLIST_STATE,
    PROCESSLIST_INFO
FROM performance_schema.threads
WHERE TYPE = 'FOREGROUND'
ORDER BY PROCESSLIST_TIME DESC;
```

With the connection ID identified, inspect active SQL via `SHOW FULL PROCESSLIST`. To view open InnoDB transactions:

```sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_wait_started,
    trx_mysql_thread_id,
    trx_query,
    trx_rows_locked,
    trx_rows_modified
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

Match `PROCESSLIST_ID` or `trx_mysql_thread_id` with thread/transaction metadata to locate the lock-holding session. Note that the process list may show `Sleep` while the connection still holds an open transaction; `PROCESSLIST_INFO` may then be `NULL`, so do not filter only for sessions actively running SQL.

### 15. Investigation Workflow When the Application Reports Deadlocks

When encountering error `1213`, gather evidence before changing settings or forcing query ordering:

1. Record timestamp, endpoint/job, request ID, business transaction, and associated SQL from application logs.
2. Capture `SHOW ENGINE INNODB STATUS\G` immediately upon detection to preserve the latest deadlock.
3. If deadlocks occur frequently, enable `innodb_print_all_deadlocks` during an investigation window and collect the error log.
4. Read each transaction in the deadlock: table, index, SQL statement, held locks, and waiting locks.
5. Reconstruct the wait cycle; identify row/index access order across concurrent business flows.
6. Check indexes and `EXPLAIN` to see whether statements scan or lock wider ranges than expected.
7. Fix transaction design: access resources in a consistent order, keep transactions short, add suitable indexes, or use atomic updates.
8. Retry the entire rolled-back transaction with bounded attempts, jitter/backoff, and idempotency.
9. Monitor deadlock rates, latency, lock waits, and side effects after deploying changes.

If the application logs only the final SQL statement without request/transaction context, reconstructing operation order is difficult. Add correlation IDs, business operation names, and transaction start/end timestamps to application logs.

### 16. Reducing Deadlocks After Identifying Root Cause

No single configuration eliminates all deadlocks. Mitigations should address the actual wait cycle:

- **Consistent lock ordering:** when multiple flows update the same two accounts, always lock in ascending `id` order.
- **Short transactions:** never make HTTP calls, send emails, or wait on user input while holding row locks.
- **Appropriate indexes:** reduce the number of records scanned and locked; inspect plans for `UPDATE`/`DELETE`.
- **Atomic updates:** place business conditions into a single `UPDATE` rather than reading and then writing in unlocked steps.
- **Small batches:** break bulk operations into bounded transactions.
- **Proper retries:** retry the entire victim transaction, not merely the last statement.
- **Idempotency:** ensure retries do not create duplicate business side effects.

Do not disable `innodb_deadlock_detect` merely to lower CPU before measuring and understanding the cause. Disabling the detector forces InnoDB to rely on timeouts to break cycles, leaving transactions blocked much longer before release. Consider changing it only for measured high-contention workloads with an appropriate fallback design.

### 17. Common Misconceptions Reading InnoDB Status

| Misconception | Correct Understanding |
| --- | --- |
| `LATEST DETECTED DEADLOCK` is the history of all deadlocks | It is only the latest deadlock; enable `innodb_print_all_deadlocks` to log every event to the error log |
| No deadlock section means no lock waits | Lock waits can exist without forming a cycle; check `data_lock_waits` and `sys.innodb_lock_waits` |
| `History list length` is the number of locked rows | It indicates undo history awaiting purge; read alongside long transactions and purge activity |
| Low `Free buffers` always means insufficient RAM | Buffer pool is meant for caching; inspect physical reads, pending I/O, and hit behavior |
| High `Pending writes` in one sample proves a storage fault | Compare over time and correlate latency, throughput, and checkpoints |
| `Sleep` means the session holds no resources | An idle session can still hold a transaction and locks if uncommitted |
| Deadlocks are always caused by missing indexes | Opposite lock acquisition orders can deadlock even with efficient primary-key lookups |
| Increasing timeout fixes deadlocks | Timeouts do not break deadlock cycles; the detector handles deadlocks while timeout handles non-cyclic waits |

### 18. Protecting Sensitive Information When Sharing Output

InnoDB Status can contain SQL statements, schema/table names, usernames, hostnames, data values in record dumps, and business-activity clues. Before posting output to public tickets or forums, scrub passwords, tokens, emails, personal data, sensitive literals, hostnames, and internal database names per organizational policy.

Grant `PROCESS` and Performance Schema read privileges only to required operational accounts. Do not grant broad privileges to application accounts solely to aid diagnostics. Store error logs and snapshots under appropriate retention, restrict readers, and avoid capturing sensitive data outside necessary scope.

### 19. Practical Checklist

1. Run `SHOW ENGINE INNODB STATUS\G` using an account with appropriate privileges.
2. Record the capture timestamp and MySQL version.
3. Read `LATEST DETECTED DEADLOCK`, identifying both transactions, held locks, waiting locks, and the victim.
4. Distinguish deadlock error `1213` from lock wait timeout `1205`.
5. Read `TRANSACTIONS` to find long transactions, row locks, undo entries, and old read views.
6. Inspect `FILE I/O`, `LOG`, `BUFFER POOL AND MEMORY`, and `SEMAPHORES` according to symptoms, comparing multiple samples.
7. Use `performance_schema.data_locks`, `data_lock_waits`, or `sys.innodb_lock_waits` to inspect active lock waits.
8. Correlate threads/connections with the process list and `information_schema.innodb_trx`.
9. Enable `innodb_print_all_deadlocks` or monitor output only as long as needed while managing error log size.
10. Fix lock ordering, indexes, or transaction scope based on evidence; retry whole transactions safely.

`SHOW ENGINE INNODB STATUS` provides a valuable internal snapshot to start investigations, especially the latest deadlock section and transaction list. Combining it with active lock waits in Performance Schema, the process list, the error log, and query plans moves you from vague symptoms like "the app is hanging or deadlocking" to specific root causes in transactions, indexes, and lock ordering.
