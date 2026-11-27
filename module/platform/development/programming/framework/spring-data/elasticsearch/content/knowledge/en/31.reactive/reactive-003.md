# ReactiveElasticsearchRepository and Repository Scanning

Spring Data Elasticsearch supports repositories using the reactive model built on Project Reactor. Instead of returning an entity or regular collection, reactive repositories return publishers such as Mono and Flux. These publishers describe an asynchronous stream of operations; execution only begins when a subscriber subscribes.

ReactiveElasticsearchRepository is the specialized repository for Elasticsearch. This interface extends ReactiveCrudRepository and ReactiveSortingRepository, providing CRUD operations, conditional searches, sorting, and derived query methods generated from method names. Spring creates proxy implementations for repository interfaces through the repository scanning mechanism. The EnableReactiveElasticsearchRepositories annotation specifies the packages to scan, the reactive template to use, and repository filters.

This lesson covers how to declare entities and ReactiveElasticsearchRepository, use Mono/Flux in CRUD and query methods, configure the Reactive Elasticsearch client, how Spring discovers repository interfaces and registers beans, how to separate reactive and imperative repositories, and common pitfalls during implementation.

## 1. What Is a Reactive Repository?

A repository is an abstraction that lets an application access data through an interface. With Spring Data Elasticsearch, the repository interface declares the required operations, and Spring Data generates an implementation backed by Elasticsearch operations.

There are two primary approaches:

| Repository | Common return types | Operations used |
|---|---|---|
| ElasticsearchRepository | Entity, List, Iterable, Page | ElasticsearchOperations |
| ReactiveElasticsearchRepository | Mono, Flux | ReactiveElasticsearchOperations |

Reactive repositories use Project Reactor as their composition library. ReactiveElasticsearchOperations executes operations through ReactiveElasticsearchClient.

Overall flow:

~~~text
WebFlux Controller / Reactive Service
                 |
                 v
     ReactiveElasticsearchRepository
                 |
                 v
  Repository proxy created by Spring
                 |
                 v
     ReactiveElasticsearchOperations
                 |
                 v
       ReactiveElasticsearchClient
                 |
                 v
             Elasticsearch
~~~

Reactive is not merely changing a return type from List to Flux. The entire flow must remain non-blocking: from HTTP handler, service, and repository down to the client. Calling block() or invoking a synchronous API on the request path can block the event loop and negate the benefits of reactivity.

## 2. Mono and Flux

Project Reactor provides two commonly used publisher types:

| Type | Element count | Example |
|---|---|---|
| Mono<T> | 0 or 1 | Find a single product by ID |
| Flux<T> | 0 to many | Find all products in a category |

Mono can complete without emitting any element, for instance when a document does not exist. Flux can emit multiple elements over time and then complete.

Example:

~~~java
Mono<Product> product = repository.findById("p-100");

Flux<Product> products = repository.findByCategory("accessories");
~~~

These two variables only hold publishers. Declaring a publisher does not mean an Elasticsearch request has already been sent. Execution happens when a subscriber subscribes.

### 2.1. Common Operators

| Operator | Purpose |
|---|---|
| map | Synchronously transforms each value |
| flatMap | Transforms each value into another publisher and merges results |
| concatMap | Transforms sequentially, preserving processing order |
| filter | Keeps only elements matching a predicate |
| switchIfEmpty | Selects an alternative publisher if the source is empty |
| defaultIfEmpty | Emits a default value if the source is empty |
| then | Waits for the publisher to complete, then runs the next step |
| onErrorResume | Switches an error into an alternative publisher |
| onErrorMap | Translates the exception type |
| doOnNext | Observes elements for logging/metrics |

Example chaining two operations:

~~~java
public Mono<Product> findAndRename(String id, String newName) {
    return repository.findById(id)
            .switchIfEmpty(Mono.error(
                    new ProductNotFoundException(id)))
            .map(product -> {
                product.setName(newName);
                return product;
            })
            .flatMap(repository::save);
}
~~~

The repository is invoked within the same reactive chain. There is no need to subscribe manually inside the service.

## 3. Declaring an Elasticsearch Entity

Entities can use the Document and Id annotations just like standard repositories:

~~~java
package com.example.catalog.domain;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Long)
    private Long price;

    public Product() {
    }

    public Product(String id, String name, String category, Long price) {
        this.id = id;
        this.name = name;
        this.category = category;
        this.price = price;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getCategory() {
        return category;
    }

    public Long getPrice() {
        return price;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

In Elasticsearch, IDs are represented as strings. Spring Data Elasticsearch documentation recommends using String for the entity's ID property. Therefore, String is a common and clear choice for IDs.

The Document annotation describes the target index and mapping metadata. Repository scanning does not create the index immediately upon scanning the package; index creation depends on mapping metadata, createIndex settings, and application startup.

## 4. Declaring ReactiveElasticsearchRepository

A repository simply needs to be an interface extending ReactiveElasticsearchRepository:

~~~java
package com.example.catalog.repository;

import org.springframework.data.elasticsearch.repository.ReactiveElasticsearchRepository;

import com.example.catalog.domain.Product;

public interface ProductRepository
        extends ReactiveElasticsearchRepository<Product, String> {
}
~~~

The two generic type parameters:

- Product: domain type stored in Elasticsearch.
- String: ID type of the entity.

Spring Data creates a proxy for this interface when repository scanning is enabled. The application can inject ProductRepository into services or controllers.

ReactiveElasticsearchRepository extends:

- ReactiveCrudRepository: reactive CRUD operations.
- ReactiveSortingRepository: sorted queries and access.

Therefore, you do not need to redeclare save, findById, findAll, or deleteById.

## 5. Reactive CRUD Operations

Some commonly inherited methods:

| Method | Return type | Meaning |
|---|---|---|
| save(entity) | Mono<S> | Saves one entity |
| saveAll(Iterable<S>) | Flux<S> | Saves multiple entities from an Iterable |
| saveAll(Publisher<S>) | Flux<S> | Saves from a publisher |
| findById(id) | Mono<T> | Finds one document by ID |
| findAll() | Flux<T> | Finds multiple documents |
| existsById(id) | Mono<Boolean> | Checks whether an ID exists |
| count() | Mono<Long> | Counts documents |
| deleteById(id) | Mono<Void> | Deletes by ID |
| delete(entity) | Mono<Void> | Deletes an entity |
| deleteAll() | Mono<Void> | Deletes all via repository operation |

Example saving and reading:

~~~java
Mono<Product> saveProduct(Product product) {
    return repository.save(product);
}

Mono<Product> findProduct(String id) {
    return repository.findById(id);
}
~~~

Deleting a document:

~~~java
Mono<Void> deleteProduct(String id) {
    return repository.deleteById(id);
}
~~~

Mono<Void> indicates an operation that only signals completion or error, without emitting a resulting entity.

### 5.1. saveAll with a Publisher

Reactive repositories have an overload accepting a Publisher:

~~~java
Flux<Product> saveProducts(Flux<Product> products) {
    return repository.saveAll(products);
}
~~~

This lets you connect a reactive source directly to the repository without converting all data into a List first.

If the data source is an Iterable:

~~~java
Flux<Product> saveProducts(List<Product> products) {
    return repository.saveAll(Flux.fromIterable(products));
}
~~~

For large streams, avoid calling collectList() just to convert a Flux into a List if holding all data in memory is unnecessary.

## 6. Derived Query Methods

Spring Data builds queries based on method names. Reactive repositories follow the same query method naming rules as other Spring Data repositories, except return types are Mono or Flux.

~~~java
public interface ProductRepository
        extends ReactiveElasticsearchRepository<Product, String> {

    Flux<Product> findByCategory(String category);

    Flux<Product> findByCategoryAndPriceLessThan(
            String category,
            Long maxPrice);

    Mono<Product> findFirstByCategoryOrderByPriceAsc(String category);

    Flux<Product> findByNameContaining(String text);

    Mono<Long> countByCategory(String category);

    Mono<Boolean> existsByName(String name);

    Mono<Long> deleteByCategory(String category);
}
~~~

Meaning:

- findByCategory returns documents with the matching category.
- findByCategoryAndPriceLessThan combines two conditions.
- findFirstByCategoryOrderByPriceAsc finds the first document ordered by ascending price.
- findByNameContaining builds a query using the supported keyword semantics for the field.
- countByCategory returns the count of matching documents.
- existsByName checks whether at least one matching document exists.
- deleteByCategory deletes matching documents and returns the count reactively.

Method names must match the domain model's property names and the keywords supported by Spring Data Elasticsearch. Not all Spring Data JPA keywords share the same semantics or are supported in Elasticsearch.

### 6.1. Combining And and Or

Example:

~~~java
Flux<Product> findByCategoryAndPriceLessThan(
        String category,
        Long maxPrice);

Flux<Product> findByCategoryOrName(
        String category,
        String name);
~~~

Spring Data parses the method name to build the query. When search logic is complex or requires exact Query DSL control, use @Query or ReactiveElasticsearchOperations.

### 6.2. Sort and Pageable

Reactive query methods can accept Sort or Pageable:

~~~java
Flux<Product> findByCategory(String category, Sort sort);

Flux<Product> findByCategory(String category, Pageable pageable);
~~~

Example invocation:

~~~java
Pageable firstPage = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Direction.ASC, "price"));

