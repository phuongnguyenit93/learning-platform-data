# Choosing a Shard Key Based on Data Distribution and Query Patterns

## 1. Why does the shard key determine sharding effectiveness?

In MongoDB, a **shard key** is a field or set of fields used to partition documents of a sharded collection into data ranges (chunks) and distribute them across shards. When an application sends a query through `mongos`, the system relies on the shard key in the filter condition to determine which shards to access.

A good shard key must satisfy two goals simultaneously:

1. **Balanced data and traffic distribution:** avoid one shard holding most of the storage, writes, or resource-intensive queries.
2. **Efficient routing:** common queries should be routed to as few shards as possible, reducing data transfer and result merging work.

These two goals can conflict. For example, distributing individual orders randomly can help spread writes evenly, but a screen listing orders by tenant would then have to search across many shards. Therefore, you cannot choose a shard key merely by counting distinct values of a field.

In **Spring Data MongoDB**, `MongoTemplate` and repositories still issue standard MongoDB queries; routing is handled by the MongoDB cluster. However, how filters are designed in the application determines whether the server can use the shard key for routing. This is part of data and query design within the scope of Spring Data MongoDB, alongside repositories, indexes, aggregations, and performance diagnostics.

### Running example model

Suppose a SaaS system stores orders for multiple businesses in the `shop.orders` collection:

~~~javascript
{
  _id: ObjectId("66aa00000000000000000001"),
  tenantId: "tenant-17",
  orderId: "ORD-2026-000081",
  createdAt: ISODate("2026-11-12T09:30:00Z"),
  status: "PAID",
  total: NumberDecimal("1290000")
}
~~~

The screens and jobs have the following illustrative characteristics:

| Business operation | Common query filter | Reference share |
| --- | --- | ---: |
| List orders of a tenant over time | `tenantId = ?`, `createdAt` in range, sorted newest first | 60% |
| View details of a single order | `tenantId = ?`, `orderId = ?` | 25% |
| System-wide reports | Aggregations across many tenants and months | 10% |
| Other operational tasks | Lookup or update by status | 5% |

These percentages are **assumptions for practicing decision-making**. In real-world application, collect metrics from logs, tracing, and production workloads. You also need to measure write volume, document size, and active tenant count; looking only at read query proportions is not enough.

## 2. Understanding key properties of a shard key

### 2.1. Cardinality: number of distinct values

**Cardinality** is the number of distinct values of a field or field combination.

- `status` only has a few values such as `NEW`, `PAID`, `CANCELLED`: low cardinality, generally unsuitable as a standalone shard key.
- `tenantId` may have tens of thousands of values: better cardinality, though order counts across tenants can vary dramatically.
- `orderId` is usually nearly unique: high cardinality, though not necessarily suited for queries filtering by tenant.

High cardinality enables splitting data into smaller pieces, but does not by itself guarantee balanced load. A few values can account for most of the data or traffic. With a shard key containing only `tenantId`, **all documents with the same tenantId share the same shard key value**; the balancer alone cannot split that set of documents into multiple different shard key ranges.

### 2.2. Frequency: distribution of occurrences and access

Beyond the number of distinct values, observe:

- **Document/storage distribution by value**: which tenant holds the most data?
- **Write distribution by value**: which tenant creates orders continuously?
- **Read distribution by value**: does any tenant receive most query requests?
- **Variation over time**: do peak hours, month-end, or promotional campaigns concentrate load on a subset of keys?

A key that balances storage at deployment time can still create a hot shard when one tenant generates most of the requests. Measure both storage size **and** QPS/CPU/IO/latency per shard.

### 2.3. Monotonicity: values increasing or decreasing over time

Fields such as `createdAt`, auto-incrementing codes, and certain ID formats are **monotonic**. If you use a ranged shard key with continuously increasing values, new records tend to concentrate in the upper range, causing one shard to absorb most writes at a given moment. Other shards still hold data but sit relatively idle.

Hashing a field with high cardinality generally spreads records more evenly. In return, **range** queries on the hashed field can no longer be routed in chronological order like a range key.

### 2.4. Query locality: does the query include the shard key?

