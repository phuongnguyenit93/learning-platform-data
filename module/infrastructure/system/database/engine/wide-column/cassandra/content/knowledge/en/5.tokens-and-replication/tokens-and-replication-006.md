# SimpleStrategy in Practice and Topology Selection Limits

> **Chapter:** Tokens and Replication  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — Apache Cassandra, a distributed database following the wide-column model.

A Cassandra record does not belong to a fixed machine just because an application connects to that machine. Cassandra hashes the **partition key** into a **token**, identifies the nodes owning token ranges, and uses the *keyspace*'s **replication strategy** to choose which nodes store copies. `SimpleStrategy` is the simplest way to observe this process in a lab; that very simplicity makes it unsuitable when a system spans multiple racks or datacenters.

After this lesson, learners can:

- Explain how `SimpleStrategy` chooses replica nodes from the token ring, including when virtual nodes (vnodes) are enabled.
- Create keyspaces, write and read data with CQL, and verify actual replicas using `nodetool`.
- Predict behavior when one node fails under `ONE`, `QUORUM`, and `ALL` consistency levels.
- Show why replication factor (RF) does not equate to rack or datacenter fault tolerance.
- Choose `NetworkTopologyStrategy` for real topologies and understand the operational work required when changing strategies.

## 1. How Does SimpleStrategy Select Replicas?

### 1.1. From Partition Key to Replica Set

Consider a table storing device measurements:

~~~sql
CREATE TABLE events_by_device (
    device_id uuid,
    event_time timestamp,
    event_type text,
    measurement double,
    PRIMARY KEY ((device_id), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

In this primary key, `device_id` is the **partition key**; `event_time` is the **clustering column**. All rows with the same `device_id` belong to the same partition. With the common `Murmur3Partitioner`, Cassandra computes the token from the partition key (it does not compute a separate token per row by `event_time`). The token determines the partition's logical position on the ring.

Each **keyspace** chooses one replication strategy. If a keyspace uses:

~~~sql
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 3
}
~~~

then for each partition, Cassandra finds **three distinct physical nodes** in token order around the ring. The general procedure is:

1. Compute the partition key's token, find the token range containing it, and identify the first responsible node.
2. Walk subsequent tokens clockwise around the ring, wrapping back to the beginning past the end.
3. Add a replica only if the next token belongs to a **physical node not yet in the replica set**.
4. Stop once `RF` distinct nodes have been selected.

Key takeaway: `SimpleStrategy` **ignores datacenters, racks, and availability zones** when selecting replicas. It only looks at positions on the token ring. One node can own multiple vnodes/tokens; passing two tokens owned by the same node does not create two independent replicas.

### 1.2. Simplified Ring Example

Suppose each node has just one token for ease of illustration, and the hypothetical tokens are ordered `10 → 30 → 60 → 90 → 10`:

~~~mermaid
flowchart LR
    A["Node A · token 10"] --> B["Node B · token 30"]
    B --> C["Node C · token 60"]
    C --> D["Node D · token 90"]
    D --> A
~~~

| Partition token | First node | RF = 1 | RF = 2 | RF = 3 |
|---|---|---|---|---|
| `25` | B | B | B, C | B, C, D |
| `75` | D | D | D, A | D, A, B |
| `5` | A | A | A, B | A, B, C |

This example only illustrates the **node-selection algorithm**. Real Murmur3 tokens span signed 64-bit integers; in a cluster with vnodes, a single node holds multiple positions around the ring and the result is not simply picking three adjacently named nodes.

**Distinguish three concepts:**

| Concept | Question it answers | Determined by |
|---|---|---|
| Partition key/token | Where logically does the partition sit? | Table key design and partitioner |
| Replication strategy/RF | Which nodes must store replicas? | Keyspace replication config and ring topology |
| Consistency level (CL) | How many replicas must respond for a request to succeed? | Each client/coordinator read/write operation |

RF = 3 means **three nodes are designated to hold replicas**, not that every write must wait for all three nodes to reply. That depends on CL.

## 2. Practice on a Single-Datacenter Cluster

### 2.1. Environment and Prerequisites

Prepare a **test Cassandra cluster with at least three active nodes** in one datacenter, with access to `cqlsh` and `nodetool`. Illustrative commands use standard Cassandra/CQL syntax common in 4.x–5.x; node addresses, container names, and startup commands depend on your environment. Never run node-stopping tests on a cluster serving real production data.

On a node, check:

~~~bash
nodetool status
~~~

Read the `Status/State` (e.g., `UN` for Up/Normal), `Tokens`, `Datacenter`, and `Rack` columns. At least three nodes must be operational before testing RF = 3. The `Tokens` column is normally greater than one when vnodes are enabled; this **does not** increase replica count on the same node.

### 2.2. Create the Keyspace and Table

Open `cqlsh` and run:

~~~sql
CREATE KEYSPACE IF NOT EXISTS lab_simple
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 3
}
AND durable_writes = true;

