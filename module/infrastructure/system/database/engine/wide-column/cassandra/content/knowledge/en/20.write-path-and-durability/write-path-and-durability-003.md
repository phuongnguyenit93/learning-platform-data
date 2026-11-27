# commitlog_sync Modes and Potential Data-Loss Scope

Suppose a Java application sends an `INSERT` to Apache Cassandra at consistency level `QUORUM` and receives **success**. If the server loses power immediately afterward, does the record survive? What if one node loses power, and what if all three replicas lose power simultaneously? The answer depends on **the commit log sync mode on each replica**, which replicas received the mutation, which data sources have already flushed, storage device characteristics, and **the failure scope**.

The focus of this lesson is the **`commitlog_sync`** parameter: it controls how and when Cassandra syncs the commit log to the storage device, directly impacting the **local ACK milestone**, write latency, and data **at risk of failing to replay after an outage**. This topic belongs to the **Write Path and Durability** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module, connecting directly to distributed architecture, partition keys, replication, consistency levels, CQL, compaction, repair, error handling, and Java integration.

> **Core rule to remember:** **An ACK per consistency level does not mean every mutation has been `fsync`ed to disk on every replica.** Under `commitlog_sync: periodic`, a replica may ACK before the next log sync. Under sync-before-ACK modes such as `batch`, the local durability boundary differs. Yet even a successful `fsync` does not replace replication, backups, or physical fault-domain planning.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish among **commit log append**, **`fsync`**, **memtable apply**, **replica ACK**, **coordinator reaching CL**, **client receiving response**, and **SSTable flush**.
2. Explain the two main modes **`periodic` and `batch`**, recognize **`group` variants where supported by the version**, and avoid blindly copying settings from another version.
3. Identify which failure modes can prevent an **ACKed-but-unsynced mutation** from replaying.
4. Contrast data loss **on one replica**, loss of **all partition copies**, and **temporary inability to observe/read**; never equate these concepts.
5. Connect `commitlog_sync` with `durable_writes`, RF, CL, `LOCAL_QUORUM`, `EACH_QUORUM`, and datacenters.
6. Understand why `commitlog_sync_period_in_ms` is not an "absolute RPO" and why `fsync` does not protect against every storage failure.
7. Practice CQL and Java Driver 4.x with writes/reads, tracing, stable timestamps, and unknown outcomes upon timeouts.
8. Analyze latency benchmarks and build a safe configuration-change checklist.

## 2. Write Path Recap: Which Milestones Does Data Cross?

For normal writes, the **coordinator** receives the request, identifies the partition's replicas via partition key/token/replication strategy, sends the mutation to them, and waits for enough ACKs to meet the consistency level (CL).

On each replica, the conceptual write path is:

```text
                  CQL INSERT / UPDATE
                          |
                          v
                   Coordinator
                  /     |      \
                 v      v       v
                R1      R2      R3   (e.g., RF=3)
                 |       |       |
               Mutation arrives at each replica
                 |
                 +----> Commit log append
                 |
                 +----> Memtable apply
                 |
                 +----> Replica ACK
                           |
             Coordinator gathers enough ACKs for CL
                           |
                           v
                    Response to client

  Later: memtable --flush--> SSTable --compaction--> new SSTable
```

**This diagram shows the flow of responsibilities, not a mandatory execution schedule for every thread or Cassandra version.** The key point is that the local write path uses the commit log and memtable when `durable_writes` is enabled; **SSTable flushing is not a default prerequisite for ACKing each mutation**.

### 2.1. Seven Distinct Events

| Event | What happened? | Does it mean the mutation is safe across all failure types? |
| --- | --- | --- |
| `A: append` | Mutation is placed into the commit log write path. | **No**; the append may still sit in buffers/OS page cache. |
| `B: memtable apply` | Data is present in the replica's memory structure. | **No**; RAM can be lost on restart/power loss. |
| `C: fsync` | The relevant commit log portion is requested to sync per filesystem/storage semantics. | Better protection against cache loss, **not immune to all device failures**. |
| `D: replica ACK` | Replica completes what the sync mode requires and responds. | Does not prove all other replicas have finished. |
| `E: coordinator meets CL` | Required number/scope of replica ACKs received. | Does not prove all replicas ACKed or all `fsync`ed. |
| `F: client receives success` | Application receives confirmation per the request's CL. | Not a multi-partition ACID transaction; does not exclude all data-loss scenarios. |
| `G: SSTable flush` | Memtable is written out as immutable SSTables. | Does not mean repaired or identical across other replicas. |

**The `commitlog_sync` mode primarily governs the relationship between `C` and `D`.** CL governs `D` and `E`. The network/coordinator governs whether `F` reaches the client. Flush/compaction belong to a separate storage lifecycle.

### 2.2. Why Is a Commit Log Needed If Memtables Exist?

Memtables allow Cassandra to handle many mutations quickly in RAM. If a node crashes before a memtable flushes, an intact commit log can be **replayed** to recover the data. If both the memtable and unsynced commit log segment are lost with no corresponding SSTable, **that replica** risks failing to recover the mutation.

This is the basis for understanding how periodic differs from batch: neither mode **eliminates the memtable**; instead, they adjust when Cassandra asks storage to sync the commit log relative to the ACK.

## 3. commitlog_sync Modes: Periodic, Batch, and Version Variants

### 3.1. `periodic` — Periodic Sync

In **`commitlog_sync: periodic`** mode, Cassandra appends mutations to the commit log and syncs the log on a **configured interval**, rather than forcing every write to wait on its own `fsync` before ACKing.

