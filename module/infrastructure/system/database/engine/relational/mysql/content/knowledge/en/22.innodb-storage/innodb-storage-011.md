# Undo Logs, History List, and Purge Operations

In the **DATABASE_MYSQL** module, learners master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query tuning, privilege management, backups, and relational database operations. Alongside the redo log for crash recovery, InnoDB uses the **undo log** to revert uncommitted changes and supply older data versions for consistent reads. When transactions modify or delete data, older versions may need to be retained for a time. Undo records no longer needed by any transaction are cleaned up by the **purge** process.

The history list reflects the amount of undo history awaiting purge. If a transaction holds an old read view for too long, purge cannot remove versions that the snapshot might still need. As a result, the history list can grow, undo tablespaces can bloat, queries may have to traverse more versions, and I/O pressure rises. Operating InnoDB effectively requires understanding the lifecycle of undo records, read views, the history list, purge threads, how to monitor them, and how to address root causes of purge lag.

## 1. What Problem Does the Undo Log Solve?

An UPDATE statement does more than change a row's current value. InnoDB must also retain enough information to:

- Revert the change if the transaction rolls back.
- Restore a consistent state when another transaction needs to read an older snapshot.
- Maintain version history until no read view needs those versions anymore.

For example, suppose an account has balance = 1000. Transaction A updates balance to 900. A transaction reading against a snapshot created before the change must still see balance = 1000. InnoDB uses undo information to reconstruct the older version for consistent reads.

The undo log stores the information needed to reverse a change or reconstruct a prior version. It is neither a full copy of the entire table nor the redo log.

### 1.1. Undo Log and Redo Log Are Different

| Component | Primary purpose | Question answered |
|---|---|---|
| Undo log | Rollback and reconstructing older versions for consistent reads | Before this change, what value did the row have? |
| Redo log | Crash recovery, replaying logged changes to restore data pages | Which changes need to be replayed after a crash? |
| Binary log | Recording server-level data change events for replication and point-in-time recovery | Which logical changes were written to the binlog? |

Undo and redo serve opposite directions. Undo helps roll back to a state prior to a change; redo helps replay needed changes after a crash. InnoDB must also ensure undo modifications can recover after a crash, so undo pages are protected by appropriate redo mechanisms. That does not make the undo log a redo log.

### 1.2. The Undo Log Is Not an Audit Log

Undo history has a technical purpose and is kept only until it is no longer needed for rollback or consistent reads. It is not a long-term business history to answer who modified data last month. If an audit trail is needed, design a dedicated audit table or event system with appropriate retention and access controls.

## 2. Two Types of Undo Records

InnoDB creates different undo records depending on the operation:

| Type | Role | General lifecycle |
|---|---|---|
| Insert undo | Reverts an inserted row if the transaction rolls back | After the transaction commits, this information is not needed for consistent reads and can be freed |
| Update undo | Reverts UPDATE/DELETE and reconstructs older versions for consistent reads | May need to be retained after commit until purge determines no read view needs it |

### 2.1. Insert Undo

When a transaction INSERTs a row, InnoDB writes enough undo information to delete that row if the transaction rolls back. Once the transaction commits, a new consistent read does not need to see the state before the row existed via an update version chain; therefore, insert undo can be freed according to the transaction's lifecycle.

This does not mean the newly inserted row is purged right after commit. The committed row is current data and remains in place. What gets freed is the undo information used to revert the insert operation.

### 2.2. Update Undo

When a transaction UPDATEs a row, InnoDB writes undo information containing the old data needed for rollback and reconstructing prior versions. If the transaction commits, the new version becomes current data, yet the older version may still be needed by read views created prior to the commit.

For DELETE, InnoDB typically marks the record as delete-marked instead of physically removing it immediately. Undo information lets older consistent reads continue seeing the row as it existed before deletion. Once no read view needs that version, purge can remove the old history and clean up the delete-marked record.

### 2.3. A Row Can Have a Version Chain

Suppose balance starts at 1000:

1. Transaction A changes balance to 900 and commits.
2. Transaction B changes balance to 800 and commits.
3. An old read view was created before both updates.

InnoDB may have to traverse the version chain to reconstruct the value 1000 for the old read view. The current version is 800; the undo chain contains the information needed to walk back through 900 and then to 1000.

Conceptual illustration:

~~~text
Current version on clustered index
balance = 800
       |
       | undo information
       v
