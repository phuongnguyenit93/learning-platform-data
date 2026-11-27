# Range, Hashed Keys, Indexes, and Uniqueness Requirements

In **Spring Data MongoDB**, applications typically operate through `MongoTemplate` or repositories, while data distribution across shards is handled by the **MongoDB sharded cluster**. Choosing a shard key not only determines where documents are stored, but also directly affects query routing capability, write speed, index design, and which `unique` constraints the system can enforce.

This lesson belongs to the **Sharding** chapter, focusing on choosing between **range-based sharding** and **hashed sharding**, preparing appropriate indexes, and preserving uniqueness rules as the number of shards grows.

## 1. Learning objectives

After completing this lesson, you will be able to:

1. Distinguish the distribution mechanics of range and hashed shard keys, including when hotspots or scatter-gather occur.
2. Choose a shard key based on cardinality, write distribution, common queries, and scaling needs.
3. Create supporting indexes for the shard key before sharding a collection that already contains data.
4. Distinguish a `unique index` on an unsharded collection from uniqueness enforced **across the entire sharded cluster**.
5. Combine MongoDB configuration with `@Sharded` entities, `MongoTemplate`, and Spring Data repositories.
6. Verify your choices using `sh.status()`, `getIndexes()`, and `explain()`.

## 2. What does a shard key actually control?

A sharded collection is divided into **shard key value ranges**; each range is managed by the cluster and distributed to shards. The `mongos` router uses chunk distribution metadata together with query filters to locate shards that may hold matching data.

For example, an order document has the shape:

```javascript
{
  _id: ObjectId("66c000000000000000000001"),
  tenantId: "shop-a",
  orderNumber: "ORD-1001",
  createdAt: ISODate("2026-11-20T02:15:00Z"),
  totalAmount: 250000,
  status: "NEW"
}
```

You could choose `tenantId`, `createdAt`, `_id`, or a combination of fields as the shard key. No option is optimal for every workload. To evaluate properly, separate three questions:

- **Data distribution:** are key values distinct enough to create multiple data ranges and balance load?
- **Routing:** do queries supply conditions on the shard key so `mongos` can narrow down which shards to query?
- **Uniqueness:** does the system need to prevent duplicates per tenant or across the entire dataset?

A shard key is **not synonymous** with a primary key, nor is it automatically a unique index.

## 3. Range-based sharding vs. hashed sharding

### 3.1. Range-based: preserving value order

With an ascending shard key `{ createdAt: 1 }`, MongoDB divides contiguous ranges of `createdAt`. Nearby values tend to be placed in the same data range; these ranges can be migrated between shards.

```text
Increasing createdAt values
|---- older range ----|---- middle range ----|---- newer range ---->
       chunk A              chunk B               chunk C
          |                    |                     |
        shard 1              shard 2               shard 3
```

A major advantage is that **range queries** on the shard key can often target a narrower set of shards. For example, if the shard key includes an appropriate prefix, queries by `tenantId` and time can leverage both routing and indexes.

Risk arises when the shard key is **monotonically increasing**, such as a timestamp or sequence. Most new records fall into the highest range, causing the single chunk or shard holding that range to receive most writes. This is a **write hotspot**. Chunk migration can spread data over time, but it does not automatically turn a sequential write stream into an evenly distributed one instantaneously.

A shard key such as `{ tenantId: 1 }` can also become skewed when one tenant generates most traffic: all documents with the same `tenantId` share the same shard key value, so extra hashing or indexing at the application level will not split that tenant's load if the shard key remains `tenantId` alone.

### 3.2. Hashed: distributing by hash value

With the shard key `{ eventId: "hashed" }`, MongoDB computes a hash of the `eventId` value and splits the **hash value range** into chunks. The application does not compute or store this hash itself.

```text
Sequential eventId: E001 E002 E003 E004 E005 E006
                       |    |    |    |    |
                    MongoDB internal hash
                       |    |    |    |    |
hash range/chunk:      C3   C1   C4   C2   C1   C4
```

