# Subrange Repair and Splitting Work into Smaller Pieces

## 1. The Problem: Repairing a Large Dataset Without Overloading the Cluster

In **Apache Cassandra**, the same partition is typically stored across multiple replicas. If a replica went offline, the network flapped, or hinted handoff failed to deliver all mutations, replicas can temporarily hold different versions of data. **Anti-entropy repair** compares and synchronizes data across replicas for the specified scopes.

When a keyspace holds terabytes of data, repairing too large a scope in a single pass can strain CPU, disk, network, temporary storage, and runtime. If the job fails near the end, operators also struggle to tell **which regions already finished**. Consequently, a common organizational pattern is **subrange repair**: splitting the target token space into **small, gap-free intervals**, then repairing, recording, and verifying each piece sequentially.

This lesson answers four questions:

1. What is **subrange repair**, and how does it differ from repairing the entire scope or only primary ranges?
2. How do you partition the **token ring** into subranges without leaving gaps or accidentally duplicating work?
3. How do you use `nodetool repair -st ... -et ...` and track succeeded/failed state?
4. Why is picking small slices **not enough by itself** to guarantee performance, correctness, and tombstone safety?

**Learning objectives:** be able to build a token-range repair plan, understand replica/DC scope, monitor progress, perform controlled retries, keep schedules safe relative to TTLs and `gc_grace_seconds`, and distinguish repair from quorum reads, compaction, and backups.

**Scope:** Cassandra using normal full replicas, typically with `Murmur3Partitioner`. `nodetool repair` commands and default modes depend on version; examples are lab exercises, not commands recommended verbatim for production.

## 2. Why Is Repair Needed Even When Applications Use QUORUM?

Suppose a keyspace has replication factor **RF = 3** in datacenter `dc1`; partition `(sensor-7, 2026-11-21)` resides on N1, N2, and N3.

~~~mermaid
sequenceDiagram
    participant App as Java client
    participant Coord as Coordinator
    participant N1 as Replica N1
    participant N2 as Replica N2
    participant N3 as Replica N3 (offline)
    App->>Coord: INSERT at LOCAL_QUORUM
    Coord->>N1: Mutation t2
    Coord->>N2: Mutation t2
    Coord-xN3: Mutation missed
    N1-->>Coord: ACK
    N2-->>Coord: ACK
    Coord-->>App: Success (2/3)
    Note over N3: Still holds stale data t1
    Note over N1,N3: Anti-entropy repair later reconciles token region
~~~

With RF = 3, a `LOCAL_QUORUM` write needs only **two** ACKs in the local DC. A `LOCAL_QUORUM` read also requires two responses; quorum sets within **the same DC and same replica set** must intersect. However:

- Replica N3 may still remain un-updated.
- Read repair can only address data actually touched on the read path, per your version's mechanics.
- Cold partitions, ranges holding tombstones, or another DC that missed mutations can still diverge.

**Anti-entropy repair** compares data across token ranges on participating replicas and streams needed differences. It does not fix only the partitions applications happen to query. Comparison may use Merkle trees and validation/streaming phases, though exact execution depends on version and repair options.

> Quorum ensures a read/write operation meets its required consistency threshold; repair gives **lagging replicas a chance to converge** across the repaired scope. Both mechanisms complement one another.

## 3. Token Ranges Are Units of Work Splitting, Not Business Value Ranges

### 3.1. From Partition Key to Token

