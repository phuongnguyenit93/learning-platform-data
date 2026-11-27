# Binlog Cache, Large Transactions, and Logging Overhead

The binary log (binlog) records data changes and certain events needed for replicas to apply changes or to perform point-in-time recovery (PITR). For InnoDB tables, MySQL must hold a transaction's events until it knows whether the transaction commits or rolls back. The **binlog cache** mechanism temporarily stores those events before they are written to the binary log.

Transaction size, how MySQL writes caches, binlog format, and sync frequency to storage all affect capacity, commit latency, I/O load, and the time replicas take to apply data. This lesson explains the cache lifecycle, how to recognize cache spills to temporary files, the impacts of large transactions, and how to tune logging overhead while preserving consistency and recovery requirements.

The examples target MySQL 8.0. Certain variables and behaviors may differ across versions or configurations; verify actual values on your instance before applying changes.

## Learning Objectives

After this lesson, you will be able to:

- Describe the roles of the transaction cache and statement cache when writing the binary log.
- Distinguish in-memory cache usage from cache spills to temporary files, and understand the limit controlled by `max_binlog_cache_size`.
- Measure cache spill levels using MySQL status counters.
- Explain why large transactions increase logging overhead, commit latency, and replica lag.
- Choose batching strategies, row image formats, cache settings, and sync policies suited to your workload.

## 1. Lifecycle of the Binlog Cache

When a session executes a data-modifying statement, MySQL generates the corresponding binlog events. For transactions, events are held temporarily until the transaction outcome is determined. If the transaction rolls back, events belonging to rollbackable changes are not recorded as a committed transaction. If the transaction commits, MySQL writes the event group to the binary log along transaction boundaries.

The processing flow can be visualized as follows:

```text
Session executes statement
          |
          v
   Generate binlog events
          |
          v
   Select appropriate cache
     /             \
    v               v
Transaction       Statement
cache             cache
    \               /
     \             /
      v           v
   Memory cache full?
       /       \
     No         Yes
      |          |
      |          v
      |      Write overflow to
      |      temporary file
      |          |
      +-----+----+
            |
            v
      COMMIT / finish
            |
            v
      Write event group
      to binary log
            |
            v
      Sync per configuration
      and complete commit
```

This diagram depicts the general concept. Exact handling details depend on the storage engine, statement type, and active binlog format.

### 1.1. Transaction Cache

`binlog_cache_size` specifies the memory cache size used to hold a transaction's events. This cache serves changes managed within transaction boundaries, such as changes to InnoDB tables. When a transaction's binlog data exceeds the memory cache, MySQL can continue storing the excess in a temporary file rather than immediately forcing the transaction to abort.

The maximum limit of the transaction cache is controlled by `max_binlog_cache_size`. If a transaction requires more space than this limit, MySQL returns an error and the transaction cannot proceed normally. Thus, `binlog_cache_size` and `max_binlog_cache_size` serve different roles:

- `binlog_cache_size`: initial memory cache allocation for the transaction cache.
- `max_binlog_cache_size`: upper limit on transaction cache data for a single transaction.

Increasing `binlog_cache_size` can reduce the number of transactions using temporary files, but increases potential RAM usage when many concurrent sessions exist. Increasing `max_binlog_cache_size` allows larger transactions, but does not make them cheaper: they still must write, store, transmit, and apply the corresponding data volume.

### 1.2. Statement Cache

`binlog_stmt_cache_size` specifies the memory cache for statements that cannot roll back transactionally, such as statements modifying tables using non-transactional storage engines. MySQL uses the statement cache to handle this class of events.

The corresponding upper limit is `max_binlog_stmt_cache_size`. If the statement cache exceeds its memory allocation, MySQL can use a temporary file; if it exceeds the maximum limit, the statement can fail. These two variables serve the statement cache, not as substitutes for `binlog_cache_size` and `max_binlog_cache_size`.

In a workload involving both InnoDB and non-transactional tables, monitor both sets of counters. Watching only the transaction cache can miss pressure originating from the statement cache.

### 1.3. Cache Spill Does Not Mean Binary Log Was Written

