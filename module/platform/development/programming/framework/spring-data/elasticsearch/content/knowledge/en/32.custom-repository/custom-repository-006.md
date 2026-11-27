# Using the Client Directly for APIs Operations Does Not Provide

Spring Data Elasticsearch offers high-level abstractions such as ElasticsearchOperations, ElasticsearchTemplate, and ElasticsearchRepository. They cover most day-to-day operations: saving and reading entities, searching with Query DSL, pagination, aggregations, index management, scripts, and several specialized APIs.

However, Elasticsearch exposes many more endpoints than Spring Data's abstractions cover. When an application needs an API without a corresponding method in Operations, you can call the Elasticsearch Java API Client directly. This lets you use the strongly typed request and response models provided by Elasticsearch while reusing the client, transport, authentication, and connections already configured by Spring.

There are three common integration approaches:

- Use ElasticsearchTemplate.execute(...) to run a callback with ElasticsearchClient and benefit from Spring Data exception translation.
- Inject ElasticsearchClient directly when you need a standalone gateway or an API that does not belong in a repository.
- In reactive applications, use ReactiveElasticsearchTemplate.execute(...) with ReactiveElasticsearchClient to preserve the Publisher flow.

This article uses the Term Vectors API as an example. It is an API for retrieving tokens, term frequencies, positions, and offsets in a document; it is not a standard CRUD/search operation exposed directly by ElasticsearchOperations.

## 1. Roles of ElasticsearchOperations and Repositories

Spring Data Elasticsearch groups operations into focused abstractions:

| Abstraction | Responsibility |
| --- | --- |
| DocumentOperations | Saving, updating, retrieving, and deleting documents. |
| SearchOperations | Searching, counting, pagination, reading SearchHit, and aggregation results. |
| IndexOperations | Creating/deleting indexes, mappings, aliases, and supported index settings. |
| ElasticsearchOperations | Combines document and search operations while providing mapping/conversion. |
| ElasticsearchRepository | Spring Data-based CRUD and query method repository. |

ElasticsearchTemplate is the default implementation of ElasticsearchOperations in the current client stack. Underneath, it uses the Elasticsearch Java API Client and adds entity mapping, conversion, callbacks, resource management, and exception translation.

For complex queries that still belong to the Search API, check NativeQuery first. NativeQuery lets you use query builders and aggregation builders from the Elasticsearch Java API Client. Do not drop down to direct client calls solely because the Criteria API cannot express a query.

Only use the client directly when an endpoint or request option is not exposed by Operations/NativeQuery, or when you need a specialized response that existing abstractions do not model.

## 2. When Do You Need to Call the Elasticsearch Java API Client?

Several scenarios may call for the lower-level API:

- Retrieving term vectors for a document.
- Calling specialized cluster, node, or snapshot endpoints.
- Working with a newer Elasticsearch API that your Spring Data version does not yet abstract.
- Accessing specialized request/response fields not modeled by SearchHit or SearchHits.
- Invoking administrative or operational endpoints outside the repository CRUD/search flow.

Selection guide:

| Requirement | Preferred approach |
| --- | --- |
| Saving, getting, updating, deleting entities | ElasticsearchOperations or Repository. |
| Query DSL, filters, sorting, pagination | Query/NativeQuery via Operations. |
| Aggregations | NativeQuery and Operations. |
| Stored scripts or supported script updates | ScriptOperations/UpdateQuery first. |
| Supported index and mapping management | IndexOperations. |
| Elasticsearch API not available in Operations | Direct ElasticsearchClient. |
| Keeping non-blocking behavior in reactive apps | ReactiveElasticsearchClient via ReactiveElasticsearchTemplate. |

For example, searching products by name with a match query is already supported via NativeQuery. But if you need to inspect term vectors for the description field of a document, you can invoke the Term Vectors API directly.

Do not build a custom repository just to wrap methods that ElasticsearchOperations already provides. Doing so adds an extra forwarding layer without introducing new capabilities.

## 3. Architecture When Using the Client Directly

In the current imperative configuration, Spring Data Elasticsearch uses the Elasticsearch Java API Client and Rest5Client. Standard configuration creates these beans:

~~~text
Spring Boot or ElasticsearchConfiguration
              |
              v
       ClientConfiguration
              |
              v
          Rest5Client
              |
              v
    ElasticsearchTransport
              |
              v
       ElasticsearchClient
          /          \
         v            v
ElasticsearchTemplate  Custom repository fragment
         |                        |
         v                        v
