# Commit Log, Storage Devices, and Durability Goals in Apache Cassandra

## 1. Why Does the Commit Log Govern the Durability of a Write?

Apache Cassandra is a distributed **wide-column** database. Data is distributed by **partition key** and replicated to appropriate replicas, while applications use **consistency levels (CL)** to decide how many responses are required before treating a CQL operation as successful.

However, **a replica acknowledging a write** and **data being safe on non-volatile storage across power loss** are two separate questions. Cassandra uses the **commit log** and **memtables** on the write path:

- The **memtable** holds data in memory, enabling fast writes prior to creating SSTables.
- The **commit log** records mutations in an append-only format so a node can replay mutations not yet flushed to SSTables after a process restart.
- **SSTables** are immutable data files created when memtables flush; compaction continues merging SSTables over time.

If Cassandra updated only memtables in RAM, a crash could wipe out all un-flushed data. The commit log provides a recovery path, yet actual effectiveness depends on the **disk synchronization (sync) mode**, the `durable_writes` setting, storage hardware, and failure domains.

This lesson belongs to the **Resource Tuning** chapter of the **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA** module. It connects write-path architecture with durability goals, read/write consistency levels, replication, compaction/repair, incident handling, and Java applications.

Learning outcomes:

1. Distinguish **commit log append**, **successful fsync**, **SSTable flush**, and **CL ACK**.
2. Understand commit-log sync modes along with latency–throughput–data-loss risk trade-offs.
3. Choose storage devices, capacity, and operational policies based on real **RPO/RTO** targets.
4. Diagnose commit log space growth, full disks, slow fsyncs, and crashes/restarts.
5. Design CQL and Java clients without confusing timeouts, quorums, or retries with durable persistence guarantees.

## 2. The Write Path: From Java Client to SSTable

### 2.1. What Steps Does a Mutation Go Through?

Suppose the table `telemetry.readings_by_device_day` has replication factor 3 in datacenter `dc1`. A Java client sends an `INSERT` at `LOCAL_QUORUM`; the coordinator locates replicas from the partition key token, distributes the mutation, and waits for two replicas in that DC to acknowledge.

At each replica, normal write handling consists of these logical stages:

1. Receive and validate the mutation.
2. Write the mutation to the **commit log**, unless configuration or data type alters behavior.
3. Apply the mutation to the corresponding **memtable**.
4. Acknowledge according to write rules and the active commit-log sync policy.
5. When the memtable meets flush criteria, flush it to an **SSTable** on the data filesystem.
6. Commit log segments no longer containing data needed for replay can be freed or reused.

~~~mermaid
flowchart LR
    A["Java client: INSERT, CL=LOCAL_QUORUM"] --> B["Coordinator"]
    B --> C["Replica A"]
    B --> D["Replica B"]
    B --> E["Replica C"]
    C --> F["Append commit log + update memtable"]
    D --> G["Append commit log + update memtable"]
    E --> H["Append commit log + update memtable"]
    F --> I["ACK per sync mode"]
    G --> J["ACK per sync mode"]
    I --> B
    J --> B
    B --> K["Client success once enough ACKs arrive"]
    F --> L["Memtable flush -> SSTable"]
    G --> M["Memtable flush -> SSTable"]
~~~

This diagram is conceptual. Replicas process concurrently; exact ordering, ACK timing, and certain optimizations vary by version and mutation type.

**Key point:** **write CL controls how many replicas ACK**, whereas commit-log sync configuration controls how strongly the mutation has been forced down to durable storage when a replica ACKs. A high CL alone cannot fix a weak commit log configuration across replicas.

### 2.2. Commit Log Is Not an SSTable

| Property | Commit log | Memtable | SSTable |
|---|---|---|---|
| Storage location | Sequential log files on filesystem | RAM and Cassandra memory structures | Immutable data files on disk |
| Role | Replay un-flushed mutations | Absorb mutations and serve reads | Store flushed data for reads/compaction |
| Write pattern | Append to segments, sync per config | Update in-memory structure | Flush/compaction writes new files |
| After process crash | Valid log portion replayed on startup | Un-flushed contents lost | Flushed SSTable data persists if storage is intact |
| During compaction | Does not directly replace compaction | Memtable flushes as needed | SSTables are merged and rewritten |
| Long-term backup copy? | **No** | **No** | Requires snapshots/backups and tested restores |

The commit log is **not** intended as a backup substitute. It is a local crash-recovery log for mutations not yet safely persisted into SSTables.

## 3. Commit-Log Segments, Flushing, and Space Reclamation

### 3.1. The Commit Log Is Divided into Segments

Cassandra does not append forever to one unbounded log file. The commit log is managed as **segments** on the filesystem. Mutations from multiple tables can share a segment, and Cassandra tracks which data still requires replay.

When a memtable flushes safely to an SSTable, the corresponding commit log entries are no longer needed for that memtable. **A segment can only be reclaimed/reused once all data in that segment still requiring recovery has been handled appropriately.**

Important consequences:

- A low-traffic table with an un-flushed memtable can pin a segment containing many mutations from other tables, preventing reclamation.
- When commit-log space grows high, Cassandra can trigger memtable flushes under total-space management.
- Commit-log size and **SSTable data size** grow and shrink differently; do not assume commit log growth means logical table data grew proportionally.
- Flushing creates extra write I/O. Afterward, compaction can introduce write amplification and temporary space demands.

