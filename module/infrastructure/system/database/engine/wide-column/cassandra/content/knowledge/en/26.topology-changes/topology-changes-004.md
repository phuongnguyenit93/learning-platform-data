# Decommission, removenode, and Choosing Based on Node State

## Lesson Objectives

In Apache Cassandra, each node holds a portion of the partition ring's **token ranges**; replicas are placed according to the **replication strategy** and **replication factor (RF)**. When you need to reduce node count or a node fails permanently, you cannot simply shut down the machine and delete its config: the cluster must update **topology**, recalculate which replicas own the data, and, when necessary, **stream data** to the remaining nodes.

The two most commonly confused administrative operations are:

- **`nodetool decommission`:** cleanly retires **a live node healthy enough to coordinate** out of the cluster in a planned way.
- **`nodetool removenode <host_id>`:** removes **a node that is already down and cannot decommission** from the cluster's membership/token metadata; surviving nodes must handle reassigning data ownership.

This lesson belongs to the **Topology Changes** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. It connects to the wide-column model, partition keys, query-driven tables, read/write consistency levels, replication, compaction, repair, error handling, and how Java applications react to topology changes.

After this lesson, you will be able to:

1. Choose between `decommission`, `removenode`, or **node replacement** based on node state and operational goals.
2. Verify RF, live node count, host ID, token ownership, disk capacity, and quorum viability before making changes.
3. Describe streaming, gossip/membership, replica placement shifts, and I/O/network costs during the transition phase.
4. Practice CQL and `nodetool` commands in a **lab scenario** with stop points and recovery plans.
5. Distinguish between **command completion**, **node disappearing from the ring**, **queryable data**, and **fully synchronized replicas**.
6. Verify data with stable markers and monitor impacts on the Java Driver.

> **Operational warning:** `decommission` and `removenode` are high-impact topology-changing operations. **Do not run them in production merely to practice.** Commands in this lesson target a lab cluster with admin access and backups; DC names, nodes, host IDs, and replacement plans must always be verified in real environments.

## 1. Token Ring, Replica Placement, and Preconditions Before Removing a Node

Cassandra uses the **partition key** to compute a token and determine the replica set responsible for a partition. With `NetworkTopologyStrategy`, replicas are distributed according to the RF configured per datacenter, factoring in snitch rack/topology placement. A joining node, a leaving node, or a node removed from metadata changes the **set of endpoints considered valid replicas** for certain token ranges.

For example, a datacenter `datacenter1` has four nodes `cass-1`, `cass-2`, `cass-3`, `cass-4`, and a keyspace sets **RF=3**. Each partition has three replicas in this datacenter; that does **not** mean all four nodes store every row. When one node leaves the ring, the remaining three nodes can assume the three replicas, **provided they have sufficient capacity and the required data to redistribute**.

| Situation | Consequence |
| --- | --- |
| Four live nodes, RF=3 | Each partition has three replicas chosen by placement; one node may not be a replica for a given partition. |
| One node temporarily down | Metadata still treats it as a member; data may be written to other replicas/hints depending on CL and config. |
| Decommission a live node | The leaving node streams required data while exiting the ring; placement shifts. |
| Removenode a dead node | Cluster removes the host ID and orchestrates streaming/rebuilding data from **surviving replicas**. |
| Only two nodes left in DC with RF=3 | No longer enough distinct nodes to place three replicas; **cannot be considered a safe scale-down** if RF3 is still needed. |

### Calculating Quorum Before Starting

In a DC with RF=3:

| Consistency Level | Acknowledgements/Replicas Required |
| --- | --- |
| `ONE` or `LOCAL_ONE` | 1 |
| `LOCAL_QUORUM` | 2 |
| `ALL` | 3 |

`LOCAL_QUORUM` requires two replicas in the local DC; reducing node count, incomplete streaming, or a concurrent fault can cause read/write timeouts or unavailable errors. `ALL` is especially sensitive to any unavailable replica.

**Keeping RF unchanged does not automatically preserve data integrity.** If some mutations were only acknowledged at `ONE` and the sole remaining copy resided on the dead node, no `removenode` command can recreate those lost bytes. You must distinguish **topology recovery** from **data recovery** via backups, event logs, or surviving replicas that still hold data.

