# Disk Capacity, Commit Log, SSTables, Hints, and Snapshots

## 1. When a Cassandra disk is nearly full, what is actually filling it?

In **Apache Cassandra**, a node does not only store the live rows returned by `SELECT`. Disk space is also consumed by the **commit log**, immutable **SSTables**, **hints** queued for peer replicas, **snapshots/backups**, temporary compaction files, and other system data. Looking at a single `disk used` number is therefore never enough to decide what to fix.

For example, two nodes both reporting **90% disk usage** can have completely different root causes:

- Active SSTables holding valid data are growing with real write throughput.
- Compaction is stalled, leaving many older row versions, tombstones, and unmerged SSTables.
- Commit log segments cannot be reclaimed because memtables are not flushing fast enough.
- A disconnected replica is causing hints to pile up on other nodes.
- Snapshots from past maintenance runs are still pinning old SSTable files.
- Streaming or compaction is writing new output files before old input files can be released.

Each scenario demands **different metrics, evidence, and actions**. Manually deleting files inside data, commit log, or hints directories risks data loss or replica divergence and is never a safe fix.

This lesson belongs to the **Cluster Observability** chapter for Apache Cassandra: it covers the role of each file type, what metrics to monitor, how to diagnose abnormal disk growth, `nodetool`/CQL inspection commands, and how a Java application adds read/write telemetry.

**Learning objectives:** distinguish filesystem-level capacity from Cassandra-level metrics, inspect commit log/SSTable/hints/snapshot consumption, estimate compaction headroom, choose meaningful alerts, and execute a non-destructive triage workflow.

**Scope:** standard full replicas, illustrated on Cassandra using `NetworkTopologyStrategy`. Exact JMX metric names, directory layouts, commit log/compaction defaults, and `nodetool` syntax vary across versions; verify against your running environment.

## 2. Write-path map and where disk space goes

~~~mermaid
flowchart TD
    A["Java client sends INSERT/UPDATE/DELETE"] --> C["Coordinator routes to replicas"]
    C --> R["Replica receives mutation"]
    R --> L["Commit log: sequential append for recovery"]
    R --> M["Memtable: in-memory data"]
    M --> F["Flush creates immutable SSTable"]
    F --> S["Active SSTables"]
    S --> K["Compaction produces merged SSTable"]
    K --> S
    S --> P["Snapshot: references/hard links to SSTables"]
    C --> H["Hint stored temporarily if target replica is absent"]
    H --> D["Deliver hint when replica returns"]
    L --> G["Segment recycled/deleted once no replayable data remains"]
~~~

This diagram is a **logical model**; it does not depict exact threading or `fsync` ordering. What matters is that the **write path** and **maintenance path** create distinct storage consumers.

| Component | Purpose | When does space shrink? | Risk of manual deletion |
| --- | --- | --- | --- |
| **Commit log** | Records mutations to recover memtables after a crash. | When a segment holds no un-flushed data needing replay; Cassandra manages reclamation. | Loss of recovery for unflushed writes. |
| **SSTables** | Durable sorted/indexed data, potentially including versions and tombstones. | Compaction, cleanup after topology shifts, or proper lifecycle operations. | Partition/row loss; replica divergence. |
| **Hints** | Stores missed mutations bound for an unreachable target replica. | When delivered or expired per hint policy and management settings. | Target replica may miss mutations permanently; requires repair. |
| **Snapshots** | Preserves an SSTable set at a point in time for backup/restore. | When cleared per retention policy and final references vanish. | Loss of restore points. |
| **Compaction/streaming output** | Files being written/received before replacing inputs or completing bootstrap. | When the task completes and unreferenced files are released. | Task corruption or lost replicas. |

**Do not assume:** data **past its TTL** makes an SSTable disappear the instant TTL expires; physical purging depends on tombstones, `gc_grace_seconds`, compaction, and whether older timestamps are shadowed. Likewise, streaming data to a new node does not immediately clean up leftover ranges on old nodes.

## 3. Two capacity views: filesystem vs. Cassandra

### 3.1. The filesystem answers “how many usable bytes remain?”

On a lab node running Linux:

~~~bash
# Inspect Cassandra node filesystems/mount points.
df -h

# Illustrates checking configured directories.
# Replace example paths with VERIFIED actual paths.
du -sh /var/lib/cassandra/data
du -sh /var/lib/cassandra/commitlog
du -sh /var/lib/cassandra/hints
~~~

`df` reports **filesystem** capacity and free space; `du` sums file/directory sizes as walked by the tool. The paths above are **common examples**, not mandatory defaults: `data_file_directories`, `commitlog_directory`, `hints_directory`, and mount points may live on separate volumes or share one volume.

