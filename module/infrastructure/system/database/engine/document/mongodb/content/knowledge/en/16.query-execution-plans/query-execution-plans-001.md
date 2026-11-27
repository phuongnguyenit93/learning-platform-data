# `explain` and `queryPlanner`, `executionStats`, `allPlansExecution` Levels in MongoDB

A syntactically valid MongoDB query is not guaranteed to run efficiently. When a collection has many documents, different execution strategies can produce vastly different costs: scanning the entire collection, reading an index and then fetching the source documents, or reading directly from index keys that already satisfy both filtering and sorting. To understand **how MongoDB plans to execute a query** and **how much data it processed during execution**, we use **`explain`**.

MongoDB lets you choose from three levels of detail, called **verbosity**:

- **`queryPlanner`**: shows the selected query plan (winning plan), rejected candidate plans, and planning details, without providing statistics from a full query execution.
- **`executionStats`**: adds statistics from executing the selected plan, such as the number of results returned, the number of index keys and documents examined, and the reported execution time.
- **`allPlansExecution`**: includes the same information as `executionStats` while also adding statistics from the **plan selection trial phase** for candidate plans when multiple plans are considered; it does not mean MongoDB runs all plans completely to the end of the result set.

This lesson belongs to the **Query Execution Plans** chapter. The goal is to know how to invoke the right `explain` verbosity level, read the key metrics, spot signs of an unsuitable index, understand the limitations of the output, and choose the right tool when investigating slow queries.

## 1. One Query Can Have Multiple Execution Paths

Suppose the `orders` collection contains hundreds of thousands of orders. The application needs to view the 10 most recent orders for customer `C0042`:

```javascript
db.orders.find({ customerId: "C0042" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(10)
```

MongoDB needs to return that customer's orders in newest-first order. However, it can reach the result via very different paths:

```text
                         Query
       customerId = C0042, sort createdAt/_id, limit 10
                             |
               +-------------+-------------+
               |                           |
     Scan documents in collection     Use suitable index
               |                           |
        Filter customerId            Seek to C0042 key range
               |                           |
          Sort results                Read in index order
               |                           |
          Take at most 10              Take at most 10
               |                           |
               +-------------+-------------+
                             |
                    Same logical result
                   but cost may differ
```

When no suitable index exists, the server may use a `COLLSCAN` and a `SORT` operation. With an appropriate compound index, such as `{ customerId: 1, createdAt: -1, _id: -1 }`, MongoDB can read the customer's key range in the required order without manually sorting all of that customer's orders.

`explain` lets you observe **the specific plan chosen on the current data and MongoDB version**, rather than guessing based on whether the collection already has indexes.

## 2. `explain` Syntax in `mongosh`

### 2.1. Calling Directly on the `find()` Cursor

```javascript
// Default verbosity: queryPlanner
db.orders.find({ customerId: "C0042" })
  .explain()

// View planning information only
db.orders.find({ customerId: "C0042" })
  .explain("queryPlanner")

// View execution statistics for the winning plan
db.orders.find({ customerId: "C0042" })
  .explain("executionStats")

// Also view trial execution statistics for candidate plans
db.orders.find({ customerId: "C0042" })
  .explain("allPlansExecution")
```

To explain **the exact query the application uses**, keep the `filter`, `sort`, `skip`, `limit`, `projection`, and related options:

```javascript
db.orders.find(
  { customerId: "C0042", status: "paid" },
  { _id: 0, customerId: 1, createdAt: 1, total: 1 }
)
  .sort({ createdAt: -1 })
  .skip(20)
  .limit(10)
  .explain("executionStats")
```

Running `explain` only on `find({customerId: ...})` and applying that conclusion to a query that also includes `sort`, `skip`, and `projection` is insufficient: different query shapes can produce different plans.

### 2.2. Calling via `db.collection.explain()`

MongoDB also supports this form:

```javascript
db.orders.explain("executionStats")
  .find({ customerId: "C0042" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(10)
```

This is the **explainable collection helper**; it is useful when you want a consistent calling pattern across `find`, `aggregate`, and other supported operations. For `find`, both calling styles express the intent to retrieve the query's explain output.

### 2.3. Calling via Database Command

When you need explicit command control or integration through a driver, use the database `explain` command:

```javascript
db.runCommand({
  explain: {
    find: "orders",
    filter: { customerId: "C0042" },
    sort: { createdAt: -1, _id: -1 },
    limit: 10
  },
  verbosity: "executionStats"
})
```

