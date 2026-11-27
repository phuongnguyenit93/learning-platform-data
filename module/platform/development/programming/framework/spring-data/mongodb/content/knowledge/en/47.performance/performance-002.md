# Explain and executionStats for Inspecting Query Plans

When a MongoDB query runs slowly in a **Spring Data MongoDB** application, timing `MongoTemplate` or repository calls only reveals the symptom. To find out whether the query is scanning the entire collection, which index it uses, whether it must sort in memory, or how many documents it reads to return a few results, you need to inspect the **query execution plan** using `explain()`.

`explain` helps analyze `find` queries, `aggregate` pipelines, and other operations supported by MongoDB. In particular, **`executionStats`** mode adds execution metrics to verify whether the chosen plan actually performs efficiently given the filter conditions, data, and existing indexes. This is a core skill when designing queries, creating indexes, and diagnosing performance in the Spring Data MongoDB module.

## 1. What does the query optimizer decide?

When receiving a query, MongoDB must choose how to locate and process data. It can:

- Scan the entire collection (`COLLSCAN`) and filter each document.
- Scan an index (`IXSCAN`), possibly retrieving the full documents via `FETCH`.
- Combine filtering, limiting (`LIMIT`), skipping (`SKIP`), projecting (`PROJECTION`), and sorting (`SORT`) steps.
- Handle query branches or pipelines, such as `$or`, `$lookup`, `$group`, or queries across a sharded cluster.

The chosen set of steps is called the **winning plan**. Having an index on a collection **does not guarantee** every query will use it; the choice depends on filter conditions, sort order, selectivity, data types, collation, statistics, and execution options of the MongoDB version.

Example `orders` collection documents:

~~~javascript
{
  _id: ObjectId("6650ef9c2d5b40641f000001"),
  tenantId: "T01",
  status: "PAID",
  createdAt: ISODate("2026-09-20T10:30:00Z"),
  totalMinor: 250000,
  customerId: "C104"
}
~~~

The application needs the **20 newest paid orders** for tenant `T01`, created since the start of September 2026. If the collection has millions of orders, simply adding `limit(20)` does not guarantee the query will be fast: MongoDB might still inspect many documents or sort many results before taking 20 records.

## 2. Three `explain` verbosity modes to distinguish

MongoDB provides three commonly used levels of detail:

| Verbosity | Key information | When to use |
| --- | --- | --- |
| `queryPlanner` | Selected plan, candidate plans, and related index info; generally does not execute the full query for runtime stats | See how MongoDB intends to execute the query |
| `executionStats` | Includes `queryPlanner` plus execution metrics for the winning plan, such as `nReturned`, `totalKeysExamined`, `totalDocsExamined`, `executionTimeMillis` | Measure the actual amount of work performed by the plan |
| `allPlansExecution` | Adds information from trial evaluations of candidate plans, within what MongoDB captures | Investigate why one plan was chosen over another |

In `mongosh`, you can inspect the query directly:

~~~javascript
const filter = {
  tenantId: "T01",
  status: "PAID",
  createdAt: { $gte: ISODate("2026-09-01T00:00:00Z") }
};

db.orders.find(filter)
  .sort({ createdAt: -1 })
  .limit(20)
  .explain("queryPlanner");

db.orders.find(filter)
  .sort({ createdAt: -1 })
  .limit(20)
  .explain("executionStats");

db.orders.find(filter)
  .sort({ createdAt: -1 })
  .limit(20)
  .explain("allPlansExecution");
~~~

`explain` does not return the list of orders like a normal `find()`; it returns a plan explanation document. With `executionStats`, MongoDB performs the work needed to gather statistics, so control its impact when running on large datasets or in production.

> **Measurement note:** `explain` does not use the existing plan cache the way a normal query does and does not add plan selections to the cache. The time reported in `explain` is not the end-to-end application response time: it does not fully capture network, Spring Data object mapping, serialization, or downstream processing time. Use `explain` to understand the plan and work done; use real latency measurements to verify application performance.

## 3. Most important fields in the output

