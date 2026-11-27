# ReactiveElasticsearchOperations and ReactiveElasticsearchTemplate

Spring Data Elasticsearch provides reactive APIs for interacting with Elasticsearch using the Reactor model. The two central components are `ReactiveElasticsearchOperations` and `ReactiveElasticsearchTemplate`: the interface defines reactive operations at the document and search level, while the template is the implementation that executes those operations through the reactive Elasticsearch client.

The reactive API returns `Mono` or `Flux` instead of returning results synchronously. `Mono<T>` represents zero or one value; `Flux<T>` represents a stream of zero to many values. As a result, a Spring WebFlux application can compose Elasticsearch operations into a non-blocking pipeline, control data flow, and combine them with other reactive sources.

The reactive API does not change Elasticsearch semantics: a document write is still a document-level operation; bulk requests can still partially succeed; there are no multi-document ACID transactions equivalent to JPA. Reactivity only changes how the application interacts and manages execution flow.

## 1. Reactivity in Spring Data Elasticsearch

In an imperative application, an operation typically returns a result immediately after the method executes:

```java
Product product = operations.get("KB-1001", Product.class);
```

With the reactive API, the method returns a publisher:

```java
Mono<Product> product = reactiveOperations.get(
    "KB-1001",
    Product.class,
    IndexCoordinates.of("products")
);
```

`Mono<Product>` is not yet a `Product`; it describes a pipeline that may emit a product, complete empty if not found, or emit an error. Execution typically begins when a subscriber requests data.

### 1.1 Mono and Flux

| Type | Element count | Example |
|---|---:|---|
| `Mono<T>` | 0 or 1 | Get a document by ID, count results, save one entity |
| `Flux<T>` | 0 to many | Get multiple entities, stream search hits, save multiple entities |

Example:

```java
Mono<Product> oneProduct = reactiveOperations.get(
    "KB-1001", Product.class, PRODUCTS
);

Flux<SearchHit<Product>> matchingProducts = reactiveOperations.search(
    query, Product.class, PRODUCTS
);
```

`Mono` and `Flux` are Project Reactor types. They implement the Reactive Streams contract, supporting `onNext`, `onError`, `onComplete` signals, and backpressure.

### 1.2 Publishers Are Typically Lazy

Creating a `Mono` or `Flux` usually only constructs the pipeline. The actual request is sent when the pipeline is subscribed to. Thus, the following code alone does not guarantee the request has executed:

```java
Mono<Product> result = reactiveOperations.get("KB-1001", Product.class, PRODUCTS);
```

In a WebFlux controller, return the publisher to the framework so the framework subscribes and writes the response. In a service, usually return the publisher to the caller rather than calling `.subscribe()` inside the method.

### 1.3 Do Not Call block in Reactive Flows

Do not turn the reactive API back into synchronous execution using `.block()` in a controller or on an event-loop thread:

```java
// Avoid in a WebFlux request path.
Product product = reactiveOperations
    .get("KB-1001", Product.class, PRODUCTS)
    .block();
```

`block()` waits for the result and occupies the thread. Calling it on an event loop can degrade throughput or throw blocking-call errors depending on the environment. Only consider bridging to blocking at controlled boundaries, such as an imperative batch job; do not use it to write WebFlux services.

## 2. Distinguishing Operations and Template

`ReactiveElasticsearchOperations` is the abstraction services should depend on. It groups reactive operations such as save, get, delete, count, search, index operations, and other query operations depending on the version.

`ReactiveElasticsearchTemplate` is the concrete implementation of this interface. The template coordinates the reactive Elasticsearch client, converter/mapping context, and Spring Data components to translate entities/queries into Elasticsearch requests and responses back into Java types.

| Component | Role |
|---|---|
| `ReactiveElasticsearchOperations` | Reactive operations interface, suitable for injecting into services |
| `ReactiveElasticsearchTemplate` | Implementation of Operations, executing via the reactive client |
| `ReactiveElasticsearchClient` | Lower-level reactive client used by the template |
| `ElasticsearchConverter` | Converts between entities and documents using mapping metadata |
| `ReactiveElasticsearchRepository` | Reactive repository abstraction for CRUD/query methods |

### 2.1 Why Should Services Depend on the Interface?

```java
@Service
public class ProductSearchService {

    private final ReactiveElasticsearchOperations operations;

    public ProductSearchService(ReactiveElasticsearchOperations operations) {
        this.operations = operations;
    }
}
```

