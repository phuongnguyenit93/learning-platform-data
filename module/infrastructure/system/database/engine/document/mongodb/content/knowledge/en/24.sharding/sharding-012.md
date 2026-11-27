# Impact of sharding on aggregation, transactions, and MongoDB operations

A MongoDB collection can grow from a few million to billions of documents, making it difficult for a single replica set to handle storage capacity, read/write throughput, and complex reporting simultaneously. **Sharding** distributes a collection's documents across multiple shards to scale horizontally. However, once data lives across multiple shards, an aggregation no longer necessarily executes on a single node; a transaction may require coordinating multiple replica sets; and tasks such as data balancing, index creation, or backups become cluster-wide operations.

For example, take the same `$group` pipeline by tenant:

- If the data to be read resides on one shard, it can be processed almost like a normal pipeline on that shard.
- If documents for multiple tenants or a single tenant span multiple shards, MongoDB must collect **partial results** and may have to **merge** them to compute the accurate cluster-wide total.
- If followed by `$sort` and `$limit`, the ordering/top N must be determined **globally across all data**, not just by taking the top N from one shard.
- If the pipeline writes results to a sharded collection or uses `$lookup` against a sharded collection, routing rules and stage constraints become critical.

Similarly, transferring inventory between two warehouses on **two different shards** can still be wrapped in a distributed transaction on supported versions, but commit overhead, abort risk, and latency are typically higher than a single-document atomic update.

This lesson belongs to the **Sharding** chapter of the *Database Engine Document MongoDB* module, focusing on three pillars: **aggregation – transactions – operations**. Examples use **mongosh** and the **Node.js Driver**; sharding/configuration commands are strictly for a **sharded cluster lab**. Because MongoDB evolves across releases, capabilities such as `$lookup` on sharded collections, distributed transactions, online resharding, DDL, and `explain` output formats must be verified against your server/driver version and managed environment.

## 1. Learning objectives

After this lesson, you will be able to:

1. Describe the query flow from the driver through `mongos`, config servers, and the shards holding data.
2. Explain **targeted operations** using a shard key versus **scatter-gather** when narrow routing is not possible.
3. Predict when an aggregation must run across multiple shards and include a **merge step**.
4. Understand how `$match`, `$group`, `$sort`, `$skip`, and `$limit` are affected by sharding.
5. Identify fan-out costs and shard-targeting conditions in `$lookup`, along with restrictions of `$out` and `$merge`.
6. Distinguish read-only aggregations from pipelines that write results to a collection.
7. Distinguish single-document atomic updates, single-shard transactions, and **cross-shard transactions**.
8. Build transactions with sessions, shard-key-aware filters, idempotency, read/write concerns, and proper retry handling.
9. Recognize transaction limits related to lifetime, cache, DDL, chunk migrations, and commit coordination.
10. Explain the balancer, chunks/ranges, data skew, hot shards, changing shard keys, and resharding.
11. Measure performance using `explain()`, per-shard metrics, indexes, and network/merge overhead.
12. Design batch jobs, reporting, backups, and schema rollouts suitable for a sharded cluster.

## 2. Architecture affects the entire read/write path

A sharded cluster consists of the following main components:

- **`mongos`:** the query router receiving commands from applications and using metadata to decide which shards must participate. It does not store the full application dataset.
- **Config server replica set (CSRS):** stores metadata about collections, chunks/ranges, data distribution, and cluster configuration.
- **Shards:** each shard is typically a **replica set** holding a subset of data from sharded collections. An unsharded collection still resides on one owning shard per metadata.
- **Balancer/metadata services:** coordinate range/chunk distribution to balance according to policies and topology; exact mechanisms can vary by version.

~~~mermaid
flowchart TD
    Client["Driver / API"] --> Router["mongos query router"]
    Router <-->|"Metadata/routing"| Config["Config Server Replica Set"]
    Router --> S1["Shard A (Replica Set)"]
    Router --> S2["Shard B (Replica Set)"]
    Router --> S3["Shard C (Replica Set)"]
    S1 --> P1["Data Range 1"]
    S2 --> P2["Data Range 2"]
    S3 --> P3["Data Range 3"]
~~~

### 2.1. Sharding differs from replication

| Aspect | Replication | Sharding |
|---|---|---|
| Primary goal | Redundancy, HA, failover recovery | Horizontal data and load distribution |
| Data per member | Secondaries replicate the replica set's data | Each shard holds **a subset** of a sharded collection |
| Component handling writes | Replica set primary | `mongos` routes to a shard, then that shard's primary receives the write |
| Distributed reads | Read preference selects a replica set member | Queries may read **multiple shards**, each with its own replica set members |
| Failures to watch | Lag/election/majority | Routing, chunk placement, balancer, scatter-gather, multi-shard failures |

Adding a shard **is not equivalent** to adding a secondary. Adding a secondary to a shard increases that shard's redundancy/read offloading; adding a shard can split data, but causes cross-shard queries and transactions to coordinate across more locations.

### 2.2. Routing metadata is not authorization data

`mongos` uses the shard key to locate where documents live. That **does not replace** `tenantId` and access permission checks. A query routed to the right shard without a tenant filter can still return unauthorized data if the application layer fails to enforce it.

## 3. The shard key determines which shards an aggregation touches

Suppose the `orders` collection is sharded by:

~~~javascript
{ tenantId: 1, orderId: 1 }
~~~

This is a compound **ranged shard key**. MongoDB distributes data across ranges of the chosen key. Whether a query is narrowly routed depends on **filters on the shard key**, current range locations, and how metadata splits/distributes chunks.

### 3.1. Point query with full shard key

~~~javascript
db.orders.findOne({
  tenantId: "t-01",
  orderId: "o-001"
})
~~~

With equality on the entire shard key and valid metadata, `mongos` can typically route directly to the shard holding that key. This is especially beneficial for single-order read/update APIs.

### 3.2. Shard key prefix only

~~~javascript
db.orders.find({ tenantId: "t-01" })
~~~

A filter on the `tenantId` prefix helps `mongos` identify **relevant ranges** and prune shards that do not hold them. However, **a single shard is not guaranteed**: chunks for the same tenant may span multiple shards. Never assume "filtering by tenantId always targets a single shard."

### 3.3. Missing shard key

~~~javascript
db.orders.find({ status: "PAID" })
~~~

`status` is not part of the shard key. Without another routing mechanism proving which shards hold matching data, the query may be sent to **all relevant shards** — commonly called **scatter-gather**.

### 3.4. Mental routing table

| Query predicate | With shard key `{tenantId:1,orderId:1}` | Routing behavior |
|---|---|---|
| `tenantId=t-01, orderId=o-001` | Full equality | Usually targets the shard holding the key |
| `tenantId=t-01` | Prefix equality | May hit one or multiple shards depending on chunk placement |
| `tenantId=t-01, orderId>{$gt:o-050}` | Range with prefix | Shards holding relevant ranges |
| `orderId=o-001` | Leading field omitted | May scatter across multiple shards |
| `status=PAID` | No shard key | Usually scatter-gather |
| No `$match` | Unfiltered | Usually full distributed collection scan |

**Principle:** determine **how many shards are touched** before asking which index a query uses. A query performing a fast IXSCAN on each shard can still incur high total network/merge overhead if broadcast to many shards.

## 4. Ranged vs. hashed shard keys: analytics trade-offs

MongoDB supports ranged and hashed shard keys (along with version-specific variants/capabilities).

### 4.1. Ranged shard key

~~~javascript
{ tenantId: 1, orderId: 1 }
~~~

Potential advantages include:

- Filters on tenant prefix and orderId range can route to relevant ranges.
- Certain sort/range queries on the shard key benefit from key ordering.
- Easy to reason about based on key order.

Disadvantages:

- If `orderId` increases monotonically or one tenant generates massive traffic, the active write range can become a **hot range**.
- A large tenant can span many chunks/shards; filtering by tenant alone does not guarantee one shard.
- Selectivity and balance depend on tenant cardinality/distribution, not just the number of fields.

### 4.2. Hashed shard key

~~~javascript
{ orderId: "hashed" }
~~~

Hashing scatters sequentially increasing key values by mapping them into a hash space. Equality lookups on the hashed key can still route efficiently. However, ranges over the **original `orderId` values** no longer correspond directly to hash order, so range queries may need to read multiple shards.

### 4.3. Hashing only tenantId may not split load well

~~~javascript
{ tenantId: "hashed" }
~~~

If there are only a few huge tenants and every order for a tenant carries the same `tenantId`, that tenant's hash remains **constant**. One very hot tenant can concentrate on a single key range/shard regardless of cluster shard count. Always analyze cardinality and workload skew.

### 4.4. Choose the shard key based on workload

Questions to answer:

1. Do APIs usually query by tenant + orderId, by date, or analyze across all tenants?
2. Is write traffic concentrated at the upper range of an increasing key?
3. Does a large tenant need to be spread across multiple shards?
4. Do queries frequently join by customerId or productId?
5. Is cluster-wide uniqueness required for a business key?
6. Is the shard key immutable/stable or updated often?
7. Is there a resharding plan if the workload shifts?

No single shard key is simultaneously optimal for **all** point lookups, range queries, joins, analytics, and write distribution.

## 5. Preparing the sharded collection lab

**Prerequisites:** connect `mongosh` to a `mongos` of a **sharded cluster lab** with administrative privileges to shard collections and create indexes. Do **not** run commands in this section on production, as sharding/index changes have lasting impact. Do not use lab timings to evaluate real-world speed: small datasets may reside entirely on one shard without showing distributed costs.

### 5.1. Create the database and orders

~~~javascript
use sharding_analytics_lab

db.createCollection("orders")

// Index supporting the shard key; additional indexes can match the workload.
db.orders.createIndex(
  { tenantId: 1, orderId: 1 },
  { name: "idx_tenant_order" }
)

// Run through mongos in the lab once collection/database qualify.
sh.shardCollection(
  "sharding_analytics_lab.orders",
  { tenantId: 1, orderId: 1 }
)
~~~

This illustrates shard key setup. Depending on version, collection state, existing indexes/unique constraints, and permissions, `sh.shardCollection` may require different preparation. Never force sharding by ignoring metadata errors or altering unique indexes on production data.

