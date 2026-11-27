# Cluster, node, shard, and replica

Elasticsearch is designed to store and search data distributed across multiple machines or processes. A Spring Data Elasticsearch application typically interacts with Elasticsearch through an HTTP client and abstractions such as `ElasticsearchRepository` or `ElasticsearchOperations`. To understand where data is stored, how requests are processed, and how the system tolerates faults, you need to distinguish four concepts: **cluster**, **node**, **shard**, and **replica**.

General relationship:

```text
Spring Data Elasticsearch application
              |
              | HTTP request
              v
       Elasticsearch cluster
       +----------------------+
       | Node A               |
       |   Primary shard 0    |
       |   Replica shard 2    |
       +----------------------+
       | Node B               |
       |   Primary shard 1    |
       |   Replica shard 0    |
       +----------------------+
       | Node C               |
       |   Primary shard 2    |
       |   Replica shard 1    |
       +----------------------+
```

In the diagram, the cluster is the entire Elasticsearch system; each node is a process participating in the cluster; an index is a logical dataset; shards split an index into smaller parts; and a replica is a copy of a primary shard to increase fault tolerance and serve reads.

## 1. What is a cluster?

A **cluster** is a group of Elasticsearch nodes that work together and are viewed as a unified search system. An application can send a request to any node in the cluster; Elasticsearch routes the request to the appropriate node and shard.

A cluster has several key characteristics:

- It has a cluster name (`cluster.name`) and a unique cluster identifier.
- It manages the list of participating nodes, indices, metadata, configuration, and shard locations.
- It distributes shards across nodes based on resource state and allocation rules.
- It monitors the health and status of primary shards and replica shards.
- It can continue serving data when a node fails, provided the required shards still have active copies on other nodes.

Cluster state is the metadata state that nodes must agree upon, such as the list of indices, mappings, settings, node membership, and the shard routing table. An elected master node is responsible for coordinating changes to the cluster state. The master is not required to process every search query or write operation; other nodes can still receive and handle requests.

In a multi-node environment, Elasticsearch uses discovery and master election mechanisms so nodes can find each other and maintain a consistent cluster. Having two processes with the same `cluster.name` is not enough to guarantee they join the right cluster: discovery, network addresses, security configuration, and connectivity conditions must also match.

For example, an environment might have a cluster named `product-search` consisting of three nodes. For a Spring Data application, the client configuration points to one or more HTTP addresses of these nodes. When the topology changes, Elasticsearch updates routing and shard distribution; the application continues operating on the configured logical index.

## 2. What is a node?

A **node** is a running Elasticsearch process. A node joins a cluster, receives requests, stores shards, or performs management tasks depending on its configured roles.

Nodes within the same cluster can have different names and roles. Common roles include:

| Role | Primary responsibility |
|---|---|
| Master-eligible | Can participate in elections and become the master to manage cluster state. |
| Data | Stores shards and performs read, write, and search operations on data. Elasticsearch provides variants such as `data_hot`, `data_warm`, `data_cold`, and `data_frozen` for different storage tiers. |
| Ingest | Executes ingest pipelines to process documents before indexing. |
| Machine learning or transform | Provides corresponding specialized tasks when those features are used. |
| Coordinating | Receives requests, distributes them to relevant shards, and aggregates returned results. Coordination capability is available on every node; a coordinating-only node is typically configured without other specialized roles. |

A single node can take on multiple roles. In small clusters or development environments, one node often handles multiple duties. In larger systems, master-eligible, data, and ingest nodes can be separated to limit resource contention and make operations more predictable.

An example node configuration might contain properties such as:

```yaml
cluster.name: product-search
node.name: search-data-01
network.host: 0.0.0.0
http.port: 9200
```

These are only basic identification and connection properties. Discovery, security, roles, and deployment settings must be added to suit the actual environment. You should not copy development configuration directly to production.

### Request-coordinating node

The node that initially receives a request usually acts as the coordinating node for that request. It determines the target shards, forwards the work to the nodes holding those shards, collects the results, and merges the response. Therefore, the application does not need to locate which node holds a specific document on its own.

If the client is configured with multiple node addresses, the client can distribute connections or requests according to the mechanism of the library in use. Regardless of which node receives the request, Elasticsearch remains responsible for routing it to the appropriate shard.

## 3. Index and shard

An **index** is a collection of documents with a shared storage purpose that typically share mappings and settings. Conceptually, an index can be thought of as similar to a database table, but Elasticsearch is not a relational database: its storage, querying, and data distribution mechanisms are different.