**Why does summing `du` not always equal `df`?**

- SSTables and snapshots often share inodes via **hard links**: adding directories separately **double-counts** allocated bytes.
- Open-but-unlinked files continue occupying disk blocks until the process closes their descriptors; `du` misses them while `df` counts them.
- Filesystems also reserve blocks, hold metadata/fragmentation, and store application logs and other files.
- Inside containers, mounted volume size may differ from container filesystem quotas.
- On multi-volume nodes, total node disk does not tell how full the **hottest single volume** is.

**Trust `df` per exact volume first to gauge disk-full risk**, then use component breakdowns to explain why. Never blindly add `du(snapshot)` to `du(active SSTables)` and treat that sum as guaranteed reclaimable physical bytes.

### 3.2. Cassandra answers “how big are live data and background tasks?”

`nodetool tablestats` and Cassandra metrics typically report:

- **Live disk space used:** size of active SSTables counted per metric definition.
- **Total disk space used:** total SSTable space counted by the tool, which may differ in scope from live space; **not** equivalent to `df` for the whole filesystem.
- **SSTable count:** number of SSTables for the table (files/structures, not partition count).
- **Droppable tombstone ratio, estimated tombstones, partition-size statistics:** clues about compaction debt and data modeling.
- **Pending/active compaction, flush, streaming:** background work that pins old files and requires headroom.

Verify exact field names, units, and calculation semantics against your **Cassandra version and monitoring exporter**. A `Table.LiveDiskSpaceUsed` metric does not inherently include commit logs, hints, snapshots, or application logs.

### 3.3. Four kinds of “capacity” to keep distinct

| Investigation term | Question | Typical source |
| --- | --- | --- |
| **Physical used/free** | Does the volume have enough blocks for writes/flushes/compactions? | `df`, node/disk exporter, filesystem metrics. |
| **Active SSTable footprint** | How much space is actively serving reads/writes? | `nodetool tablestats`, JMX `Table` metrics. |
| **Potentially reclaimable** | Which snapshots passed retention, which SSTables await compaction, which hints were delivered? | Snapshot inventory, compaction/hints state, runbooks. |
| **Temporary headroom** | Is there enough space to hold compaction/streaming inputs and outputs simultaneously? | `df`, compaction backlog, operational plan. |

Crucially, **potentially reclaimable does not mean immediately deletable**. Compaction must preserve still-needed tombstones; snapshots are governed by retention; hints may be the sole copy of writes missed by a peer replica.

## 4. Commit log: unflushed data and segment reclamation

### 4.1. Why does the commit log exist?

On a replica, a mutation is typically written to the **commit log** and applied to the **memtable**. If the node crashes before the memtable flushes to SSTables, Cassandra **replays** relevant commit log segments on startup to recover those mutations.

The commit log consists of sequentially written **segments**. One segment can contain mutations across **multiple tables**; flushing one table does not let Cassandra discard the segment if another table still has un-flushed mutations in that segment.

~~~mermaid
flowchart LR
    W["Mutation from client"] --> L["Commit log segment"]
    W --> M["Memtable"]
    M --> F["Flush → SSTable"]
    L --> X{"Is all relevant data in segment safely in SSTables?"}
    X -->|No| K["Segment still needed for recovery"]
    X -->|Yes| D["Cassandra can reclaim/recycle segment"]
~~~

**The commit log is not a query history log** and does not replace backups. Once a segment is no longer needed for recovery, Cassandra reclaims it; never expect the commit log to retain every historical mutation indefinitely.

### 4.2. `commitlog_sync` vs. commit log disk size

Commit log sync modes (such as `periodic` or `batch` in supported versions) govern how write acknowledgements interact with `fsync` and crash-loss windows. That is a **write-durability** setting, not an SSTable cleanup mechanism.

A `LOCAL_QUORUM` request controls **replica ACKs**, not per-replica `fsync` durability policy. Nor does RF = 3 prevent an individual node's commit log from filling up.

### 4.3. When does the commit log grow?

| Observation | Likely cause | What to inspect |
| --- | --- | --- |
| Commit log grows with write rate then plateaus | Data waiting to flush; segments cycling normally | Monitor trend, write rate, and configured limits. |
| Commit log keeps growing with large flush backlog | Memtable flushes stalled by I/O or system pressure | Check pending flushes, disk latency, logs, compaction. |
| High commit log usage even though one table sees few writes | Segments still hold unflushed mutations from another table | Inspect the **whole node**, not a single table. |
| Flush/segment allocation errors or disk nearly full | Out of blocks or stalled storage; write path at risk | Protect data safety, inspect volume, never delete segments manually. |
| Commit log replay runs on startup | Recovering mutations not yet flushed to SSTables before shutdown/crash | Check startup logs, corruption warnings, and disk health. |

