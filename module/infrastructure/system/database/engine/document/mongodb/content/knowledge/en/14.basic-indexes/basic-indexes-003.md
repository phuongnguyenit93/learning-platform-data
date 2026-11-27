# Single-Field and Compound Indexes in MongoDB

When a collection only holds a few dozen documents, MongoDB can scan all of the data while still responding quickly. However, once a collection grows to millions of orders, reading every document to find those belonging to a specific customer or tenant drives up CPU, I/O, and latency. **Indexes** help MongoDB locate matching documents without having to scan the entire collection.

Two foundational index types to master:

- **Single-field index:** organizes keys by a single field, such as `{customerId: 1}`.
- **Compound index:** organizes keys by **an ordered sequence of multiple fields**, such as `{tenantId: 1, status: 1, createdAt: -1}`.

The hard part is not just the `createIndex()` syntax. You also need to choose the right fields, key order, and sort directions, and know when to keep or drop an index. Three single-field indexes are not automatically equivalent to a three-field compound index; changing the field order of a compound index can also dramatically change query efficiency.

This lesson belongs to the **Basic Indexes** chapter in *Database Engine Document MongoDB*. Examples run via **mongosh** against the lab database `index_basics_lab`. Stage names and `explain()` shapes may vary across MongoDB versions and execution engines. Index decisions for production must be verified against your actual version and workload.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain how indexes reduce the amount of data read and describe their maintenance cost.
2. Create, list, measure, and drop single-field indexes using `createIndex()`, `getIndexes()`, `stats()`, and `dropIndex()`.
3. Create compound indexes and apply the **prefix rule** to predict which queries use an index effectively.
4. Design key order using **Equality–Sort–Range (ESR)** and understand when to measure placing range before sort.
5. Analyze `IXSCAN`, `COLLSCAN`, `FETCH`, `SORT`, `totalKeysExamined`, and `totalDocsExamined` in `explain("executionStats")`.
6. Distinguish filters, sorts, projections, covered queries, multikey indexes, and array edge cases.
7. Use single-field and compound unique indexes, and understand the effects of null/missing values, partial indexes, and collation.
8. Choose an index set based on read/write load, storage footprint, RAM/cache, and SLOs.

## 2. How Do Indexes Help Find Documents?

Imagine a collection with 5 million orders. An API frequently runs:

~~~javascript
db.orders.find({
  tenantId: "tenant-001",
  status: "PAID"
}).sort({
  createdAt: -1
}).limit(20)
~~~

Without a suitable index, the engine may have to inspect huge numbers of documents to identify matching orders and sort them. With an appropriate index, MongoDB can read the index range containing that tenant/status key group and leverage the creation-date order directly from the index.

~~~mermaid
flowchart LR
    API["Query with filter + sort"] --> Planner["Query planner"]
    Planner --> Choice{"Suitable access path?"}
    Choice -->|"Index"| IDX["IXSCAN: read index keys"]
    IDX --> FETCH["FETCH: retrieve documents if needed"]
    FETCH --> Result["Return results"]
    Choice -->|"Not suitable"| SCAN["COLLSCAN: scan collection"]
    SCAN --> Result
~~~

In most cases, standard indexes use a key-ordered structure, conceptually described as a B-tree. An index entry stores the ordered key and the reference needed to retrieve the document. Storage footprint and physical encoding are the responsibility of the storage engine; when learning query design, **logical key order** is what matters most.

### Indexes Are Not Free

| Benefit | Cost |
|---|---|
| Limits the number of documents examined | Indexes consume disk space and part of the cache working set |
| Can serve `sort` directly | Inserts, updates, and deletes must maintain indexes |
| Can avoid reading documents in covered queries | Index builds and rebuilds consume resources and carry operational risk |
| Can enforce uniqueness | Unique constraints can cause write operations to fail |

**An index is an access-path selection tool**, not a guarantee that every query will use an index or that using an index is always faster than a collection scan.

## 3. Practice Dataset

Run this only on the lab database. Never run commands that wipe production data to restart an exercise.

~~~javascript
use index_basics_lab

