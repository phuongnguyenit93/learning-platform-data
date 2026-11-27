# NetworkTopologyStrategy and Per-Datacenter Replication Factor

## 1. Why Does Cassandra Need a Per-Datacenter Replication Strategy?

**Apache Cassandra** is a distributed wide-column database: a partition key is hashed into a token, and the token plus topology determines which nodes hold copies of that partition. Even in a single-datacenter (*datacenter*, abbreviated **DC**) deployment, replica placement must account for node and rack failures. When a system serves **multiple DCs**, the requirements become more complex:

- The DC closest to users must serve reads/writes with low latency.
- One DC may lose network connectivity or go offline while the remaining DC continues serving part of the workload.
- Each DC may have a different node count, capacity, and recovery requirement.
- New data might not yet have reached a remote DC at the moment a client receives an ACK from the local DC.

`NetworkTopologyStrategy` (**NTS**) is the replication strategy used to specify an **independent replication factor (RF) for each DC**. For example, `dc1: 3` and `dc2: 2` means each partition targets **three full replicas in `dc1` and two full replicas in `dc2`**, provided the topology can satisfy it.

**Key questions in this lesson:**

1. How does NTS use DC/rack, tokens, and RF to choose replicas?
2. How does per-DC RF differ from consistency levels such as `LOCAL_QUORUM`, `QUORUM`, and `EACH_QUORUM`?
3. When a DC fails or the inter-DC link drops, how far can applications continue reading/writing?
4. What else must be done when changing RF or adding a DC besides editing CQL?
5. How do you inspect topology, practice CQL, and scope the Java Driver properly?

**Learning objective:** design replication for two DCs, explain exact ACK thresholds, understand cross-DC data safety limits, build a rollout checklist, and avoid confusing NTS with repair, streaming, or automatic failover.

**Assumptions:** examples use standard full replicas, `Murmur3Partitioner`, and lab DC names `dc1`/`dc2`. Detailed snitch behavior, admin tools, configuration parameters, and replica selection algorithms may vary across Cassandra versions; do not apply lab commands directly to production.

## 2. Four Components That Determine Where a Partition Is Stored

Trace from the data key to physical storage locations:

~~~mermaid
flowchart TD
    P["Row partition key"] --> T["Partitioner computes token"]
    T --> R["Token ring and node metadata"]
    S["Snitch describes DC/rack of each node"] --> N["NetworkTopologyStrategy"]
    RF["Per-DC RF of the keyspace"] --> N
    R --> N
    N --> A["Replica set in dc1"]
    N --> B["Replica set in dc2"]
    A --> C["Copies serving reads/writes"]
    B --> C
~~~

| Component | Meaning | What Not to Confuse It With |
| --- | --- | --- |
| **Partition key** | Data hashed into a token; all rows with the same partition key go to the same replica set. | Clustering columns do not select a different DC on their own. |
| **Partitioner/token ring** | How partition positions are represented on the ring; e.g., Murmur3 tokens. | A token is neither chronological order nor a business ID. |
| **Snitch/topology metadata** | Tells Cassandra which DC/rack each node belongs to; influences replica placement and communication. | A `dc1` name in CQL does not create a DC or rack by itself. |
| **NetworkTopologyStrategy + RF** | Chooses the target number of replicas in **each DC** and distributes them according to topology. | RF is not the number of nodes that must ACK every request. |

With **virtual nodes (vnodes)**, a single node can own multiple tokens spread across the ring. The token count does not equal the replica count; **RF** determines how many nodes must store a partition in each DC.

### Intuitive Example with Two DCs

Suppose:

- `dc1`: nodes A1, A2, A3, A4.
- `dc2`: nodes B1, B2, B3.
- Keyspace uses `NetworkTopologyStrategy` with RF `dc1: 3` and `dc2: 2`.

A partition P might be stored on **A1, A3, A4** and **B1, B3**. Partition Q might be stored on different nodes. **This is an illustrative example, not an exact mapping**: actual replicas depend on cluster tokens and rack topology.

~~~text
              Datacenter dc1                  Datacenter dc2
        ┌────────────────────────┐       ┌──────────────────────┐
        │ A1  A2  A3  A4        │       │ B1  B2  B3          │
        │  ●       ●   ●        │       │  ●       ●          │
        │  P has 3 replicas     │       │  P has 2 replicas   │
        └────────────────────────┘       └──────────────────────┘

        Total target for P = 3 + 2 = 5 full replicas.
