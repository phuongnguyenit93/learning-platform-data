# Slow Queries Caused by Missing Indexes, Sorts, Collations, or Data Types in MongoDB

> **Module:** Database Engine Document MongoDB  
> **Chapter:** Troubleshooting  
> **Lesson:** Slow Queries Caused by Missing Indexes, Sorts, Collations, or Data Types

## 1. Scenario and Objectives

An e-commerce application using MongoDB has four endpoints that suddenly slow down or return incomplete results:

- `GET /orders?tenant=t05&status=PAID` scans hundreds of thousands of records just to fetch the 20 latest orders.
- A reporting API calling `sort({createdAt:-1})` has to sort in RAM and occasionally spills temporary files.
- A case-insensitive customer name lookup already has an index, yet the optimizer still chooses `COLLSCAN`.
- A query filtering after November 1 misses several documents because `createdAt` is stored as a mix of BSON Date and String.

All four may surface under the symptom "MongoDB slow query," yet they cannot be fixed with the same `createIndex()` command. The right approach begins by **verifying result correctness, query shape, BSON types, collation, index catalog, and execution plan**, and only then testing a fix and measuring impact.

### 1.1. Learning Objectives

After this lesson, you will be able to:

1. Identify slow queries from logs, the profiler, metrics, and application traces.
2. Read `explain("executionStats")` to quantify how many documents/index keys are examined.
3. Distinguish a missing index from an incorrectly ordered or insufficiently selective index.
4. Analyze `IXSCAN`, `COLLSCAN`, `FETCH`, `SORT`, and `indexBounds`.
5. Design compound indexes by equality/sort/range, understanding ESR and ERS.
6. Explain blocking sorts, memory spills, pagination, and sort directions.
7. Diagnose collation mismatches across queries, collections, and indexes.
8. Understand `strength`, `locale`, `numericOrdering`, and the limitations of `$regex /i`.
9. Detect and fix String/ObjectId, String/BSON Date, and String/Number mismatches.
10. Practice with `mongosh`, Java Sync Driver, Spring Data, testing, and production runbooks.

### 1.2. Classifying the Four Causes

| Cause | Initial clue | How to verify |
|---|---|---|
| Missing or wrong index | `COLLSCAN`, high `docsExamined` | `getIndexes()`, `explain`, query filter |
| Sort without a supporting index | `SORT`, memory/spill, latency grows with dataset | Sort fields/direction, index prefix, `explain` |
| Collation mismatch | String index exists yet does not support comparison | Index/collection/query collation |
| Inconsistent BSON types | Query misses results, type-casting filters, weird sort order | `$type`, query operand types, migration history |

**Warning:** `COLLSCAN` on a small collection or an analytical query scanning everything may be reasonable. Conversely, an `IXSCAN` scanning millions of keys can still be very slow. Never judge by stage name alone.

---

## 2. Identifying Where "Slow" Actually Lives

An HTTP request passes through multiple layers:

```text
HTTP client
    │
    ├── API authentication, validation, serialization
    ├── Java Driver server selection / connection pool
    ├── Network, TLS, retries
    ▼
MongoDB server
    │
    ├── Query parse, optimization, plan cache
    ├── Index scan or collection scan
    ├── FETCH / filter
    ├── SORT / aggregation / grouping
    ├── Storage cache, I/O, concurrency
    └── Cursor firstBatch / getMore
    ▼
Java Driver BSON decoding
    │
    ▼
HTTP response
```

If application p99 is 1 second while the MongoDB server-side command took only 20 ms, investigate connection pools/network/application code. If the profiler records 700 ms, `docsExamined=900000`, and `planSummary=COLLSCAN`, the query plan takes priority.

### 2.1. What Facts Must Be Collected?

- Namespace, timestamp, host/member/shard, and MongoDB Server version.
- Query filter, projection, sort, collation, limit, skip, hint.
- Actual BSON types of operands and stored fields.
- Collection document count and data distribution.
- Index catalog (keys, order, collation, hidden/partial options).
- Explain statistics and slow log/profiler records.
- Application/driver metrics and resource utilization.
- Recent deploys, schema migrations, or index changes.

### 2.2. Query Correctness Comes Before Performance

A query passing a String to find an `ObjectId` can return 0 documents very quickly. That is a **correctness bug**. If the application sees 0 results and falls back to scanning the whole collection with type conversion, it becomes a **performance bug** too. Always verify correct results before "optimizing."

---

## 3. Capture the Exact Query Shape

Example:

```javascript
db.orders.find(
  {
    tenantId: "t05",
    status: "PAID"
  },
  {
    customerId: 1,
    total: 1,
    createdAt: 1
  }
)
.sort({ createdAt: -1, _id: -1 })
.limit(20)
.collation({ locale: "simple" });
```

Do not omit any detail:

- Adding `tenantId` can change which index is needed.
- `sort({_id:-1})` as a tie-breaker can change index direction requirements.
- `limit` affects top-N plans.
- `collation` affects string comparison and index eligibility.
- `$in`, `$gt`, and `$ne` have different selectivity than equality.
- `hint` may force a suboptimal index.
- Query parameters for a tenant with 500 records behave differently from a tenant with 5 million records.

### 3.1. Two Non-Equivalent Queries

```javascript
db.orders.find({ status: "PAID" })
  .sort({ createdAt: -1 })
  .limit(20);

db.orders.find({ tenantId: "t05", status: "PAID" })
  .sort({ createdAt: -1 })
  .limit(20);
```

A compound index with an equality prefix on `tenantId` may be great for the second query yet not necessarily optimal for the first.

### 3.2. Do Not Read Only Source Code

An application might pass a String instead of a BSON Date, attach a sort/hint via a framework, or apply a per-request collation. When needed, use sanitized driver command monitoring to confirm the exact command sent to the server.

---

## 4. Interpreting `explain("executionStats")`

### 4.1. Basic Command

```javascript
const plan = db.orders.find({
  tenantId: "t05",
  status: "PAID"
})
.sort({ createdAt: -1 })
.limit(20)
.explain("executionStats");

printjson(plan.queryPlanner);
printjson(plan.executionStats);
```

Three common verbosity levels:

- `queryPlanner`: winning plan and rejected candidates when available.
- `executionStats`: statistics from executing the winning plan.
- `allPlansExecution`: adds trial execution details for candidate plans.

### 4.2. Key Fields

| Field | What to understand |
|---|---|
| `nReturned` | Number of documents returned by the explained execution |
| `totalDocsExamined` | Number of document examinations (may count a document multiple times) |
| `totalKeysExamined` | Number of index entries examined |
| `winningPlan` | Access path chosen by the planner |
| `indexName` | Index used by the stage, if any |
| `indexBounds` | Key bounds/ranges scanned |
| `executionTimeMillis` | Timing of the explain run, not a stable latency guarantee |
| `usedDisk`/`spills` | Disk spill signal when supported |

### 4.3. Collection Scan Example

```javascript
{
  queryPlanner: {
    winningPlan: { stage: "COLLSCAN" }
  },
  executionStats: {
    nReturned: 20,
    totalDocsExamined: 500000,
    totalKeysExamined: 0,
    executionTimeMillis: 400
  }
}
```

Numbers are illustrative. For a listing API returning 20 documents, `500000/20=25000` is a scan ratio worth investigating.

### 4.4. Efficient Indexed Access Example

