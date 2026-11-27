# Shards, Replicas, Routing, and the Risk of Uneven Shard Load

Elasticsearch divides an index into multiple primary shards. Each document is stored on one shard, while replicas are copies of primary shards placed on other nodes for fault tolerance and read support. Routing determines which shard receives a document and which shards a search request needs to query.

These three mechanisms directly impact performance, yet solve different problems. Adding replicas can increase search capacity and improve availability; it does not split the write load of a single primary shard. Custom routing can reduce the number of shards searched, yet if the routing key is skewed, one shard can become a hotspot. Increasing shard counts also does not automatically fix every kind of imbalance.

This lesson explains the relationship between shards, replicas, and routing; distinguishes data imbalance from load imbalance; shows how to identify hot shards; covers choosing a routing strategy; and demonstrates how to configure, observe, and tune indexes in Spring Data Elasticsearch applications.

## 1. Primary shards and replica shards

An index is divided into one or more primary shards. Each primary shard is an independent data partition. Elasticsearch distributes primary shards and their copies across nodes in the cluster according to allocation policies.

For example, an `orders` index with three primary shards and one replica per primary:

~~~text
Index: orders

Node A                 Node B                 Node C
+----------------+     +----------------+     +----------------+
| Primary shard 0|     | Primary shard 1|     | Primary shard 2|
| Replica shard 1|     | Replica shard 2|     | Replica shard 0|
+----------------+     +----------------+     +----------------+
~~~

This diagram illustrates just one possible placement. Elasticsearch may choose other nodes based on node count, allocation awareness, disk watermarks, shard limits, and cluster state. A shard copy cannot be placed on the same node as the primary or another replica copy of that same shard.

### Primary shard

A primary shard holds the authoritative copy of a portion of an index's data. When a document is indexed, Elasticsearch determines the target shard and sends the operation to the corresponding primary shard. The primary processes the operation and coordinates replication to active replicas.

A primary shard is also the unit of data distribution and most write work. An overloaded primary shard can throttle write throughput for documents routed to it, even when other shards are idle.

### Replica shard

A replica is a copy of a primary shard. Replicas serve two main roles:

- Providing failover copies if the node holding a primary fails.
- Allowing search requests to be served from different shard copies, thereby increasing read capacity in many workloads.

A replica is not an extra data partition. It holds the exact same documents as its corresponding primary. Adding replicas increases required storage and replication work on writes.

A replica copy of shard 0 cannot sit on the same node holding primary shard 0. If the cluster lacks enough eligible nodes, replicas remain unassigned.

### Primary count and replica count differ

Primary shard count determines how the index is split into data partitions. Replica count determines how many extra copies exist for each primary.

- Primary shard count affects data distribution and parallelism.
- Replica count affects redundancy, read capacity, and storage/replication cost.
- Replica count can be changed dynamically via index settings.
- Primary shard count cannot be changed arbitrarily in place after an index is created. Changing primary layout usually requires splitting, shrinking, or reindexing into a new index under eligible conditions.

Do not increase primary shards just to fix a slow query before identifying the root cause.

## 2. How Elasticsearch distributes documents to shards

When indexing a document without specifying custom routing, Elasticsearch uses the document ID as the default routing value. The routing value is hashed and mapped onto a primary shard of the index.

You can visualize it as:

~~~text
document ID or custom routing
              |
              v
          hash value
              |
              v
     primary shard count
              |
              v
      target primary shard
              |
              v
     corresponding replicas
~~~

Example:

~~~http
POST /orders/_doc/O-100
{
  "orderId": "O-100",
  "tenantId": "tenant-A",
  "amount": 120.5
}
~~~

No routing is passed, so document ID `O-100` serves as the default routing value.

If the application specifies routing:

~~~http
POST /orders/_doc/O-100?routing=tenant-A
{
  "orderId": "O-100",
  "tenantId": "tenant-A",
  "amount": 120.5
}
~~~

Elasticsearch uses `tenant-A` to pick the shard. Documents sharing the same routing value in the same index are routed consistently to the same primary shard, unless partitioned routing is enabled.

### Hash distribution does not guarantee balanced real-world load

Hash routing spreads routing values fairly evenly when there are enough keys and each key carries similar workload. However, hashing does not know whether one tenant has a hundred documents or a hundred million documents.

