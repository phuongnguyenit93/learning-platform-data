# Indexes for Sorting, Sort Directions, and Combined Filters in MongoDB

When a MongoDB collection holds many documents, querying the right records is only half the requirement. Applications also frequently need to **return results in a deterministic order**: newest orders first, products from lowest to highest price, or transactions in a specific status ordered by timestamp. Without an appropriate index, MongoDB may have to read many documents and execute a separate **sort** stage, making the query consume more CPU, memory, and time as data grows.

MongoDB uses **indexes** to assist both **filtering** and **sorting**. In standard index definitions, **1** denotes ascending order and **-1** denotes descending order. For a single-field index, MongoDB can traverse in either direction. For a **compound index (multi-field index)**, field order and relative ascending/descending directions determine which sort patterns can be served efficiently.

This lesson explains how to build indexes for sorting, why compound indexes are not arbitrary combinations of fields, how to apply the **Equality – Sort – Range (ESR)** principle, how to read **explain()**, and limitations involving collation, multikey indexes, and inconsistent data types. Hands-on examples use mongosh before moving on to the MongoDB Java Driver and Spring Data MongoDB.

## 1. Two Distinct Tasks: Filtering and Sorting

For example, an order management screen requires:

> Fetch orders with status PAID in region APAC, newest first; when multiple orders share the same timestamp, use _id as a tie-breaker.

Query:

~~~javascript
db.orders.find({
  status: "PAID",
  region: "APAC"
}).sort({
  createdAt: -1,
  _id: -1
})
~~~

There are two sets of requirements:

- **Filter:** `status` equals `PAID` **and** `region` equals `APAC`.
- **Sort:** `createdAt` descending, and on ties, `_id` descending.

A well-designed index lets MongoDB jump directly to the matching entries and **read them in the desired return order**, instead of gathering a large result set to sort separately.

~~~text
                     Query
        status = PAID, region = APAC
        sort(createdAt DESC, _id DESC)
                       |
                       v
          MongoDB Query Planner
                  /         \
       Suitable index     No suitable index
                 |                |
        Traverse index      Filter and/or read
         in exact order       many documents
                 |                |
                 |          Separate SORT
                 |                |
                 +--------+-------+
                          |
                          v
                   Returned results
~~~

MongoDB can pick different plans depending on data, statistics, and existing indexes. **Having an index does not mean every query is guaranteed to use it**; inspect the execution plan when tuning.

## 2. Sample Dataset for the Lesson

Use a practice MongoDB instance and connect with **mongosh**. Select a dedicated database:

~~~javascript
use index_sort_lab
~~~

The commands below assume the **orders** collection is initially empty. Each document has an easy-to-read string `_id`, `status`, `region`, `total` (Decimal128), and `createdAt` (BSON Date).

~~~javascript
db.orders.insertMany([
  {
    _id: "O01", status: "PAID", region: "APAC",
    total: NumberDecimal("120.00"),
    createdAt: ISODate("2026-10-01T08:00:00Z")
  },
  {
    _id: "O02", status: "PAID", region: "APAC",
    total: NumberDecimal("85.00"),
    createdAt: ISODate("2026-10-02T08:00:00Z")
  },
  {
    _id: "O03", status: "PAID", region: "EU",
    total: NumberDecimal("200.00"),
    createdAt: ISODate("2026-10-03T08:00:00Z")
  },
  {
    _id: "O04", status: "PENDING", region: "APAC",
    total: NumberDecimal("150.00"),
    createdAt: ISODate("2026-10-04T08:00:00Z")
  },
  {
    _id: "O05", status: "PAID", region: "APAC",
    total: NumberDecimal("230.00"),
    createdAt: ISODate("2026-10-05T08:00:00Z")
  },
  {
    _id: "O06", status: "CANCELLED", region: "US",
    total: NumberDecimal("90.00"),
    createdAt: ISODate("2026-10-06T08:00:00Z")
  },
  {
    _id: "O07", status: "PAID", region: "EU",
    total: NumberDecimal("150.00"),
    createdAt: ISODate("2026-10-07T08:00:00Z")
  },
  {
    _id: "O08", status: "PENDING", region: "APAC",
    total: NumberDecimal("40.00"),
    createdAt: ISODate("2026-10-08T08:00:00Z")
  },
  {
    _id: "O09", status: "PAID", region: "APAC",
    total: NumberDecimal("95.00"),
    createdAt: ISODate("2026-10-09T08:00:00Z")
  },
  {
    _id: "O10", status: "PAID", region: "US",
    total: NumberDecimal("300.00"),
    createdAt: ISODate("2026-10-10T08:00:00Z")
  },
  {
    _id: "O11", status: "PAID", region: "APAC",
    total: NumberDecimal("150.00"),
    createdAt: ISODate("2026-10-11T08:00:00Z")
  },
  {
    _id: "O12", status: "PAID", region: "APAC",
    total: NumberDecimal("70.00"),
    createdAt: ISODate("2026-10-11T08:00:00Z")
  }
])
~~~

Documents **O11** and **O12** share the same `createdAt`, illustrating the need for a secondary tie-breaker key. After inserting, verify:

~~~javascript
db.orders.countDocuments({});
db.orders.find(
  {},
  { _id: 1, status: 1, region: 1, total: 1, createdAt: 1 }
).sort({ _id: 1 });
~~~

Expected count is **12**. Re-running `insertMany` with the same `_id` values causes duplicate key errors; insert the sample data once or use a fresh test collection.

| _id | status | region | total | UTC Date |
|---|---|---|---:|---|
| O01 | PAID | APAC | 120.00 | 10/01 |
| O02 | PAID | APAC | 85.00 | 10/02 |
| O03 | PAID | EU | 200.00 | 10/03 |
| O04 | PENDING | APAC | 150.00 | 10/04 |
| O05 | PAID | APAC | 230.00 | 10/05 |
| O06 | CANCELLED | US | 90.00 | 10/06 |
| O07 | PAID | EU | 150.00 | 10/07 |
| O08 | PENDING | APAC | 40.00 | 10/08 |
| O09 | PAID | APAC | 95.00 | 10/09 |
| O10 | PAID | US | 300.00 | 10/10 |
| O11 | PAID | APAC | 150.00 | 10/11 |
| O12 | PAID | APAC | 70.00 | 10/11 |

Example outputs in this lesson use this dataset and **make no assumptions about default `find()` order**. Whenever order matters, always specify `sort()` explicitly.

## 3. Understanding the Direction Notation `1` and `-1`

In an **index key specification**:

~~~javascript
{ createdAt: 1 }   // Ascending
{ createdAt: -1 }  // Descending
~~~

Also in a **sort specification**:

~~~javascript
db.orders.find().sort({ createdAt: 1 });
db.orders.find().sort({ createdAt: -1 });
~~~

