# Measuring Queries, Designing Indexes, and Comparing Before/After Explain Plans in MongoDB

A MongoDB query that returns the right data does not necessarily meet operational requirements. With a few dozen documents, an unindexed `find` is still fast. However, when a collection grows to hundreds of thousands or millions of documents, the same query can scan huge amounts of data and perform memory-intensive sorts, slowing down APIs and increasing load across the replica set.

Reliable optimization does not start by creating lots of indexes. You need to **measure the current state, understand access patterns, design a candidate index, re-measure under the same conditions, and verify correctness**. This lesson builds a MongoDB lab following that exact sequence, combining `mongosh`, `explain`, benchmarking methodology, and a Java Sync Driver example.

This lesson belongs to the **Integrated Practice** chapter, **Database Engine Document MongoDB** module, covering **Measuring Queries, Designing Indexes, and Comparing Before/After Explain Plans**.

**Safety note:** All data writes and index creation/hiding/dropping commands in this lesson are strictly for an isolated practice database. Never run them in production. `explain` and read queries also incur cost; when diagnosing production, limit scope, use appropriate permissions, measure impact, and follow operational procedures.

## 1. Target Outcomes

After this lesson, you can:

1. Identify a query shape and its performance target.
2. Create a deterministic test dataset with multiple tenants, statuses, and timestamps.
3. Record the index list, document counts, and state before the experiment.
4. Run `explain` at the `queryPlanner`, `executionStats`, and `allPlansExecution` verbosity levels.
5. Interpret `nReturned`, `totalDocsExamined`, `totalKeysExamined`, and stages such as `COLLSCAN`, `IXSCAN`, `FETCH`, and `SORT`.
6. Understand how `explain` structure can differ between the classic engine and the slot-based execution engine.
7. Design compound indexes based on equality, sort, and range predicates.
8. Compare query results before and after to ensure indexes do not alter semantics.
9. Measure latency with warm-ups, multiple iterations, and equivalent workloads.
10. Recognize trade-offs among read latency, index storage, and write overhead.
11. Try covered queries, keyset pagination, multikey indexes, partial indexes, and query hints.
12. Distinguish conclusions supported by `explain` from conclusions requiring application/APM measurement.
13. Write an A/B report with clear evidence, uncertainty, rollback plan, and decision.

## 2. Lab Workflow Overview

~~~text
Business request / API SLO
           |
           v
Identify query shape and data distribution
           |
           v
Create isolated, deterministic test dataset
           |
           v
BASELINE
  - getIndexes
  - query result IDs
  - explain executionStats
  - repeated latency measurements
           |
           v
Hypothesis: an index can support filter + sort
           |
           v
Design candidate compound index
           |
           v
Create index in the lab only
           |
           v
AFTER
  - same query and data
  - explain executionStats
  - repeated latency measurements
  - check result correctness
           |
           v
Compare evidence and trade-offs
           |
           v
Document decision, risks and next experiment
~~~

Never treat "it uses IXSCAN so it's definitely optimal" as the final conclusion. An index can reduce documents examined while adding write overhead, or a plan that is fast on small data may perform poorly in production.

## 3. End-to-End Business Scenario

Suppose a rental-order management application has an API:

~~~text
GET /tenants/{tenantId}/orders?status=PAID&limit=20

Required behavior:
  Only orders belonging to authenticated tenant
  Only status PAID
  Newest orders first
  Stable order on ties using _id
  Return at most 20 documents
~~~

MongoDB query pattern:

~~~javascript
db.orders.find({
  tenantId: "tenant-07",
  status: "PAID"
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
~~~

### 3.1. What Does the Access Pattern Include?

- Equality filter: `tenantId = tenant-07`.
- Equality filter: `status = PAID`.
- Sort: `createdAt` descending, then `_id` descending.
- Limit: 20.
- Read frequency: assumed high; must be measured in the real application.
- Security: `tenantId` must come from a verified authentication context.

### 3.2. Questions to Answer

1. With only the default index on `_id`, how much work does the query perform?
2. Is there a blocking sort?
3. Which index can filter and sort more efficiently?
4. Do the results stay identical after adding the index?
5. Is the read gain worth the cost of the new index?

## 4. Environment Requirements

You need:

- A **dedicated practice** MongoDB server or replica set.
- `mongosh` and an account authorized to create collections/indexes in the lab database.
- Ability to observe command output and record A/B measurements.
- Optional: Java Sync Driver and a Java project to measure from the application side.
- Enough disk space for roughly 48,000 small documents.

**Do not** use a production account with database-modification privileges just because the collection is named `orders`.

### 4.1. Isolated Database

Use the name:

~~~text
mongo_index_lab_459
~~~

If you have already run this lab, create a differently named database with the same intent. Do not drop existing data by default.

### 4.2. What Is Version-Dependent?

Explain output, metric fields, plan cache descriptions, and stage naming can vary across MongoDB versions. This lesson explains stable signal groups conceptually, without requiring every JSON output to match verbatim.

### 4.3. Record the Version First

~~~javascript
db.version();
db.adminCommand({ hello: 1 });
~~~

These commands inspect server/topology info. Do not infer overall cluster health from a single node's `hello` response.

## 5. Designing the Dataset Before Measuring

A purposeful dataset should satisfy:

- Enough documents for a noticeable difference between a scan and an index lookup.
- Multiple tenants and statuses so equality filters are selective.
- `createdAt` spread across multiple timestamps.
- Deterministic `_id`s with clear ordering.
- Fields stored with exact BSON types.
- No reliance on unseeded `Random` or `Instant.now`.
- Reproducible from the same formula.

We choose **48,000 orders**, **24 tenants**, and **4 statuses**, distributed evenly by formula. Each tenant/status pair has **500 orders**.

### 5.1. Avoiding Accidental Correlated Distribution

If you set `tenantId = i % 24` and `status = i % 4`, since 24 is divisible by 4, each tenant would only ever receive a single status. That produces unrepresentative data and distorts the query shape.

Instead:

~~~javascript
tenantIndex = i % 24;
statusIndex = Math.floor(i / 24) % 4;
~~~

Each cycle of 24 documents covers all tenants; only after a full cycle does the status rotate. After 48,000 records, every tenant has 2,000 orders and every status within a tenant has 500 orders.

### 5.2. Verifying Counts

~~~text
24 tenants x 4 statuses x 500 documents
= 48,000 documents
~~~

These are the designed counts for the lab, not measurements collected from a live cluster.

## 6. Generating Sample Data with mongosh

**Run only on a verified test deployment.** The script intentionally refuses to run if an `orders` collection already exists in the lab database so it does not overwrite state from a prior run.

~~~javascript
var lab = db.getSiblingDB("mongo_index_lab_459");

if (lab.getCollectionInfos({ name: "orders" }).length > 0) {
  throw new Error(
    "Lab orders already exists. Use a fresh lab database."
  );
}

var orders = lab.getCollection("orders");
var statuses = [
  "PENDING",
  "PAID",
  "CANCELLED",
  "COMPLETED"
];

var baseTime = Date.UTC(
  2026, 0, 1, 0, 0, 0
);

var batch = [];
var total = 48000;

for (var i = 0; i < total; i++) {
  var tenantIndex = i % 24;
  var statusIndex = Math.floor(i / 24) % 4;

  var doc = {
    _id: "o-" + String(i + 1).padStart(6, "0"),
    tenantId: "tenant-" +
      String(tenantIndex).padStart(2, "0"),
    status: statuses[statusIndex],
    customerId: "customer-" +
      String(i % 300).padStart(4, "0"),
    createdAt: new Date(
      baseTime + i * 60 * 1000
    ),
    totalMinor: NumberLong(
      100000 + (i % 500) * 1000
    ),
    priority: i % 10 === 0,
    items: [
      {
        sku: "sku-" + String(i % 40),
        qty: 1 + (i % 3)
      }
    ]
  };

  batch.push(doc);

  if (batch.length === 1000) {
    orders.insertMany(batch, {
      ordered: true
    });
    batch = [];
  }
}

if (batch.length > 0) {
  orders.insertMany(batch);
}

print("Seeded orders: " + orders.countDocuments({}));
printjson(orders.getIndexes());
~~~

### 6.1. Why Batch 1,000?

It avoids holding all 48,000 documents in a single array in `mongosh` and keeps each `insertMany` at a reasonable size. You can adjust the batch size per environment, recording any changes.

### 6.2. Do Not Drop Collections Automatically

A lab database might already hold data for another experiment. The script throws an error instead of dropping an existing collection. Only after verifying the right test environment should you intentionally use a new namespace or perform authorized cleanup.

### 6.3. Seed Before Creating Candidate Indexes

For a fair baseline, start with only the default `_id` index and no compound index serving the main query.

### 6.4. Why Is createdAt Fixed?

There is no drift from test execution time; result ordering is predictable and comparable across runs.

### 6.5. What If Seeding Stops Midway?

The collection may exist with partial records. Never use incomplete data as a baseline. Create a new lab namespace or follow safe cleanup procedures, re-seed, and confirm all 48,000 documents exist.

## 7. Checking Data Distribution

Before running `explain`, verify counts:

~~~javascript
var lab = db.getSiblingDB("mongo_index_lab_459");
var orders = lab.getCollection("orders");

print("Total: " + orders.countDocuments({}));

print(
  "tenant-07/PAID: " +
  orders.countDocuments({
    tenantId: "tenant-07",
    status: "PAID"
  })
);
~~~

With proper seeding, expected:

~~~text
Total: 48000
tenant-07/PAID: 500
~~~

If counts differ, stop the experiment and investigate the seed/namespace before comparing performance.

### 7.1. Selectivity

The query matches 500 documents out of 48,000; after sort and limit, it returns 20.

- Filter match ratio: 500 / 48,000.
- Output ratio: 20 / 48,000.
- These ratios are derived from the seed model, not server performance metrics.

### 7.2. Inspecting Group Distribution

~~~javascript
orders.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        status: "$status"
      },
      n: { $sum: 1 }
    }
  },
  {
    $sort: {
      "_id.tenantId": 1,
      "_id.status": 1
    }
  },
  { $limit: 12 }
]);
~~~

