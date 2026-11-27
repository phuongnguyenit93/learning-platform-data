# Analyzing Queries with Sort, Projection, Arrays, and Multiple Filter Branches in MongoDB

A MongoDB query can filter the right data and still be slow because the database must read too many documents, perform a separate in-memory sort, or combine multiple filter branches that existing indexes do not support. In particular, when a query combines **sort**, **projection**, **array fields**, and **$or/$and** operators, merely glancing at index names is rarely enough to tell whether the query is optimized.

The primary tool for analysis is **explain()**. Explain output reveals which execution plan MongoDB chose, which stages were used, how many index keys and documents were examined, whether FETCH or SORT is needed, and how many results the query returned.

This lesson walks through how to read and interpret execution plans, choose compound indexes for filters and sorts, evaluate covered projections, analyze multikey indexes on arrays, and handle **$or**, **$and**, and **$in** branches. Examples are built with **mongosh** and the MongoDB Java Sync Driver.

## 1. From Query to Execution Plan

An application query may consist of four parts:

~~~javascript
db.orders.find(
  {
    tenantId: "T-01",
    status: "PAID",
    tags: "priority"
  },
  {
    _id: 0,
    orderNo: 1,
    createdAt: 1,
    totalAmount: 1
  }
)
.sort({ createdAt: -1 })
.limit(20);
~~~

Each part serves a different role:

| Component | Purpose | Performance Question to Check |
| --- | --- | --- |
| **Filter** | Selects matching documents | Is there an index narrowing the documents to examine? |
| **Sort** | Orders results as requested | Does the index deliver data in order, or is a separate sort required? |
| **Projection** | Selects returned fields | Can data be served solely from the index, or must documents be fetched? |
| **Limit** | Caps returned results | Can execution stop early when the index supports filter/sort? |

To execute it, the query planner can choose among multiple **candidate plans**. For example:

~~~text
Query:
  tenantId = T-01
  status = PAID
  sort createdAt descending
  limit 20

Plan A:
  IXSCAN compound index
    -> FETCH if needed
    -> LIMIT
    -> return results

Plan B:
  IXSCAN a different index
    -> FETCH
    -> SORT
    -> LIMIT
    -> return results

Plan C:
  COLLSCAN
    -> FILTER
    -> SORT
    -> LIMIT
    -> return results
~~~

All three plans can return **the same logical result set**, yet their read and sort costs differ greatly. Analysis is not merely "whether an index is used" but **which index is used, how many keys/documents are examined, whether there is a blocking sort, and whether any condition is evaluated late**.

### 1.1. Explain Is an Execution Description, Not a Data-Modifying Statement

Use:

~~~javascript
db.orders.find({ tenantId: "T-01" })
  .sort({ createdAt: -1 })
  .explain("executionStats");
~~~

The command returns a document containing the query plan and execution statistics. It neither creates indexes nor alters business data.

**Limitation to remember:** explain observes a specific query and conditions at the time it runs. It does not replace benchmarking under production load, and it does not guarantee the planner will always pick the same plan for every data variation.

## 2. Sample Dataset for This Lesson

We use a multi-tenant orders collection containing scalar fields, subdocuments, and arrays. Each document has these fields:

~~~javascript
{
  _id: 1,
  tenantId: "T-01",
  orderNo: "ORD-001",
  status: "PAID",
  channel: "APP",
  createdAt: ISODate("2026-11-01T09:00:00Z"),
  totalAmount: 150000,
  shipping: {
    city: "HCM"
  },
  tags: ["priority", "gift"],
  items: [
    { sku: "BOOK-01", quantity: 2, unitPrice: 50000 },
    { sku: "PEN-02", quantity: 1, unitPrice: 50000 }
  ]
}
~~~

Use the lab database:

~~~javascript
use mongo_plan_lab

// Run drop operations only on a test database.
db.orders.drop();

db.orders.insertMany([
  {
    _id: 1,
    tenantId: "T-01",
    orderNo: "ORD-001",
    status: "PAID",
    channel: "APP",
    createdAt: ISODate("2026-11-01T09:00:00Z"),
    totalAmount: 150000,
    shipping: { city: "HCM" },
    tags: ["priority", "gift"],
    items: [
      { sku: "BOOK-01", quantity: 2, unitPrice: 50000 },
      { sku: "PEN-02", quantity: 1, unitPrice: 50000 }
    ]
  },
  {
    _id: 2,
    tenantId: "T-01",
    orderNo: "ORD-002",
    status: "PAID",
    channel: "WEB",
    createdAt: ISODate("2026-11-02T10:00:00Z"),
    totalAmount: 240000,
    shipping: { city: "HN" },
    tags: ["gift"],
    items: [
      { sku: "BOOK-02", quantity: 1, unitPrice: 240000 }
    ]
  },
  {
    _id: 3,
    tenantId: "T-01",
    orderNo: "ORD-003",
    status: "PENDING",
    channel: "APP",
    createdAt: ISODate("2026-11-03T08:00:00Z"),
    totalAmount: 80000,
    shipping: { city: "HCM" },
    tags: ["new"],
    items: [
      { sku: "PEN-02", quantity: 2, unitPrice: 40000 }
    ]
  },
  {
    _id: 4,
    tenantId: "T-01",
    orderNo: "ORD-004",
    status: "SHIPPED",
    channel: "APP",
    createdAt: ISODate("2026-11-04T11:00:00Z"),
    totalAmount: 450000,
    shipping: { city: "DN" },
    tags: ["priority"],
    items: [
      { sku: "BOOK-01", quantity: 1, unitPrice: 150000 },
      { sku: "BOOK-02", quantity: 1, unitPrice: 300000 }
    ]
  },
  {
    _id: 5,
    tenantId: "T-01",
    orderNo: "ORD-005",
    status: "PAID",
    channel: "APP",
    createdAt: ISODate("2026-11-05T12:00:00Z"),
    totalAmount: 120000,
    shipping: { city: "HCM" },
    tags: ["priority"],
    items: [
      { sku: "BOOK-01", quantity: 1, unitPrice: 120000 }
    ]
  },
  {
    _id: 6,
    tenantId: "T-01",
    orderNo: "ORD-006",
    status: "CANCELLED",
    channel: "WEB",
    createdAt: ISODate("2026-11-06T08:30:00Z"),
    totalAmount: 300000,
    shipping: { city: "HN" },
    tags: [],
    items: [
      { sku: "BOOK-03", quantity: 2, unitPrice: 150000 }
    ]
  },
  {
    _id: 7,
    tenantId: "T-02",
    orderNo: "ORD-007",
    status: "PAID",
    channel: "WEB",
    createdAt: ISODate("2026-11-01T14:00:00Z"),
    totalAmount: 900000,
    shipping: { city: "DN" },
    tags: ["gift"],
    items: [
      { sku: "BOOK-04", quantity: 3, unitPrice: 300000 }
    ]
  },
  {
    _id: 8,
    tenantId: "T-02",
    orderNo: "ORD-008",
    status: "PENDING",
    channel: "APP",
    createdAt: ISODate("2026-11-02T15:00:00Z"),
    totalAmount: 300000,
    shipping: { city: "HCM" },
    tags: ["new", "priority"],
    items: [
      { sku: "BOOK-01", quantity: 1, unitPrice: 300000 }
    ]
  },
  {
    _id: 9,
    tenantId: "T-02",
    orderNo: "ORD-009",
    status: "PAID",
    channel: "APP",
    createdAt: ISODate("2026-11-03T16:00:00Z"),
    totalAmount: 75000,
    shipping: { city: "HN" },
    tags: ["new"],
    items: [
      { sku: "PEN-02", quantity: 3, unitPrice: 25000 }
    ]
  },
  {
    _id: 10,
    tenantId: "T-02",
    orderNo: "ORD-010",
    status: "SHIPPED",
    channel: "WEB",
    createdAt: ISODate("2026-11-05T17:00:00Z"),
    totalAmount: 150000,
    shipping: { city: "HCM" },
    tags: [],
    items: [
      { sku: "BOOK-02", quantity: 1, unitPrice: 150000 }
    ]
  },
  {
    _id: 11,
    tenantId: "T-01",
    orderNo: "ORD-011",
    status: "PAID",
    channel: "WEB",
    createdAt: ISODate("2026-11-07T10:30:00Z"),
    totalAmount: 500000,
    shipping: { city: "DN" },
    tags: ["gift", "priority"],
    items: [
      { sku: "BOOK-04", quantity: 1, unitPrice: 500000 }
    ]
  },
  {
    _id: 12,
    tenantId: "T-01",
    orderNo: "ORD-012",
    status: "SHIPPED",
    channel: "WEB",
    createdAt: ISODate("2026-11-08T11:30:00Z"),
    totalAmount: 230000,
    shipping: { city: "HCM" },
    tags: ["priority"],
    items: [
      { sku: "BOOK-01", quantity: 2, unitPrice: 100000 },
      { sku: "PEN-02", quantity: 1, unitPrice: 30000 }
    ]
  }
]);
~~~

