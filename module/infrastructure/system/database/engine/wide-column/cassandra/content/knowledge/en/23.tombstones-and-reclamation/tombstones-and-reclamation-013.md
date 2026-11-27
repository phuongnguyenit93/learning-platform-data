# Experimenting with Deletes, Down Replicas, and Recovering Correct Data

## Lesson objectives

In Apache Cassandra, `DELETE` does not immediately erase every copy of data across nodes. Instead, Cassandra writes a timestamped **tombstone** (deletion marker). Tombstones are distributed and reconciled against live data through replica and timestamp mechanisms; only later, under certain safety conditions, can **compaction** reclaim deleted data on disk.

Trouble arises when a **replica goes down right during a DELETE**: that replica may still keep the old record. When the node returns, the system must synchronize the deletion marker before it gets dropped from other replicas. Otherwise, supposedly deleted data risks **reappearing**, commonly called *zombie data*.

This lesson belongs to the **Tombstones and Reclamation** chapter in the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. It connects the write/read path, wide-column partition keys, replication, consistency levels, CQL, compaction, repair, and Java application operations.

After this lesson, you will be able to:

1. Explain why Cassandra uses tombstones and the role of `gc_grace_seconds`.
2. Design a **three-node / RF=3** lab to delete data while one replica is down.
3. Distinguish **acknowledged DELETE**, **reads not seeing the row**, and **all replicas knowing the tombstone**.
4. Recover the node, check hints/repair, and verify data at an appropriate consistency level.
5. Recognize risks when a replica stays absent too long, as well as what cannot be fixed by compaction alone.
6. Log ACKs, timeouts, and verification results from the Java Driver without over-concluding.

> **Practice boundary:** only stop nodes in a lab cluster or a test environment authorized for fault injection. This lesson presents commands for learners to run themselves; never intentionally stop a live production system. Never shorten `gc_grace_seconds` in production to try inducing zombies.

## 1. DELETE, tombstones, and physical reclamation are three distinct moments

Suppose row `(run_id='lab-a', item_id=1)` holds `value='ACTIVE'` across three replicas. When the application sends:

~~~sql
DELETE FROM tombstone_lab.entries_by_run
WHERE run_id = 'lab-a' AND item_id = 1;
~~~

Cassandra writes a tombstone with a **deletion timestamp** to mark the data as deleted. During reads, replicas must reconcile live data and tombstones; an old record with a lower timestamp than the deletion marker must not become a live result merely because one replica missed the DELETE.

~~~mermaid
sequenceDiagram
    participant App as Client
    participant C as Coordinator
    participant R1 as Replica 1
    participant R2 as Replica 2
    participant R3 as Replica 3 (down)
    App->>C: DELETE, LOCAL_QUORUM
    C->>R1: Tombstone
    C->>R2: Tombstone
    Note over R3: Keeps old value; misses DELETE
    R1-->>C: ACK
    R2-->>C: ACK
    C-->>App: Success (2/3 ACKs met)
~~~

This is an experimental scenario diagram; not every execution is guaranteed to follow this exact message sequence. Whether the third replica retains the old value depends on it having stopped before DELETE and not yet being synchronized afterward.

| Stage | Logical data | Physical data |
| --- | --- | --- |
| Before `DELETE` | Row exists | Value may reside in replicas' memtables/SSTables |
| After `DELETE` is ACKed | Row is deleted for reads seeing sufficient tombstone info | Tombstone and old data may persist across multiple SSTables |
| Replica returns | Must learn the tombstone so it does not bring old value back | May require hints, read repair, or anti-entropy repair |
| When compaction is allowed to purge | Deleted row stays absent | Tombstone and shadowed data may be reclaimed if eligible |

**Compaction does not mean DELETE.** Nor should you assume tombstones vanish at the exact `gc_grace_seconds` second: purging also depends on overlapping SSTables, live data, compaction strategy, and safety conditions.

### Distinguishing several deletion forms

- `DELETE ... WHERE` with full primary key can delete a specific row; deleting columns, collections, or ranges uses different tombstone forms.
- `UPDATE` setting a column to `null` can also create a tombstone; TTL-expired values likewise lead to tombstone logic.
- `TRUNCATE` is a table-level data-clearing operation with different semantics from row-by-row `DELETE`; do not use `TRUNCATE` to substitute for tombstone-propagation experiments.
- Never manually edit or delete SSTable files on disk to "delete fast"; doing so can cause data loss or break recovery.