The service only needs the operations contract. Spring injects the appropriate implementation, typically `ReactiveElasticsearchTemplate`. This reduces coupling to the implementation class and makes it easier to swap configurations or mock the abstraction in tests.

### 2.2 When to Use Template Directly?

Injecting `ReactiveElasticsearchOperations` is usually sufficient. Only depend directly on `ReactiveElasticsearchTemplate` when the application truly needs implementation-specific APIs. For flexible Query DSL, `NativeQuery` with Operations generally suffices without calling the low-level client.

## 3. Configuring ReactiveElasticsearchTemplate

The reactive template requires a reactive Elasticsearch client and a mapping converter. Spring Data provides base configurations to create these beans according to the client and version in use.

### 3.1 Dependencies

An application typically needs:

- Spring Data Elasticsearch compatible with the project's Spring Boot/Spring Data version.
- Reactor Core (usually already included via Spring WebFlux).
- Spring WebFlux if building reactive HTTP APIs.
- The reactive Elasticsearch client module corresponding to the Spring Data Elasticsearch release line.

Do not independently upgrade a single Elasticsearch Java Client artifact to an arbitrary version while bypassing Spring Boot/Spring Data dependency management. Spring Data Elasticsearch releases are built to be compatible with a specific Elasticsearch client line.

General Maven example:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-elasticsearch</artifactId>
</dependency>
```

Starter names and dependency management depend on the Spring Boot version. Check the BOM and documentation for your version line to determine which reactive client implementation is provided.

### 3.2 AbstractReactiveElasticsearchConfiguration

Spring Data Elasticsearch provides reactive base configuration. A typical configuration:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.AbstractReactiveElasticsearchConfiguration;
import org.springframework.data.elasticsearch.repository.config.EnableReactiveElasticsearchRepositories;

@Configuration
@EnableReactiveElasticsearchRepositories(
    basePackages = "com.example.catalog.repository"
)
public class ReactiveElasticsearchConfig
        extends AbstractReactiveElasticsearchConfiguration {

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
            .connectedTo("localhost:9200")
            .build();
    }
}
```

The base configuration creates the reactive client, converter, and reactive operations/template according to the version's API. When the application uses authentication, TLS, proxies, or multiple nodes, configure `ClientConfiguration` for your deployment environment; never hard-code credentials in source code.

### 3.3 Injecting Operations

After configuration, services can inject the interface:

```java
@Service
public class ProductService {

    private final ReactiveElasticsearchOperations operations;

    public ProductService(ReactiveElasticsearchOperations operations) {
        this.operations = operations;
    }
}
```

Spring typically provides a `ReactiveElasticsearchTemplate` bean as the implementation. If the application creates the template manually, provide the matching reactive client and converter, and ensure the bean's lifecycle is managed by Spring.

### 3.4 Reactive and Imperative Clients Are Distinct Configuration Paths

Do not pass a blocking `ElasticsearchClient` where a reactive client is expected. Similarly, `ElasticsearchOperations`/`ElasticsearchTemplate` is the imperative API; `ReactiveElasticsearchOperations`/`ReactiveElasticsearchTemplate` is the reactive API. Choose the right abstraction for the application's execution model.

## 4. Entities and Mapping

The reactive template uses the same mapping metadata as standard Spring Data Elasticsearch. Example entity:

```java
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

    @Field(type = FieldType.Double)
    private Double price;

    @Field(type = FieldType.Integer)
    private Integer stock;

    protected Product() {
    }

    public Product(String id, String sku, String name, Double price, Integer stock) {
        this.id = id;
        this.sku = sku;
        this.name = name;
        this.price = price;
        this.stock = stock;
    }

    // Getters and setters omitted for brevity.
}
```

`@Document` specifies the default index. `@Id` maps the document ID. `@Field` describes the Elasticsearch field type and related mapping metadata. The reactive template uses the converter to convert entities to JSON documents and back.

### 4.1 Index and Mapping Operations

Index operations such as checking existence, creating an index, or putting mappings also have reactive APIs via index operations. In modern Spring Data versions, `operations.indexOps(Product.class)` returns a reactive index operations abstraction; operations such as `exists()`, `create()`, or `putMapping()` return publishers.

Usage pattern example:

```java
Mono<Boolean> ensureIndex = operations.indexOps(Product.class)
    .exists()
    .flatMap(exists -> exists
        ? Mono.just(true)
        : operations.indexOps(Product.class).create()
    );
```

This is an illustrative pattern; exact index operations signatures and mapping creation methods may vary by version. In production environments, indices and mappings are typically managed via controlled migrations or deployment steps rather than recreating them on every request.

