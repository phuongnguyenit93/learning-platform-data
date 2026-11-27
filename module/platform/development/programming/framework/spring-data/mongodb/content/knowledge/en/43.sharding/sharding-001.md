# Purpose of Sharding and the Role of mongos

## 1. The problem sharding solves

In a system using **Spring Data MongoDB**, the application can store documents with **MongoTemplate** or **MongoRepository**. As data and traffic grow, a single MongoDB replica set can hit limits on disk capacity, memory, CPU, or read/write throughput. Increasing server hardware specs (vertical scaling) only solves the problem up to a threshold and can become expensive.

**Sharding** is how MongoDB distributes documents of a collection across **multiple shards**, so that machines share storage capacity and part of the query processing workload. This is a **horizontal scaling** mechanism. The application still operates against standard database names, collection names, and MongoDB APIs; the cluster's routing layer determines which shard should receive each request.

For example, an **orders** collection has hundreds of millions of orders across many tenants. If sharded by **tenantId**, the data is split across multiple shards instead of being concentrated on a single machine. A query containing a specific tenantId can be routed to the exact shard storing that tenant, whereas a system-wide statistics report may need to read data across multiple shards.

After this lesson, you will be able to:

- Explain when sharding is needed and distinguish sharding from replication.
- Identify the **shard**, **config server replica set**, and **mongos** components in a sharded cluster.
- Describe how **mongos** routes operations based on the **shard key**, and why a query might have to run across multiple shards.
- Connect Spring Data MongoDB through mongos, inspect query scope, and recognize the operational overhead of sharding.

## 2. How does sharding differ from replication?

The two mechanisms complement each other, but they solve different needs.

| Criterion | Replication (replica set) | Sharding (sharded cluster) |
| --- | --- | --- |
| How data is organized | Replica set members hold copies of the same dataset. | Each shard holds a subset of the sharded collection's data. |
| Primary purpose | Increase availability and recover when a node fails; can serve certain read demands. | Distribute storage capacity and workload across multiple shards. |
| Write scalability | Most writes still go through the primary of a single replica set. | Writes can be distributed across shards if the shard key and workload are suitable. |
| Relationship between the two | Can be used standalone for data that does not yet need sharding. | In production deployments, each shard is typically a replica set for fault tolerance. |

**Key takeaway:** having three replicas in a replica set does not mean usable storage capacity triples. Similarly, adding shards does not automatically make every query faster: the choice of shard key and access patterns determine the actual benefit.

### When should you consider sharding?

- Data size or growth rate exceeds the capacity of a single replica set.
- Read/write load can be distributed by a clear key (such as customer, tenant, or data region).
- A single machine has become a bottleneck even after optimizing indexes, queries, configuration, and resources.
- The system is able to operate additional distributed components and monitor data balance.

If the collection is still small, queries run well on a single replica set, or most requests always target the same small group of documents, sharding can add complexity with little benefit.

## 3. Components of a sharded cluster

~~~mermaid
flowchart TB
    App["Spring Data MongoDB Application<br/>MongoTemplate / Repository"]
    Driver["MongoDB Java Driver"]
    Router["mongos<br/>Query router"]
    Meta[("Config Server Replica Set<br/>Sharding metadata")]
    A[("Shard A<br/>typically a replica set")]
    B[("Shard B<br/>typically a replica set")]
    C[("Shard C<br/>typically a replica set")]
    App --> Driver
    Driver --> Router
    Router <-.->|"Fetch and refresh metadata"| Meta
    Router -->|"Routed reads/writes"| A
    Router -->|"Routed reads/writes"| B
    Router -->|"Routed reads/writes"| C
~~~

| Component | Responsibility | What not to confuse it with |
| --- | --- | --- |
| **Shard** | Stores and processes a portion of the data; typically deployed as a replica set. | A shard is not synonymous with a mongos process. |
| **Config server replica set (CSRS)** | Maintains cluster metadata, including how shard key value ranges are mapped to shards. | The config server is not where applications send every document read request. |
| **mongos** | Receives operations from clients, uses metadata to determine relevant shards, forwards requests, and merges results when needed. | mongos is a **router**, not the storage engine for application documents. |
| **Balancer** | Coordinates migrating data ranges between shards to address imbalance according to cluster policies. | Data balancing is a background administrative activity, not mongos's per-query processing responsibility. |

A cluster can deploy **multiple mongos** instances so the application has connection options if one router becomes unavailable. Although mongos can be viewed as a routing component with relatively little persistent state, it still maintains metadata caches and connections; it should not be assumed to be completely stateless in memory.

