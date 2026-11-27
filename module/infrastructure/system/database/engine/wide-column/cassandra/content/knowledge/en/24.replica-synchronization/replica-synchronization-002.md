# Hinted Handoff and Hint Storage/Replay Time Limits

## Lesson Objectives

Apache Cassandra replicates a partition across multiple **replicas** to stay available when nodes or network links fail. When a replica temporarily misses mutations, how does it catch up once it comes back online? An important supporting mechanism is **hinted handoff**: nodes handling requests can temporarily store mutations destined for the absent replica as **hints**, then replay them when that replica becomes ready.

The key point to understand: **a hint is not a fourth copy, not an infinite durable queue, and does not replace anti-entropy repair**. Cassandra enforces limits on the **hint creation/storage window for a down node**, hint data volume, replay rate, and conditions under which the target node can receive them. When a node is absent for too long or the system suffers multiple concurrent failures, replicas may remain out of sync even when hinted handoff is enabled.

This lesson belongs to the **Replica Synchronization** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. It connects hints to replication factor (RF), consistency level (CL), the read/write path, CQL, tombstones, TTL, repair, compaction, troubleshooting, and Java Driver 4.x code.

After this lesson, you will be able to:

1. Explain **when a hint is created**, where it is stored, which replica it is replayed to, and when a hint is not created.
2. Distinguish the **hint creation window** from **replay duration**, **data TTL**, `gc_grace_seconds`, and the repair schedule.
3. Estimate hint load from mutation rate, replica downtime, mutation size, and overhead.
4. Evaluate the impact of `ONE`, `LOCAL_QUORUM`, and especially **write `ANY`** on request success and subsequent data readability.
5. Read relevant metrics and logs, design controlled CQL/Java experiments, and avoid guessing from a single `SELECT`.
6. Build runbooks for short node outages, outages exceeding the hint window, replay backlogs, deletions, and topology changes.

## 1. Context: A Replica Misses a Mutation

Suppose a datacenter has nodes A, B, and C. A keyspace uses `NetworkTopologyStrategy` with **RF = 3**; a partition of the `orders_by_id` table resides on these three replicas.

```text
              Java Client
                  |
                  v
             Coordinator
                  |
        +---------+---------+
        |         |         |
        v         v         v
     Replica A Replica B Replica C
        UP        UP        DOWN
        |         |          X
        +-- ACK --+          |
                  |          |
           Client can        |
           receive success   |
           if CL is met      |
                             |
                  Hint stored on the
                  coordinating node
                  (if eligible)
```

If a client writes `status = PAID` with `LOCAL_QUORUM`, replicas A and B can acknowledge and satisfy local quorum in an RF=3 setup. C has not received the mutation. Under appropriate conditions, the coordinator stores a **hint for C** and delivers it when C returns.

After the write completes, the replicas may temporarily be in this state:

| Replica | Status | Data Version |
| --- | --- | --- |
| A | Received mutation | `PAID` |
| B | Received mutation | `PAID` |
| C | Absent during write | `PENDING` |

**That is replica divergence:** the same partition/cell across different replicas may not yet share the same state. This differs from the case where the application writes to `orders_by_id` and forgets to update `orders_by_status_day`: the latter is **divergence across business projections**, not a replica missing a mutation sent to that table.

### 1.1. Concepts to Distinguish

| Term | Role |
| --- | --- |
| **Replication factor (RF)** | Intended number of copies of data in the configured topology |
| **Consistency level (CL)** | Number or set of replicas that must satisfy acknowledgment conditions for an operation to report success |
| **Coordinator** | Node that receives the request, identifies replicas, and coordinates the operation |
| **Hint** | Stored mutation record to be delivered later to a replica that was unable to receive the write |
| **Hinted handoff** | Mechanism for storing and replaying eligible hints |
| **Hint window** | Time window limiting **continued hint creation** for a replica considered down |
| **Read repair** | Comparing/repairing relevant data when a read detects discrepancies, depending on version/configuration |
| **Anti-entropy repair** | Process of comparing and synchronizing data across replicas over token ranges |
| **Streaming** | Transferring data during appropriate topology/repair/rebuild operations |

No single mechanism above promises that **all replicas are always identical at every moment**.

## 2. Lifecycle of a Hint

A conceptual lifecycle includes these steps:

1. The coordinator receives a mutation and identifies the replicas owning the partition.
2. The system detects that a replica is temporarily **unavailable for writes** via failure detection/coordination mechanisms.
3. If hinted handoff is enabled and the replica falls within allowed scope, the coordinator may **record a hint** for that replica.
4. The hint is stored in the creating node's **local hint store**, typically flushed to disk files per Cassandra's mechanism; this does not mean the target replica has received it yet.
5. When the target replica returns and can accept writes, the hint delivery service replays stored hints with rate/resource throttling.
6. Once successfully processed per the delivery mechanism, the associated hint record/file can be purged.
7. If mutation gaps remain, **repair** or an appropriate recovery procedure is needed.

```text
Create mutation
    |
    v
Did target replica receive it?
    | Yes                        | No
    v                            v
Normal write             Is hinted handoff enabled?
                                  | No -> no hint
                                  | Yes
                                  v
                          Within allowed window?
                                  | No -> stop creating hints
                                  | Yes
                                  v
                           Store hint on hint-holding node
                                  |
                         Target replica returned?
                                  | Not yet -> wait / evaluate limits
                                  | Yes
                                  v
                          Throttled replay
                                  |
                             Processed successfully?
                                  | No -> error/backlog,
                                  |       needs appropriate intervention
                                  | Yes
                                  v
                          Monitor convergence, purge hint
```

