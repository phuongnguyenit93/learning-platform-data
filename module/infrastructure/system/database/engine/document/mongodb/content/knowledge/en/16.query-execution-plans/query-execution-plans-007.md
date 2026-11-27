# Comparing Before-and-After Execution Plans on a Representative Dataset

When optimizing MongoDB, a change such as adding a compound index, reordering index fields, rewriting a filter, or adding a projection can speed up a query dramatically. Yet seeing `IXSCAN` replace `COLLSCAN` in `explain()` is **not enough** to declare optimization a success. You must answer more practical questions:

- Does the query return **the exact same data and order** as before?
- How many **index keys** and how many **documents** did MongoDB have to examine?
- Did it sort a large set, or follow index order?
- Does the improvement appear on data **with production-like distribution**, or only on a few dozen test records?
- Is the speed improvement consistent across repeated runs, under warm/cold cache, and under concurrent requests?
- How much write overhead, RAM, and disk space does the new index add?
- Does the query planner actually pick the new plan in the application, or did the good plan only appear when using `hint()`?

This lesson presents a **before-and-after comparison** workflow grounded in a representative dataset and a clearly defined query workload. The focus is on **gathering evidence**, interpreting `explain("executionStats")`, avoiding misleading experiments, and making verifiable index/query decisions.

> Guiding principle: **Hold data, query, and environment constant; change one factor deliberately; measure multiple metrics and scenarios; draw conclusions strictly within what was measured.**

## 1. Why Must You Use a Representative Dataset?

A query on a 30-document collection can run fast even with `COLLSCAN`. When that collection grows to 30 million documents, scanning the whole collection for an endpoint returning 20 orders becomes a major bottleneck.

Conversely, an index that looks great on evenly distributed data may help little if production has one giant tenant, a status accounting for 95% of records, or documents with long arrays turning the index multikey.

### 1.1. Properties That Must Be Represented

A useful dataset does not just match **document count**—it matches **shape and distribution** close to the real workload:

| Property | Example to Simulate | Impact on Query Plan |
|---|---|---|
| Document count | 100k, 10M, or realistic scale | `COLLSCAN` cost, page depth |
| BSON size | Docs of a few hundred bytes, some groups of tens of KB | I/O, cache, FETCH |
| Tenant distribution | Tenant A holds 80%, others hold less | Per-tenant selectivity |
| Status distribution | 70% `PAID`, 25% `PENDING`, 5% `CANCELLED` | Selectivity and index usefulness |
| Time distribution | Concentrated in recent months, peak seasons | Range scans, sorting, result limits |
| Duplicate keys | Many records sharing the same `createdAt` | Tie-breakers and sorting |
| `null`/missing values | Some records lack `category` | Index/filter eligibility, semantics |
| Array/embedded data | `items` with 1–20 elements | Multikey indexes, fetching |
| Updates/deletes | Documents frequently change status | Index maintenance, plans on fresh data |
| Hot keys | One user/tenant hit at very high frequency | Cache, contention, p95/p99 |
| Existing indexes | `_id`, compound, partial, multikey | Planner choices |

An **artificially uniform** dataset can lead to the wrong index choice. For instance, if 90% of production orders have `status: "PAID"`, an index solely on `status` has low selectivity. If test data splits three statuses equally, you will overestimate that index.

### 1.2. Test Data Must Preserve Privacy

When reproducing production distributions, prefer:

1. Synthetic data preserving realistic cardinality, histograms, skew, and sizes.
2. Anonymized data processed through an approved sanitization pipeline.
3. Stratified samples across **distribution tiers**, rather than just taking the first 10,000 records.

Never copy PII, tokens, passwords, or sensitive payloads into an unprotected benchmark environment. Replacing real names with fake names is not sufficient anonymization if other attributes enable re-identification.

### 1.3. Simple Random Sampling Can Miss the Long Tail

If 80% of traffic hits one large tenant group while only 20% of tenants share that distribution, sampling uniformly by tenant count makes the synthetic workload overly uniform. Verify all of these together:

- **Document count** distribution;
- **Request count** distribution by group;
- Mix of queries with filter, sort, projection, limit;
- Ratio of large/small tenants, hot/cold keys;
- Edge cases such as multi-month date ranges, rare statuses, users with zero events.

A **representative dataset** and a **representative workload** are distinct dimensions: production-like data benchmarked against a single rare query is still insufficient.

## 2. Start with a Testable Hypothesis

Suppose an API fetches the 50 newest paid orders for a tenant within a month:

```javascript
db.orders.find(
  {
    tenantId: "TENANT-A",
    status: "PAID",
    createdAt: {
      $gte: ISODate("2026-03-01T00:00:00Z"),
      $lt: ISODate("2026-04-01T00:00:00Z")
    }
  },
  {
    _id: 1,
    createdAt: 1,
    total: 1,
    status: 1
  }
)
.sort({ createdAt: -1, _id: -1 })
.limit(50);
```

Hypothesis:

> Index `{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }` will let MongoDB narrow data by tenant and status, traverse the `createdAt` range in output order, cut documents examined, and avoid a large sort compared to a collection scan.

A strong hypothesis specifies:

- **Workload:** exact query and call frequency;
- **Change:** which index is added or how the query is rewritten;
- **Expected metrics:** keys/docs examined, latency, sort, memory;
- **Risks:** index storage cost and write amplification;
- **Decision criteria:** improvement across key query variants without significantly degrading other workloads.

**Do not measure without knowing what you are testing.** "Add an index and see if it gets faster" is too vague for operational decisions.

## 3. Experiment Setup: Creating a Dedicated Collection

The following examples use the **`planLabOrders`** collection purely for testing. Never run `drop()` on a production collection or any collection holding data you need to keep.

Goals of the script:

- 120,000 documents so `COLLSCAN` and `IXSCAN` show a much clearer difference than a collection of a few dozen records;
- Tenant A makes up ~80%, B ~15%, C ~5%;
- `PAID` status is common, `PENDING` moderate, `CANCELLED` rare;
- Creation dates span several months with many tied timestamps;
- Some records include larger payloads;
- A pseudo-random generator with a **fixed seed** so re-runs reproduce a similar distribution.

