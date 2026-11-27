# Read/Write Quorums and Discrepancies That Still Need Repair

## 1. One Successful Operation Does Not Mean All Replicas Match

In **Apache Cassandra**, a partition's data is stored on multiple **replicas** determined by the partition key's token, replication strategy, and topology. A node acting as **coordinator** forwards the operation to the appropriate replicas and returns once the **consistency level (CL)** is satisfied.

A common scenario:

1. Partition `device-7 / 2026-11-21` has three replicas **N1, N2, N3** (RF = 3).
2. A write at `LOCAL_QUORUM` succeeds because **N1 and N2** acknowledged; **N3** is slow or disconnected.
3. A subsequent `LOCAL_QUORUM` read can still observe the latest value thanks to **overlap between the written replica set and the read replica set**.
4. **N3 may still hold stale data.** If subsequent reads do not touch N3, nothing forces quorum reads/writes alone to repair all history on that node.

This is the critical distinction between **achieving quorum for a request** and **fully synchronizing replicas over time**. This lesson explains quorum math, read reconciliation, sources of divergence, and why **anti-entropy repair** remains essential.

**Goals after this lesson:**

- Calculate response counts for `ONE`, `LOCAL_QUORUM`, `QUORUM`, and `ALL` from the replication factor.
- Explain the `R + W > RF` overlap condition and its underlying assumptions.
- Distinguish **reading the right data** from **having every replica repaired**.
- Analyze the effects of hinted handoff, read repair, tombstones, flaky networks, and multiple data centers.
- Practice CQL, inspect topology/repair, and use Java Driver 4.x with explicit CLs.

Examples assume standard **full replicas**; transient replication, LWT/Paxos, and version-specific config differences are not taken as defaults.

## 2. Three Concepts Frequently Conflated

| Concept | Question It Answers | What Does It Not Guarantee? |
| --- | --- | --- |
| **Replication factor (RF)** | How many target replica nodes does each partition have (per DC with `NetworkTopologyStrategy`)? | Does not say how many nodes a write must wait for. |
| **Consistency level (CL)** | How many matching responses does a read/write need before the coordinator returns? | Does not guarantee every replica received, stored, or repaired the data. |
| **Repair** | How are differences across replicas detected and synced over data ranges? | Not a per-request ACK condition and does not replace backups. |

**Example:** a DC has four nodes, keyspace RF = 3. Each partition has only **three target replicas** in that DC; the fourth node can act as coordinator but does not replicate every partition. `LOCAL_QUORUM` requires **two responses** out of those three replicas, not two out of all four nodes in the DC.

The partition key determines **the token and replica group**. Clustering columns only sort rows inside the partition; a partition with thousands of rows still shares the **same replica set** for all those rows.

## 3. Quorum Math: Why `R + W > RF`?

Let:

- `RF`: number of full replicas of the partition in the **considered scope**.
- `W`: number of replicas acknowledged when a write succeeds.
- `R`: number of replicas required to participate for the read consistency level.

If `R + W > RF`, any two subsets of `W` and `R` nodes chosen from the same `RF` nodes **must share at least one overlapping node**. That is **quorum overlap**.

With RF = 3:

| CL in One DC | Responses Required | Example |
| --- | ---: | --- |
| `LOCAL_ONE` | 1 | One local replica acknowledges. |
| `LOCAL_QUORUM` | `floor(3 / 2) + 1 = 2` | Two local replicas acknowledge. |
| `ALL` | 3 | All three replicas of the partition acknowledge. |

When **write `LOCAL_QUORUM`** and **read `LOCAL_QUORUM`** target the same DC, `W = 2`, `R = 2`, `RF = 3`, so `2 + 2 > 3`. Two 2-element subsets out of 3 elements cannot be disjoint.

~~~text
Partition replicas: {N1, N2, N3}

Write ACKs: {N1, N2}          -- W = 2
Read ACKs:  {N2, N3}          -- R = 2
Overlap:    {N2}

