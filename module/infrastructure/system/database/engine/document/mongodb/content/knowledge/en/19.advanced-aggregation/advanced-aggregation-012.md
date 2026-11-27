# Reading `explain` for Aggregation and Optimizing Stage Order in MongoDB

An aggregation pipeline can return the correct results yet still run slowly on large collections. This may happen because MongoDB has to read too many documents before filtering, sort a wide dataset, multiply row counts with `$unwind`, create too many intermediate groups with `$group`, or access another collection repeatedly via `$lookup`. Looking at the pipeline command alone is not enough to know what work the server actually performs.

In the **Advanced Aggregation** chapter, we combine two skills:

1. **Reading aggregation `explain` output:** determining whether a query uses an index, which parts scan a collection, where stages execute, how much data is examined, and whether memory-intensive sort/group operations or disk spills occur.
2. **Optimizing stage order:** moving early-applicable filters forward, leveraging indexes for `$match` and `$sort`, placing `$limit` appropriately, curbing row expansion from `$unwind` and join volume from `$lookup`, all while preserving **the exact same result semantics**.

One critical principle to keep in mind from the outset is that MongoDB includes an **aggregation optimizer**. The server can automatically move, split, or coalesce certain stages whenever doing so preserves semantics. Therefore, optimizing is not simply a matter of reordering lines in the pipeline and assuming it will be faster; always use `explain` to inspect the post-optimization plan and measure on representative data.

## 1. Pipeline mindset: data flowing through each stage

An example pipeline:

```javascript
db.orders.aggregate([
  { $match: { status: "paid" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 10 },
  { $project: { _id: 1, customerId: 1, total: 1 } }
])
```

Logical flow:

```text
orders collection
      |
      v
  $match status=paid        Keep paid orders
      |
      v
  $sort newest first        Establish ordering
      |
      v
  $limit 10                 Take at most 10 orders
      |
      v
  $project                  Keep fields needed for display
      |
      v
  Result
```

To compare pipelines, distinguish these concepts:

| Concept | Meaning | What to observe |
| --- | --- | --- |
| **Written order in pipeline** | Semantics declared by the developer | Does an earlier stage create fields needed by a later stage? |
| **Optimizer-transformed pipeline** | Steps MongoDB can move/coalesce when equivalent | Is `$match` pushed ahead of `$project`? Is `$limit` coalesced into `$sort`? |
| **Collection-access query plan** | How initial data is fetched from the collection/index | `COLLSCAN`, `IXSCAN`, `FETCH`, `SORT`, index bounds |
| **Execution of remaining stages** | Work performed by `$group`, `$lookup`, `$unwind`, `$setWindowFields`, etc. | Input/output row counts, timing, memory, and spills if reported |

A pipeline written in two ways with the same logical result may be transformed by the optimizer into a very similar plan. However, a **non-equivalent** reordering produces different results and is not a valid optimization.

## 2. Preparing the practice dataset

Open `mongosh` and select a dedicated database:

```javascript
use mongo_aggregation_explain_lab
```

Insert 12 orders into a new or empty `orders` collection:

```javascript
db.orders.insertMany([
  {
    _id: 101, customerId: "u1", status: "paid",
    region: "north", total: 120,
    createdAt: ISODate("2026-11-10T08:00:00Z"),
    items: [{ sku: "A", qty: 2 }, { sku: "B", qty: 1 }]
  },
  {
    _id: 102, customerId: "u2", status: "paid",
    region: "south", total: 250,
    createdAt: ISODate("2026-11-10T09:00:00Z"),
    items: [{ sku: "B", qty: 3 }]
  },
  {
    _id: 103, customerId: "u1", status: "pending",
    region: "north", total: 80,
    createdAt: ISODate("2026-11-10T10:00:00Z"),
    items: [{ sku: "C", qty: 1 }]
  },
  {
    _id: 104, customerId: "u3", status: "paid",
    region: "north", total: 300,
    createdAt: ISODate("2026-11-11T08:00:00Z"),
    items: [{ sku: "A", qty: 1 }, { sku: "C", qty: 2 }]
  },
  {
    _id: 105, customerId: "u2", status: "refunded",
    region: "south", total: 70,
    createdAt: ISODate("2026-11-11T09:00:00Z"),
    items: [{ sku: "B", qty: 1 }]
  },
  {
    _id: 106, customerId: "u1", status: "paid",
    region: "south", total: 180,
    createdAt: ISODate("2026-11-11T10:00:00Z"),
    items: [{ sku: "A", qty: 3 }]
  },
  {
    _id: 107, customerId: "u4", status: "pending",
    region: "north", total: 90,
    createdAt: ISODate("2026-11-12T08:00:00Z"),
    items: [{ sku: "B", qty: 2 }]
  },
  {
    _id: 108, customerId: "u3", status: "paid",
    region: "south", total: 210,
    createdAt: ISODate("2026-11-12T09:00:00Z"),
    items: [{ sku: "C", qty: 3 }]
  },
  {
    _id: 109, customerId: "u2", status: "paid",
    region: "north", total: 160,
    createdAt: ISODate("2026-11-12T10:00:00Z"),
    items: [{ sku: "A", qty: 2 }]
  },
  {
    _id: 110, customerId: "u5", status: "paid",
    region: "south", total: 130,
    createdAt: ISODate("2026-11-12T11:00:00Z"),
    items: [{ sku: "B", qty: 1 }]
  },
  {
    _id: 111, customerId: "u4", status: "paid",
    region: "north", total: 110,
    createdAt: ISODate("2026-11-13T08:00:00Z"),
    items: [{ sku: "A", qty: 1 }]
  },
  {
    _id: 112, customerId: "u5", status: "pending",
    region: "south", total: 60,
    createdAt: ISODate("2026-11-13T09:00:00Z"),
    items: [{ sku: "C", qty: 1 }]
  }
])
```

Add a small collection to illustrate joins:

```javascript
db.customers.insertMany([
  { _id: "u1", name: "An", tier: "gold" },
  { _id: "u2", name: "Bình", tier: "silver" },
  { _id: "u3", name: "Chi", tier: "gold" },
  { _id: "u4", name: "Dũng", tier: "silver" },
  { _id: "u5", name: "Em", tier: "bronze" }
])
```

From the data above:

| Order group | Document count | Sum of `total` |
| --- | ---: | ---: |
| `paid` | 8 | 1,460 |
| `pending` | 3 | 230 |
| `refunded` | 1 | 70 |
| `paid` and `region: "north"` | 4 | 690 |
| `paid` and `region: "south"` | 4 | 770 |

**Note:** A tiny dataset is ideal for verifying semantics, but **it does not represent production performance**. With just a handful of documents, `COLLSCAN` can be extremely cheap and the query planner may not pick an index even when one exists. Do not extrapolate exact `keysExamined` counts or runtimes from these examples.

Run the `insertMany()` commands only once on an empty collection; running them again with the same `_id` values will fail with duplicate key errors. Never delete important data just to re-run a lab.

## 3. Running `explain` on an aggregation pipeline

The most direct way in `mongosh` is using the explainable collection helper:

```javascript
const pipeline = [
  { $match: { status: "paid", region: "north" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 3 },
  { $project: { _id: 1, customerId: 1, total: 1, createdAt: 1 } }
];

db.orders.explain("queryPlanner").aggregate(pipeline);
db.orders.explain("executionStats").aggregate(pipeline);
db.orders.explain("allPlansExecution").aggregate(pipeline);
```

The three verbosity levels serve distinct purposes:

| Verbosity | Key information | When to use |
| --- | --- | --- |
| `queryPlanner` | Winning plan, indexes, rejected plans, optimized structure | Understanding the data-access path and how the optimizer organized the query |
| `executionStats` | Adds execution metrics for the winning plan and reported stages | Checking how many keys/documents were examined, returned counts, and cost indicators |
| `allPlansExecution` | Adds trial-period statistics for candidate plans when multiple plans exist | Investigating why the planner chose between competing candidate plans |

`allPlansExecution` does **not** mean every candidate plan ran over the entire dataset. Candidate stats primarily reflect the **plan-selection trial period**, while full operational statistics correspond to the winning plan during the explain run.

### Calling via database command

When you need to issue the command directly (also useful for the Java Driver):

```javascript
db.runCommand({
  explain: {
    aggregate: "orders",
    pipeline: [
      { $match: { status: "paid" } },
      { $group: { _id: "$region", totalAmount: { $sum: "$total" } } }
    ],
    cursor: {}
  },
  verbosity: "executionStats"
})
```

This runs against the **current database** and returns an explain document rather than report rows like a normal `aggregate()`. For performance analysis, use a pipeline identical to your production query: the same filters, sort, projection, limit, collation, and relevant options.

### Why not just run `explain()` on `find()`?

An aggregation may do:

```javascript
[
  { $match: { status: "paid" } },
  { $unwind: "$items" },
  { $group: { _id: "$items.sku", qty: { $sum: "$items.qty" } } },
  { $sort: { qty: -1 } }
]
```

`find({status:"paid"}).explain()` only tells you how the query retrieves `paid` orders. It **does not describe the cost** of unwinding items, summing by SKU, and sorting the groups. To understand the real pipeline, run `explain` on **the aggregation pipeline itself**.

## 4. Reading the structure of aggregation `explain` output

Depending on MongoDB version, server configuration, and pipeline type, the explain document can appear in different shapes.

**Shape with explicit aggregation stages:**

```javascript
// Structural diagram showing section placement, not actual output
{
  stages: [
    {
      $cursor: {
        queryPlanner: {
          winningPlan: { /* collection-access plan tree */ }
        },
        executionStats: { /* present at corresponding verbosity */ }
      }
    },
    { $group: { /* stage represented in explain */ } },
    { $sort: { /* stage details and metrics, if reported */ } }
  ]
}
```

**Shape with top-level query planner:**

```javascript
// Illustrative diagram
{
  queryPlanner: {
    winningPlan: {
      queryPlan: { /* stages such as IXSCAN, GROUP, or EQ_LOOKUP */ },
      slotBasedPlan: { /* when applicable for SBE */ }
    }
  },
  executionStats: {
    nReturned: 0,
    totalKeysExamined: 0,
    totalDocsExamined: 0,
    executionStages: { /* execution details */ }
  }
}
```

The `0` values in this diagram are merely placeholders showing field types, **not real measurements**. Some pipelines get pushed down into the query execution engine and appear inside `winningPlan`; others expose a top-level `stages` array. With the **slot-based execution engine (SBE)**, the structure can also include `queryPlan`, `slotBasedPlan`, and stages that differ from the classic engine.

Never build scripts assuming every aggregation explain has a fixed JSON path like `result.queryPlanner.winningPlan.stage`. Check the query type, version, sharding topology, and where MongoDB places the `$cursor`/`executionStats` sections.

### Components to recognize

| Component | What to look for | Notes |
| --- | --- | --- |
| `$cursor` | Part that reads input documents from the collection | Usually holds the planner and execution metrics for the read step |
| `winningPlan` | Plan selected by MongoDB during this explain | Can use different tree formats depending on the query engine |
| `rejectedPlans` | Candidate plans not selected | Does not mean they are wrong or broken |
| `COLLSCAN` | Collection scan | Sometimes fine if the dataset is tiny or predicate selectivity is very low |
| `IXSCAN` | Index scan | Inspect index name/bounds and keys examined |
| `FETCH` | Fetching full documents | Needed when the index does not cover all required fields |
| `SORT` | In-plan sorting step | Check whether an index could satisfy the sort order instead |
| `GROUP` or `$group` | Grouping execution | Can appear in SBE or aggregation stage blocks |
| `EQ_LOOKUP` or `$lookup` | Joining data | Names and inner structure vary by plan/version |
| `nReturned` | Number of results from the reported execution unit | Clarify scope: cursor stage or entire pipeline |
| `totalKeysExamined` | Number of index keys inspected | Can be high even when few results are returned |
| `totalDocsExamined` | Number of documents inspected | Can be `0` for an eligible covered query |
| `executionTimeMillis` | Reported execution duration | Not directly equivalent to end-to-end API latency |