Although both use `1` and `-1`, the two contexts differ:

- **createIndex()** defines how keys are organized inside the index.
- **sort()** defines the result ordering requested by the query.

For example, create one index:

~~~javascript
db.orders.createIndex({ createdAt: 1 });
~~~

MongoDB can use the **ascending createdAt** index to serve both:

~~~javascript
db.orders.find().sort({ createdAt: 1 });
db.orders.find().sort({ createdAt: -1 });
~~~

Reason: for a **single-field index**, MongoDB can traverse the index forward or backward. Thus, **you do not need to create both {field:1} and {field:-1} just to support ascending and descending sorts on a single field**.

### 3.1. `$natural` Is Not Equivalent to a Business Index Sort

~~~javascript
db.orders.find().sort({ $natural: 1 });
~~~

**$natural** reflects natural storage order, not "creation order" or "`_id` order." Never use `$natural` as a substitute for `sort({createdAt: 1})` when a deterministic business ordering is required.

### 3.2. When Two Documents Share the Same Sort Key

~~~javascript
db.orders.find({
  status: "PAID",
  region: "APAC"
}).sort({ createdAt: -1 });
~~~

Documents O11 and O12 share the same `createdAt`. If you sort solely by `createdAt`, you **have no contract guaranteeing their relative order**.

Add a unique tie-breaker key:

~~~javascript
db.orders.find({
  status: "PAID",
  region: "APAC"
}).sort({
  createdAt: -1,
  _id: -1
});
~~~

The newest-to-oldest order is **O12, O11, O09, O05, O02, O01**. The `_id` key makes the ordering between documents tied on `createdAt` unambiguous.

**Deterministic sorting** is vital when combined with `limit()`, keyset pagination, or batch job checkpoints; it prevents duplicate or shifting rows when multiple records share identical timestamps.

## 4. One Single-Field Index Can Serve Both Sort Directions

Suppose you frequently view all orders ordered by `createdAt`:

~~~javascript
db.orders.createIndex(
  { createdAt: -1 },
  { name: "idx_createdAt_desc" }
);
~~~

Queries:

~~~javascript
// Newest first
db.orders.find().sort({ createdAt: -1 });

// Oldest first
db.orders.find().sort({ createdAt: 1 });
~~~

One index on `createdAt` can be traversed forward or backward to support both. MongoDB still weighs read cost and may choose another plan on tiny datasets. If results require deterministic order on date ties, include `_id` in the sort and design the corresponding compound index when the workload warrants it.

### 4.1. Indexes Do Not Change `sort()` Semantics

Creating an index does not make this query sort automatically:

~~~javascript
db.orders.find({ status: "PAID" });
~~~

If newest-first order is required, **you must still specify sort()**. An index is only a supporting structure enabling MongoDB to execute that requirement more efficiently.

### 4.2. When Is a Compound Index Needed from the Start?

If the UI consistently requires:

~~~javascript
.sort({ createdAt: -1, _id: -1 })
~~~

an index on `createdAt` alone may not supply the full ordering across both keys. A better candidate is:

~~~javascript
db.orders.createIndex(
  { createdAt: -1, _id: -1 },
  { name: "idx_createdAt_id_desc" }
);
~~~

This index sorts `createdAt` descending and, within ties on `createdAt`, sorts `_id` descending. Still, before adding a new index, inspect which filters typically accompany the sort, because a compound index with leading equality fields may serve the business query even better.

## 5. Compound Indexes: Field Order Is Part of the Design

A **compound index** stores keys across multiple fields in the specified sequence:

~~~javascript
db.orders.createIndex({
  status: 1,
  region: 1,
  createdAt: -1
});
~~~

An index does not simply "contain three fields." Picture its keys arranged as:

~~~text
status ASC
    |
    +-- region ASC (within each status)
           |
           +-- createdAt DESC (within each status + region)
~~~

Just like a directory sorted by **province**, then **district**, then **person's name**, skipping province and district leaves names no longer globally sorted in a single sequence.

### 5.1. What Is an Index Prefix?

Given the index:

~~~javascript
{ status: 1, region: 1, createdAt: -1 }
~~~

The **prefixes** are:

~~~javascript
{ status: 1 }
{ status: 1, region: 1 }
{ status: 1, region: 1, createdAt: -1 }
~~~

An index can generally assist queries and sorts matching its prefixes. Conversely, **{region:1}** or **{createdAt:-1}** are not prefixes of that index. Leveraging a trailing field also depends on predicates on the preceding fields, not merely the field's presence in the index.

### 5.2. Why Can't Field Positions Be Swapped Arbitrarily?

Compare:

~~~javascript
// Index A
{ status: 1, createdAt: -1 }

// Index B
{ createdAt: -1, status: 1 }
~~~

If a filter specifies **status = "PAID"** and sorts by **createdAt descending**, Index A lets MongoDB isolate one status slice and read in `createdAt` order. Index B sorts everything globally by `createdAt` first, then by `status` within identical timestamps—forcing it to step past many non-PAID records.

For a query requesting the newest orders across **all** statuses, Index B can be more useful because `createdAt` leads. That is why a good index must be chosen by **query pattern**, not just field names.

## 6. Ascending/Descending Directions in Compound Indexes

Unlike single-field indexes, compound indexes must account for the **relative direction of sorted fields**.

Example:

~~~javascript
db.orders.createIndex(
  { total: 1, createdAt: -1 },
  { name: "idx_total_asc_created_desc" }
);
~~~

This index can directly serve full orderings matching:

~~~javascript
// Same directions as the index key pattern
db.orders.find().sort({
  total: 1,
  createdAt: -1
});

// Exact full reversal of the index key pattern
db.orders.find().sort({
  total: -1,
  createdAt: 1
});
~~~

These two sorts are **exact inverses of each other**.

Conversely, without an equality constraint pinning preceding keys, the following two sorts **do not match the directional pattern** of the index above:

~~~javascript
db.orders.find().sort({
  total: 1,
  createdAt: 1
});

db.orders.find().sort({
  total: -1,
  createdAt: -1
});
~~~

The `{total:1, createdAt:-1}` index cannot directly produce the order required in those two cases via a single sequential scan. MongoDB may need a `SORT` stage or a different index.

### 6.1. Direction Table for Compound Indexes

Suppose an index has keys **{a:1, b:-1}**, both `a` and `b` participate in the sort, and no equality condition pins `a`:

| Requested sort | Matches index direction for direct scan? | Explanation |
|---|---|---|
| {a:1, b:-1} | Yes | Same direction |
| {a:-1, b:1} | Yes | Exact full reversal |
| {a:1, b:1} | No by direct direction rule | `b` direction differs |
| {a:-1, b:-1} | No by direct direction rule | `b` direction differs |
| {a:1} | Possible | Matches prefix |
| {b:-1} | Cannot be inferred from index alone | `b` is not a prefix; depends on predicate on `a` |

