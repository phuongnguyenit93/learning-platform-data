# Migrating from TransportClient or RestHighLevelClient to the Appropriate Client

Elasticsearch has evolved its Java clients across multiple generations. Legacy applications may use `TransportClient` to connect directly to nodes over the transport protocol, or `RestHighLevelClient` (HLRC) to call REST APIs with typed Java request/response objects. For new applications, the current direction is the **Elasticsearch Java API Client** (`co.elastic.clients:elasticsearch-java`), which uses HTTP REST transport and provides strongly typed Java APIs. Spring Data Elasticsearch has also transitioned to the new client in modern releases.

Switching clients is not merely swapping a dependency. Connection configuration, authentication/TLS, query builders, bulk responses, aggregations, exception handling, serialization, and resource closing lifecycles can all change. Identify the exact versions of the Elasticsearch server, Spring Boot, Spring Data Elasticsearch, and the Java client before editing code.

If the application uses Spring Data Elasticsearch, most standard CRUD/search operations should go through `ElasticsearchRepository`, `ElasticsearchOperations`, or `ReactiveElasticsearchOperations`. The Java API Client can be used for newer APIs not yet covered by the abstraction. Maintaining this boundary keeps domain/service code decoupled from a specific client's request/response types.

## 1. Three client generations to distinguish

| Client | Protocol | Characteristics | Directional Status |
|---|---|---|---|
| `TransportClient` | Elasticsearch transport protocol, typically port 9300 | Direct node/cluster connection, discovery, and cluster settings; legacy API | Deprecated in Elasticsearch 7.0 and removed in Elasticsearch 8.0 |
| `RestHighLevelClient` | HTTP REST, typically port 9200 | Typed Java requests/responses built atop the Low Level REST Client | Deprecated in Elasticsearch 7.15; replaced by the Java API Client |
| Elasticsearch Java API Client | HTTP REST | Modern Java API, typed builders, typed responses, sync and async | Recommended client for new development; choose a server-compatible version |

There is also the **Low Level REST Client** (`org.elasticsearch.client:elasticsearch-rest-client`). This is a low-level HTTP client for sending `Request` and receiving `Response`. HLRC was built on the Low Level REST Client; the Java API Client uses REST transport to send requests while offering its own typed Java API layer.

### Do not confuse transport and HTTP ports

- `TransportClient` typically connects to the transport port, usually defaulting to `9300`.
- REST clients connect to the HTTP/HTTPS endpoint, usually `9200`.
- When migrating from `TransportClient` to a REST client, open the proper network route/firewall, update endpoints, and configure TLS/HTTP authentication.
- You cannot replace `9300` with `9200` in the same configuration and expect `TransportClient` to work; these are two distinct protocols.

## 2. Why you must move off TransportClient

`TransportClient` was once the standard way for Java applications to connect directly to an Elasticsearch cluster. It used the internal transport protocol, knew the cluster name, performed node discovery, and routed requests to nodes.

Drawbacks in modern architectures:

- `TransportClient` is tightly coupled to Elasticsearch's internal protocol and compatibility constraints.
- The application depends on directly reachable transport nodes.
- Cluster discovery/sniffing configuration may not work well with proxies, managed services, or cloud environments.
- Server and client upgrades carry tighter version coupling.
- `TransportClient` was removed in Elasticsearch 8.0.

An application using `TransportClient` cannot connect directly to Elasticsearch 8 using the old client. You must migrate to an HTTP REST client before upgrading the server to a version that no longer supports the transport protocol.

### Illustrative legacy configuration

```java
Settings settings = Settings.builder()
    .put("cluster.name", "search-cluster")
    .build();

TransportClient client = new PreBuiltTransportClient(settings)
    .addTransportAddress(
        new TransportAddress(
            InetAddress.getByName("es-node-1"),
            9300
        )
    );
```

This code depends on legacy transport classes. When migrating, do not retain `Settings`, `PreBuiltTransportClient`, or `TransportAddress` in the new configuration. Replace them with the HTTP endpoint, TLS, and authentication mechanism required by the cluster.

## 3. Why you should replace RestHighLevelClient

HLRC provided typed APIs for search, index, update, delete, bulk, aggregations, and many administrative APIs. It made Java programming more ergonomic than manually constructing JSON REST requests. However, Elastic deprecated HLRC in Elasticsearch 7.15 and introduced the Java API Client as its replacement.

Key considerations:

- HLRC uses types such as `SearchRequest`, `SearchSourceBuilder`, `SearchResponse`, `BulkRequest`, and `RequestOptions`.
- The Java API Client uses new types under `co.elastic.clients.elasticsearch.*`.
- Request builders, response models, Query DSL, and aggregation variants are not directly compatible.
- You cannot merely change imports from `org.elasticsearch.*` to `co.elastic.clients.*`.
- New API features are developed on the Java API Client.

If an application currently runs against an older Elasticsearch version, a transitional phase may be needed. Still, HLRC should not be chosen as the long-term architectural target for new systems. Select client and Spring Data versions from a supported compatibility matrix.

## 4. Role of the Low Level REST Client

The Low Level REST Client is a low-level HTTP client:

```java
RestClient restClient = RestClient.builder(
    new HttpHost("localhost", 9200, "http")
).build();

Request request = new Request("GET", "/products/_search");
request.setJsonEntity("""
    {
      "query": {
        "match": {
          "name": "wireless mouse"
        }
      }
    }
    """);

Response response = restClient.performRequest(request);
```

