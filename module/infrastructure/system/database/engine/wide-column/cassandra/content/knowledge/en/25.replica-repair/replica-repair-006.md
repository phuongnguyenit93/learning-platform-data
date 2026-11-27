# Repair Within a Datacenter or Across Datacenters in Apache Cassandra

## 1. Objective: Sync the Right Replicas in the Right Scope

Apache Cassandra is a **distributed wide-column** database. Each partition is identified by a **partition key**, may hold multiple clustering rows, and is stored across multiple replicas according to the configured **replication factor (RF)**. In multi-datacenter (DC) clusters, `NetworkTopologyStrategy` allows specifying a separate RF for each DC.

A CQL write may be acknowledged under `LOCAL_QUORUM` in the local DC before all replicas in other DCs acknowledge it. If a node fails, the network partitions, or a replica misses mutations, copies can diverge temporarily.

**Anti-entropy repair** is the operation where Cassandra compares and synchronizes data across replicas for a token range. A critical topic here is **choosing repair within one datacenter vs. repair across datacenters**:

- **Intra-DC / local repair:** compares replicas belonging to the same DC, avoiding sync streams crossing WAN links.
- **Cross-DC / inter-DC repair:** brings replicas across multiple DCs into comparison, catching and resolving drift that per-DC internal repair can miss.

The two approaches are not equivalent. **Running local repair separately in each DC is not enough to prove data across DCs has converged.**

In a Java application, setting read/write CLs, designing partition keys to fit queries, and maintaining an appropriate repair schedule are complementary decisions; no single decision replaces the others.

## 2. Two-DC Model: Which Replicas Actually Differ?

Suppose a cluster has two datacenters, each holding three replicas of the partition with key `order_id = O1`:

```text
               DATACENTER dc1                       DATACENTER dc2
           +----------------------+             +----------------------+
           | R1       R2       R3 |             | R4       R5       R6 |
           | status = PAID        |             | status = PENDING     |
           | status = PAID        |             | status = PENDING     |
           | status = PAID        |             | status = PENDING     |
           +----------------------+             +----------------------+
                 RF(dc1)=3                               RF(dc2)=3
                            <--- inter-DC network link --->
```

Assume `PAID` came from a valid mutation with a winning timestamp that never reached `dc2` due to a network disruption. At this point:

- A `LOCAL_QUORUM` read in `dc1` can return `PAID`.
- A `LOCAL_QUORUM` read in `dc2` can return `PENDING`.
- Repair **only within `dc1`** sees R1, R2, R3 already match, so it finds no local discrepancy to fix.
- Repair **only within `dc2`** also sees R4, R5, R6 match one another, even though all three are stale relative to `dc1`.
- Repair **scoped across `dc1` and `dc2`** is needed to compare both replica sets and deliver the winning mutation to the missing replicas.

This is a simplified example. With concurrent writes, tombstones, or TTLs, Cassandra reconciles data by **timestamps and cell rules**, not by picking "whichever DC has more copies." Do not infer wall-clock user ordering as the winner when client/coordinator timestamps from different sources can drift.

### Why Does Local Quorum Still Exist?

With RF = 3 in a single DC:

```text
LOCAL_QUORUM = floor(RF_DC / 2) + 1 = 2
```

Each read or write at `LOCAL_QUORUM` requires only two responses within the local DC to satisfy the CL; the coordinator may still contact additional replicas or forward writes to other DCs depending on the write path and cluster state. **Local CL is an acknowledgment condition**, not an instruction to "stop cross-DC replication."

Two local quorums in two different DCs **need not share any common replica**. Therefore, quorum intersection within a single DC cannot guarantee two DCs always return identical values at all times.

## 3. Anti-Entropy Repair Mechanism and What Data Is Compared

Repair does not simply copy an entire table from one supposedly "correct" node to all other nodes. On supported Cassandra versions, repair uses mechanisms such as **validation** and comparing data digest structures (such as Merkle trees) to detect mismatched ranges, followed by **streaming** the segments needing synchronization.