Previous version
balance = 900
       |
       | undo information
       v
Older version
balance = 1000
~~~

This is a conceptual model of the version chain. Physical structures and how individual fields are stored in record and undo pages are more complex than the diagram.

## 3. Undo Records, Rollback Segments, and Undo Tablespaces

Undo records are stored in undo logs belonging to rollback segments. Rollback segments manage undo logs and are stored in undo tablespaces or the system tablespace depending on configuration and version.

Concepts to distinguish:

- **Undo record:** information describing a change to reverse or an older version to reconstruct.
- **Undo log:** a set of undo records tied to a transaction and operation type.
- **Rollback segment:** an InnoDB structure managing undo logs.
- **Undo tablespace:** a tablespace dedicated to undo data, backed by its own physical files in modern MySQL configurations.

Do not refer to an entire undo tablespace file as a single undo log. One tablespace can contain multiple rollback segments and undo logs from many transactions.

### 3.1. Transactions and Rollback Segments

When a transaction modifies data, InnoDB allocates and uses appropriate undo logs. A single transaction may need undo logs for both insert and update operations. Undo logs are managed inside rollback segments, supporting rollback and maintaining version history.

### 3.2. Undo Tablespaces

An undo tablespace stores rollback segments configured to reside outside the system tablespace. Separating undo data makes capacity management and undo file lifecycles more convenient in environments supporting this feature.

Undo tablespaces remain critical internal components of InnoDB. Never delete or move undo files using filesystem operations while MySQL is managing them. All changes must follow tablespace management mechanisms supported by your MySQL version.

### 3.3. Inspecting Tablespaces

On MySQL 8.0, you can inspect tablespace metadata:

~~~sql
SELECT
    SPACE,
    NAME,
    SPACE_TYPE,
    FILE_SIZE,
    ALLOCATED_SIZE,
    STATE
FROM information_schema.innodb_tablespaces
WHERE SPACE_TYPE = 'Undo';
~~~

Displayed columns and states depend on version. Use the output to identify undo tablespaces and track file sizes; do not treat FILE_SIZE or ALLOCATED_SIZE as the logical amount of undo history still needed.

## 4. How Do MVCC and Read Views Use Undo?

InnoDB uses Multi-Version Concurrency Control (MVCC) so consistent reads can read a snapshot without locking every row being read. A read view determines which transactions had committed at the time the snapshot was created and which transactions were uncommitted or invisible to the snapshot.

When the current row has been updated by another transaction after the snapshot timestamp, InnoDB can use the undo chain to reconstruct the older version matching the read view.

### 4.1. Snapshots in REPEATABLE READ

Under InnoDB's default REPEATABLE READ, the first consistent read in a transaction typically establishes the read view; subsequent consistent reads within the same transaction reuse that snapshot. The snapshot may require older data versions until the transaction ends.

Example:

~~~sql
-- Session A
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT balance
FROM accounts
WHERE account_id = 1;
~~~

After the first SELECT, Session A's read view is established. While A remains open, Session B updates balance and commits:

~~~sql
-- Session B
UPDATE accounts
SET balance = balance + 100
WHERE account_id = 1;
~~~

If Session A reads again via consistent SELECT in the same transaction, it continues seeing the old snapshot. InnoDB must retain enough undo history to reconstruct that value.

### 4.2. Snapshots in READ COMMITTED

Under READ COMMITTED, each standard consistent read creates a fresh snapshot per statement. Thus, a long transaction in READ COMMITTED does not hold the same read view across SELECT statements like REPEATABLE READ; however, an actively running statement still needs a snapshot for its execution duration.

Changing the isolation level solely to shrink the history list can alter business semantics. Evaluate read semantics before changing it.

### 4.3. Locking Reads Differ from Consistent Reads

SELECT ... FOR UPDATE and SELECT ... FOR SHARE are locking reads. They read current data according to InnoDB's locking rules and acquire required locks; do not treat them like standard consistent reads using an old snapshot.

A single transaction can perform both consistent reads and locking reads. Therefore, when investigating read views blocking purge, determine whether the transaction executed any consistent reads and when the read view was created, rather than looking only at the currently executing SQL statement.

## 5. What Is the History List?

After a transaction that updated or deleted data commits, update undo may continue to be retained in history to serve old read views. Committed undo logs still needed for MVCC are linked in the history list. Purge threads clean up these history entries once they are no longer needed.

