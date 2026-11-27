# Write Hotspots, Data Skew, and Queries Missing the Shard Key

**Sharding** divides a MongoDB collection’s data into parts stored across multiple **shards** to expand storage capacity and distribute load. However, having multiple shards does not guarantee an even workload distribution. A poorly chosen **shard key** can cause most writes to pile onto one shard, some shards to hold far more data than others, or every request to hit every shard even when returning a single document.

Three classic symptoms:

1. **Write hotspot:** many concurrent inserts/updates hit the same shard key region, chunk, or shard. One shard saturates while others sit idle.
2. **Data skew:** storage size, document count, range/chunk count, or distinct shard key counts are unevenly distributed. Some regions hold excessive data or cannot split effectively.
3. **Queries missing the shard key:** `mongos` cannot determine which shard holds the target document, so it must **broadcast/scatter-gather** to many or all shards; latency, connection usage, CPU, and network traffic can grow with shard count.

Crucially, these three issues are **not identical**: a 50/50 data split across two shards can still carry a 95/5 load split if 95% of requests hit one customer; conversely, unequal chunk counts do not necessarily prove storage or QPS imbalance. Remediation must start by **identifying the skew type**, inspecting **query patterns**, and verifying with metrics and `explain`.

This lesson belongs to the **Sharding** chapter of the *MongoDB Document Database Engine* module. It focuses on evaluating shard keys, diagnosing root causes, fixing queries for targeting, checking the balancer, and planning safe shard key changes.

## Learning objectives

After this lesson, you will be able to:

- Describe the roles of `mongos`, config servers, shards, shard keys, and chunks/ranges.
- Distinguish **range sharding** from **hashed sharding**, knowing the trade-off between write spread and range-query locality.
- Explain why shard keys with **monotonically increasing/decreasing** values can create write hotspots.
- Identify **low cardinality**, **high frequency**, **hot tenants**, and the risk of indivisible/jumbo chunks.
- Evaluate differences among **data skew**, **chunk skew**, **working-set skew**, **read skew**, and **write skew**.
- Write and verify **targeted queries** using the full shard key or a compound shard key prefix where appropriate.
- Detect `scatter-gather` via `explain` and understand when broadcasting is acceptable.
- Use `sh.status()`, `getShardDistribution()`, `getShardedDataDistribution()`, balancer status, and `analyzeShardKey` to assist diagnosis.
- Plan controlled improvements to indexes, shard keys, routing, data models, zone placement, or resharding.
- Recognize impacts on `updateOne`, `updateMany`, `deleteMany`, upserts, unique indexes, and the Java Driver.

> **Version and scope:** Illustrative syntax uses modern MongoDB and `mongosh` through a **sharded cluster** with appropriate administrative privileges. `sh.shardCollection()`, `reshardCollection`, zone balancing, or index changes are not meant for production without a rollout plan. Features like `analyzeShardKey` (MongoDB 7.0+), `sh.getShardedDataDistribution()` (MongoDB 6.0.3+), and initial chunk distribution vary by server version. Cross-check documentation for your exact version, FCV, and Atlas/self-managed topology.

## 1. Basic shard routing architecture

A MongoDB sharded cluster consists of three main component groups:

~~~text
Java service / mongosh / application
                |
                v
         mongos (query router)
                |
        +-------+-------+
        |       |       |
        v       v       v
      Shard 0 Shard 1 Shard 2
      replica replica replica
       set     set     set
        ^       ^       ^
        |       |       |
       Config servers: metadata / chunk ranges
~~~

Applications normally connect to **`mongos`**, rather than manually hashing IDs modulo shard count and opening direct connections to shard `mongod` instances. The query router uses **cluster metadata and the shard key** to determine which shards must participate.

### 1.1. Key terminology

| Term | Meaning |
|---|---|
| **Shard** | A unit storing a subset of data, typically a replica set. |
| **`mongos`** | Query router receiving requests, routing to needed shards, and merging results when multiple shards participate. |
| **Config Server Replica Set** | Stores partitioning metadata, shard membership, and zone/range mappings. |
| **Shard key** | One or more fields determining data distribution and routing; can be ranged, hashed, or compound. |
| **Chunk / range** | A contiguous interval in the shard key space; a shard owns that range. |
| **Balancer** | Monitors data volumes per shard/collection and moves ranges to balance when needed, respecting zone constraints. |
| **Targeted operation** | Router narrows down to one shard or a small subset of shards from predicates and metadata. |
| **Broadcast/scatter-gather** | Router sends the query to many/all shards, receives results, and merges them. |
| **Resharding** | Changing the shard key and/or redistributing a collection via supported mechanisms. |

### 1.2. How a request is routed

With a hypothetical shard key `{tenantId:1, orderId:1}`:

~~~javascript
// Both components present -> opportunity to target one shard.
db.orders.findOne({
  tenantId: "TENANT-A",
  orderId: "ORD-107"
})
~~~

`mongos` locates the range owning that shard key pair. If the query supplies only `orderId` without the leading `tenantId`, the router cannot narrow down the target range:

~~~javascript
db.orders.findOne({ orderId: "ORD-107" })
// May have to probe multiple shards to find the document.
~~~

Note: **indexes** and **shard targeting** are two separate concerns. An `{orderId:1}` index on each shard makes the lookup **inside each shard** fast, yet does not tell `mongos` which shard owns `orderId`. The query can still broadcast to all shards.

### 1.3. Why doesn’t adding shards always cure slowness?

Suppose a system has four shards, yet every new insert carries a monotonically increasing `createdAt` that funnels solely into the trailing range. Adding a fifth shard will not make all five shards concurrently absorb fresh inserts. Or if an API looks up users by `email` while the shard key is `tenantId`, each request may have to hit all five shards. With more shards, fan-out overhead can grow even worse.

**Sharding scales distributed capacity when the shard key and queries actually leverage that distribution.**

## 2. Three imbalance types and how to recognize them

Do not slap a single “unbalanced shard” label on every symptom.

| Skew type | Measurement example | Common cause | Measures to consider |
|---|---|---|---|
| **Data size skew** | Shard A 900 GB, B 250 GB, C 280 GB on same collection | Large ranges, slow balancer, zones, indivisible chunks | Balancer/zone/range investigation, reshard if key is poor. |
| **Chunk-count skew** | A 100 chunks, B 50, C 52 | Differing chunk sizes, distribution policies, migrations | Do not conclude from chunk count alone; inspect owned bytes. |
| **Read/load skew** | A 12k reads/s, B 1k, C 900 | Hot tenant/key/range, cache misses, concentrated queries | Query/index/data placement/tenant partitioning. |
| **Write skew** | A 9k writes/s, B/C very low | Monotonic key, hot key, app behavior | Hashed/compound key, bucketed writes, repartitioning. |
| **Working-set skew** | A has 20 GB hot data on 8 GB RAM, B has 100 GB cold data | Access patterns, index sizes, tenant hotspots | Memory/index/workload isolation, shard key/zones. |
| **Scatter-gather overhead** | Every read API touches 8/8 shards | Predicates missing shard key, secondary-key lookups | Pass shard key in API, rethink key choice/lookup strategy. |
| **Migration imbalance** | Balancer migrations failing/slow | Jumbo/indivisible chunks, disk/network/DDL, zones | Inspect status/logs/range distribution. |

### 2.1. Even storage does not mean even load

Example measurement:

| Shard | Owned data | Reads/s | Writes/s |
|---|---:|---:|---:|
| `shardA` | 310 GB | 9,500 | 8,200 |
| `shardB` | 305 GB | 600 | 500 |
| `shardC` | 315 GB | 750 | 520 |

These are **illustrative figures**, not a MongoDB benchmark. Data sizes are nearly identical, yet **shardA is a hot shard**. A data-size-based balancer may consider the cluster balanced while A’s CPU/IOPS near saturation.

### 2.2. Equal chunk counts do not mean equal data

Two shards each holding 100 chunks does not prove equal storage: some ranges may contain larger documents or different document counts. Check **`ownedSizeBytes`**, `numOwnedDocuments`, and live workload metrics, especially since chunk sizing and partitioning mechanics vary by version.

### 2.3. Selectivity properties of a shard key

A shard key has three major characteristics:

- **Cardinality:** number of distinct values, affecting ability to split ranges/chunks.
- **Frequency distribution:** whether a single value repeats excessively (e.g., one `tenantId` owning 85% of orders).
- **Monotonicity:** whether new values always ascend/descend like timestamps or sequential IDs.

A high-cardinality key that ascends monotonically can still create an **insert hotspot**. A key that hashes evenly while the app queries only one tenant can still suffer a **hot tenant**. Never select a shard key based on a single property.

## 3. Illustrative data model and safe sharding lab

This lesson uses **orders** from a multi-tenant commerce platform:

~~~javascript
{
  _id: "O-1001",
  orderId: "O-1001",
  tenantId: "T-A",
  customerId: "C-10",
  status: "PAID",
  createdAt: ISODate("2026-06-01T09:00:00Z"),
  totalMinor: NumberLong(125000)
}
~~~

Daily volume may reach tens of millions of orders, with 80% belonging to a handful of large tenants. Common APIs:

- `GET /tenants/T-A/orders/O-1001` → fetch order by **tenant + order ID**.
- `GET /orders/O-1001` → fetch order by **order ID alone**.
- `GET /tenants/T-A/orders?from=...&to=...` → list by **tenant and date**.
- `GET /tenants/T-A/orders?status=PAID` → filter by **tenant and status**.
- Admin dashboard → total PAID count and revenue across **all tenants** by period.
- Import service → high-volume inserts with continuously increasing `createdAt`.

These access patterns **conflict**: `{createdAt:1}` aids date-range reports yet risks write hotspots, `{orderId:"hashed"}` spreads inserts yet fans out time-range queries, and `{tenantId:1,orderId:1}` aids tenant-scoped lookups yet risks one huge tenant dominating ranges.

### 3.1. Creating sample data only in a lab database

The following script is a **standalone `mongosh` example**. It inserts sample documents into a new database, deletes nothing, and makes no shard topology changes.

~~~javascript
const lab = db.getSiblingDB("shard262_lab")

const docs = [
  {
    _id: "O-1001", orderId: "O-1001", tenantId: "T-A",
    customerId: "C-10", status: "PAID",
    createdAt: ISODate("2026-06-01T09:00:00Z"),
    totalMinor: NumberLong(125000)
  },
  {
    _id: "O-1002", orderId: "O-1002", tenantId: "T-A",
    customerId: "C-10", status: "CREATED",
    createdAt: ISODate("2026-06-02T09:00:00Z"),
    totalMinor: NumberLong(70000)
  },
  {
    _id: "O-1003", orderId: "O-1003", tenantId: "T-B",
    customerId: "C-20", status: "PAID",
    createdAt: ISODate("2026-06-03T09:00:00Z"),
    totalMinor: NumberLong(95000)
  },
  {
    _id: "O-1004", orderId: "O-1004", tenantId: "T-C",
    customerId: "C-30", status: "SHIPPED",
    createdAt: ISODate("2026-06-04T09:00:00Z"),
    totalMinor: NumberLong(150000)
  },
  {
    _id: "O-1005", orderId: "O-1005", tenantId: "T-A",
    customerId: "C-11", status: "PAID",
    createdAt: ISODate("2026-06-05T09:00:00Z"),
    totalMinor: NumberLong(190000)
  },
  {
    _id: "O-1006", orderId: "O-1006", tenantId: "T-B",
    customerId: "C-22", status: "CANCELLED",
    createdAt: ISODate("2026-06-06T09:00:00Z"),
    totalMinor: NumberLong(35000)
  }
]

lab.orders_local.insertMany(docs)

lab.orders_local.find(
  {},
  { _id: 0, orderId: 1, tenantId: 1, status: 1, createdAt: 1 }
).sort({ orderId: 1 })
~~~

Re-running the script with existing `_id` values triggers duplicate key errors, not a sharding failure. To practice each design separately, create fresh lab collections and copy fixtures **only inside the test database**.

### 3.2. Demoing three sharding approaches

To compare, a **lab cluster with at least two shards connected via `mongos`** can create three separate collections. **The commands below are administrative configuration samples; run them only after understanding their impact, verifying your lab environment, and confirming proper privileges.** Never apply them to live production collections.

~~~javascript
const lab = db.getSiblingDB("shard262_lab")

// Three collections assumed to have their own data and supporting indexes.
// Each sh.shardCollection line illustrates one shard key option.