In a lab, `nodetool flush <keyspace> <table>` helps observe memtables flushing to SSTables; **never** run forced flushes indiscriminately in production just to “shrink” the commit log. Flushing creates new SSTables, adds I/O, and can increase compaction work.

**Configured commit log size limits** (such as total commit log space caps per version) trigger Cassandra to flush memtables to reclaim segments. They do not make the commit log a queue you can safely clear with OS commands.

## 5. SSTables: live data, compaction debt, and tombstones

### 5.1. Why do SSTables grow even when logical row count stays flat?

SSTables are **immutable**. An `UPDATE` normally writes a new version; a `DELETE` writes a tombstone; expired TTLs become logical deletions. Old versions and tombstones can span **multiple SSTables** for the same partition. On read, Cassandra reconciles timestamps and deletion markers.

Compaction reduces file count and overlap by merging SSTables and dropping **eligible** expired/shadowed content. However, it often must **write the new output SSTables before deleting input files**. That creates temporary disk growth; a node at 90% disk usage may **lack enough headroom for compaction to clean up the disk itself**.

~~~text
Before compaction:   SSTable A + SSTable B + SSTable C       (on disk)
During compaction:   A + B + C + new SSTable being written   (peak usage)
After completion:    new SSTable active; inputs dropped when safe
Snapshots/backups:   may still reference A/B/C even when no longer active
~~~

### 5.2. Compaction strategy shapes disk usage patterns

| Strategy | Behavior to watch | What NOT to assume |
| --- | --- | --- |
| **SizeTieredCompactionStrategy (STCS)** | Groups similarly sized SSTables; update-heavy workloads can accumulate large SSTables needing high headroom. | Low SSTable count automatically means few tombstones. |
| **LeveledCompactionStrategy (LCS)** | Organizes SSTables into levels to limit read overlap; incurs write amplification. | LCS always uses less write I/O than every other strategy. |
| **TimeWindowCompactionStrategy (TWCS)** | Groups data by time windows, suited to time-series with uniform TTLs. | Passing one window guarantees files vanish right on schedule. |

When diagnosing a filling node, inspect **SSTable counts, compaction backlog, file sizes, TTL/tombstones, partition sizes, and write rate** together. Forcing a major compaction on a nearly full disk can make things worse because output requires scratch space.

### 5.3. Tombstones affect both disk space and read latency

A table with `default_time_to_live = 2592000` (30 days) does not guarantee only 30 days of physical bytes sit on disk. After TTL expiry, purging tombstones still depends on `gc_grace_seconds`, overlap with older data in other SSTables, and compaction scheduling.

**Tombstone scans** can also force a `LIMIT 10` query to walk past vast numbers of markers before finding 10 live rows. When disk growth coincides with rising read latency and tombstone warnings, review **partition/bucketing design, TTLs, compaction, and repair schedules** instead of merely bumping alert thresholds.

## 6. Hints: queued writes for peer replicas, not formal replicas

### 6.1. Why do hints exist?

Suppose RF = 3 in `dc1`; a `LOCAL_QUORUM` write is acknowledged by N1 and N2 while N3 is temporarily unreachable. Cassandra can store a **hint** on an eligible node to replay missed mutations to N3 once N3 recovers.

~~~mermaid
sequenceDiagram
    participant App as Application
    participant C as Coordinator
    participant N1 as Replica N1
    participant N2 as Replica N2
    participant N3 as Replica N3 (offline)
    App->>C: INSERT LOCAL_QUORUM
    C->>N1: Mutation
    C->>N2: Mutation
    C-xN3: Unreachable
    N1-->>C: ACK
    N2-->>C: ACK
    C-->>App: Write success
    Note over C: May store hint for N3
    Note over N3: Must receive missed mutations on return
    C->>N3: Replay hint if still valid
~~~

Conceptual diagram only. Hinting depends on config, node health, version, time/space caps, and replay rules. Not every write missing a replica is guaranteed to keep a hint indefinitely.

### 6.2. How to read hints metrics

| Signal | Interpretation | Operational question |
| --- | --- | --- |
| Hints directory size growing | Mutations waiting for replay or not yet purged | Which target replica is slow or down? |
| Hints backlog stays flat even after target node returns | Handoff failing, throttled, or unable to keep up | Are network/streaming, auth, disk, and logs healthy? |
| Hint creation rate exceeds delivery rate | Prolonged replica outage or excessive write rate | Must the node/link be fixed before backlog overflows? |
| Hints expired or undeliverable | Handoff can no longer bring replica up to date | Evaluate anti-entropy repair, especially for tombstones. |

