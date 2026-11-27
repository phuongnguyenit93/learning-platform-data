# Designing Datacenters/Racks Around Real Failure Domains in Apache Cassandra

## 1. Start from Failure Domains, Not Datacenter Names

Apache Cassandra is a **distributed wide-column** database: data is partitioned by **partition key**, replicated across multiple **replicas**, and can serve CQL queries from Java applications across multiple locations. To keep the system serving traffic when failures occur, replicas must be placed in locations that **do not fail together from a single root cause**.

A **failure domain** is the scope of resources that can go down simultaneously due to a shared fault. For example:

- A server fails → all processes running on that host are lost together.
- A rack sharing a power source or ToR (*top-of-rack*) switch fails → multiple machines in that rack lose connectivity.
- An availability zone (AZ) loses power, networking, or storage → multiple racks/VMs in that zone may be affected together.
- A datacenter, geographic region, or WAN link fails → nodes across the entire region may become unreachable.

In Cassandra, the two key topology labels are **datacenter (DC)** and **rack**. They do not inherently create fault tolerance: Cassandra only knows the labels you declare via the **snitch**. If you place all three replicas in the same physical zone while declaring three different racks, the placement algorithm may still assume they are independent even though all three are lost together when the zone fails.

**Design principle:** map Cassandra topology onto the meaningful failure domains of your underlying infrastructure, then verify whether the replication factor and consistency level can still be satisfied when *a real failure domain actually disappears*.

## 2. Three Layers to Separate: Node, Rack, and Datacenter

| Layer | What Cassandra Sees | Real Failure Domain It Should Reflect | Example |
| --- | --- | --- | --- |
| **Node** | A Cassandra instance with a host ID, address, and token ownership | Independent machine/VM | VM `cassandra-a1` |
| **Rack** | Group of nodes sharing a rack label within a DC | Physical rack, independent power/switch, or AZ depending on infrastructure | `rack=az-a` |
| **Datacenter** | Group of nodes sharing a DC label; replication and local CL are evaluated per DC | A datacenter/region or group of AZs with suitable interconnect latency | `dc=region-a` |

A common cloud example: **one region maps to one Cassandra DC**, and **each AZ in the region maps to one Cassandra rack**. This is a *reference mapping*, not a universal rule for every cloud setup.

For on-premises deployments, a rack can correspond to a physical cabinet if power and ToR switches are truly independent. However, if multiple racks share a single PDU/UPS or core network switch, you must evaluate whether that rack label provides the independence your application expects.

### Illustration of Two DCs, Three Racks Each

```text
                       CASSANDRA CLUSTER
               NetworkTopologyStrategy (RF: 3 + 3)

        DC region-a                        DC region-b
   +----------------------+           +----------------------+
   | rack az-a1: Node A1 |           | rack az-b1: Node B1 |
   | rack az-a2: Node A2 |           | rack az-b2: Node B2 |
   | rack az-a3: Node A3 |           | rack az-b3: Node B3 |
   +----------------------+           +----------------------+
     intra-region network               intra-region network
                 <-------- WAN -------->

    Within each DC: the 3 replicas of a partition are preferentially
    placed on different racks when topology permits.
```

The diagram illustrates only **one partition** with RF = 3 in each DC. A real cluster can have multiple nodes per rack, multiple token ranges, and keyspaces with different RFs.

## 3. Distinguishing Node, Rack, and DC Fault-Tolerance Objectives

Before provisioning a cluster, translate business requirements into concrete resource-loss scenarios.

| Scenario | Design Conditions to Examine | Expected Outcome |
| --- | --- | --- |
| Single node failure | Remaining replica count, CL, spare capacity | Reads/writes still achieve CL |
| Loss of a rack/AZ | Are replicas truly in independent racks? | Losing one rack does not lose all copies |
| Loss of an entire DC | Does the remaining DC have sufficient RF and node count? Can the application fail over across regions? | Can serve from the other DC according to a prepared policy |
| WAN partition between two DCs | Is CL local or global? Does the application write in one or both DCs? | Do not implicitly assume both sides always see the latest data |
| Shared network outage across both DCs | Do the DCs truly have independent network paths? | Have a plan to mitigate correlated failures |

