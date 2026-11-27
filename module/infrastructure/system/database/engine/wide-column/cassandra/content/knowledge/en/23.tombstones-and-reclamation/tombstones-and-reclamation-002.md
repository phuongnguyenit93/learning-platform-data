# Tombstones at Cell, Collection, Row, Range, or Partition Level

In Apache Cassandra, a delete operation can affect **a column value**, **a collection element**, **a clustering row**, **a range of rows**, or **an entire partition**. Each scope has a different deletion marker (*tombstone*) representation and different consequences for reads, compaction, and repair. Understanding **tombstone scope** properly helps avoid two common misconceptions: thinking `DELETE` always deletes physically right away, or assuming every delete operation creates an individual marker for every row.

Cassandra is a **distributed wide-column** database that uses partition keys to distribute data to replicas, clustering columns to organize rows within a partition, and an LSM storage engine with memtables, SSTables, and compaction. When an old value still exists on an SSTable or on a replica that has not yet received the delete, a tombstone with a **write timestamp** helps the system recognize that the old version must be shadowed. **Physical reclamation** only happens when safety conditions are met during compaction.

This lesson belongs to the **Tombstones and Reclamation** chapter of the Apache Cassandra module. The content progresses from CQL to deletion representations and scopes, then connects to replication, consistency, compaction, repair, partition key design, and Java applications.

After this lesson, you will be able to:

1. Distinguish between a **cell tombstone**, **collection element tombstone**, **complex/collection deletion**, **row tombstone**, **range tombstone**, and **partition tombstone**.
2. Explain the difference between a **non-frozen collection** and a **frozen collection** when updating or deleting.
3. Predict which values a `DELETE` statement affects based on the **partition key**, **clustering columns**, and **static columns**.
4. Understand the relationship between `NULL`, `UNSET`, TTL, write timestamps, and deletion markers.
5. Explain why range/partition deletion does not mean generating millions of individual delete commands or freeing space immediately.
6. Observe signs of tombstone-heavy queries, choose the right deletion scope, and test via CQL/Java Driver 4.x.

## 1. Tombstones belong to a logical scope

A Cassandra partition can hold regular data (*regular columns*), static data (*static columns*), multiple clustering rows, and multi-element collections.

```text
Partition key = (tenant='acme', sensor=S1, day=2026-11-21)
│
├── static note = "Morning shift"
│
├── clustering key (08:00, E1)
│     ├── status = "ok"
│     ├── payload = "temperature=38.1"
│     └── metadata = {"unit":"C", "source":"edge"}
│
├── clustering key (08:05, E2)
│     ├── status = "ok"
│     └── payload = "temperature=38.4"
│
└── clustering key (08:10, E3)
      └── payload = "temperature=38.7"
```

You may want to perform six different operations:

- Delete **only `payload`** of E1.
- Delete **only element `metadata['source']`** of E1.
- Delete **the entire collection `metadata`** of E1.
- Delete **row E1** while keeping E2, E3, and `note`.
- Delete **all rows in a time range**.
- Delete **the entire daily partition**, including static data.

These requirements differ in **mutation scope**. Cassandra can represent them using corresponding tombstone types, rather than always scanning and erasing every byte stored across SSTables.

| Scope | Data unit shadowed | Common representation |
| --- | --- | --- |
| One scalar value | One cell in one row | Cell tombstone |
| One element of a non-`frozen` collection | Element with the corresponding key/index | Element/cell tombstone |
| Entire non-`frozen` collection | Old elements of the collection | Complex/collection deletion |
| One `frozen` collection | A single cell value | Cell tombstone |
| One clustering row | Data and liveness of the row | Row deletion/tombstone |
| One clustering slice | Rows within the specified range | Range tombstone |
| Entire partition | Clustering rows and static data in the partition | Partition deletion/tombstone |

The names of tombstone types reflect the **storage model**, not standalone CQL statements with identical names. Encoding details may vary across SSTable formats and Cassandra versions.

## 2. A practice table to distinguish deletion types

We use a table with regular columns, a static column, a non-frozen map, and a frozen map:

```sql
CREATE TABLE observations_by_sensor_day (
    tenant_id       text,
    sensor_id       uuid,
    event_day       date,
    observed_at     timestamp,
    observation_id  uuid,
    status          text,
    payload         text,
    attributes      map<text, text>,
    frozen_attrs    frozen<map<text, text>>,
    day_note        text STATIC,
    PRIMARY KEY (
        (tenant_id, sensor_id, event_day),
        observed_at,
        observation_id
    )
) WITH CLUSTERING ORDER BY (
    observed_at DESC,
    observation_id ASC
);
```

Structure explanation:

| Column | Role |
| --- | --- |
| `(tenant_id, sensor_id, event_day)` | **Composite partition key**, identifies the partition. |
| `observed_at`, `observation_id` | **Clustering columns**, identify a row within the partition. |
| `status`, `payload` | Regular scalar columns. |
| `attributes` | **Non-frozen** map, supports element-level operations. |
| `frozen_attrs` | **Frozen** map, treated as a single monolithic value. |
| `day_note` | Static column, one shared value for the partition. |

Example initializing three events in the same partition:

```sql
INSERT INTO observations_by_sensor_day (
    tenant_id, sensor_id, event_day,
    observed_at, observation_id,
    status, payload, attributes, frozen_attrs
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T08:00:00Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    'ok',
    'temperature=38.1',
    {'unit':'C', 'source':'edge'},
    {'location':'room-A'}
);

INSERT INTO observations_by_sensor_day (
    tenant_id, sensor_id, event_day,
    observed_at, observation_id, status, payload
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T08:05:00Z',
    7c2c4f75-5c44-4be4-99a0-08688b465200,
    'ok',
    'temperature=38.4'
);

INSERT INTO observations_by_sensor_day (
    tenant_id, sensor_id, event_day,
    observed_at, observation_id, status, payload
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T08:10:00Z',
    4e52e99a-178e-4d5b-9a31-027d5956e5b8,
    'ok',
    'temperature=38.7'
);
```

Writing static data by partition key:

```sql
UPDATE observations_by_sensor_day
SET day_note = 'Morning shift'
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21';
```

**Practice note:** the following DELETE examples use the same partition to make the differences clear. If you want to compare results independently, **reinitialize the sample data or use separate test partition keys** before each experiment; do not run all DELETEs sequentially and expect to observe the initial state.

## 3. Cell tombstone: deleting a single column value

A cell tombstone is used to shadow the old value of a regular column. For example, deleting `payload` of event E1 while keeping `status` and `attributes`:

```sql
DELETE payload
FROM observations_by_sensor_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND observed_at = '2026-11-21T08:00:00Z'
  AND observation_id = 8817a208-1858-4144-86e9-b24d9083e478;
```

Verification query:

```sql
SELECT observed_at, observation_id, status, payload, attributes
FROM observations_by_sensor_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND observed_at = '2026-11-21T08:00:00Z'
  AND observation_id = 8817a208-1858-4144-86e9-b24d9083e478;
```

Once the deletion is observed at an appropriate consistency level, `payload` no longer has a current value, while `status` can still be `'ok'` and `attributes` still remains. **Cell deletion is not equivalent to row deletion.**

### Deleting a column with no existing value

Cassandra does not need to check beforehand whether a cell exists before accepting a delete mutation. Deleting a cell that has no current value can still write a tombstone to shadow an older version that might arrive late from another SSTable or replica.

This explains why an application sending thousands of DELETEs "just to make sure the column is empty" can create deletion markers even though the number of live rows barely changes.

### `NULL` also carries cell-deletion semantics

```sql
UPDATE observations_by_sensor_day
SET payload = null
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND observed_at = '2026-11-21T08:00:00Z'
  AND observation_id = 8817a208-1858-4144-86e9-b24d9083e478;
```

`payload = null` is a request to delete the column's value, not "skip this column." Distinguish:

- **Omitted column** in an INSERT/UPDATE statement: does not create a tombstone just from its absence.
- **Binding `UNSET`** for a CQL variable that supports unset: performs no mutation for that column.
- **Writing `NULL`**: carries deletion semantics for the column value, typically creating a cell tombstone.
- **Writing an empty string `''`** to a text column: stores an empty value, not NULL.

A `SELECT` returning `null` only shows that the application sees no live value; **it does not prove** whether the cell never existed, was DELETEd, received NULL, or had its TTL expire.

## 4. Static-cell tombstone: deleting partition-wide data

The `day_note text STATIC` column belongs to the **partition** level, not to a single clustering row. When selecting multiple rows, the static value may repeat across result rows, but that does not turn it into multiple independent cells.

Deleting a static column only requires the **full partition key**:

```sql
DELETE day_note
FROM observations_by_sensor_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21';
```

This statement affects the shared `day_note`, **without deleting rows E1, E2, E3**. It differs from:

```sql
DELETE FROM observations_by_sensor_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21';
```

The second statement deletes **the entire partition**, including static data. If you only want to remove a day's note, do not use a partition deletion statement.

### Note on static-only partitions

Cassandra can store static data for a partition that **has no live clustering rows**. When designing data checks, do not equate "no clustering rows" with "the partition has no static data." Conversely, after a partition-level DELETE, old static cells are also shadowed by the partition tombstone.

## 5. Element tombstone: deleting an element of a non-frozen collection

CQL collections such as `map`, `set`, and `list` can be declared **non-frozen** to support element-level updates. In storage, they are typically represented as a set of cells/element paths rather than a single blob.

With `attributes map<text, text>`:

```text
attributes:
  "unit"   -> "C"
  "source" -> "edge"
```

Deleting only the key `'source'`:

```sql
DELETE attributes['source']
FROM observations_by_sensor_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND observed_at = '2026-11-21T08:00:00Z'
  AND observation_id = 8817a208-1858-4144-86e9-b24d9083e478;
```

Logical consequence:

```text
Before:
  attributes = {'unit':'C', 'source':'edge'}

After:
  attributes = {'unit':'C'}
```

The statement above does not request deleting the whole map, does not delete `payload` or `status`, and does not delete row E1.

At the storage level, a corresponding **collection element tombstone** can be created. A map with many elements being continuously added/deleted can accumulate many different cells and tombstones before being compacted.

### Updating one element vs. replacing the collection

An element-scoped update:

```sql
UPDATE observations_by_sensor_day
SET attributes['unit'] = 'F'
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND observed_at = '2026-11-21T08:00:00Z'
  AND observation_id = 8817a208-1858-4144-86e9-b24d9083e478;
```