**History list length** is a metric indicating the length of undo history awaiting purge in InnoDB. It is not the number of rows in a table, not the number of open transactions, and not the exact byte size of undo tablespaces.

### 5.1. When Does the History List Grow?

The history list can grow when:

- The workload has many UPDATEs or DELETEs committing continuously.
- A transaction holds an old read view, preventing purge from removing newer versions that the snapshot might still need.
- Purge cannot keep pace with the rate of undo history generation.
- A large volume of data is updated or deleted in a short period.

A rising history list during a heavy write burst does not automatically prove an error. Examine trends over time, purge speed, and the age of the oldest transaction/read view.

### 5.2. History List Is Not File Size

History list length measures unpurged undo history, not how much disk space undo tablespace files occupy. Tablespace files can retain allocated regions for reuse even after purge frees internal undo pages.

Therefore, a shrinking history list does not mean undo file sizes on the filesystem shrink immediately. Conversely, a large file does not necessarily mean all data inside it is still needed for consistent reads.

### 5.3. History List Is Not Transaction Count

A single transaction can generate many undo records and many pages; some other transactions generate very few. You cannot deduce the number of old transactions merely by looking at history list length.

Do not set alert thresholds based on a fixed number applied universally to every system. Establish baselines according to workload, storage capacity, growth/drain rates, and the server's purge capacity.

## 6. What Does Purge Do?

Purge is a set of InnoDB background tasks that clean up undo history and delete-marked data once no read view needs those older versions.

Purge can:

- Remove update undo no longer needed for consistent reads.
- Clean up older versions in version chains.
- Physically remove delete-marked records when conditions allow.
- Reclaim internal space inside InnoDB structures for reuse.

Purge is not an application-issued DELETE and does not run as a separate SQL statement inside business transactions.

### 6.1. Why Not Delete Old Versions Immediately at Commit?

Another transaction may have created a read view before the change committed. If InnoDB immediately deleted the old version, snapshot-reading transactions would fail to see accurate data as of their snapshot time.

Consequently, committing does not mean undo history is freed immediately. InnoDB must wait until no read view can possibly need that version.

### 6.2. Conditions Under Which Purge May Delete

A version can only be purged when no active transaction or read view needs that version to reconstruct a consistent read. Purge respects transaction history ordering and safety boundaries; it does not blindly delete every committed undo record.

### 6.3. Purge and DELETE

Example:

~~~sql
DELETE FROM orders
WHERE created_at < '2024-01-01';
~~~

In InnoDB, DELETE marks records as deleted and writes undo information. After the transaction commits, older read views may still need to see those rows. Only when no read view needs them can purge clean up the delete-marked records and associated undo history.

This explains why deleting millions of rows with DELETE does not necessarily shrink data files right away. Purge frees records so InnoDB can reuse internal space; shrinking physical files is a separate matter depending on tablespace type and administrative operations.

## 7. Old Read Views Cause Purge Lag

A common cause of history list growth is a transaction holding an old read view for a long duration.

Example:

1. Session A opens a REPEATABLE READ transaction and runs a consistent SELECT, creating a snapshot.
2. Session A neither commits nor rolls back, keeping the connection open.
3. Session B and other writers continuously run UPDATE/DELETE and commit.
4. Undo history for the new changes must be kept so Session A can reconstruct its old snapshot.
5. Purge cannot advance past the history boundary still needed by the old read view.
6. The history list grows steadily even though purge threads remain active.

### 7.1. Idle Transactions Can Still Hold a Read View

A transaction not currently executing an SQL statement can still hold a snapshot created by an earlier consistent read. Thus, the process list may show a session in Sleep state while its transaction remains open and holds a read view.

This is why you should not look only for long-running queries. Check how long transactions have been open, whether they hold a read view, and whether sessions are idle in transaction.

### 7.2. Long Transactions Do Not Always Hold an Old Read View

A transaction that has not yet performed a consistent read may not have created a read view in the same way. Under READ COMMITTED, snapshots are normally created per statement rather than held across the transaction. Therefore, do not judge solely by transaction age; check isolation level, read types, and transaction state.

### 7.3. Signs of Purge Lag

