# Risk of Old Data Reappearing When a Replica Misses a Delete in Apache Cassandra

> **Chapter:** Tombstones and Reclamation  
> **Scope:** Distributed Apache Cassandra with multiple replicas, CQL writes/deletes, tombstones, `gc_grace_seconds`, hinted handoff, repair, compaction, TTL, and node-loss scenarios. The learning goal is to understand **zombie data** (deleted data reappearing) and how to prevent it in production operations.

## 1. Learning objectives

After completing this lesson, you will be able to:

1. Explain why Cassandra **writes a deletion marker (tombstone)** instead of physically deleting across all replicas right away.
2. Reconstruct the sequence of events causing a replica to miss a DELETE and later propagate **old data** to other replicas.
3. Distinguish a **stale read before synchronization** from **zombie data after tombstones have been reclaimed**.
4. Understand the roles and limits of **consistency level (CL), hinted handoff, anti-entropy repair, `gc_grace_seconds`, and compaction**.
5. Know when a node absent for too long **should not be brought back into the cluster with old data without a recovery plan**.
6. Design a runbook and CQL/Java practice lab to test deletes on a cluster, observe tombstones, and prevent zombies.

This is a characteristic scenario of **distributed wide-column** databases: the same partition can reside on multiple nodes, data is modeled around queries, and replicas do not necessarily receive mutations simultaneously. Therefore, understanding tombstones is essential for operating Cassandra safely, alongside replication, consistency, repair, and compaction.

## 2. What actually happens on DELETE?

When an application sends:

~~~sql
DELETE FROM shop.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

Cassandra does not open every existing SSTable to erase the row in place. It writes a **tombstone**, which is metadata meaning "data at this position was deleted at a specific timestamp."

On a replica, data passes through the **commit log and memtable**, and is then flushed to **immutable SSTables**. SSTables containing the old version can still sit on disk. On read, Cassandra reconciles data and tombstones using timestamp, TTL, and deletion-scope rules to decide what remains live.

~~~text
On replica A:

Old SSTable                      Memtable / New SSTable
order-111 -> state='PAID'        order-111 -> TOMBSTONE (ts=200)
             ts=100
                  \                /
                   \  reconcile   /
                    v            v
                    Do not return row
~~~

Two key points:

- **Logical deletion**: from a CQL viewpoint, a tombstone with a newer timestamp shadows older data. Users no longer see that row on replicas that received the delete.
- **Physical reclamation**: only under safe conditions does compaction drop tombstones and shadowed old data, freeing disk space. Reclamation does not happen immediately after DELETE.

Tombstones are not created solely by full-row DELETEs; column DELETEs, subset deletions, and **TTL expiration** also lead to deleted states within their respective scopes.

### 2.1. Common types of tombstones

| Type | Typical creation case | Data shadowing scope |
|---|---|---|
| Cell tombstone | `DELETE state ...`, writing `null` to a column | A specific cell/column |
| Row tombstone | `DELETE FROM ... WHERE` with full row key | Cells belonging to that row |
| Range tombstone | Deleting multiple clustering rows within a key range | A slice of rows in a partition |
| Partition tombstone | Deleting an entire partition by partition key | Data within the partition |
| TTL-expired tombstone | Cell whose TTL has expired | Value past its lifetime |

All examples above must factor in **timestamp**. A new write with a timestamp greater than the deletion marker can validly reappear because it is a **new mutation**, unlike a zombie caused by a replica retaining **old** data after the protecting tombstone was lost.

## 3. Zombie data scenario: three replicas, one misses DELETE

Consider a keyspace in one datacenter with **RF=3**, where the natural replicas for partition `tenant-a` are A, B, C. Initially all three contain record `order-111` at timestamp `t=100`.

### 3.1. Stage-by-stage progression

~~~text
                       RF = 3, partition tenant-a

T0: Before DELETE
    A: [order-111, ts=100]
    B: [order-111, ts=100]
    C: [order-111, ts=100]

T1: Node C loses connectivity
    DELETE order-111 (tombstone ts=200), CL=QUORUM
    A: [tombstone ts=200]    ACK
    B: [tombstone ts=200]    ACK
    C: [order-111, ts=100]   DID NOT receive delete
    => Client receives DELETE success because QUORUM=2/3.

T2: C is absent for a long time, never receives tombstone via
    hinted handoff, repair, or an appropriate sync mechanism.
    A and B still use the tombstone to shadow the old value.

