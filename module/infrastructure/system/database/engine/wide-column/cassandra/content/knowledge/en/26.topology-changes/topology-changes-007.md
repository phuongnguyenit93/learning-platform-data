# Cleaning Up Data No Longer Within Ownership Scope

## 1. The Scenario: Nodes Were Added, So Why Are Old Nodes Still Full on Disk?

In **Apache Cassandra**, a partition is assigned a token based on its **partition key**. Tokens, replication strategy, and cluster topology determine **which replicas must store that partition**. When nodes are added, tokens shift, or topology is adjusted, the responsible replica set can change.

Suppose initially N1, N2, and N3 store partitions per RF = 2. After N4 joins the cluster and assumes certain token ranges, many partitions previously within N3's replica scope may no longer need to be stored on N3. Even though N4 received data via streaming and began serving reads/writes, **the old bytes on N3 do not necessarily vanish immediately**.

That is why the **cleanup** administrative operation exists: purging local data no longer within the scope a node must retain under current ownership. The standard tool is **`nodetool cleanup`**.

However, cleanup is **not** a command to "delete everything old", "purge tombstones quickly", or "free disk space regardless of cluster state". If run too early—before data has properly moved to the new replicas—purging can turn redundant copies into **data loss or reduced fault tolerance**.

**Lesson objectives:**

- Explain the difference between **physical data still on a node** and **data the node is still responsible for storing**.
- Identify when to consider cleanup after topology changes.
- Understand how cleanup differs from streaming, repair, compaction, TTLs, and deleting snapshots.
- Practice verifying topology, running `nodetool cleanup` in a **controlled lab**, and performing post-operation verification.
- Identify dangerous scenarios, monitoring practices, and a safe operational checklist.

**Scope:** this lesson uses standard full replicas and `NetworkTopologyStrategy`. Steps for replacing nodes, raising/lowering RF, token operations, and CLI flags may vary by Cassandra version. Never use these examples as a direct production runbook without verifying actual cluster state.

## 2. Token Ownership Differs from Presence on Disk

### 2.1. From Partition Key to Current Replicas

An example table storing device readings:

~~~sql
CREATE KEYSPACE IF NOT EXISTS topology_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 2
};

