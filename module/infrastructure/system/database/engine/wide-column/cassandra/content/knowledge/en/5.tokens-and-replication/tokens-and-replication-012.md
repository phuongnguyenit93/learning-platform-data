# Fault-Domain Replica Placement and Verifying Node Loss Tolerance

In Apache Cassandra, having multiple replicas only helps availability when those replicas do not share a single point of failure. This topic belongs to the **Tokens and Replication** chapter: from a partition key's token, Cassandra identifies the nodes holding data, and the replication strategy governs how copies are distributed across **data centers (DCs)** and **racks**. This lesson focuses on configuring and verifying fault-domain-aware replica placement, testing node or rack loss, and accurately explaining the limits of each read/write consistency level.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish tokens, replicas, replication factor (RF), data centers, racks, and fault domains; identify why a sufficiently large RF can still fail to survive losing an entire fault domain.
2. Design Cassandra topology with **NetworkTopologyStrategy**, choose per-DC RF, and assign nodes to racks matching real physical fault domains.
3. Compute required replica responses for **ONE**, **LOCAL_QUORUM**, **QUORUM**, and **EACH_QUORUM**, and predict whether an application can still read/write in each scenario.
4. Use CQL and operational tools to confirm the replicas of **a specific partition** before stopping nodes in tests.
5. Run controlled failure tests, record evidence, recover nodes, and assess post-incident data synchronization.

## 2. How Do Tokens, Replicas, and Fault Domains Differ?

Consider an event table queried by customer with partition key **customer_id**. Cassandra hashes the partition key value into a token. The token determines the partition's position on the token ring; from that position, the **replication strategy** selects the set of nodes storing replicas. With **virtual nodes (vnodes)**, one node can own multiple token ranges, so you cannot look at node name order or IP addresses to infer where each partition lives.

Concepts to keep separate:

| Concept | Meaning in fault-tolerant design |
| --- | --- |
| **Partition key / token** | Identifies the partition and its logical position on the token ring. Different partitions generally have different replica sets. |
| **Replica** | A partition's copy stored on a node. RF counts **replica nodes per DC** when using `NetworkTopologyStrategy`. |
| **Node** | A Cassandra process and its host/VM resources. One dead node temporarily takes down every replica placed on that node. |
| **Rack** | A topology label Cassandra uses to spread replicas. Can map to an availability zone (AZ), server rack, or independent power/network group. |
| **Data center (DC)** | A group of nodes treated by Cassandra as an operational domain, typically a geographic region or cluster segment. |
| **Fault domain** | A set of components that can fail together from a single cause: host, power feed, rack, AZ, DC, or network link. |

**Rack labels only work when they reflect physical infrastructure.** Assigning three distinct rack names to three VMs running on the same physical host does not create three independent fault domains. Conversely, if VMs span three AZs yet share one declared rack name, Cassandra cannot recognize that separation when placing replicas.

### Why Is NetworkTopologyStrategy Necessary?

**NetworkTopologyStrategy (NTS)** allocates the configured replica count per DC and tries to pick replicas across distinct racks within each DC. When enough racks exist for RF, the goal is placing each replica of a partition in a different rack. If **RF exceeds the rack count**, NTS must place additional replicas into already-used racks; losing one rack can then wipe out more than one replica of the same partition.

Avoid using **SimpleStrategy** to model multi-DC/multi-rack production systems: its replica selection lacks NTS's rack/DC-awareness. Cassandra does not auto-discover physical racks; proper snitch configuration and rack/DC metadata are prerequisites.

## 3. Reference Design: RF = 3 Across Three Racks

Suppose a DC has six healthy nodes spread across three independent racks:

| Fault domain | Nodes | Expected role with RF = 3 |
| --- | --- | --- |
| dc1 / rack-a | n01, n02 | Each partition has one replica on a node in rack-a. |
| dc1 / rack-b | n03, n04 | Each partition has one replica on a node in rack-b. |
| dc1 / rack-c | n05, n06 | Each partition has one replica on a node in rack-c. |

For an illustrative partition, the replica set might be n01, n04, n05:

~~~mermaid
flowchart TB
    client["Java/CQL client"] --> coord["Healthy coordinator"]
    coord --> ra["Replica n01 — rack-a"]
    coord --> rb["Replica n04 — rack-b"]
    coord --> rc["Replica n05 — rack-c"]
    subgraph dc1["Data center dc1"]
        ra
        rb
        rc
    end
~~~

Node names in the diagram **are purely examples**. Actual replica sets vary by partition key, token, and topology state; verify them with tools on the running cluster. Losing one rack may take down both nodes in that rack, yet under this layout any single partition loses at most **one of its three** replicas. That is the benefit of fault-domain isolation.

Compare two layouts:

- **Three nodes, one rack, RF = 3:** survives losing a single node for `LOCAL_QUORUM`, yet losing the rack takes down all three replicas.
- **Six nodes, three racks, RF = 3:** if each partition has one replica per rack, losing one rack leaves two replicas and `LOCAL_QUORUM` can continue operating.

RF alone does not guarantee how many fault domains can fail. Examine **both replica placement and the response count required by the consistency level**.

## 4. Calculating Read/Write Availability Under Replica Loss

In a DC with RF = 3, **LOCAL_QUORUM** requires this many responding replicas:

~~~text
local_quorum = floor(DC_RF / 2) + 1
RF = 3  ->  LOCAL_QUORUM = 2
RF = 4  ->  LOCAL_QUORUM = 3
RF = 5  ->  LOCAL_QUORUM = 3
~~~

Reads and writes are evaluated **independently by each operation's consistency level**:

| Consistency level | With RF = 3 in dc1 | Behavior on node loss |
| --- | --- | --- |
| **ONE** | Requires 1 replica response. | Can continue if at least 1 suitable replica remains, though reads may return stale data and writes are not yet majority-acknowledged. |
| **LOCAL_QUORUM** | Requires 2 replicas in the local DC to respond. | Can still succeed when losing 1 replica of the partition in that DC; cannot succeed when losing 2 replicas. |
| **QUORUM** | Requires majority across **total RF of all DCs** in scope. | Differs from `LOCAL_QUORUM` in multi-DC clusters; never infer from single-DC RF alone. |
| **EACH_QUORUM** | For **writes**, requires quorum in **each DC** holding replicas. | Fails if any DC cannot achieve quorum; not used as a standard read consistency level. |

**Overlap rule:** within the same DC at RF = 3, writing at `LOCAL_QUORUM` (W = 2) and reading at `LOCAL_QUORUM` (R = 2) yields **R + W = 4 > 3**, so the read and write response sets share at least one overlapping replica under stable topology. This reduces the risk of reading stale data after a successful write. It does **not** turn Cassandra into a linearizable transactional database in all cases: Cassandra also has timestamp-based conflict resolution, timeouts, concurrent writes, and multi-DC consistency boundaries.

Consistency level defines required acknowledgments, **not replica placement**. An operation succeeds only when enough replicas are **up, reachable, and respond before timeout**; `UP` status alone does not guarantee an operation will not time out.

### Forecast Table for One Partition in `dc1` (RF = 3)

| Incident affecting partition | Remaining available replicas | `LOCAL_ONE`/`ONE` | `LOCAL_QUORUM` |
| --- | ---: | --- | --- |
| No incident | 3/3 | Can succeed | Can succeed |
| Loss of exactly one replica node | 2/3 | Can succeed | Can succeed |
| Loss of a rack holding one replica | 2/3 | Can succeed | Can succeed |
| Loss of two nodes both holding the partition | 1/3 | Can succeed | Insufficient for quorum |
| Loss of all three replicas | 0/3 | Insufficient replicas | Insufficient for quorum |

"Can succeed" assumes the coordinator/client stay connected and surviving replicas reply in time. For a different partition, the very same two failed nodes might affect only one or zero replicas; testing must therefore identify **the exact endpoints of the partition key**.

## 5. Declaring DC/Rack and Creating the Keyspace

In a cluster using **GossipingPropertyFileSnitch**, each node needs **dc** and **rack** info matching its real fault domain, typically configured in **cassandra-rackdc.properties** alongside the snitch configuration. Example on node n01:

~~~properties
dc=dc1
rack=rack-a
prefer_local=true
~~~