Flux<Product> products = repository.findByCategory(
        "accessories",
        firstPage);
~~~

The reactive method still returns a Flux. Pageable passes offset, size, and sort information; it does not turn the result into a synchronous Page<T>.

If an API needs both the current page items and the total element count, you can combine the result query with a count query:

~~~java
Mono<ProductPageResponse> findPage(String category, Pageable pageable) {
    Flux<Product> items = repository.findByCategory(category, pageable);
    Mono<Long> total = repository.countByCategory(category);

    return Mono.zip(items.collectList(), total)
            .map(tuple -> new ProductPageResponse(
                    tuple.getT1(),
                    tuple.getT2(),
                    pageable.getPageNumber(),
                    pageable.getPageSize()));
}
~~~

The two queries are independent operations; if data changes between runs, total and items may reflect slightly different points in time. For deep pagination, consider search_after or an appropriate cursor instead of large offsets.

## 7. Using @Query in a Reactive Repository

When derived query methods are not expressive enough, the Query annotation lets you write Query DSL:

~~~java
import org.springframework.data.elasticsearch.annotations.Query;

public interface ProductRepository
        extends ReactiveElasticsearchRepository<Product, String> {

    @Query("""
        {
          "match": {
            "name": {
              "query": "?0"
            }
          }
        }
        """)
    Flux<Product> searchByName(String text);
}
~~~

The ?0 placeholder references the method's first parameter. With multiple parameters, you can use ?1, ?2 according to their corresponding positions.

Example query combining a filter:

~~~java
@Query("""
    {
      "bool": {
        "must": [
          {
            "match": {
              "name": "?0"
            }
          }
        ],
        "filter": [
          {
            "term": {
              "category": "?1"
            }
          }
        ]
      }
    }
    """)
Flux<Product> search(String text, String category);
~~~

Query DSL is still executed by Elasticsearch. Reactivity only affects how requests and results are composed in the application, not the query's semantics.

## 8. Publisher as a Query Parameter

A reactive repository can accept a Publisher for a finder method parameter:

~~~java
Flux<Product> findByCategory(Publisher<String> category);
~~~

This is useful when the search value comes from another reactive source. Example:

~~~java
Mono<String> category = resolveCategoryFromRequest();

Flux<Product> products = repository.findByCategory(category);
~~~

Not every method needs to accept a Publisher. For a simple already-available value, a regular String parameter is more readable. Use a Publisher when reactive composition between the parameter source and query is needed.

## 9. Reactive Repositories Execute Only on Subscription

One of Reactor's most important characteristics is that publishers are typically lazy. Example:

~~~java
Mono<Product> result = repository.save(product);
~~~

This line creates a publisher, but without a subscriber the save operation may not execute.

In Spring WebFlux, a controller can return the publisher directly:

~~~java
@RestController
@RequestMapping("/products")
public class ProductController {

    private final ProductRepository repository;

    public ProductController(ProductRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/{id}")
    public Mono<Product> findById(@PathVariable String id) {
        return repository.findById(id);
    }

    @GetMapping
    public Flux<Product> findAll() {
        return repository.findAll();
    }

    @PostMapping
    public Mono<Product> create(@RequestBody Product product) {
        return repository.save(product);
    }
}
~~~

The WebFlux framework subscribes to the publisher while handling the request and writes the result to the HTTP response. The controller does not need to call subscribe().

### 9.1. Do Not Subscribe Inside a Service

Avoid writing:

~~~java
public void create(Product product) {
    repository.save(product).subscribe();
}
~~~

Subscribing inside a service detaches the operation's lifecycle from the request/caller. The caller cannot receive results or errors in the same reactive chain; controlling cancellation, tracing, and transaction context also becomes harder.

Prefer returning the publisher:

~~~java
public Mono<Product> create(Product product) {
    return repository.save(product);
}
~~~

### 9.2. Only Block at Imperative Boundaries

block() waits for the publisher to complete and turns the result into a synchronous call. Do not use block() in a WebFlux controller, reactive service, or event-loop thread.

In a command-line job or imperative test, block() can be used at the outermost boundary when waiting is genuinely required:

~~~java
repository.save(product).block();
~~~

This blocks the calling thread. That piece of code is no longer non-blocking.

## 10. Building a Reactive Service

A service can combine multiple repository operations:

~~~java
@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Mono<Product> rename(String id, String newName) {
        return repository.findById(id)
                .switchIfEmpty(Mono.error(
                        new ProductNotFoundException(id)))
                .map(product -> {
                    product.setName(newName);
                    return product;
                })
                .flatMap(repository::save);
    }

