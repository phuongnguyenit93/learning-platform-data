# existsById, count, and Operation Costs

Spring Data Elasticsearch provides operations to check whether a document exists and to count documents. These two needs sound similar, yet they differ in cost and intent:

- existsById(id) answers a boolean question: does a document with that ID exist in the index?
- count() returns the number of documents within the repository's scope.
- Methods such as existsBySku(...) or countByActiveTrue() check existence or count by criteria, which generally requires executing a field query rather than a direct document ID lookup.

Choosing the right operation reduces unnecessary requests, avoids scanning large datasets, and limits load on Elasticsearch. This lesson explains the semantics of each method, how they map to REST APIs, what drives their costs, and how to use them safely in CRUD workflows.

## 1. What Is existsById Used For?

A repository extending ElasticsearchRepository comes with existsById out of the box:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

Usage:

~~~java
boolean exists = productRepository.existsById("P-1001");

if (exists) {
    // Document with ID P-1001 exists.
}
~~~

The result is a boolean:

- true: the document was found in the corresponding index.
- false: the document does not exist within the index/alias scope used by the repository.

This method fits when the application only needs to verify a single document by ID, such as checking a resource before displaying it, verifying operation state, or confirming an ID was created.

On the Elasticsearch side, checking existence by ID is typically performed with the Exists API, corresponding to an HTTP HEAD request:

~~~http
HEAD /products/_doc/P-1001
~~~

If the document exists, Elasticsearch returns HTTP 200. If it does not exist, the response is typically HTTP 404. A HEAD response does not download the full _source body to the application.

Spring Data may change implementation details across versions. When you need to know the exact request emitted in a project, inspect the API/implementation of the version in use or enable HTTP client logging in a test environment. The repository method's meaning remains checking existence by ID.

### 1.1. existsById Is Not count

Do not call count() to answer an existence question by ID:

~~~java
// When you only need to know whether a document exists:
boolean exists = productRepository.existsById(id);

// Do not count all documents to infer that:
boolean existsByCounting = productRepository.count() > 0;
~~~

Those two final expressions have different meanings. count() > 0 only tells you the index has at least one document, not whether a document with a specific ID exists. Moreover, count() may have to process every document in the query scope.

## 2. What Is count Used For?

A repository extending CrudRepository provides a count() method returning long:

~~~java
long total = productRepository.count();
~~~

This method counts the documents within the repository's scope. If the repository is mapped to the products index, the result is the document count in that index. If configuration uses an alias or a different index scope, the result depends on the actual index/alias accessed by the repository.

At the Elasticsearch level, the Count API can be called directly:

~~~http
GET /products/_count
~~~

Illustrative response:

~~~json
{
  "count": 1250,
  "_shards": {
    "total": 3,
    "successful": 3,
    "skipped": 0,
    "failed": 0
  }
}
~~~

The count field is the number of matching documents. _shards describes execution outcomes across the targeted shards.

The Count API does not return full documents. It returns the count and execution metadata, making it more suitable than the Search API when the goal is strictly obtaining an exact count.

### 2.1. Counting with Criteria

You can supply a query to the Count API:

~~~http
POST /products/_count
{
  "query": {
    "term": {
      "active": true
    }
  }
}
~~~

This request counts products where active = true.

In a repository, you can declare derived queries if your project's Spring Data Elasticsearch version supports the corresponding keywords:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    long countByActiveTrue();

    long countBySku(String sku);
}
~~~

Usage:

~~~java
long activeProducts = productRepository.countByActiveTrue();
long productsWithSku = productRepository.countBySku("SKU-1001");
~~~

Derived query methods are parsed by Spring Data from the method name. Verify syntax and support in your project's Spring Data Elasticsearch version, especially when methods combine multiple conditions or special field types.

When complex queries are needed, use ElasticsearchOperations with a Query and the Count API rather than forcing every condition into a method name.

## 3. existsById and existsBy<Property> Are Different Cases

A Spring Data repository can expose both existence checks by ID and existence checks by a domain property.

Example:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    boolean existsById(String id);

    boolean existsBySku(String sku);

    boolean existsByActiveTrue();
}
~~~

Comparison:

| Method | Meaning |
|---|---|
| existsById(id) | Checks for a document by Elasticsearch ID. |
| existsBySku(sku) | Checks whether any document matches the SKU condition. |
| existsByActiveTrue() | Checks whether any document has active = true. |
| count() | Counts all documents within the repository scope. |
| countBySku(sku) | Counts documents matching the SKU condition. |