**A hint is not data already present on the target replica.** A hint file existing on the coordinator only indicates saved replay work; data on the target may remain stale until delivery finishes.

### 2.1. Hints Are Bound to the Target Replica, Not Read APIs

A hint typically carries the mutation and routing info to the **target host** that missed the write. It is not a queryable document and cannot be read via `SELECT` like a row in a business table.

When multiple coordinators handle writes for the same down replica, **hints can be spread across many hint-creating nodes**, rather than residing on a single node. Therefore, monitoring hint volume requires checking **per-node** and cluster-wide metrics.

### 2.2. When the Replica Returns

The system must detect that the target is ready to receive and dispatch hints according to the version's delivery mechanism. Replay throughput may be lower than the rate at which mutations accumulated, especially if the backlog is large or the newly recovered node is serving normal traffic.

A node showing `UN`/"up" in status tools **does not prove the hint backlog has finished replaying**. You must observe pending hints, delivery rate, delivery errors, and verify data afterward.

### 2.3. When Hints Are Not Created

Never assume every write targeting an absent replica definitely creates a hint. Cases to check:

- Hinted handoff is disabled globally or not enabled for the relevant replica type/DC per version/configuration.
- The replica has been considered down **longer than the hint creation window**.
- The coordinator lacks sufficient resources/disk space or encounters an error storing the hint.
- The mutation/operation type is ineligible for hints according to the implementation.
- A failed request state does not guarantee the coordinator created a hint, especially if failure occurred before enough information was available to store it.
- Topology/host ID changes mean the old hint delivery path no longer maps to the same target.

Thus, **a write timeout status is insufficient to conclude "a hint exists" or "no hint exists."** You must inspect logs/metrics and verify via appropriate readback protocols.

## 3. Understanding Time Limits Correctly: Hint Window Is Not Row TTL

This is the most common source of confusion on this topic.

The **hint window** limits how long Cassandra continues creating/storing **new hints** for a replica detected as down. The parameter is commonly named `max_hint_window` or `max_hint_window_in_ms` depending on version/configuration. Once a node is down past the allowed window, coordinators **stop creating new hints** for that replica to avoid unbounded backlog growth.

**Do not interpret** this as a guarantee that all hints will be replayed before that time, or that after that exact duration every hint file will definitely be deleted. Retention and delivery behavior for **previously created hints** also depend on version, target node status, resources, and hint cleanup/expiration mechanisms; verify actual behavior rather than treating the configured window as a delivery deadline.

### 3.1. Three-Hour Window Example

Suppose in the lab:

```text
Hint window = 3 hours (assumed configuration)

00:00  Replica C is marked DOWN
00:15  Mutation M1 -> eligible for hint creation for C
01:30  Mutation M2 -> eligible for hint creation for C
02:59  Mutation M3 -> still eligible for hint creation for C
03:10  Mutation M4 -> C still DOWN, exceeded hint window;
                     do not assume a new hint exists for M4
05:00  C returns; stored hints may be replayed per
       conditions/version, but M4 may require repair
```

The actual starting mark is measured from when Cassandra **detects/records the replica as down** per its version mechanism, which may not coincide exactly with the OS disconnect second. Therefore, timestamps like 00:00–03:00 are a planning model.

**Operational conclusion:** a node down for **five hours** with a **three-hour** hint window must be treated as a scenario where **that replica may have lost a portion of mutations**, even if all previously stored hints replay completely. You must evaluate repair, not merely wait for the hint backlog to drain.

### 3.2. Independent Time Intervals

| Time Interval | What Does It Control? | Does It Replace the Others? |
| --- | --- | --- |
| **Hint window** | Whether to keep creating hints for a down replica | No |
| **Actual time to replay backlog** | How long delivery takes after the target returns | Not equal to the hint window by default |
| **Cell Retention/TTL** | How long business data stays live | No; TTL follows data semantics |
| **`gc_grace_seconds` and tombstone purge safety** | Deletion protection window, together with repair/compaction and replica state | No; not a hint delivery timer |
| **Anti-entropy repair schedule** | Synchronization coverage of token ranges over time | No; requires separate planning |

For instance, if telemetry data only lives **four hours**, a hint stored while a replica is down might only be delivered after the data has already logically expired. Do not expect hint replay to **extend data lifetime** to compensate for node downtime; replay must respect actual timestamps, TTLs, and mutation semantics.

### 3.3. Why Not Increase the Hint Window Indefinitely?

A long-absent node can still correspond to thousands of mutations per second. Storing hints indefinitely causes:

- Huge backlogs consuming disk space on other coordinators.
- Hint file write I/O competing with commit logs, SSTables, and compaction.
- CPU/network spikes when the target node returns and receives millions of replayed mutations.
- Risk of running out of disk on **healthy** nodes, turning a single-node outage into a cascading failure.
- Unpredictable convergence times, especially if replay throughput is lower than incoming write rates.

Limiting the hint window is a **resource and fast-recovery scope control**, not an arbitrary cap you can raise without trade-offs.

## 4. Consistency Levels and the Special Case of Write ANY

Hinted handoff interacts with the write path, but it does not give all consistency levels the same semantics.

### 4.1. RF=3, ONE, and LOCAL_QUORUM

In a DC with RF=3:

| Write CL | High-Level Acknowledgment Condition | When C Is Down |
| --- | --- | --- |
| `ONE` | One replica acknowledges | A or B can suffice if healthy |
| `LOCAL_QUORUM` | Local quorum; with RF=3, typically 2 | A+B can suffice |
| `ALL` | Requires all required replicas | Write may fail to meet CL when C is down |
| `ANY` | Special write level that can accept a hint in place of a replica ACK when conditions allow | Can report success even if no data-owning replica recorded the write |

