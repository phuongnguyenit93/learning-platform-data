# How Indexes Support Queries and Their Write Maintenance Costs

## 1. What Problem Do Indexes Solve?

In MongoDB, a collection can hold anywhere from a few hundred to millions of documents. A request like "find an order by code" or "get a customer's 20 most recent orders" usually needs only a tiny fraction of the data. If every query had to inspect every document, processing time and read operations could grow rapidly as the collection scales.

An **index** provides a separate data structure to locate documents by pre-organized key values. MongoDB can use indexes to:

1. **Filter quickly:** find keys matching an exact value or falling within a range instead of scanning broadly.
2. **Sort:** read keys in the desired return order, potentially avoiding a separate sort step.
3. **Serve results directly from the index:** in some cases, without reading the original documents.
4. **Enforce constraints:** a unique index prevents duplicate key values according to the chosen rules.

In return, when you **insert**, **update**, or **delete** documents, MongoDB may have to update the related indexes. Indexes also consume disk space and use cache memory when accessed.

> **"More indexes = faster" is not true. Indexes accelerate matching query paths, but they incur storage and maintenance costs whenever data changes.**

| Need | How can an index help? | Trade-off cost |
| --- | --- | --- |
| Lookup by business key | Locates a small key range. | Maintaining the index on inserts, deletes, or key changes. |
| Filtering by time or price | Scans the corresponding key range. | Additional storage and work on writes. |
| Fetching the N latest results | Uses key order instead of sorting a large set. | A compound index may be wider. |
| Returning few data fields | May avoid reading the original document. | The index stores more fields. |
| Enforcing uniqueness | Prevents duplicate keys even under concurrent requests. | Added check overhead and risk of E11000 errors on writes. |

This lesson focuses on **basic indexes** for querying BSON documents and why they can affect the system's write performance.

---

## 2. Index Structure from an Application Perspective

A standard MongoDB index can be thought of as a set of **keys organized in order** along with information to identify the corresponding documents. Regular indexes use a B-tree / B-tree-like structure depending on the storage engine and index type. You don't need to memorize physical page layouts to understand query behavior: the core idea is that the engine can **seek to a key** and **scan contiguous key ranges**.

For example:

```javascript
db.customers.insertMany([
  { _id: 1, email: "an@example.com", name: "An" },
  { _id: 2, email: "chi@example.com", name: "Chi" },
  { _id: 3, email: "binh@example.com", name: "Binh" }
]);

db.customers.createIndex({ email: 1 });
```

You can picture the index organizing its entries as follows:

```text
Index email (conceptual model)
───────────────────────────────────────────
"an@example.com"   -> document _id: 1
"binh@example.com" -> document _id: 3
"chi@example.com"  -> document _id: 2
───────────────────────────────────────────
```

This is only a **logical illustration**, not the actual byte format inside WiredTiger. The query:

```javascript
db.customers.findOne({ email: "binh@example.com" });
```

can locate the matching key range instead of checking every document one by one.

### 2.1. Meaning of `1` and `-1`

```javascript
db.customers.createIndex({ email: 1 });   // ascending
db.orders.createIndex({ createdAt: -1 });  // descending
```

`1` and `-1` represent the key ordering direction. For a single-field index, MongoDB can usually scan in either direction; the chosen direction matters more when **multiple fields in a compound index** work together to serve filters and sorts.

### 2.2. Indexes Do Not Contain Every Document Field

An `{ email: 1 }` index does not store `name`, `address`, `lastLogin`, or the full document by default. If a query needs to return those fields, after scanning the index MongoDB may have to **FETCH** the original document.

Therefore, it is important to distinguish between:

- **Index scan:** finding keys and locating documents.
- **Document fetch:** reading the document to retrieve fields not present in the index.
- **Covered query:** all fields needed by the query are satisfied by the index, so fetching the document may not be necessary.

### 2.3. Default Index on `_id`

MongoDB creates a unique index on `_id` for standard collections. Therefore:

```javascript
db.customers.findOne({ _id: 2 });
```

already has a suitable lookup path. You should not create a redundant index just because `_id` appears in a query.

---

## 3. How Collection Scans and Index Scans Differ

Suppose the `orders` collection has one million documents and needs a lookup by code:

```javascript
db.orders.findOne({
  orderCode: "ORD-1001"
});
```

Without a suitable index, the query engine may perform a **COLLSCAN**: inspecting documents sequentially until it finds enough results or exhausts the set to examine.

```text
Document 1    no match
Document 2    no match
Document 3    no match
...
Document N    match
```

`findOne()` does not necessarily scan the entire collection if a match is encountered early. However, searching for a **non-existent** code or one located very late can force the engine to inspect a large number of documents.

Create an index:

```javascript
db.orders.createIndex(
  { orderCode: 1 },
  { name: "idx_order_code" }
);
```

If the query planner chooses the index, MongoDB can jump directly to the matching `orderCode` key range and then fetch one or a few corresponding documents.

```text
orderCode = "ORD-1001"
          |
          v
     Index lookup
          |
          v
  Matching index entry
          |
          v
Corresponding document (if needed)
```

**Having an index does not guarantee MongoDB will use it.** The planner chooses an execution path based on factors such as filter selectivity, number of documents to read, and estimated cost. For a very small collection, scanning the collection may be faster. For a query returning nearly the entire collection, scanning an index and fetching every document individually can also be less efficient.

---

## 4. Sample Data for the Examples

Assume the `orders` collection does not initially contain the IDs used in the example:

```javascript
db.orders.insertMany([
  {
    _id: "O1001",
    orderCode: "ORD-1001",
    customerId: "C01",
    status: "PAID",
    createdAt: ISODate("2026-11-01T08:00:00Z"),
    totalMinor: NumberLong("520000"),
    items: [
      { sku: "P10", quantity: 2 },
      { sku: "P11", quantity: 1 }
    ]
  },
  {
    _id: "O1002",
    orderCode: "ORD-1002",
    customerId: "C01",
    status: "SHIPPED",
    createdAt: ISODate("2026-11-02T09:30:00Z"),
    totalMinor: NumberLong("190000"),
    items: [{ sku: "P20", quantity: 1 }]
  },
  {
    _id: "O1003",
    orderCode: "ORD-1003",
    customerId: "C02",
    status: "PAID",
    createdAt: ISODate("2026-11-03T11:00:00Z"),
    totalMinor: NumberLong("720000"),
    items: [{ sku: "P30", quantity: 3 }]
  },
  {
    _id: "O1004",
    orderCode: "ORD-1004",
    customerId: "C01",
    status: "PAID",
    createdAt: ISODate("2026-11-04T14:10:00Z"),
    totalMinor: NumberLong("870000"),
    items: [{ sku: "P40", quantity: 1 }]
  }
]);
```

These four documents illustrate syntax and data semantics. They are **not sufficient for measuring performance**: the planner may reasonably choose a COLLSCAN on a dataset that is too small.

---

## 5. Inspecting the Execution Plan with `explain()`

To see which index MongoDB actually uses, run:

```javascript
db.orders.find({
  customerId: "C01"
}).explain("executionStats");
```

Information commonly found in the output:

| Field / stage | Meaning |
| --- | --- |
| `winningPlan` | The plan selected by the query planner. |
| `COLLSCAN` | Scans documents in the collection. |
| `IXSCAN` | Traverses index entries. |
| `FETCH` | Retrieves documents after identifying keys through the index. |
| `SORT` | Sorts results in a separate stage. |
| `nReturned` | Number of documents returned. |
| `totalKeysExamined` | Number of index entries examined. |
| `totalDocsExamined` | Number of documents examined. |
| `executionTimeMillis` | Execution time within the explain context. |

Stage names and positions can vary by version and query execution engine. When building dashboards, rely on the response from your running version rather than assuming a fixed JSON tree.

Create an index and inspect again:

```javascript
db.orders.createIndex({ customerId: 1 });

db.orders.find({
  customerId: "C01"
}).explain("executionStats");
```

If the planner selects the index, `IXSCAN` followed by `FETCH` may appear, because `find()` returns full documents.

### 5.1. Reading Examined Metrics

The numbers below are **hypothetical examples**, not benchmarks:

| Scenario | `nReturned` | `totalKeysExamined` | `totalDocsExamined` | Interpretation |
| --- | ---: | ---: | ---: | --- |
| Equality using a selective index | 20 | 20 | 20 | Few keys and documents need to be read. |
| Suboptimal index | 20 | 100,000 | 80,000 | Scans many keys and filters many documents. |
| Covered query | 20 | 20 | 0 | Results can be served from the index. |
| Collection scan | 20 | 0 | 1,000,000 | Reads huge numbers of documents to return few results. |

If `totalDocsExamined` is very large compared to `nReturned`, investigate the query and index. However, do not rigidly apply a `docsExamined/nReturned` ratio to every case: an aggregation computing totals may legitimately read many documents, and when `nReturned = 0` division is undefined. Always consider `keysExamined`, CPU, I/O, sorts, and application latency as well.

### 5.2. A Fast Query on a Test Machine Does Not Prove an Index Is Good

With a warm cache and small dataset, `executionTimeMillis` may be too low to distinguish between plans. Evaluate on data whose size, key distribution, and concurrency level resemble your real workload.

---

## 6. Indexes Support Range Queries

Because indexes are ordered by key, they are often useful for date-range and price-range queries:

```javascript
db.orders.createIndex({ createdAt: 1 });

db.orders.find({
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  }
});
```

The engine can scan the corresponding key range:

```text
... Oct 30 | Oct 31 | Nov 01 .... Nov 30 | Dec 01 ...
                    ^              ^
                    |--- range -----|
```

When the condition matches 0.1% of documents, an index can be very helpful. When the condition matches 99% of documents, scanning the index and fetching nearly every document may perform no better than scanning the collection.

### 6.1. How Filter Syntax Affects Index Usage

For example, a condition that transforms a date field directly:

```javascript
db.orders.find({
  $expr: {
    $eq: [
      { $year: "$createdAt" },
      2026
    ]
  }
});
```

will not necessarily leverage a standard index on `createdAt` the way a direct range filter does. If the requirement is the year 2026 in UTC:

```javascript
db.orders.find({
  createdAt: {
    $gte: ISODate("2026-01-01T00:00:00Z"),
    $lt: ISODate("2027-01-01T00:00:00Z")
  }
});
```

is usually a more sargable way to express the predicate. For business calendars in time zones other than UTC, convert the date/time boundaries accordingly.

---

## 7. Indexes Support Sorting and `limit`

To fetch the 20 latest orders:

```javascript
db.orders.find({})
  .sort({ createdAt: -1 })
  .limit(20);
```

Without a suitable index, MongoDB may need to read many documents and maintain ordering to determine the top 20. `limit(20)` does not by itself guarantee that only 20 documents are read.

An index:

```javascript
db.orders.createIndex({ createdAt: -1 });
```

can allow the engine to traverse `createdAt` in descending order and stop once enough results are retrieved.

In particular, for a customer order-history endpoint:

```javascript
db.orders.find({
  customerId: "C01"
}).sort({ createdAt: -1 }).limit(20);
```