## 5. CRUD with ReactiveElasticsearchOperations

### 5.1 Save One Entity

`save` returns `Mono<T>`:

```java
private static final IndexCoordinates PRODUCTS =
    IndexCoordinates.of("products");

public Mono<Product> save(Product product) {
    return operations.save(product, PRODUCTS);
}
```

The publisher emits the saved entity with metadata updated according to mapping and client behavior. Because the publisher is lazy, the caller must subscribe or return it to an upper reactive layer for the operation to execute.

### 5.2 Save Multiple Entities

`saveAll` returns `Flux<T>` and can accept a source publisher:

```java
public Flux<Product> saveAll(Flux<Product> products) {
    return operations.saveAll(products, PRODUCTS);
}
```

You can create a publisher from a collection:

```java
Flux<Product> source = Flux.fromIterable(products);
return operations.saveAll(source, PRODUCTS);
```

For large volumes of data, do not load an entire file into memory to construct a massive Flux if the source can be read in batches. Use a publisher capable of emitting data on demand, cap concurrency, and monitor error results.

### 5.3 Get by ID

```java
public Mono<Product> findById(String id) {
    return operations.get(id, Product.class, PRODUCTS);
}
```

If the document does not exist, the API typically completes empty rather than emitting a null `Product`. Callers can convert the empty case into a business error:

```java
public Mono<Product> requireById(String id) {
    return operations.get(id, Product.class, PRODUCTS)
        .switchIfEmpty(Mono.error(
            new ProductNotFoundException(id)
        ));
}
```

Do not return `Mono.just(null)`: Reactor forbids emitting null as an element.

### 5.4 Delete by ID

```java
public Mono<Void> delete(String id) {
    return operations.delete(id, Product.class, PRODUCTS)
        .then();
}
```

`.then()` discards the result value and keeps only the completion/error signal. If the API needs to return the deletion status or ID, keep the return type provided by your Operations version instead of calling `.then()`.

### 5.5 Count

```java
public Mono<Long> countActive() {
    Query query = new CriteriaQuery(
        new Criteria("active").is(true)
    );

    return operations.count(query, Product.class, PRODUCTS);
}
```

`count` returns `Mono<Long>` because the result arrives asynchronously. It avoids loading all document hits into the application.

## 6. Searching with ReactiveElasticsearchOperations

Reactive Operations provides different search methods depending on your needs: streaming individual hits, obtaining a wrapper with search metadata, or retrieving a page abstraction.

### 6.1 Creating a NativeQuery

Example searching products by name:

```java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Query query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("name")
        .query("wireless keyboard")
    ))
    .withPageable(PageRequest.of(0, 20))
    .build();
```

`NativeQuery` uses the Elasticsearch Java Client Query DSL builder. It can combine bool, match, range, nested, aggregations, sorting, and other search options. The query object is independent of imperative or reactive execution; the difference lies in how Operations executes it and returns results.

### 6.2 Search Returning Flux<SearchHit<T>>

```java
public Flux<SearchHit<Product>> searchHits(String keyword) {
    Query query = NativeQuery.builder()
        .withQuery(q -> q.match(m -> m
            .field("name")
            .query(keyword)
        ))
        .withPageable(PageRequest.of(0, 20))
        .build();

    return operations.search(query, Product.class, PRODUCTS);
}
```

Each element is a `SearchHit<Product>`, containing the entity along with metadata such as score, ID, sort values, or highlights depending on the request. If only the entity is needed:

```java
public Flux<Product> searchProducts(String keyword) {
    return searchHits(keyword)
        .map(SearchHit::getContent);
}
```

`Flux` allows downstream to process each hit individually rather than buffering all results into a `List` before proceeding.

### 6.3 SearchForHits When Metadata Is Needed

When total hits or search metadata are needed alongside the result stream, use `searchForHits` returning `Mono<ReactiveSearchHits<T>>` in versions providing this abstraction:

```java
public Mono<ReactiveSearchHits<Product>> searchWithMetadata(String keyword) {
    Query query = NativeQuery.builder()
        .withQuery(q -> q.match(m -> m
            .field("name")
            .query(keyword)
        ))
        .withPageable(PageRequest.of(0, 20))
        .build();

    return operations.searchForHits(query, Product.class, PRODUCTS);
}
```

`ReactiveSearchHits` contains search metadata and a publisher of hits. Because the hits result is reactive, accessing or consuming the list still occurs via `Flux`; do not assume an in-memory synchronous `List` is already present.

