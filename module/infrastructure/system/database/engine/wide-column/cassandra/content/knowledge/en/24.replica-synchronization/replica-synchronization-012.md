# Checking Convergence Progress and Missing Data

## Objectives and Context

Apache Cassandra distributes data by **partition key** and replicates each partition across replicas according to the **replication factor (RF)**. When nodes or networks fail, some replicas may miss writes, updates, or deletes. A node coming back online **does not mean** data matches immediately. Operators need to know how far **convergence** has progressed, which records are still missing, and how to fix them.

This lesson belongs to the **Replica Synchronization** chapter in the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. It draws on the wide-column model, tokens/partition keys, query-driven table design, read/write consistency levels, replication, CQL, compaction, repair, error handling, and Java application access.

After this lesson, you will be able to:

1. Distinguish **cluster health**, **data readability**, and **replica convergence**.
2. Understand the scope of **hinted handoff**, **read repair**, and **anti-entropy repair**.
3. Design tests with **independent expected datasets** to detect missing records.
4. Track progress using logs, metrics, repair status, error counts, and query results across consistency levels.
5. Practice stopping a replica in an RF=3 lab, writing during downtime, bringing the node back, repairing, and reconciling.
6. Build a Java client that records ACK/UNKNOWN states and verifies by key without overclaiming "synchronized" beyond available evidence.

> **Environment:** node-stopping and repair operations in this lesson are strictly for a **three-node lab authorized for fault injection**. Never apply them directly to production clusters without operational planning, monitoring, and recovery procedures.

## 1. What Does "Convergence" Mean?

A partition can have multiple copies. When replicas receive updates asynchronously, their contents temporarily differ. **Convergence** means replicas gradually obtain the information needed so reads and reconciliation produce the same logical data under Cassandra's rules.

Suppose three nodes `R1`, `R2`, and `R3` hold the partition for `run_id='sync-01'`:

| Time | R1 | R2 | R3 |
| --- | --- | --- | --- |
| T0: wrote `event A` at `ALL` | A | A | A |
| T1: R3 shuts down | A | A | A, but node down |
| T2: wrote `event B` at `LOCAL_QUORUM` | A, B | A, B | Lacks B |
| T3: R3 starts up | A, B | A, B | May still lack B |
| T4: synchronization completes | A, B | A, B | A, B |

**T3 does not automatically equal T4.** `nodetool status` showing `UN` (*Up/Normal*) for R3 reflects only membership/node liveness, not proof that R3 received `event B`.

~~~mermaid
flowchart LR
    A["Write to partition"] --> B["Live replicas acknowledge"]
    B --> C["Disconnected replica misses write"]
    C --> D["Replica comes back online"]
    D --> E["Hints / read repair / anti-entropy repair"]
    E --> F["Reconcile expected records"]
    F --> G{"Data complete and sync finished?"}
    G -->|With proper evidence| H["Convergence criteria met"]
    G -->|Not yet| I["Investigate missing / lag / errors"]
~~~

### Three Types of Evidence Often Confused

| Evidence | What You Can Conclude | What You **Cannot** Yet Conclude |
| --- | --- | --- |
| Node `UN` in `nodetool status` | Node is in the cluster and alive | Local data is complete or repair finished |
| `SELECT` returns right data at `LOCAL_QUORUM` | Query reached enough replicas to return the value per chosen CL | Every replica holds the value; every other key is right |
| Repair completed without error over appropriate scope | Replicas/ranges in that repair session were compared per repair mechanics | Entire business pipeline lost no events or out-of-scope data is complete |

**Reading via R3's address does not force Cassandra to use only R3's local data.** R3 can act as coordinator and query other replicas. Hence a successful `cqlsh` query aimed at R3 does not prove R3's own SSTables hold complete data.

## 2. RF, Consistency Levels, and Inference Limits

Consider a lab with **one datacenter**, `RF=3`, and three replicas per partition. With write consistency `LOCAL_QUORUM`, the coordinator needs **two acknowledgments** from replicas in the local DC. When one node is down, the remaining two nodes can ACK if both respond.