This operation differs from assigning the entire map:

```sql
UPDATE observations_by_sensor_day
SET attributes = {'unit':'F'}
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND observed_at = '2026-11-21T08:00:00Z'
  AND observation_id = 8817a208-1858-4144-86e9-b24d9083e478;
```

Reassigning **an entire non-frozen map** requires replacement semantics: old elements not in the new set must not be retained just because they existed previously. Cassandra can write a **complex deletion** marker for the old collection along with the new elements. Therefore, repeatedly replacing a large collection can generate significant tombstone overhead.

Do not assume "one UPDATE statement = one newly written cell" when operating on multi-element collections.

## 6. Complex deletion: deleting an entire non-frozen collection

If the business requirement is to delete **the entire `attributes` map**, you can write:

```sql
DELETE attributes
FROM observations_by_sensor_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND observed_at = '2026-11-21T08:00:00Z'
  AND observation_id = 8817a208-1858-4144-86e9-b24d9083e478;
```

Logically, all elements of this map no longer have current values, while other columns such as `payload` or `status` are not automatically deleted.

For a **non-frozen collection**, Cassandra can represent deleting the whole collection via a **complex deletion** marker to shadow old elements, without necessarily issuing a separate CQL DELETE per element.

```text
Row E1
│
├── status                -> still remains
├── payload               -> still remains
└── attributes            -> complex deletion
      ├── "unit"   (old version shadowed)
      └── "source" (old version shadowed)
```

### When do complex deletions typically occur?

- `DELETE attributes` on a non-frozen collection.
- Assigning/overwriting an **entire** non-frozen map, set, or list with replacement semantics.
- Collection operations where the implementation needs to shadow old element versions to establish the new collection value.

**Narrower scope than row deletion:** deleting the entire collection still does not mean deleting the row. However, if this collection is very large, the number of elements and tombstones to inspect during reads or compaction can still be substantial.

### Do not treat all collection types identically

Non-frozen maps, sets, and lists differ in how elements are identified and how updates are supported. In particular, lists have positional/value operations and a more complex storage structure than key-based maps. When you need to modify/delete thousands of independent elements, **consider modeling each element as a CQL row**, instead of letting a collection grow unbounded inside a single row.

## 7. Frozen collection: a monolithic value, no individual element deletion

The example table has:

```sql
frozen_attrs frozen<map<text, text>>
```

With `frozen<map<...>>`, Cassandra treats the map as **a single CQL value** on write/delete. It does not support updating or deleting an inner element the way a non-frozen map does.

Example deleting a frozen map:

```sql
DELETE frozen_attrs
FROM observations_by_sensor_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND observed_at = '2026-11-21T08:00:00Z'
  AND observation_id = 8817a208-1858-4144-86e9-b24d9083e478;
```

This operation carries the semantics of deleting **one cell containing a frozen value**. To change the contents of a frozen map, the application must compute and rewrite **the entire new map**.

Comparison:

| Scenario | Non-frozen map | Frozen map |
| --- | --- | --- |
| Delete `'source'` | Can operate on element `map['source']` | No individual element deletion via equivalent syntax. |
| Replace entire map | May emit complex deletion + new elements | Rewrites a single monolithic cell value. |
| Delete entire map | Complex/collection deletion | Cell tombstone. |
| Internal cell count | Can grow with the number of elements | Stored as a single cell in terms of CQL value. |
| Recommendation | Small collections needing per-element edits | Small values, rarely changed, handled as a whole. |

This distinction matters when evaluating **tombstone count**: two schemas that present the exact same JSON/map in an API can produce very different tombstone shapes and storage costs.

## 8. Row tombstone: deleting one clustering row

A CQL row is identified by its **full primary key**, consisting of the partition key and all clustering columns.

To delete only E1:

```sql
DELETE FROM observations_by_sensor_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND observed_at = '2026-11-21T08:00:00Z'
  AND observation_id = 8817a208-1858-4144-86e9-b24d9083e478;
```

This statement lists no columns after `DELETE`. It means **deleting the clustering row** at `(08:00, E1)`, including the regular scalar and collection values in that row.

```text
Partition (acme, S1, 2026-11-21)
│
├── static day_note = "Morning shift"   -> not deleted
├── (08:00, E1)                         -> row tombstone
├── (08:05, E2)                         -> still remains
└── (08:10, E3)                         -> still remains
```

Cassandra can represent the deletion at the **row deletion** level, rather than listing every cell to delete. The row deletion marker shadows old cells belonging to that row, while static cells of the partition and other clustering rows are unaffected.

### Why is deleting a row different from deleting all regular columns?

Suppose a row has `status`, `payload`, and `attributes`. Deleting each column one by one with multiple `DELETE column` statements can create multiple cell/complex deletions. `DELETE FROM ... WHERE full_primary_key` expresses more clearly that **the entire row** is no longer a current record.

However, do not issue a row deletion if the business requirement is only to hide `payload` while keeping `status` or the remaining values. The deletion scope must match the business requirement precisely.

### Primary keys are not "set to NULL"

Row deletion is not updating `observed_at = null` or `observation_id = null`. The primary key is the **coordinate of the row**; a row tombstone records that data at that coordinate was deleted at a write timestamp.

A new write to the **same full primary key** with a timestamp newer than the deletion marker can bring live data back. DELETE does not automatically place a permanent ban on that key.