### 5.2. Orders dataset

~~~javascript
db.orders.insertMany([
  {
    _id: "t01-o001", tenantId: "t-01", orderId: "o-001",
    customerId: "c-01", status: "PAID", region: "HCM",
    amount: NumberDecimal("120"),
    createdAt: ISODate("2026-06-01T08:00:00Z")
  },
  {
    _id: "t01-o002", tenantId: "t-01", orderId: "o-002",
    customerId: "c-02", status: "PAID", region: "HN",
    amount: NumberDecimal("80"),
    createdAt: ISODate("2026-06-02T08:00:00Z")
  },
  {
    _id: "t01-o003", tenantId: "t-01", orderId: "o-003",
    customerId: "c-01", status: "CREATED", region: "HCM",
    amount: NumberDecimal("60"),
    createdAt: ISODate("2026-06-03T08:00:00Z")
  },
  {
    _id: "t01-o004", tenantId: "t-01", orderId: "o-004",
    customerId: "c-03", status: "PAID", region: "DN",
    amount: NumberDecimal("150"),
    createdAt: ISODate("2026-06-04T08:00:00Z")
  },
  {
    _id: "t02-o005", tenantId: "t-02", orderId: "o-005",
    customerId: "c-01", status: "PAID", region: "HCM",
    amount: NumberDecimal("200"),
    createdAt: ISODate("2026-06-01T09:00:00Z")
  },
  {
    _id: "t02-o006", tenantId: "t-02", orderId: "o-006",
    customerId: "c-04", status: "REFUNDED", region: "HN",
    amount: NumberDecimal("75"),
    createdAt: ISODate("2026-06-02T09:00:00Z")
  },
  {
    _id: "t02-o007", tenantId: "t-02", orderId: "o-007",
    customerId: "c-04", status: "PAID", region: "DN",
    amount: NumberDecimal("175"),
    createdAt: ISODate("2026-06-03T09:00:00Z")
  },
  {
    _id: "t02-o008", tenantId: "t-02", orderId: "o-008",
    customerId: "c-05", status: "PAID", region: "HCM",
    amount: NumberDecimal("50"),
    createdAt: ISODate("2026-06-04T09:00:00Z")
  },
  {
    _id: "t03-o009", tenantId: "t-03", orderId: "o-009",
    customerId: "c-11", status: "PAID", region: "HN",
    amount: NumberDecimal("300"),
    createdAt: ISODate("2026-06-01T10:00:00Z")
  },
  {
    _id: "t03-o010", tenantId: "t-03", orderId: "o-010",
    customerId: "c-11", status: "CREATED", region: "DN",
    amount: NumberDecimal("90"),
    createdAt: ISODate("2026-06-02T10:00:00Z")
  },
  {
    _id: "t03-o011", tenantId: "t-03", orderId: "o-011",
    customerId: "c-12", status: "PAID", region: "HCM",
    amount: NumberDecimal("40"),
    createdAt: ISODate("2026-06-03T10:00:00Z")
  },
  {
    _id: "t03-o012", tenantId: "t-03", orderId: "o-012",
    customerId: "c-13", status: "PAID", region: "DN",
    amount: NumberDecimal("110"),
    createdAt: ISODate("2026-06-04T10:00:00Z")
  }
])
~~~

Insert only once into an empty lab database. Re-running with the same `_id` triggers duplicate key errors. Verify:

~~~javascript
db.orders.countDocuments({})                // 12
db.orders.countDocuments({ status: "PAID" }) // 9
~~~

Total **PAID** revenue (excluding CREATED/REFUNDED) in the lab dataset:

| Tenant | PAID orders | Total `amount` |
|---|---:|---:|
| `t-01` | 3 | 350 |
| `t-02` | 3 | 425 |
| `t-03` | 3 | 450 |
| **Total** | **9** | **1,225** |

This is the baseline to verify aggregations produce **logically correct results** regardless of whether data sits on one or multiple shards.

### 5.3. Preparing small data for joins

~~~javascript
db.createCollection("orderLines")
db.orderLines.createIndex(
  { tenantId: 1, orderId: 1 },
  { name: "idx_lines_tenant_order" }
)

// In the lab you can shard orderLines as well.
sh.shardCollection(
  "sharding_analytics_lab.orderLines",
  { tenantId: 1, orderId: 1 }
)

db.orderLines.insertMany([
  { _id: "l-01", tenantId: "t-01", orderId: "o-001", sku: "A", qty: 2 },
  { _id: "l-02", tenantId: "t-01", orderId: "o-001", sku: "B", qty: 1 },
  { _id: "l-03", tenantId: "t-01", orderId: "o-002", sku: "A", qty: 1 },
  { _id: "l-04", tenantId: "t-02", orderId: "o-005", sku: "C", qty: 4 },
  { _id: "l-05", tenantId: "t-02", orderId: "o-005", sku: "D", qty: 1 },
  { _id: "l-06", tenantId: "t-03", orderId: "o-009", sku: "A", qty: 3 }
])
~~~

There is no guarantee that `orders` and `orderLines` sharing the same shard-key pattern will have **the same chunk placement on the same shards**; each has independent metadata/distribution. Avoid assuming that matching shard keys makes joins local to a single shard.

## 6. Aggregation can run in two parts: shard and merger

On an unsharded collection, a pipeline is typically explained as a sequence of stages reading and transforming data in one place. For a sharded collection, `mongos` can **split the pipeline** into:

- **Shards part**: reads local data and applies stages that can run distributed.
- **Merger part**: gathers and finalizes results across data from the shards.

~~~mermaid
flowchart TD
    Query["aggregate on orders"] --> Router["mongos"]
    Router --> A["Shard A: match + partial group"]
    Router --> B["Shard B: match + partial group"]
    Router --> C["Shard C: match + partial group"]
    A --> Merge["Merger: finalize group / sort"]
    B --> Merge
    C --> Merge
    Merge --> Result["Cluster-wide result"]
~~~

**Not every pipeline splits at the same point.** The optimizer decides based on stages, indexes, shard key, version, and stage requirements. Merging may occur on `mongos` or a designated shard/execution location; do not assume all raw data is always streamed back to the router for every stage.

### 6.1. Why is a merge step needed?

A revenue summation:

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: "$tenantId",
      revenue: { $sum: "$amount" }
    }
  }
])
~~~

If `t-01` has 100 PAID orders on Shard A and 80 PAID orders on Shard B, a local `t-01` group on Shard A is **not** the cluster-wide revenue for that tenant. Matching partial results from every shard holding matching documents must be merged.

### 6.2. Streaming vs. blocking stages

Some stages can run document by document, whereas stages like global `$sort` or `$group` often require exchanging/collecting results. On a sharded cluster, costs may include:

~~~text
T_total ≈ work on shards
        + network transfer
        + merge/finalize
        + coordination/queueing
~~~

This is only a **mental model**, not a latency formula. Queries can execute shard phases in parallel, so do not mechanically sum each shard's time sequentially.

## 7. Early `$match` reduces shards touched and network bytes

Compare two pipelines:

~~~javascript
// A: analyze all PAID orders.
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $group: { _id: "$tenantId", total: { $sum: "$amount" } } }
])

// B: analyze a specific order for one tenant.
db.orders.aggregate([
  { $match: { tenantId: "t-01", orderId: "o-001" } },
  { $project: { _id: 0, orderId: 1, amount: 1 } }
])
~~~

With shard key `{tenantId:1,orderId:1}`:

- A has no shard key predicate → typically inspects all shards.
- B has full shard key equality → can route narrowly to the shard holding the order.

### 7.1. Both shard targeting and indexes are needed

~~~javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_tenant_status_created" }
)
~~~

This index supports filtering/sorting by tenant/status/date on involved shards. However, it does not change the fact that a query filtering only by `tenantId` may still hit multiple shards if that tenant spans multiple distributed chunks.

### 7.2. Local filter vs. post-aggregation filter

~~~javascript
db.orders.aggregate([
  { $group: { _id: "$tenantId", total: { $sum: "$amount" } } },
  { $match: { _id: "t-01" } }
])
~~~

Logical semantics differ from filtering original documents if a pipeline performs complex transformations; the optimizer may push equivalent predicates earlier, but you should not rely on that in every case.

The clear way when analyzing a single tenant:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01" } },
  { $group: { _id: "$status", n: { $sum: 1 } } }
])
~~~

If a filter depends on a field computed inside `$group`, it cannot arbitrarily be pushed down to the base collection.

### 7.3. Tenant security is a separate condition

`$match: {tenantId:"t-01"}` narrows the query **only when `tenantId` matches authenticated permissions**. Never trust a client-supplied `tenantId` payload as an authorization control. Query targeting and authorization are two distinct layers.

## 8. `$group` on sharded collections: local vs. global computation

Lab pipeline:

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: "$tenantId",
      paidOrders: { $sum: 1 },
      revenue: { $sum: "$amount" }
    }
  },
  { $sort: { _id: 1 } }
])
~~~

Expected result:

~~~text
t-01 -> paidOrders=3, revenue=350
t-02 -> paidOrders=3, revenue=425
t-03 -> paidOrders=3, revenue=450
~~~

### 8.1. Partial aggregation optimization

When stages/accumulators allow, MongoDB can perform **partial aggregation on each shard**, then merge intermediate results. For example:

~~~text
Shard A: t-01 revenue 200, t-02 revenue 150
Shard B: t-01 revenue 150, t-02 revenue 275
Merger:  t-01 revenue 350, t-02 revenue 425
~~~

This can reduce data sent to the merger: instead of every order, shards send compact summaries. Still, **this optimization depends on the plan**; a pipeline containing non-distributable stages may have to send detailed documents to the merger.

### 8.2. Grouping by a shard key field does not guarantee single-shard execution

With compound shard key `{tenantId:1,orderId:1}`, a tenant may span multiple shards. Grouping by `tenantId` must combine each tenant's portions if present across multiple shards. Never infer "grouping by tenant is shard-local" just because tenant is the shard key prefix.

Conversely, grouping by the **entire shard key** may unlock dedicated optimizations because all documents with the same shard key value map to the same routing unit; still run `explain()` to inspect the actual plan.

