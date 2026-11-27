# Selectivity, Value Distribution, and Index Size in MongoDB

Creating indexes is one of the primary ways to speed up MongoDB queries. However, **having an index does not automatically make a query fast**, and **an index on a low-cardinality field is not always useless**. An index's effectiveness depends on the actual data: how many documents match the predicate, whether values are evenly distributed or skewed toward a few values, which fields lead a compound index, what sort order the query needs, and how much memory and disk space the index itself consumes.

This lesson belongs to the **Basic Indexes** chapter and focuses on three tightly connected concepts:

1. **Selectivity**: how strongly a query predicate narrows down the document set.
2. **Value distribution**: whether field values occur evenly or skew heavily.
3. **Index size**: how index data and structures consume resources, affecting reads, writes, and operations.

The goal is to explain why the same index can be effective for one query yet ineffective for another, and to use `explain()`, collection statistics, and real query patterns to guide index design decisions.

## 1. Recap: What Problem Do Indexes Solve?

In a MongoDB collection, documents are not stored in an order tailored to every query. To find orders where `customerId: "C001"`, MongoDB may have to inspect many documents without an appropriate index.

A standard index stores **index keys** along with references locating the documents. When a predicate can exploit index ordering, MongoDB seeks to a key range and reads only the relevant entries instead of scanning the entire collection.

```text
Collection orders:
  [doc 1] [doc 2] [doc 3] ... [doc 100000]
      \       |       /             |
       \      |      /              |
        +-----+-----+----------------+
              |
     Index on customerId
      "C001" -> matching documents
      "C002" -> matching documents
      "C003" -> matching documents
         ...
```

Example index creation:

```javascript
db.orders.createIndex(
  { customerId: 1 },
  { name: "idx_customerId" }
)
```

`1` indicates ascending order for that field in the index. MongoDB automatically creates an index on `_id` for standard collections; other indexes should be designed from real queries.

**An index is not a full copy of the collection.** For queries needing fields absent from the index, the server may still have to fetch the original documents (commonly shown as a `FETCH` stage in plans). An index pays off when the cost of locating and retrieving results is lower than alternative plans.

## 2. Selectivity: How Many Documents Match the Filter?

Suppose the `orders` collection has `N = 100,000` documents.

- Predicate `{ customerId: "C001" }` matches 4 documents.
- Predicate `{ status: "delivered" }` matches 90,000 documents.
- Predicate `{ status: "cancelled" }` matches 1,000 documents.

To express this intuitively, use the **match rate**:

\[
\text{matchRate}(q)
= \frac{\text{number of documents matching predicate } q}
        {\text{total number of documents considered}}.
\]

For the examples above:

| Predicate | Matches / 100,000 | Match rate | Result-set reduction |
| --- | ---: | ---: | --- |
| `customerId = "C001"` | 4 | 0.004% | Very strong |
| `status = "cancelled"` | 1,000 | 1% | Fairly strong |
| `status = "delivered"` | 90,000 | 90% | Very weak |

Commonly, a query matching **few documents** is called **highly selective**; a query matching most of the collection has **low selectivity**.

Terminology note: some sources define *selectivity* using the exclusion ratio or distinct-value ratio, so higher vs. lower values may flip meaning. Throughout this lesson, we always refer to `matched / total` as the **match rate**: **the lower the match rate, the more selective the predicate**.

### 2.1. Why Does Selectivity Affect Indexes?

For a predicate matching very few documents, an index usually lets MongoDB skip reading most of the collection:

```javascript
db.orders.find({ customerId: "C001" })
```

If a value appears in nearly every document:

```javascript
db.orders.find({ status: "delivered" })
```

then walking an index and fetching vast numbers of source documents may perform no better than scanning the collection—especially when returning many unindexed fields. The MongoDB query planner weighs viable plans; **there is no fixed threshold** where a 1% match rate always uses an index and 50% always skips it.

Execution plans also depend on projections, sorts, limits, existing indexes, statistics, and how data sits on disk and in memory.

### 2.2. Selectivity Is a Property of the Predicate, Not Just the Field

The `status` field may have very few distinct values, yet:

```javascript
db.orders.find({ status: "cancelled" })
```

can be far more selective than:

```javascript
db.orders.find({ status: "delivered" })
```

Even though both query the same field and share the `{ status: 1 }` index, differing match counts change how valuable the index is. Hence, never judge an index solely from **field names** or theoretical value counts.

## 3. How Does Cardinality Differ from Selectivity?