## 9. Range tombstone: deleting a range of clustering rows

If the requirement is to delete all events from 08:00 up to before 09:00 for **a daily partition**, issuing a DELETE for each observation ID can generate a huge number of individual mutations. When CQL/the version permits the corresponding range delete predicate, Cassandra can use a **range tombstone** to represent the deleted clustering slice.

Conceptual example with the first clustering column `observed_at`:

```sql
DELETE FROM observations_by_sensor_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND observed_at >= '2026-11-21T08:00:00Z'
  AND observed_at <  '2026-11-21T09:00:00Z';
```

In Cassandra versions/contexts that support this form of range deletion, the statement specifies **one complete partition key** and a **clustering range**. Verify DELETE syntax restrictions and clustering-prefix rules on the exact Cassandra version you are using.

```text
Partition (acme, S1, 2026-11-21)
│
├── (07:50, Ex)       outside range -> kept
├── [08:00, ...       delete range start
├── (08:05, E2)       in range -> shadowed
├── (08:10, E3)       in range -> shadowed
├── ... , 09:00)      delete range end
└── (09:05, Ey)       outside range -> kept
```

**A range tombstone does not necessarily create a separate tombstone for every row in the range**. It describes a slice of data to be shadowed at the deletion timestamp. However, when reading a slice that intersects the deleted range or during compaction, Cassandra still has to process the markers and related data.

### Scope limits of range deletion

- It applies **within the specified partition key**, and does not automatically delete other daily partitions.
- Range conditions must follow the **clustering-prefix order** supported by CQL.
- `CLUSTERING ORDER BY DESC` changes traversal order within the partition, but does not turn a time condition `[08:00,09:00)` into a condition across multiple partitions.
- Deleting by range and deleting row-by-row can yield the same logical state for a set of rows, but tombstone representation and write/compaction costs can differ.

### When not to delete by range

If the time range contains both data to keep and data to delete based on a business condition that does not align with the clustering range, a range tombstone will delete **too broadly**. For example, a requirement to "only delete events with `status='failed'` during hour 08" cannot arbitrarily use an hourly DELETE and expect only failed rows to be removed.

Cassandra designs tables around queries; if you need selective deletion by event type, you must know the exact full keys or have a corresponding access path/separate table.

## 10. Partition tombstone: deleting an entire partition and static data

A partition key can contain thousands of clustering rows and static columns. If the requirement is to delete **all data in the daily partition**, the statement is:

```sql
DELETE FROM observations_by_sensor_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21';
```

With no clustering predicates or column list: this is a **partition deletion**.

```text
Partition (acme, S1, 2026-11-21)
│
├── static day_note     -> shadowed
├── (08:00, E1)         -> shadowed
├── (08:05, E2)         -> shadowed
└── (08:10, E3)         -> shadowed

Partition-level deletion marker shadows old versions
belonging to that partition according to write timestamp.
```

A partition-level deletion marker can represent the entire scope without **reading every clustering row beforehand**. This is an advantage in the number of mutations issued compared to row-by-row deletion in a very large partition.

However, it is **not** an operation that "erases every SSTable the moment the command is received." Old versions in SSTables can still exist until compaction safely reclaims them. Queries/repair/streaming must handle the corresponding deletion state during the transition period.

### Distinguishing partition deletion from `TRUNCATE`

`TRUNCATE` is an administrative operation at **table scope**, not partition deletion. Do not use `TRUNCATE` to "delete data for one tenant/day": it affects data across the entire table and has its own operational/recovery implications.

Conversely, a partition-level `DELETE` targets only **one complete partition key value**, without deleting other partitions.

### Deleting a partition with no live data left

Even when SELECT no longer sees live rows in a partition, Cassandra may still need to write a deletion marker to preserve semantics against older versions. Do not spam repeated DELETEs hoping to save disk space; new mutations/timestamps can make data cleanup less predictable.

## 11. Comparison table of deletion scopes, remaining data, and costs

| Business requirement | Operation form | Remaining data | What to watch out for |
| --- | --- | --- | --- |
| Delete E1's payload | `DELETE payload` with full primary key | Other columns, other rows, static data | Cell tombstone; NULL also carries deletion semantics. |
| Delete key `'source'` from E1's map | `DELETE attributes['source']` | Other elements and other columns | Element tombstone in non-frozen map. |
| Delete E1's entire map | `DELETE attributes` | Remaining regular columns | Complex deletion of non-frozen collection. |
| Delete E1's frozen map | `DELETE frozen_attrs` | Other columns | Frozen map as a single cell. |
| Delete shared note | `DELETE day_note` with partition key | Clustering rows remain live | Static-cell tombstone. |
| Delete E1 | `DELETE FROM` with full primary key | E2/E3 and static note | Row tombstone. |
| Delete events 08:00–09:00 | `DELETE FROM` with partition key + clustering range | Rows outside the range, static note | Range tombstone if syntax is supported. |
| Delete sensor's day | `DELETE FROM` with partition key | Other daily partitions | Partition tombstone; static data is also shadowed. |

You cannot deduce the exact number of physical tombstones just by counting CQL statements executed. A collection operation can involve multiple cells, a range tombstone can shadow many rows, and the final state also depends on write timestamps, TTL, SSTables/compaction, and storage format.

## 12. Write timestamp: a tombstone is not merely a Boolean flag

