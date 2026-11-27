# Hidden Indexes and Testing Impact Before Dropping Indexes in MongoDB

Indexes help MongoDB locate documents, filter, sort, and execute many queries efficiently, yet each index also consumes disk space, cache memory, and maintenance overhead whenever data changes. When a collection accumulates too many indexes, engineering teams often want to remove rarely used ones to trim operational costs.

The challenge is that **dropping an index is a risky change**: a rare yet critical query might rely on that index. Once dropped, that query could fall back to scanning a huge collection, trigger an expensive sort, or spike latency during peak hours. If recovery is needed, rebuilding an index over large datasets consumes heavy resources and is far from instantaneous.

MongoDB provides **hidden indexes** to offer an intermediate testing step: **keep the index intact in the database, while preventing the query planner from selecting it during query planning**. If the workload runs smoothly across a representative observation window, the operations team gains stronger evidence for considering a drop. If performance degrades, you can **unhide** it without rebuilding the index.

This lesson focuses on what hidden indexes do, how to toggle them, the workflow for testing impact before dropping, how to interpret metrics, exceptions for unique/TTL indexes, and the limits of this testing approach.

## 1. What Is a Hidden Index?

A **hidden index** is an index that still exists, continues to be updated alongside data writes, and still consumes resources, yet **is excluded as a candidate by the query planner when serving queries**.

Picture a collection with three indexes:

~~~text
Collection: shop.orders

Indexes:
  _id_                            [VISIBLE]
  idx_orders_customer_created     [VISIBLE]
  idx_orders_status_created       [VISIBLE]

Query planner:
  Can consider any visible index matching the query.
~~~

When the third index is hidden:

~~~text
Collection: shop.orders

Indexes:
  _id_                            [VISIBLE]
  idx_orders_customer_created     [VISIBLE]
  idx_orders_status_created       [HIDDEN]

Query planner:
  Does NOT consider idx_orders_status_created as a candidate.
  Can still use remaining visible indexes or a collection scan.
~~~

A hidden index **is not removed from disk**. Inserts, updates, and deletes still maintain its index entries. In this regard, a hidden index is fundamentally different from a dropped index.

### 1.1. Key Properties

| Property | Visible index | Hidden index | Dropped index |
| --- | --- | --- | --- |
| Still exists in the collection | Yes | Yes | No |
| Used by query planner for queries | Possible | **No** | No |
| Usable as an index hint | Possible | **No** | No |
| Maintained when documents change | Yes | **Yes** | No |
| Consumes index storage space | Yes | **Yes** | Index removed |
| Impacts write overhead | Yes | **Still incurred** | Cost of index removed |
| Unique constraint if unique index | Enforced | **Still enforced** | Dropped index constraint lost |
| TTL behavior if TTL index | Active | **Still active** | Dropped index TTL removed |
| Can quickly restore query eligibility | Already visible | **Unhide, no rebuild needed** | Must rebuild index |

MongoDB has supported hidden indexes since **MongoDB 4.4**. In supported versions, hidden state is persisted in index metadata and remains until explicitly changed.

**You cannot hide the default `_id` index.** It is a special index bound to document identity. For all other indexes, verify operational requirements and special constraints before deciding to hide or drop.

### 1.2. Why Hidden Indexes Suit Pre-Drop Impact Testing

If you drop an index right away, you see the query-planner impact, yet recovery is expensive: you must run a full index rebuild.

If you **hide** the index first:

1. The query planner stops using that index.
2. You observe actual query plans and latencies.
3. If a regression occurs, call **unhideIndex()** so the query planner considers the index again.
4. If no unacceptable regression appears over an appropriate observation window, you can consider **dropIndex()** next.

With respect to **query index selection**, hiding simulates the index being absent. However, it is **not a complete simulation of all effects of dropping**, because write overhead, storage usage, and constraints like unique/TTL remain active.

## 2. Example Orders Collection and Three Query Types

We will use an illustrative **shop.orders** collection:

~~~javascript
{
  _id: ObjectId("673111111111111111111111"),
  customerId: "CUS-001",
  status: "PAID",
  createdAt: ISODate("2026-10-15T08:30:00Z"),
  totalAmount: NumberDecimal("450000.00"),
  shipping: {
    city: "HCM"
  }
}
~~~

Suppose the business queries include:

**Query A – fetch a customer's orders, newest first:**

~~~javascript
db.orders.find({ customerId: "CUS-001" })
  .sort({ createdAt: -1 })
  .limit(20);
~~~

**Query B – fetch the newest PAID orders:**

~~~javascript
db.orders.find({ status: "PAID" })
  .sort({ createdAt: -1 })
  .limit(20);
~~~

**Query C – look up one order by `_id`:**

~~~javascript
db.orders.findOne({
  _id: ObjectId("673111111111111111111111")
});
~~~

Indexes created to match requirements:

~~~javascript
use shop

db.orders.createIndex(
  { customerId: 1, createdAt: -1 },
  { name: "idx_orders_customer_created" }
);

db.orders.createIndex(
  { status: 1, createdAt: -1 },
  { name: "idx_orders_status_created" }
);
~~~

**idx_orders_customer_created** supports Query A. **idx_orders_status_created** is a suitable candidate for Query B. Query C can use the default **_id_** index.

Suppose the engineering team suspects **idx_orders_status_created** is no longer needed because the status-filtering flow is rarely used. **The target of the experiment is this index**, not the entire collection.

### 2.1. Listing Indexes Before Testing

~~~javascript
db.orders.getIndexes();
~~~

Output may contain entries such as:

~~~javascript
[
  {
    v: 2,
    key: { _id: 1 },
    name: "_id_"
  },
  {
    v: 2,
    key: { customerId: 1, createdAt: -1 },
    name: "idx_orders_customer_created"
  },
  {
    v: 2,
    key: { status: 1, createdAt: -1 },
    name: "idx_orders_status_created"
  }
]
~~~

This output is illustrative. Actual metadata may include additional fields depending on MongoDB version and index options. Before making changes, save the **full definition** of the candidate index, not just its name.

## 3. `hideIndex`, `unhideIndex`, and `dropIndex` Operations