```text
Time ---------------------------------------------------->

    append M1  apply memtable  ACK M1
       |             |          |
       v             v          v
       +-------------+----------+--------+
                                         |
                                         v
                                   periodic fsync

           [M1 may have ACKed before its fsync]
```

**Consequence:** If a node suffers **power loss or an OS crash** that wipes bytes living only in unsynced cache, mutations in the un-`fsync`ed tail may **fail to replay on that node**. Mutations already flushed to SSTables or synced earlier do not share this specific risk window.

Periodic mode generally avoids per-request sync wait overhead and supports good throughput. However, the "fast ACK" is an **intentional trade-off**: a replica response does not confirm disk sync for recent mutations at every instant.

### 3.2. `batch` — ACK After Group/Batch Sync

With **`commitlog_sync: batch`**, Cassandra processes mutations using a commit log sync mechanism where **the replica ACK must wait for the corresponding sync**; writes may be grouped to amortize a single sync.

```text
Time ----------------------------------------------------->

 append M1 ----+
 append M2 ----+---- sync commit log ----> ACK M1, ACK M2
 append M3 ----+

        [ACK does not precede the batch's required sync milestone]
```

**Consequence:** Once the client receives a replica ACK in batch mode and storage honors sync semantics, the mutation has a stronger local recovery basis on **that replica** if power fails before SSTable flush. In return, write latency can include the batch window and disk sync wait; if commit log I/O is slow, p95/p99 latency can climb.

**What it does NOT mean:** batch sync does not create multi-partition transactions, guarantee every replica fsynced, or make a node immune to disk loss or corruption.

### 3.3. `group` — Where Supported by Version/Distribution

Some Cassandra versions provide **`commitlog_sync: group`**, built around **group commit**: waiting for a short window to coalesce multiple mutations, performing the sync, and then completing the corresponding ACKs. The goal is balancing sync overhead against latency.

Do not assume `group` is always available with the **exact same parameter names or defaults** in every Cassandra release. Check the official documentation and `cassandra.yaml` for your **running version**. In this lesson, when reasoning about log-loss windows, focus on two semantic patterns:

- **ACK may precede sync:** exemplified by **periodic**.
- **ACK waits for sync:** exemplified by **batch**, and by **group** in versions providing that guarantee.

If your deployment does not support group or you have not verified its behavior, **do not add unverified parameters to production** or claim group behaves identically to batch in every detail.

### 3.4. Semantic Comparison Table

| Criterion | `periodic` | `batch` | `group` (if supported) |
| --- | --- | --- | --- |
| Sync schedule | On a configured periodic interval. | When processing batches requiring sync before ACK. | Coalesces writes over a group-commit window, then syncs. |
| Can replica ACK arrive before sync of a new mutation? | **Yes.** | Under batch semantics: **no**. | Under group-commit semantics: **no**. |
| Unsynced log risk after power loss | Present for unpersisted appends. | Reduced for ACKed writes, if storage honors sync. | Reduced for ACKed writes, if storage honors sync. |
| Latency impact | Often favorable since individual ACKs do not wait on sync. | May wait on batch/sync. | May wait on group window/sync. |
| Distinct concern | Window of ACKed-but-unsynced data. | Sync latency can dominate p99. | Requires tuning group window per supported version. |
| What remains unchanged | RF/CL, memtables, SSTables, repair, backups. | RF/CL, memtables, SSTables, repair, backups. | RF/CL, memtables, SSTables, repair, backups. |

## 4. Illustrative Configuration: Do Not Mix Parameter Names Across Versions

The `commitlog_sync` setting belongs to **node configuration** (typically `cassandra.yaml`), **not** a `cqlsh` `CONSISTENCY` choice or CQL clause.

### 4.1. Periodic Example

```yaml
# cassandra.yaml — illustrative only for versions using these parameter names.
commitlog_sync: periodic
commitlog_sync_period_in_ms: 10000
```

The value `10000` represents a **nominal sync period of 10,000 ms = 10 seconds**, not a recommendation to set production to 10 seconds. Verify units, parameter names, and supported ranges for your exact Cassandra version. Because this mode allows ACKs before periodic sync, evaluate your failure model and RF design.

### 4.2. Batch Example

```yaml
# cassandra.yaml — an alternative to periodic; NEVER use both simultaneously.
commitlog_sync: batch
commitlog_sync_batch_window_in_ms: 2
```

The `2` here is **purely a syntax illustration** for versions with that parameter, not a recommended value or latency guarantee. Settings may differ in newer Cassandra releases or commercial distributions. If your version supports `group`, verify the exact group window property name in that version's config.

### 4.3. Configuration Change Checklist

Before changing `commitlog_sync`:

1. Verify the **Cassandra version** and actual `cassandra.yaml` across all nodes.
2. Identify the active mode, period/window, commit log directory, and underlying storage device type.
3. Measure baseline **write latency, throughput, commitlog fsync latency**, and flush health.
4. Explicitly state the **failure modes** to tolerate: process crash, OS crash, single-host power loss, rack loss, or DC loss.
5. Assess **CL/RF/fault domains**: how many replicas ACK and where they sit physically.
6. Test in a lab with synthetic data; never reconfigure all production nodes at once without a controlled rollout plan.
7. Document impacts on startup/replay, disk space, memtable flushes, and downstream SLAs.
8. Prepare an operational rollback plan and verify effective config after rollout.

**Warning:** A cluster whose nodes run mismatched sync configurations will have **non-uniform local protection**. A single `QUORUM` response could aggregate ACKs from replicas with different sync behaviors, so never assume a uniform durability guarantee without inspecting every node.

## 5. What Is the "Potential Data-Loss Window" Really?

