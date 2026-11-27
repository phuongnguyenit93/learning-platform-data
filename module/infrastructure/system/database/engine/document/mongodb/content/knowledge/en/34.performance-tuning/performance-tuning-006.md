# Reducing Network Data Transfer Using Projection, Batching, and Compression in MongoDB

A screen listing 20 orders only displays the order number, status, and total amount, yet the API reads internal notes, full change history, and an array of 5,000 items from every document. A data processing job sends 100,000 individual update commands to MongoDB. Another service transfers large text payloads over a slow network link without compression. All three cause substantial latency, data transfer cost, and memory pressure—even when none of the queries have syntax errors.

MongoDB offers three groups of techniques to cut network overhead:

- **Projection**: return only the required fields, shrinking BSON response size.
- **Batching**: transfer multiple documents or operations in well-sized batches, reducing round trips between application and database.
- **Wire compression**: compress MongoDB protocol messages in transit using compatible codecs on both ends, trading CPU for fewer wire bytes.

They address **different bottlenecks**. Projection reduces raw data bytes; batching cuts round trips and per-command overhead; compression reduces bytes actually sent across the wire. Increasing batch size does not remove unused fields. Compressing a huge document does not mean the application actually needs its entire contents. And even with tiny responses, a query can remain slow due to missing indexes or CPU-heavy pipelines.

This lesson belongs to the **Performance Tuning** chapter of the *Database Engine Document MongoDB* module. Examples use **mongosh**, the **Node.js MongoDB Driver**, and the **Java Sync Driver**; data, figures, and hostnames are illustrative only. Specific batch defaults, compression features, and wire protocol limits depend on server and driver versions, so verify against your running environment. Never execute data-modifying commands on production purely for practice.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish BSON document bytes, network wire bytes, round trips, and API response sizes.
2. Read and write `find` projections, including nested fields and `_id`.
3. Shrink array payloads using `$slice`, `$elemMatch`, `$filter`, or counts instead of loading every element.
4. Use `$project`/`$unset` in aggregations in the proper execution order.
5. Reduce document counts via `$match`, `limit`, pagination, and properly indexed queries.
6. Explain covered queries and the conditions required to avoid fetching full documents.
7. Understand MongoDB cursors, `firstBatch`, `getMore`, and the meaning of `batchSize`.
8. Distinguish cursor batch size, total query limit, HTTP page size, and bulk write batch size.
9. Use Node.js/Java streaming cursors to avoid loading millions of documents into RAM.
10. Group writes via `insertMany`/`bulkWrite` and handle `ordered`/`unordered`, partial errors, and retries.
11. Understand BSON document limits, wire message limits, and operation count limits in a write batch.
12. Configure `snappy`, `zlib`, and `zstd` compressors according to driver/server support.
13. Distinguish wire compression, TLS encryption, WiredTiger compression, and HTTP compression.
14. Measure document sizes, execution plans, network round trips, network counters, CPU, and p95/p99 latency.
15. Recognize when an optimization raises CPU, memory, latency, or accidentally changes business semantics.

## 2. Data Transfer Cost Model

A MongoDB read is more than server query execution time. It also includes checking out a connection, transmitting the request, BSON handling, encryption/compression if enabled, transmitting the response, decoding, and application processing.

~~~mermaid
flowchart LR
    App["Application"] --> Driver["MongoDB Driver / pool"]
    Driver -->|"find/aggregate"| Server["mongod or mongos"]
    Server --> Query["Index scan, filter, sort"]
    Query --> Project["Project output BSON"]
    Project --> Compress["Wire compression if enabled"]
    Compress -->|"Network response"| Driver
    Driver --> Decode["Decode/deserialize"]
    Decode --> App
~~~

An approximate model:

\[
T \approx T_{\text{server}}+
N_{\text{roundtrips}}\cdot RTT+
\frac{B_{\text{wire}}}{\text{bandwidth}}+
T_{\text{encode/decode}}+
T_{\text{compress/decompress}}
\]

This model does not capture every effect of concurrency, packet loss, or pipelining, yet highlights key trade-offs:

| Tool | What Usually Drops | Price Paid |
|---|---|---|
| Projection | BSON output payload, decode cost | May require a separate detail request later |
| Filter/limit | Number of returned records | Needs proper indexes and pagination logic |
| Cursor batching | Number of `getMore` round trips | Memory per batch |
| Bulk writes | Per-operation command overhead | Batch size, partial failures |
| Wire compression | Bytes over MongoDB connections | CPU and sometimes higher latency |

**Note:** Reducing network bytes does not automatically cut disk I/O. A query scanning 5 million records might return one tiny projected document while still burning heavy server CPU and I/O. Always inspect the query plan.

## 3. Distinguishing BSON Size, Wire Size, and JSON Size

MongoDB stores and transmits documents in BSON with overhead for field names, types, and structure. An API may convert BSON into JSON and apply HTTP compression, resulting in distinct sizes at each layer:

~~~text
BSON size before projection
    -> BSON size after projection
        -> MongoDB wire message before compression
            -> MongoDB wire bytes after compression
                -> HTTP JSON bytes after API conversion
                    -> HTTP response bytes after Content-Encoding
~~~

Do not use `JSON.stringify(doc).length` as exact BSON byte length: JavaScript `String.length` counts UTF-16 code units, whereas BSON uses distinct binary encodings for ObjectId, Date, Decimal128, binary, and type headers.

### 3.1. Hypothetical Quantitative Example

If a full document is roughly 40 KiB while list fields alone take ~500 bytes, across 1,000 documents:

| Return Format | Estimated BSON Payload |
|---|---:|
| Full documents | Around 40 MiB |
| Projected list fields | Around 0.5 MiB |

These are **illustrative estimates**, not measured MongoDB output. Even if `zstd` compresses full documents heavily, serializing, decoding, and compressing unused fields still costs CPU; projection is usually the right starting point.

### 3.2. TCP Packets Differ from Cursor Batches

A single MongoDB response can span many TCP packets. Conversely, `getMore` is **a MongoDB-level command** fetching the next batch. Counting TCP packets is not the same as counting `getMore` round trips.

## 4. Setting Up a Lab with Heavy Documents

Run the following commands only in a learning database:

~~~javascript
use network_optimization_lab

db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: -1 },
  { name: "idx_tenant_status_created_id" }
)

db.orders.insertMany([
  {
    _id: 101,
    tenantId: "t-01",
    orderNo: "O-101",
    status: "PAID",
    total: 120000,
    createdAt: ISODate("2026-11-01T10:00:00Z"),
    customer: {
      customerId: "C-1", name: "Customer A",
      email: "a@example.invalid"
    },
    items: [
      { sku: "SKU-A", quantity: 2, price: 40000 },
      { sku: "SKU-B", quantity: 1, price: 40000 }
    ],
    internalNotes: "Long notes unnecessary for list API. ".repeat(200),
    auditTrail: Array.from({ length: 20 }, (_, i) => ({
      step: i,
      message: "Audit trail info for another screen"
    }))
  },
  {
    _id: 102,
    tenantId: "t-01",
    orderNo: "O-102",
    status: "PAID",
    total: 99000,
    createdAt: ISODate("2026-11-02T10:00:00Z"),
    customer: {
      customerId: "C-2", name: "Customer B",
      email: "b@example.invalid"
    },
    items: [{ sku: "SKU-C", quantity: 1, price: 99000 }],
    internalNotes: "No need to load notes when viewing list. ".repeat(200),
    auditTrail: []
  },
  {
    _id: 103,
    tenantId: "t-01",
    orderNo: "O-103",
    status: "PENDING",
    total: 250000,
    createdAt: ISODate("2026-11-03T10:00:00Z"),
    customer: {
      customerId: "C-1", name: "Customer A",
      email: "a@example.invalid"
    },
    items: [{ sku: "SKU-D", quantity: 2, price: 125000 }],
    internalNotes: "Payload for internal processing. ".repeat(200),
    auditTrail: []
  },
  {
    _id: 104,
    tenantId: "t-02",
    orderNo: "O-104",
    status: "PAID",
    total: 45000,
    createdAt: ISODate("2026-11-04T10:00:00Z"),
    customer: {
      customerId: "C-3", name: "Customer C",
      email: "c@example.invalid"
    },
    items: [{ sku: "SKU-E", quantity: 1, price: 45000 }],
    internalNotes: "Another tenant's data. ".repeat(200),
    auditTrail: []
  }
])
~~~