The sample output illustrates the distribution; you can remove `$limit` in the lab database to verify all 96 groups.

## 8. Confirming Initial Index State

~~~javascript
var orders = db.getSiblingDB(
  "mongo_index_lab_459"
).getCollection("orders");

printjson(orders.getIndexes());
~~~

On a new collection, usually only the default index exists:

~~~javascript
[
  {
    v: 2,
    key: { _id: 1 },
    name: "_id_"
  }
]
~~~

Exact JSON structure varies by server version. What you must record is the **key pattern, name, and options**, not incidental metadata.

### 8.1. Why Inventory First?

If the candidate index already exists from an earlier run, the "before" measurement will no longer be a true baseline.

### 8.2. The _id Index Does Not Automatically Help tenantId/status Filters

A B-tree index on `_id` does not organize data to filter first by `tenantId` and `status`. The query may use `COLLSCAN` or another optimizer-chosen plan; verify with actual `explain`.

## 9. Defining Invariant Query A

Use the exact same filter, sort, projection, and limit before and after.

~~~javascript
var lab = db.getSiblingDB("mongo_index_lab_459");
var orders = lab.getCollection("orders");

var filterA = {
  tenantId: "tenant-07",
  status: "PAID"
};

var sortA = {
  createdAt: -1,
  _id: -1
};

var limitA = 20;
~~~

### 9.1. Do Not Change the Query Between A and B

If before measures `tenant-07` and after measures `tenant-22`, latencies are no longer fairly comparable if distributions differ.

### 9.2. Keep the Projection Identical

If before returns full documents and after returns only `_id`, both network payload and index coverage changed. Change **one design variable** at a time.

### 9.3. Query Correctness Before Performance

A good index must never alter tenant isolation, status filtering, or ordering guarantees.

## 10. Saving Expected Results Before Creating the Index

In the same `mongosh` session:

~~~javascript
var baselineIds = orders.find(filterA)
  .sort(sortA)
  .limit(limitA)
  .project({ _id: 1 })
  .toArray()
  .map(d => d._id);

printjson(baselineIds);
~~~

### 10.1. Why Save the IDs?

After creating the index, we verify that the same query still returns the exact same IDs in the exact same order. If they differ, either data changed between runs, a sort tie-breaker is missing, or the query changed.

### 10.2. _id as a Tie-Breaker

Even if lab data has unique `createdAt` values, real-world events often share identical timestamps. Adding `_id` to the sort makes order deterministic.

### 10.3. No Writes Between Measurements

In the lab with no other writers, all results stay fixed. In production, concurrent writes can legitimately change top-page results between two points in time.

## 11. Running explain Before Index Creation

~~~javascript
var beforeExplain = orders.find(filterA)
  .sort(sortA)
  .limit(limitA)
  .explain("executionStats");

printjson({
  queryPlanner: beforeExplain.queryPlanner,
  executionStats: beforeExplain.executionStats
});
~~~

Key metrics typically reside at:

~~~javascript
beforeExplain.executionStats.nReturned;
beforeExplain.executionStats.totalKeysExamined;
beforeExplain.executionStats.totalDocsExamined;
beforeExplain.executionStats.executionTimeMillis;
~~~

### 11.1. Read the Actual Stages Rather Than Assuming

With 48,000 documents and no compound index, seeing `COLLSCAN` and a sort stage is very likely. However, the query planner can vary by version, query, and data state. **Record what actually appears in `winningPlan`.**

### 11.2. Explain Is Not an End-to-End Network Timer

`executionStats.executionTimeMillis` generally captures server-side execution under explain, excluding full Java API time, network round-trips, decoding, or connection pool waits.

### 11.3. Both Filtering and Sorting Cost Work

Even when returning only 20 records, the server may have to inspect many documents to locate the 20 newest matching items.

## 12. Verbosity Levels of explain

MongoDB supports three common modes:

| Mode | Provides | When to Use |
| --- | --- | --- |
| `queryPlanner` | Winning plan, plan metadata | Understand chosen route/index |
| `executionStats` | Planner + execution metrics | Count examined vs. returned |
| `allPlansExecution` | Adds candidate plan stats | Investigate planner choices |

Example:

~~~javascript
orders.find(filterA)
  .sort(sortA)
  .limit(limitA)
  .explain("queryPlanner");

orders.find(filterA)
  .sort(sortA)
  .limit(limitA)
  .explain("executionStats");

orders.find(filterA)
  .sort(sortA)
  .limit(limitA)
  .explain("allPlansExecution");
~~~

### 12.1. Do Not Enable Expensive Modes Unnecessarily

In the lab, you can inspect all three. In production, `explain` can execute the workload and consume resources; watch query scope and invocation frequency.

### 12.2. allPlansExecution Does Not Mean Every Candidate Runs to Completion

Candidate execution info may reflect bounded trial runs per planner mechanics. Do not treat partial candidate stats as full-query latency.

### 12.3. Plan Cache

`explain` is not an exact replica of normal cached-plan execution. Do not assume a single `explain` invocation reflects all plan cache/selection behavior under live production traffic.

## 13. Reading COLLSCAN, IXSCAN, FETCH, and SORT

| Stage/Signal | Conceptual Meaning | Next Question |
| --- | --- | --- |
| `COLLSCAN` | Scans collection documents | Why does the filter lack a better access path? |
| `IXSCAN` | Traverses index entries | How many keys were examined? |
| `FETCH` | Retrieves document after index lookup | Does the query need fields outside the index? |
| `SORT` | Sorts data beyond index-provided order | Does the index support the sort? |
| `LIMIT` | Caps result count | Does it bound upstream work? |
| `PROJECTION` | Projects/transforms returned fields | Is the query covered? |

### 13.1. Stage Names Can Differ