ElasticsearchOperations     APIs not in Operations
         |
         v
Spring Data Repository
~~~

The key point is that custom fragments should reuse the Spring-managed ElasticsearchClient. Never instantiate a new Rest5Client or ElasticsearchClient inside each repository, as that creates extra connection pools, transports, TLS settings, and lifecycles to manage.

Spring Boot can auto-configure ElasticsearchClient when dependencies and properties are in place. When using Java configuration, ElasticsearchConfiguration provides the ElasticsearchClient bean from the transport. In both cases, components can inject the client directly.

## 4. Two Ways to Access ElasticsearchClient

### 4.1. Using ElasticsearchTemplate.execute(...)

ElasticsearchTemplate provides an execute method that takes a callback. The callback receives ElasticsearchClient to call APIs directly, and the template performs exception translation for errors raised inside the callback.

Example:

~~~java
import co.elastic.clients.elasticsearch.core.TermvectorsResponse;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchTemplate;
import org.springframework.stereotype.Component;

@Component
public class ProductTermVectorGateway {

    private final ElasticsearchTemplate template;

    public ProductTermVectorGateway(ElasticsearchTemplate template) {
        this.template = template;
    }

    public TermvectorsResponse getDescriptionTerms(String id) {
        return template.execute(client -> client.termvectors(t -> t
                .index("products")
                .id(id)
                .fields("description")
                .positions(true)
                .offsets(true)
        ));
    }
}
~~~

In this example:

- ElasticsearchTemplate is injected from the Spring context.
- execute opens a callback on the configured ElasticsearchClient.
- client.termvectors(...) calls the Term Vectors API.
- The result is a TermvectorsResponse generated by the Elasticsearch Java API Client.
- Exceptions are translated by the template using Spring Data's exception hierarchy.

This is a suitable option when a custom repository needs to call a lower-level API while preserving Spring Data's error-handling behavior.

Note: execute is a method on the ElasticsearchTemplate implementation, not declared on the ElasticsearchOperations interface. If you need execute, inject the concrete ElasticsearchTemplate or inject ElasticsearchClient directly; do not assume every ElasticsearchOperations implementation exposes this method.

### 4.2. Injecting ElasticsearchClient Directly

You can also inject the ElasticsearchClient bean:

~~~java
import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch.core.TermvectorsResponse;
import org.springframework.stereotype.Component;

@Component
public class ProductTermVectorClient {

    private final ElasticsearchClient client;

    public ProductTermVectorClient(ElasticsearchClient client) {
        this.client = client;
    }

    public TermvectorsResponse getDescriptionTerms(String id)
            throws java.io.IOException {

        return client.termvectors(t -> t
                .index("products")
                .id(id)
                .fields("description")
                .positions(true)
                .offsets(true)
        );
    }
}
~~~

This approach works well when building a gateway independent of ElasticsearchTemplate or when calling multiple Java Client APIs in the same component.

Key differences:

| Criterion | Template execute | Inject ElasticsearchClient |
| --- | --- | --- |
| Client | Uses the client held by the template. | Uses the Spring-managed ElasticsearchClient bean. |
| Exception translation | Includes template exception translation. | Receives raw Java API Client exceptions. |
| Spring Data entity mapping | Does not automatically map low-level API responses to entities. | Does not automatically map responses to entities. |
| Coupling | Depends on ElasticsearchTemplate implementation. | Depends on Elasticsearch Java API Client. |
| Best fit | Custom repository fragments integrating with Spring Data. | Dedicated gateways/services calling multiple endpoints. |

Whichever option you choose, never instantiate a new client inside a method. Always reuse the singleton bean configured with the application's endpoints, TLS, authentication, and timeouts.

## 5. Integrating via a Custom Repository Fragment

Spring Data recommends extending repositories with a fragment interface and implementation. Each fragment adds a distinct group of capabilities to an existing repository.

For example, suppose you need a method to retrieve term vectors for a product's description.

### 5.1. Declaring the Fragment Interface

~~~java
import co.elastic.clients.elasticsearch.core.TermvectorsResponse;

public interface ProductTermVectorRepository {

    TermvectorsResponse getDescriptionTerms(String productId);
}
~~~

The interface only describes the business-facing capability callers need. It does not need to extend ElasticsearchRepository or ElasticsearchOperations.

### 5.2. Composing the Fragment into the Repository

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                ProductTermVectorRepository {
}
~~~

