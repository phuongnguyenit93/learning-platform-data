# Filtering Early with $match and Its Relationship with Indexes

In the MongoDB Aggregation Framework, a pipeline processes documents through consecutive **stages**. Each stage can filter, transform, sort, group, or combine data. If a pipeline has to read millions of documents before discarding most of them with `$match`, earlier stages may have already spent CPU, memory, I/O, and time without providing value. Therefore, an important principle is to **filter early with `$match` when it does not change the meaning of the result**, while also enabling the query planner to exploit **indexes**.

However, "putting `$match` first" is not a rule to apply blindly: some filters must be placed **after `$unwind`, `$group`, `$addFields`, or `$lookup`** because they depend on data created by those stages. MongoDB has an **aggregation pipeline optimizer** that can automatically split and push some filters earlier; the degree of optimization depends on dependencies, version, and pipeline shape. This lesson covers both **correct semantics** and **how to verify performance using `explain`**.

This is a lesson in the **Aggregation Basics** chapter of the *Database Engine Document MongoDB* module. After this lesson, you will be able to:

1. Write `$match` using syntax similar to `find()`, and use `$expr` when expression evaluation is needed.
2. Choose filter placement to reduce the volume of data passing through expensive stages.
3. Understand when `$match` can leverage **single-field, compound, multikey, and partial indexes**.
4. Distinguish between **filtering before reshaping data** and **filtering on computed results**.
5. Read `explain("executionStats")` to check `IXSCAN`, `COLLSCAN`, keys/documents examined, and pipeline optimizations.
6. Design pipelines with `$sort`, `$group`, `$unwind`, `$lookup`, and `$facet` while preserving business correctness.
7. Write equivalent queries through the MongoDB Java Sync Driver and select indexes based on access patterns.

> **Versions:** Examples use common syntax in MongoDB 7.0/8.0 and compatible releases. The `explain` structure, query optimizer, and execution engines such as SBE may change across versions. Refer to the Database Manual for your exact MongoDB Server/FCV; do not treat one specific `explain` output as a fixed format.

## 1. What Does `$match` Do in a Pipeline?

`$match` is an **aggregation stage** that keeps only documents satisfying a condition and drops non-matching documents before passing them to the next stage.

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } }
])
~~~

Conditions inside `$match` generally use **query predicate syntax** similar to `find()`:

~~~javascript
// Two ways to filter with the same meaning on source documents:
db.orders.find({ status: "PAID" })

db.orders.aggregate([
  { $match: { status: "PAID" } }
])
~~~

However, aggregation allows subsequent stages to continue processing:

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $group: { _id: "$customerId", total: { $sum: "$total" } } },
  { $sort: { total: -1 } }
])
~~~

### 1.1. Data Flow

~~~text
Collection orders: millions of documents
            |
            v
        $match
    status = "PAID"
            |
            v
   Only matching documents
            |
            v
       $group
   Group by customerId
            |
            v
        $sort
   Sort total amount descending
~~~

If `$match` filters out many documents at the start, `$group` receives less input, hash/accumulator tables may be smaller, and the number of groups to sort at the end of the pipeline may also shrink. Actual benefits depend on **filter selectivity, indexes, group cardinality, and execution strategy**.

### 1.2. `$match` Filters Documents; It Does Not Transform Fields on Its Own

| Stage | Role |
|---|---|
| `$match` | Filters documents by condition. |
| `$project` | Keeps/drops/computes output fields. |
| `$addFields` / `$set` | Adds or overwrites fields. |
| `$unwind` | Splits array elements into separate pipeline documents. |
| `$group` | Groups documents by key, computes accumulators. |
| `$sort` | Sorts pipeline documents. |
| `$limit` | Keeps at most a maximum number of documents. |
| `$lookup` | Joins data from another collection. |
| `$facet` | Runs multiple branches on the same input set. |

Filtering before transforming stages is usually beneficial **if the condition only uses source fields and moving its position does not alter the result**. When a filter references a field computed by another stage, or needs to apply to an individual item after unwinding, dependencies must be preserved.

### 1.3. Common Predicates

~~~javascript
{
  $match: {
    tenantId: "T-A",
    status: { $in: ["PAID", "SHIPPED"] },
    total: { $gte: 100000 },
    createdAt: {
      $gte: ISODate("2026-06-01T00:00:00Z"),
      $lt: ISODate("2026-07-01T00:00:00Z")
    }
  }
}
~~~

Fields at the same level combine with logical **AND**. Use `$or` for alternative conditions:

~~~javascript
{
  $match: {
    tenantId: "T-A",
    $or: [
      { status: "PAID" },
      { status: "SHIPPED" }
    ]
  }
}
~~~

Compare **BSON Date to BSON Date** and numbers to numbers; do not convert dates to strings before filtering if the actual requirement is a time range.

## 2. Practice Dataset

Use the `agg_match_lab.orders` collection with nine orders across two tenants. The dataset makes it easy to verify filter results visually.

> **Run in a lab only.** The script assumes an empty collection. If re-run, fixed `_id` values will cause duplicate key errors; choose a new lab database/collection or intentionally reset the exact fixture—do not drop shared databases.

~~~javascript
const lab = db.getSiblingDB("agg_match_lab")

lab.orders.insertMany([
  {
    _id: "O-101", tenantId: "T-A", status: "PAID",
    createdAt: ISODate("2026-06-01T08:00:00Z"),
    region: "HN", customerId: "C-1", total: 320000,
    items: [
      { sku: "BK-01", qty: 2, price: 120000 },
      { sku: "PN-02", qty: 8, price: 10000 }
    ]
  },
  {
    _id: "O-102", tenantId: "T-A", status: "PAID",
    createdAt: ISODate("2026-06-03T09:00:00Z"),
    region: "HN", customerId: "C-2", total: 140000,
    items: [{ sku: "PN-02", qty: 14, price: 10000 }]
  },
  {
    _id: "O-103", tenantId: "T-A", status: "CANCELLED",
    createdAt: ISODate("2026-06-04T10:00:00Z"),
    region: "SG", customerId: "C-3", total: 90000,
    items: [{ sku: "BK-03", qty: 1, price: 90000 }]
  },
  {
    _id: "O-104", tenantId: "T-A", status: "PAID",
    createdAt: ISODate("2026-06-08T11:00:00Z"),
    region: "SG", customerId: "C-1", total: 800000,
    items: [
      { sku: "BK-01", qty: 5, price: 120000 },
      { sku: "BK-03", qty: 2, price: 100000 }
    ]
  },
  {
    _id: "O-105", tenantId: "T-B", status: "PAID",
    createdAt: ISODate("2026-06-01T12:00:00Z"),
    region: "HN", customerId: "C-4", total: 250000,
    items: [{ sku: "BK-01", qty: 2, price: 125000 }]
  },
  {
    _id: "O-106", tenantId: "T-A", status: "CREATED",
    createdAt: ISODate("2026-06-10T13:00:00Z"),
    region: "HN", customerId: "C-5", total: 200000,
    items: [{ sku: "PN-02", qty: 20, price: 10000 }]
  },
  {
    _id: "O-107", tenantId: "T-A", status: "PAID",
    createdAt: ISODate("2026-06-15T14:00:00Z"),
    region: "SG", customerId: "C-2", total: 460000,
    items: [
      { sku: "BK-01", qty: 3, price: 120000 },
      { sku: "PN-02", qty: 10, price: 10000 }
    ]
  },
  {
    _id: "O-108", tenantId: "T-B", status: "CANCELLED",
    createdAt: ISODate("2026-06-18T15:00:00Z"),
    region: "SG", customerId: "C-6", total: 650000,
    items: [{ sku: "BK-03", qty: 5, price: 130000 }]
  },
  {
    _id: "O-109", tenantId: "T-A", status: "PAID",
    createdAt: ISODate("2026-07-01T08:00:00Z"),
    region: "HN", customerId: "C-7", total: 90000,
    items: [{ sku: "BK-03", qty: 1, price: 90000 }]
  }
])

lab.orders.find(
  {},
  { _id: 1, tenantId: 1, status: 1, createdAt: 1, total: 1 }
).sort({ _id: 1 })
~~~

Define a filter variable used throughout the lesson:

~~~javascript
const start = ISODate("2026-06-01T00:00:00Z")
const end = ISODate("2026-07-01T00:00:00Z")

const paidJuneTenantA = {
  tenantId: "T-A",
  status: "PAID",
  createdAt: { $gte: start, $lt: end }
}
~~~

The filter selects **O-101, O-102, O-104, O-107**. It excludes O-103 (CANCELLED), O-105 (different tenant), O-106 (CREATED), O-108 (different tenant), and O-109 (already in July). The result numbers in subsequent sections are only valid for the unmodified **fixture**.

## 3. Filtering Early Reduces the Data Flowing Through the Pipeline

### 3.1. A Pipeline with a Late Filter

~~~javascript
lab.orders.aggregate([
  {
    $project: {
      tenantId: 1, status: 1, createdAt: 1,
      region: 1, total: 1,
      totalWithNoChange: { $add: ["$total", 0] }
    }
  },
  { $match: paidJuneTenantA },
  {
    $group: {
      _id: "$region",
      revenue: { $sum: "$totalWithNoChange" },
      orderCount: { $sum: 1 }
    }
  }
])
~~~