existsById can leverage direct lookup by document ID. existsBySku and similar methods must evaluate conditions against a field. The exact query mechanism depends on how Spring Data builds queries in the version being used.

Do not assume every method starting with exists has the same cost. Checking by ID typically takes a simpler path than checking a non-ID property.

## 4. Using ElasticsearchOperations When Specifying an Index or Query

Besides repositories, Spring Data Elasticsearch provides ElasticsearchOperations to execute operations directly.

Example checking existence by ID and counting documents:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Query;

public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public boolean exists(String id) {
        return operations.exists(
            id,
            Product.class,
            IndexCoordinates.of("products")
        );
    }

    public long countAll() {
        return operations.count(
            Query.findAll(),
            Product.class,
            IndexCoordinates.of("products")
        );
    }
}
~~~

The example above specifies the index using IndexCoordinates. This is helpful when a service needs to select an index or alias at runtime, whereas standard repositories use the index determined from entity metadata.

Method names and overloads can differ across Spring Data Elasticsearch versions. Check against your project's dependency API. If using a repository with a fixed index, existsById() and count() are generally simpler.

## 5. Cost of existsById

Checking existence by ID is generally less expensive than counting a large set of documents because Elasticsearch can route the operation by ID directly to the shard holding the document.

Factors affecting cost include:

- **Network request count:** each repository call typically sends one request to Elasticsearch.
- **Shard routing:** Elasticsearch must determine the appropriate shard from the document ID and any routing key used.
- **Network latency:** distance between the application and cluster can make even a simple request take noticeable time.
- **Cluster load:** nodes handling heavy requests or I/O may respond slowly.
- **Custom routing:** if the document was written with custom routing, the existence check must supply the same routing to locate the right shard.

Lookup by ID does not mean zero cost. A simple request still incurs a network round trip, authentication, node processing, and response handling. Calling it thousands of times sequentially can produce significant total latency even if each individual request is fast.

### 5.1. How Routing Affects existsById

If the application uses custom routing when indexing documents, Elasticsearch uses the routing value to select the shard. When reading or checking existence, supply the matching routing value.

REST API example:

~~~http
HEAD /products/_doc/P-1001?routing=tenant-a
~~~

If routing is omitted when the document was saved with custom routing, the check may target a different shard and report that the document does not exist.

Standard repository existsById(id) does not always accept a per-call routing parameter. If your application relies on dynamic per-tenant routing, design services/APIs using operations that support routing in your Spring Data/Elasticsearch client version.

Do not use existsById as a routing-unaware check in a multi-tenant system where the same ID could live on different shards per tenant.

## 6. Cost of count

Count is usually more expensive than checking a single ID because Elasticsearch must execute the query across the shards of the selected index or alias and then aggregate the counts.

The cost depends on:

1. **Number of shards queried:** an alias or wildcard pointing to multiple indices can cause the request to fan out across many shards.
2. **Query type:** a simple match_all is typically lighter than a query with many conditions, nested queries, or complex analysis filters.
3. **Document count and data structure:** large indices or complex data distributions can make the operation more resource-intensive.
4. **Cluster health:** CPU, I/O, heap, concurrency, and other background workloads affect latency.
5. **Call frequency:** an occasional count may be acceptable, but calling count repeatedly on every request or inside loops can generate substantial load.
6. **Index scope:** counting a single index differs from counting across an alias spanning many indices.

The Count API does not transfer full _source documents to the application and does not compute relevance scores like full-text search. Still, that does not mean count is free or instantaneous. Elasticsearch must still evaluate the filter and sum counts across the relevant shards.

### 6.1. Unfiltered vs. Filtered Count

Unfiltered count:

~~~http
GET /products/_count
~~~

Filtered count:

~~~http
POST /products/_count
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "active": true
          }
        },
        {
          "range": {
            "priceInCents": {
              "gte": 100000
            }
          }
        }
      ]
    }
  }
}
~~~

A filtered query must be evaluated on the relevant shards. Filters may benefit from the query cache in certain cases, but cache effectiveness depends on query structure, data, and cluster state. Do not rely on caching to assume every count has constant cost.

### 6.2. Counting Across Multiple Indices or an Alias

Example:

~~~http
GET /orders-2026-*/_count
~~~

The request can span multiple indices matching the pattern. The number of shards queried grows with the resolved index scope.

If an alias points to multiple indices:

~~~http
GET /orders-read/_count
~~~

the result is the document count within the alias scope. This is useful for time-partitioned data, though keep in mind an alias can change which indices it points to.

