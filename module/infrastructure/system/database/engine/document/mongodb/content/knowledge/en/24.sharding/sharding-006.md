# Targeted Queries and Scatter-Gather Queries in MongoDB

When data grows to the point where a single server struggles to handle storage capacity or traffic, MongoDB lets you distribute a collection’s documents across multiple **shards**. Yet adding shards only helps when the application understands **which shard a query is sent to**. A `find()` statement may go directly to the single shard holding the document, or it may fan out to every shard and wait to merge results.

These two execution modes are commonly referred to as:

- **Targeted query**: the router can pinpoint one shard or a **subset** of shards to query using conditions on the shard key. When it narrows down to **a single shard**, it is a *single-shard query*.
- **Scatter-gather query**: the router must **broadcast the request** to multiple shards—often all shards involved in the collection—then **collect and merge** the results.

This lesson covers **Targeted Queries and Scatter-Gather Queries** in the **Sharding** chapter of the **MongoDB Document Database Engine** module. The goal is not merely memorizing “having a shard key makes it fast,” but understanding **which conditions let `mongos` narrow the scope**, behaviors across compound/hashed/range shard keys, the role of per-shard indexes, reading `explain()`, and avoiding optimizations that break business semantics.

## 1. How does sharding change a query’s path?

In an unsharded replica set, the driver picks an eligible member per read preference and sends the query to that replica set. In a **sharded cluster**, applications normally connect to **`mongos`**, the component that routes queries to shards:

```text
                APPLICATION / JAVA DRIVER
                         |
                         v
                     mongos
                   /    |    \
                  /     |     \
                 v      v      v
              Shard A Shard B Shard C
              (RS)    (RS)    (RS)
                 \      |      /
                  \     |     /
                     mongos
                        |
                        v
                  MERGED RESULT
```

A **shard** is typically a replica set storing a **subset** of a sharded collection’s data. **Config servers** store configuration/routing metadata; `mongos` uses this information to know which **shard key value ranges** currently belong to which shards. In modern MongoDB versions, data is managed via *shard key ranges* (commonly associated with *chunks*).

When an application queries `orders`:

1. `mongos` receives the command and checks whether the collection is sharded.
2. If sharded, `mongos` analyzes the query **predicates** to determine which shard key ranges could match.
3. From data placement metadata, it determines which shards own the relevant ranges.
4. `mongos` dispatches the query to **one, several, or all shards**.
5. The shards run their portion of the query and return data/statistics.
6. `mongos` or a merge step aggregates, sorts, limits, and returns results to the client.

In practice, range placement can shift during balancing or migrations. Applications should **never hardcode shard hosts per tenant**. The `mongos` router tracks metadata and handles refreshes when metadata goes stale.

### Distinguish three concepts

| Concept | Question it answers | Example |
| --- | --- | --- |
| **Shard key** | Which fields/values govern document distribution? | `{tenantId: 1, orderId: 1}` |
| **Shard targeting** | Which shards must receive the query? | Single shard, subset, or all |
| **Local query plan** | On each selected shard, does it use an index or scan the collection? | `IXSCAN`, `FETCH`, `COLLSCAN` |

A query can be **targeted to the right shard yet still be slow** if that shard scans many documents. Conversely, a query can **scatter-gather while each shard uses a good index**. Measure these two optimization dimensions independently.

## 2. Targeted vs. scatter-gather queries: visual intuition

Suppose a sharded collection stores data for multiple tenants, with shard key ranges distributed across three shards.

### 2.1. Targeted query

The application knows the full shard key of the order it wants:

```javascript
db.orders.findOne({
  tenantId: "T01",
  orderId: 104
})
```

With a ranged shard key `{tenantId: 1, orderId: 1}`, equality conditions on **all components** enable `mongos` to locate the range containing that key and route the request to the shard owning that range.

```text
                  mongos
                     |
          tenantId=T01, orderId=104
                     |
          Shard-key range lookup
                     |
          +----------+----------+
          |          |          |
       Shard A     Shard B    Shard C
          |          |          |
          X          v          X
                  Find document
                      |
                      v
                 Return result
```

Shard B here is **illustrative**, not a fixed address. Which shard actually receives a key depends on current placement metadata.

### 2.2. Scatter-gather query

The application only knows the order status is `"paid"`, without the shard key:

```javascript
db.orders.find({ status: "paid" })
```

With the collection sharded on `{tenantId: 1, orderId: 1}`, the `status` field provides no information to narrow shard key ranges.

```text
                    mongos
          filter: status = "paid"
                       |
             +---------+---------+
             |         |         |
             v         v         v
          Shard A   Shard B   Shard C
             |         |         |
           filter    filter    filter
             |         |         |
             +---------+---------+
                       |
                 merge results
                       |
                       v
                    Client
```

Each shard can still use a `{status: 1}` index to filter quickly. However, the request hits multiple shards, incurring extra network calls, distributed work, and result merging.

### Targeted does not necessarily mean one shard

A query with **part** of a shard key or a range of shard key values may touch only **a subset of shards**. For example:

```javascript
db.orders.find({ tenantId: "T01" })
```

With the compound shard key `{tenantId: 1, orderId: 1}`, `T01`’s orders may span **multiple ranges** placed on different shards. Because the query has the prefix predicate, `mongos` can narrow the scope, yet **a single shard is not guaranteed**.

This is an important distinction between:

- **Targeting a range or set of ranges** from query predicates.
- **Targeting a single shard** after resolving those ranges against current placement.

## 3. Preparing the practice environment and dataset

To observe real multi-shard routing, you need a **sharded cluster** with `mongos`, a config server replica set, and at least two shards. Multi-shard scatter-gather cannot be observed on a standalone `mongod` or a single replica set.

The examples below separate into **two practice levels**:

1. On a dedicated lab database, insert documents and learn predicate semantics.
2. When you have administrative privileges on a **lab sharded cluster**, shard the collection to observe `mongos` routing and run `explain`.

Without a sharded cluster, you can still study pipelines and shard key design, but **never treat the shard count reported on a single replica set as routing proof**.

### 3.1. Creating sample data

Connect through a lab cluster’s `mongos` or an isolated practice MongoDB environment:

```javascript
use sharding_lab

db.orders.insertMany([
  {
    _id: "T01-100", tenantId: "T01", orderId: 100,
    status: "paid", region: "north", total: 120,
    createdAt: ISODate("2026-11-10T08:00:00Z")
  },
  {
    _id: "T01-101", tenantId: "T01", orderId: 101,
    status: "pending", region: "north", total: 50,
    createdAt: ISODate("2026-11-10T09:00:00Z")
  },
  {
    _id: "T01-102", tenantId: "T01", orderId: 102,
    status: "paid", region: "south", total: 240,
    createdAt: ISODate("2026-11-11T08:00:00Z")
  },
  {
    _id: "T01-103", tenantId: "T01", orderId: 103,
    status: "cancelled", region: "north", total: 80,
    createdAt: ISODate("2026-11-11T09:00:00Z")
  },
  {
    _id: "T01-104", tenantId: "T01", orderId: 104,
    status: "paid", region: "north", total: 170,
    createdAt: ISODate("2026-11-12T08:00:00Z")
  },
  {
    _id: "T01-105", tenantId: "T01", orderId: 105,
    status: "paid", region: "south", total: 130,
    createdAt: ISODate("2026-11-12T09:00:00Z")
  },
  {
    _id: "T02-200", tenantId: "T02", orderId: 200,
    status: "paid", region: "north", total: 310,
    createdAt: ISODate("2026-11-10T10:00:00Z")
  },
  {
    _id: "T02-201", tenantId: "T02", orderId: 201,
    status: "pending", region: "south", total: 95,
    createdAt: ISODate("2026-11-10T11:00:00Z")
  },
  {
    _id: "T02-202", tenantId: "T02", orderId: 202,
    status: "paid", region: "south", total: 200,
    createdAt: ISODate("2026-11-11T10:00:00Z")
  },
  {
    _id: "T02-203", tenantId: "T02", orderId: 203,
    status: "paid", region: "north", total: 170,
    createdAt: ISODate("2026-11-12T10:00:00Z")
  },
  {
    _id: "T02-204", tenantId: "T02", orderId: 204,
    status: "pending", region: "north", total: 60,
    createdAt: ISODate("2026-11-12T11:00:00Z")
  },
  {
    _id: "T03-300", tenantId: "T03", orderId: 300,
    status: "paid", region: "south", total: 220,
    createdAt: ISODate("2026-11-10T12:00:00Z")
  },
  {
    _id: "T03-301", tenantId: "T03", orderId: 301,
    status: "paid", region: "north", total: 190,
    createdAt: ISODate("2026-11-11T11:00:00Z")
  },
  {
    _id: "T03-302", tenantId: "T03", orderId: 302,
    status: "pending", region: "south", total: 85,
    createdAt: ISODate("2026-11-11T12:00:00Z")
  },
  {
    _id: "T03-303", tenantId: "T03", orderId: 303,
    status: "paid", region: "north", total: 140,
    createdAt: ISODate("2026-11-12T12:00:00Z")
  }
])
```

The dataset has 15 documents across three tenants. Totals to cross-check ordinary queries:

| Tenant | Total orders | `paid` orders | `paid` revenue |
| --- | ---: | ---: | ---: |
| `T01` | 6 | 4 | 660 |
| `T02` | 5 | 3 | 680 |
| `T03` | 4 | 3 | 550 |
| **All** | **15** | **10** | **1,890** |

Document `"T01-104"` has `tenantId: "T01"`, `orderId: 104`. Full-key query examples will use it.

**Operational note:** only insert data into a new/empty lab collection. Re-running `insertMany()` with the same `_id`s will hit duplicate key errors. Never drop or re-shard a live production collection to practice.

### 3.2. On a lab sharded cluster only: declare the shard key

Suppose we decide to shard the collection using the ranged compound key:

```javascript
{ tenantId: 1, orderId: 1 }
```

On `mongos` with proper admin privileges, prepare the index and shard the collection:

```javascript
use sharding_lab

db.orders.createIndex(
  { tenantId: 1, orderId: 1 },
  { name: "idx_tenant_order" }
)

sh.shardCollection(
  "sharding_lab.orders",
  { tenantId: 1, orderId: 1 }
)
```

If the collection is already sharded or the environment lacks support/privileges, do not re-run commands just to force the lesson’s output. In MongoDB, sharding a populated collection also depends on index constraints, unique indexes, collection state, and server version; the snippet assumes the lab collection meets prerequisites.

**A common misconception:** 15 documents is tiny, so enabling sharding **does not guarantee the data immediately splits across three shards**. There may be only a single small data range resting on one shard. To observe real multi-shard fan-out, you need a lab environment where relevant ranges are actually distributed across multiple shards. Never arbitrarily run `moveChunk` or manual balancing commands on production to make a diagram look pretty.

To inspect metadata where authorized:

```javascript
sh.status()
```

On `mongosh` versions supporting the helper, you can view collection distribution:

```javascript
db.orders.getShardDistribution()
```

These are inspection commands. They verify the collection’s shard key, available shards, and how data/ranges are distributed before interpreting `explain` output.

## 4. Why must `mongos` look at the shard key?

With the ranged shard key:

```javascript
{ tenantId: 1, orderId: 1 }
```

MongoDB orders shard key values lexicographically by the compound key and distributes **ranges** across shards. Visualized:

```text
Logical order of shard key:

(T01, 100) ... (T01, 999)
       (T02, 100) ... (T02, 999)
             (T03, 100) ... (T03, 999)
                         ...

Shard-key ranges:
   R1 ------------ R2 ----------- R3 ----------
      |                |              |
      v                v              v
    Shard A          Shard C        Shard B
```

This diagram does not represent the actual physical distribution of the sample data. What matters is that **predicates can map to one or more key ranges**.

### Equality on the full shard key

```javascript
db.orders.find({
  tenantId: "T01",
  orderId: 104
})
```

This is a **point lookup** on the shard key: it identifies the range containing that pair and the shard owning it. Under normal routing conditions, `mongos` does not need to query every shard.

### Equality on the compound shard key prefix

```javascript
db.orders.find({ tenantId: "T01" })
```

This filters on the **leading component** of the compound key. Pairs `(T01, orderId)` sit contiguously in shard key order, so `mongos` can use this prefix to identify the relevant ranges. However, `T01`’s ranges may reside on multiple shards.

### Filtering only on the trailing component

```javascript
db.orders.find({ orderId: 104 })
```

Without `tenantId`, `orderId: 104` can appear under any tenant and sit scattered across the compound key ordering. This predicate **cannot leverage the prefix** to isolate a contiguous shard key range. Typically the router must contact all shards holding the collection.

**Intuitive rule:** with a compound ranged shard key, **field order dictates prefix targeting capability**. Having the trailing field without the leading field is not equivalent to having the full shard key.

## 5. Comparison table of query patterns with a ranged compound shard key

Suppose `orders` has shard key `{tenantId: 1, orderId: 1}`:

| Filter | Shard key info available | Routing behavior |
| --- | --- | --- |
| `{tenantId:"T01",orderId:104}` | Full equality | Usually targets **one shard** owning the key pair |
| `{tenantId:"T01"}` | Prefix equality | Targets `T01` ranges; may hit **one or multiple shards** |
| `{tenantId:"T01",orderId:{$gte:103}}` | Prefix equality + range | Targets relevant ranges in `T01`; may hit multiple shards |
| `{tenantId:{$in:["T01","T03"]}}` | Subset of prefix values | Can narrow to the **union of matching ranges** |
| `{tenantId:{$gte:"T02",$lt:"T04"}}` | Prefix range | Can skip out-of-range shards, depending on placement |
| `{orderId:104}` | Trailing field only | Usually must scatter-gather |
| `{status:"paid"}` | No shard-key predicate | Usually must scatter-gather |
| `{_id:"T01-104"}` | No shard key in filter | Usually must scatter-gather even though `_id` is indexed |
| `{tenantId:"T01",status:"paid"}` | Prefix equality + extra filter | Targets `T01` ranges; `status` filtered locally on shard |
| `{}` | No conditions | Scans collection across relevant shards |

**Do not treat this table as a promise of exact shard counts on every run.** Shard placement, optimizer version, shard key type, filter values, and ongoing migrations all affect the actual plan. `explain()` is how you confirm which shards the router selected.

### Note about `_id`

Every MongoDB document has `_id`, and MongoDB creates the `_id_` index by default. However, if the **shard key is not `_id`**, the query:

```javascript
db.orders.findOne({ _id: "T01-104" })
```

does not tell `mongos` which shard holds `(tenantId, orderId)`. It may have to send the query to multiple shards; on **each shard**, the `_id_` index still makes local lookup fast.

This is the clearest illustration that **having a good index does not mean routing to the right shard**. If the application frequently looks up orders by ID, evaluate ID/shard key design and whether `tenantId` can accompany every call.

## 6. Compound shard key: having the prefix does not guarantee one shard

Suppose tenant `T01`’s data is huge, so `T01`’s key ranges are split:

```text
Shard key: {tenantId:1, orderId:1}

T01 ranges:
  (T01, MinKey)  ... (T01, 199)    -> Shard A
  (T01, 200)     ... (T01, 499)    -> Shard B
  (T01, 500)     ... (T01, MaxKey) -> Shard C
```

This diagram is **hypothetical for explanation**, not actual lab data.

Query:

```javascript
db.orders.find({ tenantId: "T01" })
```

may need to contact **A, B, and C**, even though the predicate supplies the shard key prefix. Meanwhile:

```javascript
db.orders.find({
  tenantId: "T01",
  orderId: 235
})
```

can route directly to **B**.

### Range on the trailing component

```javascript
db.orders.find({
  tenantId: "T01",
  orderId: { $gte: 200, $lt: 300 }
})
```

narrows the scope compared to all of `T01`; if range 200–299 lies completely on B, only B handles it in this diagram. If the range straddles two shard-key ranges, `mongos` must contact both shards.

When writing APIs, pass **exactly the shard key info the application legitimately knows**, rather than guessing `tenantId` from an unverified ID format.

### Predicates that defeat targeting

An example:

```javascript
db.orders.find({
  $or: [
    { tenantId: "T01" },
    { status: "pending" }
  ]
})
```

The second branch `status: "pending"` can match documents on **any shard**, so the overall `$or` cannot be restricted to `T01`’s ranges. It may require scatter-gather.

In contrast:

```javascript
db.orders.find({
  $or: [
    { tenantId: "T01", orderId: 104 },
    { tenantId: "T02", orderId: 202 }
  ]
})
```

constrains **both branches with the full shard key**. `mongos` can target the union of those two key points instead of querying every shard. Those two points may sit on the same shard or two different shards.

**Do not assume every `$or`, `$in`, or range condition automatically scatters.** Routing depends on whether the entire predicate reduces to a narrow set of shard-key ranges.

## 7. Hashed shard keys: equality and range behave differently

Another collection might be sharded on a hashed key:

```javascript
{ tenantId: "hashed" }
```

With hashed sharding, MongoDB hashes the shard key value to assign data ranges. Alphabetically adjacent `tenantId` values are **not necessarily** adjacent in shard-key range order.

```text
Original tenantId:  T01    T02    T03    T04
                     |      |      |      |
                     v      v      v      v
Hash value:        h(T01) h(T02) h(T03) h(T04)
                   scattered across hash space
```

### Equality on a hashed key

```javascript
db.orders.find({ tenantId: "T01" })
```

When the shard key is `{tenantId: "hashed"}`, equality on `tenantId` lets `mongos` compute the hash and locate the corresponding shard-key range. Under normal conditions, this is a targeted query to the shard owning that hash value.

With a **compound** hashed shard key, inspect field order and components; never assume equality on an arbitrary field suffices to target one shard.

### Range on original values of a hashed key

```javascript
db.orders.find({
  tenantId: { $gte: "T01", $lt: "T50" }
})
```

Tenants in the alphabetical range `T01`–`T49` have hashes scattered across the entire hash space. Therefore, **a range on the original values of a hashed shard key does not yield a contiguous hash interval**, usually causing scatter-gather.

Here is the trade-off:

| Property | Ranged shard key | Hashed shard key |
| --- | --- | --- |
| Equality on full key | Usually targets one shard | Usually targets one shard |
| Range on key | Can target relevant ranges | Range on original values rarely routes narrowly |
| Physical order by key value | Preserves key order | Breaks adjacency of original values |
| Distributing ascending values | Can create hotspots if poorly designed | Can distribute better with fitting patterns |
| Reports by shard key range | Usually more favorable | Often must query multiple shards |

Hashed sharding is not a way to “make every query targeted.” It fits workloads dominated by **equality lookups** needing data/write distribution, trading off **range scan** efficiency.

## 8. Queries indexed on every shard can still scatter-gather

Suppose the shard key is:

```javascript
{ tenantId: 1, orderId: 1 }
```

and we create an index serving status queries:

```javascript
db.orders.createIndex(
  { status: 1, createdAt: -1 },
  { name: "idx_status_created" }
)
```

Run:

```javascript
db.orders.find({ status: "paid" })
  .sort({ createdAt: -1 })
  .limit(10)
```

The query **lacks a shard-key predicate**, so `mongos` may have to query all shards holding data. On each shard, MongoDB can use `idx_status_created` to filter and sort very efficiently.

```text
             mongos (scatter)
              /     |     \
             v      v      v
         Shard A Shard B Shard C
          IXSCAN  IXSCAN  IXSCAN
             \      |      /
              \     |     /
          merge / global sort / limit
                    |
                 10 results
```

