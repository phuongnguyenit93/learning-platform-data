# Bootstrap, Token Assignment, and Initial Data Streaming in Apache Cassandra

## 1. When Adding a Node, What Actually Happens?

In Apache Cassandra, every table is designed around the **queries it must serve**, data is distributed by **partition key**, and replicas are placed on nodes according to the keyspace's **replication strategy**. When adding a node to increase storage capacity or read/write throughput, the system must change its **topology**: the new node assumes responsibility for certain token ranges and needs to fetch existing data from current replicas.

This process is called **bootstrap**. A new node cannot simply join gossip and immediately possess all its assigned partitions. It must obtain cluster metadata, receive tokens, determine the data ranges it must hold, and **stream initial data** from suitable sources before transitioning to normal serving state.

Imagine a cluster storing device events under partition key `device_id`. If the application just added node N4, partitions whose tokens fall into N4's ranges will have their responsibility shifted from some older nodes to N4. A keyspace's replication factor does not automatically increase just because the cluster added a machine; **the goal is to redistribute replicas** according to the new replica placement.

In the **Topology Changes** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module, this lesson explains three foundational stages:

1. **Bootstrap**: the new node joins and announces its cluster-joining state.
2. **Token assignment**: the node receives its positions in the token ring and the data ranges it is responsible for.
3. **Initial streaming**: the node fetches required data from available replicas while the cluster continues serving traffic.

Mastering this process avoids the misconception that adding a node balances data immediately, or that a Java application can read and copy data to the new node itself.

## 2. Concepts to Distinguish

| Concept | Meaning During Node Addition |
|---|---|
| **Partition key** | Columns used to identify a partition; values are mapped to a token by the partitioner |
| **Token** | A value in the token space; used to determine a partition's position on the ring |
| **Token range** | A range of tokens a node participates in storing according to cluster placement |
| **Primary range** | A range for which a node is the primary owner in ring order under the simplified model |
| **Replica set** | Set of nodes holding replicas per the keyspace's replication strategy and RF |
| **Virtual nodes (vnodes)** | A physical node can own multiple tokens/ranges instead of one large contiguous range |
| **Seed node** | Initial contact point for cluster discovery, not a central controller node |
| **Gossip** | Metadata/state exchange between nodes that enables topology discovery |
| **Pending range / pending replica** | Ranges that a joining node will become responsible for after handoff |
| **Streaming** | Storage-level data transfer between nodes for required ranges |
| **Bootstrap complete** | The node has finished version-specific joining steps and transitioned to normal state |

With `Murmur3Partitioner`, Cassandra commonly uses tokens in the signed 64-bit integer space. **A token is not a row ID.** A partition key is hashed to a token; many partitions can reside within the same token range, and a single node can hold many ranges when using vnodes.

In a keyspace using `NetworkTopologyStrategy`, the replica list also depends on **datacenter**, per-DC replica count, and rack/snitch placement. Therefore, **owning a token does not mean that node is the sole copy**. To know where data moves from and to, you must examine the specific topology and replication strategy.

## 3. Which Stages Does a New Node Pass Through?

### 3.1. Preparing a New Node Identity

Before bootstrapping, the node must be configured as a fresh cluster member:

- `cluster_name` and communication settings must match the running cluster.
- `listen_address` or connection addresses/rules must be reachable from other nodes; ports and TLS/authentication policies must align.
- `seed_provider`/seeds help the node locate the cluster; seeds do not own all tokens and do not replace data synchronization.
- Datacenter, rack, snitch, and topology must match the keyspace's replication strategy.
- The new node's data directories, commit log, and identity must be prepared per version guidance; **never copy system data/identity from another node** to spin up a new node.
- Token/vnode settings such as `num_tokens` and the token allocation mechanism must be finalized before the first bootstrap.

Adding an empty node to a populated cluster should be treated as a **real bootstrap** procedure. Never arbitrarily disable `auto_bootstrap` just to make the machine show UP faster; doing so can skip fetching required data. Exact settings vary by Cassandra version and provisioning method.

### 3.2. Cluster Discovery and Metadata Agreement

The new node contacts seed nodes to find other members, joins gossip exchanges, and learns token ring/placement information. Seeds are **discovery contacts**, not master nodes or dedicated data stores. Streaming may pull data from replicas completely distinct from the configured seeds.

Cassandra validates required conditions regarding identity, cluster, and reachability. If the node is misconfigured with the wrong cluster name, DC, rack, or certain identifiers, joining may be rejected, stall, or result in an unexpected topology.