db.orders.insertMany([
  {
    _id: "ord-001", tenantId: "t-01", customerId: "c-101",
    status: "PAID", region: "HCM", amount: NumberDecimal("120000"),
    createdAt: ISODate("2026-01-05T08:00:00Z"),
    items: [{ sku: "A", qty: 2 }, { sku: "B", qty: 1 }]
  },
  {
    _id: "ord-002", tenantId: "t-01", customerId: "c-101",
    status: "CREATED", region: "HCM", amount: NumberDecimal("90000"),
    createdAt: ISODate("2026-01-06T09:00:00Z"),
    items: [{ sku: "A", qty: 1 }]
  },
  {
    _id: "ord-003", tenantId: "t-01", customerId: "c-102",
    status: "PAID", region: "HN", amount: NumberDecimal("350000"),
    createdAt: ISODate("2026-01-07T10:00:00Z"),
    items: [{ sku: "C", qty: 3 }]
  },
  {
    _id: "ord-004", tenantId: "t-01", customerId: "c-103",
    status: "CANCELLED", region: "DN", amount: NumberDecimal("75000"),
    createdAt: ISODate("2026-01-08T11:00:00Z"),
    items: [{ sku: "B", qty: 1 }]
  },
  {
    _id: "ord-005", tenantId: "t-01", customerId: "c-101",
    status: "PAID", region: "HCM", amount: NumberDecimal("500000"),
    createdAt: ISODate("2026-01-09T12:00:00Z"),
    items: [{ sku: "A", qty: 4 }]
  },
  {
    _id: "ord-006", tenantId: "t-02", customerId: "c-201",
    status: "PAID", region: "HCM", amount: NumberDecimal("210000"),
    createdAt: ISODate("2026-01-05T13:00:00Z"),
    items: [{ sku: "A", qty: 2 }]
  },
  {
    _id: "ord-007", tenantId: "t-02", customerId: "c-202",
    status: "CREATED", region: "HN", amount: NumberDecimal("115000"),
    createdAt: ISODate("2026-01-06T14:00:00Z"),
    items: [{ sku: "D", qty: 1 }]
  },
  {
    _id: "ord-008", tenantId: "t-02", customerId: "c-201",
    status: "PAID", region: "HN", amount: NumberDecimal("280000"),
    createdAt: ISODate("2026-01-10T15:00:00Z"),
    items: [{ sku: "A", qty: 1 }, { sku: "C", qty: 2 }]
  },
  {
    _id: "ord-009", tenantId: "t-02", customerId: "c-203",
    status: "CANCELLED", region: "DN", amount: NumberDecimal("60000"),
    createdAt: ISODate("2026-01-11T16:00:00Z"),
    items: [{ sku: "B", qty: 1 }]
  },
  {
    _id: "ord-010", tenantId: "t-03", customerId: "c-301",
    status: "PAID", region: "HCM", amount: NumberDecimal("800000"),
    createdAt: ISODate("2026-01-12T17:00:00Z"),
    items: [{ sku: "C", qty: 5 }]
  },
  {
    _id: "ord-011", tenantId: "t-03", customerId: "c-302",
    status: "CREATED", region: "HN", amount: NumberDecimal("170000"),
    createdAt: ISODate("2026-01-13T18:00:00Z"),
    items: [{ sku: "D", qty: 2 }]
  },
  {
    _id: "ord-012", tenantId: "t-03", customerId: "c-301",
    status: "PAID", region: "HN", amount: NumberDecimal("450000"),
    createdAt: ISODate("2026-01-14T19:00:00Z"),
    items: [{ sku: "A", qty: 3 }]
  }
])
~~~

Verification read commands:

~~~javascript
db.orders.countDocuments({})

db.orders.find(
  {},
  { _id: 1, tenantId: 1, customerId: 1, status: 1, createdAt: 1 }
).sort({ _id: 1 })
~~~

The lab collection has 12 documents. Re-running `insertMany()` with the same `_id` values will trigger duplicate key errors. Use a fresh lab database if you want to repeat the entire exercise. **12 documents are enough to demonstrate queries and semantics, but not enough to reliably benchmark index performance.**

## 4. Default Index on `_id`

MongoDB creates a unique `_id_` index on standard collections:

~~~javascript
db.orders.getIndexes()
~~~

You will see the key `{ _id: 1 }` and the name `_id_`. Therefore, the query:

~~~javascript
db.orders.findOne({ _id: "ord-005" })
~~~

already has an efficient access path without creating extra business indexes. However, `_id_` does not help a query filtering only on `status` or `customerId` locate the desired range of documents.

### Do Not Confuse Document ID with Business Search Keys

Many systems use an `ObjectId` for `_id` while letting users look up records by `externalOrderNo`. In that case, an API calling `findOne({externalOrderNo:"PO-123"})` may need a dedicated index. Choosing the ID is a data-modeling decision, whereas choosing indexes depends on the queries you must serve.

## 5. Single-Field Indexes: Creating and Querying

### 5.1. Ascending Index

~~~javascript
db.orders.createIndex(
  { customerId: 1 },
  { name: "idx_customer_id" }
)
~~~

`1` indicates ascending order and `-1` indicates descending order. Naming indexes makes logs, `getIndexes()` output, and `explain()` plans easier to read.

Query:

~~~javascript
db.orders.find(
  { customerId: "c-101" },
  { _id: 1, customerId: 1, status: 1 }
)
~~~

Matching documents: `ord-001`, `ord-002`, and `ord-005`. Without an explicit `sort`, **result order is not guaranteed**, even if the engine uses an ordered index.

### 5.2. Descending Index

~~~javascript
db.orders.createIndex(
  { createdAt: -1 },
  { name: "idx_created_desc" }
)
~~~

Query fetching the 5 most recent orders:

~~~javascript
db.orders.find(
  {},
  { _id: 1, createdAt: 1 }
).sort({ createdAt: -1 }).limit(5)
~~~

For a **single-field index**, MongoDB can usually scan the index in reverse to serve either ascending or descending sorts. You do not necessarily need both `{createdAt:1}` and `{createdAt:-1}` just to support both directions on one field. With **compound indexes**, the direction of each field affects multi-field sorting much more noticeably.

### 5.3. Index on a Nested Field

~~~javascript
db.orders.createIndex(
  { "items.sku": 1 },
  { name: "idx_item_sku" }
)

db.orders.find({
  "items.sku": "A"
})
~~~

Because `items` is an array of objects, an index on `items.sku` is a **multikey index**, where a single document can contribute multiple keys. This supports array queries, but causes index size and write costs to grow with array size.

### 5.4. When Is a Single-Field Index Valuable?

| Common query | Candidate single-field index | Considerations |
|---|---|---|
| Fetch a customer's orders | `{customerId:1}` | Effective when the filter is sufficiently selective |
| Fetch the latest orders system-wide | `{createdAt:-1}` | Supports sort/limit |
| Find documents containing an SKU | `{"items.sku":1}` | Multikey; item count affects footprint |
| Look up a transaction by external ID | `{externalId:1}` | May need to be unique |
| Filter all orders with status PAID | `{status:1}` | If PAID dominates the dataset, benefit may be low |

