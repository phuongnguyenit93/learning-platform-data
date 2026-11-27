# `hint`, Usage Limitations, and Verifying a Proposed Index in MongoDB

## Lesson Objectives

MongoDB has a **query planner** that selects an execution plan for queries such as `find()` and certain aggregations. When a collection has multiple indexes, one query can be executed in several ways: scanning the collection, traversing an index, combining filtering and sorting through a compound index, or fetching documents after an index scan.

During optimization, engineers sometimes propose a new index and want to know: **What happens if the query uses this exact index?** MongoDB supports **`hint()`** to request or force selection of an index where the API permits. However, `hint` has limitations: it does not fix query design on its own, does not create a nonexistent index, does not guarantee lower latency, and has unsupported cases or can yield incomplete results if a sparse/partial index is forced.

This lesson focuses on two core skills:

1. **Using `hint` for the right purpose** — syntax, limitations, special behaviors, and risks when deploying to production.
2. **Verifying a proposed index** — comparing baseline vs. candidate index using `explain()`, execution counters, result correctness, application metrics, and write/storage costs.

After this lesson, you will be able to:

- Explain how the planner picks an index in practice and why you should not force an index by intuition.
- Use `cursor.hint("index_name")`, `cursor.hint({field: 1})`, `aggregate(..., {hint: ...})`, and `hint({$natural:1})` appropriately.
- Recognize limitations with nonexistent indexes, hidden indexes, `$text`, time-series collections, query settings/index filters, sparse/partial indexes, and collation.
- Read `winningPlan`, `rejectedPlans`, `indexBounds`, `nReturned`, `totalKeysExamined`, `totalDocsExamined`, and `IXSCAN`, `FETCH`, `SORT`, and `COLLSCAN` steps.
- Design experiments comparing a query—**holding filter, sort, projection, limit, and collation constant**—without a hint and with hints for each candidate.
- Distinguish `explain("queryPlanner")`, `explain("executionStats")`, `explain("allPlansExecution")`, the plan cache, and application latency under load.
- Make sound decisions: let the planner choose, add an index, adjust the query, apply a temporary hint, or drop the proposed index.
- Build a rollout, monitoring, and rollback plan without breaking read paths or introducing unintended write overhead.

> **Principle:** `hint` is a **hypothesis test** and occasionally a controlled intervention. Proof of optimization must come from **accurate results, a sound execution plan, real latency, and total index cost**—not from forcing the planner onto an arbitrary index.

---

## 1. Why Can the Same Query Have Multiple Plans?

Suppose an order management system uses an `orders` collection. An endpoint displays the 20 newest `PAID` orders for a customer within a tenant:

~~~javascript
db.orders.find(
  {
    tenantId: "TENANT-01",
    customerId: "CUS-101",
    status: "PAID"
  },
  {
    orderNo: 1,
    createdAt: 1,
    total: 1,
    _id: 1
  }
).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
~~~

The collection might have these indexes:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, customerId: 1 },
  { name: "idx_tenant_customer" }
);

db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_tenant_status_created" }
);

db.orders.createIndex(
  {
    tenantId: 1,
    customerId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  { name: "idx_tenant_customer_status_recent" }
);
~~~

The planner has several potential paths:

1. Use the `tenantId, customerId` index to find the customer's orders, then filter `status` and sort.
2. Use the `tenantId, status, createdAt` index, then check `customerId` on matching documents.
3. Use the compound index containing all equality fields and sort keys, potentially reducing keys scanned and avoiding a separate sort step.
4. On very small data or low selectivity, scanning the collection may be estimated cheaper than some index plans.

Having the most fields in an index does not guarantee it always wins. Cost depends on matching document count, data distribution, field cardinality, cache state, document/index size, projection, limit, sort, and whether the index can cover the query.

### 1.1. An Index Is a Data Structure; a Plan Is How It Is Used

Distinguish clearly:

| Concept | Meaning |
|---|---|
| Index | Structure created via `createIndex()` |
| Query shape | Query pattern: filter, sort, projection, collation, and characteristics considered by the planner |
| Candidate plan | Execution strategy evaluated by the planner |
| Winning plan | Plan chosen for the query during a given planning pass |
| Plan cache | Mechanism caching plan info per query shape under eligible conditions |
| `hint` | Request specifying an index or collection scan instead of automatic selection, subject to precedence rules and limits |
| `explain` | Returns plan structure details and optionally execution statistics |

`hint` neither alters the collection nor creates an index. It alters how **a single command** requests execution when the server mechanism accepts that hint.

### 1.2. Seeing `IXSCAN` Is Not Enough to Conclude It Is Good

A plan with `IXSCAN` can still be very expensive if it traverses 900,000 keys and fetches hundreds of thousands of documents to return 20 results. Conversely, `COLLSCAN` on a 15-document lab collection can be a reasonable choice.

The question is not "does it use an index?" but:

- Did the index narrow the search range enough?
- Does it leverage sort and limit?
- How many documents must be fetched?
- Does it return the exact data required by the query?
- Does p95/p99 latency under real load go down or up?
- How much extra cost does the proposed index add to each write operation?

---

## 2. Basic Syntax of `cursor.hint()`

In mongosh, `hint()` is called on the cursor returned by `find()`.

### 2.1. Specifying by Index Name

~~~javascript
db.orders.find({
  tenantId: "TENANT-01",
  customerId: "CUS-101"
}).hint(
  "idx_tenant_customer"
);
~~~

The index name is the `name` specified when creating the index. If omitted, MongoDB auto-generates a name from the key pattern, e.g., `tenantId_1_customerId_1`. In production operations, assign explicit, meaningful names so hints do not rely on hard-to-track generated names.

### 2.2. Specifying by Key Pattern

~~~javascript
db.orders.find({
  tenantId: "TENANT-01",
  customerId: "CUS-101"
}).hint({
  tenantId: 1,
  customerId: 1
});
~~~

The key pattern must match an existing index and adhere to API rules. This does not ask MongoDB to auto-create `{tenantId: 1, customerId: 1}` if that index does not already exist.

### 2.3. Combining Filter, Projection, Sort, Limit, and Explain

~~~javascript
const result = db.orders
  .find(
    {
      tenantId: "TENANT-01",
      customerId: "CUS-101",
      status: "PAID"
    },
    {
      orderNo: 1,
      createdAt: 1,
      total: 1,
      _id: 1
    }
  )
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .hint("idx_tenant_customer_status_recent")
  .explain("executionStats");

printjson(result.queryPlanner.winningPlan);
printjson(result.executionStats);
~~~

Note: **`explain()` returns plan information**, not the list of 20 orders. To retrieve the actual data, run the query without calling `explain`.

### 2.4. `hint()` Is Unnecessary for Most Queries

A normal query:

~~~javascript
db.orders.find({
  tenantId: "TENANT-01",
  customerId: "CUS-101"
});
~~~

lets the planner decide. That should be the **starting point of every experiment**. Add a hint only for a specific purpose, such as testing a new index or temporarily mitigating a plan with proven performance regression.

### 2.5. Hint Can Request a Collection Scan

You can use `$natural` to force scanning the collection in one direction:

~~~javascript
db.orders.find({
  tenantId: "TENANT-01"
}).hint({
  $natural: 1
});
~~~

Or:

~~~javascript
db.orders.find({
  tenantId: "TENANT-01"
}).hint({
  $natural: -1
});
~~~

This is a useful technique when **comparing an index scan against a collection scan**. It is not advice to rely on natural order for business pagination; natural order is not a contract for chronological or `_id` ordering.

Use only `1` or `-1` for `$natural` per current MongoDB version rules.

---

## 3. Hands-On: Creating a Dataset to Compare Plans

This lesson uses a dedicated lab database `query_plan_lab`. These commands create a collection and indexes; never run them on a production database.

### 3.1. Creating `orders`

~~~javascript
use query_plan_lab

db.orders.insertMany([
  {
    _id: "O-001",
    tenantId: "TENANT-01",
    customerId: "CUS-101",
    status: "PAID",
    createdAt: ISODate("2026-11-01T09:00:00Z"),
    orderNo: "ORD-001",
    total: NumberDecimal("120000")
  },
  {
    _id: "O-002",
    tenantId: "TENANT-01",
    customerId: "CUS-101",
    status: "PAID",
    createdAt: ISODate("2026-11-02T09:00:00Z"),
    orderNo: "ORD-002",
    total: NumberDecimal("220000")
  },
  {
    _id: "O-003",
    tenantId: "TENANT-01",
    customerId: "CUS-101",
    status: "NEW",
    createdAt: ISODate("2026-11-03T09:00:00Z"),
    orderNo: "ORD-003",
    total: NumberDecimal("320000")
  },
  {
    _id: "O-004",
    tenantId: "TENANT-01",
    customerId: "CUS-101",
    status: "PAID",
    createdAt: ISODate("2026-11-04T09:00:00Z"),
    orderNo: "ORD-004",
    total: NumberDecimal("420000")
  },
  {
    _id: "O-005",
    tenantId: "TENANT-01",
    customerId: "CUS-101",
    status: "CANCELED",
    createdAt: ISODate("2026-11-05T09:00:00Z"),
    orderNo: "ORD-005",
    total: NumberDecimal("520000")
  },
  {
    _id: "O-006",
    tenantId: "TENANT-01",
    customerId: "CUS-101",
    status: "PAID",
    createdAt: ISODate("2026-11-06T09:00:00Z"),
    orderNo: "ORD-006",
    total: NumberDecimal("620000")
  },
  {
    _id: "O-007",
    tenantId: "TENANT-01",
    customerId: "CUS-102",
    status: "PAID",
    createdAt: ISODate("2026-11-07T09:00:00Z"),
    orderNo: "ORD-007",
    total: NumberDecimal("720000")
  },
  {
    _id: "O-008",
    tenantId: "TENANT-01",
    customerId: "CUS-102",
    status: "NEW",
    createdAt: ISODate("2026-11-08T09:00:00Z"),
    orderNo: "ORD-008",
    total: NumberDecimal("820000")
  },
  {
    _id: "O-009",
    tenantId: "TENANT-02",
    customerId: "CUS-101",
    status: "PAID",
    createdAt: ISODate("2026-11-09T09:00:00Z"),
    orderNo: "ORD-009",
    total: NumberDecimal("920000")
  },
  {
    _id: "O-010",
    tenantId: "TENANT-02",
    customerId: "CUS-102",
    status: "NEW",
    createdAt: ISODate("2026-11-10T09:00:00Z"),
    orderNo: "ORD-010",
    total: NumberDecimal("1020000")
  },
  {
    _id: "O-011",
    tenantId: "TENANT-01",
    customerId: "CUS-101",
    status: "PAID",
    createdAt: ISODate("2026-11-11T09:00:00Z"),
    orderNo: "ORD-011",
    total: NumberDecimal("1120000")
  },
  {
    _id: "O-012",
    tenantId: "TENANT-01",
    customerId: "CUS-101",
    status: "PAID",
    createdAt: ISODate("2026-11-11T09:00:00Z"),
    orderNo: "ORD-012",
    total: NumberDecimal("1220000")
  }
]);
~~~

The dataset intentionally includes:

- Two different tenants.
- Multiple statuses and multiple customers.
- Two documents `O-011` and `O-012` sharing the exact same timestamp.
- A query filtering multiple fields and sorting by descending timestamp.
- Fields `total` and `orderNo` to highlight projection/fetch cost.

Verify:

~~~javascript
db.orders.countDocuments({});
db.orders.find({}, { _id: 1, tenantId: 1, status: 1 })
  .sort({ _id: 1 });
~~~

### 3.2. Creating Candidate Indexes

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    customerId: 1
  },
  {
    name: "idx_tenant_customer"
  }
);