In MongoDB, a **database's primary shard** (where unsharded collections and certain related metadata reside) is a different concept from a **replica set's primary member** (the node that accepts writes). These two uses of the word "primary" are not interchangeable.

## 4. Shard key: the basis for distribution and routing

When a collection is sharded, MongoDB uses a **shard key** consisting of one or more document fields to determine which data ranges belong to each shard. Shard key value ranges are organized into data distribution units; storage locations can change when the cluster rebalances.

There are two common approaches:

1. **Range-based sharding:** distributes by ranges of key values; useful for certain range queries, though monotonically increasing keys over time can concentrate write load.
2. **Hashed sharding:** uses the hash value of the key field for distribution; can spread distinct key values evenly, but is not favorable for range queries on the hashed field.

For example, an order document:

~~~json
{
  "_id": "ord-9001",
  "tenantId": "tenant-204",
  "status": "PAID",
  "total": 240000,
  "createdAt": "2026-10-18T09:00:00Z"
}
~~~

If the **commerce.orders** collection is sharded with the key **{ tenantId: "hashed" }**, tenants can be distributed across multiple shards. Queries with an equality condition on tenantId usually allow mongos to determine the exact shard to access:

~~~javascript
db.orders.find({ tenantId: "tenant-204", status: "PAID" })
~~~

In contrast, the following query does not provide the shard key:

~~~javascript
db.orders.find({ status: "PAID" })
~~~

With this example configuration, mongos usually has to send the query to multiple shards and merge the results. That is **scatter-gather**. Each shard can still use a local index, but it incurs processing and data transfer overhead at the cluster level.

**Choosing a shard key is a critical architectural decision**, because it affects data distribution, write speed, and routing capability:

- **Cardinality:** there should be enough distinct key values so data has the opportunity to spread out.
- **Frequency distribution:** avoid having one value appear at an excessively high ratio and concentrate load.
- **Common queries:** important queries should be able to filter by the shard key; do not choose solely based on document structure.
- **Growth over time:** avoid creating hotspots when most new records fall into a single key range.
- **Update needs and data constraints:** examine update operations, unique indexes, and transactions in advance, as sharding imposes additional conditions.

With a hashed tenantId, different tenants can be spread evenly; however, **one extremely large tenant or heavy operations on just one tenant** can still cause a hotspot. In that case, evaluate a compound key or another data-partitioning strategy based on actual queries. No single shard key is optimal for every application.

## 5. What does mongos do when the application sends a request?

Consider a read operation sent by **MongoTemplate** or **MongoRepository** via the MongoDB Java Driver:

1. **The client connects to mongos.** The driver sends the MongoDB operation to an appropriate mongos router from the connection configuration.
2. **mongos determines the data scope.** The router uses its cached sharding metadata to analyze the shard key in the filter and identify shards that may contain matching data.
3. **mongos forwards the operation.** For targetable queries, the request goes to one shard or a small subset of shards; for queries without sufficient routing conditions, the request may go to multiple shards.
4. **The shards execute.** Each shard applies the query, indexes, and execution plan on the portion of data it manages.
5. **mongos aggregates the response.** The router may merge results, coordinate pagination/sorting, or execute aggregation merge stages according to the query plan, then return results to the driver.

If data locations have changed (for example, after a data range migration), mongos may have to **refresh metadata and retry routing** according to MongoDB's mechanisms. The application should not maintain its own map of "which tenant is on which shard": that detail belongs to the data cluster.

### Targeted query vs. scatter-gather

| Case (key { tenantId: "hashed" }) | Scope likely accessed | Implication |
| --- | --- | --- |
| Find by tenantId equal to a single value | Usually one data shard | Reduces participating shards and network traffic. |
| Find by tenantId and status | Usually one data shard | After routing, indexes on the shard still determine filtering speed. |
| Find by status only | Potentially all shards | Risks scatter-gather, especially as data and shard count grow. |
| Cluster-wide total revenue statistics | Potentially multiple or all shards | Requires analyzing aggregation, merge cost, and data volume. |

Good routing does not mean a query is already optimized: a targeted query is still slow if it scans too many documents on the target shard. Conversely, scatter-gather is not always a bug; it may be acceptable for infrequent analytical queries, but it must be identified and measured.

### Role of mongos in aggregation

For an aggregation pipeline, MongoDB can execute eligible stages on each shard and then perform the **merge** portion on the appropriate component depending on the version and execution plan. A **$match** condition containing the shard key at the start of the pipeline often creates an opportunity to reduce participating shards or reduce data transferred. Stages like **$group**, **$sort**, and **$lookup** on large datasets can increase distributed execution cost.

