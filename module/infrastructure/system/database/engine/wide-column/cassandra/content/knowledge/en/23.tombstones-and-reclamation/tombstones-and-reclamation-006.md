# Tombstone Reclamation Conditions in Compaction

> **Chapter:** Tombstones and Reclamation  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — Apache Cassandra and distributed wide-column databases: partition keys, query-driven table design, read/write consistency levels, CQL, replication, compaction, repair, troubleshooting, and Java connectivity.

When running `DELETE` or letting a value's TTL expire in Apache Cassandra, data usually **does not vanish immediately from all SSTables**. Cassandra records deletion metadata called a **tombstone** so that replicas and SSTables holding older values cannot let those values reappear. A tombstone can only be physically removed when the system meets conditions regarding **time**, **relationship to data residing in other SSTables**, and **synchronization safety across replicas**.

This topic is easily misunderstood via the saying: "Wait past `gc_grace_seconds` and tombstones will be deleted." In reality, passing the grace period is only **one necessary condition**. Compaction may not run right away; when it does run, it must still avoid exposing an older value that has not been removed. Furthermore, compaction on one node cannot by itself confirm that all other replicas have received the delete operation.

## 1. Learning objectives

After this lesson, you will be able to:

1. Explain why `DELETE` creates tombstones and why TTL expiration has a similar consequence.
2. Distinguish between **a row no longer visible on read**, **an aged-out tombstone**, and **a tombstone physically reclaimed from SSTables**.
3. State the conditions under which compaction can remove a tombstone without causing deleted values to reappear.
4. Describe the **zombie data** risk when a replica misses a delete operation for longer than the grace window.
5. Design a CQL lab with flush, compaction, repair, and metric observation without mistaking query results for proof of physical reclamation.
6. Choose `gc_grace_seconds` and repair schedules with solid rationale, understanding the effects of STCS/LCS/TWCS, TTL, partition keys, and Java workloads.

## 2. What is a tombstone and where is it created?

### 2.1. Logical deletion first, physical reclamation later

Cassandra stores data in memtables and immutable SSTables. Once data has been written to an SSTable, an update or delete **does not directly modify the bytes of the old SSTable**. Instead, a new mutation (including a tombstone) is written to the normal write path: commit log and memtable, then flushed into a new SSTable.

A tombstone contains metadata needed to shadow older versions of data, such as the deletion timestamp and a local deletion time used to calculate grace duration. On read, Cassandra merges relevant versions using timestamp and deletion rules; a value older than a tombstone is not allowed to appear in the results.

| Action | Logical data | Storage consequence |
|---|---|---|
| `INSERT`/`UPDATE` new value | Has value at the corresponding timestamp | Mutation is stored; old SSTables may still retain prior version |
| `DELETE` one column | Deleted column is no longer visible | Tombstone exists for the appropriate column/scope |
| `DELETE` one row | Deleted row is no longer visible | Row tombstone or related marker exists |
| `DELETE` entire partition | Rows in the partition are shadowed per timestamp rules | Partition tombstone exists |
| `TTL` expiration | Expired value is no longer visible | Expired data is treated as deleted and needs reclamation per tombstone rules |

Depending on the statement, Cassandra also has **range tombstones** for ranges of clustering keys. The size and position of different tombstone types affect the read path and compaction eligibility; not every `DELETE` produces the same physical entry.

### 2.2. Example of an old value and a new delete operation

Suppose on one node, for the same key `(device_id, day_bucket, event_id)`, two SSTables exist:

~~~text
SSTable-A (already existed):
  key = K, payload = "ACTIVE", write timestamp = 100

SSTable-B (newer):
  key = K, tombstone, delete timestamp = 200
~~~

On read, the tombstone at timestamp 200 shadows the value at timestamp 100, so the application does not see `ACTIVE`. Yet **SSTable-A still contains the old data bytes** until compaction becomes eligible to process it.

If compaction only looked at SSTable-B and dropped the tombstone while SSTable-A still remained, a later read could see `ACTIVE` again. Thus, the reclamation decision must consider **other data that the tombstone is shadowing**, not merely the age of the tombstone itself.