### 3.3. Receiving Tokens and Determining New Responsibilities

The node is assigned or uses tokens per its configured mechanism. With vnodes, a node has multiple tokens, so incoming data can arrive from many ranges and many sources. The system determines the **post-change replica set** for each range based on RF, strategy, rack/DC, and present nodes.

Distinguish between:

- **Assigned tokens**: knowing which ranges the node will be responsible for.
- **Owning the corresponding data**: having received and processed sufficient required data from source replicas.
- **Ready to serve as a normal node**: completed bootstrap/streaming, reached the appropriate state, and passed health checks.

Receiving tokens is a **routing responsibility change**, whereas streaming is **physical content transfer**. You cannot use token assignment alone to conclude data transfer is finished.

### 3.4. Planning Streaming from Existing Replicas

From the ranges being handed over, Cassandra determines the data to receive and the appropriate source replicas. Source/stream set selection depends on topology, RF, DC, token ranges, and the streaming implementation of the version in use.

Source nodes read data in the transfer ranges and send it to the new node via streaming. Data is materialized into appropriate storage components on the destination; this operation can consume network, disk read/write, CPU, and compaction resources.

### 3.5. Catching Up on New Mutations and Completing State Transition

While the new node is streaming, applications **can still continue writing** to the cluster. Cassandra coordinates topology transitions so that mutations affecting ranges in flight do not rely solely on the initial snapshot. Details of pending replica handling, writes during bootstrap, and completion steps vary by version.

A node must not be considered stable merely because it received its first stream of data. You must check bootstrap status, stream sessions, and error conditions; afterward, the node can transition from **joining** to **normal**.

~~~mermaid
flowchart TD
    A["Configure new node and verify connectivity"] --> B["Discover cluster via seeds / gossip"]
    B --> C["Receive tokens or vnodes per configuration"]
    C --> D["Compute post-change ranges and replica sets"]
    D --> E["Select source replicas and plan streams"]
    E --> F["Stream SSTables / data for assigned ranges"]
    F --> G["Handle handoff and mutations occurring during join"]
    G --> H{"Bootstrap and streams completed?"}
    H -->|No| I["Check netstats, errors, disk, and network"]
    I --> F
    H -->|Yes| J["Node is normal; verify distribution and health"]
    J --> K["Cleanup leftover data on old nodes per runbook"]
~~~

This diagram reflects a **logical sequence**, not a fixed API call schedule. A node may perform steps concurrently, and states/optimizations vary across Cassandra releases.

## 4. Illustrating the Token Ring Before and After Adding a Node

To visualize this easily, assume a small simulated token ring from `0` to `99` (this is **not** the real full Murmur3 token space). A datacenter has four nodes:

~~~text
                  Simulated token ring
          A(10) → B(40) → C(75) → D(90) → A(10)

Each partition is assigned a token by hashing its partition key.
In the simplified model, tokens in (10,40] go to B.
~~~

Suppose node **E** is added at token `30`:

~~~text
Before: A(10) ------- B(40) ------- C(75) --- D(90)
After:  A(10) --- E(30) --- B(40) --- C(75) --- D(90)
                    ^
               New position
~~~

In this ring-order illustration, before E appeared, range `(10,40]` had node B as its primary owner. After E is introduced, that range splits into:

- `(10,30]`: E becomes the primary owner of the range.
- `(30,40]`: B remains the primary owner.

Assuming replication factor 2 and ignoring complex rack/DC rules, the replica set for token `25` may change from **B + C** to **E + B**. E must fetch data for that range from an appropriate source replica; C may still hold old data until cleanup is run per procedure.

**Limitations of this example:** Real Cassandra has a huge token ring, multiple vnodes, replication strategies, and rack/DC-aware replica selection. You cannot apply "the adjacent node is always the sole streaming source" directly to every keyspace.

### 4.1. Impact of Vnodes

When a node has multiple vnodes, it does not receive a single contiguous token range. Instead, it gets many ranges scattered around the ring. Benefits can include more even load distribution and greater flexibility when scaling the cluster; the trade-off is more complex placement calculation, streaming, and token administration.

- `num_tokens` is a configuration setting governing a node's token count in vnode setups.
- Some versions/configurations support token allocation algorithms that consider replication to improve distribution.
- Do not casually change token/vnode counts on a node **that already holds data** as if it were an ordinary performance knob: changing token ownership is a topology change requiring a dedicated procedure.

