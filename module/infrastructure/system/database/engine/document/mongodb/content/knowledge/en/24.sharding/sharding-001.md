# Distinguishing Sharding, Replication, and Business Partitioning in MongoDB

## 1. Why distinguish these three concepts?

An application storing orders for thousands of stores may start with a single MongoDB server. As data and traffic grow, engineering teams often hear three proposals:

1. **“Add a replica set so the system does not stop when one machine fails.”**
2. **“Shard the orders collection to distribute data and write load across multiple machines.”**
3. **“Partition data by tenant or by year to make business management easier.”**

All three relate to how data is organized, but they **solve different problems**. Confusing them can cause a system to incur extra infrastructure costs without actually scaling write throughput, or have multiple copies without genuinely distributing data.

This lesson belongs to MongoDB’s **Sharding** chapter and helps you distinguish:

- **Replication:** creating and synchronizing multiple copies of the **same dataset** to increase availability and resilience.
- **Sharding:** splitting **a logical dataset** into multiple physical subsets stored across **different shards** to scale capacity and distribute load.
- **Business partitioning:** dividing data according to a rule **defined by the business domain and application**, such as `tenantId`, region, fiscal year, or customer group; this division **may or may not** result in physical separation across multiple machines.

After this lesson, you will be able to explain how MongoDB combines sharding with replica sets, distinguish a shard key from a business partitioning key, choose a strategy for multi-tenant systems, and avoid pitfalls around fault tolerance, consistency, query routing, and operational cost.

> **First principle:** **Replication duplicates**, **sharding distributes**, and **business partitioning defines data boundaries by domain**. A system can certainly use **all three at the same time**.

## 2. Quick comparison table

| Criterion | Replication | Sharding | Business Partitioning |
| --- | --- | --- | --- |
| Primary question | “If a node fails, is there a copy to continue?” | “How can a large collection use resources from multiple shards?” | “Which tenant, year, region, or business unit does the data belong to?” |
| Mechanism | Replica set and oplog replication | Shard key, chunks/ranges, `mongos`, balancer | Domain rules; filters, separate collections/databases/clusters, application-level routing |
| Data distribution | Data-bearing members hold the **same replica set dataset** | Each shard holds a **portion** of the sharded collection | Design-dependent: may be in the same collection or stored separately |
| Physical duplicates | Has copies of the same data | Not every shard holds the entire collection by default | May have no duplicates; depends on backup/replica setup |
| Fault tolerance | Core objective | Requires a replica set on each shard to tolerate member failures | Does not inherently provide HA |
| Scaling total logical data capacity | Not the primary goal | Yes, add shards to distribute data | Only when partitions are actually placed on infrastructure with additional capacity |
| Scaling write throughput | Does not allow multiple primaries to write to the same dataset concurrently | Possible, if the shard key distributes writes | Possible when partitions write to independent infrastructure |
| Scaling reads | Can read from secondaries with consistency trade-offs | Can distribute queries across shards | Depends on routing and infrastructure |
| Routing | Driver discovers primary/secondaries | `mongos` decides target shards based on metadata | Application/middleware decides which tenant or partition |
| Common pitfall | Assuming more replicas means logical capacity scales proportionally | Choosing a shard key that causes hotspots/scatter-gather | Having `tenantId` and assuming data is already physically separated |

These columns do not mean one mechanism is “better.” They are **complementary, non-interchangeable** design axes.

## 3. Visualized: three ways to organize one million orders

Suppose the `orders` collection has **1,000,000 documents**.

### 3.1. Replication: three nodes holding the same dataset

~~~text
                   Replica set rsOrders
                     (1 million orders)
                            |
            +---------------+---------------+
            |               |               |
       +----------+    +----------+    +----------+
       | PRIMARY  |    | SECONDARY|    | SECONDARY|
       | 1 million|    | 1 million|    | 1 million|
       +----------+    +----------+    +----------+
            |               ^               ^
            +---------------+---------------+
                 Oplog replication
~~~

In a typical configuration, **each data-bearing member** holds a copy of the entire replica set dataset. There are three physical copies for recovery when a member fails; **not three million distinct orders**.

If all writes still go to **a single primary**, adding secondaries **does not automatically triple write capacity**. Secondaries can serve reads if the read preference allows it, but they may return stale data due to replication lag.

### 3.2. Sharding: splitting the dataset into multiple parts

~~~text
                     Sharded collection
                    1,000,000 orders
                            |
                          mongos
                 +----------+----------+
                 |          |          |
                 v          v          v
             +--------+ +--------+ +--------+
             |Shard A | |Shard B | |Shard C |
             |~330k   | |~340k   | |~330k   |
             +--------+ +--------+ +--------+
                       Data distribution
~~~

The numbers in the diagram are only an **illustration** of a relatively even distribution, not a ratio MongoDB guarantees automatically.

Each shard stores a **subset** of the documents in the sharded collection. `mongos` receives queries from the application and decides which shards to route them to based on the shard key and routing metadata.

### 3.3. Business partitioning: splitting by tenant

~~~text
                 1,000,000 orders
                         |
                  tenantId in each
                  document/write path
                         |
              +----------+----------+
              |          |          |
          Tenant A    Tenant B    Tenant C
          600,000     300,000     100,000
              |          |          |
              +----------+----------+
                Same orders collection
                is completely possible!
~~~

If all documents still reside in **a single collection on one replica set**, having `tenantId` **is not yet physical sharding**. It is **logical partitioning by business domain**.

Conversely, you can place each tenant in a separate database, or map tenants to separate clusters. In that case, business partitioning can lead to **physical isolation**, but the routing and migration mechanisms are determined by the application architecture.

## 4. Replication in MongoDB

### 4.1. What does a replica set consist of?

A replica set typically has:

- **Primary:** receives normal write operations.
- **Secondary:** replicates the oplog from the primary and applies changes to its own copy.
- **Election:** when the primary becomes unavailable, eligible members elect a new primary.
- **Oplog:** operations log used for synchronization.
- **Read preference:** allows selecting primary or secondary for reads according to policy.

Failover diagram:

~~~text
Normal                      After A is lost
-----------                 ---------------
A = primary                 A = unavailable
B = secondary               B = new primary (if elected)
C = secondary               C = secondary
~~~

During an election, some reads/writes may temporarily fail; the application must handle reconnects/retries according to driver and operation semantics.

### 4.2. Which problems does replication solve?

**Availability:** When one member fails while a majority of voting members and an eligible secondary remain, the replica set can elect a new primary.

**Data redundancy:** Multiple copies of the dataset exist across data-bearing members. A single disk failure does not necessarily cause data loss for the entire replica set.

**Certain read needs:** Read preference can be configured to route queries that are not strictly sensitive to freshness to secondaries.