If the server executes the projection on many documents before filtering, it computes `totalWithNoChange` for documents that get discarded. However, MongoDB **can automatically push independent predicates ahead of projection**; you should not conclude solely from the written order that every document definitely went through projection. Even so, expressing the intent to filter early in the pipeline makes it easier to read and maintain.

### 3.2. Put `$match` First Whenever Possible

~~~javascript
lab.orders.aggregate([
  { $match: paidJuneTenantA },
  {
    $project: {
      region: 1,
      totalWithNoChange: { $add: ["$total", 0] }
    }
  },
  {
    $group: {
      _id: "$region",
      revenue: { $sum: "$totalWithNoChange" },
      orderCount: { $sum: 1 }
    }
  },
  { $sort: { revenue: -1 } }
])
~~~

Expected result:

| `_id` / region | `revenue` | `orderCount` |
|---|---:|---:|
| `"SG"` | 1,260,000 | 2 (O-104, O-107) |
| `"HN"` | 460,000 | 2 (O-101, O-102) |

Before `$group`, only **4 documents** remain instead of the **9 documents** in the fixture. With large datasets, narrowing down early can significantly reduce the number of documents passed between stages.

### 3.3. Use Half-Open Time Intervals `[start, end)`

~~~javascript
createdAt: {
  $gte: ISODate("2026-06-01T00:00:00Z"),
  $lt: ISODate("2026-07-01T00:00:00Z")
}
~~~

Writing **start inclusive, end exclusive** avoids boundary bugs when timestamps have millisecond precision, avoids computing "23:59:59.999", and suits index range scans. If the reporting period is defined in Vietnam time, local boundaries must be accurately converted to UTC.

Do not convert dates to strings for every document if the goal is simply a range:

~~~javascript
// Can prevent direct B-tree range index optimization.
{
  $match: {
    $expr: {
      $eq: [
        { $dateToString: { format: "%Y-%m", date: "$createdAt" } },
        "2026-06"
      ]
    }
  }
}
~~~

A computed expression on a field can make it **difficult for the server to utilize an existing B-tree index on `createdAt`** for filtering. When a semantically equivalent option exists, prefer a range query on the native BSON Date field.

## 4. `$match` at the Start of a Pipeline and Indexes

A `$match` placed at the beginning of a pipeline can be processed similarly to a `find()` **query filter**. When a suitable index exists and the planner chooses it, MongoDB can read the required index keys instead of scanning the entire collection.

### 4.1. Single-Field Index

~~~javascript
const lab = db.getSiblingDB("agg_match_lab")

lab.orders.createIndex(
  { status: 1 },
  { name: "ix_status" }
)

lab.orders.aggregate([
  { $match: { status: "PAID" } },
  { $group: { _id: "$region", count: { $sum: 1 } } }
])
~~~

The planner **may** use `ix_status` to fetch PAID orders before grouping, but **having an index does not guarantee `IXSCAN`**:

- If PAID makes up nearly the whole collection, `COLLSCAN` may be cheaper.
- If the collection is small, sequential scanning is sometimes cheaper than index traversal + fetch.
- If the index or collation does not match the filter, the planner may choose a different path.
- If multiple fields outside the index are needed, it may have to `FETCH` the original documents.
- Plan cache, statistics, and query structure also influence selection.

**Evaluate with `explain` on representative data**, rather than assuming that putting `$match` at the start of a pipeline means the server always uses an index.

### 4.2. Compound Indexes for Multiple Conditions

A report query filters **tenant**, **status**, **createdAt range**, and then sorts by date descending:

~~~javascript
lab.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "ix_tenant_status_createdAt_desc" }
)

lab.orders.aggregate([
  { $match: paidJuneTenantA },
  { $sort: { createdAt: -1 } },
  { $project: { _id: 1, region: 1, total: 1, createdAt: 1 } }
])
~~~

The first two fields in the index have **equality** conditions, while `createdAt` has both a **range** and a **descending sort**. With a suitable index, the planner has the opportunity to bound documents and preserve order from the index instead of running a separate in-memory sort. However, check the actual `explain` because cost also depends on match count and reading non-indexed fields.

### 4.3. Compound Index Prefixes

The index:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1 }
~~~

typically aligns well with:

~~~javascript
{ tenantId: "T-A" }

{ tenantId: "T-A", status: "PAID" }

{
  tenantId: "T-A",
  status: "PAID",
  createdAt: { $gte: start, $lt: end }
}
~~~

Conversely, a query with only `status:"PAID"` and **no tenantId filter** struggles to exploit this index via prefix optimization. The server can sometimes still perform a wide index scan, but you should not assume a compound index automatically optimizes arbitrary field subsets.

The **Equality → Sort → Range (ESR)** guideline is useful when designing multi-condition indexes, though selectivity, data distribution, and actual sorts must be considered. In some workloads with an extremely selective range, **ERS** order may perform better. Measure against your workload rather than applying a rigid order blindly.

### 4.4. Comparing Queries and Candidate Indexes

| Pipeline/filter | Candidate index | Reason |
|---|---|---|
| `$match: {status:"PAID"}` | `{status:1}` | Equality on status. |
| `$match: {tenantId:"T-A",status:"PAID"}` | `{tenantId:1,status:1}` | Compound equality. |
| `$match` tenant/status/date + `$sort` createdAt desc | `{tenantId:1,status:1,createdAt:-1}` | Equality prefix, range/sort on date. |
| `$match: {"items.sku":"BK-01"}` | `{"items.sku":1}` | Multikey index on array field. |
| `$match: {region:"HN"}` | `{region:1}` | Equality on region; create only if workload needs it. |
| `$match` on year created by `$addFields` | Index `{createdAt:1}` does not directly index computed year | Usually filter range on source date if equivalent. |

Creating too many indexes increases insert/update/delete overhead and storage size. A useful index serves a **recurring access pattern**, not every field that appears once in a pipeline.

## 5. Combining `$match` with `$sort` and `$limit`

A report often needs the **newest PAID orders** for a tenant:

~~~javascript
lab.orders.aggregate([
  { $match: { tenantId: "T-A", status: "PAID" } },
  { $sort: { createdAt: -1 } },
  { $limit: 3 },
  {
    $project: {
      _id: 1, createdAt: 1, region: 1, total: 1
    }
  }
])
// Sample data: O-109, O-107, O-104.
~~~

With the compound index `{tenantId:1,status:1,createdAt:-1}`, the planner can both locate the tenant/status subset and walk in createdAt order. `$limit:3` keeps the final result small; if the plan exploits the index sort efficiently, the number of documents needing retrieval can also drop significantly.

### 5.1. Sorting Early and Matching Late Can Be Wasteful

~~~javascript
lab.orders.aggregate([
  { $sort: { createdAt: -1 } },
  { $match: { tenantId: "T-A", status: "PAID" } },
  { $limit: 3 }
])
~~~

Semantically, if the filter only uses source fields and no stage alters documents between the two steps, MongoDB can **optimize the order of `$sort` and `$match`** to reduce the data that needs sorting. Do not evaluate performance solely by reading the source order; inspect the **optimized plan**.

Explicitly writing `$match` before `$sort` in code is usually clearer. More importantly, create an **index matching both filter and sort**, because even after reordering stages, lacking an index can still force the server to scan/sort large volumes of data.

### 5.2. `$limit` Before `$match` Changes the Result

Compare:

~~~javascript
// A: take the three newest orders among PAID orders for tenant T-A.
lab.orders.aggregate([
  { $match: { tenantId: "T-A", status: "PAID" } },
  { $sort: { createdAt: -1 } },
  { $limit: 3 }
])
// O-109, O-107, O-104.

// B: take the three newest orders across the whole collection,
// then keep only PAID orders belonging to T-A.
lab.orders.aggregate([
  { $sort: { createdAt: -1 } },
  { $limit: 3 },
  { $match: { tenantId: "T-A", status: "PAID" } }
])
// O-109, O-107 (O-108 made the top 3 but was filtered out).
~~~

Pipeline B is not equivalent to A because `$limit` truncated the dataset **before filtering**. The optimizer cannot arbitrarily swap `$match` past `$limit` if doing so changes the result. This is a key example that "filtering early" must preserve **semantics**.

### 5.3. Sort + Limit Can Be Coalesced

MongoDB has an optimization that coalesces `$sort` and `$limit` in appropriate cases, allowing the sort to keep only the required number of results rather than holding all data. However, this optimization does not replace an index: if an index supports both sort and match, the engine can avoid a memory-intensive blocking sort.

If the pipeline has `$skip` followed by `$limit`, consider that a **deep skip** may still have to traverse many index keys/documents. For very deep pagination, **keyset pagination** based on `createdAt` plus a tie-breaker key like `_id` is often worth considering instead of continuously increasing `$skip`.

### 5.4. What About Sorting on a Computed Field?

~~~javascript
lab.orders.aggregate([
  { $match: paidJuneTenantA },
  { $addFields: { shippingScore: { $multiply: ["$total", 0.01] } } },
  { $sort: { shippingScore: -1 } },
  { $limit: 3 }
])
~~~