Estimating how much data a new node will receive must be based on **per-keyspace data volume, per-DC RF, and current token distribution**, not merely dividing total cluster size by node count.

## 5. What Does Initial Data Streaming Actually Transfer?

### 5.1. Streaming Is Not a Java Application Reading and Re-INSERTing

Bootstrap is an inter-node operation at the storage layer. Source nodes transfer data for the determined ranges, typically based on SSTables or storage units supported by the engine. The destination node receives and integrates the data into Cassandra storage.

Java applications do not need to run a `SELECT *` loop and `INSERT` into the new node's IP. Doing so bypasses the replica/ownership model and can generate uncontrolled writes, tombstones, timestamps, or load. **The bottleneck of bootstrap lies in inter-node network and storage**, not in writing row-transfer logic in application code.

### 5.2. Resources to Budget

| Resource | On Source Node | On Destination Node |
|---|---|---|
| **Network** | Sends data chunks via streaming | Receives data, subject to bandwidth limits |
| **Disk I/O** | Reads SSTables and related data | Writes received files, possibly triggering concurrent compaction |
| **CPU** | Processes streams, compression/decompression per config | Processes streams and incoming SSTables |
| **Disk space** | May still retain unowned data not yet reclaimed | Needs space for new data, overhead, and background tasks |
| **Read/write path** | Competes for I/O with client requests | Receives streams while potentially serving relevant mutations |

A large streaming session can elevate p95/p99 latency for ongoing queries. Thus adding a node requires planning timing, throughput, and headroom, even though bootstrap is not "cluster-wide downtime".

### 5.3. Speed and Completion Time

As an illustrative example, if **300 GiB of actual data** needs to be transferred and sustained end-to-end throughput is **50 MiB/s**:

~~~text
300 GiB = 300 x 1024 = 307,200 MiB
Ideal transfer time = 307,200 / 50
                    = 6,144 seconds
                    ≈ 102.4 minutes
~~~

This figure is **only an ideal lower-bound estimate under assumed throughput**. Actual duration is also affected by source selection, stream throttling, TLS, network contention, disk, SSTable processing, retries, and concurrent mutation volume. Never promise completion times from a simple capacity/bandwidth division.

### 5.4. Received Data May Not Yet Equal "Final Data"

During handoff, new mutations can still arrive at responsible replicas. Cassandra coordinates pending ranges and appropriate handoff communication, yet when network failures, node reboots, or stream retries occur, you must inspect actual bootstrap status and maintain a repair schedule afterward.

**Bootstrap streaming** places initial data on the new node. **Repair** is an anti-entropy mechanism that compares and fixes differences across replicas; both may consume network and I/O, but they serve different purposes.

## 6. Replication Factor Does Not Increase When Adding a Node

This is a common point of confusion in capacity planning.

Suppose a keyspace has RF=2 in a DC with three initial nodes. Each partition is kept on **two** replicas per placement. Adding a fourth node:

- The keyspace's RF remains **2**, unless a separate configuration change is executed.
- Data is **redistributed** so each partition still has two replicas, while locations shift with token ownership.
- The new node must receive the data belonging to its new replica sets.
- Some copies on old nodes may become data **outside their responsibility** once topology stabilizes.

### Capacity Balancing Example

Assume the keyspace's logical data is **600 GiB**, RF=2, every node in the same DC is eligible, and token/load distribution is completely uniform.

| Stage | Total Logical Replicas | Old Node Average | New Node |
|---|---:|---:|---:|
| Before adding node: 3 nodes | 1,200 GiB | ~400 GiB/node | None yet |
| After full rebalance: 4 nodes | 1,200 GiB | ~300 GiB/node | ~300 GiB |
| During bootstrap | Can temporarily exceed 1,200 GiB | Old data not yet cleaned up | Growing toward its target share |

These numbers are an idealized model, excluding SSTable overhead, tombstones, metadata, multiple keyspaces, rack replication, hot data, compaction, and partition skew.

**Important operational note:** After a new node bootstraps, old data on previous nodes may still occupy disk. Running **cleanup** on old nodes, following the runbook and after verifying bootstrap, removes data no longer belonging to their token ranges. Never assume old nodes' disks are automatically freed the moment the new node shows `UN`.

Therefore, during cluster expansion, you must budget **space on the new node to receive streams** and **headroom on old nodes for temporary leftover data plus background activity**.