**Cardinality** of a field typically refers to the **number of distinct values** present in the dataset under review. For example:

- `status` has only `"pending"`, `"delivered"`, `"cancelled"` → roughly 3 distinct values.
- `customerId` spans tens of thousands of distinct customers → higher cardinality.
- `_id` is unique → every document has its own key within the collection.

High cardinality **usually creates opportunities** for selective equality lookups, yet it does not mean all values appear equally often.

| Field | Illustrative cardinality | What else to check |
| --- | --- | --- |
| `isActive` | 2 | Does `true` account for 99.9%? |
| `status` | 3–10 | How many documents does each status hold? |
| `region` | A few dozen | Does one region dominate the records? |
| `customerId` | Thousands / millions | Does one mega-customer generate most orders? |
| `_id` | Close to document count | Do queries actually filter by `_id`? |

### 3.1. Uniform vs. Skewed Distribution Examples

Two collections both have a `status` field with three values, but different distributions:

```text
Collection A (fairly uniform):
  pending     33%
  delivered   34%
  cancelled   33%

Collection B (heavily skewed):
  pending      8%
  delivered   90%
  cancelled    2%
```

Both have **cardinality = 3**, yet in Collection B, querying `status: "cancelled"` touches only ~2% of documents whereas `status: "delivered"` touches ~90%.

Therefore:

> Cardinality describes how many distinct values exist; distribution describes how often each value occurs; selectivity describes how tightly a specific predicate narrows the result set.

### 3.2. High-Cardinality Fields Can Still Be Skewed

An e-commerce platform might have a "system account" generating 300,000 orders while thousands of ordinary customers have only a few each. `customerId` still has high cardinality, yet querying by the system account's ID is nowhere near as selective as querying by a typical customer's ID.

Index design should be grounded in **workload** and **actual value frequencies**, not solely in schema structure or a distinct-value count.

## 4. Practice: Creating a Skewed Dataset

Open `mongosh` and select a dedicated database:

```javascript
use mongo_index_lab
```

The script below generates 100 orders with a skewed `status` distribution. Run it on a fresh or empty `orders` collection:

```javascript
const sampleOrders = Array.from({ length: 100 }, (_, i) => ({
  _id: i + 1,
  customerId: "C" + String((i % 50) + 1).padStart(3, "0"),
  status: i < 90
    ? "delivered"
    : (i < 98 ? "pending" : "cancelled"),
  createdAt: new Date(Date.UTC(2026, 0, 1) + i * 60000),
  amount: 100 + (i % 10) * 10,
  tags: i % 3 === 0 ? ["mobile", "sale"] : ["web"]
}));

db.orders.insertMany(sampleOrders);
```

Resulting breakdown:

| `status` value | Documents | Percentage |
| --- | ---: | ---: |
| `delivered` | 90 | 90% |
| `pending` | 8 | 8% |
| `cancelled` | 2 | 2% |
| **Total** | **100** | **100%** |

Each `customerId` from `C001` to `C050` has two orders, so an equality filter on a single customer matches 2/100 documents in this dataset.

Fixed `_id` values are purely illustrative; running `insertMany()` repeatedly on the same collection triggers duplicate key errors. Never run `drop()` on a collection containing production data to restart an exercise.

### 4.1. Counting Value Frequencies with Aggregation

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
])
```

The output returns three groups with counts 90, 8, and 2. This is how you inspect value distribution rather than guessing from field names.

Check a specific predicate:

```javascript
const total = db.orders.countDocuments({});
const cancelled = db.orders.countDocuments({ status: "cancelled" });
const byCustomer = db.orders.countDocuments({ customerId: "C001" });

printjson({
  total,
  cancelled,
  cancelledMatchRate: cancelled / total,
  byCustomer,
  customerMatchRate: byCustomer / total
});
```

On the sample data: `cancelledMatchRate = 0.02`, `customerMatchRate = 0.02`. On real production datasets, exact counts can be resource-intensive, especially on large collections; avoid running heavy counts repeatedly on a loaded system.

### 4.2. Finding the Most Frequent Values

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$customerId",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1, _id: 1 } },
  { $limit: 10 }
])
```

In this sample dataset, each customer has exactly two orders; in practice, this aggregation spots customers or groups holding an **unusually large share of records**. Data distribution over time should also be revisited: promotions, bulk imports, seasonality, or business changes can shift distributions over time.

## 5. Comparing High-Selectivity and Low-Selectivity Queries

Create a single-field index on `status`:

```javascript
db.orders.createIndex(
  { status: 1 },
  { name: "idx_status" }
)
```

