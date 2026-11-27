# Causes of Data Divergence Across Replicas

## Lesson Objectives

Apache Cassandra is a **distributed, wide-column** database where a partition is typically replicated across multiple nodes to maintain availability when machines or networks fail. For a period of time, the replicas of the same partition **may contain different versions**: one node has received a new update while another has not; one replica still retains deleted data; or competing writes are assigned different timestamps.

This is not necessarily data corruption: Cassandra's read/write *consistency level (CL)* allows choosing between the number of acknowledgments to wait for, latency, and availability. However, if divergence persists, repair processes do not run properly, or tombstones are purged too early, data can be missing, read as stale, or even reappear after deletion.

This lesson belongs to the **Replica Synchronization** chapter in the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. It covers the write/read path, replication, consistency, hinted handoff, read repair, anti-entropy repair, compaction, TTL, and error handling; examples use CQL and Java Driver 4.x.

After this lesson, you will be able to:

1. Explain why **RF = 3 does not mean all three replicas are always identical at every point in time**.
2. Distinguish between temporary replica divergence, timestamp conflicts, delete/tombstone issues, and incorrect data caused by the application writing to **different tables**.
3. Explain the impact of `ONE`, `LOCAL_QUORUM`, `ALL`, and datacenter placement on update visibility.
4. State the causes, limitations, and distinct roles of **hinted handoff**, **read repair**, **repair**, and **streaming**.
5. Verify a scenario using CQL, observing write timestamps, logs, replica metrics, and Java code.
6. Design diagnostic, failure-testing, and operational procedures to reduce divergence without harming production data.

## 1. What Is a Replica, and What Does "Different" Mean?

Suppose a keyspace uses `NetworkTopologyStrategy` with **RF = 3** in a datacenter with enough nodes. A partition with key `(tenant_id, order_id)` is stored across three replicas according to the data placement strategy.

```text
                 Java Client / cqlsh
                         |
                    Coordinator
                         |
             +-----------+-----------+
             |           |           |
          Replica A    Replica B   Replica C
          status=PAID   PENDING     PAID
          rev=12        rev=11      rev=12
```

In the diagram, A and C already have a newer version than B. This can happen if B was slow or disconnected during the write, if the client response only required a subset of replicas to acknowledge, or if synchronization has not yet completed.

**Distinguishing three types of "different":**

| Type | Example | Meaning |
| --- | --- | --- |
| **Different data state within the same partition** | A has `PAID`, B still has `PENDING` for the same cell | Divergence between replicas that needs analysis |
| **Different physical data on SSTables** | A has more recent SSTables than B, but logical queries return the same value | Not enough to conclude a consistency error; compaction/flush occurred at different times |
| **Difference between business projections** | `orders_by_id` has `PAID`, `orders_by_status_day` still has a `PENDING` row | Two tables/partitions serving different query shapes; **replica repair does not automatically fix** missing application mutations |

In Cassandra, each cell also carries metadata such as a **write timestamp** and possibly a TTL/tombstone. Two replicas may receive mutations at different times, yet after applying the same valid mutations they will converge according to conflict resolution rules. However, a late-arriving business event or clock skew can cause **all three replicas to converge to a business-incorrect value**; that is a different problem from a single replica lagging behind.

### 1.1. "Write Succeeded" Does Not Mean Every Replica Has Received It

The replication factor determines the intended replica set, whereas the operation's **consistency level** determines the number of responses required before reporting success to the client. With RF = 3, a `ONE` write can complete as soon as one replica acknowledges, while the other replicas are still receiving or waiting to apply the change.

The coordinator may still send the mutation to **multiple or all eligible replicas**, even when the client only requests `ONE`. Therefore, you should not say "a ONE write only writes to one node"; more accurately, **the client only waits for the number of acknowledgments required by that CL**.

## 2. Write Path and Read Path of a Partition

### 2.1. Conceptual Write Path

A write request arrives at the coordinator, which identifies the responsible replicas based on the token/replication strategy and forwards the mutation:

```text
t0   Client sends UPDATE(status=PAID) with CL=ONE
     |
t1   Coordinator routes mutation to A, B, C
     |
t2   A applies mutation and ACKs
     |             B is slow / disconnected
     |             C is still processing
t3   Coordinator satisfies CL=ONE -> returns success
     |
t4   C applies mutation
     |
t5   B may receive it later via an appropriate recovery mechanism
```

The interval from `t3` to `t5` is a window during which replicas can diverge. Actual behavior depends on topology, network, overload, Cassandra version, and enabled background mechanisms. A client cannot infer the time `t5` solely from the success of a `ONE` write.

### 2.2. Conceptual Read Path