**RTO** (*recovery time objective*) is the target time to restore service; **RPO** (*recovery point objective*) is the acceptable level of data loss. Having multiple replicas does not automatically reduce RTO/RPO to 0: they also depend on the commit log, cross-DC synchronization, CL, concurrent failures, backups, and application failover orchestration.

### Replica Distribution Does Not Replace Spare Capacity

Suppose a DC has three racks, one node per rack, and RF = 3. When one rack is lost, the remaining two nodes may be enough for `LOCAL_QUORUM`. However, they must absorb additional CQL traffic, compaction, and repair load. If each node was already running near CPU/disk limits before the outage, **quorum may still exist numerically while latency/timeouts breach the SLA**.

The design must simultaneously satisfy:

1. **Replica placement:** enough copies remain available.
2. **Quorum availability:** enough responses remain to meet the CL.
3. **Capacity headroom:** the surviving nodes can serve peak traffic.
4. **Operational recovery:** a post-incident recovery/repair runbook is in place.

## 4. Configuring Replication with NetworkTopologyStrategy

With multiple DCs, the standard strategy for specifying RF per DC is `NetworkTopologyStrategy` (NTS). For example, using two DCs named `region_a` and `region_b`, each with at least three nodes placed across appropriate failure domains:

```sql
CREATE KEYSPACE IF NOT EXISTS orders_global
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'region_a': 3,
    'region_b': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS orders_global.orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id text,
    state text,
    updated_at timestamp
);
```

Key properties to remember:

- `RF = 3` in `region_a` means **three replicas per partition in that DC**, not that every node stores a complete copy of the entire table.
- `RF = 3` in `region_b` represents **three additional replicas**, stored by the nodes in that DC.
- Cassandra attempts to place replicas on **different racks** within a DC when topology and available racks allow. If there are fewer racks than RF, multiple replicas may share a rack.
- DC names in CQL must match **exactly** the DC names reported by the snitch on the nodes.
- Altering RF in the schema **does not immediately synchronize missing data across all nodes**; changing replication requires a streaming/rebuild/repair procedure appropriate for your version.

For multi-DC production clusters, do not use `SimpleStrategy` as a substitute for NTS. `SimpleStrategy` does not model replica placement by DC/rack for multi-region fault tolerance.

### RF Must Be Evaluated Alongside Rack Count

| Configuration Within a DC | Single-Rack Loss Scenario | Remarks |
| --- | --- | --- |
| RF 3, three independent racks, replicas spread across all three | Two replicas may remain | Can serve `LOCAL_QUORUM = 2` if surviving nodes are healthy |
| RF 3, only two racks | One rack may hold multiple replicas | Losing the rack holding two replicas can make quorum unattainable |
| RF 3, three declared racks sharing physical power/network | Shared power/network fault can take down all three | Rack labels do not protect against correlated failures |
| RF 2, two racks | Losing one rack leaves one replica | `LOCAL_QUORUM = 2` can no longer be achieved |
| RF 3, three racks, but one rack holds many hot partitions | Replicas may be properly distributed, yet load is uneven | Must evaluate hot partitions, tokens, and capacity—not just rack count |

Choosing RF affects storage cost, write bandwidth, repair overhead, and fault tolerance. A higher RF does not replace proper failure-domain design and capacity headroom.

## 5. Checking Consistency Levels Across Failure Domains

Assume both DCs have RF = 3. The total number of copies of a partition is 6.

| Consistency Level | Required Responses in This Example | What Happens if All of `region_a` Is Lost |
| --- | --- | --- |
| `LOCAL_ONE` in `region_b` | 1 replica in `region_b` | Can serve if at least one healthy replica remains |
| `LOCAL_QUORUM` in `region_b` | 2 of 3 replicas in `region_b` | Can serve if two healthy replicas remain |
| `QUORUM` (cluster-wide) | 4 of 6 total replicas | Unattainable if only the 3 replicas in `region_b` remain |
| `EACH_QUORUM` (for regular writes) | Quorum in **each DC**, i.e., 2 + 2 | Unattainable because `region_a` does not respond |
| `ALL` | All 6 replicas | Unattainable |