// A. Ranged by timestamp: illustrates hot newest-range risk.
sh.shardCollection(
  "shard262_lab.orders_ranged",
  { createdAt: 1 }
)

// B. Hashed by orderId: spreads sequential IDs more evenly via hash.
sh.shardCollection(
  "shard262_lab.orders_hashed",
  { orderId: "hashed" }
)

// C. Compound ranged by tenantId + orderId.
sh.shardCollection(
  "shard262_lab.orders_tenant",
  { tenantId: 1, orderId: 1 }
)
~~~

For existing populated collections, key selection, compatible indexes, unique constraints, chunk initialization, and DDL privileges must satisfy server/cluster requirements. In the lab, create `orders_ranged`, `orders_hashed`, and `orders_tenant` and load data as you practice; do not assume sharding commands automatically copy data from `orders_local`. When a collection has only a few documents, the planner/balancer may not distribute across shards yet; **a six-order fixture does not prove real-world load distribution**.

### 3.3. An environment verification tip

When opening `mongosh`, verify the router:

~~~javascript
db.adminCommand({ hello: 1 })
// On mongos, output typically includes:
//   msg: "isdbgrid"
~~~

And view sharding metadata:

~~~javascript
sh.status()
~~~

`sh.status()` is meaningful when connected to **`mongos`**. If connected directly to a standalone or shard `mongod`, sharding commands will error or omit expected cluster info. Never run test DDLs to “see if it works” on production.

## 4. Write hotspots from monotonically increasing or decreasing shard keys

A shard key like `{createdAt:1}` or sequential IDs can cause recent inserts to hit the **same trailing edge** of the key space continually.

### 4.1. Range sharding splits by key intervals

Suppose current chunks are:

~~~text
createdAt ranges (min inclusive, max exclusive)

Shard A: (-∞, 2026-03-01)
Shard B: [2026-03-01, 2026-05-01)
Shard C: [2026-05-01, +∞)
                                 ^
                     all new June orders
                     land in trailing range on Shard C
~~~

This is an **illustrative diagram**, not real cluster output. When the application always sets `createdAt = new Date()`:

- Each insert advances monotonically in time.
- `mongos` routes most new inserts to the **leading/trailing chunk** bounded by `MinKey`/`MaxKey`.
- The shard owning the “newest” chunk absorbs most write throughput.
- A day later, the balancer may migrate a newer chunk; **the hotspot shifts from Shard C to another shard**, yet at any instant writes remain concentrated.