## 7. Observing Bootstrap Progress with Cassandra Tools

### 7.1. Node State Is Not the Only Indicator

Common status codes seen when running `nodetool status`:

| Illustrative Status | Interpretation |
|---|---|
| `UJ` | Node is UP and **joining**; usually indicates incomplete bootstrap |
| `UN` | Node is UP and in **normal** state |
| `DN` | Node is DOWN, normal state known in the ring |
| Other states | May relate to leaving/moving or other conditions depending on version |

`UJ` must not be treated as `UN`. Conversely, merely seeing `UN` is **necessary but not sufficient** to declare all services healthy, read/write latency stable, and post-bootstrap tasks like cleanup completed.

### 7.2. Status-Reading Commands

On a node with operational privileges and matching version:

~~~bash
# Inspect topology, DC, rack, UP/JOINING/NORMAL states.
nodetool status

# Inspect streaming sessions, progress, and transfer status.
nodetool netstats

# Inspect gossip metadata to investigate membership details.
nodetool gossipinfo

# Cluster / topology view as observed by the node.
nodetool describecluster

# Inspect compaction competing for I/O with bootstrap.
nodetool compactionstats

# Inspect storage usage and table metrics (syntax varies by version).
nodetool tablestats
~~~

`nodetool netstats` is typically helpful to see how much data a node is sending/receiving via streaming. However, do not rely on a single empty `netstats` output to declare bootstrap complete: cross-check **node state, logs, streaming errors, received data volume, and metadata**.

### 7.3. Metrics to Monitor Together

| Category | Metric/Observation | Purpose |
|---|---|---|
| **Bootstrap** | `UJ → UN`, join logs, stream session success/failure | Confirm node passed initialization stage |
| **Streaming** | Remaining bytes, received/sent bytes, transfer rate, retries/errors | Detect stalled or overly slow streams |
| **Network** | Bandwidth, connection errors/timeouts, RTT between source and target | Separate network bottlenecks from storage bottlenecks |
| **Disk** | Free bytes, IOPS, throughput, per-data-directory latency | Prevent destination node disk exhaustion during stream |
| **Compaction** | Pending tasks, bytes rewritten, read/write latency | Detect streaming I/O contention |
| **Client workload** | p95/p99 latency, write timeouts, read timeouts, unavailable | Assess application impact |
| **Topology** | DC/rack, tokens/vnodes, per-node data distribution | Detect misplacement or imbalance |
| **Post-bootstrap** | Old node disk usage, cleanup/repair plan | Complete redistribution and reconciliation |

Monitoring must compare **per node**, avoiding looking only at cluster-wide total streaming bytes. A single disk-bottlenecked source node can dictate bootstrap speed even when other nodes are idle.

## 8. Controlled Node-Addition Procedure

### Step 1 — Inspect the Cluster Before Making Changes

Confirm the cluster is stable: no unexpected down nodes, no unexpected repair/streaming/bootstrap in progress, and sufficient disk headroom, network capacity, and load capacity.

Check keyspace replication, `NetworkTopologyStrategy` settings, datacenter, rack, snitch, token distribution, per-node disk usage, and active workload types. Adding a node to a DC without proper rack alignment may not yield the expected replica placement.

### Step 2 — Prepare the New Node

Properly configure cluster identity, network, auth/TLS, snitch, and datacenter/rack. Finalize the token/vnodes policy, ensuring data/commit log directories are appropriate for a **new node**. Verify cluster connectivity and disk capacity for initial data ingestion.

**Never reuse the host ID or system data of an existing node** to "save bootstrap time". Replacing an old node is a different procedure from adding a new node.

### Step 3 — Start and Monitor Joining State

Start the node per the version's runbook, watching bootstrap logs, `nodetool status`, and `nodetool netstats`. The node receives tokens and begins streaming appropriate ranges; verify sources/destinations and data volumes in flight.

Meanwhile, watch free bytes, disk growth, and latency on both source and destination nodes. If streaming is very slow, pinpoint whether the cause is network, disk, compaction, communication errors, or config limits before intervening.

### Step 4 — Verify Completion

Once no in-progress bootstrap work remains, confirm node status is `UN`, logs show no related errors, replication/token assignments match expectations, and read/write health is stable. Do not stop verification merely because the node is "UP".

### Step 5 — Clean Up Old Data and Reconcile

