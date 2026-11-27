# Testing Performance and Query Plans Without Relying on Random Timing Metrics

> **Module:** Database Engine Document MongoDB  
> **Chapter:** Testing  
> **Lesson:** Testing Performance and Query Plans Without Relying on Random Timing Metrics

## 1. The Problem: A Query Is Slow Today and Fast Tomorrow?

A Java development team writes an API query:

~~~javascript
db.orders.find({
  tenantId: "tenant-03",
  status: "PAID"
}).sort({
  createdAt: -1
}).limit(10);
~~~

They write a simple test:

~~~java
long start = System.nanoTime();

List<Document> result = orders.find(filter)
        .sort(descending("createdAt"))
        .limit(10)
        .into(new ArrayList<>());

long elapsedMs =
        TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - start);

assertTrue(elapsedMs < 100);
~~~

This test might pass on a developer's laptop yet fail in CI. One minute later, a re-run passes. The query did not change; the index did not change; the results are still right.

Why?

- The CI runner shares CPU with other jobs.
- The JVM/JIT has not warmed up yet.
- MongoDB just started, and the WiredTiger cache is cold.
- DNS/TLS/connection pooling introduces variance.
- The OS is flushing the page cache or performing I/O.
- The query planner just selected a plan, whereas another run hits the plan cache.
- Background writes/compaction/checkpoints vary over time.
- The container hits CPU throttling.
- Network scheduling fluctuates.
- The test dataset is too small for a collection scan to differ noticeably from an index scan.

The core issue: **measured wall-clock time reflects the entire environment**, not a stable property of the query itself.

MongoDB performance testing should be split into two tiers:

1. **Deterministic query efficiency regression testing**: fixed datasets, correctness assertions, index contracts, `explain("executionStats")`, `docsExamined`, `keysExamined`, `nReturned`, query shapes, and scan-cost budgets.
2. **Benchmarking / load testing**: measuring p50/p95/p99 latency, throughput, CPU, I/O, and resource usage in a controlled environment using statistical methods and trend analysis — never hardcoding tight millisecond assertions on every CI run.

### 1.1. Learning Objectives

After this lesson, you will be able to:

- Understand why assertions like `executionTimeMillis < 50` or `System.nanoTime() < 100ms` are typically flaky.
- Read `queryPlanner` and `executionStats` accurately.
- Distinguish `IXSCAN`, `COLLSCAN`, `FETCH`, blocking `SORT`, covered queries, and query engine variations.
- Write assertions based on **budgeted scan cost** rather than raw milliseconds.
- Build representative yet reproducible datasets and query shapes.
- Choose strong metrics such as `totalDocsExamined`, `totalKeysExamined`, `nReturned`, and index specifications.
- Avoid brittle tests that assert an exact full `winningPlan` tree.
- Test with and without indexes using `hint` and negative controls.
- Write JUnit integration tests with the MongoDB Java Sync Driver.
- Understand the role of Testcontainers, isolated CI environments, and deterministic seeding.
- Recognize the effects of the plan cache, classic engine, SBE, sharding, and MongoDB server versions.
- Distinguish a performance regression gate from statistical benchmarking.
- Design a triage workflow when a query-plan test fails.

---

## 2. Three Types of Testing Often Mixed Together

| Type | Question | Metrics to Use | Run on Every CI Commit? |
|---|---|---|---|
| **Correctness test** | Does the query return the right data? | Documents, ordering, filters, projections | Yes |
| **Query efficiency regression test** | Does the query scan minimal data and use a suitable index? | Explain metrics, index catalog, scan budgets | Yes, with stable fixtures |
| **Performance benchmark** | What latency/throughput does the query achieve on this infrastructure? | p50/p95/p99, ops/s, CPU, cache/I/O, error rate | Separate / scheduled runs |

### 2.1. Correctness Does Not Prove Performance

The following two plans can return the exact same ten documents:

```text
Plan A:
  IXSCAN tenantId/status/createdAt
  docsExamined = 10
  nReturned = 10

Plan B:
  COLLSCAN over 100,000 documents
  blocking SORT
  docsExamined = 100000
  nReturned = 10
```

A unit or integration test verifying only returned results will pass for both.

### 2.2. Query Efficiency Does Not Prove Latency SLAs

A query with `docsExamined = 10` can still be slow when:

- Storage I/O is saturated.
- The server is undergoing failover.
- The connection pool is exhausted.
- Network RTT is high.
- Documents are very large.
- Write locks or resource contention occur.
- The query executes inside a complex aggregation.
- Application serialization becomes a bottleneck.

Efficiency assertions therefore do not replace benchmarking and production monitoring.

### 2.3. Benchmarking Does Not Replace Correctness or Plan Testing

A benchmark reporting 30 ms today can mask a planner using `COLLSCAN` simply because the dataset is still small or fits completely in RAM. When the collection grows to 10 million documents, latency can spike dramatically.

Good testing combines all three layers, but **never uses the same assertion to measure everything**.

---

## 3. Timing Metrics Not to Use as Sole Pass/Fail Conditions

### 3.1. Measuring in the Java Application

~~~java
long elapsed = System.nanoTime() - start;
assertTrue(elapsed < TimeUnit.MILLISECONDS.toNanos(50));
~~~

Sources of noise:

- JVM warmup / JIT compilation.
- GC pauses / safepoints.
- OS thread scheduling.
- Driver server selection.
- Connection pool checkout.
- TLS/network overhead.
- Test runner contention.
- BSON decoding.
- MongoDB server load.

### 3.2. Measuring in `mongosh`

~~~javascript
const t0 = Date.now();
db.orders.find({ status: "PAID" }).toArray();
print(Date.now() - t0);
~~~

This is an end-to-end measurement dependent on client, process, and host conditions. It is useful for quick observation, not as a hard query-plan invariant.

### 3.3. `executionStats.executionTimeMillis`

MongoDB `explain("executionStats")` reports:

```javascript
{
  executionStats: {
    executionTimeMillis: 3,
    totalKeysExamined: 10,
    totalDocsExamined: 10,
    nReturned: 10
  }
}
```

Official documentation notes that `executionTimeMillis` **does not necessarily represent actual execution time**. Explain can include plan-selection overhead and bypass the plan cache, whereas production traffic using cached plans or hints incurs different costs.

Do not write:

~~~javascript
const plan = db.orders.find(filter)
  .explain("executionStats");

if (plan.executionStats.executionTimeMillis > 10) {
  throw new Error("Query regression");
}
~~~

as a mandatory assertion on arbitrary CI runners.

### 3.4. `allPlansExecution` Does Not Make Timing Stable

`allPlansExecution` reports trial execution statistics for candidate plans alongside the winning plan. It helps diagnose how the planner made its choice, not turn milliseconds into a stable specification.

### 3.5. Where Timing Belongs

Use latency and throughput measurements in a **dedicated benchmark environment**, collecting many samples, tracking percentiles, documenting hardware/dataset/concurrency, keeping historical trends, and analyzing variance. Never merge that benchmark into a single-shot query-plan test.

---

## 4. Explain: Three Verbosity Levels

MongoDB supports:

1. `queryPlanner`.
2. `executionStats`.
3. `allPlansExecution`.

### 4.1. `queryPlanner`

Example:

~~~javascript
db.orders.find({
  tenantId: "tenant-03",
  status: "PAID"
}).sort({
  createdAt: -1
}).limit(10).explain("queryPlanner");
~~~

Returns query planner details along with winning and rejected plans, without requiring full execution stats.

### 4.2. `executionStats`

~~~javascript
db.orders.find({
  tenantId: "tenant-03",
  status: "PAID"
}).sort({
  createdAt: -1
}).limit(10).explain("executionStats");
~~~

At this level, MongoDB executes the winning plan to produce runtime metrics. This is the primary choice for **efficiency regression tests**.

### 4.3. `allPlansExecution`

~~~javascript
db.orders.find({
  tenantId: "tenant-03",
  status: "PAID"
}).sort({
  createdAt: -1
}).limit(10).explain("allPlansExecution");
~~~

Adds partial trial execution statistics for candidate plans evaluated during plan selection. Do not treat raw counters from rejected plans as full query execution numbers.

### 4.4. Beware of Different Defaults Between Commands and Helpers

`cursor.explain()` and `db.collection.explain()` commonly default to `queryPlanner`, whereas the database `explain` command may have different defaults depending on the API.

Tests should always specify **verbosity explicitly** instead of relying on implicit defaults.

### 4.5. Does Explain Execute Write Operations?

According to MongoDB docs, explain for write operations describes how records would be matched and what modifications **would** occur, without actually **applying modifications** to the database.

Even so, production testing should avoid turning explain on complex bulk writes into unnecessary load; `executionStats` still consumes resources evaluating predicates.

---

## 5. Two Key Output Sections: `queryPlanner` and `executionStats`

An explain output **abbreviated for illustration**:

~~~javascript
{
  queryPlanner: {
    namespace: "plan_lab.orders",
    winningPlan: {
      stage: "LIMIT",
      inputStage: {
        stage: "FETCH",
        inputStage: {
          stage: "IXSCAN",
          indexName: "idx_tenant_status_created",
          keyPattern: {
            tenantId: 1,
            status: 1,
            createdAt: -1
          }
        }
      }
    }
  },
  executionStats: {
    nReturned: 10,
    executionTimeMillis: 2,
    totalKeysExamined: 10,
    totalDocsExamined: 10
  }
}
~~~

**Do not treat this as a guaranteed MongoDB schema.** The `winningPlan` tree differs across the classic engine, Slot-Based Execution (SBE), EXPRESS fast paths, sharded clusters, and MongoDB versions.

### 5.1. `queryPlanner`

Reports:

- Namespace / query shape.
- Winning plan.
- Rejected plans (when present).
- Indexes considered by the planner.
- Plan cache / query identifier metadata depending on server version.

### 5.2. `executionStats`

Reports winning-plan metrics:

- `nReturned`.
- `totalDocsExamined`.
- `totalKeysExamined`.
- `executionTimeMillis` (for reference only, not a hard CI threshold).
- Execution stage details and additional engine-specific counters.

### 5.3. Why Assert Total Scan Work Instead of Timings?

With a fixed dataset, a well-indexed query normally inspects orders of magnitude fewer keys and documents than a collection scan. Scan counters measure **logical work**, which stays far more stable across OS and network fluctuations.

However, scan counters **are not strictly immutable either**: they can shift slightly when the planner, engine, indexes, or data change. Design reasonable budgets and test intent rather than locking a single exact count to the unit.

---

## 6. Strong Metrics for Regression Tests

| Field | Question | Suitable Assertion |
|---|---|---|
| `executionStats.nReturned` | How many rows did the query return? | Exact expected count on fixed fixtures |
| `executionStats.totalDocsExamined` | How many documents were examined? | Upper bound based on result/budget |
| `executionStats.totalKeysExamined` | How many index entries were examined? | Upper bound for indexed queries |
| `queryPlanner.winningPlan` | What access path did the planner choose? | Flexible parser inspecting index/stage |
| `indexName` | Which index was used? | Index contract when genuinely critical |
| `keyPattern` | Index key ordering? | Dedicated index-schema verification |
| `SORT` stage | Is there a blocking sort? | Engine/version-aware check |
| `COLLSCAN` stage | Is there a collection scan? | Observe carefully in dataset context |
| `totalKeysExamined/nReturned` | Index scan efficiency | Heuristic / budget |
| `executionTimeMillis` | Explain estimated runtime | Log for diagnostics, not as a hard gate |