### 6.4 SearchForPage

When a use case requires a page abstraction, Spring Data Elasticsearch versions support `searchForPage(...)` returning `Mono<ReactiveSearchPage<T>>`. The page abstraction holds pageable information and total hits alongside the content publisher.

```java
public Mono<ReactiveSearchPage<Product>> searchPage(String keyword) {
    Query query = NativeQuery.builder()
        .withQuery(q -> q.match(m -> m
            .field("name")
            .query(keyword)
        ))
        .withPageable(PageRequest.of(0, 20))
        .build();

    return operations.searchForPage(query, Product.class, PRODUCTS);
}
```

Exact signatures for `searchForHits`, `searchForPage`, and wrapper types can vary across Spring Data Elasticsearch release lines. Check the Javadoc for your exact dependency version before using them.

## 7. SearchHits, SearchHit, and ReactiveSearchHits

These similarly named types have distinct roles:

| Type | Meaning |
|---|---|
| `SearchHit<T>` | A single hit containing the entity and metadata of a matched document |
| `SearchHits<T>` | Imperative search result, typically containing a collection of hits and metadata |
| `ReactiveSearchHits<T>` | Reactive wrapper where metadata accompanies a publisher of hits |
| `ReactiveSearchPage<T>` | Reactive page abstraction for search results |

Reactive code should not convert `Flux<SearchHit<T>>` into a `List` just to obtain a total count. Use wrapper/metadata APIs when total hits or summary info is needed. If you only need to stream results, `Flux<SearchHit<T>>` is usually simpler.

### 7.1 Reading Highlights

If the query includes highlights, highlight metadata is stored on `SearchHit`:

```java
return operations.search(query, Product.class, PRODUCTS)
    .map(hit -> new ProductSearchResult(
        hit.getContent(),
        hit.getHighlightFields()
    ));
```

A DTO can hold both the entity and the highlight map separately. Avoid mutating entity fields just to inject highlight snippets into original source fields.

### 7.2 Reading Sort Values

With `search_after` pagination, `SearchHit` can provide the document's sort values. The application must preserve those exact values to construct the cursor for the next request. The exact API for reading sort values depends on `SearchHit` and the Spring Data version.

## 8. CriteriaQuery and NativeQuery

Reactive Operations can execute the `Query` types supported by Spring Data. Two common ways to build queries are:

- `CriteriaQuery`: expresses simple field/operator conditions.
- `NativeQuery`: expresses flexible Elasticsearch Query DSL through the Java Client builder.

### 8.1 CriteriaQuery

```java
Query query = new CriteriaQuery(
    new Criteria("status").is("ACTIVE")
        .and("price").greaterThanEqual(50)
);

return operations.search(query, Product.class, PRODUCTS)
    .map(SearchHit::getContent);
```

CriteriaQuery is well suited for basic filtering conditions and queries assembled dynamically from simple parameters.

### 8.2 NativeQuery for Bool Queries

```java
Query query = NativeQuery.builder()
    .withQuery(q -> q.bool(b -> b
        .must(m -> m.match(mm -> mm
            .field("name")
            .query(keyword)
        ))
        .filter(f -> f.term(t -> t
            .field("status")
            .value("ACTIVE")
        ))
        .filter(f -> f.range(r -> r
            .number(n -> n
                .field("price")
                .gte(50.0)
            )
        ))
    ))
    .withPageable(PageRequest.of(0, 20))
    .build();

return operations.search(query, Product.class, PRODUCTS);
```

NativeQuery is appropriate when full Query DSL is needed, such as nested queries, function scores, highlights, aggregations, or advanced sorting. The query type does not negate reactivity; the publisher is created at the Operations execution step.

## 9. Composing Multiple Reactive Operations

A major advantage of Reactor is composing operations without blocking threads.

### 9.1 Fetching and Transforming a Document

```java
public Mono<ProductView> getView(String id) {
    return operations.get(id, Product.class, PRODUCTS)
        .switchIfEmpty(Mono.error(new ProductNotFoundException(id)))
        .map(product -> new ProductView(
            product.getId(),
            product.getName(),
            product.getPrice()
        ));
}
```

`map` is used for synchronous transformations on the emitted value. If the next step returns a `Mono` or `Flux`, use `flatMap` to flatten nested publishers.

### 9.2 Chaining Two Asynchronous Operations

```java
public Mono<ProductDetails> getDetails(String id) {
    return operations.get(id, Product.class, PRODUCTS)
        .switchIfEmpty(Mono.error(new ProductNotFoundException(id)))
        .flatMap(product -> loadInventory(product.getSku())
            .map(inventory -> new ProductDetails(product, inventory))
        );
}
```

