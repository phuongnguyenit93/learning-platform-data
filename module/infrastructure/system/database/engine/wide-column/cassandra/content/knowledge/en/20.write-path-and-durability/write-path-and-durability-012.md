# Node-Stop Experiment and Verifying Acknowledged Data

## 1. Objective: What Does "Write Succeeded" Actually Mean?

In Apache Cassandra, an `INSERT` or `UPDATE` statement may be sent to a **coordinator** and distributed to multiple **replicas** by *partition key*. When the client receives a success response, the critical question is not just "did the command run," but also:

- How many replicas acknowledged the write per the **write consistency level**?
- Does the data sit in the **commit log**, **memtable**, or has it flushed into an **SSTable**?
- If one node stops abruptly right after replying, can **the remaining copies** serve read queries?
- When the node restarts, how is data recovered via commit log replay and synchronized across replicas?
- What can be proven from a single successful `SELECT`, and what **cannot** be inferred?

This lesson belongs to the **Write Path and Durability** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. It brings together distributed architecture, the wide-column model, partition keys, query-driven table design, replication, consistency levels, CQL, compaction, repair, error handling, and Java connectivity.

**Hands-on goal:** on a **three-node same-datacenter** Cassandra cluster, create data with an identifying marker, mark rows as "acknowledged" only when the client truly receives success, stop one node, query again under different consistency levels, restart the node, and analyze what you observe. This experiment tests **guarantee boundaries**—it does not claim a single passing trial proves the system can never lose data.

> **Safety scope:** perform node stop/start operations strictly in a **lab or disposable test environment**, never on a production cluster. Docker commands shown here are examples only; container names, datacenter names, and configs must match your lab infrastructure.

## 2. Write Path Model and ACK Conditions

Suppose three replicas of a partition reside on three nodes in one datacenter. Simplified write path:

~~~mermaid
sequenceDiagram
    participant Client as Client / Java
    participant C as Coordinator
    participant R1 as Replica 1
    participant R2 as Replica 2
    participant R3 as Replica 3
    Client->>C: INSERT (CL = LOCAL_QUORUM)
    par Send to replicas
        C->>R1: Mutation
        C->>R2: Mutation
        C->>R3: Mutation
    end
    Note over R1,R3: Replicas process commit log and memtable
    R1-->>C: ACK
    R2-->>C: ACK
    C-->>Client: Success (2/3 ACKs met)
    R3-->>C: ACK (may arrive later)
~~~

The coordinator **does not necessarily wait for every replica**; how many ACKs it awaits depends on the write consistency level. Upon processing a mutation, a replica writes to the **commit log** (for recovery after process stops) and updates the in-memory **memtable**. Later, memtables flush to **SSTables** on disk, and compaction reorganizes SSTables in the background.

~~~mermaid
flowchart LR
    W["Mutation arrives at replica"] --> C["Append commit log"]
    C --> M["Update memtable"]
    M --> A["ACK per write path"]
    M --> F["Flush when needed"]
    F --> S["SSTable on disk"]
    S --> K["Compaction in background"]
    R["Node restarts"] --> P["Replay valid commit log"]
    P --> M
~~~

**Distinguish ACKs from SSTable flushes:** Cassandra does not wait for each mutation to become an SSTable before replying. The commit log supports recovering unflushed writes. However, **appended to the commit log** and **fsynced to the storage device** are two distinct milestones:

| Configuration / aspect | Significance for the experiment |
| --- | --- |
| Keyspace `durable_writes = true` | Enables commit log recovery for unflushed writes; keep this enabled in durability labs. |
| Commit-log sync **periodic** | Writes may be ACKed before the commit log is durably synced to disk; creates a risk window on machine or storage power loss. |
| Commit-log sync **batch** | ACK path waits for commit log sync per batch policy, typically raising write cost/latency. |
| Memtable / SSTable | Nodes can recover data from the commit log when memtables are unflushed; SSTables are not a prerequisite per ACK. |
| Other replicas | RF and consistency level determine how many copies responded; this differs from **per-copy on-disk** durability. |

Sync options and defaults can differ across Cassandra versions/configurations. Before interpreting results related to **power loss / disk loss**, check the cluster's actual commit log configuration. **Killing a process** also does not fully simulate host power loss and wiped OS/storage-device caches.

