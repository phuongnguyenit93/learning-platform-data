# NetworkTopologyStrategy and Replica Placement by Datacenter and Rack

> **Chapter:** Tokens and Replication  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — explore Apache Cassandra's distributed architecture and wide-column model, from partition keys and query-driven table design to read/write consistency, replication, repair, and Java connectivity.

In Cassandra, **replication factor (RF)** answers "how many replicas does each partition need?", while **replication strategy** determines "where do those replicas live?". If you only count nodes without considering their physical locations, all three replicas could be lost together when a single rack, infrastructure zone, or datacenter goes down. `NetworkTopologyStrategy` (NTS) solves replica placement across **datacenters** and attempts to distribute replicas across **racks** within each datacenter.

This is the strategy you should use for production keyspaces, even when a cluster currently has only one datacenter. This lesson uses the token ring, CQL examples, and a two-datacenter cluster to explain the algorithm and verify behavior using operational tools.

**Learning Objectives**

1. Explain the roles of partition key, token, datacenter, rack, snitch, and replication factor in replica selection.
2. Predict how NTS distributes replicas according to each datacenter's RF and recognize limits when racks or nodes are insufficient.
3. Create keyspaces with CQL, verify endpoints via `nodetool`, and inspect replica health against topology.
4. Choose `LOCAL_ONE`, `LOCAL_QUORUM`, `QUORUM`, or `EACH_QUORUM` matching read/write requirements and failure scenarios.
5. Plan RF changes, DC expansion, streaming/repair, and connecting Java applications to the local DC.

## 1. Concepts to Keep Separate

### 1.1. Token Ring Determines Logical Position, NTS Determines Copies per DC

Cassandra distributes data by **partition key**. For example:

~~~sql
CREATE TABLE readings_by_device (
    device_id uuid,
    observed_at timestamp,
    temperature double,
    PRIMARY KEY ((device_id), observed_at)
) WITH CLUSTERING ORDER BY (observed_at DESC);
~~~

`device_id` is the partition key, and `observed_at` is the clustering column. Cassandra applies the partitioner (commonly `Murmur3Partitioner`) to compute a **token** from `device_id`. Two rows for the same device belong to the same partition and share one replica set; `observed_at` order does not alter token placement.

The token ring tells Cassandra which physical nodes follow sequentially at ring positions. With **virtual nodes (vnodes)**, each physical node can own multiple token intervals; thus "moving to the next token" does not necessarily mean "moving to a new physical node." A single node cannot be counted twice toward RF.

| Concept | Meaning in NTS | Scope |
|---|---|---|
| Partition key and token | Determine the starting position when locating replicas on the ring | Per partition |
| Physical node | Hosts a specific replica | Per cluster |
| Datacenter (DC) | Replica distribution domain declared in the keyspace | Per topology/snitch |
| Rack | Smaller fault domain inside a DC; NTS prefers spreading replicas across distinct racks | Per topology/snitch |
| RF per DC | Target number of replica nodes in that DC | Per keyspace |
| Consistency level (CL) | Number/scope of replicas required to acknowledge an operation | Per read/write request |

**Do not equate RF with CL:** RF is the replica placement target; CL is an operation's response requirement. A keyspace can have RF = 3 in each DC while a `LOCAL_QUORUM` write only needs acknowledgment from two replicas **in the local DC**.

### 1.2. Snitch: How Does Cassandra Know Which DC/Rack a Node Belongs To?

NTS relies on topology information supplied by the cluster's **endpoint snitch**. The snitch maps node addresses to datacenters and racks. A common implementation is `GossipingPropertyFileSnitch` with configuration such as:

~~~properties
dc=dc1
rack=rack1
~~~

This is merely an **illustration of a single node's configuration**, not a file to edit when running CQL queries. Each node carries values reflecting its own deployment location. Names like `dc1`, `dc2`, or `rack1` are logical identifiers; they must accurately mirror **physical fault domains** such as real availability zones or racks.

Inspect the topology Cassandra sees:

~~~bash
nodetool status
~~~