T3: After gc_grace_seconds elapses, if compaction becomes
    eligible to clean tombstone and shadowed data on A/B:
    A: [no tombstone left]
    B: [no tombstone left]
    C: [order-111, ts=100]   <-- old copy still remains

T4: C returns; read/repair/streaming can see
    [order-111, ts=100] with NO tombstone ts=200 left
    to negate it. Old data can be re-propagated.
    => ZOMBIE DATA: order-111 reappears.
~~~

This is a **conditional scenario**, not a claim that the moment `gc_grace_seconds` passes, every tombstone vanishes instantly. Actual purging also depends on **compaction** and rules checking SSTables with overlapping data/tombstones. The risk occurs when **all replicas holding the useful tombstone have dropped it**, while one replica still retains undeleted old data.

### 3.2. Timeline table: local state and client observation

| Milestone | A | B | C | What the client can observe |
|---|---|---|---|---|
| Before DELETE | Live data | Live data | Live data | Reads see the row |
| After DELETE QUORUM succeeds | Tombstone | Tombstone | Old data, missed DELETE | `ONE` read may see old result if hitting C |
| Before purge, after successful repair | Tombstone | Tombstone | Tombstone | Consistent reads see deletion |
| No repair and tombstones on A/B purged | No marker left | No marker left | Old data | Genuine zombie risk |
| After C re-propagates data | May hold old data | May hold old data | Old data | Deleted row can reappear |

**Distinguish two phenomena:**

1. **Stale read**: C has not received the tombstone yet, so a read from C can return the old value *while A/B still hold the deletion marker*. A timely repair can still fix this state.
2. **Zombie resurrection**: the deletion marker has been dropped from replicas that could repair C; the old value on C is no longer blocked and can spread to other replicas. At that point, ordinary repair **cannot know it was ever deleted data**.

This is why the statement "DELETE with QUORUM succeeded, so old data can never exist again" is false: QUORUM means enough replicas acknowledged the operation at write time, **not that all replicas received the mutation**.

## 4. Why does Cassandra need tombstones and a grace window?

Immutable SSTables and asynchronous replication mean a temporarily disconnected node can still hold old versions of data. A tombstone is **timestamped deletion proof** so when the node returns, newer replicas can inform the stale replica that the value is no longer valid.

If A/B erased both the data and the tombstone right at T1, the cluster would lose the proof C needs to receive. Therefore, Cassandra retains tombstones for a configurable period.

### 4.1. What is `gc_grace_seconds`?

`gc_grace_seconds` is a **per-table** property specifying the grace window before a tombstone *may* be garbage-collected during compaction. The default is typically **864000 seconds (10 days)** in Apache Cassandra; check your actual setup with `DESCRIBE TABLE` because table settings may have been changed.

~~~sql
DESCRIBE TABLE shop.orders;

-- Table configuration parameter, e.g.:
-- ... WITH gc_grace_seconds = 864000 ...
~~~

One way to visualize it:

~~~text
DELETE writes tombstone
      |
      |<---- gc_grace_seconds ---->|
      v                            v
   Tombstone retained         Tombstone STARTS
   for other replicas         being old enough to CONSIDER purging
                                    |
                                    v
                      Only when compaction and SSTable
                      safety conditions are satisfied
~~~

**Do not misinterpret:** `gc_grace_seconds=864000` does not promise "data is physically erased after exact 10 days," is not a user data retention period, and **does not run repair automatically**. It is part of the safety mechanism **before** compaction can reclaim deletion markers.

### 4.2. When is a tombstone actually purged?

Beyond the tombstone passing grace, compaction must guarantee that dropping it **does not let old data in another SSTable on the same node come back to life**. Cassandra checks the relationship between compacted SSTables and SSTables with overlapping data/token ranges outside the compaction set.

Example on A:

~~~text
SSTable-A1: order-111 = 'PAID' (ts=100)
SSTable-A2: tombstone order-111 (ts=200)

Compaction processing only A2:
  Cannot arbitrarily drop tombstone if A1 still holds old row.

Compaction eligible to process shadowed data:
  Can remove both tombstone and old value when time/grace
  and overlapping SSTable rules allow.
~~~

Purge checks provide **local safety** on the node. However, Cassandra cannot always know that an unreachable C still holds old data. Thus **timely repair across all replicas** is a critical operational factor to prevent zombies across nodes.

### 4.3. Effects and risks of lowering `gc_grace_seconds`

