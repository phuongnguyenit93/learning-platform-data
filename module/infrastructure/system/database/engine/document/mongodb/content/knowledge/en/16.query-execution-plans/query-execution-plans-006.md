# Query Shape, Plan Cache, and Plan Changes Under Shifting Data in MongoDB

A MongoDB query can run fast for weeks and then suddenly slow down even though the application code has not changed at all. The cause does not have to lie in code: document counts grow, field value ratios shift, a new index is added, or a once-suitable query plan now has to read far too much data. To analyze this phenomenon, you need to understand three closely linked concepts:

1. **Query shape:** the structural form of a query, enabling MongoDB to recognize queries sharing similar patterns.
2. **Query plan and plan cache:** how MongoDB picks an execution plan, caches the selected plan, and reuses it on subsequent runs.
3. **Replanning:** the process of re-evaluating or picking a new plan when runtime conditions render the old plan inefficient or when index structures change.

For instance, consider the same query pattern filtering on **status** and sorting by **createdAt**:

~~~javascript
db.orders.find({ status: "NEW" }).sort({ createdAt: -1 });
db.orders.find({ status: "FAILED" }).sort({ createdAt: -1 });
~~~

Both commands use different `status` literals yet share the same structure. If **NEW accounts for 99%** of documents while **FAILED accounts for 1%**, a read strategy optimal for one value may be suboptimal for the other. As data ratios shift, performance can also fluctuate over time.

This lesson focuses on **identifying query shapes, distinguishing plan cache identifiers, understanding plan selection and replacement, and inspecting with `explain()` and `$planCacheStats`**, then building a diagnostic workflow on test data. Examples use **mongosh** plus Java/Spring Data MongoDB applications.

## 1. How Is a MongoDB Query Executed?

When an application sends `find()`, MongoDB must decide how to retrieve the data and order the results. Depending on the query and existing indexes, possible steps include:

- **COLLSCAN:** scans documents in the collection and evaluates the filter.
- **IXSCAN:** traverses entries in an index, possibly paired with **FETCH** to read full documents.
- **SORT:** performs a separate sort when index order does not satisfy the requested sort.
- **LIMIT, PROJECTION, and other stages:** caps document counts, selects returned fields, or handles remaining plan steps.

Example:

~~~javascript
db.orders.find({
  status: "FAILED"
}).sort({
  createdAt: -1
}).limit(20);
~~~

Given the index:

~~~javascript
{ status: 1, createdAt: -1 }
~~~

MongoDB **can** locate the `status` group via the index and read in descending `createdAt` order. Yet if only this exists:

~~~javascript
{ status: 1 }
~~~

the server may use the index to filter and then require a `SORT` step—or choose a different strategy depending on data and cost.

### 1.1. Overall Flow Diagram

~~~text
Application sends filter + sort + projection + options
                           |
                           v
                      Query shape
                           |
                           v
                  Look up plan cache
                     /           \
         Matching plan found     No match / cache unused
                |                        |
                v                        v
        Try cached plan            Planner evaluates
                |                  candidate options
                |                        |
                +-----------+------------+
                            |
                            v
                      Execute query
                            |
                     Runtime feedback
                            |
                  Can be used to evaluate
                     or replan later
~~~

This is a conceptual model, not a rigid sequence every query must pass through verbatim. Some simple queries have only one viable plan, others use different optimizations, and creating/reusing cache entries depends on query type and MongoDB version.

### 1.2. Execution Plan Differs from Query Result

Two different plans can return **the exact same set of documents** at vastly different costs:

~~~text
Plan A: IXSCAN(status) -> FETCH -> SORT(createdAt) -> LIMIT
Plan B: IXSCAN(status, createdAt) -> FETCH -> LIMIT
~~~

With the same filter, both return 20 matching orders. Yet Plan A may have to sort many documents, whereas Plan B can read results already ordered by the index.

**A query returning correct data does not prove it ran efficiently**. To evaluate a plan, inspect index entries/documents examined, `SORT` stages, execution time, and workload characteristics.

## 2. What Is a Query Shape?

A **query shape** is the structural representation of a query. For typical queries, components such as **filter**, **sort**, **projection**, and **collation** play a key role in distinguishing shapes. Query shapes help MongoDB recognize structurally similar queries for planning or observability.

Example:

~~~javascript
// Query A
db.orders.find({
  status: "NEW"
}).sort({ createdAt: -1 });

// Query B
db.orders.find({
  status: "FAILED"
}).sort({ createdAt: -1 });
~~~

Both queries have the same predicate structure on `status` and the same sort on `createdAt`; swapping literal **NEW** for **FAILED** normally keeps the same query shape under standard query planning.

One caveat: **do not assume every literal change always preserves the exact same shape across all versions and operators**. Certain expressions, data types, and edge cases have specific canonicalization/parameterization rules. When precision is required, check the shape identifier reported by the server itself.

### 2.1. Changes That Commonly Produce a Different Shape

Compare:

~~~javascript
// Shape S1: equality on status, sort createdAt DESC
db.orders.find({ status: "NEW" })
  .sort({ createdAt: -1 });

// Shape S2: adds region predicate
db.orders.find({ status: "NEW", region: "APAC" })
  .sort({ createdAt: -1 });

// Shape S3: sorts by total instead of createdAt
db.orders.find({ status: "NEW" })
  .sort({ total: -1 });

// Shape S4: adds projection
db.orders.find(
  { status: "NEW" },
  { _id: 0, status: 1, total: 1 }
).sort({ createdAt: -1 });

// Shape S5: range predicate on createdAt
db.orders.find({
  status: "NEW",
  createdAt: { $gte: ISODate("2026-10-01T00:00:00Z") }
}).sort({ createdAt: -1 });
~~~

S2 adds a predicate, S3 changes the sort key, S4 changes the projection, and S5 adds a range predicate. These changes can yield distinct shapes compared to S1.

### 2.2. Query Shape Is Not Literal Query Text

Two differently formatted JavaScript calls:

~~~javascript
db.orders.find({ status: "NEW" });

db.orders.find({
  status: { $eq: "NEW" }
});
~~~

express the exact same equality comparison logically. MongoDB normalizes expressions before planning. However, **never write your own JSON string hash of a query and treat it as the server's query shape**: server canonicalization depends on operators and server versions.

### 2.3. Query Shape Alone Does Not Determine Performance

Two runs with the same shape can differ in:

- **Parameter values**: one status is ubiquitous, another is rare.
- **Data volume and distribution**: matching document count grows or shrinks.
- **Available indexes**: creating/dropping indexes alters eligible plans.
- **Resource state**: memory cache, I/O, CPU, concurrent queries.
- **Execution timing and whether underlying data changed**.

Shapes group structurally similar queries, yet do not guarantee identical cost or optimal plans under all circumstances.

## 3. What Is the Plan Cache?

The **plan cache** stores information about selected query plans for certain query shapes so MongoDB can reuse them, cutting the overhead of re-evaluating multiple candidates on subsequent executions.

If a query is invoked frequently:

~~~javascript
db.orders.find({
  status: "FAILED",
  region: "APAC"
}).sort({ createdAt: -1 });
~~~

having candidate indexes compete on every request would add needless overhead. The plan cache lets MongoDB reuse an evaluated plan when appropriate.

**The plan cache is not a result cache.** It does not pre-store lists of returned orders; documents are still read against current data state on every query.

| Concept | What It Stores / Provides | What Is Not Guaranteed |
|---|---|---|
| Query shape | Structure identifying a query class | Does not tell how many documents will match |
| Query plan | Stages/strategy for accessing data | Not guaranteed to stay fastest after data changes |
| Plan cache | Selected plan info kept for reuse | Does not cache query results or persist forever |
| Result set | Documents actually returned on a run | Does not stay static if data changes |

### 3.1. The Plan Cache Is Runtime State, Not a Permanent Contract

The plan cache is a server-side optimization mechanism that resets on process restarts, index creation/deletion, environment changes, or memory eviction policies. It is not an application artifact to back up across deployments.

In a multi-`mongod` deployment, cache state can differ across nodes. Thus, inspecting the cache on one node does not automatically represent every node in the deployment.

