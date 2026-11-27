# WAL, Checkpoints, and Crash Recovery in the PostgreSQL Big Picture

A PostgreSQL transaction can update thousands of records and return `COMMIT` within milliseconds, even though the data pages for those records have not necessarily been written to the table files on disk yet. This raises a critical question: **if the server loses power right after the application receives a successful commit response, what does PostgreSQL rely on to recover the data?**

The answer lies in the coordination among **Write-Ahead Logging (WAL)**, **checkpoints**, in-memory data page management, and **crash recovery**. WAL records enough information for PostgreSQL to redo necessary changes after a failure; checkpoints bound how much WAL must be processed during recovery. These same mechanisms also form the foundation for *physical replication*, WAL archiving for *point-in-time recovery* (PITR), and many operational workflows.

This lesson focuses on PostgreSQL using standard WAL-logged tables—just as InnoDB tables are crash-safe in MySQL, PostgreSQL defaults to **logged tables**. Exceptions such as `UNLOGGED` and temporary tables have different durability guarantees and are clearly distinguished. Function names, parameters, and statistics views can vary across major PostgreSQL versions; when practicing on a live server, consult the manual for that exact version.

## 1. Placing WAL and Checkpoints in the Overall Architecture

First, separate three concepts that are easily confused:

- **Data page:** a storage block holding table or index data that can be loaded into buffer memory and modified there.
- **WAL record:** a log entry describing changes needed to restore state, written sequentially into the WAL stream.
- **Checkpoint:** a synchronization milestone controlling progress of flushing dirty data pages from memory to storage, thereby bounding where redo must begin during recovery.

Simplified diagram:

```text
                           APPLICATION
                               |
                        BEGIN / UPDATE
                               |
                               v
                    PostgreSQL backend
                        /           \
                       v             v
               shared_buffers      WAL buffers
               modified data        WAL records
                   pages               |
                   |                   v
                   |               WAL write/flush
                   |                   |
                   v                   v
              Data files            pg_wal/
           (heap / indexes)     (WAL segments)
                   ^                   |
                   |                   |
                 Checkpoint -----------+
              flushes dirty       ensures WAL
               data pages         goes ahead

WHEN SERVER CRASHES:
  data files at checkpoint + needed WAL
                   |
                   v
             WAL REDO / RECOVERY
                   |
                   v
        Usable database state
```

This diagram shows **logical relationships** only. In real operation, many backends run concurrently, pages are written to memory and disk by multiple processes, WAL includes many record types, and the operating system maintains its own page cache.

### Key components involved

| Component | Primary role |
| --- | --- |
| Backend process | Processes client SQL, modifies data pages in memory, and generates WAL records when needed. |
| Shared buffers | Buffer cache holding PostgreSQL data pages, both clean and modified (*dirty pages*). |
| WAL buffers | Temporarily buffers WAL records before they are written to WAL files. |
| WAL writer | Periodically writes WAL in the background; backends can also write/flush WAL themselves to satisfy commit requirements. |
| Checkpointer | Coordinates checkpoints and writing/syncing required pages to establish a recovery milestone. |
| Background writer | Helps flush dirty pages to disk during normal operation, easing pressure on backends. |
| `pg_wal` | Directory holding WAL segments managed by PostgreSQL for operation and recovery. |
| Startup/recovery process | Reads checkpoint metadata and performs WAL replay when recovering data. |
| WAL archiver (if configured) | Copies completed WAL segments to archive storage for backup/PITR strategies. |

**There is no rule saying "every COMMIT immediately writes all table pages to disk."** What standard durability guarantees require is that relevant WAL records are durably persisted before confirming the transaction, whereas flushing data pages can happen later.

## 2. What Does Write-Ahead Logging Mean?

The name **Write-Ahead Logging** describes the "log first" rule: before a modified data page is safely written to storage, the WAL records needed to recover that change must be written and flushed in the proper order.

When a transaction updates a record:

1. The backend locates and updates data per storage/MVCC rules.
2. PostgreSQL generates WAL records describing the changes needed for redo.
3. WAL records enter WAL buffers and are written out to WAL segments.
4. When commit requires synchronous durability by default, PostgreSQL flushes WAL up to the commit point to durable storage before reporting commit success.
5. The corresponding table or index pages **can be flushed later**, by the background writer, checkpointer, or another write path.

```text
Time ---->

Data page in RAM:   UPDATE ------ dirty --------------------- flush
WAL in RAM:            WAL record --- commit record
WAL on storage:                    write + durable flush
                                                  |
                                                  v
                                         COMMIT acknowledged

Data pages are not required to be flushed at COMMIT time.
```

If a crash occurs after WAL is flushed but before data pages are flushed, PostgreSQL **reads WAL and performs redo**. This is why WAL sits at the heart of **durability** in ACID.

### WAL is not a full copy of every table

WAL is a **stream of change records and recovery metadata**, not a directory holding human-readable copies of every table. Although WAL sometimes contains *full-page images*, do not picture every `INSERT` creating a whole copy of a table or treat WAL as a standalone backup capable of rebuilding everything from scratch.

For PostgreSQL operations, WAL records describe page-level changes, transaction state, and internal operations. Users never write WAL records directly in SQL; the engine generates them automatically.

## 3. Example: A Transaction Commits Before Data Pages Flush

Create a default logged table in a test schema:

```sql
CREATE SCHEMA IF NOT EXISTS wal_lab;

CREATE TABLE wal_lab.account_balances (
    account_id bigint PRIMARY KEY,
    balance numeric(14, 2) NOT NULL CHECK (balance >= 0)
);

INSERT INTO wal_lab.account_balances (account_id, balance)
VALUES (101, 1000.00), (202, 500.00);
```

A transaction transferring 100 units:

```sql
BEGIN;

UPDATE wal_lab.account_balances
SET balance = balance - 100.00
WHERE account_id = 101;

UPDATE wal_lab.account_balances
SET balance = balance + 100.00
WHERE account_id = 202;

COMMIT;
```

