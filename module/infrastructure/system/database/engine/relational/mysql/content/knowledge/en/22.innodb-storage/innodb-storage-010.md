# Redo Log, Log Sequence Number, and Checkpoint

InnoDB uses the redo log to recover committed changes when MySQL encounters a crash before all data pages have been written down to tablespaces. When a transaction updates a row, the change is typically made on a page in the buffer pool; redo records describe the changes that need to be replayed so data pages can be brought back to a consistent state after a crash. This mechanism allows InnoDB to acknowledge a commit without waiting for every affected data page to be written immediately.

Three concepts to understand together are the **redo log**, **log sequence number (LSN)**, and **checkpoint**. The redo log stores change history in order; the LSN pinpoints progress in the log; and the checkpoint indicates up to which point changes have been safely reflected into data pages so older redo space can be reused. If the redo log is written faster than dirty pages are flushed, checkpoints fall behind and the system may experience write pressure or transaction slowdowns.

This lesson belongs to the `DATABASE_MYSQL` module, focusing on table design, data types, keys, SQL queries, indexes, transactions, concurrency control, reading execution plans, and relational database operations. The goal is to understand a change's path from the buffer pool to the redo log and data files, read LSN milestones, explain checkpoints, and choose durability/capacity settings based on real requirements.

After this lesson, you will be able to:

- Explain the role of the redo log in write-ahead logging and crash recovery.
- Distinguish between the redo log buffer, redo log files, and dirty pages in the buffer pool.
- Understand current LSN, flushed LSN, checkpoint LSN, and page LSN.
- Describe fuzzy checkpoints and why InnoDB does not need to flush the entire buffer pool at once.
- Explain checkpoint age and pressure when the redo log nears exhaustion of reusable space.
- Distinguish the redo log from the undo log, binary log, and doublewrite buffer.
- Evaluate the impact of `innodb_flush_log_at_trx_commit`, `sync_binlog`, `innodb_log_buffer_size`, and `innodb_redo_log_capacity`.
- Observe redo/checkpoint progress using `SHOW ENGINE INNODB STATUS` and status variables.
- Identify signs of checkpoint pressure and propose evidence-based mitigations.

## 1. What Problem Does the Redo Log Solve?

InnoDB manages data in pages. When a transaction updates a row, the page containing that row is loaded into the buffer pool if not already present, and the modification is made on the in-memory copy. A page that has been modified in memory but not yet written back to its data file is called a *dirty page*.

If MySQL acknowledged a commit after only modifying a page in RAM, a power failure or sudden process termination could lose changes already reported as successful. Conversely, if every commit had to immediately write all affected data pages to their final positions in tablespaces, I/O overhead and commit latency would be huge.

The redo log solves this problem by recording enough information to replay changes. InnoDB can write redo sequentially to the redo log and ensure the log is flushed according to durability policy, while data pages are flushed gradually in the background.

For example, when a transaction updates a balance from 500 to 400:

1. InnoDB locates the page containing the account row in the buffer pool.
2. The transaction modifies the page in memory and generates redo records describing the change.
3. Redo records are placed into the redo log buffer.
4. Per the commit policy, the redo log is written and flushed to storage.
5. The transaction can be acknowledged as committed once the corresponding durability condition is met.
6. The dirty page can be flushed down to the tablespace later.

If the server crashes after step 5 but before step 6, the redo log enables InnoDB to recover the committed change upon restart.

## 2. Write-Ahead Logging: The Log Must Precede the Data Page

InnoDB follows the *write-ahead logging* (WAL) principle: before a dirty page is written down to a data file, the redo records needed to recover the changes on that page must be safely written to the redo log.

Conceptual model:

```text
                  Transaction UPDATE
                          |
                          v
                 Buffer pool page
                    (dirty page)
                          |
                          +------> Redo log buffer
                          |                |
                          |                v
                          |          Redo log files
                          |                |
                          |          write / flush
                          |                |
                          v                v
                  Data tablespace     Durable redo
                   (flush later)       for recovery
```