`flatMap` avoids creating `Mono<Mono<ProductDetails>>`. If two sources are independent, they can run in parallel using `Mono.zip`:

```java
return Mono.zip(
    operations.get(id, Product.class, PRODUCTS),
    loadReviews(id)
).map(tuple -> new ProductDetails(tuple.getT1(), tuple.getT2()));
```

When one source can complete empty, define `zip` semantics carefully: `Mono.zip` requires every source to emit a value to form a tuple. Use `defaultIfEmpty`, `switchIfEmpty`, or `zipWhen` according to business requirements.

### 9.3 concatMap and flatMap on Flux

When processing multiple IDs:

```java
Flux<Product> findMany(List<String> ids) {
    return Flux.fromIterable(ids)
        .concatMap(id -> operations.get(id, Product.class, PRODUCTS));
}
```

`concatMap` processes items one by one and preserves source order. `flatMap` allows multiple operations to execute concurrently, potentially increasing throughput, though results may be emitted out of the original order:

```java
Flux<Product> findManyConcurrently(List<String> ids) {
    return Flux.fromIterable(ids)
        .flatMap(id -> operations.get(id, Product.class, PRODUCTS), 8);
}
```

The concurrency parameter limits how many inner publishers are active simultaneously. Choose the value based on cluster load, connection pool size, and latency; do not raise it indefinitely in pursuit of throughput.

## 10. Backpressure and Processing Large Datasets

Reactive Streams lets subscribers signal data demand via request(n). `Flux` can coordinate with downstream to avoid pushing unbounded elements into a slow consumer.

However, backpressure does not mean every Elasticsearch API streams documents one by one over the network as an infinite stream. A search request may still fetch a batch of hits from Elasticsearch and emit them through Flux. For large datasets, choose an appropriate pagination/scroll mechanism and control batch sizes.

### 10.1 Limiting Concurrency

When ingesting many documents:

```java
Flux<Product> source = readProductsReactive();

return source
    .buffer(500)
    .concatMap(batch -> operations.saveAll(
        Flux.fromIterable(batch), PRODUCTS
    ));
```

This example splits the source into batches of 500 and sends them sequentially. The batch size is illustrative; measure payload size, throughput, and cluster pressure.

If you want to run several batches in parallel, you can use `flatMap` with bounded concurrency. However, be mindful of commit ordering and handling partial failures.

### 10.2 Avoid Buffering an Entire Flux Unnecessarily

`collectList()` gathers all elements in memory:

```java
Mono<List<Product>> allProducts = operations.search(query, Product.class, PRODUCTS)
    .map(SearchHit::getContent)
    .collectList();
```

Use this only when results are reasonably bounded and the caller truly needs a list. With hundreds of thousands of hits, collecting everything puts pressure on the heap. Process per batch/element or stream incrementally to a sink.

### 10.3 Backpressure Does Not Override Search API Limits

`Flux` does not bypass `from`/`size`, `max_result_window`, scroll/PIT limits, or Elasticsearch response limits. To iterate over many documents, use scroll, PIT + `search_after`, or pagination APIs supported by your version. Do not mistake a reactive publisher for an unbounded server-side search cursor.

## 11. Error Handling and Retries

Reactive pipelines propagate errors via the `onError` signal. Errors can be transformed or handled using Reactor operators.

### 11.1 Translating Technical Errors into Business Errors

```java
public Mono<Product> findRequired(String id) {
    return operations.get(id, Product.class, PRODUCTS)
        .switchIfEmpty(Mono.error(new ProductNotFoundException(id)))
        .onErrorMap(ElasticsearchException.class,
            ex -> new ProductSearchException("Cannot read product", ex));
}
```

In real code, exception types depend on the client and version. Map only well-identified errors; do not turn every exception into not-found, as doing so masks connectivity or mapping failures.

### 11.2 Conditional Retries

```java
return operations.get(id, Product.class, PRODUCTS)
    .retryWhen(Retry.backoff(3, Duration.ofMillis(200))
        .filter(this::isTransientFailure));
```

Retries suit transient failures such as network resets or certain overload errors. Never retry indefinitely and never retry mapping, validation, or authorization errors.

### 11.3 Write Retries Require Idempotency

If a write succeeds in Elasticsearch but the response is lost, a retry may resend the operation. Indexing the same document ID with the same payload usually yields an idempotent final state; increment/decrement scripts or generating documents with random IDs may not be idempotent.