## 2. Decision Matrix: Decommission, Removenode, or Replace?

| State and Goal | Typical Choice | Why |
| --- | --- | --- |
| Node `UN`, healthy, want to **permanently reduce node count** | `nodetool decommission` on **the leaving node itself** | Live node can coordinate ownership transfer/streaming. |
| Node `UN` but replacing hardware while **preserving cluster capacity** | **Node replacement** per version procedure | Avoids dropping RF/capacity and bootstrapping a new node from scratch. |
| Node `DN` due to transient fault, expected to be fixed and return | **Fix fault, restart**, do not rush `removenode` | Avoids altering the ring for a temporary membership interruption. |
| Node `DN` long-term, cannot run `decommission`, **decided to permanently remove** | `nodetool removenode <host_id>` from another healthy node | Dead node cannot stream or cleanly exit the ring itself. |
| Node `DN` with failed disk but need to **replace in place** and keep capacity | **Replace/rebuild** per Cassandra and topology guidance | Usually better than shrinking the cluster if capacity would be insufficient afterward. |
| Network split, `DN` seen only from one side | **Investigate network/quorum first** | Old node may still be running on the other side; removing it and letting it return is dangerous. |
| Too few nodes/racks/DCs left to meet RF or SLA | **Halt plan; add/restore capacity** | Streaming cannot conjure extra storage hardware or source data. |

**Core rule:** `decommission` is for a node that is **still running and actively leaving**; `removenode` is for a node that is **stopped and permanently removed**. **Replace** is a separate approach when you want to **maintain topology/capacity** rather than reduce node count.

Never use `removenode` as a way to "speed up" `decommission` of a healthy node. Nor should you attempt `nodetool decommission` on a down node: there is no running process there to execute it.

### Decision Flowchart

~~~mermaid
flowchart TD
    A["Need to change a Cassandra node"] --> B{"Is the node still running and stable?"}
    B -->|Yes| C{"Goal is to permanently reduce node count?"}
    C -->|Yes| D["Check RF, disk, SLA\nDecommission on the leaving node"]
    C -->|No, hardware replacement| E["Node replacement procedure"]
    B -->|No| F{"Will the node return safely?"}
    F -->|Yes| G["Fix network/host\nRestart and verify convergence"]
    F -->|No| H{"Sufficient replicas/capacity\nand reliable source data?"}
    H -->|Yes| I{"Want to preserve capacity?"}
    I -->|Yes| E
    I -->|No| J["Removenode by host ID\nfrom a live node"]
    H -->|No| K["Stop; plan restore\nor add nodes"]
~~~

## 3. Distinguishing IP Address, Host ID, and Token

A Cassandra node has multiple identifiers:

- **IP address/hostname:** used for communication or display; can change when replacing hardware.
- **Host ID:** UUID identifying the node in cluster metadata. `removenode` requires **the host ID of the node being removed**, not the IP and not a token.
- **Token(s):** determine token range positions; with virtual nodes (*vnodes*), one node typically owns multiple tokens.

On a healthy node, inspect topology information:

~~~bash
nodetool status
nodetool describecluster
~~~

Simulated partial `nodetool status` example:

~~~text
Datacenter: datacenter1
Status=Up/Down
|/ State=Normal/Leaving/Joining/Moving
--  Address       Load     Tokens  Owns (effective)  Host ID                               Rack
UN  10.0.0.11     ...      16      ...               11111111-1111-4111-8111-111111111111  rack1
UN  10.0.0.12     ...      16      ...               22222222-2222-4222-8222-222222222222  rack2
UN  10.0.0.13     ...      16      ...               33333333-3333-4333-8333-333333333333  rack3
DN  10.0.0.14     ...      16      ...               44444444-4444-4444-8444-444444444444  rack1
~~~

The IPs, host IDs, and token counts above are **purely illustrative**; never copy fake host IDs into a real environment. Column `UN` means *Up/Normal*, `DN` is *Down/Normal*, and `UL` typically represents *Up/Leaving* in `nodetool` status output. If a node is in Joining/Leaving/Moving state, never start a second topology change on your own.

Some versions support inspecting token ownership or endpoints for a key via `nodetool ring` / `nodetool getendpoints`; placement output does not prove replicas have synchronized data bytes. Always confirm the **host ID from appropriate admin sources** and log a record before running topology-altering commands.