Numerically or chronologically adjacent values can land in different hash ranges. Thus, hashed sharding typically distributes writes with incrementing IDs better, provided the key has **high cardinality**.

In return, range queries like `eventId >= "E100"` no longer correspond to a contiguous hash range: the router usually must query multiple shards. **Equality queries on the full shard key**, such as `{ eventId: "E100" }`, can still be routed to the appropriate shard.

**Notes on hashing:**

- A hashed index is **not** a unique index; two values can hash similarly, and hashing does not enforce uniqueness.
- Hashed indexes do not support multikey fields: do not use an array field as a hashed field.
- Choosing a field with few distinct values, such as `status` with only a handful of states, will not produce good distribution merely by marking it `"hashed"`.
- MongoDB supports **compound hashed shard keys**, such as `{ region: 1, eventId: "hashed" }`; evaluate zone constraints and initial distribution separately when using compound keys.

### 3.3. Comparison table

| Criterion | Range shard key | Hashed shard key |
| --- | --- | --- |
| Partitioning method | By original value ranges | By hash ranges |
| Strengths | Workloads filtering/sorting by ranges and shard key prefixes | Spreading writes across high-cardinality fields, including incrementing values |
| Equality query on full key | Can be targeted | Can be targeted |
| Range query on key | Usually advantageous | Often must query multiple shards |
| Risks | Hotspots at the start/end of monotonic ranges, skewed distribution | Unsuitable for low-cardinality keys, loses range locality |
| `unique` on the key itself | Possible subject to sharded cluster rules | Cannot place `unique` on a hashed index or set `unique: true` on a hashed shard key |

Both strategies must be evaluated on **both reads and writes**. A log ingestion system may prefer a hashed key for even writes, whereas an application querying a customer's chronological history may prefer a compound/range key based on actual queries.

## 4. Choosing a shard key from the workload

Suppose a Spring Data MongoDB application serves multiple stores with these typical operations:

| Operation | Query filter | Requirement |
| --- | --- | --- |
| View a single order | `tenantId = ?` and `orderNumber = ?` | Fast lookup, order number unique within each tenant |
| List orders in a month | `tenantId = ?` and `createdAt BETWEEN ...` | Narrow routing, index supporting range |
| Record a new event | `eventId = ?` with time-increasing ID | Even write distribution |
| Look up an event | `eventId = ?` | Equality lookup |

You can design **two collections with two different shard keys**:

- `tenantOrders` uses range shard key `{ tenantId: 1 }` if the tenant count is large enough, per-tenant load is fairly balanced, and uniqueness is required on the pair `(tenantId, orderNumber)`.
- `events` uses hashed shard key `{ eventId: "hashed" }` if most writes and lookups are by `eventId`, while range queries are less important.

This is an illustrative configuration. With a few very large tenants, `tenantId` alone can become a hotspot; test an appropriate compound shard key or adjust data partitioning based on workload before deploying.

### 4.1. Questions to answer before creating a key

1. **Cardinality:** how many distinct shard key values exist, and does one value account for most documents?
2. **Query frequency:** what percentage of queries filter by the full shard key, a prefix, or no shard key at all?
3. **Write pattern:** does the shard key increase continuously, piling inserts at the end of the range?
4. **Stability:** is the shard key value updated often? Changing key values carries extra cost and operational conditions.
5. **Uniqueness:** is uniqueness required globally for a single field, or per combination prefixed by the shard key?
6. **Operations:** are you sharding an empty collection or one already containing substantial data and existing indexes?

Do not pick `_id` by default just because every document has it: evaluate whether that shard key fits your queries and the uniqueness guarantees you must protect.

## 5. Required indexes and query-serving indexes

A sharded collection requires an **index supporting the shard key**. For a compound shard key, the shard key must be a **prefix** of the supporting index; field order determines this.

Suppose the shard key is `{ tenantId: 1, createdAt: 1 }`:

```javascript
// Supports the shard key in the exact order
db.orders.createIndex({ tenantId: 1, createdAt: 1 });
db.orders.createIndex({ tenantId: 1, createdAt: 1, status: 1 });

// Cannot serve as supporting index for the shard key above
db.orders.createIndex({ createdAt: 1, tenantId: 1 });
db.orders.createIndex({ tenantId: 1 });
```

