# Choosing a Shard Key by Cardinality, Frequency, and Monotonicity

When a MongoDB collection grows too large or receives too many read/write operations for a single replica set to serve efficiently, **sharding** allows data to be distributed across multiple **shards**. However, adding shards does not automatically guarantee balanced load, fast queries, or easy scalability. The outcome depends heavily on the chosen **shard key**.

A shard key is one or more fields that MongoDB uses to determine **which shard-key range a document belongs to and which shard operations are routed to**. In a sharded cluster, `mongos` and partitioning metadata coordinate to route operations; data is organized into **chunks/ranges** that can be allocated or moved across shards depending on balancing policies and splittability.

A poor shard key can produce seemingly contradictory failures:

- A collection has tens of millions of documents, yet **almost all inserts funnel into a single shard**.
- A huge number of customers exist, yet one **extremely hot tenant** still bottlenecks a single shard.
- Hashing spreads inserts more evenly, yet a **time-range** report ends up reading from many shards.
- Adding more shards fails to relieve a **single shard key value that appears far too often**.
- A query that is fast when filtering on the shard key degrades into **scatter-gather** when the API forgets to pass the shard key.
- Records are balanced by **storage size** yet heavily skewed in **requests per second**, leaving latency uneven.

Choosing a shard key is therefore not “picking the field with the most values,” but solving a simultaneous problem across:

1. **Cardinality:** how many distinct shard key values exist, and do they create enough space to split data?
2. **Frequency:** how often does each value appear, how much traffic does it bear, and is there a **hot key**?
3. **Monotonicity:** are new shard key values generated in a continuously increasing/decreasing sequence or well-distributed, and how does that affect new writes?
4. **Query patterns:** do APIs typically look up an exact key, filter by a compound key prefix, or scan a range?
5. **Operational constraints:** uniqueness, zones, data size, metadata, balancing, resharding, and recoverability.

This lesson focuses on the first three criteria, then connects them to selecting **ranged, hashed, and compound shard keys** for a real-world system.

## 1. How does the shard key participate in a query’s path?

Imagine a sharded cluster:

```text
                        Application
                            |
                         mongos
                 (router + shard metadata)
                            |
                  +---------+---------+
                  |         |         |
                Shard A   Shard B   Shard C
               (replica) (replica) (replica)
                  |         |         |
              chunk(s)  chunk(s)  chunk(s)
```

If a collection is sharded on:

```javascript
{ tenantId: 1, orderId: 1 }
```

then the shard key value is the pair:

```javascript
{
  tenantId: "TENANT-A",
  orderId: "ORD-000001"
}
```

To execute an operation, `mongos` must determine the shard key value or relevant key range. With sufficient predicates in the filter, the router can **target one shard or a smaller subset of shards**. Without the necessary information, the query may be sent to many shards (**scatter-gather**).

Illustrative examples:

```javascript
// Equality on both shard key fields.
db.orders.findOne({
  tenantId: "TENANT-A",
  orderId: "ORD-000001"
});

// Only tenant is known, orderId is not.
db.orders.find({
  tenantId: "TENANT-A"
});

// No shard key components included.
db.orders.find({
  status: "PAID"
});
```

With a compound shard key, whether a query targets well also depends on field order, sharding type, range metadata, and query shape. Do not assume the second query always targets a single shard or that the third is automatically efficient just because each shard has an index on `status`.

**These are two separate optimization layers:**

- **Shard targeting:** which shards must participate?
- **Local query execution:** on each shard, which index/query plan does MongoDB use to read data?

A good shard key with a poor local index can still be slow; a great local index forced across dozens of shards still incurs fan-out and result-merging overhead.

## 2. Three core criteria: cardinality, frequency, monotonicity

Before evaluating candidate fields, distinguish these concepts.

| Criterion | Question | Risk if chosen poorly |
|---|---|---|
| **Cardinality** | How many distinct key values exist? | Too few values leave insufficient units to split data |
| **Frequency** | How often does a value appear, and how much data/traffic does it carry? | An overly common value creates a hot key/hot shard |
| **Monotonicity** | Do new values trend strictly toward the start/end of the key space? | Range-sharded collections can funnel inserts into one boundary region |
| **Query locality** | Do APIs typically know the key or key range to read? | Scatter-gather, higher network/CPU cost |
| **Growth pattern** | Does data grow by tenant, time, or ID? | Even today, skewed six months later |
| **Stability** | Does the shard key change frequently? | Complex and expensive updates/data movement |

The first three criteria directly determine **splittability** and **load skew**. Yet they alone cannot finalize a shard key, because actual read/write patterns can change the conclusion.

### 2.1. Cardinality is the number of distinct values

Suppose a collection has one million orders:

```text
status:
  "NEW", "PAID", "CANCELLED"              -> 3 values

region:
  "NORTH", "CENTRAL", "SOUTH"             -> 3 values

tenantId:
  thousands of tenants                     -> many values

orderId:
  each order has its own ID                -> nearly one million values
```

Fields like `status` or `region` have very low cardinality and are generally unsuitable as standalone shard keys for large collections. Documents sharing the same key value cannot be partitioned into arbitrarily many **distinct** value regions merely by adding shards.

`orderId` has much higher cardinality; however, that does not guarantee a good key if IDs are issued sequentially or most queries lack `orderId`.

### 2.2. Frequency is concentration on individual values

Suppose `tenantId` has 10,000 distinct values, which sounds great. However:

```text
TENANT-BIG:     75% of data
9,999 tenants:  25% remaining data
```

If the shard key is **only `tenantId`**, every document of `TENANT-BIG` has the **exact same shard key value**. The system cannot split that single `tenantId` value across multiple distinct shard-key ranges using only that key value.

**High collection-wide cardinality paired with extreme frequency on one key** still causes imbalance.

### 2.3. Monotonicity is an increasing/decreasing trend

Suppose `orderNo` increments:

```text
100001, 100002, 100003, 100004, ...
```

It has high cardinality, with each value typically appearing once. Yet with **range-based sharding** on `orderNo`, new inserts head to the **leading or trailing edge of the key space**, concentrating on a boundary chunk over a period.

This can create an **insert hot shard** even if historical data eventually spreads across shards. High cardinality + low duplicate frequency **do not automatically solve monotonicity**.

## 3. Comparing candidate shard keys by example

The `orders` collection contains:

```javascript
{
  _id: ObjectId("65a12f010000000000000001"),
  tenantId: "TENANT-A",
  orderNo: NumberLong("12004567"),
  orderId: "ORD-12004567",
  customerId: "CUS-9081",
  status: "PAID",
  total: NumberDecimal("125000.00"),
  createdAt: ISODate("2026-03-01T08:30:00Z")
}
```

Candidates:

| Shard key | Cardinality | Frequency | Monotonicity | Key consideration |
|---|---|---|---|---|
| `{ status: 1 }` | Very low | A few overwhelmingly common values | Not necessarily increasing | Poor spread, hot values |
| `{ tenantId: 1 }` | Can be high | Can skew heavily by tenant | Usually non-monotonic | Good for tenant locality, but hot-tenant risk |
| `{ orderNo: 1 }` | High | Nearly one doc/value | **Continuously increasing** | Hot boundary range on inserts |
| `{ orderNo: "hashed" }` | High | Nearly one doc/value | Hash breaks ascending order | Better write distribution, poor range-query locality |
| `{ tenantId: 1, orderId: "hashed" }` | High via orderId | Splits many orders inside a tenant | Hashes `orderId` component | Can relieve hot tenants if partitioned properly, but tenant-wide reads require routing evaluation |
| `{ tenantId: 1, createdAt: 1 }` | High combined | Duplicate timestamps can be high | Increases over time within tenant | Good for per-tenant ranges, can run hot per tenant |

No row “always wins.” Each must be evaluated alongside the queries the application actually executes.

## 4. Cardinality: a deeper look at distinct values

Cardinality is often estimated as:

\[
D = |\{k(d): d \in \text{collection}\}|
\]

where `k(d)` is the shard key value of document `d`, and `D` is the number of distinct values.

If total document count is `N`, the simple ratio:

\[
\text{distinctRatio} = \frac{D}{N}
\]

helps visualize distinct value count relative to dataset size. However, this ratio **is not enough** to finalize a shard key.

### 4.1. Example of two candidates with identical cardinality

Suppose there are 10 million documents, and two fields both have `D = 100,000`.

- **Field A:** each value appears in roughly 100 documents.
- **Field B:** one value appears in 7 million documents, while the remaining 99,999 values share 3 million.

Both have the same cardinality, yet their ability to distribute by value differs vastly. Field B is very risky if its most frequent value creates a hot key.

Therefore, after counting distinct values, you must measure the **frequency distribution**.

### 4.2. Extremely low cardinality cannot be rescued by adding shards

If a collection uses shard key `status` with only 4 values:

```text
NEW
PAID
CANCELLED
REFUNDED
```

adding a 20th shard does not invent 16 new status values. You cannot expect every shard to hold equal document counts if one status accounts for 90% of the data.

Sharding does not alter business value domains. To spread further, choose **another shard key or a compound key** with sufficient distinct values, such as incorporating an order identifier.

### 4.3. Null and missing values can lower effective cardinality

If many documents lack the candidate field:

```javascript
{ _id: 1, tenantId: null }
{ _id: 2 }
{ _id: 3, tenantId: null }
```

these records do not produce useful distinct shard key values. Missing/null shard key fields follow MongoDB’s representation/routing rules, but from a design perspective, a large volume of keyless records creates **concentration of data and queries**.

Standardize the schema, audit null/missing rates, and ensure the shard key field exists with meaningful values before deciding.

## 5. Frequency: what happens when one key value runs hot?

Let `f(v)` be the number of documents with shard key value `v`. Then:

\[
f_{\max} = \max_v f(v)
\]

and:

\[
p_{\max} = \frac{f_{\max}}{N}
\]

is the fraction of documents held by the most frequent value.

If `p_max = 0.75`, **75% of documents share the exact same shard key value**. In range-based sharding with a standalone shard key like `tenantId`, that is a red flag.

### 5.1. Data volume per key and traffic per key are two different statistics

Frequency has at least two operational meanings:

1. **Data frequency:** number of records/bytes tied to a value.
2. **Request frequency:** read/write operations per second tied to that value.

Example:

```text
TENANT-A has 50% of documents but only 5% of requests.
TENANT-B has 2% of documents but 70% of requests.
```

By storage size, tenant A is large. By traffic load, tenant B is the hot key.

A shard key should be evaluated against both **data size distribution** and **read/write traffic distribution**; counting documents alone cannot predict CPU, IOPS, or p99 latency.

### 5.2. A single key value can cap scalability

Suppose a collection is sharded on `{ userId: 1 }` and one celebrity account generates 10,000 events/second:

```javascript
{
  userId: "celebrity-user",
  eventId: "...",
  createdAt: ISODate("2026-03-01T08:00:00Z")
}
```

Every event from this user shares the same `userId` in the shard key. Adding more shards does not spread those events across multiple shard key values. The hot user can bottleneck a single shard.

A potential fix is a compound shard key adding a discriminating field, such as `eventId` or a bucket/hash suffix, though you must then assess the impact on **reading that user’s complete history**.

### 5.3. Salting comes with trade-offs

A manual design might add:

```javascript
{
  userId: "celebrity-user",
  bucketNo: 0,    // 0..15
  eventId: "EVT-123",
  ...
}
```

and shard on `{ userId: 1, bucketNo: 1 }` in an appropriate model.

If `bucketNo` has 16 values, a hot user can be divided into multiple shard-key values, **though there is no guarantee each value actually lands on a different shard** unless metadata, balancing, and topology support it.

Reading all events for that user now requires scanning across those buckets. If `bucketNo` is assigned randomly, per-user queries may fan out. Moreover, per-user/event uniqueness, pagination, and chronological ordering grow more complex.

Do not add salting solely because a frequency table looks skewed without quantifying **write gains vs. read costs**.

## 6. Monotonicity: why do ascending keys create hot shards?

Suppose you use range sharding on:

```javascript
{ orderNo: 1 }
```

and every new insert has an increasing `orderNo`:

```text
Sharding ranges:
[-∞, 100000)       -> Shard A
[100000, 200000)   -> Shard B
[200000, +∞)       -> Shard C

New inserts:
230001, 230002, 230003, ...
                          └──> Shard C
```

At this point, **all new inserts** land in the trailing chunk/range, so Shard C bears most write traffic. The balancer can migrate ranges/chunks later, yet moving historical data **does not stop new values from continuing to hit the boundary region**.

### 6.1. Fields prone to monotonic trends

- `createdAt` or event-generation timestamps;
- Auto-incrementing `orderNo`, `invoiceNo`, sequences;
- Incrementing version numbers;
- Time-generated `ObjectId`s generally exhibit an **ascending trend** due to their timestamp prefix, even though they are not a global clock and do not guarantee strict total ordering;
- String codes with a time prefix and lexicographically increasing suffix.

To optimize append-heavy workloads, inspect the actual BSON ordering of the field rather than judging just by names like `id` or `timestamp`.

### 6.2. Decreasing sequences have the symmetric problem

If a sequence generates decreasing negative numbers:

```text
-1, -2, -3, -4, ...
```

inserts concentrate at the **leading** range instead of the trailing range. The problem is not “increasing is bad,” but **new values continuously pouring into one edge of the range space**.

### 6.3. High cardinality and low frequency can still run hot

A unique `orderNo` has:

```text
D ≈ N
f_max = 1
```

Those two numbers look great. Yet if `orderNo` increments every second, range sharding can still create a hot insert range.

Therefore, **cardinality, frequency, and monotonicity must be evaluated together**.

### 6.4. Hot shard vs. hot index page

Even in an unsharded replica set, an index on an ascending key can put write pressure on specific regions of the B-tree. In sharding, the problem compounds into **routing every insert to a single shard**.

A hashed shard key helps distribute operations across shards, though it does not automatically solve every kind of contention inside a shard—especially if the application repeatedly hammers updates on a single document.

## 7. Range-based sharding: pros and cons

Range-based sharding places shard key values into contiguous intervals in BSON order.

Conceptual declaration example:

```javascript
sh.shardCollection(
  "shop.orders",
  { orderNo: 1 }
);
```

This command only applies in a **sharded cluster** configured via `mongos`, with matching indexes, privileges, and version prerequisites. Do not run sharding commands on production without a partitioning design and operational plan.

### 7.1. Benefit: range locality

Query:

```javascript
db.orders.find({
  orderNo: {
    $gte: NumberLong("12000000"),
    $lt: NumberLong("12100000")
  }
});
```

can target the shards holding the relevant shard-key ranges instead of scattering across the whole cluster by default. This helps when the system frequently:

- Scans data across numeric ranges;
- Runs time-window reports;
- Processes key partitions;
- Must map a data range to a zone/location by policy;
- Runs ordered batch jobs.

### 7.2. Drawback: write concentration on monotonic inserts

If `orderNo` increases continuously, write-heavy applications can overload the trailing range.

Trade-off:

```text
Range shard key:
  + targets range queries well
  + adjacent keys have locality
  - monotonically increasing inserts can run hot
  - high-frequency keys can form hard-to-split ranges
```

Do not pick `createdAt: 1` for a massive event stream **just because dashboards filter by date** without measuring insert distribution and the write capacity of the shard receiving fresh data.

## 8. Hashed sharding: breaking monotonicity to spread keys

A hashed shard key stores/routes using a **hash computed by MongoDB from the key value**. When IDs increase monotonically yet remain distinct, hash values tend to spread across a domain unrelated to the original order.

Example:

```javascript
sh.shardCollection(
  "shop.orders",
  { orderNo: "hashed" }
);
```

Illustration:

```text
orderNo      hash(orderNo)      Shard/key range
-------      -------------      ---------------
100001       H71                 A
100002       H08                 C
100003       H92                 B
100004       H34                 A
100005       H59                 C
...
```

Labels like H71/H08 are illustrative only, not actual hashes. The core idea: two nearby `orderNo` values are no longer forced to sit next to each other in the hash space.

### 8.1. When does a hashed shard key fit?

Especially useful when:

- The field has **many distinct values**;
- No single value generates overwhelming load by itself;
- New values increase or decrease monotonically;
- The workload primarily performs **equality** lookups on that field;
- Strong optimization for range scans on the shard key field itself is not required.

Example:

```javascript
db.orders.findOne({
  orderNo: NumberLong("12004567")
});
```

With a hashed shard key on `orderNo`, the router computes the hash of the exact value to target the corresponding shard per metadata.

### 8.2. Hashed sharding does not preserve original range locality

Query:

```javascript
db.orders.find({
  orderNo: {
    $gte: NumberLong("12000000"),
    $lt: NumberLong("12100000")
  }
});
```

does not correspond to a contiguous segment of hashes. MongoDB cannot use hash order to prune original `orderNo` intervals the way range sharding does.

Consequently, range queries may require **scatter-gather across multiple shards**. Depending on other filters and topology, the planner may apply optimizations, but never assume hashed sharding preserves range pruning on `orderNo`.

### 8.3. Hashing does not solve a single hot key

If one billion documents contain:

```javascript
{ tenantId: "TENANT-HOT" }
```

then:

```javascript
{ tenantId: "hashed" }
```

still hashes `"TENANT-HOT"` to **one single hash value**. Hashing spreads **many distinct key values**; it does not split one repeated value into multiple values.

Therefore:

> **A hashed key excels at breaking monotonicity across many distinct keys; it cannot rescue a single key with extreme frequency without an additional discriminating dimension.**

### 8.4. Hashing does not work for every field type

Limitations to note:

- A hashed index is not a B-tree index capable of range scans on original values;
- Hashed indexes do not enforce uniqueness like unique B-tree indexes;
- Array fields cannot be used as hashed keys due to multikey hashed index restrictions;
- Numeric hashing converts numbers before hashing, so avoid assuming every distinct decimal representation yields a distinct hash;
- A field with few distinct values remains low-cardinality after hashing.

Hashed sharding is a distribution mechanism, **not cryptographic security** or a guarantee of absolute load balance.

## 9. Compound shard keys: combining locality and dispersion

A shard key can combine multiple components.

Example:

```javascript
{ tenantId: 1, orderNo: 1 }
```

or a compound hashed shard key in supported versions:

```javascript
{ tenantId: 1, orderId: "hashed" }
```

### 9.1. Why can adding a field reduce key frequency?

Suppose 70% of documents belong to tenant A:

```javascript
{ tenantId: "A" }
```

If the shard key is only `tenantId`, value A runs very hot.

Adding `orderId`:

```javascript
{ tenantId: "A", orderId: "ORD-1001" }
{ tenantId: "A", orderId: "ORD-1002" }
{ tenantId: "A", orderId: "ORD-1003" }
```

Now the **compound shard key values** differ even within the same tenant. This unlocks the ability to split data inside a tenant when partitioning/balancing creates and distributes appropriate key ranges.

However, **appending a suffix to the key does not guarantee instant automatic distribution**: it depends on how the collection is sharded/refined/resharded, chunk metadata, indexes, data volume, and the balancer’s ability to split/migrate in your deployed version.

### 9.2. Compound ranged key `{ tenantId: 1, createdAt: 1 }`

Pros:

- Can provide per-tenant locality;
- Queries with `tenantId` equality and a time window can target matching ranges;
- Good for certain per-tenant, time-bound batch jobs/retention.

Cons:

- `createdAt` ascends within each tenant;
- If tenant A accounts for 70% of write traffic, A’s new inserts can still concentrate at a boundary region of tenant A;
- Frequent duplicate timestamps can create high frequency on a `(tenantId, createdAt)` pair;
- System-wide queries by time alone without `tenantId` may fan out.

### 9.3. Compound hashed key `{ tenantId: 1, orderId: "hashed" }`

Idea:

```javascript
sh.shardCollection(
  "shop.orders",
  { tenantId: 1, orderId: "hashed" }
);
```

Documents for tenant A retain the `tenantId` prefix, while the `orderId` component is hashed to break monotonicity and generate many compound key values within the tenant.

However, evaluate carefully:

- Queries specifying **both `tenantId` and `orderId`** can target well.
- Queries filtering only on **`tenantId`** may touch multiple ranges/chunks/shards, since one tenant is spread across hashed `orderId` values.
- Queries filtering on `tenantId` and a **`createdAt` range** are not automatically pruned by a shard key lacking `createdAt`, even with a matching local index.
- If `orderId` lacks distinctness or has one very hot value, hashing the suffix will not eliminate the hot key.

This approach is especially worth considering when distributing writes inside large tenants matters more than keeping all of a tenant’s data on one shard.

### 9.4. Field order matters

Compare:

```javascript
{ tenantId: 1, orderId: "hashed" }
```

with:

```javascript
{ orderId: "hashed", tenantId: 1 }
```

Both distinguish orders, yet the ability to target queries containing **only `tenantId`** changes because the leading component of the shard key changes.

Never pick field order out of habit (“tenant always comes first” or “hashed always comes first”). Check:

1. Which fields actual filters include;
2. The ratio of tenant-only, order-only, and tenant+order queries;
3. Which subset needs locality/zones;
4. How many chunks a large tenant can distribute across;
5. Uniqueness needs and compound shard key rules.

## 10. Trade-offs between shard-key targeting and local indexes

Suppose an application has three APIs:

```javascript
// API A: look up one exact order.
db.orders.findOne({
  tenantId: "TENANT-A",
  orderId: "ORD-000123"
});

// API B: chronological order history for one tenant.
db.orders.find({
  tenantId: "TENANT-A",
  createdAt: {
    $gte: ISODate("2026-03-01T00:00:00Z"),
    $lt: ISODate("2026-04-01T00:00:00Z")
  }
}).sort({ createdAt: -1, _id: -1 }).limit(50);

// API C: system-wide report on PAID orders.
db.orders.find({
  status: "PAID",
  createdAt: {
    $gte: ISODate("2026-03-01T00:00:00Z"),
    $lt: ISODate("2026-04-01T00:00:00Z")
  }
});
```

A `{ tenantId: 1, orderId: "hashed" }` shard key may work very well for **API A**, while API B may fan out across the tenant’s chunks, and API C may read across many shards.

You can still create local indexes:

```javascript
db.orders.createIndex({
  tenantId: 1,
  createdAt: -1,
  _id: -1
});

db.orders.createIndex({
  status: 1,
  createdAt: -1
});
```

These indexes enable **fast local execution on each shard**, but do not change whether a query carries a shard key predicate. A fan-out query with efficient local indexes may be acceptable if infrequent; a critical p99 endpoint that fans out on every call can put heavy strain on the cluster.

### 10.1. One shard key cannot optimize every query simultaneously

In practice, sharding usually requires optimizing routing for the **most critical query patterns**, while other queries rely on local indexes, materialized views, analytics stores, or dedicated read models.

This is not a sign of failed design; it is the natural consequence of a collection having only **one active shard key** at a time.

## 11. Do not confuse the shard key with a unique index

A shard key can have high cardinality without being **unique**.

For example:

```javascript
{ tenantId: 1 }
```

is conceptually valid as a shard key even though each tenant has many documents, though splittability and hot keys pose issues.

Conversely, a unique application business key:

```javascript
{ orderId: 1 }
```

may be unique, yet if issued sequentially under range sharding it still produces monotonic writes.

### 11.1. Unique indexes on sharded collections have constraints