The redo log and data pages follow different write schedules:

- The redo log is written in LSN order, typically sequential I/O.
- Data pages are written to their respective locations in tablespaces via page cleaner activity and the flush list.
- WAL ensures the necessary redo has been recorded before the data page containing the corresponding modification is written out.

This allows commits not to wait for every data page write. However, the redo log must satisfy the transaction's durability policy. If logs exist only in RAM or sit in the OS cache without being flushed as required, an OS crash or power loss can still lose commits depending on configuration.

## 3. Redo Log Buffer and Redo Log Files

The redo log has two primary layers that operators commonly need to distinguish.

### 3.1. Redo Log Buffer

The redo log buffer is an in-memory area in InnoDB used to hold redo records before writing them out to redo log files. Its size is configured with:

```sql
SHOW VARIABLES LIKE 'innodb_log_buffer_size';
```

`innodb_log_buffer_size` helps transactions that generate many redo records. If the buffer is too small, InnoDB may have to flush redo from the buffer to log files before the transaction finishes. Doing so does not auto-commit the transaction; it only changes when redo is written to files.

Increasing the log buffer does not replace redo log capacity. The buffer determines how much redo can be held temporarily in RAM; capacity determines how much redo log space can be used before checkpoints must free older space.

### 3.2. Redo Log Files

Redo log files are durable storage for redo records. InnoDB manages them circularly (*circular log*): once writes reach the end, it can reuse older space if checkpoints have advanced far enough that redo records in that region are no longer needed for crash recovery.

On newer MySQL releases, total redo log capacity is controlled by `innodb_redo_log_capacity`. Starting in MySQL 8.0.30, InnoDB manages redo log files inside the `#innodb_redo` directory beneath the data directory; the exact file layout is an internal detail and should not be manipulated directly by applications.

Checking configuration:

```sql
SHOW VARIABLES LIKE 'innodb_redo_log_capacity';
SHOW VARIABLES LIKE 'innodb_log_buffer_size';
```

Never delete, rename, move, or edit redo log files while the server is running. InnoDB must manage their lifecycle, placement, and state.

## 4. Log Sequence Number (LSN)

The LSN is a monotonically increasing sequence number representing progress within the redo log. You can visualize the LSN as a byte offset along the redo stream: as InnoDB generates new redo records, the LSN advances forward.

Important LSN milestones:

| Milestone | Conceptual meaning |
| --- | --- |
| Current LSN | Latest redo position generated/numbered |
| Written LSN | Redo position written to file per write progress |
| Flushed LSN | Redo position flushed per the system's sync mechanism |
| Checkpoint LSN | Oldest redo milestone no longer needed for recovery after corresponding pages have been safely flushed |
| Page LSN | LSN recorded inside a data page, representing the latest redo milestone applied to that page |

Exact field names shown in status output may vary across versions. These milestones help read progress conceptually; not every value corresponds to an independent configuration variable.

### 4.1. Current LSN

Current LSN increases as InnoDB generates redo records. Under write-heavy workloads, current LSN advances faster; under workloads with few data modifications, it advances slower.

The difference in current LSN between two points in time can estimate how much redo was generated during that interval:

```text
redo generated ~= current_lsn_after - current_lsn_before
redo rate      ~= redo generated / elapsed_seconds
```

This estimates the redo generation rate, not the total size of data pages written. A small amount of redo can lead to many page flushes and vice versa, depending on update patterns and page layout.

### 4.2. Flushed LSN

Flushed LSN indicates redo progress flushed according to InnoDB's durability mechanism. Current LSN can stay ahead of flushed LSN because newly generated redo has not finished flushing yet.

The gap between current and flushed reflects the amount of redo awaiting write/flush at the moment of observation. Do not draw failure conclusions from a single snapshot; observe trends, write rates, and flush policies.

### 4.3. Checkpoint LSN

