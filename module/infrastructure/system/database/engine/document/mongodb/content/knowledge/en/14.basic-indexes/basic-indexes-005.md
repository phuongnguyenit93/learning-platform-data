# The Equality, Sort, Range Principle and Query-Based Trade-Offs in MongoDB

> **Module:** Database Engine Document MongoDB  
> **Chapter:** Basic Indexes

## 1. Why Does Field Order in an Index Matter?

MongoDB supports **indexes** to locate, filter, and sort documents far more efficiently than scanning an entire collection. Yet simply putting the right fields into a **compound index** is not enough: **field order** can determine whether a query locates a narrow key range, reads data in pre-sorted order, or ends up filtering and sorting large numbers of documents afterward.

Suppose an API needs to fetch a store's 20 most recent paid orders with a total of 100 or more:

```javascript
db.orders.find({
  tenantId: "shop-a",
  status: "PAID",
  total: { $gte: 100 }
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
```

The query criteria involve three kinds of operations:

- **Equality (E):** `tenantId = "shop-a"` and `status = "PAID"`.
- **Sort (S):** ordering by `createdAt DESC`, then `_id DESC` for deterministic tie-breaking on identical timestamps.
- **Range (R):** `total >= 100`.

For this query, an **ESR**-oriented index could be:

```javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: -1, total: 1 },
  { name: "idx_orders_tenant_status_created_id_total" }
);
```

This index prioritizes locating the right tenant/status slice, then scanning in chronological order to return the latest page while checking the `total` condition. However, if `total >= 100` matches only a tiny fraction of the data, placing the range earlier might examine far fewer keys—even at the cost of a separate sort. That is why **ESR is a query-driven index selection guideline, not a formula that always wins**.

After this lesson, you will be able to:

1. Identify equality, sort, and range predicates in MongoDB queries.
2. Distinguish single-field indexes, compound indexes, and **index prefixes**.
3. Explain the ESR principle: Equality → Sort → Range.
4. Recognize exceptions where **ERS** (Equality → Range → Sort) should be considered.
5. Read `explain("executionStats")` plans to evaluate `IXSCAN`, `FETCH`, `SORT`, and keys/documents examined.
6. Weigh read performance alongside write overhead, storage, RAM, and index maintenance costs.
7. Design, test, and select indexes for specific queries rather than mechanically indexing every field.

## 2. Mental Model: Compound Indexes Are Ordered by Key Sequence

Given the compound index:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

MongoDB stores index entries in the corresponding key order: first by `tenantId` ascending, within each tenant by `status` ascending, and within each tenant/status by `createdAt` descending. Conceptually:

```text
tenantId = shop-a
    status = CANCELLED
        createdAt newest -> oldest
    status = NEW
        createdAt newest -> oldest
    status = PAID
        createdAt newest -> oldest
tenantId = shop-b
    status = CANCELLED
        createdAt newest -> oldest
    status = NEW
        createdAt newest -> oldest
    status = PAID
        createdAt newest -> oldest
...
```

This is a **logical key-order illustration**, not a complete description of the storage engine's physical layout. B-tree / B-tree-like indexes help MongoDB seek to a position and scan matching key ranges without reading every document in the collection.

When conditions pin `tenantId` and `status`, keys within that slice are already ordered by `createdAt DESC`. The server can return results in the desired order by scanning the index without a separate **blocking sort** step.

If only this index existed:

```javascript
{ tenantId: 1, total: 1, createdAt: -1 }
```

then within each tenant, entries are grouped by `total` first; all entries matching `total >= 100` are **not globally sorted by `createdAt`**. The trailing sort may require a separate sort stage.

### 2.1. Meaning of `1` and `-1`

- `1`: ascending order in the index key.
- `-1`: descending order.
- For a single field, the index can be scanned forward or backward for either sort direction.
- For a compound index with multiple sort fields, the **relative direction between fields** matters.

For example, the index:

```javascript
{ createdAt: -1, _id: -1 }
```

can serve `{ createdAt: -1, _id: -1 }` or its exact inverse `{ createdAt: 1, _id: 1 }`. However, a mixed sort `{ createdAt: -1, _id: 1 }` does not share the same directional relationship and is not automatically satisfied by this index.

### 2.2. Field Order in a Filter Does Not Dictate Index Order

The two filters below express the same condition:

```javascript
{ tenantId: "shop-a", status: "PAID" }

{ status: "PAID", tenantId: "shop-a" }
```

Swapping field order inside a filter object does not make MongoDB build or pick a different index. What matters are **the query optimizer, the set of predicates, and the key order of existing indexes**.

## 3. Equality (E): Exact-Match Predicates

Equality commonly appears with `$eq` or shorthand notation:

```javascript
{ tenantId: "shop-a" }
{ status: { $eq: "PAID" } }
{ _id: ObjectId("507f1f77bcf86cd799439011") }
```

When equality fields lead a compound index, they narrow down the key range to scan. For example:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

The query:

```javascript
db.orders.find({
  tenantId: "shop-a",
  status: "PAID"
}).sort({ createdAt: -1 });
```

can jump straight to the key slice for one specific tenant and status and scan chronologically instead of inspecting all tenants.

