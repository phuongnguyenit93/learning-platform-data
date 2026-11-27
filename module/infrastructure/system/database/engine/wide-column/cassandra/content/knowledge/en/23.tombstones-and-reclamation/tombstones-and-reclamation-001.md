# How DELETE, NULL, and Expired TTL Create Tombstones

In Apache Cassandra, **deleting data is not like immediately removing a record from every file on disk**. Cassandra uses a *log-structured merge* (LSM) write architecture: data is written to the commit log/memtable, flushed to immutable SSTables, and gradually merged via compaction. When data needs to be deleted, Cassandra writes a **tombstone** — a deletion marker carrying timestamp information — so that replicas and SSTables know that older versions of the data are no longer allowed to appear in read results.

There are three scenarios that commonly lead to a deleted state:

1. A **`DELETE`** statement deleting a column, a row, a range of rows, or an entire partition.
2. A **`NULL`** write to a column value — such as `UPDATE ... SET payload = null` — which carries deletion semantics for that value.
3. A value with an expired **TTL**: the value becomes expired data and is treated like a tombstone during reads/reclamation, **without requiring a new `DELETE` statement** at the exact expiration time.

Tombstones are necessary so that an old value still sitting on an SSTable or a slow-to-update replica **does not reappear on its own**. However, too many tombstones can also make queries expensive in terms of CPU/I/O and make compaction more complex. That is why the **Tombstones and Reclamation** chapter needs to be understood alongside partition keys, replication, consistency levels, compaction, repair, and CQL/Java operations.

After this lesson, you will be able to:

- Distinguish between **live data**, **a value that never existed**, **NULL**, and **tombstones**.
- Explain how tombstones are formed from `DELETE`, `NULL` writes, and expired TTLs.
- Distinguish between deleting **a cell, a row, a range of clustering rows, or an entire partition**.
- Understand how **write timestamps** and replicas determine whether a value can still be read.
- Explain why TTL expiration/deletion **does not mean** data is physically reclaimed immediately.
- Recognize signs of queries scanning many tombstones and how to minimize them in table design.
- Practice CQL and the Java Driver when deleting or writing data with TTL.

## 1. What problem do tombstones solve?

Suppose a record `payload = 'temperature=38.1'` has been successfully written. Because Cassandra has multiple replicas and multiple SSTables, this record may exist in **multiple places**. If data were only removed from one memtable or SSTable, an older version from another source could still be read back.

Cassandra solves this with **deletion markers carrying a write timestamp**:

```text
T0: Write payload = "temperature=38.1" [write timestamp = 100]

   Replica A: SSTable-1 contains payload
   Replica B: SSTable-2 contains payload
   Replica C: SSTable-3 contains payload

T1: DELETE payload                     [delete timestamp = 200]

   Replica A: old payload + new tombstone
   Replica B: old payload + new tombstone
   Replica C: may not have received the tombstone yet

T2: Read/reconcile versions by timestamp
    tombstone at 200 shadows old value at 100
```

Old data may still remain on SSTables for some time. **A tombstone is the necessary information to know that old data has been logically deleted**. Later, when compaction determines it can be safely reclaimed, that data and the corresponding tombstones can be removed from storage files.

> **Key point:** A tombstone is a component of Cassandra's consistency model and data lifecycle; it is not merely a row with a `deleted = true` column added by the application.

### Non-existent data differs from deleted data

| State | Meaning | Does a tombstone necessarily exist? |
| --- | --- | --- |
| Column never written | No value has ever existed for that column | **No.** |
| Live value | Valid cell exists at read time | No tombstone is currently winning over that value. |
| Column deleted via `DELETE` | A delete operation occurred to prevent older versions from reappearing | **A tombstone may exist** in storage. |
| Writing `NULL` to a column | CQL treats this as deleting the column value | Typically creates a tombstone for the corresponding cell. |
| Cell with expired TTL | Value is no longer live and is treated as deleted | Treated like a tombstone, without a new DELETE statement. |
| Reading `null` for a column | API/CQL sees no current value | **Not sufficient proof** that a tombstone ever existed: it may never have been written. |

Therefore, `SELECT` returning `null` is not a tool to deduce the exact type of deletion that took place.

## 2. A schema used throughout the lesson

Let's design a sensor events table with a **composite partition key**, to clearly see deletion scopes:

```sql
CREATE TABLE sensor_events_by_day (
    tenant_id   text,
    sensor_id   uuid,
    event_day   date,
    occurred_at timestamp,
    event_id    uuid,
    event_kind  text,
    payload     text,
    note        text STATIC,
    PRIMARY KEY (
        (tenant_id, sensor_id, event_day),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    occurred_at DESC,
    event_id ASC
);
```

Analysis:

| Component | Column | Role |
| --- | --- | --- |
| Partition key | `(tenant_id, sensor_id, event_day)` | Selects the partition and replica set. |
| Clustering columns | `occurred_at`, `event_id` | Identifies the event row within the partition. |
| Regular columns | `event_kind`, `payload` | Values specific to each event. |
| Static column | `note` | Shared value for the entire daily partition of the sensor. |