On a read, the coordinator contacts replicas according to the CL and the read algorithm. Cassandra may use **data responses** and **digest responses** to detect mismatches among the replicas participating in a read; the exact handling, read repair, and blocking behavior depend on the version and configuration.

For example, two `ONE` reads at different times may be served by different replicas, so one read sees `PAID` while another sees `PENDING` if the data is still divergent. This is a **possibility**, not a deterministic outcome: routing, speculative retry, replica selection, and whether a replica has caught up make the result non-deterministic.

A `LOCAL_QUORUM` read within the same DC has a much higher chance of detecting/selecting newer data when participating replicas differ, but it **does not replace anti-entropy repair across all replicas**.

## 3. Cause 1: Writing and Reading at Consistency Levels Lower Than ALL

Cassandra lets you tune the acknowledgment level to balance availability and latency.

| CL | High-Level Meaning in an RF=3 DC | Risk / Trade-off |
| --- | --- | --- |
| `ONE` | One replica acknowledges per CL | Writes/reads can usually proceed when some replicas do not respond; reads may see stale data |
| `LOCAL_QUORUM` | Majority of replicas in the local DC; with RF=3, typically 2 | Requires two replicas to respond; ensures proper quorum intersection |
| `ALL` | Every required replica within the corresponding consistency scope | Lower availability when replicas fail/lag; not a substitute for repair |
| `LOCAL_ONE` | One replica in the local DC | Prioritizes local latency/availability; can read stale data |
| `EACH_QUORUM` | Quorum in each DC according to configuration | Cost and availability depend on multiple DCs; do not choose arbitrarily |

**Note:** `ALL` and `EACH_QUORUM` have semantics tied to how replicas/DCs are required; the table above does not replace version-specific documentation. In multi-datacenter deployments, you must calculate RF per DC and understand when a request waits only on local replicas.

### 3.1. Why Is LOCAL_QUORUM Useful?

With `RF = 3` in one DC, quorum is 2. Any two subsets of 2 replicas out of 3 **must intersect in at least 1 replica**:

```text
Write LOCAL_QUORUM: A, B acknowledge
Read  LOCAL_QUORUM: B, C participate
Intersection: B

W + R > RF
2 + 2 > 3
```

Quorum intersection is the foundation for ensuring reads see completed writes under appropriate system assumptions. However, do not overgeneralize this to "every SELECT is a globally linearizable transaction": there are still concurrent writes, conflicting timestamps, TTL/tombstones, failures, and reads spanning multiple tables/partitions. **You do not get a multi-partition SQL snapshot simply by choosing LOCAL_QUORUM.**

### 3.2. Writing at LOCAL_QUORUM, Reading at ONE

If a write achieves quorum, a subsequent read using only `ONE` that hits a replica which has not yet received the update **can still return the stale value**. This is why you must evaluate the **write/read CL pair**, rather than just choosing a strong write CL and assuming every reader sees fresh data.

### 3.3. Writing in the Local DC, Reading from Another DC

With `NetworkTopologyStrategy` and `LOCAL_QUORUM`, writes complete based on the **local DC** quorum and do not necessarily wait for replicas in other DCs. A `LOCAL_ONE` or `LOCAL_QUORUM` read in a remote DC may have a staleness window if replicas there have not yet received the update.

This is **inter-datacenter lag** for the same partition, which is different from the application forgetting to write to a projection table. When cross-DC reads are required immediately after writes, you must establish a contract covering the target DC, CL, and acceptable convergence latency; do not assume that RF in the primary DC automatically guarantees freshness in every region.

## 4. Cause 2: Disconnected, Dead, or Overly Slow Nodes

A replica can miss a mutation because:

- The node shut down, restarted, suffered disk failure, or exhausted resources.
- Network partitions or high latency/jitter caused messages to arrive late.
- CPU, heap/GC, thread pools, disk I/O, or compaction backlog slowed down replica processing.
- Too many concurrent requests caused long queues, timeouts, or rejections.
- One replica failed while applying the write while other replicas succeeded.

If the CL only requires a subset of replicas to acknowledge, the coordinator can return success even while one replica is unavailable. When the node comes back, it **does not automatically know every mutation it missed** merely because the restart completed. Cassandra has mechanisms to catch up on data, each with its own conditions and scope.

### 4.1. A Timeout Does Not Prove a Mutation Failed

Suppose a client sends an `UPDATE`, and the coordinator or replicas actually processed it, but the ACK does not reach the client before the timeout expires. The client sees a timeout error, yet the mutation **may already have been applied on one or more replicas**.

For idempotent operations with a fixed key, the application can retry according to policy and reconcile the result. However, retrying is **not safe by default** if it:

- Generates a new `event_id` for the same event.
- Changes the partition key or bucket by using the retry timestamp.
- Uses a new timestamp that lets an older business value overwrite a newer update.
- Unintentionally refreshes TTL or behaves differently on collection/counter operations.

You must distinguish between **the client did not receive an ACK** and **the database definitely did not receive the mutation**.

## 5. Cause 3: Hinted Handoff Has Limited Scope

When a coordinator knows a replica is temporarily unresponsive, Cassandra can store a **hint** containing the mutation to replay to that replica later, if enabled and permitted by version/configuration conditions.

```text
      Coordinator
          |
          +--> Replica A: write succeeded
          +--> Replica B: write succeeded
          +--> Replica C: currently down
                    |
             Coordinator stores hint (if allowed)
                    |
             C returns -> replay hint
```

**Hinted handoff is a best-effort fast recovery mechanism**, not an infinite durable queue, and it **does not replace repair**. Conditions where hints may be insufficient:

1. The replica is absent longer than the configured hint window.
2. The coordinator no longer holds the hint or fails before delivering it.
3. The feature is disabled, throttled, or restricted by topology/replica type.
4. Some mutations did not pass through a coordinator retaining enough state to store a hint.
5. Hints were delivered, yet discrepancies remain that require data-level reconciliation.

You should not design SLAs assuming "every missed write is guaranteed to be recovered automatically by hints." After prolonged outages, you must evaluate **planned repair**, replica health, and actual recovery capability.

## 6. Cause 4: Read Repair Only Detects What a Read Touches

When a read contacts replicas that hold different data, Cassandra can compare digests/data and repair discrepancies detected within the **read scope** according to the version/configuration's read repair mechanism.

Example:

```text
Replica A: status = PAID    (newer write timestamp)
Replica B: status = PENDING (older write timestamp)
Replica C: status = PAID

Read across multiple replicas:
  -> can detect digest mismatch
  -> reconciles data per Cassandra rules
  -> repairs relevant data on participating replicas
```

Key points to remember:

- Read repair **does not scan the entire keyspace**; it is triggered only for the data/columns/partitions touched by that read.
- A partition or row that is **never read** can remain divergent if other synchronization mechanisms are missing.
- Some read repair strategies can be **blocking** and affect read latency; exact settings and semantics vary by Cassandra version.
- Not all replicas participate in every read, especially at low CLs.
- Read repair cannot synthesize mutations for **another business table** that the application never wrote to.

Therefore, reading a few keys repeatedly and "seeing identical results" **does not prove** that all replicas across all token ranges have converged.

## 7. Cause 5: Timestamp Conflicts and Unsynchronized Clocks

Cassandra normally resolves updates to the same cell based on the **write timestamp**, along with tombstone rules and tie-breaking when needed. A write that arrives at the server **later in wall-clock time** but carries an **older** write timestamp may lose to existing data.

Conversely, an event that is **older in business terms** but arrives later and gets assigned a newer timestamp can overwrite the current value.

### 7.1. Example: Business Updates Arriving Out of Order

```text
Revision 10: order = PENDING (event occurred earlier)
Revision 11: order = PAID    (event occurred later)

Consumer applies revision 11 first.
Later retries revision 10, assigning a new write timestamp.

Result can become PENDING even though business state should be PAID.
All replicas can even synchronize completely on the wrong PENDING value.
```

This is a critical lesson: **replicas having the same value does not mean the business state is right**. Storing a `revision bigint` column alongside the data **does not automatically turn Cassandra into a revision comparator**. The application needs a source of state, ID/sequence ordering rules, or conditional updates.

### 7.2. Impact of Clock Skew

Timestamps can be generated through coordination between the client/driver and Cassandra depending on configuration. If writers have significantly skewed clocks, a writer with a clock **running ahead** can generate very large timestamps that make it hard for other writers' updates to overwrite its data for a period of time.

Symptoms you may encounter:

- Business-newer operations fail to appear because they carry a smaller timestamp than the stored value.
- Some replicas receive mutations late, yet all eventually converge to the timestamp winner.
- TTLs and deletes exhibit hard-to-explain behavior when combined with skewed timestamps/clocks.

Synchronizing node/client clocks and monitoring clock drift are vital operational practices. However, **synchronized clocks do not replace business ordering controls** if older events can be replayed after a newer revision already exists.

### 7.3. Using WRITETIME to Investigate

For a non-counter regular column, `WRITETIME(column)` shows the write timestamp Cassandra stored for that cell, in **microseconds**:

```sql
SELECT status, revision, WRITETIME(status) AS status_write_time
FROM replica_lab.orders_by_id
WHERE tenant_id = ? AND order_id = ?;
```

