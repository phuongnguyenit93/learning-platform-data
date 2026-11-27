# Limiting Intermediate Data from `$lookup`, `$unwind`, and `$group`

## 1. The problem: small final results, heavy memory usage

In a **Spring Data MongoDB** application, a reporting API may return only the top 20 best-selling products yet still process millions of order line items to compute those 20 rows. Intermediate data generated when combining `$lookup`, `$unwind`, and `$group` is often vastly larger than the displayed output.

Example dataset across two collections:

- `orders`: `_id`, `tenantId`, `status`, `placedAt`; each document represents an order.
- `order_items`: `_id`, `orderId`, `productId`, `state`, `quantity`, `netAmount`; each document represents a line item.

Requirement: find the **top 20 highest-revenue products** across paid orders for a tenant within a date range. Revenue equals the sum of `netAmount` for items with `state = "VALID"`. Suppose a day sees **10,000 orders**, averaging **200 items** each; ordering stages poorly can force the pipeline to process around **2 million lines** just to return 20 products.

This lesson helps you:

1. Distinguish **intermediate document count**, **BSON size**, and **pipeline execution memory**.
2. Estimate data inflation across `$lookup` → `$unwind` → `$group`.
3. Design pipelines that minimize fan-out, document width, and accumulated state.
4. Apply these techniques with `MongoTemplate`, Spring Data Aggregation API, and reactive access.
5. Verify improvements using `explain("executionStats")` and realistic load testing.

## 2. How do these three operations create intermediate cost?

### 2.1. `$lookup`: expands arrays inside parent documents

A `$lookup` joining `orders._id = order_items.orderId` usually attaches an `items` array field to each order document:

```javascript
{
  $lookup: {
    from: "order_items",
    localField: "_id",
    foreignField: "orderId",
    as: "items"
  }
}
```

If `N` orders enter `$lookup`, and order `i` matches `k_i` line items, the logical output count of the join stays `N`, yet each document carries an `items` array of `k_i` elements. Intermediate data volume depends on **each line item's size** and `k_i`, not just order count.

A `$lookup` on an unindexed `foreignField` can repeatedly scan the foreign collection. When a parent matches thousands of child documents, building, processing, and passing joined arrays is costly even when only a total revenue sum is needed.

### 2.2. `$unwind`: multiplies cardinality

```javascript
{ $unwind: "$items" }
```

Each `items` element becomes a separate output document. If every order has at least one item, document count after `$unwind` is:

\[
N_{\text{after unwind}} = \sum_{i=1}^{N} k_i
\]

With 10,000 orders × 200 items/order, that is roughly **2,000,000 documents**. In the logical stream after `$unwind`, parent document fields are repeated per child item. Retaining addresses, notes, status histories, and large parent arrays bloats every intermediate record pointlessly.

Important edge cases:

| Array before `$unwind` | `preserveNullAndEmptyArrays: false` (default) | `preserveNullAndEmptyArrays: true` |
| --- | --- | --- |
| Has 3 elements | 3 documents | 3 documents |
| Empty array | 0 documents | 1 document |
| Missing/null | 0 documents | 1 document |

Do not blindly set `preserveNullAndEmptyArrays: true` when reports only count valid line items; orders lacking items can skew counts if downstream logic does not distinguish them.

### 2.3. `$group`: shrinks output while holding state in RAM

```javascript
{
  $group: {
    _id: "$items.productId",
    revenue: { $sum: "$items.netAmount" },
    lineCount: { $sum: 1 }
  }
}
```

`$group` is a **blocking stage**: it must process all relevant inputs before emitting grouped totals. Output may shrink to a few thousand products, yet the server still holds accumulated state per distinct group key and accumulator.

Two designs yielding 1,000 groups can have vastly different memory footprints:

```javascript
// Usually compact: stores only sum and count per group.
{ $group: {
    _id: "$items.productId",
    revenue: { $sum: "$items.netAmount" },
    count: { $sum: 1 }
} }

// Prone to bloat: accumulates every child document inside each group's array.
{ $group: {
    _id: "$items.productId",
    allItems: { $push: "$items" }
} }
```

`$sum` and `$count` generally require tiny per-group state. `$push`/`$addToSet` accumulate arrays and consume dramatically more memory and BSON space. Never use `$push: "$$ROOT"` "just in case" when the API only needs counts and revenue.

### 2.4. Thinking along two axes: fan-out and document width

| Stage in pipeline | Logical document count | Document width | Likely cost drivers |
| --- | ---: | --- | --- |
| `$match` orders by tenant/date/status | Matching orders | Original order fields | Scans when indexes are missing |
| `$project` keeping only `_id` | Unchanged | Small | Read cost without a suitable index |
| `$lookup` line items | May remain unchanged | `items` array can be huge | Join scans, match counts, array construction |
| `$unwind` `items` array | Can surge sharply | Repeats parent metadata per line | CPU, processing, inter-stage data transfer |
| `$group` by product | Distinct `productId` count | Depends on accumulators | Memory/spill, oversized arrays |
| `$sort` then `$limit: 20` | Down to 20 | Small if group output is lean | Sort cost if grouped output remains large |

Table entries represent **logical cardinality**, not an assertion that MongoDB holds all intermediate documents in RAM simultaneously. The query optimizer may coalesce stages and the engine can stream execution.

## 3. Practical MongoDB limits

### 3.1. The 16 MiB BSON document size limit

MongoDB caps **each returned result document** at **16 MiB BSON**. During aggregation processing, certain intermediate documents can exceed 16 MiB, so do not assume every temporary `$lookup` output immediately fails upon crossing that threshold.

Still, holding large joined arrays or `$group` with `$push` to emit a single document readily hits the 16 MiB wall. For instance, `$group: { _id: null, allOrders: { $push: "$$ROOT" } }` can fail on large data even though only one document is returned.

Shrink document size by **not accumulating whole documents into arrays**, retaining only summary figures or emitting separate result documents where business logic permits.

### 3.2. Blocking stage 100 MB memory limit and spilling

Stages like `$group`, `$sort`, and `$bucket` enforce roughly a **100 MB/stage** execution memory limit. When exceeded, spill-capable stages write temporary data to disk if `allowDiskUse` is permitted; otherwise, the pipeline errors out due to memory limits.

Since MongoDB **6.0**, the server setting `allowDiskUseByDefault` governs default behavior. Aggregation commands can override it with `{ allowDiskUse: true }` or `{ allowDiskUse: false }`.

```javascript
db.orders.aggregate(
  [ /* report stages */ ],
  {
    allowDiskUse: true,
    maxTimeMS: 30_000,
    comment: "performance-007-report"
  }
);
```

**`allowDiskUse: true` does not grant infinite memory and does not fix a flawed algorithm.** Certain accumulators like `$push` have their own array accumulation limits and cannot spill those arrays to disk. Other internal limits can still trigger depending on stage or server version. Heavy temporary disk spilling can also slow queries and pressure disk I/O.

Since MongoDB **9.0**, there is also a **total per-operation memory limit** alongside per-stage limits. By default it is the greater of **1 GiB** or **20% of available memory for the server process** (configurable). When investigating memory errors on newer versions, distinguish per-stage, accumulator, and total operation limits.

### 3.3. Other relevant limits

- An aggregation pipeline has a limit of **1,000 stages** after parsing and optimization. Trimming redundant stages helps readability, though stage count rarely matters as much as cardinality and indexes.
- `$lookup` carries constraints around schemas, indexes, server versions, sharding setups, and collection types. Do not assume `allowDiskUse` rescues every giant joined array.
- `$group` does not guarantee output order. For top 20 by revenue, place an explicit `$sort` before `$limit`.
- Cursors and `batchSize` pace result delivery to the client in batches; they do **not** limit how many records server-side stages must process.

