# Configuring ReactiveElasticsearchConfiguration and the Reactive Client

Spring Data Elasticsearch provides a reactive client so applications can send requests to Elasticsearch using Project Reactor. Instead of returning results synchronously, reactive APIs typically return a Mono or Flux. As a result, services can compose multiple asynchronous operations without blocking threads while waiting for each response.

In current Spring Data Elasticsearch, the primary configuration class is ReactiveElasticsearchConfiguration in the org.springframework.data.elasticsearch.client.elc package. This class creates the beans required for connectivity, including the low-level Rest5Client, ElasticsearchTransport, ReactiveElasticsearchClient, and ReactiveElasticsearchOperations. ReactiveElasticsearchTemplate is the default implementation of operations.

This article focuses on how to configure the client, choose connection options, use the reactive template and repositories, integrate with Spring Boot, and keep processing non-blocking from the HTTP endpoint down to Elasticsearch.

## 1. What Is Reactive Elasticsearch?

Reactive Elasticsearch allows applications to work with Elasticsearch using Reactor publishers:

- Mono<T>: emits at most one value T, or completes without a value.
- Flux<T>: emits zero or more values T.
- ReactiveElasticsearchClient: low-level client providing reactive Elasticsearch operations.
- ReactiveElasticsearchOperations: high-level abstraction for saving, reading, searching, deleting, and managing documents.
- ReactiveElasticsearchTemplate: default implementation of ReactiveElasticsearchOperations.
- Reactive Elasticsearch Repository: repository returning Mono and Flux instead of synchronous result types.

A typical flow:

~~~text
WebFlux Controller
       |
       v
Service returning Mono / Flux
       |
       v
ReactiveElasticsearchOperations
       |
       v
ReactiveElasticsearchTemplate
       |
       v
ReactiveElasticsearchClient
       |
       v
ElasticsearchTransport
       |
       v
Rest5Client
       |
       v
Elasticsearch cluster
~~~

Applications can use ReactiveElasticsearchOperations or repositories for most business logic. The low-level ReactiveElasticsearchClient is useful when you need access to a specific API not yet covered by the higher-level abstraction.

Reactive does not mean every piece of application code automatically runs on a separate thread. The primary goal is avoiding holding threads while waiting on I/O. When used properly, threads can perform other work while waiting for Elasticsearch to respond.

## 2. ReactiveElasticsearchConfiguration

The ReactiveElasticsearchConfiguration class is the base configuration for creating an Elasticsearch connection in the reactive stack.

Main import:

~~~java
import org.springframework.data.elasticsearch.client.elc.ReactiveElasticsearchConfiguration;
~~~

This class requires the application to provide a ClientConfiguration via the clientConfiguration() method. From that configuration, Spring Data creates the required beans:

| Bean | Role |
| --- | --- |
| ClientConfiguration | Cluster addresses, SSL, authentication, timeouts, headers, and HTTP options. |
| Rest5Client | Low-level HTTP client used by the Elasticsearch Java Client in the current stack. |
| ElasticsearchTransport | Connects the transport and JSON mapper with the low-level client. |
| JsonpMapper | JSON conversion for the Elasticsearch Java API Client. |
| ReactiveElasticsearchClient | Reactive client used by Spring Data to send requests. |
| ReactiveElasticsearchOperations | High-level API for document operations; default implementation is ReactiveElasticsearchTemplate. |

The operations/template bean is registered under the names reactiveElasticsearchOperations and reactiveElasticsearchTemplate. Reactive repositories use this operations bean underneath.

### 2.1. Minimal Configuration

Example connecting to a local Elasticsearch instance:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ReactiveElasticsearchConfiguration;
import org.springframework.data.elasticsearch.repository.config.EnableReactiveElasticsearchRepositories;

@Configuration
@EnableReactiveElasticsearchRepositories(
        basePackages = "com.example.catalog.repository"
)
public class ElasticsearchReactiveConfiguration
        extends ReactiveElasticsearchConfiguration {

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
                .connectedTo("localhost:9200")
                .build();
    }
}
~~~

Explanation:

- @Configuration registers this class as a Spring configuration.
- @EnableReactiveElasticsearchRepositories enables scanning for reactive repositories in the specified package.
- ReactiveElasticsearchConfiguration provides the client and template infrastructure.
- clientConfiguration() describes how to connect to the cluster.
- You do not need to manually create ReactiveElasticsearchClient or ReactiveElasticsearchTemplate when extending this base configuration class.

If repositories reside in the same package or subpackages of the configuration class, basePackages can be omitted. In large projects, declaring packages explicitly helps control the scan scope.

### 2.2. Do Not Confuse with AbstractReactiveElasticsearchConfiguration