When inspecting a `$match → $group` pipeline, never assume `nReturned` inside **an inner `$cursor`** equals the final number of groups. The cursor might feed 8 orders into `$group`, while `$group` emits only 2 regional summary documents.

## 5. Reading `executionStats` metrics together

Example hypothetical query returning 10 results:

```text
Plan A:
  nReturned          = 10
  totalKeysExamined  = 12
  totalDocsExamined  = 10

Plan B:
  nReturned          = 10
  totalKeysExamined  = 250000
  totalDocsExamined  = 50000
```

Plan A touches far less data to return the same number of results. Still, you cannot declare Plan A faster in all conditions without also checking sorting, grouping, cache state, document size, and post-cursor work.

For an aggregating query:

```javascript
db.orders.explain("executionStats").aggregate([
  { $match: { status: "paid" } },
  { $group: { _id: "$region", revenue: { $sum: "$total" } } }
])
```

The sample dataset has 8 `paid` documents, while the final output has 2 groups: `north` and `south`. An input stage must examine 8 documents to compute total revenue; therefore, **having more documents examined than groups returned** does not by itself prove an inefficient pipeline.

### Interpreting examined vs. returned gaps

- **Highly selective `$match`:** few documents pass to later stages; a matching index reduces reads.
- **`$group` collapsing many rows:** returning far fewer groups than input documents is completely normal.
- **`$unwind` expanding rows:** row counts after unwinding can exceed input document counts.
- **`$lookup` or `$facet`:** performs additional work not visible solely from the outer cursor output count.
- **`$sort` and `$skip`:** may need to inspect many records before emitting just a few results.
- **Covered query:** can scan an index with `totalDocsExamined = 0`, though the rest of the pipeline may still be heavy.

Always inspect **stage names, per-step counts, and the nature of the work** before drawing conclusions.

## 6. First optimization step: filter early with `$match`

Suppose we need the newest paid orders in the north region:

```javascript
db.orders.aggregate([
  { $match: { status: "paid", region: "north" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 3 },
  { $project: { _id: 1, customerId: 1, total: 1 } }
])
```

On the sample data, `$match` cuts 12 orders down to 4; `$sort` orders those 4; `$limit: 3` returns IDs **111, 109, 104**.

### Two potentially equivalent ways of writing it

```javascript
// Approach A: filter before sort
[
  { $match: { status: "paid" } },
  { $sort: { createdAt: -1, _id: -1 } }
]

// Approach B: sort before an independent filter
[
  { $sort: { createdAt: -1, _id: -1 } },
  { $match: { status: "paid" } }
]
```

With no intervening `$limit`/`$skip` and a filter independent of newly computed fields, both sequences yield the same logical output, and the optimizer can **push `$match` ahead of `$sort`**. Even so, do not rely on that to write confusing pipelines: expressing early filtering makes intent clearer for engineers and operators.

### Not every `$match` can be pushed forward

For example, when `highValue` must be computed from `total` first:

```javascript
db.orders.aggregate([
  {
    $set: {
      highValue: { $gte: ["$total", 200] }
    }
  },
  { $match: { highValue: true } },
  { $project: { _id: 1, total: 1, highValue: 1 } }
])
```

`highValue` **does not yet exist** on source documents. Moving `$match: {highValue:true}` ahead of `$set` manually would produce empty or incorrect results.

If the expression simply wraps a condition on a source field, you can **rewrite it equivalently in terms of the source condition**:

```javascript
db.orders.aggregate([
  { $match: { total: { $gte: 200 } } },
  { $project: { _id: 1, total: 1 } }
])
```

On the sample data, filtering directly on `total >= 200` and computing the boolean expression both target orders of 200 or more; in production, also account for `null`, type mismatches, and complex expressions.

### The optimizer can split `$match` by dependency

```javascript
db.orders.aggregate([
  {
    $addFields: {
      isLarge: { $gte: ["$total", 200] }
    }
  },
  {
    $match: {
      status: "paid",
      isLarge: true
    }
  }
])
```

Because `status: "paid"` does not depend on `isLarge`, the optimizer can move that predicate earlier while keeping `isLarge: true` after `$addFields`. Explain output may show the filter **split or relocated**. One source stage does not always map one-to-one to one execution stage.

## 7. Leveraging indexes for `$match` and `$sort`

When a pipeline starts with filters and sorts on original document fields, an index can dramatically reduce work:

```javascript
db.orders.createIndex(
  { status: 1, region: 1, createdAt: -1, _id: -1 },
  { name: "idx_status_region_created_id" }
)
```

Run `explain`:

```javascript
db.orders.explain("executionStats").aggregate([
  { $match: { status: "paid", region: "north" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 3 },
  { $project: { _id: 1, customerId: 1, total: 1 } }
])
```

This index has two equality fields (`status`, `region`) followed by two sort-order fields. When the query planner chooses the index, MongoDB can seek to the key range and read directly in descending time order, avoiding an extra in-memory sort over many documents.

However, an index is only a **candidate**. Because the sample collection is tiny, the planner might still choose a collection scan. Always inspect `IXSCAN`/`COLLSCAN`, index name, bounds, `SORT`, `totalKeysExamined`, and `totalDocsExamined` from real explain output.

### Why `$project` does not automatically make a query covered

The projection:

```javascript
{ $project: { _id: 1, customerId: 1, total: 1 } }
```

needs `customerId` and `total`, whereas the index above only holds `status`, `region`, `createdAt`, and `_id`. The server may need a **FETCH** stage to retrieve the missing fields from source documents. When a query is fully served from an index, you may see `totalDocsExamined = 0` in the read phase; merely having `$project` does not guarantee that.