The dataset has only **12 documents**, enough to verify logical results:

- Tenant **T-01** has **8 orders**.
- Tenant **T-01**, status **PAID** has **4 orders**: 1, 2, 5, 11.
- Tenant **T-01**, status **PAID**, channel **APP** has **2 orders**: 1 and 5.
- Statuses and creation timestamps are used to demonstrate sorting.
- **tags** is a scalar array; **items** is an array of embedded documents.

**Important:** with 12 documents, MongoDB may choose **COLLSCAN** as the cheapest plan even after indexes are created. Sample plan structures and metric tables for large collections below are **illustrative**, not fixed outputs reproducible verbatim on a small dataset.

## 3. Explain Modes and Metrics to Read

MongoDB provides common explain verbosity levels:

~~~javascript
// View only the plan selected by the planner and related candidates.
db.orders.find({ status: "PAID" })
  .explain("queryPlanner");

// View the plan and execution statistics.
db.orders.find({ status: "PAID" })
  .explain("executionStats");

// Also view trial execution info for candidate plans.
db.orders.find({ status: "PAID" })
  .explain("allPlansExecution");
~~~

### 3.1. `queryPlanner`

This section typically describes:

- **winningPlan**: the chosen plan.
- **rejectedPlans**: unselected candidate plans, when present.
- **planCacheShapeHash / queryHash / planCacheKey**: query shape and plan identifiers depending on version.
- Stages or plan structures showing the data path.

Do not assume field names and plan tree layouts stay identical across MongoDB versions. Versions using the **Slot-Based Execution Engine (SBE)** may display **queryPlan**, **slotBasedPlan**, or different stages compared to the classic engine.

### 3.2. `executionStats`

Useful metrics:

| Metric | Meaning | What to Watch For |
| --- | --- | --- |
| **nReturned** | Number of documents/results actually returned | A small number does not mean a cheap query |
| **totalKeysExamined** | Total number of index keys inspected | Can be high when an index is unselective or multikey |
| **totalDocsExamined** | Total number of document inspections to evaluate the query | 0 may indicate a covered query |
| **executionTimeMillis** | Server-recorded duration for the explain run | Easily affected by cache, load, and runtime conditions |
| **executionStages** | Stage tree and per-stage statistics | Look for IXSCAN, FETCH, COLLSCAN, SORT, LIMIT |
| **works / advanced / needTime** | Execution counters in supporting engines/stages | Interpret by version; not every plan reports them |

Example of a query returning 20 orders yet reading 500,000 documents:

~~~text
nReturned          = 20
totalKeysExamined  = 0
totalDocsExamined  = 500000
~~~

This can signal a collection scan or a very inefficient predicate. Conversely:

~~~text
nReturned          = 20
totalKeysExamined  = 20
totalDocsExamined  = 20
~~~

can reflect a very narrow index scan. This is purely a comparative example, not a rule that "`keysExamined` must equal `nReturned`."

**`totalDocsExamined` can exceed the count of unique logical documents** in certain plan structures, and `totalKeysExamined` can exceed document counts due to multikey or scan ranges. Read them alongside stages and filters to interpret accurately.

### 3.3. `allPlansExecution`

This mode is useful when investigating how candidate plans competed. However, data for rejected candidates may represent only partial work during the plan trial phase, not necessarily the statistics of running those plans to completion.

Never see a rejected plan examining more keys and immediately conclude the planner is always right or always wrong. Check the workload, parameter distribution, and run proper experiments.

### 3.4. Explain and the Plan Cache

A regular query can use the plan cache or plan according to MongoDB's caching policy. **`explain` does not use existing plan cache entries as its winning choice, nor does it insert the winning plan into the plan cache the way a normal query does**.

Consequently, explain is very helpful for analysis, yet differences from actual application requests can still occur. When a production query is unexpectedly slow, cross-check with the profiler, telemetry, and plan cache behavior for your server version.

## 4. Recognizing Common Stages

Plan structures may vary, but certain stage names are key.

| Stage / Plan Form | Interpretation |
| --- | --- |
| **COLLSCAN** | Scans documents in the collection |
| **IXSCAN** | Traverses index keys over defined bounds or direction |
| **FETCH** | Retrieves source documents after finding candidates via an index |
| **SORT** | Performs a separate sort step, typically a blocking sort |
| **LIMIT** | Caps result count at a step |
| **SKIP** | Skips initial results |
| **PROJECTION_COVERED** | Projection can be satisfied from the index without fetching documents |
| **PROJECTION_DEFAULT / PROJECTION_SIMPLE** | Stage applying projection according to the plan |
| **OR** | Combines results from multiple plan branches |
| **SORT_MERGE** | Merges ordered data streams in certain cases |
| **AND_HASH / AND_SORTED** | Forms of index intersection |
| **COUNT_SCAN** | Some plans that count directly from an index |
| **SHARD_MERGE / SHARDING_FILTER** | Steps related to sharded execution |

MongoDB will not always display these exact names. Newer versions, aggregation pipelines, or SBE may present plans differently. **The goal is to recognize the actual work**, not write a parser rigidly tied to one stage name.

### 4.1. Two Sample Plans

A plan using an index to filter and then fetch documents:

~~~text
LIMIT
└── FETCH
    └── IXSCAN
        indexName: idx_tenant_status_created
~~~

A plan without a suitable index for sorting:

~~~text
LIMIT
└── SORT
    └── FETCH
        └── IXSCAN
            indexName: idx_tenant_status
~~~

In the second plan, the index still helps with filtering, yet intermediate results must be sorted. A query with IXSCAN **can still be very resource-intensive** if SORT processes hundreds of thousands of documents before taking 20 results.

### 4.2. How to Read a Plan Tree

Start at the output node and trace down through child nodes to check:

1. Is **IXSCAN or COLLSCAN** the data source?
2. If IXSCAN, what is **indexName**?
3. Are **indexBounds** narrow or wide?
4. Is there a **FETCH**, and why?
5. Is there a **SORT**, or did the index already supply the order?
6. Is a residual filter applied late at FETCH?
7. Are there any OR branches or merges?
8. Are **nReturned** and keys/docs examined reasonable relative to the output?

Avoid assuming **FETCH is an error**. If a query needs fields absent from the index, fetching documents is normal behavior. The problem arises when the number of fetched documents is huge relative to the results needed.

## 5. Sort: When an Index Supplies the Requested Order

Suppose a common requirement is fetching the newest PAID orders for tenant T-01:

~~~javascript
db.orders.find({
  tenantId: "T-01",
  status: "PAID"
})
.sort({ createdAt: -1 })
.limit(20);
~~~

Create a compound index:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_tenant_status_created" }
);
~~~

The index orders keys first by `tenantId`, then by `status`, and then by `createdAt` descending within each group.

When the filter specifies **tenantId = T-01** and **status = PAID**, MongoDB can traverse the matching index slice where keys are already ordered by **createdAt descending**. Depending on the plan, the system can stop early once 20 documents are found.