Older examples may use AbstractReactiveElasticsearchConfiguration and ReactiveRestClients. Those APIs belong to the legacy reactive client generation.

In current Spring Data Elasticsearch, use ReactiveElasticsearchConfiguration in the client.elc package. With Spring Data 6.x, the legacy RestClient has been deprecated; current configuration uses Rest5Client and Elasticsearch Java Client transport.

| API | Generation | Notes |
| --- | --- | --- |
| ReactiveElasticsearchConfiguration | Current ELC client | Base configuration class for the reactive client. |
| ReactiveElasticsearchLegacyRestClientConfiguration | Legacy client | Used when maintaining the older low-level RestClient is required. |
| AbstractReactiveElasticsearchConfiguration | Legacy reactive API | Should not be copied verbatim into projects using the current client. |
| ReactiveRestClients | Legacy API | Do not confuse with the current ReactiveElasticsearchClient. |

When upgrading Spring Data Elasticsearch, verify the package imports and the type of low-level client being configured. Do not mix legacy client classes with the Elasticsearch Java API Client.

## 3. ClientConfiguration and Connection Options

ClientConfiguration describes the connection parameters used by ReactiveElasticsearchConfiguration to build the client.

Common options:

| Option | Purpose |
| --- | --- |
| connectedTo | One or more Elasticsearch node addresses. |
| usingSsl | Enables HTTPS/TLS. |
| withBasicAuth | Configures HTTP Basic Authentication. |
| withConnectTimeout | Limits the time to establish a connection. |
| withSocketTimeout | Limits the time waiting for a response on the socket. |
| withProxy | Configures an HTTP proxy. |
| withPathPrefix | Adds a path prefix when the cluster sits behind a reverse proxy. |
| withDefaultHeaders | Sends default headers on every request. |
| withHeaders | Supplies dynamic headers before each request. |
| withClientConfigurer | Customizes the underlying low-level client or HTTP client. |

### 3.1. Connecting to Multiple Nodes

You can declare multiple addresses:

~~~java
@Override
public ClientConfiguration clientConfiguration() {
    return ClientConfiguration.builder()
            .connectedTo(
                    "es-node-1.example.net:9200",
                    "es-node-2.example.net:9200",
                    "es-node-3.example.net:9200"
            )
            .build();
}
~~~

The client uses the configured addresses to connect to the cluster. In production deployments, use the endpoints provided by your Elasticsearch infrastructure or load balancer.

Do not specify a full HTTP URL if the builder expects host and port. When SSL is enabled, configure the scheme via usingSsl() or the corresponding SSL overload.

### 3.2. Enabling SSL/TLS and Basic Authentication

Example configuring HTTPS:

~~~java
import java.time.Duration;

@Override
public ClientConfiguration clientConfiguration() {
    return ClientConfiguration.builder()
            .connectedTo("search.example.net:9200")
            .usingSsl()
            .withBasicAuth(username, password)
            .withConnectTimeout(Duration.ofSeconds(5))
            .withSocketTimeout(Duration.ofSeconds(10))
            .build();
}
~~~

username and password should be loaded from a secret store, environment variables, or the application's configuration management system. Do not commit credentials to source code or shared configuration files.

usingSsl() enables TLS. If the cluster uses internal certificates or a custom certificate authority, configure an SSLContext or certificate fingerprint via the overload supported by the client version. Never disable certificate verification just to work around connection errors.

### 3.3. Timeouts

Two timeouts should typically be distinguished:

- Connect timeout: maximum time to establish a connection to a node.
- Socket timeout: maximum time waiting for a response on an established connection.

Example:

~~~java
ClientConfiguration configuration = ClientConfiguration.builder()
        .connectedTo("localhost:9200")
        .withConnectTimeout(Duration.ofSeconds(3))
        .withSocketTimeout(Duration.ofSeconds(8))
        .build();
~~~

Appropriate values depend on latency, request size, shard count, and query execution time. Too short a timeout can fail valid requests; too long a timeout can tie up resources when the cluster is degraded.

Client timeouts should also be aligned with the timeouts of the HTTP server, gateway, and upstream services calling the application.

### 3.4. Proxy and Path Prefix

When Elasticsearch sits behind a reverse proxy, a proxy or path prefix may be needed:

~~~java
ClientConfiguration configuration = ClientConfiguration.builder()
        .connectedTo("search-gateway.example.net:443")
        .usingSsl()
        .withProxy("proxy.example.net:8888")
        .withPathPrefix("elasticsearch")
        .build();
~~~

Only use withProxy when the deployment network requires a proxy. Only use withPathPrefix when the reverse proxy actually forwards requests under that prefix. If an incorrect prefix is configured, the client may receive 404 even when host and port are correct.