Single-field indexes fit queries **centered primarily on one field**. When filters and sorts consistently use a fixed group of fields together, consider a compound index.

## 6. Compound Indexes: Key Order Changes Access Patterns

Create index:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1
  },
  { name: "idx_tenant_status_created" }
)
~~~

Index keys are organized by:

~~~text
tenantId ascending
  within the same tenantId: status ascending
    within the same tenantId + status: createdAt descending
~~~

Logical illustration of key order (not actual physical byte format):

~~~text
(t-01, CANCELLED, 2026-01-08)
(t-01, CREATED,   2026-01-06)
(t-01, PAID,      2026-01-09)
(t-01, PAID,      2026-01-07)
(t-01, PAID,      2026-01-05)
(t-02, CANCELLED, 2026-01-11)
(t-02, CREATED,   2026-01-06)
(t-02, PAID,      2026-01-10)
(t-02, PAID,      2026-01-05)
...
~~~

Query:

~~~javascript
db.orders.find({
  tenantId: "t-01",
  status: "PAID"
}).sort({
  createdAt: -1
}).limit(20)
~~~

can narrow the first two fields via equality and then read the keys within that group ordered by most recent date. On the sample data, the result order is:

~~~text
ord-005
ord-003
ord-001
~~~

Changing the index to `{createdAt:-1,tenantId:1,status:1}` puts the date first; that structure might suit a global recent-orders feed, but is less suitable when every query targets a single tenant and status.

**A compound index is not an unordered set of fields.**

## 7. The Prefix Rule of Compound Indexes

Consider the index:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1 }
~~~

Its left-to-right prefixes are:

~~~text
{ tenantId: 1 }
{ tenantId: 1, status: 1 }
{ tenantId: 1, status: 1, createdAt: -1 }
~~~

A query with predicates on leading fields usually has a good chance of narrowing the key range effectively:

| Query | Compound index usability |
|---|---|
| `{tenantId:"t-01"}` | Matches the `tenantId` prefix |
| `{tenantId:"t-01",status:"PAID"}` | Matches the two-field prefix |
| `{tenantId:"t-01",status:"PAID",createdAt:{$gte:t}}` | Can use fields across the full key |
| `{status:"PAID"}` | Missing leading `tenantId`; lacks a matching prefix to filter status efficiently |
| `{createdAt:{$gte:t}}` | Missing the first two fields; not equivalent to a dedicated index on `createdAt` |
| `{tenantId:"t-01",createdAt:{$gte:t}}` | Matches the `tenantId` prefix; exploiting `createdAt` across the `status` gap is limited |

This is an efficiency design rule, **not an absolute claim that the planner will never use an index when a prefix is missing**. In some cases MongoDB can still scan the index (or pick it to avoid reading documents), yet you should not expect the same efficiency as an index whose leading keys match.

### 7.1. When Can a Prefix Index Be Redundant?

If both exist:

~~~javascript
{ tenantId: 1 }
{ tenantId: 1, status: 1, createdAt: -1 }
~~~

the single-field `tenantId` index **may** be redundant because the compound index already has it as a prefix. Still, do not drop it immediately:

- The single-field index is smaller and may serve very frequent queries with lower I/O and cache usage.
- Indexes with different options such as unique, partial, or collation are not always equivalent.
- The compound index may be kept for sorting, while the single-field index remains useful for another aggregation.
- A few infrequent but critical queries might rely on the single-field index.

Check `explain()`, write load, footprint, and business cycles before concluding an index is redundant.

### 7.2. Equality on Both Fields Does Not Dictate a Single Order

Compare:

~~~javascript
{ tenantId: 1, status: 1 }
{ status: 1, tenantId: 1 }
~~~

A query with equality on **both fields** can be supported by either order. However, a query filtering only on `tenantId` usually fits the first order better, while one filtering only on `status` fits the second better. If sorts or ranges are also involved, order matters even more.

## 8. Equality – Sort – Range (ESR)

A starting guideline for compound index design is:

1. **Equality:** exact-match filter fields, such as `tenantId = "t-01"` and `status = "PAID"`.
2. **Sort:** fields to sort by, such as `createdAt: -1`.
3. **Range:** range filter fields, such as `amount >= 100000`.

The **ESR** rule is a heuristic, not a rigid law. If the range condition is highly selective, placing range before sort may be preferable even if it requires sorting a small result set separately. Measure both options to decide.

### 8.1. Equality Followed by Sort

Query:

~~~javascript
db.orders.find({
  tenantId: "t-01",
  status: "PAID"
}).sort({ createdAt: -1 })
~~~

Index:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1 }
~~~

Both equality fields are pinned, so remaining keys in that slice are ordered by `createdAt`; this is a typically effective pattern for latest-orders lists.

### 8.2. Equality → Sort → Range

Query:

~~~javascript
db.orders.find({
  tenantId: "t-01",
  amount: { $gte: NumberDecimal("100000") }
}).sort({ createdAt: -1 }).limit(20)
~~~

Index following ESR:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, createdAt: -1, amount: 1 },
  { name: "idx_tenant_created_amount" }
)
~~~

The index focuses on the tenant slice and newest-date order. Because `amount` comes after `createdAt`, the engine may have to inspect many keys to collect 20 high-amount orders, especially if most orders have low amounts.

### 8.3. Equality → Range → Sort

Alternative:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, amount: 1, createdAt: -1 },
  { name: "idx_tenant_amount_created" }
)
~~~

