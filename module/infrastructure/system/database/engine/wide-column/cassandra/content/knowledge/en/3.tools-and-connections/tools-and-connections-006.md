# Seed Nodes and Their Role in Bootstrapping Membership Information

## 1. What Problem Do Seed Nodes Solve?

Apache Cassandra is a **distributed wide-column database** with no central server coordinating all reads and writes. Every node needs to know which nodes belong to the cluster, which nodes are currently alive, datacenter/rack topology, and token information to locate replicas for a partition. When a node **first starts and does not yet know the cluster members**, it needs one or a few initial contact addresses to find the other nodes.

A **seed node** is a node designated in the **seed/contact points list for the internal cluster gossip protocol**. A joining node contacts an active seed to begin exchanging membership information. After learning the topology, it continues gossiping with many other nodes; seeds do not hold an exclusive role throughout the cluster's lifecycle.

For the **Tools and Connections** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module, seeds should be understood in relation to **gossip, bootstrap, replication, partition keys, consistency, repair**, and Java application connections to Cassandra.

**After this lesson, you will be able to:**

1. Distinguish a seed node from a coordinator, a replica, a Java Driver contact point, and an administrative node.
2. Describe how a new node discovers cluster members via seeds and gossip, and then bootstraps data.
3. Configure `seed_provider` with the appropriate internode addresses and ports for labs and multi-node clusters.
4. Select redundant seeds across datacenters/racks, and recognize the mistake of using only `localhost` or a single seed.
5. Troubleshoot seed connection, gossip, topology, and bootstrap progress issues using Cassandra tools.

## 2. Seeds Are Not "Masters"

| Role | Primary Responsibility | Does It Exclusively Hold All Data? |
| --- | --- | --- |
| **Seed node** | Initial contact point for other nodes to learn membership via gossip; also participates in regular gossip. | **No**. Data is still distributed by tokens and replication. |
| **Coordinator** | Node that receives a specific CQL request and communicates with the required replicas. | **No**. Any eligible node can act as coordinator for a request. |
| **Replica** | Node storing a copy of data for a token range/partition per the replication strategy. | Stores the partitions it is responsible for, regardless of whether it is a seed. |
| **Java Driver contact point** | Endpoint used by an application to initiate connections and discover the cluster via the **native protocol**. | **No**. It does not have to match the gossip seeds. |
| **Seed of a new cluster** | Initial node enabling the cluster to initialize and accept other nodes. | Does not become a master node after the cluster forms. |

Cassandra does not use seeds as a **leader/master** to approve every query. When the Java Driver sends a `SELECT` to any node, that node can serve as coordinator without consulting a seed. The query's partition key and replication configuration determine which replicas participate.

Seeds may be contacted more frequently in the gossip mechanism, so choose **stable nodes with reliable networking**. Even so, do not place all seeds on a single machine or availability zone.

## 3. Gossip Initialization and Membership State Propagation

### 3.1. What Is Gossip?

**Gossip** is the decentralized state-exchange mechanism among Cassandra nodes. In Cassandra's architecture, each node periodically updates its heartbeat and exchanges information with known peers, optionally prioritizing a seed during certain exchange rounds. Data propagates gradually across the cluster rather than relying on a centralized membership table on a single node.

Gossip information typically includes:

- **Endpoint state:** which nodes are seen as up or unreachable.
- **Heartbeat/generation/version:** used to compare newer states against older information.
- **Token/topology information:** used to identify token range ownership, routing, and data movement.
- **Schema version information:** helps nodes know when schema metadata synchronization is needed (details depend on version).

**Gossip and failure detection are related but distinct.** Gossip distributes state information; each node uses its own signals and failure detector mechanism to decide whether a peer is responsive. A node can detect that a peer is down without a seed declaring "this node is dead."

### 3.2. How Does a New Node Learn the Cluster?

