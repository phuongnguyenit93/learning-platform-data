# Targeted Queries, Scatter-Gather, and Latency Impact

## 1. Why can the same query be fast on one cluster yet slow on another?

When MongoDB uses **sharding**, documents of a collection are distributed across multiple shards based on the **shard key**. Applications connect through `mongos`; the router decides which shards need to receive a query by matching filter conditions against chunk distribution metadata.

Two queries returning the exact same document can generate vastly different load:

~~~javascript
// Tenant containing the order is known.
db.orders.findOne({ tenantId: "tenant-17", orderId: "ORD-081" })

// Only the order ID is known.
db.orders.findOne({ orderId: "ORD-081" })
~~~

Suppose the collection is sharded by `{ tenantId: "hashed" }`. The first query can be routed to a single shard because `mongos` knows the shard key value. The second query omits the shard key and therefore may have to be sent to all shards, even though only one document exists in the result.

That is the difference between a **targeted query** and **scatter-gather**. Routing behavior affects the number of network requests, per-shard work, result merging, and end-user latency.

In **Spring Data MongoDB**, both `MongoTemplate` and repositories build queries sent to MongoDB. The framework does not automatically supply a missing shard key: the filter constructed by the application determines how effectively routing works. This lesson connects query design with data distribution, indexes, and performance diagnostics.

## 2. Query path inside a sharded cluster

A MongoDB sharded cluster typically includes:

- **Shards:** store a subset of data; usually each shard is a replica set.
- **Config servers:** store cluster configuration and chunk distribution metadata.
- **`mongos`:** query routing gateway, using cluster metadata to identify which shards to contact.
- **Application:** sends find, update, and aggregation commands to `mongos` via a MongoDB driver, such as Spring Data MongoDB.

~~~mermaid
flowchart TD
    A["Spring Data MongoDB / MongoDB Driver"] --> B["mongos: inspect filter and shard key"]
    B --> C{"Can data scope be narrowed?"}
    C -->|Yes| D["Target one shard or a subset of shards"]
    C -->|No| E["Send to all relevant shards"]
    D --> F["Execute on selected shard"]
    E --> G["Execute in parallel across shards"]
    F --> H["mongos returns results"]
    G --> I["Merge results, possibly sort/limit"]
    I --> H
~~~

`mongos` does not scan individual documents to learn where keys live. It uses shard key range information associated with chunks; for a **hashed shard key**, the key value is hashed before locating the corresponding range. Metadata and chunk layout can change as the balancer moves data, while the application keeps sending queries through the same interface.

**Distinguish two optimization layers:**

1. **Query routing:** how many shards `mongos` selects to receive the command.
2. **Query execution:** inside each shard, which index the query planner uses, how many keys/documents it scans, and whether in-memory sorting is required.

A query **targeting a single shard** can still be slow if it lacks an index or scans millions of documents. Conversely, a scatter-gather over a tiny dataset may finish quickly, yet its cost and tail latency become much harder to control as shard count and load grow.

## 3. Targeted query, single-shard query, and scatter-gather

| Pattern | What does `mongos` do? | Example when shard key is `{ tenantId: "hashed" }` |
| --- | --- | --- |
| **Single-shard targeted query** | Routes to the exact shard holding the requested shard key value | `{ tenantId: "tenant-17" }` |
| **Multi-shard targeted query** | Routes to a subset of shards determined from the shard key | `{ tenantId: { $in: ["tenant-17", "tenant-24"] } }` if the two values live on different shards |
| **Scatter-gather** | Broadcasts the query to all shards that must be searched when the filter cannot narrow the shard key | `{ orderId: "ORD-081" }` or `{ status: "PAID" }` |

In an eight-shard cluster, a targeted query might need one, two, or several shards. **Targeted does not mean single-shard.** Conversely, scatter-gather means `mongos` must search broadly, even if only one shard actually holds a matching document.

Routing accuracy depends simultaneously on **shard key type**, **field order of a compound shard key**, **filter operators**, and **chunk placement** at execution time.

### 3.1. When the shard key is a single hashed field

Suppose the collection is sharded by:

~~~javascript
{ tenantId: "hashed" }
~~~

Common cases:

~~~javascript
// A. Equality on the full shard key: usually goes to one shard.
db.orders.find({ tenantId: "tenant-17" })