`nodetool netstats` and version-specific hints metrics/logs help observe handoff/streaming. Some Cassandra versions provide commands to list pending hints; **verify with `nodetool help` before using**, never assuming every version shares exact command names or metric fields.

### 6.3. Never treat hints as a replacement for repair

Hints are a **best-effort, time-bounded** mechanism for missed mutations. If a replica stays down too long or hints hit caps/expiry, **anti-entropy repair** is still required to synchronize data. This is critical for `DELETE`s and TTLs: a replica that missed a tombstone can retain stale data and cause **zombie data** if tombstones are purged prematurely elsewhere.

**Never delete the hints directory directly when a disk fills up.** Doing so destroys queued mutations meant for peer replicas. If emergency intervention is required, follow an incident runbook assessing target replicas, durability, and subsequent repair.

## 7. Snapshots: why did compaction finish yet disk usage stay flat?

### 7.1. What is a Cassandra snapshot?

A table snapshot typically retains **references/hard links** to the SSTable files present at snapshot time, along with metadata for restore. Because hard links can point to the same inodes:

1. Creating a snapshot **does not immediately double SSTable disk bytes**.
2. Later, when compaction builds new SSTables and unlinks old inputs, those old files **remain allocated on disk** while referenced by the snapshot.
3. Total filesystem usage can creep upward over multiple compaction and snapshot cycles even when the logical table holds a constant dataset.

~~~mermaid
flowchart TD
    A["Active SSTable X"] --> H["Create snapshot S: hard link to X"]
    A --> C["Compaction creates SSTable Y"]
    C --> N["Y becomes new active SSTable"]
    H --> O["X still consumes disk via snapshot reference"]
    O --> R["Clear snapshot per retention"]
    R --> F["X frees blocks once no references remain"]
~~~

A snapshot does not let the application `SELECT` historical data directly through the live table. Restoring requires an explicit **restore procedure** matching file layout, schema, version, and backup plan.

### 7.2. Inspecting snapshots

~~~bash
# List existing snapshots on a node.
nodetool listsnapshots

# Use only in a lab or per an approved backup runbook.
nodetool snapshot -t obs-lab-01 telemetry_obs
~~~

`nodetool listsnapshots` typically shows snapshot tags, keyspaces/tables, and size figures. However, **reported snapshot size does not necessarily equal bytes freed upon deleting one snapshot**, because files may be shared across active SSTables and other snapshots.

Before clearing snapshots, confirm **retention rules, off-node backup schedules, and recovery needs**. Use `nodetool clearsnapshot` with exact flags per `nodetool help clearsnapshot` for your version; never run `rm -rf` on snapshot directories in production.

### 7.3. Snapshots are not completed off-node backups

- A snapshot sitting on the **same node/volume** does not survive total disk failure or host loss.
- Reliable backups require shipping data to independent off-node storage, verifying integrity, preserving schema/config, and testing restores.
- Cluster-wide snapshots **are not automatically an atomic cross-partition/cross-DC transaction snapshot**; application-consistent backup workflows must be designed explicitly.
- Once a snapshot is safely backed up off-cluster and retention allows, clearing local snapshots can reclaim space—but **never clear before verifying the off-node backup is valid**.

## 8. Minimal diagnostic command set

In lab/staging, on a properly authorized node:

~~~bash
# Membership, ring, and node state:
nodetool status
nodetool info

# Active table, SSTable, and tombstone state:
nodetool tablestats telemetry_obs.readings_by_sensor_day

# Compaction backlog / background tasks:
nodetool compactionstats
nodetool tpstats

# Streaming/handoff and snapshots:
nodetool netstats
nodetool listsnapshots

# Verify exact syntax for your version:
nodetool help tablestats
nodetool help snapshot
~~~

| Tool | Best answers | Does NOT answer on its own |
| --- | --- | --- |
| `df -h` | How much free space remains on each volume? | Which Cassandra component owns the used space. |
| `du` by directory | Which directory trees are large? | Exact reclaimable bytes when hard links exist. |
| `nodetool status` | Which nodes/DCs/racks are up/down/joining? | Whether all replicas hold synchronized data. |
| `nodetool tablestats` | SSTables, size estimates, and table state? | Total bytes of commit logs, hints, snapshots, and whole filesystem. |
| `nodetool compactionstats` | Whether compactions are active or pending? | Exactly how many bytes will be reclaimed. |
| `nodetool netstats` | Streaming/handoff state per Cassandra version? | Whether all missed mutations have been fully repaired. |
| `nodetool listsnapshots` | Which snapshot tags/tables are retained? | Whether every snapshot is backed up off-cluster. |

