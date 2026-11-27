# Balancing Index Count, Read Speed, Write Speed, and Storage

MongoDB uses **indexes** to reduce the number of documents examined during queries, support predicate filtering, sorting, uniqueness enforcement, and specialized features. Indexes can make read APIs dramatically faster, yet they are **not free**: they must be stored, maintained on data changes, occupy cache memory, and add operational and deployment complexity.

A system with dozens of indexes per collection is not necessarily faster than one with a few indexes tailored to the workload. Conversely, dropping all indexes to speed up writes typically turns critical queries into collection scans, spiking CPU, I/O, and tail latency.

This lesson—**"Balancing Index Count, Read Speed, Write Speed, and Storage"** in the **Performance Tuning** chapter—focuses on finding the **balance** among four dimensions:

1. **Index count and structure:** what requirement does each index serve, and are there duplicates or overlaps?
2. **Read speed:** do critical queries use indexes effectively and meet SLOs?
3. **Write speed:** how much overhead does index maintenance add to inserts, updates, deletes, and replication?
4. **Storage:** how much disk, WiredTiger cache, backup/restore footprint, and infrastructure cost do indexes consume?

The ultimate goal is **designing a minimal yet sufficient index set** that satisfies queries and business constraints at an acceptable write and storage cost.

> **There is no fixed "optimal index count" for every collection.** The right number depends on read/write ratio, query shapes, selectivity, sort orders, collection size, value distribution, index types, and latency/cost targets. Decisions must be based on measured data, not raw index counting.

---

## 1. Big Picture: What Does an Index Help and What Does It Cost?

Suppose an `orders` collection holds 20 million documents. An API frequently runs:

```javascript
db.orders.find({
  tenantId: "TENANT-A",
  status: "PAID"
})
.sort({ createdAt: -1 })
.limit(20);
```

Without a suitable index, MongoDB may scan many documents and perform an expensive sort. A compound index:

```javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
```

can filter by tenant and status, read entries in `createdAt` order, and stop early with `limit`.

However, when creating a new order, MongoDB must write the document **and** maintain corresponding keys across indexes. When deleting an order, keys must be removed. When updating `status`, an index containing `status` typically replaces the old key with the new key.

Summary:

```text
                           MongoDB Collection
                                  │
                     ┌────────────┴────────────┐
                     │                         │
                Read queries             Write operations
                     │                         │
                Index lookup             Document change
                     │                         │
         Fewer docs examined         Update index keys
         Efficient sort/limit        Journal, cache, I/O
                     │                         │
              Read latency ↓           Write cost ↑
                     └────────────┬────────────┘
                                  │
                           Disk + RAM
                          + operations
```

An index is worth creating when **measurable benefits** outweigh **additional costs** across the full workload and data constraints.

### 1.1. Measurable Benefits

- Fewer documents examined.
- Fewer keys examined, or keys aligned with query range.
- Avoids collection scans on critical read paths.
- Avoids blocking sorts or lowers sort cost.
- Allows early termination with `limit`.
- Enables serving certain queries entirely from the index (*covered queries*).
- Lowers p50/p95/p99 read latency.
- Reduces CPU and disk reads.
- Enforces business invariants via unique indexes.
- Automates conditional expiration lifecycles via TTL indexes.

### 1.2. Costs to Account For

- Index disk space.
- Index working set in WiredTiger cache.
- Extra work on inserts and deletes.
- Extra work on updates modifying indexed values.
- Related journal, checkpoint, I/O, and replication overhead.
- Initial index builds and post-incident/restore rebuilds.
- Backup size or restore/recovery time, depending on tooling.
- Index management, monitoring, and migration risk.
- Write latency/tail latency when resources approach saturation.

Not every cost scales at a fixed linear rate. A narrow, partial, low-churn index costs far less than a multikey index generating many entries per document.

## 2. Optimize for the Workload, Not for a Single Query

Optimizing a rare query with a new index can add overhead to **every write** on the collection. Hence you must classify the workload.

### 2.1. Example Daily Activity Profile

| Operation Type | Illustrative Frequency | Target |
|---|---:|---|
| Find 20 newest orders per tenant | 800,000/day | p95 under 80 ms |
| Find orders by customer | 300,000/day | p95 under 120 ms |
| View order by `_id` | 1,000,000/day | p95 under 40 ms |
| Create new order | 150,000/day | p95 under 100 ms |
| Update `status` | 450,000/day | p95 under 100 ms |
| Update `lastViewedAt` | 2,000,000/day | Must not bottleneck writes |
| Ad-hoc campaign report | 20/day | Batch execution acceptable |

This data is **hypothetical for decision-making practice**, not a MongoDB benchmark.

An index serving a report run 20 times/day may not be worth keeping if it slows down millions of daily updates. That report might run offline, use a different aggregation, or justify a dedicated index only if business SLOs strictly mandate it.

### 2.2. Read-Heavy, Write-Heavy, and Mixed Workloads

| Workload Type | Characteristics | Balancing Strategy |
|---|---|---|
| Read-heavy | Many `find`/`aggregate` calls, few writes | Can justify more indexes for hot queries |
| Write-heavy | Heavy inserts/updates/deletes, few query shapes | Keep index set lean; keep only essential indexes |
| Mixed | Both reads and writes are critical | Weight by SLOs; measure trade-offs |
| Analytical batch | Few jobs, large data scans | Consider dedicated pipelines/analytics replicas |
| Time-series/event ingestion | Continuous writes, time-window reads | Design indexes around time and retention |
| Multi-tenant | Tenant-scoped queries, skewed distribution | Compound indexes; avoid tenant hotspots |
| Search-heavy | Text/vector retrieval | Dedicated Search/Vector Search indexes and resources |

**Read/write ratio alone is insufficient.** A read scanning 5 million records costs far more than an `_id` lookup; updating `lastSeenAt` differs from updating hundreds of array elements.

## 3. Index Costs in Write Operations: Understanding the Mechanics

MongoDB updates database indexes as documents change.

### 3.1. Insert

When inserting a new document:

```javascript
db.orders.insertOne({
  _id: "O-001",
  tenantId: "TENANT-A",
  orderNo: "2026-0001",
  status: "NEW",
  createdAt: new Date(),
  total: 250000
});
```

MongoDB must update the automatic `_id` index plus all applicable secondary indexes.

A collection with many indexes means **a single insert** requires multiple index-key insertions, increasing:

- CPU for key extraction/encoding;
- B-tree structural operations;
- Dirty cache pages;
- Write-ahead journal/checkpoint work;
- Related disk/replication overhead;
- Potential uniqueness constraint checks/errors.

### 3.2. Delete

When deleting a document:

```javascript
db.orders.deleteOne({
  _id: "O-001",
  tenantId: "TENANT-A"
});
```

MongoDB must remove corresponding keys from every index covering that document. Deleting one million records can generate substantial I/O when many indexes exist.

### 3.3. Update

**Not every update touches every index.**

Example index:

```javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
```

Updating an unindexed field:

```javascript
db.orders.updateOne(
  { _id: "O-001" },
  { $set: { note: "Called to confirm" } }
);
```

may avoid updating keys in the `tenantId/status/createdAt` index if no other change affects index membership. MongoDB still performs the document write and related storage/replication work.

Updating an indexed field:

```javascript
db.orders.updateOne(
  { _id: "O-001" },
  { $set: { status: "PAID" } }
);
```

typically updates the key in indexes containing `status`.