| Configuration | Potential benefit | Risk / condition |
|---|---|---|
| Default value (usually 10 days) | Gives more time for repair and failed nodes to return | Tombstones kept longer, affecting disk and reads |
| Shorter grace | Tombstones can be purged earlier when compaction qualifies | **Less time** to repair a replica that missed DELETE |
| `gc_grace_seconds=0` | Can clean markers faster | **High zombie risk** if a replica can miss deletes; should not be applied broadly |
| Very long grace | Gives even more time for repair | Tombstones accumulate, increasing tombstone scan/compaction burden |

Do not lower grace merely because reports show many tombstones. First investigate **tombstone generation sources**, query filters, repair schedules, replica health, TTL patterns, and compaction strategy.

## 5. Hinted handoff and repair: two different mechanisms

At T1, the coordinator can store a **hint** for C when C is unresponsive, to attempt redelivering the mutation when the node recovers. Hinted handoff is a mechanism to recover from **short-term** missed writes.

~~~text
DELETE sent to A/B/C
                 |
           C does not respond
                 |
         Coordinator stores hint (if enabled/valid)
                 |
         C returns soon enough
                 |
         Replay hint => C gets tombstone
~~~

However, hints are **not permanent storage**:

- Bounded by settings, hint retention window, and coordinator storage/capacity.
- Cannot guarantee every failed write produces a hint or that every hint is delivered successfully.
- Hint retention is typically **shorter** than `gc_grace_seconds`; check version-specific parameters such as `max_hint_window`.
- A single DELETE succeeding at the chosen CL does not prove a failed replica will be healed by hints alone.

**Anti-entropy repair** reconciles data across replicas by token range, commonly using Merkle trees and streaming discrepancies. While A/B still retain tombstones, repair can deliver deletion markers to C so it drops old records.

| Mechanism | Purpose | Can it prevent zombies in the example? | Limitation |
|---|---|---|---|
| Hinted handoff | Replay temporarily missed mutations | Yes, if tombstone reaches C before marker loss | Does not cover all downtimes |
| Read repair | Fix some discrepancies found during reads | Possibly, when reads and reconciliation actually see the tombstone | Only keys/read paths actually touched; varies by Cassandra version |
| Anti-entropy repair | Planned reconciliation across replicas by range | **Primary measure** ensuring data/tombstones sync within expected scope | Must finish across all ranges/replicas before grace expires |
| Compaction | Merge SSTables and reclaim eligible data | Does not repair an unreachable replica C | Can drop tombstones needed by C if repair was missed |
| Backup/snapshot | Provides recovery copies | Aids recovery after divergence | Snapshots do not inherently know which records were deleted |

**Periodic repair is not an empty promise:** monitor that *repairs truly succeeded and covered all required token ranges*. If repair ran yet failed on C, do not treat C as healed.

## 6. What does consistency level protect?

With three full replicas in one DC:

- `ONE`: write or read operation requires one matching response.
- `QUORUM`: requires two responses out of RF=3.
- `ALL`: requires all three responses for the ALL-level operation to succeed.
- `LOCAL_QUORUM`: computes quorum **within the local datacenter** in multi-DC setups; unlike `QUORUM`, which spans total RF.

The familiar `R + W > RF` relationship ensures read and write response sets overlap **under appropriate replica, topology, and mutation assumptions**. Yet it does not guarantee an absent replica received the tombstone, and **does not prevent zombies once the tombstone is purged**.

In the RF=3 example:

| DELETE CL | Can succeed when C is down? | Guarantees permanent deletion without repair? |
|---|---|---|
| `ONE` | Yes, if A responds | No |
| `QUORUM` | Yes, if A and B respond | No |
| `ALL` | **No**, if C does not respond | Unusable when a replica is down; even when succeeding, maintenance/repair is still needed for future failures |

Raising DELETE CL can narrow the window where a write is acknowledged yet multiple replicas missed it, at the cost of **availability**. It is not a substitute for anti-entropy repair or handling disconnected nodes.

### 6.1. Why is `SELECT QUORUM` also insufficient?

Right after DELETE on A/B, a QUORUM read under valid conditions can reconcile the tombstone with C's data and return the right result. But once all healthy replicas have purged the tombstone, **no newer value remains to reconcile against old data from C**. Raising CL at that point cannot restore lost deletion information.

If you run a repair cycle **after** the necessary tombstone has been purged, the old data can be treated as a valid copy and replicated elsewhere. Repair has no permanent log of every DELETE to distinguish zombies.

## 7. Designing a safe repair schedule around the grace period