USE lab_simple;

CREATE TABLE IF NOT EXISTS events_by_device (
    device_id uuid,
    event_time timestamp,
    event_type text,
    measurement double,
    PRIMARY KEY ((device_id), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);

INSERT INTO events_by_device
    (device_id, event_time, event_type, measurement)
VALUES
    (d654b0fe-7357-497f-8db4-59b165d58a0f,
     '2026-11-21T09:00:00Z', 'temperature', 28.5);

INSERT INTO events_by_device
    (device_id, event_time, event_type, measurement)
VALUES
    (d654b0fe-7357-497f-8db4-59b165d58a0f,
     '2026-11-21T09:01:00Z', 'temperature', 28.7);
~~~

Both rows with the same `device_id` go into **the same partition**, and thus share the same replica set under the keyspace rules. The partition-key query aligns with query-driven table design:

~~~sql
SELECT device_id, event_time, event_type, measurement
FROM events_by_device
WHERE device_id = d654b0fe-7357-497f-8db4-59b165d58a0f
ORDER BY event_time DESC
LIMIT 10;
~~~

Note: `IF NOT EXISTS` does not update an already-existing keyspace. If `lab_simple` already exists, inspect its current config and pick a fresh lab name before comparing; do not assume the create statement changed RF.

### 2.3. Verify Who the Replicas Are

In `cqlsh`:

~~~text
DESCRIBE KEYSPACE lab_simple
~~~

Output should show `SimpleStrategy` and `replication_factor = 3`. Next, on a machine with `nodetool`:

~~~bash
nodetool getendpoints lab_simple events_by_device d654b0fe-7357-497f-8db4-59b165d58a0f
~~~

The `getendpoints` command lists the **endpoints designated as owners of that partition key**; with RF = 3 and sufficient physical nodes, expect three distinct endpoints. Match the IPs/nodes against `nodetool status`, paying attention to datacenter and rack columns. An endpoint appearing here **does not prove** the replica is fully synced or currently Up: it is the ownership list according to metadata.

Record results in an observation table:

| Evidence | What to record | How to interpret |
|---|---|---|
| `DESCRIBE KEYSPACE` | Strategy, RF | Verify keyspace-level configuration |
| `nodetool status` | Node list, DC/rack, `UN`/`DN` | Verify topology and liveness |
| `nodetool getendpoints` | Replica IPs for a `device_id` | Match RF against selected nodes |
| CQL query | Partition data | Verify read path at chosen CL |

To compare RF = 1, 2, 3, you can create **separate test keyspaces** (one per RF) with the same table structure; if using this approach, create the table in each keyspace before running `getendpoints`. Expected output is one, two, and three **distinct physical nodes** around the ring. This avoids altering RF between checks and mistakenly assuming new replicas immediately received the data.

## 3. Testing Availability and Consistency Levels

### 3.1. Why Must RF and CL Be Considered Together?

With RF = 3, the required responding replicas for common CLs are:

| CL | Required replicas with RF = 3 | When one of three replicas is Down |
|---|---:|---|
| `ONE` | 1 | Usually still readable/writable if another replica is reachable |
| `QUORUM` | `floor(3/2) + 1 = 2` | Usually still readable/writable if two replicas remain available |
| `ALL` | 3 | Fails to satisfy CL due to one missing replica |

With RF = 2, `QUORUM = 2`; with RF = 1, `QUORUM = 1`. Never claim simplistically that "`QUORUM` always survives one failed node."

In `cqlsh`, the command:

~~~text
CONSISTENCY QUORUM
~~~

sets the default CL for subsequent operations in that shell session; it is a **`cqlsh` command**, not a CQL statement to put in a schema file. Run the query from section 2.2, then set:

~~~text
CONSISTENCY ONE
~~~

and read again. Both queries succeeding when there are no failures is normal; the experiment becomes illuminating when the number of available replicas differs.

When a write succeeds at CL = `QUORUM` and a read runs at `QUORUM` over the same RF = 3 set, the two response sets of size two must overlap (`2 + 2 > 3`). This underpins quorum consistency for a history without concurrent writes. It does **not** automatically turn Cassandra into linearizable transactions for all cases: concurrent writes, timestamps, conflict resolution, and conditional operations must be analyzed separately.

### 3.2. Node Failure Test in an Isolated Environment

1. Verify all three nodes are `UN` and write data at an appropriate CL (e.g., `QUORUM`).
2. Stop **one** node using your lab/container tool; do not stop additional nodes or manually edit data files.
3. Wait for `nodetool status` to reflect the Down node (failure detection is not necessarily instant).
4. Test reads and writes to the same partition at `ONE`, `QUORUM`, and `ALL`; record successes, errors, and latencies.
5. Restart the node, confirm it returns to `UN`, then monitor replica synchronization. Hinted handoff can help deliver missed writes under appropriate conditions, but does not replace a `repair` policy.

On an exact three-node cluster with RF = 3, the typical outcome is that `ONE` and `QUORUM` stay available when one replica is Down, while `ALL` reports insufficient replicas. If you observe something different, check actual RF, endpoint list, node state, failure-detection lag, and connectivity to the coordinator before drawing conclusions.

**Distinguish success from latest data:** CL = `ONE` can receive a response from a replica that missed a recent update. CL = `QUORUM` increases agreement across replicas at the cost of waiting for more responses and reduced fault tolerance. No replication strategy replaces choosing CL to match application needs.

## 4. Topology Limits: SimpleStrategy Is Blind to Racks and Datacenters

### 4.1. Across Multiple Datacenters, RF Is One Cluster-Wide Number

Consider a hypothetical four-node cluster, one token per node:

| Node | Illustrative token | Datacenter | Rack |
|---|---:|---|---|
| A | 10 | `dc1` | `rack-a` |
| B | 30 | `dc1` | `rack-a` |
| C | 60 | `dc2` | `rack-b` |
| D | 90 | `dc2` | `rack-b` |

With `SimpleStrategy`, RF = 3:

| Partition token | Replicas | In `dc1` | In `dc2` |
|---|---|---:|---:|
| 25 | B, C, D | 1 | 2 |
| 75 | D, A, B | 2 | 1 |

Within the very same keyspace, different partitions end up with different replica counts in each DC. You therefore cannot promise "every datacenter always holds two copies" by raising `SimpleStrategy`'s RF. With vnodes, tokens interleave even more, yet the selection rule still **does not guarantee per-DC distribution**.

If `dc1` loses connectivity and an app in `dc2` needs to read at cluster-wide quorum, partition token 75 only has one replica in `dc2` and cannot reach `QUORUM = 2`, even though `dc2` has two healthy nodes. The reverse happens for other partitions when `dc2` fails.

### 4.2. Multiple Replicas Can Still Share a Single Point of Failure

Change the example: A, B, and C sit in the same rack (or availability zone), while D sits in another rack. For token 5 and RF = 3, the replica set is **A, B, C**—all three copies in the same rack. Losing that rack simultaneously destroys every replica of the partition, even though the schema declares RF = 3.

This is the difference between **node-level redundancy** and **failure-domain redundancy**:

- `SimpleStrategy` can mitigate the loss of a **single node**, provided enough replicas remain and CL permits.
- It does not deliberately spread replicas across **racks, zones, or datacenters** to survive correlated outages.
- Even when copies happen to look evenly distributed for a few partitions, that is merely an **observation of current topology**, not a guarantee preserved after adding/removing nodes, changing tokens, or scaling the cluster.

Never use `LOCAL_ONE` or `LOCAL_QUORUM` as a "fix" for `SimpleStrategy` in a multi-DC cluster. Local CLs only make sense when the replica placement design genuinely guarantees replicas in each DC. `SimpleStrategy` has no per-DC RF setting to ensure that.

## 5. When to Use SimpleStrategy vs. NetworkTopologyStrategy

| Criterion | `SimpleStrategy` | `NetworkTopologyStrategy` (NTS) |
|---|---|---|
| Replica count declaration | Single `replication_factor` for the whole cluster | Separate RF per datacenter |
| Replica selection | By token ring; ignores rack/DC | By token ring, DC-aware, and tries to spread across racks per DC |
| Small lab testing tokens and CQL | Good for learning mechanics | Also works; requires accurate topology/snitch |
| Single-DC production cluster | Not recommended | Recommended, even with only one DC today |
| Multi-DC needing local reads/writes | Does not guarantee per-DC replica allocation | Fits per-DC RF and local CLs |
| Rack fault tolerance | No rack-spreading rule | Places replicas in distinct racks when topology permits |

NTS example for one DC with **at least three nodes**:

~~~sql
CREATE KEYSPACE app_events
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;
~~~

NTS example for two DCs, **each with three suitable nodes**:

~~~sql
CREATE KEYSPACE app_events_multi_dc
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3,
    'dc2': 3
}
AND durable_writes = true;
~~~

