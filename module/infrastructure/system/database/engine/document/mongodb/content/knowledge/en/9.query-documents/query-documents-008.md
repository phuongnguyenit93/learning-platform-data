# Multi-Field Sorting and Deterministic Ordering for Tie Values in MongoDB

## Lesson Objectives

In MongoDB, a query can sort documents by multiple fields, each with its own ascending or descending direction. When multiple documents share the same value in a sort field, **the relative order among them is not automatically guaranteed** unless a tie-breaker key is present to uniquely identify each document.

For example, when displaying the newest orders, two orders can share the exact same `createdAt` timestamp down to the millisecond. A query using only `sort({ createdAt: -1 })` can return those two orders in different orders across runs. The issue becomes prominent during pagination: a user might see the same order appear on two pages, or miss it entirely under certain data conditions.

This lesson explains how to design a **deterministic total order** over a result set, how to choose a matching **compound index**, and how to integrate that ordering into pagination.

After this lesson, you will be able to:

- Use `sort()` with multiple fields and directions `1` (ascending) and `-1` (descending).
- Explain how MongoDB compares fields in priority order within a sort specification.
- Identify tie-key scenarios and use `_id` or another unique key as a tie-breaker.
- Combine `find()`, `sort()`, `limit()`, `skip()`, and aggregation `$sort`.
- Design compound indexes serving both filters and sorts; read plans via `explain("executionStats")`.
- Build **keyset/cursor pagination** with deterministic ordering, including mixed ascending and descending directions.
- Distinguish **deterministic ordering** from **cross-query data consistency** when inserts, updates, or deletes occur.
- Handle special cases such as null, missing fields, mixed BSON types, string collation, and arrays.

> **Core rule:** If a list can be paginated, it needs a total order. Example: `sort({ createdAt: -1, _id: -1 })`. `createdAt` expresses business meaning; `_id` serves as the final tie-breaker when timestamps collide.

---

## 1. Why Single-Field Sorting May Not Be Enough

Suppose an `orders` collection contains these orders:

| `_id` | `customerId` | `priority` | `createdAt` | `status` |
|---|---|---:|---|---|
| `O-001` | `C-01` | 2 | 2026-11-10 09:00:00Z | PAID |
| `O-002` | `C-01` | 2 | 2026-11-10 09:00:00Z | PAID |
| `O-003` | `C-01` | 3 | 2026-11-11 08:00:00Z | NEW |
| `O-004` | `C-01` | 3 | 2026-11-11 08:00:00Z | NEW |
| `O-005` | `C-01` | 1 | 2026-11-12 09:00:00Z | PAID |
| `O-006` | `C-01` | 2 | 2026-11-12 11:00:00Z | NEW |
| `O-007` | `C-01` | 1 | 2026-11-09 14:00:00Z | CANCELED |
| `O-008` | `C-01` | 2 | 2026-11-13 10:00:00Z | PAID |

If you query:

~~~javascript
db.orders.find(
  { customerId: "C-01" }
).sort({
  priority: -1
});
~~~

MongoDB places documents with higher `priority` first, but `O-003` and `O-004` share priority 3. No additional rule specifies which order comes first.

Even when adding a timestamp:

~~~javascript
db.orders.find(
  { customerId: "C-01" }
).sort({
  priority: -1,
  createdAt: -1
});
~~~

`O-003` and `O-004` are still equal on both fields. Adding a unique key:

~~~javascript
db.orders.find(
  { customerId: "C-01" }
).sort({
  priority: -1,
  createdAt: -1,
  _id: 1
});
~~~

Now `O-003` comes before `O-004` because they have the same `priority` and `createdAt`, and `"O-003" < "O-004"`.

**Note:** MongoDB may coincidentally return documents with tied keys in the same order across repeated runs, but that order **is not guaranteed** when sort fields cannot distinguish them. Changing an index, query plan, topology, or dataset can alter the returned order.

### 1.1. What Does "Stable" Mean in This Lesson?

Distinguish two concepts:

1. **Deterministic order:** Given the same set of documents and sort key values, each document's position is uniquely determined by the sort key list, independent of internal storage-engine ordering.
2. **Consistent snapshot:** Whether multiple queries issued at different times observe the exact same dataset state.

Adding `_id` to the sort solves the first problem. It **does not lock a data snapshot**: if a new order is inserted or an order changes `priority` between two page requests, the result set and document positions can still shift.

---

## 2. Multi-Field Sort Syntax

In **mongosh**:

~~~javascript
db.orders.find(filter).sort({
  firstField: 1,
  secondField: -1,
  thirdField: 1
});
~~~

Meaning:

- Value `1`: sort **ascending**.
- Value `-1`: sort **descending**.
- **Field declaration order in the sort object matters**: MongoDB evaluates the first field first, moves to the second field only when values of the first field are equal, and continues likewise.

Example:

~~~javascript
db.orders.find(
  { customerId: "C-01" }
).sort({
  status: 1,
  priority: -1,
  createdAt: -1,
  _id: 1
});
~~~

MongoDB applies priority order:

1. `status` ascending.
2. Within groups sharing the same `status`, `priority` descending.
3. Within groups sharing `status` and `priority`, `createdAt` descending.
4. If all three leading fields match, `_id` ascending breaks ties.

This is **lexicographic ordering** over key tuples. MongoDB does not compute a composite score or alternate between fields.

### 2.1. The First Key Has Highest Priority

Compare:

~~~javascript
// A: Prioritize status first, timestamp second
db.orders.find().sort({
  status: 1,
  createdAt: -1,
  _id: -1
});

// B: Prioritize timestamp first, status second
db.orders.find().sort({
  createdAt: -1,
  status: 1,
  _id: -1
});
~~~

Both queries share **the exact same set of fields** yet produce **different orderings**, because the field order in the sort specification differs.

Query A groups documents by status first. Query B puts all newer orders first, using status only to break ties when timestamps match.

### 2.2. Ascending and Descending Directions Can Be Mixed