## 4. A pipeline pattern prone to large intermediate data

A common anti-pattern joins all line items, unwinds them, and filters orders afterward:

```javascript
const start = ISODate("2026-10-01T00:00:00Z");
const end   = ISODate("2026-11-01T00:00:00Z");

db.orders.aggregate([
  {
    $lookup: {
      from: "order_items",
      localField: "_id",
      foreignField: "orderId",
      as: "items"
    }
  },
  { $unwind: "$items" },
  {
    $match: {
      tenantId: "tenant-01",
      status: "PAID",
      placedAt: { $gte: start, $lt: end },
      "items.state": "VALID"
    }
  },
  {
    $group: {
      _id: "$items.productId",
      revenue: { $sum: "$items.netAmount" },
      lineCount: { $sum: 1 }
    }
  },
  { $sort: { revenue: -1, _id: 1 } },
  { $limit: 20 }
]);
```

Problems with writing it this way:

1. `tenantId`, `status`, and `placedAt` are independent of the join yet appear after `$lookup`; if not hoisted early, unneeded orders enter the join.
2. `$lookup` fetches **every field** of each line item even though `$group` only uses `productId` and `netAmount`.
3. `$unwind` creates fan-out before filtering `state = "VALID"` lines.
4. Most intermediate data is computed only to discard everything outside the final top 20 groups.

MongoDB has a **query optimizer**, so physical execution does not always mirror literal JSON order. For instance, independent `$match` predicates can be hoisted, and `$lookup` → `$unwind` → `$match` may **coalesce** into an internal `$lookup`. Inspect `explain` before declaring this form slow in every version.

## 5. Designing pipelines to shrink data at the source

### 5.1. `$match` orders before joining; keep only required fields

Send only orders matching the tenant, status, and date range into `$lookup`.

```javascript
const start = ISODate("2026-10-01T00:00:00Z");
const end   = ISODate("2026-11-01T00:00:00Z");

db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-01",
      status: "PAID",
      placedAt: { $gte: start, $lt: end }
    }
  },
  { $project: { _id: 1 } },
  {
    $lookup: {
      from: "order_items",
      localField: "_id",
      foreignField: "orderId",
      pipeline: [
        { $match: { state: "VALID" } },
        { $project: { _id: 0, productId: 1, netAmount: 1 } }
      ],
      as: "items"
    }
  },
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.productId",
      revenue: { $sum: "$items.netAmount" },
      lineCount: { $sum: 1 }
    }
  },
  { $sort: { revenue: -1, _id: 1 } },
  { $limit: 20 }
], {
  allowDiskUse: true,
  maxTimeMS: 30_000
});
```

Combining `localField`/`foreignField` with `pipeline` inside `$lookup` is supported on MongoDB **5.0+**. The `pipeline` filters and trims foreign documents before returning joined results to the main pipeline.

This design shrinks **participating orders**, **line items entering the join array**, and **width per line item**. Shrinking data usually matters far more than enabling disk spill.

### 5.2. Indexing filters and join keys

On `orders`, the filter checks tenant, status, and date range; a candidate compound index:

```javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  placedAt: 1
});
```

On `order_items`, the join condition uses `orderId` and keeps only valid lines:

```javascript
db.order_items.createIndex({
  orderId: 1,
  state: 1
});
```

These are **candidate indexes**, not universal recipes for every workload. Inspect `explain` to verify server index usage, examined keys/documents, and write-overhead trade-offs. For `$lookup` using `let`/`$expr`, index usability depends on predicate forms and constraints (such as comparing fields against eligible constants, null handling, and multikey limits).

Do not create large indexes solely to eliminate `COLLSCAN` on tiny datasets; judge index value by workload and selectivity.

### 5.3. Pre-aggregating in the foreign collection when only totals are needed