The application must build JSON manually, manage response bodies and statuses, and handle deserialization. This is an option when a specialized REST endpoint lacks typed client support or when writing very low-level integrations.

For most search/index use cases, the Java API Client reduces manual effort via request builders and typed responses. Spring Data Elasticsearch provides an even higher-level abstraction for repositories, mappings, and template operations.

## 5. What is the Java API Client?

The Elasticsearch Java API Client is distributed via the artifact:

`co.elastic.clients:elasticsearch-java`

The client provides:

- Typed Java APIs for Elasticsearch REST APIs.
- Builder lambdas to construct requests.
- Typed responses for a specified document class.
- Query DSL and aggregations modeled after the client's type system.
- Synchronous API `ElasticsearchClient`.
- Asynchronous API `ElasticsearchAsyncClient`, typically returning `CompletableFuture`.
- JSON-P mapping via `JsonpMapper`, with `JacksonJsonpMapper` available.

The Java API Client uses REST transport. In a classic setup, `RestClientTransport` combines the Low Level REST Client and `JacksonJsonpMapper`:

```java
RestClient restClient = RestClient.builder(
    new HttpHost("localhost", 9200, "http")
).build();

ElasticsearchTransport transport =
    new RestClientTransport(
        restClient,
        new JacksonJsonpMapper()
    );

ElasticsearchClient client = new ElasticsearchClient(transport);
```

This snippet illustrates manual client construction. If using Spring Boot or Spring Data Elasticsearch, prefer framework auto-configuration or `ClientConfiguration` to avoid creating redundant connection pools/clients.

## 6. Choosing the client version based on server and Spring Data versions

Do not upgrade a single dependency without checking the entire version set. At least four components are involved:

1. Elasticsearch server.
2. Spring Boot.
3. Spring Data Elasticsearch.
4. Elasticsearch Java API Client and the REST transport used by Spring Data.

Different Spring Data Elasticsearch generations use different clients. Spring Data Elasticsearch 4.x lines align with the Elasticsearch 7 ecosystem and HLRC; 5.x lines move to the Elasticsearch Java API Client for the Elasticsearch 8 ecosystem. Newer lines may change requirements for Java, Spring Framework, and Elasticsearch server.

| Context | Guidance |
|---|---|
| Spring Data Elasticsearch 4.x applications | Usually based on HLRC; check the compatibility matrix and Spring Data upgrade plan |
| Spring Data Elasticsearch 5.x applications | Uses the Java API Client; do not add HLRC for new code |
| New Spring Boot applications | Use the corresponding starter/BOM and let dependency management select compatible versions |
| Applications calling REST APIs directly | Use a server-compatible Java API Client, or the Low Level REST Client where low-level access is truly needed |
| Applications using `TransportClient` | Migrate to REST before upgrading to Elasticsearch 8 or higher |

This is generational guidance, not a promise that every minor version works with every server. Before upgrading, verify the compatibility matrix and release documentation for your exact project versions.

### Use the BOM instead of pinning individual jars

With Spring Boot, let Spring Boot dependency management manage Spring Data, Spring Framework, Reactor, and related clients. Avoid arbitrarily forcing a newer or older `elasticsearch-java` version than the one tested with Spring Data.

If an override is required, justify it, verify binary/API compatibility, and run integration tests against the exact Elasticsearch server.

## 7. Inventory dependencies before migration

Before editing code, identify whether legacy clients are pulled in directly or transitively:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Or filter dependencies:

```bash
./gradlew dependencyInsight \
  --dependency elasticsearch \
  --configuration runtimeClasspath
```

With Maven:

```bash
mvn dependency:tree
```

Look for common artifacts:

| Artifact/Package | Meaning |
|---|---|
| `org.elasticsearch:elasticsearch` | Core/server-related Java classes used by some legacy clients |
| `org.elasticsearch.client:transport` | Legacy `TransportClient` |
| `org.elasticsearch.client:elasticsearch-rest-high-level-client` | HLRC |
| `org.elasticsearch.client:elasticsearch-rest-client` | Low Level REST Client |
| `co.elastic.clients:elasticsearch-java` | Java API Client |
| `spring-data-elasticsearch` | Spring Data repository/template abstraction |

Do not delete a dependency based solely on its name. Check the dependency graph to see which library still requires it and which version is resolved. Avoid keeping two client generations side by side unless there is a clear transitional need.

## 8. Find all code depending on legacy clients

Search the codebase for legacy imports and APIs:

```bash
rg -n "TransportClient|PreBuiltTransportClient|TransportAddress|Settings\\.builder" .
rg -n "RestHighLevelClient|RequestOptions|SearchSourceBuilder|SearchRequest|BulkRequest" .
rg -n "org\\.elasticsearch\\.action|org\\.elasticsearch\\.search\\.builder|org\\.elasticsearch\\.client" .
```

Categorize usage sites:

- Connection configuration and lifecycle.
- Repositories/custom repositories.
- Search query builders.
- Aggregations, sorting, highlighting, and suggestions.
- Bulk/index/update/delete operations.
- Index/template/alias management.
- Exception mapping and retries.
- Custom serializers/deserializers.
- Test fixtures and mocks.

Do not search only for client constructors. Legacy request/response types may be embedded deeply in services, mappers, tests, or public interfaces.