Depending on pipeline and indexes, shards can stream pre-sorted candidates so the merge step selects the global top 10 rather than pulling every document to `mongos` before sorting. Even so, multi-shard overhead, fan-out, network traffic, and merge work remain.

**Separate two optimization goals:**

1. **Reduce shards contacted** via appropriate shard-key predicates.
2. **Reduce work per shard** via appropriate indexes, predicates, projections, and sorts.

Solving only (2) will not eliminate scatter-gather if `mongos` still cannot tell which shards might hold results.

## 9. Practicing `explain()` to verify targeted vs. scatter

Never conclude a query is targeted solely because “the filter seems to mention `tenantId`.” Run `explain` through **`mongos`** and inspect how many shards and stages participate in execution.

### 9.1. Full-shard-key point lookup

```javascript
db.orders.find({
  tenantId: "T01",
  orderId: 104
})
  .explain("queryPlanner")
```

Or include execution statistics:

```javascript
db.orders.find({
  tenantId: "T01",
  orderId: 104
})
  .explain("executionStats")
```

In a sharded cluster, `explain` can include **per-shard details** and stages showing routing/merging. If exactly one shard participates, the query achieved single-shard execution in that `explain` run.

### 9.2. Scatter query by status

```javascript
db.orders.find({ status: "paid" })
  .explain("executionStats")
```

Compare the reported shard count against the point lookup `explain`. If the collection has ranges across three shards and `status` does not constrain the shard key, the plan shows requests going to multiple shards.

### 9.3. Prefix query

```javascript
db.orders.find({ tenantId: "T01" })
  .explain("executionStats")
```

Treat this as **one or more targeted shards**. If all of `T01`’s ranges sit on one shard, one shard participates; if `T01` is spread out, multiple participate. Do not extrapolate a single lab run into a rule that prefix queries always hit only one shard.

### 9.4. Explain structure is not fixed across versions

A sharded query’s `explain` output may include structures such as:

```text
explain (conceptual)
├── queryPlanner
│   └── winningPlan
│       ├── routing / merge stages
│       └── per-shard branches or info sections
├── executionStats
│   ├── executionStages
│   ├── totalKeysExamined / totalDocsExamined when present
│   └── per-shard statistics
├── shards (in certain explain formats)
└── other metadata
```

You may see stage names such as `SHARD_MERGE`, `SHARD_MERGE_SORT`, `SINGLE_SHARD`, `SHARDING_FILTER`, `IXSCAN`, `FETCH`, or `COLLSCAN`, depending on MongoDB version, query engine, and query form. **No single fixed JSON path** applies across all versions and all `find`/`aggregate` commands.

Some versions also emit **slot-based execution engine (SBE)** representations like `queryPlan`/`slotBasedPlan`, changing the stage tree from older docs. When reading, answer these questions:

1. How many **shards actually received requests**?
2. Which index did each shard use—any `COLLSCAN` or `SORT`?
3. Is there a merge/sort/limit step on the router or merge shard?
4. At **what scope** are `nReturned`, `totalKeysExamined`, and `totalDocsExamined` reported: per-shard or query-wide?
5. Are there signs the router had to ask every shard even though the final result is a single document?

### Examined counts alone do not reveal targeting

Compare two hypothetical plans:

```text
A: 1 shard,  totalDocsExamined = 15000, nReturned = 1
B: 3 shards, each shard totalDocsExamined = 1, total nReturned = 1
```

A targeted one shard yet may lack a local filter index, scanning 15,000 documents. B is scatter-gather yet each shard has a great index and reads very little. You cannot infer **routing efficiency** from `docsExamined` alone, nor **total latency** from shard count alone. Inspect both.

## 10. Reading `explain` for aggregations on a sharded collection

Aggregation pipelines can split work between shards and a merge step:

```javascript
db.orders.explain("executionStats").aggregate([
  { $match: { status: "paid" } },
  {
    $group: {
      _id: "$tenantId",
      paidOrders: { $sum: 1 },
      revenue: { $sum: "$total" }
    }
  },
  { $sort: { revenue: -1 } }
])
```

With the sample dataset, the groups are:

```javascript
{ _id: "T02", paidOrders: 3, revenue: 680 }
{ _id: "T01", paidOrders: 4, revenue: 660 }
{ _id: "T03", paidOrders: 3, revenue: 550 }
```

However, `status: "paid"` **does not constrain the shard key**, so the initial read typically requires multiple shards. MongoDB can run partial aggregation stages locally on shards and merge results at a merge stage, depending on the optimizer and pipeline.

```text
                mongos / router
                      |
                scatter $match
            +---------+---------+
            |         |         |
          Shard A   Shard B    Shard C
          $match    $match     $match
          partial   partial    partial
          $group    $group     $group
            |         |         |
            +---------+---------+
                      |
                 merge $group
                      |
                   $sort
                      |
                3 tenant totals
```

This diagram shows **one possible strategy**, not a guarantee that the server always splits `$group` into exactly two phases. Aggregation `explain` may show `splitPipeline`, `shardsPart`, `mergerPart`, or other stage structures depending on version. Identify **which steps run on shards and which step merges results**.

### Aggregation for a single tenant

```javascript
db.orders.explain("executionStats").aggregate([
  { $match: { tenantId: "T01", status: "paid" } },
  {
    $group: {
      _id: "$tenantId",
      paidOrders: { $sum: 1 },
      revenue: { $sum: "$total" }
    }
  }
])
```

The logical result is **one group for `T01` with 4 orders and revenue 660**. Because the compound shard key also includes `orderId`, `tenantId: "T01"` only constrains the prefix, so **one or multiple shards** may be involved if `T01` spans multiple ranges.

### Placing `$match` where it aids routing

Normally place shard-key predicates **early in the pipeline**:

```javascript
db.orders.aggregate([
  { $match: { tenantId: "T01" } },
  { $match: { status: "paid" } },
  { $group: { _id: "$region", revenue: { $sum: "$total" } } }
])
```

MongoDB’s aggregation optimizer can coalesce or push certain `$match` stages ahead of equivalent stages, so textual reordering does not guarantee a speedup in every case. Still, **filtering on the shard key before data-transforming stages** expresses intent clearly and usually helps routing/scan optimization.

Conversely, if a stage before `$match` **removes or renames the shard key**, you may lose predicate pushdown or alter semantics:

```javascript
// Careful: prior $project dropped tenantId
db.orders.aggregate([
  { $project: { status: 1, total: 1 } },
  { $match: { tenantId: "T01" } }
])
```

