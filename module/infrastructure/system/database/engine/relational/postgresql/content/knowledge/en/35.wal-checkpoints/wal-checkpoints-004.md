# Checkpoints, Redo Points, and Crash Recovery Time in PostgreSQL

PostgreSQL records data changes first in the **Write-Ahead Log (WAL)**. Data pages in data files may be written to disk later, via checkpoints or the background writer. When the server crashes, PostgreSQL needs to know where in WAL to begin reading to bring data pages back to a consistent state. That starting position is called the **redo point**.

A checkpoint is a critical consistency milestone in the WAL sequence. It helps PostgreSQL determine which older WAL is no longer needed for crash recovery of the current cluster once all related conditions are satisfied. The distance from the most recent checkpoint to the crash time directly affects how much WAL must be replayed and is a major factor in **crash recovery time**.

These concepts are closely related but not synonymous:

```text
WAL record      = log entry describing a change needing redo
Checkpoint      = process of writing dirty data pages and creating a checkpoint marker
Checkpoint LSN  = position of the checkpoint record
Redo LSN        = WAL position where crash recovery must start replaying
Crash recovery  = replaying WAL from the redo point to restore a consistent state
```

More frequent checkpoints can reduce the amount of WAL to replay after a crash, yet can also increase write I/O, cause checkpoint bursts, and increase full-page images in WAL. Therefore, checkpoint tuning is a trade-off among **durability, write performance, WAL volume, and RTO targets**, rather than simply setting checkpoints as short as possible.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why PostgreSQL needs WAL and checkpoints.
2. Distinguish between a checkpoint, checkpoint record, checkpoint LSN, and redo LSN.
3. Describe the checkpoint creation process and conditions for a checkpoint to complete safely.
4. Explain how crash recovery starts from the redo point and replays WAL.
5. Distinguish between crash recovery, archive recovery/PITR, and standby recovery.
6. Understand the relationship among checkpoint interval, `max_wal_size`, `checkpoint_timeout`, and `checkpoint_completion_target`.
7. Explain full-page images, `full_page_writes`, and the impact of checkpoints on WAL volume.
8. Monitor checkpoints using `pg_stat_checkpointer` or the corresponding view for your PostgreSQL major version.
9. Use `pg_control_checkpoint()` and `pg_controldata` to inspect checkpoint and redo information.
10. Distinguish primary checkpoints from standby restartpoints.
11. Analyze WAL retention, archive backlogs, replication slots, and disk growth.
12. Estimate recovery time, define RTO/RPO, and design recovery verification tests.
13. Tune checkpoints with measurements and avoid configurations that cause I/O spikes.

## 2. WAL Is the Foundation of Crash Recovery

WAL is a sequential log recording the information needed to recover database changes. The core rule of Write-Ahead Logging:

> **A WAL record describing a change must be durably written before the data page containing that change is allowed to be written to storage.**

### 2.1. Why Not Write Every Data Page Immediately?

A single transaction can modify many rows, indexes, and pages. If every change required writing data pages immediately, random I/O and sync costs would be very high. PostgreSQL batches WAL records into a sequential stream and writes data pages later on a background/checkpoint schedule.

Example:

```text
Transaction UPDATE account
       |
       v
Buffer page in shared_buffers modified (dirty)
       |
       +---- WAL records generated
       |
       v
WAL flushed to durable storage when COMMIT requires
       |
       v
Data page can be written to disk later
```

If the server loses power after COMMIT was confirmed but before the data page was written, WAL still lets PostgreSQL redo the change on restart, provided configuration and storage satisfy durability assumptions.

### 2.2. WAL Record and LSN

Every position in WAL is represented by a **Log Sequence Number (LSN)**. An LSN is a byte address in the WAL stream, typically shown as two hexadecimal parts:

```text
0/16B6C50
0/16B7000
0/16B9A20
```

LSNs increase monotonically as WAL is generated. An LSN is not a timestamp, transaction ID, or row sequence number. Two LSNs 1 MB apart do not mean 1 second has elapsed; WAL generation rate depends on workload.

### 2.3. WAL Segment

WAL is split into fixed-size segment files (commonly 16 MB by default, selectable at initdb). Files reside in the `pg_wal` directory. Segment filenames encode the timeline and LSN range.

An LSN maps to:

- The WAL segment containing that byte.
- The offset within that segment.

Never manually edit, truncate, rename, or delete files in `pg_wal`. PostgreSQL manages segment recycling and removal based on checkpoints, archiving, replication, and other WAL retention requirements.

### 2.4. COMMIT and Durability

Under the standard configuration `synchronous_commit=on`, PostgreSQL waits for the transaction's WAL to flush to durable storage before reporting COMMIT success to the client. Data pages may not have been written yet, because WAL is sufficient for recovery.

`synchronous_commit=off` lets the client receive acknowledgement before WAL is flushed; the database still maintains crash recovery consistency, yet recently confirmed transactions can be lost if the server crashes before flushing. Checkpoint tuning does not replace durability policy.

### 2.5. WAL Is Not a Complete Database Copy

WAL is meaningful only when paired with the corresponding data files or base backup. You cannot take a standalone WAL directory and rebuild an entire database from scratch without a matching base backup or data directory.

## 3. What Is a Checkpoint?

A checkpoint is a coordinated PostgreSQL process that:

1. Ensures required WAL has been flushed.
2. Writes relevant dirty buffers down to data files.
3. Creates a checkpoint record in WAL.
4. Updates checkpoint information in the control file so startup knows the most recent valid checkpoint.

Once a checkpoint completes, PostgreSQL has a milestone from which it can determine the redo point needed for any subsequent crash recovery.

### 3.1. What Is a Dirty Page?

A page in shared buffers is called **dirty** when its contents in RAM differ from the version on storage. For example, an UPDATE to a row can dirty a heap page and one or more index pages.

An unwritten dirty page does not mean data is lost. If the corresponding WAL record is durable, PostgreSQL can reapply the change after a crash.

### 3.2. A Checkpoint Is More Than Just "Flush WAL"

WAL flushing and data page flushing are two separate operations:

- **WAL flush:** writing the log up to a durable LSN.
- **Data page write:** writing heap/index/system catalog pages to data files.

A checkpoint coordinates both following the WAL rule. Flushing WAL alone does not complete a checkpoint; writing data pages before their WAL is durable violates the WAL rule.

### 3.3. Checkpoint Record

Near the end of a checkpoint, PostgreSQL writes a special record into WAL. This record carries checkpoint metadata, including the **redo pointer**—the LSN where crash recovery must start redoing.

The checkpoint record is written at a different LSN than the redo pointer. That is why you should not refer to both indiscriminately as "checkpoint LSN."

### 3.4. A Checkpoint Is a Milestone, Not a Backup

A checkpoint does not create an independent copy you can restore to that point in time. It does not replace a base backup, WAL archive, replication, or storage snapshots. It primarily defines a recovery start point and syncs dirty pages.

### 3.5. A Checkpoint Does Not Mean Every Transaction Finished

Checkpoints can run while other transactions remain active. Uncommitted transactions do not become committed merely because a checkpoint occurred. Checkpoints ensure data/WAL consistency, while row visibility still follows MVCC and transaction status.

### 3.6. Shutdown Checkpoint

When PostgreSQL shuts down in normal or fast mode, the server performs a checkpoint so it can restart in a clean state. Immediate shutdown skips normal shutdown/checkpoint steps, requiring crash recovery on the next startup.

## 4. Checkpoint LSN and Redo LSN

These two positions are very easy to confuse.

### 4.1. Checkpoint LSN

**Checkpoint LSN** typically refers to the position of the checkpoint record written in WAL. It identifies the checkpoint record referenced by the control file.

### 4.2. Redo LSN

**Redo LSN** is the starting position for WAL replay required during crash recovery. PostgreSQL reads from the redo point and applies WAL records sequentially up to the last valid WAL available in the recovery stream.

The redo point typically sits **before** the checkpoint record, because changes occurring while or since the checkpoint began may have produced dirty pages that still need to be written or replayed.

### 4.3. Timeline Example

```text
WAL LSN increasing --------------------------------------------------->

      Redo LSN                Checkpoint record
         |                           |
         v                           v
---------+---------------------------+-------------------------------+
         |<---- Required WAL ------->|
         |
         +-- Startup crash recovery starts here

After checkpoint completes, a crash occurs:
      |
      v
Recovery replays from redo LSN to the last valid WAL
```

This diagram illustrates conceptual relationships only; specific LSNs and other records may be interleaved.

### 4.4. Why Does Redo LSN Not Equal Checkpoint LSN?

The checkpoint record marks the completed checkpoint milestone. However, to guarantee all changes can be recovered, PostgreSQL must replay from an earlier LSN where data pages were not yet guaranteed to reflect all subsequent changes.

Therefore:

- Checkpoint LSN answers: **Where is the current checkpoint record?**
- Redo LSN answers: **If a crash happens right now, where must WAL replay start?**

### 4.5. Redo LSN Is Not the LSN of an Uncommitted Transaction

The redo point does not mean "transactions started here" or "every transaction after this must commit." It is the position in WAL needed to reconstruct consistent page state. Transaction visibility is governed by transaction status and MVCC, not inferred from the redo LSN alone.

### 4.6. Redo Distance

You can observe the distance between current WAL and redo LSN to estimate the scope of WAL requiring replay:

```sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_control_checkpoint().redo_lsn AS redo_lsn,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        pg_control_checkpoint().redo_lsn
    ) AS bytes_since_redo;
```

This is an **LSN byte distance**, not an exact prediction of recovery time. It can shift as soon as a checkpoint finishes and does not reflect all I/O, CPU, and replay costs.

## 5. When Does a Checkpoint Happen?

PostgreSQL can initiate a checkpoint for several reasons.

### 5.1. checkpoint_timeout

`checkpoint_timeout` caps the maximum time interval between automatic checkpoints during normal operation. A common default is 5 minutes, though you should check your exact major version and environment configuration.

```sql
SHOW checkpoint_timeout;
```

If a workload generates little WAL and stays below the WAL threshold, timeout will trigger the next checkpoint.

### 5.2. max_wal_size

