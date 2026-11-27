# Range Tombstones and Range Queries

## 1. Reading few rows yet processing many deletion markers: why?

In **Apache Cassandra**, a `DELETE` does not necessarily erase old data bytes from disk immediately. Cassandra writes a **tombstone** to mark values/rows that must no longer be returned; old versions can still sit in memtables or other SSTables until compaction safely removes them.

A **range tombstone** is a tombstone used to delete **a range of rows by clustering key inside a partition**, rather than issuing individual delete statements per row. It is especially relevant for wide-column tables holding many time-ordered events.

Business example: a sensor application wants to delete all measurements from **08:00 to before 09:00** on Nov 21, 2026 while keeping measurements after 09:00. In Cassandra, a range deletion can record the fact that "this clustering key range was deleted." When reading a time interval that intersects the deleted region, Cassandra must reconcile both **old data** and the **range tombstone** to determine which rows remain valid.

**Lesson objectives:**

- Distinguish **range tombstones**, **row/partition/cell tombstones**, **TTLs**, and **token-range scans**.
- Write CQL to delete a clustering key range and accurately read surviving rows.
- Explain open/close bounds markers, write timestamps, and conditions under which old records are shadowed.
- Understand impacts on the read path, caches, SSTables, compaction, `gc_grace_seconds`, and repair.
- Design query-driven tables, observe tombstone scans, and use the Java Driver safely.

**Scope:** standard full Cassandra replicas; on-disk range tombstone representation details, warning thresholds, and purging strategies may vary by version.

## 2. Foundation: partition key differs from clustering range

Consider a table storing temperature readings per device per day:

~~~sql
CREATE KEYSPACE IF NOT EXISTS sensors_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS sensors_lab.readings_by_device_day (
    device_id text,
    event_day date,
    event_time timestamp,
    event_id uuid,
    temperature decimal,
    quality text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

To run the example, replace `dc1` with your actual data center name and ensure enough nodes if using RF = 3 and `LOCAL_QUORUM`.

| Component | Role | Relationship to range tombstones |
| --- | --- | --- |
| `(device_id, event_day)` | **Composite partition key**: determines token and replica set storing the partition | A range tombstone is scoped **within the identified partition**, never spilling into other partitions automatically. |
| `event_time` | **First clustering column**, ordered descending | Allows expressing a time range spanning multiple rows **inside the same partition**. |
| `event_id` | **Second clustering column**, distinguishes concurrent events | Constraining only `event_time` can delete all matching `event_id` rows within the range. |
| `temperature`, `quality` | Regular columns | Not keys used to define the range tombstone's clustering bounds in this example. |

With `device_id='device-7'` and `event_day='2026-11-21'`, rows at 08:05, 08:30, and 09:10 all reside in **the same partition**, regardless of how many SSTables exist. Changing the day or device causes Cassandra to compute a different partition key.

**Common pitfall:** `CLUSTERING ORDER BY (event_time DESC)` changes **storage/result ordering**, not the meaning of CQL comparison operators: `event_time >= 08:00 AND event_time < 09:00` still means the interval **[08:00, 09:00)**.

## 3. Comparing tombstone types

A tombstone is **timestamped deletion metadata**, not just an "empty slot." Depending on the statement and scope, Cassandra uses different deletion-marking mechanisms.

| Deletion type | Conceptual CQL example | Logical scope |
| --- | --- | --- |
| **Cell tombstone** | `DELETE quality ... WHERE` with full primary key | One regular column value in one specific row. |
| **Row tombstone** | `DELETE FROM ... WHERE` with full partition key and clustering key of one row | Columns of that corresponding row. |
| **Partition tombstone** | `DELETE FROM ... WHERE device_id=? AND event_day=?` | All rows/values in the partition per timestamp semantics. |
| **Range tombstone** | `DELETE FROM ... WHERE partition_key = ... AND event_time >= ... AND event_time < ...` | Rows in a clustering key slice within the specified partition. |
| **TTL-expired tombstone** | `INSERT/UPDATE ... USING TTL` reaching expiration time | The TTL value is no longer live; expiry time and deletion metadata participate in reconciliation. |

Some internal details vary by column type and version. What matters for CQL authors is the **shadowed scope**: an entire partition, a single row, a single cell, or **a contiguous slice by clustering key**.

### Not deleting by token range

Two "range" concepts are very different:

- **Clustering range**: e.g., `WHERE device_id='device-7' AND event_day='2026-11-21' AND event_time >= ...`; operates inside **one partition**. Range tombstones belong here.
- **Token range**: e.g., `WHERE token(device_id, event_day) > ... AND token(device_id, event_day) <= ...`; used to **scan multiple partitions** by token across the distribution ring.

Never assume `DELETE ... WHERE token(partition_key) BETWEEN ...` creates a cluster-wide range tombstone. A range tombstone is not "delete every partition in a token slice"; broad deletion across many partitions requires a dedicated workflow identifying individual keys/scopes and evaluating cost and consistency.

## 4. Practice: creating and deleting an event range

### 4.1. Load four rows

Run in `cqlsh` after creating the table:

~~~sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO sensors_lab.readings_by_device_day
  (device_id, event_day, event_time, event_id, temperature, quality)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T07:50:00Z',
   123e4567-e89b-42d3-a456-426614174001, 20.10, 'OK');