db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1
  },
  {
    name: "idx_tenant_status_created"
  }
);

db.orders.createIndex(
  {
    tenantId: 1,
    customerId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "idx_tenant_customer_status_recent"
  }
);
~~~

Double-check the exact names and key patterns:

~~~javascript
db.orders.getIndexes();
~~~

Before hinting an index by name, verify that index actually exists. Never assume from migration source code that the index build has completed on the target database.

### 3.3. Target Query

~~~javascript
const queryFilter = {
  tenantId: "TENANT-01",
  customerId: "CUS-101",
  status: "PAID"
};

const queryProjection = {
  _id: 1,
  orderNo: 1,
  createdAt: 1,
  total: 1
};

const querySort = {
  createdAt: -1,
  _id: -1
};
~~~

We will keep **the exact same three objects** across every comparison.

---

## 4. Measuring the Baseline: Letting the Planner Choose

### 4.1. Running Explain Without a Hint

~~~javascript
const baseline = db.orders
  .find(queryFilter, queryProjection)
  .sort(querySort)
  .limit(20)
  .explain("executionStats");

printjson(baseline.queryPlanner.winningPlan);
printjson(baseline.executionStats);
~~~

The lab dataset is tiny, so the planner may pick `COLLSCAN`. That **does not prove an index is broken or unnecessary**. What matters is learning how to read the plan, not treating latency on 12 documents as proof of production optimization.

### 4.2. Comparing Candidate A: Index on Tenant and Customer

~~~javascript
const planA = db.orders
  .find(queryFilter, queryProjection)
  .sort(querySort)
  .limit(20)
  .hint("idx_tenant_customer")
  .explain("executionStats");

printjson(planA.queryPlanner.winningPlan);
printjson(planA.executionStats);
~~~

This index supports filtering `tenantId` and `customerId`, yet lacks `status` and the `createdAt, _id` sort keys needed to serve the full query. It may have to filter `status` after the index scan and sort results separately.

### 4.3. Comparing Candidate B: Index on Tenant, Status, and Time

~~~javascript
const planB = db.orders
  .find(queryFilter, queryProjection)
  .sort(querySort)
  .limit(20)
  .hint("idx_tenant_status_created")
  .explain("executionStats");

printjson(planB.queryPlanner.winningPlan);
printjson(planB.executionStats);
~~~

This index supports `tenantId` and `status`, followed by descending `createdAt`. Because `customerId` is missing from the key, the database may have to traverse orders from other customers, then fetch documents or evaluate extra predicates to match the requested customer.

Furthermore, this index lacks `_id` as a secondary sort key. If deterministic ordering by `createdAt DESC, _id DESC` is required, an index on `createdAt` alone cannot be assumed to satisfy the entire sort.

### 4.4. Comparing Candidate C: Compound Index Tailored to Query Shape

~~~javascript
const planC = db.orders
  .find(queryFilter, queryProjection)
  .sort(querySort)
  .limit(20)
  .hint("idx_tenant_customer_status_recent")
  .explain("executionStats");

printjson(planC.queryPlanner.winningPlan);
printjson(planC.executionStats);
~~~

Index C puts the three equality keys first, then the two sort keys. It is a strong candidate for this query pattern. However, that **does not guarantee** it outperforms every alternative on every dataset—especially when projection must fetch `orderNo` and `total` outside the index, or when a large index increases cache pressure.

### 4.5. Adding an Intentional Collection Scan Comparison