When someone says **"we could lose 10 seconds of data,"** clarify:

- Which data? **ACKed mutations whose log tail is unsynced on one replica**, or **every cluster write**?
- Lost due to what? **Process crash**, **OS crash**, **host power loss**, **disk failure**, or **entire datacenter outage**?
- At what moment? **At ACK time**, when the **client receives success**, or upon **node restart**?
- Are other copies intact? Have other replicas stored/synced/flushed the mutation?
- On readback, is the data merely **not yet observable**, or truly **lost across all recoverable copies**?

### 5.1. Illustrative Periodic Timeline

Suppose the nominal sync period is 10 seconds:

```text
t=00s: commit log sync completes
t=02s: mutation M1 appended -> replica ACK
t=06s: mutation M2 appended -> replica ACK
t=08s: mutation M3 appended -> replica ACK
t=09s: host loses power, OS page cache lost
t=10s: next scheduled sync never occurs

M1/M2/M3 may lack durable log records on that replica.
Mutations synced before t=00s do not fall in this same risk window.
```

This is a **plausible scenario**, not a claim that every mutation in the window will definitely be lost: the device might have flushed part of the buffer earlier, the memtable might have flushed/synced, or other replicas might still hold the data.

### 5.2. Sync Period Is Not an Absolute RPO Bound

Setting `commitlog_sync_period_in_ms = 10000`:

- `10 seconds` is the **target sync scheduling interval** in the illustrative config.
- It does **not** guarantee in all scenarios "at most 10 seconds of data lost" at cluster scale.
- Syncs can be delayed by OS scheduling, resource contention, storage I/O stalls, or node health.
- Durability also depends on SSTable flushes, storage caches, and peer replicas.
- Application RPO must be defined and verified via concrete DR/backup/replication procedures, never copied directly from one node parameter.

**More accurate phrasing:** Under periodic mode, writes ACKed since the last durable sync point **carry local risk** if that node loses its unsynced log tail. The duration and data volume of that risk zone depend on actual sync scheduling, load, and related storage mechanics.

### 5.3. Analyzing with Set Notation

Let:

- `A_i(t)`: the set of mutations that replica `i` has **ACKed** up to time `t`.
- `D_i(t)`: the set of mutations with **locally durable recoverable state** from synced commit logs or valid SSTables on replica `i`.
- `V_i(t) = A_i(t) \setminus D_i(t)`: the set of ACKed mutations **lacking local recovery guarantees** under the storage/failure assumptions under analysis.

Under periodic mode, `V_i(t)` **can be non-empty**. Under sync-before-ACK modes, `V_i(t)` is expected to be smaller on the normal ACK path, assuming storage and sync assumptions hold.

**Do not infer:** that `V_i(t)` equals "data guaranteed to be lost." It represents **data at risk** under a log-loss scenario; it may still survive on peer replicas.

## 6. Failure Models and Potential Loss Scope

### 6.1. Process Crash While the OS Survives

When the **Cassandra process** crashes while the kernel/filesystem stays alive, the OS page cache may still retain written-but-unfsynced bytes. Depending on write mechanisms, shutdown path, filesystem, and restart timing, part of the log may still be readable/replayable.

**Do not equate a process crash with power loss.** Equally, do not promise every unfsynced append is guaranteed to replay just because the OS stayed up: corruption, file-descriptor state, storage glitches, and commit log state also matter.

### 6.2. OS Crash or Host Power Loss

When the kernel/host loses power and volatile buffers vanish, **bytes not durably synced** may be absent upon restart. This is the primary failure model that exposes the difference between periodic and sync-before-ACK modes.

Under periodic, a replica may have ACKed a mutation yet lost its unsynced commit log portion. Under batch/group waiting for sync, an ACKed mutation has a stronger local replay path **assuming the storage device honors sync requests**.

### 6.3. Total Loss of a Node's Storage Device

If both commit log and SSTables on a replica are lost due to disk failure or corruption, **`fsync` before ACK does not protect that node from complete disk loss**. You need other replicas, backups, or other recovery processes.

If commit log and data sit on separate devices, failures affect components differently. **Never conclude that fsyncing the commit log makes a node immune to disk loss.**

### 6.4. Rack Loss, Shared Power, or Full DC Outage

Two replicas on two hosts sharing a rack or power domain can be taken out by the same event. CL only counts responses **by replica set and logical scope**; it does not ensure replicas occupy independent failure domains. Placement, rack/DC topology, storage, and operations determine resilience against correlated failures.

### 6.5. Network Partition Does Not Equal Data Loss

If replicas hold data while the coordinator cannot reach them, requests may return `Unavailable` or time out. Once connectivity returns, mutations may remain intact on ACKed replicas or be delivered later via hints/repair. This is a **temporary loss of acknowledgment/observability**, not automatic proof of permanent data loss.

### 6.6. Failure Model Summary Table

| Failure | What is at risk on a replica | Relevant protections |
| --- | --- | --- |
| Cassandra process crash, OS still running | RAM state; unsynced log may remain in OS cache but should not be treated as guaranteed. | Replay of surviving commit log; flushed SSTables. |
| OS crash / host power loss | Memtable and unsynced commit log. | Commit log sync, SSTables, peer replicas. |
| Commit log disk failure | Log records on that device, even if synced. | SSTables on healthy devices, peer replicas, backups. |
| Data/SSTable disk failure | SSTables on that node; commit log may lack already-flushed data for replay. | Peer replicas, snapshots/backups/appropriate repair. |
| Node/rack loss on shared power | Multiple replicas in the same fault domain. | Multi-rack/DC placement, RF, backups, power architecture. |
| Cross-DC network split | Ability to collect cross-DC ACKs/reads; not necessarily lost bytes. | Appropriate local CL, network recovery, hints/repair. |
| Timeout or lost response | **Uncertain** how far the write progressed. | Operation IDs, idempotency, reconciliation. |