**Do not confuse:** a successful `ONE` write does not mean the coordinator only sent the mutation to one replica. It may send to all relevant replicas, while the client waits only for `ONE` acknowledgment.

With `LOCAL_QUORUM`, A and B can ACK successfully; C may receive the mutation later or be assisted via hinted handoff when eligible. This does not guarantee C is synchronized the instant the client sees success.

### 4.2. Write ANY Can Succeed via a Hint

`ANY` is a **write-only consistency level**: if no data replica receives the mutation, yet the coordinator can store an eligible hint per Cassandra's mechanism, the write can still be acknowledged. This increases write availability during certain outages, with an important consequence:

```text
Client writes CL=ANY
       |
No data replica receives the mutation at that moment
       |
Coordinator stores an accepted hint
       |
Client may receive SUCCESS
       |
Immediately afterward, SELECT from the table at a normal read CL
may NOT yet see the row because the hint has not reached the target replica
```

There is no corresponding **read CL=ANY** to read a row directly from a hint. A hint is not a queryable data row. This is especially dangerous if an API promises immediate read-after-write visibility.

**The "may" condition matters:** if the coordinator cannot store a hint, or the node/configuration does not meet the requirements, an `ANY` write can still fail. Do not advertise `ANY` as unconditional write availability when the cluster is down.

### 4.3. When All Replicas Are Unresponsive

When all replicas for a partition are unavailable:

- `ONE` or `LOCAL_QUORUM` cannot gather the required replica ACKs.
- `ANY` may have a success path via hints under specific conditions.
- A successful `ANY` write **does not guarantee** that an immediate read will find the row.
- If the hint is lost or never delivered afterward, data durability may fail system requirements without an external recovery source.

For critical business data, choose CL based on SLAs, topology, recovery procedures, durability, and stale-read tolerance—not simply because "ANY has the highest availability."

## 5. Where Hints Are Stored and Coordinator Overhead

In standard architecture, hints are stored on the **Cassandra node that created the hint**, in a configured local hints directory/files. They are not in a CQL table that an application can directly `SELECT`.

Operational implications:

1. **One down replica can build backlogs across many coordinators**, not just on one disk.
2. Hint data consumes **local disk capacity**, competing with other node operations.
3. When a coordinator restarts or suffers disk errors, hint state must be assessed according to actual persistence behavior; never assume every hint remains safe simply because a mutation was sent.
4. Hint files are flushed, replayed, and deleted by dedicated mechanisms; "target node UP" does not mean all hint files are gone.
5. Hints depend on target host metadata, so node replacement or topology changes require proper repair/rebuild/streaming procedures rather than arbitrarily copying hint files.

### 5.1. Estimating Hint Volume

A rough model:

```text
R = mutation rate targeting the down replica (mutations/second)
T = duration within the active hint creation window (seconds)
S = average bytes to store one hint, including mutation + overhead

hint_count ≈ R × T
hint_bytes ≈ R × T × S
```

Suppose C is down for **15 minutes**, receiving **500 mutations/second** aimed at C, with an average hint size of **350 B** (assumed):

```text
T = 15 × 60 = 900 seconds
Hint count ≈ 500 × 900 = 450,000
Assumed bytes ≈ 450,000 × 350
              = 157,500,000 B = 157.5 MB
```

**157.5 MB is not an exact disk measurement.** Encoding, grouping/file headers, compression, flushes, mutation types, coordinator distribution, and metadata change the actual footprint. Never treat "350 B per hint" as a universal constant across schemas.

### 5.2. Hint Count Does Not Equal User Request Count

A single request can:

- Write to one or more partitions/business tables.
- Generate mutations across multiple replicas.
- Require hints for **multiple down replicas**.
- Be retried on timeout, generating extra mutations/hints depending on idempotency and the write path.

Thus, `requests/s × duration` is only an approximation when you have verified a 1-request → 1-mutation → 1-missing-replica relationship, not a formula for every table.

### 5.3. Estimating Replay Backlog Time

If the backlog holds `B` bytes, effective delivery throughput to the target node is `D` bytes/second, and the node continues receiving new traffic:

```text
minimum_replay_time ≈ B / D
```

This is an **ideal lower bound** assuming steady throughput with no retries, interruptions, or resource contention. In practice, a newly recovered node must simultaneously handle current reads/writes, streaming/repair, and hint replay.

If effective hint delivery speed only matches incoming backlog growth, the system may fail to catch up. Operational metrics should separate **stored hints**, **newly created hints**, **successfully delivered hints**, and **failed/dropped hints**.

## 6. Relevant Cassandra Configuration and Version-Dependent Limits

Specific settings live in Cassandra node configuration (typically `cassandra.yaml`), not as CQL table options. **Parameter names and units can vary by version**; check the config file and documentation for the exact Cassandra release deployed rather than copying blocks between versions.

| Option Group | Purpose | Operational Question |
| --- | --- | --- |
| **Enable/disable hinted handoff** | Whether hint creation/delivery is permitted | Does it vary by DC or cluster policy? |
| **Maximum hint window** | Caps how long hints continue being created for a down host | What repair path handles longer outages? |
| **Hints directory** | Location for hint files | Is there disk headroom? Which data shares the volume? |
| **Flush period / file size** | How hint files are buffered and written | Is there an I/O backlog or too many files? |
| **Delivery threads / throttle** | Rate limit and concurrency during replay | Could a recovering node be overwhelmed? |
| **Compression** | Reduces hint footprint depending on configuration | How much extra CPU vs. disk saved? |
| **DC/host restrictions** | Scope of hint applicability | Should certain DCs be excluded per policy? |