MongoDB enforces specific rules on **unique indexes on sharded collections**: generally they must match a shard key prefix under specific constraints, and hashed indexes do not support `unique: true` the way B-tree unique indexes do.

For instance, business logic requires `orderId` to be unique **system-wide**, while shard key `{ tenantId: 1, createdAt: 1 }` does not include `orderId` in its prefix. Do not assume that:

```javascript
db.orders.createIndex(
  { orderId: 1 },
  { unique: true }
);
```

will enforce uniqueness across the entire sharded cluster as desired.

You must check unique index constraints against the shard key, `_id` restrictions when `_id` is not part of the shard key, and potentially design identifier schemes or a separate registry when global uniqueness is required.

**Shard key selection and unique constraints must be designed together**, rather than discovering after sharding that a required unique index cannot be created.

### 11.2. Monotonic unique IDs are not automatically good shard keys

An auto-increment key is convenient for uniqueness and sorting, yet it is monotonic. You can keep a B-tree unique index on one field (if sharded uniqueness rules permit) while selecting another shard key for distribution, or use an appropriate compound key.

Exact solutions depend on topology and uniqueness scope; there is no magic formula saying “just switch to hashed and keep every unique constraint.”

## 12. Missing, null, or mixed-type shard keys

A collection might contain:

```javascript
{ _id: 1, tenantId: "A", orderId: "O1" }
{ _id: 2, tenantId: null, orderId: "O2" }
{ _id: 3, orderId: "O3" }
{ _id: 4, tenantId: 1001, orderId: "O4" }
```

Here, `tenantId` mixes Strings, Numbers, null, and missing values. These can cause:

- Unintended data distribution;
- Unpredictable query routing from a business standpoint;
- Many records piling around null/missing key values;
- Applications assuming `"1001"` and `1001` are the same tenant despite differing BSON types;
- Difficult shard key migrations due to inconsistent data.

Before choosing a shard key, you should:

1. Audit BSON types using `$type`;
2. Check missing/null rates;
3. Normalize types and formats;
4. Enforce validation on write paths;
5. Verify all data producers (APIs, imports, ETLs) follow the same schema.

A shard key is not a tool that automatically cleans up data quality.

## 13. The difference between document count and document size

Suppose there are two types of orders:

```text
Tenant A: 100,000 documents, ~1 KB each
Tenant B: 100,000 documents, ~50 KB each
```

Both have the **exact same document count**, yet Tenant B occupies roughly 50 times the raw payload bytes, excluding indexes and storage overhead.

If you evaluate a shard key purely by document count, the shard holding Tenant B can run out of disk long before other shards despite balanced record counts.

Similarly, records with huge arrays incur higher update/replication costs than compact records.

Therefore, observe:

- Document count per shard/key;
- Total storage bytes;
- Index sizes;
- Document size distribution (p50/p95);
- Write/update rates;
- Working set in RAM;
- I/O and CPU per shard.

**The goal of sharding is to distribute real resources and load, not merely row counts.**

## 14. Shard keys and chunk/range splitting limits

MongoDB divides the shard key space into metadata units that can be allocated, moved, or balanced across shards per version-appropriate mechanics.

As data grows:

- A range may need to split into smaller ranges if valid split points exist;
- The balancer can move ranges/chunks to improve distribution;
- Metadata can evolve via resharding/migrations;
- Ranges containing too many documents with **the exact same shard key value** can be hard or impossible to split at that value boundary.

### 14.1. Indivisible range: one value appears too often

Suppose one million documents contain:

```javascript
{ tenantId: "TENANT-HOT" }
```

and the shard key is solely `tenantId`.

There are not multiple shard key values for MongoDB to slice the region holding `TENANT-HOT` into non-overlapping ranges while still distinguishing documents by `tenantId` alone. This is an **indivisible/unsplittable range** at the key level.

Large ranges that are hard to split or migrate can lead to imbalance and administrative limits; mechanisms and terms like jumbo chunks and balancer behavior vary across MongoDB versions.

**Do not assume MongoDB invents extra shard key values** or that adding shards spreads a single tenant evenly.

### 14.2. Does increasing chunk size solve hot keys?

Increasing chunk size changes migration counts/granularity, but does not add distinctness to the shard key. For a single hot key, the core issue is **having no useful split boundary in the key space**.

Conversely, arbitrarily shrinking chunk size increases metadata/migration overhead without splitting documents that share the same key value.

### 14.3. The balancer does not guarantee balanced requests per second

The balancer primarily manages data-range distribution per cluster rules, limits, and policies. If Shard A holds 20% of data yet receives 80% of traffic for a hot key, balancing storage bytes will not equalize CPU/IOPS.

To distribute **traffic**, the shard key must allow requests or documents to divide across different values, and application query shapes must leverage that separation.

## 15. Designing for tenant-based workloads

Most SaaS systems have a `tenantId` field. Thus, “shard by `tenantId`” sounds natural.

### 15.1. Benefits of a tenant-oriented shard key

If most endpoints always include:

```javascript
{ tenantId: "TENANT-A" }
```

then a shard key with a tenant prefix lets `mongos` restrict operations to relevant shard-key ranges.

Benefits can include:

- Queries with clear tenant boundaries;
- Good locality for certain tenant-only queries;
- Ability to apply zone/range policies per tenant if properly designed;
- Easier per-tenant modeling for maintenance, moves, or analysis.

### 15.2. Hot-tenant risk

If one tenant generates 80% of write traffic or hundreds of GB, `{ tenantId: 1 }` is risky: that tenant maps to a single shard key value.

### 15.3. Three options to compare

**Option A — `{ tenantId: 1 }`:**

- Simple, grouped by tenant;
- Tenant-only queries can target cleanly;
- Cannot divide one giant tenant into multiple shard-key values.

**Option B — `{ tenantId: 1, orderNo: 1 }`:**

- Distinguishes orders within a tenant;
- Preserves locality by tenant + `orderNo` range;
- If `orderNo` increases monotonically within a tenant, still creates a hot range for large tenants.

**Option C — `{ tenantId: 1, orderId: "hashed" }`:**

- Generates many compound keys and breaks `orderId` monotonicity;
- Has potential to spread large write-heavy tenants;
- Tenant-only queries may span multiple shards; time-range queries are not range-pruned by the hash.

Choose based on the **largest tenant’s scale**, that tenant’s write volume, and the ratio of tenant-only vs. tenant+order queries.

## 16. Designing for event/time-series workloads

Suppose a system collects events:

```javascript
{
  deviceId: "DEVICE-001",
  eventId: "EV-1001",
  eventAt: ISODate("2026-03-01T09:00:00Z"),
  measurement: 42.7
}
```

Common queries:

```javascript
// History of one device over a time window.
db.events.find({
  deviceId: "DEVICE-001",
  eventAt: {
    $gte: ISODate("2026-03-01T00:00:00Z"),
    $lt: ISODate("2026-03-02T00:00:00Z")
  }
});

// Look up one exact event.
db.events.findOne({
  eventId: "EV-1001"
});

// Report across all devices by time.
db.events.find({
  eventAt: {
    $gte: ISODate("2026-03-01T00:00:00Z"),
    $lt: ISODate("2026-03-02T00:00:00Z")
  }
});
```

### 16.1. Ranged sharding on `eventAt`

Pro: time windows can have good locality.

Con: most new events fall into the latest time range -> potential **hot insert shard**. During large ingestion bursts, the balancer may not relieve pressure on the newest range fast enough.

### 16.2. Hashed sharding on `deviceId`

Pro: with many devices writing evenly, hashing `deviceId` distributes devices across shards; equality queries for one `deviceId` target cleanly.

Con: one extremely noisy device still maps to one hash; queries across all devices by time window may scatter.

### 16.3. Compound key on device and time

Example:

```javascript
{ deviceId: 1, eventAt: 1 }
```

supports locality for a single device’s history, though a device streaming continuously still writes to an ascending edge within that device’s group.