`WRITETIME` helps detect anomalous timestamps, but it does not tell you **business time** or "which node received it first." A newer timestamp value does not guarantee a business-newer event. Functional rules such as `revision` must still be designed and verified separately.

## 8. Cause 6: DELETE, TTL, Tombstones, and Resurrection Risk

In a distributed system, deleting data is not simply removing bytes on one replica. Cassandra uses **tombstones** to represent deleted/expired data and prevent a replica holding older data from bringing that value back to life.

### 8.1. Delete Scenario While a Replica Is Down

```text
t0  A, B, C all hold row X.
t1  Replica C loses connectivity.
t2  Client runs DELETE X; A and B receive tombstone, write satisfies required CL.
t3  C still holds value X because it missed the DELETE.
t4  C remains absent for a long time; tombstones on A/B become eligible for purge.
t5  C returns with the old value X.
```

If the system **purges tombstones before the replica that missed the delete is safely synchronized** and no other safeguard is in place, there is a **zombie/resurrection** risk: deleted data reappears.

Therefore:

- Schedule **repair** appropriately so replicas do not miss deletes for too long.
- Follow operational procedures for prolonged node downtime, node replacement, and repair verification.
- Do not lower `gc_grace_seconds` arbitrarily just to reduce tombstone counts.
- Monitor TTLs, tombstones, compaction, and data age according to policy.

Exact details of when a tombstone can be purged depend on Cassandra version, compaction strategy, configuration, and repair/replica state; do not assume that merely waiting past one parameter will make SSTables vanish immediately.

### 8.2. TTL Is Not Immediate Physical Deletion

A cell with a TTL expires logically after the specified duration. Expired data should not be returned as live once expiry takes effect, yet the SSTable/tombstone may remain on disk until compaction and safe-purge conditions are met.

Two replicas with different SSTable states do not necessarily return different query values. Conversely, **clock skew** and mutations involving TTL/rewrites can make verification harder, requiring collection of timestamps, TTLs, machine clocks, and logs.

### 8.3. Compaction Is Not Inter-Replica Repair

**Compaction** primarily organizes, merges, and purges SSTables locally on a node according to policies and conditions. It does not contact other replicas to detect every missed mutation.

**Repair** compares data across the replicas responsible for token ranges and synchronizes differences using anti-entropy algorithms. The two tasks are distinct; a node can compact cleanly while still missing mutations lost during a network outage.

## 9. Cause 7: Insufficient, Interrupted, or Mis-Scheduled Repair

Repair is the primary mechanism for reducing divergence among replicas in Cassandra. Depending on version and configuration, **full/incremental repair** may be used, with differences in data coverage, repaired state tracking, and operational behavior.

Reasons replicas still diverge:

1. Repair has not been run for the relevant token range/keyspace/table.
2. Repair failed, was canceled mid-run, or did not complete all required sessions.
3. The repair schedule exceeds the safety window for deleted/TTL data, especially with long-offline nodes.
4. A new replica or recovered node has not completed streaming/repair.
5. Operations only checked a single "repair succeeded" output without verifying scope, other jobs, or failure metrics.
6. Confusing **read repair** on occasional queries with **full data synchronization repair**.

### 9.1. What Does Anti-Entropy Repair Do?

Conceptually:

```text
Select token ranges + responsible replicas
       |
       v
Compare data state (e.g., Merkle trees/digests per mechanism)
       |
       +--> Identical: no need to stream that slice
       |
       +--> Divergent: synchronize relevant data
       |
       v
Complete, track per-session status and errors
```

Repair can consume significant CPU, disk I/O, network, and compaction resources; it should not be run cluster-wide all at once in production without planning. For a given version/topology, choose schedules, scope, and execution methods according to tested operational procedures.

### 9.2. Repair Does Not Replace the Business Source of Truth

Suppose an application maintains:

```text
orders_by_id               -> current order status
orders_by_customer_month   -> list by customer/month
orders_by_status_day       -> status queue
```

If a consumer forgets to write `orders_by_status_day` after `orders_by_id` was updated, the replicas of the **status table** may be 100% synchronized on **missing** data. Repair has no way of knowing it should generate missing rows based on the ID table.

This is **projection consistency**, which requires durable events, retry/idempotency, and application-level reconciliation. Do not attribute every discrepancy between two APIs to "Cassandra replicas are out of sync."

## 10. Cause 8: Topology Changes, Streaming, and Ownership Transition Windows

When adding nodes, replacing nodes, decommissioning, or moving token ranges, data must be **streamed** to the newly responsible nodes. During transitions, there may be pending ranges, old/new replicas, and phases where data is not yet fully distributed.

Items to check:

- Which tokens/ranges are changing ownership, and which replicas are responsible afterward?
- Did streaming complete successfully? Were there errors/timeouts or resource exhaustion on the target node?
- New writes may occur while topology changes; system mechanisms must ensure they are handled per the current ring state.
- Is repair or an additional verification step required after replacing a node, per cluster version/procedures?
- Is the application using stale topology/datacenter settings in the driver, or routing through an unintended DC?

Do not manually move tokens, delete SSTables, or manipulate the ring to "force replicas to match" in production without identifying the root cause and having a plan. Streaming and repair are resource-intensive operational tasks for I/O and network that require throttling and monitoring.

## 11. Cause 9: Misunderstandings About LWT, BATCH, Counters, and Denormalization

Several scenarios look like "replicas differ" when they actually stem from **operation semantics** or **application modeling**:

| Scenario | Common Misconception | Correct Understanding |
| --- | --- | --- |
| Two writers update the same status | Thinking the last write by wall-clock always wins | Cassandra resolves by write timestamp and cell rules; business version control is needed |
| `IF revision = ?` using LWT | Thinking all tables for the order are updated transactionally | LWT enforces conditions within its scope; it does not create a cross-projection SQL transaction |
| Logged `BATCH` across multiple partitions | Thinking every reader sees an all-or-nothing snapshot | Batch provides recovery atomicity semantics, **not cross-partition SQL isolation** |
| Counter incremented and retried after timeout | Thinking it is safe like upserting the same value | Counters have special semantics; retrying blindly is unsafe unlike idempotent writes |
| Write by ID, read by status from another table | Thinking strong CL will automatically populate the status table | Two representations have separate mutation paths requiring pipelines and reconciliation |
| Larger `WRITETIME` | Thinking this must be the newer business event | This is the cell write timestamp; do not infer business order from it |

When stronger consistency is required for conditional single-row updates, **LWT/CAS** may fit, though with cost and limitations. Do not treat LWT or batches as a "cure-all for every divergence" while ignoring partition mapping, late-arriving data, and partial failures.

## 12. Cause – Symptom – Remediation Matrix

| Cause | Common Observation | Appropriate Mechanism / Check |
| --- | --- | --- |
| Low write/read CL, update still propagating | `ONE` reads alternate between new and old | Check CL/RF/topology, verify with contract-aligned readback |
| Node down during write | One replica holds stale value | Node status, hints, repair, and downtime duration |
| Network timeout, lost ACK | Client reports timeout but data may have changed | Readback, idempotency, logs, and retry policy |
| Expired or incomplete hints | Node returns but still misses many writes | Evaluate repair schedule and data state |
| Read repair has not touched partition | Rarely read keys still have divergent replicas | Anti-entropy repair instead of spot-reading a few keys |
| Timestamp / clock skew | Business-newer update fails to win | `WRITETIME`, clocks, source revision, and writers |
| Tombstone purged before replica received delete | Deleted data risks reappearing | Check downtime, grace, repair, TTL, and compaction |
| Repair incomplete in scope or failing | Discrepancies persist long-term | Repair history, token ranges, failures, and metrics |
| Incomplete streaming / topology change | New node missing data or read/write errors | `nodetool status/netstats`, ring, and recovery plan |
| App missed mutation on secondary table | Two APIs return different statuses | Outbox/event log, reconciliation from business source |

## 13. Safe CQL Lab for Observation

Experiments should run in a **dedicated lab cluster**; never inject node/network faults or change consistency arbitrarily in production. Below is an example schema for one DC with **at least three nodes**, replacing `dc1` with your actual DC name.

### 13.1. Create Keyspace and Table

```sql
-- Use only in a test cluster; replace dc1 with the actual DC name.
CREATE KEYSPACE replica_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE replica_lab.orders_by_id (
    tenant_id text,
    order_id uuid,
    status text,
    revision bigint,
    changed_at timestamp,
    PRIMARY KEY ((tenant_id, order_id))
);
```

An easy-to-verify row:

```sql
INSERT INTO replica_lab.orders_by_id (
    tenant_id, order_id, status, revision, changed_at
) VALUES (
    'tenant-A',
    00000000-0000-4000-8000-000000000001,
    'PENDING', 1, '2026-11-21T09:00:00Z'
);
```

### 13.2. Observing cqlsh Consistency Levels

In **cqlsh**, `CONSISTENCY` is a session-level configuration command; it is **not** a CQL statement executed inside the Java driver:

```sql
CONSISTENCY ONE;

SELECT status, revision, changed_at, WRITETIME(status) AS write_ts
FROM replica_lab.orders_by_id
WHERE tenant_id = 'tenant-A'
  AND order_id = 00000000-0000-4000-8000-000000000001;

CONSISTENCY LOCAL_QUORUM;

SELECT status, revision, changed_at, WRITETIME(status) AS write_ts
FROM replica_lab.orders_by_id
WHERE tenant_id = 'tenant-A'
  AND order_id = 00000000-0000-4000-8000-000000000001;
```