### 6.1. Common Configuration Names

In some Cassandra 4.x releases you may see names like:

```yaml
# REFERENCE LIST OF NAMES ONLY, NOT A CONFIG BLOCK
# TO PASTE VERBATIM ACROSS ALL VERSIONS.
hinted_handoff_enabled: true
max_hint_window_in_ms: 10800000  # Example 3 hours in releases using ms units
hints_directory: /var/lib/cassandra/hints
max_hints_delivery_threads: 2
```

**Important note:** Newer Cassandra releases may use **unit-suffixed duration** syntax/names instead of `_in_ms`; throttling, flush, max file size, and defaults can also differ. Verify syntax **against your running release** before editing. Paths and numbers above are **examples only**, not tuning recommendations.

### 6.2. Do Not Boost Throughput by Arbitrarily Disabling Hints

Disabling hinted handoff may reduce some write/recovery overhead, but it removes fast catch-up for briefly down replicas. Divergence can then persist until other mechanisms recover the data, increasing reliance on repair.

Conversely, enabling hints with an overly long window can exhaust disk on healthy nodes. Decisions should be weighed against:

- Typical actual node outage durations.
- Peak mutation rate targeting a single replica.
- Hints directory capacity and headroom.
- Replay rate and absorption capacity of a recovering node.
- Anti-entropy repair schedule and deletion safety policy.
- API availability requirements at the chosen consistency levels.

### 6.3. Do Not Assume Per-Node Settings Are Cluster-Wide

Hinted handoff settings are normally configured per node. If nodes have inconsistent values due to configuration drift, the same outage can produce very different backlogs depending on which coordinator handles the request.

During investigations, record the **hint-creating node**, version, config values, and change timestamps. Do not inspect only the target replica's config file: the nodes holding hints are often where disk and delivery must be checked.

## 7. How Hinted Handoff, Read Repair, Anti-Entropy Repair, and Streaming Differ

| Mechanism | When It Helps | Scope | Limitations |
| --- | --- | --- | --- |
| **Hinted handoff** | Replica misses writes during a short outage with eligible hints | Stored mutations for the target | Best-effort, window/resource bounded; does not replace repair |
| **Read repair** | A read detects discrepancies per version logic/config | Data touched by the read and participating replicas | Unread data can remain divergent |
| **Anti-entropy repair** | Proactive job checking synchronization across token ranges | Relevant replicas within repair scope | Network/I/O/CPU heavy; requires scheduling and completion tracking |
| **Streaming/rebuild** | Adding/replacing nodes, bootstrap, rebuild, or recovery tasks | Data/token ranges being transferred | Does not fix business-version mistakes |
| **Compaction** | Merging/organizing SSTables and handling tombstones locally | Locally stored data | Does not compare against other replicas |

**Core scenario:** Node C is down for five hours with a three-hour hint window. When C returns, hinted handoff may replay stored hints, but mutations from the post-window period **may not exist in the backlog**. Anti-entropy repair is the complementary layer needed to detect and fix missing data on an appropriate schedule.

A quorum `SELECT` can help detect mismatches for the queried key when read repair applies, but it **is not sufficient to conclude all partitions are consistent**. Repair over token ranges is required for broader coverage.

## 8. Hint Replay with TTL, DELETE, and Tombstones

A hint should not be viewed as "re-executing a write from scratch" with new arbitrary logic. It represents the **original mutation to deliver to the target replica**. Timestamps, TTLs, and tombstones give late replay important consequences.

### 8.1. Data with TTL

Suppose an application writes telemetry with a **one-hour** TTL. Replica C goes down for two hours; the coordinator stores hints for some mutations.

```text
09:00  Event E is written with TTL = 3,600 seconds
09:00  C is down; hint E is created if eligible
10:00  Event E expires per data retention policy
11:00  C returns; system evaluates replaying hint E
```

Do not assume E will live another hour on C just because the hint was delivered at 11:00. Mutation TTL/metadata must follow Cassandra storage semantics; whether an old hint is still delivered or dropped per version conditions **is not a way to extend retention**.

To verify, check **values readable after expiration**, `TTL(column)` while still live, and delivery logs/metrics—rather than merely checking whether the hint file disappeared.

### 8.2. DELETE and Resurrection Risk

Scenario:

```text
t0   A/B/C all contain row X
t1   C goes down
t2   Client runs DELETE X; A/B store tombstone, C misses it
t3   C stays down too long; some hints may be missing
t4   Tombstones on A/B become eligible for purge per
     compaction and repair rules/conditions
t5   C returns still holding old data X
```

If the replica that missed the delete is not safely synchronized before tombstones are purged, there is a **zombie/resurrection** risk. Having hinted handoff enabled **does not permit** skipping repair planning and deletion safety.

**`gc_grace_seconds` is not the hint window.** It relates to tombstone protection duration, alongside other version-specific, compaction, and replica-state conditions. Never lower `gc_grace_seconds` just to free disk or clear hints faster; doing so increases the risk of deleted data reappearing.

### 8.3. Conflicting Timestamps and Out-of-Order Business Events

Suppose:

```text
Revision 10: order = PENDING
Revision 11: order = PAID

Mutation revision 11 reaches A/B/C.
A retry of revision 10 arrives later with a larger write timestamp.
```

Cassandra normally resolves cell conflicts by write timestamp and tombstone rules. If revision 10 carries a larger timestamp, replicas can **all converge to the business-incorrect PENDING state**.

Hinted handoff does not compare business `revision` values to preserve the "correct version." You need an authoritative transition source, ordering/deduplication, or appropriate conditional LWT/CAS. **Converged replicas do not guarantee correct business state.**