Nodes in rack-b/rack-c use their respective rack names. How configuration is supplied and deployed may differ on Kubernetes, container images, or managed services. Check the environment's active snitch before editing; changing a node's rack/DC in a live cluster is a topology change requiring a dedicated procedure.

Once nodes register accurate topology, create the lab environment:

~~~sql
CREATE KEYSPACE IF NOT EXISTS lab_replica
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS lab_replica.events_by_customer (
  customer_id text,
  event_id timeuuid,
  event_type text,
  PRIMARY KEY ((customer_id), event_id)
) WITH CLUSTERING ORDER BY (event_id DESC);
~~~

In this example, the partition key is just **customer_id**. Each `customer_id` forms one partition with three replicas in `dc1`; **event_id** orders rows inside the partition. The table is designed to serve queries by `customer_id`, following Cassandra's **query-driven table design** principle.

When using **two DCs**, RF is declared **per DC**:

~~~sql
-- Multi-DC example option; do not run if cluster lacks dc2.
ALTER KEYSPACE lab_replica
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3,
  'dc2': 3
};
~~~

Declaring `dc1:3, dc2:3` means up to **six replicas per partition across both DCs**, not a total RF of three. Never set RF higher than the existing node count in a DC, and avoid setting RF higher than the rack count if the goal is at most one replica per rack for each partition.

**Changing RF on a populated cluster does not immediately copy old records onto new replicas.** Plan version-appropriate sync/repair, monitor completion, and verify data before considering the change complete. Do not run the multi-DC `ALTER` example on a lab cluster that only has `dc1`.

## 6. Confirm Replica Placement Before Injecting Failure

Perform these steps on a **test cluster**; never casually stop production nodes.

**Step 1 — Inspect topology seen by Cassandra.** On a node with `nodetool` access:

~~~bash
nodetool status
~~~

Check each DC, the **Rack** column, node addresses, and **UN** (Up/Normal) status. Cross-reference the DC/rack list against physical/AZ layout; never assume seeing three rack names means three independent power feeds or AZs exist. On a specific node you can also run:

~~~sql
SELECT data_center, rack FROM system.local;
~~~

Querying `system.local` only returns info for **the connected node**, not the entire topology.

**Step 2 — Write and read baseline data** via `cqlsh`:

~~~sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO lab_replica.events_by_customer
  (customer_id, event_id, event_type)
VALUES ('cust-001', now(), 'before-failure');

SELECT customer_id, event_id, event_type
FROM lab_replica.events_by_customer
WHERE customer_id = 'cust-001';
~~~

Record query output, timestamp, consistency level, and coordinator/client DC. Because `event_id` is generated via **now()**, save the actual ID if you want exact row-by-row comparison after the test.

**Step 3 — Identify replicas for partition `cust-001`**:

~~~bash
nodetool help getendpoints
nodetool getendpoints lab_replica events_by_customer cust-001
~~~

In versions providing **getendpoints**, the output lists the endpoints responsible for that partition key in the table. If your version/deployment lacks this command or uses different syntax, check `nodetool` help for your running version and use the equivalent replica lookup tool. Record endpoints alongside their DC/rack; **do not pick a random node to stop**. If a table has a composite partition key, formatting the key for the tool may differ from this simple text-key example.

**Step 4 — Pick the target node(s) to fail** from the **recorded replica set** and write down expectations: stopping one replica leaves 2/3; stopping two replicas leaves 1/3. Also ensure `cqlsh` can connect through a **surviving coordinator**; losing the specific coordinator you connected to tests client reconnection, not just replica quorum.

## 7. Verification Scenarios: Node Loss and Rack Loss

### Scenario A — Losing One Replica Node

1. Verify baseline: all three replicas of `cust-001` are `UN`; `INSERT` and `SELECT` at `LOCAL_QUORUM` succeed.
2. On **one selected replica endpoint**, simulate losing the Cassandra process using your lab control mechanism (e.g., stop the service). Wait until the cluster reports **DN** (Down/Normal) in `nodetool status`.
3. From a surviving coordinator, keeping **CONSISTENCY LOCAL_QUORUM**, run `SELECT` for previously written data, then `INSERT` a new event with `event_type` set to `during-one-down`.
4. Re-read the partition and compare rows before and after failure. Both reads and writes are expected to succeed if the remaining two replicas respond.
5. Restart the node; verify it returns to `UN`, check sync state, and inspect logs/metrics for errors or timeouts.