When a cache exceeds memory, MySQL writes cache data to a temporary file. This is an intermediate storage step before the event group is written to the binary log. Therefore, an increase in `Binlog_cache_disk_use` does not mean MySQL just wrote another binary log file or that the binary log was safely synced to storage.

Temporary cache files create additional I/O on the filesystem used for temporary files. If `tmpdir` resides on a slow device or is nearly full, large transactions can increase latency or fail even while the binary log partition still has plenty of space.

## 2. Configuration Variables and Limits

Important variables to inspect include:

| Variable | Role | Considerations |
|---|---|---|
| `binlog_cache_size` | Memory size of transaction cache | Increase when significant cache spills occur and RAM budget allows |
| `max_binlog_cache_size` | Maximum transaction cache limit per transaction | Set high enough for the largest valid transaction the system permits |
| `binlog_stmt_cache_size` | Memory size of statement cache | Tune only when statement cache shows actual pressure |
| `max_binlog_stmt_cache_size` | Maximum statement cache limit | Prevent errors for valid non-transactional statements while bounding resource usage |
| `sync_binlog` | Frequency of syncing binary log to storage | Balance data durability and fsync cost |
| `binlog_format` | Event format: `ROW`, `STATEMENT`, or `MIXED` | Affects determinism, log size, and log applicability |
| `binlog_row_image` | Level of before/after image in row events | Affects log volume and data readable by consumers |

Inspect current configuration:

```sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
  'binlog_cache_size',
  'max_binlog_cache_size',
  'binlog_stmt_cache_size',
  'max_binlog_stmt_cache_size',
  'sync_binlog',
  'binlog_format',
  'binlog_row_image'
);
```

Do not set `max_binlog_cache_size` extremely high merely to silence an error from an anomalous transaction. First determine whether that transaction is valid from a business standpoint or is updating far too many records at once. An adequately high limit lets valid workloads succeed, whereas an excessively high limit lets a single session consume heavy resources and put pressure on temporary storage.

## 3. Measuring Cache Usage

MySQL provides status counters to monitor the transaction cache and statement cache:

| Counter | Meaning |
|---|---|
| `Binlog_cache_use` | Number of times transactions used the transaction cache |
| `Binlog_cache_disk_use` | Number of transactions that had to use a temporary file for the transaction cache |
| `Binlog_stmt_cache_use` | Number of transactions that used the statement cache |
| `Binlog_stmt_cache_disk_use` | Number of times the statement cache had to use a temporary file |

Read counters:

```sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
  'Binlog_cache_use',
  'Binlog_cache_disk_use',
  'Binlog_stmt_cache_use',
  'Binlog_stmt_cache_disk_use'
);
```

To evaluate accurately, sample metrics at two points in time and compute deltas across the same load interval. Do not look only at cumulative totals since MySQL startup, because older counter values may reflect a workload that has since changed.

The proportion of transactions using temporary files can be estimated as:

\[
\text{Spill rate (\%)} =
\frac{\Delta \text{Binlog\_cache\_disk\_use}}
     {\Delta \text{Binlog\_cache\_use}} \times 100
\]

Calculate similarly for the statement cache. If the denominator is 0, no corresponding transactions occurred during the measurement window and the rate cannot be interpreted. A high spill rate indicates many transactions exceed the memory cache, though that alone is not enough to conclude the cache must grow: examine transaction sizes, concurrent sessions, `tmpdir` I/O speed, and RAM budget.

To observe variables and counters together, you can run:

```sql
SHOW GLOBAL STATUS LIKE 'Binlog%cache%';
SHOW GLOBAL VARIABLES LIKE '%binlog%cache%';
```

Combine these metrics with commit latency, throughput, temporary filesystem free space, binary log size, and replica lag. A small spill rate may be completely acceptable if temporary file I/O is not a bottleneck.

## 4. Why Do Large Transactions Increase Logging Overhead?

Large transactions can generate many row events, hold caches longer, and require writing a large event group upon commit. Impacts appear across multiple layers:

1. **Memory and temporary storage:** the transaction cache can exceed memory and write temporary files. Many concurrent large transactions increase RAM pressure and `tmpdir` I/O.
2. **Binary log:** commit must flush a large event group into the binlog. Binlog volume grows, requiring more storage for rotation and retention.
3. **Commit latency:** writing large volumes of data and syncing to storage can slow commits. If `sync_binlog` requires frequent syncing, fsync costs also affect latency.
4. **Locks and undo:** long-running transactions usually hold locks longer and generate many undo records. This can force other transactions to wait while slowing InnoDB's purge process.
5. **Replication:** replicas must receive and apply all changes of the transaction. A single large transaction can take a long time to apply and create replica lag; parallel workers do not split a transaction's commit boundary.
6. **PITR:** more logs increase archive storage and the volume of events that must be replayed when recovering to a point in time. Recovery time also depends on log reading speed, change execution, and target host resources.

`max_binlog_size` is also not a hard cap on a single transaction's size. MySQL never splits a committed transaction into multiple independent transactions just to keep each binlog file under this value; one large transaction can push a file past the threshold before rotation occurs.

### 4.1. Row Event Size

With `binlog_format=ROW`, the binary log records changes at the row level. This avoids many non-determinism problems of statement-based replication, yet a statement updating millions of records can produce an enormous volume of row events.

`binlog_row_image` governs how much image data is recorded for row events:

- `FULL`: records full images per row-event rules; convenient for certain auditing tools, CDC, or consumers requiring full before/after data, though usually consumes more space.
- `MINIMAL`: records only columns required to identify the row and changed columns per MySQL rules; can significantly reduce volume for wide tables.
- `NOBLOB`: omits unnecessary BLOB/TEXT data in supported cases.

Reducing the row image changes how much information downstream tools receive. Before using `MINIMAL` or `NOBLOB`, check requirements for CDC, auditing, binlog decoding, and recovery workflows. Never trade away recoverability or consumer-required data merely to shrink log volume.

## 5. Tuning Logging Overhead

Effective tuning starts with metrics. Do not increase every cache variable or lower durability simply because commits appear slow.

### 5.1. Increasing Cache Only When Metrics Prove Necessary

If `Binlog_cache_disk_use` climbs rapidly during normal workloads, determine typical transaction sizes and available RAM. When memory budget permits, moderately increasing `binlog_cache_size` can keep more transactions' events in RAM.

Runtime change example on versions supporting dynamic modification:

```sql
-- Illustrative example: 128 KiB, not an optimal value for every system
SET GLOBAL binlog_cache_size = 131072;
```

`GLOBAL` changes do not necessarily persist across restarts; to retain settings, update startup configuration according to your system's configuration management process. Verify required administrative privileges and variable mutability on your exact version before running.

Re-evaluate counters, RAM, and I/O after the change. If cache spills drop while memory usage climbs excessively under high concurrency, rebalance accordingly. `binlog_stmt_cache_size` should only be increased when statement cache counters indicate a corresponding issue.

### 5.2. Choosing Appropriate Upper Limits

If a valid transaction fails because it exceeds `max_binlog_cache_size`, measure the binlog data required for that transaction and set a new limit aligned with tested maxima. Do the same with `max_binlog_stmt_cache_size` for the statement cache.

Do not rely on raising limits as your sole measure. Oversized transactions can cause long locks, large undo histories, temporary storage consumption, and replica lag. When business logic allows, split work into batches sized from actual data measurements.

### 5.3. Considering Format and Row Image

`ROW` is typically chosen for modern replication because replicas apply changes via row events with less dependence on re-executing SQL statements. However, log volume can be large when updating many rows or tables with many wide columns. Evaluate `binlog_row_image=MINIMAL` if consumers do not require full images.

`STATEMENT` can produce smaller logs for certain statements, but you must ensure statements are deterministic and replication-safe. Do not switch from `ROW` to `STATEMENT` solely to save space if doing so raises the risk of replicas diverging from the primary. `MIXED` lets the server choose formats per MySQL rules; you still need to understand workload behavior.