### 8.3. Accumulators affect distributability

Sums, counts, mins, and maxes can usually be computed partially and combined. Operations needing global order or whole-set semantics—such as certain window calculations, distinct distributions, or pipelines with blocking stages—may require extra memory, network transfer, or finalize steps. Never assume every `$group` reduces to a simple local `$group` + merge `$group`.

## 9. `$sort`, `$limit`, and `$skip` require global ordering

Pipeline:

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $sort: { amount: -1, tenantId: 1, orderId: 1 } },
  { $limit: 3 },
  { $project: { _id: 0, tenantId: 1, orderId: 1, amount: 1 } }
])
~~~

Correct lab top 3:

~~~text
t-03 / o-009 -> 300
t-02 / o-005 -> 200
t-02 / o-007 -> 175
~~~

### 9.1. Wrong: taking top 3 from one shard as cluster top 3

Suppose:

~~~text
Shard A: 100, 90, 80
Shard B: 300, 200, 175
~~~

Global top 3 is 300, 200, 175, not Shard A's isolated result. In sharded aggregation, the optimizer can push **local top-k** down to each shard when safe, but a **merge sort / top-k** is still required to choose the global result.

### 9.2. Sort + limit optimization

MongoDB can coalesce `$sort + $limit` into top-k, or push a sufficient limit down to shards where appropriate. This shrinks the volume buffered/transferred, though each shard may still scan more than K documents if no supporting index exists.

### 9.3. Deep skip is not free

~~~javascript
db.orders.aggregate([
  { $sort: { createdAt: -1, tenantId: 1, orderId: 1 } },
  { $skip: 100000 },
  { $limit: 20 }
])
~~~

`$skip` must discard **the first 100,000 results in global order**. In some plans, the optimizer coordinates sorting with a `skip + limit` cap per shard, yet the volume scanned and merged can remain large. One shard cannot independently skip 100,000 of its own records and return the right cluster-wide page.

For deep feeds, consider **keyset pagination** using the sort key fields and a cursor condition; ensure filters, shard key, and indexes align.

### 9.4. Tie-breakers matter more when distributed

If sorting solely by `createdAt:-1`, multiple orders across shards can share identical timestamps. MongoDB **does not guarantee ordering among documents tied across the full sort key**, so pagination order may flip. Use a truly unique tie-breaker within scope, e.g., `tenantId + orderId` as defined by business rules:

~~~javascript
{ $sort: { createdAt: -1, tenantId: 1, orderId: 1 } }
~~~

Cursor conditions for keyset pagination must match every sort dimension precisely. If `orderId` is only unique **within a tenant**, never use it alone as a cluster-wide tie-breaker.

## 10. `$facet`, `$setWindowFields`, and advanced analytics

These stages are handy for dashboards, but can create bottlenecks when data from multiple shards must be merged.

### 10.1. `$facet`: multiple branches over the same input set

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $facet: {
      byTenant: [
        { $group: { _id: "$tenantId", revenue: { $sum: "$amount" } } },
        { $sort: { revenue: -1, _id: 1 } }
      ],
      topOrders: [
        { $sort: { amount: -1, tenantId: 1, orderId: 1 } },
        { $limit: 3 },
        { $project: { _id: 0, tenantId: 1, orderId: 1, amount: 1 } }
      ]
    }
  }
])
~~~

`$facet` produces **a single output document containing arrays**. It has its own memory limits (typically **100 MiB for documents processed in the facet**) and the final BSON result must still obey the **16 MiB/document** limit. `allowDiskUse` does not allow `$facet` to spill arbitrarily past its limits. Avoid stuffing huge item lists into a single facet document.

With sharding, understand what data is gathered before `$facet` and where it executes; `$facet` is not a technique that guarantees every sub-pipeline executes distributedly. Place `$match` early and cap outputs where business logic permits.

### 10.2. Window functions

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $setWindowFields: {
      partitionBy: "$tenantId",
      sortBy: { createdAt: 1, orderId: 1 },
      output: {
        runningRevenue: {
          $sum: "$amount",
          window: { documents: ["unbounded", "current"] }
        }
      }
    }
  }
])
~~~

Computing a running total per tenant requires **complete partitioning and ordering**. If a tenant spans multiple shards, each shard cannot compute an isolated running total and call it the tenant-wide result. The planner must coordinate according to stage and version capabilities, potentially incurring sort, memory, and network overhead.

### 10.3. Multi-dimensional grouping

A report grouping by `tenantId, region, date` can generate very high group counts, especially at minute/second granularity. Even with data sharded, the end of the pipeline can bottleneck at merging or network transfer. Reduce group cardinality, use pre-aggregation for critical dashboards, and measure footprint.

## 11. `$lookup` when the joined collection is also sharded

MongoDB supports `$lookup` against a sharded `from` collection in modern releases (for instance, from **MongoDB 5.1** onward). Check version constraints before using it on legacy clusters.

Suppose both `orders` and `orderLines` are sharded. A simple join solely on `orderId`:

~~~javascript
{
  $lookup: {
    from: "orderLines",
    localField: "orderId",
    foreignField: "orderId",
    as: "lines"
  }
}
~~~

may **fail to qualify for optimal routing** when the foreign shard key is `{tenantId,orderId}`, and will also mix tenants if `orderId` can collide across tenants.

### 11.1. Joining on both tenant + orderId

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01", orderId: "o-001" } },
  {
    $lookup: {
      from: "orderLines",
      let: {
        t: "$tenantId",
        o: "$orderId"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$t"] },
                { $eq: ["$orderId", "$$o"] }
              ]
            }
          }
        },
        {
          $project: {
            _id: 0,
            sku: 1,
            qty: 1
          }
        }
      ],
      as: "lines"
    }
  },
  {
    $project: {
      _id: 0,
      tenantId: 1,
      orderId: 1,
      lines: 1
    }
  }
])
~~~

In the lab, order `t-01/o-001` has two line items: SKU A qty 2 and SKU B qty 1.

### 11.2. Targeted foreign lookup is not guaranteed automatically

Having `$expr` compare against `let` variables in the foreign pipeline **does not automatically** turn every lookup into a single-shard, compound-indexed access. Behavior depends on:

- Whether the optimizer can deduce shard key equality and route appropriately.
- Foreign collection indexes, especially `tenantId + orderId`.
- Deterministic `let` variable values (not missing/null).
- Pipeline stages/expressions, collation, and index eligibility.
- Topology, shard key, and version.

Inspect `explain("executionStats")` and monitor **shards touched, foreign documents/keys examined, and output size**. Without effective routing, a lookup can fan out across multiple shards, multiplied by the number of local input documents.

### 11.3. Fan-out and output size

`$lookup` attaches an array to **each local document**. If an order has 100,000 lines, the combined document risks exceeding the 16 MiB limit even when lines reside across shards. Use foreign `$match`, `$project`, `$sort`, and `$limit` where appropriate, or query/paginate lines separately.

### 11.4. Co-location does not arise automatically from identical shard key patterns

Two collections sharing the same shard key pattern can have chunks allocated and balanced **independently**. Never deduce that an order document and orderLines documents for the same tenant/order live on the same shard. If a workload demands data locality, apply appropriate data modeling, zone/placement strategies, or architecture, and verify on the actual cluster.

## 12. `$merge` and `$out`: writing aggregation outputs in a sharded cluster

Read-only aggregations return a cursor, whereas ETL/reporting jobs often need to **write results** into a target collection.

### 12.1. `$merge`: upsert/update materialized results

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: "$tenantId",
      revenue: { $sum: "$amount" },
      paidOrders: { $sum: 1 }
    }
  },
  {
    $project: {
      _id: 0,
      tenantId: "$_id",
      reportType: { $literal: "paid_revenue" },
      revenue: 1,
      paidOrders: 1
    }
  },
  {
    $merge: {
      into: "tenantReports",
      on: ["tenantId", "reportType"],
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
])
~~~

For this example to work, **pre-create** `tenantReports` with a **unique index matching `on`**, checking existing conditions and version. Example **unsharded** target collection:

~~~javascript
db.createCollection("tenantReports")
db.tenantReports.createIndex(
  { tenantId: 1, reportType: 1 },
  { unique: true, name: "uq_tenant_report_type" }
)
~~~

In practice, **create the target collection and index before running `$merge`** rather than relying on implicit creation. `whenMatched:"replace"` requires keeping matching keys and accounting for `_id`; ensure output documents match the selected unique index.

### 12.2. Writing to a sharded collection

`$merge` can write to a sharded output collection under supported conditions, provided `on` fields and unique indexes obey **shard key** constraints (typically requiring **all shard key fields** and associated uniqueness rules). Never shard `tenantReports` on `{tenantId, reportType}` and arbitrarily use `on:["reportType"]` — it lacks the identity/uniqueness constraints required for a sharded target.

### 12.3. `$out` is not a clone of `$merge`

`$out` writes pipeline output into a destination collection with replacement semantics and carries distinct DDL/target restrictions. Notably, **`$out` cannot output directly to an existing sharded collection as an arbitrary replacement** under MongoDB support rules. It can also impact index/metadata workflows and concurrency on the target collection.

Never pick `$out` just to "avoid writing `on`" when the destination is sharded or readers require uninterrupted stability.

### 12.4. Neither `$merge` nor `$out` works inside transactions

Both output stages are disallowed inside multi-document transactions. If you need consistent reporting:

- Read input data using an appropriate cutoff/version/snapshot.
- Materialize results outside a transaction.
- Verify completion and flip `activeReportVersion` via a small atomic update.
- Design retries/idempotency since ETL pipelines can fail midway.

### 12.5. Writing aggregation output does not automatically guarantee a job-wide snapshot

A long-running aggregation executing alongside concurrent writers observes data according to the active read concern semantics. If the requirement is "exact revenue as of 00:00 UTC," define an explicit cutoff, payment status rules, and consistent read semantics rather than simply appending `$merge`.

## 13. Indexes on sharded collections: routing and local lookup are distinct steps

Conceptually, a query involves two phases:

1. **The router locates relevant shards** via shard-key metadata.
2. **On each shard**, the query planner chooses index scans/collection scans and subsequent stages.

