# Scheduling by Data Volume, Load, and `gc_grace`

> **Chapter:** Repair  
> **Scope:** Apache Cassandra — a distributed *wide-column* database. This lesson focuses on scheduling **anti-entropy repair** across replicas based on data volume, read/write load, tombstone protection windows, and post-incident completion capacity. Examples use CQL, `nodetool`, and a Java application context.

## 1. Why Must Repair Be Scheduled?

Cassandra distributes partitions by token and keeps multiple copies (*replicas*) based on replication factor (RF). A write acknowledged to a client at consistency level (CL) `LOCAL_QUORUM`, `QUORUM`, or `ONE` **has not necessarily reached every replica**. A replica may be temporarily offline, the network may have partitioned, or hint delivery may have exceeded its retention window.

**Repair** is the mechanism that compares and synchronizes data across replicas responsible for the same token range. It brings replicas that missed mutations back toward a consistent state. A repair pass typically consumes resources to build/compare verification structures (such as Merkle trees) and **stream** differing data when needed; it is not a regular `SELECT` statement.

Three goals must be met simultaneously:

1. **Data safety:** replicas must be reconciled before tombstones become eligible for reclamation, preventing deleted data from resurrecting.
2. **Completion feasibility:** the schedule must allow enough time given existing data volume, node count, token ranges, RF, and actual repair throughput.
3. **Cluster health:** repair must not compete for I/O, CPU, network, and compaction so aggressively that read/write APIs violate SLOs.

A schedule like "run `nodetool repair` on Sundays" without buffer time, scope checks, and completion criteria can fail to meet all three goals.

### Which Mechanisms Does Repair NOT Replace?

| Mechanism | Primary Purpose | Why doesn't it replace periodic repair? |
| --- | --- | --- |
| Consistency level (`ONE`, `LOCAL_QUORUM`, …) | Defines how many replicas must respond to a request | Replicas that do not participate or respond can still miss mutations |
| Hinted handoff | Forwards mutations to absent replicas within allowed conditions/time limits | Does not guarantee recovery in all prolonged-absence cases |
| Read repair | Resolves discrepancies noticed on the read path per version-supported mechanics | Occurs only on scopes actually read; cold data may never be accessed |
| Compaction | Merges SSTables and drops eligible versions/deletion markers | Does not reconcile across all replicas of a token range |
| Snapshot/backup | Restores data after corruption, accidental deletion, or full-system recovery | Backups do not check live discrepancies between serving replicas |

**Repair is a recurring distributed maintenance task**, not a one-off command after which the cluster stays permanently identical forever.

## 2. The Direct Relationship Between Repair and `gc_grace_seconds`

When deleting a column or row, Cassandra writes a **tombstone**. Expired TTLs also carry dead-data semantics and metadata that must be handled safely. A tombstone conveys that records with older timestamps must be treated as deleted.

Consider an RF=3 example with replicas A, B, and C:

```text
T0: A, B, C hold record event=v1.

T1: C is offline; client DELETE is acknowledged by A and B.
    A and B hold tombstones, C still holds v1.

T2: Delete protection period (gc grace) elapses; A/B compact
    and purge tombstones when local conditions are met.

T3: C returns before repair; C still holds v1.
    If no valid deletion marker remains to shadow v1, the data
    can be streamed or read back as live data ("zombie").
```

The table property `gc_grace_seconds` sets the protection window for tombstones before they become age-eligible for collection. **Passing grace does not mean tombstones are deleted immediately:** purging still depends on compaction and overlapping SSTables. However, operators **must never rely on tombstones lingering longer by chance** as an excuse to delay repair.

The scheduling objective should be stated as a verifiable condition:

> **Every relevant token range/replica must complete repair successfully often enough that a replica missing a delete does not exceed the `gc_grace_seconds` window before being synchronized.**

### Use the Time of *Successful Repair*, Not Job Start Time