**Maintenance:** A replica set supports more planned maintenance/upgrade operations than a standalone instance, though downtime, elections, and write concern must still be considered.

### 4.3. What does replication not solve?

Replication **does not by itself**:

- Split a 5 TB collection into 1–2 TB per machine.
- Create three primaries that independently accept writes for the same dataset.
- Protect against accidental deletes or application bugs: valid deletes on the primary can be replicated.
- Replace backups, point-in-time recovery, or disaster recovery plans.
- Guarantee that secondaries always have the latest write.
- Guarantee that writes acknowledged at a low write concern level will never roll back during failover.

An **Arbiter** only participates in voting/elections and does not hold a copy of the data; three members consisting of two data-bearing members and one arbiter **do not equal three data copies**.

### 4.4. Read preference example

~~~javascript
// Example in mongosh connected to a replica set.
db.getMongo().setReadPref("primary");
db.orders.find({ status: "PAID" }).limit(10).toArray();

db.getMongo().setReadPref("secondaryPreferred");
db.orders.find({ status: "PAID" }).limit(10).toArray();

// Restore default.
db.getMongo().setReadPref("primary");
~~~

`secondaryPreferred` prefers reading from secondaries but can fall back to the primary. Because replication is asynchronous, secondary results may not include recent writes.

**Do not use a secondary read as the decision step for a sensitive write** such as “if stock > 0 then decrement stock” without an atomic condition in the update operation itself.

## 5. Sharding in MongoDB

### 5.1. Sharding distributes data at the collection level

Sharding allows a sharded collection to distribute its documents across multiple **shards**. One shard holds only **a portion** of that collection’s data; the union of the shards forms the collection’s logical data.

MongoDB sharding works based on a **shard key**. Ranges of shard key values are divided into **chunks** (or ranges) and assigned to shards. The balancer can move ranges between shards according to distribution and zone policies.

Example orders collection document:

~~~javascript
{
  _id: ObjectId("..."),
  tenantId: "tenant-a",
  orderId: "ORD-1001",
  createdAt: ISODate("2026-11-01T08:00:00Z"),
  total: NumberDecimal("250.00")
}
~~~

You can choose the shard key `{ tenantId: 1, orderId: 1 }` or another shard key, depending on key distribution and query patterns. There is no single best shard key for every system.

### 5.2. Three components of a sharded cluster

A MongoDB sharded cluster has the following components:

1. **Shard:** stores a subset of sharded data. In current versions, each shard must be deployed as a **replica set**.
2. **`mongos`:** query router that receives commands from applications, routes them to the appropriate shards, and merges/returns results when needed.
3. **Config servers:** store metadata about collections, shards, chunk ranges, and routing. Config servers are deployed as a replica set (**CSRS**). Starting in MongoDB 8.0, a **config shard** can be used to combine the config server role with storing application data in supported configurations.

Practical combined architecture diagram:

~~~text
                       Application
                            |
                            v
                       mongos router
                       /           \
         +------------+             +------------+
         |                                       |
         v                                       v
     Shard A                                 Shard B
   replica set                             replica set
 +----------------+                      +----------------+
 | primary A1     |                      | primary B1     |
 | secondary A2   |                      | secondary B2   |
 | secondary A3   |                      | secondary B3   |
 +----------------+                      +----------------+
   | subset A |                             | subset B |
         ^                                       ^
         |                                       |
         +--------------+------------------------+
                        |
                Config metadata
                 config servers
                   (CSRS)
~~~

**This is the most important example:** Sharding and replication **coexist**. Replication ensures multiple copies **of each shard**, while sharding distributes **different data subsets across shards**.

### 5.3. Primary shard is not a replica set primary member

In MongoDB, the term **primary** can refer to two different concepts:

- **Primary of a replica set:** the node that receives writes for that replica set.
- **Primary shard of a database:** the shard designated to store a database’s **unsharded collections** by default (as well as database metadata).

For example, **Shard A** can be the primary shard for the `shop` database, while inside Shard A’s replica set, **member A2** is currently the primary. These two uses of “primary” do not refer to the same entity.

Unsharded collections are **not automatically spread** across all shards just because the database resides in a sharded cluster. Newer versions provide commands to move unsharded collections (such as `moveCollection` starting in MongoDB 8.0), but that is a separate administrative decision from sharding a collection.

### 5.4. Clients should not connect directly to a shard for cluster-wide operations

To run queries over distributed data, applications typically connect to **`mongos`** or a managed service’s router endpoint.

If you connect directly to a shard and query a sharded collection, you risk observing only **the subset of data held by that shard**, rather than the entire collection across the cluster. Cluster-wide reads and writes must go through the proper router mechanism.

## 6. The shard key is the boundary of physical distribution

MongoDB relies on the **shard key** to partition and route data. Choosing a shard key has long-term impact on:

- Whether data is distributed evenly.
- Whether a query hits **one shard**, **a few shards**, or **all shards**.
- Whether writes concentrate on a single shard.
- The ability to distribute a large tenant across multiple shards.
- The ability to create unique indexes on the sharded collection.
- How easy or difficult it is to apply zone sharding.
- The cost of moving chunks/ranges as data grows.

### 6.1. Ranged sharding

With ranged sharding, adjacent shard key values typically belong to contiguous ranges:

~~~text
Shard key: orderNo

[0000, 3000) ----> Shard A
[3000, 7000) ----> Shard B
[7000, +inf) ----> Shard C
~~~

The ranges above are an illustrative model only, not a layout guaranteed by MongoDB.

Benefits:

- Queries on a **shard key range** can be routed to the relevant subset of shards rather than all of them.
- Can support locality for data that is close together by key.
- Easy to define zone ranges over an ordered shard key.

Risks:

- Monotonically increasing shard keys, such as continuously written timestamps, can concentrate new writes at the leading/trailing range residing on a single shard.
- Low-cardinality keys or heavily skewed values can cause uneven distribution.
- Queries that do not include the shard key can still scatter-gather.

### 6.2. Hashed sharding

Hashed sharding uses the hash value of the shard key to distribute key values:

~~~javascript
// Illustrative key pattern.
{ customerId: "hashed" }
~~~

Benefits:

- Hash values tend to distribute more evenly than monotonically increasing original values.
- Reduces the risk of write hotspots caused by sequential keys if cardinality is sufficient.

Trade-offs:

- Hashing breaks the original ordering of values, making **range** queries on the original key difficult to route to a contiguous region.
- If there is a **single highly repeated shard key value** (an extremely large tenant), hashing it still yields a single hash value and does not automatically spread documents with that value across multiple shards.
- Hashed indexes do not support `unique: true`.