After topology stabilizes, old nodes may retain SSTables containing data they no longer own. Evaluate **cleanup** on the appropriate nodes/keyspaces per runbook and disk/I/O headroom. Cleanup also generates load and may require temporary disk space, so do not run it everywhere at once while the new node is still straining resources.

Maintain **periodic repair** and check for replica divergence if interruptions occurred. Cleanup removes data **outside current ownership**, and does not replace repair.

### Step 6 — Measure Scaling Outcomes

Compare actual storage distribution, token balance, throughput, and latency before/after. If a hotspot is caused by a single overly hot partition key, adding nodes helps only if placement and traffic patterns actually spread the load. A single **hot partition** still resides on a finite replica set; key modeling/bucketing adjustments may be needed rather than simply adding machines.

## 9. Common Bootstrap Failures

| Symptom | Causes to Check | Approach |
|---|---|---|
| Node cannot find cluster | Wrong seeds, firewall, ports, TLS/auth, routing | Verify connectivity and logs instead of arbitrarily changing tokens |
| Node sees cluster but fails to join | `cluster_name`, identity, DC/rack, incompatible config, version | Compare config and metadata against expected topology |
| Prolonged `UJ`, streaming stalls | Unavailable source, network congestion, stream failure, target disk full | Inspect `netstats`, logs, filesystems, disk latency |
| Stream progresses but p99 spikes sharply | Source/target I/O contention with compaction and client traffic | Monitor resources, adjust schedule/throttling per runbook |
| Node is `UN` but received unusually little data | Token/placement, RF/DC, token distribution, or uneven data volume | Inspect ranges and replication per keyspace |
| Old nodes do not drop in disk usage | Unowned data still present, cleanup not run, snapshots, or new writes | Evaluate cleanup and SSTable-retaining components |
| Read/write timeouts appear after join | Node not yet settled, network, skew, replica placement, compaction load | Correlate cluster-wide logs/metrics; do not blame bootstrap alone |
| Bootstrap interrupted mid-way | Restart, disk failure, network drop, stream failure | Use version-appropriate resume/recovery procedure; preserve data for investigation |

Do not arbitrarily delete the data directory, reset tokens/host ID, or re-bootstrap a node that has already begun receiving data. Resume, rebuild, replace, or remove procedures vary by version and node state; determine which case applies before acting.

## 10. How Does Bootstrap Differ from Other Topology Operations?

| Operation | When Used | How Data Moves |
|---|---|---|
| **Bootstrap / add node** | Bring a new node into an existing cluster | Node receives tokens and streams initial data for its assigned ranges |
| **Decommission** | Proactively remove a live node | Transfers responsibility/data to remaining replicas per new topology |
| **Removenode** | Remove a node that can no longer rejoin via normal procedure | Cluster coordinates restoring responsibility from surviving replicas |
| **Replace node** | Replace a failed node with another machine via replacement identity | Rebuilds data belonging to the replaced node's responsibility |
| **Rebuild** | Re-fetch appropriate data from a source DC/replicas in supported contexts | Topology-based recovery streaming, not standard new-node join |
| **Repair** | Synchronize existing replicas | Compares and repairs data differences across ranges |
| **Cleanup** | Remove data outside node ownership after ownership changes | Purges local SSTables; does not stream to other nodes |

Control commands may differ between Cassandra versions. This table emphasizes **purpose**; never swap `cleanup`, `repair`, `replace`, and `bootstrap` simply because they all involve moving or reconciling data.

## 11. CQL and Java: Applications Should Still Use Partition Keys and Appropriate CL

### 11.1. Illustrative Keyspace and Table

Suppose a cluster has a datacenter named `dc1` and wants to retain three replicas in that datacenter:

~~~cql
CREATE KEYSPACE telemetry_demo
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE telemetry_demo.measurements_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    temperature double,
    PRIMARY KEY ((device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

The partition key is `(device_id, event_day)`, not `device_id` alone. When adding a node, Cassandra redistributes **tokens of the composite partition key**, and replication is computed at RF=3 for DC `dc1`. The new node's topology configuration must match the defined datacenter/rack.

Query preserving the full routing key:

~~~cql
CONSISTENCY LOCAL_QUORUM;

SELECT event_time, temperature
FROM telemetry_demo.measurements_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
LIMIT 50;
~~~

`LOCAL_QUORUM` is an illustrative choice for a DC with RF=3; actual requirements depend on latency, consistency, and topology. It does not trigger streaming or govern token allocation.

### 11.2. Java Driver 4.x Uses Cluster Metadata

With the Java driver, the application should delegate routing and topology discovery to a driver configured with the correct datacenter, rather than hardcoding the IP of a node owning a partition.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.net.InetSocketAddress;
import java.time.LocalDate;
import java.util.UUID;

// contact point and DC are examples only; replace with cluster values.
try (CqlSession session = CqlSession.builder()
        .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
        .withLocalDatacenter("dc1")
        .build()) {

    PreparedStatement query = session.prepare(
        "SELECT event_time, temperature " +
        "FROM telemetry_demo.measurements_by_device_day " +
        "WHERE device_id = ? AND event_day = ? LIMIT 50"
    );

    BoundStatement statement = query.bind(
            UUID.fromString("11111111-1111-1111-1111-111111111111"),
            LocalDate.of(2026, 11, 21))
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

    for (Row row : session.execute(statement)) {
        System.out.println(row.getInstant("event_time")
            + " " + row.getDouble("temperature"));
    }
}
~~~

The driver tracks metadata/topology and performs token-aware routing when given sufficient information and configuration. **The application does not stream data itself** when a new node appears. During cluster changes, you must still handle timeouts, `Unavailable`, controlled retries, and idempotency for writes with side effects.

A `SELECT` query like the one above also does not prove that all streaming has completed. Bootstrap status must be confirmed using **nodetool, logs, and cluster metrics**.

## 12. Scenario Exercises

**Scenario A.** A cluster has three nodes, RF=2. A fourth node is added. Afterward, is every partition stored on three replicas?

**Answer:** No. Adding a node does not automatically change RF; each partition still has two replicas per keyspace replication. Replica count changes only if a separate RF configuration change is performed.

**Scenario B.** A new node reaches the seeds and appears in state `UJ`. Can bootstrap be considered finished?

**Answer:** Not yet. `UJ` indicates the node is joining. You must monitor streaming, logs, and transition to normal state per version.

**Scenario C.** After the new node becomes `UN`, old nodes still use nearly the same disk space. Did bootstrap fail?

**Answer:** Not necessarily. Old data outside their ownership may remain until cleanup; additionally, snapshots, compaction, and new incoming load also consume disk.

**Scenario D.** A stream must transfer 300 GiB, measured at 50 MiB/s. Roughly what is the ideal duration?

**Answer:** About 102.4 minutes, excluding retries, overhead, disk, network contention, and newly arriving data.

**Scenario E.** The ops team wants to copy the entire data directory from a running node to a new node, edit the IP, and start it to "skip streaming". What is wrong?

**Answer:** Node identity and topology metadata cannot be cloned arbitrarily. Doing so can cause identity/token conflicts or data misaligned with ownership. Adding a new node must follow proper bootstrap; replacing a failed node has its own procedure.

**Scenario F.** After adding a node, a hot `device_id` partition still causes timeouts on its replica set. Why might adding a node not fix it?

**Answer:** A single partition is still placed on a finite number of replicas per RF. Adding total nodes does not split the contents of one partition. You need to examine key modeling/bucketing, load distribution, and query patterns.

## 13. Key Takeaways

**Bootstrap is a process that changes the cluster's data responsibilities**, not merely starting up a new Cassandra machine:

- **Token allocation** determines the partition ranges a new node will own; **replication strategy** determines which replicas actually hold data.
- **Initial streaming** transfers existing data from source replicas to the new node; seeds only help discover the cluster and are not default data sources.
- **Vnodes** give a node multiple token ranges, potentially streaming from many sources, requiring per-keyspace placement analysis.
- **`UJ` and `UN` differ**: a joining node is not yet a normal member; even after `UN`, you still need to verify health, capacity, and post-bootstrap tasks.
- **Old node disk space does not drop immediately**: evaluate cleanup, snapshots, and background operations once topology stabilizes.
- **Java clients** should keep partition-key routing and appropriate consistency; Cassandra handles data movement, while applications monitor errors and latency.
- **Repair, cleanup, replace, and rebuild** serve different purposes from bootstrap and must be used in the right scenarios.

When planning to scale Apache Cassandra, check **DC/rack, RF, token ownership, disk headroom, and network I/O**, then monitor **streaming + node state + application impact** until data distribution stabilizes. A node appearing in the cluster member list is only the beginning; only once required data has transferred and all post-bootstrap steps are verified has scaling achieved its goal.