## 2. Why does a down replica create zombie risk?

Cassandra uses **last-write-wins reconciliation by timestamp** alongside deletion metadata. When a replica misses a DELETE, it retains the old copy. While the tombstone persists on other replicas, the deletion marker can block the old data from being treated as valid when reconciliation sees it.

However, if the replica stays absent **too long** and surviving nodes have already been able to purge the tombstone, the system may no longer have enough trace to distinguish the old value from a value that was never deleted. When the old replica returns or syncs inappropriately, the surviving stale value can be copied back: **zombie data**.

~~~mermaid
flowchart TD
    A["R1/R2/R3 all hold old value"] --> B["R3 goes down"]
    B --> C["DELETE reaches quorum on R1 + R2"]
    C --> D{"Is R3 synced\nbefore tombstone is purged?"}
    D -->|Yes| E["R3 learns deletion marker\nOld data is shadowed and safely dropped"]
    D -->|No| F["Tombstone may be purged\nR3 still holds live old value"]
    F --> G["Zombie data risk\nwhen R3 returns/repairs"]
~~~

Here, "risk" does not mean every restart past grace is guaranteed to resurrect the row. Reproducing a zombie in a lab requires controlling timing, compaction, timestamps, and replica data; that is an advanced experiment and unnecessary for understanding the mechanism.

## 3. How do gc_grace_seconds, hints, and repair differ?

`gc_grace_seconds` is a **table-level** setting, in seconds. It specifies the minimum grace period related to dropping tombstones during compaction, giving a down replica an opportunity to receive deletion info. A common default in many Cassandra versions is **864000 seconds = 10 days**; always verify actual configuration.

~~~sql
SELECT keyspace_name, table_name, gc_grace_seconds
FROM system_schema.tables
WHERE keyspace_name = 'tombstone_lab'
  AND table_name = 'entries_by_run';
~~~

Do not think of `gc_grace_seconds` as a command to "auto-run repair after 10 days." It does not actively propagate deletion markers, does not guarantee all replicas are synced, and does not replace repair schedules.

| Mechanism | What does it do? | What does it NOT guarantee? |
| --- | --- | --- |
| **gc_grace_seconds** | Retains tombstones long enough to avoid premature purging under compaction rules | Does not auto-detect replicas missing markers; does not replace repair schedules |
| **Hinted handoff** | Stores and replays some mutations for temporarily down replicas if config/limits permit | Hints have expiration and storage limits; not a backup or repair replacement |
| **Read repair** | In read paths with reconciliation and matching policy, fixes drift among participating replicas | Does not scan every partition; one `SELECT` does not prove cluster-wide sync |
| **Anti-entropy repair** | Compares token ranges across replicas and syncs missing data/tombstones | Cannot recreate tombstones already purged on all replicas |
| **Compaction** | Merges SSTables and can purge tombstones when eligible | Does not proactively sync other replicas; purging too early can contribute to zombies |

A common operational rule: **complete repairs covering relevant data on a cadence shorter than the grace window**, with margin for node downtime and repair duration. This is a design requirement, not proof that calling repair once is safe in every setup. If using specialized tombstone mechanisms or versions with different rules, follow the documentation for your exact version.

For example, if grace is 10 days yet a replica was down for 15 days, **do not blindly boot the old node and run repair as usual**. When a replica exceeds the safety boundary and tombstones may have been dropped on other replicas, follow a recovery/replace/rebuild workflow using trusted replicas or backups, along with data completeness verification.

## 4. Lab design: three nodes, RF=3, single DC

### 4.1. Requirements and assumptions

Use a three-node cluster in the same datacenter, e.g., `cass-1`, `cass-2`, `cass-3`. Assume the datacenter is named `datacenter1`, Cassandra versions are uniform, and all three nodes serve the same keyspace. If your actual DC name differs, adjust the keyspace creation commands accordingly.

First inspect the healthy cluster:

~~~bash
# Run on a live container/VM; adjust to your lab environment.
nodetool status
~~~

Expect three nodes in `UN` (*Up/Normal*) state, with no ongoing bootstrap/decommission/repair. From `cqlsh`:

~~~sql
SELECT release_version, data_center, host_id
FROM system.local;
~~~

This query describes the connected node; it does not automatically verify the version of every node. Check each node's configuration if the cluster is mid-upgrade.