MongoDB has both the classic engine and the slot-based execution engine (SBE). Explain may describe stages inside `queryPlan`, `slotBasedPlan`, or other structures. Read for execution semantics rather than relying on a single hardcoded JSON path.

### 13.2. IXSCAN Does Not Guarantee Efficiency

A plan with `IXSCAN` that has huge `totalKeysExamined` and small `nReturned` can still be very expensive.

### 13.3. COLLSCAN Is Not Always Wrong

When a query returns most of a collection or the dataset is tiny, `COLLSCAN` is sometimes cheaper than an index. Never treat a stage name alone as an automatic error.

## 14. Four Key Metrics

**nReturned:** number of documents returned from execution to the client/limit stage per explain.

**totalDocsExamined:** number of actual documents inspected during plan execution. Can exceed the number of documents returned.

**totalKeysExamined:** number of index keys scanned. Without an index scan, this is typically low or zero.

**executionTimeMillis:** execution time reported by explain; useful as a reference, but insufficient as an end-to-end benchmark.

### 14.1. Examined-to-Returned Ratios

For `nReturned > 0`:

~~~text
Documents-per-result =
  totalDocsExamined / nReturned

Keys-per-result =
  totalKeysExamined / nReturned
~~~

These two ratios help distinguish a selective index seek from a broad scan.

### 14.2. Do Not Divide by Zero When nReturned == 0

If a query returns zero results, examine raw examined counts and selectivity rather than applying a formula with a zero denominator.

### 14.3. DocsExamined Does Not Equal Bytes Read

Total bytes, page cache hits/misses, and disk I/O depend on document size, compression, cache, and storage. Use dedicated I/O metrics when investigating I/O.

### 14.4. A Single executionTimeMillis Reading Is Not Enough

Server load, cache state, warm-up, and scheduling make numbers fluctuate. Repeat runs and record environment conditions alongside application latency.

## 15. Baseline Table Template

Fill in from actual results—never invent numbers:

| Metric | Baseline Before Index |
| --- | --- |
| Dataset size | 48,000 per seed; verify |
| Query shape | `tenantId + status`, sort `createdAt/_id` |
| Existing indexes | Record from `getIndexes` |
| Winning plan | Record from `explain` |
| `nReturned` | Record value |
| `totalDocsExamined` | Record value |
| `totalKeysExamined` | Record value |
| `executionTimeMillis` | Record value |
| Blocking sort? | Yes/no per winning plan |
| Query result IDs | Save `baselineIds` |
| p50/p95 from repeated runs | Record separately |

Never treat an assumed count of 48,000 as proof if seeding stopped partway. Always check the actual count.

## 16. Designing Indexes by Equality, Sort, Range (ESR)

A widely used heuristic is **Equality → Sort → Range (ESR)** for compound indexes, though it is not an immutable law.

Query A:

~~~javascript
{
  tenantId: "tenant-07",
  status: "PAID"
}
~~~

Sort:

~~~javascript
{
  createdAt: -1,
  _id: -1
}
~~~

Candidate index:

~~~javascript
{
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
}
~~~

### 16.1. Why tenantId and status First?

They are equality predicates. The index can immediately seek to the key range for the matching tenant and status.

### 16.2. Why createdAt and _id Next?

Within each `(tenantId, status)` group, index keys are ordered by `createdAt` desc and `_id` desc, supporting the query's sort directly.

### 16.3. Why Not Index Only createdAt?

An index on `createdAt` alone supports the sort order but still has to filter out many orders belonging to other tenants and statuses, especially in a multi-tenant dataset.

### 16.4. Why Not Index Every Field?

A compound index with too many fields wastes storage and write maintenance. Include only fields justified by the workload.

## 17. Creating the Candidate Index in the Lab

**Run the following index creation command only on the verified lab collection, never in production.**

~~~javascript
var lab = db.getSiblingDB("mongo_index_lab_459");
var orders = lab.getCollection("orders");

orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "idx_tenant_status_created_id"
  }
);

printjson(orders.getIndexes());
~~~

### 17.1. Recording Index Build Time and Resources

In production, building a new index impacts CPU, disk, I/O, replication, and write load. A small lab cannot predict index build costs at large scale.

### 17.2. Name Every Trial Index Explicitly

Explicit names keep reports, hints, `$indexStats`, and rollbacks consistent.

### 17.3. A New Index Is Not Automatically Chosen for Every Query

The optimizer selects plans based on query shape, selectivity, and statistics/conditions. Inspect the winning plan, not just `getIndexes`.

## 18. Running explain After Creating the Index

Reuse the exact same Query A:

~~~javascript
var afterExplain = orders.find(filterA)
  .sort(sortA)
  .limit(limitA)
  .explain("executionStats");

printjson({
  queryPlanner: afterExplain.queryPlanner,
  executionStats: afterExplain.executionStats
});
~~~

Check for index name:

~~~text
idx_tenant_status_created_id
~~~

if the winning plan uses this index. Also observe whether a blocking `SORT` remains and how many documents/keys were examined.

### 18.1. Conceptual Expectation

Under matching dataset and planner conditions, a compound index lets MongoDB read a small contiguous range for the tenant/status and stop once 20 ordered results are found.

### 18.2. Do Not Pre-Fill Specific Numbers Before Running

`docsExamined` may be close to 20 when fetching 20 docs using a well-matched index. However, never state that as an observed result before actually running the command.

### 18.3. Query Shape Must Be Identical

Change only the index state—keep tenant, status, projection, read preference, limit, and sort identical between both runs.

## 19. A/B Comparison Table

| Metric | Before | After | Interpretation |
| --- | --- | --- | --- |
| Winning access path | Record Plan A | Record Plan B | `COLLSCAN` or `IXSCAN`? |
| Index used | Record name | Record name | Matches candidate? |
| `nReturned` | Measured | Measured | Must preserve semantics |
| `totalDocsExamined` | Measured | Measured | Less work? |
| `totalKeysExamined` | Measured | Measured | Selective index scan? |
| Blocking `SORT` | Yes/no | Yes/no | Does index support sort? |
| `executionTimeMillis` | Measured | Measured | Reference only |
| End-to-end p50/p95 | Measured | Measured | Real SLO |
| Result IDs/order | Baseline | After | Must be identical |
| Storage/write overhead | Baseline | Post-index | Trade-off |

### 19.1. Illustrative Example — NOT a Measurement

Suppose a query examines 48,000 docs to return 20 before indexing, and examines 20 docs and 20 index keys after indexing. Examined work drops dramatically, yet you cannot claim API p95 latency drops by 2,400x as a result.

This example illustrates the principle only. **Actual reports must use measurements taken on the environment under test.**

### 19.2. Improvement Ratios

For positive measurements:

~~~text
Reduction (%) =
  (before - after) / before * 100

Speedup ratio =
  before_latency / after_latency
~~~

Do not compute speedup if `after_latency` is 0 due to coarse timer resolution; use a higher-resolution measurement method.

## 20. Verifying Correctness After Index Creation

In the same `mongosh` session holding `baselineIds`:

~~~javascript
var afterIds = orders.find(filterA)
  .sort(sortA)
  .limit(limitA)
  .project({ _id: 1 })
  .toArray()
  .map(d => d._id);

if (
  JSON.stringify(baselineIds) !==
  JSON.stringify(afterIds)
) {
  throw new Error(
    "Result IDs/order changed between A and B"
  );
}

print("Result IDs and order are unchanged");
~~~

### 20.1. Why Shouldn't an Index Change Results?

An index is a query access path, not a change to business predicates. If result sets differ, inspect query shape, data mutations, collation, or consistency before drawing conclusions.

### 20.2. Fixed Data Makes Comparison Easier

The lab has no external writers and timestamps are fixed. In production, concurrent writes can legitimately produce different snapshots at two different times.

### 20.3. Separate Count Verification

~~~javascript
orders.countDocuments(filterA);
~~~

Per the seed, Query A matches 500 docs—not just the 20 returned.