~~~mermaid
sequenceDiagram
    participant N as New Node D
    participant S as Seed A
    participant B as Node B
    participant C as Node C
    N->>S: Connect via internode, start gossip
    S-->>N: Known membership/topology state
    N->>B: Gossip directly with newly discovered peer
    B-->>N: Supplement/update membership information
    N->>C: Gossip and confirm state
    Note over N,C: If joining as a new node: determine tokens and bootstrap/stream data
    N->>B: Exchange internode data with source replica during bootstrap
    B-->>N: Stream data for relevant token ranges
    Note over N: Once required steps finish, node transitions to normal serving state
~~~

This diagram illustrates the logical flow. Not all data is sent from Seed A; **bootstrap data is streamed from the nodes holding the relevant data**, based on tokens and replication. Exact ordering, node state conditions, and metadata handling may vary by Cassandra version.

The process can be viewed in steps:

1. The node loads its cluster configuration, internode address, snitch/datacenter, and seed list.
2. The node contacts an available seed over an **internode connection** to initiate gossip exchange.
3. The node learns additional endpoints and continues propagating state with peers.
4. When joining a cluster that already holds data, the new node receives its assigned token ranges and **bootstraps/streams** corresponding data from existing replicas.
5. Once complete and operational checks pass, the node is seen as a normal member; nodes continue gossiping about topology.

**Membership discovery ≠ data copying.** Seeds assist with the discovery step; bootstrap/streaming belongs to data movement and can use non-seed peers.

### 3.3. Why Are Seeds Still Used Once a Cluster Is Stable?

According to Cassandra's gossip algorithm description, gossip rounds pick random peers and also include contacting a seed when appropriate. Seeds can therefore act as **frequently touched gossip points**, helping state propagate across the cluster. However, every node still gossips independently—there is no single "gossip server."

Consequences:

- Losing one seed does not immediately stop an entire healthy cluster from serving reads/writes.
- If **all seeds known to a new node are unreachable**, the new node may be unable to initiate the joining process.
- If a seed becomes overloaded or network-isolated, state discovery/propagation may slow down, especially during cluster scaling or recovery.
- Do not confuse losing a seed with losing the exact replica required for a query at the active consistency level.

## 4. Configuring `seed_provider` in `cassandra.yaml`

Cassandra declares seeds via `seed_provider` in `cassandra.yaml`. With `SimpleSeedProvider`, the list is a comma-separated string of seed endpoints. Example syntax per current Cassandra documentation:

~~~yaml
# cassandra.yaml excerpt (illustrative, not a complete configuration).
seed_provider:
  - class_name: org.apache.cassandra.locator.SimpleSeedProvider
    parameters:
      - seeds: "192.0.2.11:7000,192.0.2.12:7000"
~~~

The `192.0.2.x` IPs belong to a **documentation range** and must be replaced with the cluster's real internode addresses. In this example, Nodes A and B serve as seed contact points, and 7000 is the **storage/internode port**, not CQL port 9042.

Notes when applying:

- `SimpleSeedProvider` is the common seed provider implementation; a cluster management system may supply seeds differently. Verify the syntax for your **Cassandra version and deployment tooling**.
- On versions/configurations supporting `host:port`, use the **actual internode port**—do not default to 7000 if `storage_port` has been changed.
- Seeds can be declared using IPs or hostnames that resolve reliably via a supported mechanism. Inaccurate DNS or uncontrolled IP changes prevent nodes from communicating.
- The seed list is **not a list of all replicas**, does not set the replication factor, and does not automatically allocate tokens or balance data.
- Every node must have a usable seed list; nodes **do not strictly have to share an identical list**, though consistent list management simplifies operations and prevents configuration drift.

### 4.1. Which Network Do Seed Ports and Addresses Belong To?

| Parameter / Port | Purpose | Used with Seeds? |
| --- | --- | --- |
| `listen_address`, `broadcast_address` | Internode address used by Cassandra peers. | **Yes**: seeds must be reachable via their internode network addresses. |
| `storage_port`, default `7000/TCP` | Node-to-node communication, gossip, and related messages. | **Yes**: seed endpoints normally use this port. |
| `ssl_storage_port`, typically `7001/TCP` | Legacy internode TLS port, depending on version/configuration. | Only when the deployment actually uses it; many newer versions run TLS on 7000. |
| `rpc_address`, `broadcast_rpc_address` | Native client address used by the Java Driver/cqlsh. | **Do not** use as an internode seed endpoint, unless the real address happens to match and the port is still correct. |
| `native_transport_port`, default `9042/TCP` | Native CQL client-to-node. | **No**: this is the client port, not the gossip port. |
| `7199/TCP` | JMX for `nodetool` (common). | **No**: used for administration, not seed discovery. |