### 5.1. Logical Key Ordering Inside a Compound Index

~~~text
Index keys: (tenantId asc, status asc, createdAt desc)

T-01 | PAID    | 2026-11-07
T-01 | PAID    | 2026-11-05
T-01 | PAID    | 2026-11-02
T-01 | PAID    | 2026-11-01
T-01 | PENDING | 2026-11-03
T-01 | SHIPPED | 2026-11-08
...
~~~

With tenant and status fixed by equality filters, the corresponding slice is already sorted by `createdAt`. This visually demonstrates how **an equality prefix lets an index satisfy sorting on trailing fields**.

### 5.2. The ESR Guideline: Equality – Sort – Range

A common compound index design guideline:

1. **Equality:** fields compared for equality typically go first.
2. **Sort:** fields that provide the required ordering.
3. **Range:** fields using range operators like `$gte`/`$lt` are usually placed after sort fields when prioritizing avoiding a blocking sort.

Example:

~~~javascript
db.orders.find({
  tenantId: "T-01",
  status: "PAID",
  totalAmount: { $gte: 100000 }
})
.sort({ createdAt: -1 })
.limit(20);
~~~

A candidate index:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1,
    totalAmount: 1
  },
  { name: "idx_tenant_status_created_amount" }
);
~~~

This index can satisfy tenant/status equality and `createdAt` order, while `totalAmount` is checked during the scan. If the amount predicate is extremely selective, placing **totalAmount** earlier might perform better even if sorting must happen separately.

**ESR is a starting guideline, not an absolute law that always wins**. Some workloads favor **Equality – Range – Sort (ERS)** when the range is highly selective. Compare using explain and real latency.

### 5.3. Index with an Intermediate Field Not Bound by Equality

Suppose you only filter on `tenantId` and sort by `createdAt`:

~~~javascript
db.orders.find({
  tenantId: "T-01"
})
.sort({ createdAt: -1 })
.limit(20);
~~~

Existing index:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1 }
~~~

Inside the index, `createdAt` values are sorted **within each `status` group**. When `status` is not fixed, `createdAt` order is not a global order across all documents for that tenant. MongoDB may need a blocking sort or a different index.

A more suitable dedicated index:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, createdAt: -1 },
  { name: "idx_tenant_created" }
);
~~~

Thus, merely seeing **createdAt** somewhere in an index is not enough. **The field order in a compound index and which fields are equality-filtered** determine whether the index can serve the sort.

### 5.4. Sort Directions and Reverse Index Scans

Index:

~~~javascript
{ tenantId: 1, createdAt: -1 }
~~~

can serve:

~~~javascript
db.orders.find({ tenantId: "T-01" })
  .sort({ createdAt: -1 });
~~~

and in many cases can be scanned in reverse to serve:

~~~javascript
db.orders.find({ tenantId: "T-01" })
  .sort({ createdAt: 1 });
~~~

For **multi-field sorts**, the field directions must match the key pattern or **invert the entire corresponding sort suffix**; not every combination of independently flipped directions is supported by a single index.

Example:

~~~javascript
// Index:
{ tenantId: 1, status: 1, createdAt: -1 }

// With tenantId equality, sort status asc, createdAt desc:
// Compatible with index order.
db.orders.find({ tenantId: "T-01" })
  .sort({ status: 1, createdAt: -1 });
~~~

However, if you request `status` asc and `createdAt` asc, the index above cannot naturally return that order in a single scan; analyze full sort directions carefully.

## 6. Blocking Sorts and Their Cost

A **blocking sort** must receive and sort an intermediate result set before knowing what order to emit. This differs from reading index keys that are already in the desired order.

Example:

~~~javascript
db.orders.find({
  tenantId: "T-01"
})
.sort({ totalAmount: -1 })
.limit(10);
~~~

If the collection only has an index on `tenantId` and `createdAt`, the planner may read T-01 orders and then sort by `totalAmount`.

Diagram:

~~~text
IXSCAN on tenantId
       |
       v
FETCH documents and extract totalAmount
       |
       v
SORT by totalAmount descending
       |
       v
LIMIT 10
~~~

A **top-k sort** can optimize memory when combining sort and limit, yet it may still have to **inspect many input documents** to determine the top 10. Having a limit does not mean MongoDB reads only 10 documents.

### 6.1. When Can SORT Be Avoided?

Create a matching index:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, totalAmount: -1 },
  { name: "idx_tenant_amount" }
);
~~~

The query can read keys for tenant T-01 in descending amount order and stop once the limit is reached.

### 6.2. Sorting Requires Memory and Sometimes Spills to Disk

When sorting large volumes of data unsupported by an index, MongoDB enforces per-stage memory limits and provides mechanisms to spill temporary data to disk depending on version, settings, and options. If spilling is disallowed or limits are exceeded, the query can fail.

Aggregation example:

~~~javascript
db.orders.aggregate(
  [
    { $match: { tenantId: "T-01" } },
    { $sort: { totalAmount: -1 } },
    { $limit: 20 }
  ],
  { allowDiskUse: true }
);
~~~

**`allowDiskUse` does not make sorting free**. It enables processing cases that need temporary disk resources when supported, but can increase I/O and execution time. The long-term fix is usually improving the index or shrinking the input set before sorting.

### 6.3. Unstable Sort Order on Tied Values

If multiple orders share the exact same `createdAt`, MongoDB does not guarantee a deterministic tie order when sorting solely by `createdAt`.

For stable pagination:

~~~javascript
db.orders.find({ tenantId: "T-01" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
~~~

Corresponding index:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, createdAt: -1, _id: -1 },
  { name: "idx_tenant_created_id" }
);
~~~

The **`_id`** field acts as a tie-breaker when documents have identical timestamps, assuming `_id` is unique within the query scope. For sharded collections, verify identifier rules and shard key constraints for global uniqueness/ordering.

## 7. Projection: Returning Fewer Fields Does Not Mean Skipping FETCH

Projection limits which fields appear in results:

~~~javascript
db.orders.find(
  { tenantId: "T-01", status: "PAID" },
  { _id: 0, tenantId: 1, status: 1, createdAt: 1 }
)
.sort({ createdAt: -1 });
~~~

If the index:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1 }
~~~

contains every field needed for filtering, sorting, and projection, MongoDB can perform a **covered query**: using the index without reading source documents.

Illustrative plan:

~~~text
PROJECTION_COVERED
└── IXSCAN
    indexName: idx_tenant_status_created

totalDocsExamined = 0
~~~

Exact eligibility for a covered query also depends on index type, queried fields, collation, multikey status, and deployment constraints.

### 7.1. Why Must `_id` Often Be Excluded from Projection?

MongoDB includes **`_id`** by default in `find` results unless explicitly excluded by the projection.

Example:

~~~javascript
// Projection still returns _id by default.
db.orders.find(
  { tenantId: "T-01", status: "PAID" },
  { tenantId: 1, status: 1, createdAt: 1 }
);
~~~

If the index does not contain `_id`, a query returning `_id` may have to FETCH documents. To enable a covered query:

~~~javascript
db.orders.find(
  { tenantId: "T-01", status: "PAID" },
  {
    _id: 0,
    tenantId: 1,
    status: 1,
    createdAt: 1
  }
);
~~~

Or include `_id` in the index if returning `_id` is an important requirement and the benefit justifies the extra index cost.

### 7.2. Even One Unindexed Field Can Force FETCH

With the `tenantId/status/createdAt` index:

~~~javascript
db.orders.find(
  { tenantId: "T-01", status: "PAID" },
  { _id: 0, tenantId: 1, status: 1, createdAt: 1, totalAmount: 1 }
);
~~~

The **`totalAmount`** field is absent from the index, so MongoDB generally must fetch source documents to return it.

Illustrative diagram:

~~~text
PROJECTION_DEFAULT / PROJECTION_SIMPLE
└── FETCH
    └── IXSCAN
        indexName: idx_tenant_status_created
~~~