the following compound index is a natural candidate:

```javascript
db.orders.createIndex({
  customerId: 1,
  createdAt: -1
});
```

A customer's orders sit in a contiguous key range by `customerId`, and within that range `createdAt` is ordered descending. If the planner selects this index, a separate `SORT` stage can be avoided.

Indexes can also supply ordering for some aggregations. However, after transforming stages such as `$group`, `$unwind`, or `$lookup`, whether `$sort` can use an index depends on the pipeline and execution plan, not merely on field names.

---

## 8. Compound Indexes: Multiple Fields in One Index

An index containing multiple fields:

```javascript
db.orders.createIndex({
  customerId: 1,
  status: 1,
  createdAt: -1
});
```

organizes index keys hierarchically across its components. Conceptually:

```text
(customerId, status, createdAt)
("C01", "PAID",    2026-11-04)
("C01", "PAID",    2026-11-01)
("C01", "SHIPPED", 2026-11-02)
("C02", "PAID",    2026-11-03)
```

This index is a suitable candidate for:

```javascript
db.orders.find({
  customerId: "C01",
  status: "PAID"
}).sort({ createdAt: -1 }).limit(20);
```

### 8.1. The Left-Prefix Rule

With `{ customerId: 1, status: 1, createdAt: -1 }`:

- Queries filtering on `customerId` can utilize the leading prefix.
- Queries filtering on `customerId` and `status` can utilize the first two fields.
- Queries with both conditions above plus sorting on `createdAt` can utilize the third field's order.
- Queries filtering **only** on `status` without a `customerId` condition usually **cannot leverage** this index as effectively as an index starting with `status`.

MongoDB can consider different index scan strategies; do not claim an index is never used when a prefix is missing. The key takeaway is that field order affects query efficiency.

### 8.2. The ESR Guideline: Equality, Sort, Range

A common guideline for ordering fields in a compound index:

1. **E — Equality:** fields compared for exact equality.
2. **S — Sort:** fields used for sorting.
3. **R — Range:** fields with range predicates.

Example:

```javascript
db.orders.find({
  customerId: "C01",
  status: "PAID",
  totalMinor: { $gte: NumberLong("300000") }
}).sort({ createdAt: -1 }).limit(20);
```

Candidate index following ESR:

```javascript
db.orders.createIndex({
  customerId: 1,
  status: 1,
  createdAt: -1,
  totalMinor: 1
});
```

**ESR is not an absolute optimality rule.** If the range on `totalMinor` is highly selective, an Equality–Range–Sort order may reduce the number of keys scanned, even if it incurs a sort. Always test on realistic data with `explain` rather than creating indexes solely from an acronym.

### 8.3. Overly Wide Indexes Are Not Automatically Better

Adding more fields to a compound index lengthens keys and can make the index larger. Queries that do not constrain leading fields or do not need trailing fields gain little benefit. An eight-field index is not inherently better than a two-field index.

---

## 9. Covered Queries: Avoiding Original Document Reads

With the index:

```javascript
db.orders.createIndex({
  customerId: 1,
  status: 1,
  createdAt: -1
});
```

the query:

```javascript
db.orders.find(
  { customerId: "C01", status: "PAID" },
  {
    _id: 0,
    customerId: 1,
    status: 1,
    createdAt: 1
  }
).sort({ createdAt: -1 });
```

can be **covered** if other conditions also align. In that case, the engine can return data from the index without FETCHing the original documents; `totalDocsExamined` can be 0.

### 9.1. Why Use `_id: 0`?

MongoDB projections include `_id` by default. If the index being used **does not contain `_id`**, returning `_id` can force a document fetch. Therefore, when checking for a covered query, inspect **all returned fields**, including `_id`.

If you additionally request `totalMinor`, which is not in the index:

```javascript
db.orders.find(
  { customerId: "C01", status: "PAID" },
  {
    _id: 0,
    createdAt: 1,
    totalMinor: 1
  }
);
```

MongoDB may have to fetch the documents. **Projecting few fields does not mean a query is covered.**

### 9.2. Do Not Expand Indexes Indefinitely Just for Coverage

Adding fields to an index can eliminate FETCH for one endpoint, but it makes the index heavier and increases write overhead. Weigh read gains against real-world index maintenance costs.

---

## 10. Selectivity Determines the Benefit

A highly selective filter returns very few documents out of the whole collection. A low-selectivity filter matches most documents.

| Field | Assumed distribution | Potential benefit |
| --- | --- | --- |
| `orderCode` | Nearly unique code per order. | An equality index is typically very helpful. |
| `customerId` | Each customer has few orders relative to the total. | Index is useful for customer history. |
| `status` | 95% of orders are `COMPLETED`. | Querying this status may still read nearly the entire collection. |
| `isActive` | 99.9% of users are `true`. | Querying `true` gains little from a single-field index. |
| `createdAt` | Spans multiple years. | Narrow time ranges can benefit significantly. |

That does not mean boolean or status fields are never worth indexing. If a status is rare—for example, only 0.1% of documents are `FAILED`—an index can serve an error-handling dashboard well. **Data distribution and query predicates matter more than the data type of a single field.**

A query returning hundreds of thousands of documents also still incurs network transfer, BSON decoding, and application processing costs. Indexes do not replace pagination, projection, or API design that bounds returned payload sizes.

---

## 11. Multikey Indexes: Indexes on Arrays

Product example:

```javascript
{
  _id: "P100",
  name: "Laptop",
  tags: ["sale", "electronics", "featured"]
}
```

When creating:

```javascript
db.products.createIndex({ tags: 1 });
```

