# Evaluating Document Models by Queries, Indexes, Storage Size, and Update Cost

## Lesson Objectives

MongoDB lets you represent business relationships using **embedded documents**, **references**, or a combination of both. The exact same dataset can be organized as one large document or many smaller documents across different collections. No single model is universally superior: a model that makes detail reads fast can inflate update overhead or bloat index and storage footprints.

This lesson presents a decision process grounded in **measurable workloads** rather than intuition. After completing it, you will be able to:

- List the queries, updates, and consistency requirements driving a design.
- Compare embedding, referencing, and hybrid models across real read/write paths.
- Create and evaluate indexes with `explain("executionStats")`, spotting expensive scans.
- Estimate BSON size, index size, duplicated data, and growth rates.
- Analyze costs for array updates, shared-data updates, hot documents, and transactions.
- Design repeatable benchmarks comparing performance and cost over the same business dataset.
- Propose models backed by explicit assumptions, hard constraints, and evidence.

> **Principle:** Store together what is frequently **read together**, shares a close lifecycle, and requires **atomic updates together**. Separate what can grow without bound, is queried independently, or mutates continuously apart from other entities.

## 1. Why Does Document Shape Determine Performance?

Suppose an e-commerce system has customers, products, orders, and reviews. An order might look like this:

~~~javascript
{
  _id: "ORD-1001",
  customerId: "CUS-001",
  createdAt: ISODate("2026-11-14T03:15:00Z"),
  status: "NEW",
  total: NumberDecimal("1490000"),
  items: [
    {
      productId: "PRD-01",
      productNameAtPurchase: "Mechanical Keyboard",
      quantity: 1,
      unitPriceAtPurchase: NumberDecimal("850000")
    },
    {
      productId: "PRD-02",
      productNameAtPurchase: "Wireless Mouse",
      quantity: 2,
      unitPriceAtPurchase: NumberDecimal("320000")
    }
  ]
}
~~~

An order detail API can fetch all of this in a single read. However, if you need to find every order containing `PRD-01`, the system needs an appropriate query and index on the `items` array. If item counts are unbounded, the document can bloat. If a product name is copied into millions of orders and required to stay synchronized with the catalog, every rename triggers massive batch updates.

Throughout these evaluations, distinguish **snapshot data** (product name and price at checkout) from **live data** (current catalog selling price). Intentional duplication to preserve history is usually sound design; retroactively pushing new prices into old orders is both business-incorrect and expensive.

Four evaluation axes:

| Axis | Question | Evidence |
|---|---|---|
| Queries | How many reads, round trips, and milliseconds to return correct data? | Request latency p95/p99, `nReturned`, command count, response bytes |
| Indexes | Are filters and sorts supported efficiently? How much resource do indexes take? | `winningPlan`, `totalKeysExamined`, `totalDocsExamined`, `indexSizes` |
| Storage | Do documents grow too large, and how much data is duplicated? | `$bsonSize`, `avgObjSize`, `storageSize`, `totalIndexSize` |
| Updates | How many documents and indexes does one business change touch? | Write p95, modified doc count, conflicts/retries, replication and transaction overhead |

No single metric alone decides whether a model is good or bad.

## 2. Collect Workload Details Before Choosing Embedding or Referencing

### 2.1. List Read/Write Operations

An illustrative learning workload:

| Operation | Assumed Frequency | Filter / Sort | Required Fields | Characteristics |
|---|---|---|---|---|
| Customer order list | High | `customerId`, `createdAt DESC` | ID, date, status, total | 20 orders/page |
| Order details | High | `orderNo` | Header, items, purchase-time address | Co-read together |
| Orders by product | Medium | `items.productId` and date range | Matching orders and items | Needs array index if embedded |
| Transition order status | Medium | `orderNo` and current status | `status`, `updatedAt` | Business consistency |
| Update catalog price | Medium | `productId` | `currentPrice` | Must not alter historical prices |
| Latest reviews list | High on popular items | `productId`, `createdAt DESC` | 20 reviews/page | Can grow without bound |
| Add review | Medium | `productId`, user | One new review | Potentially many concurrent writers |

This table is illustrative, not benchmark data. In real projects, collect request counts, read/write ratios, array element counts, documents per parent, payload sizes, and distributions across tenants or customers.

### 2.2. Describe Every Query Completely

Do not write simply "find orders." Specify:

~~~text
Operation: GetRecentOrdersByCustomer
Filter: customerId = ?
Sort: createdAt DESC, _id DESC
Projection: orderNo, createdAt, status, total
Page size: 20
Read rate: measured via telemetry
Latency target: p95/p99 per SLA
Cardinality: orders/customer, average and maximum distribution
~~~

`_id` can serve as a secondary sort tie-breaker for deterministic ordering when multiple orders share the same timestamp. For deep pagination, consider keyset pagination instead of large `skip` values.

### 2.3. Turn Constraints into Verifiable Assumptions

- What is the maximum number of line items per order? Where is that limit enforced?
- How many reviews can a product accumulate, and how long are they kept?
- Is copied data an immutable snapshot or a cache requiring updates?
- Which changes must be atomic within **one document** versus **multiple documents**?
- Do subsets of data require different access permissions?
- Are sharding, hot keys, or cross-shard queries involved?
- How will storage volume and traffic grow over the next 6–12 months?
- Do different data types require different retention, TTL, or archival policies?

Your answers lead to different schema choices. "The array probably won't get big" is a weak assumption; "each order allows at most 100 line items and the application rejects larger orders" is a verifiable constraint.

## 3. Comparing Three Models on the Same Domain

### 3.1. Embedding: Nesting Line Items Inside Orders