## 21. Measuring Latency Multiple Times in mongosh

`explain` gives execution metrics, while repeated runs can gauge lab query duration. The example below measures **wall-clock group averages** via `Date.now`; it is not a replacement for APM or a proper microbenchmarking harness.

~~~javascript
function measureQuery(groups, queriesPerGroup) {
  for (var warm = 0; warm < 5; warm++) {
    orders.find(filterA)
      .sort(sortA)
      .limit(limitA)
      .toArray();
  }

  var samples = [];

  for (var g = 0; g < groups; g++) {
    var startMs = Date.now();

    for (var q = 0; q < queriesPerGroup; q++) {
      orders.find(filterA)
        .sort(sortA)
        .limit(limitA)
        .toArray();
    }

    var durationMs = Date.now() - startMs;
    samples.push(
      durationMs / queriesPerGroup
    );
  }

  samples.sort((a, b) => a - b);

  var medianIndex = Math.floor(samples.length / 2);
  var p95Index = Math.min(
    samples.length - 1,
    Math.ceil(0.95 * samples.length) - 1
  );

  return {
    groups: groups,
    queriesPerGroup: queriesPerGroup,
    medianMs: samples[medianIndex],
    p95Ms: samples[p95Index],
    samplesMs: samples
  };
}

printjson(measureQuery(20, 10));
~~~

### 21.1. Running Before and After

Measure before creating the index and save the output; then measure after creating the index with the exact same script, keeping group and repetition counts constant.

### 21.2. Limitations of Date.now

Clocks have finite resolution; a very fast query can register 0 ms. Averaging over groups of 10 requests reduces quantization noise, though it still falls short of a high-resolution benchmark.

### 21.3. Testing Warms the Cache

Repeated reads pull data and indexes into cache. Document warm vs. cold state, run order, and shared host resources.

### 21.4. SLOs Must Be Measured at the Application

`mongosh` timing excludes Java service factors: connection acquisition, network round-trips, DTO mapping, service concurrency, API middleware, and payload serialization.

## 22. Designing a Fair Measurement

At minimum, an A/B experiment should hold constant:

- Same server version and topology.
- Same data and indexes except the candidate index.
- Same query shape, projection, sort, limit, and read preference.
- Same user/tenant distribution.
- Same concurrency and request rate.
- Same cache state where possible.
- No large batch imports, index builds, or backups running concurrently.
- Comparable CPU/I/O/disk pressure per metrics.
- Same application/driver version for end-to-end tests.

### 22.1. Running A Strictly Before B Has Bias

After creating the index, caches may be warmer, the time of day different, and host load shifted. For rigorous benchmarks, repeat in an isolated environment and alternate run order or run multiple sessions.

### 22.2. Never Flush Production Cache for Experiments

Restarting or dropping caches in production causes disruption and produces unrepresentative traffic spikes. Use staging if you need to study cold-cache behavior.

### 22.3. Explain and Benchmarks Answer Different Questions

- Explain: what steps does the server take?
- Latency benchmark: how long does a request take under test conditions?
- Longitudinal metrics: is the gain sustainable under live load?

All three are needed for a sound conclusion.

## 23. Equality, Sort, Range (ESR) in More Detail

The ESR heuristic:

~~~text
Equality fields
      |
      v
Sort fields
      |
      v
Range fields
~~~

Still, base decisions on actual query patterns and selectivity. Example query:

~~~javascript
db.orders.find({
  tenantId: "tenant-07",
  status: "PAID",
  totalMinor: { $gte: NumberLong(400000) }
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
~~~

### 23.1. Sort-First Index

~~~javascript
{
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1,
  totalMinor: 1
}
~~~

The query leverages `createdAt` ordering while checking `totalMinor`. However, if very few records match `totalMinor`, it may have to scan many keys to collect 20 results.

### 23.2. Range-First Index

~~~javascript
{
  tenantId: 1,
  status: 1,
  totalMinor: 1,
  createdAt: -1,
  _id: -1
}
~~~

This narrows `totalMinor` better, but `createdAt` ordering is no longer contiguous after the range field, leading to a blocking sort.

### 23.3. No Single Order Fits Every Query

With a low-selectivity range, a sort-oriented index can win. With a highly selective range and few matches, a range-oriented index may perform better. Use `explain` and measurements, not ESR theory alone.

## 24. Practicing Query B with a Time Range

Find `PAID` orders for `tenant-07` from 2026-01-15 up to (excluding) 2026-02-01:

~~~javascript
var filterB = {
  tenantId: "tenant-07",
  status: "PAID",
  createdAt: {
    $gte: ISODate("2026-01-15T00:00:00Z"),
    $lt: ISODate("2026-02-01T00:00:00Z")
  }
};

orders.find(filterB)
  .sort({
    createdAt: -1,
    _id: -1
  })
  .limit(20)
  .explain("executionStats");
~~~

### 24.1. Half-Open Interval [from, to)

Use an inclusive lower bound and exclusive upper bound so adjacent intervals never overlap or drop boundary records.

### 24.2. The Same Index Can Support It

Index `(tenantId, status, createdAt desc, _id desc)` can satisfy equality and the range/sort on `createdAt` under matching conditions.

### 24.3. Always Check nReturned and Examined

If the time range contains zero records, `explain` may show `nReturned=0`. Do not extrapolate that into "the index is ultra-fast" for populated ranges.

### 24.4. Dates Must Be BSON Dates

If `createdAt` was stored as a string, filtering with `ISODate` will miss documents and sort semantics will differ.

## 25. Practicing Indexes for Customer History

Another query pattern:

~~~javascript
var filterC = {
  tenantId: "tenant-07",
  customerId: "customer-0007"
};

var sortC = {
  createdAt: -1,
  _id: -1
};
~~~

An index for this access pattern could be:

~~~javascript
{
  tenantId: 1,
  customerId: 1,
  createdAt: -1,
  _id: -1
}
~~~

### 25.1. Query A's Index Does Not Replace Query C's Index

The `tenantId, status, createdAt` index lacks `customerId` in its prefix; it is not optimal for every customer-history query.

### 25.2. Test with Representative Data

In the seed, `customerId` is generated via `i % 300`; its distribution may correlate with `tenantId`. Check `countDocuments(filterC)` before inferring selectivity.

### 25.3. Do Not Create an Index per Endpoint Out of Habit

Catalog all read/write workloads and pick a compact set of indexes serving multiple query shapes. Every index adds overhead.

## 26. Key Order in Compound Indexes

Two indexes:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1 }

{ status: 1, tenantId: 1, createdAt: -1 }
~~~

Both can serve queries with equality on both `tenantId` and `status`, yet they differ in how well they serve queries filtering only by `tenantId` or only by `status`.

### 26.1. Prefix Rule

An index whose leading fields (prefix) match a query's filters can often be reused effectively for prefix-only queries. Fields trailing an omitted key generally lose index efficiency.

### 26.2. Multi-Tenant Queries

In a tenant-scoped system, `tenantId` appears in nearly every query. Placing `tenantId` first maximizes reuse, though cardinality and real data still require verification.

### 26.3. Status Alone

`status: "PAID"` usually has low cardinality and matches many documents; a status-only index rarely delivers the expected benefit.

## 27. Sort Direction and Index Direction

Index:

~~~javascript
{
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
}
~~~

With `tenantId`/`status` equality, the index supports `createdAt desc, _id desc` and, where applicable, can scan in reverse to support `createdAt asc, _id asc`.

### 27.1. Mixed Directions Require Checking the Key Pattern

Sorting `createdAt desc, _id asc` is not the exact reverse of `createdAt desc, _id desc`. A different index may be required depending on the query.

### 27.2. Never Alter Business Sort Order Just to Match an Index

If the API requires `createdAt desc`, never flip it to `asc` simply to get an `IXSCAN`.

### 27.3. Explicit Sorts Ensure Correctness

Never rely on natural order or implicit index order when a query omits `.sort()`.

## 28. Covered Queries and Projection

A query can be satisfied entirely from index keys if its filter, sort, and projection only reference fields included in the index, avoiding full document fetches.

Example:

~~~javascript
orders.find(
  filterA,
  {
    _id: 0,
    tenantId: 1,
    status: 1,
    createdAt: 1
  }
).sort(sortA)
 .limit(20)
 .explain("executionStats");
~~~

### 28.1. Why Is Excluding _id Sometimes Important?

`_id` is returned by default. If an index omits `_id` while the projection includes `_id`, MongoDB must fetch the document. In our lab, the index includes `_id` in its key pattern so `_id` can still be covered; inspect the actual `explain` output.

### 28.2. Signs of a Covered Query

No `FETCH` stage and `totalDocsExamined` very low or `0` in the plan, though exact representation depends on the execution engine and plan shape.

### 28.3. Covered Queries Do Not Guarantee Fast Responses Unconditionally

Network latency, JSON decoding, client connection pooling, and serialization can still dominate tiny queries.

### 28.4. Do Not Mix Two Experiments

When measuring index benefit, keep the projection identical to baseline. When measuring projection coverage, run a second experiment with its own baseline.

## 29. Multikey Indexes and Arrays

The seed includes an `items` array field:

~~~javascript
{
  items: [
    { sku: "sku-7", qty: 2 }
  ]
}
~~~

If querying frequently by SKU:

~~~javascript
db.orders.find({
  tenantId: "tenant-07",
  "items.sku": "sku-7"
});
~~~

Candidate index:

~~~javascript
{
  tenantId: 1,
  "items.sku": 1
}
~~~

### 29.1. Indexing an Array Creates a Multikey Index

One document with many array elements produces multiple index entries. `totalKeysExamined` can exceed the number of documents examined or returned.

### 29.2. $elemMatch for Exact Semantics

If the same item must have `sku` X and `qty >= 2`, use `$elemMatch` to bind both predicates to the same element. Two separate dot-notation predicates can match across different elements.

### 29.3. Compound Multikey Restrictions

MongoDB enforces rules around multiple array fields/parallel arrays in compound indexes; check schema rules and your MongoDB version instead of blindly adding multiple array fields.

### 29.4. Do Not Create Array Indexes Just Because an Array Exists

If the API never queries `items.sku`, that index only adds write and storage overhead.

## 30. Partial Indexes

A partial index stores entries only for documents matching a declared filter expression.

Example index for `PAID` orders:

~~~javascript
// Lab-only design candidate:
db.orders.createIndex(
  {
    tenantId: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "idx_paid_tenant_created",
    partialFilterExpression: {
      status: "PAID"
    }
  }
);
~~~

### 30.1. Queries Must Qualify to Use a Partial Index

A query without a `status` restriction cannot safely use an index containing only `PAID` documents without missing records. The planner only picks a partial index when the query predicate guarantees completeness.

### 30.2. Isolate Experiments

Never create a partial index alongside Index A and guess which one improved performance. Test variants in separate labs or record exact `winningPlan`/hints where appropriate.

### 30.3. Partial Uniqueness Is Scoped

If a partial index is marked unique, uniqueness applies only to the subset matching `partialFilterExpression`. Business constraints must account for this.

## 31. Sparse and TTL Indexes Do Not Replace Query Indexes

- **Sparse index:** includes only documents containing the indexed field per index semantics; does not guarantee suitability for all filters.
- **TTL index:** asynchronously deletes documents based on server time; not a general-purpose date-query optimizer.
- **Text index:** serves full-text search semantics, unlike regex or compound sort indexes.
- **Wildcard index:** can support flexible schemas, though often less optimal than explicit key-pattern indexes.
- **Hashed index:** supports specific sharding/equality distribution needs, not B-tree range/sort traversal.

### 31.1. Each Type Serves a Different Goal

Never include a TTL index in Query A performance experiments, as it can expire data and invalidate your baseline.

### 31.2. Avoid Index Explosion

If every query shape gets its own dedicated index, writes slow down and storage/index builds become hard to manage. Prioritize workload-wide review.

## 32. Collation and Case-Insensitive Queries

A query using a different collation may not leverage an index built with an incompatible collation.

Example:

~~~javascript
db.orders.find({
  tenantId: "tenant-07",
  status: "PAID"
}).collation({
  locale: "en",
  strength: 2
}).explain("executionStats");
~~~

### 32.1. Look Beyond Field Names

Identical key patterns with differing collation options can force the planner onto a completely different path.

### 32.2. When Is Collation Needed?

Customer names, localized string sorting, and case-insensitive matching may require collation. Status enums and tenant IDs typically use exact semantics; do not change collation just to fix a query plan without validating business requirements.

### 32.3. SBE/Classic and Collation

Explain stage layouts can vary across versions. Verification still rests on correct query semantics and reasonable execution work.

## 33. Regex and Query Patterns That Utilize Indexes Poorly

Example:

~~~javascript
db.orders.find({
  customerId: {
    $regex: "0007"
  }
});
~~~

Unanchored regexes lack a prefix bound and use indexes poorly. If business logic needs an exact customer ID, use equality instead of regex.

### 33.1. Prefix Regex Is Different

Anchored prefix regexes can leverage indexes much better depending on collation and pattern. Do not generalize that all regexes ignore indexes.

### 33.2. Text Search Uses Dedicated Mechanisms

For free-text search, consider text indexes, Atlas Search, or dedicated search engines per requirements.

## 34. $in, $or, and Multi-Branch Queries

Multiple statuses example:

~~~javascript
db.orders.find({
  tenantId: "tenant-07",
  status: {
    $in: ["PAID", "PENDING"]
  }
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
~~~

### 34.1. One Index Does Not Guarantee a Global Sort

When `status` matches multiple values, entries sit across separate index ranges. The planner may merge sorted streams or perform an explicit `SORT` depending on the plan and version.

### 34.2. Selectivity and $in List Size

A tiny `$in` list behaves very differently from thousands of values. Measure actual keys examined, plan stages, and latency.

### 34.3. $or

With multiple branches, each branch can use a different index or fall back to a scan. Inspect the full plan tree, not just the top-level stage.

## 35. Aggregation Pipeline: $match, $sort, $limit

Aggregation equivalent of Query A:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-07",
      status: "PAID"
    }
  },
  {
    $sort: {
      createdAt: -1,
      _id: -1
    }
  },
  { $limit: 20 }
]);
~~~

Explain:

~~~javascript
db.orders.explain("executionStats").aggregate([
  {
    $match: {
      tenantId: "tenant-07",
      status: "PAID"
    }
  },
  {
    $sort: {
      createdAt: -1,
      _id: -1
    }
  },
  { $limit: 20 }
]);
~~~

### 35.1. The Pipeline Optimizer Can Push or Reorder Stages

Do not assume the textual order of stages in a pipeline equals the exact physical execution steps. `explain` reveals the optimized execution plan.

### 35.2. $group Changes the Workload

A `$group` pipeline by status or summing `totalMinor` must process many more documents even if it outputs only a few groups. Do not compare `nReturned` of a detail query against an aggregation report as equivalent workloads.

### 35.3. $lookup Is a Separate Experiment

`$lookup` is affected by indexes on the joined collection, cardinality, and engine behavior. Keep query shapes separate when evaluating.

## 36. Query Hints — Diagnostic Tool, Not a Default

Once the candidate index exists, you can test the query with a hint:

~~~javascript
orders.find(filterA)
  .sort(sortA)
  .limit(limitA)
  .hint("idx_tenant_status_created_id")
  .explain("executionStats");
~~~

### 36.1. Hints Help Isolate a Candidate Index

If the planner has not picked the new index, a hint lets you inspect how that index executes in the lab.

### 36.2. A Hint Does Not Prove an Index Is Better

A forced plan can be slower than the planner's winning plan. Compare metrics and correctness before adopting.

### 36.3. Never Hardcode Hints in Production Just to Pretty Up Explain