If N2 holds the newer write, the coordinator can reconcile the read
against the stale version from N3.
~~~

### 3.1. Request Diagram with a Slow Replica

~~~mermaid
sequenceDiagram
    participant A as Application
    participant C as Coordinator
    participant N1 as N1 (replica)
    participant N2 as N2 (replica)
    participant N3 as N3 (slow replica)
    A->>C: INSERT (LOCAL_QUORUM)
    C->>N1: Mutation t2
    C->>N2: Mutation t2
    C->>N3: Mutation t2
    N1-->>C: ACK t2
    N2-->>C: ACK t2
    C-->>A: Success (2/3 ACKs)
    Note over N3: May still hold t1
    A->>C: SELECT (LOCAL_QUORUM)
    C->>N2: Read / digest
    C->>N3: Read / digest
    N2-->>C: t2
    N3-->>C: t1
    Note over C: Detect mismatch, reconcile
    C-->>A: Newer valid value by timestamp
~~~

The diagram **does not** claim reads always pick N2 and N3, or that N3 is necessarily repaired synchronously right after the request. Replica selection, data/digest exchange, and read repair behavior depend on version, CL, and query type.

### 3.2. Limits of the Overlap Argument

`R + W > RF` is **a replica-set intersection condition**, not proof that Cassandra offers transaction isolation or serializability across operations.

For the reasoning to hold, at least these assumptions are needed:

1. `R` and `W` apply to the **same replica set** of the same partition and corresponding DC scope.
2. Replicas that ACKed the write remain available with their data for the read; all ACKed copies were not permanently lost before syncing.
3. For a completed write, **no unresolved concurrent write** or bad client timestamp distorts version ordering.
4. The read protocol reconciles versions properly; last-write-wins/tombstone semantics apply cleanly.

Therefore, quorum typically surfaces the latest completed write **when there are no concurrent writes and no failures beyond assumptions**, yet it is not multi-partition ACID transactions, does not prevent read-modify-write lost updates, and does not mean all replicas have converged.

## 4. Quorum Succeeded, Yet Data Still Diverges

### 4.1. Quorum Writes Do Not Wait for Every Replica

With RF = 3, a `LOCAL_QUORUM` write succeeds upon receiving two ACKs in the local DC. The coordinator normally attempts to forward the mutation to **all target replicas**; however, returning success **does not wait for the third replica**.

N3 may diverge due to:

- Being unreachable at write time.
- Restarting, network loss, or overload.
- The write being in flight and not yet delivered/applied.
- Another mutation with a newer timestamp or an unsynced delete/tombstone.

This is **replica divergence**. A successful write verifies only the **request's ACK threshold**, not uniform contents across every replica.

### 4.2. Quorum Reads Do Not Scan All History

A quorum read can detect discrepancies **within the queried read data**. For instance:

- A `SELECT` reading partition `device-7` can trigger reconciliation for the accessed rows of that partition.
- Another partition `device-8` that is never read can remain divergent.
- Even within partition `device-7`, clustering ranges **not queried** may remain uncompared.
- If N1 and N2 (both having the newer write) answer a read, N3 may **not participate** and remain stale.

Read repair (when active on the read path/version) can fix **detected** divergence, without scanning the whole keyspace.

### 4.3. Where `ONE` Can Still See Stale Data

Still with N1/N2 holding `t2` and N3 holding `t1`:

| Request | Example Read Replicas | Observable Outcome |
| --- | --- | --- |
| `LOCAL_ONE` | N3 only | Can see stale value `t1`. |
| `LOCAL_ONE` | N1 only | Can see new value `t2`. |
| `LOCAL_QUORUM` | N2 and N3 | Can reconcile and return valid `t2`; N3 is a repair candidate. |
| `LOCAL_QUORUM` | N1 and N2 | Sees `t2`; N3 is not necessarily repaired. |