### 6.1. Do Not Assert Exact `docsExamined` Across Every Version

Avoid:

~~~java
assertEquals(10, docsExamined);
~~~

Prefer:

~~~java
assertTrue(docsExamined <= 25);
~~~

when fixtures and the business query should only examine around 10 documents via a proper index.

Why use a budget? Minor differences in planner behavior, index coverage, mapping, or optimizer versions can slightly alter examined counts. You want to catch a 10 -> 50,000 regression, not break builds over micro-details.

### 6.2. Do Not Compute a Naive Ratio When `nReturned = 0`

Consider this heuristic:

```text
scanRatio = docsExamined / max(nReturned, 1)
```

When `nReturned = 0`, the ratio remains a rough indicator, but do not treat it as a true scanned-to-returned ratio.

In tests, use an **absolute upper bound** combined with result correctness.

### 6.3. `totalKeysExamined = 0` Alone Does Not Prove a Fast Query

If `totalKeysExamined = 0` and `totalDocsExamined = 100000`, the query likely performed a collection scan. Checking only `keysExamined < 30` is insufficient.

### 6.4. `docsExamined = 0` Can Be a Great Sign

A **covered query** reads index keys and satisfies the entire projection without fetching documents. In that case, `totalDocsExamined = 0` is completely expected.

Never write tests requiring `docsExamined >= nReturned` across all queries.

### 6.5. `nReturned` Does Not Always Equal Business Entities Returned by the API

Aggregations, grouping, pagination, cursor batches, and sharded pipelines have different semantics. For a simple `limit(10)` query, `nReturned = 10` is straightforward. For a `$group` pipeline returning 1 aggregated row across 100k documents, that single row does not mean only 1 document was scanned.

---

## 7. `IXSCAN`, `COLLSCAN`, `FETCH`, and Related Stages

### 7.1. `IXSCAN`

`IXSCAN` represents scanning entries within an index. Relevant fields include:

- `indexName`.
- `keyPattern`.
- `indexBounds`.
- `direction`.

An `IXSCAN` alone does not guarantee efficiency: if index bounds are overly wide and scan millions of keys, the query still consumes heavy resources.

### 7.2. `COLLSCAN`

`COLLSCAN` scans documents directly in the collection. It is expensive for selective queries over large collections.

However, `COLLSCAN` is **not always a bug**:

- Very small collections.
- Queries returning nearly every document.
- Intentional analytics or full-scan batch jobs.
- Cases where the optimizer judges an index unhelpful.

CI tests should forbid `COLLSCAN` **only where the workload contract demands index access**, not blindly on every MongoDB query.

### 7.3. `FETCH`

`FETCH` indicates MongoDB retrieves full documents after scanning index keys. When a projection is covered by the index, `FETCH` may disappear or be optimized away depending on the engine.

### 7.4. `SORT`

A blocking `SORT` stage appears when no chosen index satisfies the requested sort order. Check:

- Equality filter prefixes.
- Index key ordering.
- Sort directions.
- Collation settings.
- Multikey constraints.
- Whether the index can satisfy the sort.

Do not assume every `SORT` is a defect: batch analytics sorting large subsets may legitimately require it.

### 7.5. SBE and EXPRESS Stages

Modern MongoDB releases include the Slot-Based Execution Engine; certain fast paths emit `EXPRESS_IXSCAN` or `EXPRESS_CLUSTERED_IXSCAN` instead of traditional `IXSCAN`.

An assertion like:

~~~text
winningPlan.stage == "IXSCAN"
~~~

easily breaks across engine changes even when the query remains fast.

### 7.6. Plan Trees Have No Single Fixed JSON Path

Classic example:

```text
queryPlanner.winningPlan.inputStage.inputStage.stage
~~~

An SBE plan may instead expose:

```text
queryPlanner.winningPlan.queryPlan.stage
queryPlanner.winningPlan.slotBasedPlan
~~~

Sharded outputs add per-shard branches. Never assume `winningPlan.inputStage.stage` exists across every cluster topology and server version.

---

## 8. Principles for Writing Stable Plan Tests

### 8.1. Test Three Things

1. **Returned data is accurate**.
2. **Eligible index/query shape exists**.
3. **Examined work stays within budget**.

### 8.2. Avoid Hardcoding Diagnostic Details

Never gate CI on:

- Exact `executionTimeMillis`.
- Per-stage `executionTimeMillisEstimate`.
- Fixed `planCacheKey` or query hashes.
- Exact nested stage depth.
- Every field in explain JSON.
- Ordering of rejected plans.
- Candidate plan scores.
- Raw timestamps, hostnames, or `queryPlanner` internals.

### 8.3. Use Budgets with Safety Margins

Example:

```text
Expected nReturned = 10
Good path docsExamined ~ 10
Collection scan docsExamined ~ 20000

CI budget:
  totalDocsExamined <= 100
  totalKeysExamined <= 200
~~~

The safety margin remains orders of magnitude below a 20,000-doc scan regression.

### 8.4. Base Budgets on Measurements and Domain Reality, Not Guesses

Build representative fixtures, inspect explain with the intended index, and choose a budget wide enough not to couple to one internal plan representation while tight enough to catch an order-of-magnitude scan regression.

### 8.5. Never Generate Nondeterministic Test Scenarios

Do not seed data using:

~~~javascript
Math.random()
~~~

without a fixed seed and expect identical selectivity on every CI run.

Use deterministic data generation and verify exact cardinalities.

---

## 9. Sufficiently Large Fixtures with Clear Selectivity

A dataset of 5–10 documents makes `COLLSCAN` completely reasonable. To catch missing-index regressions, seed enough data to create clear separation.

### 9.1. Fixture Design

Example with 8 tenants and 1,000 orders per tenant:

```text
8 tenants x 1000 orders = 8000 documents

Per tenant:
  500 PAID
  500 PENDING

Query:
  tenantId = tenant-03
  status = PAID
  sort createdAt desc
  limit 10
~~~

Goals:

- 500 matching documents for the tenant+status pair.
- A proper index inspects only ~10 entries.
- A collection scan inspects thousands of documents.
- Expected results are completely predictable.
- Sort order is deterministic.

### 9.2. Sample Document Schema

```json
{
  "_id": "tenant-03-0998",
  "tenantId": "tenant-03",
  "status": "PAID",
  "amount": 998,
  "createdAt": {
    "$date": "2026-01-01T16:38:00Z"
  }
}
```

Deterministic values allow exact assertions on returned results.

### 9.3. Suitable Index

```javascript
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
~~~

- `tenantId` is an equality field.
- `status` is an equality field.
- `createdAt` is the sort field.

This follows the ESR (Equality, Sort, Range) guideline. Do not assume it is automatically optimal for every workload.

### 9.4. Why the Default `_id` Index Does Not Suffice

The `_id` index locates individual documents by ID, but filtering by `tenantId` and `status` while sorting by `createdAt` cannot be efficiently served by `_id` alone without a matching predicate.

### 9.5. Sizing for CI Resources

8,000 documents is an illustrative size. Depending on CI capacity, 2,000 or 20,000 may fit better. What matters is creating a **wide enough gap** between a good plan and a degraded scan.

---

## 10. Seeding Fixtures via `mongosh`

Run strictly in a **dedicated lab database**, never production.

### 10.1. Preparing the Database

```javascript
const lab = db.getSiblingDB("plan_lab");
const orders = lab.getCollection("orders");
~~~

The commands below assume `plan_lab.orders` is empty. If prior test data exists, use a fresh isolated database or follow lab cleanup procedures without accidentally dropping other collections.

### 10.2. Generating Deterministic Data

```javascript
const base = ISODate("2026-01-01T00:00:00Z");
let batch = [];

for (let tenant = 0; tenant < 8; tenant++) {
  const tenantId = "tenant-" +
    String(tenant).padStart(2, "0");

  for (let i = 0; i < 1000; i++) {
    const status = i % 2 === 0
      ? "PAID"
      : "PENDING";

    batch.push({
      _id: tenantId + "-" +
        String(i).padStart(4, "0"),
      tenantId: tenantId,
      status: status,
      amount: i + 100,
      createdAt: new Date(base.getTime() + i * 60000)
    });

    if (batch.length === 500) {
      orders.insertMany(batch);
      batch = [];
    }
  }
}

if (batch.length > 0) {
  orders.insertMany(batch);
}

print("total=" + orders.countDocuments({}));
~~~

### 10.3. Verifying Fixtures

```javascript
print("tenant-03 PAID=" +
  orders.countDocuments({
    tenantId: "tenant-03",
    status: "PAID"
  }));
~~~

Expected output:

```text
total=8000
tenant-03 PAID=500
~~~

If counts do not match, stop before inspecting plans; mismatched counts point to fixture setup bugs rather than query optimizer bugs.

### 10.4. Creating the Index

```javascript
orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_tenant_status_created" }
);

printjson(orders.getIndexes());
~~~

---

## 11. Analyzing the Indexed Query

### 11.1. Query

```javascript
const filter = {
  tenantId: "tenant-03",
  status: "PAID"
};

const cursor = orders.find(filter)
  .sort({ createdAt: -1 })
  .limit(10);
~~~

### 11.2. Correctness Verification

```javascript
const documents = cursor.toArray();

print("count=" + documents.length);
print("firstId=" + documents[0]._id);
~~~

There are 500 matches. Since `createdAt` increases monotonically with `i`, sorting descending with `limit(10)` returns the 10 largest even `i` values starting at 998.

### 11.3. Explain

```javascript
const explain = orders.find(filter)
  .sort({ createdAt: -1 })
  .limit(10)
  .explain("executionStats");

printjson({
  nReturned: explain.executionStats.nReturned,
  totalDocsExamined:
    explain.executionStats.totalDocsExamined,
  totalKeysExamined:
    explain.executionStats.totalKeysExamined,
  executionTimeMillis:
    explain.executionStats.executionTimeMillis
});
~~~

With the right index, keys/docs examined will typically be close to the number of returned documents (exact numbers can vary slightly across server versions and engines). Do not hardcode an exact assertion of `10` without first verifying behavior.

### 11.4. Illustrative Budget Check

```javascript
const stats = explain.executionStats;

if (stats.nReturned !== 10) {
  throw new Error("Unexpected result count");
}

if (stats.totalDocsExamined > 30) {
  throw new Error(
    "Too many documents examined: " +
      stats.totalDocsExamined);
}

if (stats.totalKeysExamined > 50) {
  throw new Error(
    "Too many keys examined: " +
      stats.totalKeysExamined);
}
~~~

**Note:** The `30`/`50` bounds are specific to this fixture and query. Never copy them blindly as universal rules for production queries.

### 11.5. Why Not Assert `executionTimeMillis`?

Even against identical fixtures and indexes, runtime fluctuates with CPU, cache warmth, JIT, I/O, and plan selection. A healthy test should pass whether the exact same logical work finishes in 2 ms or 25 ms.

---

## 12. Negative Control: Intentionally Forcing a Collection Scan

A test that only passes when an index exists does not prove the budget can actually catch regressions. Run a **negative control** in the lab.

### 12.1. Forcing a Natural Collection Scan via Hint

```javascript
const naturalExplain = orders.find({
  tenantId: "tenant-03",
  status: "PAID"
})
  .sort({ createdAt: -1 })
  .limit(10)
  .hint({ $natural: 1 })
  .explain("executionStats");

printjson({
  docs: naturalExplain.executionStats.totalDocsExamined,
  keys: naturalExplain.executionStats.totalKeysExamined,
  returned: naturalExplain.executionStats.nReturned
});
~~~

The `$natural` hint forces natural collection scanning where supported. On this fixture, `docsExamined` will be substantially larger than on the indexed path.

### 12.2. Comparison

```text
With index, optimizer picks optimal path:
  nReturned = 10
  docsExamined ~ 10
  keysExamined ~ 10