### 2.3. Three moments that are not equivalent

~~~mermaid
flowchart LR
    A["T0: DELETE or TTL expiration"] --> B["Reads no longer see old value"]
    B --> C["T1: tombstone passes gc_grace_seconds"]
    C --> D["T2: compaction can safely remove it"]
    D --> E["Actual disk space is gradually freed"]
~~~

- **T0:** the deletion marker takes logical effect according to timestamp and the read's consistency level.
- **T1:** the tombstone is old enough to be **considered** for reclamation. There is no automatic timer deleting it right at T1.
- **T2:** compaction processes eligible SSTables and verifies safety conditions to drop the tombstone along with shadowed old data.
- **After T2:** replacement SSTables are written, obsolete SSTables are no longer needed and are removed via file management; disk usage figures may update afterward rather than dropping immediately after `DELETE`.

## 3. Three layers of conditions for tombstone reclamation

### 3.1. Layer 1 — Past the `gc_grace_seconds` window

`gc_grace_seconds` is a **table-level** option representing how long Cassandra retains a tombstone after its local deletion time so replicas that missed the delete still have an opportunity to be synchronized. The default is typically **864000 seconds (10 days)** in Apache Cassandra; check your table schema and actual version.

~~~sql
CREATE TABLE lab_tombstone.events_by_device (
    device_id uuid,
    day_bucket date,
    event_id uuid,
    payload text,
    PRIMARY KEY ((device_id, day_bucket), event_id)
) WITH gc_grace_seconds = 864000;
~~~

The general condition to consider a tombstone is:

~~~text
current time > local deletion time + gc_grace_seconds
~~~

**Note:** this is a conceptual expression. In implementation, Cassandra relies on tombstone metadata and compaction logic; `localDeletionTime` and the delete mutation's timestamp **are not the same quantity**. Write timestamp resolves version conflicts; local deletion time evaluates tombstone retention age. Node clock skew can cause operational discrepancies, so time synchronization is essential.

Setting `gc_grace_seconds = 0` makes tombstones immediately eligible by age; it **does not** guarantee instant physical deletion and is especially dangerous when a replica holds stale data. Never choose 0 merely to make tombstone metrics look lower.

### 3.2. Layer 2 — Not exposing older versions in other SSTables

Compaction must guarantee that dropping a tombstone **does not expose** older data still residing in readable SSTables. This typically requires analyzing SSTables **participating in the compaction** as well as **overlapping uncompacted SSTables**, considering token ranges, timestamp bounds, and deletion markers.

Consider three cases:

| Case | Reasonable outcome |
|---|---|
| SSTable-A holds old value; SSTable-B holds tombstone; only B is compacted while A remains readable | **Keep** the tombstone if dropping it could expose A's data |
| A and B are compacted together, no other overlapping old data sources remain on the node, tombstone is old enough, and other constraints hold | **Both** the tombstone and the shadowed old value can be removed |
| Tombstone is old enough yet an overlapping SSTable holds data it could shadow that is not in this compaction | May need to **retain** the tombstone until a safer compaction pass |

Therefore, **"grace expired, run compaction on one SSTable" does not guarantee the tombstone disappears**. Structures like partition tombstones, row tombstones, range tombstones, TTLs, and timestamp updates make the problem more complex than a two-SSTable diagram. Cassandra performs eligibility checks internally in the storage engine; operators should never manually delete SSTable files just because they see old tombstones.

### 3.3. Layer 3 — Ensuring other replicas do not reintroduce deleted data

The first two conditions can be evaluated by compaction on **a single node**. In a distributed cluster, there is an **operational** constraint: replicas must have an opportunity to receive the deletion marker before it is reclaimed on active replicas.