### 3.1. One or Multiple Equality Fields?

If a filter has multiple equality predicates, those fields are generally placed ahead of sort and range fields:

```javascript
{ tenantId: 1, status: 1, channel: 1, createdAt: -1 }
```

MongoDB can leverage the equality prefix `tenantId + status + channel`. Among **equality fields themselves**, there is no universal rule like "always put the most selective field first" across all workloads. Prioritize index prefix reuse for critical queries, then measure real performance.

Example API queries:

| Query | Filter |
|---|---|
| Store orders page | `tenantId = ?` |
| Store orders by status page | `tenantId = ? AND status = ?` |
| Store orders by status and channel page | `tenantId = ? AND status = ? AND channel = ?` |

For these three queries, leading with `tenantId` lets one compound index serve multiple patterns. Conversely, if most queries filter first by `status` without `tenantId`, a different order or a separate index may be needed.

### 3.2. Equality Does Not Always Mean High Selectivity

`status = "PAID"` might match 70% of the collection; `tenantId = "shop-a"` might match only 1%. Both are equality predicates, yet their filtering power differs dramatically.

**Selectivity** describes how tightly a predicate narrows the document set. A highly selective predicate retains few documents; a low-selectivity predicate retains many. Prioritizing equality in ESR helps locate key slices and preserve sort order, while still requiring attention to data distribution and query patterns.

## 4. Sort (S): Leveraging Pre-Ordered Keys in the Index

Sorting occurs when a query specifies an output order:

```javascript
db.orders.find({ tenantId: "shop-a" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
```

A suitable index:

```javascript
{ tenantId: 1, createdAt: -1, _id: -1 }
```

Once `tenantId` is pinned by equality, the remainder of the index is already ordered by `createdAt DESC, _id DESC`. MongoDB can walk the index and return the first 20 items in order without collecting and sorting the full result set.

### 4.1. Why Placing Sort Before Range Is Often Useful

Suppose the filter includes `total >= 100`:

```javascript
db.orders.find({
  tenantId: "shop-a",
  status: "PAID",
  total: { $gte: 100 }
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
```

If the index puts sort fields before the range field:

```javascript
{ tenantId: 1, status: 1, createdAt: -1, _id: -1, total: 1 }
```

then after pinning tenant and status, the cursor can scan orders in descending chronological order and check `total >= 100`. Once 20 matching orders are found, the query can stop early thanks to `limit(20)`.

However, if only 1 in 10,000 orders satisfies the range, scanning in chronological order may have to skip huge numbers of index entries. That is the case to compare against ERS in a later section.

### 4.2. What Is a Non-Indexed Sort?

When MongoDB cannot use index key order to satisfy a sort requirement, it may introduce a **SORT** stage in the execution plan. A blocking sort must gather all relevant matching items before emitting sorted output, although **sort + limit** optimizations can cap how many items are buffered in memory.

An aligned index usually avoids this sort cost; nevertheless, not every query with a `SORT` stage is bad. If a range filter is extremely selective and leaves only a handful of documents, a tiny sort can be cheaper than scanning vast numbers of keys to preserve order.

### 4.3. Deterministic Sort Order for Pagination

If multiple orders share the same `createdAt`, sorting by:

```javascript
.sort({ createdAt: -1 })
```

leaves the order among tied documents undefined. Adding `_id` as a tie-breaker:

```javascript
.sort({ createdAt: -1, _id: -1 })
```

provides a deterministic order, which is especially important for keyset cursor pagination. Design the index to match the actual sort order, such as `{ tenantId: 1, createdAt: -1, _id: -1 }`.

## 5. Range (R): Inequality Predicates and Value Ranges

Range predicates commonly look like:

```javascript
{ total: { $gte: 100 } }
{ total: { $gt: 100, $lt: 500 } }
{ createdAt: { $gte: ISODate("2026-01-01T00:00:00Z") } }
{ score: { $lte: 90 } }
```

These predicates define a **span of values** rather than a single fixed equality key. An index on the range field lets the server scan just that key slice:

```javascript
db.orders.createIndex({ total: 1 });
db.orders.find({ total: { $gte: 100, $lt: 500 } });
```

Range-like operators also include `$ne` or `$nin` in many contexts, though their selectivity is typically low; having an inequality operator **does not guarantee** an index will be effective.

### 5.1. Why Placing Range Before Sort Breaks Index-Assisted Sorting

Consider the index:

```javascript
{ tenantId: 1, status: 1, total: 1, createdAt: -1 }
```

After equality on `tenantId` and `status`, the index orders entries by **total** ascending. Across the range `total` from 100 to 500, documents are grouped by `total`; `createdAt` order holds only within each distinct `total` value. Consequently, the overall result set **is not globally ordered by `createdAt DESC`** and may require a separate `SORT` stage.

Putting range after sort in ESR preserves result ordering along the sort field when scanning enough index keys for the range is acceptable.

### 5.2. Highly Selective Ranges May Be Worth Putting Before Sort

If 99.99% of orders have `total` under 100,000 and only 0.01% exceed it, the query:

```javascript
db.orders.find({
  tenantId: "shop-a",
  status: "PAID",
  total: { $gte: 100000 }
})
.sort({ createdAt: -1 })
.limit(20);
```