In **mongosh**, you can toggle hidden state using collection methods.

### 3.1. Hiding an Index by Name

~~~javascript
db.orders.hideIndex("idx_orders_status_created");
~~~

From the moment the change takes effect, the query planner stops using this index for newly planned queries.

Inspect metadata:

~~~javascript
db.orders.getIndexes().filter(
  index => index.name === "idx_orders_status_created"
);
~~~

Illustrative output:

~~~javascript
[
  {
    v: 2,
    key: { status: 1, createdAt: -1 },
    name: "idx_orders_status_created",
    hidden: true
  }
]
~~~

The **hidden: true** field is the key indicator. For visible indexes, `hidden` may be omitted or set to false depending on representation; never rely on field ordering to identify an index.

### 3.2. Hiding an Index by Key Specification

Besides the name, you can specify the matching key document:

~~~javascript
db.orders.hideIndex({
  status: 1,
  createdAt: -1
});
~~~

In operations, index names are usually easier to control for logging, runbooks, and avoiding confusion between indexes with similar key patterns.

### 3.3. Unhiding to Restore Query Planner Eligibility

~~~javascript
db.orders.unhideIndex("idx_orders_status_created");
~~~

The index returns to visible status; MongoDB can consider it again for compatible queries. **No index rebuild is needed**, since the index was continuously maintained while hidden.

Unhiding does not guarantee every query immediately selects that index: the query planner still evaluates visible alternatives, selectivity, and cost factors.

### 3.4. Dropping an Index Once Evidence Supports It

~~~javascript
db.orders.dropIndex("idx_orders_status_created");
~~~

Unlike unhiding, **dropIndex** removes the index structure from the collection. To restore it, you must recreate the index:

~~~javascript
db.orders.createIndex(
  { status: 1, createdAt: -1 },
  { name: "idx_orders_status_created" }
);
~~~

On large collections, rebuilding an index takes time and resources; never treat it as an instant rollback like **unhideIndex()**.

### 3.5. Creating an Index Already Hidden from the Start

~~~javascript
db.orders.createIndex(
  { shippingCity: 1, createdAt: -1 },
  {
    name: "idx_orders_city_created_trial",
    hidden: true
  }
);
~~~

In this case, the index is built and maintained, yet **remains unused by the query planner** until unhidden. This is handy when preparing a new index without immediately altering active query plans.

However, **createIndex** still reads source data and builds index structures, incurring real resource cost. Setting `hidden: true` does not make index creation free.

## 4. Correctly Understanding Hidden Index Impacts

Hiding an index affects **eligibility for reads**, but does not completely disable the index.

### 4.1. The Query Planner Stops Choosing the Hidden Index

Suppose before hiding, Query B used the index:

~~~javascript
db.orders.find({ status: "PAID" })
  .sort({ createdAt: -1 })
  .limit(20);
~~~

Without an eligible index, MongoDB may:

- Pick a different visible index if advantageous.
- Scan the collection (**COLLSCAN**).
- Perform an unindexed sort.
- Combine other execution stages chosen by the query planner.

A query may slow down, or in some cases remain nearly unchanged if the planner wasn't relying on that candidate index anyway.

### 4.2. `hint` Cannot Force a Hidden Index

~~~javascript
db.orders.find({ status: "PAID" })
  .hint("idx_orders_status_created");
~~~

While the index is hidden, hinting it **cannot use that index to execute the query** and normally produces a hint-related error. Hidden means unavailable to the query planner, even when an application explicitly requests it.

That is why you must audit codebases and configs for **hardcoded `hint` calls** before hiding: applications can fail outright rather than merely slowing down.

### 4.3. Writes Must Still Maintain the Index

While hidden, this write still must update corresponding index entries:

~~~javascript
db.orders.insertOne({
  customerId: "CUS-999",
  status: "PENDING",
  createdAt: new Date(),
  totalAmount: 100000
});
~~~

For an update modifying an indexed field:

~~~javascript
db.orders.updateOne(
  { _id: someOrderId },
  { $set: { status: "PAID" } }
);
~~~

**idx_orders_status_created** continues to be updated even though the query planner cannot read it. Therefore, benchmarking **insert/update/delete speeds while hidden** does not reflect the write-amplification savings of **dropping the index**.

### 4.4. Storage Size Does Not Shrink When Hidden

~~~javascript
const info = db.orders.stats();

printjson(info.indexSizes);
print(info.totalIndexSize);
~~~

Hidden indexes still appear in stats and occupy storage resources. To reclaim that index's space, you must actually drop it after verifying constraints and risk.

## 5. Safe Workflow: Audit, Hide Trial, Observe, Decide

A practical workflow should include these stages:

~~~text
          Inventory indexes and workload
                        |
                        v
            Pick the exact candidate index
                        |
                        v
            Save definition + baseline metrics
                        |
                        v
            Test in a representative environment
                        |
                        v
              Controlled hide index
                        |
                        v
             Monitor queries and system health
                        |
              +---------+----------+
              |                    |
         Regression            No regression
              |                    |
              v                    v
         Unhide ASAP       Observe across full cycle
              |                    |
              v                    v
       Investigate &         Decide: keep hidden,
        keep index            unhide, or drop
~~~

A single error-free `explain` after hiding does not mean it is safe to drop the index. Observe **all critical query groups** across a meaningful time window.

### 5.1. Define the Goal of the Trial

For example:

> Determine whether removing `idx_orders_status_created` from query planning significantly increases latency for order-listing queries or end-of-day reports.

Define acceptance thresholds before changing anything, such as:

- p95 latency of affected APIs stays within approved latency budgets.
- Zero index-hint errors appear in application logs.
- No severe spike in `totalDocsExamined`/`totalKeysExamined` for critical queries.
- Database CPU, I/O, and memory pressure stay within operational limits.
- End-of-day, month-end, and scheduled jobs have all been accounted for.

Thresholds must reflect actual SLOs and workloads; **there is no universal safe percentage** across all systems.

### 5.2. Inventory Business Dependencies

An index might support:

- Low-frequency APIs with very high business priority.
- Daily or monthly accounting reports.
- Combined filter and sort queries.
- Batch jobs or migration queries.
- Queries with hardcoded **`hint()`** in application code.
- Aggregation pipelines using `$match`, `$sort`, or compatible lookups.
- Admin portal reads or external integration jobs.

Never glance at a single UI screen and conclude an index is unneeded. Understand **full workload coverage**.

## 6. Step One: Save the Current Definition and State

Before hiding, record the candidate index's metadata:

~~~javascript
const targetName = "idx_orders_status_created";

const target = db.orders.getIndexes()
  .find(index => index.name === targetName);

printjson(target);
~~~

Record:

- **name** and **key pattern**.
- **unique**, **partialFilterExpression**, **sparse**, **collation** if present.
- **expireAfterSeconds** if it is a TTL index.
- **hidden** if already set.
- Other properties like wildcard, text, geospatial, or version specifics.
- Target collection, database, and environment.

For example, another index might have this definition:

~~~javascript
{
  key: { email: 1 },
  name: "uq_accounts_email",
  unique: true,
  partialFilterExpression: {
    email: { $type: "string" }
  }
}
~~~

If dropped and later recreated, **never record only the key pattern** while omitting `unique` and `partialFilterExpression`. Recreating an index with the wrong options alters business rules.

### 6.1. Verify the Index Is Not the Default `_id` Index

~~~javascript
db.orders.getIndexes()
  .filter(index => index.name === "_id_");
~~~

MongoDB prohibits hiding the default **_id** index. For basic index cleanup, target secondary indexes with clear purposes that can be analyzed cleanly.

### 6.2. Distinguish Exact Duplicates from Near-Duplicates

Suppose you have:

~~~javascript
{ status: 1 }
{ status: 1, createdAt: -1 }
~~~

The second compound index has `status` as a **prefix**. In many situations it can serve status-only queries. However, the first index is not automatically useless:

- The two indexes differ in size.
- Sorts or projections have distinct characteristics.
- Options like collation, partial filter, or sparse may differ.
- Selectivity, stats, and query planner choices affect real execution.
- One index might be referenced by an explicit hint.

Hidden indexes let you test actual workload dependency rather than guessing from overlapping key prefixes.

## 7. Step Two: Collect Index Usage Statistics

MongoDB provides the **$indexStats** aggregation stage to inspect index access statistics.

~~~javascript
db.orders.aggregate([
  { $indexStats: {} }
]);
~~~

Results include fields such as:

~~~javascript
{
  name: "idx_orders_status_created",
  key: {
    status: 1,
    createdAt: -1
  },
  host: "db-01.example.net:27017",
  accesses: {
    ops: NumberLong(12),
    since: ISODate("2026-11-01T00:00:00Z")
  }
}
~~~

This is an illustrative example. **accesses.ops** reports how many times the index was recorded as used since **accesses.since** within the tracked scope. It neither tells you how much time the index saved nor guarantees a low-ops index is unimportant.

Filter stats for the candidate index:

~~~javascript
db.orders.aggregate([
  { $indexStats: {} },
  {
    $match: {
      name: "idx_orders_status_created"
    }
  },
  {
    $project: {
      _id: 0,
      name: 1,
      key: 1,
      host: 1,
      accesses: 1
    }
  }
]);
~~~

### 7.1. Why `accesses.ops = 0` Is Not Enough to Drop

Several possibilities exist:

- The query needing the index runs only at month-end, while your observation window spans just a few days.
- The query runs against a different replica set member.
- The application has seasonal workloads or rare batch jobs.
- Usage counters have a recent **since** timestamp due to a restart or metadata change.
- The index enforces a constraint, such as **unique** or **TTL**, which cannot be evaluated by read counts alone.
- A critical query was temporarily broken or didn't execute during the current measurement window.

Therefore, combine index usage figures with **logs, profiler data, application telemetry, query plans, and business job schedules**.

### 7.2. Stats Must Include Clear Timestamps and Sources

In replica sets or sharded clusters, stats are scoped per node, shard, or member. Never check one node and assume the entire cluster ignores an index.

Log at least:

~~~text
indexName: idx_orders_status_created
environment: production
observationStart: ...
observationEnd: ...
member/shard: ...
accesses.ops at start: ...
accesses.ops at end: ...
queries known to depend on index: ...
~~~

Recording this prevents misjudgments from reset counters or unrepresentative windows.

## 8. Step Three: Capture Query Plan Baselines

Before hiding, run `explain` on your most important queries. For example:

~~~javascript
db.orders.find({
  status: "PAID"
})
.sort({
  createdAt: -1
})
.limit(20)
.explain("executionStats");
~~~

An **explain** response can reveal:

- **winningPlan**: the chosen execution plan.
- **IXSCAN**: index scan.
- **COLLSCAN**: collection scan.
- **SORT**: separate sort stage if required by the plan.
- **totalKeysExamined**: number of index keys inspected.
- **totalDocsExamined**: number of documents inspected.
- **nReturned**: number of documents returned.
- **executionTimeMillis**: reported execution time during the explain run.

Stage names and positions can vary across MongoDB versions and execution engines (such as the classic engine vs. SBE). Read **plan semantics**, rather than relying on fixed JSON string matching.

### 8.1. Example Baseline Before Hiding

Suppose production holds several million documents and the query above uses the candidate index.

| Metric | Illustrative value before hide |
| --- | ---: |
| nReturned | 20 |
| totalKeysExamined | 20 |
| totalDocsExamined | 20 |
| Uses candidate index scan | Yes |
| Separate expensive sort | No |
| Explain duration | 7 ms |

**These figures are hypothetical examples illustrating comparison structure, not real environment measurements.**

An aligned compound index can handle both **status = PAID** filtering and **createdAt descending** ordering. Hiding the index removes that access path from the planner.

### 8.2. Save Representative Parameter Values Too

Do not benchmark solely a rare status or a tiny customer. Test representative inputs across:

- Common and rare filter values.
- Different time windows.
- Small limits and larger bulk-read queries.
- Tenants or regions with skewed data sizes.
- Sorted queries and aggregations.
- Projections and covered query eligibility.

An index might look unnecessary for a low-selectivity filter while proving vital for a high-selectivity one.