When a query provides enough information for `mongos` to narrow down the relevant chunks, it can **target** a single shard or a subset of shards. If the necessary conditions are missing, `mongos` may have to **scatter-gather**: send the query to many or all shards and merge the results.

Do not conflate three concepts:

- **Targeted query**: routed to the shards holding the relevant key ranges; may still hit more than one shard if the range spans widely.
- **Single-shard query**: a specific case requiring only one shard.
- **Scatter-gather query**: must broadcast the query widely because the data scope cannot be sufficiently narrowed via the shard key.

This distinction is very important for compound shard keys. A query containing the key prefix can narrow down the data scope, but does not guarantee touching only a single shard.

### 2.5. Stability and data constraints

A shard key should be based on attributes that rarely change over a document's lifecycle. Updating a shard key value or changing the sharding strategy is more complex than updating an ordinary field and can trigger data movement.

Evaluate index and uniqueness constraints upfront:

- Unique indexes on a sharded collection are constrained by the shard key; with range sharding, requiring the shard key prefix is a key part of unique index design.
- **Hashed indexes do not support unique constraints**. Do not assume cluster-wide uniqueness is guaranteed simply because `orderId` is hashed.
- If `_id` is not the shard key, understand the enforcement limits of `_id` uniqueness in a sharded environment and adopt a suitable ID generation strategy.
- You cannot arbitrarily choose an array field as a shard key. The shard key and its supporting index must comply with the restrictions of your MongoDB version.

These constraints can disqualify an option that initially appears optimal for performance.

## 3. Comparing shard key strategies

| Shard key type | Strengths | Trade-offs / risks | Typically suitable when |
| --- | --- | --- | --- |
| **Ranged**, e.g. `{ tenantId: 1, createdAt: 1 }` | Can route by tenant and time range; supports locality | Hot tenants; chronologically ordered writes in a key range can cause hotspots | Most queries filter by tenant plus a date range |
| **Hashed**, e.g. `{ orderId: "hashed" }` | Spreads high-cardinality keys, reducing write concentration at one end of the range | Queries by tenant or date range typically fan out | Reads/writes are primarily by order ID |
| **Hashed by tenant**, e.g. `{ tenantId: "hashed" }` | Spreads different tenants across shards; lookups for one tenant can be targeted | Large tenants can still concentrate on a single shard; range queries across tenants lose advantage | Many relatively uniform tenants, queries almost always know the tenant |
| **Compound hashed**, e.g. `{ tenantId: 1, orderId: "hashed" }` | Can split a large tenant's data by orderId; queries with both tenant and orderId route precisely | Tenant-only queries may touch multiple shards; date queries require separate indexes | Skewed tenant sizes, heavy writes, many ID-based queries |

No single type is best for all systems. Field order in a compound shard key is also a design choice, because `mongos` uses key components according to index structure to determine relevant ranges.

### Routing example when using `{ tenantId: 1, createdAt: 1 }`

| Filter | Routing behavior | Notes |
| --- | --- | --- |
| `tenantId = "tenant-17" AND createdAt >= d1 AND createdAt < d2` | Narrows down well by prefix and time range | Fits order listing workflows |
| `tenantId = "tenant-17"` | Narrows down to the tenant's chunks | May involve multiple chunks/shards if the tenant is large |
| `orderId = "ORD-..."` | Lacks shard key prefix | Likely becomes scatter-gather despite secondary indexes on each shard |
| `createdAt >= d1 AND createdAt < d2` | Lacks `tenantId` prefix | Likely has to search across multiple shards |
| `status = "PAID"` | Does not contain shard key | Typically fans out across the entire cluster |

**Note:** a secondary index can make searches *within each shard* faster, but does not automatically turn a query missing the shard key into a single-shard query.

### When to add a hashed suffix?

Suppose one tenant accounts for 45% of all orders and generates 60% of writes. If you only choose `tenantId`, data sharing that same key is difficult to distribute. You can consider `{ tenantId: 1, orderId: "hashed" }` if `orderId` has sufficient distinct values and does not change.