~~~

**Total nodes in a DC does not equal RF:** `dc1` has four nodes, yet partition P only needs three full replicas there. A node not storing P can still accept a request as **coordinator** and forward it to P's replicas.

## 3. How NetworkTopologyStrategy Differs from SimpleStrategy

Both strategies share the general purpose of determining replicas, but they fit different scenarios:

| Criterion | `SimpleStrategy` | `NetworkTopologyStrategy` |
| --- | --- | --- |
| RF configuration | A single RF for the entire keyspace. | RF declared separately per DC name, e.g., `dc1: 3`, `dc2: 2`. |
| DC/rack awareness | Not intended for actively optimizing replica placement across DCs/racks. | Uses DC/rack topology from the snitch when placing replicas. |
| Suitability | Simple labs/concepts or limited cases. | Multi-DC deployments and typically the practical choice for single-DC production as well. |
| Managing new DCs | No independent per-DC RF declaration. | Allows declaring RF for a new DC and executing data streaming/synchronization workflows. |
| Configuration risk | Does not control replica placement across failure domains as desired. | Wrong DC/snitch/rack names or RF exceeding capacity still yields poor placement/availability. |

NTS prioritizes spreading replicas across **different racks whenever possible** within each DC, reducing the risk of a single rack failure losing multiple copies. However:

- RF = 3 **does not create three racks**. If a DC only has two racks, Cassandra must operate within the physical topology limits.
- Misconfigured snitches can assign nodes to the wrong DC/rack; placing replicas based on bad metadata does not solve physical failures.
- Setting RF higher than the number of eligible nodes in a DC is a design that cannot achieve the target replica count as intended.
- When RF or topology changes, you must verify that **actual data** has reached the new replicas; inspecting metadata alone is not enough.

**Design rule:** choose racks/DCs based on truly independent failure domains: servers, racks, network zones, power feeds, or infrastructure regions. Logical DC and rack names must reflect how you want to isolate failures.

## 4. CQL: Defining Per-DC Replication Factors

### 4.1. Creating an NTS Keyspace

In a lab with two properly named DCs and enough eligible nodes:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_geo
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3,
    'dc2': 2
}
AND durable_writes = true;
~~~

Meaning of each component:

| CQL | Meaning |
| --- | --- |
| `'class': 'NetworkTopologyStrategy'` | Uses the topology-aware replication strategy. |
| `'dc1': 3` | Targets three full replicas per partition in the DC named **exactly** `dc1`. |
| `'dc2': 2` | Targets two full replicas per partition in DC `dc2`. |
| `durable_writes = true` | Enables default durable writes via the commit log; **does not** increase RF or CL. |

DC names must match the exact names Cassandra receives from the snitch. `dc1`, `DC1`, and `us-east` are not treated as the same name just because humans know they refer to the same site.

**Do not run this `CREATE KEYSPACE` expecting `dc2` to appear automatically.** If the DC has no nodes yet or is misconfigured, requests requiring acknowledgments from `dc2` may fail. Declaring RF is part of a rollout plan, not a substitute for provisioning and joining nodes.

### 4.2. Creating a Query-Driven Table

Suppose a service retrieves events by **account and day**:

~~~sql
CREATE TABLE IF NOT EXISTS telemetry_geo.events_by_account_day (
    account_id text,
    event_day date,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((account_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

The partition key `(account_id, event_day)` determines the token; the **keyspace's** NTS RF determines the replica set for that **entire partition** in `dc1` and `dc2`. Clustering columns `event_time` and `event_id` enable chronological reads **within the partition**.

~~~sql
SELECT event_time, event_id, payload
FROM telemetry_geo.events_by_account_day
WHERE account_id = 'acct-7'
  AND event_day = '2026-11-21'
LIMIT 50;
~~~

This is a **single-partition** read following query-driven data modeling. NTS changes **where replicas live**; it does not turn a query missing its partition key into a cheap scan.

### 4.3. Inspecting Existing Replication

In `cqlsh`:

~~~sql
DESCRIBE KEYSPACE telemetry_geo;
~~~

`DESCRIBE` is a **cqlsh** helper command. To query metadata via CQL:

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'telemetry_geo';
~~~

The output shows the replication mapping and per-DC RF; it **does not prove** that SSTables for all historical data have been streamed to new nodes.

## 5. Per-DC RF and Consistency Level Thresholds

Crucial point: **replication factor (RF)** and **consistency level (CL)** serve different roles.

- RF specifies **how many target replicas** are placed in each DC.
- CL determines **how many replica responses** the coordinator must receive before returning success for a read/write.
- With `NetworkTopologyStrategy`, CLs prefixed with **`LOCAL_`** calculate their threshold in the **coordinator's/request's local DC**; it does not mean data is only sent to that DC.

### 5.1. Threshold Calculations When `dc1: 3`, `dc2: 2`

The keyspace targets a total of **5 full replicas** per partition.

| CL | If Coordinator Is in `dc1` | If Coordinator Is in `dc2` | Core Condition |
| --- | --- | --- | --- |
| `ONE` | 1 eligible replica (not necessarily in `dc1`) | 1 eligible replica | One response. |
| `LOCAL_ONE` | 1 replica in `dc1` | 1 replica in `dc2` | One response **within the local DC**. |
| `LOCAL_QUORUM` | `floor(3/2)+1 = 2` in `dc1` | `floor(2/2)+1 = 2` in `dc2` | Quorum **within the local DC**. |
| `QUORUM` | 3 of 5 total replicas | 3 of 5 total replicas | Quorum across **all replicas**, without requiring a separate quorum per DC. |
| `EACH_QUORUM` (**write**) | 2 in `dc1` **and** 2 in `dc2` | Same | Quorum in **every replicated DC**. |
| `ALL` | 5 | 5 | All five full replicas respond. |

**Why does `LOCAL_QUORUM` in `dc2` still require 2 ACKs?** With RF = 2, the quorum formula gives `floor(2/2)+1 = 2`; losing one `dc2` replica prevents `LOCAL_QUORUM` requests in that DC from reaching quorum. Not every DC can survive a single-node failure just because you chose `LOCAL_QUORUM`.

**Why is `QUORUM` not the same as `EACH_QUORUM`?** Total RF = 5, so `QUORUM` requires **3** ACKs. For instance, all three ACKs could come from `dc1`, while `dc2` has not acknowledged yet. `EACH_QUORUM` for writes requires **2 ACKs in each DC**, totaling at least four responses in this configuration.

### 5.2. Example Write in DC1 While DC2 Is Slow

~~~mermaid
sequenceDiagram
    participant App as Application in dc1
    participant C as Coordinator dc1
    participant A1 as dc1: A1
    participant A2 as dc1: A2
    participant A3 as dc1: A3
    participant B as dc2 replicas
    App->>C: INSERT, CL=LOCAL_QUORUM
    C->>A1: Mutation
    C->>A2: Mutation
    C->>A3: Mutation
    C->>B: Forward to remote replicas
    A1-->>C: ACK
    A2-->>C: ACK
    C-->>App: Success: 2/3 ACKs in dc1
    Note over B: May not yet have received/applied when client sees success
~~~

Normal writes are coordinated to the full replica set, but **a `LOCAL_QUORUM` success ACK does not wait for a remote quorum**. If `dc1` fails completely right after returning success and before the mutation reaches `dc2`, you cannot guarantee `dc2` already has that record.

### 5.3. Quorum Intersection Only Applies Within the Same Replica Set

Within **a single DC** with RF = 3, `LOCAL_QUORUM` reads and writes both require two replicas. Since `2 + 2 > 3`, the replica set that ACKed the write and the set participating in the read must intersect, **provided** it is the same partition/replica set and assumptions around data state, timestamps, absence of concurrent writes, and failure bounds hold.

However, a `LOCAL_QUORUM` write in `dc1` and a `LOCAL_QUORUM` read in `dc2` operate on **two distinct replica sets**: **there is no guaranteed intersection**. This is one cause of **cross-DC stale reads**, even when both sides use a CL named QUORUM.

CL does not provide serializable multi-partition transactions, does not automatically resolve concurrent write conflicts, and does not mean every replica has been repaired of divergence. Those concerns must be handled through data modeling, application logic, and proper repair procedures.

## 6. When a Node, Rack, or Entire DC Fails

NTS places multiple copies across DCs/racks to improve resilience, but **availability depends on CL**.

### 6.1. Scenarios with RF `dc1: 3`, `dc2: 2`

| Failure | App in `dc1`, CL `LOCAL_QUORUM` | App in `dc2`, CL `LOCAL_QUORUM` | `EACH_QUORUM` Write |
| --- | --- | --- | --- |
| One partition replica in `dc1` unavailable | Succeeds if 2 `dc1` replicas still respond. | Succeeds if 2 `dc2` replicas respond. | Succeeds if 2 in `dc1` and 2 in `dc2` respond. |
| One partition replica in `dc2` unavailable | Succeeds if `dc1` has at least 2 responding replicas. | **Insufficient `dc2` quorum** (only 1/2 left). | **Insufficient** 2 `dc2` ACKs. |
| Entire `dc2` unavailable | Still succeeds if `dc1` has at least 2 responding replicas. | Cannot achieve local quorum in `dc2`. | Cannot achieve `dc2` quorum. |
| Entire `dc1` unavailable | Cannot serve local quorum in `dc1`. | Succeeds if 2 `dc2` replicas respond. | Cannot achieve `dc1` quorum. |

This is an ACK-threshold model, not a guarantee that remote data has received every write recently acknowledged in the local DC. Rack fault tolerance also depends on whether replicas are genuinely placed on independent racks and on total node/rack counts.

### 6.2. Availability Differs from Durability and RPO

- **Availability:** are enough replicas currently alive to satisfy the request's CL?
- **Durability:** do acknowledged mutations remain on surviving storage/replicas after a failure?
- **RPO (Recovery Point Objective):** when failing over to a backup DC, how much of the most recent data can the business afford to lose?
- **RTO (Recovery Time Objective):** how long does it take to shift load, verify consistency, and restore serviceability?

A system that picks `LOCAL_QUORUM` for low latency and availability during remote DC disconnects must **accept that a local ACK does not equal a durable write confirmation in the standby DC**. If business requirements demand proof of acknowledgment in both DCs, a write CL like `EACH_QUORUM` may fit better, at the cost of tying availability to the inter-DC link and replicas on both sides.

**RF does not replace backups.** Accidental deletes or bad mutations can be replicated to every DC; you still need snapshots/backups, restore capability, and a disaster recovery runbook.

## 7. Choosing Per-DC RF: Not "The More, the Better"

### 7.1. Three Design Examples

| Design | When Considered | Benefits | Trade-offs |
| --- | --- | --- | --- |
| `dc1: 3`, `dc2: 3` | Both DCs actively serve traffic and each needs quorum to tolerate one failed replica | `LOCAL_QUORUM = 2` in both DCs; convenient for shifting traffic | Six total copies; higher storage, write, and repair costs. |
| `dc1: 3`, `dc2: 2` | Primary DC is larger; secondary DC has different capacity and accepts requiring both replicas for local quorum | Saves one replica in the secondary DC | `LOCAL_QUORUM = 2` in `dc2` cannot tolerate losing a single replica of the partition. |
| `dc1: 3`, `dc2: 1` | Only one copy in secondary DC for limited use; not considered a full HA architecture | Fewer copies and lower cost | Losing a `dc2` node can leave data with zero replicas in `dc2`; local quorum in `dc2` needs 1 but has no intra-DC redundancy. |

Do not choose RF solely by server count:

1. **Target full replicas per DC** must match fault-tolerance goals.
2. **Rack/fault domain count** must reflect expected correlated failures; RF = 3 on three nodes in one rack differs from RF = 3 spread across multiple racks.
3. **Capacity:** each replica adds data volume, write I/O, repair, and streaming load.
4. **Application CL:** RF = 2 paired with `LOCAL_QUORUM` has different availability than RF = 3.
5. **Data residency requirements:** do not replicate into disallowed DCs; storage, network links, backups, and access paths also require separate controls.

### 7.2. Rule of Thumb for Footprint and Cost

If total logical data is **D bytes**, ideal replicas generate roughly **D × total RF** in storage footprint across all DCs before accounting for SSTable overhead, compaction, snapshots, tombstones, and skew. This is a planning estimate only, **not an exact disk byte count**.

Increasing RF does not automatically make a `SELECT` faster. Reading a partition still requires a good partition key design, bounded clustering ranges, controlled partition sizes, and an appropriate consistency level. Having more replicas can aid load distribution or fault tolerance, but also adds maintenance overhead.

## 8. Hands-On CQL: Two Write Modes and Different ACKs

In a lab with enough replicas in both DCs:

~~~sql
CONSISTENCY LOCAL_QUORUM;
TRACING ON;

INSERT INTO telemetry_geo.events_by_account_day
  (account_id, event_day, event_time, event_id, payload)
VALUES
  ('acct-7', '2026-11-21', '2026-11-21T03:00:00Z',
   123e4567-e89b-42d3-a456-426614174001, 'registered');

TRACING OFF;
~~~

In `cqlsh` connected to a coordinator in `dc1`, `LOCAL_QUORUM` requires two ACKs in `dc1`. If the coordinator is in `dc2`, the same keyword requires two ACKs in `dc2` because `dc2` has RF = 2.

To demonstrate a write waiting for quorum **in each DC**:

~~~sql
CONSISTENCY EACH_QUORUM;
TRACING ON;

INSERT INTO telemetry_geo.events_by_account_day
  (account_id, event_day, event_time, event_id, payload)
VALUES
  ('acct-7', '2026-11-21', '2026-11-21T03:01:00Z',
   123e4567-e89b-42d3-a456-426614174002, 'verified');

TRACING OFF;
~~~

Here, `EACH_QUORUM` is a **write CL**, requiring two ACKs from `dc1` **and** two ACKs from `dc2`. If one `dc2` replica is unavailable, the write can fail at this CL, even though the same write at `LOCAL_QUORUM` in `dc1` would have succeeded.

Switch CL back to an appropriate read mode:

~~~sql
CONSISTENCY LOCAL_QUORUM;

SELECT event_time, event_id, payload
FROM telemetry_geo.events_by_account_day
WHERE account_id = 'acct-7'
  AND event_day = '2026-11-21';
~~~

`CONSISTENCY` and `TRACING` are **cqlsh commands**, not literal CQL sent via the Java Driver. Traces help inspect coordinators, endpoints, and communication behavior; **a successful trace does not certify that all replicas across DCs have converged**.

## 9. Java Driver 4.x: Local DC and Statement-Level CL

In Apache Cassandra Java Driver 4.x, applications typically declare a **local datacenter** so the driver prefers local nodes and manages connection pools. It **does not** mean the keyspace's replication strategy or RF is changed inside the application.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetSocketAddress;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class MultiDatacenterEvents {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement insert = session.prepare(
                "INSERT INTO telemetry_geo.events_by_account_day " +
                "(account_id, event_day, event_time, event_id, payload) " +
                "VALUES (?, ?, ?, ?, ?)");

            BoundStatement write = insert.bind(
                    "acct-7",
                    LocalDate.of(2026, 11, 21),
                    Instant.parse("2026-11-21T03:02:00Z"),
                    UUID.fromString("123e4567-e89b-42d3-a456-426614174003"),
                    "confirmed")
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
            session.execute(write);

            PreparedStatement select = session.prepare(
                "SELECT event_time, event_id, payload " +
                "FROM telemetry_geo.events_by_account_day " +
                "WHERE account_id = ? AND event_day = ?");

            BoundStatement read = select.bind(
                    "acct-7", LocalDate.of(2026, 11, 21))
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            for (Row row : session.execute(read)) {
                System.out.println(row.getInstant("event_time")
                    + " -> " + row.getString("payload"));
            }
        }
    }
}
~~~