This lab contains only four documents and is not meant for benchmarking. Do not re-insert with the same `_id`s or duplicate key errors will occur. `tenantId` illustrates multi-tenant filtering; `internalNotes`/`auditTrail` simulate heavy payloads; `orderNo`, `status`, `total`, and `createdAt` suffice for the list API.

## 5. Projections with `find`

Without projection:

~~~javascript
db.orders.find({
  tenantId: "t-01",
  status: "PAID"
})
~~~

The query returns all notes, items, emails, and audit trails. For a list API, fetch only:

~~~javascript
db.orders.find(
  { tenantId: "t-01", status: "PAID" },
  {
    _id: 1,
    orderNo: 1,
    status: 1,
    total: 1,
    createdAt: 1
  }
).sort({ createdAt: -1 }).limit(30)
~~~

Projection **does not modify stored data**; it only controls what the query returns. Authorized users opening details later can still retrieve other fields via the detail endpoint.

### 5.1. Inclusion vs. Exclusion

~~~javascript
// Inclusion: only selected fields, plus _id unless excluded.
{ orderNo: 1, status: 1, total: 1 }

// Exclusion: all fields except excluded ones.
{ internalNotes: 0, auditTrail: 0 }
~~~

**Inclusion** is usually safer for public/API contracts because newly added sensitive schema fields will not accidentally leak into existing responses.

### 5.2. `_id` Is Included by Default

~~~javascript
// Want only business fields without _id:
{ _id: 0, orderNo: 1, total: 1 }
~~~

Normally, you cannot mix inclusion and exclusion in a `find` projection **except for `_id`**. For instance, `{orderNo: 1, internalNotes: 0}` is invalid in standard projections. Certain projection expressions follow specialized rules, so stick to clean explicit contracts.

### 5.3. Should You Exclude `_id`?

Exclude `_id` only when truly unneeded. `_id` is commonly required for opening detail views, updates, and tie-breaking in keyset pagination. Saving a few bytes is rarely worth losing a stable identifier on the frontend.

## 6. Projecting Nested Fields

If the UI only shows customer name without email:

~~~javascript
db.orders.find(
  { tenantId: "t-01" },
  {
    _id: 1,
    orderNo: 1,
    "customer.name": 1,
    status: 1
  }
)
~~~

MongoDB returns `customer` containing only `name` via dotted-path projection. Avoid conflicting parent and child paths in the same projection (e.g., `customer` and `customer.name`), which triggers a path collision error.

### 6.1. Projection Is Data Minimization, Not Authorization

Hiding `email` from the list reduces accidental logging and payload size, yet **does not restrict database permissions** if another account can query the collection directly. Database RBAC and application authorization must be enforced separately.

### 6.2. Tenant Filtering Must Happen on the Server

Never fetch documents for all tenants into the application and run `Array.filter`. That transfers other tenants' data over the network and into RAM, creating severe isolation risks. Always source `tenantId` from the authenticated context and pass it in the query filter.

## 7. Shrinking Array Payloads

A document holding thousands of `items` is too heavy for a list API. If the UI only needs the first three items:

~~~javascript
db.orders.find(
  { tenantId: "t-01" },
  {
    orderNo: 1,
    items: { $slice: 3 }
  }
)
~~~

`$slice` in `find` projections caps returned array elements without mutating the stored array.

### 7.1. Elements from the End

~~~javascript
db.orders.find(
  { _id: 101, tenantId: "t-01" },
  {
    orderNo: 1,
    items: { $slice: -1 }
  }
)
~~~

Negative values take elements from the end per `$slice` syntax.

### 7.2. `$elemMatch` in Projections

~~~javascript
db.orders.find(
  { _id: 101, tenantId: "t-01" },
  {
    orderNo: 1,
    items: { $elemMatch: { sku: "SKU-A" } }
  }
)
~~~

Projection `$elemMatch` returns **at most one matching element**, not all matches. To return multiple matching elements, use `$filter` in aggregation.

### 7.3. Aggregation `$filter`

~~~javascript
db.orders.aggregate([
  { $match: { _id: 101, tenantId: "t-01" } },
  {
    $project: {
      orderNo: 1,
      expensiveItems: {
        $filter: {
          input: "$items",
          as: "item",
          cond: { $gte: ["$$item.price", 40000] }
        }
      }
    }
  }
])
~~~

To cap output further:

~~~javascript
{
  $project: {
    orderNo: 1,
    previewItems: { $slice: ["$items", 2] }
  }
}
~~~

Note that this is the aggregation `$slice` expression, whose syntax differs from `find`'s `$slice` projection operator.

### 7.4. Return Counts Instead of Entire Arrays

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01" } },
  {
    $project: {
      orderNo: 1,
      itemsCount: { $size: "$items" }
    }
  }
])
~~~

`$size` requires an array input; guard missing/null fields with `$ifNull` or type checks. Never download huge arrays to the client only to read `items.length`.

## 8. `$project` and `$unset` in Aggregation

An order-listing pipeline:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 30 },
  {
    $project: {
      _id: 1,
      orderNo: 1,
      status: 1,
      total: 1,
      createdAt: 1
    }
  }
])
~~~

`$unset` strips specific fields:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01" } },
  { $unset: ["internalNotes", "auditTrail"] },
  { $limit: 30 }
])
~~~

### 8.1. Is Placing `$project` Early Always Faster?

No. The MongoDB aggregation optimizer tracks field dependencies and automatically prunes unneeded fields between stages. Adding an early `$project` purely as a "micro-optimization" often makes no difference. Usually prioritize logical `$match`/`$sort`/`$limit` first and use `$project` to shape output. If a `$lookup` or intermediate stage generates huge arrays, trimming right where they are produced can help. Verify with `explain` and workload measurements.

### 8.2. Do Not Strip Fields Still Needed Later

If you plan to sort by `createdAt`, do not drop it in an earlier `$project` before `$sort`. Keep fields needed by downstream stages unless replaced with semantically equivalent expressions.

### 8.3. Distinguish Query `$unset` from Update `$unset`

`$unset` in aggregation only shapes pipeline output. `$unset` as an update operator permanently deletes fields from stored documents. Never run an update to "shrink payload" on a read path.

## 9. Reduce Document Counts Before Reducing Bytes

An API requesting 30 `PAID` orders for a tenant:

~~~javascript
db.orders.find(
  { tenantId: "t-01", status: "PAID" },
  { _id: 1, orderNo: 1, total: 1, createdAt: 1 }
).sort({ createdAt: -1, _id: -1 }).limit(30)
~~~

Do not do this:

~~~javascript
// Anti-pattern: load entire collection into app, then filter.
const all = await orders.find({}).toArray()
const rows = all
  .filter(x => x.tenantId === "t-01" && x.status === "PAID")
  .slice(0, 30)
~~~

This bad pattern blows up network traffic and risks leaking cross-tenant data into application memory and logs.