Projection shrinks the payload sent to the client, yet **does not guarantee fewer documents read**. Only a covered query avoids FETCH altogether.

### 7.3. Add Fields to an Index Only When Practically Worthwhile

You could add `totalAmount`:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1,
    totalAmount: 1
  },
  { name: "idx_tenant_status_created_amount" }
);
~~~

However, wider indexes carry storage, cache, and write overhead. Never stuff every projected field into a giant index just to achieve a covered query. Weigh the cost of FETCHing documents against index maintenance overhead.

### 7.4. Projection Does Not Change Filter Evaluation

Example:

~~~javascript
db.orders.find(
  { status: "PAID", totalAmount: { $gte: 100000 } },
  { _id: 0, orderNo: 1 }
);
~~~

Even though the projection only returns **`orderNo`**, the server must still evaluate **`status`** and **`totalAmount`**. If no index helps evaluate the filter, `totalDocsExamined` can remain very high.

**Projection is not a mechanism that turns a collection-scanning query into an indexed query.**

## 8. Arrays and Multikey Indexes: Why Explain Differs from Regular Indexes

MongoDB can create indexes on fields containing arrays. When indexing an array, MongoDB creates index keys for matching elements following **multikey index** rules.

Example:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, tags: 1 },
  { name: "idx_tenant_tags" }
);
~~~

Document:

~~~javascript
{
  _id: 1,
  tenantId: "T-01",
  tags: ["priority", "gift"]
}
~~~

contributes index keys corresponding to the array element values, per multikey index semantics.

### 8.1. One Document Can Produce Multiple Index Keys

Query:

~~~javascript
db.orders.find({
  tenantId: "T-01",
  tags: "priority"
});
~~~

With a multikey index, **`keysExamined`** can exceed the number of returned documents. One document holding multiple array elements can contribute multiple keys, and the planner must deduplicate results when multiple keys point to the same document.

Distinguish clearly:

- **Index entry/key:** represents one indexed value.
- **Document:** the result unit of `find`.
- **`nReturned`:** document count after applying filters and processing steps.

Do not conclude a multikey index is ineffective merely because `totalKeysExamined` exceeds `nReturned`. Check ratios, bounds, and which fields are actually filtered by the index.

### 8.2. Explain Shows Whether an Index Is Multikey

Inside IXSCAN, depending on version, output may include fields like:

~~~javascript
{
  stage: "IXSCAN",
  indexName: "idx_tenant_tags",
  isMultiKey: true,
  multiKeyPaths: {
    tenantId: [],
    tags: ["tags"]
  }
}
~~~

This is a structural illustration, not fixed verbatim output across all versions.

**`isMultiKey: true`** indicates the index contains multikey data. **`multiKeyPaths`** clarifies which field/path in a compound index introduces multikey entries.

A compound multikey index has constraints on which arrays can be indexed. You cannot arbitrarily index multiple independent array fields within the same document; account for these constraints when designing compound indexes.

## 9. Arrays of Documents and `$elemMatch`

Suppose an order has:

~~~javascript
{
  _id: 100,
  items: [
    { sku: "BOOK-01", quantity: 1 },
    { sku: "PEN-02", quantity: 5 }
  ]
}
~~~

Requirement: find orders having **the same item** with sku `BOOK-01` and quantity at least 2.

### 9.1. Two Dot-Notation Conditions Can Match Two Different Elements

~~~javascript
db.orders.find({
  "items.sku": "BOOK-01",
  "items.quantity": { $gte: 2 }
});
~~~

The example document **matches**:

- One element has sku `BOOK-01`, quantity = 1.
- Another element has quantity = 5.

The two conditions are not implicitly bound to the same array element.

### 9.2. Using `$elemMatch` to Bind to the Same Element

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "BOOK-01",
      quantity: { $gte: 2 }
    }
  }
});
~~~

The example document does not match because item `BOOK-01` has quantity 1.

In our 12-document sample dataset, order **`_id = 1`** has `BOOK-01` with quantity 2 so it matches; order `_id = 4` has `BOOK-01` with quantity 1 so it does not match.

### 9.3. Compound Multikey Indexes and Index Bounds

Consider:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    "items.sku": 1,
    "items.quantity": 1
  },
  { name: "idx_tenant_item_sku_qty" }
);
~~~

Both **`items.sku`** and **`items.quantity`** belong to the embedded document array **`items`**. When filtering with **`$elemMatch` on the shared `items` path**, MongoDB can combine the predicates to tighten index bounds (bounds compounding) under multikey index rules.

~~~javascript
db.orders.find({
  tenantId: "T-01",
  items: {
    $elemMatch: {
      sku: "BOOK-01",
      quantity: { $gte: 2 }
    }
  }
}).explain("executionStats");
~~~

In explain, inspect:

- Was **`idx_tenant_item_sku_qty`** selected?
- How tightly were bounds on **`items.sku`** and **`items.quantity`** narrowed?
- Were many keys examined due to array elements?
- Is there a FETCH to verify the document-level condition?
- Did `totalKeysExamined` and `totalDocsExamined` drop compared to other plans?

**`$elemMatch` both enforces correct business semantics and can enable tighter compound bounds on fields in the same array**, though it does not guarantee a specific index will be chosen.

### 9.4. Do Not Blindly Apply Scalar Field Rules to Arrays

For scalar fields, two conditions:

~~~javascript
{ status: "PAID", totalAmount: { $gte: 100000 } }
~~~

belong to the same document and can use a compound index relatively straightforwardly.

For two fields traversing an array of embedded documents, check whether predicates must match the same element or may span different elements. This affects both **result correctness** and **how index bounds are combined**.

## 10. Sorting on Array Fields: A Subtle Pitfall

Suppose you need to sort orders by `tags` or by an item's price inside `items`.

~~~javascript
db.orders.find({ tenantId: "T-01" })
  .sort({ tags: 1 });
~~~

When sorting directly on an array in MongoDB, the sort key is determined from **the array elements**: ascending sort uses the smallest element per comparison rules, while descending sort uses the largest element. It is not an arbitrary ordering by the first element in the array.

### 10.1. Filtering on an Element Does Not Necessarily Change the Sort Key

Example:

~~~javascript
db.orders.find({
  tags: "priority"
})
.sort({
  tags: 1
});
~~~

The query filters documents containing **`priority`**. Yet sorting on **`tags`** still follows whole-array sort rules rather than restricting the sort key to the **`priority`** element matched by the filter.

Similarly, if you filter **`items.sku = BOOK-01`** and then sort by **`items.unitPrice`**, do not assume MongoDB sorts by the unit price of **that specific `BOOK-01` item**. If business logic requires sorting by the matched item's price, reshape the model or use aggregation to extract the exact value before sorting.

### 10.2. Multikey Indexes Have Limits When Supporting Sorts

MongoDB enforces stricter rules when using a **multikey index** for sorting. In certain scenarios, even when the sort field appears in the index, the planner still needs a **blocking SORT** because index bounds and multikey paths affect ordering.

Illustrative example:

~~~javascript
db.orders.createIndex(
  { tags: 1, createdAt: -1 },
  { name: "idx_tags_created" }
);

db.orders.find({
  tags: "priority"
})
.sort({
  tags: 1
})
.explain("executionStats");
~~~

Verify whether a SORT stage appears. Never assume that merely having **`tags`** in an index allows every sort on `tags` to be resolved by the index.

In principle, avoiding a blocking sort with a multikey index depends on the sort field's bounds and path relationships with bound multikey fields. A relevant constraint is that bounds on the sort field must not restrict the index in a way that breaks sort order, and shared path prefixes with multikey fields also matter. **Always check explain instead of asserting a multikey index always supports sorting**.

### 10.3. Correctness When Sorting by a Specific Item

