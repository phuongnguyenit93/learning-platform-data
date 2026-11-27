# Comparing `nReturned`, `totalKeysExamined`, and `totalDocsExamined` in MongoDB Execution Plans

## 1. Reading `explain()` Is Not Just About Seeing Whether MongoDB Uses an Index

A query can use an index and still be slow. Conversely, a query that scans the collection is sometimes sensible if the collection is tiny or most of the data must be returned. Therefore, when evaluating a MongoDB **execution plan**, do not stop at the conclusion "`IXSCAN` is good, `COLLSCAN` is bad."

Three highly informative metrics in `explain("executionStats")` are:

- **`nReturned`:** the number of result documents returned within the scope being examined.
- **`totalKeysExamined`:** the total number of **index keys** examined during execution.
- **`totalDocsExamined`:** the total number of **documents** examined during execution.

They help answer three distinct questions:

1. **How many results** did the query actually return?
2. **How many index keys** did MongoDB have to examine to reach those results?
3. **How many documents** did MongoDB have to read/examine to determine those results?

Intuitive example:

```text
Application asks: "Fetch the 20 newest paid orders"

Scenario A:
    nReturned          = 20
    totalKeysExamined  = 20
    totalDocsExamined  = 20

Scenario B:
    nReturned          = 20
    totalKeysExamined  = 40,000
    totalDocsExamined  = 40,000

Scenario C:
    nReturned          = 20
    totalKeysExamined  = 0
    totalDocsExamined  = 100,000
```

Given the same query, dataset, and result semantics, A clearly needs to examine far fewer keys/documents. B may point to a poorly suited index or an expensive post-fetch filtering step; C suggests a collection scan. However, **these three sets of numbers are merely illustrative examples**, not measured results, and they do not let you immediately assert latency without knowing cache state, sorting, data size, limits, and system load.

The goal of this lesson is to learn how to **read, compare, interpret, and formulate improvement hypotheses**, rather than mechanically applying a "good/bad ratio" threshold to every query.

## 2. Setting Up the Environment and Test Dataset

Commands use **mongosh** syntax. Run them in a test database; never execute index-creation or sample-insert commands directly on a production collection. The examples use a separate `explainOrdersDemo` collection; on the first run, the collection should not yet contain the corresponding `_id` values.

```javascript
const docs = [];

for (let i = 0; i < 2000; i++) {
  const group = Math.floor(i / 5);

  docs.push({
    _id: i,
    tenantId: "T" + (i % 5),
    status: group % 4 === 0 ? "PAID" : "PENDING",
    createdAt: new Date(Date.UTC(2026, 9, 1, 0, i)),
    amount: i % 400,
    tags: i % 3 === 0 ? ["vip", "promotion"] : ["regular"]
  });
}

db.explainOrdersDemo.insertMany(docs);
```

Dataset characteristics:

- There are 2,000 documents, each with a distinct `_id`.
- There are five tenants, `T0` through `T4`.
- Both `PAID` and `PENDING` statuses are present.
- `createdAt` increments by the minute to establish a clear chronological order.
- `tags` is an array so multikey indexes can also be observed.

Numeric values in the illustrative `explain` snippets below may **differ from actual numbers when run**, because the planner depends on MongoDB version, data, existing indexes, execution engine, and environment conditions.

Primary query for this lesson:

```javascript
db.explainOrdersDemo
  .find({
    tenantId: "T2",
    status: "PAID"
  })
  .sort({ createdAt: -1 })
  .limit(10);
```

Business requirement: **fetch the 10 most recent paid orders for tenant T2**. This is a great example for observing the interaction between filter predicates, index order, and `limit`.

## 3. Calling `explain("executionStats")`

### 3.1. Common Syntax

```javascript
db.explainOrdersDemo
  .find({
    tenantId: "T2",
    status: "PAID"
  })
  .sort({ createdAt: -1 })
  .limit(10)
  .explain("executionStats");
```

The output can contain these key sections:

```javascript
{
  queryPlanner: {
    // Normalized query information and the selected plan.
    winningPlan: { /* stages or equivalent representation */ }
  },
  executionStats: {
    nReturned: 10,
    executionTimeMillis: 1,
    totalKeysExamined: 10,
    totalDocsExamined: 10,
    executionStages: { /* per-stage statistics */ }
  }
}
```

**This is a structural example** for identifying fields; the illustrative numbers are not guaranteed results from the dataset in section 2. Depending on the version, `winningPlan` may contain `queryPlan`, `slotBasedPlan`, or another stage structure. Read **the semantics of the metrics** rather than depending on a single JSON tree layout.

### 3.2. Three `explain` Modes

| Mode | Purpose | What to Know |
|---|---|---|
| `"queryPlanner"` | Inspect plans and the winning plan chosen by the planner | Primarily planning information, not full execution stats |
| `"executionStats"` | Execute to gather statistics on the selected plan | Provides `nReturned`, `totalKeysExamined`, `totalDocsExamined`, and many other stats |
| `"allPlansExecution"` | Also view statistics for candidate plans evaluated during plan selection, when provided | Do not add candidate plan numbers onto the winning plan's numbers |

```javascript
db.explainOrdersDemo.explain("queryPlanner")
  .find({ tenantId: "T2" });

db.explainOrdersDemo.explain("executionStats")
  .find({ tenantId: "T2" });

db.explainOrdersDemo.explain("allPlansExecution")
  .find({ tenantId: "T2" });
```

`explain` is meant for understanding a plan in a given context. It is not identical to measuring real application execution time:

- `explain` may not replicate plan cache usage the way a normal query does.
- It does not measure total connection pool wait time or all data transfers to the client.
- A real query may process multiple cursor batches, whereas explain observes execution with its own statistics scope.
- Warm/cold cache, CPU/I/O load, and concurrent writes can alter timings.

When diagnosing production issues, combine `explain` with the profiler, logs, MongoDB metrics, and application-side latency measurements.

## 4. `nReturned`: Number of Results, Not Documents Read

### 4.1. Meaning

In the overall execution statistics of a `find` command, `nReturned` typically represents **the number of documents returned by the query** during the explained execution.

```javascript
db.explainOrdersDemo.find({
  tenantId: "T2",
  status: "PAID"
}).limit(10).explain("executionStats");
```

In this example, `nReturned` is no larger than 10 because the query specifies `limit(10)`. However, you cannot deduce that MongoDB only had to examine 10 keys or 10 documents to find them.

### 4.2. Note on `limit`

Suppose the filter has very low selectivity. MongoDB might have to read hundreds of documents before finding 10 matches:

```text
nReturned         = 10
totalDocsExamined = 500
```

A 500/10 ratio suggests many documents were examined before returning 10 results. Furthermore, if there is a `sort` unsupported by an index, the server may have to examine a huge number of matching documents to determine the **10 largest/smallest values** before returning the first batch.

Conversely, with an index matching both filter and sort order, the server can fetch 10 matching documents from an adjacent key range and stop early.

### 4.3. Note on `skip`

```javascript
db.explainOrdersDemo.find({ tenantId: "T2" })
  .sort({ createdAt: -1 })
  .skip(100)
  .limit(10)
  .explain("executionStats");
```

Here `nReturned` is at most 10, yet to reach the requested page, the server may have to walk through all the results discarded by `skip`. Never use `nReturned = 10` to conclude that read cost was only 10.

### 4.4. Note on Aggregation

```javascript
db.explainOrdersDemo.explain("executionStats").aggregate([
  { $match: { status: "PAID" } },
  { $group: { _id: "$tenantId", count: { $sum: 1 } } }
]);
```

If the pipeline groups into five tenants, the **output** document count is just five, even though earlier stages may have examined hundreds of source documents. With an `$unwind` pipeline, a single source document can even generate **many intermediate documents**.

Therefore, when analyzing aggregation, distinguish:

- `nReturned` at the **final output** or at a given stage.
- The number of documents passed through **intermediate stages**.
- `totalDocsExamined` / `totalKeysExamined` for **storage access**.

Never use the `totalDocsExamined / nReturned` ratio of a `$group` pipeline to immediately claim an index is bad: turning **many source documents into a few output groups** may be the exact business requirement.

## 5. `totalKeysExamined`: Number of Index Keys Examined

### 5.1. Index Scans Navigate from Keys to Documents

Suppose you created:

```javascript
db.explainOrdersDemo.createIndex({ tenantId: 1 });
```

When filtering `tenantId: "T2"`, MongoDB can use the index to locate the corresponding key entries. `totalKeysExamined` counts **the number of index keys examined during execution**, not the number of existing indexes and not the number of keys created when building the index.

```javascript
db.explainOrdersDemo.find({
  tenantId: "T2"
}).explain("executionStats");
```

Each document usually has one key in this scalar index, so in simple queries the number of keys examined may be close to the candidate document count. However, do not treat this as a universal rule, because:

- Compound indexes bound keys across multiple fields.
- Multikey indexes can have **multiple keys for the same document**.
- A query can scan a key range and then evaluate additional predicates.
- Some plans use multiple indexes or different index stages.
- Execution steps, bound ranges, and deduplication needs can make key counts differ from document counts.

### 5.2. `totalKeysExamined = 0` Does Not Automatically Mean a Fast Query

If the planner selects `COLLSCAN`, the query does not traverse index keys:

```text
totalKeysExamined = 0
totalDocsExamined = 100,000
nReturned         = 10
```

A `0` in `totalKeysExamined` **does not mean "no work done."** It can indicate MongoDB is scanning documents directly.

If a collection has 20 documents and the query needs to return all 20, `COLLSCAN` can be reasonable. If the collection has 100 million documents and only 10 results are needed, revisit the filter and indexes.

### 5.3. A High `totalKeysExamined` Is Not Automatically a Bug

For instance, a query analyzes all key values across a wide range or needs to count matching elements. Scanning tens of thousands of keys may simply be the natural cost of the requirement.

A **covered** query might look like:

```text
nReturned         = 5,000
totalKeysExamined = 5,000
totalDocsExamined = 0
```

Although it scans many keys, it avoids reading source documents. Consider **the query goal, result count, and stage-level work** before judging.

## 6. `totalDocsExamined`: Documents Examined, Not the Whole Collection

### 6.1. Meaning

`totalDocsExamined` records how many times the engine had to examine a document while executing the query. In plans with `FETCH`, this number typically reflects fetching documents to check conditions or build results. With `COLLSCAN`, it reflects scanned documents.

A common point of confusion:

> **`totalDocsExamined` does not necessarily equal the number of distinct documents read.** In complex plans, a single document may be examined multiple times; the statistic reflects examination counts as executed by the engine.

Example:

```text
nReturned         = 30
totalKeysExamined = 2,000
totalDocsExamined = 1,500
```

One reasonable interpretation is that the server found candidates via an index and still had to fetch/inspect many documents to produce the final 30 results. However, from these three numbers alone **you cannot pinpoint** which exact condition filtered them out, because you also need to inspect the stages and `indexBounds`.

### 6.2. `totalDocsExamined = 0` Can Be a Very Strong Signal

