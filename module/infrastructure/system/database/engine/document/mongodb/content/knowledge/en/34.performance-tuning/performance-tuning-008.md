# Optimizing Aggregations, Joins, and Precomputed Summaries in MongoDB

## Lesson Objectives

As a MongoDB system grows, a query that runs smoothly on a few thousand documents can become a major bottleneck once data reaches millions of records, read/write rates climb, tenants multiply, and dashboards demand near-instant responses. Three areas commonly consume the most resources:

1. **Aggregation pipelines:** filtering, sorting, grouping, computing, and reshaping data across multiple stages.
2. **Joins via `$lookup`:** combining data across collections, potentially multiplying intermediate rows and triggering heavy index/collection lookups.
3. **Precomputed summaries (precomputed aggregates / materialized views):** maintaining pre-calculated results to trade read-time CPU/I/O for background or write-time computation.

Proper optimization is not simply "always put `$match` first," "add lots of indexes," or "cache everything." The MongoDB query optimizer applies its own rewrites; a join can change business semantics if `$limit` is moved; and a precomputed summary table can be fast yet wrong if it misses updates, deletes, late events, or order state transitions.

This lesson belongs to **Database Engine Document MongoDB → Performance Tuning → Optimizing Aggregations, Joins, and Precomputed Summaries in MongoDB**.

After this lesson, you will be able to:

- Read the structure and cost profile of an aggregation pipeline.
- Optimize `$match`, `$sort`, `$limit`, `$project`, `$group`, `$unwind`, `$facet`, and `$setWindowFields` while preserving query semantics.
- Explain when an index satisfies filtering + sorting vs. when stages sort/group in memory or spill to disk.
- Use `explain("executionStats")`, `totalKeysExamined`, `totalDocsExamined`, `nReturned`, and timings to measure rather than guess.
- Design equality and correlated-pipeline `$lookup`s, index foreign collections, cap fan-out, and eliminate N+1 patterns.
- Weigh embedding, denormalization, application-side batch queries, and `$lookup` based on data size and churn.
- Build per-day/tenant summary collections using `$group` + `$merge` with unique keys and explicit timezones.
- Compare full refreshes, scheduled refreshes, and incremental refreshes via Change Streams or outboxes.
- Handle inserts, updates, deletes, late-arriving events, duplicate processing, concurrency, and reprocessing.
- Distinguish eventual consistency from data correctness and track report freshness using `computedAt` and watermarks.
- Benchmark performance on production-like data and design observability, rollout, and rollback policies.
- Write illustrative pipelines in `mongosh` and the Java Sync Driver.

> **Principle:** Every optimization must preserve **the exact result set, ordering, data scope, and time boundaries** required by the business. A fast pipeline that drops transactions or leaks another tenant's data is broken.

---

## 1. Big Picture: Compute at Read Time or Precompute Before Reads?

Suppose an admin dashboard displays daily revenue per tenant.

A direct on-demand query:

~~~text
GET /dashboard/revenue?from=...&to=...
      |
      v
db.orders.aggregate(
  $match -> $group -> $sort -> ...
)
      |
      v
Millions of orders scanned/grouped to return a few dozen rows
~~~

A precomputed approach:

~~~text
Order created/paid/cancelled
          |
          v
Aggregation worker / Change Stream / scheduled job
          |
          v
dailyOrderSales
          |
          v
GET /dashboard/revenue
          |
          v
Find 30 pre-aggregated documents
~~~

The second option slashes read latency, yet introduces:

- More complex refresh logic.
- Lag between source data and the summary collection.
- Risk of stale or missing aggregates.
- Backfill, replay, and reconciliation requirements.
- Extra write, storage, and index overhead.
- Recomputing/migrating summaries whenever business rules change.

The design question must be: **which calculations belong at read time, which should be maintained ahead of time, and what data freshness is acceptable?**

### 1.1. Three Performance Layers

| Layer | Question | Tools |
|---|---|---|
| **Query shape** | Are we filtering, sorting, or joining in the wrong order? | Pipeline rewrites, projections, limits |
| **Physical access** | Index scan or collection scan? Join fan-out? | Compound indexes, `explain`, schema |
| **Architecture** | Are we recomputing the exact same result repeatedly? | Materialized views, CDC, caching, pre-aggregation |

Do not jump straight to a materialized view when a missing index is the sole problem; conversely, even a well-indexed aggregation becomes expensive if every dashboard view groups tens of millions of orders.

---

## 2. Illustrative Dataset

We use the `aggregation_perf_lab` database with three main collections:

- `orders`: source of truth for orders.
- `customers`: customer profiles referenced by `customerId`.
- `dailyOrderSales`: precomputed daily revenue summaries.

Timestamps, monetary amounts, and IDs are illustrative only.

### 2.1. Orders

~~~javascript
use aggregation_perf_lab

db.orders.insertMany([
  {
    _id: "ORD-101",
    tenantId: "tenant-a",
    customerId: "CUS-101",
    status: "PAID",
    createdAt: ISODate("2026-11-10T01:00:00Z"),
    paidAt: ISODate("2026-11-10T01:05:00Z"),
    currency: "VND",
    totalVnd: NumberLong("500000"),
    items: [
      { sku: "SKU-1", qty: 2, unitPriceVnd: NumberLong("150000") },
      { sku: "SKU-2", qty: 1, unitPriceVnd: NumberLong("200000") }
    ],
    updatedAt: ISODate("2026-11-10T01:05:00Z")
  },
  {
    _id: "ORD-102",
    tenantId: "tenant-a",
    customerId: "CUS-102",
    status: "PAID",
    createdAt: ISODate("2026-11-10T03:00:00Z"),
    paidAt: ISODate("2026-11-10T03:02:00Z"),
    currency: "VND",
    totalVnd: NumberLong("850000"),
    items: [
      { sku: "SKU-3", qty: 1, unitPriceVnd: NumberLong("850000") }
    ],
    updatedAt: ISODate("2026-11-10T03:02:00Z")
  },
  {
    _id: "ORD-103",
    tenantId: "tenant-a",
    customerId: "CUS-101",
    status: "PENDING",
    createdAt: ISODate("2026-11-11T05:00:00Z"),
    paidAt: null,
    currency: "VND",
    totalVnd: NumberLong("400000"),
    items: [
      { sku: "SKU-1", qty: 1, unitPriceVnd: NumberLong("400000") }
    ],
    updatedAt: ISODate("2026-11-11T05:00:00Z")
  },
  {
    _id: "ORD-104",
    tenantId: "tenant-b",
    customerId: "CUS-201",
    status: "PAID",
    createdAt: ISODate("2026-11-10T04:00:00Z"),
    paidAt: ISODate("2026-11-10T04:05:00Z"),
    currency: "VND",
    totalVnd: NumberLong("900000"),
    items: [
      { sku: "SKU-8", qty: 1, unitPriceVnd: NumberLong("900000") }
    ],
    updatedAt: ISODate("2026-11-10T04:05:00Z")
  }
]);

db.customers.insertMany([
  {
    _id: "CUS-101",
    tenantId: "tenant-a",
    displayName: "Customer A",
    segment: "LOYAL",
    active: true
  },
  {
    _id: "CUS-102",
    tenantId: "tenant-a",
    displayName: "Customer B",
    segment: "NEW",
    active: true
  },
  {
    _id: "CUS-201",
    tenantId: "tenant-b",
    displayName: "Customer C",
    segment: "LOYAL",
    active: true
  }
]);
~~~

In real applications, ensure `totalVnd` is calculated and validated by business rules. Use `NumberLong` for whole-unit VND amounts or `Decimal128` for fractional currencies; never assume JavaScript `double` fits all financial calculations.

### 2.2. Candidate Indexes

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    paidAt: -1,
    _id: -1
  },
  {
    name: "idx_orders_tenant_status_paidAt_id"
  }
);

db.orders.createIndex(
  {
    tenantId: 1,
    customerId: 1
  },
  {
    name: "idx_orders_tenant_customer"
  }
);

db.customers.createIndex(
  {
    tenantId: 1,
    segment: 1
  },
  {
    name: "idx_customers_tenant_segment"
  }
);
~~~

These indexes are **candidates**. `customers._id` already has the default unique index. On a tiny dataset, the optimizer may still pick a collection scan; that does not mean the index is wrong. Test at production-like data scale and workloads.

---

## 3. Cost Nature of an Aggregation Pipeline

A pipeline:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-a" } },
  { $sort: { paidAt: -1 } },
  { $group: { _id: "$status", count: { $sum: 1 } } },
  { $sort: { count: -1 } }
]);
~~~

incurs several distinct cost types:

- **I/O:** reading documents and index keys from storage or cache.
- **CPU:** evaluating predicates, parsing expressions, hashing group keys, matching join keys.
- **Memory:** sort buffers, `$group` hash tables, window states, intermediate arrays.
- **Disk spill:** blocking stages exceeding allowed memory thresholds.
- **Network:** shuffling data across shards/routers or returning huge outputs.
- **Write overhead:** materializing outputs into a collection via `$merge` or `$out`.

### 3.1. Streaming vs. Blocking Stages

| Stage | Execution Tendency | Key Considerations |
|---|---|---|
| `$match` | Can stream / use indexes | Push selective predicates close to the source |
| `$project` / `$set` | Transforms document by document | Trims payload when needed; does not guarantee index use |
| `$unwind` | Can multiply row count | Cardinality explosion |
| `$sort` | Blocking unless backed by an index | Memory / disk spill / top-k |
| `$group` | Typically accumulates state | Group cardinality, memory |
| `$lookup` | Depends on join strategy and indexes | Foreign scans, fan-out |
| `$facet` | Splits input into parallel sub-pipelines | Memory and output size limits |
| `$setWindowFields` | Window calculations | Partitioning, sorting, memory |
| `$merge` | Writes results into target collection | Extra writes and consistency |

### 3.2. Pipeline Order Is Logical; the Plan Is Execution