### 3.2. Why Is the First Query Sometimes Slower?

When no cached plan is available, the query planner may have to race multiple **candidate plans** before picking the best one. That trial phase adds extra work compared to using an already selected plan.

However, a slower first run can also occur because data/indexes are not yet warm in the OS or storage engine cache. **Never look at one cold run and blame the entire difference on the plan cache**.

## 4. Shape Identifiers and Plan Cache Identifiers

In MongoDB diagnostic outputs, you may encounter identifiers like **queryHash**, **planCacheShapeHash**, and **planCacheKey**. Do not treat them as synonyms.

| Identifier | Conceptual Purpose | Key Point |
|---|---|---|
| `queryHash` | Identifier tied to query shape in earlier outputs/versions | Does not describe current indexes on its own |
| `planCacheShapeHash` | Hash of the query shape in supporting versions | Introduced in MongoDB 8.0; may appear alongside `queryHash` for compatibility |
| `planCacheKey` | Cache entry/plan identifier derived from shape **and** available indexes | Can change when available indexes change even if the shape stays identical |

Conceptual example:

~~~text
Query shape:
  filter: status = ?
  sort: createdAt DESC

Time A: collection has index {status:1}
  shape hash:     S
  plan cache key: K1

Time B: add index {status:1, createdAt:-1}
  shape hash:     S
  plan cache key: K2 (may change)
~~~

**Do not try to compute specific hash values yourself from a filter string.** MongoDB computes identifiers per its server implementation. When analyzing logs/profiler output, use the exact fields reported by the server rather than concatenating queries and hashing them yourself.

### 4.1. Query Shape and `planCacheKey` Answer Two Different Questions

- **Shape hash:** "Which structural class of query is this?"
- **Plan cache key:** "Which structural class of query is this within the context of currently available indexes for plan selection?"

When comparing before/after creating an index, do not see `planCacheKey` change and conclude the application changed its filter/sort. The app may be sending the exact same shape while the set of indexes changed.

### 4.2. Does the Same Shape Guarantee the Same Plan?

No. A query might bypass cache entries, an entry might be evicted, a plan might be replanned, or environments/indexes might differ. Even within one environment, the plan can change when the server detects performance is no longer satisfactory.

Moreover, special cases like **`hint`**, certain expressions, or other optimizer rules affect plan selection. Thus, **shape is a useful unit of observation**, not a guarantee that every execution follows one immutable plan.

## 5. How Is a Query Plan Selected and Reused?

When multiple indexes are eligible, MongoDB can generate **candidate plans**, trial-execute them over a bounded portion of work, and select one per query planner criteria. Metadata for that selection can be retained in the plan cache.

Suppose the collection has:

~~~javascript
db.orders.createIndex({ status: 1 });
db.orders.createIndex({ createdAt: -1 });
db.orders.createIndex({ status: 1, createdAt: -1 });
~~~

For the query:

~~~javascript
db.orders.find({
  status: "FAILED"
}).sort({ createdAt: -1 }).limit(20);
~~~

strategies considered depending on data and version might include:

~~~text
Candidate A
  IXSCAN(status)
      -> FETCH matching documents
      -> SORT(createdAt DESC)
      -> LIMIT(20)

Candidate B
  IXSCAN(createdAt DESC)
      -> FETCH/check status
      -> stop once 20 results found

Candidate C
  IXSCAN(status, createdAt DESC)
      -> FETCH matching documents
      -> LIMIT(20)
~~~

Do not treat those three diagrams as guaranteed **`winningPlan`** trees. MongoDB may choose a different plan or represent stages differently, especially across execution engines and versions.

### 5.1. What Determines a Good Option?

Factors commonly affecting cost:

- **Selectivity:** how many documents the filter eliminates.
- **Cardinality:** how many distinct values exist, or how many records share one value.
- **Sort:** whether an index delivers the needed order or a separate sort is required.
- **Limit:** whether only the top 20 or all 500,000 documents are needed.
- **Projection:** whether source documents must be fetched.
- **Document and index size**, data traits, RAM cache, I/O, and concurrency.

An index solely on `status` can shine when `status` is rare. If `status` matches most of the collection, scanning the index and FETCHing nearly every document may lose to another strategy.

### 5.2. Cached Plan Usage vs. "Replanning Every Time"

Once a suitable plan is cached, subsequent runs with the same shape can reuse it without racing every candidate again. That cuts planning overhead, yet introduces a key trade-off: **a once-good plan can become suboptimal when data changes**.

### 5.3. Cache States to Know

Within the cache mechanism exist conceptual states such as:

| State | Meaning |
|---|---|
| **Missing** | No corresponding cache entry exists yet |
| **Inactive** | Candidate/plan info exists, but is not yet treated as an actively reused cache entry |
| **Active** | Entry is eligible for plan reuse |

MongoDB has specific rules for transitioning states based on execution feedback and work counters. Exact progression and displayed fields vary by version and engine; never assume **running a query exactly twice guarantees the cache entry is Active**.

Some query shapes may never create an entry as expected because only one viable plan exists or due to cache policies. **Not seeing an entry does not mean the query failed**.

## 6. Why Does Data Distribution Change Performance?

Suppose a system has one million orders:

| status | Count | Share |
|---|---:|---:|
| NEW | 990,000 | 99% |
| FAILED | 10,000 | 1% |

Two queries:

~~~javascript
db.orders.find({ status: "NEW" });
db.orders.find({ status: "FAILED" });
~~~

share identical structure, yet the number of matching documents differs enormously. With a `status` index, `FAILED` scans a narrow slice, while `NEW` must touch nearly the entire collection.

### 6.1. Skew: When Data Distribution Is Heavily Imbalanced

**Data skew** means different values of the same field appear at wildly different frequencies. Common examples:

- `status`: `NEW`/`PAID`/`CANCELLED`/`FAILED`.
- `tenantId`: one huge tenant alongside many tiny tenants.
- `category`: one dominant category.
- `region`: primary hub vs. low-volume regions.
- `isDeleted`: `false` on almost everything, `true` on a tiny fraction.

Queries for rare values vs. common values can have vastly different costs even when grouped under the same query shape.

### 6.2. Distribution Can Shift Over Time

For example, start of the month:

~~~text
NEW:    99%
FAILED:  1%
~~~

After an incident:

~~~text
NEW:    40%
FAILED: 60%
~~~

A plan that worked great when `FAILED` was rare may suddenly read far more records when `FAILED` becomes common. **Zero query code changes are needed** for this to happen; data shift alone suffices.

Likewise, growing document counts, deletions of old data, changing array lengths, and shifting sort value distributions can all alter costs.

### 6.3. Same Shape Does Not Mean Same Selectivity

When grouping queries by shape for analysis, also inspect **literals or value buckets with differing selectivity**. Looking only at average shape latency lets fast queries on small tenants mask slow queries on large tenants.

That does not mean dumping sensitive values into logs. You can use workload labels, tenant size tiers, or sanitized aggregate metrics.

## 7. When Does MongoDB Replan?

**Replanning** is when the server re-evaluates plan selection instead of continuing to trust the old cached plan. MongoDB detects when a cached plan performs substantially more work than expected and can trigger replanning.

Exact mechanics depend on MongoDB version and query engine. Practically, distinguish two root causes:

### 7.1. Data Changes While Indexes Stay Fixed

Suppose `FAILED` grows from 1% to 60%:

~~~text
Before:
  Same query shape
  Cached plan fits a small result set

After:
  Query shape unchanged
  Indexes unchanged
  Matching record count surges
  Old plan may have to read far more data
~~~

MongoDB **can** detect the old plan is underperforming and replan. Never assert every data ratio shift triggers an instant replan on the very next execution. A query may keep using the old plan until specific evaluation/invalidation thresholds are met, and a slowdown does not automatically mean the server changed plans.

### 7.2. Creating or Dropping an Index

When adding an index:

~~~javascript
db.orders.createIndex({ status: 1, createdAt: -1 });
~~~

MongoDB gains a new access path. Creating or dropping an index can invalidate existing collection plan cache entries per cache management rules. **`planCacheKey` may change** because the set of available indexes changed.