If a query is satisfied entirely by an index, the execution engine can return results without reading source documents. This is a **covered query**.

```javascript
db.explainOrdersDemo.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});

db.explainOrdersDemo.find(
  { tenantId: "T2", status: "PAID" },
  {
    _id: 0,
    tenantId: 1,
    status: 1,
    createdAt: 1
  }
)
.sort({ createdAt: -1 })
.limit(10)
.explain("executionStats");
```

All filtered, sorted, and returned fields are in the index; the projection also **excludes `_id`**, because `_id` is not part of the compound index above. When the planner uses the index to satisfy every requirement, `totalDocsExamined` can be 0.

Not every query with `IXSCAN` is a covered query. If the projection also requests `amount`, the server may need to `FETCH` documents even though the index found the right entries:

```javascript
db.explainOrdersDemo.find(
  { tenantId: "T2", status: "PAID" },
  { _id: 0, createdAt: 1, amount: 1 }
).sort({ createdAt: -1 }).limit(10);
```

Here `amount` is not in the sample index, so fetching source documents is normal.

### 6.3. `totalDocsExamined` Equal to `nReturned` Still Does Not Guarantee Full Optimization

```text
nReturned         = 10
totalKeysExamined = 30,000
totalDocsExamined = 10
```

The query may have scanned a massive number of **index keys** yet only fetched 10 documents. The docs-examined-to-returned ratio looks great, yet the high key count reveals substantial search work. That is why **all three metrics must be read together**.

## 7. Comparing the Three Numbers with a Scenario Table

The following values are **hypothetical figures** for sample queries, not measured output from the 2,000-document dataset. Use them to practice interpretation:

| Scenario | `nReturned` | `totalKeysExamined` | `totalDocsExamined` | Initial Reading |
|---|---:|---:|---:|---|
| A. Well-matched index, returns docs | 20 | 20 | 20 | Few keys and few documents examined |
| B. Index used, but heavy post-filtering | 20 | 25,000 | 25,000 | Review key order, filter, and `FETCH` stage |
| C. Collection scan | 20 | 0 | 100,000 | No index keys used; scans many documents |
| D. Covered query | 20 | 20 | 0 | Can be satisfied entirely from the index |
| E. Many keys scanned, few fetched | 20 | 25,000 | 20 | Index scan cost may still be high |
| F. Deep `skip` | 20 | 10,020 | 10,020 | Returns 20, yet may walk through many skipped results |
| G. Multikey lookup | 40 | 700 | 90 | Multiple keys may reference the same document; check plan |
| H. Returning most of a small collection | 200 | 0 | 200 | `COLLSCAN` may be a sensible choice |

**Never use a single row in this table to declare a query "fast" or "slow."** For a meaningful comparison, confirm the queries perform **the same function**, produce equivalent results, run over the same data distribution, and share the same limits/sorts.

### 7.1. A Handy Pair of Diagnostic Ratios

For standard `find` queries, you can compute:

\[
\text{Keys per returned doc}=
\frac{\text{totalKeysExamined}}{\text{nReturned}}
\]

\[
\text{Docs per returned doc}=
\frac{\text{totalDocsExamined}}{\text{nReturned}}
\]

Example from Scenario B:

```text
Keys per returned doc = 25,000 / 20 = 1,250
Docs per returned doc = 25,000 / 20 = 1,250
```

In other words, on average **1,250 keys and 1,250 documents were examined for each returned document**. That is a signal to investigate index selectivity.

**Never compute ratios by direct division when `nReturned = 0`.** A query returning zero results can still scan many keys/documents; in that case report the absolute examination counts, inspect `indexBounds`, and investigate why nothing matched.

### 7.2. Ratios Are Meaningful Only When You Know Query Semantics

- `limit(10)` keeps the denominator small, even when the command intentionally inspects many candidates for sorting.
- `skip(100000)` drives keys/docs examined up even though the query returns 10 documents.
- `$group` can collapse millions of documents into a few groups; a high input/output ratio is natural.
- `$unwind` can make output document counts larger than source document counts.
- Multikey indexes have multiple keys per document, so `keys/docs` does not reflect unique source documents.
- Export queries returning thousands of documents may have ratios near 1 while total work remains large.

Thus, ratios are a **hypothesis-generation tool**, not a universal quality benchmark.

## 8. Queries Without an Index: Identifying `COLLSCAN`

Suppose no suitable index exists yet for the condition:

```javascript
db.explainOrdersDemo.find({
  amount: { $gt: 390 }
}).explain("executionStats");
```

If the query planner uses a collection scan, you may see:

```text
winningPlan
  COLLSCAN

totalKeysExamined = 0
totalDocsExamined = number of documents that had to be scanned
nReturned         = number of documents with amount > 390
```

**`totalDocsExamined` is not always equal to the collection's total document count.** A `limit` might let the query stop early, or another execution detail might alter the scanned range.

A candidate index:

```javascript
db.explainOrdersDemo.createIndex({ amount: 1 });
```

Then re-run `explain("executionStats")` to see whether the planner selects the index. Because the dataset only has 2,000 documents with an artificial distribution, the planner **might still pick `COLLSCAN`** if it deems it appropriate.

Do not force `hint` in production just to make `COLLSCAN` disappear from explain. Measure **total work** and latency on the real workload.

## 9. `IXSCAN` Present, Yet Many Documents Still Read: Inspect `FETCH`

### 9.1. Filter Conditions Not Fully Covered by the Index

Suppose there is only an index on `status`:

```javascript
db.explainOrdersDemo.createIndex({ status: 1 });
```

Yet the query also filters on `tenantId`:

```javascript
db.explainOrdersDemo.find({
  status: "PAID",
  tenantId: "T2"
}).explain("executionStats");
```

The `{ status: 1 }` index helps locate `PAID` documents, but it does not store `tenantId`. The server may then:

1. `IXSCAN` to find `status = "PAID"` keys.
2. `FETCH` the corresponding documents.
3. Check `tenantId = "T2"` on each fetched document.
4. Return only documents satisfying both conditions.

Examined keys and documents can be significantly larger than `nReturned`.

### 9.2. Compound Indexes Narrow the Search from Both Sides

```javascript
db.explainOrdersDemo.createIndex({
  tenantId: 1,
  status: 1
});
```

For the same query, the compound index can establish `indexBounds` for both equality predicates. The query can traverse fewer keys and fewer documents.

If you want both to filter by tenant/status and fetch the newest orders:

```javascript
db.explainOrdersDemo.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
```

The new index can also satisfy `sort({ createdAt: -1 })` after the two equality predicates. This is especially helpful when the query has a small `limit`, because the server can read the top documents in index order without sorting the entire candidate set.

### 9.3. Never Guess from a Single Metric

After adding the compound index, you might observe:

```text
Before:
nReturned         = 10
totalKeysExamined = 500
totalDocsExamined = 500

After:
nReturned         = 10
totalKeysExamined = 10
totalDocsExamined = 10
```

This is a **hypothetical outcome** illustrating reduced examination work. To conclude an index is truly beneficial overall, you must also factor in write overhead, index size, other queries, and real latency.

## 10. Few Documents Read, Many Keys Examined: Multikey and Broad Bounds

MongoDB uses a **multikey index** when an indexed field contains an array. One document can contribute multiple index keys:

```javascript
{
  _id: 1,
  tags: ["mongodb", "index", "backend"]
}
```

```javascript
db.explainOrdersDemo.createIndex({ tags: 1 });

db.explainOrdersDemo.find({
  tags: { $in: ["vip", "promotion"] }
}).explain("executionStats");
```

In the test dataset, some documents carry **both tags** `"vip"` and `"promotion"`. The query may examine multiple keys pointing to the same document and then deduplicate the resulting documents.

Hence, you may encounter:

```text
totalKeysExamined  > totalDocsExamined
totalDocsExamined >= nReturned  (in many find queries with FETCH)
```

This is **one possible pattern**, not an invariant inequality:

- Covered queries can have `totalDocsExamined = 0`.
- `COLLSCAN` has `totalKeysExamined = 0`.
- Complex stages have different counting rules and intermediate counts.

When `keysExamined` is high, inspect `isMultiKey`, `multiKeyPaths`, `indexBounds`, and deduplication stages (`dupsTested`, `dupsDropped` if reported). A high key count alone does not prove an index is broken.

### 10.1. Loose Bounds

If an index only bounds a broad condition and then filters on another field, key counts can also be high even without arrays:

```javascript
// Index only on createdAt, while query needs tenant and status filters.
db.explainOrdersDemo.createIndex({ createdAt: -1 });

db.explainOrdersDemo.find({
  tenantId: "T2",
  status: "PAID"
}).sort({ createdAt: -1 }).limit(10)
  .explain("executionStats");
```

The server may walk many documents chronologically to find 10 orders matching the tenant and status, depending on the chosen plan. The index supports the sort order, yet **does not necessarily support the filter well**. An appropriate compound index can balance both requirements.

## 11. Covered Query: `docsExamined = 0` Does Not Mean Zero Data

An illustrative covered query:

```javascript
db.explainOrdersDemo.find(
  {
    tenantId: "T2",
    status: "PAID"
  },
  {
    _id: 0,
    tenantId: 1,
    status: 1,
    createdAt: 1
  }
).sort({ createdAt: -1 })
 .limit(10)
 .explain("executionStats");
```

With the compound index `{ tenantId: 1, status: 1, createdAt: -1 }`, MongoDB can return the needed values from the index:

```text
nReturned         = 10
totalKeysExamined = 10
totalDocsExamined = 0
```

This is a **hypothetical ideal result**. The number of documents returned is still 10: `totalDocsExamined = 0` simply means the engine did not need to read **source documents** for that specific query, not that it found no data.

### 11.1. Why Does Projection Matter?

```javascript
// Can be covered (if a matching index exists).
{ _id: 0, tenantId: 1, status: 1, createdAt: 1 }

// Usually needs to read documents because amount is not in the index.
{ _id: 0, tenantId: 1, status: 1, createdAt: 1, amount: 1 }
```

If you do not exclude `_id` from the projection, MongoDB returns `_id` by default; in the example where the compound index does not include `_id` as a key field, that prevents a covered query.

Do not create overly wide indexes just to cover every projection: large indexes increase write overhead, storage size, and cache pressure.

### 11.2. Reading the Plan to Confirm

An index-only plan may omit `FETCH` and yield `totalDocsExamined = 0`. However, stage representation varies by version; newer engines may display plans differently. It is best to inspect **all together**:

- Which index was chosen?
- Are all fields needed for filtering, sorting, and projection inside the index?
- Is `totalDocsExamined` equal to 0?
- Is there any stage or operation retrieving source documents?

## 12. Low `nReturned`: Due to `limit` or Selective Filtering?

Two queries can both return 10 documents yet mean very different things:

```javascript
// Return at most 10 out of very many PAID documents.
db.explainOrdersDemo.find({
  status: "PAID"
}).limit(10);

// Look up one specific _id value; returns 0 or 1.
db.explainOrdersDemo.find({
  _id: 123
});
```

### 12.1. Queries with a Small `limit`