`max_wal_size` sets a soft target for WAL generated between automatic checkpoints. When WAL generated since the previous checkpoint exceeds the estimated threshold, PostgreSQL can request an earlier checkpoint before timeout.

```sql
SHOW max_wal_size;
```

This is **not a hard cap** on `pg_wal` size. WAL can exceed max_wal_size because of:

- Slow or failing archive commands.
- Replication slots pinning old WAL.
- Standbys lagging in receiving or replaying WAL.
- Checkpoints unable to finish quickly enough or workloads generating WAL rapidly.
- Other operational conditions requiring segment retention.

### 5.3. Manual CHECKPOINT

A superuser or a role with `pg_checkpoint` privilege can invoke:

```sql
CHECKPOINT;
```

This requests an immediate checkpoint. Do not run it repeatedly from an application or cron just to "push data to disk"; frequent manual checkpoints increase I/O and WAL full-page images.

### 5.4. Shutdown Checkpoint

A normal or fast shutdown executes a checkpoint to close the cluster cleanly. An immediate shutdown skips normal steps, and the subsequent startup will require crash recovery.

### 5.5. Checkpoints Are Not Triggered by Every COMMIT

COMMIT primarily needs WAL flushed per durability settings; it does not force all dirty data pages to disk immediately. Running a checkpoint for every transaction would cause massive I/O overhead.

### 5.6. Checkpoint Request vs. Checkpoint Completion

A checkpoint may start due to timeout or a WAL threshold, yet writing pages can take a while. `checkpoint_completion_target` paces completion across the expected checkpoint interval. Thus request time, start time, and completion time do not necessarily coincide.

## 6. How Does the Checkpoint Process Work?

Conceptually, a checkpoint coordinates:

1. Determining the target WAL position and dirty buffers involved.
2. Ensuring WAL preceding page writes is flushed per the WAL rule.
3. Writing dirty buffers out to data files, potentially spread over time.
4. Completing the checkpoint and writing the checkpoint record.
5. Updating control information so the next startup identifies the valid checkpoint.

Internal details can vary across PostgreSQL major versions, but the WAL-before-data principle and redo pointer remain foundational.

### 6.1. Background Writer and Checkpointer

The background writer can write dirty buffers ahead of a checkpoint to reduce pressure on backends and the checkpointer. The checkpointer is responsible for completing checkpoints and writing the buffers required to uphold checkpoint semantics.

The two components have related yet distinct roles:

- The background writer runs continuously in the background to reduce how often backends must write dirty buffers when allocating free buffers.
- The checkpointer executes systematic checkpoint work and updates checkpoint statistics.

### 6.2. Backends Can Also Write Dirty Buffers

A backend may have to write dirty buffers in certain situations, such as needing to free a buffer. Not every data page write is performed by the checkpointer. Consequently, checkpoint statistics do not represent total database write I/O.

### 6.3. Checkpoint Flushes

A checkpoint may need to write a great many pages. Concentrating writes into a short window can spike storage latency and query latency. PostgreSQL tries to spread writes out to dampen bursts.

### 6.4. WAL Must Precede Data Pages

When the checkpointer prepares to write a data page with a newer LSN, the corresponding WAL must be flushed at least through the required LSN before the page is written. This protects redo capability if the data page write is torn or lost in a crash.

### 6.5. The Milestone Updates Only After Checkpoint Completion

PostgreSQL cannot declare a new checkpoint valid until all required page/WAL write conditions have completed. If the server crashes mid-checkpoint, startup falls back to the previous valid checkpoint and replays WAL from the older redo point.

### 6.6. Checkpoints Do Not Halt All Queries

Queries and transactions continue running while a checkpoint executes. Required internal locks and page latches are managed internally; a checkpoint is not a "freeze the whole database" command.

## 7. Crash Recovery: How Does PostgreSQL Use the Redo Point?

When the server starts and detects the previous shutdown was not clean, PostgreSQL performs crash recovery.

### 7.1. Reading Control File State

Startup reads the control file (`global/pg_control`) to locate the most recent valid checkpoint and required redo metadata. The control file holds critical metadata such as:

- Checkpoint location.
- Redo location.
- Timeline ID.
- Cluster state and related WAL/checkpoint fields.

The control file is vital internal state. Never edit it with a hex editor or copy it from another cluster.

### 7.2. Starting Replay from the Redo LSN

PostgreSQL locates the needed WAL segment, reads records sequentially, and redoes changes onto data pages. WAL records can describe modifications to heaps, indexes, catalogs, transaction status, and other internal structures.

### 7.3. Page LSN Helps Determine Whether a Record Was Already Applied

A data page stores an LSN describing the latest WAL record reflected on that page. During redo, PostgreSQL can compare the page's LSN against the record's LSN to decide whether the change needs to be reapplied.

This helps recovery handle situations where some pages were written to disk before the crash while others were not.

### 7.4. Redo and Transaction Visibility

PostgreSQL relies primarily on **redo**, rather than a traditional undo log that reverses every uncommitted change like some other database engines.

During recovery:

- Required WAL records are replayed so page structures are consistent.
- Transaction commit/abort status is restored from WAL and transaction status data.
- Transactions active at crash time are not treated as committed without a valid commit record.
- Uncommitted tuples do not become visible valid data to applications; cleanup of unneeded versions proceeds later via vacuum.

Therefore, "redoing a page" does not mean uncommitted transaction data is exposed to users.

### 7.5. Recovery Ends at the Last Valid WAL

Crash recovery replays WAL continuously through the last recoverable point. If archive reading is configured, PostgreSQL can request subsequent segments per recovery settings. For standard crash recovery on a primary, once the valid end is reached and startup finishes, the database opens for connections.

### 7.6. Recovery Can Detect Missing or Corrupt WAL

If a required WAL segment is missing, corrupted, or mismatches the timeline/system identifier, recovery can halt with an error. Never delete WAL or drop in a mismatched segment just to "get the server running"; inspect the data directory, archive chain, timeline, and matching base backup.

### 7.7. Why Do Checkpoints Shorten Crash Recovery?

The redo LSN is the replay starting point. A newly completed checkpoint advances the redo point closer to current WAL, shrinking the WAL range that must be read after a crash. However, recovery time also depends on I/O, WAL record types, data pages read/written, and hardware; redo distance is only one indicator.

## 8. Checkpoints and Full-Page Images (FPI)

Checkpoints affect WAL volume through the **full_page_writes** mechanism.

### 8.1. What Is a Torn Page?

A data page may be written to storage across multiple sectors or blocks. If power fails mid-write, the page may be only partially written (**torn page**). In that case, replaying small delta changes from WAL alone may not suffice to reconstruct a valid page.

### 8.2. full_page_writes

When `full_page_writes=on`, PostgreSQL logs a full-page image (FPI) of a page into WAL on the first modification to that page after a checkpoint (per the applicable rules). If a page becomes torn, recovery can use the FPI to restore the entire page before applying subsequent changes.

```sql
SHOW full_page_writes;
```

This setting should normally remain enabled. Disabling FPIs when storage can produce torn writes risks unrecoverable page corruption; only consider changing it with verified hardware/filesystem atomic-write guarantees and risk evaluation.

### 8.3. Frequent Checkpoints Can Increase WAL

After every checkpoint, pages modified for the first time can emit FPIs. If checkpoints happen too often, the same hot pages can generate many FPIs over a shorter span. WAL volume can grow substantially, particularly in workloads updating many pages.

### 8.4. WAL Compression

`wal_compression` compresses full-page images to reduce WAL size at the expense of CPU. Depending on PostgreSQL version, specific supported compression algorithms can be chosen:

```sql
SHOW wal_compression;
```

Check documentation for your exact major version before selecting an algorithm. Compressing FPIs does not mean every WAL record is compressed.

### 8.5. wal_log_hints

`wal_log_hints` instructs PostgreSQL to log hint-bit changes to WAL to support features such as data-checksums page protection and pg_rewind prerequisites per documentation. It can also influence FPI and WAL volume. Do not toggle it blindly; check replication/rewind requirements and cluster configuration.

### 8.6. Measuring FPIs

The `pg_stat_wal` view exposes `wal_fpi` on supported versions:

```sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full
FROM pg_stat_wal;
```

If `wal_fpi` makes up a large fraction of total WAL, inspect checkpoint frequency, workload page churn, `full_page_writes`, compression, and recent configuration changes.

### 8.7. Do Not Arbitrarily Disable full_page_writes to "Save WAL"

FPIs have a cost, yet they exist to protect page integrity after a crash. Optimize checkpoints, compression, storage, and workloads before considering weakening durability safeguards.

## 9. Important Checkpoint Parameters

Checkpoint tuning primarily relies on a small group of interrelated parameters.

### 9.1. checkpoint_timeout

Caps the time interval between automatic checkpoints. Raising it reduces timed checkpoints, yet redo distance after a crash can grow longer and WAL may be retained longer by checkpoints.

### 9.2. max_wal_size

Soft target for WAL generated between automatic checkpoints. Increasing it generally spaces out WAL-triggered checkpoints, lowering checkpoint frequency in write-heavy workloads, but requires sufficient disk capacity and backup/replication planning.

### 9.3. min_wal_size

`min_wal_size` sets the minimum WAL volume PostgreSQL tries to keep for reuse in `pg_wal`, avoiding constant file deletion and recreation as workload fluctuates.

```sql
SHOW min_wal_size;
```

It is not a minimum bound for WAL archives and does not guarantee WAL needed by replicas or archiving is kept indefinitely.

### 9.4. checkpoint_completion_target

Controls the target fraction of the checkpoint interval over which checkpoint writes are spread before the next checkpoint. Higher values usually distribute writes more evenly and reduce bursts, without eliminating the total dirty pages that must be written.

Example:

```sql
SHOW checkpoint_completion_target;
```

Do not misinterpret this parameter as "the checkpoint only finishes 90% of its work." It is the target proportion of the expected checkpoint interval used to pace the writes.

### 9.5. checkpoint_flush_after

`checkpoint_flush_after` sets the byte threshold written before prompting the kernel to flush dirty data to storage (when the platform supports the semantics). It can help limit dirty data piling up in the OS cache, though effectiveness depends on filesystem, kernel, and storage.

