# Partial Failure Lab and Reconciling Multi-Record Write Outcomes

**Chapter:** BATCH and counters  
**Scope:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`

This lesson covers: *Understanding Apache Cassandra's distributed architecture and wide-column model, especially partition keys, query-driven table design, and read/write consistency levels. Practicing CQL, replication, compaction, repair, error handling, and connecting from Java applications.*

A business operation often needs to write multiple records, such as saving an order's state, a query-serving denormalized copy, and an audit trail. In Cassandra, these rows may reside across **multiple partitions**; each partition in turn has **multiple replicas**. When a node or connection fails, two kinds of "missing" are easily confused: a missing row among the write group and a missing latest version on one replica. This lab demonstrates how to reproduce failure scenarios, observe outcomes across consistency levels, and decide whether resending a command is permitted.

## 1. Objectives and Observation Model

After this lesson, you will be able to:

1. Explain why a multi-partition `BATCH` is not equivalent to an ACID transaction in a relational database.
2. Distinguish `LOGGED BATCH`, `UNLOGGED BATCH`, and `COUNTER BATCH` under failures, especially after timeouts.
3. Use specific query keys to reconcile **each row** of a write attempt, avoiding conclusions drawn from imprecise aggregate queries.
4. Recognize the difference between client responses, data read at `ONE`/`LOCAL_QUORUM`/`ALL`, and replica state.
5. Design safe retry/reconciliation for regular writes while avoiding double-counting counters.

**Two axes to verify independently:**

| Axis | Question | Example |
| --- | --- | --- |
| Multiple **logical records** | Have rows A, B, and C across three partitions all been written? | A present, B present, C missing after mid-execution failure. |
| Multiple **physical replicas** | For the same row A, which replicas received the latest version? | Two replicas have the new A, the third replica temporarily holds the old A. |

The coordinator is the node that receives the request and orchestrates execution; it is not necessarily a replica holding the key. Connecting `cqlsh` to a node does **not** mean reading data directly from that node's disk.

## 2. Actual Guarantees of Batch Types

| Write Method | Mechanism on Failure | What Must **Not** Be Inferred |
| --- | --- | --- |
| `BEGIN BATCH` (logged, default) across multiple partitions | Cassandra writes a **batchlog** before dispatching mutations; if the batchlog is persisted successfully, missing mutations can be replayed to complete eventually. | No cross-partition isolation; no immediate rollback; a timeout does not prove "not written." |
| `BEGIN UNLOGGED BATCH` across multiple partitions | No batchlog guaranteeing group replay. Some mutations may be applied while others fail. | A single `APPLY BATCH` statement does not turn multiple partitions into a transaction. |
| Multiple separate `INSERT`/`UPDATE` statements | Each statement has its own response and failure; the application is responsible for overall business completion state. | Success for A does not guarantee B and C succeeded. |
| `BEGIN COUNTER BATCH` | Groups counter updates under dedicated syntax; increments are **not idempotent**. | Resending after a timeout can add again; counter updates must not be mixed into regular batches. |

**Eventual atomicity is not read-time isolation.** With a multi-partition logged batch, the system works to complete every mutation recorded in the batchlog, yet during the write/replay window, another client can still observe new A and old B. Cassandra does not create a shared snapshot across partitions for your read queries.

**A timeout response means an "unknown" state.** The request might never have reached the coordinator, might have arrived without writing, might have written partially, or might have written completely while the response was lost. Exceptions like `WriteTimeoutException`, `UnavailableException`, or connection errors carry distinct meanings about when the failure occurred; no exception by itself proves all mutations were rolled back. Record both the *error type* and the *attempt count*.

**Consistency levels apply per read/write on replicas.** For example, with RF = 3 in one datacenter: `LOCAL_QUORUM` requires two replicas in that datacenter to respond; `ALL` requires all three; `ONE` requires only one. This consistency level does not replace the batchlog and does not create isolation across multiple partitions. For two read/write operations on the same key without concurrent writes, quorum reads and quorum writes help avoid reading a stale replica; do not extrapolate that into a linearizable transaction across the entire batch.

## 3. Environment and Measurements

Use a **dedicated test cluster** of three Cassandra nodes in the same datacenter, e.g., `datacenter1`. The node-stopping commands below are intended strictly for this lab cluster. Cassandra 4.1/5.x and `cqlsh` fit this lab; verify actual datacenter and container names before running.

```bash
# Example container names: cassandra1, cassandra2, cassandra3
docker exec cassandra1 nodetool status
docker exec -it cassandra1 cqlsh
```

In `cqlsh`:

```sql
SELECT data_center, release_version FROM system.local;
```

Only proceed when all three nodes show `UN` status in `nodetool status`. Replace `datacenter1` in the `CREATE KEYSPACE` statements if your actual output differs. Avoid testing on a cluster carrying real traffic, as node restarts, counter creation, and repairs can affect other data.

Create two separate keyspaces to isolate **per-partition failures** from **replica lag**:

```sql
-- RF=1 is used solely to make failures easy to observe in the lab.
CREATE KEYSPACE IF NOT EXISTS lab_batch_r1
WITH replication = {'class': 'NetworkTopologyStrategy', 'datacenter1': 1}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS lab_batch_r1.copies_by_key (
    copy_key text PRIMARY KEY,
    attempt_id text,
    copy_no int,
    payload text
);