On servers with two network interfaces, the seed address must be the **internode broadcast endpoint** reachable by nodes in the cluster. The address used by the Java Driver may be completely different.

Example on Node A:

~~~yaml
# Internode address pair for Node A.
listen_address: 192.0.2.11
broadcast_address: 192.0.2.11
storage_port: 7000

# Native client, which may use a separate network.
start_native_transport: true
rpc_address: 198.51.100.11
broadcast_rpc_address: 198.51.100.11
native_transport_port: 9042
~~~

This configuration is an **explanatory excerpt**, not enough to launch a real cluster. You still need `cluster_name`, snitch, token/datacenter settings, auth/TLS, resources, and corresponding options. Additionally, the server must actually own the bound IPs; never copy documentation IPs into a live system.

## 5. Lab: Creating a Three-Node Cluster and Choosing Seeds

Suppose we have three nodes A, B, and C in the same datacenter/rack or across different racks:

| Node | Illustrative Internode Address | Seed? | Role During Initialization |
| --- | --- | --- | --- |
| A | `192.0.2.11:7000` | Yes | First node of the new cluster, initial gossip contact point. |
| B | `192.0.2.12:7000` | Yes, **after joining properly** | Redundant seed for nodes joining later. |
| C | `192.0.2.13:7000` | No | Regular member, learns topology from seeds. |

~~~mermaid
flowchart TD
    D["New Node D"] -->|"Start gossip / 7000"| A["Seed A"]
    D -.->|"Try backup seed if needed"| B["Seed B"]
    A <-->|"Internode gossip"| B
    B <-->|"Internode gossip"| C["Node C"]
    C <-->|"Internode gossip"| A
    D -->|"After learning topology"| C
~~~

### 5.1. Recommended Initialization Order to Understand the Mechanism

1. **Brand-new cluster with no data:** select Node A as the initial seed. On A, configure the cluster name, internode address, and appropriate seed list so A initializes the cluster. Start A and confirm it reaches a normal state.
2. **Join Node B:** let B join as a regular new node and **bootstrap successfully** from the existing cluster. Avoid configuring B as a seed beforehand if doing so causes B to skip auto-bootstrapping data from the live cluster.
3. Once B has joined properly, you can designate B as a **backup seed** using the appropriate configuration management mechanism and your version's change/restart procedure.
4. **Join Node C:** specify at least one live seed, preferably with fallback paths to A or B. Let C bootstrap, monitor gossip/streaming, and verify the node reaches normal state.

**Pitfall to avoid:** per Cassandra documentation, a node that sees itself as a seed behaves differently during bootstrap than a non-seed. For a **node that needs to bootstrap existing data from the cluster**, declaring itself a seed too early may skip necessary data streaming. A seed is not "a flag to toggle on any node right before its first boot." When deploying onto a cluster that already has data, follow the bootstrap/replace procedure for your exact version.

### 5.2. Monitoring the Joining Process

On an operational node with privileges, run:

~~~bash
# Ring membership state (U=Up, N=Normal, J=Joining).
nodetool status

# Endpoints and gossip states from the node's perspective.
nodetool gossipinfo

# Data transfer status during bootstrap/streaming.
nodetool netstats

# Check cluster info and visible schema versions.
nodetool describecluster
~~~

In `nodetool status`, a node may appear as `UJ` while joining and `UN` when operating normally. These are helpful indicators, but check **streaming, logs, and health checks** before considering expansion complete.

When a node receives new token ranges, relevant replicas may stream data to it. This process is **not the seed copying all data**. If data volume is large, monitor `nodetool netstats`, disk usage, latency, and operational limits.

