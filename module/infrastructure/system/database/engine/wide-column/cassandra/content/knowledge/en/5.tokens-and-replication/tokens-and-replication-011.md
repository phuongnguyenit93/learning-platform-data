# Impact of Changing RF on Existing Data in Apache Cassandra

> **Chapter:** Tokens and Replication  
> **Focus:** When changing a keyspace's replication factor (RF), how copies of existing data are retained, populated, or cleaned up; how to transition safely and verify results.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why changing RF alters the **designated replica set** without automatically moving all previously written data.
2. Distinguish the workflows **raising RF: full repair** and **lowering RF: cleanup**, along with their effects on availability, data durability, and disk capacity.
3. Identify the risk of missing data on reads during the transition window, especially under consistency levels `ONE` or `LOCAL_ONE`.
4. Inspect keyspace configuration, identify a partition's replicas, and plan operations per node/DC.
5. Explain the impact on Java applications using the Cassandra driver and choose appropriate consistency levels.

The example scope covers **Apache Cassandra using full replicas** with `NetworkTopologyStrategy`. Transient replication, snitch migrations, token changes, or simultaneous topology changes require separate procedures.

## 2. What Does RF Govern?

Cassandra divides the keyspace using **tokens**. The partition key is hashed into a token; the keyspace's replication strategy picks which nodes store copies of each token range. The selected nodes are called **natural replicas**.

- **Replication factor (RF)** is the target number of copies per token range; with `NetworkTopologyStrategy`, it is configured independently per datacenter (DC).
- **Replication strategy** determines which nodes/racks replicas are selected from.
- **Consistency level (CL)** determines how many responses are required per read/write operation; CL never creates missing data on a replica by itself.
- **Repair** compares data across replicas and streams differences; **cleanup** deletes data for token ranges a node is no longer responsible for storing.

Example keyspace configuration:

~~~sql
CREATE KEYSPACE learning_events
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': '2',
  'dc2': '2'
}
AND durable_writes = true;
~~~

Here RF is **2 in `dc1` and 2 in `dc2`** per token range, not RF = 2 cluster-wide. With proper topology, each partition has 4 full replicas total across the two DCs. RF is a **keyspace-level** property, so altering RF affects every table in that keyspace.

> In production systems, use `NetworkTopologyStrategy` with exact DC names reported by the cluster. `SimpleStrategy` ignores datacenter placement and is unsuitable for most real deployments.

### Metadata and Physical Copies Are Two Separate States

`ALTER KEYSPACE` updates the **replica placement rules**. Once schema agreement is reached across nodes, coordinators use the new rules to route reads and writes. However, previously written SSTables are not automatically copied or deleted solely by running `ALTER`.

Distinguish clearly:

| Component | After raising RF | After lowering RF |
|---|---|---|
| Keyspace metadata | Assigns more replicas to token ranges | Assigns fewer replicas |
| New writes, after schema agreement | Directed to the new replica set | Directed to the new replica set |
| Existing data | May be **absent** on newly added replicas | May **still remain** on nodes no longer designated as replicas |
| Required operational task | **Full repair** to stream old data to required replicas | **Cleanup** to reclaim excess data |
| Primary risk | Missing historical data on reads; insufficient real copies; network/disk load during repair | Reduced redundancy if RF is set too low; stale data consuming disk before cleanup |

The transition has an **unconverged window** between metadata and physical data. A successful `ALTER` does not prove historical copy distribution is finished.

## 3. Raising RF: Old Data Does Not Appear Automatically on New Replicas

Suppose one DC has four nodes N1, N2, N3, N4 and a partition P. Simplified illustration: before changing RF, natural replicas of P are N1 and N2.

~~~text
Before: RF = 2
P ──> N1 [has P]
  └─> N2 [has P]
      N3 [not assigned]
      N4

After ALTER: RF = 3, before full repair
P ──> N1 [has P]
  ├─> N2 [has P]
  └─> N3 [assigned, may not have P yet]
      N4

After successful full repair
P ──> N1 [has P]
  ├─> N2 [has P]
  └─> N3 [received P]
~~~

This is an illustration for a single partition; actual replicas depend on the token ring, replication strategy, and rack layout. You cannot assume N3 is always the new replica for every partition.

### What Happens to Reads and Writes?

**Writes after changing RF.** Once nodes receive the updated schema, coordinators pick replicas per the new RF. A new write goes to N1, N2, and N3. This **does not backfill older records** onto N3. If a node misses a write due to a transient error, hinted handoff only covers missed writes during the outage window; it is not a historical data-copy mechanism when raising RF.