For example, a `{ tenantId: "hashed" }` shard key can help distribute **many tenants** with different IDs, but it does not fundamentally solve the scenario where **one tenant accounts for 90% of the load**.

### 6.3. Compound shard key

Multiple fields can be used in a shard key, for example:

~~~javascript
{ tenantId: 1, orderId: 1 }
~~~

Characteristics:

- The `tenantId` prefix can help route by tenant, though if one tenant spans multiple ranges/shards, a query with only `tenantId` may still touch multiple shards.
- Adding `orderId` increases the number of key combinations, helping split a large tenant’s data when distribution and balancing allow.
- Queries containing the **full shard key conditions** generally have a better chance of targeted routing than queries with only a partial key.
- Must be designed around index/query patterns; do not pick a compound key just because “more fields is better.”

### 6.4. Choose a shard key based on workload, not schema alone

You need to answer:

1. Which filters appear in most queries?
2. Do queries filter by tenant, by `orderId`, or by time range?
3. What is the cardinality of the key?
4. Is there an overwhelmingly common value?
5. Will continuous writes create a hotspot in the tail range?
6. Does a large tenant need to be split across multiple shards?
7. Are there any unique index requirements?
8. Is there a requirement to place tenants in specific regions via zone ranges?

Conclusion: **A shard key is a physical choice that affects query routing**, whereas `tenantId` may simply be a **logical partitioning key** for business logic.

## 7. Targeted queries and scatter-gather

Suppose the `orders` collection is sharded on `{ tenantId: 1, orderId: 1 }`.

Query with the full key:

~~~javascript
db.orders.findOne({
  tenantId: "tenant-a",
  orderId: "ORD-1001"
});
~~~

`mongos` has the information needed to route to the matching shard key range; in normal distributions, a point query with the full key can target a single shard.

Query by tenant only:

~~~javascript
db.orders.find({
  tenantId: "tenant-a"
});
~~~

May touch **multiple shards** if `tenant-a`’s ranges span across multiple shards.

Query without the shard key:

~~~javascript
db.orders.find({
  status: "PAID"
});
~~~

May require a **broadcast/scatter-gather** across multiple shards and merging of results.

| Query pattern | Routing behavior |
| --- | --- |
| Full shard key equality | Typically most narrowly targeted |
| Filter on compound shard key prefix | May target one or multiple shards |
| Range compatible with shard key | May target relevant ranges/shards |
| Filter only on non-shard-key fields | Typically must query many/all shards |
| Sort/aggregate not targeting the shard key | May require cross-shard result merging |

**Do not confuse:** Sharding increases total capacity, but a query that has to scan the entire cluster can be **more expensive** than the equivalent query on a smaller unsharded dataset. Sharding does not replace indexes, projections, filters, and good query design.

## 8. Chunks, the balancer, and why distribution is not always even

MongoDB partitions the shard key space into **chunks/ranges**. Each chunk has boundaries that are **inclusive of the lower bound and exclusive of the upper bound**.

~~~text
[MinKey, 100)  -> Shard A
[100, 500)     -> Shard B
[500, MaxKey)  -> Shard C
~~~

The balancer can migrate chunks/ranges between shards to balance according to the version’s mechanism. Migration incurs network, I/O, and metadata overhead.

### 8.1. The balancer is not an instant load balancer

- It does not promise that every shard always has the exact same document count.
- It does not promise that every shard always has the same byte size, CPU usage, or write QPS.
- A tenant with many documents sharing a single shard key value can make one key region hot.
- A range containing massive data may be hard to split if there are not enough distinct shard key values.
- Zone rules can intentionally keep a subset of data on designated shards, causing uneven byte distribution.
- Migration/chunk movement does not remove the need for the application to route queries using the proper key.

**“Once sharding is enabled, MongoDB automatically evens out everything”** is a misconception. Choosing the shard key and measuring actual load remain design responsibilities.

## 9. Replication and sharding can be combined

A cluster has **3 shards**, each being a **replica set of 3 data-bearing members**:

~~~text
                  SHARDED CLUSTER
               ~3 TB logical data
                       |
                mongos / CSRS
              /        |        \
             v         v         v
           Shard A   Shard B   Shard C
           ~1 TB     ~1 TB     ~1 TB
          A1 A2 A3  B1 B2 B3  C1 C2 C3
          3 copies  3 copies  3 copies
~~~

In this simplified example:

- Total logical application data ≈ **3 TB**.
- Each shard holds ≈ **1 TB** of logical data.
- If each shard has three full replicas, total physical storage for shard data (excluding indexes, oplog, overhead, compression) can be roughly **9 TB**.
- Adding a replica to Shard A increases the **copies** of Shard A’s data; it does not automatically increase the number of distributed data subsets.
- Adding **Shard D** can increase logical data capacity and help distribute load once data/chunks are appropriately migrated.

This is only a directional estimate: actual footprint depends on indexes, oplog, compression, journal, temporary files, imbalance, and config servers.

### 9.1. Combined benefits

**Sharding** provides the ability to distribute storage and write workloads across multiple shards.

**Replication within each shard** allows the shard to continue operating if a data-bearing member fails and an election for a new primary can succeed.

**Config server replica set** protects the sharded cluster’s metadata.

A production cluster should not treat a standalone single-machine shard as an HA architecture equivalent to a replica set; current MongoDB versions require shards to be replica sets.

### 9.2. Losing an entire shard vs. losing one member

If **one member** of a shard replica set is lost, the remaining members can continue after an election if eligible.

If an **entire shard** becomes unavailable, the data residing on that shard cannot be retrieved in full through the cluster. Queries touching the lost shard may fail or return errors, even while the other shards remain healthy.

Adding replication helps tolerate member failures; it **does not** guarantee the cluster can serve all data when an entire shard/zone goes down.

## 10. What does business partitioning mean?

**Business partitioning** is the categorization of data by business domain concepts:

- Tenant/company: `tenantId`.
- Fiscal year: `fiscalYear`.
- Legal jurisdiction: `countryCode`.
- Product group: `businessUnit`.
- Data lifecycle: active/archive.
- Service tier: free/pro/enterprise.
- Transaction type or event source.

Goals may include:

1. Isolating tenants or access permissions.
2. Applying different retention/backup policies.
3. Simplifying business scoping during data migrations.
4. Narrowing query scope.
5. Dividing operational ownership by data group.
6. Separating large tenants from small tenants.
7. Supporting compliance with geographic data storage policies.

This **does not inherently dictate which machine stores the data**. Business partitioning can be as simple as a field, a set of collections, multiple databases, or completely separate clusters.

### 10.1. Logical partitioning within the same collection

Example:

~~~javascript
{
  _id: ObjectId("..."),
  tenantId: "tenant-a",
  orderId: "ORD-1001",
  total: 250
}
~~~