MongoDB uses a **multikey index** under the appropriate rules for array fields. A single document can produce multiple index entries from its elements. The query:

```javascript
db.products.find({ tags: "electronics" });
```

can locate documents containing that tag via the index.

### 11.1. Larger Arrays Mean Noticeable Maintenance Cost

A document with three tags has a very different index cost than one with several thousand tags. When array elements are added or removed, the engine must maintain the corresponding index entries. Indexing unbounded arrays can substantially increase storage and write costs.

### 11.2. Arrays Containing Embedded Documents

Example:

```javascript
{
  _id: "O2001",
  items: [
    { sku: "P1", quantity: 1 },
    { sku: "P2", quantity: 5 }
  ]
}
```

Requirement: "has a line item with SKU P1 and quantity at least 3":

```javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "P1",
      quantity: { $gte: 3 }
    }
  }
});
```

The document above **does not match**. The P1 line item has quantity 1, even though the P2 line item has quantity 5. Writing two independent dotted paths can match criteria across two separate elements and return incorrect results.

Candidate index:

```javascript
db.orders.createIndex({
  "items.sku": 1,
  "items.quantity": 1
});
```

`$elemMatch` both expresses the exact "same element" semantics and can help the planner combine index bounds when applicable.

Compound multikey indexes also have limitations regarding **parallel arrays** when multiple independent fields are arrays. Never blindly create compound indexes across multiple array fields without checking the schema and support rules.

---

## 12. INSERT: One Document Can Trigger Multiple Index Operations

Suppose a collection has:

```javascript
{ _id: 1 }                        // default index
{ orderCode: 1 }
{ customerId: 1, createdAt: -1 }
{ status: 1, createdAt: -1 }
{ "items.sku": 1 }
```

On insert:

```javascript
db.orders.insertOne({
  _id: "O9001",
  orderCode: "ORD-9001",
  customerId: "C01",
  status: "PAID",
  createdAt: new Date(),
  totalMinor: NumberLong("320000"),
  items: [
    { sku: "P10", quantity: 1 },
    { sku: "P20", quantity: 2 }
  ]
});
```

MongoDB does not just write the document; it must also maintain the related indexes.

```text
INSERT order
     |
     +--> Write BSON document
     +--> Maintain _id index
     +--> Maintain orderCode index
     +--> Maintain (customerId, createdAt) index
     +--> Maintain (status, createdAt) index
     +--> Maintain items.sku index keys
     `--> Execute associated durability/replication mechanisms
```

A single document with two SKUs can generate multiple entries in the multikey index.

### 12.1. Write Amplification

**Write amplification** means a single business operation can result in significantly more storage work than simply writing the new data payload. Indexes are one cause: data changes must be reflected across multiple structures.

Do not oversimplify this to "five indexes means exactly five physical writes." WiredTiger uses cache, pages, journaling, checkpoints, compression, and batched updates; actual cost depends on data, workload, and hardware.

### 12.2. Unique Indexes Check for Conflicts

```javascript
db.orders.createIndex(
  { orderCode: 1 },
  { unique: true, name: "uk_order_code" }
);
```

On insert, MongoDB must enforce the uniqueness constraint. If a code already exists, the insert may be rejected with **E11000 duplicate key**.

Unique indexes not only optimize reads but also protect correctness. When building a unique index on existing data, if duplicate keys already exist, the index build can fail; duplicates must be resolved according to business rules beforehand.

### 12.3. Impact on Ingest Throughput

High-throughput event-ingestion systems feel the impact of unnecessary indexes acutely. If most queries only filter by `deviceId` and `timestamp`, one well-chosen compound index is worth keeping far more than a dozen indexes on unqueried metadata. However, never drop indexes required to enforce uniqueness.

---

## 13. UPDATE: Changing an Index Key vs. Changing Only the Document

Not every update requires the same amount of index work.

### 13.1. Non-Indexed Field

Suppose `internalNote` is not indexed:

```javascript
db.orders.updateOne(
  { _id: "O1001" },
  { $set: { internalNote: "Check packaging" } }
);
```

When indexed key values do not change, index entries typically do not need to be modified just for this field. Even so, the document is still updated, incurring cache, storage, and durability costs. This operation should not be called "free."

### 13.2. Indexed Field

```javascript
db.orders.updateOne(
  { _id: "O1001" },
  { $set: { status: "SHIPPED" } }
);
```

If there is an index containing `status`, the index must reflect the new key:

```text
Old index key: ("PAID", createdAt)
                 |
                 v
        Document changes status
                 |
                 v
New index key: ("SHIPPED", createdAt)
```

Conceptually, the old entry may need to be removed and a new entry inserted. If `status` appears in multiple indexes, multiple structures must be maintained.

### 13.3. Updating an Array with a Multikey Index

```javascript
db.products.updateOne(
  { _id: "P100" },
  { $push: { tags: "clearance" } }
);

