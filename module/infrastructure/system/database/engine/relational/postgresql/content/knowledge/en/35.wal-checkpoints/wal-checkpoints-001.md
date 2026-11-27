# Principles of Write-Ahead Logging and Recovery Guarantees in PostgreSQL

PostgreSQL can confirm that a transaction has COMMITted while the data pages containing that transaction's changes have not yet been written to the table files. This does not compromise transaction durability: before confirming a commit in synchronous mode, PostgreSQL must ensure the required WAL records have been flushed according to the durability policy.

This is the **Write-Ahead Logging (WAL)** principle: writing log records that describe changes before writing the corresponding data pages. WAL enables PostgreSQL to recover the database after a crash, supports physical replication, archives logs for recovery to a specific point in time, and reduces the number of data pages that must be synced on every COMMIT.

A **Checkpoint** coordinates writing dirty pages from shared buffers to data files and establishes the position from which crash recovery can begin redo. A checkpoint neither replaces WAL nor serves as a backup.

```text
Client sends COMMIT
       |
       v
Transaction generates WAL records
       |
       v
WAL buffers -> WAL files -> durable flush
       |
       v
PostgreSQL confirms COMMIT
       |
       | Data pages may still be dirty in shared buffers
       v
Checkpoint writes dirty pages to data files
       |
       v
After a crash: read latest checkpoint + replay required WAL
```

This lesson belongs to the **Database Engine Relational PostgreSQL** module, chapter **WAL and checkpoints**, on the topic **“Principles of Write-Ahead Logging and Recovery Guarantees”**.

---

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain Write-Ahead Logging and why PostgreSQL writes WAL before writing data pages.
2. Distinguish between WAL records, WAL buffers, WAL files/segments, and data files.
3. Explain LSN and the role of page LSN in recovery.
4. Describe the path of a transaction from UPDATE to COMMIT.
5. Distinguish between WAL write, WAL flush, and fsync.
6. Explain why PostgreSQL can confirm COMMIT before data pages are written to data files.
7. Understand the impact of synchronous_commit, fsync, full_page_writes, and wal_sync_method.
8. Distinguish between transaction durability on the primary and synchronous replication on the standby.
9. Explain shared buffers, dirty pages, the background writer, and the checkpointer.
10. Describe checkpoints, the redo point, and the scope of WAL that needs to be replayed.
11. Distinguish between timed checkpoints and checkpoints triggered by WAL pressure.
12. Understand the impact of checkpoint_timeout, max_wal_size, min_wal_size, and checkpoint_completion_target.
13. Explain full-page images and the risk of torn pages.
14. Describe crash recovery, redo, and how MVCC handles uncommitted transactions.
15. Distinguish between WAL recovery, backup/restore, and Point-in-Time Recovery (PITR).
16. Design WAL archiving and understand base backup requirements.
17. Understand timelines and how PostgreSQL continues WAL after recovery creates a new branch.
18. Distinguish between physical streaming replication, synchronous replication, and logical replication.
19. Understand replication slots, WAL retention, and the risk of running out of disk space.
20. Monitor WAL, checkpoints, the archiver, and replication using system views.
21. Use pg_waldump, pg_walinspect, and pg_controldata for appropriate diagnostics.
22. Design labs to inspect LSN, checkpoints, WAL generation, and archiving.
23. Plan verified backup/restore/PITR procedures, including RPO/RTO.
24. Identify configurations that weaken durability and limitations of storage hardware.

**Scope:** Modern PostgreSQL. Column names and structures of some statistics views change across major versions. Some monitoring examples need adjustment for the running version. Do not disable data-protection settings merely to boost throughput without evaluating data-loss and recovery risks.

---

## 2. Why Is WAL Needed?

A database must maintain critical properties when multiple transactions write concurrently and when the server can stop unexpectedly:

- A transaction whose commit has been confirmed must survive a failure according to the durability policy.
- The database must not leave data pages in an inconsistent state after restarting.
- Written but uncommitted changes must not become valid data simply because the server crashed.
- Recovery must have a way to determine which changes need to be replayed.

If PostgreSQL had to write every data page to storage immediately on every UPDATE statement, a transaction modifying many rows across many pages would cause heavy random I/O and high latency.

WAL solves this problem by writing a sequential log stream describing the changes required to restore page state. The data pages can be written out later.

### 2.1. The Write-Ahead Rule

**A WAL record describing a change must be flushed to durable storage before the data page containing the corresponding change is allowed to be written to storage.**

If power is lost mid-write of a data page, PostgreSQL can use WAL to redo the necessary changes.

### 2.2. Sequential Writes vs. Random Writes

WAL is written sequentially in log order, typically across WAL segments. Data pages may be scattered across many relation files. Sequential logging reduces the cost of syncing data on the commit path.

### 2.3. Commit Does Not Require Flushing All Data Pages

When a transaction commits (COMMIT), PostgreSQL must ensure the commit record and required WAL records are flushed according to the configuration. Heap/index pages can remain in shared buffers and be written out later.

### 2.4. What Features Does WAL Support?

- Crash recovery.
- Physical streaming replication.
- WAL archiving.
- Point-in-Time Recovery.
- Certain forms of online backup.
- Logical decoding and logical replication when wal_level is set appropriately.

### 2.5. WAL Is Not an SQL Audit Log

WAL is an internal log for recovery and replication. It is not a human-readable log of SQL statements for user auditing. If you want to audit SQL statements, use appropriate logging/auditing mechanisms; do not interpret WAL as a complete history of all business actions.

---

## 3. WAL Record, LSN, and WAL Segment

### 3.1. WAL Record

A WAL record describes the information needed for recovery or WAL consumers. Its contents depend on the operation type: heap page change, index page change, transaction commit, checkpoint, relation metadata, and many other record types.

Not every WAL record corresponds to an SQL statement. WAL generally does not store an UPDATE statement as text to be re-executed like an SQL script.

### 3.2. Log Sequence Number (LSN)

An **LSN** is a logical position in the WAL stream, typically represented in hexadecimal format:

```sql
SELECT pg_current_wal_lsn();
```

LSNs increase in the order WAL is generated. An LSN is a position in the WAL stream, not a timestamp and not a transaction number.

### 3.3. Page LSN

A data page has an LSN field in its page header representing the WAL position associated with the page's state. During recovery, PostgreSQL uses this information to decide whether a WAL record needs to be applied to the page or whether the page already reflects that change.

### 3.4. WAL Segment

WAL is stored in segment files inside the pg_wal directory. A common default segment size is 16 MB, though the size can be configured when building PostgreSQL and should not be assumed to be identical across all clusters.

The WAL filename encodes timeline, log, and segment number information. A WAL stream can span many consecutive segments.

### 3.5. WAL Buffers

PostgreSQL has a shared WAL buffers memory area to hold WAL records before writing them to WAL files. The wal_buffers parameter controls the size of this area, with a default value typically chosen automatically by PostgreSQL based on configuration.

### 3.6. WAL Buffers Are Not Shared Buffers

| Component | What Does It Hold? | Purpose |
| --- | --- | --- |
| Shared buffers | Table/index data pages | Cache pages and write dirty pages |
| WAL buffers | New WAL records | Buffer log records before writing WAL files |
| OS page cache | File blocks cached by the operating system | Support file I/O |
| WAL files | WAL stream on storage | Recovery/replication/archive |
| Relation files | Heap/index data pages | Persist database state long-term |

### 3.7. Viewing WAL LSN

```sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_current_wal_flush_lsn() AS flushed_lsn;
```

The two values may differ because newly generated WAL has not yet finished flushing. LSN function names may differ in older PostgreSQL versions; check the documentation for your exact major version.

---

## 4. The Write-Ahead Rule and Data Pages

Suppose a transaction updates a row on heap page number 120:

```text
Shared buffers:
  Heap page 120: new value, state DIRTY

WAL buffers:
  WAL record describing the change on page 120

Durability order:
  1. WAL record is flushed
  2. Data page 120 is then allowed to be written to storage
```

### 4.1. What If the Data Page Is Written Before WAL?

If the new page has already been written out while the WAL record describing the change is not yet durable, a crash could leave the database without the log needed to recover or verify the page state. This violates the write-ahead rule.

### 4.2. What If WAL Is Written Before the Data Page?

If WAL is durable while the data page has not yet been written, crash recovery can read WAL and redo the change to bring the page to the correct state.

### 4.3. Why Doesn't PostgreSQL Need to Write the Page Immediately on UPDATE?

WAL allows deferring data page writes and coalescing multiple changes on the same page before writing. This lets transaction commits avoid waiting for all data files to be updated.

### 4.4. The Checkpointer Obeys the Write-Ahead Rule

Before writing a dirty data page, PostgreSQL ensures that WAL up to the corresponding page LSN has been flushed. This is a mandatory condition in the storage mechanism.

### 4.5. Durability Depends on Actual Storage

PostgreSQL can issue a flush request, but the storage device or controller must honor the semantics reported to the operating system. If the hardware or virtualization layer claims a flush completed while data still sits only in a volatile cache, durability can be compromised.

---

## 5. Path of a Transaction to COMMIT

Consider this example:

```sql
BEGIN;

UPDATE banking.accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE banking.accounts
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
```

Conceptual flow:

```text
Client
  |
  | UPDATE
  v
Executor / heap & index operations
  |
  +--> Shared buffers: dirty heap/index pages
  |
  +--> WAL buffers: WAL records
              |
              v
         WAL writer / backend
              |
              v
         Write WAL to OS
              |
              v
         Flush WAL (fsync-equivalent)
              |
              v
         COMMIT record durable
              |
              v
         COMMIT response to client
```