Now compare two predicates:

```javascript
// Matches 2/100 documents
db.orders.find({ status: "cancelled" })

// Matches 90/100 documents
db.orders.find({ status: "delivered" })
```

The first query has a **lower match rate** and can typically leverage the index to shrink the search scope. The second returns most of the collection, so even with the index present, the query planner may find a collection scan more sensible in certain situations.

Still, with only 100 documents, the entire dataset fits comfortably in cache, so speed and plans may not show dramatic differences. **Never infer from a tiny test that an index will definitely win or lose in production.**

### Projections Also Affect Cost

Compare:

```javascript
// Needs full documents, may read many source documents
db.orders.find({ status: "delivered" })

// Needs only certain fields
db.orders.find(
  { status: "delivered" },
  { _id: 0, status: 1 }
)
```

If every filtered and returned field resides in the index and other rules allow, the query can be **covered** by the index, avoiding original document reads. Hence a predicate matching many documents can still benefit when the index handles most of the work and the query returns only indexed keys.

This is another reason not to judge index effectiveness from selectivity alone.

## 6. Compound Indexes: Combining Conditions to Boost Efficiency

A field with few distinct values can become quite useful inside a **compound index** alongside other fields.

For example, a screen showing "pending orders for customer C001, newest first":

```javascript
db.orders.find({
  customerId: "C001",
  status: "pending"
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
```

You can design the index:

```javascript
db.orders.createIndex(
  {
    customerId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  { name: "idx_customer_status_created_id" }
)
```

Visualizing the path:

```text
customerId = C001
        |
        v
status = pending
        |
        v
createdAt descending, _id descending
        |
        v
Take at most the first 20 documents
```

When equality predicates narrow the leading part of the index and trailing keys align with `sort`, MongoDB can filter and read results in the desired order simultaneously. This is often more effective than creating standalone `{status: 1}` or `{createdAt: -1}` indexes.

### 6.1. Field Order in a Compound Index Matters

Two indexes:

```javascript
{ customerId: 1, status: 1, createdAt: -1 }
{ createdAt: -1, customerId: 1, status: 1 }
```

are not equivalent in which query shapes they support. With equality on `customerId` and `status`, the first index groups orders by those keys before ordering by time. The second orders globally by time first and may have to scan many entries to locate the right customer.

A common design guideline is **Equality – Sort – Range (ESR)**:

1. Place equality-filtered fields first.
2. Place `sort` fields next.
3. Place range-filtered fields (`$gt`, `$gte`, `$lt`, `$lte`) last.

This is a **design guideline**, not an immutable rule. In some workloads, a highly selective range may merit priority; whether an index serves a sort depends on key order and preceding conditions. Always measure with real queries.

### 6.2. Do Not Multiply Match Rates Mechanically

Suppose:

- `status: "pending"` matches 8%.
- `customerId: "C001"` matches 2%.

You cannot always assume the combined predicate matches `8% * 2% = 0.16%`. Multiplying them assumes the two fields are statistically independent, which often fails in reality. One customer might have only pending orders or zero pending orders.

When designing indexes, examine the **joint distribution** of fields: which group intersections queries actually filter, how many documents match, and how they are distributed over time.

### 6.3. Prefixes of a Compound Index

Index:

```javascript
{ customerId: 1, status: 1, createdAt: -1 }
```

can generally support predicates on the **prefix** `customerId`, or `customerId` plus `status`. It is not equivalent to a single-field index on `status` for all queries:

```javascript
db.orders.find({ status: "pending" })
```

lacks an equality predicate on the leading `customerId` field. MongoDB can still scan an index in certain cases, yet you should not rely on this index to efficiently serve standalone `status` queries.

## 7. How Does Data Distribution Affect the Query Planner?

The MongoDB query planner chooses among viable plans based on the query and existing indexes. For the exact same query shape with different parameter values, matching data volume can vary widely:

```javascript
db.orders.find({ status: "delivered" })
db.orders.find({ status: "cancelled" })
```

In systems using a plan cache, reusing a plan across similar executions can make performance sensitive to parameter distributions and data state. Never claim a single plan is optimal across every parameter value.

Distribution effects also show clearly with:

- **Range queries**: `amount: {$gte: 100}` may match most orders, while `amount: {$gte: 100000}` is rare.
- **Time filters**: "last 7 days" can hold many or few documents depending on ingestion rate.
- **Null or missing heavy distributions**: optional fields present in only a fraction of the collection.
- **Multi-tenant data**: one large tenant can hold the majority of documents while others are tiny.
- **Multivalue arrays**: one document generates multiple index keys, changing index key counts and scan costs.