Adding `eventId` or bucketing spreads writes further, but forces device-history reads to visit more ranges.

### 16.4. Time-series collections have special rules

MongoDB **time-series collections** have specific constraints on internal bucket organization, `metaField`/`timeField`, and shard keys depending on version. Do not copy rules for regular collections directly to time-series collections without checking your version’s documentation.

Before deciding, clarify whether this is a **regular collection storing events** or a true MongoDB time-series collection.

## 17. Designing for ascending IDs

Many applications use:

```javascript
{
  orderNo: NumberLong("12004567")
}
```

`orderNo` is commonly used to:

- Look up a single order;
- Display human-readable codes;
- Paginate by ID;
- Export orders within a range;
- Assign unique identifiers.

### 17.1. If the workload is mostly equality lookups

If 95% of queries look up a specific `orderNo` and inserts ascend monotonically, a hashed shard key on `orderNo` can fit well:

```javascript
{ orderNo: "hashed" }
```

It disperses ascending keys while retaining equality targeting.

### 17.2. If the workload is mostly range scans

If the system continually runs:

```javascript
db.orders.find({
  orderNo: {
    $gte: NumberLong("12000000"),
    $lt: NumberLong("12100000")
  }
});
```

a ranged shard key offers locality benefits. However, you must evaluate boundary insert hotspots and future partitioning/ingestion adjustments.

### 17.3. Do not assume ObjectId is completely random

BSON `ObjectId` embeds a timestamp prefix, so values generated close in time tend to ascend in comparison order—even though they are not a strict global sequence across all clients.

Consequently, using `{ _id: 1 }` in ranged sharding can create a hot write range for workloads continuously generating `ObjectId`s. To distribute by ID, inspect actual ID characteristics and consider a hashed shard key when appropriate.

### 17.4. UUIDs or random IDs still need evaluation

An apparently random ID helps break monotonicity, yet you still must consider:

- Cardinality and collision policy;
- Whether equality queries carry the shard key;
- Consistent BSON type;
- Index/storage overhead;
- Uniqueness;
- Debuggability and pagination ordering.

Do not conclude “random IDs are always better than sequential ones” if most of your workload scans ID ranges or relies on locality.

## 18. Gathering evidence from data

Do not pick a shard key by guessing which field “looks even.” Profile a representative dataset first.

Example test collection `shardKeyLab`:

```javascript
// RUN ON LEARNING DB ONLY.
// drop() deletes the collection if it already exists.
db.shardKeyLab.drop();

const totalDocs = 100000;
const batchSize = 1000;
const baseTime = Date.parse("2026-01-01T00:00:00Z");

let seed = 259;

function randomUnit() {
  seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
  return seed / 4294967296;
}

let batch = [];

for (let i = 0; i < totalDocs; i++) {
  const r = randomUnit();

  // 65% of orders belong to one very large tenant.
  const tenantId = r < 0.65
      ? "TENANT-HOT"
      : "TENANT-" + (1 + Math.floor(randomUnit() * 1000));

  batch.push({
    tenantId: tenantId,
    orderNo: NumberLong(String(i + 1)),
    orderId: "ORD-" + String(i + 1).padStart(8, "0"),
    customerId: "CUS-" + String(i % 20000),
    status: i % 10 < 7 ? "PAID" : "PENDING",
    createdAt: new Date(baseTime + i * 1000),
    total: NumberDecimal(String((i % 5000) + 100))
  });

  if (batch.length === batchSize) {
    db.shardKeyLab.insertMany(batch, { ordered: false });
    batch = [];
  }
}

if (batch.length > 0) {
  db.shardKeyLab.insertMany(batch, { ordered: false });
}

print("Inserted: " + db.shardKeyLab.countDocuments({}));
```

This dataset is intentionally designed so that:

- `tenantId` is heavily skewed toward one tenant;
- `orderNo` and `orderId` are nearly unique;
- `orderNo` ascends monotonically;
- `createdAt` ascends over time;
- `status` has few values.

Synthetic test data **does not completely replace production**: document sizes, queries/sec, network topology, and real hot keys may differ.

### 18.1. Measure frequency by tenant

```javascript
db.shardKeyLab.aggregate([
  {
    $group: {
      _id: "$tenantId",
      documentCount: { $sum: 1 }
    }
  },
  { $sort: { documentCount: -1 } },
  { $limit: 10 }
]);
```

The output reveals `TENANT-HOT` dominates. Never “assume beforehand” that data is uniform; observe it.

### 18.2. Count distinct values

```javascript
db.shardKeyLab.aggregate([
  {
    $group: {
      _id: "$tenantId"
    }
  },
  {
    $count: "distinctTenantCount"
  }
]);
```

Similarly for `orderId`, `orderNo`, and `status`, you can compare distinct counts. On huge datasets, exact aggregations can be resource-heavy; use sampling/analytical tools at appropriate times.

### 18.3. Find the most common values

```javascript
db.shardKeyLab.aggregate([
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
```

If `PAID` accounts for over 70% of records, shard key `{ status: 1 }` offers poor distribution space.

### 18.4. Evaluate document size by tenant

```javascript
db.shardKeyLab.aggregate([
  {
    $group: {
      _id: "$tenantId",
      docs: { $sum: 1 },
      bytesApprox: { $sum: { $bsonSize: "$$ROOT" } }
    }
  },
  { $sort: { bytesApprox: -1 } },
  { $limit: 10 }
]);
```

`$bsonSize` measures the BSON document size at that pipeline stage; it **does not** capture exact storage/compression/index overhead. Still, it uncovers cases where a tenant with fewer documents has huge payloads.

## 19. Evaluating monotonicity through real observation

Monotonicity cannot be determined from field names alone. Inspect values arriving in **insert order / write time**.

For example, inspect a list of the newest values:

```javascript
db.shardKeyLab.find(
  {},
  {
    _id: 0,
    orderNo: 1,
    createdAt: 1
  }
)
.sort({ createdAt: -1 })
.limit(20);
```

In this dataset, `orderNo` ascends alongside `createdAt`. In production, however, events can arrive late, retry, backfill, or import historical data, making the ascending trend non-absolute.

### 19.1. Backfill data can alter the pattern

An event system normally appends current timestamps, until a backfill job inserts 100 million events from last year. A ranged shard key on `eventAt` may then distribute load onto **older time ranges**, not solely the tail.

Thus, design must account for:

- Streaming data;
- Bulk backfills;
- Retries/out-of-order events;
- Seasonal spikes;
- Archive/purge plans;
- Tenant onboarding and migrations.

### 19.2. A single monotonicity metric does not replace workload analysis

Suppose 90% of inserts follow ascending `orderNo` and 10% are random backfills. Overall behavior can still create a hot shard. Conversely, a field ascending per user across millions of well-distributed users may not form a global hot range like a single shared sequence.

Observe **write distribution across the shard key domain**, not just the fraction of consecutive increasing pairs.

## 20. Analyzing query patterns: where do fields appear?

A shard key should be evaluated against your key queries.

Example statistics from an application:

| Query pattern | Request share | Filter fields | Desired outcome |
|---|---:|---|---|
| Exact order lookup | 55% | `tenantId + orderId` | Targeted, low latency |
| Customer history | 25% | `tenantId + customerId + createdAt` | Time-based pagination |
| Current-month tenant report | 12% | `tenantId + createdAt` | Range query |
| System-wide statistics | 5% | `status + createdAt` | Acceptable analytical fan-out |
| Reconciliation debugging | 3% | `orderNo` | Targeted if key supports it |

These figures are illustrative. In real systems, gather them from properly authorized logs/telemetry with sampling and sensitive-data masking.

### 20.1. Questions to ask for each query

1. Does the filter contain the **full shard key**?
2. For a compound key, does it match a suitable **prefix**?
3. Are predicates equality or range?
4. Does the query include sorting/pagination supported by local indexes?
5. Must the query read multiple tenants or multiple time windows?
6. How many times per second does this endpoint run?
7. Is the result size large or small?
8. Does a hot tenant/user skew request distribution?