Checkpoint LSN marks the recovery boundary: redo prior to the checkpoint milestone is no longer required to reconstruct current pages because the corresponding changes have been safely written down to data files.

Checkpoint LSN is neither the LSN of the last committed transaction nor the current position of the redo writer. It reflects data page flushing progress and the ability to reuse older redo space.

### 4.4. Page LSN

Every InnoDB page carries LSN metadata indicating the most recent change applied to that page. During crash recovery, InnoDB can compare a redo record's LSN against the page LSN to decide whether that record needs to be applied.

If the page already reflects an LSN newer than the redo record under consideration, replaying the older record is unnecessary. Page LSN is part of how recovery avoids reapplying changes already present on a page.

## 5. What Is a Checkpoint?

A checkpoint is the process by which InnoDB ensures changes with LSNs prior to a certain milestone have been safely reflected into data pages on storage. As the checkpoint advances, redo space older than that milestone can be reused since it is no longer needed for crash recovery.

A checkpoint does not mean:

- All open transactions have committed.
- All dirty pages in the buffer pool have been flushed.
- The redo log has been erased or reset to 0.
- A specific transaction just committed.

A checkpoint is data page write progress serving redo log lifecycle management and crash recovery time.

### 5.1. Dirty Pages and the Flush List

When a page in the buffer pool is modified, it becomes a dirty page. InnoDB tracks dirty pages and their modification order so it knows which pages still need flushing before the checkpoint can advance.

Page cleaner threads write dirty pages down to tablespaces in the background. Flushing can be triggered by:

- The need to make free space in the buffer pool.
- Redo log pressure as checkpoint age grows.
- Dirty page targets and flushing policies.
- Periodic sweeps and adaptive flushing decisions.

WAL requires corresponding redo to be sufficiently written/flushed before a dirty page is written down to a data file. Consequently, if a page write is interrupted, redo can still help recover the change.

### 5.2. Fuzzy Checkpoint

InnoDB uses a flexible checkpointing approach (*fuzzy checkpoint*): dirty pages are flushed incrementally according to I/O capacity, without halting all write activity to flush every page simultaneously.

This preserves concurrency. While page cleaners flush some pages, other transactions can still read and update other pages. Checkpoint LSN advances according to the boundary of the oldest changes still needing protection.

A single page can be updated many times before being flushed. By the time the page is written out, it may already include changes newer than the initial LSN that made the page dirty. Managing page LSN and the flush list lets InnoDB determine the safe milestone for advancing the checkpoint.

## 6. Checkpoint Age and Redo Log Pressure

Checkpoint age is the distance between current LSN and checkpoint LSN:

```text
checkpoint_age = current_lsn - checkpoint_lsn
```

It estimates the amount of redo generated since the last checkpoint milestone. If redo log capacity is 1 GiB and checkpoint age is 300 MiB, the used span is roughly 300 MiB. This is a simplified example to grasp the relationship; do not treat this calculation as an exact byte measurement of physical files.

When checkpoint age rises close to the usable redo capacity, InnoDB must accelerate flushing dirty pages to create reusable space. If redo generation consistently outpaces data page flushing, the system may exhibit:

- Adaptive flushing intensifying background writes.
- Rising data-file write I/O impacting latencies of other workloads.
- Write transactions slowing down or stalling as redo space nears exhaustion.
- Unstable throughput under bursty write workloads.

Larger redo log capacity can absorb longer bursts, but cannot fix storage lacking sufficient write throughput for steady-state workloads. If average redo generation consistently exceeds flushing capacity, checkpoints will eventually come under pressure.

### 6.1. Example Reading Checkpoint Age

Suppose at a given measurement point:

```text
Current LSN:       1,200 MiB
Checkpoint LSN:      800 MiB
Redo capacity:     1,024 MiB
```

Checkpoint age is roughly 400 MiB. If the workload keeps generating 100 MiB of redo per minute while the checkpoint advances only 60 MiB per minute, the gap widens by roughly 40 MiB per minute. If that trend continues, InnoDB will have to increase flushing or throttle writers to protect redo space.

