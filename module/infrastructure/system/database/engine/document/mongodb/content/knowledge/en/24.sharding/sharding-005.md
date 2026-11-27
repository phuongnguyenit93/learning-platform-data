# Ranged Sharding, Hashed Sharding, and Compound Keys in MongoDB

## 1. Why is choosing a sharding strategy important?

When data and traffic exceed the capacity of a single MongoDB replica set to serve efficiently, **sharding** allows distributing a collection’s data across multiple **shards**. Each shard stores a portion of the data, typically as its own replica set. Applications access the sharded cluster via **`mongos`**, the router responsible for directing requests to the relevant shards.

However, “having multiple shards” does not mean data or load divides evenly on its own. The **shard key** determines which data range a document belongs to; **ranged**, **hashed**, and field ordering in **compound keys** directly affect:

- Distribution of storage and insert/update workloads across shards.
- Ability for queries to **target one or a few shards**, instead of hitting all shards.
- Efficiency of equality, range, and sort queries.
- Risk of an overly common key value creating a **hot chunk/hot shard**.
- Fit with zone sharding, data locality, and unique constraints.
- Cost of the balancer, chunk migrations, shard key changes, and cluster scaling.

Suppose an orders application writes:

```javascript
{
  _id: ObjectId("6927b73c0000000000000001"),
  tenantId: "TENANT-A",
  orderId: "ORD-1001",
  customerId: "CUS-42",
  createdAt: ISODate("2026-11-14T09:15:00Z"),
  amountMinor: NumberLong("259000"),
  status: "PAID"
}
```

If most queries ask to “fetch a tenant’s orders by time range,” choosing `{ createdAt: 1 }` may favor range queries yet introduce hotspots from continuously increasing timestamps. Choosing `{ orderId: "hashed" }` may scatter inserts better yet lose tenant/time locality. Choosing `{ tenantId: 1, orderId: "hashed" }` creates another trade-off: preserving scoping by tenant while distributing by hashed order ID.

> **Foundational conclusion:** a good shard key must balance **data distribution**, **load distribution**, and **routing efficiency for real queries**. There is no single right key type for every collection.

This lesson progresses from architecture, the three main strategies, and `mongosh` and Java Sync Driver examples to monitoring and evolving keys as a system grows.

---

## 2. Components of a sharded cluster

```text
                  Application / Java Driver
                            |
                            v
                    +---------------+
                    | mongos router |
                    +---------------+
                      /      |      \
                     v       v       v
                 Shard A  Shard B  Shard C
                 (RS)     (RS)     (RS)
                    \       |       /
                     \      |      /
                  Config Server Replica Set
                    Metadata: ranges, shards,
                    routing / placement info
```

- **`mongos`** receives queries and uses the shard key and metadata to locate target shards.
- **Config server replica set** maintains sharded cluster metadata.
- **Shards** store the actual data. In modern deployments, each shard is a replica set for high availability.
- **Shard key** is a field or combination of fields in documents used to partition the value space.
- **Chunk/range** is a contiguous interval of the **shard key space** assigned to a shard.
- **Balancer** can move ranges between shards to improve balance and enforce zone placement.

A single document is never split across multiple shards. Each document belongs to **one shard** at any given time, even though that shard’s replica set keeps copies for replication.

### 2.1. Chunks have half-open intervals

A range typically has:

```text
[lowerBound, upperBound)
```

Meaning the lower bound is **inclusive** and the upper bound is **exclusive**.

Example on key `orderNumber`:

```text
Shard A: [MinKey, 10000)
Shard B: [10000, 20000)
Shard C: [20000, MaxKey)
```

An order with `orderNumber = 10000` belongs to Shard B’s range, **not** A. In practice, range boundaries and placement are managed by the cluster and can change when chunks split/migrate.

### 2.2. A shard key is not an arbitrary index

A collection can have many indexes supporting filters/sorts, yet it has only **one active shard key pattern** for distributing documents. Example:

```javascript
// Indexes serving queries:
{ tenantId: 1, createdAt: -1 }
{ customerId: 1, status: 1 }

// Shard key may be:
{ tenantId: 1, orderId: "hashed" }
```

Do not confuse calling `createIndex({ userId: "hashed" })` with **having sharded the collection**. A hashed index is an index structure; a collection only becomes sharded after an administrative operation like `sh.shardCollection(...)` on a suitable deployment.

---

## 3. Ranged sharding: splitting by value intervals

**Ranged sharding** (range-based sharding) divides the shard key space into contiguous intervals.

Example shard key:

```javascript
{ customerId: 1 }
```

Conceptual view:

```text
customerId value space (ordered by BSON comparison)

MinKey ---- C100 ---- C500 ---- C900 ---- MaxKey
   |          |         |         |
   +--Range 1-+--Range 2+--Range 3+--Range 4
        |           |          |          |
      Shard A     Shard B    Shard C    Shard A
```

Boundaries and shards in this diagram are **illustrative** only. A single shard can own multiple non-contiguous ranges. `mongos` inspects the query’s shard key predicates to identify which ranges to visit.

**Property:** shard key values close together in comparison order tend to fall into the same or adjacent ranges. Thus, range predicates on the shard key can route to a **narrower set of shards** than a broadcast query.

### 3.1. Creating a ranged-sharded collection

The following administrative commands must run on a **sharded cluster’s `mongos`** with appropriate privileges:

```javascript
// Example for an empty collection or one that already has a supporting index.
sh.shardCollection(
  "commerce.orders",
  { customerId: 1 }
);
```

If the collection already contains data, create the supporting shard key index **before** sharding:

```javascript
db.getSiblingDB("commerce").orders.createIndex({
  customerId: 1
});

sh.shardCollection(
  "commerce.orders",
  { customerId: 1 }
);
```

If the collection is empty, MongoDB can create the supporting shard key index as needed. Sharding configuration should **not** run unconditionally during application startup. It is an administrative/migration operation requiring a rollout plan.

### 3.2. Ranged sharding enables targeted range queries

Suppose shard key `{ createdAt: 1 }`:

```javascript
db.orders.find({
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  }
});
```

`mongos` can locate **the ranges covering November**, then send the query only to shards owning those ranges. The actual number of shards contacted depends on range placement at query time—**not necessarily one shard**.

### 3.3. When does ranged sharding fit?

Ranged sharding is often useful when:

- Important queries use range predicates on the **shard key or a compatible prefix**.
- Locality is needed along an ordered attribute, such as time, tenant, or group ID.
- Zone placement rules rely on real value intervals.
- The shard key has high cardinality and individual values do not have excessive frequency.
- Write workloads **do not continuously pile into the start/end of the key space**.

However, choosing `{ createdAt: 1 }` alone for a continuous event-ingestion system typically risks write hotspots.

---

## 4. Hotspots caused by monotonically increasing shard keys

Suppose every order receives a continuously incrementing `orderNumber`:

```text
100001, 100002, 100003, 100004, ...
```

If the shard key is:

```javascript
{ orderNumber: 1 }
```

new values continually land in the **highest range** bounded by `MaxKey`:

```text
Existing ranges:
[MinKey, 100000)    -> Shard A
[100000, 200000)    -> Shard B
[200000, MaxKey)    -> Shard C  <-- all new inserts go here
```

During this window, Shard C may receive almost all inserts even if the three shards have roughly balanced total storage.

MongoDB can split/migrate ranges when appropriate, yet **moving ranges does not guarantee eliminating the hotspot caused by monotonicity at any given moment**.

### 4.1. Fields prone to monotonic increases/decreases

- `createdAt` or event timestamps.
- `_id` using time-generated `ObjectId`s (not purely random).
- Auto-incrementing codes or sequences.
- Ascending log offsets or version numbers.
- Continuously decreasing counters carry the symmetric risk at the `MinKey` range.

### 4.2. Good range reads do not imply balanced writes

This is a key trade-off:

```text
Shard key = { createdAt: 1 }

Read  [10:00, 11:00)     -> can target few ranges/shards.
Write current timestamp  -> funnels into the trailing range.
```

Optimizing the **read path** with ranged sharding can bottleneck the **write path**. If one shard saturates CPU/IOPS while others sit idle, inspect the shard key and write distribution rather than just document counts per shard.