An index on `total` does not automatically provide the ordering of `shippingScore` for arbitrary expressions. If the sort depends on a **newly computed field in the pipeline**, the values usually must be computed before sorting, unless the query structure/optimizer supports an equivalent transformation. Pushing `$match` on source fields earlier helps limit the number of documents that need scoring/sorting.

## 6. How Far Can the MongoDB Optimizer Push `$match` Earlier?

MongoDB performs **pipeline optimizations** before execution. For example, a `$match` after `$project` or `$addFields` can be split into multiple independent filters and each piece moved ahead of stages that **do not create or overwrite fields the filter depends on**.

### 6.1. Example: Splitting a Filter by Dependency

~~~javascript
lab.orders.aggregate([
  {
    $addFields: {
      discountAdjustedTotal: {
        $multiply: ["$total", 0.95]
      }
    }
  },
  {
    $match: {
      status: "PAID",
      tenantId: "T-A",
      discountAdjustedTotal: { $gte: 200000 }
    }
  }
])
~~~

The three conditions have different dependencies:

| Predicate | Depends on previous computed stage? | Ability to push earlier |
|---|---|---|
| `status = "PAID"` | No | Can be pushed before `$addFields` and use an index. |
| `tenantId = "T-A"` | No | Can be pushed before `$addFields`. |
| `discountAdjustedTotal >= 200000` | **Yes** | Must stay after computing this field, barring a special equivalence proven by the optimizer. |

The optimizer can split the filter into a `status`/`tenantId` filter earlier and a computed-total filter after `$addFields`. When writing code, you do not have to cram every predicate into one `$match` if doing so hurts clarity:

~~~javascript
lab.orders.aggregate([
  {
    $match: {
      tenantId: "T-A",
      status: "PAID"
    }
  },
  {
    $addFields: {
      discountAdjustedTotal: { $multiply: ["$total", 0.95] }
    }
  },
  {
    $match: {
      discountAdjustedTotal: { $gte: 200000 }
    }
  }
])
~~~

The second version clearly expresses **two phases**: filter on existing fields first, compute derived data next, then filter on the computed result.

### 6.2. `$project` Dropping Fields Also Changes Where Filters Can Sit

~~~javascript
lab.orders.aggregate([
  { $project: { region: 1, total: 1 } },
  { $match: { status: "PAID" } }
])
~~~

Looking strictly at the declared data flow order, `status` was dropped by the projection, so the subsequent filter no longer sees `status` as a source field. However, the optimizer **may push** the `status` filter ahead of the projection if proven safe. You should not write pipelines relying on the optimizer to rescue hard-to-read logic; the clean way is:

~~~javascript
lab.orders.aggregate([
  { $match: { status: "PAID" } },
  { $project: { region: 1, total: 1 } }
])
~~~

In code reviews, treat **field dependency** as the first question: at the point of filtering, is that field a source field, a dropped field, or a newly computed field?

### 6.3. If `$addFields` Overwrites a Field, the Filter Cannot Be Moved Blindly

~~~javascript
lab.orders.aggregate([
  {
    $set: {
      status: { $toUpper: "$status" }
    }
  },
  {
    $match: {
      status: "PAID"
    }
  }
])
~~~

Here `status` after `$set` is a **transformed value**, not simply the source field. Pushing `$match` before `$set` could change the result on source documents containing `"paid"`. Therefore, you must not reorder it just to try using an index on `status` if the actual data and comparison rules differ.

If you want efficient and consistent queries, normalize data on write, use an appropriate collation/index, or design a canonical field instead of forcing every pipeline to recompute normalization on read.

### 6.4. Between Independent `$match` Stages, the Optimizer Can Coalesce

~~~javascript
lab.orders.aggregate([
  { $match: { tenantId: "T-A" } },
  { $match: { status: "PAID" } },
  { $match: { createdAt: { $gte: start, $lt: end } } }
])
~~~

Consecutive `$match` stages can be **coalesced** into an equivalent condition. Thus splitting filters across several stages for maintainability does not necessarily increase collection scan passes. However, do not generalize that MongoDB always merges **every** filter across `$unwind`, `$group`, or `$limit`; dependencies and semantic boundaries govern this.

### 6.5. The Optimizer Is Not an API Contract for Specific Stage Ordering

MongoDB can change rewrite rules across versions, query engines, and scenarios. The documentation explains common optimizations, but **does not guarantee that pipeline source code stays untouched or always transforms into one predetermined optimized form**. Inspect `explain` on the **running server** and benchmark performance with sufficiently large data.

## 7. `$match` Before vs. After `$unwind`: Easy to Change the Meaning

`$unwind` turns **one document containing an array** into **multiple pipeline documents**, each carrying one array element. Placing a filter before or after `$unwind` can return different result units.

### 7.1. Filtering Before Unwind: Selecting Orders That Have a Target Item

~~~javascript
lab.orders.aggregate([
  {
    $match: {
      "items.sku": "BK-01"
    }
  },
  {
    $unwind: "$items"
  },
  {
    $project: {
      _id: 1,
      sku: "$items.sku",
      qty: "$items.qty"
    }
  }
])
~~~

The first `$match` selects **orders** with *at least one* BK-01 item. On the fixture, those orders are **O-101, O-104, O-105, O-107**. But the subsequent `$unwind` splits **all items** of those orders; the output still includes PN-02/BK-03 SKUs from those matching orders, not just BK-01.

This is a very common trap: **filtering parent documents before `$unwind` is not equivalent to filtering elements after `$unwind`**.

### 7.2. Filtering After Unwind: Selecting Individual BK-01 Item Lines

~~~javascript
lab.orders.aggregate([
  { $unwind: "$items" },
  { $match: { "items.sku": "BK-01" } },
  {
    $project: {
      _id: 1,
      sku: "$items.sku",
      qty: "$items.qty"
    }
  }
])
~~~

Here `$match` runs on **each unwound line**, keeping only BK-01 lines. The result contains the BK-01 items from O-101, O-104, O-105, and O-107.

However, a pipeline that only unwinds and then matches may have to process all items before filtering. You can combine two `$match` stages to achieve both correct semantics and reduced input.

### 7.3. Combining Pre-Unwind and Post-Unwind Filters

~~~javascript
lab.orders.aggregate([
  // Pre-select orders that may contain the target SKU.
  { $match: { "items.sku": "BK-01" } },

  // Split items within the selected orders.
  { $unwind: "$items" },

  // Keep only the exact BK-01 items.
  { $match: { "items.sku": "BK-01" } },

  {
    $group: {
      _id: "$items.sku",
      qtySold: { $sum: "$items.qty" },
      lineCount: { $sum: 1 }
    }
  }
])
// On the fixture: _id BK-01, qtySold 12, lineCount 4.
~~~

Explanation: 2 + 5 + 2 + 3 = **12 units of BK-01** across four orders. The pre-unwind `$match` can use a **multikey index** on `items.sku`, while the post-unwind `$match` keeps the exact line items for aggregation.

If you need to filter for **a single item satisfying multiple conditions simultaneously**, use `$elemMatch` in the pre-filter:

~~~javascript
lab.orders.aggregate([
  {
    $match: {
      items: {
        $elemMatch: {
          sku: "BK-01",
          qty: { $gte: 3 }
        }
      }
    }
  },
  { $unwind: "$items" },
  {
    $match: {
      "items.sku": "BK-01",
      "items.qty": { $gte: 3 }
    }
  }
])
// In the fixture: BK-01 in O-104 and O-107.
~~~

Before unwind, two separate dot-notation predicates can match **two different items**; `$elemMatch` guarantees the same item. After unwind, each pipeline document contains **one item**, so the predicates on `items.sku` and `items.qty` describe that exact item.

### 7.4. Can the Post-Unwind `$match` Be Removed?

Only when the output requires **all items** of orders containing the target SKU. If the output is a **BK-01 line** report, removing the post-unwind filter will mix in PN-02/BK-03. Wanting fewer stages must never take priority over **data semantics**.

### 7.5. Can the Optimizer Push a Post-Unwind Filter Earlier?

MongoDB has certain rewrites involving `$unwind`, `$lookup`, and subsequent `$match` stages. However, a filter on unwound elements **cannot in general** be swapped with a pre-filter while preserving line counts/output. Do not rely on the optimizer to "guess" which items to filter: write a pipeline that clearly reflects the boundary between **parent documents** and **child elements**, then use explain to confirm the plan.

## 8. `$match` Before vs. After `$group`: Two Different Kinds of Conditions

`$group` can produce **summary documents**, with `_id` and accumulator values. After that stage, any source field not explicitly carried forward no longer exists.

### 8.1. Filtering on Source Documents Before `$group`

Requirement: revenue per region from **June PAID orders of T-A**.

~~~javascript
lab.orders.aggregate([
  { $match: paidJuneTenantA },
  {
    $group: {
      _id: "$region",
      revenue: { $sum: "$total" },
      orderCount: { $sum: 1 }
    }
  },
  { $sort: { revenue: -1 } }
])
~~~

The initial `$match` excludes out-of-scope orders. `$group` only computes over the four valid orders.

### 8.2. Filtering **Aggregated Values** After `$group`

If a requirement is added: "only return regions whose June PAID revenue for T-A is **over 500,000**":