When workloads are heavily skewed, test **common values**, **rare values**, and **typical mid-range values**, rather than running `explain()` on a single arbitrary ID.

## 8. Observing Index Behavior with `explain("executionStats")`

A practical way to evaluate index effectiveness is comparing plans and execution stats for specific queries:

```javascript
db.orders.find({ status: "cancelled" })
  .explain("executionStats")

db.orders.find({ status: "delivered" })
  .explain("executionStats")
```

With a compound index:

```javascript
db.orders.find({
  customerId: "C001",
  status: "pending"
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats")
```

Metrics to watch:

| Field | Meaning when interpreting |
| --- | --- |
| `nReturned` | Number of documents actually returned by the explained query |
| `totalKeysExamined` | Number of index key entries examined during execution |
| `totalDocsExamined` | Number of documents examined during document-reading stages |
| `executionTimeMillis` | Reported execution time in the measurement environment |
| `winningPlan` | Plan selected to execute the query |
| `IXSCAN` | An index scan stage in the corresponding plan representation |
| `COLLSCAN` | A collection scan stage |
| `FETCH` | A stage retrieving source documents |
| `SORT` | Indicates an explicit sort stage in the plan |
| `indexBounds` | Index key ranges traversed where applicable |

Stage names and field nesting can vary across MongoDB versions and execution engines. In particular, never expect every plan to show one fixed stage tree.

### 8.1. What Indicates Effective Index Filtering?

Example query returning 10 documents:

```text
Case A:
  nReturned          = 10
  totalKeysExamined  = 12
  totalDocsExamined  = 10

Case B:
  nReturned          = 10
  totalKeysExamined  = 100000
  totalDocsExamined  = 10000
```

In this hypothetical example, Case A touches far fewer entries. Case B may be scanning a wide key range, using a mismatched index, or post-filtering many documents.

However, **there is no single `keysExamined / nReturned` threshold that holds for every query**. For example:

- A `limit(10)` query may stop early after 10 matches, masking the full set's scan cost.
- A multikey index can hold multiple keys per document.
- Aggregations, sorts, or deep pagination may legitimately traverse many entries.
- A covered query can show `totalDocsExamined = 0` while still scanning index keys.

Compare metrics against **the query's goal**, collection size, and alternative plans rather than judging one metric in isolation.

### 8.2. Using `hint()` to Inspect a Specific Index

Example:

```javascript
db.orders.find({ status: "cancelled" })
  .hint("idx_status")
  .explain("executionStats")
```

`hint()` instructs MongoDB to use the named index when valid instead of letting the query planner pick normally. This is helpful when **studying** an index's plan, though stats from a hinted run do not by themselves prove it is optimal for the overall workload.

Do not hardcode `hint` into production application code without concrete justification and measurements; indexes can be dropped or modified, data distributions shift, and a pinned hint can degrade over time.

## 9. What Makes Up Index Size?

An index must store **keys**, **key-organization structures**, and pointers linking back to documents. For standard indexes, MongoDB uses an ordered structure suited to key lookups and specific filter/sort patterns.

Actual index size is influenced by:

1. **Document count and index entry count**: more indexed entries generally produce larger indexes.
2. **Key types and lengths**: long strings take more bytes than short numeric values; BSON encoding affects storage.
3. **Number of fields in a compound index**: each key encodes more components, though compression reduces actual cost.
4. **Indexed arrays (multikey)**: one document can produce multiple index entries.
5. **Index type**: standard B-tree, text, wildcard, hashed, geospatial, and others carry different storage overheads.
6. **Collation**: locale-aware collation indexes store different key representations than simple binary collation.
7. **Compression and storage layout**: on WiredTiger, compression algorithms, prefix compression, page structures, and metadata overhead affect measured size.
8. **Insert/update/delete churn and storage fragmentation**: observed size is not purely the sum of current value lengths.

For these reasons, you cannot accurately compute `indexSize = document count × single key size` with simple multiplication. That formula ignores overhead, encoding, compression, multikey expansion, and page allocation.

### 9.1. What Do Large Indexes Impact?

| Resource | Potential impact |
| --- | --- |
| Disk storage | Indexes occupy additional space beyond collection data |
| Cache memory | Frequently accessed index pages compete for cache space with data and other indexes |
| Reads | Well-fitted indexes reduce entries scanned; oversized or poorly matched indexes increase I/O and cache misses |
| Writes | Inserts, updates, and deletes must maintain affected indexes |
| Index builds | Building indexes consumes time and resources, impacting live system load |
| Backup/restore & operations | Total data volume and index structures affect operational duration depending on backup mechanics |