For example, suppose there are 10,000 tenants, yet one large tenant owns 60% of all documents. If all documents for that tenant share one custom routing value, most data and operations for that tenant concentrate onto a single shard.

Another scenario is evenly distributed document counts where one tenant generates far higher search or update traffic. Load imbalance occurs even before shard sizes diverge significantly.

## 3. What is routing used for?

Custom routing lets the application choose a business-meaningful routing key such as tenant ID, account ID, or customer ID.

When indexing:

~~~http
PUT /orders/_doc/O-100?routing=tenant-A
{
  "orderId": "O-100",
  "tenantId": "tenant-A",
  "status": "OPEN"
}
~~~

When searching with the same routing:

~~~http
GET /orders/_search?routing=tenant-A
{
  "query": {
    "term": {
      "tenantId": "tenant-A"
    }
  }
}
~~~

If all documents for `tenant-A` live on a single shard, routed searches can query only that shard instead of fanning out to every primary shard in the index.

Routing can reduce:

- Number of shards participating in a search.
- Cross-shard result coordination overhead.
- Intermediate data volume in tenant-scoped queries.
- Lookup cost by ID when the routing value is known.

Routing also imposes an operational constraint: `get`, `update`, and `delete` operations by ID must supply the same routing value used during indexing. If routing is omitted or wrong, Elasticsearch may fail to find the document even though it exists on another shard.

### Search routing and document filtering are two different things

Routing picks which shard copies handle the request. Query DSL picks which documents are returned from those shards.

If multiple tenants share the same shard, passing `routing=tenant-A` without a tenant filter in the query can return another tenant's documents residing on that shard. Routing is not a security filter and does not replace tenant predicates in queries.

## 4. How do replicas affect load?

When a search request needs to read a shard, Elasticsearch can pick one of the active copies of that shard. Multiple copies allow search requests to spread across primaries and replicas.

For example, an index with one primary and two replicas per shard:

~~~text
Shard 0 copies:
  Primary 0  -> Node A
  Replica 0  -> Node B
  Replica 0  -> Node C

Search requests:
  Request 1 -> Node A
  Request 2 -> Node B
  Request 3 -> Node C
~~~

This diagram illustrates request distribution capability. Actual copy selection also depends on cluster state, preference, adaptive replica selection, and load/latency signals.

### Replicas help reads, not split primary writes

Every write operation still goes through the corresponding primary shard. The primary coordinates replication to replicas. Thus, adding replicas can boost search capacity and availability, without splitting a hot primary shard into independent primaries.

Replicas also consume resources:

- Disk space for copies.
- Network bandwidth for replication.
- CPU and I/O for indexing, merges, and recovery.
- Recovery duration when nodes or shard copies must rebuild.

If the workload is write-heavy and one primary shard is overloaded by routing skew, adding replicas increases cost without fixing the main bottleneck.

### Changing the replica count

Replica counts can be updated via index settings:

~~~http
PUT /orders/_settings
{
  "number_of_replicas": 2
}
~~~

This instructs Elasticsearch to allocate additional or remove existing replica copies. Allocation still depends on node count, allocation rules, and cluster resources.

On a single-node cluster, replicas normally cannot be assigned to the same node as primaries and remain unassigned. That may be expected in development, whereas production needs enough nodes and configuration for desired redundancy.

### wait_for_active_shards is neither authorization nor a transaction

Write requests can require a number of active shard copies before proceeding, such as `wait_for_active_shards`. This checks shard-copy availability prior to the write. It does not alter shard selection, roll back requests like a transaction, or fix routing skew.

## 5. Types of shard imbalance

Not all imbalances are alike. Before changing settings, identify what kind of imbalance you are seeing.

### Size imbalance

Some shards store noticeably more data than others. Causes include:

- Uneven document distribution across custom routing keys.
- A large tenant owning most of the data.
- One group of documents having huge `_source` payloads.
- Historical data concentrated on a subset of keys.
- Index created with an unsuitable shard count.

Oversized shards can require more disk, heap for metadata/segments, and longer recovery times.

### Write-load imbalance

One shard receives more indexing/update requests than others. Common causes:

- A routing key with high write volume.
- A tenant with heavy workload.
- Producers distributing messages unevenly.
- A data category always written to the same route.
- Retries piling onto an already-overloaded shard.