-- RF=3 to examine ONE, LOCAL_QUORUM, and ALL within one DC.
CREATE KEYSPACE IF NOT EXISTS lab_batch_r3
WITH replication = {'class': 'NetworkTopologyStrategy', 'datacenter1': 3}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS lab_batch_r3.copies_by_key (
    copy_key text PRIMARY KEY,
    attempt_id text,
    copy_no int,
    payload text
);

CREATE TABLE IF NOT EXISTS lab_batch_r3.counters_by_key (
    counter_key text PRIMARY KEY,
    total counter
);
```

Here `copy_key` is the **partition key**. The three keys `ok12-a`, `ok12-b`, and `ok12-c` are three distinct partitions despite sharing `attempt_id`. The key design is intentionally simple to distribute partitions and read back each row easily. Do not use `SELECT *` to scan the entire table or assume filtering by `attempt_id` is valid.

### Result Recording Template

Before inducing failures, prepare an experiment log table recording timestamps and actual responses:

| Information to Record | Example Value |
| --- | --- |
| `attempt_id`, keys A/B/C | `u12`: `u12-a`, `u12-b`, `u12-c` |
| Batch type, RF, write CL | UNLOGGED, RF=1, ONE |
| Fault and timing | Node holding key C stopped before/during send |
| Client response | success / timeout / unavailable + message |
| Per-key outcome after recovery | A=present, B=present, C=absent |
| Read CL, inspection timing | ONE at t1, LOCAL_QUORUM at t2 (when RF=3) |

The example row only illustrates **how to keep the log**, not a guaranteed outcome of a specific run.

## 4. Control Run: Writing All Three Partitions Without Failure

In `cqlsh`, set `CONSISTENCY ONE` for the RF=1 keyspace:

```sql
CONSISTENCY ONE

BEGIN UNLOGGED BATCH
    INSERT INTO lab_batch_r1.copies_by_key (copy_key, attempt_id, copy_no, payload)
    VALUES ('ok12-a', 'ok12', 1, 'v1');
    INSERT INTO lab_batch_r1.copies_by_key (copy_key, attempt_id, copy_no, payload)
    VALUES ('ok12-b', 'ok12', 2, 'v1');
    INSERT INTO lab_batch_r1.copies_by_key (copy_key, attempt_id, copy_no, payload)
    VALUES ('ok12-c', 'ok12', 3, 'v1');
APPLY BATCH;

SELECT copy_key, attempt_id, payload
FROM lab_batch_r1.copies_by_key WHERE copy_key = 'ok12-a';
SELECT copy_key, attempt_id, payload
FROM lab_batch_r1.copies_by_key WHERE copy_key = 'ok12-b';
SELECT copy_key, attempt_id, payload
FROM lab_batch_r1.copies_by_key WHERE copy_key = 'ok12-c';
```

When `APPLY BATCH` succeeds and all nodes are healthy, all three regular queries see `v1`. This result proves **this specific run** completed; it does not make an unlogged batch atomic against failures.

Try an **intentional application-failure control**: execute two independent statements under `attempt_id = 'control12'`, then simulate the process stopping and skipping the third statement.

```sql
INSERT INTO lab_batch_r1.copies_by_key (copy_key, attempt_id, copy_no, payload)
VALUES ('control12-a', 'control12', 1, 'v1');
INSERT INTO lab_batch_r1.copies_by_key (copy_key, attempt_id, copy_no, payload)
VALUES ('control12-b', 'control12', 2, 'v1');