When count is used in critical business logic, define the alias/index scope clearly and verify alias configuration during deployment.

## 7. How count() Differs from hits.total in the Search API

The Search API can also return a match count in hits.total:

~~~http
GET /products/_search
{
  "query": {
    "match_all": {}
  }
}
~~~

The response may contain:

~~~json
{
  "hits": {
    "total": {
      "value": 10000,
      "relation": "gte"
    },
    "hits": []
  }
}
~~~

The relation field has two common values:

- eq: value is the exact total count.
- gte: value is a lower bound, meaning at least that many documents matched.

By default, Elasticsearch caps exact hit-count tracking at a threshold (commonly 10,000). For large result sets, the Search API may report only a lower bound to reduce counting overhead.

If you need an exact total in the Search API, you can enable it:

~~~http
GET /products/_search
{
  "track_total_hits": true,
  "size": 0,
  "query": {
    "match_all": {}
  }
}
~~~

Comparison:

| Need | Appropriate API |
|---|---|
| Only an exact count | Count API or repository count() |
| Both documents and total hit count | Search API |
| Only the first few documents, no exact total needed | Search API with bounded size and without requiring exact track_total_hits |
| Check whether a single ID exists | Exists API / existsById |
| Check whether any document satisfies a condition | Search limited to one hit or an appropriate derived exists query |

If your sole goal is counting, the Count API expresses that intent more clearly. If you are already running the Search API to retrieve documents, evaluate whether an exact total is truly needed before enabling track_total_hits.

## 8. When You Only Need to Know Whether Any Match Exists

Suppose you need to know whether there are any active products. You do not necessarily need to count every active product:

~~~java
long activeCount = productRepository.countByActiveTrue();
boolean hasActive = activeCount > 0;
~~~

If only a boolean is needed, a search query capped at one hit can be more suitable:

~~~http
POST /products/_search
{
  "size": 1,
  "track_total_hits": false,
  "query": {
    "term": {
      "active": true
    }
  }
}
~~~

The application checks whether hits.hits contains an element. Search still executes the query on the relevant shards, but it avoids computing an exact total across all hits and returns at most one document.

If your Spring Data version supports a derived existsByActiveTrue(), you can use that method to express intent. Inspect the actual generated request or version documentation when tuning performance; do not assume it always maps to one specific request shape.

## 9. Do Not Use count() to Check for an Empty Index in Every Situation

Some code writes:

~~~java
if (productRepository.count() == 0) {
    // Initialize default products
}
~~~

While logically plausible, consider the cost and concurrency implications:

- count() may query multiple shards.
- Two application instances can both observe 0 and initialize data simultaneously.
- Newly written data might not appear immediately in Count/Search APIs due to refresh timing.
- Data initialization may need idempotency and synchronization mechanisms.

If you only need to check a specific document, use existsById. If you need to seed a default dataset, design the seeding operation with deterministic IDs so it can repeat safely and prevent unintended concurrent execution.

Do not use count() as a synchronization lock or a guarantee that only one instance runs a task.

## 10. Avoid Check-Then-Write Race Conditions

A common anti-pattern:

~~~java
if (!productRepository.existsById(product.getId())) {
    productRepository.save(product);
}
~~~

This snippet issues two separate requests:

1. Check that the ID does not exist.
2. Write the document.

Between those two steps, another request can write the same ID. Thus both requests can observe false and both proceed to write. That is a race condition.

If save uses index/upsert semantics by ID, the later write overwrites the earlier document. Depending on business rules, that may or may not be acceptable.

When the requirement is to create only if absent, use a conditional create-only write (create-only/op_type=create) or appropriate optimistic concurrency control, and handle conflicts if the document already exists. Do not rely on a preceding existsById check to enforce uniqueness.

If IDs are derived deterministically from a business key, design that ID so the same entity always maps to the same document ID. For non-ID business keys, use a dedicated uniqueness and concurrency strategy.

## 11. Optimizing Repeated exists and count Calls

### 11.1. Avoid Calling in a Loop

Do not check each ID sequentially in separate requests when batching is possible:

~~~java
for (String id : ids) {
    if (productRepository.existsById(id)) {
        // ...
    }
}
~~~

For a list of thousands of IDs, this creates thousands of network round trips. Consider the Multi Get API or a suitable ids/terms query, then reconcile the returned IDs.

Example querying multiple IDs:

~~~http
POST /products/_search
{
  "size": 1000,
  "query": {
    "ids": {
      "values": [
        "P-1001",
        "P-1002",
        "P-1003"
      ]
    }
  }
}
~~~