**Reads before repair completes.** Coordinators may also query N3 under the new metadata. If N3 does not yet hold partition P, reads at `ONE`/`LOCAL_ONE` can return empty results even though P exists on N1 and N2. That is a serious risk when changing RF on a live keyspace.

**Reading at `QUORUM`/`LOCAL_QUORUM` is not a universal cure.** In the RF 2 → 3 example, `LOCAL_QUORUM` in `dc1` needs two responses; among the three new replicas, any two must intersect at least one of the two old replicas—if placement matches the diagram. However, when jumping **RF 1 → 3**, two brand-new empty replicas could form two responses; `LOCAL_QUORUM` fails to guarantee reading historical data. `ALL` queries every replica and can read from an old copy if still up, at a steep availability cost. Therefore, **analyze old vs. new replica sets, CL, and node health**, and prioritize finishing full repair promptly.

Required responses for quorum in a single DC using full replicas:

| RF in DC | `LOCAL_ONE` | `LOCAL_QUORUM` |
|---:|---:|---:|
| 1 | 1 | 1 |
| 2 | 1 | 2 |
| 3 | 1 | 2 |
| 4 | 1 | 3 |

Response counts are **operation consistency conditions**, not proof that all replicas actually hold the data. In multi-DC clusters, `QUORUM` over total RF differs from `LOCAL_QUORUM` over the local DC's RF; **`ALL`** requires all replicas across DCs—there is no consistency level named `LOCAL_ALL`.

### Why Is Full Repair Mandatory?

~~~bash
nodetool repair --full learning_events
~~~

Repair compares replicas across relevant token ranges (using Merkle trees) and streams missing data. **Full repair** inspects all data in the range; default **incremental repair** can skip data previously marked repaired. Thus running a default repair—or relying on hinted handoff/read repair—is insufficient when raising RF.

In a **cluster-wide** workflow, a common pattern is running across **each node in each DC** on a coordinated schedule to avoid overlapping load:

~~~bash
# Run sequentially per node/DC;
# -pr restricts repair to this node's primary token ranges.
nodetool repair --full -pr learning_events
~~~

Each `nodetool` invocation repairs only the ranges covered by that node/command; running once on one node is **not** a full cluster-wide repair. Declare completion only after all required ranges have been repaired successfully across all relevant nodes/DCs. In large environments, use a monitored repair schedule controlling concurrency and free disk space.

### Costs of Raising RF

- **Storage:** total target copies scale roughly with RF for data in that DC. For instance, RF 2 → 3 implies roughly 50% more replica storage in that DC alone, before overhead, compression, tombstones, indexes, and distribution skew.
- **Network:** full repair can stream substantial traffic across replicas, especially when raising RF in another DC.
- **CPU and disk:** building Merkle trees, reading SSTables, streaming data, and compactions can impact query latency.
- **Transition risk:** until repair completes, **configured replicas** outnumber **replicas holding historical data**.

Never set RF higher than the number of eligible nodes in a DC. Rack count, node placement, and node health also shape real fault tolerance; counting nodes alone does not guarantee fault isolation.

## 4. Lowering RF: Excess Copies Still Occupy Disk

Suppose partition P currently has three replicas N1, N2, N3, and RF in `dc1` is lowered from 3 to 2:

~~~text
Before: RF = 3
P ──> N1 [has P]
  ├─> N2 [has P]
  └─> N3 [has P]

After ALTER: RF = 2, before cleanup
P ──> N1 [assigned replica]
  └─> N2 [assigned replica]
      N3 [may still hold old copy, no longer a replica]

After cleanup on relevant nodes
P ──> N1 [assigned replica]
  └─> N2 [assigned replica]
      N3 [out-of-scope data cleaned up]
~~~

Lowering RF takes effect for **the target replica set** after schema agreement. Cassandra does not automatically delete excess SSTables upon `ALTER`. No-longer-routed copies can keep consuming disk space.

To remove data a node no longer owns:

~~~bash
# Run on a schedule on each node holding data for the keyspace.
nodetool cleanup learning_events
~~~

Cleanup is a **per-node** operation. It removes data for token ranges the node no longer needs to store under current topology/replication. Never mistake cleanup for full repair: cleanup **never builds missing replicas**.

When solely lowering RF without changing topology or strategy, there is no need to populate extra copies as when raising RF. Still, verify that **remaining** replicas hold consistent, healthy data before reducing redundancy. If simultaneously migrating DCs, changing snitches, bootstrapping/decommissioning nodes, or changing strategies, build a dedicated migration plan rather than extrapolating from this simplified example.