-- Intentionally DO NOT write control12-c.
SELECT * FROM lab_batch_r1.copies_by_key WHERE copy_key = 'control12-a';
SELECT * FROM lab_batch_r1.copies_by_key WHERE copy_key = 'control12-b';
SELECT * FROM lab_batch_r1.copies_by_key WHERE copy_key = 'control12-c';
```

This is a **control demonstrating the shape of a partially missing outcome**, not an example of an internal `BATCH` bug. After confirming A/B are present and C is absent, you have a baseline to compare against real batch experiments.

## 5. Partition Failure Experiment with UNLOGGED BATCH

### 5.1. Choosing Keys Located on Different Nodes

With RF=1, each partition has only one replica. Use `nodetool getendpoints` to see which node owns each key; you can run this on any live node:

```bash
docker exec cassandra1 nodetool getendpoints lab_batch_r1 copies_by_key u12-a
docker exec cassandra1 nodetool getendpoints lab_batch_r1 copies_by_key u12-b
docker exec cassandra1 nodetool getendpoints lab_batch_r1 copies_by_key u12-c
```

If all three keys land on the same node, change the key suffixes (e.g., `u12-d`, `u12-e`) and **update them consistently** in all commands below. Pick at least one key residing on the node you will stop and at least one key on a node that stays up. Keep your `cqlsh` coordinator connected to a node **different** from the one being stopped.

### 5.2. Sending a Batch While a Key-Owning Node Is Unavailable

For example, stop `cassandra3` only if it is the RF=1 replica for at least one chosen key:

```bash
docker stop cassandra3
docker exec cassandra1 nodetool status
```

On `cqlsh` connected to a live node:

```sql
CONSISTENCY ONE

BEGIN UNLOGGED BATCH
    INSERT INTO lab_batch_r1.copies_by_key (copy_key, attempt_id, copy_no, payload)
    VALUES ('u12-a', 'u12', 1, 'v1');
    INSERT INTO lab_batch_r1.copies_by_key (copy_key, attempt_id, copy_no, payload)
    VALUES ('u12-b', 'u12', 2, 'v1');
    INSERT INTO lab_batch_r1.copies_by_key (copy_key, attempt_id, copy_no, payload)
    VALUES ('u12-c', 'u12', 3, 'v1');
APPLY BATCH;
```

**Record the verbatim response**, even if it is `Unavailable` or a timeout. Timing of when Cassandra detects the lost replica and how the coordinator dispatches mutations can cause the request to be rejected **before** writing any rows, or after some rows have already been applied. Therefore, a single run is not guaranteed to produce a partially missing outcome. You can retry with a fresh `attempt_id`/keys and inject the fault while writes are in flight. Do not reuse keys from a prior run, as existing rows will mask the outcome.

Restore the node and wait for `nodetool status` to report all three nodes `UN`:

```bash
docker start cassandra3
docker exec cassandra1 nodetool status
```

Read **each key** at `ONE` on RF=1:

```sql
CONSISTENCY ONE

SELECT * FROM lab_batch_r1.copies_by_key WHERE copy_key = 'u12-a';
SELECT * FROM lab_batch_r1.copies_by_key WHERE copy_key = 'u12-b';
SELECT * FROM lab_batch_r1.copies_by_key WHERE copy_key = 'u12-c';
```

Fill the actual results into your log table. If A/B are present and C is absent, you have observed a partial failure of a multi-partition business operation. Even if all three appear, **do not conclude** that unlogged batch guarantees atomicity: the writes may all have succeeded, or another mechanism such as **hinted handoff** may have delivered the data to the replica after the node recovered. Hinted handoff is not a batchlog and does not promise "all-or-nothing." If all three are missing, the request may have been rejected before dispatching mutations.

> **Verification Point:** "Client reported an error" and "no rows exist" are two different facts. Checking all of A/B/C and measuring after recovery is required to describe what happened; the error code alone is insufficient.

## 6. Comparing LOGGED BATCH and Visibility Across Replicas

### 6.1. Writing a Logged Batch on RF=3

Restart any stopped nodes before starting. In `cqlsh`:

```sql
CONSISTENCY LOCAL_QUORUM