### 3.5. Default Headers and Dynamic Headers

You can add headers to every request:

~~~java
import org.springframework.data.elasticsearch.support.HttpHeaders;

HttpHeaders headers = new HttpHeaders();
headers.add("X-Application", "catalog-service");

ClientConfiguration configuration = ClientConfiguration.builder()
        .connectedTo("localhost:9200")
        .withDefaultHeaders(headers)
        .build();
~~~

If you need a token that changes over time, you can use a supplier:

~~~java
ClientConfiguration configuration = ClientConfiguration.builder()
        .connectedTo("search.example.net:9200")
        .withHeaders(() -> {
            HttpHeaders headers = new HttpHeaders();
            headers.add("Authorization", currentAuthorizationHeader());
            return headers;
        })
        .build();
~~~

In a reactive setup, the header supplier must not perform blocking operations. Do not call a token-issuing service synchronously inside the supplier. If the token needs asynchronous refresh, design a token-providing mechanism aligned with the application lifecycle and client API.

Do not log tokens or credentials in request logs.

### 3.6. Advanced Client Customization

When standard options are insufficient, ClientConfiguration supports withClientConfigurer to customize lower-level components such as Rest5Client or the underlying HTTP async client.

Example callback configuration pattern:

~~~java
import static org.springframework.data.elasticsearch.client.elc.ElasticsearchClients.*;

ClientConfiguration configuration = ClientConfiguration.builder()
        .connectedTo("localhost:9200")
        .withClientConfigurer(Rest5Clients.ElasticsearchRest5ClientConfigurationCallback.from(
                restClientBuilder -> {
                    // Customize low-level Rest5Client according to deployment needs.
                    return restClientBuilder;
                }))
        .build();
~~~

The specific callback type depends on the component being customized. Rest5Client has separate callbacks for the client builder, HTTP async client, connection manager, and request configuration.

Only customize the low-level client when truly necessary. Tuning connection pools, retries, or TLS affects all requests and should be tested under representative load.

## 4. Customizing transportOptions and JsonpMapper

ReactiveElasticsearchConfiguration allows overriding hooks to customize the transport.

### 4.1. transportOptions()

transportOptions() supplies options attached to requests sent through the transport. This is an extension point when default request-level configuration is needed.

Override skeleton example:

~~~java
import co.elastic.clients.transport.TransportOptions;

@Override
public TransportOptions transportOptions() {
    return super.transportOptions();
}
~~~

The example above preserves defaults. When you need to customize headers or request options at the transport level, use the builder and option types matching your Elasticsearch Java Client version.

Do not use transportOptions as a replacement for security roles or index permissions. Client-side options do not grant additional permissions to a user on the cluster.

### 4.2. jsonpMapper()

JsonpMapper is responsible for JSON conversion for the Elasticsearch Java API Client. ReactiveElasticsearchConfiguration provides a default mapper bean and uses it when creating ElasticsearchTransport.

Only override jsonpMapper() when special serialization/deserialization rules are needed, such as custom JSON handling or integrating an application-wide mapper configuration.

When customizing the mapper, verify:

- Date and time data types.
- Enums and custom value objects.
- Property names.
- Null handling.
- Compatibility with Elasticsearch responses.
- Whether Spring Data entity mapping still works properly.

Do not create arbitrary per-service mappers if the entire application expects consistent conversion rules.

## 5. Created Beans and How to Inject Them

Once configuration is complete, Spring can inject the reactive beans:

~~~java
import org.springframework.data.elasticsearch.client.elc.ReactiveElasticsearchClient;
import org.springframework.data.elasticsearch.core.ReactiveElasticsearchOperations;

@Service
public class ProductSearchService {

    private final ReactiveElasticsearchOperations operations;
    private final ReactiveElasticsearchClient client;

    public ProductSearchService(
            ReactiveElasticsearchOperations operations,
            ReactiveElasticsearchClient client) {
        this.operations = operations;
        this.client = client;
    }
}
~~~

Role of each bean:

- ReactiveElasticsearchClient: low-level communication with Elasticsearch.
- ReactiveElasticsearchOperations: high-level abstraction providing entity mapping, query APIs, and exception translation.
- ReactiveElasticsearchTemplate: default implementation of operations.
- Rest5Client: low-level HTTP client used by the Elasticsearch Java Client.
- ElasticsearchTransport: bridges the HTTP client with the JSON mapper and API client.

In most business services, inject ReactiveElasticsearchOperations. Only inject ReactiveElasticsearchClient when you need a low-level API or feature not yet supported by operations.

Do not create a new client in every method or per request. The client should be a shared Spring-managed bean to reuse the connection pool and follow the application context lifecycle.

## 6. ReactiveElasticsearchOperations and ReactiveElasticsearchTemplate