### 8.4. Collections, Counters, and Retries

The fact that a mutation can be replayed during failures does not mean every application operation is idempotent. Specifically:

- Writing to the same row key with deterministic values is usually easier to make retry-safe than generating new event IDs.
- Collection operations depend on collection type and update form, carrying distinct cost and idempotency properties.
- Counters have different semantics from regular columns; blind retries after timeouts can corrupt counts.
- Rewriting with a new TTL can alter value expiration; retention policies must remain consistent.

Hinted handoff **is not a business deduplication system** for duplicate client requests.

## 9. Multi-Datacenter: A Hint Does Not Promise Fresh Data Everywhere

With `NetworkTopologyStrategy`, DCs can have different RFs. For example:

```sql
CREATE KEYSPACE replica_hint_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc_primary': 3,
    'dc_backup': 2
};
```

This is an illustrative configuration; DC names must match your actual topology, and each DC must have enough nodes to satisfy its RF.

If a client writes with `LOCAL_QUORUM` in `dc_primary`, success is based on quorum in the **coordinator's local DC**, not a guarantee that all `dc_backup` replicas have received the mutation. During degraded cross-DC networking or slow remote replicas, a `LOCAL_ONE` read in the backup DC may still see stale data.

Do not conclude "hinted handoff guarantees all DCs stay immediately synchronized":

- Replicas may be eligible for hints per configuration/version, or cross-DC hints may have restrictions.
- Local write success does not create instant synchronization in remote DCs.
- Broad recovery may require anti-entropy repair/streaming beyond hinted handoff.
- When an application requires cross-DC read-after-write, design an explicit **consistency and DC-routing contract** rather than relying on pending hint queues.

## 10. CQL Lab: Observing a Missing Replica Case

**Run only on a lab cluster** authorized for node-down simulation. Shutting down nodes or networks for testing in production without a plan can cause service outages or data loss.

### 10.1. Preparing an RF=3 Keyspace and Table

Assume a lab cluster with one DC named `dc1` and at least three nodes. Example schema:

```sql
CREATE KEYSPACE replica_hint_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE replica_hint_lab.orders_by_id (
    tenant_id text,
    order_id uuid,
    status text,
    revision bigint,
    changed_at timestamp,
    PRIMARY KEY ((tenant_id, order_id))
);
```

The two `CREATE KEYSPACE replica_hint_lab` examples above use **different hypothetical topologies**; pick only **one** matching your real lab. Do not paste both consecutively into the same cluster because a keyspace with the same name will fail as already existing. If your lab has only one DC, use the `dc1` example here.

### 10.2. Seeding a Row with Explicit CL

In `cqlsh`, `CONSISTENCY` is a **shell command**, not syntax to embed inside a Java prepared statement.

```sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO replica_hint_lab.orders_by_id (
    tenant_id, order_id, status, revision, changed_at
) VALUES (
    'tenant-A',
    00000000-0000-4000-8000-000000000001,
    'PENDING',
    1,
    '2026-11-21T09:00:00Z'
);

SELECT status, revision, WRITETIME(status) AS status_write_time
FROM replica_hint_lab.orders_by_id
WHERE tenant_id = 'tenant-A'
  AND order_id = 00000000-0000-4000-8000-000000000001;
```

Ensure initial replicas are stable and record the result. `WRITETIME(status)` represents the write timestamp of the **`status` cell**, not the business `changed_at` column.

### 10.3. Simulating a Brief Replica Outage

Controlled procedure:

1. Identify the **actual replica set** for the test partition using tools appropriate for your version and topology; do not pick a random node.
2. Record hint window configuration, CL, RF, cluster status, hints directory usage, and baseline metrics.
3. In the lab, make one replica of the partition **temporarily unresponsive** long enough for failure detection to notice, yet **shorter than the assumed hint window**.
4. Write a new version with `LOCAL_QUORUM` while the remaining two replicas stay up.
5. Check client success, hint creation via logs/metrics if available, and `SELECT` outputs at recorded times.
6. Bring the node back, observe hint backlog and delivery, and verify data after stabilization.
7. Log hint creation time, node-up time, and backlog completion time; compare against configured limits.

Update CQL:

```sql
CONSISTENCY LOCAL_QUORUM;

UPDATE replica_hint_lab.orders_by_id
SET status = 'PAID',
    revision = 2,
    changed_at = '2026-11-21T10:00:00Z'
WHERE tenant_id = 'tenant-A'
  AND order_id = 00000000-0000-4000-8000-000000000001;

CONSISTENCY ONE;

SELECT status, revision
FROM replica_hint_lab.orders_by_id
WHERE tenant_id = 'tenant-A'
  AND order_id = 00000000-0000-4000-8000-000000000001;

CONSISTENCY LOCAL_QUORUM;

SELECT status, revision
FROM replica_hint_lab.orders_by_id
WHERE tenant_id = 'tenant-A'
  AND order_id = 00000000-0000-4000-8000-000000000001;
```

**Do not expect `ONE` to necessarily return PENDING**: the coordinator may pick a replica that received the write, or avoid the down node. Likewise, `LOCAL_QUORUM` returning `PAID` does not prove C has converged. To prove hinted handoff ran, you need **evidence from metrics/logs and replica state checks**, not a single `SELECT`.

### 10.4. Testing Beyond the Hint Window

In a separate lab scenario, keep the replica down longer than the configured window and continue writing **several mutations with stable IDs** both before and after the window boundary.

Test goals:

- Pre-boundary mutations may have generated hints.
- Post-window mutations **must not be assumed** to have hints.
- When the node comes back up, the backlog may drain completely while the replica is still missing data in certain token ranges.
- A properly scoped repair procedure can detect and fix the discrepancies.

