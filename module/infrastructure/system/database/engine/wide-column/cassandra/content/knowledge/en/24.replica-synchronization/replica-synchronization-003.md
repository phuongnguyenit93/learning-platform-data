# Hint Backlog, Hints Disk Usage, and Prolonged Replica Absence in Apache Cassandra

## 1. Context: Write Success Does Not Mean Every Replica Is Synchronized

Apache Cassandra is a distributed **wide-column** database that distributes data by **partition key** and replicates it according to a replication strategy. A table is normally designed around queries, while the consistency level (CL) specifies how many replicas must participate in acknowledging a read or write. Consequently, a write request can succeed even when one replica has not received the mutation.

Suppose a keyspace has **replication factor (RF) = 3** in one datacenter:

- Replicas A and B are operating normally.
- Replica C loses connectivity.
- The application writes with `LOCAL_QUORUM`, and A and B acknowledge so the command succeeds.
- C still lacks the new mutation. When C returns, it needs a way to catch up with the other replicas.

Cassandra provides **hinted handoff** to support this case. An eligible node can store a **hint** for the absent replica and later replay the mutation when the replica recovers. This mechanism helps during short outages but is **best effort**: it does not guarantee full data synchronization, does not replace anti-entropy **repair**, and does not alter consistency level ACK requirements.

This lesson belongs to the **Replica Synchronization** chapter in the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. We focus on three issues: **accumulating hint backlogs**, **growing hints disk usage**, and **replicas absent longer than the system's hint-creation window**. Examples connect to CQL, replication, error handling, and the Java driver.

## 2. How Does Hinted Handoff Participate in the Write Path?

### 2.1. A Write Scenario with a Down Replica

The coordinator receives the mutation, identifies replicas by the partition key's token, and distributes the request. If a replica is considered unavailable, Cassandra may create a hint describing the mutation to send to that replica, depending on configuration, downtime duration, and storage capacity.

~~~mermaid
sequenceDiagram
    participant J as Java Application
    participant K as Coordinator
    participant A as Replica A
    participant B as Replica B
    participant C as Replica C (down)
    J->>K: INSERT, CL=LOCAL_QUORUM
    K->>A: Send mutation
    K->>B: Send mutation
    K--xC: Replica unavailable
    A-->>K: ACK
    B-->>K: ACK
    K->>K: Store hint for C if eligible
    K-->>J: Success per LOCAL_QUORUM
    Note over C: C rejoins cluster
    K->>C: Replay still-valid hints
    C-->>K: Acknowledge receipt
~~~

This is a **logical illustration**, not a claim that every Cassandra version executes steps in the exact same order or always manages to store every hint. Mutations may be forwarded to other nodes holding hints; actual hint counts and locations depend on coordinators, replication, policies, and cluster state.

**Specifically:** a hint **is not an ACK on behalf of the target replica**. If the CL requires three ACKs and only two replicas actually acknowledge, the coordinator cannot report success merely because it stored a hint for the third replica.

### 2.2. What Is a Hint, and What Is It Not?

A hint is mutation information to replay to a target replica. Hints are normally written to the hint-holding node's hints storage area via Cassandra's dedicated file mechanism and configured path such as `hints_directory`.

A hint **is not a final snapshot** of the partition. If a row is updated multiple times while C is offline, multiple mutations may exist to replay; Cassandra still relies on timestamps, tombstones, and reconciliation rules to determine the final data.

A hint is also **not a receipt guaranteeing data reached the target replica**. A hint being stored, a hint being queued for replay, and the replica actually applying the mutation are three distinct states.

### 2.3. How Does Hinted Handoff Differ from Repair?

| Mechanism | Purpose | Limitations |
|---|---|---|
| **Hinted handoff** | Replay missed mutations to a replica | Covers only mutations with hints; depends on hint window, disk, and replay |
| **Anti-entropy repair** | Compare replicas and synchronize divergent data | Network/I/O intensive; must be scheduled and monitored |
| **Read repair** (version/config dependent) | Resolve certain discrepancies detected during reads | Does not scan partitions that are never queried |
| **Streaming / rebuild / replace** | Transfer data during node recovery or topology changes | Executed via dedicated topology procedures |
| **Compaction** | Merge SSTables on a single replica | Does not prove other replicas hold complete mutations |

