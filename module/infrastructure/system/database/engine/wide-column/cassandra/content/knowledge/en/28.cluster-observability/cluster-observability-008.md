# Memtables, Flush Queues, and Pending Compactions in Apache Cassandra Cluster Observability

> **Chapter:** Cluster Observability  
> **Focus:** Accurately reading the write lifecycle from memtable to SSTables, spotting stalled flush queues and lagging compaction, and separating symptoms from root causes using `nodetool`, JMX/metrics, OS tools, and Java application telemetry. Content targets Apache Cassandra 4.1/5.0; exact metrics, thread pools, and settings vary by version or distribution.

## 1. Learning objectives

After this lesson, you will be able to:

1. Distinguish an **active memtable**, a **switched memtable awaiting flush**, **flush writers**, **immutable SSTables**, **compaction tasks**, and the **commit log**.
2. Correctly interpret `MemtableOnHeapSize`, `MemtableOffHeapSize`, `AllMemtablesOnHeapSize`, `MemtableSwitchCount`, `PendingFlushes`, `PendingCompactions`, and `Compaction.PendingTasks`.
3. Pinpoint which queue is actually backed up using `nodetool tpstats` and pools such as `MemtableFlushWriter`, `PerDiskMemtableFlushWriter_*`, `MemtablePostFlush`, and `CompactionExecutor`.
4. Correlate metrics along **node → table → workload** to separate RAM, I/O, CPU, flush, and compaction pressure.
5. Design dashboards and **trend-based** alerts instead of firing on a single non-zero snapshot, and avoid mistakes when taking differences between gauges and counters.
6. Practice observation in a lab using CQL, `nodetool`, and a Java Driver example, and build a runbook to drain backlogs without losing data or triggering a “compaction storm”.

In Cassandra's distributed architecture, each replica writes and flushes **locally**. A client write can succeed at `LOCAL_QUORUM` even while a peer replica is struggling with heavy flushes or compaction. Observability must therefore track **per node, datacenter, table, and read/write consistency level**, never relying solely on cluster-wide averages.

## 2. The write path: why are there two queues?

Cassandra uses a **Log-Structured Merge Tree (LSM-tree)**-style write path. Each mutation is appended to the **commit log** for crash recovery and applied to the table's **memtable**. The memtable serves live reads in memory and is eventually flushed into one or more immutable SSTables.

~~~text
Java Application / CQL
       |
       | WRITE with consistency level
       v
    Coordinator ---> natural replicas
                          |
                   +------+------+
                   |             |
                CommitLog      Memtable (active)
                   |             |
             segment / fsync      | reaches threshold or requested
                   |             v
                   |        Memtable switch
                   |             |
                   |        Flush queue / writers
                   |             |
                   |             v
                   |        New SSTable on disk
                   |             |
                   +--> Post-flush / eligible commit log
                         segments can be reclaimed
                                 |
                              Many SSTables
                                 |
                                 v
                          Compaction backlog
                                 |
                            Compaction workers
                                 |
                         New output SSTables
~~~

Distinguish the two background pipelines:

| Task | Input | Output | When it slows down |
|---|---|---|---|
| **Flush** | Switched memtables | SSTables written to disk; memtables freed when safe | Pending flushes / flush thread pool climbs, memtable pressure, potential allocation blocking |
| **Compaction** | Multiple SSTables or SSTable maintenance tasks | Merged/rewritten SSTables; old files dropped when eligible | Pending compactions, SSTable count, write amplification, reads touching many SSTables |

**Flushing is not compaction.** A flush creates a **new** SSTable, which can increase future compaction work. Compaction merges **existing on-disk SSTables** and does not directly write active memtables.

### 2.1. Why do write ACKs not wait for compaction?

For normal durable writes, Cassandra acknowledges a mutation once the commit log/memtable write path and required replica ACKs per CL succeed; it does not wait for compaction. Flushes and compactions run asynchronously in the background. This keeps write throughput high while creating **write amplification** and a need to monitor backlogs.

Still, never translate “write ACKs don't wait for compaction” into “compaction never affects writes.” If the same disk saturates on I/O, compaction slows down flushes, memtables cannot release memory, and the write path hits **backpressure** or timeouts.

### 2.2. Why is data still safe before a memtable flushes?

If a node crashes before a memtable is persisted as an SSTable, Cassandra **replays the commit log** on startup to recover durable mutations per configuration. Commit log segments cannot be reclaimed arbitrarily while they still hold mutations belonging to un-flushed memtables.

Therefore, monitor memtables alongside `CommitLog.TotalCommitLogSize`, `CommitLog.PendingTasks`, and `CommitLog.WaitingOnSegmentAllocation`. When the commit log approaches its cap and forces flushes, you can see **frequent flushes even when individual memtables are small**.

## 3. Memtables: more than a single RAM number

A table normally has an **active memtable**. On a switch, the old memtable enters pending/flushing state while a fresh memtable continues accepting writes. Secondary indexes, materialized views, and auxiliary structures can push total memory above the base table's active memtable alone.

~~~text
            Table: orders_by_customer
                      |
              Active memtable M2
                  (accepting writes)
                      |
           memory limit / manual flush
                      |
                Switch M2 -> M3
                      |
           +----------+----------+
           |                     |
      M2 awaits flush        M3 continues taking writes
           |
      Flush writer
           |
      New SSTable
           |
    Reclaim M2 memory when safe
~~~

### 3.1. Table-level memtable metrics

| JMX Metric (Table scope) | Type | Proper interpretation |
|---|---|---|
| `MemtableOnHeapSize` | Gauge, bytes | Memtable data/structures on the JVM heap, including overhead |
| `MemtableOffHeapSize` | Gauge, bytes | Off-heap memtable footprint, if configured |
| `MemtableLiveDataSize` | Gauge, bytes | Estimated live data size, excluding full overhead |
| `AllMemtablesOnHeapSize` | Gauge, bytes | Total on-heap memtables, **including pending flushes and secondary indexes** per Cassandra's definition |
| `AllMemtablesOffHeapSize` | Gauge, bytes | Total off-heap memtables, including pending and eligible index structures |
| `AllMemtablesLiveDataSize` | Gauge, bytes | Total live data across memtables; not actual physical RAM bytes |
| `MemtableColumnsCount` | Gauge, column/cell count | Columns/cells tracked in the memtable per engine accounting, not table row count |
| `MemtableSwitchCount` | Counter | Number of flush-triggered switches since metric/node startup |

How to reason from these:

- `MemtableOnHeapSize` dropping after a flush **can be normal**, yet if `AllMemtablesOnHeapSize` stays high, old memtables **may still await reclamation** or other memtables/indexes still occupy RAM.
- `MemtableLiveDataSize` being smaller than `MemtableOnHeapSize` is normal: memory includes **structure overhead, overwrites, and management metadata**.
- A steadily rising `MemtableSwitchCount` does not mean queues are backed up; sustained writes or active flushing also increment the counter.
- `MemtableOffHeapSize` being low or 0 does not prove “memtables use no memory”: allocations may simply live on heap.

**Memtable memory is not the entire JVM heap.** Cassandra also uses heap for caches, read/write objects, compaction metadata, internal state, and GC. Read JVM heap usage, direct/off-heap memory, GC pauses, and cgroup/container health alongside it.

### 3.2. Memory limits and when flushes trigger

Common parameters in `cassandra.yaml`:

~~~yaml
# Example parameter names ONLY, NOT recommended copy-paste values.
memtable_heap_space: 2048MiB
memtable_offheap_space: 2048MiB
memtable_allocation_type: heap_buffers

# Options requiring careful version/environment review:
# memtable_flush_writers: 2
~~~

**Do not tune by copying example numbers.** Many parameters in `cassandra.yaml` are commented out and default dynamically by version or data-directory count. `memtable_cleanup_threshold` is marked **deprecated** in modern releases; Apache recommends relying on defaults tied to flush writer counts rather than adjusting it arbitrarily.

Memtable flushes can be triggered by:

1. Memtable usage approaching managed memory thresholds.
2. Commit log reaching its space cap and needing segment cleanup, forcing flushes on tables with dirty data in old segments.
3. Explicit operator commands such as `nodetool flush` (for operations/labs).
4. Lifecycle or maintenance operations requiring a flush per Cassandra internals.