### 5.1. Dirty Pages

The executor modifies data pages in shared buffers. These pages are marked dirty.

### 5.2. WAL Records

Write operations generate WAL records. WAL records can describe heap/index changes and transaction state.

### 5.3. Commit Record

When a transaction commits, PostgreSQL creates a commit record in WAL. With the default synchronous durability mode, the server must wait for the required WAL to be flushed before returning COMMIT success.

### 5.4. Data Pages May Not Be Written Yet

After COMMIT is confirmed, dirty pages may still reside in shared buffers. This is normal behavior, not an "unsaved" transaction.

### 5.5. Group Commit

Multiple transactions can wait together for a single WAL flush. PostgreSQL can batch multiple commit records into one flush, reducing the number of storage syncs per transaction.

### 5.6. A COMMIT Response Does Not Mean a Checkpoint Just Ran

A COMMIT response confirms the transaction commit according to durability settings. It does not mean all heap/index pages have been written to data files.

---

## 6. Write, Flush, and fsync

These three concepts are crucial:

- **Write**: transfers bytes from PostgreSQL buffers to the kernel/file-system layer or configured write path.
- **Flush**: requests that WAL bytes up to an LSN be pushed across the required durability boundary.
- **fsync** (or an equivalent method): asks the operating system/storage to synchronize data to the storage device according to the system's contract.

### 6.1. OS Page Cache

A successful write call may only mean the bytes were accepted into the kernel's page cache. That does not always mean the data is durable across a power loss.

### 6.2. WAL Flush

PostgreSQL must flush WAL before allowing the corresponding data page to be written out under the write-ahead rule and before confirming a synchronous commit.

### 6.3. Data Page Flush

Data pages are written out by the checkpointer/background writer. Related WAL must be flushed first.

### 6.4. Why Can Commit Be Fast?

Synchronous commit primarily waits for WAL to flush through the commit record, rather than forcing writes of all modified heap/index pages. Because WAL is a sequential stream, it is usually easier to sync than many scattered data pages.

### 6.5. The Storage Device Must Be Honest

Ensuring durability requires coordination among PostgreSQL, the operating system, filesystem, storage driver/controller, virtualization/cloud volume, and physical hardware with power-loss protection. A proper PostgreSQL configuration cannot compensate for a storage layer that falsely reports flush completion.

---

## 7. synchronous_commit: How Far Does a Transaction Wait?

The synchronous_commit parameter controls how far PostgreSQL waits for WAL on commit.

```sql
SHOW synchronous_commit;
```

### 7.1. Value on

On a primary without synchronous standbys configured, PostgreSQL waits for the local WAL flush to the required extent before confirming commit.

If synchronous replication is configured, on also waits for remote flush confirmation according to the synchronous replication mechanism.

### 7.2. Value off

PostgreSQL can return COMMIT success before the transaction's WAL is flushed locally. If the server crashes, recently confirmed transactions may be lost.

This does not mean the database will automatically become corrupt: PostgreSQL still maintains recovery consistency using durable WAL. However, the durability guarantee for the most recent commits is weakened.

### 7.3. Value local

In a synchronous replication setup, local waits for the local WAL flush but does not wait for remote standby acknowledgement.

### 7.4. Value remote_write

Waits for the standby to report that it has written WAL to the standby's OS according to the corresponding semantics, though not necessarily flushed to durable storage like remote_flush.

### 7.5. Value remote_flush

Waits for the synchronous standby to flush WAL to storage before the primary confirms commit.

### 7.6. Value remote_apply

Waits for the synchronous standby to replay WAL through the transaction so that changes are visible on the standby via the apply mechanism. This level generally increases latency because the standby must replay the WAL.

### 7.7. Comparison Table

| Value | Local primary flush | Remote standby write | Remote standby flush | Remote apply |
| --- | --- | --- | --- | --- |
| off | Does not wait for flush per commit | No | No | No |
| local | Yes | No | No | No |
| on without synchronous standby | Yes | No | No | No |
| on with synchronous standby | Yes | Acknowledgement per sync mode | Usually waits for remote flush | Not necessarily applied |
| remote_write | Yes | Yes | Not necessarily | No |
| remote_flush | Yes | Yes | Yes | No |
| remote_apply | Yes | Yes | Yes | Yes |

Details of the interaction between synchronous_commit and synchronous_standby_names should be verified against the documentation for your specific version and configuration.

### 7.8. Choosing Based on Data Requirements

- Financial transactions, orders, ledgers: typically prioritize strong durability.
- Reproducible telemetry data: off may be considered in a narrow scope if losing a small window of recent commits on crash is acceptable.
- Do not set off globally just to boost benchmark numbers.
- You can use SET LOCAL for a non-critical transaction if the application accepts the semantics.

Example in a controlled-scope transaction:

```sql
BEGIN;
SET LOCAL synchronous_commit = off;

INSERT INTO telemetry.events(event_type, recorded_at)
VALUES ('heartbeat', clock_timestamp());

COMMIT;
```

Do not apply this pattern to non-reproducible data or data requiring immediate commit guarantees.

---

## 8. fsync, full_page_writes, and Durability Settings

### 8.1. fsync

Having fsync enabled requests syncing critical data to storage. PostgreSQL recommends keeping it enabled on systems that require durability.

Disabling fsync can lead to unrecoverable database corruption after an OS crash or power loss. Do not treat this as routine tuning.

### 8.2. full_page_writes

After a checkpoint, the first time a page is modified, PostgreSQL can write a **full-page image (FPI)** to WAL, depending on full_page_writes and related conditions.

```sql
SHOW full_page_writes;
```

### 8.3. Torn Page

A data page can be larger than the atomic write unit of storage. If power fails mid-page write, the file may end up containing some new bytes and some old bytes.

An FPI lets recovery replace the torn page with a complete image and then continue redoing subsequent WAL records.

### 8.4. Do Not Disable full_page_writes Arbitrarily

Disabling full_page_writes when storage does not guarantee atomic page writes can increase the risk of page corruption after a crash. Only consider it in environments with explicit hardware guarantees and an expert-reviewed process.

### 8.5. wal_sync_method

This parameter selects the WAL synchronization method on the platform—for example, using fdatasync, fsync, or another OS-specific mechanism. PostgreSQL can choose an appropriate default.

Do not change it just because a method sounds faster; benchmarks must measure on real storage while preserving semantics.

### 8.6. wal_compression

Compresses full-page images to reduce WAL volume in suitable workloads, at the cost of CPU. Supported compression methods depend on build and version.

### 8.7. wal_log_hints

This parameter controls writing WAL for hint-bit changes when needed and can be a prerequisite for certain checksum modes and replication tooling. Check version documentation before enabling or disabling it.

### 8.8. Durability Configuration Set

A set of durability settings typically needs to be evaluated together:

- fsync = on.
- full_page_writes = on.
- synchronous_commit as required.
- Verified backups and WAL archive.
- Storage with reliable flush semantics.
- Monitoring of WAL disk usage and archive backlog.

---

## 9. Shared Buffers, Dirty Pages, and Background Writer

### 9.1. Shared Buffers

PostgreSQL caches table/index pages in shared buffers. During an UPDATE, affected pages can be modified in memory.

### 9.2. Dirty Page

A page that has been modified in memory but not yet written back to its data file is called a dirty page.

### 9.3. Background Writer

The background writer can write out some dirty buffers so backends do not have to handle all page writes themselves when free buffers are needed. Its goal relates to buffer availability and I/O smoothing.

### 9.4. Checkpointer

The checkpointer coordinates checkpoints and writes the dirty buffers required for a checkpoint to storage, while ensuring WAL is flushed before the data pages.

### 9.5. Backends Can Also Write Dirty Buffers

The checkpointer is not the only process writing data pages. Backends can also write buffers in certain situations. The background writer, checkpointer, and backends serve distinct roles.

### 9.6. WAL Writer

The WAL writer helps write WAL buffers out to WAL files periodically or under specific conditions. Backends can also perform WAL writes/flushes when needed, especially on the commit path.

### 9.7. Do Not Confuse the Background Writer with the Checkpointer

The background writer helps maintain buffer availability; the checkpointer executes checkpoints and ensures required pages are written so recovery can start from an appropriate redo point.

---

## 10. What Is a Checkpoint?

A **Checkpoint** is a synchronization point in the WAL/data-page lifecycle. PostgreSQL writes a checkpoint record into WAL and ensures that dirty buffers within the checkpoint's scope are written to data files according to the required rules.

A checkpoint establishes where redo starts during crash recovery and allows older WAL to be handled according to archive, replication, and other recovery conditions.

### 10.1. A Checkpoint Is Not a COMMIT

COMMIT confirms that a transaction is complete according to durability policy. A checkpoint is a cluster-level operation that syncs data pages and updates checkpoint state.

### 10.2. A Checkpoint Is Not a Backup

A checkpoint does not create an independently restorable copy of the database. For backup/restore, you need a base backup or logical dump along with an appropriate WAL workflow.

### 10.3. A Checkpoint Does Not Make Clients Wait for Every Transaction

Checkpoints run in the background based on schedule and WAL pressure. Normal transactions do not need to run CHECKPOINT after every COMMIT.

### 10.4. A Checkpoint Has a Redo Point

A checkpoint records information about the WAL position from which recovery may need to begin redo. WAL after the redo point may contain changes that need to be replayed to bring data pages to a consistent state.