### 4.3. Why adding a secondary index is not enough

Creating:

```javascript
db.orders.createIndex({ createdAt: 1 });
```

helps specific queries inside each shard, but **does not change** data distribution if the shard key remains `{ orderNumber: 1 }`. Routing and hotspots are still governed by the shard key.

---

## 5. Hashed sharding: partitioning by hash value

**Hashed sharding** uses a hash computed from a field’s value, then distributes documents across **intervals of the hash value**, rather than the original value order.

Example:

```javascript
sh.shardCollection(
  "commerce.orders",
  { orderId: "hashed" }
);
```

`mongos` and the servers compute the hash automatically. The application **does not need** to pre-hash IDs for routing to work.

Visualization:

```text
Original orderId:
  ORD-1001  ORD-1002  ORD-1003  ORD-1004  ORD-1005
      |         |         |         |         |
      v         v         v         v         v
  hash(...)  hash(...)  hash(...)  hash(...) ...
      \         /           \          /      /
     Hash range A         Hash range B     Hash range C
         |                    |                |
       Shard A              Shard B          Shard C
```

Hashes in the diagram do not represent exact hash values or specific shard placement.

### 5.1. Why does hashed sharding fit monotonic keys?

Two orders with consecutive IDs do not necessarily produce nearby hashes. Thus, as `orderId` increments sequentially, hashing spreads inserts across multiple ranges/shards, avoiding a single `MaxKey` range absorbing all fresh writes like ranged sharding.

Conditions for good distribution:

- The field has **many distinct values**.
- No single key value occurs overwhelmingly often.
- Hash distribution and chunks have grown/balanced sufficiently.
- Workloads do not heavily concentrate elsewhere in the system.

**Hashed sharding does not guarantee every shard always gets exactly 1/N of traffic.** Imbalances can still arise from document sizes, request distribution, balancer behavior, chunk migrations, hot tenants, and resource factors.

### 5.2. Equality lookups usually target well

With key `{ orderId: "hashed" }`:

```javascript
db.orders.findOne({
  orderId: "ORD-1001"
});
```

The router hashes the equality value and identifies the corresponding hash range/chunk. Normally such a full-key query can target **one shard** per routing metadata.

### 5.3. Range lookups on the original key are usually worse

```javascript
db.orders.find({
  orderId: {
    $gte: "ORD-1000",
    $lt: "ORD-2000"
  }
});
```

Values adjacent in string order are **not adjacent after hashing**, so range queries on the original `orderId` cannot easily target a narrow set of hash ranges. The router typically must send the query to many or all shards.

If APIs frequently scan by time or ID range, hashing that field can incur significant read cost.

### 5.4. Hashed does not mean MongoDB generates random keys

The application still stores:

```javascript
{ orderId: "ORD-1001" }
```

MongoDB uses the hash internally in the index and routing. You **do not need** to add an `orderIdHash` field to documents in Java code just to enable hashed sharding.

---

## 6. Important limitations of hashed indexes

### 6.1. Cannot create unique hashed indexes

Invalid:

```javascript
// Cannot use unique on a hashed index:
db.orders.createIndex(
  { orderId: "hashed" },
  { unique: true }
);
```

And do not use:

```javascript
// Cannot use unique: true with a hashed shard key:
sh.shardCollection(
  "commerce.orders",
  { orderId: "hashed" },
  true
);
```

MongoDB does not allow unique constraints directly on a hashed index/shard key. This **does not mean `orderId` can never be unique**, rather that uniqueness must be designed with another valid key/index meeting sharded collection constraints.

### 6.2. Hashed multikey indexes are not supported

Hashed indexes do not support array fields:

```javascript
{ userIds: ["U1", "U2"] }
```

Do not shard on:

```javascript
{ userIds: "hashed" }
```

if the field holds arrays and requires multikey semantics. Compound hashed indexes also **cannot become multikey indexes**, even if the array is in another field of the compound index.

### 6.3. Floating-point values are truncated to integers before hashing

MongoDB **truncates floating-point values to 64-bit integers prior to hashing**. Thus, `Double` values like `2.2`, `2.3`, and `2.9` can produce the exact same hash.

```text
Double 2.2 --> integer 2 --> hash(2)
Double 2.3 --> integer 2 --> hash(2)
Double 2.9 --> integer 2 --> hash(2)
```

This is a form of **conversion-induced hash collision**, undesirable for keys needing distinction across fractional values. Hashed indexes also have precision limits for floating-point values beyond documented bounds (the docs cite 2^53).

**Do not choose fractional Double fields like `price`, `temperature`, or `score` as a hashed shard key** if the goal is distributing by distinct decimal values.

### 6.4. Cannot use hashed indexes to cover queries

Hashed indexes do not support **covered queries** the way a regular B-tree index can supply all projected fields directly. Queries still need to fetch the underlying documents.

Nor does a hashed index optimize range sorts on the **original** field values. If an API needs:

```javascript
db.orders.find({ customerId: "C1" })
  .sort({ createdAt: -1 });
```

a secondary index matching that filter/sort on each shard may be required. **The shard key index serving routing is rarely optimal for every query.**

---

## 7. Ranged vs. hashed: comparison table

| Criterion | Ranged sharding | Hashed sharding |
| --- | --- | --- |
| Basis of partitioning | Order of original shard key values | Hash order of a field |
| Full shard key equality | Can target exact range/shard | Can target hash range/shard |
| Range predicate on original key | Usually targets better | Usually must hit multiple shards |
| Monotonic inserts | Risk of piling into `MinKey`/`MaxKey` range | Reduces risk if field has many values |
| Proximity of original values | Often in same or nearby ranges | Usually scattered after hashing |
| Locality by tenant/region | Preserves locality with prefix | Pure hash loses original locality |
| Zone sharding on real ranges | More natural | Ranges on hashed values do not mirror real ranges |
| Direct uniqueness on shard key | Possible under proper rules | Uniqueness not supported on hashed indexes |
| Read profile | Fits range queries with shard key | Fits equality/key lookups |
| Risks | Hot end-range, low cardinality, skew | Range scatter-gather, collisions, lost locality |
| Supports compound keys? | Yes | Yes; one field marked `"hashed"` |

Do not pick ranged just for fast reads or hashed just for even writes. Measure both **shards touched per request** and **traffic share per shard**.

---

## 8. What is a compound shard key?

A **compound shard key** consists of two or more fields in a **specific order**.

Example ranged compound key:

```javascript
{
  tenantId: 1,
  orderId: 1
}
```

Or:

```javascript
{
  region: 1,
  createdAt: 1,
  orderId: 1
}
```

Field order affects:

- How values are **ordered from left to right**.
- Which prefixes allow the router to narrow ranges.
- Which queries can target few shards.
- How documents distribute within a single prefix value.
- Selectivity, uniqueness, and zone placement strategies.

### 8.1. Compound key order is lexicographical

With key:

```javascript
{ tenantId: 1, orderId: 1 }
```

the key space is ordered as:

```text
(TENANT-A, ORD-1)
(TENANT-A, ORD-2)
(TENANT-A, ORD-3)
(TENANT-B, ORD-1)
(TENANT-B, ORD-2)
...
```

That is, `tenantId` sets the primary domain; `orderId` subdivides within each tenant.

With the reversed key:

```javascript
{ orderId: 1, tenantId: 1 }
```

ordering prioritizes `orderId`. Both keys contain the **same fields yet yield completely different distribution and routing**.

### 8.2. Compound keys increase cardinality

Suppose:

```text
tenantId has 100 values.
Each tenant has 1,000,000 distinct orderIds.
```

Choosing `{ tenantId: 1 }` yields only 100 shard key values, and each tenant occupies a single indivisible value on that key.

Choosing:

```javascript
{ tenantId: 1, orderId: 1 }
```

increases distinct key combinations. MongoDB gains room to split chunks **inside the same tenant** by `orderId`.

This can improve scalability for large tenants; however, watch out if `orderId` ascends monotonically within a tenant and concentrates inserts at that tenant’s tail end.

### 8.3. More fields is not automatically better

A key like:

```javascript
{ tenantId: 1, region: 1, status: 1, createdAt: 1, orderId: 1 }
```