Writing sample data:

```sql
INSERT INTO sensor_events_by_day (
    tenant_id, sensor_id, event_day, occurred_at, event_id,
    event_kind, payload
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T08:00:00Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    'reading',
    'temperature=38.1'
);

INSERT INTO sensor_events_by_day (
    tenant_id, sensor_id, event_day, occurred_at, event_id,
    event_kind, payload
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T08:05:00Z',
    7c2c4f75-5c44-4be4-99a0-08688b465200,
    'reading',
    'temperature=38.4'
);
```

The two rows belong to the **same daily partition** but have different clustering keys. The deletion exercises below can be run independently on the newly initialized data; if multiple examples are run consecutively, the actual state will depend on the operations performed earlier.

## 3. `DELETE` a column: creating a cell-level tombstone

To delete `payload` for the 08:00 event while keeping `event_kind` and the row identity:

```sql
DELETE payload
FROM sensor_events_by_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T08:00:00Z'
  AND event_id = 8817a208-1858-4144-86e9-b24d9083e478;
```

Here the `WHERE` condition identifies **a single row** by its full partition and clustering key. The `DELETE payload` part only removes the value of the `payload` column in that row.

Once the deletion is observed at an appropriate consistency level, a query may return:

| `occurred_at` | `event_kind` | `payload` |
| --- | --- | --- |
| 08:00 | reading | `null` |

The row still exists because `event_kind` or other live information still has a value. This is a **cell tombstone**, not a full row deletion.

**Important:** Cassandra does not have to read beforehand to check if `payload` exists. The delete statement can be accepted and write a tombstone even if no prior value existed; deletion semantics are used to protect against older versions that might arrive late.

### Deleting a static column

Because `note` is declared `STATIC`, it belongs to the partition level. You can delete `note` using only the partition key:

```sql
DELETE note
FROM sensor_events_by_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21';
```

This operation does not delete the event rows. A static column may appear across multiple **result** rows in a SELECT, but semantically it still belongs to only **one partition**; there is no need to issue a DELETE for each clustering row.

## 4. `DELETE` a row, a range, or an entire partition

The scope of `DELETE` determines the type of tombstone created and the region of data it shadows.

### 4.1. Deleting one row by full primary key

```sql
DELETE FROM sensor_events_by_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T08:00:00Z'
  AND event_id = 8817a208-1858-4144-86e9-b24d9083e478;
```

Omitting column names after `DELETE` means deleting the corresponding **clustering row**, not just a single regular column. Cassandra can represent this operation via a **row deletion tombstone** to shadow older cells of that row.

If there is a static column `note`, deleting a clustering row like this **does not implicitly delete `note`** for the partition.

### 4.2. Deleting a slice of clustering keys

With a schema clustered by `occurred_at` then `event_id`, a deletion over a **valid clustering range** within the same partition can be represented by a **range tombstone**:

```sql
DELETE FROM sensor_events_by_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at >= '2026-11-21T08:00:00Z'
  AND occurred_at <  '2026-11-21T09:00:00Z';
```

This is an example of deleting a slice **inside a single partition**, not a distributed query across the entire table. Details of supported range `DELETE` predicates and tombstone representations can vary by version/schema; test on your target version before applying in production.

A **range tombstone** can shadow many clustering rows without needing a separate CQL DELETE for each row. However, it can still incur read cost across the deleted slice, especially before compaction cleans up the data.

### 4.3. Deleting an entire partition

```sql
DELETE FROM sensor_events_by_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21';
```

This is a **partition deletion**. It affects clustering rows and static data within the specified partition key. A partition-level tombstone shadows old data across the entire partition at the write timestamp of the delete operation.

Comparison table:

| Statement | Logical scope | Tombstone concept |
| --- | --- | --- |
| `DELETE payload ... WHERE full_primary_key` | One regular column in one row | Cell tombstone. |
| `DELETE note ... WHERE partition_key` | One static column of the partition | Static-cell tombstone. |
| `DELETE FROM ... WHERE full_primary_key` | One clustering row | Row tombstone. |
| `DELETE FROM ... WHERE partition_key AND clustering_range` | A range of clustering rows | Range tombstone, when the operation is supported. |
| `DELETE FROM ... WHERE partition_key` | Entire partition, including static data | Partition tombstone. |

**Do not treat deleting an entire partition as a "fast physical delete that creates no tombstones."** In distributed storage, Cassandra still needs to write a deletion marker with timestamp information to prevent old data from reappearing.

## 5. `NULL` in CQL: not "leave the column untouched"

A very common misconception is treating `NULL` like omitting a column or keeping its current value. In Cassandra, **writing `NULL` to a regular column typically carries the semantics of deleting that column's value**.

Example:

```sql
UPDATE sensor_events_by_day
SET payload = null
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T08:05:00Z'
  AND event_id = 7c2c4f75-5c44-4be4-99a0-08688b465200;
```