Before data converges, the **same SQL/CQL query** can return different results at different CLs/replicas. Quorums improve visibility of writes satisfying intersection; repair drives **convergence across the entire replica set**.

## 5. Multi-Data-Center Quorums: Scope Decides Everything

Suppose a keyspace uses `NetworkTopologyStrategy` with **RF = 3 in `dc1`** and **RF = 3 in `dc2`**. Each partition has up to six full replicas if enough nodes exist.

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3,
  'dc2': 3
};
~~~

| CL | Threshold with RF 3 + 3 | Scope |
| --- | --- | --- |
| `LOCAL_ONE` | 1 | Coordinator's local DC. |
| `LOCAL_QUORUM` | 2 | Local DC only, e.g., `dc1`. |
| `QUORUM` | `floor(6/2)+1 = 4` | Total full replicas across DCs. |
| `EACH_QUORUM` (write) | 2 in `dc1` **and** 2 in `dc2` | Requires quorum per DC; not just any four ACKs. |
| `ALL` | 6 | All full replicas of the partition. |

**Crucial scenario:** an app in `dc1` writes at `LOCAL_QUORUM`, gets ACKs from two replicas in `dc1`, and an app in `dc2` reads at `LOCAL_QUORUM`. The two quorums operate on **two disjoint replica sets**. `W = 2` in `dc1` and `R = 2` in `dc2` **do not overlap**, even though both requests say QUORUM.

You cannot conclude `dc2` sees the new write the moment `dc1` returns success. Data propagates to `dc2` afterward, and repair resolves lingering discrepancies.

### Choosing CL by Practical Requirements

| Goal | Direction | Trade-Off |
| --- | --- | --- |
| Normal read/write guarantees needed only in local DC | `LOCAL_QUORUM` when topology fits | Does not wait for quorum in remote DCs. |
| Confirm write achieved quorum in every DC | `EACH_QUORUM` for writes where supported | Latency and availability depend on multiple DCs. |
| Cluster-wide quorum needed | `QUORUM` when scope and latency are acceptable | Cross-DC network outages can disrupt operations. |
| Prioritize latency/availability, tolerate occasional stale reads | `LOCAL_ONE` | Less overlap; monitor convergence. |

**Note:** `EACH_QUORUM` here is a **write consistency level**, not a standard read level. And CL does not change RF, topology, or repair mechanics.

## 6. Which Discrepancies Must Repair Handle?

| Source of Divergence | What Happens? | Why Isn't Quorum Enough? |
| --- | --- | --- |
| Replica disconnected while write reached `ONE` or quorum | Some replicas missed the mutation | CL only requires its ACK count. |
| Hints expired, capped, or failed to replay | Long-absent replica can miss many mutations | Hinted handoff is not an infinite complete sync log. |
| Partition or clustering range rarely read | No chance for read repair to spot mismatches | Read repair only touches actually read ranges. |
| `DELETE` or TTL creates tombstones while another replica holds old data | Deleted data may not have reached all replicas | Quorum delete writes do not wait for every replica to ACK. |
| Multi-DC writes or network partitions | One DC may temporarily see stale versions | Local quorum in one DC does not cover another DC. |
| Bootstrapping, node replacement, topology changes | Data needs streaming and verification across new token ranges | Metadata/topology changes do not prove all files synced. |
| Concurrent writes / timestamp skew | Replicas may temporarily hold differing versions | Quorum does not replace conflict resolution or transaction isolation. |

### Why Can a Missed Tombstone Become a "Zombie"?

Suppose N3 is offline when N1 and N2 receive a `DELETE` at `LOCAL_QUORUM`:

~~~mermaid
flowchart LR
    A["N1: tombstone t2"] --> Q["Quorum read can return: deleted"]
    B["N2: tombstone t2"] --> Q
    C["N3: stale data t1"] --> D["N3 still missed the delete"]
    D --> E["Offline long, repair missed"]
    E --> F["Tombstones on N1/N2 purged too early"]
    F --> G["N3 returns; data t1 risks reappearing"]