INSERT INTO sensors_lab.readings_by_device_day
  (device_id, event_day, event_time, event_id, temperature, quality)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T08:05:00Z',
   123e4567-e89b-42d3-a456-426614174002, 20.30, 'OK');

INSERT INTO sensors_lab.readings_by_device_day
  (device_id, event_day, event_time, event_id, temperature, quality)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T08:30:00Z',
   123e4567-e89b-42d3-a456-426614174003, 20.50, 'BAD');

INSERT INTO sensors_lab.readings_by_device_day
  (device_id, event_day, event_time, event_id, temperature, quality)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T09:10:00Z',
   123e4567-e89b-42d3-a456-426614174004, 21.00, 'OK');
~~~

Initial check query:

~~~sql
SELECT event_time, event_id, temperature, quality
FROM sensors_lab.readings_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21';
~~~

Expect four rows (in descending time order), assuming no other writes on the same keys.

### 4.2. Delete all rows in [08:00, 09:00)

~~~sql
DELETE FROM sensors_lab.readings_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T08:00:00Z'
  AND event_time <  '2026-11-21T09:00:00Z';
~~~

This is a **range deletion on clustering column `event_time`**. For this table, it covers every `event_id` whose `event_time` falls in the interval: specifically the **08:05** and **08:30** rows.

Rows **07:50** and **09:10** lie outside the range and are not targeted by this delete. To verify:

~~~sql
SELECT event_time, event_id, temperature
FROM sensors_lab.readings_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21';

SELECT event_time, event_id, temperature
FROM sensors_lab.readings_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T08:00:00Z'
  AND event_time <  '2026-11-21T09:00:00Z';
~~~

In a lab state with no concurrent writes, the first query returns **07:50 and 09:10**, and the second returns **no live rows**. Returning zero rows **does not mean the 08:05 and 08:30 bytes have vanished from SSTables**.

### 4.3. Why is the full partition key required?

A common mistake is trying:

~~~sql
-- Does not identify one partition; not a valid way to run a range delete.
DELETE FROM sensors_lab.readings_by_device_day
WHERE event_time >= '2026-11-21T08:00:00Z'
  AND event_time <  '2026-11-21T09:00:00Z';
~~~

In this schema, `event_time` alone is insufficient to route to a partition. Cassandra is not designed to execute an arbitrary CQL `DELETE` scanning across all devices/days like a `DELETE ... WHERE` on a relational SQL table. To delete a day across all devices, you must design tables/maintenance jobs that identify the partitions to process, or use TTL and an appropriate data lifecycle from write time.