## 3. Pre-Run Predictions: RF and Consistency Level

Suppose the keyspace has **RF = 3** in the active datacenter and all three nodes hold replicas for the test partition.

| Write CL | Required ACKs at RF=3, single DC | If success received before one node stops |
| --- | --- | --- |
| `ONE` | At least **1** replica ACK | Does not prove the remaining two replicas received the mutation. |
| `LOCAL_QUORUM` | At least **2** local-DC replica ACKs | After one node stops, at least one ACKed copy sits on the surviving nodes, assuming only one replica failed and no additional faults occurred. |
| `ALL` | **3** replica ACKs | Requires all three nodes to respond on write; `ALL` writes become unavailable if any replica cannot reply. |

With `RF = 3`, `W = 2`, and `R = 2`, we have `W + R = 4 > RF = 3`. The two quorum replica sets **must intersect** on at least one replica. Absent concurrent writes, deletes, storage errors, or anomalous configs, a write ACKed at `LOCAL_QUORUM` can be read at `LOCAL_QUORUM` after losing one replica, provided the remaining two replicas stay available.

**Inferences to avoid:**

- `ONE` succeeding **does not mean** data is guaranteed lost when a node stops. On a healthy network, the coordinator usually sends mutations to all three replicas; peer replicas may have received it. What the experiment demonstrates is a **weaker guarantee**, not mandatory data loss.
- `LOCAL_QUORUM` guarantees a quorum ACK count; it **does not promise every replica updated**, nor does it replace backups/recovery after multi-node or storage loss.
- `ALL` merely demands a larger acknowledgment count; it reduces write availability during node failures without making applications immune to disk failures, deletes, or duplicate requests.
- If the client receives a **timeout**, never record it as "definitely failed": some replicas may have applied the mutation even though the coordinator failed to return success. Mark **ACK succeeded** only when the client genuinely receives a success outcome.

Across multiple datacenters, `LOCAL_QUORUM` computes quorum only within the local datacenter, unlike `QUORUM` which counts across total topology replication. Never reuse the single-DC ACK table above for a multi-DC configuration without recalculating per-DC RF.

## 4. Setting Up the Three-Node Lab

### 4.1. Prerequisites and Baseline

Prepare a Cassandra cluster with at least **three nodes in one datacenter**, using containers or VMs. You need `cqlsh` access to a live node and `nodetool` access on the nodes. The examples below assume nodes/containers named `cass-1`, `cass-2`, `cass-3`, and a datacenter named `datacenter1`.

Check status before starting:

~~~bash
# Run on hosts/containers with matching nodetool access.
nodetool status
~~~

Expect all three nodes to be `UN` (*Up/Normal*) in the same datacenter; do not proceed if the cluster is bootstrapping, moving tokens, running heavy repair, or has unexpected down nodes. In `cqlsh`:

~~~sql
SELECT release_version, data_center, host_id FROM system.local;
~~~

Note the actual `data_center`. If it differs from `datacenter1`, substitute it into the keyspace creation command below. In mixed-upgrade environments, record each node's version to avoid behavior/config confusion.

### 4.2. Keyspace with Explicit Replication

~~~sql
CREATE KEYSPACE IF NOT EXISTS durability_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 3
}
AND durable_writes = true;

USE durability_lab;
~~~

`NetworkTopologyStrategy` is appropriate for per-datacenter replication. If your DC name differs from `datacenter1`, update the CQL accordingly. `IF NOT EXISTS` **does not alter an existing keyspace's configuration**; if the keyspace remains from an earlier lab, verify replication and `durable_writes` rather than assuming they match:

~~~sql
SELECT keyspace_name, replication, durable_writes
FROM system_schema.keyspaces
WHERE keyspace_name = 'durability_lab';
~~~

**Never use RF=1** for an experiment testing write quorums. If you have three nodes total yet a partition lacks three local-DC replicas, Section 3's assumptions no longer apply.

### 4.3. Immutable Probe Table

~~~sql
CREATE TABLE IF NOT EXISTS ack_probe (
    run_id text,
    seq int,
    marker uuid,
    payload text,
    written_at timestamp,
    PRIMARY KEY ((run_id), seq)
);
~~~

