# Per-Node Repair and Remaining Cluster-Wide Scope in Apache Cassandra

## 1. The Problem: Repairing One Node Does Not Mean the Whole Cluster Is Repaired

Apache Cassandra is a distributed **wide-column** database. Each partition is identified by a **partition key**, mapped to a **token range**, and stored across a replica group determined by the keyspace's replication strategy. Query-driven table design enables fast data access, but also means **storage responsibility is spread across many nodes**.

When the network flaps, a node goes down, writes succeed at a consistency level lower than the replica count, or hinted handoff fails to replay all mutations, replicas can end up with different data. **Anti-entropy repair** is the mechanism Cassandra uses to compare and synchronize data between replicas.

The central concern of the **Repair** chapter is scope: when an administrator connects to node A and runs `nodetool repair`, Cassandra does not automatically guarantee that every token range of every keyspace across the whole cluster has been fixed. A repair initiated from A normally processes **the token ranges A helps store or the specified primary ranges**, depending on flags. Ranges belonging solely to other replicas may still remain unchecked.

Therefore, three questions must be kept separate:

1. **Initiating node:** is the command run from A, B, or C?
2. **Repair scope:** which keyspaces/tables, token ranges, datacenters, and replica groups participate?
3. **Campaign coverage:** have all necessary ranges completed repair successfully, or are there unrun, failed, or skipped intervals?

> A "Repair completed" log line on one node confirms **a specific job** finished. It does not automatically prove **every replica of every partition across the entire cluster has converged**.

## 2. At What Unit Does Repair Operate?

### 2.1. Token Ranges and Replica Groups

Cassandra divides the token space into intervals. For each token interval in a keyspace, the replication strategy determines the set of nodes responsible for storing partitions within that interval. With RF=3, a partition has three replicas in the corresponding topology; across multiple datacenters, each DC can have its own RF.

One node may hold replicas for **many ranges** while **not holding** several other ranges. When using virtual nodes (vnodes), ownership is subdivided into many small intervals; the examples below are strictly logical illustrations and do not depict a real cluster's token ring.

### 2.2. What Does Anti-Entropy Repair Do?

A typical repair session can be understood as these logical steps:

1. Identify the keyspace/table, token ranges, participating replicas, and requested repair type.
2. Replicas prepare data for comparison, typically using a **Merkle tree** structure or version-appropriate validation mechanism.
3. Compare range contents to detect differences between replicas.
4. **Stream** needed data segments between replicas to reconcile them.
5. Update repair session progress/state; with incremental repair, also mark and organize SSTables regarding repaired state.

~~~mermaid
flowchart TD
    A["Operator selects keyspace, table, token ranges"] --> B["One node coordinates repair"]
    B --> C["Identify participating replicas"]
    C --> D["Validation / Merkle comparison"]
    D --> E{"Are there differences?"}
    E -->|Yes| F["Stream data needed to sync"]
    E -->|No| G["No differing data needs streaming"]
    F --> H["Record repair outcome for that scope"]
    G --> H
    H --> I["Update cluster-wide coverage"]
~~~

Repair **does not simply pull all data back onto the node running the command**. The initiating node acts as coordinator; the range's replicas can exchange data among themselves. Internal details vary by version and repair mode, yet the participating token/replica scope remains essential to record.

### 2.3. Different Layers of "Fullness"

| Phrase | Accurate Meaning | What Cannot Be Inferred |
|---|---|---|
| Repair on node A | A initiates repair for the selected ranges | All ranges on other nodes have been checked |
| Repair a keyspace | Tables/ranges of the keyspace within command scope | Other keyspaces have been repaired |
| Repair a table | One table and the selected ranges | Other tables in the same keyspace have been processed |
| **Full repair** | Repair mode examining data not limited solely to unrepaired portions per incremental mechanics | **Does not** mean auto-repairing the whole cluster |
| **Primary-range repair** | Processes only ranges where the node is considered primary owner per distribution and flags | Ranges the node holds only as a secondary replica were repaired by that node |
| Cluster-wide repair coverage | All target token ranges, keyspaces/tables, and DC scopes have succeeded outcomes | All future requests are guaranteed consistent or free of operational failures |

**Critical distinction:** the `--full` flag describes **the repair dataset/mode**, whereas cluster-wide scope depends on **which ranges actually ran and succeeded**.

