# Local Durability vs. Replicated Durability

## 1. Two Layers of Durability in Apache Cassandra

When an application writes data to **Apache Cassandra**, there are two very different questions:

1. **On a single node, can the data be recovered after a process restart?** This is the question of **local durability**: commit log, memtable, SSTables, and syncing mechanisms to the storage device.
2. **If an entire node or disk disappears, does the cluster still hold a copy of the data elsewhere?** This is the question of **replicated durability**: replicas, replication factor (RF), consistency level (CL), fault domains, and synchronization across replicas.

Cassandra is a **distributed wide-column** database: the partition key determines the token, and the token plus replication strategy decides which nodes store the partition. Any node receiving a query acts as the **coordinator**, forwards the mutation to the partition's replicas, and waits for the required acknowledgments per consistency level.

A write success message does not automatically mean "every replica wrote an SSTable and every disk fsynced." To understand what a write operation guarantees, you must ask **which replicas acknowledged**, and **what level of local durable persistence each replica performed**.

**Learning outcomes after this lesson:**

- Explain the local write path via **commit log → memtable → SSTable** and the role of `fsync`.
- Distinguish the replica count per **RF** from the acknowledgment count awaited per **CL**.
- Analyze what happens on process crashes, power loss, disk failure, node loss, or datacenter outage.
- Identify the limits of hinted handoff, repair, compaction, timeouts, and retries.
- Practice CQL and the Java Driver with examples writing by partition key.

**Assumptions:** examples use standard full replicas and `NetworkTopologyStrategy`, excluding transient replication or LWT/Paxos unless noted. Commit log configuration details and processing behavior may vary across Cassandra versions.

## 2. Definition: How Does Local Durability Differ from Replicated Durability?

| Perspective | **Local** durability | **Replicated** durability |
| --- | --- | --- |
| Scope | One Cassandra node, its process, and its storage devices | Multiple replicas across distinct nodes/racks/DCs |
| Primary mechanisms | Commit log, memtable, flush to SSTables, syncing data to storage | Replication strategy, RF, coordinator distributing mutations, CL setting ACK thresholds |
| Failures tolerated | Can recover from commit log/SSTables after crash if records are durable on storage | Data can survive permanent loss of a node or disk if other replicas hold the record |
| Not solved alone | Total disk loss, node loss, storage failures losing unsynced data | Writes lost before any replica persists durably; simultaneous loss of multiple copies; accidental deletes replicated |
| Design factors | `commitlog_sync`, storage, flushes, filesystem, and fsync guarantees | Per-DC RF, rack placement, CL, repair, hints, and operations |

**Note on the word "local":** *local durability* here means durability **inside a single node**. It does **not mean** `LOCAL_ONE` or `LOCAL_QUORUM`—those two consistency levels use "LOCAL" to refer to the **coordinator's local datacenter**, saying nothing directly about whether the write was fsynced.

### Intuitive Example

Suppose a partition is stored on three nodes **N1, N2, N3**, and **N4** receives the write command from the client:

~~~mermaid
flowchart LR
    C["Java application"] --> K["N4: coordinator"]
    K --> R1["N1: replica"]
    K --> R2["N2: replica"]
    K --> R3["N3: replica"]
    R1 --> L1["Commit log + memtable N1"]
    R2 --> L2["Commit log + memtable N2"]
    R3 --> L3["Commit log + memtable N3"]
~~~

On each replica node there is **one local write path**. The set N1–N3 forms the **replication layer**. N4 can act as coordinator **without being a replica** of the partition; it is not counted as a fourth copy.

## 3. How Does a Single Replica Write Data?

### 3.1. Main Steps of the Write Path

For a normal `INSERT`, `UPDATE`, or `DELETE`, a replica receives a **mutation** sent by the coordinator. The logical write path is illustrated below:

~~~mermaid
flowchart TD
    M["Replica receives mutation"] --> C["Append to commit log"]
    M --> P["Update memtable in RAM"]
    C --> A["Eligible to send internal ACK"]
    P --> A
    P --> F["Memtable flushes later"]
    F --> S["SSTable on disk"]
    S --> X["Compaction may merge SSTables"]
    C -.-> Y["Commit log segment recycled when safe"]
    S -.-> Y