db.products.updateOne(
  { _id: "P100" },
  { $pull: { tags: "clearance" } }
);
```

If `tags` has a multikey index, these operations can add or remove index entries. Frequently updated arrays paired with multiple indexes can easily drive up write costs.

### 13.4. Concurrency and Hot Index Pages

Many writers operating on adjacent keys simultaneously can put pressure on index pages, cache, and I/O. If write latency rises, examine write rate, key distribution, index count, storage latency, replication, and contention—do not assume "just adding RAM" solves it.

---

## 14. DELETE: Fast Lookup Does Not Mean Free Deletion

```javascript
db.orders.deleteOne({
  _id: "O1001"
});
```

When a document is deleted, MongoDB must maintain related indexes so subsequent queries no longer see the corresponding entries.

Deleting many old documents:

```javascript
db.events.deleteMany({
  createdAt: {
    $lt: ISODate("2026-01-01T00:00:00Z")
  }
});
```

An index on `createdAt` can help **identify** the documents to delete, but afterward the engine must still delete the document contents and update all other indexes. A large-scale delete can cause significant I/O and write pressure.

TTL indexes also generate background deletion work and index maintenance; TTL does not make expiring data resource-free.

---

## 15. Indexes and Resources: Disk, RAM, Cache, I/O

### 15.1. Storage Space

An index consumes additional disk space. Multi-field indexes or multikey indexes on large arrays can be substantial.

You can inspect statistics with:

```javascript
db.orders.stats();
```

Depending on version and environment, the output includes fields such as `storageSize`, `totalIndexSize`, and `indexSizes`.

Do not take the compressed on-disk index size and extrapolate directly how much RAM WiredTiger must retain. Page format, compression, and the working set determine actual memory usage.

### 15.2. Cache Memory and the Working Set

Frequently accessed indexes have "hot" pages in the WiredTiger cache. Those pages compete for RAM with document data pages. Infrequently used indexes still occupy disk space, though that does not mean they stay resident in RAM in full.

### 15.3. Page Splits and Internal Overhead

Because indexes store keys in order, adding keys can cause the storage engine to adjust page structures, perform reconciliation, or trigger **page splits** when necessary. Not every insert causes a split; this is normal internal behavior rather than a query bug.

### 15.4. Journal, Checkpoints, and Replication

Data and index modifications participate in the storage engine's durability mechanisms. Journaling, checkpointing, and physical page writes are related operations, though not identical. In a replica set, secondary nodes must also maintain their own data and indexes. Index costs do not occur solely on the primary.

There is no exact formula like "twice as many indexes makes inserts twice as slow." Measure on a realistic workload.

---

## 16. Basic Index Types and Trade-Offs

| Type / option | Useful for | Costs and limitations |
| --- | --- | --- |
| Single-field | Equality, range, or sort on one field. | Uses extra storage and adds work when the field changes. |
| Compound | Combined filter and sort, sometimes covered queries. | Field order matters; keys can become large. |
| Multikey | Matching elements inside arrays. | A single document can generate many entries. |
| Unique | Enforcing unique values or key combinations. | Duplicate writes fail with E11000; builds can fail on existing duplicates. |
| Partial | Indexing only documents matching a filter. | Queries must satisfy the filter to utilize it fully. |
| Sparse | Skipping documents missing the field per rules. | Requires understanding null/missing behavior, especially with unique. |
| TTL | Deleting expired documents in the background. | Deletion is not instantaneous and still generates write I/O. |
| Wildcard | Unknown or dynamic field sets. | Does not replace optimized compound indexes for fixed queries. |
| Text | Word-based text search via text indexes. | Semantics differ from equality/range indexes; requires dedicated design. |

### 16.1. Partial Indexes Reduce Index Size

Suppose 2% of orders are in the `OPEN` state, and operational APIs mainly query this subset:

```javascript
db.orders.createIndex(
  { customerId: 1, createdAt: -1 },
  {
    name: "idx_open_orders",
    partialFilterExpression: {
      status: "OPEN"
    }
  }
);
```

The query:

```javascript
db.orders.find({
  customerId: "C01",
  status: "OPEN"
}).sort({ createdAt: -1 });
```

can leverage the index because it only needs documents belonging to the indexed subset.

This index can be smaller than an index across the entire collection. However, when status transitions from `OPEN` to `PAID`, index membership changes as well, incurring write cost. Queries that do not filter on `status: "OPEN"` cannot rely on this index by default to return complete results.

### 16.2. TTL Indexes Have Deletion Overhead

```javascript
db.sessions.createIndex(
  { expireAt: 1 },
  { expireAfterSeconds: 0 }
);
```

With an appropriate Date field, a TTL index helps purge expired documents, but background deletion provides no millisecond-level timing guarantee. If a session must be rejected immediately upon expiration, the API still needs to check `expireAt`.

### 16.3. Collation for String Data

If case-insensitive queries are needed:

```javascript
db.users.createIndex(
  { displayName: 1 },
  {
    collation: { locale: "en", strength: 2 },
    name: "idx_display_name_ci"
  }
);

db.users.find({ displayName: "alex" }).collation({
  locale: "en",
  strength: 2
});
```

An index with a specific collation will not by default serve queries using a different collation. `locale: "en"` only illustrates the syntax; Vietnamese or multilingual applications must choose appropriate comparison rules.

---

## 17. Do Not Index Every Field

Suppose a product document is:

```javascript
{
  _id: "P1",
  sku: "SKU-001",
  sellerId: "S01",
  categoryId: "LAPTOP",
  status: "ACTIVE",
  priceMinor: 15900000,
  createdAt: new Date(),
  stock: 12,
  viewCount: 5000,
  tags: ["sale", "electronics"],
  description: "..."
}
```

An anti-pattern is indexing every field and adding compound indexes for every "might be used someday" combination. Consequences:

1. Inserts must maintain many indexes unrelated to common queries.
2. Updates to `stock`, `viewCount`, and `status` may need to maintain corresponding indexes.
3. Indexes consume extra disk and working-set cache.
4. Index builds and rebuilds add deployment overhead.
5. The query planner gets more candidates with no guarantee of a better plan.
6. Unused indexes become hard to spot without clear ownership and monitoring.

**Start from your queries, not from a list of fields.**

Example critical endpoints:

| API | Filter | Sort |
| --- | --- | --- |
| Product details | `sku = ?` | None |
| Seller's products | `sellerId = ?`, `status = ACTIVE` | `createdAt DESC` |
| Products by category | `categoryId = ?`, `status = ACTIVE` | `priceMinor ASC` |

Candidate indexes:

```javascript
db.products.createIndex(
  { sku: 1 },
  { unique: true, name: "uk_product_sku" }
);