**Explanation of each decision:**

1. `withLocalDatacenter("dc1")` specifies the driver's local DC. The name must match the cluster DC; `127.0.0.1` is for lab illustration only, not a production contact point.
2. The prepared statement includes the full composite partition key `(account_id, event_day)`, letting the driver compute the routing key to prefer appropriate replicas when token-aware routing is enabled.
3. `LOCAL_QUORUM` for reads/writes requires **2/3 ACKs in `dc1`** given RF `dc1: 3`. It does not wait for quorum in `dc2`.
4. When the real application is deployed in `dc2`, it should use the corresponding connection/local DC configuration; `LOCAL_QUORUM` there requires **2/2** `dc2` replicas.
5. **The driver does not automatically turn remote-DC requests into safe failover** just because the cluster replicates there. Switching DCs requires explicit routing, connectivity, CL, latency/staleness monitoring, and application procedures.
6. On a write timeout, some replicas may already have applied the mutation; retries must consider idempotency, stable event keys, and timestamp conflicts.

To ensure a **write** is ACKed in both DCs (at the corresponding latency/availability cost), you may consider `DefaultConsistencyLevel.EACH_QUORUM` on write statements when supported by your version/cluster. **Do not use `EACH_QUORUM` as a regular read CL.**

### 9.1. Active-Active: The Same Key Written from Two DCs