On MySQL versions supporting transaction compression (since MySQL 8.0.20), you can evaluate `binlog_transaction_compression` to reduce transaction payload size in the binary log; this feature applies to row-based payloads. Compression consumes CPU and requires compatibility across versions, replicas, and binlog reading tools. Benchmark with representative data before enabling in production.

### 5.4. Balancing Durability and fsync Cost

`sync_binlog` controls how frequently the binary log is synced to storage. With `sync_binlog=1`, MySQL requests a sync after each commit group; group commit can allow multiple transactions to share a single sync. Values greater than 1 or 0 can lower sync overhead, but increase the chance of losing the most recent binlog writes during an OS or server crash, depending on OS and storage device cache states.

For InnoDB, `innodb_flush_log_at_trx_commit` controls writing and syncing the redo log. The binary log and redo log serve two distinct purposes. In systems requiring high durability, the common configuration is:

```ini
[mysqld]
sync_binlog = 1
innodb_flush_log_at_trx_commit = 1
```

These two settings can increase I/O cost, yet minimize the data-loss window on crash. Only change them after agreeing on RPO, RTO, and acceptable data risk with the organization. Never use weaker durability settings to mask problems caused by oversized transactions or slow storage.

Group commit lets MySQL batch closely timed commits to reduce sync counts. Variables like `binlog_group_commit_sync_delay` and `binlog_group_commit_sync_no_delay_count` can tune group waiting behavior on supported versions. Increasing wait delay can improve throughput in certain workloads while increasing latency; measure before and after rather than applying one universal value across every system.

## 6. Controlling Large Transactions at the Application Layer

### 6.1. Batching When Business Logic Permits

A job updating millions of orders can be processed in batches. The application selects a bounded set of primary keys, updates that set within a short transaction, commits, saves a checkpoint, and proceeds to the next batch.

Illustrative example of a workflow using primary key lists fetched in batches by the application:

```sql
-- Application queries up to the next 1,000 IDs in primary key order.
SELECT id
FROM orders
WHERE archived = 0
  AND created_at < '2024-01-01'
  AND id > 0
ORDER BY id
LIMIT 1000;

-- Application passes the fetched ID list into the update transaction.
START TRANSACTION;

UPDATE orders
SET archived = 1
WHERE id IN (101, 102, 103 /* ... IDs in batch ... */)
  AND archived = 0;

COMMIT;
```

The application should persist the last processed primary key or an equivalent checkpoint, advancing the checkpoint only after a successful commit. The `archived = 0` condition helps make reruns safer if the process is interrupted. A batch size of 1,000 is just an example; an appropriate row count depends on row width, indexes, storage speed, lock contention, and replica limits.

Batching reduces per-transaction size, lock hold duration, and the volume of binlog committed at once. In exchange, batches commit independently, so the overall job no longer has the atomicity of a single transaction. Checkpoints, idempotent retries, progress monitoring, and failure resumability are required.

### 6.2. Keeping One Large Transaction When Atomicity Is Mandatory

Do not split an operation into multiple commits if business requirements demand that all changes succeed or fail together. In that situation, you must:

- Estimate the transaction's binlog and undo size before execution.
- Ensure `max_binlog_cache_size`, `tmpdir`, and the binlog filesystem have sufficient capacity.
- Run during an appropriate window, control concurrency, and monitor lock waits.
- Verify replicas have enough apply capacity and binlog retention suffices for PITR.
- Have a rehearsed rollback or recovery plan.

If a transaction cannot be split while meeting business rules, resource limits must be engineered for that case. Never assume simply raising cache size removes all transaction costs.

## 7. Diagnostic Workflow When Binlog Causes Slowdowns

When commits slow down or replica lag climbs, isolate which layer is generating cost step by step:

1. **Inspect workload:** identify which transactions generate heavy changes, how long transactions stay open, and how many rows are affected. Use query logs, application tracing, or existing observability tools.
2. **Inspect cache counters:** compare deltas of `Binlog_cache_use`, `Binlog_cache_disk_use`, and statement cache counters over the same load window.
3. **Inspect temporary storage:** observe free space, latency, and throughput of the `tmpdir` filesystem; look for I/O spikes while large transactions run.
4. **Inspect binary logs:** track volume growth rate, file rotation frequency, and write/sync times. Remember `max_binlog_size` does not split a single transaction.
5. **Inspect durability and storage:** confirm `sync_binlog`, `innodb_flush_log_at_trx_commit`, and storage device performance; do not lower durability before evaluating RPO.
6. **Inspect replicas:** use `SHOW REPLICA STATUS` on versions supporting this syntax, monitoring receiver/applier states, errors, and lag time. Distinguish log transfer time from transaction apply time.
7. **Test one controlled change:** alter one factor at a time, re-run a representative workload, and compare throughput, p95/p99 commit latency, cache spills, disk I/O, and replica lag.

Combined inspection queries:

```sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
  'Binlog_cache_use',
  'Binlog_cache_disk_use',
  'Binlog_stmt_cache_use',
  'Binlog_stmt_cache_disk_use'
);

SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
  'binlog_cache_size',
  'max_binlog_cache_size',
  'binlog_stmt_cache_size',
  'max_binlog_stmt_cache_size',
  'sync_binlog',
  'innodb_flush_log_at_trx_commit'
);
```

`SHOW REPLICA STATUS` may be replaced by legacy syntax on releases prior to the command rename. Use syntax matching your server version and inspect lag fields along with SQL/applier thread state rather than relying on a single lag number.

## 8. Practice Exercise

An e-commerce system runs InnoDB and `binlog_format=ROW`. Every night, a job updates archive status for roughly 5 million orders. While the job runs:

- `Binlog_cache_disk_use` rises rapidly.
- Commit latency increases markedly.
- Replica lag persists long after the job finishes.
- Binary log volume grows faster than on normal days.

Design a remediation plan and justify your decisions:

1. Which additional metrics do you need to determine whether transaction cache spills are the primary cause? Explain how to obtain deltas for the four cache counters.
2. When should `binlog_cache_size` be increased? Why must RAM and concurrent session counts be reviewed before raising it?
3. When should `max_binlog_cache_size` be reviewed? What happens if a transaction exceeds the maximum limit?
4. Design a batching approach by primary key with checkpointing and retries so the job can resume after failure. Specify what atomicity properties change when each batch commits separately.
5. In what cases can `binlog_row_image=MINIMAL` reduce volume? Which downstream tools must be verified before making the change?
6. Explain the relationship between `sync_binlog` and `innodb_flush_log_at_trx_commit`. Why should durability not be lowered just to make the job finish faster?
7. Propose how to check replica apply performance and estimate the job's impact on PITR recovery duration.

A solid plan must specify before/after metrics, configuration rollback criteria, and how to verify data correctness once the job completes.

## 9. Common Misconceptions

- **Assuming `Binlog_cache_disk_use` counts binary log disk writes:** this counter reflects how often the transaction cache spilled to temporary files when memory was insufficient.
- **Increasing `binlog_cache_size` without checking concurrency:** a large value can substantially raise RAM demand under concurrent load.
- **Increasing `max_binlog_cache_size` to accommodate every huge transaction:** a higher limit permits larger transactions but does not solve long locks, large undo histories, replica lag, or storage costs.
- **Batching without reviewing business requirements:** multiple small transactions lack the atomicity of a single transaction; controlled checkpointing and retries are needed.
- **Lowering `sync_binlog` without evaluating RPO:** performance may improve, but the risk of losing recent binary logs on crash increases.
- **Assuming `max_binlog_size` is an absolute file size limit:** a single transaction can push a binlog file past the threshold before MySQL rotates.
- **Choosing `MINIMAL` without checking consumers:** audit or CDC tools may require full row images to interpret changes.

## Conclusion

The binlog cache temporarily buffers events before transactions are written to the binary log. When memory cache is insufficient, MySQL uses temporary files; when a transaction exceeds the maximum limit, the transaction can fail. Large transactions also increase binlog volume, commit time, lock/undo pressure, replica lag, and PITR duration. Optimization requires combining counter observation, tuning caches within RAM budgets, controlling transaction size, selecting an appropriate row image, and maintaining durability settings aligned with agreed RPO. Measure with representative workloads and verify both replicas and recovery procedures after every significant change.