Example: "highest priority first; within the same priority, oldest orders first; if tied on both, ID ascending":

~~~javascript
db.orders.find().sort({
  priority: -1,
  createdAt: 1,
  _id: 1
});
~~~

There is no rule requiring all fields to share the same direction. However, **compound index sort directions** must still be compatible if you want to avoid an extra in-memory sort stage.

### 2.3. `sort()` Does Not Change Physical Storage Order

`sort()` specifies the **result return order**. It does not reorder documents inside the collection.

Never rely on "natural order", insertion order, disk order, or implicit `_id` order when `sort()` is omitted. None of those form an API return-order contract.

---

## 3. Creating Practice Data

The following examples use mongosh in the **`sort_lab`** database. They create test data; do not run them on production collections.

~~~javascript
use sort_lab

db.orders.insertMany([
  {
    _id: "O-001",
    customerId: "C-01",
    priority: 2,
    createdAt: ISODate("2026-11-10T09:00:00Z"),
    status: "PAID"
  },
  {
    _id: "O-002",
    customerId: "C-01",
    priority: 2,
    createdAt: ISODate("2026-11-10T09:00:00Z"),
    status: "PAID"
  },
  {
    _id: "O-003",
    customerId: "C-01",
    priority: 3,
    createdAt: ISODate("2026-11-11T08:00:00Z"),
    status: "NEW"
  },
  {
    _id: "O-004",
    customerId: "C-01",
    priority: 3,
    createdAt: ISODate("2026-11-11T08:00:00Z"),
    status: "NEW"
  },
  {
    _id: "O-005",
    customerId: "C-01",
    priority: 1,
    createdAt: ISODate("2026-11-12T09:00:00Z"),
    status: "PAID"
  },
  {
    _id: "O-006",
    customerId: "C-01",
    priority: 2,
    createdAt: ISODate("2026-11-12T11:00:00Z"),
    status: "NEW"
  },
  {
    _id: "O-007",
    customerId: "C-01",
    priority: 1,
    createdAt: ISODate("2026-11-09T14:00:00Z"),
    status: "CANCELED"
  },
  {
    _id: "O-008",
    customerId: "C-01",
    priority: 2,
    createdAt: ISODate("2026-11-13T10:00:00Z"),
    status: "PAID"
  },
  {
    _id: "O-009",
    customerId: "C-02",
    priority: 2,
    createdAt: ISODate("2026-11-13T10:00:00Z"),
    status: "NEW"
  }
]);
~~~

Verify:

~~~javascript
db.orders.countDocuments({});
~~~

The expected count for the newly created dataset is 9 documents. Examples filtering by customer `C-01` operate on 8 documents.

### 3.1. Sorting Only by `priority`

~~~javascript
db.orders.find(
  { customerId: "C-01" },
  { _id: 1, priority: 1, createdAt: 1 }
).sort({
  priority: -1
});
~~~

Documents with priority 3 appear before priority 2, followed by priority 1. Ordering **within each group** is not guaranteed because `priority` has ties.

### 3.2. Three-Field Sort Establishing Total Order

~~~javascript
db.orders.find(
  { customerId: "C-01" },
  { _id: 1, priority: 1, createdAt: 1 }
).sort({
  priority: -1,
  createdAt: -1,
  _id: 1
});
~~~

On the dataset above, the `_id` output order is:

~~~text
O-003
O-004
O-008
O-006
O-001
O-002
O-005
O-007
~~~

Explanation:

- `O-003` and `O-004` share priority 3 and the same timestamp; `_id` ascending places `O-003` first.
- Priority 2 orders sort newest first: `O-008`, `O-006`, then the two tied-timestamp orders `O-001`/`O-002`.
- Priority 1 places `O-005` before `O-007` because it is newer.

This is a **deterministic order** as long as sort key values and the document set remain unchanged.

### 3.3. Reversing the Final Key Direction

~~~javascript
db.orders.find(
  { customerId: "C-01" }
).sort({
  priority: -1,
  createdAt: -1,
  _id: -1
});
~~~

When priority and timestamp tie, `_id` descending puts `O-004` before `O-003`, and `O-002` before `O-001`. Other groups preserve their ordering determined by the first two keys.

---

## 4. Why Is `_id` Usually a Good Tie-Breaker?

Every document in a standard collection has an `_id` field; MongoDB enforces `_id` uniqueness under the applicable deployment constraints. Within a query on a single collection with unique `_id`, appending it as the final sort key is generally sufficient to break ties on earlier fields.

Standard pattern for newest-first display:

~~~javascript
db.orders.find(
  { customerId: "C-01" }
).sort({
  createdAt: -1,
  _id: -1
});
~~~

Strengths:

- No extra sequence column is needed solely for ordering.
- A tie-breaker key already exists in virtually every collection.
- Can be included directly in a compound index.
- Can serve as a cursor component for keyset pagination.

However, understand the limitations:

1. **`_id` is an identifier key, not a business clock.** ObjectId contains a timestamp component, but you should not replace `createdAt` by assuming "ObjectId increases strictly with creation time" in distributed systems.
2. **The type of `_id` must be consistent.** Mixing strings, numbers, and ObjectIds causes MongoDB to apply BSON type comparison rules. Ordering remains deterministic, yet confusing from a business perspective.
3. **The tie-breaker key must uniquely distinguish output rows.** In an aggregation or join, if the output duplicates a single `_id` across multiple result rows, `_id` alone is insufficient; you need a key unique per result row.
4. **Uniqueness scope must match deployment topology.** In sharded collections, `_id` uniqueness guarantees and shard-key usage carry specific rules; the system must ensure uniqueness across the entire queried dataset.
5. **Do not treat `_id` as a monotonic sequence guarantee.** For UUIDs or arbitrary strings, sorting by `_id` simply orders by the key's value.

If the domain already has another unique key, such as `orderNo` backed by a reliable unique index, that key can serve as the tie-breaker instead of `_id`. Verify uniqueness and type consistency first.

### 4.1. Tie-Breakers Only Help After Business Fields

Example:

~~~javascript
db.orders.find().sort({
  _id: -1
});
~~~

This query establishes deterministic ordering by `_id`, but **does not necessarily reflect order creation time**. If the requirement is "newest orders", choose:

~~~javascript
db.orders.find().sort({
  createdAt: -1,
  _id: -1
});
~~~

`createdAt` conveys "newest"; `_id` only resolves timestamp ties.

### 4.2. Alternative Tie-Breaking Keys

| Final key | When suitable | Requirement |
|---|---|---|
| `_id` | Standard document lists | Unique within the paginated result set |
| `orderNo` | Order lists with business codes | Unique index / domain uniqueness guarantee |
| `eventSequence` | Event streams with business ordering | Reliable sequence generator with clear consistency scope |
| Composite key `tenantId` + `orderNo` | Multi-tenant systems | Uniqueness enforced on the pair, not just `orderNo` alone |
| Aggregation output key | `$unwind`/`$group` producing derived rows | Fields that uniquely distinguish every output row |

Merely adding more fields does not automatically guarantee uniqueness. There must be a key or combination of keys that is **unique across the result set**.

---

## 5. Sorting in Aggregation Pipelines

In aggregation, use the `$sort` stage:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      customerId: "C-01"
    }
  },
  {
    $sort: {
      priority: -1,
      createdAt: -1,
      _id: 1
    }
  },
  {
    $project: {
      _id: 1,
      priority: 1,
      createdAt: 1,
      status: 1
    }
  },
  {
    $limit: 5
  }
]);
~~~

A tie-breaker is also needed in `$sort` if multiple documents share equal values. The `$sort` stage is **not a stable sort** in the sense of preserving input order among tied values. If a pipeline transforms documents before sorting, verify that the final key still distinguishes every result row.

### 5.1. Place `$match` Before `$sort` When Appropriate

~~~javascript
[
  { $match: { customerId: "C-01" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 20 }
]
~~~

Filtering before sorting reduces the data that must be sorted. With a suitable index, MongoDB can also retrieve documents already in index order.

However, pipeline optimization depends on surrounding stages; for example, placing `$project` or `$unwind` before `$sort` can affect index utilization. Use `explain` rather than assuming all pipelines optimize identically.

### 5.2. `$limit` After `$sort`

~~~javascript
db.orders.aggregate([
  { $match: { customerId: "C-01" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 20 }
]);
~~~

You must **sort before taking the first 20 documents** to obtain the requested top 20 results. If you limit first:

~~~javascript
// Different meaning: takes 20 documents first and only sorts those 20 documents.
db.orders.aggregate([
  { $match: { customerId: "C-01" } },
  { $limit: 20 },
  { $sort: { createdAt: -1, _id: -1 } }
]);
~~~

this does not guarantee returning the 20 newest orders across the collection.

Certain pipeline shapes allow MongoDB to coalesce `$sort` + `$limit`, but you should never alter the logical order of stages without understanding the semantics.

### 5.3. Sorting Results After `$group`

Example total orders by status:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      totalOrders: { $sum: 1 }
    }
  },
  {
    $sort: {
      totalOrders: -1,
      _id: 1
    }
  }
]);
~~~

If two statuses have the same `totalOrders`, the group's `_id` (here, the status value) acts as the tie-breaker. After `$group`, `_id` is no longer the source document's `_id`: it is the **grouping key**.

### 5.4. `$unwind` and Result Rows Sharing `_id`

Suppose an order has multiple items. After `$unwind`, each line item carries the same order `_id`:

~~~javascript
db.orders.aggregate([
  { $unwind: "$items" },
  {
    $sort: {
      createdAt: -1,
      _id: -1
    }
  }
]);
~~~

Across multiple items in the same order, both `createdAt` and `_id` are tied; item ordering is unresolved. To obtain deterministic ordering by array position, use `includeArrayIndex` and include that index in the sort:

~~~javascript
db.orders.aggregate([
  {
    $unwind: {
      path: "$items",
      includeArrayIndex: "itemIndex"
    }
  },
  {
    $sort: {
      createdAt: -1,
      _id: -1,
      itemIndex: 1
    }
  }
]);
~~~

This distinguishes elements within the same order by their array position at read time. If the array can be modified between page requests, ordering still reflects those data changes.

---

## 6. Compound Indexes for Multi-Field Sorting

### 6.1. Why Can Sorting Be Slow?

Without a supporting index, MongoDB may have to:

1. Read documents matching the filter.
2. Compute sort keys for each document.
3. Sort them in memory or spill to disk depending on version and configuration.
4. Return the limited slice of results.

On large collections, an unindexed sort consumes RAM, CPU, and disk I/O and increases latency. The sort step is visible in the query plan.

### 6.2. An Index Serving Both Filter and Sort

Common query:

~~~javascript
db.orders.find(
  { customerId: "C-01" }
).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
~~~

Candidate compound index:

~~~javascript
db.orders.createIndex(
  {
    customerId: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "idx_customer_created_id"
  }
);
~~~

Structure:

~~~text
customerId ASC  -> equality filter
createdAt DESC  -> primary sort requirement
_id DESC        -> tie-breaker
~~~

Once `customerId` is fixed by equality, matching index entries are already ordered by `createdAt DESC, _id DESC`. MongoDB can stream results in index order without a separate sort stage.

**Note:** The default `_id` index does not automatically mean every other compound index contains `_id` in the desired sort position. If a sort uses `_id` as a secondary key, explicitly include it in the compound index serving that query.

### 6.3. Field Order and Sort Direction Matter

Consider the index:

~~~javascript
db.orders.createIndex({
  customerId: 1,
  priority: -1,
  createdAt: -1,
  _id: 1
});
~~~

This index fits:

~~~javascript
db.orders.find(
  { customerId: "C-01" }
).sort({
  priority: -1,
  createdAt: -1,
  _id: 1
});
~~~

However, the query:

~~~javascript
db.orders.find(
  { customerId: "C-01" }
).sort({
  priority: -1,
  createdAt: 1,
  _id: 1
});
~~~