~~~javascript
const collscan = db.orders
  .find(queryFilter, queryProjection)
  .sort(querySort)
  .limit(20)
  .hint({ $natural: 1 })
  .explain("executionStats");

printjson(collscan.queryPlanner.winningPlan);
printjson(collscan.executionStats);
~~~

This serves as a control to see the work required without an index. Never use `$natural` as a deterministic business pagination mechanism.

### 4.6. Experiment Results Table

Record the actual metrics from your database's explain runs:

| Option | Requested Index | Keys Examined | Docs Examined | Returned | Separate Sort? | Execution Millis |
|---|---|---:|---:|---:|---|---:|
| Baseline | Planner chosen | Measure | Measure | Measure | Observe | Measure |
| A | tenant + customer | Measure | Measure | Measure | Observe | Measure |
| B | tenant + status + created | Measure | Measure | Measure | Observe | Measure |
| C | tenant + customer + status + created + ID | Measure | Measure | Measure | Observe | Measure |
| D | `$natural:1` | Measure | Measure | Measure | Observe | Measure |

Never fill in fabricated measurements and present them as MongoDB results. Plans may display different stages across versions and query engines; read the actual plan tree.

---

## 5. Understanding the Three Explain Verbosity Levels

MongoDB offers these standard verbosity levels:

### 5.1. `queryPlanner`

~~~javascript
db.orders.find(queryFilter)
  .explain("queryPlanner");
~~~

Primarily shows how the planner analyzed the query, the winning plan, and related candidates. This is a lighter mode when you want the execution path without requesting full runtime statistics like `executionStats`.

### 5.2. `executionStats`

~~~javascript
db.orders.find(queryFilter)
  .explain("executionStats");
~~~

The planner selects a plan and the server executes it to return statistics for the winning plan. Useful fields:

- `nReturned`.
- `totalKeysExamined`.
- `totalDocsExamined`.
- `executionTimeMillis`.
- Stages and counters inside `executionStages`.

### 5.3. `allPlansExecution`

~~~javascript
db.orders.find(queryFilter)
  .explain("allPlansExecution");
~~~

Provides additional information on candidate plans during the selection phase. **Do not treat metrics on rejected plans as complete benchmarks**: they may represent only partial trial execution during plan selection.

### 5.4. Distinguishing Explain from the Plan Cache

An essential detail: **`explain` bypasses existing plan cache entries and does not insert the winning plan into the plan cache**. Thus, explain is great for checking planner reasoning and single-run cost, yet does not fully mirror everyday query behavior when the plan cache is warm.

If a production application suffers high p95 latency from a query shape stuck on a poor cached plan, running explain once and seeing a good new candidate does not prove the app will immediately switch to it as expected.

When needed, inspect `$planCacheStats`, monitor telemetry, and review query settings features for your MongoDB version. Index changes (create/drop/hide) can also invalidate or alter related plan cache entries.

---

## 6. How to Read the Winning Plan and Counters

### 6.1. `COLLSCAN`

This stage shows MongoDB is scanning the collection. On small collections or queries retrieving nearly every document, this can be sensible. On large collections where only 20 selective records are needed, `COLLSCAN` usually signals checking indexes.

### 6.2. `IXSCAN`

Indicates traversing an index. Always inspect **which keys** and **how many keys** were traversed.

Illustrative example:

~~~text
nReturned: 20
totalKeysExamined: 250000
totalDocsExamined: 80000
~~~

Such a plan can be inefficient for a read path fetching only 20 orders, despite having `IXSCAN`. Inspect `indexBounds`, equality prefix, ranges, and predicates pushed down into the scan.

Do not enforce one rigid keys/returned ratio across all queries: aggregations, counts, or queries intentionally scanning broad ranges have different characteristics.

### 6.3. `FETCH`

An index can identify candidate IDs while the server still must fetch documents to:

- Check an extra filter not present in the index.
- Read projected fields absent from the index.
- Return full documents to the application.

`totalDocsExamined` helps quantify this work. A **covered query** under eligible conditions can return results from the index without fetching documents, though not every query with projection can be covered; arrays/multikey, collation, and other constraints can prevent coverage.

### 6.4. `SORT`

A separate sort step can appear when the index does not provide the required order. On large result sets, sorting can consume substantial CPU, memory, or disk depending on server policy.

If an index supports both filter and sort, the planner can avoid a separate sort step. However, **hinting an index that only supports the filter** does not magically make it support sorting.

### 6.5. `indexBounds`

This shows the key ranges scanned in the index, depending on explain format. For instance, equality on `tenantId` and `customerId` yields narrow bounds; a range on `createdAt` yields wider bounds.

Reading `indexBounds` helps answer:

- Which fields actually tighten the scan?
- Are any indexed fields left unbounded?
- Is the query scanning an entire key range due to a missing equality prefix?
- Is sorting satisfied by index order or forced into a `SORT` stage?

### 6.6. `rejectedPlans` Does Not Mean "Permanently Bad Plans"

A plan rejected during one selection pass does not prove the underlying index is always inferior. Changing data, different query literals, cache state, server version, or load conditions can shift which plan is best.

Never treat `rejectedPlans` as a list of indexes to drop immediately. An index may serve a different query shape or enforce an important unique constraint.

### 6.7. Explain Shapes Can Vary

MongoDB uses different query engines, such as classic and slot-based execution. Internal fields and tree layouts can differ. Never write scripts assuming `winningPlan.inputStage.inputStage.stage` always exists, or that a stage always lives at one fixed JSON path.

Prefer documented top-level statistic fields, and inspect the full plan tree when investigating.

---

## 7. Designing Indexes with Equality – Sort – Range

A compound index is typically designed around **Equality – Sort – Range (ESR)**, not by merely counting fields appearing in the query.

Example:

~~~javascript
db.orders.find({
  tenantId: "TENANT-01",
  status: "PAID",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z")
  }
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
~~~

Candidate index:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  { name: "idx_tenant_status_recent" }
);
~~~

With equality on tenant/status and sorting on `createdAt`/`_id`, this index has a structure worth verifying. Yet ESR is a **guiding principle**, not the lone winner for every selectivity profile; measure in practice.

### 7.1. Never Ignore Field Order

Two indexes:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1 }
{ createdAt: -1, status: 1, tenantId: 1 }
~~~

are not equivalent. Field order determines how the index serves equality prefixes, ranges, and sorting.

### 7.2. Sort Directions Matter Too

Example:

~~~javascript
db.orders.find({
  tenantId: "TENANT-01"
}).sort({
  createdAt: -1,
  _id: -1
});
~~~

An index with matching sort keys can avoid a separate sort. A compound index supports the defined sort direction or the **fully reversed** direction of that sort suffix, not arbitrary independent sign flips on individual fields.

### 7.3. Filtered Fields Missing from the Index

If you use the index:

~~~javascript
{ tenantId: 1, createdAt: -1, _id: -1 }
~~~

while the query also filters `status: "PAID"`, the database still has to fetch/inspect `status` on candidate documents. For a tenant with many orders and a low `PAID` ratio, this cost can be high.

Hinting that index merely because it supports sorting is not guaranteed to beat an index that includes `status` in the equality prefix.

### 7.4. Finding an Optimal Index for the Entire Workload

A very wide index:

~~~javascript
{
  tenantId: 1,
  customerId: 1,
  status: 1,
  createdAt: -1,
  _id: -1,
  orderNo: 1,
  total: 1
}
~~~

might let one query be covered under certain conditions, yet costs storage and write overhead while failing to provide useful prefixes for other queries.

Do not automatically stuff every projected field into an index. Weigh read gains against:

- Index size.
- Insert/update/delete overhead.
- Cache residency.
- Number of overlapping indexes.
- Stability of query patterns.
- Write-heavy workloads.