A hardcoded hint can degrade as data distribution, workloads, or indexes evolve. Apply hints only with strong justification, monitoring, and an update plan.

## 37. Hidden Indexes and Testing Missing-Index Behavior

MongoDB supports hidden indexes in compatible versions, letting the planner ignore a hidden index while still maintaining it on the write path.

Lab example:

~~~javascript
orders.hideIndex(
  "idx_tenant_status_created_id"
);

// Compare explain while hidden.

orders.unhideIndex(
  "idx_tenant_status_created_id"
);

// Compare explain when visible again.
~~~

### 37.1. Hidden Indexes Still Incur Write/Storage Cost

Hiding an index is not dropping it. It continues to be maintained, consuming storage and write overhead.

### 37.2. Never Toggle Hidden State Arbitrarily in Production

Changing planner-visible state can cause immediate latency regressions. Require change approval, metrics, and a rollback plan.

### 37.3. Using Index Visibility as an Experimental Variable in the Lab

Hiding and unhiding allows plan comparisons on the same collection without deleting data, though remember plan cache behavior and planner re-evaluation when visibility flips.

## 38. Plan Cache and Plan Variability

A query shape may reuse a cached plan or be replanned under certain conditions. Explain queries do not simulate all production plan cache behavior.

### 38.1. Never Draw Permanent Conclusions from a Single Explain

Changes in data patterns, distribution, indexes, and server versions can shift planner choices.

### 38.2. Monitor Live Queries

Compare APM data, slow query logs, and longitudinal telemetry against lab `explain` findings.

### 38.3. Never Clear the Plan Cache in Production Just to Benchmark

Doing so can disrupt live traffic; use staging or approved maintenance procedures when experimenting.

## 39. Observing Index Usage

MongoDB provides the `$indexStats` aggregation stage:

~~~javascript
orders.aggregate([
  {
    $indexStats: {}
  }
]);
~~~

### 39.1. What Does $indexStats Show?

It provides usage counters per index relative to node/version context, helping inventory unused indexes over an observation window.

### 39.2. Interpret Counters Carefully

Counters reset on restarts and may reflect unrepresentative windows. An index rarely used today could be critical for monthly reports.

### 39.3. Never Drop an Index Based Solely on $indexStats

Account for full query workloads, periodic reports, unique constraints, application dependencies, and rollback options.

## 40. Index Storage and Write Costs

Adding an index can speed up reads while introducing:

- Additional storage for index keys.
- Memory/cache pressure.
- Insert/update/delete overhead.
- Index build time.
- Replication and recovery overhead in some scenarios.
- Schema/DDL management overhead.
- Updates to indexed fields needing index entry updates.

### 40.1. Measuring Index Size

In the lab, inspect collection stats:

~~~javascript
var stats = lab.runCommand({
  collStats: "orders",
  scale: 1024 * 1024
});

printjson({
  count: stats.count,
  sizeMiB: stats.size,
  storageSizeMiB: stats.storageSize,
  totalIndexSizeMiB: stats.totalIndexSize,
  indexSizesMiB: stats.indexSizes
});
~~~

Verify fields and units against your server version's `collStats` response; record only actual figures from the lab.

### 40.2. Test Write Overhead in a Dedicated Experiment

A write-overhead test measuring inserts before and after indexing needs identical batch sizes, distributions, non-colliding IDs, warm-up, and load profiles. Never mix it into Query A timing because it mutates the dataset.

### 40.3. Fewer Indexes Is Not Automatically Enough

Retain indexes essential for correctness and unique constraints. Never sacrifice uniqueness just to trim write overhead.

## 41. Sharding and Query Targeting

In a sharded production cluster, good per-shard indexes are not enough if `mongos` must fan out to every shard.

### 41.1. Queries Must Consider the Shard Key

If a query includes the full shard key, `mongos` routes directly to the target shard. Otherwise, scatter-gather occurs, inflating overall latency.

### 41.2. Explain on a Sharded Cluster

Output includes per-shard execution and `mongos` merge stages. Never compare directly against a single-node lab and claim production will match latency.

### 41.3. Tenant Skew

A single tenant generating most data or traffic can create a hotspot; an index on `tenantId/status` does not fix shard distribution by itself.

### 41.4. Advanced Practice

Take sanitized production query shapes and verify shard targeting and `explain` on a staging sharded cluster with matching topology.

## 42. Replica Sets, Read Preference, and Cache State

An A/B experiment must keep read routing consistent.

### 42.1. Secondary Reads Can Lag

If "before" reads from primary and "after" reads from secondary, data freshness and latency can differ. Pin read preference to match the test goal and document it.

### 42.2. Primary and Secondaries Carry Different Loads

A secondary serving analytics may be heavily loaded, raising p95 latency even with an identical plan.

### 42.3. Equivalent Workload Required

Measuring peak hours against off-peak hours introduces far more confounders than the index itself.

### 42.4. Index DDL Carries Cost Across Members

In a replica set, index changes impact topology members. Never treat a tiny lab as sufficient to assess full operational risk.

## 43. Application Metrics Needed Alongside Explain

To justify an index for a production endpoint, gather:

| Layer | Metric | Meaning |
| --- | --- | --- |
| HTTP | p50/p95/p99 response latency | User-perceived latency |
| HTTP | 5xx/timeouts | Stability |
| Java driver | Command duration | MongoDB command round-trip |
| Java driver | Pool acquisition wait | Waiting for a connection |
| MongoDB | Query docs/keys examined | Server work |
| MongoDB | CPU/disk/cache | Resource impact |
| MongoDB | Slow query rate | Regressions over time |
| MongoDB | Write latency | Cost of added index |
| MongoDB | Replication lag | Replica health |
| Business | Exact result correctness | No data bugs |

### 43.1. Do Not Lump All Latency Together

A query executing in 5 ms on the server can still yield a 400 ms API response due to queuing or serialization. An index cannot fix every layer.

### 43.2. Separate Layers with Tracing

A trace should show the HTTP handler, DB call, and external calls. Compare before/after under the same version and request distribution.

## 44. Java Sync Driver: Running explain

With a compatible Java Sync Driver version, use `FindIterable.explain` to inspect the plan.

~~~java
import com.mongodb.ExplainVerbosity;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;

import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;

import org.bson.Document;
import org.bson.conversions.Bson;

public class QueryExplainDemo {

    public static void main(String[] args) {
        String uri = System.getenv(
            "MONGODB_TEST_URI"
        );

        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                "MONGODB_TEST_URI is required"
            );
        }

        try (
            MongoClient client = MongoClients.create(uri)
        ) {
            MongoDatabase db = client.getDatabase(
                "mongo_index_lab_459"
            );

            MongoCollection<Document> orders =
                db.getCollection("orders");

            Bson filter = Filters.and(
                Filters.eq(
                    "tenantId", "tenant-07"
                ),
                Filters.eq(
                    "status", "PAID"
                )
            );

            Bson sort = Sorts.orderBy(
                Sorts.descending("createdAt"),
                Sorts.descending("_id")
            );

            Document explain = orders
                .find(filter)
                .sort(sort)
                .limit(20)
                .explain(
                    ExplainVerbosity.EXECUTION_STATS
                );

            System.out.println(
                explain.toJson()
            );
        }
    }
}
~~~

### 44.1. Use a Dedicated Test URI

Never fall back to production MongoDB if the test environment variable is missing. Credentials and network must belong to the practice deployment.

### 44.2. MongoClient Lifecycle

In backend services, `MongoClient` is reused rather than opened and closed per request. This snippet runs once, so `try-with-resources` is appropriate.

### 44.3. Never Attach explain to Every Production Request

`explain` adds overhead and alters execution characteristics. Rely on telemetry/APM for production hot paths.

## 45. Java: Measuring Client-Observed Wall-Clock Time

A simple measurement:

~~~java
long startNanos = System.nanoTime();

List<Document> result = orders
    .find(filter)
    .sort(sort)
    .limit(20)
    .into(new ArrayList<>());