~~~

A table's `gc_grace_seconds` helps retain tombstones long enough for absent replicas to receive deletions. However, **grace does not run repair by itself**. If sync cycles are missed and deletion markers are purged while a stale replica still exists, deleted data can come back to life.

This explains why scheduling **anti-entropy repair** is necessary, especially for tables with heavy `DELETE`s, TTLs, and cold partitions. Lowering `gc_grace_seconds` solely to reclaim disk without controlling repair is a risky decision.

## 7. Hinted Handoff, Read Repair, and Anti-Entropy Repair: Three Roles

### 7.1. Hinted Handoff: Catching Up Temporarily Unavailable Replicas

When a replica is unavailable, Cassandra can store a **hint** on an eligible node to forward the mutation later. Hints cover short-term gaps, bounded by **retention duration, configuration, disk space, hint-holder failures, and replay conditions**.

A hint **is not** a full replica and **does not guarantee** synchronization after long outages. Write CL `ANY` can even return success via a hint under eligible conditions before any full replica can serve the new data on reads. Therefore never use `ANY` to assume data is immediately readable.

### 7.2. Read Repair: Healing Data Observed Differing on Reads

When a coordinator receives mismatched data/digests, it can fetch full data to reconcile and repair divergent replicas. Whether behavior is **blocking** or **no read-path write-back** depends on version and configuration options (such as table `read_repair` on supported releases).

Read repair makes subsequent queries more consistent within the compared slice, yet:

- Does not scan all token ranges or keyspace history.
- Does not guarantee repairing a replica that did not participate in that request.
- May never touch rarely read rows/partitions.
- Does not replace periodic anti-entropy repair.

### 7.3. Anti-Entropy Repair: Comparing Data Across Replicas

**Anti-entropy repair** compares data ranges across responsible replicas—typically using summary comparisons like Merkle trees—and streams missing/differing data to bring replicas into alignment.

It targets **table/keyspace token ranges**, regardless of whether applications issue `SELECT`s for those partitions.

| Mechanism | Primary Trigger | Typical Scope | Limitations |
| --- | --- | --- | --- |
| Hinted handoff | Replica temporarily misses a write | Missed mutations with valid remaining hints | Incomplete / bounded. |
| Read repair | Read detects data/digest mismatch | Actually queried data and involved replicas | Does not audit all data. |
| Anti-entropy repair | Planned maintenance job | Token ranges and replicas of keyspace/table | Requires resource planning, monitoring, and full-scope completion. |
| Compaction | Per-node SSTable management policy | Local data inside selected SSTables | Does not sync from other replicas. |
| Backup / snapshot | Recovery plan | Recovery points per retention | Repair cannot undo accidental deletes replicated everywhere. |

**Repair is not replication factor, not consistency level, and not backups.** Increasing RF or changing CL does not erase accumulated divergence; local compaction likewise cannot conjure data missing from another replica.

## 8. Designing a Safe Repair Schedule

### 8.1. Relationship to `gc_grace_seconds`

If a table uses `gc_grace_seconds = 864000` (10 days), treat that as a reference boundary when scheduling maintenance for replicas that missed tombstones. Never interpret it as "running repair once right on day ten is always enough."

A practical policy must:

1. Ensure **all relevant token ranges/replicas** complete repair within your organization's safety window, leaving headroom for retries and incidents.
2. Monitor and remediate **failed or partial repairs**; launching a command does not mean the work finished.
3. When a replica has been offline **longer than the safety limit**, evaluate **rebuild/replace per runbook** instead of blindly reintroducing stale node data.
4. Tune schedules around storage volume, table count, TTL/delete rates, network bandwidth, disk load, and compaction policy.
5. Distinguish **incremental/full repair**, DC scope, and options based on your **Cassandra version**; never switch modes without understanding repaired/unrepaired SSTable state.