~~~

- **Commit log** is an append-only sequential journal on storage used to **replay** acknowledged mutations after an outage. It recovers data that remained in the memtable and had not yet flushed to SSTables.
- **Memtable** holds mutable data in memory so the write path avoids random in-place SSTable edits. Data in RAM alone is insufficient to guarantee survival across power loss.
- **SSTable** is an immutable data file produced when flushing a memtable; SSTables can be merged and obsolete versions purged by compaction per policy.
- **Replica ACK** confirms mutation processing per the current write path and configuration. It **does not mean the memtable has flushed to an SSTable**.

Cassandra may write commit log entries into OS buffers before bytes are actually forced down to the storage device. Therefore, distinguish **appended / accepted by the OS** from **durably synced via fsync**.

### 3.2. Commit Log Sync: Local Data-Loss Window

The `commitlog_sync` parameter in Cassandra configuration affects when the system syncs the commit log and returns ACKs. Two main modes are commonly referenced:

| Mode | Idea | Meaning for local durability |
| --- | --- | --- |
| `periodic` | Syncs the commit log to storage on a configured interval; writes do not wait for an individual fsync per mutation | ACKs can arrive **before the next periodic sync**. On sudden power loss or buffer loss, recently ACKed writes on that node still risk loss. |
| `batch` | Batches mutations over a short window and syncs the commit log before confirming the batch | Shrinks the ACK-before-fsync window at node level but typically adds write cost/latency; still depends on OS and hardware honesty. |

Supporting parameter names, defaults, limits, and tuning behavior can vary across Cassandra releases. Never use one release's default to draw conclusions about another cluster: check the **actual configuration** and how storage honors sync requests.

**Key point:** in `periodic` mode, receiving a replica ACK does not always mean that replica's commit log has been **fsynced**. In `batch` mode, syncing before ACK strengthens local guarantees per Cassandra's design, though disk/controller failure or dishonest write-cache behavior can still lose data.

### 3.3. After a Crash, What Does Recovery Rely On?

| Scenario on **one replica** | Recovery expectation |
| --- | --- |
| Cassandra process crashes; commit log and SSTables on storage remain intact, mutations synced | On restart, Cassandra can replay the commit log to recover unflushed data. |
| Process crashes, recent data only in memtable yet corresponding commit log is durable | Old memtable is lost, but log replay can rebuild mutations. |
| Power loss before the new commit log tail is durably synced | That replica can lose some recent mutations even if it sent ACKs under a config allowing early ACKs. |
| Disk holding data/commit log is unrecoverably lost | Node-local durability cannot rescue that data; must rely on other replicas or backups. |

Flushing and compaction matter for storage management, read performance, and freeing unneeded commit log segments. They **do not replace** replication and do not mean "every ACK must wait for compaction."

## 4. Replication Factor and Consistency Level: The Second Protection Layer

Within a keyspace, **replication factor (RF)** defines the target number of replica nodes holding a partition. With `NetworkTopologyStrategy`, RF is configured **per datacenter**. **Consistency level (CL)** is the number of valid replica responses the coordinator must gather before returning a result to the client.

Example: one DC named `dc1`, at least three nodes, keyspace RF = 3. The partition for `device_id = 'sensor-9'` is stored on N1, N2, N3; N4 acts as coordinator.

~~~mermaid
sequenceDiagram
    participant App as Java client
    participant N4 as N4 coordinator
    participant N1 as N1 replica
    participant N2 as N2 replica
    participant N3 as N3 replica
    App->>N4: INSERT (LOCAL_QUORUM)
    N4->>N1: Mutation
    N4->>N2: Mutation
    N4->>N3: Mutation
    N1-->>N4: ACK
    N2-->>N4: ACK
    N4-->>App: Success, met 2/3 ACKs in dc1
    Note over N3: May not have ACKed when client sees success
    N3-->>N4: ACK (if reachable)
~~~

`LOCAL_QUORUM` requires **2 of 3** replicas in `dc1` to acknowledge. A normal write is still **sent to the entire eligible replica set**, yet the coordinator does not wait for ACKs from all replicas to satisfy this CL.