Example:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1,
    orderId: 1
  },
  { name: "idx_tenant_status_date_order" }
)
~~~

This index helps list PAID orders for a tenant by date. However:

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $sort: { createdAt: -1, orderId: 1 } },
  { $limit: 20 }
])
~~~

has no shard-key filter, so it may scatter across multiple shards even though each shard has a suitable index on `status/createdAt`. Conversely, a query targeted to a single shard can still hit a COLLSCAN if no local index supports its predicate.

### 13.1. One index does not help every pipeline equally

| Pipeline | Factors to examine |
|---|---|
| `$match` full shard key | Narrow routing; shard key index helps |
| `$match` tenant only | May hit multiple ranges/shards; needs secondary index for status/date if filtered |
| `$match` status only | May scatter; index on status cuts local reads but not shard count |
| `$group` by tenant | Can partial group then merge; shard key does not skip global merge by default |
| `$sort` on computed field | Index on base document may not apply |
| `$lookup` to sharded foreign | Inspect foreign shard key, foreign index, and shards touched |

### 13.2. Unique indexes in sharded collections

MongoDB imposes constraints on **unique indexes in sharded collections**: generally, uniqueness is supported when the **shard key is a prefix** of the index, subject to version-specific exceptions/rules. The `_id` index still exists, but if `_id` is not the shard key, cluster-wide uniqueness semantics must be carefully understood; do not assume arbitrary `_id` values are globally enforced across every sharded configuration.

Example business key unique per tenant/order:

~~~javascript
{ tenantId: 1, orderId: 1 }
~~~

is an eligible candidate when it also aligns with the collection's shard key/unique rules. Do not rely on `orderId` alone if order IDs are only unique per tenant.

### 13.3. Index builds have operational impact

Creating an index on a sharded collection runs across all shards/replica sets holding data; it increases CPU, I/O, disk, and replication load. Plan rollouts/migrations, verify index consistency across shards, and measure impact on transactions and balancing.

## 14. `explain()` for aggregations on sharded clusters

Query:

~~~javascript
db.orders.explain("executionStats").aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: "$tenantId",
      revenue: { $sum: "$amount" }
    }
  },
  { $sort: { revenue: -1, _id: 1 } },
  { $limit: 3 }
])
~~~

Read `explain` as a **cluster-wide plan**, not just a single `winningPlan`.

### 14.1. Sections you may observe

Depending on version, classic engine/SBE, and optimizer, output may contain:

- `shards`, `splitPipeline`, `shardsPart`, and `mergerPart` sections or another representation of distributed execution.
- `SHARDING_FILTER` / routing-related stages in some plans.
- `IXSCAN`, `COLLSCAN`, and `FETCH` on individual shards.
- `$mergeCursors`, merge sort/group, or equivalent stages.
- Keys/documents examined, `nReturned`, and per-shard execution stats.
- Spill statistics when a blocking stage exceeds thresholds and spilling is enabled.

Never expect an identical stage sequence across every version. Optimizers reorder or fuse stages; rely on **metrics and behavior**.

### 14.2. Checklist for reading explain

1. How many shards participated?
2. Which shards had the highest `docsExamined`?
3. Did any shard send excessive intermediate documents to the merger?
4. Was `$match` actually applied before data exchange?
5. Did `$group` run partial aggregation on shards or pull full documents?
6. Did `$sort` use an index/top-k optimization or a blocking sort?
7. Is `totalKeysExamined`/`totalDocsExamined` disproportionately high compared to documents returned?
8. Was there disk spill or a merger bottleneck?
9. Is end-to-end latency dominated by the slowest shard, network, or merger?
10. With `$lookup`, did the foreign side hit multiple shards per local row?

### 14.3. Comparing targeted vs. scatter

~~~javascript
// Full shard key: typically targets a single shard.
db.orders.explain("executionStats").aggregate([
  { $match: { tenantId: "t-01", orderId: "o-001" } },
  { $project: { _id: 0, orderId: 1, amount: 1 } }
])

// Missing shard key: typically scatters.
db.orders.explain("executionStats").aggregate([
  { $match: { status: "PAID" } },
  { $group: { _id: "$region", n: { $sum: 1 } } }
])
~~~

On a tiny lab dataset, all documents may sit on one shard/chunk by chance, making differences unsuitable for benchmarking. Performance conclusions require representative distribution and workload.

## 15. Memory, network, and disk spill in distributed aggregations

Sharding parallelizes parts of query execution, yet many pipelines still have **resource convergence points**:

- Global `$sort` must merge order across shards.
- A `$group` with huge group cardinality can demand substantial RAM or disk.
- `$lookup` with high fan-out can build large arrays/results.
- `$facet` has per-stage/per-document limits.
- `$merge` must distribute writes to the destination collection.
- Every final output document remains bound by the **16 MiB BSON limit**.

### 15.1. `allowDiskUse`

~~~javascript
db.orders.aggregate(
  [
    { $match: { status: "PAID" } },
    { $group: { _id: "$customerId", total: { $sum: "$amount" } } },
    { $sort: { total: -1 } }
  ],
  { allowDiskUse: true }
)
~~~

`allowDiskUse` permits supported stages to spill temporary data to disk per version rules (defaults since MongoDB 6.0 are influenced by `allowDiskUseByDefault`). It is **not free**, does not force an index scan, does not lift the 16 MiB document limit, and does not let stages like `$facet` spill without bound.

### 15.2. Network bytes are also a resource

A query returning 20,000 groups from each of 10 shards transfers substantial intermediate volume to the merger even if every shard's CPU is fast. Track bytes transferred/network throughput, not just query CPU.

### 15.3. The slowest shard bounds the pipeline

If the merger awaits results from every shard, a single shard missing an index or experiencing disk saturation can raise p95/p99 latency for the cluster-wide aggregation. A cluster with "9 healthy shards and 1 overloaded shard" still produces slow scatter-gather reports.

## 16. Transactions on sharded clusters: single-shard vs. cross-shard

MongoDB has supported multi-document transactions on replica sets since 4.0 and **distributed transactions on sharded clusters since 4.2** under deployment conditions. A transaction on a sharded cluster may:

1. Touch documents on only a single shard.
2. Touch documents across multiple shards.

Both preserve atomicity semantics, but their **coordination cost differs**.

### 16.1. Single-shard transaction

~~~text
Business request:
  update order + write ledger
Documents reside on the same shard
=> Commit within a single shard replica set
~~~

Do not assume a single tenant always equals a single shard. One tenant can span chunks; different collections also do not share placement by default.

### 16.2. Cross-shard distributed transaction

~~~mermaid
sequenceDiagram
    participant App as Application
    participant Router as mongos
    participant S1 as Shard A
    participant S2 as Shard B
    App->>Router: Start transaction (session)
    Router->>S1: Write order
    Router->>S2: Write inventory
    Router->>S1: Write ledger if routed to A
    App->>Router: commitTransaction
    Router->>S1: Coordinate commit decision
    Router->>S2: Coordinate commit decision
    S1-->>Router: Participant outcome
    S2-->>Router: Participant outcome
    Router-->>App: Commit outcome (may timeout/be unknown)
~~~

This diagram simplifies the distributed commit process: the system uses coordination protocols/resources accordingly rather than participants always replying strictly in the sequence drawn. When a transaction spans shards, it adds network hops, metadata routing, commit coordination, per-participant failure possibilities, and snapshot/lock retention overhead.

### 16.3. "Cross-shard" does not mean "non-atomic"

When distributed transactions are supported and commit successfully under applicable rules, MongoDB writes inside the transaction still guarantee **all-or-nothing** semantics. The trade-off is overhead, latency, abort risk, and recovery complexity — **not** having to accept partial commits as normal.

### 16.4. Not every workflow needs a distributed transaction

If you only need to update an order's total and status within the same document, a single-document atomic update remains simpler. If a workflow spans MongoDB + a payment gateway + email, a distributed MongoDB transaction **cannot** span external systems. Use outbox/idempotency/saga patterns.

## 17. Data modeling to minimize cross-shard transactions

Consider a stock reservation flow:

~~~text
1. Create order
2. Decrement inventory
3. Write request ledger
4. Emit OrderCreated event
~~~

If `orders`, `inventory`, and `requestLog` live in three sharded collections, their documents may sit on **three different shards**. Including `tenantId` in all three shard keys does not guarantee they land on the same shard.

### 17.1. Co-location is a design goal, not a default

To reduce cross-shard transactions:

- Identify which documents truly need atomic co-updates.
- If invariants belong within one document, embed within bounded limits.
- If multiple documents are needed, design shard keys and placement strategies based on **actual routing/range affinity**, not matching key names.
- Measure shards touched per transaction, not only total document count.
- Avoid a global counter document updated concurrently by every tenant.

### 17.2. Trade-off between locality and hot shards

Funneling all orders of a huge tenant onto one shard may reduce certain cross-shard operations, yet creates a **hot tenant / hot shard**. Spreading that tenant's orders across shards increases throughput, while requiring cross-shard coordination/merges for tenant-wide reports or transactions.

There is no universally best layout: choose based on access patterns and scalability goals, then validate via measurement.

### 17.3. Using a request ledger to guard retries

Even when a transaction is atomic, an HTTP request may be retried after committing if the response is lost. A ledger with a unique constraint on **business scope** such as `{tenantId,requestId}` identifies the intent and replays the prior outcome. On a sharded collection, the unique index must remain compatible with the shard key.

## 18. Preparing collections for the transaction lab

On `mongos` in the lab cluster:

~~~javascript
use sharding_analytics_lab

db.createCollection("inventory")
db.inventory.createIndex(
  { tenantId: 1, sku: 1 },
  { name: "idx_inventory_tenant_sku" }
)
sh.shardCollection(
  "sharding_analytics_lab.inventory",
  { tenantId: 1, sku: 1 }
)

db.createCollection("requestLog")
db.requestLog.createIndex(
  { tenantId: 1, requestId: 1 },
  { unique: true, name: "uq_request_scope" }
)
sh.shardCollection(
  "sharding_analytics_lab.requestLog",
  { tenantId: 1, requestId: 1 }
)