According to CQL semantics, this operation deletes the `payload` cell of the specified row and can create a tombstone, similar in intent to `DELETE payload`.

### Three different scenarios

Suppose the row already has `event_kind = 'reading'` and `payload = 'temperature=38.4'`.

**Scenario A — Omitting the column:**

```sql
UPDATE sensor_events_by_day
SET event_kind = 'calibrated-reading'
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T08:05:00Z'
  AND event_id = 7c2c4f75-5c44-4be4-99a0-08688b465200;
```

`payload` **is not mentioned**, so this operation does not request deleting it.

**Scenario B — Writing NULL:**

```sql
UPDATE sensor_events_by_day
SET payload = null
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T08:05:00Z'
  AND event_id = 7c2c4f75-5c44-4be4-99a0-08688b465200;
```

`payload` is deleted according to CQL semantics; the old value may be shadowed by a tombstone.

**Scenario C — Passing UNSET through the driver:**

In prepared statements, Cassandra supports an **UNSET** state for bind variables that are allowed to send no value. `UNSET` means *perform no mutation for that column*, which is completely different from `NULL`. The specific mechanism and API depend on the driver/version; with the Java Driver, use the bound statement's *unset* capability when you genuinely need to skip updating a column, rather than binding `null` and hoping the column stays intact.

| Case | Intended meaning | Typical impact |
| --- | --- | --- |
| Completely omit column name from `INSERT`/`UPDATE` | Do not update the column | Does not create a tombstone **just because the column is missing**. |
| Write `payload = null` | Delete the column value | May create a cell tombstone. |
| Bind variable as `UNSET` | Do not send a mutation for that column | Does not modify the corresponding cell. |
| Write empty string `''` to a `text` column | Store an empty text value | Not equivalent to `NULL`. |
| Read `payload` and receive `null` | No current value is visible | Does not prove the cause was NULL/DELETE/TTL. |

**You cannot write NULL as part of a primary key** to represent a "keyless" row; Cassandra requires all necessary key components to be valid.

### `INSERT` with a column receiving NULL

`INSERT` does not necessarily mean "insert every column." If a column is explicitly passed as `null`, it has deletion semantics for that cell. If you **do not list the column** in the INSERT column list, the operation does not automatically create a tombstone for the omitted column.

For JSON APIs or Java mappers, clearly distinguish between a **missing field** and a **field with value NULL** before generating CQL. If the mapping layer converts every absent property into `null` and rewrites the entire object, it can generate many unintended tombstones.

## 6. TTL: expiration is logical deletion, not a new DELETE

TTL (*time to live*) allows a value to expire automatically after a configured number of seconds. For example, writing an event with a one-hour TTL:

```sql
INSERT INTO sensor_events_by_day (
    tenant_id, sensor_id, event_day, occurred_at, event_id,
    event_kind, payload
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T09:00:00Z',
    4e52e99a-178e-4d5b-9a31-027d5956e5b8,
    'reading',
    'temperature=38.7'
) USING TTL 3600;
```

This sets a **3,600-second** TTL for the values written by the operation, according to Cassandra's TTL semantics. Once expired, those values are no longer considered live during reads. **No client has to send a `DELETE` at the exact 3,600th second.**

```text
Write time                         TTL expiration time
     |                                   |
     v                                   v
 Live cell, with TTL                Expired cell
     |                                   |
     |------ visible to SELECT ----------|
                                         |
                                         v
                              Treated as a tombstone
                                         |
                                         v
                         Awaiting reclamation conditions in compaction
```

The subtle point: TTL is usually stored as **expiration metadata attached to the cell**. Upon expiration, Cassandra treats that cell as deleted data. A new `DELETE` mutation does not have to be sent to replicas at the moment of expiration; therefore, you should not imagine the cluster having to schedule millions of DELETE statements.

### `USING TTL` on UPDATE

You can set a TTL for the new value in an update operation:

```sql
UPDATE sensor_events_by_day
USING TTL 1800
SET payload = 'temporary-reading'
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T08:05:00Z'
  AND event_id = 7c2c4f75-5c44-4be4-99a0-08688b465200;
```

The new TTL applies to **the rewritten cell**. It does not mean every row in the same partition expires automatically after 1,800 seconds. If `event_kind` was not changed and has no TTL, that cell can still remain after `payload` expires.

### Table-level default TTL

Cassandra also has a `default_time_to_live` schema option. Example:

```sql
ALTER TABLE sensor_events_by_day
WITH default_time_to_live = 86400;
```

This option sets a default TTL for writes to the table according to the version's semantics, unless a write specifies an appropriate TTL. **Changing the default TTL is not a physical deletion of all old data.** You need to verify its impact on new writes, live data, and columns with individual TTLs before applying it in production.

> **Note:** If you run the exercises in order, `ALTER TABLE ... default_time_to_live` changes the behavior of subsequent writes. Perform this on a test table, and do not apply it arbitrarily to a table serving production traffic.

## 7. Viewing TTL and write timestamp with CQL

You can inspect the metadata of a current value:

```sql
SELECT occurred_at, event_id,
       payload,
       TTL(payload),
       WRITETIME(payload)
FROM sensor_events_by_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T09:00:00Z'
  AND event_id = 4e52e99a-178e-4d5b-9a31-027d5956e5b8;
```

Interpretation:

- `TTL(payload)` returns the **remaining** TTL in seconds if the current cell has a TTL and is still live; the result can be `null` if the cell no longer has a value or has no TTL.
- `WRITETIME(payload)` returns the value's write timestamp in **microseconds** when available; it is not `occurred_at` (the business timestamp).
- After a cell expires, regular queries may no longer return the cell's value; `TTL`/`WRITETIME` **are not tools for exhaustively listing physical tombstones**.
- If cells in the same row have different TTLs, you cannot infer the entire row's state from the TTL of `payload` alone.

### TTL counts from write time, not necessarily event time

Suppose an event has `occurred_at = 2026-11-20T10:00:00Z` but arrives at the cluster on `2026-11-21T10:00:00Z`. If it is written on arrival with `USING TTL 86400`, it expires relative to the write time, **not automatically at 2026-11-21T10:00:00Z** just because the event time was a day earlier.

For retention based on business time, the application must proactively compute the remaining TTL or use an appropriate lifecycle policy, especially for late-arriving events and backfills.

## 8. Timestamps determine which value or tombstone wins

Cassandra attaches a write timestamp to each cell/mutation. When multiple versions of the same data exist, reconciliation uses timestamps and tie-breaking rules to determine the valid state.

Conceptual example:

```text
Cell payload = "A"            write timestamp 100
Cell payload = "B"            write timestamp 150
DELETE payload               write timestamp 200

On read/merge: tombstone at 200 shadows A and B.

Later:
Cell payload = "C"            write timestamp 250

On read/merge: C can appear because its timestamp is newer than the tombstone.
```

**These timestamp values are only to illustrate ordering**, not real microsecond values used in production. In Cassandra, a DELETE operation does not mean "permanently forbid all future writes to this key"; a valid write with a newer write timestamp can create a new current value.

Points to remember:

1. **Tombstones must be kept long enough** to shadow older versions with lower timestamps across replicas/SSTables.
2. Writing multiple times to the same primary key can create multiple versions of a cell across SSTables until compaction.
3. Write timestamps do not necessarily match the request arrival order according to the application clock; writing with client-specified timestamps must be controlled very carefully.
4. A `DELETE` statement knows nothing about a business intent of "permanently deleted" if the application later writes data with a newer timestamp.
5. If a client clock is skewed or manually writes a timestamp in the future, a tombstone may even shadow subsequent real-time writes until new write timestamps surpass it.

In particular, do not assign write timestamps far in the future just to "guarantee DELETE wins." That can cause hard-to-fix bugs when valid data is written later.

## 9. Why can a slow-to-update replica cause data to come back to life?

Cassandra distributes data by partition key and replication strategy. With a replication factor of `3`, suppose three replicas are responsible for a partition.

```text
T0: All of A, B, C have payload = "A" (timestamp 100).

T1: C temporarily loses connectivity.
    DELETE payload (timestamp 200) reaches A and B.
    A, B hold the tombstone; C still holds "A".

T2: Client reads with appropriate consistency and reconciles:
    the new tombstone can shadow the old value "A".

T3: During the safety window:
    Repair/synchronization helps C receive the tombstone before it is
    reclaimed from every place that could be used for reconciliation.

T4: After safety conditions are met:
    Compaction can clean up the tombstone/old data.
```

If C fails to receive the deletion for too long and the other replicas **have already reclaimed the tombstone before repairing the discrepancy**, the old value on C risks being treated as live data again. This scenario is commonly called **zombie data** (*resurrected data*).

Cassandra uses tombstone retention mechanisms, combined with repair and compaction conditions, to reduce that risk.

### What is `gc_grace_seconds`?

`gc_grace_seconds` is a table parameter related to the **safety window before a tombstone can be reclaimed**, usually expressed in seconds. This parameter is directly tied to replica operations and the repair schedule.

**Do not assume**:

- "After exactly `gc_grace_seconds`, every tombstone definitely disappears from disk."
- "Lowering `gc_grace_seconds` always makes reads faster without any risk."
- "Simply running manual compaction safely reclaims every DELETE."
- "`LOCAL_QUORUM` makes repair unnecessary in every situation."

Tombstones can only be removed when safe reclamation conditions are satisfied, depending on configuration, SSTable state, the grace period, and the reclamation strategy of the Cassandra version. Repair must be scheduled and operated consistently with this policy; you should not arbitrarily lower grace in a system where replicas may experience prolonged outages.

### Consistency level does not replace tombstones

Consistency level specifies how many replicas must participate in acknowledging/reading per the query policy. It affects visibility of the latest state at a point in time, but **does not automatically turn old data on every replica into physically deleted data**.

