# Reading, Rewriting Data, and Temporary Space Needs During Compaction in Apache Cassandra

## 1. Problem Statement: Compaction Is Not an “In-Place Compression” Operation

In Apache Cassandra, a distributed **wide-column** database, tables are modeled around queries and data is distributed to replicas based on the **partition key**. Each replica writes mutations to its commit log and memtable, then flushes the memtable into **immutable SSTables** on disk. A single partition can appear in multiple SSTables, carrying old versions, newer records, and tombstones from deletes or TTL expirations.

To prevent the read path from probing too many SSTables, Cassandra runs **compaction**: reading selected SSTables, reconciling versions, and **writing out new SSTables**. This is a replacement (*rewrite*) operation, never modifying old SSTables in place. Until compaction finishes, **inputs coexist simultaneously with outputs being written**, so disk must have room for both.

For example, a node stores 400 GiB of data; a compaction selects 100 GiB of old SSTables and is expected to write 85 GiB of new SSTables. You cannot conclude the node will only need 315 GiB after compaction and run it immediately when the disk is nearly full. **While outputs are being written, disk usage can temporarily climb by roughly 85 GiB**, not counting flushes, other compactions, streaming, snapshots, or incoming new writes.

This lesson belongs to the **SSTables and compaction** chapter of the **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA** module. The focus is on three operational questions: what must compaction **read**, what must it **rewrite**, and **how much temporary space is needed** before old SSTables can be reclaimed.

## 2. How Do Immutable SSTables Lead to Read–Merge–Write?

### 2.1. Why Not Modify Old Data Directly?

New mutations do not seek out old cell locations inside an SSTable to overwrite them. Instead, they go into the memtable and later form a new SSTable. When a row is updated three times and deleted once, a replica can hold multiple versions of the same key across multiple files.

Suppose a device-events table has partition key `device_id`:

| Time | Operation | Storage state that may appear |
|---|---|---|
| T0 | Insert `value=25` | SSTable A holds value 25 |
| T1 | Update `value=26` | SSTable B holds value 26 |
| T2 | Delete row | SSTable C holds tombstone |
| T3 | Insert another row in the same partition | SSTable D holds the new row |

The read path must inspect relevant sources and reconcile by **mutation timestamp**, tombstones, TTLs, and Cassandra rules. “Reading by the right partition key” reduces routing cost, but does not by itself eliminate multiple versions on disk.

### 2.2. Logical Steps of a Compaction Run

1. **Input selection:** the compaction strategy selects a matching group of SSTables; these may be similarly sized files, overlapping levels, or files in the same time window.
2. **Reading:** Cassandra opens read streams across the input SSTables, accessing metadata/indexes and required data segments. Compressed data must be decompressed as needed for processing.
3. **Merging:** the system iterates through sorted partitions/rows, reconciling versions of the same cell, TTLs, and tombstones. Not every tombstone or old version can be dropped immediately.
4. **Rewriting:** creates one or more output SSTables with corresponding data files, indexes, checksums, Bloom filters, and metadata; component details vary by SSTable format/version.
5. **Completion and replacement:** outputs become active only after the process completes validly. Input SSTables are removed from the active set and physically reclaimed only once nothing still references them.

~~~mermaid
flowchart TD
    A["SSTable A: old value"] --> D["Compaction reads and merges"]
    B["SSTable B: new value"] --> D
    C["SSTable C: tombstone / TTL"] --> D
    D --> E["Reconcile timestamps, versions, and deletion markers"]
    E --> F["Write new output SSTables"]
    F --> G["Complete and replace input SSTables"]
    G --> H["Reclaim old files when safe"]
    I["New mutations continue flushing during compaction"] --> J["Concurrent SSTables generated"]
~~~

**Practical meaning:** during the output-write stage, the disk may simultaneously hold **A + B + C + outputs**. Cluster write traffic does not necessarily pause, so newly flushed SSTables can raise disk usage even further.

### 2.3. Is the Output Guaranteed to Be Smaller Than the Input?

No. Outputs are often smaller when duplicate versions are collapsed or eligible deleted data is purged, yet **you must never treat space reduction as guaranteed**. When most data is still live, output size can approach the total input size. Size varies with compression ratio, format, metadata, and processing conditions.

Therefore, **do not budget disk space by guessing “compaction will save 30%”** without reliable historical metrics for that specific table and compaction type.

