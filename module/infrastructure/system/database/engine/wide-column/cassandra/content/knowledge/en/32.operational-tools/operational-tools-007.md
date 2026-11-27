# nodetool repair/rebuild/cleanup and Data Impact Scope

> **Chapter:** Operational Tools  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — Apache Cassandra distributed architecture and wide-column model, query-driven table design, partition keys, read/write consistency, CQL, replication, compaction, repair, failure handling, and Java application connectivity.

A Cassandra node may hold data it **rightfully owns**, **lack data it should hold**, or **retain data it no longer owns** after a topology change. The three commands `nodetool repair`, `nodetool rebuild`, and `nodetool cleanup` all act on node data, yet address **three distinct problems**:

- **`repair`:** compares data across replicas and synchronizes differences, supporting long-term consistency.
- **`rebuild`:** uses streaming to populate the token ranges **the current node should own** from source nodes; commonly used when adding a datacenter.
- **`cleanup`:** removes data for token ranges **the current node no longer needs to retain** after ownership changes.

Picking the wrong command can impose heavy load without fixing the issue: running `cleanup` does not "fix" a replica missing data, and `repair` does not necessarily purge excess post-bootstrap data. None of these commands replaces proper partition key design, sensible replication factor (RF), appropriate consistency level (CL), or backup/restore procedures.

**Version scope:** these principles apply to Apache Cassandra 4.x–5.x and many earlier releases, though CLI flags, default `repair` options, streaming scope, and monitoring mechanisms can vary by version/distribution. Before running in production, check `nodetool help repair`, `nodetool help rebuild`, and `nodetool help cleanup` on the **exact installed version**, along with the cluster topology runbook. All operational commands in this lesson are intended for an **isolated lab cluster**; large-load examples are illustrative only.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the differences among **logical token ownership**, **replica placement**, **physically stored data**, and **replica synchronization**.
2. Choose `repair`, `rebuild`, or `cleanup` accurately for a scenario and identify which node's data is affected.
3. Explain scope by node, keyspace, table, token range, datacenter, and participating replicas rather than misassuming one `nodetool` call covers the entire cluster.
4. Distinguish standard repair, **incremental repair**, and **full repair**, as well as the purpose of scoping repair ranges.
5. Describe prerequisites and post-checks when rebuilding a node in a new datacenter or running cleanup after topology changes.
6. Monitor streaming, repair, compaction, capacity, and availability; interpret timeouts, tombstones, compaction, and Java client requirements during maintenance.

## 2. Four Concepts to Check Before Choosing a Command

### 2.1. Token Ownership Is Not Physical Data

Cassandra maps **partition key → token → replica endpoints** based on the partitioner, node token assignments, and keyspace replication strategy. With `NetworkTopologyStrategy`, RF is declared per datacenter. Each node only needs to store partitions belonging to token ranges where it serves as a replica under current topology.

However, after an outage or topology change, physical state can diverge from desired state:

| State | Example | Action Required |
|---|---|---|
| Node is **assigned** as a replica but missed recent mutations | Node was Down while other replicas acknowledged writes | Reconcile and sync replicas via repair per procedure |
| New node in a DC **needs to receive** its token ranges | Expanding into a second DC and populating new replicas | Scenario-appropriate streaming/bootstrap/rebuild |
| Node is **no longer assigned** as a replica for some ranges | Adding a node shifted token ownership | Cleanup excess data **after** confirming the new owner received it |
| Node holds both owned data and excess data | Post-topology change prior to cleanup | Keep serving owned ranges; clean up ranges no longer owned |

Note: `nodetool status` displays node state and token ownership, yet **does not prove a specific partition has full data or all replicas are synchronized**. Expected endpoint lists come from metadata; actual data content must be verified via repair/streaming metrics and appropriate queries.

### 2.2. Difference Among the Three Commands in One Diagram