may run more efficiently with:

```javascript
{ tenantId: 1, status: 1, total: 1, createdAt: -1 }
```

because the range on `total` drastically shrinks the number of keys scanned. Sorting those few matching documents can cost far less than scanning a massive number of chronologically ordered entries.

This is a conditional **ERS** choice—not automatically better for every range. Measure with representative data.

## 6. The ESR Guideline: Equality → Sort → Range

**ESR** is a guideline for ordering fields in a **compound index** serving queries that combine equality, sort, and range:

```text
E (Equality) -> S (Sort) -> R (Range)
   pin the       preserve      check value
   prefix         order          bounds
```

Example query:

```javascript
db.orders.find({
  tenantId: "shop-a",                // E
  status: "PAID",                    // E
  total: { $gte: 100, $lte: 500 }   // R
})
.sort({ createdAt: -1, _id: -1 })   // S
.limit(20);
```

ESR index:

```javascript
db.orders.createIndex(
  {
    tenantId: 1,        // E
    status: 1,          // E
    createdAt: -1,      // S
    _id: -1,            // S
    total: 1            // R
  },
  { name: "idx_esr_orders" }
);
```

Potential benefits:

1. `tenantId + status` narrows down the key region.
2. Within that region, keys are already ordered by `createdAt DESC, _id DESC`.
3. The `total` predicate can be evaluated from index entries or after fetching documents depending on the plan.
4. `limit(20)` allows stopping once 20 qualifying documents are collected.

**Trade-off:** a trailing range field may not narrow the scanned index region aggressively, especially when documents matching the range are scarce. Never assume an ESR index guarantees speed just by looking at its field order.

### 6.1. ESR Is a Guideline, Not Required Syntax

MongoDB does not require an index to follow ESR for a query to execute. A query can run via COLLSCAN or another index. ESR helps predict how well an index supports both filtering and sorting; the planner still chooses plans based on statistics and data state.

An index containing every queried field is not always better than a leaner index. Extra fields enlarge the index and increase write and memory costs. Prioritize **genuinely critical queries** based on workload instead of stuffing every document field into one index.

### 6.2. Queries Without a Sort

For:

```javascript
db.orders.find({
  tenantId: "shop-a",
  status: "PAID",
  total: { $gte: 100 }
});
```

`{ tenantId: 1, status: 1, total: 1 }` is the natural **E → E → R** choice. There is no need to insert unused sort fields unless you want the index shared across other query patterns.

### 6.3. Queries Without a Range

For:

```javascript
db.orders.find({
  tenantId: "shop-a",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
```

`{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }` is the **E → E → S** pattern, very common for status-filtered, paginated lists.

## 7. When to Consider ERS: Equality → Range → Sort

An **ERS**-ordered index places the range field ahead of the sort fields:

```javascript
db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    total: 1,
    createdAt: -1,
    _id: -1
  },
  { name: "idx_ers_orders" }
);
```

### 7.1. Reasons to Test ERS

ERS can win when:

- The range predicate is **highly selective**, dramatically cutting down keys/documents examined.
- The post-range result set is small enough that sorting cost is negligible.
- Sufficient RAM/resources exist for sorting, or the query uses an efficient bounded sort strategy.
- Filtering down to a tiny set of documents matters more than maintaining full index sort order.

### 7.2. Reasons ESR Can Win

ESR can win when:

- Many documents remain after equality and the range is not overly selective.
- The query uses `sort + limit` and must return the first page very quickly.
- Index-supplied sorting avoids a blocking `SORT` stage.
- Continuous chronological pagination can terminate an index scan early once enough rows are read.

### 7.3. Comparison Table: ESR vs. ERS

| Criterion | ESR | ERS |
|---|---|---|
| Index order | Equality → Sort → Range | Equality → Range → Sort |
| Strength | Preserves sort order from the index after the equality prefix | Minimizes key scans when the range is highly selective |
| Separate SORT stage | Often avoided | Usually needed if the range spans many values |
| With `limit(20)` | Can fetch the top 20 in order quickly | May need to filter the range and sort before taking 20 |
| When range matches very few rows | May scan many keys failing the range filter | Typically scans fewer keys |
| Storage cost | Depends on actual fields/index | Similar if composed of the same fields |
| How to choose | Measure against realistic workload and data | Measure against realistic workload and data |

**No rule such as "range must always go last" or "most selective field must always go first" holds for every query.** Analyze predicates and sort requirements, then use `explain` for hard evidence.

## 8. Compound Indexes and the Index Prefix Rule

Suppose an index is:

```javascript
{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }
```

Its **prefixes** are:

1. `{ tenantId: 1 }`
2. `{ tenantId: 1, status: 1 }`
3. `{ tenantId: 1, status: 1, createdAt: -1 }`
4. The full index `{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }`

The index can effectively serve multiple queries starting with its prefixes:

```javascript
// Can leverage the tenantId prefix:
db.orders.find({ tenantId: "shop-a" });

// Can leverage the tenantId + status prefix:
db.orders.find({ tenantId: "shop-a", status: "PAID" });

// Can leverage equality prefix + sort:
db.orders.find({ tenantId: "shop-a", status: "PAID" })
  .sort({ createdAt: -1, _id: -1 });
```