BEGIN BATCH
    INSERT INTO lab_batch_r3.copies_by_key (copy_key, attempt_id, copy_no, payload)
    VALUES ('r312-a', 'r312', 1, 'v1');
    INSERT INTO lab_batch_r3.copies_by_key (copy_key, attempt_id, copy_no, payload)
    VALUES ('r312-b', 'r312', 2, 'v1');
    INSERT INTO lab_batch_r3.copies_by_key (copy_key, attempt_id, copy_no, payload)
    VALUES ('r312-c', 'r312', 3, 'v1');
APPLY BATCH;

SELECT * FROM lab_batch_r3.copies_by_key WHERE copy_key = 'r312-a';
SELECT * FROM lab_batch_r3.copies_by_key WHERE copy_key = 'r312-b';
SELECT * FROM lab_batch_r3.copies_by_key WHERE copy_key = 'r312-c';
```

`BEGIN BATCH` without the `UNLOGGED` keyword is a logged batch. With three distinct partitions, the coordinator must manage multiple mutations; the batchlog supports **eventual completion** if an error occurs after the batchlog has been durably stored. That does not make all three rows appear simultaneously to every client.

### 6.2. Writing While One Replica Is Temporarily Down

Stop one node in the **RF=3 cluster** (e.g., `cassandra3`), keeping two nodes alive:

```bash
docker stop cassandra3
docker exec cassandra1 nodetool status
```

Send a new logged batch using `LOCAL_QUORUM`:

```sql
CONSISTENCY LOCAL_QUORUM

BEGIN BATCH
    INSERT INTO lab_batch_r3.copies_by_key (copy_key, attempt_id, copy_no, payload)
    VALUES ('r3down12-a', 'r3down12', 1, 'v2');
    INSERT INTO lab_batch_r3.copies_by_key (copy_key, attempt_id, copy_no, payload)
    VALUES ('r3down12-b', 'r3down12', 2, 'v2');
    INSERT INTO lab_batch_r3.copies_by_key (copy_key, attempt_id, copy_no, payload)
    VALUES ('r3down12-c', 'r3down12', 3, 'v2');
APPLY BATCH;

SELECT * FROM lab_batch_r3.copies_by_key WHERE copy_key = 'r3down12-a';
SELECT * FROM lab_batch_r3.copies_by_key WHERE copy_key = 'r3down12-b';
SELECT * FROM lab_batch_r3.copies_by_key WHERE copy_key = 'r3down12-c';
```

If two replicas in the datacenter are still responsive, writes and reads at `LOCAL_QUORUM` can succeed even with the third replica down. Try switching to `CONSISTENCY ALL` and reading the same key while the node is still off: the request will typically fail as unavailable because fewer than three replicas are up; **a read error does not mean the record vanished**.

```sql
CONSISTENCY ALL
SELECT * FROM lab_batch_r3.copies_by_key WHERE copy_key = 'r3down12-a';
```

Restart the node, wait for `UN` status, then read at `ONE` and `LOCAL_QUORUM`:

```bash
docker start cassandra3
docker exec cassandra1 nodetool status
```

```sql
CONSISTENCY ONE
SELECT * FROM lab_batch_r3.copies_by_key WHERE copy_key = 'r3down12-a';