### 20.2. Targeting does not always mean “one shard”

Even with a well-chosen shard key, range queries or partial-prefix filters can touch **multiple chunks across multiple shards**. That can still be well-targeted if it hits only a small subset of ranges rather than the entire cluster.

Measure **number of shards queried and data scanned per shard**, rather than slapping a binary “targeted” or “scatter” label on it.

### 20.3. What does scatter-gather cost?

A query without a shard key filter may require:

```text
             mongos
          /     |      \
      Shard A Shard B Shard C
        |        |       |
      results  results results
          \     |      /
          merge / sort / limit
```

Costs include:

- Network fan-out to many shards;
- CPU/IOPS and query execution on each shard;
- Transferring partial results;
- Merging/sorting at the router or shards per execution plan;
- Tail latency dictated by the slowest shard;
- Increasing fan-out as shards are added.

Scatter-gather is not universally wrong: for periodic system-wide reporting, it can be acceptable. For high-frequency interactive endpoints, it signals that shard key or query design needs review.

## 21. Using analyzeShardKey and query sampling when supported

Supported MongoDB versions provide tools such as **`analyzeShardKey`** to evaluate candidate shard key properties and, when query sampling is available, analyze read/write distribution.

Conceptual example:

```javascript
db.adminCommand({
  analyzeShardKey: "shop.orders",
  key: { tenantId: 1, orderId: 1 }
});
```

Another candidate:

```javascript
db.adminCommand({
  analyzeShardKey: "shop.orders",
  key: { orderId: "hashed" }
});
```

**Important:** Command availability, index prerequisites, output fields, and query sampling depend on server version, deployment topology, and privileges. Do not assume these snippets work identically on every MongoDB version.

### 21.1. What information to inspect

Depending on version and data/sampling setup, analysis may include:

- Document count;
- Distinct shard key value count;
- Most frequent values;
- Monotonicity assessment;
- Read distribution characteristics;
- Write distribution characteristics;
- Share of queries targeting single vs. multiple shards;
- Degree of load concentration.

Not every field is always present. For instance, read/write distribution analysis requires representative query samples; absence of samples must never be interpreted as “zero query fan-out.”

### 21.2. Query sampling requires planning

In supported versions, the query analyzer can be configured to sample workload. Example command shape:

```javascript
db.adminCommand({
  configureQueryAnalyzer: "shop.orders",
  mode: "full",
  samplesPerSecond: 10
});
```

This command is illustrative; sampling configuration must follow version/cluster rules and permission policies. In production, sampling incurs overhead and may capture sensitive metadata/query patterns, so you should:

1. Pick a representative time window;
2. Include peak hours and batch jobs;
3. Record the sampling rate;
4. Define how sample data is secured, retained, and purged;
5. Stop or reduce sampling once sufficient data is collected.

Never leave full sampling running indefinitely just to get nice distribution charts.

### 21.3. Analysis output does not replace load testing

A shard key with high cardinality in `analyzeShardKey` can still fail in production if:

- Read workloads mostly omit the shard key;
- One user/tenant drives overwhelming traffic;
- A compound key lacks range locality;
- Index footprint grows too large;
- Balancer/migrations are under strain;
- Per-shard query planners choose suboptimal plans.

Combine **key properties + workload metrics + benchmarks**.

## 22. Comparing candidates with an evidence-based scoring matrix

Instead of choosing by a single metric, build a table across candidates.

Example SaaS workload with large tenants:

| Criterion | `{tenantId:1}` | `{orderNo:1}` | `{orderNo:"hashed"}` | `{tenantId:1,orderId:"hashed"}` |
|---|---|---|---|---|
| Cardinality | Medium/high | High | High | Very high combined |
| Hot key risk | **High** with large tenants | Low if `orderNo` unique | Low if `orderNo` unique | Lower than tenant-only if `orderId` varied |
| Monotonic insert risk | Depends on tenant distribution | **High** | Lower | Lower on hashed component |
| Equality order lookup | Needs tenant | Good with `orderNo` | Good with `orderNo` | Good with tenant+order |
| Range `orderNo` | Not directly supported by key | Has locality | **Loses locality due to hash** | No `orderNo` range locality |
| Tenant-only reads | Can be favorable | Usually fan-out | Usually fan-out | May hit multiple shards within tenant |
| Unique constraints | Must check rules | Must check rules | Hashed indexes cannot be unique | Must check compound hashed rules |
| Hot tenant writes | Risky | Spreads by `orderNo` but monotonic | Spreads cluster-wide | Potential to spread within tenant |

This table is a **preliminary assessment of key properties**, not a measured benchmark. Never assign absolute 10/10 scores without real data.

### 22.1. Weight criteria by SLOs

Example:

```text
Read latency p95 order lookup:       high weight
Write throughput during peak:        high weight
Monthly analytics fan-out:           low weight
Per-tenant locality:                 medium weight
Operational simplicity:              medium weight
```

If 80% of critical business operations are order writes, a hashed key may make sense even if nightly range reports fan out.

If the application is an analytics engine continuously scanning time ranges, prioritize query locality—and potentially offload analytics to a secondary store/collection.

## 23. Zone sharding: intentional distribution instead of uniform spread

Some systems must place data regionally due to:

- Data sovereignty requirements;
- Access latency;
- Customer contracts;
- Hot/cold storage tiering;
- Operational policies.

MongoDB supports **zone sharding** under suitable conditions, binding shard-key ranges to zones.

Conceptual example:

```text
EU Tenant IDs -> Zone EU
AP Tenant IDs -> Zone AP
```

Choosing a shard key with region/tenant locality makes defining zone ranges more natural.

However, zone constraints **restrict where chunks may reside**, so load balancing is no longer free across the entire cluster. If Zone EU has only one shard or most traffic hits one tenant in the EU, adding shards to Zone AP will not relieve EU load.

### 23.1. Hashed keys and zone policies

A hashed shard key spreads keys across the hash space, but if the business requires all documents of a tenant in a fixed region, a hashed design must be evaluated for zone-range expressibility and appropriate prefix/compound key rules.

Do not assume “hashing distributes evenly cluster-wide” will simultaneously satisfy **data residency** and regional locality.

### 23.2. Regional availability trade-offs

Pinning a tenant to a zone within a single failure domain may cut latency or meet residency, yet reduces availability for that tenant if that region fails. Shard keys, zones, and replica set placement must be designed **together**.

## 24. Choosing a shard key for time-based queries

There is a classic tension:

- **Writes:** new events always carry newer timestamps and need spreading.
- **Reads:** users frequently view the “last 24 hours” and want time-range locality.

Choosing ranged `{ createdAt: 1 }` aids range reads, yet inserts can run hot.

Choosing `{ createdAt: "hashed" }` can spread inserts when timestamps have enough distinct values, yet range reads scatter; timestamps with many duplicates also create hot hash values.

Choosing `{ deviceId: "hashed" }` spreads writes across many devices, yet cross-device time reports fan out.

No shard key is ideal for both. Architectures often:

1. Pick a shard key suited to **ingestion throughput**;
2. Use secondary indexes on each shard to cut local scan cost;
3. Pre-aggregate hourly/daily summaries into another collection;
4. Offload history to an appropriate analytics system;
5. Design zones/retention per data lifecycle policies.

### 24.1. Timestamp frequency also matters

If a system generates 100,000 events per second yet `createdAt` is truncated to whole seconds, each second produces **100,000 documents with the identical timestamp**.

Even a hashed shard key on `createdAt` hashes all those documents to **one hash value**. High write concurrency paired with coarse timestamp resolution creates a frequency problem.

Using a unique `eventId` or a compound key with sufficient discriminating breadth helps, provided subsequent time-query requirements are checked.

## 25. Considerations for updating shard key values