On a healthy cluster, both queries will likely return the **same data**. That is normal. Divergence must be induced via controlled node/network scenarios in the lab and **is not guaranteed to appear on every `ONE` read**.

### 13.3. Controlled Node-Absent Scenario

Conceptual experiment plan:

1. Identify the three actual replicas for the partition using the cluster tool appropriate for your version; record topology and CL.
2. Ensure initial data reads consistently, collecting timestamps and metrics.
3. In a test environment **where you control the nodes**, make one replica temporarily unreachable for mutations; record the start time.
4. Send an update `status = PAID` with a CL low enough that the operation can still succeed on the remaining available replicas.
5. Read with `ONE` and `LOCAL_QUORUM` at recorded timestamps, comparing results and latency. Do not assume `ONE` must see stale data or that quorum always succeeds when a replica is missing.
6. Bring the replica back; observe hinted handoff if applicable, read behavior, and the repair procedure per version documentation.
7. Compare post-recovery results, logs/metrics, and remove all test configurations.

Keep timeouts and load low, and do not shut down multiple replicas simultaneously such that the lab cluster cannot meet the CL under test. Controlled node-failure experiments **are not advice to cause disruptions in production**.

### 13.4. Demonstrating Write Timestamp Conflicts Separately from Replica Lag

On a **different test key** to avoid interference, write two updates using lab-specified CQL write timestamps:

```sql
-- CQL timestamps are in microseconds; demonstration on a test key only.
UPDATE replica_lab.orders_by_id
USING TIMESTAMP 1700000001000000
SET status = 'PAID', revision = 2
WHERE tenant_id = 'tenant-lab'
  AND order_id = 00000000-0000-4000-8000-000000000099;

-- Write arriving later but carrying a lower timestamp.
UPDATE replica_lab.orders_by_id
USING TIMESTAMP 1700000000000000
SET status = 'PENDING', revision = 1
WHERE tenant_id = 'tenant-lab'
  AND order_id = 00000000-0000-4000-8000-000000000099;

SELECT status, revision, WRITETIME(status)
FROM replica_lab.orders_by_id
WHERE tenant_id = 'tenant-lab'
  AND order_id = 00000000-0000-4000-8000-000000000099;
```

Expect `status` to remain `PAID` and `revision` to remain 2, because the `PAID` write timestamp is larger even though the `PENDING` statement ran afterward. This **does not test replica lag**; it merely shows that application order and business timestamp are two separate concepts.

Do not use `USING TIMESTAMP` arbitrarily in production to "force" data to win conflicts. Timestamps do not replace a revision/state-transition control protocol.

## 14. Java Driver 4.x: Explicit CL Writes and Reads

In Java, consistency levels should be set via the driver API per statement or execution profile, not via cqlsh's `CONSISTENCY` command. Example using **DataStax Java Driver 4.x**:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.Instant;
import java.util.UUID;

public final class ReplicaConsistencyProbe {
    private final CqlSession session;
    private final PreparedStatement upsert;
    private final PreparedStatement read;

    public ReplicaConsistencyProbe(CqlSession session) {
        this.session = session;
        this.upsert = session.prepare(
            "INSERT INTO replica_lab.orders_by_id (" +
            "tenant_id, order_id, status, revision, changed_at) " +
            "VALUES (?, ?, ?, ?, ?)"
        );
        this.read = session.prepare(
            "SELECT status, revision, changed_at, " +
            "WRITETIME(status) AS status_write_time " +
            "FROM replica_lab.orders_by_id " +
            "WHERE tenant_id = ? AND order_id = ?"
        );
    }

    public void writeWithLocalQuorum(
        String tenantId, UUID orderId,
        String status, long revision, Instant changedAt
    ) {
        session.execute(
            upsert.bind(tenantId, orderId, status, revision, changedAt)
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        );
    }

    public Row readWithOne(String tenantId, UUID orderId) {
        return session.execute(
            read.bind(tenantId, orderId)
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
        ).one();
    }