With `limit(10)`, `nReturned = 10` does not tell you how many documents in the collection match the filter. If a query asks for the first page of a 100,000-item list, an index supporting both sort and limit can be critical.

### 12.2. Queries with Highly Selective Filters

With `{ _id: 123 }`, the unique `_id` index usually lets MongoDB touch very few keys/documents. Here `nReturned = 1` reflects a highly selective predicate, not a limit cap of 1.

### 12.3. Queries Returning Zero Results

```javascript
db.explainOrdersDemo.find({
  tenantId: "NOT-EXISTING"
}).explain("executionStats");
```

The output might be:

```text
nReturned = 0
```

However:

- With a suitable index, the server can determine there are no keys in that range very quickly.
- Without an index, the server may scan the entire collection and still return 0.

Therefore, **`nReturned = 0` does not mean work = 0**. In this situation, check `totalKeysExamined`, `totalDocsExamined`, and the plan directly; never divide by `nReturned` to build a ratio.

## 13. Reading Stage-Level Statistics Instead of Only Totals

`executionStats` typically contains a statistics tree under `executionStages` or an equivalent representation. Common stages include:

| Stage or Component | Primary Role | Reading Tip |
|---|---|---|
| `COLLSCAN` | Scans documents in the collection | Can push `totalDocsExamined` high with zero index keys |
| `IXSCAN` | Scans index keys | Relates to `keysExamined` and `indexBounds` |
| `FETCH` | Fetches documents after finding candidate keys | May hold residual filters and increase `totalDocsExamined` |
| `SORT` | Sorts when existing order cannot be relied upon | Check for blocking sorts, memory limits, or limit optimizations |
| `LIMIT` | Caps the number of documents forwarded | Explains why `nReturned` is small |
| `SKIP` | Skips initial results in order | Can cause substantial work before returning a page |
| `COUNT_SCAN` or counting stage | Counts results under an eligible plan | Output count does not necessarily reflect keys inspected |
| `OR` / multi-branch stages | Merges scan paths from multiple conditions | Can introduce duplicates or require result merging |

**Never sum every `nReturned` across stages** to get total returned documents. Each stage receives and emits data within its own scope:

```text
 IXSCAN
  keysExamined = 10,000
      |
      v
 FETCH (residual filter)
  nReturned = 150
      |
      v
 SORT
      |
      v
 LIMIT
  nReturned = 20
```

This diagram is a **logical flow illustration**. In real plans, stage ordering, pushing `LIMIT` into `SORT`, and stage names may differ. `nReturned` on `IXSCAN`, `FETCH`, and `LIMIT` represents results **at each step**, not three independent sets of documents.

### 13.1. Reading Filters on `FETCH`

If `FETCH` carries a filter on `tenantId` while the index only covers `status`, that signals the server had to fetch documents to check `tenantId`. A compound index covering both fields can reduce fetch volume.

### 13.2. Reading `indexBounds`

Just because a compound index is used does not mean **every field in the index is tightly bounded**. Inspect `indexBounds` and remaining filter predicates. An unbounded or wide range can cause far more keys to be examined than final results returned.

### 13.3. Reading `rejectedPlans` in Proper Scope

`queryPlanner.rejectedPlans` describes plans that were not chosen; it does not mean MongoDB executed them to completion. When using `allPlansExecution`, trial metrics for other plans also have their own scope. Never add candidate plans' `keysExamined` into `executionStats.totalKeysExamined` when evaluating a query.

## 14. Sort: Why Looking at Only Three Numbers Is Not Enough

Consider the query:

```javascript
db.explainOrdersDemo.find({
  tenantId: "T2",
  status: "PAID"
}).sort({ createdAt: -1 })
  .limit(10)
  .explain("executionStats");
```

The query has two parts:

1. Find documents matching the filter.
2. Pick **the 10 documents with the newest `createdAt`**.

If an index supports only the equality filters and not the sort, MongoDB may have to examine **the entire candidate set** to identify the 10 newest documents. The result is still:

```text
nReturned = 10
```

yet `totalKeysExamined` and `totalDocsExamined` can be much larger than 10.

The compound index:

```javascript
db.explainOrdersDemo.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
```

can allow reading in the right order within that tenant/status slice and stopping early thanks to `limit`.

**However, two plans with identical values for these three metrics can still have different execution times** if one requires sorting, extra computation, or heavier memory processing. When evaluating a query with `sort`, also check for a `SORT` stage, whether an index supplies the sort order, and `executionTimeMillis` in measurement context.

## 15. Deep Pagination: Small `nReturned` Yet Heavy Traversal

Example:

```javascript
db.explainOrdersDemo.find({
  tenantId: "T2"
})
.sort({ createdAt: -1, _id: -1 })
.skip(300)
.limit(20)
.explain("executionStats");
```

Even if an index supports both filter and order, the server may still have to **walk past** a large number of results before grabbing 20 documents at a deep page. That can yield:

```text
nReturned         = 20
totalKeysExamined ≈ 320
totalDocsExamined may be higher, lower than 320, or equal to 0
```

This is strictly a qualitative illustration; exact numbers depend on projection, plan, and stage order. The key takeaway is that `skip` can cause cost to grow with page depth.

If the application needs to scroll continuously through large datasets, consider **keyset pagination**:

```javascript
// First page.
db.explainOrdersDemo.find({
  tenantId: "T2"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
```

Store `lastCreatedAt` and `lastId` from the last document on the page. The next page filters on the sort key:

```javascript
db.explainOrdersDemo.find({
  tenantId: "T2",
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    {
      createdAt: lastCreatedAt,
      _id: { $lt: lastId }
    }
  ]
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
```