This pipeline is not equivalent to filtering by tenant first and then projecting. Never blindly move `$match` across stages that alter field semantics or existence.

## 11. `$sort`, `$skip`, `$limit`: cross-shard merge costs

Suppose the application needs the ten most recent `paid` orders system-wide:

```javascript
db.orders.find({ status: "paid" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(10)
```

The query does not constrain the shard key, so it may scatter across shards. To return the **global top 10**, the router/merger cannot simply grab 10 from an arbitrary shard and ignore the others.

An efficient plan has **each shard return ordered candidates**, then the merge step picks the top 10:

```text
Shard A:  12:00, 11:00, 08:00, ...
Shard B:  11:30, 10:30, 09:00, ...
Shard C:  11:45, 11:15, 07:00, ...
                    |
                    v
            Global merge sort
                    |
                    v
            10 newest rows
```

### `limit` does not guarantee reading only 10 documents

If a shard lacks an index matching the filter/sort, it may have to scan many documents just to identify its newest candidates. Check indexes serving **local sorts** on each shard, such as:

```javascript
db.orders.createIndex(
  { status: 1, createdAt: -1, _id: -1 },
  { name: "idx_status_created_id" }
)
```

This index supports local filtering/sorting, yet **does not tell `mongos` that only one shard holds `paid` orders**. It solves a different part of the performance puzzle.

### Large `skip` remains expensive

```javascript
db.orders.find({ status: "paid" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(100000)
  .limit(20)
```

This query finds records after a huge offset **in global order**. Even with sort/skip/limit optimizations, the system must process enough candidates to discard the first 100,000 results. On a sharded cluster, fan-out and merge overhead multiply.

When the application only needs “next page,” consider **keyset pagination** on `createdAt` plus a stable tie-breaker, while keeping the shard key in the filter if paging is scoped to a tenant.

Example for a **single tenant’s** list:

```javascript
db.orders.find({
  tenantId: "T01",
  $or: [
    { createdAt: { $lt: ISODate("2026-11-12T09:00:00Z") } },
    {
      createdAt: ISODate("2026-11-12T09:00:00Z"),
      _id: { $lt: "T01-105" }
    }
  ]
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
```

In this example, top-level `tenantId: "T01"` constrains both `$or` branches. It **prevents scanning other tenants**, though because the shard key also contains `orderId`, it may still contact multiple shards holding `T01`’s data.

## 12. Designing APIs to carry the shard key end-to-end

A common way to improve targeting is carrying **tenant context** in the API route:

```text
GET /tenants/T01/orders/104
           |         |
           v         v
        tenantId   orderId
           \         /
            \       /
    find({tenantId:"T01",orderId:104})
```

Compare with:

```text
GET /orders/T01-104
         |
         v
  find({_id:"T01-104"})
```

The second API passes only `_id` in the filter. Even though `_id` contains a string resembling a tenant ID, `mongos` will not parse `"T01-104"` to infer `tenantId` and `orderId` if the query does not specify those fields.

### Where should tenant context come from?

In multi-tenant systems, `tenantId` should come from **trusted authentication/authorization context**, or be verified against permissions if client-supplied. Never trust an arbitrary `tenantId` from a request without verifying the user is authorized to read that tenant’s data.

A targeted, fast query that **lacks authorization checks** is still a severe data security flaw. Good design combines:

1. Verifying tenant access authorization.
2. Passing `tenantId` in the exact BSON type into the filter.
3. Including `orderId` or other shard key components when known.
4. Running `explain`/metrics on real workloads to verify contacted shard counts.

### Never assume an ID is the shard key

An ID like `"T01-104"` may be a business convention, yet MongoDB routes strictly using the **declared shard key**. If a sharded collection uses `{tenantId:1,orderId:1}`, filtering only on `_id` still lacks key info. If a different key is configured, routing behaves differently. Inspect cluster metadata rather than guessing from ID formatting.

## 13. `$in`, `$or`, expressions, and data types: why the same field routes differently

The following predicates are not equivalent in routing capability:

```javascript
// A. Equality on full shard key
{ tenantId: "T01", orderId: 104 }

// B. Equality on compound shard key prefix
{ tenantId: "T01" }

// C. List of prefix values
{ tenantId: { $in: ["T01", "T03"] } }

// D. Only a non-prefix field
{ orderId: 104 }

// E. Computed condition using an expression
{ $expr: { $eq: ["$tenantId", "T01"] } }
```

MongoDB may optimize certain expression forms, yet **never assume logically equivalent formulations have identical shard targeting capability**. For straightforward APIs, direct equality predicates on the shard key are clearer and easier to inspect than runtime-evaluated expressions.

### BSON type of shard-key predicates must match

If the collection stores:

```javascript
{ tenantId: "T01", orderId: 104 }
```

then:

```javascript
db.orders.find({
  tenantId: "T01",
  orderId: "104"
})
```

is not equivalent to equality on the **number** `104`. Shard keys store typed BSON values; strings and numbers differ in both equality semantics and key-space position.

MongoDB may still **target a single shard based on the mistyped value**—and then find zero matching documents. Thus, “single-shard query” does not prove the application’s filter matches the actual data.

### Collation and string representation

If a shard key contains strings, collation rules, casing normalization, and value types affect comparisons and routing bound inference. A query using a different collation from how the shard key was distributed may not get normal equality targeting.

Do not assume `"t01"` and `"T01"` represent the same tenant unless the schema enforces it. Normalize IDs consistently on writes and reads, and check `explain` if queries use non-default collations.

## 14. Key distinction: shard targeting vs. query selectivity

**Targeting** answers “which shards must be contacted?” **Selectivity** answers “on each shard, how many documents match and how many entries must be examined?”

Consider two queries:

```javascript
// A. Targeted via full shard key
db.orders.find({
  tenantId: "T01",
  orderId: 104
})

// B. Without shard key, filtering on selective status
db.orders.find({
  status: "cancelled"
})
```

A may contact only one shard and use a matching index quickly. B may contact all shards, yet if `status: "cancelled"` is very rare and each shard has an index, total documents read may still be small.

### Maintain indexes for both shard key and query shapes

Shard key/routing index:

```javascript
db.orders.createIndex(
  { tenantId: 1, orderId: 1 },
  { name: "idx_tenant_order" }
)
```

Index serving chronological paid orders per tenant:

```javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: -1 },
  { name: "idx_tenant_status_created" }
)
```

These two indexes serve different purposes. The second index helps:

```javascript
db.orders.find({
  tenantId: "T01",
  status: "paid"
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(10)
```