- History list length rises continuously or drains very slowly.
- Long-lived transactions exist, especially under REPEATABLE READ, that have executed consistent reads.
- Undo tablespaces grow in size or consume significant space.
- Consistent reads may have to traverse more versions.
- Purge cannot keep up with incoming updates/deletes.
- I/O and storage usage rise, and query or maintenance times may degrade.

Not every sign appears simultaneously. Correlate history list length, oldest transaction, undo tablespaces, and write workload.

## 8. Purge Threads and Background Processing Capacity

InnoDB uses purge threads to process undo history. The number of purge threads can be tuned with innodb_purge_threads in supported versions.

Checking:

~~~sql
SHOW VARIABLES LIKE 'innodb_purge_threads';
SHOW VARIABLES LIKE 'innodb_purge_batch_size';
~~~

Purge threads operate in the background, separate from application SQL request threads. Increasing thread counts can parallelize some purge workloads, yet cannot cross the boundary pinned by an old read view. If purge is disallowed from deleting versions because a transaction still needs them, adding threads does not fix the root cause.

### 8.1. When Should Purge Threads Be Tuned?

Consider adjusting only after:

- Confirming no long-lived transaction or read view is blocking purge.
- History list still grows because undo generation outpaces processing capacity.
- CPU, I/O, and workload indicate purge is the bottleneck.
- Testing in staging under similar load.

Do not increase threads reflexively. More threads can also increase resource contention or I/O.

### 8.2. Purge Batch Size

innodb_purge_batch_size affects how much work purge processes per batch. Changing it can affect smoothness and efficiency of background tasks. Keep the default setting unless metrics justify adjustment.

## 9. Monitoring History List and Transactions

### 9.1. SHOW ENGINE INNODB STATUS

An essential command for observing InnoDB's internal state:

~~~sql
SHOW ENGINE INNODB STATUS\G
~~~

Look for the TRANSACTIONS section and the line showing History list length. The same section can provide details on:

- Active transactions.
- Transactions waiting on locks.
- Associated read views and transaction IDs.
- Purge status and the transaction boundary processed by purge.
- Most recent deadlock.

Capture metrics periodically to observe trends. A single reading does not reveal whether the history list is rising or starting to drain.

### 9.2. Monitoring via INNODB_METRICS

MySQL provides the trx_rseg_history_len metric in INFORMATION_SCHEMA.INNODB_METRICS in supported versions:

~~~sql
SELECT
    NAME,
    COUNT,
    STATUS,
    COMMENT
FROM information_schema.innodb_metrics
WHERE NAME = 'trx_rseg_history_len';
~~~

The metric may need to be enabled depending on monitoring configuration and version. If no rows are returned or the metric is inactive, use SHOW ENGINE INNODB STATUS and check metric configuration rather than deriving the value using another formula.

### 9.3. Finding Long-Lived Transactions

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_wait_started,
    trx_mysql_thread_id,
    trx_isolation_level,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Focus on transactions that started early, especially open transactions that may hold a read view. trx_query may be NULL if the transaction is not currently running an SQL statement; that does not prove the transaction is not holding a snapshot.

### 9.4. Matching with the Process List

You can locate the corresponding connection:

~~~sql
SHOW FULL PROCESSLIST;
~~~

Match ID against trx_mysql_thread_id in INNODB_TRX. A connection in Sleep state that still has an open transaction warrants investigation.

### 9.5. Monitoring Undo Tablespaces

~~~sql
SELECT
    NAME,
    SPACE_TYPE,
    FILE_SIZE,
    ALLOCATED_SIZE,
    STATE
FROM information_schema.innodb_tablespaces
WHERE SPACE_TYPE = 'Undo';
~~~

Track capacity trends over time and correlate with the history list. Do not conclude purge is stuck simply because the undo file remains large; InnoDB may retain allocated space for reuse.

## 10. Investigating and Resolving an Abnormally Growing History List

When the history list grows continuously, follow this sequence:

1. Record History list length at multiple timestamps to establish the trend.
2. Check UPDATE/DELETE workloads and large write batches around the onset of growth.
3. List transactions via INFORMATION_SCHEMA.INNODB_TRX.
4. Correlate transaction age, isolation level, thread ID, and process list.
5. Identify sessions idle in transaction or holding long-lived consistent reads.
6. Check undo tablespaces and disk capacity.
7. Determine whether purge is making progress or is blocked by a read view.
8. Resolve old transactions per business decision; do not kill sessions before understanding rollback impact.
9. Monitor whether the history list shrinks after old read views are released.
10. Only afterward consider tuning purge threads or purge lag configuration.