db.inventory.insertMany([
  { _id: "inv-t01-A", tenantId: "t-01", sku: "A", available: 10, reserved: 0 },
  { _id: "inv-t02-A", tenantId: "t-02", sku: "A", available: 7, reserved: 0 },
  { _id: "inv-t03-B", tenantId: "t-03", sku: "B", available: 20, reserved: 0 }
])
~~~

In a real cluster, sharding a collection that already has unique indexes must satisfy MongoDB's shard-key/uniqueness rules. When enforcing uniqueness on `{tenantId,requestId}`, shard key `{tenantId,requestId}` is prefix-compatible, though you must still check version, collection state, existing data, and sharding restrictions beforehand.

### 18.1. Why should setup happen outside transactions?

A business transaction is not the place to create collections, indexes, and shard metadata. Certain DDL operations are allowed inside transactions from specific releases under strict constraints, especially on multi-shard writes. Pre-creating schemas via migrations keeps runtime transactions short and reduces lock contention.

### 18.2. Do not try to force multi-shard distribution in the tiny lab

Three inventory documents and twelve orders are far too small to force chunk splitting and distribution across multiple shards. The code demonstrates **semantics of transactions that may be cross-shard**, not proof that a particular run spanned shards. Confirm participating shards using metadata tools and representative data volumes.

## 19. Node.js Driver: transaction with shard-key-aware routing

Example intent: "create a new order and reserve one unit of SKU" with an authenticated `tenantId`. Calls must pass a `session` and filters containing the **full shard key** where appropriate for routing.

~~~javascript
import { MongoClient } from "mongodb";

const client = new MongoClient(process.env.MONGODB_URI, {
  serverSelectionTimeoutMS: 5000
});

await client.connect();

const database = client.db("sharding_analytics_lab");
const orders = database.collection("orders");
const inventory = database.collection("inventory");
const requestLog = database.collection("requestLog");

async function createOrderAndReserve({
  tenantId, requestId, orderId, sku, qty
}) {
  // tenantId must come from auth context; never trust client-supplied values.
  if (!tenantId || !requestId || !orderId || !sku ||
      !Number.isSafeInteger(qty) || qty <= 0 || qty > 100) {
    throw new Error("INVALID_INPUT");
  }

  // With a fixed payload, serialize keys deterministically;
  // production needs a canonical fingerprint/hash for complex payloads.
  const fingerprint = JSON.stringify({ orderId, sku, qty });
  const session = client.startSession();

  try {
    return await session.withTransaction(async () => {
      // One tenant + requestId may execute only a single business intent.
      const previous = await requestLog.findOne(
        { tenantId, requestId },
        { session }
      );

      if (previous) {
        if (previous.fingerprint !== fingerprint) {
          throw new Error("IDEMPOTENCY_KEY_REUSED");
        }
        return previous.result;
      }

      // Unique compound index acts as the final guard against concurrent requests.
      await requestLog.insertOne({
        tenantId,
        requestId,
        fingerprint,
        state: "PROCESSING",
        createdAt: new Date()
      }, { session });

      // Equality on all shard key fields of inventory.
      const stock = await inventory.updateOne(
        {
          tenantId,
          sku,
          available: { $gte: qty }
        },
        {
          $inc: {
            available: -qty,
            reserved: qty
          }
        },
        { session }
      );

      if (stock.matchedCount !== 1) {
        // Rejection is a terminal business outcome under the lab contract.
        const result = { ok: false, code: "OUT_OF_STOCK", orderId };
        await requestLog.updateOne(
          { tenantId, requestId },
          { $set: { state: "COMPLETED", result } },
          { session }
        );
        return result;
      }

      // Write full shard key fields for orders.
      await orders.insertOne({
        tenantId,
        orderId,
        status: "CREATED",
        sku,
        qty,
        createdAt: new Date()
      }, { session });

      const result = { ok: true, code: "CREATED", orderId };
      await requestLog.updateOne(
        { tenantId, requestId },
        { $set: { state: "COMPLETED", result } },
        { session }
      );
      return result;
    }, {
      readPreference: "primary",
      readConcern: { level: "snapshot" },
      writeConcern: { w: "majority" },
      maxCommitTimeMS: 10000
    });
  } finally {
    await session.endSession();
  }
}

// Example:
// await createOrderAndReserve({
//   tenantId: "t-01",
//   requestId: "reserve-1001",
//   orderId: "o-1001",
//   sku: "A",
//   qty: 1
// });

// Close client on shutdown: await client.close();
~~~

### 19.1. What matters more than lines of code

- `requestLog`, `inventory`, and `orders` may live on different shards; the transaction still coordinates atomically on supported topologies.
- The `inventory` filter uses equality on `tenantId + sku`, matching that collection's shard key.
- `orders.insertOne` supplies `tenantId + orderId`, providing full routing keys.
- Unique index `requestLog.{tenantId,requestId}` blocks two concurrent inserts for the same intent.
- `withTransaction` may retry the callback on transient errors; never call payment/email APIs inside the callback.
- When stock is insufficient, storing `OUT_OF_STOCK` enables matching retries to replay deterministically per contract.
- `writeConcern:"majority"` is vital for commit durability, though shard health and latency must still be monitored.

### 19.2. Limitations of this example

This code is a **learning skeleton**, not a complete production API. Production code must add:

- True canonical fingerprinting, authorization, and input validation.
- Checking whether duplicate key errors occurred on `requestLog` **or** the business order key; never assume every E11000 means successful replay.
- Bounded retries/reconciliation when two concurrent requests race before the ledger record is visible as committed.
- Explicit handling of `UnknownTransactionCommitResult`; never assume every exception means the transaction aborted.
- Enforcing `orderId` and `_id` uniqueness rules on sharded collections; use business keys / shard-key-compatible unique indexes rather than trusting arbitrary `_id` values to be globally unique.
- Checking completed ledger entries when clients retry after dropped responses.
- Accurate monetary representation, reservation expiration, and stock release policies where applicable.

### 19.3. Do not turn every error into a retry

Insufficient `available` stock is a **business outcome**. If a transaction aborts due to a write conflict, retrying the transaction body makes sense. If commit outcome is unknown, retry commit or reconcile. If a shard key field is missing or an index check fails, **fix the query/schema** instead of retrying blindly.

## 20. Distributed commit, retries, and uncertain outcomes

### 20.1. `TransientTransactionError`

When a participant shard hits a write conflict, failover, or transient error, the transaction may abort with the `TransientTransactionError` label. Handling steps:

1. Abort or let the driver helper abort the current attempt.
2. Start a fresh transaction attempt.
3. Re-read data and re-evaluate business preconditions.
4. Re-execute writes for the same business intent.
5. Bound retries with deadline, backoff, and jitter.

Do not simply retry the last command on the last shard using an aborted snapshot. Decisions like "is stock still sufficient?" can change on retry.

### 20.2. `UnknownTransactionCommitResult`

A distributed commit may have succeeded while its response was lost:

~~~text
Client sends commit
Participant shards finish commit protocol
Router/driver loses response
Client does not know outcome
~~~

At this point, **never mint a new `requestId` and re-run the business operation**. Use driver/helper logic to retry **commit** on the same attempt while valid context remains; if retry budget expires or the connection drops, reconcile against the ledger. Not seeing the ledger on a stale secondary does not prove the transaction aborted.

### 20.3. Cross-request idempotency

Driver retryable writes do not merge two separate HTTP requests into one logical operation. Keep `requestId` stable across:

- HTTP client retries.
- Queue redeliveries.
- Service restarts.
- Shard primary failovers.
- Transaction body retries.
- Retry/reconciliation after unknown commit results.

### 20.4. Do not forget side effects outside MongoDB

A MongoDB transaction cannot roll back emails, payment gateways, or message brokers. Use the **transactional outbox** pattern:

~~~text
MongoDB Transaction:
  update order
  update inventory
  write requestLog
  write outbox event
Commit

Outbox relay:
  publish event at-least-once
Consumer:
  deduplicate by stable eventId
~~~

The outbox relay can still publish duplicates if it crashes after publishing but before marking SENT; consumers must be idempotent.

## 21. Transaction lifetime, cache, and network across multiple shards

Multi-document transactions have a bounded lifetime, typically defaulting to **60 seconds** via `transactionLifetimeLimitSeconds`. Distributed transactions incur additional network, routing, and coordination overhead across participant shards. Large transactions can hit:

- Lifetime exceeded.
- Write conflicts or lock acquisition timeouts.
- `TransactionTooLargeForCache` or WiredTiger cache pressure.
- Errors caused by topology/metadata/chunk migration changes.
- Commit timeouts / unknown commit results.
- BSON documents exceeding 16 MiB.
- Operations or commands disallowed inside transactions.

### 21.1. 16 MiB per document vs. total transaction size

The 16 MiB limit applies to **each BSON document**. In modern MongoDB releases, a transaction can emit **multiple oplog entries**; do not equate "16 MiB per oplog entry" with "total transaction size must be under 16 MiB." Nonetheless, cache, lifetime, and physical resources still cap practical transaction size.

### 21.2. Lock wait and commit timeouts

`maxTransactionLockRequestTimeoutMillis` governs lock wait duration; `maxCommitTimeMS` in driver options bounds commit execution. Neither overrides `transactionLifetimeLimitSeconds`, and neither turns transactions into multi-hour batch jobs.

### 21.3. Shrink cross-shard scope before raising timeouts

If a transaction updates 100,000 orders across 15 shards, increasing timeouts merely holds snapshots/locks longer and makes retries more expensive. Instead:

- Use selective predicates and indexes to touch only necessary documents.
- Keep only essential invariants inside the transaction.
- Split into checkpointed batches when full-batch atomicity is unnecessary.
- Use versioned cutovers when readers need to see a complete dataset.
- Reduce involved collections/shards where feasible.

## 22. Restricted operations in sharded transactions

Some commands run normally outside transactions but face restrictions inside them.

### 22.1. `$out` and `$merge`

Neither aggregation output stage may be used **inside a multi-document transaction**. If a transaction must update a small summary, use explicit CRUD statements on a pre-existing collection; to materialize large reports, run jobs outside transactions with versioning/idempotency.

### 22.2. DDL and implicit collection creation