## 4. Safety Checklist Before Changing Topology

### 4.1. Conditions to Satisfy

1. **Clear goal:** permanently shrinking the cluster, replacing hardware, or handling a temporarily disconnected node?
2. **Accurate topology:** which nodes are up/down, datacenter/rack, host IDs, token placement, snitch, and seed configuration.
3. **Replication:** inspect every relevant keyspace; `NetworkTopologyStrategy` sets RF per DC, not a single global RF.
4. **Capacity and throughput:** do remaining nodes have enough disk headroom for incoming data, compaction, commit log, streaming, and increased load?
5. **Availability:** during transition and if another node also fails, can application CLs (`LOCAL_QUORUM`, `ALL`, etc.) still meet SLA targets?
6. **Reliable data:** backups/snapshots verified, repair up to date, no essential data residing exclusively on the failed node.
7. **Cluster health:** no abnormal bootstrap/decommission/removenode/repair/streaming running or conflicting scheduled tasks.
8. **Realistic rollback:** have a plan to add/rebuild nodes, restore data, and coordinate with ops; do not assume a one-button "undo" exists.
9. **Observability:** dashboards/logs for disk, network, streaming, pending compactions, read/write p95/p99, timeouts, and errors.

~~~bash
# Read-only/inspection commands (run on appropriate live nodes).
nodetool status
nodetool describecluster
nodetool netstats
nodetool compactionstats
nodetool tpstats
~~~

Inspect replication settings via CQL:

~~~sql
SELECT keyspace_name, replication, durable_writes
FROM system_schema.keyspaces;
~~~

When a DC has only three nodes and a critical keyspace requires **RF=3**, permanently removing one node leaves only two nodes in the DC: **do not proceed with a simple scale-down**. You must add a node, choose replace, or evaluate changing RF under a separate plan; never alter RF solely to legitimize an emergency removal without assessing data durability.

### 4.2. Estimating Transition Load

Removing a node does not make total logical data disappear: other nodes must store replicas under the new RF and token ownership. Therefore resource usage on remaining nodes **can grow significantly** after data movement.

Illustrative example: four nodes have uneven disk loads, with one node holding hundreds of GiB of SSTables. You cannot simply divide "total load / three nodes" as a guarantee of enough space, because streaming operates per token/range, SSTables, and hot/cold data distribution. Compaction outputs can coexist alongside inputs; snapshots can also retain old files. Always measure the **minimum free space per node**, never rely on averages.

## 5. Lab Practice: Preparing RF=3 Across Four Nodes

Assume a **four-node lab `cass-1` through `cass-4` in `datacenter1`**, compatible versions, sufficient disk, and authorization for destructive topology operations. Do not carry `datacenter1` from this example into production if your actual DC name differs.

Create a keyspace and table for querying a specific partition:

~~~sql
CREATE KEYSPACE IF NOT EXISTS topology_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS topology_lab.probe_by_tenant (
    tenant_id text,
    bucket date,
    event_id uuid,
    marker text,
    payload text,
    PRIMARY KEY ((tenant_id, bucket), event_id)
);
~~~

- `(tenant_id, bucket)` is the **composite partition key**; all sample reads query a single partition.
- `event_id` is a clustering key with a stable UUID identifier.
- `marker` allows comparing query results against an **expected manifest stored outside Cassandra**.
- The table avoids TTL, `DELETE`, or concurrent updates in the initial test, making it easy to distinguish topology-induced row loss from business mutations.
- `IF NOT EXISTS` does not alter an existing keyspace/table. When re-running, confirm RF and schema before proceeding.

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'topology_lab';
~~~

Load data while all four nodes are `UN`. In `cqlsh`, `CONSISTENCY` is a **cqlsh client command**, not a CQL statement:

~~~text
CONSISTENCY ALL
~~~

~~~sql
INSERT INTO topology_lab.probe_by_tenant
    (tenant_id, bucket, event_id, marker, payload)
VALUES ('tenant-a', '2026-11-21',
    11111111-1111-4111-8111-111111111111,
    'baseline-A', 'first-known-event');

INSERT INTO topology_lab.probe_by_tenant
    (tenant_id, bucket, event_id, marker, payload)
