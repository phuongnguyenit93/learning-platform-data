# Processing Flow from a Java Call to an HTTP Request and Search Results

When a Spring application calls a Spring Data Elasticsearch search method, that call passes through several layers before becoming an HTTP request. Elasticsearch executes the request across shards, returns JSON, and Spring Data converts each hit into a Java object and wraps metadata for the application.

The entire flow can be divided into four stages:

1. **Java call:** the service invokes a repository or `ElasticsearchOperations`.
2. **Request preparation:** Spring Data resolves the index and translates the query, sort, and pagination into an Elasticsearch Java API Client request.
3. **HTTP exchange and search execution:** the client sends the request to the cluster; a coordinating node distributes work to the shards.
4. **Reading results:** the client receives the response; Spring Data converts `_source` into entities and returns the result to the service.

This lesson focuses on the synchronous search path commonly used in Spring applications. Certain client class details and transport configurations vary across Spring Data Elasticsearch and Elasticsearch versions.

## 1. Starting from the Java call

An application does not normally build HTTP requests manually. Business code invokes a strongly typed method, such as on a repository:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text, analyzer = "standard")
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private double price;

    // constructors, getters, setters
}

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByCategory(String category);
}
~~~

A service uses the repository like any other dependency:

~~~java
@Service
public class ProductService {

    private final ProductRepository productRepository;

    public ProductService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    public List<Product> findProductsInCategory(String category) {
        return productRepository.findByCategory(category);
    }
}
~~~

When a controller calls `findProductsInCategory("computer")`, the service invokes `findByCategory("computer")`. At this point, the application is still working with Java objects and a `List<Product>` return type. The repository is not an HTTP client itself, but a Spring Data-provided interface.

### The repository proxy receives the call

Spring Data generates the repository implementation during application startup. Typically, the object injected into the service is a Spring-managed proxy.

When code calls `findByCategory`, the proxy routes the call to Spring Data's query execution mechanism:

- Base methods such as `save`, `findById`, and `deleteById` are handled by the base repository implementation.
- Derived query methods named like `findByCategory` are parsed according to Spring Data naming conventions.
- Methods annotated with `@Query` use the query declared in the annotation.
- Custom methods can invoke `ElasticsearchOperations` directly.

For `findByCategory`, Spring Data parses the method name, identifies the `category` property and the parameter to match, and constructs an internal query object representing the search condition. The resulting Query DSL depends on the field type, mapping, and library version.

For example, `category` is declared as `keyword`, making it suitable for exact matching. If the field were changed to `text`, Elasticsearch could analyze its content into tokens, altering search behavior and results.

### The repository delegates work to the Operations layer

Repositories typically delegate Elasticsearch operations to `ElasticsearchOperations`. This is Spring Data's abstraction for operations such as searching, saving, deleting, and creating indices.

The common implementation in applications using the Java API Client is `ElasticsearchTemplate`. The template receives the query along with entity metadata, prepares the request, and invokes the client.

If a service injects `ElasticsearchOperations` and calls `search` directly, the flow bypasses the repository proxy and method-name parsing step. Request preparation, HTTP transport, and response conversion still occur in the operations layer and below.

## 2. Spring Data prepares the request

Before sending a request, Spring Data must determine **where to search**, **what conditions to match**, and **what results to retrieve**.

### Resolving the entity and index

The entity type passed into the search operation allows Spring Data to look up mapping metadata. In the example above:

- `@Document(indexName = "products")` declares the entity's default index.
- `@Id` marks the property representing the Elasticsearch document ID.
- `@Field` describes the field type and mapping options such as analyzer.
- Additional metadata can specify date formats, nested objects, field names, or mapping strategies.

The target index may be a concrete index or an alias. Some operations accept `IndexCoordinates` to specify the target index at call time. Thus, the final index name comes from metadata or operation parameters rather than necessarily being hardcoded in the service.

Mappings on Java classes tell Spring Data how to convert data. The actual mapping on the cluster remains an Elasticsearch configuration. If an index already exists with an older mapping, editing Java annotations does not automatically cause Elasticsearch to alter the existing mapping. Inspect the index mapping whenever search behavior diverges from expectations.

### Building the query representation

