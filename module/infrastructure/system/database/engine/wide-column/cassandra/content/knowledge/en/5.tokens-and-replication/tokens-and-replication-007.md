# Distinguishing Node Count, Token Count, and Replica Count

## 1. Why Are These Three Numbers Easily Confused?

When deploying Apache Cassandra, you often hear figures such as "the cluster has **4 nodes**," "each node holds **8 tokens**," and "the keyspace uses **replication factor 3**." All three numbers relate to data distribution, yet they answer three **different** questions:

1. **Node count:** How many Cassandra processes/machines participate in the cluster, or in a given data center?
2. **Token count:** How many token positions are assigned around the data-partitioning ring to divide the token space into segments managed by nodes?
3. **Replica count:** For **each partition** in a keyspace, how many **distinct nodes** are selected to store a copy of its data?

In the **wide-column** model, the partition key determines which nodes hold a partition; token count affects how key ranges are split and balanced; replication factor determines how many copies of a partition exist. Distinguishing these three numbers accurately is foundational for query-driven table design, replication/consistency configuration, trace inspection, troubleshooting, repair planning, and connecting safely from Java.

**Lesson scope:** standard *full replicas* in Cassandra use token-based partitioning (typically `Murmur3Partitioner`). Do not apply the counting rules below directly to infer transient replication or version-specific distribution optimizations.

## 2. Definitions: Node, Token, Replica, and RF

| Concept | Counting unit | Determined by | What must **not** be inferred |
| --- | --- | --- | --- |
| **Node** | One Cassandra node (one cluster member) | Deployed node count and cluster membership status | One node does not equal a copy of *every* partition. |
| **Token** | A value/position in token space assigned to a node | Partitioner, token allocation, and settings such as `num_tokens` | A token is not a row, a partition, a machine, or a replica. |
| **Token range** | An interval of token values on the ring | Consecutive token positions | A range does not hold only one partition; it typically holds many partitions. |
| **Replica** | One node storing a copy of *a specific partition* | Partition key → token, replication strategy, RF, DC/rack topology | A node holding multiple tokens does not count as multiple replicas of the same partition. |
| **Replication factor (RF)** | Target replica count per partition (per data center when using `NetworkTopologyStrategy`) | Keyspace replication configuration | RF is not total cluster node count or tokens per node. |
| **Consistency level (CL)** | Response threshold required for a read/write operation | Per request/statement | CL does not raise or lower RF. |

One physical node can hold multiple tokens (*virtual nodes*, commonly called **vnodes**); one node can also store data for many partitions, yet for **a single** partition it counts as at most **one replica**. RF = 3 means three **distinct nodes** are chosen to store a partition when topology satisfies RF, regardless of whether each node holds one token or dozens of tokens.

To avoid terminology confusion, this lesson defines **"token count"** as *the number of token positions assigned to nodes*. With vnodes and uniform allocation, total assigned token positions usually equal:

\[
T = \sum_{i=1}^{N} T_i
\]

where `N` is the node count and `T_i` is the number of tokens assigned to the `i`-th node. This formula only counts assigned tokens; it does **not** count the possible hash outputs or the number of data replicas.

## 3. Node Count: Cluster and Per-Data-Center Scale

A node is a member performing storage and request handling in a Cassandra cluster. Clusters often span multiple **data centers (DCs)**, with nodes inside each DC placed across **racks** to enable fault-tolerant replica selection.

Topology example:

~~~text
Cluster webshop
├── dc1
│   ├── N1
│   ├── N2
│   ├── N3
│   └── N4
└── dc2
    ├── N5
    ├── N6
    └── N7
~~~

- Total nodes in cluster: **7**.
- Nodes in `dc1`: **4**; in `dc2`: **3**.
- These numbers only describe **deployment scale**; they do not yet tell how many times a partition is replicated.

A node can serve as **coordinator** for a client request even when it is not a replica of that partition. Coordinator is a **request-handling role**, whereas replica is a **per-partition storage role**. The number of available coordinators is not the keyspace's RF.