## 6. Choosing Seeds in a Multi-Datacenter Environment

A good seed list prioritizes **availability and failure-domain diversity**, matching the real internode network:

- Have **more than one seed** in production so a temporarily stopped seed does not block new nodes from joining.
- With multiple datacenters, typically distribute seeds across **datacenters**, and within each datacenter choose nodes in **different racks/availability zones** where available.
- Pick stable nodes with adequate network/CPU; avoid concentrating seeds on a single power, network, or maintenance failure point.
- Do not declare **every node as a seed**. Seeds may be contacted more often during gossip; an oversized list does not automatically increase data availability.
- Manage the seed list in configuration management tooling so nodes always have at least one reachable live discovery path; avoid ad-hoc manual edits that cause drift across environments.
- When replacing a seed, keep **existing seeds available** during the transition and update configurations step by step according to your Cassandra version's operational procedure.

Example of a two-datacenter cluster with seeds in each location:

~~~yaml
# Example internode endpoint list; replace with real addresses.
seed_provider:
  - class_name: org.apache.cassandra.locator.SimpleSeedProvider
    parameters:
      - seeds: "192.0.2.11:7000,192.0.2.12:7000,198.51.100.11:7000,198.51.100.12:7000"
~~~

| Datacenter | Illustrative Seeds | Network Requirement |
| --- | --- | --- |
| `dc-east` | `192.0.2.11`, `192.0.2.12` | Nodes inside and outside the DC have permitted internode paths to the required seeds. |
| `dc-west` | `198.51.100.11`, `198.51.100.12` | Proper internode path alongside TLS/cluster membership policy. |

This is an **operational pattern**, not a rigid recommendation to "always use four seeds." Counts and placement depend on cluster size, topology, maintenance windows, and desired availability. Datacenters/racks are also determined by the snitch/metadata; **simply adding a seed IP does not create a new datacenter** and does not change keyspace replication.

### 6.1. Seeds and Replication Factor Are Independent Configurations

In CQL, a keyspace can declare replica counts per datacenter, for example:

~~~sql
-- Apply only if the real cluster has datacenters with these exact names.
CREATE KEYSPACE IF NOT EXISTS readings_prod
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc-east': 3,
  'dc-west': 3
};
~~~

The seed list supports **membership discovery**. `NetworkTopologyStrategy` together with token placement determines the **replicas** for each partition; the consistency level (such as `LOCAL_QUORUM`) determines how many replicas in the datacenter must respond for reads/writes. These three configurations solve distinct concerns.

## 7. Seeds Differ from Java Application Contact Points

The two settings look similar because both act as "starting points to connect," yet they operate on **two different protocol layers**:

~~~text
New Cassandra node --> internode seed:7000 --> gossip/topology --> bootstrap

Java application ----> native contact point:9042 --> driver discovery --> CQL coordinator
~~~

In Java Driver 4.x, contact points only help the application establish a session and discover nodes per driver policy. They are **not** the `seed_provider` list used by Cassandra nodes.

Java example, assuming the application can reach the native endpoints and knows the actual datacenter name:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import java.net.InetSocketAddress;

try (CqlSession session = CqlSession.builder()
        .addContactPoint(new InetSocketAddress("db-a.example.internal", 9042))
        .addContactPoint(new InetSocketAddress("db-b.example.internal", 9042))
        .withLocalDatacenter("dc-east")
        .build()) {

    var row = session.execute(
        "SELECT cluster_name, data_center FROM system.local").one();
    if (row != null) {
        System.out.println(row.getString("cluster_name"));
    }
}
~~~

`dc-east` is an example; replace it with the **real datacenter**, which can be checked via `SELECT data_center FROM system.local;` in cqlsh. The Java Driver can discover additional native endpoints after connecting to a contact point. Those endpoints must be reachable from the application machine; they may share an IP with an internode seed if the node uses the same interface, but **the ports and purposes differ**.

**If all seeds temporarily go down:** a running cluster can still serve CQL requests depending on replicas/CL and network state. Conversely, if the application's contact points are unreachable, a new application instance may fail to initialize a session even while the internal ring is healthy. Both failure classes must be checked independently.