```mermaid
sequenceDiagram
    participant Op as Operator
    participant N as Repair Coordinator Node
    participant A as Replica A
    participant B as Replica B
    Op->>N: nodetool repair (with chosen scope)
    N->>A: Validation for token range
    N->>B: Validation for same token range
    A-->>N: Data digest
    B-->>N: Data digest
    Note over N: Compare, locate differing regions
    N->>A: Coordinate sync if needed
    N->>B: Coordinate sync if needed
    A<->>B: Stream data for regions needing repair
    A-->>N: Session result
    B-->>N: Session result
    N-->>Op: Complete or report error
```

This is a conceptual diagram; execution steps, source/destination selection, SSTable handling, and session reporting depend on Cassandra version as well as full vs. incremental repair.

A repair operation has at least **three scope layers** to define:

1. **Token range / partition:** which token intervals the initiating node is responsible for; range flags can narrow this further.
2. **Keyspace and table:** only the selected tables are included in the repair session.
3. **Participants:** which replicas are allowed to participate in comparison/streaming—local DC, specified DCs, or default configuration.

If any scope layer is narrowed, do not interpret the outcome as "all data on every replica has been synchronized."

## 4. Intra-DC Repair: Benefits and Boundaries

**Intra-DC repair** compares replicas within a single DC. It is typically chosen when:

- WAN bandwidth must be conserved because DCs sit across distant geographic regions.
- A replica in `dc1` just recovered from an outage while other replicas in `dc1` already hold updated data.
- Maintenance schedules separate **intra-DC** drift correction from **inter-DC** drift correction.
- Inter-DC links are currently constrained and cannot absorb heavy streaming immediately.

For example, `dc1` has three replicas:

| Replica in `dc1` | Value at partition `O1` |
| --- | --- |
| R1 | `PAID` |
| R2 | `PAID` |
| R3 | `PENDING` |

Local repair over ranges containing `O1` can compare R1/R2/R3 and sync R3 per reconciliation rules. **That still does not prove `dc2` has `PAID`**.

### The `nodetool repair -local` Command

When run on a node in **dc1**, for example to repair table `orders_by_id`:

```bash
nodetool repair -full -local repair_lab orders_by_id
```

Primary meaning of the options:

- `-full`: requests **full repair** rather than relying on the version's incremental default.
- `-local`: restricts participants to **the datacenter of the node running the command**.
- `repair_lab orders_by_id`: specifies the keyspace and table.

This command **does not automatically repair every token range in the whole cluster**. Range coverage pertains to the target node; covering all data in a DC or cluster requires a schedule across the appropriate set of nodes/ranges. Furthermore, it can fail if a required participant is unavailable.

> Remember: `-local` means "repair only with replicas in the local DC"—**it does not mean all data in other DCs is safe**.

### Is Running Local Repair in Every DC Enough?

Not necessarily. Consider:

```text
Before repair:
dc1: PAID, PAID, PAID
dc2: PENDING, PENDING, PENDING

After separate local repair in dc1:
dc1: PAID, PAID, PAID
dc2: PENDING, PENDING, PENDING

After separate local repair in dc2:
dc1: PAID, PAID, PAID
dc2: PENDING, PENDING, PENDING
```

Because each replica group is already consistent **internally**, no comparison crosses the DC boundary to detect differences between the two groups. A local-only schedule can verify intra-DC consistency while **failing to guarantee cross-DC convergence**.

## 5. Cross-DC Repair: When Is It Needed?

**Cross-DC repair** brings replicas across multiple DCs into the same comparison scope. It is critical when:

- A DC was network-isolated for a prolonged period and may have missed mutations from another DC.
- The system uses `LOCAL_QUORUM` reads/writes across **multiple DCs** and needs replicas to converge across regions.
- Individual DCs repaired locally yet continue returning different read results.
- Data must be synchronized after disaster recovery, streaming operations, or ahead of operational changes with strict consistency requirements.