Some fields mutate over time:

```javascript
{
  tenantId: "TENANT-A",
  status: "PENDING",
  ...
}
```

If `status` were the shard key, transitioning an order from `PENDING` to `PAID` would **change the shard-key value**, affecting routing and potentially triggering document movement and extra cost. Beyond low cardinality, this is another reason `status` is usually unsuitable.

Modern MongoDB releases support updating shard key values under specific conditions, yet the operation is constrained by update type, routing, transactions/retries, and other requirements. **Never claim shard keys are always strictly immutable**, nor assume frequent shard key updates are cheap.

Strong shard key candidates generally have:

- Stable values throughout the document lifecycle;
- Consistent BSON types;
- Many distinct values;
- No heavy load concentrated on one value;
- Alignment with common queries.

## 26. Changing the shard key after sharding: refine and reshard

Picking the wrong shard key on a massive collection carries substantial remediation cost.

MongoDB offers tools like **refining a shard key** and **resharding** in supported versions, with different purposes.

### 26.1. Refine shard key

Example initial shard key:

```javascript
{ tenantId: 1 }
```

Need to add a suffix component:

```javascript
{ tenantId: 1, orderId: 1 }
```

`refineCollectionShardKey`, subject to version constraints, **extends a shard key by appending trailing fields**. It does not allow arbitrarily changing the order or types of existing components.

Moreover, refining **does not immediately redistribute all existing data according to a new hash design**. You must inspect metadata/chunk placement, balancer behavior, and the distribution of the added field’s values.

Conceptual example:

```javascript
db.adminCommand({
  refineCollectionShardKey: "shop.orders",
  key: { tenantId: 1, orderId: 1 }
});
```

This command has index/precondition requirements and impacts that vary by version. Execute only after consulting official documentation and preparing a migration plan.

### 26.2. Reshard collection

To switch completely from:

```javascript
{ orderNo: 1 }
```

to:

```javascript
{ orderNo: "hashed" }
```

is not a simple suffix append. MongoDB supports **resharding** in appropriate versions/topologies to change the shard key.

Conceptual example:

```javascript
sh.reshardCollection(
  "shop.orders",
  { orderNo: "hashed" }
);
```

Resharding can involve building a new copy of the data, syncing ongoing changes, coordinating metadata cutover, index requirements, network/CPU/disk load, and application-impacting phases depending on version.

**Do not use this command as an emergency hotfix when a cluster is already overloaded** without headroom, monitoring, a rollback plan, and a tested runbook.

### 26.3. Getting the key right early is cheaper than fixing it late

Before sharding a large collection:

- Model 6–12 months of growth;
- Test hot-tenant/hot-key scenarios;
- Check peak-load write distribution;
- Evaluate range queries;
- Account for uniqueness;
- Review cluster zones and topology;
- Prepare a shard key evolution plan if initial assumptions change.

Shard keys can evolve over time, but late changes are costly operational projects—not a quick one-line index tweak.

## 27. Observing data and load after deployment

Once a collection is sharded, monitor live signals rather than relying solely on pre-launch estimates.

| Metric | Meaning |
|---|---|
| Documents/bytes per shard | Storage balance |
| Chunk/range distribution | Distribution capability of the shard key |
| Chunk migrations | Whether the balancer is moving lots of data |
| Failed/jumbo/indivisible migrations | Signs of high-frequency keys or partitioning constraints |
| Write ops/sec per shard | Presence of a hot write shard |
| Read ops/sec per shard | Presence of a hot read shard |
| CPU, IOPS, disk usage, cache pressure | Resource imbalance |
| p95/p99 by endpoint/shard | User-facing impact |
| Targeted vs. scatter-gather queries | Whether query shapes leverage the shard key |
| Replication lag per shard replica set | Load headroom and data freshness |
| Balancer activity/window | Timing and cost of balancing |

### 27.1. `sh.status()` and metadata

In `mongosh` connected through `mongos`, you can run:

```javascript
sh.status();
```

This displays high-level cluster/sharding state. Exact output format and detail vary by version. Pair it with monitoring, profiling, and `explain` to understand queries.

### 27.2. `explain()` to inspect shards involved

```javascript
db.orders.find({
  tenantId: "TENANT-A",
  orderId: "ORD-000123"
}).explain("executionStats");
```

Compare with:

```javascript
db.orders.find({
  status: "PAID"
}).explain("executionStats");
```

Explain output in a sharded cluster can show participating shards, winning plans per shard, and documents/keys examined. Exact structure varies by version and query engine.

Do not read only total `executionTimeMillis` and conclude a shard key is good. Examine **fan-out, per-shard work, and real workloads**.

### 27.3. Balanced data but poor p99

Suppose:

```text
Shard A: 30% of data, 80% of write traffic
Shard B: 35% of data, 10% of write traffic
Shard C: 35% of data, 10% of write traffic
```

Storage is fairly even, yet workload is severely skewed. If the shard key continuously routes a hot user to A, redesign distribution **by query/write frequency**, rather than just running the balancer.

## 28. A practical shard key selection workflow

### Step 1 — Clarify the scaling goal

First ask:

- Are we hitting **storage** or **write throughput** limits?
- Is the workload slow due to a single shard’s primary or scatter queries?
- Should data distribute by tenant, device, order, or region?
- What are the SLAs and budget?

Do not add sharding simply because a collection crosses an arbitrary document threshold. If indexes/schema/queries solve the bottleneck, sharding adds unnecessary complexity.

### Step 2 — List candidate keys

Examples:

```text
tenantId
orderId
orderNo
customerId
createdAt
(tenantId, orderId)
(tenantId, createdAt)
(tenantId, hashed(orderId))
```

Evaluate both single-field and compound candidates; avoid locking in by field name alone.

### Step 3 — Measure cardinality

Record:

```text
total documents N
distinct shard key values D
distinctRatio = D/N
```

For compound keys, measure distinctness of the **entire tuple**, not only individual fields.

### Step 4 — Measure frequency/skew

Record:

```text
top 10 most frequent values
f_max
p_max
top 1% key share
document bytes by key
read ops/sec by key
write ops/sec by key
```

Look closely for ultra-hot values, null/missing entries, and keys likely to grow hotspots later.

### Step 5 — Measure monotonicity

Inspect incoming key streams over insert time. Check for:

- Strict ascending/descending trends;
- Per-tenant ascending trends;
- Duplicate timestamps;
- Out-of-order/backfills;
- Bulk insert bursts.

For monotonic candidates, consider hashed keys or compound designs, while checking range query impact.

### Step 6 — Analyze query routing

Calculate the share of queries with:

```text
full shard key equality
shard key prefix equality
range on shard key
no shard key predicate
sort/limit over many shards
```

Inspect target shard counts and real call frequencies for critical queries.

### Step 7 — Review constraints

Check:

- Unique business keys;
- Shard key update frequency;
- BSON types/arrays/nulls;
- Zones/data residency;
- Time-series or special collections;
- Index requirements;
- Replica set placement and failover;
- Reshard memory/disk footprint.

### Step 8 — Test with representative data

Use a staging/test environment to:

- Populate a dataset with realistic skew and scale;
- Build a matching sharded cluster;
- Measure write p50/p95/p99 and per-shard throughput;
- Exercise range/equality reads;
- Measure query fan-out;
- Observe migrations and balancing;
- Test scaling shard count to verify hotspots actually decrease.

### Step 9 — Document the architecture decision record

Record:

```text
Chosen shard key:
  { tenantId: 1, orderId: "hashed" }

Rationale:
  Distributes writes inside large tenants,
  equality lookups by tenant+order are common.

Trade-offs:
  Tenant-only reads and time-range analytics
  may need to read from multiple shards.

Constraints:
  Unique keys, schema, query routing,
  zones, and capacity must be satisfied.

Monitoring metrics:
  Per-shard write TPS, p95 latency,
  distribution, scatter percentage.

Re-evaluation triggers:
  Hot tenant > X% load,
  fan-out > Y% queries,
  disk skew or latency breaching SLO.
```