## 8. Seeds, Token Ring, and Data Operations: Connecting Through an Example

Consider a sensor events table designed for the query "events of a device on one day":

~~~sql
-- Keyspace for a single-node Cassandra lab; do not use as a production RF template.
CREATE KEYSPACE IF NOT EXISTS seed_discovery_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS seed_discovery_lab.events_by_device_day (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  value double,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

INSERT INTO seed_discovery_lab.events_by_device_day
    (device_id, event_day, event_time, event_id, value)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:00:00Z',
        11111111-1111-4111-8111-111111111111, 25.1);

SELECT event_time, value
FROM seed_discovery_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';
~~~

Here `(device_id, event_day)` is the **composite partition key**. With multiple nodes, Cassandra computes the token to choose replicas according to the **token ring and replication**. Seeds only help a joining node **learn ring information**; they do not dictate that "all data for sensor-01 will be stored on the seed."

With RF = 1 in the lab, multi-replica failover/quorum cannot be practiced. To evaluate `LOCAL_QUORUM` or the impact of internode failures, you need a multi-node cluster with realistic per-datacenter replication factors. Adding more seeds **does not** increase the replica count.

## 9. Checking Seeds When a Node Fails to Join the Cluster

### 9.1. First, Verify the Right Address and Port

From the **host of the node attempting to join**, test TCP connectivity to the seed's **internode endpoint**:

~~~bash
# Example IPs; replace with real seed IPs on storage_port.
nc -vz 192.0.2.11 7000
nc -vz 192.0.2.12 7000
~~~

On Windows with PowerShell:

~~~powershell
Test-NetConnection -ComputerName 192.0.2.11 -Port 7000
~~~

If the network uses TLS or a different port, verify that exact configuration. **An open TCP port proves only basic network reachability**; it does not guarantee gossip handshake, cluster name, internode authentication, or snitch/config validity.

### 9.2. Inspecting the Seed and the New Node

~~~bash
# Run on nodes with Cassandra administrative privileges.
nodetool status
nodetool gossipinfo
nodetool describecluster
nodetool netstats
~~~

Cross-check these items:

1. Seeds declared in `seed_provider` use the right IP/DNS and **`storage_port`**, not `9042`.
2. The seeds are actually running and bound/listening on reachable internode addresses.
3. `cluster_name` and datacenter/rack/snitch configuration match the target cluster.
4. Both the new node's and the seeds' `listen_address`/`broadcast_address` are valid; if NAT is present, bidirectional routing must be intentionally designed.
5. Firewalls/security groups permit the necessary internode traffic, and server-to-server TLS settings align.
6. Running Cassandra versions have compatible settings during rolling upgrades; check logs if gossip or streaming is rejected.
7. If gossip already sees the node but bootstrap has not completed, focus on **streaming, disk, tokens, and logs**, rather than endlessly changing seeds.

`nodetool status` observes the ring from the queried node's perspective and is not an exhaustive test of every network path. `nodetool gossipinfo` shows endpoint states in gossip; `nodetool netstats` tracks streaming progress. Logs on the new node and seeds usually provide clearer root-cause details than a single status line.

### 9.3. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Multi-node cluster still has `seeds: "127.0.0.1:7000"` on every node | Each node contacts only its own loopback interface. | Configure real internode endpoints with at least one live, routable seed. |
| New node cannot reach any seed | Seed down, wrong DNS, firewall, wrong port/TLS, or missing route. | Test connectivity from **the new node itself** to each seed and compare configurations. |
| TCP 7000 works but gossip does not learn peers | Mismatched cluster name/snitch/internode TLS, handshake failure, or incompatible Cassandra versions. | Check logs, `nodetool gossipinfo`, and corresponding settings. |
| New node declares itself a seed, bootstrap behaves unexpectedly | Incorrect procedure adding it as a seed before receiving tokens/data. | Follow the standard node addition procedure, verify bootstrap, and only then consider updating the seed list. |
| One seed stops working yet CQL queries keep running | Seeds are neither mandatory coordinators nor masters. | Verify replicas/consistency and restore seed redundancy per plan. |
| Failed seeds prevent adding a new node | No remaining reachable seed for the new node to contact. | Restore a seed or configure live seed contact points following cluster procedures. |
| Java Driver fails on `9042` even though seed `7000` works | Misconfigured native transport/rpc address, client TLS, or auth. | Check `native_transport_port`, `broadcast_rpc_address`, and driver contact points. |
| `nodetool status` stays in `UJ` for a long time | Node discovered the cluster, but bootstrap/streaming is slow or failing. | Check `nodetool netstats`, logs, disk, internode network, and source replicas. |
| One datacenter cannot see nodes in another DC | Cross-DC networking, firewall, seed topology, or gossip/version issue. | Inspect inter-DC internode endpoints, snitch/datacenter config, and logs. |