All tenants share `db.orders`. Queries must include `tenantId`:

~~~javascript
db.orders.find({
  tenantId: "tenant-a",
  status: "PAID"
});
~~~

Common index:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
~~~

**This is not necessarily sharding.** On a replica set, all documents for tenants a/b/c still belong to the same dataset replicated to every data-bearing member.

### 10.2. Collection per year

The application can create:

~~~text
orders_2024
orders_2025
orders_2026
orders_2027
~~~

When querying orders for 2026, the application selects `orders_2026`. This is **application-defined time-based partitioning**.

Pros: easy retention/archiving operations per collection and scoping to a single year.

Cons:

- Must choose the right collection on every read/write.
- Multi-year reporting may require querying multiple collections or using `$unionWith` where supported.
- Indexes and schemas/validators must be managed across many collections.
- Too many namespaces increase metadata/operational overhead.
- Does not automatically distribute across multiple machines if all collections sit on the same replica set.

### 10.3. Database per tenant

~~~text
tenant_a.orders
tenant_b.orders
tenant_c.orders
~~~

Benefits: administrative boundaries and per-database authorization can be clearer for certain models.

Drawbacks: migrations, indexes, schema versions, connection pooling, backup/restore, and cross-tenant reporting become more complex. Using a separate database per tenant **does not automatically** increase write capacity if all databases still reside on one primary of the same replica set.

### 10.4. Cluster per tenant or tenant group

Some systems map large tenants or special customer groups to **independent clusters**.

Pros:

- Better workload isolation.
- Can provision separate capacity, versions, geographic regions, and maintenance schedules.
- Limits the impact of an oversized tenant on other tenants.

Trade-offs:

- Cost of running multiple clusters.
- Application must manage **tenant → cluster mapping**.
- Cross-cluster migrations are complex.
- Cross-tenant analytics and cross-cluster transactions are harder; there is no single default `mongos` to join across independent clusters.
- Must synchronize security, backup, schema, and index policies across many deployments.

**Do not confuse** multiple application-routed clusters with **a single sharded cluster** where `mongos` coordinates the whole collection.

## 11. Four common multi-tenancy patterns

| Pattern | Description | Is it MongoDB sharding? | Strengths | Weaknesses |
| --- | --- | --- | --- | --- |
| Shared collection | Documents contain `tenantId` | Not necessarily | Few namespaces, easy to deploy | Requires strict filtering/auth, hot tenants compete for resources |
| Collection per tenant | Each tenant has its own collection | Not necessarily | Can customize indexes/TTL per tenant | Many collections and metadata |
| Database per tenant | Separate database per tenant | Not necessarily | Clear administrative boundaries | Complex provisioning/migrations |
| Cluster per tenant/group | App routes to separate deployments | **Not** a single sharded cluster in the MongoDB sense | Strong resource isolation | Cost and cross-cluster queries |
| Shared sharded collection | One sharded collection with `tenantId` in key or filter | **Yes**, if collection is sharded | Scale-out under one logical namespace | Shard key/routing and distribution are harder |

**Important:** A tenant is a **business** concept; a shard is a **MongoDB infrastructure and data distribution** unit. There is no rule saying “one tenant equals one shard.”

## 12. The case of one extremely large tenant

Suppose:

~~~text
Tenant A: 90% write QPS, 70% data
Tenant B:  5% write QPS, 15% data
Tenant C:  3% write QPS, 10% data
Others:    2% write QPS,  5% data
~~~

If the shard key is `{ tenantId: "hashed" }`, all documents with `tenantId` A produce the same hashed key value. A single key value is not automatically spread across multiple chunks/shards just because the document count is huge.

**Consequence:** One hot tenant can become a bottleneck even with many total shards.

Design directions to consider:

- Use a **compound shard key** adding a field with sufficient variety within the tenant, such as `{ tenantId: 1, orderId: 1 }`, if query patterns and uniqueness align.
- Split the very large tenant onto a **dedicated cluster**.
- Distribute workload via bucketing or a well-defined load-splitting value, while handling query fan-out.
- Rate-limit heavy queries, add caching, or assign dedicated read capacity.
- Measure hot shards by QPS/CPU/I/O rather than storage size alone.

Do not invent a random `partitionNo` field and use it as the shard key if primary queries do not know `partitionNo`: doing so can force queries to fan out to every partition.

## 13. Hands-on example: logical partitioning before sharding

This section runs on a regular MongoDB database, **without needing a sharded cluster**.

~~~javascript
const lab = db.getSiblingDB("partitioning_lab");

lab.orders.drop();

lab.orders.insertMany([
  { _id: 1, tenantId: "A", orderId: "A-001",
    status: "PAID", total: 100,
    createdAt: ISODate("2026-01-01T09:00:00Z") },
  { _id: 2, tenantId: "A", orderId: "A-002",
    status: "PAID", total: 150,
    createdAt: ISODate("2026-01-02T09:00:00Z") },
  { _id: 3, tenantId: "A", orderId: "A-003",
    status: "CANCELLED", total: 50,
    createdAt: ISODate("2026-01-03T09:00:00Z") },
  { _id: 4, tenantId: "A", orderId: "A-004",
    status: "PAID", total: 250,
    createdAt: ISODate("2026-01-04T09:00:00Z") },
  { _id: 5, tenantId: "A", orderId: "A-005",
    status: "PENDING", total: 300,
    createdAt: ISODate("2026-01-05T09:00:00Z") },
  { _id: 6, tenantId: "A", orderId: "A-006",
    status: "PAID", total: 200,
    createdAt: ISODate("2026-01-06T09:00:00Z") },

  { _id: 7, tenantId: "B", orderId: "B-001",
    status: "PAID", total: 75,
    createdAt: ISODate("2026-01-01T10:00:00Z") },
  { _id: 8, tenantId: "B", orderId: "B-002",
    status: "PAID", total: 125,
    createdAt: ISODate("2026-01-02T10:00:00Z") },
  { _id: 9, tenantId: "B", orderId: "B-003",
    status: "PENDING", total: 200,
    createdAt: ISODate("2026-01-03T10:00:00Z") },
  { _id: 10, tenantId: "B", orderId: "B-004",
    status: "PAID", total: 50,
    createdAt: ISODate("2026-01-04T10:00:00Z") },

  { _id: 11, tenantId: "C", orderId: "C-001",
    status: "PAID", total: 40,
    createdAt: ISODate("2026-01-01T11:00:00Z") },
  { _id: 12, tenantId: "C", orderId: "C-002",
    status: "PAID", total: 60,
    createdAt: ISODate("2026-01-02T11:00:00Z") },
  { _id: 13, tenantId: "C", orderId: "C-003",
    status: "CANCELLED", total: 90,
    createdAt: ISODate("2026-01-03T11:00:00Z") },

  { _id: 14, tenantId: "D", orderId: "D-001",
    status: "PAID", total: 300,
    createdAt: ISODate("2026-01-01T12:00:00Z") },
  { _id: 15, tenantId: "D", orderId: "D-002",
    status: "PAID", total: 500,
    createdAt: ISODate("2026-01-02T12:00:00Z") }
]);