### 10.1. Handling Long-Lived Transactions

If a session is identified holding a read view too long:

- Contact the application team or connection owner to understand what the transaction is doing.
- If the transaction was abandoned, terminate it per operational procedures.
- Prefer controlled COMMIT or ROLLBACK if the application can still act.
- If the connection must be KILLed, prepare for rollback duration and workload impact.

Do not KILL connections indiscriminately just because the history list grew. Rolling back a large transaction also consumes I/O and time; identify which session is genuinely the cause and can be ended safely.

### 10.2. Reducing Undo Generation Rate

If a heavy write workload generates undo faster than purge can clean up:

- Split large updates/deletes into smaller batches if business rules allow.
- Keep transactions short and commit regularly at business boundaries.
- Optimize indexes and predicates to avoid scanning or updating unnecessary rows.
- Avoid updating the same row multiple times within one transaction if operations can be consolidated.
- Schedule maintenance jobs during appropriate system load windows.

Batching into multiple transactions changes overall atomicity. Apply only if the business accepts each batch as an independent commit unit with a safe way to resume on mid-way failure.

## 11. Purge Lag and Throttling Variables

MySQL provides configuration variables related to purge lag:

- innodb_max_purge_lag: history list length threshold above which InnoDB may delay certain DML operations to help purge catch up.
- innodb_max_purge_lag_delay: maximum delay limit applied to DML by the purge lag mechanism.

Checking values:

~~~sql
SHOW VARIABLES LIKE 'innodb_max_purge_lag';
SHOW VARIABLES LIKE 'innodb_max_purge_lag_delay';
~~~

These variables throttle new undo generation by introducing delays; they do not immediately erase the history list and do not release old read views.

### 11.1. Do Not Set Arbitrary Thresholds

An appropriate threshold depends on capacity, workload type, I/O capability, purge speed, and acceptable application latency. Setting it too low can delay DML too often; setting it too high lets history lists accumulate heavily before throttling kicks in.

Measure baselines and test in staging. Never apply global settings in production based on a single history list snapshot.

### 11.2. Throttling Does Not Replace Fixing the Root Cause

If an old read view blocks purge, slowing down DML can reduce accumulation rate but does not make older versions purgeable. Release the long-held transaction/read view first.

## 12. Undo Tablespaces and Truncation

Undo tablespaces can remain large files after a heavy write workload ends. Cleaning the history list and returning internal tablespace space for reuse are distinct from shrinking the physical file.

Some MySQL versions support automatic undo tablespace truncation when configuration and conditions permit. Variables commonly inspected include:

~~~sql
SHOW VARIABLES LIKE 'innodb_undo_log_truncate';
SHOW VARIABLES LIKE 'innodb_max_undo_log_size';
SHOW VARIABLES LIKE 'innodb_undo_tablespaces';
~~~

Variable semantics and mutability depend on the MySQL version. Before using them, verify documentation for your exact server version and tablespace state.

### 12.1. General Conditions for Truncation

Truncation cannot be performed arbitrarily on an undo tablespace still actively used by running transactions. InnoDB must drain or wait until associated rollback segments in that tablespace are no longer active before safely executing truncation.

When automatic truncation is enabled, InnoDB can select eligible undo tablespaces for truncation per configured thresholds. Do not delete undo files directly via the filesystem or rename files yourself to free space.

### 12.2. Truncate Is Not Purge

| Operation | Goal |
|---|---|
| Purge | Removes undo history and delete-marked records no longer needed for MVCC |
| Reuse | Reuses freed space internally within the tablespace |
| Truncate undo tablespace | Reclaims undo file space once the tablespace qualifies |

Purge must first render undo history unnecessary. Truncation is a physical space-management step at the tablespace level with its own prerequisites.

## 13. Impact of Large Transactions and Mass DELETEs

A transaction modifying or deleting millions of records can generate huge amounts of undo. While the transaction remains uncommitted, undo required for rollback is retained. After commit, update undo may still be needed for old read views; purge must process the large history backlog before space can be reclaimed.

### 13.1. Large Uncommitted Transactions

While the transaction remains open:

- Undo needed for rollback continues to be held.
- Locks may continue to be held.
- Rollback can take a long time if changes are massive.
- Other transactions may be blocked.

### 13.2. After a Large Transaction Commits

