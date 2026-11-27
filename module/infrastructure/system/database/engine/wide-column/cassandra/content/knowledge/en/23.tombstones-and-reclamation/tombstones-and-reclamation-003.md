# Reading Through Tombstones and Data Merge Costs

A Cassandra query can **return 20 rows yet have to inspect thousands or millions of deleted values**. The reason lies in how Apache Cassandra stores data under the LSM (*log-structured merge*) model: data is written to memtables and immutable SSTables; updates, deletes, and TTL-expired values can coexist alongside older versions until compaction can safely clean them up. Meanwhile, the read path must **merge versions**, apply **tombstones**, and return the latest logical state.

This lesson belongs to the **Tombstones and Reclamation** chapter of the Apache Cassandra wide-column database module. The topic connects directly to partition keys, clustering columns, replication, consistency levels, CQL, compaction, repair, troubleshooting, and how the Java Driver pages queries.

The focus is not merely "how are tombstones created?", but rather:

- What must Cassandra do when **reading through deletion markers**?
- Why can the amount of data **scanned** be far greater than the amount of data **returned**?
- How does a replica merging memtable/SSTables differ from a coordinator reconciling results across replicas?
- Why are `LIMIT`, paging, raising consistency levels, or forcing compaction not universal fixes for tombstone-scanning queries?
- How do you measure, reproduce, explain, and reduce **read amplification** while preserving deletion semantics?

After this lesson, you will be able to explain the read path through tombstones, analyze a high-latency scenario, safely use CQL and observability tools, write bounded Java queries, and choose appropriate fixes at the schema/TTL/compaction/application level.

## 1. Two facts to remember when reading in Cassandra

**First fact:** Cassandra does not necessarily overwrite old data in place. A new value and a tombstone can reside in **different SSTables**, or one version in the memtable and an older version on an SSTable.

**Second fact:** a `SELECT` result is the **reconciled logical state**, not a verbatim concatenation of all records on disk.

Illustrative example of one `payload` cell for the same full primary key:

```text
Old SSTable:  payload = "A"          write timestamp = 100
New SSTable:  payload = "B"          write timestamp = 200
Memtable:     DELETE payload         write timestamp = 300

SELECT payload:
  compares versions and deletion markers
  -> tombstone 300 shadows A and B
  -> result sees no current payload
```

Versions A and B may still occupy bytes in SSTables. That does not mean Cassandra will return A or B on a valid read. **A newer deletion marker prevents older versions from being surfaced**, until physical reclamation conditions are guaranteed.

### Three layers of work that are easily confused

| Layer | Responsibility | Do not confuse with |
| --- | --- | --- |
| **Storage on one replica** | Locate the partition/slice across memtable and potentially relevant SSTables; merge versions, TTL, and tombstones. | `SELECT LIMIT 20` does not mean opening only 20 cells. |
| **Reconciliation across replicas** | Per consistency level and read protocol, compare/reconcile state from queried replicas and handle discrepancies via versioning. | Not the same as SSTable compaction or running `nodetool repair`. |
| **Physical reclamation** | Compaction can drop old data and tombstones when safety conditions are satisfied. | Does not happen immediately after DELETE or TTL expiration. |

Reading through deletion markers is **normal and necessary** work; performance issues arise when the amount of data that must be inspected is disproportionately large compared to the useful result.

## 2. Following the read path: from CQL to SSTables

Consider a request to fetch the latest events of a device. Cassandra first needs to identify the **complete partition key**, then use the **clustering range** to narrow the data region to read.

Conceptual diagram:

```text
Java Application / cqlsh
         |
         | SELECT ... WHERE full partition key AND clustering range
         v
   Coordinator node
         |
         | Select replicas by token, topology, and consistency level
         v
   Replicas serving the read
         |
         +--> Memtable: new values, unflushed tombstones
         |
         +--> SSTable-1: old values
         |
         +--> SSTable-2: newer tombstones
         |
         +--> SSTable-3: other values/TTLs
         |
         v
   Merge by partition + clustering order
   and reconcile by write timestamp, TTL, deletion markers
         |
         v
   Live rows/cells matching WHERE and LIMIT
         |
         v
 Coordinator reconciles required responses
         |
         v
   CQL results paged back to client
```

On each replica, Cassandra uses structures like **Bloom filters, partition indexes, partition summaries, caches**, and SSTable metadata to avoid reading irrelevant files or sections whenever possible. Not every query has to scan **every SSTable**. However, when a partition has data/versions across multiple sources or tombstones inside the slice being read, the replica still has to inspect enough information to determine the true state.

### What resources does each step consume?

| Step | Work | Notable cost |
| --- | --- | --- |
| Identify partition | Hash partition key, select token and replicas | Routing, network/coordinator. |
| Locate within an SSTable | Check index/filter and partition offset | CPU, I/O, cache misses. |
| Scan clustering slice | Read data positions within the required range | I/O, decoding, bytes scanned. |
| Merge sources | Merge clustering order from memtable/SSTables | CPU, temporary memory, multiple iterators. |
| Apply deletions/TTL | Compare write timestamps, row/range/partition tombstones, cell expiry | CPU, number of markers and versions inspected. |
| Reconcile replicas | Compare state per read protocol/consistency | Network, latency, and extra read work depending on case. |
| Page response | Serialize live rows and transmit to client | Network, heap, page fetch time. |

**Read amplification** occurs when actual work is much higher than the useful data returned. Tombstones are one source of amplification; many SSTables, large cells, wide range queries, and slow replicas can worsen the problem.

## 3. Illustrative schema: device events by day

Using a table with a composite partition key and time-based clustering key:

```sql
CREATE TABLE device_events_by_day (
    tenant_id   text,
    device_id   uuid,
    event_day   date,
    occurred_at timestamp,
    event_id    uuid,
    event_kind  text,
    payload     text,
    source_app  text,
    PRIMARY KEY (
        (tenant_id, device_id, event_day),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    occurred_at DESC,
    event_id ASC
);
```

Analysis:

- **Partition key:** `(tenant_id, device_id, event_day)`. Each device on each day has one logical partition.
- **Clustering columns:** `occurred_at` and `event_id`. Newer rows are queried in descending time order; `event_id` distinguishes events at the same timestamp.
- **Regular columns:** `event_kind`, `payload`, and `source_app`. They can have independent values and TTLs/write timestamps.
- Two different days for the same device are **two different partition keys**, even if all remaining column values are identical.

Writing some test data into one partition:

```sql
INSERT INTO device_events_by_day (
    tenant_id, device_id, event_day,
    occurred_at, event_id, event_kind, payload, source_app
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T08:00:00Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    'reading', 'temperature=38.1', 'gateway-1'
);

INSERT INTO device_events_by_day (
    tenant_id, device_id, event_day,
    occurred_at, event_id, event_kind, payload, source_app
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T08:05:00Z',
    7c2c4f75-5c44-4be4-99a0-08688b465200,
    'reading', 'temperature=38.4', 'gateway-1'
);

INSERT INTO device_events_by_day (
    tenant_id, device_id, event_day,
    occurred_at, event_id, event_kind, payload, source_app
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T08:10:00Z',
    4e52e99a-178e-4d5b-9a31-027d5956e5b8,
    'reading', 'temperature=38.7', 'gateway-2'
);
```

This is lab data. The next sections assume DELETE statements are executed **after** these value versions exist and are observed at an appropriate consistency level. When studying performance, separate the post-DELETE state from cases where operations run concurrently.

## 4. Reading a cell with a tombstone: merging by write timestamp

Suppose we delete `payload` of the 08:05 event:

```sql
DELETE payload
FROM device_events_by_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T08:05:00Z'
  AND event_id = 7c2c4f75-5c44-4be4-99a0-08688b465200;
```

When reading:

```sql
SELECT occurred_at, event_id, event_kind, payload, source_app
FROM device_events_by_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T08:05:00Z'
  AND event_id = 7c2c4f75-5c44-4be4-99a0-08688b465200;
```

The `payload` value is no longer live; however, `event_kind` and `source_app` can still exist. That is the difference between **cell deletion** and **row deletion**.

### Illustrating reconciliation of one cell

```text
SSTable-1:
   payload = "temperature=38.4", timestamp 100

SSTable-2:
   payload = "temperature=38.5", timestamp 150

Memtable:
   DELETE payload, timestamp 200

Read result:
   payload = null, because tombstone at 200 shadows both older versions

However:
   event_kind = "reading" is still live
   source_app = "gateway-1" is still live
   -> row E2 can continue to appear
```

The timestamps 100/150/200 are only illustrative sequence numbers, not real units from a lab operation. Cassandra uses its write timestamps and conflict resolution rules; **the response order of two requests does not replace write timestamp ordering**.

A new write to `payload` with a timestamp newer than the tombstone can create a live value at the same full primary key. A tombstone is not a permanent lock/ban.

## 5. Row, range, and partition tombstones during reads

A deletion marker can shadow a scope larger than a single cell:

| Deletion form | Data shadowed on read | Does it delete rows outside the scope? |
| --- | --- | --- |
| **Cell tombstone** | One regular or static cell | No. |
| **Collection element/complex deletion** | One element or one non-frozen collection | Does not automatically delete other regular columns. |
| **Row tombstone** | Cells/row at one full clustering key | Does not automatically delete other clustering rows or static data. |
| **Range tombstone** | Old rows/cells belonging to a clustering slice of the partition | Does not delete rows outside the range or other partitions. |
| **Partition tombstone** | Old rows and static data in one complete partition key | Does not automatically delete other partition keys. |

### Row deletion

```sql
DELETE FROM device_events_by_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T08:05:00Z'
  AND event_id = 7c2c4f75-5c44-4be4-99a0-08688b465200;
```

Unlike deleting `payload`, this statement deletes **row E2**. When reading the partition in clustering order, the replica must compare the row deletion against old cells belonging to the same clustering key.

### Range deletion

In Cassandra versions/CQL contexts that support deleting by a **clustering slice**, a range tombstone can shadow multiple rows without issuing a separate DELETE for each row.

Conceptual example:

```text
Partition for day 2026-11-21:

08:00 E1     <- delete range starts
08:05 E2     <- inside deleted range
08:10 E3     <- inside deleted range
08:15 E4     <- delete range ends
08:20 E5     <- outside range, still live

Range tombstone can store range [08:00, 08:15)
per supported clustering conditions and order.
```

When reading a slice that intersects this range, the replica must **apply the deletion range** while scanning the corresponding rows and markers. That does not mean each row in the range always has its own physical row tombstone.

### Partition deletion

```sql
DELETE FROM device_events_by_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21';
```

A partition-level tombstone shadows all old data belonging to **that daily partition** at the write timestamp of the delete operation. Events on other days have different partition keys and are not deleted by this statement.

**Do not run the illustrative DELETEs sequentially on the same dataset if you want to compare each deletion type.** Reinitialize the data or use separate test partition keys.

## 6. Why is deleted data still read through before returning results?

Logically, if E2 is deleted, a `SELECT` must not return E2 as a live row. At the storage level, however, this can happen:

```text
Memtable:      tombstone for E2 (timestamp 300)
SSTable-A:     old E1 and E2 (timestamp 100)
SSTable-B:     old E2 and E3 (timestamp 200)
SSTable-C:     newer update to E3 (timestamp 350)

A replica reading a slice containing E1..E3:
- locates relevant sources;
- merges in clustering order;
- evaluates E2 tombstone against old versions of E2;
- evaluates valid version of E3;
- returns only E1/E3 if still live and matching WHERE.
```

Cassandra cannot ignore a tombstone just because another SSTable already has a value. If deletion information were skipped while old versions still existed, deleted data would risk reappearing in results.

### One tombstone can shadow a huge amount of data

From a CQL perspective, `DELETE FROM ... WHERE partition_key` is a single partition-level mutation. Yet it can shadow **millions of old clustering rows**, and the SSTables containing those rows may still occupy significant disk space.

Points to distinguish:

- **Number of DELETE commands:** number of mutations issued by the application.
- **Number of tombstones/markers in storage:** depends on deletion scope, TTL, collections, version, and compaction.
- **Number of cells/markers inspected during a read:** depends on the query, live/deleted data, SSTable overlap, index/filters, and read plan.
- **Number of rows returned:** may be only 0, 10, or 20.

These quantities **are not equal**. You cannot use the number of returned rows to infer exact read-path cost.

## 7. Read amplification: measuring the cost of a small result

Suppose an API needs the **20 most recent live events**, yet many rows in the same clustering range have been deleted.

```text
Clustering order (newest -> oldest):

E1000  deleted
E0999  expired
E0998  deleted
E0997  deleted
...
E0801  deleted
E0800  live #1
...
E0300  live #20

Returned result:             20 live rows
Positions/markers inspected: can be very large
```

A **conceptual** metric:

```text
read_amplification_ratio
  = number of data units or markers that must be processed
    / number of useful data units returned
```

This ratio is for explanation, **not a standardized metric** emitted directly by every Cassandra version. The unit of measurement could be cells, bytes read from disk, SSTable fragments, or rows, so define the unit clearly when comparing.

For example, a workload measuring **2,020 relevant positions** to return **20 rows** has a ratio of 101 by position count. That does not mean each live row corresponds to exactly one cell or that disk bytes read are 101x. Each row may consist of multiple cells, tombstones, and versions across multiple SSTables.

### Why can p99 be high even when p50 is good?

- Most partition keys have few tombstones, while a few tenants or devices have very many.
- Some newest clustering slices experienced heavy DELETEs or TTL expirations.
- Different replicas have different SSTable counts and cache states.
- Background compaction/repair or disk I/O raises latency for certain requests.
- Fan-out queries hitting multiple partitions/shards only need **one slow source** to drag total latency up.

Therefore, monitor **p95/p99, outlier keys, and actual read work**, not just average latency or returned row counts.

## 8. What does `LIMIT` do and not do?

`LIMIT` caps the number of **result rows**; it does not directly cap the number of tombstones scanned.

```sql
SELECT occurred_at, event_id, event_kind
FROM device_events_by_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
LIMIT 20;
```

When live rows sit near the start of the clustering range, Cassandra can stop early once 20 rows are found. When the start of the range has lots of deleted or TTL-expired data, the replica may have to read much longer to find 20 valid rows.

Comparison:

| Query | Scope | Watch out for |
| --- | --- | --- |
| Full partition key, `LIMIT 20` | Latest rows of one daily partition | Can be fast if few tombstones exist at the start of the range. |
| Full partition key, 5-minute clustering range | Narrow time slice | Good if the range has few rows/tombstones. |
| Full partition key, 24-hour range | A large slice within the daily partition | May have to inspect huge numbers of rows/cells/tombstones. |
| `COUNT(*)` on a very large partition | Count valid rows | Can read a lot of data; does not measure physical tombstones. |
| Missing partition key with `ALLOW FILTERING` | May need to filter across a wide scan | Does not cure read amplification; can make it worse. |

### A query with `LIMIT 20` can still fail

Depending on version and configuration, Cassandra has **warning/failure thresholds** when the tombstones scanned by a query exceed a limit. A query needing to scan huge numbers of tombstones to return 20 rows can be slow, time out, or hit safety guards. Do not simply raise the threshold to "let the 20 rows return"; first identify why the query is scanning so many deletion markers.

## 9. Paging is not a tombstone reclamation process

The Cassandra Java Driver can page results: instead of loading thousands of rows in a single response, it fetches data in **result pages**. Page size helps bound response payload and client-side memory.

```text
SELECT ... LIMIT 200
        |
        v
    Page 1: 50 live rows
    Page 2: 50 live rows
    Page 3: 50 live rows
    Page 4: 50 live rows
```

In practice, rows per page and retrieval behavior can be affected by protocol/configuration and data state. Keep in mind:

- **`LIMIT 200`** caps the total results of the SELECT statement.
- **Page size 50** is the page size requested by the driver, not a hard limit on all internal work at a replica.
- **Paging state** lets the query resume; it does not clean SSTables or tombstones.
- If each page has to skip many tombstones, total fetch time across pages can still be high.
- When an application automatically iterates through the entire `ResultSet`, subsequent pages will be fetched; avoid calling `all()` on queries that could return large volumes without a memory budget.

**Measure first-page latency and total traversal time separately**. A fast first page does not guarantee a long historical query or subsequent pages will also be fast.

## 10. Clustering range: narrowing the scan scope

Query-driven table design is an effective way to reduce the number of rows/tombstones a replica must inspect.

For example, wanting only events from 08:00–08:10 on a given day:

```sql
SELECT occurred_at, event_id, event_kind, payload
FROM device_events_by_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at >= '2026-11-21T08:00:00Z'
  AND occurred_at <  '2026-11-21T08:10:00Z'
LIMIT 100;
```

This is **one partition lookup and one clustering range**. The half-open interval `[start, end)` prevents duplicate boundary data when stitching adjacent time slices together.

However:

1. A 10-minute range containing 1,000 deleted events can still be expensive.
2. `LIMIT` does not eliminate tombstones inside the slice.
3. The clustering key `occurred_at` locates the exact time position, but **does not distribute rows of the same partition to other tokens**.
4. Adding filter conditions on `payload` or `event_kind` without an appropriate query model does not automatically create an efficient index.

### A complete partition key is essential

The columns `tenant_id`, `device_id`, and `event_day` **together** form the partition key. A query knowing only `tenant_id` and `device_id` cannot target a single daily partition:

```sql
-- Missing full partition key of the example table:
SELECT *
FROM device_events_by_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12;
```

This is not an efficient primary-key query for reading "all-day" history. To read multiple days, the service layer must enumerate the required day buckets, query each partition, and merge the results.

## 11. Tombstones from TTL: no new DELETE on expiration