The output typically groups nodes by `Datacenter` and includes `Rack`, `Status/State` (e.g., `UN` for Up/Normal), `Tokens`, and load. Using `"rack1"` in two different DCs does **not** mean they share one physical rack; NTS evaluates racks independently within each DC. Conversely, labeling three nodes on the same physical rack with three different rack names creates a false sense of distribution and provides no real fault isolation.

> **Caution:** Never arbitrarily rename datacenters/racks or switch snitches on a live cluster. Topology changes can alter replica sets and require version-specific operational procedures.

## 2. Replica Selection Algorithm of NetworkTopologyStrategy

### 2.1. Core Algorithm

For a keyspace:

~~~sql
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3,
    'dc2': 2
}
~~~

each partition needs **three replicas on three distinct nodes in `dc1`** and **two replicas on two distinct nodes in `dc2`**, assuming enough eligible nodes exist. That totals **five replicas**, not RF = 3 cluster-wide. Datacenters omitted from the map are not asked by NTS to store replicas for this keyspace.

Conceptually, NTS:

1. Computes the token from the partition key and finds the starting position on the token ring.
2. Walks candidate nodes in ascending token order, wrapping around the ring.
3. For **each declared DC**, selects nodes until that DC's RF is satisfied; one physical node counts for at most one replica of the partition.
4. Within each DC, **prefers racks that do not yet hold a replica** before picking another node in an already-used rack, topology permitting.
5. Completes once every declared DC meets its RF or all eligible nodes have been traversed.

How this differs from `SimpleStrategy`: NTS enforces **per-datacenter quotas** and is **rack-aware**. NTS cannot invent independent fault domains if the underlying infrastructure lacks them; nor does it force every replica onto a separate rack when `RF > number of racks with eligible nodes`.

### 2.2. Two-Datacenter Ring Example

To see replica selection clearly, assume six nodes with **only one token per node**:

| Node | Illustrative token | Datacenter | Rack |
|---|---:|---|---|
| A | 10 | `dc1` | `r1` |
| B | 20 | `dc2` | `r1` |
| C | 30 | `dc1` | `r2` |
| D | 40 | `dc2` | `r2` |
| E | 50 | `dc1` | `r3` |
| F | 60 | `dc2` | `r3` |

~~~mermaid
flowchart LR
    A["A · 10 · dc1/r1"] --> B["B · 20 · dc2/r1"]
    B --> C["C · 30 · dc1/r2"]
    C --> D["D · 40 · dc2/r2"]
    D --> E["E · 50 · dc1/r3"]
    E --> F["F · 60 · dc2/r3"]
    F --> A
~~~

With RF `dc1: 3, dc2: 2`:

| Partition token | Nodes encountered walking the ring | Replicas in `dc1` | Replicas in `dc2` |
|---:|---|---|---|
| 25 | C → D → E → F → A → B | C (`r2`), E (`r3`), A (`r1`) | D (`r2`), F (`r3`) |
| 55 | F → A → B → C → D → E | A (`r1`), C (`r2`), E (`r3`) | F (`r3`), B (`r1`) |

A partition with token 25 starts at Node C, yet **C is not the only copy**. Its replica set also includes two other nodes in `dc1` and two nodes in `dc2`. Nodes of the two DCs do not have to sit in two contiguous arcs around the token ring.

**Example scope:** tokens `10/20/...` are hypothetical numbers for practicing reasoning; real Murmur3 tokens span 64-bit signed integers, and production clusters normally use vnodes so candidate order varies.

### 2.3. Why RF = 3 Does Not Automatically Survive a Rack Outage

Suppose `dc1` has only two racks across three nodes:

| Node | DC | Rack |
|---|---|---|
| A | `dc1` | `r1` |
| C | `dc1` | `r1` |
| E | `dc1` | `r2` |

NTS can still satisfy RF = 3 on **A, C, E**, placing two replicas in rack `r1`. When `r1` fails, only **one** replica remains in this DC, failing `LOCAL_QUORUM = 2`. With RF = 3 and a requirement to survive any single rack failure while maintaining local quorum, deploying **at least three independent racks**, each containing a node storing the partition, is a sound design.