This enables splitting a single tenant's data across multiple orderId values; it **does not mean** MongoDB always balances the entire tenant immediately. Actual distribution still depends on chunk size, split points, the balancer, tenant distribution, and per-key traffic. At the same time, screens filtering only by `tenantId` may touch more shards than before.

## 4. Process for choosing a shard key from real metrics

### Step 1: Tabulate the workload

For each query, record:

1. Actual filters, especially fields appearing in equality (`=`), range (`>=`, `<`), and `$in` conditions.
2. Frequency, read/write ratio, p95/p99 latency, and number of documents scanned.
3. Typical result count, sorting, pagination, aggregations, and whether queries can include the tenant.
4. Feasibility of updating application code to always pass shard key conditions, such as fetching order details using `tenantId + orderId`.

Do not focus only on the single most frequent query. An infrequent reporting query that scans hundreds of millions of documents can still dominate resource cost.

### Step 2: Measure data distribution by candidate key

Check the number of distinct values, tenant size percentiles, document/byte counts, and write rates on the largest groups. You can run preliminary analysis using aggregation in a test environment or on suitably instrumented data:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$tenantId",
      orderCount: { $sum: 1 }
    }
  },
  { $sort: { orderCount: -1 } },
  { $limit: 10 }
])
~~~

This pipeline finds the tenants with the most documents; it does **not** measure byte size or QPS. On large datasets, be mindful of aggregation cost and rely on prepared telemetry or statistics systems. To tell whether a key will cause hotspots, you must also collect read/write traffic per tenant across multiple time windows.

### Step 3: Evaluate each candidate against the same criteria

| Criterion | Verification question |
| --- | --- |
| Distribution | Does the key have enough values to split chunks? Does any value group hold too much data? |
| Writes | Do new inserts land across multiple shards or pile onto one key range? |
| Reads | What percentage of common queries can be targeted? |
| Expensive queries | How many shards must aggregations, exports, and ad-hoc lookups touch? |
| Indexes and sorting | Is the shard key supporting index compatible with primary filters and sort orders? |
| Stability | Is the shard key frequently updated? Is there risk of tenant partitioning rules changing? |
| Uniqueness | Must orderId, invoice codes, or business keys be guaranteed unique cluster-wide? |
| Operations | As shard count grows, are data distribution costs and potential resharding needs acceptable? |

Eliminate candidates that violate hard requirements first, then compare performance on datasets closely modeling production. Do not substitute an arbitrary composite score for actual testing.

### Step 4: Choose based on workload, with change triggers

For the illustrative workload at the beginning, you could choose `{ tenantId: 1, createdAt: 1 }` **if** per-tenant data is reasonably balanced, date-range listing queries are top priority, and no single tenant generates excessive write load.

If a few large tenants dominate most data or writes, also test `{ tenantId: 1, orderId: "hashed" }` or an alternative data strategy. The trade-off to evaluate is fan-out on tenant/date-range listing queries and extra indexes; adding a hashed suffix is not free.

If most requests read or write an independent order by `orderId`, `{ orderId: "hashed" }` may be more pragmatic. However, tenant-aware APIs must still enforce access control at the application layer; having a query target a shard does not replace tenant data isolation checks.

## 5. Practice in MongoDB

Assume you have a sharded MongoDB cluster and operate via `mongos`. The illustrative approach is to shard `shop.orders` by `tenantId` and `createdAt`.

### Create the index and declare the shard key

~~~javascript
use shop

// Supporting index for the ranged shard key.
db.orders.createIndex({ tenantId: 1, createdAt: 1 })

// Run via mongos, after verifying cluster configuration,
// existing indexes, and collection constraints.
sh.shardCollection("shop.orders", { tenantId: 1, createdAt: 1 })
~~~

Because this changes data distribution structure, perform it in a test environment first. Collections with existing data or unique indexes must be checked against your MongoDB version's requirements. Creating the index in this example alone does not guarantee the workload is optimized.

### Compare queries with and without the shard key

~~~javascript
// Screen listing orders by tenant and time range:
db.orders.find({
  tenantId: "tenant-17",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  }
}).sort({ createdAt: -1 }).limit(50)

// Lookup by orderId without knowing the tenant:
db.orders.find({ orderId: "ORD-2026-000081" })
~~~