Spring Data supports several ways to express search conditions:

| Declaration style | Role |
|---|---|
| Derived query, e.g., `findByCategory` | Spring Data parses the method name and creates a query |
| `@Query` | Declares JSON query content along with parameters |
| `CriteriaQuery` | Builds conditions using Spring Data's Criteria API |
| `NativeQuery` | Builds queries backed by the Elasticsearch Java API Client and Query DSL |
| `ElasticsearchOperations.search(...)` | Calls the operations layer directly with a `Query` object |

A query can also carry information beyond filter conditions:

- `Pageable` defines the page number and page size.
- `Sort` defines the sort order.
- Highlight specifies fields for matching snippets.
- Aggregations instruct Elasticsearch to compute statistics or group data.
- Source filtering restricts which fields are retrieved from `_source`.
- Routing, preference, and other search options influence request scope or execution behavior.

All of this information is assembled into a complete search request specification.

### Converting a Spring Data query into an Elasticsearch request

On the Java API Client path, Spring Data's request converter translates the `Query` object into a request understood by the Elasticsearch client, typically a `SearchRequest`.

This translation combines:

- The index or `IndexCoordinates`.
- The Query DSL.
- `from` and `size` for offset-based pagination.
- Sort, source filters, highlights, and aggregations if present.
- Routing or other search options if configured.

`ElasticsearchConverter` and mapping metadata supply the information needed to work with entities. When saving or reading entities, the converter transforms between Java objects and document representations. Request conversion must likewise preserve index details and Spring Data-supported options.

One distinction to keep clear: **a Java query object is not complete HTTP JSON**. It is an application-layer model. Adapter and client layers convert that model into the wire-format request.

## 3. From the Elasticsearch Java API Client to HTTP

In modern Spring Data Elasticsearch setups, the standard client path uses the Elasticsearch Java API Client (`co.elastic.clients.elasticsearch.ElasticsearchClient`) along with its underlying transport and REST client. Older projects may use different clients or transport setups; inspect the project's actual dependencies and configuration to confirm which classes run.

The Java API Client provides a strongly typed Java API. Neither the application nor Spring Data needs to concatenate JSON strings and manage HTTP manually per query. The client accepts request objects, serializes them, and sends them through the transport.

### The transport handles network communication

The transport is responsible for sending requests to a configured Elasticsearch node. Depending on client configuration, components at this layer handle:

- Connecting to one or more nodes.
- Connection pooling and connection reuse.
- TLS/HTTPS.
- Authentication and HTTP headers.
- Timeouts, connection errors, and retry or node-failover policies per client configuration.

The request is serialized into an HTTP method, URL, headers, and body. For a search on a specific index, the request typically takes this form:

~~~http
POST /products/_search
Content-Type: application/json

{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "laptop"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "category": "computer"
          }
        }
      ]
    }
  },
  "from": 0,
  "size": 10
}
~~~

This illustrates the HTTP shape of a search; real requests may include extra headers, URL parameters, or additional body sections. When searching across multiple indices or aliases, the path segment differs. Some APIs also allow cluster-level search endpoints.

Key elements in the example:

- `POST /products/_search`: invokes the Search API on the `products` index.
- `match`: searches `name` content according to the field's analyzer.
- `term`: matches exact values on a `keyword` field such as `category`.
- `from`: starting offset of the result page.
- `size`: maximum number of hits to retrieve on the page.

For deep pagination queries, `from`/`size` can be resource-intensive because Elasticsearch must hold and sort many intermediate results. When traversing large data sets, consider `search_after` paired with a stable sort or an appropriate scrolling mechanism for your Elasticsearch version.

### HTTP requests do not send the whole Java entity

A search request primarily describes conditions and how to fetch documents. It does not upload an entire `Product` object to the cluster. Elasticsearch only knows about its indices, mappings, and the documents stored in those indices.

The write path follows the same layered pattern with different requests. For example, `save(product)` converts the entity into a document and calls the index or document update API. A subsequent search reads indexed documents; when a document becomes visible in search results depends on Elasticsearch's refresh behavior.

## 4. Elasticsearch receives and executes the search

Upon receiving the HTTP request, Elasticsearch processes it inside the cluster. The receiving node acts as the coordinating node for the search operation.