### 8.3. Do Not Treat `explain` as a Complete Benchmark

**Explain** reveals the plan and logical work, yet does not fully reflect end-to-end application latency:

- Warm vs. cold cache states differ.
- Real production concurrency is higher.
- Network hops and driver decoding are not measured like API requests.
- The query planner may choose different plans across parameter values or stats.
- The environment where `explain` runs may not mirror production load.

Combine **before/after `explain`** with **real workload metrics**.

## 9. Step Four: Run the Hide Experiment

Once you have a baseline and rollback plan, execute:

~~~javascript
db.orders.hideIndex("idx_orders_status_created");
~~~

Verify the change:

~~~javascript
const index = db.orders.getIndexes().find(
  i => i.name === "idx_orders_status_created"
);

printjson({
  name: index?.name,
  hidden: index?.hidden
});
~~~

Expect **hidden: true** on the target index.

### 9.1. Re-run the Same Query

~~~javascript
db.orders.find({
  status: "PAID"
})
.sort({
  createdAt: -1
})
.limit(20)
.explain("executionStats");
~~~

Suppose after hiding, the planner finds no equivalent index:

| Metric | Before hide | After hide | Interpretation |
| --- | ---: | ---: | --- |
| nReturned | 20 | 20 | Same number of results |
| totalKeysExamined | 20 | 0 | Plan likely fell back to COLLSCAN |
| totalDocsExamined | 20 | 2,000,000 | Read cost spiked sharply |
| Separate SORT | No | Yes | Must sort without index order |
| Explain duration | 7 ms | 900 ms | Notable regression |

**This table is a hypothetical scenario**, not a guaranteed outcome or fixed forecast. In an environment where another index satisfies the query, the delta might be tiny or look completely different.

### 9.2. Distinguish Correctness from Performance

When an index is hidden, the logical result set of normal queries **should not change merely because that index is unavailable**, yet:

- Queries may slow down or time out.
- Requests using **`hint` pointing to the hidden index** can fail with an error.
- Queries without an explicit sort still have no guaranteed result order.
- Downstream components sensitive to response times can experience cascading failures.

That is why testing must check not just "returned the right number of documents," but also **latency, system load, timeouts, and API error rates**.

### 9.3. Hide Only One Index at a Time When Possible

If you hide three indexes simultaneously and a regression hits, pinpointing the culprit becomes difficult. A cautious workflow changes **one candidate at a time**, monitors all affected queries, and only then moves to the next candidate.

Still, some indexes are tightly coupled, such as near-duplicate sets. Whenever testing a multi-index change together, enforce clear experimental design and rapid rollback readiness.

## 10. When Should You Unhide Immediately?

Stop-trial signals include:

- Queries whose p95 used to sit below SLO now breach latency budgets.
- Frequent **COLLSCAN** or expensive **SORT** stages appear.
- Queries using hardcoded hints start throwing errors.
- Critical APIs show rising timeouts or error rates.
- Database CPU, disk I/O, or cache pressure climbs sharply.
- Replication lag or member load increases noticeably.
- Scheduled business jobs fail to finish on time.

Restore the index:

~~~javascript
db.orders.unhideIndex("idx_orders_status_created");
~~~

Confirm status:

~~~javascript
db.orders.getIndexes().filter(
  index => index.name === "idx_orders_status_created"
);
~~~

After unhiding, keep monitoring until performance stabilizes. In some cases the query planner might stick to an alternative plan; if metrics do not recover, investigate further instead of blaming everything on the hidden trial.

**Rolling back via unhide does not undo timeouts, retries, or side effects that already occurred during the trial.** Production trials still require proper change windows and active monitoring.

## 11. Special Index Types: Evaluate Beyond Read Performance

An index rarely picked by the query planner may still be vital for **data integrity** or system mechanics.

### 11.1. Unique Indexes: Hiding Does Not Disable Uniqueness

Example:

~~~javascript
db.accounts.createIndex(
  { email: 1 },
  {
    name: "uq_accounts_email",
    unique: true
  }
);
~~~

Hide the index:

~~~javascript
db.accounts.hideIndex("uq_accounts_email");
~~~

**The unique constraint remains enforced.** An insert introducing a duplicate email under the index's rules still fails with a duplicate key error:

~~~javascript
db.accounts.insertOne({
  email: "same@example.net"
});
~~~

If you drop the unique index, the uniqueness constraint it enforced **vanishes**. That is a major business difference that hidden indexes **do not simulate**.

Before dropping a unique index, confirm whether an **alternative safeguard** enforces uniqueness. Never conclude from a "clean hide trial with zero errors" that a unique index can be dropped safely.

### 11.2. TTL Indexes: Hiding Keeps Expiration Active

Example TTL index on a BSON Date field:

~~~javascript
db.sessions.createIndex(
  { expiresAt: 1 },
  {
    name: "ttl_sessions_expiry",
    expireAfterSeconds: 0
  }
);
~~~

If hidden:

~~~javascript
db.sessions.hideIndex("ttl_sessions_expiry");
~~~

The TTL index stays active and **the TTL monitor continues deleting expired documents** per configuration. Hiding is not a way to pause automatic data expiration.

If you drop the TTL index, the collection loses that expiration mechanism. Documents meant to expire will linger, impacting retention compliance and storage.

If your goal is altering retention policy, update the TTL settings and business rules properly—never use hide as a pause switch for TTL.

### 11.3. Partial Indexes and Sparse Indexes

Example partial index:

~~~javascript
db.orders.createIndex(
  { customerId: 1, createdAt: -1 },
  {
    name: "idx_paid_customer_created",
    partialFilterExpression: {
      status: "PAID"
    }
  }
);
~~~

This index holds only entries matching the partial filter. It may show modest counts in collection-wide stats while remaining crucial for a key query subset.

During audits, record **partialFilterExpression** alongside the corresponding query filters. Similarly, sparse indexes omit missing-field documents differently from standard indexes; never treat two indexes with matching key patterns as equivalent if one is sparse and the other is not.

### 11.4. Collation and Language-Aware Indexes

Two indexes with identical key patterns but different **collations** serve different string comparison rules. For instance, a case-insensitive query may need an index with matching collation to stay fast.