### 4.2. Sample keyspace and table

~~~sql
CREATE KEYSPACE IF NOT EXISTS tombstone_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS tombstone_lab.entries_by_run (
    run_id text,
    item_id int,
    value text,
    created_at timestamp,
    PRIMARY KEY ((run_id), item_id)
) WITH gc_grace_seconds = 864000;
~~~

`run_id` is the **partition key**, isolating data from each test run; `item_id` is the clustering column. The experiment touches only a single partition and known rows, avoiding wide scans. `created_at` is illustrative data; timestamps used to reconcile mutations are managed by Cassandra and must not be inferred solely from this column's value.

**If the keyspace/table already exists**, `IF NOT EXISTS` does not update old settings. Verify beforehand:

~~~sql
SELECT keyspace_name, replication, durable_writes
FROM system_schema.keyspaces
WHERE keyspace_name = 'tombstone_lab';

SELECT table_name, gc_grace_seconds
FROM system_schema.tables
WHERE keyspace_name = 'tombstone_lab'
  AND table_name = 'entries_by_run';
~~~

Never run an RF=3 lab on a cluster with only two healthy replicas from the start; ACK-count predictions will not hold.

### 4.3. Preparing baseline data across three replicas

In `cqlsh` while all three nodes are `UN`:

~~~text
CONSISTENCY ALL
~~~

~~~sql
INSERT INTO tombstone_lab.entries_by_run
    (run_id, item_id, value, created_at)
VALUES ('delete-demo-01', 1, 'SHOULD_BE_DELETED',
        '2026-11-21T09:00:00Z');

INSERT INTO tombstone_lab.entries_by_run
    (run_id, item_id, value, created_at)
VALUES ('delete-demo-01', 2, 'CONTROL_KEEP',
        '2026-11-21T09:00:00Z');
~~~

`CONSISTENCY ALL` before stopping a node requires **all three replicas to ACK** the initial data. Record the actual response: if any timeout/error occurs, do not treat preparation as complete. Row `item_id=2` serves as a **control sample** to ensure we did not accidentally delete the whole partition.

Read baseline:

~~~sql
SELECT item_id, value, created_at
FROM tombstone_lab.entries_by_run
WHERE run_id = 'delete-demo-01';
~~~

Expect `item_id=1` and `item_id=2`. When rerunning, **change `run_id`** so you do not mix data/tombstones from the previous run. Never shift system clocks or use arbitrary CQL timestamps in a basic lab, as clock skew complicates deletion marker analysis.

## 5. Experiment A: stopping a replica before DELETE

From the lab's Docker host:

~~~bash
# Example container name; perform only in a lab.
docker kill --signal=KILL cass-3
~~~

`SIGKILL` stops the process abruptly, unlike `nodetool drain`. This simulates a **node temporarily unable to receive mutations**, not a power-loss or total storage-device loss experiment.

Check the remaining two nodes:

~~~bash
# Run on cass-1 or cass-2.
nodetool status
~~~

Expect `cass-3` to report `DN` (*Down/Normal*) while `cass-1` and `cass-2` remain `UN`. Connect `cqlsh` to a live node; do not use `cqlsh` inside the stopped container.

Set write consistency level:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

Execute **DELETE on exactly one row**:

~~~sql
DELETE FROM tombstone_lab.entries_by_run
WHERE run_id = 'delete-demo-01'
  AND item_id = 1;
~~~

With RF=3 in one DC, `LOCAL_QUORUM` requires **2/3 replicas** to acknowledge. Because two replicas remain alive, DELETE **can succeed** if both process the request. Record the client's exact response:

| Outcome | Record | Valid conclusion |
| --- | --- | --- |
| `DELETE` returns success | `ACK_LOCAL_QUORUM` | Two replicas acknowledged the delete mutation per CL |
| Timeout | `UNKNOWN_TIMEOUT` | One or more replicas may have processed it, yet client did not receive enough ACKs |
| Unavailable/error | Actual error code | Do not assume 0 replicas processed it; inspect error type and logs |

**Proceed to the confirmed-DELETE verification branch only upon receiving a successful ACK.** If the outcome is uncertain, start a new `run_id` after the cluster is healthy or investigate per your logbook; never silently retry and count this as a guaranteed single-ACK operation.

### Reading while the third replica is still down

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
SELECT item_id, value
FROM tombstone_lab.entries_by_run
WHERE run_id = 'delete-demo-01';
~~~