The `find: "orders"` part sits inside the command to be explained; `verbosity` sits outside to select the level of detail. The command runs against the **current database**, so verify you are in the right database before practicing.

## 3. Comparing the Three Verbosity Levels

| Level | Purpose | Typical Information | Questions to Ask |
| --- | --- | --- | --- |
| `queryPlanner` | Understand plan selection | `queryPlanner`, `winningPlan`, `rejectedPlans`, query shape info and stages | Which index does MongoDB intend to use; are `SORT` or `FETCH` needed? |
| `executionStats` | Measure work of the winning plan | Planner info plus `executionStats`: `nReturned`, `totalKeysExamined`, `totalDocsExamined`, `executionTimeMillis`, execution stage tree | Is it examining too many keys/docs to return a few results? |
| `allPlansExecution` | Investigate candidate comparison | Info from both levels above plus `allPlansExecution` when candidate plan data is available | How did competing candidates perform during the plan selection trial phase? |

A sensible reading workflow is to **start with `queryPlanner`**, move to `executionStats` when operational metrics are needed, and use `allPlansExecution` if you suspect an issue in choosing among multiple indexes or plans.

The three levels do not represent three different query algorithms; they are three **detail levels returned** by the plan explanation mechanism. Higher detail generally entails additional observation work and more explain output to read.

## 4. Preparing Lab Data

Use a lab database with read/write permissions. The data generation commands below are intended only for a practice environment:

```javascript
use mongo_explain_lab
```

Create 2,400 sample orders:

```javascript
const sampleOrders = Array.from({ length: 2400 }, (_, i) => ({
  _id: i + 1,
  orderCode: "ORD-" + String(i + 1).padStart(5, "0"),
  customerId: "C" + String((i % 300) + 1).padStart(4, "0"),
  status: i % 10 < 8 ? "delivered" : "pending",
  total: 100 + (i % 100) * 5,
  createdAt: new Date(Date.UTC(2026, 0, 1) + i * 60000),
  channel: i % 3 === 0 ? "mobile" : "web"
}));

db.orders.insertMany(sampleOrders);
```

This dataset has several intentional characteristics:

- Each customer from `C0001` to `C0300` has 8 orders.
- `status: "delivered"` makes up 80% of documents; `status: "pending"` makes up 20%.
- `createdAt` increments by one minute per document to establish a clear chronological order.
- The `_id` field is chosen to be unique to support deterministic sorting and clarify lookups via the `_id_` index.

On small datasets, MongoDB may choose a different plan than expected because scanning the collection is also very cheap. Do not treat illustrative numbers in this lesson as actual server measurements.

Run `insertMany()` only once on a new/empty collection; running it repeatedly with the same `_id` values causes duplicate key errors. Avoid dropping real collections to recreate sample data.

Verify the data with standard queries:

```javascript
db.orders.countDocuments({})
db.orders.countDocuments({ customerId: "C0042" })
db.orders.countDocuments({ status: "pending" })
```

According to the generation formula, the results are `2400`, `8`, and `480`, respectively.

## 5. The `queryPlanner` Level: What Does MongoDB Plan to Do?

Run:

```javascript
db.orders.find({ customerId: "C0042" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(5)
  .explain("queryPlanner")
```

The explain response may contain these groups of information:

```text
explain
├── explainVersion              (depends on version)
├── queryPlanner
│   ├── namespace               database.collection
│   ├── parsedQuery             parsed filter expression
│   ├── winningPlan             selected plan tree
│   ├── rejectedPlans           unselected candidate plans
│   └── ...                     other info depending on version
├── serverInfo                  server details (when available)
└── ...                         metadata, command parameters
```

The exact structure **varies across MongoDB versions and execution engines**. Some versions use the classic plan tree with `stage`; others include `queryPlan` and `slotBasedPlan` when the query runs on the **slot-based execution engine (SBE)**. Therefore, read **the meaning of the stages and selected indexes** rather than writing tools that assume a single fixed JSON tree shape.

### 5.1. `winningPlan` and `rejectedPlans`

`winningPlan` represents the plan MongoDB chose to execute during that explain run. Stages can be nested:

```text
LIMIT
  └── FETCH
        └── IXSCAN
              indexName: idx_customer_created_id
```

This is an **illustrative tree**, not a guarantee that every version will return these exact stage names or nesting format. It conveys the idea: scan the index, fetch source documents if needed, and limit the output.

