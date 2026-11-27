# Document routing to shards and the role of routing

Elasticsearch splits an index into multiple primary shards to distribute data and process queries across different parts of the document set. When writing or reading a document by ID, Elasticsearch must determine which shard is responsible for that document. This shard-selection mechanism is called routing.

By default, Elasticsearch uses the _id value as the routing key, hashes it, and determines the primary shard. In many cases, the default behavior is enough. Applications can pass a custom routing key, such as tenantId or customerId, to co-locate related documents on the same shard and narrow the scope of shards that need to be searched. Doing so can reduce query cost, but it also introduces constraints on writes, updates, reads, deletes, and load distribution.

Understanding routing helps design indices and APIs properly from the start, especially for multi-tenant systems, parent-child relationships, or queries that only need data belonging to a specific group.

## 1. Why does Elasticsearch need routing?

An index can have multiple primary shards. Each primary shard is an independent data partition; replica shards are copies providing availability and extra read capacity. A document belongs to a specific primary shard and that shard's replicas.

When an application sends a request to index a document, Elasticsearch must identify the target primary shard. When fetching a document by ID, Elasticsearch also needs to know which shard to ask. If a search query does not restrict routing, Elasticsearch typically must send the query to the relevant shards in the index and merge the results.

Routing answers the question: **given the routing key of this document or query, which shard should handle it?**

There are two related but distinct concerns:

- **Document routing:** determines which primary shard in an index a document belongs to.
- **Shard allocation:** decides which node in the cluster holds a shard and when shards move between nodes.

A routing key does not directly specify a node name or server host. It helps Elasticsearch pick a shard; cluster allocation is responsible for placing those shards onto nodes.

## 2. How default routing works

When an application does not pass a routing parameter, Elasticsearch uses the document's _id as the routing value. That value is hashed and the result is mapped to one of the index's primary shards.

Conceptually, this looks like:

~~~text
document _id
     |
     v
hash(_id)
     |
     v
select a primary shard
     |
     v
write document to that shard
~~~

For example, the products index has three primary shards. Documents with different IDs are distributed based on the hash result:

| Document ID | Default routing | Illustrative primary shard |
|---|---|---|
| product-101 | product-101 | shard 0 |
| product-205 | product-205 | shard 2 |
| product-330 | product-330 | shard 1 |

The shards in the table only illustrate possible outcomes; you cannot deduce the actual shard merely by looking at the ID. Elasticsearch runs its hashing algorithm and chooses the shard according to index settings.

Advantages of default routing:

- The application does not need to design or store an extra routing key.
- Operations using the same ID can always locate the right shard given the same index and shard configuration.
- Data is usually distributed fairly evenly when IDs have good distribution.
- No separate routing parameter needs to be passed in index, get, update, or delete calls.

For CRUD by ID and full-index search, default routing is usually a sensible starting point. Only use custom routing when there is a specific query pattern or data relationship requirement.

## 3. Custom routing: choosing your own routing key

Elasticsearch allows applications to pass a routing parameter instead of using _id as the routing value. Documents with the same routing value are placed onto the same primary shard of the index.

For example, a multi-tenant SaaS system has many tenants. Each tenant has many documents, and most queries only read data for a single tenant. The application can use tenantId as the routing key:

~~~text
tenant-42
  ├── document A
  ├── document B
  └── document C

tenant-77
  ├── document D
  └── document E

routing("tenant-42") ──> a primary shard is selected
~~~

The value tenant-42 does not mean that tenant receives its own dedicated shard. Elasticsearch hashes the routing value to select a shard. Multiple tenants can land on the same shard; a tenant with a fixed routing value concentrates its documents onto one shard under standard routing configurations.

### 3.1. Declaring required routing in the mapping

If the design requires every document to have a routing key, you can declare _routing.required when creating the index:

~~~http
PUT /tenant-documents
Content-Type: application/json

{
  "mappings": {
    "_routing": {
      "required": true
    },
    "properties": {
      "tenantId": {
        "type": "keyword"
      },
      "title": {
        "type": "text"
      },
      "content": {
        "type": "text"
      }
    }
  }
}
~~~

With this mapping, attempts to index a document without supplying routing are rejected. This protects data conventions on the Elasticsearch side, preventing some documents from accidentally falling back to default routing.

_routing.required only requires the request to provide a routing value. It does not automatically verify that the routing value equals tenantId inside _source; the application must still ensure those two values match.