**Note on `EACH_QUORUM`:** this is a write CL, not a standard read option equivalent to `LOCAL_QUORUM`.

With `LOCAL_QUORUM`, responses within a single DC are counted independently. It removes WAN dependency from the client acknowledgment path, but **does not prove that every DC has written or read the same version at that moment**.

### During a WAN Outage, What Is Guaranteed?

Suppose an application in `region_a` writes a mutation at `LOCAL_QUORUM`:

1. The coordinator sends the mutation to the corresponding replicas according to placement; distribution may include the other DC.
2. The application can receive a success response once enough replicas **within `region_a`** acknowledge.
3. If the WAN is down, replicas in `region_b` might not yet have the new mutation.
4. An application in `region_b` reading at `LOCAL_QUORUM` may still observe the stale value.
5. After the network recovers, hinted handoff and **anti-entropy repair** must be considered to ensure data convergence, especially after prolonged outages.

This is not automatically a **multi-region linearizable database** simply because two DCs are used. For workloads requiring globally synchronized acknowledgment, you must analyze CL, WAN latency, availability, and operation type; do not blindly raise every request to `EACH_QUORUM` without measuring the impact.

### The Quorum Formula Only Holds Within Its Defined Scope

With RF = 3 in a single DC:

```text
LOCAL_QUORUM = floor(3/2) + 1 = 2

Any two quorums within the SAME set of three replicas must intersect.
Two local quorums in TWO DIFFERENT DCs are not guaranteed to intersect.
```

You must distinguish **quorum intersection** from **physical fault tolerance**. If replicas share the same real failure domain, multiple replicas can be lost simultaneously, rendering quorum math purely theoretical.

## 6. Mapping Racks from Physical Infrastructure into the Snitch

The snitch is how Cassandra learns which **DC/rack** each node belongs to. With `GossipingPropertyFileSnitch`, DC/rack information is typically configured via `cassandra-rackdc.properties` on each node.

Example on node A1 in zone `az-a1`:

```properties
dc=region_a
rack=az-a1
```

Example on node A2 in zone `az-a2`:

```properties
dc=region_a
rack=az-a2
```

Example on node B1 in the other region:

```properties
dc=region_b
rack=az-b1
```

In deployments using `cassandra.yaml`, the corresponding snitch is selected with an example setting such as:

```yaml
endpoint_snitch: GossipingPropertyFileSnitch
```

The snippets above **illustrate values only** and are not a complete startup configuration. Parameters and deployment mechanisms may differ across Cassandra 3.x/4.x/5.x or cluster management platforms; some systems use a different snitch or an operator that assigns topology automatically.

### Logical Names Must Match Physical Reality

| Logical Label | Good Practice | Dangerous Practice |
| --- | --- | --- |
| `dc=region_a` | Nodes belong to a region with matching latency/operational coordination | Mixing machines separated by high-latency WAN into a single DC without evaluating CL |
| `rack=az-a1` | Nodes in the same AZ share a rack; different AZs get different racks | Assigning three different racks to three VMs all located in the same AZ |
| `rack=rack-01` on-prem | Reflects physical power, ToR, and isolation boundaries | Multiple "different" racks sharing the same network/power single point of failure |
| `dc=region_b` | RF and availability of `region_b` are managed independently | Placing nodes in `region_b` while declaring `dc=region_a` to avoid altering the keyspace |

**Do not change the DC/rack of a live node and simply restart it** as a shortcut to "relocate replicas." Cassandra uses topology to determine placement; changing labels can alter replica sets, disrupt reads/writes, and require data movement. You must follow a topology-change procedure supported by your version and operations team.

## 7. Anti-Patterns That Break Failure-Domain Design