This index has a better chance of bounding the `amount` range early. However, because keys are grouped by `amount` before `createdAt`, it **does not by default** provide tenant-wide `createdAt` order across a range on `amount`; the query may require a separate sort stage.

| Option | Potential advantage | Potential drawback |
|---|---|---|
| `{tenantId:1,createdAt:-1,amount:1}` | Serves date sort within tenant | May scan many keys before finding enough matching `amount` values |
| `{tenantId:1,amount:1,createdAt:-1}` | Narrows the `amount` range earlier | May require a `SORT` stage on `createdAt` |

### 8.4. Controlled Comparison Using `hint`

~~~javascript
const q = {
  tenantId: "t-01",
  amount: { $gte: NumberDecimal("100000") }
}

db.orders.find(q)
  .sort({ createdAt: -1 })
  .limit(20)
  .hint("idx_tenant_created_amount")
  .explain("executionStats")

db.orders.find(q)
  .sort({ createdAt: -1 })
  .limit(20)
  .hint("idx_tenant_amount_created")
  .explain("executionStats")
~~~

Use `hint()` **in experiments** to compare existing indexes. Avoid hardcoding `hint` into production queries based on a single test: when data distribution, indexes, or queries evolve, a forced choice can become suboptimal.

## 9. Sort Direction in Compound Indexes

Consider the index:

~~~javascript
{ tenantId: 1, createdAt: -1, amount: 1 }
~~~

When the filter has equality on `tenantId`, the index can support sorting the remaining two fields in this pattern:

~~~javascript
sort({ createdAt: -1, amount: 1 })
~~~

or scanning the entire pattern in reverse:

~~~javascript
sort({ createdAt: 1, amount: -1 })
~~~

However:

~~~javascript
sort({ createdAt: -1, amount: -1 })
~~~

matches neither the index pattern nor the exact inverse of both fields, so it is not served directly by that index. The query planner may need an extra sort stage.

### 9.1. When a Prefix Is Pinned by Equality

Index:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1 }
~~~

Query:

~~~javascript
db.orders.find({
  tenantId: "t-01",
  status: "PAID"
}).sort({ createdAt: 1 })
~~~

can scan the tenant/status key range in reverse to retrieve dates in ascending order.

### 9.2. When a Middle Field Is Omitted

Query:

~~~javascript
db.orders.find({
  tenantId: "t-01"
}).sort({ createdAt: -1 })
~~~

on `{tenantId:1,status:1,createdAt:-1}` has keys grouped by **status** before `createdAt`. Because `status` is not pinned, the order across the whole tenant is not globally sorted by date. If this API is critical, consider:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, createdAt: -1 },
  { name: "idx_tenant_created" }
)
~~~

**A compound index cannot serve every sort pattern simply because it contains the sort field somewhere.**

## 10. Selectivity and Cardinality

`_id` usually has very high cardinality; `status` usually has few distinct values. Yet what determines an index's benefit is the **selectivity of the predicate on real data**.

Hypothetical example:

~~~text
Collection: 1,000,000 orders

status = PAID          -> 850,000 orders   (weak filter)
tenantId = t-01        ->  80,000 orders   (moderate filter)
customerId = c-101     ->      25 orders   (strong filter)
~~~

If a query returns nearly the entire collection, using an index can still trigger huge numbers of FETCHes. For a predicate returning very few documents, an index is typically much more attractive. However, **there is no rule that "high-cardinality fields must always come first in a compound index"** for every workload:

- Order of equality fields also affects prefix usability.
- Sorts and ranges impose key-order constraints.
- Some status values are much rarer than others.
- Data can be heavily skewed across tenants.

### 10.1. Reading Efficiency from `explain`

The metrics:

~~~text
nReturned
totalKeysExamined
totalDocsExamined
executionTimeMillis
~~~

show result counts and query work. If a query returns 20 documents while examining 200,000 index keys, the index may still be a poor fit. If it returns 100,000 documents, network transfer and document reads remain costly even with an efficient key scan.

Never treat a single ratio as a universal benchmark: aggregations, multikey queries, pagination, and zero-result queries must be analyzed in context.

## 11. Reading `explain("executionStats")`

~~~javascript
db.orders.find({
  tenantId: "t-01",
  status: "PAID"
}).sort({ createdAt: -1 }).explain("executionStats")
~~~

| Stage / metric | Meaning |
|---|---|
| `queryPlanner.winningPlan` | The selected execution plan |
| `IXSCAN` | Reads index keys |
| `COLLSCAN` | Scans collection documents |
| `FETCH` | Retrieves documents from storage/cache to check filters or return fields |
| `SORT` | Performs a separate sort stage in the plan |
| `indexName` | Name of the index used in the stage |
| `indexBounds` | Index key range scanned |
| `executionStats.nReturned` | Number of documents returned |
| `totalKeysExamined` | Total index keys inspected |
| `totalDocsExamined` | Total documents inspected |

The JSON structure can differ between the classic execution engine and Slot-Based Execution. Do not rely on a single hardcoded JSON path across versions.

### 11.1. Three Common Scenarios

**COLLSCAN:** may happen due to a missing index or because the planner determines scanning the collection is cheaper. On 12 documents, COLLSCAN is completely normal.

**IXSCAN + FETCH:** the index narrows down candidates, while the engine still reads documents to retrieve unindexed fields or verify additional predicates. This is normal behavior.

**IXSCAN + SORT:** the index is used for filtering but does not provide the full requested order; sorting can consume significant CPU/RAM on large datasets.

### 11.2. A Measurement Methodology