### 9.1. Aggregate on the Server Instead of Fetching All Records

When only total revenue is needed:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  {
    $group: {
      _id: null,
      totalRevenue: { $sum: "$total" },
      ordersCount: { $sum: 1 }
    }
  },
  { $project: { _id: 0, totalRevenue: 1, ordersCount: 1 } }
])
~~~

The server sends one summary document rather than thousands of orders. Still, aggregation scans/uses indexes and consumes CPU; smaller responses do not guarantee lower total server compute.

## 10. Projections and Covered Queries

If an index contains all fields needed to **filter, sort, and return**, MongoDB can satisfy the query from the index without `FETCH`ing full documents under supported conditions.

~~~javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, orderNo: 1, total: 1 },
  { name: "idx_cover_order_list" }
)

db.orders.find(
  { tenantId: "t-01", status: "PAID" },
  { _id: 0, orderNo: 1, total: 1 }
)
~~~

This is a covered query **candidate**: `_id` is excluded since it is absent from the index. Verify that the planner picks the index and satisfies coverage rules.

### 10.1. Projection Alone Does Not Create Coverage

If the index covers only `tenantId, status` while the response requests `total`, MongoDB must still `FETCH` documents. Multikey arrays, null checks, and other query shapes impose extra restrictions. Confirm via `explain("executionStats")`.

### 10.2. Do Not Index Large Fields Arbitrarily

Bloated compound indexes carrying rarely used fields raise storage, cache pressure, and write amplification. Reserve covered indexes for critical queries with compact fields and stable shapes.

### 10.3. Coverage Differs from Compression

Covered queries eliminate server document fetches; projections shrink BSON output; wire compression shrinks message bytes over the network. They complement each other but solve different layers.

## 11. Pagination to Avoid Returning Millions of Documents

For lists, bound the records per response:

~~~javascript
db.orders.find(
  { tenantId: "t-01", status: "PAID" },
  { _id: 1, orderNo: 1, total: 1, createdAt: 1 }
).sort({ createdAt: -1, _id: -1 }).limit(30)
~~~

Never trust arbitrary `limit` values from clients, such as 500,000. Enforce a maximum `pageSize` and field projections per endpoint.

### 11.1. Offset Pagination

~~~javascript
db.orders.find(
  { tenantId: "t-01", status: "PAID" },
  { orderNo: 1, total: 1, createdAt: 1 }
).sort({ createdAt: -1, _id: -1 })
 .skip(30000)
 .limit(30)
~~~

The response carries only 30 records, yet the server scans and skips 30,000 preceding entries. A small network response cannot save deep-offset server work.

### 11.2. Keyset Pagination

With a deterministic sort `createdAt: -1, _id: -1`, save the key pair of the last item from the prior page:

~~~javascript
const lastCreatedAt = ISODate("2026-11-02T10:00:00Z")
const lastId = 102

db.orders.find(
  {
    tenantId: "t-01",
    status: "PAID",
    $or: [
      { createdAt: { $lt: lastCreatedAt } },
      { createdAt: lastCreatedAt, _id: { $lt: lastId } }
    ]
  },
  { _id: 1, orderNo: 1, total: 1, createdAt: 1 }
).sort({ createdAt: -1, _id: -1 }).limit(30)
~~~

Candidate index:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: -1 }
)
~~~

### 11.3. Why Is a Tie-Breaker Needed?

Two records can share the exact same `createdAt`. Sorting only by timestamp causes unstable ordering and skipped or duplicated rows across pages. Unique `_id` is a standard tie-breaker.

### 11.4. Keyset Pagination Does Not Automatically Guarantee Snapshot Consistency

If sort keys mutate or documents are deleted while paging, items can shift across pages. Reports needing strict point-in-time snapshots require appropriate read concern / snapshot strategies, not just continuation tokens.

## 12. Avoiding N+1 Reads

An API loads 100 orders and issues individual `findOne` calls for each customer's name:

~~~javascript
// Conceptual anti-pattern:
for (const order of orders) {
  const customer = await customers.findOne({
    _id: order.customerId
  })
}
~~~

This triggers 101 logical database calls, crippling performance over high RTT links. Better approach:

1. Collect unique customer IDs.
2. Chunk IDs into reasonable batches.
3. Query each batch via `$in`.
4. Project only ID and `displayName`.
5. Join in application memory by ID.

~~~javascript
db.customers.find(
  {
    tenantId: "t-01",
    _id: { $in: ["C-1", "C-2", "C-3"] }
  },
  { _id: 1, displayName: 1 }
)
~~~

The `customers` collection here illustrates the access pattern and is not part of the initial orders lab seed. Huge `$in` arrays inflate command size and planner work; chunk IDs sensibly.

### 12.1. `$lookup` Can Replace Multiple Requests

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  { $sort: { createdAt: -1 } },
  { $limit: 30 },
  {
    $lookup: {
      from: "customers",
      let: { id: "$customer.customerId", tenant: "$tenantId" },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$_id", "$$id"] },
                { $eq: ["$tenantId", "$$tenant"] }
              ]
            }
          }
        },
        { $project: { _id: 1, displayName: 1 } }
      ],
      as: "customerInfo"
    }
  },
  { $project: { orderNo: 1, total: 1, customerInfo: 1 } }
])
~~~

Limiting before `$lookup` is valid when joining the 30 newest orders; if sorting by a joined field first, restructure the pipeline. Foreign indexes and cardinality govern performance.

### 12.2. Watch Out for Fan-Out

A 1:N join can produce massive embedded arrays hitting the 16 MiB BSON document limit. If only counts or totals are needed, compute them server-side with `$count` or `$group` inside the foreign pipeline instead of returning every child record.

## 13. Cursors: `firstBatch` and `getMore`

When a `find` matches many documents, the server returns `firstBatch` along with a cursor ID; the driver issues `getMore` as batches are consumed.

~~~mermaid
sequenceDiagram
    participant App as Driver
    participant DB as MongoDB
    App->>DB: find(filter, projection, batchSize)
    DB-->>App: firstBatch + cursorId
    App->>App: Process documents
    App->>DB: getMore(cursorId)
    DB-->>App: nextBatch
    App->>DB: getMore(cursorId)
    DB-->>App: finalBatch or cursor exhausted
~~~

### 13.1. `batchSize` Does Not Cap Total Documents

~~~javascript
db.orders.find({ tenantId: "t-01" }).batchSize(100)
~~~

The query still returns thousands of records across multiple batches. To cap total results:

~~~javascript
db.orders.find({ tenantId: "t-01" })
  .limit(1000)
  .batchSize(200)
~~~

Here `limit=1000` caps total records, while `batchSize=200` tunes batch sizing subject to server/driver limits.

### 13.2. Batch Size Is a Hint, Not a Guarantee

A batch can be capped earlier by response byte limits and cursor execution rules. Never assume `batchSize(200)` always returns exactly 200 documents, especially with large documents.

### 13.3. `firstBatch` Defaults Can Differ

MongoDB applies default count/byte bounds for `firstBatch` and subsequent `getMore` calls. Documentation often mentions ~101 documents for `firstBatch` when unspecified, yet never hardcode that as an invariant across all queries, drivers, and versions.

### 13.4. Cursor Batches Are Not HTTP Pages

API page size is the max items returned to the frontend. Driver batch size governs chunks read from MongoDB to serve an API or job. A 30-item HTTP page might fit in one cursor batch, or a backend might use a different query; they are separate contracts.

## 14. Choosing `batchSize` Based on Document Bytes

Suppose:

| Property | Dataset A | Dataset B |
|---|---|---|
| Average projected doc | 500 bytes | 40 KiB |
| Requested batch | 1,000 docs | 1,000 docs |
| Approximate total BSON | 0.5 MiB | 40 MiB |