is not inherently better than a shorter key. Extra fields enlarge key size, complicate routing/upserts/updates, and add zero benefit if real queries filter on non-prefix fields.

Prioritize fields by **access patterns** and distribution goals rather than maximizing field count.

---

## 9. The prefix rule in compound shard keys

If the shard key is:

```javascript
{ tenantId: 1, orderId: 1 }
```

compare:

```javascript
// Equality on the entire shard key:
db.orders.findOne({
  tenantId: "TENANT-A",
  orderId: "ORD-1001"
});
```

This query typically targets **one chunk/shard**.

```javascript
// Only the tenantId prefix:
db.orders.find({
  tenantId: "TENANT-A"
});
```

The router can narrow down to ranges belonging to tenant A, yet tenant A may span **multiple chunks and shards**. A single shard is not guaranteed.

```javascript
// Missing the prefix:
db.orders.find({
  orderId: "ORD-1001"
});
```

Without `tenantId`, the router typically **cannot identify a narrow prefix region**, so it may scatter-gather across many shards.

### 9.1. Illustrative routing table

| Query | Full key present? | Notes |
| --- | --- | --- |
| `{ tenantId: "A", orderId: "O1" }` | Yes | Typically targets one shard. |
| `{ tenantId: "A" }` | Prefix present | Narrows to tenant A’s ranges; may span multiple shards. |
| `{ orderId: "O1" }` | No | Typically broadcasts or targets broadly. |
| `{ tenantId: "A", orderId: { $gte: "O1", $lt: "O9" } }` | Prefix equality + range | Can target chunks intersecting the requested range. |
| `{ tenantId: { $in: ["A", "B"] }, orderId: "O1" }` | Multiple prefix values | Can target range sets for A and B. |
| `{ status: "PAID" }` | No | No shard key predicate; typically scatter-gather. |

These are routing expectations, **not a fixed `explain` result**. Placement shifts as the balancer runs, and the query planner may apply additional optimizations depending on version.

### 9.2. Shard key prefix vs. secondary index prefix

MongoDB requires an index supporting the shard key, yet business queries may still need other indexes:

```javascript
// Shard key:
{ tenantId: 1, orderId: 1 }

// Separate index to list a tenant's newest orders:
{ tenantId: 1, createdAt: -1, _id: -1 }
```

Query:

```javascript
db.orders.find({
  tenantId: "TENANT-A",
  status: "PAID"
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
```

The query can target only shards holding tenant A; on **each targeted shard**, the secondary index helps filter and sort. Do not confuse having a shard key prefix with already having an optimal compound index for every `sort`.

---

## 10. Compound hashed shard keys: combining locality and distribution

MongoDB supports **compound hashed indexes** as shard keys. Only **one field** in a compound index may be marked `"hashed"`; remaining fields are ranged/non-hashed fields.

Examples:

```javascript
{ tenantId: 1, orderId: "hashed" }
```

Or:

```javascript
{ orderId: "hashed", createdAt: 1 }
```

Or:

```javascript
{ region: 1, tenantId: 1, orderId: "hashed" }
```

**Hashing applies only to the field marked `"hashed"`**, rather than hashing the entire `{ tenantId, orderId }` tuple into a single value.

### 10.1. Pattern A — non-hashed prefix, hashed suffix

```javascript
{
  tenantId: 1,
  orderId: "hashed"
}
```

Ordering structure:

```text
original tenantId
    |
    +--> hash(orderId) within tenant domain
```

Effects:

- Queries with `tenantId` can narrow to ranges belonging to that tenant.
- Hashed `orderId` helps scatter documents/inserts **within the tenant’s domain**, provided enough chunks exist and the balancer distributes them.
- Fits multi-tenant systems wanting tenant-level scoping while having large tenants that need distribution.
- Can support zone ranges on the non-hashed prefix when zones are properly designed.

Trade-offs:

- A tenant with few documents may still live on a single shard rather than scattering evenly.
- An extremely large tenant can span multiple shards, so tenant-only queries may still hit multiple shards.
- Range queries on original `orderId` lose the locality of `{ tenantId: 1, orderId: 1 }`.
- Hotspots on **one heavily repeated `orderId` value** are not broken into multiple chunks because all documents sharing the full shard key still sit in one key region.

### 10.2. Pattern B — hashed prefix, non-hashed suffix

```javascript
{
  orderId: "hashed",
  createdAt: 1
}
```

Meaning:

```text
hash(orderId)
    |
    +--> createdAt ordered within each hash prefix
```

This pattern can be useful when most requests access by `orderId`, wanting to distribute inserts/order groups first while utilizing the time suffix for queries that supply the full prefix.

Trade-offs:

- Queries specifying only `createdAt` **without `orderId`** typically target broadly.
- Cannot use the hashed prefix to define zones by original `createdAt` order.
- If all documents for an `orderId` arrive simultaneously with the same `createdAt`, the key may still lack workload separation.

### 10.3. Pattern C — zone-friendly prefix

```javascript
{
  region: 1,
  customerId: "hashed"
}
```

Using `region` as a non-hashed prefix enables organizing regional zone ranges, while hashed `customerId` distributes within each region.

However, creating zones and pre-splitting compound hashed keys **have specific prerequisites**; simply putting `region` first does not automatically pin all EU data to one data center. You must define zone ranges, assign shards to zones, and verify balancer convergence.

---

## 11. Comparing three key choices for an orders collection

Suppose the workload is:

```text
40%  Fetch order by tenantId + orderId.
30%  List latest orders by tenantId.
20%  Insert new continuously ascending orderIds.
10%  System-wide summary reports by time.
```

Three options:

### Option 1 — `{ tenantId: 1, orderId: 1 }`

Pros:

- Full equality targets well.
- Tenant-only queries narrow to the tenant domain.
- `orderId` ranges within a tenant retain locality.

Cons:

- For huge tenants inserting monotonically increasing `orderId`s, the tail end of that tenant’s domain can run hot.
- If writes concentrate on one tenant, this prefix can skew.

### Option 2 — `{ orderId: "hashed" }`

Pros:

- Spreads inserts across distinct `orderId`s.
- Equality lookups by `orderId` target well.

Cons:

- Tenant-only queries generally broadcast because `tenantId` is **not in the shard key**.
- No locality guarantee for per-tenant listing requests.
- Original `orderId` range queries do not target narrowly.

### Option 3 — `{ tenantId: 1, orderId: "hashed" }`

Pros:

- Full `tenantId + orderId` lookups target well.
- Opportunity to spread writes of large tenants via hashing.
- Queries with the `tenantId` prefix narrow scope compared to pure hashed `orderId`.

Cons:

- Per-tenant queries may still run across multiple shards if the tenant spans widely.
- Range queries on `orderId` within a tenant lose locality.
- Effectiveness depends on cardinality, chunk count, initial distribution, and per-tenant load.

**There is no universal winner.** If 80% of requests are per-tenant `orderId` ranges, ranged compound may win. If new `orderId` inserts are very high and equality lookups dominate, compound hashed is worth testing.

---

## 12. Even distribution is not just document count

A shard holding 1 million tiny documents may consume less disk and CPU than another holding 200,000 huge documents or serving heavy queries.

When evaluating a shard key, distinguish:

- **Data distribution:** document counts, bytes, and chunk ownership per shard.
- **Read distribution:** read requests and CPU/I/O per shard.
- **Write distribution:** inserts/updates/deletes, throughput, and lock/I/O pressure.
- **Query targeting:** average shards contacted per query.
- **Latency:** p50/p95/p99 from the application’s perspective, not just one shard’s latency.
- **Range migration:** chunk moves, balancing time, jumbo chunks, and affected operations.

A shard key producing balanced data distribution is **insufficient** if 90% of queries continually read data from the same customer/tenant, causing a hot read shard.

### 12.1. Cardinality

Cardinality is the number of distinct shard key values. A low-cardinality key:

```javascript
{ status: 1 } // "NEW", "PAID", "CANCELLED"...
```

is typically very poor for sharding a large collection. Even with 10 shards, very few distinct values limit how finely the shard key space can be divided.

### 12.2. Frequency and skew

Suppose `tenantId` has one million values, yet **one tenant holds 70% of the data**. High cluster-wide cardinality does not solve a single “hot tenant.”

Adding a sufficiently discriminating field:

```javascript
{ tenantId: 1, orderId: "hashed" }
```

opens the possibility of dividing a large tenant’s data across multiple ranges/shards, though you must measure after the balancer actually distributes it.

### 12.3. Monotonicity

If the key field always increases, ranged sharding risks a hot tail range. Hashed values generally handle **ascending order issues** better, yet cannot fix frequency skew if one key value repeats excessively.

### 12.4. Query patterns

Quantify workload by query shape:

```text
GET /orders/{orderId}
GET /tenants/{tenantId}/orders
GET /tenants/{tenantId}/orders?from=...&to=...
POST /orders
GET /reports/orders?from=...&to=...
```

The shard key must be chosen based on **real request weights and costs**, not whichever field “looks most random.”

---

## 13. Scatter-gather: when must the router query multiple shards?

**Targeted query**: `mongos` uses shard key conditions to pinpoint shards that may hold matching results.

**Scatter-gather/broadcast**: `mongos` must send the query to many or all shards because it cannot narrow the shard key space sufficiently.

Example shard key:

```javascript
{ tenantId: 1, orderId: "hashed" }
```

Queries:

```javascript
// Full shard key equality: targeted.
db.orders.findOne({
  tenantId: "T1",
  orderId: "O100"
});

// tenantId prefix: narrows to T1's ranges,
// though T1 may span multiple shards.
db.orders.find({
  tenantId: "T1"
});

// Missing tenantId; orderId only.
// Usually cannot target efficiently under this compound key.
db.orders.findOne({
  orderId: "O100"
});

// Missing shard key:
// typically scatter-gather.
db.orders.find({
  status: "PAID"
});
```

### 13.1. Scatter-gather is not always wrong

An analytical report over the whole dataset may **intentionally** leverage parallel reads across shards:

```javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $group: { _id: "$region", total: { $sum: 1 } } }
]);
```

If the problem genuinely requires reading the entire cluster, broadcasting makes sense. The problem is when **high-frequency online requests** like “get order details” broadcast simply because the API omits the shard key.

### 13.2. Secondary indexes do not prevent broadcast

Even if you create:

```javascript
db.orders.createIndex({ status: 1 });
```

a query filtering only on `status` can still be sent to every shard, with each shard using its local index. **Local indexes** reduce work per shard; the **shard key** reduces how many shards must be contacted. They are two separate optimization layers.

### 13.3. Do not omit shard key filters in Java calls

If an API knows both `tenantId` and `orderId`, do not send only `orderId` just because it is “business-unique.” Full shard key predicates improve targeting and often satisfy update/upsert requirements. API/DTO designs should preserve necessary routing fields.

---

## 14. Relationship with sort, pagination, and indexes

Suppose a hot query:

```javascript
db.orders.find({
  tenantId: "T1",
  status: "PAID"
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
```

Shard key:

```javascript
{ tenantId: 1, orderId: "hashed" }
```

does not automatically mean the query has an index supporting the newest-first sort. You can create a **secondary index**:

```javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
});
```

Understand:

- The shard key helps `mongos` determine **which shards may contain tenant T1**.
- The secondary index helps each shard filter and sort efficiently.
- If the tenant’s data spans multiple shards, `mongos` may need to **merge-sort results from multiple shards**.
- `limit(20)` does not make querying multiple shards cost the same as querying one shard.
- Deep pagination using `skip(100000)` remains expensive even with good indexes.

### 14.1. Keyset pagination

For `(createdAt desc, _id desc)` ordering, cursor/keyset pagination can be used:

```javascript
const lastTs = ISODate("2026-11-14T07:00:00Z");
const lastId = ObjectId("6927b73c0000000000000002");

db.orders.find({
  tenantId: "T1",
  status: "PAID",
  $or: [
    { createdAt: { $lt: lastTs } },
    {
      createdAt: lastTs,
      _id: { $lt: lastId }
    }
  ]
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
```

This is an illustrative pagination pattern. If `_id` uses a different BSON type, pass `lastId` in that matching type. Across multiple shards, pagination/merge stability must still be tested under concurrent writes.

---

## 15. Constraints on shard key supporting indexes

MongoDB requires a sharded collection to have an **index supporting the shard key**:

- The index can be the exact shard key index.
- Or a compound index where the **shard key is a prefix** of the index.
- If the collection is **empty**, `sh.shardCollection()` can create the supporting index if absent.
- If the collection **already has data**, the supporting index must be created **before** sharding the collection.
- Do not drop or hide the last remaining index supporting the shard key, aside from specific version-supported hashed shard key index exceptions.

Example:

```javascript
// Shard key:
{ tenantId: 1, orderId: 1 }

// Supporting index, key is a prefix:
{ tenantId: 1, orderId: 1, createdAt: -1 }

// Does NOT support shard key prefix because order is reversed:
{ orderId: 1, tenantId: 1 }
```

### 15.1. Creating an index does not automatically shard the collection

```javascript
db.orders.createIndex({ tenantId: 1, orderId: 1 });
```

does not mean the collection is sharded. You must run:

```javascript
sh.shardCollection(
  "commerce.orders",
  { tenantId: 1, orderId: 1 }
);
```

on `mongos` with valid privileges and preconditions.

### 15.2. Hashed and compound hashed indexes

```javascript
// Prepare the index:
db.orders.createIndex({
  tenantId: 1,
  orderId: "hashed"
});

// Use the matching shard key:
sh.shardCollection(
  "commerce.orders",
  { tenantId: 1, orderId: "hashed" }
);
```

The snippet is split into two steps for clarity. In real execution, ensure `db` is `commerce`, the collection state fits, existing unique/indexes do not conflict, and your server version supports compound hashed shard keys.

### 15.3. Collation

If a collection has a default collation other than `"simple"`, sharding imposes specific requirements on collation and the supporting shard key index. In some cases `sh.shardCollection()` requires specifying `{ locale: "simple" }` in `options`.

Do not ignore this requirement when sharding collections with locale-specific string data. Shard keys require consistent comparison semantics across the cluster.

---

## 16. Unique indexes in sharded collections

This is a frequent source of design bugs, especially for order IDs and idempotency keys.

### 16.1. Ranged sharded collections

MongoDB can enforce unique constraints when the unique index uses the **shard key or a compound index prefixed by the shard key** under supported conditions.

Example shard key:

```javascript
{ tenantId: 1, orderId: 1 }
```

Uniqueness on the **full pair** makes sense:

```javascript
db.orders.createIndex(
  { tenantId: 1, orderId: 1 },
  { unique: true }
);
```

This guarantees `(tenantId, orderId)` is unique; it does **not** guarantee `orderId` is globally unique across all tenants.

When calling `shardCollection` with uniqueness on the shard key itself:

```javascript
sh.shardCollection(
  "commerce.orders",
  { tenantId: 1, orderId: 1 },
  true
);
```

Prerequisites on existing indexes and collection state must be satisfied. Do not run the command without checking for duplicate data first.

### 16.2. Hashed shard keys cannot have `unique: true`

```javascript
// Invalid:
sh.shardCollection(
  "commerce.orders",
  { orderId: "hashed" },
  true
);
```

Hashed indexes do not directly support uniqueness. If `orderId` is a business identity that must be globally unique, you need **a supported ID generation scheme and separate constraint mechanism**; never assume hash routing proves uniqueness.

### 16.3. `_id` is not necessarily cluster-wide unique if it is not the shard key

In a sharded collection where `_id` is **not the shard key**, the default `_id` index enforces uniqueness **within each shard**, not automatically across the entire cluster.

If the application assigns `_id` from an uncoordinated sequence, two shards can store the same `_id` under certain conditions. Therefore:

- Generate sufficiently unique `_id` values in the application (e.g., `ObjectId`/UUID per contract).
- If the business requires hard cluster-wide uniqueness, select an appropriate key/index architecture.
- Never treat per-shard `_id` uniqueness as proof of a global business invariant.

### 16.4. Idempotency in multi-tenant systems

Suppose each tenant supplies its own `requestId`:

```javascript
{
  tenantId: "T1",
  requestId: "REQ-123"
}
```

An appropriate unique scope may be `(tenantId, requestId)`. If `requestId` must be globally unique across all tenants, that is a different rule requiring a dedicated data design. Transactions do not magically create unique constraints on fields incompatible with the shard key.