CREATE TABLE IF NOT EXISTS topology_lab.readings_by_device (
  device_id text,
  event_time timestamp,
  event_id uuid,
  reading decimal,
  PRIMARY KEY ((device_id), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

- `device_id` is the **partition key**: with a partitioner like `Murmur3Partitioner`, Cassandra computes the token from this key.
- `event_time` and `event_id` are **clustering columns**: they sort/distinguish rows **within a single partition**, without changing which replicas own the partition.
- `NetworkTopologyStrategy` with `dc1: 2` targets **two full replicas** for every partition in that DC, assuming sufficient nodes and valid topology.

In practice, Cassandra may use **virtual nodes (vnodes)**: each node owns many tokens, so its data spans many non-contiguous segments. **Token count does not equal replica count.** To know which partitions a node must store, look at the **token map + replication strategy + DC/rack placement**, not just node count or token count.

### 2.2. Four Distinct Concepts

| Concept | Meaning | Example After Adding a Node |
| --- | --- | --- |
| **Current natural replica/ownership** | Node selected by topology and RF to hold a partition | N4 and N2 are the two new target replicas for partition P. |
| **Physical data still on disk** | Local SSTables still retain bytes from prior writes/streams | N3 still has SSTables containing P even though it is no longer a target replica. |
| **Coordinator** | Node receiving the request and coordinating replicas per consistency level | N1 receives query for P even if it does not hold P itself. |
| **Temporary/pending replica during transition** | Positions involved while topology is unsettled | Handoffs may occur during bootstrap; do not draw early conclusions about redundant copies. |

**Remember:** a node **having data on disk** does not prove that node **is still a current owner**. Conversely, metadata indicating N4 is a new owner **does not automatically prove N4 has received all old data**; streaming/bootstrap completion must be verified.

## 3. Token Ring Example: Which Node Becomes "No Longer an Owner"?

To visualize this easily, suppose a DC has three nodes **A, B, C** placed on the token ring in order:

~~~text
Initial ring: A → B → C → (back to A)
RF = 2; ignoring rack/vnode details for illustration.
~~~

A partition P has a token falling **right after token A, before token B**. Using clockwise replica selection in this simplified model, the two initial replicas are **B and C**.

Then node **D** is added between A and B:

~~~text
New ring: A → D → B → C → (back to A)
For P: new target replicas = D and B.
~~~

| Stage | Target Replicas for P | Data That May Still Exist |
| --- | --- | --- |
| Before D joins | B, C | SSTables for P on B and C. |
| D bootstrapping/streaming | Transitioning to new topology | B and C may still hold P; D may have only partial data. |
| D completed data transfer and topology stabilized | D, B | D and B serve P; C **may** still retain old bytes of P. |
| C runs cleanup under valid conditions | D, B | P is no longer in C's active dataset, if C is truly no longer a replica. |

~~~mermaid
flowchart TD
    S["Before expansion: A - B - C, RF=2"] --> P["Partition P belongs to B and C"]
    P --> J["Add D between A and B"]
    J --> T["Bootstrap: stream P's data to D"]
    T --> Q{"Is D ready and topology stable?"}
    Q -->|No| W["Do not run cleanup yet"]
    Q -->|Yes| N["Target replicas for P: D and B"]
    N --> X["C still holds unneeded physical copy"]
    X --> Y["Cleanup on C can remove P"]
~~~

This example illustrates simplified replica selection. With **NTS, multiple racks, multiple DCs, and vnodes**, exact replica sets may differ from the diagram; always inspect actual topology before running cleanup.

### Cleanup Does Not Change Replication Factor

After expansion, RF is still **2**. `nodetool cleanup` neither increases nor decreases RF; it only handles **data on a node that is no longer within that node's responsibility**. Raising RF from 2 to 3 is a separate replication change requiring assurances that new replicas receive full data before declaring safety.

## 4. What Does Cleanup Actually Do Inside a Node?

Cassandra writes mutations to **memtables** and flushes them into **immutable SSTables**. One SSTable can contain many partitions spanning many token ranges. After ownership shifts, a single SSTable may contain both:

1. Partitions still within the node's scope that **must be kept**.
2. Partitions that moved to another replica set and **can be dropped from this node**.

Cleanup is a **filtering operation based on current ownership**. Because SSTable files are not updated row-by-row in place like a relational table, the process may read data, retain what belongs to the node, write new SSTables or drop unneeded SSTables, and release old files once safe.

~~~mermaid
flowchart LR
    A["Old SSTable on node C"] --> B{"Partition in C's current replica set?"}
    B -->|Yes| K["Keep data belonging to C"]
    B -->|No| D["Remove from C's active dataset"]
    K --> N["Resulting SSTable after cleanup"]
    D --> F["Old files freed once unreferenced"]
~~~

**Limitations to remember:**

- Cleanup **does not send dropped data to new nodes**; data transfer belongs to **bootstrap/streaming** and dedicated synchronization procedures.
- Cleanup **does not fix discrepancies between replicas**, nor compare timestamps/tombstones across nodes like anti-entropy repair.
- Cleanup **does not create additional replicas** and does not guarantee target replicas hold data if prior streaming failed.
- Cleanup **does not guarantee immediate disk reduction**: rewriting SSTables can require temporary space; snapshots/backups, referenced files, or background tasks can retain old bytes.
- **Removing an "excess" copy** is not equivalent to a CQL `DELETE` and does not create tombstones for data now owned by another node.

### Regarding "Reclamation"

Cleanup reclaims data because **there is no longer storage responsibility under token ownership**. This differs from **expired TTLs** or tombstones eligible for purge. Both mechanisms can affect SSTables, yet their removal criteria are completely different.

## 5. How Cleanup Differs from Commonly Confused Cassandra Operations

| Operation | Primary Goal | Does It Replace Cleanup? |
| --- | --- | --- |
| **Bootstrap/streaming** when adding a node | Transfer required data to the new replica | **No.** Old nodes may still retain unowned data after transfer. |
| **`nodetool cleanup`** | Drop local data for which the node is no longer a replica under current topology | This is the operation under discussion; does not stream data to other replicas. |
| **Anti-entropy repair** | Synchronize data differences across replicas within repair scope | **No.** Repair is not meant to purge data no longer owned by the node. |
| **Normal compaction** | Merge SSTables, optimize storage, purge eligible data/tombstones | **Not synonymous.** It is not a command to filter data by new ownership. |
| **`nodetool decommission`** | Retire a live node from the ring via a data/topology transfer workflow | **No.** Cleanup applies to **nodes still in the ring** holding leftover data. |
| **`nodetool removenode`** | Handle a no-longer-existing member per cluster procedure | **No.** That is a membership change, not merely deleting local SSTables. |
| **TTL/tombstones** | Determine expired or logically deleted data | **No.** TTL expiration does not mean a node lost ownership. |
| **Snapshot/backup** | Provide a restore point against failure/accidental deletion | **No.** Backup files can still consume disk even after successful cleanup. |
| **`clearsnapshot`** | Remove snapshots per retention policy | **No.** Clearing snapshots does not evaluate replica ownership. |

In short:

~~~text
Topology change + streaming : needed copies are transferred to new owners.
Cleanup                     : old physical copies no longer owned are dropped.
Repair                      : replicas holding data are reconciled/synchronized.
Compaction                  : local SSTables are reorganized.
Backup                      : preserves recoverability if data is lost/wrongly deleted.
~~~

These operations serve **complementary, non-interchangeable** goals.

## 6. When Should You Consider Running Cleanup?

The classic scenario is **expanding a cluster by bootstrapping new nodes**. Existing nodes previously held token ranges whose responsibility shifted to other replicas under the new topology; old data can remain on disk.

Other changes can also shift ownership, yet **you must not assume cleanup is always mandatory**:

- **Token moves or moving a node** in versions/workflows that support them: ownership can shift; consult official procedures and streaming steps.
- **Replication/topology changes across DCs or racks**: may call for redistribution/repair and conditional cleanup, yet metadata changes **do not prove new replicas already hold the data**.
- **Decommission/replace/removenode**: have dedicated coordination and data-cleanup steps; follow the exact procedure rather than substituting `cleanup` mechanically.

### Reasons That Are *Not* Sufficient for Cleanup

- `nodetool tablestats` reports large storage usage with **no ownership change**.
- A table contains heavy **tombstones** or expired TTLs.
- A replica recently went down, hit write timeouts, or returned divergent reads.
- A node is low on free disk and someone wants to "try cleanup to see if space drops".

In those cases, find the real cause: partition/bucket design, compaction, repair, backup retention, data growth, or node faults. Cleanup is not a general-purpose disk-cleaning tool.

## 7. Safety Preconditions **Before** Cleanup

**Never run cleanup while an ownership transition is incomplete.** This is the single most important rule.

### Precondition Checklist

1. **Cluster is stable:** required nodes are `UN` (Up/Normal) in `nodetool status`, with no `UJ`/joining nodes or abnormal topology transitions.
2. **Bootstrap/streaming complete:** confirmed via bootstrap progress, `nodetool netstats`, and logs/monitoring; never rely solely on seeing the new node in the list.
3. **Valid RF and placement:** `NetworkTopologyStrategy` has accurate per-DC RF; sufficient nodes/racks meet fault-tolerance requirements.
4. **New replica set received needed data:** verify streaming status and data convergence; consider repair/validation per runbook if transfer errors or missed writes occurred.
5. **No concurrent topology changes running:** never run cleanup mid-bootstrap, decommission, move, replace, or RF modification.
6. **Recovery plan ready:** backups/snapshots conform to policy and restore steps are known; remember snapshots may prevent immediate disk reduction.
7. **Sufficient resources:** adequate free disk, I/O/CPU/network, and compaction backlog headroom for maintenance; cleanup can create temporary files.
8. **Scoped execution:** identify **which nodes** and **which keyspaces/tables** actually need cleanup, along with a schedule and error/rollback plan.

~~~mermaid
flowchart TD
    A["Topology just changed"] --> B{"Did streaming/bootstrap complete?"}
    B -->|No| X["Stop: do not run cleanup yet"]
    B -->|Yes| C{"Are ring, RF, DC/rack, and replica ownership stable?"}
    C -->|No| X
    C -->|Yes| D{"Checked health, needed repair, backups, and disk?"}
    D -->|No| Y["Satisfy preconditions first"]
    D -->|Yes| E["Select each old node and table scope"]
    E --> F["Run monitored cleanup"]
    F --> G["Verify data, ownership, disk usage, and logs"]
~~~

If a node recently lost connectivity or the cluster lacks sufficient replicas for RF, the issue is not cleanup speed—it is **the safety of deleting old copies**. Resolve replica health first.

## 8. Practicing CQL and `nodetool` in a Lab Environment

### 8.1. Preparing Table and Data

This example needs a **multi-node lab** with an actual datacenter named `dc1`. Have at least three nodes before testing node addition, with RF = 2 as in section 2. Never run these steps on a production cluster.

~~~sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO topology_lab.readings_by_device
  (device_id, event_time, event_id, reading)
VALUES
  ('device-7', '2026-11-21T08:00:00Z',
   123e4567-e89b-42d3-a456-426614174001, 21.50);

INSERT INTO topology_lab.readings_by_device
  (device_id, event_time, event_id, reading)
VALUES
  ('device-8', '2026-11-21T08:05:00Z',
   123e4567-e89b-42d3-a456-426614174002, 22.75);

SELECT device_id, event_time, event_id, reading
FROM topology_lab.readings_by_device
WHERE device_id = 'device-7';
~~~

`LOCAL_QUORUM` with RF = 2 in `dc1` requires `floor(2/2)+1 = 2` replica responses. It **does not guarantee every node in the cluster** stored the same data; only the partition's target replicas per RF need to participate.

If running CQL before creating the keyspace/table, create them per section 2. `CONSISTENCY` is a **cqlsh** command, not a CQL statement sent directly by the Java Driver.

### 8.2. Inspecting State Before Bootstrap

On an appropriate Cassandra node:

~~~bash
nodetool status
nodetool ring
nodetool netstats
nodetool help cleanup
~~~

- **`status`**: inspect membership, DC/rack, and `UN`/joining/leaving states.
- **`ring`**: view token ownership; with vnodes, one node owns multiple tokens.
- **`netstats`**: view active streaming/reception; useful to confirm no incomplete data transfers remain.
- **`help cleanup`**: verify **exact syntax for the running Cassandra version**.

For the sample table with a **single-column partition key `device_id text`**, you can check expected natural endpoints for a key value using the appropriate command if supported by your version:

~~~bash
nodetool getendpoints topology_lab readings_by_device device-7
~~~

This command lets you compare expected endpoints **before/after topology changes**. It does not verify SSTable contents on each node or prove streaming finished. With composite partition keys, passing the key to the tool can be trickier; the example intentionally uses a single-column partition key for easier practice.

### 8.3. Completing Expansion via a Separate Runbook

Adding a new node is an independent workflow: configure cluster name, seeds, DC/rack, partitioner, tokens, storage, networking, and security; start bootstrap, monitor streaming, and confirm the node joined normally with valid new replica ownership.

This lesson does **not** reduce node creation to a CQL statement. Before practicing cleanup, snapshot before-and-after token map/endpoint outputs and confirm **target data transferred completely**.

### 8.4. Running Cleanup **Only After** All Preconditions Are Met

On an **old node** whose ownership changed, test cleanup on a **specific table scope** in the lab:

~~~bash
# Run ON an old node verified safe that holds unowned data.
nodetool cleanup topology_lab readings_by_device
~~~

Never run blindly on all nodes just because the command succeeded on one node. Multiple old nodes may need cleanup, yet **each node must be identified individually** against the ring and new replica sets. A newly bootstrapped node typically received data and is not the primary target for cleaning leftover post-expansion copies.

`nodetool cleanup` can target a **keyspace or a set of tables**, depending on version syntax. Use `nodetool help cleanup` to check job-parallelism flags if available; never raise job count arbitrarily since cleanup competes for I/O with reads/writes.

### 8.5. Post-Cleanup Observation and Verification

~~~bash
nodetool compactionstats
nodetool tablestats topology_lab.readings_by_device
nodetool status
nodetool getendpoints topology_lab readings_by_device device-7
~~~

Then re-run the CQL query by partition key:

~~~sql
CONSISTENCY LOCAL_QUORUM;

SELECT event_time, event_id, reading
FROM topology_lab.readings_by_device
WHERE device_id = 'device-7';
~~~

**What to verify:** the query still returns valid data, post-change natural endpoints match expected nodes, no unresolved streaming/repair errors exist, and disk usage/SSTable metrics shift reasonably over time.

**What must not be inferred:** a successful `SELECT` at `LOCAL_QUORUM` does not prove all target replicas are repaired or that no stale copies remain on any node. It only tests read results at that CL at test time.

## 9. Why Might Disk Usage Not Drop Immediately?

Cleanup may need to write **new SSTables containing partitions still owned by the node**, while old files remain referenced by active reads/compactions, snapshots, or backups. Consequently, disk usage may **not drop**—or may even **rise temporarily**—for a period.

| Symptom | Causes to Investigate | Interpretation |
| --- | --- | --- |
| Cleanup completed yet disk barely changed | Node still owns most data; little excess existed; snapshots/backups hold files | Do not assume cleanup failed. |
| Disk rises during cleanup | Writing new SSTables while old files stay until safely replaced | Ensure headroom and monitor compaction. |
| `tablestats` changes slowly | Background activity; metrics update over time | Watch trends after tasks truly complete. |
| Snapshots still consume heavy space | Hard links/snapshot retention pinning SSTable files | Purge snapshots per separate **backup policy**; never delete arbitrarily. |
| Cleanup runs long or times out | Many large SSTables, I/O saturation, high concurrency, tombstone/compaction backlog | Find bottleneck; never raise concurrency unboundedly. |
| Cleanup did not delete data on new target node | Expected: the new node **must** keep partitions per RF | Cleanup is not a cluster-wide delete. |

The share of reclaimed data **does not necessarily equal 1 / newly added node count**. Vnode layout, RF, partition sizes, data volume, rack/DC, and new replica sets give each node a different proportion.

## 10. Cleanup, Consistency Level, and Repair

Cassandra applies CL to read/write requests, such as `LOCAL_ONE` or `LOCAL_QUORUM`. Cleanup is **not a CQL statement with a consistency level**; it is an administrative operation on a node's locally stored data.

Suppose before adding N4, N3 was a replica for P. Afterward, N4 must receive P and N3 becomes a non-owner:

- If **N4 received all of P's data**, N3 can drop the portion of P it no longer owns.
- If **N4 bootstrapped incomplete data** yet N3 is cleaned up prematurely, the system can lose a valid copy or un-transferred mutations.
- If **N4 holds data yet another target replica missed writes/deletes**, cleanup does not fix that discrepancy. Scoped **repair** is the synchronization mechanism to consider.
- If **deletes/tombstones** have not converged and `gc_grace_seconds` was set too low, returning an old-data replica can cause zombies; cleanup does not replace repair or long-offline node handling.

A successful `LOCAL_QUORUM` operation only confirms the response threshold for RF and DC; it does not thoroughly verify ownership transfer or authorize immediately purging all old copies.

## 11. Java Application Integration: Cleanup Is Not an Application API

**Apache Cassandra Java Driver 4.x** applications typically need no code changes when a cluster scales properly. The driver updates topology/token map metadata and routes queries bearing a partition key to appropriate replicas per policy. Data is looked up by the same logical key even when natural endpoints change.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetSocketAddress;

public final class ReadDeviceAfterTopologyChange {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement query = session.prepare(
                "SELECT event_time, event_id, reading " +
                "FROM topology_lab.readings_by_device " +
                "WHERE device_id = ? LIMIT 20");

            BoundStatement read = query.bind("device-7")
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            for (Row row : session.execute(read)) {
                System.out.println(row.getInstant("event_time")
                    + " | " + row.getBigDecimal("reading"));
            }
        }
    }
}
~~~

