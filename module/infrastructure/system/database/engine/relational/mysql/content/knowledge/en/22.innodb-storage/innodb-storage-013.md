# Crash Recovery and Transaction State Restoration

When MySQL stops abruptly, InnoDB must bring data on disk back to a consistent state before allowing applications to resume writing. The **crash recovery** mechanism uses the redo log to reapply necessary changes and the undo log to revert incomplete transactions. Consequently, after a successful restart, committed transactions are preserved according to the configured durability policy, while uncommitted transactions are rolled back.

This lesson belongs to the **InnoDB Storage** section of MySQL. You will understand the roles of redo, undo, checkpoints, doublewrite, and the binary log; trace the stages InnoDB goes through when recovering after a crash; inspect durability settings; handle cases where a client loses connection during COMMIT; and recover data to a specific point in time using backups combined with binary logs.

## 1. What Problem Does Crash Recovery Solve?

During operation, InnoDB typically modifies pages in the buffer pool first. Pages that have been modified but not yet written back to data files are called **dirty pages**. If the server halts abruptly, data files may still lack some committed changes or contain partially written pages.

InnoDB uses write-ahead logging (WAL): required redo information must be written to the redo log before the corresponding data page is written down to a data file. Upon restarting after a crash, the engine can use the redo log to bring pages to the required state, then use undo to remove the effects of uncommitted transactions.

Two primary goals:

- **Consistency:** data structures and transaction states are brought back to a consistent state according to InnoDB rules.
- **Durability:** committed changes are preserved within the bounds of flush settings, the operating system, storage hardware, and backup mechanisms.

Crash recovery is InnoDB's automatic mechanism when the server restarts after an unclean shutdown. It differs from recovering a database whose files were lost or restoring to an earlier point in time from a backup.

## 2. Redo Log, Undo Log, and Binary Log

Three log types serve distinct roles:

| Component | Content / Purpose | When used? |
| --- | --- | --- |
| Redo log | Records information needed to replay InnoDB page changes. | Crash recovery: replays logged changes whose data pages may not have been flushed yet. |
| Undo log | Stores information needed to roll back changes and reconstruct older row versions for MVCC. | Rolling back uncommitted transactions; consistent reads needing prior versions. |
| Binary log (binlog) | Records logical or row-level change events depending on configuration. | Replication and point-in-time recovery after restoring a backup. |

Redo does not replace undo. When crash recovery runs, a change from an uncommitted transaction may still be redone onto a page, and then that transaction is rolled back using undo. That is why you cannot assume every change replayed from redo belongs to a committed transaction.

The binary log does not replace the redo log either. Redo serves InnoDB's internal recovery; binlog serves replication and recovery along an SQL/row event stream. When binary logging is enabled, MySQL coordinates commits between InnoDB and the binlog via internal two-phase commit to minimize mismatch between the two logs.

## 3. LSN, Checkpoints, and Write-Ahead Logging

Each change written to the redo log corresponds to a logical position called a **Log Sequence Number (LSN)**. The LSN increases monotonically along the redo stream. It helps InnoDB identify which redo has been recorded and up to what point data pages have been checkpointed.

A **checkpoint** is a milestone indicating that dirty pages prior to a specific redo position have been written down to data files as required. When a server crashes, InnoDB does not need to re-read the entire redo log since database creation; the engine starts from the appropriate checkpoint and processes the necessary redo thereafter.

General write flow:

```text
Transaction modifies record
          |
          v
Page in buffer pool becomes dirty
          |
          +----------------------+
          |                      |
          v                      v
       Redo log              Dirty page
          |                      |
          v                      |
Write/flush redo before          |
data page                        |
          |                      |
          +----------+-----------+
                     |
                     v
          Page flushed to data file
                     |
                     v
                 Checkpoint
```

WAL lets InnoDB acknowledge transaction commits without synchronously writing every data page to its final location. The redo log supplies the information to bring pages up to date later.

## 4. Transaction Commits and Durability Configuration

When a transaction commits, InnoDB writes the corresponding redo to the log. How promptly the log is written and flushed to storage depends on `innodb_flush_log_at_trx_commit`.

```sql
SHOW VARIABLES LIKE 'innodb_flush_log_at_trx_commit';
```