When hiding a collated index, do not test only default-collation queries; test the exact collated queries your application sends.

### 11.5. Indexes Serving Specialized Features

Text, geospatial, wildcard, and other specialized indexes differ from standard B-trees:

- Text queries rely on appropriate text indexes.
- Geospatial queries use dedicated indexes and rules.
- Wildcard indexes cover dynamic field paths.
- Shard-key-related indexes carry special operational roles.

For these, verify exact index functionality and constraints before hiding or dropping rather than running only a simple lookup check.

## 12. Why Hidden Indexes Cannot Measure All Benefits of Dropping

A hidden index is a **query-planner dependency test**, not a comprehensive drop simulation.

### 12.1. What Hidden Indexes Help Verify

- Which queries lose an indexed access path?
- Does the query planner have an acceptable visible fallback?
- Do query latencies climb?
- Do collection scans or sorts increase?
- Does any code pass a `hint` naming the index?
- Can the read workload tolerate running without the candidate index?

### 12.2. What Hidden Indexes Do Not Simulate

- **Storage savings** gained after dropping.
- **Write overhead reduction** from stopping index entry updates.
- **Cache pressure relief** from removing the index structure.
- **Loss of uniqueness** when dropping a unique index.
- **Loss of TTL expiration** when dropping a TTL index.
- **Rebuild cost and duration** if a post-drop rollback becomes necessary.
- Operational changes tied to special index properties.

If your primary goal is cutting write amplification, hiding provides zero quantitative proof of write gains. Use hiding to test **read-side risk**, and use dedicated staging benchmarks to estimate post-drop write improvements.

## 13. Query Plans, Index Prefixes, and Misleading Cases

### 13.1. One Index Can Serve Multiple Query Shapes

A compound index:

~~~javascript
{
  customerId: 1,
  createdAt: -1
}
~~~

can help both:

~~~javascript
db.orders.find({ customerId: "CUS-001" });
~~~

and:

~~~javascript
db.orders.find({ customerId: "CUS-001" })
  .sort({ createdAt: -1 });
~~~

Hiding the index might trigger a regression on **one query shape** while leaving another unaffected. Checking only the primary API's latency can miss secondary breakage.

### 13.2. Other Indexes Can Mask the Impact

Suppose the collection also has:

~~~javascript
{ status: 1 }
{ status: 1, createdAt: -1 }
{ createdAt: -1 }
~~~

Hiding `{ status: 1, createdAt: -1 }` lets MongoDB fall back to `{ status: 1 }` plus a sort, or `{ createdAt: -1 }` plus filtering. Depending on data, one fallback might remain acceptable or prove inefficient.

The accurate takeaway from a clean trial is **"given the observed workload and remaining visible indexes, no regression breached thresholds"**—never **"the hidden index is universally useless under all conditions."**

### 13.3. Covered Queries Can Lose Index-Only Execution

Example:

~~~javascript
db.orders.find(
  { status: "PAID" },
  { _id: 0, status: 1, createdAt: 1 }
);
~~~

If a compound index includes all queried and returned fields, the query may complete without fetching documents, under eligible conditions. Once hidden, the fallback plan may have to examine far more documents.

Thus, comparing **totalDocsExamined** relative to returned counts reveals regressions better than looking at one timing number alone.

### 13.4. Selectivity Varies with Data Skew

When `PAID` covers 90% of the collection, filtering `PAID` has low selectivity. When `PENDING` is only 0.1%, a `status` index can be vital for `PENDING` queries.

Always benchmark both **common** and **rare** values, especially on skewed collections.

## 14. Production Observation: Combining Multiple Signals

Never rely on a single `explain` or one index usage counter check.

| Source | Question answered | Limitation |
| --- | --- | --- |
| **getIndexes()** | Does the index exist and is it hidden? | Does not show whether the index helps the workload |
| **$indexStats** | How many times has the index been used since stats started? | Counters do not measure performance gains or rare jobs |
| **explain("executionStats")** | Which plan does this query use and how many keys/docs are scanned? | Does not replace live workload latency |
| **Profiler / slow query log** | Which queries are slow and how did plans change? | Requires proper configuration and overhead checks |
| **APM / application telemetry** | How did p50/p95/p99 API latencies and error rates shift? | Reflects layers outside the database as well |
| **Host / cluster metrics** | Did CPU, I/O, cache, or replication lag increase? | Must be compared against matching load and time windows |
| **Business batch schedule** | Do rare queries or scheduled jobs need the index? | May not appear during a short trial window |

### 14.1. Before/After Comparison Over a Suitable Window

A trial log might use a table like this:

| Metric | Baseline | Hidden trial | Acceptance threshold |
| --- | ---: | ---: | --- |
| p95 API list orders | 80 ms | 95 ms | < 150 ms |
| p99 API list orders | 180 ms | 250 ms | < 300 ms |
| Timeout rate | 0.02% | 0.03% | < 0.10% |
| Queries switching to COLLSCAN | 0 | 5 | Investigate closely |
| Database CPU | 45% | 49% | Within load budget |
| End-of-day reconciliation job | Completed | Not yet run | **Insufficient to conclude** |

**All figures in this table are hypothetical.** The key point is that a trial looking fine for daytime APIs is still incomplete if **the end-of-day reconciliation job has not run yet**.

### 14.2. Evaluate Full Workload Cycles

Many systems have distinct periodic loads:

- Morning data syncs.
- End-of-day report rollups.
- Weekend cleanup batches.
- Start-of-month financial reconciliation.
- Promotional campaigns generating traffic spikes.

Trial windows must span relevant workloads or be paired with equivalent representative tests. If an entire schedule cannot be observed, explicitly document what remains **unverified** before deciding to drop.

### 14.3. Track by Query Shape

A query shape captures the filter structure, sort, projection, and query attributes rather than literal parameter values. Grouping by query shape when assessing index impact avoids mistaking ten thousand executions of the same shape for ten thousand distinct queries.

Monitoring tools may define query shape identifiers differently across MongoDB versions. Use metadata schemas matching your deployed version.

## 15. Staging vs. Production: Choosing Trial Scope

### 15.1. Staging with Representative Data