---

## 17. `null`, missing values, and low-cardinality keys

A sharded collection may contain documents missing one or more shard key fields. MongoDB treats missing fields similarly to `null` **when partitioning chunk ranges**, while query routing follows its own rules.

Example compound key:

```javascript
{ tenantId: 1, orderId: 1 }
```

Documents:

```javascript
{ tenantId: "T1" }
{ tenantId: "T1", orderId: null }
```

can land in the same shard-key value region equivalent to `(T1, null)`.

### 17.1. Why is this dangerous?

If 40% of documents lack `tenantId`, a huge volume of data piles into ranges holding the `null` prefix, degrading distribution and complicating query targeting.

In domains requiring tenant/order fields, **enforce validation**:

```javascript
db.runCommand({
  collMod: "orders",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["tenantId", "orderId"],
      properties: {
        tenantId: { bsonType: "string", minLength: 1 },
        orderId: { bsonType: "string", minLength: 1 }
      }
    }
  },
  validationAction: "error"
});
```

This is a **validation example** for an existing collection; do not run it in production without merging existing schema rules. Validators must account for all rules in the system.

### 17.2. Do not use hashing to “fix” every low-cardinality field

```javascript
{ status: "hashed" }
```

with 3 status values still has only a handful of **distinct input values**, and therefore few distinct hash values. Hashing does not turn documents sharing the same status into distinct hash values; single-value frequency stays high.

For better distribution, choose a key with sufficient cardinality, potentially a compound key with another discriminating field.

---

## 18. Zone sharding and compound keys

**Zones** allow binding shards or shard groups to shard key ranges for goals such as locality, residency, and load distribution.

Suppose tenants grouped by `region` must live in designated regions:

```javascript
{ region: 1, customerId: "hashed" }
```

`region` is a **non-hashed** prefix, allowing zone ranges to be defined by region while hashed `customerId` distributes within each region.

### 18.1. Zone ranges are half-open intervals

Conceptual example on a single key:

```text
Zone EU: ["EU", "US")
Zone US: ["US", "ZZ")
```

Specific bounds must be chosen according to BSON/field comparison order rather than treating string labels as a geographic map by intuition.

With compound keys, zone bounds must include the full prefix structure required by MongoDB—for example, using `MinKey`/`MaxKey` in trailing fields to cover an entire prefix domain.

### 18.2. Hashed fields do not preserve locality by original values

With a single key:

```javascript
{ region: "hashed" }
```

zone ranges on the shard key apply to **hashed values of `region`**, not the domain order `"EU" < "US"`. It is awkward to use directly to pin real regional domains to data centers intuitively.

Therefore, if **regional data residency** is mandatory, a structure with a non-hashed prefix is usually worth considering.

### 18.3. Pre-splitting compound hashed zones has special rules

When sharding an empty collection with a **non-hashed prefix before a hashed field** and requiring **initial distribution across zones**, MongoDB requires defining zone ranges and using options like `presplitHashedZones` appropriately.

Do not assume MongoDB automatically splits every tenant/region evenly at collection creation time. Documentation specifies distinct behavior between:

```javascript
{ hashedField: "hashed", region: 1 }    // hashed prefix
{ region: 1, hashedField: "hashed" }    // non-hashed prefix
```

In production, design zone ranges, verify the balancer, and test placement before taking live traffic.

---

## 19. Initial chunks and the balancer: not every initialization strategy behaves the same

MongoDB partitions collections into chunks/ranges that the balancer can move between shards.

### 19.1. Sharding a populated collection

For an already populated collection, `sh.shardCollection` may initialize broad ranges and let the balancer distribute them under applicable conditions. Never conclude that immediately after sharding, data is already balanced across every shard.

### 19.2. Empty collection with a ranged key

Without configured zones, MongoDB may create **one initial chunk covering the entire key space**. As data grows, splitting/balancing gradually distributes chunks.

### 19.3. Empty collection with a hashed key

Hashed sharding can pre-create initial empty chunks and distribute them across multiple shards, especially with a hashed field in the prefix. Details such as **default chunk count** depend on the compound hashed key structure and server version (for example, compound hashed-prefix behavior changed in MongoDB 8.0).

Therefore, never hardcode assumptions like “every shard always gets two chunks” in operational runbooks. Inspect actual post-command distribution and monitor the balancer.

### 19.4. The balancer cannot fix a poor key

If all documents share the same shard key value, a chunk cannot split down the middle of **one single key value**. Hashing that value still yields one hash. An indivisible/jumbo chunk/range may form, and adding shards will not resolve it.

You must increase the shard key’s discriminating power, change the key, or redesign the data model.

---

## 20. Configuration examples in `mongosh`

**Safety note:** all `sh.shardCollection` commands below are **independent** candidate examples—do not run them sequentially on the same `commerce.orders`. A collection has only one active shard key pattern at a time. Run only on a test sharded cluster through `mongos` with proper privileges.

### 20.1. Option A — single ranged key

```javascript
// On mongos, a test collection with existing data needs the index first.
db.getSiblingDB("commerce").orders.createIndex({
  createdAt: 1
});

sh.shardCollection(
  "commerce.orders",
  { createdAt: 1 }
);
```

Suitable for testing time-range queries, but measure write hotspot risk carefully.

### 20.2. Option B — single hashed key

```javascript
db.getSiblingDB("commerce").orders.createIndex({
  orderId: "hashed"
});

sh.shardCollection(
  "commerce.orders",
  { orderId: "hashed" }
);
```

Good for equality lookups and varied ID inserts, though `orderId` range queries or tenant-only queries may target broadly.

### 20.3. Option C — ranged compound

```javascript
db.getSiblingDB("commerce").orders.createIndex({
  tenantId: 1,
  orderId: 1
});

sh.shardCollection(
  "commerce.orders",
  { tenantId: 1, orderId: 1 }
);
```

Test with per-tenant queries and `orderId` ranges; watch for hotspots when `orderId` increments sequentially within large tenants.

### 20.4. Option D — compound hashed

```javascript
db.getSiblingDB("commerce").orders.createIndex({
  tenantId: 1,
  orderId: "hashed"
});

sh.shardCollection(
  "commerce.orders",
  { tenantId: 1, orderId: "hashed" }
);
```

Test with `tenant + orderId` lookups and multi-tenant write workloads; monitor chunk distribution for large tenants.

### 20.5. Option E — hashed prefix

```javascript
db.getSiblingDB("commerce").orders.createIndex({
  orderId: "hashed",
  createdAt: 1
});

sh.shardCollection(
  "commerce.orders",
  { orderId: "hashed", createdAt: 1 }
);
```

Test with `orderId` queries and time-window operations **within the same `orderId`**; do not expect `createdAt`-only queries to target narrowly.

### 20.6. `sh.enableSharding` is not required in all versions

Since MongoDB 6.0, sharding a collection no longer requires calling `sh.enableSharding()` beforehand to enable sharding on the database in the legacy way. Still, **do not ignore your exact version’s specifics**; older cluster docs or automation may differ.

---

## 21. Checking topology and distribution after sharding

On `mongos`:

```javascript
db.hello();
sh.status();
```

These tools inspect cluster metadata; output fields depend on MongoDB version.

A helpful method:

```javascript
db.getSiblingDB("commerce").orders.getShardDistribution();
```

It prints data/chunk distribution statistics across shards. Note that figures may be estimates, and unclean shutdowns can occasionally leave temporarily skewed stats.

### 21.1. Reading query plans to check shard targeting

```javascript
db.getSiblingDB("commerce").orders.find({
  tenantId: "T1",
  orderId: "O100"
}).explain("executionStats");
```

Compare with:

```javascript
db.getSiblingDB("commerce").orders.find({
  status: "PAID"
}).explain("executionStats");
```

On a sharded cluster, `explain` can display per-shard/stage info and how many shards participated. Exact formatting changes across versions and execution engines.

What to observe:

- How many shards did the query target?
- How many keys/documents did each shard scan?
- Is there an index matching the filter/sort?
- How many documents and bytes were returned?
- Do timings differ widely between router and shards?
- Is a query returning few documents broadcasting across the whole cluster?