### ACK Thresholds When RF = 3 in a Single Datacenter

| Write CL | Required replica responses | Example success condition | What must NOT be inferred |
| --- | ---: | --- | --- |
| `ONE` or `LOCAL_ONE` | 1 | N1 ACKs | That N2, N3 received, applied, or fsynced the write. |
| `QUORUM` or `LOCAL_QUORUM` | 2 | N1 and N2 ACK | That N3 caught up; that N1/N2 necessarily fsynced under `periodic`. |
| `ALL` | 3 | N1, N2, N3 all ACK | That all replicas will survive forever or cannot fail simultaneously. |
| `ANY` (writes only) | May acknowledge via hint under supported Cassandra conditions | No replica directly ACKed yet write is stored as a hint | That any replica already holds data ready for an immediate `SELECT`. |

**RF is not CL.** Setting RF = 3 does not mean every write waits for three ACKs. Conversely, setting `ALL` does not create a fourth replica. Increasing RF only increases the **target** copy count, requiring sufficient eligible nodes and streaming data to new replicas.

**CL success is the condition for the coordinator to reply**, while the actual durability of each ACK still relies on local write persistence at each replica. The two protection layers complement each other but cannot fully replace each other.

## 5. Comparing Failures with Concrete Examples

Suppose RF = 3 in `dc1`, N1–N3 are full replicas of the partition, N4 is coordinator, and replicas have processed or are processing a new write.

| Outage | If only **N1** ACKed at `LOCAL_ONE` | If **N1 and N2** ACKed at `LOCAL_QUORUM` |
| --- | --- | --- |
| N1 process restarts; commit log intact and synced | N1 can recover the mutation from commit log | N1 recovers; N2 also applied the mutation |
| N1 disk lost right after ACK, before N2/N3 apply write | **May lose** the latest write version | N2 holds an ACKed copy (though N2's fsync durability still needs scrutiny) |
| N3 loses connectivity while N1/N2 are healthy | N1 can satisfy `LOCAL_ONE` | Two ACKs from N1/N2 still satisfy `LOCAL_QUORUM` |
| Both N1 and N2 are permanently lost before N3 receives write | New write risks loss if no valid copy/hint/backup remains | Even though client saw success, losing all replicas holding the write can still cause data loss |
| Simultaneous power loss before commit logs on ACKing nodes sync | Risk of losing write on N1 | Risk of losing write **on both N1 and N2** if both depend on unsynced data |

This table illustrates **record survival**, not immediate readiness to serve a `SELECT`. For instance, RF = 3 with one failed node can still satisfy `LOCAL_QUORUM` if two replicas respond, whereas if two nodes fail, `LOCAL_QUORUM` fails for lack of quorum even though one copy survives.

### Avoid Confusing Durability and Availability

- **Durability:** can an acknowledged write still be recovered after a given failure mode?
- **Availability:** can the cluster keep serving reads/writes at the requested CL while a failure is ongoing?

With RF = 3, `ALL` requires three ACKs before returning success, so a single unavailable replica causes new `ALL` writes to fail. `LOCAL_QUORUM` generally trades response count for tolerating one failed replica in the DC. `LOCAL_ONE` preserves higher availability, yet if the latest write exists on only one replica, losing that replica carries higher data risk.

### Why "RF = 3 Guarantees No Data Loss" Is False

RF = 3 does not provide absolute immunity against:

- Writes ACKed prior to `fsync` across multiple nodes followed by **simultaneous power loss**.
- Writes completing at `ONE` where the ACKing replica is permanently lost before peer replicas receive the data.
- Shared faults across the same rack, shared storage subsystem, entire datacenter, or operator mistakes.
- Erroneous `DELETE`, wrong `UPDATE`, or corruption **replicated** across replicas.
- Long periods without repair causing copies to diverge or lose safe convergence.

Replicated durability improves tolerance of **independent member** failures; actual guarantees depend on deployment topology and correlated failures.

## 6. Multiple Datacenters: Per-DC RF and `LOCAL_QUORUM` Scope

Consider the keyspace:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3,
  'dc2': 3
};
~~~