For A, a batch of 1,000 is lightweight. For B, it nears common wire message limits, forcing splitting, higher memory usage, and latency spikes. These numbers are purely mathematical illustrations.

### 14.1. Batch Too Small

`batchSize=1` across 20,000 docs triggers thousands of `getMore` calls, making RTT the bottleneck.

### 14.2. Batch Too Large

`batchSize=10000` balloons per-request RAM, delays time-to-first-result, and drives GC pressure across concurrent cursors. Fewer `getMore` calls do not guarantee better p99.

### 14.3. Trade-Off Table

| Batch Size | Round Trips | Client Memory | Best For |
|---|---|---|---|
| Small | Potentially many | Lower | Streaming, slow clients |
| Moderate | Balanced | Balanced | Most jobs |
| Very large | Fewer until caps hit | Potentially high | Tiny docs, high RTT, benchmarked |

No single `batchSize` fits every collection.

## 15. Node.js Driver: Projection + Streaming Cursor

~~~javascript
import { MongoClient } from "mongodb"

const client = new MongoClient(process.env.MONGODB_URI, {
  maxPoolSize: 30
})
await client.connect()

try {
  const orders = client.db("network_optimization_lab")
    .collection("orders")

  const cursor = orders.find(
    { tenantId: "t-01", status: "PAID" },
    {
      projection: {
        _id: 1,
        orderNo: 1,
        status: 1,
        total: 1,
        createdAt: 1
      },
      batchSize: 200,
      limit: 1000
    }
  ).sort({ createdAt: -1, _id: -1 })

  try {
    for await (const order of cursor) {
      // Process each document; avoid logging PII in production.
      console.log(order.orderNo, order.total)
    }
  } finally {
    await cursor.close()
  }
} finally {
  await client.close()
}
~~~

### 15.1. Why Use an Iterator?

`for await` consumes results incrementally. `toArray()` buffers all returned results into RAM: even with `batchSize=100`, the final array can hold millions of documents.

### 15.2. When Is `toArray()` Still Fine?

For a paginated query with `limit(30)` and compact documents, `toArray()` is clean and convenient:

~~~javascript
const rows = await orders.find(
  { tenantId: "t-01", status: "PAID" },
  { projection: { _id: 1, orderNo: 1, total: 1 } }
).limit(30).toArray()
~~~

Avoid unbounded `toArray()` on large jobs.

### 15.3. Close Cursors

If an app stops early after 100 records or hits an error, close the cursor to free server and client resources. Use `try/finally` or driver-supported lifecycle management.

## 16. Java Sync Driver: Cursor Batching and Projection

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

public class EfficientOrderReader {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> orders = client
                .getDatabase("network_optimization_lab")
                .getCollection("orders");

            try (MongoCursor<Document> cursor = orders.find(
                    Filters.and(
                        Filters.eq("tenantId", "t-01"),
                        Filters.eq("status", "PAID")
                    ))
                .projection(Projections.fields(
                    Projections.include(
                        "orderNo", "total", "status", "createdAt"
                    ),
                    Projections.excludeId()
                ))
                .sort(Sorts.descending("createdAt", "_id"))
                .limit(1000)
                .batchSize(200)
                .iterator()) {

                while (cursor.hasNext()) {
                    Document order = cursor.next();
                    System.out.println(order.getString("orderNo"));
                }
            }
        }
    }
}
~~~

Try-with-resources closes `MongoCursor`. Replacing the loop with `into(new ArrayList<>())` on an unbounded query still loads everything into RAM regardless of `batchSize`.

### 16.1. Object Mapping Consumes CPU Too

POJO deserialization, JSON conversion, and GC overhead rise when passing unused fields through the driver. Projections save both network bytes and Java heap allocations.

### 16.2. Connection Pooling

Never instantiate a new `MongoClient` per document or HTTP request. Reuse a client pool scoped to service lifecycle to avoid DNS, topology discovery, and TLS handshake overhead.

## 17. API Page Size Differs from Cursor Batch Size

An API:

~~~text
GET /orders?pageSize=30&cursor=...
~~~

can execute `limit(31)` to detect whether a next page exists, while the MongoDB cursor uses `batchSize=100` for transport. Distinct parameters:

| Parameter | Layer | Meaning |
|---|---|---|
| HTTP `pageSize=30` | API | Max records shown to the frontend |
| MongoDB `limit(31)` | Query | Max 31 records fetched by backend to determine `hasNext` |
| MongoDB `batchSize(100)` | Cursor | MongoDB batch chunking within wire limits |

Never pass a MongoDB `cursorId` directly to a browser as a persistent pagination token; it relies on server cursor lifetimes and protocols. Encode an application token containing seek keys and authorization checks.

## 18. `bulkWrite`: Batching Multiple Writes

A job updating 50,000 orders with 50,000 sequential `updateOne` calls wastes huge round-trip time. Use `bulkWrite`:

~~~javascript
const orders = db.getSiblingDB("network_optimization_lab").orders

orders.bulkWrite([
  {
    updateOne: {
      filter: { _id: 101, tenantId: "t-01" },
      update: { $set: { status: "SHIPPED" } }
    }
  },
  {
    updateOne: {
      filter: { _id: 102, tenantId: "t-01" },
      update: { $set: { status: "SHIPPED" } }
    }
  }
], { ordered: false })
~~~

Use only on lab data; production order state transitions require full business workflow validation.

### 18.1. Ordered vs. Unordered

| Setting | General Semantics |
|---|---|
| `ordered: true` | Executes sequentially; stops at first error per API rules |
| `ordered: false` | May continue processing remaining operations on error; order is not guaranteed |

`ordered: false` suits independent operations. If operation B depends on A, do not switch to unordered merely for higher throughput.

### 18.2. Bulk Is Not a Transaction

A `bulkWrite` batch is **not atomic across the entire batch**. Earlier operations may succeed before a validation or duplicate-key failure occurs. If all-or-nothing atomicity is required, evaluate multi-document transactions and their constraints—never try to abuse one giant bulk write as a transaction.

### 18.3. Partial Failures

When the driver throws a bulk exception, inspect which operations succeeded and which errors are retryable. Blindly retrying the whole batch can duplicate `$inc` or other non-idempotent writes.

## 19. Node.js: Chunking Bulk Writes into Reasonable Batches

~~~javascript
async function writeInBatches(collection, operations, batchMaxOps = 500) {
  if (!Number.isInteger(batchMaxOps) || batchMaxOps <= 0) {
    throw new Error("INVALID_BATCH_MAX_OPS")
  }

  for (let start = 0; start < operations.length; start += batchMaxOps) {
    const batch = operations.slice(start, start + batchMaxOps)
    await collection.bulkWrite(batch, { ordered: false })
  }
}
~~~

`500` is purely an illustrative limit to bound memory and error scope, **not a universal MongoDB optimal default**. For huge inputs, stream-build and flush batches incrementally instead of loading all operations into an array upfront.

### 19.1. Counting Operations Alone Is Insufficient

500 tiny updates might be a few KiB, whereas 500 inserts with 200 KiB documents total ~100 MiB. Account for **byte budgets**, concurrency, partial errors, and driver message splitting.

### 19.2. Drivers Split Messages When Needed

Modern drivers split batches automatically to stay within operation-count and message-byte limits; applications must still bound in-memory objects, retries, and primary write pressure.

### 19.3. Write Concern and Correctness

Never weaken write concern or durability just to improve network benchmarks if the business requires majority acknowledgements. Latency tuning must not compromise durability guarantees.

## 20. `insertMany` and Server-Side `updateMany`