    public Flux<Product> findAffordable(String category, long maxPrice) {
        return repository.findByCategoryAndPriceLessThan(
                category,
                maxPrice);
    }
}
~~~

flatMap is suitable when the next step returns a publisher. map is suitable when only transforming values in memory. Do not wrap a repository call in Mono.just(repository.save(...)) because the resulting type becomes Mono<Mono<Product>> and the operation is not flattened properly.

## 11. Error Handling in Reactive Chains

Errors in Reactor propagate as error signals. Errors can be transformed or handled with operators:

~~~java
public Mono<Product> findRequired(String id) {
    return repository.findById(id)
            .switchIfEmpty(Mono.error(
                    new ProductNotFoundException(id)))
            .onErrorMap(
                    DataAccessException.class,
                    ProductStorageException::new);
}
~~~

If you want a fallback when a specific error type occurs:

~~~java
public Mono<Product> findOrFallback(String id) {
    return repository.findById(id)
            .onErrorResume(
                    DataAccessResourceFailureException.class,
                    error -> loadFallbackProduct(id));
}
~~~

Avoid catching every Throwable and returning Mono.empty(), as that can turn connection errors, mapping errors, or permission errors into "not found" cases and mask the real cause.

If you need to return corresponding HTTP status codes, handle exceptions in controller advice or translate business errors into responses at the web layer.

## 12. Backpressure and Large Data Streams

Flux supports backpressure: downstream can regulate the rate at which it requests elements from upstream. This enables building pipelines that process large datasets without buffering everything in memory.

Example saving sequentially:

~~~java
Flux<Product> importProducts(Flux<Product> input) {
    return input.concatMap(repository::save);
}
~~~

concatMap processes each element in order. If multiple concurrent operations are allowed:

~~~java
Flux<Product> importProducts(Flux<Product> input) {
    return input.flatMap(repository::save, 8);
}
~~~

The concurrency parameter limits how many inner publishers are subscribed to simultaneously. An appropriate value depends on throughput, cluster limits, and document size.

Avoid using unbounded flatMap on a large source by default. Too many simultaneous requests can overload Elasticsearch and build up queues in the application.

### 12.1. Avoid collectList for Large Datasets

collectList() gathers all elements into a single List before emitting the result:

~~~java
Mono<List<Product>> allProducts = repository.findAll().collectList();
~~~

This may work for small datasets, but consumes excessive memory when an index has millions of documents. If streaming processing is needed, keep using Flux and operators like buffer, window, concatMap, or flatMap with bounded concurrency.

### 12.2. Reactive Does Not Mean Every Downstream Automatically Applies Backpressure

When integrating message brokers, HTTP services, or external APIs, verify whether those publishers truly support backpressure or use unbounded buffers. Use limitRate, concurrency limits, and bounded buffers where appropriate. Monitor pipeline memory, queues, and latency.

## 13. Reactive Elasticsearch Client and Operations

Reactive repositories execute through ReactiveElasticsearchOperations. You can inject this abstraction when dynamic queries or operations unsuitable for repository methods are needed:

~~~java
import org.springframework.data.elasticsearch.core.ReactiveElasticsearchOperations;

@Service
public class ProductSearchService {

    private final ReactiveElasticsearchOperations operations;

    public ProductSearchService(ReactiveElasticsearchOperations operations) {
        this.operations = operations;
    }
}
~~~

ReactiveElasticsearchOperations is the reactive counterpart of ElasticsearchOperations. It provides document, search, and index operations returning Mono/Flux. Reactive repositories use this operations abstraction underneath.

ReactiveElasticsearchClient is the reactive client provided by Spring Data Elasticsearch, built on the Elasticsearch Java Client transport. At the application layer, prefer ReactiveElasticsearchOperations or repositories; only call the client directly when you need a low-level API not exposed by the abstraction.

## 14. Configuring the Reactive Client with Java Configuration

In current Spring Data Elasticsearch, you can extend ReactiveElasticsearchConfiguration to configure the client:

~~~java
package com.example.catalog.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ReactiveElasticsearchConfiguration;

@Configuration
public class ReactiveEsClientConfiguration
        extends ReactiveElasticsearchConfiguration {

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
                .connectedTo("localhost:9200")
                .build();
    }
}
~~~