This is an index design rule for sorting. **The query planner still chooses plans by cost**: even when an index can provide ordering, actual execution depends on filters, projections, limits, and competing indexes.

### 6.2. Example with Multiple Sort Keys

Suppose a screen requires sorting by **status ascending**, **createdAt descending**, and then **_id descending**:

~~~javascript
db.orders.find().sort({
  status: 1,
  createdAt: -1,
  _id: -1
});
~~~

An index with matching directions:

~~~javascript
db.orders.createIndex({
  status: 1,
  createdAt: -1,
  _id: -1
});
~~~

This index can also be traversed in reverse to serve **{status:-1, createdAt:1, _id:1}**. However, if a user flips only `createdAt` while keeping the other two directions fixed, that is no longer a full reversal; index compatibility must be re-evaluated.

### 6.3. Equality Constraints Change Effective Sort Requirements

Given the index:

~~~javascript
{ status: 1, createdAt: -1 }
~~~

Query:

~~~javascript
db.orders.find({
  status: "PAID"
}).sort({
  createdAt: -1
});
~~~

MongoDB can use the index to locate the **status = PAID group**, within which `createdAt` is already ordered descending. Because `status` is pinned by equality, it does not need to appear in the `sort()`.

Without the `status` filter:

~~~javascript
db.orders.find().sort({
  createdAt: -1
});
~~~

`{status:1,createdAt:-1}` **does not provide a global descending `createdAt` order**, because `createdAt` is partitioned into separate groups by `status`.

This is the **non-prefix subset sort** concept: MongoDB can leverage the ordering of trailing index fields if all preceding keys are bound by suitable equality constraints.

## 7. Combining Equality Filters and Sorts: Matching Indexes to Requirements

Returning to the order-screen requirement:

~~~javascript
db.orders.find({
  status: "PAID",
  region: "APAC"
}).sort({
  createdAt: -1,
  _id: -1
});
~~~

A useful index:

~~~javascript
db.orders.createIndex(
  {
    status: 1,
    region: 1,
    createdAt: -1,
    _id: -1
  },
  { name: "idx_status_region_created_id" }
);
~~~

Why choose this ordering?

1. **status** and **region** are equality predicates, pinpointing the group of documents to read.
2. **createdAt** and **_id** follow the equality keys in exact sort direction.
3. Once status and region are fixed, index entries in that slice are organized by `createdAt` descending and `_id` descending.

With the sample dataset, the ordered results are:

~~~text
O12 (10/11, _id O12)
O11 (10/11, _id O11)
O09 (10/09)
O05 (10/05)
O02 (10/02)
O01 (10/01)
~~~

### 7.1. What If Only One Equality Field Is Filtered?

Index:

~~~javascript
{ status: 1, region: 1, createdAt: -1, _id: -1 }
~~~

Query filtering only on `status`:

~~~javascript
db.orders.find({
  status: "PAID"
}).sort({
  createdAt: -1,
  _id: -1
});
~~~

Within the `PAID` status group, MongoDB still has to traverse multiple distinct **regions**. Because `region` sits before `createdAt` and is not pinned by equality, that index cannot supply a global `createdAt` order across all regions.

If this is a frequent query pattern, the index:

~~~javascript
{ status: 1, createdAt: -1, _id: -1 }
~~~

may be more appropriate.

**Design for the workload:** A single index does not have to serve every filter variant optimally. Focus on the most frequent queries, not merely the most complex one.

### 7.2. Order of Equality Fields Can Differ

When a query **always constrains both `status` and `region` by equality**, both:

~~~javascript
{ status: 1, region: 1, createdAt: -1 }
{ region: 1, status: 1, createdAt: -1 }
~~~

can filter by the equality pair and then sort by `createdAt`. However, equality field order still affects **prefixes** and index reusability for queries filtering only one of the two fields. Review the whole workload before choosing.

## 8. The ESR Principle: Equality – Sort – Range

A widely used MongoDB compound index guideline is **ESR**:

~~~text
E = Equality: fields using exact equality predicates
S = Sort:     fields used for sorting
R = Range:    fields using range operators $gt/$gte/$lt/$lte, etc.
~~~

Typical query shape:

~~~javascript
db.orders.find({
  status: "PAID",
  region: "APAC",
  total: { $gte: NumberDecimal("100.00") }
}).sort({
  createdAt: -1
});
~~~

An **Equality → Sort → Range** index:

~~~javascript
db.orders.createIndex(
  {
    status: 1,
    region: 1,
    createdAt: -1,
    total: 1
  },
  { name: "idx_esr_status_region_date_total" }
);
~~~

When `status` and `region` are pinned, the index supplies descending `createdAt` order. Putting `total` after `createdAt` evaluates the range condition, though because `createdAt` keys are not bounded by `total`, MongoDB may scan more entries and discard documents with `total` under 100.

On the sample dataset, the expected descending `createdAt` results are **O11, O05, O01**.

### 8.1. Why Is Range Usually Placed After Sort?

Putting range before sort groups entries by the range field, breaking global ordering on the sort field. For example:

~~~javascript
// Equality -> Range -> Sort
{
  status: 1,
  region: 1,
  total: 1,
  createdAt: -1
}
~~~

With **total >= 100** and sorting by **createdAt descending**, this index sorts by `total` first. Orders totaling 120, 150, and 230 sit in separate `total` buckets; `createdAt` is ordered only within each `total` value, not globally. The query planner may need a separate sort stage.

By contrast, **{status:1,region:1,createdAt:-1,total:1}** prioritizes preserving return order while accepting extra checks on `total`.

### 8.2. ESR Is a Guideline, Not an Immutable Law

If a range predicate is **highly selective** (leaving very few documents), an **Equality – Range – Sort (ERS)** index can read far less data even with a small final sort. ESR order is not automatically fastest in every workload.

For instance, if `total >= 1,000,000` matches only a handful of orders out of millions, filtering by `total` early can be much cheaper than scanning huge numbers of records in `createdAt` order just to keep the sort intact.

Base the decision on:

- **Selectivity** of the equality and range predicates.
- Expected number of returned documents.
- Whether **limit** is applied.
- Cost of sorting (in-memory or resource usage).
- Existing data and indexes.
- Results from **explain("executionStats")** on a representative workload.

### 8.3. Do Not Confuse Range with Every Predicate Expression

Operators such as **$gt, $gte, $lt, $lte** are classic range predicates. Conditions like **$ne** and **$nin** have their own selectivity and index usage characteristics and generally do not behave like point equalities. **$in** also depends on context, list size, and sorting; never assume every `$in` behaves identically to a single equality.