To evaluate properly, sample multiple points over time:

1. Capture current LSN and checkpoint LSN.
2. Wait a fixed measurement interval.
3. Capture both values again.
4. Calculate redo generation rate and checkpoint advance rate.
5. Correlate with disk latency, dirty pages, throughput, and commit latency.

A high checkpoint age during a large import may be a temporary burst; a sustained upward trend under normal workloads warrants investigation.

## 7. How Does Crash Recovery Use the Redo Log?

When MySQL starts after a crash, InnoDB must bring data pages back to a consistent state. Conceptually, the process involves:

1. Locating the most recent checkpoint and reading the redo log from the necessary position.
2. Replaying needed redo records to bring data pages to the state recorded in the log.
3. Handling incomplete transactions using undo information to roll back uncommitted changes.
4. Completing necessary recovery steps before allowing normal workloads to resume.

Redo serves *roll forward*: reapplying logged changes. Undo serves *rollback*: reverting uncommitted transaction changes and supporting MVCC. The two mechanisms complement each other.

### 7.1. Why Doesn't the Redo Log Need to Contain the Entire Table?

The redo log stores page/record-level change information and metadata needed for InnoDB to replay changes. Data files remain the persistent storage for tables and indexes. The redo log only needs to retain changes since the checkpoint still required for recovery.

As checkpoints advance, old redo records can be reused. Therefore, the redo log is not a complete historical backup of the database.

### 7.2. Crash Recovery and Startup Time

If checkpoints consistently stay close to current LSN, the amount of redo to process after a crash is typically smaller than when checkpoints lag far behind. However, recovery time also depends on dirty page count, database size, storage throughput, incomplete transactions, and pre-crash workload.

Do not increase redo capacity solely aiming to "make recovery faster." Larger capacity can allow a larger span of uncheckpointed redo, increasing the redo range needing recovery after a crash in some scenarios. Balance burst tolerance, write throughput, and recovery objectives.

## 8. Redo Log, Undo Log, Binary Log, and Doublewrite Buffer

These mechanisms are often confused because all relate to data writes and recovery.

| Mechanism | Primary role | Scope |
| --- | --- | --- |
| Redo log | Replay changes to recover data pages after a crash | InnoDB/storage engine |
| Undo log | Roll back uncommitted transactions, provide older versions for MVCC | InnoDB/storage engine |
| Binary log (binlog) | Record transactions/events for replication and point-in-time recovery | MySQL server layer |
| Doublewrite buffer | Protect against torn pages during incomplete page writes | InnoDB page write path |

### 8.1. Redo and Undo

Redo answers: "How do we replay necessary changes onto pages?" Undo answers: "How do we revert to an earlier version or roll back an uncommitted transaction?"

A row-updating transaction can generate both redo and undo information. If the transaction commits and the server crashes before data pages are flushed, redo helps recover the committed change. If the transaction had not committed at crash time, recovery uses undo to revert incomplete changes.

### 8.2. Redo and Binary Log

The redo log is used by InnoDB for crash recovery of data pages. The binary log is used by MySQL to record transactions/events for replication and point-in-time recovery. When binlog is enabled, MySQL coordinates commits between the storage engine and binary log via two-phase commit to avoid inconsistency between the two log streams.

The redo log does not replace the binlog for replication; nor does the binlog replace the redo log for InnoDB crash recovery.

### 8.3. Redo and Doublewrite Buffer

The redo log holds changes for replay. The doublewrite buffer protects page writes against partial page writes (*torn pages*). If storage interrupts a page write mid-way, the intact page copy in the doublewrite area can restore the page before redo is applied.

The two mechanisms solve different problems and together contribute to data durability.

## 9. Durability at COMMIT: innodb_flush_log_at_trx_commit

`innodb_flush_log_at_trx_commit` controls how InnoDB writes and flushes the redo log when a transaction commits.