A shard can be hot even when its data size is not the largest.

### Read-load imbalance

One shard receives more search requests or CPU-heavy queries. Possible causes:

- Many requests routing to one large tenant.
- One tenant generating high traffic.
- Queries hitting a shard with many documents or large fields.
- Search routing continually targeting the same shard.
- Differing caches, segments, and workloads across shards.

Replicas can help distribute read load across shard copies. However, if requests target one routing key, they still target only that shard and its replica copies.

### Node allocation imbalance

The number of shard copies or total disk usage across nodes can be uneven. Causes include:

- New nodes joining or nodes leaving.
- Disk watermarks.
- Allocation awareness.
- Allocation filtering.
- Active shard recoveries.
- Differing node roles and resources.

Elasticsearch can relocate shard copies between nodes to balance allocation. This does not split one large shard into smaller shards and does not redistribute documents inside a shard.

## 6. What is a hot shard?

A hot shard is a shard receiving significantly higher load or work than other shards. It can become the bottleneck for the entire index.

Example:

~~~text
Index orders - write operations per minute

Shard 0:  1,200
Shard 1:    180
Shard 2:    160
Shard 3:    190
Shard 4:    170
Shard 5:    200
~~~

Shard 0 receives several times more writes than the rest. Even when the overall cluster has free CPU and disk, requests targeting shard 0 can still slow down or be rejected.

### Signs of a hot shard

- Bulk requests exhibit unusually high latency.
- 429 or indexing rejection rates rise.
- One shard has a much higher indexing rate than others.
- A node hosting the hot shard shows high CPU, disk I/O, or indexing pressure.
- Search latency varies by routing key.
- Certain tenants experience slowness while others remain fast.
- Recovery or merges on the hot shard drag on.

Do not diagnose a hot shard purely from node CPU. One node can host multiple shards; correlate node metrics with shard copies and per-index workload.

### Hot nodes and hot shards are not the same

A hot node is a node under high load. A hot shard is a shard experiencing heavy workload. A hot node may simply hold many active shards, simultaneous merges, or recoveries. A hot shard may sit on a node with overall resource headroom while that specific shard is throttled by its workload or data layout.

Distinguish both levels to pick the right remediation.

## 7. Routing skew and why custom routing can backfire

Routing keys with low cardinality or skewed workloads easily create hot shards.

For example, using `status` as routing:

~~~text
routing = status

OPEN     -> shard 0
PAID     -> shard 2
CANCELLED-> shard 1
~~~

If most orders are in `OPEN` status, the shard chosen for `OPEN` receives most documents and operations. Low-cardinality keys concentrate data heavily.

Using tenant ID can work well if there are enough tenants of comparable size. Yet if a very large or high-traffic tenant exists, that single tenant can overheat a shard.

### Common causes

1. **Low cardinality:** too few routing keys relative to shard count.
2. **Storage skew:** a few keys hold vastly more documents.
3. **Traffic skew:** one key receives far more requests.
4. **Unstable keys:** the same entity is indexed under different routing values.
5. **Hot tenant:** one large tenant occupies a shard or group of shards with most of the load.
6. **Unbalanced batches:** one worker processes routing keys concentrated onto one shard.
7. **Overly narrow search routing:** many requests repeatedly hit the same shard while others sit idle.

Custom routing is not automatically better than default routing. Use it only when fan-out reduction or partitioning benefits are clearly measured.

## 8. Choosing a routing key

A routing key should meet several criteria:

- High enough cardinality to spread data.
- Stable over the document's lifecycle.
- Known at index time as well as at get/update/delete time.
- Aligned with common query patterns.
- Free of a few excessively hot keys.
- Does not leak sensitive information if routing appears in logs or request traces.

Common options:

| Routing key | Advantages | Risks |
|---|---|---|
| No custom routing, use document ID | Distribution is usually even when IDs are sufficiently random | Searches may fan out across the whole index |
| Tenant ID | Tenant-scoped queries can cut shard fan-out | Large tenants can create hot shards |
| Customer ID | Customer-scoped queries can hit one shard | Heavy customers can accumulate data/load |
| Account ID | Fits account-scoped access workloads | Large accounts can run hot |
| Status/category | Easy grouping by type | Low cardinality and typically skewed distribution |
| Tenant + bucket | Splits large tenants across multiple routes | Tenant queries must target multiple buckets |
| Random per-document | Even distribution in some cases | Does not optimize tenant-scoped searches |