If the requirement is "orders containing `BOOK-01`, sorted by `BOOK-01` price within each order," aggregation can unwind `items` to sort on the exact element:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "T-01" } },
  { $unwind: "$items" },
  { $match: { "items.sku": "BOOK-01" } },
  { $sort: { "items.unitPrice": -1, _id: 1 } },
  {
    $project: {
      _id: 1,
      orderNo: 1,
      sku: "$items.sku",
      itemPrice: "$items.unitPrice"
    }
  }
]);
~~~

The pipeline above outputs **one result per `BOOK-01` item** after unwinding. If an order has multiple items with the same sku, multiple rows can appear for that order; if you want one row per order, add grouping rules or schema constraints.

Aggregation is **not automatically faster** than `find`. `$unwind` can multiply intermediate rows, and `$sort` can become a blocking stage. The primary goal here is semantic correctness.

## 11. Projection with Multikey Indexes

Covered queries on arrays have special restrictions.

Suppose the index is:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, tags: 1 },
  { name: "idx_tenant_tags" }
);
~~~

A query that filters on `tags` without returning the array field:

~~~javascript
db.orders.find(
  {
    tenantId: "T-01",
    tags: "priority"
  },
  {
    _id: 0,
    tenantId: 1
  }
);
~~~

Depending on conditions, MongoDB may be able to use the index without fetching documents because the projection does not request the `tags` array.

Conversely:

~~~javascript
db.orders.find(
  {
    tenantId: "T-01",
    tags: "priority"
  },
  {
    _id: 0,
    tenantId: 1,
    tags: 1
  }
);
~~~

To return the whole `tags` array, a multikey index does not store the original array structure in a way that reconstructs it completely, so **it cannot default to a covered query**. The query may have to FETCH the documents.

Requirements for covered queries on multikey indexes generally include **not projecting the array field**, meeting standard covered query rules, and not using `$elemMatch` in contexts that disallow coverage.

A query with a minimal projection on an array does not automatically become covered; always check **`totalDocsExamined`** and the actual stages.

## 12. Multiple Filter Branches: Distinguishing `$and`, `$or`, and `$in`

MongoDB lets you combine predicates at multiple logical levels.

### 12.1. `$and`: All Conditions Must Hold

~~~javascript
db.orders.find({
  $and: [
    { tenantId: "T-01" },
    { status: "PAID" },
    { totalAmount: { $gte: 100000 } }
  ]
});
~~~

When fields do not require repeated complex operators, this is equivalent to:

~~~javascript
db.orders.find({
  tenantId: "T-01",
  status: "PAID",
  totalAmount: { $gte: 100000 }
});
~~~

An appropriate **compound index** is usually a strong candidate for serving multiple conditions. MongoDB can also consider **index intersection** in some cases, though there is no guarantee the planner will choose intersection when multiple single-field indexes exist.

### 12.2. `$or`: At Least One Branch Must Hold

~~~javascript
db.orders.find({
  tenantId: "T-01",
  $or: [
    { status: "PAID" },
    { channel: "APP" }
  ]
});
~~~

The predicate means:

~~~text
tenantId = T-01
AND
(
  status = PAID
  OR
  channel = APP
)
~~~

Notice `tenantId` sits outside `$or` as a shared constraint. Accidentally placing `tenantId` inside only one branch could widen results across tenants, causing correctness and security bugs.

### 12.3. `$in`: One Field Matches a Set of Values

~~~javascript
db.orders.find({
  tenantId: "T-01",
  status: {
    $in: ["PAID", "SHIPPED"]
  }
});
~~~

Logically, this is close to:

~~~javascript
db.orders.find({
  tenantId: "T-01",
  $or: [
    { status: "PAID" },
    { status: "SHIPPED" }
  ]
});
~~~

When comparing multiple values on **a single field**, `$in` is usually clearer. However, plan selection and sort preservation depend on value count, bounds, compound indexes, and MongoDB version. Never assume a huge `$in` list always behaves like a single equality predicate.

## 13. `$or` and Indexes: Each Branch Can Have Its Own Access Path

Suppose we look for T-01 orders with status `PAID` **or** channel `APP`:

~~~javascript
db.orders.find({
  tenantId: "T-01",
  $or: [
    { status: "PAID" },
    { channel: "APP" }
  ]
});
~~~

We can create indexes:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, status: 1 },
  { name: "idx_tenant_status" }
);

db.orders.createIndex(
  { tenantId: 1, channel: 1 },
  { name: "idx_tenant_channel" }
);
~~~

The query planner may use a plan combining branches via different indexes:

~~~text
OR / UNION
├── IXSCAN idx_tenant_status
└── IXSCAN idx_tenant_channel
       |
       v
Deduplicate documents if appropriate
       |
       v
FETCH / PROJECTION
~~~

This is a conceptual diagram, not guaranteed stage names across every MongoDB version.

### 13.1. Why Can One Unindexed Branch Make the Entire OR Expensive?

With OR, MongoDB must retrieve matches from **every branch**. If even one branch must scan most of the collection, a combined plan using indexes on the other branches may offer little benefit.

Example:

~~~javascript
db.orders.find({
  $or: [
    { status: "PAID" },
    { "shipping.city": "HCM" }
  ]
});
~~~

If an index exists on `status` but no suitable index exists for `shipping.city`, the planner may pick **COLLSCAN** for the entire OR rather than combining index plans. That is why you must check **every branch** of an OR, not just the first branch.

Do not treat this as a hard rule tied to one stage name; the planner evaluates valid plans based on context and version. When all branches are suitably indexable, MongoDB can use multiple indexes.

### 13.2. OR Can Match the Same Document via Multiple Branches

Document `_id = 1` has status `PAID` and channel `APP`, so it satisfies **both** branches. A regular `find` query still returns that document **once**, not twice.

When analyzing explain for an OR, index keys or candidates examined can exceed `nReturned` because multiple branches lead to the same document. Do not confuse examined keys with unique results.

### 13.3. Shared Conditions Can Narrow Index Bounds

~~~javascript
{
  tenantId: "T-01",
  $or: [
    { status: "PAID" },
    { channel: "APP" }
  ]
}
~~~

With compound indexes sharing the `tenantId` prefix, each branch can bound its index scan to that tenant rather than scanning across all tenants.

In multi-tenant systems, keeping `tenantId` in filters is a matter of **data correctness and isolation** before it is a query optimization. Starting indexes with `tenantId` also helps shrink keys examined when workloads primarily query per tenant.

## 14. `$or` Combined with Sort: Why `SORT` Easily Appears

Suppose we add a sort:

~~~javascript
db.orders.find({
  tenantId: "T-01",
  $or: [
    { status: "PAID" },
    { channel: "APP" }
  ]
})
.sort({ createdAt: -1 })
.limit(20);
~~~

Even if both branches have indexes:

~~~javascript
{ tenantId: 1, status: 1 }
{ tenantId: 1, channel: 1 }
~~~

the combined results from two index scans are not naturally ordered by **createdAt descending**.

The plan may be:

~~~text
LIMIT
└── SORT createdAt descending
    └── OR
        ├── IXSCAN idx_tenant_status
        └── IXSCAN idx_tenant_channel
~~~

In other cases, if each branch can deliver the same order and the planner has an eligible strategy, **`SORT_MERGE`** or another plan may appear to avoid a standard full sort.

Candidate indexes:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_tenant_status_created" }
);

db.orders.createIndex(
  { tenantId: 1, channel: 1, createdAt: -1 },
  { name: "idx_tenant_channel_created" }
);
~~~

These indexes help each branch when `status`/`channel` are equality predicates, yet **do not guarantee** the combined OR + sort will pick a non-blocking merge plan. Always inspect the actual explain output.

### 14.1. Changing Indexes to Prioritize Global Sort Order

Another option:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, createdAt: -1 },
  { name: "idx_tenant_created" }
);
~~~

The planner can scan T-01 orders by `createdAt` descending and check status/channel afterward. If `limit` is small and match rate is high, this can be efficient.

However, if the OR condition is highly selective, the planner may have to scan many documents before finding 20 matches, making this plan worse than selective index branches plus a sort.

This is a trade-off:

- **Per-branch indexes:** filter more tightly, may require sort/merge.
- **Global sort-order index:** may avoid sorting, yet scans more documents to find matches.

No single default wins across every data distribution.

### 14.2. Reading Metrics Against the Target Goal

If the API needs 20 results:

| Plan | `keysExamined` | `docsExamined` | Has SORT? | Observation |
| --- | ---: | ---: | --- | --- |
| Scan index by shared sort order | 700 | 700 | No | Reads many to find enough matches |
| Two selective index branches | 80 | 65 | Yes | Fewer documents, yet requires sorting |
| Collection scan | 1,000,000 | 1,000,000 | Yes | Potentially very expensive |

**These are hypothetical numbers for illustration.** Conclusions must rest on real `executionStats` and latency, not on a single column in isolation.

## 15. `$and` and Index Intersection

Suppose single-field indexes exist:

~~~javascript
db.orders.createIndex(
  { status: 1 },
  { name: "idx_status" }
);

db.orders.createIndex(
  { channel: 1 },
  { name: "idx_channel" }
);
~~~

And the query is:

~~~javascript
db.orders.find({
  status: "PAID",
  channel: "APP"
});
~~~

Possible plans include:

1. Use `idx_status` then FETCH to check `channel`.
2. Use `idx_channel` then FETCH to check `status`.
3. Use **index intersection** if the planner deems it suitable.
4. Use a compound index on `status` + `channel` if one exists.

### 15.1. Intersection Is Not Guaranteed

Stages like **AND_HASH** or **AND_SORTED** indicate index intersection plans. Yet the planner may pick a single index if that costs less. Having multiple indexes does not guarantee MongoDB will combine them.

If a query shape is frequent and critical, a compound index:

~~~javascript
db.orders.createIndex(
  { status: 1, channel: 1 },
  { name: "idx_status_channel" }
);
~~~

can be more efficient and predictable, depending on workload. However, each added index increases storage and write overhead; do not create indexes for every field combination just because you can.

### 15.2. Intersection Does Not Automatically Solve Sorting

Suppose:

~~~javascript
db.orders.find({
  status: "PAID",
  channel: "APP"
})
.sort({ createdAt: -1 });
~~~

Even when intersection helps filter `status`/`channel`, results from intersection are not guaranteed to arrive in `createdAt` order. A compound index accounting for both filter and sort can be better:

~~~javascript
db.orders.createIndex(
  { status: 1, channel: 1, createdAt: -1 },
  { name: "idx_status_channel_created" }
);
~~~

This is why you must evaluate **the entire query shape**, not just the filter.

## 16. Multi-Level Nested Conditions

A real-world query may combine multiple branches:

~~~javascript
const filter = {
  tenantId: "T-01",
  $and: [
    {
      $or: [
        { status: "PAID" },
        { status: "SHIPPED" }
      ]
    },
    {
      $or: [
        { channel: "APP" },
        { "shipping.city": "HCM" }
      ]
    }
  ]
};

db.orders.find(filter)
  .sort({ createdAt: -1 })
  .limit(20);
~~~

The query means:

~~~text
tenantId = T-01
AND
(status = PAID OR status = SHIPPED)
AND
(channel = APP OR shipping.city = HCM)
~~~

Here multiple combinations let a document match. The planner must evaluate logical branches and pick an execution strategy; you cannot assume one single compound index automatically handles every scenario.

### 16.1. Simplifying Branches on the Same Field

Two branches:

~~~javascript
{
  $or: [
    { status: "PAID" },
    { status: "SHIPPED" }
  ]
}
~~~

can usually be expressed as:

~~~javascript
{
  status: {
    $in: ["PAID", "SHIPPED"]
  }
}
~~~

This form is cleaner and helps applications standardize query shapes. Still, plan impact must be checked when combined with sorting.

### 16.2. Never Rewrite in Ways That Alter Semantics

Do not turn:

~~~text
(A OR B) AND (C OR D)
~~~

into:

~~~text
A OR B OR C OR D
~~~

because the two expressions are not equivalent. Index tuning must preserve exact filter logic, especially in multi-tenant systems or queries enforcing authorization rules.

### 16.3. When Should You Split into Multiple Queries?

If an OR is very complex and each branch needs a different index, you can sometimes experiment with running separate queries and merging results in the application. However, you must handle:

- Deduplicating documents appearing in multiple branches.
- Preserving correct overall sort order.
- Global pagination and limits.
- Read consistency across queries.
- Network cost and extra round trips.
- Ensuring each document is returned exactly once.

Splitting an OR into multiple queries is **not automatically faster or simpler**. Do so only after benchmarking and clearly defining semantics.

## 17. Explain for Aggregation Pipelines

When requirements combine filtering, projection, sorting, and array processing, applications may use aggregation:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "T-01", status: "PAID" } },
  {
    $project: {
      _id: 0,
      orderNo: 1,
      createdAt: 1,
      totalAmount: 1
    }
  },
  { $sort: { createdAt: -1 } },
  { $limit: 20 }
]);
~~~

Explain it:

~~~javascript
db.orders.explain("executionStats").aggregate([
  { $match: { tenantId: "T-01", status: "PAID" } },
  {
    $project: {
      _id: 0,
      orderNo: 1,
      createdAt: 1,
      totalAmount: 1
    }
  },
  { $sort: { createdAt: -1 } },
  { $limit: 20 }
]);
~~~

MongoDB's aggregation optimizer can reorder or coalesce stages when safe, such as pushing `$match` earlier or coalescing `$sort` + `$limit`.

**Never assume the written stage order equals the execution stage order.** Inspect the optimized pipeline, query plan, and `executionStats` when returned.

### 17.1. Initial `$match` and Indexes

A `$match` at the start of a pipeline generally lets MongoDB consider collection indexes:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "T-01" } },
  { $sort: { createdAt: -1 } },
  { $limit: 20 }
]);
~~~

If `{ tenantId: 1, createdAt: -1 }` fits, the optimizer can leverage it. However, a stage transforming documents before `$match`/`$sort` can change index eligibility.

### 17.2. `$unwind` Multiplies Row Counts

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "T-01" } },
  { $unwind: "$items" },
  { $match: { "items.sku": "BOOK-01" } },
  { $sort: { "items.unitPrice": -1 } }
]);
~~~

After `$unwind`, an order with three items becomes three pipeline documents. Output metrics on stages after unwind reflect **pipeline documents**, not just source documents.

If the goal is merely filtering orders that contain a matching item, `$elemMatch` on the source document may do less work:

~~~javascript
db.orders.find({
  tenantId: "T-01",
  items: {
    $elemMatch: {
      sku: "BOOK-01"
    }
  }
});
~~~

However, the two approaches do not return the same result structure if the unwound aggregation returns individual items. Choose according to business requirements.

### 17.3. Early `$project` Does Not Always Speed Things Up

If an early projection drops fields needed by sorting or filtering, the pipeline is no longer equivalent. If projection adds computed fields, indexes cannot serve sorts on that expression the way they do for stored fields.

Optimization should rely on explain and post-optimization semantics rather than a blind rule like "put `$project` as early as possible."

## 18. Filtering and Sorting in a Sharded Cluster

On a sharded collection, a query may route to one shard or multiple shards depending on the shard key.

Hypothetical example where **`tenantId`** is part of the shard key by cluster design:

~~~javascript
db.orders.find({
  tenantId: "T-01",
  status: "PAID"
})
.sort({ createdAt: -1 })
.limit(20);
~~~

If predicates allow targeted routing, fewer shards participate. If a query omits an appropriate shard key:

~~~javascript
db.orders.find({
  status: "PAID"
})
.sort({ createdAt: -1 })
.limit(20);
~~~

the request may have to execute across multiple shards and merge results.

Explain output may show per-shard plans and result merge/sort steps. Optimal indexes on each shard do not eliminate network or merge costs across a distributed query.

### 18.1. Distinguishing Local Sort from Global Sort

One shard can emit results ordered by `createdAt` descending via an index. Yet across multiple shards, `mongos` or merge steps must still coordinate rows to deliver **global sort order**.