The MongoDB optimizer may hoist `$match`, coalesce `$sort` + `$limit`, or optimize projections depending on query shape and version. Writing 8 stages does not mean the engine runs 8 naive passes.

Always inspect `explain()` to verify the actual execution plan.

### 3.3. Optimizations Must Preserve Semantics

Suppose the requirement is "20 most recent orders from VIP customers." Placing `$limit: 20` *before* filtering VIP customers from `$lookup` could leave only a few VIP orders even when more exist further back. Changing stage order **alters results**, not just performance.

---

## 4. `$match`: Filtering Early and Index-Friendly

### 4.1. Explicit Time-Range Predicates

~~~javascript
const from = ISODate("2026-11-01T00:00:00Z");
const to = ISODate("2026-12-01T00:00:00Z");

db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-a",
      status: "PAID",
      paidAt: {
        $gte: from,
        $lt: to
      }
    }
  },
  {
    $group: {
      _id: null,
      totalVnd: { $sum: "$totalVnd" },
      orders: { $sum: 1 }
    }
  }
]);
~~~

Compared to placing `$match` after `$group`, filtering at the source drastically reduces rows processed. Prioritize selective predicates like tenant, status, and date ranges.

### 4.2. Avoid Transforming Indexed Fields Inside Filters When Possible

A pattern that struggles to leverage standard indexes:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      $expr: {
        $eq: [
          { $year: "$paidAt" },
          2026
        ]
      }
    }
  }
]);
~~~

When querying a UTC year range, express it directly:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      paidAt: {
        $gte: ISODate("2026-01-01T00:00:00Z"),
        $lt: ISODate("2027-01-01T00:00:00Z")
      }
    }
  }
]);
~~~

Direct field ranges enable clean index range scans. If business logic uses a local timezone, compute the exact UTC boundary timestamps for that timezone rather than assuming UTC midnight.

### 4.3. Not Every `$match` Can Move to the Start

If a predicate depends on a computed field:

~~~javascript
[
  {
    $addFields: {
      netVnd: {
        $subtract: ["$grossVnd", "$refundVnd"]
      }
    }
  },
  { $match: { netVnd: { $gte: 100000 } } }
]
~~~

The engine cannot push the `netVnd` filter ahead of its computation without an equivalent rewrite. The optimizer only reorders stages when dependency rules guarantee identical results.

### 4.4. Stages with "First-Stage" Requirements

Stages like `$geoNear`, `$search`, or `$vectorSearch` must occupy the first stage of a pipeline. You cannot apply "always put `$match` first" blindly.

When using search or geo stages, pass predicates inside their dedicated `query`/`filter` options rather than misplacing `$match`.

### 4.5. Tenant Scope Is Always Mandatory

In multi-tenant systems:

~~~javascript
{
  tenantId: authenticatedContext.tenantId,
  status: "PAID"
}
~~~

`tenantId` must come from the authenticated context—never accept arbitrary raw BSON filters from clients. A fast pipeline missing a tenant filter is a security breach.

---

## 5. Compound Indexes and the ESR Guideline

**ESR** is a common heuristic for ordering compound index keys:

- **Equality:** fields matched with equality predicates.
- **Sort:** fields used for sorting.
- **Range:** fields filtered with ranges.

Example:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  paidAt: -1,
  _id: -1
});
~~~

For query:

~~~javascript
db.orders.find({
  tenantId: "tenant-a",
  status: "PAID"
}).sort({
  paidAt: -1,
  _id: -1
}).limit(20);
~~~

The index returns pre-sorted entries within the equality prefix, avoiding a blocking sort.

### 5.1. Ranges Change Index Choices

Query:

~~~javascript
db.orders.find({
  tenantId: "tenant-a",
  status: "PAID",
  paidAt: { $gte: ISODate("2026-11-01T00:00:00Z") }
}).sort({
  paidAt: -1,
  _id: -1
});
~~~

Both the range predicate and the sort target `paidAt`. Actual efficiency depends on data distribution and planner selection. ESR is not a rigid law, especially when a range predicate is ultra-selective or sorting dominates cost.

### 5.2. Longer Indexes Are Not Automatically Faster

Adding every field into a compound index can:

- Inflate storage and RAM usage.
- Slow down inserts, updates, and deletes.
- Add more candidate plans for the optimizer to weigh.
- Fail to speed up queries if fields sit in unusable positions.
- Still fail to eliminate sorts if directions/semantics clash.

Measure `keysExamined`, `docsExamined`, execution time, and index size.

### 5.3. Covered Queries Do Not Automatically Apply to All Pipelines

A query is covered when filters, sorts, and projections are all satisfied by the index. Yet after `$group`, `$lookup`, computed expressions, or extra field references, the planner must read documents. Never assume every aggregation on indexed fields is covered.

### 5.4. Collations and Data Types

String equality and sorting depend on matching collations between query and index. `Decimal128`, `NumberLong`, strings, and `Date` values follow distinct comparison semantics. Keep types consistent across stored documents and query predicates for both accuracy and index eligibility.

---

## 6. `$sort`, `$limit`, and Top-K Optimization

### 6.1. Sort Using an Index Before Joining

To fetch the 20 newest paid orders:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-a",
      status: "PAID"
    }
  },
  {
    $sort: {
      paidAt: -1,
      _id: -1
    }
  },
  { $limit: 20 },
  {
    $project: {
      _id: 1,
      paidAt: 1,
      totalVnd: 1,
      customerId: 1
    }
  }
]);
~~~

With a matching compound index, the engine returns the first 20 matches quickly. `_id` breaks ties deterministically when multiple orders share the same `paidAt`.

### 6.2. `$sort + $limit` Coalescence

When no cardinality-changing stage sits between them, MongoDB can coalesce `$sort` + `$limit` into a top-k bounded sort, cutting memory vs. sorting the full set. If `$skip` sits in between, the optimizer adjusts the tracked bound (`skip + limit`).

Never assume this optimization triggers in every pipeline or version; verify with `explain()`.

### 6.3. Avoid Deep `$skip`

~~~javascript
[
  { $sort: { paidAt: -1, _id: -1 } },
  { $skip: 200000 },
  { $limit: 20 }
]
~~~

Deep offset pagination scans and discards huge numbers of entries, scaling latency linearly with offset. For feeds and order lists, keyset pagination is usually far better.

### 6.4. Keyset Pagination

After the first page, store the last `(paidAt, _id)` pair. Next page:

~~~javascript
const lastPaidAt =
  ISODate("2026-11-10T03:02:00Z");

const lastId = "ORD-102";

db.orders.find({
  tenantId: "tenant-a",
  status: "PAID",
  $or: [
    {
      paidAt: { $lt: lastPaidAt }
    },
    {
      paidAt: lastPaidAt,
      _id: { $lt: lastId }
    }
  ]
}).sort({
  paidAt: -1,
  _id: -1
}).limit(20);
~~~

This assumes consistent `_id` ordering types and identical sort keys across pages. Under live writes, keyset pagination does not guarantee an immutable snapshot unless the application enforces a consistency contract.

### 6.5. Sorting Can Alter Expected Business Semantics

Placing `$sort` before vs. after `$group` means two completely different things: sorting raw input documents vs. sorting aggregated groups. Know whether you are ordering by order time, customer, or total revenue.

---

## 7. `$project` and Document Size Optimization

### 7.1. Return Fewer Fields

An order document may contain hundreds of line items, shipping addresses, and audit trails, yet the dashboard only needs:

~~~javascript
{
  _id: 1,
  tenantId: 1,
  paidAt: 1,
  totalVnd: 1
}
~~~

Projection shrinks payloads sent to clients and across pipeline stages when used appropriately.

### 7.2. An Early `$project` Is Not Always Faster

The MongoDB optimizer tracks required fields automatically via projection optimization. Inserting `$project` right at the start purely for "fewer fields" **does not automatically improve** the plan.

Use early projection when:

- Stripping huge fields prior to processing where the engine does not prune them automatically.
- Preventing sensitive fields from flowing downstream.
- Trimming inflated shapes right after `$lookup` or `$unwind`.
- `explain` or benchmarks prove measurable gains.

### 7.3. Projection Can Affect Index Usage

If an early `$project` renames or transforms a field before `$match`/`$sort`, the planner may lose direct index eligibility on the source field. Check stage dependencies before reordering stages.

### 7.4. Do Not Return Large Embedded Arrays or Blobs Unnecessarily

When an aggregation only needs counts or sums, never carry huge arrays or GridFS metadata forward. Large payloads bottleneck network transfer even if the DB scan is fast.

---

## 8. `$group`: Reducing Datasets at a Memory Cost

### 8.1. Daily Revenue Calculation

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-a",
      status: "PAID",
      paidAt: {
        $gte: ISODate("2026-11-01T00:00:00Z"),
        $lt: ISODate("2026-12-01T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$paidAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      orders: { $sum: 1 },
      grossVnd: { $sum: "$totalVnd" }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

`$dateTrunc` (MongoDB 5.0+) buckets dates by timezone. Stored `Date` values remain UTC instants; "00:00 local time" does not equal `00:00Z`.

### 8.2. Group Cardinality

With 1 million orders grouped into 30 days, `$group` tracks state for only ~30 groups.

Grouping by `customerId` across 900,000 distinct customers forces the engine to maintain massive in-memory hash tables.

### 8.3. Accumulators

| Accumulator | Use Case | Watch Out For |
|---|---|---|
| `$sum` | Totals / counts | Numeric types, overflow |
| `$avg` | Averages | Output type and precision |
| `$min` / `$max` | Lowest / highest value | Hard to maintain incrementally on deletes/updates |
| `$first` / `$last` | First / last by input order | Requires explicit prior `$sort` semantics |
| `$push` | Collect values into array | Can breach 16 MiB document limit |
| `$addToSet` | Distinct values set | Memory grows with distinct count |
| `$topN` / `$bottomN` | Top-N per group | Version support and memory |
| `$count` accumulator | Group count | Use appropriate stage/version |

### 8.4. Risk of `$push`ing Every Element

~~~javascript
{
  $group: {
    _id: "$tenantId",
    allOrders: { $push: "$$ROOT" }
  }
}
~~~

If a tenant has millions of orders, `allOrders` blows past memory and the 16 MiB BSON document limit. Never use `$group` to stuff all raw records into one giant document.

### 8.5. When Only a Count Is Needed

Use `countDocuments()` or `$match + $count`. Never do `$group + $push + $size`, which materializes giant intermediate arrays pointlessly.

### 8.6. `$first` / `$last` Need Deterministic Ordering

Finding each customer's newest order:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-a"
    }
  },
  {
    $sort: {
      customerId: 1,
      createdAt: -1,
      _id: -1
    }
  },
  {
    $group: {
      _id: "$customerId",
      newestOrder: { $first: "$$ROOT" }
    }
  }
]);
~~~

