# Adaptive Hash Index, Change Buffer, and Version-Specific Feature Conditions

## Objectives

In the `DATABASE_MYSQL` module, you master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, and concurrency control. You practice reading execution plans, optimizing queries, managing privileges, backups, and handling relational database operational issues. In the **System Performance** chapter, this lesson explains two internal InnoDB mechanisms—the adaptive hash index and the change buffer—how they affect reads/writes, how to monitor them, and default changes across MySQL versions.

After this lesson, you will be able to:

- Distinguish the adaptive hash index from user-created B-tree indexes.
- Explain how the change buffer defers updates to secondary index pages to reduce random I/O.
- Recognize suitable workloads, overhead, and bottleneck symptoms for each mechanism.
- Read relevant InnoDB configuration variables and monitoring metrics.
- Compare differences across MySQL 8.0, 8.4, and 9.7 before upgrading or changing configurations.

## 1. Two Internal Mechanisms in the InnoDB Performance Picture

InnoDB organizes data using clustered indexes and secondary indexes, typically based on B-tree structures. The buffer pool keeps frequently accessed data and index pages in memory. When a needed page is not in the buffer pool, InnoDB may have to read it from storage. Under workloads with heavy random access, I/O cost and thread synchronization can become bottlenecks.

The adaptive hash index (AHI) adds a hash-based lookup path for repeated, frequent B-tree search patterns. The change buffer temporarily holds modifications to eligible secondary index pages not currently in the buffer pool, then merges those changes when pages are loaded or when InnoDB has background processing capacity.

The two mechanisms solve two distinct problems:

| Mechanism | Focus | Expected Impact |
|---|---|---|
| Adaptive hash index | Speeds up certain repeated index reads | Reduces B-tree traversal cost for suitable lookup patterns |
| Change buffer | Defers certain writes to secondary index pages not in the buffer pool | Reduces small random reads/writes, batching updates for later processing |

They are internal InnoDB optimizations. Neither replaces proper index design, index-friendly SQL queries, an appropriately sized buffer pool, or measurement on real workloads.

## 2. Adaptive Hash Index (AHI)

### 2.1. How the AHI Is Built

AHI is a hash structure managed automatically by InnoDB. InnoDB observes search patterns on B-trees; when it detects that certain index pages are accessed frequently and the search pattern benefits, the engine builds hash entries based on a prefix of the index key. Only qualifying portions of data are placed into AHI. Operators do not create AHI with `CREATE INDEX` and do not specify individual columns for it.

For example, an application repeatedly looks up orders by `order_id`:

```sql
SELECT order_id, status, total_amount
FROM orders
WHERE order_id = 900001;
```

If the index and related pages are accessed frequently, AHI can help InnoDB look them up faster once the pattern is recognized. Queries still rely on the underlying B-tree index; AHI is an extra acceleration path built by the engine when beneficial.

AHI tends to be helpful when:

- The workload has many repeated lookups over the same key range or key prefix.
- Frequently used index pages already reside in the buffer pool.
- The system has sufficient buffer pool memory and stable access patterns.
- Lookup savings outweigh the cost of monitoring and maintaining the hash table.

AHI may provide little benefit or add overhead when:

- The workload consists mostly of scans, wide range scans, or scattered non-repeating access.
- Queries use leading-wildcard `LIKE` patterns such as `LIKE '%abc'`.
- Many concurrent threads contend on latches protecting AHI, such as high-concurrency join workloads.
- Data and indexes change continuously so hash maintenance cost outweighs read gains.

Do not declare AHI universally good or bad based solely on application type. The same system may benefit from AHI during read peaks yet suffer contention when thread counts spike. Measure throughput, p95/p99 latency, CPU, and latch wait times under the same load scenario.

### 2.2. Partitions and Latch Contention

AHI is divided into partitions; each partition has its own latch to reduce contention when many threads access it concurrently. `innodb_adaptive_hash_index_parts` controls the partition count. In MySQL 8.4, the default is `8`, the allowed range is `1` to `512`, and the variable is non-dynamic, requiring configuration at server startup.

If AHI improves lookups yet many threads wait on rw-latches associated with `btr0sea.c`, you can try increasing partitions or disabling AHI. Adding partitions does not guarantee improvement: re-measure because it also alters how the hash structure is partitioned and managed. When AHI does not help the workload, disabling it completely can eliminate tracking and synchronization overhead.

`innodb_adaptive_hash_index` can be changed dynamically at `GLOBAL` scope. When turned off, InnoDB empties the hash table and queries continue using the B-tree; when turned back on, the hash table is rebuilt gradually during normal operations. Therefore, benchmarks must include a warm-up phase and should not compare a warmed run against a run immediately after enabling AHI.