lab.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "ix_tenant_status_date" }
);

lab.orders.createIndex(
  { tenantId: 1, orderId: 1 },
  { name: "uq_tenant_order", unique: true }
);
~~~

Here `tenantId` is a **business partitioning key**, and indexes assist queries/constraints. However, because `shardCollection` has not been run, **there is no physical sharding**.

### 13.1. Count by tenant

~~~javascript
lab.orders.aggregate([
  { $group: { _id: "$tenantId", orders: { $sum: 1 } } },
  { $sort: { _id: 1 } }
]);
~~~

Expected values:

| Tenant | Order count |
| --- | ---: |
| A | 6 |
| B | 4 |
| C | 3 |
| D | 2 |
| **Total** | **15** |

### 13.2. Total PAID revenue by tenant

~~~javascript
lab.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: "$tenantId",
      paidOrders: { $sum: 1 },
      revenue: { $sum: "$total" }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Verification:

| Tenant | PAID orders | PAID revenue |
| --- | ---: | ---: |
| A | 4 | 700 |
| B | 3 | 250 |
| C | 2 | 100 |
| D | 2 | 800 |
| **Total** | **11** | **1,850** |

These metrics help you observe **business distribution**. They **do not tell you** how many shards the documents reside on.

### 13.3. Query by tenant

~~~javascript
lab.orders.find({
  tenantId: "A",
  status: "PAID"
}).sort({ createdAt: -1 });
~~~

This query can leverage the `ix_tenant_status_date` index on a regular collection. If later sharded on a key with `tenantId` in the prefix, the query may also benefit from **shard targeting**. These are two distinct benefits:

- **Index:** reduces the number of documents/keys scanned within a shard/server.
- **Shard key:** reduces the number of shards that need to be contacted.

A query targeted to the right shard can still be slow if that shard lacks an index. A query with a good index can still incur scatter-gather overhead if it lacks the shard key.

## 14. Observing sharding on an existing cluster

This section **only applies when a test sharded cluster is available** and you connect through `mongos`. Do not enable sharding or modify a production cluster just to complete an exercise.

### 14.1. Viewing cluster status

~~~javascript
// Run in mongosh connected to mongos.
sh.status();
~~~

The output provides information on shards, databases, and metadata for sharded collections, depending on version/privileges and configuration.

You can also use:

~~~javascript
db.hello();
~~~

When connected to `mongos`, the response typically includes `msg: "isdbgrid"`, distinguishing the router from a standalone `mongod`.

### 14.2. Illustrating shardCollection

Suppose the lab cluster has the `partitioning_lab.orders` collection, a shard key has been chosen after workload analysis, and a matching index exists:

~~~javascript
// ILLUSTRATION ONLY: modifies sharding metadata in the cluster.
// Do not run on production or a collection with live
// traffic without a rollout plan.
sh.shardCollection(
  "partitioning_lab.orders",
  { tenantId: 1, orderId: 1 }
);
~~~

In a real cluster, preconditions and the sharding procedure depend on version, collection state, indexes, unique indexes, zone ranges, and administrative privileges. The example here only illustrates **the command that associates a collection with a shard key**.

**Specifically:** The `lab.orders` collection in section 13 already has a unique index `{tenantId:1,orderId:1}` and `_id_`; when converting to a sharded collection, you must verify conditions around **uniqueness**, shard-key prefix, `_id` data, and cluster rules. Do not assume every index on an unsharded collection remains valid as-is after sharding.

### 14.3. Reading cluster routing

After sharding completes, query through `mongos`:

~~~javascript
lab.orders.find({
  tenantId: "A",
  orderId: "A-001"
}).explain("queryPlanner");
~~~

Explain fields may vary across versions and engines; in a sharded cluster, the plan typically shows information about the queried shards, routing, and subplans. You should distinguish:

- **Shard targeting:** how many shards the query is sent to.
- **Index selection:** whether each shard uses `IXSCAN`, `COLLSCAN`, or another plan.
- **Merge stage:** whether results from multiple shards need to be merged/sorted.

Do not rely on a single explain snapshot to infer real production load; measure against actual workloads and data distributions.

## 15. Time-based partitioning is not automatically equivalent to time-series or a shard key

An application can split:

~~~text
events_2025
events_2026
events_2027
~~~

or use a single `events` collection with an `occurredAt` field and an index.

Different options:

| Option | Organization | Automatically scales out across shards? |
| --- | --- | --- |
| Collection per year | Application routes data by collection name | No |
| Regular collection indexed on Date | B-tree index supports time filters/sorts | No |
| Sharded collection keyed on Date | MongoDB distributes ranges/chunks | Yes, if cluster is sharded |
| Time series collection | Bucket mechanism designed for measurements | Does not automatically mean sharded |

You can **shard a time series collection** in supported versions/setups, but time series and sharding are **two separate decisions** with specific constraints.

If the shard key is solely a monotonically increasing `occurredAt`, writes can concentrate on the tail range. If a hashed key is used to spread writes evenly, time-range queries may have to contact multiple shards. Choose based on actual goals rather than mechanically assuming “data has a timestamp, so shard by timestamp.”

## 16. Zone sharding: connecting business rules to shard placement

MongoDB allows configuring **zones** associated with specific shards and **shard key ranges**. The balancer can move ranges to shards belonging to the appropriate zone.

Business example:

~~~text
EU region tenant -> data resides in zone eu
APAC region tenant -> data resides in zone apac
~~~

This is an example of combining:

- **Business partitioning:** identifies the tenant/region of the data.
- **Sharding:** uses the shard key to route and divide ranges.
- **Zone policy:** specifies which shards may hold ranges belonging to a zone.
- **Replication:** replicates data within each shard replica set.

### 16.1. A zone is not just a region field

Adding `region: "EU"` to a document **does not** automatically activate zone sharding. Zones must be configured on the cluster for appropriate key ranges. Administrative APIs include `sh.addShardToZone()` and `sh.updateZoneKeyRange()`, but because they alter cluster metadata, do not run them arbitrarily in a lab.

### 16.2. Limitations when using zones