### 10.5. Checkpoint Record and Checkpoint Completion

Conceptually, PostgreSQL writes a checkpoint record to WAL, flushes dirty pages according to the write-ahead rule, and updates control information when the checkpoint completes. If a crash happens mid-checkpoint, recovery uses the latest completed checkpoint recorded in the control file.

### 10.6. A Checkpoint Is More Than Just a Record

The checkpointer must perform the work of writing dirty buffers according to the rules, updating durable state, and managing the WAL/checkpoint lifecycle. Seeing a checkpoint record alone does not mean all checkpoint steps have completed.

---

## 11. How Does a Checkpoint Work?

```text
Checkpoint is triggered
       |
       v
Determine checkpoint state / redo point
       |
       v
Write checkpoint record to WAL
       |
       v
Flush dirty buffers following the write-ahead rule
       |
       v
Write data pages to data files
       |
       v
Update control information upon completion
```

Internal details may vary by version and checkpoint type, but the WAL-before-data rule must always hold.

### 11.1. Dirty Buffers Can Be Written Gradually

A checkpoint does not necessarily write all pages in a single burst. PostgreSQL can spread the work across a target time interval.

### 11.2. WAL Does Not Wait for a Checkpoint to Be Written

WAL is written continuously as transactions generate records. A checkpoint is not the only time WAL is flushed.

### 11.3. Timed Checkpoints

checkpoint_timeout defines the maximum time interval between scheduled timed checkpoints, subject to version limits and behavior.

### 11.4. Checkpoints Triggered by WAL Volume

If WAL is generated rapidly and exceeds the configured threshold, PostgreSQL may request an earlier checkpoint to recycle WAL segments.

### 11.5. Manual CHECKPOINT

The command:

```sql
CHECKPOINT;
```

requests an immediate checkpoint. This is an administrative command requiring appropriate privileges (superuser or a role granted pg_checkpoint, depending on version). Do not run it periodically from an application after each batch.

---

## 12. Redo Point and Recovery Scope

Suppose a checkpoint completes at LSN C. Afterwards, transactions continue generating WAL:

```text
WAL timeline
------------------------------------------------------------>
       C                LSN D                 LSN E
       |                  |                     |
  Checkpoint         UPDATE page A         COMMIT transaction
  redo point         UPDATE page B
```

If a crash occurs after LSN E while data pages A/B have not yet been completely written to data files, recovery reads WAL from the appropriate redo point and replays the required changes.

### 12.1. Not All WAL Since Database Creation Must Be Replayed

Checkpoints bound the redo scope required for crash recovery on the same timeline/cluster.

### 12.2. Recovery May Need WAL After the Checkpoint

Data pages may not yet contain post-checkpoint changes. WAL provides the information to replay them.

### 12.3. Page LSN Helps Avoid Unnecessary Redo

If a page already has a sufficiently recent LSN, recovery can recognize that the record is already reflected on the page and avoid reapplying it unnecessarily.

### 12.4. Redo Is Not Re-Executing SQL

Recovery processes WAL records at the storage/internal-operations level, rather than re-running original client SQL statements.

### 12.5. A New Checkpoint Does Not Always Delete Old WAL Immediately

WAL may still be needed for archiving, replication slots, standbys, backups, or recovery. Only when no retention requirement remains and internal conditions permit can segments be recycled or removed.

---

## 13. Timed Checkpoints vs. WAL-Pressure Checkpoints

### 13.1. Timed Checkpoint

A checkpoint triggered when the checkpoint_timeout interval elapses.

### 13.2. Requested Checkpoint

A checkpoint requested early due to WAL volume exceeding the target, a manual command, or certain operational events.

### 13.3. Checkpoints Too Frequent

Overly frequent checkpoints can increase data-page write I/O, increase full-page images in WAL after each checkpoint, cause write bursts if work is not smoothed, and increase storage write amplification.

### 13.4. Checkpoints Too Infrequent

Less frequent checkpoints can reduce checkpoint overhead and FPI frequency in some workloads, but can enlarge the WAL redo scope after a crash, increase retained WAL volume, lengthen crash recovery, and increase disk pressure if max_wal_size is not sized appropriately.

### 13.5. Do Not Tune Checkpoints by a Single Metric

You must balance recovery time objective, WAL volume, storage throughput, workload spikes, and archive/replication requirements.

---

## 14. Key Checkpoint Parameters

### 14.1. checkpoint_timeout

The maximum time between scheduled timed checkpoints. A common default is 5 minutes, but confirm on your cluster:

```sql
SHOW checkpoint_timeout;
```

### 14.2. max_wal_size

The target WAL size at which PostgreSQL considers triggering an earlier checkpoint. This is **not an absolute hard limit** on pg_wal size.

WAL can exceed this level due to archive backlogs, replication slots, workload spikes, or other retention conditions.

### 14.3. min_wal_size

The minimum WAL volume PostgreSQL tries to retain/recycle to reduce repeated creation and deletion of segment files.

### 14.4. checkpoint_completion_target

The target fraction of the checkpoint interval over which checkpoint writes are spread. Higher values spread writes more evenly and reduce bursts, but do not eliminate the need for adequate I/O capacity.

### 14.5. Viewing the Settings

```sql
SELECT
    name,
    setting,
    unit,
    source
FROM pg_catalog.pg_settings
WHERE name IN (
    'checkpoint_timeout',
    'max_wal_size',
    'min_wal_size',
    'checkpoint_completion_target',
    'full_page_writes',
    'wal_compression',
    'wal_buffers',
    'synchronous_commit',
    'fsync'
)
ORDER BY name;
```

### 14.6. A Starting Point Is Not a Prescription

A system can start with defaults, measure checkpoint frequency and WAL volume, and adjust incrementally. Do not copy another system's configuration when storage, transaction sizes, and recovery targets differ.

### 14.7. max_wal_size Is Not a Disk Quota

Monitor free space on the filesystem hosting pg_wal and the archive. A slot held open for a long time can cause WAL to grow far beyond max_wal_size.

---

## 15. Full-Page Images and Checkpoints

### 15.1. Why Are FPIs Needed?

When PostgreSQL writes a page to storage, a failure can leave the page only partially written. If WAL only contained records describing small delta changes, recovery might lack enough information to repair the torn page.

### 15.2. Writing a Full-Page Image

When full_page_writes is enabled, PostgreSQL can write a complete image of a page to WAL the first time the page is modified after a checkpoint, according to the corresponding rules and conditions.

### 15.3. FPIs Increase WAL Volume

After a checkpoint, many pages modified for the first time can generate FPIs. Overly frequent checkpoints can cause FPIs to be generated more often.

### 15.4. wal_compression

Compressing FPIs can reduce WAL bytes when page images compress well. It consumes CPU, and effectiveness depends on data and page contents.

### 15.5. An FPI Is Not a Full Database Snapshot

An FPI is a page image inside WAL to support recovery. It is not an independent backup of the entire database.

### 15.6. Page Checksums Differ from FPIs

Checksums help detect page corruption when reading a page. FPIs help recover certain torn-page cases via WAL. The two mechanisms have related goals but do not replace each other.

---

## 16. Crash Recovery: PostgreSQL Restarting After a Failure

Suppose the server shuts down abruptly:

- Some transactions committed and their WAL was flushed.
- Some data pages were not yet written to data files.
- Some in-flight transactions were uncommitted.
- Some page writes may have been interrupted.

On restart, PostgreSQL performs crash recovery.

### 16.1. Reading Control Information

PostgreSQL identifies the latest checkpoint and required state from the control file and WAL.

### 16.2. Starting Redo

PostgreSQL reads WAL from the required position and replays changes not yet fully reflected in data pages.

### 16.3. Page LSN

Recovery checks the page's LSN to determine which records need to be applied. This supports safe replay.

### 16.4. Transaction Status and Visibility

WAL contains transaction completion information. A transaction without a valid commit record is not treated as committed merely because some of its tuples were written to the heap.

### 16.5. PostgreSQL Does Not Use a Traditional Undo Log for Every UPDATE

PostgreSQL relies on MVCC tuple versions and transaction visibility. After a crash, uncommitted changes remain invisible; dead tuple cleanup is handled later according to vacuum rules. Do not think of recovery as running an SQL undo script statement by statement.

### 16.6. The Server Opens Normal Connections Only After Proper Recovery

If required WAL is missing or corruption cannot be repaired by the recovery mechanism, PostgreSQL may fail to start. Do not bypass errors just to force the server into accepting connections.

---

## 17. Crash Recovery and Transaction Durability

### 17.1. Committed Transaction with Synchronous Commit

If the WAL commit record was durably flushed, recovery can restore the changes even if data pages were not written before the crash.

### 17.2. Uncommitted Transaction

The transaction's changes are not treated as committed. Tuple versions may exist physically on disk, but are not visible to new transactions under MVCC status.

### 17.3. Transaction Committed with synchronous_commit=off

A commit response may have been sent before the local WAL flush. If a crash occurs at that moment, some recent transactions may disappear after recovery. The application must accept this possibility when enabling that mode.

### 17.4. fsync=off

This is a much more severe risk: the system can lose or corrupt data in ways that cannot be recovered using existing WAL alone. Do not use this for production optimization.

### 17.5. Commit Response Lost on the Network

A client may not know whether a transaction committed if the connection drops right as the server processes COMMIT. This is an **ambiguous outcome** at the application layer. Design idempotency/business keys for safe retries; do not assume a network error means the transaction rolled back.

### 17.6. End-to-End Durability