Forced natural scan:
  nReturned = 10
  docsExamined ~ 8000
  keysExamined = 0
~~~

These figures are **illustrative**, not live measurements; actual counters vary slightly by version and engine.

### 12.3. Why Negative Controls Matter

They verify that a degraded scan plan would genuinely trip the CI budget of `docsExamined <= 30`.

### 12.4. Never Hint Indexes in Main Tests Meant to Verify the Planner

Wrong way to test whether the planner picks an index automatically:

```javascript
orders.find(filter)
  .hint("idx_tenant_status_created")
  .explain("executionStats");
~~~

If the main test forces a hint, you only prove the index exists and is usable — **not that the planner picks it during normal execution**.

Separate these clearly:

- **Main test (no hint):** lets the optimizer choose freely; validates scan budgets.
- **Diagnostic hinted test:** compares index candidates A vs. B.
- **Negative control:** forces natural scan or uses an unindexed fixture in a separate test database.

### 12.5. Never Drop Indexes on Shared Databases

Never execute:

```javascript
db.orders.dropIndex("idx_tenant_status_created");
~~~

on shared staging or production just to verify a test fails.

Use an isolated disposable database with hints or dedicated setup for control tests. Index DDL disrupts plan caches and concurrent operations.

---

## 13. Verifying Index Contracts Separately from Explain

When performance depends on a compound index created by migrations:

```javascript
{
  tenantId: 1,
  status: 1,
  createdAt: -1
}
~~~

create a dedicated **index catalog test**.

### 13.1. Why?

A developer might accidentally remove an index migration while all query-correctness tests continue passing. When CI spins up a fresh database, the index is missing and scan budgets fail. An index catalog test surfaces the exact missing index immediately.

### 13.2. `mongosh`

```javascript
const indexes = orders.getIndexes();

const expected = indexes.find(
  i => i.name === "idx_tenant_status_created");

if (!expected) {
  throw new Error("Missing expected index");
}

printjson(expected.key);
~~~

### 13.3. Key Order Matters Greatly

Compound indexes:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
~~~

and:

```javascript
{ createdAt: -1, status: 1, tenantId: 1 }
~~~

are not equivalent across query shapes.

Assert exact key order and directions, not merely the presence of the three field names.

### 13.4. Index Options Also Matter

An index can be:

- Partial.
- Sparse.
- Unique.
- Collation-specific.
- Hidden.
- TTL.
- Multikey.
- Wildcard.
- Hashed.

Matching names and keys alone does not guarantee matching semantics. When correctness or performance relies on partial filters or collation, verify critical index options explicitly.

### 13.5. Hidden Indexes

A hidden index remains visible in the catalog, yet the query planner ignores it during normal planning. A test checking only index existence could pass even while a plan regression happens in production.

Combine catalog checks with no-hint explain tests.

---

## 14. Summary Table of Assertion Design Principles

| Goal | Preferred Assertion | Avoid |
|---|---|---|
| Accurate result count | `nReturned == expected` and data assertions | Checking only milliseconds |
| Prevent large collection scans | `totalDocsExamined <= budget` | Asserting exact full plan JSON |
| Prevent overly wide index scans | `totalKeysExamined <= budget` | Checking only for `IXSCAN` |
| Verify index contracts | `listIndexes` checking keys/options | Checking index name while ignoring key order |
| Prevent heavy blocking sorts | Engine/fixture-aware stage & work checks | Hardcoding `winningPlan.inputStage...` across versions |
| Verify covered queries | `docsExamined ~ 0` with projection/index contract | Expecting every `IXSCAN` to be covered |
| Catch latency/timeout regressions | Dedicated benchmarks & monitoring | Single-run `executionTimeMillis < 5` |
| Inspect production plans | Slow logs, profiler, `$planCacheStats`, telemetry | Treating `explain` as a plan-cache lookup |
| Negative controls | Natural hint in isolated test DB | Dropping indexes on shared clusters |

---

## 15. Java Sync Driver: Running `explain("executionStats")`

The MongoDB Java Sync Driver exposes `FindIterable.explain(...)`.

Java example:

```java
import com.mongodb.ExplainVerbosity;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;

import org.bson.Document;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Sorts.descending;

public class ExplainExample {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_TEST_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException(
                    "MONGODB_TEST_URI must point to a test database");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("plan_lab");
            MongoCollection<Document> orders =
                    db.getCollection("orders");

            Document explain = orders
                    .find(and(
                            eq("tenantId", "tenant-03"),
                            eq("status", "PAID")))
                    .sort(descending("createdAt"))
                    .limit(10)
                    .explain(ExplainVerbosity.EXECUTION_STATS);

            Document stats =
                    explain.get("executionStats", Document.class);

            long nReturned =
                    ((Number) stats.get("nReturned")).longValue();
            long docsExamined =
                    ((Number) stats.get("totalDocsExamined")).longValue();
            long keysExamined =
                    ((Number) stats.get("totalKeysExamined")).longValue();

            System.out.printf(
                    "returned=%d docs=%d keys=%d%n",
                    nReturned, docsExamined, keysExamined);
        }
    }
}
~~~

### 15.1. Why Cast to `Number`?

BSON numeric values can decode as `Integer` or `Long` depending on value magnitude and driver codecs. Writing:

```java
stats.getLong("totalDocsExamined")
~~~

can fail when the field arrives as Int32. Casting via `((Number) value).longValue()` safely normalizes numeric types after checking presence.

### 15.2. Why Omit `executionTimeMillis`?

The goal of the test is preventing scan regressions. You may log timing as diagnostic context, never as a single-run pass/fail gate.

### 15.3. Error Handling

If `executionStats` or expected fields are missing:

- Check verbosity.
- Check query type.
- Check topology/sharded output structure.
- Check server/driver compatibility.
- Never silently default missing metrics to `0` and pass the test.

Failing with clear diagnostic messages is far better than masking an explain schema change.

---

## 16. JUnit 5: Complete Integration Test Without Millisecond Assertions

This example uses the MongoDB Java Sync Driver, JUnit 5, and a test MongoDB instance configured via `MONGODB_TEST_URI`. It uses a **uniquely named database** to prevent collisions across test runs.

### 16.1. Test Goals

- Seed 8,000 deterministic documents.
- Create the compound index.
- Assert result correctness.
- Assert `totalDocsExamined <= 30`.
- Assert `totalKeysExamined <= 50`.
- Verify the index exists in the catalog.
- Make zero assertions on `executionTimeMillis`.
- Clean up only the dedicated test database.

### 16.2. JUnit Code

```java
import com.mongodb.ExplainVerbosity;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.IndexOptions;
import org.bson.Document;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.UUID;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Indexes.ascending;
import static com.mongodb.client.model.Indexes.compoundIndex;
import static com.mongodb.client.model.Sorts.descending;
import static org.junit.jupiter.api.Assertions.*;

class QueryPlanRegressionTest {

    private static final String INDEX_NAME =
            "idx_tenant_status_created";

    private static MongoClient client;
    private static MongoDatabase database;
    private static MongoCollection<Document> orders;

    @BeforeAll
    static void setupDatabase() {
        String uri = System.getenv("MONGODB_TEST_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException(
                    "MONGODB_TEST_URI is required for this test");
        }

        // Must be a dedicated disposable MongoDB TEST instance.
        client = MongoClients.create(uri);

        String dbName = "plan_regression_" +
                UUID.randomUUID().toString().replace("-", "");

        database = client.getDatabase(dbName);
        orders = database.getCollection("orders");

        final Instant base =
                Instant.parse("2026-01-01T00:00:00Z");

        List<Document> batch = new ArrayList<>(500);

        for (int tenant = 0; tenant < 8; tenant++) {
            String tenantId = String.format(
                    Locale.ROOT, "tenant-%02d", tenant);

            for (int i = 0; i < 1000; i++) {
                String id = String.format(
                        Locale.ROOT, "%s-%04d", tenantId, i);

                Document order = new Document("_id", id)
                        .append("tenantId", tenantId)
                        .append("status",
                                i % 2 == 0 ? "PAID" : "PENDING")
                        .append("amount", i + 100)
                        .append("createdAt",
                                Date.from(base.plusSeconds(i * 60L)));

                batch.add(order);

                if (batch.size() == 500) {
                    orders.insertMany(batch);
                    batch = new ArrayList<>(500);
                }
            }
        }

        if (!batch.isEmpty()) {
            orders.insertMany(batch);
        }

        orders.createIndex(
                compoundIndex(
                        ascending("tenantId", "status"),
                        com.mongodb.client.model.Indexes.descending(
                                "createdAt")),
                new IndexOptions().name(INDEX_NAME));
    }

    @AfterAll
    static void cleanup() {
        try {
            if (database != null) {
                // Only the uniquely named test database.
                database.drop();
            }
        } finally {
            if (client != null) {
                client.close();
            }
        }
    }

    @Test
    void returnsCorrectOrdersAndRespectsScanBudget() {
        var filter = and(
                eq("tenantId", "tenant-03"),
                eq("status", "PAID"));

        List<Document> results = orders.find(filter)
                .sort(descending("createdAt"))
                .limit(10)
                .into(new ArrayList<>());

        assertEquals(10, results.size());
        assertEquals("tenant-03-0998",
                results.get(0).getString("_id"));

        for (Document result : results) {
            assertEquals("tenant-03",
                    result.getString("tenantId"));
            assertEquals("PAID",
                    result.getString("status"));
        }

        for (int i = 1; i < results.size(); i++) {
            Date previous = results.get(i - 1).getDate("createdAt");
            Date current = results.get(i).getDate("createdAt");
            assertFalse(previous.before(current),
                    "Sort order must be descending");
        }

        Document explain = orders.find(filter)
                .sort(descending("createdAt"))
                .limit(10)
                .explain(ExplainVerbosity.EXECUTION_STATS);

        Document stats =
                explain.get("executionStats", Document.class);

        assertNotNull(stats,
                "Expected executionStats in explain output");

        long returned = number(stats, "nReturned");
        long docs = number(stats, "totalDocsExamined");
        long keys = number(stats, "totalKeysExamined");

        assertEquals(10L, returned);
        assertTrue(docs <= 30,
                "Docs examined too high: " + docs);
        assertTrue(keys <= 50,
                "Keys examined too high: " + keys);

        // Intentionally no executionTimeMillis assertion.
    }

    @Test
    void declaresExpectedIndex() {
        boolean found = false;

        for (Document idx : orders.listIndexes()) {
            if (INDEX_NAME.equals(idx.getString("name"))) {
                Document key = idx.get("key", Document.class);

                assertEquals(
                        new Document("tenantId", 1)
                                .append("status", 1)
                                .append("createdAt", -1),
                        key);

                found = true;
                break;
            }
        }

        assertTrue(found,
                "Expected compound index not found");
    }

    private static long number(Document document, String key) {
        Object value = document.get(key);

        assertNotNull(value, "Missing metric: " + key);
        assertTrue(value instanceof Number,
                "Metric is not numeric: " + key);

        return ((Number) value).longValue();
    }
}
~~~

### 16.3. Strengths