Here, for every partition, the target is **three replicas in `dc1` and three replicas in `dc2`** (six physical nodes total), unlike `SimpleStrategy` RF = 3 which picks only three nodes cluster-wide. An application setting CL = `LOCAL_QUORUM` in a DC with RF = 3 typically needs two replicas **in that DC** to respond, reducing cross-DC network dependency for local requests.

Names `dc1`/`dc2` must **match exact case-sensitive spelling** reported by Cassandra/snitch. Configure the snitch and racks properly when building the cluster. NTS attempts to distribute replicas across existing racks; if fewer racks exist than RF, you cannot get one copy per distinct rack. NTS cannot fix misconfigured rack labels or nodes all placed in one physical fault domain.

**Quick rule of thumb:** use `SimpleStrategy` to illustrate the algorithm in an isolated lab. For any environment heading toward real operations, choose `NetworkTopologyStrategy` from day one—even with a single datacenter—and verify physical topology before choosing RF.

## 6. Switching from SimpleStrategy to NTS: New Schema Does Not Mean Data Is in Place

Suppose keyspace `lab_simple` uses `SimpleStrategy` RF = 3 and all three nodes belong to datacenter `dc1`. After verifying the DC name with `nodetool status` and confirming snitch/rack config is accurate, you can update metadata via:

~~~sql
ALTER KEYSPACE lab_simple
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};
~~~

However, **`ALTER KEYSPACE` only changes how Cassandra determines desired replicas**. It does not mean every new replica immediately holds all historical data. A real operational plan requires:

1. Inventory nodes, rack/DC counts, DC names from snitch, current RF, client apps, and active CLs; back up data and verify recovery paths.
2. Define target topology and storage capacity; if adding a new DC, prepare a dedicated bootstrap/streaming/migration runbook rather than just adding a DC name in CQL.
3. Update keyspace replication configuration; verify schema agreement and accurate metadata.
4. Run a **full repair** on affected nodes following the exact Cassandra version's runbook to distribute and synchronize data after placement or RF changes; monitor disk load, network, and completion time.
5. Re-verify endpoints for sample partitions, check each datacenter, and test the application's target consistency levels.

Example repair command on a target node:

~~~bash
nodetool repair --full lab_simple
~~~

Full repair consumes significant I/O and network bandwidth; run it within planned maintenance windows across affected nodes rather than triggering uncontrolled cluster-wide runs. In real clusters, changing DCs, snitches, or rack assignments carries version-specific operational constraints and may require separate migration procedures. Never arbitrarily alter rack/DC labels on a live cluster.

**Contrast with compaction:** compaction merges and sorts local SSTables on a single node; it does not choose partition replicas and does not replace anti-entropy repair across nodes. Nor does hinted handoff guarantee indefinite synchronization.