## 5. How range tombstones work inside the read path

### 5.1. Start and end boundary markers

At the storage layer, a range deletion can be represented by **boundary markers** (range open/close) tagged with a **deletion timestamp** and local deletion time; Cassandra uses that metadata when traversing ordered clustering keys.

~~~text
Clustering key in ascending time (logical illustration):

07:50        08:00          08:05      08:30       09:00        09:10
  |------------|--------------|----------|------------|------------|
               [========== deleted range ===========)
               ^ range start                         ^ range end
    live                        shadowed                            live
~~~

Given the table's actual `DESC` storage order, Cassandra traverses backward along the time axis; the **CQL range start/end** meaning remains `>= 08:00` and `< 09:00`. Do not infer physical marker order solely from an ascending-time diagram.

**A range tombstone does not necessarily turn into one separate tombstone per row**: it can represent a contiguous span. However, read costs can still be high if a partition accumulates many range tombstones, overlapping ranges, and old data scattered across many SSTables.

### 5.2. Reads must reconcile multiple data sources

When a client reads `WHERE device_id=? AND event_day=? AND event_time >= ...`, the coordinator picks replicas by token and consistency level. Each replica may have to read the **memtable** plus multiple **SSTables**, then reconcile:

1. Values with different write timestamps at the same key.
2. Row/cell tombstones or range tombstones affecting that key.
3. TTL-expired data, deletion markers, and reconciliation rules.
4. Versions residing across newer/older SSTables.

~~~mermaid
flowchart TD
    Q["SELECT in range 08:00–09:00"] --> P["Coordinator locates partition replicas"]
    P --> R["Replica reads memtable + relevant SSTables"]
    R --> D1["SSTable A: pre-delete rows 08:05 and 08:30"]
    R --> D2["SSTable B: range tombstone [08:00, 09:00)"]
    D1 --> H["Reconcile by timestamp and deletion scope"]
    D2 --> H
    H --> O["Do not return rows shadowed by tombstone"]
    O --> C["Coordinator returns results per CL"]
~~~

**Caches and indexes do not remove reconciliation duties:** Bloom filters and partition indexes help locate/skip SSTables by partition key; key caches can reduce lookup time; yet a query touching a range tombstone region must still apply deletion metadata accurately. Cache hits must never expose a deleted row.

## 6. Timestamps decide which delete wins

Cassandra uses **write timestamps** in its last-write-wins reconciliation, not simply when requests reached the machine. A range tombstone with deletion timestamp `t_del` generally shadows data in its range whose timestamp is no newer than `t_del` (specific tie-breaking rules apply when timestamps are equal).

### Logical timeline example

~~~text
t1: INSERT event 08:05, temperature = 20.30
t2: DELETE range [08:00, 09:00)             (t2 > t1)
t3: Re-INSERT event 08:05, temperature = 21.10 (t3 > t2)
~~~

- After `t2`, the record from `t1` is not returned.
- A valid new record with a timestamp **greater than** the deletion timestamp can appear inside the previously deleted range.
- If a client supplies an incorrect `USING TIMESTAMP`, clocks are skewed, or old data imports use inappropriate timestamps, results may differ from "whichever command ran later wins."

**Important:** a range tombstone is not a permanent ban against any new record with the same clustering key. It is timestamped deletion metadata that must be reconciled against newer and older writes.

Example controlling timestamp in a lab (to illustrate the principle only — **do not** hardcode this value in real applications):

~~~sql
-- Use a timestamp matching an independent lab test event.
-- Do not apply if data with other timestamps already exists on the same key.
DELETE FROM sensors_lab.readings_by_device_day
USING TIMESTAMP 1795200000000000
WHERE device_id = 'device-lab'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T08:00:00Z'
  AND event_time <  '2026-11-21T09:00:00Z';
~~~