ProductRepository includes both CRUD/query methods from ElasticsearchRepository and the added getDescriptionTerms(...) method.

### 5.3. Writing the Implementation

The default implementation name is formed from the fragment interface name plus the Impl suffix:

~~~java
import co.elastic.clients.elasticsearch.core.TermvectorsResponse;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchTemplate;
import org.springframework.stereotype.Component;

@Component
public class ProductTermVectorRepositoryImpl
        implements ProductTermVectorRepository {

    private final ElasticsearchTemplate template;

    public ProductTermVectorRepositoryImpl(
            ElasticsearchTemplate template) {
        this.template = template;
    }

    @Override
    public TermvectorsResponse getDescriptionTerms(String productId) {
        return template.execute(client -> client.termvectors(t -> t
                .index("products")
                .id(productId)
                .fields("description")
                .positions(true)
                .offsets(true)
                .termStatistics(true)
        ));
    }
}
~~~

Spring Data composes the fragment implementation into the repository proxy. When a service calls productRepository.getDescriptionTerms(...), the call routes to the fragment implementation.

The implementation must reside within the package scan scope discoverable by repository infrastructure, unless the fragment is configured manually. If you change the postfix via repository configuration, the implementation class name must match the new postfix.

### 5.4. Using the Repository

~~~java
@Service
public class ProductAnalysisService {

    private final ProductRepository productRepository;

    public ProductAnalysisService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    public TermvectorsResponse analyzeDescription(String productId) {
        return productRepository.getDescriptionTerms(productId);
    }
}
~~~

The service depends only on the repository contract. It does not need to know about callbacks, ElasticsearchClient, or how termvectors requests are built.

## 6. Example API Missing from Operations: Term Vectors

The Term Vectors API returns token information for a document. Depending on the request, the response can include:

- Occurrence frequency of each term in a field.
- Token positions within the text.
- Start and end character offsets of each token.
- Payloads if supported by mapping and request options.
- Term statistics and field statistics.

Example REST request:

~~~http
GET /products/_termvectors/P-100
Content-Type: application/json

{
  "fields": ["description"],
  "positions": true,
  "offsets": true,
  "term_statistics": true,
  "field_statistics": false
}
~~~

Corresponding Java API Client request:

~~~java
TermvectorsResponse response = client.termvectors(t -> t
        .index("products")
        .id("P-100")
        .fields("description")
        .positions(true)
        .offsets(true)
        .termStatistics(true)
        .fieldStatistics(false)
);
~~~

The response is represented by TermvectorsResponse. You can check whether the document exists and read the per-field term vectors map:

~~~java
if (!response.found()) {
    // Document does not exist.
    return;
}

var descriptionVector = response.termVectors().get("description");

if (descriptionVector == null) {
    // No term vector for the requested field.
    return;
}

var terms = descriptionVector.terms();
~~~

Each entry in the terms map represents a term and its metadata. Your application can read frequencies, positions, or offsets according to the Term and TermVector structures in your Elasticsearch Java Client version.

### 6.1. Mapping and Term Vectors

Elasticsearch can store term vectors inside the index or compute them on the fly from indexed data when possible. If a use case frequently needs term positions and offsets, you can configure term_vector in the mapping:

~~~json
{
  "mappings": {
    "properties": {
      "description": {
        "type": "text",
        "term_vector": "with_positions_offsets"
      }
    }
  }
}
~~~

Common term vector options:

| Value | Information stored |
| --- | --- |
| no | Does not store term vectors. This is the default. |
| yes | Stores terms and frequencies. |
| with_positions | Adds token positions. |
| with_offsets | Adds character offsets. |
| with_positions_offsets | Stores both positions and offsets. |
| with_positions_offsets_payloads | Stores positions, offsets, and payloads. |

Storing term vectors increases index size and can increase write overhead. Enable it only when the application genuinely needs that information and you have measured the impact on representative data.

### 6.2. Meaning of Statistics

Term statistics and field statistics are not always exact cluster-wide figures. The Term Vectors API retrieves statistics from the shard holding the document; returned statistics have limitations and should be interpreted within the API's intended scope.

If you only need document-level frequencies, positions, or offsets, do not request unnecessary statistics. Keeping the payload minimal makes the request intent clearer.

### 6.3. Fetching Term Vectors for Multiple Documents

The Elasticsearch Java API Client also offers mtermvectors to retrieve term vectors for multiple documents in one request:

~~~java
var response = client.mtermvectors(m -> m
        .index("products")
        .ids("P-100", "P-101", "P-102")
        .fields("description")
        .positions(true)
        .offsets(true)
);
~~~