Checking:

```sql
SHOW VARIABLES LIKE 'innodb_flush_log_at_trx_commit';
SHOW VARIABLES LIKE 'innodb_flush_log_at_timeout';
```

Key values:

| Value | Behavior at commit | Trade-off |
| --- | --- | --- |
| `1` | Writes redo log and flushes to storage on every commit; default | Strongest durability under standard design; can add flush cost, though group commit shares I/O |
| `2` | Writes redo log to file at every commit, but flushes periodically, typically about once per second | Can lose recent transactions on OS crash or power loss before flush; typically survives a mysqld-only crash if the OS stays up |
| `0` | Does not require redo write/flush per commit; writes and flushes periodically, typically about once per second | Can lose recent transactions on mysqld crash, OS crash, or power loss |

Periodic flushing is not an exact per-second guarantee; actual flush schedules and behavior depend on activity, schedulers, the OS, and storage. Values `0`/`2` trade durability for reduced synchronization overhead in certain workloads.

For critical transactional data, `innodb_flush_log_at_trx_commit = 1` is typically kept. Do not lower it to 0 or 2 merely because commits appear slow; first measure fsync latency, group commit, storage, and transaction patterns.

### 9.1. Binlog and sync_binlog

If binary logging is enabled and durability between InnoDB and the binlog is required, inspect:

```sql
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'sync_binlog';
```

`sync_binlog = 1` requests synchronizing the binlog to storage at every commit (which can be batched via group commit). A common configuration prioritizing durability is:

```ini
innodb_flush_log_at_trx_commit = 1
sync_binlog = 1
```

These two variables protect two separate log streams. Setting only one to 1 does not replace synchronizing the other if the system requires durability and consistent replication/PITR.

Actual durability still depends on the OS, filesystem, controllers, storage hardware, and whether they honor flush/sync commands properly. Hardware caches without power-loss protection can undermine durability assumptions.

### 9.2. Group Commit

When multiple transactions commit close together, MySQL can batch log flush requests so multiple transactions share a single storage sync. This is group commit. It reduces fsyncs per transaction while preserving durability policies.

Therefore, `innodb_flush_log_at_trx_commit = 1` does not mean each transaction always issues a separate fsync call. Commit performance depends on concurrent transactions, binlog group commit, storage latency, and workload structure.

## 10. Configuring Redo Log Capacity and Log Buffer

### 10.1. innodb_redo_log_capacity

`innodb_redo_log_capacity` defines the total redo log capacity managed by InnoDB. On MySQL versions supporting this variable (since 8.0.30), it can be changed dynamically at GLOBAL scope:

```sql
SHOW GLOBAL VARIABLES LIKE 'innodb_redo_log_capacity';

-- Example setting capacity to 2 GiB; use only after evaluating workload and disk.
SET GLOBAL innodb_redo_log_capacity = 2147483648;
```

Increasing capacity can:

- Allow absorbing longer write bursts before checkpoints must catch up.
- Reduce frequency of checkpoint pressure in bursty write workloads.
- Increase disk space dedicated to the redo log.
- Potentially enlarge the redo span needing recovery after a crash if checkpoint age grows accordingly.

Reducing capacity can force InnoDB to flush dirty pages more aggressively to return checkpoints to a safe margin. Do not change capacity arbitrarily by guesswork; measure redo rate, checkpoint age, dirty pages, I/O latency, and disk space before choosing a value.

### 10.2. innodb_log_buffer_size

```sql
SHOW GLOBAL VARIABLES LIKE 'innodb_log_buffer_size';
```

A log buffer that is too small can force large transactions to flush redo to files multiple times while the transaction is still running. Increasing the buffer can help redo-heavy transactions reduce premature flushes, but does not solve checkpoint pressure caused by insufficient capacity or storage throughput.

Only increase it when evidence shows large transactions routinely fill the log buffer or cause significant premature writes. For ordinary workloads, the default buffer may already suffice.