## 7. Per-Replica Durability and Cluster Durability Are Two Separate Problems

### 7.1. RF and CL Specify Copy Count and ACK Count

**Replication factor (RF)** defines how many target replicas store a partition. **Consistency level (CL)** defines how many ACKs to wait for before returning success. Example in a single DC with RF=3:

| Write CL | Required replica ACKs |
| --- | ---: |
| `ONE` | 1 |
| `TWO` | 2 |
| `QUORUM` | `floor(3/2)+1=2` |
| `ALL` | 3 |

A successful `QUORUM` request has **at least two replica ACKs**, yet **the fsync status of each replica** still depends on `commitlog_sync`. You cannot substitute "two copies definitely hit disk" for the ACK equation.

### 7.2. RF=3, CL=QUORUM Scenarios

| Scenario | Reasonable conclusion |
| --- | --- |
| R1, R2 ACKed under periodic; R3 has not ACKed. | Write met `QUORUM`; **R1/R2 may** still have unsynced log portions. |
| Only R1 lost power before sync; R2 remains alive with the mutation. | **R2 can retain the data**, so R1's local fault does not mean cluster-wide loss. |
| Both R1 and R2 lost power before sync; R3 lacks the mutation. | There is a **risk** neither ACKed replica can replay; cluster survival depends on where data actually persists. |
| R1/R2 ACKed under batch with sync complete; R3 is down. | Both ACKed copies have better local replay protection against cache loss, **not immunity to losing both disks**. |
| All three replicas lost storage devices with no backups. | No sync mode rescues data when every copy and log is physically destroyed. |

**The word "risk" matters.** You cannot claim a power failure **definitely** destroys every un-`fsync`ed mutation: the OS/device might have flushed parts earlier, or another replica may have received and flushed it.

### 7.3. `ALL` Is Not Absolute Insurance Either

An `ALL` write at RF=3 gathers all three ACKs. If all three nodes use periodic mode and simultaneously lose power before their respective syncs, a **correlated risk window** can still exist. If they occupy independent racks/DCs and do not lose power together, the probability and failure profile differ.

Saying "`ALL` means data can never be lost" overpromises beyond what CL proves. An ACK condition is not a disk-warranty or backup contract.

### 7.4. `ANY` and Hints

`ANY` is strictly for **normal writes**. Where supported, a request can be acknowledged because the coordinator/hint host stored a **hint**, even while **no target replica has ACKed**. In that case:

- Do not treat a hint as a target replica holding read-ready data.
- Durability and replay depend on the hint-storing host, its storage, and hinted handoff limits.
- A successful `ANY` write does not allow concluding that an immediate `SELECT ONE` will see the mutation.

Hinted handoff is a **best-effort** convergence helper, not a replacement for anti-entropy repair or backups.

## 8. Multi-DC: Local ACKs, Global ACKs, and Losing a Datacenter

Suppose `NetworkTopologyStrategy` has RF=3 in `dc1` and RF=3 in `dc2`:

```text
                       Partition P

    dc1: R1  R2  R3                 dc2: R4  R5  R6
          RF=3                           RF=3

        Total RF = 6, cluster-wide QUORUM = 4.
```

| Write CL | Mandatory ACK threshold | What cannot be inferred from success |
| --- | --- | --- |
| `LOCAL_ONE` in dc1 | 1 dc1 ACK. | That every dc2 replica received/synced it. |
| `LOCAL_QUORUM` in dc1 | 2 dc1 ACKs. | That dc2 achieved a quorum ACK. |
| Cluster-wide `QUORUM` | Any 4 ACKs across 6 replicas. | That each DC individually has a local quorum ACK. |
| `EACH_QUORUM` | 2 dc1 ACKs **and** 2 dc2 ACKs. | That every replica across both DCs ACKed. |
| `ALL` | 6 ACKs. | That disks/fault domains cannot fail together. |

### 8.1. LOCAL_QUORUM Does Not Mean No Remote Replication

Mutations still need to be distributed per topology to replicas in the other DC, but a `LOCAL_QUORUM` write can return success once **two replicas in the local DC** ACK. If the remote DC is isolated, applications in the healthy DC can keep writing at a local CL, though remote clients are **not guaranteed** to read the mutation immediately.

### 8.2. ACKs from Two DCs Do Not Imply fsync

If an `EACH_QUORUM` write in RF=3+3 succeeds, the coordinator received **at least two ACKs in each DC**. Yet if both DCs run periodic mode, those ACKs **may precede sync** on individual replicas. If business requirements demand surviving total power loss of an entire DC, evaluate commitlog sync, fault domains, storage, concurrent failure tolerance, and DR strategy.

### 8.3. Asymmetric RF

If `dc1 RF=5` and `dc2 RF=1`, cluster-wide `QUORUM` still requires 4 ACKs out of 6 total, and can obtain all four **solely within dc1**. Therefore, global `QUORUM` does not imply an ACKed copy in the remote DC under every topology.

### 8.4. Do Not Confuse RPO with commitlog_sync

**RPO** is the maximum acceptable data loss defined by the business when recovering from a specific outage. A periodic sync setting only characterizes **local unsynced-log risk**; it does not directly define **system-wide** RPO. A DR architecture must evaluate:

1. RF and placement across each fault domain.
2. Local durability of each ACK per `commitlog_sync`.
3. Which DCs/racks can fail simultaneously.
4. Hinted handoff/repair and convergence latency.
5. Snapshots, backups, restore testing, and application reconciliation.