VALUES ('tenant-a', '2026-11-21',
    22222222-2222-4222-8222-222222222222,
    'baseline-B', 'second-known-event');
~~~

`ALL` at RF3 requires all three replicas of each partition to acknowledge, **not** all four nodes if the fourth node is not a replica. Record `ACK_ALL` for each statement only if `cqlsh` returns success. A timeout means the outcome is **indeterminate**, never automatically assume the data was not written.

Baseline read:

~~~sql
SELECT event_id, marker, payload
FROM topology_lab.probe_by_tenant
WHERE tenant_id = 'tenant-a' AND bucket = '2026-11-21';
~~~

Expected manifest for `tenant-a/2026-11-21`:

| event_id | marker | Write Outcome |
| --- | --- | --- |
| `11111111-1111-4111-8111-111111111111` | `baseline-A` | Actual ACK/UNKNOWN received |
| `22222222-2222-4222-8222-222222222222` | `baseline-B` | Actual ACK/UNKNOWN received |

Save the manifest along with timestamps, keyspace, RF/CL, topology, host IDs, and errors in an **external cluster log**. On each re-run, change the tenant/bucket or event IDs and manifest so prior test data is not reused.

## 6. Scenario A: Decommissioning a Healthy Node

### 6.1. Preconditions

Node `cass-4` is **`UN`**, storage is healthy, and network connectivity is solid; the three nodes `cass-1..3` have enough resources to maintain RF3 after `cass-4` leaves. No other major topology change or repair is competing for resources. The goal is to **scale down from four to three nodes**, not replace one node with a new one.

### 6.2. Steps

On a live node, capture baseline:

~~~bash
nodetool status
nodetool netstats
nodetool compactionstats
~~~

Next, **run the command on `cass-4` itself—the node intended to leave the ring**:

~~~bash
# Run inside LAB cass-4, NOT on cass-1/2/3.
nodetool decommission
~~~

This process typically involves ring/gossip state transitions and **streaming required data to nodes assuming ownership**. Wait for the administrative operation to complete per logs and cluster status. A long-running command does not mean it is hung; never arbitrarily kill the process or run decommission a second time without confirming state.

~~~mermaid
sequenceDiagram
    participant Ops as Operator
    participant N4 as cass-4 (live)
    participant Cluster as Cluster
    participant Dest as Nodes receiving token ranges
    Ops->>Cluster: Check RF/disk/topology
    Ops->>N4: nodetool decommission
    N4->>Cluster: Begin leaving membership
    N4->>Dest: Stream data to transfer
    Dest-->>N4: Receive data / progress
    N4-->>Cluster: Finish leaving ring per version mechanism
    Cluster-->>Ops: Verify post-change state and data
~~~

During execution, monitor from the **remaining nodes**:

~~~bash
nodetool status
nodetool netstats
nodetool compactionstats
~~~

Expected state after completion:

- `cass-4` is no longer a normal member of the ring; **the three remaining nodes are `UN`**.
- Keyspace schema/replication remains RF3 and new placement assigns the three remaining nodes.
- Queries by partition key still return expected data when surviving replicas satisfy CL.
- Disk usage on remaining nodes rises consistently with streaming; no prolonged anomalies in timeouts, pending compactions, or disks.

**Do not treat `nodetool decommission` returning success as proof that all business data is verified.** You must check the manifest, RF/CL, streaming/compaction status, and post-change health. Removing a node does not automatically reconcile against an external source of truth.

## 7. Scenario B: removenode When a Node Is Permanently Dead

### 7.1. Situation and Preconditions

Start from **a fresh independent four-node lab copy** (`UN`, RF3); **do not run immediately after Scenario A** when the cluster already has only three nodes. Suppose `cass-4` is completely lost due to hardware failure and cannot restart or coordinate `decommission`. The cluster needs to shrink to three nodes without replacing the machine.

Before choosing `removenode`:

1. Confirm `cass-4` truly **cannot/will not return**, not merely experiencing a network partition.
2. Verify surviving replicas hold sufficient source data; if no trustworthy copy remains, restore/backfill instead of assuming you can stream from the dead node.
3. Record the **exact** host ID of `cass-4` from `nodetool status` and administrative records.
4. Verify the other three nodes are healthy with enough disk and throughput for RF3.
5. Have a plan to prevent the old node with its old data/host ID from rejoining the ring after removal.