~~~javascript
db.events.insertMany([
  { _id: "E-1", tenantId: "t-01", type: "CREATED" },
  { _id: "E-2", tenantId: "t-01", type: "PAID" },
  { _id: "E-3", tenantId: "t-01", type: "SHIPPED" }
], { ordered: false })
~~~

The `events` collection is part of the lab examples and may not exist yet. Re-inserting identical IDs causes duplicate key errors. Batching cuts command overhead, not the total stored document bytes.

When a uniform bulk update condition applies and semantics permit:

~~~javascript
db.orders.updateMany(
  {
    tenantId: "t-01",
    status: "PENDING",
    createdAt: { $lt: ISODate("2026-11-01T00:00:00Z") }
  },
  { $set: { status: "EXPIRED" } }
)
~~~

This runs server-side, avoiding pulling documents to the app and writing them back individually. However, `updateMany` bypasses per-order side effects or application validations in one-by-one workflows; verify semantics before switching.

## 21. BSON and Wire Protocol Limits

Distinguish MongoDB's protocol limits:

| Limit | Meaning |
|---|---|
| `maxBsonObjectSize` | Max single BSON document size, typically 16 MiB |
| `maxMessageSizeBytes` | Max single MongoDB wire message size, commonly ~48 MiB across versions |
| `maxWriteBatchSize` | Max operations in a single write batch, typically 100,000 |
| Batch byte limits | Server may return fewer documents than requested `batchSize` |

Inspect live values via `hello`:

~~~javascript
const hello = db.adminCommand({ hello: 1 })

printjson({
  maxBsonObjectSize: hello.maxBsonObjectSize,
  maxMessageSizeBytes: hello.maxMessageSizeBytes,
  maxWriteBatchSize: hello.maxWriteBatchSize
})
~~~

### 21.1. Do Not Confuse 16 MiB with a Collection Limit

A collection can hold vast numbers of documents; the BSON limit applies **per document**. Compression does not make a 20 MiB BSON document valid just because its compressed wire bytes drop below 16 MiB.

### 21.2. Do Not Treat the Protocol Maximum Batch as a Recommendation

`maxWriteBatchSize` is a hard protocol ceiling, not a recommendation to fire 100,000-op batches routinely. Size batches around payload bytes, RTT, CPU, write contention, concurrency, and retry granularity.

## 22. Java Sync Driver: `bulkWrite`

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.BulkWriteOptions;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.UpdateOneModel;
import com.mongodb.client.model.Updates;
import com.mongodb.client.model.WriteModel;
import org.bson.Document;
import java.util.List;

public class BulkUpdateDemo {
    public static void main(String[] args) {
        try (MongoClient client =
                MongoClients.create(System.getenv("MONGODB_URI"))) {
            MongoCollection<Document> orders = client
                .getDatabase("network_optimization_lab")
                .getCollection("orders");

            List<WriteModel<Document>> writes = List.of(
                new UpdateOneModel<>(
                    Filters.and(
                        Filters.eq("_id", 101),
                        Filters.eq("tenantId", "t-01")
                    ),
                    Updates.set("status", "SHIPPED")
                ),
                new UpdateOneModel<>(
                    Filters.and(
                        Filters.eq("_id", 102),
                        Filters.eq("tenantId", "t-01")
                    ),
                    Updates.set("status", "SHIPPED")
                )
            );

            orders.bulkWrite(
                writes,
                new BulkWriteOptions().ordered(false)
            );
        }
    }
}
~~~

In production, catch and inspect `MongoBulkWriteException`, track per-operation outcomes, and retry strictly per idempotency policy. Never just print "bulk failed" and replay non-idempotent updates blindly.

## 23. What Is Wire Compression?

MongoDB supports **wire protocol compression** between server and driver when both sides share a supported codec. During connection handshake, both advertise compression capabilities and negotiate a shared algorithm for eligible messages.

~~~mermaid
sequenceDiagram
    participant Driver as MongoDB Driver
    participant Server as mongod/mongos
    Driver->>Server: Handshake / hello, compressor capabilities
    Server-->>Driver: Hello response / supported compressors
    Note over Driver,Server: Negotiate shared codec if available
    Driver->>Server: Potentially compressed request message
    Server-->>Driver: Potentially compressed response message
    Driver->>Driver: Decompress then decode BSON
~~~

### 23.1. Compression Is Not Encryption

Compression merely shrinks bytes; anyone holding the bytes and codec can decompress them. **TLS** provides confidentiality and integrity; a connection with `zstd` but no TLS does not satisfy encrypted transport requirements.

### 23.2. Not Every Message Is Compressed

Handshakes, tiny messages, and certain protocol messages are not compressed. Enabling a compressor will not shrink every single packet by a fixed percentage.

### 23.3. Encryption and Compression Operate at Separate Layers

A connection can use both TLS and wire compression per protocol and runtime support. Never disable TLS to try to boost compression throughput in production.

## 24. Comparing `snappy`, `zlib`, and `zstd`

| Codec | Typical Tendency | Trade-Offs |
|---|---|---|
| **snappy** | Very fast compression/decompression, moderate ratio | Saves fewer bytes than stronger codecs |
| **zlib** | Tunable compression levels; strong ratio on text | CPU scales with level; can raise latency |
| **zstd** | Often strong balance of ratio and speed across workloads | Requires driver, server, and runtime support |

No single codec is universally best. Results vary by payload:

- Repetitive text and uniform schemas compress heavily.
- Random bytes, ciphertext, JPEG, and MP4 barely compress further.
- Responses of a few dozen bytes cost more in codec overhead than they save.

### 24.1. Heavy Compression Can Slow Requests Down

If server and app share a high-speed local network, saving a few KiB may not pay back compression/decompression CPU. Over bandwidth-constrained WAN links, the trade-off can flip. Measure p95/p99 and CPU rather than looking only at compression ratios.

### 24.2. Compression Ratio Is Not Latency Ratio

Shrinking a message from 10 MiB to 3 MiB does not make a request 3.3× faster. Server query execution, serialization, connection wait, and compression CPU can dominate total duration.

## 25. Server Configuration for Wire Compression

On self-managed servers supporting these codecs:

~~~yaml
net:
  compression:
    compressors: zstd,snappy,zlib
~~~

This is an **illustrative compression snippet**, not a complete `mongod.conf`. TLS, authorization, bind addresses, and replication/sharding configs must be configured properly. Verify exact option syntax and codec support against your MongoDB version.

### 25.1. A Shared Codec Is Required

If the server enables only `snappy` while the client requests only `zstd`, `zstd` cannot be used. Depending on driver/protocol, the connection falls back to uncompressed traffic. Verify actual negotiation rather than reading only one side's config.

### 25.2. Sharded Clusters Have Two Network Hops

~~~text
Application --TLS/negotiated compression--> mongos
mongos --TLS/negotiated compression--> shard mongod
~~~

Client compression to `mongos` does not prove internal `mongos`→shard traffic uses the same codec. Verify and configure across all network segments.

### 25.3. Storage Compression Is Not Wire Compression

WiredTiger compression shrinks data on disk. `net.compression.compressors` governs network messages. A deployment using storage compression still sends uncompressed wire messages unless wire compression is negotiated.

## 26. Node.js: Enabling Compressors

~~~javascript
import { MongoClient } from "mongodb"

const client = new MongoClient(process.env.MONGODB_URI, {
  compressors: ["zstd", "snappy", "zlib"],
  zlibCompressionLevel: 6
})

await client.connect()

try {
  console.log(
    await client.db("admin").command({ ping: 1 })
  )
} finally {
  await client.close()
}
~~~