This can leverage an index on `(tenantId, customerId, createdAt, _id)` when query shapes align. Never rely on `$first` without defining a deterministic sort order.

---

## 9. Memory Limits, Disk Spills, and `allowDiskUse`

Blocking stages such as `$sort` and `$group` retain state in memory. MongoDB enforces stage memory limits; exceeding them either spills to disk if permitted or fails with an error.

### 9.1. MongoDB 6.0 and Default Parameters

Starting in MongoDB 6.0, the server parameter `allowDiskUseByDefault` controls automatic disk spilling for stages exceeding memory thresholds. Depending on version and configuration, queries can override via `allowDiskUse`.

Example:

~~~javascript
db.orders.aggregate(
  [
    { $match: { tenantId: "tenant-a" } },
    {
      $group: {
        _id: "$customerId",
        totalVnd: { $sum: "$totalVnd" }
      }
    },
    { $sort: { totalVnd: -1 } }
  ],
  {
    allowDiskUse: true
  }
);
~~~

### 9.2. Spilling Is Not a Victory

Spilling lets a query finish instead of throwing a memory error, yet it can:

- Spike disk I/O.
- Degrade p95/p99 latency.
- Contend for I/O with concurrent database workloads.
- Mask high-cardinality groups or missing sort indexes.

Inspect `executionStats`/profiler and fix the query shape or schema if spills happen routinely.

### 9.3. Not Every Stage Spills

For instance, `$facet` enforces its own output and memory limits; `allowDiskUse` does not give `$facet` infinite memory, and `$facet` does not spill the same way individual `$sort`/`$group` stages do.

### 9.4. Do Not Raise Memory Limits Arbitrarily

Concurrent queries share host RAM. Increasing a per-query memory limit 10× does not give the cluster 10× more RAM when 100 queries execute at once.

---

## 10. `$lookup`: Efficient Equality Joins

### 10.1. Joining Orders to Customers

Orders store `customerId`, matching `_id` in `customers`:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-a",
      status: "PAID"
    }
  },
  {
    $sort: {
      paidAt: -1,
      _id: -1
    }
  },
  { $limit: 20 },
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  },
  {
    $unwind: {
      path: "$customer",
      preserveNullAndEmptyArrays: true
    }
  },
  {
    $project: {
      _id: 1,
      paidAt: 1,
      totalVnd: 1,
      "customer.displayName": 1
    }
  }
]);
~~~

Putting `$limit` before the join **is valid here** because the requirement is "20 newest orders, enriched with customer name"—not filtering or sorting by joined customer attributes.

### 10.2. Why Do Foreign Indexes Matter?

`customers._id` is indexed by default, letting equality `$lookup` fetch matching documents directly instead of scanning the entire `customers` collection for every batch.

Without an index on `foreignField`, foreign `docsExamined` skyrockets. The MongoDB Manual recommends indexing `foreignField` for frequent equality `$lookup`s.

### 10.3. `$lookup` Always Returns an Array

Even when one order maps to one customer, `customer` from `$lookup` is an array. `$unwind` flattens it, and `preserveNullAndEmptyArrays: true` keeps orders whose customer document is missing.

### 10.4. Null/Missing Values and Join Semantics

If `localField` or `foreignField` is `null` or missing, equality `$lookup` follows specific null-matching semantics. Never assume every document always yields exactly one match; validate schemas and enforce unique business keys.

### 10.5. Tenant Isolation

If `customerId` is only unique per tenant, or when joining on business keys like email, include `tenantId` on the foreign match so cross-tenant data can never leak. Globally unique `_id`s help identity safety, yet the application must still enforce authorization and visibility.

---

## 11. Correlated `$lookup` with `pipeline` and `let`

When joining on multiple conditions, use `let` and `$expr`:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-a",
      status: "PAID"
    }
  },
  {
    $lookup: {
      from: "customers",
      let: {
        orderCustomerId: "$customerId",
        orderTenantId: "$tenantId"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$_id", "$$orderCustomerId"] },
                { $eq: ["$tenantId", "$$orderTenantId"] }
              ]
            }
          }
        },
        {
          $project: {
            _id: 1,
            displayName: 1,
            segment: 1
          }
        }
      ],
      as: "customer"
    }
  }
]);
~~~

### 11.1. What to Push Down into the Foreign Pipeline

- Equality and range predicates on foreign fields when semantics allow.
- `$project` to return only needed fields.
- `$limit` when business logic needs at most one or N matches.
- Matching `$sort` when selecting top-N related records per parent.

### 11.2. `$expr` and Indexes

Inside a `$lookup` pipeline, MongoDB can use indexes for `$expr` comparisons (`$eq`, `$lt`, `$lte`, `$gt`, `$gte`) when `let` variables resolve cleanly and index eligibility rules hold.

However, not every expression uses indexes; restrictions apply for multikey, partial/sparse indexes, and missing/null variables. Never claim "having an index makes every correlated lookup fast."

### 11.3. Equality Syntax Is Often Simpler

When joining on a single field pair, `localField`/`foreignField` is cleaner and often easier for the engine to optimize than a complex correlated subpipeline. Use `pipeline` when extra predicates, sorts, limits, or projections are needed.

### 11.4. Joining on Tenant + Business Key

If customers are identified by `externalCustomerCode` per tenant, consider a unique compound index:

~~~javascript
db.customers.createIndex(
  {
    tenantId: 1,
    externalCustomerCode: 1
  },
  {
    unique: true,
    name: "uk_customer_tenant_external_code"
  }
);
~~~

This enforces per-tenant identity; align lookup predicates with this index.

---

## 12. Fan-Out: Why `$lookup` Becomes Expensive

### 12.1. Join Cardinality

Suppose:

- 1,000 customers.
- Each customer averages 500 orders.
- Joining from `customers` to `orders`.

The `$lookup` result arrays hold 500,000 orders total. Following with `$unwind` inflates the pipeline from 1,000 rows to 500,000 rows.

### 12.2. Never Load All Related Records into One Document

Dangerous example:

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      localField: "_id",
      foreignField: "customerId",
      as: "allOrders"
    }
  }
]);
~~~

A single customer with hundreds of thousands of orders inflates `allOrders`, spiking memory and breaching the 16 MiB BSON limit.

### 12.3. Fetch Only a Summary or Top-N When Sufficient

Example fetching at most the 3 newest orders per customer:

~~~javascript
db.customers.aggregate([
  {
    $match: {
      tenantId: "tenant-a"
    }
  },
  {
    $lookup: {
      from: "orders",
      let: {
        cid: "$_id",
        tid: "$tenantId"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$customerId", "$$cid"] },
                { $eq: ["$tenantId", "$$tid"] }
              ]
            }
          }
        },
        {
          $sort: {
            createdAt: -1,
            _id: -1
          }
        },
        { $limit: 3 },
        {
          $project: {
            _id: 1,
            createdAt: 1,
            totalVnd: 1
          }
        }
      ],
      as: "recentOrders"
    }
  }
]);
~~~

Candidate index:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  customerId: 1,
  createdAt: -1,
  _id: -1
});
~~~

Important note: `$limit: 3` inside the foreign pipeline is valid because the goal is **top 3 orders per customer**; never apply it when counting or summing all orders.

### 12.4. When to Switch to Pre-Aggregated Summaries?

If the dashboard only displays `orderCount` and `totalSpent` per customer, there is no reason to return raw order arrays. Group orders into compact summary rows before joining, or materialize a persistent summary collection.

---

## 13. Counting/Summing Related Documents Instead of Returning Huge Join Arrays

### 13.1. Correlated Aggregate Summary

~~~javascript
db.customers.aggregate([
  {
    $match: {
      tenantId: "tenant-a"
    }
  },
  {
    $lookup: {
      from: "orders",
      let: {
        cid: "$_id",
        tid: "$tenantId"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$customerId", "$$cid"] },
                { $eq: ["$tenantId", "$$tid"] }
              ]
            },
            status: "PAID"
          }
        },
        {
          $group: {
            _id: null,
            orderCount: { $sum: 1 },
            totalSpentVnd: { $sum: "$totalVnd" }
          }
        }
      ],
      as: "purchaseSummary"
    }
  },
  {
    $project: {
      displayName: 1,
      purchaseSummary: 1
    }
  }
]);
~~~

### 13.2. Trade-Off

Each customer triggers a logical correlated subpipeline; even with indexes, grouping orders across hundreds of thousands of customers on every request generates heavy I/O.

If an endpoint repeatedly reads those summaries, consider maintaining a `customerPurchaseStats` collection.

### 13.3. Group First, Then Join

An alternative:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-a",
      status: "PAID"
    }
  },
  {
    $group: {
      _id: "$customerId",
      orderCount: { $sum: 1 },
      totalSpentVnd: { $sum: "$totalVnd" }
    }
  },
  {
    $lookup: {
      from: "customers",
      localField: "_id",
      foreignField: "_id",
      as: "customer"
    }
  }
]);
~~~