- Zero `elapsedMs < N` conditions.
- Deterministic fixtures.
- Fresh, isolated test database per run.
- Result correctness assertions included.
- Scan budgets tight enough to catch a collection scan over 8,000 docs.
- Index metadata verified independently.
- JDBC/HTTP/app timings kept out of efficiency assertions.

### 16.4. Safety Warning

`cleanup()` calls `database.drop()`. Only run this against an **isolated MongoDB test instance** with `MONGODB_TEST_URI` properly scoped to a disposable target and appropriately restricted user permissions. Never point it at shared staging or production.

In real projects, add safety guards via test profiles, container networking, or host/cluster allowlists so tests can never accidentally drop a real database.

### 16.5. Why Not Assert the Index Name Directly in the Main Test?

The example uses the **index contract** and **scan budget** as dual guardrails without coupling to internal planner tree shapes. When a use case genuinely requires verifying the selected index, add a flexible `winningPlan` inspector as shown in the next section.

---

## 17. Checking Used Index Names with a Flexible Parser

When you need to confirm the planner chose a specific index, traverse the explain structure recursively instead of relying on a rigid field path.

### 17.1. Java Helper

```java
import org.bson.Document;

import java.util.HashSet;
import java.util.List;
import java.util.Set;

public final class ExplainIndexNames {

    private ExplainIndexNames() {
    }

    public static Set<String> collect(Document explain) {
        Set<String> names = new HashSet<>();
        Object planner = explain.get("queryPlanner");
        visit(planner, names);
        return names;
    }

    private static void visit(Object value, Set<String> names) {
        if (value instanceof Document) {
            Document document = (Document) value;

            Object name = document.get("indexName");
            if (name instanceof String) {
                names.add((String) name);
            }

            for (Object child : document.values()) {
                visit(child, names);
            }
        } else if (value instanceof List<?>) {
            for (Object child : (List<?>) value) {
                visit(child, names);
            }
        }
    }
}
~~~

### 17.2. Usage in Tests

```java
Set<String> usedIndexes = ExplainIndexNames.collect(explain);

assertTrue(
        usedIndexes.contains("idx_tenant_status_created"),
        "Expected index not present in planner output: " +
                usedIndexes);
~~~

### 17.3. Limitations of the Simple Helper

- Candidate/rejected plans inside `queryPlanner` can also carry `indexName`. Traversing all of `queryPlanner` may pick up **an index from `rejectedPlans`**, which does not prove the winning plan used it.
- Sharded and SBE outputs introduce multiple branches and different stage shapes.
- Internal field layouts can shift across versions.
- Some stages do not emit `indexName` in the classic format.

Therefore, to inspect the **winning index**, start traversal specifically at `queryPlanner.winningPlan` (and winning subplans), never `rejectedPlans`.

### 17.4. Traversing Only `winningPlan`

```java
Document planner =
        explain.get("queryPlanner", Document.class);
assertNotNull(planner);

Object winning = planner.get("winningPlan");

Set<String> names = new java.util.HashSet<>();

// Use a dedicated visit helper strictly on the winning branch.
// Do not include rejectedPlans as proof of the winning index.
~~~

You can refactor the helper to accept `Object winningPlan` and walk only that subtree. If supporting multiple MongoDB major versions, validate the parser against representative outputs for each engine and topology.

### 17.5. When Is a Scan Budget Alone Sufficient?

If the actual requirement is "the API fetches 10 orders without scanning thousands of docs," bounding `totalDocsExamined` and `totalKeysExamined` couples far less to implementation details than asserting a specific index name.

When a query also requires specific ordering or predicates, combining index catalog checks + correctness + scan budgets provides solid protection.

---

## 18. Testing Blocking `SORT` and Index Sort Order

Consider the query:

```javascript
db.orders.find({
  tenantId: "tenant-03",
  status: "PAID"
}).sort({
  createdAt: -1
}).limit(10);
~~~

It can leverage:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
~~~

for both filtering and sorting.

### 18.1. If the Index Omits `createdAt`

An index on just:

```javascript
{ tenantId: 1, status: 1 }
~~~

narrows down the 500 matching records, yet still requires sorting them by `createdAt` before returning the top 10.

### 18.2. How to Check

Inspect `SORT`-related stages and scan work in explain. A recursive stage helper looks like:

```java
static boolean containsStage(Object value, String wanted) {
    if (value instanceof Document) {
        Document d = (Document) value;
        Object stage = d.get("stage");

        if (wanted.equals(stage)) {
            return true;
        }

        for (Object child : d.values()) {
            if (containsStage(child, wanted)) {
                return true;
            }
        }
    } else if (value instanceof List<?>) {
        for (Object child : (List<?>) value) {
            if (containsStage(child, wanted)) {
                return true;
            }
        }
    }
    return false;
}
~~~

### 18.3. Why `SORT` Assertions Are Fragile

SBE may represent execution using different stage names/fields, and the optimizer can push down or fuse stages.

Therefore:

- On a **pinned-version test matrix**, asserting stage `SORT` works when you know the exact output format.
- For **multi-version suites**, prefer semantic checks and scan budgets, capturing the plan structure as diagnostic output on failure.
- Never rely on `containsStage(winningPlan, "SORT") == false` as a cross-version guarantee.

### 18.4. Presence of `SORT` Does Not Always Need Fixing

If a workload intentionally sorts hundreds of thousands of records for a batch report, a blocking sort may be acceptable when memory/SLOs are sized accordingly. Ground tests in explicit business expectations.

---

## 19. Testing Covered Queries

A query is covered by an index when all filtered and projected fields can be satisfied straight from index entries without fetching full documents under eligible conditions.

### 19.1. Covered Index Example

```javascript
db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1,
    amount: 1
  },
  {
    name: "idx_orders_cover"
  }
);
~~~

Query:

```javascript
const plan = db.orders.find(
  { tenantId: "tenant-03", status: "PAID" },
  { _id: 0, tenantId: 1, status: 1, createdAt: 1, amount: 1 }
)
  .sort({ createdAt: -1 })
  .limit(10)
  .hint("idx_orders_cover")
  .explain("executionStats");

printjson({
  n: plan.executionStats.nReturned,
  docs: plan.executionStats.totalDocsExamined,
  keys: plan.executionStats.totalKeysExamined
});
~~~

When properly covered, `totalDocsExamined` can be **0**.

### 19.2. Why Must the Projection Exclude `_id`?

MongoDB projects `_id` by default. If `_id` is not in the index, the engine must fetch documents just to retrieve `_id`. Specify `_id: 0` or intentionally include `_id` in the index after evaluating the storage trade-off.

### 19.3. Multikey Indexes and Collation

Covered queries have strict limitations involving:

- Multikey array fields.
- Collation.
- Specific query operators.
- Projection shapes.
- Index types.
- Server versions.

Do not assume simply putting all field names into an index always yields `docsExamined = 0`.

### 19.4. Avoid Forcing Coverage via Hints in Production-Path Tests

Hints are handy for testing whether an index *can* cover a query. Keep main tests hint-free so you verify the optimizer naturally picks an efficient path; if it does not, investigate why rather than masking it with a hint.

---

## 20. Plan Cache: Explain Does Not Prove Which Plan Is Cached

A crucial point highlighted in MongoDB documentation:

> Explain **bypasses the existing plan cache** and prevents the winning plan from that explain run from entering the cache.

Implications:

- Explain reveals how the optimizer evaluates a query at test time.
- However, it **does not fully reflect steady-state execution** when an application relies on cached plans.
- A passing explain test does not guarantee the current production cached plan matches.
- `executionTimeMillis` in explain can include plan-evaluation costs absent from steady-state traffic.

### 20.1. DDL Can Invalidate the Query Plan Cache

Creating, dropping, or hiding indexes or altering schema/index settings can invalidate cached plans for the collection.

Consequently, a benchmark run right after an index migration may behave differently from one measured after steady-state warmup.

### 20.2. `$planCacheStats`

MongoDB provides the `$planCacheStats` aggregation stage to inspect cached plans where privileges and topology permit.

~~~javascript
db.orders.aggregate([
  { $planCacheStats: {} }
]);
~~~

Output depends on server version, engine, and live cache state. Never assert exact full `$planCacheStats` documents in CI.

### 20.3. `explain` vs. Production Logs

If production slow logs show `planSummary: COLLSCAN` while staging explain after adding an index shows `IXSCAN`, there is not necessarily a contradiction:

- Different plan caches.
- Different data distributions.
- Different indexes.
- Different query shapes or parameter values.
- Different server versions/engines.
- Different collations or hints.
- Different execution nodes or shards.

Capture full context before drawing conclusions.

### 20.4. Never Clear the Plan Cache Carelessly in Production

Use `planCacheClear` or DDL only via an intentional runbook when justified; it is never a routine "reset" step to embed in CI suites targeting shared clusters.

---

## 21. Query Shapes and Parameter Selectivity

Two queries:

```javascript
{ tenantId: "tenant-01", status: "PAID" }
{ tenantId: "tenant-03", status: "PAID" }
~~~

share the same shape yet may see very different data distributions.

### 21.1. Why Can the Same Shape Perform Differently?

One tenant has 500 orders; another has 5 million. Fetching the top 10 with a proper index stays fast, whereas an unbounded query or full aggregation can diverge dramatically.

### 21.2. Do Not Test Only One Parameter Literal

Cover a representative matrix:

- Small tenant.
- Large / hot tenant.
- Common status.
- Rare status.
- Narrow date range.
- Wide date range.
- Matches found vs. zero matches.
- First page vs. deep pages.

### 21.3. Never Use Purely Random Data

Use deterministic fixtures with **deliberately modeled distributions**, such as:

```text
tenant-small: 200 orders
tenant-medium: 5,000 orders
tenant-hot: 100,000 orders

status:
  PAID: 80%
  PENDING: 15%
  CANCELLED: 5%
~~~

All proportions must seed identically every time.

### 21.4. Query Shape Hashes Are Not Permanent Test IDs

Field names and semantics such as `queryHash`, `planCacheShapeHash`, and `queryShapeHash` evolve across MongoDB versions. Do not hardcode shape hashes in cross-release assertions.

---

## 22. ESR: Equality, Sort, Range and Index Regressions

ESR is a guideline for ordering compound index keys:

- **Equality** predicates first.
- **Sort** keys when helpful.
- **Range** predicates positioned thoughtfully relative to selectivity.

Example:

```javascript
db.orders.find({
  tenantId: "tenant-03",
  status: "PAID",
  createdAt: { $gte: ISODate("2026-01-01T05:00:00Z") }
}).sort({ createdAt: -1 }).limit(10);
~~~

Candidate index:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
~~~

### 22.1. Why Index Key Order Matters

If an index leads with `amount` yet the query never predicates on `amount`, it cannot narrow filters or satisfy sorting as expected.

### 22.2. Testing Range Predicates

Fixtures must include sufficient out-of-range documents so a range-scan regression clearly increases `keysExamined` and `docsExamined`.

### 22.3. Avoid Applying ESR Dogmatically

Some workloads combine a highly selective range predicate with sorting over a tiny subset, where an ERS ordering can perform better according to documentation and measurements. Test candidate access paths against real workloads instead of following rules mechanically.

### 22.4. Combine Index Definitions and Explain Tests

- Index catalog checks catch missing indexes or altered key orders.
- Explain budgets catch wide scans.
- Correctness tests catch wrong filtering or sorting.
- Benchmarks measure real workload latency.

---

## 23. Multikey Indexes and Examined Key Counts

An array field generates multiple index keys from a single document.

Example:

```javascript
{
  _id: 1,
  tenantId: "tenant-01",
  tags: ["promo", "vip", "mobile"]
}
~~~