The MongoDB Manual notes that **monotonic** shard keys can create **hot chunks / hot shards**. Balancing **historical storage volume** does not equal balancing the **stream of new inserts**. See [Choose a Shard Key](https://www.mongodb.com/docs/manual/core/sharding-choose-a-shard-key/).

### 4.2. Why doesn’t the balancer cure this at the root?

The balancer distributes **ranges by data volume** per policy, moving newer chunks to other shards when splits/migrations qualify. Yet with a monotonic key, incoming inserts still pour into the **tail range** at any given moment. Moving chunk ownership only **relocates the hotspot**, rather than turning one single edge range into multiple concurrent write targets.

Never try to “fix” this workload merely by adding shards or enabling the balancer and assuming new writes will auto-balance.

### 4.3. Example of a continuously incrementing ID

~~~javascript
{
  orderSeq: NumberLong(1000000001),
  tenantId: "T-A",
  createdAt: ISODate("2026-11-14T00:00:00Z")
}
~~~

Shard key `{orderSeq:1}` has high cardinality yet is **monotonic**. As long as every new `orderSeq` exceeds all prior values, writes route to the upper range, creating a hot chunk. **High cardinality is insufficient** to prevent write hotspots.

### 4.4. Not every timestamp field causes hotspots

If the timestamp is only a **secondary field** while the shard key is `{orderId:"hashed"}`, increasing `createdAt` does not force inserts onto one shard. What causes the hotspot above is the **partitioning shard key value** increasing monotonically, not the mere presence of a time field.

Furthermore, timestamps inside a **compound** shard key behave differently depending on the leading field and its distribution. For example, `{tenantId:1,createdAt:1}` has many `tenantId`s, yet **one super-hot tenant** still funnels all of that tenant’s new writes into one hot edge range. Always analyze **the entire shard key pattern**, not individual fields in isolation.

### 4.5. Hotspots can still happen when the key is non-monotonic

Suppose the application maintains a `counters` record:

~~~javascript
db.counters.updateOne(
  { _id: "GLOBAL_ORDER_COUNT" },
  { $inc: { value: 1 } }
)
~~~

Even if `orders`’ shard key hashes perfectly, `counters.GLOBAL_ORDER_COUNT` remains **one hot document** if every request updates it. This contention is a **hot document**, unsolvable by changing the `orders` shard key. You must split the counter into buckets, use asynchronous aggregation, or relax update rules if business permits.

### 4.6. Signals of a monotonic hotspot

- The shard owning the **upper/lower edge range** shows high write QPS/CPU/IOPS.
- New inserts almost exclusively carry **ascending** or **descending** shard key values.
- The balancer frequently migrates ranges, yet the hot shard **moves around over time**.
- Indexing/replication lag on the hot shard outpaces other shards.
- Historical storage may look balanced while new writes remain sharply skewed.

When investigating, sample sufficiently short time windows to trace **the hotspot’s movement**, rather than relying solely on daily averages.

## 5. Hashed sharding: spreading writes, but at what trade-off?

**Hashed sharding** uses a hash of the shard key value to assign ranges. Two consecutive ascending IDs usually produce non-adjacent hashes, letting inserts scatter across chunks/shards.

### 5.1. Example sharding by hashed orderId

~~~javascript
// Illustrative only on a lab cluster with suitable collection/metadata.
sh.shardCollection(
  "shard262_lab.orders_hashed",
  { orderId: "hashed" }
)
~~~

For a scalar `orderId` with high cardinality and low duplication, a hashed key generally spreads writes better than monotonic `{orderSeq:1}`, once ranges/initial distribution are established.

### 5.2. Equality lookups are typically targeted

~~~javascript
db.getSiblingDB("shard262_lab").orders_hashed.findOne({
  orderId: "O-1005"
})
~~~

The router computes the hash of the specific `orderId` and pinpoints the chunk/shard holding it. **Equality on a hashed shard key** is a well-suited access pattern.

### 5.3. Range queries typically lose locality

~~~javascript
db.getSiblingDB("shard262_lab").orders_hashed.find({
  orderId: {
    $gte: "O-1000",
    $lt: "O-2000"
  }
})
~~~

Order IDs in `[O-1000, O-2000)` **are not contiguous under the hash**, so the router cannot restrict execution to a tight run of chunks. Range queries on a hashed field often **broadcast**, even if local indexes still assist filtering. See [Hashed Sharding](https://www.mongodb.com/docs/manual/core/hashed-sharding/).

### 5.4. Hashed keys do not fix hotspots lacking key distinctness

Suppose the shard key is:

~~~javascript
{ tenantId: "hashed" }
~~~

If 80% of orders have `tenantId: "T-BIG"`, `hash("T-BIG")` still yields **one single hash value**; they still concentrate in the same chunk/shard. Hashing **does not automatically scatter identical values** across shards. If one huge tenant must span multiple shards, the shard key needs an additional discriminating dimension **within the tenant**, such as `orderId`, weighing the trade-off for tenant-wide queries.

### 5.5. Hashed keys and traditional indexes

Hashed indexes do not support every query/filter style like B-tree ranged indexes, and hashed shard keys restrict uniqueness. A hashed-sharded collection still needs **supplementary indexes on each shard** for queries on `createdAt`, `status`, or `customerId`, though local indexes **never make queries shard-targeted by themselves**.

Do not choose a hashed shard key solely to balance inserts while ignoring your product’s most critical queries. Choosing a shard key balances:

| Goal | Ranged key | Hashed key |
|---|---|---|
| **Range** queries on the shard key itself | Usually good locality. | Often hits multiple shards. |
| Full-key equality | Usually targeted. | Usually targeted. |
| Inserts with monotonic keys | Prone to hot edge chunks. | Usually spreads better when values vary well. |
| Hot tenant with `tenantId`-only key | One tenant stays on one key. | One tenant still hashes to one value. |
| Sorting by key value | Can leverage order/range locality. | Hashing destroys natural key order. |
| Cluster-wide unique constraints | Subject to shard key/index rules. | Hashed indexes cannot be unique; must rethink uniqueness. |

**Section takeaway:** Hashed sharding is a tool to mitigate **monotonic write hotspots**, not a universally optimal choice for every workload. See [Troubleshoot Shard Keys](https://www.mongodb.com/docs/manual/core/sharding-troubleshooting-shard-keys/).

## 6. Compound shard keys: balancing tenant isolation and load distribution

In multi-tenant applications, including `tenantId` in the shard key tells the router where a tenant’s data lives. Yet it is a **trade-off**: a tenant can grow huge, may need multiple shards, and some APIs only know `orderId`.

### 6.1. `{tenantId:1}`: targeted by tenant, yet prone to hot tenants

~~~javascript
// Design sample; do not run on production.
sh.shardCollection(
  "shard262_lab.orders_tenant_only",
  { tenantId: 1 }
)
~~~

Pros: `{tenantId:"T-A"}` targets ranges holding tenant A; per-tenant filtering is natural. Cons:

- **Limited cardinality:** with only 5 tenants, there are very few distinct values to partition.
- **High frequency:** one tenant with 80% of orders funnels most writes onto one key.
- **Splittability:** many documents sharing **the exact same shard key value** cannot be split across ranges using that value, creating an **indivisible chunk**.

Never assume a huge tenant spreads automatically when you add shards if **its entire partitioning key is one identical `tenantId` value**.

### 6.2. `{tenantId:1,orderId:1}`: boosts cardinality, with nuances

~~~javascript
sh.shardCollection(
  "shard262_lab.orders_tenant",
  { tenantId: 1, orderId: 1 }
)
~~~

Within a tenant, distinct `orderId`s multiply shard key values so ranges can split. The router can handle:

~~~javascript
// Full equality on compound shard key: typically routes to one shard.
lab.orders_tenant.findOne({
  tenantId: "T-A",
  orderId: "O-1005"
})

// Prefix equality tenantId: may hit one or multiple shards
// because a tenant's orders can span multiple ranges.
lab.orders_tenant.find({
  tenantId: "T-A"
})
~~~

**Having the shard key prefix does not always mean one shard.** If tenant A owns chunks on several shards, the router sends the query to **the relevant subset of shards**, still skipping shards that hold none of A’s ranges.

### 6.3. Sequential orderIds can still create a hot edge *within a tenant*

If `orderId` increments sequentially within `T-A`, compound range key `{tenantId:1,orderSeq:1}` funnels new inserts **for `T-A`** into `T-A`’s trailing range. With many active tenants writing concurrently, load spreads across tenants, yet one giant tenant can still run hot.

An option worth evaluating:

~~~javascript
// Compound hashed shard key: tenantId prefix, hashed orderId suffix.
// Requires a server version supporting compound hashed shard keys.
sh.shardCollection(
  "shard262_lab.orders_tenant_hashed",
  { tenantId: 1, orderId: "hashed" }
)
~~~

With plenty of distinct `orderId`s, hashing `orderId` improves the ability to spread **a single tenant’s** writes across ranges; actual effectiveness depends on chunk initialization, zones, balancer, and workload. Full equality `tenantId + orderId` can target narrowly; `tenantId`-only queries may contact multiple shards to gather the whole tenant. **Never declare a new shard key spreads a hot tenant evenly before measuring it.**

### 6.4. Adding a bucket key when workloads need multiple write points

Another technique embeds a **distribution bucket** in the key:

~~~javascript
{
  tenantId: "T-A",
  bucket: 7,            // Derived from a deterministic hash of orderId.
  orderId: "O-1005",
  createdAt: ISODate("2026-06-05T09:00:00Z")
}
~~~

An application can pick a shard key like `{tenantId:1,bucket:1,orderId:1}` in an appropriate design. Computing `bucket` **deterministically** from `orderId` enables:

- Spreading one tenant’s writes across multiple bucket ranges.
- Lookups by `orderId` to recompute `bucket` and pass **all shard key fields** for targeted routing.
- `tenantId`-only queries lacking `bucket` still must scan the tenant’s buckets, increasing fan-out.

**Never pick a fresh random bucket per insert** if lookup paths cannot derive the bucket from the ID. If the key includes `bucket` and `orderId`, ensure APIs can supply the complete key.

### 6.5. Choosing key order based on real APIs

| Candidate shard key | Favorable queries | Risks |
|---|---|---|
| `{tenantId:1}` | Per-tenant lookups/listings. | Hot tenant, low cardinality. |
| `{tenantId:1,orderId:1}` | Full `tenant+order` equality; tenant prefix. | Sequential `orderId` can run hot inside a tenant; order-only lacks prefix. |
| `{tenantId:1,orderId:"hashed"}` | Full `tenant+order` equality; spreads order IDs. | Tenant-wide list may hit multiple shards; `orderId` ranges lose locality. |
| `{orderId:"hashed"}` | `orderId` equality; spreads order IDs. | Tenant-wide queries and date ranges broadcast. |
| `{createdAt:1}` | Date ranges. | Monotonic hotspot on new writes. |
| `{tenantId:1,bucket:1,createdAt:1}` | `tenant+bucket+date` when bucket is known. | Tenant-date fans out across buckets; higher app complexity. |

A single ideal key for every query rarely exists. You may need to adjust APIs to pass tenant/key fields, introduce **read models/secondary indexes**, or separate OLTP from analytical workloads instead of forcing every requirement into one shard key.

## 7. Data skew from low cardinality and high-frequency values

**Low cardinality** and **high frequency** are two root causes distinct from monotonicity.

### 7.1. Low cardinality

For example, shard key `{region:1}` where data only contains:

~~~javascript
{ region: "NORTH" }
{ region: "SOUTH" }
{ region: "CENTRAL" }
~~~

With only 3 region values on a 12-shard cluster, distinct key regions are scarce; adding shards cannot split data within each region. A fix may add higher-cardinality shard key components, such as `{region:1,tenantId:1,orderId:1}`, if query and write distributions align.

Never append suffix fields solely to “make the key longer”; evaluate **cardinality, frequency, monotonicity, query prefixes**, and unique index implications.

### 7.2. High-frequency value

Suppose order frequencies are:

| Tenant | % of documents | % of writes |
|---|---:|---:|
| T-BIG | 72% | 91% |
| T-A | 12% | 3% |
| T-B | 9% | 4% |
| Other tenants | 7% | 2% |

Numbers are **hypothetical examples**. Under `{tenantId:1}`, `T-BIG` creates a massive hotspot; hashed `tenantId` still maps all of `T-BIG` to one hash. If a huge tenant owns **a single shard key value**, do not expect the balancer to split documents sharing that exact value across multiple chunks via migrations.

### 7.3. Indivisible chunk: a range that cannot split further

A **chunk/range** can grow huge yet remain unsplittable if its documents lack enough distinct shard key values to establish a valid split point. This is commonly described as an **indivisible chunk**, related to **jumbo** states depending on server version/diagnostics.

~~~text
Chunk A holds all documents with tenantId = "T-BIG"
         |
         v
All share the exact same shard key value
         |
         v
No split point exists within the same value
         |
         v
Adding shards or running the balancer will not
magically split it into balanced chunks.
~~~

The root fix is to **change the partitioning model / add a shard key component / reshard** when data and version allow, or partition load along another dimension. Do not start with manual `moveChunk` before understanding why the chunk cannot split.

### 7.4. Jumbo chunks have multiple causes

Oversized data regions, insufficient distinct key values, huge documents, migration constraints, balancer thresholds, or index/topology issues can trigger stuck-migration warnings. **Do not diagnose every storage skew as a jumbo chunk**; inspect balancer state, chunk details, server logs, and shard key characteristics.

### 7.5. Data size skew can be intentional by design

If an organization uses **zones** to isolate data by country or tenant tier, Shard A may legitimately hold more data than B due to **data placement policy**. The balancer must respect zone assignments and eligible shards per zone. Unequal GB counts alone do not prove a bug when the deployment prioritizes data residency or workload isolation.

## 8. The balancer: balances data, not a QPS dispatcher

The balancer manages range/chunk moves to satisfy data placement policies. It **does not dynamically rewrite document shard keys based on current CPU request load**.

### 8.1. What can the balancer do?

- Move ranges when eligible imbalances are detected.
- Respect **zone rules** and placement constraints.
- Distribute initial/accumulated data per shard settings, chunk sizing, and server version.
- Reduce **data imbalance** when chunks/ranges are movable.

### 8.2. What can’t the balancer fix by itself?

- **Monotonic** shard keys still send new writes to the trailing range.
- A tenant with **one shard key value** cannot spread across shards via the balancer alone.
- Queries missing the shard key still fan out to shards determined by `mongos`.
- A **hot document** remains one single document; migrating it relocates the heat rather than parallelizing writes to that document across shards.
- A collection balanced in bytes can still be skewed in **QPS/CPU/working set**.

### 8.3. Checking balancer status

On `mongos` with metadata read privileges:

~~~javascript
sh.getBalancerState()

db.adminCommand({ balancerStatus: 1 })

sh.status(true)
~~~

`sh.getBalancerState()` indicates whether the balancer is enabled; it is **insufficient** to conclude migrations are succeeding or the collection is balanced. `balancerStatus` and logs show detailed progress by version; `sh.status(true)` prints chunk/placement details. During production investigations, pair monitoring/Atlas metrics with commands rather than trusting a single shell snapshot.

### 8.4. Do not casually disable the balancer or move ranges by hand

A hasty reaction:

~~~text
Hot shard -> Stop balancer -> Manually move a few chunks
~~~

can leave data unbalancing over time, or merely **shift** the hotspot onto another shard. Manual/forced migrations also carry network, disk, and jumbo/indivisible chunk risks. Act only after finding the root cause, with rollout/rollback plans aligned to server version docs.

### 8.5. When is zone sharding useful?

**Zones** bind shard key ranges to specific shard groups—for example, EU data in EU regions or premium tenants on dedicated hardware. Yet if a zone contains only **one shard** and an entire hot tenant is pinned there, throughput remains capped.

Zones help **placement/data residency/workload isolation**, without increasing cardinality or curing monotonic keys. When designing zones, provision enough shards/capacity per zone and remember the balancer respects zone boundaries.

## 9. Queries missing the shard key: the cause of scatter-gather

When `mongos` cannot identify target shards from **query predicates and shard key metadata**, the router may send the query to **all shards** and combine results. This is **broadcast** or **scatter-gather**.

### 9.1. Targeted vs. scatter-gather diagram

~~~text
Query with full shard key or routable prefix:

Application
    |
  mongos
    |
    +----------------> Shard B
    |                  (owns matching range)
    |
    +-- skips Shard A/C when metadata excludes them

Query missing the shard key:

Application
    |
  mongos
    |
    +------------> Shard A ----+
    +------------> Shard B ----+--> merge results --> Client
    +------------> Shard C ----+
~~~

Scatter-gather can be expensive because:

- Many shards must parse/filter/execute, even when **zero documents match** on those shards.
- Extra network round trips/connections and merge overhead on `mongos` or a merge shard.
- Request tail latency can be dragged down by the **slowest shard**.
- High-QPS APIs multiply shard operations: 1,000 req/s × 8 shards ≈ up to 8,000 shard-level query participations/s (**illustrative arithmetic only**, not a standard workload metric).
- With `sort`, `limit`, and aggregations, merging must process many partial results.

### 9.2. Having an email index still broadcasts without the shard key

Suppose `orders` has shard key `{tenantId:1,orderId:1}` plus a local index:

~~~javascript
lab.orders_tenant.createIndex(
  { customerEmail: 1 },
  { name: "ix_customer_email" }
)
~~~

Request:

~~~javascript
lab.orders_tenant.find({
  customerEmail: "an@example.test"
})
~~~

Without `tenantId`/`orderId`, the router typically cannot tell which shard holds that email, even though every shard indexes `customerEmail`:

~~~text
mongos: queries multiple shards
  Shard A: IXSCAN(customerEmail)
  Shard B: IXSCAN(customerEmail)
  Shard C: IXSCAN(customerEmail)
~~~

**Fast local index scans on each shard do not eliminate fan-out overhead.** Fixes include passing `tenantId` in the API, choosing a different shard key, or building an `email → tenant/orderKey` lookup collection with appropriate consistency guarantees.

### 9.3. Full key vs. prefix key

With compound shard key:

~~~javascript
{ tenantId: 1, orderId: 1 }
~~~

| Query | Typical routing |
|---|---|
| `{tenantId:"T-A",orderId:"O-1005"}` | Full equality; typically one shard owning that key. |
| `{tenantId:"T-A"}` | Prefix present; typically shards holding `T-A` ranges (one or multiple). |
| `{orderId:"O-1005"}` | Missing leading prefix; risks broadcast. |
| `{status:"PAID"}` | No shard key; typically broadcast. |
| `{tenantId:"T-A",createdAt:{$gte:start,$lt:end}}` | Targets by tenant prefix, yet may hit multiple shards if `T-A` spans ranges. |
| `{tenantId:{$in:["T-A","T-B"]}}` | Can target union of both tenants’ ranges; shard count depends on placement. |
| `{tenantId:{$regex:/^T-/}}` | Router targeting may face limits depending on predicate/collation; check `explain`. |

This is a **reasoning model**, not a guarantee for every dataset. Even with the shard key, broad predicates and wide chunk distribution can touch many or all shards. The MongoDB Manual bases targeting on the **full key or compound key prefix**, not arbitrary indexed fields. See [Routing with mongos](https://www.mongodb.com/docs/manual/core/sharded-cluster-query-router/).

### 9.4. Why aren’t `_id` queries always targeted?

MongoDB automatically creates the `_id` index, yet if the collection is sharded on `{tenantId:1,orderId:1}`, querying only:

~~~javascript
lab.orders_tenant.findOne({ _id: "O-1005" })
~~~

does not let the router deduce `tenantId` or the owning chunk. It may probe multiple shards, even though `_id` index makes each shard’s local check fast.

**`_id` does not automatically act as the shard key** if you chose another shard key. This also ties into `_id` uniqueness and unique indexes on sharded collections; never assume every sharded collection guarantees global `_id` uniqueness when `_id` is not the shard key.

### 9.5. Cases where broadcasting is legitimate

Not all scatter-gather is wrong. Analytics computing **cluster-wide** revenue:

~~~javascript
lab.orders_tenant.aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: "$tenantId",
      paidOrders: { $sum: 1 },
      revenue: { $sum: "$totalMinor" }
    }
  }
])
~~~

When stats across **every tenant** are required, parallel execution across shards followed by merging is proper and even beneficial. Distinguish:

- **OLTP point lookups:** user wants one order; fan-out is usually wasteful.
- **Cluster-wide analytics:** result needs all data; multi-shard participation is natural.

The goal is not dogmatically “every query hits one shard,” but **selective OLTP queries should be targeted where the model allows**, while analytics are optimized for total cost and parallel execution.

### 9.6. Queries without the shard key affect paging/sorting

~~~javascript
lab.orders_tenant.find(
  { status: "PAID" }
).sort({ createdAt: -1 }).limit(20)
~~~

To find the global top 20, each shard must produce partial results for the router/merge stage to coordinate. Without a suitable local index on each shard, each shard also pays sort costs. A local `{status:1,createdAt:-1}` index helps **inside each shard**, yet the query still fans out without `tenantId`/`orderId`.

For deep pagination with `skip`, the router must collect far more records than the final page size. For tenant-scoped APIs, consider keyset pagination by shard key/`createdAt` plus a stable tie-breaker like `orderId`, backed by matching indexes and tenant filters.

### 9.7. Querying by tenant is both performance and authorization

When APIs return orders per tenant, `tenantId` should come from a **trusted authorization context**, not an unverified query parameter. Including `tenantId` in filters improves targeting and isolates data, yet **indexes/shard keys never replace authentication/authorization**. Enforce consistent scoping across queries, aggregations, `$lookup`s, updates, and export jobs.

## 10. Verifying targeted vs. broadcast with `explain`

Do not guess from SQL-like syntax or index existence. **`explain()` on a sharded cluster** reveals which shards were actually queried and each shard’s query plan within version capabilities.

### 10.1. Comparing two queries with the same business goal

With hypothetical shard key `{tenantId:1,orderId:1}`:

~~~javascript
const lab = db.getSiblingDB("shard262_lab")

// A. API already knows tenant and order ID:
lab.orders_tenant.explain("executionStats").find({
  tenantId: "T-A",
  orderId: "O-1005"
})