If the application supplies timestamps itself, it must maintain consistent clock, ordering, and idempotency policies; using identical timestamps for deletes and new writes has specific conflict-resolution semantics. Never rely on `WRITETIME(temperature)` to infer that a deleted row has no markers left on disk: CQL normally returns only live values.

## 7. Why can range queries get slower after many DELETEs?

A `SELECT` with a full partition key requesting only a few rows can still have to read **many tombstone markers**. Factors that commonly compound include:

- **Many small deleted ranges** inside the same partition, e.g., deleting 5-minute slices across 180 days.
- **Overlapping delete ranges** with different timestamps.
- **Old SSTables holding shadowed rows** while new SSTables hold range tombstones.
- **New memtables and old SSTables** requiring reconciliation, alongside TTL tombstones.
- **Oversized partitions** causing slice queries or partition scans to read huge volumes of data to find a few live rows.

| Query | Visible result | Underlying work that may be needed |
| --- | --- | --- |
| `SELECT ... WHERE pk=? AND event_time >= 08:00 AND event_time < 09:00` | 0 rows after delete | Traverse sources holding old rows and range tombstone metadata over that slice. |
| `SELECT ... WHERE pk=? LIMIT 10` | 10 live rows | May have to skip many deleted rows to find 10 live rows. |
| `SELECT COUNT(*) WHERE pk=?` | A single number | May have to process vast numbers of rows, TTLs, and tombstones; not an instant metadata count. |
| Multi-partition scan via `token(pk)` | Many rows across many partitions | Each partition can still carry its own range tombstones, increasing total work. |

In production, scanned tombstone counts can trigger query safety warnings/limits; parameters such as `tombstone_warn_threshold` and `tombstone_failure_threshold` (if present in your version) **are not data optimizers**. Merely raising thresholds to "stop the errors" can increase latency, memory pressure, and replica load.

### 7.1. `LIMIT` does not cure tombstone scans

~~~sql
SELECT event_time, temperature
FROM sensors_lab.readings_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
LIMIT 10;
~~~

`LIMIT 10` caps the maximum **10 rows returned**; it does not guarantee Cassandra reads only 10 SSTable entries. If the first live row sits behind many deleted rows, the replica still needs to walk through those markers and related data to produce the right result.

**Paging** in the Java Driver splits results into pages, yet does not reduce the source entries that must be evaluated to complete a long query. Queries with higher CLs may also have to reconcile versions from multiple replicas depending on data consistency state.

## 8. Reclaiming range tombstones: grace, repair, and compaction

### 8.1. Why not delete tombstones right away?

A replica can be offline when a range deletion is written. If active replicas drop tombstone metadata too early, the previously absent replica can bring **old rows** back when it rejoins and syncs, causing **zombie data**.

~~~mermaid
sequenceDiagram
    participant App as Client
    participant N1 as Replica N1
    participant N2 as Replica N2
    participant N3 as Replica N3 (offline)
    Note over N1,N3: RF = 3, N3 has not received delete
    App->>N1: DELETE range [08:00, 09:00)
    N1->>N2: Forward mutation/tombstone
    N2-->>N1: ACK
    N1-->>App: May succeed at LOCAL_QUORUM
    Note over N1,N2: Tombstone still needed to shadow old records
    Note over N3: Still holds 08:05, 08:30 data
    Note over N1,N3: Timely repair/sync propagates deletion info
~~~

**`gc_grace_seconds`** is an important protection window for tombstone cleanup and giving absent replicas a chance to receive deletion info. Yet it **does not run repair automatically**, nor does it guarantee tombstones vanish the instant grace expires.

### 8.2. Three conditions to consider before purging

1. **Tombstone age:** has the deletion metadata met the time eligibility condition?
2. **Safety against overlapping data:** do other SSTables contain older versions that this tombstone still needs to shadow?
3. **Convergence across replicas:** do replica/offline history and repair schedules mean dropping the marker early risks zombies?