Hinted handoff reduces recovery time during brief outages. Repair remains necessary to reconcile gaps lacking hints or where hints were lost.

## 3. Hint Window: Why Is Prolonged Replica Absence a Problem?

Cassandra limits the duration during which it **continues creating hints** for a replica marked absent, commonly configured via `max_hint_window_in_ms`. Once downtime exceeds this window, the system can stop creating new hints for that replica.

**Hypothetical** example with a three-hour configured window:

| Time | Event | Meaning |
|---|---|---|
| 09:00 | C goes down | Eligible writes can generate hints for C |
| 10:30 | C still down | Hint backlog keeps growing |
| 12:00 | Three hours elapsed | Subsequent mutations may no longer store hints for C |
| 14:00 | C still down | A data gap forms with no hints available to replay |
| 15:00 | C recovers | Valid hints replay, but post-window mutations may still be missing |

**Do not mistake the hint window for a fixed TTL on every hint file**, nor a promise that outages shorter than the window always recover completely. It is a threshold governing hint creation for an absent node; retention, discarding, or delivery also depend on version, configuration, system errors, and replay capacity.

The three-hour mark in the table is illustrative only, **not a mandatory default across all Cassandra clusters**. Check the actual value configured on your running cluster.

### Replica UP Does Not Mean Caught Up

A replica returning to `UP` status only means it is eligible to communicate and accept traffic per cluster health. At that moment:

1. Hints may still reside on disks across multiple coordinators.
2. The system must replay them at a controlled rate.
3. During replay, the target node may still lack earlier mutations.
4. Mutations outside the hint window or lost hints are not automatically restored by replay.

Therefore, after an outage, verify that the **backlog decreases**, **replay runs without errors**, and **repair/reconciliation is executed if needed**, rather than merely checking `nodetool status`.

## 4. How Hint Backlog Forms and Grows

**Hint backlog** is the total volume of hints still pending delivery to a target replica. It grows whenever mutations are stored as hints without yet being replayed successfully. When the node recovers, the backlog shrinks if replay throughput exceeds the rate of newly created hints.

Mental model:

~~~text
Change in backlog over time
≈ newly created hint bytes
  - successfully delivered hint bytes
  - hint bytes dropped due to management mechanisms and retention policies
~~~

Never treat a shrinking backlog caused by dropped files as proof that the replica is synchronized. Track **delivered**, **failed/dropped**, and recovery outcomes separately.

### Factors That Cause Rapid Backlog Growth

- High write rates to token ranges owned by the down replica.
- Large mutations, many columns, or large payloads.
- Multiple replicas absent simultaneously, increasing the number of hints to store.
- Prolonged outages spanning the hint window.
- Slow replay caused by a weak target node, network congestion, busy disks, or throttling.
- Compaction, streaming, and repair competing for I/O on coordinators and the target.

Cluster-wide total write rate is not necessarily the hint-generating write rate for **one specific replica**. When forecasting, filter for traffic whose target replicas include the absent node.

## 5. Estimating Hints Disk Usage

### 5.1. Approximate Formula

For a downtime interval prior to replay, you can estimate:

~~~text
Raw hint bytes
≈ eligible mutations / second
  x average hint bytes / mutation
  x seconds eligible for hint creation
  x number of down target replicas needing hints per mutation
~~~

This is a **rough estimate**, not how Cassandra allocates exact files. Real sizes include metadata, serialization/compression variance, multiple coordinators, and retry behavior. If mutations do not all target the same down replicas, do not blindly multiply by the total count of absent nodes.

### 5.2. Capacity Calculation Example

Replica C is offline and traffic generates:

- 1,000 mutations/second requiring hints for C.
- Average 2 KiB per hint.
- Three hours of downtime within the hint-creation window.
- No replay during that interval.