Cassandra does not provide automatic serializable transactions for arbitrary multi-DC `UPDATE` operations. Mutation versions are reconciled by write timestamp and tombstones; **writing from two DCs to the same cell** can cause conflicts or outcomes that violate user-expected ordering, especially under clock skew or client-supplied timestamps.

For critical workloads:

- Choose **event/idempotency keys** so retries do not accidentally duplicate or overwrite data.
- Avoid unsynchronized **read-modify-write** patterns when multiple writers update the same value concurrently.
- Define **write ownership rules**, ordering, logical partition ownership, or conditional primitives appropriate for your requirements.
- For data needing strong/conditional consistency, evaluate LWT mechanisms along with their limits and overhead rather than merely raising standard CL.

## 10. Adding a New DC or Changing RF: Metadata Updates Are Not the End

Suppose you currently have `dc1: 3` and want to add `dc2: 2`. There are two layers of work:

1. **Physical topology:** provision nodes in `dc2`, configure snitch/racks accurately, set up networking and security, and ensure nodes join the cluster cleanly.
2. **Data replication:** update keyspace RF, stream/synchronize data to the new replicas, and verify that data and tombstones are preserved.

A CQL statement modifying replication metadata:

~~~sql
ALTER KEYSPACE telemetry_geo
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3,
    'dc2': 3
};
~~~