MongoDB supports limited collection/index creation inside transactions from specific releases, subject to **strict restrictions**. A transaction writing across multiple shards cannot generally be assumed to support **implicitly creating collections** while writing across shards. Pre-creating collections and indexes **before runtime** via migrations is far more predictable.

### 22.3. Transactions require primary read preference

Transactions must obey primary read preference rules. Do not pass `readPreference:"secondary"` hoping to read reporting data inside a distributed transaction that also writes. All operations must share the **same session** and valid transaction options.

### 22.4. Do not run parallel operations arbitrarily within one transaction

In the Node.js Driver, **parallel operations on the same transaction are not supported**. Avoid:

~~~javascript
await session.withTransaction(async () => {
  await Promise.all([
    orders.updateOne(filterA, updateA, { session }),
    inventory.updateOne(filterB, updateB, { session })
  ]);
});
~~~

Execute operations sequentially with explicit `matchedCount` checks and clear error handling.

### 22.5. Special namespaces and administrative commands

Do not assume system namespaces or administrative commands such as `shardCollection`, `moveChunk`, index/collection DDL, `replSetReconfig`, or `explain` are valid inside transactions. Administrative/sharding tasks belong in operational workflows **outside business transactions**, subject to release support.

## 23. How do chunk migrations and the balancer affect workloads?

A sharded collection is partitioned into **ranges/chunks** by shard key. When distribution becomes uneven or topology changes, the balancer/placement services can orchestrate migrations between shards.

### 23.1. Migration is not a simple file copy

Moving a chunk/range involves:

- Copying range data to the destination shard.
- Catching up concurrent modifications occurring during migration.
- Updating ownership/routing metadata.
- Cleaning up old/orphan documents per protocol.

Exact steps and locking/coordination mechanics vary by version; never trigger manual chunk migrations in production just because a shard looks busy.

### 23.2. Impact on aggregations

As routing metadata updates, `mongos` refreshes its routing table. Large multi-shard queries may incur extra metadata/network overhead or follow server consistency/routing safeguards. Never double-count documents just because a chunk is migrating: the server enforces ownership/sharding filtering; if results appear wrong, investigate the root cause rather than adding ad-hoc client deduplication.

### 23.3. Impact on transactions

Migrations and transactions touching overlapping data/metadata ranges can cause contention, lock waits, or placement-related transient errors requiring transaction retries. **Keeping transactions short** lowers collision odds and eases balancing.

### 23.4. The balancer does not fix every form of skew

One shard might hold lots of bytes yet sit idle, while another holds little data yet absorbs 70% of writes due to a concentrated shard key. Balancing **storage/chunks** does not equal balancing **CPU/QPS**. When one key value is extremely hot, chunks cannot meaningfully split it or all writes hit a single range—requiring a **data model or shard key change**.

## 24. Hot shards, data skew, and "adding shards didn't make it faster"

Suppose a cluster has 5 shards, but 80% of order writes have `tenantId="t-major"` under shard key `{tenantId:"hashed"}`. Every document for that tenant hashes to the exact same key value; hashing will never split that tenant's 80% load across 5 shards.

### 24.1. Types of skew

| Skew type | Example | Consequence |
|---|---|---|
| Storage skew | One shard stores most bytes | Disk pressure, difficult maintenance |
| Read skew | API queries mainly one tenant/range | Hot read shard |
| Write skew | Monotonic inserts pile onto tail range | Hot primary shard |
| Computation skew | Aggregation group hits one massive key | Shard or merger exhausts RAM/CPU |
| Join skew | One customer has millions of order lines | `$lookup`/`$unwind` explosion |
| Network skew | One shard has poor RTT/throughput | Drags down global query p99 |

### 24.2. Pick the shard key for real query patterns

A shard key that spreads writes yet forces periodic reports to scatter may still be an acceptable trade-off if write throughput is paramount. Conversely, optimizing for every report while funneling all inserts onto one shard can bottleneck the entire system.

### 24.3. Separate OLTP and analytics when necessary

For heavy reporting, sometimes **an OLTP sharded cluster should not carry all BI workloads**. Consider:

- Materialized summary collections.
- Incremental aggregation via change streams or an outbox.
- ETL into a dedicated warehouse/OLAP engine.
- Scheduled reporting windows, resource quotas, and pre-aggregation.
- Secondary reads via read preferences when consistency permits, while watching each shard replica set's lag and capacity.

Not every dashboard requires a new architecture; measure first and align solutions with SLOs.

## 25. Resharding and changing the shard key

An initially chosen shard key can become obsolete as tenant counts, query patterns, or write volumes evolve. MongoDB supports **resharding collections** in modern releases (e.g., MongoDB 5.0+ with refinements and changed limits across newer releases).

### 25.1. Why reshard?

- The old shard key yields skewed distribution.
- A hot tenant occupies a single indivisible range/value.
- Dominant queries shifted from `tenantId + orderId` to `tenantId + createdAt` or another pattern.
- Adding shards/zones requires a new placement strategy.

### 25.2. Resharding is a major operational change

Resharding may require copying and reorganizing massive volumes of data, catching up concurrent changes, and performing a metadata cutover. Cluster resources and throughput can be impacted; verify version limits, disk headroom, balancer state, backups, and rollback/abort options.

### 25.3. Never change a shard key just to rescue one query

Changing the shard key affects **every** query, write, unique constraint, and data distribution. If only one end-of-day report scans the collection, adding a materialized summary or offloading to an analytics store carries far less risk than resharding terabytes of live data.

### 25.4. Recommended rollout workflow

1. Capture baseline query routing, chunk distribution, hot keys, and application SLOs.
2. Model candidate shard keys against representative data and distributions.
3. Verify unique indexes and compatibility.
4. Estimate disk, network, migration, and cutover costs.
5. Rehearse resharding on an equivalent staging environment.
6. Prepare monitoring metrics, rollback/recovery plans, and a maintenance window.
7. Execute using the official runbook for your server version/managed provider.
8. Validate targeted queries, aggregation plans, and transaction paths post-cutover.

## 26. Zone sharding, locality, and data policies

Zone sharding lets you map **shard key ranges** to designated shard groups/zones to steer placement by policy. This is not equivalent to replica set member tags.

### 26.1. Zones vs. replica set read tags

- **Zone sharding:** controls **data placement** of shard-key ranges across shards.
- **Replica set member tags / read preference:** selects **replica set members** to serve reads by purpose/region.

Assigning Asian tenants to a zone can aid data locality if chunk placement and workloads match, though global aggregations must still gather data across zones. Never use read preference tags as a substitute for shard-key placement.

### 26.2. Compliance and residency

Zone placement helps support regional placement goals, but does not by itself satisfy every legal requirement: backups, logs, replication members, copies, config metadata, and network transit must also be governed. Never assume a `region` tag alone proves strict data residency.

### 26.3. Cross-zone transactions

If a transaction spans shards across multiple zones/regions, network RTT, partition risk, and commit latency can be significant. Keeping most transactions local to one zone improves latency, though cross-region workflows remain challenging. Measure empirically.

## 27. Read preference and read concern in sharded clusters

Each shard is normally a replica set; queries can specify a read preference to pick members, yet **shard routing** and **replica set member selection** remain two separate layers.

Example:

~~~text
Query without shard key:
  mongos sends to Shard A, B, C
  each shard selects a member to serve the read per readPreference
~~~

Using `secondary` mode does not turn a scatter query into a targeted one. It only shifts read execution from primary to secondary within each shard where supported.

### 27.1. Read concern local/majority/snapshot

- `local` reflects a node's local state per allowed semantics; it may be stale or rolled back under certain failures.
- `majority` requires data to be majority-committed, though **it does not mean latest** when reading from a secondary.
- `snapshot` can provide a more consistent point-in-time view across supported commands/transactions; conditions vary by version and topology.

Never stitch together a multi-shard report and claim "this is definitely an exact snapshot at 00:00 UTC" without choosing appropriate read concerns and cutoffs.

### 27.2. Causal consistency and read-your-writes

A user who just created an order on Shard A's primary and immediately reads from a secondary may miss it due to replication lag. Causal sessions combined with appropriate majority read/write concerns can provide causal guarantees where supported, though they may **wait** for secondaries to catch up. For critical read-after-write flows, reading from the primary is usually more predictable.

### 27.3. Distributed transactions normally read from primary

Do not set a secondary read preference on transactions writing across shards. Transactions must adhere to driver/server requirements for primary reads, snapshot isolation, and commit concerns; configure separate read preferences for read-only analytical queries.

## 28. Operations: observing cluster, shards, and data distribution

In `mongosh` connected to the lab `mongos`, inspect:

~~~javascript
sh.status()
~~~

This displays an overview of sharded databases/collections, shards, and associated metadata depending on `mongosh`/server version. With admin privileges, list shards via:

~~~javascript
db.adminCommand({ listShards: 1 })
~~~

Inspect collection indexes and query plans:

~~~javascript
db.orders.getIndexes()

db.orders.explain("executionStats").aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  { $sort: { createdAt: -1, orderId: 1 } },
  { $limit: 20 }
])
~~~

### 28.1. Metrics you must track

| Operational area | Metrics / observations |
|---|---|
| Data distribution | Bytes/documents/chunks per shard, worst skew |
| Routing | Shards touched on critical queries |
| Queries | p95/p99 latency, docs/keys examined per shard |
| Merger | Bytes transferred, merge CPU/memory, spills |
| Hot keys | Read/write share by shard-key range/tenant |
| Replication | Lag, majority commit latency, elections per shard |
| Balancer | Migration duration, failures, backlog, resource overhead |
| Transactions | Duration, abort/retry counts by label, participants, commit latency |
| DDL | Index build status, lock waits, schema drift across shards |
| Storage | Disk/CPU/cache/network on every shard and config server |
| Availability | Router errors, shard unavailability, config metadata issues |

Not every metric exists under those exact field names inside MongoDB; several must be gathered via the profiler/diagnostic tools, cloud provider telemetry, driver command monitoring, or application instrumentation.

### 28.2. Distinguish "fast on a shard" from "fast end-to-end"