### 9.6. checkpoint_warning

`checkpoint_warning` logs a warning if WAL-volume-triggered checkpoints happen too frequently. It is a diagnostic signal that `max_wal_size` may be too low for the WAL generation rate; it does not fix the cause on its own.

### 9.7. wal_buffers

`wal_buffers` is shared memory buffering WAL records, not checkpoint size. It affects how backends write WAL; PostgreSQL usually picks a sensible default at startup. Do not raise wal_buffers as a substitute for checkpoint tuning when the bottleneck is data-page I/O.

### 9.8. wal_writer_delay and wal_writer_flush_after

WAL writer parameters control background WAL flush cadence and byte thresholds. They can affect WAL latency and throughput, but do not replace the COMMIT durability contract or checkpoints.

### 9.9. Qualitative Impact Table

| Parameter | Raising the value tends to | Trade-offs to watch |
| --- | --- | --- |
| `checkpoint_timeout` | Trigger fewer timed checkpoints. | Redo distance after a crash may grow longer. |
| `max_wal_size` | Allow more WAL between checkpoints. | `pg_wal` / retention may require more disk space. |
| `min_wal_size` | Keep more segments around for reuse. | Pre-reserves disk space. |
| `checkpoint_completion_target` | Spread checkpoint writes across more of the interval. | Can push writes closer to the next checkpoint; workload/storage still must be measured. |
| `checkpoint_flush_after` | Raise the byte threshold before requesting a flush. | Dirty pages may accumulate more depending on platform. |
| `wal_buffers` | Reduce contention/buffer pressure in high-WAL workloads. | Uses more shared memory; does not fix checkpoint I/O. |
| `wal_compression` | Reduce WAL bytes from FPIs. | Consumes more CPU. |

Optimal values depend on WAL rate, storage speed, page churn, archive/replication lag, and RTO targets.

## 10. Checkpoint Frequency and Recovery Time: The Trade-Off

### 10.1. Frequent Checkpoints

Advantages:

- Redo point stays closer to current WAL.
- Less WAL may need replaying after a crash.
- WAL segments eligible for recycling may be freed sooner if no other retention blockers exist.

Costs:

- More checkpoint writes.
- Higher I/O and potential latency spikes if not smoothed well.
- Potentially more full-page images and higher WAL volume.
- Storage must absorb more total writes.

### 10.2. Infrequent Checkpoints

Advantages:

- Lower checkpoint frequency.
- Can reduce repeated FPIs across back-to-back checkpoints.
- Lower checkpoint overhead in certain workloads.

Costs:

- Redo point can drift farther behind current WAL.
- Crash recovery may need to replay much more WAL.
- WAL segments may be retained longer because checkpoints have not advanced.
- Recovery time after a crash can grow.

### 10.3. No Single Optimal Checkpoint Setting Fits All Databases

Write-heavy OLTP databases, read-mostly analytics databases, systems with archiving/replication, and bulk-load workloads behave very differently. Tune based on real workload measurements, not a number copied from a blog post.

### 10.4. checkpoint_completion_target Does Not Change Checkpoint Interval

This parameter primarily **smooths write rate**. It does not lengthen or shorten the time between checkpoints like `checkpoint_timeout`, nor does it directly alter the WAL volume target like `max_wal_size`.

### 10.5. max_wal_size Does Not Strictly Cap Crash Recovery WAL Bytes

Checkpoints, archiving, replication slots, and standbys can keep WAL above the threshold. Never assume "max_wal_size=4GB means pg_wal will never exceed 4GB" or "recovery will never replay more than 4GB."

## 11. Monitoring Checkpoints and Redo Points

Do not tune by guesswork. Inspect checkpoint counts, write/sync times, buffers written, WAL generation, and redo distance.

### 11.1. Inspect Active Settings

```sql
SELECT
    name,
    setting,
    unit,
    source,
    pending_restart
FROM pg_settings
WHERE name IN (
    'checkpoint_timeout',
    'checkpoint_completion_target',
    'max_wal_size',
    'min_wal_size',
    'checkpoint_flush_after',
    'checkpoint_warning',
    'full_page_writes',
    'wal_compression',
    'wal_buffers',
    'log_checkpoints'
)
ORDER BY name;
```

`pg_settings` shows effective values and their source. `pending_restart` highlights parameters changed in config files that still require a restart to take effect.

### 11.2. PostgreSQL 17 and Later: pg_stat_checkpointer

In PostgreSQL 17+, checkpoint statistics moved into `pg_stat_checkpointer`:

```sql
SELECT
    num_timed,
    num_requested,
    restartpoints_timed,
    restartpoints_requested,
    restartpoints_done,
    write_time,
    sync_time,
    buffers_written,
    stats_reset
FROM pg_stat_checkpointer;
```

Key columns:

- `num_timed`: checkpoints triggered by timeout.
- `num_requested`: checkpoints requested due to WAL threshold or explicit commands.
- `write_time`: time spent writing checkpoint buffers (in milliseconds in stats).
- `sync_time`: time spent syncing files during checkpoints.
- `buffers_written`: number of buffers written by checkpoints.
- Restartpoint fields relate to recovery/standby activity.

These are cumulative counters since the last stats reset, not metrics for the current minute alone. Take snapshots over time and compute deltas.

### 11.3. PostgreSQL 16 and Earlier: pg_stat_bgwriter

In earlier major versions, checkpoint statistics lived in `pg_stat_bgwriter`. Familiar columns include:

```sql
SELECT
    checkpoints_timed,
    checkpoints_req,
    checkpoint_write_time,
    checkpoint_sync_time,
    buffers_checkpoint,
    buffers_clean,
    maxwritten_clean,
    buffers_backend,
    buffers_backend_fsync,
    buffers_alloc,
    stats_reset
FROM pg_stat_bgwriter;
```

Statistics schemas change across major versions; do not run a PG16 query on PG17+ and assume the server is broken if columns moved to another view. Check `server_version_num` and documentation for your exact version.

### 11.4. Measuring Requested Checkpoint Ratio

If `checkpoints_req` or `num_requested` climbs quickly relative to timed checkpoints, `max_wal_size` may be too small for your WAL rate, or the workload produces WAL bursts. This is a signal to investigate, not automatic proof that raising max_wal_size alone is enough.

### 11.5. Measuring Checkpoint Write/Sync Time

High `write_time` and `sync_time` can indicate slow storage writes or fsyncs. Inspect OS/storage metrics, latency, queue depth, WAL syncs, and query latency as well. Do not look at cumulative milliseconds alone and declare checkpoints slow; compute deltas over time intervals.

### 11.6. log_checkpoints

Enable `log_checkpoints` to log details for every checkpoint:

```sql
SHOW log_checkpoints;
```

Configuration example:

```conf
log_checkpoints = on
```

Logs can record checkpoint start/end, buffers written, WAL added/removed/recycled, and timings depending on major version. Correlate logs with workload and latency at matching timestamps.

### 11.7. pg_stat_wal

```sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full,
    wal_write,
    wal_sync,
    wal_write_time,
    wal_sync_time,
    stats_reset
FROM pg_stat_wal;
```

This view tracks WAL records/bytes and full-page images. If `wal_bytes` jumps sharply after shortening the checkpoint interval, examine the `wal_fpi` ratio and update workload.

### 11.8. Inspecting Redo Point and Checkpoint Record

```sql
SELECT *
FROM pg_control_checkpoint();
```

This function returns checkpoint metadata from the control file, including fields like `checkpoint_lsn`, `redo_lsn`, `redo_wal_file`, timeline IDs, and related flags. This administrative function requires appropriate privileges (typically superuser or a documented monitoring role).

Focused query:

```sql
SELECT
    checkpoint_lsn,
    redo_lsn,
    redo_wal_file,
    timeline_id,
    prev_timeline_id,
    full_page_writes
FROM pg_control_checkpoint();
```

### 11.9. Viewing Redo Distance

```sql
WITH checkpoint_state AS (
    SELECT redo_lsn, checkpoint_lsn
    FROM pg_control_checkpoint()
)
SELECT
    checkpoint_lsn,
    redo_lsn,
    pg_current_wal_lsn() AS current_wal_lsn,
    pg_size_pretty(
        pg_wal_lsn_diff(
            pg_current_wal_lsn(),
            redo_lsn
        )::bigint
    ) AS approximate_redo_distance
FROM checkpoint_state;
```

Run `pg_current_wal_lsn()` on the primary. On a standby, use an appropriate replay LSN (such as `pg_last_wal_replay_lsn()`) and keep in mind the standby is in recovery, not generating WAL like a primary.

### 11.10. pg_controldata

On a host with read access to the data directory, use the utility:

```bash
pg_controldata "$PGDATA"
```

Output includes lines such as:

- Latest checkpoint location.
- Latest checkpoint's REDO location.
- Latest checkpoint's REDO WAL file.
- Latest checkpoint's TimeLineID.
- Latest checkpoint's PrevTimeLineID.
- Latest checkpoint's full_page_writes.

`pg_controldata` reads the data directory's control file. Point it at the right `PGDATA`/cluster; never inspect control data from a different instance to infer the current server's state.

### 11.11. Viewing Current WAL

```sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_walfile_name(pg_current_wal_lsn()) AS current_wal_file;
```

Current WAL LSN functions are for the primary. On standbys, use replay functions such as `pg_last_wal_receive_lsn()` and `pg_last_wal_replay_lsn()` as appropriate.

### 11.12. Resetting Statistics

Some statistics can be reset using administrative stats functions. Never reset counters during a production investigation if dashboards or alerts depend on them; snapshot values beforehand and note the `stats_reset` timestamp.

## 12. WAL Retention, Archiving, and Checkpoints

Checkpoints can make older WAL segments eligible for recycling, but checkpoints are not the only condition. PostgreSQL must keep WAL if another component still needs it.

### 12.1. WAL Recycling

After a checkpoint, WAL segments older than what crash recovery needs can be recycled or deleted if no other retention requirements apply. Recycling means reusing the segment file rather than creating a new file; it is not archiving.

### 12.2. archive_mode and archive_command

When archiving is enabled, PostgreSQL copies completed WAL segments to the archive destination via `archive_command` or an archive library. If the archive command fails, the server retains the unarchived WAL segments and retries.