TTL (*time to live*) is a major source of expired data in Cassandra. A cell written with a TTL carries expiration metadata; when it expires, it is **no longer live** during reads and is treated like a deletion marker, yet **no new `DELETE` statement** needs to be issued at the exact expiration time.

Example:

```sql
INSERT INTO device_events_by_day (
    tenant_id, device_id, event_day,
    occurred_at, event_id, event_kind, payload
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T09:00:00Z',
    142dd6ae-6706-4f2c-a5e8-61cdd9c22cad,
    'temporary',
    'expire-after-60-seconds'
) USING TTL 60;
```

Before expiration, the written cell can be live. After expiration, Cassandra does not return that value as current data; inside SSTables it may still need to be inspected during reconciliation and compaction.

### A cell's TTL does not automatically delete the entire partition

If a row has multiple columns, they can have **different TTLs/write timestamps**. Expiration of `payload` does not implicitly delete `source_app`, other clustering rows, or the daily partition. Conversely, once all data determining a row's liveness expires, the row may stop appearing as a live row.

Do not interpret every TTL expiration as a **partition tombstone**. TTL expiration acts at the scope of the cells/row liveness written with the corresponding TTL.

### TTL counts from write time, not automatically from `occurred_at`

An event created on Monday but backfilled on Wednesday with `USING TTL 604800` typically expires relative to Wednesday's write time, not "seven days after event time" unless the application computes remaining TTL. If retention is tied to event time, a clear backfill and TTL policy is required.

### Viewing TTL and write timestamp

```sql
SELECT occurred_at, event_id,
       payload, TTL(payload), WRITETIME(payload)
FROM device_events_by_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T09:00:00Z'
  AND event_id = 142dd6ae-6706-4f2c-a5e8-61cdd9c22cad;
```

`TTL(payload)` gives remaining time when the cell is live and has a TTL; `WRITETIME(payload)` gives the cell's timestamp when available. These two functions **do not list physical tombstones**, and `null` in a SELECT result cannot by itself tell whether a cell was DELETEd, expired by TTL, or never written.

## 12. Replica-local merge vs. coordinator reconciliation

The read path has **two levels of merging** to distinguish.

### Level 1: a replica merges versions from memtable/SSTables

The replica must resolve records with the same full primary key but different write timestamps, some containing tombstones/expired cells. This is the direct work of the LSM read path.

```text
Replica A:
  memtable      -> DELETE payload @300
  SSTable-1     -> payload='A' @100
  SSTable-2     -> payload='B' @200
  Logical result -> payload is deleted
```

If many SSTables contain the same partition, the read path can incur heavier work locating, merging, and filtering. Bloom filters/indexes and caching reduce unnecessary work but cannot bypass reconciliation rules.

### Level 2: coordinator processes results from replicas

When a request reads at a consistency level like `LOCAL_QUORUM`, the coordinator may contact multiple replicas, receive data/digests, and resolve discrepancies per the Cassandra version's read protocol. Extra work may be needed when a replica is slow or returns differing states.

```text
Replica A: tombstone @300 (payload deleted)
Replica B: tombstone @300
Replica C: payload='A' @100 (missed DELETE)

Coordinator / read by CL:
  queried replicas and response handling depend on CL/read protocol
  newer state can win once reconciled
```

This is **read-time reconciliation**, not the same as **periodic anti-entropy repair**. *Read repair* behavior upon detecting mismatches can vary by version, configuration, and query scope. Do not claim that a single SELECT guarantees **every replica is permanently repaired**.

### What does consistency level solve?

| Level/aspect | Meaning | Limitation |
| --- | --- | --- |
| `LOCAL_ONE` | Succeeds with reads/writes requiring one replica in the relevant data center. | Can see stale state if the queried replica missed an update/delete. |
| `LOCAL_QUORUM` | Requires a quorum of replicas in the data center; increases convergence probability under corresponding assumptions. | Does not purge physical tombstones, change partition keys, or repair all replicas. |
| Repair | Synchronizes discrepancies across replicas per repair scope/strategy. | Not the same as compaction, and cannot replace plans for repairing long-disconnected replicas. |
| Compaction | Merges SSTables and can drop tombstones/old versions when safe. | Does not perform anti-entropy across all replicas on its own. |

Choosing CL must balance consistency, latency, and availability. **Raising CL does not make tombstones vanish from SSTables**; some queries also have to wait for more replicas.

## 13. `gc_grace_seconds`, repair, and zombie data risk

Cassandra must retain deletion markers long enough so a replica that once missed a DELETE does not bring old data back after other replicas have reclaimed the marker.

```text
T0: A, B, C have payload='A' @100
T1: C disconnects
T2: DELETE payload @200 is stored by A, B
T3: A/B still hold tombstone; reads can shadow 'A'
T4: Eligible repair/synchronization lets C receive the deletion
T5: Compaction is permitted to clean tombstone/old version when safe
```

If C keeps `'A'` while the marker on A/B is purged **too early**, the old state risks reappearing when C returns and data is reconciled. This phenomenon is called **zombie data**.

`gc_grace_seconds` is a setting related to the **protection window before a tombstone becomes eligible for reclamation**, not a guaranteed physical deletion schedule. Purge eligibility also depends on SSTable overlap, compaction strategy, state, and Cassandra version mechanics. Repair must be operated in alignment with the deletion policy and potential outage durations.

Do not:

- Lower `gc_grace_seconds` drastically just to quiet read latency warnings.
- Treat a single `nodetool compact` run as proof that all deletion markers were safely cleaned.
- Assume `LOCAL_QUORUM` or a high RF guarantees replicas never miss a mutation.
- Arbitrarily delete physical files/restore SSTables without understanding tombstones and timestamps.

**Deletion safety is a data correctness requirement**, not merely a disk-saving goal.

## 14. Does compaction reduce the cost of reading through tombstones?

It can, but **neither immediately nor unconditionally**.

Compaction merges versions across SSTables and can drop shadowed values or tombstones when safety conditions are satisfied. When fewer SSTables contain the same partition and obsolete versions are cleared, the read path can have less work to do.

However:

1. Tombstones still within grace or needed to shadow old data in another SSTable may not be purged yet.
2. Compaction creates CPU and disk I/O load and needs disk headroom; forcing it at the wrong time can spike production p99.
3. Continuous writes/deletes can create new tombstones faster than cleanup happens.
4. A partition key that is too large or too hot remains large/hot after compaction; compaction **does not re-shard partition keys**.
5. Compaction strategy must be chosen based on **write/read patterns, updates/deletes, and TTL**, not simply because of one tombstone warning.

### Conceptual STCS, LCS, and TWCS

| Strategy | Typically evaluated aspects | Notes when tombstones exist |
| --- | --- | --- |
| **SizeTieredCompactionStrategy (STCS)** | Groups SSTables by size; fits some append/update write patterns. | Can have significant SSTable overlap before merging. |
| **LeveledCompactionStrategy (LCS)** | Organizes SSTables into levels aiming to limit overlap for many read-heavy workloads. | Trades off write amplification/compaction I/O; does not drop needed tombstones on its own. |
| **TimeWindowCompactionStrategy (TWCS)** | Append-mostly time-series data with nearly uniform TTLs over time windows. | Late writes, updates to old records, or uneven TTLs can hinder data reclamation; not a default choice for every table. |

This is a mental model, not a substitute for load testing on your Cassandra version. TWCS can help SSTables holding data with similar lifecycles get cleaned more smoothly in some workloads, but **does not promise** every tombstone past grace is deleted immediately.

## 15. Diagnosing with `nodetool`: inspecting metrics at the right level

When suspecting a query is reading through many tombstones, start with metrics at the **table and node** level:

```bash
nodetool tablestats app_ks.device_events_by_day
nodetool tablehistograms app_ks device_events_by_day
```

Depending on Cassandra version, useful metrics include:

| Metric group | Diagnostic meaning |
| --- | --- |
| **Average tombstones per slice** | Level of tombstones encountered in observed read slices, per version statistics. |
| **Average live cells per slice** | Estimate of work reading live data; compare against tombstones per slice to see imbalance. |
| **Read latency and SSTables per read** | Read amplification may come from the number of sources being merged. |
| **Partition size / cell count histogram** | Spot heavy tails and outlier partitions. |
| **Pending compactions / SSTable count** | Is background work keeping up with the write/delete rate? |
| **CPU, disk I/O, network, GC per replica** | Identify resource saturation when queries slow down. |
| **Read timeouts/errors and p95/p99 from application** | Assess real SLO impact. |

`tablestats` does not produce an exhaustive `partition_key → exact tombstone count` list. Numbers may be averages/histograms at the **queried node** and reflect different observation scopes. Always record the node, version, timestamp, and observation window when comparing.

You cannot infer tombstone counts from `COUNT(*)` alone. Example:

```sql
-- Use only in a lab or after evaluating cost:
SELECT COUNT(*)
FROM device_events_by_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21';
```

This statement counts **logical rows observed by the query**; it does not enumerate deleted markers in SSTables and can create substantial load if the partition is huge.

## 16. Tracing a suspect read query

In `cqlsh` in a controlled environment, you can enable tracing around **one representative query**:

```sql
TRACING ON;

SELECT occurred_at, event_id, event_kind, payload
FROM device_events_by_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
LIMIT 20;

TRACING OFF;
```

Tracing can provide information about participating replica/coordinator steps, timing, and indications of data/tombstones scanned, depending on version and query. Read a trace as **evidence about the read path**, not as an exact count of all physical tombstones.

**Tracing has overhead**, especially if enabled across many production queries. Enable it only for small samples, with proper authorization, then turn it off.

### Tombstone warnings/thresholds

Some Cassandra versions have settings like `tombstone_warn_threshold` and `tombstone_failure_threshold`. They can help detect/prevent read queries that scan too many tombstones. Exact names, defaults, scopes, and behaviors must be confirmed on the running version/distribution.

If you see warnings or failures:

1. Identify the **query text and partition key**.
2. Find the tombstone source: cell DELETE, row/range deletion, partition deletion, TTL, NULL/collection replacement.
3. Measure the actual live data returned.
4. Check clustering range, SSTable count, compaction backlog, and replica load.
5. Test schema/TTL/query changes before considering threshold adjustments.

**Raising thresholds does not remove tombstones**. It may allow queries to keep scanning even more markers, increasing load or latency.

## 17. A repeatable root-cause analysis workflow

A classic case: a dashboard needs the 20 latest events yet occasionally times out.

| Step | Check | Possible conclusion |
| --- | --- | --- |
| 1 | Does the query have the full partition key? | Distinguish single-partition reads from multi-partition scans. |
| 2 | What are the clustering range and `LIMIT`? | May be scanning too wide or hitting many deleted rows. |
| 3 | How many live rows are in the response? | Distinguish small output from small read work. |
| 4 | Do tracing/metrics show high tombstones per slice? | Confirm the read path actually encounters many deletion markers. |
| 5 | What are SSTables per read and pending compactions? | Check merge costs caused by multiple SSTables/versions. |
| 6 | What is the deletion/TTL source? | Find the cause generating tombstones, not just the symptom. |
| 7 | Is anything unusual with replicas, RF, CL, and repair? | Check version divergence and network/replica bottlenecks. |
| 8 | Test query/partition/bucket/TTL fixes on a production-like workload | Verify p95/p99, timeouts, and data correctness after the change. |

A hypothesis **must be verified**: "The start of the clustering range just had many rows deleted, so the LIMIT 20 query has to scan deep." If the trace shows few tombstones yet high SSTables per read or high node disk I/O, the cause may lie elsewhere. Do not blame tombstones solely because the table has a TTL.

## 18. Designing to reduce reading through tombstones

There are three main approaches: **narrow query scope**, **reduce unnecessary tombstone generation**, and **improve data lifecycle on SSTables**.

### 18.1. Narrow the partition key and clustering range

If all events of a device accumulate in one partition over many months:

```sql
-- Example key putting a device's entire history into one partition:
PRIMARY KEY ((tenant_id, device_id), occurred_at, event_id)
```