`rejectedPlans` shows the candidates that were not chosen when the planner had multiple options to evaluate. **Rejected does not necessarily mean wrong**; that candidate simply was not selected in the current planning context. If there are no competing candidates, the `rejectedPlans` array may be empty.

### 5.2. `parsedQuery` Differs from the User's Query String

`parsedQuery` reflects the expression MongoDB produces after parsing the filter. For example, a simple equality condition may be normalized into an explicit operator form. Thus, do not expect `parsedQuery` to match the shell filter character-for-character; what matters is checking **filter semantics**.

### 5.3. Questions to Ask When Reading the Planner

1. Is there a `COLLSCAN` or `IXSCAN` stage?
2. If `IXSCAN` is used, is it the expected index?
3. Is `sort` satisfied by index order, or does a `SORT` stage appear?
4. Is there a `FETCH` stage indicating source documents must be read?
5. Does the plan include `LIMIT`, and is the limit positioned appropriately?
6. Are there any notable plans in `rejectedPlans`?

`queryPlanner` is usually enough to answer "which path does MongoDB intend to take," but **not enough** to state how many documents that path read or how many milliseconds it took at runtime.

## 6. Common Stages and How to Interpret Them

| Stage / Concept | Role | What to Watch For |
| --- | --- | --- |
| `COLLSCAN` | Scans the collection to inspect documents | May be reasonable on small collections or when most of the data must be read |
| `IXSCAN` | Traverses keys in an index | Check index name, key bounds, and keys examined |
| `FETCH` | Retrieves documents from the collection after finding keys | May be needed because filter or projection lacks fields in the index |
| `SORT` | Sorts results at an execution step | Can increase cost when the index does not support the sort order |
| `LIMIT` | Caps the number of returned results | Does not mean the preceding search/filter cost is always small |
| `SKIP` | Skips a number of results | Large offsets may have to walk past many entries |
| `PROJECTION` or covered variants | Selects returned fields | Covered queries may avoid fetching source documents |
| `COUNT_SCAN` | Counts via an index scan when eligible | Depends on query shape and plan |
| `EOF` | Plan has no results to process in that context | Read alongside filter and other explain sections |

Do not treat this as an **exhaustive list of stages**. The query engine may display `OR`, `AND_HASH`, `SHARD_MERGE`, or other stage names depending on the query type, optimization, and sharding configuration. With SBE, low-level descriptions may use distinct operators that do not match classic engine stage names.

### `IXSCAN` Does Not Automatically Mean an Optimal Query

For example, the query planner picks index `{ status: 1 }` for:

```javascript
db.orders.find({ status: "delivered" })
```

If 80% of documents have `status: "delivered"`, the query may still examine a huge number of keys and documents even though the stage is `IXSCAN`. Conversely, a `COLLSCAN` on a very small collection can be an efficient choice.

**Conclusions must be based on actual workload**, not merely labeling "`IXSCAN` is good" and "`COLLSCAN` is bad".

### `indexBounds`: Which Key Range Does the Index Scan?

When `IXSCAN` is present, part of the plan may show `indexBounds`, describing the range of keys scanned. With an equality filter `customerId: "C0042"`, that field's key range is typically bounded around that value; with a range filter `total: {$gte: 500}`, the range is wider.

Visualizing it:

```text
Index on customerId:

... C0040 | C0041 | [C0042 ... C0042] | C0043 | ...
                      ^ range to inspect
```

If `indexBounds` is too broad or an important condition cannot form a tight bound on the index, MongoDB may have to scan many keys before filtering. Reading `indexBounds` should be combined with the filter, index key order, multikey flags, and execution statistics.

## 7. The `executionStats` Level: How Much Data Did MongoDB Process?

Run the same query with higher verbosity:

```javascript
db.orders.find({ customerId: "C0042" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(5)
  .explain("executionStats")
```

The response includes planner information **and** the `executionStats` section, typically containing fields such as:

```javascript
// Structural illustration only, not measured output from the sample data
{
  executionStats: {
    nReturned: 5,
    executionTimeMillis: 2,
    totalKeysExamined: 5,
    totalDocsExamined: 5,
    executionStages: {
      // Stage tree and detailed counters depending on MongoDB version
    }
  }
}
```

The numbers `5` and `2` **only illustrate an efficient plan case**. Actual results may differ and cannot be deduced from query syntax alone.