When investigating before/after a deployment, check index change history—not just query changes in code.

### 7.3. Other Changes Affecting Plan Selection

Depending on server and query type, changes to:

- Query **collation**.
- **Projection, sort, or filter predicates**.
- **Hidden/unhidden indexes**.
- **Query settings, `hint`, or planning options**.
- **Restarts or failovers** resetting runtime cache state.

can cause the server to pick a different execution strategy or stop reusing an old entry.

**Do not confuse plan cache changes with result changes.** A logically valid query must still return documents matching its filter/sort; plan changes primarily alter execution path, performance, and non-deterministic tie order when sort is omitted.

## 8. Replanning Cannot Fix Every Slow Query

If only a poor index exists—or no helpful index exists at all—replanning cannot conjure a good index out of thin air.

Example:

~~~javascript
db.orders.find({
  tenantId: "tenant-large",
  status: "PAID"
}).sort({
  createdAt: -1
});
~~~

If the app routinely filters by `tenantId` + `status` and sorts by `createdAt`, consider the index:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
~~~

An index matching equality filters and sort order matters far more than waiting for replanning to work around missing indexes.

### 8.1. Do Not Treat Every Plan Change as a Bug

Switching from `COLLSCAN` to `IXSCAN`, or vice versa, is not always a regression. If data shrinks, a collection scan can beat traversing an index and fetching many documents. If data grows huge while the filter stays selective, `IXSCAN` usually wins.

Judge by **actual cost of the query pattern** and latency requirements, not by stage names alone.

### 8.2. Factors That Slow Queries Even When the Plan Is Unchanged

- Concurrent CPU/I/O contention.
- Working set data/indexes evicted from memory cache.
- Larger documents than before.
- Slow or degraded network path to MongoDB.
- Larger result sets because fewer documents are filtered out.
- App switching from a narrow projection to fetching full documents.

Therefore, plan cache analysis is only one piece of an end-to-end latency investigation.

## 9. Setting Up a `mongosh` Lab to Observe Query Plans

For hands-on practice, connect `mongosh` to a MongoDB instance with permission to create collections/indexes in a test database:

~~~javascript
use query_plan_lab
~~~

Create the **`orders`** collection with a small dataset for verifying logic. Run the insert once when the collection does not yet contain those `_id` values:

~~~javascript
db.orders.insertMany([
  {
    _id: "O01", status: "NEW", tenantId: "T-A",
    totalCents: 12000,
    createdAt: ISODate("2026-10-01T08:00:00Z")
  },
  {
    _id: "O02", status: "NEW", tenantId: "T-A",
    totalCents: 7500,
    createdAt: ISODate("2026-10-02T08:00:00Z")
  },
  {
    _id: "O03", status: "FAILED", tenantId: "T-A",
    totalCents: 13500,
    createdAt: ISODate("2026-10-03T08:00:00Z")
  },
  {
    _id: "O04", status: "NEW", tenantId: "T-A",
    totalCents: 19900,
    createdAt: ISODate("2026-10-04T08:00:00Z")
  },
  {
    _id: "O05", status: "PAID", tenantId: "T-B",
    totalCents: 39900,
    createdAt: ISODate("2026-10-05T08:00:00Z")
  },
  {
    _id: "O06", status: "NEW", tenantId: "T-A",
    totalCents: 14900,
    createdAt: ISODate("2026-10-06T08:00:00Z")
  },
  {
    _id: "O07", status: "FAILED", tenantId: "T-B",
    totalCents: 9900,
    createdAt: ISODate("2026-10-07T08:00:00Z")
  },
  {
    _id: "O08", status: "NEW", tenantId: "T-B",
    totalCents: 8800,
    createdAt: ISODate("2026-10-08T08:00:00Z")
  },
  {
    _id: "O09", status: "NEW", tenantId: "T-A",
    totalCents: 6400,
    createdAt: ISODate("2026-10-09T08:00:00Z")
  },
  {
    _id: "O10", status: "PAID", tenantId: "T-A",
    totalCents: 21000,
    createdAt: ISODate("2026-10-10T08:00:00Z")
  },
  {
    _id: "O11", status: "NEW", tenantId: "T-A",
    totalCents: 8600,
    createdAt: ISODate("2026-10-11T08:00:00Z")
  },
  {
    _id: "O12", status: "NEW", tenantId: "T-B",
    totalCents: 7400,
    createdAt: ISODate("2026-10-12T08:00:00Z")
  }
])
~~~

Verify:

~~~javascript
db.orders.countDocuments({})

db.orders.aggregate([
  { $group: { _id: "$status", count: { $sum: 1 } } },
  { $sort: { count: -1, _id: 1 } }
])
~~~

With this sample data: **NEW = 8, FAILED = 2, PAID = 2**. A 12-document dataset only serves to learn syntax; **it is too small to infer whether a production planner will pick IXSCAN or COLLSCAN**.

### 9.1. Creating Multiple Index Options

~~~javascript
db.orders.createIndex(
  { status: 1 },
  { name: "idx_status" }
);

db.orders.createIndex(
  { createdAt: -1 },
  { name: "idx_created_desc" }
);

db.orders.createIndex(
  { status: 1, createdAt: -1 },
  { name: "idx_status_created_desc" }
);
~~~

These three indexes give the planner multiple access paths. Sample query:

~~~javascript
db.orders.find({
  status: "FAILED"
}).sort({
  createdAt: -1
}).limit(5);
~~~

On this seed data, the logical output is **O07 then O03**. Which index/plan gets picked must be observed directly from the server, not assumed just from the number of indexes.

### 9.2. Which Index Fits Filter and Sort?

| Index | Primary Capability | Point to Weigh |
|---|---|---|
| `{status:1}` | Filters by status | Sorting `createdAt` may require a separate step |
| `{createdAt:-1}` | Provides chronological order | May have to inspect many non-matching statuses |
| `{status:1,createdAt:-1}` | Filters `status` then reads `createdAt` descending | Typically suits equality filter + sort pattern |

These are **structural capabilities**. If a query returns nearly the whole collection or the collection is tiny, the fastest plan may differ from expectations.

## 10. Using `explain()` to See How a Query May Run

`explain()` reveals the plan built by the query planner and, in the right mode, execution metrics:

~~~javascript
db.orders.find({
  status: "FAILED"
}).sort({
  createdAt: -1
}).limit(5).explain("executionStats");
~~~

The actual output contains multiple sections. Look for:

| Field / Stage | Guiding Question |
|---|---|
| `winningPlan` | Which plan was chosen? |
| `IXSCAN` | Is an index scan used? |
| `COLLSCAN` | Is the entire collection scanned? |
| `SORT` | Is there a separate sort step? |
| `FETCH` | Must source documents be retrieved? |
| `indexName` | Which index is scanned? |
| `totalKeysExamined` | How many index entries were traversed? |
| `totalDocsExamined` | How many documents were read/inspected? |
| `nReturned` | How many documents did the query return? |
| `executionTimeMillis` | Timing reported for this explain run |

**Important note:** **`explain()` ignores existing plan cache entries and does not insert new entries into the cache**. It is great for studying how the planner evaluates a query, yet **does not directly prove which cached plan a live production request just used**.

Some versions use structures like **`queryPlanner.winningPlan.queryPlan`** or engine-specific stages. Never hardcode parsing logic on one fixed stage path without checking your server version and real output.

### 10.1. Three Common Explain Modes

~~~javascript
db.orders.find({ status: "FAILED" })
  .explain("queryPlanner");

db.orders.find({ status: "FAILED" })
  .explain("executionStats");

db.orders.find({ status: "FAILED" })
  .explain("allPlansExecution");
~~~

High-level meaning:

- **`queryPlanner`:** info on the selected plan and candidates within display scope.
- **`executionStats`:** execution statistics for the winning plan.
- **`allPlansExecution`:** adds trial-phase statistics for evaluated candidates when available.

Not every output includes full stats for multiple candidates. Candidate counts and detail depend on query structure, version, engine, and applied optimizations.

### 10.2. Testing a Specific Index with `hint()`

To compare two index options on the same filter:

~~~javascript
db.orders.find({ status: "FAILED" })
  .sort({ createdAt: -1 })
  .hint("idx_status")
  .explain("executionStats");

db.orders.find({ status: "FAILED" })
  .sort({ createdAt: -1 })
  .hint("idx_status_created_desc")
  .explain("executionStats");
~~~

Inspect **`SORT`**, **`keys/docs examined`**, and other stages to understand cost. **`hint()` forces using the specified index**, making it a way to compare access options—not proof the query planner will pick that option on its own in production.

Never ship `hint` into application code by default without measurements and an index maintenance strategy; forcing an index can backfire when data shifts.

### 10.3. Avoid Reading `executionTimeMillis` as an Absolute Benchmark

Duration on a single explain run is affected by data cache, system load, document count, disk I/O, and many variables. Comparisons in a tiny lab can yield noisy numbers.

For realistic evaluation, run repeated measurements on representative data, check **keys/docs examined per `nReturned`**, inspect the plan, and monitor application latency under equivalent load.

## 11. Inspecting the Plan Cache with `$planCacheStats`

MongoDB provides the **`$planCacheStats`** aggregation stage to view entries in a collection's plan cache when supported by deployment, version, and user privileges.

~~~javascript
db.orders.aggregate([
  { $planCacheStats: {} }
])
~~~

Depending on version, output can contain fields such as **`planCacheKey`**, **`planCacheShapeHash`** or **`queryHash`**, **`isActive`**, **`works`**, **`cachedPlan`**, **`createdFromQuery`**, and host/engine info. Do not assume every version returns identical fields.

### 11.1. Projecting Only Needed Diagnostic Fields

~~~javascript
db.orders.aggregate([
  { $planCacheStats: {} },
  {
    $project: {
      _id: 0,
      planCacheKey: 1,
      planCacheShapeHash: 1,
      queryHash: 1,
      isActive: 1,
      works: 1,
      createdFromQuery: 1
    }
  }
])
~~~

**`$planCacheStats` must be the first stage in the pipeline** in typical usage like this example. Fields absent from your server version's output simply will not appear after `$project`.

### 11.2. What If No Entry Appears?

Possible reasons:

- The query was just run and has not yet met the conditions for caching an entry.
- The query planner did not need to race multiple plans for that shape.
- The cache was invalidated/evicted, or the server recently restarted.
- You are inspecting the plan cache on a different node than the one that ran the query.
- The query/operation used a planning path that does not populate cache entries as expected.

Hence, **an empty plan cache does not prove indexes are ignored**, and **an active cache entry does not prove a query is fast**.

### 11.3. Never Use `explain()` to "Warm Up" the Plan Cache

This is a common mistake:

~~~javascript
// Surveys planner; does not warm up the cache.
db.orders.find({
  status: "FAILED"
}).sort({
  createdAt: -1
}).explain("executionStats");
~~~

To observe plan cache creation/reuse under eligible conditions, **execute the normal query** so the driver/`mongosh` actually consumes results:

~~~javascript
for (let i = 0; i < 5; i++) {
  db.orders.find({
    status: "FAILED"
  }).sort({
    createdAt: -1
  }).toArray();
}

db.orders.aggregate([
  { $planCacheStats: {} }
]);
~~~

This snippet uses only 12 documents, so `toArray()` poses no memory risk. However, **running five times does not guarantee an Active entry will appear**; results also depend on planner, engine, and indexes.

### 11.4. Which Node's Plan Cache?

In a replica set, each **`mongod`** maintains its own query execution, resources, and plan cache. When multiple nodes serve reads, the same shape can hit nodes with different cache/runtime states.

In a sharded environment, you also need to know how the router and individual shards handle the query. Never read metrics from one node and declare it the sole state of the entire deployment.

## 12. Practicing Heavily Skewed Data on a Dedicated Collection

A 12-document dataset is handy for checking results, yet far too small for studying data skew. Create a separate **`skewOrders`** collection with 5,000 documents. Never run this test on production; use a lab database and ensure sufficient storage.

### 12.1. Creating 4,900 `NEW` and 100 `FAILED`

In `mongosh`:

~~~javascript
use query_plan_lab

const total = 5000;
const chunkSize = 500;

for (let start = 1; start <= total; start += chunkSize) {
  const batch = [];
  const end = Math.min(start + chunkSize - 1, total);

  for (let i = start; i <= end; i++) {
    batch.push({
      _id: "S-" + String(i).padStart(5, "0"),
      seq: i,
      status: i <= 4900 ? "NEW" : "FAILED",
      tenantId: i % 10 === 0 ? "T-small" : "T-large",
      totalCents: 1000 + (i % 200) * 100,
      createdAt: new Date(
        Date.UTC(2026, 9, 1) + i * 60 * 1000
      )
    });
  }

  db.skewOrders.insertMany(batch);
}
~~~

Run **once** on a collection without these `_id` values. Re-running triggers duplicate key errors; never drop/overwrite real data for experiments.

Distribution check:

~~~javascript
db.skewOrders.aggregate([
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
])
~~~

Expected result:

| status | Documents | Share |
|---|---:|---:|
| NEW | 4,900 | 98% |
| FAILED | 100 | 2% |

This set is still small compared to production, yet clearly demonstrates the gap between a common value and a rare value.

### 12.2. Creating Indexes with Different Strategies

~~~javascript
db.skewOrders.createIndex(
  { status: 1 },
  { name: "idx_skew_status" }
);

db.skewOrders.createIndex(
  { createdAt: -1 },
  { name: "idx_skew_created" }
);

db.skewOrders.createIndex(
  { status: 1, createdAt: -1 },
  { name: "idx_skew_status_created" }
);
~~~

Two structurally similar queries:

~~~javascript
// Very common value
db.skewOrders.find({
  status: "NEW"
}).sort({ createdAt: -1 }).limit(20);

// Rare value
db.skewOrders.find({
  status: "FAILED"
}).sort({ createdAt: -1 }).limit(20);
~~~

Both share the same structural filter and sort. Yet evaluated **without a limit**, `NEW` returns 4,900 documents while `FAILED` returns 100. With `limit(20)`, both can stop once 20 matches are found, making cost differences depend heavily on indexes and `createdAt` distribution.

### 12.3. Comparing Plans with `explain()`

~~~javascript
db.skewOrders.find({
  status: "NEW"
}).sort({
  createdAt: -1
}).limit(20).explain("executionStats");

db.skewOrders.find({
  status: "FAILED"
}).sort({
  createdAt: -1
}).limit(20).explain("executionStats");
~~~

Inspect:

- **Is there a separate `SORT`?**
- **Which index or `COLLSCAN` did `winningPlan` choose?**
- **How do `totalKeysExamined` and `totalDocsExamined` differ?**
- **Is `nReturned` 20 in both?**
- **If multiple candidates exist, what does `allPlansExecution` reveal?**

**Important:** These two explain calls compare **fresh planner decisions on specific values**, not direct proof that two normal runs used the same cache entry.

### 12.4. Shifting Distribution Without Changing Query Shape

In the **test-only `skewOrders` collection**, flip the first 3,000 documents from `NEW` to `FAILED`:

~~~javascript
db.skewOrders.updateMany(
  {
    status: "NEW",
    seq: { $lte: 3000 }
  },
  {
    $set: { status: "FAILED" }
  }
)
~~~

After the update:

~~~javascript
db.skewOrders.aggregate([
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  }
])
~~~

Expected distribution:

| status | Documents | Share |
|---|---:|---:|
| NEW | 1,900 | 38% |
| FAILED | 3,100 | 62% |

Filter and sort in code are untouched, yet **the data ratio of each status flipped dramatically**.

### 12.5. Re-Inspecting After the Shift

~~~javascript
db.skewOrders.find({
  status: "FAILED"
}).sort({
  createdAt: -1
}).limit(20).explain("executionStats");

db.skewOrders.aggregate([
  { $planCacheStats: {} },
  {
    $project: {
      _id: 0,
      planCacheKey: 1,
      planCacheShapeHash: 1,
      queryHash: 1,
      isActive: 1,
      works: 1
    }
  }
])
~~~