Depending on the MongoDB Node.js Driver version, `snappy`/`zstd` may require optional native packages. Missing dependencies can prevent codec usage or fail initialization; check driver docs, logs, and deployment artifacts.

### 26.1. URI Compressors

Some drivers support URI parameters:

~~~text
mongodb://mongo1.db.internal:27017/?tls=true&compressors=zstd,snappy,zlib
~~~

Verify parser version and installed packages. Never leak real usernames or passwords into shared logs.

### 26.2. `zlibCompressionLevel`

Higher levels improve ratio at the expense of CPU and latency. This setting applies only when `zlib` is negotiated and supported. Do not crank levels up blindly.

### 26.3. Connection Pools and Negotiated State

Pool connections negotiate compression upon creation. Existing pooled connections do not adopt new compressor settings until recycled; roll out changes properly and benchmark at steady state.

## 27. Java Driver: Configuring Compressors

In the Java Sync Driver, compressor options can be supplied via the connection string in supported versions:

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.bson.Document;

public class CompressionDemo {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        // URI from secret/config:
        // mongodb://mongo1.db.internal:27017/
        // ?tls=true&compressors=zstd,snappy,zlib

        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .build();

        try (MongoClient client = MongoClients.create(settings)) {
            Document ping = client.getDatabase("admin")
                .runCommand(new Document("ping", 1));
            System.out.println(ping.toJson());
        }
    }
}
~~~

Verify classpath dependencies for the requested codecs per Java Driver version—do not assume `zstd`/`snappy` libraries exist in every runtime. Keep TLS certificate validation enabled.

## 28. Wire Compression Differs from HTTP Compression

An application has two distinct network hops:

~~~text
MongoDB -> Backend API -> Browser
~~~

MongoDB wire compression affects the MongoDB→backend hop. The backend then converts BSON to JSON for HTTP responses; HTTP `Content-Encoding: gzip`/`br` is an **entirely separate mechanism**. Enabling `zstd` in the MongoDB driver does not shrink bytes sent to browsers.

### 28.1. Already-Compressed Content

For JPEG, MP4, compressed PDFs, or encrypted binaries, re-compressing yields little savings while burning CPU. For large media, consider streaming, GridFS, object storage/CDN, thumbnails, or lazy loading instead of embedding binaries in list APIs.

### 28.2. Base64 JSON

Converting binary blobs into Base64 strings inside JSON expands payload size and increases parsing overhead. When appropriate, stream raw binaries via a dedicated endpoint with proper authorization and caching.

## 29. Measuring Document Sizes with `$bsonSize`

MongoDB aggregation can compute BSON byte sizes:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01" } },
  {
    $project: {
      orderNo: 1,
      rawBsonBytes: { $bsonSize: "$$ROOT" }
    }
  }
])
~~~

To measure post-projection shape:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01" } },
  {
    $project: {
      orderNo: 1,
      status: 1,
      total: 1,
      createdAt: 1
    }
  },
  {
    $project: {
      projectedBsonBytes: { $bsonSize: "$$ROOT" }
    }
  }
])
~~~

### 29.1. Output Is Not Wire Bytes

`$bsonSize` measures the BSON document itself, excluding wire protocol headers, compression ratios, TLS framing, or HTTP JSON output. It evaluates projection savings rather than exact network traffic.

### 29.2. Watch Outliers

Average document size can mask documents carrying massive arrays near the BSON limit. When choosing batch sizes, check p95/p99 document sizes and extreme outliers.

## 30. `explain()` for Query Plans

~~~javascript
db.orders.explain("executionStats").find(
  { tenantId: "t-01", status: "PAID" },
  { _id: 0, orderNo: 1, total: 1 }
)
~~~

Inspect:

- `nReturned`.
- `totalKeysExamined` and `totalDocsExamined`.
- Selected index.
- Presence of `COLLSCAN`, `FETCH`, or index-only execution depending on engine/version.
- Query execution statistics within `explain` scope.

### 30.1. `explain` Is Not a Wire Profiler

`explain` does not report compressed response bytes or TCP packet counts. Projection can slash response bytes while `docsExamined` remains huge if the query lacks a good index.

### 30.2. Only Semantically Identical Queries Are Comparable

When running before/after benchmarks, keep filters, sorts, limits, read concerns, and business results identical. A version that looks "faster" because it accidentally dropped 90% of rows is not a valid optimization.

## 31. Network Counters and Monitoring

With appropriate privileges, inspect:

~~~javascript
const network = db.adminCommand({ serverStatus: 1 }).network
printjson(network)
~~~

Depending on version, `network` stats may expose `bytesIn`, `bytesOut`, `numRequests`, and compression metrics. These counters are **process-wide**, not isolated to one HTTP request or query.

### 31.1. Do Not Infer Per-Request Bytes from Production `serverStatus`

If 300 clients hit production concurrently, a 10-second `bytesOut` delta aggregates all workloads. To measure per-query savings, use an isolated test environment or client/network instrumentation.

### 31.2. Driver Command Monitoring

Driver command monitoring can count `find`/`getMore`/bulk requests. However, logging raw command payloads can expose sensitive data and add overhead. Enable payload logging only in test environments or with strict redaction/sampling.

### 31.3. Measure Both Sides

When `mongos`, load balancers, or API gateways sit in the path, measure bytes at the exact network hop you aim to optimize. Server egress, client ingress, and HTTP egress differ due to compression and serialization.

## 32. Measuring BSON Size in Node.js

Depending on the MongoDB Node.js Driver version, BSON utilities can calculate sample object sizes:

~~~javascript
import { BSON } from "mongodb"

const sample = {
  orderNo: "O-101",
  status: "PAID",
  total: 120000
}

console.log(BSON.calculateObjectSize(sample))
~~~

This measures the BSON representation of `sample`, **not** wire compression or HTTP payload. If real records use BSON types distinct from plain JS objects, verify against actual documents.

Never call `toArray()` on millions of documents just to measure size; sample or use `$bsonSize` server-side.

## 33. Fair Optimization Benchmarking

To evaluate projection, batching, and compression, build a test matrix:

| Variable | Options |
|---|---|
| Projection | Full / list fields / array preview |
| Cursor `batchSize` | 20 / 100 / 500 / 2000 |
| Compressor | None / `snappy` / `zlib` / `zstd` where supported |
| Dataset | Text / small docs / pre-compressed binary |
| Network | Same region / cross-region / simulated latency |
| Concurrency | 1 / 10 / 50 workers |

Collect on every run:

1. Returned document and field counts.
2. Estimated raw BSON size.
3. Measured network bytes on the target hop.
4. Number of `find`/`getMore` calls and round trips.
5. Server/client CPU, RSS, GC pauses, and pool checkout wait.
6. Latency p50/p95/p99, throughput, and timeout/error rates.
7. Index plan and `docsExamined`.
8. Correctness checks: row counts and business invariants.

### 33.1. Warm-Up

Initial connections include DNS, TLS handshakes, topology discovery, and cold caches. Never compare a warm baseline against a cold variant. Run warm-up iterations and measure steady state on identical data.

### 33.2. Change One Variable at a Time

If you add an index, apply projection, and enable `zstd` simultaneously, you cannot isolate which change helped most. Benchmark individually, then test combinations.

### 33.3. Averages Are Insufficient

A massive batch size might improve mean throughput while worsening p99 due to outlier documents or GC pauses. Inspect full latency distributions and peak concurrency.

## 34. When to Choose Projection, Batching, or Compression?