~~~javascript
lab.orders.aggregate([
  { $match: paidJuneTenantA },
  {
    $group: {
      _id: "$region",
      revenue: { $sum: "$total" },
      orderCount: { $sum: 1 }
    }
  },
  { $match: { revenue: { $gt: 500000 } } },
  { $sort: { revenue: -1 } }
])
// Only region SG, revenue 1,260,000.
~~~

`revenue` **only exists after `$group`**. You cannot move `{revenue:{$gt:500000}}` to the start of the pipeline and expect an index on `orders.revenue` to help, because it is an **aggregated sum across multiple orders** rather than a source field.

### 8.3. Do Not Filter Individual Orders Above the Threshold Instead of the Group Sum

Two different statements:

~~~text
A. "Only group regions whose TOTAL revenue > 500,000."
B. "Take only INDIVIDUAL orders with total > 500,000 and then group."
~~~

Pipeline A:

~~~javascript
lab.orders.aggregate([
  { $match: paidJuneTenantA },
  { $group: { _id: "$region", revenue: { $sum: "$total" } } },
  { $match: { revenue: { $gt: 500000 } } }
])
~~~

Pipeline B:

~~~javascript
lab.orders.aggregate([
  {
    $match: {
      ...paidJuneTenantA,
      total: { $gt: 500000 }
    }
  },
  { $group: { _id: "$region", revenue: { $sum: "$total" } } }
])
~~~

In the fixture, pipeline B only counts O-104 in SG with 800,000; it drops O-107 even though O-107 contributes 460,000 to SG's revenue. Pipeline A gives SG 1,260,000. **Never turn a group-total filter into a per-document filter** just to push it earlier/use an index.

### 8.4. Filtering on the Grouping Key Can Optimize Differently from Filtering Accumulators

Sometimes a filter after `$group` only uses **`_id`, the grouping key**, and can be equivalent to filtering the source field before grouping, such as only region HN. The optimizer can recognize certain cases and push the appropriate predicate. However, if grouping creates keys via expressions or involves empty/missing semantics, equivalence must be examined carefully.

Example of proactive early filtering:

~~~javascript
lab.orders.aggregate([
  {
    $match: {
      ...paidJuneTenantA,
      region: "HN"
    }
  },
  {
    $group: {
      _id: "$region",
      revenue: { $sum: "$total" }
    }
  }
])
~~~

If the goal is solely the HN group from the start, this reduces input. If you need to **rank all groups first and then pick HN**, stage order can carry different semantics.

## 9. `$match` After `$lookup` and Its Relationship with Two-Collection Indexes

`$lookup` typically pulls data from another collection to attach to input documents. There are **two distinct places to filter**:

1. Filtering **source** documents before `$lookup`, which can use indexes on the source collection.
2. Filtering data in the **looked-up collection**, using an appropriate pipeline/condition, which can use indexes on the other collection.

### 9.1. Reducing Input Before Joining

Suppose a `customers` collection stores `_id`, `name`, `tier`, while `orders.customerId` is the customer ID. You can filter the four June PAID orders of T-A before looking up the customer:

~~~javascript
lab.orders.aggregate([
  { $match: paidJuneTenantA },
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  },
  { $unwind: "$customer" },
  {
    $project: {
      _id: 1,
      total: 1,
      customerName: "$customer.name"
    }
  }
])
~~~

The index `{tenantId:1,status:1,createdAt:-1}` can support **filtering orders**; the default `_id` index on `customers` can support **lookup by foreignField**. Two indexes serve **two different sides**; no single index on orders automatically optimizes queries into customers.

If you also need to filter by `customers.tier`, you may need to design `$lookup.pipeline` with appropriate indexes, depending on the join conditions and server version. Inside a `$lookup` pipeline, a `$match` using `$expr` to compare a field in the foreign collection against a `let` variable has specific **index limitations** (e.g., field–constant, variables resolved to constants, and certain multikey restrictions). Do not assume every `$expr` inside a lookup uses an index.

### 9.2. A Pre-Match Cannot Filter a Field That Only Exists After Lookup

~~~javascript
// Customer tier comes from the customers collection.
lab.orders.aggregate([
  { $match: paidJuneTenantA },
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  },
  { $unwind: "$customer" },
  { $match: { "customer.tier": "GOLD" } }
])
~~~

The `"customer.tier"` filter does not apply to source `orders` because that field only appears after the join. Pushing it to the top of the pipeline would be wrong. A performance solution can be **filtering tier early right on the foreign side** using pipeline-form `$lookup` in equivalent cases; check join semantics, especially when `preserveNullAndEmptyArrays`, left-outer joins, and cardinality change the result.

### 9.3. Some Stages Have Rules Requiring Them to Be First

Not every pipeline allows `$match` at position 0. For example:

- `$geoNear` is a stage that must come first under normal syntax restrictions; place geospatial conditions and applicable predicates inside `$geoNear`'s `query` option when supported.
- `$search` (MongoDB Atlas Search) and `$vectorSearch` have specific placement and syntax constraints; typically they must be the first stage in applicable pipelines, or `$vectorSearch` has supported `filter` options.
- For `$text` in aggregation, a `$match` containing `$text` must be the **first stage** in the pipeline per the rules; you cannot arbitrarily place `$text` after other stages.

Therefore, the general rule is **filter at the earliest point that is permitted and semantically equivalent**, rather than "`$match` must always be the absolute first stage."

## 10. `$facet` and Shared Filtering Before Multiple Branches

`$facet` runs multiple sub-pipelines on the **same input document set**, often used to return both summary statistics and a list. If every branch needs the same tenant/time scope, filtering before `$facet` reduces the input volume for all branches.

~~~javascript
lab.orders.aggregate([
  { $match: paidJuneTenantA },
  {
    $facet: {
      summary: [
        {
          $group: {
            _id: null,
            revenue: { $sum: "$total" },
            count: { $sum: 1 }
          }
        }
      ],
      byRegion: [
        {
          $group: {
            _id: "$region",
            revenue: { $sum: "$total" }
          }
        },
        { $sort: { revenue: -1 } }
      ],
      recent: [
        { $sort: { createdAt: -1 } },
        { $limit: 2 },
        { $project: { _id: 1, createdAt: 1, total: 1 } }
      ]
    }
  }
])
~~~

A `$match` outside `$facet` has the opportunity to use indexes on the source collection. According to MongoDB documentation, if `$facet` is the **first stage**, it may have to perform a **collection scan**; when an upstream `$match` or `$sort` already exploits an index, `$facet` receives results from upstream instead of initiating a separate scan.

### 10.1. Do Not Share a Filter If Branches Need Different Datasets

If the `summary` branch wants **all statuses**, while `recentPaid` only wants PAID, placing `$match:{status:"PAID"}` outside the facet will break `summary`. In that case:

~~~javascript
lab.orders.aggregate([
  // Conditions truly shared by all branches:
  {
    $match: {
      tenantId: "T-A",
      createdAt: { $gte: start, $lt: end }
    }
  },
  {
    $facet: {
      allStatuses: [
        { $group: { _id: "$status", count: { $sum: 1 } } }
      ],
      paid: [
        { $match: { status: "PAID" } },
        { $group: { _id: null, revenue: { $sum: "$total" } } }
      ]
    }
  }
])
~~~

**Shared filter early, specific filter inside each branch** is an easy-to-follow model. A `$match` inside a `$facet` sub-pipeline does not "restart" a collection scan from source indexes the way an independent pipeline does: it receives **documents distributed by the facet**.

### 10.2. Facet Memory Limits

`$facet` has its own memory/output size limits; filtering early reduces input, but does not automatically eliminate all risks when each branch generates overly large result arrays. Pagination, output limits, and execution monitoring are essential, especially when analyzing large collections.

## 11. Using `explain` to Verify Whether `$match` Uses an Index

**Measure and observe**, rather than guessing from the pipeline. In `mongosh`, use:

~~~javascript
const lab = db.getSiblingDB("agg_match_lab")

const pipeline = [
  {
    $match: {
      tenantId: "T-A",
      status: "PAID",
      createdAt: {
        $gte: ISODate("2026-06-01T00:00:00Z"),
        $lt: ISODate("2026-07-01T00:00:00Z")
      }
    }
  },
  { $sort: { createdAt: -1 } },
  { $project: { _id: 1, createdAt: 1, region: 1, total: 1 } }
]

printjson(
  lab.orders.explain("executionStats").aggregate(pipeline)
)
~~~

`executionStats` requests execution statistics in addition to the plan. `queryPlanner` mainly shows the path selected by the planner; `allPlansExecution` can provide data on multiple candidate plans in supported contexts.

### 11.1. Where to Look in Explain?

| Concept | How to interpret |
|---|---|
| **`COLLSCAN`** | Reads documents via a collection scan. Not automatically slow; for very small sets or low-selectivity filters, it can be reasonable. |
| **`IXSCAN`** | Scans index keys using the selected index. |
| **`FETCH`** | Reads full documents from the collection after an index scan when additional fields/checks are needed. |
| **`PROJECTION`** | Selects/computes output fields; exact representation depends on the engine. |
| **`SORT`** | Performs a sort operation in the plan; can be a blocking sort if not served by index order. |
| **`DISTINCT_SCAN`** | A specialized index scan that can be used for certain optimized distinct/group patterns. |
| **`totalKeysExamined`** | Total number of index keys examined in that portion of execution. |
| **`totalDocsExamined`** | Total number of documents read/examined in that portion of execution. |
| **`nReturned`** | Number of documents returned at the corresponding statistics level. |
| **`indexBounds`** | The index key ranges scanned for each field. |