`explain` output contains many fields and can vary across MongoDB versions, classic execution engine, slot-based execution engine (SBE), aggregation structures, and sharded clusters. Do not write performance checks relying solely on a fixed JSON path inside `winningPlan`.

| Field / component | Meaning | Interpretation |
| --- | --- | --- |
| `queryPlanner.winningPlan` | Plan chosen by MongoDB | Check stage chain, indexName, scan direction, `indexBounds` |
| `queryPlanner.rejectedPlans` | Candidate plans not selected, if present | Helps understand index competition; does not prove every option was tried |
| `executionStats.nReturned` | Number of result documents returned by the executed plan | Useful denominator for comparing scan volume, considering `limit` and selectivity |
| `executionStats.totalKeysExamined` | Number of index entries/keys examined | Unusually high values can indicate overly wide index scan bounds |
| `executionStats.totalDocsExamined` | Number of document examinations | If much higher than results, filtering may occur after reading many documents |
| `executionStats.executionTimeMillis` | Estimated execution time per MongoDB's measurement | For comparison under equivalent test conditions, not representative of API latency |
| `executionStats.executionStages` | Per-stage metrics | Locate stages causing heavy reads, scans, or sorts |
| `indexName`, `indexBounds` | Index used and index scan range | Verify whether filter predicates narrow the scan range as intended |

`totalDocsExamined` counts document examinations, **not necessarily unique documents**. `totalKeysExamined` is also not the number of returned results. Both metrics must be read alongside `nReturned`, filter predicates, and result limits.

An **illustrative abbreviated** output after adding a suitable index might look like:

~~~json
{
  "queryPlanner": {
    "winningPlan": {
      "stage": "LIMIT",
      "inputStage": {
        "stage": "FETCH",
        "inputStage": {
          "stage": "IXSCAN",
          "indexName": "idx_orders_tenant_status_created",
          "direction": "forward"
        }
      }
    }
  },
  "executionStats": {
    "nReturned": 20,
    "executionTimeMillis": 4,
    "totalKeysExamined": 24,
    "totalDocsExamined": 20
  }
}
~~~

Values `4`, `24`, and `20` are **hypothetical numbers for learning how to read a plan**, not benchmarks or guaranteed output of any MongoDB version. On an SBE-enabled server, `winningPlan` may appear under `queryPlanner.winningPlan.queryPlan` accompanied by `slotBasedPlan`; sharded or aggregation cases can have different nested structures.

In this example, MongoDB uses `IXSCAN` on the suitable index, reads only a couple dozen keys, fetches 20 documents, and returns 20 results. Seeing `FETCH` is normal when the query needs fields not fully present in the index. Not every good query has `totalDocsExamined = 0`.

## 4. Reading common stages

| Stage / indicator | Meaning | Investigation questions |
| --- | --- | --- |
| `COLLSCAN` | Scans documents in the collection | Can an index satisfy the filter, or is a full collection scan actually cheaper? |
| `IXSCAN` | Traverses entries in an index | Are `indexBounds` narrow? Is `keysExamined` much larger than `nReturned`? |
| `FETCH` | Retrieves actual documents to evaluate/read additional data | Are many documents filtered out after FETCH? Is a covered query needed? |
| `SORT` | Sorts outside the traversed index order | Can a compound index support the sort? How large is the set being sorted? |
| `LIMIT` / `SKIP` | Caps results or skips a number of results | Does deep `skip` pagination force MongoDB to walk too many keys? |
| `PROJECTION_COVERED` or equivalent | Returned data is satisfied entirely from the index per the engine used | Can `FETCH` be eliminated to keep `totalDocsExamined = 0`? |
| `OR` / branch merge stages | Combines results from multiple branches | Does each branch have an appropriate index? |
| `SHARD_MERGE` and shard-related stages | Aggregates results from shards | Is the query targeted to specific shards or fanning out? |

A `SORT` stage **is not always an error**: sorting a small set can be cheaper than maintaining another large index. `COLLSCAN` can also be reasonable for small collections or queries returning most of the collection. What matters is **the amount of work and latency relative to actual requirements**, not blindly eliminating every stage name considered bad.