Trade off widening compound indexes for covered queries against storage and write overhead based on workload needs. Never stuff every field into an index just for a rarely run report.

### Field order in an index matters

```javascript
{ status: 1, region: 1, createdAt: -1, _id: -1 }
```

differs from:

```javascript
{ createdAt: -1, status: 1, region: 1, _id: -1 }
```

With equality predicates on `status` and `region`, the first order narrows the key range before reading in sort order. This illustrates the **Equality – Sort – Range (ESR)** guideline. Optimal order in practice still depends on range predicates, selectivity, existing indexes, and chosen plans.

## 8. `$sort` and `$limit`: top-K optimization without changing semantics

For "the three most recent paid orders," the right order is:

```javascript
db.orders.aggregate([
  { $match: { status: "paid" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 3 }
])
```

On the sample dataset, the resulting IDs are **111, 110, 109**.

In contrast:

```javascript
// DIFFERENT SEMANTICS: limiting before sorting
db.orders.aggregate([
  { $match: { status: "paid" } },
  { $limit: 3 },
  { $sort: { createdAt: -1, _id: -1 } }
])
```

`$limit: 3` picks the first three documents arriving in arbitrary input order (which is unguaranteed without `$sort`). The trailing sort merely reorders **those three selected documents**; it cannot find the three newest orders across the entire `paid` set.

### The optimizer can coalesce sort and limit

With:

```javascript
[
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 3 }
]
```

MongoDB can optimize this into a bounded **top-K sort**, holding only enough intermediate state to retain the top three results rather than sorting and buffering the entire dataset in the same way. This requires no intervening stage that alters document counts in a way that blocks coalescing.

An example on a large dataset:

```text
Source 2,000,000 documents
          |
          v
      $sort by key
          |
          v
       $limit 20

The optimizer can use a bounded top-20 sort
(when applicable), reducing intermediate sort state.
```

**However, top-K does not mean the server only reads 20 documents.** Without a sort-supporting index, the server may still have to scan most of the input set to determine which 20 documents belong at the top.

### Sorting with `$skip` and `$limit`

```javascript
db.orders.aggregate([
  { $match: { status: "paid" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $skip: 3 },
  { $limit: 3 }
])
```

MongoDB can optimize sort/skip/limit into a plan tracking **at least the first `skip + limit` elements** in sorted order and discarding `skip` of them (6 positions in this example). You cannot move `$limit: 3` before `$skip: 3` and keep the same result.

Deep offset pagination still carries a cost: `$skip: 100000` typically requires stepping past many items before returning a few rows. For very deep "load more" flows, consider keyset pagination based on the sort key instead of large offsets.

## 9. `$project`, `$set`, and `$unset`: trimming data while preserving dependencies

Shrinking document size early **can** help when downstream stages buffer lots of intermediate data, provided you keep fields required by later filters, sorts, groups, or joins.

Example computing total revenue by region:

```javascript
db.orders.aggregate([
  { $match: { status: "paid" } },
  { $project: { region: 1, total: 1, _id: 0 } },
  {
    $group: {
      _id: "$region",
      revenue: { $sum: "$total" }
    }
  }
])
```

The projection keeps only `region` and `total`, which suffices for the aggregation. The sample data yields two groups: `north = 690`, `south = 770`.

### Incorrect example from dropping a field too early

```javascript
db.orders.aggregate([
  { $project: { region: 1, total: 1, _id: 0 } },
  { $match: { status: "paid" } },
  { $group: { _id: "$region", revenue: { $sum: "$total" } } }
])
```

Under source-pipeline semantics, `status` is already stripped before `$match`. As a result, `status: "paid"` no longer sees the field and can drop every document; **do not expect the optimizer to fix a pipeline whose semantics are already wrong**.

### No need to manually project early in every pipeline

MongoDB performs **projection optimization** automatically, carrying only needed fields through relevant stages. Sprinkling `$project` stages at the top of every pipeline does not always speed things up; it can clutter code and introduce bugs later if someone adds a predicate relying on a stripped field.

Focus early projection on cases with clear payoff:

- A `$group` with `$push: "$$ROOT"` risking large buffered documents.
- A `$lookup` returning bulky foreign fields the report doesn't need.
- A pipeline passing large documents through multiple heavy stages.
- Stripping sensitive fields before returning API payloads.

`$project` reshapes the data stream; it does not shrink stored documents in the collection and does not guarantee index coverage.

### `$match` after projection can be pushed earlier

If a projection passes `status` through unchanged:

```javascript
[
  { $project: { status: 1, total: 1 } },
  { $match: { status: "paid" } }
]
```

the optimizer can push the `status` predicate ahead of the projection. If the projection **renames or recomputes** the filtered field, pushdown depends on expression relationships. Inspect `explain` to distinguish written stages from optimized execution steps.

## 10. `$group`: filter before grouping and group at the right granularity

`$group` collapses multiple documents into groups with accumulators. Example reporting paid revenue by region:

```javascript
db.orders.aggregate([
  { $match: { status: "paid" } },
  {
    $group: {
      _id: "$region",
      orderCount: { $sum: 1 },
      revenue: { $sum: "$total" }
    }
  },
  { $sort: { revenue: -1 } }
])
```

Result:

```javascript
{ _id: "south", orderCount: 4, revenue: 770 }
{ _id: "north", orderCount: 4, revenue: 690 }
```

**Key optimization:** if you only care about `paid` orders, put `$match` before `$group` to shrink the input and unlock an index on `status`.

### `$match` on grouped output must stay after `$group`

Requirement: return only regions whose total `paid` revenue exceeds 700:

```javascript
db.orders.aggregate([
  { $match: { status: "paid" } },
  {
    $group: {
      _id: "$region",
      revenue: { $sum: "$total" }
    }
  },
  { $match: { revenue: { $gt: 700 } } }
])
```