| Value | General behavior | Trade-off |
| --- | --- | --- |
| `1` | Writes and flushes redo log to storage at every commit. | Highest durability under standard design, in exchange for potential commit I/O cost. |
| `2` | Writes redo log to file at every commit; flushes from OS cache to storage periodically, typically about once per second. | Can lose recent commits if the OS or server fails before the flush. |
| `0` | Writes and flushes redo log periodically, typically about once per second, rather than at every commit. | Can lose recent transactions if mysqld or the system stops abruptly. |

Actual flush intervals are influenced by `innodb_flush_log_at_timeout`, system load, and storage device capability. Value `1` only guarantees durability under the assumption that the OS and hardware honor flush requests properly; controllers or drives with unprotected caches can weaken durability.

If the binary log is enabled, pay attention to `sync_binlog` as well:

```sql
SHOW VARIABLES LIKE 'sync_binlog';
SHOW VARIABLES LIKE 'log_bin';
```

- `sync_binlog = 1` requests synchronizing the binlog to storage after every commit group per MySQL's mechanism.
- Value `0` leaves flush timing to the OS; values `N` greater than 1 synchronize after every N event groups.

For systems requiring high durability with binary logging enabled, a commonly considered configuration is `innodb_flush_log_at_trx_commit = 1` alongside `sync_binlog = 1`. Measure I/O load and verify storage hardware genuinely honors flush commands before treating the configuration as an absolute guarantee.

### Coordinating InnoDB and the Binary Log

When binary logging is enabled, InnoDB transaction commits are coordinated with the binlog via internal two-phase commit. Conceptually:

1. InnoDB places the transaction into the **prepare** state and writes necessary information to the redo log.
2. MySQL writes transaction events to the binary log and syncs according to `sync_binlog`.
3. InnoDB completes the commit once the binlog phase succeeds.
4. If the server crashes between phases, recovery cross-checks InnoDB's prepared state against the binlog to decide whether the transaction should be finalized or rolled back.

This is internal coordination between the storage engine and server. Applications do not execute these two phases manually with two separate SQL statements.

## 5. Doublewrite and Protecting Pages Against Partial Writes

The redo log protects replayability of changes, yet a page can be partially written if power fails or the system crashes mid-page-write. A partially written page is commonly called a **torn page**.

InnoDB has the **doublewrite buffer** mechanism: before writing a page to its final location in a data file, the engine writes a copy of the page to the doublewrite area, and only then writes the page to its target location. If a crash partially corrupts the target page, InnoDB can use the valid page copy in doublewrite to restore it and then apply necessary redo.

Checking configuration:

```sql
SHOW VARIABLES LIKE 'innodb_doublewrite';
```

Doublewrite helps protect pages against partial writes; it does not replace redo logs, backups, or replicas on other servers. Doublewrite storage locations and implementation details can differ by version and configuration, so do not manually modify or delete related internal files.

## 6. Crash Recovery Phases at MySQL Startup

When mysqld detects InnoDB was not shut down cleanly, the engine performs recovery before allowing normal workloads to proceed. The process can be summarized as follows:

1. **Read startup state and checkpoint.** InnoDB identifies the checkpoint LSN and the redo range to process.
2. **Check/restore necessary pages.** The doublewrite mechanism can be used to handle torn pages.
3. **Redo.** The engine replays changes from the redo log to bring pages up to the state reflected in the log.
4. **Roll back incomplete transactions.** Uncommitted transactions are reverted using the undo log. Committed transactions are retained according to recovery state and durability policy.
5. **Resume background processing.** Purge and cleanup tasks can continue after the server starts; some remaining work may proceed asynchronously.

The exact order of internal tasks depends on version. What matters is that redo and undo solve two different problems: redo brings pages to a recoverable state, and undo removes the effects of uncommitted transactions.

### Transaction State After a Crash

| Pre-crash state | Post-recovery outcome |
| --- | --- |
| Transaction committed and required logs durably stored | Changes are retained. |
| Transaction uncommitted | Changes are rolled back via undo. |
| Transaction in prepared phase with binlog enabled | MySQL cross-checks InnoDB state against binlog to finalize commit or roll back properly. |
| Client lost connection right while sending COMMIT | Client may not know whether the commit succeeded; business state must be verified before retrying. |

Crash recovery cannot turn an un-flushed commit into a guaranteed commit. If configuration permits losing the most recent redo or binlog during power loss, those transactions may not appear after recovery.

## 7. Experiment: Uncommitted Transactions Are Rolled Back After a Crash

You can observe this principle in a dedicated lab environment. Never intentionally kill mysqld or power off a machine in production.