### Illustrative Command for Non-Local-Restricted Repair

In versions with matching option semantics, a full repair **without `-local` or `-dc`** can involve replicas from all relevant DCs of the keyspace:

```bash
nodetool repair -full repair_lab orders_by_id
```

**Do not reflexively run this command on all nodes simultaneously.** It can stream data across WAN links, generate validation/streaming load across many replicas, and consume substantial bandwidth. Execute on a schedule across node/range scopes with concurrency limits and resource monitoring.

Some versions support restricting participants by DC:

```bash
# Example scope option; verify "nodetool help repair" for your version.
nodetool repair -full -dc dc1 repair_lab orders_by_id
```

Here, `-dc dc1` restricts participants to the specified DC; **it does not mean repairing across both `dc1` and `dc2`**. To genuinely compare data across DCs, the session's participant/range set must include replicas from all DCs being compared.

The syntax and valid combinations for `-dc` flags vary by version; never assume a flag can be repeated or combined arbitrarily with `-local` without checking help output for your deployed version.

### Performance and Reliability Trade-offs

| Aspect | Local DC Repair | Cross-DC Repair |
| --- | --- | --- |
| Replicas compared | Replicas within one selected DC | Replicas across multiple relevant DCs |
| WAN traffic | Generally avoids cross-DC streaming | Can generate WAN streaming |
| Network latency | Typically lower due to intra-DC links | Affected by inter-DC latency, bandwidth, and stability |
| Cross-DC divergence | May go **undetected** | Can be detected and fixed if ranges and participants cover both |
| Operational impact | Focused on resources in the repaired DC | Requires resource coordination across multiple DCs |
| Meaning after completion | Repaired the selected local scope | Repaired the selected cross-DC scope; does not automatically guarantee other scopes |

Because of these cost differences, schedules often need to **combine intra-DC and inter-DC repairs**, rather than choosing one and discarding the other. Cadence must reflect data churn, replica uptime, hint limits, tombstone grace, SLAs, and hardware capacity.

## 6. Defining Repair Scope: Avoiding "One Command Fixes the Cluster"

`nodetool` connects to **one node** in Cassandra and drives repair for that node/range scope. Completion on one node **does not mean** every partition across every node was scanned.

Common options:

| Option / Input | What to Understand | Warning |
| --- | --- | --- |
| `keyspace [table]` | Restricts data by keyspace and table | If only one table is named, other tables are not repaired |
| `-local` | Works only with replicas in the target node's DC | Does not detect drift existing solely between DCs |
| `-dc <dc>` | Restricts participants to specified DC(s) in supporting versions | Wrong DC selection can omit replicas needing sync |
| `-pr` | Repairs only the node's primary ranges as defined in that version | Must run across enough nodes/ranges for coverage; do not infer coverage blindly when combining DC options |
| `-st`/`-et` | Bounds start/end token range in supporting versions | Requires understanding the partitioner/token ring and how interval bounds are interpreted |
| `-full` | Runs full repair rather than relying solely on incremental state | Can incur heavy I/O and streaming |
| `-hosts` | Restricts participants by host where supported | Unsuitable for cluster-wide schedules if required replicas are accidentally excluded |

For the options above, parameter names and combination rules can differ between Cassandra 3.x, 4.x, and 5.x. Run:

```bash
nodetool help repair
```

on **the exact version in operation** before copying any command into maintenance procedures.

### Primary Ranges and Virtual Nodes

A node can own many token ranges, especially when the cluster uses **vnodes**. When `-pr` is enabled, repair processes only primary ranges per your version/configuration definition. The typical aim is avoiding redundant validation when building a cluster-wide repair schedule.

However:

- `-pr` run on **one node** is not a full-ring repair command.
- You must calculate the set of nodes/ranges required to cover the entire keyspace.
- When targeting intra-DC or cross-DC scope, verify how `-pr` interacts with participant-filtering options.
- If a token range is missed, data in that range may never have been compared.