These fields may reside under **`queryPlanner`, `executionStats`, `stages`, `winningPlan`, or nested `queryPlan`**, depending on the pipeline, SBE/classic engine, and version. Some `$group`/`$sort` operations appear as differently named execution stages in newer versions; do not write programs that parse explain via a hardcoded JSON path without checking the server.

### 11.2. How to Read Sample Scenarios

~~~text
Scenario A:
  COLLSCAN
  docsExamined: 1,000,000
  nReturned: 1,200

Scenario B:
  IXSCAN -> FETCH
  keysExamined: 1,350
  docsExamined: 1,210
  nReturned: 1,200
~~~

If these are two **truly equivalent** execution plans measured under identical conditions, plan B can reduce I/O significantly. However, these numbers are **conceptual illustrations**, not explain output generated from the lesson's nine-document fixture. Do not infer that latency drops strictly in proportion to docs examined; cache, network, CPU, index size, contention, and post-match aggregation also play a role.

A plan with `IXSCAN` where `keysExamined` is huge compared to `nReturned` can still perform poorly. For instance, an index only on `status` when 90% of orders are PAID may still scan most of the index and fetch many documents.

### 11.3. Questions to Ask When Reading Explain

1. **Which index** did the server choose? Does it match expectations?
2. Was `$match` on source fields pushed into the **cursor/query plan**, or is it still processed after stages?
3. Is there an expensive `SORT` even though an index exists for ordering?
4. Are many documents being `FETCH`ed? Did projection reduce transferred payload without reducing fetched documents?
5. Is `keysExamined/docsExamined` reasonable relative to `nReturned` and selectivity?
6. On a sharded cluster, does the query **target the right shards** or fan out?
7. Does the plan change when re-run on sufficiently large, production-like data?

### 11.4. Comparing Pipelines Before and After Reordering

~~~javascript
const lab = db.getSiblingDB("agg_match_lab")

const late = [
  { $project: {
      tenantId: 1, status: 1, createdAt: 1,
      total: 1, region: 1
  } },
  { $match: paidJuneTenantA },
  { $group: { _id: "$region", revenue: { $sum: "$total" } } }
]

const early = [
  { $match: paidJuneTenantA },
  { $project: { total: 1, region: 1 } },
  { $group: { _id: "$region", revenue: { $sum: "$total" } } }
]

printjson(lab.orders.explain("executionStats").aggregate(late))
printjson(lab.orders.explain("executionStats").aggregate(early))
~~~

If the optimizer can push `$match` ahead of projection in both pipelines, the plans may look **very similar**. That is a sensible outcome: MongoDB optimized it for you. The value of explicitly writing an early match lies in readability and control, not necessarily seeing a massive change in execution stats in every case.

### 11.5. `hint` to Test a Candidate Index

`aggregate()` supports the `hint` option for the initial collection read in allowed contexts/versions:

~~~javascript
lab.orders.aggregate(
  [
    { $match: paidJuneTenantA },
    { $sort: { createdAt: -1 } }
  ],
  {
    hint: "ix_tenant_status_createdAt_desc"
  }
)
~~~

Or pass hint in explain using the API appropriate for your shell/driver version. **`hint` does not create an index**; if you specify a nonexistent or unsuitable index, the command may fail or perform poorly. The hint option on aggregation applies to the **source collection**, and does not automatically govern indexes chosen inside every `$lookup`/`$unionWith`.

**Do not pin an index based on a single explain:** changing indexes or data volume can make a hint worse than the planner's automatic choice. Use hint only when you have a justified need to control execution and have measured performance.

### 11.6. `allowDiskUse` Is No Substitute for Good Filters/Indexes

Some aggregation stages like `$sort` or `$group` can consume substantial memory; depending on version/configuration, eligible operations can **spill to disk** when permitted. The `allowDiskUse` option and `allowDiskUseByDefault` setting vary by MongoDB version, yet even with spilling, processing millions of unnecessary documents still incurs I/O.

~~~javascript
lab.orders.aggregate(
  [
    { $match: paidJuneTenantA },
    { $group: { _id: "$customerId", total: { $sum: "$total" } } },
    { $sort: { total: -1 } }
  ],
  { allowDiskUse: true }
)
~~~

`allowDiskUse: true` merely permits disk resource usage in supported stages; **it does not replace early filtering, proper indexing, or shrinking the input set**.

## 12. Scenarios Where Indexes Are Not Used as Expected

### 12.1. Low-Selectivity Filters

If 99% of orders have `status:"PAID"`, an index on `status` alone does not eliminate many documents. The planner may reasonably choose a collection scan, or scan the index and still fetch most data.

Conversely, a filter combining `tenantId`, `status`, and a `createdAt` range may select only a small fraction. This explains why compound indexes modeled after **access patterns** often outperform single-field indexes on low-cardinality fields.

### 12.2. Path / BSON Type Mismatches

~~~javascript
// Data uses BSON Date:
{ createdAt: ISODate("2026-06-01T08:00:00Z") }

// Filter below uses a string, not the same BSON type:
{ createdAt: "2026-06-01" }
~~~

An index cannot "fix" data-type semantic mismatches. MongoDB follows BSON comparison rules; cross-type comparisons behave according to operator and type bracketing rules. For date ranges, query using matching Date values.

If legacy data mixes strings and dates in the same field, migrate the schema or handle them separately rather than creating an index and expecting a single range query to understand both types.

### 12.3. Computed Expressions on a Field

~~~javascript
// Direct filter (good candidate for an index on total):
{ $match: { total: { $gte: 500000 } } }

// Compute via expression first, then filter:
{
  $match: {
    $expr: {
      $gte: [
        { $multiply: ["$total", 1.1] },
        550000
      ]
    }
  }
}
~~~

The two conditions may be equivalent within a controlled numeric domain, yet the `$expr` form with multiplication **does not automatically utilize `total` index bounds** like a direct predicate. Some simple `$expr` comparisons can be optimized/index-supported in certain contexts, but you should not generalize that to arbitrary expressions.

Before rewriting, verify **numeric types**, precision/rounding, null/missing behavior, and edge cases; never convert a complex expression into a direct predicate if it alters business logic.

### 12.4. Case-Insensitive Regex and Collation

~~~javascript
// A prefix regex can produce useful index bounds
// on an appropriate string index in certain scenarios.
{ $match: { customerId: /^C-/ } }

// A case-insensitive regex does not automatically leverage a
// case-insensitive collation index the way you might expect.
{ $match: { customerId: /^c-/i } }
~~~

For frequent case-insensitive string queries, consider a **collation with a matching index** or a canonical normalized field. Do not conclude "there is an index on customerId so every regex is fast," especially with unanchored patterns or leading wildcards.

### 12.5. Partial Indexes Only Apply When the Filter Implies the Index Condition

~~~javascript
lab.orders.createIndex(
  { tenantId: 1, createdAt: -1 },
  {
    name: "ix_paid_tenant_date",
    partialFilterExpression: { status: "PAID" }
  }
)
~~~

This index only contains **PAID** orders. The query:

~~~javascript
lab.orders.aggregate([
  {
    $match: {
      tenantId: "T-A",
      status: "PAID",
      createdAt: { $gte: start, $lt: end }
    }
  }
])
~~~

is a candidate for the partial index because it implies `status:"PAID"`. However, a query searching only for `tenantId:"T-A"`, regardless of status, **cannot automatically** use the partial index as a complete data source because it omits CREATED/CANCELLED orders.

**Partial indexes** can reduce index size and query cost where applicable, but evaluate the impact when business statuses change, queries filter multiple statuses, or a plan fails to satisfy index eligibility.

### 12.6. Index Collation and Query Collation

If an index on `customerName` has collation `{locale:"en", strength:2}`, a query comparing strings under a different collation may not use the index to compare strings in the same way. Design collations from **business comparison rules** and pass the matching collation when needed:

~~~javascript
lab.orders.aggregate(
  [{ $match: { customerName: "an" } }],
  { collation: { locale: "en", strength: 2 } }
)
~~~

This example only illustrates syntax; the fixture lacks `customerName`, so it returns no results on current data. Do not create a collated index and assume every query switches comparison rules by default.

### 12.7. Multikey Indexes and Multiple Conditions on Arrays

~~~javascript
lab.orders.createIndex(
  { "items.sku": 1, "items.qty": 1 },
  { name: "ix_item_sku_qty" }
)
~~~

Two dot-notation conditions:

~~~javascript
{
  $match: {
    "items.sku": "BK-01",
    "items.qty": { $gte: 3 }
  }
}
~~~

can match **two different items** within the same order. If business logic requires the same item, use:

~~~javascript
{
  $match: {
    items: {
      $elemMatch: {
        sku: "BK-01",
        qty: { $gte: 3 }
      }
    }
  }
}
~~~