~~~mermaid
flowchart TD
    Start["Slow API/job or high network bytes"] --> Extra{"Returning extra fields/docs?"}
    Extra -->|"Yes"| Project["Filter, projection, limit, pagination"]
    Extra -->|"No"| RTT{"Many getMore / N+1 / write calls?"}
    Project --> RTT
    RTT -->|"Yes"| Batch["Cursor batching, bulkWrite, batch fetch"]
    RTT -->|"No"| Bandwidth{"Bandwidth bottleneck and compressible data?"}
    Batch --> Bandwidth
    Bandwidth -->|"Yes"| Compress["Benchmark snappy, zlib, zstd"]
    Bandwidth -->|"No"| Plan["Check query plan, disk, CPU, locks"]
    Compress --> Measure["Measure end-to-end latency, bytes, CPU, correctness"]
    Plan --> Measure
~~~

Generally prioritize **trimming unneeded data first**, then cutting round trips, and finally testing wire compression if network bandwidth remains significant. Still, real priorities depend on workload; avoid treating this flow as an inflexible law.

## 35. Security Considerations When Shrinking Payloads

Projection limits sensitive fields appearing in responses and logs, yet **does not replace** authentication and authorization. Tenant filters must always derive from an authenticated principal.

Wire compression is not a security control. Keep TLS and certificate validation enabled. In certain protocols, compressed payload lengths can leak information via side channels if an attacker controls part of the input and observes packet sizes. Risk depends on your threat model and trust boundaries; assess carefully for highly sensitive data.

### 35.1. Do Not Use Compression to "Hide" Secrets

A password or API key inside a compressed payload is still present and trivially decoded by the client. The right fix is never projecting secrets, enforcing permissions, and limiting log exposure.

### 35.2. Optimization Must Never Lower Durability

Never weaken read/write concern, drop tenant filters, or skip validation solely to win benchmark latency. Those alter **business semantics and risk**, not merely network overhead.

## 36. Practice Exercise A — Projection

Using the lab `orders` collection:

1. Query all fields for orders matching `tenantId: "t-01", status: "PAID"`.
2. Query the same filter returning only `_id`, `orderNo`, `total`, and `createdAt`.
3. Explain which fields drove the largest byte reduction.
4. Why must tenant filtering never run in app code after fetching everything?

## 37. Practice Exercise B — Large Arrays

Write a projection returning only the first two `items`. Write an aggregation returning only `itemsCount`. Explain why `$elemMatch` in a projection does not return all matching elements like `$filter`.

## 38. Practice Exercise C — Covered Query

Given index `{tenantId: 1, status: 1, orderNo: 1, total: 1}`. Write a covered query candidate, explain `_id: 0`, and inspect `explain` for `FETCH`. Why should you not add a long notes field into the index just to cover a query?

## 39. Practice Exercise D — `batchSize` and `limit`

A job needs to read up to 10,000 docs:

1. Does `batchSize(200)` cap total returned docs at 200?
2. Does `limit(10000)` fix an exact number of `getMore` calls?
3. Why can a batch of 200 docs × 1 MiB/doc hit byte limits?
4. When should you prefer a stream/iterator over `toArray()`?

## 40. Practice Exercise E — Pagination

Design an API listing 30 orders sorted by `createdAt: -1, _id: -1` with a continuation key for the next page. Pick a candidate index. Compare against `skip(30000)` on network response and server work.

## 41. Practice Exercise F — N+1 and Joins

An API reads 200 orders and queries 200 customers sequentially. Count logical DB calls and propose a batched `$in` with projection or `$lookup` with foreign projection. Why must tenant filtering and fan-out bounds be enforced?

## 42. Practice Exercise G — Bulk Operations

Write a `bulkWrite` updating three independent orders with `ordered: false`. Explain what happens to the other operations if one fails, whether bulk is atomic across the whole batch, and why blindly retrying `$inc` operations is risky.

## 43. Practice Exercise H — Codecs

Measure the same text dataset across four configurations: uncompressed, `snappy`, `zlib`, and `zstd` (where supported). Record bytes, CPU, p95, p99, and throughput. Explain why the best codec for text may perform poorly on JPEG/MP4.

## 44. Practice Exercise I — Storage vs. Wire

A teammate says: "WiredTiger already has `snappy` enabled, so the MongoDB driver receives compressed data over the network." Correct the statement, distinguishing `storage compression`, `wire compression`, and TLS.

## 45. Practice Exercise J — Observability

Measure `serverStatus().network` before and after a workload in an isolated lab. Use `$bsonSize` to measure raw BSON docs and driver command monitoring to count `getMore` calls if permitted.

Why must production network counters never be interpreted as bytes for a single query? Why do raw BSON bytes differ from compressed wire bytes?

## 46. Practice Exercise K — Binary Documents

A list API returns 100 records, each carrying a 2 MiB JPEG image even though the UI only needs a thumbnail URL. Choose projections, design the detail API, and decide how to serve binaries. Should you expect `zstd` to shrink JPEGs by 90%?

## 47. Practice Exercise L — Regression After Raising Batch Size

After raising `batchSize` from 100 to 10,000, `getMore` count drops while RSS and p99 climb. Form hypotheses covering memory, GC, outlier documents, concurrency, and byte limits. Rebuild a benchmark testing moderate batch sizes.

## 48. Practice Answer Hints

**A:** Inclusion projection `{_id: 1, orderNo: 1, total: 1, createdAt: 1}` strips notes and arrays; server-side tenant filtering enforces isolation and cuts transfer volume.

**B:** `{items: {$slice: 2}}` caps array output; aggregation `$size: "$items"` returns count; projection `$elemMatch` returns a single element, unlike `$filter`.

**C:** Filtering on tenant/status and projecting `{_id: 0, orderNo: 1, total: 1}` enables an index-only candidate; verify with `explain` and avoid indexing oversized text fields.

**D:** `batchSize` does not cap total docs; `limit` does. `getMore` counts depend on server/driver/document size. Cursor iterators prevent holding all results in RAM.

**E:** Keyset pagination uses the last `(createdAt, _id)` pair and tenant filter; index `{tenantId: 1, status: 1, createdAt: -1, _id: -1}`. `skip` forces the server to walk discarded entries.

**F:** 201 logical calls (1 orders query + 200 customer queries). Batch IDs or join, preserve tenant isolation, and optimize cardinality/indexes.

**G:** Unordered allows independent operations to continue on error; bulk is not atomic across the batch. Retrying non-idempotent updates can duplicate side effects.

**H:** Text compresses strongly; already-compressed images/video compress poorly. Pick codecs from real measured wire bytes, CPU, and latency.

**I:** WiredTiger compression shrinks disk storage; wire compression requires negotiation between server and driver; TLS encrypts traffic.

**J:** Server counters are process-wide, `$bsonSize` measures raw BSON, and compressed wire bytes depend on codec and message sizes. Measure in isolation.

**K:** Omit JPEG binaries from lists, return thumbnail URLs, and serve files via dedicated endpoints using GridFS/object storage/CDN; do not expect heavy compression on JPEGs.

**L:** Fewer `getMore` calls do not prove lower latency; check bytes/doc, memory, GC, concurrency, and response limits across moderate batch sizes.

## 49. Common Errors and Troubleshooting