Before retrying writes, determine:

- Is the ID stable?
- Does resending the same payload produce the same final state?
- Do scripts have repeatable side effects?
- Is there a version/sequence or idempotency key to detect duplicate requests?
- Should state be re-read before retrying?

### 11.4 Timeout and Cancellation

```java
return operations.get(id, Product.class, PRODUCTS)
    .timeout(Duration.ofSeconds(3));
```

Timeout emits an error if the publisher does not complete within the specified duration. Cancellation from a client disconnect can cancel pipeline consumption; the extent to which the request is canceled at the client/server depends on the transport and API. Do not assume cancellation guarantees Elasticsearch has not already executed a write.

## 12. Integrating with Spring WebFlux

WebFlux controllers can return `Mono` or `Flux` directly:

```java
@RestController
@RequestMapping("/products")
public class ProductController {

    private final ProductSearchService service;

    public ProductController(ProductSearchService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<ProductView> get(@PathVariable String id) {
        return service.getView(id);
    }

    @GetMapping
    public Flux<ProductView> search(@RequestParam String q) {
        return service.searchProducts(q)
            .map(ProductView::from);
    }
}
```

Spring WebFlux subscribes to the publisher and writes data to the response. Do not call `.subscribe()` or `.block()` in the controller.

### 12.1 Return Page or Flux?

If the endpoint needs page metadata such as total count, page number, and page size, return a clearly structured page DTO. If the endpoint uses a streaming response or only needs the elements, Flux may be a better fit.

Avoid collecting all results into a list just to return a JSON array when the result set can be very large. For standard APIs, pagination still requires size limits and a clear page/cursor contract.

## 13. Reactive Repositories and ReactiveElasticsearchOperations

Spring Data Elasticsearch also supports reactive repositories, such as `ReactiveElasticsearchRepository<T, ID>`. Repositories suit CRUD and convention-based query methods.

```java
public interface ReactiveProductRepository
        extends ReactiveElasticsearchRepository<Product, String> {

    Flux<Product> findByActiveTrue();

    Flux<Product> findByNameContaining(String name);
}
```

Comparison:

| Option | Suitable when |
|---|---|
| `ReactiveElasticsearchRepository` | Simple CRUD/query methods, repository abstraction |
| `ReactiveElasticsearchOperations` | Need control over queries, mapping, search metadata, or varied template operations |
| `ReactiveElasticsearchTemplate` | Need the concrete implementation or template-specific APIs |
| Low-level reactive client | Need client features not exposed by Spring Data abstractions |

Repositories and Operations can coexist in the same application. You do not need to force complex Query DSL into repositories, nor use the template for simple CRUD operations already cleanly expressed by repository methods.

## 14. Reactive Search and Pagination

### 14.1 PageRequest

You can attach a `Pageable` to a query:

```java
Query query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m.field("name").query(keyword)))
    .withPageable(PageRequest.of(
        page,
        size,
        Sort.by(Sort.Order.desc("createdAt"), Sort.Order.asc("sku"))
    ))
    .build();

return operations.searchForPage(query, Product.class, PRODUCTS);
```

Page numbers typically start at 0. APIs should cap `size`, validate page numbers, and allowlist client-supplied sort fields. Reactivity does not make deep offset pagination cheap.

### 14.2 Deep Pagination

For large document counts, `from`/`size` is bounded by `max_result_window` and grows more expensive with offset. Use `search_after` with stable sorting and PIT when deep scanning over a snapshot is needed. The reactive API can emit results as a Flux, but the application still must manage the PIT ID, sort cursor, checkpoints, and cleanup.

### 14.3 Scroll

Some Spring Data Elasticsearch versions provide reactive scroll or `searchForStream`-style APIs. Exact APIs vary by release. A scroll context has a `keep_alive`, must be continued in time, and must be cleared when done. A reactive publisher does not automatically turn a scroll ID into a durable checkpoint.

## 15. Aggregations in Reactive Operations

Reactive Operations can also execute queries containing aggregations. When both hits and aggregation metadata are needed, use the reactive search result wrapper supported by your version; when only aggregations are needed, set search `size: 0` and read the aggregation container.

Example declaring a terms aggregation:

```java
Aggregation byCategory = Aggregation.of(a -> a
    .terms(t -> t.field("category").size(20))
);

Query query = NativeQuery.builder()
    .withQuery(q -> q.matchAll(m -> m))
    .withMaxResults(0)
    .withAggregation("by_category", byCategory)
    .build();
```