Each partition targets **3 replicas in `dc1`** and **3 replicas in `dc2`** if the topology has sufficient nodes. With a coordinator in `dc1`:

| Write CL | Condition to return success | Meaning during a DC outage |
| --- | --- | --- |
| `LOCAL_ONE` | 1 ACK in `dc1` | Does not wait for `dc2`. |
| `LOCAL_QUORUM` | 2 ACKs in `dc1` | Does not guarantee `dc2` replicas applied the write at success time. |
| `QUORUM` | 4 ACKs across all 6 replicas | Requires cluster-wide quorum; responses may span both DCs. |
| `EACH_QUORUM` (writes) | 2 ACKs in **each** DC | Requires both DCs to satisfy write conditions. |
| `ALL` | All 6 ACKs | Losing one replica can fail `ALL` requests. |

On a normal write, the coordinator may send the mutation to replicas in both `dc1` and `dc2`, yet with `LOCAL_QUORUM` it **does not wait for ACKs from `dc2`**. If `dc1` goes down right after the client receives success and before the new write reaches `dc2`, **never assume the data is recoverable in `dc2`**.

CL selection must follow **fault-tolerance goals** and cross-DC latency costs; if an ACKed write must be confirmed in more than one DC, the write policy must reflect that and the application must accept that cross-DC link loss can fail writes.

Placing replicas across **independent racks/fault domains** with proper topology lowers correlated failure risk. Merely adding nodes in the same fault domain or raising `num_tokens` does not provide equivalent DC-failure resilience.

## 7. Where Do Hints, Repair, and Backups Fit In?

| Mechanism | Purpose | Does it guarantee durability for every write? |
| --- | --- | --- |
| **Hinted handoff** | Temporarily records mutations undelivered to an unavailable replica for replay once it returns | **No.** Hints have retention windows, config limits, and operating conditions; not a full replica or repair substitute. |
| **Read repair** | When a read encounters inconsistent replicas, may reconcile and repair per mechanism/version | **No.** Covers only queried data and depends on specific repair behavior. |
| **Anti-entropy repair** | Compares and synchronizes data across replicas, especially infrequently read partitions | **Does not replace ACK-time guarantees**; essential for convergence and long-term operational safety. |
| **Compaction** | Merges and cleans SSTables on **one node** per compaction strategy | **No.** Does not create extra replicas or fix discrepancies across nodes. |
| **Snapshot/backup** | Preserves separate recovery points against operator error, corruption, or multi-replica loss | Provides restore paths, though RPO/RTO depend on backup schedules and restore drills. |

### Why Is `ANY` Not Like `ONE`?

`ONE` requires at least one real replica to respond. `ANY` is write-only; in certain situations the coordinator can return success when the mutation is recorded as a **hint** with no full replica having applied it yet. Consequently, a `SELECT` immediately after an `ANY` write may **not read the data yet**. It is not the default choice for workloads requiring immediate replica persistence.

### Replicas Protect Against Node Loss; Backups Protect Against Other Failures

Replication also propagates **accidental deletes** or **bad updates** to peer replicas. Beyond replicas, critical systems need backups, tested restore procedures, protection against correlated failures, and a recovery plan aligned to RPO/RTO targets. When changing RF or topology, monitor streaming and run appropriate repair procedures—never assume metadata changes alone finished copying older data.

## 8. CQL Practice: Same Data, Different ACK Thresholds

Lab example assumes an actual datacenter named `dc1` and **at least three Cassandra nodes** in that DC. If your deployment differs, adjust DC name/RF before running.

### 8.1. Create a Query-Driven Table