**Inspect per node first, then aggregate by cluster.** A token range has multiple replicas, yet each node owns its own disk, commit log, hints, and snapshots. Plenty of total cluster free space cannot save one node whose data volume is full.

## 9. CQL lab: distinguishing logical data from file footprint

### 9.1. Create a lab table

Assume DC `dc1` and RF = 3. If your lab has fewer than three nodes, adjust topology/RF/CL validly before running:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_obs
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry_obs.readings_by_sensor_day (
    sensor_id text,
    event_day date,
    event_time timestamp,
    event_id uuid,
    reading decimal,
    PRIMARY KEY ((sensor_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
  AND default_time_to_live = 2592000
  AND gc_grace_seconds = 864000;
~~~

Here `(sensor_id, event_day)` is a **composite partition key**, and `event_time` and `event_id` are clustering columns. Daily bucketing fits per-sensor/per-day reads while preventing unbounded partition growth. RF = 3 means **three target replica copies**, not three SSTables of the same data on one node.

### 9.2. Writing and inspecting TTL

~~~sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO telemetry_obs.readings_by_sensor_day
  (sensor_id, event_day, event_time, event_id, reading)
VALUES
  ('sensor-9', '2026-11-21', '2026-11-21T08:30:00Z',
   123e4567-e89b-42d3-a456-426614174001, 21.70);

SELECT event_time, reading,
       TTL(reading) AS ttl_remaining_seconds,
       WRITETIME(reading) AS write_time_us
FROM telemetry_obs.readings_by_sensor_day
WHERE sensor_id = 'sensor-9'
  AND event_day = '2026-11-21';
~~~

Assuming no competing writes, `TTL(reading)` returns **remaining seconds for the cell** and `WRITETIME(reading)` returns its write timestamp in microseconds. Neither tells you when an SSTable or commit log segment on disk will be removed.

### 9.3. Running a controlled observation sequence

In a **dedicated lab**, you can run these steps:

1. Write rows across the same and different partitions; record `df`, `tablestats`, commit log, and compaction metrics.
2. Run `nodetool flush telemetry_obs readings_by_sensor_day` **in the lab only**, then compare memtable/SSTable counts, commit log size, and actual disk usage.
3. Run `nodetool snapshot -t obs-lab-01 telemetry_obs`, then check `listsnapshots`.
4. Continue writing, updating, or deleting rows, then observe SSTables and tombstones after system-driven flushes/compactions.
5. Verify that the snapshot retains older files even after logical data changes; do **not** expect snapshot creation to immediately double every file.
6. Clear the lab snapshot only after confirming no restore is needed and using the version-appropriate command; observe how much `df` changes.

During these tests, **never induce replica failures or delete commit logs/hints** just to make metrics look “prettier”. If you need to simulate hints from a down node, use an isolated lab cluster with recovery and repair steps prepared.

## 10. From Cassandra metrics to a practical dashboard

### 10.1. Metric groups to view side by side

| Dashboard group | Example metrics/signals | Why place them together |
| --- | --- | --- |
| **Capacity** | Used/free disk per volume, growth rate in GB/day, time-to-full forecast | Assess whether flushes and compactions can keep running. |
| **SSTables & reads** | Live/total disk, SSTable count, partition-size distribution, tombstone scans | Identify version/tombstone/large-partition drivers. |
| **Writes & commit log** | Write latency/timeouts, commit log size/pending tasks, memtable flush backlog | Catch un-reclaimed segments from write/flush bottlenecks. |
| **Compaction** | Pending tasks, active compactions, bytes read/written, throughput | Assess compaction debt and temporary headroom. |
| **Hints & replicas** | Hints generated/delivered/pending, hints disk usage, nodes down, handoff failures | Separate replica outages from normal data growth. |
| **Snapshots/backups** | Snapshot tag count, snapshot age, retention, backup success/restore tests | Explain pinned old files and safe cleanup eligibility. |
| **Node resources** | CPU, heap/GC, disk latency/IOPS, filesystem errors, network bandwidth | Pinpoint hardware bottlenecks behind flush, compaction, repair, or handoff. |

Common JMX metrics in Cassandra include families under **`Table`**, **`CommitLog`**, **`Compaction`**, **`ThreadPools`**, and hints-related MBeans. Names such as `LiveDiskSpaceUsed`, `TotalDiskSpaceUsed`, `PendingTasks`, and `TotalCommitLogSize` appear in many versions, yet **exact MBean schemas, exporter labels, and units must be verified on real nodes**.

Conceptual dashboard labeling design:

~~~text
cluster      = cassandra-main
datacenter   = dc1
rack         = rack-a
node         = cassandra-01
filesystem   = /data
keyspace     = telemetry_obs
table        = readings_by_sensor_day
component    = commitlog | sstable | hints | snapshot
~~~

This is a **design label taxonomy**, not built-in Prometheus label names on every exporter. Never attach arbitrary table labels to node-level metrics that have no keyspace/table scope. When aggregating disk across a DC, avoid summing replica sizes as if they represented un-replicated logical data.

### 10.2. Three rules for useful disk alerts

1. **Measure growth rate and free bytes, not just % used.** Two volumes both at 85% used—one with 20 GB free and another with 2 TB free—carry very different risk.
2. **Pair causal signals.** Rising disk + rising hints + down replica points to handoff; rising disk + pending compaction + rising SSTable count points to compaction debt; rising disk + snapshot count/age points to retention cleanup.
3. **Alert per node/volume first, then correlate service impact.** One nearly full node can trigger write timeouts even when total cluster capacity looks ample.

### 10.3. Illustrative alert threshold examples

| Alert tier | Illustrative condition | Action needed |
| --- | --- | --- |
| **Watch** | Disk > 75% and growing faster than baseline | Inspect growth rate and snapshot/hints/compaction trends. |
| **Actionable** | Disk > 85% or free space drops below planned compaction headroom | Identify dominant consumer, shed load or adjust scheduled maintenance. |
| **Critical** | Disk > 95%, allocation/flush errors, or rising write timeouts | Prioritize data preservation, assess service availability, execute incident runbook. |

The **75/85/95%** figures are **illustrative only**, not Cassandra standards. Production thresholds must reflect volume size, write rate, compaction strategy, largest SSTable size, streaming requirements, response time, and headroom when a replica goes down.

### 10.4. Estimating compaction headroom

Suppose a **1,000 GB** volume has **820 GB** used and **180 GB** free. An upcoming compaction is expected to write **150 GB** of output while incoming writes add **40 GB** before inputs can be deleted.

~~~text
Initial free space                    : 180 GB
Estimated temporary compaction output : 150 GB
New writes during the same window     :  40 GB
Illustrative minimum extra needed     : 190 GB
Conclusion                            : at least 10 GB short of headroom
~~~

This is a **simplified estimate**: inputs/outputs may free at staggered times, while filesystem overhead, snapshots, and concurrent compactions push peak demand higher. Still, the lesson is clear: **never count on a huge compaction to rescue a volume that already lacks space to write its output**.

## 11. Java Driver: observing from the application side

Disk, hints, and SSTables are **server-side** indicators; the Java application should simultaneously measure **end-to-end latency, timeouts, CL, error rates, and key query classes** to spot user impact.

Example using **Apache Cassandra Java Driver 4.x**; the code prints simple metrics in place of a full metrics backend and requires no cluster admin privileges.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetSocketAddress;
import java.time.LocalDate;
import java.util.concurrent.TimeUnit;

public final class ObservedCassandraRead {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement statement = session.prepare(
                "SELECT event_time, event_id, reading " +
                "FROM telemetry_obs.readings_by_sensor_day " +
                "WHERE sensor_id = ? AND event_day = ? LIMIT 50");

            BoundStatement request = statement.bind(
                    "sensor-9", LocalDate.of(2026, 11, 21))
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            long startedAt = System.nanoTime();
            boolean success = false;
            try {
                for (Row row : session.execute(request)) {
                    System.out.println(row.getInstant("event_time")
                        + " => " + row.getBigDecimal("reading"));
                }
                success = true;
            } catch (RuntimeException error) {
                // Production: classify timeout/unavailable/overloaded,
                // record metrics labeled by query_name, DC, consistency level.
                // Never log sensitive payloads or blindly retry every error.
                System.err.println("reading query failed: "
                    + error.getClass().getSimpleName());
                throw error;
            } finally {
                long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - startedAt);
                System.out.println("query=readings_by_sensor_day"
                    + " consistency=LOCAL_QUORUM"
                    + " success=" + success
                    + " elapsed_ms=" + elapsedMs);
            }
        }
    }
}
~~~