---

## 8. Process for Comparing Multiple Indexes Without Altering the Query

### 8.1. Keep the Query Shape Fixed

Before calling `hint`, fix:

~~~javascript
const filter = {
  tenantId: "TENANT-01",
  customerId: "CUS-101",
  status: "PAID"
};

const projection = {
  _id: 1,
  orderNo: 1,
  createdAt: 1,
  total: 1
};

const sort = {
  createdAt: -1,
  _id: -1
};

const limit = 20;
~~~

Why keep them constant?

If one test returns whole documents and another returns only `_id`, or one sorts by `createdAt` and another omits sorting, you are comparing **two different business requirements**, not just comparing indexes.

### 8.2. Illustrative Script Running Explain Per Candidate

~~~javascript
const candidates = [
  null,
  "idx_tenant_customer",
  "idx_tenant_status_created",
  "idx_tenant_customer_status_recent"
];

for (const candidate of candidates) {
  let cursor = db.orders
    .find(filter, projection)
    .sort(sort)
    .limit(limit);

  if (candidate !== null) {
    cursor = cursor.hint(candidate);
  }

  const report = cursor.explain("executionStats");

  printjson({
    candidate: candidate || "PLANNER_DEFAULT",
    nReturned: report.executionStats.nReturned,
    totalKeysExamined: report.executionStats.totalKeysExamined,
    totalDocsExamined: report.executionStats.totalDocsExamined,
    executionTimeMillis: report.executionStats.executionTimeMillis,
    winningPlan: report.queryPlanner.winningPlan
  });
}
~~~

This script makes no assumptions about which index the query planner picks at baseline. The output reflects verification data from your running server.

**Only run the script once the corresponding index names have been created.** If an index is missing, `hint` errors out. On large datasets, each `executionStats` explain actually executes the query, so control permissions and resources.

### 8.3. Reading Metrics for Their Intended Purpose

| Metric | Practical Question |
|---|---|
| `nReturned` | Did it return the expected count? |
| `totalKeysExamined` | Did it scan too many index entries? |
| `totalDocsExamined` | Did it fetch/inspect too many documents? |
| `IXSCAN` vs `COLLSCAN` | What is the primary access path? |
| `SORT` | Is there a separate sort step? |
| `indexBounds` | Which filters were pushed down into the index? |
| `executionTimeMillis` | Server-reported duration for the explain run; read with caveats |
| Index size | How much extra disk/cache does the new index consume? |
| p95/p99 API latency | Is it genuinely faster for users under load? |
| Write latency | Did maintaining an extra index slow writes? |

### 8.4. Always Verify Data Correctness

A proposed index must return **the exact same business results** for the same query, aside from concurrent writes or queries with undefined tie-breaking order.

When comparing queries with sorting, include a tie-breaker key for deterministic order:

~~~javascript
.sort({
  createdAt: -1,
  _id: -1
});
~~~

If results differ between a hint and baseline on static data, investigate:

- Is a sparse/partial index missing part of the result set?
- Do queries have differing collations?
- Are there mixed BSON types in the field?
- Were projection, limit, or filter accidentally altered?
- Did forcing `$natural` omit business sorting?

Never accept a "faster" plan if it drops records.

### 8.5. Do Not Conclude from a Single Run

In a small lab, `executionTimeMillis` is tiny and differences are mostly noise. In production, a single explain run cannot replace stability testing under load.

A more reliable procedure:

1. Warm up data/connections for every candidate.
2. Run multiple iterations under equivalent load.
3. Use diverse representative filter values, including small and large tenants.
4. Measure p50, p95, p99, and throughput.
5. Keep write rate and concurrency similar to production.
6. Compare cache churn, index size, and I/O.
7. Separate plan selection/explain metrics from end-to-end app latency.
8. Never treat fabricated numbers as measured results.

---

## 9. Limitation 1: `hint` Only Works with Existing, Permitted Indexes

### 9.1. Nonexistent Index

~~~javascript
db.orders.find({
  tenantId: "TENANT-01"
}).hint("idx_does_not_exist");
~~~

If an index with that name does not exist, the operation returns an error. `hint` **does not** tell MongoDB to create a new index.

Practice:

~~~javascript
db.orders.getIndexes();
~~~

Verify name, key pattern, collation, and index options before hinting.

### 9.2. Hidden Indexes

MongoDB supports **hidden indexes** to exclude an index from query planner selection without dropping it. Hinting a hidden index can be rejected.

Do not do this:

~~~javascript
// If the index is hidden, hinting it will fail.
db.orders.find({ tenantId: "TENANT-01" })
  .hint("idx_hidden_candidate");
~~~

In testing workflows, when evaluating the impact of removing an index from planner consideration, hidden indexes are a helpful tool. However:

- Hidden indexes are still maintained on writes and still consume storage.
- Hiding an index is not equivalent to dropping an index.
- You cannot use `hint` to "sneak" a query onto a hidden index.
- Hiding/unhiding can affect the plan cache and other queries' behavior.
- Only toggle hidden index state in production through change management.

### 9.3. Time-Series Collections

On **time-series collections**, MongoDB imposes specific restrictions: when hinting an index, you must specify **by index name** rather than key pattern in the APIs/versions documented by MongoDB.

Conceptual example:

~~~javascript
db.metrics.find({
  "metadata.deviceId": "SENSOR-01"
}).hint("idx_metrics_device_time");
~~~

This only makes sense when the time-series collection and index have actually been created properly and the index name exists. Do not take a regular collection's key pattern and assume time-series handles it identically.

---

## 10. Limitation 2: `$text` and Queries with Special Index Rules

For queries using **`$text`**, MongoDB does not allow using `hint()` to specify a different index for that query.

~~~javascript
// Illustrates a text query:
db.articles.find({
  $text: {
    $search: "mongodb index"
  }
});
~~~

Do not write:

~~~javascript
// This is not supported for forcing an index on a $text query.
db.articles.find({
  $text: {
    $search: "mongodb index"
  }
}).hint("idx_articles_created");
~~~

Full-text, geospatial, wildcard, hashed, and special-expression queries have dedicated index support rules. `hint` cannot turn a regular index into one capable of serving predicates it was never designed for.

For example, a hashed index suits certain equality lookups, yet does not naturally support ordered range scans like a standard B-tree index. Simply existing does not make an index valid or effective for every filter/sort.

---

## 11. Limitation 3: Sparse and Partial Indexes Can Miss Data

### 11.1. Sparse Indexes

A sparse index on `email` omits documents **lacking the `email` field**:

~~~javascript
db.users.createIndex(
  { email: 1 },
  {
    sparse: true,
    name: "idx_sparse_email"
  }
);
~~~

The query:

~~~javascript
db.users.find({});
~~~

requests **every user**, including users without an `email`. Forcing a sparse index as the data source for such a query risks **missing results** because those documents have no index entry.

Example:

~~~javascript
// Do not use this to retrieve all users:
db.users.find({}).hint("idx_sparse_email");
~~~

This is why the query planner normally avoids choosing a sparse index when it does not cover the full result set.

Especially for a full-collection count, forcing a sparse index can yield a different count from reality because documents lacking the field are absent from the index. **Never trade correctness just to see IXSCAN.**

### 11.2. Partial Indexes

A partial index only indexes documents matching a filter:

~~~javascript
db.orders.createIndex(
  { createdAt: -1 },
  {
    partialFilterExpression: {
      status: "OPEN"
    },
    name: "idx_open_orders_created"
  }
);
~~~

Eligible query:

~~~javascript
db.orders.find({
  status: "OPEN"
}).sort({
  createdAt: -1
});
~~~