ESR is useful when you can clearly specify query patterns before creating indexes, rather than replacing analysis of actual queries.

## 9. Range and Sort on the Same Field

An easier case to optimize is **range filtering and sorting on the exact same field**. For example, orders with totals from 100 up to 250 sorted by ascending total:

~~~javascript
db.orders.find({
  status: "PAID",
  total: {
    $gte: NumberDecimal("100.00"),
    $lt: NumberDecimal("250.00")
  }
}).sort({
  total: 1
});
~~~

Suitable index:

~~~javascript
db.orders.createIndex(
  { status: 1, total: 1 },
  { name: "idx_paid_total" }
);
~~~

Once `status` is pinned to `PAID`, MongoDB can scan the **`total` range** in the index in ascending order. On the sample data, matching documents appear sorted by `total`:

~~~text
O01   120.00
O07   150.00
O11   150.00
O03   200.00
O05   230.00
~~~

The order between **O07** and **O11** is undefined when sorting only by `total`, since both share 150.00. If a deterministic order is needed:

~~~javascript
db.orders.find({
  status: "PAID",
  total: {
    $gte: NumberDecimal("100.00"),
    $lt: NumberDecimal("250.00")
  }
}).sort({
  total: 1,
  _id: 1
});
~~~

When this query runs frequently, the index:

~~~javascript
{ status: 1, total: 1, _id: 1 }
~~~

supports both `total` order and the `_id` tie-breaker. Do not assume `{status:1,total:1}` alone guarantees secondary `_id` order: declare the sort and select an index covering both keys when deterministic tie-breaking is required.

### 9.1. Reverse Sorts Can Also Use the Index

With **{status:1,total:1}**, if `status` is pinned by equality, MongoDB can traverse the slice backward to serve:

~~~javascript
db.orders.find({ status: "PAID" })
  .sort({ total: -1 });
~~~

When an index has multiple fields actively participating in sorting, evaluate **exact full reversal of the key pattern**. When leading fields are pinned by equality, sort eligibility depends only on the trailing fields.

### 9.2. A Preceding Range Breaks a Different Trailing Sort

Index:

~~~javascript
{ status: 1, total: 1, createdAt: -1 }
~~~

can filter `status` and a `total` range while returning `total` ascending. However, if you want to **sort solely by `createdAt` descending** across all totals in that range, the index does not order `createdAt` globally—it orders `createdAt` inside each `total` value. A different index or a `SORT` stage is needed.

Practical rule of thumb: with multiple fields, ask **"At the point index entries are read, have all keys preceding the sort field been pinned to a single value?"**

## 10. Inspecting Execution Plans with explain()

You cannot evaluate an index merely by verifying that a query returns correct results. The optimization goal is reducing scanned data and avoiding expensive sorts when the benefit justifies it.

MongoDB provides **explain()** to inspect query execution plans:

~~~javascript
db.orders.find({
  status: "PAID",
  region: "APAC"
}).sort({
  createdAt: -1,
  _id: -1
}).explain("executionStats");
~~~

You will see details in **queryPlanner** and **executionStats**. Output structure varies across MongoDB versions and query execution engines; some place stages directly in `winningPlan`, while others nest structures like `queryPlan`.

### 10.1. Key Elements to Look For

| Common field or stage | Meaning |
|---|---|
| winningPlan | Chosen execution plan |
| IXSCAN | Index scan |
| COLLSCAN | Collection scan |
| SORT | Separate sort stage in the plan |
| FETCH | Fetching full documents when the index does not supply all needed data |
| PROJECTION_* | Extracting or shaping returned fields |
| indexName | Name of the index used in that stage |
| totalKeysExamined | Number of index entries examined |
| totalDocsExamined | Number of documents read/examined |
| nReturned | Number of documents returned |
| executionTimeMillis | Execution time reported per explain rules |

Interpret metrics **in context**: IXSCAN is not automatically good if it scans most of the index. COLLSCAN is not automatically bad on a tiny collection. A separate SORT can be completely fine on a few dozen records left after a highly selective range filter.

### 10.2. Observing an Index Aligned with the Query Pattern

Create the designed index:

~~~javascript
db.orders.createIndex(
  {
    status: 1,
    region: 1,
    createdAt: -1,
    _id: -1
  },
  { name: "idx_status_region_created_id" }
);
~~~

Then:

~~~javascript
db.orders.find({
  status: "PAID",
  region: "APAC"
}).sort({
  createdAt: -1,
  _id: -1
}).explain("executionStats");
~~~

If the optimizer picks the suitable index to supply ordering, you will normally see the relevant index scan and **no separate blocking SORT stage**. However, because the sample collection holds only 12 documents, MongoDB may still pick COLLSCAN + SORT due to lower overall overhead; do not mistake that for a broken index definition.

In experiments, you can use **hint()** to force a specific index and observe its behavior:

~~~javascript
db.orders.find({
  status: "PAID",
  region: "APAC"
}).sort({
  createdAt: -1,
  _id: -1
}).hint(
  "idx_status_region_created_id"
).explain("executionStats");
~~~

**hint() is an investigative tool with specialized use cases**, not a default optimization for production queries. Hinting forces an index even when the query planner might pick a superior plan.

### 10.3. `totalKeysExamined` Exceeding `nReturned` Can Be Normal

If an index orders `status`, `region`, `createdAt`, then `total`, while the query filters `total >= 100`, the server may step through many `PAID`/`APAC` entries, inspect `total`, and return only a subset. In that case:

~~~text
totalKeysExamined  > nReturned
~~~

is not necessarily an error. The real question is whether the number of entries examined is reasonable given selectivity, dataset size, and latency targets.

### 10.4. Comparing Before and After Indexing on Representative Data

A practical observation workflow:

1. Record the exact filter, projection, sort, and limit used by the application.
2. Run `explain("executionStats")` before adding or changing indexes.
3. Create the candidate index for the query pattern.
4. Re-check `winningPlan`, keys/docs examined, `nReturned`, and `SORT` stages.
5. Measure actual latency under representative load and data volume.
6. Check added insert/update overhead and index storage growth.

**Never run benchmarks in a way that impacts production systems.** A twelve-document dataset only teaches mechanics; it does not represent performance on collections with millions of documents.

## 11. Sort + Limit: Indexes Shine for First-Page Results

A UI often needs only **the 20 newest orders**:

~~~javascript
db.orders.find({
  status: "PAID",
  region: "APAC"
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
~~~

When an index supports both filter and sort, MongoDB can scan matching entries in order and stop once 20 documents are collected, rather than sorting the entire matching set.

This is why sort-supporting indexes are especially valuable for **top-N** queries and paginated views.

### 11.1. `limit` Does Not Replace `sort`

~~~javascript
db.orders.find({ status: "PAID" }).limit(20);
~~~

This asks for at most 20 documents, with no guarantee they are the **20 newest**. To get the newest ones, you must include **sort({createdAt:-1,...})**.

### 11.2. Offset Pagination Can Be Expensive

~~~javascript
db.orders.find({
  status: "PAID",
  region: "APAC"
}).sort({
  createdAt: -1,
  _id: -1
}).skip(10000).limit(20);
~~~

Even with an index supporting the order, skipping a large offset forces MongoDB to walk past all preceding entries before reaching the target page. If documents are inserted or deleted concurrently, offsets also shift, causing duplicates or skipped items across pages.

For deep pagination, consider **keyset pagination** using a deterministic sort key:

~~~javascript
// Assuming the last item on the previous page:
const lastCreatedAt = ISODate("2026-10-09T08:00:00Z");
const lastId = "O09";

db.orders.find({
  status: "PAID",
  region: "APAC",
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    {
      createdAt: lastCreatedAt,
      _id: { $lt: lastId }
    }
  ]
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
~~~

The predicate uses **$lt** because we are reading newest to oldest. On the sample dataset starting after `O09`, the next page is **O05, O02, O01**. Ensure `_id` and `createdAt` maintain consistent types, sort keys do not mutate arbitrarily, and the index matches the query shape.

**Keyset pagination does not create an immutable snapshot either** under concurrent writes; its primary benefit is addressing page boundaries by key rather than offset.

## 12. Projections and Covered Queries

An index does more than accelerate filters and sorts—sometimes it contains **every field the application needs to return**, letting MongoDB avoid fetching documents. Under qualifying conditions, this is called a **covered query**.

Example index:

~~~javascript
{
  status: 1,
  region: 1,
  createdAt: -1,
  _id: -1
}
~~~

Query requesting only fields present in the index:

~~~javascript
db.orders.find(
  {
    status: "PAID",
    region: "APAC"
  },
  {
    _id: 1,
    status: 1,
    region: 1,
    createdAt: 1
  }
).sort({
  createdAt: -1,
  _id: -1
});
~~~

In terms of required fields, the index covers filter, sort, and projection. MongoDB **can** satisfy this query without reading the base documents, depending on index configuration and execution rules. Check **totalDocsExamined**, `FETCH` stages, and `winningPlan` to verify coverage.

If you add **total** to the projection while the index lacks `total`:

~~~javascript
{
  _id: 1,
  status: 1,
  region: 1,
  createdAt: 1,
  total: 1
}
~~~

MongoDB may need to fetch the original documents to read `total`. Do not stuff every document field into an index solely to achieve coverage if index overhead becomes excessive.

### 12.1. Note on `_id` in Projections

By default, MongoDB query results include **_id**. If the index excludes `_id` and you want a covered query without `_id`, explicitly exclude `_id` in the projection:

~~~javascript
db.orders.find(
  { status: "PAID" },
  { status: 1, region: 1, _id: 0 }
);
~~~

Whether `_id` resides in the index depends on the index definition. A compound index containing **_id:1** or **_id:-1** can supply that key; an index solely on `status`/`region` does not automatically expose `_id` for all projection patterns.

### 12.2. Covered Queries Are Not the Only Goal

An overly wide index can speed up one read while:

- Consuming more RAM and disk space.
- Forcing writes to update larger index keys.
- Increasing build/rebuild, operational, and maintenance overhead.
- Still failing to serve other filters or sorts.

Choose indexes to balance **read cost** against **write and storage cost**, rather than indexing every field combination.

## 13. Factors Preventing an Index from Supporting a Sort as Expected

An index whose field names appear to match can still fail to serve the full sort. Before judging a plan, check data types, collations, multikey behavior, and other constraints.

### 13.1. Collation in String Comparison and Sorting

String sorting is governed by **collation**, which specifies language rules, case sensitivity, and accent handling. If an index is created with a different collation from the query, it may not support the required string comparisons or sorts.

Example `customers` collection with `country` and `fullName`:

~~~javascript
db.customers.createIndex(
  { country: 1, fullName: 1 },
  {
    name: "idx_country_name_vi",
    collation: {
      locale: "vi",
      strength: 2
    }
  }
);
~~~

Query using the matching collation:

~~~javascript
db.customers.find({
  country: "VN"
}).collation({
  locale: "vi",
  strength: 2
}).sort({
  fullName: 1
});
~~~

The index can help because `country` is bound by equality and `fullName` follows. However, if a query uses **simple collation** or a different collation to sort names, ordering rules differ and MongoDB may not use this index to satisfy the sort.

For technical codes like `sku` or `code`, clarify whether binary or locale-based comparison is needed; never apply one collation across all data just because it fits personal names.

### 13.2. Multikey Indexes When a Field Is an Array

MongoDB creates a **multikey index** when indexing an array field under supported conditions. Such indexes store keys derived from each array element, aiding element-value queries.

Example:

~~~javascript
db.products.createIndex({
  tags: 1,
  createdAt: -1
});
~~~

Do not assume this means every query sorting by array `tags` or `createdAt` skips `SORT`. When sorting array fields, MongoDB follows specific rules for sort key selection and index bounds/multikey paths; certain filter and sort combinations still require a separate sort stage.

If a screen frequently sorts by **createdAt** and filters by a tag, verify with **explain()** on real data rather than assuming from the two fields' presence in the index.

### 13.3. Mixed BSON Types in Data

Suppose `total` is written sometimes as `Decimal128` and sometimes as a `String`:

~~~javascript
{ total: NumberDecimal("100.00") }
{ total: "100.00" }
~~~

Indexes sort according to BSON type comparison rules and do not magically treat the string `"100.00"` as `Decimal128`. Numeric range filters can miss string values, and sorting mixed-type data can produce results outside expected numeric order.

The fix is **enforcing BSON types at write time**, using schema validation where appropriate and migrating legacy data. Indexes cannot repair inconsistent data types.

### 13.4. One Index Does Not Automatically Replace All Others

Having the index:

~~~javascript
{ status: 1, createdAt: -1 }
~~~

serves filtering by `status` + sorting by `createdAt` well. However, a query filtering or sorting by **region**, or sorting by `createdAt` across all statuses, may require a different index or plan.

Index intersection (combining multiple indexes in certain plans) **also does not guarantee** every filter + sort combination runs as efficiently as a single compound index. If sorting is on a critical path, design the index around the complete query pattern.

### 13.5. Partial Indexes: Useful for Targeted Subsets

If most queries read only `PAID` orders, consider a **partial index**:

~~~javascript
db.orders.createIndex(
  {
    region: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "idx_paid_region_date",
    partialFilterExpression: {
      status: "PAID"
    }
  }
);
~~~

The index includes only documents matching the declared partial filter. Queries must include compatible predicates proving results fall within the indexed subset so MongoDB can use it:

~~~javascript
db.orders.find({
  status: "PAID",
  region: "APAC"
}).sort({
  createdAt: -1,
  _id: -1
});
~~~

If a query **does not restrict `status = PAID`**, this partial index lacks full coverage and cannot be used to retrieve all orders. It is a targeted optimization, not a general replacement for standard indexes.

### 13.6. Write Costs of Indexes

On every insert, update to indexed fields, or delete, MongoDB may have to update corresponding indexes. Creating excessive compound indexes can:

- Increase disk storage and cache consumption.
- Increase write and update overhead.
- Lengthen index build and maintenance windows.
- Give the planner more candidate plans to evaluate.

Therefore, **do not create every ascending/descending permutation of fields**. First exploit reverse scans, prefixes, and equality prefixes; only add further indexes for genuinely needed query patterns.

## 14. Supporting Multiple Sort Directions in One Product

Suppose a UI offers two sort choices:

1. **Newest:** sort by `createdAt` descending, `_id` descending.
2. **Oldest:** sort by `createdAt` ascending, `_id` ascending.

With matching `status` + `region` equality filters:

~~~javascript
db.orders.createIndex({
  status: 1,
  region: 1,
  createdAt: -1,
  _id: -1
});
~~~

One index can support both sorts when the equality fields are pinned:

~~~javascript
// Newest
db.orders.find({
  status: "PAID",
  region: "APAC"
}).sort({
  createdAt: -1,
  _id: -1
});

// Oldest
db.orders.find({
  status: "PAID",
  region: "APAC"
}).sort({
  createdAt: 1,
  _id: 1
});
~~~

However, if the UI option is:

~~~javascript
// createdAt descending, _id ascending
db.orders.find({
  status: "PAID",
  region: "APAC"
}).sort({
  createdAt: -1,
  _id: 1
});
~~~

then the sort directions are neither aligned with nor the full inverse of **{createdAt:-1, _id:-1}**. If that query is critical, you may need a different key pattern or accept a `SORT` stage.

### 14.1. Distinguishing Equality Key Direction from Sort Key Direction

When `status` and `region` are pinned by equality, their `1` or `-1` direction **does not affect ordering inside a slice with fixed values**. Thus, when evaluating reverse scans for sorting `createdAt`/`_id`, what matters is the relative direction among **the keys actively participating in the sort**.

Even so, equality key directions still matter for other query patterns that sort on them or filter only a partial prefix. Never alter index directions casually without auditing other queries.

### 14.2. Do Not Add an Index Just Because Users Toggle "Newest / Oldest"

When both sort keys flip direction together:

~~~javascript
{ createdAt: -1, _id: -1 }
{ createdAt: 1, _id: 1 }
~~~

one matching index can be scanned in either direction. Understanding **reverse index traversal** helps eliminate duplicate indexes.

## 15. MongoDB Java Sync Driver: Creating Indexes and Sorting

In Java applications using the MongoDB Sync Driver, **com.mongodb.client.model.Indexes** helps define indexes, and **Sorts** builds sort specifications. Examples assume a compatible **mongodb-driver-sync** dependency and a configured **MONGODB_URI** environment variable.

### 15.1. Creating a Compound Index in Java

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Indexes;
import com.mongodb.client.model.IndexOptions;
import org.bson.Document;
import org.bson.conversions.Bson;

public class CreateOrdersIndex {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> orders = client
                    .getDatabase("index_sort_lab")
                    .getCollection("orders");

            Bson indexKeys = Indexes.compoundIndex(
                    Indexes.ascending("status", "region"),
                    Indexes.descending("createdAt", "_id")
            );

            String name = orders.createIndex(
                    indexKeys,
                    new IndexOptions().name("idx_status_region_created_id")
            );

            System.out.println("Index: " + name);
        }
    }
}
~~~

In this snippet:

- **Indexes.ascending("status","region")** creates two ascending keys.
- **Indexes.descending("createdAt","_id")** creates two descending keys.
- **Indexes.compoundIndex(...)** combines keys in sequence.
- **IndexOptions().name(...)** assigns a clear name for index listings and explain plans.

Creating an index is a costly DDL/administrative operation. In production applications, manage indexes via controlled startup/migration workflows rather than recreating indexes per request.

### 15.2. Query with Filter + Sort + Limit

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;

public class ReadRecentPaidOrders {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        Bson filter = Filters.and(
                Filters.eq("status", "PAID"),
                Filters.eq("region", "APAC")
        );

        Bson sort = Sorts.orderBy(
                Sorts.descending("createdAt"),
                Sorts.descending("_id")
        );

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> orders = client
                    .getDatabase("index_sort_lab")
                    .getCollection("orders");

            try (MongoCursor<Document> cursor = orders.find(filter)
                    .projection(Projections.include(
                            "status", "region", "createdAt"))
                    .sort(sort)
                    .limit(20)
                    .iterator()) {

                while (cursor.hasNext()) {
                    Document order = cursor.next();
                    System.out.println(order.toJson());
                }
            }
        }
    }
}
~~~