long durationNanos =
    System.nanoTime() - startNanos;

double durationMs =
    durationNanos / 1_000_000.0;

System.out.println(
    "Documents: " + result.size()
);

System.out.println(
    "Elapsed ms: " + durationMs
);
~~~

### 45.1. Warm-Up and Repetitions Are Required

A single sample is skewed by JIT compilation, class loading, connection setup, GC, cache, and network jitter. Use a proper test harness with warm-ups and multiple iterations.

### 45.2. Measuring Inclusive Time Intentionally

This code includes driver execution and materializing results into a `List`, not just server execution time.

### 45.3. Never Create a New Client per Sample

Doing so measures connection handshakes rather than query performance.

### 45.4. Never Load the Entire Collection into a List

Here `limit=20`. On large datasets, use cursors/pagination instead of unbounded heap loading.

## 46. Testing Correctness Alongside Performance

A lab does not end when p95 drops.

Assertions should cover:

- Only `tenant-07` returned.
- Only `PAID` status returned.
- Ordered by `createdAt` desc, `_id` desc.
- At most 20 records.
- Identical result IDs and order before and after.
- No duplicates within a page.
- `countDocuments(filterA)` matches the seed.
- Projection matches the API contract.
- Query does not drop records due to collation/type mismatch.
- No unintended updates/deletes occurred during testing.

### 46.1. Do Not Use explain to Prove Full Correctness

`explain` reports plans and counters, not tenant isolation or business semantics assertions.

### 46.2. Concurrent Update Testing Is a Separate Scope

In production with continuous writes, pagination consistency needs dedicated concurrency tests; a static lab dataset proves behavior only at a single snapshot.

## 47. Checklist to Decide Whether an Index Is Worth Creating

1. The query shape is frequent enough or affects an SLO.
2. Baseline `explain` shows high work relative to `nReturned`.
3. The candidate index supports the required filter/sort/range.
4. Post-index `explain` shows reduced work or a better plan.
5. Query result correctness is unchanged.
6. Client-observed p95 improves under equivalent workload.
7. Server CPU/I/O does not spike abnormally.
8. Write overhead and index storage are acceptable.
9. Unique/index constraints remain intact.
10. No redundant duplicate indexes are created.
11. Index build/rollout has a safe plan.
12. Rollback and regression monitoring are ready.
13. Scope of conclusions is clear: lab vs. staging vs. production.

### 47.1. If the Plan Looks Great but Latency Doesn't Drop

That is not necessarily a failure. The query may already be fast while network/application code is the bottleneck, or storage cache/CPU conditions differed.

### 47.2. If Latency Drops but docsExamined Doesn't Change

Cache warming, load shifts, topology, or run order may explain the difference. Measure further before crediting the index.

## 48. Common Measurement Mistakes

| Mistake | Consequence | How to Avoid |
| --- | --- | --- |
| Using 10 documents to compare indexes | Planner differs from production | Representative dataset |
| Measuring once per run | Noise and warm-up bias | Repeated samples |
| Comparing two queries with different filters | Different workloads | Fixed query shape |
| Adding an index and changing projection | Confounded change | Separate experiments |
| Skipping correctness checks | May return wrong data | Exact result assertions |
| Confusing explain millis with API latency | Misjudged SLO | Driver/APM/end-to-end |
| Treating `IXSCAN` as proof of optimality | Still scans huge key ranges | Check keys/docs examined |
| Treating `COLLSCAN` as always wrong | Reasonable on tiny data | Evaluate cost/selected plan |
| Ignoring `SORT` | Sort can dominate cost | Interpret all stages |
| Missing tie-breaker | Unstable pagination | Append `_id` to sort |
| Assuming fixed stage JSON layout | Automation breaks across versions | Version-aware parsing |
| Omitting MongoDB version | Hard to reproduce | Record environment metadata |
| Omitting index inventory | Dirty baseline | `getIndexes` before/after |
| Adding multiple candidate indexes at once | Unclear which index helped | One variable per trial |
| Hardcoding hints in production by default | Forced bad plan later | Hint only with evidence |
| Forgetting partial-index predicates | Query cannot use index | Check predicate implication |
| Changing collation unrecorded | Index compatibility shifts | Preserve collation |
| Ignoring multikey array size | High `keysExamined` | Inspect array cardinality |
| Huge `skip` values | Slow pagination | Keyset where appropriate |
| Comparing cold vs. warm cache | False speedup | Controlled repetitions |
| Restarting production to clear cache | Outage/disruption | Use staging |
| Ignoring write overhead | Index trade-off overlooked | Write/storage metrics |
| Ignoring sharded routing | Slow scatter-gather | Shard targeting metrics |
| Forgetting read preference | Comparing different nodes | Pin/report read path |
| Load-testing overloaded production | Incident | Isolated staging |
| No rollback plan | Hard to revert index change | Change management plan |

## 49. Exercises on Queries and Explain

### Exercise 1 — Baseline Query

On the 48,000-order dataset, write a `find` for `tenant-07`/status `PAID`, sorted by `createdAt desc, _id desc`, limit 20. Record the exact query shape.

### Exercise 2 — Distribution

Why is `status = statuses[i % 4]` unsuitable when `tenant = i % 24`? Calculate the record count per tenant/status with the chosen seed formula.

### Exercise 3 — Baseline Explain

Run `explain("executionStats")` before creating any index. Record `winningPlan`, `nReturned`, `docsExamined`, `keysExamined`, and `executionTimeMillis`.

### Exercise 4 — Query Planner Verbosity

Compare `queryPlanner`, `executionStats`, and `allPlansExecution`. Which provides runtime counters, and which includes candidate plan observations?

### Exercise 5 — Explain Stages

A plan contains `IXSCAN`, `FETCH`, and `SORT`. What does each stage mean? Why isn't `IXSCAN` alone enough to conclude the index supports the sort?

### Exercise 6 — Selectivity

A query matches 500/48,000 docs with limit 20. Explain the difference between matched count and `nReturned`.

## 50. Exercises on Compound Indexes

### Exercise 7 — ESR

Design a compound index for `tenantId/status` equality and `createdAt/_id` descending sort; explain the key order.

### Exercise 8 — Index Prefix

Compare `{tenantId,status,createdAt}` against `{status,tenantId,createdAt}` when a query filters only by `tenantId`.

### Exercise 9 — Sort Directions

Which sort orders does an index `(createdAt:-1,_id:-1)` support when scanned forward vs. backward? Analyze sorting by `createdAt:-1,_id:1`.

### Exercise 10 — Range vs. Sort

Add `totalMinor>=400000` to the query. Compare pros and cons of placing `totalMinor` before vs. after `createdAt`.

### Exercise 11 — Large Index Scan

A plan reports `keysExamined=5000, docsExamined=20, nReturned=20`. Why should the key scan still be investigated?

### Exercise 12 — Covered Query

Write a projection containing only fields inside the compound index, then inspect `FETCH`/`docsExamined`.

### Exercise 13 — Partial Index

Design an index solely for `PAID` orders. When can a query use it? Why would a query not filtering on `PAID` risk missing data?

### Exercise 14 — Array Index

Create a compound index on `tenantId/items.sku` and explain why it is multikey. When should `$elemMatch` be used?

## 51. Exercises on Measurement and Benchmarking

### Exercise 15 — A/B Timing

Run 20 groups × 10 queries before and after indexing. Record median/p95, index inventory, and environment metadata.

### Exercise 16 — Cold vs. Warm

Why might the post-index query run faster solely due to a warm cache? Design a measurement protocol that reduces bias.

### Exercise 17 — Server vs. Client

`explain` reports `executionTimeMillis=5`, while API p95 is `450 ms`. List the layers that could cause the gap and the telemetry needed.

### Exercise 18 — Result Correctness

Save `baselineIds`, create the index, rerun the exact query, and compare exact result IDs. Why must sort and limit stay identical?

### Exercise 19 — Incomplete Dataset