NTS prefers distinct racks, yet cannot guarantee fault tolerance when nodes/racks are missing, rack info is wrong, or multiple logical racks share a single power/network zone. "Rack-diverse replica placement" is the result of **both strategy and infrastructure deployment**.

## 3. Declaring NTS in CQL and Inspecting Topology

### 3.1. Environment Requirements

The recommended lab has **two datacenters, each with three active nodes**, arranged across three separate racks per DC if possible, with permission to run `cqlsh` and `nodetool`. Never run experiments that stop nodes, alter RF, or swap snitches on a production cluster.

Check from one node:

~~~bash
nodetool status
~~~

Record the **exact** DC names (case-sensitive), racks, and each node's status. The CQL examples below assume the snitch reports `dc1` and `dc2`. If your cluster reports different names, update **the replication map keys** to match real names.

### 3.2. Create Keyspace, Table, and Sample Data

In `cqlsh`, configure three replicas per DC:

~~~sql
CREATE KEYSPACE IF NOT EXISTS lab_nts
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3,
    'dc2': 3
}
AND durable_writes = true;

USE lab_nts;

CREATE TABLE IF NOT EXISTS readings_by_device (
    device_id uuid,
    observed_at timestamp,
    temperature double,
    PRIMARY KEY ((device_id), observed_at)
) WITH CLUSTERING ORDER BY (observed_at DESC);

INSERT INTO readings_by_device (device_id, observed_at, temperature)
VALUES (a30b7134-4294-4b54-8765-2046c9e86055,
        '2026-11-21T09:00:00Z', 28.4);

INSERT INTO readings_by_device (device_id, observed_at, temperature)
VALUES (a30b7134-4294-4b54-8765-2046c9e86055,
        '2026-11-21T09:01:00Z', 28.8);

SELECT device_id, observed_at, temperature
FROM readings_by_device
WHERE device_id = a30b7134-4294-4b54-8765-2046c9e86055
ORDER BY observed_at DESC
LIMIT 10;
~~~

Both rows sharing `device_id` belong to the same partition and thus get **the same replica set** across both DCs. The `PRIMARY KEY ((device_id), observed_at)` design serves queries reading recent measurements for a device; if a device writes continuously for years, consider bucketing by day or month to prevent unbounded partitions.

**Note:** `CREATE KEYSPACE IF NOT EXISTS` **does not modify** the replication map of an existing keyspace. If `lab_nts` already exists, inspect its schema before testing, or pick a different lab keyspace name. Do not assume RF was updated just because the statement returned no error.

### 3.3. Inspect Metadata and Actual Replica Set

In `cqlsh`:

~~~text
DESCRIBE KEYSPACE lab_nts
~~~

And inspect the sample partition's token:

~~~sql
SELECT token(device_id) AS partition_token
FROM lab_nts.readings_by_device
WHERE device_id = a30b7134-4294-4b54-8765-2046c9e86055
LIMIT 1;
~~~

On a node, run `nodetool`:

~~~bash
nodetool getendpoints lab_nts readings_by_device a30b7134-4294-4b54-8765-2046c9e86055
~~~

With **two DCs having three nodes each** and RF = 3 per DC, expect **six distinct physical endpoints**: three in `dc1` and three in `dc2`. Cross-check each IP from `getendpoints` against its DC/rack in `nodetool status`. If each DC has more than three nodes, check whether the three chosen replicas span appropriate racks.

| Check | Expected result | What to inspect if wrong? |
|---|---|---|
| `DESCRIBE KEYSPACE` | `NetworkTopologyStrategy`, `dc1: 3`, `dc2: 3` | Was an existing keyspace reused? Are DC names exact? |
| `nodetool status` | Nodes `UN`, DC/rack info accurate | Snitch, node config, network, membership errors |
| `getendpoints` | 3 endpoints per DC; each node counted once | Keyspace RF, token distribution, available nodes in DC |
| Query by `device_id` | Returns both sample rows | Keyspace/table, write timing, CL, available replicas |