    public Row readWithLocalQuorum(String tenantId, UUID orderId) {
        return session.execute(
            read.bind(tenantId, orderId)
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        ).one();
    }
}
```

**Scope of the example:** this is single-table lab probing code, not a transaction mechanism or complete error-handling system.

- `CqlSession` should be created for the service lifecycle and shared rather than opening a connection per request.
- `UUID` maps to the CQL `uuid` type, `Instant` maps to `timestamp`; `Row` may be `null` if the key does not exist.
- If the cluster lacks enough replicas to satisfy `LOCAL_QUORUM` in the local DC, writes/reads may fail; do not automatically interpret a timeout as "not written."
- Retrying the same key is an upsert, but generating a new revision/status from a stale source can cause a business regression. You must have a source revision and an idempotency policy.
- When investigating replica divergence, observe topology/routing and server metrics; calling `readWithOne` twice does not guarantee the two requests hit two different replicas.
- Measure latency, errors, call timestamps, and results together; do not just log `status` and guess which replica is wrong.

### 14.1. Network Errors and Retries

A client seeing a timeout may be in an **unknown outcome** state. Example handler:

```text
write(order, version, stableKey)
    |
    +-- success -> acknowledged per CL
    |
    +-- timeout -> DO NOT generate a new version/event_id
                    record metric + verify via readback
                    controlled retry per idempotency contract
                    avoid regressing when a newer version already exists