**Never assume a memtable flushes at “exactly 2 GiB per table”.** Memtable space budgets are managed at the node/pool level, and selecting which table flushes depends on multiple factors.

## 4. Flush queues: metrics you must distinguish

Here, **flush queue** refers to switched memtables or related tasks waiting to complete flush/post-flush—not a single queue with one uniform metric name across every Cassandra release.

### 4.1. `PendingFlushes` is an estimate, not a completed-flush counter

In Apache's metric documentation:

| Metric | Documented type | Meaning |
|---|---|---|
| `Table.PendingFlushes` | **Counter** (named/described as pending estimate) | Estimated pending flush tasks for the table at observation time |
| `Table.BytesFlushed` | Counter | Cumulative bytes flushed since node start/restart |
| `Table.MemtableSwitchCount` | Counter | Cumulative memtable switches |
| `ThreadPools.PendingTasks` (flush pool) | Gauge | Tasks **currently queued** in that thread pool |
| `ThreadPools.ActiveTasks` (flush pool) | Gauge | Tasks **currently executing** |
| `ThreadPools.CompletedTasks` (flush pool) | Counter | Cumulative completed tasks; take rate to observe throughput |
| `MemtablePool.BlockedOnAllocation` | Allocation-wait indicator; check exact type in running JMX | Evidence that writes blocked waiting for memory freed after a flush |

**Metric naming trap:** Apache documents `PendingFlushes` as `Counter`, yet describes it as the **estimated number of pending flush tasks**. Therefore, **do not blindly apply `rate()`/`increase()` just because its type says Counter** as you would for a monotonic completion counter. Inspect actual values, upward/downward movement, and `tpstats`, and verify exporter mapping before writing PromQL.

### 4.2. Thread pools commonly involved in flushing

In Cassandra 4.x/5.0, documented pool names include:

| Pool (typical form) | Responsibility | When `PendingTasks` rises steadily |
|---|---|---|
| `MemtableFlushWriter` | Writes memtables out as SSTables | Flushes are backed up; check whether per-disk writers also exist |
| `PerDiskMemtableFlushWriter_0`, `_1`... | Writer dedicated to each data directory/disk | Can isolate a bottleneck to **one specific disk** |
| `MemtablePostFlush` | Post-flush work, including commit log reclamation when eligible | SSTables may already be written while segment cleanup lags |
| `MemtableReclaimMemory` | Frees/recycles memtable memory | Explains why memory does not drop instantly after flush |
| `CompactionExecutor` | Executes SSTable compactions | Never lump compaction queues into flush queues |

Exact pool names and counts vary by version, OS, and data-directory layout. Always verify against `nodetool tpstats` on your **running binary** rather than assuming every cluster shares identical pool names.

**Illustrative** `tpstats` example (**not** live output from a real node):

~~~text
Pool Name                         Active   Pending   Completed   Blocked
MemtableFlushWriter                  2         7         380       0
MemtablePostFlush                    1         3         377       0
PerDiskMemtableFlushWriter_0         2         5         379       0
CompactionExecutor                   2        18         212       0
~~~

`Pending=7` on a pool and `PendingFlushes=7` on a table **are not necessarily equivalent**. One is scoped to a **thread pool** and the other to a **table**; a flush spans multiple stages, so several pools can reflect different pieces of the same work. **Never sum all `PendingTasks` together** and call it “total flushes”.

### 4.3. `MemtablePool.BlockedOnAllocation` is a high-signal symptom

Per Apache's documentation for `memtable_flush_writers`, `MemtablePool.BlockedOnAllocation` should be 0 under normal conditions; non-zero values indicate **threads blocking on memtable memory allocation while waiting for flushes to free space**.

This matters far more than seeing `PendingFlushes=1` at a single instant because it directly links backlog to write-path stalls. Verify the exact MBean/metric type on your running version before alerting, and confirm whether it reports instantaneous blocked threads or another statistic.

## 5. Pending compactions: why do growing SSTables create sustained pressure?

Flushes produce additional SSTables; `UPDATE`/`DELETE` operations do not modify old files in place but write newer versions. **Compaction** picks sets of SSTables, merges them, drops shadowed data and eligible tombstones, writes output SSTables, and deletes obsolete inputs when safe.

~~~text
Flush #1 -> SSTable 001  ┐
Flush #2 -> SSTable 002  ├-> Compaction per strategy -> SSTable 005
Flush #3 -> SSTable 003  ┤                        \
Flush #4 -> SSTable 004  ┘                         \-> Reduces SSTable count
                                                   when output consolidates
~~~

When new SSTables arrive faster than compaction can consolidate them over a sustained period:

- Table SSTable count climbs; reading a partition may touch many files.
- Disk I/O and read amplification rise, especially under heavy `UPDATE`/`DELETE` workloads and overlapping SSTables.
- Temporary disk headroom needed for compaction outputs grows.
- Compaction competes with flushes and CQL for CPU/I/O, causing **flush queues to grow too**.
- Tombstones can only be purged once grace/compaction conditions are met; never force them away by sacrificing consistency guarantees.

### 5.1. Key metrics and their meanings

| Metric | Scope | Type | Interpretation |
|---|---|---|---|
| `Compaction.PendingTasks` | Node | Gauge | **Estimated** remaining compaction tasks |
| `Compaction.PendingTasksByTableName` | Node / per keyspace-table | Gauge map | Identifies **which tables** contribute to backlog |
| `Table.PendingCompactions` | Table | Gauge | Estimated pending compactions for that table |
| `Compaction.CompletedTasks` | Node | Listed as Gauge in docs | Completed tasks value; verify version/semantics before taking rate |
| `Compaction.TotalCompactionsCompleted` | Node | Meter | Rate of completed compactions |
| `Compaction.BytesCompacted` | Node | Counter, bytes | Cumulative bytes compacted since start/restart |
| `Table.CompactionBytesWritten` | Table | Counter, bytes | Cumulative bytes written by compaction |
| `Table.LiveSSTableCount` | Table | Gauge | Number of **live** SSTables for the table |
| `Table.LiveDiskSpaceUsed` | Table | Bytes indicator | Active SSTable footprint; read alongside `TotalDiskSpaceUsed` |
| `ThreadPools.CompactionExecutor.PendingTasks` | Pool | Gauge | Queued executor tasks; not identical to strategy backlog estimates |

`PendingCompactions`/`PendingTasks` is an **estimate**—not remaining rows to compact, not bytes, and not convertible into an ETA via “pending × average compaction duration”. One massive task can keep pending small while running for hours, while many tiny tasks can drain in seconds.

### 5.2. Reading `nodetool compactionstats`

~~~bash
nodetool compactionstats
nodetool compactionstats -H
~~~

**Simulated** output:

~~~text
pending tasks: 14
- orders.events_by_tenant: 9
- orders.orders_by_id: 5

id            compaction type    keyspace   table             completed  total      unit  progress
...           Compaction         orders     events_by_tenant  24 MiB     96 MiB    bytes 25.00%

Active compaction remaining time: 0h00m36s
~~~

How to read it:

1. **Pending tasks 14** is a point-in-time node estimate, not 14 tasks running concurrently.
2. The progress line tracks the **currently active task**, not an ETA for draining the entire backlog.
3. Per-table counts point you to inspect `events_by_tenant` first.
4. Check history across snapshots: pending rising during bursts then draining is normal; **unrelenting** growth paired with rising SSTable counts, disk pressure, and latency is alarming.
5. Compaction executors also run non-merge maintenance such as repair validation/anti-compaction, `scrub`, or `upgradesstables`; inspect `compaction type` and logs.

### 5.3. Compaction strategy changes what “pending” means