**Explanation:**

1. `WHERE device_id = ?` supplies the full partition key, enabling **token-aware routing** when configuration/topology align.
2. `LOCAL_QUORUM` with RF = 2 in `dc1` requires two responses, yet **does not trigger cleanup** and does not prove new replicas finished streaming.
3. `withLocalDatacenter("dc1")` must match the real DC; `127.0.0.1` is a lab example. Production requires proper contact points, auth/TLS, and timeouts.
4. While bootstrap runs, applications may see higher latency or routing/load bumps; never handle this by having the application invoke `nodetool cleanup`.
5. Cleanup belongs to a **separately privileged operational channel**; never grant a Java API account rights to execute cluster maintenance commands just to reduce disk usage.

If the application observes inconsistent data after expansion, inspect topology, streaming, CL, timeouts, and repair. "Running cleanup one more time" is **not a remedy for missing data on replicas**.

## 12. Troubleshooting When Cleanup Behaves Unexpectedly

### 12.1. Diagnostic Checklist

1. **Did bootstrap actually finish?** Check node states and streaming sessions; never rely on a brief single-point observation.
2. **Is the token map stable?** Are any nodes joining/leaving/moving or changing RF/rack/DC concurrently?
3. **Did transferred data reach the new replicas?** Check endpoint mappings, streaming/repair logs, sample partition-key reads, and metrics.
4. **Did cleanup run on the right node?** Is this an old node that actually lost ownership of some token ranges?
5. **Were the right keyspace/tables targeted?** Running on one table does not clean every keyspace.
6. **Is disk headroom sufficient?** Are overlapping compactions, snapshots pinning files, or heavy backlogs present?
7. **Are physical files still referenced?** Distinguish active SSTables, snapshots/backups, and uncollected files.
8. **What are repair and CL outcomes?** One successful request cannot replace checking replica convergence.