| Field | Interpretation |
| --- | --- |
| `nReturned` | Number of result documents/values returned during the explained execution |
| `executionTimeMillis` | Reported execution time, usually in ms; affected by environment conditions |
| `totalKeysExamined` | Total number of index keys scanned/examined according to statistics |
| `totalDocsExamined` | Total number of documents examined in steps that read documents |
| `executionStages` | Detailed execution tree, potentially containing per-stage counters |

### 7.1. Distinguishing Examined vs. Returned

Suppose a query returns `nReturned = 10` but `totalDocsExamined = 50,000`. That shows a huge number of documents were examined relative to the results returned. Perhaps the index is unsuitable, a filter is evaluated only after fetching, or the query must read large amounts of data to sort or skip.

A hypothetical example:

| Query | `nReturned` | `totalKeysExamined` | `totalDocsExamined` | Initial Assessment |
| --- | ---: | ---: | ---: | --- |
| A | 10 | 12 | 10 | Few items examined relative to results |
| B | 10 | 80,000 | 20,000 | Examines very many keys and documents |
| C (covered) | 10 | 10 | 0 | Can return results from index without fetching documents |
| D (COLLSCAN) | 10 | 0 | 2,400 | Scans documents without an index |

This table is only for practicing metric reading; not every row corresponds to a measured plan. **Whether a cost is good or bad depends on what the query needs to do**, not solely on a ratio. For instance, counting millions of documents, deep pagination, or aggregations may legitimately have high `examined` counts.

### 7.2. When Is `totalDocsExamined = 0`?

A **covered query** can use only the index to filter and retrieve returned fields without fetching source documents. For example, given the index:

```javascript
db.orders.createIndex(
  { customerId: 1, createdAt: -1, _id: -1 },
  { name: "idx_customer_created_id" }
)
```

a query that only needs fields contained in the index:

```javascript
db.orders.find(
  { customerId: "C0042" },
  { _id: 1, customerId: 1, createdAt: 1 }
)
  .sort({ createdAt: -1, _id: -1 })
  .limit(5)
  .explain("executionStats")
```

can be satisfied from the index without reading source documents, depending on the planner and configuration. However, if the projection also requires `total`, which is not in the index, MongoDB may have to `FETCH` documents to read `total`.

Do not confuse **`totalDocsExamined = 0`** with "doing no work": the query may still examine many index keys or perform other operations.

### 7.3. `executionTimeMillis` Is Not a Production Latency Guarantee

Explain timing is affected by:

- Data size, value distribution, and indexes.
- Cache state, disk I/O, CPU load, and concurrent requests.
- MongoDB version, hardware specs, and replica set/sharded cluster topology.
- Plan trial overhead and how `explain` executes and reports statistics.
- Differences between a shell measurement and a real request, which also include network, driver, BSON decoding, and application processing.

Thus, `executionTimeMillis = 2` in a single run does not guarantee an endpoint will always take 2 ms. Combine `explain` with monitoring, slow-query logs/profiler (when permitted), and benchmarks on representative workloads.

## 8. Hands-On Comparison Before and After Creating an Index

Keep a consistent query shape:

```javascript
const filter = { customerId: "C0042" };
const order = { createdAt: -1, _id: -1 };

db.orders.find(filter)
  .sort(order)
  .limit(5)
  .explain("executionStats")
```

Inspect `queryPlanner.winningPlan`, `totalKeysExamined`, `totalDocsExamined`, and sort information. In a lab environment with 2,400 documents and only the `_id_` index, a plan may scan many documents and then sort; however, **do not assert the winning plan beforehand** without running MongoDB.

Create an index matching the filter and sort:

```javascript
db.orders.createIndex(
  { customerId: 1, createdAt: -1, _id: -1 },
  { name: "idx_customer_created_id" }
)
```

Run it again:

```javascript
db.orders.find(filter)
  .sort(order)
  .limit(5)
  .explain("executionStats")
```

Key things to check are whether `idx_customer_created_id` appears in the winning plan, whether MongoDB avoids an extra `SORT` step, and whether the examined keys/docs counts change.

If you want to inspect specific fields of the explain output in `mongosh`:

```javascript
const result = db.orders.find(filter)
  .sort(order)
  .limit(5)
  .explain("executionStats");

printjson(result.queryPlanner);
printjson({
  nReturned: result.executionStats?.nReturned,
  keysExamined: result.executionStats?.totalKeysExamined,
  docsExamined: result.executionStats?.totalDocsExamined,
  executionTimeMillis: result.executionStats?.executionTimeMillis
});
```