### 7.1. One Rack Per Node, All Running in the Same Zone

Cassandra sees multiple racks and assumes it can place replicas independently; however, if the zone goes down, everything disappears. Adding labels does not create new power feeds or network paths.

### 7.2. Using a Single DC Spanning a High-Latency WAN

If nodes within the same DC are separated by tens or hundreds of milliseconds, `LOCAL_QUORUM` may have to wait across the WAN for two acknowledgments. As a result, local latency is no longer "local" and depends on inter-region link stability.

### 7.3. Creating a New DC but Forgetting Keyspace Replication

If a keyspace only declares `region_a: 3`, nodes in `region_b` can join the cluster without becoming replicas for that keyspace. Applications in the new region do not automatically gain three copies of the required data just because new nodes exist.

### 7.4. Three Replicas Sharing a Non-Redundant Resource

Three VMs might reside on different hosts while sharing the same storage appliance, top-of-rack uplink, or a common dependent network policy. When that shared point fails, RF = 3 still loses its fault tolerance.

### 7.5. Checking Only That Nodes Report "UN"

`nodetool status` reporting Up/Normal is a membership signal; it **does not guarantee** that replication is complete, DC/rack labels are accurate, repair is keeping up, or the Java Driver can reach CQL endpoints from another region.

### 7.6. Assuming the Driver Automatically Fails Over to Another DC

The Java Driver typically routes according to the configured **local datacenter**. Failing an application over to another DC when an entire DC fails must be designed upfront: connectivity, routing, DNS/service discovery, authentication, the new local DC setting, and tolerating potentially unconverged data. You cannot rely on the driver automatically using a remote DC in every scenario.

## 8. Node Allocation and Fault-Tolerance Calculations

A sample design has two regions, three AZs per region, and one node per AZ:

| DC | Rack/AZ | Example Node | Target Replicas per Partition |
| --- | --- | --- | --- |
| `region_a` | `az-a1` | A1 | 1 in this AZ when RF3 is evenly distributed |
| `region_a` | `az-a2` | A2 | 1 in this AZ when RF3 is evenly distributed |
| `region_a` | `az-a3` | A3 | 1 in this AZ when RF3 is evenly distributed |
| `region_b` | `az-b1` | B1 | 1 in this AZ when RF3 is evenly distributed |
| `region_b` | `az-b2` | B2 | 1 in this AZ when RF3 is evenly distributed |
| `region_b` | `az-b3` | B3 | 1 in this AZ when RF3 is evenly distributed |

Under the ideal assumptions above:

- Loss of A1: `region_a` still has A2 and A3, which can satisfy `LOCAL_QUORUM` in `region_a`.
- Loss of all of `region_a`: clients switch to `region_b` **if cross-region failover capability is prepared**; `region_b` still has three replicas, enough for local `LOCAL_QUORUM`.
- WAN cut: each region can still serve local quorum on the data it holds, **but data freshness may differ between regions**.
- Loss of two AZs in the same region: that region is left with only one replica, insufficient for RF3 `LOCAL_QUORUM`.

For production, do not size capacity as "just enough for three nodes across three AZs" while ignoring the scenario where one AZ is lost and the remaining two AZs carry the load. If the application requires uptime across an AZ outage, the remaining nodes must have enough I/O, CPU, RAM, disk space, and network bandwidth to serve the remaining traffic.

### When a Rack Has Multiple Nodes

Cassandra can place different partitions/tokens across multiple nodes within the same rack, as long as replica placement distributes each partition across racks as widely as topology permits. You do not have to have strictly one node per rack.

What matters is **preventing correlated failures** and maintaining **resource balance**. If one rack has several times as many nodes as another, the cluster may not achieve ideal load balance even though NTS recognizes three racks. Inspect per-keyspace ownership, disk usage, token distribution, and actual hotspots.

## 9. Data, Connectivity, and Networking Between Two DCs

Multi-DC Cassandra may need to exchange:

1. **Mutation replication:** the coordinator distributes writes to replicas in the relevant DCs.
2. **Gossip/membership:** nodes learn topology and member states.
3. **Streaming:** adding nodes/DCs, rebuilding, changing topology, or repairing discrepancies.
4. **Repair:** validation and streaming to reconcile replicas, which may traverse the WAN.
5. **CQL clients:** applications typically connect to coordinators in the local DC; failover must plan routes to the other region ahead of time.

Inter-DC links must be evaluated for bandwidth, latency, packet loss, firewall/TLS rules, and independence from correlated failures. Do not simply open the CQL port and conclude the topology is complete; **internode communication and streaming** must also be reachable.

### Setting Operational Thresholds for DC-Loss Scenarios

| Resource or Metric | Before Outage | During Single-DC Outage | After Recovery |
| --- | --- | --- | --- |
| Quorum | Each DC has enough replicas per RF | Surviving DC must independently satisfy chosen CL | Re-verify placement and run repair |
| Read/write p95/p99 | Per-DC baseline | Concentrated load and latency may increase | Re-measure after streaming/repair |
| Network | Normal mutations and gossip | Cross-region client failover traffic may surge | Hinted handoff and repair/streaming can cause bursts |
| Disk | Data at each replica | Load concentrates on surviving DC | Repair/compaction need headroom |
| Data | DCs may briefly diverge | Disconnected DC misses mutations | Must verify convergence before declaring recovery complete |

**Do not look only at the count of Up nodes.** A DC that still meets quorum can still breach SLOs if disks saturate or CQL p99 spikes.

## 10. Hands-On CQL: Two Keyspaces with Different Fault-Tolerance Requirements

The examples below assume the cluster already has nodes deployed in `region_a` and `region_b`. Use your real topology and verify configuration before running.

### Keyspace with Replicas in Only One DC

```sql
CREATE KEYSPACE IF NOT EXISTS orders_local
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'region_a': 3
};
```

Here, `orders_local` **has no RF for `region_b`**. Deploying six nodes across two DCs does not automatically make this keyspace's data present in `region_b`.

### Keyspace with Replicas in Both DCs