~~~mermaid
flowchart TB
    R["Multiple replicas share the same token range"] --> Q["repair: compare and synchronize differences"]
    S["New node / new DC needs data for assigned ranges"] --> T["rebuild: stream data from sources to current node"]
    U["Old node retains data for ranges whose ownership moved"] --> V["cleanup: remove excess data on current node"]
    Q --> W["Goal: consistent replicas"]
    T --> X["Goal: node holds data it should own"]
    V --> Y["Goal: node reclaims no-longer-needed disk space"]
~~~

| Attribute | `nodetool repair` | `nodetool rebuild` | `nodetool cleanup` |
|---|---|---|---|
| Primary question | Do replicas for the same range differ? | Where does this node get the data it should own? | Does this node still hold ranges it no longer owns? |
| Core impact | Compares hashes/ranges, streams divergent data across replicas | Streams ownership-matching data to the **receiving node** | Deletes physical data **no longer owned by the node running the command** |
| Impact scope | Ranges within repair scope on the initiating node and participating peers | Ranges the current node must receive | Ranges the current node **no longer** replicates |
| Generates network I/O | Yes, potentially heavy | Yes, typically heavy when populating data | Mostly scans/rewrites local SSTables; not a tool to supply replicas to a new node |
| Generates disk/CPU I/O | Yes: reading data, Merkle trees, streaming, related compaction | Yes: receiving/writing SSTables, validation/indexing, related compaction | Yes: scanning/rewriting SSTables and releasing files |
| Used when a long-Down node returns | Possibly needed if within safety bounds; check `gc_grace_seconds` | Only when part of an appropriate re-population workflow | Does not recover missed data |
| Used after adding a node | Optionally per runbook to verify/fix divergence | Not run on all existing nodes by default | Normally run on old nodes after streaming and topology stabilize |
| Used when adding a new datacenter | Needed ongoing per consistency schedule | Common streaming step for new nodes in the new DC | Only if a node retains ranges it no longer owns |

**Operational scope is always bound to keyspace and topology.** A keyspace with RF=3 in `dc1` and RF=0 in `dc2` has a very different definition of "replicas that must hold data" from one with RF=3 in both DCs. Never run a command for one keyspace and assume every datacenter sees the same effect.

## 3. nodetool repair: Reconciling Replicas of the Same Token Range

### 3.1. What Problem Does Repair Solve?

Suppose a partition is replicated on three replicas A, B, and C (RF=3). A and B record a new mutation, while C was disconnected and still holds an older value. Once C returns, **hinted handoff** can replay some missed mutations, but hints are bounded by storage/time windows and do not guarantee all divergence is healed.

**Anti-entropy repair** inspects data across replicas for selected token ranges. It uses mechanisms such as Merkle tree comparisons and streaming divergent ranges to heal discrepancies. Exact algorithms, subrange grouping, and repair state tracking vary by version, while the goal remains **bringing participating replicas into consistent data state**.

~~~text
Before repair:
  Replica A: K = V2
  Replica B: K = V2
  Replica C: K = V1 (missed mutation)

Repair on token range containing K:
  detect discrepancy -> stream missing data/updates

After successful repair and verification:
  A, B, C hold consistent data state
~~~

**Repair does not "take the initiating node's latest data and overwrite every other node".** Cassandra compares versions, timestamps, and tombstones per conflict-resolution rules. Under concurrent writes with skewed timestamps, "newest" by app wall-clock time may not match the winning version in Cassandra.

### 3.2. Scope of a Single Repair Invocation

Illustrative commands:

~~~bash
# Repair using the running version's defaults (check help first).
nodetool repair operational_lab

# Full repair for one table in a keyspace, in a lab cluster.
nodetool repair --full operational_lab events_by_device
~~~

When invoking `nodetool repair` on node X:

1. Node X is the **initiator** of the repair session; it selects ranges within the scope defined by the command/repair mode.
2. Other replicas for those ranges **participate**, consuming CPU, I/O, and network to compare/stream data.
3. Token ranges **outside the selected scope** are not automatically repaired merely because they belong to the same keyspace.
4. In a multi-node cluster, running one command on **an arbitrary node** does not mean all cluster data has been covered. Full token-range coverage requires scheduling by ownership and version.