`$elemMatch` both ensures correct semantics and helps the planner **intersect/combine compound multikey index bounds** when predicates share the array boundary. Multikey indexes have limitations regarding covered queries and compound parallel arrays; do not assume they fit every deeply nested array scenario.

### 12.8. Indexes Do Not Replace Authorization and Tenant Filtering

In a multi-tenant application, every query must filter `tenantId` from a **trusted authorization context**, rather than blindly trusting an arbitrary tenantId sent by a client. Placing a tenant `$match` early helps query targeting and reduces input, but **does not replace authorization**. If a lookup/group branch in a pipeline omits the tenant filter, a fast index does not make the query safe for data isolation.

### 12.9. Sharding and Shard-Key Targeting

On a sharded collection, queries with conditions matching the **shard key** can be routed to only the necessary shards instead of fanning out to all shards. An early `$match` containing a shard-key predicate can be crucial for performance. Still, the effect depends on the shard key pattern, range/hashed routing, chunk distribution, version, and pipeline optimizer.

In `explain` for a sharded aggregation, inspect **which shards participate**, `SHARD_MERGE`, or related stages rather than looking only at `IXSCAN` on one shard. Do not assume filtering by `tenantId` is always targeted if the collection is not sharded by tenantId or the field does not suffice for the shard key.

## 13. `$match` Semantics: More Limits and Pitfalls to Know

### 13.1. Query Predicates Are Not Aggregation Expressions

In `$match`, the following syntax uses a **query operator**:

~~~javascript
{
  $match: {
    total: { $gte: 500000 }
  }
}
~~~

To compare **two fields within the same document** or compute values using aggregation expressions, use `$expr`:

~~~javascript
{
  $match: {
    $expr: {
      $gt: ["$total", "$creditLimit"]
    }
  }
}
~~~

The second filter means "this document's total is greater than its creditLimit." `"$total"` is a **field path expression** in the aggregation language, distinct from the `total` key in query syntax. Depending on the expression, `$expr` may not use index bounds like a direct predicate; inspect explain.

### 13.2. Do Not Put `$project` Expressions into `$match` as Query Syntax

Wrong intent:

~~~javascript
// $toUpper is not how you declare a direct field predicate like this.
{
  $match: {
    status: { $toUpper: "$status" }
  }
}
~~~

Correct when the goal is comparing status after uppercasing:

~~~javascript
{
  $match: {
    $expr: {
      $eq: [{ $toUpper: "$status" }, "PAID"]
    }
  }
}
~~~

However, if data is already normalized to uppercase status, a direct filter `{status:"PAID"}` is usually much easier to index. If the requirement is case-insensitive string matching with index support, consider collation/canonical keys instead of recomputing `$toUpper` on every document.

### 13.3. `$match` Does Not Mean SQL HAVING in Every Position

In SQL, we distinguish WHERE (filtering source rows) and HAVING (filtering groups). MongoDB aggregation uses the **same name `$match`**:

~~~javascript
// Similar to WHERE: filters orders before grouping.
{ $match: { status: "PAID" } }

// Similar to HAVING: filters results after $group.
{ $match: { revenue: { $gt: 500000 } } }
~~~

The difference lies in **position and the shape of documents** flowing through the pipeline, not the stage name. An initial `$match` searches `status` in orders; a post-group `$match` checks `revenue` created by grouping.

### 13.4. Null, Missing, and Array Paths

In the MongoDB query language:

~~~javascript
{ $match: { optionalField: null } }
~~~

typically matches documents where the field is **explicitly null** or **missing**, depending on path/context. If the goal is "field does not exist":

~~~javascript
{ $match: { optionalField: { $exists: false } } }
~~~

If the goal is "field exists and is BSON null":

~~~javascript
{ $match: { optionalField: { $type: "null" } } }
~~~

With paths traversing arrays, multiple dot-notation conditions can be satisfied by **different elements**. To require the same element, use `$elemMatch` as in section 7. This is not merely a performance/index issue, but a matter of filter **correctness**.

### 13.5. Operators That Cannot Be Used Arbitrarily in `$match`

`$match` supports many query operators, but has restrictions:

- **`$where`** cannot be used in `$match`.
- **`$near` and `$nearSphere`** cannot be used in `$match` in the usual way; check `$geoNear` or supported geospatial predicates like `$geoWithin`, depending on the goal.
- **`$text` in `$match` must be in the first stage** per aggregation text search rules; do not place it arbitrarily after `$project` or `$group`.
- Certain specialized Atlas search stages have their own placement constraints, as mentioned in section 9.

Knowing these syntax restrictions prevents turning a "move match first" tip into a pipeline the server rejects.

### 13.6. `$match` with Expressions on Computed Field Results

Example computing order value after discount:

~~~javascript
lab.orders.aggregate([
  {
    $match: {
      tenantId: "T-A",
      status: "PAID"
    }
  },
  {
    $addFields: {
      amountAfterDiscount: {
        $multiply: ["$total", 0.9]
      }
    }
  },
  {
    $match: {
      amountAfterDiscount: { $gte: 300000 }
    }
  },
  {
    $project: {
      _id: 1, total: 1, amountAfterDiscount: 1
    }
  }
])
~~~

The two `$match` stages have **different roles**: the first can leverage a compound index on tenant/status; the second must inspect the computed field to return orders meeting the threshold. This is a well-structured pipeline even when not every condition can be pushed to the top.

## 14. Writing Efficient Pipelines with the MongoDB Java Sync Driver

In the Java Sync Driver, `MongoCollection.aggregate()` takes a list of `Bson` stages. Builders such as `Aggregates.match`, `Filters.and`, `Filters.eq`, `Filters.gte`, `Filters.lt`, and `Indexes.compoundIndex` construct syntax equivalent to `mongosh` with compile-time API type checking.

### 14.1. Translating `$match` + `$sort` + `$limit` to Java

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.time.Instant;
import java.util.Arrays;
import java.util.Date;
import java.util.List;

import static com.mongodb.client.model.Aggregates.limit;
import static com.mongodb.client.model.Aggregates.match;
import static com.mongodb.client.model.Aggregates.project;
import static com.mongodb.client.model.Aggregates.sort;
import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.gte;
import static com.mongodb.client.model.Filters.lt;
import static com.mongodb.client.model.Projections.fields;
import static com.mongodb.client.model.Projections.include;
import static com.mongodb.client.model.Sorts.descending;

// Assume database is a MongoDatabase pointing to "agg_match_lab".
MongoCollection<Document> orders = database.getCollection("orders");

Date start = Date.from(Instant.parse("2026-06-01T00:00:00Z"));
Date end = Date.from(Instant.parse("2026-07-01T00:00:00Z"));

Bson matchFilter = and(
    eq("tenantId", "T-A"),
    eq("status", "PAID"),
    gte("createdAt", start),
    lt("createdAt", end)
);

List<Bson> pipeline = Arrays.asList(
    match(matchFilter),
    sort(descending("createdAt")),
    limit(3),
    project(include("_id", "createdAt", "region", "total"))
);

orders.aggregate(pipeline).forEach(System.out::println);
~~~

**Note on imports:** Do not statically import both `Indexes.descending` and `Sorts.descending` simultaneously when unnecessary, as it easily causes builder name confusion. The example uses `Sorts.descending` for `$sort`; when creating an index below, call `Indexes.descending` via its qualified class name to convey clear intent.

### 14.2. Creating a Compound Index in Java

~~~java
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;

orders.createIndex(
    Indexes.compoundIndex(
        Indexes.ascending("tenantId", "status"),
        Indexes.descending("createdAt")
    ),
    new IndexOptions().name("ix_tenant_status_createdAt_desc")
);
~~~

The example illustrates a **key pattern**; it does not prove the planner always chooses the index. After creation, run explain on a real server and inspect the workload. If the collection already has an equivalent index, do not create a duplicate index differing only by name without evaluating cost.

### 14.3. Aggregation with `$group` in Java

~~~java
import static com.mongodb.client.model.Aggregates.group;
import static com.mongodb.client.model.Accumulators.sum;

orders.aggregate(Arrays.asList(
    match(matchFilter),
    group(
        "$region",
        sum("revenue", "$total"),
        sum("orderCount", 1)
    )
)).forEach(System.out::println);
~~~

The result corresponds to the SG and HN groups in section 3. With the Java API, `group` builds the aggregation stage; the initial `match` remains the filter on source documents.

### 14.4. When Using Spring Data MongoDB

Spring Data has a DSL such as `Aggregation.match(Criteria.where(...))`. The semantics remain the same:

~~~java
import static org.springframework.data.mongodb.core.aggregation.Aggregation.*;
import org.springframework.data.mongodb.core.query.Criteria;

var aggregation = newAggregation(
    match(
        Criteria.where("tenantId").is("T-A")
            .and("status").is("PAID")
            .and("createdAt").gte(start).lt(end)
    ),
    group("region").sum("total").as("revenue"),
    sort(org.springframework.data.domain.Sort.Direction.DESC, "revenue")
);
~~~

This is a **DSL illustration**; check your project's Spring Data MongoDB version when using it in code. If the framework uses entity field mapping, aliases, or custom converters, understand the actual generated BSON pipeline. Do not look at code resembling `$match` and assume it filters the exact field name stored in MongoDB.