### 3.1. Generating Synthetic Data with `mongosh`

```javascript
// RUN ONLY ON A TEST DATABASE.
// drop() will delete the entire planLabOrders collection if it exists.
db.planLabOrders.drop();

const totalDocs = 120000;
const batchSize = 1000;
const baseTime = Date.parse("2026-01-01T00:00:00Z");
const dayMillis = 24 * 60 * 60 * 1000;

let seed = 20261114;

// Pseudo-random number generator with a fixed seed.
// Math.imul and >>> 0 keep values in the uint32 range.
function rnd() {
  seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
  return seed / 4294967296;
}

function chooseTenant(x) {
  return x < 0.80
    ? "TENANT-A"
    : (x < 0.95 ? "TENANT-B" : "TENANT-C");
}

function chooseStatus(x) {
  return x < 0.70
    ? "PAID"
    : (x < 0.95 ? "PENDING" : "CANCELLED");
}

let batch = [];

for (let i = 0; i < totalDocs; i++) {
  // ~180 days, simulated hour/minute/second derived from i.
  const daysFromStart = Math.floor(rnd() * 180);
  const secondsInDay = i % 86400;
  const createdAt = new Date(
    baseTime + daysFromStart * dayMillis + secondsInDay * 1000
  );

  const tenantId = chooseTenant(rnd());
  const status = chooseStatus(rnd());
  const total = Math.floor(rnd() * 4000000) + 10000;

  batch.push({
    tenantId: tenantId,
    status: status,
    createdAt: createdAt,
    total: total,
    customerId: "C-" + (i % 18000),
    category: i % 7 === 0 ? "PRIORITY" : "STANDARD",
    itemCount: 1 + (i % 8),
    note: i % 20 === 0 ? "x".repeat(2000) : "ok",
    source: {
      channel: i % 4 === 0 ? "MOBILE" : "WEB",
      importBatch: Math.floor(i / batchSize)
    }
  });

  if (batch.length === batchSize) {
    db.planLabOrders.insertMany(batch, { ordered: false });
    batch = [];
  }
}

if (batch.length > 0) {
  db.planLabOrders.insertMany(batch, { ordered: false });
}

print("Inserted: " + db.planLabOrders.countDocuments({}));
```

The script inserts documents with `_id` values generated by MongoDB/the driver. Keep `_id` values stable within a comparison session. Re-running the script drops and recreates the collection; that does not compare against **the exact same BSON records** from the prior run, so key comparisons should run **within a single seed**.

### 3.2. Why Is a Fixed Seed Necessary Yet Still Not Enough?

A fixed seed helps:

- Re-runs keep nearly identical tenant/status ratios.
- Scripts and queries are easier to compare.
- One source of unwanted variance is reduced.

However, it does not hold every factor constant: `_id` values, cache state, record placement, index builds, system load, and MongoDB versions may differ. For strict A/B testing, use the same collection snapshot or materialized dataset and interleave plan measurements on unchanged data.

### 3.3. Inspecting Test Data Distribution

Never assume synthetic data matches target ratios just because the script defined probabilities. Inspect directly:

```javascript
db.planLabOrders.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        status: "$status"
      },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
```

Inspect the date range:

```javascript
db.planLabOrders.aggregate([
  {
    $group: {
      _id: null,
      minCreatedAt: { $min: "$createdAt" },
      maxCreatedAt: { $max: "$createdAt" },
      total: { $sum: 1 }
    }
  }
]);
```

Inspect collection and index sizes (values vary by engine/version):

```javascript
db.planLabOrders.stats();
db.planLabOrders.getIndexes();
```

These commands inspect the dataset; **they do not replace query benchmarking**. Subsequent sections assume the dataset is populated and unmodified by other processes during the before/after window.

## 4. Freezing the Query Shape Before Measuring

A valid comparison requires both sides to **return the exact same logical results**.

Define the query:

```javascript
const filter = {
  tenantId: "TENANT-A",
  status: "PAID",
  createdAt: {
    $gte: ISODate("2026-03-01T00:00:00Z"),
    $lt: ISODate("2026-04-01T00:00:00Z")
  }
};

const projection = {
  _id: 1,
  createdAt: 1,
  status: 1,
  total: 1
};

const sort = { createdAt: -1, _id: -1 };
const limit = 50;
```

Across all primary plan comparisons:

- Keep filter fields, operators, and values identical.
- Keep projection identical: adding or dropping one field can toggle whether a query is covered or needs `FETCH`.
- Keep sort fields and directions identical.
- Keep `limit` and `skip` (if any) identical.
- Record collation, read concern/read preference, session, and driver settings.
- Run against **the exact same data state** if isolating the effect of an index.

If you change both the query and the index simultaneously, you can prove "the new overall solution is faster," but you cannot isolate how much improvement came from the index versus the query rewrite.

### 4.1. Verify Correctness Before Optimizing

A faster query that drops documents is a business bug. Verify:

- Results belong to the right tenant and status.
- `createdAt` lies within the half-open `[start, end)` interval as specified.
- Ordering is descending by `createdAt`, then `_id`.
- At most 50 documents are returned.
- Projection omits no fields the client actually requires.

For instance, if the before query filtered `status: "PAID"` and the after query removed that predicate to fit an index, results are not equivalent and latency comparisons are invalid.

## 5. Measuring the Plan Before Adding an Index

On the fresh test collection containing only the default `_id` index, run:

```javascript
const before = db.planLabOrders.find(
  filter,
  projection
)
.sort(sort)
.limit(limit)
.explain("executionStats");

printjson(before);
```

For a query filtering tenant, status, and a `createdAt` range without a suitable index, the plan may look like:

```text
COLLSCAN
   |
  FILTER (tenantId, status, createdAt)
   |
  SORT (createdAt DESC, _id DESC)
   |
  LIMIT 50
```