`executionStats` exists at the `executionStats`/`allPlansExecution` levels, so do not assume it exists in `queryPlanner`. The optional chaining `?.` syntax here is `mongosh` JavaScript syntax, not MongoDB query syntax.

### Do Not Compare Two Queries with Different Shapes

All of the following differences can alter the plan:

```javascript
// Query by customerId, no sort
db.orders.find({ customerId: "C0042" })

// With sort + limit
db.orders.find({ customerId: "C0042" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(5)

// With additional status condition and projection
db.orders.find(
  { customerId: "C0042", status: "pending" },
  { _id: 0, customerId: 1, status: 1 }
)
```

To attribute an improvement to a new index, compare **the exact same filter, sort, projection, and limit**, on comparable data, while recording the server version and measurement conditions.

## 9. `allPlansExecution`: Inspecting Competing Candidates

When a query has multiple suitable indexes, the query planner may need to choose among competing plans. For instance, create additional single-field indexes on `customerId` and `createdAt` in the lab:

```javascript
db.orders.createIndex(
  { customerId: 1 },
  { name: "idx_customer" }
)

db.orders.createIndex(
  { createdAt: -1 },
  { name: "idx_created_desc" }
)
```

For the query:

```javascript
db.orders.find({ customerId: "C0042" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(5)
  .explain("allPlansExecution")
```

several approaches might exist: using the compound index on customer/time; using the customer index followed by a sort; or using the time index and filtering by customer. Which candidates the planner actually evaluates depends on the version and data conditions.

At this verbosity, `executionStats` may include `allPlansExecution`:

```javascript
// Illustrates field placement only
{
  queryPlanner: {
    winningPlan: { /* ... */ },
    rejectedPlans: [ /* ... */ ]
  },
  executionStats: {
    nReturned: 5,
    totalKeysExamined: 5,
    totalDocsExamined: 5,
    executionStages: { /* ... */ },
    allPlansExecution: [
      // Candidate trial-phase statistics,
      // if the planner had candidates and data to report
    ]
  }
}
```

**Crucial distinction:** `allPlansExecution` does not mean MongoDB ran **every** candidate plan completely to the end of the dataset and measured full execution time for all plans. It generally contains statistics from the **candidate trial/evaluation phase** used to pick the winning plan, while the full execution stats reflect only the selected plan.

### Must `winningPlan` + `rejectedPlans` Match the Count of `allPlansExecution`?

Do not assume a simple one-to-one match. Reporting structure and candidate counts vary by version and planner behavior; sometimes only one viable plan exists or detailed trial info is not reported. An empty or sparse `allPlansExecution` **does not by itself prove** an index is broken.

During an investigation, read all of these together:

1. `queryPlanner.winningPlan`: the selected plan.
2. `queryPlanner.rejectedPlans`: plans listed as unselected.
3. `executionStats`: work performed by the winning plan.
4. `executionStats.allPlansExecution`: candidate trial data, if present.

### When Should You Use This Level?

- Multiple similar indexes exist and it is unclear why the planner chose a specific one.
- A query is slow for some parameter values but fast for others.
- Skewed data distribution is suspected of causing an inappropriate plan choice.
- You want to understand the range of options the planner considered, not just the winning plan's index.

For a simple question like "does it scan the collection?", `queryPlanner` is usually enough; for "how many documents did it scan?", `executionStats` is more direct.

## 10. `explain` and the Plan Cache: An Important Limitation

MongoDB can store a **chosen query plan** in the plan cache to avoid replanning from scratch on similar subsequent runs. However, `explain` is designed to **explain the planning and execution of the requested query**, not to act as a tool that directly reads the exact cached plan of an arbitrary production request.

One important rule to remember is that **`explain` does not use existing plan cache entries the way normal queries do, nor does running `explain` create new entries in the plan cache**. Consequently, the plan shown by `explain` may differ from the plan an application uses when the cache influences normal queries.

Implications:

- `winningPlan` in explain is the winning plan **for that explain invocation**.
- Do not immediately assert that every production request uses that exact same plan.
- When investigating variations over time or across parameter values, inspect monitoring data and plan cache information if you have the appropriate permissions and tools.
- Never clear the plan cache on a live system just to make an `explain` output look "more accurate"; that is a separate operational action and can impact many queries.