## 9. Connection configuration changes

`TransportClient` typically requires a cluster name, transport addresses, and possibly sniffing. REST clients require HTTP/HTTPS URIs, TLS, credentials/API keys, and timeout/connection settings.

| Legacy Configuration | New REST Configuration |
|---|---|
| Cluster name | Usually not needed in the REST client |
| Transport address, port 9300 | HTTP/HTTPS URI, usually port 9200 |
| Transport sniffing | Load balancer/service discovery/DNS appropriate for the environment |
| Transport-level security | HTTPS/TLS and HTTP authentication |
| Internal node list | One or more REST endpoints supported by the client |
| Transport connection settings | HTTP connection pool, connect/response timeouts, and retry policy |

Do not carry `cluster.name` or transport sniff settings over to a REST client. Design the new connection setup for how the cluster is deployed: self-managed, Kubernetes, cloud service, or managed Elasticsearch.

## 10. Configuring Spring Boot with properties

With Spring Boot auto-configuration for Elasticsearch, settings are typically placed in `application.yml`:

```yaml
spring:
  elasticsearch:
    uris:
      - https://es.example.internal:9200
    username: ${ELASTICSEARCH_USERNAME}
    password: ${ELASTICSEARCH_PASSWORD}
    connection-timeout: 5s
    socket-timeout: 30s
```

Property names and value types depend on the Spring Boot version. Check the configuration metadata/reference for your exact version before use. If using API key or certificate authentication, configure according to version support or provide a suitable custom client configuration.

Do not hard-code passwords, API keys, or private keys in committed source or config files. Use a secret manager, environment variables, or your platform's secret management mechanism.

### When to use auto-configuration

Auto-configuration is appropriate when:

- Only one primary client/connection configuration is needed.
- Endpoints, auth, and timeouts can be configured via properties.
- Complex custom transport is unnecessary.
- You want Spring Boot to manage bean lifecycles.

Do not manually create a second client alongside auto-configuration if it already provides the needed beans. Two clients can create two connection pools, consume extra sockets/memory, and complicate health/metrics.

## 11. Configuring Spring Data Elasticsearch with ClientConfiguration

When custom configuration is needed, Spring Data Elasticsearch provides `ClientConfiguration` and version-specific configuration base classes.

Example for imperative configuration:

```java
import java.time.Duration;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchConfiguration;

@Configuration
public class ElasticsearchConfig extends ElasticsearchConfiguration {

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
            .connectedTo("es.example.internal:9200")
            .usingSsl()
            .withBasicAuth(
                System.getenv("ELASTICSEARCH_USERNAME"),
                System.getenv("ELASTICSEARCH_PASSWORD")
            )
            .withConnectTimeout(Duration.ofSeconds(5))
            .withSocketTimeout(Duration.ofSeconds(30))
            .build();
    }
}
```

Packages/classes and builder options vary across Spring Data Elasticsearch versions. Cross-check Javadoc for the actual dependency. If Spring Boot auto-configuration is already customized via properties, do not simultaneously define another configuration class without knowing which beans take precedence.

### TLS and certificate validation

In production, use HTTPS and verify certificate chains/hostnames. Never disable certificate validation just to get a connection working in a live environment. If the cluster uses a private CA, configure the truststore/SSL context using the mechanism supported by the client/framework.

Do not treat `usingSsl()` as proof that all certificates are properly configured. Verify CA trust, hostnames, certificate expiration, and TLS policies in the actual deployment.

## 12. TransportClient sniffing and REST discovery

`TransportClient` could sniff the cluster to discover node addresses. In cloud, Kubernetes, proxy, or managed-service environments, having the client connect directly to advertised node IPs often fails because:

- Node publish addresses are unreachable from the application network.
- Only a single gateway endpoint is exposed.
- TLS certificates do not match internal node hostnames.
- Managed services do not expose transport ports to applications.
- Pod/node IPs change across lifecycles.

With REST clients, you typically use a DNS/service endpoint or platform load balancer. Ensure REST endpoints respond consistently and the connection pool distributes requests properly.

Do not enable sniffing just because the legacy configuration used it. If you use node discovery, verify server publish addresses, TLS identities, routing, and network policies.

## 13. From HLRC to Java API Client: data type changes

Example search with HLRC:

```java
SearchRequest request = new SearchRequest("products");
SearchSourceBuilder source = new SearchSourceBuilder()
    .query(QueryBuilders.matchQuery("name", "wireless mouse"))
    .size(20);
request.source(source);

SearchResponse response =
    highLevelClient.search(request, RequestOptions.DEFAULT);
```

With the Java API Client:

```java
SearchResponse<ProductDocument> response = client.search(
    search -> search
        .index("products")
        .size(20)
        .query(query -> query
            .match(match -> match
                .field("name")
                .query("wireless mouse")
            )
        ),
    ProductDocument.class
);
```

Key differences:

- Requests are built using lambda builders or builder objects from the Java API Client.
- Query DSL is expressed via typed variants such as `match`, `term`, `bool`, and `range`.
- Response types typically take a generic document class.
- `RequestOptions.DEFAULT` as used in HLRC no longer applies.
- Legacy `SearchSourceBuilder` or `QueryBuilders` cannot be reused.

## 14. Migrating QueryBuilders to typed Query DSL

HLRC example:

```java
QueryBuilder query = QueryBuilders.boolQuery()
    .must(QueryBuilders.matchQuery("name", "mouse"))
    .filter(QueryBuilders.termQuery("status", "ACTIVE"))
    .filter(QueryBuilders.rangeQuery("price").lte(100));
```

Java API Client:

```java
Query query = Query.of(q -> q.bool(b -> b
    .must(m -> m.match(mm -> mm
        .field("name")
        .query("mouse")
    ))
    .filter(f -> f.term(t -> t
        .field("status")
        .value("ACTIVE")
    ))
    .filter(f -> f.range(r -> r
        .number(n -> n
            .field("price")
            .lte(100.0)
        )
    ))
));
```

Scalar types, ranges, and builder overloads may vary by client version. Use the compiler and Javadoc to pick the exact variant. Do not translate a query by renaming classes while ignoring the semantics of `must`, `filter`, `should`, `minimum_should_match`, or scoring.

### Benefits of typed DSL

- Better IDE autocomplete.
- Compiler catches many structural mistakes.
- Fewer JSON field/operator typos from string concatenation.
- Typed responses reduce manual parsing.
- Easy to create reusable query helpers/factories.

However, typed DSL does not guarantee business-correct queries. Test query behavior against real Elasticsearch with representative mappings and data.

## 15. Migrating SearchResponse and hit mapping

HLRC typically returns `SearchResponse` containing `SearchHits`, where each hit has `_id`, `_source`, score, sort values, and metadata.

The Java API Client returns `SearchResponse<TDocument>` with a list of typed hits:

```java
SearchResponse<ProductDocument> response = client.search(
    s -> s.index("products")
        .query(q -> q.match(m -> m.field("name").query("mouse"))),
    ProductDocument.class
);

for (Hit<ProductDocument> hit : response.hits().hits()) {
    String id = hit.id();
    float score = hit.score() == null ? 0.0f : hit.score();
    ProductDocument product = hit.source();
}
```

During migration, check:

- `_source` may be null if the request omits source or mapping fails.
- Score may be null for queries/contexts without scoring.
- Sort values must be read with the proper JSON value type.
- Highlighting, inner hits, matched queries, and explanations have new structures.
- `total` has a relation such as `eq` or `gte`; it is not always an exact count if total hits tracking is bounded.
- If using field collapsing or aggregations, response accessors differ from HLRC.

Do not assume total hits is always an exact `long` as legacy code might have read it. Check `track_total_hits` and the response relation.

## 16. Migrating aggregations

HLRC uses classes such as `TermsAggregationBuilder`, `DateHistogramAggregationBuilder`, `AggregationBuilders`, and response types like `ParsedTerms` and `ParsedDateHistogram`.

The Java API Client uses typed aggregation builders and response variants:

```java
SearchResponse<ProductDocument> response = client.search(
    s -> s.index("products")
        .size(0)
        .aggregations("by_status", a -> a
            .terms(t -> t.field("status"))
        ),
    ProductDocument.class
);

Aggregate aggregate = response.aggregations().get("by_status");
if (aggregate != null && aggregate.isSterms()) {
    for (StringTermsBucket bucket : aggregate.sterms().buckets().array()) {
        String key = bucket.key().stringValue();
        long count = bucket.docCount();
    }
}
```

This snippet illustrates a terms aggregation on a `keyword` field. The variant type depends on mapping and API version; terms aggregations have distinct variants by field type. Read the proper variant rather than casting responses as in HLRC.

### Verifying buckets and counts

- `docCount` is the number of documents in the bucket.
- `sum_other_doc_count` indicates documents belonging to unreturned buckets.
- `terms.size` limits returned buckets and does not necessarily enumerate all values.
- Composite aggregations have different bucket pagination semantics than terms aggregations.
- Filter, nested, and global aggregations must have their scopes re-verified.

Aggregation migration requires comparing results on identical fixtures between the old and new clients.

## 17. Migrating the Bulk API

HLRC:

```java
BulkRequest request = new BulkRequest();
request.add(new IndexRequest("products")
    .id(product.getId())
    .source(jsonSource, XContentType.JSON));

BulkResponse response =
    highLevelClient.bulk(request, RequestOptions.DEFAULT);
```

Java API Client:

```java
BulkResponse response = client.bulk(bulk -> bulk
    .operations(operation -> operation
        .index(index -> index
            .index("products")
            .id(product.getId())
            .document(product)
        )
    )
);

if (response.errors()) {
    for (BulkResponseItem item : response.items()) {
        if (item.error() != null) {
            // Record item.id(), item.status() and item.error().
        }
    }
}
```

The Java API Client can serialize objects directly through the mapper. If the source previously used custom conversion, check `JsonpMapper` and mappings so the transmitted data does not change unexpectedly.

### Partial failures must still be handled

The Bulk API is not transactional. `errors()` can be true even when the overall request was processed. Inspect each item and classify mapping errors, conflicts, 429s, and transient failures. Only retry items that are safe to retry; do not mark an entire batch successful simply because the HTTP call returned a response.

## 18. Migrating Index, Update, and Delete APIs

Legacy request/response objects are not directly compatible with the Java API Client. For example:

| HLRC | Java API Client |
|---|---|
| `IndexRequest` | `IndexRequest<TDocument>` builder |
| `UpdateRequest` | `UpdateRequest<TDocument, TPartialDocument>` builder |
| `DeleteRequest` | `DeleteRequest` builder |
| `GetRequest` | `GetRequest` builder |
| `BulkRequest` | `BulkRequest` builder with `operations` |
| `RequestOptions` | Transport/client configuration and new per-API request options |

For updates, check serialization of `doc`, `upsert`, scripts, and retry-on-conflict. For deletes, check routing and optimistic concurrency metadata. Do not assume defaults match HLRC.

## 19. Migrating index/template/alias APIs

Applications may use HLRC to create indexes, mappings, templates, aliases, and inspect cluster state. The Java API Client organizes these APIs under typed namespaces:

```java
CreateIndexResponse response = client.indices().create(
    create -> create
        .index("products-v2")
        .mappings(mapping -> mapping
            .properties("name", property -> property
                .text(text -> text)
            )
            .properties("status", property -> property
                .keyword(keyword -> keyword)
            )
        )
);
```

In Spring Data Elasticsearch, `IndexOperations` via `ElasticsearchOperations` can handle many index lifecycle tasks:

```java
IndexOperations indexOperations =
    operations.indexOps(ProductDocument.class);

if (!indexOperations.exists()) {
    indexOperations.create();
    indexOperations.putMapping();
}
```

Do not let every application instance automatically create/alter mappings on startup if deployment requires controlled migrations. Index templates, alias switches, and reindexing should typically be managed as intentional release/infrastructure steps.

## 20. Exception handling changes

HLRC throws exceptions and exposes response statuses under the old API, such as `ElasticsearchException`, `ElasticsearchStatusException`, or `ResponseException` at the low level. The Java API Client and transport have a different exception model.

During migration, review:

- HTTP status and error type.
- Error body/caused-by.
- Version conflicts.
- Resource not found.
- Authentication/authorization failures.
- Connection timeouts, socket timeouts, and connection resets.
- Serialization/deserialization errors.
- Request rejections and cluster overload.

Do not catch all exceptions and turn them into `Optional.empty()` or HTTP 200. That can hide connection, mapping, or authorization failures.

### Create application-level exceptions

One way to reduce client coupling is to translate exceptions at the adapter/repository boundary into business exceptions:

```java
try {
    return client.get(request, ProductDocument.class);
} catch (ElasticsearchException ex) {
    if (isNotFound(ex)) {
        throw new ProductNotFoundException(productId);
    }
    throw new SearchInfrastructureException("Elasticsearch get failed", ex);
}
```

Accessor/method names for classifying exceptions depend on the client version. This example only illustrates the principle: domain/service code should not have to import HLRC or Java API Client exceptions everywhere.

## 21. Serialization and mapping

This is one of the most error-prone areas during migration. HLRC typically used `XContentBuilder`, `XContentType`, `XContentParser`, or custom serializers. The Java API Client uses JSON-P and `JsonpMapper`, commonly configured with `JacksonJsonpMapper`.

Check these data types:

- `Instant`, `LocalDate`, `OffsetDateTime`, and date formats.
- Enum serialization.
- Null handling and field omission.
- `BigDecimal`, integers, and floating-point numbers.
- Nested objects and collections.
- Custom field names/aliases.
- Geo types and binary values.
- Unknown fields in responses.
- Custom Jackson modules and naming strategies.

### Using JacksonJsonpMapper

Example mapper configuration:

```java
ObjectMapper objectMapper = new ObjectMapper()
    .findAndRegisterModules();

JsonpMapper jsonpMapper = new JacksonJsonpMapper(objectMapper);
```

This mapper allows the Java API Client to use Jackson for JSON mapping. If the application uses Java Time modules, naming strategies, or custom serializers, ensure those modules are registered and applied consistently by the client.

Spring Data Elasticsearch has its own mapping/conversion infrastructure for repository entities. Do not assume Jackson annotations, Spring Data `@Field`, and JSON-P mapping share identical semantics on every code path. If the same POJO is written through both Spring Data and the Java API Client directly, test serialization on both paths.

## 22. Distinguishing Spring Data mapping from client mapping

Spring Data Elasticsearch provides:

- `@Document` to describe the index.
- `@Id` to map the document ID.
- `@Field` to define field mappings.
- Custom conversions and entity callbacks.
- `ElasticsearchRepository`.
- `ElasticsearchOperations` and `ReactiveElasticsearchOperations`.

The Java API Client directly uses `JsonpMapper` to serialize/deserialize `_source`. It does not automatically invoke the full Spring Data entity conversion/callback pipeline.

This means:

- Writing via `ElasticsearchOperations.save()` applies Spring Data conversions/callbacks.
- Writing directly with `ElasticsearchClient.index()` uses the Java API Client's mapper.
- The same entity can serialize differently if the two mapping configurations diverge.
- When calling the client directly, use clear DTO/document models and test the JSON output.

Do not mix both write paths for the same index unless schema/source compatibility is verified.

## 23. When to use Spring Data abstraction vs. calling Java API Client directly

| Use Case | Appropriate Choice |
|---|---|
| Standard document CRUD | `ElasticsearchRepository` |
| Custom search queries, aggregations, and template operations | `ElasticsearchOperations` |
| Reactive repositories/search | `ReactiveElasticsearchRepository`, `ReactiveElasticsearchOperations` |
| Newer Elasticsearch APIs not yet wrapped by Spring Data | Java API Client |
| Specialized REST endpoints or APIs lacking typed support | Low Level REST Client, with strict control |
| Business logic/domain services | Depend on application ports/services, not client request types |