Ensuring transaction durability requires database configuration, storage flush correctness, backup/restore, and operational procedures. A successful COMMIT does not replace a backup.

---

## 18. WAL Archiving

**WAL archiving** is the copying of completed WAL segments to an external archive outside pg_wal.

```sql
SHOW archive_mode;
SHOW archive_command;
SHOW archive_timeout;
```

### 18.1. Enabling Archive Mode

archive_mode must be configured appropriately and typically requires a restart to change. An archive_command or archive library is configured to transfer completed WAL segments to storage.

### 18.2. Archive Command

An illustrative conceptual example:

```conf
archive_mode = on
archive_command = 'archive-helper %p %f'
```

Where %p is the path to the source WAL file, %f is the WAL filename, and archive-helper is a script/tool provided by the deployment.

This is a placeholder, not an existing executable. A production helper must verify idempotency, filesystem permissions, copy errors, checksums, handling of pre-existing files, atomic publish, alerting, and durable storage. Never report success before the archive has been safely persisted according to contract.

### 18.3. When Should Archive Command Return Success?

The archive command must report success only after the segment is safely stored. If it reports success prematurely, PostgreSQL may allow recycling the WAL segment before the archived copy is truly durable.

### 18.4. Archive Backlog

If the archive command fails repeatedly, WAL segments can accumulate in pg_wal, filling up the filesystem.

### 18.5. pg_stat_archiver

```sql
SELECT *
FROM pg_catalog.pg_stat_archiver;
```

Typically useful fields include archived count, failed count, last archive time, and last archived file; check the view schema for your version.

### 18.6. archive_timeout

You can force a WAL segment switch at an interval to archive changes in low-write workloads. This can create extra segment/archive overhead. Do not set it too low without a clear need.

---

## 19. Base Backup and Point-in-Time Recovery (PITR)

A WAL archive alone is insufficient to recover a database from total loss of the data directory. You need a suitable **base backup** and a continuous sequence of WAL from the backup's required starting point to the recovery target.

### 19.1. Base Backup

A base backup is a consistent physical copy of the cluster over a time span. It can be created with pg_basebackup or a PostgreSQL-compatible backup solution.

### 19.2. WAL During Backup

An online backup requires sufficient WAL to make the backup consistent. Backup tools coordinate with PostgreSQL to capture the necessary WAL information.

### 19.3. PITR

PITR enables recovery to a target timestamp, transaction ID, restore point, or LSN supported by your version.

```text
Base backup at time T0
       |
       v
Restore data directory
       |
       v
Provide continuous WAL archive from T0
       |
       v
PostgreSQL recovery / replay WAL
       |
       v
Stop at recovery target T1
       |
       v
Database at state T1
```

### 19.4. PITR Fails If Any Intermediate WAL Is Missing

If a required segment is lost, the recovery chain breaks. An archive directory with thousands of files is useless if the exact needed segment is missing.

### 19.5. Backups and Archives Must Separate Failure Domains

If base backups and WAL archives reside in the same storage account or region and it is deleted or damaged, recoverability can be lost all at once. Consider replication, immutability, access controls, and offsite copies.

### 19.6. Testing Restores

A backup logged as successful does not prove it can be restored. Regularly spin up a recovery environment, restore a base backup, replay WAL to a target, and verify application data.

---

## 20. Conceptual PITR Configuration

A recovery target requires configuring the restore process according to your PostgreSQL version. Common parameters in a recovery configuration:

```conf
restore_command = 'restore-helper %f %p'
recovery_target_time = '2026-11-14 09:30:00+07'
recovery_target_action = 'pause'
```

restore-helper is a placeholder for the program that fetches segments from the archive. In modern versions, requesting archive recovery typically involves signal files such as recovery.signal; standby setup uses a different signal file. Do not manually create or delete signal files outside the documented procedure for your version.

### 20.1. restore_command

Invoked by PostgreSQL to fetch a WAL segment from the archive. The command must return appropriate exit codes whether the file exists or not, and safely handle filenames and paths.

### 20.2. recovery_target_time

Stops or takes action at the target timestamp. The timezone must be specified clearly to avoid confusing local time and UTC.

### 20.3. recovery_target_lsn

LSN can be used as a recovery target when you need to stop at a specific WAL position and know the target LSN.

### 20.4. recovery_target_name

A named restore point previously created with pg_create_restore_point can be used.

### 20.5. recovery_target_action

Options such as pause, promote, or shutdown determine behavior once the target is reached; supported values depend on version.

### 20.6. After Reaching the Target

If promoted so the database accepts new writes, PostgreSQL creates a new timeline. Do not continue writing onto the old timeline as if no recovery branch occurred.

---

## 21. Timeline: When Recovery Creates a New WAL Branch

Timelines distinguish different WAL histories after a failover or PITR promotion.

```text
Timeline 1
Base backup
   |
   +---- WAL ---- WAL ---- Recovery target
                              |
                              | Promote
                              v
Timeline 2
                         New WAL ---- New WAL
```

### 21.1. Why Are Timelines Needed?

After promoting a standby or completing PITR and resuming writes, the new WAL history can diverge from the old timeline.

### 21.2. Timeline History File

PostgreSQL creates a timeline history file describing the timeline/ancestor relationship and the branch point.

### 21.3. Backups Must Retain History Files

Archive management must preserve timeline history files alongside WAL segments so recovery follows the right branch.

### 21.4. Do Not Rely Only on WAL Segment Numbers

Two timelines can have similar segment numbers while belonging to different histories. Archive tooling must preserve full filenames and never overwrite segments from another timeline.

### 21.5. Failover and Split Brain

HA orchestration must ensure only one primary accepts writes at any time. Timelines support recovery history, but do not prevent split brain on their own if failover orchestration is misconfigured.

---

## 22. Physical Streaming Replication and WAL

Physical replication streams WAL from the primary to a standby so the standby replays physical cluster changes.

### 22.1. Primary Sends WAL

WAL sender processes send the WAL stream to the standby over the replication protocol.

### 22.2. Standby Receives and Replays

The standby WAL receiver receives and writes WAL, and the startup process replays records to update data pages.

### 22.3. Standby Does Not Re-Run SQL

A physical standby applies WAL records; it does not re-execute the original UPDATE statements.

### 22.4. Standby Can Lag at Multiple Stages

- Primary generates WAL.
- WAL is sent.
- Standby receives/writes WAL.
- Standby replays WAL.

The corresponding LSNs help distinguish network lag from replay lag.

### 22.5. Viewing Replication Status

```sql
SELECT
    application_name,
    client_addr,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    sync_state
FROM pg_catalog.pg_stat_replication;
```

Check view names and columns for your version.

### 22.6. Do Not Confuse Standby Receiving WAL with Standby Replaying It

A standby may have received and flushed WAL without having applied it yet. Queries on the standby may not see the latest data while replay lag exists.

---

## 23. Synchronous Replication and Commit Acknowledgement

Synchronous replication allows the primary to wait for one or more standbys to confirm WAL according to policy.

### 23.1. synchronous_standby_names

This setting defines which standbys are considered synchronous and the selection/quorum rules.

Illustrative example:

```conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
```

Check syntax and FIRST/ANY options for your version.

### 23.2. RPO Can Be Reduced

If the primary confirms commit after a standby flushes WAL per configuration, certain primary-loss scenarios can fail over to the standby without losing commits confirmed under that policy.

### 23.3. Increased Latency

The primary must wait for remote acknowledgement, so network and standby storage latency can directly impact commit latency.

### 23.4. Standby Disconnects

When no eligible standby remains, commit behavior depends on synchronous replication configuration, timeouts, and operational choices. You must clearly understand the availability trade-off.

### 23.5. Synchronous Replication Does Not Replace Backups

A logical mistake like an accidental DELETE will be replicated to the standby. Backup/PITR is still required to return to a point before the mistake.

---

## 24. Logical Replication and WAL Level

Logical replication uses logical changes extracted from WAL rather than only replaying physical page changes on the same cluster layout.

### 24.1. wal_level

WAL levels determine what information is written for recovery, replication, and logical decoding. replica is usually sufficient for physical replication and WAL archiving; logical writes extra information needed for logical decoding. minimal has limitations that make it unsuitable for typical archive recovery or streaming replication.

```sql
SHOW wal_level;
```

### 24.2. Logical Decoding

Logical decoding turns WAL into a stream of logical changes that plugins/output formats can consume.

### 24.3. Logical Replication Is Not Physical Recovery

A logical subscriber can have its own schema, indexes, and data layout. Logical WAL synchronizes data between objects rather than restoring the entire physical cluster verbatim.

### 24.4. Replica Identity

UPDATE/DELETE in logical replication requires identifying rows using replica identity settings and an appropriate index. This is distinct from HOT updates, even though both relate to update semantics.

### 24.5. WAL Volume Can Increase

wal_level=logical and logical decoding requirements can produce different WAL/retention workloads than physical replication alone. Measure on your actual workload.

---

## 25. Replication Slots and WAL Retention

Replication slots retain WAL required by consumers so a standby or logical subscriber does not lose segments before reading them.

### 25.1. Viewing Slots

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    wal_status,
    safe_wal_size