Query ineligible to use the index to return the **complete** result set:

~~~javascript
db.orders.find({}).sort({
  createdAt: -1
});
~~~

The second query needs `OPEN`, `PAID`, and `CANCELED`. The partial index only holds `OPEN`, so it lacks the full data. MongoDB normally refuses to pick a partial index if doing so would produce an incomplete result set.

Never assume `hint` makes a query lacking the filter condition valid. Depending on API/version and how the hint is applied, carefully verify correctness and planner rules. The right approach is **writing queries with compatible predicates and/or creating an index serving the full requirement**, not relying on `hint` to bypass data limits.

### 11.3. The Query Must Be Narrower Than or Equal to the Partial Index Predicate

Given the partial index:

~~~javascript
db.orders.createIndex(
  { createdAt: -1 },
  {
    partialFilterExpression: {
      total: { $gte: 1000000 }
    }
  }
);
~~~

Query:

~~~javascript
db.orders.find({
  total: { $gte: 2000000 }
});
~~~

requests a subset of indexed documents, so it can qualify.

Query:

~~~javascript
db.orders.find({
  total: { $gte: 500000 }
});
~~~

needs documents outside the index, so the partial index is insufficient.

### 11.4. Do Not Force Hints When Counting or Exporting Everything

Tasks such as:

- Counting all users.
- Exporting an entire collection.
- Auditing scans.
- Accounting reports requiring all statuses.

demand strict completeness. Before using a sparse/partial index or hint, prove the query filter strictly requests a subset contained inside the index.

---

## 12. Limitation 4: Collation and Comparison Order

An index configured with a specific collation compares strings according to that locale. Example:

~~~javascript
db.customers.createIndex(
  { fullName: 1 },
  {
    name: "idx_name_vi",
    collation: {
      locale: "vi",
      strength: 2
    }
  }
);
~~~

Query with matching collation:

~~~javascript
db.customers.find({
  fullName: "An"
}).collation({
  locale: "vi",
  strength: 2
}).hint("idx_name_vi");
~~~

When a query and index have different collations, hinting that index does not automatically alter the query's string comparison semantics. The index may fail to provide expected string filtering/sorting; the server may incur extra work or enforce restrictions.

Checklist:

1. Does the collection have a default collation?
2. Which collation was the index built with?
3. Does the query specify a collation?
4. Does index uniqueness depend on collation?
5. Does string sorting return the right order for Vietnamese business rules?

An explain showing "index used" is insufficient if inconsistent collations return wrong ordering or comparisons.

---

## 13. Limitation 5: Index Filters and Query Settings Can Override `hint`

### 13.1. Index Filters

In versions/configurations supporting **index filters**, when an index filter applies to a query shape, MongoDB can **ignore `hint()`** for that query shape.

That means if a developer adds:

~~~javascript
db.orders.find({
  tenantId: "TENANT-01"
}).hint("idx_tenant_customer");
~~~

and explain shows the hinted index was not used, it is not necessarily a syntax mistake in `hint`. Check any index filter rules active on that query shape.

Never assume a command-level `hint` always holds absolute priority over cluster configuration.

### 13.2. Query Settings

In modern MongoDB versions supporting **query settings**, cluster-level configuration can enforce index hints or restrictions per query shape. These settings carry precedence rules relative to inline command hints.

When query settings enforce index hints, the server may ignore application-supplied hints. Check active query settings and tooling for your version before assuming a `hint` in application code will always take effect.

**Distinction:**

| Mechanism | Typical Scope | Purpose |
|---|---|---|
| `cursor.hint()` | A single query/call | Test or specify an index |
| Index filter | Configured query shape | Restrict the set of indexes the planner considers |
| Query settings | Query shape / cluster per version | Control query behavior at the operations layer |
| Hidden index | State of a single index | Exclude index from planner choices without dropping |
| Plan cache | Cached plans | Reduce replanning overhead when eligible |

Syntax and support for index filters/query settings vary by version; change them in production only after checking current server documentation and establishing a rollback procedure.

### 13.3. `hint` Does Not Replace System-Wide Query Settings

If the goal is reducing the risk of a query shape picking a bad index across thousands of app instances, embedding `hint` in source code creates coupling that is hard to roll back if indexes are renamed or dropped.

In some versions and situations, query settings are a cleaner operational choice. Yet no single option fits every system; weigh scope of change, feature availability, and observability.

---

## 14. Hint in Aggregation

`db.collection.aggregate()` supports a `hint` option for an index on the **input collection** where the API allows.

Example:

~~~javascript
db.orders.aggregate(
  [
    {
      $match: {
        tenantId: "TENANT-01",
        status: "PAID"
      }
    },
    {
      $sort: {
        createdAt: -1,
        _id: -1
      }
    },
    {
      $limit: 20
    },
    {
      $project: {
        orderNo: 1,
        createdAt: 1,
        total: 1
      }
    }
  ],
  {
    hint: "idx_tenant_status_created"
  }
);
~~~

Note: the aggregation `hint` option applies to the **initial collection/view** the pipeline runs against. It **does not apply to collections accessed inside `$lookup` or `$graphLookup` stages**.

### 14.1. An Outer Pipeline Hint Cannot Force a Joined Collection's Index

Example:

~~~javascript
db.orders.aggregate(
  [
    {
      $match: {
        tenantId: "TENANT-01"
      }
    },
    {
      $lookup: {
        from: "order_items",
        localField: "_id",
        foreignField: "orderId",
        as: "items"
      }
    }
  ],
  {
    hint: "idx_tenant_customer"
  }
);
~~~

The outer pipeline hint targets the `orders` collection, **not** indexes on `order_items`.

To speed up joins, you normally need an appropriate index on the foreign collection, for example:

~~~javascript
db.order_items.createIndex(
  { orderId: 1 },
  { name: "idx_order_items_orderId" }
);
~~~

Then measure the plan/latency of the full aggregation and each lookup path. Never put a `hint` on the input collection and conclude the foreign side is optimized.

### 14.2. Pipeline Stage Order Also Matters

If `$match` can be applied early, fewer documents flow into downstream stages. If `$sort` must process millions of documents after stages that break index support, hinting the input index will not eliminate that sort.

Example pipeline:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      status: "PAID"
    }
  },
  {
    $group: {
      _id: "$customerId",
      totalSpent: { $sum: "$total" }
    }
  },
  {
    $sort: {
      totalSpent: -1
    }
  }
]);
~~~

Sorting by `totalSpent` sorts **computed aggregate values**. An index on the raw `total` field does not directly satisfy sorting by per-customer totals after `$group`.

### 14.3. Explaining Aggregation

~~~javascript
db.orders.explain("executionStats").aggregate(
  [
    {
      $match: {
        tenantId: "TENANT-01",
        status: "PAID"
      }
    },
    {
      $sort: {
        createdAt: -1,
        _id: -1
      }
    },
    {
      $limit: 20
    }
  ],
  {
    hint: "idx_tenant_status_created"
  }
);
~~~

Inspect both the input collection access plan and downstream aggregation stages. Explain layouts vary by engine/version; do not compare one top-level metric while ignoring expensive pipeline stages.

---

## 15. Hint in the Java Driver and Spring Data MongoDB

### 15.1. Java Sync Driver

The MongoDB Java Sync Driver supports specifying an index on `FindIterable`, typically via `hintString()` for index names or `hint()` for key patterns.

~~~java
import com.mongodb.ExplainVerbosity;
import com.mongodb.client.FindIterable;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Sorts.descending;
import static com.mongodb.client.model.Sorts.orderBy;

public class OrderPlanExample {