Across MongoDB versions, there are query shape/plan identifier fields such as `queryHash`, `planCacheKey`, or `planCacheShapeHash`. Field names and availability can change, so do not write scripts depending on a single field name without verifying against your server version.

## 11. Comparing Automatic Plan Selection vs. `hint()`

When multiple indexes exist, you sometimes need to study a specific index in isolation:

```javascript
// MongoDB chooses the plan automatically
db.orders.find({ customerId: "C0042" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(5)
  .explain("executionStats")

// Request a specific index by name
db.orders.find({ customerId: "C0042" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(5)
  .hint("idx_customer_created_id")
  .explain("executionStats")
```

`hint()` helps isolate a plan using a specific index if valid. It is an **investigative** tool and does not automatically prove the forced index is always better.

Do not force `hint` mechanically in production: if an index is renamed or dropped, data distribution shifts, or queries change, a hardcoded hint can become a liability or cause errors.

To compare two plans in a controlled environment, record `totalKeysExamined`, `totalDocsExamined`, `executionTimeMillis`, the winning plan, and the data state. When comparing hinted vs. unhinted runs, keep in mind that planning overhead and measurement conditions may differ.

## 12. `explain` for Aggregation

`explain` is not limited to `find()`. If your application aggregates data with `aggregate()`, you can explain the pipeline:

```javascript
db.orders.explain("executionStats").aggregate([
  { $match: { customerId: "C0042" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 5 },
  {
    $project: {
      _id: 1,
      customerId: 1,
      createdAt: 1,
      total: 1
    }
  }
])
```

An aggregation explain response may show `queryPlanner`, `executionStats`, or a `stages` array depending on the pipeline, which stages can be pushed down to the query engine, and the server version. Do not assume aggregation results will always place fields in the exact same locations as `find()` explain.

### Pipelines Can Be Reordered and Optimized

You might write:

```javascript
[
  { $match: { status: "pending" } },
  { $sort: { createdAt: -1 } },
  { $limit: 10 }
]
```

MongoDB can optimize execution to leverage indexes or coalesce equivalent steps. Explain describes **the plan after planning and optimization**, not necessarily a verbatim repetition of every stage in the source pipeline's order.

An aggregation stage can incur substantial cost on its own even after inputs come from an index. Therefore, for complex pipelines, read both the **initial data-reading information** and **downstream stages**, especially `$group`, `$sort`, `$lookup`, or `$unwind` when present.

### Explaining `countDocuments()` Does Not Appear in the Same Shape as `find`

Convenience helpers may execute different commands or pipelines under the hood. To inspect the plan of a count operation, explain the corresponding command or pipeline rather than assuming you can append `.explain()` to every method returning a number:

```javascript
db.orders.explain("executionStats").aggregate([
  { $match: { status: "pending" } },
  { $count: "total" }
])
```

This is an example counting pipeline. When comparing with a real `countDocuments()` call in an application, ensure filters, collation, and execution conditions match.

## 13. Reading Explain in a Sharded Cluster

On a **sharded cluster**, a query may be routed to one shard or multiple shards, and the results are then merged. Explain output can include per-shard details, merge steps, or multi-tiered reporting sections.

Conceptual example:

```text
Client
  |
 mongos
  |-- shard A: filter / IXSCAN / FETCH
  |-- shard B: filter / IXSCAN / FETCH
  '-- merge/sort/limit results
```

When a query is slow in a sharded system, also check:

- Does the query target the right shard(s) based on the shard key?
- Is there a **scatter-gather** query across many shards?
- Which shard's work do the statistics reflect, and how costly is the merge step?
- Are sort and limit executed on the shards, on the router, or both under the optimized plan?

Do not arbitrarily sum metrics across multiple explain branches and compare them to standalone server results. Report structure varies by version and query type; read per-node/per-shard scopes as well as aggregated summaries when present.

## 14. Java Sync Driver: Calling the `explain` Database Command