Example stop/start commands **only for lab machines using systemd**:

~~~bash
sudo systemctl stop cassandra
# Run test read/write operations from another node.
sudo systemctl start cassandra
~~~

On Kubernetes or managed environments, use the equivalent controlled fault action. Avoid testing on production without formal approval and recovery procedures.

### Scenario B — Losing an Entire Rack

Only run if the lab genuinely has three independent fault domains. Stop **all nodes belonging to one rack**, not just a single node. Verify beforehand that each tested partition holds **exactly one** replica in the target rack. With RF = 3 spread across three racks, two replicas remain in the other two racks and `LOCAL_QUORUM` can continue. If two replicas of a partition sat in the same rack due to misconfiguration or too few racks, expectations change.

Test multiple representative partition keys rather than only `cust-001`, because endpoint sets differ by token. Recover all nodes in the rack, monitor their return to `UN`, and verify data synchronization.

### Scenario C — Losing Two Replicas of the Same Partition

In the lab, pick **two endpoints that actually belong to `cust-001`'s replica set** and make them unavailable. `LOCAL_QUORUM` (needing 2/3) must **fail to be satisfied** for this partition; typical errors are **UnavailableException**, **ReadTimeoutException**, or **WriteTimeoutException** depending on detection timing and operation type.

You can switch a test read to **ONE** to observe one surviving replica answering, yet **never treat that result as proof of data consistency**. A `ONE` write succeeding while only one replica is up risks a window with a single copy and potential data loss if that last node fails before other copies catch up.

### Scenario D — Two DCs and Losing One DC

If both `dc1` and `dc2` have RF = 3, a **LOCAL_QUORUM request in `dc1`** requires two replicas in `dc1`; replicas in `dc2` do not count toward `dc1`'s local quorum. When `dc1` fails completely, the application can only fail over to `dc2` if **the client/driver is configured for appropriate routing/failover** and `dc2` has enough replicas. A successful `LOCAL_QUORUM` write in `dc1` **does not guarantee** `dc2` has received all data at that exact moment: the client response only awaits local quorum in `dc1`, while cross-DC replication and error handling continue asynchronously.

If business logic requires write confirmation in **every DC**, consider **EACH_QUORUM for writes** alongside its latency and availability trade-offs. Never blindly swap `LOCAL_QUORUM` for `QUORUM`/`EACH_QUORUM` across all queries: decide based on desired fault tolerance, client location, and consistency requirements.

## 8. Measure, Conclude, and Recover Properly

Create a test log for each **partition key** and test run:

| Data to record | How to observe |
| --- | --- |
| Actual topology and RF | `nodetool status`, keyspace config, rack ↔ physical fault-domain mapping table |
| Key's replica endpoints | `nodetool getendpoints` or version-equivalent tool |
| Injected fault | Which node/rack stopped, stop/recovery timestamps, `DN`/`UN` state |
| Consistency level | `CONSISTENCY` in `cqlsh` or per-statement config in Java driver |
| Outcomes and latency | Successful `SELECT`/`INSERT` counts, response times, timeouts, exception types |
| Post-recovery data | Rows written before/during fault, reads after stabilization, repair/sync status |

**Distinguish three failure signals:**

- **Unavailable:** the coordinator knows live replicas are insufficient for the requested consistency level.
- **Read/Write timeout:** execution was attempted, but insufficient responses arrived before deadline; a **write timeout outcome may be indeterminate** (some replicas may have applied the write).
- **Client connection failure:** may stem from contact point/coordinator outage or driver config; insufficient alone to conclude all replicas are down.

After each drill, restore services and verify nodes rejoin cleanly. **Hinted handoff** can replay some missed writes while a replica is briefly down, subject to retention windows and conditions; it does not replace **anti-entropy repair**. Succeeding on a few partition reads or seeing all nodes `UN` also **does not prove all replicas are synchronized**. After topology/replication changes, prolonged outages, or when guaranteed convergence is needed, run repair per your version and operational policy, monitoring until completion. Repair incurs I/O, CPU, and network cost, so schedule it appropriately.