CONSISTENCY LOCAL_QUORUM
SELECT * FROM lab_batch_r3.copies_by_key WHERE copy_key = 'r3down12-a';
```

The recently recovered replica may lag behind temporarily. Reading at `ONE` **can potentially** hit a stale version if the coordinator picks that replica; it will not necessarily happen every time. Reading at `LOCAL_QUORUM` without concurrent writes compares multiple replicas and typically sees the quorum-acknowledged value. Hinted handoff, read repair (version-dependent), and anti-entropy repair help replicas converge; they operate at the replica layer, distinct from the batchlog's mutation-group layer.

To inspect **which specific replica** holds data, do not use the trick of "logging into `cqlsh` on that node and running `SELECT`": the query still routes through a coordinator and can be served by another replica. Node-level verification requires appropriate operational/tracing tools, SSTable inspection in a lab environment, or corresponding telemetry; `CONSISTENCY ONE` does not pin reads to an arbitrary chosen node.

### 6.3. Coordinator Failure Right After Dispatch

To observe an indeterminate timeout on a logged batch, issue multiple batches with **unique keys** from the test application (see the Java section) and stop the coordinator while requests are in flight. Restart the node and check every key across multiple reads. A given attempt may have:

- Returned success: verify all rows exist at the chosen write CL.
- Reported timeout/disconnect: check each key; initially some may be missing and later converge if the batchlog was written and replayed successfully.
- Created no rows: the request may not have been received or was rejected before persisting the batchlog.

There is no reliable way to time **one** `docker stop` command right at the internal batchlog write boundary on every run. Do not treat a single observation as proof of event ordering without logs/tracing. Nor is there a fixed absolute replay deadline: recovery speed depends on configuration, cluster state, and failure timing.

## 7. COUNTER BATCH: Retrying Can Increment Twice

Counters have their own update mechanism. Do not place counters in regular tables and do not mix `UPDATE ... + 1` into logged/unlogged batches containing regular `INSERT`s. With RF=3 and a healthy cluster:

```sql
CONSISTENCY LOCAL_QUORUM

BEGIN COUNTER BATCH
    UPDATE lab_batch_r3.counters_by_key
    SET total = total + 1 WHERE counter_key = 'counter12-a';
    UPDATE lab_batch_r3.counters_by_key
    SET total = total + 1 WHERE counter_key = 'counter12-b';
APPLY BATCH;

SELECT total FROM lab_batch_r3.counters_by_key
WHERE counter_key = 'counter12-a';
SELECT total FROM lab_batch_r3.counters_by_key
WHERE counter_key = 'counter12-b';
```

On the first write, if successful with no prior updates, each counter will typically equal 1. **Re-run the exact counter batch above** to simulate an application retrying after an indeterminate timeout. If both attempts apply, each counter becomes 2. Identical keys and identical CQL statements do not make `+ 1` idempotent.

Under real network failures, one or more increments might not yet be applied at read time, or an increment might already be applied even though the client received no response. After a timeout, you cannot decide to "resend" merely by inspecting a counter at one point in time, especially with concurrent writers.

**Application rule:** do not enable blind retries on counter updates. If each event must be counted **exactly once**, consider persisting immutable events with unique `event_id` values and building an aggregate with deduplication/reconciliation; or pick a system with transactions suited to exactly-once requirements. Marking an "event processed" row in another table and performing a counter update do **not automatically** become a transaction across two partitions.

## 8. Post-Failure Reconciliation from a Java Application

With Java Driver 4.x, fix `attempt_id` and **the key of each record** before sending. The example below uses `INSERT` statements that deterministically set the same keys and payload, so resending the exact same values can bring data to the desired state **when there are no competing writers**. It is unsuitable for counters or cumulative updates.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DriverException;
import com.datastax.oss.driver.api.core.cql.BatchStatement;
import com.datastax.oss.driver.api.core.cql.DefaultBatchType;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;

import java.util.List;

public final class BatchCheck {
    public static void run(CqlSession session, String attemptId) {
        PreparedStatement insert = session.prepare(
            "INSERT INTO lab_batch_r3.copies_by_key " +
            "(copy_key, attempt_id, copy_no, payload) VALUES (?, ?, ?, ?)"
        );

        var builder = BatchStatement.builder(DefaultBatchType.LOGGED)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(true);

        List<String> keys = List.of(
            attemptId + "-a", attemptId + "-b", attemptId + "-c"
        );

        for (int i = 0; i < keys.size(); i++) {
            builder.addStatement(insert.bind(keys.get(i), attemptId, i + 1, "v1"));
        }

        try {
            session.execute(builder.build());
            System.out.println("Batch acknowledged: " + attemptId);
        } catch (DriverException ex) {
            System.err.println("Unknown outcome: " + attemptId + " / " + ex);
        }

        // Verify each partition, even after an exception.
        PreparedStatement read = session.prepare(
            "SELECT payload FROM lab_batch_r3.copies_by_key WHERE copy_key = ?"
        );
        for (String key : keys) {
            Row row = session.execute(
                read.bind(key)
                    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            ).one();
            System.out.println(key + " -> " +
                (row == null ? "<absent>" : row.getString("payload")));
        }
    }
}
```