For a keyspace with multiple tables, depending on invocation flags, repair may apply to all default-eligible tables or only named tables. Scoping by **keyspace/table** narrows workload without altering the core principle: repair must cover the relevant **ranges and replicas**.

### 3.3. Incremental Repair, Full Repair, and Repaired SSTables

| Mode | Goal | Limits / Points to Remember |
|---|---|---|
| **Incremental repair** | Tracks/marks repaired data ranges so subsequent runs focus on unrepaired data | Carries repair session state and repaired/unrepaired separation; requires consistent operational scheduling |
| **Full repair** | Reconciles all data in the selected scope, not limited to unrepaired data | Can be expensive; not intended to run continuously on all nodes |
| **Preview repair** (if supported by version) | Estimates/checks data divergence without performing the same state repairs as real repair | Does not replace completed repair; verify behavior/flags via `help` |

In Cassandra 4.x/5.x, `nodetool repair` typically defaults to **incremental repair** and uses `--full` to select full repair. Options and capabilities in 3.x or other distributions may differ; never read an old runbook and assume an unflagged call runs full repair.

Do not mix incremental and full repair haphazardly during topology changes. Incremental repair tracks metadata/state and has specific recovery rules if interrupted; schedules must cover the right ranges, DCs, and tables, and verify actual completion.

### 3.4. Limiting Scope by Datacenter and Primary Range

Depending on version, `nodetool repair` offers options such as:

- `--full`: full repair mode.
- `-pr` or `--partitioner-range` in some releases: repairs only the node's **primary ranges**, often used in multi-node schedules to reduce redundant work; verify exact flag names.
- `-local` or datacenter-scoping options: restricts participants to the **local DC** per version semantics, which may leave cross-DC divergence unreconciled.
- Options scoping keyspaces, tables, token ranges, nodes, or parallelism, depending on release.

**Do not assume running `-pr` on one node repairs all replicas of a keyspace**, or that `-local` synchronizes across DCs. In multi-DC setups, understand participant scope, replication strategy, and repair objectives before scheduling.

### 3.5. Tombstones, `gc_grace_seconds`, and Zombie Data Risk

A replica may miss a `DELETE` and retain old data. Tombstones on surviving replicas mask that old data during synchronization, yet tombstones become eligible for compaction purge **once `gc_grace_seconds` elapses** and local conditions are met.

If a node that missed a delete returns **after tombstones on other replicas were purged**, old data can spread back as **zombie data**. Therefore:

- Repair must run frequently enough and **complete**, leaving safety margin ahead of the grace window.
- Never shrink `gc_grace_seconds` solely to save disk without an active repair schedule, Down-node monitoring, and trusted recovery procedures.
- A node disconnected longer than grace may require **rebuild/replace from clean sources** per runbook rather than simply rejoining and running normal repair.
- `nodetool cleanup` does not prevent zombie data; it has no knowledge of historical tombstones if the data range still belongs to the node.

## 4. nodetool rebuild: Populating Owned Data via Streaming

### 4.1. Purpose and Data Sources

`nodetool rebuild` instructs **the node running the command** to stream data from source nodes for the token ranges it must hold under current replication metadata. The classic scenario is **expanding to a new datacenter**: new-DC nodes have joined the cluster without a full data copy yet and pull data from an existing DC.

Logical structure example:

~~~text
Before expansion:
  dc1: A, B, C; keyspace RF dc1 = 3

After new topology is properly configured:
  dc1: A, B, C
  dc2: D, E, F; keyspace RF dc1 = 3, dc2 = 3

Goal:
  D, E, F (dc2) receive data for the ranges each node must hold.
  Replicas in dc1 continue serving apps with appropriate CL/routing.
~~~

Common CLI example:

~~~bash
# Run on a new node in dc2; "dc1" is the actual source DC name.
nodetool rebuild dc1
~~~

Many versions take the source datacenter argument at the end of the command; specifying keyspaces, tokens, or filters (if available) varies by version. Run `nodetool help rebuild` on the target node before applying. **Never run it across all nodes in all DCs simultaneously** thinking it is a "cluster-wide refresh" command.

### 4.2. Specific Scope of Rebuild