filter and sort locally with high efficiency. However, because only `tenantId` is present from the compound shard key `{tenantId:1,orderId:1}`, how many shards are contacted still depends on `T01`’s range span and placement.

**Every query-serving index does not have to contain every shard key field** in all cases. Index design must balance workload, selectivity, sorts, coverage, and write/index storage overhead.

## 15. Queries that cannot avoid fan-out

Not every application can or should force the shard key into every query. System-wide reports often must aggregate **across tenants**.

Example regional revenue report:

```javascript
db.orders.aggregate([
  { $match: { status: "paid" } },
  {
    $group: {
      _id: "$region",
      revenue: { $sum: "$total" }
    }
  },
  { $sort: { revenue: -1 } }
])
```

If `region` and `status` are not in the shard key, the query may need data from every shard. That is **not automatically a design flaw**: the business question asks for a system-wide total, so all shards must contribute.

Ways to reduce cost include:

- Suitable indexes for filters and index-capable stages **on each shard**.
- Scoping to a reporting time window instead of scanning full history.
- Designing aggregations to run partially per shard and merge efficiently when supported by the optimizer.
- Maintaining pre-aggregated tables (*materialized summaries*) when reports run very frequently.
- Offloading heavy analytical workloads to dedicated infrastructure/patterns rather than forcing OLTP lookups and multidimensional analytics to share identical patterns.

**Never inject fake shard keys** into filters just to make `explain` show fewer shards if doing so drops valid data. Targeting is only useful when it **preserves exact business results**.

## 16. Choosing a shard key from query patterns

Choosing a shard key is a long-term decision shaping data distribution, load balance, hotspots, and targeting. Start from the **most frequent queries**.

Suppose a system has three query patterns:

| Pattern | Frequency | Key conditions | Goal |
| --- | --- | --- | --- |
| Look up one order | Very high | `tenantId + orderId` | Targeted point lookup |
| List one tenant’s orders | High | `tenantId + status`, sorted by time | Limit shard fan-out and use local index/sort |
| Cross-tenant report | Lower | `status + createdAt` | Optimize scan/aggregation, accept multi-shard |

Here `{tenantId:1,orderId:1}` is a **reasonable candidate** for point lookups, though you must inspect whether huge tenants span many shards. If workloads primarily read by `tenantId`, evaluate alternative keys or distribution strategies based on cardinality, tenant skew, and growth.

### Avoid monotonic keys causing write hotspots

If the shard key is solely a continuously ascending value (e.g., timestamp or ascending sequence in ranged sharding), new writes concentrate at the tail of the key space and on one shard for a period. This is a **write hotspot**, not merely a query-targeting problem.

Hashed keys can spread ascending values better in some workloads, though range queries on original keys target less narrowly. No shard key optimizes every query; balance read/write distribution and query patterns.

### Cardinality and oversized tenants

If you shard only on `tenantId` and one huge tenant owns most of the data, that tenant creates imbalance/hotspots. A compound shard key can split a tenant’s data across multiple shard-key ranges, trading off the fact that `tenantId`-only queries may contact multiple shards.

This explains why the goal “every per-tenant query hits only one shard” **does not always coexist** with spreading a giant tenant’s data. Measure actual data volume and traffic per tenant.

### Stability of the shard key

A shard key should have stable meaning, appear in most critical queries, and distribute well. If business logic frequently mutates shard-key values, updating/moving documents is far costlier than regular fields.

Before deciding, inventory API routes, measure the share of queries supplying the full shard key, cross-tenant query rates, and read/write distribution, rather than picking whichever field looks highest-cardinality on paper.

## 17. Distinguishing read preference from shard routing

A sharded cluster consists of replica set shards:

```text
                     mongos
                       |
       +---------------+----------------+
       |                                |
    Shard A                          Shard B
   +--------+                       +--------+
   | P  S S |                       | P  S S |
   +--------+                       +--------+
```

There are **two distinct routing steps**:

1. `mongos` decides **which shards process the request** using shard key/predicates.
2. Within each shard replica set, **read preference** influences which replica member executes the read per policy.

```javascript
// Illustrating a non-transaction read policy only
db.orders.find({ tenantId: "T01", orderId: 104 })
  .readPref("secondaryPreferred")
```

`secondaryPreferred` does not make `mongos` bypass shard key conditions, nor does it turn scatter-gather into targeted. It governs **replica member selection inside each contacted shard**, without changing shard-key data distribution.

Reading from secondaries can observe stale data lagging behind the primary depending on replication lag and read concern. For reads inside transactions, strict rules require `primary` read preference. Never use `readPreference` as a band-aid for queries fanning out across too many shards.

## 18. Java MongoDB Sync Driver examples

In Java, queries should always pass whatever shard key values the business logic knows. The MongoDB Java Sync Driver dispatches commands via the configured topology; when connected to `mongos`, the cluster’s router determines target shards.

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.conversions.Bson;

public class ShardTargetingExample {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Missing MONGODB_URI");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("sharding_lab");
            MongoCollection<Document> orders =
                db.getCollection("orders");

            // A. Both fields of the ranged compound shard key present
            Bson targeted = Filters.and(
                Filters.eq("tenantId", "T01"),
                Filters.eq("orderId", 104)
            );
            Document order = orders.find(targeted).first();
            System.out.println("Targeted lookup: " + order);

            // B. Missing shard key: typically touches multiple shards
            Bson scatter = Filters.eq("status", "paid");
            for (Document d : orders.find(scatter).limit(5)) {
                System.out.println("Paid order: " + d.get("_id"));
            }
        }
    }
}
```

This example requires the `mongodb-driver-sync` dependency and `MONGODB_URI` pointing to a **lab sharded cluster** to observe routing. Against a regular replica set, both commands still read data but cannot demonstrate multi-shard target vs. scatter behavior.

**Important note:** calling `.first()` on a query missing the shard key does not magically tell the router which shard holds it. Limiting results to 1 or 5 is never proof that a query hit only one shard.

### 18.1. Running `explain` from Java

To inspect plans directly from Java, send the `explain` database command:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public class ExplainShardQuery {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Missing MONGODB_URI");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("sharding_lab");

            Document findCommand = new Document("find", "orders")
                .append("filter",
                    new Document("tenantId", "T01")
                        .append("orderId", 104));

            Document explainCommand =
                new Document("explain", findCommand)
                    .append("verbosity", "executionStats");

            Document explainResult = db.runCommand(explainCommand);
            System.out.println(explainResult.toJson());
        }
    }
}
```

To inspect scatter-gather, swap `filter` with:

```java
new Document("status", "paid")
```