### Resolving indices and shards

Elasticsearch resolves the index name or alias in the URL, verifies access permissions, and identifies which shards must participate.

An index can consist of multiple primary shards and replica shards. The coordinating node selects appropriate shard copies based on cluster state, routing, and request options. If the request supplies `routing`, the shard scope can be narrowed; otherwise, a typical query may fan out across multiple shards.

### Query phase

During the query phase, shards execute the search against their local data:

1. Read index structures and apply the Query DSL.
2. Identify matching documents.
3. Compute scores if the query uses relevance ranking.
4. Apply sorting and retain the candidate hits needed for the requested page.
5. Compute local aggregation results if requested.

Each shard returns candidate hit metadata to the coordinating node. The coordinating node merges shard results, establishes global ordering, and identifies which hits belong to the page to return.

### Fetch phase

Once it knows which documents to return, Elasticsearch runs the fetch phase to retrieve the content and fields needed for those hits. Depending on the request, this data may include `_source`, stored fields, doc values, highlights, or other metadata.

The coordinating node merges the fetched results into the final response. For distributed searches, the response is therefore assembled across shards rather than coming simply from a single shard.

### Why might a saved document not be immediately searchable?

A successful index operation means Elasticsearch has accepted the document write. Whether that document appears in searches also depends on refresh: a refresh makes newly written changes visible to search operations.

Consequently, if an application calls `save` and immediately calls `search` without seeing the document, check the refresh interval and the write operation's refresh policy. Do not default to forcing immediate refreshes on every write, as frequent refreshes can hurt performance.

## 5. The response returns to Java

Elasticsearch returns an HTTP response, usually JSON containing execution details and the list of hits. A condensed response might look like this:

~~~json
{
  "took": 4,
  "timed_out": false,
  "_shards": {
    "total": 3,
    "successful": 3,
    "skipped": 0,
    "failed": 0
  },
  "hits": {
    "total": {
      "value": 42,
      "relation": "eq"
    },
    "max_score": 1.7,
    "hits": [
      {
        "_index": "products",
        "_id": "p-100",
        "_score": 1.7,
        "_source": {
          "name": "Laptop Pro",
          "category": "computer",
          "price": 1200.0
        }
      }
    ]
  }
}
~~~

Fields commonly worth checking:

- `took`: time Elasticsearch reports for executing the search, in milliseconds.
- `_shards`: number of participating shards and their success/failure counts.
- `hits.total.value`: count of matching hits reported in total hits.
- `hits.total.relation`: indicates whether the count is exact (`eq`) or a lower bound (`gte`).
- `_id`: document ID in Elasticsearch.
- `_score`: relevance score when ranking applies.
- `_source`: returned document data.

The Java API Client decodes the response into the client's Java types. Spring Data's adapter layer further transforms that response into Spring Data's result model.

### Converting `_source` into an entity

Given the target type `Product`, Spring Data uses converters and mapping metadata to construct Java objects:

- Reads fields from `_source`.
- Converts JSON data types into Java property types.
- Applies custom converters if the project registers any.
- Extracts the document ID from hit metadata and populates the property annotated with `@Id`.
- Preserves search metadata such as score, sort values, highlights, and inner hits in the corresponding hit wrapper.

Conversion succeeds only when the returned data matches the Java types and mapping. For example, a date field formatted differently from what the converter expects can cause conversion errors even when Elasticsearch executed the query successfully.

### `SearchHits` and `SearchHit`

When calling `ElasticsearchOperations.search`, the return type is typically `SearchHits<T>`. This wrapper holds both the result list and metadata for the entire search execution.

Each `SearchHit<T>` element can provide:

- `getContent()`: the converted entity.
- `getId()`: document ID.
- `getScore()`: hit score.
- `getSortValues()`: sort values returned by Elasticsearch.
- `getHighlightFields()`: highlighted snippets.
- Other metadata such as inner hits depending on the query type.

Example:

~~~java
SearchHits<Product> hits = operations.search(query, Product.class);

long totalHits = hits.getTotalHits();