For example, raising `dc2` RF from 2 to 3 **only updates the target replica placement**. It does not guarantee that the third full replica in `dc2` has received all historical partitions/tombstones. You must follow an approved procedure for your Cassandra version: verify sufficient nodes, run properly scoped streaming/rebuild/repair, validate results, and adjust maintenance schedules.

**A safe conceptual rollout sequence:**

1. **Pre-change assessment:** capacity, WAN bandwidth, current RF, racks/DCs, client CL, backup/restore readiness, and failure budgets.
2. **Prepare DC/nodes:** snitch reports accurate DC/racks; cluster connectivity, auth/TLS, and firewall rules are in place.
3. **Plan the RF change:** choose timing, order of DC creation, and keyspace updates per version docs; anticipate availability impact while target RF lacks full replicas.
4. **Populate new replicas:** monitor streaming/rebuild/repair for the right keyspace and DC; never assume `ALTER KEYSPACE` means data is complete.
5. **Verify:** topology is stable, token ownership looks right, sample reads succeed in each DC, and repair/missing data/tombstones pass checks per runbook.
6. **Adjust applications:** local DC, CL, routing/failover, timeouts, and cross-DC monitoring; roll out gradually with controlled traffic.
7. **Clean up old data if needed:** once new replicas are safe and ownership shifts are complete, evaluate running cleanup on nodes no longer responsible for ranges. Never delete data manually before streaming finishes.

### Warning When Decreasing RF or Removing a DC

Lowering RF can remove redundant copies. Removing a DC from metadata before ensuring data resides safely on surviving nodes—or running cleanup too early—can cause data loss or reduced fault tolerance. This must be a planned change covering **data migration, tombstone protection, replica verification, and recovery**, not a one-line CQL edit.

## 11. Repair, Hinted Handoff, and Protecting Deletes Across DCs

**NTS decides where copies should exist; it does not keep all copies identical automatically.**

| Mechanism | Purpose | Multi-DC Limitations |
| --- | --- | --- |
| **CL writes** | Determines how many replicas ACK before client sees success | `LOCAL_QUORUM` does not wait for remote quorum. |
| **Hinted handoff** | Temporarily records missed mutations for replay to replicas | Bounded by time/config; does not replace repair after prolonged DC outages. |
| **Read repair** | Reconciles/repairs divergent data on read paths, depending on version | Local reads do not force repair on every partition in remote DCs. |
| **Anti-entropy repair** | Reconciles token ranges across participating replicas | Requires a schedule covering the **right DCs/replicas** and completion tracking. |
| **Compaction** | Merges SSTables and purges eligible data on each node | Does not propagate mutations to other DCs. |
| **Backup/snapshot** | Provides history to restore after accidental deletes or mass corruption | Does not mean remote replicas received the latest writes. |