The operational principle is: **every replica that might hold old data must have a chance to receive tombstones before tombstones on healthy replicas are reclaimed**. Hence, the standard practice is completing repair across the entire required scope **more frequently than `gc_grace_seconds`**, with enough buffer for slow schedules, node failures, and repair retries.

Example for a table with `gc_grace_seconds=864000` (10 days):

~~~text
Day 0: DELETE on A/B; C misses it.
Day 2: repair is scheduled yet fails on C's range.
Day 4: repair retry succeeds; C receives tombstone.
Day 10+: compaction can purge eligible tombstones.

=> C healed in time; zombie risk from this mutation is reduced.
~~~

Conversely:

~~~text
Day 0: DELETE on A/B; C misses it.
Day 8: repair fails yet monitoring raises no alert.
Day 10+: compaction qualifies and drops tombstones on A/B.
Day 15: C finally returns and repair runs.

=> Day 15 repair may already be too late.
~~~

Never design a schedule like "repair on exact day 10" when grace is 10 days. Reserve a **generous buffer** for prolonged outages and full repair runtime on a large cluster.

### 7.1. Repair must cover all at-risk data

In clusters using **NetworkTopologyStrategy**, each DC has its own RF. Repair schedules must ensure relevant token ranges, tables, and replicas are all synchronized, including DCs that may not be the Java application's local datacenter.

~~~bash
# Illustrative repair command by primary ranges.
# Orchestrate sequentially across relevant nodes/DCs.
nodetool repair --full -pr zombie_lab orders
~~~

Running `-pr` on **one node** only repairs primary ranges assigned to that node/command; it does **not** confirm the keyspace was repaired cluster-wide. Whether you use full repair, incremental repair, or a dedicated repair orchestrator depends on your Cassandra version and operational policy; the mandatory requirement is **actually achieving coverage**.

| Signal to monitor | Why does it affect zombies? |
|---|---|
| Last successful repair time of **every range** | Identifies ranges that may have gone unsynced too long |
| Nodes down/unreachable per DC | Replicas missing tombstones may be out of repair reach |
| Repair failures, timeouts, streaming errors | Job was scheduled yet data never reached the failing replica |
| **Per-table** `gc_grace_seconds` | Each table has a different reclamation window |
| Hinted handoff status | Undelivered hints mean the replica cannot be assumed to have received DELETE |
| Compaction backlog and tombstone metrics | Affects purge timing and read costs |
| Snapshot/backup age | Restoring too-old snapshots can reintroduce pre-DELETE data |

### 7.2. You must define what "repair succeeded" means

An automated job running daily yet failing on 20% of ranges is **not** sufficient protection. For each repair run, record:

1. Keyspace/table scope, token ranges, DCs/nodes.
2. Start/end timestamps, repair mode, and Cassandra version.
3. Per-range success/failure outcomes, error logs, and retry actions.
4. Oldest repair age compared against the smallest grace of critical tables.
5. Isolated nodes or nodes recently recovered from downtime.

Set alerts **before** repair age touches grace. If one DC is isolated while another DC continues receiving deletes, prioritize restoring cross-DC sync rather than checking only that nodes in the local DC are back up.

## 8. Node absent too long: why not arbitrarily bring old data back?

Suppose C is down for 14 days while a table has a 10-day grace. When C returns, it may still hold `order-111` in old SSTables. A/B may already have purged the deletion marker.

**Dangerous action:** Boot C with old data, let it participate in reads/repairs/streaming normally, and wait to see if errors happen. If tombstones have vanished on other replicas, bringing C back can elevate zombie probability.

**Safer decision process:**

1. **Isolate the situation:** Record node disconnect duration, tables/ranges it owns, each table's grace, and whether DELETEs/TTLs occurred during that window.
2. **Inspect evidence:** Do remaining replicas still hold tombstones? Which repairs completed during C's absence? Were hints sufficient? Are there delete records in the application's source of truth?
3. **Do not trust the old node's data to be accurate:** If the node passed grace or its state cannot be verified, consider **replacing/rebuilding/bootstrapping the node from healthy replicas** per your current topology/version runbook, rather than feeding old SSTables directly into reconciliation.
4. **Post-recovery verification:** Query previously deleted sample keys against checklists, verify ranges, and run appropriate repairs once topology stabilizes.
5. **Investigate any discrepancy that occurred:** If zombies already appeared, use business logs or independent deletion ledgers to identify true states, then remediate under control.

The exact choice among `replace_address`, rebuild, bootstrap, decommissioning, and reloading fresh data **depends on version, topology, and cluster state**. Never run a generic "wipe node data" command without verifying the node, token ranges, and recovery source. With low RF or multiple simultaneous replica failures, surviving replicas might also lack enough data to recover.