// B. API only knows order ID:
lab.orders_tenant.explain("executionStats").find({
  orderId: "O-1005"
})
~~~

When data/metadata allow, **A can target a single shard**, whereas **B may broadcast**. Both queries may return **the exact same order** if `orderId` is unique, yet routing costs differ sharply.

Prerequisites for valid comparison:

- The collection is **actually sharded** on the stated key.
- Connected through **`mongos`**, not directly to a shard `mongod`.
- Data spans multiple shards; tiny fixtures often sit on one shard and hide fan-out.
- Use consistent workload snapshots/connection settings and inspect actual plans.

### 10.2. Reading `explain` for sharded queries

Depending on MongoDB Server/engine, you may observe:

| Component / concept | How to read it |
|---|---|
| `SINGLE_SHARD` | Router selected a single shard in an eligible plan. |
| `SHARD_MERGE` | Plan includes a stage merging results across shards. |
| `SHARDING_FILTER` / `SHARD_FILTER` | Enforces ownership/metadata filtering during execution where applicable. |
| `shards` | List of participating shards and per-shard plans/statistics. |
| `IXSCAN` | Index scan **inside a shard**; does not imply only one shard participated. |
| `COLLSCAN` | Collection scan on a shard; may indicate missing index or planner choice. |
| `FETCH` | Fetches full document after index lookup when needed for fields/filters. |
| `totalKeysExamined` | Index keys examined; verify scope of the reported statistic. |
| `totalDocsExamined` | Documents examined; may sum shard-level stats. |
| `nReturned` | Documents returned at the reported execution level. |
| `splitPipeline` / `mergeType` | Splits aggregation between shard-side and merge-side when present. |

Never write an `explain` parser assuming every version emits a fixed JSON path like `queryPlanner.winningPlan.shards`. Classic engine, SBE, and aggregations differ in shape; focus on **participating shards + keys/docs examined + sort/merge**.

### 10.3. Visualizing “every shard has an index yet still fans out”

~~~text
Query A: full shard key
  mongos -> Shard B: IXSCAN + FETCH
  total shards targeted = 1

Query B: orderId only
  mongos -> Shard A: IXSCAN + FETCH
          -> Shard B: IXSCAN + FETCH
          -> Shard C: IXSCAN + FETCH
  total shards targeted = 3
~~~

This is an **explanatory simulation**, not real explain output. If each shard inspects just one key, Query B may still feel fast on small datasets; as request rates and shard counts scale, fan-out becomes costly. Measure p95/p99 latency and per-shard QPS rather than claiming “broadcast is always exactly N times slower.”

### 10.4. Does `hint` turn a broadcast into a targeted query?

No. `hint()` controls which index **executes the query locally** per API/version:

~~~javascript
lab.orders_tenant.find(
  { orderId: "O-1005" }
).hint({ orderId: 1 })
~~~

If that index exists/applies, each shard can use it, yet the router still lacks `tenantId` to deduce target shards from the compound shard key. **Index tuning fixes local scans; shard key predicates fix routing.**

### 10.5. Comparing `find()` and `aggregate()`

~~~javascript
lab.orders_tenant.explain("executionStats").aggregate([
  { $match: { tenantId: "T-A", orderId: "O-1005" } },
  { $project: { _id: 1, status: 1, totalMinor: 1 } }
])

lab.orders_tenant.explain("executionStats").aggregate([
  { $match: { orderId: "O-1005" } },
  { $project: { _id: 1, status: 1, totalMinor: 1 } }
])
~~~

An early `$match` on the shard key gives the router a chance to target shards. However, if `$match` follows stages that alter fields or dependencies, the optimizer may not push it down to cursor targeting. **Inspect the optimized aggregation plan**, not just source stage order.

### 10.6. How to count participating shards

Some versions show `SINGLE_SHARD` or `SHARD_MERGE` in `winningPlan`; others show a `shards` object/array with execution stats. The safest method is to **inspect every shard entry in `explain`** and verify whether it actually executed work rather than appearing only as metadata. When automating checks, build parsers for your exact deployed version and retest after upgrades.

## 11. Measuring data distribution and chunks/ranges

To separate **data skew** from **load skew**, gather at least two metric sets: *owned data distribution* and *read/write activity*.

### 11.1. `sh.status()`: overview of topology, chunk counts, zones

~~~javascript
// Run on mongos:
sh.status()

// More detailed; can be very long on large clusters:
sh.status(true)
~~~

Per the MongoDB Manual, `sh.status(true)` shows full chunk distribution and sharding configuration. Default `sh.status()` may summarize collections with many chunks. If chunks are flagged jumbo or migrations fail, this helps guide further diagnosis.

**Never use chunk count as the sole metric of data size.** Combine owned data bytes and per-shard skew.

### 11.2. `getShardDistribution()`: single-collection distribution

~~~javascript
const lab = db.getSiblingDB("shard262_lab")
lab.orders_tenant.getShardDistribution()
~~~

This `mongosh` helper prints distribution statistics for **one sharded collection**. It is not a Java Driver API and does not measure query QPS. If the collection is unsharded or you are connected to the wrong endpoint, output will not reflect sharded distribution.

### 11.3. `sh.getShardedDataDistribution()`: cluster-wide stats

Starting in MongoDB **6.0.3**, `mongosh` provides:

~~~javascript
sh.getShardedDataDistribution()
~~~

Illustrative output may contain:

~~~javascript
[
  {
    ns: "shard262_lab.orders_tenant",
    shards: [
      {
        shardName: "shardA",
        numOwnedDocuments: 1200000,
        ownedSizeBytes: 310000000000,
        numOrphanedDocs: 0,
        orphanedSizeBytes: 0
      },
      {
        shardName: "shardB",
        numOwnedDocuments: 1100000,
        ownedSizeBytes: 295000000000,
        numOrphanedDocs: 0,
        orphanedSizeBytes: 0
      }
    ]
  }
]
~~~