1. Identify the **query shape**: filter, sort, projection, limit.
2. Capture the plan and `executionStats` before changing indexes.
3. Create the candidate index in a test environment.
4. Re-run the exact query against representative data.
5. Compare `nReturned`, keys examined, docs examined, `SORT` stages, and latency.
6. Also measure write throughput/latency and index footprint.
7. Test when data exceeds cache size or when selectivity shifts.

A 0–1 ms difference on 12 documents cannot prove an index wins. You need a representative dataset size and run count.

## 12. Covered Queries: When the Index Alone Can Answer

A **covered query** can be satisfied entirely from the index without accessing the underlying documents, provided the filter predicates and projected fields are all contained in the index and other coverage rules are met.

With the index:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1 }
~~~

try:

~~~javascript
db.orders.find(
  {
    tenantId: "t-01",
    status: "PAID"
  },
  {
    _id: 0,
    tenantId: 1,
    status: 1,
    createdAt: 1
  }
).sort({ createdAt: -1 }).explain("executionStats")
~~~

This is a **covered query candidate** because filter, sort, and projection only reference fields in the index. `_id: 0` is important: when `_id` is requested and the index does not include `_id`, MongoDB may need to fetch the original documents. A signature of coverage in a qualifying plan is the absence of a document FETCH stage and `totalDocsExamined = 0`.

### Projections Do Not Automatically Cover a Query

~~~javascript
db.orders.find(
  { tenantId: "t-01" },
  { _id: 0, customerId: 1 }
)
~~~

A projection shrinks the response payload, yet if the index used for filtering does not contain `customerId`, the engine may still have to read the documents.

### Should You Add Extra Fields to an Index Just to Cover?

For example, an index:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1, customerId: 1, amount: 1 }
~~~

covers more fields for certain queries, while also growing larger, consuming more cache, and increasing write amplification. Only widen an index when the read speedup for critical queries justifies the cost.

## 13. Multikey: Indexes on Arrays

The index:

~~~javascript
db.orders.createIndex(
  { "items.sku": 1 },
  { name: "idx_item_sku" }
)
~~~

operates on objects inside the `items` array. A single document with many items can produce many index keys; element count impacts storage and write cost.

### 13.1. Compound Multikey on the Same Object Array

~~~javascript
db.orders.createIndex(
  { "items.sku": 1, "items.qty": 1 },
  { name: "idx_item_sku_qty" }
)
~~~

If business logic searches for an item with SKU `A` and `qty >= 2`, use:

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 2 }
    }
  }
})
~~~

`$elemMatch` requires both predicates to match **the same array element**. The query:

~~~javascript
db.orders.find({
  "items.sku": "A",
  "items.qty": { $gte: 2 }
})
~~~

can match SKU from one item and `qty` from a different item. An index will not fix broken query semantics. Under eligible conditions, `$elemMatch` also allows the planner to intersect index bounds for fields from the same array.

### 13.2. Independent Arrays Differ from Subfields of One Array

Given a document:

~~~javascript
{
  tags: ["new", "vip"],
  couponCodes: ["SAVE10", "WELCOME"]
}
~~~

the compound index:

~~~javascript
{ tags: 1, couponCodes: 1 }
~~~

can violate the **parallel arrays** restriction of compound multikey indexes. Never assume an index combining two independent array fields is valid just because `items.sku + items.qty` within the same array of objects works.

### 13.3. Coverage Limits with Arrays

Multikey indexes have specific coverage restrictions; in particular, queries returning array fields usually cannot be covered in the same simple way scalar fields can. Always inspect `explain()` rather than assuming a field's presence in an index eliminates FETCH.

## 14. Single-Field and Compound Unique Indexes

An index can both accelerate queries and **enforce uniqueness**.

### 14.1. Unique on One Field

~~~javascript
db.transactions.createIndex(
  { transactionId: 1 },
  { unique: true, name: "uq_transaction_id" }
)
~~~

MongoDB rejects any document with the same `transactionId` key as another document, typically returning duplicate key error `E11000`.

Checking with `findOne()` before inserting **does not replace a unique index**: two clients can both read "not found" concurrently and both proceed to insert.

### 14.2. Unique Compound Index per Tenant

An `orderNo` may repeat across different tenants, while remaining unique within a single tenant:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, orderNo: 1 },
  {
    unique: true,
    name: "uq_tenant_order_no"
  }
)
~~~

Uniqueness applies to the **combination** `tenantId + orderNo`. For example, `(t-01, INV-100)` and `(t-02, INV-100)` are two distinct keys.

### 14.3. Nulls and Missing Fields

A unique index **does not automatically require the field to exist**. With a standard single-field unique index, null/missing values follow uniqueness rules such that multiple documents lacking the key can collide. With a unique compound index, the constraint applies to the **key tuple**, including null/missing components where present.

To ensure `orderNo` is always a string, use schema validation or dedicated write checks. To enforce uniqueness only on documents that actually have a string `orderNo`, use an appropriately scoped partial unique index.

### 14.4. Partial Unique Index

~~~javascript
db.orders.createIndex(
  { tenantId: 1, orderNo: 1 },
  {
    unique: true,
    name: "uq_tenant_order_no_string",
    partialFilterExpression: {
      orderNo: { $type: "string" }
    }
  }
)
~~~

This index only enforces uniqueness among documents matching the filter. Documents outside the filter are not constrained by this index. **Do not create both a full unique index and a partial unique index on the same keys** without clarifying your goal; the full index may defeat the purpose of the partial one.

Building a unique index on a populated collection can fail if duplicates exist. Clean up legacy data according to plan before enabling the new constraint.