**Observation limit:** `getendpoints` reports **which nodes metadata assigns as replicas**; it does not prove historical data on all nodes is synchronized or that those nodes are currently Up. Inspect cluster health, test reads/writes at appropriate CL, and run repair if topology/RF recently changed.

## 4. Read/Write Consistency Across Multiple Datacenters

### 4.1. Calculating `LOCAL_QUORUM`, `QUORUM`, and `EACH_QUORUM`

Suppose keyspace `lab_nts` has `dc1: 3` and `dc2: 3`, totaling six full replicas per partition.

| Consistency level | Response condition in RF 3 + 3 example | Notes |
|---|---|---|
| `LOCAL_ONE` | 1 replica in local DC | Favors latency/availability; may read an un-updated replica |
| `LOCAL_QUORUM` | 2 replicas in local DC | `floor(3/2)+1 = 2` |
| `ONE` | Any 1 replica across DCs | Does not guarantee the response comes from the local DC |
| `QUORUM` | 4 replicas cluster-wide | `floor(6/2)+1 = 4` |
| `ALL` | All 6 replicas | Tolerates zero unresponsive replicas |
| `EACH_QUORUM` | **On write:** 2 replicas in `dc1` **and** 2 in `dc2` | Used for writes; not a standard CQL read CL |

Above, **local DC** means the DC of the coordinator handling the request (typically controlled in the Java driver via local datacenter and routing policy). `LOCAL_QUORUM` in `dc1` and `LOCAL_QUORUM` in `dc2` may require the same numeric count of responses, yet from **completely different replica sets**.

For a DC's own RF of `n`, that DC's local quorum is:

\[
Q_{\mathrm{local}} = \left\lfloor\frac{n}{2}\right\rfloor + 1
\]

For total full replicas across all DCs of `N`, global cluster quorum is:

\[
Q_{\mathrm{global}} = \left\lfloor\frac{N}{2}\right\rfloor + 1
\]

For instance, if `dc1: 3`, `dc2: 2`, then `LOCAL_QUORUM` in `dc1` needs 2, in `dc2` also needs **2**, while global `QUORUM` needs `floor(5/2)+1 = 3`. Therefore, never say "`LOCAL_QUORUM` always needs two replicas" when RF can differ.

### 4.2. Choosing CL Based on Application Requirements

For a Java application deployed in `dc1`, pairing **write `LOCAL_QUORUM` and read `LOCAL_QUORUM` in the same DC** with RF = 3 guarantees the two quorums intersect (`2 + 2 > 3`) in that DC. This forms the basis for reading quorum-acknowledged writes when there are no concurrent writes or complicating update histories.

However:

- **`LOCAL_QUORUM` does not mean every DC immediately sees the latest data.** A write in `dc1` can be acknowledged before `dc2` replicas respond; apps reading immediately in `dc2` must account for replication lag, network faults, and the CL used on both sides.
- **`LOCAL_QUORUM` does not guarantee linearizability for every access.** Account for timestamps, concurrent writes, last-write-wins, retries, conflicts, and conditional operations (LWT).
- **Cluster-wide `QUORUM`** requires enough replicas across DCs; with two DCs at RF 3 + 3, losing an entire DC leaves only three replicas, failing the four-response requirement.
- **`EACH_QUORUM` for writes** enforces quorum acknowledgment from **every DC**, at the cost of higher cross-DC latency and dependency; losing an entire DC causes writes at that CL to fail.

There is no single "best" CL for all cases. Define **the scope where writes must be visible immediately**, cross-DC latency, and desired fault tolerance before choosing CL.

### 4.3. Practicing CQL in Each DC

Connect `cqlsh` to a node in `dc1` and run:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

Then execute:

~~~sql
SELECT observed_at, temperature
FROM lab_nts.readings_by_device
WHERE device_id = a30b7134-4294-4b54-8765-2046c9e86055
LIMIT 10;
~~~

The `CONSISTENCY` command above is a **`cqlsh`-specific command** setting CL for subsequent queries in that session. Open another `cqlsh` session to a node in `dc2` and repeat with `LOCAL_QUORUM`; the acknowledging replicas will be in `dc2`. To measure differences, run separately with `LOCAL_ONE` and `QUORUM`, recording outcomes, latency, coordinator node, and network state.