Logically, both updates form one atomic transaction. Under standard PostgreSQL durability settings, when `COMMIT` returns success, the engine has persisted the required WAL per the transaction's durability boundary, yet **does not require both modified heap pages to be written into table files at that moment**.

If the OS or PostgreSQL crashes before those two dirty pages are flushed, PostgreSQL uses WAL during crash recovery to restore the state of committed transactions.

**Never** induce a real crash in production to verify this behavior. Crash testing belongs in an isolated lab where power/shutdown mechanics, storage caching, backups, and acceptable data loss are understood.

### Common question: does UPDATE write to disk before COMMIT?

An `UPDATE` modifies pages in memory and generates WAL; when data pages or WAL flush to storage depends on multiple processes and buffer state. Learners should not conflate three separate events:

1. PostgreSQL **logically processed the UPDATE** inside the transaction.
2. The WAL record was **written or flushed**.
3. The data page was **written to the data file**.

These three events do not occur at one mandatory instant. WAL decouples transaction confirmation from flushing every modified data page immediately.

## 4. WAL Segments, pg_wal, and WAL Sequence Numbers (LSN)

WAL records are ordered sequentially in a continuous WAL stream. PostgreSQL stores this stream in **WAL segment files** inside the `pg_wal` subdirectory of the data directory.

A segment is commonly **16 MiB** by default, though WAL segment size can be chosen at cluster initialization depending on PostgreSQL version. Never treat 16 MiB as a universal constant across every system.

### 4.1. What is an LSN?

A **Log Sequence Number (LSN)** represents a logical position in the WAL stream. It is typically printed as:

```text
0/16B6C50
0/16B6D20
```

The second value lies further ahead in the WAL stream. An LSN is neither a timestamp nor an application transaction ID.

Uses of LSNs:

- Tracking WAL write and flush positions.
- Measuring replication or recovery progress.
- Comparing received vs. replayed positions on a standby.
- Relating checkpoint milestones to redo starting points.

On an active primary, you can inspect:

```sql
SELECT pg_current_wal_lsn() AS current_wal_lsn;
```

Some diagnostic functions require appropriate privileges, and `pg_current_wal_*` functions target a running primary; on a standby, use the receive/replay WAL functions instead.

Example measuring byte distance between two illustrative LSNs:

```sql
SELECT pg_wal_lsn_diff('0/16B6D20'::pg_lsn, '0/16B6C50'::pg_lsn)
       AS wal_bytes_between;
```

`pg_wal_lsn_diff` returns the WAL offset difference in bytes. To measure WAL generation rate, sample two LSNs over a time interval and take the difference—remembering the result is **WAL volume generated**, not business payload size or table growth.

### 4.2. LSNs, timelines, and physical location

When monitoring recovery or failover, you will also encounter **timeline IDs**. A timeline identifies a branch of WAL history after events like point-in-time recovery and standby promotion. Two WAL sequences on different timelines cannot be compared naively just by seeing which LSN integer is larger.

WAL segment filenames encode timeline and segment location. Never judge from filename strings alone that transaction history is intact, especially after PITR or promotion.

### 4.3. Why must you never manually delete files in pg_wal?

`pg_wal` is managed by PostgreSQL. Segments may still be needed for:

- Crash recovery and checkpoint boundaries.
- Streaming replication to standbys.
- Unconsumed replication slots.
- WAL archiving.
- Ongoing backup or recovery operations.

Deleting WAL files with OS commands to "free disk space" can make the server unrecoverable or break replicas. Solve disk pressure by diagnosing why WAL is retained and using proper administrative commands—never arbitrarily deleting files inside `pg_wal`.

## 5. What Is a Checkpoint and What Problem Does It Solve?

Suppose PostgreSQL has run continuously for days, generating huge WAL volume while data pages trickle out to disk. Without recovery milestones, a crash could force PostgreSQL to replay an enormous stretch of history to bring data up to date.

A **checkpoint** establishes a milestone guaranteeing that dirty data pages up to that point are synced per checkpoint rules, recording the checkpoint location in WAL and cluster control state. Restarting after a crash lets PostgreSQL start redo from the appropriate recent checkpoint rather than replaying history from database creation.

```text
WAL over time

--------- [checkpoint A] ---------- [checkpoint B] -------- crash
                      |                         |
                      |                         +-- choose appropriate recovery point
                      +-- older WAL may no longer be needed
                          for crash recovery unless retained
                          for other requirements

Recovery normally redoes from the checkpoint-determined point
to the end of valid applicable WAL.
```

A checkpoint does not delete data or commit application transactions. It manages **page durability and recovery bounds**, not `COMMIT`.

### 5.1. What work does a checkpoint perform?

Conceptually:

1. Checkpointer identifies dirty pages that must be written for the checkpoint.
2. PostgreSQL coordinates writing those modified data pages to storage.
3. Required file and WAL syncs execute so the milestone is valid for recovery.
4. Checkpoint metadata is persisted so the next startup knows which state is safely on disk.
5. Older WAL segments no longer needed may be recycled or removed per policy and retention rules.

The word "may" in step 5 is crucial: **a checkpoint does not mean PostgreSQL immediately deletes all prior WAL**. Backups, archiving, replication, slots, and retention settings can keep older segments alive.

### 5.2. Can INSERTs run while a checkpoint is executing?

Yes. PostgreSQL allows backends to keep serving transactions while a checkpoint runs, coordinating memory, WAL, and page writes. A checkpoint is not a "pause button" freezing all transactions until every page flushes.

On the other hand, checkpoints consume I/O bandwidth; if poorly tuned relative to WAL generation rate and disk hardware, they can trigger latency spikes. That is why checkpoints are paced and monitored rather than run back-to-back continuously.

## 6. How Do Checkpoints and COMMIT Differ?