| Aspect | Scope to Understand |
|---|---|
| **Target** | **Current node** where `nodetool rebuild` is invoked |
| **Sources** | Source nodes holding data to stream, optionally restricted to a source DC |
| **Token ranges** | Ranges the receiving node must own per topology/keyspace |
| **Data** | Data for keyspaces/tables within rebuild scope supported by the version |
| **Data path** | Network streaming, writing SSTables/disk on the receiving node |
| **Impact** | Sources incur disk/network reads; target incurs network/disk writes and background work |

**Rebuild is not a cluster-wide snapshot restore.** It does not take backups automatically, cannot fix old data if sources themselves are missing/corrupt, and cannot target "an arbitrary node" by name when invoked against a different CLI node. The target is **the node controlled by `nodetool`**.

### 4.3. Rebuild vs. Bootstrap and Node Replacement

These workflows are related but **not identical**:

- **Bootstrap**: a new node joins the ring and receives its required ranges via the cluster join workflow.
- **Rebuild**: a node already in topology receives/re-receives its range data via streaming; commonly part of adding a DC.
- **Replace**: replacing a dead node with a new node via replacement/bootstrapping mechanisms and proper configuration; never assume `rebuild` alone replaces the full replacement runbook.

Adding a new DC requires careful ordering across snitch/DC/rack config, replication strategy, node count, bootstrapping, and streaming. Never change DC/rack names on a live production node and run rebuild to "move" the node elsewhere.

### 4.4. Why Must a Successful Rebuild Still Be Verified?

A streaming session ending successfully means the scoped streaming job finished; it **does not automatically guarantee**:

- All active keyspaces declared RF in the target DC properly.
- All clients configured the right local datacenter and CL for multi-DC operation.
- Source replicas were synchronized prior to streaming.
- Concurrent writes arriving during the transition left no divergence needing follow-up repair/reconciliation.

Therefore, after rebuild, verify schemas, sample partition endpoints, stream completion, table stats, reads at target CL, and upcoming repair schedules.

## 5. nodetool cleanup: Removing Ranges No Longer Owned by the Node

### 5.1. When Does Excess Data Appear?

Suppose `dc1` has A, B, and C, each replicating ranges per old RF/topology. Successfully adding D shifts token/range assignments; some ranges move to D or get reassigned. Cassandra streams needed data to D, yet old SSTables on A/B/C may still contain partitions they no longer need to retain under the new ring.

`nodetool cleanup` checks current ownership and **removes physical data no longer falling within the local node's replica responsibility**. This reclaims disk space after topology changes.

~~~bash
# Example only in a lab cluster where streaming/topology has completed.
nodetool cleanup operational_lab

# Target table only:
nodetool cleanup operational_lab events_by_device
~~~

In production, this command can generate heavy disk I/O by reading/rewriting SSTables; verify scope and service impact before running.

### 5.2. Cleanup Data Scope

| Question | Answer |
|---|---|
| Which node does cleanup act on? | The node controlled by `nodetool`; does not automatically clean other nodes |
| Which data does it delete? | Data belonging to **ranges no longer replicated by that node** within the keyspace/table scope |
| Does it send data to the new owner? | **No**: cleanup only deletes leftover copies; the new owner must already have received data via bootstrap/streaming |
| Does it delete rows a client just `DELETE`d? | Not by that business logic; tombstone purging belongs to compaction and separate safety rules |
| Does it fix missing data on another replica? | No; use streaming/rebuild/repair as appropriate |
| Why might disk not drop immediately? | Files may be rewritten/released alongside compaction and SSTable management; snapshots or other files can still pin space |

Never run cleanup while the cluster is still transitioning, while a new node has not finished streaming, or while any replica risks losing the sole copy of a range. **Confirm the new owning node is Up/Normal and holds the data before cleaning old nodes.**

### 5.3. Why Might Disk Still Look Full After Cleanup?

Check for:

1. SSTables span multiple ranges, and rewrite/compaction is still running or holding temporary files.
2. Snapshots/hard links or filesystem backups still hold blocks even after live files were replaced.
3. Data the node still legitimately owns under RF/topology is large; cleanup never deletes owned data.
4. Commit logs, hints, transaction logs, or compaction backlogs consume disk.
5. Adding a node did not shift replica placement as expected; given specific RF and node counts, many ranges still belong to the old node.

Reclaimed disk bytes **cannot be calculated precisely** from an ownership ratio like "40% → 30%": vnodes, compression, partition/hot-key skew, snapshots, and RF prevent physical size from scaling linearly with token ownership.

## 6. Operational Stories: Three Easily Confused Scenarios

### 6.1. Scenario A — One Replica Down for 24 Hours

**Situation:** RF=3, one node is temporarily Down while writes at `LOCAL_QUORUM` keep succeeding on the two remaining replicas. After recovering the node:

1. Check `nodetool status`, logs, downtime duration, and `gc_grace_seconds` on critical tables.
2. Check whether hints functioned properly, **without relying on hints alone**.
3. Run repair on affected ranges/tables per runbook; monitor repair sessions, streams, and completion status.
4. Verify sample reads from the app/target CL and watch for read-repair/consistency symptoms.

**Primary command to consider:** `nodetool repair`. Do not run `cleanup` because replica ownership did not change, and do not default to `rebuild` if the node only missed a short write window safely within repair bounds.

### 6.2. Scenario B — Opening a New Datacenter

**Situation:** `dc1` is steady; adding `dc2` with D/E/F to serve local reads/writes.

1. Confirm actual topology, snitch/rack, per-DC RF, and sufficient nodes/disk/network; prepare the version-accurate DC-expansion procedure.
2. Bring new nodes into the proper state per runbook (bootstrap/initialization) instead of guessing order from one command.
3. Rebuild/stream on **each receiving node** in `dc2` from a valid source DC; monitor `nodetool netstats` and disk space.
4. Cross-check sample endpoints/partitions, test `LOCAL_QUORUM` reads in `dc2` only after replicas are ready, and schedule follow-up repair/reconciliation.

**Primary command to consider:** `nodetool rebuild dc1` on receiving nodes. `repair` handles ongoing maintenance/reconciliation, while `cleanup` applies only if ownership shifts leave excess data; it is **not** a substitute for streaming.

### 6.3. Scenario C — Adding a Node in a DC, Yet Old Disks Stay Full

**Situation:** A single-DC cluster adds node D; D is Up/Normal and finished streaming. Old nodes still hold many SSTables for ranges they no longer own.

1. Confirm all nodes are steady, streaming finished, and keyspace replica placement matches design.
2. Confirm no topology jobs are active; check snapshots/backups and ensure enough free space for SSTable rewrites.
3. Run `nodetool cleanup <keyspace>` **on each old node needing cleanup** on a staggered maintenance schedule to avoid simultaneous I/O storms.
4. Measure before/after disk usage, SSTable counts, compaction backlog, and app latency; verify data on the new owner.

**Primary command to consider:** `nodetool cleanup`. Do not substitute `repair` expecting disk usage to shrink on its own, and do not clean up node D solely because D is new without proving it holds out-of-range data.

## 7. CQL Lab and Observing Command Scope

### 7.1. Setup and Sample Data

Practice on a **test Cassandra cluster with at least three nodes** in a genuine datacenter named `dc1`, with `nodetool` and `cqlsh`. If your lab topology differs, adjust RF/DC/CL accordingly; pre-check with:

~~~bash
nodetool status
nodetool describecluster
nodetool help repair
nodetool help rebuild
nodetool help cleanup
~~~

In `cqlsh`:

~~~sql
SELECT release_version FROM system.local;