**An index taking disk space does not mean the entire index must reside in RAM.** MongoDB/WiredTiger caches accessed pages; what matters is the size and access pattern of the **working set** (frequently used data and index pages) relative to available memory/cache.

## 10. Measuring Index and Collection Size

In `mongosh`, you can run:

```javascript
db.orders.stats()
```

Output includes fields such as `count`, `size`, `storageSize`, `totalIndexSize`, `indexSizes`, and `nindexes` on supported versions. Exact field names and formatting may vary by version, with these core meanings:

| Field | Information |
| --- | --- |
| `count` | Number of documents in the collection at stats time |
| `size` | Logical data size reported by collection stats |
| `storageSize` | Storage space allocated for collection document data |
| `nindexes` | Number of indexes on the collection |
| `totalIndexSize` | Total storage size of all indexes per stats |
| `indexSizes` | Size breakdown per index name |

Example reading selected fields without printing all metadata:

```javascript
const s = db.orders.stats();
printjson({
  count: s.count,
  dataSizeBytes: s.size,
  dataStorageBytes: s.storageSize,
  totalIndexBytes: s.totalIndexSize,
  indexes: s.indexSizes
});
```

Do not treat `size`, `storageSize`, and `totalIndexSize` as interchangeable quantities. Logical data size, allocated document storage, and index storage reflect different layers.

### 10.1. Reading Sizes in MiB

```javascript
const stat = db.orders.stats();
const toMiB = bytes => bytes / (1024 * 1024);

print("Logical data: " +
  toMiB(stat.size).toFixed(2) + " MiB");
print("Data storage: " +
  toMiB(stat.storageSize).toFixed(2) + " MiB");
print("Total indexes: " +
  toMiB(stat.totalIndexSize).toFixed(2) + " MiB");
```

This simply **converts bytes** for readability. Numbers change after writes, deletes, or index builds. In a 100-document lab collection, sizes are tiny and do not represent costs at millions of documents.

### 10.2. Inspecting Existing Indexes

```javascript
db.orders.getIndexes()
```

`getIndexes()` describes index configurations such as names, key patterns, `unique`, `partialFilterExpression`, or `hidden` where present; it does not replace `indexSizes` in collection stats.

Statistics commands may require appropriate privileges; never run index modifications or drops "just to test" on a live production database.

### 10.3. `$indexStats` Measures Usage, Not Size

```javascript
db.orders.aggregate([
  { $indexStats: {} }
])
```

The `$indexStats` stage reports index usage on the target node, typically listing index names and `accesses` counters. This usage data shows which indexes are queried; **it is not index byte size** and does not replace `indexSizes`.

Usage counters are scoped per node/process or since the index was rebuilt depending on deployment; low counts do not prove an index is redundant, especially if it serves rare critical workloads, unique constraints, or scheduled batch jobs.

## 11. Multikey Indexes and How Arrays Affect Size

Suppose each product has multiple tags:

```javascript
{
  _id: "p01",
  tags: ["mongodb", "database", "backend"]
}
```

Create an index:

```javascript
db.products.createIndex(
  { tags: 1 },
  { name: "idx_tags" }
)
```

Because `tags` is an array, this becomes a **multikey index**: one document with multiple elements can contribute multiple index key entries instead of just one.

```text
Document p01:
  tags = ["mongodb", "database", "backend"]

Index on tags (illustrative key mapping):
  "backend"  -> p01
  "database" -> p01
  "mongodb"  -> p01
```

If each document contains an array of hundreds of elements, index entry counts can grow substantially. The index can become far larger than an index on a short scalar field across the same document count.

**Never assume** a document with an N-element array always generates exactly N index entries: duplicate values, encoding, and index build rules affect final key counts. Compound multikey indexes also carry specific restrictions; combining multiple array fields into one compound index is not always valid.

Example query:

```javascript
db.products.find({ tags: "mongodb" })
```

The `tags` index helps find products containing that element. When reading `totalKeysExamined`, remember that index entries can outnumber matching documents due to multikey expansion.

### Dots in Nested Field Paths

Indexes can also target nested fields:

```javascript
db.products.createIndex(
  { "seller.country": 1 },
  { name: "idx_seller_country" }
)
```

Selectivity still depends on **the actual predicate**: `country: "VN"` may be common, while a country with very few sellers may be rare. Nesting a field inside an object does not automatically make its index more selective.