### 8.1. Once zombie data has appeared, can repair fix it?

You cannot expect repair to know deletion intent on its own. If tombstone `ts=200` is gone everywhere, old data `ts=100` looks like a live value. Repair can synchronize this **wrong state** to more replicas.

Investigation steps when deleted records reappear:

| Question | Reliable evidence |
|---|---|
| Was DELETE actually executed and ACKed? | Application logs, business events, idempotency keys, write audits |
| Mutation timing relative to grace? | Table config at the time, node/repair timeline |
| Which node missed the tombstone? | Repair/streaming/hints logs and replica state |
| Is the reappearing data a zombie or a new write? | Mutation timestamp, creation events, audit trail |
| How wide is the blast radius? | List of affected primary keys, token ranges, and DCs |
| Can deletion intent be reconstructed? | Independent source of truth, CDC, or application event ledger |

After verification, you may need to **issue new DELETE mutations** for the zombie records via CQL, propagate them to relevant replicas, repair, and verify across multiple CLs/DCs. Never run blind broad-scope DELETEs: you could accidentally erase valid newer updates. If the system lacks deletion-intent logs, it is **not always possible to deduce 100%** which rows should be deleted from remaining Cassandra data alone.

## 9. TTL, compaction, and easily misunderstood cases

### 9.1. TTL also creates a deleted state

~~~sql
INSERT INTO zombie_lab.orders
    (tenant_id, order_id, status)
VALUES ('tenant-a',
        22222222-2222-2222-2222-222222222222,
        'TEMPORARY')
USING TTL 300;
~~~

After 300 seconds, the TTL value expires and is no longer live at the CQL level. Expired tombstones/metadata still must go through storage and compaction rules; that does not mean the SSTable file is deleted at exact second 300.

**Risk scenario to understand:** Both TTL and DELETE need consistent application across replicas. With TTL data, the expiration time is written alongside the value, so a replica holding a TTL copy already knows that lifetime; however, extra mutations, timestamps, repair, and TTL/DELETE combinations can create complex states. Do not use the reasoning "every replica knows the TTL so zombie cases are completely solved" as an excuse to skip repair.

### 9.2. Range tombstones can shadow many rows

Suppose a table has partition `tenant_id` and clustering `created_at`:

~~~sql
CREATE TABLE zombie_lab.events_by_tenant (
    tenant_id text,
    created_at timestamp,
    event_id uuid,
    details text,
    PRIMARY KEY ((tenant_id), created_at, event_id)
);

-- Delete rows belonging to a clustering range in the partition.
DELETE FROM zombie_lab.events_by_tenant
WHERE tenant_id = 'tenant-a'
  AND created_at >= '2026-01-01T00:00:00Z'
  AND created_at < '2026-02-01T00:00:00Z';
~~~

This statement only illustrates **deleting by clustering range**; WHERE DELETE syntax/constraints depend on primary key and CQL version. When clustering keys include `event_id`, range predicates may need adjustment per version-supported rules. The key point is that **one range tombstone can shadow many rows**, so a replica missing it can cause a large set of old rows to reappear.

### 9.3. Operational factors affecting purge timing

| Factor | Impact |
|---|---|
| `gc_grace_seconds` | Sets minimum duration before tombstones qualify for reclamation |
| Compaction strategy | Determines which SSTables are merged and when |
| Overlapping SSTables | Can block tombstone purge if uncompacted SSTables still hold old data |
| Tombstones across versions | Must reconcile timestamps/deletion times properly |
| Repair state and version purge policies | Can affect reclamation conditions under advanced configs |
| Snapshots | Can keep old physical files on disk even when live data was replaced |
| Other replicas' state | Not always verified by local compaction; hence repair schedules remain vital |

### 9.4. Clocks and timestamps cannot be ignored

Cassandra uses **write timestamps** to reconcile mutations. If an application assigns heavily skewed custom timestamps, a DELETE with a lower timestamp than another record may fail to shadow that record. That is a **timestamp-ordering error**, not necessarily a zombie caused by tombstone reclamation.

In production, monitor node clock synchronization and restrict uncoordinated manual timestamps from multiple sources. Investigating "reappearing" rows must examine both **source of timestamps** and mutation history, not only `gc_grace_seconds`.

## 10. Controlled CQL hands-on practice