In a Java application using the MongoDB Sync Driver, you can send the `explain` database command to observe the same query as in `mongosh`.

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public class ExplainQueryExample {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Missing MONGODB_URI environment variable");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database =
                client.getDatabase("mongo_explain_lab");

            Document findCommand = new Document("find", "orders")
                .append("filter",
                    new Document("customerId", "C0042"))
                .append("sort",
                    new Document("createdAt", -1).append("_id", -1))
                .append("limit", 5);

            Document explainCommand =
                new Document("explain", findCommand)
                    .append("verbosity", "executionStats");

            Document explanation =
                database.runCommand(explainCommand);

            System.out.println(
                explanation.toJson()
            );

            Document stats =
                explanation.get("executionStats", Document.class);
            if (stats != null) {
                System.out.println(
                    "nReturned = " + stats.get("nReturned")
                );
                System.out.println(
                    "totalKeysExamined = "
                    + stats.get("totalKeysExamined")
                );
                System.out.println(
                    "totalDocsExamined = "
                    + stats.get("totalDocsExamined")
                );
            }
        }
    }
}
```

This snippet requires a compatible MongoDB Java Sync Driver and a valid `MONGODB_URI` environment variable. Never hardcode connection strings containing passwords directly in source code.

With a compatible Java Driver, some query iterables also provide an `explain` API with corresponding verbosity options. Using the database command explicitly illustrates the `find` and `verbosity` payloads; when an application involves complex collections, views, or aggregations, choose the invocation method suited to your driver API and version.

**Be careful when parsing JSON manually:** in the Java example, access top-level `executionStats` only if it exists. For complex aggregations or sharded explains, statistics may reside elsewhere. A robust monitoring tool must handle structural variations by version and query type instead of assuming all explains share one fixed JSON layout.

## 15. Common Pitfalls

| Misconception | What Actually Happens | How to Understand and Handle It |
| --- | --- | --- |
| "`queryPlanner` tells how many ms the query takes" | This level mainly returns planning info, without full execution stats | Use `executionStats` when metrics are needed |
| "`IXSCAN` means the query is definitely fast" | An index can scan a very wide range and fetch many documents | Check `keysExamined`, `docsExamined`, `nReturned`, and the filter |
| "`COLLSCAN` is a MongoDB bug" | Scanning the collection is sometimes a sensible plan | Check data size, selectivity, sort, and actual cost |
| "`rejectedPlans` are invalid plans" | Rejected simply means not chosen | Read planner context and candidate statistics |
| "`allPlansExecution` runs every candidate plan in full" | Candidate stats primarily describe the plan selection trial phase | Do not treat candidate timings as full query benchmarks |
| "`explain` definitely uses the application's exact plan cache" | Explain does not use the plan cache the way normal queries do | Combine with cache observation/monitoring if needed |
| "`totalKeysExamined = nReturned` means no other work remains" | Fetch, projection, network, and app processing can still occur | Read the entire plan and surrounding context |
| "`totalDocsExamined = 0` means the query consumes zero resources" | Covered queries can still traverse many index keys | Check `totalKeysExamined`, timing, and sort as well |
| "Changing `limit` or `skip` won't change the plan" | Query shape and cost can change | Explain the exact query used by the application |
| "One `executionTimeMillis` reading is enough to conclude" | Cache, system load, and trial planning affect measurements | Measure on representative workloads alongside monitoring |
| "Aggregation plans look identical to `find` plans" | Pipelines have distinct stages, optimizations, and representations | Read both pipeline stages and query planner sections |
| "Scripts can rigidly depend on `winningPlan.stage`" | SBE/sharding/versions alter structure | Handle structures according to version and scope |
| "Forcing a hint solves every problem" | An unsuitable hint can worsen performance or fail | Use only with measurements and monitoring procedures |

## 16. Practice Exercises

### Exercise 1. Choosing Verbosity

Given three requirements:

1. Find out which index a query uses and whether there is a `SORT`.
2. Find out how many index keys/documents were read when returning 20 documents.
3. Inspect candidate trial-phase statistics when the planner must choose among multiple indexes.

**Answer:**

1. `queryPlanner`.
2. `executionStats`.
3. `allPlansExecution`.

Higher levels also include parts of the information from lower levels, but you do not always need the highest verbosity for every question.

### Exercise 2. Writing `explain` with the Exact Query Shape

Requirement: retrieve the 15 newest `pending` orders, sorted by `createdAt` descending and `_id` descending, returning only `status`, `createdAt`, and `_id`. Write the command to view execution statistics.

**Answer:**

```javascript
db.orders.find(
  { status: "pending" },
  { status: 1, createdAt: 1, _id: 1 }
)
  .sort({ createdAt: -1, _id: -1 })
  .limit(15)
  .explain("executionStats")