Once DELETE is ACKed and the two live replicas serve the `LOCAL_QUORUM` read, expect to see only the control row `item_id=2`. If `item_id=1` does not appear, **this is evidence of the read result at the chosen CL**, not proof that `cass-3` knows the tombstone.

Reading at `LOCAL_ONE` might also miss the row, yet **`LOCAL_ONE` offers weaker guarantees** while a stale replica exists. A single clean read at `LOCAL_ONE` is not enough to confirm all replicas are synced.

## 6. Experiment B: starting the replica and synchronizing the deletion marker

Restart the node:

~~~bash
docker start cass-3
~~~

Check `nodetool status` until all three nodes show `UN`. At this point, replica `cass-3` previously stored `item_id=1` before stopping; it may:

- Receive a **hint** stored while down, if hints are enabled, within limits, and replayed successfully.
- Be synced with the tombstone via **read repair** under matching read conditions.
- Be synced via **anti-entropy repair** over the token range containing this partition.

There is no basis to claim with certainty which one happened from `nodetool status` alone. `UN` status says the node is up, not that every SSTable has been repaired.

### 6.1. Reading after the node returns

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
SELECT item_id, value
FROM tombstone_lab.entries_by_run
WHERE run_id = 'delete-demo-01';
~~~

If only `item_id=2` remains, the system returns accurately at the current read scope. However, connecting `cqlsh` directly to `cass-3` **does not guarantee** Cassandra reads only that node's local copy: the coordinator still picks replicas by routing and consistency level. Therefore, never cite "I queried from cass-3 and didn't see the row" as proof that all replicas are clean.

### 6.2. Repairing while the tombstone is still within grace

On the lab cluster, run repair on the table with all nodes healthy:

~~~bash
# Run on an appropriate lab node after all three nodes are UN.
nodetool repair -full tombstone_lab entries_by_run
~~~

`nodetool repair -full` runs anti-entropy repair without relying on marked incremental ranges; it can consume CPU, disk I/O, network, and time. Running the command on one node applies to the ranges handled by that node's repair session; in different topologies, plan **coverage across all involved ranges/replicas**. Never treat a command returning success on one random node as proof that every node/table on a large cluster was fully repaired.

In a three-node RF=3 lab, the node invoking repair participates in all replica ranges of the table; still inspect completion logs/status, errors, and actual scope. Run repair **before exceeding grace**, while needed tombstones still exist and all replicas can communicate.

After repair, read the target row and control sample again:

~~~sql
SELECT item_id, value
FROM tombstone_lab.entries_by_run
WHERE run_id = 'delete-demo-01';
~~~

Expected:

- **Do not see** `item_id=1`.
- **Still see** `item_id=2` with `value='CONTROL_KEEP'`.
- No other writes/updates occurred on the same key during the test.

To investigate deeper, collect repair/hints logs and metrics on each node. This test focuses strictly on two known rows; it does not prove the state of other partitions in the cluster.

## 7. Why shouldn't you deliberately wait past gc_grace_seconds?

Standard experiments should finish before tombstones can be purged. To understand zombie risk, use a **hypothetical scenario** rather than taking a production node down for ten+ days:

| Milestone | Two healthy replicas | Down replica | Risk |
| --- | --- | --- | --- |
| T0 | Hold live row | Holds live row | Normal |
| T1 | Receive DELETE and store tombstone | Misses DELETE | Stale replica |
| T1 + a few hours | Tombstone remains; can repair | Not back yet | Can recover safely if synced before purge |
| Past grace and compaction qualifies | Tombstone **may** be purged | Still holds old value | Deletion info lost on purged replicas |
| Stale replica returns unchecked | May learn old value as live data | Carries stale copy | **Zombie** risk |

**Condition to emphasize:** reaching `gc_grace_seconds` does not automatically trigger a purge at that exact instant; it opens purge eligibility subject to compaction checks. A cluster may retain tombstones far longer than grace. Conversely, never rely on such luck as an operational strategy.

If a replica has been out of the cluster too long — especially past grace or without covered repairs — **do not restart it normally by default**. First assess whether tombstones could have been purged, the health of surviving replicas, backups, and the node replacement/rebuild procedure for your exact version. The goal is avoiding bringing stale data back into the cluster; never manually delete SSTables on the old node.