Whereas the query:

```javascript
db.orders.find({ status: "PAID" });
```

**does not use the `tenantId` prefix**. MongoDB might still pick a plan involving this compound index in certain circumstances, yet it generally loses the benefit of jumping to a narrow key range that a prefix-matched query enjoys.

### 8.1. Sorting on Fields That Do Not Start the Index

In certain cases, MongoDB can sort using a **non-prefix subset** of an index if every field preceding that subset is pinned by equality.

For example, given:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

The query:

```javascript
db.orders.find({ tenantId: "shop-a", status: "PAID" })
  .sort({ createdAt: -1 });
```

can use index sort order because both fields ahead of `createdAt` are fixed by equality. If you drop the `status` condition:

```javascript
db.orders.find({ tenantId: "shop-a" })
  .sort({ createdAt: -1 });
```

then the tenant's documents span multiple `status` groups; `createdAt` order is **not contiguous** across all status groups. This index will not automatically provide a global `createdAt` sort for that query.

### 8.2. Should You Also Keep a Single-Field Prefix Index?

If `{ tenantId: 1, status: 1 }` already exists, a separate `{ tenantId: 1 }` index may be redundant in many workloads because the compound index starts with `tenantId`. Still, before dropping the single-field index, verify:

- Whether the indexes differ in unique, sparse, partial, or collation properties.
- Whether any high-frequency query relies on the smaller index for better read/working-set efficiency.
- Whether any query depends on a hint, specific plan, or operational purpose.
- Whether you have sufficient write/storage and query-frequency data to decide.

Never drop an index purely from prefix inspection without reviewing the workload.

## 9. Hands-On Example: Collection and Real Queries

Create a lab database for illustrative data. Install MongoDB Server and connect with `mongosh` using write permissions on the practice database.

```javascript
const lab = db.getSiblingDB("esr_index_lab");
const orders = lab.getCollection("orders");

orders.insertMany([
  {
    _id: "O-001", tenantId: "shop-a", status: "PAID",
    total: 120, createdAt: ISODate("2026-01-11T10:00:00Z")
  },
  {
    _id: "O-002", tenantId: "shop-a", status: "PAID",
    total: 500, createdAt: ISODate("2026-01-12T10:00:00Z")
  },
  {
    _id: "O-003", tenantId: "shop-a", status: "NEW",
    total: 80, createdAt: ISODate("2026-01-13T10:00:00Z")
  },
  {
    _id: "O-004", tenantId: "shop-a", status: "PAID",
    total: 25, createdAt: ISODate("2026-01-14T10:00:00Z")
  },
  {
    _id: "O-005", tenantId: "shop-a", status: "PAID",
    total: 230, createdAt: ISODate("2026-01-15T10:00:00Z")
  },
  {
    _id: "O-006", tenantId: "shop-a", status: "CANCELLED",
    total: 180, createdAt: ISODate("2026-01-16T10:00:00Z")
  },
  {
    _id: "O-007", tenantId: "shop-b", status: "PAID",
    total: 1000, createdAt: ISODate("2026-01-17T10:00:00Z")
  },
  {
    _id: "O-008", tenantId: "shop-b", status: "PAID",
    total: 35, createdAt: ISODate("2026-01-18T10:00:00Z")
  },
  {
    _id: "O-009", tenantId: "shop-a", status: "PAID",
    total: 700, createdAt: ISODate("2026-01-19T10:00:00Z")
  },
  {
    _id: "O-010", tenantId: "shop-a", status: "PAID",
    total: 150, createdAt: ISODate("2026-01-20T10:00:00Z")
  }
]);
```

This is a tiny learning dataset; it is meaningless for benchmarking production index speed. If inserts fail with duplicate `_id` errors from an earlier run, use a different lab database or clean up test data carefully. Never drop collections belonging to real applications.

Query to analyze:

```javascript
const filter = {
  tenantId: "shop-a",
  status: "PAID",
  total: { $gte: 100 }
};

const sort = { createdAt: -1, _id: -1 };

printjson(
  orders.find(filter, { _id: 1, tenantId: 1, status: 1, total: 1, createdAt: 1 })
    .sort(sort)
    .limit(3)
    .toArray()
);
```

With the sample data, the three latest matching orders are `O-010` (150), `O-009` (700), and `O-005` (230). Order `O-004` has `total` 25, so it is excluded even though it is chronologically closer.

### 9.1. Create an ESR Index

```javascript
orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1,
    _id: -1,
    total: 1
  },
  { name: "idx_esr" }
);
```

### 9.2. Create an ERS Index for Comparison

```javascript
orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    total: 1,
    createdAt: -1,
    _id: -1
  },
  { name: "idx_ers" }
);
```

The two indexes differ in the ordering of `total` and the sort fields. They consume extra storage and incur maintenance overhead whenever documents are written or updated, so in a real application avoid keeping both permanently if the workload only needs one.

### 9.3. Inspect the Index List

```javascript
printjson(orders.getIndexes());
```

Alongside the two custom indexes, the collection has the default `_id` index. This highlights the distinction between **declared indexes** and **indexes selected by the query planner**: an index's existence does not prove every query uses it.