This experiment can be time- and resource-consuming if using a multi-hour default window. In a lab you may configure it per your version's test guidelines, but **never alter production settings just to speed up a test**.

### 10.5. Testing Write ANY Separately

For `ANY`, run the experiment only if the lab has enough nodes for a coordinator to accept requests while all partition replicas are unavailable, and the system is configured/allowed to use corresponding hint conditions.

```sql
-- Test only in a lab and record topology/hint-creation behavior.
CONSISTENCY ANY;

INSERT INTO replica_hint_lab.orders_by_id (
    tenant_id, order_id, status, revision, changed_at
) VALUES (
    'tenant-A',
    00000000-0000-4000-8000-000000000002,
    'PENDING',
    1,
    '2026-11-21T10:05:00Z'
);

-- ANY is not a read consistency level; switch to a valid read CL.
CONSISTENCY ONE;

SELECT status, revision
FROM replica_hint_lab.orders_by_id
WHERE tenant_id = 'tenant-A'
  AND order_id = 00000000-0000-4000-8000-000000000002;
```

If the write succeeded solely via a hint, an immediate read may not see the row yet. **There is no guaranteed outcome** if the lab is not set up so that all data replicas are genuinely unavailable: the write might reach a replica, or the request might fail because a hint could not be stored.

## 11. Java Driver 4.x: Writing with Explicit CL, Recognizing Unknown Outcomes

The Java example uses **DataStax Java Driver 4.x** with an application-scoped `CqlSession`. It illustrates **per-statement consistency levels** and avoiding false conclusions from timeouts. It is not a self-healing data library.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.servererrors.WriteFailureException;
import com.datastax.oss.driver.api.core.servererrors.WriteTimeoutException;

import java.time.Instant;
import java.util.UUID;

public final class HintedHandoffLabRepository {
    private final CqlSession session;
    private final PreparedStatement upsert;
    private final PreparedStatement read;

    public HintedHandoffLabRepository(CqlSession session) {
        this.session = session;
        this.upsert = session.prepare(
            "INSERT INTO replica_hint_lab.orders_by_id " +
            "(tenant_id, order_id, status, revision, changed_at) " +
            "VALUES (?, ?, ?, ?, ?)"
        );
        this.read = session.prepare(
            "SELECT status, revision, changed_at, " +
            "WRITETIME(status) AS status_write_time " +
            "FROM replica_hint_lab.orders_by_id " +
            "WHERE tenant_id = ? AND order_id = ?"
        );
    }

    public void writeQuorum(
        String tenantId, UUID orderId,
        String status, long revision, Instant changedAt
    ) {
        try {
            session.execute(
                upsert.bind(tenantId, orderId, status, revision, changedAt)
                    .setConsistencyLevel(
                        DefaultConsistencyLevel.LOCAL_QUORUM
                    )
            );
        } catch (WriteTimeoutException | WriteFailureException ex) {
            // Mutation outcome on each replica is unknown.
            // Do not generate a new event_id/revision and retry infinitely.
            // Log context and hand off to a safe readback/retry workflow.
            throw new IllegalStateException(
                "Write outcome requires verification", ex
            );
        }
    }

    public Row readOne(String tenantId, UUID orderId) {
        return session.execute(
            read.bind(tenantId, orderId)
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
        ).one();
    }

    public Row readLocalQuorum(String tenantId, UUID orderId) {
        return session.execute(
            read.bind(tenantId, orderId)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM
                )
        ).one();
    }
}
```

Operational notes:

- Other exceptions (client timeout, unavailable, connection error) can also occur and must be classified per your service contract; the example shows only two common server-side errors.
- `WriteTimeoutException` does not prove the mutation was **not** applied on any replica. Conversely, write success at a given CL does not prove **every replica** received it.
- Keep the same `tenant_id`/`order_id` and revision on retry **if business rules allow**, and never let an older revision overwrite a newer accepted state.
- The Java driver **does not provide a client API to SELECT hint files directly** on coordinators. Inspecting hinted handoff requires operational metrics and logs.
- `Row` may be `null` when the partition has no readable data at the chosen CL. Do not conclude from a single `null` that "the database lost data."
- Do not treat `LOCAL_QUORUM` as a fix for discrepancies across separate projection tables; that is a business mutation synchronization issue.

### 11.1. Why Not Automatically Retry Every Write?

A write-path timeout can occur **after the mutation has reached some replicas**, or even before the client receives the ACK. Retrying with the same primary key and values is usually easier to control than generating new IDs, yet you must still consider write timestamps, TTLs, counters, and business ordering.

Example:

```text
Request #1: revision 10 -> PENDING, timed out but some replicas wrote it
Request #2: revision 11 -> PAID, succeeded
Retry #1:   revision 10 -> PENDING with a newer write timestamp