A time-series table might use:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry_lab.readings_by_sensor_day (
  sensor_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  reading decimal,
  PRIMARY KEY ((sensor_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

`(sensor_id, event_day)` is a **composite partition key**. Cassandra hashes the entire partition key into a **token**, then uses the token, replication strategy, and topology to select replicas storing the partition. Rows belonging to that partition—even with different `event_time` values—all sit in the same **token range**.

**There is no direct ordering relationship** between tokens and dates, sensor names, or `event_time` order. Thus repairing token interval `(a, b]` **does not mean** fixing "days from a to b," and you cannot pick `a, b` from business time windows.

### 3.2. Visualizing Intervals Around the Ring

The token ring model typically uses **left-open, right-closed** intervals:

~~~text
           token A           token B           token C           token D
         ──────┬────────────────┬────────────────┬────────────────┬───── ...
                (A, B]           (B, C]           (C, D]

A partition with exact token B belongs to (A, B], not (B, C].
~~~

With `Murmur3Partitioner`, the token space uses 64-bit signed integers and **wraps around** at the domain boundary. Be especially careful with intervals wrapping across max/min tokens; never assume every interval satisfies `start < end` under plain numeric comparison.

When using virtual nodes (**vnodes**), a Cassandra node can own **multiple non-contiguous token segments**. Having 16 tokens on a node does not mean it holds 16 replicas of the same partition; full replica count is determined by RF and topology.

### 3.3. Subranges, Primary Ranges, and Replica Sets Differ

| Concept | Meaning | Key Consideration |
| --- | --- | --- |
| **Token range** | An interval of token positions on the ring | May contain huge numbers of partitions. |
| **Subrange repair** | Repairing a token scope explicitly specified by operator start/end | May be one slice of a larger region; full coverage must be managed explicitly. |
| **Primary range** | Token region where a node is primary owner per ring rules | `-pr` is a separate scope option, not a synonym for `-st/-et`. |
| **Replica set** | Nodes storing copies of partitions within a token segment | Can change across token boundaries or topology shifts. |
| **Repair coordinator** | Node initiating/coordinating the repair session | Not identical to coordinators of application queries. |

In particular, running a repair command on one node **does not automatically prove all token ranges across the cluster were repaired**. Actual scope depends on initiating node, token ownership, DC/host/primary-range flags, and Cassandra version. A complete plan requires defining **the target range set along with participating replicas**.

## 4. How Subrange Repair Operates

### 4.1. Logical Processing Phases

~~~mermaid
flowchart TD
    A["Identify token ranges needing repair"] --> B["Select a subrange (start, end]"]
    B --> C["Select repair coordinator / participant replicas"]
    C --> D["Compare data in subrange"]
    D --> E{"Any differing data?"}
    E -->|Yes| F["Sync missing / differing parts"]
    E -->|No| G["No differing data needs transfer"]
    F --> H["Verify repair session completed"]
    G --> H
    H --> I["Save outcome and move to next subrange"]
~~~

This is a conceptual flow, not an exact spec of internal RPCs. Validation normally scans relevant data on replicas, builds comparison digests, and may stream between nodes. **Having zero differences** still incurs validation overhead. If repair fails mid-way, you cannot blindly mark the entire subrange `DONE`.

### 4.2. Why Split into Smaller Pieces?

| Benefit | Practical Explanation |
| --- | --- |
| **Bounded scope per run** | Each unit of work can be monitored, stopped, or retried independently. |
| **Clean checkpointing** | Clear visibility into which subranges finished and which need retries. |
| **Resource contention control** | Easier to cap concurrent repairs and avoid starving reads/writes. |
| **Schedule optimization** | Spread subranges across maintenance windows, prioritizing tombstone-risk regions. |
| **Fault isolation** | Narrows investigation scope when timeouts, node drops, or stream failures occur. |

**Limitations:** finer slicing creates more sessions and scheduling, metadata, validation, and coordination overhead; if subranges are too tiny, fixed overhead can outweigh benefits. **Numerically narrow token ranges do not guarantee small data volume**: uneven partition distribution, row sizes, tombstones, and hot partitions all skew volume. A massive partition **cannot be split in half by slicing token ranges**, because the entire partition shares one token.

## 5. Planning Gap-Free Slices

### 5.1. Using Shared Boundaries

Suppose we only need to repair token segment `A` to `D` in ascending order and it **does not wrap around the ring end**. Pick interior split points `B` and `C`:

~~~text
Repair target:             (A, D]

Subrange 1:                (A, B]
Subrange 2:                (B, C]
Subrange 3:                (C, D]

Union of three subranges:  (A, D]
No gaps at B, C; boundary points are not double-counted.
~~~

In practice, interval conventions enforced by `nodetool` must be checked against your version/partitioner, with special care for ring boundaries. **Never blindly repair a numeric span from min to max assuming cluster-wide coverage** without verifying ownership scope and wrap-around semantics.

### 5.2. Two-Part Example on a Slice of Murmur3 Token Space

Pick two illustrative slices, **not representing the entire ring**:

| Job ID | Planned Token Interval | Completion Handling |
| --- | --- | --- |
| `repair-A` | `(-4611686018427387904, 0]` | Must complete and be logged separately. |
| `repair-B` | `(0, 4611686018427387903]` | Must complete and be logged separately. |

Combined, the two jobs span `(-4611686018427387904, 4611686018427387903]`—**not the full Murmur3 domain**. This is solely a safe example clarifying boundary alignment; real schedules must derive ranges from actual token map/ownership and coverage plans.

### 5.3. Data Volume Does Not Equal Token Width

A minimal plan should estimate:

- SSTable bytes/counts, partition counts, and tombstones in scope where observable.
- Participating replicas, rack/DC layout, transfer bandwidth, and streaming pressure.
- Overlap across subranges and other active repair jobs.
- Load windows, CPU/I/O headroom, and spare disk capacity.

Rather than slicing into 100 equal numeric intervals and assuming each takes equal time, **measure actual duration and data volume**, then adjust boundaries and parallelism for the next cycle. Query-driven partition keys, avoiding oversized partitions, and sensible compaction/TTL tuning all make repair runtimes more predictable.

## 6. Hands-On `nodetool repair -st/-et`

### 6.1. Inspect Environment First

On a node in lab/staging:

~~~bash
nodetool status
nodetool ring
nodetool help repair
~~~

`status` shows nodes/DCs/racks and health; `ring` shows token ownership; `help repair` **confirms exact syntax for the running version**. Never rely on a random online snippet to pass flags from a different release.

Example using the Section 3 keyspace/table, on a node suited to act as repair coordinator:

~~~bash
# Repair only the first token slice on the designated node.
nodetool repair -st -4611686018427387904 -et 0 telemetry_lab readings_by_sensor_day

# Once the first slice succeeds and is recorded,
# repair the second token slice in the example.
nodetool repair -st 0 -et 4611686018427387903 telemetry_lab readings_by_sensor_day
~~~

**Meaning:** `-st` (*start token*) and `-et` (*end token*) define the token scope to examine. Next come `keyspace` and `table`. The numbers above are illustrative boundaries for **two subranges**, not defaults to reuse blindly.

These commands **do not guarantee** either of the following without verification:

1. The initiating node actually participates in or covers every token range needing repair per topology.
2. The whole cluster, all DCs, and all tables were repaired—task scope depends on options, participant replicas, and the overall schedule.

In production, use approved runbooks, cap concurrency, pick the right coordinators, and verify **incremental/full repair** mode along with participating replicas/DCs. Never combine `-pr`, `-local`, `-dc`, `-full`, or other flags without checking how they interact in your deployed version.

### 6.2. Full Repair, Incremental Repair, and Scope

| Distinction | High-Level Meaning | Risk If Confused |
| --- | --- | --- |
| **Full repair** | Examines data in scope beyond just portions not yet marked repaired | Higher resource cost; requires matching schedule and understanding of repaired/unrepaired state. |
| **Incremental repair** | Uses SSTable repaired tracking/state per version mechanics | Cannot treat every small run as equivalent to full repair. |
| **`-pr` (primary ranges)** | Restricts repair to the node's primary ranges | Not equivalent to arbitrary subranges via `-st/-et`. |
| **DC/host limits** | Selects participating replica subset per topology requirements | Can omit replicas needing sync if only part of the scope is repaired. |

In some versions, incremental repair involves SSTable steps like **anti-compaction** and maintaining repaired state. Changing modes, aborting mid-way, or overlapping multiple runs demands care because it can spike I/O and complicate repair metadata. This lesson **does not assert a fixed default mode** for `nodetool repair`; verify that on your actual Cassandra release.

### 6.3. Post-Command Observation

~~~bash
nodetool netstats
nodetool compactionstats
nodetool tpstats
nodetool status
~~~

- **`netstats`**: inspect active streaming or data transfers where exposed by version.
- **`compactionstats`**: inspect related compaction/validation tasks and backlogs.
- **`tpstats`**: observe thread pools and pending tasks to spot execution pressure.
- **`status`**: confirm no participating node abruptly dropped or entered a transition state.

Depending on version, detailed repair outcomes also live in **node logs, task logs, and metrics/monitoring systems**. A finished command without full-scope confirmation **must never automatically be labeled "cluster repaired."**

## 7. Designing a Scheduler and Per-Subrange Checkpointing

Subrange repair delivers the most value when operated as **a stateful work queue**, not manual commands typed without saving results.

### 7.1. Minimal Checkpoint Record

~~~text
repair_run_id     : repair-2026-11-21-dc1-01
keyspace          : telemetry_lab
table             : readings_by_sensor_day
partitioner       : Murmur3Partitioner
topology_snapshot : version-of-token-map-at-planning-time
repair_mode       : confirmed-full-or-incremental-mode
scope             : participant DCs/nodes according to runbook

task_id    start_token             end_token             state
--------   ----------------------  --------------------  ---------
range-A    -4611686018427387904    0                     DONE
range-B    0                       4611686018427387903   PENDING

Per task: coordinator_node, started_at, finished_at, attempt_count,
          tool_exit_status, repair_session_id/log_reference, failure_reason.
~~~

The fields above represent an **orchestrator checkpoint model**, not a schema created by Cassandra itself. Marking `DONE` requires proof that the repair session **succeeded for the intended scope**; `RUNNING` or `FAILED` never counts as complete.

### 7.2. Recommended State Machine

~~~mermaid
flowchart TD
    P["PENDING"] --> R["RUNNING"]
    R -->|Repair completes and verified OK| D["DONE"]
    R -->|Timeout / failed / node down| F["FAILED"]
    F --> I["Investigate root cause"]
    I -->|Topology still valid, retry safe| P
    I -->|Topology/ownership changed| X["REPLAN all affected scopes"]
    D --> V["Verify repair run coverage"]
~~~

**Key rules:**

1. **Run with bounded concurrency.** Prefer serial execution in lab; in production raise parallelism only after measuring capacity and limiting sessions with overlapping participant replicas.
2. **Keep scope immutable within a run.** Every task must use the same token-map/topology snapshot and full/incremental/DC policy unless explicitly replanned.
3. **Retry under control.** Whenever unsure whether a session completed, inspect real logs/state before re-running; never mark DONE just because a command was launched.
4. **Never skip failed subranges.** Overall run status finishes only when every slice in coverage meets completion criteria.
5. **Handle topology changes.** Bootstrap, decommission, token move, or node replace can alter ownership/participant sets. When that happens, stop reasoning on the stale snapshot and replan per runbook.

### 7.3. Scheduler Pseudocode

~~~text
plan = load_validated_subranges()
assert coverage_has_no_gaps(plan)
assert topology_and_repair_scope_confirmed(plan)

for task in plan.in_order():
    if task.state == DONE:
        continue

    if topology_changed_since_plan():
        mark_run_needs_replan()
        stop

    mark(task, RUNNING)
    outcome = run_repair_on_approved_coordinator(
        keyspace, table, task.start_token, task.end_token,
        verified_mode_and_dc_scope
    )

    if outcome.completed_successfully_and_verified:
        save_logs_and_mark(task, DONE)
    else:
        save_logs_and_mark(task, FAILED)
        stop_or_retry_under_policy()

assert every_task_verified_done()
assert final_coverage_matches_intended_scope()
~~~

This pseudocode illustrates orchestration flow only; **it is not an executable script**. A production orchestrator must compute ring boundaries accurately, select responsible coordinators, verify outcomes, and handle interrupted sessions.

## 8. Tombstones and `gc_grace_seconds`: The Deadline Making Repair Crucial

When applications `DELETE` or TTLs expire, Cassandra retains **tombstones** to shadow stale data. If one replica misses a deletion and other replicas purge tombstones too soon, stale data can resurrect (*zombie data*) when the lagging replica returns.

~~~mermaid
flowchart LR
    A["N1/N2 receive DELETE t2"] --> B["Tombstone shadows old value t1"]
    C["N3 offline, still holds t1"] --> D["Delete not yet synced"]
    B --> E{"Repair completes while tombstone is valid?"}
    D --> E
    E -->|Yes| F["N3 gets chance to receive deletion"]
    E -->|No| G["Risk of t1 resurrecting once tombstone purges"]
~~~

A table's `gc_grace_seconds` governs how long tombstones remain protected before becoming eligible for cleanup under valid conditions. For example, `gc_grace_seconds = 864000` (10 days) **does not** mean Cassandra auto-repairs after 10 days, nor that every tombstone disappears right on day ten.

**A sliced plan must finish on time**, not merely start before grace expires. If a job has 200 subranges and 199 complete while the one slice holding an offline replica is skipped, that slice still carries tombstone risk.

Real policies need buffer time for retries, node faults, and maintenance, plus awareness of version/config nuances. If a node stayed offline too long, consider safe rebuild/replace workflows rather than letting a very stale node rejoin and hoping one normal repair fixes everything.

**Never lower `gc_grace_seconds` to compensate for an overly slow repair schedule.** Dropping bytes from SSTables via compaction or TTL does not remove the requirement to sync tombstones across replicas before purging markers risks zombies.

## 9. How Repair Differs from Compaction, Streaming, and Backups

| Mechanism | Purpose | Relation to Subrange Repair |
| --- | --- | --- |
| **Anti-entropy repair** | Compares and synchronizes data across replicas | Subrange repair restricts **the token scope** of this operation. |
| **Compaction** | Merges SSTables and drops eligible versions/tombstones on **one node** | Does not fix other replicas; can contend for I/O alongside repair. |
| **Bootstrap/replace streaming** | Transfers data for new nodes/topology changes | Does not replace ongoing replica verification and convergence. |
| **Hinted handoff** | Replays some mutations temporarily missed by a replica | Has time/size limits; does not cover all replica divergence. |
| **Read repair** | Fixes mismatches noticed on the read path per policy/version | Does not scan all token ranges like anti-entropy repair. |
| **Snapshot/backup** | Recovers point-in-time data after operator errors or major loss | Repair can propagate accidental deletes too; backups serve a different goal. |

Good practice avoids **stacking multiple heavy tasks** without coordination: repair, aggressive compaction, cluster-expansion streaming, and full backups all compete for CPU, disk, network, and temp space.

Subrange repair is not a fix for an oversized partition causing timeouts; splitting by token never splits rows sharing the same partition. Revisit partition keys/bucketing, data bounds, and read/write workloads instead.

## 10. CQL and Java: Verifying Data Without Confusing It with Repair

### 10.1. Testing CQL Operations on a Specific Partition

After creating `telemetry_lab.readings_by_sensor_day` in lab:

~~~sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO telemetry_lab.readings_by_sensor_day
    (sensor_id, event_day, event_time, event_id, reading)
VALUES
    ('sensor-7', '2026-11-21', '2026-11-21T03:00:00Z',
     123e4567-e89b-42d3-a456-426614174001, 22.50);

SELECT event_time, event_id, reading
FROM telemetry_lab.readings_by_sensor_day
WHERE sensor_id = 'sensor-7'
  AND event_day = '2026-11-21';
~~~

`CONSISTENCY` is a **cqlsh** command, not CQL syntax sent verbatim from Java. `LOCAL_QUORUM` with RF = 3 in the local DC requires two replica responses; it does not trigger repair across the full token interval.

CQL reads show **the logical result seen by a client**; they do not prove every full replica is identical. Combine application checks with repair session state, topology, and operational metrics.

### 10.2. Java Driver 4.x: Using the Right CL for Application Queries

Small Java example independent of the repair scheduler:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetSocketAddress;
import java.time.LocalDate;

public final class ReadAfterRepairExample {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement query = session.prepare(
                "SELECT event_time, event_id, reading " +
                "FROM telemetry_lab.readings_by_sensor_day " +
                "WHERE sensor_id = ? AND event_day = ?");

            BoundStatement read = query.bind(
                    "sensor-7", LocalDate.of(2026, 11, 21))
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            for (Row row : session.execute(read)) {
                System.out.println(row.getInstant("event_time")
                        + ": " + row.getBigDecimal("reading"));
            }
        }
    }
}
~~~

**Important distinction:** `withLocalDatacenter("dc1")` lets the driver target the local DC; `setConsistencyLevel(LOCAL_QUORUM)` sets the response threshold for **this read request**. Nothing in that `SELECT` replaces running repair across divergent token ranges.

To drive repair from an orchestrator, use **dedicated admin/automation tooling with isolated privileges** rather than granting every Java service permission to invoke `nodetool repair`. Triggering privileged ops commands from user-facing APIs introduces load and security hazards.

## 11. Incident Handling: If One Piece Fails, How Is the Whole Run Counted?

| Scenario | What NOT to Do | Proper Action |
| --- | --- | --- |
| Subrange A DONE, B FAILED | Mark the whole run complete | Keep A DONE, investigate B, retry B per policy, and verify. |
| A replica goes down mid-session | Ignore error, treat data as repaired | Inspect session outcome and participants; fix node and re-run affected region. |
| Token intervals shift due to added node | Keep running old plan blindly | Replan against new ownership and re-evaluate repaired/pending coverage. |
| Repair runs too slowly | Crank parallelism indefinitely | Measure I/O, network, tombstones, hot data; tune job count, timing, and subrange size. |
| A few tasks lack confirmation logs | Assume "probably finished" | Mark `UNKNOWN`/FAILED and verify logs before re-running. |
| Failure exceeded `gc_grace_seconds` | Run old repair as if risk-free | Follow tombstone-safety runbook; consider rebuild/replace if node is too stale. |
| Job ran in only one DC | Conclude all DCs are synced | Review DC/host scope and multi-DC coverage plan. |

### Minimal Investigation Procedure

1. **Identify the task:** keyspace, table, start/end token, coordinator, participants, repair mode, timestamp, and session logs.
2. **Confirm topology:** up/down nodes, token map, DC scope, and membership changes since planning.
3. **Measure load:** streaming, compaction, CPU/I/O, free disk space, and backlogs.
4. **Classify failure:** timeout, insufficient replicas, validation/streaming failure, operator abort, or topology drift.
5. **Decide action:** retry same scope, adjust concurrency, split large slices further, or replan per topology.
6. **Close the task:** move to `DONE` only when repair genuinely finished and evidence is saved; update the coverage map.

Re-running a task still incurs validation/streaming overhead even if data already converged; **controlled retry** never means infinite blind retries without diagnosing root causes.

## 12. Common Mistakes

| Claim | True or False? | Explanation |
| --- | --- | --- |
| "Using `LOCAL_QUORUM` eliminates the need for repair." | **False** | Replicas outside the ACK set or cold regions can still diverge. |
| "A subrange is an interval over `event_day`." | **False** | `-st/-et` bounds are tokens, not timestamps or clustering keys. |
| "Splitting a token range into 8 parts gives each exactly 1/8 of the data." | **False** | Partition distribution, sizes, and tombstones are uneven. |
| "Repairing a slice on one node always fixes every DC." | **False** | Must check participant replicas, node/DC scope, and version. |
| "`-pr` is equivalent to `-st/-et`." | **False** | Primary ranges and explicit subranges are two different scope filters. |
| "Task timed out with no final exception means DONE." | **False** | Require explicit completion evidence from sessions and admin tools. |
| "Repair fixes data deleted by an accidental `DELETE`." | **False** | Repair can propagate tombstones; logical mistakes require backups/other sources. |
| "Repair can ignore grace because tombstones stay forever." | **False** | Tombstones can be purged once eligible, and stale replicas risk zombies. |
| "Smaller subranges always save resources." | **False** | Too small inflates scheduling/validation overhead, and large partitions still cannot split. |
| "You can checkpoint per subrange and resume unfinished parts." | **True, conditionally** | Only when coverage/topology plan stays valid and completion state is verified. |

## 13. Exercises with Answers

**Exercise 1.** You want to repair token interval `(-100, 200]` in two parts, splitting at `50`. Write the two gap-free intervals.

**Answer:** `(-100, 50]` and `(50, 200]`. A token equal to `50` belongs to the first slice. This is a **non-wrapping** subrange example and does not prove the whole ring was repaired.

**Exercise 2.** RF = 3 in one DC. A `LOCAL_QUORUM` write receives ACKs from N1 and N2 while N3 is offline. Why is subrange repair still useful?

**Answer:** N3 may have missed the mutation. A successful quorum write only requires two replica ACKs; once N3 returns, repair synchronizes the partitions N3 missed within that range.

**Exercise 3.** A repair run has 50 subranges. 49 tasks are `DONE`, and one task is `FAILED` due to a streaming timeout. Should the whole table be marked repaired?

**Answer:** **No.** One region still lacks verified repair completion. Investigate, retry per policy, or replan; overall completion holds only once full coverage is verified.

**Exercise 4.** Two token intervals have equal numeric width, yet one holds a single 200 GB partition while the other holds many small partitions totaling 2 GB. Can you assume both take equal repair time?

**Answer:** **No.** Token width does not accurately represent bytes, SSTable count, tombstones, or transfer cost. An interval holding a massive partition remains a bottleneck even if you split tokens further.

**Exercise 5.** A replica missed a deletion and stayed offline past the grace period. Why can't you simply lower `gc_grace_seconds` to "help repair run faster"?

**Answer:** Lowering grace can let tombstones purge prematurely, allowing an old replica to reintroduce deleted records as zombies. Handle replica/repair safely with adequate buffer time.

**Exercise 6.** In a two-DC cluster, a `nodetool repair` task is configured to include only DC1 replicas. Can you declare DC2 fully synchronized?

**Answer:** **No.** Scope was restricted to DC1 participants; you must schedule/verify DC2 synchronization according to topology and actual requirements.

**Exercise 7.** Mid-way through 100 subranges, the cluster adds a new node. Is it safer to keep running all old intervals as-is or re-evaluate ownership?

**Answer:** **Re-evaluate ownership** and the token map, identify which intervals/replicas shifted, and replan per runbook. Never treat a pre-bootstrap plan as valid for the new topology.

## 14. Practical Checklist Before Reporting "Repair Completed"

~~~text
[ ] Verify actual keyspace, table(s), partitioner, and topology.
[ ] Inspect token map, target coverage, and ring wrap-around boundaries.
[ ] Split into gap-free subranges; record start/end tokens per task.
[ ] Confirm coordinator/participants, DC scope, and full/incremental mode.
[ ] Pick concurrency and maintenance windows suited to load headroom.
[ ] Monitor session/logs, validation, and streaming for every task.
[ ] Mark DONE only once completion outcomes are verified.
[ ] Retry/replan every FAILED/UNKNOWN task; skip no token intervals.
[ ] Confirm repair finishes inside tombstone safety margins and handle long-offline replicas.
[ ] Verify full coverage across all planned scopes/replicas and archive evidence.
~~~

**Takeaway:** *Subrange repair* does not invent a new consistency level; it **splits anti-entropy repair work across token intervals** to simplify tracking, load throttling, and retries. Proper repair is not just running lots of `nodetool` commands—it is **defining the data/replica scope needing sync, leaving no token range gaps, verifying each piece, and finishing before tombstones lose safety guarantees**. Achieve this by relying on token ownership, per-DC replication, metrics, and task states rather than counting commands executed.