This is merely a visual diagram; MongoDB may display stages in different orders, structures, or names depending on **classic engine/SBE**, version, and `SORT + LIMIT` optimizations.

The baseline expectation is that MongoDB must inspect many documents to find matches and sort eligible candidates. Never write down imagined numbers like "120,000 docs examined" before inspecting actual output.

### 5.1. Values to Record from Explain

```javascript
const s = before.executionStats;

printjson({
  nReturned: s.nReturned,
  totalKeysExamined: s.totalKeysExamined,
  totalDocsExamined: s.totalDocsExamined,
  executionTimeMillis: s.executionTimeMillis
});
```

An **illustrative hypothetical baseline**, not output from running the script:

| Metric | Before Index (Illustrative Example) |
|---|---:|
| `nReturned` | 50 |
| `totalKeysExamined` | 0 |
| `totalDocsExamined` | 120,000 |
| `executionTimeMillis` | 85 ms |
| Plan | `COLLSCAN` + sort |

Use this table strictly to visualize how to read metrics. Actual numbers vary with hardware, MongoDB version, cache, load, and data.

### 5.2. Reading `nReturned` Properly

`nReturned` is the number of documents emitted by the execution plan. When a query has `limit(50)` and thousands of records match, `nReturned` is just 50; it **does not mean only 50 documents match the filter overall**.

To measure total filter selectivity, run `countDocuments(filter)` separately. However, that is a separate query that should be evaluated independently and may consume resources. Do not fold counting into the main pagination query's timing unless the application runs a count on the same request path.

### 5.3. Why Is `executionTimeMillis` Insufficient?

`executionTimeMillis` in explain is a useful reference, yet is affected by:

- Test timing, cache state, and host resources;
- Planner overhead racing multiple candidates;
- How records are consumed in explain mode;
- Server load and storage state;
- Query engine version and how the tool reports time.

It is **not a complete metric** replacing client-observed p95/p99 latency. Combine plan statistics with real execution benchmarks that consume full results.

## 6. Adding the Compound Index After Capturing the Baseline

Once before-metrics are recorded:

```javascript
db.planLabOrders.createIndex(
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
```

This index includes:

1. `tenantId` and `status`: two equality predicates, typically placed first in the prefix.
2. `createdAt` descending: supports both the date range and sort order.
3. `_id` descending: tie-breaker for documents sharing identical timestamps, keeping sort deterministic.

This index targets a **specific query shape**; it does not mean every query on the collection is optimized.

Re-run the exact same query:

```javascript
const after = db.planLabOrders.find(
  filter,
  projection
)
.sort(sort)
.limit(limit)
.explain("executionStats");

printjson(after);
```

If the planner leverages the index as expected, you may see a path like:

```text
IXSCAN idx_tenant_status_created_id
   |
  FETCH (because projection needs total outside index)
   |
  LIMIT / PROJECTION
```

The index can supply `createdAt DESC, _id DESC` order after the equality prefix, avoiding a large **blocking SORT** when eligible. Still, never assert every MongoDB version prints this exact stage chain or that the planner is guaranteed to pick the new index: check the real output.

### 6.1. After Indexing, `totalDocsExamined` Is Not Always Zero

The example projection includes `total: 1`, whereas the index covers only `tenantId`, `status`, `createdAt`, and `_id`. Because MongoDB must read `total` from documents, the query can include `FETCH` and `totalDocsExamined > 0`.

With `limit(50)` and a well-aligned index, MongoDB may need to fetch roughly as many documents as are returned rather than scanning most of the collection. **The goal is eliminating wasted work**, not forcing `totalDocsExamined = 0` on every query.

### 6.2. Covered Queries Are a Separate Experiment

If only indexed fields are needed:

```javascript
db.planLabOrders.find(
  filter,
  {
    tenantId: 1,
    status: 1,
    createdAt: 1,
    _id: 1
  }
)
.sort(sort)
.limit(limit)
.explain("executionStats");
```

Under eligible conditions, the query can be covered by the index with `totalDocsExamined: 0`. However, **the projection changed** relative to the query requesting `total`, so never cite this number as proof that adding the index alone made the original query avoid document reads.

If the API genuinely does not need `total`, trimming the projection is a valid optimization—just report it explicitly as a **second change**.

## 7. Comparing Before and After Metrics Properly

Once you have both outputs, build a comparison table:

| Metric | Before | After | Interpretation |
|---|---:|---:|---|
| `nReturned` | Measured | Measured | Verify expected identical count |
| `totalKeysExamined` | Measured | Measured | Index traversal cost |
| `totalDocsExamined` | Measured | Measured | Document inspection/fetch cost |
| `executionTimeMillis` | Measured | Measured | Explain timing signal |
| Has `COLLSCAN`? | Yes/No | Yes/No | Did it scan the whole collection? |
| Has `IXSCAN`? | Yes/No | Yes/No | Which index was used? |
| Has blocking `SORT`? | Yes/No | Yes/No | Did it sort an intermediate set? |
| Has `FETCH`? | Yes/No | Yes/No | Did it need fields outside the index? |
| Index size | Measured | Measured | Added storage cost |
| Real client latency | Measured | Measured | Application experience |

### 7.1. Examined-to-Returned Ratios

When `nReturned > 0`, reference ratios are:

```text
docsPerResult = totalDocsExamined / nReturned
keysPerResult = totalKeysExamined / nReturned
```

Hypothetical example:

```text
Before:
  nReturned = 50
  totalDocsExamined = 120000
  docsPerResult = 2400

After:
  nReturned = 50
  totalDocsExamined = 50
  totalKeysExamined = 50
  docsPerResult = 1
  keysPerResult = 1
```

This illustrates **wasted read work dropping sharply** in the example. Yet a query returning 1 rare record might still legitimately examine many keys; evaluate ratios within the same query shape and selectivity instead of imposing a blanket rule like "every query must be under 2."

If `nReturned = 0`, do not divide by zero; inspect absolute keys/docs examined and understand why zero results matched.