A delete operation can be acknowledged at a given consistency level while another replica is lagging; tombstones, repair, and compaction still play essential roles. To investigate a "deleted yet still visible" read result, examine **which replica states exist, write times, CL, timestamps, and repair schedule** instead of relying on a single test query.

## 10. When does physical reclamation happen?

Tombstones make data no longer live **logically**, while physical reclamation is a separate process. Cassandra uses compaction to inspect data across multiple SSTables and drop versions that are no longer needed when eligible.

```text
DELETE / NULL / TTL expiry
           |
           v
  Tombstone or expired cell
           |
           v
  Reads: do not return deleted value
           |
           +---> Other replicas may still hold old value
           |          |
           |          v
           |      needs safe reconciliation/repair
           |
           v
  Meets grace conditions and overlap/version checks
           |
           v
  Compaction can reclaim tombstone and deleted data
           |
           v
  Reduces physical footprint on SSTables
```

Reclamation conditions may depend on:

- **Tombstone age** relative to `gc_grace_seconds` and its corresponding policy.
- **SSTable overlap:** another SSTable may still contain an older version that the tombstone must shadow. Removing a tombstone too early while old data still exists can cause the record to reappear.
- **Repair and replica state:** the risk that a replica missed the delete.
- **Compaction strategy, TTL, and write pattern:** when data gets merged or an SSTable becomes eligible for cleanup.
- **Version/tombstone garbage collection differences:** inspect your actual deployment configuration rather than applying a fixed formula to every cluster.

Therefore, after a `DELETE` or TTL expiration, bytes on disk may **not drop immediately**, and may even temporarily increase because the new operation wrote an additional deletion marker. This is expected behavior in LSM storage, not proof that DELETE failed.

## 11. Operations prone to generating many unintended tombstones

### Deleting row-by-row inside a huge partition

For instance, an application executes one million `DELETE ... WHERE full_primary_key` statements to delete one million old events. This can create many row tombstones or cell tombstones, making reads over that slice and compaction resource-intensive.

If the requirement is truly to delete **an entire partition** and none of the data inside needs to be kept, a partition-level DELETE can differ significantly in mutation/tombstone count compared to row-by-row deletion. However, **do not delete an entire partition** if it still contains valid rows or static data that must be preserved.

### Updating many columns with NULL

An API that updates one field while accidentally sending `null` for all remaining fields can generate massive amounts of cell tombstones.

For example, a JSON request only sends `payload`, but the mapper also writes `event_kind = null`. This is not "leave `event_kind` unchanged"; it is a deletion of that column's value.

### Very short TTLs on high-throughput writes

If millions of cells expire after a few minutes, shortly after writing there can be massive amounts of expired data/tombstones for the read path and compaction to process.

TTL itself is not bad; the issue is **cell creation rate, expiration rate, query patterns, and how data is grouped into partitions**. For time-series data, time bucketing and an appropriate compaction strategy may be needed instead of packing the entire history into one partition.

### Large collections with frequent element modifications/deletions

For non-`frozen` collections, deleting elements or replacing the collection can create element-level/collection-level tombstones. A row containing a collection that continuously grows or gets replaced repeatedly incurs very different costs than a few small scalar columns.

Example using a test table:

```sql
CREATE TABLE session_attributes_by_id (
    session_id uuid PRIMARY KEY,
    attributes map<text, text>
);

INSERT INTO session_attributes_by_id (session_id, attributes)
VALUES (
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    {'theme': 'dark', 'locale': 'vi'}
);

DELETE attributes['locale']
FROM session_attributes_by_id
WHERE session_id = 327a71e9-f562-4b54-94b9-2138a9e30b12;
```

Deleting a map element can create a tombstone for that corresponding element. For workloads that continuously update collections, evaluate modeling each attribute as a separate row or keeping collections small, depending on the read path.

## 12. How do tombstones affect reads/writes and operations?

### Read path

A `SELECT` with `LIMIT 20` does not guarantee a replica only inspects 20 cells. If many rows near the start of the clustering range have been deleted or expired by TTL, Cassandra may have to scan through **a large number of tombstones** just to find 20 live rows.

```text
Query 20 latest events

[expired][deleted][deleted][expired][deleted]...[live #1]
[expired][deleted][expired]...[live #2]
... many other markers ...
[live #20]

Result: 20 rows
Read work: may have to process far more than 20 data positions
```

Common symptoms:

- Rising p95/p99 latency even when the number of returned rows is low.
- Read timeouts or tombstone-related warnings in logs/tracing.
- Reads over a time range with lots of TTL-expired data are slower than other ranges.
- Increased CPU/I/O when merging many SSTables and comparing tombstones.

### Write path

Writing a tombstone is typically a normal mutation in the LSM engine, **without requiring an immediate scan of every SSTable to erase old data**. That allows writes to remain fast, while the cost of tombstones shows up **later** during reads or compaction.

Do not think of tombstones as the reason every DELETE is slow at write time; observe mutation throughput, replica load, and background work as well.

### Compaction, repair, and streaming