**Compaction** can merge data and deletion markers, dropping data/tombstones safe to purge or retaining metadata still needed. Never manually delete SSTable files just because `SELECT` no longer returns data. `nodetool compact` or major compactions also **do not guarantee** all tombstones vanish and can cause heavy I/O.

Related mechanisms:

| Mechanism | Role | Do not infer |
| --- | --- | --- |
| **Hinted handoff** | Stores some mutations to redeliver to temporarily unavailable replicas within operational limits | Does not replace repair or retain deletes forever. |
| **Read repair** | Can fix replica drift on read data depending on version/mode | Does not ensure unread ranges converge on their own. |
| **Anti-entropy repair** | Syncs data/tombstones across replicas for covered data regions | Not an instant tombstone-deletion switch. |
| **Compaction** | Reduces SSTables and cleans eligible versions/markers per node | Does not send deletes to other replicas and does not replace repair. |
| **Backup/snapshot** | Recovers from accidental deletes/logic bugs per retention policy | Replication does not undo a delete that already propagated to replicas. |

### 8.3. Range tombstones and TWCS/TTL

**TimeWindowCompactionStrategy** is often useful for append-only time-series data with nearly uniform TTLs. However, frequent **range deletes on old data**, backfills, or old updates can scatter markers and versions across multiple SSTables/windows, making reclamation harder.

For data needed only for 30 days, a **TTL set at write time** can fit better than daily manual range-delete jobs. Still, TTL also generates tombstones on expiration; it **does not** let you skip `gc_grace_seconds`, repair, or compaction conditions. When business logic must selectively delete a slice inside a partition, range tombstones may be necessary.

## 9. Lab observation guide

### 9.1. Enable tracing for a small query

~~~sql
CONSISTENCY LOCAL_QUORUM;
TRACING ON;

SELECT event_time, event_id, temperature
FROM sensors_lab.readings_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T08:00:00Z'
  AND event_time <  '2026-11-21T09:00:00Z';

TRACING OFF;
~~~

Depending on version and trace events, you can inspect read steps, endpoints, timing, or tombstones processed. **Trace is a diagnostic tool**, not a certificate that all replicas were repaired or SSTable files were deleted.

### 9.2. Inspecting metrics and cluster state

On a node with `nodetool` access:

~~~bash
nodetool tablestats sensors_lab.readings_by_device_day
nodetool compactionstats
nodetool status
~~~

Commonly useful info (metric names may vary by version):

- **Tombstones scanned per read/slice**: markers traversed on the read path, especially on hot partitions/time ranges.
- **SSTable count/size**: how many files a query must reconcile, and whether disk usage is growing or shrinking.
- **Read latency/timeouts**: are tombstone scans impacting APIs or triggering warnings?
- **Pending/active compactions**: is a backlog preventing old files from merging?
- **Replica up/down and repair status**: might any replica have missed deletes for a long time?

Do not conclude "range tombstones are the culprit" from a single metric. Combine actual CQL queries, partition sizes, SSTable counts, TTLs, tombstone metrics, CL, write patterns, and timing.

### 9.3. If you need to inspect markers on disk

In an isolated test environment, you can use SSTable inspection tools bundled with your **exact Cassandra version** and table metadata to view range tombstone markers/partitions. Follow the tool's operational requirements on whether the node must be stopped; never run SSTable edit/delete actions in production just to "clean tombstones." CQL `SELECT` displays **live logical data**, not raw deletion markers directly.

## 10. Java application: range deletion with prepared statements

Example using **Apache Cassandra Java Driver 4.x**, with the `readings_by_device_day` table already created. Both time bounds are passed as `Instant` and belong to one identified partition:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.net.InetSocketAddress;
import java.time.Instant;
import java.time.LocalDate;

public final class DeleteDeviceReadingsRange {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement deleteRange = session.prepare(
                    "DELETE FROM sensors_lab.readings_by_device_day " +
                    "WHERE device_id = ? AND event_day = ? " +
                    "AND event_time >= ? AND event_time < ?");