If an order has multiple lines sharing `productId`, you can **pre-group per order and product inside `$lookup.pipeline`** before emitting to the main stream:

```javascript
{
  $lookup: {
    from: "order_items",
    localField: "_id",
    foreignField: "orderId",
    pipeline: [
      { $match: { state: "VALID" } },
      {
        $group: {
          _id: "$productId",
          revenue: { $sum: "$netAmount" },
          lineCount: { $sum: 1 }
        }
      }
    ],
    as: "productTotals"
  }
}
```

Then `$unwind: "$productTotals"` and `$group` again on `"$productTotals._id"`, summing `revenue` and `lineCount` across orders:

```javascript
{ $unwind: "$productTotals" },
{
  $group: {
    _id: "$productTotals._id",
    revenue: { $sum: "$productTotals.revenue" },
    lineCount: { $sum: "$productTotals.lineCount" }
  }
}
```

This helps when **each order contains many duplicate products**; if most products appear once per order, an extra `$group` inside the foreign pipeline can actually slow things down. Compare group counts and intermediate records before adopting it. Also, `$group` inside a subpipeline remains subject to memory limits.

### 5.4. Controlling fan-out without breaking correctness

Different options carry different semantics:

| Technique | When to use | Correctness risk |
| --- | --- | --- |
| `$match` parent before `$lookup` | Always prefer when conditions are join-independent | Preserves results within the filter scope. |
| `$match` inside `$lookup.pipeline` | Only keep child lines relevant to the report | Preserve parent semantics if parents without items must stay. |
| `$project` inside foreign pipeline | Keep only fields needed for calculation | Do not drop fields used by later stages. |
| `$limit` inside foreign pipeline | Business logic genuinely wants at most `K` items per parent | **Corrupts totals** if all child items must be summed. |
| `$sort` + `$limit` before `$lookup` | Analyzing `K` parents chosen by pre-join criteria | Corrupts top `K` ranked by post-join metrics like revenue. |
| `$group` with `$sum`/`$count` | Aggregated numbers are needed | Define eligible lines and numeric currency types carefully. |
| `$group` with `$push` | Full item list is genuinely required | Risks accumulator array and BSON size limits. |

Common wrong example:

```javascript
// DO NOT use when total revenue across all line items is required.
{
  $lookup: {
    from: "order_items",
    localField: "_id",
    foreignField: "orderId",
    pipeline: [
      { $sort: { netAmount: -1, _id: 1 } },
      { $limit: 5 }
    ],
    as: "items"
  }
}
```

This pipeline examines only the **top 5 highest-revenue lines per order**, so product totals no longer reflect all items. It is only valid if the report explicitly asks for "top 5 lines per order." Whenever using `$limit` intentionally, pair `$sort` with a deterministic tie-breaker for reproducible results.

### 5.5. Avoiding long arrays in `$group`

If a report needs a few top entries rather than full lists, consider bounded accumulators such as `$topN` or `$firstN` (available since MongoDB 5.2), or compute totals and pick top items via `$sort` + `$limit`. Bounded accumulators have specific usage conditions and do not blindly replace full aggregations.

Example listing the **3 highest-value lines per product** on supported versions:

```javascript
{
  $group: {
    _id: "$productId",
    topItems: {
      $topN: {
        n: 3,
        sortBy: { netAmount: -1, _id: 1 },
        output: { orderId: "$orderId", netAmount: "$netAmount" }
      }
    }
  }
}
```

This yields the **top 3**, not all lines. `$topN` still consumes memory under relevant limits; it merely avoids growing an array proportional to every item in a group.

When exact monetary arithmetic is required, prefer storing `netAmount` as **Decimal128** (or smallest-unit integers by design) instead of error-prone `double` floats.

## 6. MongoDB can coalesce `$lookup`, `$unwind`, and `$match`

Example stage sequence:

```javascript
{
  $lookup: {
    from: "order_items",
    localField: "_id",
    foreignField: "orderId",
    as: "items"
  }
},
{ $unwind: "$items" },
{ $match: { "items.state": "VALID" } }
```

When eligible, the MongoDB optimizer **coalesces** `$unwind` into `$lookup`, and may push `items`-related `$match` filters into the lookup as well. In `explain`, you might see an internal `$lookup` containing `pipeline` and an `unwinding` field, avoiding materializing large intermediate arrays.

Key takeaway: **do not evaluate optimization purely from input JSON stage order**. Writing explicit `$match` and `$project` upfront remains readable, maintainable, and clear in intent, while performance conclusions must come from the actual execution plan.

Other optimizer interactions:

- Adjacent `$sort` + `$limit` can coalesce into a top-`K` sort instead of sorting everything. If `$unwind` or `$group` **alters document count in between**, the optimizer cannot merge them without breaking semantics.
- Early `$match` can use indexes on the primary collection; an initial `$sort` can also use an index when eligible.
- Equality-join `$lookup` may execute via `EQ_LOOKUP` under the Slot-Based Execution Engine on supported versions; `$lookup` with a foreign subpipeline may follow a different execution path than SBE. Never expect every join pipeline to show `EQ_LOOKUP`.

## 7. Implementing with Spring Data MongoDB

### 7.1. Concise pipeline via Aggregation API

The example below uses standard `MongoTemplate` operations, suitable for straightforward joins; key imports:

```java
import java.time.Instant;
import java.util.List;

import org.bson.Document;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationOptions;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.data.mongodb.core.query.Criteria;

// mongoTemplate is an injected Spring bean.
Aggregation pipeline = Aggregation.newAggregation(
    Aggregation.match(
        Criteria.where("tenantId").is("tenant-01")
            .and("status").is("PAID")
            .and("placedAt")
                .gte(Instant.parse("2026-10-01T00:00:00Z"))
                .lt(Instant.parse("2026-11-01T00:00:00Z"))
    ),
    Aggregation.project("_id"),
    Aggregation.lookup("order_items", "_id", "orderId", "items"),
    Aggregation.unwind("items"),
    Aggregation.match(Criteria.where("items.state").is("VALID")),
    Aggregation.group("items.productId")
        .sum("items.netAmount").as("revenue")
        .count().as("lineCount"),
    Aggregation.sort(Sort.by(
        Sort.Order.desc("revenue"),
        Sort.Order.asc("_id")
    )),
    Aggregation.limit(20)
).withOptions(
    AggregationOptions.builder().allowDiskUse(true).build()
);

AggregationResults<Document> result =
    mongoTemplate.aggregate(pipeline, "orders", Document.class);
List<Document> topProducts = result.getMappedResults();
```

Stage order here filters parents early, though basic `lookup(...)` does not yet trim foreign document fields. When joined data is large, choose a `LookupOperation` builder supporting `pipeline` in your Spring Data version, or provide a custom BSON `AggregationOperation`.

### 7.2. Using `AggregationOperation` for `$lookup.pipeline`

Example building the BSON stage directly in Java:

```java
import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;

AggregationOperation reducedLookup = context ->
    new Document("$lookup",
        new Document("from", "order_items")
            .append("localField", "_id")
            .append("foreignField", "orderId")
            .append("pipeline", List.of(
                new Document("$match",
                    new Document("state", "VALID")),
                new Document("$project",
                    new Document("_id", 0)
                        .append("productId", 1)
                        .append("netAmount", 1))
            ))
            .append("as", "items"));

// Replace Aggregation.lookup(...) in the pipeline above with reducedLookup.
// Also remove the trailing Aggregation.match("items.state") since filtering
// now happens in the subpipeline. Keep group/sort/limit stages unchanged.
```

Note when constructing raw BSON: strings `"orderId"` and `"netAmount"` are **stored MongoDB field names**, which may differ from Java property names mapped with `@Field`. Never concatenate request parameters into raw JSON strings; pass values via typed BSON/Criteria APIs to avoid date, ObjectId, or numeric type bugs.