Each shard may finish in 20 ms, yet a query scattering to ten shards and merging 100 MB of data takes much longer overall. Measure from the **API/driver edge**, alongside per-shard breakdowns to locate bottlenecks.

### 28.3. Do not benchmark with tiny datasets

Twelve orders in the lab do not cause MongoDB to split/migrate chunks as in production. `explain` may validly show a single shard or COLLSCAN. The lab teaches semantics; benchmarking requires representative dataset sizes, client concurrency, key distributions, and topologies.

## 29. Backup, restore, and upgrades in sharded clusters

When data spans multiple shards, backups are no longer as simple as copying files from a single node:

- Shards accept writes at different wall-clock instants.
- Chunk/collection placement metadata resides on config servers.
- Distributed transactions may commit across shards.
- Balancer/migrations may alter placement while backups run.

### 29.1. Consistent backups

A cluster-consistent backup requires a **sharding-aware** strategy/tool capturing shard data alongside synchronized metadata/commit state. Never take independent uncoordinated snapshots of each shard at arbitrary times and expect restores to yield a consistent cluster.

### 29.2. Restore and business integrity

After restoring, verify:

- Expected collections and indexes exist, including shard keys and unique constraints.
- Chunk/zone metadata and router connections function properly.
- Business transactions are not left partially visible.
- Read/write APIs send valid shard-key filters.
- Reporting/materialized views may require replay or reconciliation.

### 29.3. Version and FCV upgrades

Aggregation features, transactions, resharding, and DDL depend on server versions and **Feature Compatibility Version**. During upgrades:

1. Check compatibility across drivers, `mongos`, config servers, and shards.
2. Follow the supported rolling upgrade sequence.
3. Update FCV only at the proper stage.
4. Watch for query planner and `explain` behavioral changes.
5. Re-run tests for transactions, retry labels, lookups, and output stages.

Never upgrade shards piecemeal and immediately invoke new features before the rest of the cluster reaches the supported version/FCV.

## 30. Change streams, ETL, and distributed data

Sharded clusters support change streams subject to version/topology requirements. Consumers can watch changes on a sharded collection or at an appropriate database/cluster scope.

### 30.1. Why are they beneficial for analytics?

Instead of running aggregations scanning billions of orders every minute, you can:

~~~text
Order CREATED / PAID / REFUNDED
  -> Change Stream or outbox
  -> Consumer updates tenant/daily summary
  -> Dashboard reads compact summary
~~~

Trade-offs:

- Requires resume tokens/checkpoints and recovery workflows if a consumer stops.
- Events may be redelivered during retries/restarts; consumers must be idempotent.
- Do not assume cluster-wide global ordering behaves like a single queue across all business events; design entity keys/ordering and consistency boundaries deliberately.
- On status transitions, avoid double-counting revenue or forgetting to subtract refunded revenue.

### 30.2. Outbox keeps business events consistent

When events must correspond strictly to database commits, write the outbox entry inside the same transaction as order/stock updates, then relay it post-commit. Change streams can tail outbox changes; consumers still deduplicate by `eventId`.

### 30.3. When is batch ETL still preferable?

End-of-day reports can rely on cutoffs/versions, run batch aggregations, write to a materialized collection, and publish the active version upon completion. Change streams do not automatically make every historical calculation effortless as streaming state.

## 31. Choosing strategies by use case

| Need | Recommended design | Caveat |
|---|---|---|
| Read one order by tenant + orderId | Full shard-key predicate, indexed lookup | Don't query `_id` alone if it lacks routing/uniqueness |
| Daily report across all tenants | Distributed aggregation or summary store | Scatter/merge/network can be costly |
| Top 20 orders cluster-wide | `$match → $sort → $limit` with tie-breaker | Global merge; needs indexes and plan checks |
| Top 20 orders for one tenant | Shard-key prefix filter + date index | Tenant may still span multiple shards |
| Join order with lines | Join both tenant + orderId, foreign index | Foreign lookup may scatter; watch fan-out |
| Total revenue per tenant | Partial group/final merge or materialized summary | Don't mistake local group for global |
| `$merge` into sharded summary | Shard-key-aware `on` + valid unique index | Output stage doesn't work with arbitrary keys |
| Replacement report | `$out` to supported target, versioned cutover | Cannot arbitrarily overwrite sharded collections |
| Reserve one SKU's stock | Conditional single-document atomic update | API retries still require idempotency |
| Order + inventory + ledger | Short transaction across shards if needed | Commit latency, retries/unknown outcome |
| Bulk import millions of docs | Checkpointed batches, idempotent upserts | Never wrap entire load in one giant transaction |
| Change shard key | Runbook-driven resharding | Resource cost, availability, unique constraints |
| Offload reads from primary | Secondary read preference per shard | Doesn't reduce shards touched; may be stale |
| Low-SLA dashboard | Incremental/materialized analytics | Design freshness and reconciliation |

## 32. Common pitfalls

| Pitfall | Consequence | Fix |
|---|---|---|
| Thinking sharding always makes aggregations faster | Scatter/merge can be slower | Measure query routing and plans |
| Filtering only on status/index without shard key | Many shards still queried | Add shard-key-aware filters where applicable |
| Assuming tenantId guarantees one shard | Tenant can span chunks/shards | Check placement metadata and `explain` |
| Hashing tenantId to "split a giant tenant" | Same tenant hashes to same key value | Pick a shard key with within-tenant distribution |
| Treating one shard's group sum as global total | Wrong totals | Global merge / final aggregation |
| Taking per-shard limit as global top N | Wrong top N | Let MongoDB merge sort/limit |
| Treating deep `$skip` as instant jump | Scans/merges many rows | Keyset pagination using sort key |
| Sorting without a unique tie-breaker | Unstable pagination across shards | Add scoped unique tie-breaker fields |
| Joining `$lookup` only by orderId when scoped per tenant | Cross-tenant mixups, heavy fan-out | Join on both tenant + orderId |
| Assuming matching shard-key patterns mean co-location | Chunk placement is independent | Verify actual placement |
| Using `$out` onto a sharded target | Unsupported behavior | Use compliant `$merge` or versioned reports |
| `$merge` missing shard key in `on` | Errors / broken uniqueness | Design output key and compatible unique index |
| Thinking cross-shard transactions aren't atomic | Misunderstanding transactions | Use supported distributed transactions |
| Thinking cross-shard transactions are free | Higher commit/network/abort overhead | Minimize shards touched and scope |
| Retrying timeouts with a fresh `requestId` | Risk of double-applying | Reconcile / keep stable idempotency key |
| Calling payment/email inside transaction callback | Duplicate external side effects | Outbox / external idempotency |
| Keeping a transaction open during long ETL | Hits lifetime/cache/lock limits | Checkpointed batches |
| Running DDL/sharding commands inside business transactions | Compatibility errors, contention | Pre-migrate outside runtime |
| Assuming balancing bytes balances QPS | Hot shard stays hot | Measure workload skew, consider resharding |
| Assuming secondary reads target a single shard | Scatter queries still scatter | Separate read preference from shard routing |
| Backing up each shard independently at different times | Cluster-inconsistent restores | Use sharding-aware consistent backups |
| Benchmarking performance with 12 documents | Unrepresentative of real clusters | Benchmark with realistic distributed datasets |

## 33. Comprehensive practice lab

Use the lab collections `orders`, `orderLines`, `inventory`, and `requestLog`. Predict the **logical result** first, then explain **likely routing and cost**. Never run sharding modifications on production.

### Exercise 1 — Targeted or scatter?

With shard key `{tenantId:1,orderId:1}`, classify:

~~~javascript
// A
db.orders.find({ tenantId: "t-01", orderId: "o-001" })

// B
db.orders.find({ tenantId: "t-01" })

// C
db.orders.find({ status: "PAID" })

// D
db.orders.find({ orderId: "o-001" })
~~~

Which typically targets one shard? Which may touch multiple shards? Why?

### Exercise 2 — Cluster-wide PAID totals

Write `$match` + `$group` + `$sort` returning PAID count and revenue per tenant. Predict the three rows and explain partial grouping vs. merging.

### Exercise 3 — Cluster-wide top 3

Retrieve the three highest-amount PAID orders, breaking ties with `tenantId`/`orderId`. Why can't you just take one shard's result?

### Exercise 4 — Pagination

Suppose you want page 5 with 20 orders per page sorted by `createdAt`. Calculate `skip` and explain why skipping must apply to **global** ordering; propose keyset pagination.

### Exercise 5 — Sharded foreign join

Join order `t-01/o-001` with its lines. Use `let` and `$expr` comparing both `tenantId` and `orderId`. Why is joining only on `orderId` incorrect?

### Exercise 6 — Grouping by tenant

One tenant has 500,000 orders spread across two shards. If the shards return local revenues of 200,000 and 300,000, what is the true total? Why isn't Shard A's result sufficient?

### Exercise 7 — Sharded `$merge` target

Design a materialized report with shard key `{tenantId:1,reportType:1}`. How must `on` fields and the unique index be configured? Why is `on:["reportType"]` insufficient?

### Exercise 8 — `$out`

Can `$out` write directly into an already-sharded `tenantReports` collection? If not, propose an alternative for creating versioned reports.

### Exercise 9 — Reading explain

Run the two pipelines in Section 14.3 through `mongos`. Record shards touched, COLLSCAN/IXSCAN, docs examined, and merge stages **if present**. Do not fabricate fields absent from the plan output.

### Exercise 10 — Inventory transaction

Inside one transaction: decrement inventory `t-01/A` by 1, insert order `t-01/o-1001`, and write `requestLog`. If `inventory` and `orders` live on different shards, does atomicity semantics change?

### Exercise 11 — Unknown commit retry

A transaction commits, yet the client loses the response. Is it safe for the client to resend the request with a **new `requestId`**? Design reconciliation.

### Exercise 12 — Hot shard

80% of cluster writes belong to the largest tenant with shard key `{tenantId:"hashed"}`. Why might adding shards fail to boost throughput? Propose a shard-key design that distributes within a tenant.

### Exercise 13 — Balancer and transactions

A chunk migration runs while a large transaction reads/writes the same range. Name sources of contention/aborts and design retry handling.

### Exercise 14 — Daily reporting