The batch API is useful when analyzing a set of documents. Limit the number of IDs per request and keep response sizes bounded. Never send an unbounded list just because the endpoint accepts multiple documents.

## 7. Using the Client Directly in a Custom Service Instead of a Repository

Not every Elasticsearch API belongs inside a repository. Repositories typically represent data access scoped to an aggregate or domain type. Cluster administration APIs—such as snapshots, node stats, cluster settings, or index lifecycle management—fit better in a dedicated operational service.

Example of a snapshot administration gateway:

~~~java
import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch.snapshot.CreateSnapshotResponse;
import org.springframework.stereotype.Component;

@Component
public class SnapshotGateway {

    private final ElasticsearchClient client;

    public SnapshotGateway(ElasticsearchClient client) {
        this.client = client;
    }

    public CreateSnapshotResponse createSnapshot(
            String repository,
            String snapshot,
            String index) throws java.io.IOException {

        return client.snapshot().create(s -> s
                .repository(repository)
                .snapshot(snapshot)
                .indices(index)
                .includeGlobalState(false)
                .waitForCompletion(false)
        );
    }
}
~~~

This belongs at the service level because taking snapshots is a cluster administration task, not a behavior of ProductRepository.

Grant appropriate cluster privileges to the identity executing snapshots. Never grant cluster-admin privileges to a business service whose only job is product CRUD.

## 8. Direct Client Calls Do Not Automatically Apply Spring Data Mapping

When calling ElasticsearchTemplate.save(entity), Spring Data uses mapping metadata to convert the entity into a document. That process may consider:

- @Document and index name.
- @Id and @Field.
- Field naming strategies.
- Custom conversions.
- Type hints.
- Entity callbacks.
- Routing and refresh policies configured on the template.

When calling client.index(...) or client.get(...), the Elasticsearch Java API Client uses the transport's serializer/JsonpMapper and the target type specified by the caller. It does not run the full Spring Data entity mapping lifecycle.

Direct client example:

~~~java
var response = client.get(g -> g
        .index("products")
        .id("P-100"),
        Product.class
);
~~~

Here the Java API Client deserializes the source into Product via JsonpMapper. Do not assume every Spring Data annotation on Product is honored the same way as when reading through ElasticsearchOperations.

If you need Spring Data mapping, use Operations to read entities and call the client directly only for the supplemental API. If the response is an Elasticsearch-specific model, keep it inside the gateway/adapter layer and convert it into business DTOs as needed.

## 9. Preserving Existing Client Configuration

When calling the client directly, reuse the Spring-managed bean. Connection configuration is typically provided by ElasticsearchConfiguration or Spring Boot auto-configuration.

Java configuration example:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchConfiguration;

@Configuration
public class ElasticsearchConfig extends ElasticsearchConfiguration {

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
                .connectedTo("localhost:9200")
                .build();
    }
}
~~~

This configuration creates the transport and ElasticsearchClient. Components can then inject ElasticsearchClient or ElasticsearchTemplate.

If the application uses Spring Boot, Boot can configure the client from spring.elasticsearch properties. Do not add a second client just to call another API.

Settings that must stay consistent include:

- Endpoints and node list.
- TLS/certificate validation.
- Basic auth or API keys.
- Default headers.
- Connect/socket timeouts.
- Proxies and path prefixes.
- TransportOptions and JsonpMapper.
- Observation/tracing if configured.

Do not instantiate a new Rest5Client inside a repository. Rest5Client is the low-level HTTP transport; most direct API use cases should use the strongly typed ElasticsearchClient.

## 10. Reactive Custom Repositories

If the application uses the reactive stack, do not call the blocking ElasticsearchClient from WebFlux request paths. Use ReactiveElasticsearchClient and ReactiveElasticsearchTemplate.

ReactiveElasticsearchTemplate provides an execute callback to call the reactive client directly and return a Publisher. Example:

~~~java
import co.elastic.clients.elasticsearch.core.TermvectorsResponse;
import org.springframework.data.elasticsearch.client.elc.ReactiveElasticsearchTemplate;
import reactor.core.publisher.Mono;

public class ReactiveProductTermVectorRepositoryImpl {

    private final ReactiveElasticsearchTemplate template;

    public ReactiveProductTermVectorRepositoryImpl(
            ReactiveElasticsearchTemplate template) {
        this.template = template;
    }