With `limit`, shards can apply eligible optimizations to cut data sent back, but exact effectiveness must be verified in the running cluster's explain.

### 18.2. Multikey and OR in a Sharded Cluster

Queries on arrays or multiple OR branches execute on the relevant shards. If predicates cannot route narrowly, the workload fans out to multiple shards. Analyze:

- Number of shards queried.
- Index used on each shard.
- Keys/documents examined per shard.
- Load at the merge stage.
- Impact of sort/projection on network data transfer.

Never inspect explain from one shard and assume the entire distributed query has the same cost.

## 19. Building a Checklist to Read Explain for Complex Queries

When facing a query with filters, sort, projection, arrays, and OR, walk through in order.

### Step 1 – Describe the Query Shape

Record:

~~~text
Collection:
Equality filters:
Range filters:
$or branches:
Array conditions:
Sort pattern:
Projection fields:
Limit/skip:
Collation:
Read preference:
Relevant shard key:
~~~

Without capturing the full query shape, you risk building an index for a narrow variant while missing the real workload.

### Step 2 – Read the Winning Plan

~~~javascript
db.orders.find({
  tenantId: "T-01",
  status: "PAID"
})
.sort({ createdAt: -1 })
.limit(20)
.explain("executionStats");
~~~

Identify IXSCAN/COLLSCAN, `indexName`, and bounds. Do not stop at the index name and ignore residual filters.

### Step 3 – Look for SORT

If SORT appears:

- Is the sort field unindexed?
- Is there an intermediate field not equality-bound in the compound index?
- Does a range predicate precede the sort and break index sort order?
- Is there a multikey restriction?
- Does an OR branch emit multiple result streams?
- Is there a collation mismatch with the index?

### Step 4 – Look for FETCH and Projection

If FETCH appears:

- Does projection request fields missing from the index?
- Is `_id` returned by default?
- Which filter conditions must be evaluated on the document?
- Do array fields or `$elemMatch` preclude coverage?

FETCH itself is not bad. Check **how many documents** must be FETCHed.

### Step 5 – Analyze Arrays and Branches

For arrays:

- Does the index report `isMultiKey`?
- Must the query match the same element?
- Is `$elemMatch` used properly?
- Does sorting on the array match business semantics?

For OR:

- Does every branch have an appropriate index?
- How are duplicate documents across branches handled?
- Does global sorting require a separate stage?
- Can an OR on the same field become `$in` while preserving semantics?

### Step 6 – Evaluate Cost

Compare:

~~~text
nReturned
totalKeysExamined
totalDocsExamined
SORT/FETCH stage counts
Participating shards
executionTimeMillis
Real app P95/P99
CPU / I/O / cache
~~~

A query returning 10 documents while inspecting 500,000 index keys is likely worth optimizing. A query returning 100,000 documents with `totalDocsExamined` around 100,000 is not necessarily wrong if business logic truly requires transferring that volume.

### Step 7 – Test Candidate Indexes

Create a test index in an appropriate environment:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_trial_tenant_status_created" }
);
~~~

Re-run the same query shape and representative parameters. You can use **`hint`** to inspect what plan a specific index yields:

~~~javascript
db.orders.find({
  tenantId: "T-01",
  status: "PAID"
})
.sort({ createdAt: -1 })
.hint("idx_trial_tenant_status_created")
.explain("executionStats");
~~~

**Hint is a testing tool, not a default solution for production queries.** As data evolves, a fixed hint can lock in a stale plan; if the index is dropped or hidden, hints can cause errors.

### Step 8 – Benchmark on a Representative Workload

Small lab collections clarify semantics, not production behavior with millions of documents. Test on realistic data volumes and distributions, covering common and rare query shapes, skewed data states, per-tenant conditions, and real concurrency.

## 20. Common Anti-Patterns

| Misconception | Reality to Understand |
| --- | --- |
| Having IXSCAN means the query is optimized | It can still scan many keys or require FETCH/SORT |
| No SORT stage means results are guaranteed sorted right | Only true when the query requests a sort and the plan delivers that order |
| Having the sort field in a compound index is enough | Must check equality prefix, range predicates, and sort directions |
| Having `limit(20)` means MongoDB reads only 20 documents | It may read and sort huge sets to find the top 20 |
| Projecting few fields always saves document reads | Only covered queries avoid FETCH completely |
| Leaving `_id` in projection doesn't matter | `_id` is returned by default and can block coverage |
| A multikey index has one key per document | An array can generate many keys |
| Two predicates `items.sku` and `items.quantity` always match the same element | Must use `$elemMatch` when business logic requires the same element |
| Sorting on an array uses the filter-matched element | Array sorting follows whole-array rules, not just the filtered element |
| Every OR branch having an index guarantees no SORT | Merging branch results can still require sorting |
| One OR branch having an index optimizes the whole OR | Another branch may force scanning massive data |
| Two single-field indexes always intersect | The planner is not guaranteed to choose index intersection |
| `$in` with many values behaves like single equality for sort | Multiple ranges/merges may be required depending on size and plan |
| Fast explain plan guarantees a fast API | Production involves cache, network, concurrency, and different data |
| Adding as many fields to a compound index as possible is best | Wide indexes increase write, storage, and cache overhead |
| `$unwind` leaves result counts unchanged | One document can expand into many pipeline rows |
| Explain from one shard represents the whole cluster | Fan-out and merging across shards can dominate |

## 21. Java Sync Driver: Building Queries and Calling Explain

In Java, you can build queries using **Filters**, **Sorts**, and **Projections**. Example:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;

public class QueryPlanExample {

    public static void main(String[] args) {
        try (MongoClient client =
                     MongoClients.create("mongodb://localhost:27017")) {

            MongoDatabase database =
                    client.getDatabase("mongo_plan_lab");

            MongoCollection<Document> orders =
                    database.getCollection("orders");

            Bson filter = Filters.and(
                    Filters.eq("tenantId", "T-01"),
                    Filters.eq("status", "PAID")
            );

            Bson sort = Sorts.descending("createdAt");

            Bson projection = Projections.fields(
                    Projections.include(
                            "tenantId", "status", "createdAt"
                    ),
                    Projections.excludeId()
            );

            orders.find(filter)
                    .sort(sort)
                    .projection(projection)
                    .limit(20)
                    .forEach(System.out::println);
        }
    }
}
~~~

To get explain output with minimal dependence on driver-version-specific helper APIs, send the **`explain` command** directly via `MongoDatabase.runCommand()`:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public class ExplainFindCommand {

    public static void main(String[] args) {
        try (MongoClient client =
                     MongoClients.create("mongodb://localhost:27017")) {

            MongoDatabase database =
                    client.getDatabase("mongo_plan_lab");

            Document findCommand = new Document("find", "orders")
                    .append("filter", new Document(
                            "tenantId", "T-01"
                    ).append("status", "PAID"))
                    .append("sort", new Document(
                            "createdAt", -1
                    ))
                    .append("projection", new Document(
                            "_id", 0
                    ).append("tenantId", 1)
                     .append("status", 1)
                     .append("createdAt", 1))
                    .append("limit", 20);

            Document explainCommand =
                    new Document("explain", findCommand)
                            .append("verbosity", "executionStats");

            Document result =
                    database.runCommand(explainCommand);

            System.out.println(result.toJson());
        }
    }
}
~~~

These examples require a running MongoDB server and the MongoDB Java Sync Driver dependency. Some driver versions also offer an `explain` API on compatible iterables. Response structure depends on MongoDB version and execution strategy.

### 21.1. Adjusting Indexes from Java

You can create a compound index:

~~~java
import com.mongodb.client.model.Indexes;

// orders is an already-initialized MongoCollection<Document>.
orders.createIndex(
        Indexes.compoundIndex(
                Indexes.ascending("tenantId", "status"),
                Indexes.descending("createdAt")
        )
);
~~~