You need tenant revenue up to 00:00 UTC across 5 TB of data undergoing continuous writes. Propose cutoff, materialization, versioned cutover, and accuracy validation; do you need one transaction spanning all 5 TB?

### Exercise 15 — Backups

Why do data-file snapshots taken from Shard A at 10:00 and Shard B at 10:30 fail to guarantee a cluster-consistent backup?

### Exercise 16 — Measuring performance

Build a before/after sharding table:

| Metric | Before | After | Interpretation |
|---|---|---|---|
| API point lookup p95 | … | … | Is it targeted? |
| Global aggregation p95 | … | … | How costly is merge/network? |
| Shards touched / query | … | … | Is there scatter? |
| Write QPS per shard | … | … | Is there a hot shard? |
| Disk bytes/chunks per shard | … | … | Is storage skewed? |
| Transaction abort rate | … | … | Cross-shard contention? |
| Commit p99 | … | … | Did coordination add latency? |
| Balancer migration rate | … | … | Does it impact peak hours? |

Fill only real measurements from monitoring/benchmarks; never invent numbers to "prove sharding is faster."

## 34. Suggested lab answers

**Exercise 1:** A provides full shard-key equality so it usually targets a single shard. B has the tenant prefix so it may touch one or multiple shards depending on chunk placement. C and D lack the shard key prefix and may scatter.

**Exercise 2:** `t-01`: 3 PAID, 350; `t-02`: 3 PAID, 425; `t-03`: 3 PAID, 450. Shards can compute partial groups and the merger computes cluster totals.

**Exercise 3:** `t-03/o-009` (300), `t-02/o-005` (200), `t-02/o-007` (175). Global top 3 must be selected across all qualifying shards.

**Exercise 4:** Page 5 (1-based), size 20 → `skip=(5-1)*20=80`. Global sort/skip/limit requires cluster-wide ordering. Keyset pagination uses a cursor on the complete sort key.

**Exercise 5:** Match both `tenantId` and `orderId` in the foreign pipeline. Using `orderId` alone risks colliding across tenants and fails to qualify for proper foreign shard targeting.

**Exercise 6:** Total 500,000 in the same currency/unit. Local shard revenue is only a portion; a merger or tenant-wide materialized summary is needed.

**Exercise 7:** `on` must comply with the shard key and have a supporting unique index per sharded output rules. `reportType` alone neither identifies the tenant nor satisfies shard-key identity.

**Exercise 8:** `$out` cannot write arbitrarily into a sharded target. Use `$merge` obeying shard-key/unique constraints or materialize a new report version in a supported collection and perform an atomic cutover.

**Exercise 9:** Report only fields genuinely present in `explain`. The full-shard-key query generally touches fewer shards than the status-only query; stage names vary by execution engine.

**Exercise 10:** A supported distributed transaction still commits/aborts atomically across multiple shard participants; latency, overhead, and abort risk are higher.

**Exercise 11:** No. Reuse the existing `requestId`, retry commit in context if possible, or reconcile against the ledger; never create a new business intent.

**Exercise 12:** Hashing `tenantId` does not spread one tenant's orders across multiple key values. Use a shard key providing **within-tenant** distribution while preserving query routing and uniqueness.

**Exercise 13:** Migrations can contend on metadata/locks and cause transient errors; keep transactions short, shard-key-aware, and use bounded retries rather than unbounded timeouts.

**Exercise 14:** Use cutoffs and incremental/pre-aggregation, write summaries tagged with `reportVersion`, validate, then atomically flip `activeVersion`. You do not need a transaction across 5 TB when semantics are structured cleanly.

**Exercise 15:** Shards captured at different timestamps may reflect half before and half after distributed transactions, and placement metadata can change mid-backup. Use a consistent, sharding-aware backup mechanism.

**Exercise 16:** Evaluate routing, hot shards, merge/network overhead, latency, transaction aborts/commits, and balancer impact together—never measure only raw bytes or aggregate throughput.

## 35. Review questions

**1. Why can sharding make aggregations more complex?**

Because data is distributed across shards, stages like group, sort, and join may require partial processing, network transfers, and global merging.

**2. Does `mongos` store full collection data?**

No. It is a query router using metadata to direct operations to shards; application data resides on shards.

**3. How does filtering on the full shard key help?**

It lets the router target relevant shards/ranges, usually cutting fan-out. Full equality on the shard key can target a single shard.

**4. If `tenantId` is in the shard key, does every tenant query hit only one shard?**

No. A single tenant can be split into multiple chunks across multiple shards depending on shard key and placement.

**5. Why can a query filtering only by `status` trigger scatter-gather?**

Because `status` provides no shard-key routing information; the router may have to query every shard for matching documents.

**6. Is running `$group` on each shard enough for cluster-wide totals?**

Not when a group's documents appear on multiple shards. Partial results must be merged across shards.

**7. How does global top N differ from local top N?**

Global top N considers matching documents across all shards; local top N considers only one shard. The optimizer may compute local top-k as an intermediate step, but still needs a global merge.

**8. Does deep `$skip` become cheaper just because there are more shards?**

Not necessarily. Global ordering and skipping the cluster-wide prefix are still required; large offsets can still incur heavy network/sort/merge work.

**9. Is `$lookup` against a sharded collection supported?**

Yes, in modern versions such as MongoDB 5.1+, though performance and targeting depend on query shape, shard keys/indexes, and version.

**10. Do two collections with the same shard key automatically reside on the same shard?**

No. Chunk placement and balancing are managed independently per collection, so joins and transactions can still cross shards.

**11. What must be considered when running `$merge` into a sharded output collection?**

The `on` fields and unique index must satisfy shard key and uniqueness rules; never use keys omitting shard identity.

**12. Can `$out` replace an arbitrary sharded output collection?**

No. It has restrictions on sharded targets; use `$merge` or another materialization pattern.

**13. Are sharded transactions atomic?**

Yes, on supported topologies and versions. Cross-shard commits cost more, yet partial commits are never accepted as normal.

**14. When a transaction commit times out, should you retry with a new `requestId`?**

No; the prior transaction may have committed. Retry the commit or reconcile using a stable idempotency key.

**15. Why are multi-shard transactions prone to higher latency?**

They add routing, network hops, participant coordination, commit protocols, and higher odds of errors or lock contention.

**16. Does `transactionLifetimeLimitSeconds` automatically increase when shards are added?**

No. Transactions remain bound by lifetime and resource limits; adding shards does not allow unbounded long-running workflows.

**17. Does the balancer guarantee equal QPS across shards?**

No. Balancing data bytes or chunks does not balance hot keys, CPU, or write rates.

**18. Does a hashed shard key always solve a hot tenant?**

No—if you hash only `tenantId`, all writes for that tenant produce the same hash value and still concentrate load.

**19. Does a secondary read preference reduce the number of shards touched?**

Not directly. It chooses which replica set member serves reads within each shard; shard-key routing still decides how many shards participate.

**20. What matters when backing up a sharded cluster?**

Consistency across shard data, placement metadata, and distributed transactions; never combine independent shard snapshots taken at arbitrary times.

## 36. Pre-deployment sharding checklist for analytics and transactions

- [ ] Have primary access patterns been analyzed: point lookups, range queries, global aggregations, joins, and writes?
- [ ] Do candidate shard keys have adequate cardinality, distribution, and locality?
- [ ] Does any single tenant or hot key account for most of the QPS?
- [ ] Do critical queries supply the full shard key or a selective prefix to minimize shards touched?
- [ ] Have targeted vs. scatter-gather plans been verified with `explain()` on a representative topology?
- [ ] Are proper **per-shard indexes** present for filters, sorts, and joins?
- [ ] Do `$group`/`$sort` pipelines account for global merging, memory, and network capacity?
- [ ] Is there a unique tie-breaker for cross-shard sorting and pagination?
- [ ] Do `$lookup` pipelines on foreign sharded collections match full tenant/shard keys and control fan-out?
- [ ] Are joined documents kept safely under the 16 MiB limit?
- [ ] Are `$facet` and blocking stages bounded within version-specific memory/spill limits?
- [ ] Are `$merge`/`$out` compatible with sharded targets and unique indexes?
- [ ] Do transactions genuinely require cross-shard atomicity?
- [ ] Are business transactions scoped to minimal documents/shards with deadlines and bounded retries?
- [ ] Are collections and indexes pre-created via migrations, avoiding unsupported DDL inside transactions?
- [ ] Does error handling distinguish `TransientTransactionError` from `UnknownTransactionCommitResult`?
- [ ] Are idempotency keys and unique request ledgers enforced for API retries?
- [ ] Are external payment/email calls kept outside transaction callbacks?
- [ ] Has chunk migration/balancer impact on peak hours and transactions been assessed?
- [ ] Are zone placement, data residency, and hot-shard mitigations planned where needed?
- [ ] Are resharding, rollout/rollback, and version/FCV compatibility runbooks prepared?
- [ ] Are sharding-aware backups and restores verified regularly?
- [ ] Are p95/p99 latency, per-shard QPS/CPU/disk/cache, merger network traffic, and replication lag measured?
- [ ] Can heavy analytics be offloaded to summaries/ETL/warehouse if scatter-gather grows too expensive?

## 37. Conclusion

**Sharding changes where and how MongoDB operations execute, without changing the correctness goals of queries.** An aggregation is only accurate when partial results are combined into a cluster-wide answer faithful to pipeline semantics; a global top N cannot be replaced by one shard's top N; and a join to a sharded foreign collection still requires accurate join keys, supporting indexes, and fan-out control.

For transactions, MongoDB supports **distributed transactions** on sharded clusters in compatible versions, so writes spanning shards remain atomic. The trade-off is **coordination latency, network hops, lock/cache pressure, and additional retry/unknown-commit scenarios**, making short, shard-key-aware, idempotent transactions an essential design discipline.

Operationally, monitor **chunk placement, hot shards, the balancer, resharding, replication, indexes, and consistent backups** together. Adding shards pays off only when workloads distribute cleanly, queries avoid unnecessary scatter, and merge steps do not become new bottlenecks. Good outcomes must be proven by **shards touched, query plans, p95/p99 latency, per-shard metrics, and business correctness** — not merely cluster node count.