| Criterion | `COMMIT` | Checkpoint |
| --- | --- | --- |
| Scope | One transaction (or group) being confirmed | Whole cluster's page-flushing progress and recovery milestone |
| Who initiates it? | Application/backend or transaction execution layer | Checkpointer on schedule, WAL threshold, or admin request |
| Goal | Finalize a transaction and persist changes per durability settings | Establish a recovery milestone and sync dirty pages per checkpoint rules |
| Forces immediate write of all transaction table pages? | No | Syncs pages belonging to the checkpoint per coordination rules |
| Commits open client transactions? | Yes, if successful | Never commits open transactions on its own |
| Impact on crash recovery | Durable WAL commit identifies confirmed transactions | Bounds how far back WAL redo must scan |

Example:

```sql
BEGIN;
UPDATE wal_lab.account_balances
SET balance = balance + 10
WHERE account_id = 101;

-- A checkpoint may occur while this transaction is still open.
ROLLBACK;
```

A checkpoint does not turn an uncommitted `UPDATE` into a committed transaction. PostgreSQL continues enforcing transaction and MVCC semantics. Pages on disk may physically contain uncommitted tuple bytes, yet those versions are never treated as valid results of a rolled-back transaction.

### What if a checkpoint happens before COMMIT?

WAL and checkpoints ensure physical recovery integrity, while **transaction status** still governs logical visibility. There is no rule saying "if a data page hit disk, the transaction automatically succeeded." PostgreSQL tracks commit/abort status and MVCC visibility independently of whether a page was written out.

## 7. How Does PostgreSQL Decide When to Checkpoint?

Checkpoints trigger on multiple conditions. Key settings to know:

| Parameter | General meaning |
| --- | --- |
| `checkpoint_timeout` | Maximum time between automatic scheduled checkpoints under normal operation. |
| `max_wal_size` | Target WAL size; as WAL grows, PostgreSQL triggers checkpoints based on WAL thresholds. |
| `min_wal_size` | Target minimum WAL to retain for recycling, avoiding excessive segment creation/deletion. |
| `checkpoint_completion_target` | Fraction of the checkpoint interval over which checkpoint writes are spread. |
| `checkpoint_warning` | Emits log warnings when WAL-triggered checkpoints happen closer together than this threshold. |

Inspect current settings:

```sql
SHOW checkpoint_timeout;
SHOW checkpoint_completion_target;
SHOW min_wal_size;
SHOW max_wal_size;
SHOW checkpoint_warning;
```

Or check sources and units:

```sql
SELECT
    name, setting, unit, source, context, pending_restart
FROM pg_settings
WHERE name IN (
    'checkpoint_timeout',
    'checkpoint_completion_target',
    'min_wal_size',
    'max_wal_size',
    'checkpoint_warning'
)
ORDER BY name;
```

### 7.1. max_wal_size is not a hard limit

Learners often assume `max_wal_size = '2GB'` means `pg_wal` can **never** exceed 2 GB. In reality, it is a **soft target guiding checkpoint pacing and WAL recycling**, not a hard directory quota.

WAL usage can still exceed it when:

- Sudden bursts of WAL generation occur.
- Checkpointing, disk writes, or archiving fall behind.
- A replication slot retains unconsumed WAL.
- A standby or backup process requires older segments.
- `wal_keep_size` or other retention requirements apply.

Therefore, if `pg_wal` grows steadily, **never blindly shrink `max_wal_size`**. Diagnose why WAL is accumulating first.

### 7.2. checkpoint_completion_target and I/O smoothing

Checkpoints write many dirty pages. Flushing them all at maximum speed causes I/O spikes and query stalls. `checkpoint_completion_target` spreads checkpoint writes across a target share of the checkpoint interval.

A balanced target smooths I/O peaks without eliminating the physical cost of writing pages. Under extreme write rates or undersized disks, checkpoints can still lag, forcing backends to write pages or raising latency.

Never change multiple parameters simultaneously because of one slow query. Measure WAL rate, page writes, checkpoint duration, and application latency before and after in a controlled environment.

## 8. How Does Crash Recovery Work?

**Crash recovery** is how PostgreSQL restores database consistency after an abnormal process or server termination—such as power loss, kernel panic, unclean shutdown, or a severe backend crash.

At a high level:

1. PostgreSQL detects the cluster did not shut down cleanly.
2. The engine reads cluster control state and checkpoint records.
3. It determines the **redo starting point** from the appropriate checkpoint.
4. It reads and applies valid WAL records sequentially per replay rules.
5. Transaction/MVCC state is restored so committed transactions are visible while incomplete ones are not treated as committed.
6. Once recovery finishes, the server accepts connections according to its role and configuration.

```text
Before crash:

                 checkpoint
                     |
WAL  ---- A ---- B ---- C ---- D ---- E ---- crash
                     |                 |
                     |                 +-- last valid WAL
                     +-- basis for redo start

Data files:
    hold pages flushed at various times
    may not yet hold every recently committed change

On restart:
    read checkpoint / redo location
            |
            v
    replay required WAL
            |
            v
    determine accurate transaction states
            |
            v
    database ready
```

Do not picture PostgreSQL throwing away the database and restoring a separate "checkpoint backup." Checkpoints **do not create standalone backup snapshots**; recovery uses the existing data files plus required WAL.

### 8.1. Redo and uncommitted transactions

Crucial point: physical WAL replay can re-apply page modifications produced by a transaction that was **uncommitted** at crash time. That **never** makes that transaction count as committed.

PostgreSQL uses **MVCC and transaction commit status** to determine tuple visibility. Uncommitted tuple versions do not become valid data merely because WAL replayed page changes; they are ignored by readers and later cleaned up by VACUUM and pruning.

Avoid oversimplifying crash recovery as "only replaying committed transactions' records and skipping uncommitted ones." WAL redo and transaction visibility work as two cooperating layers.

### 8.2. Does crash recovery require the application to run ROLLBACK?

No. After a crash, old sessions and open transactions no longer exist in a way that old connections could send `ROLLBACK`. PostgreSQL restores transaction state automatically so uncommitted changes are never exposed as committed.

From the application perspective:

- Transactions open when the connection dropped cannot resume on a new connection.
- Transactions confirmed committed before the crash under standard durability settings are expected to survive recovery.
- Transactions where the client **does not know whether COMMIT succeeded** must be verified via business keys or idempotency—never blindly retried in ways that create duplicates.