Only `south` (revenue 770) is returned. You cannot move `$match: {revenue:{$gt:700}}` ahead of `$group`, because `revenue` only exists **after summing all documents in each group**.

### Ordering of `$limit` and `$group` changes the question

```javascript
// Regional totals across ALL paid orders
[
  { $match: { status: "paid" } },
  { $group: { _id: "$region", revenue: { $sum: "$total" } } },
  { $sort: { revenue: -1 } },
  { $limit: 1 }
]
```

asks "which region has the highest revenue?"; this differs from:

```javascript
// Regional totals across ONLY the 3 newest paid orders
[
  { $match: { status: "paid" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 3 },
  { $group: { _id: "$region", revenue: { $sum: "$total" } } }
]
```

In the second pipeline, `$limit` **alters the input set** entering `$group`. That change is valid if you explicitly want to group only the three newest orders, but it is **not** an equivalent optimization for reporting totals over all orders.

### Group count and memory

Grouping by `region` maintains minimal state. Grouping by `customerId + timestamp + sku` can create enormous numbers of groups. Accumulators like `$push` can inflate per-group memory state dramatically. That is why choosing the proper granularity, filtering early, and avoiding needless arrays/fields matter.

MongoDB can report metrics such as `usedDisk`, `spills`, `spilledRecords`, `maxAccumulatorMemoryUsageBytes`, or similar memory counters **when provided by the version and stage**. Seeing spills is a cue to review group cardinality, inputs, and memory; permitting disk spill does not make the pipeline faster on its own.

## 11. `$unwind`: watch out for row multiplication before heavy stages

`$unwind` splits each array element into its own pipeline row. Given:

```javascript
{ _id: 101, items: [{sku:"A",qty:2},{sku:"B",qty:1}] }
```

after `$unwind: "$items"`, this single document contributes **two rows**. Downstream stages may therefore process more rows than there are source documents.

### Filter orders first, then unwind items

```javascript
db.orders.aggregate([
  { $match: { status: "paid" } },
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      units: { $sum: "$items.qty" }
    }
  },
  { $sort: { units: -1, _id: 1 } }
])
```

Here only `paid` orders are expanded into item rows. If `$unwind` came before `$match` without optimizer pushdown, it would also expand `pending` and `refunded` orders only to discard them later.

### Two `$match` placements do not always mean the same thing

```javascript
// 1. Match orders containing SKU A, then unwind ALL items of those orders
db.orders.aggregate([
  { $match: { "items.sku": "A" } },
  { $unwind: "$items" },
  { $project: { _id: 1, "items.sku": 1 } }
])
```

For order `101` containing both A and B, the result includes **both A and B** because the filter inspected the document **before** unwinding.

```javascript
// 2. Unwind first, then keep only item rows with SKU A
db.orders.aggregate([
  { $unwind: "$items" },
  { $match: { "items.sku": "A" } },
  { $project: { _id: 1, "items.sku": 1 } }
])
```

This time order `101` contributes **only the item row for A**. These two pipelines have different meanings; swapping stage positions blindly to "filter earlier" would change the output.

If your goal is strictly item rows for A while still narrowing initial collection reads, you can use **two filters**:

```javascript
db.orders.aggregate([
  { $match: { "items.sku": "A" } },
  { $unwind: "$items" },
  { $match: { "items.sku": "A" } }
])
```

The first filter eliminates orders without A; the second retains only the A elements. This can help when a multikey index supports the first filter and documents have large arrays, though you should always verify with `explain` rather than assuming it is always faster.

### Empty arrays and `preserveNullAndEmptyArrays`

By default, `$unwind: "$items"` emits no rows for empty arrays, `null` values, or missing fields. When specifying:

```javascript
{
  $unwind: {
    path: "$items",
    preserveNullAndEmptyArrays: true
  }
}
```

MongoDB keeps documents lacking elements to unwind according to those semantics. Changing this option alters row counts and group outputs; choose based on business requirements rather than simply trying to preserve total counts.

## 12. `$lookup`: reduce documents before joining

`$lookup` pulls related data from another collection. If a pipeline only needs customer details for the three newest `paid` orders, joining every order before limiting is rarely the best way to express it.

### List queries: limit before joining when requirements match

```javascript
db.orders.aggregate([
  { $match: { status: "paid" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 3 },
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  },
  {
    $project: {
      _id: 1,
      total: 1,
      createdAt: 1,
      customer: 1
    }
  }
])
```

Here only the three newest orders enter `$lookup`. `customers._id` already has a default unique index in standard collections, well suited for equality lookups by customer ID. With the sample data, the three orders are `111`, `110`, and `109`.

**Be careful to distinguish a different requirement:** "the three newest orders from **gold-tier customers**." If you filter `customer.tier: "gold"` only **after** `$limit: 3`, you could miss the fourth or fifth order that actually belongs to a gold customer. Whenever top-3 selection depends on fields from the foreign collection, the lookup/filter/limit order must match the real semantics.

Correct example for "the three newest `paid` orders by gold customers":

```javascript
db.orders.aggregate([
  { $match: { status: "paid" } },
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  },
  { $unwind: "$customer" },
  { $match: { "customer.tier": "gold" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 3 }
])
```

Results come from orders of `u1` and `u3`, giving IDs `108`, `106`, `104` (in descending `createdAt` order). Another strategy might start from the gold customers side or reshape the join depending on data characteristics.

### Explain for lookup

```javascript
db.orders.explain("executionStats").aggregate([
  { $match: { status: "paid" } },
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  }
])
```

In supporting versions and plan shapes, `$lookup` explain metrics may report `indexesUsed`, `totalDocsExamined`, `totalKeysExamined`, lookup counts, or stages such as `EQ_LOOKUP`. Exact JSON paths and field names **are not uniform across all versions**.

Do not look solely at indexes on `orders`: for joins, **indexes on the foreign `customers` collection matter just as much**. Joining onto an unindexed foreign field can force MongoDB to do dramatically more work.