Seeding stopped at 25,000/48,000 records. Can it be used as a baseline? State the conditions to restart safely.

### Exercise 20 — Storage Cost

Measure `totalIndexSize` before and after adding the index. Why can't write impact be inferred from size alone?

### Exercise 21 — Concurrent Load

Compare two p95 values collected at different QPS/concurrency levels. Why is claiming a speedup unfair?

## 52. Advanced Exercises

### Exercise 22 — Customer History

Design an index for `tenantId/customerId` and sort `createdAt/_id`; explain why Query A's index is not optimal for this query.

### Exercise 23 — $in and Sort

Query `PAID` or `PENDING` for the same tenant sorted by time. How can Index A be used? Which stages must be inspected?

### Exercise 24 — Collation

A case-insensitive query changes collation. Why might the planner skip the existing index?

### Exercise 25 — Hint

Explain a scenario where a hint is used to benchmark a candidate index without forcing the hint in production code.

### Exercise 26 — Hidden Index

Design a lab hide/unhide experiment, record metrics, and verify the hidden index still incurs storage/write overhead.

### Exercise 27 — Sharded Routing

A query omits the shard key and fans out across shards. Does an index on each shard completely solve the problem?

### Exercise 28 — Index Write Regression

After adding an index, read p95 drops while insert p95 rises. What metrics and business trade-offs should be weighed?

### Exercise 29 — Production Change

Write a change proposal including index DDL, expected benefit, load risk, monitoring gates, rollback, and owner.

### Exercise 30 — Summary Report

Populate the before/after table with real measurements, distinguishing observed evidence, hypotheses, and recommendations. Propose keeping or dropping the candidate index, with caveats.

## 53. A/B Report Template for Team Review

~~~yaml
experimentId: "mongo-index-lab-459"
environment:
  type: "isolated MongoDB lab"
  serverVersion: "record actual version"
  driverVersion: "record if using Java"
  topology: "record actual topology"

dataset:
  collection: "orders"
  documents: 48000
  tenants: 24
  statuses: 4
  verified: true

query:
  filter:
    tenantId: "tenant-07"
    status: "PAID"
  sort:
    createdAt: -1
    _id: -1
  limit: 20
  projection: "same before and after"

before:
  indexes: "record actual names"
  winningPlan: "record actual stages"
  nReturned: "measured"
  totalDocsExamined: "measured"
  totalKeysExamined: "measured"
  explainExecutionTimeMillis: "measured"
  clientMedianMs: "measured"
  clientP95Ms: "measured"

candidate:
  keyPattern:
    tenantId: 1
    status: 1
    createdAt: -1
    _id: -1
  name: "idx_tenant_status_created_id"

after:
  indexes: "record actual names"
  winningPlan: "record actual stages"
  nReturned: "measured"
  totalDocsExamined: "measured"
  totalKeysExamined: "measured"
  explainExecutionTimeMillis: "measured"
  clientMedianMs: "measured"
  clientP95Ms: "measured"

correctness:
  sameIdsAndOrder: "true or false"
  sameDataset: "true or false"

costs:
  indexStorage: "measured"
  writeImpact: "requires separate test"

decision:
  recommendation: "pending actual measurements"
  caveats: "lab results do not prove production p95"
  owner: "reviewer"
~~~

### 53.1. Never Populate "measured" with Hypothetical Numbers

The template provides a framework for recording genuine evidence rather than pre-filled lab results.

### 53.2. Decisions Require Scope

An index that works well for Query A in the lab may still be suboptimal for a multi-query, write-heavy production workload.

## 54. End-to-End Execution Checklist

### Preparation

1. Test deployment verified as non-production.
2. Credentials and network access restricted.
3. MongoDB version/topology recorded.
4. Lab database free of leftover test data/indexes.
5. Deterministic dataset with full count and valid BSON types.
6. Seed count and distribution verified.
7. Query shape and target SLO explicitly written down.

### Baseline

8. `getIndexes` saved.
9. Query result IDs and order saved.
10. `explain` verbosity recorded.
11. `nReturned`/`docsExamined`/`keysExamined` recorded.
12. `winningPlan` and blocking `SORT` identified.
13. Repeated latency samples saved.
14. No concurrent writers mutating the dataset.

### Candidate Index

15. Equality/sort/range predicates classified.
16. Key order has clear rationale.
17. Explicit index name assigned.
18. Storage/write cost assessed.
19. DDL run only in the lab or under approved change control.
20. Never introduce multiple candidate indexes into the same measurement.

### After and Conclusion

21. Query and settings match baseline exactly.
22. Post-change index inventory saved.
23. Post-change `explain` analyzed.
24. Result IDs and order remain identical.
25. Median/p95 measured across multiple repetitions.
26. Cache/load differences documented.
27. Docs/keys examined and sort stages compared.
28. Write/storage impact weighed.
29. Do not extrapolate `explain` millis into end-to-end SLOs.
30. Report states observations, caveats, and decision.
31. If deploying, canary/rollback/monitoring are prepared.
32. Never drop production data or indexes following lab steps.

## 55. Quick Practice Runbook

~~~text
DEFINE:
  Choose one important query shape
  Record filters, projection, sort, limit and SLO

SETUP:
  Verify dedicated lab DB
  Seed fixed data
  Check count and distribution
  Ensure no candidate index exists

BASELINE:
  Capture getIndexes
  Capture result IDs
  Capture explain executionStats
  Capture repeated wall-clock samples

DESIGN:
  Write hypothesis
  Choose compound index key pattern
  Estimate index/write trade-offs

APPLY:
  Create named index in lab

REMEASURE:
  Same query and same dataset
  Capture explain and timing
  Compare IDs, nReturned, examined, SORT

INTERPRET:
  Separate facts from assumptions
  Check confounding cache/load/topology
  Decide whether candidate index is useful

REPORT:
  Save before/after metrics
  State limitations
  Propose production rollout only with approval
~~~

## 56. Conclusion

Practical MongoDB index optimization does not end with **`createIndex`**. A reliable workflow is:

- **Start from the access pattern:** filters, sort, limit, data distribution, and SLOs.
- **Measure the baseline first:** index inventory, `explain`, examined counters, and repeated latency samples.
- **Design indexes around a hypothesis:** equality/sort/range, cardinality, and cost.
- **Change one variable at a time:** never alter the query, projection, or dataset alongside the index.
- **Inspect explain afterward:** check whether the planner performs less work and whether any blocking sort remains.
- **Verify result correctness:** IDs, order, tenant scope, and business semantics must remain intact.
- **Measure across layers:** `explain` for server work; Java/APM for client latency; load metrics for system-wide impact.
- **Weigh trade-offs:** storage, writes, replication, sharding, cache, and index maintenance.
- **Report honestly:** never present assumed numbers as experimental results, and never treat a single `IXSCAN` as proof of permanent optimality.

With **before/after evidence and reproducibility**, adding an index becomes a verified engineering decision rather than guesswork—forming the foundation for scaling MongoDB safely as data and traffic grow.

## References

- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual — Query Plans](https://www.mongodb.com/docs/manual/core/query-plans/)
- [MongoDB Manual — Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB Manual — Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/)
- [MongoDB Manual — ESR Guideline](https://www.mongodb.com/docs/manual/tutorial/equality-sort-range-guideline/)
- [MongoDB Manual — Covered Queries](https://www.mongodb.com/docs/manual/core/query-optimization/#covered-query)
- [MongoDB Manual — Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/)
- [MongoDB Manual — Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/)
- [MongoDB Manual — Hidden Indexes](https://www.mongodb.com/docs/manual/core/index-hidden/)
- [MongoDB Manual — Index Statistics](https://www.mongodb.com/docs/manual/reference/operator/aggregation/indexStats/)
- [MongoDB Manual — Query Optimization](https://www.mongodb.com/docs/manual/core/query-optimization/)
- [MongoDB Manual — Sharding](https://www.mongodb.com/docs/manual/sharding/)
- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