**One fast `explain` does not prove API p99 is fast**; observe real workloads under concurrency.

### 21.2. Do not look only at chunk sizes

A cluster balanced in bytes yet imbalanced in read/write operations can still run hot on one shard. Combine shard-level metrics for CPU, I/O, ops/sec, query latency, cursor/connection pools, and network.

---

## 22. Using `analyzeShardKey` to evaluate candidates

Starting in MongoDB **7.0**, shard keys can be analyzed based on **key characteristics and sampled query workloads**.

On a supported collection:

```javascript
db.getSiblingDB("commerce").orders.analyzeShardKey({
  tenantId: 1,
  orderId: "hashed"
});
```

Output may include:

- **`keyCharacteristics`**: cardinality, frequency, monotonicity.
- **`readWriteDistribution`**: estimated read/write distribution from sampled queries.

To obtain useful read/write metrics, configure query sampling via `configureQueryAnalyzer` per documentation and privileges. Never treat “no samples available” output as proof that the workload will be balanced.

### 22.1. A candidate evaluation process

1. Extract common query shapes from tracing/profiler/logs with sensitive data masked.
2. List ranged, hashed, and compound candidates.
3. Analyze cardinality/frequency and monotonicity.
4. Estimate targeted vs. scatter-gather behavior for critical queries.
5. Benchmark production-like data skew and concurrency on a staging cluster.
6. Inspect writes/sec/CPU, chunk counts, and per-shard distribution.
7. Compare p95/p99 latency, not just aggregate throughput.
8. Evaluate migration/resharding cost and unique/zone constraints.

Never pick a key solely by finding the most random-looking field. If the app always queries by `tenantId`, pure hashed `orderId` may make tenant-only queries far more expensive even if bytes look balanced.

---

## 23. Changing the shard key: refine vs. reshard

An initially chosen shard key is not permanent forever, yet changing it carries **significant operational cost**.

### 23.1. `refineCollectionShardKey`: appending a suffix

Example current key:

```javascript
{ tenantId: 1 }
```

Want to increase distinct key combinations:

```javascript
{ tenantId: 1, orderId: 1 }
```

You can use the refine mechanism:

```javascript
db.adminCommand({
  refineCollectionShardKey: "commerce.orders",
  key: { tenantId: 1, orderId: 1 }
});
```

This example is **illustrative**; before running, a supporting index for the new key must exist and all version/cluster refine preconditions must be met.

Refining **only appends trailing fields**, without altering the order/type of the existing prefix. Never use refine to change:

```text
{ tenantId: 1 }
    -->
{ tenantId: "hashed" }
```

because that alters the type of the first field rather than appending a suffix.

### 23.2. `reshardCollection`: choosing a different key

Starting in MongoDB **5.0**, resharding is supported to switch a collection to a different shard key, for example:

```javascript
// Replace ranged key with compound hashed (illustrative):
sh.reshardCollection(
  "commerce.orders",
  { tenantId: 1, orderId: "hashed" }
);
```

Resharding imposes prerequisites on version, resources, disk, replication, indexes, migrations, and collection scope. Never run it casually mid-peak.

### 23.3. Choosing refine or reshard?

- **Refine**: when adding a suffix to raise cardinality/granularity while keeping the existing prefix and key style.
- **Reshard**: when the distribution strategy genuinely must change—e.g., ranged to hashed, reordering fields, or swapping the primary field.
- Refine **does not guarantee** skewed data immediately redistributes optimally.
- Reshard addresses severe distribution skew more powerfully, but demands more resources and stricter planning.

Per MongoDB guidance, evaluate resharding when fixing severe data skew; refine helps when you simply need finer key granularity and cannot or need not swap the whole key.

### 23.4. Do not change a shard key with `createIndex`

Creating an index:

```javascript
db.orders.createIndex({ tenantId: 1, orderId: "hashed" });
```

does not change the shard key if the collection is currently sharded on `{ createdAt: 1 }`. Changing placement requires supported refine/reshard operations.

---

## 24. Java MongoDB Sync Driver: queries with shard keys

In Java, most CRUD on a sharded cluster looks identical to a regular collection. What matters is **connecting to valid `mongos` / sharded cluster endpoints** and supplying routing predicates whenever possible.

### 24.1. Creating a MongoClient

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

public final class ShardedClientExample {

    public static MongoClient createClient() {
        return MongoClients.create(
            "mongodb://router1.example.net:27017," +
            "router2.example.net:27017/" +
            "?retryWrites=true"
        );
    }

    public static MongoCollection<Document> orders(
            MongoClient client
    ) {
        return client.getDatabase("commerce")
            .getCollection("orders");
    }
}
```

Illustrative URI. Production must configure TLS, auth, secret management, proper replica/sharded topology, and appropriate timeouts. Never connect directly to a shard `mongod` hostname in place of `mongos`, especially when accessing across shards.

### 24.2. Targeted query using a compound hashed key

Suppose shard key:

```javascript
{ tenantId: 1, orderId: "hashed" }
```

Java:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import static com.mongodb.client.model.Filters.*;

public class OrderQueries {

    public static Document findOrder(
            MongoCollection<Document> orders,
            String tenantId,
            String orderId
    ) {
        return orders.find(
            and(
                eq("tenantId", tenantId),
                eq("orderId", orderId)
            )
        ).first();
    }
}
```

The application does not compute the hash; `mongos`/servers do. `tenantId` + `orderId` give the router the full shard key tuple.

### 24.3. Listing orders for a tenant

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import java.util.ArrayList;
import java.util.List;

public class TenantOrders {

    public static List<Document> latest(
            MongoCollection<Document> orders,
            String tenantId
    ) {
        return orders.find(
            Filters.eq("tenantId", tenantId)
        ).sort(
            Sorts.orderBy(
                Sorts.descending("createdAt"),
                Sorts.descending("_id")
            )
        ).limit(20).into(new ArrayList<>());
    }
}
```

If the tenant’s data resides across multiple shards, the query may need to merge results from those shards. For efficient filtering/sorting, shards need a matching index. In real APIs, paginate with cursors rather than deep `skip` offsets.

### 24.4. Updates and the full shard key

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

public class OrderUpdates {

    public static UpdateResult markPaid(
            MongoCollection<Document> orders,
            String tenantId,
            String orderId
    ) {
        return orders.updateOne(
            Filters.and(
                Filters.eq("tenantId", tenantId),
                Filters.eq("orderId", orderId),
                Filters.eq("status", "PENDING")
            ),
            Updates.set("status", "PAID")
        );
    }
}
```

This example uses equality on the full compound shard key, aiding routing and preventing invalid state transitions. To enforce complex invariants, also account for concurrency, unique indexes, retries, and idempotency.

Some updates/upserts have special rules when missing or modifying the shard key; do not blindly apply older-version rules to newer drivers. Always verify operation contracts against your running MongoDB version.

### 24.5. Do not hash fields manually in Java

Never do:

```java
int hash = orderId.hashCode();
```

and treat it as a MongoDB hashed shard key. Java’s `String.hashCode()` is **not** the hash function used by MongoDB hashed indexes.

Pass the original value; `mongos` computes the hash itself. To inspect hashed values while debugging, use MongoDB’s provided helpers such as `convertShardKeyToHashed()` in `mongosh`, rather than reimplementing hashes in application code.

---

## 25. Case study 1: multi-tenant SaaS

The system has:

- 50,000 tenants.
- 1% of tenants account for 60% of orders.
- Most requests include `tenantId`.
- Large tenants write many new orders per second.
- Reports primarily view orders for a single tenant.

Three options:

| Shard key | Strengths | Risks |
| --- | --- | --- |
| `{ tenantId: 1 }` | Simple tenant-local routing. | Large tenants become indivisible hot keys/chunks. |
| `{ tenantId: 1, createdAt: 1 }` | Favorable for time/range within a tenant. | Ascending timestamps inside large tenants can heat up tail ranges. |
| `{ tenantId: 1, orderId: "hashed" }` | Can split large tenants by hashed ID. | Time/`orderId` ranges lose ranged locality; a tenant may span shards. |

**Evaluation approach**: capture sampled read/write patterns, measure large tenants, and compare shards per query plus p99 for “latest orders.” If using a hashed suffix, add a secondary index `{tenantId:1, createdAt:-1}` for sorting and measure merge overhead.