ReactiveElasticsearchConfiguration creates the required beans, including ReactiveElasticsearchClient and ReactiveElasticsearchOperations. The operations bean is also registered under the name reactiveElasticsearchTemplate for repository infrastructure to use by default.

In real deployments, configure TLS, authentication, connection settings, and timeouts according to cluster requirements. Do not hard-code credentials in source code.

### 14.1. ReactiveElasticsearchConfiguration and Legacy Configuration

Spring Data Elasticsearch 6.x uses ReactiveElasticsearchConfiguration with a reactive client based on the Rest5Client transport. ReactiveElasticsearchLegacyRestClientConfiguration using the legacy RestClient has been deprecated since version 6.0, and migration to ReactiveElasticsearchConfiguration is recommended.

Older configuration examples from prior versions may use different classes or factory methods. When upgrading, check compatible Spring Data Elasticsearch and Elasticsearch client versions rather than copying configuration from a different release train.

## 15. Enabling Repository Scanning

Spring Data needs to know which packages contain repository interfaces in order to create proxy beans. For reactive Elasticsearch, use the annotation:

~~~java
@EnableReactiveElasticsearchRepositories
~~~

This annotation enables the reactive Elasticsearch repository infrastructure. If no package is specified, Spring scans the package of the annotated configuration class and its subpackages.

Example:

~~~java
package com.example.catalog.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.repository.config.EnableReactiveElasticsearchRepositories;

@Configuration
@EnableReactiveElasticsearchRepositories(
        basePackages = "com.example.catalog.repository")
public class ReactiveRepositoryConfiguration {
}
~~~

Spring locates repository interfaces in the configured packages, creates corresponding factories/proxies, and registers beans in the ApplicationContext. The application can then inject the interface like a regular Spring bean.

### 15.1. Repository Scanning Differs from ComponentScan

These two mechanisms serve different purposes:

| Mechanism | Which classes it scans | Result |
|---|---|---|
| ComponentScan | @Component, @Service, @Controller, @Configuration, and related stereotypes | Beans from annotated classes |
| EnableReactiveElasticsearchRepositories | Spring Data reactive Elasticsearch repository interfaces | Repository proxy beans |
| Mapping context | Domain types and mapping metadata | Entity/index conversion metadata |

Repository interfaces do not need @Component. The EnableReactiveElasticsearchRepositories annotation activates a dedicated registrar to find repositories and generate proxies.

Repository scanning also does not turn every entity in a package into a Spring bean. Domain objects are managed by the mapping context when repositories or operations work with those types.

## 16. Selecting Packages to Scan

EnableReactiveElasticsearchRepositories has the following attributes:

| Attribute | Purpose |
|---|---|
| value | Alias for basePackages |
| basePackages | Package names to scan |
| basePackageClasses | Type-safe way to specify packages using marker classes |
| includeFilters | Additionally select repositories by filter |
| excludeFilters | Exclude repositories by filter |
| considerNestedRepositories | Whether to scan nested repository interfaces |
| reactiveElasticsearchTemplateRef | Name of the ReactiveElasticsearchOperations bean to use |
| repositoryImplementationPostfix | Suffix of custom repository implementations |
| queryLookupStrategy | Strategy for resolving query methods |
| namedQueriesLocation | Location of named queries properties file |

### 16.1. basePackages

Specify packages using Strings:

~~~java
@EnableReactiveElasticsearchRepositories(
        basePackages = {
                "com.example.catalog.repository",
                "com.example.inventory.repository"
        })
~~~

Spring scans the declared packages and their subpackages.

### 16.2. basePackageClasses

You can use a marker class placed inside the repository package:

~~~java
package com.example.catalog.repository;

public interface CatalogRepositoryMarker {
}
~~~

Then:

~~~java
@EnableReactiveElasticsearchRepositories(
        basePackageClasses = CatalogRepositoryMarker.class)
~~~

basePackageClasses is a safer choice than String package names because package refactoring is better supported by IDEs and the compiler. The marker only identifies the package; it is not a repository itself.

### 16.3. Default Package of the Configuration Class

If value, basePackages, or basePackageClasses is not specified, Spring scans the package containing the configuration class and its subpackages.

Example:

~~~text
com.example.catalog
    Application.java
    config
        ReactiveRepositoryConfiguration.java
    repository
        ProductRepository.java
~~~

If the annotation is placed on ReactiveRepositoryConfiguration in package com.example.catalog.config, the default base package is com.example.catalog.config. It will not automatically scan the sibling package com.example.catalog.repository.