Reactive execution:

```java
return operations.searchForHits(query, Product.class, PRODUCTS)
    .map(searchHits -> searchHits.getAggregations());
```

Aggregation container types and how buckets are read depend on the Elasticsearch Java Client and Spring Data version. Distinguish buckets/metrics from `Flux<SearchHit<T>>`; an aggregation is not a document stream.

## 16. Reactive Updates and Deletes

Reactive Operations provides update/delete operations corresponding to the APIs supported by the version. Methods typically return a `Mono` containing the response or operation result.

General delete-by-query example:

```java
Query inactiveProducts = new CriteriaQuery(
    new Criteria("active").is(false)
);

Mono<?> deleteResult = operations.delete(
    inactiveProducts,
    Product.class,
    PRODUCTS
);
```

For update operations, you can use `UpdateQuery` and your version's reactive update API. Check exact method signatures and response types because some releases expose different operations between imperative and reactive templates.

### 16.1 Reactivity Does Not Create Multi-Document Transactions

Chaining multiple `Mono` instances with `then`, `zip`, or `flatMap` only controls execution ordering. It does not create a shared ACID transaction. If the first step writes successfully and a later step fails, Reactor does not roll back the earlier Elasticsearch operation.

For multi-step workflows, you still need idempotency, outbox, saga, or business-level compensation. `onErrorResume` only switches to an alternative pipeline; it does not undo committed side effects.

## 17. Blocking Code and Schedulers

Not every library called by a reactive service is non-blocking. If a step uses JDBC, blocking file I/O, or a synchronous SDK, do not run it directly on an event-loop thread.

Example intentionally bridging a blocking call:

```java
Mono<LegacyData> loadLegacyData(String id) {
    return Mono.fromCallable(() -> legacyBlockingClient.load(id))
        .subscribeOn(Schedulers.boundedElastic());
}
```

`boundedElastic` is intended for bounded blocking tasks. Do not wrap reactive Elasticsearch calls in `fromCallable` and offload them to boundedElastic; doing so forfeits reactive benefits and creates unnecessary blocking threads.

## 18. Testing Reactive Operations

Reactive services can be tested with Reactor Test and `StepVerifier`:

```java
StepVerifier.create(service.findById("KB-1001"))
    .expectNextMatches(product -> product.getSku().equals("KB-1001"))
    .verifyComplete();
```

If the document does not exist:

```java
StepVerifier.create(service.requireById("missing"))
    .expectError(ProductNotFoundException.class)
    .verify();
```

Unit tests can mock `ReactiveElasticsearchOperations` to return `Mono.just`, `Mono.empty`, or `Flux.just`. Integration tests require a compatible Elasticsearch instance to verify mappings, Query DSL, converters, and the real reactive client.

When mocking, remember publishers are lazy: only verifying the pipeline triggers the publisher in tests. Do not call `.subscribe()` arbitrarily and assert immediately, as the test may finish before the pipeline completes.

## 19. Common Pitfalls

### 19.1 Calling block in a Controller

`.block()` breaks non-blocking behavior and can block the event loop. Return `Mono`/`Flux` to WebFlux.

### 19.2 Calling subscribe in a Service

If a service subscribes itself, the caller loses control over lifecycle, errors, and results. Return the publisher so the caller composes the pipeline; only subscribe at well-defined application boundaries such as standalone workers.

### 19.3 Assuming Creating a Mono Sends the Request

Publishers are typically lazy. Without a subscriber, the pipeline may never run. In WebFlux, the framework subscribes when processing the response.

### 19.4 Using map When the Callback Returns a Publisher

`map` produces nested publishers like `Mono<Mono<T>>`. Use `flatMap` or `flatMapMany` when flattening is needed.

### 19.5 flatMap Without Concurrency Limits

Issuing many simultaneous Elasticsearch requests can overload the connection pool or cluster. Cap concurrency and use backpressure/batching.

### 19.6 collectList on Large Result Sets

Buffering an entire Flux in memory can cause heap pressure. Process element by element or in batches for large datasets.

### 19.7 Retrying Non-Idempotent Writes

Retrying a script that increments stock can add multiple times if the first request succeeded but the response was lost. Design appropriate IDs, versions, or idempotency keys.

### 19.8 Using Imperative Operations in a Reactive Pipeline

Do not call blocking `ElasticsearchOperations` on the event loop and wrap the result in a Mono. Inject `ReactiveElasticsearchOperations` and use the reactive client.

### 19.9 Assuming Flux Means Server-Side Streaming of the Entire Index