Suppose the application reads one sensor's measurements for a single day. We use a **compound partition key** `(sensor_id, event_day)` to bound partition size and keep same-day readings co-located:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry.readings_by_sensor_day (
  sensor_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  reading decimal,
  PRIMARY KEY ((sensor_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

The partition's replicas are determined by the token of the **entire partition key** `(sensor_id, event_day)` and `telemetry`'s replication settings. Changing CL changes neither the replica count nor the partition token.

### 8.2. Switch CL in cqlsh and Observe

~~~sql
CONSISTENCY LOCAL_ONE;
TRACING ON;

INSERT INTO telemetry.readings_by_sensor_day
  (sensor_id, event_day, event_time, event_id, reading)
VALUES
  ('sensor-9', '2026-11-21', '2026-11-21T03:00:00Z',
   123e4567-e89b-42d3-a456-426614174001, 21.75);

CONSISTENCY LOCAL_QUORUM;

INSERT INTO telemetry.readings_by_sensor_day
  (sensor_id, event_day, event_time, event_id, reading)
VALUES
  ('sensor-9', '2026-11-21', '2026-11-21T03:01:00Z',
   123e4567-e89b-42d3-a456-426614174002, 21.90);

SELECT event_time, event_id, reading
FROM telemetry.readings_by_sensor_day
WHERE sensor_id = 'sensor-9'
  AND event_day = '2026-11-21'
LIMIT 10;

TRACING OFF;
~~~

`CONSISTENCY` and `TRACING` are **`cqlsh` commands**, not raw CQL sent via the Java driver. Traces show the coordination path and participating endpoints (details vary by version and topology). In both `INSERT`s, data can go to **the same replica set**; the difference is **the response threshold the coordinator must wait for**.

To cross-check node states in a dedicated lab, you can run:

~~~bash
nodetool status
~~~

This command shows whether nodes are `UN`, `DN`, DC/rack, and topology details. Never treat `UN` on the coordinator as proof that enough ACKs arrived; node status is only one piece of interpreting outcomes. Do not stop nodes or simulate power outages on a production cluster to "test durability."

### 8.3. Reasoning Exercise with RF = 3

Suppose the partition's replicas are N1, N2, N3; after N1/N2 ACK while N3 has not yet ACKed:

- With `LOCAL_QUORUM`, **the write can return success** thanks to 2 ACKs in the DC.
- If N3 loses connectivity, new data can still exist on N1/N2.
- If **N1's disk is permanently lost**, N2 retains the mutation if stored under its local durability guarantees. This **differs** from when only N1 had ACKed under `LOCAL_ONE`.
- If both N1 and N2 lose unsynced data and N3 never received the write, **client success does not prevent write loss**.

## 9. From a Java Application: Setting CL per Write Statement

This is a Java Driver 4.x example using the table above. The sample fixes `event_id` for easier retry and readback verification:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.math.BigDecimal;
import java.net.InetSocketAddress;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public class WriteSensorReading {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement prepared = session.prepare(
                    "INSERT INTO telemetry.readings_by_sensor_day " +
                    "(sensor_id, event_day, event_time, event_id, reading) " +
                    "VALUES (?, ?, ?, ?, ?)");

            BoundStatement write = prepared.bind(
                    "sensor-9",
                    LocalDate.of(2026, 11, 21),
                    Instant.parse("2026-11-21T03:02:00Z"),
                    UUID.fromString("123e4567-e89b-42d3-a456-426614174003"),
                    new BigDecimal("22.10"))
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            session.execute(write);
        }
    }
}
~~~

- The driver chooses the receiving node (coordinator) per policy and metadata; Cassandra determines replicas via partition key, token, and replication strategy.
- `setConsistencyLevel(LOCAL_QUORUM)` requires enough **replica ACKs in the local datacenter**. It does **not** configure `commitlog_sync` or force every replica to `fsync` every write.
- `withLocalDatacenter("dc1")` must match the actual DC name; `127.0.0.1` is solely for a local lab.
- When a request **times out**, you cannot assume the write failed completely: some replicas may have saved the data. Before designing retries, examine **idempotency**, timestamps, stable key assignment, and the risk of duplicate writes or overwriting concurrent writes.

For a sensor measurement, the application can assign a stable `event_id` at the source and retain idempotency keys for controlled retries. Never automatically treat every `UPDATE`, counter operation, or list append as safe to repeat.

## 10. Choosing a Strategy Based on Failure Goals