~~~text
Mutation count = 1,000 x 3 x 60 x 60 = 10,800,000
Hint bytes     = 10,800,000 x 2 KiB = 21,600,000 KiB
Storage        ≈ 20.6 GiB
~~~

**20.6 GiB is only raw example data**, excluding metadata, traffic spikes, new SSTables, commit logs, snapshots, compaction, or streaming. Hints can be spread across multiple hint-holding nodes; each node needs adequate headroom on the filesystem hosting `hints_directory`.

A practical budgeting rule:

~~~text
Required free disk headroom
≥ peak hint backlog per node
  + ongoing write / flush growth
  + background tasks sharing the filesystem
  + runbook safety margin
~~~

If hints reside on a dedicated volume, budget against that volume. Never sum free disk across the whole cluster to claim a single coordinator has enough space.

### 5.3. How Long Will a 12 GiB Backlog Take to Replay?

Suppose measured replay throughput is 8 MiB/s, with no new hints and no retries:

~~~text
12 GiB = 12 x 1024 MiB = 12,288 MiB
Ideal duration = 12,288 / 8
               = 1,536 seconds
               ≈ 25.6 minutes
~~~

This is an ideal calculation only. Replay is affected by throttling, network bandwidth, target node CPU/disk, slow/failed responses, and resource contention from other tasks. If the newly UP node is overloaded, replay can take much longer.

### 5.4. What Happens When Hints Fill the Disk?

- Hints consume **temporary space** while mutations may still be written normally into memtables/SSTables.
- Writing hints generates **disk write I/O**; replaying generates **disk read and network I/O**.
- Hints compete for resources with compaction, flushes, streaming, and application reads/writes.
- If space runs out or hint writes fail, hinted handoff recovery capability drops. Impact on write requests depends on version and CL; never assume every request immediately fails or definitely succeeds.

**Never delete hint files manually to free disk space.** Deleting them can discard mutations the replica never received. Modifying or discarding hints must be an operational decision paired with an appropriate repair/recovery plan.

## 6. Consistency Levels Do Not Replace Hinted Handoff and Vice Versa

Suppose one DC has RF=3 and a mutation targets A, B, C:

| State | Write CL | Success Condition | Role of Hints |
|---|---|---|---|
| A and B alive; C down | `ONE` | Can succeed with at least one ACK | May store a hint for C |
| A and B alive; C down | `LOCAL_QUORUM` | Can succeed with two ACKs in the DC | May store a hint for C |
| A and B alive; C down | `ALL` | Missing C's ACK; cannot satisfy CL | A hint does not replace an ACK |
| Only A alive; B and C down | `LOCAL_QUORUM` | Insufficient quorum | Hints do not make the write succeed |
| Only A alive; B and C down | `ONE` | Can succeed with A's ACK | If eligible, may create hints for B/C |

The table illustrates ACK conditions in a single DC; timeouts, network congestion, or overloaded nodes can still cause operations to fail even when enough nodes appear UP.

Read CLs likewise do not prove every replica has caught up. A `SELECT` at `LOCAL_QUORUM` may return the right data for the queried partition, yet it is not proof that all data on C is synchronized.

In multi-datacenter clusters, `LOCAL_QUORUM`, `QUORUM`, `EACH_QUORUM`, and per-DC hinted handoff options must be analyzed against the actual topology.

## 7. Long-Offline Replicas and Data Divergence Risks

### 7.1. Mutations Without Hints Still Need Synchronization

Outages exceeding the hint window create intervals without new hints. Hints may also be missing due to disabled features, write errors, disk pressure, topology changes, or failed replays.

When the replica returns, it may miss:

- The latest update to a row.
- A new row created during the downtime.
- A DELETE or tombstone generated while offline.
- TTL expirations or newer updates relative to stale data on that replica.

**Repair** compares replicas and synchronizes remaining differences. It is the tool to consider after prolonged outages or whenever replay cannot guarantee coverage of all mutations.

### 7.2. Why Are Tombstones and `gc_grace_seconds` Especially Critical?