Adding a day/hour time bucket isolates history into smaller partitions:

```sql
-- Example daily bucket key:
PRIMARY KEY (
    (tenant_id, device_id, event_day),
    occurred_at, event_id
)
```

This is not just changing `WHERE`: changing the partition key requires creating a **new table and migrating**. The read layer must know the buckets and plan fan-out when querying across multiple days.

**Bucketing does not delete tombstones itself**, but limits the amount of data and markers a daily query must inspect. If a single day is still written too densely, hourly buckets or sharding may fit better; weigh the cost of querying multiple partitions.

### 18.2. Avoid unintended tombstone creation

- Do not automatically bind `null` for every absent field in a PATCH API; distinguish **absent/UNSET** from **explicit delete**.
- Avoid running millions of individual delete statements when a better lifecycle model exists and business scope permits.
- Avoid very large non-frozen collections that are repeatedly replaced in full; consider element-level updates or query-driven child tables.
- Choose reasonable TTLs rather than pairing very short TTLs with frequent scans over slices full of expired values.
- Do not regenerate `event_id` or time buckets on retries, as that can produce unwanted extra rows.

### 18.3. Align TTL and compaction appropriately

For append-mostly time-series data with relatively uniform TTL/retention, evaluate TWCS and organize time buckets around the data lifecycle. When there are late-arriving data, frequent updates/deletes, or varied TTLs, test carefully because compaction strategy assumptions may not hold.

Do not lower `gc_grace_seconds` arbitrarily. Any change affecting tombstone reclamation must evaluate repair/replica safety and zombie data risk.

### 18.4. Serve top-N queries with an appropriate data path

If a dashboard always wants the "20 latest live events" while the raw store contains millions of very short-TTL or bulk-deleted events, consider a **query-serving table** or dedicated aggregation/routing mechanism based on product requirements. However, secondary tables must have update/delete synchronization rules, TTLs, and partial-failure handling; they are not updated atomically just by sharing a tenant.

## 19. Java Driver 4.x: reading a bounded slice

The repository below queries **one daily partition** with a **specific clustering slice**. The example uses Java Driver 4.x and assumes `CqlSession` is connected to the keyspace containing `device_events_by_day`.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public final class DeviceEventReader {
    private final CqlSession session;
    private final PreparedStatement byDayRange;

    public DeviceEventReader(CqlSession session) {
        this.session = session;
        this.byDayRange = session.prepare(
            "SELECT occurred_at, event_id, event_kind, payload " +
            "FROM device_events_by_day " +
            "WHERE tenant_id = ? AND device_id = ? AND event_day = ? " +
            "AND occurred_at >= ? AND occurred_at < ? LIMIT ?"
        );
    }

    // Reads only one UTC day, returning at most limit live rows.
    public List<EventRow> readSlice(
            String verifiedTenantId,
            UUID deviceId,
            Instant startInclusive,
            Instant endExclusive,
            int limit) {

        if (limit < 1 || limit > 200) {
            throw new IllegalArgumentException("limit must be 1..200");
        }
        if (!startInclusive.isBefore(endExclusive)) {
            throw new IllegalArgumentException("empty time range");
        }

        LocalDate day = startInclusive.atZone(ZoneOffset.UTC).toLocalDate();
        LocalDate lastDay = endExclusive.minusNanos(1)
            .atZone(ZoneOffset.UTC).toLocalDate();

        if (!day.equals(lastDay)) {
            throw new IllegalArgumentException(
                "range must stay inside one UTC day");
        }

        BoundStatement statement = byDayRange.bind(
            verifiedTenantId,
            deviceId,
            day,
            startInclusive,
            endExclusive,
            limit
        ).setPageSize(50);

        List<EventRow> events = new ArrayList<>();

        for (Row row : session.execute(statement)) {
            events.add(new EventRow(
                row.getInstant("occurred_at"),
                row.getUuid("event_id"),
                row.getString("event_kind"),
                row.getString("payload")
            ));
        }

        return events;
    }

    public static final class EventRow {
        public final Instant occurredAt;
        public final UUID eventId;
        public final String eventKind;
        public final String payload;

        EventRow(Instant occurredAt, UUID eventId,
                 String eventKind, String payload) {
            this.occurredAt = occurredAt;
            this.eventId = eventId;
            this.eventKind = eventKind;
            this.payload = payload;
        }
    }
}
```

### What this code accomplishes

1. Binds the complete **partition key** (`tenant_id`, `device_id`, `event_day`) and clustering range.
2. Derives the UTC day bucket from the start timestamp; ensures the half-open interval stays within **one day**.
3. Bounds the number of **logical rows returned** via `LIMIT ?` up to 200 per the illustrative policy.
4. Uses a page size of 50 to avoid requesting an overly large single response.
5. Treats `payload == null` as **no current live value visible**; the code does not guess whether it is due to a tombstone or TTL.

### What this code does not solve

- It **does not force Cassandra to read at most 200 tombstones**; workloads with dense deleted ranges can still be slow.
- A page size of 50 does not remove tombstones or reduce old data copies on SSTables.
- Multi-day queries must enumerate buckets, read relevant partitions, and merge by `occurred_at DESC, event_id ASC`.
- An API calling multiple buckets/shards needs **concurrency/backpressure limits**; unbounded fan-out can turn one slow query into many slow queries.
- `verifiedTenantId` must come from an authenticated/authorized context; putting a tenant ID in the key does not automatically provide row-level security.

To verify performance, the application should measure **first page**, **total fetch**, returned row counts, p95/p99, and controlled correlation/tracing. Do not arbitrarily log sensitive payloads or identifiers for diagnosis.

## 20. Lab: creating live data, deletes, TTLs, and observing the read path

The goal of this lab is to **observe logical semantics and operational signals** — do not assume one small DELETE will visibly change metrics on a production table.

### Step 1 — Create the lab table and three rows

Using the `device_events_by_day` schema from section 3 in a test keyspace, write three rows with the same partition key. Read back:

```sql
SELECT occurred_at, event_id, event_kind, payload
FROM device_events_by_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
LIMIT 10;
```

Initially the result has three events ordered by `occurred_at DESC`.

### Step 2 — Compare cell deletion and row deletion

**Round A:** delete `payload` of E2 using the `DELETE payload` statement from section 4 and read back. E2 may still be returned because `event_kind` and `source_app` are still live.

**Round B:** reinitialize the sample data, then delete all of E2 using `DELETE FROM ... WHERE full_primary_key` from section 5. E2 is no longer returned as a live row under the observed deletion state.

**Do not run a cell deletion followed by a row deletion on the same data to infer the difference without checking the intermediate state.**

### Step 3 — Write a cell with TTL

Run `INSERT ... USING TTL 60` from section 11 on **another row**. Check `TTL(payload)` while the value is live. After TTL expiration in the lab environment, check again: payload is no longer considered live.

Do not conclude "TTL doesn't work" just because SSTable size does not drop immediately.

### Step 4 — Inspect traces and statistics

Enable tracing **for only a few queries** as in section 16. Then inspect `nodetool tablestats` and `tablehistograms` if you have lab operational access.

An experiment with only a few rows is **not enough** to trigger tombstone warnings or significantly shift histograms. To measure performance, you need a workload generator controlling DELETE/TTL rates, clustering ranges, SSTable counts, and read/write load — run in a test environment rather than adding load to production.

### Step 5 — Form a hypothesis and verify it

For example:

> "When 90% of the newest events in a partition have expired by TTL, a query fetching the 20 newest live events will have to inspect more data."

Vary **one factor at a time** (TTL expiration rate, partition size, page size, compaction strategy, or range width), and measure p95/p99 and traces. The goal is to prove the **cause of read amplification** rather than measuring a random slow query.

## 21. Quantitative scenario: few results, many tombstones

An IoT service has one device producing **200 events/second**. Average payload is **400 bytes/event**. Initial design:

```sql
PRIMARY KEY (
    (tenant_id, device_id),
    occurred_at, event_id
)
```

All events of one device go into **one logical partition**. During one day of continuous writes:

```text
200 events/s × 86,400 s = 17,280,000 rows/day