### 11.1. Tombstones and `gc_grace_seconds`

Suppose `dc2` is disconnected for days. A `DELETE` succeeding at `LOCAL_QUORUM` in `dc1` might **not reach** replicas in `dc2`. If tombstones on the receiving replicas are purged before the disconnected DC is safely synchronized, old data risks reappearing (*zombie data*).

`gc_grace_seconds` governs tombstone retention; **it does not trigger repair by itself**. Operations must ensure post-outage DC repair/recovery, handle nodes offline past grace limits, and avoid arbitrarily lowering grace periods just to reclaim disk space.

### 11.2. Local Repair and Cross-DC Repair Are Not the Same

Running repair **only within `dc1`** can converge `dc1` replicas, but **does not prove `dc2` received every update/delete**. When scheduling repairs, verify the `-local`, `-dc`, and `-hosts` scoping options and the repair strategy for **your exact Cassandra version**; explicitly account for which DCs/replicas participate, data-transfer overhead, and tombstone protection.

Cross-DC repair can consume significant bandwidth, CPU, and I/O; monitor actual completion outcomes rather than merely checking that `nodetool repair` started.

## 12. Observing and Diagnosing Live Topology

### 12.1. Common `nodetool` Commands

On a Cassandra node with operator access in lab/staging:

~~~bash
nodetool status
nodetool ring
nodetool netstats
nodetool compactionstats
~~~

- `status`: view whether nodes are `UN`/down/joining, DC/rack names, and topology info.
- `ring`: inspect token ownership, especially with vnodes.
- `netstats`: track streaming/reception during topology changes or data movement.
- `compactionstats`: spot background work competing for I/O with repair/streaming.

With composite partition keys, determining exact natural endpoints requires tools/topology metadata aligned with the exact schema and partitioner. `nodetool ring` shows token ranges, but **is not proof that all SSTables are synchronized** after an RF increase.

### 12.2. Diagnostic Checklist When DC2 Reads Differ from DC1

1. **Check the keyspace:** does `system_schema.keyspaces` declare RF with the exact DC names?
2. **Check the snitch:** which nodes are assigned to `dc1`/`dc2` and which racks—any naming or config mistakes?
3. **Check CL and coordinator:** are requests actually using `LOCAL_ONE`, `LOCAL_QUORUM`, or `QUORUM`? Which local DC is the driver selecting?
4. **Check replica health:** any downed nodes, network partitions, pending streams, write timeouts, or failed hints/repairs?
5. **Check timestamps and concurrent writes:** both DCs may be writing differently to the same key; it is not always replication lag.
6. **Check repair scope:** have token ranges and participating DCs in repair been verified complete?
7. **Check deletes/TTLs:** were tombstones synchronized before purging, or was a replica offline past grace limits?

**Do not try to fix every mismatch by raising RF, raising CL, or forcing compaction.** Each tool addresses a different layer; first identify which part of writing, replication, or repair failed.

## 13. Common Reasoning Mistakes

| Claim | Verdict | Explanation |
| --- | --- | --- |
| "`dc1: 3, dc2: 2` means Cassandra picks any five random nodes." | **False** | RF is enforced **per DC** based on tokens/racks/topology. |
| "If a cluster has 10 nodes in `dc1`, each partition has 10 replicas." | **False** | `dc1` RF sets the target replica count, not the DC node count. |
| "`LOCAL_` means the commit log was fsynced locally." | **False** | `LOCAL_` scopes the CL to a DC, not local durability mechanisms. |
| "`LOCAL_QUORUM` always survives one node failure." | **False** | With `dc2` RF = 2, both replicas are needed for local quorum. |
| "`QUORUM` = `EACH_QUORUM`." | **False** | Global quorum can be satisfied by one DC; `EACH_QUORUM` writes require quorum in every DC. |
| "A successful write at `dc1`/`LOCAL_QUORUM` means `dc2` already has it." | **False** | It does not wait for remote ACKs. |
| "NTS automatically repairs all divergent replicas after a network outage." | **False** | Proper convergence and repair/recovery processes are required. |
| "Running `ALTER KEYSPACE` to a higher RF is enough to create new copies." | **False** | Historical data must be transferred and verified on new replicas. |
| "Increasing RF makes full-table CQL scans cheaper." | **False** | RF does not change partition key design or query cost. |
| "Having multiple replicas across two DCs eliminates the need for backups." | **False** | Accidental deletes/corruption propagate; backups serve a different purpose. |