Reading the same data while all nodes are Up is **not enough** to prove local quorum survives failures. Testing that requires an isolated lab and a controlled failure drill.

## 5. Failure Scenarios: Node Loss, Rack Loss, and Datacenter Loss

Assume two DCs, **each with three replicas across three independent racks**, RF 3 + 3. The application can connect to a healthy DC and fail over when required.

| Incident | `LOCAL_QUORUM` in affected DC | `LOCAL_QUORUM` in healthy DC | Global `QUORUM` |
|---|---|---|---|
| One replica/node in `dc1` Down | Can still reach 2/3 | Can still reach 2/3 | Can still reach 4/6 if 5 replicas remain up |
| One rack in `dc1` Down (1 replica per rack) | Can still reach 2/3 | Can still reach 2/3 | Can still reach 4/6 |
| Total loss of `dc1` | Cannot be met from a `dc1` coordinator | Can reach 2/3 in `dc2` | Fails 4/6 |
| Inter-DC link cut while nodes inside each DC stay up | Can reach 2/3 locally | Can reach 2/3 locally | May fail 4/6 from an isolated side |

These are **theoretical expectations based on responding replica counts**, not guarantees that operations always succeed: coordinator health, client network, failure detection delay, timeouts, data sync state, and load all affect reality. If one rack holds **two** replicas in the same DC, losing that rack leaves only 1/3 and local quorum **fails**.

### 5.1. Safe Failure-Testing Procedure in a Lab

1. Confirm both DCs have enough `UN` nodes; back up any lab data you need to keep.
2. Write sample data and measure reads/writes with `LOCAL_QUORUM` in `dc1`.
3. Stop **one node** in `dc1` via your lab management tool; wait for the cluster to detect the Down state.
4. Test `LOCAL_QUORUM` reads/writes in `dc1`, then test in `dc2`; record outcomes and response times.
5. Restart the node, wait for stabilization, and verify sync/repair per lab procedures.
6. Only if the lab permits and recovery is verified, simulate a rack/DC outage within planned scope; never touch production.

**Do not confuse availability with consistency:** during a network partition, both DCs can keep accepting writes at their respective `LOCAL_QUORUM`. If multiple sides update the same partition, understand timestamp and conflict resolution; once connectivity heals, not every intermediate write history is guaranteed to be preserved in the order users expect.

## 6. Choosing Topology/RF and Scaling the System

### 6.1. Practical Design Guidelines

| Problem | Suggested choice | What to verify |
|---|---|---|
| Single-DC production, three nodes across three independent racks | NTS with RF `dc1: 3` | Snitch reports accurate DC/rack, capacity headroom on node loss |
| Two DCs needing independent local reads/writes | NTS with per-DC RF, typically 3 per DC if infrastructure allows | Driver bound to local DC, failover and sync strategy |
| Second DC only for testing/DR | `dc2` RF matching RPO/RTO goals and budget | Never assume RF = 1 satisfies quorum or fault tolerance |
| RF = 3 but each DC only has two racks | NTS still works | One rack may hold two replicas; consider adding a rack or adjusting fault tolerance goals |
| Store replicas in one DC only | Declare RF only for that DC | Verify access paths and old copies after schema changes |

Choose RF based on required fault domains, storage capacity, network cost, and CL targets. With two DCs at RF 3 + 3, **each partition has six replicas**, meaning substantial storage and replication traffic compared to one copy—before even counting compaction, index, and metadata overhead.

NTS manages **replica placement**. If strict data residency requirements exist, also evaluate coordinators, queries, logs, backups, snapshots, monitoring, and where applications process data; a replication map alone is not a complete compliance policy.

### 6.2. Changing RF in a DC

Example raising `dc1` RF from 2 to 3 in an existing NTS keyspace:

~~~sql
ALTER KEYSPACE lab_nts
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3,
    'dc2': 3
};
~~~