### What Changes in Durability and Consistency?

- RF 3 tolerates one replica outage better than RF 2; lowering RF **shrinks your fault-tolerance budget**, even while stale copies linger on disk.
- With RF 3, `LOCAL_QUORUM` needs 2 responses; with RF 2, `LOCAL_QUORUM` still needs 2 responses, meaning losing a single replica makes `LOCAL_QUORUM` unachievable in that DC.
- Copies sitting outside the natural replica set **do not count** as valid redundancy for new requests. Never rely on them for recovery or live serving.
- Disk usage does not necessarily drop immediately or linearly after cleanup due to snapshots, compactions, tombstones, and other keyspaces' data.

Before lowering RF, review SLAs, backups, application CLs, repair health, and recent node errors. Never lower RF merely to relieve low disk space while the cluster is missing replicas or out of sync.

## 5. Complete CQL Example with Two Datacenters

Assume the cluster uses exact DC names `dc1` and `dc2`. Initial keyspace:

~~~sql
DESCRIBE KEYSPACE learning_events;

-- Expected config before change:
-- {'class':'NetworkTopologyStrategy','dc1':'2','dc2':'2'}
~~~

### Scenario A: Raise RF in `dc1` from 2 to 3

~~~sql
ALTER KEYSPACE learning_events
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': '3',
  'dc2': '2'
};

DESCRIBE KEYSPACE learning_events;
~~~

Key points to understand:

1. `dc1` begins designating an extra replica per token ring; **existing data in `dc1` has not yet been copied completely**.
2. `dc2` stays at RF = 2 because we **preserved** `dc2`'s setting in the `ALTER` statement.
3. After schema agreement, schedule a full repair covering all affected ranges and verify results; never treat `DESCRIBE` showing RF = 3 as proof of completion.

### Scenario B: After Convergence, Lower RF in `dc1` from 3 Back to 2

~~~sql
ALTER KEYSPACE learning_events
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': '2',
  'dc2': '2'
};

DESCRIBE KEYSPACE learning_events;
~~~

Afterward, remove excess copies using `cleanup` on relevant nodes per operational procedure. Never accidentally omit `dc2` from the map; in `NetworkTopologyStrategy`, option semantics and defaults vary by version, so **explicitly declare all DCs you intend to keep** and inspect the config after `ALTER`.

> **Note:** In modern Cassandra, certain RF declarations can use automatic per-DC expansion syntax. When modifying production keyspaces, explicitly specifying each DC's RF makes peer review clearer. Do not copy `dc1`/`dc2` verbatim if your cluster uses different names.

## 6. Runbook for Changing RF on a Live Cluster

### Step 1: Verify Pre-Change State

Check these items:

| Item | Operational question |
|---|---|
| Goal | Improve fault tolerance, add a DC, or reduce storage cost? |
| Topology | Does each DC have enough nodes/racks for the target RF? |
| Health | Are all relevant nodes Up/Normal? Are any nodes bootstrapping or leaving? |
| Data | Have recent repairs failed? Are there tombstone backlogs or restorable backups/snapshots? |
| Capacity | Is there enough disk/network headroom for added copies and repair/cleanup? |
| Application | Does the Java driver use `LOCAL_ONE`, `LOCAL_QUORUM`, `QUORUM`, or another level? |
| Rollback | If raising RF needs rollback, is cleanup planned; if lowering RF needs rollback, is full repair planned? |

Reference commands, run in an authorized operational environment:

~~~bash
nodetool status
nodetool describecluster
~~~

In `cqlsh`:

~~~sql
DESCRIBE KEYSPACE learning_events;
CONSISTENCY;
~~~

Check the **application's** consistency from driver config, because `cqlsh`'s displayed level only applies to that `cqlsh` session. For a specific partition key, inspect **designated endpoints**:

~~~bash
# Example table with text partition key tenant_id
nodetool getendpoints learning_events events tenant_a
~~~

`getendpoints` shows **intended placement**, not proof that data already sits on those endpoints' disks.

### Step 2: Update Metadata in a Controlled Way

Record the old configuration, run `ALTER KEYSPACE`, confirm schema agreement across nodes, and re-run `DESCRIBE` to verify each DC's RF matches the target. While metadata propagates, watch for schema errors or queries routed through not-yet-converged nodes.

### Step 3A: If Raising RF, Immediately Execute Full Repair