This reduces orders down to one summary row per customer before joining, avoiding raw-order fan-out; however, it still scans and groups all matching orders on every run. Benchmark both options.

---

## 14. `$unwind`: The Stage That Multiplies Rows

### 14.1. Order Items Example

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-a",
      status: "PAID"
    }
  },
  {
    $unwind: "$items"
  },
  {
    $group: {
      _id: "$items.sku",
      unitsSold: { $sum: "$items.qty" }
    }
  },
  {
    $sort: {
      unitsSold: -1
    }
  },
  { $limit: 10 }
]);
~~~

An order with 20 items emits 20 rows after `$unwind`. One million orders averaging 10 items expand into 10 million rows.

### 14.2. When Is `$unwind` Unnecessary?

If you only need order `totalVnd`, never unwind `items`. Unwinding and re-grouping by order wastes work and risks double-counting order totals.

### 14.3. `preserveNullAndEmptyArrays`

By default, `$unwind` drops documents where the array is missing or empty. To retain parent documents, use:

~~~javascript
{
  $unwind: {
    path: "$items",
    preserveNullAndEmptyArrays: true
  }
}
~~~

This changes counts and group outputs; decide based on business semantics, not performance alone.

### 14.4. `$filter` and `$map` as Alternatives in Some Cases

If you only need to transform array elements while keeping one parent document, `$filter`/`$map` can beat `$unwind` → `$group`, though they still cost CPU/memory and remain bounded by the 16 MiB BSON limit.

---

## 15. `$facet`: Multiple Outputs from One Input Stream

Suppose a search response needs:

- 20 newest orders.
- Order counts by status.
- Order value totals.

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-a"
    }
  },
  {
    $facet: {
      page: [
        {
          $sort: {
            createdAt: -1,
            _id: -1
          }
        },
        { $limit: 20 },
        {
          $project: {
            _id: 1,
            status: 1,
            totalVnd: 1
          }
        }
      ],
      byStatus: [
        {
          $group: {
            _id: "$status",
            count: { $sum: 1 }
          }
        }
      ],
      totals: [
        {
          $group: {
            _id: null,
            count: { $sum: 1 },
            totalVnd: { $sum: "$totalVnd" }
          }
        }
      ]
    }
  }
]);
~~~

### 15.1. Benefits

One input stream feeds multiple independent sub-pipelines—handy for APIs returning paginated rows and facet counts together.

### 15.2. Limitations

`$facet` has strict memory and output size limits, and `allowDiskUse` does not make it unlimited. Placing `$facet` as the first stage also prevents sub-pipelines from leveraging source collection indexes the way a leading `$match`/`$sort` can.

### 15.3. Do Not Assume One `$facet` Pipeline Is Always Cheaper Than Separate Queries

If `page` only needs 20 documents while `totals` scans millions, `$facet` ties page latency to the slowest branch. When stats tolerate slight lag, separate queries or materialized summaries can be much faster.

---

## 16. Window Functions and Optimization Limits

`$setWindowFields` computes rankings, running sums, and moving averages over partitioned, sorted windows.

Example running revenue per tenant:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      status: "PAID"
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$tenantId",
      sortBy: {
        paidAt: 1
      },
      output: {
        runningVnd: {
          $sum: "$totalVnd",
          window: {
            documents: ["unbounded", "current"]
          }
        }
      }
    }
  },
  {
    $project: {
      tenantId: 1,
      paidAt: 1,
      totalVnd: 1,
      runningVnd: 1
    }
  }
]);
~~~

### 16.1. Optimizing Windows

- Filter early before the window stage.
- Pick sensible partition keys.
- Index partition + sort keys when query shapes benefit.
- Avoid creating millions of partitions without measuring memory.
- Bound time ranges when business requirements permit.

### 16.2. Moving Windows and Late-Arriving Data

For a 7-day moving average, a late transaction for an older date alters **multiple subsequent days**, not just that single day's bucket. Materialized views must recompute all affected windows, not just one row.

---

## 17. `explain()`: Observe Instead of Guessing

### 17.1. Aggregation Explain

~~~javascript
db.orders.explain("executionStats").aggregate([
  {
    $match: {
      tenantId: "tenant-a",
      status: "PAID"
    }
  },
  {
    $sort: {
      paidAt: -1,
      _id: -1
    }
  },
  { $limit: 20 }
]);
~~~

### 17.2. Metrics to Inspect

| Metric | Meaning |
|---|---|
| `winningPlan` | Access path chosen by the planner |
| `IXSCAN` / `COLLSCAN` | Index scan vs. collection scan when shown |
| `totalKeysExamined` | Number of index entries scanned |
| `totalDocsExamined` | Number of documents inspected |
| `nReturned` | Number of documents returned |
| `executionTimeMillis` | Execution time in the test environment |
| Sort stage / spill | Whether a blocking sort or disk spill occurred |
| Join stages / index use | Whether the foreign collection used an index |
| `usedDisk` / spills | Indication of disk spilling when reported |

Stage names and output shapes in `explain` change across MongoDB versions and query engines. Never write rigid assertions tied to one stage name across versions.

### 17.3. Checking `$lookup`

Verify:

- How many input documents enter the join?
- Does the foreign field have a matching index?
- Number of foreign `docsExamined`.
- Any repeated foreign collection scans?
- Fan-out from parent to child records.
- Were sort and limit pushed down into the foreign subpipeline?

Specific `$lookup` stats depend on server version and explain representation.

### 17.4. Query Engine and `EQ_LOOKUP`

Certain MongoDB versions and query shapes use the slot-based execution engine for equality `$lookup`, appearing as `EQ_LOOKUP` in `explain`. Do not treat presence or absence of `EQ_LOOKUP` as the sole pass/fail criterion, as correlated pipelines, sharding, index types, and stage placement affect eligibility.

### 17.5. `explain` Does Not Replace Production Latency Metrics

`executionTimeMillis` reflects a single run affected by cache/warm-up state. Always inspect profiler data, slow-query logs, app traces, p50/p95/p99, and throughput under real concurrency.

---

## 18. Schema Modeling: Embed, Reference, or Precompute?

### 18.1. Embedding

Example order storing product name/price snapshots at purchase time:

~~~javascript
{
  _id: "ORD-101",
  tenantId: "tenant-a",
  items: [
    {
      sku: "SKU-1",
      titleAtPurchase: "Jacket",
      qty: 2,
      unitPriceVnd: NumberLong("150000")
    }
  ]
}
~~~

Benefit: reading an order requires no join to live `products` to reconstruct purchase history. This is also **business-correct**, since live product names and prices change over time.

Trade-off: data duplication and clearly separating purchase-time snapshots from canonical catalog records.

### 18.2. References + `$lookup`

Fits when data is large, changes frequently, forms unbounded one-to-many relationships, or requires independent entity lifecycles.

### 18.3. Precomputed Summaries

Fits when many requests repeatedly ask for grouped counts, sums, or rankings across large datasets.

### 18.4. Decision Matrix

| Question | Embed | `$lookup` | Materialized View |
|---|---|---|---|
| Stable one-to-few | Great | Possible | Usually unnecessary |
| Very large one-to-many | Risk of bloated documents | With index and `$limit` | Great if only summary is needed |
| Continuously changing data | Needs sync | Reads latest source | Needs refresh |
| Price snapshot at purchase | Ideal | Joining live price is wrong | Can aggregate snapshots |
| Daily revenue reports | Does not replace grouping | Unneeded if orders suffice | Ideal |
| Exact real-time transactional state | Source document | Can join source | Staleness risk |

### 18.5. Do Not Force SQL Thinking onto Every MongoDB Workload

Denormalizing select fields cuts joins, yet never stuff unbounded arrays into one document or scatter brittle copies everywhere. Tuning balances **read latency, write amplification, consistency, and storage**.

---

## 19. When Should You Maintain a Precomputed Summary Collection?

A frequently queried report:

~~~text
Dashboard every 10 seconds
  -> Count 10 million orders by tenant/day
  -> Return 30 rows
~~~

If every request runs the exact same `$group`, massive compute is wasted regenerating nearly identical outputs.

Instead, maintain:

~~~javascript
{
  tenantId: "tenant-a",
  day: ISODate("2026-11-09T17:00:00Z"),
  currency: "VND",
  paidOrders: 1250,
  grossVnd: NumberLong("750000000"),
  computedAt: ISODate("2026-11-14T05:00:00Z"),
  version: 1
}
~~~

`day` marks the start of the day **in the local business timezone**, stored as a UTC `Date` (here 00:00 on Nov 10 in `Asia/Ho_Chi_Minh` equals `17:00Z` on Nov 9).

### 19.1. When Materialization Makes Sense

- Summary reads outnumber source changes.
- Raw scans/groups are expensive.
- Freshness bounds are acceptable.
- A clean recompute/reconciliation path from source exists.
- Summary output is orders of magnitude smaller than source data.
- Business rules and metric definitions are stable enough to version.

### 19.2. When It Does Not

- Dataset is small and indexed queries already meet SLOs.
- Users slice arbitrarily across thousands of filter combinations.
- Correctness demands instantaneous transactional snapshots while refresh is eventual.
- Definitions change constantly, making backfills prohibitive.
- No operational process exists to repair staleness or drift.

### 19.3. Materialized Views Differ from Standard MongoDB Views

A standard MongoDB **view** is logical and executes its aggregation at read time. A **materialized view** persists computed documents in a collection refreshed on a schedule or via CDC. Their read costs and freshness differ completely.

---

## 20. Building Summary Collections with `$group` and `$merge`

### 20.1. Designing a Unique Key

One row per tenant, day, and currency:

~~~javascript
db.dailyOrderSales.createIndex(
  {
    tenantId: 1,
    day: 1,
    currency: 1
  },
  {
    unique: true,
    name: "uk_sales_tenant_day_currency"
  }
);
~~~