DELETE and TTL operations in Cassandra can create tombstones. These deletion markers prevent old values from resurfacing when other replicas have not yet received the delete mutation.

Suppose C missed a DELETE while down. Meanwhile A and B completed compactions and eligible tombstones were purged from storage. When C comes back online, it may still hold an old value with no corresponding tombstone left on healthy replicas to mask it. The result can be **zombie data**.

Therefore:

1. Never lower `gc_grace_seconds` just to reclaim tombstones/hints faster.
2. Design repair schedules around maximum expected replica offline durations and tombstone retention policies.
3. For outages **long enough that tombstones risk having been purged before the replica returns**, do not assume "start it up and run repair" is always safe. Evaluate rebuild/replace/resync per runbook and data state before letting the old node serve traffic.
4. Repair consumes network, CPU, disk, streaming, and compaction; capacity-plan instead of running uncontrolled cluster-wide repairs.

Examine both `max_hint_window_in_ms` and `gc_grace_seconds`: the two settings serve **two different purposes**. The hint window caps hint creation opportunity; grace governs deletion marker safety. Do not treat them as one combined downtime limit.

### 7.3. Decision Rules by Absence Severity

| Scenario | Reasonable Approach |
|---|---|
| Short outage within hint window | Recover node, monitor replay, and maintain periodic repair |
| Outage near or exceeding hint window | Inspect hints; schedule repair for data not guaranteed to have replayed |
| Very long outage exceeding deletion/data safety thresholds | Assess zombie risk; may require rebuild/replace per runbook |
| Node lost data or changed identity/topology | Use node replacement and streaming procedures; do not rely solely on hints tied to the old node |

The rows above are evaluation guidelines. Decisions must rely on Cassandra version, actual configuration, recorded downtime, replica state, and repair policies.

## 8. Diagnosing Backlogs: What Should You Monitor?

### 8.1. Useful Metric Groups

| Group | What to Monitor | Purpose |
|---|---|---|
| **Capacity** | Hint bytes/files and filesystem free space | Detect disk exhaustion risk |
| **Hint creation** | Rate of hints created, broken down by node/target if available | Identify debt accumulation rate |
| **Hint delivery** | Hints delivered, failed/retried, throughput | Assess backlog drain capability |
| **Backlog age** | Timestamp of oldest hint / when backlog started if collected | Detect lingering debt |
| **Target node** | UP/DOWN, disk I/O, CPU, network, mutation latency | Know whether the node can absorb replay |
| **Background tasks** | Compaction, repair, streaming, flush | Identify I/O contention |
| **Data quality** | Repair results, outage scope, mismatches | Verify completeness post-replay |

Exact metric names in JMX, exporters, or dashboards depend on Cassandra version. When configuring alerts, verify units and exact meanings—especially since **created**, **delivered**, and **failed/dropped** may differ.

The most important indicator is not "C is currently UP" but **whether the backlog is shrinking sustainably**, plus whether data outside the hint window has been addressed.

### 8.2. Helpful Investigation Commands

Examples run on a Cassandra node with appropriate permissions:

~~~bash
# Node status by datacenter and token.
nodetool status

# Current node information.
nodetool info

# Status of streaming/rebuild/repair streaming sessions.
# Not a complete measurement tool for hinted handoff.
nodetool netstats

# Compaction competing for disk bandwidth.
nodetool compactionstats

# Check hint commands supported by your exact version.
nodetool help
~~~

On Linux, you can check actual hints directory size **after confirming the configured path**:

~~~bash
du -sh /var/lib/cassandra/hints
df -h /var/lib/cassandra/hints
~~~

`du` measures directory usage; `df` measures filesystem free space. If the cluster places `hints_directory` elsewhere, substitute the actual path. Never infer replay backlog solely from `df`.

### 8.3. Reading Logs on a Timeline

An investigation timeline might look like this:

~~~text
09:10  C marked DOWN
09:12  hint bytes begin rising on coordinators
11:40  free disk hits warning threshold
12:10  C returns UP, replay starts slowly
13:00  replay throughput increases, backlog drops
14:30  backlog is small, but post-hint-window gap still needs assessment
~~~