## 10. Using explain("executionStats") to Make Decisions

A practical way to verify behavior is running the query with:

```javascript
const query = orders.find(filter)
  .sort(sort)
  .limit(3);

printjson(query.explain("executionStats"));
```

Output provides details on the plan and execution. Stage names and JSON structure may vary across MongoDB versions and query engines. Look for fields showing:

| Field / stage | What to look for |
|---|---|
| `IXSCAN` | Index scan over key bounds/predicates |
| `COLLSCAN` | Collection scan instead of index lookup |
| `FETCH` | Retrieving actual documents from the collection using index pointers |
| `SORT` | Separate sort step; evaluate cost and index-sort eligibility |
| `PROJECTION_COVERED` or equivalent projection stage | Ability to return fields from the index without reading documents |
| `nReturned` | Actual number of results returned by the recorded execution |
| `totalKeysExamined` | Number of index keys inspected |
| `totalDocsExamined` | Number of documents inspected/fetched |
| `executionTimeMillis` | Execution time measured in explain under current run conditions |
| `indexBounds` | Index key range bounds applied by the query |
| `indexName` | Name of the index used in the executing stage |

None of these fields **alone suffices for a conclusion**. Interpret returned counts, keys/documents examined, sorts, data size, cache state, and actual application latency together.

### 10.1. Controlled Comparison with hint

To force MongoDB to test a specific index, use `hint()` in your lab environment:

```javascript
const esrPlan = orders.find(filter)
  .sort(sort)
  .limit(3)
  .hint("idx_esr")
  .explain("executionStats");

const ersPlan = orders.find(filter)
  .sort(sort)
  .limit(3)
  .hint("idx_ers")
  .explain("executionStats");

printjson({
  esr: esrPlan.executionStats,
  ers: ersPlan.executionStats
});
```

Depending on version, the plan tree lives inside `queryPlanner` and stage details may vary. With only 10 lab documents, timing differences have no statistical significance. For real workload evaluation, use representative data volumes, query mixes, and production-like read/write concurrency.

**`hint()` can lock in a bad plan** if data distributions shift. Use it for controlled comparisons or well-evidenced edge cases; do not hardcode hints into every query by default.

### 10.2. Recognizing Whether the Index Serves the Sort

If the ESR index is selected appropriately, the planner can exploit `createdAt DESC, _id DESC` ordering and avoid a separate blocking `SORT`.

When using the ERS index with `total >= 100`, keys are grouped by `total`, so a query needing global chronological order will typically exhibit a `SORT` stage. That **does not automatically make ERS slower**: if the range filters out nearly everything, the tiny sort cost may be well worth it.

### 10.3. Why `keysExamined` Matters

Suppose a query returns 20 documents:

- Plan A: `totalKeysExamined = 25`.
- Plan B: `totalKeysExamined = 200000`.

All else being equal, Plan A is typically more efficient because it inspects far fewer keys. Yet if Plan A has to sort huge documents while Plan B avoids sorting and streams the first page faster, evaluation requires examining actual timings, memory, and dataset characteristics.

These numbers are **illustrative examples**, not measurements from the lab dataset.

### 10.4. Can `docsExamined` Be 0?

Yes, in a qualifying **covered query**: all filter and projection fields exist in the index, and all engine requirements to skip FETCH are satisfied. For example:

```javascript
orders.find(
  { tenantId: "shop-a", status: "PAID" },
  { _id: 0, tenantId: 1, status: 1, createdAt: 1 }
)
.sort({ createdAt: -1 });
```

If an eligible index contains the required fields and the query satisfies engine coverage rules, the server can return results straight from the index. Confirm via the plan and `totalDocsExamined`. Exclude `_id` from the projection whenever the index does not include `_id`; do not assume secondary indexes automatically cover `_id` in every situation.

**Note:** Array fields (multikey), collations, expression types, and projections can all affect coverage eligibility; never infer coverage from an index name alone.

## 11. Equality, Sort, and Range with Special Predicate Types

### 11.1. Is `$in` Equality?

`$in` matches a field against a list of values:

```javascript
db.orders.find({
  status: { $in: ["PAID", "NEW"] }
}).sort({ createdAt: -1 });
```

`$in` is not identical to a single equality when results from multiple values must be merged. MongoDB can execute multiple index scan branches and merge-sort them under certain conditions. With very large lists, its behavior approaches that of a range operator.

MongoDB documentation notes specific thresholds on `$in` array length in certain `sort` scenarios; that is an implementation detail that can evolve across releases. When combining `$in` with `sort`, verify with `explain` on your running version rather than treating a fixed count as a permanent design rule.

### 11.2. `$ne` and `$nin`

`$ne` and `$nin` typically have low selectivity, for instance:

```javascript
{ status: { $ne: "CANCELLED" } }
```

If most orders are not `CANCELLED`, an index on `status` barely narrows the result set. Depending on workload, COLLSCAN may rival or outperform index scan + FETCH.

### 11.3. Regex and String Prefixes

A prefix-anchored regex such as:

```javascript
{ sku: /^ABC/ }
```

can utilize an index range scan on a string index under qualifying conditions. Regexes with leading wildcards like `/.*ABC/` generally cannot exploit index prefixes to narrow the key region.