`run_id` is the **partition key**, and `seq` is the clustering key. Use a fresh `run_id` for each trial; write each `seq` once per run to avoid overwriting earlier results accidentally. `marker` is a fixed UUID tied to the test event, allowing exact data verification after recovery. Do not enable TTLs, use counters, or introduce concurrent writes in this first experiment, as they complicate reasoning about ACKed data.

Before testing, confirm you have permission to stop a node and a reliable way to start it back up. Record the start time, version, RF, CL, datacenter, target node name, and initial cluster state.

## 5. Experiment A: Successful Writes While All Three Nodes Run

In `cqlsh` connected to a live node:

~~~sql
USE durability_lab;
~~~

The `CONSISTENCY` directive below is a **`cqlsh` command**, not a CQL statement. Use it to set the CL for subsequent statements.

~~~text
CONSISTENCY ONE
~~~

~~~sql
INSERT INTO ack_probe (run_id, seq, marker, payload, written_at)
VALUES (
    'trial-a-20261121', 1,
    11111111-1111-4111-8111-111111111111,
    'ack-one', toTimestamp(now())
);
~~~

If `cqlsh` confirms the command **with no error**, log **ACK at ONE**. Continue:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
INSERT INTO ack_probe (run_id, seq, marker, payload, written_at)
VALUES (
    'trial-a-20261121', 2,
    22222222-2222-4222-8222-222222222222,
    'ack-local-quorum', toTimestamp(now())
);
~~~

~~~text
CONSISTENCY ALL
~~~

~~~sql
INSERT INTO ack_probe (run_id, seq, marker, payload, written_at)
VALUES (
    'trial-a-20261121', 3,
    33333333-3333-4333-8333-333333333333,
    'ack-all', toTimestamp(now())
);
~~~

Read back while the cluster still has all nodes:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
SELECT seq, marker, payload, written_at
FROM ack_probe
WHERE run_id = 'trial-a-20261121';
~~~

Expected output shows three rows with matching `marker` and `payload`. **Mark a row as "ACK succeeded" only if its corresponding INSERT itself returned success.** If a command timed out or errored, record `UNKNOWN` and never treat a subsequent `SELECT` as proof that the client received an ACK.

### Result Log to Record

| run_id/seq | Write CL | Client received | Expected marker | Notes |
| --- | --- | --- | --- | --- |
| `trial-a-20261121 / 1` | `ONE` | ACK / TIMEOUT / ERROR | `1111…1111` | Record timestamp and connected node |
| `trial-a-20261121 / 2` | `LOCAL_QUORUM` | ACK / TIMEOUT / ERROR | `2222…2222` | Mark ACK only on success |
| `trial-a-20261121 / 3` | `ALL` | ACK / TIMEOUT / ERROR | `3333…3333` | Verify all three replicas are available |

This serves as the baseline for comparison **after stopping a node**. Use a new `run_id` if re-running the entire lab, since inserting into the same key with a newer timestamp masks prior trial data.

## 6. Experiment B: Abruptly Stop One Node, Read from Remaining Two

Assume Experiment A's writes are complete. Stop `cass-3` **without intentionally draining/flushing**:

~~~bash
# Example when running the lab in Docker. Substitute actual container name.
docker kill --signal=KILL cass-3
~~~

On VMs, the equivalent is abruptly killing the Cassandra process in the **lab** without a graceful shutdown. `SIGKILL`'s impact on a **process** differs from physical power loss and wiped storage caches; never claim this measures pre-outage fsync durability.

**Do not run `nodetool drain` before stopping** if the goal is testing recovery of unflushed writes: draining flushes memtables to SSTables and turns the test into a controlled shutdown. `docker stop` typically sends a graceful signal before force-killing after a timeout, so it is also not strictly equivalent to `docker kill`.

On `cass-1` or `cass-2`:

~~~bash
nodetool status
~~~

Wait for the cluster to mark `cass-3` as down; **two `UN` nodes** remain in the local DC. Connect `cqlsh` to **one of the two surviving nodes** and run:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
SELECT seq, marker, payload
FROM durability_lab.ack_probe
WHERE run_id = 'trial-a-20261121';
~~~