- Zone ranges are based on the **shard key**; you cannot arbitrarily route on a non-key field.
- Ranges are inclusive of the lower bound and exclusive of the upper bound.
- A shard can belong to multiple zones, depending on configuration.
- The balancer takes time to reach the desired distribution; instant migration is not guaranteed.
- A shard replica set can have members in different geographic locations; checking zones alone is not enough to prove every **physical copy** resides in the required jurisdiction.
- With a hashed shard key, zone ranges are based on **hashed values**, which do not trivially map to original tenant ID strings by default.

**Do not treat zone sharding alone as a legal guarantee of data residency.** You must verify the placement of all data-bearing members, backups, config metadata, logs, exports, and operational procedures.

## 17. Indexes and uniqueness across the three models

### 17.1. Replica sets do not change collection-level uniqueness scope

On a regular collection inside a replica set, a unique index enforces uniqueness for that collection on that dataset. Replication copies changes and indexes using MongoDB’s replication mechanism; it does not give each secondary an “independent uniqueness scope” for separate application writes.

### 17.2. Sharded collections have specific rules

With ranged sharding, a unique index on a sharded collection must align with a **shard-key prefix** according to MongoDB’s supported rules.

Example shard key:

~~~javascript
{ tenantId: 1 }
~~~

Index enforcing unique emails within a tenant:

~~~javascript
db.users.createIndex(
  { tenantId: 1, emailKey: 1 },
  { unique: true }
);
~~~

Conversely, a unique index only on `{emailKey:1}` lacks the shard-key prefix in the scenario above, so you cannot assume MongoDB will accept or enforce it cluster-wide.

### 17.3. _id and global uniqueness

If `_id` is not the shard key, there are scenarios where MongoDB enforces `_id` uniqueness only within each shard. The application must generate globally unique identifiers when business logic depends on a global `_id`.

### 17.4. Business partitioning into multiple clusters has separate constraints

If tenant A and tenant B are written to **two independent MongoDB clusters**, a unique index on a collection in cluster A **does not** automatically prevent a duplicate value in cluster B. If global uniqueness across multiple clusters is needed, an explicit registry/coordination model or shared constraint architecture must be designed.

**In summary:** Always ask “at **what scope** must uniqueness hold?” before deciding on an index.

## 18. Transactions and consistency when data is distributed

### 18.1. Replication: write concern and read preference

In a replica set:

- Normal writes go to the primary.
- `writeConcern: {w:"majority"}` defines acknowledgment across a majority of members per deployment rules.
- Read preference can send reads to secondaries.
- Secondaries can be stale due to replication lag, even after the primary has acknowledged a write.

**Replication does not automatically imply linearizable reads in all configurations.**

### 18.2. Sharding: a business transaction can touch multiple shards

Suppose a money transfer:

~~~text
Account A on Shard 1
Account B on Shard 2

Debit A   -> Shard 1
Credit B  -> Shard 2
~~~

Two update operations on **two documents** and **two shards** do not automatically form a single atomic write merely because they execute through `mongos`. MongoDB supports **distributed transactions** in appropriate versions/topologies, but they carry coordination overhead and operational limits.

Good design tries to colocate frequently co-updated data within a reasonable scope when possible, without compromising so much that the shard key creates hotspots or makes other queries very expensive.

### 18.3. Business partitioning does not create transactions across multiple clusters

If the application partitions tenants onto independent clusters, a MongoDB transaction on cluster A **cannot participate** in a global transaction with cluster B. You must design sagas, outbox/inbox patterns, idempotency, or orchestration workflows according to business requirements.

### 18.4. Single-document writes remain atomic

Sharding does not remove single-document update atomicity within MongoDB’s guarantees. Example:

~~~javascript
db.inventory.updateOne(
  {
    tenantId: "A",
    sku: "SKU-1",
    stock: { $gte: 1 }
  },
  {
    $inc: { stock: -1 }
  }
);
~~~

The inventory condition must be checked as part of the write operation itself, rather than doing a stale secondary read followed by an unconditional update. If the collection is sharded, the filter should be designed to satisfy routing rules and operation validity on a sharded collection.

## 19. Scale-out and availability are not a single number

A requirement saying “the system needs to triple” is not enough to choose a mechanism. You need to know what is tripling:

| Goal | Replication | Sharding | Business Partitioning |
| --- | --- | --- | --- |
| Tolerate one member failure | **Suitable** | Only when each shard has replication/HA | Not sufficient on its own |
| Store more logical data | Every copy still holds the entire dataset | **Suitable** if evenly distributed | Possible, if partitions sit on different capacity |
| Distribute write QPS | One primary still receives writes for the dataset | **Suitable** if shard key has enough diversity | Possible with independent clusters |
| Offload reporting from primary | Can read from secondaries | Can distribute reads across shards | Can use reporting cluster/partition |
| Isolate a large tenant | Not with replication alone | Possible via shard key/zones with careful design | Separate database/cluster can be clearer |
| Archive an old year | Not directly | Does not replace retention | Yearly collection/retention fits well |
| Restrict data by region | Replica placement must be designed | Zone sharding can assist | Regional tenant/cluster routing can assist |
| Fast cross-tenant queries | Not directly | Depends on shard targeting/queries | Can become harder across separate clusters |

There is no default answer such as “adding shards is always faster” or “adding replicas is always cheaper.” You must measure dataset size, working set, QPS, query patterns, and HA requirements.

## 20. Three architectural decision scenarios

### Scenario A — Data fits on one server, but downtime is unacceptable

Requirements:

- 100 GB dataset.
- Application does not need massive write scale-out.
- Wants automatic failover if a node fails.

**Priority:** a replica set with election-eligible data-bearing members and backups. Sharding is likely unnecessary, as adding routers/shards/config metadata increases complexity without better solving the core requirement.

### Scenario B — Dataset and write workload exceed a single primary’s capacity

Requirements:

- Very large orders collection.
- Many tenants writing concurrently.
- Scaling a single machine’s CPU/storage is no longer enough.
- Queries mostly include `tenantId`/`orderId`.

**Consider:** a sharded collection with a workload-benchmarked shard key, shards deployed as replica sets, routing via `mongos`, and a plan to monitor balancing/hotspots. Business partitioning may still be needed for tenant filtering and retention.

### Scenario C — An enterprise tenant requires complete isolation

Requirements:

- Enterprise tenant has dedicated SLAs, version, or storage region.
- Must not contend for load with standard tenants.
- Can accept separate management and higher cost.

**Consider:** a dedicated database/cluster per tenant or tenant group, application-level routing mapping, and separate backups and security. Do not confuse this strategy with letting MongoDB split one collection via shards; you can still use sharding **inside** the dedicated cluster if the tenant grows too large.

## 21. Operational cost and failure domains

### 21.1. Replication

Must operate:

- Elections and failover.
- Oplog retention.
- Replication lag.
- Write concern and read preference.
- Storage capacity for replicas and indexes.
- Backups/restores; replicas are not point-in-time backups.

### 21.2. Sharding

In addition to each shard’s replication, must operate:

- `mongos` and config server replica set.
- Shard key/index design.
- Balancer and chunk/range migrations.
- Scatter-gather query performance.
- Adding/removing shards procedurally.
- Distributed transactions when used.
- Zone placement and availability when a shard fails.
- Unique index constraints and `_id` global uniqueness.

### 21.3. Business partitioning

Applications and operations must manage:

- Partition catalog (`tenant → collection/database/cluster`).
- Provisioning new tenants.
- Synchronized index/schema migrations across partitions.
- Moving tenants, splitting/merging partitions.
- Cross-partition analytics.
- Access controls preventing tenant data leakage.
- Backups/retention and data residency per business policy.

**Business partitioning can increase complexity at the application layer**, even when each individual MongoDB cluster is very simple.

## 22. A systematic decision process

Follow this sequence:

~~~text
1. Need HA and member fault tolerance?
      |
      +-- Yes --> design replica set / backups / failover
      |
      v
2. Has dataset or write QPS exceeded one shard/primary?
      |
      +-- Yes --> analyze sharding, shard key, workload
      |
      v
3. Need to separate tenant/year/region by business policies?
      |
      +-- Yes --> define logical partitions
                  then choose collection/database/cluster/zone
      |
      v
4. Need to combine them?
      |
      +-- Sharded cluster composed of replica sets
      +-- TenantId + shard key
      +-- Zone sharding by business region
      +-- Dedicated cluster for large tenants
      |
      v
5. Re-measure failures, read/write QPS, routing,
   query latency, lag, cost, and operational complexity
~~~

### Pre-sharding checklist

1. Does the dataset truly exceed the suitable capacity/working set of a single replica set?
2. Can the write workload be distributed across multiple shard keys?
3. Do common queries carry the shard key?
4. Is there a single hot tenant or hot timestamp?
5. Are cross-shard aggregations/transactions frequent?
6. Do unique constraints align with a shard-key prefix?
7. Do indexes support queries inside each shard?
8. Is there a plan for resharding/migration and hotspot monitoring?
9. Is there enough budget to operate additional `mongos`/CSRS/shards?
10. Is zone placement or regional data residency required?

## 23. Common misconceptions

| Misconception | Why it is wrong | Correct understanding |
| --- | --- | --- |
| “Three replicas means three times the logical data capacity” | Each data-bearing member holds the same dataset | Replication creates copies for HA |
| “A replica set has three primaries for writes” | A typical replica set has one primary accepting writes | To distribute writes, consider multiple shards |
| “Sharding puts a full copy of all data on every shard” | Each shard holds a subset | Full copies of **a subset** live within each shard’s replica set |
| “Having tenantId means it is sharded by tenant” | A logical field does not create physical shards | Must configure `shardCollection`/cluster properly |
| “One tenant always maps to one shard” | Shard key ranges can contain many tenants; large tenants can span many ranges | A shard is a physical unit; a tenant is a domain concept |
| “Collection per year auto-distributes across servers” | Collections may sit on the same primary shard/replica set | Requires separate physical placement/routing |
| “Sharding doesn’t need replica sets” | Current shards must be deployed as replica sets | Replication provides HA |
| “Secondaries always have recently written data” | Replication is asynchronous | Use appropriate read preference/read concern/causal consistency |
| “Sharding always speeds up every query” | Scatter-gather and merges can be expensive | Choose shard key and indexes for the workload |
| “Hashed tenantId spreads a hot tenant across all shards” | One `tenantId` produces one hashed value | Need compound/other distribution strategy |
| “The balancer always equalizes CPU and write QPS” | The balancer handles placement/ranges, not every query/workload | Monitor hotspots and key distribution |
| “Primary shard is the replica set’s primary member” | Two different levels of concepts | Distinguish database primary shard from replSet primary |
| “Zone tags alone prove data residency compliance” | Replicas, backups, and other placements still exist | Audit all data/metadata/backup paths |
| “Unique indexes work on sharded collections just like regular ones” | Requires shard-key prefix and has restrictions | Check sharded uniqueness rules before rollout |
| “Adding a shard immediately balances data” | Balancing/migration takes time and conditions | Plan and monitor chunk/range movement |
| “Replication replaces backups” | Accidental deletes/logic bugs get replicated | Maintain separate backups and test restores |
| “Apps using multiple clusters share one MongoDB transaction” | Independent clusters do not share transactions automatically | Use sagas/coordination when needed |

## 24. Hands-on exercises

### Exercise 1 — Three proposals, three needs

A system faces three problems:

1. One MongoDB machine crashing brings down the API.
2. One collection exceeds a single machine’s capacity.
3. The accounting department wants to freeze data by fiscal year.

For each problem, choose **replication**, **sharding**, or **business partitioning** as the primary direction. State one reason and one thing that mechanism does not guarantee by itself.

**Guided answer:** (1) replication for HA, does not replace backups; (2) sharding to scale out data, still needs replica sets for HA; (3) period/year partitioning or retention policy, does not necessarily require sharding.

### Exercise 2 — Count replicas, do not miscount logical data

A replica set has 3 data-bearing members holding 300 GB of logical data, ignoring indexes/oplog/overhead. How much logical data does each member hold? Roughly what is the total storage footprint across replicas?

**Answer:** Each member holds ~300 GB; total physical data stored across replicas is ~900 GB. You must not say the system has 900 GB of distinct business data.

### Exercise 3 — Sharding with replication

A cluster has 4 shards, each a replica set with 3 data-bearing members; a 4 TB logical dataset is evenly distributed. Ignoring overhead, estimate the logical dataset per shard and total replica storage.

**Answer:** ~1 TB/shard, ~3 TB of replicas for each shard’s subset, ~12 TB total physical storage for the copies; not 12 TB of unique logical data.

### Exercise 4 — Logical tenant partitioning

The `orders` collection has 15 documents as in section 13, all on one replica set. The `tenantId` field is indexed. Is this already MongoDB sharding? Why or why not?

**Answer:** Not yet. `tenantId` is logical business partitioning and the index helps queries; there is no sharded collection or chunk routing via `mongos`.

### Exercise 5 — Checking order counts by tenant

Run `$group` on `lab.orders` and compare:

~~~text
A: 6
B: 4
C: 3
D: 2
Total: 15
~~~

If one group has overwhelmingly many orders, what happens to load when the shard key is only `tenantId`?

**Answer:** A hot tenant concentrates onto a single shard key value, causing a hotspot; you must evaluate distribution and compound shard keys or another architecture.