### `indexBounds` and compound indexes

With index `{ tenantId: 1, status: 1, createdAt: -1 }`, the example query has two equality predicates (`tenantId`, `status`) and a date range (`createdAt`). MongoDB can bound the index range by tenant, status, and date interval, while reading in descending `createdAt` order without a separate sort.

If the index were only `{ tenantId: 1 }`, MongoDB might still read many orders for the tenant, filter `status` and `createdAt`, and sort the remainder. Seeing `IXSCAN` alone is **not enough** to conclude an index is good; inspect the scan bounds and actual counters.

## 5. Testing before and after adding an index

Run the actual query under identical conditions: same data, filter, sort, limit, projection, collation, and environment. Start by checking existing indexes:

~~~javascript
db.orders.getIndexes();
~~~

Then run the query and record `nReturned`, `totalKeysExamined`, `totalDocsExamined`, `executionTimeMillis`, and winning plan. If no suitable index exists, consider creating a compound index:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_orders_tenant_status_created" }
);
~~~

Re-run `explain("executionStats")` with the exact same query. Compare an **illustrative synthetic** example:

| Metric | Before (missing suitable index) | After (compound index) |
| --- | ---: | ---: |
| Main plan | `COLLSCAN` + `SORT` | `IXSCAN` + `FETCH` |
| `nReturned` | 20 | 20 |
| `totalKeysExamined` | 0 | 24 |
| `totalDocsExamined` | 120,000 | 20 |
| `executionTimeMillis` | 165 ms | 4 ms |

In this illustrative scenario, the index narrows the documents read and provides sort order. However, **do not treat synthetic numbers as mandatory targets**. With real queries, dataset, value distribution, cache, and system load determine the actual improvement. A compound index can speed up read queries but also increases storage footprint, write cost, and index build time.

### Choosing index field order

For many queries combining equality, sort, and range, a guiding rule is **Equality → Sort → Range (ESR)**. The example above aligns with equality on `tenantId`, `status` and sort/range on `createdAt`.

However, ESR is not an absolute formula. Highly selective range conditions, other queries on the same collection, sort direction, partial/multikey indexes, collation, and write constraints can make another order better. Always verify with execution plans and representative data. With partial indexes, the query filter must satisfy the required condition for the optimizer to use that index; sparse and multikey indexes also have their own constraints.

## 6. Covered queries and document read cost

If a query only filters, sorts, and returns fields already contained in the index, MongoDB can return results without reading the original documents. This is a **covered query**. With index `{ tenantId: 1, status: 1, createdAt: -1 }`, try:

~~~javascript
db.orders.find(
  { tenantId: "T01", status: "PAID" },
  { _id: 0, tenantId: 1, status: 1, createdAt: 1 }
).sort({ createdAt: -1 })
 .limit(20)
 .explain("executionStats");
~~~

If conditions support a covered query and the plan uses this index, `totalDocsExamined` can be `0`. Specifying `{ _id: 0 }` is important when `_id` is not in the index, because `find`'s default projection includes `_id`.

Do not force every query to be a covered query: adding too many fields bloats the index and increases write cost. Only optimize this way when metrics show document fetching is a bottleneck and the query shape is stable.

## 7. Running `explain` from a Spring Data MongoDB application

In real systems, queries often start with `Criteria`, `Query`, `MongoTemplate`, repositories, query derivation, or the aggregation API. To reproduce the exact plan, inspect **the BSON sent to MongoDB**, including field mapping (`@Field`), BSON types, projection, sort, limit, skip, collation, and hints (if any).

Application code example using `MongoTemplate`:

~~~java
import java.time.Instant;
import java.util.Date;
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class OrderReadService {
    private final MongoTemplate template;

    public OrderReadService(MongoTemplate template) {
        this.template = template;
    }

    public List<Order> newestPaidOrders(String tenantId, Instant since) {
        Query query = new Query()
            .addCriteria(Criteria.where("tenantId").is(tenantId)
                .and("status").is("PAID")
                .and("createdAt").gte(Date.from(since)))
            .with(Sort.by(Sort.Direction.DESC, "createdAt"))
            .limit(20);

        return template.find(query, Order.class, "orders");
    }
}
~~~