**Grace alone does not protect against all divergence.** Non-delete writes can also be missed on a replica; data slices remain divergent until repair or another sync mechanism finishes.

### 8.2. When to Investigate Urgently

- One or more nodes have been down for an extended period, especially on tables with TTLs/deletes.
- Repairs repeatedly fail, pending compactions grow, or network streaming bottlenecks.
- `LOCAL_ONE` and `LOCAL_QUORUM` reads return different results for the same data after writes have settled.
- Cross-DC reads observe stale data past expected replication lag.
- Tombstone warnings, suspected zombie data, or confirmed replica mismatches.

Differing read outputs alone are **insufficient** to conclude a node has a bad disk; correlate timestamps, CL, traces, topology, repair history, and concurrent write workloads.

## 9. CQL Practice: Observing Quorums and Returned Data

### 9.1. Creating a Table with a Query-Driven Partition Key

Lab example in DC `dc1` with at least three nodes. Adjust DC/RF to match your environment before running:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry_lab.readings_by_device_day (
    device_id text,
    event_day date,
    recorded_at timestamp,
    event_id uuid,
    reading decimal,
    PRIMARY KEY ((device_id, event_day), recorded_at, event_id)
) WITH CLUSTERING ORDER BY (recorded_at DESC, event_id ASC)
  AND gc_grace_seconds = 864000;
~~~

The composite partition key `(device_id, event_day)` determines the token and replica group. `recorded_at` and `event_id` uniquely identify each reading and allow time-ordered reads **within the partition**. No cluster-wide token scan is needed to fetch one device's data for a day.

### 9.2. Writing and Reading at `LOCAL_QUORUM`

In `cqlsh`:

~~~sql
CONSISTENCY LOCAL_QUORUM;
TRACING ON;

INSERT INTO telemetry_lab.readings_by_device_day
    (device_id, event_day, recorded_at, event_id, reading)
VALUES
    ('device-7', '2026-11-21', '2026-11-21T03:00:00Z',
     123e4567-e89b-42d3-a456-426614174001, 21.75);

SELECT recorded_at, event_id, reading
FROM telemetry_lab.readings_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21';

TRACING OFF;
~~~

With RF = 3 in `dc1`, both `LOCAL_QUORUM` writes and reads require **two replica responses** in `dc1`. Tracing can show the coordinator, participating endpoints, inter-node messages, and read cost. **A successful trace does not prove the remaining replica is synchronized.**

Switch CL to observe semantics (controlled lab only):

~~~sql
CONSISTENCY LOCAL_ONE;

SELECT recorded_at, event_id, reading
FROM telemetry_lab.readings_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21';
~~~

If data has converged, results match. If replicas diverge, `LOCAL_ONE` may read from a lagging copy. Never induce divergence by stopping nodes or altering storage on production clusters.

### 9.3. Testing Tombstones and Repair Responsibility

~~~sql
CONSISTENCY LOCAL_QUORUM;

DELETE FROM telemetry_lab.readings_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND recorded_at = '2026-11-21T03:00:00Z'
  AND event_id = 123e4567-e89b-42d3-a456-426614174001;

SELECT recorded_at, event_id, reading
FROM telemetry_lab.readings_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21';
~~~

Normally zero rows return, yet **empty results do not mean the tombstone was purged or every replica received the delete**. Tombstone cleanup must respect grace, repair, and safe compaction.

### 9.4. Observing Cluster Health and Repair Tasks

In a lab or per an approved runbook:

~~~bash
nodetool status
nodetool netstats
nodetool compactionstats
~~~

`nodetool status` checks node/DC/rack up/down status; `netstats` helps inspect streaming/hints where applicable; `compactionstats` shows background compaction. None of them **prove on their own** that all replicas hold identical data.

Sample repair command **for lab reference only**—never run arbitrarily in production:

~~~bash
nodetool repair telemetry_lab readings_by_device_day
~~~