**Precondition:** the CQL above is only an example if the current state is actually `dc1: 2, dc2: 3`. Do not run it as an unplanned "quick fix." `ALTER KEYSPACE` updates **metadata about desired replicas**; new replicas do not immediately hold historical data.

Typical operational procedure:

1. Check current RF, snitch, DCs/racks/nodes, disk space, Cassandra version, backup needs, and application CLs.
2. Ensure enough **physical nodes and racks** exist to satisfy the target; if adding nodes, complete join/bootstrap/streaming per the appropriate operational guide.
3. Apply the schema change and wait for schema agreement; verify with `DESCRIBE KEYSPACE` and `nodetool getendpoints` on sample partitions.
4. Schedule a **full repair** on relevant nodes so historical data streams to newly assigned replicas; monitor network, disk, compaction, and timeouts.
5. Switch CL or ramp production traffic only after verifying placement and data completeness.

Example repair command on a node within operational scope:

~~~bash
nodetool repair --full lab_nts
~~~

Full repair is resource-intensive; **node scope, execution order, and repair flags** must follow your exact version and runbook. Never run full repair concurrently across the whole cluster without accounting for load.

### 6.3. Adding a New Datacenter

Suppose `dc2` previously had no replicas of an existing keyspace and needs to be brought online. Adding `'dc2': 3` to the replication map **does not automatically populate old data into `dc2`**. You need a sequence covering node/snitch deployment, bootstrap or rebuild/streaming from the source DC per runbook, data verification and appropriate repair, and only then shifting application traffic and local CL.

During transition, avoid rushing to require `LOCAL_QUORUM` in the new DC before data and replicas finish syncing. When lowering RF or retiring a DC, leftover copies may remain on disk; plan cleanup after confirming valid ownership and recoverability.

**Repair differs from compaction:** repair exchanges data/differences between replicas to resolve divergence; compaction merges SSTables **within a single node** and does not stream data to new replicas. Hinted handoff helps when a replica is temporarily Down, but does not replace periodic repair.

## 7. Java Driver: Routing to the Local DC and Setting CL

In a Java application, **the replication strategy and RF live in Cassandra's schema**; the Java Driver selects coordinators, routes queries, and sets per-statement consistency. Simple example using DataStax/Apache Cassandra Java Driver 4.x:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.net.InetSocketAddress;
import java.util.UUID;

try (CqlSession session = CqlSession.builder()
        .addContactPoint(new InetSocketAddress("10.0.1.11", 9042))
        .withLocalDatacenter("dc1")
        .build()) {

    PreparedStatement prepared = session.prepare(
        "SELECT observed_at, temperature " +
        "FROM lab_nts.readings_by_device " +
        "WHERE device_id = ? LIMIT 10");

    BoundStatement statement = prepared
        .bind(UUID.fromString("a30b7134-4294-4b54-8765-2046c9e86055"))
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

    session.execute(statement).forEach(row ->
        System.out.println(row.getInstant("observed_at") + " : " +
                           row.getDouble("temperature")));
}
~~~

`10.0.1.11` is only an **illustrative** contact point; replace it with a real node address in `dc1`. Production deployments must configure authentication/TLS if required and review timeouts, retries, and idempotence. `withLocalDatacenter("dc1")` directs the driver to use the local DC for routing; it **does not** modify the replication map. `LOCAL_QUORUM` sets the acknowledgment requirement for that specific operation, without altering RF.

When failing over to `dc2`, point the session/client to the new serving DC and ensure RF, data sync, and consistency in that DC meet business needs. Never simply change `"dc1"` to `"dc2"` and assume every partition is already synced, especially right after adding a DC or altering RF.

## 8. Diagnosing Common Symptoms