// B. Equality on the shard key plus extra conditions:
// still capable of routing to a single shard.
db.orders.find({ tenantId: "tenant-17", status: "PAID" })

// C. Multiple shard key values: may hit multiple shards,
// though not necessarily all shards.
db.orders.find({ tenantId: { $in: ["tenant-17", "tenant-24"] } })

// D. Missing shard key: risks scatter-gather.
db.orders.find({ orderId: "ORD-081" })

// E. Range query on the raw values of a hashed key:
// does not benefit from range-based routing.
db.orders.find({ tenantId: { $gte: "tenant-10", $lt: "tenant-20" } })
~~~

A hashed shard key helps distribute **distinct key values**. It does not automatically split a dataset sharing the **same key value**, such as one very large tenant; this is a trade-off to weigh when designing multi-tenant systems.

### 3.2. When the shard key is a ranged compound key

Suppose another collection uses the shard key:

~~~javascript
{ tenantId: 1, createdAt: 1 }
~~~

Here `tenantId` is the **prefix** of the shard key, followed by `createdAt`. Filter shape determines the chunk scope accessed:

| Filter | Routing capability | Explanation |
| --- | --- | --- |
| `tenantId = t AND createdAt = d` | Can pinpoint a single point in the key space | Filter supplies a full compound key value |
| `tenantId = t AND createdAt >= d1 AND createdAt < d2` | Targets the tenant's chunks in the date range | A wide range may span multiple shards |
| `tenantId = t` | Targets chunks belonging to that tenant | May hit multiple shards if the tenant's data spans multiple chunks |
| `createdAt >= d1 AND createdAt < d2` | Usually must scan many or all shards | Missing the `tenantId` prefix |
| `status = "PAID"` | Usually scatter-gather | Unrelated to the shard key |

There is no rule that "having any one field of the shard key is enough." For a compound shard key, conditions on an **appropriate prefix** generally help `mongos` narrow down better than conditions only on trailing fields. Large key ranges can touch multiple chunks and shards even when the filter includes the shard key.

### 3.3. Cases requiring caution

- **`_id`:** querying by `_id` does not default to targeting one shard if `_id` is not the shard key or does not identify the shard key.
- **`$or`:** if one branch cannot be narrowed using the shard key, routing for the entire query can widen; always verify with `explain`.
- **Aggregation:** an early `$match` containing a shard key condition, pushed down appropriately by the optimizer, can reduce participating shards. Other stages like `$group`, `$sort`, or `$lookup` can still incur distributed work and merging.
- **Secondary indexes:** an index on `orderId` helps each shard search faster, but does not tell `mongos` which shard holds the document if the query lacks the shard key.

## 4. Practice: creating a collection and observing routing

The example below assumes an existing **sharded cluster**, a connection to `mongos`, and the `shop` database. In production, enabling sharding or changing a shard key requires a dedicated operational procedure; run hands-on experiments on a test cluster.

### 4.1. Preparing data and indexes

A sample document:

~~~javascript
{
  _id: ObjectId("66aa00000000000000000001"),
  tenantId: "tenant-17",
  orderId: "ORD-081",
  createdAt: ISODate("2026-11-12T09:30:00Z"),
  status: "PAID",
  total: NumberDecimal("1290000")
}
~~~

Example shard key setup:

~~~javascript
use shop

// Hashed index to support the hashed shard key.
db.orders.createIndex({ tenantId: "hashed" })

// Execute via mongos, on a collection meeting the sharding/index
// prerequisites of your MongoDB version.
sh.shardCollection("shop.orders", { tenantId: "hashed" })

// Secondary index for tenant, date range, and sort filtering.
db.orders.createIndex({ tenantId: 1, createdAt: -1 })
~~~

The `{ tenantId: 1, createdAt: -1 }` index supports common search/sort patterns **inside the selected shard**. This index does not alter the collection's shard key. Unique index constraints, especially with hashed keys, must be evaluated before applying to real data.

### 4.2. Comparing queries

~~~javascript
// Query 1: has equality on the hashed shard key.
db.orders.find({
  tenantId: "tenant-17",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  }
}).sort({ createdAt: -1 }).limit(50)

// Query 2: has orderId, lacks tenantId.
db.orders.find({ orderId: "ORD-081" })

// Query 3: filters paid orders system-wide.
db.orders.find({ status: "PAID" }).limit(50)
~~~