Spring Data MongoDB builds the pipeline for developers, but **it does not automatically turn a pipeline without a shard key into a targeted query**. Always inspect the execution plan and actual data volume.

## 6. Illustrative setup on MongoDB

The example below assumes you already have a working **sharded cluster**, appropriate administrative privileges, and **mongosh connected to mongos**. Run in a test environment before applying to a system with real data.

~~~javascript
// Select the business database.
use commerce

// Hashed index used for the shard key (especially important to consider
// before sharding a collection that already contains data).
db.orders.createIndex({ tenantId: "hashed" })

// Shard the collection by the hashed value of tenantId.
sh.shardCollection("commerce.orders", { tenantId: "hashed" })

// Index serving business query patterns within each shard.
db.orders.createIndex({ tenantId: 1, status: 1, createdAt: -1 })
~~~

Explanation:

- The **sh.shardCollection** command declares the collection's shard key. Index preparation steps and sharding prerequisites also depend on existing data and the MongoDB version.
- The **shard key index** helps MongoDB manage the sharding structure. The **business query index** helps each shard find documents quickly after mongos routes the request.
- Sharding does not mean all documents are evenly distributed the moment the command runs. Actual distribution depends on data volume, the shard key, and the balancing process.
- Once a collection is sharded, changing the shard key strategy requires an intentional process, depending on the capabilities and limitations of the running version.

You can verify from a **mongosh session connected to mongos**:

~~~javascript
sh.status()

use commerce

db.orders.find({ tenantId: "tenant-204", status: "PAID" })
  .explain("executionStats")

db.orders.find({ status: "PAID" })
  .explain("executionStats")
~~~

Compare the participating shards, number of documents examined, number of documents returned, and execution time. Field structures in **explain** output vary by MongoDB version and query type; read the actual plan rather than relying on a fixed stage name.

## 7. Connecting from Spring Data MongoDB

In a Spring Data MongoDB application, **mongos sits between the MongoDB Java Driver and the shards**. The repository layer or MongoTemplate does not need to know which shard each document resides on.

Example connection configuration of a Spring Boot application using the **spring.data.mongodb.uri** property:

~~~yaml
spring:
  data:
    mongodb:
      uri: "mongodb://mongos-a.example.net:27017,mongos-b.example.net:27017/commerce?retryWrites=true"
~~~

These are illustrative addresses and must be replaced with the endpoints provided for the actual cluster. For managed MongoDB services, use the connection string provided by the vendor, along with TLS and authentication credentials per system policy. Configuration property syntax may differ across Spring Boot versions; always check the version in use.

Example document mapping and query:

~~~java
import java.time.Instant;
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.stereotype.Service;

@Document(collection = "orders")
record Order(
    @Id String id,
    String tenantId,
    String status,
    Instant createdAt
) {}

interface OrderRepository extends MongoRepository<Order, String> {
    List<Order> findByTenantIdAndStatus(String tenantId, String status);
}

@Service
class OrderLookupService {
    private final MongoTemplate mongoTemplate;

    OrderLookupService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    List<Order> findPaidByTenant(String tenantId) {
        Query targeted = Query.query(
            Criteria.where("tenantId").is(tenantId)
                    .and("status").is("PAID")
        );
        return mongoTemplate.find(targeted, Order.class);
    }
}
~~~

In a real project, these classes should be placed in their respective Java files. The example uses **constructor injection** so Spring supplies MongoTemplate to the service; each query passes the active tenantId into the filter.

**What to understand when reading the code:**

- **@Document** maps the Java class to the **orders** collection; the record must contain the **tenantId** field matching the created shard key.
- **MongoRepository** and **MongoTemplate** construct the filter and send it via the driver. **mongos**, based on the shard key and metadata, is what performs routing.
- Both query approaches can target the destination shard if the filter contains an appropriate shard key condition.
- If you only call **findByStatus("PAID")**, the application still works at the API level, but the query may have to hit multiple shards. Repository convenience does not eliminate distributed execution costs.
- Create and reuse the **MongoClient**/connection pool at the application scope; do not create a new client per request.

For write operations, design documents and update/delete filters to carry shard key information where appropriate. An update filtering by tenantId and order ID is easier to route and control than a query that omits tenantId. Certain operations on sharded collections also have specific requirements depending on the MongoDB version.

## 8. Limitations and costs to plan for upfront

### Skewed load and hotspots