```sql
SHOW archive_mode;
SHOW archive_command;
SHOW archive_timeout;
```

An archive backlog can grow `pg_wal` beyond `max_wal_size`. This is a safeguard so unarchived WAL is not discarded.

### 12.3. archive_timeout

`archive_timeout` forces a WAL segment switch after a configured interval if WAL has been written, letting the archive receive segments sooner during low-WAL workloads. It does not trigger a checkpoint and does not shrink archived segments to just a few bytes; archived segments remain full standard size.

### 12.4. Replication Slots

Replication slots retain WAL needed by subscribers and standbys. If a consumer stops reading or a slot is abandoned, WAL can accumulate and fill the disk.

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    wal_status,
    safe_wal_size
FROM pg_replication_slots;
```

The `wal_status`/`safe_wal_size` columns exist in newer major versions; view schemas vary by version. On older majors, omit unsupported columns and check the docs.

### 12.5. max_slot_wal_keep_size

`max_slot_wal_keep_size` caps how much WAL a replication slot can retain, depending on major version. If exceeded, the slot may lose the ability to continue streaming and require resync/reinitialization. Do not set it too low if standbys/consumers cannot keep up.

### 12.6. wal_keep_size

`wal_keep_size` retains a configured minimum amount of WAL for streaming standbys. It does not replace archiving or slots when WAL retention must survive long consumer outages.

### 12.7. Checkpoints Do Not Free WAL Pinned by Slots

Even when a checkpoint advances the redo LSN, PostgreSQL must still keep WAL starting from the oldest slot `restart_lsn` or other retention constraints. Raising checkpoint frequency cannot clear a lagging replication slot.

### 12.8. Monitoring Disk Growth

Monitor:

- Free space on the filesystem hosting `pg_wal`.
- Count of ready and archive-failed WAL segments.
- Archive lag and archive command duration.
- Replication slot `restart_lsn` and retained WAL.
- Standby receive/replay lag.
- Alerts when disk headroom gets low or WAL grows abnormally.

Never manually delete files in `pg_wal` to reclaim disk space. If archiving or a slot is pinning WAL, fix the underlying cause per runbook.

## 13. Restartpoints on a Standby

A standby replaying WAL also needs to flush modified data pages to storage so it can restart faster. However, because a standby is in recovery mode, the corresponding mechanism is called a **restartpoint**, not a regular primary checkpoint.

### 13.1. What Is a Restartpoint?

A restartpoint is a checkpoint-like operation on a standby that flushes replayed changes and creates a point from which recovery can resume if the standby restarts or crashes.

### 13.2. Restartpoints Are Constrained by Checkpoint Records from the Primary

A standby can complete a restartpoint only at a checkpoint record received in the WAL stream. Consequently, restartpoints cannot happen more frequently than checkpoint records generated by the primary. A restartpoint request may have to wait for the next checkpoint record.

### 13.3. Why Does a Standby Need Restartpoints?

- Flush replayed dirty pages to data files.
- Reduce how much WAL must be replayed if the standby crashes or restarts.
- Allow recycling or removing older WAL segments once no longer needed for recovery, archiving, or downstream replication.

### 13.4. max_wal_size on a Standby

A standby can also retain WAL during recovery. If a restartpoint cannot run yet because a new checkpoint record has not arrived, WAL volume can exceed the target. Never treat `max_wal_size` as a hard limit for the WAL directory.

### 13.5. Restartpoint Statistics

On PostgreSQL 17+, `pg_stat_checkpointer` includes counters:

```sql
SELECT
    restartpoints_timed,
    restartpoints_requested,
    restartpoints_done
FROM pg_stat_checkpointer;
```

In older major versions, restartpoint columns may reside in `pg_stat_bgwriter`. Check the view schema for your version.

### 13.6. Primary Checkpoint Is Not a Standby Restartpoint

The primary emits a checkpoint record and updates its own checkpoint state. The standby receives that record via WAL and uses it as an opportunity to create a restartpoint on the standby's storage. The two operations are related but do not share a single checkpoint state.

### 13.7. Do Not Run CHECKPOINT on the Primary to Fix Standby Lag

If a standby lags due to network, replay throughput, or slot/archive backlogs, running `CHECKPOINT` on the primary will not resolve the root cause. Investigate receive lag, replay lag, I/O, and WAL retention.

## 14. Crash Recovery vs. Archive Recovery / PITR

Both processes replay WAL, yet they have different purposes and starting points.

### 14.1. Crash Recovery

The goal is to restore the cluster after a crash to the latest valid WAL state usable by the existing data directory. PostgreSQL starts from the redo point in the current checkpoint/control file.

```text
Current data directory
       |
       v
Checkpoint state / redo LSN
       |
       v
Replay available WAL through last valid point
       |
       v
Open database after recovery
```

### 14.2. Archive Recovery

Archive recovery uses a base backup and archived WAL segments to continue replaying. It can rebuild a cluster from backup or bring a cluster to a specific recovery target.

### 14.3. Point-in-Time Recovery (PITR)

PITR lets recovery stop at a timestamp or LSN just before a logical mistake, such as an accidental DROP TABLE. It requires:

- A valid base backup.
- Continuous WAL from the base backup's checkpoint/redo point through the target.
- The correct timeline and archive chain.
- Proper recovery configuration.

PITR cannot reconstruct data that was never backed up or WAL that was never written or archived.

### 14.4. Current Checkpoints Do Not Shorten PITR from an Older Base Backup

When restoring from a base backup, recovery must start from the redo point required by that backup and replay continuous WAL to the target. Newer checkpoints taken on the primary after the backup do not allow skipping the WAL records required from the base backup.

Therefore:

- Checkpoint frequency directly impacts crash recovery of a running data directory.
- Base backup cadence and WAL archive continuity strongly govern PITR recovery distance.
- Restartpoints help a standby checkpoint its recovery progress during replay.

### 14.5. Timeline

After a promotion/failover or PITR, PostgreSQL can create a new timeline. Timeline history records the branching lineage among WAL streams. During recovery, you must target the right timeline; never splice WAL from two divergent branches arbitrarily.

### 14.6. recovery.signal and standby.signal

In PostgreSQL 12+, recovery parameters belong in the standard configuration file, and signal files indicate mode:

- `recovery.signal`: start in archive recovery / PITR mode.
- `standby.signal`: start as a standby and continue streaming/archive recovery per configuration.

Signal files are empty marker files indicating startup mode; they do not contain WAL configuration. Consult docs for your major version when deploying.

### 14.7. Selected Recovery Settings

Example configuration parameters:

```conf
restore_command = 'cp /archive/%f %p'
recovery_target_time = '2026-11-14 09:30:00+07'
recovery_target_action = 'pause'
recovery_target_timeline = 'latest'
```

This is a conceptual configuration example. `restore_command` must fit your archive environment and handle filenames safely. Target timestamps must specify the right timezone and format; never apply recovery settings to production without testing restores on an isolated cluster.

### 14.8. Recovery Target

PostgreSQL supports multiple ways to specify a target, depending on version:

- `recovery_target_time`: timestamp.
- `recovery_target_lsn`: LSN.
- `recovery_target_xid`: transaction ID.
- `recovery_target_name`: named restore point.
- `recovery_target_inclusive`: whether to stop right after or just before the target per target semantics.
- `recovery_target_action`: pause, promote, or shutdown.

Do not rely on target timestamps when transaction-level precision is required. Create a named restore point prior to risky changes or record LSN/correlation metadata in release workflows.

### 14.9. recovery_target_action

`pause` lets you inspect the database at the target before continuing or promoting per runbook. `promote` turns the recovered instance into a new primary. `shutdown` stops the server upon reaching the target. Choose deliberately according to the recovery plan so an environment does not auto-promote by mistake.

### 14.10. Archiving Is Not Just Copying the Latest File

PITR requires a **continuous WAL chain** starting from the base backup. Missing one intermediate segment in the archive can halt recovery before the target even if newer segments exist. Verify archive integrity and test restores regularly.

## 15. RTO, RPO, and Recovery Time

Checkpoints are one factor in RTO, but they do not determine total recovery duration on their own.

### 15.1. RTO — Recovery Time Objective

**RTO** is the maximum downtime the business tolerates after an incident. For example, a 15-minute RTO means operations must restore service within 15 minutes according to the agreed measurement definition.

### 15.2. RPO — Recovery Point Objective

**RPO** is the maximum data loss the business tolerates, typically expressed as a time window prior to failure. For example, a 1-minute RPO allows losing at most roughly one minute of data under the chosen backup, replication, and durability model.

A checkpoint is **not an RPO boundary**. RPO depends on:

- Whether WAL is durably flushed before COMMIT is confirmed.
- `synchronous_commit` and synchronous vs. asynchronous replication.
- Whether WAL archiving is continuous and shipped safely to external storage.
- Whether base backups and WAL retention cover the PITR window.
- Whether failover could lose WAL not yet replicated to the standby.

### 15.3. Components of Recovery Time

```text
Total service recovery time
  =
  detection + failover/restore decision
  + starting PostgreSQL
  + WAL redo/replay
  + consistency and business verification
  + traffic routing / reopening service