    public Mono<TermvectorsResponse> getDescriptionTerms(String productId) {
        return Mono.from(template.execute(client ->
                client.termvectors(t -> t
                        .index("products")
                        .id(productId)
                        .fields("description")
                        .positions(true)
                        .offsets(true)
                )
        ));
    }
}
~~~

The reactive callback returns a Publisher; Mono.from(...) adapts a single-result Publisher into a Mono. The API call executes only when the publisher is subscribed to.

Do not call block() or subscribe() inside a reactive custom repository. Return Mono/Flux to the caller so the framework manages subscription, cancellation, and error signals.

## 11. Handling Errors from the Direct Client

The Elasticsearch Java API Client can throw:

- IOException for transport or response-reading failures.
- ElasticsearchException when the cluster returns an API error.
- Mapping/serialization errors during JSON conversion.
- Authentication or authorization errors.
- Errors caused by invalid requests or version-incompatible APIs.

When using ElasticsearchTemplate.execute, the template performs exception translation to convert certain errors into Spring Data's exception hierarchy.

When injecting ElasticsearchClient directly, callers must handle exceptions according to the API and application architecture.

Example:

~~~java
public TermvectorsResponse getTerms(String id) {
    try {
        return client.termvectors(t -> t
                .index("products")
                .id(id)
                .fields("description")
        );
    } catch (IOException ex) {
        throw new ProductSearchInfrastructureException(
                "Could not read product term vectors", ex
        );
    }
}
~~~

In real code, distinguish connection errors, 404 errors, 401/403 errors, 400 request errors, and 5xx server errors. Never catch a generic Exception and return an empty list, as that hides configuration or business failures.

Do not log entire requests or responses if they contain sensitive data. Log index names, endpoints, request IDs, error types, and script/query IDs in accordance with observability policies.

## 12. Authorization and Security

Direct client calls do not bypass Elasticsearch security. Requests still execute under the identity and credentials configured on the transport.

Examples:

| API | Typical required privileges |
| --- | --- |
| Term Vectors | Read privilege on the corresponding document/index. |
| Snapshot create | Cluster privilege for creating snapshots and required privileges on the snapshot repository. |
| Cluster/node monitoring | Cluster monitor privilege or privileges matching the endpoint. |
| Index metadata | Index/cluster privileges depending on the specific API. |

Grant services only the privileges they need. If a service only reads term vectors from products, do not grant snapshot-admin privileges or cluster-settings permissions.

For administrative APIs, separate operational gateways/services and credentials from business services. Verify security privileges per endpoint and Elasticsearch version, since required permissions can vary across APIs.

## 13. Version Constraints and Compatibility

The Elasticsearch Java API Client generates request/response models according to its client version. A method or field may not exist in the client managed by Spring Data even if a newer Elasticsearch cluster already supports that endpoint.

When you need a new API:

1. Check the Elasticsearch cluster version.
2. Check the Spring Data Elasticsearch version.
3. Check the Elasticsearch Java API Client version managed by your dependencies.
4. Confirm the endpoint and request fields exist in that client.
5. Only upgrade the client independently if the compatibility matrix allows it.
6. Test serialization, responses, and errors against a compatible cluster.

Do not force an arbitrary Elasticsearch Java Client version override. Spring Data Elasticsearch relies on specific client types; upgrading the client in isolation can introduce binary or API incompatibilities.

If an endpoint is not yet available in your current Java API Client, consider:
- Waiting for a client release that supports it.
- Upgrading Spring Data and the client together per the compatibility matrix.
- Using the low-level HTTP client configured in Spring to invoke the REST endpoint, while taking full responsibility for request serialization, response parsing, error handling, and security checks.

Do not fall back to the legacy RestHighLevelClient in new code. RestHighLevelClient has been removed in modern Elasticsearch generations.

## 14. Testing Custom Repositories

Custom fragments can be tested by mocking ElasticsearchTemplate or ElasticsearchClient, depending on how they are implemented.

For implementations using template.execute, verify that:

- The fragment calls the expected API and index.
- The document ID is passed accurately.
- The field list and term vector options match requirements.
- The response is returned to the caller.
- Errors from the callback are propagated or translated per contract.
- No new client is created inside each method.

Service/fragment-level test example:

~~~java
@ExtendWith(MockitoExtension.class)
class ProductTermVectorRepositoryImplTest {

    @Mock
    ElasticsearchTemplate template;