## 3. Why Does Compaction Consume Both Read I/O and Write I/O?

Compaction is a background storage-engine task, yet it competes for resources with application read/write traffic.

| Cost type | Source | What can be observed in production |
|---|---|---|
| **Read I/O** | Reading source SSTables to merge | Higher disk read bandwidth, higher query latency |
| **Write I/O** | Creating new SSTables and related components | Higher disk write bandwidth, reduced headroom |
| **CPU** | Decompression, merging, tombstone handling, recompression | Higher CPU, throttled compaction throughput |
| **Temporary disk space** | Retaining old SSTables while writing new ones | Free space dips before recovering |
| **Memory/handle resources** | Buffers, metadata, and iterators | Resource pressure rises when multiple tasks run concurrently |
| **Write amplification** | Live data may be rewritten across multiple compaction cycles | Total bytes written to disk exceed logical bytes written by apps |
| **Read amplification before compaction** | Queries must read multiple SSTables/versions/tombstones | Read latency and SSTables per read climb |

**Core trade-off:** compaction rewrites data in exchange for lower future read cost and reclamation of eligible versions/tombstones. Running compaction aggressively can improve read latency and reduce SSTable counts, yet competes for I/O with live read/write traffic. Running too slowly lets SSTables and backlogs accumulate.

### Illustrating Read and Write Amplification

An application writes 1 GiB of new logical data. That data flushes, and then may participate in multiple compactions over its lifecycle. Total SSTable bytes written to disk can substantially exceed 1 GiB; the multiplier depends on strategy, update patterns, replication, and storage settings.

Conversely, a query returning 10 rows may need to read multiple SSTables when a partition spans many files. **Reducing read amplification via compaction usually trades off higher write amplification.** Neither can be optimized completely in isolation.

## 4. What Is Temporary Space and When Does It Appear?

### 4.1. “Old Inputs” and “New Outputs” Coexist

Suppose a compaction selects 4 SSTables, 20 GiB each:

~~~text
Before compaction:
SSTable A 20 GiB
SSTable B 20 GiB
SSTable C 20 GiB
SSTable D 20 GiB
-----------------
Total input = 80 GiB

During compaction:
Old SSTables still held: 80 GiB
New output SSTable: grows up to ~72 GiB
------------------------------------------------
Space coexisting simultaneously: ~152 GiB

After completion and input reclamation:
Only output retained: ~72 GiB
~~~

The 72 GiB output is illustrative only. This is **not a default compaction reduction ratio**. If old files are pinned by snapshots, backups, or active readers, physical space reclamation may arrive later than expected.

### 4.2. Space Budgeting Formula

To evaluate a node during compaction, use an approximate model:

~~~text
Free space to reserve
≈ Total new outputs not yet freed
  + Growth from writes / flushes
  + Streaming, repair, or other background tasks
  + Safety margin
~~~

Here:

- **New outputs:** estimated SSTable space compaction creates **before old inputs are deleted**. If multiple jobs run concurrently, sum all coexisting outputs.
- **Growth from writes/flushes:** write traffic does not vanish while compaction runs.
- **Other tasks:** streaming, repair, rebuild, bootstrap, snapshots/backups, and temp files can increase disk demand. Distinguish truly new growth from space already counted in current usage.
- **Safety margin:** reserves room for estimation error, traffic spikes, and compactions running longer than expected.

This is a **planning model**, not an exact prediction algorithm and not a “you always need 2× data” rule. Input SSTables may be freed at different times, multiple tasks can be concurrency-capped by config, and not the entire data directory participates in one compaction.

**Measure free space per disk/data directory, not just total cluster capacity.** A single full node or a single full drive on a node can still fail tasks even while other nodes have plenty of free disk.

### 4.3. Peak Space Calculation Example

Suppose a node has a 1,000 GiB data volume with 760 GiB used. Current free space = 240 GiB.

| Component to reserve for | Estimate |
|---|---:|
| Compaction preparing to write new outputs | 145 GiB |
| Another concurrent compaction task | 20 GiB |
| New writes and flushes during execution | 30 GiB |
| Desired safety margin | 50 GiB |
| **Total needed to preserve safety margin** | **245 GiB** |
| **Currently free** | **240 GiB** |
| **Shortfall vs. budget** | **5 GiB** |