### The optimizer can coalesce lookup, unwind, and match

A sequence like:

```javascript
[
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  },
  { $unwind: "$customer" },
  { $match: { "customer.tier": "gold" } }
]
```

can in eligible cases be combined by the optimizer to avoid building unnecessary intermediate arrays or to push predicates into lookup execution. Explain output may show fields like `unwinding`, an internal pipeline, or a different join representation. Do not assume a stage "disappeared" just because `$unwind` isn't printed separately in `explain`.

Still, **not every `$lookup` optimizes identically**, especially lookups using sub-pipelines, complex expressions, sharding, or differing schemas. Always check your actual query shape and server version.

## 13. `$facet`: apply shared filters before branching reports

`$facet` runs multiple sub-pipelines over the same input document set. For example, a dashboard needing both total revenue by region and order counts by status:

```javascript
db.orders.aggregate([
  {
    $match: {
      createdAt: {
        $gte: ISODate("2026-11-10T00:00:00Z")
      }
    }
  },
  {
    $facet: {
      byRegion: [
        {
          $group: {
            _id: "$region",
            orderCount: { $sum: 1 },
            total: { $sum: "$total" }
          }
        }
      ],
      byStatus: [
        {
          $group: {
            _id: "$status",
            orderCount: { $sum: 1 }
          }
        }
      ]
    }
  }
])
```

Placing the shared `$match` **before `$facet`** narrows the document stream fed into every sub-pipeline and gives MongoDB a chance to use an index on the initial filter.

Conversely, if `$facet` is the very first stage in the pipeline, it generally cannot use indexes on filters buried inside its branches. However, when stages before `$facet` (`$match`, `$sort`) already use an index, `$facet` receives that stream **without necessarily triggering an extra collection scan**.

### Never blindly pull a branch-specific filter outside

If `byStatus` must count all orders while `byRegion` only covers `paid` orders, putting `$match:{status:"paid"}` **before `$facet`** restricts both branches to `paid` orders, changing the business logic.

When branches require different filters, keep branch-specific predicates inside their respective sub-pipelines or design a two-tier structure instead of hoisting everything to the top.

`$facet` also carries strict memory and output-size limits; `allowDiskUse` does not bypass all of them. Heavy multi-branch facet pipelines should be measured and, where consistency and latency allow, split into separate queries.

## 14. Identifying heavy stages: blocking, memory, and disk spill

Certain stages must accumulate significant data before completing their output:

| Stage | Common cost | Optimization focus |
| --- | --- | --- |
| `$sort` | Ordering many documents; may consume large RAM | Matching index, early filter, top-K with `$limit` |
| `$group` | Holding state for many group keys/accumulators | Trim input documents and reduce group cardinality |
| `$setWindowFields` | Sorting/buffering windows per partition/order | Filter early when semantically valid; index `partitionBy`/`sortBy` where helpful |
| `$lookup` | Querying and combining a foreign collection | Filter inputs, index foreign key, control match fan-out |
| `$unwind` | One document can expand into many rows | Avoid unwinding earlier than necessary |
| `$facet` | Multiple sub-pipelines over shared input | Early shared filter; avoid bloated branches |

MongoDB versions enforce memory limits on certain stages and can spill intermediate state to disk when permitted. Depending on version, configuration, and stage type, explain/profiler output may expose indicators such as `usedDisk`, `spills`, `spilledDataStorageSize`, or equivalent counters.

When needed, you can run a pipeline with `allowDiskUse`:

```javascript
db.orders.aggregate(
  [
    { $match: { status: "paid" } },
    { $group: { _id: "$region", total: { $sum: "$total" } } },
    { $sort: { total: -1 } }
  ],
  { allowDiskUse: true }
)
```

**Permitting disk use is not an automatic speedup.** Spilling incurs I/O overhead and does not lift the BSON size limit per result document or stage-specific memory caps.

### Rules for `$setWindowFields`

If a pipeline computes a running total per customer:

```javascript
db.orders.aggregate([
  { $match: { status: "paid" } },
  {
    $setWindowFields: {
      partitionBy: "$customerId",
      sortBy: { createdAt: 1, _id: 1 },
      output: {
        runningTotal: {
          $sum: "$total",
          window: { documents: ["unbounded", "current"] }
        }
      }
    }
  }
])
```

filtering `$match:{status:"paid"}` **before** the window computes running totals strictly across paid orders; filtering **after** the window means pending/refunded orders contributed to the running totals before being dropped from output. Moving that filter **changes the numbers** even though both pipelines only emit paid orders at the end.

`$setWindowFields` is only available on supported MongoDB versions. If your environment runs an older version, use an appropriate reporting alternative rather than copying syntax without checking server compatibility.

## 15. Comparing pipelines before and after changes rigorously

When an aggregation feels slow, run controlled comparisons instead of tweaking multiple things at once.

**Baseline example for regional revenue:**

```javascript
const baseline = [
  { $match: { status: "paid" } },
  {
    $group: {
      _id: "$region",
      revenue: { $sum: "$total" }
    }
  },
  { $sort: { revenue: -1 } }
];

db.orders.explain("executionStats").aggregate(baseline);
```

**Filtered variant when only the `north` region is needed:**

```javascript
const filtered = [
  { $match: { status: "paid", region: "north" } },
  {
    $group: {
      _id: "$region",
      revenue: { $sum: "$total" }
    }
  }
];

db.orders.explain("executionStats").aggregate(filtered);
```

These two pipelines **do not return the same result set**: `baseline` returns both `north` and `south`, whereas `filtered` returns only `north`. They illustrate the value of early filtering **when requirements change or only `north` is actually needed**, not an apples-to-apples benchmark of two equivalent queries.

To compare **two ways of writing the same requirement**, keep filters, projections, sorts, and data identical; for instance:

```javascript
const versionA = [
  { $match: { status: "paid", region: "north" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 3 }
];

const versionB = [
  { $sort: { createdAt: -1, _id: -1 } },
  { $match: { status: "paid", region: "north" } },
  { $limit: 3 }
];

db.orders.explain("executionStats").aggregate(versionA);
db.orders.explain("executionStats").aggregate(versionB);
```

Because the filter in `B` precedes `$limit` and is independent of the sort, the optimizer can compile both versions into very similar plans. If timings differ, check cache state, indexes, planner choices, and test conditions before concluding that line order caused the gap.

### Metrics worth recording

| Metric / evidence | Why |
| --- | --- |
| Predicates and parameter values | Selectivity and data skew strongly affect plans |
| Sort, limit, skip, projection | Shape the query and total work required |
| Available indexes and `winningPlan` | Reveal the exact data-access path |
| `totalKeysExamined`, `totalDocsExamined` | Estimate key/document scan scope |
| `SORT`, `FETCH`, `GROUP`, `EQ_LOOKUP` stages | Spot major execution work |
| Row counts after key stages | Catch `$unwind` blow-ups or `$group` reductions |
| Memory/spill counters when reported | Spot oversized intermediate stage state |
| Multi-run timings | Avoid drawing conclusions from a single cached or noisy run |

Never point to a single `executionTimeMillis` reading to promise identical API speed. Real application latency also includes network hops, driver work, BSON decoding, service logic, and production resource contention.

## 16. `explain` is not a permanent snapshot of every request

MongoDB uses query planning and may maintain a **plan cache** for similar query shapes. Under explain behavior, running `explain` does not consume an existing plan cache entry like a normal query, nor does it insert a new plan cache entry.

Therefore, `winningPlan` reflects the plan chosen **during that explain call**; it does not prove every live application request uses that exact plan. When slowdowns happen only for specific parameter values or during peak load, combine `explain` with monitoring, profiler data, or slow-query logs according to your access policy and operational procedures.

### Using `hint()` while studying indexes

```javascript
db.orders.explain("executionStats").aggregate([
  { $match: { status: "paid", region: "north" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 3 }
], {
  hint: "idx_status_region_created_id"
})
```

If your `mongosh`/driver version supports `hint` on aggregation commands, it lets you inspect a plan using the named index explicitly. However, `hint` typically governs initial collection access and **does not force downstream stages to use indexes**; nor does it guarantee a faster pipeline.

Do not hardcode hints in production based solely on small experiments. If an index is dropped, schemas/workloads shift, or data skews, a forced hint can degrade performance or error out.

### Queries on sharded clusters

In sharded environments, `explain` can break down work per shard, router/merge phases, and distributed sort/group steps. Check:

- Is the query **targeted** to a single shard via the shard key, or does it scatter-gather?
- Which stages execute on shards vs. at the merge node?
- Are massive numbers of documents shipped between shards and the router?
- Is `$group` split into shard-local pre-aggregation plus a final merge?

Do not sum metrics blindly across shard branches and treat them identically to a standalone explain. Structure and metric scope depend on version and pipeline shape.

## 17. Java MongoDB Sync Driver: running explain for aggregation

You can invoke the `explain` database command from Java to receive the JSON/BSON pipeline plan:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

import java.util.List;

public class AggregationExplainDemo {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Missing MONGODB_URI");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database =
                client.getDatabase("mongo_aggregation_explain_lab");

            List<Document> pipeline = List.of(
                new Document("$match",
                    new Document("status", "paid")
                        .append("region", "north")),
                new Document("$sort",
                    new Document("createdAt", -1)
                        .append("_id", -1)),
                new Document("$limit", 3),
                new Document("$project",
                    new Document("_id", 1)
                        .append("customerId", 1)
                        .append("total", 1))
            );

            Document aggregateCommand =
                new Document("aggregate", "orders")
                    .append("pipeline", pipeline)
                    .append("cursor", new Document());

            Document explainCommand =
                new Document("explain", aggregateCommand)
                    .append("verbosity", "executionStats");

            Document explanation =
                database.runCommand(explainCommand);

            System.out.println(explanation.toJson());