**Measurement explanation:**

- The timer measures **client time iterating the entire result set**, which can include multi-page fetches and stdout printing, differing from single-replica internal latency. In production, instrument at the driver/request layer to separate server latency, network, paging, and client handling.
- `LOCAL_QUORUM` with RF = 3 in `dc1` requires two replicas; a timeout at this CL **does not automatically prove a disk is full**, since the cause could be a down node, network, read path, or compaction.
- Keep `query_name` labels bounded; avoid partition keys or UUIDs as metric labels to prevent **high cardinality** and data leakage.
- Never grant the Java application privileges to run `nodetool`, delete snapshots, truncate hints, or touch storage files. Disk management belongs strictly to authorized operational channels.

## 12. Runbook: fast disk growth—isolating the cause in a few steps

### Step 1 — Assess scope and severity

- Which node, DC/rack, and **which specific volume** is nearly full? Are disk write errors, memtable flush failures, or request timeouts rising?
- How many GB remain in `df`? How does GB/hour growth compare to response time?
- Are any nodes down, bootstrapping, rebuilding, repairing, streaming, or running major compaction?

If imminent disk exhaustion threatens to halt the write path, escalate under an **incident commander**, prioritizing data preservation and service continuity; never run destructive cleanup commands before confirming root cause.

### Step 2 — Break down storage consumers