### 25.1. One tenant can span multiple shards

For huge tenants, a compound hashed key allows splitting that tenant’s orders into chunks across multiple shards. That benefits write distribution while trading off cost on `"all orders for tenant"` queries.

Never promise “having a `tenantId` prefix means every read touches only one shard.”

### 25.2. One ultra-hot tenant can still exceed single-document capacity

If every request updates **the exact same counter document** for a tenant, changing the orders shard key to spread orders **will not parallelize updates to that single document**. Redesign with counter sharding, batching, or a different model if the true bottleneck is one hot document.

---

## 26. Case study 2: chronological event logs

Data:

```javascript
{
  _id: ObjectId(),
  applicationId: "APP-A",
  ts: ISODate("2026-11-14T09:15:00Z"),
  eventId: "EVT-1001",
  level: "INFO"
}
```

Write stream: hundreds of thousands of events per minute, with continuously increasing `ts`.

### 26.1. Key `{ ts: 1 }`

Advantage: time-window queries can target relevant ranges.

Risk: all new writes concentrate in the `MaxKey` range, risking a hot shard.

### 26.2. Key `{ eventId: "hashed" }`

Advantage: distributes varied event IDs.

Risk: queries asking for “all events in the last 5 minutes” lack the shard key and broadcast, consuming heavy I/O, CPU, and network.

### 26.3. Key `{ applicationId: 1, eventId: "hashed" }`

Advantage: scopes by application prefix while hashing events within each app.

Risk: time-range queries within each application may still run across multiple shards and require a separate index `{ applicationId: 1, ts: -1 }`.

### 26.4. When to consider another model?

For logs/time-series, **time series collections**, retention/TTL, pre-aggregation, or dedicated ingestion pipelines may fit better. Time-series sharding has **version-specific shard key rules**; do not apply regular-collection conclusions verbatim.

---

## 27. Time series collections: special notes

If the collection is a time-series collection:

```javascript
{
  ts: ISODate("2026-11-14T09:15:00Z"),
  meta: {
    sensorId: "S1",
    region: "VN"
  },
  temperature: 28.5
}
```

MongoDB enforces dedicated shard key constraints for `metaField` and `timeField`:

- `metaField` can be used as a ranged or hashed shard key under supported conditions.
- `timeField`, if used in the shard key, must sit in the appropriate position of the pattern and be ranged.
- **Starting in MongoDB 8.0, shard keys containing `timeField` on time series collections are deprecated.**
- A monotonically increasing time field alone is generally unsuitable as a shard key due to hotspots.

**Do not copy `sh.shardCollection("logs.events",{ts:1})` meant for an ordinary collection directly onto a time series collection while ignoring its special constraints.** Check version docs and design around metadata and query workloads.

---

## 28. Common misconceptions

| Misconception | Correct understanding |
| --- | --- |
| “Hashed is always faster than ranged.” | Hashed improves spread in many cases, yet range queries may scatter-gather. |
| “Ranged always targets only one shard.” | Range predicates can intersect multiple chunks across multiple shards. |
| “`createdAt` as a ranged key is optimal for every logs app.” | Continuously ascending timestamps risk a hot `MaxKey` range. |
| “Hashing spreads evenly even with three key values.” | Low cardinality still limits distinct hash values. |
| “One hot tenant is solved just by `{tenantId:1}`.” | Identical `tenantId` values sit in an unsplittable key range. |
| “Field order in a compound key doesn’t matter.” | `{tenantId:1,orderId:1}` and `{orderId:1,tenantId:1}` have different routing/locality. |
| “Prefix equality always targets one shard.” | A prefix can span many chunks and shards. |
| “Must hash `orderId` manually in Java.” | MongoDB computes it; Java `hashCode()` is incompatible. |
| “Hashed indexes can be `unique:true`.” | MongoDB does not support unique constraints on hashed indexes. |
| “Default `_id` index enforces global uniqueness when `_id` is not the shard key.” | `_id` uniqueness may only be enforced per shard. |
| “The shard key index is enough for every sort query.” | Secondary indexes on each shard are usually still needed. |
| “Having a `status` index keeps `status` queries on one shard.” | Local indexes do not replace shard-key routing; queries still broadcast. |
| “Use an array field as a hashed shard key.” | Hashed indexes do not support multikey/arrays. |
| “Hashing Double 2.2 differs from 2.3.” | Floating-point values truncate to integer before hashing, causing collisions. |
| “Compound hashed hashes the entire tuple.” | Only one field is marked `"hashed"`. |
| “`{region:"hashed"}` can zone alphabetically by region.” | Zones on hashed fields use hash ranges, not original values. |
| “Right after sharding, data is balanced immediately.” | Initial chunks/balancer follow a process depending on version/topology. |
| “Even data size means even traffic.” | Read/write hotspots can persist despite balanced bytes. |
| “Empty collections require all indexes beforehand.” | MongoDB can create the supporting shard key index when needed. |
| “Populated collections don’t need a shard key index beforehand.” | Populated collections require a supporting index prior to sharding. |
| “`createIndex` changes the shard key.” | It only builds an index; separate shard/refine/reshard is required. |
| “Refine can convert ranged to hashed.” | Refine only appends a suffix; it cannot alter prefix/types. |
| “Resharding is always lightweight and free.” | It is a resource-intensive placement operation needing planning. |
| “One `explain` is enough to pick a key.” | Need workload sampling, write spread, and p95/p99 under load. |

---

## 29. Applied exercises

### Exercise 1 — Monotonically increasing key

An `events` collection has 100 million records, adding several million per hour. Every new insert has an ascending `ts`.

**Question:** What is the risk of `{ ts: 1 }`?

**Hint:** New inserts concentrate in the highest `MaxKey` range, creating a write hotspot even though time-window queries target well.

### Exercise 2 — Equality vs. range with hashed sharding

Shard key:

```javascript
{ userId: "hashed" }
```

Compare:

```javascript
db.users.findOne({ userId: "U100" });

db.users.find({
  userId: { $gte: "U100", $lt: "U900" }
});
```

**Hint:** Equality can target a single hash range, whereas a range on original `userId` does not correspond to a contiguous hash range and usually hits multiple shards.

### Exercise 3 — Low cardinality

A collection has 800 million documents and `status` has only 4 values. Should you shard on `{ status: "hashed" }` to spread data more evenly?

**Answer:** Unsuitable. Hashing still yields hash values corresponding to only four distinct statuses; frequency stays high and chunks cannot be split usefully. You need a higher-cardinality field.

### Exercise 4 — Compound key queries

Key:

```javascript
{ tenantId: 1, orderId: 1 }
```

**Question:** Which query targets more narrowly?

```javascript
// A
{ tenantId: "T1", orderId: "O10" }

// B
{ tenantId: "T1" }

// C
{ orderId: "O10" }
```

**Answer:** A supplies the full key and targets most narrowly in theory; B supplies the prefix and may touch multiple shards; C lacks the prefix and typically targets broadly.

### Exercise 5 — Reversed compound key order

Compare:

```javascript
{ tenantId: 1, orderId: 1 }
{ orderId: 1, tenantId: 1 }
```

**Question:** If 80% of APIs filter by tenant, which key gives better locality/query targeting?

**Hint:** Put `tenantId` as the prefix, while still inspecting large-tenant load and suffix monotonicity.

### Exercise 6 — Compound hashed

Key:

```javascript
{ region: 1, customerId: "hashed" }
```

**Question:** Does MongoDB hash `region + customerId` together into one hash?

**Answer:** No. `region` keeps its original/ranged values; only `customerId` is hashed.

### Exercise 7 — Global uniqueness

A sharded collection uses `{ orderId: "hashed" }`; the dev team wants `sh.shardCollection(..., true)` to guarantee unique `orderId`.

**Answer:** Not allowed; hashed shard keys do not directly support unique constraints. You must design another identity enforcement scheme conforming to sharded collection rules.

### Exercise 8 — Relying on `_id` for global uniqueness

A collection is sharded on `{ tenantId: 1 }`, and `_id` is not part of the shard key. Does MongoDB guarantee `_id` is globally unique across the cluster?