## 4. Token Count: Ring Positions and Virtual Nodes

### 4.1. From Partition Key to Token

Cassandra passes the partition key value through a *partitioner* to compute a token. With `Murmur3Partitioner`, a token is a signed 64-bit integer; the diagram below uses small numbers purely for readability and **not real hash values**.

Nodes take responsibility for **token ranges**. In the classic token ring mental model, a token assigned to a node marks the end of an interval `(previous token, current token]`, moving clockwise. The final interval wraps around to the first token.

~~~mermaid
flowchart LR
    P["Partition key: account_id = 'a-42'"] --> H["Partitioner computes token"]
    H --> T["Partition token"]
    T --> O["Locate token range containing that value"]
    O --> R["Select replica nodes per RF and topology"]
~~~

A token is **not** a fresh ID allocated per record. Many partitions can land in the same token range, and the token space itself has vastly more possible values than the number of tokens assigned to nodes.

### 4.2. One Node Can Hold Multiple Tokens

Under **one token per node**, 4 nodes correspond to 4 token positions, splitting the ring into 4 ranges. With **vnodes**, each node is assigned multiple distinct token positions; for instance, `num_tokens = 8` across 4 nodes yields **32 token positions** when all 4 nodes are allocated 8 tokens.

~~~text
Vnodes example: 4 nodes, 2 tokens per node (8 tokens on the ring)

Ascending positions:  -90    -60    -30      0      30      60      90     120
Node holding token:   N1     N2     N3     N4      N1      N2      N3      N4
                      └──────────────────────────────────────────────────────┘
                            Ring wraps from last token back to first token
~~~

In this example, N1 owns both token `-90` and token `30`. This gives N1 responsibility for **multiple non-contiguous token ranges** around the ring rather than a single contiguous range. Total node count remains **4**. If the keyspace has RF = 3, a partition still has **3 replicas**—it does not become 6 or 8 replicas just because nodes hold multiple tokens.

Higher token counts generally allow more flexible range allocation/load distribution at the cost of extra metadata, streaming, repair, and operational overhead; the right token count depends on version, topology, workload type, and scaling plans. Never treat "more tokens is always better" as a universal rule.

> When adding nodes, Cassandra can reassign token ranges and stream data to redistribute load. Having more tokens or more nodes **does not automatically increase a keyspace's RF**.

## 5. Replica Count: How Many Nodes Store Each Partition?

Replicas are determined per partition by the **partition's token**, **replication strategy**, and **topology**. For production keyspaces using `NetworkTopologyStrategy`, RF is typically configured **independently per data center**.

Example:

~~~sql
CREATE KEYSPACE IF NOT EXISTS webshop
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3,
  'dc2': 2
};
~~~

Assuming topology has enough suitable nodes:

- **Each partition** in keyspace `webshop` has **3 full replicas in `dc1`** and **2 full replicas in `dc2`**.
- That totals **5 full replicas across 5 distinct nodes** for that partition—not 7 copies (7 is the total cluster node count).
- Other partitions can have **different replica sets**, while keeping the 3 + 2 counts.
- Replicas are placed based on tokens and DC/rack selection rules, not picked arbitrarily from any node.

If `RF_dc` denotes the RF of a DC, the target copy count in a multi-DC keyspace is:

\[
R_{\text{total}} = \sum_{dc} RF_{dc}
\]

This formula assumes each DC has enough eligible nodes to meet RF and counts full replicas only. If configuration sets RF higher than the existing node count in a DC, **it is impossible to place enough replicas on distinct nodes** in that DC; that is a topology planning error that cannot be fixed by increasing token counts.

### One Token Does Not Equal One Replica

Returning to the illustrative ring in section 4: 4 nodes N1–N4, each with 2 tokens. Suppose a partition has token **15**:

1. Walking clockwise in ascending order, the first assigned token greater than or equal to 15 is **30**, owned by N1: this is the starting point for replica selection.
2. In a **simplified** model using `SimpleStrategy` with RF = 3, continue walking the ring and picking **distinct nodes**: N1, N2, N3.
3. Upon encountering another token belonging to an already-selected node, Cassandra does not count that node a second time toward RF.