### 3.2. Writing documents with a routing key

Example creating a document belonging to tenant tenant-42:

~~~http
PUT /tenant-documents/_doc/doc-100?routing=tenant-42
Content-Type: application/json

{
  "tenantId": "tenant-42",
  "title": "User Guide",
  "content": "Tenant document content."
}
~~~

Elasticsearch uses tenant-42 to determine the target primary shard. The tenantId value in _source is business data that the application can filter or display; the routing parameter is metadata controlling shard placement. The two values are linked by application convention, not as the exact same concept.

### 3.3. Reads, updates, and deletes must use the same routing

When a document is written using custom routing, operations locating the document by ID must also provide the corresponding routing value:

~~~http
GET /tenant-documents/_doc/doc-100?routing=tenant-42
~~~

~~~http
POST /tenant-documents/_update/doc-100?routing=tenant-42
Content-Type: application/json

{
  "doc": {
    "title": "User Guide New Edition"
  }
}
~~~

~~~http
DELETE /tenant-documents/_doc/doc-100?routing=tenant-42
~~~

If routing is omitted or a different value is passed, Elasticsearch may look on another shard and fail to find the document. The result can be 404, even though the document actually exists on the shard chosen by the original routing.

Therefore, the application must retain the routing key throughout the document's lifecycle. If an API only receives an ID and cannot determine the routing value, custom routing will complicate reads, updates, and deletes.

## 4. How does routing help search queries?

When searching without passing routing, Elasticsearch must distribute the query to all required shards in the index. If the application knows beforehand that a query only concerns one or a few routing keys, it can pass them in the routing parameter of the Search API.

For example, searching documents for tenant tenant-42:

~~~http
POST /tenant-documents/_search?routing=tenant-42
Content-Type: application/json

{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "tenantId": "tenant-42"
          }
        }
      ],
      "must": [
        {
          "match": {
            "content": "guide"
          }
        }
      ]
    }
  }
}
~~~

The routing=tenant-42 parameter limits which shard Elasticsearch needs to query. The term condition on tenantId filters data by tenant in the results. The two parts serve different purposes:

- Routing reduces the scope of shards that must be queried.
- The query condition ensures results satisfy the application's data constraints.

**Do not treat routing as an authorization or tenant isolation mechanism.** A single shard can contain documents from multiple tenants because different routing keys can hash to the same shard. Additionally, an API caller could pass arbitrary routing values. The system must still authenticate users, determine the tenant from trusted server-side context, and add appropriate filter conditions.

The Search API can accept multiple routing values, typically comma-separated. When querying data for a known group of tenants, this can limit the query to relevant shards. If users need to search across all tenants or the entire index, the benefit of reducing fan-out disappears.

## 5. Benefits of custom routing

### 5.1. Reducing the number of shards queried

Suppose an index has 12 primary shards, yet a request only needs data for tenant tenant-42. If that tenant is used as the routing key and the search request passes the same routing value, Elasticsearch can query only the corresponding shard instead of fanning out to all 12 shards.

This can reduce:

- The number of shards that must execute the query.
- Coordination and result-merging work across shards.
- CPU and network resources for queries scoped to a known data group.
- Search latency under suitable workloads.

Actual benefits still depend on document count, query complexity, caching, shard size, and cluster load. Routing does not guarantee every query will be faster; benchmark using representative workloads.

### 5.2. Placing related data on the same shard

Some data models require related documents to reside on the same shard. For instance, Elasticsearch parent-child relationships require parent and child documents to live on the same shard. You can use the parent's ID as the routing value for both parent and child to satisfy that requirement.

~~~text
parent: order-900
  routing = order-900
      |
      +-- child: item-1, routing = order-900
      |
      +-- child: item-2, routing = order-900
      |
      +-- child: item-3, routing = order-900

All are routed to the same primary shard.
~~~

When designing parent-child models, maintain consistent routing across the entire relationship. If parent and child are written with different routing, relationship queries may not behave as expected.

### 5.3. Suited for queries scoped by tenant or data group

Routing by tenant, customer, organization, or a business partitioning key can be useful when most queries have a clear scope. It allows group-scoped read patterns to leverage shard routing rather than always searching the entire index.

Benefits materialize only when the application routinely knows the routing key before querying. If most screens search across tenants, tenant-based routing may not reduce the number of participating shards.