Tombstones carry a write timestamp to reconcile against old data. In Cassandra, a live value and a tombstone can arrive at replicas in different orders and still be compared by timestamp during read/merge.

Illustrative example:

```text
Timestamp 100: status = "pending"
Timestamp 150: status = "processed"
Timestamp 200: DELETE status

=> Tombstone at 200 shadows old values at 100 and 150.

Timestamp 250: status = "reopened"
=> Value at 250 can become live again.
```

Similarly:

- **Cell tombstone** shadows old versions of a cell.
- **Complex deletion** shadows old elements of a collection within its scope.
- **Row tombstone** shadows old cells belonging to the row.
- **Range tombstone** shadows old rows/cells within the clustering slice.
- **Partition tombstone** shadows old rows and static data in the partition.

On equal timestamps, Cassandra also applies tie-breaking rules; therefore **do not intentionally generate identical write timestamps** for conflicting operations and rely on request order to deduce the final state.

### Two different time concepts

| Time | Purpose |
| --- | --- |
| **Write timestamp** (typically microsecond resolution) | Reconciles live data and tombstones, deciding which version wins. |
| **Local deletion time / deletion or expiration recorded time** | Participates in evaluating tombstone age and garbage collection eligibility. |

Do not confuse `observed_at` (the business event time, also a clustering column in the table) with the mutation's **write timestamp**. An old event written today can carry a new write timestamp, even though `observed_at` was yesterday.

### DELETE does not mean "never write to this key again"

If the application writes new data with a newer timestamp than the deletion marker to the same primary key, Cassandra can allow the data to reappear. If the business logic must forbid reusing an identifier, design an appropriate **ownership/claim mechanism or business state**, rather than relying on tombstones as a permanent blocklist.

## 13. How TTL expiration interacts with each data scope

TTL is a common source of tombstone states in time-series data. When a cell with a TTL expires, Cassandra treats that value as no longer live; **no client needs to send a new `DELETE`** at the exact second of expiration.

Example:

```sql
INSERT INTO observations_by_sensor_day (
    tenant_id, sensor_id, event_day,
    observed_at, observation_id, status, payload
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T09:00:00Z',
    142dd6ae-6706-4f2c-a5e8-61cdd9c22cad,
    'temporary',
    'expire-in-10-min'
) USING TTL 600;
```

After **600 seconds from write time under TTL semantics**, the values with TTL are no longer live. This does not mean the entire daily partition is deleted. Other rows, static data, or cells without TTL may still remain.

### TTL and non-frozen collections

A non-frozen collection consists of multiple elements/cells. Writes with TTL can apply a lifetime to the written cells/elements, while elements written at different times have different expiration times.

This can leave a map appearing to have few live elements while still holding a history of expired cells and tombstones on SSTables. You cannot look solely at the number of current keys in `SELECT attributes` to know the internal storage cost.

### TTL and frozen collections

A frozen map is a monolithic cell value; if that cell carries a TTL, **the entire frozen value** expires according to the cell's lifetime. It does not have independent expiration for individual inner elements like a non-frozen map written across multiple operations.

### TTL is not equivalent to a row tombstone or partition tombstone

When the TTL of some regular cells expires, that is an expiring-cell state. Cassandra also has the concept of a **row liveness marker** and metadata related to determining whether a row is alive; do not crudely infer that "payload's TTL expired so the whole row was DELETEd" or "every cell in the day expired by TTL so a partition deletion was generated."

You must inspect all live data in the row/partition and how values were written before concluding whether a row will still appear in SELECT.

### Inspecting TTL via CQL

```sql
SELECT observed_at, observation_id,
       payload,
       TTL(payload),
       WRITETIME(payload)
FROM observations_by_sensor_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND observed_at = '2026-11-21T09:00:00Z'
  AND observation_id = 142dd6ae-6706-4f2c-a5e8-61cdd9c22cad;
```

`TTL(payload)` gives the remaining time when the cell is live and has a TTL; `WRITETIME(payload)` gives the write timestamp when available. They are **not** tools for accurately enumerating all physical tombstones after data expires.

## 14. Why do range/partition tombstones still have read costs?

A common mistaken explanation is: "If deleting an entire partition creates just one tombstone, subsequent queries will definitely be cheap." The number of **delete mutations** and the amount of **read/compaction work** are not the same quantity.

Cassandra may need to:

1. Read/merge partition and clustering range information across multiple SSTables.
2. Compare tombstones against old cells/rows by write timestamp.
3. Determine which values are still live to return.
4. Retain deletion markers while older versions still need to be shadowed on other SSTables or replicas.
5. Drop tombstones and corresponding data only when compaction satisfies safe reclamation conditions.

```text
SSTable-A: rows E1, E2, E3 (older timestamps)
SSTable-B: range tombstone [08:00,09:00)
SSTable-C: some newer writes in the same partition

On read:
  must reconcile markers, timestamps, and corresponding data.
```

A range tombstone can **save delete commands** compared to deleting row-by-row, but reading a slice intersecting many tombstones and a large volume of old data can still be resource-intensive. A partition tombstone has broader scope, making old versions in the partition no longer live, but it does not make the SSTables holding them disappear right away.

### `LIMIT` does not cap the number of tombstones inspected

```sql
SELECT observed_at, observation_id, status
FROM observations_by_sensor_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
LIMIT 20;
```