`allowDiskUse(true)` only permits disk spill in MongoDB; it **does not cap `$lookup`/`$unwind` document counts** and is no substitute for shrinking data. To bound API execution time, configure appropriate `maxTime`/timeouts in `AggregationOptions` or the corresponding execution layer.

### 7.3. Repositories and reactive access

`@Aggregation` on repositories is handy for fixed reports, yet the pipeline still executes through MongoDB stages; a repository returning a short `List<T>` does not magically limit intermediate joined lines.

With `ReactiveMongoTemplate`, the main difference is consuming output as `Flux`/`Mono`. Reactor backpressure primarily throttles **items emitted to the client** and does not guarantee reducing how many documents the server joins/groups beforehand.

```java
// Illustrative extension: reuses the pipeline from the example above.
Flux<Document> stream = reactiveMongoTemplate
    .aggregate(pipeline, "orders", Document.class);
// Subscribing controls downstream flow to the application;
// it does not replace server-side $match or fan-out reduction.
```

For both blocking and reactive approaches, benchmark only on datasets with realistic `items/order` ratios and `productId` distributions. Tests with just a couple of lines per order will hide production pipeline bottlenecks.

## 8. Measuring document counts and true cost with `explain`

### 8.1. Verifying indexes and cardinality

Use the application's actual pipeline:

```javascript
const pipeline = [
  // Paste stages from section 5.1.
];

db.orders.explain("executionStats").aggregate(
  pipeline,
  { allowDiskUse: true }
);
```

Questions to ask while reading `explain`:

| What to look for | Meaning |
| --- | --- |
| `totalKeysExamined`, `totalDocsExamined` | Keys and documents read by the engine. Far larger than needed documents signals weak indexes/filters. |
| `IXSCAN`, `COLLSCAN` | Did the pipeline start and join using indexes or collection scans? |
| `indexesUsed`, `collectionScans` (if reported for `$lookup`) | Did the join utilize an index on the foreign collection? |
| `nReturned`, `executionTimeMillisEstimate` per stage if present | Which stage inflates cardinality or consumes time? |
| `usedDisk`, `spills`, memory stats if present | Which stage spilled to disk or hit memory pressure? |
| `unwinding` in `$lookup`, `EQ_LOOKUP` if present | Did the optimizer coalesce join/unwind or choose a dedicated join strategy? |

**Explain shapes vary across MongoDB Server versions, engines, stage types, and builds.** Do not expect every field listed above in every plan. Also, `explain`'s `executionTimeMillis` does not equal real API latency under network, mapping, cache, and concurrent load.

A meaningful before/after benchmark:

1. Keep **the same dataset, indexes, server settings, report time window, and ratio of large-item orders**.
2. Record filtered parent count before join, estimated `items/order` fan-out (mean and p95/p99), distinct product count, and output BSON size.
3. Compare `explain("executionStats")` before and after; confirm indexes on both `orders` and `order_items` are used.
4. Run representative load after warm-up, measuring **p50/p95/p99 latency**, CPU, RAM, I/O, `usedDisk`, error rates, and server execution time.
5. Verify identical output results on edge-case datasets; never trade correctness for speed.

To gauge joined line counts, you can run a **separate** diagnostic pipeline on the filtered orders:

```javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-01",
      status: "PAID",
      placedAt: {
        $gte: ISODate("2026-10-01T00:00:00Z"),
        $lt: ISODate("2026-11-01T00:00:00Z")
      }
    }
  },
  {
    $lookup: {
      from: "order_items",
      localField: "_id",
      foreignField: "orderId",
      pipeline: [
        { $match: { state: "VALID" } },
        { $count: "n" }
      ],
      as: "stats"
    }
  },
  {
    $project: {
      validItemCount: {
        $ifNull: [ { $first: "$stats.n" }, 0 ]
      }
    }
  },
  {
    $group: {
      _id: null,
      orderCount: { $sum: 1 },
      validItemTotal: { $sum: "$validItemCount" },
      maxValidItemsPerOrder: { $max: "$validItemCount" }
    }
  }
]);
```