### 7.2. Lab Simulation

On the lab Docker host, assuming the container is named `cass-4`:

~~~bash
# Kill the node ONLY in the lab; never manufacture production split-brain.
docker kill --signal=KILL cass-4
~~~

On a live node, observe:

~~~bash
nodetool status
~~~

Wait for `cass-4` to appear as `DN` (*Down/Normal*). Record its **Host ID** column. If the host ID is unclear, stop: `removenode` takes a host ID, **not an IP or the nickname cass-4**.

Run the command from **another healthy node, such as `cass-1`**, with the real host ID from status output:

~~~bash
# Replace <HOST_ID_CASS_4> with the REAL UUID; never use an example value.
nodetool removenode <HOST_ID_CASS_4>
~~~

The `nodetool status` example in section 3 shows a dummy UUID; **never pass that dummy UUID into a real command**. When removenode runs, Cassandra updates metadata/token ownership and **surviving replicas** handle transferring data needed by newly responsible nodes. Because the removed target node is down, it cannot act as a streaming source.

Monitor during execution:

~~~bash
nodetool status
nodetool netstats
nodetool compactionstats

# On nodetool versions supporting this syntax:
nodetool removenode status
~~~

`removenode status` can report removal progress; exact status details and CLI flags vary by version, so consult `nodetool help removenode` if different. If the session reports errors or hangs, **do not use force/assassinate options out of habit**: evaluate streaming, source replicas, resources, and version-specific troubleshooting guides before forcing metadata removal.

### 7.3. Never Bring the Old Node Back

Once `removenode` succeeds, cluster metadata no longer accepts the old node as a normal member. **Do not simply run `docker start cass-4` with its old data/system files**, because its identity and tokens have been removed from the ring. If you need four nodes again, follow **new node bootstrap or replace/rebuild** appropriate to topology/version, with safely synchronized data.

If the removed node missed tombstones for longer than `gc_grace_seconds`, letting it return with old SSTables also introduces **zombie data** risk. Never resolve this by manually deleting a few metadata/SSTable files and retrying.

## 8. When Should You Replace Instead of Shrinking Node Count?

**Replace** is appropriate when a node fails but the cluster **still needs the same node count and capacity**. For example:

- RF=3 across **exactly three nodes**: permanently removing one node to leave two nodes is usually not a valid way to preserve RF3.
- The three surviving nodes after a failure are already near full disk or high CPU: `removenode` may lack headroom.
- Rack/DC placement requirements cannot be met if a node is dropped: the replica slot must be preserved.

For a down node requiring replacement, the replacement procedure depends on version, seeds/snitch, IP/host ID, and startup flags; some versions use `replace_address_first_boot` or equivalent node-replacement options. **Never copy a single startup flag across every Cassandra version.** Use version-specific docs, control the old node's identity, and verify data streaming/replication preservation.

| Goal | Retire Node | Preserve Node Count/Capacity |
| --- | --- | --- |
| Healthy node | `decommission` may fit | Plan a replace; not necessarily decommission |
| Permanently failed node | `removenode` if RF/disk suffice | Replacement/rebuild from healthy replicas or backup |
| Temporarily failed, fixable node | Do not rush ring changes | Recover node, check hints/repair |

**Changing an IP does not automatically mean `removenode` is needed.** You may need node replacement, network config updates, or gossip handling; determine membership and data goals before selecting an operation.

## 9. Post-Decommission/Removenode Verification

### 9.1. Do Not Conflate Five Distinct Milestones

| Observation Milestone | Confirmed Fact | Not Yet Proven |
| --- | --- | --- |
| `nodetool` returns success | Admin command reported completion per CLI mechanics | All business data is intact |
| `nodetool status` no longer lists old node | Membership/token metadata updated | All new replicas have reconciled data bytes |
| `netstats` shows no streaming | No active streaming observed at check time | No replica divergence or historical data loss |
| `SELECT` returns marker at `LOCAL_QUORUM` | Query met CL and returned right marker | Every replica holds the marker |
| Repair completes on relevant scope + manifest reconciled | Stronger evidence of convergence and expected data | Events never written to any trusted source will be created by repair |