Tombstones must remain long enough to preserve deletion semantics across SSTables/replicas. When present in large numbers, compaction work and data management across replicas can consume I/O, CPU, time, and disk headroom.

When handling deleted data in a replicated system, repair procedures and tombstone retention policies must align. Do not try to "clean up" by lowering grace or triggering aggressive compactions without verifying safety conditions first.

## 13. Observing tombstones with tools and CQL

### `nodetool tablestats`

Example with keyspace `app_ks`:

```bash
nodetool tablestats app_ks.sensor_events_by_day
```

Depending on the version, the output may include fields describing **average live cells per slice**, **average tombstones per slice**, read latency, SSTable count, and other table details. These metrics are useful for seeing whether queries on the table are encountering many tombstones.

Limitation: these are statistics at the **table/node level and observation window**, not a complete list of tombstones for every partition key.

### `nodetool tablehistograms`

```bash
nodetool tablehistograms app_ks sensor_events_by_day
```

Histograms can show distributions of partition size, cell count, read latency, and other version-supported statistics. Combine this with tablestats, application metrics, and logs to avoid confusing **large partitions** with **tombstone-heavy** ones.

### Tracing a suspect query

In `cqlsh`, you can enable tracing for a bounded read query:

```sql
TRACING ON;

SELECT occurred_at, event_id, event_kind
FROM sensor_events_by_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
LIMIT 20;

TRACING OFF;
```

Traces can help inspect query processing steps and the amount of data/tombstones scanned when the version provides the relevant details. Tracing has overhead; do not leave it enabled continuously for all production requests.

### Warning/failure thresholds

Some Cassandra versions provide warning or failure threshold parameters when a read query encounters too many tombstones; commonly referenced configuration names are `tombstone_warn_threshold` and `tombstone_failure_threshold` in applicable versions.

**Specific values/formats depend on version and configuration.** Do not copy a "standard threshold" from another environment and treat it as an absolute safety rule. If you receive warnings, examine query patterns, deletions/TTL expirations, partitioning, SSTable overlap, and compaction status before deciding to adjust thresholds.

### `COUNT(*)` does not measure tombstone count

```sql
SELECT COUNT(*)
FROM sensor_events_by_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21';
```

The result is the number of rows observed by the query under read semantics, **not** the number of tombstones existing on disk. Counting over a large partition can also create significant load. Therefore, do not use `COUNT(*)` as a periodic tombstone-measurement tool.

## 14. Java Driver: distinguishing column deletion and TTL writes

A Java Driver 4.x example using explicit `PreparedStatement`s for two purposes:

- `DELETE payload`: intentionally deletes the value of an event.
- `INSERT ... USING TTL ?`: writes an event that only lives for the specified number of seconds.