~~~mermaid
flowchart LR
    K["Partition with token = 15"] --> A["Token 30 → N1"]
    A --> B["Token 60 → N2"]
    B --> C["Token 90 → N3"]
    C --> D["3 replicas: N1, N2, N3"]
~~~

This example only clarifies the **principle of choosing distinct nodes around the ring**. `SimpleStrategy` is unsuitable for multi-rack/multi-DC production deployments; `NetworkTopologyStrategy` also considers DC/rack when choosing replicas, so the actual node set can differ from the illustrative sequence above.

## 6. Putting the Three Numbers Side by Side

Suppose a cluster has **4 nodes in one DC**, each node is assigned **8 tokens**, and the keyspace sets **RF = 3**:

| Question | Answer |
| --- | --- |
| How many nodes are in the cluster? | **4 nodes** |
| How many tokens are assigned per node? | **8 tokens/node** |
| How many total assigned tokens are there? | **4 × 8 = 32 tokens** |
| How many replicas does one partition of the keyspace have? | **3 replicas**, on 3 distinct nodes |
| How many copies does a partition have when 1 node is not a replica? | **Still 3**; the fourth node does not hold that partition |
| Does RF = 3 mean all 4 nodes store every partition? | **No** |
| Does increasing tokens/node from 8 to 16 raise RF to 6? | **No**, RF stays 3 unless keyspace config changes |

### Mental Model: Three Decision Layers

~~~mermaid
flowchart TD
    N["4 Cassandra nodes"] --> V["8 tokens per node → 32 token positions"]
    PK["Table partition key"] --> H["Hash → 1 token value for partition"]
    H --> M["Locate token range and ring position"]
    V --> M
    RF["Keyspace RF = 3, replication strategy"] --> S["Select 3 distinct nodes as replicas"]
    M --> S
    S --> A["Partition has 3 copies"]
~~~

**How to read it:** node count tells you how many members can take work; token count affects how responsibility ranges are sliced; RF and replication strategy determine how many nodes hold each partition. The three variables are related but **not interchangeable**.

## 7. Impact on Capacity, Speed, and Availability

### 7.1. Storage Capacity

If a keyspace's raw source data occupies roughly `D` units and has RF = 3 in one DC, then **replicated data** alone intuitively occupies around `3D` across the nodes. In reality, overhead also comes from commit logs, memtables, SSTable metadata, tombstones, compaction, snapshots, and uneven distribution.

With 4 nodes and RF = 3, if data is evenly distributed, the **average** replicated data per node is near:

\[
\frac{D \times RF}{N} = \frac{3D}{4}
\]

This is only a **planning estimate**, not a per-node storage guarantee. Token count affects the granularity of load division, whereas RF is the primary multiplier determining replicated data volume in this model.

### 7.2. When Nodes Fail

In **one DC with 4 nodes and RF = 3**, if an operation uses `LOCAL_QUORUM`, the coordinator needs responses from **2 of the partition's 3 replicas**:

| State of partition's replicas | Live replicas | `LOCAL_QUORUM` read/write |
| --- | ---: | --- |
| All 3 replicas up | 3 | Can succeed |
| 1 replica down, 2 replicas up | 2 | Can still succeed |
| 2 replicas down, 1 replica up | 1 | Fails to meet CL |

If the fourth node—which is **not** a replica of the partition in question—is up, it can act as coordinator but **cannot count as an extra replica ACK**. Assigning more tokens to that node will not turn it into a fourth copy either.

With RF = 3 in the same DC, `LOCAL_ONE` needs one replica to respond, `LOCAL_QUORUM` needs two, and `ALL` needs three. With multiple DCs, `LOCAL_QUORUM` calculates quorum over the **local DC's RF**, whereas `QUORUM` calculates over the keyspace's **total RF**. RF controls copy count; CL controls minimum responses before a request succeeds.

### 7.3. When Scaling Fault Tolerance or Load