Then compare **participating shard counts, chosen indexes, and merge stages**. Returned BSON schemas vary across versions, so production monitoring code should not hard-parse a fixed path like `queryPlanner.winningPlan.shards[0]` without verifying your version’s explain schema.

### 18.2. Why shouldn’t Java code pick shards manually?

Never hardcode things like:

```java
// Unsuitable pattern for standard sharded collections:
// "T01 always lives on mongo-shard-b:27017"
```

MongoDB can migrate data during balancing; an application connecting directly to an individual shard risks incomplete reads, misrouted writes, or stale metadata bugs. When working with a sharded cluster, use the URI/endpoint configured for `mongos` or the managed router entry point. The router tracks metadata and dispatches queries to shards.

## 19. Performance investigation before changing shard keys or APIs

When a MongoDB query runs slowly on a sharded cluster, never assume a missing index is the sole cause. Analyze in order:

1. **Capture the real query shape**: filters, BSON types, sort, skip, limit, projection, aggregation pipeline, collation, read preference.
2. **Verify the actual shard key**: never guess from ID names; inspect collection metadata and shard-key range placement.
3. **Check routing scope via `explain`**: one shard, a subset, or all shards.
4. **Inspect local plans per shard**: `IXSCAN`, `COLLSCAN`, `FETCH`, `SORT`, index bounds, and examined counts.
5. **Inspect merge stages**: `SHARD_MERGE`, merge sort, group, skip/limit, and intermediate data volumes in actual output.
6. **Cross-check data distribution**: is there an oversized tenant, write hotspot, chunk/range skew, or overloaded shard?
7. **Apply semantically sound fixes**: add shard key predicates when legitimately known and authorized; add local indexes; optimize pipelines or pagination; consider summaries for cross-shard reports.
8. **Measure on representative data**: test repeatedly while accounting for cache state, replication lag, concurrency, and network. A single `explain` on 15 documents cannot predict production latency.

### Diagnostic observation table

| Symptom | Likely cause | Investigation path |
| --- | --- | --- |
| `find({_id:...})` contacts all shards | `_id` is not in the shard key | Can trusted shard key fields be added to the API/filter? |
| Query with `tenantId` hits many shards | Compound key has extra fields; tenant spans ranges | Is the full key available for point lookups? |
| Targeted query is still very slow | Shard holds lots of data, local index unsuitable | Inspect local `explain`, keys/docs examined, and sort |
| Scatter-gather yet each shard reads very little | Good local index, missing shard-key predicate | Check cluster-wide necessity, fan-out, and merge cost |
| Slow global sort despite `limit` | Missing local index or heavy multi-shard merge | Check filter/sort index and top-K execution plan |
| Range on hashed shard key fans out | Hashing breaks raw range adjacency | Revisit access pattern; keep alternative key for range reports |
| Unexpected `$or` fan-out | One branch does not constrain the shard key | Inspect predicates on every branch |
| Aggregation `$match` fails to target as expected | Filter depends on computed/renamed field or non-sargable expr | Inspect optimized pipeline and `explain` |
| One shard overloaded | Skewed key distribution or hotspot | Inspect cardinality, splits/placement, and workload |
| Speed shifts after balancing | Range placement and cache shifted | Check metadata and measurement timestamps |

## 20. Common misconceptions

| Misconception | Why it is wrong | Correct understanding |
| --- | --- | --- |
| “Having the shard key in the filter always queries one shard” | Compound prefix/ranges can span multiple shards | Full-key equality usually hits one shard; prefixes only narrow scope |
| “`orderId` alone suffices because the compound key includes `orderId`” | Missing leading `tenantId` | With ranged compound keys, prefix order is crucial |
| “Having `_id` lets MongoDB know the shard immediately” | `_id` is not necessarily the shard key | `_id` index and shard routing are separate mechanisms |
| “`IXSCAN` proves the query is targeted” | Every shard in a scatter query can use an index | Check participating shard count |
| “Scatter-gather is always a bug” | System-wide reports may need data from all shards | Optimize local/merge work or maintain summary tables |
| “Hashed shard keys route every range query to one shard” | Hashing does not preserve raw value order | Equality targets better than ranges on hashed keys |
| “`limit(1)` only queries one shard” | Router doesn’t know which shard holds matching docs | `limit` does not replace a shard-key predicate |
| “Adding a `status` index makes `status` queries target one shard” | Local indexes do not change the shard key | Need shard-key constraints to narrow router targets |
| “`tenantId` matches by string even with wrong BSON type” | BSON string and number have distinct equality semantics | Standardize shard key data types |
| “Secondary read preference prevents scatter queries” | Read preference picks replica members inside shards | Shard-key routing remains unchanged |
| “After sharding, 15 documents split evenly across three shards” | Tiny datasets may sit in one range/shard | Inspect real distribution; never fabricate fan-out |
| “Moving `$match` before any stage is always valid” | Stages computing/renaming/unwinding fields change semantics | Reorder only when results stay identical |
| “Global top 10 only needs top 10 from one shard” | Other shards may hold newer records | Needs globally ordered merge |
| “Hardcoding tenant -> shard B is faster than `mongos`” | Chunks/ranges can migrate | Rely on official router and metadata |
| “One `explain` suffices to conclude performance” | Data, cache, balancing, and network vary | Measure representative workloads and per-shard local plans |

## 21. Practice exercises with answers

### Exercise 1. Full-key lookup

A collection has ranged shard key:

```javascript
{ tenantId: 1, orderId: 1 }
```

Which query is more likely to perform a single-shard point lookup?

```javascript
// A
db.orders.find({ orderId: 104 })

// B
db.orders.find({ tenantId: "T01", orderId: 104 })
```

**Answer:** B. It has equality on the **entire shard key**. A lacks the `tenantId` prefix, typically forcing the router to contact all relevant shards.

### Exercise 2. Including `tenantId` yet still hitting multiple shards

Tenant `T01` has millions of orders spanning three shard-key ranges across two shards. Does the query:

```javascript
db.orders.find({ tenantId: "T01" })
```

guarantee contacting only one shard?

**Answer:** No. With compound key `{tenantId:1,orderId:1}`, `tenantId` is the prefix, so the router narrows to that tenant, yet `T01`’s ranges may belong to **multiple shards**. For a point lookup when `orderId` is known, supply both fields.

### Exercise 3. Indexes do not alter routing

A collection is sharded on `{tenantId:1,orderId:1}` and has an index `{status:1}`. Does the query:

```javascript
db.orders.find({ status: "paid" })
```

guarantee avoiding scatter-gather?