### 7.2. Percentage Time Improvement

You can report:

```text
improvementPct = (beforeMs - afterMs) / beforeMs * 100%
speedup = beforeMs / afterMs
```

If before is 100 ms and after is 25 ms:

```text
Latency reduction = 75%
Speedup = 4x
```

From a single run, however, that is only a calculation on one observation. For operational conclusions, run multiple iterations and examine latency distribution and variance.

### 7.3. Never Treat `keysExamined = 0` as Always Good

A `COLLSCAN` can report `totalKeysExamined = 0` alongside a massive `totalDocsExamined`. Conversely, an indexed query might scan a few thousand keys and fetch only 50 documents—often a major improvement.

Read both metrics **together**, never chasing the minimum of a single metric in isolation.

## 8. Finding Key Stages in Explain

`explain()` output can have a complex structure. Common sections:

- `queryPlanner`: planner info, `winningPlan`, and `rejectedPlans` when present;
- `executionStats`: plan execution metrics under the requested verbosity;
- `executionStats.executionStages`: stage tree formatted by engine;
- `serverInfo`, index filters, query shape, or other metadata depending on version.

### 8.1. `COLLSCAN`

`COLLSCAN` means scanning the collection. It is not always bad:

- Query returns most of the documents;
- Collection is very small;
- No selective filter exists;
- Index traversal plus fetching nearly every document costs more than a sequential scan.

Thus, the goal is not "eliminate every `COLLSCAN`," but **cut total cost for queries with critical SLAs**.

### 8.2. `IXSCAN`

`IXSCAN` means traversing an index. Inspect **`indexName`**, bounds conditions, and keys examined.

Having an index scan does not guarantee efficiency. A poorly ordered index can scan hundreds of thousands of keys and still fetch many documents. For example, `{ status: 1 }` is typically suboptimal for "TENANT-A's `PAID` orders within a month, sorted by `createdAt`" if `PAID` is 70% of the collection.

### 8.3. `FETCH`

`FETCH` represents retrieving documents (or checking residual predicates) beyond what is in the index, depending on engine. If an index holds only `tenantId` and `status` while projection requests `total`, `createdAt`, and `customerId`, MongoDB must fetch documents.

Some `FETCH` work is **expected and necessary**. Fetching 50 documents instead of tens of thousands can still perform wonderfully without being covered.

### 8.4. `SORT`

A `SORT` stage indicates data had to be sorted rather than read directly in index order. With `limit(50)`, the engine can use a **top-k sort** to save memory; stage details depend on version.

Do not stop at the `SORT` name; inspect candidate volume, memory/spill stats if reported, and latency. Sorting 20 records is nothing like sorting 2 million records.

### 8.5. Different Engines and Versions

In modern MongoDB versions, explain can show stage names/formats such as `PROJECTION_COVERED`, `PROJECTION_SIMPLE`, `LIMIT`, `SORT_KEY_GENERATOR`, `EQ_LOOKUP`, `EXPRESS_IXSCAN`, or a `slotBasedPlan` section.

What matters is **semantics**: does it scan the collection, look up an index, fetch documents, perform a blocking sort, and how many keys/documents does it examine? Never build comparison tools hardcoded to a single JSON path without accounting for server versions.

## 9. Fair Comparison via `hint` on the Same Data State

Comparing before and after at two different times can introduce noise: index building warms caches, background load shifts, or writes land in between.

A complementary test is **after creating the index**, using `hint()` to request both access paths on **the exact same data**:

```javascript
// Force collection scan in the test environment.
const scanPlan = db.planLabOrders.find(
  filter,
  projection
)
.sort(sort)
.limit(limit)
.hint({ $natural: 1 })
.explain("executionStats");

// Force candidate index.
const indexPlan = db.planLabOrders.find(
  filter,
  projection
)
.sort(sort)
.limit(limit)
.hint("idx_tenant_status_created_id")
.explain("executionStats");

printjson({
  scan: {
    keys: scanPlan.executionStats.totalKeysExamined,
    docs: scanPlan.executionStats.totalDocsExamined,
    ms: scanPlan.executionStats.executionTimeMillis
  },
  index: {
    keys: indexPlan.executionStats.totalKeysExamined,
    docs: indexPlan.executionStats.totalDocsExamined,
    ms: indexPlan.executionStats.executionTimeMillis
  }
});
```

**Meaning:** `hint` lets you inspect a scan plan and an index plan against the same collection state. However:

- `hint({ $natural: 1 })` forces natural-order traversal where applicable, not a complete reproduction of every detail of the old baseline.
- Forcing an index can yield a **worse** plan than what the planner chooses automatically.
- Hinted results only prove conditional behavior in the **experiment**, not that the app will choose that index on its own.
- Always measure **without a hint** as well to verify the default post-optimization plan.

Do not ship hints to production based on small benchmarks; a hardcoded hint can stop the planner from picking a better index as data and queries evolve.

### 9.1. Explain and the Plan Cache

`explain()` generally **does not consult the plan cache the way normal queries do**, nor does it write explain's winning plan into the plan cache like a regular query run. Therefore, `explain()` is great for checking how the planner evaluates a query, yet **insufficient** to prove which cached plan the app uses or guarantee identical runtime latency.

To study live plan cache behavior, combine metrics from real queries, query monitoring tools, and version-appropriate plan cache metadata/commands, and compare execution behavior.

Never clear the plan cache arbitrarily in production just to "re-measure," because forcing widespread replanning can impact latency across many queries.

## 10. Measure Real Runtime, Not Just Explain

An experiment should have two layers:

1. **Explain:** explains why a query performs more or less work.
2. **Application benchmark:** measures real latency as code consumes results over network/driver/serialization under production-like conditions.

Simple measurement example in `mongosh`:

```javascript
function runTimedQuery(hintName) {
  const startedAt = Date.now();

  let cursor = db.planLabOrders.find(
    filter,
    projection
  )
  .sort(sort)
  .limit(limit);

  if (hintName !== null) {
    cursor = cursor.hint(hintName);
  }

  let count = 0;

  while (cursor.hasNext()) {
    cursor.next();
    count++;
  }

  return {
    elapsedMillis: Date.now() - startedAt,
    returned: count
  };
}

printjson(runTimedQuery(null));
printjson(runTimedQuery("idx_tenant_status_created_id"));
```

This example consumes the full 50-record result rather than timing cursor construction alone. Still, it remains a **single-threaded microbenchmark**. It does not capture HTTP endpoint latency, business logic, connection pooling, or concurrent request contention.

### 10.1. Measure Repeatedly and Report Median / p95

A single measurement is easily skewed by OS scheduling, page faults, GC, or cache state. Therefore:

- Warm up multiple times before collecting samples.
- Measure at least dozens of iterations in a quiet environment.
- Store **all samples**, not just averages.
- Report median (p50), p95, and spread/variance.
- Compare identical query shape, result count, and cursor consumption pattern.
- Interleave A/B variants to reduce temporal drift; do not always run all A before all B.

Example sampling helper:

```javascript
function measureMany(hintName, iterations) {
  const samples = [];

  for (let i = 0; i < iterations; i++) {
    const result = runTimedQuery(hintName);
    samples.push(result.elapsedMillis);
  }

  samples.sort((a, b) => a - b);

  const n = samples.length;
  const p50 = samples[Math.floor(0.50 * (n - 1))];
  const p95 = samples[Math.floor(0.95 * (n - 1))];

  return { samples, p50, p95 };
}

// Warm up before sampling.
for (let i = 0; i < 5; i++) {
  runTimedQuery(null);
}

printjson(measureMany(null, 30));
```

This percentile snippet illustrates order-statistic selection; observability tools may use different interpolation conventions. For sub-millisecond queries, `Date.now()` lacks resolution; use a high-resolution timer supported by your runtime.

### 10.2. Cold Cache vs. Warm Cache

The very first run may read disk pages from storage, while subsequent runs hit RAM. Separate:

- **Cold-cache behavior:** approximates a working set not yet resident in cache.
- **Warm-cache behavior:** approximates steady-state traffic with hot data/indexes.

Never restart MongoDB or flush OS caches on production to manufacture a cold cache. In test environments, follow a consistent reset procedure only if permitted and after assessing impact. Truly simulating a cold cache is hard; describe exact measurement conditions rather than labeling a script's first iteration "cold."

### 10.3. Measurement Order Can Introduce Bias

Example:

```text
1. Run baseline on a cold cache.
2. Build index (reads data, warming the cache).
3. Run after-test on a warm cache.
4. Claim the index made queries 100x faster.
```

That experiment **conflates index effects with cache effects**. To prevent this, warm up both cases appropriately, interleave runs in a test environment, or use equivalent snapshots/hosts under documented cache conditions.

## 11. Do Not Measure Only One Filter Value Combination

One query shape covers many real parameter combinations:

```javascript
{
  tenantId: tenant,
  status: status,
  createdAt: { $gte: from, $lt: to }
}
```

The planner might pick a great plan for a small tenant and a 1-month window, yet struggle for a huge tenant and a 6-month window.

Build a **variant matrix**:

| Case | Tenant | Status | Time Window | Purpose |
|---|---|---|---|---|
| A | Huge Tenant A | Common PAID | 1 day | Very narrow time filter |
| B | Huge Tenant A | Common PAID | 1 month | Typical query |
| C | Huge Tenant A | Common PAID | 6 months | Broad range query |
| D | Small Tenant C | PAID | 1 month | Low-volume tenant |
| E | Tenant A | Rare CANCELLED | 1 month | Uncommon status value |
| F | Tenant A | PAID | No date range | Tests tenant-wide sort/limit |

For each row:

1. Run before/after queries or controlled plan comparisons.
2. Record `nReturned`, keys/docs examined, stages, and latency.
3. Note actual production query frequency.
4. Check p95/p99 and concurrent load for critical endpoints.

Never report only the "best-case" parameter combo while ignoring what most users experience.

### 11.1. Selectivity and Cardinality

If `PAID` covers 70% of data, an index solely on `status` must scan huge numbers of keys. A compound index with `tenantId`, `status`, and `createdAt` narrows the slice far better.

One mental model:

```text
N = total documents
selectivity(tenantId) ≈ share of documents for tenant
selectivity(status)   ≈ share of documents with status
selectivity(date)     ≈ share of documents in date window
```

Do not naively multiply these fractions when fields are **correlated**. For example, Tenant A might be 95% `PAID` while Tenant B is only 10% `PAID`; assuming independence gives wrong estimates. Representative datasets must preserve key correlations.

### 11.2. Test Zero-Result Queries

Rare queries returning `nReturned = 0` also matter:

```javascript
db.planLabOrders.find({
  tenantId: "TENANT-C",
  status: "UNKNOWN",
  createdAt: {
    $gte: ISODate("2026-03-01T00:00:00Z"),
    $lt: ISODate("2026-04-01T00:00:00Z")
  }
})
.limit(50);
```

A query returning zero matches can still scan the entire collection if no index helps, making "not found" paths slow. Do not drop zero-result cases from benchmarks just because `nReturned` is zero for ratio calculations.

## 12. When a New Index Improves the Plan Yet Slows the System

Adding an index carries cost. Celebrating after measuring a single read query can overlook operational consequences.

### 12.1. Write Amplification

On every insert, MongoDB must update relevant indexes. On updates touching indexed fields, old keys must be removed and new keys inserted. Adding wide indexes can:

- Increase CPU/I/O for inserts/updates/deletes;
- Grow on-disk index footprint;
- Expand the cache working set;
- Lengthen index builds, backups, and restores;
- Reduce write throughput under heavy load.

Optimizing a critical read API can still be worth it, but quantify the trade-off with numbers.

### 12.2. Wider Indexes Are Not Automatically Better

Suppose you append `total` to the index:

```javascript
db.planLabOrders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1,
  total: 1
});
```