## 3. Example: After Repairing A, the Cluster Still Has Unprocessed Ranges

Suppose a datacenter has five nodes A, B, C, D, and E with RF=3. For simplicity, illustrate five token ranges R1–R5, each with one primary owner and three replicas:

| Range | Primary owner (illustrative) | Three replicas storing data |
|---|---|---|
| R1 | A | A, B, C |
| R2 | B | B, C, D |
| R3 | C | C, D, E |
| R4 | D | D, E, A |
| R5 | E | E, A, B |

In reality, the token ring has far more intervals, and replica placement is determined by the partitioner, replication strategy, vnodes, and racks/DCs. This table is only for reasoning about coverage.

### 3.1. Running Once on Node A

If repairing A selects **all ranges where A is a replica**, A's scope is `{R1, R4, R5}`. Replicas in R1, R4, and R5 can be compared within that chosen scope. However:

- **R2** resides only on B, C, D.
- **R3** resides only on C, D, E.

Thus a single repair run from A does not cover R2 or R3.

If running **primary-range repair** with `-pr` from A, the scope in this example is narrower still: A initiates only **R1**. In return, you can organize a campaign running primary-range repair sequentially across each primary owner to avoid redundant work.

~~~text
All target ranges:           R1  R2  R3  R4  R5
Repair all replicas on A:     X   -   -   X   X
Not covered by A:             -   X   X   -   -

Repair -pr on A:             X   -   -   -   -
After -pr on A:              R2, R3, R4, R5 still pending
~~~

However, **range R1 repaired from A does not mean only A's data was processed**: repair can compare and transfer data among A, B, and C, depending on participating members and validation outcomes.

### 3.2. Cluster-Wide Primary-Range Plan

An illustrative cycle:

| Turn | Node running `nodetool repair -pr` | Target primary range | Cumulative coverage |
|---|---|---|---|
| 1 | A | R1 | R1 |
| 2 | B | R2 | R1, R2 |
| 3 | C | R3 | R1, R2, R3 |
| 4 | D | R4 | R1–R4 |
| 5 | E | R5 | R1–R5 |

If every session completes successfully with stable topology and proper DC/replica scope, the campaign can cover all of R1–R5 by primary owner. Never equate the "one range per node" example with a real cluster: **vnodes place many ranges on each node**, and a campaign must track real ranges from token metadata.

### 3.3. Thinking in Terms of Coverage Sets

Let `U` be the target token ranges for a keyspace/table/DC. Let `S(A)` be the ranges repaired **successfully** across jobs initiated by A.

~~~text
U = {R1, R2, R3, R4, R5}

After repairing A:
S(A) = {R1, R4, R5}

Remaining = U - S(A) = {R2, R3}
~~~

If repair from B adds R2 while also re-running R1, new coverage grows only by R2; **repeating work does not increase coverage proportionally**. When computing remaining scope, take the **union of completed ranges**, exclude failed/aborted jobs, and match the exact keyspace, table, and DC.

## 4. `nodetool repair` Options to Distinguish

Syntax and defaults change across **Cassandra versions**. The commands below illustrate operational semantics; before running in production, inspect `nodetool help repair` for your active version.

~~~bash
# Repair scope is decided by version defaults if no extra flags are passed.
# Do not assume identical defaults across all versions.
nodetool repair my_keyspace

# Only primary ranges of the current node.
nodetool repair -pr my_keyspace

# Only one table in the keyspace; table name follows keyspace.
nodetool repair -pr my_keyspace orders_by_id

# Full repair (contrasted with incremental); still processes only the selected scope.
nodetool repair --full my_keyspace

# Combine full mode with primary-range scope, if supported by your Cassandra version.
nodetool repair --full -pr my_keyspace
~~~

| Option | What does it select? | Notes |
|---|---|---|
| Without `-pr` | Generally replica ranges the node is responsible for, depending on repair mode | Can overlap ranges when run repeatedly across nodes |
| `-pr` / `--primary-range` | Primary token ranges of the node | Used to build multi-node coverage schedules; does not mean one node covered the cluster |
| `--full` | Full repair, contrasted with incremental repair | "Full" refers to the method, not node count |
| Repair without `--full` | May default to incremental in many modern versions | Check version and impact on repaired/unrepaired SSTables |
| Table scope | Restricts repair to the specified table(s) | Omitted tables still require their own schedule |
| DC/host scope, e.g. `-local` or `-dc` | Restricts participating replicas per topology | Satisfies only that local/DC goal; does not automatically fix cross-DC drift |