This Java query mirrors the filter and sort used in mongosh. Here, **MongoCursor** is closed via try-with-resources, and `MongoClient` closes when the CLI program exits. Long-lived web applications should reuse a managed `MongoClient` bean while closing cursors after each read.

### 15.3. Using Sorts.ascending and Sorts.descending Properly

~~~java
// Single field, ascending
Sorts.ascending("total");

// Single field, descending
Sorts.descending("createdAt");

// Multiple fields, mixed directions
Sorts.orderBy(
        Sorts.ascending("total"),
        Sorts.descending("createdAt")
);
~~~

These expressions only construct a **sort specification**. Which index MongoDB selects depends on existing collection indexes and accompanying filters; the `Sorts` API itself does not create indexes.

## 16. Spring Data MongoDB: Query, Sort, and Compound Indexes

With Spring Data MongoDB, you can combine **Criteria**, **Query**, and **Sort**:

~~~java
import java.util.List;
import org.bson.Document;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class OrderSearchService {
    private final MongoTemplate mongoTemplate;

    public OrderSearchService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<Document> findRecentPaidApacOrders() {
        Query query = Query.query(
                Criteria.where("status").is("PAID")
                        .and("region").is("APAC")
        );

        query.with(Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("_id")
        ));
        query.limit(20);

        return mongoTemplate.find(
                query,
                Document.class,
                "orders"
        );
    }
}
~~~

Assuming `MongoTemplate` points to the **index_sort_lab** database, the returned order on the sample dataset is **O12, O11, O09, O05, O02, O01**.

### 16.1. Declaring a Compound Index on an Entity

When using Spring Data MongoDB to map documents to entities, compound indexes can be declared via annotations per project configuration:

~~~java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("orders")
@CompoundIndex(
        name = "idx_status_region_created_id",
        def = "{'status': 1, 'region': 1, 'createdAt': -1, '_id': -1}"
)
public class OrderDocument {
    @Id
    private String id;
    private String status;
    private String region;
    private Instant createdAt;

    // Constructors, getters, and setters per project conventions.
}
~~~

This annotation declares the desired index. **Whether the index is auto-created at startup depends on Spring Data MongoDB configuration**, version, and deployment workflow. In production systems, manage index changes proactively to avoid unintended index builds as instances begin serving traffic.

Additionally, Java `Instant` fields must map cleanly to BSON Date, and `_id` types must match stored documents. Projects using `ObjectId` or custom IDs may require different mapping configurations.

### 16.2. Good Indexes Must Match Actual Repository Queries

If a repository method routinely queries:

~~~text
status = PAID
region = APAC
sort by createdAt DESC, _id DESC
~~~

then an index on `status`/`region`/`createdAt`/`_id` aligns in principle. Yet if the same application also has an "all latest orders" page without status/region filters, that page may require a separate index starting with `createdAt`. Never assume a single entity annotation optimizes every repository query.

## 17. A Design Workflow for Filter + Sort Indexes

Instead of guessing indexes, translate business requirements into measurable designs.

### Step 1. Record the Full Query Pattern

Example:

~~~javascript
db.orders.find(
  {
    status: "PAID",
    region: "APAC",
    total: {
      $gte: NumberDecimal("100.00")
    }
  },
  {
    _id: 1,
    total: 1,
    createdAt: 1
  }
).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
~~~

Do not write merely "query orders by status." Capture **projection**, **sort**, **limit**, and each field's predicate type.

### Step 2. Group Fields by Role

| Field | Role |
|---|---|
| status | Equality |
| region | Equality |
| total | Range |
| createdAt | Sort descending |
| _id | Sort descending, tie-breaker |

Following ESR, a candidate index is:

~~~javascript
{
  status: 1,
  region: 1,
  createdAt: -1,
  _id: -1,
  total: 1
}
~~~

This index prioritizes reading results in exact sort order. However, since `total` sits behind the sort keys, narrowing by `total` may be less tight than an index placing `total` earlier.

### Step 3. Consider Range Before Sort If Highly Selective

An alternative:

~~~javascript
{
  status: 1,
  region: 1,
  total: 1,
  createdAt: -1,
  _id: -1
}
~~~

This prioritizes the range on `total`, though it does not preserve global `createdAt` ordering across the `total` span and may need a trailing sort.

If the `total` threshold rarely matches, sorting a tiny subset can be inexpensive. If the UI always fetches the top 20 newest orders from a large pool, preserving order in the index often yields greater benefit. **Never pick by guesswork alone.**

### Step 4. Measure with `explain` and a Representative Workload