Pros:

- Test hide/unhide with zero user-facing impact.
- Replay scripted read and write workloads.
- Uncover known queries dependent on the index.

Cons:

- Smaller data sizes can cause the query planner to pick different plans.
- Value distributions and statistics may diverge from production.
- Lower concurrency and different cache/I/O profiles.
- Rare batch jobs may not be simulated.

Staging is a vital step, yet clean runs on a few thousand documents cannot prove safety at hundreds of millions of documents.

### 15.2. Production Trials Require Change Control

**Hiding an index in production is a real change to query planner behavior**, not a harmless shadow simulation. Execute it only with proper authorization and change plans.

A controlled rollout needs:

1. Confirmed collection and exact index name.
2. Saved index definition and baseline metrics.
3. Assigned owners for monitoring metrics and executing rollback.
4. Defined observation window and abort thresholds.
5. Ready-to-run `unhide` command.
6. Active monitoring of affected APIs and jobs.
7. Recorded results and post-trial decision.

If your architecture supports testing on a subset of workload or a closer-to-production replica, choose the lowest-risk scope that still represents reality.

### 15.3. Hiding Is Not a Per-User Feature Flag

Toggling an index's hidden flag applies at the index/collection level. It is not a per-request flag for independent A/B simulation. Every query planned while the index is hidden sees that hidden state across the deployed scope.

Therefore, never assume "only 5% of users see the hidden index" when running **`hideIndex()`** on a shared collection, unless your deployment architecture isolates environments or shards specifically to support that experiment.

## 16. Hidden Indexes in Replica Sets and Sharded Clusters

### 16.1. Replica Sets

Each replica set member maintains its own data and indexes to serve reads routed to it according to topology and read preferences. When evaluating impact, observe:

- Reads routed to the primary.
- Reads routed to secondaries via read preferences.
- Load and latency across all nodes.
- Replication lag and any topology changes.

Never inspect one node and assume every client sees identical query performance. Drivers may read from other members with different cache warmth and workload pressure.

### 16.2. Sharded Clusters

In a sharded cluster, a collection spans multiple shards. Query plans and performance vary by data distribution, targeted shards, and shard-key routing.

Before hiding or dropping an index in a sharded cluster, check:

- Do queries include the shard key or scatter-gather across shards?
- Does the index support filters/sorts on individual shards?
- Does the collection or index tie directly to shard-key constraints?
- Which shards were queried for index usage metrics?
- Is any shard vastly larger than others?
- Has the collection-wide index operation been approved operationally?

When administering sharded collections, execute commands through **`mongos`** per standard procedure; never alter index states independently on individual shards and leave the cluster inconsistent.

### 16.3. Hidden Indexes Do Not Replace Shard Key Analysis

A secondary index can assist queries, yet cannot fix a poorly chosen shard key or skewed data chunks. If queries still fan out to many shards, hiding an index reveals only part of the intra-shard execution impact.

Never drop an index tied to sharded cluster operational constraints merely because its read usage looks low. Check topology-specific rules first.

## 17. Example Using `collMod`

Alongside the **`hideIndex()`** and **`unhideIndex()`** helpers, MongoDB provides the administrative **`collMod`** command to modify select index properties, including `hidden`.

Hide an index by name:

~~~javascript
db.runCommand({
  collMod: "orders",
  index: {
    name: "idx_orders_status_created",
    hidden: true
  }
});
~~~

Unhide it:

~~~javascript
db.runCommand({
  collMod: "orders",
  index: {
    name: "idx_orders_status_created",
    hidden: false
  }
});
~~~

Run this inside the **shop** database, since **`collMod: "orders"`** targets that collection in the current database.

For everyday hands-on work, **`db.orders.hideIndex()`** and **`db.orders.unhideIndex()`** are cleaner to read. When integrating into automation tools or drivers lacking dedicated helpers, `collMod` is the explicit alternative.

### 17.1. Required Index Permissions

Viewing index lists and toggling hidden state require different privileges. Standard application accounts granted collection read permissions do not automatically have `hide`/`unhide`/`drop` rights.

In production, use least-privilege administrative identities with auditing and change approval workflows. Never grant index-management privileges to a business API just to run experiments.

## 18. Java Sync Driver Example for Managing Hidden Indexes

A Java application should not hide indexes inside request-handling code. However, admin tooling or migration jobs may need to issue **`collMod`**.

Example using **`MongoDatabase.runCommand()`**:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public class ToggleHiddenIndex {

    private static void setHidden(
            MongoDatabase database,
            String collectionName,
            String indexName,
            boolean hidden) {

        Document indexOptions = new Document("name", indexName)
                .append("hidden", hidden);

        Document command = new Document("collMod", collectionName)
                .append("index", indexOptions);

        Document result = database.runCommand(command);
        System.out.println(result.toJson());
    }

    public static void main(String[] args) {
        String uri = "mongodb://localhost:27017";

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database = client.getDatabase("shop");

            // Intentional experiment; never run automatically inside HTTP requests.
            setHidden(
                    database,
                    "orders",
                    "idx_orders_status_created",
                    true
            );

            // Restore after observation:
            setHidden(
                    database,
                    "orders",
                    "idx_orders_status_created",
                    false
            );
        }
    }
}
~~~

This demonstrates the Java API, **not a safe automated production pipeline**. Running it requires a MongoDB server supporting hidden indexes, an existing target index, a valid URI, and sufficient account privileges.

The snippet toggles hide then unhide back-to-back to illustrate syntax, leaving no real observation period in between. In actual trials, those two calls belong to **two separate operational steps**, separated by a metric-collection window.

### 18.1. Be Careful When Automating Drops

If code automatically runs:

~~~java
// Never assume dropping is safe merely because hiding succeeded.
~~~

you lack evidence that the workload does not need the index. Drop decisions require full-cycle observation, constraint checks, and a prepared recovery plan.

Admin tooling can automate capturing index definitions and metrics, while still enforcing explicit change gates before any drop.

## 19. Deciding to Keep, Unhide, or Drop

After the trial, interpret outcomes as follows:

| Trial result | Appropriate decision |
| --- | --- |
| Critical queries slow down noticeably | **Unhide** and keep the index, or design a replacement |
| Errors caused by index hints | **Unhide**, fix the dependency, or plan a safe migration |
| No regression yet, but month-end jobs haven't run | Keep observing or keep the index; **insufficient evidence to drop** |
| No regression across representative workloads, no special constraints | Consider **dropping** after completing final review |
| Index is unique, TTL, or backs business rules | Evaluate constraints separately; a hidden trial is **not enough** |
| Want planner to skip index while preserving its constraint | Can **keep hidden** long-term if intentional and write cost is acceptable |
| Upcoming feature will require the index | Keep the index or schedule a proper build before feature launch |

An index **unused in today's workload** may be intentionally kept for an upcoming release; conversely, an index with low access counts that serves an **ultra-critical query** may be well worth keeping.

### 19.1. Save the Definition for Rebuilding

Before dropping, save the full spec:

~~~javascript
const definition = db.orders.getIndexes().find(
  i => i.name === "idx_orders_status_created"
);

printjson(definition);
~~~

For the sample index, the rebuild command would be:

~~~javascript
db.orders.createIndex(
  { status: 1, createdAt: -1 },
  {
    name: "idx_orders_status_created"
  }
);
~~~

If the actual index has `unique`, TTL, collation, `partialFilterExpression`, or other options, preserve and restore every one faithfully. The simple command above **is not enough** to rebuild every index type.

### 19.2. Keep Monitoring After Dropping

A successful hidden trial lowers risk, yet you must keep monitoring after dropping:

- Query latencies and application errors.
- Storage and cache resources.
- Write throughput and latency.
- Query plans under live traffic.
- Periodic batch jobs as each runs post-change.

Dropping can reduce write and storage overhead, yet actual savings must be measured—they do not scale linearly with the byte size of the removed index.

## 20. Sample Runbook for a Trial

A concise yet complete operational runbook might look like this:

### Phase A – Preparation

**Goal:** verify whether `idx_orders_status_created` can be safely removed from `shop.orders`.

Steps:

1. Confirm target environment, database, and collection.
2. Save **`getIndexes()`** output and the candidate index definition.
3. Audit unique, TTL, partial, sparse, collation, and sharding constraints.
4. Collect **`$indexStats`** over a representative window.
5. Inventory APIs, jobs, and query shapes relying on the index.
6. Record baseline `explain` plans and p95/p99 latencies.
7. Agree on rollback thresholds.
8. Stage the **`unhideIndex()`** command ready to run.

### Phase B – Execution

~~~javascript
use shop

db.orders.hideIndex("idx_orders_status_created");

db.orders.getIndexes().filter(
  i => i.name === "idx_orders_status_created"
);
~~~

Verify **hidden: true**, then monitor the workload.

### Phase C – Comparison

Re-run representative queries:

~~~javascript
db.orders.find({
  status: "PAID"
})
.sort({
  createdAt: -1
})
.limit(20)
.explain("executionStats");
~~~

Log:

~~~text
Query shape:
Candidate index:
Baseline timestamp:
Hidden timestamp:
Plan before:
Plan after:
DocsExamined before/after:
KeysExamined before/after:
p95/p99 before/after:
Errors and timeouts:
Batch/report status:
Conclusion:
~~~

### Phase D – Rollback If Thresholds Are Breached

~~~javascript
db.orders.unhideIndex("idx_orders_status_created");
~~~

Confirm metadata and continue monitoring. If the trial caused a regression, do not proceed to drop.

### Phase E – Decision

Once sufficient evidence is gathered:

- **Keep visible:** index is beneficial or removal risk is unacceptable.
- **Keep hidden:** want planner to avoid it while keeping the index/constraint intact.
- **Drop:** query impact and constraints are verified, with a rebuild plan ready.
- **Replace index:** another index serves multiple query shapes better; build and test the new index before removing the old one.

Never turn this runbook into an automated **`hide → wait a few seconds → drop`** script, because a few seconds cannot prove all critical workloads have executed.

## 21. Common Misconceptions

| Misconception | Correct understanding |
| --- | --- |
| A hidden index is deleted from the database | It still exists, is maintained on writes, and occupies storage |
| Hiding an index speeds up inserts/updates just like dropping | Write maintenance overhead remains while hidden |
| The query planner can still pick a hidden index if it's a great match | Hidden indexes are never selected to serve queries |
| You can `hint` a hidden index for testing | Hints cannot make a hidden index usable |
| Hiding a unique index disables uniqueness checks | Unique constraints remain enforced |
| Hiding a TTL index stops expired document deletion | TTL expiration remains active |
| Seeing `accesses.ops = 0` proves the index is useless | Check stats reset time, nodes, rare queries, and constraints |
| Before/after `explain` alone suffices to drop | Observe live workloads, SLOs, concurrency, and periodic schedules |
| Unhiding and recreating an index are equivalent | Unhiding requires no rebuild; dropping and recreating is costly |
| If two indexes share a key prefix, one is definitely redundant | Check sorts, projections, selectivity, collations, and index types |
| Hiding affects only the test query | Hiding removes planner visibility across the whole collection |
| You can hide the default `_id` index | Hiding the default `_id` index is prohibited |
| No slowdown during the trial means zero risk | Rare jobs or peak loads may not have occurred yet |
| Dropping an already-hidden index is just a minor status tweak | Dropping removes the index structure and can drop special constraints |

## 22. Hands-On Lab with a Test Collection

This lab uses an isolated collection to avoid affecting business data. The examples below are for `mongosh` on MongoDB versions supporting hidden indexes.

### Exercise 1 – Create Data and Index

~~~javascript
use hidden_index_lab

db.orders.insertMany([
  {
    _id: 1,
    customerId: "C-01",
    status: "PAID",
    createdAt: ISODate("2026-01-01T10:00:00Z"),
    amount: 100000
  },
  {
    _id: 2,
    customerId: "C-02",
    status: "PENDING",
    createdAt: ISODate("2026-01-02T10:00:00Z"),
    amount: 200000
  },
  {
    _id: 3,
    customerId: "C-01",
    status: "PAID",
    createdAt: ISODate("2026-01-03T10:00:00Z"),
    amount: 300000
  },
  {
    _id: 4,
    customerId: "C-03",
    status: "CANCELLED",
    createdAt: ISODate("2026-01-04T10:00:00Z"),
    amount: 150000
  },
  {
    _id: 5,
    customerId: "C-02",
    status: "PAID",
    createdAt: ISODate("2026-01-05T10:00:00Z"),
    amount: 280000
  }
]);