### 3.2. Why Does the Commit Log Grow Even When Client Writes Succeed?

Suppose multiple tables share mutations written into a commit-log segment. Hot tables flush quickly; a low-traffic table still holds un-flushed data. The segment containing both may remain pinned because the low-traffic table's mutations are not yet safely in SSTables.

Other signs causing log growth:

- Write rate exceeds flush capacity.
- The SSTable data disk is slow, delaying flushes.
- Many active memtables or tables with differing write patterns.
- I/O contention with compaction, repair, bootstrap/streaming, or snapshots.
- Filesystem nearly full or hitting errors, preventing flushes/syncs from keeping pace.

**Never manually delete commit-log segments to reclaim disk space.** Doing so can lose mutations whose memtables have not flushed; inspect state and follow proper recovery procedures before touching any files.

### 3.3. Role of the Total Space Limit

Cassandra releases include mechanisms/settings to bound total commit log space (often seen conceptually as `commitlog_total_space_in_mb` or a version-specific name). As pressure climbs, Cassandra triggers flushes to free segments, yet **this limit is not a hard quota guaranteeing the filesystem always retains free space** in all circumstances.

If set too low relative to workload and resources, the node may flush constantly, driving write amplification and storage congestion. If set too high on a small volume, logs can eat into headroom needed by other operations. Monitor commit-log disk usage, pending flushes, disk latency, and write p99 together.

## 4. Three Concepts Easily Conflated: Append, Sync, and ACK

### 4.1. Appending to the Filesystem Does Not Guarantee Surviving Power Loss

An append call may only place bytes into a process buffer or the **OS page cache**. Only when data is properly synchronized and the storage device reliably executes the write command do you have strong grounds to say data has cleared RAM/cache loss risks.

Therefore:

- **Process crash** is not the same as **host power loss**. The OS page cache may survive a single process dying, yet you should not rely on it always flushing cleanly.
- **fsync/force** asks the OS to push data down to the storage layer; actual guarantees still depend on whether the filesystem, controller, and device honor durability semantics.
- **Devices with volatile write caches unprotected against power loss** can undermine expected guarantees even when software invokes fsync.

### 4.2. Commit-Log Sync Modes

Cassandra offers commit-log synchronization modes, commonly **`periodic`** and **`batch`**; some versions/configs also offer **`group`**. Exact names, defaults, and companion parameters must be verified against the deployed Cassandra release.

| Mode | General Principle | Key Trade-Off |
|---|---|---|
| **`periodic`** | Mutations can be acknowledged after appending to the log path while forcing data to disk runs periodically | Better throughput and latency on many workloads; carries a **risk window** on sudden host/power loss |
| **`batch`** | Groups/write steps wait for log sync to disk per mode rules before acknowledging | Narrows the window where ACKed mutations aren't durable yet; increases sensitivity to fsync latency |
| **`group`** (if supported) | Batches a group of mutations to amortize sync cost | Balances throughput against group wait time; read version config and exact semantics |

**Do not confuse `commitlog_sync=batch` with CQL `BEGIN BATCH`.** One is a node-level write-log sync policy; the other is a CQL statement grouping mutations with its own semantics.

### 4.3. If Using Periodic, What Is the Data-Loss Risk?

Suppose a system picks a **10-second sync interval purely for illustration**, recording mutations and returning ACKs in periodic mode. If the machine loses power before the next sync, some ACKed mutations not yet safely on disk may fail to recover from the log.

**Do not interpret "10 seconds" as a guarantee of always losing exactly 10 seconds of data.** Data may have been flushed earlier by the OS/device, already reached SSTables, or been affected by device latency, scheduling, and other faults. The figure is an **estimated risk interval tied to sync cadence**, not an exact verified RPO.

With replicated data, if **only one node loses power** while other replicas hold the mutation, data can recover from peers. Yet if **multiple replicas crash/lose power together** before persistence completes, high RF/CL alone will not preserve every ACKed mutation.

### 4.4. If Using Batch, Is There Absolute "Zero Data Loss"?

Do not make that claim. Waiting for fsync before ACK strengthens durability on the acknowledging replica, yet:

- A disk/controller may falsely report success or have an unprotected write cache.
- Filesystem bugs, firmware faults, or an entire failure-domain outage can still cause loss.
- Non-ACKing replicas may still lack the mutation even after the client met CL.
- Operational mistakes, accidental deletes, corruption, or application bugs are not solved by the commit log alone.
- Backups, repair, and restore drills remain essential.

**Durability is a property of the whole write path—Cassandra + OS/filesystem + hardware + replication + operations**—not a single configuration flag.

## 5. Keyspace `durable_writes` and Guarantee Boundaries

When creating a keyspace, Cassandra allows configuring `durable_writes`. For keyspaces holding important data, **`durable_writes = true`** is the standard choice.