## 15. Partial, Sparse, and Collation

Two indexes with identical key patterns do not necessarily share the same scope or semantics.

### 15.1. Sparse Index

~~~javascript
db.customer_profiles.createIndex(
  { nickname: 1 },
  { sparse: true, name: "idx_existing_nickname" }
)
~~~

A sparse index can omit documents lacking the indexed field according to sparse rules, so queries using it without suitable predicates risk returning incomplete results. Partial indexes generally express document selection criteria more explicitly.

### 15.2. Partial Index

For example, indexing only orders currently in progress:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, createdAt: -1 },
  {
    name: "idx_created_orders",
    partialFilterExpression: {
      status: "CREATED"
    }
  }
)
~~~

The query `{tenantId:"t-01",status:"CREATED"}` can use this index appropriately. A query requesting all statuses cannot rely solely on an index containing only `CREATED`, because it would miss `PAID` and `CANCELLED`.

The optimizer only chooses a partial index when it can verify the query needs no data outside the index's filter scope.

### 15.3. Collation

~~~javascript
db.customers.createIndex(
  { displayName: 1 },
  {
    name: "idx_name_ci",
    collation: { locale: "en", strength: 2 }
  }
)

db.customers.find({
  displayName: "alice"
}).collation({
  locale: "en",
  strength: 2
})
~~~

A collated string index can support queries comparing or sorting with the matching collation. If a query uses a different collation, the index may not support the string comparison as expected. Collation does not replace normalization and security rules for usernames or emails.

## 16. Which Queries Can Single-Field and Compound Indexes Support?

Suppose you have three indexes:

~~~javascript
// I1
{ customerId: 1 }

// I2
{ tenantId: 1, status: 1, createdAt: -1 }

// I3
{ tenantId: 1, createdAt: -1 }
~~~

| Query | Potentially suitable index | Reason |
|---|---|---|
| `customerId = c-101` | I1 | Matches the exact field |
| `tenantId = t-01` | I2 or I3 | Both have `tenantId` as a prefix |
| `tenantId=t-01 AND status=PAID ORDER BY createdAt DESC` | I2 | Equality on first two fields, sort on the third |
| `tenantId=t-01 ORDER BY createdAt DESC` | I3 | I2 has `status` in between, so it does not give global `createdAt` order |
| `status=PAID` | None with a `status` prefix | Evaluate based on actual workload |
| `createdAt from date D, no tenant filter` | None starting with `createdAt` | May require a single-field `createdAt` index |

No single index answers every query optimally. Choosing an index set means balancing active APIs against maintenance overhead.

## 17. Index Intersection: Can It Replace a Compound Index?

If you have:

~~~javascript
{ tenantId: 1 }
{ status: 1 }
{ createdAt: -1 }
~~~

MongoDB may pick one index for a query, and in certain cases combine multiple indexes via **index intersection**. Still, do not assume the planner will combine all three, or that a collection of single-field indexes supports filter+sort as well as a dedicated compound index.

A compound index ordered **tenant → status → createdAt** can serve equality filters and sorting in a single structure. Index intersection may incur extra key-merging, FETCH, or SORT work.

Therefore, for frequently executed queries:

- Inspect `winningPlan` instead of guessing what the optimizer will do.
- Compare a compound index against multiple single-field indexes.
- Sum the total footprint and write cost of both index sets.
- Do not add three single-field indexes merely because "each filter needs an index."

## 18. Managing Indexes Across the System Lifecycle

### 18.1. Listing Indexes

~~~javascript
db.orders.getIndexes()
~~~

The output includes key patterns, names, and options such as unique, partial, or collation when present. After a migration, **re-read metadata** to confirm the actual configuration.

### 18.2. Measuring Footprint

~~~javascript
const stats = db.orders.stats()

printjson({
  count: stats.count,
  size: stats.size,
  storageSize: stats.storageSize,
  totalIndexSize: stats.totalIndexSize,
  indexSizes: stats.indexSizes
})
~~~

`indexSizes` and `totalIndexSize` report storage engine footprint statistics, not the exact RAM an index occupies in cache.

### 18.3. Measuring Usage

~~~javascript
db.orders.aggregate([
  { $indexStats: {} }
])
~~~

`$indexStats` helps observe index accesses over the time window tracked by the node's metrics. A low access count does not automatically make an index useless: monthly batch jobs or rare investigative queries may still depend on it. Never drop an index based on just a few hours of observation.

### 18.4. Hiding an Index Before Dropping

On versions supporting hidden indexes:

~~~javascript
db.orders.hideIndex("idx_customer_id")

// After observation completes:
db.orders.unhideIndex("idx_customer_id")
~~~

A hidden index is not selected by the query planner for normal queries, yet it is still maintained on writes and constraints like uniqueness remain enforced. It is a tool for testing the impact of removing an index, not a way to eliminate storage or write costs.

### 18.5. Dropping an Index

~~~javascript
db.orders.dropIndex("idx_customer_id")
~~~

**Use only in labs or planned production changes.** Before dropping:

1. Identify which critical queries the index serves and when they run.
2. Check whether it enforces any unique business key.
3. Evaluate query plans with the index absent.
4. Prepare a rollback plan, rebuild cost estimate, and expected build time.
5. Monitor latency, CPU/I/O, and write throughput after deployment.

Never use `dropIndex("_id_")` to drop the default `_id` index on a standard collection.

### 18.6. Cost of Building Indexes on Large Collections