Including `currency` prevents adding VND and USD together. If orders are converted to a single canonical currency using historical FX rates, explicitly record the metric, FX rate, and version rather than silently summing mixed currencies.

### 20.2. Full Aggregation from Source

~~~javascript
db.orders.aggregate([
  {
    $match: {
      status: "PAID",
      paidAt: { $type: "date" }
    }
  },
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        day: {
          $dateTrunc: {
            date: "$paidAt",
            unit: "day",
            timezone: "Asia/Ho_Chi_Minh"
          }
        },
        currency: "$currency"
      },
      paidOrders: { $sum: 1 },
      grossVnd: { $sum: "$totalVnd" }
    }
  },
  {
    $project: {
      _id: 0,
      tenantId: "$_id.tenantId",
      day: "$_id.day",
      currency: "$_id.currency",
      paidOrders: 1,
      grossVnd: 1,
      computedAt: "$$NOW"
    }
  },
  {
    $merge: {
      into: "dailyOrderSales",
      on: ["tenantId", "day", "currency"],
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
]);
~~~

**Requirements:** The index on `on` fields must satisfy `$merge` unique-index requirements, matching collations/field rules, and every output row must contain all key fields. Additional constraints apply for sharded targets and across MongoDB versions.

### 20.3. Why Use `$merge`?

`$merge` writes pipeline results into a target collection. With `on` and `whenMatched: "replace"`, existing groups are updated with fresh totals and new groups are inserted.

A replace-based pipeline is **idempotent for groups computed from the same source snapshot**, making bucket reruns convenient. Still, concurrent runs or shifting source reads can race—coordinate refresh execution order.

### 20.4. Where `$merge` Does Not Solve Consistency Automatically

- If a day loses all `PAID` orders due to deletes or rollbacks, the pipeline emits no row for that day, so `$merge` **does not delete the stale row**.
- Two concurrent refresh workers writing the same bucket can let the slower stale run overwrite the newer one.
- Source mutations mid-aggregation can make a full scan reflect an inconsistent cut unless snapshot isolation is configured.
- Multi-group outputs do not commit atomically as a single cross-collection transaction.
- If `$merge` fails halfway through, partial rows remain persisted.

Thus `$merge` is a materialization writer, not a complete "exactly-once materialized view engine."

### 20.5. `$out` vs. `$merge`

- `$merge` matches by keys and updates/inserts into an existing collection.
- `$out` creates or atomically swaps an output collection per its semantics, fitting certain full-refresh batch jobs.
- Both carry restrictions around transactions, sharding, read/write stages, and permissions—never invoke them accidentally from read-only API requests.
- For atomic cutovers of massive snapshots in production, you can build a **new versioned collection**, validate it, and flip an application read pointer/namespace rather than mutating rows piecewise.

---

## 21. Querying the Dashboard from the Summary Collection

After materialization:

~~~javascript
db.dailyOrderSales.find(
  {
    tenantId: "tenant-a",
    currency: "VND",
    day: {
      $gte: ISODate("2026-10-31T17:00:00Z"),
      $lt: ISODate("2026-11-30T17:00:00Z")
    }
  },
  {
    _id: 0,
    day: 1,
    paidOrders: 1,
    grossVnd: 1,
    computedAt: 1
  }
).sort({
  day: 1
});
~~~

### 21.1. Index for Dashboard Reads

The unique index `{tenantId: 1, day: 1, currency: 1}` satisfies `$merge` key matching, yet if reads always filter equality on `tenantId` and `currency` plus range/sort on `day`, consider adding a read-optimized index:

~~~javascript
db.dailyOrderSales.createIndex(
  {
    tenantId: 1,
    currency: 1,
    day: 1
  },
  {
    name: "idx_daily_sales_tenant_currency_day"
  }
);
~~~

Two indexes add write amplification; measure whether both are warranted or if a unified key order `{tenantId: 1, currency: 1, day: 1}` works for both `$merge` and reads.

### 21.2. Dramatically Fewer Rows

Even with 10 million orders, 100 tenants × 365 days × 2 currencies yields at most ~73,000 summary rows—far cheaper than repeatedly grouping raw orders.

### 21.3. Attach Freshness Metadata

An API should expose:

~~~json
{
  "tenantId": "tenant-a",
  "currency": "VND",
  "rows": [
    {
      "day": "2026-11-10",
      "paidOrders": 1250,
      "grossVnd": 750000000
    }
  ],
  "computedAt": "2026-11-14T05:00:00Z",
  "freshness": "AS_OF_COMPUTED_AT"
}
~~~

Illustrative payload. `computedAt` records when the job ran, not whether every upstream event was ingested. For streaming pipelines, track a **source event watermark** or resume checkpoint to report freshness reliably.

---

## 22. Full Refresh, Scheduled Refresh, and Incremental Refresh

| Update Strategy | Best Fit | Benefits | Risks |
|---|---|---|---|
| On-demand aggregation | Low traffic / small datasets | Live source reads | Heavy queries as data scales |
| Scheduled full refresh | Infrequently changing reports, medium data | Simple logic | Rescans full source repeatedly |
| Scheduled partial refresh | Recent daily buckets | Fewer scans | Misses older historical corrections |
| Event-driven incremental | High churn, low freshness lag | Minimal recomputation when correct | Complex CDC, idempotency, concurrency |
| Hybrid CDC + reconciliation | Production-critical summaries | Freshness + self-healing | Higher operational complexity |
| Append-only rollup | Immutable events | Easy incremental updates | Breaks on updates, deletes, or backdated edits |

### 22.1. Scheduled Full Refresh

An hourly job groups all orders. Simple, yet high repeated read cost: if `tenant-a` has 10 million orders, every hour scans all 10 million. Budget the load carefully.

### 22.2. Scheduled Partial Refresh

If most writes hit the last 7 days, the job recomputes the last 7 daily buckets. However, a late refund on a 3-month-old order still needs to update the older month.

### 22.3. Event-Driven Incremental

Change Streams or outbox events notify workers of mutations so only affected groups update. Much fresher, yet requires handling retries, duplicates, ordering, and event history retention.

### 22.4. Hybrid

A common production architecture:

~~~text
Change Streams -> near real-time updates
             |
             v
dailyOrderSales

Nightly reconciliation:
  group authoritative orders
  -> compare/repair dailyOrderSales
~~~

For critical financial/business reporting, hybrid protects against drift from missed events or crashes.

---

## 23. Incremental Aggregation: Do Not Blindly `$inc`

Suppose an order transitions from `PENDING` to `PAID`:

~~~javascript
{
  status: "PAID",
  totalVnd: NumberLong("500000")
}
~~~

You might be tempted to write:

~~~javascript
db.dailyOrderSales.updateOne(
  {
    tenantId: "tenant-a",
    day: saleDay,
    currency: "VND"
  },
  {
    $inc: {
      paidOrders: 1,
      grossVnd: NumberLong("500000")
    }
  },
  { upsert: true }
);
~~~

If the exact same event is processed **twice** after a retry, revenue doubles.

### 23.1. State Transitions to Handle

| Order Change | Aggregate Impact |
|---|---|
| New `PENDING` | Does not increase `PAID` revenue |
| `PENDING` → `PAID` | Increment count and amount |
| `PAID` → `REFUNDED` | Subtract or reclassify per accounting policy |
| `PAID` amount edited | Apply exact delta |
| `paidAt` moved to another day | Decrement old bucket, increment new bucket |
| `currency` changed | Move metric to the new currency bucket |
| Order deleted | Decrement/recompute if previously counted |
| Duplicate CDC event | Must not double-count |
| Late-arriving event | Update historical bucket accurately |
| Business rule change | Requires backfill/recomputation |

### 23.2. Safer Pattern: Recompute the Affected Bucket

When receiving an event for an order on day D:

1. Identify both old and new `(tenant, currency, day)` buckets if changed.
2. Query the source of truth `orders` for each affected bucket.
3. Re-group that bucket.
4. Replace the summary row—or delete/zero it if zero orders remain.
5. Persist the checkpoint only after storing the result.

This is **idempotent against current source truth** provided concurrent stale writes are prevented. It eliminates double-counting retries at the cost of scanning that single bucket.

### 23.3. When a Single Bucket Is Also Huge

You can maintain a per-`orderId` contribution ledger and apply deltas via transactions/idempotency. Still, complexity rises significantly:

- Store the last accounted status, amount, and day.
- Transactionally claim event/contribution versions.
- Subtract old contribution, add new contribution.
- Enforce unique event IDs and ordering.
- Handle out-of-order updates.
- Reconcile periodically against source.

Never claim Change Streams guarantee exactly-once business processing merely because resume tokens exist.

---

## 24. Recomputing a Daily Bucket Properly

Suppose we recompute:

~~~javascript
const tenantId = "tenant-a";
const currency = "VND";
const from = ISODate("2026-11-09T17:00:00Z");
const to = ISODate("2026-11-10T17:00:00Z");

db.orders.aggregate([
  {
    $match: {
      tenantId,
      currency,
      status: "PAID",
      paidAt: {
        $gte: from,
        $lt: to
      }
    }
  },
  {
    $group: {
      _id: null,
      paidOrders: { $sum: 1 },
      grossVnd: { $sum: "$totalVnd" }
    }
  }
]);
~~~

### 24.1. Why Use Half-Open `[from, to)`?

Half-open intervals prevent boundary overlap across consecutive days. `to` is the start of the next local day in the tenant/business timezone—not always `from + 24 hours` in DST-observing zones.

### 24.2. What If Zero Orders Remain?

`$group` returns zero documents. The worker must explicitly **delete or zero out** the summary row per policy. A full-pipeline `$merge` will not remove stale zero-order rows automatically.

### 24.3. Concurrency

Worker A reads source at T1, while Worker B reads newer state at T2. If B writes the summary first and A overwrites it later, **stale overwrite** corrupts the summary. Prevent this via:

- Serializing work per bucket key.
- Per-key leases/locks.
- Monotonic generation/watermark CAS checks.
- Or delayed recomputation + periodic reconciliation.

Never assume "`$merge` replace is idempotent" makes concurrent writers race-free.

### 24.4. Snapshot Semantics

An aggregation scanning source data while writes continue sees shifting state depending on read concern and snapshot isolation. For financial reporting, define cutoff and consistency policies explicitly rather than assuming every group reflects one globally consistent instant.

---

## 25. Using Change Streams to Maintain Summaries

### 25.1. General Flow

~~~text
MongoDB orders
   |
   +-- insert/update/replace/delete
   |
   v
Change Stream consumer
   |
   v
Determine affected bucket(s)
   |
   v
Recompute or apply idempotent contribution
   |
   v
dailyOrderSales
   |
   v
Checkpoint resume token
~~~

### 25.2. Why Are Resume Tokens Needed?

After a worker crash, the resume token lets the consumer resume from the last processed event per Change Streams semantics, provided the oplog still retains that history.

### 25.3. Never Checkpoint Before Updating the Summary

Wrong:

~~~text
Read event
  -> persist resume token
  -> crash
  -> summary never updated
~~~

Upon restart, the worker skips that event permanently.

Persist the checkpoint only after the summary update succeeds. Because crashing **after updating the summary and before checkpointing** replays the event, updates must be idempotent or deduplicated transactionally.

### 25.4. Deletes and Pre-Images

A delete event includes the document key but not the full pre-deletion document by default. To learn the old day/tenant/currency bucket, you need one of:

- Change Stream pre-images enabled with adequate retention.
- A contribution ledger keyed by `orderId`.
- Audit/outbox events capturing before/after state.
- Reconciliation/backfill when prior state is unavailable.

Never assume delete events always include old `paidAt` and `currency`.

### 25.5. Oplog History Loss

If a consumer stays down too long, its resume token can fall off the oplog. You must bootstrap/recompute from source and establish a fresh checkpoint without leaving a blind gap—never just restart watching "from now" and silently drop missed mutations.

---

## 26. Protecting Summaries from Double-Counting and Drift

### 26.1. Design for At-Least-Once Delivery by Default

Events can be redelivered after crashes or retries. Any `$inc`-based logic must deduplicate before applying; otherwise counts and sums drift.

### 26.2. Contribution Ledger

Store per-order contribution documents:

~~~javascript
{
  _id: "ORD-101",
  tenantId: "tenant-a",
  sourceVersion: 12,
  day: ISODate("2026-11-09T17:00:00Z"),
  currency: "VND",
  paidContributionVnd: NumberLong("500000"),
  paidContributionCount: 1,
  updatedAt: ISODate("2026-11-14T04:00:00Z")
}
~~~

On updates, look up the prior contribution and apply only the delta. Updating ledger + summary requires coordinated atomicity/idempotency; if using multi-document transactions, handle write concern, retries, and unknown commit outcomes properly.

### 26.3. Never Assume Global Event Ordering Across Services

Change Streams preserve ordering per defined semantics, yet downstream partitions, multiple workers, external brokers, and retries can reorder events arriving at your handler.

Use a monotonic source version or sequence number so stale events never overwrite newer state. Do not trust client-supplied `updatedAt` timestamps as strict versions when clock skew exists.

### 26.4. Reconciliation Jobs

Periodically recompute selected buckets from the authoritative source and compare:

~~~text
expected grossVnd from orders
vs
observed grossVnd in dailyOrderSales
~~~

Alert on discrepancies and repair with an audit trail. A blazingly fast summary that is off by 0.5% fails financial reporting requirements.

---

## 27. Late-Arriving Data and Backfills

### 27.1. Event Time vs. Processing Time

A payment settles at 23:59 on Monday, yet the consumer processes the event at 00:05 on Tuesday. Bucketing by processing time misattributes Monday's revenue to Tuesday.

The right rule is usually bucketing by **business event time** (e.g., `paidAt`) in the configured business timezone.

### 27.2. Late Corrections

An order from last month receives a refund today. Business rules may specify:

- Reducing revenue on **the original sale day**.
- Recording negative net revenue on **the refund day**.
- Tracking gross sales and refunds as **two separate metrics**.

There is no single universal accounting rule; lock down the metric contract before writing pipelines.

### 27.3. Historical Backfills

When changing the definition of a "paid order" or adding currencies:

1. Increment `metricSchemaVersion`.
2. Backfill into a new collection or schema version.
3. Verify completeness and checksums.
4. Canary compare against legacy reports.
5. Flip dashboard read pointers or feature flags.
6. Retain a rollback path.
7. Clean up legacy aggregates once approved.

### 27.4. TTL Does Not Replace Business Retention

If TTL deletes raw orders before backfills or repairs run, summaries lose their source of truth. Raw data and event log retention must cover correction windows, audits, and restores.

---

## 28. Aggregates That Are Hard to Update Incrementally

### 28.1. `$sum` and `$count`

Straightforward to maintain via deltas given before/after state and deduplication.

### 28.2. `$avg`

Never store only the average; store `sum` and `count` and derive the average from them. On deletes or edits, adjust both `sum` and `count`.

### 28.3. `$min` and `$max`

Suppose `min price = 100`, and the document holding `100` is deleted. You cannot determine the new minimum from `100` alone; you need member records or bucket recomputation.

### 28.4. Distinct Counts

Counting unique customers requires large sets, reference counts, or approximate sketches (if business tolerances allow). You cannot simply increment a counter on every "customerSeen" event when one customer places many orders.

### 28.5. Percentiles

Percentiles cannot be subtracted when a record is deleted. Use batch recomputation, mergeable histograms, or well-specified approximate sketches.

### 28.6. Window Aggregates

Moving averages and running totals span multiple buckets; mutating one historical day invalidates downstream window buckets.

---

## 29. Multi-Tenancy and Sharded Clusters

### 29.1. Tenant-Aware Filtering

Include `tenantId` in both source `$match` stages and materialized keys. Never precompute cross-tenant totals and let tenants filter unrestricted rows if isolation rules prohibit mixing.

### 29.2. Shard Keys

On sharded `orders`, queries filtering by `tenantId` target fewer shards when shard keys and query shapes align. Yet shard keys must balance writes, tenant skew, and hotspots—not just dashboards.

### 29.3. `$lookup` on Sharded Collections

MongoDB supports `$lookup` against sharded foreign collections in supported versions (e.g., MongoDB 5.1+), yet performance depends heavily on routing, indexes, and cross-shard network traffic. Never assume cross-shard joins match local `_id` lookup latency.

### 29.4. `$group` on Sharded Clusters

Aggregations can run partial grouping on each shard before merging, yet check stage placement, merge node location, and network fan-in. Cluster-wide grouping can stress coordinator memory and I/O.

### 29.5. `$merge` into Sharded Targets

Strict rules govern `on` fields relative to the target's shard key and unique indexes. Never write a `$merge` matching only `(tenantId, day)` when the sharded target requires additional shard-key fields without checking version rules.

### 29.6. Hot Buckets

A massive tenant can turn a single "daily aggregate document" into a hot document under per-order `$inc` updates. Options:

- Striped/sharded counters merged on read or rollup.
- Batched updates.
- Interval materialization from logs.
- Per-minute/hour summaries rolled up daily.
- Partitioned worker queues by `(tenant, time)`.

Balance write contention against document/index counts and read complexity.

---

## 30. Java Sync Driver: Optimized Aggregation Pipeline

Backend example querying the 20 newest paid orders enriched with customer display names:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

import java.util.List;

public class OptimizedOrdersExample {

    public static void run(MongoClient client) {
        MongoDatabase db =
            client.getDatabase("aggregation_perf_lab");

        MongoCollection<Document> orders =
            db.getCollection("orders");

        Document match = new Document(
            "$match",
            new Document("tenantId", "tenant-a")
                .append("status", "PAID")
        );

        Document sort = new Document(
            "$sort",
            new Document("paidAt", -1)
                .append("_id", -1)
        );

        Document lookup = new Document(
            "$lookup",
            new Document("from", "customers")
                .append("localField", "customerId")
                .append("foreignField", "_id")
                .append("as", "customer")
        );

        Document unwind = new Document(
            "$unwind",
            new Document("path", "$customer")
                .append(
                    "preserveNullAndEmptyArrays",
                    true
                )
        );

        Document project = new Document(
            "$project",
            new Document("_id", 1)
                .append("paidAt", 1)
                .append("totalVnd", 1)
                .append("customer.displayName", 1)
        );

        orders.aggregate(
            List.of(
                match,
                sort,
                new Document("$limit", 20),
                lookup,
                unwind,
                project
            )
        ).forEach(System.out::println);
    }
}
~~~

### 30.1. Why This Stage Order?

- `$match` filters tenant and status.
- `$sort` + `$limit` selects only the 20 orders to display.
- `$lookup` joins only those 20 orders.
- `$unwind` and `$project` produce a compact response.

**Do not reuse this exact order** if the requirement is "20 newest orders from VIP customers"—then customer segment must be filtered *before* `$limit` or denormalized with proper freshness semantics.

### 30.2. Managing `MongoClient`

In Java backends, `MongoClient` is a long-lived pooled singleton, never instantiated per request. Enforce server-side timeouts and application deadlines so heavy aggregations cannot hang threads indefinitely.

### 30.3. Client Inputs

Tenant IDs and authorization must come from the backend context. Never pass raw client JSON straight into `$match` or `$lookup`, which risks authorization bypass and denial-of-service queries.

---

## 31. Java Sync Driver: Summary Refresh Job

Raw BSON documents can express `$merge` cleanly:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

import java.util.List;

public class DailySalesRefresh {