Index:

```javascript
{ tenantId: 1, tags: 1 }
~~~

### 23.1. Why Can `keysExamined` Exceed `docsExamined`?

A single document produces multiple index entries under a multikey array structure. Therefore:

```text
keysExamined = 100
docsExamined = 20
nReturned = 20
~~~

does not automatically mean the planner malfunctioned.

### 23.2. Tests Must Account for Array Cardinality

If fixture `tags` arrays grow 10x longer, key scan budgets can change even with identical queries and indexes. Keep fixture cardinality deterministic and update budgets consciously when data models intentionally evolve.

### 23.3. `$elemMatch` and Correlated Predicates

Queries over arrays can achieve tighter multikey index bounds when `$elemMatch` expresses correlated element matching. Never add `$elemMatch` solely to coerce an index if doing so alters query semantics.

### 23.4. Do Not Assert `keysExamined == nReturned` Everywhere

Equality queries, ranges, multikey indexes, duplicate values, sparse indexes, and partial indexes naturally produce `keysExamined` differing from `nReturned`.

---

## 24. Partial Indexes, Sparse Indexes, and Collation

### 24.1. Partial Indexes

```javascript
db.orders.createIndex(
  { tenantId: 1, createdAt: -1 },
  {
    name: "idx_active_by_tenant",
    partialFilterExpression: { active: true }
  }
);
~~~

This index contains only documents matching the partial filter.

Queries must include predicates proving eligibility so the planner can safely use the index. If a query does not guarantee `active: true`, the planner skips the partial index to avoid missing documents.

### 24.2. CI Tests Should Exercise Partial Semantics

Verify:

1. Queries specifying `active: true`.
2. Queries omitting `active`.
3. Clear distribution of active vs. inactive documents.
4. Catalog inspection confirming `partialFilterExpression`.
5. Appropriate explain budgets for each variant.

### 24.3. Collation

An index built with a specific collation will not be used as intended by queries carrying mismatched collations.

For case-insensitive search, treat both index collation and query collation as **parts of the query contract**.

### 24.4. Sparse / Unique Indexes

Sparse indexes omit documents lacking the indexed field. Unique sparse/partial indexes have distinct semantics; never assume index presence guarantees usability for every query shape.

### 24.5. Hashed / Wildcard / Text Indexes

Specialized indexes exhibit distinct explain stages and applicability rules compared with standard B-tree compound indexes. Tailor scan budgets to the index type rather than copying thresholds from `status/createdAt` queries.

---

## 25. Aggregation Pipelines: Testing Work Rather Than Millis

Example pipeline:

```javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-03", status: "PAID" } },
  { $sort: { createdAt: -1 } },
  { $limit: 10 },
  { $project: { _id: 0, amount: 1, createdAt: 1 } }
]);
~~~

### 25.1. Place `$match` Early When Semantics Permit

Pushing selective filters earlier allows index utilization, though the optimizer also rewrites stages automatically. Never assume every manual pipeline rewrite preserves semantics across `$group` or `$unwind` boundaries.

### 25.2. Explaining Aggregations

```javascript
const aggPlan = db.orders.explain("executionStats")
  .aggregate([
    { $match: { tenantId: "tenant-03", status: "PAID" } },
    { $sort: { createdAt: -1 } },
    { $limit: 10 },
    { $project: { _id: 0, amount: 1, createdAt: 1 } }
  ]);

printjson(aggPlan);
~~~

Aggregation explain output may expose `stages`, `queryPlanner`, and SBE-specific nested objects depending on pipeline shape and server version.

### 25.3. Never Assume `totalDocsExamined` Always Lives at the Top Level

In aggregations and sharded pipelines, counters may live inside nested sections. When tests parse stats:

- Know the exact explain layout of the target MongoDB version.
- Extract counters from the proper stages/shards.
- Avoid double-counting across stages or shards.
- Document parser assumptions clearly.

### 25.4. `$group` and `nReturned`

This pipeline:

```javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $group: { _id: "$tenantId", count: { $sum: 1 } } }
]);
~~~

may return 8 summary rows while scanning thousands of orders. A high scan-to-returned ratio is inherent to aggregation.

### 25.5. Spill Metrics

Large sort/group stages may spill to disk depending on data size and memory limits. Depending on version and engine, explain reports counters such as `usedDisk`, `spills`, or `spilledBytes`.

You can enforce a **spill/memory budget** in version-pinned tests without coupling cross-version assertions to exact nested field paths.

### 25.6. `$lookup`

Pipelines joining with `$lookup` need testing for foreign-collection indexes, fan-out, cardinality, and result correctness. Top-level stage document counts do not capture every nested collection scan transparently.

---

## 26. Sharded Clusters: One Explain Reflects Multiple Execution Nodes

In a sharded cluster:

```text
Java application
      |
      v
mongos
  ├── shardA
  ├── shardB
  └── shardC
~~~

### 26.1. Query Targeting

When a query includes an eligible shard key, `mongos` routes to specific shards. Otherwise, it broadcasts scatter-gather queries across all shards.

### 26.2. Why Replica-Set Tests Are Not Enough for Sharding

Plan tests on an unsharded collection cannot validate:

- Shard targeting vs. scatter-gather.
- Router/merge overhead.
- Per-shard index availability.
- Balancer / chunk distribution skew.
- Cross-shard merge-sort behavior.

### 26.3. Sharded Explain Structure Differs

Sharded explain outputs contain per-shard sections and merge stages. Do not assume all counters sit neatly under a single top-level:

```text
executionStats.totalDocsExamined
~~~

### 26.4. Shard-Aware Budgets

Topology-aware tests can assert:

- Number of targeted shards when the explain output exposes it reliably.
- Per-shard docs/keys examined.
- Aggregated totals summed **once** without double-counting.
- Absence of unintended scatter-gather broadcasts.
- Correctness of merged results, sorting, and limits.

### 26.5. Never Sum Shard Durations to Estimate HTTP Latency

Shards execute in parallel. Adding individual shard times linearly does not yield total response latency; measure end-to-end router, network, and merge times instead.

### 26.6. Should Sharded Plan Tests Run on Every PR?

Spinning up full sharded clusters can be costly. A balanced strategy:

- Fast replica-set contract tests on every PR.
- Sharded topology integration tests nightly or pre-release.
- Production telemetry segmented by query shape.

---

## 27. Classic Engine, SBE, and Cross-Version Evolution

MongoDB includes multiple execution engines. Explain plan trees are not an immutable API contract.

### 27.1. Classic Plan

May look like:

```text
LIMIT
  FETCH
    IXSCAN
~~~

### 27.2. SBE Plan

May contain:

```text
queryPlanner.winningPlan.queryPlan
queryPlanner.winningPlan.slotBasedPlan
~~~

### 27.3. EXPRESS Path

MongoDB 8.0+ introduces specialized EXPRESS stages for supported simple shapes, such as `EXPRESS_IXSCAN`. Asserting the literal token `IXSCAN` misses valid indexed fast paths.

### 27.4. Writing Resilient Tests

Prioritize:

1. Data correctness.
2. Index catalog contracts.
3. Aggregate scan budgets.
4. Optional plan-stage diagnostics.
5. Version-specific stage assertions only when strictly needed inside a pinned test matrix.

### 27.5. MongoDB Stable API Does Not Guarantee Explain JSON Structure

MongoDB documentation explicitly states **there is no guaranteed stable output format for `explain`**, even under the Stable API. Never build cross-version test suites on full explain JSON equality.

### 27.6. Server Upgrades

Before upgrading major MongoDB versions:

- Capture baseline explain summaries for key queries.
- Run CI index and scan-budget tests against the target version.
- Separate parser-schema changes from true scan regressions.
- Review release notes for optimizer and SBE changes.
- Run isolated workload benchmarks.
- Never raise scan budgets merely to make failing upgrade tests green without explanation.

---

## 28. When the Planner Picks `COLLSCAN` Despite an Existing Index

Common reasons:

- Very small collection.
- Low index selectivity.
- Query matches most documents.
- Index cannot satisfy sort or collation.
- Query predicate does not satisfy `partialFilterExpression`.
- Index is hidden.
- Data distribution shifted.
- Cost-model differences across server versions.

### 28.1. Why You Should Not Ban `COLLSCAN` Globally

An assertion like:

```java
assertFalse(explain.toJson().contains("COLLSCAN"));
~~~

can fail falsely when `COLLSCAN` appears inside `rejectedPlans`, trial execution metadata, or a legitimately small lookup table.

### 28.2. The Right Approach

Inspect:

- The winning plan in context.
- Scan budgets.
- Query correctness.
- Index contracts.
- Actual workload intent.

### 28.3. When the Planner Picks an Unexpected Plan

Investigate systematically:

1. Is the dataset large enough?
2. Has index creation completed?
3. Do filters, sorts, and collations match the index?
4. Is a field projection blocking coverage?
5. Is the index hidden or partial?
6. Is production hitting a different cached plan?
7. Which MongoDB Server version and engine executed it?
8. Did concurrent writes alter collection statistics?

---

## 29. Separating CI Regression Gates from Benchmark Suites

Recommended pipeline:

```text
Pull Request
   │
   ├── Unit tests
   ├── Integration correctness tests
   ├── Index migration/catalog tests
   └── Explain scan-budget tests
          │
          └── PASS/FAIL independent of elapsedMs

Nightly / Pre-release
   │
   ├── Workload replay / benchmark
   ├── Controlled load/concurrency
   ├── p50/p95/p99 latency
   ├── Throughput/error rate
   ├── CPU/IO/cache/replication
   └── Trend comparison, regression review

Production
   │
   ├── APM/tracing
   ├── Slow-operation logs
   ├── Controlled profiler
   ├── Query shape telemetry
   └── SLO-based alerting
~~~

### 29.1. Why Maintain Two Pipelines?

PR CI demands speed and determinism. Benchmarks require stable dedicated hardware, longer runs, and statistical rigor.

### 29.2. CI Can Still Log Diagnostic Timings

Recording `executionTimeMillis` or wall-clock duration in test logs helps investigation without serving as a pass/fail threshold.

### 29.3. Should Every Tier Have Timeouts?

Set **generous safety timeouts to catch hung tests** (preventing infinite integration hangs), but treat those as liveness safeguards rather than performance regression assertions.

Tight CI timeouts will still flake.

---

## 30. Proper Latency Benchmarking Methodology

To verify whether an API meets a 100 ms SLO, run genuine latency benchmarks.

### 30.1. Controlled Environment

- Dedicated MongoDB instance/cluster.
- Consistent server version and FCV.
- Production-representative indexes, schemas, and datasets.
- Fixed hardware and cgroup allocations.
- No noisy neighbor jobs running concurrently.
- Predictable network RTT.
- Properly sized connection pools.
- Production read/write concerns.
- Matching replica-set/sharded topology where applicable.

### 30.2. Warmup

Allow the JVM, driver pools, TLS sessions, OS/WiredTiger caches, and query plan cache to stabilize before recording samples.

However, if production traffic experiences cold starts, measure **warm** and **cold** scenarios explicitly as separate runs.

### 30.3. Concurrency

Single-threaded benchmarks miss lock, pool, and CPU contention visible at 1,000 concurrent requests.

Sweep multiple concurrency levels:

- 1 client.
- 10 concurrent clients.
- 100 concurrent clients.
- Peak representative concurrency.

Ensure the load generator itself does not saturate and masquerade as database latency.