FROM pg_catalog.pg_replication_slots;
```

Some columns exist only in newer PostgreSQL versions; adjust the SELECT to match your cluster's view schema.

### 25.2. Inactive Slots

A stopped logical consumer can leave a slot inactive for a long time. Required WAL continues to be retained, potentially causing pg_wal to grow.

### 25.3. max_slot_wal_keep_size

Limits the amount of WAL retained for replication slots according to version configuration. Once exceeded, the slot may become unusable for catching up and the consumer must be handled or reinitialized.

### 25.4. wal_keep_size

Retains a configured minimum amount of WAL for standbys, but does not replace full replication slots or archiving.

### 25.5. max_wal_size Does Not Strictly Cap Slot Retention

A replication slot or archive failure can cause WAL to grow past max_wal_size. You must monitor disk usage and slot lag.

### 25.6. Do Not Drop Active Slots Arbitrarily

Dropping a slot can prevent a consumer from obtaining needed WAL. Verify owner, purpose, active status, and resync capability before making changes.

---

## 26. WAL Disk Usage and Filesystem Exhaustion Risk

WAL can accumulate due to failing archive commands, stalled replication slots, prolonged standby outages, unconfirmed logical consumer flushes, checkpoint/WAL generation pressure, workload bursts, or backup/replication settings retaining WAL for long periods.

### 26.1. Monitoring the pg_wal Directory

pg_wal disk usage is a critical operational metric. Use OS/monitoring tools to track free disk space rather than relying only on max_wal_size.

### 26.2. Never Manually Delete WAL Files

Never manually delete files inside pg_wal to free up space. Doing so can render the cluster unable to crash-recover or break replication/recovery.

### 26.3. Address the Root Cause

- Archive failure: fix destination, permissions, or network.
- Slot retention: identify the consumer and its progress.
- Standby offline: restore or reinitialize following procedure.
- WAL generation spike: evaluate workload and checkpoint settings.
- Disk nearly full: expand capacity or handle retention as planned.

### 26.4. Trend-Based Alerting

A pg_wal filesystem at 60% usage and growing rapidly can be more dangerous than a steady 80%. Alerts should factor in growth rate, remaining capacity, and estimated time to full.

---

## 27. WAL Statistics and Checkpoint Monitoring

### 27.1. pg_stat_wal

On versions supporting this view (PostgreSQL 14 and later):

```sql
SELECT *
FROM pg_catalog.pg_stat_wal;
```

Provides WAL records, full-page images, bytes, buffers full, and write/sync statistics depending on version.

### 27.2. pg_stat_checkpointer

Newer PostgreSQL versions (PostgreSQL 17 and later) provide a dedicated view for the checkpointer:

```sql
SELECT *
FROM pg_catalog.pg_stat_checkpointer;
```

Older versions expose some checkpoint statistics in pg_stat_bgwriter. Do not use column names from newer versions against older clusters without checking.

### 27.3. pg_stat_bgwriter

```sql
SELECT *
FROM pg_catalog.pg_stat_bgwriter;
```

This view provides information on the background writer and, depending on version, checkpoint statistics.

### 27.4. pg_stat_archiver

```sql
SELECT *
FROM pg_catalog.pg_stat_archiver;
```

Tracks archive successes/failures and the most recent archive time and file.

### 27.5. Replication Views

- pg_stat_replication: primary side.
- pg_stat_wal_receiver: standby side.
- pg_replication_slots: retention state.
- pg_stat_database: aggregated transaction/I/O counters.

### 27.6. Measuring WAL Generation Delta

You can snapshot pg_stat_wal before and after an interval and calculate the wal_bytes delta. Counters are cumulative and can be reset; record timestamps and stats_reset for accurate comparisons.

### 27.7. Do Not Judge Solely by Checkpoint Count

Inspect timed vs. requested checkpoints, write/sync times, buffers written, WAL bytes, disk latency, checkpoint warnings, and application latency.

---

## 28. Checking LSN and WAL Progress

### 28.1. Primary Current/Flush LSN

```sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_current_wal_insert_lsn() AS insert_lsn,
    pg_current_wal_flush_lsn() AS flush_lsn;
```

### 28.2. Computing Bytes Between Two LSNs

```sql
SELECT pg_wal_lsn_diff(
    '0/5000000',
    '0/4000000'
) AS wal_bytes;
```

Illustrative values; in production, pass LSNs collected from the same compatible WAL history.

### 28.3. Standby Replay LSN

On the standby:

```sql
SELECT
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn(),
    pg_last_xact_replay_timestamp();
```

These functions help track receive and replay progress. If no new WAL arrives, the replay timestamp may appear old even though the standby has no error.

### 28.4. Primary and Standby LSNs

Do not subtract LSNs from two incompatible timelines or clusters as if they belonged to the same stream. You must know the timeline and replication relationship.

### 28.5. An LSN Is Not a Clock

An LSN distance does not directly tell you how many seconds of lag exist without knowing the WAL generation rate and corresponding measurement window.

---

## 29. WAL Inspection Tools

### 29.1. pg_waldump

pg_waldump is a command-line utility that reads and displays WAL record information for diagnostics.

```bash
pg_waldump --path=/path/to/pg_wal --start=0/4000000 --end=0/5000000
```

Option names and archive-reading support depend on version. Use a binary compatible with the cluster and WAL format.

### 29.2. pg_walinspect

The pg_walinspect extension provides SQL functions to inspect WAL records in supported versions.

```sql
CREATE EXTENSION IF NOT EXISTS pg_walinspect;
```

Refer to your version's documentation to choose appropriate functions and arguments. Do not assume every cluster has this extension installed.

### 29.3. pg_controldata

The pg_controldata utility displays control file information, including checkpoint and cluster state. It runs against the data directory with appropriate OS permissions and should be used in controlled operational environments.

### 29.4. Never Edit WAL Records

WAL is critical internal data. Never manually edit bytes or rename/delete segments to "fix errors."

### 29.5. pg_resetwal Is a Last Resort

pg_resetwal can reset WAL/control information in special corruption scenarios, but risks losing transaction history and creating a logically inconsistent database. Use it only under expert recovery guidance, after taking a copy of the data directory and assessing potential data loss. Never use it to free disk space or clear an archive backlog.

---

## 30. WAL, Unlogged Tables, and Temporary Tables

### 30.1. Logged Tables

Regular tables are WAL-logged to support crash recovery and physical replication.

### 30.2. UNLOGGED Tables

UNLOGGED tables reduce WAL for table data according to PostgreSQL semantics, but their data is not preserved across crashes like logged tables and is not replicated to physical standbys like normal logged data. Associated indexes and metadata behave according to the relation type.

Do not use UNLOGGED for ledgers, orders, or non-reproducible data just to cut down on WAL.

### 30.3. Temporary Tables

Temporary tables have session-scoped semantics and do not require durability or replication like regular tables. They suit temporary data that can be regenerated.

### 30.4. Do Not Confuse Less WAL with Higher Durability

Less WAL does not mean more durable data. For critical data, prioritize proper recovery semantics over eliminating logging.

---

## 31. WAL and Data Security

WAL can contain enough information to reconstruct data changes, including row and page contents. Archives may retain old data for extended periods.

- Restrict which users/roles can read WAL archives. Never place an archive directory in a public location or allow every application account to read it.
- Consider encrypting disks, object storage, or backup repositories. PostgreSQL does not automatically encrypt every WAL archive via a single simple setting across all deployments.
- WAL retention must satisfy backup/PITR and replication needs while also having a secure deletion policy.
- Archive credentials, cloud storage keys, and backup access tokens must be managed as secrets.
- WAL does not replace audit logs containing user/session/object/action metadata.

---

## 32. Lab: Inspecting WAL LSN Before and After Operations

This lab uses a dedicated schema wal_lab.

> **Warning:** Run only on an authorized test database. The DROP command in this lab deletes the named schema and all objects inside it.

### 32.1. Create the Schema and Table

```sql
DROP SCHEMA IF EXISTS wal_lab CASCADE;
CREATE SCHEMA wal_lab;

CREATE TABLE wal_lab.events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_type TEXT NOT NULL,
    payload TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
```

### 32.2. Record LSN Before the Operation

```sql
SELECT pg_current_wal_lsn() AS before_lsn;
```

Record the result.

### 32.3. Insert a Batch

```sql
INSERT INTO wal_lab.events (event_type, payload)
SELECT
    'heartbeat',
    'device-' || g::TEXT
FROM generate_series(1, 1000) AS g;
```

### 32.4. COMMIT and Fetch LSN After

With autocommit enabled, the INSERT commits upon completion. Then run:

```sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_current_wal_flush_lsn() AS flushed_lsn;
```

### 32.5. Calculate the Delta

Compare before/after LSNs using pg_wal_lsn_diff with the two recorded values:

```sql
SELECT pg_wal_lsn_diff(
    '0/LSN_AFTER',
    '0/LSN_BEFORE'
) AS generated_bytes;
```

Replace the placeholders with actual LSNs; the example above is not meant to be run verbatim.

### 32.6. Why Does the Delta Not Equal the Exact Row Data Size?

WAL also includes record headers, transaction records, index changes, full-page images, alignment padding, and other system changes. WAL generation may also reflect concurrent cluster activity.

### 32.7. Run Multiple Times

Record baseline and deltas during a quiet workload period to approximate the amount of WAL generated by the lab.

---

## 33. Lab: Manual Checkpoint and Observing Checkpoint State

### 33.1. View Settings

```sql
SHOW checkpoint_timeout;
SHOW max_wal_size;
SHOW checkpoint_completion_target;
```

### 33.2. Record LSN Before Checkpoint

```sql
SELECT pg_current_wal_lsn();
```

### 33.3. Request a Checkpoint

```sql
CHECKPOINT;
```

This command requires appropriate privileges and can generate I/O. Run only in a lab or an approved maintenance window.

### 33.4. Read LSN Again

```sql
SELECT
    pg_current_wal_lsn(),
    pg_current_wal_flush_lsn();