| CL | RF=3, One DC | Meaning for the Experiment |
| --- | --- | --- |
| `ONE` / `LOCAL_ONE` | Needs one replica ACK | Can succeed even if another copy lacks the mutation |
| `LOCAL_QUORUM` | Needs two replicas in local DC | If write succeeds, at least two replicas acknowledged |
| `ALL` | Needs all three replicas | Cannot succeed while one replica is unresponsive |

In a single-DC/RF3 setup, `W=2` and `R=2` satisfy `W+R=4>3`, so the two quorums must overlap. This lets quorum reads see quorum-ACKed writes, yet **it does not mean a single quorum read proves every replica has been healed**.

Limits to keep in mind:

- A `LOCAL_ONE` query may read from a stale replica; that does not pinpoint which exact replica is missing data.
- An `ALL` query while a node is down may throw `Unavailable`; **a query error is not proof of data loss**.
- An `ALL` read succeeding after all three nodes return may reconcile data across replicas; it is not an independent dump of each replica.
- With **multiple datacenters**, `LOCAL_QUORUM` applies quorum only inside the local DC. Check each DC's replication and use appropriate CLs when aiming for cluster-wide convergence.
- For concurrent writes to the same key, Cassandra reconciles by timestamp/tombstone; quorum does not provide conditional update transactions. To prevent lost updates, use LWT/`IF` patterns where appropriate.
- If a client times out, the mutation may still exist on some replicas. Distinguish **ACKed**, **unknown outcome**, and **never sent** instead of conflating them.

## 3. Three Mechanisms Bringing Replicas Closer

### 3.1. Hinted Handoff: Catch-Up After Brief Outages

When a replica misses a mutation, a live node can store a **hint** and replay it after the replica returns, subject to configuration, resources, and hint retention limits. Hints shorten the window of missing data for some outages.

**Never treat hinted handoff as a cure-all for missing data:**

- Hints can expire, be disabled, hit capacity limits, or fail to cover the full downtime interval.
- An empty hint queue proves only that no pending hints remain within observed scope—it **does not prove** all replicas match.
- Hints do not replace periodic anti-entropy repair schedules.

### 3.2. Read Repair: Fixing Slices Observed Diverging on Reads

The read path can detect mismatches among participating replicas and, per version/configuration, repair within the read data scope. However, a `SELECT` on one partition does not scan and compare the entire token range.

Never design recovery procedures assuming "reading through every key will fully repair everything." Read load, `read_repair` table options, Cassandra version, and chosen replicas dictate what actually happens. Use managed repair for systematic synchronization.

### 3.3. Anti-Entropy Repair: Comparing Replica Ranges

`nodetool repair` initiates token-range comparison across replicas, exchanging needed data/differences. It may use Merkle trees and streaming; exact details vary by version, repair mode, and topology.

Repair has two dimensions that must not be conflated:

1. **Job completion:** the repair session reports success over an explicit keyspace/table/token-range scope with zero unhandled errors.
2. **Proving business data completeness:** every event/key ACKed by the app or emitted by the source of truth is present. Repair cannot recreate an event if it **exists on no remaining trusted replica or source**.

If data was deleted, tombstones must still exist and propagate safely. A replica offline longer than `gc_grace_seconds` after tombstones were purged can reintroduce **zombie data**; never solve that by blindly repairing the stale node.

| Mechanism | Primary Scope | What to Monitor | When It Is Insufficient |
| --- | --- | --- | --- |
| Hints | Buffered mutations to replay to an absent node | Hints pending, failed/delivered, per-node logs | Outage exceeded hint window; not all writes produce hints |
| Read repair | Discrepancies detected on the read path | Mismatches, read-repair metrics/logs where exposed by version | Unread partitions; only a subset of replicas participated |
| Anti-entropy repair | Token ranges/replicas in the repair session | Session state, range coverage, errors, streaming | Repair missed ranges, tombstones purged, event absent on all replicas |
| Business source reconciliation | IDs/events that ought to exist | Expected vs. actual sets, bucket checksums | Expected source is incomplete or unreliable |

## 4. Setting Measurable Convergence Criteria

Before injecting faults, define **what "done" means**, instead of merely waiting for every node to display `UN`.

Example criteria for lab `replication_lab.sync_probe`:

1. All involved nodes are `UN`, with valid schema/keyspace/replication.
2. Data **ACKed** in the client log has the expected markers/keys.
3. Hints and repair finished for the lab scope, with zero pending related errors.
4. Verification queries scoped by `run_id` and each `event_id` return expected values at the designated CL.
5. No concurrent writes/deletes or TTLs altered data during measurement.

**Accurate conclusion:** defined observation and synchronization criteria were met for **the specific table, keys, timestamp, topology, and CL**. Proving exact physical contents across every individual replica requires storage-level tools/checks or detailed repair coverage; one CQL query is not enough.

### Reference Progress Metrics

| Metric | Interpretation |
| --- | --- |
| Time from `node UN` to `repair complete` | Latency to complete controlled synchronization |
| Hints queued/delivered/failed | Mutation replay trend; inspect errors and hint limits too |
| Repair sessions/ranges completed vs. failed | Fraction of scope actually reconciled, not just request counts |
| Streaming bytes and duration | Data exchanged for sync and network/disk load |
| Read mismatch / read repair metrics | Signs of replica divergence, depending on Cassandra version and instrumentation |
| `expected_count`, `found_count`, `missing_count`, `mismatch_count` | Reconciliation against known keys from an external source |
| Disk I/O, compaction backlog, read/write p95/p99 | Cost of synchronization and application impact |

An example ratio is `found_count / expected_count` when the expected list is **complete and trusted**. Without an expected list, you cannot conclude "zero data loss" simply because `SELECT COUNT(*)` returns a number or pending hints hit zero. Full-table `COUNT(*)` checks also cause broad scans and unnecessary load.

## 5. Preparing a Three-Node Lab and Expected Dataset

### 5.1. Verify Topology

Assume a lab cluster with three nodes `cass-1`, `cass-2`, and `cass-3` in datacenter `datacenter1`; adjust names to match your environment.

~~~bash
# Run in the lab environment on a live node.
nodetool status
~~~

Expect all three nodes `UN` (*Up/Normal*), not bootstrapping, decommissioning, or running heavy maintenance. In `cqlsh`, check the connected node's version/DC:

~~~sql
SELECT release_version, data_center, host_id
FROM system.local;
~~~

Check each node when needed, since `system.local` describes only the answering node. If the datacenter is not named `datacenter1`, edit the DC name in `CREATE KEYSPACE`. Software/cluster configs and admin commands can differ across Cassandra versions.

### 5.2. Create an RF=3 Keyspace and Single-Partition Test Table

~~~sql
CREATE KEYSPACE IF NOT EXISTS replication_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS replication_lab.sync_probe (
    run_id text,
    event_id uuid,
    marker text,
    source_version int,
    payload text,
    PRIMARY KEY ((run_id), event_id)
);
~~~

`run_id` is the **partition key**; `event_id` is the clustering key. Each lab run should use a **fresh** `run_id`. Expected data is defined by `event_id` and stable `marker` values for post-incident reconciliation. `source_version` is merely application metadata; it **does not automatically guard against concurrent updates**. In the basic lab, avoid updating the same key repeatedly, counters, TTLs, or deletes so conclusions stay crisp.

If the keyspace/table already exists, `IF NOT EXISTS` will not alter old settings. Verify RF and durable writes:

~~~sql
SELECT keyspace_name, replication, durable_writes
FROM system_schema.keyspaces
WHERE keyspace_name = 'replication_lab';
~~~

Identify which nodes are expected to hold a partition using your running version's admin tools. In a three-node RF=3 lab topology, every node will replicate the test partition. On larger clusters, `nodetool getendpoints` by **partition key** lists endpoints; the output reflects **placement**, not proof that an endpoint already holds all data.

### 5.3. Store the Expected Dataset Outside Cassandra

Before the experiment, create a client-side manifest with at least these fields:

| run_id | event_id | marker | Purpose | Expected ACK |
| --- | --- | --- | --- | --- |
| `sync-demo-01` | `11111111-1111-4111-8111-111111111111` | `baseline-A` | Write while all replicas are up | Write at `ALL` |
| `sync-demo-01` | `22222222-2222-4222-8222-222222222222` | `during-outage-B` | Write while node 3 is down | Write at `LOCAL_QUORUM` |
| `sync-demo-01` | `33333333-3333-4333-8333-333333333333` | `after-recovery-C` | Write after node 3 returns | Write at `LOCAL_QUORUM` |