```

For PITR, include the time to fetch and restore the base backup plus replay archived WAL from the backup to the recovery target. For standby failover, detection, promotion, and catch-up may dominate.

### 15.4. Rough Redo Time Estimate

A rough estimate:

\[
T_{\text{redo}} \approx
\frac{\text{WAL bytes to replay}}
{\text{effective replay throughput}}
\]

For instance, replaying 12 GB of WAL at an effective throughput of 120 MB/s gives roughly 100 seconds by simple division. This is only an initial approximation—it omits startup overhead, random data-page reads/writes, CPU, decompression, fsyncs, and post-recovery checks.

### 15.5. WAL Bytes Are Not the Only Factor

Two databases with the same 10 GB of WAL to replay can experience very different recovery times because:

- WAL records describe different operation types.
- One workload contains many full-page images.
- Data pages needing reads/writes may be scattered vs. having good locality.
- Storage throughput and latency differ.
- Cache warmth (hot vs. cold) differs.
- CPU and memory differ.
- Archive/restore sources vary in speed.

### 15.6. Closer Checkpoints May Reduce Redo, but Do Not Guarantee RTO

Shortening redo distance reduces only one component of recovery time. If the bottleneck is backup restore, archive fetching, startup checks, filesystem mount, or application warm-up, checkpoint tuning will not meet RTO by itself.

### 15.7. Recovery Time Must Be Measured Empirically

Do not infer RTO from `max_wal_size` or `checkpoint_timeout`. Simulate crashes and restores in a production-like environment, measuring elapsed time from detection until the application serves requests cleanly.

## 16. Lab 1: Observing Checkpoints and Redo Points

Run this lab on a practice database using a role with privileges to read control checkpoint metadata and run `CHECKPOINT`. Do not run manual checkpoints repeatedly in production.

### 16.1. Check Version and Privileges

```sql
SELECT version();
SHOW server_version_num;
SHOW checkpoint_timeout;
SHOW max_wal_size;
SHOW checkpoint_completion_target;
```

Ensure your role has sufficient privileges to run `CHECKPOINT` and query `pg_control_checkpoint()`. If permission is denied, use a DBA account inside the lab per administrative policy.

### 16.2. Record Checkpoint State Before

```sql
SELECT
    checkpoint_lsn,
    redo_lsn,
    redo_wal_file,
    timeline_id,
    full_page_writes
FROM pg_control_checkpoint();
```

Record the values and the snapshot timestamp.

### 16.3. Record Current WAL LSN

```sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_walfile_name(pg_current_wal_lsn()) AS wal_file;
```

### 16.4. Trigger a Manual Checkpoint

```sql
CHECKPOINT;
```

This is an administrative command that can generate I/O. Run it once in the lab.

### 16.5. Re-read Checkpoint State

```sql
SELECT
    checkpoint_lsn,
    redo_lsn,
    redo_wal_file,
    timeline_id,
    full_page_writes
FROM pg_control_checkpoint();
```

The new checkpoint LSN will typically differ from before, and redo LSN may advance. Exact values depend on WAL activity and snapshot timing.

### 16.6. Compare Byte Distance

```sql
SELECT
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        (SELECT redo_lsn FROM pg_control_checkpoint())
    ) AS bytes_from_redo;
```

This is a snapshot measurement. WAL can keep advancing between SQL statements; do not expect the result to stay static.

### 16.7. Read Checkpoint Statistics by Major Version

PostgreSQL 17+:

```sql
SELECT *
FROM pg_stat_checkpointer;
```

PostgreSQL 16 and earlier:

```sql
SELECT *
FROM pg_stat_bgwriter;
```

Do not expect identical columns across the two views. Consult the matching version documentation and record `stats_reset`.

## 17. Lab 2: Generating a WAL Workload and Observing Checkpoint Requests

Test on a dedicated lab database with temporary or lab tables:

### 17.1. Create a Table for Many Rows

```sql
CREATE TABLE IF NOT EXISTS public.checkpoint_lab (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payload text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
```

### 17.2. Insert Data to Generate WAL

```sql
INSERT INTO public.checkpoint_lab(payload)
SELECT repeat(md5(g::text), 8)
FROM generate_series(1, 100000) AS g;
```

This batch produces heap/index writes and WAL. Exact volume depends on compression, schema, and configuration.

### 17.3. Update the Same Set of Pages

```sql
UPDATE public.checkpoint_lab
SET
    payload = payload || 'x',
    updated_at = clock_timestamp()
WHERE id BETWEEN 1 AND 50000;
```

This generates additional WAL and dirty pages. Repeat carefully in the lab if a larger workload is needed.

### 17.4. Observe WAL Bytes

```sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full
FROM pg_stat_wal;
```

Take two snapshots separated by an interval and compute deltas. Counters are cumulative, so track when stats were reset.

### 17.5. Observe Checkpoint Counters/Logs

If `log_checkpoints=on`, check the server log to see whether checkpoints were triggered by timeout or request, along with write/sync durations. Compare against the checkpoint stats view.

### 17.6. Clean Up the Lab

```sql
DROP TABLE public.checkpoint_lab;
```

Run this only if the table was created exclusively for this lab and holds no other data.

## 18. Lab 3: Observing Crash Recovery in a Disposable Cluster

This lab **intentionally performs an unclean PostgreSQL shutdown**. Never run it on production, shared development, or any data directory holding data you need to keep.

### 18.1. Create a Disposable Cluster

On a machine with PostgreSQL installed, initialize a fresh lab data directory with `initdb` and start an instance on a dedicated port. Illustrative shell example:

```bash
initdb -D /tmp/pg-checkpoint-lab
pg_ctl -D /tmp/pg-checkpoint-lab -o "-p 5544" -l /tmp/pg-checkpoint-lab.log start
```

On Windows, use an appropriate separate path and ensure no port or data directory conflicts with existing services. Never point `PGDATA` at a real cluster.

### 18.2. Create a Table and COMMIT Data

Connect to the lab port:

```sql
CREATE TABLE public.crash_lab (
    id integer PRIMARY KEY,
    value text NOT NULL
);

INSERT INTO public.crash_lab
VALUES (1, 'committed-before-crash');

CHECKPOINT;
```

Note that the row was COMMITted and a checkpoint was executed before creating more workload.

### 18.3. Create Committed Changes After the Checkpoint

```sql
INSERT INTO public.crash_lab
VALUES (2, 'committed-after-checkpoint');

UPDATE public.crash_lab
SET value = 'updated-after-checkpoint'
WHERE id = 1;
```

Do not call CHECKPOINT after these two changes. WAL holds the information required to recover them.

### 18.4. Immediate Shutdown in the Lab Cluster

From the lab cluster's terminal:

```bash
pg_ctl -D /tmp/pg-checkpoint-lab stop -m immediate
```

`immediate` simulates an unclean shutdown by halting the server without waiting for a normal checkpoint. This bypasses normal clean shutdown; run it only on a disposable cluster.

### 18.5. Restart and Inspect Recovery Logs

```bash
pg_ctl -D /tmp/pg-checkpoint-lab -o "-p 5544" -l /tmp/pg-checkpoint-lab.log start
```

The server log will report that the database system was interrupted and record the redo/recovery sequence. Exact messages vary with PostgreSQL major version and WAL workload.

### 18.6. Verify Data

```sql
SELECT *
FROM public.crash_lab
ORDER BY id;
```

Both changes COMMITted before the crash must be present after crash recovery, assuming storage and durability settings honor durability guarantees. Do not expect uncommitted transactions to survive as committed.

### 18.7. Stop and Remove the Lab Cluster

Once finished, shut down normally and delete only the lab data directory you created. Double-check the path points strictly to the disposable directory before deleting.

### 18.8. Lab Limitations

`pg_ctl stop -m immediate` simulates an unclean process shutdown, yet does not reproduce all forms of power loss, controller cache failures, torn writes, or storage corruption. To validate real RTO/RPO, test on production-equivalent infrastructure and verify hardware durability.

## 19. Lab 4: Measuring Recovery Time and Building a Baseline

### 19.1. Define Start and End Milestones

Record:

- Incident start time (or recovery start time).
- Time PostgreSQL reports recovery complete / ready.
- Time the application successfully connects.
- Time a business verification transaction succeeds.
- Time full traffic resumes.

Define RTO up to the final meaningful business milestone, not just when the PostgreSQL process comes alive.

### 19.2. Collect Redo Distance Before Testing

```sql
SELECT
    checkpoint_lsn,
    redo_lsn,
    pg_current_wal_lsn() AS current_lsn,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        redo_lsn
    ) AS redo_bytes;
```

Save the result along with workload rate, WAL segment size, storage metrics, and checkpoint configuration.

### 19.3. Execute the Recovery Test

Restore a lab copy from a base backup or use a disposable cluster to trigger a controlled crash per procedure. Never break a live primary just to measure a metric.

### 19.4. Record Results

| Run | Redo bytes | WAL replay throughput | Server ready | App ready | Notes |
| --- | ---: | ---: | ---: | ---: | --- |
| 1 | Record measurement | Record measurement | Record duration | Record duration | Storage/cache |
| 2 | Record measurement | Record measurement | Record duration | Record duration | Different workload |
| 3 | Record measurement | Record measurement | Record duration | Record duration | Archive/restore |

Never fill in fabricated numbers as real measurements. The goal is a repeatable baseline.

### 19.5. Change One Parameter at a Time

Test one change at a time (e.g., `max_wal_size` or `checkpoint_timeout`), holding workload and storage comparable, and measure:

- Checkpoint frequency and requested checkpoints.
- WAL bytes / FPIs.
- Query latency while checkpoints run.
- Redo distance at representative intervals.
- Empirical recovery time.

### 19.6. Compare Both Steady-State and Recovery

A setting might speed up recovery while hurting normal-state latency or raising WAL/disk usage. Evaluate all of:

- p95/p99 write latency.
- Throughput.
- Checkpoint write/sync time.
- WAL generation and archive lag.
- Recovery RTO.
- Storage capacity.

### 19.7. Do Not Run CHECKPOINT to "Clean Up" Production Measurements

If you want to measure crash recovery, take checkpoints in a disposable test cluster at controlled points. Running CHECKPOINT right before a production restart alters state and I/O, making the measurement unrepresentative of an unplanned failure.

## 20. Controlled Checkpoint Tuning Process

Never start by bumping every parameter. Identify the real bottleneck and keep a baseline for comparison.

### 20.1. Step 1 — Define Objectives

Document:

- Target RTO for crash recovery.
- Steady-state throughput and p95/p99 latency.
- Average and peak WAL generation rates.
- Filesystem capacity for `pg_wal`, archives, and backups.
- Replication lag and slot retention.
- Storage write throughput and latency.

### 20.2. Step 2 — Collect a Baseline

Over a representative interval, take snapshots of:

- `pg_stat_checkpointer` (PG17+) or checkpoint counters in `pg_stat_bgwriter` (PG16 and earlier).
- `pg_stat_wal`.
- `pg_replication_slots`.
- `pg_stat_archiver`.
- `pg_stat_replication` on the primary and `pg_stat_wal_receiver` on standbys when applicable.
- OS/storage metrics and query latency.

Compute deltas over time rather than reading a single cumulative snapshot.

### 20.3. Step 3 — Separate Checkpoint Pressure from Retention Pressure

If `num_requested`/`checkpoints_req` climbs sharply, the WAL threshold may be triggering frequent checkpoints.

If `pg_wal` grows even while checkpoints run steadily, inspect archive failures, replication slots, standby lag, and WAL retention. Raising checkpoint frequency will not resolve a slot pinning old WAL.

### 20.4. Step 4 — Adjust Only Related Parameter Groups

For example:

- Too-frequent checkpoints due to WAL threshold: evaluate increasing `max_wal_size`.
- Too-frequent checkpoints due to time: evaluate `checkpoint_timeout`.
- I/O spikes during checkpoints: check `checkpoint_completion_target` and storage throughput.
- Rising WAL bytes due to FPIs: inspect checkpoint interval, `full_page_writes`, and `wal_compression`.

Never disable `full_page_writes` as a first optimization step.

### 20.5. Step 5 — Check Context and Reload/Restart Requirements

```sql
SELECT
    name,
    setting,
    unit,
    context,
    pending_restart