- Tombstones are propagated as mutations to replicas per RF and CL. A `DELETE` succeeding at `QUORUM` **does not mean every replica** received and stored the tombstone.
- A Down or isolated replica may still retain the old value. **Hinted handoff** has time and operational limits and does not replace repair.
- **Anti-entropy repair** synchronizes data across replicas. Repair frequency, completion time, and coverage must be managed so a replica that missed a deletion does not return past the safety window still carrying old data.
- Some configurations/versions offer `only_purge_repaired_tombstones` to restrict purging data not marked as repaired. This is an **additional guardrail**, not a substitute for properly scheduled repair, and its version-specific behavior must be verified before use.

**Critical boundary:** Cassandra does not automatically "verify repair across all replicas" before every compaction that reclaims tombstones. `gc_grace_seconds` is the window for repair/sync work to finish, **not a certificate that it has finished**.

### 3.4. Decision table

| Past grace? | Old data exposable locally on node? | Replicas safely operated/repaired? | Conclusion |
|---|---|---|---|
| No | Any | Any | Not yet eligible for normal reclamation |
| Yes | Yes, not safely shadowed/removed by compaction | Possibly yes | Should not drop tombstone due to local data exposure risk |
| Yes | No local shadowed data outside compaction scope | Unknown | May satisfy **local technical** eligibility yet still carry zombie risk from another replica |
| Yes | Can safely eliminate old versions | Yes, per verified runbook | Valid basis for compaction to reclaim when it runs |

This table is a mental model. Whether Cassandra purges a specific tombstone also depends on the compaction algorithm, SSTable metadata, tombstone type, version, and configuration.

## 4. Why does zombie data appear when a replica fails for too long?

### 4.1. Timeline with RF = 3

Suppose a cluster has three replicas A, B, C, and a partition holds `status = 'ACTIVE'` at timestamp 100 on all three. The system writes at `QUORUM`.

| Point in time | Replica A | Replica B | Replica C | Event |
|---|---|---|---|---|
| Day 0 | ACTIVE | ACTIVE | ACTIVE | Data is synchronized |
| Day 1 | Tombstone ts=200 | Tombstone ts=200 | **Down, still ACTIVE** | Delete meets `QUORUM` via A and B |
| Days 1–11 | Marker retained | Marker retained | Down | Cannot repair C; hints may expire |
| Past grace | Tombstone may be purged if locally compaction-safe | Same as A | Still ACTIVE | Deletion marker may be gone on A/B |
| C returns | No marker left | No marker left | ACTIVE ts=100 | Repair/read reconciliation may propagate old value |

Deleted data that reappears is called **zombie data**. Whether resurrection actually occurs depends on mutation history, timestamps, actual SSTables, repair, and compaction; the table describes a **risk scenario**, not a claim that every node Down over 10 days definitely brings data back.

~~~mermaid
sequenceDiagram
    participant App as Application
    participant A as Replica A
    participant B as Replica B
    participant C as Replica C
    Note over C: Offline, still holds old value V
    App->>A: DELETE K (ts=200)
    A->>A: Write tombstone
    A->>B: Forward delete mutation
    B->>B: Write tombstone
    A-->>App: QUORUM met, return success
    Note over A,B: Past grace + locally safe compaction
    Note over A,B: Tombstone may be reclaimed
    Note over C: C returns with old V
    C-->>A: Repair/sync value V
    Note over A,C: No deletion marker remains to shadow V
~~~

The danger lies in the fact that **each node only sees its own SSTables during compaction**. Ensuring old data isn't exposed on A does not prove C knows about the delete.

### 4.2. Why shouldn't grace be lowered arbitrarily?

The grace duration must reflect the **longest potential isolation window** of a replica plus repair execution time, operational delays, cascading incidents, and clock skew; not merely how long hints are retained.

For instance, if an organization allows nodes to be offline for 48 hours yet repairing a large dataset takes multiple days, setting a 24-hour grace to "clean tombstones fast" creates an obvious risk. Even systems on a regular repair schedule must check **repair completion**, not merely that jobs were scheduled or started.

For outages exceeding `gc_grace_seconds`, follow a **recovery/rebuild/replace runbook** appropriate for your version and topology, which may require rebuilding the replica's data from healthy sources; never simply boot the old node and trust repair to handle everything.

## 5. Why do tombstones remain even when eligible?