The manifest must also record the **actual observed outcome** of each INSERT. If a command times out, mark it `UNKNOWN`; never promote it to "ACKed" just because a later read finds the row. To know whether the system accepted **all business events**, reconcile against a trusted event source (event log / transactional source), not just writes that succeeded in Cassandra.

## 6. Experiment A: Creating a Replica Missing Data

### Step 1 — Write Baseline While All Nodes Are Up

In `cqlsh` connected to a live node:

~~~text
CONSISTENCY ALL
~~~

~~~sql
INSERT INTO replication_lab.sync_probe
    (run_id, event_id, marker, source_version, payload)
VALUES (
    'sync-demo-01',
    11111111-1111-4111-8111-111111111111,
    'baseline-A', 1, 'created-when-three-up'
);
~~~

Record **ACK_ALL** in the manifest only if the client receives success. `ALL` requires three replicas to acknowledge the mutation; it does not create a logical snapshot for other concurrent writes.

### Step 2 — Stop the Third Replica

~~~bash
# Sample command for Docker lab only; substitute exact container name.
docker kill --signal=KILL cass-3
~~~

Connect to `cass-1` or `cass-2` to check:

~~~bash
nodetool status
~~~

The two surviving nodes should show `UN`, with `cass-3` down as `DN` (*Down/Normal*). Wait for failure detection to reflect the state before interpreting results; process `SIGKILL` does not fully simulate physical power loss or disk corruption.

### Step 3 — Write B While Only Two Replicas Remain

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
INSERT INTO replication_lab.sync_probe
    (run_id, event_id, marker, source_version, payload)
VALUES (
    'sync-demo-01',
    22222222-2222-4222-8222-222222222222,
    'during-outage-B', 1, 'written-while-cass-3-down'
);
~~~

With RF3 in one DC, if both live nodes acknowledge, the command is ACKed at `LOCAL_QUORUM`. Because `cass-3` was already down beforehand, it **did not directly process INSERT B**, setting up a temporary missing-data scenario to observe upon recovery.

Read with quorum while `cass-3` is still down:

~~~sql
SELECT event_id, marker, source_version, payload
FROM replication_lab.sync_probe
WHERE run_id = 'sync-demo-01';
~~~

If both A and B were ACKed, both are expected in the read. At this stage **do not use `CONSISTENCY ALL`** to verify completeness: one replica is down, so `ALL` cannot complete normally.

### Step 4 — Restart the Down Replica

~~~bash
docker start cass-3
~~~

Check `nodetool status` until all three nodes show `UN`. You can re-read A and B at `LOCAL_QUORUM`. Seeing both is an outcome of quorum reading, **not proof that B has been replicated to node 3**.

### Step 5 — Write C After All Three Nodes Are Up

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
INSERT INTO replication_lab.sync_probe
    (run_id, event_id, marker, source_version, payload)
VALUES (
    'sync-demo-01',
    33333333-3333-4333-8333-333333333333,
    'after-recovery-C', 1, 'written-when-three-up'
);
~~~

Once A/B/C are acknowledged by the client at their respective CLs, you have a verification marker set. **To observe replica catch-up**, log node return timestamps, hint delivery, and repair rather than relying on one `SELECT`.

## 7. Experiment B: Observing Hints, Repairing Divergence, and Verifying

### 7.1. Observing Progress Before Repair

On an eligible lab node:

~~~bash
nodetool status
nodetool netstats
nodetool compactionstats
~~~

- `nodetool status` shows node liveness and topology, **not a data-sync percentage**.
- `nodetool netstats` is useful when streaming is active; it is **not a complete count of all hints**.
- `nodetool compactionstats` shows compaction load, yet compaction never replaces anti-entropy repair.
- Watch logs/JMX/metrics for hints delivered, hints pending, repair sessions, and errors per your exact version. Never infer full data completeness from a single zero metric.