## 9. Distinguishing a Clean Shutdown from a Crash

PostgreSQL supports multiple shutdown modes with different consequences. A controlled shutdown flushes buffers, closes connections, handles transactions, and records a clean state. An abrupt termination requires WAL redo on the next startup.

Shutdown modes of `pg_ctl`:

| Mode | Operational meaning |
| --- | --- |
| `smart` | Waits for all active clients to disconnect before stopping; can hang if clients stay connected. |
| `fast` | Controlled shutdown: disconnects clients, rolls back active transactions, checkpoints, and stops cleanly. |
| `immediate` | Abrupt stop without clean shutdown; the next startup requires crash recovery. |

In a lab environment with access to the data directory:

```bash
# Syntax example only; do not run in production without a runbook.
pg_ctl -D /path/to/pgdata stop -m fast
```

`immediate` is not a routine way to stop "faster"; it deliberately forces crash recovery on the next start. In environments managed by systemd, Kubernetes operators, or cloud providers, always use the platform's managed lifecycle procedures.

### Signs in startup logs

After a clean shutdown, logs note the database shut down normally. After a crash, recovery messages appear, for example:

```text
LOG:  database system was interrupted; last known up at ...
LOG:  database system was not properly shut down; automatic recovery in progress
LOG:  redo starts at ...
LOG:  redo done at ...
LOG:  checkpoint starting: end-of-recovery immediate wait
LOG:  database system is ready to accept connections
```

This is an **illustrative example**, not guaranteed word-for-word output across every version and incident. During recovery, logs also report WAL locations, timing, timelines, checkpoints, and errors if WAL is missing.

If PostgreSQL reports missing WAL records/segments or unreadable data files, never delete WAL files or force state changes to make the server start. Preserve evidence, verify backups, and follow an approved recovery runbook.

## 10. full_page_writes and Full-Page Images in WAL

A subtle failure occurs if power drops halfway through writing an 8 KiB data page to storage. Depending on disk hardware and OS layers, that page can end up half-written—a **torn page**.

`full_page_writes` protects recovery against torn pages. When enabled (the normal default), PostgreSQL writes a **full-page image** to WAL the first time a page is modified after a checkpoint. During WAL replay, that full-page image restores a clean baseline even if the on-disk data page was torn.

```text
After checkpoint:

First time a data page is modified
            |
            v
     WAL may contain full-page image
            |
            v
     Subsequent changes to page
     continue generating WAL per mechanism

On crash with torn data page:
     WAL redo + full-page image restores the page
```

Check setting:

```sql
SHOW full_page_writes;
```

### WAL volume trade-off

Full-page images increase WAL size, especially right after a checkpoint when many pages get touched for the first time. Thus, **overly frequent checkpoints inflate WAL volume due to full-page writes**, on top of flushing data pages more often.

This links three factors:

1. Checkpoints set the redo starting milestone.
2. After a checkpoint, first touches on pages emit full-page images.
3. Too-frequent checkpoints amplify both I/O and WAL volume.

Never disable `full_page_writes` just to shrink WAL without carefully evaluating storage hardware atomicity and data-loss risks.

### wal_compression

`wal_compression` lets PostgreSQL compress full-page images in WAL using algorithms supported by your version. Compression reduces WAL volume at the cost of extra CPU; actual savings depend on page contents and workload.

```sql
SHOW wal_compression;
```

Do not treat WAL compression as a replacement for `full_page_writes` or backups; each serves a different purpose.

## 11. synchronous_commit, fsync, and Durability Guarantees

A common misconception is that "having WAL" means **every COMMIT is durably flushed to physical disk before the client gets a response**, regardless of settings.

In truth, durability depends on choices such as:

- `synchronous_commit`: how strictly commit waits for local WAL flush and, under synchronous replication, standby confirmation.
- `fsync`: whether PostgreSQL issues OS sync calls to persist data to durable storage.
- `full_page_writes`: protection against torn pages.
- Storage hardware, OS, controllers, write caches, and whether flush acknowledgments are honest.

Inspect settings:

```sql
SHOW synchronous_commit;
SHOW fsync;
SHOW full_page_writes;
```

### 11.1. synchronous_commit = on

With `synchronous_commit = on` and **no synchronous standby configured**, PostgreSQL waits until the transaction's commit WAL is flushed locally before confirming commit to the client.

When synchronous replication is configured, `on` also waits for standby acknowledgment per `synchronous_standby_names` and actual setup. Never look solely at `synchronous_commit = on` to determine whether synchronous replicas exist.

### 11.2. synchronous_commit = off

With `synchronous_commit = off`, PostgreSQL can acknowledge commit before flushing that commit's WAL to durable storage. This reduces commit latency on some workloads, at the risk that **recently acknowledged transactions right before a crash can be lost**.

That does not mean "disabling `synchronous_commit` corrupts the database." The risk is **losing confirmed transactions whose WAL had not yet flushed durably**. Accepting that trade-off must come from business requirements, not merely chasing benchmark numbers.

### 11.3. fsync = off is a far more severe risk

Disabling `fsync` stops PostgreSQL from requesting durable OS storage syncs; after an OS crash or power loss, you risk **database corruption** beyond just losing recent transactions. Never disable `fsync` on systems requiring data integrity just to boost write speed.

### 11.4. Standby synchronization levels

PostgreSQL supports values like `remote_write` and `remote_apply` for synchronous replication. They control how far a standby must process WAL (written vs. replayed) before the primary confirms commit. They **do not replace** understanding local WAL flush boundaries, network latency, standby health, and failure modes.

In summary: when discussing RPO or durability guarantees, always state **the exact configuration and failure scope** (backend crash, OS crash, power loss, total disk failure, site outage) rather than claiming "PostgreSQL uses WAL so RPO is zero in every scenario."

## 12. Monitoring WAL and Checkpoints via SQL

Much monitoring data is exposed via system views and functions. Examples below target modern PostgreSQL; note that checkpoint views were reorganized in newer major versions.

### 12.1. WAL statistics

```sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full,
    stats_reset
FROM pg_stat_wal;
```