Never promise "`EACH_QUORUM` always gives RPO=0" or "10-second periodic means the cluster loses at most 10 seconds."

## 9. `durable_writes`: Whether the Commit Log Is Used at All

A Cassandra keyspace has the **`durable_writes`** attribute, determining whether normal mutations are written to the commit log for that keyspace.

Lab keyspace configuration example:

```sql
CREATE KEYSPACE IF NOT EXISTS sync_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
}
AND durable_writes = true;
```

**`durable_writes = true`** enables the write path to use the commit log to recover unflushed mutations. However, it does **not** force every ACK to wait for `fsync` if the node runs in periodic mode.

**`durable_writes = false`** can bypass commit log writes for supported mutations; if a node crashes before flushing and has no commit log record to replay, the replica can lose mutations in the memtable. Never disable this to benchmark a critical business workload without understanding the risk.

### Three Interacting Settings

| Setting | Question it answers |
| --- | --- |
| Keyspace `durable_writes` | Are normal mutations recorded in the recovery commit log? |
| Node `commitlog_sync` | When is the log synced relative to the replica ACK? |
| Request RF + CL | How many replicas must ACK in which scope before the coordinator returns success? |

Never treat any one of these three settings as a substitute for the meaning of the other two.

## 10. Commit Log Segments, Replay, and SSTable Flush

The commit log is typically organized into **segments**. Segments can hold mutations from multiple tables. Memtables hold mutable data in memory; upon flushing, they create immutable SSTables on disk.

```text
      mutation ---> commit log segment 101 ----+
                                            /   \
                                      table A   table B
                                       |          |
                                     memtable A  memtable B
                                       |          |
                                     flush A    flush B
                                       |          |
                                     SSTable    SSTable

 Segment becomes eligible for reclamation only when no
 unflushed mutations still depend on it per Cassandra tracking.
```

### 10.1. Commit Log Replay

After a crash, if SSTables do not yet include mutations that were in the memtable, Cassandra can **replay intact valid commit log records** to rebuild state. Under periodic mode, log tails that were **unsynced and actually lost** during the outage cannot be replayed out of thin air.

### 10.2. Flush Protects a Different Path

Once a memtable has flushed to valid SSTables, those mutations can be recovered from SSTables without relying on the old commit log segment. Thus **the unsynced-log risk window does not mean every mutation since the last sync is definitely unpersisted**: some may already be in SSTables or on peer replicas.

### 10.3. Do Not Confuse Flush, Compaction, and Repair

- **Flush:** writes local memtable contents to an SSTable.
- **Compaction:** merges/rewrites local SSTables, processing older versions and tombstones per rules.
- **Anti-entropy repair:** compares/repairs data **across replicas**.
- **Hinted handoff:** stores/replays mutations a replica temporarily missed.

None of these mechanisms is a semantic "substitute for `fsync`"; each solves a different problem at a different time.

### 10.4. Never Delete Commit Logs Manually

A segment containing unflushed mutations for any table is still required for replay. Deleting commit logs to "free disk space" while Cassandra is running can destroy the ability to recover data. If commit log space grows, investigate **flush backlog, disk latency, capacity, and node health**—never fix it by arbitrarily deleting files.

## 11. CQL Lab: Observing What CQL Can Prove

The lab requires a dedicated Cassandra cluster with an actual DC named `dc1` and at least three nodes for RF=3. Administrative commands belong strictly in a test environment—**never induce crashes or power loss in production**.

### 11.1. Prepare the Data

```sql
CREATE KEYSPACE IF NOT EXISTS sync_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS sync_lab.event_by_id (
  event_id uuid PRIMARY KEY,
  state text,
  operation_id uuid,
  event_at timestamp
);
```

`event_id` is the partition key; all subsequent queries target the **same partition**. This makes replica thresholds easier to reason about than queries spanning multiple partitions.

### 11.2. Write/Read at QUORUM

In `cqlsh`:

```sql
CONSISTENCY QUORUM;

INSERT INTO sync_lab.event_by_id (
  event_id, state, operation_id, event_at
) VALUES (
  11111111-1111-4111-8111-111111111111,
  'RECEIVED',
  22222222-2222-4222-8222-222222222222,
  '2026-11-21 10:00:00+0000'
);

SELECT state, operation_id, WRITETIME(state)
FROM sync_lab.event_by_id
WHERE event_id = 11111111-1111-4111-8111-111111111111;
```

`CONSISTENCY QUORUM` is a **`cqlsh` command** applying to subsequent statements in the shell session. If the INSERT succeeds, the coordinator received enough ACKs for `QUORUM`. However, `WRITETIME(state)` only shows the **cell's logical timestamp**, not the `fsync` time or ACK time.

**Do not try to infer the `commitlog_sync` mode from a successful INSERT/SELECT.** CQL does not directly expose "when `fsync` completed" per cell.

### 11.3. Controlled Tracing

```sql
TRACING ON;

CONSISTENCY QUORUM;

UPDATE sync_lab.event_by_id
SET state = 'PROCESSED'
WHERE event_id = 11111111-1111-4111-8111-111111111111;

TRACING OFF;
```

Tracing can display the coordinator, messages, and latencies; **not the full `fsync` syscall history on each replica**. Never enable tracing broadly in production.

### 11.4. Observing Memtables/Flushes

From an administrative shell on **one node in the lab**:

```bash
nodetool status
nodetool tablestats sync_lab
nodetool compactionstats

# Lab only: request table flush to observe lifecycle.
nodetool flush sync_lab event_by_id

nodetool tablestats sync_lab
```