You do not need to call the Java API Client directly just to use a `match` or `term` query if Spring Data `NativeQuery` already supports it. Using Spring Data's abstraction preserves mappings, repository conventions, and lifecycle integration.

## 24. Migrating custom repositories

If legacy code injects `RestHighLevelClient` into a repository:

```java
public class ProductSearchRepositoryImpl {
    private final RestHighLevelClient client;

    // Builds SearchRequest and parses SearchResponse
}
```

It can be migrated to `ElasticsearchOperations`:

```java
public class ProductSearchRepositoryImpl {

    private final ElasticsearchOperations operations;

    public ProductSearchRepositoryImpl(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<ProductDocument> search(Query query) {
        return operations.search(
            query,
            ProductDocument.class,
            IndexCoordinates.of("products")
        );
    }
}
```

`Query` can be constructed with `NativeQuery`:

```java
Query query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("name")
        .query("wireless mouse")
    ))
    .withPageable(PageRequest.of(0, 20))
    .build();
```

Package/import names and builders depend on the Spring Data version. Custom repository fragments should keep business APIs stable while migrating implementations from HLRC to Spring Data/Java API Client.

## 25. Reactive client is not the same as async Java API Client

The Java API Client provides `ElasticsearchAsyncClient` based on `CompletableFuture`. This is an asynchronous API, but it does not automatically produce Reactive Streams `Mono`/`Flux` with backpressure.

Async example:

```java
ElasticsearchAsyncClient asyncClient =
    new ElasticsearchAsyncClient(transport);

CompletableFuture<SearchResponse<ProductDocument>> future =
    asyncClient.search(
        request,
        ProductDocument.class
    );
```

To integrate with Reactor, you can wrap a `CompletableFuture` as a `Mono`:

```java
Mono<SearchResponse<ProductDocument>> result =
    Mono.fromFuture(() -> asyncClient.search(request, ProductDocument.class));
```

However, you must understand cancellation semantics, executors, connection lifecycles, and backpressure. `Mono.fromFuture` only adapts a single future into a publisher; it does not turn a single API request into a demand-driven stream of documents.

Spring Data Elasticsearch has its own reactive client/operations for reactive repositories. If the application needs end-to-end Reactive Streams, prefer `ReactiveElasticsearchOperations` rather than wrapping the async client everywhere. Verify the exact reactive transport/client version supported by Spring Data.

## 26. Managing client lifecycle and closing resources

Clients and transports own connection pools, threads, and related resources. When constructed manually, close resources cleanly when the application context shuts down:

```java
@Bean(destroyMethod = "close")
RestClient restClient() {
    return RestClient.builder(
        new HttpHost("localhost", 9200, "http")
    ).build();
}
```

With a manual Java API Client, manage both the transport and the underlying `RestClient` according to client/version guidance. Never instantiate a new client per method call or per request; use a Spring-managed singleton bean.

If Spring Boot/Spring Data already manages the client lifecycle, do not manually close the shared bean inside a service. Closing it prematurely breaks other requests; failing to close on shutdown can leak threads/sockets.

## 27. Timeouts, retries, and connection pools

`TransportClient` settings do not map one-to-one to REST. Design:

- Connection timeout: time to establish a connection.
- Socket/response timeout: time waiting for a response.
- Connection pool size and per-route limits.
- Connection keep-alive and stale connection handling.
- Retry policies for network/transient errors.
- Node selection/load balancing.
- Per-API request timeouts where supported.

Do not retry every error. For index/update with stable IDs, retries may be idempotent depending on semantics; for scripted increments or non-idempotent operations, retries can duplicate side effects. A timeout also does not prove the server did not execute the request.

Size timeouts to the workload: autocomplete and interactive search typically need shorter deadlines than exports or batch jobs. Do not set overly long timeouts to mask slow queries or an overloaded cluster.

## 28. Authentication and TLS

Legacy `TransportClient` setups may use separate transport security plugins/settings. REST migration must transition to appropriate HTTP mechanisms:

- HTTPS/TLS.
- Basic authentication or API keys.
- CA certificates/truststores.
- Client certificates if mutual TLS is required.
- Credential rotation.
- Least-privilege roles/index privileges.

Do not pass usernames/passwords in URLs. Do not log `Authorization` headers or API keys. Never disable hostname verification or certificate validation in production.

### TLS checks

Before rollout:

1. Verify endpoints use `https`.
2. Verify the CA is trusted.
3. Verify hostnames match certificates.
4. Verify certificates have not expired.
5. Verify credentials have the proper index/API permissions.
6. Verify rotation does not require unplanned restarts.

## 29. Search semantics to preserve during migration

A query can compile into a valid request yet return different results after migration. Compare:

- `must`, `filter`, `should`, `must_not`.
- `minimum_should_match`.
- Analyzers and multi-fields.
- Fuzziness, prefix, and wildcard queries.
- Sort and missing-value behavior.
- Nested queries/inner hits.
- Highlight fields and fragment settings.
- `track_total_hits`.
- Pagination with `from`/`size`, `search_after`, and PIT.
- Runtime mappings and script fields.
- Routing and preference.
- Source filtering.
- Timeout and `terminate_after`.