### Incremental and Full Repair

**Incremental repair** typically inspects only data not yet marked repaired per version mechanics and updates related state upon success. It can reduce repeated validation in future cycles, but also introduces SSTable mechanisms like anti-compaction and more complex handling when repair is interrupted.

**Full repair** inspects a broader scope of data for the selected ranges and can consume more I/O and network bandwidth. Full repair likewise fixes only **the scope actually selected**.

Do not arbitrarily switch from incremental to full or mix both without planning. After an incremental session fails, inspect **actual repair state**, logs, and guidance for your exact Cassandra version; do not assume every range is clean simply because the process exited.

### Primary-Range Is Not Always the Only Plan

Running repair **without `-pr` sequentially across every node** can duplicate work on ranges sharing replica groups. Meanwhile, a **`-pr` campaign across owners** systematically partitions initiation scope, though it must account for DCs, topology, keyspaces/tables, and version traits.

If an organization uses repair orchestration software, that tool may split by token ranges and coordinate quite differently from the "run one command per node" model. What must still be preserved is **successful coverage of all target ranges**.

## 5. Datacenter Scope and Replication in Multi-DC Clusters

Suppose `NetworkTopologyStrategy` spans two datacenters:

~~~cql
CREATE KEYSPACE app_data
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3,
    'dc2': 3
};
~~~

Each token range has replicas in both `dc1` and `dc2`. A repair run solely among replicas in `dc1` can help `dc1` replicas sync with each other, but **does not guarantee they have been compared against `dc2`**.

### Local Repair and Cluster-Wide Repair Are Different Scopes

- **Single-DC scoped repair:** suitable when intentionally syncing only replicas within that datacenter; reduces cross-DC traffic.
- **Repair involving replicas from multiple DCs:** necessary when the requirement is cross-DC data convergence; consumes inter-DC bandwidth and experiences network latency.
- **Running `-pr` on every node of one DC:** requires understanding primary-range allocation in that DC; do not assume this suffices for replicas in another DC.

Flags like `-local` or `-dc` vary in meaning and valid combinations across versions. For multi-DC clusters, map out **range × DC × participating replicas** and clearly define whether the campaign targets **intra-DC** or **cross-DC** divergence. Never treat "ran repair on enough nodes" as proof if key DCs never participated in validation/streaming.

| Question to Resolve | If Ignored |
|---|---|
| Which replication strategy does the keyspace use, and what is RF per DC? | Required replicas may be missing from comparison |
| Can the inter-DC network sustain cross-DC repair? | Jobs may stall or fail |
| Was any DC partitioned longer than the hint window or grace period? | Data and tombstones may be missing |
| Does replication policy require cross-DC convergence? | Local repair finishes yet the cluster remains divergent across DCs |

## 6. Building a Table to Track Remaining Scope

Running a command and checking an exit code is not enough to know the whole cluster is repaired. A clear repair schedule needs a target range list and actual outcomes.

### 6.1. Suggested Coverage Ledger Structure

| Field | Meaning |
|---|---|
| `cluster_id`, `topology_epoch` | Cluster/topology snapshot at planning time |
| `keyspace`, `table` | Target data object repaired |
| `token_start`, `token_end` | Token interval; account for ring wrap-around and boundaries |
| `dc_scope`, `replica_set` | DC and replicas that actually participated |
| `repair_kind` | Full or incremental, plus relevant options |
| `coordinator`, `job_id` | Initiating node and session/job ID |
| `started_at`, `finished_at` | Actual timestamps |
| `result` | Succeeded, failed, aborted, not started |
| `verified_source` | Log/metrics/tool source used for verification |

You do not need a custom application to store a ledger: organizations can use existing repair schedulers and result stores. The critical requirement is **distinguishing "scheduled," "running," and "succeeded."** Only ranges with completion proof count toward coverage.

### 6.2. Computing Remaining Scope

A verification set for a campaign can be expressed as:

~~~text
Target:             all ranges of app_data.orders_by_id in requested scope