| Strategy | What to read alongside pending | Characteristics |
|---|---|---|
| `SizeTieredCompactionStrategy` (STCS) | SSTable count, size tiers, read amplification | Merges similarly sized files; burst flushes can produce many small SSTables |
| `LeveledCompactionStrategy` (LCS) | SSTable distribution per level, L0 file count, cross-level compactions | Lower-level backlogs can hurt reads and writes |
| `TimeWindowCompactionStrategy` (TWCS) | Time windows, TTL, out-of-window SSTables, out-of-order writes | Great for time series; late-arriving writes keep old windows open |
| `UnifiedCompactionStrategy` (UCS, Cassandra 5.0) | Strategy config, shards/levels, and task sources | Do not interpret like STCS/LCS; tune per version guidance |

**Never compare raw pending task counts across different strategies as an absolute performance score.** Workload, SSTable sizes, strategy rules, and task estimation logic govern the number.

## 6. Separating symptoms along causal chains

Observability is not about listing numbers—it is about locating **where incoming work outpaces background clearing**.

~~~text
                         CQL write rate rises
                                  |
                                  v
                          Memtables fill quickly
                                  |
                         Frequent switches/flushes
                                  |
                 +----------------+----------------+
                 |                                 |
           Flushes keep up                    Flushes wait on I/O
                 |                                 |
          More SSTables created           PendingFlushes climbs
                 |                        MemtablePool blocked
                 |                                 ^
                 v                                 |
       Compaction must keep up                     |
                 |                                 |
          Pending compaction climbs ---+-----> Disk contention
                 |                     |
                 v                     v
       SSTablesPerRead rises       Write/read latency rises
                 |
          Read amplification
~~~

This diagram shows **possible pathways**, not inevitability. Heavy flushing on a table does not always stall compaction, and rising compaction backlog does not instantly cause memtable allocation blocks. Always check **temporal ordering**: which signal moved first, which followed, and what changed when traffic dropped.

### 6.1. Distinguishing five states

| Observed state | Typical metrics | Initial explanation | What to verify next |
|---|---|---|---|
| **Brief write burst** | Memtables, switches, and bytes flushed climb; pending blips briefly then returns to baseline | Usually normal | Queue recovery, p95/p99, disk headroom |
| **Flush writers falling behind** | `PendingFlushes` and flush pool pending climb continuously; all-memtables memory high | Memtables waiting to hit disk | Disk latency, active writers, post-flush, `BlockedOnAllocation` |
| **Compaction falling behind** | `PendingCompactions` climbs for a sustained period; SSTable count and read latency rise | SSTables piling up unmerged | Compaction throughput, strategy, CPU/disk, active tasks |
| **Slow commit log I/O** | `CommitLog.PendingTasks`, `WaitingOnCommit`, or `WaitingOnSegmentAllocation` climb | `fsync`/segment stall, possibly unrelated to memtable size | Commit log disk, allocation, sync mode, disk free |
| **Request/CPU bottleneck elsewhere** | `MutationStage.PendingTasks`/`Native-Transport-Requests.PendingTasks` climb while flush and compaction stay idle | Slow request path distinct from flush backlog | CPU, GC, coordinator, network, query patterns |

Terms like “climbs continuously” must be defined against **your cluster's observation windows and baseline SLOs**. There is no universal “pending > 5 means broken” rule for all Cassandra clusters.

### 6.2. When `AllMemtables...` is high while active memtable is small

Consider two snapshots on a node:

~~~text
At 10:00:
  MemtableOnHeapSize          120 MiB
  AllMemtablesOnHeapSize     650 MiB
  PendingFlushes                  6

At 10:05:
  MemtableOnHeapSize           90 MiB
  AllMemtablesOnHeapSize     710 MiB
  PendingFlushes                  9
~~~

These are **simulated figures** for interpretation practice. The active memtable is modest, yet total memtable memory includes flushed/pending memtables and auxiliary structures. A widening gap paired with growing `PendingFlushes` strongly suggests slow flushing, though **not conclusive** without checking thread pools, `BlockedOnAllocation`, and I/O.

### 6.3. When pending compactions grow while flush queues stay low

~~~text
T0: PendingFlushes=0, PendingCompactions=8,  LiveSSTableCount=35
T1: PendingFlushes=0, PendingCompactions=19, LiveSSTableCount=53
T2: PendingFlushes=0, PendingCompactions=31, LiveSSTableCount=76
~~~

Here compaction backlog is accumulating even though flushes complete promptly. Check per-table metrics, compaction output throughput, disk I/O, STCS/LCS/TWCS/UCS strategy behavior, and read latency impact. **Do not** blindly increase `memtable_flush_writers`: that can create **even more small SSTables** and worsen compaction load.

### 6.4. When `PendingCompactions` is high while SSTable count barely moves

Possible reasons:

- Current tasks are large/long-running; file count does not measure task byte size.
- Pending tasks include maintenance/repair/validation work distinct from regular merges.
- The strategy estimates backlog differently from raw SSTable count.
- Compaction outputs are splitting or replacing files with similar counts.
- Comparisons are accidentally mixing **two different tables/nodes** or a metric exporter reset.

In this case, `nodetool compactionstats`, compaction type, byte progress, `Compaction.BytesCompacted` rates, and disk metrics are far more informative than a single SSTable count snapshot.

## 7. Observing with `nodetool`: a three-tier workflow

### Tier 1 — Is the cluster/node healthy?

~~~bash
# Read status; run on target node or via authorized JMX.
nodetool status
nodetool version
nodetool info
~~~

Check:

1. Which nodes are `DOWN`, `JOINING`, `LEAVING`, or `NORMAL`?
2. Do nodes in the same datacenter diverge in disk space, heap/GC, write latency, or thread queues?
3. Are streaming, repair, bootstrapping, or backups generating background I/O?
4. Is pressure hitting **all replicas of a partition or just one node**?

**A `UN` node** only means `UP/NORMAL` via gossip at that moment—it never proves flush or compaction backlogs are zero.

### Tier 2 — Inspect tables and both queues

~~~bash
nodetool tablestats
nodetool tablestats -H
nodetool tablestats observability_lab.events_by_tenant

nodetool tpstats
nodetool compactionstats
nodetool compactionstats -H
~~~

Supported `tablestats` flags vary by version for human-readable output (`-H`) and structured formats (`-F json` or `-F yaml`). Check `nodetool help tablestats` on your actual binary when scripting.

Read `tablestats` in order:

1. **Memtable data size**, switch count, pending flushes if shown.
2. **SSTable count**, live/total disk space, compaction counters.
3. **Write/read latency**, SSTables per read, tombstone metrics to gauge impact.
4. Focus on **hot tables** or tables diverging across nodes instead of scanning hundreds of tables without workload context.

Read `tpstats` in order:

1. `MemtableFlushWriter` and `PerDiskMemtableFlushWriter_*`: active, pending.
2. `MemtablePostFlush` and `MemtableReclaimMemory`.
3. `CompactionExecutor`.
4. `MutationStage`, `Native-Transport-Requests`, `ReadStage`, and dropped messages (if printed) to spot request-path backpressure.

Read `compactionstats` in order:

1. Node-level pending tasks.
2. Which tables contribute how much.
3. Active tasks, compaction type, completed/total bytes, and progress speed across two samples.
4. Treat the ETA as a rough estimate for the active task only, never a guarantee for clearing the whole backlog.

### Tier 3 — Correlate causes outside Cassandra

~~~bash
# Illustrative OS commands for Linux labs/servers.
# Availability depends on permissions and installed packages.
iostat -xz 1 5
vmstat 1 5
df -h
~~~

Check:

- Disk `await`/latency, throughput, utilization, and divergence **per device**.
- Whether commit log and data directories share a saturated disk/volume.
- User/system CPU, `iowait`, run queue, container CPU throttling.
- Heap GC pauses and direct/off-heap memory.
- Free disk and growth rate, including **snapshots** pinning old SSTables.
- Network/streaming traffic if repair or bootstrap is active.

**Note:** High `%util` on SSD/NVMe does not prove saturation on every system; combine it with latency, I/O queue depth, and actual throughput.

## 8. JMX and metric exporters: names, scopes, and data types

Cassandra uses Dropwizard Metrics, exposed via **JMX**, virtual tables/metric reporters, or monitoring agents. Raw values are **per node**: Prometheus/Grafana or your collector must aggregate deliberately—never assume Cassandra emits cluster-wide totals.

### 8.1. Table metric names over JMX