### 14.5. Why the Index Relationship Does Not Depend on the Framework

Whether a filter is generated from `mongosh`, the Java Driver, Spring Data, or another language service, MongoDB Server still receives a **BSON query/pipeline**. The query planner selects indexes based on the **actual data and expressions**, not based on which builder the application used. Therefore, inspect the actual BSON pipeline and server `explain` when debugging performance.

## 15. Step-by-Step Optimization Methodology

A workflow balancing **correctness** and **performance**:

### Step 1 — State the Business Output Clearly

For example:

~~~text
Compute revenue per region for PAID orders
belonging to tenant T-A created in June 2026 (in UTC).
Return only regions with total revenue > 500,000,
sorted by revenue descending.
~~~

Classification:

| Condition | Applies to which data? | Appropriate position |
|---|---|---|
| tenantId = T-A | Source document | Initial `$match`. |
| status = PAID | Source document | Initial `$match`. |
| createdAt in June | Source document | Initial `$match`. |
| group by region | Filtered set | `$group`. |
| revenue > 500,000 | **Group result** | `$match` after `$group`. |
| sort revenue desc | **Group result** | `$sort` after grouping/revenue filter. |

### Step 2 — Write a Simple, Semantically Correct Pipeline

~~~javascript
const pipeline = [
  { $match: paidJuneTenantA },
  {
    $group: {
      _id: "$region",
      revenue: { $sum: "$total" },
      orders: { $sum: 1 }
    }
  },
  { $match: { revenue: { $gt: 500000 } } },
  { $sort: { revenue: -1 } }
]

lab.orders.aggregate(pipeline)
~~~

### Step 3 — Identify Recurring Query/Access Patterns

If multiple endpoints repeatedly filter tenant/status/date and sort by createdAt, a compound index `{tenantId:1,status:1,createdAt:-1}` is a natural candidate. However, if most queries only use `region`, a different index might serve better. Do not create indexes based solely on a rarely executed experimental pipeline.

### Step 4 — Use `explain` and Measure

~~~javascript
printjson(lab.orders.explain("executionStats").aggregate(pipeline))
~~~

Inspect the scan stage, indexName/indexBounds, keys/docs examined, number of documents entering `$group`, sort stage, and total latency. On real datasets, compare options under equivalent workloads; do not read a single `executionTimeMillis` number to declare an index optimal.

### Step 5 — Monitor During Rollout

- **Throughput/latency:** p50/p95/p99 of the report or API.
- **Index size, write overhead:** does the new index noticeably increase write costs?
- **CPU/I/O/cache:** did reducing docsExamined actually reduce load?
- **Spill/disk usage:** did `$group` or `$sort` need temporary disk space?
- **Cardinality and data skew:** one huge tenant may behave differently from a test tenant.
- **Sharding/replication:** does the query target the right shard? Does aggregation fan out or merge expensively?
- **Correctness:** do groups/totals/order counts still match requirements, especially after moving `$match` positions?

### Step 6 — Optimize Further Only When a Real Bottleneck Exists

Once you have matched early and placed suitable indexes, if the bottleneck lies in `$lookup`/`$group` or output volume, you may need pipeline restructuring, pre-aggregation, caching, or data modeling changes. Adding more `$match` stages will not solve the problem by itself if the filter already selects nearly the entire collection.

## 16. Common Misconceptions

| Misconception | Accurate understanding |
|---|---|
| "`$match` must always be stage 0." | Some stages require being first; filters on computed fields or after unwind/group have dependencies that must be respected. |
| "Having `$match` first guarantees MongoDB uses an index." | The planner can choose `COLLSCAN` if the index is unsuitable or the collection/filter is not selective enough. |
| "Indexing every field in `$match` is fastest." | Indexes add write overhead; choose based on access patterns, prefixes, and real statistics. |
| "A single-field index on status suffices for all reports." | If status has low selectivity, a compound index on tenant/status/date can be much more useful. |
| "Putting a filter after `$project` guarantees projection runs first." | The optimizer may push independent predicates earlier; check `explain`. |
| "The optimizer definitely pushes every `$match` earlier." | It cannot push conditions based on newly created fields or across boundaries that change semantics. |
| "Putting `$match` before or after `$limit` is the same." | No; filtering the top N differs from taking the top N of the filtered set. |
| "`$match` before `$unwind` only keeps matching items." | It only selects parent documents; unwinding afterward can emit other items as well. |
| "Any filter after `$unwind` should be removed for speed." | Post-unwind filters can be required to select the exact individual elements. |
| "Two conditions on `items.sku` and `items.qty` always apply to the same item." | They can match two separate elements; use `$elemMatch` when the same element is required. |
| "`$match` total revenue > X can be moved before `$group`." | If filtering on a group accumulator, it must stay after group. |
| "`$match` after `$group` can never be optimized early." | Filters solely on the grouping key can sometimes be pushed; check dependencies and the optimizer. |
| "`$match` before `$lookup` filters fields in the foreign collection." | Fields from lookup only appear after the join, unless an appropriate filter is placed inside the foreign lookup pipeline. |
| "An index on orders also speeds up every condition inside `$lookup`." | Lookup requires an appropriate index on the **foreign collection**; the two sides are two separate access patterns. |
| "A leading `$facet` still uses all indexes like a normal query." | A leading `$facet` can lead to `COLLSCAN`; upstream filtering/indexing is usually better when semantically valid. |
| "`IXSCAN` proves the plan is optimal." | You must inspect `keysExamined`, `docsExamined`, `FETCH`, sorts, and latency. |
| "`hint` is always faster than the planner's choice." | A hint can force a poor index; you must measure and consider version/data. |
| "`allowDiskUse` fixes slow queries caused by late filtering." | It only allows disk spilling for eligible stages; it does not eliminate redundant work. |
| "`$dateToString` then matching month performs identically to a range index." | It can be semantically correct if timezone is handled carefully, but it does not directly leverage a range index like filtering on the native Date. |
| "`$expr` always uses indexes just like normal field–constant predicates." | Index support depends on expression/context; measure on a real server. |
| "A partial index always works for any query containing the indexed key." | The query must fall within the indexed subset (implying the partial filter) to return complete results. |
| "An index's collation applies automatically to all queries." | Queries must use a compatible collation when comparing strings to get results/index usage under those rules. |
| "A fast query by tenantId means tenant security is correct." | Tenant identity must come from authorization and be filtered properly in every branch. |
| "MongoDB shell and Java driver have different execution plans just because syntax differs." | The planner operates on the actual BSON query/collection/indexes; differences usually stem from pipeline/options/data. |

## 17. Practice Exercises and Suggested Answers

Exercises are based on the nine-order dataset in section 2, assumed unmodified. You can re-run them on a fresh test collection to ensure the initial fixture. The goal is to determine **filter semantics** and **index opportunities**, not to measure absolute speed on nine documents.

### Exercise 1 — Early Filtering Before Group

**Task:** Count PAID orders of tenant T-A in June 2026, grouped by region.

**Answer:**

~~~javascript
lab.orders.aggregate([
  { $match: paidJuneTenantA },
  { $group: { _id: "$region", count: { $sum: 1 } } }
])
~~~

Result: HN has **2** orders and SG has **2** orders. `$match` uses source fields, so it can be placed before group and becomes a candidate for index usage.

### Exercise 2 — Revenue After Group

**Task:** Return only regions with June PAID revenue for T-A greater than 500,000.

**Answer:**

~~~javascript
lab.orders.aggregate([
  { $match: paidJuneTenantA },
  { $group: { _id: "$region", revenue: { $sum: "$total" } } },
  { $match: { revenue: { $gt: 500000 } } }
])
// Only SG, 1,260,000.
~~~

Do not move `revenue > 500000` before group because revenue is an **accumulator result**, not the `total` of a single order.

### Exercise 3 — Filtering the Top Three Newest Orders

**Task:** The three newest PAID orders of T-A (no month restriction).

**Answer:**

~~~javascript
lab.orders.aggregate([
  { $match: { tenantId: "T-A", status: "PAID" } },
  { $sort: { createdAt: -1 } },
  { $limit: 3 }
])
// O-109, O-107, O-104.
~~~

Moving `$limit` before match turns it into "filter within the three newest orders system-wide," which is no longer equivalent.

### Exercise 4 — Choosing a Compound Index

**Task:** Many reports filter `tenantId = T-A`, `status = PAID`, `createdAt` in a range, and sort by createdAt descending. Which index is a reasonable candidate?

**Answer:**

~~~javascript
lab.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 }
)
~~~

The two equality fields lead, and createdAt serves range/sort. Use `explain` with representative data to evaluate; do not claim this single index is always optimal for every query.

### Exercise 5 — Is a Post-Unwind Filter Really Needed?

~~~javascript
lab.orders.aggregate([
  { $match: { "items.sku": "BK-01" } },
  { $unwind: "$items" }
])
~~~

**Question:** Does the result contain only BK-01 items?

**Answer:** No. The pre-match only selects orders **with at least one BK-01**; unwind splits **all items** in those orders. Add `{ $match: {"items.sku":"BK-01"} }` after unwind to keep only BK-01 lines.