## 3. Change Buffer

### 3.1. The Problem the Change Buffer Solves

When `INSERT`, `UPDATE`, or `DELETE` modifies a secondary index, the index page containing the target entry may not be in the buffer pool. Updating it immediately would force InnoDB to read the page from disk just to change a small portion, creating random I/O. This is especially costly when indexes exceed cache size and writes scatter across many key values.

The change buffer stores eligible modifications for secondary index pages when those pages are not yet in the buffer pool. When a page is later loaded into the buffer pool by a read operation, InnoDB merges the pending changes into the page. Background threads can also merge changes when the system is nearly idle or during a slow shutdown.

For example, a table has multiple secondary indexes and new rows arrive with scattered key values. Instead of forcing every write to immediately read various secondary index pages from disk, InnoDB can record changes in the change buffer and batch-process them when the corresponding pages are loaded.

The change buffer is not a query result cache, does not hold full new table rows, and does not replace redo/undo logs. It optimizes updates to certain secondary index pages. In memory, the change buffer uses a portion of the buffer pool; on disk, this structure resides in the system tablespace so pending changes persist across restarts.

### 3.2. Supported Scope and Limitations

Change buffering applies only to secondary indexes. Clustered indexes, `FULLTEXT` indexes, and `SPATIAL` indexes are not supported by the change buffer. Important conditions apply:

- `INSERT`s into unique secondary indexes are not buffered because InnoDB must verify uniqueness before inserting the entry. Other change buffering types such as delete marking and purging can still apply to unique indexes when eligible.
- Change buffering is not supported for secondary indexes containing descending index columns, or when the primary key has descending columns.
- Only secondary index pages not currently in the buffer pool are candidates. If a page is already in the buffer pool, InnoDB updates it in memory along the normal path.
- `UPDATE` can generate both inserting a new entry and delete-marking the old entry, thus involving multiple change buffering categories.

Because of these limits, the change buffer does not accelerate every write. Specifically, do not expect it to speed up bulk inserts into unique indexes or tables with unsupported index types.

### 3.3. Benefits and Overhead

The change buffer is often helpful when data exceeds the buffer pool, multiple secondary indexes are updated frequently, and the workload is random-I/O bound. It reduces page reads needed merely to update a single index entry, batching multiple modifications for more efficient writes.

In return, the change buffer consumes buffer pool capacity and creates deferred merge work. If merging fails to keep up with incoming modifications, a backlog can build. When merging occurs, background I/O can climb and slow down read queries, especially on disk-bound systems. Merging can continue after transactions commit and even after server restarts; this does not mean transactions are uncommitted, only that deferred secondary index updates are being processed by InnoDB.

Consider disabling change buffering or keeping it low when:

- The working set fits or nearly fits in the buffer pool and reserving space for the change buffer displaces useful data cache.
- Tables have few secondary indexes or low index update rates.
- Storage devices have low random-read latency, shrinking the benefit of deferring random reads.
- The system frequently faces I/O pressure from merges, recovery, or heavy write tasks.

SSDs do not automatically render the change buffer useless. Measure with your own device type, data size, indexes, and concurrent load.

## 4. Feature Conditions and Default Changes Across Versions

A common upgrade pitfall is confusing **whether a feature still exists** with **whether its default value changed**. AHI and change buffering still exist in the modern MySQL series listed below, yet their defaults differ.

| MySQL Version | Default `innodb_adaptive_hash_index` | Default `innodb_change_buffering` | Default `innodb_change_buffer_max_size` |
|---|---:|---|---:|
| 8.0 | `ON` | `all` | `25` |
| 8.4 | `OFF` | `none` | `25` |
| 9.7 | `OFF` | `none` | `5` |

The values above are the documented defaults for each published release series. Check patch releases, distributions, and actual server configuration before applying changes. If an option file explicitly sets a variable, that configuration can override the version default.

Key milestones and conditions to remember:

- MySQL 5.5 expanded the change buffer to support buffering changes from `UPDATE` and `DELETE`; previously it primarily served `INSERT` and was commonly called the insert buffer.
- MySQL 5.6 added `innodb_change_buffer_max_size`, allowing the change buffer cap to be set as a percentage of the buffer pool.
- Starting in MySQL 8.4, the default for AHI switched from `ON` to `OFF`, and the default for `innodb_change_buffering` switched from `all` to `none`. This is a default change, not a removal of the two features.
- In MySQL 8.4, `innodb_adaptive_hash_index_parts` defaults to `8`, has a maximum of `512`, and is non-dynamic. `innodb_adaptive_hash_index` is a dynamic `GLOBAL` variable.
- `innodb_change_buffering` and `innodb_change_buffer_max_size` are dynamic `GLOBAL` variables. Changing `innodb_change_buffering` affects only new operations; existing buffered entries still need to be merged.
- In current MySQL 9.7 documentation, `innodb_change_buffer_max_size` defaults to `5`; do not carry over the `25` default from 8.0/8.4 configs without checking.