If hints replayed cleanly, B may have reached R3 very fast. Therefore you **will not necessarily observe a missing read via CQL at `LOCAL_ONE`**. In Cassandra, connecting to R3 does not force queries to read only R3's local copy; data can be fetched or reconciled from peer replicas.

### 7.2. Running Anti-Entropy Repair in the Lab

Once all three nodes are healthy with no conflicting maintenance jobs, try:

~~~bash
# Run on an eligible lab node; adjust for version/topology.
nodetool repair -full replication_lab sync_probe
~~~

This command can consume CPU, disk I/O, network, and time. Record start/end times, exit status, log errors, and which ranges and replicas the repair session covered. Depending on version, `-full` requests a full repair; on large clusters, running one command on one node **does not prove** the entire cluster/table across all token ranges was repaired. A full-coverage workflow is needed.

**A scoped successful repair is stronger evidence than "node UN"**, yet still cannot verify an event ever existed if all replicas missed it.

### 7.3. Verification Reads with Explicit Keys

In `cqlsh`:

~~~text
CONSISTENCY ALL
~~~

~~~sql
SELECT event_id, marker, source_version, payload
FROM replication_lab.sync_probe
WHERE run_id = 'sync-demo-01';
~~~

In a small lab, compare results against the three manifest markers. Reading at `ALL` requires every replica to respond; **if it errors because a node is unavailable, that is an availability/incomplete-read error—never immediately count it as missing**.

**Per-key verification** when a discrepancy is suspected:

~~~sql
SELECT marker, source_version, payload
FROM replication_lab.sync_probe
WHERE run_id = 'sync-demo-01'
  AND event_id = 22222222-2222-4222-8222-222222222222;
~~~

If `during-outage-B` returns after repair, record **FOUND_MATCH** at the active CL. If no row returns, record **MISSING_AT_SELECTED_CL**. If a row returns with a different marker, record **MISMATCH** and investigate overwrites/timestamps. Timeouts or `Unavailable` must be recorded as **READ_ERROR**, **never** counted as "MISSING".

Even an `ALL` read can reconcile data across replicas; it does not give an independent physical snapshot of each node. If strict evidence of **each replica's SSTable/memtable state** is needed, use version-appropriate diagnostic procedures or local storage inspection tools alongside repair monitoring. Do not treat CQL as a definitive per-replica physical audit.

### 7.4. Progress Log

| Milestone | Nodes | Hints / Repair | Read CL | Result | Conclusion |
| --- | --- | --- | --- | --- | --- |
| T0: before fault | 3 `UN` | Not needed yet | `ALL` | A matches | Baseline |
| T1: R3 down | 2 `UN`, 1 `DN` | Hints may be stored | `LOCAL_QUORUM` | A, B match | B has quorum ACK |
| T2: R3 up | 3 `UN` | Hints may be draining | `LOCAL_QUORUM` | A, B match | Not yet proof R3 synced |
| T3: repair done | 3 `UN` | Repair session succeeded | `ALL` | A, B, C match | Convergence criteria met within verified scope |

Never fill in "match" unless actually measured in the lab. Each row must store **observed values**, timestamps, CL, error status, and repair session info. If anomalies remain when the check window ends, report **INCOMPLETE/UNKNOWN** along with unverified keys/ranges.

## 8. Detecting Missing Records Using an Expected Source

The distinction between **convergence** and **completeness** is crucial:

- **Replica convergence:** replicas share the same logical state across the repaired/verified scope.
- **Business completeness:** all mandatory business events exist in the storage system.

If an event `D` was lost **before any replica accepted it** or before reaching a trusted source, repair cannot regenerate D. Replicas can be 100% identical while **all missing D**.

To detect missing data, you need an external expected set (e.g., an event log with `event_id`, acknowledged request list, trusted source snapshot, or outbox). Reconcile:

~~~text
expected = {A, B, C, D}
actual   = {A, B, C}
missing  = expected - actual = {D}
extra    = actual - expected = {}
~~~

On large Cassandra tables, avoid full-table `SELECT COUNT(*)` or scanning every partition per check. Use stable `event_id` values, bucket by `run_id`/time, and **query with explicit partition keys**. At high event volumes, export per-bucket checksums/counts from a trusted pipeline and drill into mismatched buckets. Matching checksums/counts are a positive signal, though **not sole proof** that two sets have identical elements without an appropriate verification design.