~~~javascript
db.orders.find({
  status: "PAID",
  region: "APAC",
  total: { $gte: NumberDecimal("100.00") }
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20).explain("executionStats");
~~~

Compare index entries scanned, documents read, documents returned, and whether `SORT` appears. Beyond latency, measure impact on inserts/updates and added index footprint.

### Step 5. Review Adjacent Query Patterns

Several patterns often coexist in a product:

| Query pattern | Candidate index |
|---|---|
| All newest orders | `{createdAt:-1, _id:-1}` |
| Newest PAID orders only | `{status:1, createdAt:-1, _id:-1}` |
| Newest PAID orders in APAC | `{status:1, region:1, createdAt:-1, _id:-1}` |
| PAID in `total` range, sorted by `total` ASC | `{status:1, total:1, _id:1}` |
| Single customer timeline | `{customerId:1, createdAt:-1, _id:-1}` if schema includes `customerId` |

These are **pattern-based candidates**, not instructions to build every index in the table. Longer indexes can satisfy shorter ones via prefixes; if a shorter index is completely redundant under your workload, consider dropping it. Conversely, a shorter index can sometimes remain worthwhile due to smaller footprint and distinct read/write efficiency. Base decisions on plan analysis and real operations.

## 18. Common Misconceptions

| Misconception | Consequence | Correct understanding |
|---|---|---|
| `{createdAt:1}` only supports ascending sorts | Creating redundant reverse single-field indexes | Single-field indexes can be scanned forward or backward |
| Including all fields in a compound index is enough | Queries still incur `SORT` stages | Requires matching key order and relative sort directions |
| `{a:1,b:-1}` supports every ASC/DESC combination | Wrong index choices | Directly supports matching pattern or exact full reversal |
| `{status:1,createdAt:-1}` always sorts `createdAt` efficiently across the collection | `createdAt` is partitioned per `status` group | Needs equality on `status` or a dedicated global sort index |
| Just adding `sort()` makes MongoDB use an index | Queries slow down as data grows | Create an aligned index and verify with `explain` |
| Having an index means `find()` skips `sort()` | Result order is not guaranteed | Still specify `sort()` explicitly as required |
| Since `status` is equality, placing it after Range is equivalent | Increases scanned keys or loses useful sort order | Apply ESR and examine data distribution |
| ESR is always fastest | Misses ERS wins on ultra-selective ranges | Compare actual plans and execution costs |
| Range on `total` then sort by date is always handled together by an index | Date order is fragmented across `total` values | Weigh sort priority vs. range filtering |
| Sorting by `createdAt` alone is stable across ties | Pagination duplicates or drops items | Add a unique tie-breaker such as `_id` |
| `skip(100000)` costs the same as `skip(10)` | Deep pages become slow | Consider keyset pagination |
| A String index sorts numeric strings numerically | Results follow lexicographical order instead | Standardize BSON types and fix bad data |
| Any query collation leverages a String index | Index fails to provide expected comparison order | Align query and index collations when needed |
| Multikey indexes always satisfy sorts on array fields | Queries may still require separate sorts | Check multikey rules and `explain` |
| Seeing `IXSCAN` means optimal | May still scan vast numbers of entries | Check keys/docs examined, `nReturned`, and total cost |
| Hinting an index is always better than the planner | Forces suboptimal plans over time | Use `hint` deliberately, never as a blanket default |
| Adding extra indexes has no downsides | Inflates write costs and storage | Index only for critical query patterns |

## 19. Practice Exercises

These exercises use the **orders** dataset from Section 2. Determine the logical result sets first, then create the necessary indexes and inspect them with `explain()` in a practice environment.

### Exercise 1. Single-Field Index and Two Sort Directions

Create one index:

~~~javascript
db.orders.createIndex({ total: 1 });
~~~

Execute:

~~~javascript
db.orders.find().sort({ total: 1 });
db.orders.find().sort({ total: -1 });
~~~

**Question:** Is a second `{total:-1}` index mandatory just because the second query sorts descending?

**Guidance:** No. MongoDB can scan a single-field index in both directions. When multiple documents share the same `total`, add a secondary key to `sort()` for deterministic order and evaluate a matching compound index.

### Exercise 2. Mixed Directions in a Compound Index

Given the index:

~~~javascript
{ total: 1, createdAt: -1 }
~~~

Identify which sorts match directionally when both fields participate in the sort:

~~~javascript
// A
{ total: 1, createdAt: -1 }

// B
{ total: -1, createdAt: 1 }

// C
{ total: 1, createdAt: 1 }

// D
{ total: -1, createdAt: -1 }
~~~

**Answer:** A matches directly and B is the exact full reversal. C and D do not align directionally to serve the full sort in one direct scan unless special constraints reduce the effective sort requirement.

### Exercise 3. Two Equality Filters, Newest First

Write a query finding **PAID** orders in **APAC**, sorted by `createdAt` and `_id` descending. Create an index following Equality → Sort.

**Reference solution:**

~~~javascript
db.orders.createIndex({
  status: 1,
  region: 1,
  createdAt: -1,
  _id: -1
});

db.orders.find({
  status: "PAID",
  region: "APAC"
}).sort({
  createdAt: -1,
  _id: -1
});
~~~

Results: **O12, O11, O09, O05, O02, O01**.

**Open question:** If the `region` filter is removed, does that index still guarantee descending `createdAt` order across all regions within `PAID`? Why or why not?

**Guidance:** Not from this index layout, because `region` precedes `createdAt` and is no longer pinned by equality.

### Exercise 4. Range and Sort on the Same Field

Find `PAID` orders with `total` from 100 up to 250, sorted by `total` ascending.

~~~javascript
db.orders.find({
  status: "PAID",
  total: {
    $gte: NumberDecimal("100.00"),
    $lt: NumberDecimal("250.00")
  }
}).sort({
  total: 1
});
~~~

Candidate index:

~~~javascript
{ status: 1, total: 1 }
~~~

Matching documents: **O01, O03, O05, O07, O11**. Ordered by `total`: O01, O07/O11 (both 150), O03, O05. To eliminate ambiguity at `total = 150`, add `_id` to the sort and consider `{status:1,total:1,_id:1}`.

### Exercise 5. Distinguishing ESR and ERS

Query:

~~~javascript
db.orders.find({
  status: "PAID",
  region: "APAC",
  total: { $gte: NumberDecimal("100.00") }
}).sort({
  createdAt: -1
});
~~~

Compare the two indexes:

~~~javascript
// A: Equality -> Sort -> Range
{ status: 1, region: 1, createdAt: -1, total: 1 }

// B: Equality -> Range -> Sort
{ status: 1, region: 1, total: 1, createdAt: -1 }
~~~

Explain which index is better suited to streaming results in `createdAt` order and which can perform better if the `total` threshold is extremely selective. Propose how to use `explain()` to observe actual costs.

**Guidance:** A prioritizes `createdAt` ordering; B prioritizes filtering by `total`. There is no single fixed optimal answer across all data distributions.

### Exercise 6. Covered Query

Given the index:

~~~javascript
{ status: 1, region: 1, createdAt: -1, _id: -1 }
~~~

Query projecting only:

~~~javascript
{
  _id: 1,
  status: 1,
  region: 1,
  createdAt: 1
}
~~~

Show why all required fields live inside the index. Then add **total** to the projection and explain why MongoDB may have to FETCH the original documents.

### Exercise 7. Keyset Pagination

A screen lists `PAID`/`APAC` orders by `createdAt DESC, _id DESC`. The previous page ended at `O09`. Write the condition fetching documents **older than O09** in the same order, up to 5 documents.

**Reference solution:**

~~~javascript
const lastCreatedAt = ISODate("2026-10-09T08:00:00Z");
const lastId = "O09";

db.orders.find({
  status: "PAID",
  region: "APAC",
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    {
      createdAt: lastCreatedAt,
      _id: { $lt: lastId }
    }
  ]
}).sort({
  createdAt: -1,
  _id: -1
}).limit(5);
~~~

On the initial dataset, the results are **O05, O02, O01**.

### Exercise 8. Reading explain() Instead of Guessing

Run:

~~~javascript
db.orders.find({
  status: "PAID",
  region: "APAC"
}).sort({
  createdAt: -1,
  _id: -1
}).explain("executionStats");
~~~

Locate **winningPlan**, **totalKeysExamined**, **totalDocsExamined**, **nReturned**, and check whether a separate `SORT` stage appears. Compare before and after creating the matching compound index. Explain why the sample collection is too small to infer production speed.

### Exercise 9. Choosing Indexes Across Multiple Screens

Suppose an application has three screens:

1. All newest orders, unfiltered.
2. Newest `PAID` orders, unfiltered by region.
3. Newest `PAID` orders in `APAC`.

Propose candidate indexes for each screen and identify which indexes can serve other queries via prefixes. Do not simply output an index list; explain the effect of key order and the cost of maintaining multiple indexes.

**Guidance:** You can evaluate:

~~~javascript
{ createdAt: -1, _id: -1 }
{ status: 1, createdAt: -1, _id: -1 }
{ status: 1, region: 1, createdAt: -1, _id: -1 }
~~~

These are **query-pattern candidates**, not a requirement to build all three in every deployment. Weigh each screen's frequency, data characteristics, and actual efficiency via `explain()`.

## 20. Summary of Key Principles

1. **Single-field indexes can be traversed in both directions.** Do not create duplicate ascending and descending indexes just to sort one field in both directions.
2. **Compound indexes depend on field order and relative directions.** They support sorting along the key pattern or its exact full reversal; when sorting only trailing fields, preceding prefix fields must be pinned by equality.
3. **Filters and sorts must be designed together.** Placing equality fields ahead of sort keys lets MongoDB isolate a slice and read directly in order.
4. **ESR is a helpful guideline, not an absolute rule.** If a range is ultra-selective, ERS with a trailing sort may outperform it on specific workloads.
5. **Always declare `sort()` explicitly**, and include a unique tie-breaker key when ordering must be deterministic across tied values.
6. **`explain()` is your plan verification tool.** Inspect `IXSCAN`, `SORT`, `FETCH`, keys/docs examined, and real datasets rather than merely counting created indexes.
7. **Indexes carry write and storage costs.** Choose indexes around critical query patterns and avoid redundant indexes.

A good index does more than name the queried fields. It reflects **how the application filters, the desired output order, sort directions, and result set size**. Once you master reverse index traversal, equality prefixes, compound sorting, and ESR trade-offs, you can design MongoDB queries accurately and scale performance with solid evidence as your data grows.