            BoundStatement stmt = deleteRange.bind(
                    "device-7",
                    LocalDate.of(2026, 11, 21),
                    Instant.parse("2026-11-21T08:00:00Z"),
                    Instant.parse("2026-11-21T09:00:00Z"))
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            session.execute(stmt);
        }
    }
}
~~~

**Key points with Java:**

1. **You must pass the full partition key** `device_id` and `event_day`; prepared statements allow binding exact `date`/`timestamp` types.
2. Bounds `>= start`, `< end` form a **half-open** interval. When deleting adjacent intervals, keep boundary conventions consistent so no record at the seam is missed or accidentally hit.
3. `LOCAL_QUORUM` controls the **replica ACK threshold** in the local DC; it **does not** mean tombstones have been compacted or reached every replica.
4. **Timeouts are uncertain outcomes**: one or more replicas may already have applied the delete mutation. Retries must use the same scope and appropriate idempotency/timestamp policies; in particular, avoid letting newly written data later be shadowed by a retried delete with a newer timestamp.
5. To prevent accidental deletes, enforce application account permissions, validate time/device bounds, write audits, and require approvals for bulk deletions.

`127.0.0.1` and `dc1` are for lab use only; production must configure contact points, local DC, TLS/authentication, timeouts, and retry policies per actual topology.

## 11. Designing to reduce range tombstones and read cost

You cannot always eliminate `DELETE`. However, if a system produces millions of tiny delete ranges, revisit the **data contract and query-serving tables**.

| Need | Design to consider | Trade-off |
| --- | --- | --- |
| Keep sensor data for only 30 days | Uniform TTL, daily/bucketed partitions, TWCS when workload fits | TTL still creates tombstones and must wait for safe purge. |
| Discard an entire day of device data | Partition key `(device_id, event_day)`; consider partition deletion instead of many range deletions | A partition deletion still requires tombstones and repair. |
| Delete only one time slice due to corrupt data | Range deletion on the matching clustering prefix | Precise scope, yet markers and old versions can add read cost. |
| Frequently alter/delete many scattered slices | Revisit bucketing, append-only model, or a "confirmed data" table | Must synchronize query-serving tables and state rules. |
| Inventory/delete many partitions in batches | Job iterating partition keys with rate limiting and checkpoints | Never confuse token-range scans with one cross-partition range tombstone. |
| Need undo for accidental deletes | Verified backup/snapshot and restore workflow | Other replicas may receive the same tombstone and cannot auto-revert. |

**Bucketing note:** if you often delete rows across a business-time window, aligning bucket boundaries with the retention/deletion unit can simplify operations. Still, avoid **oversized partitions**, too few partitions, or excessive data duplication.

### Pre-deployment checklist for a range delete command

1. **Scope:** are exact partition key, clustering prefix, and both interval bounds known?
2. **Timestamps:** are there client-supplied timestamps or late writes that might conflict?
3. **Replication:** do RF, DCs, CL, and replica health match deletion requirements?
4. **Recovery:** are backups/audits/recovery capabilities in place if the delete is wrong?
5. **Read path:** how much live data and how many tombstones remain, and which queries cut across the deleted range?
6. **Maintenance:** are repair schedules, `gc_grace_seconds`, compaction strategy, and SSTable counts monitored?
7. **Load:** are batch deletes rate-limited with safe retries to avoid creating massive tombstones at once?

## 12. True and false statements