```javascript
{
  queryPlanner: {
    winningPlan: {
      stage: "FETCH",
      inputStage: {
        stage: "IXSCAN",
        indexName: "idx_tenant_status_created"
      }
    }
  },
  executionStats: {
    nReturned: 20,
    totalDocsExamined: 20,
    totalKeysExamined: 20
  }
}
```

This is simplified example output, not a fixed JSON schema.

### 4.5. Do Not Rely on an Exact Plan Tree Shape Generally

MongoDB Classic Engine, SBE, EXPRESS fast paths, and sharded explains produce different structures. Different versions expose:

```text
winningPlan.inputStage
winningPlan.queryPlan
winningPlan.slotBasedPlan
per-shard winningPlans
```

Only hardcode stage paths when tests pin a specific MongoDB version/topology. Prefer reading logical work counters and index metadata.

### 4.6. Explain Does Not Fully Reflect the Production Plan Cache

Per MongoDB documentation, `explain()` bypasses the existing cached plan and does not cache the winning plan from the explain run. Therefore, explain is **evidence of query behavior at test time**, not proof of the exact plan used by a prior production request.

### 4.7. Do Not Assert Arbitrary Execution Timings

Bad for CI regression:

```javascript
if (plan.executionStats.executionTimeMillis > 10) {
  throw new Error("Slow query");
}
```

Better direction:

```javascript
const s = plan.executionStats;
if (s.totalDocsExamined > 100 ||
    s.totalKeysExamined > 200) {
  throw new Error("Excessive scan work");
}
```

Thresholds make sense only for a fixed fixture and query. Latency SLOs still require separate benchmarking.

---

## 5. Cause 1: Missing or Unsuitable Indexes

### 5.1. `getIndexes` Is the First Step

```javascript
db.orders.getIndexes();
```

Check:

- Key pattern and order.
- Direction (`1`/`-1`).
- Unique, partial, sparse, hidden flags.
- Index type (B-tree, hashed, text, wildcard, multikey).
- Collation.
- Same database/collection on the right cluster.

### 5.2. Multiple Single-Field Indexes Are Not Equivalent to a Compound Index

Suppose you have:

```javascript
db.orders.createIndex({ tenantId: 1 });
db.orders.createIndex({ status: 1 });
db.orders.createIndex({ createdAt: -1 });
```

Query:

```javascript
db.orders.find({
  tenantId: "t05",
  status: "PAID"
}).sort({ createdAt: -1 }).limit(20);
```

MongoDB may have to scan a wide single index and then filter/sort separately. Although the engine can use index intersection in certain cases, that is no guaranteed substitute for a workload-matched compound index.

### 5.3. Proposed Compound Index

```javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_tenant_status_created" }
);
```

This index orders the two equality predicates first and the sort field after.

### 5.4. Why Does Key Order Matter?

Index:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

differs from:

```javascript
{ createdAt: -1, status: 1, tenantId: 1 }
```

for narrowing bounds by tenant/status and reading `createdAt` in order. Never treat a compound index as an unordered list of field names.

### 5.5. Prefix Rule

Index:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

has prefixes:

```javascript
{ tenantId: 1 }
{ tenantId: 1, status: 1 }
{ tenantId: 1, status: 1, createdAt: -1 }
```

A query filtering only on `status:"PAID"` without `tenantId` cannot narrow bounds the way a query supplying the equality prefix can.

### 5.6. Reading `indexBounds`

Explain might show:

```javascript
indexBounds: {
  tenantId: ['["t05", "t05"]'],
  status: ['["PAID", "PAID"]'],
  createdAt: ["[MaxKey, MinKey]"]
}
```

Output is illustrative; bounds syntax, ordering, and availability vary by engine/version.

- Tight equality bounds: great for selective filters.
- Nearly full-domain bounds: the index may scan broadly.
- Missing prefix predicates: trailing keys cannot be leveraged efficiently.

### 5.7. An Index Is Not Always Chosen

Even when a suitable index exists, the planner may choose `COLLSCAN` on tiny collections or unselective predicates. Verify data distribution and cost rather than forcing indexes blindly.

---

## 6. ESR/ERS: Equality, Sort, Range

### 6.1. The ESR Guideline

- **E — Equality**: fields matched by exact equality.
- **S — Sort**: fields defining ordering.
- **R — Range**: `$gte`/`$lte`/`$gt`/`$lt` bounds.

Query:

```javascript
db.orders.find({
  tenantId: "t05",
  status: "PAID",
  total: { $gte: 1000 }
}).sort({ createdAt: -1 }).limit(20);
```

Candidate ESR index:

```javascript
{
  tenantId: 1,
  status: 1,
  createdAt: -1,
  total: 1
}
```

### 6.2. When ERS Can Be Better

If `total>=1000000` is extremely selective, an index:

```javascript
{
  tenantId: 1,
  status: 1,
  total: 1,
  createdAt: -1
}
```

may scan far fewer entries, even if it requires an in-memory sort. ESR prioritizes avoiding sorts; ERS prioritizes narrowing early by range. **No single key order is optimal for every query.**

### 6.3. How to Decide

1. Estimate equality selectivity.
2. Assess whether the range predicate is highly selective.
3. Estimate how many rows actually need sorting.
4. Compare `explain` across candidate indexes in a test environment.
5. Benchmark if cost/time differences are significant.
6. Evaluate write amplification and index size.

### 6.4. Do Not Create Unlimited Indexes for Every Query

Every index adds storage, cache pressure, and insert/update/delete overhead. Design indexes covering key query shape families and avoid redundant indexes.

---

## 7. Why Does an Index Exist Yet `COLLSCAN` Still Happen?

| Cause | Example |
|---|---|
| Index lacks equality prefix | Index starts with `customerId`, query filters only `status` |
| Index lacks sort field | Filter works well, yet triggers blocking `SORT` |
| Very unselective filter | 95% of documents match |
| Small collection | Full scan is cheaper than index traversal |
| Partial index does not cover query | Query omits `active:true` predicate |
| Hidden index | Index exists in catalog, yet planner ignores it |
| Index collation mismatch | String equality with simple query, ICU index |
| Query computes expression on field | `$expr/$toDate` prevents direct index use |
| Hint forces wrong index | App hardcodes an outdated hint |
| Different shard/node | Index build/status or workload differs from expectation |
| Query type mismatch | Filter misses or forces conversion |
| Plan cache/replanning | Production cached plan differs from explain |

### 7.1. Partial Index

```javascript
db.orders.createIndex(
  { tenantId: 1, createdAt: -1 },
  {
    name: "idx_active_by_tenant",
    partialFilterExpression: { active: true }
  }
);
```

A query that does not guarantee `active:true` cannot use this partial index because doing so would miss inactive documents the query might require.

### 7.2. Hidden Index

A hidden index appears in `getIndexes()` yet is ignored by the optimizer. Do not immediately create a duplicate index; check the hidden flag and rollout history first.

### 7.3. Hashed Index

A hashed index suits equality/sharding workloads, not range scans or sorts like ascending/descending B-tree indexes. Distinguish index types.

### 7.4. Multikey Index

Array values generate multiple index entries; `keysExamined` can exceed `docsExamined`. Compound multikey indexes have restrictions; sorting on an array field may still require an in-memory sort.

### 7.5. Wildcard/Text Indexes