An index can hold a large volume of data. If an entire index were stored on a single node, scalability and fault tolerance would be limited. Elasticsearch solves this by splitting an index into **primary shards**.

A **shard** is an independent data partition of an index. In terms of storage, each shard is a separate Lucene index. Elasticsearch distributes shards across nodes so multiple nodes can store and process an index's data together.

For example, the `products` index has three primary shards:

```text
Index: products
  ├── Primary shard 0
  ├── Primary shard 1
  └── Primary shard 2
```

### How does Elasticsearch choose a shard?

When writing a document, Elasticsearch needs to determine which primary shard the document belongs to. By default, the system uses the `_id` value combined with the number of primary shards to compute the target shard. If the application uses custom routing, the routing value is used instead of `_id` in that calculation.

Thanks to routing, read or write requests for a single document can be sent directly to the appropriate shard without scanning the entire index. When searching an index without specifying routing, the request is typically sent to the relevant shards; each shard executes the search, and the coordinating node merges the results.

### Number of primary shards

The number of primary shards is configured at index creation via the `number_of_shards` setting. This is a decision with long-term impact on how data is partitioned. You cannot simply change this setting the way you change the number of replicas on an existing index. When a different primary shard structure is needed, common approaches are creating a new index and reindexing the data, or using split/shrink operations when the corresponding conditions are met.

Choosing too few shards can limit data distribution and parallel processing. Choosing too many shards increases metadata overhead, memory usage, file handles, and cluster management work. The appropriate number of shards depends on expected data volume, shard size, write/read rates, node count, and future scalability; there is no single right number for every index.

## 4. Primary shard and replica shard

Within each shard group of an index, the **primary shard** is the main shard that receives initial write operations. A **replica shard** is a copy of its corresponding primary shard.

If an index has three primary shards and each primary has one replica, the logical structure is:

```text
products
  ├── Primary shard 0  ── Replica shard 0
  ├── Primary shard 1  ── Replica shard 1
  └── Primary shard 2  ── Replica shard 2
```

Elasticsearch attempts to place a replica on a different node from its corresponding primary. That way, when the node holding the primary is lost, an active replica on another node can be promoted to become the new primary.

### Write flow

A typical write flow proceeds as follows:

1. The application sends an index, update, or delete document request to an Elasticsearch node.
2. The receiving node determines the primary shard based on routing.
3. The request is forwarded to the node holding that primary shard.
4. The primary executes the operation and propagates the change to replicas in the in-sync copies group.
5. Elasticsearch returns the result according to the request's acknowledgment conditions and the state of the relevant copies.

Therefore, a Spring Data application only needs to call the repository or operations API. The application does not manually select which node stores a document, nor does it send the same operation separately to each replica.

### Read and search flow

For retrieving a single document, Elasticsearch can select any active shard copy in the primary/replica group to serve the request. For searches spanning multiple shards, the coordinating node sends the query parts to the relevant shards, receives partial results, and merges them before returning them to the application.

Replicas can help increase read throughput, especially when there are many search requests. However, having replicas does not mean every query will be faster in all cases: actual performance also depends on shard count, node resources, query type, caching, write load, and request distribution.

### Is a replica a backup?

No. Replicas help the cluster remain available when a node holding a shard fails and can increase read capacity. Replicas still belong to the same cluster and are affected by deletions or data modifications. If an index is accidentally deleted or bad data is written, the replicas reflect those changes as well.

To back up and restore data, you must use a snapshot repository and an appropriate snapshot/restore process. Replicas should not be treated as a backup strategy.

### Number of replicas

The number of replicas for an index is configured with `number_of_replicas`. Unlike the number of primary shards, the number of replicas can be changed after an index has been created. Increasing replicas creates additional data copies and requires storage capacity, CPU, memory, and network bandwidth for synchronization and shard recovery.

A replica cannot be placed on the same node as its corresponding primary. Therefore, if a cluster has only one node, replicas typically remain unassigned. This is a common reason a cluster shows a `yellow` status: primary shards are allocated, but replicas cannot be placed on another node.

## 5. Example of shard distribution across three nodes

Suppose the `products` index is created with:

```json
{
  "settings": {
    "number_of_shards": 3,
    "number_of_replicas": 1
  }
}
```

The index has three primary shards and one replica per primary, totaling six shard copies. A valid distribution across three nodes is:

| Node | Stored shard copies |
|---|---|
| Node A | Primary 0, Replica 2 |
| Node B | Primary 1, Replica 0 |
| Node C | Primary 2, Replica 1 |