## 7. Relation to Table Design and Java Clients

Using `SimpleStrategy` or NTS **does not change** a table's partition key. With `PRIMARY KEY ((device_id), event_time)`, the application reads a device's events via `WHERE device_id = ?`, while `event_time` orders rows inside the partition. If one device produces massive volume, the partition can grow too wide or too hot; raising RF will not fix an unsuitable partition key design.

When connecting from Java, replication strategy is configured **on Cassandra/keyspace**, while CL can be set **per request** in the driver. Example with Java Driver 4.x on a connected `CqlSession`:

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import java.util.UUID;

UUID deviceId = UUID.fromString("d654b0fe-7357-497f-8db4-59b165d58a0f");

SimpleStatement statement = SimpleStatement.builder(
        "SELECT event_time, measurement " +
        "FROM lab_simple.events_by_device WHERE device_id = ? LIMIT 10")
    .addPositionalValue(deviceId)
    .setConsistencyLevel(DefaultConsistencyLevel.QUORUM)
    .build();

session.execute(statement);
~~~

In a multi-DC NTS environment, applications normally set the driver's local datacenter and consider `LOCAL_QUORUM` based on availability, latency, and consistency needs. A Java CL cannot force `SimpleStrategy` to distribute replicas by DC; that responsibility belongs solely to the replication strategy.

## 8. Scenario Exercises and Self-Check

**Scenario A — Reading the ring table:** Four nodes hold tokens 10/30/60/90 in order A/B/C/D; a partition has token 75 and `SimpleStrategy` RF = 3. Which nodes are replicas?

<details>
<summary>Answer</summary>

Starting from D (token 90), wrapping to A (token 10), then B (token 30): **D, A, B**. With vnodes, inspect the actual token ring rather than mechanically following node names.
</details>

**Scenario B — Rack limitation:** Three replicas reside on three distinct nodes in the same rack. Does RF = 3 guarantee surviving an entire rack outage?

<details>
<summary>Answer</summary>

**No.** All three nodes share one fault domain. `SimpleStrategy` ignores racks when choosing replicas. To gain rack-aware distribution, use NTS with properly configured topology/snitch.
</details>

**Scenario C — Changing RF:** A keyspace with RF = 2 is altered to RF = 3, and `ALTER KEYSPACE` succeeds. Can you conclude historical data already has three copies?

<details>
<summary>Answer</summary>

**Not yet.** Metadata selecting replicas changes before existing data is streamed/reconciled. A full repair and verification across relevant nodes are required.
</details>

**Scenario D — Production topology:** A cluster currently has one datacenter, with plans to expand to a second datacenter later. Which strategy should you start with?

<details>
<summary>Answer</summary>

**`NetworkTopologyStrategy`**, declaring RF for the current datacenter, configuring topology accurately, and planning DC expansion when needed. It is also the recommended choice for single-DC production clusters.
</details>

### Lab Completion Checklist

- [ ] Explain why two rows with the same partition key share the same replica set.
- [ ] Read strategy/RF with `DESCRIBE KEYSPACE` and node/DC/rack with `nodetool status`.
- [ ] Use `getendpoints` to verify the exact number of physical replica nodes matching RF.
- [ ] Distinguish RF from CL and calculate quorum for RF = 1, 2, 3.
- [ ] Prove by example that `SimpleStrategy` does not guarantee rack/DC-aware replicas.
- [ ] Know when NTS is required and why changing replication metadata may require full repair.

## References

1. Apache Cassandra Documentation — [Dynamo: Replication Strategy, SimpleStrategy, NetworkTopologyStrategy](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html).
2. Apache Cassandra Documentation — [CQL: Data Definition, CREATE/ALTER KEYSPACE](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html).
3. Apache Cassandra Documentation — [nodetool getendpoints](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/getendpoints.html) and [cqlsh CONSISTENCY](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html).
4. Apache Cassandra Documentation — [Repair and full repair when changing RF](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html), [Production recommendations](https://cassandra.apache.org/doc/stable/cassandra/getting-started/production.html).