flips only the direction of `createdAt`. A single compound index does not support arbitrary combinations of ascending/descending directions. In general, an index supports the declared key order **or the exact inverse of all corresponding sort keys**, not flipping one field independently while keeping the others unchanged.

Therefore, measure the actual sort patterns used by your APIs. Do not create dozens of indexes speculatively for unused direction combinations.

### 6.4. Equality First, Sort Second

A practical guideline for compound index design is **Equality – Sort – Range (ESR)**: place equality-filtered fields first, then sort fields, followed by range fields where appropriate. This is a practical heuristic, not an immutable formula.

Example:

~~~javascript
db.orders.find({
  customerId: "C-01",
  status: "PAID"
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
~~~

Candidate index:

~~~javascript
db.orders.createIndex(
  {
    customerId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "idx_customer_status_recent"
  }
);
~~~

If a query omits the `status` filter, this index cannot serve the sort as effectively as an index without `status`, because `status` sits between `customerId` and the sort fields. Design indexes around **common query shapes**, not just the widest possible index.

### 6.5. Verify with `explain("executionStats")`

~~~javascript
const details = db.orders
  .find({ customerId: "C-01" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats");

printjson(details.queryPlanner.winningPlan);
printjson(details.executionStats);
~~~

Useful fields:

| Field | Meaning |
|---|---|
| `winningPlan` | Execution plan selected by MongoDB |
| `IXSCAN` or equivalent index scan stage | Index traversal |
| `COLLSCAN` | Collection scan |
| `SORT` or equivalent sort stage | Dedicated sort step consuming resources |
| `nReturned` | Number of documents returned |
| `totalKeysExamined` | Number of index keys inspected |
| `totalDocsExamined` | Number of documents inspected/fetched |
| `executionTimeMillis` | Execution time reported in explain |

Exact fields and stage names vary by MongoDB version and query engine. On a tiny dataset, the planner may pick `COLLSCAN` because it is cheaper than using an index; never conclude from a 9-document example that an index is unnecessary.

`explain` clarifies the execution plan, while production latency benchmarking also requires testing network, driver, cache, concurrency, and realistic large data distributions.

### 6.6. In-Memory Sort and Resource Limits

When ordering cannot be satisfied by an index, MongoDB must perform a sort. On large datasets, the sort operation can exceed memory limits; whether it spills to disk depends on MongoDB version and configuration, such as `allowDiskUse` or `allowDiskUseByDefault`.

In aggregation, you can pass:

~~~javascript
db.orders.aggregate(
  [
    { $match: { customerId: "C-01" } },
    { $sort: { createdAt: -1, _id: -1 } },
    { $limit: 20 }
  ],
  { allowDiskUse: true }
);
~~~

This is **not a substitute for an index** on critical read paths. Disk-based sorting can be slow and resource-intensive; inspect `winningPlan` and benchmark on sufficiently large data.

---

## 7. Pagination with `skip()` and `limit()`

### 7.1. Offset Pagination

A common pattern:

~~~javascript
const pageSize = 3;
const pageNumber = 2;

db.orders.find(
  { customerId: "C-01" }
).sort({
  createdAt: -1,
  _id: -1
}).skip(
  (pageNumber - 1) * pageSize
).limit(pageSize);
~~~

With `pageSize = 3` and `pageNumber = 2`, the query skips the first 3 documents and returns up to the next 3 documents.

**Important:** Use the exact same sort specification across every page, including the unique tie-breaker. Sorting only by `createdAt` lets tied-timestamp documents shift relative positions, causing duplicates or omissions across pages even when data has not changed.

### 7.2. Why Are Large Offsets Expensive?

To fetch page 10,000 with 20 results per page, the database still has to walk past a huge number of preceding results before returning the desired 20 documents. An index enables ordered scanning, but it does not eliminate the cost of a deep `skip`.

When datasets are large and users scroll continuously, **keyset pagination** usually outperforms deep offsets.

### 7.3. A Tie-Breaker Does Not Solve Concurrent Mutations Between Pages

Suppose a user fetches page 1, and then a new order is inserted with a newer timestamp than all others. Before fetching page 2 with `skip(3)`, the new order shifts positions downward. A document from page 1 can reappear on page 2.

This is **result-set drift from concurrent writes**, distinct from **non-deterministic ordering on tied keys**.

Adding `_id` fixes the tied-key problem. However, offset pagination can still duplicate or skip items when data changes between reads. If minimizing this issue is required, consider keyset pagination and an appropriate data-consistency policy.

---

## 8. Keyset/Cursor Pagination with Deterministic Ordering

### 8.1. Principle

With sort:

~~~javascript
{ createdAt: -1, _id: -1 }
~~~

The first page reads 3 documents:

~~~javascript
const pageSize = 3;

const firstPage = db.orders
  .find({ customerId: "C-01" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(pageSize)
  .toArray();

printjson(firstPage);
~~~

Grab the last document on the page:

~~~javascript
const last = firstPage[firstPage.length - 1];
~~~

The next page must fetch documents **coming after** `last` in the same ordering, meaning:

- `createdAt` is **less than** the last timestamp; or
- `createdAt` is **equal to** the last timestamp and `_id` is **less than** the last ID (since both directions are descending).

~~~javascript
const nextPage = db.orders.find({
  customerId: "C-01",
  $or: [
    {
      createdAt: { $lt: last.createdAt }
    },
    {
      createdAt: last.createdAt,
      _id: { $lt: last._id }
    }
  ]
}).sort({
  createdAt: -1,
  _id: -1
}).limit(pageSize).toArray();

printjson(nextPage);
~~~

No page-depth `skip` is needed. The query bounds results using cursor conditions based on the sort keys.

### 8.2. Formula for Two Descending Fields

With ordering:

~~~text
sort(A DESC, B DESC)
~~~

and end-of-page cursor `(a, b)`, the "after cursor" condition is:

~~~text
A < a
OR
(A = a AND B < b)
~~~

With both ascending:

~~~text
sort(A ASC, B ASC)
~~~

the condition is:

~~~text
A > a
OR
(A = a AND B > b)
~~~

With mixed directions, the comparison operator changes per field.

Example:

~~~text
sort(priority DESC, _id ASC)

After cursor (priority = p, _id = id):
  priority < p
  OR
  (priority = p AND _id > id)
~~~

**Do not use `$lt` for every field when the sort mixes directions.**

### 8.3. Three-Field Cursor Example

Sort:

~~~javascript
{
  priority: -1,
  createdAt: -1,
  _id: 1
}
~~~

Suppose the last document on the page has:

~~~javascript
{
  priority: 2,
  createdAt: ISODate("2026-11-10T09:00:00Z"),
  _id: "O-001"
}
~~~

The condition for fetching the next page is:

~~~javascript
const cursor = {
  priority: 2,
  createdAt: ISODate("2026-11-10T09:00:00Z"),
  _id: "O-001"
};

db.orders.find({
  customerId: "C-01",
  $or: [
    { priority: { $lt: cursor.priority } },
    {
      priority: cursor.priority,
      createdAt: { $lt: cursor.createdAt }
    },
    {
      priority: cursor.priority,
      createdAt: cursor.createdAt,
      _id: { $gt: cursor._id }
    }
  ]
}).sort({
  priority: -1,
  createdAt: -1,
  _id: 1
}).limit(3);
~~~

This is an extended lexicographic comparison: **the first field differing from the cursor determines position; all preceding fields must equal the cursor**.

### 8.4. Designing Safe Cursors in APIs

An application-level cursor typically needs to encode:

- Values of **all sort keys** from the last document on the page.
- Fixed filter parameters or a query-shape identifier to prevent applying a cursor to a different query.
- Sort direction and version metadata in case the API evolves.
- Accurate representations of BSON data types, such as BSON Date and ObjectId.

Never pass a string-formatted timestamp that truncates milliseconds and compare it against a BSON Date; doing so can skip or duplicate results. If the API uses opaque cursors, encode the fields in a versioned format and sign or integrity-check them per application design.

In the example using string `_id`, the cursor can also store a string. When `_id` is an ObjectId, decode the cursor back into a proper ObjectId; do not compare a hex string against an ObjectId as if they were the same BSON type.

### 8.5. Limitations When Data Mutates

Keyset pagination avoids deep-offset costs and generally eliminates positional drift when new documents are inserted at the top of the list. However, it **does not create a snapshot across multiple requests**:

- If an already-read document changes `createdAt` or `priority`, it may move into the unread region and appear again.
- If an unread document changes keys and moves ahead of the cursor, it may be skipped on subsequent pages.
- Deleted documents disappear.
- Newly inserted documents whose keys fall past the cursor can appear on later pages.

If the business requirement is "export the exact result set as of time T" across multiple pages and minutes, evaluate proper snapshot/consistency mechanisms, frozen ID-set strategies, or dedicated export pipelines. Tie-breakers and keysets solve **ordering**, not a snapshot consistency contract.

---

## 9. Cases That Make Sort Results Unpredictable

### 9.1. Missing Fields and `null` Values

Example:

~~~javascript
db.tasks.insertMany([
  { _id: "T-01", priority: 2, title: "Read docs" },
  { _id: "T-02", priority: null, title: "Verify data" },
  { _id: "T-03", title: "Write report" },
  { _id: "T-04", priority: 1, title: "Push release" }
]);
~~~

Query:

~~~javascript
db.tasks.find().sort({
  priority: 1,
  _id: 1
});
~~~

MongoDB uses **BSON comparison order**. In sorting, missing fields and `null` compare equivalently at the sort-key level, so `_id` breaks ties between them. That does not mean the application automatically distinguishes "unprioritized" from "lowest priority".

If business rules require "tasks without a priority must always appear last", **normalize the data** into an explicit value or sort field instead of accidentally relying on `null` ordering.

A read model might contain:

~~~javascript
{
  _id: "T-03",
  priority: null,
  priorityGroup: 1
}
~~~

and sort with:

~~~javascript
db.tasks.find().sort({
  priorityGroup: 1,
  priority: -1,
  _id: 1
});
~~~

If using `priorityGroup`, populate and maintain that field consistently across every document according to application rules.

### 9.2. Inconsistent BSON Types

A field stored sometimes as a string and sometimes as a number:

~~~javascript
{ _id: "A", score: 10 }
{ _id: "B", score: "9" }
{ _id: "C", score: 8 }
~~~

MongoDB does not convert everything to numbers for comparison; it applies BSON type ordering rules. Thus, do not expect the string `"9"` to appear between the numbers 8 and 10.

Recommendations:

- Store one consistent BSON type for any sorted field.
- Use schema validation where appropriate.
- Migrate legacy records with mismatched types.
- If sorting by converted values is required, handle conversion explicitly in aggregation or materialize a dedicated sort key.

### 9.3. String Sorting and Collation

By default, binary/simple string comparison does not match linguistic intuition for all users.

Example `users` collection:

~~~javascript
db.users.insertMany([
  { _id: "U-01", fullName: "An", score: 8 },
  { _id: "U-02", fullName: "an", score: 8 },
  { _id: "U-03", fullName: "Ánh", score: 8 },
  { _id: "U-04", fullName: "Bình", score: 9 }
]);
~~~

Query with collation:

~~~javascript
db.users.find().collation({
  locale: "vi",
  strength: 2
}).sort({
  fullName: 1,
  _id: 1
});
~~~

`locale: "vi"` selects Vietnamese locale rules; `strength: 2` generally distinguishes diacritics while ignoring case differences at that comparison level. Strings treated as equal under a given collation still need `_id` as a final key to establish deterministic order.

For performance, an index supporting string sorting must have a **compatible collation** with the query:

~~~javascript
db.users.createIndex(
  { fullName: 1, _id: 1 },
  {
    name: "idx_fullName_vi",
    collation: {
      locale: "vi",
      strength: 2
    }
  }
);
~~~

An index built with a different collation may not support string sorting as expected. Verify with `explain`.

### 9.4. Sorting on Arrays

When a field is an array, MongoDB chooses a representative element for sorting depending on sort direction and context. Example:

~~~javascript
db.students.insertMany([
  { _id: "S-01", scores: [6, 9] },
  { _id: "S-02", scores: [7, 8] }
]);
~~~

Sorting directly on `scores`:

~~~javascript
db.students.find().sort({
  scores: 1,
  _id: 1
});
~~~

is not equivalent to "sort by average score" or "by first element" in all situations. If business logic requires average or maximum score, compute an explicit sort field:

~~~javascript
db.students.aggregate([
  {
    $addFields: {
      averageScore: { $avg: "$scores" }
    }
  },
  {
    $sort: {
      averageScore: -1,
      _id: 1
    }
  }
]);
~~~

Queries sorting on a computed key must sort after computation and cannot easily use a direct index on `scores`. If read frequently, consider persisting `averageScore` as a derived field updated consistently.

### 9.5. Sorting by ObjectId Does Not Replace `createdAt`

ObjectId is designed as an identifier and contains a timestamp component, but ID values are not an exact business clock. They can be generated on clients, across multiple processes, or at different times, and their timestamp resolution is insufficient for all event-ordering requirements.

If the requirement is newest by order placement time:

~~~javascript
db.orders.find().sort({
  createdAt: -1,
  _id: -1
});
~~~

Do not default to:

~~~javascript
db.orders.find().sort({
  _id: -1
});
~~~

and claim it represents exact chronological order for all records.

### 9.6. Sort Keys Changing While Users Paginate

If a list is sorted by `priority`, and users or background jobs modify priority in real time, document positions shift too. Cursors do not pin documents to old positions after updates.

For live-updating task lists, define the intended behavior:

- Allow the list to shift and reflect fresh data.
- Anchor queries to a fixed time cutoff or version.
- Show a "list updated" banner and let the user refresh.
- Run exports against a controlled snapshot if strict point-in-time accuracy is required.

---

## 10. Deterministic Sorting with Multiple Filters and Sort Keys

### 10.1. Filtering Does Not Imply Sorting

Query:

~~~javascript
db.orders.find({
  customerId: "C-01",
  status: { $in: ["NEW", "PAID"] }
}).sort({
  priority: -1,
  createdAt: -1,
  _id: 1
});
~~~

MongoDB filters documents first before determining return order. The `status` field in the filter does not affect ordering unless explicitly included in `sort`.

If business logic wants `NEW` prioritized before `PAID`, you cannot infer that from element order in `$in`. You must add an explicit domain rank field (such as `statusRank`) or a computed expression.

### 10.2. Sorting by a Custom Business Order

Suppose the desired status order is:

~~~text
NEW -> PAID -> CANCELED
~~~

Alphabetical sorting on `status` does not produce that order. One solution is storing `statusRank`:

~~~javascript
{
  _id: "O-101",
  status: "NEW",
  statusRank: 1,
  createdAt: new Date()
}
~~~

Query:

~~~javascript
db.orders.find().sort({
  statusRank: 1,
  createdAt: -1,
  _id: -1
});
~~~

Whenever status changes, `statusRank` must be updated consistently. If you prefer not to persist a derived field, compute it with `$switch` in aggregation:

~~~javascript
db.orders.aggregate([
  {
    $addFields: {
      statusRank: {
        $switch: {
          branches: [
            {
              case: { $eq: ["$status", "NEW"] },
              then: 1
            },
            {
              case: { $eq: ["$status", "PAID"] },
              then: 2
            },
            {
              case: { $eq: ["$status", "CANCELED"] },
              then: 3
            }
          ],
          default: 99
        }
      }
    }
  },
  {
    $sort: {
      statusRank: 1,
      createdAt: -1,
      _id: -1
    }
  }
]);
~~~

Trade-off: sorting on a computed field in a pipeline cannot leverage an index on an unpersisted `statusRank`. If the API is high-traffic and the collection is large, materializing the rank with an index is worth considering.

### 10.3. Top N Per Group Differs from Global Sort

Another requirement is "3 newest orders per customer". Simply running:

~~~javascript
db.orders.find().sort({
  createdAt: -1,
  _id: -1
}).limit(3);
~~~

returns the **3 newest orders across the entire collection**, not 3 orders per customer.

Getting Top N per group requires an aggregation pipeline or another technique (such as window functions or `$group` with appropriate operators depending on MongoDB version). Within each group, a tie-breaker is still needed when business ordering keys tie.

---

## 11. Java and Spring Data MongoDB: Keeping Sort Order Consistent

### 11.1. Java Sync Driver

The MongoDB Java Driver provides helpers in `com.mongodb.client.model.Sorts`:

~~~java
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Sorts.descending;
import static com.mongodb.client.model.Sorts.orderBy;

import org.bson.Document;
import com.mongodb.client.MongoCollection;

MongoCollection<Document> orders = database.getCollection("orders");

orders.find(eq("customerId", "C-01"))
      .sort(orderBy(
          descending("createdAt"),
          descending("_id")
      ))
      .limit(20)
      .forEach(System.out::println);
~~~

This is a query snippet; the `database` variable must come from a connected `MongoClient`. If an API lists orders oldest-first, invert the directions accordingly:

~~~java
import static com.mongodb.client.model.Sorts.ascending;

orders.find(eq("customerId", "C-01"))
      .sort(orderBy(
          ascending("createdAt"),
          ascending("_id")
      ))
      .limit(20);
~~~

**Keep one consistent rule:** the sort passed to the driver must have the exact same fields and directions as cursor pagination. Never generate a cursor under one sort order and query the next page under another.

### 11.2. Spring Data MongoDB

You can construct a `Sort`:

~~~java
import org.springframework.data.domain.Sort;

Sort stableSort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("_id")
);
~~~

With `MongoTemplate`:

~~~java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = new Query(
    Criteria.where("customerId").is("C-01")
);

query.with(stableSort);
query.limit(20);

var orders = mongoTemplate.find(
    query,
    OrderDocument.class,
    "orders"
);
~~~

In projects mapping Java properties to MongoDB fields, verify exact stored field names. `_id` may map to a Java property annotated with `@Id`; verify the mapping rather than assuming every property shares the same name in BSON.

### 11.3. APIs Should Define Sort as Part of the Contract

Example endpoint:

~~~text
GET /customers/C-01/orders?limit=20&sort=recent
~~~

You can define:

~~~text
sort=recent:
  createdAt DESC, _id DESC

sort=oldest:
  createdAt ASC, _id ASC

sort=priority:
  priority DESC, createdAt DESC, _id ASC
~~~

Do not let clients pass arbitrary combinations of fields and directions straight into the database without validation. Unbounded sort shapes make index optimization hard, can trigger expensive in-memory/disk sorts, and complicate cursor encoding.

APIs should expose a bounded set of meaningful sort modes, tested and backed by appropriate indexes.

---

## 12. Common Pitfalls

### Pitfall 1 — Sorting Only by Timestamp

~~~javascript
db.orders.find().sort({ createdAt: -1 });
~~~

**Problem:** Multiple orders share the same timestamp, leaving their relative order unguaranteed.

**Solution:**

~~~javascript
db.orders.find().sort({
  createdAt: -1,
  _id: -1
});
~~~

### Pitfall 2 — Assuming a Sort Is Deterministic Because Test Runs Look Identical

In a small database with a static query plan, results may happen to come back in the same order across runs. That does not make it a MongoDB guarantee when sort keys tie.

**Solution:** Add a unique tie-breaker key and write tests with intentionally tied timestamps and priorities.

### Pitfall 3 — Using `skip` Without a Sort

~~~javascript
db.orders.find().skip(20).limit(20);
~~~

**Problem:** No order is specified, so pages follow no stable rule.

**Solution:** Always specify a complete sort for paginated APIs.

### Pitfall 4 — Using Very Deep `skip` Assuming an Index Fixes Everything

Even with an index, skipping hundreds of thousands of entries carries significant overhead.

**Solution:** Use keyset/cursor pagination for sequential page-by-page navigation.

### Pitfall 5 — Using a Timestamp-Only Cursor

~~~javascript
// Insufficient when multiple documents share the same createdAt
db.orders.find({
  createdAt: { $lt: lastCreatedAt }
}).sort({
  createdAt: -1
});
~~~

**Problem:** Remaining documents sharing the same timestamp as the last item on the page are skipped.

**Solution:** Include both `createdAt` and the `_id` tie-breaker in the cursor, and add the equality branch.

### Pitfall 6 — Wrong Comparison Operator for Sort Direction

With sort `{ priority: -1, _id: 1 }`, the next-page condition is not `priority < p OR _id < id`. When priorities tie, `_id` must be **greater than** the cursor because `_id` is sorted ascending.

**Solution:** Write the "after cursor" condition following lexicographic comparison and each key's direction.

### Pitfall 7 — Assuming `_id` Always Reflects Exact Chronological Order

**Problem:** `_id` can be a string or UUID, and even ObjectId is not an absolute business clock.

**Solution:** Use the domain timestamp as primary key and `_id` as tie-breaker.

### Pitfall 8 — Wrong Field Order in a Compound Index

A query filters on `customerId`, yet the index puts sort keys first or inserts an unqueried field between `customerId` and the sort keys, altering index usability.

**Solution:** Analyze query shapes and measure with `explain`, following Equality–Sort–Range where appropriate.

### Pitfall 9 — Using an Incompatible Collation with an Index

A string index using simple collation cannot efficiently serve a sort using another locale collation.

**Solution:** Verify query and index collations match, and inspect the query plan.

### Pitfall 10 — Confusing Deterministic Ordering with an Immutable Snapshot

**Problem:** Even with `_id` as tie-breaker, documents can still be inserted, deleted, or updated between two requests.

**Solution:** Distinguish product consistency requirements from sorting requirements. For strict point-in-time exports, choose an appropriate snapshot or frozen-result mechanism.

---

## 13. Design Workflow for a List API

### Step 1 — Define the Meaning of Ordering

For example: "Most recent orders" means `createdAt DESC`; on ties, `_id DESC`.

### Step 2 — Define the Filter Set

For example, viewing orders for one customer and status:

~~~javascript
{
  customerId: "C-01",
  status: "PAID"
}
~~~

### Step 3 — Choose a Tie-Breaker

Choose `_id` if unique within the result set. For aggregations emitting multiple rows per source document, choose another unique key combination if needed.

### Step 4 — Design Indexes Around Common Queries

Example:

~~~javascript
db.orders.createIndex(
  {
    customerId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "idx_customer_status_recent"
  }
);
~~~

### Step 5 — Choose a Pagination Strategy

- Small lists, limited page counts, infrequently changing data: `skip/limit` may suffice.
- Large lists, continuous scrolling: keyset/cursor pagination.
- Exact dataset as of a fixed timestamp: dedicated consistency/export design, not cursors alone.

### Step 6 — Verify

~~~javascript
db.orders
  .find({
    customerId: "C-01",
    status: "PAID"
  })
  .sort({
    createdAt: -1,
    _id: -1
  })
  .limit(20)
  .explain("executionStats");
~~~

Evaluate the plan, keys/documents examined, latency, and query scaling as data grows.

### Step 7 — Test Edge Cases That Break Assumptions

- Two documents with identical timestamps.
- Multiple documents sharing identical status, priority, and timestamp.
- Page boundaries landing right in the middle of a tied-timestamp group.
- Missing or null sort fields.
- Multiple BSON types in `_id` (if the current schema allows it).
- Inserts, updates, and deletes occurring between two requests.
- Next page after cursor for ascending, descending, and mixed-direction sorts.
- Filter or collation changes between requests.

These cases validate real API contracts far better than a dataset where every timestamp is unique.

---

## 14. Practice Exercises

### Exercise 1 — Three-Field Sort

Use the `orders` collection created in Section 3. Write a query that:

1. Sorts `priority` descending.
2. On equal priority, sorts `createdAt` descending.
3. On ties in both, sorts `_id` ascending.
4. Returns only orders for `C-01` projecting `_id`, `priority`, and `createdAt`.

Check the order of `O-003`, `O-004`, `O-001`, `O-002` and explain why the final key determines their positions.

### Exercise 2 — Changing Field Order

Compare:

~~~javascript
db.orders.find().sort({
  status: 1,
  createdAt: -1,
  _id: -1
});

db.orders.find().sort({
  createdAt: -1,
  status: 1,
  _id: -1
});
~~~

Explain how each query prioritizes its first field; give an example of two documents that swap positions between the two outputs.

### Exercise 3 — Creating a Suitable Index

Given the query:

~~~javascript
db.orders.find({
  customerId: "C-01",
  status: "PAID"
}).sort({
  createdAt: -1,
  _id: -1
}).limit(10);
~~~

Do the following:

1. Propose a compound index.
2. Explain the equality role of `customerId` and `status`.
3. Run `explain` before and after creating the index on a sufficiently large dataset.
4. Check whether a separate resource-consuming sort stage remains.
5. Discuss why an index serving this query is not automatically optimal for a query that omits the `status` filter.

### Exercise 4 — Cursor with Tied Timestamps

Suppose sort is `{ createdAt: -1, _id: -1 }` and page 1 ends at:

~~~javascript
{
  createdAt: ISODate("2026-11-10T09:00:00Z"),
  _id: "O-002"
}
~~~

Write the filter for the next page so other documents with the same timestamp and `_id` smaller than `"O-002"` are not skipped.

### Exercise 5 — Mixed-Direction Cursor

Sort:

~~~javascript
{ priority: -1, createdAt: 1, _id: 1 }
~~~

Cursor:

~~~javascript
{
  priority: 2,
  createdAt: ISODate("2026-11-10T09:00:00Z"),
  _id: "O-001"
}
~~~

Write the `$or` condition for the next page in lexicographic order, and explain why `priority` uses `$lt` while `createdAt` and `_id` use `$gt` in their respective branches.

### Exercise 6 — Missing Data and Collation

Create a `students` collection where some documents lack `lastName`, some have `lastName: null`, and some strings differ only in case. Sort by `lastName ASC, _id ASC` using simple collation and `locale: "vi", strength: 2`. Record the results and explain why normalizing fields and declaring the right collation matters.

### Exercise 7 — Data Changing During Pagination

Simulate:

1. Fetch page 1 ordered by `createdAt DESC, _id DESC`, page size 3.
2. Insert a new document at the top of the list.
3. Fetch page 2 using `skip(3)`.
4. Fetch page 2 using the keyset cursor from page 1.
5. Compare scenarios that can cause duplicates or omissions.
6. Try another update changing `createdAt` on an already-read document, and discuss keyset limitations.

Run this only on a lab database because the exercise involves write operations.

---

## 15. Review Questions

1. In `sort({ a: 1, b: -1 })`, which field does MongoDB prioritize?
2. When does field `b` affect result placement?
3. Why is `sort({ createdAt: -1 })` insufficient for deterministic pagination?
4. What property must a tie-breaker key satisfy?
5. Why is `_id` commonly chosen, and when might `_id` be insufficient?
6. Is sorting by `_id` always equivalent to sorting by creation time?
7. How must a compound index align with filters and sorts?
8. Why can flipping a single field's direction prevent an index from serving a sort efficiently?
9. What do `totalKeysExamined` and `totalDocsExamined` measure?
10. Why does `$sort` after `$limit` differ from `$sort` before `$limit`?
11. What limitations does offset pagination have when data changes?
12. What condition does keyset pagination use for sorting two descending fields?
13. With a mixed-direction sort, how do cursor comparison operators change?
14. How do null, missing fields, and inconsistent BSON types affect sorting?
15. How does index collation relate to Vietnamese string sorting?
16. Why can `$unwind` cause the source document's `_id` to no longer uniquely identify output rows?
17. How do deterministic ordering and snapshot consistency differ?

## 16. Summary

Multi-field sorting in MongoDB **compares keys sequentially in their declared order**. The first field has the highest priority, and subsequent fields are evaluated only when preceding fields tie. When a result set can contain multiple documents sharing business sort keys, add a **unique tie-breaker**—typically `_id`—to establish deterministic ordering.

In real-world applications:

- **Define a meaningful business sort:** e.g., `createdAt DESC`.
- **Complete it with a tie-breaker key:** e.g., `_id DESC`.
- **Design matching indexes:** accounting for equality filters, key order, and sort directions.
- **Paginate consistently with the sort:** offset for simple needs, keyset/cursor for large datasets.
- **Distinguish ordering from consistency:** a unique key alone does not freeze the result set against concurrent writes.
- **Test with tied keys:** inspect query plans, latency, and pagination behavior.

Good design ensures users see results in the right order, pagination APIs stay consistent, and the database executes queries efficiently at scale.

## Official MongoDB References

- [MongoDB Manual — cursor.sort()](https://www.mongodb.com/docs/manual/reference/method/cursor.sort/)
- [MongoDB Manual — $sort Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sort/)
- [MongoDB Manual — Sort Results with Indexes](https://www.mongodb.com/docs/manual/tutorial/sort-results-with-indexes/)
- [MongoDB Manual — Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual — BSON Type Comparison Order](https://www.mongodb.com/docs/manual/reference/bson-type-comparison-order/)
- [MongoDB Manual — Collation](https://www.mongodb.com/docs/manual/reference/collation/)
- [MongoDB Manual — cursor.skip()](https://www.mongodb.com/docs/manual/reference/method/cursor.skip/)
- [MongoDB Manual — Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/)
- [MongoDB Java Sync Driver — Sort Results](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/sort/)
- [Spring Data MongoDB — Querying Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html)