| Business requirement | Design direction | Trade-off |
| --- | --- | --- |
| Minimize latency when losing very recent writes in rare outages is acceptable | Evaluate `LOCAL_ONE` alongside retry policies, backups, and benchmarking | Risk of losing the latest version if only one replica received it before failing. |
| Tolerate one replica failure in the DC and reduce single-node write risk | Sufficient RF, `LOCAL_QUORUM` for critical writes | Requires at least quorum responses; typically higher latency than `LOCAL_ONE`. |
| Require writes acknowledged across multiple DCs | Per-DC RF and cross-DC acknowledgment policy, e.g., `EACH_QUORUM` for writes | Latency and availability depend on cross-DC links. |
| Shrink window of losing ACKed writes on sudden single-node power loss | Evaluate `commitlog_sync`, storage fsync characteristics, and power-loss modes | Stricter sync carries latency/throughput cost; does not change RF. |
| Recover from accidental deletes, corruption, or multi-replica loss | Backups/snapshots stored outside the fault domain, periodic restore drills | Dedicated storage/operational overhead and separate RPO/RTO. |

### Layer-Aligned Operational Checklist

1. **On each replica:** check commit log config, storage sync latency, disk space, and disk errors; monitor flush/commit log/compaction via version-appropriate metrics.
2. **Across the cluster:** verify topology, RF, rack/DC placement, live replicas, write timeouts/unavailabilities, hinted handoff, and repair status.
3. **In the application:** choose CL per workload, configure local DC accurately, monitor latency and retries; on timeout treat writes as **potentially partially applied**.
4. **Disaster recovery:** practice restoring from backups and define clear RPO/RTO; never confuse replication with recovery history.

## 11. Self-Check Questions

**Question 1.** A replica sends an ACK while its commit log runs in `periodic` mode. Can you assert the commit log was fsynced for that write?

**Answer:** **No.** The ACK can occur before the next periodic sync. Power loss prior to that sync can lose local data.

**Question 2.** RF = 3 in one DC. A `LOCAL_QUORUM` write returns success after two ACKs. Does that prove the third replica already received the write?

**Answer:** **Not yet.** The coordinator only required two local acknowledgments. The third replica may process or catch up later.

**Question 3.** A node permanently loses its disk; prior to the outage, that node's own commit log was fully synced. Can you recover from the commit log on the lost disk?

**Answer:** **No.** Syncing protects against process crashes or power loss while storage survives; losing the disk requires relying on other replicas or backups.

**Question 4.** `dc1` has RF = 3 and `dc2` has RF = 3. A `LOCAL_QUORUM` write on a `dc1` coordinator reports success. Is the data guaranteed to exist in `dc2` at that moment?

**Answer:** **Not guaranteed.** `LOCAL_QUORUM` only requires two ACKs in `dc1`. Replicas in `dc2` may not have applied the mutation yet.

**Question 5.** An ops team increases `num_tokens` from 8 to 16 to "double durability," keeping RF = 2. Evaluate this conclusion.

**Answer:** Incorrect. Token count affects data range partitioning, not the number of copies per partition. RF remains 2; increasing copies requires changing replication settings and ensuring sufficient nodes.

**Question 6.** Data was accidentally deleted and the `DELETE` fully replicated. Can repair automatically restore data to before the deletion?

**Answer:** Normally **no**. Repair converges replicas to the current data/tombstone state; rolling back prior to a deletion requires an appropriate backup/restore strategy or business event history.

## 12. Final Mental Model

~~~mermaid
flowchart TD
    A["Client sends mutation"] --> B["Coordinator finds replicas via partition key and RF"]
    B --> C["Each replica: commit log + memtable"]
    C --> D["Local durability: sync/flush, replay capability"]
    C --> E["ACKs from replicas"]
    E --> F{"Consistency level threshold met?"}
    F -->|Yes| G["Coordinator returns success"]
    F -->|No| H["Wait further, timeout, or unavailable"]
    D --> I["Protects on process crash if log/data remain durable"]
    G --> J["Survival on node loss depends on actual copies"]
    J --> K["Repair + fault domains + backups support long-term operations"]
~~~

**Principle to remember:** `commit log + memtable/SSTable` explains **how a single replica retains data**; `RF + topology` explains **how many nodes can hold the data**; `CL` explains **how many ACKs are needed to return success**. No single layer protects against every failure. When evaluating a Cassandra write, ask: **which nodes are replicas, which replicas ACKed, how is the commit log synced, are copies in independent fault domains, and are backups available to recover from logical errors?**