### 9.4. When Replacing or Removing a Seed

Do not stop all seeds at once to "clean up the list." On a live system:

1. Select a backup seed that is **already a normal member** of the cluster in an appropriate failure domain.
2. Intentionally update the seed list via configuration management and apply changes according to your version's procedure.
3. Keep existing live seeds running during the transition; verify that a new node can reach at least one healthy seed.
4. Remove old seeds from configuration and maintenance procedures only after nodes have picked up the change and topology is stable.

If you need to **fully replace a node** serving as a seed, you must also handle data/tokens and ring membership via the **replace/decommission/bootstrap** procedure. Removing a seed IP from YAML does not remove a node from the ring; replacing a node that holds data is not just changing the seed list.

## 10. Self-Practice Exercises

1. Sketch the path **New Node D → Seed A → peers B/C → bootstrap data**. Explain why bootstrap data is not necessarily streamed from the seed.
2. In a three-node cluster, choose two seeds with stable networking and write a `seed_provider` excerpt. Clearly identify which port is internode and which port is for `cqlsh`/Java Driver.
3. Suppose a node configures its seed as `127.0.0.1` while running on a different machine from the actual seed. Predict the issue and propose a corrected configuration.
4. Suppose Seed A goes down while Node B is a live backup seed. Contrast the impact on (a) CQL queries from already-connected clients and (b) a new node preparing to join.
5. Run `nodetool status`, `nodetool gossipinfo`, and `nodetool netstats` in an appropriate lab. Point out the fields that help determine membership and bootstrap status.
6. Explain why a new node should not be designated as a seed before bootstrapping into a cluster that already contains data.
7. With two datacenters, propose a seed distribution across racks/DCs to avoid a single point of failure. Explain why not every node needs to be a seed.
8. Connect with the Java Driver to a native contact point on `9042` and explain why Java contact points do not have to be `7000` seeds.
9. With RF = 3 in one datacenter, calculate the minimum replicas required for `LOCAL_QUORUM`. Explain why changing the seed list does not change the answer.

**Completion criteria:** distinguish seeds, coordinators, and replicas; describe gossip and bootstrap; write seed configurations for the right internode network; diagnose unreachable-seed failures; and accurately explain the independent role of the seed list relative to replication/consistency and Java clients.

## References

- [Apache Cassandra — Dynamo architecture: Gossip, Seeds and Ring Membership](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html): gossip algorithm and the role of seeds in membership discovery.
- [Apache Cassandra — cassandra.yaml configuration](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html): `seed_provider`, `SimpleSeedProvider`, `listen_address`, `broadcast_address`, and internode ports.
- [Apache Cassandra — Frequently Asked Questions](https://cassandra.apache.org/doc/stable/cassandra/overview/faq/index.html): seeds, startup behavior, and operation when a seed fails.
- [Apache Cassandra — Adding, replacing, moving and removing nodes](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/topo_changes.html): bootstrap, token allocation, and observing streaming.
- [Apache Cassandra — Glossary: Seed](https://cassandra.apache.org/_/glossary.html): concise definition of a seed node.
- [Apache Cassandra Java Driver 4.x](https://docs.datastax.com/en/developer/java-driver/4.17/): native client contact points and initializing `CqlSession`.