### 12.2. Common Mistakes and How to Avoid Them

| Situation | What Not to Do | Proper Approach |
| --- | --- | --- |
| New D is still bootstrapping; N3 holds old data | Run cleanup immediately because copies look redundant | Wait for bootstrap/streaming completion and verify topology. |
| Old node disk did not drop after cleanup | Delete SSTable files manually | Inspect active SSTables, compaction, snapshots, and retention. |
| Low disk, cleanup drags on | Run in parallel on every node to finish faster | Size disk headroom, throttle/schedule, limit concurrent nodes and jobs. |
| New D reads missing rows | Run cleanup on other nodes to "sync" | Investigate streaming/replicas/repair; cleanup does not move data. |
| Multi-DC, NTS sets per-DC RF | Treat a single-DC ring diagram as absolute truth | Verify natural endpoints by token, rack, and DC on the real cluster. |
| A node was offline long; tombstones unrepaired | Lower `gc_grace_seconds` to go faster | Follow repair/rebuild runbooks to avoid zombie data. |
| Topology shifts again mid-cleanup | Continue assuming the old token map | Reassess safety; pause/replan for the new state. |

**If cleanup fails mid-way**, never assume data is either lost or completely clean. Inspect logs, SSTable counts, and topology/replica status before deciding to retry; different Cassandra versions handle progress/failures differently.