for (SearchHit<Product> hit : hits.getSearchHits()) {
    Product product = hit.getContent();

    System.out.println("id = " + hit.getId());
    System.out.println("score = " + hit.getScore());
    System.out.println("name = " + product.getName());
}
~~~

If a repository returns `List<Product>`, the application receives a list of entities and does not directly retain the full metadata from `SearchHits`. When total hits, scores, highlights, or sort values are needed, pick a metadata-rich return type supported by the repository API or call `ElasticsearchOperations`.

### Returning results to the service and controller

Once conversion finishes, results travel back up through the calling layers:

1. The client returns the response to the operations layer.
2. Operations converts the response into `SearchHits`, `SearchPage`, or the corresponding result type.
3. The repository returns the type declared by the method signature.
4. The service receives the result and applies business logic.
5. The controller can map the result into the application's API response.

Spring Data does not dictate the public JSON structure of the application's REST API. Controllers and the presentation layer remain responsible for selecting which fields are exposed to external clients.

## 6. Calling search directly via `ElasticsearchOperations`

Repositories fit common queries with clear conventions. When complex Query DSL is required, you can build a `NativeQuery` and call operations directly.

The following example searches for products whose name matches `laptop`, filters strictly for category `computer`, and retrieves the first 10 results:

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.Query;

Query query = NativeQuery.builder()
    .withQuery(q -> q
        .bool(b -> b
            .must(m -> m
                .match(mm -> mm
                    .field("name")
                    .query("laptop")
                )
            )
            .filter(f -> f
                .term(t -> t
                    .field("category")
                    .value(FieldValue.of("computer"))
                )
            )
        )
    )
    .withPageable(PageRequest.of(0, 10))
    .build();

SearchHits<Product> hits = operations.search(query, Product.class);

for (SearchHit<Product> hit : hits.getSearchHits()) {
    Product product = hit.getContent();
    // Process the product and hit metadata
}
~~~

`NativeQuery` lets you describe queries using Elasticsearch's Java API. `PageRequest` supplies paging details to Spring Data. `operations.search` accepts the query along with the entity type to resolve the mapping and convert response documents into `Product`.

Field names in Query DSL must match the mapping on the index. If a Java property maps to a different field name, inspect the live mapping and the sent request to make sure the DSL references the right field.

Specific APIs can vary across Java API Client and Spring Data Elasticsearch versions. When adapting examples to a project, treat the project's existing dependencies as authoritative and check imports for `NativeQuery`, `Query`, and `FieldValue`.

## 7. Comparing Java operations to HTTP APIs

Different repository methods map to different Elasticsearch APIs. The table below outlines common endpoints as a guide when tracing requests; actual requests can vary with version, ID types, aliases, and configuration.

| Java call | Meaning | Common HTTP API |
|---|---|---|
| `repository.findById(id)` | Read a single document by ID | `GET /products/_doc/{id}` |
| `repository.save(product)` | Index or update a document | `PUT /products/_doc/{id}` or corresponding index API |
| `repository.deleteById(id)` | Delete a document by ID | `DELETE /products/_doc/{id}` |
| `repository.findByCategory(value)` | Find documents matching conditions | `POST /products/_search` |
| `operations.search(query, Product.class)` | Search using a query built in Java | `POST /products/_search` |

Do not assume every `find...` method calls the Search API. `findById` typically reads directly by document ID, whereas conditional finder methods usually invoke the Search API.

## 8. How to trace requests when debugging

When results deviate from expectations, trace each boundary along the flow rather than staring solely at the repository call line.

### Inspect from the application layer

Verify:

- The service calls the right repository or operations instance.
- Passed arguments hold the expected values.
- The return type retains the metadata you need.
- `Pageable` and `Sort` specify the right page, size, and direction.

If the method is a derived query, check that property names match the entity. If using `@Query` or `NativeQuery`, inspect the JSON/DSL and parameter values.

### Inspect the index and mapping

You can use Elasticsearch APIs or cluster management tools to view the mapping:

~~~http
GET /products/_mapping
~~~

Cross-check:

- Is the index or alias correct?
- Is the target field `text`, `keyword`, numeric, date, or another type?
- Does the `text` field's analyzer match the intended search behavior?
- Do field names in Query DSL match the live mapping?
- Is `_source` enabled and does it contain the fields the application needs to read?