Each node holds two shard copies, and no node holds both the primary and replica of the same shard. If Node A fails, Replica 0 on Node B can be promoted to Primary 0. The cluster can continue serving shard 0 as long as that replica is eligible to operate.

The number of shard copies is calculated using the formula:

```text
Total shard copies = number of primary shards × (1 + number of replicas per primary)
                   = 3 × (1 + 1)
                   = 6
```

This is the total number of logical shard copies to distribute, not the required number of nodes. However, to place a primary and its replica on different nodes, the cluster must have at least two nodes capable of storing those shards. The actual number of nodes and roles also depends on fault-tolerance requirements and allocation policies.

## 6. Cluster health and shard state

Elasticsearch provides cluster health to observe shard availability:

| Health | Meaning |
|---|---|
| `green` | All primary shards and required replica shards are allocated. |
| `yellow` | All primary shards are allocated, but at least one replica is unassigned. |
| `red` | At least one primary shard is unassigned; part of the index's data may be inaccessible. |

Common shard states:

- `UNASSIGNED`: the shard has not been assigned to any node.
- `INITIALIZING`: the shard is being initialized or recovered on a node.
- `STARTED`: the shard is active.
- `RELOCATING`: the shard is being moved from one node to another.

`green` does not automatically prove that the system has a solid disaster recovery plan; this status only indicates that the current shard copies are fully allocated. Backups, monitoring, recovery testing, and distributing nodes across failure domains still need to be designed separately.

### Useful observability APIs

The following requests can be sent using Kibana Dev Tools, curl, or an appropriate HTTP tool:

```http
GET /_cluster/health
GET /_cat/nodes?v
GET /_cat/indices?v
GET /_cat/shards/products?v
GET /products/_settings
```

Meanings:

- `/_cluster/health` reports the overall status, number of nodes, and count of active or unassigned shards.
- `/_cat/nodes` lists nodes, addresses, and some resource information.
- `/_cat/indices` lists indices, primary/replica counts, and status.
- `/_cat/shards/products` displays each shard of the `products` index, its primary/replica type, and the node storing it.
- `/{index}/_settings` reads index settings, including `number_of_shards` and `number_of_replicas`.

The `_cat` APIs are designed for human readability. When building automated integrations, prefer APIs with structured responses suitable for programmatic processing.

## 7. How do these concepts relate to Spring Data Elasticsearch?

Spring Data Elasticsearch provides mapping and abstractions for Java applications to work with Elasticsearch. For example:

```java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    private String name;

    // getters, setters, constructors
}
```

A repository can be declared as follows:

```java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
```

When the application calls:

```java
productRepository.save(product);
```

Spring Data converts the entity into a document and sends the operation through the configured Elasticsearch client. Elasticsearch receives the request, determines the primary shard via routing, performs the write, and synchronizes replicas according to cluster mechanisms.

`indexName = "products"` specifies the logical index the entity maps to. It does not mean the application is connecting directly to a fixed node or shard. Node addresses, authentication, and connections are configured at the client layer; primary shard count, replicas, and allocation are managed at the index/cluster layer.

When you need to proactively configure index topology, you can declare index settings using mechanisms supported by Spring Data, such as the `@Setting` annotation or the `IndexOperations` API, depending on the library version and how the project creates indices. An example of settings on the Elasticsearch side is:

```json
{
  "settings": {
    "number_of_shards": 3,
    "number_of_replicas": 1
  }
}
```

These settings need to be applied when creating the index. If the index already exists, changing the replica count can be done by updating settings; changing the primary shard count requires an appropriate data migration process such as reindex or split/shrink according to Elasticsearch conditions.

## 8. Key design takeaways

- **Cluster** is the entire Elasticsearch system; **node** is a process participating in that system.
- **Index** is a logical dataset; **shard** is a physical partition of an index.
- **Primary shard** receives initial write operations; **replica shard** holds a copy of the primary.
- Adding nodes provides more places to distribute shards and more resources, but does not automatically change the primary shard count of already-created indices.
- Increasing replicas can improve fault tolerance and read capacity, while increasing storage and synchronization overhead.
- Replicas do not replace snapshot backups.
- A Spring Data application operates on indices and documents via client/repository/operations; Elasticsearch is responsible for routing requests to nodes and shards.
- Monitor cluster health, shard allocation, storage usage, and actual load before adjusting shard or replica counts.

Properly understanding clusters, nodes, shards, and replicas helps you interpret Elasticsearch status, explain how requests from Spring Data reach the data, and choose index configurations that fit your application's scale and availability requirements.