Here `lastCreatedAt` and `lastId` are variables captured by the application from the previous page; do not run the next-page snippet without initializing those two variables.

Keyset pagination avoids skipping past a huge offset, but it only works reliably when sort order, tokens, filter conditions, and sort fields are designed consistently. This technique does not automatically create a fixed snapshot when concurrent writes occur.

## 16. Comparing an Index Before and After a Change

When testing a compound index, the disciplined approach is to keep **the query and dataset identical**, changing only one variable at a time.

### 16.1. Save the Query Under Analysis

```javascript
const filter = { tenantId: "T2", status: "PAID" };
const sort = { createdAt: -1 };
const limit = 10;

db.explainOrdersDemo.find(filter)
  .sort(sort)
  .limit(limit)
  .explain("executionStats");
```

### 16.2. Compare Index Candidates

Example candidate indexes:

```javascript
// Tenant only:
db.explainOrdersDemo.createIndex({ tenantId: 1 });

// Tenant + status:
db.explainOrdersDemo.createIndex({
  tenantId: 1,
  status: 1
});

// Tenant + status + sort:
db.explainOrdersDemo.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
```

In practice, multiple indexes may coexist. The planner might choose a different index from the one you just created. If you need to compare **one specific index in isolation** in a test environment, you can use `hint()` to request the desired plan:

```javascript
db.explainOrdersDemo.find(filter)
  .sort(sort)
  .limit(limit)
  .hint({ tenantId: 1, status: 1, createdAt: -1 })
  .explain("executionStats");
```

**Do not turn `hint()` into a blanket production recommendation**. A hint forces an index path; when data, server version, key distribution, or workload changes, the forced index may no longer be optimal. Use hints primarily for controlled experiments and impact validation before considering long-term use.

### 16.3. Result Tracking Table

After each `explain` run, record:

| Plan / Index | `nReturned` | `totalKeysExamined` | `totalDocsExamined` | `executionTimeMillis` | Has `SORT`? |
|---|---:|---:|---:|---:|---|
| Collection scan or baseline | Fill from explain | Fill from explain | Fill from explain | Fill from explain | Yes/No |
| Index `tenantId` | Fill from explain | Fill from explain | Fill from explain | Fill from explain | Yes/No |
| Index `tenantId, status` | Fill from explain | Fill from explain | Fill from explain | Fill from explain | Yes/No |
| Index `tenantId, status, createdAt` | Fill from explain | Fill from explain | Fill from explain | Fill from explain | Yes/No |

Never pick the row with the lowest `executionTimeMillis` from a single run, because millisecond timings fluctuate with cache state, background load, and small dataset sizes. Read **all together**: key count, document count, stages, real latency, and index maintenance cost.

## 17. Cases Where Three Metrics Alone Are Insufficient

### 17.1. Results Must Be Grouped or Aggregated

```javascript
db.explainOrdersDemo.explain("executionStats").aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: "$tenantId",
      totalAmount: { $sum: "$amount" }
    }
  }
]);
```

An output of five groups may require inspecting many source documents. A low output `nReturned` is normal. Examine input costs and the `$match` and `$group` stages rather than applying list-page ratios.

### 17.2. Queries Returning Very Many Documents

An export of 100,000 documents might have:

```text
nReturned         = 100,000
totalKeysExamined = 100,000
totalDocsExamined = 100,000
```

Keys/returned and docs/returned ratios near 1 look great, yet transferring 100,000 documents over the network, decoding BSON, and processing in the application can still take significant time. In this situation, also review projection, batch size, throughput, and streaming options.

### 17.3. Documents of Differing Sizes

Two queries both read 1,000 documents, yet one set has documents of a few hundred bytes while the other has huge documents. The three metrics do not directly reflect **the number of bytes read or returned**. Cache hit rates, disk I/O, and document size can strongly impact timing.

### 17.4. Queries Using Multiple Indexes or `$or` Branches

```javascript
db.explainOrdersDemo.find({
  $or: [
    { tenantId: "T1", status: "PAID" },
    { tenantId: "T2", status: "PAID" }
  ]
}).explain("executionStats");
```

A plan can execute multiple index branches and merge results; keys examined may be the sum across branches. A single document can also match multiple branches and require deduplication. You must inspect the stage structure rather than interpreting the three metrics as a single simple index scan.

### 17.5. Queries on a Sharded Cluster

In a sharded cluster, `mongos` can route a query to one or multiple shards. Explain output can contain per-shard statistics and a result-merging section. In that case:

- Each shard's `nReturned` does not necessarily equal the final client document count.
- Shards may examine vastly different numbers of keys/documents due to data distribution.
- Sort/limit and merge steps can affect result counts at different tiers.
- A single "hot" or slow shard can dominate latency even if aggregate counters are modest.

Read both **per-shard statistics** and the router merge plan. Do not mistakenly add already-aggregated totals onto per-shard numbers when they represent the same work at different tiers.

## 18. Complementary Metrics to Inspect Alongside the Main Three

| Metric / Info | Follow-Up Question |
|---|---|
| `winningPlan` | Which strategy did the planner select? |
| `indexName` / `keyPattern` | Which index did the query actually use? |
| `indexBounds` | Which key ranges are scanned? Wide or narrow? |
| `executionStages` | Which stage incurs the cost? |
| `executionTimeMillis` | What duration did explain record during this analysis? |
| `SORT` and related stats | Is there a resource-heavy sort? |
| `isMultiKey` / `multiKeyPaths` | Does the index involve arrays? |
| `dupsTested` / `dupsDropped` when present | Do multiple keys/branches point to the same document? |
| `rejectedPlans` | Which alternatives did the planner consider and reject? |
| Profiler and application metrics | At which step do users actually wait? |