### 30.4. Percentiles

Instead of a single `42 ms` sample:

```text
p50 = 18 ms
p95 = 45 ms
p99 = 96 ms
max = 340 ms
error rate = 0.05%
~~~

These numbers are illustrative; percentiles describe latency distributions far better than single points or averages.

### 30.5. Repeated Runs

Repeat benchmark runs under identical settings and compare distributions and confidence intervals. Never conclude an upgrade is "4% slower" from a single run.

### 30.6. Bootstrap Confidence Intervals

Bootstrapping across independent runs or block-level aggregates helps quantify uncertainty. Avoid naive request-level resampling when observations exhibit strong autocorrelation.

### 30.7. Measure Throughput Alongside Latency

A change might lower p95 at 100 ops/s yet slash maximum throughput at 1,000 ops/s. Always record offered arrival rates and concurrency alongside latency.

### 30.8. Separate Query Time from API Time

Measure distinctly:

- MongoDB command latency.
- End-to-end HTTP latency.
- Driver connection-pool wait time.
- Application serialization.
- Network overhead.
- Retries.

Per-layer timing pinpoints where bottlenecks actually sit.

---

## 31. Is JMH Suitable for MongoDB Query Benchmarks?

JMH excels at Java microbenchmarks such as BSON serialization or CPU-bound mapping code, whereas network database queries involve major external components outside the JVM.

### 31.1. Where JMH Shines

- Comparing BSON encoding/decoding overhead.
- Comparing domain mapping transformations.
- Benchmarking custom codecs.
- Measuring client-side query builder allocations.

### 31.2. Where JMH Falls Short

- Replica-set replication throughput.
- Storage-backed index scan performance.
- Network latency and packet jitter.
- Sharded router (`mongos`) overhead.
- Write concern replication lag.
- Connection-pool behavior under realistic concurrency.

Run system-level load tests and workload benchmarks rather than relying solely on JMH.

### 31.3. Keep JMH Out of Standard Unit Tests

JMH requires forked JVMs, warmup iterations, and controlled measurement windows that are slow and noisy inside standard PR CI.

---

## 32. Testcontainers and Isolating MongoDB Test Environments

Testcontainers provides disposable MongoDB containers for integration tests.

### 32.1. Benefits

- Reproducible MongoDB server versions.
- Isolated per-run databases.
- Zero impact on production.
- Portable across container-capable CI runners.
- Clean teardown.
- Easy replica-set initialization for transaction or change-stream tests.

### 32.2. Pin Image Versions

Never use `latest` for query-plan regression gates if you expect stable behavior. Pin exact major/minor versions or immutable image digests per policy.

Example setup manifest:

```text
MongoDB test image: pinned release
Java driver: pinned via dependency management
Fixture generator version: 3
Index migration version: 12
Query contract version: 2
~~~

### 32.3. `MongoDBContainer` APIs Vary Across Testcontainers Versions

Imports, package names, and helper constructors change across Testcontainers major releases. Avoid blindly copying outdated snippets.

In the JUnit example earlier, injecting `MONGODB_TEST_URI` decouples assertion code from container provisioning so any compatible harness or Testcontainers setup can supply the URI cleanly.

### 32.4. Replica Set vs. Standalone?

For routine find `explain`/index-read checks, a single `mongod` test instance often suffices. Tests exercising transactions, causal sessions, or change streams require an initialized replica set.

### 32.5. Test Environments Differ from Production Yet Remain Valuable

Testcontainers does not replicate production disks, network topology, or data scale. Its strength is enforcing **logical scan regression gates**, not replacing production benchmarks.

### 32.6. Safe Data Cleanup

Use a unique database name per run ID so `database.drop()` can never hit a shared or production database by mistake.

---

## 33. Standard CI Setup for Query-Plan Tests

### 33.1. Separate Setup from Test Execution

1. Start the test MongoDB instance.
2. Apply schema/index migrations.
3. Seed deterministic fixtures.
4. Validate fixture counts and distributions.
5. Run correctness assertions.
6. Run explain scan-budget tests.
7. Record diagnostic plan summaries on failure.
8. Tear down isolated data cleanly.

### 33.2. Why Apply Real Migrations?

If tests create indexes manually in setup while production migrations omit them, plan tests pass in CI while production hits slow scans.

Pair two test checks:

- **Migration contract test:** executes real migrations and verifies the resulting index catalog.
- **Query behavior test:** seeds data and enforces scan budgets against the migrated schema/indexes.

Together they prevent unindexed releases.

### 33.3. Never Share Mutable State Across Unordered Tests

If Test A drops an index while Test B runs `explain` on the same database, outcomes depend on execution order and concurrency.

Enforce:

- Unique database per test class or run.
- Zero shared mutable plan cache or index DDL.
- Clear setup and cleanup ownership.
- Strict test isolation.

### 33.4. Capture Diagnostics on Failure

When a budget assertion fails, log:

- Query name and shape.
- Fixture counts.
- MongoDB server version.
- Index names and keys (no secrets).
- `nReturned`.
- `totalDocsExamined`.
- `totalKeysExamined`.
- Sanitized `winningPlan` summary.
- Configured budgets.

Never dump raw query documents containing PII into logs.

---

## 34. Named Query Contract Pattern

Instead of repeating explain parsing in every test, create a small abstraction:

```java
public record QueryBudget(
        String name,
        long expectedReturned,
        long maxDocsExamined,
        long maxKeysExamined) {
}
~~~

Example:

```java
QueryBudget recentPaidOrders = new QueryBudget(
        "recent-paid-orders",
        10,
        30,
        50);
~~~

### 34.1. Assertion Helper

```java
static void assertBudget(
        Document explain,
        QueryBudget budget) {

    Document stats =
            explain.get("executionStats", Document.class);

    if (stats == null) {
        throw new AssertionError(
                "Missing executionStats for " + budget.name());
    }

    long returned =
            ((Number) stats.get("nReturned")).longValue();
    long docs =
            ((Number) stats.get("totalDocsExamined")).longValue();
    long keys =
            ((Number) stats.get("totalKeysExamined")).longValue();

    if (returned != budget.expectedReturned()) {
        throw new AssertionError(
                budget.name() + " returned " + returned);
    }

    if (docs > budget.maxDocsExamined()) {
        throw new AssertionError(
                budget.name() + " docsExamined " + docs);
    }

    if (keys > budget.maxKeysExamined()) {
        throw new AssertionError(
                budget.name() + " keysExamined " + keys);
    }
}
~~~

### 34.2. Benefits

- Query budgets carry meaningful business names.
- Easy to review in pull requests.
- Prevents conflating milliseconds with scan budgets.
- Scales cleanly across workload tiers.
- Eliminates assertion boilerplate.

### 34.3. Limitations

The helper above assumes an unsharded `find` explain with top-level `executionStats`. Aggregations and sharded explains need dedicated adapters and explicit handling for nested or missing fields.

### 34.4. Budgets Are Not Production SLAs

`maxDocsExamined = 30` is a **logical work guardrail**. p95 latency SLOs still require benchmarking and APM monitoring.

---

## 35. Empty vs. Non-Empty Results and Sort Stability

### 35.1. Queries Returning Matches

Against deterministic fixtures, assert exact counts, field values, and sort ordering.

### 35.2. Queries Returning Zero Matches

Example:

```javascript
db.orders.find({
  tenantId: "tenant-not-exist",
  status: "PAID"
}).explain("executionStats");
~~~

With a proper index, empty-result queries examine very few entries. Since `nReturned = 0` confuses ratio metrics, stick to absolute upper bounds for docs and keys examined.

### 35.3. Sort Tie-Breakers

If multiple documents share identical `createdAt` timestamps, sorting only on `createdAt` leaves relative order undefined among tied records.

Always add a deterministic secondary tie-breaker:

```javascript
db.orders.find(filter)
  .sort({ createdAt: -1, _id: 1 })
  .limit(10);
~~~

When doing so, include `_id: 1` in the candidate index so the entire sort stays covered by index order:

```javascript
{
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: 1
}
~~~

### 35.4. Why Test Tie-Breakers?

Unstable pagination sorting can skip or duplicate records across page boundaries even when explain metrics look great.

### 35.5. Never Alter Query Shapes in Tests vs. Production

Tests must match production query shapes exactly: filters, sorts, projections, limits, skips, collations, and options. Testing a modified sort invalidates both plan and correctness conclusions for the real API.

---

## 36. Pagination: `skip` vs. Keyset Cursors

### 36.1. Large `skip`

```javascript
db.orders.find({ tenantId: "tenant-03" })
  .sort({ createdAt: -1 })
  .skip(900)
  .limit(10);
~~~

Even with an index, MongoDB must step through hundreds of index keys just to skip the first 900 entries.

### 36.2. Keyset Pagination

Instead of `skip`, seek from a cursor boundary:

```javascript
db.orders.find({
  tenantId: "tenant-03",
  createdAt: { $lt: ISODate("2026-01-01T12:00:00Z") }
}).sort({ createdAt: -1 }).limit(10);
~~~

This is a simplified illustration. When timestamps can collide, use a lexicographic tuple predicate pairing `createdAt` and `_id` alongside a matching compound index.

### 36.3. Test Both Shallow and Deep Pages

If the API supports jumping to page 1,000, do not test only page 1. Build sufficiently deep fixtures and define deep-page budgets and benchmarks.

### 36.4. Keyset Pagination Changes Semantics Slightly

Keyset pagination alters API contracts, relies on unique tie-breakers, and behaves differently under concurrent inserts or deletes between pages.

---

## 37. Geospatial, Text, and Vector Workloads Need Dedicated Metrics

Do not force a single `docsExamined <= 30` threshold across every specialized search engine.

### 37.1. Geospatial

`2dsphere` indexes generate candidate grid matches followed by exact geometry checks. Efficiency testing must evaluate index applicability, distances, false-positive filtering, and correctness.

### 37.2. Text Search

Full-text search evaluates relevance scoring across posting lists; returning 10 top-ranked documents can legitimately examine many index postings and documents.

### 37.3. Vector Search

Atlas Vector Search and specialized search pipelines emit completely different query plans and telemetry than core `find`. Never assume `explain.executionStats.totalDocsExamined` has the same semantics or field path.

### 37.4. Tailor Tests to the Operator

- Correctness and ranking stability.
- Index definitions.
- Engine-appropriate explain/search metrics.
- Relevance quality.
- Specialized workload benchmarks.

Never reuse B-tree equality budgets for approximate nearest-neighbor search.

---

## 38. Cold Cache vs. Warm Cache

### 38.1. Cold Cache

Queries incur disk reads, raising latency even when `docsExamined` is tiny.

### 38.2. Warm Cache

The identical query runs far faster once hot data and index pages reside in WiredTiger and OS caches.

### 38.3. Explain Budgets Stay Steadier Than Timings

Because `docsExamined` and `keysExamined` track logical access paths, they stay mostly stable across cache states while `executionTimeMillis` fluctuates wildly.

Still, scan counts are not strictly immutable across optimizer, data, index, or engine changes.

### 38.4. Benchmarks Must Declare Cache State

Warm-state benchmarks cannot predict cold-start tail latencies. Test two explicit modes where supported:

- Controlled cold/post-restart state (when infrastructure permits).
- Warm steady-state workload.

### 38.5. Never Flush OS Caches on Shared CI Hosts

Flushing page caches or restarting MongoDB disrupts concurrent jobs on shared machines. Isolate cache experiments on dedicated benchmark nodes.