~~~javascript
// Collection: orders_embedded
{
  _id: "ORD-1001",
  customerId: "CUS-001",
  createdAt: ISODate("2026-11-14T03:15:00Z"),
  status: "NEW",
  total: NumberDecimal("1490000"),
  items: [
    {
      productId: "PRD-01",
      productNameAtPurchase: "Mechanical Keyboard",
      quantity: 1,
      unitPriceAtPurchase: NumberDecimal("850000")
    },
    {
      productId: "PRD-02",
      productNameAtPurchase: "Wireless Mouse",
      quantity: 2,
      unitPriceAtPurchase: NumberDecimal("320000")
    }
  ]
}
~~~

**Benefits:**

- Detail queries read a single document, eliminating joins.
- Fields within the same document can be updated atomically in one write.
- Historical snapshot data lives directly alongside the order.
- Fits well when item counts are small and business-bounded.

**Limitations:**

- Document size grows with the array; unchecked item counts risk document size and cache pressure.
- Multikey indexes on arrays multiply index entries.
- Returning the whole document ships unnecessary payload if a listing page only needs header fields.
- Frequent updates on the same document can create write contention.
- A regular BSON document is capped at **16 MiB**.

Embedding fits when child records belong tightly to the parent, are co-read together, share lifecycles, and have strictly capped counts.

### 3.2. Referencing: Separating Order Headers and Line Items

~~~javascript
// Collection: orders_ref
{
  _id: "ORD-1001",
  customerId: "CUS-001",
  createdAt: ISODate("2026-11-14T03:15:00Z"),
  status: "NEW",
  total: NumberDecimal("1490000")
}

// Collection: order_items
{
  _id: "OI-001",
  orderId: "ORD-1001",
  productId: "PRD-01",
  productNameAtPurchase: "Mechanical Keyboard",
  quantity: 1,
  unitPriceAtPurchase: NumberDecimal("850000")
}
~~~

**Benefits:**

- Order headers stay small regardless of line item count.
- Items can be searched, updated, and paginated independently.
- Child indexes and retention can be tailored separately.
- Suits large or unbounded one-to-many relationships.

**Costs:**

- Order details typically require two queries or `$lookup`.
- Separate documents require link keys and additional indexes.
- Business actions writing both header and items may require transactions, retry/idempotency logic, or other consistency designs.
- Must handle orphan references and related deletion workflows.

Do not assume referencing always uses less storage: many small documents each carrying `_id`, link fields, and separate indexes also incur overhead.

### 3.3. Hybrid: Splitting by Semantics and Lifecycle

A common conceptual e-commerce model:

~~~text
customers
    |
    +--> orders
           |
           +--> items[]: bounded count,
                         purchase-time name/price
           |
           +--> productId referencing catalog if needed

products
    |
    +--> currentPrice, currentName, stock
    |
    +--> ratingSummary: precomputed stats
    |
    +--> reviews collection: independent reviews, paginated
~~~

Example separate review:

~~~javascript
{
  _id: ObjectId("..."),
  productId: "PRD-01",
  customerId: "CUS-001",
  rating: 5,
  content: "Great keyboard feel",
  createdAt: ISODate("2026-11-14T04:00:00Z")
}
~~~

Product can store precomputed stats for fast reads:

~~~javascript
{
  _id: "PRD-01",
  currentName: "Mechanical Keyboard",
  currentPrice: NumberDecimal("850000"),
  stock: 120,
  ratingSummary: {
    count: 2389,
    average: 4.7
  }
}
~~~

This is hybrid because:

- Line items preserve snapshots and need no updates when catalog prices change.
- Unbounded reviews live separately for independent writes and pagination.
- `ratingSummary` is derived data reducing read-time aggregation; it needs an update and rebuild strategy.

**Sources of truth must be crystal clear:** `reviews` is the source for reviews; `ratingSummary` is a precomputed projection. Order item prices are snapshots; `products.currentPrice` is live pricing.

## 4. Evaluating by Query Count and Returned Payload

### 4.1. Reading Details: One Document vs. Joining

**Embedding:**

~~~javascript
db.orders_embedded.findOne({ _id: "ORD-1001" });
~~~

**Referencing via two queries:**

~~~javascript
const order = db.orders_ref.findOne({ _id: "ORD-1001" });

const items = db.order_items
  .find({ orderId: "ORD-1001" })
  .toArray();
~~~

Referencing can use one aggregation instead of two round trips:

~~~javascript
db.orders_ref.aggregate([
  { $match: { _id: "ORD-1001" } },
  {
    $lookup: {
      from: "order_items",
      localField: "_id",
      foreignField: "orderId",
      as: "items"
    }
  }
]);
~~~

Index to test on the joined collection:

~~~javascript
db.order_items.createIndex(
  { orderId: 1 },
  { name: "idx_order_items_orderId" }
);
~~~

`$lookup` is not inherently slow. Cost depends on how many orders match before the join, indexes, child count per order, and returned payload size. If one order has huge numbers of children, returning them all in one result array still stresses memory and BSON limits.

### 4.2. Order Listings: Use Projections

Listing screens need only headers:

~~~javascript
db.orders_embedded.find(
  { customerId: "CUS-001" },
  {
    _id: 1,
    createdAt: 1,
    status: 1,
    total: 1
  }
).sort({ createdAt: -1, _id: -1 }).limit(20);
~~~

Projections reduce bytes sent to the driver. However, they do not guarantee proportional disk I/O savings: if the query must fetch documents from storage, reading, caching, and decompression still depend on the execution plan.

If filter, sort, and projection fields are all satisfied by a suitable index, MongoDB can perform a covered query. Verify with `explain`, as multikey indexes and certain query shapes have restrictions.

### 4.3. Partial Array Reads Are Not Free in Every Case