**Distinguish server-side metrics from client-side metrics.** Explain's `executionTimeMillis` excludes application time spent selecting a server, waiting on a connection pool, fetching multiple batches, decoding data, and processing JSON after receipt.

## 19. Workflow for Diagnosing a Slow Query

When a query returns a few rows yet is slow, you can follow this workflow.

### Step 1 — Pin Down the Business Query

Define the exact filter, projection, sort, limit/skip, and consistency requirements:

```javascript
db.explainOrdersDemo.find(
  { tenantId: "T2", status: "PAID" },
  { _id: 1, createdAt: 1, amount: 1 }
).sort({ createdAt: -1 }).limit(10);
```

Do not compare a query returning full documents with a query returning two fields as though their costs were equivalent.

### Step 2 — Collect Explain

```javascript
db.explainOrdersDemo.find(
  { tenantId: "T2", status: "PAID" },
  { _id: 1, createdAt: 1, amount: 1 }
).sort({ createdAt: -1 }).limit(10)
 .explain("executionStats");
```

Record the three metrics along with `winningPlan`, selected index, sort, and execution time.

### Step 3 — Read the Three Metrics in Order

**First check `nReturned`:** does the query return the expected count? Do `limit`, `skip`, or aggregation alter the output?

**Next check `totalDocsExamined`:** did the server read many documents to return a few results? Is there a `FETCH`, `COLLSCAN`, or residual filter?

**Then check `totalKeysExamined`:** did the query scan many index keys? Are `indexBounds` wide? Are multikey, `$in`, `$or`, or deduplication involved?

Reading in this order prevents misinterpreting a large number before knowing what goal it serves.

### Step 4 — Narrow Down the Root Cause

| Observation | Potential Causes to Check Next |
|---|---|
| `keys = 0`, `docs` very large | Collection scan; index missing/unhelpful, or query needs many documents |
| `keys` large, `docs` large, `nReturned` small | Weak index selectivity, filter evaluated at FETCH, sort/skip, or overly broad range |
| `keys` large, `docs` low | Scanning many index keys, multikey/deduplication, wide bounds, partial index-only filtering |
| `docs = 0`, `keys` close to `nReturned` | Likely an efficient covered query |
| `nReturned = 0` yet `docs` large | No matches found, yet many documents were scanned |
| `keys/docs` low yet query still slow | Sort, CPU expressions, document size, I/O, network, application |
| Same query slow only on one shard | Skewed data distribution, index, cache, or shard load |

### Step 5 — Propose Small, Targeted Changes

Commonly helpful actions:

- Create/adjust a compound index to match filter predicates and sort order.
- Review index field order (equality conditions, range conditions, sort).
- Trim unnecessary fields from projections.
- Avoid deep `skip` where keyset pagination fits.
- Verify type, array, and `$elemMatch` predicates match business intent.
- Adjust the data model if per-request computation or joining is too expensive.
- Reduce returned document counts if the API does not truly need them.

### Step 6 — Re-measure on the Same Workload

Use the exact same query, dataset, projection, and sort. Record before/after values of the three metrics alongside latency and write/index overhead. One change might speed up query A while slowing down inserts/updates or enlarging indexes enough to hurt query B.

### Step 7 — Do Not Ignore the Production Environment

An index chosen on a 2,000-document dataset can differ from a 100-million-document collection. Measurements must be validated on a representative workload, under realistic caching conditions and realistic data distributions. Only **real numbers from a measured environment** should be used to promise performance improvements.

## 20. Common Misconceptions

| Misconception | Accurate Interpretation |
|---|---|
| `IXSCAN` is always fast | An index can still scan huge numbers of keys; check bounds and result counts |
| `COLLSCAN` is always bad | On small sets or queries returning most data, a collection scan can be sensible |
| `nReturned` is the number of documents examined | It reflects the output count at the scope being inspected |
| `totalKeysExamined` is the number of indexes used | It is the number of **index keys examined**, not index structures |
| `totalDocsExamined` is total collection documents | It is the count of document examinations during execution |
| `totalKeysExamined = 0` means zero cost | A collection scan can have `keys = 0` and huge `docs` |
| `totalDocsExamined = 0` means zero results returned | A covered query can return results from the index without reading source documents |
| `totalDocsExamined = nReturned` guarantees full optimization | It may still scan huge numbers of keys or incur sort/other costs |
| Keys greater than docs means the index is broken | Multikey and complex plans can inspect multiple keys per document |
| You should divide `docs / nReturned` for every aggregation | Group/unwind/count change what output document counts mean |
| `nReturned = 0` means the query is practically free | A non-matching query can still scan massive amounts of data |
| `limit(10)` guarantees only 10 documents are examined | Sort, skip, and poorly selective filters can force the server to inspect far more |
| `explain` captures all system time | It omits full driver, network, and application processing time |
| Creating a compound index guarantees the planner picks it | The planner also weighs data, stats, query conditions, and other indexes |
| Every explain run yields identical counts/timings | Plans and timings can vary with conditions and versions |

## 21. Practice Exercises

### Exercise 1 — Reading a Metrics Table

Three plans for **the same query** have hypothetical metrics:

| Plan | `nReturned` | `totalKeysExamined` | `totalDocsExamined` |
|---|---:|---:|---:|
| A | 15 | 15 | 15 |
| B | 15 | 4,000 | 4,000 |
| C | 15 | 0 | 50,000 |

Answer:

1. Which plan examines the fewest keys and documents?
2. Which plan most likely uses `COLLSCAN`?
3. Which plan likely uses an index yet still performs heavy post-filtering?
4. Why can you not prove from this table alone that A has the lowest latency?

### Exercise 2 — Running `explain("executionStats")` Yourself

Using the `explainOrdersDemo` collection from section 2:

```javascript
db.explainOrdersDemo.find({
  tenantId: "T2",
  status: "PAID"
}).sort({ createdAt: -1 }).limit(10)
  .explain("executionStats");
```

Record `nReturned`, `totalKeysExamined`, `totalDocsExamined`, and the winning plan's stages. Then create index `{ tenantId: 1, status: 1, createdAt: -1 }` and run it again. Explain the results based on **the metrics you actually observed**, not the illustrative numbers in the lesson.

### Exercise 3 — Why Does Projection Change `docsExamined`?

Given the index:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

Compare:

```javascript
// A
db.explainOrdersDemo.find(
  { tenantId: "T2", status: "PAID" },
  { _id: 0, tenantId: 1, status: 1, createdAt: 1 }
).explain("executionStats");

// B
db.explainOrdersDemo.find(
  { tenantId: "T2", status: "PAID" },
  { _id: 0, tenantId: 1, status: 1, createdAt: 1, amount: 1 }
).explain("executionStats");
```

Identify which query **can be covered**, why adding `amount` may trigger `FETCH`, and why a wider index is not necessarily better for overall system cost.

### Exercise 4 — Impact of Sort and Limit

Compare two queries:

```javascript
db.explainOrdersDemo.find({
  tenantId: "T2",
  status: "PAID"
}).limit(10).explain("executionStats");

db.explainOrdersDemo.find({
  tenantId: "T2",
  status: "PAID"
}).sort({ createdAt: -1 })
  .limit(10)
  .explain("executionStats");
```

Why can adding a sort cause the query to examine more entries even though `nReturned` remains 10? At which step can a compound index help?

### Exercise 5 — `nReturned = 0`

Run a query guaranteed to match nothing:

```javascript
db.explainOrdersDemo.find({
  tenantId: "NOT-EXISTING"
}).explain("executionStats");
```

Compare the plans **with** and **without** an index supporting `tenantId` in a suitable test environment. Why can you not compute a `docs/returned` ratio when zero results return? Which metrics reveal whether the query did a lot or a little work?

### Exercise 6 — Multikey and Key Counts

Create the index:

```javascript
db.explainOrdersDemo.createIndex({ tags: 1 });
```

Run:

```javascript
db.explainOrdersDemo.find({
  tags: { $in: ["vip", "promotion"] }
}).explain("executionStats");
```

Explain why a document matching both tags is still returned only once by `find()`. When keys examined exceeds documents read, what information should you inspect in the plan?

### Exercise 7 — Comparing Offset Pagination vs. Keyset Pagination

Query:

```javascript
db.explainOrdersDemo.find({
  tenantId: "T2"
})
.sort({ createdAt: -1, _id: -1 })
.skip(300)
.limit(20)
.explain("executionStats");
```

Design the keyset query for the next page based on `createdAt` and `_id` of the previous page's last document. Explain why on deep pages `nReturned` can remain 20 while `totalKeysExamined` is large.

### Exercise 8 — Aggregation Results Differ from Find Results

Given the pipeline:

```javascript
db.explainOrdersDemo.explain("executionStats").aggregate([
  { $match: { status: "PAID" } },
  { $group: { _id: "$tenantId", count: { $sum: 1 } } }
]);
```

Describe why the pipeline's output document count can be vastly smaller than `totalDocsExamined`. When should you examine `$group` stage statistics instead of relying on a simple ratio?

### Exercise 9 — Distinguishing Index-Only Queries from Collection Scans

Two hypothetical metric sets:

```text
X: nReturned=100, totalKeysExamined=100, totalDocsExamined=0
Y: nReturned=100, totalKeysExamined=0, totalDocsExamined=100
```

Propose a plausible plan for X and Y. Can you assert X is always faster than Y? What additional facts are needed to evaluate them?

### Exercise 10 — Writing a Brief Diagnostic Report

An API fetching the 20 most recent orders reports:

```text
nReturned         = 20
totalKeysExamined = 90,000
totalDocsExamined = 1,000
```

Write a report covering:

1. Which two metrics show a large gap relative to result count?
2. What causes are suggested when fewer documents are fetched than keys examined?
3. Which stages, index bounds, multikey info, or sorts should be checked next?
4. How could a compound index help if the query filters by `tenantId`, `status`, and sorts by `createdAt`?
5. What should be re-measured before proposing the index for production?

## 22. Summary

**`nReturned` tells you the output count, `totalKeysExamined` tells you how many index keys were examined, and `totalDocsExamined` tells you how many times documents were examined.** These three metrics describe different layers of work in an execution plan and only make sense when read side by side.

**Close numbers do not automatically mean optimal; large gaps do not automatically mean a bug.** A covered query can have `docsExamined = 0`, a collection scan has `keysExamined = 0`, a multikey index holds multiple keys per document, and `limit` or `$group` can make `nReturned` tiny relative to its input.

**To optimize accurately, understand the query before looking at the numbers.** Identify the filter, projection, sort, limit/skip, array data, `indexBounds`, and the busiest stages; only then formulate hypotheses about indexes or query design.

**`explain("executionStats")` is a starting point for investigation, not a final performance test.** Cross-check against real latency, read/transfer volume, system load, and index maintenance overhead before deciding on changes. When you read all three metrics in context, you can explain **how much work MongoDB actually did to produce the result** instead of merely guessing that "the query has an index."