This is an illustrative example only. Correlate node logs, hint metrics, network, disk, and restart timestamps to distinguish **failed to create hints**, **hints exist but not replayed**, **replay failing**, and **replay finished but repair needed**.

## 9. Configuration Affecting Hints and Trade-Offs

Common configuration names, subject to Cassandra version:

| Configuration | Meaning | Trade-Off |
|---|---|---|
| `hinted_handoff_enabled` | Enables the hinted handoff mechanism | Disabling increases reliance on repair to catch up |
| `max_hint_window_in_ms` | Limits how long hints are created for a down replica | Longer increases stored hint volume; shorter widens un-hinted gaps |
| `hints_directory` | Where hints are stored on the node | Needs disk headroom; avoid contention with data/commit log |
| `hinted_handoff_throttle_in_kb` or equivalent throttle | Caps delivery throughput per version | Too low: backlog drains slowly; too high: target node overloads |
| Thread count, file size, flush interval limits | How hints are written and sent | Can affect I/O, latency, and resource consumption |
| Per-datacenter policy if supported | Cross-DC hint creation scope | Affects network usage and divergence repair responsibility |

Never change settings based on defaults in a guide without verifying your Cassandra version. Specifically, increasing the hint window does not create extra disk space or replay capacity. Throttle tuning must be measured on both **sending nodes** and **receiving nodes**, alongside application p95/p99 latency.

## 10. CQL and Java Example: Writing with Proper Consistency Still Requires Repair

### 10.1. Illustrative Keyspace and Table

Assume one datacenter named `dc1` and three replicas. Actual DC names must come from cluster configuration:

~~~cql
CREATE KEYSPACE demo_sync
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE demo_sync.sensor_by_id (
    sensor_id uuid PRIMARY KEY,
    state text,
    updated_at timestamp
);
~~~

In `cqlsh`, set the write CL and execute a write:

~~~cql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO demo_sync.sensor_by_id (sensor_id, state, updated_at)
VALUES (
    11111111-1111-1111-1111-111111111111,
    'ACTIVE',
    '2026-11-21T08:00:00Z'
);

SELECT sensor_id, state, updated_at
FROM demo_sync.sensor_by_id
WHERE sensor_id = 11111111-1111-1111-1111-111111111111;
~~~

In the scenario where A/B are alive and C is down, the INSERT can succeed with `LOCAL_QUORUM`. Yet a subsequent successful SELECT **does not prove** C received the record. Hint/replay status must be verified at the operational layer, and repair remains necessary when data may be missing.

### 10.2. Java Driver 4.x

With a `CqlSession session` connected to the right keyspace/datacenter, the application can specify write consistency explicitly:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.util.UUID;

// Prepare once and reuse across the service.
PreparedStatement insert = session.prepare(
    "INSERT INTO demo_sync.sensor_by_id " +
    "(sensor_id, state, updated_at) VALUES (?, ?, ?)"
);

UUID sensorId =
    UUID.fromString("11111111-1111-1111-1111-111111111111");

BoundStatement statement = insert.bind(
        sensorId, "ACTIVE", Instant.parse("2026-11-21T08:00:00Z"))
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

session.execute(statement);
~~~

If the statement throws no exception, the client knows the request was processed per its write consistency and driver/server protocol. That **does not mean all replicas are synchronized**, and this API does not return hint backlog status.

Conversely, on a write timeout or connection loss, do not conclude with certainty that the mutation reached zero replicas. Design retries with stable keys and deduplication-safe side effects; store an operation ID when business logic requires it; monitor errors in both the service and Cassandra layers.

This driver example is a **regular write**, not an LWT. `LOCAL_QUORUM` defines ACK requirements, not compare-and-set or repair of replicas that missed earlier mutations.

### 10.3. Query and Partition Design Still Matters

A table serving queries by `sensor_id` can read a partition accurately by primary key. However, such a query cannot verify that entire token ranges are synchronized. If a node was offline for a long time, do not scan the whole table from Java just to check: use repair and appropriate monitoring tools.