## 12. Compound Index Size and Covered Query Benefits

A compound index holds multiple key components and therefore consumes more storage:

```javascript
db.orders.createIndex(
  { customerId: 1, createdAt: -1, status: 1 },
  { name: "idx_customer_date_status" }
)
```

In return, this index can support filtering, sorting, and projection under suitable conditions:

```javascript
db.orders.find(
  { customerId: "C001" },
  {
    _id: 0,
    customerId: 1,
    createdAt: 1,
    status: 1
  }
)
  .sort({ createdAt: -1 })
```

When every filtered, sorted, and returned field lives in the index, the query can run as a **covered query**, avoiding source document fetches. In qualifying plans, `totalDocsExamined` can be 0.

However, `{customerId:1,createdAt:-1,status:1}` cannot cover a query that also requests `amount` if `amount` is absent from the index:

```javascript
db.orders.find(
  { customerId: "C001" },
  { _id: 0, customerId: 1, createdAt: 1, amount: 1 }
)
  .sort({ createdAt: -1 })
```

MongoDB may have to read the source documents to fetch `amount`. Adding `amount` to the compound index **could** eliminate document reads for this query, yet it also enlarges the index and raises maintenance costs. Avoid stuffing every display field into an index just to get a covered query on a rarely visited screen.

### Watch Out for `_id` in Projections

MongoDB returns `_id` by default unless explicitly excluded. If `_id` is absent from the active index, returning `_id` prevents the query from being covered. In the example above, `_id: 0` was an intentional choice.

Covered queries also have restrictions around index types, multikey arrays, collations, and filter syntax. Always verify with `explain()` rather than inferring purely from a field list.

## 13. Shrinking Index Size by Choosing the Right Scope

Not every document needs to appear in every index. Within MongoDB's supported limits, a **partial index** indexes only documents matching a specified condition.

For example, suppose the system frequently queries `pending` orders by customer and timestamp, while most orders are already `delivered`:

```javascript
db.orders.createIndex(
  { customerId: 1, createdAt: -1 },
  {
    name: "idx_pending_customer_createdAt",
    partialFilterExpression: {
      status: "pending"
    }
  }
)
```

This index stores keys only for documents matching `status: "pending"`, instead of the whole collection. On our sample dataset, that is 8/100 documents.

Qualifying query:

```javascript
db.orders.find({
  customerId: "C041",
  status: "pending"
})
  .sort({ createdAt: -1 })
```

Because the query filter **entails the partial condition** `status: "pending"`, the index is an eligible candidate.

Conversely:

```javascript
db.orders.find({ customerId: "C041" })
```

cannot rely on this partial index to return all orders for C041, because `delivered` and `cancelled` documents are missing from the index. The query planner must preserve result correctness.

### When Is a Partial Index Worth Considering?

- Queries primarily target a **small, well-defined subset** based on business state.
- Query predicates consistently **specify or entail** the partial index condition.
- Reducing indexed entries saves meaningful storage and maintenance overhead compared to a full index.

However, if status frequently transitions from `pending` to `delivered`, the system still has to update the index as documents enter or leave the indexed subset. Partial indexes do not mean "zero write cost."

Sparse indexes can also omit documents missing the indexed field, yet sparse and partial semantics differ. Never substitute `sparse: true` for a partial filter when business logic intends to exclude a specific status value.

## 14. Trade-Offs Between Read Performance, Write Cost, and Storage

An index that dramatically helps a rare query still incurs ongoing operational costs.

When inserting a document:

```javascript
db.orders.insertOne({
  _id: 201,
  customerId: "C201",
  status: "pending",
  createdAt: new Date(),
  amount: 250
})
```

MongoDB must maintain all indexes covering the new document. When updating an indexed field—such as changing `status`—affected index entries may need updating. When deleting a document, its index entries must also be removed.

Thus, creating 10 indexes might speed up various reads while inflating total index size and write work compared to 2–3 well-targeted indexes. This is a **trade-off**, not a fixed rule about a maximum number of indexes.

### Decision-Making Scenario

Suppose a collection holds 5 million orders with this `status` distribution:

```text
delivered: 4,700,000
pending:     250,000
cancelled:    50,000
```

Primary workloads:

1. Most requests fetch orders for a specific `customerId`, newest first.
2. An admin dashboard inspects `pending` orders chronologically.
3. Monthly reports read millions of `delivered` orders.

One sensible approach:

- Prioritize a compound index leading with `customerId`, followed by date/sort keys, for workload 1.
- Consider an index on `status` and `createdAt`, or a partial index on `pending`, for workload 2.
- Do not automatically add a single-field `{status:1}` index just because report 3 filters on `delivered`; the report may need to scan huge numbers of documents regardless of the index. Inspect actual plans and choose an appropriate reporting strategy.

The best choice depends on query frequency, target latency, storage footprint, write rate, and hardware resources. A sort-supporting index can still be worthwhile even when filter selectivity is modest, especially with small `limit` values.

## 15. Evaluation Workflow Before Adding an Index

A basic, repeatable workflow suitable for operational runbooks:

**Step 1 — Document the query shape.**

```javascript
db.orders.find({
  customerId: "C001",
  status: "pending"
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
```

Record the full filter, sort, limit, projection, and typical parameter values. An index designed for a query missing `sort` may fail to serve the real query properly.

**Step 2 — Inspect value distributions and match rates.**

Measure appropriately on a representative dataset; check common and rare values, large vs. small tenants, peak periods, and `null`/missing values.

**Step 3 — Check existing indexes.**

```javascript
db.orders.getIndexes()
```

Avoid creating an index nearly identical to an existing compound index that already serves the workload unless it brings clear, measurable gains.

**Step 4 — Measure a baseline.**

```javascript
db.orders.find({
  customerId: "C001",
  status: "pending"
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats")
```

Record `totalKeysExamined`, `totalDocsExamined`, plan stages, and timing. Note dataset and version context so subsequent measurements remain comparable.

**Step 5 — Choose a sensible index.**

Evaluate positions of equality, sort, and range fields, prefix reuse, selectivity, and covered query needs. Consider single-field, compound, or partial indexes depending on workload.

**Step 6 — Measure after the change in a suitable environment.**

Re-run the query using both common and rare parameter values, inspecting plans and write impact. Never rush multiple indexes into production based solely on tiny test datasets.

**Step 7 — Monitor storage footprint and usage.**

```javascript
const stats = db.orders.stats();
printjson(stats.indexSizes);

db.orders.aggregate([
  { $indexStats: {} }
]);
```

Combine these figures with memory, cache, throughput, latency, and write metrics. `$indexStats` has measurement-scope limits, so never drop an index solely because access counts look low over a short window.

**Step 8 — Revisit as workloads evolve.**

Distributions are not static: adding a huge customer, a new status, or a new search screen can alter index priorities. Review periodically rather than treating indexes as "create once and forget."

## 16. Common Misconceptions

| Misconception | Why it is wrong | Correct understanding |
| --- | --- | --- |
| "An index on a 2-value field is always useless" | One value may be rare; the index can also support sorts or partial queries | Inspect per-value distributions and query shapes |
| "High cardinality means every equality lookup is fast" | Skewed distributions can leave one value matching huge sets | Check actual frequencies of queried values |
| "If 90% of documents match, an index is always slower" | Covered queries, sorts, and limits alter cost | Inspect actual plans and execution stats |
| "Indexes speed up queries with zero trade-offs" | Indexes take storage and require write maintenance | Evaluate reads, writes, and storage together |
| "`indexSize = N × keySize` is exact" | Ignores compression, overhead, multikey, and page layout | Measure via `stats()` rather than simple multiplication |
| "`{a:1,b:1}` serves all queries on `b` efficiently" | `b` is not a leading prefix of the index | Check prefix rules and query shapes |
| "Index key count equals document count" | Multikey arrays can generate multiple keys per document | Check `totalKeysExamined` and index type |
| "If an index exists, it will always be chosen" | The planner may pick COLLSCAN or a different plan | Inspect the actual `winningPlan` |
| "Add lots of fields so every query is covered" | Inflates index size and write cost for limited gain | Add fields selectively for high-value workloads |
| "A partial index can serve any query" | It holds only documents matching its partial filter | Queries must guarantee no results are missed |
| "`$indexStats` shows index byte size" | It primarily reports access statistics | Use `indexSizes`/`totalIndexSize` for storage size |
| "An entire index must fit in RAM" | The engine caches active pages / working set | Track working-set access patterns, not just total size |
| "A 100-document test proves production gains" | Tiny datasets and warm caches differ vastly from production | Benchmark on representative volumes and parameter mixes |

## 17. Practice Exercises

### Exercise 1. Calculating Match Rate and Evaluating Selectivity

A collection has 200,000 documents:

- `status: "complete"` matches 170,000 documents.
- `status: "failed"` matches 2,000 documents.
- `customerId: "C017"` matches 5 documents.