db.products.createIndex(
  { sellerId: 1, status: 1, createdAt: -1 },
  { name: "idx_seller_active_recent" }
);

db.products.createIndex(
  { categoryId: 1, status: 1, priceMinor: 1 },
  { name: "idx_category_status_price" }
);
```

These are **candidates for the listed queries**, not a default index set for every e-commerce system. If an overnight inventory report can acceptably scan the collection, a dedicated index for it may not be worth slowing down every stock update.

---

## 18. Overlapping and Redundant Indexes

Two indexes:

```javascript
{ customerId: 1 }
{ customerId: 1, createdAt: -1 }
```

share the `customerId` prefix. The second compound index can serve many queries that filter only on `customerId`; thus the first single-field index **may** be redundant.

However, do not drop it immediately because:

- The single-field index may be smaller and fit an extremely frequent query better.
- One index may have `unique`, collation, a partial filter, or other special properties.
- A periodic query or report might rely on the single-field index.
- Each index's net benefit and cost also depend on the query planner and real data.

The goal is to minimize **total read, write, and operational cost**, not merely to shrink the index count for a cleaner dashboard.

---

## 19. Monitoring Which Indexes Are Used

### 19.1. Listing Indexes

```javascript
db.orders.getIndexes();
```

The output reveals existing key patterns, names, and options. This is the first step before proposing a new index.

### 19.2. Access Statistics

```javascript
db.orders.aggregate([
  { $indexStats: {} }
]);
```

`$indexStats` helps observe index usage. However, statistics have a specific scope and reset boundary, and you must account for all relevant nodes and business cycles. An index unused over a two-hour window **does not prove it is useless**, as it may serve a month-end job or emergency workflow.

### 19.3. Slow-Query Log, Profiler, and Monitoring

These tools help pinpoint queries with high latency, high keys/docs examined, or expensive sorts. When enabling detailed profiling in production, consider overhead and sensitive data that could appear in logs.

### 19.4. Measure Before and After Changes

```javascript
db.orders.find({
  customerId: "C01",
  status: "PAID"
}).sort({ createdAt: -1 })
  .limit(20)
  .explain("executionStats");
```

Compare plans, keys/docs examined, sorts, and timing, while also measuring application p95/p99 latency, read/write IOPS, write throughput, and index sizes in a representative environment.

---

## 20. `hint()`, Hidden Indexes, and the Index Removal Process

`hint()` can be used to **test** a specific index:

```javascript
db.orders.find({
  customerId: "C01",
  status: "PAID"
}).sort({ createdAt: -1 })
  .hint({ customerId: 1, status: 1, createdAt: -1 })
  .explain("executionStats");
```

This example assumes the corresponding index already exists. Avoid forcing plans with `hint()` on every production query just to "be sure an index is used"; shifting data distributions can make a forced plan worse over time.

**Hidden indexes** allow hiding an index from the query planner in supported versions:

```javascript
db.orders.hideIndex("idx_customer_status_recent");

// To restore for testing:
// db.orders.unhideIndex("idx_customer_status_recent");
```

The name must match an existing index. **Hiding does not drop the index or reduce write maintenance**: the index continues to be updated on writes. Hidden indexes are useful for evaluating read-path impact before deciding to drop.

If you actually drop it:

```javascript
db.orders.dropIndex("idx_customer_status_recent");
```

dependent queries may slow down, and restoring the index may require rebuilding it across the entire collection. Do not drop indexes that enforce uniqueness or support critical workflows without assessing data constraints and impact first.

---

## 21. Building Indexes on Large Collections

Creating a new index on a very large collection can require reading significant amounts of data, building index pages, and consuming CPU, I/O, RAM, and disk space. The build mechanism and impact on reads/writes depend on the MongoDB version and deployment topology.

Before running:

```javascript
db.orders.createIndex({
  customerId: 1,
  createdAt: -1
});
```

verify:

1. Current document count and storage size.
2. Projected index size and available storage headroom.
3. Read/write load during the build window.
4. Duplicate key status if creating a unique index.
5. Coordination across the replica set / sharded cluster.
6. Metrics to monitor during and after the build.
7. Rollback strategy if query plans or latencies degrade.

An index build is not a zero-cost configuration command just because its syntax is short. For unique indexes, building one can also change the **write contract**: duplicate-key inserts that previously succeeded will begin failing.

---

## 22. Pagination: Indexes Do Not Make Deep `skip` Free

The query:

```javascript
db.orders.find({
  customerId: "C01"
}).sort({ createdAt: -1 }).skip(200000).limit(20);
```

may have to traverse many entries to skip the first 200,000 results, even with a compound index. A deep `skip` does not become a constant-time jump with zero cost.

One solution is **keyset pagination** with a deterministic sort order:

```javascript
db.orders.createIndex({
  customerId: 1,
  createdAt: -1,
  _id: -1
});
```

First page:

```javascript
db.orders.find({
  customerId: "C01"
}).sort({ createdAt: -1, _id: -1 }).limit(20);
```

Subsequent pages use the last key pair from the previous page:

```javascript
const lastCreatedAt = ISODate("2026-11-02T09:30:00Z");
const lastId = "O1002";