    @Test
    void delegatesTermVectorRequestToTemplate() {
        // Stub template.execute(...) and assert the result.
        // An Answer can be used if inspecting the callback with a mock client.
    }
}
~~~

Because execute accepts a callback, tests need to invoke the callback with a mock client or use an integration test to verify the real request. Do not merely verify that template.execute was called without checking key request contents.

For integration tests:

- Use an Elasticsearch version compatible with your client.
- Create the required index and mapping.
- Index documents containing the field whose term vectors are queried.
- Invoke the repository fragment.
- Verify found, field, terms, frequencies, positions, and offsets.
- Verify non-existent document handling.
- Verify missing-privilege error handling.
- Verify cases where the field lacks term vectors or has no value.

Testcontainers can spin up an ephemeral cluster. Pick an image version matching your project's Spring Data Elasticsearch and Java API Client versions.

## 15. Common Pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Cannot inject ElasticsearchClient | Missing auto-configuration or Java client setup. | Check dependencies, beans, and ElasticsearchConfiguration. |
| Cannot call execute on ElasticsearchOperations | execute is not part of the ElasticsearchOperations interface. | Inject ElasticsearchTemplate or ElasticsearchClient. |
| Fragment implementation not found | Wrong suffix, package, or repository scan scope. | Name it FragmentNameImpl and place it inside the scan scope. |
| Direct client ignores @Field mappings | Java API Client uses JsonpMapper, bypassing Spring Data converters. | Use Operations for entity mapping or convert responses manually. |
| 401/403 errors | Insufficient credentials or privileges. | Verify identity, index privileges, and cluster privileges. |
| IOException | Connection, timeout, or transport failure. | Check endpoints, TLS, timeouts, and network connectivity. |
| API missing from client | Java API Client is older than the cluster endpoint. | Check compatibility and upgrade per the matrix. |
| Term vectors return empty fields | Field is not indexed or lacks suitable data. | Inspect mapping and document source. |
| Term vectors consume excessive resources | Computing term vectors on the fly or requesting excessive metadata. | Request only required fields; consider storing term_vector for repeated use cases. |
| Reactive endpoint blocks | Calling synchronous ElasticsearchClient in WebFlux. | Use ReactiveElasticsearchTemplate/ReactiveElasticsearchClient. |
| Multiple connection pools created | Instantiating clients inside fragments/services. | Inject the Spring-managed singleton bean. |

## 16. Implementation Selection Workflow

When adding a new Elasticsearch capability to a repository:

1. Check whether ElasticsearchOperations, IndexOperations, ScriptOperations, and SearchOperations already have a matching method.
2. If it is a query, check CriteriaQuery, StringQuery, or NativeQuery first.
3. If no abstraction exists for the API, check whether the Elasticsearch Java API Client supports the endpoint.
4. Create a fragment interface with method names phrased in business language.
5. Create an implementation with the Impl suffix.
6. Inject the Spring-configured ElasticsearchTemplate or ElasticsearchClient.
7. Invoke the API inside a callback or a dedicated gateway.
8. Map low-level responses to DTOs if you want to avoid leaking client models outward.
9. Handle exceptions, security, and timeouts according to the service contract.
10. Test requests and responses against a compatible Elasticsearch version.
11. Monitor latency, errors, and resource consumption.
12. When Spring Data adds an official abstraction, evaluate migrating back to reduce custom-maintained code.

## 17. References

- [Spring Data Elasticsearch — Custom Repository Implementations](https://docs.spring.io/spring-data/elasticsearch/reference/repositories/custom-implementations.html)
- [Spring Data Elasticsearch — Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch — Elasticsearch Clients](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/clients.html)
- [Spring Data Elasticsearch — ElasticsearchTemplate API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/ElasticsearchTemplate.html)
- [Spring Data Elasticsearch — ElasticsearchTemplate.ClientCallback API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/ElasticsearchTemplate.ClientCallback.html)
- [Elasticsearch — Get term vector information](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-termvectors)
- [Elasticsearch — Java API Client](https://www.elastic.co/docs/reference/elasticsearch/clients/java)
- [Elasticsearch — Create a snapshot](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-snapshot-create)

When Operations does not expose an endpoint, a custom repository fragment can call the Elasticsearch Java API Client directly. ElasticsearchTemplate.execute is well suited when you want the shared client and Spring Data's exception translation; injecting ElasticsearchClient directly fits specialized gateways. Keep mapping boundaries clear, never instantiate separate clients, use reactive clients in reactive applications, and verify version compatibility along with endpoint-specific security privileges.