The `{ tenantId: 1 }` index can support some tenant queries, but it is **insufficient** as the supporting index for the entire compound shard key `{ tenantId: 1, createdAt: 1 }`.

Points to keep in mind when calling `sh.shardCollection()`:

- **Empty collection:** MongoDB can automatically create the shard key index if no suitable index exists yet.
- **Collection with existing documents:** you must create the shard key supporting index before sharding.
- You can create additional indexes for queries besides the shard key index, provided they meet sharded collection constraints (especially for `unique`).
- You cannot arbitrarily drop or hide the sole index supporting a shard key. Some MongoDB versions allow dropping a **hashed shard key index** under specific conditions, but doing so impacts balancing and queries; it is not a default optimization.

### 5.1. A shard key index is not enough to optimize every query

If a collection is sharded by `{ tenantId: 1 }`, the query:

```javascript
db.tenantOrders.find({
  tenantId: "shop-a",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  }
}).sort({ createdAt: -1 });
```

can be routed by `mongos` using `tenantId`, but an index containing only `tenantId` may not be efficient for filtering and sorting by `createdAt`. When the workload runs this query frequently, consider a secondary index:

```javascript
db.tenantOrders.createIndex({ tenantId: 1, createdAt: -1 });
```

Distinguish two responsibilities: **shard targeting** enabled by the shard key, and **query execution** inside the shard optimized by appropriate indexes. Measure with `explain("executionStats")` rather than assuming every query containing the shard key is fast.

## 6. Uniqueness in a sharded cluster

### 6.1. Why is there a "shard key as prefix" constraint?

A single shard can check documents stored on that shard locally. To guarantee a key combination is not duplicated **across the entire cluster**, all documents sharing that key combination must be routed to the same shard for verification.

Therefore, on a **ranged sharded collection**, MongoDB permits the following unique indexes:

1. A unique index directly on the shard key.
2. A unique compound index with the **entire shard key as its prefix**, in the exact order.
3. The default `_id` index, with an important exception explained below.

For example, a collection sharded by `{ tenantId: 1 }`:

| Index | Valid as a unique index? | Meaning |
| --- | --- | --- |
| `{ tenantId: 1 }` | Yes | At most one document per `tenantId`, usually unsuitable for an orders collection |
| `{ tenantId: 1, orderNumber: 1 }` | Yes | No duplicate `orderNumber` within each tenant |
| `{ tenantId: 1, email: 1 }` | Yes | No duplicate `email` within each tenant |
| `{ orderNumber: 1 }` | No | Missing shard key prefix |
| `{ orderNumber: 1, tenantId: 1 }` | No | Contains shard key, but wrong prefix order |

The index `{ tenantId: 1, orderNumber: 1 }` with `unique: true` guarantees the **pair of values** is unique. It does **not** require all `orderNumber` values across the entire cluster to be globally distinct. Two different tenants are allowed to both use `"ORD-1001"`.

If the shard key is `{ tenantId: 1, createdAt: 1 }`, the index `{ tenantId: 1, orderNumber: 1 }` **does not satisfy** the unique index requirement because it omits `createdAt` from the shard key. Adding `createdAt` to the unique index changes the meaning of uniqueness: documents with the same `tenantId` and `orderNumber` but different `createdAt` could then coexist. This is why **uniqueness requirements must be determined before finalizing the shard key**.

### 6.2. The `_id` field has an easily misunderstood exception

MongoDB creates a unique `_id` index by default. However, if a sharded collection uses a shard key **other than** `_id`, the default unique index on `_id` only enforces uniqueness **within each shard**; two documents with the same `_id` can still exist on two different shards.

Therefore:

- Generate sufficiently unique `_id` values from the application side, such as an independently generated ID with negligible collision probability.
- Do not interpret the presence of the `_id_` index as proof of global uniqueness under every shard key design.
- If the problem strictly requires global uniqueness for a business code across the system, design the shard key or write workflow with an appropriate enforcement mechanism.