After commit, the transaction no longer needs undo for rollback, yet old read views may still need version history. Purge can only remove the portion of history that is safe to reclaim.

### 13.3. Deleting in Batches

If business logic allows, instead of a massive DELETE:

~~~sql
DELETE FROM audit_events
WHERE created_at < '2023-01-01'
ORDER BY event_id
LIMIT 1000;
~~~

The application or job can loop batch by batch, commit each batch, and stop when affected rows reach 0. Ensure the filter condition has a suitable index and each batch makes forward progress.

Avoid infinite loops if a batch deletes zero rows due to unchanging data or conditions. Log deleted row counts, per-batch duration, and history list during execution.

### 13.4. Batch Trade-Offs

Small batches reduce undo volume and lock duration per transaction, but increase commit frequency and may extend total job runtime. Large batches reduce commit overhead, but create longer transactions and larger undo bursts. Pick batch sizes based on measurement; there is no single optimal number for every table.

## 14. Common Misconceptions

| Misconception | Reality |
|---|---|
| Committing deletes undo logs immediately | Update undo may still be needed by old read views |
| History list length is the count of deleted rows | It measures undo history awaiting purge, not row count |
| When history list drops, undo files shrink immediately | Tablespaces may retain allocated regions for reuse |
| A Sleeping transaction cannot affect purge | A session idle in transaction can still hold a read view |
| Every long transaction holds a read view | Depends on whether consistent reads occurred and the isolation level |
| Increasing innodb_purge_threads always fixes purge lag | Versions still needed by old read views cannot be purged |
| Undo logs are audit logs | Undo history has a technical lifecycle, not long-term business auditing |
| DELETE physically removes records at commit | InnoDB may need to purge delete-marked records afterward |
| Increasing innodb_max_purge_lag speeds up purge | That mechanism throttles DML rather than directly accelerating purge |
| Undo files can be deleted while MySQL runs | Undo tablespaces are managed by InnoDB; never delete directly via filesystem |

## 15. Practice Lab: Observing Undo History and Purge

Perform this on MySQL 8.0 with a dedicated lab database. This lab creates a small table and uses two sessions to observe an old read view retaining prior versions. Never run on production.

### 15.1. Preparing the Table

Run once:

~~~sql
CREATE TABLE lab_undo_demo (
    id INT NOT NULL,
    value_text VARCHAR(100) NOT NULL,
    counter_value INT NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

INSERT INTO lab_undo_demo (id, value_text, counter_value)
VALUES
    (1, 'initial', 0),
    (2, 'initial', 0);
~~~

### 15.2. Step 1 — Session A Creates a Read View

In Session A:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT *
FROM lab_undo_demo
WHERE id = 1;
~~~

The first SELECT creates a consistent read view. Keep transaction A open so the snapshot stays active.

### 15.3. Step 2 — Session B Updates and Commits

In Session B:

~~~sql
UPDATE lab_undo_demo
SET value_text = 'updated-1',
    counter_value = counter_value + 1
WHERE id = 1;

UPDATE lab_undo_demo
SET value_text = 'updated-2',
    counter_value = counter_value + 1
WHERE id = 2;
~~~

With autocommit enabled, each UPDATE is a separate transaction. You can wrap them in one transaction if you want to observe multiple changes committing together:

~~~sql
START TRANSACTION;

UPDATE lab_undo_demo
SET value_text = 'updated',
    counter_value = counter_value + 1;

COMMIT;
~~~

Do not run both update variants if you want to keep results simple; choose one approach and note the commit timestamp.

### 15.4. Step 3 — Session A Re-Reads the Snapshot

Back in Session A:

~~~sql
SELECT *
FROM lab_undo_demo
WHERE id = 1;
~~~

Under REPEATABLE READ, Session A still sees the old snapshot version even though Session B committed new changes. Undo information enables reconstructing the older version.

### 15.5. Step 4 — Observing Transactions and the History List

From another administrative session:

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_mysql_thread_id,
    trx_isolation_level,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;

SHOW ENGINE INNODB STATUS\G
~~~

Locate transaction A and note History list length. Because the lab dataset is tiny, the history list may not climb noticeably enough to chart; the goal is confirming the read view exists and understanding why purge must retain required history.

### 15.6. Step 5 — Ending the Read View

In Session A:

~~~sql
COMMIT;
~~~

Or use ROLLBACK if you do not want to keep any changes from Session A. When the transaction ends, the read view is released. Purge can advance once no other read view needs those older versions.

Check again:

~~~sql
SHOW ENGINE INNODB STATUS\G
~~~

History list length may decrease according to background purge cadence, not necessarily dropping to 0 instantaneously.

### 15.7. Step 6 — Observing Undo Tablespaces and Metrics

~~~sql
SELECT
    NAME,
    COUNT,
    STATUS
FROM information_schema.innodb_metrics
WHERE NAME = 'trx_rseg_history_len';

SELECT
    NAME,
    SPACE_TYPE,
    FILE_SIZE,
    ALLOCATED_SIZE
FROM information_schema.innodb_tablespaces
WHERE SPACE_TYPE = 'Undo';
~~~

Record the metrics and explain why undo files may remain large even after the history list drops.

### 15.8. Step 7 — Cleaning Up the Lab Table

Ensure both sessions have finished their transactions, then:

~~~sql
DROP TABLE lab_undo_demo;
~~~

Drop only the lab table just created.

**Target outcome:** explain how undo records serve rollback and MVCC; observe an old read view reading prior versions; locate long-lived transactions; read History list length; distinguish purge from undo tablespace truncation.

## 16. Operations and Alerting Workflow

An undo/purge monitoring dashboard should include these metrics and context:

- History list length over time, growth rate, and drain rate.
- Oldest transaction and its isolation level.
- Open transaction counts and idle transactions in connection pools.
- Row counts modified by large transactions.
- Undo tablespace size and file growth trends.
- UPDATE/DELETE rates and maintenance batch jobs.
- Server CPU/I/O and consistent read query latencies.

### 16.1. Trend-Based Alerting

Alert when the history list grows continuously over multiple intervals, exceeds operational baselines, or coincides with rapid undo tablespace growth. Combine with oldest transaction age to distinguish:

- Purge blocked by an old read view.
- Purge unable to keep up with undo generation rate.
- Undo file retaining allocated space while the history list is no longer rising.

### 16.2. When Purge Has Caught Up

After the transaction holding the read view finishes, monitor the history list draining gradually. Do not force tablespace truncation immediately upon seeing one low value. Evaluate auto-truncation mechanisms, undo tablespace state, and capacity requirements before altering configuration.

### 16.3. When History List Continues Rising

If no old read view exists yet the history list keeps growing, inspect write volume, purge threads, I/O, and heavy DELETE/UPDATE jobs. Only adjust purge threads or purge lag settings after confirming background processing capacity is the bottleneck.

## 17. Key Takeaways

- Undo logs support rollback and reconstruct older versions for consistent reads; redo logs serve crash recovery.
- Insert undo is primarily needed to roll back INSERT operations; update undo may be needed after commit for MVCC.
- Undo records are managed in undo logs and rollback segments; undo tablespaces store rollback segments configured accordingly.
- InnoDB uses read views to determine which versions a consistent read is permitted to see.
- REPEATABLE READ typically keeps the same read view from the first consistent read until the transaction ends; READ COMMITTED creates a fresh snapshot per consistent read statement.
- History list length reflects undo history awaiting purge; it is not row count, transaction count, or exact file size.
- Purge cleans up undo history and delete-marked records only when no read view needs them anymore.
- Idle transactions can still hold read views and block purge; investigate transaction age, isolation level, and read types.
- Increasing purge threads cannot bypass boundaries pinned by old read views.
- innodb_max_purge_lag throttles DML when the history list exceeds a threshold; it does not directly delete undo history.
- Undo tablespaces may retain allocated space after purge; truncation is a separate file-management operation performed only when conditions are met.
- Large DELETEs and long transactions generate substantial undo; batching is only appropriate when business logic accepts multiple commit boundaries.
- Monitor SHOW ENGINE INNODB STATUS, INFORMATION_SCHEMA.INNODB_TRX, INNODB_METRICS, and undo tablespace metadata.
- Never delete undo files directly via the filesystem and never treat undo logs as audit logs.

Undo logs, the history list, and purge are three parts of the same data version lifecycle in InnoDB. When a transaction holds a read view too long, purge must retain the history that snapshot still needs. By monitoring history list length alongside long-lived transactions, optimizing transaction lifecycles, and controlling write workloads, DBAs can address purge lag at its root cause and maintain stable performance.