| Symptom | Likely Cause | Next Step |
| --- | --- | --- |
| Previously ACKed marker missing at quorum | Wrong keyspace/partition, delete/TTL/overwrite, failed node, unsynced data | Inspect manifest and mutation history, CL/RF, logs, and repair |
| Marker visible only under certain reads | Divergent replicas, differing routing and CLs | Inspect endpoints, traces/logs/metrics; run scoped repair |
| `nodetool status` all `UN`, yet pending hints remain high | Node is up but mutation replay has not finished | Watch delivery, errors, and hint windows; consider repair |
| Repair reports complete, yet source events still missing | Event never reached Cassandra, was deleted, or fell outside repair scope | Reconcile source/outbox; run controlled backfill |
| Deleted row reappears | Stale tombstone, long-offline replica, newer timestamp, bad restore | Investigate `gc_grace_seconds`, repair history, and writer sources before fixing |
| Read timeouts during streaming/repair | Overload or insufficient replicas to meet CL | Record READ_ERROR, throttle/recover, and retry; never count as missing |

## 9. Writing and Reconciling in Java Driver 4.x

The example below uses **Java Driver 4.x** and the keyspace/table created earlier. Writing fixed markers and verifying them are two separate operations; **the client call's ACK** determines what is recorded as acknowledged.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.util.UUID;

public final class ReplicaConvergenceProbe {
    private final CqlSession session;
    private final PreparedStatement insert;
    private final PreparedStatement read;

    public enum WriteResult { ACKNOWLEDGED, UNKNOWN }
    public enum CheckResult { FOUND_MATCH, MISSING, MISMATCH, READ_ERROR }

    public ReplicaConvergenceProbe(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO replication_lab.sync_probe " +
            "(run_id, event_id, marker, source_version, payload) " +
            "VALUES (?, ?, ?, ?, ?)");
        this.read = session.prepare(
            "SELECT marker, source_version, payload " +
            "FROM replication_lab.sync_probe " +
            "WHERE run_id = ? AND event_id = ?");
    }

    public WriteResult insertAtQuorum(
            String runId, UUID eventId, String marker, String payload) {
        BoundStatement statement = insert.bind(
                runId, eventId, marker, 1, payload)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotence(false);
        try {
            session.execute(statement);
            System.out.printf("WRITE_ACK run=%s event=%s%n", runId, eventId);
            return WriteResult.ACKNOWLEDGED;
        } catch (RuntimeException error) {
            System.err.printf("WRITE_UNKNOWN run=%s event=%s cause=%s%n",
                runId, eventId, error.getClass().getSimpleName());
            return WriteResult.UNKNOWN;
        }
    }

    public CheckResult checkAtAll(
            String runId, UUID eventId, String expectedMarker) {
        BoundStatement statement = read.bind(runId, eventId)
            .setConsistencyLevel(DefaultConsistencyLevel.ALL);
        try {
            Row row = session.execute(statement).one();
            if (row == null) {
                return CheckResult.MISSING;
            }
            return expectedMarker.equals(row.getString("marker"))
                ? CheckResult.FOUND_MATCH
                : CheckResult.MISMATCH;
        } catch (RuntimeException error) {
            System.err.printf("READ_ERROR run=%s event=%s cause=%s%n",
                runId, eventId, error.getClass().getSimpleName());
            return CheckResult.READ_ERROR;
        }
    }
}
~~~

Principles illustrated by this code:

- `PreparedStatement` and `CqlSession` are reused; parameterization avoids concatenating user input into CQL strings.
- `eventId/marker` data must remain **stable** across writes/checks; use a fresh `runId` per lab run.
- When a write receives no ACK, the outcome is `UNKNOWN`, not "definitely unwritten"; careless retries can overwrite data if reusing the same key with different payloads/timestamps.
- `ALL` succeeds only when enough replicas respond; never roll `READ_ERROR` into `MISSING` when tallying counts.
- `FOUND_MATCH` means the row read at `ALL` carries the expected marker—it **does not prove** local storage on every individual node is identical.
- Callers must persist an **expected event manifest** outside the probed table alongside CL, timestamps, ACK/UNKNOWN state, restart/repair times, and error codes to compare across checks.