With the same query predicates, consider:

1. Which value is now more common?
2. Does the query need to read more documents than before?
3. If `winningPlan` changed, **was it due to distribution, indexes, or runtime conditions**?
4. If `winningPlan` stayed the same, can performance still change?
5. Can you prove the cache replanned using `explain()` alone? **No.**

This experiment does not guarantee the query planner always switches plans. A good compound index may remain optimal under both distributions, especially when only 20 results are needed. The purpose is learning **how to form hypotheses and gather evidence**, not forcing the server to switch plans.

### 12.6. Status Distribution Also Impacts Writes

When data flips from mostly `NEW` to mostly `FAILED`, indexes must be updated for every document whose status changed. That adds **write overhead**. In a real system, updating thousands or millions of documents consumes significant resources; never run broad `updateMany` operations without evaluating production impact.

## 13. Observing the Plan Cache Before and After Index Changes

Changing indexes can alter **`planCacheKey`** without changing the query shape. Use a separate test collection to illustrate.

Example before adding an index:

~~~javascript
db.skewOrders.find({
  status: "FAILED"
}).sort({
  createdAt: -1
}).limit(20).toArray();
~~~

Inspect cache if supported:

~~~javascript
db.skewOrders.aggregate([
  { $planCacheStats: {} }
])
~~~

Add a candidate index tailored to a new query pattern:

~~~javascript
db.skewOrders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_tenant_status_created" }
);
~~~

Run the query:

~~~javascript
db.skewOrders.find({
  tenantId: "T-small",
  status: "FAILED"
}).sort({
  createdAt: -1
}).limit(20).toArray();
~~~

Then inspect `$planCacheStats` again. When an index is created, older cache entries may be invalidated and new entries use a **`planCacheKey`** reflecting the current index set.

**Never conclude the shape hashes of the two different queries above must match**: the query with `tenantId` and the one without `tenantId` are two distinct shapes. To compare hashes before/after an index change, run **the exact same filter + sort + projection** at both times without changing the query pattern mid-test.

### 13.1. Distinguishing Index Changes from Data Changes

| Operation | Query Shape of Same Query | Plan Cache / `planCacheKey` |
|---|---|---|
| Growing docs, shifting status ratios | Typically unchanged | Not automatically invalidated at once; performance may shift, may replan |
| Creating a new index | Query shape unchanged | Eligible index set changes; entries may invalidate and key may change |
| Dropping an index | Query shape unchanged | Plans using old index become invalid; cache must adapt |
| Changing filter or sort in app | May become a different shape | May use a separate entry |
| Restarting a node | Logical query shape unchanged | Runtime cache is not preserved |

That is why debugging "a query that suddenly got slow" requires checking **both data shifts and index/deployment history**.

## 14. When Should You Clear the Plan Cache?

MongoDB provides administrative commands to clear plan cache entries when necessary. In `mongosh`, a common method in supported versions is:

~~~javascript
// Use only in lab environments or under an approved operational runbook.
db.skewOrders.getPlanCache().clear();
~~~

Or the corresponding database command:

~~~javascript
db.runCommand({
  planCacheClear: "skewOrders"
});
~~~

Clearing the plan cache **does not delete documents, does not drop indexes, and does not change application query shapes**. It simply forces subsequent runs to replan instead of using older cached entries.

### 14.1. Do Not Use Cache Clearing as a Default Quick Fix

If a query lacks a proper index or data ratios shifted, clearing the cache might temporarily help a few cases yet **fails to fix the root cause**. Subsequent runs also incur replanning overhead.

Only touch the cache once you understand the impact and have a concrete reason—such as controlled query experiments, following an incident runbook, or clearing a confirmed pathological cache state.

**Never clear caches across production nodes blindly** just because latency spiked. Across multiple nodes, identify the specific node/collection and assess impact on other workloads.

### 14.2. `hint` Is a Different Kind of Intervention

~~~javascript
db.skewOrders.find({
  status: "FAILED"
}).sort({
  createdAt: -1
}).hint("idx_skew_status_created");
~~~

**`hint`** mandates using the named index; it can help diagnose or mitigate special cases, yet couples the app to that index. If the index is dropped/hidden or data distribution shifts, the hint can error out or slow queries down.

In supporting MongoDB versions, **query settings** allow governing certain query shape behaviors administratively; this is an advanced operational feature requiring version and privilege checks. Do not confuse query settings with manually editing a single plan cache entry.

## 15. Investigation Workflow When a Query Shape Suddenly Slows Down

Suppose an endpoint used to respond quickly, and latency spikes after a bulk data import. Instead of clearing the plan cache immediately, follow this workflow.

### Step 1. Identify the Exact Query Being Executed

Record:

- Collection and database.
- Filter and **BSON types** of values.
- Sort, projection, limit, skip, collation.
- Existing index names.
- MongoDB version, deployment topology, and serving node(s).
- Call rate, before/after latency, and returned document counts.

Example:

~~~javascript
db.orders.find(
  {
    tenantId: "T-A",
    status: "NEW"
  },
  {
    _id: 1,
    createdAt: 1,
    totalCents: 1
  }
).sort({
  createdAt: -1
}).limit(50);
~~~

**Never omit projection or limit** when reproducing a query. Altering them can change query shape/plan, making test results diverge from production requests.

### Step 2. Group by Shape While Checking Skewed Values

Two requests can share a shape:

~~~javascript
{ tenantId: "T-A", status: "NEW" }
{ tenantId: "T-B", status: "NEW" }
~~~

yet tenant `T-A` may hold millions of documents while `T-B` holds hundreds. Compare selectivity and request frequency across value buckets, not just average shape latency.

In multi-tenant datasets, always preserve **`tenantId` in filters and appropriate indexes** where security/data isolation dictates. Never strip tenant filters just to benchmark faster.

### Step 3. Inspect Data Distribution

On modest collections or test environments:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
~~~

On massive production collections, full-collection aggregations for stats can be expensive. Prefer existing metrics, analytics stores, or scheduled audits rather than running unbounded `$group` queries during peak load.

### Step 4. Check Indexes and Deployment History

~~~javascript
db.orders.getIndexes();
~~~

Verify whether an index was recently created, dropped, hidden/unhidden, or changed collation. If a query switched indexes after a release, index changes are a prime suspect.

For compound indexes, check **field order** and **equality + sort + range**. Simply seeing a field in an index does not prove the index supports both filter and sort.

### Step 5. Use `explain()` to Analyze Current Options

~~~javascript
db.orders.find({
  tenantId: "T-A",
  status: "NEW"
}).sort({
  createdAt: -1
}).limit(50).explain("executionStats");
~~~

Inspect `winningPlan`, `SORT` stages, keys/docs examined, and `nReturned`. To compare two indexes, use targeted `hint` calls in a test environment.

Remember that **`explain` does not directly reflect which cached plan normal runs used**. For runtime evidence and replanning proof, combine profiler/logs/APM and `$planCacheStats` per server version.

### Step 6. Inspect Cache and Normal Executions

~~~javascript
db.orders.aggregate([
  { $planCacheStats: {} },
  {
    $project: {
      _id: 0,
      planCacheKey: 1,
      planCacheShapeHash: 1,
      queryHash: 1,
      isActive: 1,
      works: 1
    }
  }
]);
~~~

If an entry is absent, do not assume the cache is broken. If an Active entry exists, do not automatically conclude the specific slow query used it; match shape/key and host/request.

### Step 7. Pick a Fix Matching the Root Cause

| Root Cause Found | Remediation Direction |
|---|---|
| Missing suitable index | Consider creating a compound index matching filter/sort |
| High data skew | Evaluate query patterns and skewed values; consider targeted indexes/model adjustments |
| Result set grew too large | Bound returned data, paginate, refine projection |
| Sort not using index | Revisit key order and index direction |
| Cached/old plan genuinely harmful | Evaluate replanning and controlled intervention if needed |
| Resource bottleneck | Investigate CPU/I/O/memory, concurrency, network |
| Query changed in code | Review shape, projection, sort, collation, and indexes |
| Nodes show differing performance | Inspect routing, data, cache, and per-node config |