Arguments, default mode (incremental/full), processing scope, load limits, and completion tracking must follow your version and operational runbook. **One command succeeding on one node does not prove all ranges cluster-wide were repaired.** You need topology coverage planning and completion verification.

## 10. Java Driver 4.x: CL Is a Statement Property

Java applications should define partition keys clearly, use prepared statements, set CLs per business requirements, and treat timeouts as **unknown outcomes**.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.math.BigDecimal;
import java.net.InetSocketAddress;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class QuorumReadingExample {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            UUID eventId = UUID.fromString(
                    "123e4567-e89b-42d3-a456-426614174001");

            PreparedStatement insert = session.prepare(
                    "INSERT INTO telemetry_lab.readings_by_device_day " +
                    "(device_id, event_day, recorded_at, event_id, reading) " +
                    "VALUES (?, ?, ?, ?, ?)");

            BoundStatement write = insert.bind(
                    "device-7",
                    LocalDate.of(2026, 11, 21),
                    Instant.parse("2026-11-21T03:00:00Z"),
                    eventId,
                    new BigDecimal("21.75"))
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
            session.execute(write);

            PreparedStatement select = session.prepare(
                    "SELECT recorded_at, event_id, reading " +
                    "FROM telemetry_lab.readings_by_device_day " +
                    "WHERE device_id = ? AND event_day = ?");

            BoundStatement read = select.bind(
                    "device-7", LocalDate.of(2026, 11, 21))
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            for (Row row : session.execute(read)) {
                System.out.println(row.getInstant("recorded_at")
                        + " -> " + row.getBigDecimal("reading"));
            }
        }
    }
}
~~~

**Explanation:**

1. Partition key `(device_id, event_day)` gives the driver enough data to compute routing keys and prefer replicas when token-aware routing is enabled.
2. `LOCAL_QUORUM` on writes and reads creates overlap **within `dc1`**, given `dc1` RF=3 and section 3's assumptions holding.
3. `withLocalDatacenter("dc1")` must match the real data center name. `127.0.0.1` is for local lab illustration only; production requires TLS/authentication and proper contact points.
4. **A write timeout does not prove the write failed.** Some replicas may have applied it before the client received enough ACKs; retries must use stable event IDs, respect idempotency, and avoid accidentally overwriting newer data.
5. Even with `LOCAL_QUORUM` on both statements, application code **does not heal unread partitions**. Replication monitoring and planned repairs remain necessary.

## 11. Common Misconceptions

| Claim | Verdict | Explanation |
| --- | --- | --- |
| "RF = 3 means every write waits for three nodes." | **False** | CL sets the ACK threshold; `LOCAL_QUORUM` needs two in an RF=3 DC. |
| "`R + W > RF` means every replica holds the new record." | **False** | It ensures response-set overlap, not full synchronization. |
| "Two `LOCAL_QUORUM` calls in two DCs always overlap." | **False** | Replica sets in different DCs can be completely disjoint. |
| "Read repair automatically scans the whole keyspace." | **False** | It only processes data touched by actual reads and matching policies. |
| "Hints can replace repair even after very long node outages." | **False** | Hints have time/size caps; anti-entropy repair is still needed. |
| "`gc_grace_seconds` triggers repair automatically when due." | **False** | Grace is a tombstone retention window, not a repair scheduler. |
| "Repair and compaction are the same thing." | **False** | Repair synchronizes replicas; compaction manages local SSTables. |
| "Write `LOCAL_QUORUM` success in dc1 means dc2 has quorum." | **False** | No ACKs from dc2 are required for `LOCAL_QUORUM` success in dc1. |
| "Running repair can undo any accidental `DELETE`." | **False** | Repair spreads tombstones; you need backups to undo logic mistakes. |
| "Quorum read/write is a cluster-wide serializable transaction." | **False** | Cassandra has eventual-consistency/timestamp semantics; LWT is a separate mechanism for limited linearizable conditions. |