---

## 39. How Slow Query Logs and the Database Profiler Complement Regression Tests

### 39.1. Slow-Operation Logs

MongoDB diagnostic logs record:

- Namespace.
- Plan summary.
- Duration.
- Docs/keys examined.
- Query shape / identifiers.
- Operation type.

These logs help pinpoint **real queries that deserve regression contract tests**.

### 39.2. Database Profiler

`system.profile` captures fine-grained operation details when enabled at an appropriate level, though profiling adds runtime overhead.

### 39.3. Never Use Slow Logs as the Sole CI Assertion

If a CI run runs under the slow-ms threshold, nothing gets logged. Absence of slow-log entries does not prove a query is indexed.

### 39.4. Sample Representative Production Queries from Telemetry

Production telemetry reveals:

- Most expensive API routes.
- Query shapes scanning excessive documents.
- Tenant/data skew patterns.
- Aggregations spilling to disk.
- Workloads driving p99 tail latency.

After sanitizing and modeling selectivity, capture **deterministic synthetic fixtures** reproducing those patterns in tests.

### 39.5. Never Copy Raw Production Data into CI

Production logs and filters often contain PII. Construct synthetic fixtures matching production cardinality and skew without checking real customer records into Git or CI artifacts.

---

## 40. When a Query Plan Changes Yet Stays Fast

A MongoDB upgrade may change:

```text
FETCH -> IXSCAN
~~~

to an SBE execution plan while keeping:

```text
nReturned = 10
totalDocsExamined = 10
totalKeysExamined = 10
~~~

virtually identical.

### 40.1. Is This a Regression?

Not necessarily. If correctness and logical work budgets remain solid, do not fail builds purely because the explain JSON tree reshaped.

### 40.2. When Does a Plan Change Warrant Investigation?

- Sharp jump in `totalDocsExamined`.
- Sharp jump in `totalKeysExamined`.
- Unexpected blocking sort or disk spill.
- Frequent plan-cache replanning churn.
- Meaningful production latency increase.
- Incorrect returned data.
- Index missing or accidentally hidden.

### 40.3. Record Server Versions in Test Reports

On failure, log both the MongoDB Server version and Java driver version. Failures appearing only on MongoDB 9.x may simply require updating explain parsers for newer optimizer output.

---

## 41. When an Index Is Used Yet `keysExamined` Remains High

Suppose:

```text
Plan:
  IXSCAN { status: 1 }

Stats:
  keysExamined = 500000
  docsExamined = 500000
  nReturned = 10
~~~

Asserting only `IXSCAN present` passes even as the query scans half a million index entries.

### 41.1. Stronger Budget

```text
nReturned == 10
docsExamined <= 100
keysExamined <= 200
~~~

### 41.2. Better Candidate Index

Replace:

```javascript
{ status: 1 }
~~~

with an index matched to the query:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
~~~

backed by explain verification.

### 41.3. Impact on Write Workloads

Compound indexes consume RAM, disk, and write amplification. Never blindly add indexes just to silence a read test while ignoring write throughput and storage costs.

### 41.4. Measure Write Overhead in Benchmarks

Explain tests guard read access paths; separate benchmarks should verify insert and update throughput after index additions.

---

## 42. When Tests Fail Due to Intentional Dataset Changes

Suppose a product change multiplies `PAID` orders per tenant by 20x.

### 42.1. The Failing Test Still Adds Value

It flags that either scan budgets or index designs need re-evaluation.

### 42.2. Never Blindly Raise Budgets Without Justification

A pull request changing:

```text
maxDocsExamined: 30 -> 100000
~~~

just to turn CI green removes the regression guardrail altogether.

### 42.3. Process for Updating a Budget

1. Identify the data distribution or query-shape change.
2. Compare before/after explain outputs.
3. Inspect index candidates and options.
4. Measure updated result counts and selectivity.
5. Calculate a justified new work budget.
6. Run benchmarks if workload scale grew substantially.
7. Document the rationale in the PR or ADR.

### 42.4. Using Relative Budgets Appropriately

When a query returns variable `N` documents, consider:

```text
docsExamined <= max(absoluteFloor, ratioBudget * nReturned)
~~~

Be mindful of edge cases like `nReturned = 0`, aggregations, multikey arrays, and range queries by keeping an absolute bound alongside ratios.

---

## 43. Unindexed Baseline and Periodic Negative Controls

Periodically confirm your regression guardrail actually fires:

1. Seed fixtures.
2. Explain the query with the right index.
3. Force a natural scan or query an isolated unindexed DB copy.
4. Confirm `docsExamined` breaches the budget.
5. Drop/reset the isolated test database.

### 43.1. Keep Negative Controls Out of Flaky PR Gates

If fixtures are too tiny, even `COLLSCAN` fits within budget and the negative control proves nothing.

### 43.2. When Queries Return Few Matching Rows

Include plenty of non-matching documents so a natural scan must visit many irrelevant records.

### 43.3. `limit` Queries Can Short-Circuit Early

Especially without sorting or when matching documents happen to sit first on disk, `COLLSCAN` can find 10 matches almost immediately.

To build a reliable negative control, include a sort unsupported by indexes or arrange fixture insertion order so natural scans traverse significant data. Never assume `$natural` always scans 100% of a collection.

### 43.4. Never Break Standard PR Pipelines Intentionally

Keep negative controls as dedicated tests that assert `work > threshold` — passing when simulated degradation is caught rather than deliberately throwing uncaught exceptions and turning builds red.

---

## 44. Priority Tiers by Workload Criticality

| Query Group | Priority | Test Gate |
|---|---|---|
| Critical checkout / read-after-write | Very high | Correctness + index contract + explain budget + failover tests |
| User-facing listing / search | High | Correctness + scan budget + pagination/sort tests |
| Admin reports | Medium | Pipeline explain + periodic workload benchmark |
| One-time migrations | Per runbook | Dry run, batching, resource budgets, checkpoints |
| Background analytics | Per batch SLA | Explain/benchmark; do not forbid every `COLLSCAN` |
| Rare maintenance queries | Lower | Correctness + resource safety bounds |
| Specialized vector/text search | Per ranking quality | Index/search metrics + relevance + benchmarks |

### 44.1. Which Queries to Protect First

Prioritize queries with:

- High request traffic.
- Heavy scan potential.
- Strict latency sensitivity.
- Skewed tenant distributions.
- Frequently evolving query shapes.
- Rapidly growing collections.
- Reliance on multi-column compound indexes.
- Complex joins, grouping, or sorting pipelines.

### 44.2. You Do Not Need Thousands of Brittle Plan Tests

A focused suite covering high-impact query shapes outperforms hundreds of fragile assertions tied to exact stage nesting.

---

## 45. Runbook When a CI Query-Plan Test Fails

### Step 1 — Classify the Failure

- Correctness mismatch?
- Missing index?
- Excessive `totalDocsExamined`?
- Excessive `totalKeysExamined`?
- Missing explain field?
- Driver/server mismatch?
- Unexpected plan stage?
- Corrupted test fixture?

### Step 2 — Inspect Test Fixtures

- Total document count.
- Predicate cardinality.
- Sort tie-breakers.
- Index definitions and options.
- Test database isolation.

### Step 3 — Inspect Query Shape

- Filter predicates.
- Sort specification.
- Projection.
- Limit / skip.
- Collation.
- Hints.
- Read preference.
- Aggregation stages.

### Step 4 — Compare Before/After Explain Output

Record sanitized summaries:

```text
Query: recent-paid-orders
Server version: pinned test version
Returned: 10

Before:
  docsExamined: 10
  keysExamined: 10
  index: idx_tenant_status_created

After:
  docsExamined: 8000
  keysExamined: 0
  winning access: COLLSCAN
~~~

### Step 5 — Check Recent Code and Migrations

- Did someone modify or drop an index?
- Was a migration skipped?
- Did a query predicate change?
- Was an index hidden or made partial?
- Did a field's BSON type change?
- Did collation change or mismatch?
- Did fixture data distribution shift?

### Step 6 — Pick the Right Fix

- Restore or refine the index.
- Fix the query predicate.
- Add selective filters.
- Align sort fields and directions.
- Optimize projections.
- Replace deep `skip` with keyset pagination.
- Adjust schema design.
- Update budgets only with documented evidence.

### Step 7 — Check for Side-Effect Regressions

An index that speeds up reads can slow writes down. Check benchmarks, index size, and write amplification.

### Step 8 — Close the Incident

Document:

- Root cause.
- Query shape.
- Before/after scan metrics.
- Index migration/version.
- Benchmark findings (if run).
- Remaining risks.

Never declare "flakiness resolved" simply by bumping a timeout from 50 ms to 5,000 ms.

---

## 46. Common Pitfalls When Writing Query-Plan Tests

| Mistake | Why It Fails | Fix |
|---|---|---|
| `assert elapsedMs < 10` | Host and runtime noise | Enforce scan budgets |
| `assert executionTimeMillis == 1` | Explain timings fluctuate | Log diagnostically only |
| 3-document dataset | `COLLSCAN` looks optimal | Seed representative scale |
| Random seeding per run | Selectivity drifts between runs | Use deterministic fixtures |
| Asserting only `IXSCAN` | Can still scan millions of keys | Enforce keys/docs budgets |
| Checking only low `keysExamined` | `COLLSCAN` reports `keys = 0` | Pair with `docsExamined` budget |
| Checking only low `docsExamined` | Covered scans can walk millions of keys | Pair with `keysExamined` budget |
| Full `winningPlan` JSON equality | Shifts across engines and versions | Use resilient semantic checks |
| Scanning `rejectedPlans` for index name | Proves candidate consideration, not selection | Walk only `winningPlan` |
| Hinting indexes in main tests | Hides planner regressions | Keep main tests hint-free |
| Dropping indexes on shared staging | Breaks other tests and plan caches | Use isolated DB or `$natural` hint |
| Assuming explain uses plan cache | Explain bypasses cached plans | Inspect production telemetry separately |
| Hardcoding `queryHash` strings | Identifiers evolve across releases | Avoid fixed shape-hash checks |
| Requiring `nReturned == docsExamined` on covered queries | Covered queries examine 0 docs | Use upper-bound budgets |
| Naive `docsExamined/nReturned` on `$group` | Aggregates return summary rows | Write operator-specific tests |
| Sorting without a unique tie-breaker | Unstable order across pages | Include `_id` tie-breaker |
| Testing altered query shapes vs. prod | Misleading plans and correctness | Keep identical shapes and options |
| Skipping index catalog verification | Harder to diagnose missing-index failures | Add migration/catalog contract tests |
| Ignoring partial filters or collation | Planner safely skips mismatched indexes | Verify index options explicitly |
| Benchmarking on shared CI runners | CPU/cache contention corrupts results | Use dedicated benchmark nodes |
| Computing p95 from 10 requests | Tiny sample size | Run sustained representative loads |
| Skipping warmup | JIT/pool/cold-cache bias | Use structured warmup |
| Treating JMH as a DB load test | Misses network, storage, and locking | Run system-level benchmarks |
| Failing every `COLLSCAN` globally | Some analytics scans are intentional | Align gates with workload contracts |
| Picking scan budgets arbitrarily | False passes or false breaks | Derive budgets from measured fixtures |
| Pointing tests at production URI | Risk of dropping live data | Dedicated isolated test instances |
| Sharing mutable test DB across tests | Concurrent DDL flakes tests | Unique DB per run/class |
| Tight `maxTimeMS` as perf assertion | Timeout noise | Use generous safety timeouts |
| Treating CI plan gates as latency SLOs | Ignores network, I/O, and throughput | Pair with benchmarks and APM |
| Copying `find` thresholds to vector search | Incompatible telemetry models | Use search-specific evaluations |
| Pasting production queries into CI | PII leakage risk | Synthesize sanitized fixtures |