### Exercise 6 — One Element Satisfying Both Conditions

**Task:** Find orders having an item with `sku = BK-01` and `qty >= 3` **on the same item**.

**Answer:**

~~~javascript
lab.orders.aggregate([
  {
    $match: {
      items: {
        $elemMatch: {
          sku: "BK-01",
          qty: { $gte: 3 }
        }
      }
    }
  }
])
// O-104, O-107.
~~~

Two separate dot-notation conditions can match different items; `$elemMatch` expresses the exact invariant. A compound index on `items.sku`/`items.qty` can help subject to multikey limits.

### Exercise 7 — Combining Two Filters Around `$addFields`

**Task:** Find PAID orders of T-A whose total after a 10% discount is at least 300,000.

**Answer:**

~~~javascript
lab.orders.aggregate([
  { $match: { tenantId: "T-A", status: "PAID" } },
  {
    $addFields: {
      discountedTotal: { $multiply: ["$total", 0.9] }
    }
  },
  { $match: { discountedTotal: { $gte: 300000 } } },
  { $project: { _id: 1, discountedTotal: 1 } }
])
// O-104 (720,000) and O-107 (414,000).
~~~

The first filter can use an index on tenant/status; the second filter depends on the computed field, so keep it after creating the field.

### Exercise 8 — Can `$limit` Be Placed First?

Requirement: "get the two highest-total PAID orders of T-A." Compare:

~~~javascript
// Correct:
[
  { $match: { tenantId: "T-A", status: "PAID" } },
  { $sort: { total: -1 } },
  { $limit: 2 }
]

// Not equivalent:
[
  { $sort: { total: -1 } },
  { $limit: 2 },
  { $match: { tenantId: "T-A", status: "PAID" } }
]
~~~

**Answer:** The first pipeline selects O-104 and O-107. The second pipeline picks the top two orders across the entire collection first, so it may drop one of them after filtering; it is not guaranteed to return the full top two within the requested subset.

### Exercise 9 — Explaining `IXSCAN` and `FETCH`

An explain shows `IXSCAN` on `{tenantId:1,status:1,createdAt:-1}` followed by a document `FETCH`. Why is fetching still necessary?

**Answer:** The pipeline requires fields like `region` or `total` that are not in the index, or needs to verify another predicate; the engine must read the source documents. An index scan only proves index keys were leveraged for part of the processing.

### Exercise 10 — Is `COLLSCAN` Always a Bug?

On the nine-document fixture, `explain` picks `COLLSCAN` despite an index on status. Is this sufficient evidence of poor query performance?

**Answer:** No. A tiny collection or low-selectivity predicate can make a collection scan cheaper. Evaluate on representative data and workloads, examining keys/docs examined, sort, latency, and plan.

### Exercise 11 — Partial Index

Given the index:

~~~javascript
lab.orders.createIndex(
  { tenantId: 1, createdAt: -1 },
  { partialFilterExpression: { status: "PAID" } }
)
~~~

**Question:** Can a pipeline with only `$match:{tenantId:"T-A"}` use this index as a complete source for all orders of the tenant?

**Answer:** No. The index only contains PAID orders; a query unrestricted by status also needs CREATED/CANCELLED orders. A query implying `status:"PAID"` is a proper candidate.

### Exercise 12 — `$facet` with Two Scopes

**Task:** Within June for T-A, one branch counts **all statuses**, while one branch computes only PAID revenue.

**Answer:**

~~~javascript
lab.orders.aggregate([
  {
    $match: {
      tenantId: "T-A",
      createdAt: { $gte: start, $lt: end }
    }
  },
  {
    $facet: {
      statusCounts: [
        { $group: { _id: "$status", count: { $sum: 1 } } }
      ],
      paidRevenue: [
        { $match: { status: "PAID" } },
        { $group: { _id: null, revenue: { $sum: "$total" } } }
      ]
    }
  }
])
~~~

Putting status PAID in the shared pre-match would cause the statusCounts branch to **lose CREATED/CANCELLED data**.

### Exercise 13 — Filtering After Lookup

A pipeline looks up customers and then filters `customer.tier:"GOLD"`. Why can you not simply move this filter before lookup to use an index on orders?

**Answer:** `customer.tier` does not exist on source orders documents; it appears after the join. You can optimize by filtering on the foreign side with `$lookup.pipeline` and a suitable index on customers, while preserving join semantics and checking explain.

### Exercise 14 — Measuring Performance

**Task:** Write an explain command for an aggregation filtering June PAID orders of tenant T-A and then grouping by region.

**Answer:**

~~~javascript
lab.orders.explain("executionStats").aggregate([
  { $match: paidJuneTenantA },
  { $group: { _id: "$region", revenue: { $sum: "$total" } } }
])
~~~

Inspect query plan/indexName, scan stages, `keysExamined`, `docsExamined`, documents fed into group, and statistics provided in your server version. Do not expect every output to share the exact same JSON layout.

### Exercise 15 — Date Range with Local Time

Requirement: filter orders created on 2026-06-01 in **Asia/Ho_Chi_Minh**, while BSON Date stores UTC timestamps. Should you use the UTC interval from `2026-06-01T00:00:00Z` to `2026-06-02T00:00:00Z`?

**Answer:** No, if the daily period is defined in Vietnam time. Convert the start/end instants from UTC+7 (assuming no daylight saving shifts in this timezone):

~~~javascript
{
  $match: {
    createdAt: {
      $gte: ISODate("2026-05-31T17:00:00Z"),
      $lt: ISODate("2026-06-01T17:00:00Z")
    }
  }
}
~~~

Using a BSON Date range can support indexes; the decisive point is **converting boundaries to the right business timezone**, not formatting strings on the client machine.

### Exercise 16 — Java Driver and Early Filtering

**Task:** Translate `{$match:{tenantId:"T-A",status:"PAID"}}` to the Java Sync Driver.

**Answer:**

~~~java
Bson firstStage = Aggregates.match(
    Filters.and(
        Filters.eq("tenantId", "T-A"),
        Filters.eq("status", "PAID")
    )
);
~~~

Place this stage at the beginning of `List<Bson>` passed to `collection.aggregate(...)`. When using the builders, import `com.mongodb.client.model.Aggregates` and `Filters` or equivalent static imports.

## 18. Official MongoDB Documentation for Deeper Reading

The links below point to the MongoDB Database Manual and Java Driver documentation. When applying to production, select the **branch matching your running server/driver**; `explain` structure and the optimizer may change across versions.

- [`$match` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/match/) — syntax, restrictions, and conditions for index usage.
- [Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/) — `$match` splitting/pushdown, `$sort`/`$match` reordering, coalescence, and interaction with the execution engine.
- [Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/) — how stages pass documents and process data.
- [Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/) — memory, disk usage, and pipeline limits.
- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — how to read `IXSCAN`, `COLLSCAN`, `FETCH`, index bounds, and execution stats.
- [`db.collection.explain()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.explain/) — invoking explain for aggregate/query.
- [Indexes](https://www.mongodb.com/docs/manual/indexes/) — overview of index types and write-cost trade-offs.
- [Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/) — compound keys, prefixes, combining filter/sort.
- [The ESR Guideline](https://www.mongodb.com/docs/manual/tutorial/equality-sort-range-guideline/) — Equality, Sort, Range and index ordering choices.
- [Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/) — indexes on arrays and compound bounds with `$elemMatch`.
- [Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/) — boundaries of indexed documents and query eligibility.
- [`$expr` Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/expr/) — using aggregation expressions in filters and index limitations.
- [`$unwind` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/unwind/) — splitting array elements into pipeline documents.
- [`$group` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/) — accumulators, resources, and optimizations in applicable cases.
- [`$sort` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sort/) — relationship with indexes and `$limit`.
- [`$lookup` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/) — foreign collection filtering, indexes, and pipeline rewrites.
- [`$facet` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/facet/) — running multiple branches and the impact of a leading stage on indexes.
- [`$geoNear` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/geoNear/) — geospatial stage with placement constraints.
- [`db.collection.aggregate()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.aggregate/) — options such as `hint`, `allowDiskUse`, and `collation`.
- [MongoDB Java Sync Driver — Aggregation](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/) — building pipelines with `Aggregates`, `Filters`, and the Java Driver.
- [MongoDB 8.0 — Aggregation Pipeline Optimization](https://www.mongodb.com/docs/v8.0/core/aggregation-pipeline-optimization/) — 8.0 branch reference for comparing optimizations.
- [MongoDB 7.0 — `$match`](https://www.mongodb.com/docs/v7.0/reference/operator/aggregation/match/) — syntax/restrictions in the 7.0 branch.

**Conclusion:** `$match` can make aggregations more efficient by **narrowing data early** and enabling MongoDB to use **indexes**. However, stage ordering is only valid when **semantics are preserved**: filters on source fields can be placed early, whereas filters on **unwound elements**, **grouped values**, **computed fields**, or **joined lookup data** must follow actual dependencies. Indexes help when they align with **predicates, compound prefixes, sorts, collations, partial filters, and data distribution**; the mere existence of an index is not proof the optimizer used it. Write clear pipelines, design indexes from access patterns, and verify the server's decisions using **`explain("executionStats")`** on representative data.