Passing grace only makes a tombstone **eligible for removal**; it does not mean it has been selected in a compaction. There are several reasons:

1. **No eligible compaction yet:** no compaction ran on the SSTable holding the tombstone, or the scheduler did not pick the necessary files.
2. **SSTable overlap:** compaction ran on one group of files, yet old data remains exposable in other SSTables.
3. **Tombstone not yet old enough:** local deletion time/TTL or clock offsets make actual calculation differ from expectations.
4. **Compaction bottleneck:** backlog, disk speed, CPU, or compaction throughput throttling delays file processing.
5. **Repaired data policy:** protection options tied to repaired/unrepaired state can retain tombstones longer under relevant settings.
6. **Staggered TTLs or late-arriving data:** SSTables still hold versions/tombstones needed to shadow earlier data; short TTL writes do not make an entire partition droppable at once.
7. **Impact of compaction strategy:** SSTable selection differs sharply across STCS, LCS, and TWCS, leading to different tombstone removal opportunities.

Do not infer "tombstones still exist after 10 days so Cassandra is broken." Check whether compaction is running, which SSTables overlap, where tombstones reside, and safety conditions.

### 5.1. Size-Tiered Compaction Strategy (STCS)

STCS typically selects SSTables of similar size to compact. A tombstone in a small SSTable may sit waiting because it hasn't qualified for a matching compaction tier or because old data lives in a very differently sized SSTable. STCS offers tombstone-compaction options, though they should be used only after understanding I/O impact and overlapping data regions.

### 5.2. Leveled Compaction Strategy (LCS)

LCS organizes SSTables into levels and tries to limit overlap within levels. During compaction, SSTable scope must preserve correctness across levels. LCS often improves read predictability in suitable workloads, yet **does not** guarantee every tombstone past grace is deleted immediately; overlap scenarios and heavy compaction costs still exist.

### 5.3. Time-Window Compaction Strategy (TWCS)

TWCS groups SSTables into time windows. For time-series data that is **mostly written in time order with relatively uniform TTLs**, SSTables in older windows can become completely expired and be dropped efficiently.

However, late-arriving data, updates/deletes to old partitions, or mixed TTLs can create logical overlap across windows. Therefore, you cannot claim "TWCS + TTL means zero tombstones" or "every expired window is deleted immediately." Be especially cautious with settings that aggressively drop expired SSTables, as that can raise the risk of exposing data in overlapping files.

| Strategy | General SSTable selection | Consequence for tombstones |
|---|---|---|
| STCS | Groups SSTables by size | Tombstones may wait for matching files; overlap exists |
| LCS | Splits SSTables into levels, manages overlap bounds | More organized processing opportunities yet must still preserve safety |
| TWCS | Groups SSTables by time | Beneficial for uniform-TTL sequential data; sensitive to late writes |

**Compaction strategy is a workload choice**, not a switch to accelerate tombstone reclamation at any cost.

## 6. CQL lab: observing tombstones, grace, and compaction

### 6.1. Experimental conditions and boundaries

Use an **isolated test Cassandra cluster** with `cqlsh` and `nodetool`; document version, RF, CL, compaction strategy, and topology. The examples below follow standard CQL for Cassandra 4.x–5.x. If your environment only has one node, adjust replication/CL accordingly; **do not use an RF=3 lab keyspace on a single node** and draw conclusions about replicas.

In a lab with at least three nodes in a DC named literally `dc1`:

~~~sql
CREATE KEYSPACE IF NOT EXISTS lab_tombstone
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

USE lab_tombstone;

CREATE TABLE IF NOT EXISTS events_by_device (
    device_id uuid,
    day_bucket date,
    event_id uuid,
    payload text,
    PRIMARY KEY ((device_id, day_bucket), event_id)
) WITH gc_grace_seconds = 120
  AND compaction = {'class': 'SizeTieredCompactionStrategy'};
~~~

**Scope warning:** `gc_grace_seconds = 120` (two minutes) is **strictly for a disposable lab**, so it can be waited out and observed in a single session. This value is far too low when replicas can go Down or repairs cannot complete within two minutes. **Never apply to production.** For pre-existing tables, `IF NOT EXISTS` does not alter configuration: verify the actual schema.