Assuming `CqlSession` is already connected to the keyspace containing `sensor_events_by_day`.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class SensorEventRepository {
    private final CqlSession session;
    private final PreparedStatement deletePayload;
    private final PreparedStatement insertWithTtl;

    public SensorEventRepository(CqlSession session) {
        this.session = session;

        this.deletePayload = session.prepare(
            "DELETE payload FROM sensor_events_by_day " +
            "WHERE tenant_id = ? AND sensor_id = ? AND event_day = ? " +
            "AND occurred_at = ? AND event_id = ?"
        );

        this.insertWithTtl = session.prepare(
            "INSERT INTO sensor_events_by_day " +
            "(tenant_id, sensor_id, event_day, occurred_at, event_id, " +
            "event_kind, payload) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?) USING TTL ?"
        );
    }

    public void removePayload(
            String tenantId, UUID sensorId, LocalDate eventDay,
            Instant occurredAt, UUID eventId) {

        session.execute(deletePayload.bind(
            tenantId, sensorId, eventDay, occurredAt, eventId
        ));
    }

    public void insertExpiringEvent(
            String tenantId, UUID sensorId, LocalDate eventDay,
            Instant occurredAt, UUID eventId,
            String eventKind, String payload, int ttlSeconds) {

        if (ttlSeconds <= 0) {
            throw new IllegalArgumentException("TTL must be positive");
        }

        session.execute(insertWithTtl.bind(
            tenantId, sensorId, eventDay, occurredAt, eventId,
            eventKind, payload, ttlSeconds
        ));
    }
}
```

The code intentionally uses `DELETE payload` instead of binding `null` to clearly express the business intent. If the code needs to distinguish between "do not update payload" and "delete payload," design an API or DTO with an **absent state** separate from `null`, rather than letting a mapping framework decide implicitly.

Operational points:

1. Java binds the **full partition key and clustering key** for column deletion.
2. TTL is passed in **seconds**; there must be a clear retention policy. TTL is not based on `occurredAt` unless the application computes it from event time.
3. Keep `eventId` and `occurredAt` stable across retries to avoid creating new rows.
4. A timeout on `DELETE` or `INSERT` does not prove the mutation was not applied; the application must have appropriate retry/backoff and consistency policies.
5. If using a mapper/driver with `UNSET` bind variables, check the semantics of your specific version; **`NULL` and `UNSET` are not equivalent**.
6. Rewriting the same event with a new TTL on retry can **change the expiration time** depending on the mutation and timestamp; row identity idempotency does not automatically mean "TTL is applied exactly once."
7. A `DELETE` statement in Cassandra does not immediately remove data from disk across every replica; it must be coordinated with compaction/repair operations.

## 15. Designing to minimize unnecessary tombstones

The most effective approach is usually **reducing write patterns that generate tombstones in bulk**, rather than just raising warning thresholds.

### 15.1. Choose partition keys and time buckets aligned with lifecycle

Time-series data is often queried by device, customer, and time range. Using a partition key with a day/hour bucket helps limit the amount of data and tombstones a bucket-scoped query must inspect.

For example, the current table uses `(tenant_id, sensor_id, event_day)` so reading `2026-11-21` avoids scanning the sensor's entire history. If events are written extremely densely within a single day, hourly buckets or sharding can be considered after measuring load and fan-out.

**Bucketing does not delete tombstones by itself.** It groups data by time and narrows query scope; TTL/compaction and the mutation pattern still govern the lifecycle.

### 15.2. Avoid row-by-row deletes when the retention model can be changed

If the policy is simply to retain data for a fixed duration, you can evaluate uniform TTLs, time bucketing, and an appropriate compaction strategy. Some append-mostly time-series workloads with nearly uniform TTLs may be suitable for evaluating **TimeWindowCompactionStrategy (TWCS)**, because SSTables can hold data with similar lifecycles.

However:

- TWCS does not change the partition key and **does not guarantee** tombstones are cleaned up the moment TTL expires.
- Writing late-arriving events, updating old data, or having widely varying TTLs can make reclamation harder.
- Do not delete an entire partition just because it "looks old" if it still holds live data or different retention rules apply.
- Do not arbitrarily lower `gc_grace_seconds` to make physical data disappear sooner.

### 15.3. Write only values that actually changed

For a PATCH API, distinguish:

- **Absent field**: do not modify the cell.
- **Field containing a value**: update the cell.
- **Field requested to be deleted**: issue `DELETE col` or intentionally use `null`.

This avoids generating tombstones from serializing an entire DTO with dozens of unrelated `null` properties.

### 15.4. Control collections and payloads

Keep collections at an appropriate size; if a map/set/list is continuously updated or has elements deleted frequently, consider switching to multiple rows with an explicit primary key. Do not store huge payloads in a single cell if the access path and storage requirements fit an object-storage reference model.

### 15.5. Load test with TTL, deletes, and replica failures

A benchmark consisting only of `INSERT` and `SELECT` on fresh data does not reflect tombstone costs. You should test:

- `DELETE` rates at cell/row/partition levels.
- TTL expiration rates and data age distributions.
- Clustering range width and the number of live rows to return.
- p95/p99 behavior during compaction, repair, or when a replica is disrupted.
- Recovery behavior after a replica has been offline, especially regarding tombstone grace.

The goal is to prevent **latency spikes and the risk of losing deletion semantics**, not merely getting the reported tombstone count low in a single measurement.

## 16. Checklist for troubleshooting a tombstone-slow query

| Check question | Why is it needed? |
| --- | --- |
| Does the query specify the **full partition key**? | Avoids reading across unintended partitions. |
| Is the clustering range too wide? | Reading a broad slice can hit a lot of deleted data. |
| How many live rows are returned, and how many tombstones are scanned? | `LIMIT` does not reflect actual scan cost. |
| Are tombstones coming from `DELETE`, `NULL` writes, or TTL? | Each source has a different remediation path. |
| Is a map/list/set being modified/deleted continuously? | Collections can generate many internal tombstones. |
| Is there SSTable overlap or a compaction backlog? | Affects cleanup/merging of old data. |
| Did a replica miss deletes, is repair lagging, or is grace misconfigured? | Relates to zombie data risk. |
| Should partitions be re-bucketed or the read path redesigned? | Reduces the amount of data the query must process. |
| Do metrics/logs/tracing support the conclusion? | Do not change configurations based on guesswork alone. |

A reasonable troubleshooting workflow:

1. Pick **a representative slow query** and identify the exact partition key/clustering slice.
2. Check read latency, tombstones per slice, SSTables per read, and related warnings.
3. Cross-reference the source of deletions/expirations against application history and retention policies.
4. Verify compaction, repair, and replica health before intervening.
5. Test query/partitioning/TTL changes on a reproducible workload.
6. Monitor after changes: p95/p99, timeouts, tombstone scans, CPU/I/O, and data correctness.

**Do not** resolve this by raising `tombstone_failure_threshold` or lowering `gc_grace_seconds` without addressing the root cause, as that can mask performance issues or compromise deletion safety.

## 17. Case study exercise

A system stores device accesses with the schema:

```sql
CREATE TABLE accesses_by_device_day (
    device_id  uuid,
    event_day  date,
    seen_at    timestamp,
    access_id  uuid,
    ip         text,
    user_agent text,
    PRIMARY KEY ((device_id, event_day), seen_at, access_id)
);
```

The application writes 100,000 rows/day for one device. A day later, it:

- Deletes `user_agent` for 30,000 rows due to privacy requirements.
- Writes `ip = null` to another 10,000 rows.
- Writes some new rows with `USING TTL 86400`.
- Reads `LIMIT 20` to fetch the 20 most recent rows.

**Questions:**

1. Does deleting `user_agent` on 30,000 rows create tombstones? At what scope?
2. How does writing `ip = null` differ from omitting `ip` from the `UPDATE` statement?
3. After 86,400 seconds, do the cells written with TTL require a separate job to send `DELETE`?
4. Why might `SELECT LIMIT 20` still scan many tombstones?
5. If only `ip` remains live on a row, does deleting `user_agent` make the whole row disappear?
6. How does deleting the entire day's partition differ from deleting `user_agent` on some rows?
7. If a replica is offline at the time of deletion and stays offline for a very long time, what should you worry about?
8. Why can setting `gc_grace_seconds` too low introduce risk?
9. Does `TTL(user_agent)` after the value has been deleted provide a list of tombstones on SSTables?
10. To reduce tombstone overhead, what two changes in API design or data lifecycle are worth considering?

**Answers and explanations:**

1. **It can create many cell tombstones** for `user_agent` at the specified full primary keys, according to cell deletion semantics.
2. `ip = null` carries the meaning of **deleting the value**; omitting the column from UPDATE means **not requesting an update to that cell**.
3. **No.** The TTL is stored alongside the value; upon expiration, Cassandra treats the value like a tombstone without needing a new DELETE request at that exact time.
4. Because within the latest clustering slice there may be many deleted or expired cells/rows that must be processed to find enough valid rows.
5. **No**, as long as another live cell or appropriate liveness info remains; deleting one regular column is not equivalent to a row deletion.
6. Partition deletion shadows **all clustering rows and static data** of that partition; column deletion only affects the named cell in the corresponding rows.
7. The replica may still hold old values, leading to **zombie data risk** if tombstones are reclaimed before the deleted state is safely synchronized.
8. Because the protection window against a replica missing deletions is shortened, while repair/compaction may not have synchronized sufficiently.
9. **No.** The TTL function on a CQL value is not a tool to scan physical tombstones or prove why a cell is no longer live.
10. For example: **avoid sending NULL for un-updated fields**, and **design retention with appropriate TTL/bucketing/compaction** instead of mass cell-by-cell deletions when unnecessary.

### CQL hands-on exercise

Create a test table `accesses_by_device_day`, write two rows, and then observe the difference between:

```sql
-- Delete just one column:
DELETE user_agent
FROM accesses_by_device_day
WHERE device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND seen_at = '2026-11-21T10:00:00Z'
  AND access_id = 8817a208-1858-4144-86e9-b24d9083e478;