If retries do not check versions, replicas may converge
to the wrong PENDING state even when hinted handoff/repair works properly.
```

The system needs an **idempotency key**, an authoritative revision source, per-entity ordering, or appropriate LWT/CAS. Hinted handoff is a layer below the application, not a business state-transition serializer.

## 12. Observing Hint Backlogs and Recovery Status

You cannot evaluate hinted handoff solely by checking whether "the node is up." Monitor these signal groups:

| Group | What to Observe | Risk Detected |
| --- | --- | --- |
| Hint counts | Hints created/pending/delivered/dropped/failed per tool support | Backlog not shrinking, hints not created, or hints dropped |
| Disk | Hints directory usage on each hint-creating node, growth rate | Disk exhaustion on healthy coordinators |
| Delivery | Effective replay rate, retry counts, age/remaining duration | Target returned but failing to catch up |
| Replica state | Node UP/DOWN, host ID, topology/DC, streaming | Is the target node genuinely ready? |
| Read/write | p95/p99 latency, timeouts, CL, ACK counts | Recovering node overloaded or reads still stale |
| Repair | Schedule, token range scope, completed/failed jobs | Hints insufficient for long outages |
| Tombstones/TTL | Deletes not reaching replicas, data age, compaction | Resurrection / retention expiration risk |
| App invariants | Correct version, secondary table mappings converged | Separating replica lag from projection lag |

Exact metric/JMX/table names on dashboards depend on Cassandra version and monitoring stack. Never write alerts tied to a metric **that does not exist in your cluster**. Use the exact names from the running system and note scope: **per host**, **per DC**, or **per keyspace**.

### 12.1. Reference Operational Tools

Common inspection commands:

```text
nodetool status
nodetool tpstats
nodetool netstats
nodetool compactionstats
```

Where supported by the version, dedicated hinted handoff operations may exist to list pending hints, pause/resume delivery, or clear hints. **Do not assume identical commands exist across all versions**, and never delete/truncate hints merely to silence an alert without a repair/recovery plan.

Because hinted handoff uses its own storage directory, monitor actual disk usage per access-control policies alongside Cassandra metrics/logs. Never use `SELECT COUNT(*)` on a business table as a way to "count hints."

### 12.2. How Should Alert Thresholds Be Designed?

There is no universal MB or hint-window threshold. Base alerts on:

1. **Backlog growth rate** while a replica is down.
2. **Free disk space on hint-creating nodes**, alongside compaction and other storage needs.
3. **Oldest hint age** or replica downtime relative to the configured window.
4. **Replay rate** after the replica returns and sluggish drain progress.
5. **Repair schedule** relative to tombstone deletion protection windows.
6. **User request impact**: timeouts, p99 latency, and CL satisfaction.

Concrete thresholds like "alert when hints directory reaches 10 GB" only make sense after measuring that specific cluster's schema, throughput, topology, and disk headroom. Do not apply them blindly across every Cassandra deployment.

## 13. Runbook: Short Outage, Long Outage, and Stalled Replay

### 13.1. Before Touching the Cluster

Record:

```text
Cluster/version:
DC/RF:
Time node was considered DOWN:
max hint window and config version:
Current node status:
Coordinator nodes holding hints:
Disk usage on those nodes:
Pending/delivery/failed hints:
Current read/write CL and timeouts:
Repair history and coverage:
TTL/delete policy and gc_grace:
Business source/replay options:
```

Without evidence of which nodes hold hints or which replicas own the key, do not rush to "fix" things by altering timestamps, truncating tables, or switching all reads to `ALL`.

### 13.2. Scenario A — Outage Shorter Than Hint Window

1. Identify when the replica was marked down.
2. Verify hinted handoff is enabled and coordinators have sufficient disk/resources.
3. Verify writes/reads still satisfy agreed CLs; do not lower CL to mask errors if SLAs forbid it.
4. Recover the node per system procedures.
5. Observe hint delivery rate, delivery errors, and load on the returning node.
6. After the backlog stabilizes, spot-check partitions/rows written during the outage.
7. Maintain the regular repair schedule; hinted handoff does not eliminate the need for anti-entropy repair.

Do not promise "once the node is up, all hints are done." Require metric/log evidence.

### 13.3. Scenario B — Outage Exceeds Hint Window

1. Determine how long the outage exceeded the window and which mutations may **lack hints**.
2. Recover the node and monitor any hints still eligible for replay.
3. **Schedule repair per version/topology procedures**, covering the token ranges needing synchronization.
4. Check tombstone/`gc_grace_seconds` safety and deleted data; do not force compaction.
5. If the node requires replace/rebuild, plan streaming and verify sufficient disk/resources.
6. Verify data post-recovery, including mutations from the **post-window** period.

**Do not mark the incident resolved just because the hint backlog is 0.** A zero backlog may simply mean hints stopped being created after the cutoff; it **does not prove the replica holds complete data**.

### 13.4. Scenario C — Node Is UP but Backlog Does Not Shrink

Investigation areas:

- Are host ID, topology, and target still valid?
- Does the target node have enough CPU, disk, and network, and is it free of compaction/streaming bottlenecks?
- Are there delivery errors, connection failures, low throttle limits, or heavy ongoing traffic?
- Is the hint-holding coordinator short on disk/I/O or facing a massive backlog?
- Are hint files corrupted or ineligible for replay per version rules?
- Is it necessary to move to repair/rebuild if hints cannot guarantee convergence?

Only increase threads/throttles after identifying the bottleneck. Cranking up delivery too aggressively can **overload the newly recovered node**, making the situation worse.

### 13.5. Scenario D — Deleted Data Reappears

Prioritize preserving evidence:

1. Record the full keyspace/table/partition/clustering key and observed value.
2. Gather deletion/TTL timestamps, `WRITETIME` if a live value exists, node offline windows, and repair history.
3. Inspect tombstones/grace, compaction, and which replicas missed the delete.
4. Do not lower grace or force SSTable cleanup before understanding resurrection risk.
5. Recover per the runbook for your Cassandra version with data-safety verification.

Do not blame every "reappearing" record on hints; sometimes the root cause is a producer replaying an old event with a new timestamp or an undeleted projection table. Those two failure classes require separate procedures.

## 14. Common Pitfalls

| Pitfall | Consequence | Correct Understanding / Resolution |
| --- | --- | --- |
| "RF=3 means no hints or repair needed" | Replicas missing mutations can keep stale data | RF is replica count, not an instant synchronization guarantee |
| "Write ONE only sends to one replica" | Misunderstanding the write path | ONE is the ACK count waited for, not a limit on coordinator forwarding |
| "3h hint window = all hints replayed within 3h" | Wrong recovery SLAs | Window caps hint creation for down hosts, not delivery deadline |
| "Node UP = data is definitely consistent" | Backlog remains or mutations exceeded window | Monitor delivery and run repair |
| "Just raise the window to 7 days" | Hints can fill disks and recovery becomes too slow | Calculate R×T×S, set limits, and use repair |
| "Hints guarantee zero lost mutations on any failure" | Best-effort mistaken for absolute durable transactions | Maintain recovery sources, repair, and monitoring |
| "ANY success = subsequent read definitely sees the row" | Reads may miss it if only a hint exists | ANY is a write CL, not a read CL |
| "Reading LOCAL_QUORUM always heals down nodes" | Quorum does not require all replicas to have the mutation | Use hints/repair and separate monitoring |
| "Hinted handoff replaces anti-entropy repair" | Long outages still leave missing data | Schedule token-range repairs |
| "Hint window is the data TTL" | Wrong retention expectations | Separate mutation TTL, window, and grace |
| "Lower gc_grace_seconds to clean hints" | Misses the actual target and increases resurrection risk | Manage hints, tombstones, and repair separately |
| "Hints on source auto-fix other projection tables" | Unsent business mutations will never be generated | Use durable events, retries, and business reconciliation |
| "Timeout retries are always safe" | Duplicate IDs, timestamps overwriting newer state | Enforce idempotency/ordering and readback |
| "Backlog = 0 means data is complete" | Hints may never have been created post-window | Verify with repair and authoritative data sources |
| "Increasing throttle always finishes faster" | Newly returned node suffers I/O/network storms | Tune based on bottlenecks and real measurements |

## 15. Practice Exercise

A single-DC lab cluster, **RF=3**, stores order status in `orders_by_id`. Three replicas A/B/C initially hold `status=PENDING`, revision 7. C is marked down at 09:00. The cluster sets **hint window = 2 hours** for this illustrative scenario. During downtime, coordinators receive an average of **300 mutations/second** destined for C; assume each hint takes **400 B on disk** (for calculation purposes only).

Timeline:

```text
09:00  C is marked DOWN
09:10  Write revision 8, status=PAID at CL=LOCAL_QUORUM
10:30  Write revision 9, status=SHIPPED at CL=LOCAL_QUORUM
11:20  Write revision 10, status=DELIVERED at CL=LOCAL_QUORUM
12:00  C returns
```

**Tasks:**

1. With RF=3 in one DC, what is the minimum number of ACKs for `LOCAL_QUORUM`? Why can the write at 09:10 succeed while C is down?
2. Can the mutations at 09:10 and 10:30 generate hints? What about the mutation at 11:20 after C has been down for over two hours?
3. Estimate the **hint count and bytes** that can be created during the **two-hour active hint creation period**, assuming R/S remain constant and all mutations are eligible. Name at least three factors that make real disk usage differ from this calculation.
4. C returns at 12:00: can you conclude that by 12:01 all revisions exist on C? If not, what must be measured?
5. The hint backlog drains completely, yet C still lacks revision 10. Which mechanism is appropriate to detect/fix what hints did not cover?
6. If a `DELETE` at 11:20 was also missed by C and the tombstone is purged before old data on C is synchronized, what risk arises? What are the roles of `gc_grace_seconds` and repair?
7. Suppose a client writes with `ANY` and only a hint is stored: what might an immediate `ONE` read see? Why is there no `READ ANY`?
8. In Java Driver 4.x, write a prepared statement updating status with `LOCAL_QUORUM` and a `ONE` readback; describe how to handle a timeout so revision 8 does not overwrite revision 10.
9. If `orders_by_id` is at revision 10 while `orders_by_status_day` still holds revision 8's state, does hinted handoff automatically fix two different tables? What mechanism is needed?

**Reference Hints:**

```text
RF=3 -> LOCAL_QUORUM = floor(3/2)+1 = 2 replica ACKs.