**Answer:** No. The index speeds up filtering **on each shard**, yet `status` gives `mongos` no information on which shard-key ranges hold matches. The query can still fan out.

### Exercise 4. Hashed equality vs. range

A collection is sharded on:

```javascript
{ tenantId: "hashed" }
```

Compare:

```javascript
// A
db.orders.find({ tenantId: "T01" })

// B
db.orders.find({ tenantId: { $gte: "T01", $lt: "T50" } })
```

**Answer:** A uses equality on the hashed key, enabling the router to compute the hash and target the owning shard. B is a raw-value range, which does not map to a contiguous hash interval and usually requires scatter-gather.

### Exercise 5. `$or` with one unconstrained branch

```javascript
db.orders.find({
  $or: [
    { tenantId: "T01", orderId: 104 },
    { status: "pending" }
  ]
})
```

Why might this query need to contact every shard?

**Answer:** The first branch has full-key equality, but the second branch can match `pending` orders for **any tenant on any shard**. The overall `$or` must evaluate that branch as well.

### Exercise 6. Compute paid total for tenant T01

Write an aggregation returning total `paid` order count and `paid` revenue for `T01` on the sample dataset.

**Answer:**

```javascript
db.orders.aggregate([
  { $match: { tenantId: "T01", status: "paid" } },
  {
    $group: {
      _id: "$tenantId",
      count: { $sum: 1 },
      revenue: { $sum: "$total" }
    }
  }
])
```

Logical output: `{_id:"T01", count:4, revenue:660}`. Because only the `tenantId` prefix of the compound shard key is constrained, routing may hit one or multiple shards holding `T01`.

### Exercise 7. Why does `findOne({_id:...})` still scatter?

Shard key is `{tenantId:1,orderId:1}`; `_id` has a unique index. The app runs:

```javascript
db.orders.findOne({ _id: "T01-104" })
```

Does the `_id_` index guarantee `mongos` routes to a single shard?

**Answer:** No. The `_id_` index helps locate documents **within a shard**, yet tells the router nothing about the shard-key range. If tenant `T01` is already authenticated and `orderId: 104` is known, include `tenantId` and `orderId` in the filter.

### Exercise 8. Reading both dimensions of explain

Hypothetical measurements:

```text
Query A: 1 shard, 40,000 documents examined
Query B: 3 shards, 30 total documents examined
```

Which query is better targeted? Which is guaranteed to be faster?

**Answer:** A is better targeted because it hits only one shard. Neither can be declared faster from those two numbers alone: A may lack a local index, while B incurs fan-out/network/merge overhead despite reading very few documents. Inspect local plans, timings, caches, and environment.

### Exercise 9. Global sort and limit

A `status: "paid"` query hits three shards and requests the 10 newest orders system-wide. Why isn’t taking the 10 newest from Shard A enough?

**Answer:** Shard B or C may hold orders newer than those on A. The router must combine results across shards, typically via an optimized merge sort/top-K plan. `limit(10)` does not make a query target one shard.

### Exercise 10. API knows the tenant yet forgets to pass it in the filter

An endpoint successfully authenticates tenant `T01`, yet the query code runs:

```javascript
db.orders.find({ orderId: 104 })
```

What issues exist besides performance?

**Answer:** Performance-wise, missing the shard key prefix can cause scatter-gather. Business/security-wise, `orderId` may collide across tenants; omitting the tenant filter risks returning unauthorized data from another tenant. Always enforce the authenticated tenant context in the filter.

### Exercise 11. Small dataset and participating shard count

You shard a 15-document lab collection and run `explain` on `status: "paid"`. `explain` shows only one shard participating. Can you conclude `status` is targeted by the shard key?

**Answer:** No. The newly sharded collection likely still keeps all relevant shard-key ranges on one shard because the dataset is tiny. Inspect placement metadata. Never claim single-shard execution in a tiny lab proves `status` predicates target narrowly in a distributed production cluster.

### Exercise 12. Choosing how to improve a system-wide report

An hourly report totals `paid` revenue across all tenants; the shard key is `{tenantId:1,orderId:1}`. Should you add `tenantId: "T01"` to the query to hit fewer shards?

**Answer:** No, because that breaks the “all tenants” business requirement. Instead, consider local indexes on `status` and time, filtering by reporting period, checking aggregation split/merge execution, or maintaining a separate summary table where appropriate.

## 22. Practical workflow to avoid unnecessary fan-out

When designing or tuning queries on a sharded collection:

1. **State the business question clearly**: one order, one tenant, a time window, or all tenants?
2. **Verify the real shard key**: fields, field order, ranged/hashed, and BSON types.
3. **Compare filters against the shard key**: full equality, prefix, range, `$in`, or missing shard-key predicate?
4. **Enforce tenant authorization** before inserting `tenantId` into filters; never trade data security for speed.
5. **Run `explain` via `mongos`**: verify single shard, subset, or multi-shard; never guess from indexes.
6. **Inspect each local plan**: matching index, keys/docs examined, sorts, and covered queries if applicable.
7. **Inspect merges**: sorting, grouping, skip/limit, and data transferred across shards.
8. **Check real data distribution**: small collections may not split across shards yet; large tenants may span wider than expected.
9. **Refine query shapes before changing the shard key**: supply known keys, preserve exact types, tune indexes and pagination.
10. **Measure against real workloads**: latency, fan-out, network, cache, balancing, and data skew; one `explain` never replaces ongoing monitoring.

## Conclusion

In MongoDB sharding, **`mongos` routes based on the shard key and data placement metadata**, not on whether a field is indexed or whether an ID “looks like” it embeds a tenant ID. With **equality on the full shard key**, queries can generally reach a single shard; with a **prefix or range**, the router can narrow down to a subset of shards; queries **lacking shard key conditions** typically **scatter-gather**.

However, a targeted query can still be slow if a shard lacks an index, and scatter-gather can be completely legitimate for cluster-wide reports. Compound shard keys, hashed shard keys, `$or`, BSON types, and range placement all alter routing behavior. Good practice is to **include valid shard-key predicates whenever the key is genuinely known, verify via `explain`, and optimize per-shard execution and merge steps** while preserving exact business results.

### Official references

- [MongoDB Manual — Sharding](https://www.mongodb.com/docs/manual/sharding/)
- [MongoDB Manual — Shard Keys](https://www.mongodb.com/docs/manual/core/sharding-shard-key/)
- [MongoDB Manual — Sharded Cluster Query Router](https://www.mongodb.com/docs/manual/core/sharded-cluster-query-router/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual — Sharded Collection Operations](https://www.mongodb.com/docs/manual/core/sharded-cluster-query-router/#query-routing)