### Step 8. Monitor After Making Changes

After creating an index or modifying a query, re-measure:

- **p50, p95, p99 latency** of the endpoint/query pattern.
- **`nReturned`** and examined keys/docs ratios.
- **Insert/update throughput** and index storage footprint.
- **Plan change/replanning frequency** if observability tools expose it.
- **Query behavior across all nodes**, not just one tested instance.

The ultimate goal is steady performance under real workloads, not a pretty one-off explain.

## 16. Profiling, Logs, and APM: Separating Observation from Intervention

During real incident response, server logs, the profiler, and APM telemetry often outweigh manual `explain` runs. Depending on MongoDB version, logs/profiler entries can include query shape, plan cache identifiers, chosen plans, keys/docs read, or replanning flags.

### 16.1. Do Not Enable Full Profiling Recklessly

The profiler adds overhead and stores query data inside the database. In production, verify security policies, access controls, and performance cost before raising profiling levels or lowering slow-op thresholds.

Profiler entries may capture filter literals or sensitive values depending on configuration. Restrict access and handle data per security policy; never paste raw customer queries into public chats for debugging.

### 16.2. Use Driver Command Monitoring When Appropriate

MongoDB drivers emit command monitoring events, letting applications track commands sent to the server. This helps confirm the exact `find()`/`getMore` calls, per-command timing, errors, and request correlation.

Yet **command monitoring does not replace query planner metrics**; it complements them with client/driver timing. When breaking down latency:

~~~text
API Latency
  = validation + business logic time
  + connection pool wait time
  + network + MongoDB server execution
  + BSON decoding + serialization
  + data post-processing and response write
~~~

If total API time climbs while DB keys/docs examined stay flat, the slowdown may lie outside the query plan.

### 16.3. Detecting Replans via Server Signals

Some MongoDB versions log diagnostic fields indicating a plan was replanned or explaining replan reasons. Log format, field names, and enabling flags depend on version; never write tooling demanding one hardcoded log string across every deployment.

When reporting a plan change incident, capture at least:

1. Query shape or corresponding identifier.
2. Before/after index and plan, if evidenced.
3. Data distribution and timestamp of the shift.
4. Keys/docs examined and before/after latency.
5. Concurrent index, deployment, or topology changes.

A single `explain` snapshot cannot prove which cached plan the server replanned away from.

## 17. Limitations and Edge Cases to Remember

### 17.1. Query Shape Is Not a Full Copy of the Command

A `find` command carries many options. Not every option participates in query shape identity identically across every version and context. **Filter, sort, projection, and collation** are core factors, while special operators, aggregation pipelines, literals, and query settings follow specific rules.

To conclude "two requests share the same shape," rely on identifiers reported by your MongoDB version rather than comparing JSON strings in application code.

### 17.2. The Plan Cache Is Not a Complete Historical Log

`$planCacheStats` shows currently cached entries, not a permanent audit log of every plan ever selected. Entries vanish on restarts, invalidations, evictions, and other events.

To study multi-day regressions, store metrics and observations in a proper time-series monitoring system with clear retention and security policies.

### 17.3. Aggregation Pipelines Have Diverse Execution Forms

Not every aggregation pipeline is optimized and cached like a simple `find`. Stages can be pushed down, reordered, or run on different engines; some stages are blocking, memory-heavy, or unable to use indexes as expected.

Therefore, when studying **aggregation plan caching**, use explain and observability tools suited to that specific pipeline. Never mechanically transfer every `find()` rule onto complex pipelines.

### 17.4. Sharding Introduces Multi-Tier Decisions

In a sharded cluster, a query routes through `mongos` to one or more shards and merges results. Each shard can choose a different query plan due to indexes, data distribution, or cache state.

An identical shape does not mean identical cardinality on every shard. **A large tenant concentrated on one shard** can behave very differently from small tenants or scatter-gather requests.

### 17.5. Cache and Query Settings Serve Different Roles

The plan cache stores chosen plans for reuse under runtime policies. Query settings on supporting versions provide administrative control over query behavior; they are not merely pinning a raw cached plan entry.

If an app needs controlled index behavior, verify version compatibility, permissions, and operational policies before applying `hint` or query settings. Forcing an index at the wrong moment can make performance regressions harder to untangle.

## 18. Java MongoDB Sync Driver: Reading Query Plans

In Java, the MongoDB Sync Driver provides builders like **Filters**, **Sorts**, and **Indexes**, plus **`explain()`** on queries. Examples require a compatible **`mongodb-driver-sync`** dependency and a configured **`MONGODB_URI`** environment variable.

### 18.1. Standard Query

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;

public class OrderQueryExample {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        Bson filter = Filters.eq("status", "FAILED");
        Bson sort = Sorts.descending("createdAt");

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> orders = client
                    .getDatabase("query_plan_lab")
                    .getCollection("orders");

            try (MongoCursor<Document> cursor = orders
                    .find(filter)
                    .sort(sort)
                    .limit(20)
                    .iterator()) {

                while (cursor.hasNext()) {
                    System.out.println(cursor.next().toJson());
                }
            }
        }
    }
}
~~~

This is a **standard query**. The server selects or reuses a plan while processing it. Application code does not manually manage the plan cache for requests to execute.

### 18.2. Calling Explain in Java

~~~java
import com.mongodb.ExplainVerbosity;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

public class OrderExplainExample {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> orders = client
                    .getDatabase("query_plan_lab")
                    .getCollection("orders");

            Document plan = orders.find(
                    Filters.eq("status", "FAILED"))
                    .sort(Sorts.descending("createdAt"))
                    .limit(20)
                    .explain(ExplainVerbosity.EXECUTION_STATS);

            System.out.println(
                    plan.toJson()
            );
        }
    }
}
~~~

`explain()` returns the plan tree and execution stats; in real code, parse fields according to your driver/server version. **Never take explain timing as the latency of every regular query**, since explain interacts differently with the plan cache.

### 18.3. Creating Indexes for Query Patterns

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;
import org.bson.Document;

public class OrderIndexSetup {
    public static void createIndex(
            MongoCollection<Document> orders) {

        orders.createIndex(
                Indexes.compoundIndex(
                        Indexes.ascending("tenantId", "status"),
                        Indexes.descending("createdAt")
                ),
                new IndexOptions()
                        .name("idx_tenant_status_date")
        );
    }
}
~~~

The example takes a preconfigured **`MongoCollection`**. This index suits queries filtering **`tenantId = ..., status = ...`** and sorting **`createdAt DESC`**.

Never create indexes per incoming user request. Manage indexes via controlled migrations/bootstrapping, monitor index build impact on large datasets, and avoid redundant indexes.

### 18.4. Same Shape from Different Java Parameters

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

import java.util.List;
import java.util.ArrayList;

public class StatusQuery {
    public static List<Document> latestByStatus(
            MongoCollection<Document> orders,
            String status) {

        return orders.find(Filters.eq("status", status))
                .sort(Sorts.descending("createdAt"))
                .limit(20)
                .into(new ArrayList<>());
    }
}
~~~

Calling:

~~~java
latestByStatus(orders, "NEW");
latestByStatus(orders, "FAILED");
~~~

Both calls preserve the same filter/sort/limit structure, yet may match vastly different document counts. If `status` comes from an HTTP request, validate authorization/input semantics and avoid writing sensitive data to diagnostic logs.

## 19. Spring Data MongoDB: Query Shape in Repositories and Services

Spring Data MongoDB maps **Criteria** and **Sort** into MongoDB queries. The plan cache is still managed by the **MongoDB server**, not as a map of Java `Query` objects inside the app.

Example:

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

    public List<Document> latestOrdersForTenant(
            String tenantId,
            String status) {

        Query query = new Query(
                Criteria.where("tenantId").is(tenantId)
                        .and("status").is(status)
        );

        query.with(Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("_id")
        ));

        query.limit(20);
        query.fields()
                .include("createdAt")
                .include("status")
                .include("totalCents");

        return mongoTemplate.find(
                query,
                Document.class,
                "orders"
        );
    }
}
~~~