`LIMIT 20` caps the number of **result** rows; it does not guarantee a replica only inspects 20 internal cells/rows. When the newest range has lots of deleted/TTL-expired data, Cassandra may have to read past many markers before returning enough live rows.

A query returning 0 rows yet having to process many tombstones can still be slow.

## 15. Tombstone reclamation: when are deletion markers cleaned up?

Logical deletion occurs when old data is beaten by a deletion marker by timestamp. **Physical reclamation** is a subsequent step, primarily via compaction, subject to the requirement of not letting old data "come back to life."

```text
DELETE / NULL / TTL expiry
            |
            v
Deletion marker / expired cell logically effective
            |
            +--> other replicas may still hold old data
            |
            v
Old data and deletion markers remain on SSTables
            |
            v
Satisfies grace, SSTable overlap, repair, and safety conditions
            |
            v
Compaction can purge tombstone + shadowed versions
```

### Role of `gc_grace_seconds`

`gc_grace_seconds` is a table parameter that helps define the **protection window** for tombstones before they become eligible for reclamation under version mechanics. It relates to the risk of a disconnected replica missing a deletion and later returning with old data.

If a replica missed a deletion while other replicas cleaned up the tombstone too early, the old version can be propagated and reappear — commonly called **zombie data**. Therefore, repair schedules, grace configuration, and tombstone cleanup must be designed together.

**However, `gc_grace_seconds` is not an "erase on the dot" timer:**

- Reaching the grace period **does not guarantee** the tombstone is purged immediately.
- Another SSTable may still contain an older version that the tombstone must shadow.
- Compaction strategy and overlap conditions affect purge eligibility.
- Replica/repair state and version-specific tombstone garbage collection mechanisms also play a role.

Do not lower `gc_grace_seconds` solely because logs show many tombstones, especially in clusters where replicas can be offline for extended periods or repair is not guaranteed.

### Why doesn't a delete operation reduce disk space immediately?

In an LSM engine, a DELETE initially **appends** a tombstone to the commit log/memtable/SSTable. Physical bytes on disk can temporarily increase. Only when compaction becomes eligible to purge shadowed data and markers can the footprint shrink. Do not conclude DELETE failed just because SSTable bytes have not dropped immediately after CQL returns success.

## 16. Observability: measuring tombstones by query and table

When you see SELECT returning few rows while p99 rises, diagnose rather than measuring live row count alone.

### Table statistics

```bash
nodetool tablestats app_ks.observations_by_sensor_day
nodetool tablehistograms app_ks observations_by_sensor_day
```

Version-supported fields may include:

- **Average tombstones per slice** and live cells per slice.
- **Read latency**, SSTables per read, SSTable count.
- **Partition size / cell count histogram**.
- Metrics related to tombstones, compaction backlog, read timeouts, and node load.

These numbers may be scoped to **table and node**, not the exact tombstone count of a single full primary key. Large partition size, high cell count, heavy TTL, and hot partitions can occur together, so combine metrics.

### Tracing a bounded query

In a controlled environment:

```sql
TRACING ON;

SELECT observed_at, observation_id, status
FROM observations_by_sensor_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
LIMIT 20;

TRACING OFF;
```

Tracing can show the read path and the amount of data/tombstones inspected when the version provides that information. Tracing has overhead; **do not** enable it for every production request.

### Tombstone warning and failure thresholds

Some Cassandra versions have settings such as `tombstone_warn_threshold` and `tombstone_failure_threshold` for read queries. Names, defaults, ranges, and semantics can vary by version/distribution. Check the exact system you are running rather than copying thresholds from another environment.

**Do not raise the failure threshold as a root fix**: it may simply allow a query to keep scanning even more data and increase CPU/I/O.

### Why doesn't `COUNT(*)` measure tombstones?

```sql
SELECT COUNT(*)
FROM observations_by_sensor_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21';
```

`COUNT(*)` returns the number of visible rows under read semantics; it does not count all physical tombstones. Counting over a large partition can also create heavy load. Use metrics/tracing/histograms or inspect SSTables with appropriate tools in a safe environment to investigate further.

## 17. Java Driver 4.x: expressing deletion scope in the API

A repository should clearly separate **cell**, **row**, and **partition** delete operations, rather than providing one method with a confusing boolean parameter.