Variables `X` and `Y` must come from real SLOs and workloads, not universal magic numbers.

## 29. Hands-on exercises

### Exercise 1 — Distinguish the three criteria

For each field below, analyze cardinality, frequency, and monotonicity:

```text
status     = NEW/PAID/CANCELLED
tenantId   = 10,000 tenants, one tenant holds 70% of orders
orderNo    = continuously incrementing integer per order
createdAt  = ascending timestamp, many orders share the same second
orderId    = UUID/random ID per order
```

Which field is riskiest for range sharding? Which is riskiest for hot keys? Why is high cardinality insufficient to pick ranged `orderNo`?

### Exercise 2 — Measure frequency with aggregation

Create `shardKeyLab` from section 18.

1. Count documents by `tenantId`.
2. Identify the top 5 tenants.
3. Calculate the largest tenant’s percentage share.
4. Count distinct `orderId` and `status` values.
5. Explain why `{ tenantId: 1 }` can still run into trouble despite having many tenants.

### Exercise 3 — Monotonic inserts and hot ranges

With range sharding `{ orderNo: 1 }`, suppose:

```text
Shard A: [-∞, 1,000,000)
Shard B: [1,000,000, 2,000,000)
Shard C: [2,000,000, +∞)
```

Millions of new orders arrive with `orderNo >= 2,500,000`.

1. Which shard do new inserts typically target?
2. Why doesn’t the balancer moving older chunks fix the root cause?
3. If `{ orderNo: "hashed" }` is chosen instead, how does write distribution conceptually change?
4. How are range queries for `orderNo` 2,500,000–2,600,000 affected?

### Exercise 4 — Hot tenant

A SaaS system has tenant A accounting for 80% of writes, while 5% of other tenants share 20%.

1. Evaluate shard key `{ tenantId: 1 }`.
2. What does appending `orderId` as a suffix change about the compound key’s cardinality?
3. Compare `{ tenantId: 1, orderNo: 1 }` and `{ tenantId: 1, orderId: "hashed" }`.
4. Why might adding more shards alone fail to reduce CPU on tenant A?
5. Assess the impact on an API fetching order history by tenant and time range.

### Exercise 5 — Query targeting

With shard key `{ tenantId: 1, orderId: "hashed" }`, evaluate:

```javascript
db.orders.findOne({
  tenantId: "A",
  orderId: "O-1"
});

db.orders.find({
  tenantId: "A"
});

db.orders.find({
  orderId: "O-1"
});

db.orders.find({
  createdAt: { $gte: ISODate("2026-03-01T00:00:00Z") }
});
```

Which query has full-key equality? Which has a prefix? Which lacks the shard key? Why does a local `createdAt` index help execution yet fail to turn the last query into a single-shard target?

### Exercise 6 — Read frequency vs. storage frequency

Two tenants:

```text
Tenant A: 50% data, 5% traffic
Tenant B: 2% data, 70% traffic
```

Predict which shard may run hot if both reside on separate key ranges. Which metrics distinguish **storage skew** from **traffic skew**?

### Exercise 7 — Time-series ingestion

A system writes 100,000 events/sec, with every event’s timestamp rounded to the second.

1. Why does `createdAt` have high frequency despite seeming like a timestamp?
2. Why doesn’t hashing `createdAt` split events sharing the same second?
3. Propose an additional key field with appropriate cardinality.
4. Assess the impact on queries asking for “all events from 8am to 9am.”
5. If the collection is a MongoDB time-series collection, what additional constraints must be checked?

### Exercise 8 — Designing uniqueness

The application requires `orderId` to be unique cluster-wide, with `tenantId` as the tenant key.

1. Distinguish a shard key from a unique index.
2. Why is `unique: true` on a hashed index not a valid solution?
3. When the shard key lacks `orderId` in its prefix, what constraints apply?
4. Design a business identifier/registry or index strategy compatible with your deployed version’s rules.

### Exercise 9 — Range locality or write distribution?

One system has 70% inserts, 25% order lookups by ID, and 5% `orderNo` range reports. Another system has 10% inserts and 80% `orderNo` range scans.

For both systems, compare ranged vs. hashed shard keys on `orderNo`. How might the conclusions differ? State the metrics you would measure to defend each decision.

### Exercise 10 — Planning a reshard

A collection is currently sharded on `{ tenantId: 1 }`, with one tenant holding 85% of data and write load.

1. Explain why an unsplittable range can form under `tenantId`.
2. Propose two new candidate shard keys.
3. When is refining with a suffix sufficient, and when is full resharding needed?
4. What disk/network/CPU costs must be prepared for?
5. How do you verify query routing and uniqueness after the change?

### Exercise 11 — Geographic partitioning

Tenants require data storage in EU or APAC regions, yet large tenants can run very hot.

1. Which locality must shard key/zone policies satisfy?
2. If the EU zone has only one shard, does adding APAC shards relieve a hot EU shard?
3. Why does a plain hashed key fail to guarantee data residency?
4. Propose a plan to scale capacity inside each zone.
5. Distinguish balancing by storage from balancing by traffic.

### Exercise 12 — Shard key decision report

Prepare an engineering report comparing two candidate keys covering:

- Cardinality and top-frequency values;
- Data size and request rates by key;
- Insert monotonicity;
- Share of queries with full shard key/prefix/range;
- Expected scatter-gather rate;
- Unique constraints and data types;
- Staging throughput/latency test results;
- Selection rationale, accepted trade-offs, and alert thresholds.

Never write simply “hashing spreads evenly” or “range makes queries fast” without specifying **which workload** and **which conditions** substantiate the claim.

## 30. MongoDB references

- [MongoDB Sharding](https://www.mongodb.com/docs/manual/sharding/)
- [Choose a Shard Key](https://www.mongodb.com/docs/manual/core/sharding-choose-a-shard-key/)
- [Shard Keys](https://www.mongodb.com/docs/manual/core/sharding-shard-key/)
- [Hashed Sharding](https://www.mongodb.com/docs/manual/core/hashed-sharding/)
- [Range-Based Sharding](https://www.mongodb.com/docs/manual/core/ranged-sharding/)
- [Analyze Shard Key](https://www.mongodb.com/docs/manual/reference/command/analyzeShardKey/)
- [Configure Query Analyzer](https://www.mongodb.com/docs/manual/reference/command/configureQueryAnalyzer/)
- [Reshard Collection](https://www.mongodb.com/docs/manual/core/resharding/)
- [Refine a Shard Key](https://www.mongodb.com/docs/manual/core/sharding-refine-a-shard-key/)
- [Zone Sharding](https://www.mongodb.com/docs/manual/core/zone-sharding/)
- [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)

## Conclusion

A good shard key must be chosen from **data and workload**, not field names alone.

High **cardinality** provides enough distinct values to partition the key space, yet is insufficient on its own. **Frequency** of individual values must be checked to prevent one tenant, user, or status from dominating data or traffic. **Monotonicity** of new values dictates the risk of continuous inserts piling into a boundary range under a ranged shard key. Even a field with **a unique value per document** can still be a poor ranged shard key if values increase relentlessly.

**Range sharding** helps when range queries and locality matter, yet can create hot shards on monotonic keys. **Hashed sharding** spreads many distinct keys, including ascending IDs, yet loses original range locality and **cannot fix a single hot key**. **Compound shard keys** can raise cardinality and subdivide data inside a tenant, though field ordering and hashed components introduce trade-offs for query targeting, read scope, uniqueness, and operations.

Before committing, measure distinct values, top frequencies, request distributions, write direction, data size, query patterns, and staging behavior. After rollout, monitor inter-shard skew, fan-out, hot keys, migrations, and p95/p99 latency. **The ultimate goal is not even document counts on a diagram, but distributing real load while keeping critical queries efficiently routed and satisfying application data constraints.**