### 9.2. Inspecting State, Load, and Data

On a live node:

~~~bash
nodetool status
nodetool describecluster
nodetool netstats
nodetool compactionstats
~~~

In `cqlsh`:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
SELECT event_id, marker, payload
FROM topology_lab.probe_by_tenant
WHERE tenant_id = 'tenant-a'
  AND bucket = '2026-11-21';
~~~

Compare each `event_id/marker` pair against the manifest **stored outside Cassandra**. On a production cluster, perform bounded reconciliation on critical partitions/buckets rather than a full-table `SELECT COUNT(*)`, as full scans can be heavily resource-intensive.

After topology changes, schedule **repair according to version guidance and the keyspaces/ranges needing synchronization**. Repair incurs CPU, network, disk, streaming, and compaction costs; a command run on one node does not automatically prove the whole cluster is fully repaired. Never automatically run full repair across many nodes at once during peak traffic hours.

### 9.3. Read/Write Behavior Across CLs

Starting from four nodes at RF3, after cleanly removing one node to leave three healthy nodes still at RF3:

- `LOCAL_QUORUM` needs **2/3 ACKs**; verify read/write latency and timeouts under realistic load.
- `ALL` needs **3/3 ACKs**; while nodes/streaming are settling, availability may drop. Never default to raising CL to ALL as "the way to prove all data is safe".
- `LOCAL_ONE` may return data from a single replica; it is not a test of convergence across all copies.

If an earlier write **timed out**, the event may still have reached some replicas. Do not count timeouts as lost events or blindly retry non-idempotent operations. ACKed `marker` values and the business event source must be persisted separately to decide safe backfills.

## 10. Impact on Java Driver and Application Troubleshooting

Applications using Cassandra Java Driver 4.x typically rely on topology discovery, metadata, token-aware routing, and connection pools. When a node leaves the ring:

1. The driver may temporarily hit connection errors or route shifts while topology updates.
2. Read/write paths at the required CL may time out when streaming/compaction compete for resources.
3. Prepared statements and sessions can be reused; **there is no need to maintain static node lists per query** if discovery/load balancing are configured properly.
4. Do not treat every timeout as `NOT_WRITTEN`: if an operation is non-idempotent or triggers external side effects outside Cassandra, retrying can corrupt business logic.
5. Monitor latency, unavailables, timeouts, node availability, and driver metadata refresh speed.

The Java sample below verifies only **known event IDs**, avoiding full-table scans:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.LocalDate;
import java.util.Map;
import java.util.UUID;

public final class TopologyVerification {
    public enum Result { MATCH, MISSING, MISMATCH, READ_ERROR }

    private final CqlSession session;
    private final PreparedStatement select;

    public TopologyVerification(CqlSession session) {
        this.session = session;
        this.select = session.prepare(
            "SELECT marker FROM topology_lab.probe_by_tenant " +
            "WHERE tenant_id = ? AND bucket = ? AND event_id = ?");
    }