db.orders.createIndex(
  { status: 1, createdAt: -1 },
  { name: "idx_status_created" }
);
~~~

Re-running `insertMany` on a collection already holding IDs 1–5 causes duplicate key errors; use a new test database or clean up sample data explicitly rather than running against production.

### Exercise 2 – Observe Before Hiding

~~~javascript
db.orders.getIndexes();

db.orders.find({ status: "PAID" })
  .sort({ createdAt: -1 })
  .explain("executionStats");
~~~

Check:

- Does **idx_status_created** exist?
- Does the winning plan use this index?
- How many documents are returned?
- Is there a separate `SORT` stage?
- What are `totalKeysExamined` and `totalDocsExamined`?

With **only 5 documents**, the query planner may choose `COLLSCAN` due to tiny cost; never treat skipping an index on a tiny dataset as proof that the index is useless in production.

### Exercise 3 – Hide the Index and Compare

~~~javascript
db.orders.hideIndex("idx_status_created");

db.orders.getIndexes().filter(
  index => index.name === "idx_status_created"
);

db.orders.find({ status: "PAID" })
  .sort({ createdAt: -1 })
  .explain("executionStats");
~~~

Explain:

1. Does the index still appear in `getIndexes()`?
2. Why does `hidden: true` not mean dropped?
3. Can the query planner use this index after hiding?
4. Did the plan change? If no change appeared due to the tiny collection, what kind of test environment is needed to measure accurately?

### Exercise 4 – Exploring `hint`

While the index is still hidden:

~~~javascript
db.orders.find({ status: "PAID" })
  .hint("idx_status_created")
  .toArray();
~~~

Observe the error message and explain why `hint` cannot force the query planner to use a hidden index.

Then unhide it:

~~~javascript
db.orders.unhideIndex("idx_status_created");
~~~

Re-run the hinted query if you want to observe the difference in a test collection.

### Exercise 5 – Testing a Unique Index

~~~javascript
db.accounts.insertOne({
  _id: 1,
  email: "an@example.net"
});

db.accounts.createIndex(
  { email: 1 },
  {
    name: "uq_accounts_email",
    unique: true
  }
);

db.accounts.hideIndex("uq_accounts_email");
~~~

Attempt to insert another account with the same email:

~~~javascript
db.accounts.insertOne({
  _id: 2,
  email: "an@example.net"
});
~~~

MongoDB still rejects the unique constraint violation. Explain why a hidden trial alone cannot prove **dropping a unique index** is safe.

### Exercise 6 – Analyzing a Suspected Redundant Index

Suppose a real system has three indexes:

~~~javascript
{ customerId: 1 }
{ customerId: 1, createdAt: -1 }
{ status: 1, createdAt: -1 }
~~~

And these queries:

~~~javascript
// Q1
db.orders.find({ customerId: "C-01" });

// Q2
db.orders.find({ customerId: "C-01" })
  .sort({ createdAt: -1 })
  .limit(30);

// Q3
db.orders.find({ status: "PAID" })
  .sort({ createdAt: -1 })
  .limit(30);
~~~

Propose:

1. Which index is the best candidate to hide-test first?
2. Do Q1, Q2, and Q3 depend on the same index?
3. In which cases should selectivity and projection be checked?
4. Why shouldn't you hide all three indexes in one step?
5. Which metrics and query shapes must be monitored before dropping?

### Exercise 7 – Write Your Own Runbook

You need to shrink index footprint on a 100-million-document collection. Write a plan covering:

- Goal and candidate index name.
- Commands to inspect definition and usage.
- How to identify critical queries, scheduled jobs, and hints.
- Baseline metrics.
- Hide command and hidden-state verification.
- Rollback thresholds and unhide command.
- Representative observation window.
- What a hidden trial does not simulate.
- Conditions permitting a drop and how to preserve the definition for rebuilding.

A solid plan goes beyond **the three commands hide–unhide–drop**—it includes **rationale for picking the index, workload evidence, stop criteria, and recovery procedures**.

## 23. Key Principles to Remember

Hidden indexes are a tool to **reduce risk when evaluating whether an index is still needed for query performance**. Hiding keeps the index intact while barring the query planner from using it; unhiding lets the planner reconsider it immediately without rebuilding from scratch.

Thus, the proper workflow is typically:

**Inventory → Measure baseline → Hide → Monitor workload → Unhide on regression → Drop only after full evaluation.**

Never forget three limitations:

1. Hidden indexes **still consume write and storage resources**.
2. Hidden indexes **still enforce unique/TTL and attached mechanisms**, so they do not simulate every consequence of dropping.
3. A short test or single query **does not represent the entire workload**, especially for periodic reports, rare queries, and sharded clusters.

A well-designed experiment answers not just "is the index currently used?", but also **"if this index is gone, which critical queries and constraints will be impacted, and how does the system recover?"**.

## References

- [MongoDB Manual — Hidden Indexes](https://www.mongodb.com/docs/manual/core/index-hidden/)
- [MongoDB Manual — db.collection.hideIndex()](https://www.mongodb.com/docs/manual/reference/method/db.collection.hideIndex/)
- [MongoDB Manual — db.collection.unhideIndex()](https://www.mongodb.com/docs/manual/reference/method/db.collection.unhideIndex/)
- [MongoDB Manual — db.collection.dropIndex()](https://www.mongodb.com/docs/manual/reference/method/db.collection.dropIndex/)
- [MongoDB Manual — db.collection.getIndexes()](https://www.mongodb.com/docs/manual/reference/method/db.collection.getIndexes/)
- [MongoDB Manual — $indexStats](https://www.mongodb.com/docs/manual/reference/operator/aggregation/indexStats/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual — Index Properties](https://www.mongodb.com/docs/manual/core/indexes/index-properties/)