```

When analyzing, verify the index/sort and the number of documents examined rather than just looking for an `IXSCAN`.

### Exercise 3. Reading Metrics

Two queries both return `nReturned = 10`, with hypothetical metrics:

```text
A: totalKeysExamined = 12, totalDocsExamined = 10
B: totalKeysExamined = 70000, totalDocsExamined = 25000
```

Which query shows signs of more efficient lookup/filtering? Can we state with certainty that A is faster at all times?

**Answer:** A examines far fewer keys and documents relative to the result count. That is a favorable signal. However, we cannot state with certainty that A is always faster under all conditions without checking query shape, cache, I/O, sorting, document sizes, latency, and real workload.

### Exercise 4. Comparing Before and After Indexing

The `orders` collection frequently runs:

```javascript
db.orders.find({ customerId: "C0042" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(5)
```

Propose a suitable index, then write an explain command to verify it.

**Answer:**

```javascript
db.orders.createIndex(
  { customerId: 1, createdAt: -1, _id: -1 },
  { name: "idx_customer_created_id" }
)

db.orders.find({ customerId: "C0042" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(5)
  .explain("executionStats")
```

Compare against the baseline before creating the index, specifically `winningPlan`, keys/docs examined, and whether `SORT` appears. A new index is only a **candidate**; there is no guarantee the query planner will always choose it on every dataset.

### Exercise 5. Why Is `rejectedPlans` Empty?

A query returns `rejectedPlans: []`. Can we conclude that MongoDB is malfunctioning?

**Answer:** No. There may simply not be multiple viable candidates to compare, or the planner's reporting may have no rejected plans. Read the entire explain output and context; an empty `rejectedPlans` array is not an error signal on its own.

### Exercise 6. Understanding `allPlansExecution`

A report has a winning plan, two rejected plans, and several candidate statistics. Should you take `executionTimeMillis` or the trial counters of each candidate and declare "this is the full time to run the entire query using index X"?

**Answer:** No. Candidate statistics in `allPlansExecution` relate to the plan selection trial phase; they do not necessarily reflect running the full query for each option. To study a single option independently, you can explain the same query with an appropriate `hint` in a controlled environment and compare full results, while still accounting for measurement context.

### Exercise 7. When `FETCH` Appears

A query filters only on `customerId` but needs to return `total`, whereas the index only includes `customerId` and `createdAt`. Why might MongoDB have to `FETCH` the source documents?

**Answer:** The index does not contain the `total` value, so the server may need to fetch the document to read this field. If truly worthwhile for the workload, consider an index including the additional field needed by the query, weighing storage and write overhead. Do not expand an index just to avoid `FETCH` for a rarely used query.

## 17. Workflow for Investigating Slow Queries with `explain`

When a MongoDB endpoint is slow, you can follow this sequence:

1. **Capture the actual query**: filter, sort, limit, skip, projection, collation, parameters, and database/collection. Do not rely on a vague description like "find customer orders."
2. **Run `queryPlanner`**: inspect the winning plan, considered indexes, sort/fetch stages, bounds, and any collection scans.
3. **Run `executionStats` in an appropriate environment**: compare `nReturned` against `totalKeysExamined` and `totalDocsExamined`; note limit, offset, and stage-level activity.
4. **If multiple plans compete**, use `allPlansExecution` to examine candidate trial data; do not treat it as a full benchmark of each plan.
5. **Check existing indexes** with `getIndexes()`; design new indexes considering equality, sort, range, projection, and value distribution—not just field names.
6. **Run controlled experiments**: when appropriate, compare before/after index creation or use `hint` in a test environment, keeping the query shape and measurement conditions equivalent.
7. **Review production context**: cache, plan cache, sharding, concurrency, slow-query monitoring, index size, and write cost. `explain` is a diagnostic tool, not a replacement for overall observability.

## Conclusion

`explain` is the bridge between the query a developer writes and how MongoDB executes it. **`queryPlanner` answers "what does MongoDB plan to do?"**; **`executionStats` answers "how much work did the winning plan do?"**; and **`allPlansExecution` helps explain "how were competing candidates tested during plan selection?"**.

When evaluating a query, inspect **both the plan and the metrics**. An `IXSCAN` can scan too many keys; a `COLLSCAN` can be appropriate on small datasets; a `FETCH` can be necessary if the projection needs fields outside the index; and a low `executionTimeMillis` in explain does not guarantee consistently low application latency. Understanding the three verbosity levels, the difference between query plans and execution metrics, and the limits of explain will help you design indexes and optimize MongoDB queries based on evidence rather than guesswork.