After a flush, the memtable transitions to an SSTable per node mechanics; this **does not prove** the mutation lacked durability prior to the flush, because the commit log may already have synced. Nor does it prove all replicas have flushed, since the admin command ran on the connected node.

### 11.5. How to Check Commit Log Mode

Inspect the **lab cluster's node configuration** via the operational procedure supported by your Cassandra version. Do not try changing `commitlog_sync` via CQL: it is **not** a per-statement parameter. To compare periodic vs. batch, perform two properly configured and restarted lab runs with identical workload, hardware, and RF/CL, then compare **latency/throughput/fsync metrics**, not just SELECT outputs.

## 12. Java Driver 4.x: CL Does Not Control fsync

The Java Driver application selects the **request consistency level**, while `commitlog_sync` is configured **on the Cassandra nodes**. The driver has no statement method like "`setCommitlogSync(BATCH)`" to force individual mutations to change a replica's sync mode.

The example below assumes a `CqlSession` with lab contact points, local datacenter, authentication/TLS, and a reused `PreparedStatement`:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.DriverTimeoutException;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.servererrors.UnavailableException;
import com.datastax.oss.driver.api.core.servererrors.WriteFailureException;
import com.datastax.oss.driver.api.core.servererrors.WriteTimeoutException;

import java.time.Instant;
import java.util.UUID;

public final class SyncAwareWriter {
    public enum Outcome {
        ACKNOWLEDGED_AT_CL, UNAVAILABLE, UNKNOWN
    }

    private final CqlSession session;
    private final PreparedStatement insert;