Hint window = 2 hours:
  09:10 and 10:30 fall within the assumed window.
  11:20 exceeded the window; do not assume a new hint was created.

Hint count ≈ 300 mutations/s × (2 × 3,600 s)
           = 2,160,000 hints

Assumed disk ≈ 2,160,000 × 400 B
             = 864,000,000 B = 864 MB decimal.
```

These numbers **exclude** compression, file/header metadata, mutation variance, coordinator distribution, hint write failures, and ineligible mutation types. After 12:00, monitor actual delivery and schedule **repair** because mutations occurred past the hint window. `ANY` is a write CL that can acknowledge via hint alone; a read from a replica lacking the data may still not find the row. Discrepancies across projections must be solved using **durable change sources, retry/idempotency, and application-layer reconciliation**, not hinted handoff alone.

## Conclusion

**Hinted handoff helps a temporarily absent replica catch up on mutations stored as hints**, yet it has clear boundaries: **only hints created within eligible conditions and the allowed window have a chance to be replayed**, and delivery depends on the target node, resources, and cluster health. The hint window is not a data TTL, not a backlog drain deadline, and cannot replace repair. When a node suffers prolonged downtime, backlogs grow large, tombstones approach expiration of protection, or topology changes, you need **anti-entropy repair/streaming alongside a verified runbook**. When application operations time out, keep keys and revisions stable, prevent regressive retries, and distinguish **replica divergence** from **projection consistency**. Cassandra reliability comes from combining RF, CL, hints, repair, operational observability, and business-level controls—not from any single parameter.