### 6.3. Hashed keys do not support `unique: true`

Commands like the following are **invalid**:

```javascript
// Illustrative invalid commands — DO NOT run:
db.events.createIndex({ eventId: "hashed" }, { unique: true });
sh.shardCollection("shop.events", { eventId: "hashed" }, true);
```

MongoDB does not allow unique constraints on a **hashed index**, nor does it accept `unique = true` when the shard key is hashed.

You can address uniqueness with a separate identity-tracking collection or by changing the shard key model, but **never assume** that simply adding a regular unique index on the same field as a hashed shard key will make MongoDB enforce cluster-wide uniqueness. When designing a solution, account for all unique index constraints of sharded collections.

### 6.4. Other conditions to check

- When sharding a collection that already has unique indexes, those unique indexes must be compatible with the intended shard key; otherwise, sharding will fail.
- Once a collection is sharded, you cannot arbitrarily create a unique index lacking the shard key as a prefix.
- Unique indexes using collation require attention: enforcing uniqueness in a sharded cluster requires **simple collation** under MongoDB rules.
- Documents missing a field in a unique index can produce an index entry equivalent to `null`; standardize data, check for duplicates, and define a policy for optional fields.
- Setting `unique: true` in `sh.shardCollection()` (for a **ranged key**) requires a unique index **exactly on the shard key**, not merely a compound unique index with the shard key as a prefix.

## 7. Hands-on with `mongosh`

The commands below are for a **lab environment that already has a sharded cluster** and is connected to **`mongos`**. The two examples use separate collections so shard key choices do not mix.

### 7.1. Example A — Range key and per-tenant uniqueness

Problem: each tenant has many orders; `orderNumber` must be unique **within the tenant**.

```javascript
// Connect mongosh to mongos, then select the database
use shop

// 1. Create the collection and indexes before writing data
db.createCollection("tenantOrders");
db.tenantOrders.createIndex({ tenantId: 1 });
db.tenantOrders.createIndex(
  { tenantId: 1, orderNumber: 1 },
  { unique: true, name: "uk_tenant_order" }
);
db.tenantOrders.createIndex({ tenantId: 1, createdAt: -1 });

// 2. Shard the collection using a range shard key
sh.shardCollection("shop.tenantOrders", { tenantId: 1 });

// 3. Insert two orders belonging to two tenants
db.tenantOrders.insertMany([
  {
    tenantId: "shop-a",
    orderNumber: "ORD-1001",
    createdAt: ISODate("2026-11-20T02:15:00Z")
  },
  {
    tenantId: "shop-b",
    orderNumber: "ORD-1001",
    createdAt: ISODate("2026-11-20T02:16:00Z")
  }
]);

// 4. Test duplicate within the same tenant: expected E11000
db.tenantOrders.insertOne({
  tenantId: "shop-a",
  orderNumber: "ORD-1001",
  createdAt: ISODate("2026-11-20T02:17:00Z")
});
```

In this example:

- The first two documents are **valid** despite having the same `orderNumber` because they belong to different tenants.
- The final insert is expected to fail with `E11000 duplicate key` due to the duplicate `(tenantId, orderNumber)` pair.
- The shard key `{ tenantId: 1 }` serves as the prefix of the unique index `{ tenantId: 1, orderNumber: 1 }`.
- The unique index `uk_tenant_order` both protects the business rule and serves queries filtering by both fields; the timestamp index serves a different query pattern.

If the collection already contains data, **check for duplicates before creating a unique index**. Creating a unique index will fail if violating data already exists.

### 7.2. Example B — Hashed key for an event stream

Problem: the application continuously writes events with ascending IDs and often reads back a single event by ID.

```javascript
use shop

db.createCollection("events");
db.events.createIndex({ eventId: "hashed" });

// Hashed shard key: DO NOT pass unique=true
sh.shardCollection("shop.events", { eventId: "hashed" });

db.events.insertMany([
  { eventId: "E000001", kind: "ORDER_CREATED" },
  { eventId: "E000002", kind: "ORDER_PAID" },
  { eventId: "E000003", kind: "ORDER_SHIPPED" }
]);

db.events.findOne({ eventId: "E000002" });
```