Typical columns:

| Column | Interpretation |
| --- | --- |
| `wal_records` | Number of WAL records generated since stats reset. |
| `wal_fpi` | Number of full-page images written to WAL. |
| `wal_bytes` | Total WAL bytes generated per stats counter. |
| `wal_buffers_full` | Number of times WAL buffers filled up per stats tracking. |
| `stats_reset` | Timestamp when these statistics were last reset. |

Values are **cumulative**, not "WAL bytes per second." To calculate rate, sample twice, subtract, and divide by elapsed seconds—checking `stats_reset` so resets do not skew deltas.

Using LSNs operationally to measure generation between two samples:

```sql
SELECT pg_current_wal_lsn();
```

Record the LSN before and after a fixed interval, then compute:

```sql
SELECT pg_wal_lsn_diff(
    '0/2000000'::pg_lsn,
    '0/1A00000'::pg_lsn
) AS wal_bytes_generated;
```

These LSNs **merely illustrate the calculation**. Monitoring scripts must substitute live measurements rather than treating example constants as server data.

### 12.2. Checkpoint statistics across major versions

In older PostgreSQL major versions, checkpoint metrics lived in `pg_stat_bgwriter`. In newer major versions—especially PostgreSQL 17+—checkpoint metrics moved to `pg_stat_checkpointer`.

Never copy `SELECT checkpoints_timed, checkpoints_req FROM pg_stat_bgwriter` from old docs assuming it works across every version.

**On servers with `pg_stat_checkpointer`**, query:

```sql
SELECT *
FROM pg_stat_checkpointer;
```

**On servers using the older layout**, inspect available columns in:

```sql
SELECT *
FROM pg_stat_bgwriter;
```

In `psql`, inspect columns on your exact version:

```text
\d+ pg_stat_checkpointer
\d+ pg_stat_bgwriter
```

Or via metadata SQL:

```sql
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'pg_catalog'
  AND table_name IN ('pg_stat_checkpointer', 'pg_stat_bgwriter')
ORDER BY table_name, ordinal_position;
```

Key metrics to watch include timed vs. requested checkpoints, write/sync times, and buffers written during checkpoints. Exact column names and structure **depend on major version**, so always check the matching manual.

### 12.3. Checkpoint logging

PostgreSQL supports logging checkpoints via `log_checkpoints`:

```sql
SHOW log_checkpoints;
```

When enabled, logs record checkpoint start, completion, write/sync durations, and buffer/WAL counts. These lines help diagnose frequent checkpoints, slow I/O, or shorter-than-expected intervals.

Illustrative log format:

```text
LOG:  checkpoint starting: time
LOG:  checkpoint complete: wrote ... buffers; ...
```

This is a structural sample, not live metrics. Correlate checkpoint timestamps with query latency spikes and WAL/replication events rather than blaming checkpoints blindly for every slowdown.

## 13. Why Can WAL Fill Up the Disk?

Rapid WAL growth does not automatically mean checkpoints are broken. Multiple causes look similar on disk while requiring completely different fixes.

| Cause | Signs to check | Direction to resolve |
| --- | --- | --- |
| Heavy write workload or excessive full-page images | `pg_stat_wal` climbs fast, frequent checkpoints, bulk loads/updates | Measure WAL rate, review workload and checkpoint settings. |
| Failing WAL archiving | `pg_stat_archiver` shows failures, `archive_command` errors in logs | Fix archive destination, permissions, copy command, and bandwidth. |
| Physical replication slot retaining WAL | Slot shows stale `restart_lsn`, standby disconnected long ago | Inspect consumer/slot and retention policy; never drop slots blindly. |
| Unconsumed logical replication slot | Logical slot not advancing, WAL retention growing | Check subscriber/decoder health and lag. |
| Large WAL retention config | `wal_keep_size` or backup/replication keeping segments | Evaluate RPO targets and standby catch-up window. |
| Slow checkpoints / insufficient I/O | Long checkpoint logs, many dirty pages, high disk latency | Measure storage I/O and capacity; do not just shrink `max_wal_size`. |

Inspect replication slots if permitted:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn
FROM pg_replication_slots
ORDER BY slot_name;
```

For a replication slot, `restart_lsn` marks the oldest WAL position the slot may still require. An inactive or lagging slot can cause `pg_wal` to grow continuously, especially without a slot retention cap.

**Never drop a replication slot** solely to reclaim disk space: the slot may be protecting a standby or logical subscriber's ability to catch up. Dropping it while a consumer still needs old WAL can force rebuilding the replica from scratch.

### 13.1. pg_stat_archiver

When WAL archiving is enabled:

```sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time
FROM pg_stat_archiver;
```

This shows whether archiving is progressing or failing repeatedly. However, **checking counters alone never proves your archive holds an intact PITR chain**; verify segment continuity, retention, base backups, and restore tests.

### 13.2. pg_wal does not keep all WAL forever

Once no longer needed for crash recovery, replication, or retention rules, WAL segments are recycled or deleted by PostgreSQL. If your backup strategy needs long-term WAL history, configure **WAL archiving to an external repository** rather than expecting `pg_wal` to keep data from months ago.

## 14. WAL, Replication, and Standby Recovery

WAL underpins **physical streaming replication**. The primary generates WAL; standbys receive the WAL stream and replay records to reproduce physical page changes in order.

```text
             PRIMARY
     SQL -> pages + WAL
                   |
                   v
              WAL stream
                   |
                   v
              STANDBY
          WAL receive / write
                   |
                   v
                WAL replay
                   |
                   v
              Data files
```

Standbys do not necessarily receive or replay every WAL record instantaneously. Distinct lag stages exist:

- **Send lag:** primary has not sent generated WAL yet.
- **Receive/write lag:** standby has not received/written all generated WAL.
- **Flush lag:** standby WAL is not yet flushed to the same position.
- **Replay lag:** standby has WAL locally but has not finished applying it to data files.

On the primary, when standbys are connected:

```sql
SELECT
    application_name,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    sync_state