FROM pg_settings
WHERE name IN (
    'checkpoint_timeout',
    'checkpoint_completion_target',
    'max_wal_size',
    'min_wal_size',
    'wal_buffers',
    'full_page_writes'
)
ORDER BY name;
```

`context` indicates whether a change requires a restart or only a reload. `pending_restart` indicates a requested value has not taken effect yet because a restart is needed.

### 20.6. Step 6 — Apply Methodically

In a lab or approved change window, update the configuration file:

```conf
# Illustrative values, not a recommendation for all workloads:
checkpoint_timeout = '10min'
max_wal_size = '4GB'
checkpoint_completion_target = 0.9
log_checkpoints = on
```

After editing, reload if the parameters allow:

```sql
SELECT pg_reload_conf();
```

Re-check `pg_settings` and logs. Parameters requiring a restart will keep `pending_restart=true` until restarted.

### 20.7. Step 7 — Re-Measure Steady State

Compare checkpoint counts, write/sync times, WAL/FPI bytes, query latency, disk growth, and replication/archive lag. A configuration that lowers checkpoint counts at the cost of protracted checkpoints or high disk pressure may be worse overall.

### 20.8. Step 8 — Run Recovery Tests

Execute a crash recovery test or restore test on a production-like environment. Measure actual RTO and verify committed data, uncommitted data, and application behavior post-recovery.

### 20.9. Step 9 — Document and Keep a Rollback Plan

Record before/after configuration, workload profile, test window, WAL bytes, checkpoint metrics, and recovery duration. If latency or disk usage degrades, revert to the known-good configuration and investigate further.

## 21. Easily Confused Concepts

### 21.1. CHECKPOINT vs. pg_switch_wal

`CHECKPOINT` initiates a checkpoint, writing dirty data pages and updating checkpoint state.

`pg_switch_wal()` requests advancing to a new WAL segment (when conditions allow), often useful to archive the current segment sooner. It is **not a checkpoint** and does not force all dirty data pages to disk.

```sql
SELECT pg_switch_wal();
```

Do not call `pg_switch_wal()` repeatedly to "free up pg_wal"; archive, replication, or slot retention may still pin old segments.

### 21.2. Checkpoint LSN vs. Current WAL LSN

`pg_current_wal_lsn()` is the current WAL position on the primary. `checkpoint_lsn` is the checkpoint record position saved in control state. `redo_lsn` is where recovery must start. These three values answer three distinct questions.

### 21.3. Checkpoint vs. COMMIT

COMMIT requires WAL durability per `synchronous_commit`; it does not wait for all data pages to be checkpointed. Checkpoints manage dirty pages and establish a recovery start point.

### 21.4. Checkpoint vs. Backup

A checkpoint is not a backup. A base backup requires a consistent copy of data files plus necessary WAL; continuous WAL archiving enables PITR. Running CHECKPOINT does not produce an independently restorable copy.

### 21.5. Checkpoint vs. Replication

A primary checkpoint does not mean a standby has replayed up to that LSN. The standby maintains its own receive LSN, replay LSN, and restartpoint state. Network or replay lag may still exist.

### 21.6. max_wal_size vs. pg_wal Disk Usage

`max_wal_size` is a soft checkpoint target, not a filesystem quota. Archive failures, slots, or standbys can push `pg_wal` well above it. Lowering max_wal_size is not a safe way to cap disk usage when retention blockers exist.

### 21.7. Crash Recovery vs. PITR

Crash recovery brings the existing data directory back to consistency after a crash. PITR restores from a base backup and replays WAL to a target. Newer checkpoints on the primary cannot substitute for continuous WAL from the base backup.

### 21.8. Restartpoint vs. Checkpoint

Checkpoints are performed by the primary; restartpoints are the equivalent operations on a standby during recovery, constrained by checkpoint records received from the primary.

## 22. Troubleshooting Checkpoint and Recovery Issues

### 22.1. Requested Checkpoints Occurring Too Frequently

Possible causes:

- `max_wal_size` set too low for WAL generation rate.
- Bulk loads/updates creating WAL bursts.
- Checkpoint interval poorly matched to write rate.

Investigation steps:

1. Measure WAL bytes/sec and checkpoint counters.
2. Distinguish timeout-triggered vs. WAL-threshold-triggered checkpoints.
3. Check disk capacity, archiving, and replication retention.
4. Test raising max_wal_size in a controlled environment.
5. Re-measure I/O and recovery time.

### 22.2. High Checkpoint Write Time

Inspect storage write throughput, queue depth, latency, checkpoint buffers written, and checkpoint_completion_target. If storage cannot keep up with the workload, simply raising timeout may lengthen redo distance without fixing the bottleneck.

### 22.3. High Checkpoint Sync Time

High sync time can point to fsync latency, filesystem behavior, controller cache, virtualized storage, or syncing many files. Check OS/storage metrics and durability configuration; never turn off fsync to mask the symptom.

### 22.4. Periodic Query Latency Spikes

If spikes line up with checkpoint logs, check whether checkpoint writes are concentrating too tightly. Inspect `checkpoint_completion_target`, dirty page rate, background writer, and storage headroom. Never assume every latency spike is checkpoint-related; inspect query plans, lock waits, CPU, and I/O too.

### 22.5. pg_wal Growing Unboundedly

Check:

- Whether archive command/library has errors or a backlog.
- Whether any replication slot is inactive or lagging.
- Whether a standby stopped receiving or replaying.
- What the oldest `restart_lsn` is.
- How much free space remains on the filesystem.

Never manually delete WAL segments. If a slot is no longer needed, verify policy and drop it properly; if a standby needs the slot, recover or reinitialize the standby per plan.

### 22.6. Recovery Taking a Long Time

Collect redo distance, WAL replay rate, recovery logs, I/O latency, CPU, cache state, and workload profile. Inspect checkpoint age, WAL archive fetch speed, and base backup age for PITR. Increasing checkpoint frequency only helps when redo distance is the primary bottleneck.

### 22.7. Recovery Halts Due to Missing WAL

Inspect segment names, timeline history, archive status, base backup checkpoint/`backup_label`, and WAL continuity. Never mix segments from another timeline or fabricate empty files to bypass errors.

### 22.8. Database Crash Loop

Read logs from the initial startup and root error, inspect the control file, data directory, storage, WAL segments, and filesystem. Never delete `postmaster.pid` or replace the control file before confirming no old server process is running and verifying which cluster the data belongs to.

### 22.9. Standby Restartpoints Not Advancing

Verify whether the standby is receiving new checkpoint records, whether replay is lagging, whether storage can write, and any WAL retention constraints. A standby whose replay has stalled will not advance restartpoints normally.

### 22.10. Excessive Checkpoint Logs

Checkpoint logs aid investigation at the cost of log volume. Configure log rotation/retention, ship logs centrally, and keep enough detail to analyze checkpoint timing; do not turn off diagnostic logging simply because log volume grew without checking why.

## 23. Production Best Practices

1. Keep `full_page_writes=on` unless backed by verified engineering proof.
2. Size `max_wal_size` based on WAL generation and disk capacity, not guesswork.
3. Use `checkpoint_completion_target` to smooth checkpoint I/O.
4. Monitor requested checkpoints, write/sync times, and FPI/WAL bytes.
5. Monitor archive backlogs and replication slot retention separately from checkpoints.
6. Never schedule frequent `CHECKPOINT` calls from applications.
7. Never manually delete or edit files in `pg_wal`.
8. Never treat checkpoints as backups or PITR capability.
9. Test crash recovery on a disposable cluster.
10. Test PITR from base backups and WAL archives regularly.
11. Measure RTO from incident detection until the application serves traffic again.
12. Define RPO based on WAL durability, archiving, and replication policies.
13. Record PostgreSQL major/minor version and config before comparing metrics.
14. Maintain adequate disk headroom for WAL bursts, archive backlogs, and replication lag.
15. Maintain a runbook for slot/archive backlogs before filesystems fill up.
16. Never disable fsync or durability safeguards to shorten checkpoints.
17. On failover, verify timelines and standby state before opening traffic.
18. Apply checkpoint changes incrementally with a rollback plan.

## 24. Practice Exercises

The exercises below use an isolated PostgreSQL lab. Some questions require inspecting real output; never fill in fabricated values. Crash/recovery simulations must use a disposable cluster, never production.

### Exercise 1. WAL Rule

Explain why PostgreSQL must write WAL durably before writing the data page containing the corresponding change to disk.

### Exercise 2. LSN

What is an LSN? Why does a 10 MB distance between two LSNs not automatically equal 10 seconds?

### Exercise 3. Distinguish Three Positions

Distinguish among `pg_current_wal_lsn()`, `checkpoint_lsn`, and `redo_lsn`.

### Exercise 4. Checkpoint Record

Must the checkpoint record and the redo pointer be at the exact same LSN? Explain.

### Exercise 5. Dirty Page

A page is dirty in shared_buffers while its corresponding WAL has already flushed. If the server crashes before the page is written to disk, how does PostgreSQL recover?

### Exercise 6. Checkpoint and COMMIT

A transaction received COMMIT success, yet its data page has not been checkpointed. Is data lost simply because a checkpoint has not run? State the relevant durability conditions.

### Exercise 7. Checkpoint Triggers

List at least three causes that can trigger an automatic or manual checkpoint.

### Exercise 8. max_wal_size

Why does `max_wal_size='2GB'` not guarantee `pg_wal` will never exceed 2 GB?

### Exercise 9. checkpoint_timeout

How can increasing `checkpoint_timeout` affect redo distance and I/O?

### Exercise 10. checkpoint_completion_target

What does this parameter do? Does it reduce the total number of dirty pages that need to be written?

### Exercise 11. Frequent Checkpoints

State two benefits and three potential costs of overly frequent checkpoints.

### Exercise 12. Infrequent Checkpoints

State two benefits and three potential risks of overly infrequent checkpoints.

### Exercise 13. Full-Page Image

Why does `full_page_writes` log an FPI on the first page modification after a checkpoint? How does an FPI help with torn pages?

### Exercise 14. WAL Compression

Which part of WAL can `wal_compression` shrink, and what resource does it trade off?

### Exercise 15. Checkpoint LSN and Redo LSN

An output shows checkpoint LSN is `0/9000100` and redo LSN is `0/8F00000`. Which value is used as the starting point for crash recovery? Why?

### Exercise 16. pg_control_checkpoint

Write SQL to fetch checkpoint_lsn, redo_lsn, redo_wal_file, and timeline_id.

### Exercise 17. pg_controldata

List which checkpoint information can be read via `pg_controldata` and explain why you must point it to the exact data directory.

### Exercise 18. Newer Major Stats

In PostgreSQL 17+, which view holds checkpoint statistics? Name at least four useful columns.

### Exercise 19. Older Major Stats

In PostgreSQL 16 and earlier, which view holds checkpoint counters? Name two counters distinguishing timed vs. requested checkpoints.

### Exercise 20. WAL Statistics

Write SQL to query `wal_records`, `wal_fpi`, and `wal_bytes`.

### Exercise 21. Archive Backlog

The archive command keeps failing. Why is a checkpoint not permitted to delete all older WAL segments awaiting archiving?

### Exercise 22. Replication Slot

An inactive replication slot holds a very old restart_lsn. What can happen to `pg_wal` disk usage? How should it be handled?

### Exercise 23. Restartpoint

How does a restartpoint differ from a checkpoint? Why can a standby not create a restartpoint at any arbitrary LSN?

### Exercise 24. Crash Recovery vs. PITR

Distinguish the recovery starting point of an existing data directory after a crash from recovery starting from an older base backup.

### Exercise 25. RTO/RPO

How do checkpoints affect RTO? Do they determine RPO? Explain.

### Exercise 26. Estimating Recovery

A system needs to replay 24 GB of WAL, and measured replay throughput is 200 MB/s. Estimate pure redo time by simple division and list at least four factors omitted from that calculation.

### Exercise 27. CHECKPOINT vs. pg_switch_wal

How do these two commands differ? Which one writes dirty data pages?

### Exercise 28. Crash Experiment

Outline a procedure using a disposable cluster to simulate an unclean shutdown and verify COMMITted data after recovery.

### Exercise 29. Tuning

Metrics show requested checkpoints climbing rapidly, write latency rising during checkpoints, and archive backlog at 0. Propose an order of investigation and trial changes.

### Exercise 30. Recovery Plan Design

A SaaS platform requires a 10-minute RTO and a 1-minute RPO. Propose the roles of checkpoints, WAL archiving, base backups, standby replication, monitoring, and recovery drills. Identify limitations that checkpoints alone cannot solve.

## 25. Exercise Solution Hints

### Answer 1. WAL Rule

If a data page is written to disk before its corresponding WAL, a crash can leave the page holding changes without sufficient WAL to recover or verify it. Writing WAL first ensures PostgreSQL has a durable log to redo changes if a page write is missing or torn.

### Answer 2. LSN

An LSN is a byte position in the WAL stream. Byte distance does not map to a fixed elapsed time because WAL generation rate varies by workload; 10 MB might be produced in milliseconds or over many minutes.

### Answer 3. Three Positions

- `pg_current_wal_lsn()`: current WAL position on the primary.
- `checkpoint_lsn`: position of the checkpoint record referenced by control state.
- `redo_lsn`: WAL position where crash recovery must start replaying.

Do not use the three values interchangeably.

### Answer 4. Checkpoint Record

No. The checkpoint record sits at the WAL position marking the checkpoint; the redo pointer is where replay must begin. Redo LSN is typically earlier than the checkpoint record because changes occurring since the previous checkpoint may still need redo.

### Answer 5. Dirty Page

After a crash, PostgreSQL reads WAL from the redo point. If the page on disk does not yet reflect a record, redo applies the change; if the page already carries a sufficiently recent LSN, recovery can skip that record. WAL-before-data guarantees the required log data is present.

### Answer 6. COMMIT Before Checkpoint

Data is not lost merely because the page has not been checkpointed, provided the transaction's WAL was flushed per durability settings and storage honors durability assumptions. Upon restart, WAL replay reconstructs the changes. `synchronous_commit` and replication durability govern when the server confirms COMMIT.

### Answer 7. Checkpoint Triggers

Examples: `checkpoint_timeout`, WAL exceeding the `max_wal_size` target, SQL `CHECKPOINT` command, and normal/fast shutdown.

### Answer 8. max_wal_size

It is a soft target, not a quota. Archive backlogs, replication slots, standby lag, and retention requirements can pin old WAL; workload bursts can also push size above the target.

### Answer 9. checkpoint_timeout

Raising timeout usually reduces timed checkpoints, potentially reducing checkpoint frequency/overhead, yet redo distance can lengthen and crash recovery may replay more WAL. Infrequent checkpoints can also alter FPI/WAL volume.

### Answer 10. checkpoint_completion_target

It spreads checkpoint writes across a target fraction of the checkpoint interval to dampen bursts. It does not eliminate the total dirty pages needing writes; it mainly paces I/O distribution.

### Answer 11. Frequent Checkpoints

Benefits: shorter redo distance; potentially less WAL replayed during crash recovery. Costs: more checkpoint writes, I/O and latency spikes, more FPIs/WAL volume, and higher storage write pressure depending on the system.

### Answer 12. Infrequent Checkpoints

Benefits: lower checkpoint frequency and potentially fewer repeated FPIs. Risks: longer redo distance, slower recovery, longer WAL retention, and a larger burst of dirty pages when a checkpoint eventually runs.

### Answer 13. FPI

FPIs log a full page image on the first modification after a checkpoint so recovery can restore the page if a crash causes a torn write. After restoring the full page image, subsequent WAL records are replayed.

### Answer 14. WAL Compression

`wal_compression` compresses full-page images to reduce WAL bytes across disk, network, and archives, trading off CPU for compression and decompression. It does not compress all WAL records.

### Answer 15. Redo LSN

`0/8F00000` is the redo LSN, so it is the starting point for crash recovery. `0/9000100` is the checkpoint record LSN. The redo point does not equal the checkpoint record position.

### Answer 16. pg_control_checkpoint

```sql
SELECT
    checkpoint_lsn,
    redo_lsn,
    redo_wal_file,
    timeline_id