Example:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class ObservationRepository {
    private final CqlSession session;
    private final PreparedStatement deletePayload;
    private final PreparedStatement deleteRow;
    private final PreparedStatement deletePartition;

    public ObservationRepository(CqlSession session) {
        this.session = session;

        this.deletePayload = session.prepare(
            "DELETE payload FROM observations_by_sensor_day " +
            "WHERE tenant_id = ? AND sensor_id = ? AND event_day = ? " +
            "AND observed_at = ? AND observation_id = ?"
        );

        this.deleteRow = session.prepare(
            "DELETE FROM observations_by_sensor_day " +
            "WHERE tenant_id = ? AND sensor_id = ? AND event_day = ? " +
            "AND observed_at = ? AND observation_id = ?"
        );

        this.deletePartition = session.prepare(
            "DELETE FROM observations_by_sensor_day " +
            "WHERE tenant_id = ? AND sensor_id = ? AND event_day = ?"
        );
    }

    public void removePayload(
            String tenantId, UUID sensorId, LocalDate day,
            Instant observedAt, UUID observationId) {
        session.execute(deletePayload.bind(
            tenantId, sensorId, day, observedAt, observationId
        ));
    }

    public void removeObservation(
            String tenantId, UUID sensorId, LocalDate day,
            Instant observedAt, UUID observationId) {
        session.execute(deleteRow.bind(
            tenantId, sensorId, day, observedAt, observationId
        ));
    }

    // Dangerous operation: deletes both static data and all rows in the day.
    // Call only after authentication/authorization and business policy checks.
    public void removeWholeDay(
            String verifiedTenantId, UUID sensorId, LocalDate day) {
        session.execute(deletePartition.bind(
            verifiedTenantId, sensorId, day
        ));
    }
}
```

In real-world applications:

1. The **full primary key** must be bound when deleting a row or cell; partition deletion only uses the **full partition key**.
2. `tenantId` must come from an authenticated/authorized context, never arbitrarily trusting user-supplied strings.
3. Dedicated permissions/call paths are needed for **partition deletion**, since its blast radius is much larger than deleting a column.
4. The same keys and mutation semantics must remain stable on retries. A timeout does not prove the server did not apply the DELETE.
5. If using client-specified write timestamps, mutation ordering must be managed; skewed timestamps can let old data win or let deletion markers shadow new writes.
6. The repository should not turn absent fields in a PATCH API into `null` and write tombstones. Distinguish **do not update**, **assign value**, and **explicit delete**.
7. Deleting rows across multiple partitions does not become an atomic transaction just because Java calls prepared statements sequentially.

### When you need to delete one map key

The application should have a dedicated method like `removeAttribute(key)`, building valid prepared CQL for the target version and binding both the element key and the full primary key. Do not use `DELETE attributes` when you only want to delete one key, because that wipes the entire collection.

## 18. Anti-patterns related to tombstone scope

| Anti-pattern | Consequence | Improvement |
| --- | --- | --- |
| Sending `null` for all fields missing in PATCH | Unintended cell tombstones | Distinguish absent, UNSET, and explicit delete. |
| Deleting row-by-row when business wants to drop whole partition | Many mutations/row tombstones; higher write work | Use partition-level deletion when **genuinely allowed** to delete the whole partition. |
| Deleting whole partition when only one column needed removal | Loss of valid data, including static data | Keep delete scope to the business minimum. |
| Deleting map key by repeatedly reassigning the whole large map | Complex deletion and many cells/tombstones | Edit elements when needed, or model elements as rows. |
| Using frozen collection yet needing per-element deletes | Forces replacing whole value, costly updates | Choose small non-frozen collections or a child table per element. |
| Very short TTLs on very high-rate writes | Many expired cells and read/compaction cost | Design bucketing/lifecycle and load-test TTLs. |
| Assuming `LIMIT 10` means reading only 10 cells | May scan a huge number of tombstones | Measure scanned tombstones and narrow the clustering range. |
| Lowering `gc_grace_seconds` to "delete fast" | Zombie data risk if a replica misses deletes | Synchronize repair and evaluate safety per version. |
| Raising tombstone warning threshold to quiet logs | Masks the root cause of read amplification | Fix DELETE/TTL/query/schema patterns first. |
| Using unbounded collections for large datasets | Overhead/tombstones bloat | Cap collection size, split into query-driven tables. |

The goal is not "never have tombstones." Cassandra **needs tombstones** to delete data properly in a distributed environment. The goal is **proper scope, managed lifecycle, and no surprise costs**.

## 19. Case study exercise and answers

A system stores device data with partition `(tenant_id='acme', sensor=S1, event_day=2026-11-21)` and:

- Static column `day_note = 'Morning shift'`.
- Row E1 at 08:00 has `status='ok'`, `payload='T=38.1'`, `attributes={'unit':'C','source':'edge'}`, and `frozen_attrs={'location':'room-A'}`.
- Row E2 at 08:05 has `status='ok'`, `payload='T=38.4'`.
- Row E3 at 08:10 has `status='ok'`, `payload='T=38.7'`.

The following operations are evaluated **independently from the same initial state**, unless stated otherwise.

**Questions:**

1. What deletion scope does `DELETE payload` at E1's full primary key create? Can E1 still be read?
2. How does `DELETE attributes['source']` on E1 differ from `DELETE attributes`?
3. Can deleting `frozen_attrs` delete only the key `'location'` while keeping other keys?
4. How does `DELETE FROM ... WHERE full_primary_key_of_E1` differ from `DELETE payload`?
5. Does deleting E1 automatically delete `day_note`?
6. What does `DELETE day_note ... WHERE partition_key` delete? Do E2/E3 stay alive?
7. How does deleting a range `[08:00, 08:10)` affect E1, E2, E3?
8. Does deleting **the entire daily partition** preserve static `day_note`?
9. Why can a range tombstone shadow 100,000 rows without necessarily having 100,000 DELETE statements?
10. If `payload` is written with a 600-second TTL, does TTL expiration automatically generate a new DELETE statement from the application?
11. Can you deduce the number of tombstones on SSTables from `COUNT(*)` or `TTL(payload)`?
12. If a replica misses a delete and returns after tombstones on other replicas were unsafely purged, what risk arises?
13. If you rewrite `payload` on E1 with a write timestamp greater than the cell tombstone, what can happen?
14. When a Java DTO does not contain the `status` field, should you bind `null` or skip the mutation if the intent is "keep status unchanged"?

**Answers:**

1. **Cell tombstone** for E1's `payload`. E1 can still exist thanks to `status` or other live values.
2. The first deletes **one element** of a non-frozen map; the second deletes **the entire collection**, potentially via complex deletion.
3. **Not under frozen value element-update semantics.** A frozen map is a monolithic value; the entire cell must be replaced or deleted.
4. The first deletes **the entire row E1** via row deletion, whereas the second deletes only `payload`.
5. **No.** Static data belongs to the partition, not specifically to E1.
6. Deletes the **static cell** of the partition; rows E2/E3 are not automatically deleted.
7. If range syntax is supported with that condition, E1 and E2 fall within `[08:00,08:10)`, while E3 at exactly 08:10 is **outside the range** and is kept.
8. **No.** Partition deletion shadows both static data and clustering rows belonging to the partition.
9. Because a range tombstone represents a **clustering slice** with a deletion timestamp, without needing a separate mutation for each row.
10. **No.** The cell expires by TTL and is treated as deleted data, not a new DELETE job.
11. **No.** COUNT(*) counts visible rows; TTL() gives remaining metadata for a value, not a physical tombstone listing.
12. **Zombie data**: the old version risks reappearing if deletion information was reclaimed before the replica was safely synchronized.
13. The new value **can come back to life** if it wins according to timestamps and relevant reconciliation rules.
14. **Skip the mutation** for `status`, or use UNSET per your API/version; binding NULL carries deletion semantics and can create a tombstone.

### Additional practice

Create the table `observations_by_sensor_day` in a test keyspace and write one partition with three rows as in section 2. Then run three separate rounds of experiments:

```sql
-- Round A: delete one cell.
DELETE payload FROM observations_by_sensor_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND observed_at = '2026-11-21T08:00:00Z'
  AND observation_id = 8817a208-1858-4144-86e9-b24d9083e478;