Do not pick a routing key merely because the field appears often in queries. Weigh fan-out savings against the risk of uneven data and traffic distribution.

## 9. Partitioned routing for large tenants

Elasticsearch supports partitioned routing via the `index.routing_partition_size` index setting. Instead of mapping one routing value to a single shard, one routing value can be distributed across a subset of shards. The document ID participates in choosing a shard within that partition.

This keeps a large routing key from dumping all its documents onto one shard. Searches with the same routing value query that partition's shards rather than scanning the whole index.

Example index creation:

~~~http
PUT /orders
{
  "settings": {
    "number_of_shards": 12,
    "number_of_replicas": 1,
    "index.routing_partition_size": 3
  },
  "mappings": {
    "_routing": {
      "required": true
    },
    "properties": {
      "tenantId": {
        "type": "keyword"
      },
      "status": {
        "type": "keyword"
      }
    }
  }
}
~~~

This example illustrates 12 primary shards and a partition size of 3. A routing value spreads across a subset of three shards per Elasticsearch's partitioned routing algorithm.

### Trade-offs of partitioned routing

- A single tenant can write across multiple shards in its partition.
- Tenant searches must query the shards belonging to that partition.
- More shards are queried than with single-shard custom routing.
- Write distribution for large tenants improves.
- Partition size must be chosen at index design time; it cannot be treated as an arbitrary setting to change on an already-populated index.

Partitioned routing is worth considering when large routing keys need load spreading while keeping key-scoped queries from fanning out across the entire index. Check limits and configuration rules for your Elasticsearch version.

## 10. Composite routing and tenant bucketing

Another approach constructs the routing value from tenant ID and a bucket:

~~~text
routing = tenantId + "#" + bucketNumber
~~~

The bucket can be derived from the order ID or a deterministic hash:

~~~java
int bucket = Math.floorMod(
    orderId.hashCode(),
    bucketCount
);

String routing = tenantId + "#" + bucket;
~~~

Example with 8 buckets for `tenant-A`:

~~~text
tenant-A#0 -> shard 0
tenant-A#1 -> shard 3
tenant-A#2 -> shard 5
tenant-A#3 -> shard 1
tenant-A#4 -> shard 4
tenant-A#5 -> shard 2
tenant-A#6 -> shard 0
tenant-A#7 -> shard 5
~~~

Shard mappings in the diagram are illustrative. Hash routing can still map multiple buckets to the same shard.

### Benefits

- Writes for large tenants spread across multiple routing keys.
- A worker or partition queue can handle a subset of buckets independently.
- Bucket count can be tuned to workload.

### Costs

- When searching all orders of a tenant, the application must query all buckets for that tenant or omit routing and search with a tenant filter.
- Get/update/delete by ID must recompute the exact original bucket/routing value.
- Bucket count and hash algorithm must remain stable.
- Changing bucket count requires migration or versioned routing strategies.
- More buckets do not guarantee each bucket lands on a distinct shard.

Composite routing trades off write distribution against query fan-out. Do not inflate bucket counts indiscriminately when tenant-wide search is the dominant workload.

## 11. Does increasing primary shards solve hot shards?

Adding primary shards can help spread documents and load when the index is structured appropriately. However, it does not automatically cure every hot shard.

For example, suppose an index initially has three primary shards. If every document of `tenant-A` uses unpartitioned custom routing `tenant-A`, creating a new index with twelve primary shards still routes all `tenant-A` documents onto a single shard.

Raising shard counts while keeping the same hot routing key may only change which shard ID is picked, without eliminating the hotspot.

### When does increasing shard count help?

- Existing shards are too large and data needs splitting.
- Default ID routing spreads evenly, yet shard count is too low to utilize the cluster.
- Workloads benefit from higher shard parallelism.
- Expected growth requires a new index sized with more shards.

### When does it not help?

- One tenant using one routing key drives most traffic.
- One heavy query targets a single route.
- Nodes suffer disk/CPU bottlenecks independent of shard count.
- Mappings or queries trigger expensive scans/aggregations.
- Replica placement or allocation constraints are the root cause.