-- Delete an entire clustering row:
DELETE FROM accesses_by_device_day
WHERE device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND seen_at = '2026-11-21T10:00:00Z'
  AND access_id = 8817a208-1858-4144-86e9-b24d9083e478;
```

Read back the columns with the full partition key, distinguishing **a live row with an empty column** from **a deleted row**. Then test a short TTL on a lab table and observe the expired values. Still seeing SSTable space or tombstone-related warnings after TTL expiration **does not prove the data is still live**.

## 18. Key takeaways

- **`DELETE`** writes a deletion marker to shadow old data; its scope can be a cell, static column, row, clustering range, or partition.
- **Writing `NULL` to a column** is a value deletion operation under CQL semantics. **Omitting the column** or binding **UNSET** differs from NULL.
- **TTL expiration** makes a cell no longer live and treats it like a tombstone; **no new DELETE mutation** needs to be issued at the exact moment of expiration.
- Tombstones carry a **write timestamp** to win over older versions of data and prevent unsynchronized data from reappearing.
- **Logical deletion** happens first; **physical reclamation** depends on compaction, grace, SSTable overlap, and replica/repair safety.
- Arbitrarily lowering `gc_grace_seconds` or skipping repair can create **zombie data** risks.
- Tombstones increase read costs when queries must scan through large amounts of deleted data; `LIMIT` and paging do not solve the root cause.
- Minimize tombstones through partition key/bucket design, appropriate TTLs, avoiding unintended NULL writes, and controlling collections/updates/deletes.
- Evaluate real behavior using `nodetool`, metrics, tracing, warning logs, and benchmarks that include TTL/deletes rather than looking solely at live row counts.
- In Java applications, clearly separate the intent to **keep a column unchanged**, **delete a column**, and **write a value with TTL**, while keeping the full primary key stable on retries.

Understanding deletion markers helps you explain seemingly contradictory situations in Apache Cassandra: data has been deleted yet SSTables have not shrunk, a query returns few rows yet is still slow, or an old replica can cause data to reappear when grace/repair is mismanaged. This is the foundation for diving deeper into tombstone reclamation, compaction, replication, and troubleshooting in distributed Cassandra systems.