Keep query semantics at the business level, build test fixtures, and compare results between the old and new clients on the same cluster/index. Do not rely solely on JSON request snapshots if server semantics also change across versions.

## 30. Search after, PIT, and scroll

Export or deep-pagination applications may use Scroll, `search_after`, or Point in Time (PIT). The new typed API represents these requests/responses differently from HLRC.

When migrating:

- Preserve stable sorting and tie-breakers.
- Retain the PIT ID across pages when using PIT.
- Update the PIT ID if a response returns a new one.
- Close the PIT upon completion/cancellation.
- Check scroll keep-alive and cleanup.
- Do not mix deep `from`/`size` with `search_after`.
- Test cancellation and mid-stream failures.

Do not merely rename methods. Cursor semantics, sort values, and snapshot lifecycles must be preserved.

## 31. Query templates, scripts, and runtime fields

If the application uses stored search templates, Painless scripts, or runtime mappings, verify how the new request builder represents them. Some generic JSON values can be passed as `JsonData`, though that does not ensure every Java value serializes properly if the mapper is unconfigured.

Principles:

- Keep script sources fixed and pass data via params.
- Never accept arbitrary script sources from public clients.
- Verify stored script IDs and permissions.
- Test runtime field types and query behavior.
- Verify template parameters after migration.

## 32. Handling JSON and JsonData

The Java API Client uses `JsonData` for dynamic JSON in certain APIs. It is useful when data shapes are unknown at compile time, though it sacrifices compile-time type safety compared to POJOs.

Example:

```java
JsonData scriptParam = JsonData.of(Map.of(
    "minimumPrice", 10,
    "maximumPrice", 100
));
```

If using a custom mapper, ensure `JsonData` serializes/deserializes with the same `JsonpMapper`. Do not convert all entities to `Map<String, Object>` when strong domain models already exist; preserve typed models whenever possible.

## 33. Layered migration testing

A solid test plan should include:

### Unit tests

- Query factories produce the right filters and operators.
- Mappers convert entities to documents accurately.
- Error adapters classify timeouts/conflicts/validation errors.
- Retries apply only to allowed failures.
- Bulk response parsers handle partial failures.
- Services do not depend directly on legacy request/response types.

### Integration tests

- Connect to the real Elasticsearch server over REST/TLS.
- Authentication and index privileges work.
- Save/get/search/update/delete.
- Bulk item success and partial failure.
- Mapping/date/enum/nested serialization.
- Aggregations, sorting, highlighting, and pagination.
- Alias/index/template management.
- Refresh/search visibility.
- PIT/scroll/`search_after` if applicable.

### Regression tests

- Run identical fixtures and queries on old/new clients in compatible environments.
- Compare IDs, ordering, total relations, aggregation buckets, and highlights.
- Document acceptable differences caused by server version/mapping changes.

Do not merely check that the new client initializes. The goal of migration is preserving business behavior and operational reliability.

## 34. Using Testcontainers or an Elasticsearch test environment

Integration tests need an Elasticsearch instance compatible with the client/Spring Data versions. You can use Testcontainers or an isolated test environment.

Example structure:

```text
JUnit
  |
  v
Spring ApplicationContext
  |
  v
Spring Data Elasticsearch / Java API Client
  |
  v
Elasticsearch test node
```

Select an image version compatible with the client and Spring Data. If production clusters enable security/TLS, maintain a separate test group verifying auth/TLS instead of testing only unsecured HTTP.

Do not run tests against an Elasticsearch image from a different major version and conclude production migration is safe. Client/server compatibility and API behavior must be verified on the target version.

## 35. Migration roadmap from TransportClient

A roadmap can be broken down into steps:

1. Inventory server, Java, Spring Boot, and Spring Data versions.
2. Find all occurrences of `TransportClient`, `PreBuiltTransportClient`, transport addresses, and sniff settings.
3. Identify REST endpoints, network policies, TLS, and authentication.
4. Choose Spring Data/Java API Client versions compatible with the target Elasticsearch.
5. Migrate connection configuration from transport to REST.
6. Replace custom repository/API calls with Spring Data operations or the Java API Client.
7. Update query/aggregation/bulk builders and response parsing.
8. Verify serialization, mapping, retries, timeouts, and resource lifecycle.
9. Run integration/regression tests.
10. Perform a canary rollout and monitor latency, errors, throughput, heap, and connection pools.
11. Remove legacy transport dependencies and configs once no callers remain.

If the current server is Elasticsearch 7.x, you may need to upgrade client and server in compatible increments. Do not upgrade the server to 8.x before applications depending on `TransportClient` have migrated.

## 36. Migration roadmap from RestHighLevelClient

For HLRC, you can break it down:

1. Inventory all HLRC imports and APIs.
2. Upgrade Spring Data Elasticsearch/Spring Boot to a branch using the Java API Client if the architecture relies on Spring Data.
3. Keep repository/service interfaces stable.
4. Migrate basic CRUD/search to `ElasticsearchOperations` or repositories.
5. Migrate specialized APIs to Java API Client typed builders.
6. Replace query builders, aggregation parsing, and bulk response handling.
7. Migrate serializers to `JsonpMapper` or maintain clean Spring Data mapping boundaries.
8. Update exception translation, timeouts, and retries.
9. Run behavioral comparison tests.
10. Remove HLRC dependencies/imports and legacy adapter code.

### Do not migrate everything in a single commit for large codebases