With RF=3, one node stopped, two nodes healthy, and Experiment A's `LOCAL_QUORUM`/`ALL` writes **ACKed**, expect to see at least rows `seq=2` and `seq=3`. Row `seq=1` (ACKed at `ONE`) **may also appear** because peer copies received the mutation; if it does, never conclude `ONE` provides the same guarantee as quorum.

### Analytical Readout

| Row | Guarantee from pre-stop ACK | Observation to record |
| --- | --- | --- |
| `seq=1` written at `ONE` | Only one replica guaranteed to have acknowledged | Present/absent; do not generalize from one trial |
| `seq=2` written at `LOCAL_QUORUM` | Two replicas acknowledged | Expected readable at `LOCAL_QUORUM` with one node down |
| `seq=3` written at `ALL` | All three replicas acknowledged | Expected readable at `LOCAL_QUORUM` across two surviving nodes |

If an ACKed `LOCAL_QUORUM`/**ALL** row cannot be read, **do not jump to concluding Cassandra lost data**. Verify the ACK truly succeeded, the right keyspace/`run_id` was queried, RF/DC settings, live replica count, read timeouts, node errors, concurrent writes/deletes, and lab config. Gather logs/traces before drawing conclusions on unexpected results.

## 7. Experiment C: Writing While One Node Is Down

Keep `cass-3` down temporarily. In `cqlsh` connected to a live node, write a **new** row at `LOCAL_QUORUM`:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
INSERT INTO durability_lab.ack_probe
    (run_id, seq, marker, payload, written_at)
VALUES (
    'trial-b-20261121', 1,
    44444444-4444-4444-8444-444444444444,
    'two-replicas-ack', toTimestamp(now())
);
~~~

If both surviving replicas respond successfully, `LOCAL_QUORUM` reaches **2/3** and can return an ACK. Read it back at `LOCAL_QUORUM`:

~~~sql
SELECT marker, payload
FROM durability_lab.ack_probe
WHERE run_id = 'trial-b-20261121' AND seq = 1;
~~~

Next, **switch to `ALL`** and use a new key without overwriting the row just created:

~~~text
CONSISTENCY ALL
~~~

~~~sql
INSERT INTO durability_lab.ack_probe
    (run_id, seq, marker, payload, written_at)
VALUES (
    'trial-b-20261121', 2,
    55555555-5555-4555-8555-555555555555,
    'all-while-node-down', toTimestamp(now())
);
~~~

Since one replica cannot acknowledge, **do not expect the `ALL` write to ACK successfully**. The client may receive `Unavailable` or a timeout error depending on when the coordinator detects the down node and runtime conditions.

**Critical point:** an `INSERT` at `ALL` failing to receive an ACK **does not prove** the mutation was unapplied on the surviving replicas. If you later read `seq=2`, that does not contradict the earlier client error: live replicas may have applied it while the request failed to satisfy the required consistency level. Therefore, never use this outcome for business counting like "client error means 0 executions."

Do not repeat `ALL` on the same key trying to "make it succeed." Every trial needs a distinct marker, timestamped log, and clear evaluation rule.

## 8. Restarting the Node and Verifying

Restart `cass-3`:

~~~bash
# Applies only when using Docker with the example container name.
docker start cass-3
~~~

Check status:

~~~bash
nodetool status
~~~

Wait for all three nodes to return to `UN`. During startup, Cassandra can **replay the commit log** to recover mutations logged but not flushed to SSTables before the process died. The temporarily stopped replica may also receive missed writes via **hints** if conditions and hint retention windows permit; **repair** is the proactive mechanism to reconcile data across replicas. Never assume hints are always present, enabled, or sufficient to cover every outage.

Read from a live coordinator:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
SELECT seq, marker, payload
FROM durability_lab.ack_probe
WHERE run_id = 'trial-a-20261121';

SELECT seq, marker, payload
FROM durability_lab.ack_probe
WHERE run_id = 'trial-b-20261121';
~~~

**Distinguish three conclusions:**

1. `SELECT` returning `marker` strictly means **the read query at the chosen CL returned that data**.
2. It **does not automatically prove** replica `cass-3` holds a complete up-to-date copy, because the coordinator may have read from peer replicas.
3. A previously un-ACKed write appearing later **does not retroactively turn it into an ACKed write** at the original call time.

In a small lab, run a **controlled repair** after the node returns to resynchronize data:

~~~bash
# Run on an appropriate lab node; production clusters require a planned repair schedule.
nodetool repair durability_lab ack_probe
~~~

Repair can consume substantial CPU, I/O, and time on large datasets; never run it casually in production. `UN` status and a single `SELECT` result do not prove all replicas are synchronized—combine logs/metrics, repair status, and topology checks when evaluating.

### Final Experiment Report

| Step | What must be recorded |
| --- | --- |
| Before writing | Cassandra version; DC; RF; `UN` node count; commit log config |
| After each write | `run_id`, `seq`, `marker`, CL, timestamp, **actual ACK/timeout/error received** |
| After `SIGKILL` | Stopped node; timestamp; `nodetool status`; read CL; observed rows/markers |
| With two nodes up | `LOCAL_QUORUM` ACKs; `ALL` errors; whether un-ACKed write was later readable |
| After restart | `UN` status, read results per CL, recovery logs, repair run if executed |
| Conclusion | Distinguish **theoretical guarantees**, **observed results**, and **test limitations** |

## 9. Java Connectivity: Recording ACKs and Handling Unknown Outcomes

In Java applications using **Apache Cassandra Java Driver 4.x**, audit accuracy depends on **recording the outcome of the client call**, not guessing earlier ACKs from later reads. Minimal example:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.Instant;
import java.util.UUID;

public final class DurabilityProbe {
    private final CqlSession session;
    private final PreparedStatement insert;
    private final PreparedStatement select;

    public DurabilityProbe(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO durability_lab.ack_probe " +
            "(run_id, seq, marker, payload, written_at) " +
            "VALUES (?, ?, ?, ?, ?)");
        this.select = session.prepare(
            "SELECT marker, payload FROM durability_lab.ack_probe " +
            "WHERE run_id = ? AND seq = ?");
    }

    public boolean writeAndObserveAck(
            String runId, int seq, UUID marker, String payload) {
        BoundStatement statement = insert.bind(
                runId, seq, marker, payload, Instant.now())
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotence(false);

        try {
            // Normal return: client received success response at requested CL.
            session.execute(statement);
            System.out.printf(
                "ACK run=%s seq=%d marker=%s CL=LOCAL_QUORUM%n",
                runId, seq, marker);
            return true;
        } catch (RuntimeException error) {
            // Client error/timeout: do not infer the mutation definitely did not write.
            System.err.printf(
                "UNKNOWN run=%s seq=%d marker=%s error=%s%n",
                runId, seq, marker, error.getClass().getSimpleName());
            return false;
        }
    }

    public void verify(String runId, int seq) {
        Row row = session.execute(select.bind(runId, seq)
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM))
            .one();
        if (row == null) {
            System.out.println("NOT OBSERVED at LOCAL_QUORUM");
        } else {
            System.out.printf("OBSERVED marker=%s payload=%s%n",
                row.getUuid("marker"), row.getString("payload"));
        }
    }
}
~~~

**How to read this code:**

- `writeAndObserveAck` prints `ACK` only after `session.execute` returns normally. If an exception is caught, it logs `UNKNOWN`; production logging should classify exact exception types to distinguish failure modes.
- `runId + seq + marker` must remain stable across a trial. Resending with a new key creates **a new event**, rather than retrying recovery of the same write.
- `setIdempotence(false)` is a **conservative choice for this experiment** to keep the client from automatically replaying requests as if every error meant "not written." For plain `INSERT`s with fixed values and no side effects, production apps can design explicit idempotent retry policies after accounting for conflicts, timestamps, and TTLs.
- `verify` only logs `OBSERVED`; it **does not prove a prior ACK** and does not prove a specific replica is synchronized.
- The snippet returns `false` on any runtime exception to signal "no ACK proof"; production systems must **classify exceptions**, retain logs/traces, avoid masking config errors, and handle retry/reconciliation decisions in the business layer.

Experiment logs should be stored outside the cluster under fault, such as application logs or monitoring systems. If ACK logs lived only on the stopped node, the experimenter would lose reliable evidence of when the client received success.

## 10. Interpretation Mistakes to Avoid

| Inaccurate claim | Accurate understanding |
| --- | --- |
| "`INSERT` returned success, so all replicas hold the data." | Only enough replicas ACKed per write CL; only `ALL` requires every chosen replica. |
| "ACK means the data flushed to SSTables." | Commit log and memtable serve the write path; SSTable flushing runs later. |
| "`ONE` definitely loses data if one node dies." | There is no quorum guarantee; often peer replicas still received it and can serve reads. |
| "`LOCAL_QUORUM` can never lose data under any outage." | Risks remain on multi-copy loss, storage faults, power loss, sync config, or concurrent writes/deletes. |
| "Timeout means the write failed and can always be resent safely." | State may be **unknown**; retries must evaluate idempotency and business semantics. |
| "Seeing the row after the node comes back proves that node holds a copy." | The coordinator may have read from peer nodes; check/reconcile replicas or run repair. |
| "`nodetool drain` tests crashing with unflushed writes." | Drain is a controlled stop that flushes memtables. |
| "`SIGKILL` proves power-loss durability." | It only kills the process; OS/disk caches may survive. |
| "Repair recovers all lost data." | Repair reconciles surviving data across replicas; it cannot regenerate data lost on **all** copies. |
| "Raising read CL to `ALL` is always better." | `ALL` reduces availability when nodes fail; match CL to requirements and actual RF. |

## 11. Extended Exercises

### Exercise 1 — Comparing ACKs Against Observed Data

Run Experiments A through C, recording `seq`, `marker`, write CL, read CL, node states, and responses. Mark "ACKed" only when **the client received success**. Explain why `seq=1` written at `ONE` can still appear after a node goes down, and why observing it must not be used to elevate `ONE` to quorum-level guarantees.

### Exercise 2 — W+R > RF Scenarios

With RF=3 in one DC, compute `W+R` for:

- `W=1, R=1`: does not guarantee replica-set overlap.
- `W=2, R=2`: sum is 4 > 3; guaranteed overlap.
- `W=3, R=1`: sum is 4 > 3; overlaps if read/write operations have enough live replicas to respond.

Discuss **availability** when one node goes down: `W=3` cannot succeed, whereas `W=2` can succeed if the remaining two replicas are healthy. Set intersection is only one piece of consistency; also account for concurrent updates, tombstones, timeouts, and topology.

### Exercise 3 — Power Loss vs. SIGKILL

Build a prediction table for `periodic` vs. `batch` commit-log sync modes. Distinguish:

1. Cassandra process dies while host/OS and storage caches keep running.
2. Entire host loses power immediately after ACK.
3. Two of three nodes become unreachable simultaneously.

Never turn predictions into absolute guarantees without verifying actual config, storage hardware, and fsync behavior.

### Exercise 4 — What Must Be Investigated in a Real Outage?

Suppose `LOCAL_QUORUM` returned an ACK, yet a `SELECT` after one node goes down times out. Check **read consistency**, live replica count and DC mapping, node/coordinator logs, connection status, tombstones, timeouts, and concurrent writes/deletes before suspecting data loss. Write an evidence-based recovery checklist and specify when repair is required.

### Exercise 5 — Applying Principles to a Java API

Design an API returning `ACKNOWLEDGED`, `NOT_ACKNOWLEDGED` (only with clear proof), and `UNKNOWN`; persist a stable `operation_id` for business logic. Explain why reading the row after a timeout does not prove the **preceding client call** received an ACK, and why counter increments or external side effects cannot be retried arbitrarily.

## Key Takeaways

**A write ACK in Cassandra confirms that enough replicas responded per the chosen consistency level; it does not automatically mean every replica updated or every byte was fsynced.** To verify, log actual ACKs received, use data with stable markers, stop one node cleanly in a lab, read at defined CLs, restart, and observe recovery/repair. Comparing `ONE`, `LOCAL_QUORUM`, and `ALL` at RF=3 reveals the trade-offs among guaranteed consistency, failure-specific durability, and availability when a node is down.