Here `Order` is the application's `@Document` entity; Java fields must map to the corresponding MongoDB fields. The snippet assumes `tenantId`, `status`, and `createdAt` share the same names in Java and BSON, with `createdAt` stored as a BSON Date.

To view `executionStats` over the same application connection, you can use the **MongoDB Java Driver** via the `MongoTemplate.execute` callback:

~~~java
import java.time.Instant;
import java.util.Date;
import com.mongodb.ExplainVerbosity;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;

public class OrderExplainService {
    private final MongoTemplate template;

    public OrderExplainService(MongoTemplate template) {
        this.template = template;
    }

    public Document explainNewestPaidOrders(String tenantId, Instant since) {
        return template.execute("orders", collection ->
            collection.find(Filters.and(
                    Filters.eq("tenantId", tenantId),
                    Filters.eq("status", "PAID"),
                    Filters.gte("createdAt", Date.from(since))
                ))
                .sort(Sorts.descending("createdAt"))
                .limit(20)
                .explain(ExplainVerbosity.EXECUTION_STATS)
        );
    }
}
~~~

`MongoTemplate.execute` opens collection access through the driver; this example builds the BSON filter **manually**, so it does not automatically apply `@Field` mappings from the entity like `MongoTemplate.find`. If the application uses `@Field("created_at")`, custom converters, `@Query`, soft-delete filters, or collations, transfer those exact details to the explain query. Explaining a query different from production leads to wrong conclusions even if the output looks plausible.

Only invoke such diagnostics from internal tools, test environments, or controlled admin routes. Avoid exposing a public API that runs arbitrary `executionStats` on unbounded inputs, as analyzing can consume as many resources as a heavy query.

### Analyzing repository-derived queries

When using method derivation such as `findTop20ByTenantIdAndStatusAndCreatedAtAfterOrderByCreatedAtDesc`, verify the actual command sent by the driver rather than guessing from the method name. Enable appropriate logging in test environments or use driver command observation to capture filter, projection, sort, limit, collation, and read preference; then run that **exact query shape** in `mongosh` or a driver callback. Do not log sensitive query values in production.

## 8. Viewing `explain` for aggregation pipelines

With Spring Data MongoDB, `Aggregation` and `MongoTemplate.aggregate` can build multi-stage pipelines. `explain` helps evaluate whether `$match` was pushed early, whether `$sort` can use an index, and where `$group`/`$lookup` spend resources.

Example in `mongosh`:

~~~javascript
db.orders.explain("executionStats").aggregate([
  { $match: { tenantId: "T01", status: "PAID" } },
  { $sort: { createdAt: -1 } },
  { $limit: 20 },
  { $project: { _id: 0, customerId: 1, totalMinor: 1, createdAt: 1 } }
]);
~~~

MongoDB may optimize or reorder stages according to optimizer rules, so the execution plan **does not necessarily mirror the exact order of stages you wrote**. When `$match` and `$sort` are pushed down to the indexed query portion, explain results may appear in `queryPlanner`, `$cursor`, execution stats, or shard/SBE-specific sections depending on the version.

For aggregations, pay particular attention to the number of documents flowing through each stage, `$group` and `$lookup` operations, memory usage, disk spill (when reported), and result limits. `executionStats` of a simple `find` cannot represent an entire pipeline if the main cost lies in downstream aggregation stages.

## 9. Situations where the plan differs from expectations

### An index exists, yet MongoDB still chooses `COLLSCAN`

This can be reasonable when the collection is small, the query returns most of the data, or the index does not support the filter/sort well. Check `getIndexes()`, actual conditions, `indexBounds`, collation, data types, and selectivity. Test with `hint()` **only for comparison in an appropriate environment** and compare statistics; do not reflexively push `hint` to production whenever the planner skips an index.

### `IXSCAN` appears, yet `totalKeysExamined` remains very large

An index might only bound the first field and scan most keys for a tenant, or range and sort fields might not match the index order. Inspect `indexBounds` and post-`FETCH` filters, and review compound index field ordering and the workload queries it must serve.