For table `observability_lab.events_by_tenant`, example MBeans:

~~~text
org.apache.cassandra.metrics:type=Table,keyspace=observability_lab,scope=events_by_tenant,name=MemtableOnHeapSize
org.apache.cassandra.metrics:type=Table,keyspace=observability_lab,scope=events_by_tenant,name=AllMemtablesOnHeapSize
org.apache.cassandra.metrics:type=Table,keyspace=observability_lab,scope=events_by_tenant,name=PendingFlushes
org.apache.cassandra.metrics:type=Table,keyspace=observability_lab,scope=events_by_tenant,name=BytesFlushed
org.apache.cassandra.metrics:type=Table,keyspace=observability_lab,scope=events_by_tenant,name=PendingCompactions
org.apache.cassandra.metrics:type=Table,keyspace=observability_lab,scope=events_by_tenant,name=LiveSSTableCount
~~~

The same metrics may appear under reporter naming:

~~~text
org.apache.cassandra.metrics.Table.MemtableOnHeapSize.observability_lab.events_by_tenant
org.apache.cassandra.metrics.Table.PendingCompactions.observability_lab.events_by_tenant
~~~

Attribute ordering inside a JMX ObjectName can vary without changing meaning. Use a JMX client matching domain/type/keyspace/scope/name rather than brittle string-order parsers.

### 8.2. ThreadPool and Compaction MBeans

~~~text
org.apache.cassandra.metrics:type=ThreadPools,path=internal,scope=MemtableFlushWriter,name=PendingTasks
org.apache.cassandra.metrics:type=ThreadPools,path=internal,scope=MemtablePostFlush,name=PendingTasks
org.apache.cassandra.metrics:type=ThreadPools,path=internal,scope=CompactionExecutor,name=PendingTasks
org.apache.cassandra.metrics:type=Compaction,name=PendingTasks
org.apache.cassandra.metrics:type=Compaction,name=BytesCompacted
org.apache.cassandra.metrics:type=CommitLog,name=WaitingOnSegmentAllocation
~~~

**Do not conflate** `Table.PendingCompactions`, `Compaction.PendingTasks`, and `ThreadPools.CompactionExecutor.PendingTasks`:

- One estimates pending compactions **per table**.
- One estimates pending compactions **node-wide**.
- One measures the **executor's queue** and varies by version/scheduling.

If a dashboard shows only one of the three, you may miss **which table drives the backlog** or whether tasks are even scheduled onto the executor yet.

### 8.3. Exporting to Prometheus with the right types

JMX exporters/agents transform dots, casing, and label names. Never **assume** a Prometheus metric named `cassandra_table_pending_compactions` exists out of the box in every organization.

A **conceptual** dashboard design:

~~~text
Raw JMX:
  Table.PendingCompactions (gauge, per table)
  ThreadPools.PendingTasks (gauge, per pool)
  Table.BytesFlushed (counter)
  Compaction.BytesCompacted (counter)

Exporter:
  <metric_name defined by your config>
  labels: cluster, dc, node, keyspace, table, type/pool

Grafana:
  panel 1: pending flushes by node + table
  panel 2: flush pool active/pending and blocked allocations
  panel 3: pending compactions by node + table
  panel 4: bytes flushed/compacted rates
  panel 5: SSTable count, disk latency, p99 read/write
~~~

Every panel must state **unit, metric type, window, and label grouping**. For cumulative counters like `BytesFlushed`, compute rates (bytes/second) across intervals; for gauges like `PendingCompactions`, plot raw/smoothed levels—never blindly apply `rate()`. For `PendingFlushes`, verify post-exporter semantics since docs classify it as Counter while its meaning is a pending estimate.

### 8.4. Common dashboard mistakes

| Mistake | Why is it wrong? | How to fix it |
|---|---|---|
| Summing `AllMemtablesOnHeapSize` and `MemtableOnHeapSize` | Double-counts active memtable bytes | Pick the right scope; never add overlapping metrics |
| Taking `rate(PendingCompactions)` as throughput | Pending is a **work-remaining gauge**, not a completion counter | Plot pending level/trend alongside `TotalCompactionsCompleted` and `BytesCompacted` |
| Watching cluster averages only | One disk-saturated node gets masked by healthy peers | Use per-node max/p95 and drill down by table |
| Looking at raw SSTable count alone | TWCS and other strategies have different healthy SSTable counts | Combine strategy, SSTables-per-read, pending, and latency |
| Treating “0 pending” as healthy storage | Queue can be 0 due to low traffic, disabled compaction, stalled scheduling, or missing metrics | Check query SLOs, disk/GC, compaction enabled, scrape health |
| Alerting on a single sample | Flushes/compactions are naturally bursty | Alert on sustained windows and recovery time |
| Mixing MiB/MB or microseconds/milliseconds | Breaks threshold/SLA comparisons | Standardize units in exporter and dashboards |
| Ignoring node restarts | Counters reset; post-restart baseline shifts | Use reset-aware rate functions and annotate uptime/restarts |

## 9. Alert design: is a long queue always dangerous?

**There is no single universal pending threshold for every Cassandra cluster.** Build baselines tailored to write rate, compaction strategy, disk hardware, data-directory count, RF, partition size, TTL, and dataset size.

### 9.1. Multi-signal alert structure

An **illustrative policy**—real thresholds must come from history and SLOs:

| Tier | Combined condition | Action |
|---|---|---|
| Watch | Pending flush/compaction elevated for 3–5 min without latency impact and plenty of disk free | Check trend: transient burst vs. sustained growth |
| Flush alert | Pending flush climbs for 10–15 min **and** `AllMemtables...` rises or `BlockedOnAllocation` appears | Investigate disk/flush writers; avoid forcing extra flushes |
| Compaction alert | Pending compaction climbs for 15–30 min **and** SSTable count, read latency, or disk pressure rises | Inspect strategy/throughput and the table driving backlog |
| Urgent | Write timeouts/unavailables climb, allocation/commitlog waits persist, or free disk is critically low | Trigger incident runbook; shed load in a controlled way |

These minute durations **are not Apache Cassandra defaults**. A cluster handling 10-minute bulk loads needs different windows than a latency-sensitive payment cluster.

### 9.2. Arrival rate vs. service rate thinking

Let:

- \(\lambda_f\): rate at which memtables need flushing (tasks/second).
- \(\mu_f\): rate at which flushes complete (tasks/second).
- \(\lambda_c\): rate at which compaction work is generated.
- \(\mu_c\): rate at which compaction work finishes.

Intuitively, when \(\lambda_f > \mu_f\) persists, **flush queues grow**; when \(\lambda_c > \mu_c\), **compaction backlogs grow**. Because tasks vary wildly in size and Cassandra exposes **estimates**, treat this as a **mental model**, not an exact ETA calculator.

Crucially, **raising \(\mu_f\) by adding flush writers** can emit more small SSTables, increasing \(\lambda_c\) and total compaction cost. Always tune **both queues together** alongside disk and CPU capacity.

### 9.3. Alert per node rather than cluster totals alone

For any critical table, alert on:

- Which node has the maximum `PendingFlushes`, not just the cluster sum.
- Which node hits the highest `AllMemtablesOnHeapSize`/memtable budget.
- Which node sees `Compaction.PendingTasks` and `Table.PendingCompactions` rising longest.
- Which node shows sustained `CommitLog.WaitingOnSegmentAllocation` or `BlockedOnAllocation`.
- Which node has high write p99 paired with high disk `await`.

If one replica bottlenecks, `CL=ONE` may hide errors temporarily and `LOCAL_QUORUM` can keep succeeding via healthy peers. **Application write success does not prove every node's flushes and compactions are keeping up.**

## 10. Backlog investigation runbook: find root cause before tuning

### 10.1. Step 1 — Assess impact

Capture baseline facts:

- Cluster, DC/rack/node, Cassandra version, uptime/recent restarts.
- When the issue started; correlation with bulk loads, repairs, bootstraps, snapshots, restores, compaction edits, or app deploys.
- Which tables saw write surges, heavy TTL/DELETEs, or oversized partitions.
- Read/write p95/p99 SLOs, timeouts/unavailables, consistency level (`ONE`/`LOCAL_QUORUM`...), and request classes.
- Free disk, disk I/O latency, CPU, heap/off-heap, and GC.
- **Per-replica** health; never stop at whether one coordinator received ACKs.