Wildcard, text, geospatial, and vector/search indexes behave differently from conventional compound indexes. Do not apply scalar equality ESR heuristics to every search type.

---

## 8. Cause 2: Sorts Making Queries Slow

### 8.1. Indexes Can Provide Sort Order

With:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

the query:

```javascript
db.orders.find({
  tenantId: "t05",
  status: "PAID"
}).sort({ createdAt: -1 }).limit(20);
```

can walk entries in order and avoid an extra sort stage.

### 8.2. Blocking Sort

When no index supports the order:

```text
COLLSCAN/IXSCAN → FETCH/filter → SORT → LIMIT
                                      │
                                      └── memory or disk spill
```

A query returning only 20 documents after `limit` may have to read and sort huge numbers of candidates.

### 8.3. Clues

- Plan contains `SORT` or an equivalent engine stage.
- High docs/keys examined.
- Memory/spill statistics when supported.
- Logs/profiler show `usedDisk`.
- Latency grows sharply as candidate count rises.

### 8.4. Index Sort Direction

A single-field index:

```javascript
{ createdAt: 1 }
```

supports both ascending and descending sorts by walking forward or backward.

A compound index with multiple sort fields only supports matching direction patterns or inverting the **entire** pattern.

For example, index:

```javascript
{ score: -1, createdAt: 1 }
```

typically supports:

```javascript
{ score: -1, createdAt: 1 }
{ score: 1, createdAt: -1 }
```

and does not support as efficiently:

```javascript
{ score: -1, createdAt: -1 }
```

### 8.5. Equality Prefix Before Sort

Index:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

generally requires equality predicates on leading keys `tenantId`/`status` to satisfy the `createdAt` sort efficiently.

If `status` varies because the query filters only on `tenantId`, entries are grouped by `status` rather than forming one monotonic descending `createdAt` sequence across the whole tenant.

### 8.6. When a Sort Is Acceptable

A report doing a full scan and sorting 2,000 records may already be fast enough. Do not force a new index if its write overhead outweighs the real benefit.

---

## 9. Sort Memory, Disk Spill, and `allowDiskUse`

### 9.1. Memory Limits

Many MongoDB releases enforce a memory threshold around 100 MB for pipeline stages like `$sort`. Starting in MongoDB 6.0, `allowDiskUseByDefault` governs whether stages exceeding the threshold spill to disk by default or error. Newer versions may also enforce per-operation memory limits.

Always verify the actual MongoDB Server version and configuration before concluding.

### 9.2. `allowDiskUse`

```javascript
db.orders.aggregate(
  [
    { $match: { status: "PAID" } },
    { $sort: { createdAt: -1 } }
  ],
  { allowDiskUse: true }
);
```

This permits temporary disk usage when supported by the operation/stage; **it does not mean the query is optimized**. It can raise disk I/O, latency, and storage pressure.

### 9.3. `$sort` + `$limit`

```javascript
db.orders.aggregate([
  { $match: { tenantId: "t05", status: "PAID" } },
  { $sort: { createdAt: -1 } },
  { $limit: 20 }
]);
```

MongoDB can coalesce `$sort` and `$limit` when no intervening stage alters row count, retaining only the top N items.

### 9.4. Wrong Order Changes Results

Never rewrite:

```javascript
[{ $sort: { createdAt: -1 } }, { $limit: 20 }]
```

as:

```javascript
[{ $limit: 20 }, { $sort: { createdAt: -1 } }]
```

if the business requires the 20 newest documents across the whole collection. The second version sorts only the first 20 arbitrary documents fetched.

### 9.5. Sorting After Aggregation

```javascript
db.orders.aggregate([
  { $group: { _id: "$tenantId", revenue: { $sum: "$total" } } },
  { $sort: { revenue: -1 } }
]);
```

`revenue` is a computed field produced after `$group`; an index on raw `total` cannot satisfy sorting by grouped `revenue`. You may need materialized summaries, caching, batch reports, or an accepted bounded sort.

---

## 10. Stable Sorting, Pagination, and `skip`

### 10.1. Non-Deterministic Order with Duplicate Sort Values

If two documents share the same `createdAt`, sorting by:

```javascript
.sort({ createdAt: -1 })
```

does not guarantee a deterministic order among documents with equal timestamps.

### 10.2. Tie-Breaker

```javascript
.sort({ createdAt: -1, _id: -1 })
```

Candidate index:

```javascript
{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }
```

Ensure `_id` types/schemas are consistent, especially with legacy data.

### 10.3. Deep `skip`

```javascript
db.orders.find(filter)
  .sort({ createdAt: -1, _id: -1 })
  .skip(100000)
  .limit(20);
```

Even with a matching index, the server must still walk through 100,000 entries to discard the large offset.

### 10.4. Keyset Pagination

Save the boundary of the last item on the page:

```javascript
const lastCreatedAt =
  ISODate("2026-11-01T10:00:00Z");
const lastId = "t05-0999"; // If _id is String in the schema.

db.orders.find({
  tenantId: "t05",
  status: "PAID",
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

Do not apply verbatim if `_id` is an `ObjectId` or uses a different sort/collation. Verify lexicographic ordering, tie-breakers, and behavior when data mutates between pages.

---

## 11. Cause 3: Collation Mismatch

### 11.1. What Is Collation?

Collation defines string comparison rules for locale, letter case, diacritics, numeric ordering, and ICU rules. When neither collection nor query specifies collation, MongoDB defaults to `locale:"simple"` with binary comparison.

Three places must be checked:

1. Collection default collation.
2. Index collation.
3. Query/aggregate collation.

### 11.2. Case-Insensitive Index

```javascript
db.customers.createIndex(
  { displayName: 1 },
  {
    name: "idx_name_ci",
    collation: { locale: "en", strength: 2 }
  }
);
```

`strength:2` typically ignores case while distinguishing accents per the ICU locale. `strength:1` typically ignores both accents and case at the primary comparison level, depending on locale/options.

### 11.3. Query Matching Collation

```javascript
db.customers.find({ displayName: "alice" })
  .collation({ locale: "en", strength: 2 });