db.orders.find({
  customerId: "C01",
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    { createdAt: lastCreatedAt, _id: { $lt: lastId } }
  ]
}).sort({ createdAt: -1, _id: -1 }).limit(20);
```

This example assumes string `_id` values and descending sort order. Keep data types and collations consistent. When multiple filter conditions are involved, analyze the corresponding index and query plan.

---

## 23. Java MongoDB Sync Driver

In Java, you can create indexes using `Indexes` and `IndexOptions`, and query using `Filters` and `Sorts`:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

public class OrderIndexExample {

    private final MongoCollection<Document> orders;

    public OrderIndexExample(MongoCollection<Document> orders) {
        this.orders = orders;
    }

    public void createIndexes() {
        orders.createIndex(
            Indexes.ascending("orderCode"),
            new IndexOptions()
                .unique(true)
                .name("uk_order_code")
        );

        orders.createIndex(
            Indexes.compoundIndex(
                Indexes.ascending("customerId"),
                Indexes.descending("createdAt")
            ),
            new IndexOptions()
                .name("idx_customer_recent")
        );
    }

    public void printRecentOrders(String customerId) {
        orders.find(Filters.eq("customerId", customerId))
            .sort(Sorts.descending("createdAt"))
            .limit(20)
            .forEach(order -> System.out.println(order.toJson()));
    }
}
```

Do not call `createIndexes()` on every HTTP request. Indexes should be managed as part of schema/migration/deployment processes. If existing data contains duplicate `orderCode` values, creating a unique index will fail and the source data must be cleaned up first.

With Spring Data MongoDB, you can use `@Indexed`, `@CompoundIndex`, or operate via `MongoTemplate`; whether annotations automatically create indexes at startup depends on configuration and version. In operations, always verify the actual indexes present in MongoDB.

**A slow query is not necessarily caused by a missing index.** API response time also includes networking, connection pooling, BSON encoding/decoding, document count, and transferring large payloads. Indexes do not replace pagination or proper API payload sizing.

---

## 24. Designing Indexes by Read/Write Workload

| Criterion | Read-heavy | Write-heavy |
| --- | --- | --- |
| Priority | Serve common queries with low p95/p99 latency. | Sustain insert/update/delete throughput. |
| Appropriate indexes | Compound filter/sort indexes, possibly covered queries. | Minimal set of indexes supporting essential queries and constraints. |
| Risks | Wide and overlapping indexes, large working set. | Write amplification, contention, many indexes on frequently updated fields. |
| How to measure | Keys/docs examined, sort stages, read latency. | Writes/s, write latency, index size, cache, and I/O. |

**Read-heavy example:** A product catalog receives thousands of requests/second while product updates are rare; indexing by category, status, and price is well worth the storage cost.

**Write-heavy example:** Event ingestion writes tens of thousands of documents/second, queried mainly by `deviceId` and `timestamp`; `{ deviceId: 1, timestamp: -1 }` makes more sense than multiple indexes on rarely queried metadata.

**Mixed example:** Orders require a unique order code constraint, per-customer order history, and an operational dashboard by status; keep indexes serving critical queries, but avoid adding new indexes for every rarely run report.

There is no rule such as "every collection should have three indexes" or "at most ten indexes." Evaluate based on access patterns, data distribution, and the live system.

---

## 25. Decision Process Before Creating an Index

1. **Specify the query:** filters, sort, projection, limit, frequency, and p95/p99 targets.
2. **Inspect existing indexes:** `db.collection.getIndexes()`.
3. **Measure baseline:** `explain("executionStats")`, latency, and I/O under a representative workload.
4. **Select candidate index:** equality, sort, range, prefix, selectivity, multikey, and partial considerations.
5. **Estimate write cost:** how many inserts/updates/deletes the new index affects, and whether any field changes frequently.
6. **Assess size and cache:** expected index size and whether it competes with data for the working set.
7. **Roll out carefully:** account for index build cost, unique constraints, and replication.
8. **Re-measure:** query plan, keys/docs examined, sorts, read/write latency, throughput, storage, and cache.
9. **Observe across full cycles:** do not drop an index simply because it saw low usage over a short window.
10. **Document owner and purpose:** which endpoint uses the index, why the fields are ordered that way, and when to review it.

Example index governance record:

```text
Index name   : idx_customer_recent
Collection   : orders
Query        : GET /customers/{id}/orders
Filter       : customerId = ?
Sort         : createdAt DESC
Goal         : p95 below business SLA threshold
Trade-off    : additional disk usage and insert cost
Owner        : Order Service Engineering Team
```

---

## 26. Practice Exercises

### Exercise 1 — Choosing an Index for Order History

```javascript
db.orders.find({
  customerId: "C42"
}).sort({ createdAt: -1 }).limit(50);
```

**Question:** Single-field index on `customerId`, single-field index on `createdAt`, or a compound index?  
**Hint:** `{ customerId: 1, createdAt: -1 }` is the natural candidate because it filters by customer and then walks orders in chronological order.

### Exercise 2 — When an Index Is Not Selective Enough

98% of orders have `status = "COMPLETED"`.

```javascript
db.orders.find({ status: "COMPLETED" });
```

**Question:** Does creating `{ status: 1 }` guarantee every query run will be faster?  
**Hint:** No; the engine may still have to read nearly the entire collection. Measure selectivity and inspect the execution plan.

### Exercise 3 — Covered Query

Given index `{ customerId: 1, status: 1, createdAt: -1 }`:

```javascript
// A
db.orders.find(
  { customerId: "C01", status: "PAID" },
  { _id: 0, customerId: 1, status: 1, createdAt: 1 }
);

// B
db.orders.find(
  { customerId: "C01", status: "PAID" },
  { customerId: 1, status: 1, createdAt: 1, totalMinor: 1 }
);
```