The partition key is `(device_id, day_bucket)` and the clustering key is `event_id`. Since one partition holds a device's events for one day, partition-key queries route efficiently; for very hot devices, daily buckets may still grow too large and require redesign.

### 6.2. Create a value then logically delete it

In `cqlsh`:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

Run CQL:

~~~sql
INSERT INTO lab_tombstone.events_by_device
    (device_id, day_bucket, event_id, payload)
VALUES (
    0f94e3b9-0b36-4930-91f2-606b44b5231b,
    '2026-11-21',
    df4d2f1a-c74e-48dc-b889-4e18de3cd51b,
    'VISIBLE_BEFORE_DELETE'
);

SELECT event_id, payload
FROM lab_tombstone.events_by_device
WHERE device_id = 0f94e3b9-0b36-4930-91f2-606b44b5231b
  AND day_bucket = '2026-11-21';
~~~

Before deleting, run flush on **the nodes holding replicas** to create an SSTable storing the old value:

~~~bash
nodetool flush lab_tombstone events_by_device
~~~

`nodetool` runs against the local node; determine the endpoints for the partition and repeat on the relevant nodes when observing physical state across all RF=3 replicas. On each node, flush only writes that node's current memtable to an SSTable.

Next:

~~~sql
DELETE FROM lab_tombstone.events_by_device
WHERE device_id = 0f94e3b9-0b36-4930-91f2-606b44b5231b
  AND day_bucket = '2026-11-21'
  AND event_id = df4d2f1a-c74e-48dc-b889-4e18de3cd51b;

SELECT event_id, payload
FROM lab_tombstone.events_by_device
WHERE device_id = 0f94e3b9-0b36-4930-91f2-606b44b5231b
  AND day_bucket = '2026-11-21';
~~~

The `SELECT` result after deletion returns no matching row, **yet does not prove bytes were erased from disk**. The tombstone may still be in the memtable. Flush once more on the relevant replicas to produce a new SSTable holding the deletion marker, then inspect storage metrics.

### 6.3. Observe and compare before/after compaction

On each replica:

~~~bash
nodetool tablestats lab_tombstone.events_by_device
nodetool compactionstats
nodetool tpstats
~~~

When you have direct access to the SSTable directory on a lab host/container, the **`sstablemetadata`** tool for your exact version can help inspect SSTable/tombstone metadata and the *estimated droppable tombstone ratio*. Exact invocation, paths, and output fields must be checked via `sstablemetadata --help` in your environment. Never modify SSTables managed by Cassandra directly.

Comparison:

| Point in time | Logical observation | Reasonable physical observation |
|---|---|---|
| Before DELETE | Row `VISIBLE_BEFORE_DELETE` present | SSTable contains old value |
| Immediately after DELETE | Row not visible at tested CL | Old value may still exist; tombstone may be in memtable |
| After flush, **under 120 seconds** | Row not visible | Old-value SSTable and tombstone SSTable both exist; not old enough to purge |
| After 120 seconds, **no suitable compaction yet** | Row not visible | Tombstone may still remain despite being old enough |
| After eligible compaction | Row not visible | Tombstone and old data may be reclaimed, subject to overlap and safety checks |

To study the mechanics, after passing grace and ensuring all replicas received the delete, you can **in a lab** request manual compaction on each relevant node:

~~~bash
nodetool compact lab_tombstone events_by_device
~~~

This is an I/O-heavy command, not a required step for every deletion in production. Even after the command completes, whether data still exists in any SSTable must be verified with appropriate metadata/storage tools; `SELECT` continuing to return empty **cannot prove purging**.

**Comparison caveat:** in a tiny lab with very little data, metadata may shift too fast or background compaction may already have run. To evaluate quantitatively, populate enough partitions and write values and tombstones across multiple SSTables before measuring, while recording compaction state.

### 6.4. TTL: expiration time and reclamation time

In the same table, add an event with TTL:

~~~sql
INSERT INTO lab_tombstone.events_by_device
    (device_id, day_bucket, event_id, payload)
VALUES (
    0f94e3b9-0b36-4930-91f2-606b44b5231b,
    '2026-11-21',
    3400f4b1-136a-4130-86a0-8dfc63269fb0,
    'EXPIRES_AFTER_60S'
) USING TTL 60;
~~~

During the first minute, the record remains visible. After TTL, the expired value is treated as deleted during reads; it can remain in SSTables and is subject to reclamation rules like a tombstone. **TTL = 60 does not mean disk space is freed after exact 60 seconds**. And `gc_grace_seconds = 120` in the lab is the window that must also elapse from the corresponding deletion/expiration timestamp, along with compaction conditions.

### 6.5. Data to record in the lab report

| Evidence | Content to record | Valid conclusion |
|---|---|---|
| Schema | RF, CL, `gc_grace_seconds`, compaction | Know exact configuration conditions |
| CQL before/after `DELETE` | Row visible before, hidden after | Logical deletion works |
| Flush timing | Which SSTables formed from values and markers | Basis to analyze overlap |
| `tablestats`, `compactionstats` | SSTable count, tombstones per slice if shown, pending compactions | Data on storage/read path |
| `sstablemetadata` or equivalent SSTable tool | Before/after metadata, droppable tombstone figures | Physical observation within tool limits |
| Replica/repair state | Nodes at full RF, up/down, deletion marker sync | Evaluate zombie risk |

**Never use a single number** like "SSTable count dropped" to conclude a specific tombstone was deleted: compaction can merge multiple files while keeping the deletion marker. Likewise, never take "DELETE command succeeded" to mean all replicas synced at all CLs.

## 7. Impact of tombstones on the read path and storage

### 7.1. Tombstones still carry a cost on reads

When querying a partition/range, Cassandra may need to read and merge many cells, range markers, and tombstones across multiple SSTables to determine which rows remain live. If a partition has many tombstones, even `SELECT ... LIMIT 10` can sometimes have to skip huge amounts of deleted data before finding ten live rows.

Thus, logical deletion **does not immediately make queries faster**. If data is frequently deleted in bulk, the workload may suffer:

- More tombstones scanned per query, driving up CPU/IO and p95/p99.
- Warnings or errors related to tombstone scan thresholds, depending on version/config.
- SSTable footprint larger than live data size, increasing compaction write amplification.
- Need to manage TTL, partition size, clustering range, and an appropriate deletion strategy.

### 7.2. Monitoring with metrics that match their true meaning

Commonly useful signals:

| Tool / metric | Answers the question | Does not prove |
|---|---|---|
| `nodetool tablestats` | Does the table have notable SSTable counts / read cost / tombstones per slice? | Exact number of tombstones purged |
| `nodetool tablehistograms` | Do partition size, latency, and SSTables per read show skewed distributions? | Every partition matches the percentile |
| `nodetool compactionstats` | Is compaction running, what do pending tasks look like? | Running compaction will drop all tombstones |
| JMX/Table `TombstoneScannedHistogram` and read latency | Are queries scanning many tombstones and is p99 rising? | Tombstones are the sole cause |
| `sstablemetadata`, appropriate file inspection | Tombstone/drop eligibility at SSTable scope | Other replicas received the delete |
| `nodetool status`, repair history | How are topology and sync state managed? | Up status alone guarantees consistent data |

Choose before/after measurement windows under the same workload. Many metrics are cumulative counters requiring delta/rate calculations; table-level or node-level histograms do not replace end-to-end application latency. Never run heavy SSTable analysis or manual compaction on a production cluster during peak hours.

## 8. Designing and operating so tombstones do not become a burden

### 8.1. Choose `gc_grace_seconds` based on replica risk and repair

There is no single optimal grace value for every table. The decision must answer:

1. How long can a replica remain isolated at most before being recovered/rebuilt?
2. What schedule does repair run on, and how long does it actually take across all data ranges?
3. Are there maintenance windows, unstable network zones, frequent node Down events, or snapshot/restore workflows?
4. Does the data use TTLs, column/row/partition deletes, version updates, or multi-DC synchronization?
5. Is there monitoring for successful repair completion and alerting on missed schedules?