A job that starts every week yet routinely fails halfway through **does not** mean data is repaired weekly. Track:

- **Most recent successful repair completion** per keyspace/table and token range.
- Maximum duration any scope has gone unreconciled.
- Token ranges, nodes, or datacenters left unprocessed due to failed/skipped jobs.
- Error recovery time, re-runs of failed ranges, and schedule gaps.

If one table has the lowest `gc_grace_seconds` in a workload, either the shared schedule must be safe for that table, or build **separate schedules by table group**.

### A Time-Budgeting Formula

Let:

- `G`: effective grace window to protect, in time units; for example, 10 days.
- `I`: planned interval between **starts** of full-scope repair cycles.
- `D`: longest expected duration to finish one cycle (including busy-load periods).
- `F`: budget for offline nodes, failed jobs, retries, or recovery actions.
- `M`: safety margin for measurement uncertainty and unexpected events.

Conservative planning condition:

```text
I + D + F + M < G
```

This is an **operational budgeting rule**, not an internal Cassandra algorithm. It intentionally accounts for cases where a range repairs early in one cycle and late in the next. When a schedule spans multiple workers, DCs, and token ranges, track **the actual gap between successes per scope**, rather than replacing everything with a single average.

Example with `G = 10 days`:

| Component | Illustrative Budget |
| --- | ---: |
| Launch interval `I` | 5 days |
| Repair completion `D` | 2 days |
| Failure/offline-replica handling `F` | 1 day |
| Safety buffer `M` | 1 day |
| **Total** | **9 days** |

This schedule leaves 1 day of headroom. If repair actually takes 4 days, the inequality no longer holds; you must **adjust the schedule, increase repair capacity, reduce data in scope, or tune grace under a validated plan**.

A node offline longer than `gc_grace_seconds` is particularly hazardous: **do not simply bring the old node back and hope a late repair job eliminates all zombie risk**. Evaluate node replacement/rebuild/restore procedures per your Cassandra version and the state of remaining trustworthy replicas.

## 3. Which Data Actually Must Be Repaired?

You cannot take a table's row count and divide evenly by node count to design a repair schedule.

Identify:

1. **Keyspace and replication strategy:** `NetworkTopologyStrategy` or another strategy; RF for **each datacenter**.
2. **Token scope:** vnodes, range ownership, replicas involved per range, and primary-range scope when scheduling.
3. **Per-node volume:** actual data inside SSTables; compression, tombstones, and related files make scanned bytes differ from logical data.
4. **Churn rate:** write throughput, updates/deletes, TTLs, and mutations missing on some replicas.
5. **Repair mode and prior history:** incremental vs. full; repaired/unrepaired SSTables in the running version.
6. **Ongoing topology shifts:** bootstrap, decommission, replace, move, or adding a DC can alter token ownership and reconciliation scope.

Illustrative keyspace:

```cql
CREATE KEYSPACE IF NOT EXISTS app_repair_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};
```

If the real cluster has **two datacenters**, design the repair strategy around per-DC RFs and actual repair scope; a pass restricted to DC1 **does not automatically verify** DC2 data if policy requires covering both.

### Logical Size, Per-Replica Size, and Scanned Data Differ

Suppose a keyspace holds 2 TiB of logical data replicated at RF=3. Roughly 6 TiB of replicated data is a **naive estimate** before accounting for compression, duplicate SSTables, compaction, tombstones, and snapshots.

Even so, that **does not mean a repair command transfers 6 TiB over the network**:

- Validation may read many SSTables locally across replicas.
- **Streaming** happens primarily when differences are found; it may be tiny if replicas match, or huge if a node missed many mutations.
- CPU/I/O cost of comparison and network cost of streaming are **two separate metrics**.

When sizing a schedule, base it on **measured durations and load of real repair runs**, not by multiplying `logical_data × RF` to guess streamed bytes.

## 4. Estimating Runtime from Volume and Real Throughput

A simple capacity model:

```text
T_estimated = D_to_validate / V_effective + T_overhead
```

Where:

- `D_to_validate`: bytes expected to be read/compared in the selected repair scope, gathered from telemetry and trial runs on the actual cluster.
- `V_effective`: effective validation throughput under **normal read/write load**, not peak standalone SSD benchmark speed.
- `T_overhead`: metadata exchange, session startup, SSTable handling, resource waits, anti-compaction, and streaming differences.

This is a **budgeting** model, not an exact formula for Cassandra repair duration. Ranges processed concurrently can contend for I/O; raising parallelism does not shrink duration linearly.

### Numeric Example for Building a Schedule

An illustrative cluster has **6 nodes in one datacenter**, RF=3. Telemetry from trials shows each node holds roughly **1.2 TiB** of SSTables for the keyspace to repair; during a low-load window, one primary-range repair pass on a single node typically takes **12–18 hours**.

Suppose we test running **at most 2 repair coordinators concurrently**, limiting overlapping primary ranges and controlling impact on query-serving replicas.

A rough estimate, splitting into three waves of two nodes and waiting for each wave to finish:

```text
3 waves × 18 hours = 54 hours ≈ 2.25 days
Adding overhead, retries, and low-load windows -> allocate 3 days to complete.
```

This **is not a claim** that each repair only touches data on the initiating node; repair also interacts with the other replicas storing the same token range. Measured timings can swing sharply if two coordinators in a wave trigger validation/streaming on overlapping replicas.

If `G = 10 days`, scheduled every 5 days yet each cycle occasionally takes 3 days, plus 1 day for failure handling and 1 day buffer:

```text
5 + 3 + 1 + 1 = 10 days
```

**Fails the conservative condition `< G`.** The schedule must be fixed—for example, shortening the launch interval to 4 days, safely reducing runtime via performance tuning, or raising grace if justified without introducing new risks. Do not fix it by launching repairs on all nodes simultaneously if the cluster is near CPU/disk saturation.

## 5. Read/Write Load and Concurrency Limits

Repair consumes resources both similarly to and differently from application queries:

| Resource | What Does Repair Use It For? | What Happens Under Severe Contention? |
| --- | --- | --- |
| CPU | Building/comparing verification trees, compression/decompression, SSTable & stream processing | Read/write p95/p99 spikes, threads queue up |
| Disk I/O | Reading SSTables, validation, anti-compaction/SSTable writes, and streamed data | Read latency, pending compactions, and flush times rise |
| Network | Exchanging validation metadata and streaming between replicas | Application bandwidth contention, timeouts |
| Disk space | SSTables rewritten or split during repair/compaction | Disk headroom shrinks; running out of space can fail jobs |
| Memory/GC | Buffers, metadata, Merkle trees, and stream state | GC pauses, OOM, or service slowdowns if misconfigured |

### Low-Load Windows Are Not "Idle Disk Hours"

A table with continuous writes, compaction backlogs, backups, and repair shares I/O. Pick windows with **real headroom**: CPU, disk IOPS/throughput, network, heap, and tail latency remain within budget.

Example:

- API requires read p99 under 120 ms.
- Without repair, p99 is around 75 ms.
- With two coordinated repairs running, p99 rises to 95 ms and pending compactions stay flat: acceptable.
- With four repairs running, p99 jumps to 220 ms and the I/O queue climbs continuously: fails SLO, even though repair jobs finish faster individually.

These numbers illustrate how to evaluate; every cluster needs its own SLOs and guardrails.

### Less Obvious Bottlenecks

- **Participating replicas** invited into repair may serve multiple sessions from different coordinators. Do not look only at the initiating node's CPU.
- **Overlapping SSTables, tombstones, and compaction backlogs** affect how much data must be scanned and anti-compacted.
- **Inter-datacenter links** may have different cost and bandwidth characteristics than intra-DC links.
- **Oversized partitions or hot partitions** can make validation steps drag disproportionately.
- **Continuous writes** keep generating new data; a completed repair does not mean mutations arriving after the validation snapshot/start point were reconciled.