    public static Document explainCandidate(
            MongoCollection<Document> orders) {

        FindIterable<Document> query = orders.find(
                and(
                    eq("tenantId", "TENANT-01"),
                    eq("customerId", "CUS-101"),
                    eq("status", "PAID")
                )
            )
            .sort(
                orderBy(
                    descending("createdAt"),
                    descending("_id")
                )
            )
            .limit(20)
            .hintString(
                "idx_tenant_customer_status_recent"
            );

        return query.explain(
            ExplainVerbosity.EXECUTION_STATS
        );
    }
}
~~~

In a real project, `orders` comes from a connected `MongoClient`, and the query should include the exact same projection as the live API so measurements reflect actual workload. Verify exact methods/packages against your driver version.

To specify a key pattern:

~~~java
FindIterable<Document> query = orders
    .find(eq("tenantId", "TENANT-01"))
    .hint(
        new Document("tenantId", 1)
            .append("customerId", 1)
    );
~~~

Never let an index name in application code depend on a migration that may not have run in every environment. If the index is absent, the operation can fail and break the endpoint using the hint.

### 15.2. Spring Data MongoDB

In Spring Data MongoDB, on supported versions, `Query` can specify an index name via `withHint()`.

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = Query.query(
    Criteria.where("tenantId").is("TENANT-01")
        .and("customerId").is("CUS-101")
        .and("status").is("PAID")
);

query.with(
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("_id")
    )
);

query.limit(20);

query.withHint(
    "idx_tenant_customer_status_recent"
);

var orders = mongoTemplate.find(
    query,
    OrderDocument.class,
    "orders"
);
~~~

This snippet assumes `mongoTemplate` and a matching `OrderDocument` entity class. If the entity uses `@Field`, `@Id`, or custom converters, verify the actual BSON field names and index keys.

In production, only add `withHint` after gathering evidence and having a rollback plan. Never treat `hint` as a "guaranteed fast" setting immune to data drift or MongoDB upgrades.

### 15.3. Log Query Shapes Instead of Sensitive Data

When investigating a slow endpoint, it is useful to log:

- Operation/API name.
- Tenant tier or data-size bucket, not necessarily raw tenant IDs.
- Query shape or filter fields.
- Hinted index name, if any.
- Latency and sample rate.
- Query comment/tracing ID when permitted.
- MongoDB version/cluster/deployment when comparing.

Never log full documents or PII just to prove an index was used.

---

## 16. When Hint Produces Slower Results: Root Cause Analysis

### 16.1. Unselective Index

If `status: "ACTIVE"` matches 95% of the collection, forcing a single-field `status` index can require scanning massive numbers of keys and fetching many documents, whereas `COLLSCAN` may fare better in some situations.

~~~javascript
db.users.find({
  status: "ACTIVE"
}).hint({
  status: 1
});
~~~

Do not assume every equality predicate yields a selective index.

### 16.2. Index Does Not Support Sort

An index containing only `tenantId` filters by tenant but fails to provide `createdAt DESC, _id DESC` order. The database must perform an extra sort.

### 16.3. Index Lacks Fields Needed for Reading

A query needing only document IDs and status can be covered by a suitable index. Yet if projection requests large `note` or `items` fields outside the index, the server must fetch documents.

Forcing an index just because `totalKeysExamined` is low while ignoring `totalDocsExamined` can mask heavy fetch costs.

### 16.4. Selectivity Varies Across Tenants

A small tenant has 500 orders; a huge tenant has 20 million orders. The exact same query shape can exhibit vastly different cost profiles depending on parameter values and data distribution.

When testing hints, collect representative samples covering:

- Small and large tenants.
- Common and rare status values.
- Narrow and wide date ranges.
- First pages and deep pages.
- `limit(20)` and unbounded cases.
- Queries with differing sorts/projections.

### 16.5. Oversized Indexes Increase Cache Pressure

A compound index with many fields can grow substantially larger. Once the index working set no longer fits in RAM/cache, unrelated queries can slow down even if the tested endpoint appears fast.

### 16.6. Write Amplification

Every index on a collection adds maintenance work on inserts, updates, and deletes touching indexed fields. Any proposed index must be evaluated on **the write path as well**.

Do not optimize a low-traffic read query by adding a heavy index that degrades throughput across millions of writes.

### 16.7. The Planner Already Picked a Better Index

If the baseline planner picked index A and you forced index B, B is very likely suboptimal under current data and query conditions. Verify with explain and benchmarks instead of assuming the planner is always wrong.

---

## 17. When Should or Shouldn't You Use `hint` in Production?

### 17.1. Situations Where It May Be Considered

- A critical query suffered a measured regression and a specific index has proven superior on a representative workload.
- A temporary mitigation is needed while investigating the query planner, plan cache, or data shift.
- The query shape is stable, the index is managed via migrations/rollouts, and monitoring is active.
- Configuration allows toggling the hint off easily without ripping out large chunks of code.
- You verified the filter does not fall into an incomplete sparse/partial index edge case.

### 17.2. Situations to Avoid

- Baseline has not been measured and you do not know what the planner chose.
- The index was just created and is not yet present across all environments.
- Queries change frequently with dynamic filter/sort combinations.
- Data selectivity shifts dramatically across tenants or over time.
- Migrations might hide, drop, or rename the index.
- Full-text or time-series queries where hint hits API limitations.
- Full collection results are needed, yet a sparse/partial index omits documents.
- Trying to use `hint` as a band-aid for missing indexes, bloated projections, or flawed schemas.

### 17.3. Prioritize Fixing the Root Cause

If index C dramatically beats the baseline:

1. Confirm index C exists and is eligible for planner consideration.
2. Check whether the query filters/sorts cleanly so the planner picks C naturally.
3. Check whether index filters or query settings are interfering.
4. Benchmark on large datasets across varied parameter values.
5. Check whether overlapping indexes can be removed or the query adjusted so the planner picks the right plan on its own.
6. Keep a long-term hint only with documented justification and active monitoring.

A well-proposed index should **be evaluated across the whole workload**, not proven by a single `hint` in mongosh.

---

## 18. Evaluating a New Index as a System Change

### 18.1. Do Not Create Indexes Ad-Hoc in Production Just to Experiment

Building an index on a large collection consumes CPU, disk I/O, cache, and storage. Creating a unique index can also fail if duplicate keys already exist. Moreover, creating, dropping, or hiding an index can impact the plan cache and other query shapes.

Controlled testing should start with:

- A representative staging snapshot or dataset.
- Data distribution statistics.
- Proper index management permissions.
- Monitoring of resources and build duration.
- A canary/rollback plan.
- Records of index name, key pattern, collation, and unique/sparse/partial options.

### 18.2. Hiding an Index as an Evaluation Tool

On MongoDB versions supporting hidden indexes, you can temporarily hide an index from the planner to verify whether other queries still rely on it.

**Do not confuse hiding an index with dropping an index:**

- The index remains stored on disk.
- Writes still incur index maintenance overhead.
- The query planner will not pick a hidden index.
- Hinting a hidden index returns an error.
- Unhiding after the experiment restores planner eligibility, though final plan choice still depends on data, cache, and configuration.

Hiding/unhiding alters workload-wide behavior; perform it in production only with approval and proper observability.

### 18.3. An Old Index May Serve Other Queries

An index A that performs poorly for the "recent orders" endpoint might still:

- Serve customer lookup queries.
- Support per-tenant reports.
- Enforce a unique constraint.
- Support another sort/filter pattern.
- Serve as a fallback when another index is hidden or dropped.

Never drop an index simply because a `hint` proved index B faster for one query.

### 18.4. Monitoring Index Usage