    public static void execute(MongoClient client) {
        MongoDatabase db =
            client.getDatabase("aggregation_perf_lab");

        MongoCollection<Document> orders =
            db.getCollection("orders");

        Document dateTrunc = new Document(
            "$dateTrunc",
            new Document("date", "$paidAt")
                .append("unit", "day")
                .append(
                    "timezone",
                    "Asia/Ho_Chi_Minh"
                )
        );

        Document match = new Document(
            "$match",
            new Document("status", "PAID")
        );

        Document groupId = new Document(
            "tenantId", "$tenantId"
        )
            .append("currency", "$currency")
            .append("day", dateTrunc);

        Document group = new Document(
            "$group",
            new Document("_id", groupId)
                .append(
                    "paidOrders",
                    new Document("$sum", 1)
                )
                .append(
                    "grossVnd",
                    new Document("$sum", "$totalVnd")
                )
        );

        Document projection = new Document(
            "$project",
            new Document("_id", 0)
                .append("tenantId", "$_id.tenantId")
                .append("currency", "$_id.currency")
                .append("day", "$_id.day")
                .append("paidOrders", 1)
                .append("grossVnd", 1)
        );

        Document merge = new Document(
            "$merge",
            new Document(
                "into",
                "dailyOrderSales"
            )
                .append(
                    "on",
                    List.of(
                        "tenantId", "day", "currency"
                    )
                )
                .append(
                    "whenMatched",
                    "replace"
                )
                .append(
                    "whenNotMatched",
                    "insert"
                )
        );

        // $merge is a write stage and does not return rows
        // like a typical reporting query.
        orders.aggregate(
            List.of(
                match,
                group,
                projection,
                merge
            )
        ).toCollection();
    }
}
~~~

### 31.1. Prerequisites Before Running

- Matching unique index exists on the target collection.
- Server version supports all stages and expressions (`$dateTrunc`, `$merge`).
- Service account has read permission on `orders` and write permission on the summary collection.
- Timezone and monetary rules match business requirements.
- Concurrent refresh jobs cannot race and cause stale overwrites.
- Monitoring alerts on failed or missed refreshes.

### 31.2. Never Trigger from Every HTTP Request

`$merge` mutates data; never let a dashboard view accidentally launch a full refresh. Run refreshes via a scheduled job or dedicated worker with locks, retries, and separate SLOs, while the dashboard reads the summary collection.

---

## 32. Benchmarking: Measure the Real Workload

### 32.1. Tiny Lab Data Is Insufficient

With 4 orders, both `COLLSCAN` and index scans finish instantly. Benchmark on a production-like synthetic dataset:

- 1–100 million orders.
- Skewed tenant sizes.
- Realistic status, date, and `customerId` distributions.
- Varying `items` array lengths.
- Realistic average customers per tenant.
- Realistic update/delete/refund rates.
- Target query concurrency.
- Cold vs. warm cache states.
- Production-like sharding/topology.

### 32.2. Candidate Strategies to Compare

A. Raw aggregation on every dashboard view.

B. Raw aggregation with compound indexes.

C. `$group` before `$lookup`.

D. Correlated `$lookup` with foreign index and `$limit`.

E. Scheduled materialized summary.

F. Incremental summary + nightly reconciliation.

### 32.3. Benchmark Metrics

| Group | Metrics |
|---|---|
| Latency | p50/p95/p99, max duration |
| Throughput | Requests/second |
| Query work | Keys/docs examined |
| Memory | Sort/group memory and disk spills |
| Joins | Foreign scans, returned fan-out |
| I/O | Disk read/write, network transfer |
| Resources | CPU/RAM/Search or `mongod` utilization |
| Write cost | Extra writes, index updates |
| Freshness | Summary lag / watermark |
| Correctness | Discrepancy rate vs. authoritative recompute |
| Operations | Failed refreshes, replay time, backfill duration |

### 32.4. Measure Correctness Alongside Performance

Suppose a summary query drops from 2 seconds to 20 ms while revenue is off by 1% due to duplicate CDC events. That is **not** a successful optimization.

### 32.5. Warm-Up and `explain` Overhead

Repeat benchmarks across diverse query parameters and data slices. `explain("executionStats")` illuminates plans, yet production workloads also include network, serialization, caching, concurrency, and framework overhead.

---

## 33. Common Design Pitfalls

**Pitfall 1 — "Always put `$match` first."** Not always possible; search/geo stages require stage 1, and computed fields impose dependencies.

**Pitfall 2 — "Putting `$project` first in every pipeline optimizes it."** The optimizer already prunes unused fields; measure first.

**Pitfall 3 — "Just index every field."** Indexes add storage and write overhead without guaranteeing optimal plans.

**Pitfall 4 — "An indexed `$sort` makes the whole pipeline free."** Once `$group` or key transformations occur, sorting on aggregated fields can still block.

**Pitfall 5 — "`$limit` before a join never changes results."** Wrong whenever the join filters or ranks by joined fields.

**Pitfall 6 — "`$lookup` always returns a single document."** It returns an array; one-to-many joins can fan out massively.

**Pitfall 7 — "Any index on the foreign collection is enough."** It must match the exact join keys and predicates; verify with `explain`.

**Pitfall 8 — "Correlated `$expr` uses indexes for every expression."** Restrictions exist around field-vs-constant rules, multikeys, and index types.

**Pitfall 9 — "`$unwind` does not multiply rows."** One-to-many arrays can expand datasets tenfold or more.

**Pitfall 10 — "`$group` + `$push: $$ROOT` is a safe way to export data."** Easily blows memory and the 16 MiB BSON limit.

**Pitfall 11 — "`allowDiskUse: true` makes queries faster."** It enables disk spilling to avoid OOM errors, often raising I/O and latency.

**Pitfall 12 — "`$facet` has unlimited memory under `allowDiskUse`."** False.

**Pitfall 13 — "Standard views are materialized views."** MongoDB views compute at read time; materialized collections must be refreshed.

**Pitfall 14 — "`$merge` automatically deletes vanished groups."** False; empty groups produce no pipeline output to trigger deletion.

**Pitfall 15 — "`$merge replace` prevents stale concurrent writer races."** False; a slower stale worker can overwrite a newer run.

**Pitfall 16 — "Change Streams deliver events strictly once."** Never design business logic assuming exactly-once delivery.

**Pitfall 17 — "`$inc` per event is always safe."** Duplicate deliveries double-count totals.

**Pitfall 18 — "Delete events always include the before-image."** Not by default; use pre-images, audits, or contribution ledgers.

**Pitfall 19 — "When an order changes dates, just add to the new bucket."** You must also subtract from or recompute the old bucket.

**Pitfall 20 — "VND and USD can be summed directly."** Never; include currency as a key or enforce documented FX conversion.

**Pitfall 21 — "Current sum and count let you handle deletes for min/max."** False; min/max deletes require member tracking or recomputation.

**Pitfall 22 — "A materialized aggregate is the source of truth."** Keep a clear source of truth; summaries can lag or drift.

**Pitfall 23 — "A fresh `computedAt` proves all events were processed."** False; track checkpoints and watermarks.

**Pitfall 24 — "One index fits all tenants equally."** Tenant skew, sharding, and query mixes change optimal strategies.

**Pitfall 25 — "Fast on 1,000 docs means production-ready."** Validate scale, concurrency, and correctness.

---

## 34. Checklist for Optimizing Aggregations, Joins, and Summaries

### 34.1. Aggregation

- [ ] Exact business and metric definitions documented.
- [ ] `$match` uses tenant, status, and time ranges and is placed cleanly.
- [ ] `$sort` backed by indexes where possible.
- [ ] `$limit` placement preserves valid business results.
- [ ] Avoided deep `$skip` where keyset pagination works.
- [ ] Projections trim unnecessary fields.
- [ ] `$group` avoids excessive cardinality or oversized arrays.
- [ ] Memory usage and disk spills monitored.
- [ ] `explain` verified on realistic data scale.
- [ ] UTC vs. local business timezones handled accurately.

### 34.2. Joins

- [ ] Foreign join keys are properly indexed.
- [ ] Join fan-out estimated and bounded.
- [ ] Tenant and authorization predicates enforced on both sides.
- [ ] Avoided looking up millions of child docs just to count them.
- [ ] Used correlated pipelines when multi-predicate filtering/trimming is needed.
- [ ] Missing/empty array semantics handled in `$unwind`.
- [ ] Placed sort/limit before joins only when semantics permit.
- [ ] Eliminated N+1 query loops in application code.
- [ ] Evaluated denormalizing immutable snapshot fields where appropriate.

### 34.3. Materialized Summaries

- [ ] Authoritative source of truth clearly defined.
- [ ] Metric definitions, currency, and timezone locked down.
- [ ] Unique summary key and index match `$merge` requirements.
- [ ] Refresh status, `computedAt`, and source watermark tracked.
- [ ] Inserts, updates, deletes, and late events handled.
- [ ] Deduplication, idempotency, and event ordering enforced.
- [ ] Concurrent workers prevented from stale overwrites.
- [ ] Groups dropping to zero / vanishing handled explicitly.
- [ ] Scheduled reconciliation and backfill pipelines built.
- [ ] Schema/metric versioning and rollback paths prepared.
- [ ] Read consistency tested while refreshes run.
- [ ] Alerts configured for summary lag and drift.

### 34.4. Production Readiness

- [ ] p95/p99 latency and CPU/IO within SLOs.
- [ ] Checked Search/sharding/server version constraints.
- [ ] `maxTimeMS`, client timeouts, and rate limits enforced.
- [ ] Zero cross-tenant data leakage.
- [ ] Backups/restores cover both source collections and summary/index definitions.
- [ ] Refresh workers run with least-privilege credentials.
- [ ] Benchmarked at realistic volume and state distributions.

---

## 35. Practice Exercises

### Exercise 1 — Basic Pipeline

Write a daily revenue aggregation for `tenant-a` in November 2026 using `$match` before `$group` and `$dateTrunc` with timezone `Asia/Ho_Chi_Minh`.

### Exercise 2 — Explaining Sort Order