Completed:
  R1: SUCCESS
  R2: SUCCESS
  R3: FAILED
  R4: NOT_STARTED
  R5: SUCCESS

Remaining / needs reprocessing:
  R3 (failed)
  R4 (not yet run)
~~~

When an error hits one range, never mark the entire node "repaired" if the job only completed partially. After resolving the cause, re-run only the affected scope using mechanisms supported by your version/tooling.

### 6.3. Topology Changes Invalidate Old Plans

Bootstrap, decommission, replace, token move, or RF changes alter **replica ownership**. If a coverage plan was generated before that change, the primary owner list or replica groups may no longer be accurate.

Snapshot topology before every major campaign. If topology shifts mid-campaign, recompute ownership, identify ranges needing re-repair, and avoid recording outcomes under the old topology as proof for the new scope.

## 7. Tools for Gathering Evidence Before and During Repair

With appropriate permissions, check cluster health and topology before starting. Example commands on a Cassandra node:

~~~bash
# Node and datacenter status.
nodetool status

# Token range and endpoint description by keyspace, as supported by version.
nodetool describering app_data

# Streaming activity information (not a substitute for repair logs).
nodetool netstats

# Compaction tasks that may contend for I/O with repair.
nodetool compactionstats

# Check exact options for your version.
nodetool help repair
~~~

After initiating, inspect command output/exit code, server logs, and version-provided repair/validation/streaming metrics. When using a repair orchestrator, check task/session IDs and succeeded token ranges reported by that tool.

**Do not use `nodetool status` to declare data synchronized.** An `UN` (Up/Normal) node only reflects membership status—it does not prove ranges have undergone anti-entropy repair.

### Symptoms to Watch For

| Symptom | Possible Cause | Next Check |
|---|---|---|
| Repair on one node reports SUCCESS while other nodes have no schedule | Many ranges remain out of scope | Cross-check token map and ledger |
| Repair halts during validation/streaming | Network, disk, heap, SSTable, node down | Inspect session/logs, fix root cause, re-run failed scope |
| Pending compactions and latency rise | Repair contending for I/O with traffic/compaction | Reduce concurrency, split scope, throttle schedule |
| One DC finished repair yet another DC remains divergent | Scope was intra-DC only | Review inter-DC plan and replication |
| Old data "resurrects" even after repair | May involve tombstones purged too early | Investigate `gc_grace_seconds`, outages, and repair history; evaluate rebuild |
| Running an old repair plan after node replacement | Token ownership shifted | Recompute ranges and replica sets |

## 8. Repair and Fault Tolerance: Hints, Tombstones, `gc_grace_seconds`

### 8.1. Hinted Handoff Does Not Replace Repair

Hinted handoff can store mutations for a temporarily absent replica and replay them when it returns. However, **the hint window, hint storage capacity, and replay** all have limits. When a node is absent for a long time, there is no guarantee all missed mutations during the outage were recovered via hints.

Repair compares actual data across replicas, making it essential for long-term anti-entropy. Schedules must ensure every scope is reconciled before deletion markers become hazardous.

### 8.2. Tombstones and Zombie Data Risk

A delete in Cassandra creates a tombstone to shadow older versions. If replica C loses connectivity and misses a delete while other replicas compact away eligible tombstones from SSTables, when C returns **zombie data** can occur: seemingly deleted data reappears.

`gc_grace_seconds` governs tombstone retention duration to reduce that risk, but it is not a safety switch guaranteed in every topology. Physical purging also depends on overlapping data, compaction, and version conditions. Repair schedules must align with grace periods and real outages.

**Do not treat "repair finished after tombstones were already lost" as proof zombies were prevented.** For nodes offline too long or suspected of missing deletes, evaluate rebuild/replace from healthy data sources per runbook.

### 8.3. Per-Node Repair Must Complete Full Cycles

Suppose `gc_grace_seconds` is configured for a finite safety window. If you repair only A weekly while B/C/D/E never enter a complete schedule, ranges outside A may go unreconciled before tombstones become eligible for purging. **The interval between successful repairs for each range** is what must be tracked—not merely an isolated count of "how many nodes ran a command."

The operational goal should be **a repair cycle with clear scope and evidence**, matched to data type, uptime, retention, TTL, and recovery policies.

## 9. Runbook: Organizing Per-Node Repair and Identifying Remaining Scope

### Step 1 — Define the Target