This is a common reason applications fail to find the ProductRepository bean. Specify basePackages or basePackageClasses if repositories reside outside subpackages of the configuration class.

## 17. Important Scanning Attributes

### 17.1. reactiveElasticsearchTemplateRef

By default, the reactive repository infrastructure uses the bean named reactiveElasticsearchTemplate. If the application has multiple ReactiveElasticsearchOperations beans or a custom bean with a different name, specify it explicitly:

~~~java
@EnableReactiveElasticsearchRepositories(
        basePackages = "com.example.catalog.repository",
        reactiveElasticsearchTemplateRef = "catalogReactiveOperations")
~~~

The referenced bean must be a compatible ReactiveElasticsearchOperations. Do not point a reactive repository to an imperative ElasticsearchOperations.

### 17.2. considerNestedRepositories

Defaults to false. If a repository interface is declared nested inside another class, it is not detected unless enabled:

~~~java
@EnableReactiveElasticsearchRepositories(
        basePackages = "com.example.catalog",
        considerNestedRepositories = true)
~~~

Normally, repository interfaces should be top-level types so they are easy to locate, test, and organize by package. Only enable this option if the project genuinely needs nested repository interfaces.

### 17.3. repositoryImplementationPostfix

If a repository has a custom implementation fragment, the default suffix used to locate the implementation class is Impl.

For example, ProductRepository can be paired with ProductRepositoryImpl following the corresponding custom implementation convention. You can change the suffix if the project uses a custom naming convention.

### 17.4. queryLookupStrategy

The default strategy is CREATE_IF_NOT_FOUND:

- CREATE: creates the query from the method name.
- USE_DECLARED_QUERY: requires a pre-declared query.
- CREATE_IF_NOT_FOUND: prefers a declared query; if none exists, creates one from the method name.

Choose the strategy matching project conventions. If most queries use derived methods, the default is usually appropriate.

### 17.5. namedQueriesLocation

Allows specifying the file containing named query properties. The default is META-INF/elasticsearch-named-queries.properties. Use this when the project manages named queries outside annotations or method declarations.

## 18. Spring Boot Auto-Configuration

In a Spring Boot application, auto-configuration can create the client, template, and repository infrastructure when the required dependencies are on the classpath.

Common dependencies:

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

Spring Boot manages compatible versions through Boot's dependency management. Do not arbitrarily mix Spring Data Elasticsearch, Elasticsearch Java client, and Spring Boot versions.

When Reactor is on the classpath, Spring Boot supports the reactive client and ReactiveElasticsearchTemplate alongside appropriate imperative components. Default repository scanning relies on auto-configuration packages, typically starting from the package of the SpringBootApplication class.

Example:

~~~java
@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

If the application class resides in the root package com.example.catalog, repository subpackages are usually detected via auto-configuration. When the package structure is non-standard or you need to restrict scanning, use EnableReactiveElasticsearchRepositories explicitly.

You can disable repository auto-configuration using the property:

~~~properties
spring.data.elasticsearch.repositories.enabled=false
~~~

Only disable it when the application manages repository configuration manually or you do not want Spring Boot to register repository beans.

## 19. Combining Reactive and Imperative Repositories

An application can contain both imperative and reactive repositories, but packages should be clearly separated:

~~~text
com.example.catalog
    imperative
        repository
            LegacyProductRepository
    reactive
        repository
            ProductRepository
    config
        ImperativeRepositoryConfig
        ReactiveRepositoryConfig
~~~

Configuration example:

~~~java
@Configuration
@EnableElasticsearchRepositories(
        basePackages = "com.example.catalog.imperative.repository")
class ImperativeRepositoryConfig {
}
~~~

~~~java
@Configuration
@EnableReactiveElasticsearchRepositories(
        basePackages = "com.example.catalog.reactive.repository")
class ReactiveRepositoryConfig {
}
~~~

Both repository groups can access the same Elasticsearch cluster, while each uses the operations/template matching its programming model.

Do not let both registrars scan the same repository package indiscriminately. When multiple Spring Data modules are present, use distinct packages and store-specific repository base interfaces so repositories are not bound to the wrong store or registered twice.

Do not call an imperative repository on a reactive request path and wrap the result in Mono.just. The imperative call already blocks before the Mono is created:

~~~java
Mono<Product> wrong = Mono.just(blockingRepository.findById("p-100").orElseThrow());
~~~

If integrating a blocking API is unavoidable, move it off the event loop onto an appropriate scheduler and limit concurrency. Better yet, use reactive APIs end-to-end when the system adopts the reactive stack.

## 20. Using ReactiveElasticsearchOperations for Dynamic Queries