In this configuration, query 1 typically targets one shard; queries 2 and 3 omit the shard key and usually scatter-gather. `limit(50)` caps the number of returned results, but **does not prove** only one shard was accessed.

### 4.3. Using `explain` to verify

~~~javascript
// Measure query with the shard key.
db.orders.find({
  tenantId: "tenant-17",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  }
}).sort({ createdAt: -1 }).limit(50)
  .explain("executionStats")

// Measure query missing the shard key.
db.orders.find({
  orderId: "ORD-081"
}).explain("executionStats")
~~~

When reading `explain` from `mongos`, inspect:

1. **Participating shards list:** look at the shard-related plan details to see whether it hit one shard, a subset of shards, or all shards.
2. **Index and plan:** check whether the query uses `IXSCAN` or `COLLSCAN`; watch for sort and merge stages if present.
3. **Scan volume:** check `totalKeysExamined`, `totalDocsExamined`, and returned result count; aggregate totals may span multiple shards.
4. **Timing:** compare `executionTimeMillis` with end-to-end application measurements; `explain` timing does not replace production latency benchmarks.

Stage names and JSON structures in `explain` can vary by MongoDB version and query type. Do not write monitoring tools tightly coupled to an unverified JSON path on your real cluster.

You can observe distribution status with:

~~~javascript
sh.status()
db.orders.getShardDistribution()
~~~

Balanced storage distribution **does not guarantee** balanced request counts or latency. Additional metrics from individual shards and `mongos` are needed.

## 5. How does scatter-gather increase latency?

During scatter-gather, `mongos` dispatches a query to multiple shards, waits for the required responses, and merges the results. For queries that must wait for all shards, you can approximate it mentally as:

\[
T_{\text{request}}
\approx T_{\text{routing}} +
\max_i(T_{\text{network},i} + T_{\text{execution},i}) +
T_{\text{merge}} + T_{\text{return}}
\]

This is a **mental model**, not an exact timing formula for every command. Some queries can return early, cap results, or process batch-by-batch; actual time also depends on queues, sorting, fetching, result size, and pipeline structure.

Nevertheless, the formula highlights four primary sources of overhead.

### 5.1. Fan-out increases request counts and resource contention

With N shards, a targeted query sent to one shard generates one primary execution stream. Scatter-gather can hit N shards, consuming more sockets, CPU, IO, and cursor management overhead. Under high concurrency, fan-out amplifies cluster-wide load.

Illustrative example: a system has 12 shards and receives 800 queries/second lacking the shard key. One query can fan out to 12 shards, creating up to roughly **9,600 shard executions/second** for this query group alone, before counting secondary commands or extra batches. This is an estimate of **work amplification**, not an actual measurement or a claim that every shard scans its entire dataset.

### 5.2. Tail latency depends on the slowest shard

If a query must gather results from all shards, a single shard slowed down by disk IO, CPU, queuing, or network issues can drag out the entire response time. As the number of participating shards rises, the probability of hitting at least one slow shard can also rise.

In an idealized model, if the probability of each shard being slow is `p`, shards are independent, and the query waits for all of them, the probability of encountering **at least one slow shard** among `N` shards is:

\[
P(\text{at least one slow shard}) = 1 - (1-p)^N
\]

For instance, `p = 1%` and `N = 8` yields roughly 7.7%. This is only a qualitative illustration of *tail latency*: real shards can suffer from correlated causes, share dependencies, and not every query waits for every shard. Do not use this formula as an SLA predictor.

### 5.3. Merging, sorting, and pagination consume extra resources

For distributed find queries, `mongos` may need to merge cursors and results from multiple shards. With sorting or aggregation, distributed execution depends on the query plan:

- Certain filter/sort steps can be pushed down to the shards.
- The merge portion may run on `mongos` or a designated merge shard depending on pipeline and version.
- Grouping, large-scale sorts, or blocking pipeline stages can consume substantial memory, IO, or time before producing the final output.

`limit` reduces result size, but does not automatically eliminate work across all shards. With pagination using a large `skip`, each shard may still need to process many records before mongos merges them; evaluate keyset pagination where appropriate.

### 5.4. Targeted queries are not always fast either

A targeted query can still be slow if one shard holds an oversized tenant or becomes a **hot shard**. Adding more shards does not automatically split records sharing the same shard key value. Missing indexes, excessive document scans, locks, and IO contention still need separate remediation.