- Compare `du` across actual directories against disk metrics, remembering hard links.
- Use `tablestats` to see which tables show growing SSTable footprints.
- Check commit log size, flush metrics/queues, and compaction backlog.
- Check hints size/queues and target replica states.
- Check snapshot tags, snapshot age, off-node backups, and retention policies.

### Step 3 — Match combined signals to root causes

| Combined signals | Primary hypothesis | Relatively safe action |
| --- | --- | --- |
| Disk up, SSTable count and pending compaction up | Compaction falling behind writes/updates/deletes | Measure I/O, workload, partition size, compaction; throttle load/maintenance per runbook. |
| Commit log up, pending flushes up | Flushes stalled; segments still hold un-SSTabled data | Inspect flush errors, disk latency, and resources; never delete commit logs. |
| Hints up, target node down | Handoff incomplete | Restore replica/network, monitor replay; evaluate repair for missed data. |
| Hints up even with target node up | Delivery throttled/failing or huge backlog | Check logs, throughput, version, and repair policy. |
| Snapshot count/size up after scheduled backups | Expired retention not cleared or backup incomplete | Verify off-node backup, clear per approved retention. |
| Disk rises during compaction/streaming, then drops | Temporary coexistence of new outputs and old inputs | Ensure headroom; avoid launching more heavy tasks. |
| Live SSTables shrink yet `df` stays flat | Snapshots/hard links or open-file handles still pin blocks | Check retention/references; never delete active SSTables. |
| Many tombstones, high read latency, bloated SSTables | Deletes/TTLs and overlapping versions | Review schema, TTL, bucketing, compaction, and repair cadence. |

### Step 4 — Fix the cause, not just the symptom

If snapshots are backed up/verified and expired, clear **only those snapshots** per the runbook. If hints are backed up, restore peer replicas and schedule repairs as needed. If flushes/compactions are stalled, resolve I/O, partition design, or capacity before piling on extra maintenance commands. If real data is growing steadily, **expand capacity** or adjust retention/schema—never delete SSTables manually.

### Step 5 — Verify after intervention

- Has disk growth slowed, with enough free headroom for upcoming tasks?
- Have client latency/timeouts, write failures, and replica health recovered?
- Are commit log/hints/compaction backlogs draining over time?
- Is snapshot retention properly recorded and restore capability intact?
- Is follow-up repair needed after a replica missed mutations or tombstones?

Record **before/after metrics**, Cassandra version, DC/node/volume, actions taken, timestamps, and approver so the team does not have to re-guess next time.

## 13. Common misconceptions that cause incidents

| Claim | Assessment | Reason |
| --- | --- | --- |
| “`df` is larger than `tablestats`, so Cassandra is misreporting.” | **False** | The filesystem also holds commit logs, hints, snapshots, temp files, and more. |
| “Snapshots always double active SSTable disk usage immediately.” | **False** | Hard links share blocks; extra space is retained only after compaction creates new files. |
| “Deleting a snapshot frees every byte listed as snapshot size.” | **False** | Blocks may still be referenced by active SSTables or other snapshots. |
| “Manually deleting commit log segments frees disk safely.” | **False** | Breaks crash-replay recovery for unflushed mutations. |
| “Hints act as an extra replica, so repair isn't needed.” | **False** | Hints have limits/TTLs and never replace anti-entropy repair. |
| “`LOCAL_QUORUM` guarantees every replica received the mutation.” | **False** | RF 3 only requires 2 local-DC ACKs to satisfy CL. |
| “Once TTL expires, SSTables vanish immediately.” | **False** | Tombstones, `gc_grace_seconds`, and compaction govern physical reclamation. |
| “Major compaction is always the best fix for a full disk.” | **False** | Requires heavy scratch space and imposes severe I/O load. |
| “Cluster has 40% disk free overall, so one node at 97% is fine.” | **False** | Writes and flushes can fail on the single nearly full node/volume. |
| “Disk grew due to hints, so just delete the hints folder.” | **False** | Target replicas can lose undelivered mutations. |
| “Operators must verify off-node backups before clearing snapshots.” | **True** | On-node snapshots may be the last available restore point. |