Compare `$sort + $limit` against `$limit + $sort`. Why can the second fail to return the global top 20?

### Exercise 3 — ESR Index

Propose an index for `tenantId`, `status: "PAID"`, sorted by `paidAt: -1, _id: -1`, and run `explain`.

### Exercise 4 — Projection

Compare returning full order documents vs. projecting only `_id, paidAt, totalVnd`. Measure payload size and latency.

### Exercise 5 — Group Cardinality

Group by `status` vs. `customerId`; observe group counts and memory usage as the dataset grows.

### Exercise 6 — Proper `$first`

Find the newest order per customer, adding `_id` as a sort tie-breaker.

### Exercise 7 — Equality `$lookup`

Join `orders` → `customers` on `customerId` and `_id`, returning only `displayName`. Verify foreign index usage.

### Exercise 8 — Fan-Out

Join `customers` → all `orders` and `$unwind`. Calculate intermediate row counts when one customer has 10,000 orders.

### Exercise 9 — Top-3 Lookup

Write a correlated lookup returning the 3 newest orders per customer and propose a foreign compound index.

### Exercise 10 — Count Instead of Array

Replace an `allOrders` lookup with a grouped count/total pipeline. Compare memory and network usage.

### Exercise 11 — Tenant Filtering

Write a correlated lookup matching both `customerId` and `tenantId`. Test with colliding logical keys across two tenants.

### Exercise 12 — `$unwind`

One order has 5 items, another has 0 items. Compare outputs with `preserveNullAndEmptyArrays` enabled vs. disabled.

### Exercise 13 — `$facet`

Build a response returning 20 paginated orders, counts by status, and total revenue. Explain when stats should split into a summary query.

### Exercise 14 — `allowDiskUse`

Create a high-cardinality `$group` aggregation in a lab environment and compare `explain`/spill behavior under server settings.

### Exercise 15 — Materialized View

Create `dailyOrderSales` with a unique `(tenantId, day, currency)` key and `$group + $merge`. Query monthly summaries.

### Exercise 16 — Vanished Groups

After materializing, flip all orders for one day from `PAID` to `CANCELLED`. Why does a full-refresh `$merge` leave the stale row? Propose ways to delete, zero, or rebuild.

### Exercise 17 — Duplicate Events

A worker using `$inc` receives the same change event twice. Show how revenue double-counts and design deduplication.

### Exercise 18 — Order Changing Dates

An order updates `paidAt` from Nov 10 to Nov 11. List which buckets must be recomputed.

### Exercise 19 — Refunds

Choose a policy for gross revenue and refunds, designing two metrics so gross and net are never confused.

### Exercise 20 — Late Events

A payment settles at 23:59 on day 10 and arrives at the consumer at 00:05 on day 11. Explain event time vs. processing time and timezone handling.

### Exercise 21 — `$merge` Concurrency

Two workers recompute the same day from different source snapshots simultaneously. Propose serialization, CAS, or watermark controls.

### Exercise 22 — Incremental Min/Max

A group has min 100 and second min 120. When the 100 document is deleted, why can you not just subtract the min and why must you recompute?

### Exercise 23 — Change Streams

Design checkpoint-after-success and recovery after oplog history loss, plus handling deletes lacking before-images.

### Exercise 24 — Java Sync Driver

Build a `match/sort/limit/lookup/unwind/project` pipeline using `Document` and explain why `$limit` before `$lookup` is valid for that use case.

### Exercise 25 — Multi-Tenant Sharding

Describe the impact of tenant skew during grouping/joining and when updating a hot summary document.

### Exercise 26 — Benchmark

Compare on-demand raw aggregation against materialized summaries on a large dataset, measuring p95 latency, I/O, summary freshness, discrepancy rate, and write overhead.

---

## 36. Review Questions

1. What are the three major cost areas of aggregations, joins, and materialization?
2. When can `$match` be pushed earlier in a pipeline?
3. Why can not every `$match` be placed at the start of a pipeline?
4. How do `$geoNear`, `$search`, and `$vectorSearch` constrain stage order?
5. What does ESR stand for?
6. Why can a compound index satisfy both filtering and sorting?
7. Why can overly long indexes slow down writes?
8. What is a covered query?
9. When is `$sort` blocking?
10. How does the optimizer optimize `$sort + $limit`?
11. Why is deep `$skip` slow?
12. Which sort keys does keyset pagination need?
13. Does an early `$project` always improve speed?
14. What memory costs does `$group` incur?
15. Why does grouping by `customerId` differ from grouping by `status`?
16. What does `$first` mean without a prior sort?
17. Why is `$push: "$$ROOT"` dangerous for huge groups?
18. Does `allowDiskUse` bypass all memory limits?
19. Does `$lookup` return an object or an array?
20. Why are foreign indexes critical for `$lookup`?
21. How does `localField`/`foreignField` `$lookup` differ from correlated `pipeline`/`let`?
22. Under what conditions can `$expr` inside `$lookup` use an index?
23. What is join fan-out?
24. When should `$limit` precede `$lookup`?
25. Why can filtering VIP customers after `$limit` lose valid top-20 results?
26. How can `$unwind` alter row counts?
27. When should you use `$filter`/`$map` instead of `$unwind`?
28. What limits apply to `$facet`?
29. How does a MongoDB view differ from a materialized view?
30. When should data be precomputed?
31. How does `$merge` differ from `$out`?
32. Why does `$merge` require a unique index on `on` fields?
33. Why does a full-refresh `$merge` not delete vanished groups automatically?
34. When is a full refresh preferable to incremental updates?
35. Why can `$inc` per event double-count?
36. Do Change Streams guarantee exactly-once business processing?
37. What problem arises when delete events lack a before-image?
38. What is a contribution ledger used for?
39. Why should averages be stored as `sum` and `count`?
40. Why are `min`/`max` hard to update incrementally after deletes?
41. Why must `currency` be a dimension of revenue summaries?
42. How does a local business day differ from a UTC day?
43. How does late-arriving data affect summaries?
44. What concurrency bug occurs when an older worker overwrites a newer summary?
45. How do `computedAt` and a source watermark differ?
46. Between search indexes, caches, and summaries, which is the source of truth?
47. Where can sharded joins spend extra network overhead?
48. How should hot aggregate buckets be handled?
49. Why is `explain` insufficient to prove production SLOs?
50. Is a fast optimization that produces wrong business numbers acceptable?

---

## 37. Summary

Optimizing MongoDB aggregations, joins, and precomputed summaries spans three layers.

**Query layer:** Write semantically sound `$match`/`$sort`/`$limit`/`$project`/`$group` stages, eliminate wasted work, and prevent fan-out and unindexed large sorts.

**Physical access layer:** Pick compound indexes aligned with filters, sorts, and joins; verify `explain("executionStats")` for memory, spills, documents examined, and foreign scans.

**Architecture layer:** When dashboards repeatedly group massive datasets, materialize summaries via `$merge` or dedicated refresh pipelines. Always preserve an authoritative source of truth and define metrics, timezones, currencies, consistency contracts, idempotent refreshes, backfills, and reconciliation.

Key principles:

1. **Preserve correctness before optimizing:** never reorder limits, joins, or groups recklessly.
2. **Measure with `explain` and real benchmarks:** never infer from code or tiny datasets.
3. **Bound join fan-out:** fetch only needed rows/fields or aggregate before joining.
4. **Stop recomputing the same heavy report on every request** when precomputation meets freshness tolerances.
5. **Materialized summaries have their own lifecycle:** rebuilds, incremental updates, late events, deletes, concurrency, schema versioning, and monitoring.
6. **`$merge` does not automatically handle vanished groups, exactly-once semantics, or concurrent writer ordering.**
7. **Distinguish `computedAt` from true freshness:** track checkpoints/watermarks and reconcile periodically against the source.
8. **Tenant isolation, monetary precision, and timezones** are core parts of correctness, not minor details.

The final question when designing a pipeline is not merely "Can we cut 2 seconds down to 20 ms?"—it is **"Does that 20 ms still return the exact right dataset, for the right tenant, in the right time window, and stay accurate after updates, deletes, and retries?"**

## References

- [MongoDB Manual — Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/)
- [MongoDB Manual — Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/)
- [MongoDB Manual — Aggregation Commands](https://www.mongodb.com/docs/manual/aggregation/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual — $match](https://www.mongodb.com/docs/manual/reference/operator/aggregation/match/)
- [MongoDB Manual — $sort](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sort/)
- [MongoDB Manual — $limit](https://www.mongodb.com/docs/manual/reference/operator/aggregation/limit/)
- [MongoDB Manual — $project](https://www.mongodb.com/docs/manual/reference/operator/aggregation/project/)
- [MongoDB Manual — $group](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/)
- [MongoDB Manual — $lookup](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/)
- [MongoDB Manual — $unwind](https://www.mongodb.com/docs/manual/reference/operator/aggregation/unwind/)
- [MongoDB Manual — $facet](https://www.mongodb.com/docs/manual/reference/operator/aggregation/facet/)
- [MongoDB Manual — $setWindowFields](https://www.mongodb.com/docs/manual/reference/operator/aggregation/setWindowFields/)
- [MongoDB Manual — $dateTrunc](https://www.mongodb.com/docs/manual/reference/operator/aggregation/dateTrunc/)
- [MongoDB Manual — $merge](https://www.mongodb.com/docs/manual/reference/operator/aggregation/merge/)
- [MongoDB Manual — $out](https://www.mongodb.com/docs/manual/reference/operator/aggregation/out/)
- [MongoDB Manual — Read-Only Views and Materialized Views](https://www.mongodb.com/docs/manual/core/materialized-views/)
- [MongoDB Manual — ESR Index Guideline](https://www.mongodb.com/docs/manual/tutorial/equality-sort-range-guideline/)
- [MongoDB Manual — Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/)
- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [MongoDB Java Sync Driver — Aggregation](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/)