In production, building indexes on large collections requires change planning and resource monitoring. Only create indexes after identifying query shapes and evaluating costs; never let request-handling code repeatedly call `createIndex`.

### 21.2. Reading Explain Without Hardcoding Stages

For automated monitoring, collect metrics with relatively stable contracts such as **`nReturned`**, **`totalKeysExamined`**, and **`totalDocsExamined`**, alongside plan summaries/query shape logs. Never rely on a naive text search for **`"IXSCAN"`** in JSON, as output structure varies across engines and versions.

## 22. Practice Exercises: Sort and Compound Indexes

Use the **`mongo_plan_lab.orders`** collection created earlier. In a small lab, explain may pick COLLSCAN even when indexes exist. The main goal is learning what questions to ask and how to read a plan.

### Exercise A – Comparing Indexed vs. Unindexed Sort

Create the index:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_tenant_status_created" }
);
~~~

Run:

~~~javascript
db.orders.find({
  tenantId: "T-01",
  status: "PAID"
})
.sort({ createdAt: -1 })
.limit(3)
.explain("executionStats");
~~~

Answer:

1. If the index is chosen, which fields make up the equality prefix?
2. Can the index provide `createdAt` descending order?
3. Does FETCH occur because the query returns full documents?
4. Why does `limit(3)` not prove only 3 keys were read?
5. If `status` is removed from the filter, is this index still guaranteed to avoid a blocking sort?

### Exercise B – Sorting on a Field Outside the Index

~~~javascript
db.orders.find({
  tenantId: "T-01"
})
.sort({ totalAmount: -1 })
.limit(3)
.explain("executionStats");
~~~

Then try:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, totalAmount: -1 },
  { name: "idx_tenant_amount" }
);
~~~

Re-run explain and inspect the sort stage. If a tiny dataset shows little difference, explain why large datasets and representative distributions are required to evaluate indexes.

## 23. Practice Exercises: Projection and Covered Queries

### Exercise C – Comparing Projections With and Without `_id`

~~~javascript
const filter = {
  tenantId: "T-01",
  status: "PAID"
};

db.orders.find(
  filter,
  {
    tenantId: 1,
    status: 1,
    createdAt: 1
  }
).explain("executionStats");
~~~

Compare with:

~~~javascript
db.orders.find(
  filter,
  {
    _id: 0,
    tenantId: 1,
    status: 1,
    createdAt: 1
  }
).explain("executionStats");
~~~

Answer:

1. Why does the projection return `_id` by default?
2. When can the plan achieve `totalDocsExamined = 0`?
3. Why can adding `totalAmount` to the projection trigger FETCH?
4. Is it worth creating a new index just to cover one extra field?

### Exercise D – Projecting an Array Field

~~~javascript
db.orders.createIndex(
  { tenantId: 1, tags: 1 },
  { name: "idx_tenant_tags" }
);

db.orders.find(
  { tenantId: "T-01", tags: "priority" },
  { _id: 0, tenantId: 1 }
).explain("executionStats");
~~~

Compare against adding **`tags: 1`** to the projection and explain why requesting the full array can prevent a covered query.

## 24. Practice Exercises: Arrays and `$elemMatch`

### Exercise E – Comparing Two Predicates on an Embedded Array

~~~javascript
const looseQuery = {
  "items.sku": "BOOK-01",
  "items.quantity": { $gte: 2 }
};

const sameElementQuery = {
  items: {
    $elemMatch: {
      sku: "BOOK-01",
      quantity: { $gte: 2 }
    }
  }
};

printjson(db.orders.find(looseQuery, { _id: 1 }).toArray());

printjson(
  db.orders.find(sameElementQuery, { _id: 1 }).toArray()
);
~~~

Answer:

1. Why can the two queries return different result sets?
2. Which document has a matching sku while only another item has sufficient quantity?
3. If a compound multikey index is created on `items.sku`/`items.quantity`, how can `$elemMatch` help the planner combine bounds?
4. Why can `totalKeysExamined` exceed `nReturned` when arrays are involved?

### Exercise F – Sorting by a Specific Item

Write an aggregation using **`$unwind`**, **`$match`**, and **`$sort`** to retrieve `BOOK-01` items by `unitPrice` descending. Explain why:

~~~javascript
db.orders.find({
  "items.sku": "BOOK-01"
}).sort({
  "items.unitPrice": -1
});
~~~

does not automatically mean "sort by the `unitPrice` of the matched `BOOK-01` item."

## 25. Practice Exercises: `$or`, `$and`, and Sort

### Exercise G – Measuring a Two-Branch OR

~~~javascript
db.orders.createIndex(
  { tenantId: 1, status: 1 },
  { name: "idx_tenant_status" }
);

db.orders.createIndex(
  { tenantId: 1, channel: 1 },
  { name: "idx_tenant_channel" }
);

db.orders.find({
  tenantId: "T-01",
  $or: [
    { status: "PAID" },
    { channel: "APP" }
  ]
})
.explain("executionStats");
~~~

Determine:

1. Which index can be used for each branch?
2. Will a document matching both branches appear twice?
3. If `sort({ createdAt: -1 })` is added, what additional stage might the plan need?
4. If the `channel` index is dropped, why might the plan switch to a collection scan?
5. Why might `{ tenantId: 1, createdAt: -1 }` be an alternative for queries with a small limit?

### Exercise H – Optimizing a Multi-Branch Query

~~~javascript
db.orders.find({
  tenantId: "T-01",
  status: { $in: ["PAID", "SHIPPED"] },
  $or: [
    { channel: "APP" },
    { "shipping.city": "HCM" }
  ],
  totalAmount: { $gte: 100000 }
})
.sort({ createdAt: -1, _id: -1 })
.limit(20)
.explain("executionStats");
~~~

Analyze step by step:

- Which fields are equality, range, and OR branches?
- How many distinct candidate indexes could exist?
- Should you prioritize sorting or selective filtering?
- Is a compound index containing `createdAt` and `_id` needed?
- If one OR branch matches very rarely, is a dedicated index for that branch worth creating?
- How do you measure `totalKeysExamined`/`totalDocsExamined`, blocking sorts, runtime, and index maintenance overhead?

Answers must be grounded in **real workload and data**, as no single compound index is guaranteed optimal for every variation.

## 26. Summary of the Analysis Method

When a MongoDB query is complex, evaluate it through four questions:

1. **Filter:** Does MongoDB find documents with narrow index bounds, or is it scanning too many keys/documents?
2. **Sort:** Does an index already provide the result order, or is a blocking sort/merge required?
3. **Projection:** Can results come straight from the index, or must source documents be FETCHed?
4. **Arrays and filter branches:** How do multikey, `$elemMatch`, and `$or/$and/$in` alter semantics, examined keys, and the execution plan?

Verify with **`explain("executionStats")`**, compare candidate indexes on the same query shape, record **`nReturned`**, **`totalKeysExamined`**, **`totalDocsExamined`**, SORT/FETCH/IXSCAN/COLLSCAN, and correlate with actual latency. For large workloads, never tune solely on tiny sample datasets; weigh storage and index maintenance costs as well.

**A good plan is one that returns accurate business results and fits the real workload**, not necessarily the plan with the most IXSCAN stages or zero FETCHes at all costs.

## References

- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual — db.collection.explain()](https://www.mongodb.com/docs/manual/reference/method/db.collection.explain/)
- [MongoDB Manual — Query Plans](https://www.mongodb.com/docs/manual/core/query-plans/)
- [MongoDB Manual — Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/)
- [MongoDB Manual — ESR Guideline](https://www.mongodb.com/docs/manual/tutorial/equality-sort-range-guideline/)
- [MongoDB Manual — Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/)
- [MongoDB Manual — $elemMatch](https://www.mongodb.com/docs/manual/reference/operator/query/elemMatch/)
- [MongoDB Manual — $or](https://www.mongodb.com/docs/manual/reference/operator/query/or/)
- [MongoDB Manual — Sort Results](https://www.mongodb.com/docs/manual/reference/method/cursor.sort/)
- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