Practice using an **isolated lab cluster of at least three nodes** in the same DC `dc1`, with all nodes up and controlled repair/flush/compaction allowed. Never deliberately induce zombies in production, and never set grace to 0 to prove the risk.

### Step 1 — Create a table with RF=3

~~~sql
CREATE KEYSPACE IF NOT EXISTS zombie_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': '3'
};

CREATE TABLE IF NOT EXISTS zombie_lab.orders (
    tenant_id text,
    order_id uuid,
    status text,
    updated_at timestamp,
    PRIMARY KEY ((tenant_id), order_id)
) WITH gc_grace_seconds = 86400;
~~~

**Use the name `dc1` only if that matches your actual DC name**. A grace of 86400 seconds (one day) only shortens the discussion timeframe in the lab and **is not a production recommendation**. The lab cluster must have at least three eligible nodes in the DC. For multi-DC clusters, ALTER/CREATE statements must reflect all DCs; this example uses a single DC.

### Step 2 — Write data and read before deleting

~~~sql
CONSISTENCY QUORUM;

INSERT INTO zombie_lab.orders
    (tenant_id, order_id, status, updated_at)
VALUES ('tenant-a',
        11111111-1111-1111-1111-111111111111,
        'PAID', '2026-11-21T00:00:00Z');

SELECT order_id, status, updated_at
FROM zombie_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

Quorum in an RF=3 lab requires two responses. Verify both that the table holds the right data and that nodes are **Up/Normal** before continuing.

### Step 3 — Delete and confirm logical result

~~~sql
DELETE FROM zombie_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

SELECT order_id, status
FROM zombie_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

If DELETE QUORUM succeeds and replicas operate normally, SELECT QUORUM should return no live row for that key. **That checks current state**, and does not prove the tombstone reached all three replicas or will persist long enough if one node goes absent.

### Step 4 — Observe tombstones and node status

~~~bash
nodetool status
nodetool tablestats zombie_lab.orders
nodetool compactionstats
~~~

`tablestats` includes SSTable metrics, average tombstones per read/related metrics depending on version; a table with tiny data may not show significant numbers. Use metrics/logs/tracing to observe tombstone **cost**, rather than relying on one counter to infer all replicas received the delete.

In a lab, you can enable tracing when inspecting a query:

~~~sql
TRACING ON;

SELECT order_id, status
FROM zombie_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

TRACING OFF;
~~~

Tracing adds overhead; enable it only for selective test queries. Offline tools like `sstablemetadata`/readers can inspect tombstone metadata, yet must follow version rules regarding daemon shutdown and be used only on lab nodes.

### Step 5 — Simulate missing a DELETE (isolated lab only)

If the lab environment has safe node-control tooling, design a test scenario:

1. Write data fully across three replicas; verify RF and token ranges.
2. Disconnect **one** node C in the lab while keeping A/B running.
3. Send DELETE at CL QUORUM and record the ACK result.
4. Restore C **before grace expires**, observing hinted handoff.
5. Run **full-scope repair** to verify C receives the tombstone.
6. Re-read the key across nodes using your verification method; confirm no live data remains.

**There is no need to intentionally keep a node down past grace and force compaction to make a zombie happen.** The point of the exercise is understanding why step 5 (timely repair) prevents the risk, and why the DELETE QUORUM result in step 3 is insufficient.

### Step 6 — Repair and verify coverage

~~~bash
# Illustrative; run sequentially on EACH node of the lab cluster
# to cover relevant primary ranges; do not run concurrently arbitrarily.
nodetool repair --full -pr zombie_lab orders
~~~

Review the output of all runs, noting which nodes/ranges completed. After repair, verify again:

~~~sql
CONSISTENCY QUORUM;

SELECT order_id, status
FROM zombie_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

If no node was isolated too long and repair succeeded, the expected result remains no live row. **Do not run repair and immediately conclude all historical zombie risk is gone**: that only holds for the covered scope and tombstones that still had enough metadata to repair.

## 11. How should Java applications handle DELETE?

Java Driver 4.x allows setting CL per statement. In this example, the client can enforce DELETE QUORUM and then read at QUORUM to check state; however, the client receiving an ACK **does not replace the cluster's repair schedule**.