## 6. Risks and limitations to understand clearly

### 6.1. Hot shards and uneven data distribution

Custom routing can concentrate a large volume of documents or query traffic onto a single shard. For example, if one tenant is hundreds of times larger than the others, using tenantId as the routing key can turn that tenant's shard into a hotspot.

Consequences can include:

- One shard grows rapidly in size while other shards hold little data.
- CPU, disk I/O, or indexing pressure concentrates on one part of the cluster.
- Queries for the large tenant suffer high latency.
- Scaling out the cluster does not automatically split data already concentrated on that shard.

High-cardinality routing values still do not guarantee even load distribution. Elasticsearch hashes values to pick shards, yet the volume and traffic per value can vary dramatically.

### 6.2. Routing keys must be stable

If a document is written using tenant-42, but a subsequent update uses tenant-77, Elasticsearch will locate the shard using the new value and may fail to find the old document. Therefore, routing keys must remain stable throughout a document's lifecycle.

If business rules allow transferring a document from one tenant to another, design an explicit data migration flow: identify the old routing, read the old document, write the document under the new routing, and handle deleting the old copy. Do not merely change the tenantId field in _source and assume the document automatically moves shards.

### 6.3. Risk of duplicate _id across different shards

With custom routing, the same _id with two different routing values can be routed to two different shards. Uniqueness of _id is enforced per shard, so the application should not assume _id remains unique across the entire index if multiple routing values are permitted for the same ID.

Use a consistent routing key and design IDs suitable for the business scope. For instance, if an ID is unique only within a tenant, construct a composite ID combining tenant and local ID, or ensure every operation consistently uses the owning tenant's routing.

### 6.4. Changing primary shard count is a design issue

Routing is computed from the routing value and the index's number of primary shards. When creating an index, the primary shard count is a fundamental part of data distribution. If you later need to change the shard topology or routing strategy, you generally have to create a new index, reindex the data, and switch aliases or the application to the new index.

Do not treat routing as a parameter that can be freely changed once an index already contains data. Estimate volume, tenant count, skew, and query patterns before finalizing the design.

### 6.5. Routing does not replace business filters

Routing selects shards based on request metadata. It does not verify that documents in _source belong to the tenant a user is authorized to access. One shard can hold multiple tenants, and a query could return documents from another tenant if the query lacks proper filter conditions.

The server must determine routing from the caller's identity and permissions, never trusting routing values arbitrarily supplied by a client. At the same time, the query must include the corresponding tenant filter or authorization condition.

## 7. How to choose a routing key

A good routing key must fit how the application writes and queries data. Consider the following criteria:

| Criterion | Question to answer |
|---|---|
| Query scope | Do most requests know the routing key before searching? |
| Stability | Does the routing value stay constant throughout the document's lifecycle? |
| Storage distribution | Is any tenant or group disproportionately large? |
| Load distribution | Does any group write or search much more frequently? |
| Data relationships | Do documents needing parent-child joins share the same routing? |
| Operations | Can you monitor hot shards and adjust strategies if needed? |

Some examples:

| Routing key | When it may fit | Main risk |
|---|---|---|
| No custom routing, use _id | CRUD by ID, full-index search, no clear query grouping | Single-tenant queries may still fan out |
| tenantId | Almost all queries are scoped to a single tenant | Large tenants create hot shards; cross-tenant queries gain little |
| customerId | Data and queries frequently focus on one customer | High-volume or high-traffic customers skew load |
| parentId | Need parent-child co-located on the same shard | Every operation must preserve parent routing |
| accountId or organizationId | Requests mainly read a single account or organization | Multi-account query cases must be clearly handled |

Do not pick a routing key just because that field exists on the entity. Start from actual query patterns and verify whether requests always know the routing value.

## 8. Routing in bulk indexing

When writing multiple documents via the Bulk API, routing is declared in each operation's metadata. Each document can have its own routing value:

~~~http
POST /_bulk
Content-Type: application/x-ndjson

{ "index": { "_index": "tenant-documents", "_id": "doc-100", "routing": "tenant-42" } }
{ "tenantId": "tenant-42", "title": "Document A" }
{ "index": { "_index": "tenant-documents", "_id": "doc-200", "routing": "tenant-77" } }
{ "tenantId": "tenant-77", "title": "Document B" }
~~~