### 10.3. Flush Rate and Adaptive Flushing

Variables commonly associated with page flushing:

```sql
SHOW VARIABLES LIKE 'innodb_adaptive_flushing';
SHOW VARIABLES LIKE 'innodb_io_capacity';
SHOW VARIABLES LIKE 'innodb_io_capacity_max';
SHOW VARIABLES LIKE 'innodb_max_dirty_pages_pct';
SHOW VARIABLES LIKE 'innodb_max_dirty_pages_pct_lwm';
```

- `innodb_adaptive_flushing` allows InnoDB to adjust flush rate based on redo generation and checkpoint pressure.
- `innodb_io_capacity` guides the background I/O bandwidth InnoDB can use for tasks like flushing.
- `innodb_io_capacity_max` sets a higher ceiling for background I/O when acceleration is needed.
- Dirty page thresholds influence flush decisions based on the percentage of dirty pages in the buffer pool.

These variables are not standalone speed knobs. Setting them too low can make checkpoints lag behind; setting them too high can starve foreground queries and other services of I/O. Base them on actual storage capability and measure system-wide latency.

## 11. Observing LSN and Checkpoints

### 11.1. SHOW ENGINE INNODB STATUS

The most useful command for inspecting InnoDB's internal snapshot:

```sql
SHOW ENGINE INNODB STATUS\G
```

In the `LOG` section, depending on version, you may see lines such as:

- `Log sequence number`
- `Log buffer assigned up to`
- `Log buffer completed up to`
- `Log written up to`
- `Log flushed up to`
- `Added dirty pages up to`
- `Pages flushed up to`
- `Last checkpoint at`

Read them to compare redo generation progress, redo write/flush progress, and data page flushing. Milestones do not need to be equal at every instant because they represent different stages of the pipeline.

### 11.2. Status Variables for LSN

On MySQL versions exposing the corresponding status variables, you can query:

```sql
SHOW GLOBAL STATUS LIKE 'Innodb_lsn%';
```

Or:

```sql
SELECT VARIABLE_NAME, VARIABLE_VALUE
FROM performance_schema.global_status
WHERE VARIABLE_NAME IN (
    'Innodb_lsn_current',
    'Innodb_lsn_flushed',
    'Innodb_lsn_last_checkpoint'
)
ORDER BY VARIABLE_NAME;
```

Variable names and availability may differ across releases; verify output on the target server. If a variable does not exist, use the milestones in `SHOW ENGINE INNODB STATUS`.

### 11.3. Sampling Over Time

A single snapshot shows state at only one instant. To determine whether checkpoints are lagging behind, take multiple samples separated by a time interval and record:

| Metric | Question to answer |
| --- | --- |
| Current LSN | How fast is redo being generated? |
| Flushed LSN | Are redo writes/flushes keeping up with current LSN? |
| Checkpoint LSN | Is the checkpoint advancing fast or slowly? |
| Checkpoint age | Is the redo region used since the last checkpoint growing or shrinking? |
| Dirty pages | How many unflushed pages is the buffer pool accumulating? |
| Disk write latency/IOPS | Does storage have enough write capacity? |
| Commit latency | Are clients waiting on redo/binlog flushes? |

Compare metrics from the same timestamp to distinguish a log flush bottleneck from a data page flushing bottleneck.

## 12. Diagnosing Checkpoint Pressure

Checkpoint pressure occurs when InnoDB cannot flush dirty pages fast enough to reuse redo log space at the rate the workload generates redo.

Signs to check:

- Checkpoint age grows steadily and approaches redo capacity.
- `Pages flushed up to` or checkpoint LSN advances slowly relative to current LSN.
- Data-file write I/O spikes while write workloads are high.
- Write transaction latency rises disproportionately relative to SQL count.
- InnoDB ramps up adaptive flushing or writers wait for redo space.
- Persistent high dirty page ratios paired with high storage queue/latency.