    public Result check(String tenantId, LocalDate bucket,
                        UUID eventId, String expectedMarker) {
        BoundStatement stmt = select.bind(tenantId, bucket, eventId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
        try {
            Row row = session.execute(stmt).one();
            if (row == null) {
                return Result.MISSING;
            }
            return expectedMarker.equals(row.getString("marker"))
                ? Result.MATCH : Result.MISMATCH;
        } catch (RuntimeException error) {
            System.err.printf(
                "READ_ERROR event=%s type=%s%n",
                eventId, error.getClass().getSimpleName());
            return Result.READ_ERROR;
        }
    }

    public void verifyManifest(String tenantId, LocalDate bucket,
                               Map<UUID, String> expected) {
        for (Map.Entry<UUID, String> item : expected.entrySet()) {
            Result result = check(
                tenantId, bucket, item.getKey(), item.getValue());
            System.out.printf("event=%s result=%s%n",
                item.getKey(), result);
        }
    }
}
~~~

Distinguish clearly:

- `MATCH`: value read at `LOCAL_QUORUM` matches the expected marker.
- `MISSING`: query succeeded but returned no row for that key.
- `MISMATCH`: row returned with wrong marker; investigate overwrites, timestamps, keyspace, or expected source.
- `READ_ERROR`: timeout, unavailable, or other error; **do not** count as missing rows.

This code alone does not confirm per-replica data is fully synchronized. For large manifests, apply rate and concurrency limits; CQL call volume can be high if checking event-by-event. When the goal is proving business completeness, reconciliation must rely on a trusted event source, not solely rows present in Cassandra.

## 11. Special Risks and Safe Stopping

| Signal/Risk | How to Assess | Priority Action |
| --- | --- | --- |
| Node is `DN` but not confirmed permanently dead | Check network partition, disk, service, and restart plan | Do not rush `removenode`; fix fault and recover |
| A DC has fewer nodes than RF | Placement can no longer satisfy configuration | Halt scale-down; add node or replace |
| Disk free drops during streaming | New SSTables, compaction, snapshots holding data | Throttle load, evaluate headroom; never force major compaction when disk is low |
| Prolonged pending compaction/streaming | I/O/network congestion, concurrent repair | Adjust maintenance window, check errors; never force remove without basis |
| Hints still exist for removed node | Mutations not yet replayed or past replay window | Check logs, repair/reconcile; never treat hints as a backup source |
| Old replica missed deletes past `gc_grace_seconds` | Tombstones may have been purged; zombie risk | Evaluate rebuild/replace; never allow stale node to rejoin |
| An ACKed marker reads missing after topology change | Source replica, routing, timestamps, streaming/repair error | Stop rollout, preserve evidence, check manifest and logs |
| `removenode` fails | Missing source replica, stream error, coordinator/node fault | Investigate per version; never use force/assassinate arbitrarily |

**Rollback is not always reversible.** After decommission/removenode, host ID/token placement has changed and data may have streamed elsewhere. Returning to four nodes usually requires **adding/bootstrapping/replacing a node** under a fresh procedure, not merely booting the old machine with its previous data directory/identity.

Never manually touch system tables or token/SSTable files to force a node "back into" the ring. If an operation is mid-way and the cluster is unstable, preserve logs/traces/metrics and consult the recovery runbook for your exact Cassandra version.

## 12. Practice Exercises and Self-Check Questions

**Exercise 1 — Choosing the Command.** With RF3 and four healthy nodes, the company wants to remove one node. Do you choose `decommission` or `removenode`? On which node does the command run? What conditions must hold for disk, streaming, and read/write CL?

**Exercise 2 — Temporarily DN Node.** A node is `DN` due to a 10-minute network outage but can still operate again. Why is `removenode` premature? Draft a checklist covering network, gossip, disk, logs, and hints before recovering the node.

**Exercise 3 — Completely Failed Node.** A `DN` node has lost its disk and cannot start. Explain why `nodetool decommission` is inappropriate and why `nodetool removenode <host_id>` must run on a live node. State how to verify the host ID before running it.

**Exercise 4 — RF Limit.** Three nodes in a DC all hold replicas at RF3; you want to scale down to two nodes. Why can you no longer maintain three-replica placement afterward? What is the safer alternative?

**Exercise 5 — Progress vs. Data.** Once `nodetool status` no longer lists cass-4 and `nodetool netstats` shows no streaming, is that enough to conclude no business data is missing? Design an expected manifest, partition-key queries, repair coverage, and `MATCH/MISSING/MISMATCH/READ_ERROR` reporting.

**Exercise 6 — Java Application.** When the driver receives a write timeout during removenode, should you log `NOT_WRITTEN` and replay every request? Distinguish `ACKNOWLEDGED`, `UNKNOWN`, and how to use an operation ID to check idempotency.

**Exercise 7 — Topology Change with Tombstones.** A node missed `DELETE`s for too long and risks zombie data. If replacing this node, what must you watch out for regarding `gc_grace_seconds`, repair, rebuild, and preventing the old data directory from returning?

## Key Takeaways

**`decommission` is used to cleanly remove a live node from the ring; `removenode <host_id>` is used to remove a node that is already down and cannot return, redistributing work across surviving replicas.** When the goal is preserving capacity, evaluate **replace** instead of shrinking node count. Before any change, inspect topology, per-DC RF, CL, capacity, data copies, and streaming viability; afterward, verify membership, latency, and **expected data markers**. A completed `nodetool` command does not substitute for reconciliation and replica maintenance.