Logical payload/day:
17,280,000 × 400 bytes
= 6,912,000,000 bytes ≈ 6.44 GiB
```

Suppose a business job deletes many of the newest events in the same partition, leaving only **a small fraction** of rows near the start of the clustering range alive. Query:

```sql
SELECT occurred_at, event_id, event_kind
FROM device_events_by_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
LIMIT 20;
```

It may have to scan across a huge range of rows/tombstones to find 20 valid rows. This risk comes from **data shape and tombstone generation sources**, not because Cassandra "forgot" to execute DELETE.

Note that the example above compares two schemas: the **unbucketed** design creates one massive historical partition, whereas the CQL query illustrates the design **with `event_day`**. Even though daily bucketing reduces relative size, **17,280,000 rows in one day** can still be large or hot; applying this to a real system requires evaluating hour/minute buckets and proper query bounds.

### If choosing a 5-minute bucket

```text
200 events/s × 300 s = 60,000 rows/bucket

Logical payload:
60,000 × 400 bytes = 24,000,000 bytes ≈ 22.9 MiB
```

A 5-minute bucket reduces single-partition size under the assumed traffic, yet a 24-hour history query may need **288–289 buckets**, depending on boundaries. It also does not automatically eliminate tombstones generated within an active bucket.

**Trade-off:** reduces per-partition size/read scope, increases partition lookups and merge costs for long-range queries. Do not pick a new bucket solely by row count; measure p95/p99, read amplification, write hotspots, and fan-out.

## 22. Misconceptions to eliminate

| Claim | Issue | Correct understanding |
| --- | --- | --- |
| "DELETE succeeded so old data is gone from SSTables." | DELETE writes a logical tombstone; physical reclamation comes later. | Distinguish read results from disk footprint. |
| "With LIMIT 20 the replica only inspects 20 cells." | Many cells/rows/tombstones may be skipped before finding 20 live rows. | Measure scanned tombstones and clustering range. |
| "Paging cleans tombstones page by page." | Paging only splits results and continues the query. | Use paging for memory/network, do not treat it as GC. |
| "COUNT(*) tells us the number of tombstones." | Counts logical rows, not physical markers. | Use metrics/tracing/appropriate SSTable tools. |
| "Every SELECT always scans every SSTable end to end." | Cassandra uses filters/indexes/caches and locates the partition/slice. | Cost depends on relevant SSTables, tombstones, and query scope. |
| "Increasing RF or LOCAL_QUORUM removes tombstones faster." | RF/CL govern replicas and acknowledgments, not tombstone purging. | Look at compaction, repair, retention, and schema. |
| "Running repair causes compaction to clean all tombstones." | Repair syncs replicas; it does not replace purge conditions. | Monitor grace, overlap, compaction, and version behavior. |
| "Lowering gc_grace_seconds always reduces latency with zero risk." | Can increase zombie data risk. | Set policy based on repair and how long replicas may be absent. |
| "TWCS cures every tombstone-heavy query." | Has assumptions on write/TTL patterns; does not change partition keys. | Benchmark with real workloads. |
| "A small partition cannot suffer read amplification." | Dense TTLs/deletes or many SSTables can still make reads expensive. | Measure markers/bytes that must be inspected. |
| "A tombstone is literally the NULL value read back." | NULL could mean never written or deleted/TTL-expired. | Do not infer root cause from SELECT null. |
| "Scanning the whole tenant with ALLOW FILTERING fixes slow queries." | Can increase partitions/cells inspected. | Design tables around queries and full keys. |

## 23. Exercises and answers

A session-tracking application has the table:

```sql
CREATE TABLE activities_by_user_day (
    tenant_id   text,
    user_id     uuid,
    activity_day date,
    occurred_at timestamp,
    activity_id uuid,
    action      text,
    details     text,
    PRIMARY KEY (
        (tenant_id, user_id, activity_day),
        occurred_at, activity_id
    )
) WITH CLUSTERING ORDER BY (
    occurred_at DESC, activity_id ASC
);
```

In one day, user U creates **50,000 rows**. A job deletes 30,000 recent rows, and another 10,000 rows carried a short TTL and have expired. The dashboard wants the **20 newest live activities**.

**Questions:**

1. What is the table's partition key? Does `occurred_at` change the token as it increases?
2. If `SELECT ... LIMIT 20` returns exactly 20 rows, does that prove the replica only read 20 rows?
3. Why can a tombstone in the memtable shadow a value in an older SSTable?
4. When reading from multiple SSTables, what information must the replica rely on to decide if a cell is live?
5. How does replica-internal reconciliation differ from cross-replica reconciliation?
6. If `details` is DELETEd while `action` remains live, does the whole row necessarily disappear?
7. If 10,000 rows have cells with expired TTLs, must the application issue 10,000 DELETE commands at expiration time?
8. Will running `COUNT(*)` give the number of tombstones in the partition?
9. Does a page size of 50 cap the number of tombstones Cassandra inspects at 50?
10. What are two other causes besides tombstones that can increase SELECT p99?
11. If a replica was offline when DELETE was written and returns after the tombstone was unsafely purged, what risk arises?
12. What is one **schema-level** measure and one **mutation/query-level** measure to reduce read amplification?
13. If the 1,000 newest events are all deleted, does choosing `CLUSTERING ORDER BY DESC` guarantee fetching the 20 newest rows is fast?
14. Why shouldn't you immediately fix this by raising `tombstone_failure_threshold`?
15. When evaluating a compaction strategy, what factors besides current tombstone count must you consider?

**Answers and explanations:**

1. `(tenant_id, user_id, activity_day)` is the composite partition key; `occurred_at` is a clustering column and does not participate in token calculation.
2. **No.** LIMIT constrains live output rows; it does not strictly bound the cells/tombstones/SSTables inspected.
3. Because a tombstone with a newer write timestamp can shadow older values during the merge process.
4. It must reconcile by partition/clustering key, write timestamp, tombstones, TTL, and liveness/conflict rules.
5. A replica merges local data sources; the coordinator handles responses/discrepancies across replicas per the read protocol and consistency level.
6. **No.** Deleting a regular column is not equivalent to row deletion if the row still has appropriate live data.
7. **No.** Values carrying TTL expire automatically per stored metadata and are treated as deleted data during reads.
8. **No.** COUNT(*) counts logical rows seen by the query, not physical markers.
9. **No.** Page size relates to result rows per page, not internal tombstone scan limits.
10. For example: many SSTables containing the same partition, high disk I/O, overloaded replicas/coordinator, slow network, or ongoing compaction.
11. **Zombie data** risk because the old version on the slow replica could reappear.
12. Schema: bucket by time/access path. Mutation/query: avoid unintended NULL writes, reduce individual DELETEs, or narrow the clustering range.
13. **No.** Cassandra may have to inspect 1,000 deleted positions before finding live rows.
14. Loosening thresholds masks symptoms and allows queries to burn even more CPU/I/O; find the tombstone source first.
15. Consider TTL/retention, update/delete patterns, SSTable overlap, late-arriving data, repair/grace, I/O, load, and Cassandra version.

## 24. Checklist for handling a query reading through many tombstones

- [ ] Identify the **exact full partition key** and clustering range of the slow query.
- [ ] Compare rows **returned** against tombstones/data scanned via tracing or metrics.
- [ ] Distinguish tombstones from **cell/row/range/partition DELETE**, NULL, collections, or TTL.
- [ ] Measure p95/p99, timeouts, SSTables per read, CPU/I/O, compaction backlog, and outlier keys.
- [ ] Check whether the query reads **one partition**, multiple buckets, or fans out across shards.
- [ ] Do not use `COUNT(*)` or full-table scans to measure tombstones in production.
- [ ] Check consistency level, replica health, and repair schedule when stale data or replica divergence appears.
- [ ] Do not arbitrarily lower `gc_grace_seconds` or force large-scale compactions without understanding safety conditions.
- [ ] Inspect TTLs, late-arriving events, update/delete patterns, and uniformity of data lifecycles.
- [ ] Test reasonable partition key/bucket designs, clustering ranges, and query paths on a representative workload.
- [ ] Use Java prepared statements, paging, bounded results, bounded concurrency, and consistent UTC bucket calculation.
- [ ] Verify **data correctness** after every change: whether DELETE still holds, whether zombie data occurs, or whether fan-out misses data.
- [ ] Conclude resolution only when latency, replica load, and reclamation behavior all meet verification criteria.

## 25. Key takeaways

- Reading in Cassandra is the process of **locating a partition and slice**, merging data from memtable/SSTables, applying write timestamps, tombstones, and TTLs, and returning live rows.
- **Tombstones exist to preserve deletion semantics** in an environment with multiple SSTables and replicas; deletion markers cannot be skipped just to read faster.
- **Read amplification** occurs when merge/scan cost is far higher than useful data. A 20-row result may require inspecting huge numbers of tombstones.
- **`LIMIT` and paging** bound returned data; they do not shrink partitions or clean tombstones.
- **Replica-local merging** differs from **coordinator reconciliation across replicas**; repair and compaction have distinct functions and do not replace each other.
- **TTL expiration** makes a cell no longer live without a new DELETE mutation, yet markers/old data can persist on SSTables until safely reclaimed.
- **`gc_grace_seconds`, SSTable overlap, and repair** govern tombstone reclamation safety; lowering grace without justification can cause zombie data.
- **Schema/partition key changes, clustering range narrowing, mutation patterns, and TTL lifecycles** are usually more sustainable than merely loosening tombstone thresholds.
- Use **metrics, tracing, histograms, and benchmarks** to explain p99 and prove improvements, rather than drawing conclusions from SELECT row counts.

Understanding the work Cassandra performs **before returning live rows** is the foundation for diagnosing tombstone-slow queries. It helps you design wide-column tables around queries, choose reasonable consistency levels, coordinate compaction and repair safely, and write Java applications that control resources and behavior when data is deleted or expires.