If the application starts timing out, **stabilize incoming load** via approved mechanisms while preserving logs and metrics. Never trigger large flushes or major compactions to “clear the queue” on an already saturated disk.

### 10.2. Step 2 — Capture synchronized snapshots

~~~bash
# On the target node, record timestamps alongside command output.
nodetool status
nodetool tablestats -H observability_lab.events_by_tenant
nodetool tpstats
nodetool compactionstats -H
nodetool getcompactionthroughput
nodetool gcstats
~~~

Collect JMX metrics **on that exact node**:

~~~text
Table:
  AllMemtablesOnHeapSize, AllMemtablesOffHeapSize
  MemtableOnHeapSize, MemtableOffHeapSize
  PendingFlushes, MemtableSwitchCount, BytesFlushed
  PendingCompactions, LiveSSTableCount, CompactionBytesWritten

Pools:
  MemtableFlushWriter.PendingTasks/ActiveTasks/CompletedTasks
  PerDiskMemtableFlushWriter_*.PendingTasks/ActiveTasks
  MemtablePostFlush.PendingTasks
  CompactionExecutor.PendingTasks/ActiveTasks/CompletedTasks

Compaction:
  PendingTasks, PendingTasksByTableName, BytesCompacted,
  TotalCompactionsCompleted

CommitLog:
  TotalCommitLogSize, PendingTasks, WaitingOnSegmentAllocation,
  WaitingOnCommit

Others:
  MemtablePool.BlockedOnAllocation (if exposed by binary)
  MutationStage.PendingTasks, ClientRequest.Write Latency/Timeouts
  JVM heap usage, GC pauses, OS disk latency/IOPS, free disk
~~~

**Collect at least two or more points at a fixed cadence** (e.g., every 30–60 seconds over several minutes). A single snapshot cannot tell whether a queue is growing or draining.

### 10.3. Step 3 — Follow the decision tree

~~~text
Pending flushes climbing persistently?
  |
  +-- YES --> AllMemtables* rising? BlockedOnAllocation?
  |            |
  |            +-- YES --> Check memtable budget, disk latency,
  |            |           flush pool active/pending, commit log
  |            |
  |            +-- NO --> Check brief burst flushes,
  |                        metric exporter, and sample timing
  |
  +-- NO --> Pending compactions climbing persistently?
               |
               +-- YES --> Check compaction throughput, strategy,
               |           active tasks, SSTable count, disk pressure
               |
               +-- NO --> If requests remain slow:
                            check CPU/GC, network, read path,
                            commit log fsync, client/coordinator
~~~

If **both queues climb together**, prioritize measuring **disk I/O saturation** and competing disk work: compaction can stall flushes while flushes feed more compaction inputs. Breaking that feedback loop may require **throttling arrival rate or deferring maintenance**, not adding threads.

### 10.4. Step 4 — Evaluate real I/O and throughput

| Observation | Hypothesis | Next step |
|---|---|---|
| Disk latency rises, `PerDiskMemtableFlushWriter_0` pending high | One data directory/volume is constrained | Check hardware, snapshots/repairs, directory layout, and headroom |
| Flush pool always Active near MaxPoolSize, pending growing | Writer concurrency insufficient or I/O slow | Measure throughput, CPU, disk; review flush writers **only after ruling out I/O bottleneck** |
| Compaction backlog grows, actual throughput below cap | CPU/disk/request contention or waiting task | Check active tasks, GC, I/O, and compaction type |
| Compaction backlog grows, throughput flat at cap, disk has headroom | Throughput cap may be too low for workload | Consider raising cap gradually and safely |
| Compaction backlog grows, disk 100% busy / high await | Storage saturation | Do not raise cap; cut contention and plan capacity |
| `WaitingOnSegmentAllocation` high | Commit log segment allocation/flush cleanup lagging | Check commit log disk, post-flush, total free space |
| Low free disk and `TotalDiskSpaceUsed` much larger than `LiveDiskSpaceUsed` | Snapshots/obsolete files or compaction pinning space | Check snapshot/cleanup policy—**never delete files manually** |

### 10.5. Step 5 — Validate after intervention

For **a single approved change**, record:

1. Timestamp, operator, node/table, old/new values, and objective.
2. Did flush pending drop and `BlockedOnAllocation` return to zero?
3. Is compaction pending trending back to baseline, with SSTables/read latency stabilizing?
4. Did disk `await`, CPU, GC, and write p99 improve or worsen?
5. Did it cause more tiny SSTables, new compaction backlogs, or higher disk usage?
6. Do CQL operations at the Java app's CL preserve expected data correctness?

If queues shrink while p99 timeouts climb, **do not call it a success**. A healthy system serves queries within SLA and keeps headroom for future bursts.

## 11. Configuration knobs and commands frequently misused

### 11.1. `memtable_flush_writers`: more is not always better

Per Apache docs, `memtable_flush_writers` controls per-disk flush writer concurrency. Defaults scale with data-directory count; extra writers can help when **I/O stalls occasionally**, yet also emit **smaller, more frequent flushes** that raise compaction cost.

Consider increasing it only after confirming:

- `PendingFlushes`/flush pool pending persists over time.
- Allocation blocking or write latency impact is observed.
- Underlying disks can absorb higher throughput/IOPS (not already saturated).
- Data-directory layout, commit log placement, and storage topology are understood.
- Before/after benchmarks use matching workload and compaction strategy.

**Never** tweak the deprecated `memtable_cleanup_threshold` as a “quick rescue” for slow flushes, and never bloat the heap arbitrarily at the expense of long GC pauses.

### 11.2. `compaction_throughput`: watch disk headroom first

In Cassandra 5.0, `compaction_throughput` caps overall compaction throughput in MiB/s. Inspect on a node with:

~~~bash
nodetool getcompactionthroughput
nodetool help setcompactionthroughput
~~~

Command to **modify** (syntax reference only; DO NOT run in production without approval):

~~~bash
# Lab example only, after measuring disk/CPU headroom and preparing rollback.
# Argument is the MiB/s limit per Cassandra 5.0 nodetool.
nodetool setcompactionthroughput 32
~~~

**Warning:** passing `0` does **not pause compaction**; per documentation, it **disables the throughput limit entirely**. On an already saturated disk, unthrottling compaction can severely degrade read/write p99.

Never treat `32` as a universal magic number: it may be too low or too high for another cluster. Verify behavior across versions via `getcompactionthroughput` and check persistence across restarts.

### 11.3. `concurrent_compactors`: distinguish busy from useful parallelism

Raising compactor threads lets more tasks run concurrently, yet they **compete for disk/CPU** with each other and with flushes. Once disk throughput is saturated, adding workers creates zero extra hardware bandwidth. Per Apache guidance, check `compaction_throughput` and real resources before altering concurrency.

In Cassandra 5.0, specialized tasks such as repair validation have separate workers/limits. Never use `CompactionExecutor.PendingTasks` alone to justify raising concurrency across the board.

### 11.4. `nodetool flush` and `nodetool compact` are not “queue reset” buttons

~~~bash
# LAB node/table example ONLY; never use to cure congestion.
nodetool flush observability_lab events_by_tenant

# Operational docs allow major compaction in specific cases,
# NEVER run ad-hoc to clear production backlogs:
nodetool compact observability_lab events_by_tenant
~~~

Why:

- `flush` **creates flush work** and usually emits new SSTables; when writers are already backed up, it **lengthens the queue**.
- `compact` triggers **massive I/O**, demands temporary disk headroom, and competes with flushes and CQL traffic. Under several strategies, major compaction carries long-term operational side effects.
- Leaving `disableautocompaction` active accumulates SSTables; re-enabling it can unleash a huge backlog.
- Manually deleting SSTables/tombstones or slashing `gc_grace_seconds` to “free disk quickly” risks **data loss/zombie data** without fixing the I/O cause.

**Safe sequence:** isolate the bottleneck → throttle/smooth incoming load if needed → review hardware and strategy → adjust one knob → re-measure and roll back if metrics worsen.