### `SORT` appears despite creating an index

The index might not support the sort for that specific query shape—for example, an incompatible range condition before the sort field, mismatched sort direction, different collation, or multikey constraints limiting sort usage. Check how many records `SORT` processes and its actual cost before adding another index.

### Low `nReturned`, high scan volume

Rare-match queries may scan many keys before finding a few matching documents. Deep pagination with `skip(100000)` can also walk many results just to discard them. If the UI paginates in a fixed order, consider **keyset pagination** (e.g., on `createdAt` plus `_id` as a tie-breaker) with a matching compound index.

### Data type or mapping mismatches make indexes ineffective

For instance, some documents store `createdAt` as a BSON Date while others store a string; a query using `Date` does not match strings. Likewise, Java `@Field("tenant_id")` produces a different physical field name than `"tenantId"` used in a raw driver callback. Verify stored data and mappings before concluding an index is broken.

### Plan looks good on dev but is slow in production

Dev may have little data, different `status` distribution, warm cache, low concurrency, or no sharding. In production, index builds, replication lag, write traffic, shard targeting, and resource contention can dominate latency. Measure on representative data and combine application metrics, MongoDB profiler/slow query logs, and properly configured monitoring.

## 10. Diagnostic and post-optimization verification workflow

An effective sequential workflow:

1. **Pick the right slow query:** capture the actual query shape from the Spring Data MongoDB application, noting the endpoint, call rate, p50/p95/p99, timeouts, and data volume.
2. **Reproduce conditions:** preserve filter, sort, projection, limit, skip, collation, data types, read preference, and a sufficiently representative dataset.
3. **Read `queryPlanner`:** identify winning plan, indexName, stages, and `indexBounds`; verify the query has the expected structure.
4. **Read `executionStats`:** record `nReturned`, `totalKeysExamined`, `totalDocsExamined`, `executionTimeMillis`, and execution stages. Pinpoint the specific bottleneck such as wide scans, heavy `FETCH` filtering, or large sorts.
5. **Test one hypothesis-driven change:** add/adjust an index, tune projection, move `$match` earlier, change pagination, or fix schema/mapping.
6. **Re-run and compare:** use equivalent conditions, run multiple times as appropriate, account for cache and load variance; never rely on a single run.
7. **Measure at the application layer:** verify p95/p99 latency, CPU, I/O, connection count, cache behavior, and the impact of any new index on inserts/updates/deletes.
8. **Deploy and monitor:** build indexes per operational rollout plans, monitor slow queries, write load, index size, and post-release performance; be ready to adjust if results deviate.

### Optimization record template

| Item | Before optimization | After optimization | Notes |
| --- | --- | --- | --- |
| Query shape and parameters | Record | Keep equivalent | Same filter/sort/limit/collation |
| Winning plan | `COLLSCAN`, `SORT`... | `IXSCAN`, `FETCH`... | Record actual index and stages |
| `nReturned` | ... | ... | Ensure result parity |
| `totalKeysExamined` | ... | ... | Compare index scan range |
| `totalDocsExamined` | ... | ... | Compare documents read |
| `executionTimeMillis` | ... | ... | Time per explain, reference only |
| Spring Data operation p95 | ... | ... | Observed via app instrumentation |
| Write impact / index size | ... | ... | Avoid excessive trade-offs for one query |

## 11. Practical takeaways

`queryPlanner` shows **which plan MongoDB intends to use to execute the query**; `executionStats` adds **how many keys and documents that plan examined and how many results it returned**. An `IXSCAN` is not automatically good, a `COLLSCAN` is not automatically bad, and a few milliseconds reported in `explain` do not replace real application latency.

With Spring Data MongoDB, start from the exact filter/sort/projection sent by `MongoTemplate` or repository to MongoDB, inspect the plan, locate where the cost sits, and test index or query changes with a clear hypothesis. **Reading `explain` alongside `executionStats`, then verifying with application metrics** is the grounded way to make optimization decisions and avoid redundant indexes.