Primary shard count should be chosen based on expected data size, node count, workload, and recovery capacity. Avoid over-sharding because every shard adds heap, segment metadata, file handle, cluster state, and coordination overhead.

## 12. Shard sizing and shard count

There is no single shard size fitting all indexes. Appropriate shard size depends on:

- Source and index storage size.
- Document count.
- Field count and mapping types.
- Segment count and merge activity.
- Update/delete frequency.
- Ingest rate.
- Query latency and concurrency.
- Node heap, disk, and network.
- Acceptable recovery time.

Oversized shards slow recovery, make merges heavier, and cap parallelism. Too many small shards add substantial cluster overhead and make search fan-out expensive.

Operational guidelines often start testing around tens of gigabytes per shard, though this is not a hard rule. Benchmark with data and workloads close to production.

### Evaluating with real data

Measure at least:

- Primary shard size.
- Replica shard size.
- Document count per shard.
- Indexing throughput.
- Search latency p50/p95/p99.
- Recovery duration.
- Merge time and segment counts.
- Disk utilization and heap pressure.

An index with six equally sized shards can still suffer traffic imbalance. Conversely, shards of differing sizes are not necessarily problematic if workload and latency remain within targets.

## 13. Allocation and shard balancing across nodes

Elasticsearch cluster allocation decides which node holds each shard copy. Cluster allocation can balance shard counts and disk space subject to active constraints.

Influencing factors:

- Disk watermarks.
- Shard allocation awareness.
- Allocation filtering.
- Node attributes.
- Node roles.
- Shard limits.
- Active recoveries and relocations.
- Cluster allocation explain decisions.

### Zone or rack awareness

For fault tolerance, assign node attributes like `zone` and configure allocation awareness. Elasticsearch tries to spread shard copies across different failure domains when enough eligible nodes exist.

Example node attribute:

~~~yaml
node.attr.zone: zone-a
~~~

Cluster setting:

~~~http
PUT /_cluster/settings
{
  "persistent": {
    "cluster.routing.allocation.awareness.attributes": "zone"
  }
}
~~~

This is an example configuration. Configure attributes on nodes and ensure the cluster has enough zones. If a zone lacks nodes, some replicas may remain unassigned to satisfy awareness constraints.

Awareness improves placement fault tolerance. It does not balance document counts or traffic inside a shard.

### Allocation filtering

Shards can be restricted to nodes based on attributes, such as hot/warm tiers or specialized nodes. This helps organize resources, though misconfigured filters can leave shards with no eligible nodes and keep them unassigned.

Do not treat allocation filtering as a way to split documents inside a shard. A shard copy moves intact between nodes; its internal documents stay in the same shard.

## 14. Search load balancing and adaptive replica selection

For a shard with a primary and multiple replicas, search requests can be sent to any eligible shard copy. Elasticsearch uses adaptive replica selection based on performance and response-time metrics.

This distributes search traffic across nodes holding copies of that shard. However:

- It does not create extra shards.
- It does not split a primary shard into smaller pieces.
- It cannot rescue a routing key whose traffic overwhelms every copy.
- It does not shrink the data a query must process on a shard.
- It does not replace query tuning or routing design.

If a hot tenant sends all searches to one shard, replicas can distribute requests across node copies, yet every request still performs the full work on that shard.

### Preference and cache locality

Search `preference` can influence copy selection and request stickiness across calls. Using `preference` appropriately can improve cache locality in some workloads, while pinning all requests to a single node or copy can create a hot node.

Do not hardcode `preference` just to make results appear consistent without measuring its impact on load and caches.

## 15. Routing in Spring Data Elasticsearch

Spring Data Elasticsearch supports marking an entity property for routing with the `@Routing` annotation.

Example:

~~~java
@Document(indexName = "orders")
public class Order {

    @Id
    private String id;

    @Routing
    @Field(type = FieldType.Keyword)
    private String tenantId;

    @Field(type = FieldType.Keyword)
    private String status;

    // getters and setters
}
~~~

When using entity-aware Spring Data operations, routing metadata can be extracted from the annotated property. This lets entity-based saves or reads apply the route per your version's contract.

Check the exact API of your Spring Data Elasticsearch version, especially for operations taking only IDs or `Query` objects. Do not assume every overload infers routing when no entity carrying the routing property is supplied.