### 11.5. Spot workload and data-model causes

A table with **very wide partitions**, frequent `UPDATE`s, short TTLs, or range `DELETE`s generates heavy tombstones, SSTables, and compaction load:

- Overly coarse partition keys (e.g., all events for one huge tenant in one partition) skew memory and reads.
- Millions of cells with synchronized TTL expirations create waves of tombstones/compaction.
- Bulk ingests create many medium SSTables without compaction headroom.
- Late/out-of-order writes into TWCS keep old time windows dirty and hard to reclaim.
- SAI/secondary indexes and materialized views add write and storage amplification.

When backlogs persist on **just a few tables**, the true fix may be redesigning **partition keys, query-driven tables, time buckets, TTL policy, or ingest pacing**—not adding threads.

## 12. CQL/`nodetool` lab: watching a memtable become an SSTable

**Goal:** Observe memtable metrics, flush counters, and SSTable counts before and after small writes—without inducing disk saturation or timeouts. This lab **does not need a large pending queue**; a healthy cluster flushes fast enough that pending may read 0.

**Environment:** Single-node Cassandra 4.1 or 5.0 **lab**, `cqlsh`, `nodetool`, and a JMX exporter/console if available. Run only where data changes are permitted; **never** run repeated `nodetool flush` in production just to test a dashboard.

### Step 1 — Create an isolated keyspace and table