## 13. Self-Check Exercises with Answers

**Exercise 1.** A partition P previously had replicas B and C. After adding node D, under the new topology P belongs to B and D. Streaming to D is complete. Could C still hold P's data in SSTables?

**Answer:** **Yes.** Physical data can remain on C even though C is no longer a natural replica. Cleanup on C can drop data no longer within its responsibility once safety conditions are verified.

**Exercise 2.** After adding a node, does `nodetool cleanup` automatically copy data from old nodes to the new node?

**Answer:** **No.** Bootstrap/streaming and synchronization mechanisms handle data transfer. Cleanup only removes local data no longer owned.

**Exercise 3.** RF = 3 in `dc1`; the cluster has six nodes in that DC. How many natural replicas does a partition have, and how many responses does `LOCAL_QUORUM` require?

**Answer:** Target is **three replicas**, not six. `LOCAL_QUORUM = floor(3/2)+1 = 2`. Cleanup does not alter this number.

**Exercise 4.** While `nodetool status` still shows the new node `UJ` and `netstats` shows active streaming, should you run cleanup on old nodes to free disk immediately?

**Answer:** **No.** Data transfer and topology are not yet stable. Deleting old copies too early risks data loss/reduced fault tolerance.

**Exercise 5.** Why might cleanup succeed while filesystem usage stays almost unchanged?