Therefore, performance evaluation must measure **both the number of targeted shards and execution efficiency on each shard**.

## 6. Writing well-routed queries with Spring Data MongoDB

### 6.1. Domain and query patterns

Suppose `shop.orders` is sharded by `{ tenantId: "hashed" }`. Domain definition:

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

Listing queries by tenant and time range:

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

    public List<Order> listOrders(
            String tenantId,
            Instant fromInclusive,
            Instant toExclusive) {
        Query query = new Query(
            Criteria.where("tenantId").is(tenantId)
                .and("createdAt").gte(fromInclusive).lt(toExclusive)
        );

        query.with(Sort.by(Sort.Direction.DESC, "createdAt"));
        query.limit(50);
        return mongoTemplate.find(query, Order.class);
    }

    public List<Order> listByStatusAcrossTenants(String status) {
        // Missing tenantId: may scatter-gather.
        return mongoTemplate.find(
            Query.query(Criteria.where("status").is(status)),
            Order.class
        );
    }
}
~~~

With the hashed shard key `tenantId`, `listOrders` supplies an equality condition and thus has a basis to target one shard. `listByStatusAcrossTenants` fits system-wide aggregation tasks when data across all tenants is genuinely needed, but anticipate fan-out cost and avoid calling it frequently on latency-sensitive API paths.

### 6.2. Repository methods must also include the shard key

~~~java
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository extends MongoRepository<Order, String> {
    // Includes tenantId: helps mongos route using the assumed shard key.
    List<Order> findByTenantIdAndOrderId(
        String tenantId, String orderId);

    // Only orderId: may scatter-gather if tenantId is unknown.
    List<Order> findByOrderId(String orderId);
}
~~~

The repository method name does not determine shard count. The MongoDB filter generated by Spring Data is the routing basis. When designing APIs, pass a verified `tenantId` from the user context down to the query layer whenever business semantics allow, while enforcing authorization independently of sharding.

**Note on `findById`:** `MongoRepository.findById(id)` typically filters on `_id`. If the shard key is `tenantId`, this operation does not automatically target the right shard. For tenant-scoped operations, use a method taking `tenantId + orderId` or a query specifying both tenant and ID.

### 6.3. Capturing `explain` for application-generated queries

During performance investigations, you can run an equivalent `explain` command through `MongoTemplate`:

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;

Document find = new Document("find", "orders")
    .append("filter", new Document("tenantId", "tenant-17"));

Document explain = mongoTemplate.executeCommand(
    new Document("explain", find)
        .append("verbosity", "executionStats")
);
~~~

This snippet illustrates invoking the command; in real applications, enable `executionStats` only in controlled diagnostic workflows, targeting the right database, filter, and permissions. Avoid dumping full explain outputs or sensitive data into public logs. You can also use `mongosh` to quickly verify the same query.

## 7. Measuring and remediating when scatter-gather slows the system

You cannot diagnose the root cause from a single `executionTimeMillis` number. Measure under the same workload and inspect the full path.

### Step 1: Capture the query shape from the application

For each slow query, identify:

- Collection, filter, projection, sort, limit, aggregation stages, and index hints (if any).
- Frequency, concurrency, read/write ratio, and p50/p95/p99 latency.
- Is the full shard key present, or are fields missing? Is the filter equality, range, or `$in`?
- Result size, scanned documents/keys, and data proportion of large tenants.

### Step 2: Check routing with `explain`

Run with representative data and filter values:

~~~javascript
// Query containing the shard key value.
db.orders.find({
  tenantId: "tenant-17",
  orderId: "ORD-081"
}).explain("executionStats")

// Query missing the shard key.
db.orders.find({
  orderId: "ORD-081"
}).explain("executionStats")
~~~

The two queries have different business criteria; here they are used to **compare routing behavior**, not as a pure speed benchmark. To measure real benefit, validate correctness on the expected dataset while controlling for cache effects, background load, and indexes.

### Step 3: Identify the bottleneck