| Goal | Change to consider | What not to confuse |
| --- | --- | --- |
| Add CPU/RAM/disk resources and spread load | Add nodes, balance token ranges, monitor data distribution | Adding nodes does not automatically raise RF. |
| Increase copies per partition | Alter keyspace replication factor, ensure enough nodes, sync new copies | Adding tokens does not increase copies. |
| Finer-grained key range distribution | Evaluate vnode/token count per node based on version and workload | Never casually change `num_tokens` on a running node as a harmless tweak. |
| Reduce cross-DC dependency for reads/writes | Choose per-DC RF and appropriate CL, such as `LOCAL_QUORUM` | Adding cluster-wide nodes does not alter CL ACK requirements. |

When changing topology, Cassandra must move/stream data to match the new distribution. When changing RF, historical data must be synchronized to the new replica set via appropriate operational/repair workflows. Local compaction on one node does not replace repair across replicas.

## 8. Practice: Checking Each Number with Cassandra Tools

### 8.1. Check Node Count and Tokens per Node

Run on a machine with `nodetool` access:

~~~bash
nodetool status
~~~

In the output, inspect **Data center**, `UN` (*Up/Normal*) status, **Tokens**, and **Rack**. Illustrative output (omitting IPs/UUIDs and unrelated fields):

~~~text
Datacenter: dc1
Status=Up/Down
|/ State=Normal/Leaving/Joining/Moving
--  Address   Tokens  Rack
UN  node1     8       rack1
UN  node2     8       rack2
UN  node3     8       rack3
UN  node4     8       rack1
~~~

This output shows **4 nodes** in `dc1`, each assigned **8 tokens**, totaling **32 tokens**. `nodetool status` also has an `Owns` or `Owns (effective)` column; ownership percentages depend on keyspace/RF and must not be misread as replica count or token count.

To inspect tokens and ranges around the ring, run:

~~~bash
nodetool ring
~~~

This lists token endpoints and helps inspect actual token allocation. With multiple vnodes, a node appears at multiple positions. Do not infer replica counts directly from line counts in `nodetool ring`.

### 8.2. Create a Keyspace and Table by Partition Key

Assuming the lab has **one DC named `dc1` with at least three nodes**, run:

~~~sql
CREATE KEYSPACE IF NOT EXISTS orders_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS orders_lab.orders_by_customer (
  customer_id text,
  ordered_at timestamp,
  order_id uuid,
  total decimal,
  PRIMARY KEY ((customer_id), ordered_at, order_id)
) WITH CLUSTERING ORDER BY (ordered_at DESC, order_id ASC);
~~~

`customer_id` is the **partition key**; `ordered_at` and `order_id` are clustering columns. This design fits the query "a customer's order history" using a concrete partition key:

~~~sql
INSERT INTO orders_lab.orders_by_customer
  (customer_id, ordered_at, order_id, total)
VALUES
  ('customer-17', '2026-11-21T03:00:00Z',
   123e4567-e89b-42d3-a456-426614174000, 129.50);

SELECT ordered_at, order_id, total
FROM orders_lab.orders_by_customer
WHERE customer_id = 'customer-17'
LIMIT 10;
~~~

The customer may have many **rows**, yet every row sharing `customer_id` sits in **one partition** and shares the same replica group. RF = 3 still means three nodes store copies of this partition—not "each row gets three tokens."

### 8.3. Inspect the Replica Nodes of a Partition

On a host with `nodetool`, pass the single partition key `customer_id` from the example:

~~~bash
nodetool getendpoints orders_lab orders_by_customer customer-17
~~~

This lists the endpoints responsible for **that specific partition key** in the keyspace/table. In a single-DC lab with RF = 3 and matching topology, expect **three endpoints on three distinct nodes**. Changing `customer_id` may return a different endpoint set; these results do not depend on which coordinator node a Java client connects to.

In `cqlsh`, you can test the required CL without altering RF:

~~~sql
CONSISTENCY LOCAL_QUORUM;
SELECT ordered_at, order_id, total
FROM orders_lab.orders_by_customer
WHERE customer_id = 'customer-17'
LIMIT 10;
~~~