| Symptom | Causes to check | Investigation path |
|---|---|---|
| `LOCAL_QUORUM` fails even though many cluster nodes are Up | Insufficient replicas in local DC; multiple nodes on same rack/network path failed; RF differs from expected | Check coordinator's DC, `nodetool status`, keyspace RF, endpoints |
| `QUORUM` fails when losing an entire DC with RF 3 + 3 | Only 3/6 replicas remain, below global quorum = 4 | Pick CL per app needs; evaluate routing to healthy DC |
| `getendpoints` shows nodes in unexpected racks | Snitch/rack config misrepresents topology, token ring, or insufficient racks | Verify physical DC/rack, deployment layout, and node count |
| `ALTER KEYSPACE` succeeded but old data fails reads in new DC | Metadata updated, new replicas haven't finished sync/streaming/repair | Check bootstrap progress, rebuild/streaming, repair, node status |
| Java queries cross to remote DC with elevated latency | Misconfigured local DC, routing, contact points, or failover | Check driver local datacenter, network path, coordinator, metrics |
| After network split, two DCs return different results | Concurrent writes, local CL, timestamps, delayed replication | Inspect read/write CLs, timestamps, retries, and repair |

`UnavailableException` generally indicates insufficient replicas considered alive to satisfy CL; `ReadTimeoutException`/`WriteTimeoutException` indicate insufficient responses arrived before timeout. Never assume data was lost or a write definitely failed solely from a timeout: check logs/metrics and handle retries safely, especially for non-idempotent operations.

## 9. Practice Exercises

**Exercise 1 — Calculate replica counts and quorums.** A keyspace declares `dc1: 3, dc2: 2`. How many replicas does a partition have? How many responses does `LOCAL_QUORUM` need when the coordinator is in `dc1` vs. `dc2`? How many responses does global `QUORUM` need?

<details>
<summary>Answer hint</summary>

Total **5 replicas**. Local quorum in `dc1` is **2/3**, in `dc2` is **2/2**; cluster-wide quorum is **3/5**. Therefore `dc2` cannot tolerate a single replica going Down while still requiring `LOCAL_QUORUM`.
</details>

**Exercise 2 — Rack outage.** In `dc1`, RF = 3 is placed on A (rack r1), C (rack r1), E (rack r2). What happens to `LOCAL_QUORUM` when rack r1 goes completely down?

<details>
<summary>Answer hint</summary>

Only E remains—**1/3**—whereas local quorum requires **2/3**, so the operation fails CL. You need a topology with more independent racks or adjusted availability targets.
</details>

**Exercise 3 — Datacenter outage.** A cluster with RF 3 + 3 loses all of `dc1`. The application fails over its coordinator to `dc2`. Are `LOCAL_QUORUM` and cluster-wide `QUORUM` still achievable by replica count?

<details>
<summary>Answer hint</summary>

`LOCAL_QUORUM` in `dc2` can reach **2/3** if DC2 is healthy and data is ready; cluster-wide `QUORUM` requires **4/6** and therefore fails with only three replicas in `dc2`.
</details>

**Exercise 4 — DC expansion.** A keyspace long had only `dc1: 3`. Operations adds `dc2: 3` in CQL, and the app in `dc2` immediately switches to `LOCAL_QUORUM`. Can you guarantee all historical data is already in DC2?

<details>
<summary>Answer hint</summary>

**No.** The schema change only declares where replicas should live. The new DC requires bootstrap/rebuild/streaming and appropriate repair, plus data verification, before serving live traffic.
</details>

### Self-Check Checklist

- [ ] Distinguish token ring, datacenter, rack, RF, and CL.
- [ ] Understand that NTS picks replicas per **each** DC's RF and prefers spreading across racks.
- [ ] Create an NTS keyspace in CQL and verify replicas using `nodetool getendpoints`.
- [ ] Calculate `LOCAL_QUORUM` and `QUORUM` across different RF configurations.
- [ ] Predict the impact of node, rack, and datacenter failures on satisfying CL.
- [ ] Know why changing RF or adding a DC requires streaming or repair and data verification.
- [ ] Configure local datacenter and per-request consistency in the Java Driver.

## Further Reading

1. Apache Cassandra Documentation — [Dynamo: Partitioning and Replication Strategy](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html).
2. Apache Cassandra Documentation — [CQL Data Definition: CREATE/ALTER KEYSPACE](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html).
3. Apache Cassandra Documentation — [nodetool getendpoints](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/getendpoints.html).
4. Apache Cassandra Documentation — [Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html).