Repository methods fit fixed queries or queries derivable from method names. When a query is built from multiple request-dependent conditions, use ReactiveElasticsearchOperations.

Service skeleton example:

~~~java
import org.springframework.data.elasticsearch.core.ReactiveElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;

public class DynamicProductSearch {

    private final ReactiveElasticsearchOperations operations;

    public DynamicProductSearch(ReactiveElasticsearchOperations operations) {
        this.operations = operations;
    }

    public Flux<Product> findByCategory(String category) {
        CriteriaQuery query = new CriteriaQuery(
                Criteria.where("category").is(category));

        return operations.search(
                        query,
                        Product.class,
                        IndexCoordinates.of("products"))
                .map(SearchHit::getContent);
    }
}
~~~

ReactiveElasticsearchOperations returns publishers for search results. The application can map SearchHit to the entity or keep hit metadata if score, highlights, sort values, or aggregations are needed.

## 21. Custom Repository Implementations

If a repository needs a specialized query without placing the logic into a service, you can use a custom repository fragment. The implementation can inject ReactiveElasticsearchOperations and return Mono/Flux.

Fragment interface:

~~~java
public interface ProductSearchRepository {
    Flux<Product> searchByText(String text);
}
~~~

Main repository:

~~~java
public interface ProductRepository
        extends ReactiveElasticsearchRepository<Product, String>,
                ProductSearchRepository {
}
~~~

Implementation:

~~~java
public class ProductSearchRepositoryImpl
        implements ProductSearchRepository {

    private final ReactiveElasticsearchOperations operations;

    public ProductSearchRepositoryImpl(
            ReactiveElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public Flux<Product> searchByText(String text) {
        CriteriaQuery query = new CriteriaQuery(
                Criteria.where("name").contains(text));

        return operations.search(
                        query,
                        Product.class,
                        IndexCoordinates.of("products"))
                .map(SearchHit::getContent);
    }
}
~~~

The implementation name must match the repository fragment convention and configured postfix. When using custom repository implementations, ensure the class is located in a package discoverable by the repository infrastructure.

## 22. Testing Reactive Repositories

With Reactor, StepVerifier helps verify publishers without blocking:

~~~java
import reactor.test.StepVerifier;

@Test
void findsProductById() {
    Mono<Product> result = repository.findById("p-100");

    StepVerifier.create(result)
            .expectNextMatches(product ->
                    product.getId().equals("p-100"))
            .verifyComplete();
}
~~~

Testing a Flux:

~~~java
@Test
void findsProductsByCategory() {
    Flux<Product> result = repository.findByCategory("accessories");

    StepVerifier.create(result)
            .expectNextCount(2)
            .verifyComplete();
}
~~~

Testing saving an entity:

~~~java
@Test
void savesProduct() {
    Product product = new Product(
            "p-100",
            "Wireless Keyboard",
            "accessories",
            1299000L);

    StepVerifier.create(repository.save(product))
            .expectNextMatches(saved ->
                    saved.getId().equals("p-100"))
            .verifyComplete();
}
~~~

These examples assume the index and an Elasticsearch test instance are already initialized. Integration tests should use an Elasticsearch version compatible with the Spring Data version in use, such as a container in the test environment, and explicitly manage index setup and cleanup.

### 22.1. Testing Repository Scanning

If the repository is not injected:

- Start the Spring ApplicationContext in a test.
- Confirm the ProductRepository bean exists.
- Verify the package falls under basePackages/basePackageClasses.
- Verify the ReactiveElasticsearchOperations bean is created.
- Verify reactiveElasticsearchTemplateRef points to the right bean.

Do not merely mock ProductRepository in a service unit test if your goal is verifying repository scanning; mocks do not exercise the repository infrastructure.

## 23. Common Pitfalls

### ReactiveElasticsearchRepository Bean Not Found

Usually caused by repository scanning not being enabled, scan packages not covering the repository interface, or configuration only enabling imperative EnableElasticsearchRepositories.

Check EnableReactiveElasticsearchRepositories and basePackages/basePackageClasses.

### Placing the Configuration Class in a Subpackage and Forgetting Sibling Packages

If no package is specified, Spring only scans the configuration class's package and its subpackages. Repositories in sibling packages will not be discovered.

### Binding a Reactive Repository to an Imperative Template

Reactive repositories require ReactiveElasticsearchOperations. If multiple templates exist, configure reactiveElasticsearchTemplateRef to reference the right bean.

### Calling subscribe Inside a Service

Subscribing manually detaches results and errors from the caller. Return Mono/Flux so the framework or outer layer subscribes.

### Calling block in WebFlux

block stalls the thread and can throw errors when executed on a Reactor non-blocking thread. Keep the reactive chain intact or move blocking integrations onto a dedicated scheduler at an appropriate boundary.

### Using List or Page for Reactive Finders

Reactive query methods typically return Flux or Mono. Pageable can be a parameter, but the return type remains Flux; if a total count is needed, compose a separate count query.

### Using collectList for Large Datasets

collectList buffers all elements onto the heap. Continue processing as a Flux and cap concurrency and buffering.

### Assuming Flux Automatically Guarantees Appropriate Pacing

Backpressure only helps when the entire publisher chain and integrations properly support it. Control concurrency, buffers, and queues at system boundaries.

### Using Legacy Reactive Client Configuration

The legacy RestClient configuration has been deprecated since Spring Data Elasticsearch 6.0. In the current stack, use ReactiveElasticsearchConfiguration and the corresponding client transport.

### Using the Wrong ID Type

Elasticsearch document IDs are strings. Using String as the ID property keeps mapping and repository generics consistent.

### Scanning the Same Package with Both Registrars

Imperative and reactive repository infrastructures serve different models. Separate packages and explicitly assign base packages for each registrar to avoid duplicate registration or binding the wrong operations bean.

## 24. Checklist for Setting Up ReactiveElasticsearchRepository

When adding reactive repositories to an application:

1. Choose the reactive stack for the request path and ensure Reactor is on the classpath.
2. Add the Spring Data Elasticsearch dependency compatible with your Spring Boot release train.
3. Declare entities with Document, Id, and appropriate field mappings.
4. Create a repository interface extending ReactiveElasticsearchRepository<Entity, String>.
5. Choose Spring Boot auto-configuration or configure the client via ReactiveElasticsearchConfiguration.
6. Enable EnableReactiveElasticsearchRepositories if explicit scanning is needed.
7. Specify basePackages or basePackageClasses matching the repository packages.
8. Confirm the ReactiveElasticsearchOperations bean exists and repositories use the right template.
9. Write finder methods returning Mono/Flux and use @Query when custom Query DSL is required.
10. Inject the repository into reactive services/controllers and return publishers directly.
11. Never call subscribe or block in WebFlux request flows.
12. Cap concurrency and avoid collecting large datasets into a List.
13. Use StepVerifier and integration tests to verify queries, mappings, and repository scanning.
14. Monitor errors, latency, memory, queues, and Elasticsearch load in production.

## 25. Summary

ReactiveElasticsearchRepository is Spring Data Elasticsearch's repository abstraction powered by Project Reactor. This interface extends ReactiveCrudRepository and ReactiveSortingRepository, providing CRUD, sorting, and query methods as Mono or Flux. Derived query methods, Pageable, Sort, and @Query are all supported; when dynamic queries are needed, ReactiveElasticsearchOperations can be used.

Repository scanning is activated with EnableReactiveElasticsearchRepositories. If no package is specified, Spring scans the configuration class's package and its subpackages. You can use basePackages or basePackageClasses to define the scope explicitly; reactiveElasticsearchTemplateRef selects the ReactiveElasticsearchOperations bean used by the repositories. Repository scanning is a dedicated mechanism, distinct from ComponentScan or creating entity beans.

With Spring Boot, the reactive client and template can be auto-configured when compatible dependencies are on the classpath. When configuring manually in current Spring Data Elasticsearch, use ReactiveElasticsearchConfiguration. Keep the reactive chain intact end-to-end, return publishers to callers, avoid block/subscribe inside services, and control backpressure when processing large streams. Separating reactive and imperative packages clearly ensures repositories are discovered and bound to the right operations bean.

## References

- [Spring Data Elasticsearch – Reactive Elasticsearch Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories/reactive-elasticsearch-repositories.html)
- [Spring Data Elasticsearch – ReactiveElasticsearchRepository API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/repository/ReactiveElasticsearchRepository.html)
- [Spring Data Elasticsearch – EnableReactiveElasticsearchRepositories API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/repository/config/EnableReactiveElasticsearchRepositories.html)
- [Spring Data Elasticsearch – ReactiveElasticsearchConfiguration API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/ReactiveElasticsearchConfiguration.html)
- [Spring Data Elasticsearch – Elasticsearch Clients](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/clients.html)
- [Spring Boot – NoSQL and Elasticsearch](https://docs.spring.io/spring-boot/reference/data/nosql.html)
- [Project Reactor – Reference Guide](https://projectreactor.io/docs/core/release/reference/)