~~~javascript
db.orders.getIndexes();
db.orders.stats();

db.orders.aggregate([
  { $indexStats: {} }
]);
~~~

`$indexStats` reports index access counts over a statistics window. Counters reset on server restarts or operational events. A rarely queried index may still be essential to enforce uniqueness. Combine access stats with query logs, controlled profiling, and application inventories before deciding to drop an index.

---

## 19. Formal Verification Workflow for a Proposed Index

A solid proposal should cover all of these steps.

### Step 1 — Describe the Query and SLA

~~~text
Operation: GetPaidOrdersByCustomer
Filter:
  tenantId = ?
  customerId = ?
  status = PAID
Sort:
  createdAt DESC, _id DESC
Projection:
  orderNo, createdAt, total, _id
Limit:
  20
Traffic:
  collect real measurements
Latency target:
  p95/p99 per SLA
Cardinality:
  order distribution across tenant/customer/status
~~~

Never write "orders query is slow" and propose a random index.

### Step 2 — Inventory Existing Indexes

~~~javascript
db.orders.getIndexes();
~~~

Record names, key patterns, options, and similar indexes. Avoid duplicating an index if an equivalent one already exists.

### Step 3 — Measure Baseline

~~~javascript
db.orders
  .find(queryFilter, queryProjection)
  .sort(querySort)
  .limit(20)
  .explain("executionStats");
~~~

Record the plan, keys/docs examined, returned count, and sort/fetch stages.

### Step 4 — State the Index Hypothesis

Example:

~~~text
Candidate:
  { tenantId:1, customerId:1, status:1,
    createdAt:-1, _id:-1 }

Hypothesis:
  Tightens equality bounds on tenant/customer/status.
  Supports sorting recent orders.
  Cuts keys/docs examined when status is uncommon.
  Keeps added write cost within acceptable thresholds.
~~~

### Step 5 — Create the Index in an Appropriate Test Environment

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    customerId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "idx_tenant_customer_status_recent"
  }
);
~~~

### Step 6 — Compare the Same Query with `hint`

~~~javascript
db.orders
  .find(queryFilter, queryProjection)
  .sort(querySort)
  .limit(20)
  .hint("idx_tenant_customer_status_recent")
  .explain("executionStats");
~~~

Compare metrics against the baseline and other candidate indexes under identical conditions.

### Step 7 — Verify No Missing or Wrong Results

Especially when dealing with:

- Sparse/partial indexes.
- Collation.
- Arrays/multikey.
- Queries with sort + limit.
- Tenant/permission filters.
- Documents with missing/null fields.
- Concurrent writes shifting result sets.

An index that appears faster while dropping records **fails verification**.

### Step 8 — Benchmark End-to-End

Measure API p50/p95/p99 latency and throughput at representative concurrency. Monitor CPU/RAM/disk/cache, network, write latency, and replication lag. Repeat across diverse filter value sets.

### Step 9 — Assess Total Cost

Compare:

- Read gains.
- Index storage footprint.
- Build cost.
- Write amplification.
- Index overlap/redundancy.
- Plan cache behavior changes.
- Operational risk from coupling app code to index names.

### Step 10 — Rollout and Rollback

If proceeding with deployment:

1. Create the index and confirm it is ready.
2. Canary a subset of traffic if possible.
3. Observe actual plans and latency.
4. If using a hint, make it configurable for quick toggle/rollback.
5. Monitor for query regressions and write overhead.
6. Never drop old indexes until confirming all related queries remain well served.
7. Document experiment results and schedule a review date for the hint/index.

---

## 20. Decision Matrix: What to Do After Testing a Hint?

| Measured Outcome | Potential Meaning | Action |
|---|---|---|
| Baseline planner already picked the good candidate | Index fits and optimizer works properly | Usually no hint needed |
| Hinted candidate sharply cuts keys/docs examined and p95 | Candidate is valuable | Validate full workload and write cost before rollout |
| Hinted candidate is faster in explain, yet app p95 unchanged | Bottleneck may lie outside DB scan | Check network/driver/cache/serialization |
| Hinted candidate is slower than baseline | Index does not fit current query/data | Do not keep hint; analyze bounds/sort/fetch |
| Sparse hint returns incomplete data | Does not cover the full result set | Reject approach or fix predicate/index |
| Hint fails with index not found | Requested index does not exist | Check migration/index deployment |
| Hinting a hidden index errors out | Hidden indexes cannot be used | Check index state; do not force workarounds |
| Hint is ignored contrary to expectations | Index filter or query settings may be active | Check configuration and explain |
| Candidate helps reads, yet spikes write p99 | Trade-off breaches SLA | Design a different index or adjust workload |
| Results vary widely across tenants | Distribution skew | Evaluate additional query shapes/selectivity and workload-specific design |

The goal is choosing an option with **low total cost and predictable behavior**, not forcing an index onto every query.

---

## 21. Common Misconceptions

### "With a hint, MongoDB always uses that exact index"

Not unconditionally. The index must exist and be valid. Hidden indexes, `$text`, time-series key patterns, query settings/index filters, and other limits can cause errors or override behavior.

### "Hint creates the index if it doesn't exist"

False. `createIndex()` creates indexes; `hint()` merely specifies an existing index or collection scan per API rules.

### "IXSCAN means the query is already optimized"

False. It can still scan massive numbers of keys and fetch many documents. Check `totalKeysExamined`, `totalDocsExamined`, `SORT`, latency, and result correctness.

### "A hint is always faster than letting the planner choose"

False. The planner may choose a superior plan. Forcing an ill-suited access path can raise CPU, I/O, or sorting cost.

### "`executionTimeMillis` is the user's latency"

False. It omits full network, driver, serialization, and application overhead; explain also behaves differently regarding plan selection and caching.

### "Explain proves what the production plan cache is using"

Not completely. Explain bypasses existing plan cache entries and inserts none. Observe live runtime behavior when investigating cache issues.

### "Rejected plans are useless for all queries"

False. An index rejected for one query shape can be vital for another query.

### "A partial index always serves any query with the same sort key"

False. The query must not require documents outside the partial index's filter scope.

### "Forcing a sparse index to count the whole collection is still accurate"

Unreliable. Sparse indexes omit documents lacking the indexed field; forcing them can undercount.

### "An outer aggregation hint makes `$lookup` use the foreign collection's index"

False. An aggregation hint on the input collection does not apply to `$lookup`/`$graphLookup`.

### "A hidden index can still be used via hint even though the planner doesn't see it"

False. Hinting a hidden index is rejected.

### "Changing key order in a compound index doesn't matter"

False. Equality prefix, sort, range, and direction all depend on key order.

### "One benchmark on tiny data is enough"

False. You need realistic distribution, concurrency, p95/p99, cache behavior, read/write mix, and repeated runs.

### "An index rarely hit in `$indexStats` should be dropped immediately"

False. It may enforce a unique constraint or serve rare but critical jobs; counters also reset over time.

### "Putting a hint in code and forgetting about it is fine"

Not recommended. Indexes can be renamed, hidden, or dropped, and data distribution shifts. Long-lived hints require monitoring and a review/rollback plan.

---

## 22. Practice Exercises

### Exercise 1 — Baseline and Two Candidate Indexes

Using the `query_plan_lab` dataset:

1. Run the query listing `PAID` orders for a customer, sorted `createdAt DESC/_id DESC`, limit 20.
2. Run explain without a hint.
3. Hint `idx_tenant_customer`.
4. Hint `idx_tenant_customer_status_recent`.
5. Compare `totalKeysExamined`, `totalDocsExamined`, `winningPlan`, and `SORT`.
6. Explain why 12 documents are insufficient to prove real-world latency.