FROM pg_control_checkpoint();
```

### Answer 17. pg_controldata

It reads latest checkpoint location, REDO location, REDO WAL file, timeline IDs, full_page_writes, and other control metadata. Point it to the exact data directory because each cluster has its own control file, system identifier, and checkpoint state; reading the wrong cluster leads to false conclusions.

### Answer 18. PG17+

View `pg_stat_checkpointer`. Useful fields: `num_timed`, `num_requested`, `write_time`, `sync_time`, `buffers_written`, `restartpoints_done`, and `stats_reset`.

### Answer 19. PG16 and Earlier

View `pg_stat_bgwriter`. Two counters distinguishing triggers: `checkpoints_timed` and `checkpoints_req`. Other columns include checkpoint write/sync time and buffers checkpoint.

### Answer 20. WAL Statistics

```sql
SELECT wal_records, wal_fpi, wal_bytes
FROM pg_stat_wal;
```

### Answer 21. Archive Backlog

WAL segments not yet successfully archived may be needed for PITR or standbys. Deleting them breaks the WAL chain and compromises recoverability. PostgreSQL retains them for retry; operators must fix the archive destination or command.

### Answer 22. Replication Slot

An inactive slot can pin WAL from an old restart_lsn, growing `pg_wal` and filling the filesystem. Determine whether the slot is still needed; recover the consumer/standby, or drop the slot per change plan if obsolete. Never manually delete WAL files.

### Answer 23. Restartpoint

A restartpoint is a checkpoint-like operation on a standby in recovery that saves replay progress. It can only complete at checkpoint records received from the primary, so it cannot be created arbitrarily at any LSN.

### Answer 24. Crash Recovery vs. PITR

Crash recovery of a live data directory starts from the redo LSN in the current checkpoint/control state. PITR starts from the base backup's redo point and replays continuous WAL from the backup to the recovery target. Newer primary checkpoints do not allow skipping WAL from the backup.

### Answer 25. RTO/RPO

Checkpoints can shrink the WAL volume needing replay and thus reduce one component of crash recovery RTO. They do not set RPO; RPO depends on WAL durability, archive continuity, backups, synchronous/asynchronous replication, and failover policy.

### Answer 26. Estimate

24 GB ÷ 200 MB/s ≈ 120 seconds using 1 GB = 1000 MB (or roughly 123 seconds using 1 GiB = 1024 MiB). This excludes startup, random I/O, data page writes, CPU, decompression, fsyncs, archive fetches, and application verification.

### Answer 27. CHECKPOINT vs. pg_switch_wal

`CHECKPOINT` writes dirty pages and updates checkpoint state. `pg_switch_wal()` advances WAL to a new segment so the current segment can be archived sooner; it neither creates a checkpoint nor forces all dirty data pages to flush.

### Answer 28. Crash Experiment

Create a dedicated cluster with initdb, start on an isolated port, create a table and COMMIT data, run CHECKPOINT, make more COMMITted changes, stop via `pg_ctl stop -m immediate`, restart, inspect recovery logs, and SELECT to verify. Operate strictly on a disposable data directory.

### Answer 29. Tuning

1. Confirm whether requested checkpoints are rising due to WAL threshold or another cause.
2. Measure WAL generation rate, FPIs, and checkpoint write/sync times.
3. Since archive backlog is 0, check slots/standby retention and disk space next.
4. Inspect storage write latency and checkpoint completion behavior.
5. Try raising `max_wal_size` if WAL threshold truly drives frequent checkpoints and disk headroom permits.
6. Re-measure steady-state latency, WAL bytes, checkpoint stats, and recovery time.

Never alter `full_page_writes` or disable fsync just to improve numbers.

### Answer 30. Recovery Plan

- **Checkpoints:** tune to balance steady-state I/O and redo distance; do not treat as an RPO control.
- **Base backups:** schedule frequently enough, store in an independent failure domain, and test restores.
- **WAL archiving:** archive continuously, alert on archive failures, and verify chain continuity to meet a 1-minute RPO where feasible.
- **Standbys:** use streaming/synchronous replication aligned with RPO, considering synchronous_commit / standby acknowledgements and failover capability.
- **Monitoring:** track checkpoint stats, WAL bytes, archive lag, slot retention, standby receive/replay lag, disk headroom, and backup age.
- **Recovery drills:** practice crash recovery, standby promotion, and PITR to hit the 10-minute RTO; measure from detection to app-ready.

Checkpoints alone cannot guarantee a 1-minute RPO, replace base backups/archives, prevent failover loss of unreplicated WAL, or meet RTO when backup restore, archive fetch, storage, or app startup is the bottleneck.

## 26. Operational Case Studies

### 26.1. Requested Checkpoints Spike After Traffic Growth

**Symptom:** `num_requested` climbs rapidly, WAL bytes/sec is high, and query latency spikes periodically during checkpoints.

**Analysis:** The workload generates WAL faster than the current configuration accommodates. When checkpoints are repeatedly requested due to `max_wal_size`, the checkpointer must write dirty pages frequently.

**Action:** Measure WAL rate and checkpoint timings; check disk headroom; test raising `max_wal_size`/adjusting timeout in a change window; re-measure p95/p99 and recovery tests. Do not blindly shrink `checkpoint_timeout`, which would make checkpoints even more frequent.

### 26.2. pg_wal Nearly Fills Filesystem Despite Steady Checkpoints

**Symptom:** Checkpoint logs look normal, yet `pg_wal` keeps growing.

**Analysis:** Checkpoints are not the sole retention control. The archive command may be failing or a replication slot may be pinning old WAL.

**Action:** Inspect `pg_stat_archiver`, archive logs, `pg_replication_slots.restart_lsn`, and standby replay. Fix the archive/consumer or clean up obsolete slots. Never delete WAL manually.

### 26.3. Slow Crash Recovery Despite Small Redo Distance

**Symptom:** LSN distance is modest, yet startup still takes a long time.

**Analysis:** Recovery time also depends on random I/O, data page reads/writes, WAL record types, FPIs, cache warmth, storage latency, and CPU. Startup tasks or archive retrieval may also contribute.

**Action:** Inspect recovery logs and OS/storage metrics; separate redo time from restore, startup, and validation time; do not simply increase checkpoint frequency.

### 26.4. PITR Takes Long Even Though a Checkpoint Just Ran on the Primary

**Symptom:** Operations expects a recent checkpoint to speed up PITR, yet restoring from an older base backup still replays a long stretch of WAL.

**Analysis:** PITR from a base backup begins at the backup's redo point, not the primary's current checkpoint. Checkpoints after the backup do not let recovery skip required WAL.

**Action:** Optimize base backup cadence, archive throughput, and appropriate restore parallelism; benchmark PITR with representative backup ages.

### 26.5. Standby Not Releasing WAL

**Symptom:** restartpoints_done is not advancing and retained WAL is large.

**Analysis:** The standby may not have received new checkpoint records, replay may be lagging, or storage is slow. A replication slot may also pin WAL at an old restart_lsn.

**Action:** Inspect receive/replay LSNs, wait events, slot retention, and standby logs. Restore streaming/replay or reinitialize the standby per procedure.

### 26.6. FPI/WAL Volume Increases After Shortening checkpoint_timeout

**Symptom:** Checkpoint count and `wal_fpi` climb, and WAL archive bandwidth grows.

**Analysis:** Hot pages experience their "first modification after checkpoint" more often across shorter intervals, producing more full-page images.

**Action:** Compare FPI ratio, workload, `wal_compression`, and checkpoint interval; balance recovery time against WAL/storage cost. Never turn off `full_page_writes` just to shrink WAL.

## 27. Checklist for Checkpoint Design and Operations

### 27.1. Understanding State

1. Are you distinguishing checkpoint LSN from redo LSN?
2. Do you inspect current checkpoint state via `pg_control_checkpoint()`/`pg_controldata`?
3. Do you track the PostgreSQL major version to select the right stats view?
4. Do you know the WAL generation rate during peak workloads?
5. Do you measure redo distance rather than looking only at `max_wal_size`?

### 27.2. Tuning and Performance

6. Is `checkpoint_timeout` aligned with the workload?
7. Is `max_wal_size` sized for WAL bursts and disk headroom?
8. Is `checkpoint_completion_target` smoothing I/O?
9. Are checkpoint write/sync times monitored via deltas?
10. Are FPI/WAL bytes and the effect of checkpoint frequency monitored?
11. Is `full_page_writes` kept enabled per durability assumptions?
12. Has `wal_compression` been evaluated using CPU and WAL metrics?
13. Are checkpoint warnings and requested checkpoints monitored?
14. Is checkpoint pressure separated from archive/slot retention pressure?

### 27.3. WAL and Retention

15. Is the archive command monitored with alerts on failures?
16. Is the WAL archive continuous from base backup to recovery target?
17. Are inactive or lagging replication slots alerted on?
18. Are disk alerts set for the filesystem hosting `pg_wal`?
19. Are manual WAL deletions and edits strictly avoided?
20. Is `max_wal_size` understood as a soft target rather than a hard quota?

### 27.4. Recovery

21. Are crash recovery, archive recovery/PITR, and standby restartpoints clearly distinguished?
22. Is there a recent base backup with verified restore tests?
23. Are timelines handled properly during failover or PITR?
24. Are RTO and RPO clearly defined around business requirements?
25. Is crash recovery tested on a disposable cluster?
26. Is PITR tested using real backups and WAL archives?
27. Is app-ready time measured, not just process-ready time?
28. Are data consistency and transaction results verified post-recovery?
29. Are runbooks maintained for missing WAL, archive backlogs, and standby lag?
30. Is capacity planned for WAL, archives, backups, replicas, and restore staging?

## 28. Summary

A **checkpoint** is the process by which PostgreSQL syncs WAL and dirty data pages, writes a checkpoint record, and updates state to establish the starting point for crash recovery. **Redo LSN** is the WAL position where replay starts; **checkpoint LSN** is the checkpoint record's position. The two values are related but not identical.

Key principles to remember:

- WAL-before-data ensures required WAL is durable before the corresponding data page is written.
- Crash recovery begins at the redo point of a valid checkpoint and replays WAL sequentially.
- Newer checkpoints typically shorten redo distance, while recovery time also depends on storage, CPU, data pages, WAL record types, and startup workflows.
- Overly frequent checkpoints can increase I/O, latency spikes, and full-page images; overly infrequent checkpoints can lengthen redo distance and recovery time.
- `checkpoint_timeout` governs time, `max_wal_size` is a soft WAL target, and `checkpoint_completion_target` spreads checkpoint writes.
- `full_page_writes` protects against torn pages; never disable it arbitrarily.
- `pg_stat_checkpointer` exists from PostgreSQL 17 onward; older major versions store checkpoint counters in `pg_stat_bgwriter`.
- `pg_control_checkpoint()` and `pg_controldata` expose checkpoint and redo metadata.
- Archive failures and replication slots can retain WAL even while checkpoints continue running.
- Standbys use restartpoints, constrained by checkpoint records received from the primary.
- Crash recovery differs from PITR: PITR requires a base backup and continuous WAL from the backup to the target.
- RTO measures service restoration time; RPO measures tolerable data loss. Checkpoints alone do not determine RPO.
- Configurations must be benchmarked and recovery-tested in a production-like environment.

Practical rule:

> **Tune checkpoints to balance steady-state I/O against redo distance; engineer RTO and RPO holistically through backups, WAL archiving, replication, and recovery drills.**

## 29. References

Official PostgreSQL documentation; select the pages matching your running server major version:

- [WAL Introduction](https://www.postgresql.org/docs/current/wal-intro.html): Write-Ahead Logging and durability.
- [WAL Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html): checkpoints, WAL buffers, full_page_writes, max_wal_size, and WAL parameters.
- [WAL Internals](https://www.postgresql.org/docs/current/wal-internals.html): WAL records, LSNs, and segment organization.
- [WAL Reliability](https://www.postgresql.org/docs/current/wal-reliability.html): WAL protection and storage assumptions.
- [Routine Database Maintenance — WAL](https://www.postgresql.org/docs/current/wal-configuration.html): WAL/checkpoint configuration and tuning.
- [Continuous Archiving and Point-in-Time Recovery](https://www.postgresql.org/docs/current/continuous-archiving.html): base backups, WAL archiving, and PITR.
- [Warm Standby](https://www.postgresql.org/docs/current/warm-standby.html): streaming replication, standby recovery, and restartpoints.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): pg_stat_checkpointer, pg_stat_bgwriter, pg_stat_wal, and related views.
- [Administrative Functions](https://www.postgresql.org/docs/current/functions-admin.html): pg_control_checkpoint, LSN functions, and WAL control functions.
- [pg_controldata](https://www.postgresql.org/docs/current/app-pgcontroldata.html): reading control information from the data directory.
- [pg_ctl](https://www.postgresql.org/docs/current/app-pg-ctl.html): starting/stopping the server and shutdown modes.
- [pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html): creating base backups and checkpoint modes.
- [pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html): logical backups, not a replacement for physical base backups in PITR.