Cap concurrent jobs, stream throughput, and compaction throughput using your version's configuration controls. Never copy throttle settings from another cluster without measuring.

## 6. Choosing Incremental vs. Full Repair

Cassandra offers different repair modes; mechanics and defaults vary by version. Two concepts to know:

| Mode | Core Idea | Trade-off |
| --- | --- | --- |
| **Incremental repair** | Targets data not yet marked repaired under the version's mechanism; may use anti-compaction to manage state | Reduces repeated work in some workloads, but requires careful state and failure management |
| **Full repair** | Reconciles all data in the selected scope, not just the unrepaired subset | Typically consumes more resources and time; useful when broad coverage verification/recovery is needed |

Never assume that **one successful incremental repair on one node = the entire keyspace on all replicas is consistent**. Verify token scope, participating nodes, DCs, repaired/unrepaired state, and prior full runs.

In some Cassandra versions, `nodetool repair` defaults to incremental while `-full` selects full repair. Depending on version and orchestrator, flags and interactions between full and incremental can differ; check the corresponding documentation and active operational policy.

### Can a Schedule Combine Both Repair Modes?

Yes, if operators understand their Cassandra version's workflow, recovery procedures, and monitoring. For example, a system might run regular incremental repairs by primary range while scheduling periodic full repairs or running full repair when suspect state needs verification. However, **there is no fixed ratio** like "7 incrementals then 1 mandatory full" applicable to every cluster.

The evaluation criterion remains **whether all required replicas and token ranges were reconciled within the safety window**, at acceptable resource cost and completion reliability.

## 7. Dividing Repair Scope by Node, Token Range, Table, and Datacenter

A sound schedule guarantees coverage and avoids launching concurrent sessions over the same scope.

### Primary Range

Depending on version, `-pr` / `--partitioner-range` requests repairing the **primary ranges** tied to the node running the command. When orchestrated cleanly across all required nodes, this minimizes redundant token-range validation.

Example on a lab cluster:

```bash
nodetool repair -pr app_repair_lab
```

Never run it once on a single node and declare the whole cluster repaired. You need a **plan covering all primary ranges** across nodes/DCs matching your replication strategy and version.

### Table Scope

When a keyspace has multiple tables with different grace windows, splitting schedules by data tier often makes more sense than running the whole keyspace at one cadence:

| Data Class | Example Characteristics | Scheduling Strategy |
| --- | --- | --- |
| High-DELETE tables, low `gc_grace_seconds` | Tombstones can become GC-eligible quickly | Repair successfully more often; prioritize based on zombie risk |
| Append-only event tables with uniform TTL | Data rarely updated | Still ensure coverage per grace and replica traits; tune around compaction/streaming windows |
| Very large, low-churn tables | Heavy scans, tiny diffs | Split ranges and windows; do not equate "low streaming" with "free validation" |
| Hot tables, high write throughput | New data arrives continuously | Pick concurrency/throttles per SLO and monitor progress closely |

### Datacenter

In multi-DC clusters, per-DC repair must align with replication policies and cross-DC consistency targets. **Local per-DC repair** may suffice for intra-DC replicas, but does not necessarily fix all cross-DC drift depending on your workflow and repair scope.

Never launch the exact same schedule across every node in every DC at the same time. Account for inter-DC bandwidth, replica load, and token scope; if using an orchestrator, a single authority must own the schedule and prevent overlaps.

## 8. Sample CQL and Observational Commands Before Scheduling

These examples are for **test/lab** clusters. They are not instructions to alter production repair policies without verifying version, topology, and impact.

### Step A — Identify Data with Tombstone Risk

Suppose keyspace `app_repair_lab` has a state-transition table:

```cql
CREATE TABLE IF NOT EXISTS app_repair_lab.orders_by_id (
    order_id uuid PRIMARY KEY,
    state text,
    updated_at timestamp
) WITH gc_grace_seconds = 864000;
```

`864000` seconds equals **10 days** as an example. If the workload deletes frequently, the repair schedule must ensure replicas have a chance to receive tombstones within this window, keeping your actual version's repair/GC behavior in mind.

A few mutations for discussion:

```cql
INSERT INTO app_repair_lab.orders_by_id (order_id, state, updated_at)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'PENDING',
    '2026-11-21T03:00:00Z'
);

UPDATE app_repair_lab.orders_by_id
SET state = 'DONE'
WHERE order_id = 11111111-1111-4111-8111-111111111111;

DELETE FROM app_repair_lab.orders_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

After `DELETE`, queries return no row logically on replicas that received the tombstone, yet the deletion marker must still persist long enough to reconcile other replicas.

### Step B — Observe Load and Node Health

On an accessible node:

```bash
nodetool status
nodetool tablestats app_repair_lab.orders_by_id
nodetool compactionstats
nodetool tpstats
nodetool netstats
```

Each command surfaces a different aspect: whether nodes are up or offline, per-table data/memory sizes and SSTable counts, compaction tasks, thread-pool queues, and streaming activity. Exact metric names and outputs vary by Cassandra version.

Supplement with monitoring telemetry: read/write p95/p99, I/O, network saturation, disk headroom, heap/GC, hinted handoff, abnormal node counts, and **outcomes per repair session/range**. You cannot judge repair safety solely from `nodetool status` showing every node `UN`.

### Step C — Controlled Trial Repair

Example operating on a primary-range scope for the lab keyspace:

```bash
nodetool repair -pr app_repair_lab
```

Example full repair for the lab keyspace when evaluating by version:

```bash
nodetool repair -full app_repair_lab
```

**Never run these two commands simultaneously**, never start full repair across all nodes at once, and never test in production just for quick observation. Define scope, load windows, resource limits, progress tracking, failed-part retries, and an owner to close out the run.

### Step D — Reading Results by Succeeded Scope

After every run, record:

- Start/end timestamps, coordinating node, keyspace/table list, and ranges.
- Repair mode, flags used, Cassandra version, RF, and participating DCs.
- Success/failure at both job level **and range/session level**.
- Duration, streamed volume, validation work, CPU/I/O/network, and p95/p99 impact.
- Missing ranges and their retry schedule.

A job finishing without terminal errors still requires verifying the expected ranges were processed per plan. Conversely, partial job failure does not mean every range in that job went unrepaired; keep progress records for controlled retries.

## 9. Designing a Daily and Load-Window Schedule

Suppose a cluster has 6 nodes in one DC, keyspace RF=3, minimum grace 10 days, and a goal of completing full coverage every 5 days. Testing shows repairing full scopes on two nodes concurrently stays within p99 and disk I/O thresholds.

An illustrative wave-based schedule:

| Wave | Work Scope | Condition to Advance to Next Wave |
| --- | --- | --- |
| 1 | Primary ranges coordinated by N1/N2 | Both scopes complete; backlog stays below threshold |
| 2 | Primary ranges coordinated by N3/N4 | Confirm no skipped ranges and healthy throughput |
| 3 | Primary ranges coordinated by N5/N6 | Complete coverage; record per-range success timestamps |
| Reserve | Retry failed sessions/ranges | Stay inside safe time budget before `gc_grace_seconds` |

This structure illustrates the logic for operators. In practice, repairing N1 and N2 may still touch shared replicas; use an orchestrator that understands token ownership and caps concurrency by **loaded replica**, not only by coordinator count.

### When to Throttle Concurrency or Pause

Slow down temporarily when:

- API p99, timeouts, or error rates breach defined SLOs.
- Pending compactions, disk queues, or GC pauses climb steadily.
- Streaming saturates the network on a node or DC.
- Free disk headroom drops below the safety threshold.
- A node goes down or topology shifts, invalidating current sessions.

However, **pausing must never turn into indefinitely skipping schedules**. Every pause must log the latest coverage date and remaining grace budget; if insufficient time remains, escalate remediation, reschedule workloads, and add capacity rather than simply disabling repair.

## 10. Monitoring: Mandatory Metrics to Confirm Schedule Health

| Category | Metrics to Have | Operational Question |
| --- | --- | --- |
| **Coverage** | Last successful repair timestamp per table/range/DC | Is any range approaching or past grace? |
| **Runtime** | Median/p95 time per range, total cycle duration | Can the schedule finish within budget as data grows? |
| **Incidents** | Failed/cancelled sessions, retry backlog, offline nodes | Are scopes repeatedly skipped week after week? |
| **Network** | Bytes streamed, stream throughput, errors | Have replicas drifted heavily? Is bandwidth bottlenecked? |
| **Storage** | Disk used, free space, SSTable count, compaction backlog | Are validation/anti-compaction contending excessively? |
| **API** | Read/write p95/p99, timeout rate, throughput | Is repair degrading user-facing traffic? |
| **Tombstones/TTL** | Tombstones scanned, low-grace tables, delete rate | Does any table need a tighter schedule due to purge risk? |
| **Topology** | RF/DC, token ownership, node/bootstrap/decommission events | Does the old plan still cover the right replicas? |

### Three Essential Alerts

1. **Grace budget:** a range/table has little time left before exceeding its safety window, measured from **last success**, not job start.
2. **Repair duration drift:** runtimes are climbing across cycles, forecasting that upcoming cycles will miss their deadline.
3. **Resource degradation:** repair is driving excessive latency or disk/network pressure, threatening both safety and availability.

A dashboard saying "repair runs once a day" is insufficient. It must show **what has been repaired, what remains, where failures occurred, and how much safety margin is left**.

## 11. When Data Volume Grows Faster Than Repair Speed

Example:

```text
Month 1: 0.8 TiB per node, repair cycle 24 hours.
Month 3: 1.4 TiB/node, repair cycle 44 hours.
Month 6: 2.5 TiB/node, repair cycle 86 hours.
```

If you keep a 48-hour low-load window and unchanged grace, the schedule gradually **becomes impossible to finish**.

Remediation options to weigh by root cause:

- **Scale capacity:** add nodes, upgrade storage, or increase CPU/network; after topology changes, refresh ownership and re-measure.
- **Shrink data per repair scope:** split keyspaces/tables along access patterns, design controlled TTLs and retention; never fragment into tiny partitions mechanically.
- **Optimize schedule:** split ranges, tune concurrency, pick quieter windows; optimization must not overload shared replicas.
- **Reduce dead-data overhead:** tune compaction/TTL where safe and appropriate; never force tombstone GC just to speed up repair.
- **Tier tables:** give critical low-grace tables priority schedules while ensuring low-churn tables still maintain coverage.
- **Review grace:** if operationally justified and supported by version, increasing `gc_grace_seconds` for tables needing more repair time widens the safety window, though tombstones persist longer and add read/storage overhead. Never lower grace automatically to "save disk."

**Higher RF** improves availability under node loss yet increases the number of replicas to maintain; never treat raising RF as an automatic fix for scheduling or gc grace.

## 12. Distinguishing Operational Incidents from Scheduling Bugs

### Scenario A — Repair Finishes Later Than Grace

**Signs:** numerous scopes unrepaired for longer than grace; a replica experienced an outage.

**Risk:** tombstones may have purged on healthy replicas before the old replica received the delete. Stale data can resurrect.

**Action:** investigate affected scopes and data; inspect tombstone/compaction history, backups, and repair logs. When a node's data is too stale, evaluate rebuild/replace from trustworthy sources rather than running a late repair and assuming safety.

### Scenario B — Incremental Repair Runs Frequently Yet Data Still Diverges

**Signs:** dashboard shows many succeeded jobs, yet certain ranges/DCs lack coverage or repaired/unrepaired state looks anomalous.

**Direction:** verify exact token scopes, nodes/DCs, job types, versions, and full/incremental schedules. Run verification per standard runbook; never equate one session's success with cluster-wide health.

### Scenario C — Every Repair Run Causes Severe p99 Spikes

**Signs:** CPU/disk already near saturation prior to repair; during repair, compaction backlogs and timeouts climb.

**Action:** lower concurrency/throttles, shift maintenance windows, and address I/O and capacity bottlenecks while respecting coverage deadlines. Raising parallelism to "finish faster" often slows down both repair and live traffic.

### Scenario D — A Node Is Offline for Days

**Signs:** node missed mutations, hints cover only a limited window, repair cannot complete.

**Action:** compare offline duration against the lowest grace period of data the node owns. If beyond the safety window, follow node replace/rebuild/restore runbooks; never blindly restart the node and trust stale local values.

### Scenario E — Just Changed Replication Factor or Added a DC

**Signs:** ownership and replica counts shifted; old primary-range schedules no longer match.

**Action:** finish topology/streaming steps per procedure, update the schedule, and re-verify new coverage by DC and token. Repair must still be scheduled against the current replica layout.

## 13. Connection to Java Applications and Consistency Level

In a Java application, a write request can complete at a CL before every replica receives the mutation. Example using Java Driver 4.x:

```java
import java.util.UUID;
import java.time.Instant;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class OrderRepository {
    private final CqlSession session;
    private final PreparedStatement insert;

    public OrderRepository(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO app_repair_lab.orders_by_id " +
            "(order_id, state, updated_at) VALUES (?, ?, ?)"
        );
    }

    public void save(UUID orderId, String state, Instant updatedAt) {
        BoundStatement statement = insert.bind(orderId, state, updatedAt)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
        session.execute(statement);
    }
}
```

`LOCAL_QUORUM` is a consistency guarantee **for that request**, not a promise that all replicas stay permanently synced. Repair scheduling is a cluster operations responsibility, not something executed on every repository call.

Applications still need to:

- Design partition keys for query patterns, avoiding oversized partitions and hotspots.
- Use controlled retries and idempotency on disconnects; a timeout does not prove no replica persisted the write.
- Monitor latency and error rates while repair runs so teams can react if SLOs degrade.
- Align TTL, DELETE, backup, and retention policies with the repair schedule.

Raising the consistency level in Java **does not replace** full-replica repair. Conversely, well-scheduled repair **does not turn two CQL statements into an atomic transaction**; if business logic requires compare-and-set, evaluate LWTs for the appropriate access pattern.

## 14. Reusable Scheduling Runbook Template

Before every cycle, operators should document:

| Item | Must Specify |
| --- | --- |
| Scope | Keyspaces/tables, datacenters, token ranges, node list |
| Repair mode | Full/incremental and version-appropriate tool flags |
| Grace | Lowest `gc_grace_seconds`, high-risk TTL/delete tables |
| Deadline | Cutoff time before exceeding the safety window |
| Capacity | SSTable size, recent repair duration, streaming and disk headroom |
| Concurrency | Concurrent coordinators/ranges, per-replica caps, throttles |
| SLO guardrails | p99 thresholds, timeouts, disk queues, GC, network, compaction |
| Retry | Owner for failed ranges, retry window, offline-node workflow |
| Audit | Store per-range/DC success results and report gaps |

### Short Procedure

1. **Inventory:** confirm RF, token ranges, tables, grace settings, data volume, and node health.
2. **Budget:** compute deadlines from last successful repair and the lowest grace threshold.
3. **Capacity test:** estimate runtime from recent runs under representative load; reserve margin for streaming and failover.
4. **Schedule:** batch into low-overlap scopes, pick high-headroom windows, and cap replica impact.
5. **Execute:** track completed scopes rather than just terminal command duration.
6. **Recover:** retry failed scopes and handle offline nodes before grace expires.
7. **Review:** compare runtime, load, and coverage after each cycle; update the schedule as data grows or topology changes.

## 15. Common Misconceptions

**"`nodetool repair` ran with no errors, so the whole cluster is safe."** Not necessarily. Check command scope and which token ranges/DCs/tables actually completed.

**"Running repair every 10 days is enough for a table with 10-day grace."** Leaves zero room for runtime, outages, retries, or schedule drift; usually unsafe.

**"Data rarely changes, so repair isn't needed."** Replicas can still miss rare mutations, especially deletes; low churn does not mean replicas are identical.

**"Using `LOCAL_QUORUM` ensures every replica receives DELETE."** False at RF=3: quorum acknowledgment does not require the third replica to be synced.

**"Increasing concurrency always shortens repair time."** Only until hitting I/O, network, CPU, compaction, or memory limits; beyond that, both repair and live traffic slow down.

**"With many nodes, just run `-pr` on one node."** False. One node's primary ranges do not represent all tokens in the cluster.

**"Compaction deletes tombstones after grace, so repair timing doesn't matter."** False. If an old replica missed the tombstone, premature purging causes zombie data.

**"With good backups, repair isn't needed."** Backups and repair solve different problems: restoring from archives vs. reconciling live serving replicas.

**"Measuring streamed bytes alone tells whether repair is fast or slow."** Inaccurate. Validation may still read huge SSTable volumes even when differing streamed bytes are near zero.

## 16. Practice Questions

1. A table has 7-day grace; cycles launch every 5 days, each run takes 2 days, and retries need 1 day. Why is this schedule insufficiently safe?
2. In an RF=3 cluster, a `LOCAL_QUORUM` write succeeds while one replica is offline. What still needs repair?
3. Explain the difference between *repair job started*, *session completed*, and *all required token ranges repaired successfully*.
4. Two different repair coordinators both pull the same replica into validation. Why is counting concurrency solely by coordinator misleading?
5. SSTable size is large yet streamed bytes are tiny. Why can repair still take a long time?
6. Table A has `gc_grace_seconds=864000` and table B has `gc_grace_seconds=259200`. What is concerning about a weekly repair schedule for the whole keyspace?
7. When a node goes offline longer than grace and returns, why can't one late `nodetool repair` be treated as sufficient to eliminate all risks?
8. Compare the purposes of `compaction`, `repair`, and `read repair`.
9. Before raising repair concurrency from 2 to 4, which metrics would you measure?
10. When adding a new datacenter or changing RF, which parts of the repair schedule must be revisited?

## 17. Quick Decision Table

| If the primary issue is… | What to do first |
| --- | --- |
| **Grace nearly expired, repair incomplete** | Identify unfinished ranges, prioritize safe remediation and node recovery; avoid missing deadlines |
| **Data growing, repair duration lengthening** | Measure scanned/streamed bytes, compaction, and per-range runtime; add capacity or split schedule properly |
| **Repair slowing API traffic excessively** | Lower concurrency/throttles, pick high-headroom windows, track deadlines |
| **Node disconnected for a long time** | Evaluate data age and `gc_grace_seconds` before reintroducing the node |
| **Multiple tables with different grace values** | Schedule by table/risk group; use the lowest grace threshold if bundled together |
| **Running full/incremental with unclear coverage** | Log per-range outcomes, cross-check topology and version policies |

**Takeaway:** Repair is a maintenance schedule that must **complete across the right replicas and token scopes**, not merely a line in cron. Measure real volume and runtime, cap load to protect SLOs, and ensure **the gap between successful repairs plus recovery/buffer time remains shorter than the applicable `gc_grace_seconds` window**. Only a verifiable, failure-resilient schedule keeps Cassandra replicas converged without pushing the cluster into resource contention.