### Exercise 6 — Replication lag and reads

An order was just written on the primary but does not appear when reading with `secondaryPreferred`. Is this evidence that sharding failed?

**Answer:** No. This can be a stale read caused by replication lag. Read preference and consistency must be designed appropriately.

### Exercise 7 — Choosing a shard key

The workload has many queries like:

~~~javascript
db.orders.findOne({
  tenantId: "A",
  orderId: "A-001"
});
~~~

Compare the pros/cons of `{orderId:"hashed"}`, `{tenantId:1}`, and `{tenantId:1,orderId:1}`. Choose one direction if tenant A accounts for most of the data, and state what must be benchmarked.

### Exercise 8 — Targeted vs. scatter-gather

A sharded collection uses `{tenantId:1,orderId:1}`. Evaluate which query is likely to target more narrowly:

~~~javascript
db.orders.findOne({ tenantId: "A", orderId: "A-001" });
db.orders.find({ tenantId: "A" });
db.orders.find({ status: "PAID" });
~~~

**Answer:** The full-key point query usually routes most narrowly; tenant-only may hit one or multiple shards; status-only typically requires scatter-gather.

### Exercise 9 — Splitting collections by year

An application has `orders_2025` and `orders_2026` on the same replica set. What needs to change to give each year separate physical capacity? What difficulties arise for cross-year queries?

### Exercise 10 — Primary shard vs. replica set primary

Explain these two statements:

- “Database `shop` has Shard B as its primary shard.”
- “Shard B’s replica set currently has member B2 as primary.”

Why do these two statements not contradict each other?

### Exercise 11 — Global unique key

The `users` collection is sharded on `tenantId`. The application wants platform-wide unique emails, but the `{tenantId:1,email:1}` index only enforces email uniqueness within a tenant. Name two architectural options to consider.

**Hint:** Change the shard key/uniqueness model if appropriate, or use a separate registry with a globally unique key and write coordination. Do not arbitrarily create a unique index without the shard-key prefix.

### Exercise 12 — Zones and data residency

EU data must stay within the EU region. A cluster configures an EU zone and places EU tenant ranges on shards in that zone. What else must still be checked besides zone ranges?

**Answer:** Placement of all data-bearing replica members, backups, exported data, logs, metadata/config, access accounts, and operational policies. Zones alone do not guarantee strict compliance.

### Exercise 13 — Inventory condition under concurrency

The backend reads stock from a secondary and then decrements stock on the primary if it sees `stock > 0`. Identify the bug and write a conditional `updateOne`:

~~~javascript
db.inventory.updateOne(
  { sku: "SKU-1", stock: { $gte: 1 } },
  { $inc: { stock: -1 } }
);
~~~

Explain why an atomic write condition is still needed even when using sharding and replication.

### Exercise 14 — Choosing an option for an enterprise tenant

A large tenant needs a separate SLA, separate backups, dedicated administrative staff, and isolation from smaller tenants. Choose among a `tenantId` shard key, zone sharding, and a dedicated cluster. State the cost/operability trade-offs rather than giving a one-word answer.

### Exercise 15 — Failure domains

In a sharded cluster, member A1 of Shard A fails while replica set A remains eligible for election; later, all of Shard B fails. Describe the different availability impacts. Why can’t another healthy shard substitute for Shard B’s data?

### Exercise 16 — Integrated architecture design

A SaaS application has these requirements:

- 4 million businesses, mostly small but a few extremely large.
- A single member failure must not stop the service.
- Some tenants have mandatory data residency regions.
- Reports may lag by a few seconds, but payment confirmations must not use stale reads.
- Data is growing beyond a single server.

Propose how to combine **replica sets**, **sharding**, **business partitioning**, **zones/dedicated clusters**, **read preference**, and **write/read concern**; state at least three risks that must be measured before production operation.

## 25. Summary

The three mechanisms must be understood **by their goals**, not by their names:

- **Replication:** maintains asynchronously synchronized copies in a replica set, supporting availability/failover and some read distribution; does not distribute writes for the same dataset across multiple primaries.
- **Sharding:** splits a sharded collection by shard key into chunks/ranges across multiple shards; supports storage scale-out and workload distribution when the shard key fits; does not create HA without replication inside each shard.
- **Business partitioning:** defines boundaries by tenant, year, region, or service tier; may just be a filter in one collection or become separate collections/databases/clusters; does not automatically become MongoDB sharding.

A **production sharded cluster** combines a **replica set on each shard** with a **config server replica set**, serving applications via `mongos`. A multi-tenant system can store `tenantId` in documents, use a workload-appropriate shard key, attach zones for data requiring specific placement, and isolate large tenants onto dedicated clusters when needed.

**Final design rule:** Start from requirements for **availability, capacity, write/read workload, query patterns, consistency, tenant isolation, and data locality**. Only then choose the number of replicas, number of shards, shard key, and business partitioning strategy. Data only truly scales out when physical routing and placement support that goal.

### Official MongoDB documentation

- [Replication](https://www.mongodb.com/docs/manual/replication/) — replica sets, primary/secondary, replication lag, and failover.
- [Replica Set Members](https://www.mongodb.com/docs/manual/core/replica-set-members/) — data-bearing members and arbiters.
- [Sharding Introduction and Architecture](https://www.mongodb.com/docs/manual/sharding/) — data distribution, shard keys, and cluster components.
- [Sharded Cluster Components](https://www.mongodb.com/docs/manual/core/sharded-cluster-components/) — shards, mongos, config servers.
- [Shards](https://www.mongodb.com/docs/manual/core/sharded-cluster-shards/) — shard replica sets, primary shard, and unsharded collections.
- [Config Servers](https://www.mongodb.com/docs/manual/core/sharded-cluster-config-servers/) — CSRS, routing metadata, and config shards since 8.0.
- [Data Partitioning with Chunks](https://www.mongodb.com/docs/manual/core/sharding-data-partitioning/) — ranges, chunks, and initial distribution.
- [Ranged Sharding](https://www.mongodb.com/docs/manual/core/ranged-sharding/) — key selection and range queries.
- [Hashed Sharding](https://www.mongodb.com/docs/manual/core/hashed-sharding/) — hash distribution and trade-offs with range queries.
- [Shard Keys](https://www.mongodb.com/docs/manual/core/sharding-choose-a-shard-key/) — shard key selection.
- [Zones](https://www.mongodb.com/docs/manual/core/zone-sharding/) — zone ranges and data locality.
- [Maintain Uniqueness in Sharded Clusters](https://www.mongodb.com/docs/manual/tutorial/maintain-uniqueness-in-sharded-clusters/) — unique index limitations.
- [Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/) — secondary reads and stale data.
- [Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — transactions in replica sets and sharded clusters.