Here two requests with different `status` or `tenantId` share the same query structure yet may have very different selectivity. MongoDB can use or switch plans based on runtime conditions. To optimize this read path, candidate indexes normally need both `tenantId`/`status` equality and `createdAt`/`_id` sort keys.

### 19.1. Java Schema and BSON Types Must Stay Consistent

If one service stores **`createdAt`** as a BSON Date while another stores it as a String, structurally identical filters match disjoint subsets. MongoDB does not coerce date Strings into Dates inside an index to sort identically.

Use consistent mappings—such as **`Instant`/`Date`** serialized to BSON Date via configured drivers/converters—and schema validation where needed to enforce database types.

### 19.2. Projections Must Match When Comparing Performance

Two methods:

~~~java
// A: fetches the whole document.
mongoTemplate.find(query, Document.class, "orders");

// B: fetches only needed fields.
query.fields()
        .include("status")
        .include("createdAt");
mongoTemplate.find(query, Document.class, "orders");
~~~

have different projections and potentially different read/serialization costs. In real apps, never diagnose method A's latency by running explain on a trimmed query B and assuming they behave identically.

### 19.3. Should You Use `@Hint` Everywhere?

Spring Data and the MongoDB Driver offer APIs to specify hints when needed. Overusing them can lock an app onto an index that turns suboptimal after data shifts. Especially in multi-tenant or volatile datasets, measure and review hints whenever indexes are added or dropped.

The preferred path is identifying **query patterns**, creating matching indexes, and observing the planner rather than hardcoding hints upfront without evidence.

## 20. Comparison Scenario: Same Shape, Different Optimal Read Path

Suppose an app has two groups of orders:

~~~text
status = NEW:
  Most of the data
  Queries typically match thousands of records

status = FAILED:
  Very small fraction of data
  Queries match only a few records
~~~

Three index choices exist:

~~~javascript
{ status: 1 }
{ createdAt: -1 }
{ status: 1, createdAt: -1 }
~~~

When filtering by `status` and sorting by `createdAt`, the compound index is usually a strong candidate. If a query omits the `status` filter, the `createdAt`-only index helps more. If `status` is ultra-selective yet the query uses a different sort, a single-field `status` index can filter first and sort the tiny slice cheaply.

### 20.1. Why Can One Query Pattern Never Have a "Magic Index" for Everything?

Suppose an app has three screens:

~~~javascript
// A: newest orders system-wide
db.orders.find().sort({ createdAt: -1 }).limit(20);

// B: newest FAILED orders
db.orders.find({ status: "FAILED" })
  .sort({ createdAt: -1 }).limit(20);

// C: high-total orders for a tenant
db.orders.find({
  tenantId: "T-large",
  totalCents: { $gte: 10000 }
}).sort({ totalCents: -1 }).limit(20);
~~~

Different query patterns:

| Screen | Filter | Sort | Candidate Index |
|---|---|---|---|
| A | None | `createdAt` DESC | `{createdAt:-1}` |
| B | `status` equality | `createdAt` DESC | `{status:1,createdAt:-1}` |
| C | `tenant` equality + `total` range | `total` DESC | `{tenantId:1,totalCents:-1}` |

One long index cramming every field will not serve all three well. Field order in compound indexes is critical, and every index adds write maintenance overhead.

### 20.2. When Sort Values Are Not Unique

If two orders share the exact same `createdAt`, sorting solely by `createdAt` does not guarantee deterministic ordering between them. For pagination or batch checkpoints, add a unique tie-breaker like `_id`:

~~~javascript
db.orders.find({
  status: "FAILED"
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
~~~

Changing the sort also changes index requirements. If the app uses a tie-breaker sort for deterministic order, design indexes including the tie-breaker and reproduce incidents using that exact sort.

## 21. Common Misconceptions and Diagnostic Mistakes

| Misconception or Symptom | Actual Issue | How to Handle It |
|---|---|---|
| "Changing literals always creates two distinct shapes" | Query shape usually tracks normalized structure, not literal strings | Compare server-reported shape/hashes for your version |
| "Same shape means identical speed" | Selectivity/cardinality per literal can vary hugely | Inspect value distributions and keys/docs examined |
| "`planCacheKey` is identical to `queryHash`" | One identifies shape; the other also encodes available indexes | Distinguish `planCacheShapeHash`/`queryHash` from `planCacheKey` |
| "Same shape means the plan never changes" | Cache can be invalidated, replanned, or evicted | Check logs/metrics and index/deploy history |
| "The cache stores query result documents" | Plan cache stores plan metadata, not result sets | Every query still reads current data |
| "`explain()` shows which cached plan is used" | `explain` bypasses and never warms the plan cache | Use `explain` for plan inspection; profiler/logs/`$planCacheStats` for runtime state |
| "Running `explain` repeatedly warms the cache" | Explain does not populate cache entries like normal queries | Run normal queries when testing cache behavior per server rules |
| "No `$planCacheStats` entry means no index is used" | Shape may not create an entry or entry was evicted | Check `winningPlan` via `explain` and learn cache rules |
| "An Active cache entry means the query is fast" | A cached plan can become suboptimal | Measure latency, keys/docs examined, and feedback |
| "Seeing `IXSCAN` means optimal" | It might scan nearly the whole index and FETCH many docs | Compare `nReturned` with keys/docs examined |
| "Seeing `COLLSCAN` means a bug" | On tiny collections or unselective filters, `COLLSCAN` can make sense | Evaluate cost on representative data |
| "Clearing the cache permanently fixes slow queries" | Missing indexes, skew, or resource bottlenecks may be to blame | Investigate root cause before touching cache |
| "Adding an index does not affect the plan cache" | Available index set changes; keys/entries may invalidate | Track create/drop/hide index history |
| "More `FAILED` docs won't affect unchanged queries" | Matching record volume can surge | Check current distribution and actual selectivity |
| "A dev `explain` represents production" | Data size, distribution, version, topology, and load differ | Observe on representative data and timing |
| "Hinting an index guarantees stable performance" | Forced indexes can turn bad as data shifts | Use hints purposefully and monitor post-deploy |
| "Same app means all nodes share one cache" | Plan cache is per-node runtime state | Inspect serving nodes and replica/shard differences |
| "p95 spike means the planner just replanned" | Network, CPU, I/O, pool wait, and payload also add latency | Break down latency and look for plan change evidence |
| "Sorting by `createdAt` is strictly deterministic" | Many documents can share timestamps | Add a unique tie-breaker like `_id` |
| "Create as many indexes as possible" | Indexes cost RAM, disk, and write overhead | Design around key query patterns |

### 21.1. Why Should You Never Derive Shape Hashes from Raw Query Strings?

Consider two expressions:

~~~javascript
db.orders.find({ status: "NEW" });

db.orders.find({
  status: { $eq: "NEW" }
});
~~~

Their JavaScript/JSON strings differ, yet logically both express equality. The planner normalizes queries, so hashing raw query strings will never yield reliable shape identifiers.

For long-term tracking, applications can assign **business names to query patterns** (e.g., `"orders-by-status-newest"`) and correlate them with MongoDB's reported identifiers. Business names keep dashboards readable without guessing internal hash algorithms.

### 21.2. Plan Changes and Bad Performance Do Not Have a 1-to-1 Relationship

There are at least four scenarios:

| Plan Changed? | Slower? | Possible Interpretation |
|---|---|---|
| No | No | Stable workload |
| No | Yes | Same plan, yet matching rows grew, resources starved, or different parameters |
| Yes | No | Planner successfully adapted to new data/indexes |
| Yes | Yes | New plan hurts this workload, or environment remains bottlenecked |

Thus, one latency measurement never proves the plan cache is guilty. Correlate plans, data, execution stats, and change timelines.

## 22. Practice Exercises

Exercises build on the **`query_plan_lab`** database and **`orders`/`skewOrders`** collections created above. Create indexes, modify data, or clear caches only in practice environments you own. Never use live production data for learning.

### Exercise 1. Identifying Query Shapes

Given the queries:

~~~javascript
// A
db.orders.find({ status: "NEW" })
  .sort({ createdAt: -1 });

// B
db.orders.find({ status: "FAILED" })
  .sort({ createdAt: -1 });

// C
db.orders.find({ status: "NEW", tenantId: "T-A" })
  .sort({ createdAt: -1 });

// D
db.orders.find({ status: "NEW" })
  .sort({ totalCents: -1 });

// E
db.orders.find(
  { status: "NEW" },
  { _id: 0, createdAt: 1 }
).sort({ createdAt: -1 });
~~~

**Questions:**

1. Which pair shares filter/sort structure with only different literals?
2. Why does C differ from A in filter structure?
3. Why should D and E be treated differently from A?
4. Should you assert two different queries definitely have different hashes without checking the MongoDB server?

**Guidance:** A and B share the common pattern; C adds `tenantId`, D changes the sort, and E changes the projection. To confirm exact shape hashes, inspect the server's version-specific output.

### Exercise 2. Selecting Candidate Indexes

Query:

~~~javascript
db.orders.find({
  status: "FAILED"
}).sort({
  createdAt: -1
}).limit(20);
~~~

Compare:

~~~javascript
{ status: 1 }
{ createdAt: -1 }
{ status: 1, createdAt: -1 }
~~~

Identify which index structurally supports filtering `status` and returning `createdAt` in order. Explain why `{status: 1}` alone may need a `SORT` stage while `{createdAt: -1}` alone may inspect many mismatched statuses.

**Guidance:** Compound index **`{status: 1, createdAt: -1}`** usually suits equality filter + sort. Final choice still depends on data volume and the query planner.

### Exercise 3. Distinguishing Shape Hash from `planCacheKey`

Suppose the app leaves filter/sort/projection untouched, while an admin adds a new matching index. Answer:

1. Does the logical query shape change?
2. Can `planCacheKey` change?
3. Why?
4. Can you hash the raw JSON query string as a substitute for `planCacheShapeHash`?

**Guidance:** Shape keeps its structure; `planCacheKey` can change because eligible indexes changed; never compute shape hashes from raw query strings.

### Exercise 4. Explain and Cache

Run:

~~~javascript
db.orders.find({
  status: "FAILED"
}).sort({
  createdAt: -1
}).explain("executionStats");
~~~

Then:

~~~javascript
db.orders.aggregate([
  { $planCacheStats: {} }
]);
~~~

**Question:** Can you cite the `explain` execution above as proof the plan cache is warmed? If the second command shows no entry, can you conclude the query errored or skipped indexes?

**Guidance:** No. Explain bypasses the cache and creates no entries. Missing entries can stem from many causes; separate candidate plan inspection from runtime cache state.

### Exercise 5. Data Skew and Plan Selection

Suppose before an incident:

~~~text
NEW    = 99%
FAILED = 1%
~~~

After the incident:

~~~text
NEW    = 40%
FAILED = 60%
~~~

Explain:

1. By roughly what factor can matching documents for `status = FAILED` grow?
2. If the app did not alter the query, can the query shape remain identical?
3. Is MongoDB guaranteed to replan immediately on the next run?
4. Does an unchanged plan prove latency cannot increase?

**Guidance:** `FAILED` share jumped from 1% to 60%; if total documents stay constant, `FAILED` records grew roughly 60x. Shape can remain unchanged; immediate replanning is not guaranteed; the same plan can end up reading far more data.

### Exercise 6. Reading `executionStats`

Suppose two options are measured on identical data and equivalent requests:

| Metric | Plan X | Plan Y |
|---|---:|---:|
| `nReturned` | 20 | 20 |
| `totalKeysExamined` | 15,000 | 25 |
| `totalDocsExamined` | 14,000 | 20 |
| Separate `SORT` | Yes | No |

**Question:** Which plan shows signs of reading less data and avoiding sorting? Can you declare it strictly faster under all conditions solely from this table?

**Guidance:** Plan Y looks more favorable on examined keys/docs and sorting, yet you must measure real latency, resources, index size, concurrency, and write overhead on the live workload. This table illustrates metric reasoning, not measurements from the lab collection.

### Exercise 7. Creating Skewed Data and Shifting Distribution

Using **`skewOrders`** from the lab:

1. Check initial `NEW` and `FAILED` counts.
2. Run explain for `NEW` and `FAILED` filters with identical sort/limit.
3. Run the `updateMany` from section 12.4 on the test collection.
4. Recheck distribution.
5. Re-run explain.
6. Inspect `$planCacheStats` if entries exist.

Write a short note distinguishing:

- **What was directly measured**: distribution, `winningPlan`, keys/docs examined.
- **Hypothesis**: data shift caused a plan change.
- **What cannot be concluded from explain alone**: which cached plan normal requests actually used.

### Exercise 8. Comparing Cache Clearing vs. Creating an Index

A query is slow because no index fits **`tenantId = ..., status = ...`** with sort **`createdAt DESC`**.

Answer:

1. If you only clear the plan cache without changing indexes, does that create a new index option?
2. Which fields should the candidate index include?
3. Why must write cost be weighed before adding an index?
4. When should `hint` be used for diagnosis?

**Guidance:** Clearing the cache creates no indexes. Consider **`{tenantId: 1, status: 1, createdAt: -1}`**. Indexes add storage/write cost; use `hint` purposefully to test a plan, not as a default production override.

### Exercise 9. Analyzing a Real Incident

An endpoint shows:

~~~text
Last week: p95 80 ms
This week: p95 800 ms
Query pattern: orders by tenantId + status, sort createdAt
Records for a large tenant surged
An index deployment recently went out
~~~

Draft an investigation plan including at least:

- Capturing exact query shape and filter/sort/projection/limit parameters.
- Checking data distribution across tenant/status.
- Comparing indexes before/after deployment.
- Running explain on representative requests.
- Checking logs/profiler/APM and `$planCacheStats` if supported.
- Separating query plan regression from resource contention.
- Planning re-measurement after remediation.

**Key point:** Two changes happened concurrently (data and indexes). Never declare one of them the sole cause without evidence.

### Exercise 10. True/False Review

Evaluate and explain:

1. The plan cache stores the full list of returned documents for a query shape.
2. Two queries with different literals but identical structure can share a shape.
3. `planCacheKey` always stays unchanged when a new index is created.
4. `explain("executionStats")` can be used to view metrics for a plan.
5. Repeatedly running `explain` is a guaranteed way to warm up the plan cache.
6. An Active cache entry guarantees a query will always be fast.
7. Data skew can cause the same query pattern to run at different costs.
8. A plan change always means MongoDB encountered a bug.

**Answers:** (1) False; (2) True in standard cases; (3) False; (4) True; (5) False; (6) False; (7) True; (8) False.

## 23. Mental Model to Apply

You can summarize how these concepts connect:

~~~text
Query shape
  = "What structure is the application asking for?"
                    |
                    v
Indexes + query planner
  = "Which paths exist to find and sort the data?"
                    |
                    v
Plan cache
  = "Which chosen plan is saved for potential reuse?"
                    |
                    v
Runtime feedback / data distribution
  = "Is that plan still effective right now?"
                    |
            +-------+-------+
            |               |
           Yes             No / conditions shifted
            |               |
      Keep reusing      May replan,
      when eligible     invalidate, or switch plans
~~~

**Five core principles:**

1. **Query shape describes structure, not selectivity.** Different parameter values can create wildly different workloads under the same shape.
2. **The plan cache remembers execution strategies, not results.** Data is still read per query, and cache entries are transient state.
3. **Shifting data can make an old plan inefficient**, yet immediate replanning on every change is never guaranteed.
4. **`explain()` and `$planCacheStats` answer different questions.** Explain analyzes how the planner builds/runs a plan diagnostically; `$planCacheStats` shows current cache entries within observation scope.
5. **Optimization is a measurement and verification loop.** Inspect data skew, indexes, filters, sorts, projections, limits, plans, keys/docs examined, and system latency before intervening.

Once you separate **query shape**, **active plan**, **data distribution**, and **cache state**, you can investigate a slowing MongoDB query without rashly clearing caches or hardcoding hints. The sound approach is gathering evidence, choosing fitting indexes/query patterns, re-measuring on representative workloads, and monitoring adaptability as data continues to grow.