This index might allow a matching query to become covered under eligible conditions, skipping `FETCH`. Yet it also increases index key bytes and maintenance overhead.

On a write-heavy collection where reads need just 50 records, a narrower index with 50 `FETCH` operations can beat a huge index overall. Optimize for the **end-to-end workload**, not "covered at all costs."

### 12.3. Partial Indexes and Differing Conditions

If a query always filters `status: "PAID"`, a partial index shrinks the number of keys maintained:

```javascript
db.planLabOrders.createIndex(
  { tenantId: 1, createdAt: -1, _id: -1 },
  {
    name: "idx_paid_orders_partial",
    partialFilterExpression: { status: "PAID" }
  }
);
```

Queries using a partial index must include predicates implying `status: "PAID"`; a query filtering only tenant and time while expecting `PAID`/`PENDING`/`CANCELLED` cannot rely solely on a `PAID`-only partial index.

This is a **separate candidate index experiment** requiring its own selectivity, size, and write-cost comparison—not an "obvious win" for every endpoint.

## 13. Shifting Data Can Skew Comparisons

Before/after measurements require stable data as much as possible. In production, data rarely stands completely still:

- Import jobs insert new documents;
- Orders change status, shifting selectivity;
- TTL or retention jobs purge old data;
- New tenants onboard;
- Campaigns trigger traffic spikes;
- Index builds compete with active workloads.

### 13.1. Do Not Compare Distant Points in Time Ignoring Drift

If you capture baseline on 1 million documents in January and after-metrics on 20 million documents in July, you cannot attribute differences solely to the index. Conversely, if data was purged and shrank, queries may speed up even if the index is no better.

A proper report records:

```text
Collection/doc count at each run:
Data/index sizes:
Measurement timestamp:
MongoDB version:
Topology:
Tenant count and key distributions:
Existing indexes:
Read concern/read preference:
Concurrency/background load:
```

### 13.2. Test on the Same Snapshot or Environment Clone

Where feasible, you can:

- Use a test environment with an immutable dataset;
- Clone/snapshot a representative data state and run A/B comparisons;
- Run multiple plans on the same dataset via `hint` in a test environment;
- Evaluate index impact via canarying when production rollout carries risk.

Verify caches, hardware, settings, and background load; never call two clones with differing hardware or RAM sizes a "fair comparison."

## 14. Query Planner and Plan Cache Can Shift Behavior

The MongoDB query planner picks a plan using query shape, candidate indexes, statistics/trial execution, and version-specific logic. In eligible scenarios, the plan cache reuses plan choices for matching query shapes.

Implications for before/after tests:

- Adding or dropping an index alters the candidate plan pool.
- A shape optimal for a rare literal may perform poorly for a common literal.
- Replanning can occur when an active plan degrades.
- Changes in query shape, collation, or sort order can trigger a different plan.
- Explain does not fully reflect plan cache usage for regular requests.

### 14.1. Rejected Plans Are Not Necessarily "Wrong"

Explain may list `rejectedPlans`—candidates evaluated and not selected during that planning pass. A rejected plan is not necessarily inferior for **every filter literal and every data distribution**.

Do not assume the planner is buggy simply because an index a developer expected did not win. Compare costs across the real workload and understand why the planner scored them differently.

### 14.2. Impact of `hint`

When using:

```javascript
db.planLabOrders.find(filter, projection)
  .sort(sort)
  .limit(limit)
  .hint("idx_tenant_status_created_id");
```

the application requests a specific index. This helps in benchmarks, yet in production a hardcoded hint can cause regressions when:

- The dataset shifts;
- The query shape changes;
- The index is dropped or renamed;
- Filter values have vastly different selectivity;
- A newer MongoDB planner offers a better plan.

A hint should be a deliberate, monitored, evidence-backed decision—never a knee-jerk reaction whenever a plan looks unexpected.

## 15. Explain for Aggregation Pipelines

Many queries are aggregations rather than `find()`:

```javascript
db.planLabOrders.aggregate([
  {
    $match: {
      tenantId: "TENANT-A",
      status: "PAID",
      createdAt: {
        $gte: ISODate("2026-03-01T00:00:00Z"),
        $lt: ISODate("2026-04-01T00:00:00Z")
      }
    }
  },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 50 },
  {
    $project: {
      _id: 1,
      createdAt: 1,
      total: 1,
      status: 1
    }
  }
]);
```

One way to explain an aggregation is:

```javascript
db.planLabOrders.explain("executionStats").aggregate([
  {
    $match: {
      tenantId: "TENANT-A",
      status: "PAID",
      createdAt: {
        $gte: ISODate("2026-03-01T00:00:00Z"),
        $lt: ISODate("2026-04-01T00:00:00Z")
      }
    }
  },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 50 },
  {
    $project: {
      _id: 1,
      createdAt: 1,
      total: 1,
      status: 1
    }
  }
]);
```

MongoDB can push down `$match`, coalesce `$sort + $limit`, or combine stages depending on version. Aggregation explain layout can differ from `find()`: some stages report separate execution stats, while others embed inside the query planner.

### 15.1. Compare Only Semantically Equivalent Pipelines

If you move `$limit` ahead of `$match`:

```javascript
[
  { $limit: 50 },
  { $match: { status: "PAID" } }
]
```

the meaning changes from "first 50 `PAID` orders" to "take 50 documents, then keep `PAID` ones"—potentially returning fewer than 50 and missing valid matches. Never treat speeding up by doing less work **while changing results** as a valid optimization.

Similarly, moving `$project` before `$match` and dropping filtered fields breaks the pipeline. Every rewrite must preserve semantics, required fields, and ordering.

### 15.2. When Sorting Spills to Disk

Large sort/group pipelines consume substantial memory and, where settings/version allow, can spill to disk. Check spill metrics, memory usage, and latency instead of glancing only at `executionTimeMillis`.

Indexes matching `$match` and `$sort` can avoid blocking sorts, yet not every pipeline remains index-eligible after stages that transform documents. Inspect the optimized stage layout and actual query plan.