ReactiveElasticsearchOperations is the high-level API for interacting with Elasticsearch in a reactive application. ReactiveElasticsearchTemplate is the default implementation.

Common operations:

| Operation | Common return type |
| --- | --- |
| save(entity) | Mono<T> |
| get(id, type) | Mono<T> |
| exists(id, index) | Mono<Boolean> |
| delete(id, index) | Mono<String> |
| search(query, type) | Flux<SearchHit<T>> |
| searchForHits(query, type) | Mono<ReactiveSearchHits<T>> |
| searchForPage(query, type) | Mono<SearchPage<T>> |
| count(query, type) | Mono<Long> |
| aggregate(query, type) | Flux<AggregationContainer<?>> |

Mono is used when the operation returns at most one result. Flux is used when multiple hits or multiple elements may be returned.

### 6.1. Saving a Document

Example entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private Double price;

    // Constructor, getters, and setters
}
~~~

Saving the entity with operations:

~~~java
Mono<Product> save(Product product) {
    return operations.save(product);
}
~~~

Calling save returns a Mono. The save is executed when the publisher is subscribed to by the framework or caller. Without a subscriber, the pipeline is not executed in the usual reactive manner.

### 6.2. Getting a Document by ID

~~~java
Mono<Product> findById(String id) {
    return operations.get(id, Product.class);
}
~~~

If no document is found, the Mono completes without emitting a value. You can use switchIfEmpty to handle the missing case:

~~~java
Mono<Product> findRequired(String id) {
    return operations.get(id, Product.class)
            .switchIfEmpty(Mono.error(
                    new IllegalArgumentException("Product not found: " + id)
            ));
}
~~~

In real applications, you can replace IllegalArgumentException with a domain exception and map it to HTTP 404 in controller advice.

### 6.3. Searching with the Query API

Example searching products by name:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.ReactiveElasticsearchOperations;
import reactor.core.publisher.Flux;

Flux<Product> searchByName(String text) {
    var query = NativeQuery.builder()
            .withQuery(q -> q.match(m -> m
                    .field("name")
                    .query(text)
            ))
            .build();

    return operations.search(query, Product.class)
            .map(SearchHit::getContent);
}
~~~

operations.search returns Flux<SearchHit<Product>>. Each SearchHit contains the entity along with metadata such as ID, score, and highlight details if configured on the query. map extracts the entity to return Flux<Product>.

If you need score, ID, or highlight metadata, keep SearchHit instead of only extracting getContent().

### 6.4. Retrieving Overall Search Metadata

When total hits or search metadata are needed, use searchForHits:

~~~java
Mono<ReactiveSearchHits<Product>> searchWithMetadata(Query query) {
    return operations.searchForHits(query, Product.class);
}
~~~

When a SearchPage structure is needed, you can use searchForPage:

~~~java
Mono<SearchPage<Product>> searchPage(Query query) {
    return operations.searchForPage(query, Product.class);
}
~~~

These APIs return metadata as a Mono because all metadata for a single search response is encapsulated in one result. Choose the API based on whether the caller wants to stream individual hits or needs response-level metadata.

### 6.5. Searching and Counting

~~~java
Mono<Long> countByCategory(String category) {
    Query query = NativeQuery.builder()
            .withQuery(q -> q.term(t -> t
                    .field("category")
                    .value(category)
            ))
            .build();

    return operations.count(query, Product.class);
}
~~~

Count returns Mono<Long>. There is no need to fetch all documents and call collectList().count() to count them. Using the count API lets Elasticsearch perform the count server-side.

### 6.6. Deleting a Document

~~~java
Mono<String> deleteById(String id) {
    return operations.delete(id, Product.class);
}
~~~

If the operation targets a specific index, you can use the overload accepting IndexCoordinates. When working with custom routing, ensure the routing resolver is properly configured so operations reach the correct shard.

## 7. Reactive Repositories

Spring Data Elasticsearch supports reactive repositories built on Project Reactor. Common base interfaces include:

- ReactiveRepository.
- ReactiveCrudRepository.
- ReactiveSortingRepository.

Repository example:

~~~java
import org.springframework.data.repository.reactive.ReactiveSortingRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ProductRepository
        extends ReactiveSortingRepository<Product, String> {

    Flux<Product> findByCategory(String category);

    Mono<Product> findFirstBySku(String sku);

    Flux<Product> findByCategoryOrderByPriceAsc(String category);
}
~~~

Common return types:

- Flux<Product>: multiple products or no products.
- Mono<Product>: at most one product.
- Mono<Long>: document count.
- Mono<Boolean>: existence check.

When a method can return multiple documents, do not declare Mono<Product> merely because the caller expects a single result. If multiple documents actually match, the framework may throw a result size error instead of silently picking one record.