```

If the collection defaults to `simple`, the query:

```javascript
db.customers.find({ displayName: "alice" });
```

uses binary semantics. An ICU strength-2 index cannot satisfy the binary string comparison of a `simple` query.

### 11.4. Collation Mismatch Does Not Always Invalidate the Whole Index

A compound index with an ICU collation may still support comparisons on non-string prefix fields depending on the query. More precisely, a mismatch prevents the index from **supporting string comparisons or string sorts** with differing semantics.

### 11.5. Inspecting Metadata

```javascript
db.customers.getIndexes();
```

Inspect all of:

- `locale`.
- `strength`.
- `caseLevel`.
- `numericOrdering`.
- Other related options.

Do not check only field names.

### 11.6. Default Inheritance

If a collection has a default collation, indexes and operations inherit it unless explicitly overridden. Check when and with what options the collection was created.

---

## 12. Strength, Vietnamese Diacritics, and Semantics Changes

### 12.1. Common Levels

| Strength | Brief description |
|---|---|
| `1` Primary | Ignores most case/accent differences |
| `2` Secondary | Typically distinguishes accents while ignoring case |
| `3` Tertiary | Typically considers case as well |
| `4`/`5` | Additional fine-grained distinctions per locale/settings |

This is an ICU overview; actual behavior depends on locale and settings.

### 12.2. Vietnamese Names

For names like `Nguyễn`, `nguyen`, `NGUYỄN`, the API must decide:

- Exact match or case-insensitive?
- Accent-insensitive or accent-sensitive?
- Prefix or substring matching?
- Is stored text normalized to Unicode NFC/NFD?
- Are multiple languages supported?

Do not assume `locale:"en"` fits all Vietnamese rules. Test `locale:"vi"` and strength levels appropriate for your environment.

### 12.3. Unique Indexes Can Be Affected

```javascript
db.users.createIndex(
  { username: 1 },
  {
    unique: true,
    name: "uq_username_ci",
    collation: { locale: "en", strength: 2 }
  }
);
```

This treats `alice` and `ALICE` as duplicates. Changing collation can cause an index build to fail on existing data, so audit duplicate candidates before rollout.

### 12.4. Do Not Change Collation Just to "Speed Up"

Collation changes **correctness**. If a query used to be case-sensitive and becomes case-insensitive, matching results change. Test business semantics and unique constraints.

---

## 13. `$regex /i` and the Limits of Collation Indexes

### 13.1. Common Anti-Pattern

```javascript
db.customers.find({
  displayName: { $regex: "^alice", $options: "i" }
});
```

The team builds an index:

```javascript
db.customers.createIndex(
  { displayName: 1 },
  { collation: { locale: "en", strength: 2 } }
);
```

MongoDB documentation notes that `$regex` is **not collation-aware**, so case-insensitive indexes do not speed up regex queries the way they speed up collation-matched equality queries.

### 13.2. Different Search Patterns

| Search type | Recommendation |
|---|---|
| Case-insensitive equality | Matching query/index collation |
| Case-sensitive anchored prefix | Can use B-tree prefix range when suitable |
| Case-insensitive prefix | Normalized search key or dedicated search engine |
| Substring/full-text | Consider specialized text/search index or Atlas Search |
| Fuzzy, accent-aware | Design search semantics & relevance, not plain B-tree |

### 13.3. Normalized Fields

Example:

```json
{
  "displayName": "Nguyễn Văn A",
  "searchKey": "nguyen van a"
}
```

Index `searchKey` once business rules define normalization. Never roll a custom accent-stripping algorithm without Unicode/locale testing, and do not equate normalized keys with full ICU comparison.

### 13.4. User-Supplied Regex Input

Never pass raw user regex strings into MongoDB unchecked; regular expressions can burn CPU or trigger broad scans. Enforce length limits, allowed operators, and proper escaping/validation.

---

## 14. `numericOrdering` Is Not String-to-Number Casting

Data:

```javascript
{ code: "2" }
{ code: "10" }
{ code: "100" }
```

Simple lexicographic order is `"10", "100", "2"`.

```javascript
db.codes.find().sort({ code: 1 })
  .collation({ locale: "en", numericOrdering: true });
```

sorts non-negative integer digit substrings numerically.

### 14.1. Limitations

Per MongoDB documentation, `numericOrdering:true` does not fully handle:

- Negative or plus signs.
- Decimal separators.
- Exponents.
- Very long digit strings.

Never use `numericOrdering` as a substitute for numeric modeling of currency, quantities, or measurements.

### 14.2. Choose BSON Numeric Types for Prices

If `price` needs numeric comparisons, store it as `NumberInt`/`NumberLong`/`Double`/`Decimal128` as appropriate, rather than storing Strings and hoping collation interprets them.

---

## 15. Cause 4: Inconsistent BSON Types

### 15.1. Flexible Schemas Are Double-Edged

MongoDB permits a field to hold different types unless schema validation is enforced.

Example:

```javascript
{
  _id: ObjectId("65b8f9a53a9b43885f4e52c1"),
  createdAt: ISODate("2026-11-01T00:00:00Z"),
  total: NumberDecimal("150.00")
}