If repair fails frequently, **do not simply lower grace to reclaim faster**. Fix repair reliability, availability, and procedures for unreachable replicas first. Conversely, a very long grace does not fix missing repairs while prolonging how long tombstones stick around.

### 8.2. Do not abuse row-by-row `DELETE` for bulk data removal

A workload generating millions of events/day and then deleting row-by-row after a retention period can create massive tombstones and write amplification. When business policy permits:

- Use a **reasonable TTL** when creating events instead of running a job scanning/deleting row-by-row; while TTL still behaves like tombstones, uniform TTLs support time-series data design.
- Choose **partition keys and time buckets** aligned with queries, data size, and lifecycle; avoid one partition holding millions of rows requiring scans through tombstones.
- Evaluate **TWCS** for time-series workloads fitting time-ordered writes and consistent lifecycles, while verifying late data handling.
- For datasets that can be dropped at whole-table/keyspace granularity, schema-level operations follow different workflows than row-by-row deletion; use only when business scope and impact are clear.
- If a table frequently updates the same cells or uses large collections, track tombstones from element updates/deletes rather than counting only `DELETE` statements.

**Note:** having a TTL does not automatically require TWCS. A table whose data can be updated at arbitrary times and queried outside time windows may need a different strategy.

### 8.3. Repair, hints, and compaction each have distinct duties

| Mechanism | Primary purpose | Role regarding tombstones |
|---|---|---|
| **Hinted handoff** | Forwards some missed mutations while a replica is temporarily Down | Assists tombstone propagation within a limited window; does not guarantee long-term sync |
| **Repair** | Compares and synchronizes data across replicas | Reduces risk of a replica holding old data after tombstones pass grace |
| **Compaction** | Merges SSTables and reconciles versions per node | Can remove tombstones along with shadowed data when eligible |
| **Snapshot/backup** | Provides procedural data recovery capability | Does not replace repair; restoring old snapshots must assess deleted-data reintroduction risk |

Some runbooks require **full repair** after changing RF/topology; for tombstone protection, you need a repair schedule suited to your cluster and version, never equating "repair ran" with "zombies are impossible." Using incremental/full repair must follow your version, token range scope, and current tooling.

## 9. Connection to Java clients and consistency levels

In the Java Driver, a delete operation is a normal mutation carrying a CL like any other write. Example with Java Driver 4.x on a `CqlSession session` configured with a local datacenter:

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.LocalDate;
import java.util.UUID;

PreparedStatement deleteByKey = session.prepare(
    "DELETE FROM lab_tombstone.events_by_device " +
    "WHERE device_id = ? AND day_bucket = ? AND event_id = ?");

BoundStatement statement = deleteByKey.bind(
        UUID.fromString("0f94e3b9-0b36-4930-91f2-606b44b5231b"),
        LocalDate.of(2026, 11, 21),
        UUID.fromString("df4d2f1a-c74e-48dc-b889-4e18de3cd51b"))
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

session.execute(statement);
~~~

With RF=3 in one DC, `LOCAL_QUORUM` typically waits for two replicas to acknowledge. It does not guarantee the third replica wrote the tombstone; hence a successful Java operation does not replace repair duties. Nor does a timeout prove the delete failed: some replicas may have written the deletion marker while the client missed enough ACKs before the deadline.

**Retry note:** when re-writing/re-deleting the same key, if the application uses client timestamps, TTL, or conflict logic, control mutation order and idempotency. In particular, never create a delete timestamp older than a newer update and assume the delete will win; Cassandra uses timestamps to resolve versions.

## 10. Misconceptions to eliminate