Do not conclude from a single symptom. For instance, high commit latency paired with low checkpoint age may point to slow redo fsync or binlog fsync rather than checkpoint pressure. Conversely, high checkpoint age with steady commit latency during a brief burst may not yet be an incident.

### 12.1. Investigation Workflow

1. Confirm `innodb_redo_log_capacity`, `innodb_flush_log_at_trx_commit`, and `sync_binlog`.
2. Capture `SHOW ENGINE INNODB STATUS` and LSN variables at multiple timestamps.
3. Estimate redo generation rate and checkpoint advance rate.
4. Observe dirty pages, page cleaner activity, disk latency, IOPS, and queue depth.
5. Identify the workload generating redo: large batch updates, imports, secondary index maintenance, multi-row transactions, or a sudden write spike.
6. Check whether storage is shared with binlogs, temporary files, backups, or other workloads.
7. Test tuning one variable in a test environment or monitored maintenance window, then compare before and after.

### 12.2. Mitigations

- Increase `innodb_redo_log_capacity` if the issue is short bursts and sufficient disk space exists; larger capacity provides more headroom.
- Improve storage throughput/latency if data page flushing cannot keep up with steady-state workloads.
- Tune `innodb_io_capacity`/`innodb_io_capacity_max` to realistic I/O capability, avoiding saturating foreground workloads with background I/O.
- Split large write batches into reasonably sized transactions if business rules allow, reducing bursts and lock hold times.
- Reduce unnecessary updates, avoiding updating the same rows/indexes overly frequently.
- Review indexes and schema to minimize redundant page modifications, without dropping indexes/constraints needed for correctness.
- Keep transactions short and prevent clients from leaving transactions open unintentionally.

Do not lower `innodb_flush_log_at_trx_commit` as a fix for checkpoint pressure. That variable governs durability of redo flushes at commit; checkpoint pressure primarily relates to dirty page flush speed and reusing redo space. Both bottlenecks can occur together, but they are not the same issue.

## 13. Redo Log Capacity and Crash Recovery: Balance Rather Than Maximize

Too little redo capacity can cause bursty write workloads to push checkpoints under frequent pressure. Too much capacity can:

- Consume more disk space.
- Allow larger checkpoint age before flushing must ramp up.
- Increase the amount of redo that may need scanning after a crash, depending on checkpoint position at crash time.
- Mask insufficient storage throughput for a period of time.

Choose capacity based on:

- Peak and average redo generation rates.
- Typical duration of write bursts.
- Storage's data page flushing capability.
- Disk space and recovery time requirements.
- Dirty page ratios and update patterns.

For example, if a workload has a write burst generating 200 MiB of redo in 30 seconds before returning to low levels, larger capacity can help InnoDB absorb the burst without overly aggressive flushing. If a workload generates 200 MiB every 30 seconds continuously while storage can only flush 100 MiB every 30 seconds, increasing capacity only delays when pressure hits; you need either higher write throughput or lower redo generation.

## 14. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Thinking commits must flush all data pages | Misunderstands why the redo log is needed | Distinguish redo flushes from data page flushes |
| Thinking a checkpoint is a commit | Confuses page write progress with transaction state | A checkpoint is the boundary of reusable redo |
| Confusing redo log with undo log | Misunderstands crash recovery and MVCC | Redo rolls forward; undo rolls back and builds older versions |
| Confusing redo log with binlog | Expects redo to serve replication/PITR | Use redo for InnoDB recovery, binlog for replication/PITR |
| Only increasing redo capacity when checkpoint age grows | Masks insufficient storage throughput | Compare redo rate against checkpoint advance and disk capacity |
| Lowering flush-at-commit to fix checkpoint pressure | Trades durability without fixing page flushing | Determine whether the bottleneck is redo fsync or checkpoint/data page flush |
| Increasing log buffer to solve every redo issue | Fails to address capacity or checkpoint pressure | Increase only when large transactions fill the log buffer |
| Drawing conclusions from a single LSN snapshot | Ignores trends and workload context | Sample over time and correlate with I/O |
| Deleting or editing redo files manually | Can corrupt recoverability | Let InnoDB manage redo files |
| Thinking larger capacity is always better | Increases disk usage and potentially recovery work | Balance bursts, throughput, and RTO |