```

A checkpoint can generate a WAL record and update state; do not expect the LSN to reset to 0 or WAL files to vanish immediately.

### 33.5. Check Checkpoint Stats

On versions with pg_stat_checkpointer:

```sql
SELECT *
FROM pg_stat_checkpointer;
```

On older versions, check checkpoint-related columns in pg_stat_bgwriter.

### 33.6. Manual Checkpoints Are Not Routine Application Operations

Do not execute CHECKPOINT after every transaction or request. It can trigger heavy write I/O and disrupt the checkpoint schedule tuned for the workload.

---

## 34. Lab: Observing Archive and WAL Switch

This lab requires a cluster with WAL archiving enabled and a safely configured archive destination. If you lack server configuration privileges, inspect existing state in read-only mode.

### 34.1. Check Configuration

```sql
SHOW archive_mode;
SHOW archive_command;
SHOW archive_timeout;
```

### 34.2. View Archiver Statistics

```sql
SELECT *
FROM pg_stat_archiver;
```

### 34.3. Request a WAL Switch

In a lab with a properly configured archive:

```sql
SELECT pg_switch_wal();
```

This function switches to a new WAL segment; the old segment can be archived once eligible. Do not call it repeatedly to force archiving every few seconds in production.

### 34.4. Verify Archive Destination

Use appropriate OS/storage tools to verify the file arrived, has valid size/checksum, and was not overwritten. Do not rely on a single SQL query alone.

### 34.5. Test the Failure Path

In a test environment, simulate the archive destination becoming temporarily unreachable and observe failed counts, failure timestamps, and disk growth. Restore the destination and verify the archiver catches up.

Never intentionally break production archiving to perform a lab exercise.

---

## 35. Lab: Testing PITR in an Isolated Environment

PITR requires OS access and a base backup. It cannot be completed solely via SQL inside a database session.

### 35.1. Preparation

1. Create an isolated PostgreSQL lab cluster.
2. Enable archive_mode and configure an archive destination.
3. Take a base backup using pg_basebackup or a compatible tool.
4. Confirm continuous WAL archiving.
5. Record the timestamp and a restore point.

### 35.2. Create a Restore Point

```sql
SELECT pg_create_restore_point('before_test_change');
```

Save the returned LSN along with the timestamp.

### 35.3. Create Test Data

```sql
INSERT INTO wal_lab.events(event_type, payload)
VALUES ('pitr-test', 'created-after-restore-point');
```

Record the timestamp/LSN and verify the row is present on the primary.

### 35.4. Restore an Isolated Copy

Use the base backup, WAL archive, and recovery target configuration to recover to the named restore point or recorded timestamp.

### 35.5. Verification

- Rows created before the restore point must exist.
- Rows created after the restore point must not appear if recovery stopped before them.
- The database must start in the expected state.
- Timeline/history must be preserved properly.
- The application must pass smoke tests.

### 35.6. Measure RTO

Measure the elapsed time from starting the restore until both database and application are ready. Do not measure only backup copy time.

### 35.7. Measure RPO

Determine the potential data-loss window based on the recovery target and how promptly WAL is archived/flushed. RPO is not automatically guaranteed simply because archive_mode is enabled.

---

## 36. Checkpoint Tuning by Workload

### 36.1. Write-Heavy Workloads

A continuous ingestion system can generate WAL quickly. Too small a max_wal_size can cause frequent requested checkpoints.

### 36.2. Burst Workloads

A large batch import can generate a lot of WAL in a short window, triggering early checkpoints. Monitor I/O and checkpoint statistics before and after batches.

### 36.3. Read-Heavy Workloads

With minimal writes, checkpoint pressure may be low. There is no need to raise all WAL settings simply because the system handles many queries.

### 36.4. Storage Throughput

Checkpoints write many dirty pages. Storage with low IOPS or throughput may fail to finish smoothly even with a high checkpoint_completion_target.

### 36.5. Recovery Time

Overly infrequent checkpoints can increase the amount of WAL to redo after a crash. Test recovery time against realistic data and volume.

### 36.6. Adjust One Parameter at a Time

1. Record baseline checkpoint and WAL metrics.
2. Determine whether timed or requested checkpoints dominate.
3. Review WAL generation rate and disk capacity.
4. Check full-page images.
5. Evaluate storage write latency.
6. Change a single parameter with a clear hypothesis.
7. Run a representative workload.
8. Measure commit latency, checkpoint duration, WAL bytes, and recovery time.
9. Keep or roll back based on data.

### 36.7. Do Not Force Checkpoints Too Quickly

A low checkpoint_completion_target concentrates writes more tightly. Setting it too low can cause I/O spikes. Defaults are generally a good starting point before collecting evidence.

---

## 37. Common WAL and Checkpoint Incidents

| Symptom | Possible Cause | Investigation Path |
| --- | --- | --- |
| pg_wal growing continuously | Archive failure, slot lag, standby offline | Archiver, slots, disk trend |
| Too many requested checkpoints | High WAL generation or low max_wal_size | Checkpoint stats, WAL rate |
| Increased commit latency | Slow storage flush, sync replication lag | WAL sync stats, standby state |
| Standby replay lag | Standby I/O/CPU bottleneck, WAL burst | receive/replay LSN, standby load |
| Archive falling behind | Destination/network/permissions | pg_stat_archiver, logs |
| Slow startup recovery | Large WAL replay volume, slow storage | Checkpoint interval, WAL size |
| Invalid WAL record | WAL corruption, storage/transfer issue | logs, archive checksum, hardware |
| Page checksum error | Page corruption | backup, storage, FPI/recovery evidence |
| Recent commits lost after crash | synchronous_commit=off, unreliable storage flush | durability settings, hardware |
| Database fails to start | WAL/control/data corruption or missing WAL | logs, backup, recovery plan |
| Disk full | Slot/archive retention or workload spike | pg_wal usage, archive, slots |
| Missing archive file | Retention/permission/tool bug | timeline, archive inventory |
| PITR stops early | Missing WAL segment or wrong target/timezone | archive continuity, target config |
| Standby requires resync | WAL recycled before standby caught up | slot, wal_keep_size, base backup |
| WAL volume spikes after checkpoint | Full-page images | pg_stat_wal, FPI counters |

### 37.1. Do Not Delete WAL to Fix Disk Full

If disk space runs out, address retention causes, expand disk, or clear archive/slot backlogs per procedure. Manually deleting WAL can make the cluster unrecoverable.

### 37.2. Do Not Run pg_resetwal as a First Step

Determine the root cause and preserve a copy of the data directory before considering extreme recovery actions.

### 37.3. Distinguish Archive Failure from Replication Lag

The archive destination and standby streaming are two separate WAL consumption paths. One can be healthy while the other is stalled.

### 37.4. Server Logs Are Key Evidence

Collect PostgreSQL logs around the time of failure, OS/storage logs, archive logs, and metrics. Do not infer the root cause from a disk usage alert alone.

---

## 38. Backup Strategy and Recovery Objectives

### 38.1. RPO

**Recovery Point Objective** is the maximum amount of data a business tolerates losing, typically expressed as a time interval or a data point.

### 38.2. RTO

**Recovery Time Objective** is the target time to restore service after an incident.

### 38.3. WAL Archive Interval Affects RPO

If WAL is archived only when a segment fills or per archive_timeout, the latest point recoverable from the archive depends on whether the segment has been safely archived and other conditions.

### 38.4. Base Backup Cadence Affects Recovery Cost

Fresher base backups reduce the amount of WAL to replay, at the expense of storage and backup bandwidth. Choose a cadence based on RTO, storage, and operational capacity.

### 38.5. Full Backups Do Not Replace WAL Continuity

A base backup alone does not allow PITR to arbitrary points in time. A continuous chain of WAL from the backup start/consistent point to the recovery target is required.

### 38.6. Logical Dumps Serve a Different Purpose

pg_dump creates a logical backup to restore schema/data by objects. It does not replace a physical base backup plus WAL archive for continuous physical PITR.

### 38.7. Practice Restores Regularly

A backup schedule is incomplete without restore drills, checksum verification, archive access checks, and up-to-date runbooks.

---

## 39. Settings to Review Before Making Changes

```sql
SELECT
    name,
    setting,
    unit,
    context,
    pending_restart,
    source