Flux is an application-side publisher abstraction. The Search API still enforces size/pagination limits; large exports require scroll or PIT + search_after.

### 19.10 Assuming Reactivity Provides Transactions

Reactor orchestrates signal flow; it does not roll back Elasticsearch side effects. Multi-document workflows still require application-level consistency design.

## 20. Combined Example Service

```java
@Service
public class ReactiveProductService {

    private static final IndexCoordinates PRODUCTS =
        IndexCoordinates.of("products");

    private final ReactiveElasticsearchOperations operations;

    public ReactiveProductService(ReactiveElasticsearchOperations operations) {
        this.operations = operations;
    }

    public Mono<Product> findById(String id) {
        return operations.get(id, Product.class, PRODUCTS)
            .switchIfEmpty(Mono.error(new ProductNotFoundException(id)));
    }

    public Mono<Product> save(Product product) {
        return operations.save(product, PRODUCTS);
    }

    public Flux<Product> saveAll(Flux<Product> products) {
        return operations.saveAll(products, PRODUCTS);
    }

    public Flux<Product> search(String keyword, int page, int size) {
        Query query = NativeQuery.builder()
            .withQuery(q -> q.match(m -> m
                .field("name")
                .query(keyword)
            ))
            .withPageable(PageRequest.of(page, size))
            .build();

        return operations.search(query, Product.class, PRODUCTS)
            .map(SearchHit::getContent);
    }

    public Mono<Long> countByName(String keyword) {
        Query query = new CriteriaQuery(
            new Criteria("name").contains(keyword)
        );

        return operations.count(query, Product.class, PRODUCTS);
    }

    public Mono<Void> delete(String id) {
        return operations.delete(id, Product.class, PRODUCTS).then();
    }
}
```

This service demonstrates reactive CRUD, search, and count using publishers. Exact overload names may vary by Spring Data Elasticsearch version; when applying to a project, use the exact APIs of your managed dependencies.

## 21. Usage Guidelines

- Inject `ReactiveElasticsearchOperations` so services depend on the abstraction; `ReactiveElasticsearchTemplate` is the implementation.
- Use `Mono` for zero/one results and `Flux` for multi-element streams.
- Return publishers from services/controllers; avoid arbitrary `.block()` or `.subscribe()` on request paths.
- Use `map` for synchronous transformations and `flatMap` for operations returning publishers.
- Cap concurrency, batch writes, and avoid `collectList()` on large datasets.
- Choose `NativeQuery` or `CriteriaQuery` based on query complexity.
- Use reactive search wrappers when total hits, aggregations, or page metadata are needed.
- Handle errors with Reactor operators and conditional retries; write retries must be idempotent.
- Configure the reactive client matching your Spring Data Elasticsearch line, without mixing in blocking clients.
- Use reactive repositories for simple CRUD/query methods; use Operations when fine-grained query control is required.
- Remember Flux does not remove Elasticsearch pagination or search context limits.
- Reactivity does not provide multi-document ACID transactions; outbox, saga, compensation, or proper aggregate design is still required.

## 22. Summary

`ReactiveElasticsearchOperations` is the reactive abstraction for working with Elasticsearch; `ReactiveElasticsearchTemplate` is the implementation operating via the reactive Elasticsearch client and Spring Data converter. APIs return `Mono` or `Flux`, enabling CRUD, search, count, and query operations to be composed into Reactor pipelines without blocking threads.

In WebFlux applications, controllers should return publishers so the framework manages subscriptions. Services should compose operations using `map`, `flatMap`, `zip`, `concatMap`, or bounded-concurrency `flatMap`. Understand lazy publishers, backpressure, cancellation, error propagation, and retries. `ReactiveSearchHits`/`ReactiveSearchPage` are useful when metadata is needed, while `Flux<SearchHit<T>>` fits hit-by-hit processing.

Reactivity does not change Elasticsearch's fundamental limits. Searches still require pagination/cursors, bulk operations can partially succeed, and multiple documents cannot be committed/rolled back in a single ACID transaction. Use the proper reactive client, control batching/concurrency, design idempotent retries, and enforce business consistency at the application layer.

## References

- [Spring Data Elasticsearch Reference — Reactive Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/reactive-template.html)
- [Spring Data Elasticsearch Reference — Reactive Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/repositories/reactive-repositories.html)
- [Project Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [Reactive Streams Specification](https://www.reactive-streams.org/)
- [Spring Framework — Web Reactive](https://docs.spring.io/spring-framework/reference/web/webflux.html)