This is **hypothetical data**, not fixture output. `numOwnedDocuments`/`ownedSizeBytes` reflect data the shard **owns**; `numOrphanedDocs`/`orphanedSizeBytes` reflect orphaned records when present. Compare **owned data** rather than mistakenly adding orphaned documents into the collection’s logical size. See [sh.getShardedDataDistribution](https://www.mongodb.com/docs/manual/reference/method/sh.getshardeddatadistribution/).

### 11.4. Balancer/migration status and logs

~~~javascript
sh.getBalancerState()
db.adminCommand({ balancerStatus: 1 })
~~~

Combine with **config server/balancer logs**, shard logs, disk/capacity, and chunk/range info to spot:

- Range migrations retrying/aborting.
- Jumbo/indivisible chunks.
- Disk/network/replication lag on donor/recipient.
- Zone constraints leaving the balancer without eligible target shards.
- Competing resharding/DDL or admin operations.

An **enabled** balancer does not guarantee migrations succeed. Persistent skew may stem from placement limits or unsplittable/unmovable ranges rather than “the balancer isn’t running.”

### 11.5. Measure runtime load per shard

Collect from Atlas Metrics, MongoDB monitoring, or existing observability:

| Metric | Signal |
|---|---|
| CPU % / core utilization | One shard saturated, others idle. |
| Disk reads/writes and IOPS | Hot shard pushing past disk capacity. |
| Memory / cache eviction | Hot working set exceeding RAM/cache. |
| Replication lag | Secondaries on hot shard falling behind. |
| Read/write operations/sec | Sharp load gap despite equal owned bytes. |
| P95/P99 latency | Tail latency rises when one shard slows down. |
| Network bytes / connection usage | Scatter-gather fan-out/merge overhead. |
| Query shape frequency | Which predicates lack the shard key. |
| Chunk migration rate/failures | Whether balancer progresses or stalls. |
| Owned bytes/documents | Data skew and growth over time. |

Never compare **QPS** alone across shards: two shards at equal QPS have very different loads if one runs heavy scans/sorts and the other serves point lookups. Track **cost per operation** and keys/docs examined when available.

### 11.6. Inspect across time windows

For example, a normal day shows:

~~~text
Shard A: 30% writes, 34% reads, 31% owned bytes
Shard B: 35% writes, 33% reads, 34% owned bytes
Shard C: 35% writes, 33% reads, 35% owned bytes
~~~

Yet during a 15-minute flash sale:

~~~text
Shard A: 92% writes, 75% reads, 31% owned bytes
Shard B:  4% writes, 12% reads, 34% owned bytes
Shard C:  4% writes, 13% reads, 35% owned bytes
~~~

Data storage is balanced, yet the heavily accessed tenant/key sits on Shard A. The issue is **temporal workload skew**, not data storage balance.

## 12. `analyzeShardKey`: measuring a candidate key before resharding

Guessing a shard key often fails when production tenant distributions and query shapes diverge from test data. Starting in **MongoDB 7.0**, **`analyzeShardKey`** evaluates existing or candidate keys via metrics on **key characteristics** and **read/write distribution** from data and query samples when prerequisites are met.

### 12.1. Two metric groups

| Group | Contents |
|---|---|
| **`keyCharacteristics`** | Cardinality, frequency, monotonicity, and key-value traits. |
| **`readWriteDistribution`** | Routing/distribution characteristics of sampled read/write queries under the candidate key. |

A high-cardinality key is still poor if the application **never puts that field in filters**. Similarly, great read targeting still fails if 99% of new writes hammer one monotonic range.

### 12.2. Calling `analyzeShardKey` in mongosh

Per current docs, the method looks like:

~~~javascript
// Run only when cluster/version/permissions meet requirements.
const lab = db.getSiblingDB("shard262_lab")

lab.orders_tenant.analyzeShardKey({
  tenantId: 1,
  orderId: 1
})

// Analyze another candidate to compare.
lab.orders_tenant.analyzeShardKey({
  orderId: "hashed"
})
~~~

This analysis command **does not reshard the collection**. It reports metrics for evaluation. For reliable **readWriteDistribution**, representative query sampling must be configured per docs. A six-document lab collection has virtually zero statistical value; never choose a production shard key from a handful of samples.

### 12.3. Query analyzer sampling

MongoDB provides a **query analyzer** and commands like `configureQueryAnalyzer` to sample queries per version and privilege rules. Set a sampling rate suited to live QPS to limit overhead, monitor the sampling window, and categorize:

- Point lookups by `tenant + order`.
- Point lookups by `orderId` alone.
- Range scans by `createdAt`.
- `updateOne`/`upsert`/`deleteMany` omitting the shard key.
- Hourly scheduled jobs or flash-sale traffic.

If the sample window captures only off-peak OLTP and misses batch imports or end-of-day analytics, `readWriteDistribution` will be skewed. **Sampling metrics are only as good as how well they represent the workload you are optimizing.**

### 12.4. Comparing two candidates

Suppose:

| Dimension | `{tenantId:1,orderId:1}` | `{orderId:"hashed"}` |
|---|---|---|
| `tenant+order` lookups | Good | `orderId` equality is usually good. |
| `orderId`-only queries | Risk of broadcast | Usually targeted. |
| Tenant-wide lists/reports | Can target tenant ranges | Risk of broadcast. |
| Sequential IDs in hot tenant | Can form hot range | Hashing usually spreads better. |
| Unique indexes for `tenant+externalOrderNo` | Check shard key prefix/constraints | Re-evaluate uniqueness rules; hash is non-unique. |
| API change effort | May require passing tenant | Can keep order-only APIs. |

This is a **theoretical trade-off table**, not measurements from a specific workload. Also factor in data residency, index footprint, shard ownership, and rollout feasibility.

### 12.5. Analyzer output is not a performance guarantee

`analyzeShardKey` and `explain` inform decisions; they do not replace **real load testing**, p95/p99 measurement, failure-mode testing, and post-rollout monitoring. A key that works well under today’s distribution can degrade if a major customer grows 50× or product ships a new query omitting `tenantId`.

## 13. Missing the shard key in **write operations**

Unlike `find()`, writes on a sharded collection carry **specific routing rules and syntax constraints** that vary across server versions and write/upsert types.

### 13.1. `insertOne` with full shard key in the document

~~~javascript
const lab = db.getSiblingDB("shard262_lab")

lab.orders_tenant.insertOne({
  _id: "O-2001",
  tenantId: "T-A",
  orderId: "O-2001",
  status: "CREATED",
  createdAt: new Date(),
  totalMinor: NumberLong(70000)
})
~~~

`mongos` inspects the shard key values in the document to pick the target shard. If your data model requires non-null `tenantId`/`orderId`, enforce data hygiene in the application and schema validation. Never assume missing/null shard key fields are safe simply because a command accepts some cases.

### 13.2. `updateOne` with full shard key

~~~javascript
lab.orders_tenant.updateOne(
  {
    tenantId: "T-A",
    orderId: "O-2001",
    status: "CREATED"
  },
  {
    $set: {
      status: "PAID",
      paidAt: new Date()
    }
  }
)
~~~

The router targets the owning shard; the `status: "CREATED"` predicate also guards the state transition against two concurrent requests. **Full shard key equality** generally delivers the clearest performance and semantics for point writes.

### 13.3. `updateOne` by `_id` alone may take a costlier write path

~~~javascript
lab.orders_tenant.updateOne(
  { _id: "O-2001" },
  { $set: { status: "CANCELLED" } }
)
~~~

When `_id` is not the shard key and the filter lacks the full shard key, MongoDB uses a **two-phase write protocol** or version-specific operation/upsert limits; the request may have to locate the document across shards before executing the write. Never assume the `_id` index tells the router which shard holds the document.

This example **illustrates routing risk**, not a recommended call right after marking an order `PAID` in real business logic. For status transitions, always keep state guards and authorization like the `updateOne` example above.

### 13.4. `updateMany` and `deleteMany`

~~~javascript
// Modify only the authorized tenant:
lab.orders_tenant.updateMany(
  {
    tenantId: "T-A",
    status: "CREATED"
  },
  {
    $set: { needsReview: true }
  }
)
~~~

With compound shard key `{tenantId:1,orderId:1}`, the `tenantId` prefix targets **the set of shards** holding that tenant’s ranges; do not assume only one shard.

If the filter only says `status: "CREATED"`, the router may broadcast. `updateMany` and `deleteMany` follow routing rules based on whether the filter contains the **full shard key**; omitting it sends work to multiple shards. Moreover, `updateMany` is **atomic per document**, not atomic across all matched documents without a transaction.

### 13.5. Upserts have version-specific requirements

~~~javascript
lab.orders_tenant.updateOne(
  { tenantId: "T-A", orderId: "O-3001" },
  {
    $setOnInsert: {
      createdAt: new Date(),
      status: "CREATED"
    }
  },
  { upsert: true }
)
~~~

**Having the full shard key in the filter** makes routing unambiguous and easier to operate. Still, rules like “upsert must include the full shard key” have evolved across MongoDB versions (for example, changes in 7.x/8.x). Never assert an absolute rule for all deployments: check the `updateOne()` docs for your exact server and driver versions, especially when changing shard key field values, using null/missing keys, or updating without `_id`.

### 13.6. Unique indexes on sharded collections

If cluster-wide uniqueness of `(tenantId, externalOrderNo)` is needed, align the shard key and unique index with **unique index restrictions**. With ranged shard keys, a unique index on a sharded collection generally must have **the shard key as a prefix** to guarantee cluster-wide uniqueness, aside from documented exceptions/limits.

~~~javascript
// Example key design intentionally chosen for uniqueness:
// Shard key: { tenantId: 1, externalOrderNo: 1 }
// Prefix-compatible unique constraint candidate:
db.orders.createIndex(
  { tenantId: 1, externalOrderNo: 1 },
  { unique: true }
)
~~~

With a **hashed shard key**, a hashed index cannot serve as a simple unique index in the same way. And if `_id` is not the shard key, MongoDB restricts **global `_id` uniqueness**: the `_id` index may enforce uniqueness **per shard only**, requiring application mechanisms to ensure global ID uniqueness when needed. Never rely on “`_id` is always globally unique regardless of shard key” when designing payments/identity.

### 13.7. Mutating a document’s shard key field

MongoDB supports updating shard key values in qualifying scenarios/versions, yet an update moving a document to a range owned by another shard incurs movement overhead and query/session/transaction constraints. Avoid picking mutable fields like `status`, `currentAssignee`, or changeable `region` as the shard key if updates continually shift documents across shards.

This is not merely an atomicity issue, but also **performance and operational complexity**.

## 14. Aggregation in a sharded cluster: filter early and merge

An aggregation can split into a **shard-side partial pipeline** and a **merge-side pipeline**. `mongos` or a shard merges results depending on stages and server version. When predicates cover the shard key and can be pushed down early, fewer shards participate.

### 14.1. Single-tenant report

~~~javascript
const start = ISODate("2026-06-01T00:00:00Z")
const end = ISODate("2026-07-01T00:00:00Z")

lab.orders_tenant.aggregate([
  {
    $match: {
      tenantId: "T-A",
      status: "PAID",
      createdAt: { $gte: start, $lt: end }
    }
  },
  {
    $group: {
      _id: "$customerId",
      totalMinor: { $sum: "$totalMinor" },
      orders: { $sum: 1 }
    }
  },
  { $sort: { totalMinor: -1 } }
])
~~~

`tenantId: "T-A"` is the shard key prefix, letting the router identify relevant ranges. Yet because `T-A` may live across **multiple shards**, the aggregation can still split partial work and merge. Actual placement dictates shard count, not the `tenantId` name alone.

### 14.2. All-tenants report

~~~javascript
lab.orders_tenant.aggregate([
  {
    $match: {
      status: "PAID",
      createdAt: { $gte: start, $lt: end }
    }
  },
  {
    $group: {
      _id: "$tenantId",
      totalMinor: { $sum: "$totalMinor" },
      orders: { $sum: 1 }
    }
  },
  { $sort: { totalMinor: -1 } }
])
~~~

Because the summary spans all tenants, involving every shard can be **correct**. Optimize using local indexes, shard-side filters/grouping, sort/merge resources, and result limits—do not try to force one shard to do all the work.

### 14.3. Filters after `$project` may be pushed down, but do not rely on it blindly

~~~javascript
lab.orders_tenant.aggregate([
  { $project: { tenantId: 1, status: 1, totalMinor: 1 } },
  { $match: { tenantId: "T-A", status: "PAID" } }
])
~~~

The optimizer can push some independent predicates earlier. However, if `$match` depends on a field computed by `$project`, or a prior stage changes semantics, reordering may be invalid. Write **shard key filters early when semantically valid** and confirm targeting with `explain`, rather than hoping every pipeline auto-optimizes.

### 14.4. `$lookup` and sharding do not solve routing automatically

Joining another collection in aggregation can generate many subqueries or stage splits under sharding. Indexes and the shard key of the **foreign collection** affect how `$lookup` executes depending on server version. If each order looks up a customer by `customerId` without the customer’s shard key, fan-out/merge overhead can appear. Check `explain` for the entire pipeline, especially when `$lookup`, `$group`, or `$sort` dominates execution time.

### 14.5. Streaming analytics vs. OLTP

OLTP workloads need single orders returned in milliseconds, making targeted lookups vital. Analytics scanning tens of millions of documents to aggregate can benefit from parallel execution across all shards. When these needs clash, consider **read models/denormalization** or a dedicated analytical store rather than picking an extreme shard key just to optimize one query.

## 15. When changing the shard key is needed: refine or reshard?

If measurements prove the current shard key is **fundamentally unsuitable**, there are two change paths:

1. **Refine shard key:** append suffix fields to the existing shard key (keeping the old prefix).
2. **Reshard collection:** redistribute data under a different shard key; can change fields or switch ranged ↔ hashed per server support.

These are **high-risk DDL/cluster-level operations**, not routine query tuning. You need capacity headroom, a migration plan, unique-constraint checks, query contract review, zone policies, and rollback/recovery procedures.

### 15.1. Refine shard key: appending a suffix component

Suppose the old key is:

~~~javascript
{ tenantId: 1 }
~~~

A huge tenant has many orders, and `tenantId` alone lacks distinct values to split ranges. To preserve `tenantId` as the prefix, evaluate:

~~~javascript
{ tenantId: 1, orderId: 1 }
~~~

Sample admin command on a supported lab cluster:

~~~javascript
// DO NOT run directly on production.
db.adminCommand({
  refineCollectionShardKey: "shard262_lab.orders_tenant_only",
  key: { tenantId: 1, orderId: 1 }
})
~~~

Refinement has index/key-field prerequisites and version limits. It **does not** allow removing `tenantId` or moving `orderId` ahead of it; it only appends a suffix. If common queries omit `tenantId`, refining **will not fix** `orderId`-only fan-out. If `orderId` ascends monotonically, the compound ranged key can still run hot inside a tenant.

### 15.2. Reshard: changing key structure

MongoDB supports `reshardCollection` starting in **5.0** under deployment prerequisites. Example transition from:

~~~javascript
// Current:
{ tenantId: 1, orderId: 1 }

// New candidate:
{ orderId: "hashed" }
~~~

Command shape:

~~~javascript
// DDL illustration only in a prepared lab cluster.
db.adminCommand({
  reshardCollection: "shard262_lab.orders_tenant",
  key: { orderId: "hashed" }
})
~~~

Resharding can transform write spread and query targeting. Yet it also alters the **query contract**: tenant-only APIs now risk broadcasting, and existing unique indexes may no longer satisfy the new key. Before running, audit queries, writes, indexes, uniqueness, zones, and storage capacity.

### 15.3. Resharding with the same shard key

Starting in MongoDB **8.0**, you can reshard with the **same existing shard key** via redistribution when appropriate, e.g., `forceRedistribution: true`:

~~~javascript
// Illustration only; do not run on production.
db.adminCommand({
  reshardCollection: "shard262_lab.orders_tenant",
  key: { tenantId: 1, orderId: 1 },
  forceRedistribution: true
})
~~~

Redistributing with the same key can relieve certain placement imbalances, yet **cannot fix intrinsic flaws of the key**, such as a monotonic write edge or an overwhelmingly repeated `tenantId` value.

### 15.4. Costs to plan for

- Copying/cloning data and indexes generates **I/O, network, CPU, and storage pressure**.
- Can require **substantial extra disk space** on recipient shards.
- Can involve a brief **write-blocking/cutover latency window** per server version limits.
- Assess impacts on **oplog, replication, change streams**, and active operations.
- Certain DDLs are disallowed or blocked while resharding runs.
- Unique index/shard key compatibility is a strict prerequisite.
- Actual duration depends on data size, cluster throughput, and concurrent load.

Test on staging with representative data/workload, monitor closely, verify post-cutover queries, and prepare recovery. See [Reshard a Collection](https://www.mongodb.com/docs/manual/core/sharding-reshard-a-collection/).

### 15.5. When NOT to jump straight to resharding

If the issue is an API forgetting to pass a known `tenantId`, a missing local index, unthrottled batch imports, one standalone hot counter document, or temporary balancer migrations, **fixing the specific query/index/throttling/model** is far safer than resharding the whole collection. Changing the shard key is a major decision made after proving the key itself bottlenecks the system.

## 16. Java Sync Driver: passing the right shard key in OLTP queries

The Java Driver does not ask the application to choose shards manually. What you control is the **BSON filter** sent through `mongos`. If the filter omits the shard key, the router can still broadcast even when code uses `Filters.eq` and a local index exists.

### 16.1. Targeted lookup by tenant + orderId

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.conversions.Bson;

// database: MongoDatabase connected to cluster via mongos.
MongoCollection<Document> orders =
    database.getCollection("orders_tenant");

String authorizedTenantId = "T-A"; // From verified auth context.
String orderId = "O-1005";

Bson filter = Filters.and(
    Filters.eq("tenantId", authorizedTenantId),
    Filters.eq("orderId", orderId)
);

Document order = orders.find(filter).first();
System.out.println(order == null ? "Not found" : order.toJson());
~~~

If the key is `{tenantId:1,orderId:1}`, the filter supplies both fields. Do not use `Filters.eq("orderId", orderId)` alone on critical OLTP paths just because the driver returns correct results on a tiny cluster.

### 16.2. Conditional update with full shard key

~~~java
import com.mongodb.client.result.UpdateResult;
import com.mongodb.client.model.Updates;

UpdateResult result = orders.updateOne(
    Filters.and(
        Filters.eq("tenantId", authorizedTenantId),
        Filters.eq("orderId", orderId),
        Filters.eq("status", "CREATED")
    ),
    Updates.combine(
        Updates.set("status", "PAID"),
        Updates.set("paidAt", new java.util.Date())
    )
);

if (result.getMatchedCount() == 0) {
    // Missing order, state already changed, or invalid tenant scope.
    System.out.println("Update precondition not met");
}
~~~

The shard key filter assists routing; the `status` filter guards the **business transition**. Never treat `matchedCount: 0` as a network error; it usually just means no document matched.

### 16.3. Index serving tenant + sort

~~~java
import com.mongodb.client.model.Indexes;
import com.mongodb.client.model.IndexOptions;

orders.createIndex(
    Indexes.compoundIndex(
        Indexes.ascending("tenantId"),
        Indexes.descending("createdAt")
    ),
    new IndexOptions().name("ix_tenant_createdAt_desc")
);
~~~

This index helps **inside each shard** for tenant/date queries and sorting, without changing the shard key. For tenants spanning multiple shards, queries still require a merge step. Production index creation must consider write overhead, disk usage, and existing indexes.

### 16.4. `explain` in Java

~~~java
import com.mongodb.ExplainVerbosity;

Document plan = orders.find(
    Filters.and(
        Filters.eq("tenantId", authorizedTenantId),
        Filters.eq("orderId", orderId)
    )
).explain(ExplainVerbosity.EXECUTION_STATS);

System.out.println(plan.toJson());
~~~

`FindIterable.explain()` reveals the query plan. To count targeted shards, understand the output structure for your server/version rather than spotting `IXSCAN` and assuming single-shard execution.

### 16.5. Tenant-scoped aggregation in Java

~~~java
import java.util.Arrays;
import java.util.Date;
import java.time.Instant;
import org.bson.conversions.Bson;
import com.mongodb.client.model.Aggregates;
import com.mongodb.client.model.Accumulators;
import com.mongodb.client.model.Sorts;

Date start = Date.from(Instant.parse("2026-06-01T00:00:00Z"));
Date end = Date.from(Instant.parse("2026-07-01T00:00:00Z"));

Bson match = Aggregates.match(Filters.and(
    Filters.eq("tenantId", authorizedTenantId),
    Filters.eq("status", "PAID"),
    Filters.gte("createdAt", start),
    Filters.lt("createdAt", end)
));

orders.aggregate(Arrays.asList(
    match,
    Aggregates.group(
        "$customerId",
        Accumulators.sum("paidOrders", 1),
        Accumulators.sum("revenueMinor", "$totalMinor")
    ),
    Aggregates.sort(Sorts.descending("revenueMinor"))
)).forEach(System.out::println);
~~~

This query places the `tenantId` filter before grouping. If the `tenantId` prefix covers multiple ranges across shards, the aggregation may still execute across shards and merge.

### 16.6. Common API bug: service only accepts `orderId`

~~~java
// Context-poor API:
public Document getOrder(String orderId) {
    return orders.find(Filters.eq("orderId", orderId)).first();
}
~~~

On a collection sharded with a `tenantId`-leading key, this service broadcasts. A better contract passes `authorizedTenantId`:

~~~java
public Document getOrder(String authorizedTenantId, String orderId) {
    return orders.find(Filters.and(
        Filters.eq("tenantId", authorizedTenantId),
        Filters.eq("orderId", orderId)
    )).first();
}
~~~

If the caller genuinely lacks the tenant, use a lookup mapping, a different key, or a safe two-step lookup flow. Never guess a `tenantId` or accept an unverified client value just to make queries fast.

### 16.7. The driver does not infer the shard key automatically

The Java Driver serializes filters, manages topology/`mongos` discovery, and handles retryable writes where eligible, yet it cannot infer `tenantId` from `orderId` without a mapping. Changing the connection string will not turn a keyless query into a targeted one; fix the **query shape or data model**.

## 17. Runbook for investigating hot shards or skewed data

When production alerts “MongoDB sharded cluster is slow despite adding shards,” do not jump straight to resharding. Follow **measure → classify → verify → fix safely**.

### Step 1 — Identify symptoms and timing

~~~text
Hot writes?         Hot reads?
Data size skew?     Chunk/zone imbalance?
Query latency?      Migration failures?
~~~

Pinpoint **metrics and timestamps**: is one shard at 95% CPU? Did p99 spike during a flash sale? Are owned bytes 70/15/15? Are point lookups broadcasting? Did app writes spike suddenly or has data drifted for weeks?

### Step 2 — Confirm the real shard key

~~~javascript
// Through mongos with appropriate metadata privileges.
sh.status()
~~~

Record the **exact shard key pattern**, including field order and hashed/ranged mode. Never read an index name from an old design doc and assume it is the deployed shard key.

### Step 3 — Gather data distribution

~~~javascript
const lab = db.getSiblingDB("shard262_lab")

lab.orders_tenant.getShardDistribution()
sh.getShardedDataDistribution()
~~~

Inspect owned bytes/docs per shard and range ownership, not just chunk counts. If the balancer looks stuck, check `balancerStatus` and logs.

### Step 4 — Gather query shapes and `explain`

Pick high-**QPS** and slow-**p95/p99** queries across reads and writes:

~~~javascript
// With full key:
lab.orders_tenant.explain("executionStats").find({
  tenantId: "T-A",
  orderId: "O-1005"
})

// Missing leading shard key prefix:
lab.orders_tenant.explain("executionStats").find({
  orderId: "O-1005"
})
~~~

Count participating shards and inspect `IXSCAN`/`COLLSCAN` **on each shard**. Check whether well-indexed queries are still fanning out.

### Step 5 — Classify the root cause

| Observation | Investigate first |
|---|---|
| New writes hit the trailing range | Monotonic key, hot chunk, insert pattern. |
| One tenant drives most traffic | Hot tenant, frequency skew, `tenantId`-only key. |
| Bytes skewed while QPS is even | Range placement, balancer, zones, indivisible chunks. |
| Bytes even while QPS is skewed | Hot keys, working set, query patterns. |
| Point lookups hit every shard | Missing shard key/prefix, API contract. |
| Shards scan many docs despite targeting | Local indexes/filter selectivity, sort. |
| Migrations fail repeatedly | Balancer logs, jumbo/indivisible chunks, capacity/zones. |

### Step 6 — Choose the smallest effective fix

Actions ordered by increasing risk:

1. **Fix API/queries** to pass the full shard key or matching prefix.
2. **Create/tune local indexes** for filters/sorts once queries are targeted.
3. **Relieve application hotspots**, e.g., throttle imports, bucket counters, batch writes reasonably.
4. **Adjust the data model**, or add lookup mappings/read models.
5. **Evaluate refining/resharding the shard key** using `analyzeShardKey`, staging tests, and a migration plan.
6. **Adjust zones/balancer/capacity** per root cause; never perform manual interventions without understanding placement.

### Step 7 — Verify after rollout

- Do owned bytes/docs and range distribution meet expectations?
- Did per-shard QPS/CPU/IOPS improve?
- Did the targeted/broadcast ratio for OLTP queries improve?
- Did p95/p99 latency drop under comparable workloads?
- Were there regressions in tenant-wide reports, range queries, or unique constraints?
- Are balancer and replication stable, with no new stuck migrations or jumbo chunks?
- Did error/retry rates on `updateOne`/upserts increase due to the new key?

### 17.1. Evidence-based diagnostic template

~~~text
Symptom:
  write latency p99 jumped from 20ms to 220ms during flash sale.

Measurements:
  Shard B at 95% CPU, A/C at 30%.
  Owned bytes A/B/C = 33/34/33%.
  85% of writes belong to tenant T-BIG.
  Shard key {tenantId:1}, one tenant repeats heavily.

Preliminary conclusion:
  Workload skew / hot tenant, not storage imbalance.

Actions:
  Evaluate compound key with orderId/hash or bucketing.
  Audit query contracts (tenant-only vs tenant+order).
  Benchmark workload/reshard on staging.
~~~

Numbers are **illustrative scenarios**; never treat them as fixed thresholds for every cluster.

### 17.2. Actions to avoid doing prematurely

- Disabling the balancer just because CPU is high without proving migrations are the cause.
- Manually moving ranges before measuring hotspots and splittability.
- Changing the shard key just because one query broadcasts when the API could simply pass `tenantId`.
- Adding shards and promising write throughput will scale linearly.
- Creating dozens of local indexes to “fix broadcast” without fixing routing.
- Pinning all tenants into one zone/shard without modeling peak QPS.
- Dropping tenant filters to “speed up” queries at the cost of breaking tenant isolation.
- Running `reshardCollection` directly in production without testing capacity, cutover, and rollback.

## 18. Architectural scenarios and design choices

### 18.1. Chronological post feed

An application stores new posts with continuously ascending `createdAt`, shard key `{createdAt:1}`; “newest posts” queries also hit the top of the dataset.

**Problem:** write hotspot on the tail range; read hotspot also focused on fresh data.

**Evaluation path:** Shard by `userId`/`authorId`/hash or a suitable compound key, noting a global “newest” feed may need to merge across shards or use a materialized feed/cache. Never simply swap `createdAt` for a hash without planning global chronological reads.

### 18.2. Tenant B generates 90% of orders

Key `{tenantId:"hashed"}` sounds “hashed so balanced,” yet every order of Tenant B shares the same hash.

**Problem:** hot tenant on one single key value; indivisible chunks may appear.

**Evaluation path:** compound hashed key `{tenantId:1,orderId:"hashed"}` or bucketing by `orderId`, honoring query targeting and data residency constraints. If Tenant B needs strict isolation, consider dedicated resources or a tenant-specific shard strategy.

### 18.3. Equal document counts yet one shard hits 100% CPU

One hot customer repeatedly reads/updates the exact same document while the balancer reports balanced storage.

**Problem:** **hot document / workload skew**, not data size skew.

**Evaluation path:** reduce contention via data-model changes, split/bucketed counters, caching, asynchronous aggregation, or rate limiting; the balancer cannot split writes to a single document across shards concurrently.

### 18.4. API fetches order by `orderId` after sharding on `tenantId`

~~~javascript
// Old query:
db.orders.findOne({ orderId: "O-1005" })

// Better query for key {tenantId:1,orderId:1}:
db.orders.findOne({
  tenantId: "T-A",
  orderId: "O-1005"
})
~~~

**Problem:** API contract omits the leading shard key prefix, causing broadcast.

**Evaluation path:** extract `tenantId` from verified auth context/URL and include it in the filter; if legitimate callers only know `orderId`, build a consistent lookup mapping or reconsider the shard key. Never fabricate `tenantId` just to target.

### 18.5. Email lookup despite having an email index

Orders are sharded by tenant; each shard indexes `customerEmail`, yet email-only lookups still broadcast.

**Problem:** local indexes do not alter shard metadata.

**Evaluation path:** tenant-aware queries, an `email → tenantIds/orderIds` read model, or a global search service; safeguard PII and per-tenant/global uniqueness policies. Never assume email is inherently stable/unique.

### 18.6. EU region zone with a full EU shard

Zone constraints pin EU data to a specific group of shards, one of which runs out of capacity.

**Problem:** zone placement/capacity skew; the balancer cannot move EU data to shards outside the zone.

**Evaluation path:** add eligible shards inside the zone, adjust zone ranges after reviewing data residency, capacity planning, and migration health. Never break zone policies just to equalize bytes.

### 18.7. Date-range queries slow down after switching to hashed `orderId`

Hashing improved inserts, yet `createdAt` is not the shard key, forcing June reports to scan many shards.

**Evaluation path:** if reports are tenant-scoped, include the tenant filter when supported by the key; add local `createdAt`/`status` indexes, materialized daily aggregates, or an analytical replica/warehouse. Only reshard again if range query workloads outweigh write spread and metrics confirm it.

### 18.8. Importing 20 million documents in a day with a sequential key

**Problem:** bulk insert wave piles onto one hot range, spiking lag, locks, and I/O.

**Evaluation path:** pre-partition / use a suitable hashed key / bucketed insert strategy, throttle ingestion, and tune indexes and chunk distribution; never expect unordered `bulkWrite` to spread writes across shards if **the shard key itself remains monotonic**.

### 18.9. Collection accumulates many orphaned documents

Migrations and chunk ownership transfers can temporarily leave orphaned records. Summing raw storage bytes including orphans skews perceived logical owned distribution.

**Evaluation path:** use `getShardedDataDistribution` to separate `ownedSizeBytes` from `orphanedSizeBytes`, and check range deletion/migration logs per version. Never manually delete orphans directly on a shard.

### 18.10. Query by `userId` fast on 3 shards, slow on 20 shards

If the key is `tenantId` and `userId` queries omit tenant, requests broadcast to every shard. Even with a `userId` index on each shard, total shard operations and merge overhead multiply.

**Evaluation path:** query with `tenantId`; if impossible, introduce global identifier/lookup routing, a read model, or reshard when the pattern is truly dominant. **Scaling data out** exposes weaknesses in **fan-out query patterns**.

## 19. Common misconceptions and corrections

| Misconception | Why it is wrong | Correct understanding |
|---|---|---|
| “With 8 shards, every insert splits 1/8.” | Routing uses shard key/chunk placement, not round-robin per insert. | Pick a shard key with suitable cardinality and distribution. |
| “Sequential shard keys have high cardinality so they’re always good.” | New inserts all hit the upper range. | Check monotonicity and write hotspots. |
| “Enabling the balancer spreads writes evenly.” | The balancer moves ranges for data balance, not splitting one hot range into parallel write targets. | Fix key/write patterns for monotonic/hot values. |
| “Hashing `tenantId` splits a huge tenant’s load.” | All documents of the same `tenantId` share one hash. | Add a discriminating component within the tenant when needed. |
| “Hashing `createdAt` preserves time-range targeting like a ranged key.” | Hashing destroys contiguity of original values. | Hashed aids write spread, while range queries may broadcast. |
| “Any query containing a compound key field is targeted.” | Router needs the full key or **leading prefix**. | Inspect key order and `explain`. |
| “`tenantId` prefix guarantees single-shard queries.” | Large tenants can span ranges across multiple shards. | Prefix only narrows to a **subset of shards**. |
| “An `orderId` index guarantees `orderId` lookups hit one shard.” | Indexes work **inside a shard**, giving the router no placement info under another key. | Supply the shard key or change routing strategy. |
| “`_id` is always equivalent to the shard key.” | The shard key is chosen via DDL; `_id` can be different. | Never infer targeting or global uniqueness from `_id` under another key. |
| “`IXSCAN` in `explain` means no broadcast.” | Every participating shard can run `IXSCAN`. | Check participating **shards** first, then local plans. |
| “`COLLSCAN` is always the root of latency.” | Tiny collections or full analytical scans can legitimately use `COLLSCAN`. | Inspect `docsExamined`/selectivity/QPS. |
| “Equal chunks means equal data.” | Ranges vary in document count and byte size. | Use `ownedSizeBytes`/`numOwnedDocuments`. |
| “Equal data means equal workload.” | Hot tenants/keys concentrate read/write QPS. | Compare per-shard load metrics over time. |
| “A jumbo chunk just needs a manual `moveChunk`.” | If indivisible, the range lacks valid split points. | Investigate key frequency/cardinality, constraints, and version. |
| “Stopping the balancer ends hotspots.” | It can worsen data skew without fixing hot keys. | Diagnose the hotspot root cause first. |
| “Adding shards always relieves hot documents.” | One document cannot split writes across shards. | Change data model / counter bucketing / aggregation. |
| “Pick the shard key solely by storage GB.” | Keyless APIs broadcast and write skew can spike. | Balance read/write patterns alongside placement. |
| “One day of query samples is enough to pick a key.” | Flash sales, imports, and analytics may be missed. | Use `analyzeShardKey` and multi-cycle representative samples. |
| “Hashed keys are always faster than ranged keys.” | Range/sort locality degrades and unique constraints complicate. | Choose based on OLTP vs. range scan share. |
| “Refine can change the leading field of the key.” | Refine only **appends a suffix**. | Changing the leading prefix requires resharding where supported. |
| “Resharding with the same key fixes monotonicity.” | The key stays monotonic; redistribution only moves existing ranges. | To change write spread, change the key/write pattern. |
| “Keyless upserts behave identically across all versions.” | Routing/required predicates have changed across versions. | Check `updateOne()` docs for your exact server version. |
| “`updateMany` is atomic cluster-wide.” | Atomic per document unless wrapped in a transaction. | Separate atomicity from routing. |
| “`bulkWrite({ordered:false})` auto-balances shard writes.” | Unordered only relaxes ordering; the shard key still dictates routing. | Need a distributing key and live distribution monitoring. |
| “A zone with one shard scales without limits.” | Zones constrain placement and capacity. | Provision enough shards per zone. |
| “Filtering by `tenantId` always secures tenant data.” | A forged client `tenantId` can still read another tenant. | Source tenant from trusted authorization context. |
| “Once resharded, every API stays optimal.” | Query contracts, unique indexes, and targeting change. | Run regression tests across query shapes before cutover. |

### 19.1. Distinguishing three answers for three symptoms

~~~text
Seeing a write hotspot:
  Ask which key, which value, and which chunk receives the writes?

Seeing data skew:
  Ask what owned bytes/docs/ranges look like, and what balancer/zone constraints apply?

Seeing slow queries:
  Ask how many shards mongos targeted,
  and which index or scan/sort each shard executed?
~~~

**Never use a single reflex—like “add more shards”—to answer all three questions.**

## 20. Hands-on exercises and suggested answers

Exercises assume a three-shard cluster or the scenario stated in the prompt. QPS/GB figures are **illustrative**, not measured output from `shard262_lab`. Commands may run on an **authorized lab cluster**; never run DDL/migrations on production.

### Exercise 1 — Why does a timestamp key create a hotspot?

**Prompt:** `orders` is sharded on `{createdAt:1}`. Every new order carries wall-clock time; 90% of inserts go to Shard C even though A/B/C hold similar data sizes. Explain.

**Answer:** Range sharding maintains a chunk bounded above by `MaxKey`. As `createdAt` rises continuously, fresh values fall into the **trailing range**, currently owned by Shard C. The balancer can migrate the hot range elsewhere over time, yet cannot spread concurrent new inserts across multiple targets simultaneously. Consider a hashed key or higher-spread key while accounting for time-range queries.

### Exercise 2 — Does hashing `tenantId` cure a hot tenant?

**Prompt:** 85% of orders have `tenantId: "T-MEGA"`. Shard key is `{tenantId:"hashed"}`. Why is one shard still hot?

**Answer:** Hashing a repeated value yields the **exact same hash**. All `T-MEGA` documents still share one key value, concentrating in one range/shard. You need a discriminating dimension **within the tenant**, such as hashed/bucketed `orderId`, plus a plan for tenant-wide queries.

### Exercise 3 — Full key vs. missing leading prefix

**Prompt:** Shard key `{tenantId:1,orderId:1}`. Two queries:

~~~javascript
db.orders.findOne({ tenantId: "T-A", orderId: "O-1" })
db.orders.findOne({ orderId: "O-1" })
~~~

Which query targets better?

**Answer:** The first query has the full key, letting the router identify the range/shard. The second lacks `tenantId` and risks broadcasting to many/all shards. A local `orderId` index does not fix routing.

### Exercise 4 — Query by `tenantId` alone

**Prompt:** Shard key `{tenantId:1,orderId:1}`. Why can `{tenantId:"T-A"}` target **multiple shards**?

**Answer:** Tenant `T-A` can span multiple `orderId` ranges located on different shards; the prefix lets the router skip shards without `T-A`, without guaranteeing only one shard. Check chunk placement/`explain`.

### Exercise 5 — `_id` and the shard key

**Prompt:** Shard key is `{tenantId:1,orderId:1}`. Collection has an `_id` index. Does `{_id:"O-1001"}` guarantee targeted routing?

**Answer:** No. The router cannot deduce the owning shard from `_id` if `_id` is not part of the shard key. It may query multiple shards, each using its local `_id` index. If global ID uniqueness is required, design within sharded unique index constraints.

### Exercise 6 — Local indexes and routing

**Prompt:** Every shard has `{customerEmail:1}`; searching `{customerEmail:"an@example.test"}` still hits 6 shards. Does that mean the index isn’t being used?

**Answer:** Not necessarily. `IXSCAN` can occur on all six shards. The index helps local filtering without telling the router which shard holds the email. Inspect per-shard `explain` and consider a tenant-aware API or lookup read model.

### Exercise 7 — Balanced data yet skewed CPU

**Prompt:** Owned bytes are A=100 GB, B=100 GB, C=100 GB; CPU is A=95%, B/C=15%. Should you run the balancer to “balance CPU”?

**Answer:** Not without evidence. Data is already even; the cause may be workload skew, hot tenant/key, differing queries, working-set differences, or a hot document. Gather QPS/IOPS/query shapes first. The balancer primarily manages data ranges, not CPU dispatch.

### Exercise 8 — Are 100 chunks always more data than 50 chunks?

**Answer:** No. Chunks differ in byte size and document density. Inspect `ownedSizeBytes`, `numOwnedDocuments`, orphaned data, chunks/ranges, and version-specific balancing.

### Exercise 9 — Low-cardinality key

**Prompt:** A 10-shard cluster uses shard key `{countryGroup:1}` with only three values. Why is scaling limited?

**Answer:** Few key values cause many documents to share identical keys, preventing fine range splits. Consider appending a high-cardinality suffix via refine if appropriate or resharding to a better key, while checking query prefixes and residency.

### Exercise 10 — Indivisible chunk

**Prompt:** One chunk holds all documents with `tenantId: "T-BIG"`, with no valid split point because the key is `tenantId` alone. Can adding shards without changing the key solve this?

**Answer:** No guarantee. Identical key values cannot split usefully into multiple chunks; adding shards does not divide that single value. You must change/refine the shard key or redesign partitioning when tenant data genuinely needs splitting. Manual chunk moves merely relocate the hotspot.

### Exercise 11 — When are hashed keys worse than ranged keys?

**Prompt:** 90% of requests fetch orders within contiguous `orderSeq`/`createdAt` intervals. What happens if you switch to hashed `orderSeq` to spread writes?

**Answer:** Hashing destroys range locality, causing key-range queries to broadcast and potentially hurting OLTP/report latency. Measure range query share and evaluate compound keys or separate read models; hashed is not an absolute win.

### Exercise 12 — Explain shows `IXSCAN` on 4 shards

**Prompt:** A query plan shows `IXSCAN` on all four shards. Can you conclude it targeted one shard?

**Answer:** No—`explain` itself shows four shards participated. Local index usage does not equate to targeted routing. Count participating shards and inspect keys/docs examined.

### Exercise 13 — Analytics broadcast

**Prompt:** A total revenue report across all tenants must read data from every shard. Should broadcasting be treated as a bug?

**Answer:** No. For cluster-wide analytics, parallel shard execution and merging can be completely natural. Optimize filters, shard-local indexes, partial `$group`, sort/merge, and read models.

### Exercise 14 — Full key in `updateOne`

**Prompt:** Shard key `{tenantId:1,orderId:1}`. Write an update transitioning an order from `CREATED` to `PAID` with clear routing and business conditions:

**Answer:**

~~~javascript
db.orders.updateOne(
  {
    tenantId: "T-A",
    orderId: "O-1001",
    status: "CREATED"
  },
  {
    $set: {
      status: "PAID",
      paidAt: new Date()
    }
  }
)
~~~

The full key enables targeted routing; the `status` filter guards the state transition. If `matchedCount: 0`, the order may be missing or already transitioned.

### Exercise 15 — `updateMany` missing the shard key

**Prompt:** `updateMany({status:"EXPIRED"},{$set:{archived:true}})` on a collection sharded by `tenantId`/`orderId`. What are the risks?

**Answer:** It can broadcast to many/all shards because the filter omits the shard key. Each document updates atomically on its own, yet the whole operation is not atomic without a transaction. If scoped to one tenant, pass `tenantId` from auth; if cluster-wide, apply batching, rate limiting, and monitoring.

### Exercise 16 — Upsert missing the shard key

**Prompt:** Backend upserts an order by `orderId` alone on a collection sharded by `{tenantId:1,orderId:1}`. Can you rely on fast, uniform routing across every MongoDB version?

**Answer:** No. Rules and routing for upserts and writes missing the full shard key vary by version, potentially involving the two-phase write protocol or precondition errors. APIs should pass the **full shard key** and unique business identity. Check `updateOne()` docs for your exact server version before deploying.

### Exercise 17 — How do refine shard key and reshard differ?

**Prompt:** A collection has shard key `{tenantId:1}`, and you want `{tenantId:1,orderId:1}` or `{orderId:"hashed"}`. Which operation fits each?

**Answer:** Appending a suffix while keeping the prefix can use **refine** when eligible. Dropping `tenantId`, changing the leading field, or restructuring the key requires **reshard** where supported. Evaluate index/unique constraints, query contracts, zones, and migration overhead.

### Exercise 18 — Should you reshard immediately when one API is slow?

**Prompt:** Key is `{tenantId:1,orderId:1}`; `GET /orders/{orderId}` broadcasts, yet the auth layer already knows `tenantId`. What should you do first?

**Answer:** Pass `tenantId` from auth context into the BSON filter, then re-measure targeted shards and p95 latency. Fixing the **query contract** is far lower risk than resharding the entire collection.

### Exercise 19 — Bucket key

**Prompt:** Key is `{tenantId:1,bucket:1,orderId:1}`, with `bucket = hash(orderId) mod 16`. What does a single-order lookup need?

**Answer:** It needs **`tenantId`, `bucket`, and `orderId`** (with `bucket` computed deterministically from `orderId`) for full-key targeting. `tenantId`-only queries must visit multiple bucket ranges—a trade-off between write spread and tenant-wide reads.

### Exercise 20 — Balancer enabled yet shards remain skewed

**Prompt:** `sh.getBalancerState()` returns `true`, yet owned bytes remain 70/15/15 after hours. Can you conclude the balancer has a bug?

**Answer:** Not yet. Check `balancerStatus`, `sh.status(true)`, migration logs, zone constraints, indivisible/jumbo ranges, and disk/network/replication health. An enabled balancer does not guarantee every range can split/migrate immediately.

### Exercise 21 — Chunk count vs. owned bytes

**Prompt:** Shard A has 200 chunks and B has 180 chunks, yet owned bytes are A=100 GB and B=140 GB. Which shard holds more data?

**Answer:** By **owned bytes**, B holds more data despite fewer chunks. Chunk count is not an absolute proxy for storage volume. Also inspect orphans, zones, and workload before balancing.

### Exercise 22 — Orphaned documents

**Prompt:** After migration, Shard A holds 20 GB of orphaned bytes. Should you add them into logical owned collection size when evaluating data balance?

**Answer:** No—do not count orphans as logically owned data. Use `numOwnedDocuments`/`ownedSizeBytes` for logical distribution; orphan metrics diagnose range deletion/migration cleanup. Never manually delete orphans directly on a shard `mongod`.

### Exercise 23 — Zone constraints

**Prompt:** Zone EU has only one shard, and all EU writes run hot. Does adding a shard to the cluster outside Zone EU automatically relieve EU write load?

**Answer:** Not necessarily. The balancer must obey placement rules; if the new shard is not in an eligible zone, EU data cannot migrate there. You must expand capacity inside the zone while honoring residency policies.

### Exercise 24 — Analyzing a shard key before resharding

**Prompt:** You plan to switch from `{tenantId:1,orderId:1}` to `{orderId:"hashed"}`. What must you measure first?

**Answer:** Cardinality/frequency/monotonicity, read/write distribution and targeting under the candidate key, hot-tenant impact, `tenantId`-only queries, range report workloads, unique index constraints, migration overhead, and capacity headroom. Use `analyzeShardKey` (7.0+) with representative query samples and staging load tests.

### Exercise 25 — Hot counter updates despite hashed orders

**Prompt:** Orders are sharded by hashed `orderId` and inserts spread well, yet the system stalls when every request runs `$inc` on `counters._id: "GLOBAL"`. Will changing the `orders` shard key help?

**Answer:** No; the bottleneck is the **hot counter document**. Consider bucketed counters with asynchronous aggregation, rate limits, or relaxing strictness. If an exact instantaneous single counter across all requests is mandatory, you must confront single-point write contention.

### Exercise 26 — Flash sale window

**Prompt:** Per-shard storage is 33/33/34%, and daytime writes are 30/34/36%. During a 15-minute flash sale, writes swing to 90/5/5%. What should you inspect?

**Answer:** Capture write distribution by tenant/key/value within the **15-minute window**, pinpoint the hot range/shard key, check targeted queries, and inspect cache/IOPS—do not rely on 24-hour averages. Workload skew from one tenant or a batch import is likely, not a balancer bug.

### Exercise 27 — Does the Java Driver auto-target by `orderId`?

**Prompt:** A Java method `orders.find(eq("orderId", id)).first()` runs against shard key `{tenantId:1,orderId:1}`. Does the driver infer `tenantId` from previous documents?

**Answer:** No. It sends the application’s BSON filter; the router lacks `tenantId` when omitted. Update the API to pass `authorizedTenantId` or redesign the mapping/key; never expect the driver to memorize shards from prior queries.

### Exercise 28 — Ranged key when analytics only queries recent data

**Prompt:** Data is range-sharded by `createdAt`; last-month reports are fast and targeted, yet peak inserts run hot. Should you immediately switch to hashed `createdAt`?

**Answer:** Insufficient evidence. Measure write load and range-read share first; hashing `createdAt` destroys range locality and may slow reports. Evaluate compound keys, bucketing, materialized aggregates, batch scheduling/throttling, and reshard only if net gains outweigh regressions.

### Exercise 29 — Unique `_id` on a sharded collection

**Prompt:** A collection is sharded on `{tenantId:1,orderId:1}`, and the app treats `_id` as a global key. Can you assume MongoDB prevents duplicate `_id` across all shards automatically?

**Answer:** Not by default. When `_id` is not the shard key, the `_id` index may enforce uniqueness **within each shard only**. For global ID uniqueness, use a compatible key/unique index or application-guaranteed global ID generation. Check unique index rules per server version.

### Exercise 30 — Designing a “fit all three” approach

**Prompt:** Pick a shard key for SaaS: 70% reads by `tenant+order`, 15% reads by `order`-only, 10% tenant-by-date reports, 5% global analytics. Peak writes come mostly from one tenant. Propose a process instead of guessing one key right away.

**Suggested answer:**

1. Gather hourly/per-tenant query samples; measure cardinality, frequency, and monotonicity of candidates.
2. Compare `{tenantId:1,orderId:1}`, `{tenantId:1,orderId:"hashed"}`, `{orderId:"hashed"}`, and bucketed models.
3. Check whether the 15% order-only APIs can pass `tenantId` from auth context.
4. Estimate cost for tenant-by-date reports when tenant data spans multiple shards, local indexes, and read models.
5. Benchmark with hot tenants, realistic shard counts, concurrency, and size/zone constraints.
6. Select the key minimizing total cost across **writes + OLTP targeted reads + analytics**, not storage % alone.
7. If changing a production key, prepare a staging runbook, unique-constraint checks, capacity headroom, cutover plan, and post-launch latency monitoring.

A valid answer can vary with SLAs and user journeys; what matters is defending **trade-offs** with measured evidence.

## 21. Symptom-based operational checklist

### 21.1. When write QPS concentrates on one shard

- Does the shard key have **monotonic values** or too few distinct values?
- Does the hot shard own the `MaxKey`/`MinKey` range?
- Is there a hot tenant or hot document?
- Are storage bytes balanced while writes are skewed?
- Are there enough chunks/ranges to distribute, or is one range unsplittable?
- Are scheduled bulk inserts/imports causing spikes?
- Would a hashed key distribute writes/queries, or do all writes share one value?
- Do we need compound hashed/bucketing or an invariant change before resharding?

### 21.2. When data is skewed across shards

- How are owned docs/bytes distributed? Are orphaned records distorting numbers?
- Are zone policies or uneven shard capacities in effect?
- Is the balancer enabled, and are migrations attempting/failing?
- Are there jumbo/indivisible chunks or heavily duplicated key values?
- Has data been skewed since initial sharding, after adding a shard, or recently?
- Do we need refine/reshard, or just fix/wait for migrations?

### 21.3. When queries get slower as shards are added

- Do OLTP point-lookup APIs include the **full shard key/prefix** in filters?
- Does `explain` show one or multiple participating shards?
- What are `IXSCAN`/`FETCH`/`COLLSCAN` and `docsExamined` on each shard?
- Do `sort`/`limit`/`skip`/`$group`/`$lookup` trigger heavy merges?
- Can the shard key be injected from auth context or a lookup mapping?
- Is a hashed key forcing range predicates to broadcast?
- Is one query shape causing trouble or the entire workload?
- Does the query genuinely require cluster-wide analytics?

## 22. Official MongoDB documentation

Use the links below to verify exact syntax and limits for your **MongoDB Server version**, especially for sharding DDL, write targeting, and resharding:

- [Sharding Introduction and Architecture](https://www.mongodb.com/docs/manual/sharding/) — shard keys, shards, chunks/ranges, query routers, and overall architecture.
- [Choose a Shard Key](https://www.mongodb.com/docs/manual/core/sharding-choose-a-shard-key/) — cardinality, frequency, monotonicity, and query patterns.
- [Troubleshoot Shard Keys](https://www.mongodb.com/docs/manual/core/sharding-troubleshooting-shard-keys/) — data skew, uneven load distribution, and scatter-gather.
- [Ranged Sharding](https://www.mongodb.com/docs/manual/core/ranged-sharding/) — contiguous partitioning by key ranges.
- [Hashed Sharding](https://www.mongodb.com/docs/manual/core/hashed-sharding/) — hashed keys, write distribution, and range-query trade-offs.
- [Routing with mongos](https://www.mongodb.com/docs/manual/core/sharded-cluster-query-router/) — targeted vs. broadcast, query modifiers, single/multi-writes.
- [Sharded Cluster Balancer](https://www.mongodb.com/docs/manual/core/sharding-balancer-administration/) — range migrations and balancing by data distribution/zones.
- [Troubleshoot Stuck Chunk Migrations](https://www.mongodb.com/docs/manual/troubleshooting/chunk-migrations-stuck/) — balancer logs, jumbo/indivisible ranges, and handling migration failures.
- [`sh.status()`](https://www.mongodb.com/docs/manual/reference/method/sh.status/) — inspecting chunk/zone/topology info in `mongosh`.
- [`db.collection.getShardDistribution()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.getsharddistribution/) — data distribution for a single collection.
- [`sh.getShardedDataDistribution()`](https://www.mongodb.com/docs/manual/reference/method/sh.getshardeddatadistribution/) — owned/orphaned document sizes per shard (6.0.3+).
- [`db.collection.analyzeShardKey()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.analyzeshardkey/) — evaluating candidate keys and read/write distribution.
- [`configureQueryAnalyzer`](https://www.mongodb.com/docs/manual/reference/command/configureQueryAnalyzer/) — enabling query sampling for shard key analysis.
- [Refine a Shard Key](https://www.mongodb.com/docs/manual/core/sharding-refine-a-shard-key/) — appending a suffix to an existing shard key.
- [Reshard a Collection](https://www.mongodb.com/docs/manual/core/sharding-reshard-a-collection/) — changing shard keys, redistribution, and production prerequisites.
- [Sharding Zone-Based Architecture](https://www.mongodb.com/docs/manual/core/zone-sharding/) — data residency and zone-based placement.
- [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — unique constraints on sharded collections.
- [`db.collection.updateOne()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateOne/) — version-specific routing/upsert/shard-key update rules.
- [`db.collection.updateMany()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateMany/) — multi-update routing and per-document atomicity.
- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — reading plans when one or multiple shards participate.
- [Aggregation Pipeline on Sharded Collections](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-sharded-collections/) — split/merge pipelines and aggregation optimization.
- [Java Sync Driver — Read Operations](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/) — building shard-key-friendly filters.
- [MongoDB 8.0 Sharding Docs](https://www.mongodb.com/docs/v8.0/sharding/) — 8.0 reference when deployments are not on the latest manual version.

## 23. Conclusion

**Sharding does not automatically guarantee an evenly balanced system.** Data distribution and request routing depend directly on the **shard key pattern, actual shard key values, query predicates, and placement metadata**.

When encountering **write hotspots**, look for monotonic keys, hot tenants/keys, or hot documents rather than blindly adding shards. When seeing **data skew**, distinguish owned bytes/chunks/orphans, balancer activity, and zone constraints from QPS load. When a **point query lacks the shard key**, use `explain` to check if it scatter-gathers; local indexes on shards never replace shard targeting.

The lowest-risk remedies are usually **fixing queries to pass the shard key**, adding appropriate local indexes, throttling or remodeling hot workloads, and clarifying access patterns. Only when the existing key itself proves to be the architectural bottleneck should you evaluate **refining or resharding** using `analyzeShardKey`, representative data, unique constraints, and a cutover plan. A good shard key is not one that puts every query on a single shard, but one that **balances write distribution, data placement, and the application’s most critical access paths** in real production workloads.