## 15. Practice Exercises

1. Run `SHOW VARIABLES LIKE 'innodb_redo_log_capacity'` and `SHOW VARIABLES LIKE 'innodb_log_buffer_size'`. Record your lab server configuration.
2. Run `SHOW ENGINE INNODB STATUS\G`; locate current LSN, flushed LSN, pages flushed, and last checkpoint.
3. If the server provides `Innodb_lsn_current`, `Innodb_lsn_flushed`, and `Innodb_lsn_last_checkpoint`, capture two samples 30 seconds apart and calculate redo generation and checkpoint advance rates.
4. Run a workload updating many rows in a lab table, observing changes in current LSN and checkpoint LSN.
5. Compare one large transaction against many small transactions updating an equivalent total number of rows. Observe redo rate, commit latency, and dirty pages.
6. Test increasing `innodb_redo_log_capacity` in a lab environment with adequate disk space. Observe checkpoint pressure and redo file footprint; restore configuration afterward if needed.
7. Compare `innodb_flush_log_at_trx_commit` settings in a test environment without using data requiring durability. Explain the risks of values 0, 1, and 2.
8. If binlog is enabled, check `sync_binlog` and explain why redo flush and binlog sync are two separate streams.
9. Read `SHOW ENGINE INNODB STATUS` to distinguish log flush lag from checkpoint lag.
10. Write a short report: how much redo per second the workload generates, how fast the checkpoint advances per second, whether storage has sufficient capacity, and which change should be tested first.

## 16. Redo Log and Checkpoint Operations Checklist

- [ ] Understood that the redo log protects changes before data pages are flushed.
- [ ] WAL is upheld: required redo is written before the corresponding dirty page.
- [ ] Distinguished redo log buffer, redo log files, and buffer pool dirty pages.
- [ ] Understood current, written, flushed, checkpoint, and page LSNs.
- [ ] Understood that a checkpoint is neither a commit nor a full buffer pool flush.
- [ ] Monitored checkpoint age over time rather than relying on a single snapshot.
- [ ] Checked `innodb_redo_log_capacity` and `innodb_log_buffer_size` against the actual bottleneck.
- [ ] Confirmed durability requirements before changing `innodb_flush_log_at_trx_commit`.
- [ ] When binlog is enabled, evaluated `sync_binlog` alongside the redo flush policy.
- [ ] Correlated redo generation with checkpoint advance and storage throughput.
- [ ] Assessed the impact of redo capacity on burst tolerance and recovery time.
- [ ] Avoided manual manipulation of redo log files while the server is running.
- [ ] Prepared a before/after measurement plan for every configuration change.

## 17. Completion Criteria

You have completed this lesson when you can trace the path of a change from the buffer pool to the redo log and data files, explain WAL, LSN, page LSN, and fuzzy checkpoints, calculate checkpoint age from LSN milestones, distinguish redo/undo/binlog/doublewrite, select a flush policy matching durability requirements, and diagnose checkpoint pressure using time-series observations.

## References

- [MySQL 8.4 Reference Manual — InnoDB Redo Log](https://dev.mysql.com/doc/refman/8.4/en/innodb-redo-log.html)
- [MySQL 8.4 Reference Manual — Configuring InnoDB Redo Logging](https://dev.mysql.com/doc/refman/8.4/en/innodb-redo-log.html#innodb-redo-log-configuration)
- [MySQL 8.4 Reference Manual — InnoDB Parameters](https://dev.mysql.com/doc/refman/8.4/en/innodb-parameters.html)
- [MySQL 8.4 Reference Manual — Binary Log Group Commit](https://dev.mysql.com/doc/refman/8.4/en/replication-features-transactional.html)