| Claim | Assessment | Correct explanation |
|---|---|---|
| "Once deleted, disk is freed immediately." | False | Delete typically only writes a marker; disk is reclaimed via eligible compaction |
| "After 10 days tombstones vanish automatically." | False | Grace is an age condition; compaction, overlap, and safety checks still apply |
| "Running `nodetool compact` deletes all tombstones." | False | Compaction must still keep ineligible tombstones or those shadowing old data |
| "`gc_grace_seconds=0` always improves performance." | False / dangerous | Raises risk of old data reappearing; does not guarantee immediate purging |
| "Repair is unrelated to deletes." | False | Repair delivers missed deletion info to replicas that missed mutations |
| "Hints can replace repair." | False | Hints have windows/limits and do not guarantee recovering all misses |
| "TTL avoids tombstones completely." | False | TTL expiration creates a deleted state that must be safely cleaned up |
| "Many tombstones always cause `SELECT` to fail." | Overstated | Impact depends on tombstones scanned, partition, read path, and version thresholds |
| "Reading empty proves physical cleanup." | False | Old value may still sit in an SSTable shadowed by a tombstone |
| "An Up replica proves every delete was received." | False | Up status says nothing about each partition's sync history |

## 11. Applied scenarios

### Scenario A — Past grace yet SSTable still retains tombstone

SSTable A holds `V(ts=100)`. SSTable B holds `DELETE(ts=200)` which is past grace; the scheduler picks B to compact without A. Should the tombstone be dropped from B?

**Answer:** no, if A can still be read and A's old value would be exposed. The tombstone must be kept, or compaction must safely process/check overlapping data. Passing age **does not** equal local safety.

### Scenario B — Node returns after 15 days

RF=3, one node missed `DELETE`, no effective repair ran, grace is configured to 10 days. The other two replicas compacted and reclaimed the tombstone. The old node returns. What can happen?

**Answer:** if the old node still holds a value with a timestamp before DELETE while the deletion marker is gone on the remaining replicas, the old data can re-propagate and appear as a zombie. You need a proper node recovery runbook, repair schedule, and outage window monitoring — not just raising the read CL.

### Scenario C — One-hour TTL, why does disk usage keep growing?

The application writes millions of events per hour with TTL=3600 seconds. After two hours, most events are no longer visible, yet SSTables are larger than expected.

**Answer:** TTL expiration does not mean files were deleted. Grace, compaction, overlap, TTL distribution, and SSTable selection conditions all apply. Check strategy, tombstone metrics, flush/compaction timing, partition size, and late-arriving data.

### Scenario D — Should grace be changed from 10 days to 1 hour?

The operations team runs repair **once a week**, yet wants to shrink disk usage by setting `gc_grace_seconds = 3600`.

**Answer:** unsafe. A one-hour window is far shorter than a weekly repair schedule; a replica missing a delete could return with old data. Re-evaluate repair, topology, incident SLAs, retention, workload, compaction, and zombie risk before making any change.

## 12. End-of-lesson checklist

- [ ] Distinguish `DELETE`/TTL expiry from reclaiming bytes in SSTables.
- [ ] State why `gc_grace_seconds` is a necessary but insufficient time condition.
- [ ] Explain the scenario where a tombstone in SSTable B shadows an old value in SSTable A.
- [ ] Explain zombie risk when a replica misses a DELETE and the repair window is missed.
- [ ] Use `cqlsh`, `nodetool flush`, `tablestats`, and `compactionstats` to observe the process.
- [ ] Do not treat empty `SELECT` results or successful `nodetool compact` runs as proof of purging.
- [ ] Understand the effects of STCS, LCS, TWCS, and TTL/late-arriving data.
- [ ] Choose grace based on completed repairs, replica offline duration, and topology.
- [ ] Connect CL and timeout ambiguity when Java sends delete operations.

## 13. References

1. Apache Cassandra Documentation — [Storage engine: SSTables, compaction, commit log](https://cassandra.apache.org/doc/stable/cassandra/architecture/storage-engine.html).
2. Apache Cassandra Documentation — [Anti-entropy repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html).
3. Apache Cassandra Documentation — [CQL data definition and table properties](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html).
4. Apache Cassandra Documentation — [Monitoring metrics](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html).
5. Apache Cassandra Documentation — [Compaction](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/overview.html).