If the app displays only the 10 newest reviews of a product, embedding all 100,000 reviews inside the product and slicing 10 elements does not solve continuous parent document growth.

Referencing can do:

~~~javascript
db.reviews.find(
  { productId: "PRD-01" }
).sort({ createdAt: -1, _id: -1 }).limit(10);
~~~

Paired with index:

~~~javascript
db.reviews.createIndex(
  { productId: 1, createdAt: -1, _id: -1 },
  { name: "idx_recent_product_reviews" }
);
~~~

This keeps read volume bounded to page size and avoids funneling all writes into one product document.

## 5. Using `explain("executionStats")` to Inspect Queries

Create an index matching the order listing query:

~~~javascript
db.orders_embedded.createIndex(
  { customerId: 1, createdAt: -1, _id: -1 },
  { name: "idx_customer_recent_orders" }
);
~~~

Inspect the plan:

~~~javascript
const result = db.orders_embedded
  .find({ customerId: "CUS-001" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats");

printjson(result.executionStats);
printjson(result.queryPlanner.winningPlan);
~~~

Fields to examine:

| Field | Meaning | Red Flag to Investigate |
|---|---|---|
| `nReturned` | Number of documents returned | Does not match query intent |
| `totalKeysExamined` | Index entries scanned | Huge relative to returned count |
| `totalDocsExamined` | Documents inspected/fetched | Scanning many docs to return very few |
| `executionTimeMillis` | Execution time reported by explain | High or erratic; corroborate with app telemetry |
| `winningPlan` | Selected execution plan | `COLLSCAN` where an index is expected, or expensive in-memory sort |
| `rejectedPlans` | Candidate plans discarded, if returned | Helpful for debugging index selection |

If a query returns 20 orders after examining 100,000 documents, you likely need to revisit indexes or filters. Still, never apply a rigid `docsExamined/nReturned` ratio to every query: aggregations, counts, and analytics intentionally scan many records.

Execution plans may render differently across MongoDB versions and query engines. Stages like `IXSCAN`, `FETCH`, `SORT`, or `COLLSCAN` can appear in different plan tree branches. Read the full plan tree rather than checking one hardcoded JSON path.

**Limits of explain:** it reveals database-side work, not end-to-end latency. Response time also includes connection pooling, network, TLS, driver BSON decoding, serialization, business logic, and concurrency.

## 6. Designing Indexes Around Workload

### 6.1. Equality, Sort, and Range

Example:

~~~javascript
db.orders_embedded.find({
  customerId: "CUS-001",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z")
  }
}).sort({ createdAt: -1 }).limit(20);
~~~

Candidate index:

~~~javascript
db.orders_embedded.createIndex(
  { customerId: 1, createdAt: -1 },
  { name: "idx_customer_created" }
);
~~~

The **Equality – Sort – Range (ESR)** rule of thumb is useful for ordering compound index keys. However, validate indexes on real workloads; multi-dimensional ranges/sorts or skewed filter selectivity can favor different key orders.

### 6.2. Indexing Fields Inside Arrays

Find orders containing a specific product:

~~~javascript
db.orders_embedded.find({
  "items.productId": "PRD-01"
});
~~~

Candidate index:

~~~javascript
db.orders_embedded.createIndex(
  { "items.productId": 1, createdAt: -1 },
  { name: "idx_item_product_created" }
);
~~~

This is a **multikey index** because `items` is an array. One document with many items contributes many index entries. Multikey index rules also constrain sorting and indexing multiple array fields together.

Long embedded arrays increase:

- Index entries stored and maintained.
- Document and payload sizes.
- Insert/update overhead on indexed fields.
- Hot-document risk when multiple writers edit the same array.

For the same query, referencing allows a dedicated index:

~~~javascript
db.order_items.createIndex(
  { productId: 1, orderId: 1 },
  { name: "idx_item_product_order" }
);
~~~

However, to return **orders** rather than **line items**, include the cost of joining or querying `orders_ref` by `orderId`. Comparing two commands that return different shapes is an apples-to-oranges comparison.

### 6.3. Indexes Always Carry Maintenance Overhead

A single insert must write primary data and update every applicable index. Updating indexed fields requires updating index keys. Too many indexes inflate disk usage, cache demand, build times, and write amplification.

Checklist before adding an index:

1. Which exact queries use this index?
2. Does the index support both filtering and sorting?
3. Does it overlap significantly with an existing index?
4. How large is the index compared to the collection data?
5. How many writes mutate the indexed keys?
6. Does the index enforce a constraint (like unique) or only speed up reads?
7. Would a partial index or another index type fit better?

An index with low read counts may still be essential to enforce uniqueness. Never drop an index solely because read stats look low.

### 6.4. Inspecting Index Metadata and Usage

~~~javascript
db.orders_embedded.getIndexes();
db.orders_embedded.stats();

db.orders_embedded.aggregate([
  { $indexStats: {} }
]);
~~~

In supported versions, collection stats report fields such as `indexSizes`, `totalIndexSize`, `avgObjSize`, `size`, and `storageSize`. Exact interpretation depends on the storage engine and server version.

`$indexStats` reports index access counts accumulated during the current tracking window. Counters reset on operational events like restarts or index rebuilds. Observe over a representative period before declaring an index unused.

## 7. Evaluating BSON Size, Storage, and Indexes

### 7.1. The 16 MiB Limit and Array Growth

MongoDB caps a regular **BSON document at 16 MiB**. Embedding all comments or reviews into a parent document risks approaching that limit as data grows.

~~~javascript
// Example model prone to uncontrolled bloat:
{
  _id: "PRD-01",
  name: "Mechanical Keyboard",
  reviews: [
    // Every review from launch day through years ahead...
  ]
}
~~~

Even before hitting 16 MiB, oversized documents degrade p95/p99 latency, pressure caches, and trigger write conflicts. The usual alternative is separate paginated reviews, optionally paired with a tiny curated or precomputed subset on the product document.

### 7.2. Measuring Document Size with `$bsonSize`

On an order collection with an `items` array:

~~~javascript
db.orders_embedded.aggregate([
  {
    $project: {
      documentBytes: { $bsonSize: "$$ROOT" },
      itemCount: { $size: "$items" }
    }
  },
  {
    $group: {
      _id: null,
      count: { $sum: 1 },
      avgBytes: { $avg: "$documentBytes" },
      maxBytes: { $max: "$documentBytes" },
      totalMeasuredBytes: { $sum: "$documentBytes" },
      avgItems: { $avg: "$itemCount" }
    }
  }
]);
~~~

This example assumes every order has an `items` array. If legacy documents might omit the field or store a non-array, guard before applying `$size`.

Do not measure averages alone. The largest documents, outliers, and element-count distributions drive the biggest risks.

### 7.3. Logical BSON Size Differs from Disk Size

| Metric | Reflects |
|---|---|
| `$bsonSize` | Logical BSON size of a document |
| `size` or `avgObjSize` in stats | Logical data size statistics |
| `storageSize` | Allocated storage space for data, affected by storage engine and compression |
| `totalIndexSize` | Reported size of all indexes |
| Network payload | Actual bytes transferred over driver and APIs, which may differ from stored BSON size |

Documents with repeated field names often compress well; high-entropy data compresses less. Never equate `$bsonSize` directly with disk usage or cloud billing. Measure on representative datasets.

### 7.4. Estimating Duplication Under Growth

Suppose you have **1,000,000 orders**, averaging **5 items/order**, with each item copying a product name averaging **50 string bytes**.

~~~text
1,000,000 orders × 5 items/order × 50 bytes/item
= 250,000,000 bytes ≈ 250 MB raw product-name payload
~~~

That is not total BSON size. Add BSON framing overhead, field names, other snapshot values, indexes, and replicas; storage compression may reduce disk footprint. For historical snapshots, this cost is often reasonable. For live fields synced on every product edit, add fan-out update costs.

Total capacity forecasts should include:

~~~text
Stored data after storage engine compression
+ Indexes
+ Replica copies / redundancy factor
+ Backups / snapshots and retention
+ Temporary headroom for migrations, restores, index builds
+ Growth buffer
~~~

On managed services, billing across tiers, storage, I/O, backups, and networking also depends on the provider.

### 7.5. Do Not Ignore Read Payloads

If a listing page only needs `orderNo`, `status`, and `total` while the API returns `items` too, network payloads balloon when orders contain many items. Projections trim bytes returned to clients; tailored indexes and read models can reduce overhead further in certain cases.

Splitting header and details can fit apps that rarely load details, despite adding a join when details are viewed.

## 8. Update Cost: Measuring One Business Change

### 8.1. Single-Document Updates Are Atomic

MongoDB provides atomicity for writes **on a single document**, even when modifying multiple fields:

~~~javascript
db.orders_embedded.updateOne(
  { _id: "ORD-1001", status: "NEW" },
  {
    $set: {
      status: "PAID",
      paidAt: new Date(),
      updatedAt: new Date()
    }
  }
);
~~~

Including the expected status in the filter is a **conditional update** that detects concurrent state transitions. The application must handle `matchedCount`, errors, retries, and idempotency appropriately.

Single-document atomicity does not make every command fast. Latency still depends on indexes, document size, storage engine, write concern, and concurrent writers.

### 8.2. Updating Arrays: Few Elements or Many?

Appending an item with `$push`:

~~~javascript
db.orders_embedded.updateOne(
  { _id: "ORD-1001" },
  {
    $push: {
      items: {
        productId: "PRD-03",
        productNameAtPurchase: "Headphones",
        quantity: 1,
        unitPriceAtPurchase: NumberDecimal("450000")
      }
    }
  }
);
~~~

This illustrates only array manipulation; real orders must also update totals, stock, taxes, and status rules.

If an array is long and mutated continuously, measure:

- Growth rate of BSON size and index keys.
- Update latency p95/p99.
- Write conflicts/retries or hot-document contention.
- Network/byte transfer when re-reading the document.
- Complexity when concurrent operations edit the array.
- Risk of hitting the document size cap.

### 8.3. Do Not Assume Every Update Rewrites Full BSON to Disk

Claiming "editing 10 bytes in a 1 MiB document always rewrites 1 MiB to disk" is inaccurate. Storage engines use different optimizations and write mechanics depending on update type, indexes, journal/oplog, and data layout.

Write amplification cannot be deduced linearly from document size in every scenario. Nonetheless, large documents still carry cache, network, concurrency, and index-growth penalties; benchmark your actual workload.

### 8.4. Fan-Out Updates When Duplicating Live Data

If you copy a product's live price into every order and try keeping it synchronized, a single edit can require finding and modifying hundreds of thousands of documents.

Example illustrating **a dangerous update against historical snapshots**—do not run on finalized orders:

~~~javascript
db.orders_embedded.updateMany(
  { "items.productId": "PRD-01" },
  {
    $set: {
      "items.$[line].productNameAtPurchase": "New product name"
    }
  },
  {
    arrayFilters: [
      { "line.productId": "PRD-01" }
    ]
  }
);
~~~

For `productNameAtPurchase`, the operation above is also **business-incorrect** because history must preserve purchase-time details.

A cleaner design:

- Store **purchase-time** price and name in the order (immutable snapshot).
- Store `products.currentPrice` and current name in the catalog (canonical source).
- If a screen needs live data, query separately by `productId` or maintain a controlled synchronized read model.
- Pay denormalization maintenance costs only when read gains truly justify them.

Affected document count is a primary metric: one `updateMany` can cost vastly more than a handful of `updateOne` operations.

### 8.5. Hot Documents and Multiple Writers

A product document embedding all reviews where every user `$push`es into the same array becomes a centralized write bottleneck. The database can experience write conflicts/retries or degraded throughput under concurrent writes.

Separating reviews into independent documents distributes writes and allows dedicated pagination indexes. If an aggregate score is needed, `ratingSummary` can be a computed field updated via a dedicated mechanism.

### 8.6. Transactions and Consistency Costs

Embedding keeps updates across fields of one document atomic. With referencing, a workflow mutating multiple documents or collections may require a **multi-document transaction** on supported topologies.

Transactions add session management, concurrency control, commit, and retry overhead. They do not eliminate fan-out updates, oversized documents, or poor indexes. Use transactions to enforce genuine consistency invariants after bounding update scope.

### 8.7. Measuring Full Update Cost

For a single business change, ask:

~~~text
One business change
  -> How many documents must be located and updated?
  -> How many indexes are modified?
  -> Is a cross-collection transaction required?
  -> How many writers can contend on the same document?
  -> What are the update rate and p95/p99 latency?
  -> What state remains if a failure occurs mid-way?
  -> Must caches or read models be rebuilt?
  -> How much do replication, backup, and storage costs rise?
~~~

This is far more realistic than timing a single isolated command.

## 9. Design Patterns That Balance the Four Cost Axes

| Pattern | Approach | Best When | Costs to Manage |
|---|---|---|---|
| Embedding | Place children inside parent | Children are few, bounded, co-read | Large docs/multikey indexes, hot updates |
| Referencing | Link keys to separate collection | Children are many, independent, paginated | Joins, link indexes, cross-doc consistency |
| Subset | Embed hot slice, separate cold remainder | Details are large, UI needs only a few fields | Syncing subset if it is a copy |
| Extended reference | Store link key + a few stable related fields | Cut lookups via snapshot/read model | Define source of truth and refresh rules |
| Bucket | Group events into bounded chunks | High event volume, window-based reads | Bucket bounds, concurrency, sizing |
| Outlier | Split off extreme outlier cases | Most docs small, rare massive docs | Dual read paths and migrations |
| Computed | Store precalculated aggregates | Aggregate reads far outnumber writes | Consistency, retries, rebuilds |

**Subset example:** profile keeps only a few recent activities for dashboard display, while full history lives in `user_activities`.

**Bucket example:** sensor readings grouped by device and hour, each bucket size-capped. For time-stamped telemetry, evaluate **time series collections** before hand-rolling buckets.

**Computed example:** product stores `ratingSummary.average` and `ratingSummary.count`, while full reviews live in a separate collection. If aggregated asynchronously, the UI must accept lag and have a drift-repair plan.

## 10. Practice: Two Schemas on the Same Dataset

Use `mongosh` in a dedicated lab database. These commands intentionally create fresh namespaces; never run on production. With tiny sample sizes, the goal is inspecting document structures and query plans rather than large-scale benchmarking.

### 10.1. Seed Product Data

~~~javascript
use document_model_lab

db.products.insertMany([
  {
    _id: "PRD-01",
    name: "Mechanical Keyboard",
    currentPrice: NumberDecimal("850000"),
    stock: 120
  },
  {
    _id: "PRD-02",
    name: "Wireless Mouse",
    currentPrice: NumberDecimal("320000"),
    stock: 250
  },
  {
    _id: "PRD-03",
    name: "Headphones",
    currentPrice: NumberDecimal("450000"),
    stock: 90
  }
]);
~~~

### 10.2. Option A: Embedded Items

~~~javascript
db.orders_embedded.insertMany([
  {
    _id: "ORD-1001",
    customerId: "CUS-001",
    createdAt: ISODate("2026-11-14T03:15:00Z"),
    status: "NEW",
    total: NumberDecimal("1490000"),
    items: [
      {
        productId: "PRD-01",
        productNameAtPurchase: "Mechanical Keyboard",
        quantity: 1,
        unitPriceAtPurchase: NumberDecimal("850000")
      },
      {
        productId: "PRD-02",
        productNameAtPurchase: "Wireless Mouse",
        quantity: 2,
        unitPriceAtPurchase: NumberDecimal("320000")
      }
    ]
  },
  {
    _id: "ORD-1002",
    customerId: "CUS-001",
    createdAt: ISODate("2026-11-14T04:20:00Z"),
    status: "PAID",
    total: NumberDecimal("450000"),
    items: [
      {
        productId: "PRD-03",
        productNameAtPurchase: "Headphones",
        quantity: 1,
        unitPriceAtPurchase: NumberDecimal("450000")
      }
    ]
  },
  {
    _id: "ORD-1003",
    customerId: "CUS-002",
    createdAt: ISODate("2026-11-14T05:00:00Z"),
    status: "NEW",
    total: NumberDecimal("850000"),
    items: [
      {
        productId: "PRD-01",
        productNameAtPurchase: "Mechanical Keyboard",
        quantity: 1,
        unitPriceAtPurchase: NumberDecimal("850000")
      }
    ]
  }
]);
~~~

Create indexes for read patterns:

~~~javascript
db.orders_embedded.createIndex(
  { customerId: 1, createdAt: -1, _id: -1 },
  { name: "idx_customer_recent" }
);

db.orders_embedded.createIndex(
  { "items.productId": 1, createdAt: -1 },
  { name: "idx_product_created" }
);
~~~

### 10.3. Option B: Referenced Items

~~~javascript
db.orders_ref.insertMany([
  {
    _id: "ORD-1001",
    customerId: "CUS-001",
    createdAt: ISODate("2026-11-14T03:15:00Z"),
    status: "NEW",
    total: NumberDecimal("1490000")
  },
  {
    _id: "ORD-1002",
    customerId: "CUS-001",
    createdAt: ISODate("2026-11-14T04:20:00Z"),
    status: "PAID",
    total: NumberDecimal("450000")
  },
  {
    _id: "ORD-1003",
    customerId: "CUS-002",
    createdAt: ISODate("2026-11-14T05:00:00Z"),
    status: "NEW",
    total: NumberDecimal("850000")
  }
]);

db.order_items.insertMany([
  {
    _id: "OI-001",
    orderId: "ORD-1001",
    productId: "PRD-01",
    productNameAtPurchase: "Mechanical Keyboard",
    quantity: 1,
    unitPriceAtPurchase: NumberDecimal("850000")
  },
  {
    _id: "OI-002",
    orderId: "ORD-1001",
    productId: "PRD-02",
    productNameAtPurchase: "Wireless Mouse",
    quantity: 2,
    unitPriceAtPurchase: NumberDecimal("320000")
  },
  {
    _id: "OI-003",
    orderId: "ORD-1002",
    productId: "PRD-03",
    productNameAtPurchase: "Headphones",
    quantity: 1,
    unitPriceAtPurchase: NumberDecimal("450000")
  },
  {
    _id: "OI-004",
    orderId: "ORD-1003",
    productId: "PRD-01",
    productNameAtPurchase: "Mechanical Keyboard",
    quantity: 1,
    unitPriceAtPurchase: NumberDecimal("850000")
  }
]);
~~~

Indexes:

~~~javascript
db.orders_ref.createIndex(
  { customerId: 1, createdAt: -1, _id: -1 },
  { name: "idx_customer_recent" }
);

db.order_items.createIndex(
  { orderId: 1 },
  { name: "idx_items_order" }
);

db.order_items.createIndex(
  { productId: 1, orderId: 1 },
  { name: "idx_items_product_order" }
);
~~~

### 10.4. Compare Equivalent Business Payloads

Embedded order details:

~~~javascript
db.orders_embedded.findOne({ _id: "ORD-1001" });
~~~

Referenced order details:

~~~javascript
db.orders_ref.aggregate([
  { $match: { _id: "ORD-1001" } },
  {
    $lookup: {
      from: "order_items",
      localField: "_id",
      foreignField: "orderId",
      as: "items"
    }
  }
]);
~~~

Compare query counts, returned payloads, indexes on join keys, and CPU/latency under realistic load. Never compare a header-only query against a query returning full items and declare one model faster.

### 10.5. Inspect `explain` Across Both Query Paths

Order list:

~~~javascript
db.orders_embedded
  .find({ customerId: "CUS-001" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats");

db.orders_ref
  .find({ customerId: "CUS-001" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats");
~~~

Find orders involving a product:

~~~javascript
db.orders_embedded
  .find({ "items.productId": "PRD-01" })
  .explain("executionStats");

db.order_items
  .find({ productId: "PRD-01" })
  .explain("executionStats");
~~~

In the referenced model, the last query returns line items, not order headers. If business requirements demand order headers, include the order-joining step. This prevents skewed scope comparisons.

### 10.6. Measure BSON Bytes per Model

~~~javascript
db.orders_embedded.aggregate([
  {
    $project: {
      bsonBytes: { $bsonSize: "$$ROOT" },
      itemCount: { $size: "$items" }
    }
  }
]);

db.orders_ref.aggregate([
  {
    $project: {
      bsonBytes: { $bsonSize: "$$ROOT" }
    }
  }
]);

db.order_items.aggregate([
  {
    $project: {
      bsonBytes: { $bsonSize: "$$ROOT" }
    }
  }
]);
~~~

Inspect storage and indexes:

~~~javascript
db.orders_embedded.stats();
db.orders_ref.stats();
db.order_items.stats();

db.orders_embedded.getIndexes();
db.orders_ref.getIndexes();
db.order_items.getIndexes();
~~~

**Fair comparison:** Referenced total size is **orders_ref + order_items + indexes of both collections**. Comparing `orders_ref` alone against `orders_embedded` omits child data.

### 10.7. Measure Order Status Updates

~~~javascript
db.orders_embedded.updateOne(
  { _id: "ORD-1001", status: "NEW" },
  { $set: { status: "PAID", updatedAt: new Date() } }
);

db.orders_ref.updateOne(
  { _id: "ORD-1001", status: "NEW" },
  { $set: { status: "PAID", updatedAt: new Date() } }
);
~~~

In both models, this modifies one document. Larger differences emerge when editing items, under concurrent writes, or in workflows requiring atomicity across header and children.

### 10.8. Record Results in an Evaluation Table

| Metric | Embedded | Referenced | How to Measure |
|---|---:|---:|---|
| Collections needed for order details | 1 | 2 | Schema diagram |
| Implementation round trips | Measure | Measure | Driver/API telemetry |
| `totalKeysExamined` | Measure | Measure | Explain on relevant queries |
| `totalDocsExamined` | Measure | Measure | Explain and follow-up joins |
| Total dataset BSON bytes | Measure | Measure | `$bsonSize` summed across collections |
| Total dataset index bytes | Measure | Measure | Stats of all collections |
| Detail read p95 | Measure | Measure | Load test on large dataset |
| Item update p95 | Measure | Measure | Write load test |
| Largest document size | Measure | Measure | Aggregation, outlier check |
| Multi-entity write consistency | Evaluate | Evaluate | Transaction/atomicity design |

Every "Measure" cell must be filled from real lab/workload runs, never guessed.

## 11. Fair Benchmarking at Production Scale

### 11.1. Conditions That Must Remain Equivalent

- Same MongoDB version, storage engine, and CPU/RAM/disk hardware.
- Same business data and identical distributions of orders/items/reviews.
- Same filter, sort, projection, page size, and returned payload.
- Same write concern, read concern, and transaction policies.
- Same client count, connection pool, concurrency, network, and driver.
- Each model has indexes properly tuned for its own workload.
- Same read/write ratios, especially peak traffic bursts.
- Warm-up phase, repeated runs, and variance reporting.

It is unfair to benchmark embedding with a warm in-memory cache while referencing hits cold disk; it is equally unfair to give one model proper indexes and leave the other unindexed.

### 11.2. Synthetic Data Must Mirror Real Distributions

If all 1,000,000 test orders have exactly two items, you miss:

- A small fraction of customers with huge order histories.
- Bestsellers appearing in hundreds of thousands of orders.
- Single-item orders alongside B2B orders with hundreds of items.
- Peak write bursts contending on the same entity.
- Legacy records missing fields or having uneven shapes.
- Huge outlier documents driving tail p99 latency.

Outliers can break embedding viability long before averages look troubling.

### 11.3. Experimental Workflow

1. Write a specific hypothesis: e.g., "embedding items cuts order-detail p95 by at least 20%, while total storage grows under 15%."
2. Seed representative data for both candidates.
3. Build matching indexes and record their sizes and build durations.
4. Warm up, run steady-state load tiers, and measure p50/p95/p99 and throughput.
5. Run read-heavy, write-heavy, and mixed workloads separately.
6. Benchmark fan-out updates and hot-key contention.
7. Monitor CPU, cache, memory, disk I/O, network, replication lag, and write conflicts where available.
8. Repeat measurements under identical conditions; report medians and variance.
9. Estimate total storage/index/backup costs and schema migration effort.
10. Pick the option meeting requirements and log assumptions for post-launch tracking.

`explain()` is only part of measurement. True p95/p99 latency must be captured from the application or load-test harness at production-equivalent concurrency.

Never enable verbose profiling in production casually just for ad-hoc numbers; profiling carries overhead and can log sensitive query parameters. Choose observability mechanisms per operational policy.

## 12. Weighted Decision Matrix

Use two evaluation tiers:

**Tier 1 — Mandatory Gates (pass/fail):**

- Correct data semantics (snapshot vs. live).
- No unbounded arrays risking document size limits.
- Meets access control and retention requirements.
- Meets required consistency, transaction, and recovery guarantees.
- Has viable migration and rollback paths.

**Tier 2 — Weighted Optimization:** reads, indexes, storage, updates, and scalability.

Illustrative 1–5 scale, where 5 is best. Scores are **purely hypothetical to illustrate the method**, not a MongoDB benchmark:

| Criterion | Weight | Embedding | Referencing | Hybrid |
|---|---:|---:|---:|---:|
| Order details | 30% | 5 | 3 | 5 |
| Product-based queries | 20% | 3 | 5 | 4 |
| Storage and indexes | 15% | 3 | 4 | 4 |
| Update cost & consistency | 25% | 3 | 4 | 5 |
| Relationship growth | 10% | 2 | 5 | 4 |

Scoring calculation:

~~~text
Embedding = 5×0.30 + 3×0.20 + 3×0.15 + 3×0.25 + 2×0.10 = 3.50
Reference = 3×0.30 + 5×0.20 + 4×0.15 + 4×0.25 + 5×0.10 = 4.00
Hybrid    = 5×0.30 + 4×0.20 + 4×0.15 + 5×0.25 + 4×0.10 = 4.55
~~~

In this example Hybrid scores highest, yet if the workload is heavily event-write-oriented or every child is always read independently, the ranking could flip. Never pick a model that fails a Tier 1 gate merely because its weighted score is high.

## 13. Common Scenarios

### 13.1. Cart with Bounded Items

**Requirement:** Each cart holds at most 50 products, detail view always loads the entire cart, frequent updates hit one cart.

**Candidate:** Embed items in cart. Enforce caps and handle concurrency when multiple requests edit one cart simultaneously; single-document atomic updates help.

### 13.2. Comments Under Popular Articles

**Requirement:** One article can accumulate hundreds of thousands of comments; UI loads 20 comments at a time; many concurrent posters.

**Candidate:** Separate `comments` collection, index `{postId:1, createdAt:-1, _id:-1}`, paginate. Optionally keep a few featured comments as a read model in `post` if genuinely needed.

### 13.3. Paid Invoices

**Requirement:** Purchase-time names and prices must never change when the catalog updates.

**Candidate:** Embed line-item snapshots; retain `productId` to link to the catalog when needed, never mutating historical snapshots. This is business-valuable duplication.

### 13.4. Profile and Login History

**Requirement:** Profiles are heavily read; login events grow continuously with separate retention.

**Candidate:** Keep profile lean, store login events in a separate collection indexed by `userId` and timestamp. Avoid embedding full login history in profiles.

### 13.5. Product Rating Scores

**Requirement:** Product pages read average ratings thousands of times, new reviews arrive continuously, review lists are paginated.

**Candidate:** Separate `reviews` plus computed `ratingSummary` on `product`. Must have deduplicated updates, drift detection, and rebuilds.

### 13.6. Rarely Changing Config Documents

**Requirement:** Config has a few nested objects, read as a whole document, rarely edited, and updated as a single versioned unit.

**Candidate:** Embed in one document. If thousands of writers edit concurrently, evaluate versioning/conditional updates and contention.

## 14. Common Misconceptions

**"With MongoDB, you must embed everything."** False. Embedding unbounded relationships produces oversized documents and hot writes.

**"Referencing always saves storage."** Not guaranteed. A separate collection adds `_id`, link keys, indexes, and per-document overhead.

**"Embedded data doesn't need indexes."** False. Queries filtering/sorting on parent or array fields still need indexes.

**"More indexes always mean faster performance."** False. Indexes consume resources and slow writes; the planner might not even use extra ones.

**"`$lookup` is always slower than one document."** Cannot be generalized blindly. Performance depends on indexes, match cardinality, cache, and output size.

**"Editing one field in a 1 MiB document always rewrites 1 MiB to disk."** Not a universal storage engine rule. Measure it.

**"Every product price change must update all old orders."** Usually business-incorrect when order prices are purchase-time snapshots.

**"Small averages mean no 16 MiB risk."** Extreme outliers with huge arrays can still hit the cap.

**"`explain` alone tells production latency."** False. Network, drivers, mapping, serialization, and concurrency also matter.

**"Winning one benchmark proves the schema is optimal."** Insufficient. Run multiple trials with representative distributions and write workloads.

**"Transactions solve every referencing issue."** Transactions provide multi-document atomicity on supported deployments, yet do not eliminate fan-out or storage bloat.

**"Data duplication is always wrong."** Snapshots and read models are valid choices when sources of truth and update policies are explicitly defined.

## 15. Exercises

### Exercise 1 — Build a Workload Matrix

An online learning platform has:

- 100,000 learners.
- Each learner enrolls in many courses.
- Each course has a lesson list usually read together.
- Each course accumulates thousands of view history events.
- The history page returns 20 events/page.
- Learner progress updates continuously.

Create a table of Operation / Filter / Sort / Projection / Frequency / Growth / Consistency and propose embedding vs. referencing for `lessons`, `viewEvents`, and `studentProgress`. Justify using both read and write paths.

### Exercise 2 — Analyze `explain`

Query:

~~~javascript
db.orders_embedded.find({
  customerId: "CUS-100",
  status: "PAID"
}).sort({ createdAt: -1 }).limit(20);
~~~

Hypothetical measurement:

~~~text
nReturned = 20
totalKeysExamined = 120000
totalDocsExamined = 90000
~~~

Why should this be investigated? Propose two candidate compound indexes and explain how to verify field order with `explain`. Why do selectivity and data distribution affect the decision?

### Exercise 3 — Estimate Raw Growth

A `posts` collection has 200,000 articles; each averages 500 comments; each comment averages 180 BSON bytes.

- Estimate total comment data before indexes, compression, and replicas.
- Explain why certain viral posts risk hitting the 16 MiB limit.
- Analyze multikey index costs and concurrent comment inserts.
- Propose a separate `comments` collection with indexes by post/time.

### Exercise 4 — Update Cost of Duplicated Data

A carrier's name appears in two million orders. The carrier rebrands:

1. Is the name on an order a snapshot or live data?
2. If a snapshot, should two million orders be updated?
3. If a live cache, what sync management strategy fits?
4. On which endpoints would referencing increase read cost?
5. Which metrics must be measured before changing schemas?

### Exercise 5 — Schema Experiment

Starting from the lab dataset, generate additional orders with a skewed item-count distribution. Compare:

- Order detail and order list p95 latency.
- `totalKeysExamined`/`totalDocsExamined` across read patterns.
- Total dataset BSON size plus total index size.
- Item/status update p95 under concurrency.
- Unusually large B2B orders.
- Migration effort from old model to new model.

Write a final recommendation stating benefits, costs, and scenarios where the alternative wins.

## 16. Review Questions

1. Why should document modeling start from the workload?
2. Which query properties dictate index design?
3. When does embedding help atomicity and data locality?
4. When should child data move to a separate collection?
5. How do multikey indexes increase overhead?
6. What do `nReturned`, `totalKeysExamined`, and `totalDocsExamined` reveal?
7. Why do projections not guarantee proportional disk I/O reductions?
8. How does logical BSON size differ from `storageSize`?
9. Why must indexes from all collections be summed when evaluating referencing?
10. How does snapshot duplication differ from a live cache?
11. Why does a tiny update not always incur write I/O equal to the full document size?
12. How do hot documents emerge?
13. What do multi-document transactions solve, and what do they not solve?
14. Which equivalent conditions are required for a trustworthy benchmark?
15. Which mandatory gates must be checked before applying a weighted scoring matrix?

## 17. Summary

Evaluating MongoDB document models must combine **queries, indexes, storage size, and update cost**. Embedding favors small, bounded child data co-read with the parent. Referencing favors large, independently read/paginated, or independently updated children. Hybrid models excel when you need both historical snapshots and live data or computed read models.

A verifiable decision follows: **clear workload → schema candidates → matching indexes → explain and BSON/index size measurement → read/write benchmarking under concurrency → checking consistency, limits, and total cost**. Before any optimization, define the semantics of copied data: is it an immutable snapshot or a copy that must track a canonical source?

## Official References

- [MongoDB Manual — Data Modeling](https://www.mongodb.com/docs/manual/data-modeling/)
- [MongoDB Manual — Embedded Data Versus References](https://www.mongodb.com/docs/manual/data-modeling/concepts/embedding-vs-references/)
- [MongoDB Manual — Data Model Design Patterns](https://www.mongodb.com/docs/manual/data-modeling/design-patterns/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual — Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB Manual — Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/)
- [MongoDB Manual — Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/)
- [MongoDB Manual — BSON Document Limits](https://www.mongodb.com/docs/manual/reference/limits/)
- [MongoDB Manual — BSON Size Aggregation Expression](https://www.mongodb.com/docs/manual/reference/operator/aggregation/bsonSize/)
- [MongoDB Manual — Index Statistics Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/indexStats/)
- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