FROM pg_catalog.pg_settings
WHERE name = ANY (ARRAY[
    'wal_level',
    'wal_buffers',
    'wal_writer_delay',
    'wal_writer_flush_after',
    'wal_sync_method',
    'fsync',
    'full_page_writes',
    'wal_compression',
    'synchronous_commit',
    'checkpoint_timeout',
    'checkpoint_completion_target',
    'max_wal_size',
    'min_wal_size',
    'archive_mode',
    'archive_timeout',
    'wal_keep_size',
    'max_slot_wal_keep_size',
    'max_wal_senders',
    'max_replication_slots'
])
ORDER BY name;
```

### 39.1. Context

pg_settings.context indicates whether a parameter can be changed at session level, via reload, or requires a restart depending on version and configuration.

### 39.2. pending_restart

Indicates whether a configured value requires a restart to take effect in the corresponding cases.

### 39.3. Configuration Management

Use a config management process with versioning, review, and restart-requirement checks. ALTER SYSTEM writes to postgresql.auto.conf; understand precedence and manage that file properly.

### 39.4. Changing Durability Settings Requires Review

Modifying fsync, full_page_writes, or synchronous_commit can alter data-loss guarantees. Evaluate against RPO, hardware, and business policy before applying.

---

## 40. Designing Safe WAL Retention

### 40.1. Identify Consumers

List all WAL consumers and needs:

- Internal crash recovery.
- WAL archiver.
- Physical standbys.
- Logical replication slots.
- Logical decoding consumers.
- Base backup/PITR windows.

### 40.2. Define Retention Targets

Plan for archive retention days, how many standbys can be offline, peak WAL generation rate, and headroom capacity.

### 40.3. Monitor Slot Lag

An inactive logical slot can retain WAL indefinitely without proper limits. Alert on retained bytes and inactivity age.

### 40.4. Clean Up Archives Based on Backup Dependencies

Do not delete WAL archives solely because a segment is old. Check all retained base backups and the WAL range required to restore them.

### 40.5. Check Timeline History

Keep timeline history files and related WAL segments; do not delete a branch needed by an existing backup.

### 40.6. Do Not Use max_wal_size as an Archive Retention Policy

max_wal_size controls checkpoint pressure, not how long WAL is retained for PITR or consumer slots.

---

## 41. Scenario A: COMMIT Succeeds but Data File Has Not Changed Yet

**Context:** An application writes an order and receives COMMIT success. An operator inspects the relation file immediately afterward and thinks the data was not saved.

### 41.1. Explanation

COMMIT success under synchronous durability means the WAL commit record was flushed per policy. Data pages can still be dirty in shared buffers.

### 41.2. What Protects the Data?

The WAL-before-data rule guarantees that when the page is eventually written, its corresponding WAL is already durable. If a crash occurs before the page is written, recovery redoes from WAL.

### 41.3. When Does a Checkpoint Happen?

Checkpoints occur on timeout, WAL pressure, or manual request—not after every COMMIT.

### 41.4. How to Verify

Use SQL, transaction semantics, WAL metrics, and recovery tests. Physical file layout is an implementation detail; do not inspect relation files directly to judge transaction state.

---

## 42. Scenario B: pg_wal Disk Nearly Full

**Context:** Monitoring reports the filesystem containing pg_wal has 5% free space left.

### 42.1. Rapid Investigation

- Check pg_stat_archiver and archive errors.
- Check inactive or lagging replication slots.
- Check standby receive/replay LSNs.
- Check WAL generation rate.
- Check available space at the archive destination.
- Review PostgreSQL logs.

### 42.2. Actions

- Fix the archive destination if failing.
- Recover the standby/consumer if possible.
- Identify unused slots and handle them according to the runbook.
- Expand storage capacity if necessary.
- Throttle workload if there is a WAL generation spike.

### 42.3. Do Not Delete WAL Files

WAL may currently be needed for recovery or replication. Manual deletion can prevent the database from starting or prevent a standby from catching up.

### 42.4. Post-Incident

Review retention settings, alert thresholds, capacity forecasts, and verify archive completeness.

---

## 43. Scenario C: Crash and Lost Recent Commits

**Context:** A service received COMMIT success, yet after a restart some recent transactions are missing.

### 43.1. Check synchronous_commit

If the transaction or session used synchronous_commit=off, PostgreSQL may have returned a response before flushing WAL.

### 43.2. Check fsync/Storage

If fsync=off or storage does not implement flush semantics honestly, durability can be severely compromised.

### 43.3. Check Synchronous Replication Expectations

If the application mistakenly assumes on always means the remote standby has applied the transaction, there may be a mismatch between expectations and actual configuration. With a sync standby, on typically waits for remote flush, not necessarily remote apply.

### 43.4. Network Ambiguous Outcome

If a client times out during COMMIT, the transaction may have committed even though the client never received the response. This is a different situation from a transaction receiving success and disappearing after a crash.

### 43.5. Application Improvements

Use idempotency keys, business transaction identifiers, and reconciliation workflows to handle retries and ambiguous outcomes.

---

## 44. Scenario D: Prolonged Recovery After Restart

**Context:** The database takes minutes or hours to finish crash recovery.

### 44.1. Contributing Factors

- WAL distance from the checkpoint redo point to the crash.
- WAL generation rate.
- Storage read/write throughput.
- Full-page images and workload characteristics.
- Number of records to replay.
- Page cache and checkpoint history.

### 44.2. Investigation

- Read PostgreSQL startup/recovery logs.
- Review checkpoint frequency and requested checkpoints.
- Check WAL segment availability/continuity.
- Evaluate storage throughput.
- Compare recovery time against RTO.

### 44.3. Do Not Simply Increase Checkpoint Frequency

More frequent checkpoints can reduce redo volume but increase I/O and FPIs. Benchmark both steady-state workload and recovery time.

### 44.4. Recovery Testing

Use a production-sized copy or equivalent environment to measure actual restart/replay duration.

---

## 45. Scenario E: Standby Lag After a Bulk Load

**Context:** A large COPY import completes on the primary, but the read replica falls behind.

### 45.1. WAL Burst

COPY into a logged table generates WAL for data changes and corresponding indexes/constraints.

### 45.2. Receive Lag vs. Replay Lag

Compare sent/write/flush/replay LSNs to tell whether the standby has not received enough WAL or has received it and is applying slowly.

### 45.3. Checkpoint I/O

Bulk loads can increase checkpoint writes and storage I/O, affecting both primary and standby.

### 45.4. Operational Solutions

- Schedule batches during suitable windows.
- Measure WAL rate and standby apply capacity.
- Review indexes/constraints and batch sizes.
- Monitor disk, WAL archive, and slot retention.
- Never disable durability to mask a replication bottleneck.

---

## 46. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| COMMIT success means all data pages are written to disk | WAL is flushed per policy; pages may still be dirty |
| WAL is an SQL log | WAL is an internal log for recovery and replication |
| Successful write means data is durable | It may only be in the OS page cache |
| A checkpoint is a COMMIT | A checkpoint is a cluster-wide sync operation |
| A checkpoint is a backup | No; a base backup and WAL are required |
| Every transaction needs a checkpoint | Checkpoints run on schedule/WAL pressure |
| WAL is only written during a checkpoint | WAL is generated continuously on write operations |
| Data pages are written before WAL | Violates the write-ahead rule |
| WAL flush is unrelated to durability | Flushing is central to commit durability |
| synchronous_commit=off always corrupts the database | Recent commits may be lost, but recovery consistency is still maintained via durable WAL |
| fsync=off only gives a slight speedup | Risks corruption after a crash |
| full_page_writes off is always safe | Risks torn pages if storage writes are not atomic |
| FPI is a full database backup | FPI is a page image inside WAL |
| Page checksums replace full_page_writes | The two mechanisms serve different goals |
| Background writer and checkpointer are the same | They have distinct roles |
| max_wal_size is a hard limit | WAL can exceed it due to slots/archive/retention |
| Old WAL can be deleted once checkpoint finishes | It may still be needed by archive/standby/backups |
| Archive mode enabled guarantees PITR works | Requires a base backup and WAL continuity |
| pg_dump + WAL archive is equivalent to physical PITR | Logical backup and physical recovery serve different goals |
| Standby receiving WAL means new changes are readable | It may not have replayed them yet |
| Synchronous replication is a backup | Logical errors also replicate |
| remote_write equals remote_flush | Not necessarily durable to storage |
| remote_flush means standby has applied changes | Flush differs from apply |
| Replication slots are always safe | Inactive slots can retain WAL and fill the disk |
| max_wal_size controls slot retention | It is not a retention cap |
| wal_keep_size replaces replication slots/archive | No |
| Logical replication is physical replication | They are different mechanisms with different purposes |
| WAL contains no sensitive data | It can contain enough info to reconstruct changes |
| pg_resetwal is a way to clean up pg_wal | It is an extreme recovery tool carrying data-loss risks |
| LSN is a timestamp | LSN is a position in the WAL stream |
| LSN diff is always time lag | It is byte distance, not time |
| More frequent checkpoints are always better | Increases I/O and can increase FPIs |
| Less frequent checkpoints are always better | Can increase recovery time and WAL retention |
| WAL compression is free | Has a CPU cost and data-dependent effectiveness |
| UNLOGGED tables physically replicate like logged ones | Not with logged-table semantics |
| Successful backup means restore works | Requires restore drills and validation |
| One PITR lab proves all backups work | Must test multiple targets and failure modes |
| COMMIT timeout means transaction rolled back | It may be an ambiguous outcome |
| Archive file existing means the file is complete | Requires checksum/size/continuity verification |

---

## 47. Practice Exercises

### Exercise 1 — Write-Ahead Logging

Explain the WAL principle and what can happen if a data page is written before its corresponding WAL.

### Exercise 2 — WAL vs. Data Files

Distinguish between WAL records, WAL segments, heap files, and index files. State the purpose of each.

### Exercise 3 — LSN

Run pg_current_wal_lsn() before and after an INSERT. Why does the LSN increase not necessarily equal the row data byte size?

### Exercise 4 — Page LSN

Explain the role of page LSN when recovery decides whether to apply a WAL record.

### Exercise 5 — WAL Buffers

Distinguish between wal_buffers and shared_buffers. Which memory areas does a transaction write to?

### Exercise 6 — Write and Flush

Explain why writing to the OS page cache does not always mean data is durable across a power loss.

### Exercise 7 — Commit Path

Diagram the flow from UPDATE to COMMIT, including heap/index dirty pages, WAL records, commit record, and flush.

### Exercise 8 — Group Commit

How can multiple transactions committing concurrently reduce the number of fsync calls?

### Exercise 9 — Dirty Pages

Why can PostgreSQL confirm COMMIT while data pages remain dirty in shared buffers?

### Exercise 10 — synchronous_commit

Compare off, local, remote_write, remote_flush, and remote_apply. Which value waits for standby replay?

### Exercise 11 — fsync

State the risks of disabling fsync in production. Why can this not be treated as a normal tuning option?

### Exercise 12 — full_page_writes

Explain torn pages and how full-page images support recovery.

### Exercise 13 — wal_compression

Describe the benefits and CPU trade-offs of compressing full-page images.

### Exercise 14 — Checkpoint

Explain checkpoint, redo point, and checkpoint record. Why is a checkpoint not a backup?

### Exercise 15 — Checkpoint Pressure

Distinguish between timed checkpoints and requested checkpoints. Which metrics indicate checkpoints are occurring too frequently?

### Exercise 16 — max_wal_size

Why is max_wal_size not a hard cap for pg_wal?

### Exercise 17 — checkpoint_completion_target

Explain the goal of this parameter and the impact of setting it too low.

### Exercise 18 — Crash Recovery

A committed transaction flushed WAL, but its data page was not written yet. The server crashes. Describe the recovery process.

### Exercise 19 — Uncommitted Transaction

A transaction modifies a page and then the server crashes before COMMIT. Why does the transaction's data not become committed after recovery?

### Exercise 20 — WAL Replay

Why does recovery replay WAL records instead of re-executing the original SQL statements?

### Exercise 21 — Archive

Design an idempotent archive helper and describe the conditions for returning success.

### Exercise 22 — Archive Failure

The archive command fails continuously. Why can pg_wal grow, and how do you investigate?

### Exercise 23 — Base Backup

Explain why a WAL archive is insufficient without a compatible base backup.

### Exercise 24 — PITR

Design a restore procedure to a recovery_target_time. Which files and configurations are required for your version?

### Exercise 25 — Timeline

Draw Timeline 1 and Timeline 2 after a promotion. Why must the archive keep history files?

### Exercise 26 — Physical Replication

Distinguish between WAL send, write, flush, and replay LSNs. Can a standby that has flushed WAL but not yet replayed it read the new data?

### Exercise 27 — Synchronous Replication

Explain the RPO and latency trade-offs when using a synchronous standby.

### Exercise 28 — Logical Replication

Distinguish logical decoding from physical replay. Why can wal_level=logical increase overhead?

### Exercise 29 — Replication Slots

An inactive logical slot retains WAL for days. What happens, and which metrics should trigger alerts?

### Exercise 30 — wal_keep_size

Why does wal_keep_size not replace an archive/slot retention plan?

### Exercise 31 — Monitoring

Write queries to inspect pg_stat_archiver, pg_stat_replication, pg_replication_slots, and version-appropriate checkpoint stats.

### Exercise 32 — WAL Delta

Use pg_wal_lsn_diff to compute bytes between two LSNs. Why cannot this be interpreted directly as seconds of lag?

### Exercise 33 — pg_waldump

Describe how to use pg_waldump for diagnostics and why the binary must match the WAL format.

### Exercise 34 — pg_resetwal

Why is pg_resetwal strictly a last resort? List the risks regarding transaction history and data consistency.

### Exercise 35 — UNLOGGED

Compare logged and UNLOGGED tables with respect to WAL, crash recovery, and physical replication.

### Exercise 36 — Backup Restore Drill

Design a restore drill incorporating a base backup, WAL archive, recovery target, and application smoke tests.

### Exercise 37 — RPO/RTO

A system has an RPO of 5 minutes and an RTO of 30 minutes. Propose backup cadence, WAL archiving, monitoring, and restore testing to verify these objectives.

### Exercise 38 — Disk Full

The pg_wal filesystem has 5% space left. Outline the investigation order for archive, slots, standbys, WAL generation, and storage. Why must WAL not be deleted manually?

### Exercise 39 — Durability Incident

An application received COMMIT success, but transactions were lost after a crash. List the configuration and storage conditions to check.

### Exercise 40 — Ambiguous Commit

A client times out during COMMIT. Design idempotency/reconciliation so retries do not create duplicate transactions.

### Exercise 41 — Bulk Load

A large COPY causes standby lag. Use LSNs to determine receive lag vs. replay lag, and propose adjustments to batching or replication capacity.

### Exercise 42 — Checkpoint Benchmark

Design an experiment changing checkpoint_timeout/max_wal_size on staging. Measure steady-state I/O, WAL volume, commit latency, and recovery time.

### Exercise 43 — Archive Security

WAL archives contain sensitive data. Propose access controls, encryption, retention, immutability, and credential rotation.

### Exercise 44 — Version Compatibility

A query on pg_stat_checkpointer fails on an older PostgreSQL version. Build a way to check version and select the corresponding view.

### Exercise 45 — Production Runbook

Write a runbook for handling WAL archive backlogs, slot retention, disk pressure, and standby lag, including escalation and validation.

### Exercise 46 — End-to-End Design

An order-processing system requires near-zero RPO on primary loss, 14-day PITR, a reporting read standby, and high write volume. Design WAL settings, synchronous replication, archive/base backups, slot policy, checkpoint tuning, monitoring, storage capacity, and restore drills. State the trade-offs regarding latency, availability, and cost.

---

## 48. WAL and Checkpoint Operations Checklist

| Question | What to Verify |
| --- | --- |
| Is WAL enabled at the right level? | wal_level |
| Is fsync enabled? | Durability policy |
| Is full_page_writes enabled? | Torn-page protection |
| Does synchronous_commit match transaction needs? | Commit durability |
| Does storage have honest flush semantics? | OS/controller/cloud volume |
| Does the WAL disk have enough free space? | pg_wal capacity/trend |
| How are timed vs. requested checkpoints behaving? | Checkpointer stats |
| What are checkpoint write/sync times? | I/O pressure |
| Are FPI/WAL bytes spiking? | pg_stat_wal |
| Is max_wal_size reasonable? | WAL rate and recovery |
| Is checkpoint_completion_target appropriate? | Write smoothing |
| Are archive mode and command set properly? | archive_mode, archive settings |
| What are archive successes/failures? | pg_stat_archiver |
| Is the archive destination durable? | Checksum/replication/immutability |
| Is the WAL archive continuous? | Missing segment checks |
| When was the latest base backup? | Backup catalog |
| Is WAL from base backup to target complete? | PITR continuity |
| When was the last restore drill? | RTO/RPO evidence |
| Is timeline history preserved? | Archive inventory |
| What is standby receive/flush/replay lag? | pg_stat_replication |
| What is synchronous standby state? | sync_state/quorum |
| Are any logical slots inactive? | pg_replication_slots |
| How much WAL are slots retaining? | Capacity/alerts |
| Is max_slot_wal_keep_size configured? | Version/config policy |
| Has a standby been offline long? | Rebuild/resync plan |
| Is manual WAL deletion prohibited? | Runbook |
| Is WAL archive access restricted? | Least privilege |
| Are archives encrypted? | At-rest protection |
| Is the retention policy clear? | Backup dependency |
| Are secrets managed properly? | Rotation/access logs |
| Is monitoring trend-based? | Time-to-full alerts |
| Is commit latency baselined? | p95/p99 |
| Has crash recovery time been measured? | RTO test |
| Is pg_resetwal safeguarded against misuse? | Emergency-only procedure |
| Are version-specific stats handled? | View/column compatibility |
| Are backups isolated from primary failure domain? | Offsite/independent copy |
| Does the app handle ambiguous commits? | Idempotency/reconciliation |
| Is there a config rollback plan? | Versioned settings |

## Conclusion

**WAL and checkpoints** form the foundation that enables PostgreSQL to process write transactions efficiently while remaining recoverable after a crash.

Key principles to remember:

1. **WAL must be durably written before the corresponding data pages.** This is the write-ahead rule, guaranteeing recovery has logs to redo when a data page was not completely written.
2. **COMMIT and checkpoint are two different events.** COMMIT confirms a transaction according to durability settings; a checkpoint syncs dirty pages and sets a redo point.
3. **WAL flush is central to commit durability.** Data pages may remain dirty after the client receives COMMIT success.
4. **fsync and full_page_writes protect integrity after a crash.** Disabling them can create severe data-loss or corruption risks.
5. **synchronous_commit determines how long commits wait.** remote_flush and remote_apply have different semantics; synchronous replication increases latency but can lower RPO.
6. **Checkpoints must be balanced.** Too frequent increases I/O and FPIs; too infrequent can increase WAL retention and recovery time.
7. **WAL archives must accompany base backups.** PITR is reliable only with a continuous WAL chain and tested restores.
8. **Timelines must be managed properly.** Failover or promotion creates a new WAL branch; archives must preserve timeline history.
9. **Replication slots can retain WAL for a very long time.** Monitor slot lag and disk usage; never delete WAL manually.
10. **Monitoring must distinguish write, flush, and replay.** Current LSN, flush LSN, standby receive/replay LSN, and archiver stats answer different questions.
11. **A successful backup does not prove recoverability.** Restore drills, checksum/continuity checks, and RTO/RPO measurements are required.
12. **Durability is an end-to-end commitment.** PostgreSQL, OS, storage, archives, and runbooks must each perform their role properly.

A reliable PostgreSQL system does more than just write transactions fast. It must know which transactions are durable, which WAL must still be retained, how checkpoints are progressing, how far standbys have replayed, and whether a base backup plus WAL archive can restore data to target objectives after an incident.