List the keyspaces/tables needing repair, replication strategies, per-DC RFs, current topology, and intra-DC vs. cross-DC sync requirements. Exclude or categorize objects intentionally by policy; never accidentally skip a table just because a command omitted it.

### Step 2 — Partition Token Ranges Without Gaps

Use token metadata and orchestration tools to build a worklist. If implementing primary-range repair, assign ranges by owner and verify every range has an owner in the schedule. If opting to repair all replica ranges per node, account for overlap to manage load.

### Step 3 — Check Safety Conditions and Capacity

Before running, check node up/down status, free disk space, compaction backlog, read/write latency, network, Cassandra version, and other streaming jobs. Repair can require validation, data streaming, and compaction/anti-compaction, so keep capacity and I/O headroom.

### Step 4 — Execute with Throttling

Never blindly run in parallel on all nodes without proving sufficient resources. Choose concurrency and execution hours based on workload. Group ranges/nodes to limit jobs contending for the same disks and network links, especially in multi-DC clusters.

### Step 5 — Record Every Outcome

Collect outputs/logs/metrics and update the ledger with `SUCCESS`, `FAILED`, or `NOT_STARTED` for the corresponding range and table. An aborted job must not be marked succeeded merely because it ran partway.

### Step 6 — Handle Remaining Scope

Compute the difference between all target scopes and succeeded scopes. Re-run failed ranges, unrun scopes, and segments needing re-evaluation after topology shifts. Do not repeat an entire cycle just because a script is easier to write if tooling lets you fix only the remainder cleanly.

### Step 7 — Verify and Schedule the Next Cycle

Verify every target range/table/DC hit target coverage, jobs exited cleanly, no sessions are stuck, nodes are healthy, and metrics returned to baseline. Record the last completion timestamp **by range**, not only by node; schedule the next cycle early enough relative to tombstone/repair policies.

## 10. CQL and Java Example: Readable Data Does Not Prove the Cluster Is Repaired

### 10.1. Creating a Keyspace and Table for Queries

Suppose a DC named `dc1` has RF=3. In real deployments, the datacenter name must match topology:

~~~cql
CREATE KEYSPACE app_data
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE app_data.orders_by_id (
    order_id uuid PRIMARY KEY,
    state text,
    updated_at timestamp
);

INSERT INTO app_data.orders_by_id (order_id, state, updated_at)
VALUES (
    11111111-1111-1111-1111-111111111111,
    'PAID',
    '2026-11-21T08:00:00Z'
);
~~~

Reading by partition key:

~~~cql
CONSISTENCY LOCAL_QUORUM;

SELECT state, updated_at
FROM app_data.orders_by_id
WHERE order_id = 11111111-1111-1111-1111-111111111111;
~~~

A successful `LOCAL_QUORUM` query lets the application observe state consistent with the chosen consistency level. However, **it does not check all token ranges**, prove remaining replicas caught up on every mutation, or replace anti-entropy repair.

### 10.2. Java Driver 4.x with Explicit Read Consistency

Assuming `CqlSession session` is connected to the right DC and the table exists:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.UUID;

PreparedStatement lookup = session.prepare(
    "SELECT state, updated_at FROM app_data.orders_by_id " +
    "WHERE order_id = ?"
);

UUID orderId =
    UUID.fromString("11111111-1111-1111-1111-111111111111");

BoundStatement statement = lookup.bind(orderId)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

Row row = session.execute(statement).one();
if (row != null) {
    String state = row.getString("state");
    // Use the value for business logic. This is not a repair outcome.
}
~~~

Java applications must design partition keys, read/write CLs, retries, and timeout handling for business requirements. **Managing repair is a distributed operations task**—you cannot conclude the whole cluster is repaired from a `SELECT` result or because the Java driver connected successfully.

### 10.3. Running Repair for This Table

Example running on each selected node:

~~~bash
# Primary range scope of the current node for the target table.
nodetool repair -pr app_data orders_by_id
~~~

After this command on A, the operator must still mark ranges not initiated by A and continue the schedule across remaining nodes. If choosing full repair:

~~~bash
nodetool repair --full -pr app_data orders_by_id
~~~

Verify **Cassandra version, flag options, and repair policy** before applying. The two illustrative commands differ in repair mode; both remain bounded to the initiating node's primary ranges and the specified table scope.