**Hint:** A is more likely to be covered because it projects only indexed fields and excludes `_id`; B requests `totalMinor`, which is outside the index.

### Exercise 4 — Update Cost

Given an index containing `status`, but not `internalNote`:

```javascript
// A
db.orders.updateOne(
  { _id: "O1001" },
  { $set: { internalNote: "OK" } }
);

// B
db.orders.updateOne(
  { _id: "O1001" },
  { $set: { status: "SHIPPED" } }
);
```

**Hint:** B may need to update index keys; A typically leaves index keys unchanged, though it still writes the document.

### Exercise 5 — Index on a Large Array

A product has 1,000 tags and an index `{ tags: 1 }`.

**Task:** Explain why membership queries are supported, yet index size and the cost of adding/removing tags can increase. **Hint:** A multikey index can hold many entries per document.

### Exercise 6 — Partial Index

Only 2% of orders have `status = "OPEN"`; the operations endpoint typically filters by `customerId` and fetches the most recent ones.

```javascript
db.orders.createIndex(
  { customerId: 1, createdAt: -1 },
  { partialFilterExpression: { status: "OPEN" } }
);
```

**Question:** Why can this index be smaller than a full-collection index? Why can't a query not restricted to `OPEN` rely on this index by default to return complete results?

### Exercise 7 — Redundant Index?

A collection has `{ customerId: 1 }` and `{ customerId: 1, createdAt: -1 }`.

**Hint:** They may overlap, but before dropping one you should check query statistics, index options, size, usage frequency, and periodic batch reports.

### Exercise 8 — Slow Writes After Adding Indexes

An event-ingestion service has eight indexes, while queries primarily filter by `deviceId + timestamp`.

**Task:** Propose an investigation sequence: measure write latency, inspect index usage, check rare queries, test with hidden indexes where appropriate, re-measure, and only drop once confident it will not affect SLAs or data constraints.

---

## 27. Common Misconceptions

| Misconception | Correct understanding |
| --- | --- |
| "The more indexes, the faster the database." | Indexes only help matching queries while increasing write and storage costs. |
| "If an index exists, MongoDB will always use it." | The planner may pick COLLSCAN or a different index. |
| "Indexes only help WHERE, not sorting." | Key order can support sort and limit operations. |
| "Field order in a compound index does not matter." | Prefixes, ranges, and sorts depend on field order. |
| "ESR is always the only right order." | ESR is a guideline; data distribution can favor another order. |
| "Projecting few fields makes a query covered." | All projected fields must be satisfied by the index; check `_id` and the plan. |
| "Every index includes `_id`." | The default `_id` index does not put `_id` into other indexes. |
| "An array creates only one index entry." | A multikey index can create multiple entries per document. |
| "Indexes only affect reads/SELECTs." | INSERT, UPDATE, and DELETE must maintain affected indexes. |
| "Updating a non-indexed field writes nothing extra." | The document itself still changes and requires storage processing. |
| "DELETE has no index maintenance." | Indexes must reflect deleted documents. |
| "An index takes the same RAM as its on-disk size." | Working set, caching, and compression make those sizes differ. |
| "Boolean fields should never be indexed." | Selective predicates, rare values, and partial indexes can make them useful. |
| "An index unused today should be dropped right away." | It might serve periodic jobs or enforce data constraints. |
| "Hidden indexes save write overhead." | Hidden indexes are still maintained on writes. |
| "TTL deletes instantaneously with no cost." | TTL runs in the background and still generates deletes and index updates. |
| "With an index, returning 100,000 documents via an API is still fast." | Network transfer, decoding, and payload volume still consume resources. |

## 28. Summary

Indexes help MongoDB locate documents by key, scan targeted data ranges, leverage sort order, and occasionally return results directly from the index. Benefits are clearest for **selective queries, well-aligned filter + sort patterns, and frequently called endpoints**.

Each index is also a structure that must be maintained. **Inserts** create entries, **updates** to indexed keys can alter entries, and **deletes** remove entries; these operations consume additional memory, storage, and I/O. Unique, partial, multikey, and TTL indexes each carry their own cost rules or constraints.

Good index design aims for neither **the most** nor **the fewest** indexes. It selects an index set **sufficient** to satisfy queries and protect data integrity at a balanced read, write, and operational cost—validated through `explain()`, usage statistics, and real-world monitoring.

## 29. Official MongoDB Documentation

- [Indexes — MongoDB Manual](https://www.mongodb.com/docs/manual/indexes/): overview of index types.
- [Query Optimization](https://www.mongodb.com/docs/manual/core/query-optimization/): filters, sorts, and covered queries.
- [Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/): compound indexes and prefixes.
- [Equality, Sort, Range Guideline](https://www.mongodb.com/docs/manual/tutorial/equality-sort-range-guideline/): the ESR guideline.
- [Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/): indexing arrays.
- [Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/): indexing a filtered subset of documents.
- [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/): unique key constraints.
- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/): execution plans and metrics.
- [$indexStats](https://www.mongodb.com/docs/manual/reference/operator/aggregation/indexStats/): index usage statistics.
- [Hidden Indexes](https://www.mongodb.com/docs/manual/core/index-hidden/): evaluating impact without using an index.
- [Java Sync Driver — Indexes](https://www.mongodb.com/docs/drivers/java/sync/current/indexes/): creating indexes with the Java driver.

Details regarding the query planner, index builds, and explain output structure can vary across versions. Always cross-check against your actual MongoDB and driver versions during implementation.