A frequent mistake is using `term` on a `text` field when trying to match the entire value exactly, or using `match` when exact matching on `keyword` is required.

### Inspect HTTP requests and responses

In development environments, you can enable appropriate logging at the client/transport layer or use Elasticsearch request inspection tools. Exact logger names and activation settings depend on the client version. Avoid logging request or response bodies containing sensitive data in production without proper access controls and log retention policies.

Capture the actual request and replay it in Elasticsearch Dev Tools or an HTTP client. For example, if the request is `POST /products/_search`, run the exact same body to distinguish a query issue from an entity conversion issue.

Additional useful tools:

- `GET /_cat/indices?v` to check whether the index exists and inspect its status.
- `POST /products/_validate/query?explain=true` to validate a query and inspect how Elasticsearch interprets it.
- `_explain` for a specific document to see why it matched or failed to match.
- Profile API when analyzing query execution cost; enable it only when needed because profiling adds overhead.

### Categorizing errors by layer

| Symptom | Layer to inspect first |
|---|---|
| Repository cannot be created or bean missing | Spring configuration, dependencies, repository scanning |
| Cannot convert query into request | Query builder, API compatibility across versions |
| Connection refused or timeout | Host, port, TLS, network, timeouts, and cluster status |
| HTTP 401 or 403 | Authentication, roles, and index access permissions |
| HTTP 404 or index not found | Index name, alias, and index creation process |
| HTTP 400 or query parse error | Query DSL, field names, data types, and mapping |
| Shard failure or HTTP 5xx | Cluster health, shards, nodes, and server logs |
| Hits returned but entity creation fails | `_source`, Java types, date formats, and custom converters |
| Write succeeds but search does not find it | Refresh and whether the document has been refreshed |

A request can succeed at the HTTP level yet still contain shard failures or data conversion errors. Always inspect the HTTP status, response body, `_shards` details, and root exception rather than checking only whether the client received a response.

## 9. Key points to remember when designing search

**Distinguish `text` and `keyword`.** `text` is typically tokenized for content search; `keyword` preserves values for exact matching, filtering, grouping, or sorting. Choose field types according to business intent.

**Java mappings and cluster mappings must stay consistent.** Annotations describe how Spring Data converts entities and can be used during index creation. Existing mappings on the cluster still need independent verification.

**Pagination affects search cost.** `PageRequest` typically maps to `from` and `size`. When paging deeply across many pages, evaluate `search_after` and a stable sort.

**Choose result types based on needs.** `List<T>` is convenient when only entities are needed. `SearchHits<T>` fits cases requiring scores, total hits, highlights, or sort values. Returning metadata-rich types avoids extra requests for data already included in the initial response.

**Refresh affects immediate read-after-write visibility.** If a business flow must immediately read newly saved documents, design an intentional refresh policy and weigh its cost.

**Track client versions.** Spring Data Elasticsearch, Elasticsearch server, and the Elasticsearch Java API Client must be compatible. When upgrading, check dependencies, transport settings, request types, and builder APIs instead of just fixing imports until code compiles.

## 10. Reviewing the entire flow

For a call to `productRepository.findByCategory("computer")`, the typical path is:

1. The service invokes the repository method.
2. The repository proxy receives the call and Spring Data's query mechanism parses `findByCategory`.
3. Spring Data constructs a query from the property and parameter.
4. The repository delegates execution to `ElasticsearchOperations`.
5. Operations resolves the index and combines the query with pagination details.
6. The request converter creates an Elasticsearch Java API Client request.
7. The client serializes the request and the transport sends HTTP to Elasticsearch.
8. The coordinating node resolves the index, selects shards, and runs query/fetch phases.
9. Elasticsearch returns a response containing hits, `_source`, and metadata.
10. The client decodes the response; Spring Data converters transform data into `Product`.
11. Operations and the repository return the result to the service.
12. The service passes results to the controller or continues business processing.

When you understand the boundaries between repositories, operations, converters, the Java API Client, HTTP transport, and the Elasticsearch cluster, you can pinpoint whether a failure stems from query creation, request transmission, shard execution, or response-to-entity conversion. That is how you trace a Java call all the way to an HTTP request and back to search results.