{
  _id: "65b8f9a53a9b43885f4e52c2",
  createdAt: "2026-11-02T00:00:00Z",
  total: "150.00"
}
```

An index on `createdAt` does not auto-convert Strings to Dates; an index on `total` does not turn Strings into Decimal128.

### 15.2. Symptoms

- Lookups by "identical-looking" IDs fail to match.
- Date ranges return incomplete results.
- Sorting dates/prices splits values into unexpected groups.
- Queries using `$toDate`/`$toString` on fields do heavy scan work.
- A CSV/JSON migration altered BSON types.
- Two services serialize fields with different conventions.

### 15.3. Type Bracketing

Comparison query operators `$gt`, `$gte`, `$lt`, `$lte` apply **type bracketing**: they compare against BSON values within the matching type category.

### 15.4. Numeric Types Form One Comparison Group

Int32, Int64, Double, and Decimal128 are treated by MongoDB as numeric types comparable with one another under numeric comparison semantics. String `"150"` is **not** Number `150`.

### 15.5. `$ne`/`$nin` Differ from Range Predicates

`$ne` and `$nin` do not type-bracket the same way `$gt/$gte/$lt/$lte` do. Do not extrapolate from `$ne` behavior to assume range queries auto-cast types.

### 15.6. BSON Sort Order

With mixed types, MongoDB sorts according to BSON type comparison order. Never assume all values displaying as "dates" sort chronologically if some are stored as strings.

---

## 16. `ObjectId` Differs from `String`

### 16.1. Creating a Document with `ObjectId`

```javascript
db.orders.insertOne({
  _id: ObjectId("65b8f9a53a9b43885f4e52c1"),
  status: "PAID"
});
```

### 16.2. Wrong-Type Query

```javascript
db.orders.findOne({
  _id: "65b8f9a53a9b43885f4e52c1"
});
```

A BSON String does not equal the corresponding BSON `ObjectId`. It returns `null` even though both display the exact same hex characters.

### 16.3. Correct Query

```javascript
db.orders.findOne({
  _id: ObjectId("65b8f9a53a9b43885f4e52c1")
});
```

### 16.4. Server-Side Conversion Anti-Pattern

```javascript
db.orders.find({
  $expr: {
    $eq: [
      { $toString: "$_id" },
      "65b8f9a53a9b43885f4e52c1"
    ]
  }
});
```

The server must evaluate the expression across documents and may not use the `_id` index directly. Convert incoming IDs to the right BSON type at the application boundary.

### 16.5. Do Not Convert Every String ID to `ObjectId`

Many schemas intentionally store String IDs. The actual stored type in the collection dictates whether to query by String or `ObjectId`—never guess from string length.

---

## 17. BSON `Date` Differs from ISO Date Strings

### 17.1. Data

```javascript
{ _id: 1, createdAt: ISODate("2026-11-01T00:00:00Z") }
{ _id: 2, createdAt: "2026-11-01T00:00:00Z" }
```

### 17.2. Date Range Query

```javascript
db.events.find({
  createdAt: {
    $gte: ISODate("2026-10-01T00:00:00Z")
  }
});
```

A range predicate using BSON Date will not auto-parse String fields into Dates.

### 17.3. Checking Types

```javascript
db.events.aggregate([
  {
    $group: {
      _id: { $type: "$createdAt" },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
```

### 17.4. Why Are ISO Strings Still Problematic?

There may be:

- Mixed `+07:00` and `Z` offsets.
- Formats missing milliseconds.
- Inconsistent date string formats.
- Mixed Strings and Dates.
- Parse errors or implicit timezone assumptions.

Even though uniformly formatted UTC ISO strings happen to share lexicographic order, they are no substitute for BSON Date.

### 17.5. `$toDate` Inside `$expr`

```javascript
db.events.find({
  $expr: {
    $gte: [
      { $toDate: "$createdAt" },
      ISODate("2026-11-01T00:00:00Z")
    ]
  }
});
```

This forces runtime conversion across many documents, hindering direct index usage. Unparseable strings will also fail the operation.

### 17.6. Remediation Path

- Parse/validate at the Java API boundary.
- Migrate String → BSON Date in safe batches.
- Enforce schema validation.
- Test timezone and Date precision.
- Review indexes once data types are consistent.

---

## 18. Numeric BSON Types and Numeric Strings

Data:

```javascript
db.products.insertMany([
  { _id: 1, price: NumberInt(150) },
  { _id: 2, price: NumberLong("150") },
  { _id: 3, price: 150.0 },
  { _id: 4, price: NumberDecimal("150.00") },
  { _id: 5, price: "150" }
]);
```

Query:

```javascript
db.products.find({
  price: { $gte: 100 }
});
```

This matches the numeric values, yet will not auto-convert String `"150"`.

### 18.1. Why Is This Both a Correctness and a Performance Issue?

If the UI misses products with String prices, a developer might write a fallback aggregation converting the entire collection, creating CPU pressure instead of fixing the schema.

### 18.2. Decimal128 and Currency

When exact decimal semantics are required, consider `Decimal128`/Java `BigDecimal` mapping or integer minor units per policy. Never change numeric production schemas without reviewing converters and rounding rules.

### 18.3. Checking with `$type`

```javascript
db.products.aggregate([
  {
    $group: {
      _id: { $type: "$price" },
      count: { $sum: 1 }
    }
  }
]);
```

### 18.4. Do Not Use `numericOrdering` to Fix `price`

Numeric ordering only affects string collation. The proper fix is storing `price` using appropriate numeric BSON types.

---

## 19. Java Sync Driver: Handling BSON Operands Correctly

### 19.1. `ObjectId`

```java
import org.bson.types.ObjectId;
import static com.mongodb.client.model.Filters.eq;

String incomingId = "65b8f9a53a9b43885f4e52c1";

if (!ObjectId.isValid(incomingId)) {
    throw new IllegalArgumentException("Invalid ObjectId");
}

ObjectId id = new ObjectId(incomingId);
Document order = orders.find(eq("_id", id)).first();
```

Use only when `_id` is stored as `ObjectId`. If the collection uses String IDs, keep it as String.

### 19.2. BSON Date

Wrong when the field is Date:

```java
orders.find(Filters.gte(
        "createdAt", "2026-11-01")).first();
```

Right:

```java
import java.time.Instant;
import java.util.Date;

Date threshold = Date.from(
        Instant.parse("2026-11-01T00:00:00Z"));

Document order = orders.find(
        Filters.gte("createdAt", threshold)
).first();
```

### 19.3. Collation with Java Driver

```java
import com.mongodb.client.model.Collation;
import com.mongodb.client.model.CollationStrength;

Collation caseInsensitive = Collation.builder()
        .locale("en")
        .collationStrength(CollationStrength.SECONDARY)
        .build();

Document customer = customers
        .find(Filters.eq("displayName", "alice"))
        .collation(caseInsensitive)
        .first();
```

The index on `displayName` needs a matching collation to accelerate the string lookup. Do not change driver options while ignoring the index catalog.

### 19.4. `explain` with Java Driver

```java
import com.mongodb.ExplainVerbosity;

Document explain = orders.find(
        Filters.and(
                Filters.eq("tenantId", "t05"),
                Filters.eq("status", "PAID")))
        .sort(Sorts.descending("createdAt"))
        .limit(20)
        .explain(ExplainVerbosity.EXECUTION_STATS);

Document stats = explain.get(
        "executionStats", Document.class);

long returned =
        ((Number) stats.get("nReturned")).longValue();
long examined =
        ((Number) stats.get("totalDocsExamined")).longValue();
long keys =
        ((Number) stats.get("totalKeysExamined")).longValue();
```

Check for null/missing fields in real code. Using `Number` avoids depending on whether a numeric field decodes as `Integer` or `Long`.

### 19.5. Spring Data MongoDB

Spring Data mapping may convert `@Id String` into `ObjectId` in certain flows; `@MongoId` and converters clarify the desired representation. Always verify actual stored BSON and query BSON types via integration tests.

For `BigDecimal`, decide between `Decimal128` and String representation per mapping/annotations and migration rules. Never assume changing a Java property type automatically fixes existing documents.

---

## 20. From Slow Logs to Query Shape

### 20.1. Diagnostic Slow-Operation Logs

A MongoDB structured log may record:

```json
{
  "s": "I",
  "c": "COMMAND",
  "msg": "Slow query",
  "attr": {
    "ns": "commerce.orders",
    "planSummary": "COLLSCAN",
    "docsExamined": 500000,
    "keysExamined": 0,
    "durationMillis": 850
  }
}
```

This is an abbreviated example, not an exact log schema.

### 20.2. Database Profiler

`system.profile` stores operation details when enabled with a level/threshold/filter. It incurs CPU/I/O/storage/PII costs; do not leave profiling level 2 running long-term just to catch one slow query.

### 20.3. Driver Metrics

Use `CommandListener` or tracing to measure client-side command duration; correlate with server logs, pool waits, retries, and cursor batches. Do not compare `explain.executionTimeMillis` directly against HTTP p99 while ignoring environment differences.

### 20.4. Choosing Representative Queries

Extract query shapes and field types from sanitized telemetry—never copy raw customer PII into repositories or CI fixtures.

### 20.5. Look Beyond the Single Slowest Query

A query taking 80 ms executed 20,000 times/second can consume far more CPU than a 2-second query run once an hour. Combine duration, frequency, docs/keys examined, and resource metrics.

---

## 21. Lab 1: Missing Index and Sort

**Run only on an isolated lab MongoDB instance.** The `slow_query_lab` database and `orders` collection below should be empty before seeding; never run `dropDatabase()` on shared environments.

### 21.1. Generate Deterministic Data

```javascript
const lab = db.getSiblingDB("slow_query_lab");
const orders = lab.getCollection("orders");
const base = ISODate("2026-01-01T00:00:00Z");
let batch = [];

for (let tenant = 0; tenant < 6; tenant++) {
  const tenantId =
    "t" + String(tenant).padStart(2, "0");

  for (let i = 0; i < 2000; i++) {
    batch.push({
      _id: tenantId + "-" + String(i).padStart(4, "0"),
      tenantId,
      status: i % 4 === 0 ? "PAID" : "PENDING",
      total: i + 100,
      createdAt: new Date(base.getTime() + i * 60000),
      customerId: "C-" + (i % 100)
    });

    if (batch.length === 500) {
      orders.insertMany(batch);
      batch = [];
    }
  }
}

if (batch.length) {
  orders.insertMany(batch);
}

print("total=" + orders.countDocuments({}));
print("t05Paid=" + orders.countDocuments({
  tenantId: "t05", status: "PAID"
}));
```

Expected:

```text
total=12000
t05Paid=500
```

### 21.2. Explain Before Indexing

```javascript
const filter = { tenantId: "t05", status: "PAID" };

const before = orders.find(filter)
  .sort({ createdAt: -1 })
  .limit(20)
  .explain("executionStats");

printjson({
  returned: before.executionStats.nReturned,
  docsExamined: before.executionStats.totalDocsExamined,
  keysExamined: before.executionStats.totalKeysExamined,
  winning: before.queryPlanner.winningPlan
});
```

With no index beyond `_id`, you will likely see `COLLSCAN` and a sort; inspect actual output rather than hardcoding stage paths.

### 21.3. Create Compound Index

```javascript
orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_tenant_status_created" }
);
```

### 21.4. Explain After Indexing

```javascript
const after = orders.find(filter)
  .sort({ createdAt: -1 })
  .limit(20)
  .explain("executionStats");

printjson({
  returned: after.executionStats.nReturned,
  docsExamined: after.executionStats.totalDocsExamined,
  keysExamined: after.executionStats.totalKeysExamined,
  winning: after.queryPlanner.winningPlan
});
```

### 21.5. Verify Correctness

```javascript
const results = orders.find(filter)
  .sort({ createdAt: -1 })
  .limit(20).toArray();

print(results.length);
print(results[0]._id);
```

Expect 20 results; the first record is typically `t05-1996` given the seeded fixture and `createdAt` sort.

### 21.6. Negative Control with Natural Scan

```javascript
const natural = orders.find(filter)
  .sort({ createdAt: -1 })
  .limit(20)
  .hint({ $natural: 1 })
  .explain("executionStats");

printjson({
  docs: natural.executionStats.totalDocsExamined,
  keys: natural.executionStats.totalKeysExamined
});
```

This is a diagnostic lab exercise. Never use a `$natural` hint to "fix" production queries.

---

## 22. Lab 2: Collation Mismatch

### 22.1. Create Collection

```javascript
const lab = db.getSiblingDB("slow_query_lab");
const customers = lab.getCollection("customers");

customers.insertMany([
  { _id: 1, displayName: "Alice" },
  { _id: 2, displayName: "alice" },
  { _id: 3, displayName: "ALICE" },
  { _id: 4, displayName: "Bob" }
]);
```

### 22.2. Create ICU Index

```javascript
customers.createIndex(
  { displayName: 1 },
  {
    name: "idx_name_ci",
    collation: { locale: "en", strength: 2 }
  }
);
```

### 22.3. Without Collation

```javascript
printjson(customers.find({
  displayName: "alice"
}).toArray());

printjson(customers.find({
  displayName: "alice"
}).explain("executionStats"));
```

### 22.4. Matching Collation

```javascript
printjson(customers.find({
  displayName: "alice"
}).collation({
  locale: "en", strength: 2
}).toArray());

printjson(customers.find({
  displayName: "alice"
}).collation({
  locale: "en", strength: 2
}).explain("executionStats"));
```

### 22.5. Interpretation

- Query results differ due to comparison semantics.
- Matching collation makes the ICU index eligible for string comparisons.
- With only four documents, the optimizer may still pick `COLLSCAN`; do not conclude an index is broken from a tiny fixture.
- Seed more synthetic docs if you want to observe plan selection.
- Test strength 1 and 2 on accented values and evaluate correctness before choosing.

---

## 23. Lab 3: BSON Type Mismatch

### 23.1. Create Mixed Data

```javascript
const lab = db.getSiblingDB("slow_query_lab");
const mixed = lab.getCollection("mixed_types");

mixed.insertMany([
  {
    _id: ObjectId("65b8f9a53a9b43885f4e52c1"),
    createdAt: ISODate("2026-11-01T00:00:00Z"),
    price: NumberDecimal("150.00")
  },
  {
    _id: "65b8f9a53a9b43885f4e52c2",
    createdAt: "2026-11-02T00:00:00Z",
    price: "150"
  },
  {
    _id: "numeric-01",
    createdAt: ISODate("2026-11-03T00:00:00Z"),
    price: NumberInt(200)
  }
]);
```

### 23.2. Classify Types

```javascript
mixed.aggregate([
  {
    $project: {
      idType: { $type: "$_id" },
      dateType: { $type: "$createdAt" },
      priceType: { $type: "$price" }
    }
  }
]);
```

### 23.3. Compare String and ObjectId

```javascript
printjson(mixed.findOne({
  _id: "65b8f9a53a9b43885f4e52c1"
}));

printjson(mixed.findOne({
  _id: ObjectId("65b8f9a53a9b43885f4e52c1")
}));
```

### 23.4. Date Range

```javascript
mixed.find({
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z")
  }
}).toArray();
```

### 23.5. Numeric Range

```javascript
mixed.find({
  price: { $gte: 100 }
}).toArray();
```

Observe the difference between numeric BSON values and String `price`; explain why an index alone cannot fix it.

---

## 24. Migrating from Mixed Types to a Consistent Schema

### 24.1. Do Not Run Blanket Conversions Immediately

An update pipeline converting every field to Date can fail on malformed strings, generate heavy write load, or impact replication.

### 24.2. Audit Before Migrating

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: { $type: "$createdAt" },
      count: { $sum: 1 }
    }
  }
]);
```

### 24.3. Check Convertibility

```javascript
db.orders.aggregate([
  {
    $project: {
      oldType: { $type: "$createdAt" },
      parsedDate: {
        $convert: {
          input: "$createdAt",
          to: "date",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
```

Do not overwrite production fields with `null` when conversion fails.

### 24.4. Safe Migration

1. Verify source formats and timezones.
2. Back up/snapshot per policy.
3. Run on staging with representative data.
4. Select only records with the wrong type.
5. Parse/validate; record conversion failures.
6. Write in batches with idempotent checkpoints.
7. Monitor CPU, disk, oplog window, and replication lag.
8. Verify counts and random samples.
9. Switch application queries to typed filters.
10. Add schema validation to prevent recurrence.

### 24.5. MongoDB JSON Schema

Example checking BSON Date:

```javascript
db.runCommand({
  collMod: "orders",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      properties: {
        createdAt: { bsonType: "date" }
      }
    }
  }
});
```

This is a **lab skeleton**. In production, merge with the existing validator, define required fields/`validationLevel`, and ensure writer compatibility. Validation does not automatically fix existing documents.

### 24.6. Without Fixing Data, Indexes Alone Will Not Solve the Root Cause

If queries always filter by Date yet 10% of documents hold Strings, a Date index cannot produce complete results. Schema migration and fixing writer sources are required.

---

## 25. Aggregations and Computed Sorts

### 25.1. Early `$match`

```javascript
db.orders.aggregate([
  { $match: { tenantId: "t05", status: "PAID" } },
  { $sort: { createdAt: -1 } },
  { $limit: 20 },
  { $project: { customerId: 1, total: 1, createdAt: 1 } }
]);
```

Preserves semantics while allowing the optimizer to leverage collection indexes where appropriate.

### 25.2. `$project` Can Break Index Access Paths

If a projection drops a field before sorting or introduces a newly computed field, the sorter may no longer use the same index order. Inspect the optimized pipeline rather than only looking at the original stage order.

### 25.3. `$group` Creates New Fields

```javascript
db.orders.aggregate([
  { $group: { _id: "$tenantId", revenue: { $sum: "$total" } } },
  { $sort: { revenue: -1 } }
]);
```

An index on raw `total` does not provide ordering for computed `revenue`. You may need a materialized summary collection, caching, or batch reports.

### 25.4. `$lookup`

A foreign collection missing an index on the join key can slow down the aggregation even if the base collection is well-indexed. Inspect `$lookup` explain output, `indexesUsed`, documents examined, and fan-out where supported by your server version.

### 25.5. Aggregation Explain Output Differs from `find`

Counters may appear in nested stages or sharded sections. Do not assume every pipeline exposes `executionStats.totalDocsExamined` at the same JSON path as `find`.

---

## 26. Diagnostic Hints: Comparing Access Paths

### 26.1. Use in a Safe Environment

```javascript
const filter = {
  tenantId: "t05",
  status: "PAID"
};

const noHint = db.orders.find(filter)
  .sort({ createdAt: -1 }).limit(20)
  .explain("executionStats");

const withHint = db.orders.find(filter)
  .sort({ createdAt: -1 }).limit(20)
  .hint("idx_tenant_status_created")
  .explain("executionStats");

printjson({
  plannerDocs: noHint.executionStats.totalDocsExamined,
  hintedDocs: withHint.executionStats.totalDocsExamined
});
```

### 26.2. Do Not Use `hint` to Mask a Bad Plan

Hints help prove a candidate index is beneficial, yet hardcoding hints in production can:

- Break if the index is dropped.
- Miss better indexes after upgrades.
- Become wrong when data distribution shifts.
- Regress other query variants.

### 26.3. Compare Correctness Too

A partial index combined with mismatched query conditions can error or change result semantics. Do not compare only examined counters.

---

## 27. On Replica Sets and Sharded Clusters

### 27.1. Replica Sets

Queries may run on the primary or a secondary. Members vary in cache warmth, load, replication lag, and read preference. Check where the request actually executed.

### 27.2. `mongos` Fan-Out

```text
Java app
   │
   ▼
mongos
   ├─ shard A: IXSCAN
   ├─ shard B: IXSCAN
   └─ shard C: IXSCAN
        │
        ▼
   merge/sort
```

A query missing the shard-key predicate triggers scatter-gather, even when each shard uses an index efficiently.

### 27.3. Per-Shard Explain

Inspect per-shard docs/keys examined and routing. Never sum parallel shard durations into a single HTTP latency figure.

### 27.4. Collation and Sharding

Sharded indexes, unique indexes, and collations carry restrictions depending on server version/topology. Never change collection default collation or shard keys arbitrarily to fix one slow query.

### 27.5. Multi-Member Index Rollouts

Index builds consume CPU, disk, cache, replication bandwidth, and workload concurrency. Plan a change window, monitoring, and rollback.

---

## 28. Production Slow-Query Incident Runbook

### Step 1 — Determine Impact

Record affected APIs, start time, p95/p99/error rates, cluster/replica/shard, and recent deploys/index/schema changes.

### Step 2 — Capture the Real Query

Collect filter, projection, sort, collation, limit/skip, hint, BSON operand types, and driver/server versions; sanitize PII.

### Step 3 — Verify Correctness

Are documents that should match missing from results? Do fields have mixed types? Did collation alter semantics?

### Step 4 — Inspect the Index Catalog

```javascript
db.orders.getIndexes();
```

Check key order, hidden/partial/sparse flags, collation, uniqueness, and migration state.

### Step 5 — Controlled Explain

```javascript
db.orders.find(filter)
  .sort(sort)
  .limit(20)
  .explain("executionStats");
```

Never run `explain("executionStats")` on a heavy unbounded query during peak traffic without assessing impact.

### Step 6 — Classify Root Cause

- Missing/wrong index.
- Wide index bounds.
- Blocking sort/spill.
- Collation mismatch.
- BSON type inconsistency.
- Deep pagination/regex/expressions.
- Query plan cache/topology.
- Non-query bottleneck.

### Step 7 — Test the Minimal Fix in Lab/Staging

Measure result correctness, docs/keys examined, and index catalog before and after. Benchmark representative workloads separately to verify latency.

### Step 8 — Production Rollout

Assign an owner, approval, resource budget, and rollback plan. Index builds/schema backfills can affect writes, disk, and replication lag. Do not immediately drop an index still serving other queries.

### Step 9 — Verify

Compare latency distribution, throughput, query work, errors, CPU, I/O, cache, and replication. Test case/accent/timezone/type correctness.

### Step 10 — Postmortem

Document the specific root cause and preventive actions: migrations, schema validation, index tests, query reviews, or observability.

---

## 29. Quick Troubleshooting Reference Table

| Symptom | Check first | Possible fix |
|---|---|---|
| `COLLSCAN` and high `docsExamined` | Index existence/shape | Suitable compound index |
| `IXSCAN` yet high `keysExamined` | Bounds/prefix/selectivity | Fix index key order/query |
| Blocking `SORT` | Equality prefix/direction | Index filter+sort, limit |
| `usedDisk` | Pipeline cardinality/memory | Index, `$match`, top-N, batch |
| Slow deep-skip sort | Skip depth | Keyset pagination |
| Case-insensitive index unused | Query/index collation | Align collation |
| Slow `$regex /i` | Regex semantics | Normalized key/search solution |
| String date misses Date filter | `$type` | Data migration + validation |
| String ID misses `ObjectId` | BSON type | Parse `ObjectId` at boundary |
| String `price` sorts wrong | `$type` | Numeric BSON representation |
| Partial index unused | Predicate filter | Match partial conditions |
| Hidden index | Catalog `hidden` flag | Review state/rollout |
| Aggregation computed sort | `$group`/`$project` stages | Materialize/report design |
| Explain differs from production logs | Cache/version/data/node | Correlate telemetry |
| New index slows down writes | Index overhead | Audit index portfolio |

---

## 30. Exercise A — Missing Compound Index

A collection has one million orders with only `{status:1}` and `{createdAt:-1}` indexes. A query filters by tenant/status, sorts by `createdAt` descending, and limits to 20.

Tasks:

1. Explain why two single-field indexes are insufficient.
2. Propose a compound index.
3. Write the `explain` call.
4. Define docs/keys budgets for an appropriate fixture.
5. Analyze write/storage costs of the new index.

## 31. Exercise B — `IXSCAN` Still Slow

Explain shows:

```text
nReturned=10
keysExamined=650000
docsExamined=300000
winning plan contains IXSCAN
```

Explain why "having an index" does not mean "query is optimal," analyze `indexBounds`, and propose improvements.

## 32. Exercise C — Sort Direction

Index:

```javascript
{ score: -1, createdAt: 1 }
```

Compare sorts:

```javascript
{ score: -1, createdAt: 1 }
{ score: 1, createdAt: -1 }
{ score: -1, createdAt: -1 }
```

Which patterns can be served by forward/reverse index scans? Which pattern may require an extra sort?

## 33. Exercise D — Equality Prefix

Index:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

Compare queries:

```javascript
{ tenantId: "t05", status: "PAID" }
{ tenantId: "t05" }
{ status: "PAID" }
```

in the context of sorting by `createdAt`. Explain why the equality prefix affects sort/index access.

## 34. Exercise E — Collation

Index:

```javascript
{ username: 1 }
// collation: { locale: "en", strength: 2 }
```

Compare a `simple` query and a `strength: 2` collation query, case-insensitive results, unique index risks, and why `regex /i` does not solve it automatically.

## 35. Exercise F — Date vs. String

Data:

```javascript
{ createdAt: ISODate("2026-11-01T00:00:00Z") }
{ createdAt: "2026-11-01T00:00:00Z" }
```

Write a Date range query, predict its output, use `$type`, and propose migration and validation.

## 36. Exercise G — `ObjectId` and Java Driver

Java:

```java
collection.find(Filters.eq(
  "_id", "65b8f9a53a9b43885f4e52c1")).first();
```

The collection stores `ObjectId`. Explain the mismatch, fix the type at the boundary, handle invalid IDs, and avoid `$expr/$toString` scans.

## 37. Exercise H — Numeric Fields

Data:

```javascript
{ price: NumberInt(150) }
{ price: NumberDecimal("150.00") }
{ price: "150" }
```

Which group does `price:{$gte:100}` match? Why doesn't `numericOrdering` replace a numeric schema?

## 38. Exercise I — Sort Spill

Pipeline:

```javascript
[
  { $match: { status: "PAID" } },
  { $sort: { createdAt: -1 } }
]
```

Logs show `usedDisk:true`. Propose how to check indexes, selective filters, limits, and memory settings. Explain why enabling `allowDiskUse` is not the optimal fix.

## 39. Exercise J — Incident Runbook

API p99 spiked after a CSV migration; 15% of `createdAt` values turned into Strings, and queries started using `$expr/$toDate`. Write:

1. How to verify root cause.
2. Short-term load-relief measures.
3. Idempotent migration with rollback.
4. Schema validation.
5. Before/after explain.
6. Benchmark and regression tests.

## 40. Exercise K — Sharding

`mongos` scatters across 5 shards; each shard executes `IXSCAN`, yet router merge/sort is slow. Outline how to inspect shard targeting, per-shard indexes, query collation, and routing. Why shouldn't shard durations be summed into HTTP latency?

## 41. Exercise L — Vietnamese Name Search

Searching names "Nguyễn", "NGUYỄN", "nguyen":

1. Define case/accent semantics.
2. Design index/collation or normalized keys.
3. Test Unicode correctness.
4. Check regex prefix/search performance.
5. Ensure unique username behavior is not altered unintentionally.

---

## 42. Pre-Closure Incident Checklist

### 42.1. Evidence

- [ ] Captured actual query shape, including collation and operand types.
- [ ] Captured index catalog.
- [ ] Verified result correctness.
- [ ] Captured before/after explain.
- [ ] Recorded `docsExamined`/`keysExamined`/`nReturned`.
- [ ] Captured latency/throughput/resource metrics.
- [ ] Recorded topology/versions and query member context.

### 42.2. Correctness

- [ ] `ObjectId`/String IDs match schema.
- [ ] BSON Date and timezone policies are accurate.
- [ ] Numeric types are consistent.
- [ ] Collation case/accent rules are accurate.
- [ ] Unique constraints remain unaltered unintentionally.
- [ ] Sort/pagination ordering is stable.
- [ ] Legacy data handled.

### 42.3. Performance

- [ ] Index matches equality/sort/range.
- [ ] Index bounds are sufficiently narrow.
- [ ] Blocking sort/spills resolved or justified.
- [ ] Deep skip/regex/expressions addressed.
- [ ] Docs/keys scan budgets are reasonable.
- [ ] p95/p99 improved across multiple samples.
- [ ] New index does not push write workload over budget.

### 42.4. Operations

- [ ] Owner and rollback plan assigned.
- [ ] No indexes dropped on shared databases just to test.
- [ ] Migration includes backup/checkpoint/validation.
- [ ] Raw PII/secrets excluded from logs.
- [ ] Integration tests added for types/collation/indexes.
- [ ] Post-rollout monitoring continues.
- [ ] Postmortem documents exact root cause.

---

## 43. Official References

- [MongoDB — Interpret Explain Plan Results](https://www.mongodb.com/docs/manual/tutorial/analyze-query-plan/)
- [MongoDB — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB — Query Plans and Plan Cache](https://www.mongodb.com/docs/manual/core/query-plans/)
- [MongoDB — Use Indexes to Sort Query Results](https://www.mongodb.com/docs/manual/tutorial/sort-results-with-indexes/)
- [MongoDB — ESR Equality, Sort, Range](https://www.mongodb.com/docs/manual/tutorial/equality-sort-range-guideline/)
- [MongoDB — Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/)
- [MongoDB — Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/)
- [MongoDB — Hidden Indexes](https://www.mongodb.com/docs/manual/core/index-hidden/)
- [MongoDB — Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/)
- [MongoDB — Collation](https://www.mongodb.com/docs/manual/reference/collation/)
- [MongoDB — Case-Insensitive Indexes](https://www.mongodb.com/docs/manual/core/index-case-insensitive/)
- [MongoDB — BSON Comparison/Sort Order](https://www.mongodb.com/docs/manual/reference/bson-type-comparison-order/)
- [MongoDB — Type Bracketing in Query Predicates](https://www.mongodb.com/docs/manual/reference/mql/query-predicates/type-bracketing/)
- [MongoDB — $type Aggregation](https://www.mongodb.com/docs/manual/reference/operator/aggregation/type/)
- [MongoDB — $convert](https://www.mongodb.com/docs/manual/reference/operator/aggregation/convert/)
- [MongoDB — $toDate](https://www.mongodb.com/docs/manual/reference/operator/aggregation/toDate/)
- [MongoDB — Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/)
- [MongoDB — $sort](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sort/)
- [MongoDB — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB Java Sync Driver — Query Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/)
- [MongoDB Java Sync Driver — Collation](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/limit-sort/)
- [MongoDB Java Sync Driver — Monitoring](https://www.mongodb.com/docs/drivers/java/sync/current/monitoring-and-logging/)

> **Version note:** MongoDB Classic/SBE/EXPRESS query plans, sort spill limits, collation behaviors, index visibility, and aggregation explain outputs may differ across server releases. Cross-check against the exact MongoDB Server, Java Driver, and topology in use. Commands creating data/indexes/validators are strictly for labs or deployments with change approval.

---

## 44. Summary

1. **Missing/wrong indexes** cause MongoDB to examine excessive documents or index entries. Inspect the index catalog, key order, prefixes, selectivity, and `explain("executionStats")`.
2. **Slow sorts** may stem from indexes lacking the right order, mismatched sort directions, missing equality prefixes, deep pagination, or sorting on computed fields. `allowDiskUse` is not an index optimization.
3. **Collation mismatches** prevent an ICU index from supporting string comparisons in a query using a different collation. Case-insensitive `$regex` does not automatically benefit from a case-insensitive collation index.
4. **BSON types** are part of query correctness: `ObjectId` differs from String, Date differs from String, and numeric BSON types differ from numeric strings. Range predicates use type bracketing, while BSON numeric types compare together as a group.
5. **Explain is not a production latency benchmark.** Use docs/keys examined, index/plan metadata, and correctness to diagnose logical work; use APM/benchmarks to validate SLOs.
6. **Schema migration and validation** are usually the sustainable fix for type mismatches rather than query-time casts that defeat indexes.
7. **Safe rollouts** require a lab, before/after evidence, index build resource budgets, regression tests, monitoring, and rollback plans.

**Operational principle:** Investigate along the chain **query shape → BSON types and collation → index catalog → explain work → verify hypothesis → test → roll out and re-measure**. Identifying the exact root cause improves performance without sacrificing data correctness.