~~~cql
CREATE KEYSPACE telemetry_demo
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE telemetry_demo.readings_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    temperature double,
    PRIMARY KEY ((device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

The name `dc1` is illustrative; it must match the actual datacenter name in your cluster.

### 5.1. `durable_writes = true`

Cassandra uses the commit log for that keyspace's mutations via the standard path. **This does not by itself prove fsync before ACK**: risk exposure still depends on `commitlog_sync` and the storage device.

### 5.2. `durable_writes = false`

Depending on operation type and version, disabling durable writes means mutations bypass the normal commit log path for that keyspace; un-flushed memtable data may not survive a crash.

This is a **deliberate choice to give up part of crash protection**, not a free tuning trick to raise TPS. Consider it only for truly reconstructible workloads with corresponding tests and risk sign-off.

Never disable durable writes for transactional data, business state, or hard-to-recreate data just because write latency looks high. Even for ephemeral data, analyze impacts on replicas, ACKs, crashes, and recovery.

### 5.3. Distinguishing Across Three Condition Layers

| Condition | What It Determines | What It Does **Not** Determine |
|---|---|---|
| **`durable_writes`** on keyspace | Whether the keyspace uses the standard commit log write path | Number of replica ACKs |
| **`commitlog_sync`** on node | When the log is forced to disk on the write path | RF, replica selection, partition key |
| **Write CL** on request | ACK condition for coordinator to return success | Write cache protection, filesystem, or snapshots/backups |
| **RF + topology** on keyspace | Copy count and replica placement | Whether each replica waits for fsync before ACK |

Managing durability requires inspecting **all three configuration layers and the hardware together**. Do not assume RF=3 with `LOCAL_QUORUM` guarantees two copies were fsynced if running `periodic`.

## 6. Setting Targets Before Tuning: RPO, RTO, and Write Latency

### 6.1. What Is RPO?

**Recovery Point Objective (RPO)** is the maximum data loss a business **accepts** when an incident hits a defined failure scope. It can be expressed in time or mutation count.

Examples:

- Telemetry that devices can resend: the business accepts losing at most a few seconds of readings if all recovery mechanisms fail.
- Payment-confirmed orders: requires zero loss of ACKed state even if a machine dies; may need stronger guarantees and reconciliation mechanisms.
- Event logs backed by durable upstream storage: Cassandra can be backfilled; effective RPO depends on upstream retention and replay procedures.

**Target RPO is not achieved automatically** simply by setting a matching commit-log sync interval. You must define the **failure scenario**: single process crash, one-node power loss, rack loss, whole-DC outage, or accidental logical deletion.

### 6.2. What Is RTO?

**Recovery Time Objective (RTO)** is the maximum time the business accepts to restore service after an outage.

The commit log helps a node **replay mutations** on restart, yet RTO also depends on:

- Volume of log to replay and disk/CPU speed.
- Health of surviving replicas, application CL, and failover behavior.
- Streaming/rebuilding if a node loses its disk.
- Repair, data validation, backup/restore, and procedures to re-admit traffic.
- Post-recovery compaction/flush volume.

**Do not equate commit log replay time with service RTO.** If one machine dies, the application may keep running via surviving replicas; conversely, a node may be UP yet still miss SLOs or lack fully restored data.

### 6.3. Target Selection Matrix

| Business Requirement | Priority Focus | Required Validation Test |
|---|---|---|
| Must survive single process crash | Commit log, clean restart/replay, healthy replicas | Controlled restart in staging |
| Must survive host/machine power loss | Sync policy and hardware genuinely retaining data across power loss | Fault injection in test environment, verify ACKed data |
| Must tolerate one node failure | RF, CL, replicas placed across distinct hosts | Stop one node in staging and test reads/writes |
| Must survive entire rack/DC loss | Failure-domain-aware RF, routing/CL, network, and restore | Simulate rack/DC outage per runbook |
| Must recover from accidental delete/corruption | Snapshots/backups with verified restores and retention | Restore drills—do not rely on commit log |
| Must hit low write p99 | Fsync latency, network, queues, commit-log device | Benchmark p50/p95/p99 alongside error rate |
| Must never run out of disk | Headroom and capacity alerting | Load test above normal traffic, track flush/compaction |

### 6.4. Data-Loss Risk in a Periodic Window: Rough Calculation

Suppose on **one replica**, eligible write traffic is:

- 8,000 mutations/sec.
- Average 1 KiB of commit log data per mutation (estimate).
- Hypothetical 5-second sync risk window.

~~~text
8,000 mutations/s × 1 KiB/mutation × 5 s
= 40,000 KiB ≈ 39.1 MiB mutation-log payload
~~~

**39.1 MiB is neither "guaranteed to be lost" nor a hard upper bound.** It is merely an estimate of mutation volume potentially sitting inside an un-synced window. Actual bytes may already be flushed to disk, held by another replica, carry metadata overhead, involve retries, or face a sync window that is not strictly five seconds.

Never **multiply by the replica count** and claim that is the logical data at risk; multiple replicas hold copies of the same mutations. Evaluate the **ACK set, failure domains, and persistence timing on each replica**.

## 7. Choosing Storage Devices for the Commit Log

### 7.1. Commit Log Writes Are Sequential Yet Highly Sensitive to Sync Latency

An append-only log writes sequentially, yet in modes waiting for sync before ACK, **fsync latency and drive tail latency** can dictate write p95/p99. An SSD/NVMe with impressive brochure throughput may still show poor fsync p99 under concurrent compaction, flushes, and streaming.

When selecting storage, evaluate:

- **Write latency**, especially p95/p99 and stability when nearly full.
- **Fsync/sustained write rate** under real patterns, not just sequential MB/s.
- **Power-loss protection (PLP)** for drive caches and in-flight writes.
- **Endurance** and sustained write resilience across multi-day workloads.
- **Filesystem + mount + storage stack** and flush/barrier semantics.
- **I/O contention** with SSTable flushes/compaction, snapshots, and background tasks.

An NVMe drive with PLP on reliable infrastructure is often a strong candidate for low fsync latency. Still, exact device class, cloud volumes, RAID/JBOD layout, and tuning must fit real hardware and failure scenarios.

### 7.2. Should You Separate the Commit Log from Data Directories?

Two common layouts:

~~~text
Option A: Shared high-performance storage pool

  /data/cassandra/data       <- SSTables
  /data/cassandra/commitlog  <- Commit log

Option B: Separate device / volume

  /data/cassandra/data       <- SSTables
  /fast/cassandra/commitlog  <- Commit log
~~~

Option B can **isolate commit log I/O** from compaction and streaming when backed by truly independent physical devices or volumes with dedicated capacity. Separating paths on the **same underlying device**, however, creates no extra IOPS and does not reduce contention.

| Choice | Potential Benefit | Trade-Off / Risk |
|---|---|---|
| Same strong NVMe | Simple, fewer failure points, easy operations | Flushes/compaction may contend with commit log I/O |
| Commit log on dedicated device | Can reduce fsync tail latency via workload isolation | Cost, capacity management, separate failure domain, needs backup/recovery policy |
| Commit log on slow disk or network storage failing sync requirements | Lower upfront cost | High tail write latency, timeouts, data risk if storage lacks durability guarantees |
| Commit log on ephemeral disk | Potentially high I/O | Data loss when instance/volume vanishes unless covered by proper replication/recovery |

**Never move the commit log to ephemeral storage just for higher TPS** without analyzing RPO/RTO and the consequences of losing one or more replicas. On cloud platforms, verify provider documentation on flush/fsync semantics and volume durability.

### 7.3. PLP, RAID, Filesystem, and UPS

- **PLP** on an SSD/controller protects volatile cache data on power loss. It complements—never replaces—replication and backups.
- **UPS** prevents certain power outages but cannot prevent crashes, controller bugs, or drive failures.
- **RAID/JBOD** each carry specific failure/performance models. Because Cassandra already provides replication, do not pick RAID by default just to feel "safer"; assess failure domains, disk replacement procedures, fault tolerance, and durability targets.
- **Filesystem journaling** does not mean every commit-log append is already durable. Actual `fsync` behavior across device and controller is what must be verified.
- **Storage caches** must never report fsync success before data is safe unless the cache is power-protected and obeys flush commands. Non-compliant hardware breaks software durability assumptions.

## 8. Commit Log Capacity and Disk Headroom

### 8.1. Do Not Size the Volume by a Single Segment's Size

Capacity must cover:

1. Active / non-reusable commit-log segments.
2. Segments generated during write bursts.
3. Extended segment retention caused by slow or stalled memtable flushes.
4. Filesystem overhead, logs, and other consumers if sharing a volume.
5. Operational headroom during investigation and recovery.

A configured segment size like `commitlog_segment_size_in_mb` is merely a file management unit, not **total** required space.

### 8.2. Capacity Example When Flushing Is Bottlenecked

Suppose a node generates an average of **50 MiB/s of mutation logs** during a burst, and an incident blocks backlog reclamation for 4 minutes. For rough sizing:

~~~text
50 MiB/s × 240 s = 12,000 MiB ≈ 11.72 GiB
~~~

This number does not mean commit log disk usage always rises by exactly 11.72 GiB: segments may be reused, data may compress, flushing may still trickle along, or old segments may already occupy disk. Use the math to gauge risk scale, then **measure real bytes per node**.

A volume with only 5 GiB free is clearly at risk in this scenario even if logical application data barely grows. The real fix may be flush throughput, compaction/streaming scheduling, or I/O capacity—not just raising `commitlog_total_space`.

### 8.3. What Can Happen When the Commit Log Fills Up?

When the system can no longer write logs, writes, flushes, or segment reuse can be severely disrupted. Depending on version and error state, the node may:

- Emit write errors/timeouts and dropped mutations.
- Increase flush/compaction pressure and read/write p99.
- Enter a state unable to accept certain requests.
- Raise disk-full warnings and log exceptions.
- Struggle during startup/recovery if the filesystem or commit log is corrupted.

**Do not assert every Cassandra version reacts identically to a full disk.** Instead of waiting for errors, alert on free bytes, commitlog size trends, pending flushes, error rates, and p95/p99.

## 9. Commit Log vs. Hints, Batchlog, and Backups

| Component | Purpose | Can It Replace the Commit Log? |
|---|---|---|
| **Commit log** | Replay un-flushed mutations after a node restarts | It is the mechanism under discussion |
| **Hints / hinted handoff** | Replay missed mutations to a temporarily absent replica | **No**: heals divergence between replicas, not a crash log for local memtables |
| **Batchlog** | Supports re-distributing logged batches in applicable scenarios | **No**: different purpose and scope |
| **SSTable** | Stores flushed data and serves reads | Part of the same engine, yet does not capture un-flushed mutations |
| **Repair** | Compares replicas and synchronizes divergence | **No**: cannot recover proof of mutations lost on all replicas |
| **Snapshot/backup** | Recovers from data loss or accidental deletes per retention | **Cannot replace commit log** on the write path; nor can commit log replace backups |

If a mutation is ACKed on some replicas and a missing node later recovers, **hinted handoff and repair** help synchronize it. Yet if a mutation was never durably persisted on **any surviving replica**, repair cannot conjure it out of thin air.

## 10. Consistency Level, Replication, and Durability: Three Risk Layers

Assume a keyspace with RF=3 in a single DC.

| Scenario | Write CL | What Is Confirmed | What Is Not Guaranteed |
|---|---|---|---|
| A ACKs, B/C haven't ACKed | `ONE` | At least one replica completed its write path | Unknown if B/C have data; also depends on A's sync policy |
| A/B ACK, C hasn't ACKed | `LOCAL_QUORUM` | Two valid ACKs in the DC | C may lack the mutation; A/B may not have fsynced if periodic |
| A/B/C ACK | `ALL` | All three ACKed per CL | Does not replace PLP, sync policy, backups, or accidental-delete protection |
| Only A alive and CL `LOCAL_QUORUM` | `LOCAL_QUORUM` | Quorum cannot be met | Hints do not satisfy ACK or create durability |
| A/B ACK, other DC hasn't confirmed | `LOCAL_QUORUM` | Local DC quorum | No guarantee the remote DC confirmed quorum |

### 10.1. Durability Does Not Equal Linearizability

Even if the commit log syncs before ACK and writes use `QUORUM`, Cassandra still applies timestamp/last-write-wins rules for normal writes. Two clients concurrently writing the same cell produce outcomes based on timestamps and timing; **durability does not create compare-and-set semantics**.

If business logic requires "update only when current version equals X", use LWT with `IF` / `IF NOT EXISTS` and appropriate serial consistency. The commit log and durable storage still matter, yet they do not replace consensus.

### 10.2. Partitioning Hardware by Failure Domains

RF=3 has vastly different real-world meaning if all three replicas share one power feed, rack, or underlying filesystem. With `NetworkTopologyStrategy`, DC/rack topology and placement must be configured properly to spread risk; CL must align with fault-tolerance targets.

**Do not treat replica count as a substitute for failure-domain analysis.** A rack-wide power loss can wipe out multiple copies at once despite high RF.

## 11. Version-Specific Configuration and Verification

Parameter names, defaults, units, and support **change across Cassandra versions**. Below are common concepts to guide inspection, **not production configs to copy verbatim**.

| Config Group | Meaning | Questions When Changing |
|---|---|---|
| `commitlog_directory` | Commit log path | Does it have enough disk, PLP, and fault isolation? |
| `commitlog_sync` | Synchronization method (periodic/batch/version-specific) | When are ACK and sync executed? |
| **Sync period** parameter | Interval between periodic syncs; name/unit varies by version | How do risk window and write latency change? |
| **Batch/group window** parameter | Mutation grouping waiting for sync, if supported | How do p99 and throughput change? |
| `commitlog_segment_size_in_mb` or equivalent | Segment management size | Does it match log churn and mutation sizes? |
| `commitlog_total_space_in_mb` or equivalent | Total log/flush management threshold | Does raising it jeopardize disk headroom? |
| Version-specific commit-log compression options | Compressing logs before storage | What is the CPU vs I/O trade-off? |
| Keyspace `durable_writes` | Use standard commit log path | Can the business tolerate losing un-flushed data? |

The following block **illustrates the concept** and intentionally leaves version-dependent parameters abstract:

~~~yaml
# ILLUSTRATIVE LINES — verify against your running version's cassandra.yaml.
commitlog_directory: /var/lib/cassandra/commitlog
commitlog_sync: periodic

# Examples of CONCEPTS to verify, do not guess syntax:
# - sync period if using periodic
# - batch/group window if using batch/group
# - segment size and total commit log space
~~~

Never edit `cassandra.yaml` on a traffic-serving node without benchmarks, syntax/startup checks, rollout plans, and rollback steps. Some changes require restarts; exact behavior must follow your running release's documentation.

### Controlled Change Procedure

1. Capture baseline state (write p50/p95/p99, TPS, errors, commit-log size, fsync/disk latency).
2. Define allowed RPO/RTO and failure scenarios.
3. Verify exact version, key names/units, and topology.
4. Test in staging with production-like payloads, CL, concurrency, and storage hardware.
5. Change one factor under control, evaluating throughput **and** fault/crash recovery.
6. Roll out via change window/canary where appropriate, preserving rollback readiness.
7. Update runbooks, monitoring, and verify real behavior post-deployment.

## 12. Observing Commit Log, Flushes, and Storage via Metrics

### 12.1. Recommended Metric Groups

| Group | What to Measure | Signals Requiring Investigation |
|---|---|---|
| **Commit log** | Disk bytes, segment count, append/sync latency, sync failures (if exporter supports) | Continuous log growth or rising fsync p99 |
| **Write path** | Write latency p50/p95/p99, timeouts, unavailable, mutation errors | Requests queuing or failing |
| **Memtable/flush** | Pending flushes, flush time, bytes flushed | Logs not reclaimed because data hasn't reached SSTables |
| **Disk** | Free bytes, throughput, IOPS, await/utilization, fsync latency | Device running out of headroom or high tail latency |
| **Compaction/repair** | Pending compaction, streaming, repair load | Background jobs competing for I/O with commit log/flushes |
| **Node health** | GC pauses, heap, CPU, dropped messages, status | Pressure elsewhere dragging down write latency |
| **Replication** | CL and RF, node UP/DOWN, hints, repair state | Whether ACKs succeed and how synchronized data is |

Exact JMX/Prometheus metrics **depend on Cassandra version and exporter**. A metric named `CommitLog...` may be collected per node rather than per keyspace; verify scope and units before aggregating.

Do not look only at **write throughput**: a periodic configuration can raise TPS at the cost of data-loss risk during power outages. Conversely, a batch configuration may yield lower TPS while meeting stricter RPO requirements. Evaluate **performance and durability together**.

### 12.2. Low-Invasiveness Diagnostic Commands

Examples on a node with operational access:

~~~bash
# Node status and DC/rack layout.
nodetool status

# Node load, cache/heap info, and general state.
nodetool info

# Thread pools, pending, and dropped messages.
nodetool tpstats

# Per-table read/write and SSTable stats.
nodetool tablestats telemetry_demo.readings_by_device_day

# Compaction tasks competing for disk I/O.
nodetool compactionstats

# Streaming during bootstrap, repair, or topology changes.
nodetool netstats

# Help and capabilities for the exact running version.
nodetool help
~~~

Operational commands like `nodetool flush` actively generate SSTables and load; **do not run them ad-hoc on a disk-full cluster** just to "test the commit log". Assess impact and runbook procedures first.

On Linux, inspect the commit log filesystem after confirming the exact path:

~~~bash
df -h /var/lib/cassandra/commitlog
du -sh /var/lib/cassandra/commitlog

# Examples if tools are installed and operator is authorized:
# iostat -x 1
# lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT
~~~

`du` measures directory usage, `df` measures filesystem free space, and `iostat` shows disk await/utilization. None of these directly tell you how many mutations remain un-fsynced. Do not judge commit log health from a single space snapshot.

### 12.3. Building a Timeline to Pinpoint Root Cause

~~~text
10:00 write traffic triples
10:05 commit log bytes climb without dropping back down
10:07 memtable flush backlog grows
10:09 compaction/streaming also consume disk I/O
10:12 write p99 spikes and timeouts appear
10:15 commit log filesystem hits 8% free

Hypothesis to verify:
  flushing bottlenecked -> segments cannot be reclaimed
  -> commit log grows -> disk headroom drops
  -> read/write latency and errors increase
~~~

This illustrates an analysis chain, **not real Cassandra logs**. Check concurrent factors such as GC, network, kernel disk errors, and volume throttling.

## 13. CQL and Java Examples: A Successful Operation Does Not Replace Durability Goals

### 13.1. Writing Data by Partition Key

In the illustrative `telemetry_demo` keyspace:

~~~cql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO telemetry_demo.readings_by_device_day (
    device_id, event_day, event_time, temperature
) VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-21',
    '2026-11-21T10:15:00Z',
    24.6
);

SELECT event_time, temperature
FROM telemetry_demo.readings_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
LIMIT 10;
~~~

The partition is determined by `(device_id, event_day)`. While this structure enables efficient per-device/per-day queries, **a good partition model does not replace the commit log**. Conversely, ultra-durable storage cannot make queries lacking a partition key efficient.

### 13.2. Java Driver 4.x and Timeout Ambiguity

Example using a `CqlSession session` initialized with proper contact points/local DC:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

PreparedStatement insert = session.prepare(
    "INSERT INTO telemetry_demo.readings_by_device_day " +
    "(device_id, event_day, event_time, temperature) " +
    "VALUES (?, ?, ?, ?)"
);

UUID deviceId =
    UUID.fromString("11111111-1111-1111-1111-111111111111");
Instant eventTime = Instant.parse("2026-11-21T10:15:00Z");

BoundStatement statement = insert.bind(
        deviceId,
        LocalDate.of(2026, 11, 21),
        eventTime,
        24.6)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

session.execute(statement);
~~~

In this example, the CQL uses a deterministic key by device/day/timestamp, and writing the same value can be designed for safe retries under business semantics. However:

- **`execute` succeeding** means server/driver met the request conditions; it is not a certificate of hardware PLP or that every replica fsynced.
- **Write timeout** does not prove no replica wrote the mutation. Some ACKs may have occurred or the mutation may have been applied even though the client timed out.
- Retries require **idempotency**, stable keys, and avoiding duplicated external side effects. Never blindly retry counter increments or non-idempotent mutations.
- If the service needs to know "is the accepted order durable?", the answer involves **write CL, commitlog sync, replication, storage hardware, and reconciliation**, not just Java exceptions.
- The driver has no per-statement option to turn `periodic` into `batch` on replicas; that is a node-level Cassandra policy managed separately.

### 13.3. Recovering After a Crash

A restarting node can replay valid commit log entries to rebuild un-flushed memtable state. Once back online:

1. Check node health and startup/replay logs.
2. Reconcile data and replica divergence, especially after power loss or disk errors.
3. Maintain scheduled repair for anti-entropy.
4. Do not assume one successful `SELECT` proves the whole cluster holds complete data.
5. If data is lost across all replicas, use backups/upstream replay; a damaged node's commit log cannot self-recover from an unreadable device.

## 14. Runbook: Commit-Log Disk Nearly Full, Write P99 Rising

**Scenario:** A Cassandra node has only 7% free space on its commit log filesystem, write p99 jumped from 20 ms to 900 ms, hot tables are still receiving steady writes, compaction is rising, and another replica is streaming.

### Step 1 — Assess Immediate Risk

Check write timeouts/unavailables, healthy node count, application CL, I/O error logs, filesystem free bytes, and commit log growth rate. If a replica cannot write durably, assess quorum impact rather than looking only at node UP status.

### Step 2 — Quantify Fill Rate

Collect time-series `du`/`df` and commitlog segment metrics; compare incoming bytes, flush backlog, and disk write throughput. Project remaining safe runway from real measurements—**do not assume total log threshold acts as a hard cap**.

### Step 3 — Find Why Segments Are Not Reclaimed

Inspect memtable flushes, data disk latency, compaction/streaming/repair, I/O throttling, and error logs. If the data disk is very slow, even a fast commitlog disk will not let segments free on schedule.

### Step 4 — Relieve Pressure Under Control

Per operational procedures, consider throttling/pausing backfills or non-critical batch jobs, lowering concurrency, throttling streaming/repair when safe, and resolving the disk bottleneck. Avoid shifting all load onto other nodes and overloading the entire cluster.

**Never free space by manually deleting commit-log segments**, and never carelessly disable durable writes. Those actions risk losing un-flushed data.

### Step 5 — Fix Capacity / Hardware Issues

If the filesystem is filling from legitimate load, expand/adjust storage per runbook with appropriate backups, downtime/rollout windows, and restart checks. If hardware failed or logs were lost, node replacement, restore, or repair may be required depending on data/replica state; do not assume `fsck` or repeated restarts suffice.

### Step 6 — Post-Recovery Verification

Requirements:

- Commit log usage stabilizes and the filesystem retains headroom.
- Flush queues do not grow unboundedly.
- Disk latency, compaction, and streaming return within sustainable bounds.
- Write p50/p95/p99 and timeouts/unavailables drop back to SLO.
- Node health, replication, and critical data are verified.
- If a crash or replica loss occurred, RPO/RTO recovery plans are validated.

After the incident, update capacity alerts and test recovery procedures rather than applying a one-off fix and closing the incident.

## 15. When Tuning Makes Writes Faster Yet Data Less Durable

A team measures:

~~~text
Config A:
  p99 write = 18 ms
  commit log sync = periodic
  RPO across host power loss unverified

Config B:
  p99 write = 45 ms
  commit log sync = batch
  Verified persistence on PLP-backed hardware in staging

API Target:
  p99 write <= 60 ms
  ACKed data must survive single-host power loss
~~~

**In this illustrative scenario**, B may better satisfy business goals despite being slower. Still, you cannot conclude "batch is always better than periodic": if the workload includes upstream replay and RPO tolerates losing a few seconds, periodic can be an intentional choice.

What matters is **making guarantees match tested failure scenarios**:

- Which failure's loss of ACKed data does RPO tolerate?
- How many replicas sit in independent failure domains?
- Do replicas share consistent commitlog policies and storage semantics?
- After power loss, is ACKed data actually readable?
- Does commit log tail latency breach write SLOs?
- Are backups and logical-error recovery procedures in place?

A TPS benchmark measured only on a healthy cluster **cannot answer** these questions.

## 16. Misconceptions to Avoid

| Claim | True/False | Explanation |
|---|---|---|
| "Cassandra ACK means SSTables have flushed." | **False** | Normal writes can ACK once mutations reach commit log + memtable per policy |
| "Having a commit log means fsync before ACK." | **False** | Still depends on sync mode |
| "`LOCAL_QUORUM` automatically syncs every ACK to durable storage." | **False** | CL and sync policy are separate layers |
| "`durable_writes=false` only affects speed." | **False** | Un-flushed mutations can be lost after a crash |
| "The commit log is a long-term backup." | **False** | Logs are reclaimed once no longer needed for replay, not an independent backup |
| "With RF=3 we don't need backups." | **False** | Replication does not protect against accidental deletes or widespread corruption |
| "Raising commitlog_total_space prevents disk-full." | **False** | May delay flushing yet still exhaust the volume |
| "Commit log growth always means the log disk is too slow." | **False** | Un-flushed data for SSTables can also pin segments |
| "Separating log directory on the same disk definitely boosts IOPS." | **False** | Underlying hardware resources still contend |
| "A fast SSD makes fsync always safe across power loss." | **False** | Must verify PLP/cache behavior and firmware reliability |
| "Batch sync mode makes every CQL statement an ACID transaction." | **False** | Neither LWT nor multi-row ACID transactions |
| "Raising write CL fixes a failing log disk." | **False** | Cannot replace hardware or per-replica write paths |
| "Lose one replica and repair recreates every mutation regardless of peers." | **False** | Cannot repair data lost across all replicas |
| "One successful SELECT means full recovery." | **False** | Query checks only one scope, not all replicas |
| "Lowering sync interval guarantees RPO to the exact millisecond set." | **False** | Real RPO also depends on hardware, replicas, and failure domains |

## 17. Exercises with Answers

### Question 1 — ACK and Fsync

A keyspace has `durable_writes=true`, write CL=`LOCAL_QUORUM`, and commitlog sync uses `periodic`. Two replicas return ACKs. Can you guarantee both fsynced the mutation before ACKing?

**Answer:** No. Quorum indicates two replicas acknowledged along the write path; periodic mode can acknowledge before logs are forced down to durable storage. To assess durability, check sync policy and actual storage behavior.

### Question 2 — Estimating Risk in a Sync Window

A node sees 8,000 mutations/s, ~1 KiB log payload per mutation, and a hypothetical 5-second window. Roughly how much raw payload is involved?

**Answer:** About `8000 × 1 × 5 = 40000 KiB ≈ 39.1 MiB`. This is mutation volume *potentially inside the risk window*, not guaranteed lost data or a strict upper bound.

### Question 3 — Commit Log Grows Even Though Hot Table Memtable Flushed

Why can segments still not be deleted?

**Answer:** Segments can contain mutations from **multiple tables**; mutations belonging to another table's memtable may remain un-flushed/unsafe. Check node-wide flush states, not just one hot table.

### Question 4 — Impact of `durable_writes=false`

A transactional application wants higher TPS by disabling durable writes. What is the risk?

**Answer:** Un-flushed mutations lack crash recovery logging. If multiple replicas fail or no upstream replay exists, business data can be lost. Do not use this for data requiring durability just for TPS.

### Question 5 — Device with Unprotected Write Cache

Cassandra requests sync, yet the controller reports success while data still sits in volatile cache. On power loss, what risk arises?

**Answer:** Data thought to be durable can be lost. Verify flush semantics, PLP/BBU, and device/firmware correctness; RAID or UPS alone is not an absolute answer.

### Question 6 — Protection After Accidental Delete

RF=3 and batch sync are both healthy, yet an operator accidentally deletes an entire table and the DELETE replicates successfully. Can the commit log reliably restore the prior version?

**Answer:** No. The commit log is not a point-in-time backup. You need snapshots/backups, tested restores, and a business recovery strategy.

### Question 7 — Disk Full: Should You Delete Segments?

The commitlog filesystem has 2% free space and write timeouts climb. Someone proposes deleting the oldest few commit log files.

**Answer:** Never delete them manually. They may hold un-flushed mutations. Verify flush/backlogs and disk health, shed load, and follow data-safe recovery runbooks.

### Question 8 — RPO with Whole-DC Loss

A cluster has two DCs. The app writes only at `LOCAL_QUORUM` in DC1 without waiting for DC2 ACKs. DC1 fails completely right after write success. Is DC2 guaranteed to have the latest mutation?

**Answer:** No. `LOCAL_QUORUM` only ensures local DC quorum per ACK policy; DC2 may not have received it yet. Choose CL/topology/replication and failure domains matching your DC-loss RPO goal.

### Question 9 — Batch Sync and CQL Batch

Does enabling `commitlog_sync=batch` make every `INSERT` a multi-table atomic operation or CAS?

**Answer:** No. Batch sync is a log-sync policy; CQL batches and LWTs have distinct semantics. Never infer business atomicity from the word "batch".

### Question 10 — Choosing by SLO

Hypothetical benchmark A has 18 ms p99 (periodic) and B has 45 ms p99 (batch with PLP); the p99 SLO is <= 60 ms and the system must survive single-host power loss. Must you pick A just because it is faster?

**Answer:** No. B can meet both the SLO and verified durability goals. Final decisions must rest on real failure-scenario tests, topology, and risk—not TPS/p99 alone.

## 18. Summary

The commit log is a core pillar of **local write durability** in Cassandra, bridging in-memory memtable mutations and flushed SSTables. When tuning resources:

1. **Separate append, fsync, memtable flush, and CL ACK.** They are distinct milestones.
2. **Understand `periodic` vs `batch`/`group` per version:** throughput and p99 must be weighed against the data-loss risk window.
3. **Keep `durable_writes` aligned with business needs**; disabling the commit log is a durability trade-off, not simple speed tuning.
4. **Select storage by fsync latency, PLP, and failure domains**, not just advertised MB/s or IOPS.
5. **Budget disk headroom for pinned segments and flush backlogs**, especially when compaction/repair/streaming run concurrently.
6. **RF and CL do not replace durability policies and backups**; accidental deletes, corruption, and cross-DC outages need separate plans.
7. **Measure write p50/p95/p99, timeouts, free disk, commitlog bytes, and flush activity** before and after every change.
8. **Define RPO/RTO by concrete failure scenarios** and validate them through safe staging drills.

The ultimate question is not "how fast a disk should hold the commit log?", but **"when the Java application receives an ACK, which replicas hold the mutation, through what sync mechanism and hardware, and what survives the failure scenarios the business requires?"** Only when you can answer that is commit log tuning both effective and true to durability goals.