~~~java
import java.util.UUID;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class OrderDeletion {
    // CqlSession was built with the proper local datacenter and is reused.
    public static boolean deleteAndCheck(
            CqlSession session, String tenantId, UUID orderId) {
        PreparedStatement delete = session.prepare(
                "DELETE FROM zombie_lab.orders " +
                "WHERE tenant_id = ? AND order_id = ?");

        BoundStatement del = delete.bind(tenantId, orderId)
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
        session.execute(del);

        PreparedStatement select = session.prepare(
                "SELECT order_id FROM zombie_lab.orders " +
                "WHERE tenant_id = ? AND order_id = ?");

        Row row = session.execute(
                select.bind(tenantId, orderId)
                      .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM))
                .one();
        return row == null;
    }
}
~~~

**Scope of `deleteAndCheck`:** `true` only reflects that the immediately following SELECT **did not see the row** at the request's CL. It does not prove C received the tombstone, that all DCs are repaired, or that the row can never become a zombie.

For applications requiring strict deletion control due to business/security requirements, consider:

- **Independent audit log or deletion event ID:** preserve proof of deletion intent, key, and timestamp; helps detect/remediate zombies after prolonged outages.
- **Explicit idempotency and retries:** a DELETE retried after timeout may already have applied partially; log outcomes and retry per policy.
- **Topology-aware CL:** `LOCAL_QUORUM` only requires local DC quorum, without confirming remote DCs received DELETE.
- **Service-level observability:** track down nodes, repair age, and pre/post-delete query results; never rely solely on API HTTP 200 status.
- **Query-driven data modeling:** if an entity is denormalized across **multiple application-maintained tables**, deleting in one table does not automatically create tombstones in the other tables. That is a different failure class from zombies across replicas of the **same table**.

Avoid uncoordinated client-supplied CQL timestamps, especially when multiple services write to the same partition. A DELETE with an older timestamp than a valid INSERT/UPDATE will not shadow the newer value; that is a write-ordering issue requiring separate analysis.

## 12. Production prevention and response runbook

### 12.1. Before an incident

1. **Table inventory:** collect `gc_grace_seconds`, RF, DCs, compaction strategy, tables with heavy TTLs/deletes, and CDC/audit sources.
2. **Repair schedule:** ensure repair covers ranges on a cadence **significantly shorter than grace**, alerting when jobs fail or nodes are unavailable.
3. **Node outage SLA:** define maximum absence duration before mandatory data investigation replaces ordinary rejoin.
4. **Backup/restore:** test restoring individual tables and full topology; avoid restoring old snapshots and mixing them with new data without accounting for deletions.
5. **Observability:** collect logs for DELETE errors, hints, repair, streaming, and tombstone warnings; measure read p95/p99, tombstones scanned, and compaction.
6. **Grace change discipline:** alter only after proving repair coverage, failure windows, and workload behavior; document the rationale.

### 12.2. When a node is unreachable

**Within grace and before deletion proof is lost:** prioritize bringing the node back via supported operational workflows, verifying hints/repairs, and recording results. If the node has been down close to grace, decide on action **before** tombstones can purge; never treat "node Up/Normal" as proof the replica is synced.

**If downtime exceeds grace or history cannot be verified:** isolate stale-data risk, gather evidence, and consider rebuilding the node with current data from trusted replicas. Never wipe all snapshots, manually delete SSTables, or open traffic before assessing data scope.

### 12.3. After detecting a zombie

1. **Scope it:** keyspace, table, primary key, DC, DELETE timestamp, involved nodes, token ranges.
2. **Distinguish root cause:** premature tombstone GC, repair failure, old snapshot restore, bad timestamps, valid new write, or multi-table duplication lag.
3. **Consult source of truth:** delete events, audit logs, business metadata; do not assume the record sitting in Cassandra is the right state.
4. **Remediate:** issue new delete/update mutations for the verified list of records, propagate across replicas, repair, and verify across multiple CLs/DCs.
5. **Prevent recurrence:** adjust repair schedules, node replacement policy, grace, hints, and upgrade/recovery procedures.
6. **Long-term verification:** monitor the same key set across subsequent compaction and repair cycles.

For sensitive data requested for deletion, do not claim system-wide deletion is complete if you only verified one SELECT from one DC. Deletions in backups, CDC, data lakes, or denormalized tables are separate pipelines that must also be tracked.

## 13. Misconceptions that commonly lead to zombie data