Looking solely at additional space before the safety margin, projected usage is `760 + 145 + 20 + 30 = 955 GiB`, leaving `45 GiB` free. That does not yet fill the drive, but drops below the chosen 50 GiB safety reserve. Never assume “240 GiB free is plenty” without accounting for concurrent activities.

In practice, refresh estimates from input sizes, output history, write rates, compaction speed, concurrency, and disk metrics. Numbers in the table are only for **practicing capacity-planning reasoning**, not recommended Cassandra operational thresholds.

## 5. Relationship to Each Compaction Strategy

The compaction strategy determines **which SSTables are selected and how often data must be rewritten**. Thus it simultaneously affects read amplification, write amplification, and temporary space.

| Strategy | Selection and rewrite pattern (overview) | Temporary space implications |
|---|---|---|
| **SizeTieredCompactionStrategy (STCS)** | Merges similarly sized SSTables into larger files | Compaction of a large SSTable tier can require substantial output space while holding inputs |
| **LeveledCompactionStrategy (LCS)** | Organizes SSTables into levels to bound key overlap; data may be rewritten repeatedly across levels | Frequent rewrites and overlapping SSTable compactions; monitor concurrent per-level output and I/O budget |
| **TimeWindowCompactionStrategy (TWCS)** | Groups SSTables by time windows; older uniform-TTL datasets can expire as groups | Active window still needs rewrites; fully expired windows can reclaim space without merging everything |

These are common strategies to compare. Supported strategies and execution details vary by **Cassandra version**. Do not infer headroom from a strategy's name; use metrics from the concrete workload.

### 5.1. STCS: Watch Out for Large-Tier Compactions

STCS commonly merges several similarly sized files. For example, four 50 GiB SSTables merge into an output of roughly 200 GiB if little data is dropped. That scenario can demand nearly 200 GiB of free space to write the output **before** the inputs are reclaimed.

That is why capacity planning based on average daily free space can miss peak demand right when a large SSTable tier becomes eligible to compact. STCS fits many write-oriented workloads, yet overlapping SSTables and large-merge headroom needs can significantly impact latency-sensitive read workloads.

### 5.2. LCS: Less Read Overlap in Exchange for More Rewrites

LCS bounds key-range overlap among SSTables within organized levels (notably distinct from level 0). It often lets point queries check fewer SSTables. To preserve level invariants, a slice of data may have to be **read and rewritten multiple times** as it is pushed through levels.

Overall **write amplification** and I/O cost can exceed STCS, even though each individual compaction handles a smaller set than a giant tiered merge. With LCS, evaluate concurrent jobs, output sizes, backlog, disk throughput, and ongoing flushes.

### 5.3. TWCS: Data Expiring by Window

TWCS generally fits time-series **written chronologically with rare historical edits and roughly uniform TTLs**. When an SSTable becomes *fully expired* and safety conditions are satisfied, Cassandra can reclaim the file without reading and rewriting every live row.

However, these situations erode its benefits:

- Writing late data with older timestamps or updating prior partitions.
- Mixing data with wildly varying TTLs, or mixing in non-TTL data.
- Data for the same partition spanning many windows with deletes/overwrites.
- Write/flush rates causing active-window compaction to lag behind incoming traffic.

TWCS is not free: the active window still requires compaction, writing new outputs, and I/O. Do not pick the strategy solely because a table has a timestamp column; inspect **actual write patterns** and retention.

## 6. Tombstones and Reclamation Conditions During Compaction

Tombstones are deletion markers ensuring stale replicas and old SSTables cannot resurrect deleted values. When compaction encounters a tombstone, it **does not drop it immediately by default**.

Why?

1. An SSTable **outside the input set** may still hold older data shadowed by this tombstone.
2. An unreachable replica may not yet have received the delete mutation; purging the deletion marker too early risks **zombie data** when that replica returns.
3. TTL-expired data is also subject to safe on-disk reclamation logic; expiration does not mean the file vanishes immediately.

`gc_grace_seconds` relates to the protection window against data resurrection, yet **exceeding grace age is not the sole condition in all cases**. Cassandra must also check overlapping data, deletion markers, and strategy/version safety conditions. **Repair** helps synchronize replicas; **compaction** processes SSTables on each replica. Both tasks are related, yet neither replaces the other.

Example:

~~~cql
-- Assume keyspace demo already exists.
CREATE TABLE demo.measurements_by_device (
    device_id uuid,
    measured_at timestamp,
    temperature double,
    PRIMARY KEY (device_id, measured_at)
) WITH default_time_to_live = 604800
  AND compaction = {
      'class': 'TimeWindowCompactionStrategy',
      'compaction_window_unit': 'DAYS',
      'compaction_window_size': '1'
  };
~~~

This example assumes time-series data retained for 7 days and written mostly in chronological order. It only illustrates syntax; choose `gc_grace_seconds`, repair schedules, and retention based on topology, replica outage windows, and real business needs.

**Do not lower `gc_grace_seconds` to 0 to free disk when running out of space.** Such a decision requires analyzing guarantees around repair, replication, and data resurrection risk.

## 7. Factors That Prevent Space from Being Freed as Expected

### 7.1. Snapshots and Backups Still Pin Old SSTables

Cassandra snapshots typically rely on hard links to SSTables at snapshot time. When compaction creates replacement SSTables, old files may no longer belong to the active table, yet **physical space remains held by snapshots** until snapshots are cleared per policy.

Similarly, backup/retention mechanisms may keep copies or hard links depending on setup. **Filesystem usage may not drop** in step with “bytes compacted” reported by tools.

### 7.2. Active Readers and Components Referencing Old Files

A query currently reading old SSTables or a storage component holding references to them can delay physical reclamation. Therefore, “compaction task finished” and “all free space recovered” do not necessarily occur at the exact same instant.

### 7.3. Concurrent Flushes, Streaming, Repair, and Bootstrap

Incoming traffic keeps creating memtables and SSTables. Streaming, bootstrap, rebuild, or repair can transfer/write additional data; budget space **per node and per data directory** for tasks expected to overlap. Never divide the cluster's total replication factor into a “shared free pool”: compaction is local, and each replica needs its own headroom.

### 7.4. Different Layers Report Different Sizes

- **Logical live data:** currently valid data the application cares about.
- **SSTable live bytes:** data in active SSTables, potentially including old versions/tombstones.
- **Total storage used:** active files, snapshots/backups, commit logs, and other on-disk components.
- **Filesystem free bytes:** space actually available to write in the relevant data directory.

These metrics **are not equivalent**. During a disk-full incident, start from filesystem free space and reconcile against SSTable stats and space-pinning sources.

## 8. How to Observe and Estimate on a Real Cluster

With operational permissions in an appropriate environment, start with the following commands. Exact syntax and output fields may vary by version.

~~~bash
# Active compaction tasks, progress, and pending tasks.
nodetool compactionstats

# Table statistics: SSTable count, storage space,
# read/write latency, and partition/tombstone info if supported by version.
nodetool tablestats demo.measurements_by_device

# Completed compaction history (version/config dependent).
nodetool compactionhistory

# Existing snapshots that may hold space from old SSTables.
nodetool listsnapshots

# Node health check; Load is for reference only.
nodetool status
~~~

`tablestats` keyspace/table argument syntax can differ across versions; if the command above is unsupported, check `nodetool help tablestats` for your running Cassandra version. To measure real free disk space, use OS tools on the corresponding **data filesystem**, such as `df -h` on Linux. Never infer free space solely from the `Load` column of `nodetool status`.

### Metrics to Correlate When Investigating

| Observation group | What to check | Explanation |
|---|---|---|
| Disk capacity | Free bytes, used %, per data directory | Determine whether room remains for new outputs |
| Compaction | Active tasks, estimated remaining bytes, pending | Know how many jobs can write outputs concurrently |
| SSTables | Count, size distribution, live/total bytes | Spot file proliferation, huge merge groups, or fragmentation |
| Workload | Write throughput, flush rate, read latency p95/p99 | Estimate growth during compaction and read impact |
| Infrastructure | Disk read/write throughput, latency, CPU | Check I/O bottlenecks and resource contention |
| File pinning | Snapshots, backup retention, long-running reads | Explain why deleting inputs didn't raise free bytes |
| Replication | Repair/streaming, slow/down replicas | Assess tombstone safety and concurrent activity |

Counting SSTables alone **is not enough**. Compacting four 100 GiB files can need far more temporary space than hundreds of multi-MiB files. Conversely, hundreds of small files can spike read amplification even if total size is modest.

### Checklist Before a Major Operational Change