With the chosen shard key, the first query provides both the prefix and time range so `mongos` can narrow down the chunks to search. The second query lacks the shard key, risking hitting all shards.

Measure rather than guessing how many shards are accessed:

~~~javascript
db.orders.find({
  tenantId: "tenant-17",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  }
}).explain("executionStats")

db.orders.find({
  orderId: "ORD-2026-000081"
}).explain("executionStats")

sh.status()
db.orders.getShardDistribution()
~~~

In the `explain` output, examine the shards actually involved, the index plan used, `totalKeysExamined`, `totalDocsExamined`, and execution time. Output field structures may vary across versions and query types; inspect shard-related stages directly. `sh.status()` and `getShardDistribution()` help observe distribution state, but to conclude load balance you must combine CPU, IO, network, and latency metrics per shard.

### If testing the compound hashed option

The following is **an alternative design for testing**, not meant to overwrite the collection already sharded in the example above:

~~~javascript
// Example index preparation for a separate collection/experiment.
db.orders_candidate.createIndex({ tenantId: 1, orderId: "hashed" })

// Run only when the corresponding collection is not yet sharded
// and meets cluster prerequisites.
sh.shardCollection(
  "shop.orders_candidate",
  { tenantId: 1, orderId: "hashed" }
)
~~~

In this case, `{ tenantId: "tenant-17", orderId: "ORD-..." }` specifies a complete shard key value; a query with only `tenantId` can usually still be targeted via the prefix but may search multiple shards. Queries by `createdAt` will need a suitable index to reduce scanned documents on participating shards. Pay attention to unique key design if `orderId` must be unique; hashed indexes are not unique indexes.

## 6. Designing queries with Spring Data MongoDB

Spring Data MongoDB does not automatically add `tenantId` or a date range to queries simply because a collection is sharded. Developers must pass those fields according to business semantics.

Simple domain example:

~~~java
import java.math.BigDecimal;
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record Order(
    @Id String id,
    String tenantId,
    String orderId,
    Instant createdAt,
    String status,
    BigDecimal total
) {}
~~~

List query using `MongoTemplate`:

~~~java
import java.time.Instant;
import java.util.List;

import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class OrderQueryService {
    private final MongoTemplate mongoTemplate;

    public OrderQueryService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<Order> findOrders(
            String tenantId,
            Instant fromInclusive,
            Instant toExclusive,
            int requestedLimit) {
        int limit = Math.min(Math.max(requestedLimit, 1), 100);

        Query query = new Query(
                Criteria.where("tenantId").is(tenantId)
                        .and("createdAt").gte(fromInclusive).lt(toExclusive)
        );

        query.with(Sort.by(Sort.Direction.DESC, "createdAt"));
        query.limit(limit);
        return mongoTemplate.find(query, Order.class);
    }
}
~~~

Combining `tenantId` with `createdAt` enables the server to route using the chosen ranged shard key. Descending sort can leverage a reverse scan on a compatible index depending on the actual plan; still verify with `explain`. Limiting result count reduces transferred data, but does not fix fan-out if the filter lacks the shard key.

An equivalent repository declaration can look like:

~~~java
import java.time.Instant;
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository extends MongoRepository<Order, String> {
    List<Order> findByTenantIdAndCreatedAtGreaterThanEqualAndCreatedAtLessThan(
            String tenantId, Instant fromInclusive, Instant toExclusive);
}
~~~

The repository expresses business criteria; routing still happens in MongoDB. For APIs returning large sets, use pagination or an appropriate cursor/iteration mechanism and verify the actual query's index and sort behavior.

When updating or deleting an order, include known shard key values in the filter so the server can target accurately. Do not assume lookups by `_id` are always routed efficiently if `_id` is not part of the shard key.

## 7. Validating the choice before going to production

A shard key is only validated when tested against a workload with realistic distribution. Prepare a dataset with small, medium, and very large tenants, realistic order timestamps, and peak read/write ratios.

**Verify routing and latency:**

- Run `explain("executionStats")` on representative queries: by tenant/date, by orderId, reporting queries, and updates.
- Record participating shards, `totalKeysExamined`, `totalDocsExamined`, p50/p95/p99 latency, and the percentage of targeted requests.
- Compare query plans against existing indexes; avoid creating unnecessary indexes because indexes increase write cost and storage.