Case-sensitive vs. case-insensitive regexes and collations have specific index usage limitations; do not assume a case-insensitive collated index accelerates every `/i` regex.

### 11.4. Array Predicates and Multikey Indexes

If an indexed field contains an array, MongoDB creates a **multikey index**. Filtering, sorting, and coverage rules for multikey indexes are more complex than for scalar indexes, especially with multiple array fields and `$elemMatch`.

For instance, querying `tags` while sorting by `createdAt` requires checking actual index behavior, document structure, and multikey limits. **Never mechanically apply scalar ESR rules to every array query.**

### 11.5. Collation and String Comparison

Indexes are built with a specific collation. To let an index assist collation-sensitive string comparisons or sorts, queries must specify a matching collation:

```javascript
db.customers.createIndex(
  { tenantId: 1, name: 1 },
  { name: "idx_customer_name_ci", collation: { locale: "en", strength: 2 } }
);

db.customers.find({ tenantId: "shop-a" })
  .collation({ locale: "en", strength: 2 })
  .sort({ name: 1 });
```

This illustrates collation syntax; do not run it if the `customers` collection does not exist yet. Collation changes comparison and ordering semantics, making it part of the query and index contract.

## 12. More Indexes Are Not Always Better

Every index requires storage and updates whenever indexed document fields change. A collection with many indexes increases costs across:

- **Inserts:** adding entries to every affected index.
- **Updates:** updating index entries whenever indexed fields change.
- **Deletes:** removing document entries from all indexes.
- **Disk/storage:** indexes consume space and can bloat total index footprint.
- **RAM/cache:** index working sets compete with document data and other structures for cache memory.
- **Builds/maintenance:** building indexes consumes I/O and CPU and requires careful production rollout strategies.
- **Planner:** too many overlapping indexes complicate plan selection and operational governance.

### 12.1. Example of Three Nearly Identical Indexes

```javascript
{ tenantId: 1, status: 1 }
{ tenantId: 1, status: 1, createdAt: -1 }
{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }
```

Prefix-wise, the longest index can serve many queries covered by the two shorter ones. Yet the longer index is larger and may be less optimal for queries needing only narrow keys. Decide what to keep or drop only after checking call frequency, latency, write load, unique/partial/collation options, and workload dependencies.

### 12.2. Is "One Index per Endpoint" Good Practice?

If an API has 50 endpoints built around 5 dominant query shapes, creating 50 indexes is excessive. Conversely, if one ultra-critical query has a strict low-latency SLA, a dedicated index may be well worth its cost.

Focus on **query patterns**, for example:

| Query pattern | Filter / sort fields | Candidate index |
|---|---|---|
| Orders by tenant | E: `tenantId`; S: `createdAt DESC` | `{ tenantId: 1, createdAt: -1, _id: -1 }` |
| Orders by tenant + status | E: `tenantId`/`status`; S: `createdAt DESC` | `{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }` |
| High-value orders | E: `tenantId`/`status`; R: `total` | `{ tenantId: 1, status: 1, total: 1 }` |
| High-value orders, newest first | E: `tenantId`/`status`; R: `total`; S: `createdAt DESC` | Compare ESR vs. ERS |
| Order lookup by ID | E: `_id` | Default `_id` index |

You do not need to create every listed candidate. One index serving multiple patterns is often better than several specialized indexes if performance requirements are met.

## 13. Partial Indexes, Unique Indexes, and Index Eligibility

A **partial index** indexes only documents matching a filter specified at index creation, reducing index size and write maintenance compared to a full-collection index when queries target a specific subset.

For example, if most queries target orders in `PAID` status:

```javascript
db.orders.createIndex(
  { tenantId: 1, createdAt: -1, _id: -1 },
  {
    name: "idx_paid_orders",
    partialFilterExpression: { status: "PAID" }
  }
);
```

To allow the planner to use the partial index without missing documents, the query must include a matching or narrower condition guaranteeing results lie within the indexed subset:

```javascript
db.orders.find({
  tenantId: "shop-a",
  status: "PAID"
}).sort({ createdAt: -1, _id: -1 });
```

A query without `status: "PAID"` cannot rely on this partial index to return all orders, because documents in other states are absent from the index.

**Do not confuse partial indexes with ESR.** ESR governs **field order inside an index**; partial filters govern **which documents receive index entries**. Both can be combined when the workload warrants it.

A unique index enforces **uniqueness** (such as unique `orderId` values) while also assisting lookups. A dedicated unique index represents a business invariant; never drop it just because another compound index handles sorting or ranges.

## 14. Applying ESR in the MongoDB Java Sync Driver

E/S/R principles are language-agnostic. The Java driver provides typed builders for filters, sorts, and indexes.

The examples below use `org.mongodb:mongodb-driver-sync` and assume MongoDB Server is running with data populated in the lab database.

### 14.1. Creating a Compound Index in Java

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import static com.mongodb.client.model.Indexes.ascending;
import static com.mongodb.client.model.Indexes.compoundIndex;
import static com.mongodb.client.model.Indexes.descending;