FROM pg_stat_replication;
```

On the standby, you can inspect:

```sql
SELECT
    pg_is_in_recovery() AS is_standby_recovery,
    pg_last_wal_receive_lsn() AS last_received_lsn,
    pg_last_wal_replay_lsn() AS last_replayed_lsn;
```

When `pg_is_in_recovery() = true`, the instance is in recovery/standby mode; never mistake it for a writable primary. LSNs tell part of the story; interpret them alongside time-based lag, network health, and apply throughput.

### WAL and synchronous replication

Under synchronous replication, the primary waits for confirmation from one or more standbys depending on `synchronous_standby_names` and `synchronous_commit`. This alters commit acknowledgment rules and fault tolerance per configuration; it **does not guarantee every standby always holds identical live data at all instants**.

For instance, if a synchronous standby slows down or disconnects, synchronous commits can stall. That is a trade-off among multi-node durability, latency, and write availability. Evaluate business requirements rather than enabling a mode merely because its name includes "synchronous."

## 15. How Does Crash Recovery Differ from PITR?

Both use WAL, yet **solve completely different problems**:

**Crash recovery:** PostgreSQL uses existing data files and available WAL to restore consistent state after an abrupt termination. It does not require picking an arbitrary historical timestamp when restarting after an ordinary crash.

**Point-in-time recovery (PITR):** operators restore **a base backup** and replay archived WAL up to a chosen target timestamp or point—such as right before an accidental `DROP TABLE`. PITR requires a full backup and WAL archive strategy plus tested recovery procedures.

```text
CRASH RECOVERY:
  current data files + required available WAL
                |
                v
         consistent state after crash

PITR:
  base backup at T0
          |
          +--- continuous WAL archive T0 -> T1 -> T2 -> T3
                                         |
                                         v
                             choose recovery target T2
                                         |
                                         v
                               state at T2
```

### 15.1. Why can't you do PITR with WAL alone?

WAL records incremental changes, not full standalone data files capable of rebuilding a cluster from zero in normal setups. PITR requires:

1. A **valid base backup** of the database cluster.
2. A **continuous WAL chain** from the backup milestone to the recovery target.
3. Recovery configuration pointing PostgreSQL to archived WAL.
4. Matching extensions, tablespaces, configs, and environment requirements.
5. Verified restore testing.

If the entire data directory is lost and no base backup exists, holding a handful of WAL segments is **not enough** to recover the database.

### 15.2. WAL archiving

Conceptual configuration example:

```conf
wal_level = replica
archive_mode = on
archive_command = '... safely copy WAL segment to archive store ...'
```

The `archive_command` value above is a **conceptual placeholder**, not an executable shell command. Real deployments use proven backup tooling or safe, idempotent copy/verify scripts with error handling, data protection, and strict access controls.

If archiving fails repeatedly, PostgreSQL retains WAL segments longer, causing `pg_wal` to grow. Never disable archiving or delete WAL without understanding historical recovery requirements.

### 15.3. Recovery targets, timelines, and promotion

Modern PostgreSQL major versions configure archive recovery with `restore_command`, `recovery_target_*` parameters, and `recovery.signal` or `standby.signal` marker files. Older versions used `recovery.conf`; never copy outdated `recovery.conf` instructions onto modern servers.

Recovering to a past point in time and opening the database for writes creates a new timeline. Backup tooling must manage **timeline history** rather than naively assuming "WAL segments with matching LSNs belong to the same data history."

## 16. UNLOGGED and TEMPORARY: Durability Exceptions

By default, ordinary PostgreSQL tables are **logged tables** whose changes are recorded in WAL. However, PostgreSQL has special table types that do not share the same crash recovery guarantees.

### 16.1. UNLOGGED tables

```sql
CREATE UNLOGGED TABLE wal_lab.import_staging (
    batch_id bigint NOT NULL,
    item_code text NOT NULL,
    raw_payload jsonb NOT NULL
);
```

`UNLOGGED` tables work well for reproducible staging data because their contents are not protected by WAL like logged tables. Important consequences:

- Unlogged table contents are **not crash-safe** like logged tables.
- After a crash or unclean shutdown, unlogged tables are **truncated** during recovery.
- Unlogged table data is **not replicated** to standbys via physical WAL streaming replication.

Never use `UNLOGGED` for ledgers, paid orders, or irreplaceable business data merely to speed up writes.

### 16.2. TEMPORARY tables

```sql
CREATE TEMP TABLE temp_daily_totals (
    report_date date,
    total numeric(14, 2)
) ON COMMIT DROP;
```

Temporary tables live only for the session or transaction as defined. With `ON COMMIT DROP`, the table vanishes when the creating transaction commits. Temporary table data is never meant to survive session termination or crashes.

**Distinguishing the three table kinds:**

| Table kind | Typical purpose | Post-crash durability |
| --- | --- | --- |
| Logged table | Durable business data | Protected by WAL and recovery per durability settings. |
| Unlogged table | Reproducible staging/cache data | Contents can be lost/truncated after crash; never use for irreplaceable data. |
| Temporary table | Session scratch data | Does not persist past session/transaction boundaries per its rules. |

Creating one `UNLOGGED` table does not turn off WAL for the whole database. Other logged tables and system metadata retain full WAL protection; never assume "the entire database skips WAL now."

## 17. Real-World Scenario: Checkpoints Occurring Too Frequently

Suppose an OLTP server logs:

```text
LOG:  checkpoints are occurring too frequently ...
HINT: Consider increasing the configuration parameter "max_wal_size".
```

This suggests WAL generation is triggering WAL-based checkpoints too close together, though you should measure before changing settings.

Analysis steps:

1. Check current `checkpoint_timeout`, `max_wal_size`, and `checkpoint_completion_target`.
2. Inspect timed vs. requested checkpoint counts in the appropriate stats view **for your major version**.
3. Check WAL generation in `pg_stat_wal` and full-page image counts.
4. Correlate checkpoint logs with disk latency and application write bursts.
5. Consider adjusting WAL/checkpoint targets within disk capacity and recovery-time SLAs, then re-measure.

The trade-off:

- Less frequent checkpoints reduce heavy flush bursts and can reduce WAL from full-page images in some workloads.
- However, more WAL accumulates between checkpoints, increasing redo work during crash recovery.
- Checkpoints must still satisfy recovery-time targets and storage throughput.

No single `max_wal_size` fits every server. Configuration depends on WAL rate, RAM, storage throughput, RTO goals, and replication/backup needs.

## 18. Real-World Scenario: pg_wal Grows While Checkpoints Run Normally

Suppose `pg_wal` grows continuously even though logs show checkpoints completing regularly. Likely culprits include a **replication slot retaining old WAL** or **failing WAL archiving**, not broken checkpoints.

Check:

```sql
SELECT slot_name, slot_type, active, restart_lsn
FROM pg_replication_slots;