This is a **diagnostic query** and consumes resources itself. Run it bounded in an appropriate environment; never accidentally place it on a production request path.

## 9. Common bad choices

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `$lookup` before any filter | Joins many unneeded parents. | `$match` parent fields as early as possible; verify optimizer via explain. |
| Missing index on `foreignField` | Join can scan the foreign collection repeatedly. | Design indexes matching join keys and actual filter predicates. |
| `$unwind` large arrays and `$project` last | Intermediate documents carry unneeded fields. | Trim fields before join and inside subpipeline; check engine optimization. |
| `$group` + `$push: "$$ROOT"` when only counting | Huge arrays, memory/BSON errors despite spill enabled. | Use `$sum`, `$count`, compact accumulators, or bounded top-N. |
| Arbitrary `$limit` inside `$lookup` | Corrupts totals and top-20 rankings. | Limit only when required by business logic after deterministic sorting. |
| Treating `allowDiskUse` as a performance cure | Slow due to I/O and can still hit separate limits. | Shrink cardinality, width, group count, and monitor `usedDisk`. |
| Setting small `batchSize` thinking the join is lighter | Server still computes groups before returning cursor. | Measure pipeline and explain on the server side. |
| Omitting `$sort` before top 20 | Output order is not guaranteed. | `$sort` by metric and tie-breaker key, then `$limit`. |
| Using `double` for money across many items | Floating-point rounding drift. | Use Decimal128 or smallest-unit integers. |

## 10. Hands-on exercises

Suppose there are **100,000 orders**, averaging 80 lines each; 5% of orders exceed 1,000 lines. Each `order_items` document also carries a 2 KiB `description` and 3 KiB `extraAttributes`, while the report only needs `productId`, `netAmount`, and `state`.

1. Estimate the **logical document count after `$unwind`** if joining all orders using the 80 lines/order average; explain why p95/p99 skew still poses risks for documents with huge arrays.
2. Rewrite the pipeline putting `$match` on tenant/date/status before the join, minimal `$project`, and `$lookup.pipeline` to filter valid items.
3. Choose indexes for both collections; name the fields in `explain` that confirm both indexes are active.
4. Prove why `{ $limit: 10 }` at the end of the pipeline and `{ $limit: 10 }` inside `$lookup.pipeline` are **not equivalent**.
5. Compare `$group: { all: { $push: "$$ROOT" } }` with `$group: { count: { $sum: 1 } }` when one product appears across 300,000 lines.
6. Describe how to distinguish failures caused by the 16 MiB BSON limit, 100 MB stage limit, `$push`-specific limits, and total operation memory limits in MongoDB 9.0+.
7. Implement the report with `MongoTemplate`, measure before/after using `explain`, and test with `allowDiskUse: false` in a test environment to observe memory limits—avoid heavy load tests in production.

**Hint:** At 100,000 × 80, the estimate is **8,000,000 documents** after unwinding (assuming uniform average line counts). This calculation measures logical cardinality only; do not infer MongoDB holds all 8 million documents in RAM at once. A thorough solution proves revenue totals and rankings remain exact after optimization.

## References

- [MongoDB — Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/)
- [MongoDB — Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/)
- [MongoDB — `$lookup` stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/)
- [MongoDB — `$unwind` stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/unwind/)
- [MongoDB — `$group` stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/)
- [MongoDB — `$push` accumulator](https://www.mongodb.com/docs/manual/reference/operator/aggregation/push/)
- [Spring Data MongoDB — Aggregation Framework Support](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html)
- [Spring Data MongoDB — AggregationOptions.Builder API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/aggregation/AggregationOptions.Builder.html)