## 14. Exercises with answers

**Exercise 1.** After compaction finishes, `tablestats` shows active SSTable size dropped sharply, yet `df` barely changed. Why?

**Answer:** Local snapshots or backups may still reference the old input SSTables via hard links; the active file set changed, but filesystem blocks are not freed yet. Check `listsnapshots`, retention policies, and remaining references.

**Exercise 2.** RF = 3 in `dc1`. N3 is offline, and `LOCAL_QUORUM` writes succeed on N1/N2 while coordinator hints grow. Can you assert N3 has durably persisted those mutations?

**Answer:** **No.** Quorum required only 2 ACKs, and hints are pending deliveries. Restore N3, monitor hint delivery, and run repair if needed.

**Exercise 3.** Why might a commit log segment remain unreclaimed even after one table flushes?

**Answer:** A segment can hold mutations for **multiple tables**; data for another table may still need replay. Cassandra reclaims segments only once all contained mutations are safely persisted.

**Exercise 4.** A volume has 180 GB free; expected compaction output is 150 GB while new writes add ~40 GB before inputs can be freed. Is headroom sufficient under the simplified estimate?

**Answer:** **No.** Illustrative minimum need is 190 GB—short by at least 10 GB before counting metadata or concurrent tasks. Do not force a large compaction on that volume.

**Exercise 5.** Why does `LIMIT 10` not guarantee a read inspects only 10 rows or tombstones?

**Answer:** Cassandra may traverse many versions and tombstones before collecting ten **live** rows. Inspect tombstones scanned and partition/SSTable design.

**Exercise 6.** Hints disk usage spikes after a node goes down. Should the first response be deleting hint files or fixing the down replica?

**Answer:** **Investigate and restore the replica/network first**, then monitor handoff; never delete hint files manually. After a long outage, review repair scheduling and `gc_grace_seconds`.

**Exercise 7.** A dashboard adds `du -sh` of the data directory plus `du -sh` of snapshots and subtracts from `df` free space. What can go wrong?

**Answer:** It can **double-count** SSTables hard-linked in both active data and snapshots, whereas `df` counts unique filesystem blocks. Understand inode sharing and metric definitions.

**Exercise 8.** A table sets a 30-day TTL, yet disk usage grows for 45 days. Does that prove TTL is broken?

**Answer:** **No.** Data may be logically expired while tombstones/SSTables still await purge eligibility, snapshots pin old files, or write rates outpace reclamation. Check `TTL()`, compaction, `gc_grace_seconds`, cells with different TTLs, and snapshot retention.

## 15. Diagnostic decision flow

~~~mermaid
flowchart TD
    A["Cassandra node disk filling up"] --> B["Check df/free GB, growth rate, and errors"]
    B --> C{"Which consumer is growing most?"}
    C -->|Commit log| L["Check memtable flushes, segments, and disk I/O"]
    C -->|SSTables| S["Check compaction debt, TTL, tombstones, partition size"]
    C -->|Hints| H["Check down replicas, handoff, repair"]
    C -->|Snapshots| P["Check off-node backup status, hard links, retention"]
    C -->|Streaming/compaction output| T["Check headroom and background jobs"]
    L --> X["Fix root cause; never delete data files manually"]
    S --> X
    H --> X
    P --> X
    T --> X
    X --> V["Verify free disk, latency, backlogs, and data safety"]
~~~

**Summary:** `df` tells **whether the node still has room to write**; `tablestats` and SSTable metrics tell **how large active data is**; the commit log tracks **mutations still needed for crash recovery**; hints reflect **mutations waiting on peer replicas**; and snapshots track **old files pinned for recovery**. Compaction and streaming can require temporary extra disk, so observability must combine **current capacity, growth rate, headroom, background tasks, and replica state**. When troubleshooting a filling disk, prioritize data integrity and fixing root causes over manually deleting files Cassandra still needs.