## 11. Runbook: Long Node Outage, Hints Disk Filling Up

**Step 1 — Determine outage scope.** Record the start time, affected nodes/targets, DC, token ranges, RF, and write CL. Correlate `nodetool status` with logs, write timeouts, and infrastructure events.

**Step 2 — Measure backlog and disk headroom.** Compute hint bytes per hint-holding node, free space per filesystem, hints created/delivered rates, and incoming write rate. Check if compaction/streaming are competing for I/O.

**Step 3 — Resolve the root cause of replica downtime.** Inspect network, disk, processes, GC, capacity, and target node health. A node that just came UP while still sluggish may not handle heavy replay.

**Step 4 — Throttle replay by measurements.** Watch throughput, retries/errors, I/O, and p95/p99. When adjusting throttles or concurrency, weigh backlog size against application serving capacity; do not blast a recovering node.

**Step 5 — Plan repair or rebuild.** Compare downtime against the hint window and tombstone/`gc_grace_seconds` safety thresholds. If hints may be missing, schedule repair. If the node is dangerously stale or lost data, evaluate rebuild/replace per runbook.

**Step 6 — Verify recovery.** Confirm the backlog drops to baseline, replay errors stop growing, free disk is safe, required repairs finished, read/write latency returned to normal, and no data discrepancies remain within verification scope.

**Do not rush into:** manually deleting hint files, lowering `gc_grace_seconds`, forcing an old node to serve unverified, or merely raising write CL hoping historical data heals itself.

## 12. Scenarios and Self-Check Questions

**Scenario A.** RF=3, A and B alive, C down. Write at `LOCAL_QUORUM` succeeds. Can you infer C received the mutation?

**Answer:** No. Two ACKs satisfy the CL while C can still miss it. Hints can only help replay if eligible.

**Scenario B.** A replica was down for 5 hours with an effective 2-hour hint window. After recovery, all remaining hint files finish replaying. Is the replica guaranteed to be completely synchronized?

**Answer:** No. Mutations outside the hint window may lack hints. Repair/reconciliation is required.

**Scenario C.** 1,000 hints per second, averaging 2 KiB, generated continuously for three hours. What is the raw volume?

**Answer:** 10.8 million hints, roughly **20.6 GiB** before overhead. Measure actual disk usage on hint-holding nodes.

**Scenario D.** C is already UP, yet the hints directory keeps growing. Which causes should be checked?

**Answer:** Throttled replay, overloaded target node, slow network/disk, delivery errors/retries, or new hint generation outpacing successful delivery.

**Scenario E.** C was down for many days, missed DELETEs, and tombstones may have been purged on other replicas. Is replaying remaining hints enough?

**Answer:** No. Zombie data risk exists; assess data staleness and safe repair/rebuild/replace procedures.

**Scenario F.** RF=3, C down, CL=`ALL`. The coordinator records a hint for C. Does the command satisfy `ALL`?

**Answer:** No. A hint does not act as replica C's ACK.

## 13. Key Takeaways

Hinted handoff is a **near-outage recovery helper**, not a strong guarantee that every replica holds the latest data.

- **Hint backlog** grows with eligible mutations during downtime; it shrinks only on successful replay or when hints are discarded by management mechanisms.
- **Hints disk usage** must be measured per specific node and filesystem alongside write traffic and I/O-competing tasks.
- **Write consistency** defines ACK conditions; hints do not replace ACKs and do not prove the target replica was updated.
- **Outages longer than the hint window** can leave un-hinted data gaps requiring repair.
- **Outages too long relative to tombstone/repair safety** can cause zombie data, requiring proper rebuild/replace procedures.
- **Java clients** must design consistency, retries, and idempotency explicitly, while hint state is monitored via metrics, logs, and Cassandra operational tools.

During real incidents, combine **outage timeline, hint creation/delivery rates, backlog bytes, disk headroom, repair, and tombstone safety**. A node showing `UP` is the starting point of recovery; data completeness must be verified separately.