~~~sql
CREATE KEYSPACE IF NOT EXISTS observability_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS observability_lab.events_by_tenant (
    tenant_id text,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((tenant_id), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
  AND compaction = {
      'class': 'SizeTieredCompactionStrategy'
  };
~~~

`SimpleStrategy` RF=1 is **only suitable for single-node demos**, never multi-DC production. For real workloads, use `NetworkTopologyStrategy` with per-DC RF and partition keys bounded against giant partitions.

### Step 2 — Capture baseline before writing

~~~bash
nodetool status
nodetool tablestats observability_lab.events_by_tenant
nodetool tpstats
nodetool compactionstats
~~~

If using a JMX console or exporter, record:

~~~text
Table.MemtableOnHeapSize
Table.AllMemtablesOnHeapSize
Table.MemtableSwitchCount
Table.PendingFlushes
Table.BytesFlushed
Table.LiveSSTableCount
Table.PendingCompactions
Compaction.PendingTasks
~~~

Values **must carry node and table labels** for later comparison. On Cassandra 5.0, never assume every metric exports under an identical Prometheus name; match your JMX exporter mapping.

### Step 3 — Insert a few mutations and read them back

~~~sql
CONSISTENCY ONE;

INSERT INTO observability_lab.events_by_tenant
  (tenant_id, event_time, event_id, payload)
VALUES ('team-a', '2026-11-21T01:00:00Z',
        11111111-1111-1111-1111-111111111111, 'create');

INSERT INTO observability_lab.events_by_tenant
  (tenant_id, event_time, event_id, payload)
VALUES ('team-a', '2026-11-21T01:01:00Z',
        22222222-2222-2222-2222-222222222222, 'update');

INSERT INTO observability_lab.events_by_tenant
  (tenant_id, event_time, event_id, payload)
VALUES ('team-b', '2026-11-21T01:02:00Z',
        33333333-3333-3333-3333-333333333333, 'create');

SELECT event_time, event_id, payload
FROM observability_lab.events_by_tenant
WHERE tenant_id = 'team-a';
~~~

**Expected observation:** `MemtableLiveDataSize` or `MemtableOnHeapSize` rises as data is written. Do not expect the byte increase to equal the raw payload string length due to keys, timestamps, and structure overhead.

### Step 4 — Manually flush **one** table in the lab

~~~bash
nodetool flush observability_lab events_by_tenant

nodetool tablestats observability_lab.events_by_tenant
nodetool tpstats
nodetool compactionstats
~~~

After the flush completes:

- `MemtableSwitchCount` increases relative to baseline.
- `BytesFlushed` increases as the new SSTable is written.
- Active memtable size drops or switches to a fresh memtable.
- `LiveSSTableCount` typically increments, subject to compaction and sample timing.
- `PendingFlushes`/pool pending may already return to **0 before you run the next command**.
- `PendingCompactions` may stay 0; STCS waits for threshold SSTable counts before scheduling.

**Important:** Never try to force huge queues by running concurrent flushes or flooding writes until disk fills up. The goal is understanding **causality and instrumentation**, not causing an outage.

### Step 5 — Emit a couple more small SSTables in the lab

~~~sql
INSERT INTO observability_lab.events_by_tenant
  (tenant_id, event_time, event_id, payload)
VALUES ('team-a', '2026-11-21T01:03:00Z',
        44444444-4444-4444-4444-444444444444, 'paid');

INSERT INTO observability_lab.events_by_tenant
  (tenant_id, event_time, event_id, payload)
VALUES ('team-b', '2026-11-21T01:04:00Z',
        55555555-5555-5555-5555-555555555555, 'processed');
~~~

~~~bash
nodetool flush observability_lab events_by_tenant
nodetool tablestats observability_lab.events_by_tenant
nodetool compactionstats
~~~

If the table meets compaction thresholds, an automatic compaction may run; otherwise `pending tasks: 0` is **not a lab error**. Never run major compaction just to make a chart move.

### Step 6 — Compare all three checkpoints

| Metric | Before writes | After flush #1 | After flush #2 | What to explain |
|---|---|---|---|---|
| `MemtableOnHeapSize` | Record | Likely drops low | Likely drops low | Active memtable |
| `AllMemtablesOnHeapSize` | Record | May drop post-flush | May fluctuate | Includes unreclaimed memtables |
| `MemtableSwitchCount` | Record | Likely increments | Increments again | Counter; compare delta |
| `BytesFlushed` | Record | Rises on real flush | Rises further | Rate/bytes, not pending |
| `PendingFlushes` | Record | Usually returns to 0 fast | Usually returns to 0 fast | Snapshot; easy to miss fast tasks |
| `LiveSSTableCount` | Record | Likely +1 | Likely +1 or lower if compacted | Do not assume monotonic |
| `PendingCompactions` | Record | May stay 0 | May stay 0 | Strategy/input-dependent |

The lab succeeds when you **observe sensible changes** in switches/flushes/SSTables and can explain why pending counts can remain 0. Exact numbers depend on timing, cluster state, and internal scheduling.

### Step 7 — Verify logical data without arbitrarily changing CL

~~~sql
CONSISTENCY ONE;

SELECT event_time, event_id, payload
FROM observability_lab.events_by_tenant
WHERE tenant_id = 'team-a';

SELECT event_time, event_id, payload
FROM observability_lab.events_by_tenant
WHERE tenant_id = 'team-b';
~~~

Proper flushes and compactions must **preserve CQL read results** for committed mutations. If you ever observe missing rows, timeouts, or errors, never jump to blaming compaction—check CL, node availability, logs, disk, schema, and timestamps.

## 13. Java Driver: observing from the application side

A Java application **cannot see inside memtables directly**. Cassandra Java Driver 4.x sends CQL to a coordinator; the application measures **request success/latency/timeouts**, while memtables/flushes/compactions are observed via JMX/`nodetool` on the **servers**.

### 13.1. Java example with prepared statements

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.util.UUID;

public final class LabEventWriter {
    private final CqlSession session;
    private final PreparedStatement insert;

    public LabEventWriter(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO observability_lab.events_by_tenant " +
            "(tenant_id, event_time, event_id, payload) VALUES (?, ?, ?, ?)");
    }

    public long insertAndMeasureNanos(
            String tenantId, String payload) {
        BoundStatement statement = insert.bind(
                tenantId, Instant.now(), UUID.randomUUID(), payload)
            .setConsistencyLevel(DefaultConsistencyLevel.ONE);

        long startedAt = System.nanoTime();
        session.execute(statement);
        return System.nanoTime() - startedAt;
    }
}
~~~

In a lab with RF=1, `CL ONE` requires one replica response. In production with RF≥3, choose CL matching your availability SLA and local DC—**never** copy `CL ONE` blindly from a lab snippet into business-critical code.

`insertAndMeasureNanos` measures **client-observed request duration** across connection, driver, coordinator, network, and replica handling; it **does not isolate flush or compaction time**. A single sample is never p99: collect many requests into histograms over time.

### 13.2. Capturing application and server metrics together

Hypothetical incident correlation table:

| UTC Time | Java write p99 | Java timeouts/min | Node pending flush | Node pending compaction | Disk await |
|---|---:|---:|---:|---:|---:|
| 10:00 | 12 ms | 0 | 0 | 2 | 1 ms |
| 10:05 | 20 ms | 0 | 3 | 12 | 3 ms |
| 10:10 | 180 ms | 18 | 11 | 24 | 24 ms |
| 10:15 | 40 ms | 1 | 2 | 17 | 5 ms |

These are **illustrative figures**, not real Cassandra recordings. Disk `await`, backlogs, and p99 correlate here, yet you still must identify which work drove I/O: compaction, flushes, snapshots, repair, backups, or other traffic.

Application-side investigation checklist:

1. Tag metrics with `cluster`, `dc`, `service`, `operation`, `consistency_level`, and `table`/workload (never log sensitive partition keys).
2. Track timeouts by type (read, write, unavailable), retry counts, and driver pool/reconnection state where exposed.
3. Align failure timestamps with **replica-owning nodes**, rather than assuming every request uses the same coordinator.
4. Check **idempotency** before retrying write timeouts: an ACK may be lost even though the write landed.
5. Never enable unlimited speculative execution/retries to “push through” a backlog—that **amplifies traffic** and worsens disk contention.

### 13.3. Measure p99 with a metrics library, not `println`

With the Java Driver, use built-in driver metrics and/or service telemetry (Micrometer, OpenTelemetry, etc.) per standardized configuration. For a CQL latency histogram:

- Time both successes and failures, tagged by request class.
- Use proper **histograms/timers** producing p50/p95/p99 over windows with adequate sample volume.
- Synchronize clocks (NTP) to align server and client events, while timing **request durations** with a monotonic clock such as `System.nanoTime()`.
- Monitor retries, request rate, in-flight count, connection pool usage, and client timeouts alongside server metrics.
- Base alert thresholds on **SLOs**; do not turn normal background compaction into user-facing pages.

**Data correctness:** reading back via CQL after a flush does not replace anti-entropy repair. If a lagging replica missed mutations, check hints, repair, and CL across the topology rather than trusting coordinator metrics alone.

## 14. Case studies: diagnosing common scenarios

### Case A — Flush queue grows while compaction stays quiet

**Signals (illustrative):**

~~~text
Node N1, table events_by_tenant
  PendingFlushes:             3 -> 9 -> 17
  AllMemtablesOnHeapSize:   500 -> 740 -> 900 MiB
  MemtablePool blocked:      0 -> 2 -> 5 (per exporter)
  PendingCompactions:        2 -> 3 -> 4
  Disk await:                2 -> 20 -> 35 ms
~~~

**Hypothesis:** Flushes are blocked on disk I/O, not necessarily starved of compaction workers. Inspect:

- `tpstats`: active/pending flush writers and `MemtablePostFlush`.
- Disk I/O on the exact data directory, commit log directory, and OS processes.
- Snapshots/backups, `nodetool netstats`, or any compaction reading/writing the same disk.
- Memory budgets and other tables (another table may occupy shared flush writers).

**Avoid:** raising `memtable_flush_writers` while the disk is already saturated; extra writers add contention. **Prioritize:** smoothing write bursts/backups/repairs in a controlled way, fixing the disk bottleneck, and verifying backlog recovery.

### Case B — Compaction backlog creeps up while flushes stay healthy

~~~text
Node N2, table orders_by_customer
  PendingFlushes:           0 -> 0 -> 0
  PendingCompactions:      10 -> 25 -> 42
  LiveSSTableCount:        58 -> 87 -> 126
  SSTablesPerRead:         rising
  p99 read latency:        rising
~~~

**Hypothesis:** Compaction work is arriving faster than it finishes—perhaps the compaction throughput cap is too low, SSTable sizes are awkward, or heavy updates/TTLs drive churn.

**Investigation:** Check `compactionstats` task types and progress, `getcompactionthroughput`, CPU/disk headroom, table compaction strategy, and bulk ingests. Only if disk has ample headroom and throughput sits flat at the cap should you consider raising the cap **incrementally**. If disk is already congested, raising the cap can hurt read latency further.

### Case C — Flush and compaction rise together, write timeouts appear

~~~text
N3:
  MemtablePool.BlockedOnAllocation: sustained non-zero
  Flush pool PendingTasks:       rising
  Compaction.PendingTasks:       rising
  CommitLog.WaitingOnSegmentAllocation: rising
  Data disk await:               elevated
  Client write timeouts:         rising
~~~

**Hypothesis:** Resource contention loop: compaction, flushes, and commit log compete for I/O, memtables cannot free space in time, and clients time out.

**Priority:** Protect availability and disk headroom, rate-limit ingestion per approved runbook, defer optional background jobs, and inspect disks/limits per node. Never run `nodetool flush` or major compaction to “clear the backlog” while disk is overloaded.

### Case D — Slow commit log while memtable pending stays low

~~~text
N4:
  PendingFlushes:                  0
  PendingCompactions:              1
  CommitLog.WaitingOnCommit:       rising
  CommitLog.PendingTasks:          rising
  Write p99:                       rising
~~~

**Hypothesis:** The `fsync`/commit log path is bottlenecked, not the flush queue. Inspect commit log sync mode, disk latency, volume placement, and segment state. **Do not tune compaction threads before proving compaction is contending for I/O.**

### Case E — Pending compactions stay non-zero while the service is healthy

~~~text
N5:
  PendingCompactions:      3 -> 5 -> 2 -> 4
  LiveSSTableCount:        stable per strategy
  Compaction throughput:   active
  Read/write p99:          within SLO
  Disk free/IO latency:    normal
~~~

This can simply be **normal background operation**, especially under steady writes with continuous compaction. Never fire a P1 page merely because a gauge is rarely 0. Use longer trends, backlog age, and service-impact signals.

### Case F — Only one node in a DC runs hot

One node exhibits far higher memtable/flush/compaction pressure than peers:

- Is a **hot partition or hot token range** routing excessive writes to that node?
- Are keyspace RF, rack/DC placement, and token distribution balanced?
- Did that node recently replace/bootstrap, run heavy repair/streaming, or hit degraded hardware?
- Does that node have mismatched table compaction config from local JMX overrides?
- Is one disk across multiple data directories failing or degraded?

**Never average across the cluster and ignore a hot node.** With RF=3, one bottlenecked replica may stay partially hidden by clients for a while, yet slash fault tolerance the moment a second node goes down.

## 15. Production dashboard and response checklist

### 15.1. Minimum panels

| Panel | Required labels | How to read it |
|---|---|---|
| Active/all memtable bytes | cluster/DC/node/keyspace/table | Separate live active writes from pending/index memtables |
| Memtable switch rate, bytes flushed/sec | node/table | SSTable creation pace via flushes; spot bursts |
| Pending flush + flush pool active/pending | node/table/pool | Fast producer vs. resource-starved writers |
| Memtable blocked allocation | node | Direct backpressure on memory allocation |
| Pending compaction by table and node | node/table | Pinpoint backlog-generating tables |
| Bytes compacted/sec, compaction task progress | node/compaction type | Processing capacity and long-running large tasks |
| SSTable count + SSTables per read | node/table | Read amplification and strategy behavior |
| CommitLog pending/wait timers | node | Separate `fsync`/segment bottlenecks |
| Disk I/O latency/throughput/free space | node/disk | Root hardware resource evidence |
| JVM GC/heap/off-heap | node | Separate memory pressure from flush bottlenecks |
| Java p95/p99 latency, timeouts, retries | service/DC/operation/CL | Direct SLO impact |

### 15.2. Checklist during an alert

- [ ] Located affected **node/DC/table** and confirmed metrics are scraping continuously.
- [ ] Checked `nodetool status`, topology, streaming, repairs/backups, and recent changes.
- [ ] Captured at least two evenly spaced checkpoints for pending flushes/compactions and rates.
- [ ] Inspected flush pools, post-flush, and `BlockedOnAllocation`, not just `PendingFlushes`.
- [ ] Inspected compaction type, progress, and SSTable counts per strategy, not just total pending.
- [ ] Correlated with disk latency, free disk, CPU/GC, commit log `fsync`, and request p99.
- [ ] Distinguished normal traffic bursts from **non-draining** backlogs.
- [ ] Preserved required CL per app guarantees; made no unapproved CL downgrades.
- [ ] Changed at most **one variable** at a time with before/after numbers and rollback plan.
- [ ] Avoided manually deleting SSTables/snapshots/tombstones or forcing flushes/major compactions to “clear” queues.
- [ ] Verified CQL CRUD and Java application health without regressions post-mitigation.
- [ ] Documented root cause, affected tables/nodes, and preventive actions.

### 15.3. Short incident report template

~~~text
INCIDENT: CASSANDRA-WRITE-LATENCY-EXAMPLE
Window UTC:    2026-11-21 10:00 .. 10:20
Cluster/DC:    test-east / dc1
Node/Table:    n3 / observability_lab.events_by_tenant

Symptoms:
  Flush pending 2 -> 18; compaction pending 10 -> 32.
  All-memtables memory rising; disk await 3 -> 28 ms.
  Write p99 15 -> 220 ms; client timeout spike.

Correlated events:
  Bulk ingest overlapped repair + compaction on same volume.

Hypothesis:
  I/O contention delayed flush, then blocked memtable allocation.

Action:
  Ingest rate limited under approved runbook; repair rescheduled.
  No forced flush/compaction, no change to gc_grace_seconds.

Verification:
  Flush pending returned to baseline; compaction queue decreasing.
  Disk await and write p99 recovered, no new timeouts.

Residual risk:
  Recheck backlog and disk headroom over next compaction cycle.
~~~

Numbers in this template are **fictional sample values**, not default thresholds or an actual incident report.

## 16. Self-assessment questions

**Question 1.** Why are small `MemtableOnHeapSize` and large `AllMemtablesOnHeapSize` not necessarily contradictory?  
**Hint:** Total includes memtables awaiting flush, secondary indexes, and other components; the active memtable may just have switched.

**Question 2.** Does `MemtableSwitchCount` rising over 10 minutes prove flushes are stalled?  
**Hint:** No; it is a switch counter. Look at pending tasks, active writers, drain time, and `BlockedOnAllocation`.

**Question 3.** `PendingFlushes` says “pending”, yet Apache lists its metric type as Counter. Should you plot `rate()`/`increase()` right away?  
**Hint:** Not automatically; verify semantics, version, and exporter behavior alongside `tpstats` and snapshots over time.

**Question 4.** Why can increasing `memtable_flush_writers` drive up `PendingCompactions`?  
**Hint:** It can produce smaller, more frequent SSTables, increasing compaction work.

**Question 5.** Does `Compaction.PendingTasks=100` mean 100 seconds remain until completion?  
**Hint:** No. It is a task-count estimate; task sizes/costs vary widely and ETAs cannot be derived from task counts.

**Question 6.** `PendingFlushes=0`, `PendingCompactions` climbs steadily, and `SSTablesPerRead` rises. What should you inspect?  
**Hint:** Compaction strategy, throughput cap, active tasks, and disk/CPU—do not jump to adding flush writers.

**Question 7.** Both flush and compaction queues rise alongside very high disk `await`. Should you immediately run `setcompactionthroughput 0`?  
**Hint:** No; `0` removes throttling and can saturate the disk even further.

**Question 8.** Why is `nodetool flush` not a fix for a flush backlog?  
**Hint:** It adds more flush work and emits more SSTables without making writers or disks faster.

**Question 9.** Why check `CommitLog.WaitingOnSegmentAllocation` when writes slow down?  
**Hint:** Commit log segment allocation can stall on disk or flush cleanup independently of compaction queues.

**Question 10.** Why can summing pending compactions across the entire cluster hide an incident?  
**Hint:** One node with a failing disk can be masked by peers with zero backlog; track per-node/per-table max and trends.

**Question 11.** On a healthy cluster, a lab with three `INSERT`s and one flush always reads `PendingFlushes=0`. Did the lab fail?  
**Hint:** No; short queues drain before sampling. Track switch counters, bytes flushed, and SSTables instead.

**Question 12.** Java Driver reports timeouts while server compaction pending is low. Can you declare Cassandra healthy?  
**Hint:** No; check commit log, request thread pools, GC, network, coordinators, and client retries.

**Question 13.** Why avoid judging compaction solely by average read/write latency?  
**Hint:** SLOs are sensitive to p95/p99, hot partitions/nodes, and tail latency; averages hide spikes.

**Question 14.** If raising compaction throughput shrinks pending tasks while read p99 spikes sharply, did the change succeed?  
**Hint:** No; evaluate both SLOs and hardware resources, and consider rolling back and re-throttling throughput.

**Question 15.** Why is knowing whether repair/streaming runs alongside compaction essential?  
**Hint:** They compete for disk, network, and CPU while generating extra background work that lengthens queues.

## 17. Summary and memory map

~~~text
                 CQL WRITE / JAVA DRIVER
                           |
                CommitLog + Memtable
                           |
                    Memtable switch
                           |
              +------------+------------+
              |                         |
       Flush queues/pools          New active memtable
              |
        Memtable flush writers
              |
          New SSTable
              |
       Compaction backlog
              |
       Compaction executor
              |
         Merged SSTable
              |
       Faster reads when read
       amplification drops appropriately

Observe together:
  - Active/all memtable bytes + BlockedOnAllocation
  - PendingFlushes + flush/post-flush thread pools
  - PendingCompactions + Compaction.PendingTasks
  - BytesFlushed/sec + BytesCompacted/sec + SSTable count
  - CommitLog fsync/segments + OS disk/CPU/GC
  - Java request p95/p99, errors, retries, CL

Read TRENDS and causal correlations;
never tune threads/caps merely because a gauge is non-zero.
~~~

**Core principle:** Memtables, flush queues, and pending compactions are **three consecutive stages of Cassandra's write path**, each with distinct resources, metrics, and drain speeds. Accurate observability correlates **node–table–time window**, respects counter vs. gauge semantics, and pairs Cassandra metrics with disk/CPU/GC and Java client latency. When backlogs persist, fix the **actual bottleneck** instead of piling more work onto queues via forced flushes or major compactions.

## References

- [Apache Cassandra 5.0 — Monitoring metrics](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html) — names and types of Table, ThreadPools, Compaction, CommitLog, JVM/ClientRequest metrics.
- [Apache Cassandra 5.0 — Storage Engine](https://cassandra.apache.org/doc/stable/cassandra/architecture/storage-engine.html) — commit log, memtable, SSTables, flushing, and the write path.
- [Apache Cassandra 5.0 — Compaction overview](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/overview.html) — compaction strategies, tombstones, throughput, operational tools.
- [Apache Cassandra 5.0 — cassandra.yaml](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html) — `memtable_flush_writers`, `memtable_cleanup_threshold`, memtable memory budgets, `concurrent_compactors`, `compaction_throughput`.
- [Apache Cassandra 5.0 — nodetool tpstats](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/tpstats.html) — thread-pool usage and options.
- [Apache Cassandra 5.0 — nodetool tablestats](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/tablestats.html) — table statistics and formatting flags.
- [Apache Cassandra 5.0 — nodetool compactionstats](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/compactionstats.html) — pending tasks, active compactions, and progress.
- [Apache Cassandra 5.0 — nodetool flush](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/flush.html) — syntax for flushing one or more tables.
- [Apache Cassandra 5.0 — getcompactionthroughput](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/getcompactionthroughput.html) and [setcompactionthroughput](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/setcompactionthroughput.html) — compaction throughput limit; `0` removes the cap.
- [Apache Cassandra 5.0 — Use nodetool for troubleshooting](https://cassandra.apache.org/doc/stable/cassandra/troubleshooting/use_nodetool.html) — interpreting compaction backlogs, thread pools, and dropped messages.