When upgrading from 8.0 to 8.4 or 9.7, check both config files and running values. Do not assume the server still enables AHI or change buffering just because 8.0 previously used those defaults. Conversely, if the config file explicitly specifies `ON` or `all`, the server may continue using those values after upgrading.

## 5. Reading Configuration and Observing Activity

### 5.1. Verify Version and Running Variables

Before evaluating performance, record the version and actual variable values:

```sql
SELECT VERSION();

SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
  'innodb_adaptive_hash_index',
  'innodb_adaptive_hash_index_parts',
  'innodb_change_buffering',
  'innodb_change_buffer_max_size'
);
```

`SHOW GLOBAL VARIABLES` reflects the active runtime values, accounting for option files and runtime changes. Use it as your ground truth before comparing against version default tables.

### 5.2. Observing AHI

Run the following command in a MySQL client to view the InnoDB Standard Monitor:

```sql
SHOW ENGINE INNODB STATUS\G
```

In the `INSERT BUFFER AND ADAPTIVE HASH INDEX` section, note counts such as hash searches and non-hash searches. These show whether AHI is being used; a high hash-search ratio alone does not prove better overall performance.

In the `SEMAPHORES` section, look for threads waiting on rw-latches related to `btr0sea.c`. If many threads are waiting, AHI may be a point of contention. Correlate wait times with CPU, throughput, p95/p99 latency, and concurrent load. Depending on findings, test AHI on/off or more partitions in a controlled experiment.

### 5.3. Observing the Change Buffer

In the same `SHOW ENGINE INNODB STATUS` output, the `INSERT BUFFER AND ADAPTIVE HASH INDEX` section contains `Ibuf` and `merged operations` lines to track size, merge counts, and merged operation types. Capture metrics over intervals to check whether the backlog grows steadily or drains evenly.

You can list InnoDB metric names and descriptions with:

```sql
SELECT NAME, COMMENT
FROM information_schema.innodb_metrics
WHERE NAME LIKE '%ibuf%';
```

To inspect change buffer mutex instrumentation:

```sql
SELECT NAME, ENABLED, TIMED
FROM performance_schema.setup_instruments
WHERE NAME LIKE '%wait/synch/mutex/innodb/ibuf%';
```

Enable extra instrumentation only according to your environment's observability procedures, since timing collection carries overhead. Avoid querying `INFORMATION_SCHEMA.INNODB_BUFFER_PAGE` in production solely to count change buffer pages: that table can cause significant overhead. If detailed page-type analysis is needed, reproduce it on a test instance.

## 6. Controlled Configuration Changes

The examples below illustrate changing `GLOBAL` variables while the server is running. Appropriate privileges and impact assessment are required before running in production.

Disable AHI:

```sql
SET GLOBAL innodb_adaptive_hash_index = OFF;
```

Enable AHI for testing:

```sql
SET GLOBAL innodb_adaptive_hash_index = ON;
```

Choose change buffering scope:

```sql
-- Do not buffer new operations
SET GLOBAL innodb_change_buffering = 'none';

-- Buffer inserts only if supported by workload/version and proven helpful via benchmark
SET GLOBAL innodb_change_buffering = 'inserts';
```

Valid values for `innodb_change_buffering` include:

| Value | Operations Buffered |
|---|---|
| `none` | No operations buffered |
| `inserts` | Inserts |
| `deletes` | Delete marking, i.e., marking index records for later deletion |
| `changes` | Inserts and delete marking |
| `purges` | Physical deletions during background purge |
| `all` | Inserts, delete marking, and purges |

`UPDATE` is a composite modification that can involve both inserting and delete marking. Choosing a value must reflect actual workloads and the values supported by the running version.

`innodb_change_buffer_max_size` specifies the maximum percentage of total buffer pool capacity reserved for the change buffer. In MySQL 8.4, the default is `25` with a range of `0`–`50`; in MySQL 9.7, the default is `5`. Consider increasing it only when heavy write workloads cause the change buffer to hit its cap while merging lags behind. Consider lowering it when the change buffer displaces memory needed for data pages or when the server primarily handles reporting on relatively static data. Do not raise the limit solely because change buffer numbers look large; inspect merge backlog, I/O, and buffer pool pressure first.

Example changing the limit at runtime:

```sql
SET GLOBAL innodb_change_buffer_max_size = 20;
```

The number `20` is a syntax example only, not a default recommendation. `innodb_adaptive_hash_index_parts` is non-dynamic in MySQL 8.4; changing it requires setting it in an option file or startup option and restarting during a maintenance window. Always verify version-specific documentation before using this variable.

## 7. Benchmarking Process to Decide On or Off

Never change AHI, change buffering, buffer pool size, and multiple I/O variables in the same test run. Changing multiple factors makes it very difficult to isolate what caused the outcome.

Suggested comparison workflow:

1. Record MySQL version, variable settings, buffer pool size, storage type, and relevant schemas/indexes.
2. Select a representative workload: read/write ratio, lookup patterns, secondary index count, concurrency, working set size, and key distribution.
3. Measure baseline over a steady interval: throughput, p95/p99 latency, CPU, read/write IOPS, buffer pool hit behavior, semaphore/latch waits, and change buffer merges.
4. Change one mechanism or one variable in a test environment; keep data, queries, and load levels constant.
5. Run warm-up long enough, especially after enabling AHI because the hash table builds incrementally. For change buffer tests, observe both the load phase and the post-load merge phase.
6. Repeat multiple times and compare the same metrics. If results fluctuate widely, lengthen test runs or reduce background noise.
7. Apply only when the target metric improves without meaningfully degrading p99 latency, background I/O, memory pressure, or stability.

Example result interpretation:

| Observation | Investigation Direction |
|---|---|
| AHI on increases read throughput and keeps latch waits low | AHI likely fits the workload's repeated lookups |
| AHI on raises CPU or rw-latch waits, worsening p99 | Try increasing partitions in test or turning AHI off |
| Change buffer reduces random reads during writes and merges steadily | Mechanism likely helps an I/O-bound workload |
| Change buffer grows continuously, merges create background I/O, and reads slow down | Check write rate, secondary indexes, buffer cap, and test lowering/disabling buffering |
| 8.0 and 8.4 yield different results with unchanged app | Compare changed defaults and option files after upgrade |

## 8. Operational Checklist

Before and after changing configuration, verify:

- [ ] Recorded `SELECT VERSION()` and actual values of relevant variables.
- [ ] Distinguished version defaults from values set in option files or at runtime.
- [ ] Evaluated AHI on real lookup workloads, including contention and p95/p99 latency.
- [ ] Inspected `SEMAPHORES` in InnoDB status if AHI latch contention is suspected.
- [ ] Confirmed workload eligibility for change buffering: secondary index pages not in buffer pool and supported index types.
- [ ] Factored in merge backlog, background I/O, and buffer pool capacity when evaluating the change buffer.
- [ ] Checked default changes from MySQL 8.0 to 8.4 and from 8.4 to 9.7 when upgrading.
- [ ] Benchmarked each change separately, including warm-up and monitoring of the merge phase.
- [ ] Prepared a rollback plan and post-change monitoring for production.

## Conclusion

The adaptive hash index speeds up certain repeated read patterns using an InnoDB-managed hash structure, yet can cause latch contention at high concurrency. The change buffer defers certain updates to secondary index pages absent from the buffer pool to cut random I/O, at the cost of future merge work and buffer pool space. Both mechanisms must be evaluated separately against workload, index types, storage hardware, and concurrency. When operating or upgrading, always check actual runtime values: MySQL 8.4 changed the defaults of AHI to `OFF` and change buffering to `none`; MySQL 9.7 keeps those defaults and sets `innodb_change_buffer_max_size` default to `5`. Make changes only after measuring, understanding support conditions, and preparing monitoring and rollback plans.

## References

- [MySQL 8.4 Reference Manual: Adaptive Hash Index](https://dev.mysql.com/doc/refman/8.4/en/innodb-adaptive-hash.html)
- [MySQL 8.4 Reference Manual: Change Buffer](https://dev.mysql.com/doc/refman/8.4/en/innodb-change-buffer.html)
- [MySQL 8.4 Reference Manual: InnoDB Startup Options and System Variables](https://dev.mysql.com/doc/refman/8.4/en/innodb-parameters.html)
- [MySQL 8.4 Reference Manual: Changes in MySQL 8.4](https://dev.mysql.com/doc/refman/8.4/en/upgrading-from-previous-series.html)
- [MySQL 9.7 Reference Manual: InnoDB Startup Options and System Variables](https://dev.mysql.com/doc/refman/9.7/en/innodb-parameters.html)
- [MySQL 9.7 Reference Manual: Change Buffer](https://dev.mysql.com/doc/refman/9.7/en/innodb-change-buffer.html)