`CONSISTENCY` is a **`cqlsh` command**, not a CQL statement sent verbatim from Java. In a Java app using Cassandra Java Driver 4.x, use `BoundStatement.setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)` to request the equivalent consistency level.

**Observation note:** if your actual topology, replica states, or datacenter name differ from the example, outputs will differ. Always use your real DC name when creating keyspaces and configuring `local datacenter` in the Java driver.

## 9. Typical Misconceptions

| Claim | True or false? | Explanation |
| --- | --- | --- |
| "The cluster has 6 nodes, so every partition has 6 copies." | **False** | Replica count depends on the keyspace's RF, not total node count by default. |
| "A node has 16 tokens, so it holds 16 replicas of each partition." | **False** | Multiple tokens give a node multiple ranges; for one partition, that node is at most one replica. |
| "RF = 3 means every write waits for all 3 ACKs." | **False** | ACK threshold depends on CL. `LOCAL_QUORUM` in a DC with RF = 3 needs two. |
| "Scaling nodes from 4 to 5 automatically gives each partition an extra copy." | **False** | Replicas are redistributed; **target replica count** stays unchanged unless RF changes. |
| "Increasing `num_tokens` fixes having too few nodes for RF = 3." | **False** | Three suitable distinct nodes in the DC are needed to store three full replicas. |
| "Two different partitions can share the same replica group." | **True** | Different tokens/partition ranges can map to the same group of replica nodes. |
| "One node can act as both coordinator and replica." | **True** | The two roles are defined per request and per partition, and are not mutually exclusive. |

## 10. Self-Check Exercises with Answers

**Exercise 1.** A DC has 5 nodes, 16 tokens assigned per node, RF = 3. What is the total number of assigned tokens and the target replica count for one partition?

**Answer:** `5 × 16 = 80` token positions; **3 replicas** on three distinct nodes. Do not infer 80 copies.

**Exercise 2.** A cluster has `dc1`: 4 nodes and `dc2`: 3 nodes; 8 tokens per node. The keyspace uses `NetworkTopologyStrategy` with RF `dc1 = 3`, `dc2 = 2`. What are the cluster node count, assigned token positions, and replica count per partition?

**Answer:** **7 nodes**, `7 × 8 = 56` assigned tokens, and **5 replicas** per partition (3 in `dc1`, 2 in `dc2`), when the cluster satisfies the topology.

**Exercise 3.** A partition has three replicas N1/N2/N3, while N4 does not hold that partition. N1 and N2 are up; N3 is down. Can a `LOCAL_QUORUM` request sent to N4 succeed?

**Answer:** **Yes, it can**, provided N1 and N2 are in the local DC, respond in time, and no other error occurs. N4 coordinates the request but does not count as a third replica ACK.

**Exercise 4.** Operations wants to increase data fault tolerance, yet only increases `num_tokens` from 8 to 32 while keeping node count and RF = 2 unchanged. What is the outcome?

**Answer:** Assigned tokens/node may increase if changed via a valid procedure, yet **each partition still has only two replicas**. Increasing copies requires raising RF, ensuring enough nodes, and syncing data via an appropriate workflow.

## 11. End-of-Lesson Quick Reference

| If you want to know… | Check… |
| --- | --- |
| **How many Cassandra machines exist?** | Node count per DC/rack via topology and `nodetool status`. |
| **How many ring positions does a node own?** | The node's token list, `Tokens` in `nodetool status`, or `nodetool ring`. |
| **How many copies does a partition have?** | Keyspace RF per DC and the partition's actual endpoints. |
| **How many responses must a read/write wait for?** | The **request's** consistency level and RF in the corresponding scope. |
| **Why doesn't adding a node change RF?** | Nodes and tokens govern load distribution; RF is declared on the keyspace. |

**Chain of reasoning to remember:** *partition key → token → token range → replica set per replication strategy and topology → required responses per consistency level*. That is the accurate way to read **node count, token count, and replica count** when designing and operating Cassandra.