Index builds can consume CPU, I/O, RAM/temp space, and impact live load. Exact impact depends on MongoDB version and topology. When adding indexes in production, plan deployment timing, disk headroom, replication impact, build duration, monitoring, and abort/recovery procedures. Never repeatedly create and drop indexes "for quick testing" on a primary serving live traffic.

## 19. Index Design in Multi-Tenant Systems

Most SaaS APIs filter by:

~~~javascript
{ tenantId: authenticatedTenantId }
~~~

If an API also filters by status and sorts by date:

~~~javascript
db.orders.find({
  tenantId: authenticatedTenantId,
  status: "PAID"
}).sort({
  createdAt: -1,
  _id: 1
}).limit(20)
~~~

Candidate index:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1,
    _id: 1
  },
  { name: "idx_tenant_status_date_id" }
)
~~~

`_id` serves as a tie-breaker providing deterministic order when multiple documents share the same timestamp. Because `createdAt` and `_id` sort in mixed directions, the index must be designed to match that pattern.

### 19.1. Indexes Do Not Replace Authorization

Putting `tenantId` first in an index only makes queries efficient—it **does not prevent cross-tenant data access**. APIs must obtain the tenant from the authenticated context, enforce authorization checks, and inject the tenant filter properly.

### 19.2. Keyset Pagination with Deterministic Sorting

If sorting by `createdAt` descending and `_id` ascending, the cursor carries both fields:

~~~javascript
const cursorDate = ISODate("2026-01-07T10:00:00Z")
const cursorId = "ord-003"

db.orders.find({
  tenantId: "t-01",
  status: "PAID",
  $or: [
    { createdAt: { $lt: cursorDate } },
    {
      createdAt: cursorDate,
      _id: { $gt: cursorId }
    }
  ]
}).sort({
  createdAt: -1,
  _id: 1
}).limit(20)
~~~

Because `createdAt` is descending, the next page takes earlier timestamps; on ties, `_id` is ascending so it takes larger IDs. `{tenantId:1,status:1,createdAt:-1,_id:1}` is a candidate index. Queries with `$or` should be measured on realistic data.

Deterministic order **does not guarantee a frozen snapshot across HTTP requests**: inserts or updates between pages can still shift results.

## 20. Common Mistakes in Index Design

| Mistake | Consequence | Fix |
|---|---|---|
| Indexing every field | Wastes disk/cache/writes, hard to manage | Start from query shapes and SLOs |
| Treating a compound index like three single indexes | Misunderstands prefixes, filters, and sorts | Trace key order from left to right |
| Placing a sort field after a non-equality field | Query may still need a separate `SORT` | Reorder fields based on workload |
| Treating ESR as an absolute rule | Misses highly selective ranges | Compare ESR vs. range-before-sort with `explain` |
| Checking only for `IXSCAN` | Can still scan many keys, FETCH, or SORT | Measure `nReturned`, keys/docs examined, and latency |
| Assuming any projection is covered | May still FETCH documents | Verify coverage and `totalDocsExamined` |
| Using two dotted predicates on an array | May match two different elements | Use `$elemMatch` for same-element matching |
| Unique index without requiring the field | Null/missing values produce unexpected collisions | Pair validator with appropriate unique constraint |
| Dropping an index after short-term low usage | Breaks rare but critical queries | Observe across full business cycles |
| Hardcoding `hint` without data | Poor plans when data/indexes shift | Use `hint` only with verified justification |
| Benchmarking on 12 documents | Noise hides real cost | Use realistic volume and representative workload |
| Changing production indexes without a plan | Impacts builds, disk, replication, and latency | Use change management and rollback plans |

## 21. Comprehensive Lab Exercises

**Scenario:** An e-commerce system has 20 million orders, multiple tenants, and heavy write volume. Its three most critical APIs are: latest PAID orders per tenant, customer order history, and looking up orders by item SKU. Experiment in the lab and propose a minimal index set to support these APIs.

### Exercise 1 — Single-Field Index

Create `{customerId:1}` and query orders for `c-101`. Predict the returned IDs and run `explain("executionStats")`. Why might the plan show `COLLSCAN` on a small dataset even though the index exists?

### Exercise 2 — Time-Ordered Index

Create `{createdAt:-1}` and retrieve the 5 latest orders system-wide. Write an ascending-sort query and explain why a second index with direction `1` is not automatically needed.

### Exercise 3 — Prefix Rule

Given `{tenantId:1,status:1,createdAt:-1}`:

1. List all three prefixes.
2. Explain why a query filtering only on `status` lacks a suitable prefix.
3. Explain why a query filtering by tenant and sorting by `createdAt` may need a dedicated `{tenantId:1,createdAt:-1}` index.

### Exercise 4 — ESR

Given the query:

~~~javascript
db.orders.find({
  tenantId: "t-01",
  amount: { $gte: NumberDecimal("100000") }
}).sort({ createdAt: -1 }).limit(20)
~~~

Compare two indexes:

~~~javascript
{ tenantId: 1, createdAt: -1, amount: 1 }
{ tenantId: 1, amount: 1, createdAt: -1 }
~~~

Which index prioritizes sorting? Which index can narrow the range earlier? If the range matches only 0.1% of documents, how might the trade-off shift?

### Exercise 5 — Sort Direction

With `{tenantId:1,createdAt:-1,amount:1}` and equality on `tenantId`, explain:

- Sort `{createdAt:-1,amount:1}`.
- Sort `{createdAt:1,amount:-1}`.
- Sort `{createdAt:-1,amount:-1}`.

Which cases match the index pattern or its exact full reversal?

### Exercise 6 — Covered Query