If you need to read full documents by ID, the Multi Get API may be preferable. If you only need to determine which IDs exist, an IDs query and set comparison can work. Keep batch size, response size, and shard count in mind.

### 11.2. Avoid Repeated Counts on Every UI Request

A listing page might trigger:

- Search to fetch 20 products.
- Count to get total product count.
- Several existsById calls for individual items.

If an exact total is not strictly needed, omit the separate count request. If the Search API already returns hits.total with sufficient accuracy, reuse that value. If you only need to show "more results available," you do not need to count everything.

If counts change slowly and business rules allow, cache the count briefly or maintain separate summary metrics. Any cache needs an invalidation strategy when documents are created, updated, or deleted; otherwise, numbers will become stale.

### 11.3. Bound Query Scope

When counting with criteria:

- Target the right index or alias.
- Query only necessary fields.
- Use keyword fields for exact filter values.
- Use range queries matching numeric/date types.
- Avoid overly broad index wildcards when unnecessary.
- Avoid complex queries when a simple filter field suffices.

Well-structured queries reduce Elasticsearch's workload and are easier to inspect during debugging.

## 12. Impact of Refresh and Consistency

Elasticsearch exhibits near-real-time behavior for Search and Count. A newly indexed document may not appear in query results until the next refresh.

Distinguish:

| Operation | Behavior for observing new data |
|---|---|
| Get document by ID | Realtime per Get API semantics |
| Exists by ID | Follows document ID lookup path; normally sees successfully written documents immediately |
| Search | Near-real-time, depends on refresh |
| Count API | Relies on search/query mechanics and may miss new documents before refresh |

For instance, writing a document and immediately calling count() or countBy... might not include that document if a refresh has not occurred yet.

In tests that need immediate Search/Count assertions after a write, refresh the index explicitly. In production, do not refresh after every write because frequent refreshes degrade indexing performance.

If the application requires read-after-write via search, choose a refresh policy aligned with business requirements and load. Do not mistake refresh delay for a failed write.

## 13. Measure Costs Rather Than Guessing

There is no fixed number for the cost of existsById or count. Measuring in an environment close to production is far more reliable.

Useful metrics include:

- Request rate of exists/count.
- p50, p95, and p99 latency.
- Timeout and error rates.
- Number of shards queried.
- Elasticsearch CPU, heap, I/O, and search thread pool load.
- Response size and network traffic.
- Repeated calls per business request.

You can enable HTTP client logging in a test environment to see which requests Spring Data emits. Do not enable logging containing sensitive data or credentials in production.

When comparing two approaches, use the same dataset, same index, same query, and same concurrency level. Measure multiple runs to avoid drawing conclusions from a single request skewed by caches or transient load.

## 14. Examples of Choosing an API by Business Need

| Requirement | Recommended approach | Reason |
|---|---|---|
| Check whether product ID P-1001 exists | existsById("P-1001") | Direct lookup by ID |
| Count all products | count() | Returns exact count within repository scope |
| Count active products | countByActiveTrue() or Count API with filter | Filtered count |
| Check if a specific SKU exists | existsBySku(sku), if supported | Boolean check by property |
| Only need to know if at least one active product exists | exists query or Search with size 1 | No exact total needed |
| Fetch a list and total count | Search API; use hits.total when accurate enough | One request returns both hits and total |
| Check a batch of IDs | Multi Get or IDs query | Reduces round trips |
| Create document only if it does not exist | Create-only write / concurrency control | Avoids check-then-write race conditions |

## 15. Checklist When Using existsById and count

Before adding an existence check or count to a service, verify:

- Do you need only a boolean or an exact count?
- Are you checking by document ID or by a property?
- Does the repository point to one index, an alias, or multiple indices?
- Do documents use custom routing?
- Can the information be obtained from an existing Search result?
- Is the operation called repeatedly in a loop or on every UI request?
- Does the count need to be immediately accurate after writes, or is refresh delay acceptable?
- Is there a race condition between checking and writing?
- Can multiple IDs be batched or metrics cached if business rules allow?
- Have latency and cluster load been measured under realistic conditions?

existsById and count are simple CRUD operations that serve different purposes. Use existsById when you need to confirm a document by ID; use count when you genuinely need a quantity; use an exists query or Search limited to one hit when you only need to know whether matching documents exist. Account for request count, shard fan-out, routing, refresh, and concurrency so repeated checks do not place unnecessary load on Elasticsearch.