Calculate the match rate of each predicate and rank them from highest to lowest selectivity.

**Answer:**

| Predicate | Match rate | Selectivity |
| --- | --- | --- |
| `customerId = "C017"` | 5 / 200,000 = 0.0025% | Highest |
| `status = "failed"` | 2,000 / 200,000 = 1% | High |
| `status = "complete"` | 170,000 / 200,000 = 85% | Low |

This evaluates result-set narrowing, **not** a guarantee of which index the planner will pick for every query.

### Exercise 2. Cardinality and Distribution

Two collections both have an `isActive` field with values `true` and `false`:

- Collection A: `true = 50%`, `false = 50%`.
- Collection B: `true = 99.9%`, `false = 0.1%`.

Does cardinality differ? How does `isActive: false` differ in selectivity?

**Answer:** Cardinality is 2 in both collections. However, `isActive: false` matches 50% in A versus only 0.1% in B, making the predicate far more selective in B. Whether an index is used still depends on query shape and execution cost.

### Exercise 3. Choosing an Index for a Combined Query

An application routinely queries:

```javascript
db.orders.find({
  customerId: "C008",
  status: "pending"
})
  .sort({ createdAt: -1 })
  .limit(10)
```

Propose a compound index.

**Reference answer:**

```javascript
db.orders.createIndex(
  { customerId: 1, status: 1, createdAt: -1 },
  { name: "idx_customer_status_created" }
)
```

Both equality fields lead; `createdAt` provides chronological ordering within the filtered group. Verify effectiveness with `explain()` on real data; if deterministic tie-breaking on identical `createdAt` values is needed, add `_id` to the sort and consider updating the index accordingly.

### Exercise 4. Distinguishing Data Size from Index Size

Collection stats report:

```text
size           = 800 MiB
storageSize    = 500 MiB
totalIndexSize = 320 MiB
```

What can you conclude, and what should you not conclude?

**Answer:** `size` reflects logical data size, `storageSize` reflects allocated/reported document storage, and `totalIndexSize` reflects reported index storage. Do not add all three together as three separate copies of the same data; nor should you assume all 320 MiB of indexes must permanently stay resident in RAM.

### Exercise 5. Arrays and Multikey Indexes

Compare:

```javascript
{ _id: 1, tags: ["a"] }
{ _id: 2, tags: ["a", "b", "c", "d"] }
```

With `{tags:1}`, why can the second document contribute more index entries?

**Answer:** `tags` is an array, so a multikey index can create index keys for multiple distinct elements within a single document. Index size does not necessarily scale linearly with document count alone. Actual entry counts also depend on deduplication rules and index structure.

### Exercise 6. Partial Indexes and Result Completeness

Given the partial index:

```javascript
db.orders.createIndex(
  { customerId: 1, createdAt: -1 },
  {
    partialFilterExpression: { status: "pending" },
    name: "idx_pending_only"
  }
)
```

Why can't `find({customerId:"C001"})` treat this index as a complete source for all of the customer's orders?

**Answer:** Because the index contains only documents with `status: "pending"`. Using it as a complete source for a query without a status filter would omit `delivered` and `cancelled` orders. This index fits queries that combine `status: "pending"` with the customer filter.

### Exercise 7. Interpreting `explain` Metrics

Two plans for the same query show these hypothetical statistics:

```text
Plan A: nReturned=20, totalKeysExamined=24,
        totalDocsExamined=20
Plan B: nReturned=20, totalKeysExamined=80000,
        totalDocsExamined=7000
```

Which plan shows signs of more selective filtering based on items examined?

**Answer:** Plan A examines far fewer keys and documents to return the same 20 results. Still, in a real environment you must also weigh execution time, cache state, sorting, index size, write frequency, and representative data.

## 18. Conclusion

**Selectivity**, **value distribution**, and **index size** must always be evaluated together:

- **Selectivity** answers: how much does a specific predicate narrow the result set?
- **Value distribution** answers: how widely do common and rare values differ within the same field?
- **Index size** answers: how much storage, cache, and write-maintenance cost does the system pay to accelerate critical queries?

The practical rule is **design indexes for real queries and real values**, not merely for field structures. Whenever assessing an index, ask how many documents it filters out, whether it supports sort/limit/projection, how skew and multikey expansion affect it, and whether read gains justify storage and write overhead. Use `explain("executionStats")`, `db.collection.stats()`, `getIndexes()`, and index access statistics to make evidence-based decisions, and keep re-evaluating as workloads evolve.