## 16. Index Experiments with Multiple Candidates

Suppose three candidate indexes exist:

```javascript
// I1: filter tenant + status.
db.planLabOrders.createIndex(
  { tenantId: 1, status: 1 },
  { name: "I1_tenant_status" }
);

// I2: filter + range/sort.
db.planLabOrders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: -1 },
  { name: "I2_full_query" }
);

// I3: filter tenant + sort, without status.
db.planLabOrders.createIndex(
  { tenantId: 1, createdAt: -1, _id: -1 },
  { name: "I3_tenant_time" }
);
```

You do not need to keep all three long-term. In a test environment, use `hint()` to measure each on the identical query:

```javascript
for (const indexName of [
  "I1_tenant_status",
  "I2_full_query",
  "I3_tenant_time"
]) {
  const plan = db.planLabOrders.find(filter, projection)
    .sort(sort)
    .limit(limit)
    .hint(indexName)
    .explain("executionStats");

  printjson({
    index: indexName,
    keys: plan.executionStats.totalKeysExamined,
    docs: plan.executionStats.totalDocsExamined,
    returned: plan.executionStats.nReturned,
    ms: plan.executionStats.executionTimeMillis
  });
}
```

Plausible interpretation:

- **I1:** filters tenant/status, yet still checks dates and sorts many candidates.
- **I2:** leverages tenant/status and `createdAt/_id` order, enabling early stop on limit.
- **I3:** walks chronologically within the tenant while skipping non-matching statuses; still competitive if `PAID` is near-universal and `limit` is small.

Thus, **I2 looks best aligned with the query shape**, yet cannot be declared the universal winner across all datasets. If `status` is 99% `PAID`, I3 may compete closely; if a tenant has few `PAID` orders, I2 pulls far ahead.

A good experiment is designed to **allow disproving the initial hypothesis**, not cherry-picking metrics to validate a predetermined index.

## 17. Index Creation Costs and Production Rollouts

Adding an index to a large collection carries costs beyond subsequent query latency.

Factors to weigh:

- CPU, I/O, and memory consumed during the build;
- Increased storage and cache working set;
- Impact on concurrent write operations;
- Replication lag and failover readiness during rollout;
- A rollback plan if queries regress or write throughput drops;
- Post-deploy monitoring across multiple traffic cycles.

A local dev benchmark **is not equivalent** to a production commitment on a replica set or sharded cluster. Roll out in production with controlled monitoring of p95/p99, slow query rates, CPU/IOPS, replication lag, and index size.

Before dropping an old index after adding a new one, verify whether other queries still rely on it. An index redundant for one query may be crucial for another endpoint.

## 18. Elements to Include in an Experiment Report

A structured report can follow this template:

```text
GOAL
  Endpoint: GET /tenants/{id}/orders
  Query shape: tenantId = ?, status = PAID,
               createdAt in [from, to),
               sort createdAt DESC, _id DESC, limit 50
  Target KPI: cut p95 latency without excessive write latency increase

ENVIRONMENT
  MongoDB version:
  Topology: standalone / replica set / sharded cluster
  CPU/RAM/storage:
  Read concern/read preference:
  Driver/version:
  Background load:

DATASET
  Document count:
  Avg / p95 document size:
  Tenant distribution:
  Status distribution:
  Time distribution:
  Existing indexes:

INTERVENTION
  Before:
  After index/query change:
  Factors held constant:

RESULTS
  nReturned:
  totalKeysExamined:
  totalDocsExamined:
  winningPlan/indexName:
  SORT/FETCH/spills:
  executionTimeMillis:
  Client p50/p95/p99:
  Write throughput/latency:
  Index size:
  Query correctness:

CONCLUSION
  Improved query shapes:
  Regressed query shapes:
  Index maintenance cost:
  Deploy / do-not-deploy decision:
  Post-rollout monitoring plan:
```

### 18.1. Illustrative Example Metrics Table

**This table uses hypothetical numbers to demonstrate formatting—not actual runs from a specific MongoDB host.**

| Metric | Before | After |
|---|---:|---:|
| Document count | 120,000 | 120,000 |
| `nReturned` | 50 | 50 |
| `totalDocsExamined` | 120,000 | 50 |
| `totalKeysExamined` | 0 | 50 |
| Blocking sort | Yes | No |
| `executionTimeMillis` | 92 ms | 4 ms |
| Client p50 | 105 ms | 9 ms |
| Client p95 | 160 ms | 18 ms |
| Added index storage | 0 MB | +measured amount |
| Write throughput | Baseline | Impact must be measured |

From this hypothetical table, the new plan **sharply cut examined documents** and improved latency for **this workload**. You still cannot claim the index is "system-wide optimal" without measuring other queries and write workloads.

## 19. Post-Deployment Query Monitoring

Pre-deploy benchmarking is only one step. Post-deploy, plans can shift as data grows or distributions change.

Signals to track:

- Endpoint p50/p95/p99 latency broken down by tenant/status/query pattern;
- Slow operation counts and heavy query shapes;
- `docsExamined`/`keysExamined` on critical queries;
- Chosen plan/index details during query investigations;
- Cache pressure, disk IOPS, CPU, and memory;
- Index size and observed index usage;
- Write latency and throughput;
- Replica set replication lag;
- Shard routing and load balance when sharded.

MongoDB offers tools like the profiler, diagnostic logs, `explain()`, `$indexStats`, and deployment monitoring. **Verbose profiling/diagnostic logging adds overhead and records sensitive query details**, so never enable high collection levels indefinitely in production without a plan.

### 19.1. Observing Index Usage Alone Is Insufficient to Drop an Index

You can inspect `$indexStats` to see index access counters within the limits of that mechanism:

```javascript
db.planLabOrders.aggregate([
  { $indexStats: {} }
]);
```

However, index usage stats depend on observation window, node, and query mix. An index rarely hit today might serve a month-end job or critical incident recovery. Never drop an index solely because access counts look low over a short window.