### Exercise 2 — Understanding `indexBounds`

Create the index:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_tenant_status_time_lab" }
);
~~~

Run:

~~~javascript
db.orders.find({
  tenantId: "TENANT-01",
  status: "PAID",
  createdAt: {
    $gte: ISODate("2026-11-05T00:00:00Z")
  }
}).hint("idx_tenant_status_time_lab")
  .explain("executionStats");
~~~

Analyze equality bounds on tenant/status, range bounds on `createdAt`, examined keys/docs, and the impact of adding a secondary sort on `_id`.

### Exercise 3 — Forcing a Collection Scan

Run the same query with and without:

~~~javascript
.hint({ $natural: 1 })
~~~

What changes in the winning plan? Why should natural order not serve as a chronological pagination contract?

### Exercise 4 — Hinting a Nonexistent Index

Call `hint("index_missing")` on the lab collection. Record the error. Write error-handling logic capable of detecting a missing index migration. Why can a hardcoded index name break a production endpoint after a schema change?

### Exercise 5 — Sparse Indexes and Completeness

Create:

~~~javascript
db.users.insertMany([
  { _id: 1, name: "An", email: "an@example.test" },
  { _id: 2, name: "Binh" },
  { _id: 3, name: "Chi", email: null }
]);

db.users.createIndex(
  { email: 1 },
  { sparse: true, name: "idx_lab_sparse_email" }
);
~~~

Compare document counts from:

~~~javascript
db.users.find({}).toArray();
db.users.find({}).hint("idx_lab_sparse_email").toArray();
~~~

Analyze why you must not force a sparse index for a query requesting all users.

### Exercise 6 — Partial Index for `ACTIVE` Only

Create the index:

~~~javascript
db.users.createIndex(
  { score: -1 },
  {
    partialFilterExpression: { status: "ACTIVE" },
    name: "idx_lab_active_score"
  }
);
~~~

Which queries are compatible?

~~~javascript
db.users.find({ status: "ACTIVE" });
db.users.find({ status: "INACTIVE" });
db.users.find({});
~~~

Explain using the set of documents covered by the partial index. Do not assume `hint` legitimizes a query lacking a matching filter.

### Exercise 7 — Aggregation and `$lookup`

Given `orders` and `order_items` collections, write a pipeline matching by tenant and using `$lookup` on `orderId`.

- Hint an index on `orders`.
- Create `{orderId: 1}` on `order_items`.
- Explain why hinting `orders` does not apply directly to the foreign collection.
- Measure overall execution plan and latency on representative data.

### Exercise 8 — Query Settings / Index Filters

Investigate index filters or query settings supported in your MongoDB environment. Describe a scenario where `hint` is ignored due to active configuration. Distinguish a query-level hint from cluster-level settings and the plan cache.

Never modify production query settings without a runbook and proper authorization.

### Exercise 9 — Java Driver

Write a Java method accepting a `MongoCollection<Document>` and a string `indexName`. Have it run a query with `hintString(indexName)` and `ExplainVerbosity.EXECUTION_STATS`, printing `nReturned`, `totalKeysExamined`, and `totalDocsExamined`. Handle errors if the index does not exist.

### Exercise 10 — Production Index Proposal

A collection holds 20 million orders: 80% `PAID`, 15% `CANCELED`, 5% `OPEN`. A dashboard reads the most recent `OPEN` orders per tenant at 100 requests/second while the system processes 500 writes/second.

Tasks:

1. Propose a standard compound index and an alternative partial index.
2. Explain which queries each index can serve.
3. Plan measurements for p95/p99, keys/docs examined, index size, and write amplification.
4. Assess whether a production hint is needed.
5. Design a canary and rollback plan.
6. Identify risks of optimizing only the dashboard while neglecting historical endpoints.

---

## 23. Review Questions

1. What is the role of `hint()` relative to the query planner?
2. What is the difference between hinting an index name vs. hinting a key pattern?
3. Does `hint()` create an index?
4. What is `hint({$natural:1})` used for? Why should it not replace business sorting?
5. When might the planner pick `COLLSCAN` even when an index exists?
6. Why is `IXSCAN` alone insufficient to prove a query is optimal?
7. Which costs do `totalKeysExamined` and `totalDocsExamined` represent?
8. Why must you inspect `SORT` and `FETCH`?
9. What does `indexBounds` help reveal?
10. Why must filter, sort, projection, limit, and collation remain identical when comparing indexes?
11. How does `executionStats` differ from `allPlansExecution`?
12. How does explain interact with the plan cache?
13. Is `executionTimeMillis` equivalent to API p95 latency?
14. Why does hinting a hidden or nonexistent index error out?
15. Can you force an arbitrary index on a `$text` query?
16. What restriction applies to hinting on time-series collections?
17. How can index filters or query settings affect `hint`?
18. Why can a sparse index return incomplete results for a full-collection query?
19. What condition must a query meet to be fully served by a partial index?
20. Does an aggregation hint apply to the foreign side of `$lookup`?
21. Why does varying tenant selectivity impact index effectiveness?
22. How can a new index increase write costs?
23. When should you avoid keeping long-term hints in source code?
24. What evidence is needed before deciding to drop an old index?
25. How do you roll back when deploying an index or hint slows down production queries?

## 24. Summary

`hint()` is an important tool for **verifying a proposed index plan**. It lets you request a specific index by name or key pattern, or use `$natural` to test a collection scan. However, `hint` carries technical limitations and can worsen a query if you ignore predicates, sort order, document fetch volume, and index state.

A reliable evaluation workflow consists of:

1. **Clearly specifying the query shape and SLA.**
2. **Checking `getIndexes()` and baseline explain without a hint.**
3. **Creating candidate indexes suited to the workload.**
4. **Using `hint` to compare plans and execution statistics on the exact same query.**
5. **Verifying no missing or incorrect results.**
6. **Benchmarking real latency, concurrency, and representative data distributions.**
7. **Measuring index storage and write overhead.**
8. **Deploying with canarying, monitoring, and rollback.**

Never turn `hint` into an emotional override of the planner. An index should be kept when it **returns accurate results, reduces total cost on the real workload, and remains sustainable as data and traffic evolve**.

## Official MongoDB References

- [MongoDB Manual — cursor.hint()](https://www.mongodb.com/docs/manual/reference/method/cursor.hint/)
- [MongoDB Manual — db.collection.explain()](https://www.mongodb.com/docs/manual/reference/method/db.collection.explain/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual — Query Plans](https://www.mongodb.com/docs/manual/core/query-plans/)
- [MongoDB Manual — Use Indexes to Sort Query Results](https://www.mongodb.com/docs/manual/tutorial/sort-results-with-indexes/)
- [MongoDB Manual — Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/)
- [MongoDB Manual — Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/)
- [MongoDB Manual — Sparse Indexes](https://www.mongodb.com/docs/manual/core/index-sparse/)
- [MongoDB Manual — Hidden Indexes](https://www.mongodb.com/docs/manual/core/index-hidden/)
- [MongoDB Manual — db.collection.aggregate()](https://www.mongodb.com/docs/manual/reference/method/db.collection.aggregate/)
- [MongoDB Manual — Query Settings](https://www.mongodb.com/docs/manual/reference/query-settings/)
- [MongoDB Manual — $planCacheStats](https://www.mongodb.com/docs/manual/reference/operator/aggregation/planCacheStats/)
- [MongoDB Manual — $indexStats](https://www.mongodb.com/docs/manual/reference/operator/aggregation/indexStats/)
- [MongoDB Java Sync Driver — Explain Query Results](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/aggregation-examples/)
- [Spring Data MongoDB — Query Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html)