When using the Bulk API, ensure routing is included in the metadata for every document requiring custom routing. Setting routing on another request or merely storing it inside _source does not make the Bulk API automatically use that field to pick a shard.

When processing bulk responses, inspect per-item errors. A bulk request can succeed at the HTTP level while individual items fail due to missing routing, mapping errors, or write failures.

## 9. Using routing with Spring Data Elasticsearch

Spring Data Elasticsearch provides entity mapping and abstraction layers for interacting with Elasticsearch. When using custom routing, it is important that the routing value be attached to the metadata of the Elasticsearch operation. Simply declaring a tenantId property on an entity or storing it in _source does not automatically ensure every request uses that property for routing.

In Spring Data Elasticsearch versions supporting the @Routing annotation, you can mark the property holding the routing value on the entity. Illustrative example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.Routing;

@Document(indexName = "tenant-documents")
public class TenantDocument {

    @Id
    private String id;

    @Routing
    @Field(type = FieldType.Keyword)
    private String tenantId;

    @Field(type = FieldType.Text)
    private String title;

    // constructors, getters and setters
}
~~~

In this model, tenantId is both data stored in the document and the routing value used by the mapping layer when performing supported operations. Verify the exact annotation and behavior in your project's Spring Data Elasticsearch version, especially for custom queries or low-level client APIs.

If an operation uses ElasticsearchOperations, a repository, or the Elasticsearch Java Client directly, check the API for your exact version to pass routing into the request. Do not assume every custom query automatically inherits routing from the entity. For search requests, routing must be set on the corresponding query/request object; for ID-based operations, routing must be passed alongside the read, update, or delete operation.

A useful convention is encapsulating routing resolution in a service or data access component. That way, save, search, get-by-ID, and delete flows follow the same rule instead of assembling routing parameters inconsistently across call sites.

## 10. Testing and observing routing

Before rolling out custom routing, test with data close to the real distribution:

1. Create an index with the planned number of primary shards.
2. Generate documents matching realistic tenant or group counts.
3. Write data using the planned routing key.
4. Compare full-index queries against queries with routing.
5. Measure shards queried, latency, CPU, storage, and indexing throughput.
6. Test the largest tenant and high-frequency access groups.
7. Test get, update, delete, and bulk with valid, missing, and mismatched routing.
8. Verify authorization and tenant filters independently of routing.

In production, monitor per-shard size and load, indexing pressure, search latency, rejected requests, and cluster health. If a shard receives disproportionate data or traffic, re-evaluate the routing key or data partitioning strategy.

## 11. Example routing choice for a multi-tenant system

Suppose a document management platform has 200 tenants. Most search requests originate from an authenticated tenant. Each tenant has thousands to millions of documents, and the API typically searches by keywords within a tenant's scope.

A viable approach might be:

- Use tenantId as the routing key so tenant-scoped queries hit only the relevant shard.
- Store tenantId in _source as keyword for exact filtering.
- Mark routing as required in the mapping to prevent writes missing routing.
- Have the server extract the tenant from authentication context and automatically attach both routing and the filter condition to queries.
- Ensure all get-by-ID, update, and delete operations know the owning tenant to pass routing consistently.
- Monitor tenants with high volume or traffic to spot hot shards.

If one exceptionally large tenant accounts for most of the load, routing the entire tenant to one shard can become a bottleneck. You would then re-evaluate partitioning, such as splitting large tenants across multiple routing partitions or designing dedicated indices per data group. These options add complexity and must be validated for your Elasticsearch version, index configuration, and specific workload.

If the application routinely searches across all tenants, custom routing by tenant may provide no meaningful benefit. The routing key should reflect the dominant query scope, not just the organizational structure of the data.

## 12. Conclusion

Routing is the mechanism Elasticsearch uses to determine which shard handles a document or query. By default, _id is the routing value; custom routing allows using business keys such as tenantId, customerId, or parentId to co-locate related data and limit searched shards.

Custom routing can improve performance when requests usually know the routing key and data is distributed reasonably well. In return, the application must pass routing consistently across index, get, update, delete, bulk, and search operations; monitor hot shards; avoid duplicate IDs across different routing values; and never treat routing as a security mechanism.

Start with default routing unless you have a clear reason. Switch to custom routing only after identifying query patterns, measuring load, and proving the benefit of reducing shard fan-out or co-locating related documents on the same shard.