A repair scheduler must track **completion by range and participants**, not merely "invoked the command on a few nodes."

## 7. Do Full Repair and Incremental Repair Change the Meaning of DC Scope?

These two concepts answer **two independent questions**:

- **Local vs. cross-DC:** *which replicas are allowed to participate*.
- **Full vs. incremental:** *which data/SSTables are examined in the repair session based on version state and repair mechanics*.

**Full repair** inspects data in the selected scope without relying on whether data was previously marked repaired by incremental repair. **Incremental repair** manages repaired/unrepaired or pending repair state per version mechanics and focuses on unrepaired data under those rules.

Do not naively interpret "incremental" as "only fix rows updated since last time." It has specific semantics around SSTable state, sessions, and Cassandra versions—not a simple application-timestamp scan.

| Choice | Question to Check | Common Reasoning Error |
| --- | --- | --- |
| Full + local | Do we need to check all data within this DC's scope? | Assuming other DCs were checked too |
| Incremental + local (when supported) | How are repaired/unrepaired state and DC scope managed? | Assuming results are definitely synced across DCs |
| Full + cross-DC | Are token ranges and all relevant DCs covered? | Assuming one run covers the entire cluster |
| Incremental + cross-DC | Are sessions, resources, and cross-DC repaired state compatible with the schedule? | Assuming restarting a command is safe and equivalent to full |

Repair mechanics, session state, and `nodetool repair` defaults have evolved across Cassandra's history. To keep examples applicable across versions, sample commands use `-full` explicitly; **never mix full and incremental arbitrarily in one operational schedule without understanding your repaired-SSTable management strategy**.

## 8. Why Can Repair Consume Heavy Bandwidth and Disk?

During repair, nodes read data/SSTables, compute validation metadata, resolve differences, and **stream** data across replicas. Running multiple sessions concurrently can contend for:

- **Disk I/O:** reading SSTables, writing streamed data, flushing, and compaction.
- **CPU/memory:** hashing, validation, and metadata structures.
- **Network:** especially inter-DC WAN links with throughput caps or egress costs.
- **Storage headroom:** new SSTables, temporary files, and associated compaction activity can increase space requirements.
- **Foreground latency:** Java applications continue sending `SELECT`, `INSERT`, and `UPDATE`; overly heavy repair can degrade p95/p99 latency.

For example, a token range contains roughly **120 GiB of data to compare**. Do not assume "120 GiB will traverse the WAN": validation may find few differences, or lots of data may stream if two sides diverged significantly. Actual traffic also depends on execution method, compression, and overlap.

### Signs You Should Throttle or Split the Schedule

| Signal | Possible Interpretation | Action |
| --- | --- | --- |
| WAN near saturation during cross-DC repair | Streaming/validation contending for link capacity | Lower concurrency and reschedule repair |
| Read/write p99 spikes during repair | I/O/CPU/network contention | Compare against baseline and throttle tasks |
| Disks nearly full | Insufficient headroom for streamed/compacted data | Prioritize capacity; do not force repair forward |
| One node repeatedly timing out | Replica overloaded, GC pauses, disk/network faults | Restore node health first |
| Repair session fails after hours | Participant interrupted or topology shifted | Inspect logs/session/range to re-run only the needed scope |

Repair helps data converge—**it does not replace replication** or eliminate root causes of timeouts. When an entire DC is down, cross-DC repair may be unable to finish; restore connectivity and availability before orchestrating repair.

## 9. Tombstones, TTL, and Why Repair Must Not Be Skipped Too Long

Cassandra represents deletions using **tombstones**. While any replica still holds stale data, tombstones on other replicas must remain long enough for the deletion to propagate safely through synchronization mechanisms.

Example:

```text
T0: dc1 receives DELETE O1 -> stores tombstone.
T1: dc2 is isolated -> still holds old row O1.
T2: dc1 compacts and tombstones become eligible for collection
    once safety conditions are met.
T3: dc2 returns, streams/repairs without deletion evidence remaining
    in some scenarios -> risk of stale data reappearing (zombie).
```

This is why `gc_grace_seconds`, TTL, repair schedules, and replica offline windows must be designed **together**. Depending on version/format and policy, tombstone exceptions/optimizations may exist; the core safety rule remains **never letting a replica miss deletes beyond the protection window without an appropriate recovery workflow**.

Special consequence in multi-DC clusters:

- Local repair in `dc1` protects tombstone propagation among R1/R2/R3.
- However, if `dc2` was isolated for a long time, **local repair in `dc1` never sends tombstones to `dc2`**.
- Separate local repair in `dc2` also cannot learn tombstones from `dc1` if all of `dc2` still holds the old row.
- Therefore, **cross-DC repair** and DC recovery strategies must be built into plans for prolonged isolation.

Never lower `gc_grace_seconds` just to make compaction purge SSTables faster; doing so increases the risk of deleted data resurrecting if repair is missed.

## 10. Distinguishing Repair from Read Repair, Hints, Compaction, and Backup

| Mechanism | Typical Scope Affected | What It Helps With | Does Not Replace |
| --- | --- | --- | --- |
| **Read repair** | Queried data and replicas participating in reads | Reconciles and may fix diffs on the read path | Repairing unread data |
| **Hinted handoff** | Mutations stored as hints for temporarily absent replicas within config limits | Replays some missed mutations | Full repair when hints expire or are lost |
| **Anti-entropy repair** | Selected token ranges, tables, and replicas | Compares/fixes discrepancies across replicas | Backups, transactions, or CL guarantees at all times |
| **Compaction** | SSTables on **a single replica** | Merges local data, handles versions/tombstones safely | Synchronizing replicas/DCs |
| **Backup/snapshot** | Saved copies of data for recovery | Restoring after data loss or severe incidents | Repair for comparing live replicas |

Do not assume `LOCAL_QUORUM` + read repair is always enough to replace operational repair. Rarely read partitions may never trigger read repair for months; that data still belongs in an anti-entropy repair schedule.

## 11. CQL Example: Two-DC Keyspace and Per-Partition Queries

This example describes a cluster with DCs named `dc1` and `dc2`, **each with at least three nodes**. If your lab has one DC or fewer nodes, adjust DC names and RFs to match actual topology before running:

```sql
CREATE KEYSPACE IF NOT EXISTS repair_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3,
    'dc2': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS repair_lab.orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id text,
    status text,
    updated_at timestamp
);
```

Queries using the exact partition key:

```sql
INSERT INTO repair_lab.orders_by_id
    (order_id, customer_id, status, updated_at)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'customer-42',
    'PENDING',
    '2026-11-20 09:00:00+0000'
);

UPDATE repair_lab.orders_by_id
SET status = 'PAID',
    updated_at = '2026-11-20 09:05:00+0000'
WHERE order_id = 11111111-1111-4111-8111-111111111111;

SELECT order_id, status, updated_at
FROM repair_lab.orders_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

In `cqlsh`, you can set:

```text
CONSISTENCY LOCAL_QUORUM;
```

When observing `dc1` and `dc2`, connect clients to coordinators in **the respective DC** and run queries at `LOCAL_QUORUM` to understand read scope. **Never simulate divergence by intentionally deleting SSTables/commit logs or disrupting production nodes.** All fault-injection experiments belong strictly in an isolated lab cluster.

### Why Doesn't a `SELECT` Statement Replace Repair?

`SELECT ... WHERE order_id = ?` touches only that single partition. It does not synchronize other unread orders. Even if a table uses `read_repair = 'BLOCKING'` on Cassandra 4.x, read repair may occur when a mismatch is encountered, yet its scope remains fundamentally different from anti-entropy repair across token ranges and selected participants.

## 12. Operational Playbook: Choosing Local vs. Cross-DC

Before running a repair wave, answer these questions and record the decisions:

### Step 1 — Verify Topology

```bash
nodetool status
nodetool describecluster
```

Verify actual DC names, node Up/Down/Normal states, per-keyspace replica counts, and inter-DC connectivity. `nodetool status` output does not replace inspecting keyspace replication schemas; cross-check both sources using proper admin tools.

If topology changes, rebuilds, decommissions, or severe node errors are underway, follow the corresponding operational runbook before scheduling large-scale repairs.

### Step 2 — Define Goal and Scope

| Question | Decision to Record |
| --- | --- |
| Fix drift within one DC or across DCs? | `-local`, selected DC participants, or cross-DC |
| Which keyspaces/tables hold critical data? | List of keyspaces/tables and RF |
| Which token ranges need coverage? | Node/range list, with or without `-pr` |
| Full or incremental per version? | Repair policy and repaired-SSTable state |
| Is the maintenance window sufficient? | WAN bandwidth, disk, CPU, p99 SLA, time |
| Any tombstones or long-offline replicas? | Check last repair timestamp and `gc_grace_seconds` |

### Step 3 — Measure Baseline

```bash
nodetool tablestats repair_lab.orders_by_id
nodetool compactionstats
nodetool netstats
```

Depending on version, these commands expose table sizes, related I/O, and active streaming. Simultaneously monitor network throughput, disk latency, CPU/GC, client p95/p99, and free disk space through system monitoring.

### Step 4 — Execute Within Controlled Scope

**Case A: only need to fix replicas inside `dc1`.** From a node in `dc1`, with illustrative full repair:

```bash
nodetool repair -full -local repair_lab orders_by_id
```

**Case B: need to compare between `dc1` and `dc2`.** From an eligible node in the cluster, after confirming WAN headroom and version help:

```bash
nodetool repair -full repair_lab orders_by_id
```

Both commands above represent **one step on one node**; schedule across enough nodes/ranges to achieve target coverage. Do not run both commands back-to-back mechanically—choice must follow your goal and data state.

### Step 5 — Monitor and Verify

Record per session: coordinating node, keyspace/table, token ranges, participants/DCs, full/incremental mode, start/end timestamps, success/error status, and streamed bytes if any.

Check:

- Did repair complete **the entire planned scope** or only part of it?
- Were there timeout/streaming errors, full disks, down nodes, or failed sessions?
- Did read/write p99 spike during peak hours?
- Are remaining nodes/ranges scheduled, or did only one node finish?
- Do tombstone/TTL datasets require a tighter repair cadence?

If a session fails, **do not mark the entire keyspace repaired**. Inspect logs, identify which ranges/participants did not complete, and apply version-appropriate retry/recovery mechanisms. Avoid launching concurrent overlapping repair sessions on the same data.

## 13. Java Driver: Local CL Does Not Mean Cross-DC Convergence

Java Driver 4.x applications commonly configure `local datacenter` on the session to route through nearby coordinators. That setting and **consistency level** govern the request path—they do not replace anti-entropy repair.

Example repository reading an order:

```java
import java.util.Optional;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class OrderRepository {
    private final CqlSession session;
    private final PreparedStatement selectStatus;

    public OrderRepository(CqlSession session) {
        this.session = session;
        this.selectStatus = session.prepare(
            "SELECT status FROM repair_lab.orders_by_id WHERE order_id = ?"
        );
    }

    public Optional<String> findStatus(UUID orderId) {
        BoundStatement statement = selectStatus.bind(orderId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

        Row row = session.execute(statement).one();
        return row == null || row.isNull("status")
            ? Optional.empty()
            : Optional.of(row.getString("status"));
    }
}
```

If application A in `dc1` and application B in `dc2` both use `LOCAL_QUORUM`, they can observe different states **while the DCs have not yet converged**. Reads and writes in each DC also depend on timing, available replicas, timestamps, and consistency strategies; you cannot fix cross-DC divergence simply by raising driver timeouts.

If business logic requires CAS to prevent conflicting updates, you can use **LWT** (`INSERT ... IF NOT EXISTS` or `UPDATE ... IF`) with an appropriate serial consistency, though LWT **does not replace anti-entropy repair schedules** for normal data and requires separate analysis of `SERIAL`/`LOCAL_SERIAL` scope.

## 14. Four Self-Assessment Scenarios

### Scenario 1 — Each DC Internally Consistent Yet Results Differ

`dc1` has three `PAID` replicas; `dc2` has three `PENDING` replicas. An administrator runs local full repair successfully across all nodes/ranges in each DC. Can you conclude both DCs match?

**Answer:** No. Local sessions never compare data between the two DCs. You need repair with participants and token ranges spanning both DCs if cross-DC convergence is the goal.

### Scenario 2 — Repair Schedule Run on Only One Node

A cluster uses vnodes and has a large keyspace. One node in `dc1` runs `nodetool repair -full -local repair_lab orders_by_id` and returns a success exit code. Can you report "the entire keyspace is repaired"?

**Answer:** No. Inspect which token intervals that node repaired and its participant scope; schedule across all critical ranges for full coverage. Adding `-pr` without a coverage plan does not solve this either.

### Scenario 3 — WAN Saturated

A cross-DC full repair runs during peak traffic. WAN links approach saturation and API p99 spikes. Should you run extra repairs in parallel to finish faster?

**Answer:** No. Protect SLAs and headroom—adjust schedule, concurrency, and per-session size after inspecting throughput and errors. Adding parallel streams onto an already saturated WAN link usually makes things worse.

### Scenario 4 — Long DC Outage with Heavy DELETEs

`dc2` was offline past the tombstone protection window while `dc1` continued deleting data. After `dc2` returns, only local repair is run inside `dc2`. What is the risk?

**Answer:** `dc2` may only compare replicas still holding old data inside its own DC without receiving tombstones from `dc1`. Once tombstones have been collected on the relevant copies, zombie-data risk arises. You need a DC recovery runbook and cross-DC reconciliation/safe data-recovery points rather than relying on local repair alone.

## 15. Operational Checklist and Key Takeaways

- [ ] Know **RF per DC**, datacenter names, and the coordinator's role in every read/write.
- [ ] Understand `LOCAL_QUORUM` governs only local-DC acknowledgment conditions, not cross-DC convergence.
- [ ] Distinguish **intra-DC repair** from **cross-DC repair** by participating replica sets.
- [ ] Explicitly define **keyspace, table, token range, node, and participants** for every repair wave.
- [ ] Never interpret one `nodetool repair` on one node as cluster-wide repair.
- [ ] Check `nodetool help repair` on your exact version before using `-local`, `-dc`, `-pr`, or full/incremental.
- [ ] Monitor **WAN bandwidth, disk I/O, CPU, p95/p99, and free disk** when running cross-DC repair.
- [ ] Schedule repairs to prevent prolonged drift, especially with DELETE/TTL workloads and previously offline replicas.
- [ ] Never treat read repair, hinted handoff, compaction, or backups as substitutes for anti-entropy repair.
- [ ] In Java applications, use prepared statements and intentional CLs; evaluate cross-DC consistency against business requirements.
- [ ] Record succeeded ranges/sessions and remediate failed scopes instead of declaring "repair done" by command count.

**Takeaway:** Repair **within a datacenter** synchronizes replicas inside the selected DC scope and generally avoids WAN load. Repair **across datacenters** is necessary to detect divergence invisible within each DC alone, but consumes network bandwidth and must be scheduled carefully. Either way, actual scope still depends on **token ranges, tables, participants, and repair mode**, so never equate "one command succeeded" with "the whole cluster is consistent."