### 7.1. Enabling Reactive Repositories

Use the annotation:

~~~java
@Configuration
@EnableReactiveElasticsearchRepositories(
        basePackages = "com.example.catalog.repository"
)
public class RepositoryConfiguration {
}
~~~

If this configuration resides with ReactiveElasticsearchConfiguration, the annotation can be placed on that subclass. Simply ensure reactive repositories are scanned and a suitable ReactiveElasticsearchOperations bean exists in the application context.

Do not use @EnableElasticsearchRepositories for reactive repositories. That annotation activates the imperative repository infrastructure.

### 7.2. Repository Methods with Publisher Inputs

A reactive repository can accept a Publisher as a parameter:

~~~java
Flux<Product> findByCategory(Publisher<String> category);
~~~

This allows chaining input data from another reactive source. When using publisher inputs, understand that the query only executes once the publisher is subscribed to and the input value is emitted.

## 8. Integrating with Spring WebFlux

The reactive client shines when all layers of the application preserve publishers instead of converting results to synchronous values.

Controller example:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/products")
public class ProductController {

    private final ProductRepository repository;

    public ProductController(ProductRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/category/{category}")
    public Flux<Product> findByCategory(
            @PathVariable String category) {
        return repository.findByCategory(category);
    }

    @GetMapping("/sku/{sku}")
    public Mono<Product> findBySku(@PathVariable String sku) {
        return repository.findFirstBySku(sku);
    }

    @PostMapping
    public Mono<Product> create(@RequestBody Product product) {
        return repository.save(product);
    }
}
~~~

Spring WebFlux subscribes to the publisher to process the request and write the response. The controller does not need to call subscribe() or block().

Request flow:

~~~text
HTTP request
     |
     v
WebFlux Controller
     |
     v
Mono / Flux from service or repository
     |
     v
Reactive Elasticsearch Operations
     |
     v
Elasticsearch
     |
     v
Result Mono / Flux
     |
     v
HTTP response
~~~

When a controller returns Mono or Flux, the framework can manage subscription, cancellation, and response writing according to the reactive contract.

## 9. Spring Boot Auto-Configuration

When using Spring Boot, you do not always need to write a custom subclass extending ReactiveElasticsearchConfiguration.

When Spring Data Elasticsearch and Reactor are on the classpath, Spring Boot can auto-configure ReactiveElasticsearchClient and ReactiveElasticsearchTemplate. Common starters:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-elasticsearch</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

The Spring Boot BOM manages compatible dependency versions. Do not independently upgrade the Elasticsearch Java Client or Rest5Client without checking the compatibility matrix.

### 9.1. Configuring via application.yml

Example:

~~~yaml
spring:
  elasticsearch:
    uris: https://search.example.net:9200
    username: ${ES_USERNAME_FROM_SECRET_STORE}
    password: ${ES_PASSWORD_FROM_SECRET_STORE}
    socket-timeout: 10s
~~~

The illustrative username and password values should be replaced with secrets supplied via environment variables or a secret manager. Never commit real passwords to the repository.

Spring Boot uses spring.elasticsearch properties to configure the REST client, transport, and ReactiveElasticsearchClient. In the current stack, ReactiveElasticsearchClient uses a transport based on Rest5Client.

### 9.2. When to Use Manual Configuration

Use ReactiveElasticsearchConfiguration when you need to:

- Configure multiple clients or separate clusters.
- Customize ClientConfiguration beyond default properties.
- Change JsonpMapper or transportOptions.
- Configure callbacks on the low-level client.
- Explicitly control repository packages and mapping infrastructure.

If Boot already creates the right ReactiveElasticsearchClient and ReactiveElasticsearchTemplate, inject those beans. Avoid creating duplicate client or template beans without a clear reason.

If you provide your own operations/template bean to back reactive repositories, the bean name commonly used by Spring Boot/Spring Data is reactiveElasticsearchTemplate. Check the auto-configuration conditions of your Boot version to avoid bean conflicts.

## 10. Client Lifecycle and Resource Management

The client is a shared component of the application context. Do not create a new client inside each service method or request.

A typical Spring configuration manages the lifecycle as follows:

1. Application context starts up.
2. ReactiveElasticsearchConfiguration creates ClientConfiguration.
3. Low-level client and transport are created.
4. ReactiveElasticsearchClient is created from the transport.
5. ReactiveElasticsearchTemplate is created from the client and converter.
6. Services/repositories receive the injected beans.
7. When the application context closes, Spring manages shutdown of the infrastructure beans.

Do not close the client after every request. If you manually instantiate a low-level client outside Spring configuration, you are responsible for closing its resources when the application stops.

Guidelines:

- Use singleton beans for client and template.
- Do not create a new Rest5Client per search.
- Do not call close() after each operation.
- Do not leave a connection or response body open beyond the request lifecycle.
- Use timeouts and connection pools sized appropriately for your load.
- Monitor connection failures, timeouts, and request latency.

## 11. Reactor: Subscription, Laziness, and Backpressure

### 11.1. Publishers Execute Only When Subscribed To

Example:

~~~java
Mono<Product> result = repository.findById("P-100");
~~~

This line creates a publisher. It does not mean the Elasticsearch request has completed or that the Product value is immediately available.

When the framework or caller subscribes, the pipeline executes:

~~~java
return repository.findById("P-100")
        .map(Product::getName);
~~~

In a controller, simply return the publisher to WebFlux. Do not subscribe manually.

### 11.2. Do Not Call block() on a Reactive Request Path

Avoid writing:

~~~java
Product product = repository.findById("P-100").block();
~~~

block() waits synchronously for the result and holds the thread until the publisher completes. If called on a WebFlux event-loop thread, it can degrade throughput or throw an exception due to a blocking call.

Instead, compose publishers:

~~~java
Mono<Product> findAndUpdate(String id) {
    return repository.findById(id)
            .flatMap(product -> {
                product.setCategory("FEATURED");
                return repository.save(product);
            });
}
~~~

flatMap chains the save operation after findById emits the entity.

### 11.3. Do Not Call subscribe() Inside a Service

Avoid:

~~~java
public void save(Product product) {
    repository.save(product).subscribe();
}
~~~

This creates an execution stream detached from the caller. The caller does not receive the operation's result or error, making coordination with transactions, retries, tracing, and cancellation difficult.

Return the publisher instead:

~~~java
public Mono<Product> save(Product product) {
    return repository.save(product);
}
~~~

The caller decides how to compose, handle errors, and complete the request.

### 11.4. Backpressure Does Not Mean Unbounded Queries

Flux allows downstream to request data based on demand. However, an Elasticsearch search request still has a result limit determined by size/from or the corresponding pagination mechanism.

Do not assume Flux<SearchHit<T>> automatically scans the entire index infinitely or fetches multiple pages automatically. If pagination is needed, configure Query/Pageable, use search_after/PIT when appropriate, or implement an explicit iteration mechanism.

Collecting all results with collectList() can grow memory usage proportionally to hit count. Only use it when the result set is already bounded to a reasonable size.

## 12. Composing Multiple Reactive Operations

Reactor provides operators for composing operations:

| Operator | Purpose |
| --- | --- |
| map | Transforms a value synchronously. |
| flatMap | Chains an operation returning a Publisher. |
| concatMap | Executes elements sequentially in order. |
| flatMapSequential | Executes asynchronously while preserving emission order. |
| filter | Filters values. |
| switchIfEmpty | Handles a publisher that emits no value. |
| onErrorResume | Switches to another publisher on error. |
| retryWhen | Retries according to a configured policy. |
| timeout | Limits the wait time for a publisher. |
| zip | Combines results from multiple publishers. |

Example finding a product and then saving an access log:

~~~java
Mono<Product> findAndRecord(String id) {
    return repository.findById(id)
            .flatMap(product ->
                    accessLogRepository.save(
                            new ProductAccessLog(product.getId())
                    ).thenReturn(product)
            );
}
~~~

thenReturn preserves the Product result after the log write finishes.

### 12.1. Running Multiple Independent Operations

~~~java
Mono<Tuple2<Long, Long>> loadStatistics() {
    Mono<Long> active = repository.countByCategory("ACTIVE");
    Mono<Long> archived = repository.countByCategory("ARCHIVED");

    return Mono.zip(active, archived);
}
~~~

Mono.zip runs independent publishers and emits a tuple when all complete. If one operation fails, the error is forwarded according to Reactor rules.

Only run operations in parallel when they are truly independent and the cluster has sufficient capacity. Issuing too many concurrent requests can increase pressure on Elasticsearch.

## 13. Error Handling and Retries

Errors from Elasticsearch are translated into error signals in Mono/Flux. You can handle them using onErrorResume, onErrorMap, or retryWhen.

Example mapping an error in a service:

~~~java
Mono<Product> findProduct(String id) {
    return repository.findById(id)
            .switchIfEmpty(Mono.error(
                    new ProductNotFoundException(id)
            ))
            .onErrorMap(
                    ElasticsearchException.class,
                    ProductSearchException::new
            );
}
~~~

Actual exception names depend on the client layer and Spring Data version. Handle errors by meaningful exception types or status codes rather than parsing fixed error messages.

### 13.1. Bounded Retries

Retries are only appropriate for transient, recoverable failures such as certain connection errors or throttling. Never retry indefinitely and never retry every exception.

Example:

~~~java
Mono<Product> findWithRetry(String id) {
    return repository.findById(id)
            .retryWhen(
                    Retry.backoff(2, Duration.ofMillis(200))
                            .filter(this::isTransientFailure)
            );
}
~~~

The isTransientFailure method should classify errors according to application policy. Mapping, authentication, validation, or invalid query errors usually do not resolve on retry.

For write operations, idempotency must be considered. If the client does not know whether the previous request was processed by the server, retrying a non-idempotent write can cause duplicate effects.

### 13.2. Timeout and Cancellation

You can apply a timeout to a pipeline:

~~~java
Mono<Product> findProduct(String id) {
    return repository.findById(id)
            .timeout(Duration.ofSeconds(3));
}
~~~

Timeout causes the publisher to emit an error if it does not complete within the allowed duration. When downstream cancels the subscription, cancellation propagates through the reactive pipeline to the extent supported by the underlying components.

Reactor timeouts do not replace client socket timeouts. These two layers serve different purposes and should be configured compatibly.

## 14. Pagination and Large Results

The reactive API does not remove Elasticsearch pagination limits.

With repositories, you can accept Pageable:

~~~java
Flux<Product> findByCategory(String category, Pageable pageable);
~~~

With operations, configure pageable on Query or NativeQuery according to your version's API. When returning a page with metadata, use searchForPage to receive Mono<SearchPage<T>>.

For very large datasets:

- Do not call collectList() on unbounded result sets.
- Choose an appropriate page size.
- Iterate using cursor/search_after if needed.
- Consider Point in Time to maintain a consistent snapshot across pages.
- Close the PIT when finished.
- Limit concurrent requests.
- Handle cancellation when the client disconnects.

Flux is only how data is represented in the application. It does not change Search API semantics.

## 15. Reactive Client and Imperative Client in the Same Application

An application may require both reactive and imperative clients, but their beans and call paths must be kept separate.

| Reactive | Imperative |
| --- | --- |
| ReactiveElasticsearchClient | ElasticsearchClient |
| ReactiveElasticsearchOperations | ElasticsearchOperations |
| ReactiveElasticsearchTemplate | ElasticsearchTemplate |
| Mono / Flux | Direct value or Collection |
| Reactive repository | Imperative repository |

Do not inject ElasticsearchOperations, call it in a reactive service, and expect wrapping the result in Mono.fromCallable() to turn blocking I/O into non-blocking I/O.

If you must integrate a blocking library, you can isolate that call on the boundedElastic scheduler:

~~~java
Mono<Result> callBlockingLibrary() {
    return Mono.fromCallable(() -> blockingLibrary.call())
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

This is only a workaround to isolate blocking work. For Elasticsearch, use ReactiveElasticsearchClient/Operations to keep I/O on the reactive stack.

If you have two clusters or two client types, use explicit qualifiers and meaningful bean/service names to prevent injecting the wrong one.

## 16. Managing Indices and Mappings via the Reactive API

ReactiveElasticsearchOperations provides indexOps() to interact with indices reactively.

Example obtaining ReactiveIndexOperations:

~~~java
ReactiveIndexOperations indexOperations =
        operations.indexOps(Product.class);
~~~

Index operations such as checking existence, creating an index, creating mappings, or deleting an index return publishers according to the API. When invoking them, you must subscribe or compose the publisher into a pipeline for the request to execute.

For example, index initialization should be handled during bootstrap or migration, not by repeatedly running create-index calls on every business request.

In production, index templates, mappings, and aliases are usually best managed via separate migrations or deployments. Automatic index creation from entity metadata is convenient in development, but mapping changes in production should be controlled carefully.

## 17. Testing the Reactive Client

You can use Reactor Test with StepVerifier to test publishers:

~~~java
import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

@Test
void returnsProductById() {
    Mono<Product> result = repository.findById("P-100");

    StepVerifier.create(result)
            .expectNextMatches(product ->
                    product.getId().equals("P-100"))
            .verifyComplete();
}
~~~

StepVerifier subscribes to the publisher and verifies emitted signals. This is the appropriate way to test Mono/Flux without blocking in tests.

For integration tests:

- Run a compatible Elasticsearch version.
- Verify TLS/authentication if the environment uses them.
- Verify mappings and indices are created.
- Test save/get/search/delete.
- Test empty results and error mapping.
- Test timeouts, cancellation, and retries.
- Verify reactive repositories are scanned in the right package.
- Verify no imperative client is mistakenly injected.

Testcontainers can help spin up Elasticsearch for integration tests. Choose an image version matching the compatibility matrix of your Spring Data Elasticsearch and Elasticsearch Java Client versions.

## 18. Observability and Operations

In production, monitor:

- Request latency and throughput.
- Connection timeouts and socket timeouts.
- HTTP status codes and error types.
- Number of concurrent in-flight requests.
- Retry counts.
- Connection pool saturation.
- Elasticsearch cluster health and search/write latency.
- Cluster heap, CPU, thread pools, and rejected requests.
- Application-side cancellations or timeouts.

Spring Data Elasticsearch integrates with observation/Micrometer abstractions depending on the version. You can use Spring Boot's observation registry and tracing to correlate HTTP requests with Elasticsearch operations.

TRACE-level transport logging can be helpful when debugging requests/responses, but should not be enabled broadly in production. Logs may contain queries, document payloads, or sensitive information.

## 19. Common Configuration Issues

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| ReactiveElasticsearchClient bean not found | Missing Spring Data Elasticsearch or Reactor, or auto-configuration disabled. | Check dependencies and Spring Boot configuration. |
| ReactiveElasticsearchOperations not found | Client not configured or template not created. | Use ReactiveElasticsearchConfiguration or Boot auto-configuration. |
| Reactive repository not created | EnableReactiveElasticsearchRepositories not enabled or wrong scan package. | Check annotation and basePackages. |
| Repository returns publisher but no request is sent | Publisher was not subscribed to. | Return publisher to the framework or compose with another publisher. |
| Requests hang or thread starvation occurs | Called block or used imperative client on the WebFlux event loop. | Use the reactive client end-to-end and remove blocking calls. |
| TLS handshake fails | Incorrect certificate, CA, or SSL context. | Check certificate chain and trust configuration. |
| 401/403 | Wrong username/password or insufficient role permissions. | Check credentials and cluster/index privileges. |
| 404 via reverse proxy | Wrong path prefix or endpoint. | Check withPathPrefix and proxy configuration. |
| Connection timeout | Node unreachable, pool saturated, or timeout too short. | Check network, cluster, connection pool, and timeouts. |
| Search returns fewer documents than expected | Query size/page size or filter limits results. | Check Query, Pageable, and Search API behavior. |
| Old config class fails to compile | Example uses AbstractReactiveElasticsearchConfiguration or legacy client. | Use ReactiveElasticsearchConfiguration with the right package and version. |
| Multiple operations/client beans | Boot auto-config and manual config create duplicate configurations. | Pick one configuration approach or use explicit qualifiers. |

## 20. End-to-End Configuration Workflow

When introducing reactive Elasticsearch into an application, you can follow this sequence:

1. Select compatible versions of Spring Boot, Spring Data Elasticsearch, and Elasticsearch.
2. Add Spring Data Elasticsearch and Reactor dependencies.
3. If the HTTP server is also reactive, use Spring WebFlux.
4. Choose between Boot auto-configuration or manual ReactiveElasticsearchConfiguration.
5. Configure host, TLS, authentication, timeouts, and headers.
6. Verify Spring creates ReactiveElasticsearchClient and ReactiveElasticsearchOperations.
7. Declare entities with @Document and appropriate field mappings.
8. Enable @EnableReactiveElasticsearchRepositories if using manual repository configuration.
9. Inject ReactiveElasticsearchOperations or reactive repositories into services.
10. Return Mono/Flux end-to-end across services and WebFlux controllers.
11. Avoid block(), subscribe(), and imperative clients in the reactive request path.
12. Verify pagination, cancellation, retries, and error mapping.
13. Write integration tests against a compatible Elasticsearch instance.
14. Monitor latency, connection pool usage, and cluster resources in production.

## 21. References

- [Spring Data Elasticsearch — Elasticsearch Clients](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/clients.html)
- [Spring Data Elasticsearch — ReactiveElasticsearchConfiguration API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/ReactiveElasticsearchConfiguration.html)
- [Spring Data Elasticsearch — ReactiveElasticsearchOperations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/ReactiveElasticsearchOperations.html)
- [Spring Data Elasticsearch — Reactive Elasticsearch Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories/reactive-elasticsearch-repositories.html)
- [Spring Data Elasticsearch — ReactiveElasticsearchTemplate API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/ReactiveElasticsearchTemplate.html)
- [Spring Boot — Working with NoSQL Technologies](https://docs.spring.io/spring-boot/reference/data/nosql.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)

ReactiveElasticsearchConfiguration creates the reactive client and required abstractions from ClientConfiguration. In services, ReactiveElasticsearchOperations or reactive repositories provide Mono/Flux APIs to integrate with Spring WebFlux. Keep processing non-blocking, manage the client as a singleton bean, configure TLS/auth/timeouts properly, and distinguish the current client from legacy APIs for stable connectivity.