-- Round B: delete one row.
DELETE FROM observations_by_sensor_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND observed_at = '2026-11-21T08:00:00Z'
  AND observation_id = 8817a208-1858-4144-86e9-b24d9083e478;

-- Round C: delete the entire partition.
DELETE FROM observations_by_sensor_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21';
```

Before each round, restore the sample data. Query back by the full partition key and compare the remaining live rows/static values. If you have operational access to a lab environment, also observe tombstone and SSTable statistics with appropriate tools. **Do not perform partition deletion on production data just to test.**

## 20. Checklist for choosing the right tombstone level

- [ ] Identify the **full partition key** and clustering columns of the table.
- [ ] Determine whether the business requirement is deleting a **cell, element, collection, row, range, or partition**.
- [ ] Check whether the target column is **regular, static, non-frozen collection, or frozen value**.
- [ ] For range deletions, confirm syntax and clustering-prefix rules on the **exact Cassandra version in use**.
- [ ] Do not confuse **NULL** with **UNSET** or an omitted column in a mutation.
- [ ] Evaluate **write timestamps** when concurrent writes/deletes or retries occur.
- [ ] Check TTL and cell/collection lifecycles; do not assume every TTL expiration is a row/partition DELETE.
- [ ] For wide-scope delete commands, verify that all shadowed data **is permitted to be deleted**, including static data.
- [ ] When investigating cost, measure **tombstones scanned**, SSTable count/read latency, and compaction, not just COUNT(*).
- [ ] Maintain repair schedules and safe grace configuration to reduce zombie data risk.
- [ ] Do not expect compaction or DELETE to free SSTable bytes immediately.
- [ ] In Java, separate cell/row/partition delete APIs, enforce tenant authorization, and restrict dangerous operations.
- [ ] Use a lab environment with a TTL/DELETE workload to test before intervening in production.

## 21. Key takeaways

- A **cell tombstone** shadows one column value; a **static-cell tombstone** shadows a shared partition-level value.
- **Non-frozen collections** can have **element tombstones** and **complex deletions**; **frozen collections** are handled as a single monolithic cell value.
- A **row tombstone** shadows one clustering row; it does not automatically delete static data or other rows in the same partition.
- A **range tombstone** shadows a clustering slice within **one partition**, without implicitly creating an individual tombstone for every row.
- A **partition tombstone** shadows both clustering rows and static values belonging to **one complete partition key**.
- **NULL, DELETE, and TTL expiration** can all lead to a deleted state, though their scope and formation differ.
- Tombstones carry a **write timestamp**, which must be reconciled against live data versions before determining read results.
- **Logical deletion first, physical reclamation later**: compaction, `gc_grace_seconds`, replica state, and SSTable overlap determine when cleanup can occur.
- **Many tombstones can make SELECT slow even with a small LIMIT**, because Cassandra must inspect markers and old data to find live rows.
- The sustainable solution is choosing the **right deletion scope**, managing collections/TTL, designing appropriate partition keys, and monitoring performance rather than merely loosening tombstone thresholds.

Understanding tombstones from the cell level to the partition level helps you make accurate decisions when deleting data in Cassandra: deleting only what is requested, avoiding shadowing valid data, and predicting impacts on the read path, compaction, repair, replication, and Java operations. This is also the foundation for deeply understanding the **tombstone reclamation** process and troubleshooting in distributed wide-column databases.