## 20. Common Mistakes in Before/After Comparisons

| Mistake | Why Conclusions Mislead | Fix |
|---|---|---|
| Testing on 20 documents | Collection scans stay tiny and cheap | Use realistic scale and distribution |
| Testing only one small tenant | Misses hot/giant tenants | Use a large/small tenant matrix |
| Seeding artificially uniform data | Distorts selectivity | Simulate skew and correlations |
| Changing query and index together | Cannot tell which caused the speedup | Isolate changes in separate runs |
| Comparing `executionTimeMillis` once | Cache and load add noise | Run many iterations; use median/p95 |
| Cold cache before, warm cache after | Credits cache warmth to the index | Control cache conditions |
| Not exhausting the cursor | Measures only query object creation | Consume full results in benchmarks |
| Seeing `IXSCAN` and calling it good | May scan millions of keys | Check keys/docs examined, sort, fetch |
| Thinking `COLLSCAN` is always wrong | Queries returning most docs may suit scan | Weigh total cost and SLA |
| Benchmarking only matching queries | Misses zero-result/miss queries | Add non-matching variants |
| Changing limit/sort/projection | Two queries are no longer equivalent | Freeze query shape |
| Using `hint()` after and calling it planner default | Hint forces the plan | Also run unhinted explain |
| Treating explain as live plan cache proof | Explain uses separate planner rules | Observe live runtime requests |
| Building wide indexes ignoring writes | Can regress overall system throughput | Measure write latency/throughput/size |
| Skipping post-deploy checks | Data distribution shifts over time | Monitor and keep a rollback plan |

## 21. Practice Exercises

### Exercise 1 — Baseline on a Representative Dataset

Create `planLabOrders` using the script in section 3. Run the section 4 query before creating any compound index. Record `nReturned`, `totalDocsExamined`, `totalKeysExamined`, `executionTimeMillis`, and the winning plan. Explain why the baseline on 120,000 documents differs from testing on 50 documents.

### Exercise 2 — Measuring Before and After Creating an Index

Create the index:

```javascript
db.planLabOrders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
});
```

Re-run the exact same query. Compare metrics and identify the index used. Is there a `SORT`? Is there a `FETCH`? Why must the query still read `total` from documents?

### Exercise 3 — Using `hint` to Contrast Two Plans

After creating the index, compare:

```javascript
// Force natural scan.
db.planLabOrders.find(filter, projection)
  .sort(sort).limit(50)
  .hint({ $natural: 1 })
  .explain("executionStats");

// Force compound index.
db.planLabOrders.find(filter, projection)
  .sort(sort).limit(50)
  .hint("idx_tenant_status_created_id")
  .explain("executionStats");
```

Explain how this test complements before/after comparisons, and why it does not prove an unhinted production query will choose that index.

### Exercise 4 — Varying Selectivity

With the same index, test:

1. Tenant A, status `PAID`, 6-month range.
2. Tenant C, status `PAID`, 1-day range.
3. Tenant A, status `CANCELLED`, 1-month range.
4. Tenant A, status `PAID`, no date range.

Tabulate keys/docs examined and execution time. Explain why record volume and value distribution impact index efficiency even though the query uses the same fields.

### Exercise 5 — Projection and Covered Queries

Run two queries:

- Query A returns `total` alongside the indexed fields.
- Query B returns only `tenantId`, `status`, `createdAt`, and `_id`.

Observe `totalDocsExamined` and `FETCH`. Why can you not claim Query B proves the index improved **Query A** enough to skip reading documents?

### Exercise 6 — Benchmark Matrix with p95

Write a helper running the query 50 times in `mongosh` or the Java driver, with warm-up and full result consumption. Measure p50/p95, then compare indexes `I1`/`I2`/`I3` across three tenant/status groups. Describe your strategy for controlling cache and background load.

### Exercise 7 — Weighing Index Cost

Suppose a new index drops read API p95 from 120 ms to 25 ms, yet raises insert p95 from 15 ms to 22 ms. Reads run at 3,000 req/s, inserts run at 2,500 req/s, and the cluster is near CPU saturation. Should you keep the index? Propose what additional measurements to gather before deciding, rather than looking solely at read gains.

### Exercise 8 — Technical Review Report

Write a 1–2 page index proposal report covering hypothesis, dataset, query shape, environment, before/after explain, p50/p95, affected queries, index size, correctness checks, and rollback plan. Clearly separate **measured data** from **projections**.

## 22. MongoDB Reference Documentation

- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [db.collection.explain()](https://www.mongodb.com/docs/manual/reference/method/db.collection.explain/)
- [Query Optimization](https://www.mongodb.com/docs/manual/core/query-optimization/)
- [Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/)
- [Sort Results with Indexes](https://www.mongodb.com/docs/manual/tutorial/sort-results-with-indexes/)
- [Query Plans](https://www.mongodb.com/docs/manual/core/query-plans/)
- [Plan Cache](https://www.mongodb.com/docs/manual/core/query-plans/#plan-cache)
- [Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/)
- [Index Statistics](https://www.mongodb.com/docs/manual/reference/operator/aggregation/indexStats/)

## Conclusion

Comparing **before-and-after** execution plans is an engineering experiment, not merely spotting `IXSCAN` in place of `COLLSCAN`. Reliable conclusions require a **representative dataset**, equivalent queries, documented environments, varied selectivity cases, and repeated measurements.

Use `explain("executionStats")` to understand cost: `nReturned`, `totalKeysExamined`, `totalDocsExamined`, `FETCH`, `SORT`, and selected indexes. Use real benchmarks to measure p50/p95 latency while controlling cache and plan state, then factor in index storage and write amplification. When needed, use `hint()` on the same dataset to isolate plan costs, while always measuring unhinted queries and monitoring live plan cache/query behavior in the application.

**Conclude a new index or query is better only when it returns exact results, cuts cost on critical workloads, and avoids unacceptable system-wide regressions.** Evidence from realistic data outweighs the feeling that a plan "looks prettier" in explain.