public final class CreateEsrIndex {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            uri = "mongodb://127.0.0.1:27017";
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> orders = client
                    .getDatabase("esr_index_lab")
                    .getCollection("orders");

            String indexName = orders.createIndex(
                    compoundIndex(
                            ascending("tenantId", "status"),
                            descending("createdAt", "_id"),
                            ascending("total")
                    )
            );

            System.out.println("Created/existing index: " + indexName);
        }
    }
}
```

The Java library returns the created index name or an existing matching index name per server rules. In real applications, indexes are typically managed through migration/deployment scripts or controlled admin processes rather than rebuilt on every application startup.

### 14.2. Writing an E/S/R Query in Java

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import org.bson.Document;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.gte;
import static com.mongodb.client.model.Sorts.descending;

// Assuming orders is an initialized MongoCollection<Document>:
try (MongoCursor<Document> cursor = orders.find(
        and(
                eq("tenantId", "shop-a"),
                eq("status", "PAID"),
                gte("total", 100)
        )
    )
    .sort(descending("createdAt", "_id"))
    .limit(20)
    .batchSize(20)
    .iterator()) {

    while (cursor.hasNext()) {
        System.out.println(cursor.next().toJson());
    }
}
```

Explanation:

- `eq` on `tenantId` and `status` creates equality filters.
- `gte("total", 100)` is the range predicate.
- `sort(descending("createdAt", "_id"))` sorts by both fields descending.
- `limit(20)` caps total returned documents.
- `batchSize(20)` hints how many documents to fetch per cursor batch; **it does not change the index strategy**.
- `MongoCursor` is closed cleanly via `try-with-resources`.

### 14.3. Checking Correct Results Is Not Checking Index Usage

A Java application can still receive accurate results via COLLSCAN, so "the program works" **does not prove the index is effective**. To investigate performance, run `explain` from the MongoDB Shell or the driver's explain API using the exact filter and sort sent by the application.

Also pay attention to **BSON types**. If `total` is stored as `Decimal128` in the collection while the Java filter passes an integer `100`, numeric comparison semantics and index behavior must be verified for the actual types stored. For monetary values, use consistent numeric types across schema, driver, and indexes.

## 15. Workload-Driven Index Selection Workflow

A practical workflow to follow:

### Step 1 — Document Real Queries

Do not start from a list of collection fields. Catalog:

- Actual equality and range filters.
- Sorts and sort directions.
- Limits / page sizes.
- Query frequency, SLAs, and tenant characteristics.
- Projections (which fields are returned).
- Insert/update/delete rates and which fields mutate frequently.

Example:

```javascript
find({ tenantId: ?, status: ?, total: { $gte: ? } })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
```

### Step 2 — Classify E, S, and R

| Role | Fields |
|---|---|
| E | `tenantId`, `status` |
| S | `createdAt`, `_id` |
| R | `total` |

Also verify whether conditions are single equalities or `$in` sets, whether collation is required, and whether any field is an array.

### Step 3 — Propose a Minimal Candidate Set

Start with ESR:

```javascript
{ tenantId: 1, status: 1, createdAt: -1, _id: -1, total: 1 }
```

If the range is very selective, also propose ERS for comparison:

```javascript
{ tenantId: 1, status: 1, total: 1, createdAt: -1, _id: -1 }
```

Also evaluate whether a shorter index suffices—for example, `{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }` if post-filtering `total` still meets the SLA.

### Step 4 — Inspect Explain and Measure Under Representative Conditions

Compare:

- Was the candidate index actually selected?
- Is there a separate `SORT` stage?
- What are `totalKeysExamined` and `totalDocsExamined`?
- Are many documents fetched and then discarded?
- What is the first-page / total latency observed by the application?
- Do sort memory or network payload sizes become bottlenecks?
- Does the new index measurably degrade write throughput?

### Step 5 — Weigh Index Costs

If a new index shaves a rare endpoint from 20 ms to 15 ms while inflating storage and write costs across millions of inserts, it is probably not worth keeping. If it cuts an endpoint hit thousands of times per second from 300 ms to 30 ms, a dedicated index is highly valuable.

These numbers merely illustrate the trade-off; gather real measurements before deciding.

### Step 6 — Monitor and Revisit

Distributions of `status`, `tenantId`, and `total` evolve over time. An index that once worked well can degrade as one tenant grows huge or business filters shift. Track slow queries, latency, index usage, write load, and storage size, adjusting via controlled deployment and rollback procedures.

## 16. Common Pitfalls