## 12. Self-Check Exercises with Answers

**Exercise 1.** A DC has RF = 3. A `LOCAL_QUORUM` write is ACKed by N1, N2; N3 lacks the mutation. A `LOCAL_QUORUM` read contacts N2, N3. Why can it return the new data?

**Answer:** The sets `{N1,N2}` and `{N2,N3}` overlap at N2. Without concurrent writes and under timestamp rules, the coordinator reconciles newer data on N2 against stale data on N3.

**Exercise 2.** After the request in Exercise 1, why is repair still necessary?

**Answer:** N3 might not be fully healed, and other unread rows/partitions can still diverge. Read repair is not a keyspace-wide scan; anti-entropy repair synchronizes designated token ranges.

**Exercise 3.** RF = 5 in one DC. How many ACKs does `QUORUM` require? If both write and read use `QUORUM`, must the sets intersect?

**Answer:** `floor(5/2)+1 = 3`. Two 3-node subsets out of 5 nodes must share at least one node, since `3+3>5`.

**Exercise 4.** A keyspace has `dc1: RF=3`, `dc2: RF=3`. A write in dc1 uses `LOCAL_QUORUM`. An immediate read in dc2 also uses `LOCAL_QUORUM`. Does `2+2>3` guarantee reading the new write?

**Answer:** **No.** The two quorums operate in **two different DCs**, not the same three-replica set. The remote DC may not have received the mutation yet.

**Exercise 5.** A replica was offline longer than hint retention with no repair run; the table sees many `DELETE`s. Why is lowering `gc_grace_seconds` to purge tombstones dangerous?

**Answer:** The offline replica may still hold deleted data. If tombstones on other replicas are purged before deletes reach the stale replica, deleted data risks resurrection; follow repair/rebuild runbooks and safety checks.

**Exercise 6.** After a successful `LOCAL_QUORUM` write, a `LOCAL_ONE` read from N3 returns the stale value. Does that prove the quorum write failed?

**Answer:** No. `LOCAL_QUORUM` only needs two of three ACKs; N3 may still lag. `LOCAL_ONE` reading from an eligible replica can observe stale data before convergence.

**Exercise 7.** An application performs frequent read-modify-write balance updates on the same row using `LOCAL_QUORUM` for both. Does that prevent lost updates under concurrent clients?

**Answer:** **No.** CL does not turn a read-modify-write cycle into an isolated transaction. Redesign the update flow, enforce concurrency control, or use conditional mechanisms (such as LWT when appropriate) while accounting for their cost and limits.

## 13. Decision Flow: Is Quorum Enough or Is Repair Needed?

~~~mermaid
flowchart TD
    A["Cassandra read/write"] --> B["Identify partition key, RF, and topology"]
    B --> C["Choose CL matching consistency/latency goals"]
    C --> D{"Do R and W overlap within the same replica set?"}
    D -->|Yes| E["Helps reads see ACKed writes under assumptions"]
    D -->|No| F["May observe stale data, especially cross-DC"]
    E --> G{"Have all replicas/partitions been checked?"}
    F --> G
    G -->|No| H["Hints/read repair cover only limited slices"]
    G -->|Yes| I["Still monitor errors, tombstones, and repair history"]
    H --> J["Schedule full-coverage anti-entropy repair"]
    J --> K["Verify repair outcomes and scope"]
    I --> K
    K --> L["Monitor replica convergence and tombstone safety"]
~~~

**Core takeaway:** `R + W > RF` explains **why two quorums over the same replica group must intersect**; it **does not mean every replica already matches**. Hinted handoff patches short outages, read repair fixes discrepancies noticed on reads, and **anti-entropy repair** is the maintenance job that compares and synchronizes replicas—especially cold partitions and tombstones risking zombie data. Designing DC-appropriate CLs, monitoring replicas, and completing repairs go hand in hand.