## 14. Self-Check Exercises with Answers

**Exercise 1.** A keyspace uses `NetworkTopologyStrategy` with `dc1: 3` and `dc2: 2`. How many full replicas per partition are targeted cluster-wide, assuming enough nodes?

**Answer:** **Five full replicas**—three in `dc1` and two in `dc2`. Coordinator-only nodes do not count as additional replicas.

**Exercise 2.** With RF `dc1: 3`, `dc2: 2`, how many ACKs does an `EACH_QUORUM` write require?

**Answer:** **Two in `dc1` and two in `dc2`**, totaling at least four ACKs—not any three ACKs.

**Exercise 3.** One replica node for a partition in `dc2` goes down, leaving one `dc2` replica. An application in `dc2` uses `LOCAL_QUORUM`. Can the write succeed?

**Answer:** **It cannot achieve `dc2` `LOCAL_QUORUM`** because `dc2` RF = 2 requires both replicas for quorum. Depending on business needs, lowering CL can restore availability at the cost of weaker consistency guarantees, though it does not fix the downed node.

**Exercise 4.** A `LOCAL_QUORUM` write in `dc1` succeeds, and immediately afterward a `LOCAL_QUORUM` read in `dc2` does not see the value. Does this contradict `R + W > RF`?

**Answer:** **No.** The two local quorums are evaluated over **two different replica sets in two different DCs**; there is no forced intersection. Consider mutation propagation delay, DC health, repair, and concurrent writes.

**Exercise 5.** You change `dc2` RF from 2 to 3 and immediately let applications read at `LOCAL_QUORUM`. Can you assume the third replica holds full historical data?

**Answer:** **No.** New RF metadata does not automatically stream historical data. Follow a properly scoped transfer/rebuild/repair and verification process before trusting the new topology.

**Exercise 6.** Why is RF = 3 in a DC with three nodes but only one rack still not a strong rack-fault-tolerant architecture?

**Answer:** Because all three nodes share a single failure domain. If the shared rack/network/power fails, multiple replicas can be lost at once. Configure racks and snitch to reflect real failure domains.

**Exercise 7.** When a remote DC has been offline longer than the hint retention window, can you simply bring the DC back up and rely on hints to catch up completely?

**Answer:** **No.** Hints are bounded. You must evaluate repair/rebuild per runbook—especially tombstones and `gc_grace_seconds`—before considering data converged.

**Exercise 8.** Two applications in two DCs concurrently update `account_id='acct-7'` using unreliable timestamps. Does switching the write CL to `EACH_QUORUM` prevent lost updates?

**Answer:** **No.** CL controls ACK thresholds; it does not turn read-modify-write into an isolated transaction. You must address data modeling, clocks/timestamps, idempotency, and appropriate conditional mechanisms.

## 15. NTS Configuration Decision Flow

~~~mermaid
flowchart TD
    A["Application needs multi-DC Cassandra"] --> B["Identify failure domains, racks/DCs, and RPO/RTO"]
    B --> C["Choose per-DC RF based on fault tolerance and capacity"]
    C --> D["Verify snitch, token map, and node/rack counts"]
    D --> E{"New DC or RF change?"}
    E -->|Yes| F["Plan streaming/rebuild/repair and verification"]
    E -->|No| G["Maintain topology, monitor replicas"]
    F --> H["Select CL for workload and failover"]
    G --> H
    H --> I{"Only local ACK or remote ACK too?"}
    I -->|Local| J["LOCAL_QUORUM/LOCAL_ONE per target"]
    I -->|Every DC| K["Consider EACH_QUORUM for writes"]
    J --> L["Monitor latency, remote data, repair, and backups"]
    K --> L
~~~

**Core takeaway:** `NetworkTopologyStrategy` defines **how many replicas of a partition are placed in each DC**; `LOCAL_QUORUM`, `QUORUM`, and `EACH_QUORUM` decide **which replicas must acknowledge before the client sees success**. Configuring RF does not stream historical data, a local ACK does not replace a cross-DC ACK, and replication does not replace repair or backups. A sound multi-DC system requires designing **partition keys, topology/racks, per-DC RF, CL, synchronization mechanisms, tombstone protection, and failover/restore plans** together.