```sql
CREATE KEYSPACE IF NOT EXISTS orders_global
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'region_a': 3,
    'region_b': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS orders_global.orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id text,
    state text,
    updated_at timestamp
);

INSERT INTO orders_global.orders_by_id
    (order_id, customer_id, state, updated_at)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'customer-42',
    'PENDING',
    '2026-11-20 09:00:00+0000'
);

SELECT state, updated_at
FROM orders_global.orders_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

In `cqlsh` connected to a coordinator in each DC:

```text
CONSISTENCY LOCAL_QUORUM;
```

Cross-checking from two DCs **only makes sense once the keyspace has replicas in both regions and has been properly populated**. If a test cluster only has one DC or fewer nodes than RF, `LOCAL_QUORUM` may return an insufficient-replicas error.

### Why You Must Not Arbitrarily Change RF

Suppose a live keyspace only has `region_a: 3`, and you add `region_b: 3` via `ALTER KEYSPACE`. The DDL statement changes **replication metadata**, not ensuring that historical data is immediately streamed in full to every node in `region_b`.

You need a new-DC rollout runbook with **rebuild/streaming and repair** procedures appropriate for your version, monitoring range progress and completion status before shifting traffic. Consult `nodetool help rebuild` and your exact version's operational documentation; never run rebuild casually on production nodes just to test.

## 11. Java Driver 4.x: Selecting the Right Local Datacenter

In Java applications, `CqlSession` needs to know the **local datacenter** so the load-balancing policy selects coordinators close to the application. Java Driver 4.x example:

```java
import java.net.InetSocketAddress;
import java.util.Optional;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class RegionalOrderReader {
    private final CqlSession session;
    private final PreparedStatement selectState;

    public RegionalOrderReader(CqlSession session) {
        this.session = session;
        this.selectState = session.prepare(
            "SELECT state FROM orders_global.orders_by_id WHERE order_id = ?"
        );
    }

    public Optional<String> findState(UUID orderId) {
        BoundStatement statement = selectState.bind(orderId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

        Row row = session.execute(statement).one();
        if (row == null || row.isNull("state")) {
            return Optional.empty();
        }
        return Optional.of(row.getString("state"));
    }

    // Example configuration for an application deployed in region_a.
    public static CqlSession openRegionASession() {
        return CqlSession.builder()
            .addContactPoint(new InetSocketAddress("10.10.0.11", 9042))
            .withLocalDatacenter("region_a")
            .build();
    }
}
```

The addresses and region names in this example are illustrative only. In a real environment, you must properly configure redundant contact points, security, certificates, credentials, network reachability, and session lifecycle; **do not create a session per request**.

### Two Applications Across Two Regions

| Application | Configured Local DC | `LOCAL_QUORUM` Target | What to Keep in Mind |
| --- | --- | --- | --- |
| App A running near `region_a` | `region_a` | Two replicas in `region_a` with RF3 | May not wait for acknowledgments from `region_b` |
| App B running near `region_b` | `region_b` | Two replicas in `region_b` with RF3 | May temporarily see a different version than App A |

If App A must fail over to `region_b` when `region_a` fails, you must have an **application failover plan** covering the new local DC, endpoints, and consistency caveats. Do not assume `withLocalDatacenter("region_a")` automatically switches to `region_b` during an outage.

## 12. Playbook for Auditing Datacenter/Rack Design

### Step 1 — Map Real Failure Domains

List every node along with:

- Cloud region/site, AZ, physical rack, or power/switch group.
- Host/VM/hypervisor, storage type, network uplink, and power feed.
- The DC/rack labels Cassandra currently sees.
- Any shared resources that could take down multiple nodes simultaneously.

Flag pairs of nodes that **a single failure** could knock out together. If they are placed in different Cassandra "racks," revisit the design.

### Step 2 — Reconcile the Topology Observed by Cassandra

On operational nodes:

```bash
nodetool status
nodetool describecluster
nodetool status orders_global
```

`nodetool status` typically groups nodes by DC; combine it with snitch metadata and your infrastructure inventory to verify racks. `nodetool describecluster` helps inspect cluster details and schema versions, but **is not sufficient proof of power/network independence**.

Note that the `Owns (effective)` column can depend on keyspace/RF. With replication, the sum of ownership percentages across nodes **does not necessarily equal 100%** by simple addition.

### Step 3 — Verify Replication and CL Configuration

In `cqlsh`:

```text
DESCRIBE KEYSPACE orders_global;
CONSISTENCY LOCAL_QUORUM;
```

Ensure DC names in NTS match the snitch and that each DC has enough nodes/racks for the target design. Identify the CL used by each business flow, not just the default CL of a `cqlsh` session.

### Step 4 — Validate Failure Scenarios Without Breaking Production

In an **isolated lab/staging** environment, test:

1. Loss of one node in a rack: is local quorum still satisfied?
2. Loss of one AZ/rack: are there enough replicas and headroom?
3. WAN outage: do both DCs still serve local reads/writes, and how does data converge afterward?
4. Loss of a DC: do applications have a failover path and CQL connectivity to the surviving DC?
5. DC recovery: are streaming status, hinted handoff, repair, and p95/p99 stable?

Do not intentionally sever networks, stop multiple nodes, or alter live topology in production merely for simulation.

### Step 5 — Establish a Repair Schedule and Recovery Targets

**Intra-DC** repair can synchronize local replicas, but **does not automatically compare two DCs** if each is internally consistent while holding different data. When cross-DC convergence is required, the anti-entropy repair schedule must cover the appropriate token ranges and replicas across the relevant DCs.

Also monitor:

- How long a replica/DC is disconnected relative to `gc_grace_seconds` and hint retention limits.
- Data divergence after a disconnected region recovers.
- Tombstones/TTLs to mitigate the risk of deleted data resurrecting.
- WAN cost, disk I/O, compaction backlog, and p95/p99 during repair/streaming.

**Read repair does not replace anti-entropy repair** for partitions that are not read; compaction does not replace replica synchronization either. Backups and a recovery plan remain necessary even with a high RF.

## 13. Analysis Scenarios

### Scenario 1 — "Three Racks" in the Same AZ

Three nodes are assigned `rack1`, `rack2`, and `rack3`, all running as VMs in AZ-a. The keyspace has RF3. What happens if AZ-a goes down?

**Hint:** All three replicas can be lost simultaneously. Rack labels do nothing if they do not reflect three independent physical failure domains. You must fix actual placement and schedule a proper topology-change procedure.

### Scenario 2 — Two Racks with RF3

A DC has two racks: `rack-a` holds two replicas of a partition, and `rack-b` holds one replica. Read/write CL is `LOCAL_QUORUM`. If `rack-a` fails, can the cluster still serve local quorum requests for that partition?

**Hint:** No—only one replica remains, whereas RF3 local quorum requires two. You must design the number of failure domains and placement to match the rack failures you need to survive.

### Scenario 3 — Complete Loss of One Region

Two DCs each have RF3. The application is able to switch over to `region_b`. When `region_a` fails, `LOCAL_QUORUM` in `region_b` remains available, but what about cluster-wide `QUORUM`?

**Hint:** `region_b` still has three replicas, enough for a local quorum of two; however, a global quorum for a total RF of 6 requires four, so it cannot be reached. This is the trade-off between regional availability and global consistency.

### Scenario 4 — Two Local Quorums Returning Two Different Values

During a WAN partition, two applications each write data to the same partition in their own DC. Once the network reconnects, can a majority vote across DCs be used to pick the right value?

**Hint:** No. Cassandra uses timestamp/tombstone reconciliation rules, creating a risk of business-level conflicts. You need write rules, conflict prevention (such as appropriately scoped LWTs or write ownership partitioning), and proper repair; DC count is not a voting quorum.

### Scenario 5 — Adding `region_b` Without Data Present Yet

An administrator provisions nodes in `region_b` and runs `ALTER KEYSPACE` to add RF3. Immediately afterward, an application in `region_b` queries at `LOCAL_QUORUM` and receives missing data or errors. Can we conclude that Cassandra lost all the data?

**Hint:** Not yet. Changing RF metadata does not mean all replicas have been streamed. Verify the add-DC/rebuild/repair workflow, topology state, and data on each node before enabling application traffic.

## 14. Pre-Production Design Checklist

- [ ] Identify **real physical failure domains**: hosts, power, switches, AZs, DCs, and WAN links.
- [ ] Map **one Cassandra DC to an appropriate latency/operational boundary** and racks to independent fault-isolation groups.
- [ ] Do not assign fake racks just to create the appearance of distributed replicas.
- [ ] Verify `NetworkTopologyStrategy` and RF using the **exact DC names reported by the snitch**.
- [ ] Provision enough racks for the target RF and single-rack/AZ loss scenarios.
- [ ] Size capacity and latency for losing one node, one AZ, or an entire DC—not just theoretical quorum counts.
- [ ] Choose `LOCAL_QUORUM`, `QUORUM`, or other CLs based on real requirements, understanding the boundaries of local quorum across DCs.
- [ ] Intentionally implement Java Driver routing/failover, contact points, and local DC configuration.
- [ ] Verify internode networking, streaming/repair, security/TLS, and inter-DC links.
- [ ] Never change DC/rack on a live node or alter RF in production without a streaming/repair runbook.
- [ ] Maintain a cross-DC repair schedule when required, along with tombstone/TTL policies, backups, and a recovery plan.
- [ ] Test fault scenarios in staging and monitor p95/p99, error rates, and disk/network behavior after changes.

**Key takeaway:** In Cassandra, `datacenter` and `rack` are **labels for placement and consistency scoping**, not inherent proof of infrastructure independence. A reliable multi-DC architecture binds those labels to **real failure domains**, chooses RF and CL that withstand defined failure modes, and pairs them with spare capacity, streaming/repair, monitoring, and a Java application failover plan.