Run full repair for the keyspace, **covering all necessary ranges/DCs**. You can run `--full` with `-pr` on **each node**, sequentially and coordinated. Monitor completion logs, streaming errors, disk usage, network throughput, read/write latency, and compaction load. Never launch multiple heavy jobs concurrently without evaluating load capacity.

~~~bash
# Sample per-node command on a coordinated schedule:
nodetool repair --full -pr learning_events

# Inspect active streaming at check time:
nodetool netstats
~~~

Depending on version, flags and repair orchestrators vary; read `help` for your exact running version before applying to production. One job reporting success does not mean other nodes finished.

### Step 3B: If Lowering RF, Run Cleanup on Excess Copies

Once surviving replicas are confirmed healthy and data is synchronized, run cleanup on relevant nodes, scheduled to avoid disk I/O contention:

~~~bash
nodetool cleanup learning_events
~~~

Monitor disk, compactions, and free space. If snapshots pin SSTables, filesystem usage may not drop as expected even after cleanup succeeds.

### Step 4: Post-Change Verification

Do not stop at a single `SELECT` returning a row. At minimum:

1. `DESCRIBE` shows accurate per-DC RF; schema agreement is confirmed.
2. Expected nodes/racks remain Up/Normal; no new replicas are missing or failing repeatedly.
3. Repair or cleanup completed successfully **across the entire intended scope**.
4. Read sample keys that existed prior to the RF change across different partitions/token ranges; compare against source records or app inventories.
5. Monitor read/write errors, timeouts/unavailables, latency, disk, streaming, and repair metrics post-change.
6. Confirm backups and periodic repair schedules still align with RF, workload, and `gc_grace_seconds`.

Record results by **node, DC, timestamp, Cassandra version, command, and status**, so on-call engineers know the exact scope completed.

## 7. Impact on Consistency Levels and Java Applications

With full replicas, required responses for a consistency level depend on RF. Within a DC, `LOCAL_QUORUM` requires `⌊RF_DC / 2⌋ + 1` replicas; `LOCAL_ONE` requires one. Raising RF from 2 to 3 still requires 2 responses for `LOCAL_QUORUM`, whereas lowering from 3 to 2 removes the ability to maintain `LOCAL_QUORUM` if one of the two replicas goes down.

When analyzing read/write overlap, the classic formula is **R + W > RF** for intersection between read and write acknowledgment sets, *assuming converged data/replicas and valid underlying assumptions*. That formula does not fix unstreamed historical data after raising RF, does not guarantee linearizability across all Cassandra operations, and does not replace repair.

Example with Java Driver 4.x setting per-statement consistency:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

public final class EventReader {
    // Session pre-built by the application with the matching local datacenter.
    public static String findPayload(
            CqlSession session, String tenantId, int eventId) {
        SimpleStatement query = SimpleStatement.builder(
                "SELECT payload FROM rf_lab.events " +
                "WHERE tenant_id = ? AND event_id = ?")
            .addPositionalValues(tenantId, eventId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .build();

        Row row = session.execute(query).one();
        return row == null ? null : row.getString("payload");
    }
}
~~~

**Note on the Java sample:** the method accepts a valid `CqlSession` created and reused across the application lifecycle rather than opening/closing sessions per query. It targets the `rf_lab.events` lab table; DC name and CL must be chosen to match real topology.

The Java driver's CL **does not automatically adjust when RF changes**. After raising or lowering RF, audit default CLs, per-statement overrides, timeouts, retry policies, fault tolerance, and driver local DC selection. During transition, avoid running a check at `LOCAL_ONE` and declaring data lost before full repair finishes; conversely, do not treat reading a few keys successfully as proof that every token range is synchronized.

## 8. Common Misconceptions That Cause Incidents

| Misconception | Fact to remember |
|---|---|
| "`ALTER KEYSPACE` succeeded, so all old data now has the new RF." | `ALTER` changes replica placement rules; **raising RF requires full repair** for existing data. |
| "Default incremental repair is enough after raising RF." | Full repair is needed because data already marked repaired may be skipped by incremental repair. |
| "Hinted handoff or read repair will automatically balance every partition." | Those mechanisms do not guarantee streaming all historical data to new replicas. |
| "`SELECT` returning a few records proves all token ranges are fine." | Verify repair completion across scope and check multiple partitions. |
| "Lowering RF frees disk immediately." | Excess copies remain on disk until cleanup; snapshots can also hold disk space. |
| "Cleanup and compaction will fix missing replicas after raising RF." | Cleanup deletes unowned data; compaction organizes local files; **repair** syncs replicas. |
| "RF = 3 across two DCs means three copies total." | With `NetworkTopologyStrategy`, RF is set per DC; e.g., `dc1=3, dc2=2` targets 5 copies. |
| "Reading at `QUORUM` during transition is always safe." | Analyze old RF, new RF, and replica set overlap; RF 1 → 3 is a counterexample. |

### Tombstones and the Risk of Deleted Data Resurrecting

Cassandra uses tombstones to represent deletions. If a replica misses a tombstone, old data on that node can become an issue once tombstones on other replicas are purged after the grace period and compaction. Changing RF mid-unconverged state makes monitoring replica sync even more critical. Keep repair schedules aligned with `gc_grace_seconds`, and never shrink the grace period arbitrarily just to reclaim disk faster.

## 9. Controlled Practice Exercise

**Prerequisites:** a lab cluster with at least three active nodes in `dc1` and sufficient resources; substitute your DC name if different. Never run experiments on production keyspaces. This exercise tests RF changes on **existing data**, not just new writes.

**Setup:**

~~~sql
CREATE KEYSPACE rf_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': '2'
};