MongoDB notes that inserts/deletes add/remove corresponding index keys, whereas updates **affect only a subset of indexes** depending on which fields/keys change. Partial/sparse indexes are updated only when the document enters, leaves, or remains within the index filter scope. See [Write Operation Performance](https://www.mongodb.com/docs/manual/core/write-performance/).

### 3.4. Frequently Updated Fields Are Risk Points

Example:

```javascript
db.sessions.updateOne(
  { _id: sessionId },
  { $set: { lastSeenAt: new Date() } }
);
```

If every user sends continuous heartbeats and `lastSeenAt` is indexed solely for a rare query, MongoDB maintains that index constantly.

Before indexing a high-churn field, ask:

- Which queries truly depend on it?
- Could separate `createdAt`/`expiresAt` fields work instead?
- Can updates be batched or the data model adjusted?
- Is real-time querying on that field actually required?
- Can a partial index limit how many documents are indexed?
- Does the index significantly raise write p99?

Do not blindly delete a TTL index if it enforces retention policies; evaluate its actual role.

## 4. Why Can Too Many Indexes Slow Down Writes?

Suppose a collection has:

```text
_id_
tenantId_1
status_1
createdAt_-1
tenantId_1_status_1
tenantId_1_status_1_createdAt_-1
customerId_1
tenantId_1_customerId_1
tenantId_1_customerId_1_createdAt_-1
orderNo_1
lastSeenAt_1
```

If many indexes do not serve frequent queries, overhead persists across the collection despite low read utilization.

A conceptual cost model:

\[
T_{\text{write}} \approx T_{\text{document}} +
\sum_{i \in \text{affected indexes}} T_{\text{index},i} +
T_{\text{other}}
\]

`T_other` includes durability/replication, contention, and network. This formula is a **mental framework**, not a linear equation for predicting exact milliseconds.

### 4.1. Doubling Indexes Does Not Necessarily Halve Write Speed

Costs depend on:

- Index size and type;
- Index keys per document;
- Compression and caching;
- Selectivity and key ordering;
- Whether values actually change or stay identical;
- RAM and disk load;
- Batch size;
- CPU and replication topology;
- Primary vs. secondary roles;
- Concurrent workloads.

Three new indexes might barely affect one specific update while heavily slowing continuous inserts. **Benchmark the exact operations your application runs** before drawing conclusions.

### 4.2. Indexing Also Happens Across Replica Sets

When the primary executes writes, secondaries maintain data and index copies via replication. Index storage and maintenance CPU/I/O occur on every data-bearing node.

Do not claim "the index consumes 5 GB cluster-wide" just because the primary shows 5 GB, nor sum all replica copies as logical data size. Distinguish:

- **Logical index footprint per dataset**;
- **Physical footprint across replicas**;
- **Backup/snapshot overhead**;
- **Per-node working set**.

## 5. Index Count Does Not Equal Index Size

Two indexes both count as one entry in `getIndexes()`, yet their sizes can differ dramatically.

Example:

```javascript
db.products.createIndex({ category: 1 });

db.products.createIndex({
  title: 1,
  description: 1,
  createdAt: -1
});
```

Indexes on multiple fields or long strings usually produce much larger keys. Actual data, prefix compression, and value distributions also affect size.

### 5.1. Factors Affecting Size

- Number of indexed documents;
- Keys generated per document;
- Length and BSON types of values;
- Number of fields in a compound key;
- Multikey arrays;
- Duplicate values and prefix compression;
- Index type (B-tree, geospatial, wildcard, text, Search);
- Partial filters;
- Update churn;
- Storage engine and fragmentation/compaction state.

A rarely used index covering a long array per document can consume more space than several narrow scalar indexes combined.

### 5.2. Disk Footprint Differs from RAM Working Set

- **Disk index size:** storage space occupied by the index on disk.
- **Index working set:** portion of index pages actively accessed by the workload.
- **WiredTiger cache usage:** RAM used by the storage engine for hot data/index pages and metadata.

An index larger than RAM is not automatically slow; if the active portion fits in cache, reads stay fast. Conversely, a tiny index paired with non-selective queries can still perform poorly.

## 6. Running Example Dataset

We use a **test** collection `indexTradeoffLab.ordersBench`. Never run `drop()` or `deleteMany({})` on production just to test examples.

Sample document:

```javascript
{
  _id: "ORD-1001",
  tenantId: "T-01",
  orderNo: "2026-1001",
  customerId: "C-07",
  status: "PAID",
  createdAt: ISODate("2026-11-10T08:00:00Z"),
  updatedAt: ISODate("2026-11-11T09:00:00Z"),
  amount: 249000,
  channel: "WEB",
  tags: ["priority", "gift"],
  archived: false,
  expireAt: null
}
```

Typical query shapes:

**Q1 — Latest orders by tenant and status:**

```javascript
db.ordersBench.find({
  tenantId: "T-01",
  status: "PAID"
})
.sort({ createdAt: -1 })
.limit(20);
```

**Q2 — Order history for a customer:**

```javascript
db.ordersBench.find({
  tenantId: "T-01",
  customerId: "C-07"
})
.sort({ createdAt: -1 })
.limit(20);
```

**Q3 — Find order by order number within tenant:**

```javascript
db.ordersBench.findOne({
  tenantId: "T-01",
  orderNo: "2026-1001"
});
```

**Q4 — Nightly revenue aggregation:**

```javascript
db.ordersBench.aggregate([
  {
    $match: {
      tenantId: "T-01",
      createdAt: {
        $gte: ISODate("2026-11-01T00:00:00Z"),
        $lt: ISODate("2026-12-01T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: "$channel",
      amount: { $sum: "$amount" }
    }
  }
]);
```

**Q5 — Frequent status updates:**

```javascript
db.ordersBench.updateOne(
  { _id: "ORD-1001", tenantId: "T-01" },
  {
    $set: {
      status: "SHIPPED",
      updatedAt: new Date()
    }
  }
);
```

Now the question is: **how many** indexes and **on which fields** should we build to serve these five workload patterns?

## 7. Start with Mandatory Indexes

MongoDB automatically creates the `_id` index for standard collections according to collection-type rules.

```javascript
db.ordersBench.getIndexes();
```

On a new collection, you typically see:

```javascript
[
  {
    v: 2,
    key: { _id: 1 },
    name: "_id_"
  }
]
```

The `_id` index serves `_id` lookups and enforces uniqueness within the defined scope. Do not create an extra `{_id:1}` index just because of `findOne({_id: ...})`.

### 7.1. Unique Indexes Are Data Constraints

If `orderNo` must be unique **within a tenant**, use:

```javascript
db.ordersBench.createIndex(
  { tenantId: 1, orderNo: 1 },
  {
    unique: true,
    name: "uq_tenant_orderNo"
  }
);
```

This index not only accelerates Q3; it prevents duplicate `(tenantId, orderNo)` pairs per MongoDB unique semantics.

**Never drop a unique index just because `$indexStats` shows low query reads.** It can be a **correctness constraint**, not merely a performance tool.

### 7.2. Unique Indexes and Optional Fields

When fields are optional, missing, or `null`, unique semantics can produce surprises. Clarify whether uniqueness applies only when the field exists or across all records. A properly designed partial unique index may fit.

Before switching to partial unique, check for existing duplicates, filter expressions, and constraint scope. Never alter a business invariant solely to shave index storage.

## 8. Compound Indexes Replacing Multiple Single-Field Indexes

To serve Q1:

```javascript
db.ordersBench.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1
  },
  {
    name: "idx_tenant_status_created_desc"
  }
);
```

To serve Q2:

```javascript
db.ordersBench.createIndex(
  {
    tenantId: 1,
    customerId: 1,
    createdAt: -1
  },
  {
    name: "idx_tenant_customer_created_desc"
  }
);
```

To enforce and serve Q3:

```javascript
db.ordersBench.createIndex(
  { tenantId: 1, orderNo: 1 },
  { unique: true, name: "uq_tenant_orderNo" }
);
```

These three indexes serve distinct purposes. You probably do not also need all of:

```javascript
{ tenantId: 1 }
{ status: 1 }
{ createdAt: -1 }
{ customerId: 1 }
{ orderNo: 1 }
```

unless they serve meaningful independent query shapes.

### 8.1. Do Not Assume a Compound Index Always Replaces Single-Field Indexes

Index `{tenantId:1,status:1,createdAt:-1}` supports conditions matching a **prefix** of the index well, yet is not guaranteed to be optimal for:

```javascript
db.ordersBench.find({ status: "PAID" });
```

Because `status` is not the leading field, the planner may need a separate index or choose a different scan strategy.

Do not drop `{status:1}` merely because `status` appears inside a compound index; inspect the workload and `explain`.

### 8.2. Compound Key Order Matters

With index:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

a query with equality on `tenantId`/`status` and sort `createdAt:-1` leverages the prefix and ordering cleanly.

However, if reordered as:

```javascript
{ createdAt: -1, tenantId: 1, status: 1 }
```

query Q1 may scan a much larger key range because the leading field changed. Never order index keys by how JSON fields happen to be written in one query; consider **equality, sort, range**, and data distribution.

## 9. The ESR Rule: Equality, Sort, Range

A common heuristic for designing compound B-tree indexes is:

1. **Equality (E):** fields with equality predicates;
2. **Sort (S):** required sort order;
3. **Range (R):** fields with range filters like `$gte`, `$lt`.

Example:

```javascript
db.ordersBench.find({
  tenantId: "T-01",
  status: "PAID",
  amount: { $gte: 100000 }
})
.sort({ createdAt: -1 })
.limit(20);
```

A candidate index:

```javascript
{
  tenantId: 1,
  status: 1,
  createdAt: -1,
  amount: 1
}
```

Still, ESR is **not an absolute rule**. If the range on `amount` is extraordinarily selective, an **ERS** order might examine far fewer keys even while handling the sort differently. Test both candidates on real data with `explain` and latency/load tests.

### 9.1. Overly Wide Compound Indexes Can Backfire

A six-field index inflates key size, raises write cost, and still fails to optimize queries filtering only on middle fields. Do not "stuff every field into one index" mechanically just to reduce index count.

### 9.2. Prefixes and Reverse Scans

MongoDB can traverse certain compound B-tree indexes in reverse to satisfy inverted sort orders. However, not every ascending/descending combination across fields is equally supported; verify the index sort pattern alongside equality predicates.

**Always verify with `explain` and query results**, rather than guessing from `1`/`-1` counts in an index definition.

## 10. Covered Queries: Speeding Up Reads by Avoiding Document Fetches

A query is **covered** when both predicates and projected output fields are satisfied directly from the index per MongoDB's rules, avoiding reading the source documents for that part.

Example index:

```javascript
db.ordersBench.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
```

Query:

```javascript
db.ordersBench.find(
  {
    tenantId: "T-01",
    status: "PAID"
  },
  {
    _id: 0,
    tenantId: 1,
    status: 1,
    createdAt: 1
  }
)
.sort({ createdAt: -1 })
.limit(20);
```

If the planner selects the index and coverage rules hold, `totalDocsExamined` can be **0**.

### 10.1. Why Is `_id: 0` Needed?

By default, MongoDB `find()` returns `_id`. If `_id` is not part of the compound index, the default projection forces a document `FETCH`. Excluding `_id` when unnecessary enables a covered query.

### 10.2. Do Not Add Every Field Just to Achieve Coverage

Suppose the UI also wants:

```text
customerName
shippingAddress
items
paymentDetails
```

Stuffing all of them into the index bloats index size, spikes write overhead, and some field types are poor candidates for index keys anyway.

An alternative strategy:

1. Use a narrow index to locate the exact 20 documents;
2. `FETCH` those 20 documents;
3. Project only the required fields.

This usually beats maintaining a gigantic index solely to avoid fetching 20 records. Decide based on measurements.

### 10.3. Covered Queries Have Special Rules for Multikey Indexes

Never assume array queries can be covered just like scalar fields. Multikey indexes carry specific restrictions on projections and `$elemMatch`. Check `explain` and documentation for your index type and version.

## 11. Measuring Index Effectiveness with `explain("executionStats")`

In an authorized test environment, run:

```javascript
db.ordersBench.find({
  tenantId: "T-01",
  status: "PAID"
})
.sort({ createdAt: -1 })
.limit(20)
.explain("executionStats");
```

Fields to inspect:

| Field/Concept | Meaning |
|---|---|
| `winningPlan` | Execution plan chosen by the planner |
| `IXSCAN` or equivalent stage | Whether an index scan was used |
| `COLLSCAN` | Whether a full collection scan occurred |
| `FETCH` | Whether source documents were read after the index |
| `SORT` / blocking sort | Whether sorting occurred outside the index |
| `nReturned` | Number of documents returned |
| `totalKeysExamined` | Number of index entries scanned |
| `totalDocsExamined` | Number of documents inspected |
| `executionTimeMillis` | Execution time within explain scope |

Stage names and output schemas vary by query engine and MongoDB version; never build monitoring parsers tied to a single hard-coded stage name.

### 11.1. Documents Examined vs. Returned

A useful metric:

\[
R_{\text{docs}}=
\frac{\text{totalDocsExamined}}{\max(1,\text{nReturned})}
\]

Example:

```text
nReturned = 20
totalDocsExamined = 1,000,000
R_docs = 50,000
```

MongoDB examined 50,000 documents on average per returned document. That signals a query/index issue worth inspecting.

Still, a high ratio is not automatically a bug: queries returning **0 matches** or scanning large analytical sets can naturally yield high ratios. Interpret alongside business intent, latency, and resource consumption.

### 11.2. Keys Examined Matters Too

An index scan might `FETCH` only 20 documents yet walk millions of index keys to locate them. Low `totalDocsExamined` alone does not prove an index is efficient. Inspect **both keys examined and docs examined**.

### 11.3. A Single `explain` Does Not Measure p99

`explain("executionStats")` observes a single execution/query shape. It excludes:

- Driver pool wait;
- Network latency;
- Concurrent traffic;
- Warm/cold cache states;
- Replication;
- Application serialization;
- Retries and request fan-out.

Use `explain` to inspect the query plan, then verify end-to-end SLOs via APM and load testing.

## 12. Inspecting Index Inventory and Definitions

Run:

```javascript
db.ordersBench.getIndexes();
```

This returns **definition metadata**, such as key, name, unique, partial, sparse, TTL, collation, or hidden flags (if present).

Example:

```javascript
[
  { name: "_id_", key: { _id: 1 } },
  {
    name: "idx_tenant_status_created_desc",
    key: { tenantId: 1, status: 1, createdAt: -1 }
  },
  {
    name: "idx_tenant_customer_created_desc",
    key: { tenantId: 1, customerId: 1, createdAt: -1 }
  }
]
```

`getIndexes()` **does not tell you which indexes are heavily used**, nor does it report each index's size directly.

### 12.1. Categorizing Indexes by Purpose

An index inventory should capture:

```text
Index name
Index key
Unique/TTL/partial/hidden?
Protected query shapes
SLO/owner
Accesses over time
Index size
Write frequency of indexed fields
Notes on business constraints
```

An index with no identifiable owner or query shape is a **candidate for investigation**, not yet proof to delete.

## 13. `$indexStats`: Finding Rarely Accessed Indexes

MongoDB provides `$indexStats` to inspect usage statistics per index.

```javascript
db.ordersBench.aggregate([
  {
    $indexStats: {}
  },
  {
    $project: {
      name: 1,
      key: 1,
      host: 1,
      accesses: 1
    }
  }
]);
```

Sample output:

```javascript
{
  name: "idx_tenant_status_created_desc",
  key: { tenantId: 1, status: 1, createdAt: -1 },
  host: "mongo1.example:27017",
  accesses: {
    ops: NumberLong("23500"),
    since: ISODate("2026-11-10T00:00:00Z")
  }
}
```

`accesses.ops` counts **user operations** utilizing that index on that host per `$indexStats` semantics—not total keys examined or index write operations.

### 13.1. Important Caveats

- `$indexStats` **must be the first stage** in an aggregation pipeline.
- `$indexStats` cannot run inside transactions.
- Stats are **node/host-scoped**, not automatically aggregated across all replica members.
- Counters start from `accesses.since`, not the entire lifetime of the index.
- `mongod` restarts, drop/recreate operations, or modifying certain index attributes reset counters.
- Internal operations like TTL deletions, oplog apply, or index builds are not counted as user accesses in `accesses.ops`.
- An index rarely picked by the query planner may still enforce **uniqueness, TTL, or operational requirements**.

These caveats are documented in [MongoDB `$indexStats`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/indexstats/).

### 13.2. Do Not Immediately Drop Indexes with `accesses.ops = 0`

Example:

```text
Index A: accesses.ops=0
Index B: accesses.ops=3
Index C: accesses.ops=1,000,000
```

Questions to ask:

1. Did the server restart recently?
2. Does this index serve a monthly/quarterly batch job?
3. Does the app query it only during failover/DR?
4. Does the index enforce a unique or TTL constraint?
5. Was this metric collected on a primary or secondary?
6. Does another shard or tenant rely on it?
7. Is there a `hint()` or rare emergency code path?
8. Did the observation window cover a full business cycle?
9. Was the index just created without traffic yet?
10. Can we hide it first and monitor SLOs?

Never drop a cluster-wide production index based on one hour of zero accesses on a single node.

## 14. Measuring Index and Collection Sizes

A common source is `collStats` / `db.collection.stats()` depending on version and privileges.

Example:

```javascript
db.ordersBench.stats({
  scale: 1024 * 1024
});
```

Output may include:

```text
count
size
storageSize
totalIndexSize
indexSizes
nindexes
```

Size values scale according to the chosen `scale` factor. Check exact field definitions for your storage engine and version.

An explicit command approach:

```javascript
const stats = db.runCommand({
  collStats: "ordersBench",
  scale: 1024 * 1024
});

printjson({
  count: stats.count,
  logicalDataMB: stats.size,
  storageMB: stats.storageSize,
  totalIndexMB: stats.totalIndexSize,
  indexSizesMB: stats.indexSizes
});
```

These commands are references for supported versions/deployments; metric availability can vary on Atlas tiers. Never assume `size` equals physical bytes on disk.

### 14.1. Distinguishing Size Metrics

| Metric | Interpretation |
|---|---|
| `size` | Logical data size per stats definition |
| `storageSize` | Storage allocated/used for the collection by the storage engine |
| `totalIndexSize` | Total index footprint per stats |
| `indexSizes` | Per-index footprint |
| Node/volume disk used | Total disk: data, indexes, journal, logs, metadata, etc. |

Never arbitrarily sum overlapping or differently scoped metrics and call it your billing total.

### 14.2. A Footprint Report Should Record Full Context

```text
Collection: ordersBench
Count: 20,000,000 documents
Storage size: 18.3 GiB
Total index size: 12.4 GiB
Largest index: 5.1 GiB
Primary node: mongo-rs-01
Measured at: 2026-11-14 09:00 UTC
Server/FCV: ...
```

These numbers are **illustrative**. In practice, capture figures from the exact target server, timezone, unit, and version.

### 14.3. Index Size Does Not Equal RAM Usage

A 5 GiB index might have only 100 MiB of hot pages, or scan across nearly all keys continuously and thrash cache. `indexSizes` does not mean "the entire index sits in RAM."

To diagnose memory pressure, check WiredTiger cache metrics, page reads/evictions, and query latency.

## 15. WiredTiger Cache, Indexes, and Read Latency

WiredTiger caches data and index pages to minimize disk I/O. When the working set outgrows cache or queries thrash pages, performance degrades.

### 15.1. Common Symptoms

- Read p95/p99 rises despite steady QPS.
- Disk reads increase.
- WiredTiger cache eviction pressure rises.
- A new query pulls cold index pages into memory.
- Backups or index builds compete for I/O.
- OS page cache and WiredTiger cache are squeezed by resource limits.

### 15.2. Is a "Nearly Full Cache" Always Bad?

No. Caches are meant to stay full of hot data. Inspect **eviction rate, disk read latency, dirty bytes, contention**, and workload. Do not treat 80–90% cache utilization as proof you need more RAM if p99 meets SLOs and eviction is healthy.

### 15.3. Narrow Indexes Can Improve Cache Locality

If two query shapes are satisfied by one compact index, cache efficiency often improves compared to maintaining several near-duplicate indexes. However, merging into an overly wide index with large keys can worsen working-set pressure.

**Reducing index count does not automatically shrink the working set**; compare physical sizes and access patterns.

## 16. Partial Indexes: Indexing Fewer Documents

A partial index indexes only documents matching a `partialFilterExpression`.

Suppose only 10% of orders are active:

```javascript
db.ordersBench.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1
  },
  {
    name: "idx_active_tenant_status_created",
    partialFilterExpression: {
      archived: false
    }
  }
);
```

Documents with `archived: true` have no entry in this index. Potential benefits:

- Fewer index keys;
- Smaller index;
- Zero maintenance overhead on writes to out-of-scope documents;
- Smaller cache footprint;
- Efficient queries targeting active orders.

### 16.1. Queries Must Prove They Fall Within the Partial Index Scope

Example query that can use the index:

```javascript
db.ordersBench.find({
  tenantId: "T-01",
  archived: false,
  status: "PAID"
})
.sort({ createdAt: -1 });
```

Whereas this query:

```javascript
db.ordersBench.find({
  tenantId: "T-01",
  status: "PAID"
});
```

does not restrict results to `archived: false`, so the planner **cannot use the partial index because doing so would omit matching records**.

This is critical: **a smaller partial index is not a drop-in replacement for every query on the same fields**.

### 16.2. When Records Transition States

```javascript
db.ordersBench.updateOne(
  { _id: "ORD-1001" },
  { $set: { archived: true } }
);
```

The document **exits** the partial index scope, so MongoDB removes its key from the index. If `archived` flips back and forth repeatedly, entering and leaving the index also incurs cost.

### 16.3. Partial vs. Sparse Indexes

- `sparse`: filters based on field presence according to index/compound rules.
- `partial`: supports explicit filter predicates such as `archived: false`, `status: "ACTIVE"`, or range checks.

MongoDB generally recommends partial indexes for precise scope control. Do not combine `partialFilterExpression` with `sparse: true` on the same index. See [Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/).

### 16.4. Partial Unique Indexes Have Different Guarantees

A unique partial index enforces uniqueness **only among documents matching the partial filter**. If business logic requires global uniqueness across all records, swapping a full unique index for a partial unique index breaks data integrity.

## 17. Multikey Indexes: Key Count Can Exceed Document Count

When indexing an array field, MongoDB creates a **multikey index** where supported.

Example:

```javascript
{
  _id: "ORD-1001",
  tenantId: "T-01",
  tags: ["priority", "gift", "mobile"]
}
```

Index:

```javascript
db.ordersBench.createIndex({
  tenantId: 1,
  tags: 1
});
```

A single document generates multiple index keys—one per distinct value in the array.

### 17.1. A Document with 100 Tags Is Not Equivalent to a Scalar Field

Long arrays inflate index key counts and disk usage significantly. An update adding or removing tags modifies many keys at once.

If a `tags` index is rarely queried while every order carries hundreds of tags, it is a major cost driver.

### 17.2. Compound Multikey Limits

MongoDB restricts **compound multikey indexes**, especially when multiple indexed fields are arrays in the same document. Never assume you can freely create a compound index over arbitrary combinations of array fields.

If a document contains:

```javascript
{
  categories: ["A", "B"],
  colors: ["red", "blue"]
}
```

and you want a compound index across both arrays, check MongoDB's multikey constraints; unsupported combinations fail index creation or document writes.

### 17.3. Should Array Queries Be Indexed?

Possibly, after measuring:

- Key entry counts;
- Docs examined;
- Query frequency;
- Selectivity;
- Sort behavior;
- Proper `$elemMatch` and multikey bounds;
- Index size and write overhead.

Never index an array field simply because an array exists in the schema.

## 18. Choosing Between Compound Indexes and Index Intersection

MongoDB's query planner can combine multiple indexes in supported situations (*index intersection*), yet this **does not guarantee performance equal to a compound index**.

Suppose:

```javascript
db.ordersBench.createIndex({ tenantId: 1 });
db.ordersBench.createIndex({ status: 1 });
```

Query:

```javascript
db.ordersBench.find({
  tenantId: "T-01",
  status: "PAID"
});
```

Plans may pick one index, use intersection if chosen by the planner, or pick another strategy based on data statistics.

Index:

```javascript
db.ordersBench.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
```

also preserves key ordering and handles filter + sort far more effectively.

### 18.1. Do Not Create Pairwise Single Indexes Assuming "The Planner Will Intersect Them"

If Q1 is a hot query, benchmark the compound index directly. Never assume MongoDB will always intersect two single-field indexes at the same latency.

### 18.2. Do Not Merge Unrelated Predicates into Compound Indexes

If 99% of queries filter independently by `customerId` or `createdAt`, separate single-field indexes may be needed. **Actual query patterns** dictate the structure.

## 19. Collations and String-Sorting Indexes

String indexes depend on **collation** when language-specific, diacritic-insensitive, or case-insensitive comparisons/sorts are required.

Example case-insensitive product search/sort:

```javascript
db.products.createIndex(
  { tenantId: 1, title: 1 },
  {
    name: "idx_tenant_title_ci",
    collation: {
      locale: "en",
      strength: 2
    }
  }
);
```

Queries must specify a matching collation under MongoDB's rules:

```javascript
db.products.find({
  tenantId: "T-01",
  title: "Keyboard"
})
.collation({
  locale: "en",
  strength: 2
});
```

Mismatched collations prevent the planner from using that index. Maintaining extra indexes differing only by collation to serve UI sort variants adds disk and write overhead.

**Do not treat English collation as a default for Vietnamese text.** Choose locale and strength based on business expectations and benchmark with accented data.

## 20. TTL Indexes: Cost Justified by Retention

A TTL index lets MongoDB automatically delete expired documents via a background thread.

Example `sessionsLab` collection:

```javascript
db.sessionsLab.createIndex(
  { expireAt: 1 },
  {
    expireAfterSeconds: 0,
    name: "ttl_expireAt"
  }
);
```

Documents with a valid Date in `expireAt` become eligible for expiration at the configured time.

### 20.1. TTL Is Not Just a Read Index

A TTL index may show `accesses.ops = 0` because background TTL sweeps are internal operations not counted as user queries. It remains essential for retention.

**Never drop a TTL index just because `$indexStats` reports zero query usage.**

### 20.2. TTL Deletes Also Generate Write Load

When expiring batches of documents, MongoDB deletes documents and removes entries from all associated indexes. Expect activity across:

- Delete operations;
- Disk I/O;
- Replication traffic;
- Write latency;
- TTL queue/background load;
- Disk capacity.

TTL does not guarantee deletion to the exact millisecond. For legally strict retention deadlines, add explicit enforcement and verification.

### 20.3. Partial TTL Requires Checking Rules

MongoDB supports certain partial TTL index forms depending on version and collection type, but not all combinations are valid. Never assume any compound key + partial filter works as a TTL index; verify against documentation for your exact MongoDB release.

## 21. Wildcard Indexes: Flexible at a Cost

If a collection stores per-tenant dynamic fields:

```javascript
{
  tenantId: "T-01",
  attributes: {
    color: "blue",
    memoryGB: 16,
    keyboardLayout: "US"
  }
}
```

A wildcard index candidate:

```javascript
db.products.createIndex({
  "attributes.$**": 1
});
```

Wildcard indexes support queries over unpredictable paths according to MongoDB's rules.

### 21.1. Do Not Treat Wildcard Indexes as "Free Indexes for Every Field"

Indexing many dynamic paths can:

- Generate massive key counts;
- Consume substantial disk and cache;
- Add insert/update overhead;
- Fail to optimize sorts/queries as effectively as targeted compound indexes;
- Not enforce uniqueness constraints;
- Have restrictions with arrays, projections, and compound structures depending on version.

If actual queries only filter on `attributes.color` and `attributes.memoryGB`, indexing those two specific paths is cheaper and more predictable.

### 21.2. Decide Using Telemetry

Use query logs or Atlas insights to identify hot paths, then compare wildcard against explicit indexes. Do not create a wildcard index just because the schema is flexible.

## 22. Geospatial, Text, Hashed, and Search Indexes Also Have Trade-Offs

Not every index is a standard B-tree.

| Index/Engine | Primary Use Case | Trade-Offs to Evaluate |
|---|---|---|
| B-tree single/compound | Equality/range/sort | Writes + disk + planner complexity |
| Multikey | Querying arrays | Multiple keys/document |
| 2dsphere | Geospatial queries | Geometry validity / index footprint |
| 2d | Flat coordinate planes | Semantic and configuration limits |
| Hashed | Equality / hash-distributed patterns | Cannot replace normal range/sort |
| Text index (`$text`) | Basic full-text search | Maintenance cost, limited compared to Search |
| Wildcard | Dynamic path queries | Indexes many fields, storage overhead |
| MongoDB Search | Lucene full-text / relevance | Separate search index, indexing lag, Search nodes/resources |
| MongoDB Vector Search | Similarity retrieval | Vector storage/index, ANN/ENN cost, sync lag |

### 22.1. MongoDB Search Indexes Do Not Appear as Normal B-Tree Indexes

When using:

```javascript
db.products.createSearchIndex(...);
```

Search indexes have their own lifecycle and metrics. `db.products.getIndexes()` does not list MongoDB Search indexes.

When capacity-planning a collection, account for:

- Database indexes;
- Search/Vector Search indexes;
- Dedicated Search Nodes or co-located resources;
- Backfills and rebuilds;
- Vector embeddings stored in documents.

### 22.2. Text and Vector Search Have Sync Lag

Search indexes synchronize asynchronously from the source collection. A newly written record may not appear immediately in Search or Vector Search results.

Do not rely on Search indexes for business invariants requiring immediate read-after-write consistency or instant authorization checks.

## 23. Hidden Indexes: Test Removal from the Planner Before Dropping

MongoDB supports **hidden indexes** to evaluate the impact of preventing the planner from using an index.

Suppose you have:

```text
idx_tenant_status_created_desc
```

An administrative operation can hide it:

```javascript
db.ordersBench.hideIndex(
  "idx_tenant_status_created_desc"
);
```

Once hidden:

- The query planner **will not select it**;
- `hint()` cannot force queries to use a hidden index;
- **The index is still maintained on writes**;
- **The index still consumes disk and memory**;
- Unique constraints remain enforced if unique;
- TTL expiration continues operating;
- The index can be unhidden much faster than rebuilding from scratch;
- `$indexStats` counters may reset on hide/unhide.

See [Hidden Indexes](https://www.mongodb.com/docs/manual/core/index-hidden/).

### 23.1. Hidden Indexes Only Test Read Impact

Because a hidden index is still updated on every write, hiding it **does not measure the write or storage savings of actually dropping it**.

This distinction is easy to confuse:

```text
Hide index:
  Read behavior changes
  Write index maintenance still exists
  Disk index still exists

Drop index:
  Read behavior changes
  No corresponding index maintenance
  No corresponding index structure
```

Thus, hiding lowers read-regression risk, whereas write gains must be measured in staging benchmarks or during controlled rollout.

### 23.2. Hidden Testing Plan

1. Inventory query shapes and owners for the index.
2. Inspect `$indexStats` over a long enough window.
3. Exclude indexes serving uniqueness/TTL constraints.
4. Benchmark the workload with the index hidden in staging.
5. If testing in production, use a change window and SLO alarms.
6. Compare p95/p99, query scans, CPU, and I/O.
7. If performance degrades, unhide immediately.
8. Consider dropping only after gathering sufficient evidence.

### 23.3. Hiding Is Still a Production Change

`hideIndex()` is **not read-only**. It can instantly flip queries to `COLLSCAN` and spike latency. Never run it casually to "probe" a live user-facing cluster without approval.

### 23.4. The `_id` Index Cannot Be Hidden

The `_id` index has special constraints and cannot be hidden under MongoDB rules. Do not attempt to "reduce index count" by tampering with `_id`.

## 24. Dropping Indexes: An Operational Change Requiring a Rollback Plan

Dropping an index reduces write overhead and logical index footprint over time, yet can slow down read APIs or remove constraints.

Syntax example **to run only when approved**:

```javascript
db.ordersBench.dropIndex(
  "idx_tenant_status_created_desc"
);
```

Before dropping, verify:

- Does the index enforce unique/TTL/partial business invariants?
- Which queries use it—including rare emergency queries?
- Does another index cover those same query shapes?
- Does it affect shard key or indexing constraints?
- Do scheduled reports or batch jobs depend on it?
- Can it be rebuilt within your RTO?
- Is there enough disk/CPU/I/O headroom to rebuild if rolling back?
- Are change window, owner, alerts, and runbook defined?

### 24.1. Rollback After Drop Is Not Instantaneous

Rolling back a drop requires **rebuilding the index**. On large collections, index builds consume substantial time and resources even while serving traffic.

Therefore hiding is a valuable pre-drop safety step, though not a substitute for a rebuild recovery plan.

### 24.2. Disk Usage After Drop

Dropping an index changes logical index footprint, yet **free space reported by the OS/volume does not necessarily shrink immediately or identically** due to storage engine allocation, snapshots, and block reuse. Re-measure relevant metrics afterward; never promise exact GB freed on the volume immediately matching `indexSizes`.

### 24.3. Do Not Drop an Index Simply Because Another Shares Its Prefix

Example:

```text
A: { tenantId: 1 }
B: { tenantId: 1, status: 1, createdAt: -1 }
```

B can satisfy most `tenantId`-only queries, yet A is smaller, may cache better, and carries different traversal costs. Check `explain` on the workload before deciding.

## 25. Duplicates, Redundant Indexes, and Index Inventory

You may encounter:

```text
Index A: { tenantId: 1 }
Index B: { tenantId: 1, status: 1 }
Index C: { tenantId: 1, status: 1, createdAt: -1 }
Index D: { tenantId: 1, status: 1, createdAt: -1, orderNo: 1 }
```

Each index may help some queries, yet keeping too many overlapping indexes creates bloat.

### 25.1. Classifying Redundancy

**Exact equivalent:** identical keys and critical options—likely an unnecessary duplicate (and subject to version rules around equivalent indexes).

**Prefix-overlap:** one index is a prefix of another; potentially redundant, though not guaranteed.

**Same fields, different order:** e.g., `{tenantId,createdAt}` vs. `{createdAt,tenantId}`; serve different query shapes and are not redundant by default.

**Different sort direction:** some inverted directions work via reverse scans, though compound sort semantics must be checked.

**Different collation/partial/unique:** two indexes with identical keys but different options serve distinct requirements or constraints.

### 25.2. Sample Inventory Table

| Index | Purpose | Read Usage | Business Constraint? | Action Candidate |
|---|---|---|---|---|
| `_id_` | ID lookup | High | Yes | Keep |
| `uq_tenant_orderNo` | Order number lookup / uniqueness | Medium | Yes | Keep |
| `idx_tenant_status_created_desc` | Q1 hot path | High | No | Keep |
| `idx_tenant_customer_created_desc` | Q2 hot path | High | No | Keep |
| `idx_status_1` | Legacy status-only filter | Low | No | Investigate |
| `idx_lastSeenAt_1` | Legacy dashboard | Near 0 | No | Investigate closely |
| `ttl_expireAt` | Session retention | 0 user accesses | Yes | Keep per policy |

This table is illustrative, not measurements from a live system.

### 25.3. Measure "Value per Workload," Not Raw Index Count

An index hit 1,000,000 times/day saving 0.1 ms per query can deliver less value than an index hit 100,000 times/day cutting latency from 2 seconds down to 20 ms. Frequency must be weighed alongside **impact**.

## 26. Quantitative Cost-Benefit Estimation

A guiding model:

\[
B_{\text{read}} =
\sum_{q \in Q}
f_q \cdot
\left(t_{q,\text{without}} - t_{q,\text{with}}\right)
\]

Where:

- \(Q\): relevant query shapes;
- \(f_q\): invocation count of query shape \(q\) over an interval;
- \(t\): measured duration under a representative workload.

Similarly, write cost:

\[
C_{\text{write}} =
\sum_{w \in W}
f_w \cdot
\left(t_{w,\text{with}} - t_{w,\text{without}}\right)
\]

These sums yield **relative aggregate work-time deltas**, not exact CPU capacity or dollar cost, because requests run concurrently and resource contention is non-linear.

### 26.1. Illustrative Example

Suppose index X:

```text
Reduces latency by 8 ms for 500,000 reads/day
Increases latency by 0.6 ms for 1,000,000 writes/day
Consumes 5 GiB extra index storage
```

Cumulative read time saved in this simplified model:

\[
500,000 \times 0.008 = 4000\text{ seconds/day}
\]

Cumulative write time added:

\[
1,000,000 \times 0.0006 = 600\text{ seconds/day}
\]

This does not mean the system saves "3,400 wall-clock seconds" due to concurrency, caching, and contention differences. Rather, it is an initial quantitative signal to **guide deeper investigation and benchmarking**.

### 26.2. Business Weighting

A rare reporting read and a critical payment write carry different business weights.

Example scoring dimensions:

| Dimension | Question |
|---|---|
| Latency SLO | Does the index help hot paths meet p95/p99? |
| Write throughput | Do writes slow down under peak load? |
| Storage budget | Does the index breach quota or disk headroom? |
| Reliability | Do index builds/restores risk availability? |
| Correctness | Does the index enforce unique/TTL/invariants? |
| Business criticality | Which endpoints directly impact revenue? |
| Operational complexity | Can changes be rolled back safely? |

Never use an artificial "total score" to override mandatory security or uniqueness guarantees.

## 27. Optimizing Indexes for Update-Heavy Workloads

A `users` collection:

```javascript
{
  _id: "U101",
  tenantId: "T-01",
  emailNormalized: "u101@example.com",
  plan: "PRO",
  lastSeenAt: ISODate("2026-11-14T10:00:00Z")
}
```

Workload:

```text
Lookup email: 100,000/day
Update lastSeenAt: 10,000,000/day
Filter lastSeenAt range: 100/day
```

A unique index on `tenantId + emailNormalized` is likely justified, whereas indexing `lastSeenAt` can be far too expensive for 100 queries/day.

### 27.1. Options

- Accept scans/batch jobs for rare reports if acceptable.
- Materialize daily/hourly aggregates.
- Offload heartbeat events to a separate collection.
- Throttle `lastSeenAt` update frequency per business policy.
- Use a partial index for a valid subset if applicable.
- Measure read benefit vs. write penalty explicitly before deciding.

### 27.2. Do Not Alter Business Semantics Purely for Speed

If `lastSeenAt` drives security or session-logout policies, reducing its update frequency must be reviewed. Performance tuning must not silently compromise security freshness or correctness.

## 28. Trade-Offs with Bulk Ingest and Batch Writes

Bulk importing millions of documents into a heavily indexed collection can be slow due to index maintenance.

### 28.1. Why Can Ingesting with Fewer Indexes Be Faster?

Each insert updates all existing indexes. Some offline import workflows:

1. Prepare a new collection;
2. Insert data;
3. Create indexes afterward;
4. Verify readiness and query plans;
5. Cut over application traffic to the new collection.

This works only when:

- No concurrent queries require the indexes during ingest;
- Uniqueness constraints during ingest are either unnecessary or enforced otherwise;
- Sufficient disk and time exist for the post-load index build;
- A rollback plan exists;
- Dirty/duplicate data will not cause unique index builds to fail;
- Cutover is properly approved.

### 28.2. Online Production Imports Differ from Offline Loads

Do not drop indexes from a live production collection serving traffic just to speed up an import, because:

- Query plans degrade immediately;
- Unique/TTL invariants break;
- Rebuilding triggers heavy load;
- Duplicate rows inserted mid-gap can block rebuilding unique indexes;
- Backups, replication, and operational SLOs suffer.

For online writes, tune batch sizes, concurrency, network, and **controlled** index design instead.

### 28.3. `ordered` and Write Efficiency

With `insertMany`, `ordered: true` vs. `false` changes behavior upon batch errors. Never use `ordered: false` to silently ignore validation or unique key errors. Always inspect failed documents and ensure idempotency.

## 29. Sharded Clusters: Indexes Cost Per Shard

In sharded MongoDB:

```text
Application
    │
  mongos
    │
    ├── Shard A
    ├── Shard B
    └── Shard C
```

Indexes on sharded collections must be evaluated alongside query routing and data distribution.

### 29.1. Shard Key and Query Targeting

If the shard key is `tenantId` or a well-chosen compound key, queries carrying the shard key can target fewer shards. An optimal per-shard index **cannot fix** scatter-gather routing if `mongos` cannot target shards.

For example:

```javascript
db.ordersBench.find({
  status: "PAID"
});
```

lacks `tenantId`/shard key and may scatter across all shards even if every shard indexes `{status:1}`.

### 29.2. Cluster-Wide Storage

In sharded clusters, each shard holds a subset of data and its indexes, and each replica set holds copies. Distinguish:

- Logical index size per collection;
- Sum of index sizes across shards;
- Per-member storage;
- Replication factor;
- Backups;
- Search index footprint if applicable.

Do not miscount a 2 GiB index across three replica members as "6 GiB of logical index data," yet physical disk provisioning must cover all copies.

### 29.3. Unique Indexes on Sharded Collections Have Special Constraints

MongoDB enforces shard-key prefix requirements for unique indexes in many sharded configurations. Never add a unique index on `orderNo` alone to a sharded collection assuming global cluster uniqueness works automatically.

Check version documentation and shard key design before adding or dropping unique indexes on sharded collections—this is a **correctness constraint**, not merely a performance choice.

## 30. Index Builds: The Cost of Adding an Index

Building an index on a large collection is resource-intensive.

```javascript
db.ordersBench.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_tenant_status_created_desc" }
);
```

During the build, MongoDB reads data, extracts keys, sorts/builds index structures, and commits the index.

Observed impacts can include:

- Increased CPU, RAM, and disk I/O;
- Reduced free disk headroom;
- Read/write latency impact;
- Secondary replication/build load;
- Long build durations;
- Asynchronous readiness depending on management APIs;
- Build failures on invalid data or duplicate keys if unique.

### 30.1. Plan Deployment Timing

If API traffic peaks at 20:00, do not launch a massive index build right at peak just because queries are slow. Check:

- Maintenance / low-traffic windows;
- Remaining disk capacity;
- Resource headroom;
- Rollback strategy;
- Monitoring;
- Index build progress tracking;
- Replica set / quorum considerations;
- Failure scenarios.

Do not apply legacy version index-build locking assumptions blindly to modern MongoDB releases; concurrency and locking behavior have evolved across versions.

### 30.2. `createIndex()` Succeeding Does Not Guarantee Faster Queries

An index existing does not force the planner to use it. Query shape, collation, selectivity, partial predicates, sort order, and plan cache can steer MongoDB elsewhere. Always **verify `explain` on representative queries** post-build.

### 30.3. Index Builds Use Temporary Space

Capacity planning must allow headroom for index builds and temporary sort/build artifacts depending on version and configuration. Never provision disk right up to current `storageSize + totalIndexSize` and then trigger a large build.

## 31. Fair Before/After Benchmarking When Changing Indexes

A trustworthy comparison requires **identical workload, identical data, and documented conditions**.

### 31.1. Record a Pre-Change Baseline

Capture:

```text
MongoDB version / FCV
Cluster topology / tier / node size
Dataset count / distribution / size
Current indexes / index sizes
Read-write traffic mix / query shapes
p50/p95/p99 read latency
p50/p95/p99 insert/update/delete latency
ops/sec, concurrency
CPU/RAM/cache/disk I/O
Replication lag
Driver pool wait
```

### 31.2. Test Data Must Mirror Production Distribution

A collection of 10,000 documents with uniform tenant IDs does not represent 100 million documents where one tenant holds 70% and certain statuses dominate.

Simulate:

- Large vs. small tenants;
- Hot vs. cold records;
- Field cardinality;
- Missing/null values;
- Long vs. short arrays;
- Data skew;
- Range queries;
- Peak date windows;
- Realistic document sizes.

### 31.3. Separate Warm Cache and Cold Cache

The first run after an index build may fault many pages from disk, while subsequent runs benefit from cache.

Define scenarios explicitly:

- Cold-cache scenario;
- Warm-cache steady state;
- Load concurrency;
- Tail latency;
- Stabilization window before measuring;
- Volume/tier;
- Background workload.

Never cherry-pick the fastest single run as proof.

### 31.4. Avoid Destructive Testing on Production

Control `hideIndex`, `dropIndex`, rebuilds, and heavy load tests carefully. Use staging with production-like data or well-designed synthetic datasets. Any production test requires a change window, owner, risk review, and rollback plan.

### 31.5. Multi-Dimensional Comparison

| Metric | Baseline | Candidate A | Candidate B |
|---|---:|---:|---:|
| Read p95 | 180 ms | 80 ms | 65 ms |
| Update p95 | 22 ms | 29 ms | 45 ms |
| Insert throughput | 8,000/s | 7,200/s | 5,300/s |
| Index size | 4 GiB | 7 GiB | 13 GiB |
| CPU p95 | 65% | 70% | 90% |
| Disk read p95 | 12 ms | 8 ms | 8 ms |

**Hypothetical figures.** Here Candidate B yields faster reads but imposes heavy write and storage penalties. If order updates have strict SLOs, Candidate A may be the better choice.

There is no "best index" without stating **business priorities**.

## 32. Avoiding Measurement Errors from Cache, Plan Cache, and Stats

When comparing plans/indexes, results can be skewed by:

- Warmed data cache;
- Query plan cache;
- Background compaction/checkpoints;
- Concurrent writes;
- Network jitter;
- Shard rebalancing;
- Primary elections;
- Index builds;
- App deployments;
- Garbage collection;
- Load generator bottlenecks.

### 32.1. Changing Indexes Changes Plan Selection

The planner may pick a different index after create/hide/drop, shifting latency beyond mere footprint changes.

Always record `winningPlan` before and after, not just wall-clock times.

### 32.2. Bounded Plan Testing with `hint()`

In authorized environments, test a specific index with `hint()`:

```javascript
db.ordersBench.find({
  tenantId: "T-01",
  status: "PAID"
})
.sort({ createdAt: -1 })
.hint("idx_tenant_status_created_desc")
.explain("executionStats");
```

However:

- `hint()` can force a suboptimal plan;
- Hidden indexes cannot be used with `hint()`;
- Partial indexes still require coverage conditions;
- This command does not prove the default planner will pick that index;
- Leaving `hint()` in production code couples queries to index names;
- Treat `hint` as a diagnostic tool, not a blanket fix for planner issues.

## 33. Prioritizing Indexes for Hot Query Shapes

A practical rollout process:

1. Rank top query shapes by total execution time, p95/p99, and frequency.
2. Map business impact and SLOs.
3. Run `explain()` on each target query.
4. Design candidate indexes using equality/sort/range.
5. Check overlap with existing indexes.
6. Estimate write and storage costs.
7. Benchmark under a mixed read/write load.
8. Pick the smallest index set meeting SLOs.
9. Validate behavior in staging.
10. Roll out with alerts and rollback readiness.

### 33.1. Do Not Optimize 100 Query Shapes Simultaneously

Focus on the top 5–10 query shapes driving p99 and user impact. Rare queries can move to batch/analytics paths or rate-limited endpoints.

### 33.2. Optimize Schema and Queries Before Adding Indexes

Often the bottleneck is not a missing index:

- Returning too many fields;
- Unbounded queries lacking `limit`;
- N+1 queries;
- Unanchored regexes unable to leverage indexes well;
- Aggregations performing massive `$unwind`s;
- Unbounded embedded arrays;
- Missing pagination;
- Missing tenant/shard keys in predicates;
- Unnecessary sorts;
- Instantiating multiple `MongoClient` objects;
- Excessive sequential round trips per request.

Fixing the query or data model often yields massive wins with zero new indexes.

## 34. Pagination and Sorting: Impact on Index Design

An endpoint often needs:

```javascript
db.ordersBench.find({
  tenantId: "T-01",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
```

When deterministic ordering is required despite ties on `createdAt`, adding `_id` as a tie-breaker makes sense.

Candidate index:

```javascript
db.ordersBench.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
});
```

### 34.1. Large `skip()` Offsets Can Be Expensive

```javascript
db.ordersBench.find({
  tenantId: "T-01"
})
.sort({ createdAt: -1 })
.skip(100000)
.limit(20);
```

Offset pagination must walk and discard many index entries even when indexed. On large datasets, **keyset/cursor pagination** using `{createdAt, _id}` scales far better.

### 34.2. Keyset Pagination Requires Matching Indexes and Predicates

The next-page query filters "less than the last `(createdAt, _id)` pair" for descending order, properly handling ties on timestamps. Never filter solely by `createdAt: {$lt: lastCreatedAt}`, which skips orders sharing the boundary timestamp.

Switching pagination strategies can eliminate far more work than adding an index just to speed up `skip()`.

## 35. Time-Series and Data Lifecycles

For continuous telemetry, logs, or events:

```javascript
{
  sensorId: "S-101",
  ts: ISODate("2026-11-14T10:00:00Z"),
  temperature: 25.3
}
```

Workloads typically combine steady inserts, sensor/time-window queries, and retention policies.

A pattern:

```text
High write rate
Reads mostly by sensor + time range
Policy-based data expiration
```

Choose collection type, schema, and indexes accordingly.

### 35.1. Time-Series Collections Have Distinct Index Designs

MongoDB time-series collections use bucket-based storage with version-specific index rules and options. Never copy regular-collection B-tree/TTL assumptions directly onto time-series collections without checking compatibility.

### 35.2. Retention Shrinks Total Footprint

Retaining logs for 30 days instead of forever via TTL/retention cuts storage footprint. Yet deleting data is a legal/business decision, and TTL sweeps still consume write capacity. Never shorten retention just to hit a disk KPI.

## 36. Index Costs in Backup, Restore, and DR

Index footprint affects operations during:

- Snapshots and backups;
- Large dataset restores;
- Index rebuilds depending on restore method;
- Initial sync of replica set members;
- Provisioning new nodes;
- Resharding and rebalancing;
- Changing tiers or volume sizes;
- Cross-region cloud migrations.

Not all backup mechanisms store or restore index files the same way; verify your exact method (Atlas snapshots, logical backups, storage-level snapshots).

### 36.1. Do Not Assume Every Restore Rebuilds All Indexes

Physical snapshots preserve data/index state differently from logical exports/imports. RTO depends on backup/restore mechanism, data volume, network, and hardware. Measure via **restore drills** rather than estimating solely from `totalIndexSize`.

### 36.2. Budget Storage for Physical Copies

Example:

```text
Logical data:             40 GiB
Logical indexes:          20 GiB
Replica set:              3 data-bearing nodes
```

Roughly speaking, three copies can consume hundreds of GiB of physical storage once accounting for journals, compression, snapshots, free headroom, and temporary index builds. This is not an exact billing formula; rely on Atlas/cloud/storage metrics.

## 37. Role of Monitoring and Alerting

You cannot maintain balance long-term if you benchmark once at index creation and stop watching afterward.

A complete dashboard includes:

### Reads

- Query p50/p95/p99 by endpoint/query shape;
- Operations/s;
- `totalDocsExamined` / `nReturned`;
- `totalKeysExamined`;
- `COLLSCAN` / slow query rate;
- Sort spills;
- Read IOPS / cache misses.

### Writes

- Insert/update/delete operations/s;
- Write p95/p99;
- Write errors / duplicate key errors;
- Replication lag;
- Journal/checkpoint/disk write pressure;
- Concurrent operations / locks;
- Change stream / CDC lag where applicable.

### Indexes/Storage

- Index count per collection;
- Total index size;
- Per-index sizes;
- `$indexStats` accesses over windows;
- Hidden/partial/TTL/unique flags;
- Index build status;
- Free disk / headroom;
- WiredTiger cache / eviction;
- Backup/restore size and duration.

### Application

- HTTP latency / error rate;
- Driver command duration;
- Connection pool checkout wait;
- Retry counts;
- Business read/write ratio;
- Deployment annotations.

### 37.1. Tie Alerts to SLOs

For example:

```text
Write p99 > 150 ms for 10 minutes
AND traffic > minimum volume
```

is far more actionable than alerting "collection has more than 10 indexes," because index count is a design attribute rather than an outage on its own.

Any new index that raises write p99 while lowering read p95 must be evaluated against **both SLOs**.

## 38. Decision Matrix: When to Add, Merge, or Drop an Index?

| Situation | Preferred Action | Verification Needed |
|---|---|---|
| Hot query shows `COLLSCAN`, bad p99 | Test suitable index | Read benefit vs. write penalty |
| Multiple single-field indexes share prefixes | Evaluate compound candidate | Are standalone shapes still needed? |
| Index has few query accesses | Investigate / test hiding | Unique/TTL/rare batch/recent restart |
| Index includes constantly updated field | Re-evaluate | Business value of query, write latency |
| Dataset has many archived docs | Consider partial index | Do queries include matching predicates? |
| Index on long arrays | Measure multikey footprint | Keys per doc and update churn |
| Query returns many fields | Fix projection/limit first | Is covering index worth the size? |
| Full-text semantics needed | Use Search where appropriate | Lucene lifecycle and cost |
| `2dsphere` geo queries | Appropriate geo index | Geometry validity and index size |
| Write-heavy ingest | Keep only essential indexes | Unique/TTL and load window |
| Sharded query scatter-gather | Fix shard key targeting | Per-shard indexes cannot fix routing |
| Index build spikes I/O | Schedule change window | Resource headroom and rollback |
| Disk nearing capacity | Analyze sizes/retention | Never drop constraints arbitrarily |
| Planner picks odd index | `explain`/benchmark | Never hardcode `hint` blindly |

An index is **kept** not only for high access counts; it may protect correctness or serve a rare yet mandatory query.

## 39. Common Mistakes

| Mistake | Consequence | Correct Understanding |
|---|---|---|
| "More indexes are always faster" | Higher write cost and storage | Choose based on workload |
| "Fewer indexes are always better" | Hot reads scan excessively | Keep indexes meeting SLOs |
| "Every field needs an index" | Redundant indexes, hard maintenance | Design for query shapes |
| "A compound index replaces every single index" | Queries missing leading prefix suffer | Check prefixes and use cases |
| "ESR is an absolute rule" | May scan excessive keys | Benchmark ESR vs. ERS |
| "0-access indexes must be deleted" | Breaks unique/TTL or rare batches | Inventory and observe full cycles |
| "Hidden indexes save write overhead" | Wrong: hidden indexes still update | Hiding tests planner impact only |
| "Dropping an index is instantly reversible" | Rebuild is slow and resource-heavy | Prepare rollback plans |
| "Every update modifies every index" | Misjudges write cost | Depends on modified indexed keys |
| "Partial indexes serve all queries on those fields" | Missing results if query lacks filter | Predicate must imply partial filter |
| "A multikey array counts as one key" | Underestimates storage | Many keys per document |
| "Index size equals cache RAM needed" | Wrong capacity plan | Disk footprint differs from working set |
| "Queries with `IXSCAN` are automatically optimal" | May scan millions of keys | Check keys, docs, and latency |
| "Explain 20 ms means API p99 is 20 ms" | Ignores pool/network/app | Measure end-to-end |
| "Good read p95 means no need to test writes" | Write SLOs quietly break | Benchmark mixed read/write |
| "Summing replica metrics gives business writes" | Double counts copies | Separate node and internal ops |
| "Dropping an index immediately frees exact GB on disk" | Misleading capacity forecast | Track storage engine lifecycle |
| "Index builds never affect live traffic" | I/O and CPU spikes | Budget capacity and change windows |
| "Creating a unique index cannot fail" | Fails on duplicate data | Validate data beforehand |
| "A TTL index with 0 accesses is useless" | Breaks data retention | TTL sweeps are internal ops |
| "Index intersection always matches compound indexes" | Suboptimal plans | Measure each query shape |
| "Wildcard indexes replace specific indexes" | Bloated index footprint | Use only for truly dynamic queries |
| "Search indexes work like B-tree indexes" | Under-provisioned nodes / sync lag | Manage independently |
| "Indexes fix every slow API" | Bottleneck may be N+1 or pool | Trace the full request |
| "A 100-doc benchmark represents production" | Unreliable conclusions | Use representative size and skew |

## 40. Practice Exercises

### Exercise 1 — Identifying Valuable Indexes

A collection has:

```text
_id_
tenantId_1
status_1
tenantId_1_status_1
tenantId_1_status_1_createdAt_-1
customerId_1
tenantId_1_customerId_1_createdAt_-1
```

Daily traffic:

```text
Q1: tenantId + status + createdAt sort: 500,000 calls
Q2: tenantId + customerId + createdAt sort: 200,000 calls
Q3: status-only: 10 calls
```

1. Which indexes clearly serve hot queries?
2. Which indexes are candidates for redundancy review?
3. Why shouldn't `status_1` be dropped immediately?
4. What must be measured before and after hiding an index?
5. How can index overhead affect write operations?

### Exercise 2 — Insert/Update/Delete Costs

A collection has `_id_` and five secondary indexes.

1. Which indexes are affected by inserting a document?
2. What happens when deleting a document?
3. Does updating an unindexed field necessarily modify keys in all five indexes?
4. What happens when updating a field included in three indexes?
5. Under what conditions can a partial index lower cost?

### Exercise 3 — ESR and ERS

Query:

```javascript
db.ordersBench.find({
  tenantId: "T-01",
  amount: { $gte: 1000000 }
})
.sort({ createdAt: -1 })
.limit(20);
```

1. Propose an index following ESR.
2. Propose an index following ERS if `amount` is highly selective.
3. Benchmark `totalKeysExamined`, sort behavior, and latency.
4. When can ERS win?
5. Why is there no single key order optimal for every data distribution?

### Exercise 4 — Covered Queries

Given index:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

1. Write a query returning only those three fields without `_id`.
2. Check `totalDocsExamined` with `explain`.
3. Add `shippingAddress` to the projection.
4. What changes in `FETCH`?
5. Should `shippingAddress` be added to the index purely for coverage?

### Exercise 5 — Reading `$indexStats`

Output:

```text
Index A accesses.ops=0 since 10 minutes ago
Index B accesses.ops=1000 since 90 days ago
Index C accesses.ops=0 since 90 days ago, unique=true
```

1. Which index has enough evidence for immediate deletion?
2. Why does `since` matter?
3. Is a hidden index updated on writes?
4. Why does a unique index differ from an ordinary query index?
5. Do primary metrics represent secondary reads?

### Exercise 6 — Partial Indexes

90% of orders have `archived: true`.

1. Create a partial index `{tenantId, status, createdAt}` only for `archived: false`.
2. Write a query that can use it.
3. Write a query that cannot use it because results would be incomplete.
4. When `archived: false` changes to `true`, what index maintenance occurs?
5. Why do partial filters shrink storage without guaranteeing every query speeds up?

### Exercise 7 — Multikey Cost

Each document averages 80 tags.

1. How does `{tenantId:1, tags:1}` affect index key count?
2. What cost does an update adding 20 tags incur?
3. Measure `indexSizes` and benchmark inserts.
4. Can you freely create `{tags:1, otherArray:1}`?
5. When should you redesign the data model?

### Exercise 8 — Calculating Throughput from `opLatencies`

Two samples:

```text
T1: reads.ops=200000
T2: reads.ops=212000
Interval=120 seconds
```

1. Calculate reads/sec.
2. What happens if the server restarts in between?
3. Can this number be treated as HTTP RPS?
4. If writes increase while reads drop, how do you evaluate the trade-off?

### Exercise 9 — Estimating Total Cost

A new index:

```text
Reduces read latency by 10 ms across 300,000 reads/day
Increases write latency by 1 ms across 800,000 writes/day
Adds 8 GiB storage
```

1. Compute the cumulative time delta in the simplified model.
2. Why cannot this be converted directly into CPU-seconds?
3. If the write SLO is 50 ms, what must be measured?
4. If the index is a mandatory unique constraint, does the decision change?
5. When workload triples, what should be tested?

### Exercise 10 — Rarely Read TTL Index

Index `ttl_expireAt` shows `accesses.ops=0`.

1. Should it be deleted?
2. How does the TTL worker impact writes?
3. During bulk expiration, which metrics can spike?
4. Does TTL guarantee millisecond-exact deletion?
5. Is retention a technical or business/compliance decision?

### Exercise 11 — Hidden Index Experiment

1. Pick a low-usage ordinary non-unique, non-TTL index.
2. Record baseline p95/p99.
3. Test hiding it in staging under representative load.
4. Compare `explain` and SLOs.
5. Unhide if queries degrade.
6. Why does hiding fail to measure write savings after dropping?
7. Why should you not run this experiment unapproved in production?

### Exercise 12 — Replica Set Capacity

A collection has a 10 GiB index footprint per data-bearing member in a three-member replica set.

1. Distinguish logical from physical index footprint.
2. Estimate physical copy size before other overheads.
3. How much disk headroom is needed for index builds?
4. Do all backup/restore methods handle indexes identically?
5. Why does `stats()` size not reflect total disk usage?

### Exercise 13 — Hot Shard

A sharded collection shows:

```text
Shard A: 70% writes, CPU 95%
Shard B: 15% writes, CPU 35%
Shard C: 15% writes, CPU 30%
```

1. How could adding an index overload Shard A further?
2. How do query targeting and shard keys factor in?
3. Why does a good per-shard index not fix scatter-gather?
4. Which per-shard metrics should be monitored?
5. When should data redistribution be considered?

### Exercise 14 — Application N+1

An API returns 100 orders and runs a separate query for each customer.

1. How many MongoDB commands run per request?
2. Why might adding indexes fail to fix p99?
3. How can the data access pattern be optimized?
4. What pool wait and network round-trip metrics should be measured?
5. Compare before/after using distributed tracing.

### Exercise 15 — Building a Realistic Benchmark

Use a staging collection with:

- 1 million orders;
- 10 tenants with skewed distribution;
- 70% reads, 30% writes;
- Queries Q1/Q2 plus status updates;
- Compare three index sets.

Requirements:

1. Document dataset generation methodology.
2. Record baseline indexes and sizes.
3. Run `explain` for every query shape.
4. Measure read/write p95/p99.
5. Measure CPU, disk, and cache.
6. Measure index sizes and build durations.
7. Select a configuration based on SLOs and justify it.

### Exercise 16 — Keep or Drop Decision

A non-unique, non-TTL index shows:

```text
Accesses near 0 over 60 days
Size 12 GiB
Insert p99 120 ms, SLO 100 ms
Quarterly report might use this index
```

1. Can it be dropped immediately?
2. What questions must be asked of the report owner?
3. What does hiding the index help validate?
4. What does hiding the index fail to validate?
5. Design a change window and rollback plan.
6. How will you measure write improvements after dropping?

## 41. Checklist for Adding a New Index

### Before Creating

- [ ] Concrete query shape and owner identified.
- [ ] Query frequency and business SLO known.
- [ ] Baseline `explain()` captured before changes.
- [ ] Existing indexes and prefix overlaps reviewed.
- [ ] Key order evaluated via equality/sort/range.
- [ ] Evaluated whether a covered query is worthwhile.
- [ ] Checked array/multikey/partial/collation constraints.
- [ ] Representative test data exists for cardinality and skew.
- [ ] Baseline read/write p95/p99 captured.
- [ ] Disk/CPU/cache headroom verified for index build.
- [ ] Build execution and rollback plans prepared.

### After Creating

- [ ] Index build completed cleanly.
- [ ] Query planner selects the index as expected.
- [ ] `keysExamined`/`docsExamined` dropped appropriately.
- [ ] Read latency/SLOs improved.
- [ ] Insert/update/delete latencies remain within target.
- [ ] Disk/index size growth stayed within budget.
- [ ] Replication lag and background I/O remain acceptable.
- [ ] Queries not targeting the new index remain healthy.
- [ ] Metrics and index inventory updated.
- [ ] Owner assigned for ongoing index lifecycle.

## 42. Checklist for Auditing Existing Indexes

- [ ] List all indexes using `getIndexes()`.
- [ ] Measure per-index size via appropriate stats.
- [ ] Inspect `$indexStats` along with `since` timestamps.
- [ ] Gather metrics across all relevant nodes/shards.
- [ ] Separate unique/TTL constraints from query-performance indexes.
- [ ] Review unused indexes across full business cycles.
- [ ] Inspect prefix, sort, and collation overlaps.
- [ ] Measure write impact on indexed fields.
- [ ] Check for multikey/index-entry explosion.
- [ ] Verify partial predicates cannot omit expected query results.
- [ ] Test hiding candidate indexes in staging when needed.
- [ ] Maintain an unhide or rebuild recovery plan.
- [ ] Never drop `_id` or critical constraints arbitrarily.
- [ ] Monitor metrics after changes.
- [ ] Schedule periodic reviews as query shapes evolve.

## 43. Official References

- [MongoDB Indexes Overview](https://www.mongodb.com/docs/manual/indexes/)
- [Create Indexes](https://www.mongodb.com/docs/manual/core/indexes/create-index/)
- [Indexing Strategies](https://www.mongodb.com/docs/manual/applications/indexes/)
- [Write Operation Performance](https://www.mongodb.com/docs/manual/core/write-performance/)
- [Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/)
- [Equality, Sort, Range Guideline](https://www.mongodb.com/docs/manual/tutorial/equality-sort-range-guideline/)
- [Covered Queries](https://www.mongodb.com/docs/manual/core/query-optimization/)
- [Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/)
- [Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/)
- [Hidden Indexes](https://www.mongodb.com/docs/manual/core/index-hidden/)
- [$indexStats Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/indexstats/)
- [collStats Command](https://www.mongodb.com/docs/manual/reference/command/collStats/)
- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/)
- [Wildcard Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-wildcard/)
- [MongoDB Performance Tuning](https://www.mongodb.com/docs/manual/administration/performance-tuning/)
- [MongoDB Atlas Performance Advisor](https://www.mongodb.com/docs/atlas/performance-advisor/)
- [MongoDB Search](https://www.mongodb.com/docs/search/)
- [MongoDB Vector Search](https://www.mongodb.com/docs/vector-search/)

## Conclusion

Balancing index count, read speed, write speed, and storage is a **system-wide optimization problem**, not blindly creating an index per field or deleting every low-usage index.

A good index proves it serves **valuable query shapes** with lower read latency, better sorting, and fewer keys/documents examined, while keeping **insert/update/delete throughput** and **disk/cache footprint** within acceptable limits. MongoDB maintains index keys on inserts and deletes; updates only affect indexes tied to modified values or membership. Therefore, cost varies with index structure, data types, and field update frequency.

**Compound indexes**, **covered queries**, **partial indexes**, and sound query design typically deliver greater value than proliferating redundant indexes. **Multikey and wildcard indexes** warrant close scrutiny due to key multiplication. **Unique and TTL indexes** protect correctness and retention lifecycles, so they must never be dropped solely because `$indexStats` reports zero query reads.

Combine `getIndexes()`, `$indexStats`, `stats()/collStats`, `explain("executionStats")`, driver/APM metrics, and mixed read/write benchmarks on representative workloads. Use **hidden indexes** to safely test planner impact, remembering they **still consume storage and write maintenance**; actual drops require a change window and a rebuild/rollback plan.

**The best index set is the smallest set of indexes that meets all read, write, correctness, and storage SLOs—proven by measurement, not by index count.**