A hashed key can help spread ascending inserts when the value set is wide enough. However, **this example does not provide a global unique constraint on `eventId`**. If strict duplicate prevention is needed, design an additional mechanism from the outset.

### 7.3. Example C — Seeing unique index restrictions clearly

With `shop.tenantOrders` already sharded on `{ tenantId: 1 }`, the following syntax **cannot be used to create a unique index**:

```javascript
// Illustrative invalid command — DO NOT run:
db.tenantOrders.createIndex(
  { orderNumber: 1 },
  { unique: true }
);

// You can create a regular index for queries,
// but it does NOT enforce uniqueness on orderNumber:
db.tenantOrders.createIndex({ orderNumber: 1 });
```

A **non-unique** index on `orderNumber` is valid for lookup needs, but queries without the shard key may have to be sent to multiple shards. Having an index on each shard does not by itself resolve routing overhead.

## 8. Connecting to Spring Data MongoDB

Spring Data MongoDB handles document mapping and query construction. **Creating the sharded cluster, choosing the actual shard key, and running `sh.shardCollection()` are MongoDB configuration operations**. Placing a Java annotation alone does not replace preparing indexes and sharding the collection on the server.

### 8.1. Entity using a ranged shard key

```java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Sharded;
import org.springframework.data.mongodb.core.mapping.ShardingStrategy;

@Document(collection = "tenantOrders")
@Sharded(shardKey = "tenantId", shardingStrategy = ShardingStrategy.RANGE)
public class TenantOrder {

    @Id
    private String id;

    private String tenantId;
    private String orderNumber;
    private Instant createdAt;
    private String status;

    // Constructor, getters, setters...
}
```

`@Sharded` describes the shard key on the entity and helps Spring Data append shard key conditions for **certain document replacement operations**. The annotation does not mean Spring Data automatically creates all required indexes or enables sharding on the cluster.

In repositories, express the shard key prefix in frequently used query methods:

```java
import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface TenantOrderRepository
        extends MongoRepository<TenantOrder, String> {

    Optional<TenantOrder> findByTenantIdAndOrderNumber(
            String tenantId, String orderNumber);
}
```

An explicit update query using `MongoTemplate`:

```java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public class TenantOrderService {

    private final MongoTemplate template;

    public TenantOrderService(MongoTemplate template) {
        this.template = template;
    }

    public void markPaid(String tenantId, String orderNumber) {
        Query query = Query.query(
            Criteria.where("tenantId").is(tenantId)
                    .and("orderNumber").is(orderNumber)
        );

        Update update = new Update().set("status", "PAID");
        template.updateFirst(query, update, TenantOrder.class);
    }
}
```

Including `tenantId` in the filter both clearly states business scope and helps `mongos` route better. For operations that require the shard key in the filter, **do not rely on `@Sharded` to automatically add the key to every query type**; Spring Data documentation only describes automatic inclusion in specific cases. Always verify actual generated commands and cluster behavior.

### 8.2. Entity using a hashed shard key

If choosing sharding by `eventId` for the events collection:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Sharded;
import org.springframework.data.mongodb.core.mapping.ShardingStrategy;

@Document(collection = "events")
@Sharded(shardKey = "eventId", shardingStrategy = ShardingStrategy.HASH)
public class EventDocument {

    @Id
    private String id;

    private String eventId;
    private String kind;

    // Constructor, getters, setters...
}
```

The Spring Data enum value is **`ShardingStrategy.HASH`**, whereas the MongoDB syntax in `mongosh` is **`"hashed"`**. They describe the same strategy, though they do not use the same keyword.

Indexes can be managed via deployment scripts, migrations, or `MongoTemplate.indexOps(...).ensureIndex(...)`. If relying on `@Indexed`/`@CompoundIndex` annotations, check your **automatic index creation** configuration, because that feature is not enabled automatically in every application and does not replace controlled migrations when production already holds data.

## 9. Inspecting the cluster and verifying results

After configuration, verify **schema/indexes**, **data constraints**, and **actual queries**.

### 9.1. Checking configuration and indexes

```javascript
use shop