            // Do not assume every explain always has a top-level
            // executionStats: aggregation may place details inside
            // stages[].$cursor or another SBE structure.
            Document stats =
                explanation.get("executionStats", Document.class);
            if (stats != null) {
                System.out.println(
                    "keysExamined = " + stats.get("totalKeysExamined"));
                System.out.println(
                    "docsExamined = " + stats.get("totalDocsExamined"));
            }
        }
    }
}
```

This snippet requires the MongoDB Java Sync Driver and a Java version with `List.of`. The connection string is read from the `MONGODB_URI` environment variable to keep credentials out of source code.

In driver versions that expose an `explain` method directly on `AggregateIterable`, you can also use that API along with `ExplainVerbosity`. Here we use `runCommand` to make the `aggregate`, `pipeline`, `cursor`, and `verbosity` fields explicit—not because every environment requires raw database commands.

### Parsing explain output in Java requires handling multiple shapes

A robust diagnostic tool must handle these variations:

- Top-level `queryPlanner`/`executionStats`.
- A `stages` array containing `$cursor` and subsequent aggregation stages.
- Classic plan trees or SBE `queryPlan`/`slotBasedPlan`.
- Per-shard sections in sharded deployments.
- Version-specific field names and stage counters.

Never inspect one sample explain JSON captured on a laptop and treat it as an immutable schema across all servers.

## 18. Practice exercises with answers

### Exercise 1. Explain the right pipeline

Requirement: inspect execution stats for the newest `paid` orders in `north`, up to three orders.

**Answer:**

```javascript
db.orders.explain("executionStats").aggregate([
  { $match: { status: "paid", region: "north" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 3 }
])
```

When the pipeline runs normally, the logical result IDs are `111`, `109`, `104`. The `explain` command outputs **the plan and execution statistics**, not that array of three order documents.

### Exercise 2. Spot the invalid reordering

Compare:

```javascript
// A
[
  { $match: { status: "paid" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 3 }
]

// B
[
  { $match: { status: "paid" } },
  { $limit: 3 },
  { $sort: { createdAt: -1, _id: -1 } }
]
```

**Answer:** Pipeline `A` picks the three newest paid orders across the entire matching set. Pipeline `B` takes the first three paid orders arriving in input order and sorts only those three; they are not guaranteed to be the newest overall. Reordering them this way is invalid when results must stay unchanged.

### Exercise 3. Counting rows accurately after unwind

Order `101` has two elements in `items`: A and B. Why can `$unwind` followed by `$group` with `$sum: 1` count 2 when the collection only has one order `101`?

**Answer:** After `$unwind`, order `101` becomes two pipeline rows. `$sum: 1` counts **input rows entering `$group`**, not unique order documents. If you need distinct orders per SKU, collect order IDs with `$addToSet` or structure a distinct-counting step accordingly.

### Exercise 4. Can `$match` move ahead of `$group`?

```javascript
[
  { $match: { status: "paid" } },
  { $group: { _id: "$region", revenue: { $sum: "$total" } } },
  { $match: { revenue: { $gt: 700 } } }
]
```

**Answer:** You cannot push `$match` on `revenue` ahead of `$group` while preserving semantics, because `revenue` is only computed after summing all documents in each group. Filtering `status` before `$group` works because `status` exists on the source documents.

### Exercise 5. Explain shows `COLLSCAN`—is the index broken?

On the 12-order sample collection, even after creating an index on `status, region, createdAt, _id`, `explain` still shows `COLLSCAN`. Can you conclude the index is useless in production?

**Answer:** No. Tiny collections make collection scans practically free. Evaluate query shape, data distribution, `winningPlan`, examined counts, sorting, and workload at realistic scale before judging. Having an eligible index does not force the planner to choose it in every scenario.

### Exercise 6. Optimizing a join without altering output

Requirement A: get the three newest `paid` orders and display their customer details. Requirement B: get the three newest `paid` orders **from gold-tier customers**.

**Answer:** For A, `$match → $sort → $limit → $lookup` works because top-3 selection does not depend on customer attributes. For B, tier must be checked before choosing the top 3: `$match paid → $lookup → $unwind → $match customer.tier → $sort → $limit` (or an equivalent design filtering gold customers first). Putting `$limit` before filtering for gold customers can miss qualifying orders.

### Exercise 7. Which stage needs a memory check?

A pipeline grouping by `customerId` with `$push: "$$ROOT"` across millions of documents shows spill indicators and high RAM consumption.

**Answer:** `$group` maintains group states and value arrays, which can grow huge. Drop `$push: "$$ROOT"` if unneeded, project fewer fields, filter earlier, reduce group granularity, or redesign the report. `allowDiskUse` allows certain operations to spill, but it does not eliminate I/O overhead or the BSON result document size limit.

### Exercise 8. Why doesn't `explain` have `stages` as expected?

Explaining a simple aggregation pipeline on Server A returns `stages:[{$cursor:...},{$group:...}]`, whereas Server B shows top-level `queryPlanner.winningPlan.queryPlan`.

**Answer:** Explain formatting varies by server version, query-engine pushdown eligibility, and classic vs. SBE execution. Never conclude data is missing just because JSON paths differ. Read planner and execution statistics wherever the server reports them.

## 19. Practical workflow for optimizing aggregation

To optimize systematically while keeping output accurate, follow this sequence:

1. **Define expected output:** what does each output row represent, do filters apply before or after grouping/windowing, does `$limit` cap documents or groups, and should empty arrays be dropped or preserved?
2. **Capture the full pipeline and query shape:** keep every real stage, option, and filter predicate. Avoid tuning a stripped-down toy query that does not represent the endpoint.
3. **Run `queryPlanner` to inspect the read path:** index names, bounds, `COLLSCAN`, `IXSCAN`, `FETCH`, `SORT`, and `$cursor`.
4. **Run `executionStats`:** examine keys/docs examined, per-stage row counts when available, timings, and memory/spill signs to locate where data is heavily read, multiplied, grouped, or sorted.
5. **Check stage dependencies:** hoist independent `$match` predicates early, keep predicates on computed fields after their defining stages, and never move `$limit` across `$group`, `$unwind`, or `$lookup` carelessly.
6. **Design indexes for leading `$match`/`$sort` prefixes:** order keys around equality, sort, and range; do not expect an index to solve every downstream `$group` or `$lookup` automatically.
7. **Limit fan-out and intermediate state:** avoid unwinding or joining unnecessary data; do not push `$project` so early that required fields vanish; avoid `$push` on bulky objects unless truly needed.
8. **Compare under controlled conditions:** verify equivalent output whenever semantics must stay fixed, then benchmark on representative data across realistic parameter values, cache warmth, and load.
9. **Monitor after deployment:** watch application latency, CPU, I/O, cache pressure, index footprint, write throughput, and other queries; every new index carries maintenance cost.

## 20. Conclusion

`explain` lets you inspect both **the collection access plan and aggregation execution**. When reading it, do not stop at `IXSCAN` or a single timing number; trace data flow across `$match`, `$cursor`, `$sort`, `$group`, `$unwind`, and `$lookup` all the way to the output, keeping in mind that the optimizer may reshape stages.

Good stage ordering aims to **eliminate unneeded data as early as semantically valid**, **align order with indexes**, **shrink row counts before expensive stages**, and **avoid holding massive intermediate state**. Yet correctness always comes before speed: post-group filters cannot move ahead of `$group` when they depend on aggregated totals; `$limit` before `$sort` is not top-K; filtering before vs. after `$unwind` selects whole documents vs. individual array elements; and `$limit` before `$lookup` can drop records matching foreign predicates. By combining accurate `explain` analysis with strict respect for pipeline semantics, MongoDB optimization becomes evidence-based engineering rather than guesswork.