In some situations, you must **rebuild/replace the replica from trusted sources**, or restore from backups and reconcile against source systems. If all copies have lost tombstones and no reliable deletion history exists, repair **cannot deduce** which rows were once deleted; recovery must come from event logs/backups/business sources of truth.

## 8. Extended experiment: TTL and compaction

TTL also causes expired data to be treated as no longer existing. It interacts with tombstones and physical reclamation:

~~~sql
-- Separate row; do not share the same key with the main DELETE experiment.
INSERT INTO tombstone_lab.entries_by_run
    (run_id, item_id, value, created_at)
VALUES ('ttl-demo-01', 1, 'TEMPORARY',
        '2026-11-21T09:00:00Z')
USING TTL 120;
~~~

Read before expiration:

~~~sql
SELECT item_id, value, TTL(value)
FROM tombstone_lab.entries_by_run
WHERE run_id = 'ttl-demo-01' AND item_id = 1;
~~~

After TTL expires, `SELECT` may stop returning the row; that does not prove data bytes were reclaimed from SSTables right away. Inspect tombstone and compaction metrics via administration tools:

~~~bash
nodetool tablestats tombstone_lab.entries_by_run
nodetool compactionstats
~~~

**Do not force `nodetool compact` just to "wipe clean" fast after 120 seconds.** Major compaction generates I/O/CPU load, depends on purge conditions, and can disrupt time-series data/strategies. Allow sufficient observation time and understand `gc_grace_seconds` and the compaction mechanics of your actual Cassandra version.

| Observation | Proper interpretation |
| --- | --- |
| `SELECT` no longer sees the row | Logical data is not returned by that query |
| SSTables still occupy space | Old data or tombstones may be awaiting compaction |
| Tombstones do not drop immediately | Purging depends on grace, overlap, and SSTable selection |
| Many tombstones cause high read latency | The read path may have to inspect many deleted/expired entries |
| Repair has run | Can synchronize replicas; **does not** force immediate disk release |

## 9. Java application: separating DELETE outcomes from read outcomes