Adjust contact points, datacenter, driver version, and timeout settings to match your cluster. A read error during reconciliation must still be logged as a read error—**never** record `absent` if the query did not finish. For concurrently modified data, record the version/`event_id` to determine the authoritative value before compensating.

For `INSERT`/`UPDATE` statements writing the same deterministic values to the same keys, a practical recovery workflow is: persist `attempt_id` → send → on indeterminate outcome, re-read each key at an appropriate CL → compensate only missing keys or resend a verified-idempotent operation → perform a final reconciliation check. Never apply this same pattern to counters, because compensating a "missing" read cannot guarantee against double-counting.

## 9. Common Result Interpretation Table

| Observation | Possible Explanation | What to Verify |
| --- | --- | --- |
| Client reports timeout, A/B/C all present | Write completed but response was lost; or completed after client timeout. | Read at appropriate CL, check timestamps and attempt count. |
| Client reports error, A/B present, C missing | Multi-partition write partially failed; or a replica of C had not responded at read time. | Separate partition vs. replica; check RF/CL, query each key, re-check once node is healthy. |
| `ALL` cannot read while one node is down | Insufficient replicas available for the chosen CL. | Check `nodetool status`; do not assume data was deleted. |
| `ONE` occasionally returns stale version, `LOCAL_QUORUM` returns new version | Replicas not yet converged or lag in propagation/recovery. | Check competing writes, hints/repair, and read timing. |
| Counter went from 1 to 2 after retry | Two increments were applied. | Check attempt count and retry policy; do not arbitrarily decrement counters if concurrent writes exist. |
| Logged batch initially missing after timeout, later complete | Likely batchlog replay or replica recovery mechanism, depending on case. | Use logs/tracing to identify the mechanism; do not attribute cause solely from SELECT. |

For a write acknowledged to the client at `LOCAL_QUORUM` on RF=3, a subsequent read also at `LOCAL_QUORUM` can still **fail** if node failures leave fewer than two active replicas. Consistency does not eliminate availability requirements.

## 10. Practice Checklist and Self-Check Questions

- [ ] Record `attempt_id`, all three `copy_key` values, and timestamps for **every** run.
- [ ] Confirm all three nodes are `UN`, along with datacenter and RF, before injecting faults.
- [ ] Run both a fault-free control and a simulated application stop mid-way across three statements.
- [ ] Observe `UNLOGGED BATCH` at RF=1 and record runs that do not yield partial results too.
- [ ] Distinguish `ALL` read failures caused by missing replicas from genuinely absent rows.
- [ ] Run the `COUNTER BATCH` twice and explain why blind retries are unsafe.
- [ ] Ground all present/missing conclusions in three partition-key queries with explicit CL and timestamps.

**Explain in your own words using your observed data:**

1. Why does a successful `BEGIN BATCH` not mean another client always reads an atomic snapshot of A/B/C simultaneously?
2. Is a single `WriteTimeoutException` sufficient proof that no rows were saved? What additional evidence is required?
3. When one node in an RF=3 cluster stops, why can `LOCAL_QUORUM` still succeed while `ALL` fails?
4. When re-running the exact `UPDATE total = total + 1` statement, why does the outcome differ from resending an `INSERT` with the same key and values?
5. If an UNLOGGED run returns an error yet all three rows appear after the node recovers, **does** that prove unlogged batches have a batchlog? Why or why not?

**Key Takeaway:** Before repairing data after an error, determine whether you are reconciling **multiple logical rows**, **multiple replicas of one row**, or **both at once**. Use batchlog semantics to understand replay commitments, consistency levels to understand replica acknowledgments, and `attempt_id` for business reconciliation. Counter increments in particular must be treated as operations that can be applied multiple times under uncontrolled retries.