---

## 47. Practice Exercise A: Replacing Millisecond Checks with Work Budgets

Given the legacy test:

~~~java
long start = System.nanoTime();
List<Document> orders = collection.find(filter)
        .limit(20)
        .into(new ArrayList<>());
long ms = (System.nanoTime() - start) / 1_000_000;
assertTrue(ms < 30);
~~~

Tasks:

1. Add result correctness assertions.
2. Fetch `explain("executionStats")`.
3. Assert fixture-calibrated docs and keys scan budgets.
4. Log `executionTimeMillis` strictly for diagnostics.
5. Explain why the rewritten test is far less flaky.

---

## 48. Exercise B: Comparing Two Plans

Given:

```text
Plan A: IXSCAN
  keysExamined = 20
  docsExamined = 20
  nReturned = 20

Plan B: IXSCAN
  keysExamined = 700000
  docsExamined = 350000
  nReturned = 20
~~~

Tasks:

1. Explain why both use an index yet differ massively in efficiency.
2. Choose scan budgets that catch Plan B.
3. Propose an improved compound index.
4. Describe the write overhead of adding that index.

---

## 49. Exercise C: Deterministic Fixtures

Seed 12,000 orders with:

- 6 tenants.
- 2,000 orders/tenant.
- 70% `PAID`.
- Timestamps incrementing by one minute.
- Deterministic `_id`s.

Tasks:

1. Seed without uncontrolled randomness.
2. Verify counts.
3. Create the compound index.
4. Query the top 10.
5. Inspect `nReturned`, `docsExamined`, and `keysExamined`.
6. Define a budget with a sensible safety margin.

---

## 50. Exercise D: Index Missing the Sort Field

Original index:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
~~~

Changed to:

```javascript
{ tenantId: 1, status: 1 }
~~~

Tasks:

1. Predict the effect when sorting by `createdAt` descending.
2. Compare explain plans.
3. Inspect for a blocking sort.
4. Choose assertions resilient across engine/version changes.
5. Explain why asserting the entire plan tree is unnecessary.

---

## 51. Exercise E: Covered Queries

Given index:

```javascript
{ tenantId: 1, status: 1, amount: 1 }
~~~

And projection:

```javascript
{ _id: 0, tenantId: 1, status: 1, amount: 1 }
~~~

Tasks:

1. Explain the requirements for coverage.
2. Why can `docsExamined = 0` be accurate?
3. What changes if `_id: 1` is added to the projection?
4. Check multikey and collation restrictions.

---

## 52. Exercise F: Plan Cache

An explain test reports `IXSCAN`, yet production slow logs report `COLLSCAN`.

List at least seven causes, covering:

- Plan cache.
- Dataset distribution.
- Index / migration state.
- Query shape / parameters.
- Server version / engine.
- Collation / hints.
- Router / shard differences.

Explain why calling `explain()` does not inspect the live plan cache.

---

## 53. Exercise G: Aggregation Regression

Pipeline:

```javascript
[
  { $match: { tenantId: "tenant-03" } },
  { $group: { _id: "$status", count: { $sum: 1 } } }
]
~~~

Returns 2 groups while scanning 1,000 orders.

1. Why is a high `docsExamined / nReturned` ratio normal here?
2. Could earlier filtering reduce work further?
3. Which index supports the `$match`?
4. Which metrics help evaluate grouping overhead?
5. Why does a 30-doc threshold from a top-10 query not apply here?

---

## 54. Exercise H: Sharded Plans

A query fans out to 4 shards, each reporting separate `executionStats`.

1. How do you avoid double-counting examined stats?
2. What does the number of targeted shards reveal?
3. Why shouldn't shard durations be summed to estimate HTTP latency?
4. When must you test via `mongos` rather than standalone `mongod`?
5. Design a shard-targeting budget model.

---

## 55. Exercise I: Pagination

An API uses:

```javascript
.skip(100000).limit(20)
~~~

Tasks:

1. Estimate `keysExamined` even with an index.
2. Propose a keyset cursor query.
3. Add a sort tie-breaker.
4. Size a sufficiently deep test fixture.
5. Compare correctness and scan budgets.
6. Benchmark deep-page latency separately.

---

## 56. Exercise J: CI vs. Benchmark

A team wants every pull request gated by:

```text
MongoDB query p95 <= 30 ms
~~~

computed from 20 requests on a shared CI runner.

Redesign this into:

- A fast, deterministic explain gate.
- Nightly / pre-release dedicated benchmarks.
- Proper sampling and confidence intervals.
- Production SLO monitoring.
- A clear regression response policy.

---

## 57. Exercise K: MongoDB Upgrade

After a server upgrade, explain switches from `IXSCAN/FETCH` to an SBE path while counters remain equivalent.

1. Should an exact-stage assertion break the build?
2. How do you verify semantic equivalence?
3. When should you update plan parsers?
4. Do you still need workload benchmarks?
5. How should MongoDB version/FCV be captured in diagnostics?

---

## 58. Exercise L: Negative Control

Design a test proving `docsExamined <= 30` catches a collection scan.

1. Seed dataset.
2. Run hint-free explain.
3. Force `$natural` hint.
4. Compare scan metrics.
5. Never drop indexes on production.
6. Never use index hints to "pretty up" main planner tests.

---

## 59. Standard Checklist for Query-Efficiency Regression Tests

### 59.1. Fixtures

- [ ] Dedicated MongoDB test instance/namespace.
- [ ] Unique database name or explicit isolation.
- [ ] Deterministic seed data.
- [ ] Verified counts and distributions.
- [ ] Large enough dataset to separate index scans from collection scans.
- [ ] Zero raw production PII.
- [ ] Safe teardown/cleanup.
- [ ] No shared mutable index or plan-cache state across tests.

### 59.2. Query Contract

- [ ] Filter matches production query shape.
- [ ] Complete sort specification with tie-breakers where needed.
- [ ] Realistic projection, limit, skip, and collation.
- [ ] Thorough correctness assertions.
- [ ] Expected result counts checked.
- [ ] Critical queries assigned names and owners.
- [ ] Skewed data scenarios covered.

### 59.3. Index Contract

- [ ] Indexes created by real migrations.
- [ ] Exact key order and sort directions checked.
- [ ] Partial, sparse, unique, and collation options verified.
- [ ] Indexes not accidentally hidden.
- [ ] Hint-free explain tests present.
- [ ] Appropriate negative controls verified.
- [ ] Never altering indexes on shared production for tests.

### 59.4. Assertions

- [ ] Explicit `executionStats` verbosity.
- [ ] Checks `nReturned`.
- [ ] Checks `totalDocsExamined`.
- [ ] Checks `totalKeysExamined`.
- [ ] Data-grounded scan budgets.
- [ ] Safe handling of `nReturned = 0`.
- [ ] No brittle exact millisecond assertions.
- [ ] No full explain JSON equality assertions.
- [ ] No assumptions that query hashes stay immutable across releases.
- [ ] Parser accounts for classic, SBE, and sharded formats.
- [ ] Rich diagnostic output logged on failure.

### 59.5. Benchmarking and Monitoring

- [ ] Separate benchmarks for latency and throughput.
- [ ] Warmup and stable dedicated hosts.
- [ ] Tracks p50/p95/p99 latency and error rates.
- [ ] Tracks concurrency and ops/s.
- [ ] Tracks CPU, memory, disk, and network.
- [ ] Compares repeated runs and statistical variance.
- [ ] Separates application time from MongoDB command time.
- [ ] Does not substitute JMH microbenchmarks for database load tests.
- [ ] Monitors production SLOs independently from CI explain gates.

---

## 60. Official References

- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual — Interpret Explain Plan Results](https://www.mongodb.com/docs/manual/tutorial/analyze-query-plan/)
- [MongoDB Manual — Explain Command](https://www.mongodb.com/docs/manual/reference/command/explain/)
- [MongoDB Manual — cursor.explain()](https://www.mongodb.com/docs/manual/reference/method/cursor.explain/)
- [MongoDB Manual — db.collection.explain()](https://www.mongodb.com/docs/manual/reference/method/db.collection.explain/)
- [MongoDB Manual — Query Plans and Plan Cache](https://www.mongodb.com/docs/manual/core/query-plans/)
- [MongoDB Manual — Slot-Based Query Execution Engine](https://www.mongodb.com/docs/manual/reference/sbe/)
- [MongoDB Manual — Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB Manual — ESR Equality, Sort, Range Guideline](https://www.mongodb.com/docs/manual/tutorial/equality-sort-range-guideline/)
- [MongoDB Manual — Covered Queries](https://www.mongodb.com/docs/manual/core/query-optimization/#covered-query)
- [MongoDB Manual — Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/)
- [MongoDB Manual — Hidden Indexes](https://www.mongodb.com/docs/manual/core/index-hidden/)
- [MongoDB Manual — $planCacheStats](https://www.mongodb.com/docs/manual/reference/operator/aggregation/planCacheStats/)
- [MongoDB Java Sync Driver — Cursors and Explain](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/cursor/)
- [MongoDB Java Sync Driver — Indexes](https://www.mongodb.com/docs/drivers/java/sync/current/indexes/)
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/)
- [Testcontainers MongoDB Module](https://java.testcontainers.org/modules/databases/mongodb/)

> **Note:** MongoDB does not guarantee a fixed `explain` output format, even under the Stable API. When writing parsers or stage-specific checks, verify against your exact MongoDB Server version, execution engine, topology, and Java driver. All examples target isolated test databases rather than production clusters.

---

## 61. Summary

1. **Never use single-query milliseconds as a primary pass/fail gate in CI.** Timings fluctuate with JVM warmup, network jitter, cache state, noisy neighbors, and planner overhead.
2. **Query efficiency testing** should focus on correctness, index contracts, `nReturned`, `totalDocsExamined`, `totalKeysExamined`, and workload-appropriate scan budgets.
3. **`explain("executionStats")`** is invaluable for measuring logical work, yet it **bypasses the plan cache** and its timings do not mirror steady-state production latency.
4. **`IXSCAN` does not prove a query is efficient; `COLLSCAN` does not prove a query is broken.** Inspect actual scanned work and business intent.
5. **`winningPlan` trees vary** across classic, SBE, EXPRESS, and sharded execution across versions. Avoid full JSON equality or rigid stage paths unless pinned to one tested version.
6. **Fixtures must be deterministic and large enough** with representative selectivity so missing-index regressions clearly breach scan budgets.
7. **Separate hint-free main tests from hinted diagnostics.** Hints compare candidate access paths cleanly, whereas using them in main tests hides planner regressions.
8. **Index catalog tests and query-plan tests reinforce each other**: one ensures migrations create the promised indexes, and the other ensures queries avoid excessive scans.
9. **Aggregations, multikey arrays, deep pagination, and sharding** obey different scan semantics; never copy a top-10 equality budget blindly to every operation.
10. **True benchmarks require multiple samples and percentiles** in controlled environments while observing throughput, concurrency, CPU, I/O, and error rates.

**Bottom line:** CI gates should block changes causing **abnormal growth in logical work**, while benchmarks and production observability answer **how fast the system actually runs**. Separating those two concerns eliminates flaky timing tests while still catching meaningful query-plan regressions.