In real systems, classify `Unavailable`, read timeouts, write timeouts, connection errors, and query/schema errors distinctly. Swallowing every exception as "data loss" is semantically wrong and triggers uncontrolled retries.

## 10. Operating Safe Convergence in Multi-Node Environments

### Monitoring Over Time

Post-recovery checks should sample multiple milestones: when the node first becomes `UN`, as hints drain, during streaming/repair, and once reconciliation stabilizes. Record application latency too: streaming and compaction can push p95/p99 up even as data converges.

### Ensuring Repair Actually Covers Scope

In clusters with many token ranges and multiple DCs, schedule repairs so **every required range and replica** is checked at an appropriate cadence. Full/incremental repair, session outcomes, and completion semantics depend on version/flags; never equate "command succeeded on one node" with "the entire system is synchronized."

### Watch TTLs, Tombstones, and Long-Offline Nodes

If a table uses TTLs or `DELETE`, **tombstones are data that must propagate**, not just live rows. For long-offline nodes—especially past grace where tombstones may have been purged—evaluate zombie risk before letting the stale node rejoin. Replace/rebuild from healthy replicas or restore from trusted sources may be required; never delete SSTables manually.

### Do Not Confuse Compaction with Repair

Compaction merges SSTables **on a single node** and reclaims eligible old data/tombstones; repair compares data **across replicas**. Repair can trigger streaming and new SSTables, leading to compaction, yet the two tasks are not the same. Replication factor and consistency levels govern placement and ACKs, and **do not guarantee instant convergence** after downtime.

### When Is Backfill Needed Instead of Repair?

If reconciliation discovers an `event_id` present in the business source yet **absent on every replica**, turn to a recovery source: durable event logs, outboxes, backups, or upstream systems. Backfills must preserve stable IDs and avoid overwriting newer updates. If idempotency or state transitions are required, use conditional writes/LWT designed around business rules.

## 11. Practice Exercises and Self-Check Questions

**Exercise 1 — Predict before testing.** With RF=3 in one DC, write A at `ALL`, stop R3, then write B at `LOCAL_QUORUM`. Identify which replicas definitely ACKed B once the client gets success. Why can you not conclude B is on R3 the moment R3 turns `UN`?

**Exercise 2 — Record a progress manifest.** Run the lab, logging `T_down`, `T_write_ack`, `T_up`, `T_hints_drained` (if metrics exist), `T_repair_done`, and `T_verified`. Add an `UNKNOWN` state on write timeout. Explain why pending hints reaching 0 is insufficient as a completion criterion.

**Exercise 3 — Separate read results from per-replica storage.** Connect `cqlsh` to R3 and read B at `ALL`. The output returns marker B. What has been proven? What has **not** been proven about R3's own SSTables/memtables?

**Exercise 4 — Missing event.** The source manifest lists A, B, C, and D, yet Cassandra returns only A, B, and C. Repair succeeded over the lab scope. What steps determine whether D was never written, is missing on a replica, expired via TTL, or lies outside the query scope?

**Exercise 5 — Deletions and prolonged outages.** A replica stayed offline longer than `gc_grace_seconds`, likely missed `DELETE`s, and tombstones on peer replicas were purged. Why isn't running repair right away always safe? Outline an assessment, rebuild, and reconciliation workflow.

**Exercise 6 — Java and false positives.** Modify the code to count `FOUND_MATCH`, `MISSING`, `MISMATCH`, and `READ_ERROR` separately while bounding total concurrent requests. Why does folding `READ_ERROR` into `MISSING` make dashboards falsely report data loss?

## Takeaways

**Replica convergence is an observable, scope-bound verification process—not a state guaranteed simply because nodes show `UN`.** Use RF/CL to reason about ACKs and read paths, track hints/repair/streaming, reconcile known keys against an external manifest, and clearly separate missing reads from read errors. Repair synchronizes data **still present on replicas**, while proving zero missing business events requires an expected source and backfill plans when needed.