With `{tenantId:1,status:1,createdAt:-1}`, write a query returning only those three fields while excluding `_id`. Then add `amount` to the projection and inspect `explain`. Distinguish **returning fewer fields** from **reading zero documents**.

### Exercise 7 — Multikey

Create `{"items.sku":1}` and `{"items.sku":1,"items.qty":1}`. Write a query finding an item with both `sku = "A"` and `qty >= 2`; explain the role of `$elemMatch`.

### Exercise 8 — Unique Business Key

Design a unique index for `tenantId + orderNo`. Before creating it on a legacy collection, how should you check for missing, null, or duplicate `orderNo` values? Explain how to combine a validator with a partial unique index if uniqueness applies only to orders that have a code.

### Exercise 9 — Measuring and Pruning Indexes

Suppose 8 different indexes already exist. Record `getIndexes()`, `$indexStats`, and `indexSizes`. Identify indexes that may overlap in prefix or add little value, but **do not drop** any until rare queries, unique constraints, and a rollback plan are confirmed.

### Exercise 10 — Choosing the Final Index Set

Fill out the table based on a real workload:

| Query | Frequency | SLO | Candidate index | `explain` result | Write / index cost |
|---|---|---|---|---|---|
| Latest PAID orders per tenant | … | … | … | … | … |
| Customer order history | … | … | … | … | … |
| Orders containing SKU A | … | … | … | … | … |
| Amount range report | … | … | … | … | … |

Do not invent "measured" numbers without running actual measurements; record assumptions and a test plan instead.

## 22. Review Questions and Answers

**1. How does a single-field index differ from a compound index?**

A single-field index organizes keys by one field; a compound index organizes keys across multiple fields in a **specific key order**. A compound index is not equivalent to a set of single-field indexes.

**2. What are the three prefixes of `{tenantId:1,status:1,createdAt:-1}`?**

`{tenantId:1}`, `{tenantId:1,status:1}`, and the full `{tenantId:1,status:1,createdAt:-1}`.

**3. Does that index replace `{status:1}` for a query filtering only on `status`?**

Not by default; `status` follows `tenantId`, so the index has no prefix starting with `status`.

**4. Why can omitting an equality condition on a middle field hurt sorting?**

Keys are grouped by the middle field first, so trailing field order holds only within each group rather than across the entire result set.

**5. Do you need both single-field indexes `{createdAt:1}` and `{createdAt:-1}`?**

Not by default. A single-field index can be scanned in either direction; for multi-field compound sorts, direction combinations are stricter.

**6. What does ESR stand for?**

Equality–Sort–Range: placing equality fields, then sort fields, then range fields is a common heuristic. With very selective ranges, placing range before sort can sometimes perform better.

**7. Does seeing `IXSCAN` prove a query is fast?**

No. It could still scan huge numbers of keys, FETCH many documents, or perform a SORT. Inspect execution metrics.

**8. When can a query be covered?**

When the index satisfies all filter conditions and projected fields under supported rules, avoiding document reads. Verify via the plan and `totalDocsExamined`.

**9. Does a unique index force a field to exist?**

No. Uniqueness prevents duplicate keys; validation handles required/type rules. Null/missing values carry specific uniqueness semantics.

**10. Does unique compound `{tenantId:1,orderNo:1}` allow two tenants to share the same `orderNo`?**

Yes, because uniqueness applies to the two-field combination.

**11. Why is `$elemMatch` important with a compound multikey index on `items`?**

It ensures item predicates apply to **the same array element**, while also helping the planner combine index bounds.

**12. Why shouldn't you build one compound index containing all fields?**

Large indexes increase write overhead and disk footprint, and key order may not align with real queries and sorts.

**13. When should `hint()` be used?**

To compare or investigate specific indexes in a controlled way, not to permanently pin production queries by default.

**14. Should an index be dropped if `$indexStats` shows low accesses over one hour?**

That is insufficient evidence. Daily/monthly queries or rare operational tasks may still rely on it.

## 23. Quick-Reference Command Cheat Sheet

| Purpose | Command |
|---|---|
| Create single-field index | `db.orders.createIndex({customerId:1})` |
| Create descending index | `db.orders.createIndex({createdAt:-1})` |
| Create compound index | `db.orders.createIndex({tenantId:1,status:1,createdAt:-1})` |
| Create unique compound index | `db.orders.createIndex({tenantId:1,orderNo:1},{unique:true})` |
| List indexes | `db.orders.getIndexes()` |
| Explain a query | `db.orders.find(filter).explain("executionStats")` |
| Explain a sorted query | `db.orders.find(filter).sort(sort).explain("executionStats")` |
| Test a specific index | `db.orders.find(filter).hint("index_name").explain("executionStats")` |
| Check index sizes | `db.orders.stats().indexSizes` |
| Check index usage | `db.orders.aggregate([{$indexStats:{}}])` |
| Hide an index if supported | `db.orders.hideIndex("index_name")` |
| Unhide an index | `db.orders.unhideIndex("index_name")` |
| Drop an index | `db.orders.dropIndex("index_name")` |

## 24. Conclusion

**Single-field indexes** fit queries centered primarily on one field. **Compound indexes** can efficiently serve an access pattern combining filters, sorts, and even projections, yet key order is decisive: MongoDB organizes keys left-to-right, uses prefixes to narrow ranges, and serves sort order only when preceding conditions align.

Start from the **filter + sort + projection** of real queries, use prefixes and ESR to propose candidate indexes, and verify with `explain("executionStats")` under representative workloads. Finally, balance read gains against write, disk, cache, and operational costs. **A small set of indexes tailored to your workload is usually far more valuable than many indexes mismatched to how the application accesses data.**