A single shard can receive the majority of writes if the shard key increases monotonically or if one shard key value is disproportionately common. Increasing the number of shards may not solve this if the workload continuously hits the same data range. Evaluate key distribution using real data and access patterns.

### Cross-shard queries

Queries missing the shard key may need to access multiple shards, increasing connections, I/O, and data transfer. Large result sets, sorting, and cross-shard aggregations require special attention. Local indexes remain important, but indexes do not replace the shard key for routing.

### Transaction overhead

MongoDB supports transactions that can span multiple shards in appropriate configurations and versions, yet coordination across components increases latency and resource usage. With Spring Data MongoDB, **MongoTransactionManager** manages transactions at the framework level; it does not eliminate the cost of distributed transactions. Prefer document models and business boundaries that minimize operations spanning multiple shards.

### Unique constraints and data consistency

Unique indexes on a sharded collection have conditions tied to the shard key; you cannot assume that any unique index on a single shard automatically enforces cluster-wide uniqueness. When designing fields such as orderNumber, email, or business codes, check the limitations for your MongoDB version and specific shard key model.

### Operations, security, and availability

- Monitor storage skew, CPU/I/O usage, query speed, and latency across shards.
- Observe data balancing, topology changes, and metadata updates; all of these can affect latency.
- Configure multiple mongos instances and appropriate connections to avoid depending on a single router.
- Protect connections to mongos with authentication, TLS, least-privilege permissions, and secure secret management.
- Deploy shards and config servers as replica sets in a fault-tolerant architecture; multiple mongos instances **cannot compensate** for an unavailable data shard.

## 9. Architecture selection scenarios

**Scenario A — Multi-tenant SaaS:** The application always sends queries with tenantId, and tenants are relatively uniform in size. A shard key based on tenantId is a strong benchmark candidate. If using hashed tenantId, note that one very large tenant can still cause heavy load on a single shard.

**Scenario B — Orders with time-based reporting:** 95% of queries read a single tenant, while 5% aggregate system-wide revenue. Sharding can serve the tenant query group well; the reporting group may have to run across multiple shards and require pipeline optimization, indexes, or a dedicated analytics pipeline.

**Scenario C — Low data volume, low writes, high availability requirement:** A well-operated replica set can be simpler and more appropriate. Sharding is not a prerequisite for failover.

**Scenario D — One customer generates the majority of data:** Choosing tenantId as the sole shard key risks concentrating write volume onto a single shard, even when the cluster has many shards. Investigate compound keys, access distribution, and potential storage model changes before finalizing.

## 10. Deployment verification checklist

1. **Define the reason for scaling:** storage capacity, write load, read load, or all three? Have queries/indexes and a single replica set already been optimized?
2. **Collect workload profile:** frequently used filters, ratio of queries with the shard key, document sizes, key frequency distribution, and growth trends.
3. **Choose the shard key based on metrics:** project targeted queries, hotspots, large data ranges, and balancing feasibility.
4. **Design Spring Data MongoDB connectivity:** use supported mongos/cluster endpoints, appropriate connection pooling, TLS, authentication, and timeouts.
5. **Measure in a staging environment:** compare explain plans, throughput, p95/p99 latency, data scanned, and participating shards between queries with and without the shard key.
6. **Monitor post-deployment:** track data distribution, balancing, router/shard errors, and cross-shard transactions; adjust based on metrics.

### Self-check questions

**1. If mongos stops, are documents deleted?** No. mongos is not where documents are stored. However, clients using that router may lose connectivity until they fail over to an available router/endpoint.

**2. If a query has an index on every shard but lacks the shard key, does mongos know which shard holds the results?** Usually it cannot determine that from the index alone; the query may still have to go to multiple shards.

**3. Does adding more shards increase throughput linearly?** No. Network overhead, coordination, balancing, hotspots, cross-shard queries, and resource limits can make actual gains significantly lower.

**4. Does Spring Data MongoDB need a special API to choose a shard?** No. The application uses repositories or MongoTemplate as usual; what matters is that the data model, filters, and shard key enable mongos to route effectively.

## Conclusion

Sharding scales MongoDB by splitting data across multiple shards. **mongos is the request routing point**: it receives operations from the driver, relies on metadata and the shard key to select appropriate shards, forwards requests, and aggregates results when needed. In a Spring Data MongoDB application, the benefits of sharding do not come from a special MongoTemplate or repository API, but from designing the **shard key, queries, indexes, and cluster operations**. Always validate with real workloads and execution plans before deciding to scale horizontally.