sh.status();

db.tenantOrders.getIndexes();
db.events.getIndexes();
```

From `sh.status()`, locate the namespace, shard key, and corresponding partition info. From `getIndexes()`, confirm the key supporting index exists, has the right field order, has required `unique` flags, and did not accidentally attempt a unique hashed index (which would be rejected).

### 9.2. Inspecting `explain()` for common queries

```javascript
// Includes shard key: favorable for shard targeting
db.tenantOrders.find({
  tenantId: "shop-a",
  orderNumber: "ORD-1001"
}).explain("executionStats");

// Missing shard key: risks scattering the query
db.tenantOrders.find({
  orderNumber: "ORD-1001"
}).explain("executionStats");

// Equality on hashed key
db.events.find({
  eventId: "E000002"
}).explain("executionStats");

// Range on hashed key: may need to query multiple shards
db.events.find({
  eventId: { $gte: "E000001", $lt: "E000100" }
}).explain("executionStats");
```

When reading the output, note the number of shards queried, index-using stages, documents scanned, and processing time. `explain` formats can differ across MongoDB versions; evaluate actual output rather than hardcoding expectations for a single stage name.

### 9.3. Common error scenarios

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `shardCollection` reports missing index | Collection has data but lacks an index supporting the shard key | Create an index with all fields in the exact order before sharding |
| Cannot create unique index | Unique index lacks the shard key as prefix, or duplicate data exists | Redesign compatible constraints and clean up duplicates |
| Insert returns `E11000` | Duplicate combination of fields constrained by `unique` | Inspect the field values; return the proper business error |
| Continuous writes pile onto one shard | Monotonically increasing range key, or one key value is too "hot" | Consider hashed/compound keys and workload distribution |
| Query is slow despite existing index | Filter lacks shard key, index doesn't fit query shape, or multiple shards participate | Inspect `explain()` and redesign filters/indexes |
| Mistakenly assuming `_id` is cluster-wide unique | Shard key differs from `_id`; default index only checks per shard | Use a globally unique ID strategy and explicit global constraints |
| Using hashed key while still needing unique business code | Unique hashed indexes are not supported | Change shard key model or design a separate uniqueness mechanism |

## 10. A practical decision workflow

When starting a new collection:

1. **Write down data rules first:** for example, "`orderNumber` only needs to be unique within `tenantId`".
2. **List important queries:** equality, range, sort, updates, and actual frequencies.
3. **Estimate value distribution:** cardinality, large tenants, monotonicity, write rate.
4. **Select key and strategy:** range if preserving order benefits queries; hashed if spreading incrementing values and primarily performing equality lookups.
5. **Check validity of all existing unique indexes:** especially the prefix requirement on sharded collections.
6. **Create supporting and query indexes**, prepare data, then shard via `mongos`.
7. **Test duplicates, inspect `explain()`, and review cluster stats** on a representative dataset before going live.

**Three principles to remember:** range fits when range locality matters; hashed fits when write distribution is the priority and the key is sufficiently distinct; uniqueness on a sharded collection must be designed alongside the shard key from the start. Choosing poorly here is usually much harder to fix than adding a query index later.

## References

- MongoDB Manual — [Shard Keys](https://www.mongodb.com/docs/manual/core/sharding-shard-key/)
- MongoDB Manual — [Hashed Sharding](https://www.mongodb.com/docs/manual/core/hashed-sharding/)
- MongoDB Manual — [Shard Key Indexes](https://www.mongodb.com/docs/manual/core/sharding-shard-key-indexes/)
- MongoDB Manual — [Maintain Uniqueness in Sharded Clusters](https://www.mongodb.com/docs/manual/tutorial/maintain-uniqueness-in-sharded-clusters/)
- MongoDB Manual — [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- Spring Data MongoDB — [`@Sharded` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/Sharded.html)
- Spring Data MongoDB — [`ShardingStrategy` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/ShardingStrategy.html)