| Symptom | Possible Cause | Fix |
|---|---|---|
| List API returns MiB of data | Returning full documents | Inclusion projection, pagination |
| `_id` still appears | `_id` not excluded | Add `_id: 0` if truly unneeded |
| Projection path collision error | Conflicting parent/child paths | Fix projection paths |
| Query still slow despite tiny response | Missing index, high `docsExamined` | Run `explain`, optimize query/index |
| Covered query does not trigger | Index missing field or multikey rules | Check winning plan / `FETCH` |
| `batchSize` returns fewer than N docs | Wire byte caps / cursor limits | Measure actual batches and `getMore` |
| App OOM despite small `batchSize` | `toArray()` buffers everything | Use streaming iterator |
| Excessive `getMore` calls | Batch size too small | Increase reasonably and benchmark |
| Large batch hurts p99 | Memory/GC/time-to-first-byte | Shrink or tune batch size |
| `bulkWrite` partial errors | Subset of operations failed | Inspect errors and retry policy |
| Duplicate side effects after retry | Non-idempotent updates | Use stable IDs and guarded retries |
| Compression saves no bytes | Incompressible data / unnegotiated codec | Check support and payload types |
| Compression spikes CPU | Codec/level too heavy | Benchmark lighter codecs/levels |
| `zstd`/`snappy` fails to activate | Missing dependencies / version mismatch | Verify driver codec packages |
| Frontend still slow | Large HTTP JSON payload | Optimize API→browser hop |
| `$lookup` hits BSON size limit | Large array fan-out | Foreign projection or `$count`/`$group` |
| Pagination skips/duplicates rows | Non-unique sort key | Add tie-breaker and keyset seek |
| Network metrics noisy | Multi-client production traffic | Benchmark in isolation |

## 50. Review Questions

**1. What does projection reduce?** — Unneeded BSON fields returned, decoding work, and network payload.

**2. Does `{a: 1, b: 1}` return `_id`?** — Yes, unless `_id: 0` is specified.

**3. Can you freely mix `a: 1` and `b: 0`?** — No under standard rules, except for `_id`.

**4. When is `$slice` projection used?** — When the UI needs only a slice of an embedded array.

**5. Does `$elemMatch` projection return all matches?** — No; use aggregation `$filter` for multiple matches.

**6. Is placing `$project` first in a pipeline always faster?** — No; the optimizer already prunes unneeded fields in many cases.

**7. What is a covered query?** — A query served solely from index keys without `FETCH`ing documents when all rules are met.

**8. Does projection alone make a query covered?** — No; indexes and query shape must align.

**9. Does `batchSize(100)` cap total results at 100 records?** — No; use `limit` for total caps.

**10. What is `getMore`?** — The command requesting the next batch from an open server cursor.

**11. Can `toArray()` cause OOM?** — Yes, when materializing huge result sets in memory.

**12. Do larger batches always lower p99?** — No; memory pressure, byte limits, and GC pauses can raise tail latency.

**13. Is API `pageSize` the same as MongoDB `batchSize`?** — No; they operate at different layers.

**14. What does deep `skip` cost?** — The server must scan and discard all skipped entries.

**15. Why are N+1 queries harmful?** — They multiply round trips and per-command overhead.

**16. Is `bulkWrite` atomic across the whole batch?** — Not by default.

**17. When does `ordered: false` fit?** — Independent operations with proper per-item error handling.

**18. Can compression bypass the 16 MiB BSON document limit?** — No.

**19. Which layer do `snappy`, `zlib`, and `zstd` operate on?** — Wire compression when negotiated.

**20. Does compression replace TLS?** — No; compression does not encrypt data.

**21. Does WiredTiger disk compression automatically compress network traffic?** — No.

**22. Does JPEG compress significantly further on the wire?** — Barely, as it is already compressed.

**23. Does `$bsonSize` measure compressed wire bytes?** — No.

**24. Does `explain` report TCP packet counts?** — No.

**25. Why measure CPU and p95/p99 alongside bytes?** — Compression and large batches spend CPU/memory that can hurt latency.

**26. Does projection enforce security?** — No; authorization is still mandatory.

**27. Should each HTTP request create a new `MongoClient`?** — No; reuse connection pools.

**28. What is the typical optimization order?** — Cut unused data, cut round trips, test compression, and measure correctness and latency.

## 51. Quick Reference Cheat Sheet

| Purpose | Syntax / Mechanism |
|---|---|
| Inclusion projection | `find(filter, {field: 1, _id: 0})` |
| Exclude heavy fields | `find(filter, {largeField: 0})` |
| Nested field only | `{"customer.name": 1}` |
| First N array elements | `items: {$slice: 3}` |
| Single matching array element | `$elemMatch` projection |
| Multiple matching array elements | Aggregation `$filter` |
| Array length only | Aggregation `$size` |
| Shape pipeline output | `$project` / `$unset` |
| Reduce returned documents | `$match`, `limit`, pagination |
| Avoid N+1 | Batch `$in` / `$lookup` |
| Index-only reads | Covered query where eligible |
| Cursor chunking | `batchSize`, `getMore` |
| Total result cap | `limit` |
| Node streaming | `for await (const x of cursor)` |
| Java streaming | `MongoCursor` with try-with-resources |
| Batch writes | `insertMany` / `bulkWrite` |
| Ordered/unordered writes | `ordered: true/false` |
| Server wire compressors | `net.compression.compressors` |
| Driver wire compressors | `compressors=zstd,snappy,zlib` per support |
| Encryption | TLS |
| Storage compression | WiredTiger compression |
| Measure BSON | `$bsonSize` |
| Query plan | `explain("executionStats")` |
| Network counters | `serverStatus().network` |
| Protocol limits | `db.adminCommand({hello: 1})` |

## 52. Production Deployment Checklist

- [ ] List and detail APIs have explicit field contracts?
- [ ] Unused notes, arrays, or PII are excluded?
- [ ] Inclusion projections used and `_id` handled intentionally?
- [ ] Nested fields and array previews return exact expected semantics?
- [ ] Tenant filters derive from authenticated context?
- [ ] `$match`, sort, limit, and indexes are designed together?
- [ ] Checked `explain`, `docsExamined`, and `keysExamined`?
- [ ] No pulling full collections into app memory to filter/group?
- [ ] Keyset pagination considered for deep pages?
- [ ] Eliminated N+1 queries and unbounded `$lookup` fan-outs?
- [ ] Distinguished API `pageSize`, cursor `batchSize`, and `limit`?
- [ ] `batchSize` tuned for document size, RTT, and memory?
- [ ] Iterators/streams used for large result sets?
- [ ] Cursors closed on early exit?
- [ ] Bulk writes enforce operation count and byte budgets?
- [ ] Partial failures, retries, and idempotency handled?
- [ ] Durability / write concern never lowered to game benchmarks?
- [ ] Server and driver share supported compressors?
- [ ] Node/Java codec dependencies verified?
- [ ] TLS and hostname verification kept enabled?
- [ ] Wire compression distinguished from storage and HTTP compression?
- [ ] Not expecting high compression ratios on JPEG/MP4?
- [ ] Measured network bytes, request counts, CPU, memory, and p95/p99?
- [ ] Representative benchmarks run with warm-up and multiple repetitions?
- [ ] Verified record counts, fields, and business invariants?
- [ ] Monitoring and rollback plans ready before rolling out changes?

## 53. Conclusion

Optimizing MongoDB network transfer begins with one rule: **do not send data the application does not use**. Projections, `$match`, limits, and pagination cut both fields and document counts. Array operators and server-side aggregations return summaries or previews instead of raw bloat, and covered queries can eliminate server document fetches when paired with suitable indexes.

When round trips remain high, **cursor batching** and **bulk writes** slash command overhead. Yet `batchSize` is not `limit`, `toArray()` still fills RAM, and `bulkWrite` is not a batch-wide transaction. Size batches by measuring document bytes, RTT, concurrency, memory, and error semantics.

Finally, **wire compression** with `snappy`, `zlib`, or `zstd` shrinks bytes over MongoDB connections when negotiated by client and server on compressible payloads. Compression never replaces TLS, differs from WiredTiger storage compression, and cannot fix a bad query plan. Every valid optimization must be verified via **network bytes, CPU, p95/p99 latency, and result correctness**—never just a single "percent compressed" headline.