**Answer:** No; by default the `_id` index may only enforce uniqueness within each shard. Use appropriate ID generation and constraint mechanisms.

### Exercise 9 — Hashing Doubles

If a numeric field stores Doubles `2.2`, `2.3`, `2.9`, will a hashed index generate distinct hashes?

**Hint:** MongoDB truncates floating-point values to 64-bit integers before hashing; all three can yield the same hash. Do not pick such a field expecting high hashed differentiation.

### Exercise 10 — Refine or reshard?

Current key:

```javascript
{ tenantId: 1 }
```

Proposal A:

```javascript
{ tenantId: 1, orderId: 1 }
```

Proposal B:

```javascript
{ orderId: "hashed" }
```

**Hint:** A can use **refine** if prerequisites are met; B requires **reshard** because it replaces the key entirely.

### Exercise 11 — Zone placement

An enterprise must keep data in separate regions while distributing customers inside each region.

**Hint:** Consider a non-hashed `region` prefix plus a hashed `customer` suffix with valid zone configuration; test initial splitting/balancer behavior rather than just defining the key pattern.

### Exercise 12 — Secondary index

Shard key `{tenantId:1,orderId:"hashed"}`; a hot query lists recent orders by tenant and `createdAt`.

**Hint:** Add an appropriate secondary index such as `{tenantId:1,createdAt:-1}` on the collection and measure merge-sort cost when a tenant spans multiple shards.

### Exercise 13 — Indivisible hot tenant

One tenant accounts for 80% of traffic, and every request updates the exact same inventory summary document.

**Hint:** Hashing `orderId` on the `orders` collection does not parallelize updates to **one single document**. Redesign the counter/workload instead of merely changing the `orders` shard key.

### Exercise 14 — Initial distribution

A brand-new empty ranged-sharded collection is created, and the team expects 100 balanced chunks across 10 shards immediately.

**Hint:** Never assume that. Initial distribution depends on key type, zones, version, and balancer; inspect `sh.status()` and actual distribution.

### Exercise 15 — Pre-production testing

You have two candidates:

```javascript
A: { tenantId: 1, createdAt: 1 }
B: { tenantId: 1, orderId: "hashed" }
```

Propose a comparative test.

**Hint:** Generate a representative workload including large tenants; measure inserts/sec per shard, p95/p99 for full-key lookups and latest orders, shards per query, chunk/data skew, CPU/I/O, and migration times.

---

## 30. Process for choosing a shard key in a real system

### Step 1 — Identify invariants that must hold

Document clearly:

- Which business keys must be unique, and at what scope?
- Are there data residency/zone requirements?
- Are there time-series collections with special key limits?
- Are there giant tenants or hot documents?
- Which queries must meet strict p99 targets?

### Step 2 — List top query shapes

Example:

| Query shape | Share | Requirement |
| --- | ---: | --- |
| `tenantId + orderId` | 40% | Fast single lookup. |
| `tenantId + createdAt range` | 30% | Recent filtering/sorting. |
| Insert new order | 20% | Distributed writes. |
| Cluster-wide reports | 10% | Can tolerate cross-shard aggregation. |

Hypothetical figures for illustration. In practice, gather from tracing/sampling and weigh cost per query rather than request count alone.

### Step 3 — Build the candidate list

```javascript
{ tenantId: 1, orderId: 1 }
{ orderId: "hashed" }
{ tenantId: 1, orderId: "hashed" }
{ tenantId: 1, createdAt: 1 }
```

Never take a candidate into production before checking version, index, uniqueness, and zone constraints.

### Step 4 — Estimate distribution

For each key, analyze:

- Cardinality.
- Frequency of top values.
- Monotonicity of ranged components.
- Hot tenants.
- Size/chunk histogram.
- Projected query targeting by prefix and range.

### Step 5 — Measure on production-like workloads

Run on staging with representative shard count and data skew. Monitor:

- Insert/update/read throughput.
- Shards touched per query.
- p50/p95/p99 latency.
- CPU/disk/network per shard.
- Speed and cost of chunk migrations.
- Performance of secondary indexes and sorts.
- Impact on transactions/uniqueness if applicable.

### Step 6 — Prepare deployment

1. Verify cluster/topology/routers.
2. Verify supporting shard key index.
3. Audit duplicates, missing keys, nulls, and multikey fields.
4. Check collation and unique constraints.
5. Configure zone placement if needed.
6. Evaluate initial chunk distribution/balancer.
7. Prepare backups, rollback/reshard plan, and monitoring.
8. Execute migration under change management.
9. Verify query routing post-deployment.

### Step 7 — Monitor after launch

Even an initially sound shard key can degrade when:

- A new tenant captures most traffic.
- APIs shift from equality lookups to heavy range queries.
- Data grows and nulls proliferate.
- New indexes change query shapes.
- Shard counts or zone policies change.
- Hot reads shift to a specific data subset.

Periodically review `analyzeShardKey`, `getShardDistribution()`, query profiler/tracing, and per-shard metrics. When a key no longer fits, plan a controlled refine or reshard.

---

## 31. Official MongoDB documentation

- [Ranged Sharding](https://www.mongodb.com/docs/manual/core/ranged-sharding/): partitioning by shard key intervals.
- [Hashed Sharding](https://www.mongodb.com/docs/manual/core/hashed-sharding/): hashed indexes and compound hashed shard keys.
- [Choose a Shard Key](https://www.mongodb.com/docs/manual/core/sharding-choose-a-shard-key/): cardinality, frequency, monotonicity, and routing.
- [Shard Keys](https://www.mongodb.com/docs/manual/core/sharding-shard-key/): role, updates, and shard key limitations.
- [Shard Key Indexes](https://www.mongodb.com/docs/manual/core/sharding-shard-key-indexes/): supporting indexes, unique constraints, and version-dependent exceptions.
- [Hashed Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-hashed/): floating point, arrays, uniqueness, and covered query limitations.
- [Data Partitioning with Chunks](https://www.mongodb.com/docs/manual/core/sharding-data-partitioning/): chunk boundaries, initial distribution, and migration.
- [Zones](https://www.mongodb.com/docs/manual/core/zone-sharding/): zone ranges and placement.
- [`sh.shardCollection()`](https://www.mongodb.com/docs/manual/reference/method/sh.shardCollection/): collection sharding syntax, unique, collation, and options.
- [`db.collection.analyzeShardKey()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.analyzeShardKey/): evaluating shard keys on sampled workloads.
- [`db.collection.getShardDistribution()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.getShardDistribution/): viewing data distribution across shards.
- [Change a Shard Key](https://www.mongodb.com/docs/manual/core/sharding-change-a-shard-key/): refine and reshard.
- [Refine a Shard Key](https://www.mongodb.com/docs/manual/core/sharding-refine-a-shard-key/): appending a suffix to a shard key.
- [Reshard a Collection](https://www.mongodb.com/docs/manual/core/sharding-reshard-a-collection/): changing shard keys or redistributing data in supported versions.
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/): connecting and CRUD via the driver.

Some details regarding initial chunks, the balancer, time-series collections, index restrictions, and resharding vary across releases. Before deploying, cross-check documentation for your exact **server version, FCV, `mongosh`, and Java driver**.

---

## 32. Conclusion

**Ranged sharding** partitions along contiguous intervals of the original shard key: advantageous for range queries and locality, yet prone to hot ranges when fields increase/decrease monotonically.

**Hashed sharding** uses a field’s hash to distribute distinct values more widely: generally helpful for sequential inserts and equality lookups, yet degrades targeted routing for range queries on original values; hashed indexes also restrict uniqueness, multikeys, and floating-point precision.

**Compound shard keys** combine fields to boost cardinality and balance routing with distribution. Prefix order is critical. In **compound hashed shard keys**, only one field is hashed: `{tenantId:1,orderId:"hashed"}` and `{orderId:"hashed",tenantId:1}` do not deliver the same locality or targeting behavior.

To choose well, measure **cardinality + frequency + monotonicity + query shapes + uniqueness + zone requirements** under representative load. Secondary indexes solve access patterns **within each shard**, while the shard key governs **data placement and `mongos` routing**. Never conflate the two roles.

**A good shard key does not merely slice data into pieces—it helps most requests locate the right piece with minimal distributed work.**