CREATE TABLE rf_lab.events (
  tenant_id text,
  event_id int,
  payload text,
  PRIMARY KEY ((tenant_id), event_id)
);

INSERT INTO rf_lab.events (tenant_id, event_id, payload)
VALUES ('team_a', 1, 'before-rf-change');

INSERT INTO rf_lab.events (tenant_id, event_id, payload)
VALUES ('team_b', 2, 'also-before-rf-change');

SELECT * FROM rf_lab.events WHERE tenant_id = 'team_a';
~~~

**Observe RF before and after `ALTER`:**

~~~bash
nodetool status
nodetool getendpoints rf_lab events team_a
~~~

~~~sql
ALTER KEYSPACE rf_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': '3'
};

DESCRIBE KEYSPACE rf_lab;
~~~

Re-run `getendpoints` for `team_a` and `team_b` to observe the **designated** replica sets. Notice that endpoint changes alone do not prove historical data has streamed. Next, run scheduled full repair across all relevant nodes:

~~~bash
nodetool repair --full -pr rf_lab
~~~

Check completion logs across all executed nodes, re-read both partitions, and observe load. Once full repair convergence is verified, test lowering RF back to 2:

~~~sql
ALTER KEYSPACE rf_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': '2'
};
~~~

Run per-node cleanup in the lab, then re-check `getendpoints`, disk usage, and read success. Self-check questions:

1. If `ALTER` from RF 2 to 3 finished but full repair has not run yet, why can a `ONE` query return empty?
2. Why is one repair run on a single node insufficient to claim the whole cluster is repaired?
3. If RF drops from 3 to 2, why does `LOCAL_QUORUM` resilience to one dead replica change?
4. Why cannot cleanup substitute for full repair when raising RF?
5. If a DC has two nodes and you set RF = 3, is the flaw in metadata, physical replica count, or CL availability as well?

**Guided answers:** (1) the new replica may not hold historical data yet; (2) repair only covers that node/command's range scope; (3) with RF 2, quorum requires both copies; (4) cleanup removes unowned data rather than streaming old data to new replicas; (5) the target of three independent replicas cannot be met with two nodes.

## 10. Operational Takeaways

Changing RF is a **multi-step data redistribution workflow**, not a single CQL statement:

~~~text
Raising RF:
  Check health/capacity
      -> ALTER KEYSPACE
      -> schema agreement
      -> FULL REPAIR across all relevant cluster ranges
      -> verify data + metrics

Lowering RF:
  Check durability/backups/CL
      -> ALTER KEYSPACE
      -> schema agreement
      -> CLEANUP on relevant nodes
      -> verify data + disk usage + metrics
~~~

Two deciding rules: **raising RF requires populating existing data onto new replicas; lowering RF requires cleaning up excess copies and accepting reduced fault tolerance**. Testing, repair, cleanup, and monitoring plans must consider topology, token ranges, DCs, consistency levels, and all partitions that existed prior to the change.

## References

- [Apache Cassandra — Frequently Asked Questions: Can I change the replication factor on a live cluster?](https://cassandra.apache.org/doc/stable/cassandra/overview/faq/index.html)
- [Apache Cassandra — Repair: full vs. incremental, primary range, operating repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html)
- [Apache Cassandra — CQL Data Definition: CREATE/ALTER KEYSPACE and NetworkTopologyStrategy](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html)
- [Apache Cassandra — Production recommendations](https://cassandra.apache.org/doc/stable/cassandra/getting-started/production.html)