| Observation | Possible cause | What to try |
| --- | --- | --- |
| Almost all shards receive the query, each processing little data | Missing shard key causing fan-out | Add shard key conditions where business logic permits |
| Only one shard receives the query, yet p99 remains high | Hot shard, missing index, or overloaded resources | Inspect indexes, tenant skew, CPU/IO, and contention |
| Each shard scans many documents; `docsExamined` is large | Unsuitable filter/index | Design indexes supporting filter, sort, and projection |
| `mongos` or merge phase takes significant time | Distributed merge/sort/aggregation | Push filters early, trim returned fields, optimize pipeline |
| Latency rises when adding shards despite less data per shard | Fan-out overhead, tail latency, network | Reduce participating shards; measure network and latency percentiles |
| Data size is balanced, yet one shard is always busy | Skewed QPS distribution by key | Re-evaluate shard key and workload distribution |

### Step 4: Validate fixes in a representative environment

Evaluate changes based on fit with business requirements:

1. **Fix API/queries:** pass known shard keys; place appropriate `$match` stages in aggregations; avoid ID-only lookups without tenant when design permits.
2. **Optimize indexes:** add indexes for frequent queries on target shards; re-measure `keysExamined/docsExamined` rather than checking only for `IXSCAN`.
3. **Reduce merge work:** narrow datasets early, select minimal projections, optimize sorting and pagination; for system-wide reports, consider dedicated pre-aggregated data.
4. **Reassess shard key design:** if most critical queries cannot carry the shard key, evaluate a better key strategy or resharding through operational procedures.
5. **Track results:** compare participating shards, throughput, p50/p95/p99, and resource usage before/after across multiple time windows.

Do not change the shard key solely because one uncommon query fans out. Weigh the combined cost of reads, writes, large-tenant skew, uniqueness, and periodic background queries.

## 8. Misconceptions that lead to wrong optimizations

| Misconception | Reality |
| --- | --- |
| "If an index exists, `mongos` knows which shard holds the document." | Shard indexes aid execution inside a shard; routing still relies primarily on the shard key and distribution metadata. |
| "The query returns one document, so it only runs on one shard." | Few results do not mean a query targeted a single shard. |
| "`findById` is always fastest on a sharded collection." | If `_id` is not the shard key, lookups by `_id` can fan out. |
| "Adding `limit(1)` eliminates scatter-gather." | `limit` can reduce result size/work, but does not conjure a missing shard key. |
| "A query with `tenantId` definitely targets one shard." | Depends on the shard key; with a ranged compound shard key, one tenant may span multiple shards. |
| "Scatter-gather is always slower than every targeted query." | Latency depends on data size, cache, indexes, load balance, and merge; fan-out mainly increases cost and tail latency risk. |
| "More shards always make a query faster." | Adding shards can increase target count and merge cost if queries lack proper routing. |
| "Adding `shardKey` to the Java entity is enough." | Query filters must actually carry shard key conditions; mapping annotations do not fix queries missing the key. |

## 9. Analysis exercise

A `payments` collection is sharded by `{ merchantId: 1, createdAt: 1 }`. The API has three query types:

~~~javascript
// A. Weekly transaction report for a merchant.
db.payments.find({
  merchantId: "m-007",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-11-08T00:00:00Z")
  }
})

// B. Look up a single transaction by payment ID only.
db.payments.find({ paymentId: "P-88015" })

// C. List all transactions across the entire system for the week.
db.payments.find({
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-11-08T00:00:00Z")
  }
})
~~~

**Determine:** which query has a strong basis for targeting, and which ones tend to scatter-gather? Does adding an index `{ paymentId: 1 }` for B make B target a single shard? If merchant `m-007` has huge data volume, is A guaranteed to hit only one shard?

**Solution guide:**

- **A** uses the `merchantId` prefix and `createdAt` range, so `mongos` can narrow down the chunks to access. If that key range spans multiple shards, A must still contact multiple shards.
- **B** lacks the shard key and therefore risks scatter-gather. An index on `paymentId` speeds up lookup on *each queried shard*, without telling `mongos` the exact target shard.
- **C** lacks the `merchantId` prefix; chunks for many merchants may hold transactions from that time window, so the query typically searches widely across the cluster.
- For a very large merchant, data for the same merchant across different time intervals can live on multiple chunks/shards. **Targeted A does not guarantee single-shard execution.**

When applying findings to a real project, run `explain("executionStats")` via `mongos`, then measure application p95/p99 under near-production load. The metrics that matter most are **how many shards each query hits, how much work each shard performs, and how overall request response time changes**.