### Java Application Integration

In the Java driver, keep two concerns separate:

1. **Local DC / routing:** configure the DC closest to the app, contact points, and connection policy so healthy coordinators are chosen; this does not replace proper server-side topology/racks.
2. **Per-statement consistency:** for example, with DataStax/Apache Cassandra Java Driver 4.x, set explicit consistency per statement:

~~~java
import com.datastax.oss.driver.api.core.ConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

SimpleStatement read = SimpleStatement.builder(
        "SELECT event_id, event_type FROM lab_replica.events_by_customer " +
        "WHERE customer_id = ?")
    .addPositionalValue("cust-001")
    .setConsistencyLevel(ConsistencyLevel.LOCAL_QUORUM)
    .build();

// session.execute(read) after CqlSession is configured with contact points/local DC.
~~~

APIs and configuration vary by driver version. Logs should record consistency level, exception type, and DC/coordinator to avoid confusing coordinator selection issues with missing replicas.

## 9. Common Design Mistakes

| Misconception | Consequence / fix |
| --- | --- |
| "RF = 3 means surviving any three failed nodes." | False: with `LOCAL_QUORUM`, an RF = 3 partition only maintains quorum when **at most one replica** of that partition is unavailable. |
| "We have three copies, so any rack can fail safely." | False if copies share a rack or logical racks do not map to physical fault domains. |
| "Six nodes in the DC and RF = 3 means six copies per partition." | False: there are three replicas in the DC; six nodes is total node count sharing distribution across many partitions. |
| "`LOCAL_QUORUM` in `dc1` counts `dc2` replicas too." | False: quorum only counts replicas **in the local DC** for `LOCAL_QUORUM`. |
| "`nodetool status` showing all `UN` means replica data is identical." | False: `UN` describes node status; verify synchronization/repair and read/write behavior. |
| "Stopping any two nodes tests losing two replicas." | Not guaranteed: those two nodes may not both hold the partition under test. |
| "Raising RF via `ALTER` immediately replicates all old data." | False: you must execute a repair/sync plan and verify completion. |
| "Switching to `ONE` during outages carries zero risk." | `ONE` lowers response requirements but increases stale-read risk and exposure when replicas lag behind. |

## 10. Practice Exercise and Completion Criteria

**Context:** `dc1` has six nodes across three independent racks (two nodes/rack), `NetworkTopologyStrategy` with RF = 3. Table `events_by_customer` is written and read at `LOCAL_QUORUM`.

1. Use `nodetool status` to verify DC/rack configuration looks right; draw a physical placement diagram.
2. Create three partitions with keys `cust-001`, `cust-002`, `cust-003`; for each key, list its three replica endpoints and corresponding racks. Verify whether each key has one replica in each rack.
3. For `cust-001`, predict read/write outcomes when stopping one endpoint; test and record evidence. Repeat for stopping the entire rack holding that endpoint (if lab permits).
4. Predict and test losing two endpoints of `cust-001` simultaneously; compare `LOCAL_QUORUM` with an observational `ONE` read.
5. Recover nodes, re-verify data written before and during the incident, and describe the procedure to ensure convergence plus how to detect timeouts or lagging replicas.

**Passing criteria** are met when the test log answers three questions: (a) **Which nodes/racks hold which partition?** (b) **For a given fault, how many replicas still respond compared to consistency level?** (c) **What evidence confirms the system returned to healthy state and data converged after the fault?**

### Self-Check Questions

- Why can a three-rack RF = 3 layout survive a rack outage while a single-rack layout cannot?
- With RF = 4 across three racks, why can losing one rack cause `LOCAL_QUORUM` to fail?
- Why is a "stop two nodes" test insufficient to prove a partition lost two replicas?
- Why does a `LOCAL_QUORUM` write in `dc1` not guarantee an immediate `LOCAL_QUORUM` read in `dc2` sees the new record if a cross-DC link issue occurs?

Key takeaway to retain: **fault tolerance is a property of each partition, its actual replica set, physical fault domains, and the consistency level used at request time**. Proper design must be backed by measured tests; replication protects availability while enough replicas survive, whereas repair and recovery workflows protect data convergence after nodes return.