The snippet below uses **Apache Cassandra Java Driver 4.x**. Assume `CqlSession` is connected to the right keyspace/topology and the lab table exists; `PreparedStatement`s are reused:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class TombstoneProbe {
    private final CqlSession session;
    private final PreparedStatement deleteOne;
    private final PreparedStatement selectOne;

    public enum DeleteResult { ACKNOWLEDGED, UNKNOWN }

    public TombstoneProbe(CqlSession session) {
        this.session = session;
        this.deleteOne = session.prepare(
            "DELETE FROM tombstone_lab.entries_by_run " +
            "WHERE run_id = ? AND item_id = ?");
        this.selectOne = session.prepare(
            "SELECT value FROM tombstone_lab.entries_by_run " +
            "WHERE run_id = ? AND item_id = ?");
    }

    public DeleteResult deleteAtQuorum(String runId, int itemId) {
        BoundStatement statement = deleteOne.bind(runId, itemId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotence(false);
        try {
            session.execute(statement);
            System.out.printf("DELETE_ACK run=%s item=%d%n", runId, itemId);
            return DeleteResult.ACKNOWLEDGED;
        } catch (RuntimeException error) {
            System.err.printf(
                "DELETE_UNKNOWN run=%s item=%d error=%s%n",
                runId, itemId, error.getClass().getSimpleName());
            return DeleteResult.UNKNOWN;
        }
    }

    public boolean observedAbsentAtQuorum(String runId, int itemId) {
        BoundStatement statement = selectOne.bind(runId, itemId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
        Row row = session.execute(statement).one();
        return row == null;
    }
}
~~~

Explaining the points governing reliability:

- `DELETE_ACK` is logged only when `session.execute` returns successfully. Timeouts or exceptions are marked `UNKNOWN`; if detailed classification is required, the caller must preserve the exception to distinguish `Unavailable`, timeouts, and configuration errors.
- `observedAbsentAtQuorum` returns `true` when **a quorum read sees no row**; it does not mean **every single replica** holds the tombstone or that physical bytes were deleted.
- `setIdempotence(false)` is a cautious lab choice when concurrent writes on the same key might exist: retrying a `DELETE` using a fresh timestamp can interact differently with concurrent updates. In real workflows, retries must rely on business identifiers, timestamps, and concurrency models.
- Keep a dedicated `runId` per test run, and do not send new writes to the same key while analyzing results.
- Never silently switch from `LOCAL_QUORUM` to `LOCAL_ONE` on verification reads and interpret the two outcomes as equivalent.

If a system must "permanently erase customer information," CQL deletes and tombstones are only **one part of the data lifecycle**. You must also account for backups, snapshots, downstream ETL, caches, logs, and retention policies. This lab does not by itself satisfy system-wide legal data-erasure requirements.

## 10. Verification and troubleshooting checklist

| Check | Success signal | If abnormal |
| --- | --- | --- |
| Topology | 3 nodes in same DC, RF=3, initially `UN` | Fix lab config before testing |
| Baseline write | `INSERT` at `ALL` ACKed for both rows | Do not proceed on an uncertain baseline |
| Node down | Specifically `cass-3` is `DN`, other two nodes `UN` | Check gossip/network and node names |
| DELETE | `LOCAL_QUORUM` ACKed while two replicas live | Log `UNKNOWN` on timeout; do not claim guaranteed delete |
| Pre-restart read | Only control sample remains at `LOCAL_QUORUM` | Check key, write CL, timestamps, and read errors |
| Node restart | All three nodes return to `UN` | Collect startup and recovery logs |
| Hints/repair | Sync completes within grace for relevant scope | Do not rely on `SELECT` alone; check repair coverage |
| Final read | Target row absent, control sample still present | Check logs, repair sessions, stale replicas, and concurrent updates |
| Long-term ops | Repair schedule aligns with grace and downtime | Assess zombie risk and rebuild/restore procedures |

### If a deleted row "reappears," what should you check?

1. **Keys and write sources:** was `run_id` reused? Did any service `INSERT` to the same primary key after DELETE?
2. **Timestamps:** did a new write carry a higher timestamp than the tombstone? Are clients supplying timestamps or are clocks noticeably skewed?
3. **CL and topology:** at what CL was DELETE truly ACKed, what is the actual RF, and which datacenters are counted?
4. **Replica health:** which node went down and for how long, did hints survive, and did repair cover all ranges?
5. **Tombstone lifecycle:** what were actual `gc_grace_seconds`, compaction, and deletion mechanics doing?
6. **Source of truth:** if no deletion evidence remains, consult event logs/backups/business ledgers to determine valid values before fixing data.

Do not immediately "solve" it by running `DELETE` again and calling it done: that can mask an operational design flaw and recreate the same risk on the next outage.

## 11. Exercises and thought questions

**Exercise 1 — ACKs and guarantee scope.** Prepare two rows at `ALL`, stop one replica, then delete one row at `LOCAL_QUORUM`. Record strictly whether the client returned success or error. Why can `W=2` at RF=3 still return an ACK while one replica is down?

**Exercise 2 — What does reading nothing mean?** While `cass-3` is still stopped, a `LOCAL_QUORUM` read sees only the control sample. Which statement is true: "the deleted row is shadowed at quorum" or "all three replicas physically erased it"? Explain.

**Exercise 3 — Recovery.** Start `cass-3` back up and run controlled repair before grace can expire. Monitor logs/metrics and CQL results. Why is a single `SELECT` routed through coordinator `cass-3` insufficient to prove its local replica copy has been healed?

**Exercise 4 — Hypothetical zombie.** A replica stays down past grace and tombstones on the other nodes were dropped by compaction. Analyze what can happen when the replica holding the old record returns. Outline the steps to verify a trusted source before rebuilding/replacing the node.

**Exercise 5 — TTL and reclamation.** Write a row with a 120-second TTL. After 120 seconds, reads no longer see the row. Can you assert disk space has been freed? Why?

**Exercise 6 — Retrying in Java.** `DELETE` at `LOCAL_QUORUM` times out, yet a subsequent `SELECT` does not see the row. Do you have sufficient proof that the first DELETE call was ACKed? Design a minimal log structure containing `operation_id`, primary key, CL, timestamp, and outcome type for investigation.

## Key takeaways

**Tombstones are necessary metadata so deleted data is not resurrected from stale replicas.** A proper experiment records DELETE ACKs, sets CL matching RF, stops and recovers one replica under control, synchronizes before tombstones are purged, and checks both target data and control samples. `gc_grace_seconds` provides a safety window for propagating deletion markers while hints/repair drive synchronization; a single `SELECT` returning no row does not mean all replicas are synced or that data has already been reclaimed from disk.