CREATE KEYSPACE IF NOT EXISTS operational_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS operational_lab.events_by_device (
    device_id uuid,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((device_id), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

INSERT INTO operational_lab.events_by_device
    (device_id, event_time, event_id, payload)
VALUES (
    d654b0fe-7357-497f-8db4-59b165d58a0f,
    '2026-11-21T09:00:00Z',
    80aaeac3-1f11-4f66-877f-d9ccfca2216d,
    'sample-event'
);

SELECT device_id, event_time, event_id, payload
FROM operational_lab.events_by_device
WHERE device_id = d654b0fe-7357-497f-8db4-59b165d58a0f;
~~~

**Note:** `IF NOT EXISTS` does not alter settings or key schemas of an already existing object. If `operational_lab` already exists, inspect `DESCRIBE KEYSPACE` and `DESCRIBE TABLE`; pick a different lab name if needed to avoid colliding with old RF/tables. Sample data is only for testing queries, **not** sufficient to benchmark repair/streaming.

### 7.2. Checking Replica Placement of the Sample Partition

On a node:

~~~bash
nodetool getendpoints operational_lab events_by_device d654b0fe-7357-497f-8db4-59b165d58a0f
nodetool tablestats operational_lab.events_by_device
nodetool netstats
nodetool compactionstats
~~~

Cross-check `getendpoints` with `nodetool status`. With RF=3 and enough physical nodes, metadata endpoints typically list three distinct nodes. **Being listed as an endpoint does not prove** the node finished streaming, is Up, or holds a complete data copy.

Record before selecting a command:

| Evidence | Observation to Save | Meaning |
|---|---|---|
| `nodetool status` | Nodes UN/DN, DC/rack, tokens, ownership | Topology state of each node |
| `getendpoints` | Replica list for the sample partition | Who **should** hold data for that key |
| `tablestats` | SSTable/disk size/read-write latency per table | Storage resources and changes |
| `netstats` | Streaming sessions and transfer status | Whether rebuild/repair is streaming or done |
| `compactionstats` | Active/pending compaction tasks | Forecasts potential I/O contention |
| Repair logs/metrics | Ranges/tables, sessions, and outcomes | Proof repair succeeded, not merely started |

### 7.3. Testing Repair on a Small Scope

Choose one lab table, and record timestamp and background load. If the cluster has sufficient nodes and resource budget:

~~~bash
# Full repair of a single table in the lab; can generate notable load.
nodetool repair --full operational_lab events_by_device
~~~

While running, monitor on the initiating node **and participating peers**:

~~~bash
nodetool netstats
nodetool compactionstats
nodetool tpstats
~~~

Afterward, read session completion logs, check errors/timeouts, verify `UN` node status, and run sample queries at appropriate CL. **Never** infer "the whole cluster has been repaired" from running one command on one node and one table.

### 7.4. Rebuild and Cleanup Require Dedicated Topology Labs

You cannot accurately demonstrate `rebuild` or `cleanup` with `INSERT`/`SELECT` alone. They require **actual topology changes in an isolated environment**:

| Lab | Required Preconditions | Applicable Command | Proof of Success |
|---|---|---|---|
| Rebuild new DC | Target node initialized per runbook; DC/RF metadata and source valid | `nodetool rebuild dc1` on target node | Streaming completes, endpoints match, sample data readable in new DC |
| Cleanup after node expansion | New owner received ranges; all nodes steady | `nodetool cleanup operational_lab` on old node needing cleanup | Disk/SSTables change; still-owned ranges remain readable |
| Repair diverged replica | Replica missed mutations while still within safe recovery window | Scoped `nodetool repair --full operational_lab events_by_device` | Repair succeeds, logs/metrics align; no zombie data surfaces |

**Never simulate "missing replica" by manually deleting SSTable files.** That corrupts data and invalidates test conditions. Use controlled node outages/backup snapshots in the lab and follow version-accurate bootstrap/replace procedures.

## 8. When Must You Stop or Postpone Maintenance?

Repair, rebuild, and cleanup can all run long, consume heavy resources, and impact application p95/p99. Before every operation:

1. **Verify exact node and cluster:** IP/host, DC, version, keyspace/table, token ranges, cluster state. Never run in the wrong environment.
2. **Check RF/CL and live data:** confirm enough replicas remain available for reads/writes; account for recently Down nodes and tombstone grace.
3. **Check resources:** sufficient disk for streaming and temporary SSTables, network bandwidth, compaction backlog, CPU/GC, I/O errors.
4. **Bound scope and parallelism:** proceed one keyspace/table/node or small batch at a time per runbook; never launch across the entire cluster without estimating I/O.
5. **Prepare rollback/recovery:** snapshots/backups, pre-change token/topology inventory, and clear ownership for aborting/resuming jobs per version.
6. **Monitor clients too:** app p50/p95/p99, timeout/Unavailable errors, Java driver retry rates, and ingress queues.

**Postpone cleanup** if streaming to new owning nodes is incomplete or topology is still shifting. **Postpone broad rebuild** if the source DC is saturated or destination disk is tight. **Schedule repair within the grace window**; never defer repair indefinitely until tombstones risk purging.

### 8.1. Distinguishing Three Observational Outcomes

| Outcome | What It Proves | What It Does Not Prove |
|---|---|---|
| Command exits with code 0 | The operation completed within the command's scope per the tool | All out-of-scope keyspaces/nodes are consistent |
| `netstats` shows no active streams | No streaming session is active at read time | Missing source data was completely received in every case |
| Sample query reads cleanly at CL=ONE | One replica served a value at that moment | Other replicas have not diverged or contain no zombie data |
| `nodetool status` all UN | Nodes are Up/Normal in the queried node's view | SSTables are uncorrupted, repair is complete, or physical ownership is clean |
| Disk drops after cleanup | Data/files were reclaimed | New replicas are complete if streaming/CL was not verified |

The strongest conclusion combines **multiple layers of evidence**: accurate metadata, completed job logs/metrics with zero errors, critical data reading/writing accurately at target CL, and disk/network returning to baseline.

## 9. Implications for Java Applications and Consistency Levels

Java applications choose CL based on consistency needs and route by datacenter; they do not directly control `nodetool` range repairs. A write succeeding at `LOCAL_QUORUM` with RF=3 typically requires two replicas in the local DC to respond—**it does not guarantee the third replica received every mutation**. A node recovering from an outage still relies on hints/repair strategies.

Java Driver 4.x verification query example, assuming an existing `CqlSession session` configured with the right local datacenter:

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.UUID;

PreparedStatement ps = session.prepare(
    "SELECT event_time, event_id, payload " +
    "FROM operational_lab.events_by_device WHERE device_id = ?");

BoundStatement statement = ps.bind(
        UUID.fromString("d654b0fe-7357-497f-8db4-59b165d58a0f"))
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setPageSize(100);

ResultSet results = session.execute(statement);
for (Row row : results) {
    UUID eventId = row.getUuid("event_id");
    // Compare eventId and payload against verification data.
}
~~~

Topology changes can shift request distribution across nodes and alter latency. During rebuild/cleanup/repair, monitor **request timeouts, host errors, latency, retries, and pool saturation**, and ensure the driver knows the exact local DC. Unbounded retries while servers stream/repair can tip the system into overload. When a write timeout occurs, the mutation may already have landed on some replicas; never treat a timeout as a guaranteed rollback.

Verification queries should span multiple partitions and token boundaries without ignoring CL limits. When verifying replica synchronization, rely on repair/status metrics and runbook verification tools—never conclude from a single `SELECT` at `ONE`.

## 10. Common Misconceptions

| Claim | Assessment | Accurate Understanding |
|---|---|---|
| "Running repair on one node repairs the entire cluster" | Generally false | Covers only ranges and participants in command scope; needs a coverage plan |
| "Repair copies an entire keyspace from coordinator to other nodes" | False | Repair compares replica data and streams only necessary differences |
| "Rebuild finds and fixes all bad data on every node" | False | Rebuild populates ranges **the current node should own** |
| "Cleanup replaces repair after a replica goes Down" | False | Cleanup purges data **no longer owned by the node**; it does not sync replicas |
| "Right after adding a node, cleanup can always run immediately" | False | Wait for topology and streaming to finish and verify new owners |
| "Cleanup deletes expired tombstones" | Wrong tool purpose | Tombstone purging belongs to compaction and separate safety rules |
| "Running rebuild on any one node populates the whole new DC" | False | Each receiving node must run the required streaming step |
| "Full repair is always better than regular incremental repair" | Overstated | Full is resource-heavy; choose schedule/mode per version and ops needs |
| "`-local` fixes all cross-DC data divergence" | False | Limiting to local participants does not ensure cross-DC anti-entropy |
| "Hinted handoff completely replaces repair" | False | Hints are bounded; anti-entropy repair is still required |
| "Disk shrank means all data is safe" | Insufficient | Still need replica/streaming/CL checks and app health verification |
| "A 3.x runbook's flags work identically on 5.x" | Dangerous | Verify `nodetool help` and docs for the exact release |

## 11. Self-Check Scenarios

**Scenario A — Disconnected replica:** RF=3, one replica goes Down while QUORUM writes keep succeeding, then returns after two days. Cluster topology did not change; which command takes priority?

**Hint:** check downtime against `gc_grace_seconds`, hints status, and repair coverage. Prioritize **repair** scoped to the affected node/ranges; do not run cleanup. If downtime exceeded the safe grace window, use proper rebuild/replace workflows instead of blind repair.

**Scenario B — Opening a new DC:** `dc1` holds full data, and `dc2` has three new nodes joined to topology per runbook that have not yet received data. Which command populates ranges onto D/E/F?

**Hint:** on **each target node**, run the **rebuild/streaming** workflow from a valid source, e.g., `nodetool rebuild dc1` if matching version syntax. Check per-DC RF, netstats, and local-CL reads after completion.

**Scenario C — Expanding a DC:** after adding node D, topology is steady and D received its ranges; A/B/C still hold large old disk footprints. Which command, and where does it run?

**Hint:** run **cleanup on the old nodes needing cleanup** scoped by keyspace/table while monitoring disk and compaction—not solely on D. Never run while streaming is still active.

**Scenario D — Repairing one table:** `nodetool repair --full operational_lab events_by_device` succeeds on node A. Can you declare all tables in all DCs repaired?

**Hint:** **no**. The command selected only that specific table and the token/participant scope determined by the node and flags. A dedicated plan is required to cover other tables, ranges, and DCs.

**Scenario E — Purging tombstones:** a table has heavy tombstones and high p99, while topology has not changed. Is `cleanup` appropriate?

**Hint:** not the primary tool. Investigate TTL/DELETE patterns, partition size, SSTable overlap, `gc_grace_seconds`, repair, and compaction strategy; cleanup only removes ranges no longer owned by the node.

### End-of-Lesson Checklist

- [ ] Distinguish logical ownership, replica placement, and actual SSTable data.
- [ ] Distinguish repair, rebuild, and cleanup outcomes by **direction of data impact**.
- [ ] Describe keyspace/table, token ranges, nodes, and datacenters within each command's scope.
- [ ] Understand why one repair run on one node does not cover the entire cluster by default.
- [ ] Distinguish full/incremental repair and the role of `gc_grace_seconds`.
- [ ] Know that rebuild is typically used when adding a DC and differs from bootstrap/replace.
- [ ] Run cleanup only after new owners received data and topology stabilized.
- [ ] Collect `status`, `getendpoints`, `netstats`, `tablestats`, `compactionstats`, and logs before/after.
- [ ] Separate command exit success from evidence of data consistency and app SLOs.
- [ ] Never run heavy I/O commands cluster-wide simultaneously without bounded scope and a recovery plan.

## 12. References

1. Apache Cassandra Documentation — [nodetool repair](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/repair.html): syntax, modes, and repair scope.
2. Apache Cassandra Documentation — [nodetool rebuild](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/rebuild.html): streaming data to a node.
3. Apache Cassandra Documentation — [nodetool cleanup](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/cleanup.html): removing data no longer owned.
4. Apache Cassandra Documentation — [Anti-entropy repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html): purpose of repair, repair schedules, and tombstone safety.
5. Apache Cassandra Documentation — [Adding a datacenter](https://cassandra.apache.org/doc/stable/cassandra/operating/topo_changes.html): overview of topology changes and streaming.
6. Apache Cassandra Documentation — [nodetool status](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/status.html), [netstats](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/netstats.html), [tablestats](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/tablestats.html): inspection tools.