### Setting the routing property server-side

Example order creation service:

~~~java
public Order createOrder(CreateOrderRequest request) {
    String tenantId = currentTenant.requireTenantId();

    Order order = new Order();
    order.setId(request.orderId());
    order.setTenantId(tenantId);
    order.setStatus("OPEN");

    return operations.save(order);
}
~~~

`tenantId` comes from a trusted context. Never accept an arbitrary tenant ID from the request body as the routing property.

### Routing when using the Java API Client directly

If calling the Elasticsearch Java API Client directly, routing is passed on the request:

~~~java
IndexResponse response = client.index(i -> i
    .index("orders")
    .id(order.getId())
    .routing(order.getTenantId())
    .document(order)
);
~~~

Searches should also pass the matching route:

~~~java
SearchResponse<Order> response = client.search(s -> s
    .index("orders")
    .routing(tenantId)
    .query(q -> q.term(t -> t
        .field("tenantId")
        .value(tenantId)
    )),
    Order.class
);
~~~

These are direct Java API Client requests. When using Spring Data Operations, routing is supplied via query or operation metadata according to the release train's API. Do not confuse direct client parameters with method signatures across every Spring Data version.

## 16. Configuring shards and replicas at index creation

Primary shard and replica counts can be declared in index settings:

~~~http
PUT /orders
{
  "settings": {
    "number_of_shards": 6,
    "number_of_replicas": 1
  },
  "mappings": {
    "properties": {
      "tenantId": {
        "type": "keyword"
      },
      "status": {
        "type": "keyword"
      },
      "createdAt": {
        "type": "date"
      }
    }
  }
}
~~~

The index has six primary shards and one replica per primary, totaling twelve shard copies when all replicas are allocated.

To adjust replica count after index creation:

~~~http
PUT /orders/_settings
{
  "number_of_replicas": 2
}
~~~

Primary shard count cannot be changed with the same setting update. To change primary counts, consider split/shrink or creating a new index and reindexing.

### Spring Data index creation from entities

Spring Data can create indexes from entity metadata and index settings configurations. For specific shard/replica layouts, use index settings resources or provision indexes via scripts/`IndexOperations` depending on your project's schema management approach.

Do not rely on an Elasticsearch version's default shard count across every environment. Manage index templates, settings, and mappings deliberately, and inspect the resulting index after creation.

If production uses aliases pointing to versioned indexes, create a new index with desired settings and switch the alias after reindexing and verifying data.

## 17. Diagnosing shard imbalance

Start with shard status:

~~~http
GET /_cat/shards/orders?v
~~~

This displays shard ID, primary/replica, state, node, and disk size. It helps spot which nodes hold shard copies and whether sizes diverge.

Inspect index stats:

~~~http
GET /orders/_stats/indexing,search,store,segments
~~~

Inspect node stats:

~~~http
GET /_nodes/stats/indices,thread_pool,fs
~~~

Inspect concise node health:

~~~http
GET /_cat/nodes?v&h=name,roles,cpu,heap.percent,ram.percent,disk.used_percent
~~~

Inspect thread pools:

~~~http
GET /_cat/thread_pool/write,search?v
~~~

Metric names and granularity can differ across Elasticsearch versions. These APIs require appropriate monitoring permissions.

### Reading metrics layer by layer

1. Compare shard sizes to spot data skew.
2. Compare indexing/search stats to spot traffic skew.
3. Map shards to nodes to detect node placement skew.
4. Check thread pool queues/rejections to identify real pressure.
5. Check disk, heap, CPU, and I/O to pinpoint limiting resources.
6. Compare application-side latency per tenant or routing key.
7. Check whether queries and bulk requests concentrate on a single route.

Do not look solely at cluster-wide average CPU. A cluster with low average CPU can still have one shard or node locally saturated.

### Using allocation explain for unassigned shards

If replicas are unassigned, ask Elasticsearch to explain:

~~~http
GET /_cluster/allocation/explain
{
  "index": "orders",
  "shard": 0,
  "primary": false
}
~~~

The output identifies which allocation decider blocks assignment, such as disk watermarks, awareness rules, or lack of eligible nodes.

Never force shard allocation manually without understanding why it failed. Doing so improperly can reduce fault tolerance or cause data loss.