You can introduce an adapter interface at the application boundary:

```java
public interface ProductSearchPort {
    SearchPage<ProductDocument> search(ProductSearchCriteria criteria);
}
```

The old implementation uses HLRC, and the new implementation uses Spring Data/Java API Client. Contract tests run against both implementations during the transition. Once rollout completes, delete the old implementation and legacy dependencies.

Avoid maintaining two implementations long-term without an operational reason; dual paths increase test cost and risk behavioral drift.

## 37. Canary rollout and rollback

For high-traffic systems:

- Deploy the new client to a single instance/canary first.
- Keep index/mapping and query semantics unchanged during the client rollout if possible.
- Compare p50/p95/p99 latency, error rates, connection counts, and throughput.
- Monitor serialization errors, bulk item failures, and rejected requests.
- Run shadow reads if data and cost allow; do not duplicate write side effects.
- Gradually ramp traffic once metrics stabilize.
- Maintain a binary/config rollback plan within server compatibility limits.

If the migration coincides with a major Elasticsearch server upgrade, rollback must account for old client compatibility and index/mapping states. Do not assume rolling back the application binary alone suffices after altering the server or schema.

## 38. Common migration mistakes

### Swapping dependencies while keeping HLRC code

Request/response types are incompatible. API calls and parsing must be rewritten accordingly.

### Using TransportClient with Elasticsearch 8+

`TransportClient` was removed in Elasticsearch 8. Migrate to a REST client.

### Using HLRC for new development

HLRC has been deprecated since 7.15. Choose the Java API Client per the compatibility matrix.

### Configuring the wrong port

Transport ports and HTTP ports use different protocols. REST clients connect to the HTTP/HTTPS endpoint.

### Keeping legacy sniffing in cloud environments

Node publish addresses may be unreachable or mismatch certificates. Use appropriate endpoints/load balancers.

### Creating multiple clients/connection pools

Auto-configuration and custom beans both creating clients can inflate sockets, threads, and memory. Establish a single lifecycle owner.

### Ignoring serialization differences

Dates, enums, nulls, numerics, and nested fields may serialize differently in JSON. Test real payloads.

### Skipping bulk item error checks

HTTP 200 does not mean all bulk actions succeeded. Inspect every response item.

### Testing only client initialization

Successfully constructing a client does not prove queries, aggregations, mappings, and pagination behave identically.

### Wrapping CompletableFuture in Mono and calling it end-to-end reactive

Async APIs do not automatically provide backpressure over a document stream. Choose reactive abstractions when Reactive Streams are required.

## 39. Pre-completion migration checklist

- Elasticsearch server version and Java runtime are confirmed.
- Spring Boot/Spring Data/Java client versions are compatible.
- No callers of `TransportClient` remain.
- No new callers use HLRC.
- REST endpoints, TLS, and authentication work.
- Connection pool and timeouts are tuned for the workload.
- Client/transport lifecycle is managed by Spring.
- Search query and aggregation semantics are preserved.
- Bulk item errors, retries, and idempotency are handled.
- Mappings and JSON serialization are tested.
- PIT/scroll/`search_after` are verified if used.
- Exception translation and logging do not leak secrets.
- Metrics/tracing accurately reflect client operations.
- Integration/regression tests run against the target server version.
- Canary and rollback plans are defined.
- Dependency tree contains no unnecessary legacy artifacts.

## 40. Conclusion

`TransportClient` used the internal transport protocol and was removed in Elasticsearch 8.0. `RestHighLevelClient` used HTTP REST but was deprecated in 7.15; its replacement is the Elasticsearch Java API Client. The new client offers typed builders, typed responses, sync/async APIs, and runs over REST transport. The Low Level REST Client remains useful for low-level HTTP requests, while Spring Data Elasticsearch provides repository/template abstractions for most business needs.

Migration must start from the compatibility matrix across the Elasticsearch server, Spring Boot, Spring Data, and the Java client. Then migrate endpoints/TLS-auth configurations, update request/response builders, aggregations, bulk handling, serialization, exception mapping, and lifecycle management. With Spring Data, prefer repositories/`ElasticsearchOperations`/reactive operations; call the Java API Client directly only where lower-level APIs are required. Test mappings, query semantics, partial bulk failures, timeouts, security, and search visibility against the target server; roll out via canary before removing legacy dependencies. Never treat a clean compile or successful client initialization as a completed migration.

## References

- [Elasticsearch – Java API Client](https://www.elastic.co/docs/reference/elasticsearch/clients/java)
- [Elasticsearch – Migrating from the High Level REST Client](https://www.elastic.co/guide/en/elasticsearch/client/java-api-client/current/migrate-hlrc.html)
- [Elasticsearch – Low Level REST Client](https://www.elastic.co/guide/en/elasticsearch/client/java-rest/current/java-rest-low.html)
- [Elasticsearch – TransportClient removal/deprecation notes](https://www.elastic.co/guide/en/elasticsearch/client/java-api/current/transport-client.html)
- [Spring Data Elasticsearch – Reference](https://docs.spring.io/spring-data/elasticsearch/reference/)
- [Spring Data Elasticsearch – Client configuration](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/clients.html)
- [Spring Data Elasticsearch – ElasticsearchOperations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Boot – Elasticsearch](https://docs.spring.io/spring-boot/reference/data/nosql.html#data.nosql.elasticsearch)