| Wrong claim | Truth |
|---|---|
| "DELETE physically erases data on every node immediately." | DELETE writes a tombstone; old SSTables can still hold data. |
| "QUORUM success means all 3 replicas deleted it." | With RF=3, quorum only requires 2 responses. |
| "Hints are kept until the node returns even if it takes weeks." | Hints have retention limits and do not replace repair. |
| "One repair on one node suffices for all token ranges." | You must ensure **the entire scope is repaired**. |
| "After 10 days tombstones vanish immediately." | Grace only determines age eligibility; purging depends on compaction and overlap checks. |
| "If compaction purged tombstones, repair can always fix it." | Repair no longer knows about old DELETEs once markers are gone. |
| "If tombstone and old data share one SSTable, there is no risk." | Consider other SSTables and other replicas, not just a single local file. |
| "`gc_grace_seconds=0` is always safe if reading at QUORUM." | A replica that missed deletes can still cause zombies after purge. |
| "For a node Down past grace, just restart it and run repair." | The node can bring deleted data back; proper assessment/recovery is needed. |
| "Every record appearing after DELETE is a zombie." | It could be a valid newer UPDATE or an application timestamp bug. |
| "TTL removes data from disk at the exact second of expiry." | TTL ends liveness; physical reclamation occurs later via compaction. |
| "Deleting an entity in Cassandra auto-deletes all other tables." | Each denormalized table has its own mutation lifecycle if app-maintained. |

## 14. Self-assessment questions

**Q1.** With RF=3, C down, DELETE QUORUM returns success. What is confirmed and what is not?  
**Hint:** A/B ACKed; does not prove C received the tombstone.

**Q2.** After one day, SELECT ONE from C returns the deleted row while A/B still hold the tombstone. Is this a zombie yet?  
**Hint:** First and foremost it is a **stale read**; repair can still fix C.

**Q3.** Why might running repair on day 11 be too late when grace=10 days?  
**Hint:** Compaction on A/B may already have purged the deletion marker before then.

**Q4.** Are setting `gc_grace_seconds=0` and raising DELETE CL to ALL enough to replace repair?  
**Hint:** No long-term guarantee under node failures and differing purge timings; ALL also makes writes unavailable when one replica is down.

**Q5.** How does hinted handoff differ from anti-entropy repair?  
**Hint:** Hints replay temporarily failed mutations; repair reconciles data by token range.

**Q6.** Why might compaction keep a tombstone even past grace?  
**Hint:** An overlapping SSTable outside the compaction set may still hold shadowed old data.

**Q7.** When an old node returns after 15 days with a 10-day grace, what action should be avoided?  
**Hint:** Do not let the node carry old SSTables straight into repair/reads without assessing risk.

**Q8.** Does a `LOCAL_QUORUM` DELETE on a two-DC cluster prove the other DC received the delete?  
**Hint:** No, it only requires quorum of the local DC.

**Q9.** Why is a successful repair after zombies have spread insufficient to prove data correctness?  
**Hint:** Repair syncs currently visible data; it does not restore lost deletion intent.

**Q10.** When SELECT returns a row after DELETE, what information should be compared before deleting again?  
**Hint:** Mutation timestamps, DELETE audits, new write history, replica state, repair, snapshots/restores.

## 15. Summary

~~~text
                     DELETE
                        |
             Write tombstone on replicas
                   /          \
         Replica receives    Replica misses
           tombstone            DELETE
             |                   |
     Grace period running        |
             |                   |
   Repair/hints deliver marker---+
             |
       All replicas converge
             |
        Compaction qualifies
             |
     Tombstone can be purged
             |
        [Safe path]

Conversely:
   Replica misses delete + repair missed in time
                 +
   Tombstone purged on healthy replicas
                 |
      Old replica returns / streams
                 |
        ZOMBIE DATA can appear
~~~

**Core principle:** A tombstone is proof of deletion in a multi-replica system; `gc_grace_seconds` provides time to synchronize deletion markers, while **timely full-coverage repair and proper node recovery** keep replicas aligned on that state. Once deletion proof vanishes before a stale replica is healed, deleted data can reappear and cannot be distinguished from valid data by repair alone.

## References

- [Apache Cassandra — Tombstones](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/tombstones.html) — zombie data, grace period, TTL, and tombstone reclamation.
- [Apache Cassandra — Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html) — anti-entropy repair, incremental/full repair, primary ranges, and operational scheduling.
- [Apache Cassandra — CQL data manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html) — DELETE, TTL, mutation timestamps, and write consistency.
- [Apache Cassandra — Storage engine](https://cassandra.apache.org/doc/stable/cassandra/architecture/storage-engine.html) — commit log, memtables, immutable SSTables, and compaction.
- [Apache Cassandra — cassandra.yaml configuration](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html) — hinted handoff and operational parameters to verify against your version.
- [Apache Cassandra — CREATE TABLE](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html) — table properties, `gc_grace_seconds`, and compaction.