## 18. Remediations by root cause

### Case A: one tenant creates a hot shard

Approaches:

- Move large tenants to dedicated indexes if operational benefits justify it.
- Use partitioned routing to spread one routing key across multiple shards.
- Use composite routing with stable buckets.
- Isolate write-heavy workloads into suitable indexes.
- Cap concurrency or ingest rate for hot tenants.

Account for increased query fan-out when splitting a tenant across multiple buckets.

### Case B: many small shards and high search fan-out

Approaches:

- Create a new index with a more suitable primary shard count.
- Reindex or rollover according to data lifecycle strategy.
- Lower shard count in new indexes via shrink when preconditions allow.
- Optimize queries to avoid unnecessary fan-out.
- Avoid creating tiny per-tenant indexes if the cluster ends up managing thousands of shards.

### Case C: high read load with stable writes

Approaches:

- Increase replicas if nodes and disks have capacity headroom.
- Check search load balancing and replica allocation.
- Optimize queries, filters, sorts, and aggregations.
- Use routing where query patterns allow cutting shard fan-out.
- Cache at the application layer for repeated reads if semantics permit.

Adding replicas does not guarantee every query speeds up. Heavy queries on a shard still process large volumes of data.

### Case D: hot node due to uneven allocation

Approaches:

- Check allocation explain and awareness settings.
- Check disk watermarks and node roles.
- Add appropriate nodes if cluster capacity is insufficient.
- Adjust allocation filters carefully.
- Wait for relocations/recoveries to finish and monitor load.
- Check whether oversized or highly active shards are concentrated on one node.

Avoid continually moving shards while the cluster is overloaded; relocation also consumes network and disk I/O.

### Case E: high index-wide write load

Approaches:

- Add ingest capacity with appropriate nodes and resources.
- Tune bulk size/concurrency based on metrics.
- Lower refresh frequency during bulk ingestion if use cases permit.
- Optimize mappings and remove unnecessary fields.
- Reduce frequent in-place updates through better data modeling.
- Consider rollover to partition data over time.

Do not simply add replicas to solve a write bottleneck.

## 19. Rollover, ILM, and time-based data partitioning

For time-series append workloads such as logs, events, or telemetry, a single ever-growing index causes shards to grow indefinitely. Rollover creates a new index when age, document count, or size thresholds are met.

Example aliases:

~~~text
events-write -> events-000001
events-read  -> events-000001, events-000002, ...
~~~

After rollover:

~~~text
events-write -> events-000002
events-read  -> events-000001, events-000002
~~~

Each backing index has its own shard/replica settings. ILM can transition indexes across phases and perform rollover, shrink, or deletion according to policy.

Rollover helps manage lifecycle and bound index sizes. It does not automatically resolve a hot routing key if all events of a large tenant still land on the same shard within each backing index.

When designing time-based indexes, determine whether tenant routing is still necessary or default ID routing suffices. If queries always filter by time range and tenant, consider appropriate aliases, data streams, and filter strategies.

## 20. Impact of routing and shards on bulk indexing

A bulk request can contain documents belonging to different shards. Elasticsearch dispatches operations to their target primary shards. If a batch is unevenly distributed, a single hot shard can delay completion of the whole batch.

Example:

~~~text
Bulk batch: 1,000 operations

Shard 0: 800 operations
Shard 1:  50 operations
Shard 2:  40 operations
Shard 3:  35 operations
Shard 4:  25 operations
Shard 5:  50 operations
~~~

The overall batch is not huge, yet most operations concentrate on shard 0. Adding bulk workers can overload that shard faster.

### Producer adjustments

- Monitor routing key distribution inside batches.
- Bound concurrency per workload.
- Use backoff on 429s.
- Avoid having multiple workers concurrently push data for the same hot tenant.
- Consider partitioning producers by routing key or bucket.
- Measure latency and rejection counts per shard/tenant where possible.

Do not split batches purely by document count when payload sizes and routing distributions vary widely.

## 21. Example strategy selection for an order system

Suppose a system serves 500 tenants:

- 450 small tenants, each under 100,000 orders.
- 45 medium tenants, each with several million orders.
- 5 very large tenants, each with tens of millions of orders.
- Most searches look up orders by tenant and time range.
- Several large tenants generate many times more traffic.

A possible design:

1. Use tenant ID as routing for most tenants if benchmarks show significant fan-out savings.
2. Isolate the very large tenants into dedicated indexes or apply partitioned routing.
3. Keep `tenantId` as a `keyword` field for filtering in every query.
4. Set replica counts based on read throughput and availability needs.
5. Use time partitioning/rollover if data lifecycle fits.
6. Monitor hot shards and per-tenant traffic to adjust.
7. Manage index templates and aliases for controlled schema/settings evolution.

No single design fits every system. If tenants are small and workloads lack significant skew, default document-ID routing can be simpler and better balanced than custom routing.

### How to benchmark

Compare at least three options:

- Default routing by document ID.
- Custom routing by tenant ID.
- Partitioned/composite routing for large tenants.

Measure:

- Index throughput.
- Bulk latency p50/p95/p99.
- Search latency per tenant.
- Shard size distribution.
- Search shard fan-out.
- 429/rejected operations.
- CPU, heap, disk I/O, and network.
- Recovery duration after node failure.

Use a workload with production-like tenant distribution. Benchmarking with uniform tenants can mask hot-tenant issues.

## 22. Common pitfalls

| Symptom or assumption | Cause | How to address |
|---|---|---|
| Added replicas yet writes stay slow | Hot primary still handles all writes | Fix routing skew or scale shard write capacity |
| Raised primary shards yet large tenant stays hot | Single routing key still selects one shard | Partitioned/composite routing or isolate tenant |
| One node holds far more shards | Allocation rules and node resources differ | Check allocation, awareness, and disk |
| Shard sizes match yet latencies diverge | Traffic/query costs differ | Measure per-shard indexing/search load |
| Tenant-scoped searches stay slow | Query lacks routing or proper tenant filter | Check routes, queries, and fan-out |
| Missing routing during get by ID | Original route not stored/supplied | Use `@Routing` property or pass route explicitly |
| Replicas unassigned | Insufficient nodes or allocation rule blocks it | Check allocation explain |
| Cluster has too many small shards | Over-sharding and too many indexes | Rollover, shrink/reindex, and manage shard counts |
| One tenant consumes most storage | Data skew | Isolate tenant or partition routes |
| Raising bulk concurrency triggers more 429s | Hot shard or cluster indexing pressure | Lower concurrency, backoff, tune batches |
| Changed tenant routing yet docs did not move | Source field does not rewrite shard metadata | Reindex/migrate with new routing |
| Search routing treated as security filter | Confused shard selection with document filtering | Add tenant filters and authorization |

## 23. Shard, replica, and routing design checklist

- [ ] Determine primary shard count from expected data volume and workload.
- [ ] Do not over-shard just to raise parallelism.
- [ ] Choose replica count based on availability and read throughput.
- [ ] Ensure replica copies can be allocated across distinct nodes.
- [ ] Remember replicas do not split primary write workloads.
- [ ] Use custom routing only with matching query patterns and measured gains.
- [ ] Choose routing keys with appropriate cardinality and distribution.
- [ ] Measure data skew and traffic skew separately.
- [ ] Check for hot tenants and hot shards.
- [ ] Consider partitioned routing for oversized routing keys.
- [ ] Evaluate query fan-out costs when using bucket routing.
- [ ] Keep routing values immutable over document lifecycles.
- [ ] Always include explicit tenant filters even when routing by tenant.
- [ ] Configure zone/rack awareness if availability requires it.
- [ ] Monitor shard allocation, disk watermarks, and recoveries.
- [ ] Use replicas to support reads and redundancy where appropriate.
- [ ] Benchmark with production-like data and traffic distributions.
- [ ] Manage primary shard changes via new indexes, split, shrink, or reindex.
- [ ] Monitor indexing/search latency and rejections per shard/node.
- [ ] Have a migration plan before changing routing strategies.

Shards divide an index into data partitions; replicas provide copies for availability and read scaling; routing picks shards for documents and limits shards searched. A well-performing design balances storage, traffic, and query scope. Replicas cannot cure a primary write hotspot, raising shard counts does not automatically fix skewed routing keys, and custom routing can create hot shards if one large key dominates workload. Measure shard sizes, indexing/search rates, latency, and allocation before making changes; choose routing, partitioning, replicas, and index lifecycles around your actual workload.