| Claim or symptom | Issue | Remedy |
|---|---|---|
| "Just index every field used in filters" | Too many indexes inflate write/storage costs | Design from query patterns |
| "Field order in a compound index does not matter" | Breaks prefix matching and index sorting | Analyze E/S/R and key order |
| "Equality fields must always be ordered by descending selectivity" | Ignores other prefix queries and sorts | Evaluate the overall workload |
| "Ranges must always go at the end of an index" | Ultra-selective ranges may favor ERS | Compare ESR vs. ERS with `explain` |
| "An index containing all fields always avoids SORT" | A range before sort breaks global sort order | Check compound key order and `explain` |
| "createIndex succeeding proves the query is fast" | Planner may pick another index or COLLSCAN | Verify with `explain` and benchmarks |
| "A SORT stage is always bad" | Sorting a tiny post-range set can be cheap | Check keys/docs examined and timing |
| "limit(20) only reads 20 documents" | Sorting/filtering may examine huge key/doc counts | Use an aligned index and check `executionStats` |
| "More compound indexes are always better" | Storage, RAM, and write costs climb | Consolidate patterns; prune verified redundancies |
| "The default `_id` index makes every query covered" | Secondary indexes do not automatically hold projected fields | Verify coverage and `totalDocsExamined` |
| "A compound index serves any subset of its fields equally" | Prefixes are not the same as middle/suffix subsets | Check equality constraints before sort keys |
| "An index optimizes all regex queries" | Unanchored regexes or mismatched collations lose index support | Match query syntax and index design |
| "Use `hint` to lock in the best index forever" | Data and workloads shift over time | Use `hint` only with evidence and monitoring |

## 17. Comprehensive Practice Exercises

These exercises use the `esr_index_lab.orders` collection from Section 9. Do not modify data outside the practice database.

### Exercise A — Identifying E/S/R

Given the query:

```javascript
orders.find({
  tenantId: "shop-a",
  status: "PAID",
  total: { $lt: 300 }
})
.sort({ createdAt: -1, _id: -1 })
.limit(5);
```

Identify:

1. Which fields are equality?
2. Which fields are sort?
3. Which field is range?
4. Propose one ESR index and one ERS index.
5. Why can both indexes yield identical results while differing in execution cost?

### Exercise B — Using Index Prefixes

Suppose the index is:

```javascript
{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }
```

Evaluate how well each query leverages prefixes or sort order:

```javascript
// Q1
orders.find({ tenantId: "shop-a" });

// Q2
orders.find({ tenantId: "shop-a", status: "PAID" })
  .sort({ createdAt: -1, _id: -1 });

// Q3
orders.find({ status: "PAID" })
  .sort({ createdAt: -1, _id: -1 });

// Q4
orders.find({ tenantId: "shop-a" })
  .sort({ createdAt: -1, _id: -1 });
```

Hint: Q2 pins both fields before the sort; Q4 spans multiple `status` groups, so it lacks a global `createdAt` order from this index alone.

### Exercise C — Comparing ESR and ERS with explain

Run:

```javascript
const queryFilter = {
  tenantId: "shop-a",
  status: "PAID",
  total: { $gte: 100 }
};

const querySort = { createdAt: -1, _id: -1 };

const planESR = orders.find(queryFilter)
  .sort(querySort)
  .limit(3)
  .hint("idx_esr")
  .explain("executionStats");

const planERS = orders.find(queryFilter)
  .sort(querySort)
  .limit(3)
  .hint("idx_ers")
  .explain("executionStats");

printjson(planESR);
printjson(planERS);
```

Compare `indexName`, `indexBounds`, presence of `SORT`, keys examined, docs examined, and `nReturned`. On a tiny dataset, **never draw production performance conclusions from a few milliseconds of runtime**.

### Exercise D — Changing the Range Predicate and Predicting Impact

Compare two filters:

```javascript
{ tenantId: "shop-a", status: "PAID", total: { $gte: 50 } }

{ tenantId: "shop-a", status: "PAID", total: { $gte: 600 } }
```

The second filter matches fewer documents in the lab dataset. Predict why the ERS index can become more advantageous when a range grows very selective, while grounding conclusions in `explain` and real queries.

### Exercise E — Estimating Index Cost for an Application

A hypothetical system writes 10,000 orders per minute and maintains 6 compound indexes. Discuss:

- Which indexes must be maintained on inserts and updates?
- If a seventh index is added solely for a once-a-day report, is the cost justified?
- If the new index drastically reduces response time for a mission-critical API, does the decision change?
- How should you measure index usage, storage, and write throughput before keeping or dropping an index?

This exercise focuses on **trade-off reasoning**; exact CPU/RAM figures cannot be derived purely from document counts and index counts.

## 18. Official Documentation

- [MongoDB Manual – The ESR (Equality, Sort, Range) Guideline](https://www.mongodb.com/docs/manual/tutorial/equality-sort-range-guideline/)
- [MongoDB Manual – Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/)
- [MongoDB Manual – Compound Index Prefixes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/index-prefix/)
- [MongoDB Manual – Use Indexes to Sort Query Results](https://www.mongodb.com/docs/manual/tutorial/sort-results-with-indexes/)
- [MongoDB Manual – Query Plans](https://www.mongodb.com/docs/manual/core/query-plans/)
- [MongoDB Manual – Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual – Covered Queries](https://www.mongodb.com/docs/manual/core/query-optimization/)
- [MongoDB Manual – Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/)
- [MongoDB Manual – Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/)
- [MongoDB Manual – Indexes and Query Performance](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB Java Sync Driver – Work with Indexes](https://www.mongodb.com/docs/drivers/java/sync/current/indexes/)

**Key takeaway:** Equality narrows the index slice, Sort returns results in pre-ordered sequence, and Range bounds the key span. **ESR is usually the best starting point when a query both filters and sorts; ERS is worth testing when the range is highly selective.** Final decisions must rely on `explain`, real data and query volumes, and index maintenance costs.