SELECT
    archived_count,
    last_archived_time,
    failed_count,
    last_failed_time
FROM pg_stat_archiver;
```

Then correlate:

- Is an inactive replication slot pinning a very old `restart_lsn`?
- Is a standby down or failing to catch up?
- Is `archive_command` failing or is the archive target out of space?
- Is `wal_keep_size` or a backup tool pinning WAL segments?

In principle, checkpoints free **some** older WAL from crash-recovery duties, yet segments remain pinned if other consumers need them. That is why `pg_wal` usage cannot be explained by checkpoints alone.

### What never to do

Never run:

```bash
# NEVER RUN THIS: dangerous operation shown as anti-pattern.
rm -f /path/to/pgdata/pg_wal/*
```

That destroys crash recovery and replication integrity. In a disk-full incident, prioritize assessing WAL/backup/replication status and adding storage or fixing the retention blocker through supported tools and procedures.

## 19. Real-World Scenario: Disconnecting Right at COMMIT

Consider an order-creation workflow:

```sql
BEGIN;

INSERT INTO orders (
    request_key, order_id, customer_id, amount
) VALUES (
    'checkout-2026-00017', 50017, 101, 250000
);

COMMIT;
```

Suppose the client sends `COMMIT` and loses the network connection before receiving the response. Two outcomes are possible:

- The transaction **committed**, yet the acknowledgment never reached the client.
- The transaction **did not commit**, e.g., the connection failed before transaction confirmation completed.

WAL and crash recovery ensure the database recovers consistent state per durable records, yet **cannot tell a client whether its request succeeded** when the response packet was lost.

Therefore, applications need:

1. An immutable `request_key` per business action.
2. A `UNIQUE` constraint enforcing idempotency.
3. Result lookup after reconnecting.
4. Retry logic distinguishing transient failures, duplicate-key errors, and business errors.

Without idempotency, retrying with a fresh `order_id` can create duplicate orders even though PostgreSQL recovered cleanly.

> The `INSERT INTO orders` snippet illustrates business flow only; it assumes an `orders` table with matching columns and constraints exists. Never run it directly on production tables lacking that structure.

## 20. "WAL Flushed, Data Page Not Flushed" and Its Consequences

Test your understanding against four cases:

**Case A — Commit WAL flushed, data page not flushed, then crash.**

Under standard durability assumptions and healthy storage, PostgreSQL replays WAL to recover the committed change. That is exactly what write-ahead logging is built for.

**Case B — Data page written to disk, transaction never COMMITted, then crash.**

Physical pages may hold uncommitted bytes, yet an uncommitted transaction is never treated as committed. PostgreSQL enforces MVCC and transaction status during recovery to keep state consistent.

**Case C — Power drops right after a checkpoint completes.**

Recovery uses the checkpoint to choose the redo start point, then replays any WAL generated **after** that checkpoint. Checkpoints do not freeze the database at completion time.

**Case D — COMMITted with `synchronous_commit = off`, then immediate crash.**

Recently acknowledged transactions whose WAL had not yet flushed durably risk being lost. Never claim the same durability guarantees as the synchronous default.

## 21. Practice Exercises

Use only an authorized lab PostgreSQL environment. Read-only queries below do not modify data; server shutdowns or modifying recovery parameters are not required exercises.

### Exercise 1. Observing WAL and checkpoint settings

```sql
SELECT name, setting, unit, context, source
FROM pg_settings
WHERE name IN (
    'wal_level',
    'synchronous_commit',
    'fsync',
    'full_page_writes',
    'wal_compression',
    'checkpoint_timeout',
    'max_wal_size',
    'min_wal_size',
    'checkpoint_completion_target'
)
ORDER BY name;
```

**Question:** which settings govern WAL durability, which primarily govern checkpoints, and which govern WAL size targets?

**Hint:** `synchronous_commit` and `fsync` control durability synchronization; `full_page_writes` protects recovery against torn pages; `checkpoint_timeout` and `checkpoint_completion_target` control checkpoint pacing; `max_wal_size` and `min_wal_size` set WAL sizing targets.

### Exercise 2. Reading WAL statistics

```sql
SELECT wal_records, wal_fpi, wal_bytes, stats_reset
FROM pg_stat_wal;
```

**Task:** sample values at two timestamps separated by real workload. Explain the difference between cumulative totals and WAL generation rate over time.

**Hint:** the delta in `wal_bytes` is the WAL generated between samples if `stats_reset` did not change. Divide by elapsed seconds to estimate bytes/sec.

### Exercise 3. Distinguishing checkpoint and commit

Suppose an application executes:

```sql
BEGIN;
UPDATE wal_lab.account_balances
SET balance = balance + 50
WHERE account_id = 202;
ROLLBACK;
```

**Question:** if a checkpoint happens to run during this transaction, will the +50 update persist after `ROLLBACK`?

**Answer:** No. Checkpoints never commit transactions. PostgreSQL still enforces transaction semantics and MVCC.

### Exercise 4. Checking replica replay

On a standby where stats access is permitted:

```sql
SELECT
    pg_is_in_recovery(),
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn();
```

**Question:** if receive LSN advances faster than replay LSN, what can you infer?

**Hint:** the standby has received newer WAL than it has finished applying. Check replay lag, system resources, and connection state; a single snapshot alone does not prove replication is broken.

### Exercise 5. Identifying why WAL is retained

A server's `pg_wal` keeps growing, and `pg_replication_slots` shows a slot with `active = false` and a very old `restart_lsn`.

**Question:** what does this suggest, and what should you check first?

**Suggested answer:** the inactive slot is retaining WAL so a consumer can catch up, driving disk growth. Before dropping or altering the slot, identify which consumer owns it, whether it is still needed, and how it would be rebuilt if old WAL is lost.

### Exercise 6. Crash recovery or PITR?

Classify each scenario:

1. Server loses power, reboots on the same data directory, and PostgreSQL replays WAL automatically.
2. An operator runs `DROP TABLE` by mistake; the DBA wants to rebuild state before that command using a base backup and archived WAL.
3. The primary streams WAL to a standby so the standby applies recent changes.

**Answer:** (1) crash recovery; (2) PITR; (3) physical streaming replication. All three rely on WAL, yet differ in goals, inputs, and operations.

### Exercise 7. Is an UNLOGGED table suitable for paid orders?

```sql
CREATE UNLOGGED TABLE wal_lab.paid_orders_tmp (
    order_id bigint PRIMARY KEY,
    paid_amount numeric(14, 2) NOT NULL
);
```

**Question:** should this table serve as the sole source of truth for paid transactions?

**Answer:** No. Unlogged table data lacks WAL crash-recovery protection and can be truncated after a crash. Use it only when data loss is acceptable or contents can be regenerated.

### Exercise 8. Inspecting checkpoint stats on your version

In `psql`:

```text
\d+ pg_stat_bgwriter
\d+ pg_stat_checkpointer
```

**Task:** on your server, determine which view exposes checkpoint stats and compare with the manual for that major version. If one view does not exist, that does not mean the server is broken; stats views differ across versions.

## 22. Common Misconceptions

**1. "COMMIT must flush every table data page to disk."** No. WAL makes transaction confirmation durable per settings without flushing every data page at commit time.

**2. "WAL is a complete backup."** No. WAL supports redo, replication, and PITR, yet PITR requires a valid base backup plus the full WAL chain.

**3. "A checkpoint is a database-wide COMMIT."** No. Checkpoints flush dirty pages and record recovery milestones without committing application transactions.

**4. "A checkpoint deletes all older WAL immediately."** No. WAL may still be pinned by replication slots, standbys, archiving, or backups.

**5. "`max_wal_size` is a hard quota on `pg_wal`."** No. Actual disk usage can exceed that target.

**6. "With WAL enabled, `synchronous_commit = off` still keeps every COMMIT after a crash."** No. Acknowledged transactions whose WAL has not flushed durably can be lost.

**7. "`fsync = off` only loses a bit of recent data."** The risk is far worse, including database corruption after OS or storage crashes.

**8. "Crash recovery replays only committed transactions row by row."** WAL redo is physical page recovery; transaction status and MVCC determine logical visibility.

**9. "WAL segments are always exactly 16 MB."** 16 MiB is the common default, yet segment size can be customized at cluster initialization.

**10. "Delete files in `pg_wal` to free disk space."** Doing so can break recovery or replication. Always investigate why WAL is retained.

**11. "`UNLOGGED` tables are just as durable because they live inside PostgreSQL."** No. Unlogged contents can be lost after a crash and are not replicated via physical WAL streaming like logged tables.

**12. "Reads on a standby always see the latest primary COMMIT immediately."** Receive/replay lag can exist. Check synchronous replication settings and application consistency needs.

**13. "One checkpoint stats view works identically on every major version."** No. Stats views and columns evolve across major releases, such as splitting `pg_stat_checkpointer` from `pg_stat_bgwriter`.

**14. "Successful restart after crash means backups and DR are covered."** Crash recovery handles one failure mode; accidental drops, total storage loss, and site outages require independent backups, PITR, and DR.

## 23. Troubleshooting Workflow Along the WAL Axis

When facing unexpected restarts, write stalls, or surging WAL usage, follow this diagnostic sequence:

```text
1. Is the issue a CRASH, logical data loss, or replication lag?
                           |
                           v
2. Is the server running as primary or standby?
                           |
                           v
3. How far has WAL been generated, written, flushed, received, and replayed?
                           |
                           v
4. What do recent checkpoints and I/O metrics look like?
                           |
                           v
5. Are archiving, replication slots, or backups retaining WAL?
                           |
                           v
6. Do durability settings trade off RPO?
                           |
                           v
7. Safe action: restore, expand disk, fix archive/consumer,
   or tune checkpoints based on evidence and runbooks
```

In production systems, always record **PostgreSQL version**, incident timestamp, WAL position/timeline, relevant parameters, log excerpts, and backup status before changing state. Never run low-level repair tools, delete WAL, or force promotion before understanding data state and dependent systems.

## 24. Summary

Remember the relationship among these three mechanisms in one sentence: **WAL protects the change history needed for redo; checkpoints bound how much history must be replayed after a crash; crash recovery combines data files and WAL to restore consistent state**.

- **WAL** is written ahead of data pages per the write-ahead rule. LSNs mark positions in the WAL stream; logged records enable recovery even when data pages have not flushed.
- **COMMIT** ends a transaction, while the durability of that acknowledgment depends on `synchronous_commit`, `fsync`, and storage reliability.
- **Checkpoints** coordinate flushing dirty pages and record redo milestones; they do not commit transactions, replace backups, or automatically delete all old WAL segments.
- **Crash recovery** replays WAL from the checkpoint-determined start point, coordinating with transaction status and MVCC so only committed changes become visible after restart.
- **Replication** streams and replays WAL on standbys; **PITR** combines a base backup with archived WAL to restore to a chosen point in time.
- **Safe operations** require monitoring WAL, checkpoint, archiver, and replication slot stats, configurations, and logs—while never manually deleting files inside `pg_wal`.

Understanding this big picture explains why PostgreSQL can return `COMMIT` rapidly yet recover cleanly from power loss, why checkpoints influence I/O patterns, why WAL can grow large on disk, and why backups and replication are distinct from crash recovery.