```

The driver provides retry policies, yet the application remains responsible for business semantics, especially with counters, collections, TTLs, and multiple projection tables. Do not retry infinitely or let failed requests cause a write storm while nodes are recovering.

## 15. Runbook for Diagnosing Divergent Replicas

When receiving reports like "reading the same key returns different results" or "deleted data reappeared," follow an ordered workflow to avoid misdiagnosis:

### 15.1. Step 1 — Determine Whether It Is the Same Data or Two Projections

Record:

```text
keyspace
table
full partition key
clustering key (if any)
column/value
requested consistency level
datacenter / client location
query timestamp
source event ID / business revision
```

If two screens read different tables, first check the **write path and projection sync lag**. Do not run a cluster-wide repair simply because two tables do not match.

### 15.2. Step 2 — Check Topology and Availability

Collect ring/node status appropriate for your Cassandra version:

```text
nodetool status
nodetool netstats
nodetool tpstats
nodetool compactionstats
```

The `nodetool` commands above are suggested tools/actions, not an automated script. Check DCs, RF, UP/DOWN replicas, streaming/hints, pending tasks, disk saturation, CPU/GC, and network. For a specific key, identify the exact **replica set for its token range** instead of guessing from node ordering in a dashboard.

### 15.3. Step 3 — Classify the Failure Mode

| Question | If Yes | Next Direction |
| --- | --- | --- |
| Was a node down or network degraded during the write? | Yes | Inspect hints, repair window, readback after recovery |
| Did the client experience a write timeout / unknown outcome? | Yes | Do not conclude the write failed; reconcile key/version |
| Do `ONE` and `QUORUM` reads differ on the same key? | Possibly | Check replica lag, timing, and CL; do not ignore in-flight writes |
| Is `WRITETIME` anomalous compared to event version? | Yes | Investigate clock drift and producer timestamps |
| Was `DELETE`/TTL data potentially missed? | Yes | Check tombstones/grace/repair and resurrection risk |
| Was there an incomplete node replacement / streaming? | Yes | Inspect topology and streaming/repair |
| Do two APIs read two projection tables? | Yes | Durable event log/reconciliation, not just replica repair |

### 15.4. Step 4 — Choose Appropriate Recovery

- Brief replica lag with active hints: observe catch-up per configuration and verify data afterward.
- Long node downtime or missed mutations: evaluate **repair/restore/replace** per the version runbook, checking disk capacity and scope first.
- Incorrect business timestamp: fix the **mutation producer and version rules**; repair only makes replicas agree on the timestamp winner.
- Risk of improper tombstone purge: **prioritize data preservation and investigation**; do not force compaction or lower grace.
- Secondary table missing rows: replay/reconcile from a trusted source; do not rely on replica repair.

Avoid running repair, full compaction, streaming, and heavy backfills concurrently without accounting for CPU, disk, I/O, and network. These operations can worsen an ongoing load incident.

### 15.5. Step 5 — Verify Recovery

Do not merely confirm a single `SELECT` returned the right value once. Gather evidence:

1. Node/replica set is stable; relevant streaming/repair completed with no critical errors.
2. Read at the required CL over defined intervals, verifying the same key/column/timestamp and version.
3. No abnormal backlog of hints/repair, timeouts, or dropped mutations.
4. Deleted/TTL data does not reappear in relevant test cases.
5. If the application maintains projections, business invariants have been reconciled separately.

## 16. Common Pitfalls

| Pitfall | Consequence | Correction |
| --- | --- | --- |
| "RF=3 so all nodes are always identical" | Failing to recognize divergence windows and replica errors | Distinguish RF from CL and convergence mechanisms |
| "ONE only writes to one replica" | Misunderstanding the write path | ONE sets the required ACK count; the coordinator may send more broadly |
| "Write QUORUM means read ONE is always fresh" | May read a replica that has not received the write | Evaluate the R/W pair and quorum intersection |
| "Read repair will fix the entire cluster" | Unread partitions can remain divergent | Schedule anti-entropy repair by token ranges |
| "Hints guarantee every missed mutation is delivered" | Long-offline nodes still miss data | Hints are best-effort, not a replacement for repair |
| "Timeout means the write never happened" | Bad retries cause duplicate or regressed data | Unknown outcome, idempotency, and readback |
| "A cell with higher revision automatically wins" | Cassandra does not compare business revisions | CAS/sequences/source of truth |
| "Lower grace to save disk space" | Zombie/resurrection risk | Design safe repair/deletion schedules |
| "Compaction synchronizes replicas" | Missed mutations can still persist | Distinguish compaction vs. anti-entropy repair |
| "LWT or logged batch makes all tables atomic/isolated" | Observing partial updates in business data | Understand transaction scope; use retries/reconciliation |
| "Two SSTables differing in bytes = bad data" | False alarms from different flush/compaction times | Compare logical values, timestamps, and tombstones |
| "Quorum gives a consistent multi-partition snapshot" | Application reads inconsistent states | Define separate transaction/business invariants |

## 17. Practice Exercise

A lab Cassandra cluster has a single-DC keyspace, **RF=3**, with replicas A/B/C. Source order state:

```text
tenant_id = T
order_id = O1
status = PENDING
revision = 9
```

Suppose:

- A, B, and C initially all hold revision 9.
- While C is disconnected, the application writes revision 10 with `status = PAID` using `LOCAL_QUORUM`.
- A and B acknowledge; the client receives success.
- Some time later, C returns, though it is not guaranteed to have received all changes missed during disconnection.
- The application also maintains an `orders_by_status_day` table updated by an asynchronous consumer.

**Tasks:**

1. Explain why a `LOCAL_QUORUM` write can succeed when C is unresponsive. What is the minimum number of ACKs if local RF = 3?
2. Could a `ONE` read on the same row see revision 9 or 10? Why can you not assert with certainty that it will return one specific value?
3. How does a `LOCAL_QUORUM` read intersect with the successful write on A/B? Does this prove C is already synchronized?
4. If C is offline for a very long time and hinted handoff is no longer sufficient, which mechanism should be scheduled to synchronize replicas?
5. Suppose a `DELETE` was also missed by C. Describe the role of tombstones, grace, and repair schedules; what can happen if the deletion marker is purged before C receives the delete?
6. A consumer processes revision 11 (`SHIPPED`) first, then processes revision 10 (`PAID`) late with a newer write timestamp. Can the replicas eventually be completely identical yet **business-incorrect**? How should this be fixed?
7. `orders_by_id` shows `PAID` while `orders_by_status_day` still has a `PENDING` row. Why does Cassandra anti-entropy repair not solve this automatically?
8. Write the CQL to create the lab keyspace/table and two readback queries under `ONE` and `LOCAL_QUORUM`. List the metrics/logs to collect before drawing conclusions.

**Reference Hints:**

- With RF=3 in one DC, local quorum is **2 ACKs**. A+B suffice for the write to complete even if C does not respond.
- A `ONE` read may be routed to a replica that has or has not received the mutation; the outcome depends on timing, routing, and convergence state.
- Two quorum sets of size 2 intersect in at least one replica, yet that does not mean replica C has caught up or that secondary tables are synchronized immediately.
- Hinted handoff is best-effort within a limited window/conditions; repair is the anti-entropy mechanism that must be scheduled when replicas may miss data.
- Tombstones protect deletions; if a deletion marker is lost while a replica still holds old data, deleted data risks reappearing.
- Business revisions must be controlled at the source, such as sequential processing or appropriate CAS/LWT. Write timestamps do not know which event occurred later.
- The ID table and status table are **two projections with separate mutations**; they require durable events, retry/idempotency, and business-level reconciliation, unlike inter-replica repair for a single partition.

## Conclusion

Cassandra replicas can diverge due to **unpropagated writes, consistency levels, node/network failures, incomplete hints, untouched partitions during read repair, timestamp conflicts, TTL/DELETE/tombstones, insufficient repair scope, or topology changes**. RF determines the number of copies; CL determines the acknowledgments waited for; while hinted handoff, read repair, anti-entropy repair, and streaming drive convergence within their respective scopes. Crucially, always separate **divergence across replicas of the same partition** from **business-incorrect data or missing mutations across query-driven tables**. Diagnose keys, timestamps, CL, topology, and logs accurately before taking action; maintain repair schedules, tombstone safety, controlled retries, and business reconciliation so the system stays available under failure while keeping data reliable.