1. **Verify affected nodes/drives and compaction strategy** of the target table.
2. **Estimate input and output sizes** from compaction history, similar tables, and version/tombstone distribution; document uncertainty.
3. **Account for concurrent tasks**, plus flush rates, streaming/repair if any, and a safety margin.
4. **Inspect snapshots/backups and real filesystem usage**, especially when old inputs cannot be freed immediately.
5. **Check remaining I/O headroom for compaction to finish**, since slow compaction means holding both inputs and outputs longer.
6. **Monitor free bytes during execution**, comparing growing output sizes against pending backlog; adjust per the cluster runbook.

## 9. How Do Java Applications and Write Streams Affect Compaction?

The Java driver does not directly control compaction, yet **how the application creates mutations and partitions** dictates future version counts and SSTable patterns.

For example, a telemetry system writing to an unbounded time partition:

~~~cql
CREATE TABLE demo.telemetry_unbounded (
    device_id uuid,
    event_time timestamp,
    value double,
    PRIMARY KEY (device_id, event_time)
);
~~~

As a device sends millions of events over months, the partition grows huge and spans many SSTables. Writing corrections for past timestamps also causes overlapping data in compaction. One query-window organization uses bucketing:

~~~cql
CREATE TABLE demo.telemetry_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    value double,
    PRIMARY KEY ((device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

Java client writing full partition and clustering keys via a prepared statement:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

// CqlSession session is initialized and managed across the application lifecycle.
PreparedStatement insert = session.prepare(
    "INSERT INTO demo.telemetry_by_device_day " +
    "(device_id, event_day, event_time, value) VALUES (?, ?, ?, ?)"
);

UUID deviceId = UUID.fromString("11111111-1111-1111-1111-111111111111");
Instant eventTime = Instant.parse("2026-11-21T10:00:00Z");
LocalDate bucket = LocalDate.of(2026, 11, 21);

session.execute(insert.bind(deviceId, bucket, eventTime, 26.5));
~~~

Bucketing bounds partition size and narrows query scope, yet **does not automatically make compaction cheap**. Balance bucket size against write rate, TTL, retention, and cross-day queries.

Application-side habits that curb unnecessary background I/O:

- Avoid **repeatedly updating the same row** when business logic can append immutable events; each update creates a new version requiring reconciliation.
- Avoid **continuous bulk DELETEs** when a bucket/TTL retention model fits better; TTLs also generate expiration markers, so measure carefully.
- Avoid abusing **large batches** across multiple partitions: batches do not make compaction free and can create write pressure.
- Apply **bounded concurrency/backpressure** to backfills, imports, and data recovery so flush/compaction waves do not exceed disk capacity.
- Track **p95/p99 read/write latency**, request timeouts, and ingest rates when tuning compaction strategies.

These decisions tie directly into Cassandra's wide-column structure, partition keys, and query-driven table design. They also show why managing compaction requires coordinating **data model, CQL, Java ingestion, and replica operations**.

## 10. Real-World Scenario: Compaction Nearly Fills a Node

Suppose a time-series table uses STCS and a node reports:

- Data drive nearly full; free space dropped from 150 GiB to 65 GiB.
- `nodetool compactionstats` shows compaction writing a huge new SSTable.
- Input SSTables have not disappeared yet; meanwhile, a backfill job keeps writing data.
- Read p99 latency spikes from I/O contention.

Analysis workflow:

**Step 1: Determine actual free disk space.** Read filesystem free bytes per data directory and watch the burn rate. Do not rely solely on live SSTable size or guess that finishing compaction will instantly free enough space.

**Step 2: Break down disk growth.** Identify which compaction task is writing outputs, how much data remains to be written, any concurrent tasks, and write/flush rate from the backfill. Check snapshots/backups pinning replaced SSTables.

**Step 3: Protect availability.** Per your runbook, throttle or pause proactive backfill/import streams if allowed, and consider tuning compaction throughput/concurrency based on cluster state. Understand the trade-off: **slowing compaction prolongs how long both inputs and outputs must be kept**.

**Step 4: Long-term fix aligned with workload.** If large STCS tiers routinely need temporary space exceeding headroom, review strategy, data model, retention, capacity, and load balance; evaluate LCS/TWCS against real traits rather than switching blindly mid-incident. Adding capacity or shifting load may be necessary.

**Step 5: Verify recovery.** Monitor free bytes, pending compactions, SSTable count, I/O latency, read/write p99, and write rate. Declare stability only once backlog stops growing and safety headroom remains for the next compaction wave.

**Avoid hasty actions:** never delete SSTable files directly from the data directory, never lower `gc_grace_seconds` manually to delete tombstones, and never force full compaction without checking headroom. Such actions risk data loss or worsening disk exhaustion.

## 11. Distinguishing Compaction, Repair, and Cleanup

These three operations are easily lumped together as “data cleanup”, yet differ in goals and costs:

| Operation | Primary purpose | Storage impact |
|---|---|---|
| **Compaction** | Merges SSTables on a replica, reduces duplicate versions, organizes files, reclaims eligible data | Reads inputs and writes new SSTables; requires temporary space |
| **Repair** | Synchronizes data discrepancies across replicas, preventing missed mutations/deletes | Can generate I/O, streaming, and version-dependent SSTables/compaction |
| **Cleanup** | Removes data a node is no longer responsible for by token range after topology changes | Also involves reading/writing data and space needs; must follow proper procedure |

Compaction **does not verify that all replicas are in sync**. Repair **does not guarantee old SSTables are reclaimed immediately**. Cleanup **is not a general fix for tables heavy with tombstones**. Plan disk capacity for these tasks separately and evaluate whether running them concurrently will contend for I/O.

## 12. Applied Exercises

### Exercise 1 — Peak Disk Calculation

A node uses 600 GiB out of 800 GiB total. Compaction selects 120 GiB of old SSTables with an estimated 100 GiB output. Another 35 GiB of writes/flushes are expected, and a 60 GiB safety margin must be kept. No other compaction jobs are active. Is free space sufficient to preserve the safety margin?

**Answer:** Current free space is 200 GiB. Budgeted demand is `100 + 35 + 60 = 195 GiB`, leaving roughly 5 GiB over the desired reserve. **On paper in this example it barely fits**, yet the error margin is razor-thin; never base a safe operational decision on a single output estimate alone.

### Exercise 2 — Misconception About Post-Compaction Space

After compaction, live SSTable bytes drop by 80 GiB, yet `df` increases by only 10 GiB. Name at least two hypotheses.

**Answer:** Snapshots/backups retain hard links to old SSTables; active readers or storage components have not released file handles; concurrent new mutations/flushes or other tasks consumed space simultaneously; “live SSTable” metrics differ in scope from the filesystem view.

### Exercise 3 — Strategy Trade-Offs

Workload A has p99-sensitive point reads and frequent updates on the same keys. Workload B is append-only time-series with nearly uniform TTLs. Which strategy should be tested first for each?

**Answer:** For A, **LCS** is typically worth evaluating because it limits SSTable overlap on reads, though write amplification and I/O must be measured. For B, **TWCS** typically fits time-window and expiration traits assuming minimal late writes/historical edits. Never choose without benchmarking.

### Exercise 4 — Tombstones and Repair

A team wants to set `gc_grace_seconds=0` because compaction didn't drop tombstones immediately, while a replica occasionally goes offline for several days. What is the risk?

**Answer:** Tombstones may be purged before the down replica receives the delete, causing deleted data to **reappear** when the replica syncs. Design repair schedules and replica outage policies before altering grace.

### Exercise 5 — Why Not Run Full Compaction Recklessly?

A node is running low on disk; an admin suggests `nodetool compact` hoping old files will be deleted and free space. What must be evaluated first?

**Answer:** Full compaction can write a huge output while inputs still exist, sharply spiking temporary space demand. Check input sizes, estimated output, concurrent tasks, snapshots, and I/O; never treat full compaction as an instant disk-full cure.

## 13. Key Takeaways

Compaction is the pipeline **read input SSTables → merge and reconcile → write output SSTables → replace/reclaim inputs when safe**. This pipeline explains three vital realities:

1. **Data can be rewritten multiple times**: write amplification is the cost paid to improve the read path and storage layout.
2. **Temporary space is a prerequisite for compaction to finish**: while writing outputs, input SSTables still occupy disk; write traffic, streaming, repair, and snapshots push peak disk higher.
3. **No single headroom ratio fits every table**: STCS, LCS, TWCS, compaction concurrency, TTLs, tombstones, overlapping data, and partition structure dictate actual needs.

When planning Apache Cassandra operations, calculate capacity **per node and per data directory**, estimate maximum coexisting outputs, monitor backlog/I/O, keep a safety margin, and verify file reclamation. A compaction that “shrinks space at the end” can still **fill the disk before finishing** if the rewrite phase is not budgeted.