Create the table and initial data:

```sql
CREATE TABLE crash_recovery_lab (
    item_id INT PRIMARY KEY,
    quantity INT NOT NULL
) ENGINE = InnoDB;

INSERT INTO crash_recovery_lab (item_id, quantity)
VALUES (1, 10);
```

In session A:

```sql
START TRANSACTION;

UPDATE crash_recovery_lab
SET quantity = 99
WHERE item_id = 1;

-- Do not COMMIT.
```

At this point, the change to `99` is uncommitted. If mysqld is stopped abruptly in the lab and restarted, InnoDB uses redo to recover needed pages and then rolls back the uncommitted transaction using undo.

After MySQL restarts, check:

```sql
SELECT quantity
FROM crash_recovery_lab
WHERE item_id = 1;
-- Expected value: 10
```

The value reverts to `10` because the transaction updating it to `99` had not committed. If the transaction had committed and required redo was durably saved, the expected result would be `99`.

To verify the committed branch, reset the value to `10`, run `UPDATE`, and then `COMMIT` before stopping MySQL in a separate test. You cannot run a `ROLLBACK` statement after the server restarts to undo a pre-crash transaction; uncommitted transactions were already handled by recovery.

## 8. Reading Logs and Verifying Recovery

MySQL's error log is the primary source to determine whether the server ran crash recovery, recovery duration, and any errors encountered. Error log location depends on configuration:

```sql
SHOW VARIABLES LIKE 'log_error';
```

In the error log, look for messages mentioning InnoDB, checkpoint LSN, redo, transaction rollback, doublewrite, or page corruption. Exact phrasing and details vary across versions.

Once the server is up, inspect baseline status:

```sql
SELECT VERSION();
SHOW ENGINE INNODB STATUS\G
```

In the LOG section of `SHOW ENGINE INNODB STATUS`, LSN, checkpoint, and flush activity details help assess log state. The TRANSACTIONS section helps identify remaining open transactions. This is a point-in-time snapshot when the command runs, not a complete recovery history report.

Verify active durability settings:

```sql
SHOW VARIABLES WHERE Variable_name IN (
    'innodb_flush_log_at_trx_commit',
    'innodb_flush_log_at_timeout',
    'sync_binlog',
    'innodb_doublewrite',
    'log_bin'
);
```

After recovery, reconcile data against business invariants: monetary totals, balances, inventory counts, order statuses, and foreign key relationships. Do not rely solely on MySQL reporting `ready for connections` to conclude all business data is valid.

## 9. Client Loses Connection During COMMIT: Outcome May Be Ambiguous

A real-world scenario is when an application sends `COMMIT`, but the network drops before receiving a response. Two possibilities exist: the server committed yet the response was lost, or the server did not finish committing. From the client's perspective, a connection error alone cannot distinguish the two cases.

Do not automatically retry a non-idempotent operation such as deducting funds or creating an order. Design operations with an idempotency key or unique business code:

```sql
CREATE TABLE payment_requests (
    request_id VARCHAR(64) PRIMARY KEY,
    account_id BIGINT NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE = InnoDB;
```

The application records a unique `request_id` alongside the balance change in a single transaction. If the COMMIT response is lost, the application reconnects and looks up `request_id` to determine whether the request was recorded. The unique key prevents the same request from being processed twice if the application retries.

Workflow pattern:

1. Generate a stable request ID on the application side before sending the operation.
2. Within the same transaction, check/record the request ID and perform the business change.
3. Commit.
4. If connection is lost, query the request ID over a new connection; retry only per the designed idempotency rules.

Never use "did not receive a response" as proof that a transaction rolled back.

## 10. Recovering Data Using Backups and Binary Logs

Crash recovery handles internal state after an abnormal server shutdown. If data files are lost, physically corrupted, or you need to revert to before an erroneous operation, a backup/restore procedure is required. A point-in-time recovery (PITR) plan typically includes:

1. Restoring a consistent full backup from a known point in time.
2. Identifying the binary log starting position or timestamp corresponding to that backup.
3. Using `mysqlbinlog` to replay events after the backup up to just before the target stop time.
4. Verifying data and business invariants before reopening application traffic.

Example command structure replaying by position:

```bash
mysqlbinlog \
  --start-position=12345 \
  --stop-position=67890 \
  /backup/binlog.000123 \
  | mysql -u recovery_user -p
```

Example by timestamp:

```bash
mysqlbinlog \
  --start-datetime="2026-11-18 09:00:00" \
  --stop-datetime="2026-11-18 10:15:00" \
  /backup/binlog.000123 \
  | mysql -u recovery_user -p
```

These are command syntax examples; replace files, positions, timestamps, and connection credentials with your actual backup details. Exact positions must come from backup metadata or the backup tool used. Replaying from the wrong starting point can re-apply transactions already present in the backup; stopping at the wrong position can miss events or apply unwanted ones. When high precision is needed, prefer position/GTID and procedures recorded by the backup tool rather than timestamp estimates.

If GTID is enabled, retain GTID metadata of backups and binlogs to determine applied transaction sets. Never mix binlogs from different sources or servers without understanding topology and GTID sets.

### Crash Recovery and PITR Are Different

| Scenario | Primary mechanism |
| --- | --- |
| mysqld crashes yet data files remain intact | InnoDB automatically runs crash recovery using redo and undo. |
| A transaction was uncommitted at crash time | InnoDB rolls back that transaction via undo. |
| A transaction committed yet client lost the response | Reconnect and verify business state / idempotency key. |
| Data files are lost or irreparably corrupted | Restore backup; if needed, replay binlogs to advance to the desired point in time. |
| User accidentally ran and committed a bad statement | Restore backup to a recovery environment and use binlog/PITR to extract data up to right before the mistake, then reconcile and restore per plan. |

## 11. When Startup Fails and innodb_force_recovery

If InnoDB cannot start due to page corruption, redo/undo issues, or storage problems, first preserve the data directory and a backup copy. Inspect the error log, filesystem health, disk space, file permissions, and recent configuration changes.

`innodb_force_recovery` is an emergency mode to attempt starting InnoDB under certain corruption scenarios in order to extract data. Value `0` is normal operation; higher values skip progressively more recovery or background steps. High levels can cause data loss or permanent file corruption.

```sql
SHOW VARIABLES LIKE 'innodb_force_recovery';
```

Consider setting this variable only after making an exact copy of the data directory, reading the error log, and establishing a data extraction plan. Never use `innodb_force_recovery` as a routine fix for a slow restart; never raise its value arbitrarily and never write new business data to an instance running in forced recovery mode. The goal is usually starting just enough to dump data to a clean instance and restore via a safe procedure.

If a good backup exists, restoring to a fresh instance is usually clearer and easier to verify than continuing to run on a corrupted data directory.

## 12. Post-Crash Operations Checklist

When MySQL stops abruptly, follow this sequence:

1. Determine incident scope: mysqld crash, OS reboot, power outage, full filesystem, or storage hardware failure.
2. Preserve error logs and timestamps; never delete redo, undo, or data files to "try restarting."
3. Check filesystem free space, file permissions, data directory configuration, and recent changes.
4. Let InnoDB run normal recovery; monitor the error log until the server is ready.
5. Inspect `SHOW ENGINE INNODB STATUS`, durability settings, and active transactions.
6. Verify business data, replication/binlogs, and dependent applications.
7. If recovery fails, evaluate backups and PITR; keep corrupted data untouched for analysis.
8. Once service stabilizes, identify root cause and adjust backups, monitoring, flush policy, or hardware as needed.

Never manually delete redo logs, undo tablespaces, or `ibdata1` to force MySQL to start. These files are part of InnoDB's durable state; improper manipulation can render data unrecoverable.

## 13. Self-Check Exercises

1. Why does InnoDB need a redo log if pages were already modified in the buffer pool?
2. Why might crash recovery redo changes of an uncommitted transaction and then still roll back that transaction?
3. Distinguish the duties of the redo log, undo log, and binary log.
4. How does Checkpoint LSN help reduce recovery work?
5. What durability differences result from `innodb_flush_log_at_trx_commit` values of `1`, `2`, and `0`?
6. How does `sync_binlog` coordinate with InnoDB when binary logging is enabled?
7. What failure mode does the doublewrite buffer protect against? Why does it not replace backups?
8. Why can a client losing connection during COMMIT not conclude that the transaction rolled back?
9. Outline the steps to recover to a specific point in time using a full backup and binary logs.
10. When might `innodb_force_recovery` be considered and why must it be used with caution?

Clearly distinguish **crash recovery** from **backup restore/PITR**. Crash recovery uses redo and undo to complete internal recovery after a failure; backups and binary logs enable recovery when data is lost, corrupted, or must be rolled back to an earlier business point in time.