    public SyncAwareWriter(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO sync_lab.event_by_id " +
            "(event_id, state, operation_id, event_at) " +
            "VALUES (?, ?, ?, ?) USING TIMESTAMP ?");
    }

    public Outcome write(
            UUID eventId, UUID operationId,
            String state, Instant eventAt, long timestampMicros) {
        // Keep eventId, operationId, payload, and timestamp stable
        // when retrying the same business operation.
        BoundStatement request = insert
            .bind(eventId, state, operationId, eventAt, timestampMicros)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(true);
        // idempotent=true is valid only when mutation semantics truly
        // allow repetition and have no external side effects.

        try {
            session.execute(request);
            return Outcome.ACKNOWLEDGED_AT_CL;
        } catch (UnavailableException e) {
            return Outcome.UNAVAILABLE;
        } catch (WriteTimeoutException
                 | WriteFailureException
                 | DriverTimeoutException e) {
            return Outcome.UNKNOWN;
        }
    }
}
```

### 12.1. Meaning of the Java Method's Outcome

`ACKNOWLEDGED_AT_CL` means the request **was acknowledged at `LOCAL_QUORUM`**. It does **not** confirm that the two ACKing replicas ran batch sync or that new commit log entries were fsynced in periodic mode.

`UNKNOWN` means the actual outcome is unclear: the mutation may have reached some replicas or completed fully while the response was lost. Do not change `eventId`/`operationId` to retry; address idempotency, timestamps, and reconciliation.

### 12.2. Do Not Confuse Unreadable Data with Permanently Lost Data

After a successful `LOCAL_QUORUM` request in dc1, a client in dc2 reading at `LOCAL_QUORUM` may not see the mutation yet. This can simply be **cross-DC replication latency**, not proof that the mutation is missing from the ACKing replicas.

### 12.3. Possibility of Concurrent Writes

Two clients updating the same cell via normal writes can both satisfy CL; Cassandra reconciles by **timestamp** without applying compare-and-set automatically. For business invariants such as "only one client may create a reservation," use LWT (`IF NOT EXISTS`/`IF`) with an appropriate serial consistency; `commitlog_sync` does not replace Paxos.

## 13. Write Failures and Timeouts: Do Not Infer Durable Byte Counts from Responses

### 13.1. `UnavailableException`

The coordinator sees too few live replicas to satisfy CL. For example, RF=3, a `QUORUM` write needs two, but only one replica is considered UP. There is no CL success; do not conclude that older data or an earlier request disappeared.

### 13.2. `WriteTimeoutException`

The coordinator did not receive enough ACKs within the deadline. Example:

```text
R1: mutation applied, ACK reaches coordinator
R2: mutation may have applied, ACK arrives late
R3: unresponsive
CL=QUORUM, RF=3: coordinator receives 1 ACK before deadline
-> WriteTimeout
```

**Do not interpret** "received only one ACK" as "only one replica applied the mutation." The fsync status of any replicas that applied it is a **separate** question.

### 13.3. `WriteFailureException`

A replica may report an I/O/storage error while processing a mutation, preventing the request from meeting CL. Another replica may still have written successfully. If the storage error involves the commit log, raising timeouts will not fix the root cause.

### 13.4. Driver Timeout or Lost Coordinator Connection

The coordinator may have received enough ACKs while the response was lost on the network, causing a driver timeout. The application layer must not assume the request rolled back. Design for **unknown outcomes** and retry with stable IDs, avoiding counter increments, list appends, or duplicate side effects.

### 13.5. Two Layers of Questions After Any Error

| Question | Sources to inspect |
| --- | --- |
| Was the request **acknowledged at CL**? | Server/client responses, exceptions, traces, coordinator. |
| Is the mutation **recoverable under the failure model**? | Replica placement, commit log sync, SSTables, storage, backups, and post-outage state. |

A success response answers the first question at CL; answering the second requires additional assumptions and evidence.

## 14. Performance Benchmarking: Changing commitlog_sync Affects More Than Averages

When comparing periodic and batch/group in a lab, hold **schema, partition distribution, RF, CL, client concurrency, hardware, and load** constant; otherwise results will be noisy.

| Metric | Why does it matter? |
| --- | --- |
| Write p50/p95/p99 latency | Sync-waiting modes can raise tail latency, especially when disks are busy. |
| Throughput/success rate | Does the write path sustain the target load? |
| Commit log sync duration | Shows real `fsync` cost and storage jitter. |
| Commit log segment space/pressure | Is there a backlog when memtable flushes fall behind? |
| Pending flush/compaction tasks | Is background I/O competing with the commit log? |
| GC, CPU, disk IO, and queues | Avoid blaming every timeout on `commitlog_sync`. |
| Unavailable/WriteTimeout/WriteFailure | Classify actual errors rather than lumping them into "slow writes." |
| Retry rate and duplicate requests | Analyze application-side amplification. |

### A Sound Controlled Experiment

1. Use **two equivalent lab environments**, or apply configuration changes properly between runs.
2. Record the Cassandra version and support for periodic/batch/group.
3. Choose a write workload with **identical mutation shapes**, evenly distributed partition keys, and fixed request rates.
4. Keep RF/CL and concurrency limits fixed; avoid unintended hot partitions.
5. Measure latency, fsync duration, throughput, and error rate after nodes stabilize.
6. When analyzing durability, document the **failure mode** being modeled; never pull power on shared hardware.
7. State limitations clearly: a healthy benchmark **does not prove** recovery from an untested failure.

**Do not take a single p99 measurement and claim "batch is always slower than periodic by exactly X ms."** The difference depends on hardware, group window, concurrent write volume, and specific workload.

## 15. Real-World Business Scenarios

### Scenario A — Reconstructible Telemetry

A system stores measurements whose source of truth lives in a durable stream outside Cassandra. A small amount of unsynced data on one replica can be **replayed** by event ID. Throughput can be prioritized with periodic mode while still accounting for cluster availability, deduplication, and correlated failure risk.

**Do not assume:** telemetry is always low-priority. A safety alerting stream may tolerate neither lag nor data loss.

### Scenario B — Critical Transaction State

A payment API needs to know clearly when a write state was accepted and must never create two transactions on retry. Switching to `batch` alone is insufficient: you need **operation IDs**, idempotency rules, CL/fault-domain policies, proper business-level transactions, and timeout reconciliation.

### Scenario C — Three Periodic Replicas Sharing Power

RF=3, client `ALL` write succeeds, yet all three nodes share a power source and hold unsynced mutations. A single power outage creates risk of a **correlated failure across all ACKed copies**.

**Lesson:** Choosing `ALL` does not substitute for placing replicas in independent fault domains; both sync and placement matter.

### Scenario D — Batch on a Slow Commit Log Disk

A cluster experiences sharp write p99 spikes when using batch mode. Metrics show commit log `fsync` is slow and erratic. Increasing memtable size will not necessarily help, because the ACK milestone **waits on commit log sync**. Investigate disk latency/storage and version-specific sync tuning.

### Scenario E — Cluster Retains Data Even When One Replica Loses Its Log

RF=3, `QUORUM` write succeeds; R1 loses power and loses its unsynced periodic log tail, while R2 still holds the mutation. Once R1 recovers, peer replicas and sync/repair mechanisms can restore its missing data.

**Lesson:** Local log loss differs from losing every copy of a partition; also distinguish data recovery from when reads can be served at CL.

### Scenario F — Periodic Window Is Not an SLA

A team configures 10-second periodic sync and promises "database RPO is 10 seconds across all outages." That promise lacks foundation: it ignores failure model, fault domains, actual sync behavior, backups, replication, and restore verification.

**Lesson:** RPO is a property of **end-to-end system recovery**, not a unit conversion of one `commitlog_sync` parameter.

## 16. Exercises and Solutions

### Exercise 1 — ACK Before fsync

A node runs periodic mode; a mutation was appended to the commit log, applied to the memtable, and ACKed by the replica. Is it certain the corresponding log was `fsync`ed?

**Answer:** No. Periodic mode allows ACKs before the periodic sync cycle. If the node loses power and drops unsynced bytes, that replica may fail to replay the mutation.

### Exercise 2 — How Does Batch Differ from Periodic?

Under `batch` semantics, must the replica wait for the required commit log sync before ACKing?

**Answer:** Yes. That is the core distinction from periodic. In return, write latency may incur the sync wait cost.

### Exercise 3 — 10-Second Period

Does `commitlog_sync_period_in_ms=10000` prove "the cluster loses at most exactly 10 seconds of data"?

**Answer:** No. It is a nominal node sync interval; actual loss depends on sync timing, scheduling, storage, flushing, RF/CL, surviving replicas, and failure type.

### Exercise 4 — Process Crash vs. Power Loss

Why does a Cassandra process crash with a surviving OS differ from host power loss?

**Answer:** The OS page cache can retain appended bytes when the process dies; power loss can wipe unsynced caches. Never treat both failure models as identical or assume every byte will replay.

### Exercise 5 — RF=3, QUORUM

R1 and R2 ACK under periodic mode; R3 has not ACKed. Are both guaranteed to have fsynced their commit logs?

**Answer:** No. `QUORUM` proves **two ACKs**, not fsync ordering under periodic mode.

### Exercise 6 — Only One Replica Loses Its Log

R1 loses its unsynced log tail while R2 retains the mutation. Is the mutation definitely lost from the entire cluster?

**Answer:** No. Local data loss on R1 does not mean losing all copies; assess other replicas, storage, and reconciliation/repair.

### Exercise 7 — Does ALL Protect Against Every Outage?

RF=3, an `ALL` write succeeds, yet all three replicas run periodic mode and lose power simultaneously before sync. Can you claim "zero risk of data loss"?

**Answer:** No. CL requires three ACKs, which neither guarantees all three synced nor prevents correlated outages.

### Exercise 8 — RF=3+3, EACH_QUORUM

An `EACH_QUORUM` write succeeds. Does that prove both DCs fsynced every ACK?

**Answer:** No. It proves a quorum of ACKs in each DC; local fsync still depends on the sync mode on those replicas.

### Exercise 9 — durable_writes=false

A keyspace disables the commit log for normal writes, a mutation sits only in the memtable, and the node loses power before flushing. What is the risk?

**Answer:** The mutation can be lost on that node because the memtable vanishes and no commit log record exists for replay. Other replicas may retain data, but the local copy cannot be considered durable.

### Exercise 10 — Is WRITETIME the fsync Time?

`SELECT WRITETIME(state)` returns a microsecond timestamp. Can it be used to measure commit log `fsync` or ACK timing?

**Answer:** No. `WRITETIME` is the logical timestamp attached to the winning cell, not storage sync or network response timing.

### Exercise 11 — UNKNOWN State

The coordinator receives two quorum ACKs and sends success, but the response to the Java client is lost. The driver times out. Should you assume the mutation was not written and create a new event ID?

**Answer:** No. The client outcome is unknown; creating a new event ID can create two events. Keep ID/payload/timestamp stable and reconcile per business rules.

### Exercise 12 — Segment Containing Multiple Tables' Mutations

A commit log segment holds mutations for tables A and B. A has flushed, B has not. Can the segment be deleted manually?

**Answer:** No. B still needs those records for replay; Cassandra tracks and reclaims segments automatically once no unflushed mutations depend on them.

### Exercise 13 — Flush and Repair

R1 flushed its memtable to an SSTable. Can you conclude R2/R3 hold the same data and repair is unnecessary?

**Answer:** No. Flushing is a single-node operation; repair compares replicas. An SSTable on R1 does not prove other replicas caught up.

### Exercise 14 — Total Disk Loss

A replica runs batch mode and its commit log `fsync`ed, yet both the node's commit log device and SSTable device fail. Can batch mode recover data from that node alone?

**Answer:** No. `fsync` cannot save data when the storage devices holding it are physically lost. You need other replicas or backups.

### Exercise 15 — Group Commit

One Cassandra version supports `group`. Should you blindly copy the group window parameter name from another Cassandra version without checking?

**Answer:** No. Modes, parameter names, and units can vary by version. Verify official docs and actual configuration; deploy only after measuring latency and testing the failure model.

### Exercise 16 — Lowering CL to Fix Timeouts

An API promises successful writes at `QUORUM`. On timeout, the application retries at `ONE` and returns "quorum confirmed." What is wrong?

**Answer:** `ONE` does not satisfy `QUORUM`. Retrying lower alters the ACK contract, while the first attempt's outcome may remain unknown. Never silently downgrade CL or misreport the confirmation level.

## 17. Final Checklist and Conclusion

Before claiming Cassandra data is "durable," answer:

1. **Does the keyspace set `durable_writes=true`?** Are mutations written to the commit log?
2. **Which `commitlog_sync` does the replica run?** Periodic or a sync-before-ACK mode?
3. **Have append, `fsync`, ACK, and flush been distinguished?** Those milestones are not identical.
4. **What are RF and CL?** How many replicas ACKed, and in which DC/rack?
5. **What failure model is under consideration?** Process crash, power loss, disk failure, or whole fault-domain outage?
6. **Do intact copies/SSTables/backups exist?** Losing one local commit log does not automatically mean cluster-wide loss.
7. **Are repair, hints, and recovery plans in place?** Missed or divergent data needs convergence mechanisms.
8. **Did any request time out?** Success/unknown outcomes must be reconciled against CL and operation IDs.
9. **Are there concurrent writes or anomalous timestamps?** Fsync does not resolve race conditions or last-write-wins.
10. **Have RPO/RTO been validated via DR tests?** Never derive SLAs from a nominal fsync period.

**Conclusion:** `commitlog_sync` defines one of the most critical boundaries of write durability **on each replica**. `periodic` permits ACKs before sync and carries a local risk window if the host loses unpersisted logs; `batch` and supported group-commit modes place ACKs after sync per their semantics, usually trading I/O wait cost. Yet **cluster-wide durability of a mutation** also depends on RF/CL, replica placement, failure type, SSTable flushes, repair, backups, and how applications handle timeouts.

Always distinguish **"acknowledged at CL,"** **"fsynced on a replica,"** and **"recoverable after the failure scenarios the business requires."** These three statements are not equivalent, and cannot be answered by a single parameter.

### References

- [Apache Cassandra — Storage Engine](https://cassandra.apache.org/doc/stable/cassandra/architecture/storage-engine.html): commit log, memtables, SSTables, and write path.
- [Apache Cassandra — Dynamo / Tunable Consistency](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html): RF, coordinator, replicas, and response thresholds.
- [Apache Cassandra — Configuring Cassandra](https://cassandra.apache.org/doc/stable/cassandra/configuration/cass_yaml_file.html): `commitlog_sync` parameters, sync period/window, and version-specific configuration.
- [Apache Cassandra — CQL DDL](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html): `durable_writes` and keyspace configuration.
- [Apache Cassandra — cqlsh](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html): `CONSISTENCY` and `TRACING` during practice.
- [Apache Cassandra — Hints](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/hints.html): hinted handoff for replicas that missed writes.
- [Apache Cassandra — Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html): anti-entropy repair across replicas.