**Answer:** The node may have lost very little ownership, SSTables may retain many owned partitions, background tasks may still be running, or snapshots/backups and open references still pin bytes on disk. Check metrics before concluding.

**Exercise 6.** A team proposes using `nodetool cleanup` to remove old tombstones after TTL expiration and replace repair. Is this proposal right?

**Answer:** **No.** Cleanup acts on current ownership; tombstone purging follows compaction and safety conditions, while repair reconciles replicas. Those are three distinct goals.

**Exercise 7.** Why should you not look solely at token counts when deciding which nodes need cleanup?

**Answer:** Token counts do not reveal full partition replica ownership. You must inspect token ranges, vnodes, `NetworkTopologyStrategy`, per-DC RF, and rack placement. Two nodes with identical token counts can experience different ownership shifts.

**Exercise 8.** After scaling out, a Java app still runs `SELECT ... WHERE device_id=?`. Must the partition key be changed so Cassandra routes to the new node?

**Answer:** Usually **no**, if schema and query patterns have not changed. Cassandra and the driver route using the updated token map/topology. If errors appear post-expansion, check metadata, streaming, replicas/CL, and health instead of arbitrarily changing the primary key.

## 14. Decision Workflow Before and After Cleanup

~~~mermaid
flowchart TD
    A["Cassandra topology changed"] --> B["Check RF, DC/rack, token map"]
    B --> C{"New/moved-token nodes stable and streaming done?"}
    C -->|No| D["Do not cleanup; resolve bootstrap/streaming"]
    C -->|Yes| E{"Are old nodes holding data outside ownership?"}
    E -->|No / unclear| F["Observe further; do not run out of habit"]
    E -->|Yes| G{"Backups, disk headroom, repair/health OK?"}
    G -->|No| H["Satisfy safety preconditions"]
    G -->|Yes| I["Run controlled cleanup on target nodes/tables"]
    I --> J["Monitor compaction, SSTables, and errors"]
    J --> K["Verify natural endpoints, CQL reads, and disk usage"]
    K --> L["Save logs, update runbook, and record maintenance result"]
~~~

**Remember:** after a topology change, **data ownership** may move to new replicas, yet **SSTables on old nodes may still hold unneeded physical copies**. `nodetool cleanup` reclaims those portions **after** topology and streaming stabilize. It does not replace streaming, repair, compaction, or backups. Cleanup safety depends on verifying **who must store the data, whether it reached the new owners, and whether recoverability remains intact**, never on a desire to free disk as fast as possible.