**Verify distribution and scalability:**

- Compare document counts, data size, index size, and growth rate across shards.
- Observe reads/writes per shard during peak hours; do not infer load balance from document counts alone.
- Add shards in a test environment to see how chunks redistribute, and whether any key range or tenant cannot be split small enough.
- Measure the impact of chunk migrations, the balancer, and long-running queries on application latency.

**Verify business constraints:**

- Test edge cases: largest tenant, missing/null values, legacy data, and `orderId` generation rules.
- Confirm unique index design, uniqueness scope of business codes, and `_id` generation strategy.
- Audit query paths from controller/service/repository so `tenantId` is not accidentally omitted in tenant-scoped data access.

If a candidate balances storage yet still produces high p99 write latency, adjust the shard key design or query shape. Changing the shard key once data has grown large can require resharding with significant operational cost, so plan ahead early.

## 8. Common mistakes and how to fix them

| Mistake | Consequence | Remedy |
| --- | --- | --- |
| Choosing `status` because it is filtered very often | Low cardinality; many documents share values and cannot be split | Use a field or compound key with better selectivity; keep a status index if needed |
| Choosing ranged `createdAt` because data always has timestamps | New writes pile onto the upper end of the shard key range | Evaluate a hashed key or compound key based on access patterns |
| Hashing `tenantId` and assuming large tenants will auto-split evenly | Same tenant value still maps to the exact same hash key position | Try a compound key that allows splitting within a tenant |
| Looking only at balanced storage size | A shard can run hot from high QPS even with modest data size | Also measure write/read throughput, CPU/IO, and latency |
| Adding an index on `orderId` and expecting single-shard queries | A secondary index speeds up local shard search, not mongos routing | Include the shard key in the API when possible, or re-evaluate strategy |
| Using a compound key but omitting the prefix field in queries | Queries easily fan out to multiple shards | Design queries around the shard key prefix and inspect `explain` |
| Choosing a shard key without checking unique constraints | Desired unique indexes may not be creatable | Define uniqueness requirements before finalizing the key |
| Adding a hashed suffix to every collection | Breaks locality for certain range queries; increases fan-out | Use only when distribution and write hotspots justify the trade-off |

## 9. Self-assessment scenario

A system has 20,000 tenants. Most tenants only have a few thousand orders, but the top 5 largest tenants account for 55% of total orders and 70% of writes. The primary read query is:

~~~javascript
db.orders.find({
  tenantId: "tenant-big-1",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  }
})
~~~

**Question:** Should you choose `{ tenantId: "hashed" }` or `{ tenantId: 1, orderId: "hashed" }`?

**Analysis hints:**

1. With `{ tenantId: "hashed" }`, all data of a single tenant still has one shard key value. The five largest tenants can continue to create storage skew and write load concentration.
2. With `{ tenantId: 1, orderId: "hashed" }`, keys of a large tenant can be split by orderId, providing an opportunity to better distribute writes and storage.
3. However, the tenant + date-range query lacks an orderId value, so it may have to read from multiple shards. An index on `{ tenantId: 1, createdAt: 1 }` remains helpful *inside* shards but does not eliminate fan-out.
4. A final decision should only be made after benchmarking with representative data and QPS, comparing listing query p95/p99, write hotspots, distribution, and operational cost.

If date-range queries are extremely latency-sensitive, you may need to reconsider business-level partitioning, API optimizations, or a separate reporting store. Never promise that a single shard key will simultaneously optimize every query type.

## 10. Design takeaways

Choosing a shard key starts with **value and traffic distribution**, continues with **actual query patterns**, and only then arrives at ranged, hashed, or compound hashed decisions. A high-cardinality key can still perform poorly if queries omit the key; a well-routed key can still perform poorly if writes pile onto one shard.

With Spring Data MongoDB, design service and repository filters to pass the full shard key when business logic allows, inspect plans on `mongos`, and monitor performance as data or shard count grows. A good decision is one you can justify with workload data, metrics, and validation results.