## 11. Incident Scenario: Repair on A Succeeded, Yet B/C/D Data Still Diverges

In a 5-node cluster with RF=3, repair runs from A after an outage. The command reports SUCCESS; days later, the application reads a partition whose primary/replica set is B, C, D and finds inconsistent data.

**Investigate hypothesis by hypothesis:**

1. **Was the partition's range repaired by A?** In the example, R2 resides only on B, C, D and is outside A's scope; repairing A never touched it.
2. **Was the command scoped by table/keyspace or primary range?** A `-pr` repair on A never covers R2.
3. **Did the job truly SUCCEED for every range it took?** Could a session have failed while someone checked only incomplete console/exit output?
4. **Is there another datacenter outside the repaired scope?** Local repair may not resolve cross-DC divergence.
5. **Did topology change after repair?** Ownership/replica sets may have shifted; coverage must be refreshed.
6. **Was there a very long outage or purged tombstones?** If zombie-data risk exists, evaluate safe repair vs. rebuild.

**Resolution path:** identify the token range of the affected partition, current replica set, and prior repair sessions; mark R2 as uncovered or failed, then schedule an appropriate repair session for R2 and any remaining ranges. In parallel, audit the cluster-wide schedule rather than patching just one visible partition.

Never manually overwrite a replica with ad-hoc writes hoping to sync everything: normal CQL writes only apply the requested mutations and can mask symptoms of the underlying error.

## 12. Practice Exercises with Answers

**Question 1.** There are five ranges R1–R5. Node A stores R1, R4, R5. A repair from A covering all its replica ranges completes. Which parts remain uncovered by A?

**Answer:** R2 and R3. One successful repair on A does not mean the entire cluster is complete.

**Question 2.** A runs `nodetool repair --full -pr app_data orders_by_id`. Can this be called a "full cluster repair"?

**Answer:** No. `--full` specifies the repair mode; `-pr` restricts scope to A's primary ranges; the table is also explicitly scoped. Other nodes/ranges need their corresponding schedule.

**Question 3.** After A/B/C finish per schedule, D's job fails and E has not run yet. Is a report saying "5/5 nodes initiated repair" enough to prove coverage?

**Answer:** No. You need **per-range success outcomes**. Ranges assigned solely to D or E in the schedule remain part of remaining scope.

**Question 4.** A cluster has `dc1` and `dc2`. All `dc1` nodes complete local repair, yet `dc2` had a long network partition. Can you conclude all replicas cluster-wide are identical?

**Answer:** No. You must evaluate ranges/replicas in `dc2` and cross-DC reconciliation goals—not just node counts in `dc1`.

**Question 5.** Node C was down past the tombstone safety period; other replicas compacted and dropped some deletion markers. Should simply running repair from C always be treated as safe?

**Answer:** No. You must assess zombie-data risk, repair history, and potentially use rebuild/replace per runbook when stale data cannot be trusted.

**Question 6.** After a bootstrap event, a schedule built on old primary owners is still running. What should be done?

**Answer:** Refresh token ownership and replica sets from the new topology, verify which ranges completed validly, and reschedule the missing portions.

## 13. Summary

In Cassandra, **repair is coordinated from one node but scoped by token range, keyspace/table, and participating replicas**. Therefore:

- **One node repairing successfully** confirms only the scopes that command selected and completed—not the entire cluster.
- **Full repair** and **primary-range repair** answer two different questions: repair mode vs. which ranges are selected.
- **Running `-pr` sequentially per plan** can partition coverage cleanly, but must account for all owners and real topology/DCs.
- **Remaining scope** is the set of ranges not yet repaired successfully—including failed jobs, unrun jobs, wrong DC/table filters, or ownership shifts.
- **Anti-entropy repair** differs from hinted handoff, read repair, and compaction; repair must be scheduled before tombstones lose safety guarantees, especially after long outages.
- **Measuring coverage by range, table, and DC** is far more reliable than counting nodes where commands ran or reading one partition successfully from Java.

In operations, start from a **target scope list**, orchestrate throttled repair by node/range, keep completion evidence, and backfill remaining scopes. Only when every required scope shows a succeeded result is there a basis to say a cluster-wide repair campaign met its target—and even then, it does not replace error monitoring, recurring repair schedules, and safe replication practices.