| Statement | Verdict | Explanation |
| --- | --- | --- |
| "A range tombstone deletes a cluster-wide token range." | **False** | It represents deleting a **clustering key range inside one partition**. |
| "One range tombstone always turns into N tombstones for N rows." | **False** | It can be represented by range boundary markers. |
| "`CLUSTERING ORDER BY ... DESC` flips `>=` into `<=`." | **False** | CQL comparisons preserve value meaning; storage/display order differs from predicate semantics. |
| "Range deletion can shadow old data in other SSTables." | **True** | Readers reconcile markers with written versions by timestamp. |
| "Zero returned rows means tombstones were physically deleted." | **False** | Old data/markers can remain until compaction/purge. |
| "`LIMIT 10` guarantees scanning only 10 source rows." | **False** | Reads may have to walk past many tombstones to find 10 live rows. |
| "Once grace expires, compaction definitely deletes all markers." | **False** | Safe purge conditions, overlap, and compaction timing still apply. |
| "Repair helps tombstones reach an absent replica." | **True, when executed properly** | Repair drives convergence; it does not run automatically just because `gc_grace_seconds` is set. |
| "Increasing RF makes tombstones vanish faster in each SSTable." | **False** | RF increases replica count and does not directly govern per-node purging. |

## 13. Self-check exercises with answers

**Exercise 1.** A table has `PRIMARY KEY ((device_id, event_day), event_time, event_id)`. If you delete with `event_time >= 08:00 AND event_time < 09:00`, which rows are affected when the partition has 07:59, 08:00, 08:30, and 09:00?

**Answer:** Affects **08:00 and 08:30** (and all `event_id`s at those timestamps). 07:59 is outside the range, and 09:00 is excluded by `< 09:00`.

**Exercise 2.** A range tombstone has timestamp `t2`, and an old row in scope has timestamp `t1 < t2`. On read, should the old row appear?

**Answer:** **No.** The range tombstone shadows old records within its scope. A valid write with a timestamp greater than `t2` can appear again.

**Exercise 3.** Why does `SELECT ... LIMIT 5` sometimes still trigger tombstone warnings?

**Answer:** Cassandra must inspect deleted markers/rows while searching for **five live rows**. If many leading rows were deleted, source work can vastly exceed five rows.

**Exercise 4.** Data in a partition was range-deleted at RF = 3, `LOCAL_QUORUM` succeeded, yet one replica is offline. Should `gc_grace_seconds` be set to 0 immediately to free disk?

**Answer:** **No.** The replica missing the tombstone could bring old data back. Handle replica state and repair, evaluating operational safety before adjusting grace.

**Exercise 5.** An organization wants to delete all records of a sensor for exact Nov 21. Must it generate hundreds of hourly range tombstones?

**Answer:** **Not necessarily.** With partition key `(device_id, event_day)`, consider a **partition deletion** for that exact day. Even so, partition deletion still writes a tombstone and requires replica/repair attention.

**Exercise 6.** A system has two query patterns: partition-key reads and token scans. Under which pattern is a range tombstone inside a partition processed?

**Answer:** **Both**, if read data touches the deleted range. Token scans traverse multiple partitions, yet within each partition they still honor row/cell/range/partition tombstones.

## 14. Decision flow summary

~~~mermaid
flowchart TD
    A["Want to delete Cassandra data"] --> B{"Delete entire partition?"}
    B -->|Yes| P["Partition deletion by full partition key"]
    B -->|No| C{"Delete contiguous clustering key range?"}
    C -->|Yes| R["Range deletion within one partition"]
    C -->|No| D["Delete row/cell or redesign data path"]
    R --> T["Write timestamped range tombstone"]
    P --> T2["Write partition tombstone"]
    T --> Q["Reads must reconcile markers with memtable/SSTable data"]
    T2 --> Q
    Q --> E["Repair helps sync deletes across replicas"]
    E --> F["Compaction purges only when safety conditions hold"]
    F --> G["Monitor tombstone scans, latency, SSTables, and disk"]
~~~

**Remember:** A range tombstone is **deletion metadata for a clustering key range belonging to one partition**, not a token range. It makes old rows **disappear logically**, yet data and markers can remain on SSTables to preserve timestamp ordering and protect against lagging replicas. Range queries must reconcile all relevant data and markers; therefore partition/bucket design, choosing TTL vs. DELETE, managing repair/compaction, and observing tombstone scans matter far more than looking solely at how many rows `SELECT` returns.
