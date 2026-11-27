# Injecting ElasticsearchOperations or ReactiveElasticsearchOperations

When a repository method needs a complex query, multi-step processing, or operations that do not fit derived query methods, Spring Data Elasticsearch allows adding a custom repository implementation. Inside that implementation, the application can inject `ElasticsearchOperations` or `ReactiveElasticsearchOperations` to work directly with Elasticsearch through Spring Data's abstractions.

`ElasticsearchOperations` is the imperative API: methods typically return immediate results such as `SearchHits<T>`, entities, or response objects. `ReactiveElasticsearchOperations` is the reactive API: methods return publishers such as `Mono<T>` or `Flux<SearchHit<T>>`. These two interfaces serve different programming models and cannot be swapped simply by renaming a variable.

This lesson explains how to create a repository fragment, inject operations via constructor injection, write custom queries, select the right bean when an application has multiple Elasticsearch templates, structure reactive implementations, and handle common wiring errors.

## 1. Why Does a Custom Repository Need ElasticsearchOperations?

Spring Data repositories already provide CRUD and query methods derived from method names. For example:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByCategory(String category);
}
~~~

For simple queries, this is usually enough. However, some requirements demand greater control:

- Combining multiple dynamic conditions based on request parameters.
- Using specific Query DSL constructs that query derivation cannot express clearly.
- Combining search, aggregations, highlighting, or hit metadata.
- Executing multiple Elasticsearch operations within a single business-level method.
- Using `ElasticsearchOperations` or `ReactiveElasticsearchOperations` APIs that the repository interface does not expose directly.
- Reusing search logic across multiple repositories.

Instead of pushing all logic into a service or creating a separate client, you can write a custom repository fragment and inject operations into its implementation.

~~~text
ProductRepository
       |
       +---- ElasticsearchRepository<Product, String>
       |            CRUD and query methods
       |
       +---- ProductSearchRepository
                    custom search contract
                          |
                          v
              ProductSearchRepositoryImpl
                          |
                          v
               ElasticsearchOperations
                          |
                          v
                    Elasticsearch
~~~

Spring Data composes the fragments into a single repository proxy. Clients simply inject `ProductRepository` and call both CRUD and custom methods.

## 2. Distinguishing the Two Operations Interfaces

Spring Data Elasticsearch provides two abstractions:

| Interface | Programming style | Common search return type |
|---|---|---|
| `ElasticsearchOperations` | Imperative, blocking | `SearchHits<T>` |
| `ReactiveElasticsearchOperations` | Reactive, non-blocking | `Flux<SearchHit<T>>` or `Mono<ReactiveSearchHits<T>>` |

Both interfaces offer corresponding feature groups—document operations, search, queries, aggregations, and index management—but their method signatures and result consumption patterns differ.

### 2.1. ElasticsearchOperations

`ElasticsearchOperations` is the umbrella interface for imperative operations. It provides APIs such as:

- `save(...)`, `get(...)`, `delete(...)`.
- `search(...)`, `searchOne(...)`, `searchForStream(...)`.
- `count(...)`, `exists(...)`.
- `indexOps(...)` for metadata/index operations.
- `update(...)`, bulk operations, and other query operations.

Example:

~~~java
SearchHits<Product> hits = operations.search(
        query,
        Product.class,
        IndexCoordinates.of("products"));
~~~

The call returns once the synchronous operation completes. If invoked from a WebFlux event-loop, this API can block threads; do not use it directly on reactive request paths.

### 2.2. ReactiveElasticsearchOperations

`ReactiveElasticsearchOperations` provides reactive operations. Example:

~~~java
Flux<SearchHit<Product>> hits = reactiveOperations.search(
        query,
        Product.class,
        IndexCoordinates.of("products"));
~~~

The publisher only describes the operation until a subscription occurs. Once downstream subscribes, the request executes and `SearchHit<Product>` items are emitted sequentially.

Some methods return full search metadata:

~~~java
Mono<ReactiveSearchHits<Product>> result =
        reactiveOperations.searchForHits(
                query,
                Product.class,
                IndexCoordinates.of("products"));
~~~

`ReactiveSearchHits<T>` holds search metadata and exposes a publisher of hits via `getSearchHits()`.

### 2.3. Do Not Inject the Wrong Operations Type

You cannot assign `ReactiveElasticsearchOperations` to an `ElasticsearchOperations` variable or vice versa. They are separate abstractions.

An imperative custom fragment should inject `ElasticsearchOperations`. A reactive custom fragment should inject `ReactiveElasticsearchOperations`. If an application uses both stacks, place implementations in appropriate packages or modules and keep constructor types explicit about their requirements.

## 3. What Is a Repository Fragment?

Spring Data builds repositories from multiple fragments. A fragment consists of:

1. An interface declaring custom functionality.
2. An implementation class executing that interface.

The main repository extends the fragment interface. Spring Data composes the fragment into the repository proxy when initializing the repository.

Example interface:

~~~java
package com.example.catalog.repository;

public interface ProductSearchRepository {

    List<Product> searchByText(String text);
}
~~~

Implementation:

~~~java
package com.example.catalog.repository;

public class ProductSearchRepositoryImpl
        implements ProductSearchRepository {

    // Implementation is added in the next sections.
}
~~~

The default implementation class name is the fragment interface name plus the `Impl` suffix: `ProductSearchRepository` → `ProductSearchRepositoryImpl`.

Main repository:

~~~java
package com.example.catalog.repository;

import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

import com.example.catalog.domain.Product;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                ProductSearchRepository {
}
~~~

When Spring creates `ProductRepository`, the proxy includes both CRUD methods from `ElasticsearchRepository` and `searchByText` from the fragment.

## 4. Injecting ElasticsearchOperations via Constructor Injection

A custom fragment implementation is a bean discovered and registered by the repository infrastructure. It can use standard Spring dependency injection. The recommended approach is constructor injection:

~~~java
package com.example.catalog.repository;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;

public class ProductSearchRepositoryImpl
        implements ProductSearchRepository {

    private final ElasticsearchOperations operations;

    public ProductSearchRepositoryImpl(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    // Custom methods use operations here.
}
~~~

Spring locates a matching bean of type `ElasticsearchOperations` and passes it to the constructor when instantiating the fragment implementation. Because the field is declared `final`, the dependency is always present once the object is constructed.

Benefits of constructor injection:

- Makes required dependencies explicit in the constructor signature.
- Simplifies writing unit tests with mock or fake operations.
- Supports immutable objects after initialization.
- Avoids a partially initialized state where an `@Autowired` field is not yet assigned.
- Catches missing-bean or ambiguous-bean errors early at startup.

With a single constructor, Spring does not require the `@Autowired` annotation on the constructor.

### 4.1. Do Not Instantiate ElasticsearchOperations Manually in a Fragment

Do not create a new client or template inside the implementation:

~~~java
// Avoid creating a new client/template for every repository fragment.
public ProductSearchRepositoryImpl() {
    // new ElasticsearchClient(...)
    // new ElasticsearchTemplate(...)
}
~~~

Inject the operations bean managed by Spring configuration. The shared template uses the application's configured connections, converters, mapping context, callbacks, and other integration components.

### 4.2. Do Not Inject the Repository into Its Own Fragment

Avoid creating a circular dependency like this:

~~~java
public ProductSearchRepositoryImpl(ProductRepository repository) {
    // ProductRepository itself includes this fragment.
}
~~~

`ProductRepository` is assembled by composing `ProductSearchRepositoryImpl`. If the implementation in turn requires `ProductRepository` itself, Spring may encounter a circular dependency or fail to build the proxy.

Fragments should depend on `ElasticsearchOperations`, `ReactiveElasticsearchOperations`, or other services that do not depend back on that repository proxy.

## 5. Writing a Custom Search Using ElasticsearchOperations

Example of searching products by name with `CriteriaQuery`:

~~~java
package com.example.catalog.repository;

import java.util.List;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;

import com.example.catalog.domain.Product;

public class ProductSearchRepositoryImpl
        implements ProductSearchRepository {

    private final ElasticsearchOperations operations;

    public ProductSearchRepositoryImpl(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public List<Product> searchByText(String text) {
        Criteria criteria = Criteria.where("name").contains(text);
        CriteriaQuery query = new CriteriaQuery(criteria);

        SearchHits<Product> hits = operations.search(
                query,
                Product.class,
                IndexCoordinates.of("products"));

        return hits.getSearchHits().stream()
                .map(SearchHit::getContent)
                .toList();
    }
}
~~~

In this example:

- `Criteria` represents the search condition.
- `CriteriaQuery` wraps the query for Spring Data.
- `Product.class` supplies the domain type for mapping.
- `IndexCoordinates.of("products")` specifies the target index.
- `SearchHits<Product>` holds metadata for the entire search response.
- `SearchHit::getContent` extracts the entity from each hit.

If you need scores, highlights, or sort values, return `SearchHits<Product>` or a DTO mapped from each `SearchHit` rather than returning only `List<Product>`.

### 5.1. Using NativeQuery When Specific Query DSL Is Needed

When a query requires multiple Elasticsearch-specific conditions, you can use `NativeQuery`:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
                .bool(b -> b
                        .must(m -> m
                                .match(match -> match
                                        .field("name")
                                        .query(text)))
                        .filter(f -> f
                                .term(term -> term
                                        .field("active")
                                        .value(true)))))
        .build();

SearchHits<Product> hits = operations.search(
        query,
        Product.class,
        IndexCoordinates.of("products"));
~~~

`NativeQuery` allows building queries with Elasticsearch Java API Client builders. `ElasticsearchOperations` still handles execution and mapping results back to the domain type.

Use CriteriaQuery when conditions are simple and clearly expressed with the Criteria API. Use NativeQuery when you need specific Query DSL constructs or client APIs.

### 5.2. Preserving SearchHit Metadata

If the custom method needs to return both entities and scores:

~~~java
public interface ProductSearchRepository {
    SearchHits<Product> searchWithMetadata(String text);
}
~~~

Implementation:

~~~java
@Override
public SearchHits<Product> searchWithMetadata(String text) {
    CriteriaQuery query = new CriteriaQuery(
            Criteria.where("name").contains(text));

    return operations.search(
            query,
            Product.class,
            IndexCoordinates.of("products"));
}
~~~

The service layer can inspect `hits.getTotalHits()`, `hits.getMaxScore()`, and `hit.getScore()`, or highlight fields if highlighting was enabled on the query.

## 6. Using the Fragment in Services and Controllers

The service only needs to inject the composed repository:

~~~java
@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public List<Product> search(String text) {
        return repository.searchByText(text);
    }
}
~~~

The controller does not need to know which operations interface the custom fragment uses:

~~~java
@RestController
@RequestMapping("/products")
public class ProductController {

    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping("/search")
    public List<Product> search(@RequestParam String q) {
        return service.search(q);
    }
}
~~~

Dependency flow:

~~~text
Controller
    |
    v
ProductService
    |
    v
ProductRepository proxy
    |
    +---- ElasticsearchRepository base implementation
    |
    +---- ProductSearchRepositoryImpl
                  |
                  v
          ElasticsearchOperations
                  |
                  v
             Elasticsearch
~~~

Services and controllers depend on the repository contract. Only the custom implementation depends directly on operations.

## 7. Injecting ReactiveElasticsearchOperations

For reactive applications, define a fragment returning publishers:

~~~java
package com.example.catalog.repository;

import reactor.core.publisher.Flux;

import com.example.catalog.domain.Product;

public interface ReactiveProductSearchRepository {

    Flux<Product> searchByText(String text);
}
~~~

Main repository:

~~~java
import org.springframework.data.elasticsearch.repository.ReactiveElasticsearchRepository;

public interface ReactiveProductRepository
        extends ReactiveElasticsearchRepository<Product, String>,
                ReactiveProductSearchRepository {
}
~~~

The implementation injects `ReactiveElasticsearchOperations`:

~~~java
package com.example.catalog.repository;

import org.springframework.data.elasticsearch.core.ReactiveElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;

import reactor.core.publisher.Flux;

import com.example.catalog.domain.Product;

public class ReactiveProductSearchRepositoryImpl
        implements ReactiveProductSearchRepository {

    private final ReactiveElasticsearchOperations operations;

    public ReactiveProductSearchRepositoryImpl(
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

`ReactiveElasticsearchOperations.search(...)` returns `Flux<SearchHit<Product>>`. The custom method maps each hit to its entity while preserving the reactive publisher.

Do not call `.block()` or `.subscribe()` inside the fragment. Return `Flux<Product>` to the repository caller so WebFlux or outer layers manage subscription and cancellation.

### 7.1. Returning Metadata with ReactiveSearchHits

If you need total hits or search metadata, define the fragment to return `Mono<ReactiveSearchHits<Product>>`:

~~~java
import org.springframework.data.elasticsearch.core.ReactiveSearchHits;

public interface ReactiveProductSearchRepository {
    Mono<ReactiveSearchHits<Product>> searchWithMetadata(String text);
}
~~~

Implementation:

~~~java
@Override
public Mono<ReactiveSearchHits<Product>> searchWithMetadata(String text) {
    CriteriaQuery query = new CriteriaQuery(
            Criteria.where("name").contains(text));

    return operations.searchForHits(
            query,
            Product.class,
            IndexCoordinates.of("products"));
}
~~~

Callers can retrieve the hit publisher:

~~~java
return repository.searchWithMetadata(text)
        .flatMapMany(ReactiveSearchHits::getSearchHits)
        .map(SearchHit::getContent);
~~~

`search(...)` fits when you only need a stream of hits. `searchForHits(...)` fits when you need the overall search response metadata object.

## 8. Constructor Injection with Multiple Operations Beans

In simple applications, Spring usually has one `ElasticsearchOperations` bean and one `ReactiveElasticsearchOperations` bean. Constructor injection by type can automatically resolve the appropriate bean.

When an application has multiple clusters, multiple index templates, or multiple operations beans of the same type, you must specify the exact bean with `@Qualifier`.

Example:

~~~java
public ProductSearchRepositoryImpl(
        @Qualifier("catalogElasticsearchOperations")
        ElasticsearchOperations operations) {
    this.operations = operations;
}
~~~

For reactive:

~~~java
public ReactiveProductSearchRepositoryImpl(
        @Qualifier("catalogReactiveElasticsearchOperations")
        ReactiveElasticsearchOperations operations) {
    this.operations = operations;
}
~~~

The qualifier name must match the bean name declared in the Spring context. Do not use an index name as a qualifier; bean names and index names are separate concepts.

### 8.1. Declaring Multiple Imperative Operations Beans

Example configuration with two clusters/templates:

~~~java
@Configuration
public class ElasticsearchOperationsConfiguration {

    @Bean("catalogElasticsearchOperations")
    ElasticsearchOperations catalogOperations(
            ElasticsearchClient catalogClient,
            ElasticsearchConverter converter) {
        return new ElasticsearchTemplate(catalogClient, converter);
    }

    @Bean("auditElasticsearchOperations")
    ElasticsearchOperations auditOperations(
            ElasticsearchClient auditClient,
            ElasticsearchConverter converter) {
        return new ElasticsearchTemplate(auditClient, converter);
    }
}
~~~

This is a structural example; exact constructors and client creation depend on your application's Spring Data Elasticsearch / client version. In real systems, each template must be wired to the matching cluster's client, converter, and mapping context.

Custom fragment:

~~~java
public ProductSearchRepositoryImpl(
        @Qualifier("catalogElasticsearchOperations")
        ElasticsearchOperations operations) {
    this.operations = operations;
}
~~~

### 8.2. Primary Bean

If one operations bean should be the default for unqualified dependencies, mark it with `@Primary`:

~~~java
@Bean
@Primary
ElasticsearchOperations defaultElasticsearchOperations(...) {
    // Create the default template.
}
~~~

`@Primary` resolves default type-based selection. When a fragment targets a specific cluster, still use `@Qualifier` to make the intent explicit.

### 8.3. Default Bean Names and Repository Infrastructure

Spring Data repository infrastructure requires the corresponding operations/template bean to create repository proxies:

| Repository infrastructure | Default operations bean |
|---|---|
| `@EnableElasticsearchRepositories` | `elasticsearchTemplate` |
| `@EnableReactiveElasticsearchRepositories` | `reactiveElasticsearchTemplate` |

When using multiple repository configurations or multiple clusters, configure each registrar so repositories use the right template. Injecting operations directly into a custom fragment and selecting the underlying template for the repository proxy are two separate wiring points that must stay consistent.

## 9. Configuring Repositories for Multiple Clusters

When there are multiple Elasticsearch clusters, you can split repository packages:

~~~text
com.example.catalog
    catalog
        repository
            ProductRepository
            ProductSearchRepository
            ProductSearchRepositoryImpl
        config
            CatalogElasticsearchConfig
    audit
        repository
            AuditRepository
        config
            AuditElasticsearchConfig
~~~

Each configuration enables repository scanning for its corresponding package and references the appropriate template:

~~~java
@Configuration
@EnableElasticsearchRepositories(
        basePackages = "com.example.catalog.catalog.repository",
        elasticsearchTemplateRef = "catalogElasticsearchTemplate")
public class CatalogRepositoryConfig {
}
~~~

~~~java
@Configuration
@EnableElasticsearchRepositories(
        basePackages = "com.example.catalog.audit.repository",
        elasticsearchTemplateRef = "auditElasticsearchTemplate")
public class AuditRepositoryConfig {
}
~~~

The template reference attribute is used in imperative repository configuration. For reactive repositories, use `@EnableReactiveElasticsearchRepositories` and `reactiveElasticsearchTemplateRef`.

Custom fragments in the catalog package must inject `catalogElasticsearchOperations` or the corresponding bean. Do not let a fragment use the audit cluster simply because that bean was marked Primary.

## 10. Discovery and Naming of Custom Fragments

Repository infrastructure locates fragment implementations within the scanned repository package scope. By default, implementations carry the `Impl` suffix.

Example:

~~~text
ProductSearchRepository
ProductSearchRepositoryImpl
ProductRepository
~~~

Interfaces and implementations should reside in the same package or in locations discoverable by repository scanning according to Spring Data's rules.

### 10.1. Customizing the Postfix

You can change the suffix in the repository configuration:

~~~java
@EnableElasticsearchRepositories(
        basePackages = "com.example.catalog.repository",
        repositoryImplementationPostfix = "Custom")
~~~

With the `Custom` postfix, Spring looks for `ProductSearchRepositoryCustom` instead of `ProductSearchRepositoryImpl`.

Reactive repository configuration has a corresponding postfix attribute. If you change the postfix, ensure all fragment implementations follow the configured naming convention.

### 10.2. Do Not Confuse Fragment Implementations with Legacy RepositoryName + Impl

Previously, Spring Data commonly looked for a class named after the main repository plus `Impl`, such as `ProductRepositoryImpl`. This single-custom-implementation approach has been deprecated in current Spring Data documentation; use a dedicated fragment interface and name the implementation after the fragment.

Recommended model:

~~~text
ProductRepository
    extends ElasticsearchRepository
    extends ProductSearchRepository

ProductSearchRepositoryImpl
    implements ProductSearchRepository
    injects ElasticsearchOperations
~~~

The fragment model separates custom behavior into independent parts that can be reused and combined across a repository.

### 10.3. Do You Need `@Component` or `@Repository`?

Fragment implementations are discovered and registered by the repository infrastructure by convention. Normally, you do not need to add `@Component` just for the fragment to be found.

If registering a bean manually for special wiring needs, the bean name must match the fragment interface plus postfix convention so the infrastructure links the right implementation. Avoid both declaring a bean manually and letting component scanning create a second bean of the same class under another name.

## 11. Reusing a Fragment Across Multiple Repositories

A fragment interface can be extended by multiple repositories:

~~~java
public interface TextSearchFragment<T> {
    SearchHits<T> searchText(String text, Class<T> type, String indexName);
}
~~~

Generic implementation:

~~~java
public class TextSearchFragmentImpl<T>
        implements TextSearchFragment<T> {

    private final ElasticsearchOperations operations;

    public TextSearchFragmentImpl(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public SearchHits<T> searchText(
            String text,
            Class<T> type,
            String indexName) {

        CriteriaQuery query = new CriteriaQuery(
                Criteria.where("name").contains(text));

        return operations.search(
                query,
                type,
                IndexCoordinates.of(indexName));
    }
}
~~~

Two repositories can both extend the fragment:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                TextSearchFragment<Product> {
}

public interface ArticleRepository
        extends ElasticsearchRepository<Article, String>,
                TextSearchFragment<Article> {
}
~~~

In production code, generic fragments must be named and organized so Spring Data can resolve the right implementation. If a generic fragment is contributed from an external module/library or resides outside the repository base package, it may need to be registered via a fragment registration mechanism such as `spring.factories` according to Spring Data documentation.

If the index name can be obtained from entity metadata or `@Document`, avoid accepting arbitrary index names from external requests. Only allow indexes configured by the application.

## 12. Custom Fragments with Multiple Dependencies

An implementation can inject multiple beans, not just ElasticsearchOperations:

~~~java
public class ProductSearchRepositoryImpl
        implements ProductSearchRepository {

    private final ElasticsearchOperations operations;
    private final ProductSearchPolicy policy;
    private final Clock clock;

    public ProductSearchRepositoryImpl(
            ElasticsearchOperations operations,
            ProductSearchPolicy policy,
            Clock clock) {
        this.operations = operations;
        this.policy = policy;
        this.clock = clock;
    }
}
~~~

For example:

- `ElasticsearchOperations` executes queries.
- `ProductSearchPolicy` applies filtering rules or result limits.
- `Clock` supplies the current time so tests remain deterministic.

A fragment is still a regular Spring bean, so it participates in dependency injection, AOP, and other bean mechanisms. Keep dependencies clear and avoid turning fragments into containers for all application business logic.

## 13. Testing Imperative Custom Repositories

You can unit test a fragment by mocking `ElasticsearchOperations`:

~~~java
@ExtendWith(MockitoExtension.class)
class ProductSearchRepositoryImplTest {

    @Mock
    ElasticsearchOperations operations;

    @Test
    void executesSearchAndReturnsContents() {
        Product product = new Product(
                "p-100",
                "Wireless Keyboard",
                "accessories");

        // Stub operations.search(...) with a SearchHits<Product> fixture.
        when(operations.search(
                any(Query.class),
                eq(Product.class),
                any(IndexCoordinates.class)))
                .thenReturn(searchHitsContaining(product));

        ProductSearchRepositoryImpl fragment =
                new ProductSearchRepositoryImpl(operations);

        List<Product> result = fragment.searchByText("keyboard");

        assertThat(result).containsExactly(product);
        verify(operations).search(
                any(Query.class),
                eq(Product.class),
                any(IndexCoordinates.class));
    }
}
~~~

This test illustrates mocking the contract and verifying the fragment calls operations. The helper `searchHitsContaining` is a test-created fixture to avoid coupling to specific `SearchHit`/`SearchHitsImpl` constructors across release trains.

Unit tests do not verify mappings or whether Elasticsearch accepts the Query DSL. Integration tests are needed to validate real queries.

## 14. Testing Reactive Fragments

Reactive operations should be mocked to return publishers:

~~~java
@ExtendWith(MockitoExtension.class)
class ReactiveProductSearchRepositoryImplTest {

    @Mock
    ReactiveElasticsearchOperations operations;

    @Test
    void mapsReactiveSearchHitsToProducts() {
        Product product = new Product(
                "p-100",
                "Wireless Keyboard",
                "accessories");

        SearchHit<Product> hit = createSearchHit(product);

        when(operations.search(
                any(Query.class),
                eq(Product.class),
                any(IndexCoordinates.class)))
                .thenReturn(Flux.just(hit));

        ReactiveProductSearchRepositoryImpl fragment =
                new ReactiveProductSearchRepositoryImpl(operations);

        StepVerifier.create(fragment.searchByText("keyboard"))
                .expectNext(product)
                .verifyComplete();
    }
}
~~~

`StepVerifier` verifies the publisher without calling `block()`. In integration tests, spin up a real reactive Elasticsearch client to validate queries and mappings.

## 15. Testing Repository Composition and Dependency Injection

Unit testing the implementation only verifies that the constructor receives operations. To check whether Spring Data discovers the fragment and wires it into the repository proxy, you need to start an ApplicationContext.

An integration test can:

1. Enable `@EnableElasticsearchRepositories` for the test package.
2. Provide an `ElasticsearchOperations` bean.
3. Initialize `ProductRepository`.
4. Autowire the repository proxy.
5. Invoke the custom method `searchByText`.
6. Verify the fragment implementation is called and results are mapped.

For reactive:

1. Enable `@EnableReactiveElasticsearchRepositories`.
2. Provide `ReactiveElasticsearchOperations`.
3. Initialize `ReactiveProductRepository`.
4. Invoke the custom method and verify with StepVerifier.

This test catches errors such as fragment implementations placed outside the scan package, wrong postfix names, missing operations beans, or misconfigured qualifiers.

## 16. Common Pitfalls When Injecting Operations

### Missing `ElasticsearchOperations` Bean

Causes may include unconfigured client/template, missing dependencies, or disabled auto-configuration. Verify that a bean of type `ElasticsearchOperations` exists in the Spring context.

### Multiple `ElasticsearchOperations` Beans

Spring cannot choose which bean to inject when multiple candidates exist without `@Primary` or `@Qualifier`. Add an explicit qualifier on the fragment constructor.

### Injecting Reactive Operations into an Imperative Fragment

These are distinct interfaces. Use the type matching the repository and the fragment's return types.

### Custom Implementation Not Discovered

Check that the fragment interface is extended by the main repository, that the implementation class uses the right postfix, and that it lies within the scanning scope.

### Using `ProductRepositoryImpl` Under the Legacy Convention

Prefer `ProductSearchRepository` + `ProductSearchRepositoryImpl`. The fragment model separates custom contracts from the main repository and is recommended in current documentation.

### Adding `@Component` and Creating Duplicate Beans

Fragment infrastructure already manages implementations by naming convention. If declaring components/beans manually, ensure bean names and registration do not create two competing instances.

### Circular Dependency Between Fragment and Repository Proxy

Do not inject the repository proxy into the fragment that forms part of that proxy. Inject operations or a lower-level dependency.

### Repository Using a Different Template Than the Fragment

In multi-cluster applications, the repository proxy and custom fragment can accidentally point to two different operations beans. Align template references and `@Qualifier` annotations consistently.

### Calling `block` in a Reactive Fragment

`ReactiveElasticsearchOperations` returns publishers. Do not block or subscribe inside a fragment; return the publisher to the caller.

### Using `ElasticsearchOperations` on a WebFlux Request Path

Imperative operations can block. For non-blocking processing, use reactive repositories and operations end to end.

### Instantiating Templates Inside the Constructor

Creating clients/templates manually scatters configuration and complicates connection management. Inject Spring-managed beans.

## 17. When to Use a Repository Fragment vs. Operations in a Service

Not every custom query requires a custom repository.

| Situation | Appropriate structure |
|---|---|
| Fixed query expressible by method name | Derived repository method |
| Static declarative Query DSL | `@Query` |
| Dynamic query used in a single use case | Service injects operations |
| Dynamic query tied to Product access responsibility | ProductSearchRepository fragment |
| Custom behavior reused across multiple repositories | Reusable fragment |
| Changing behavior across all repositories | Custom repository base class, when truly needed |
| Deep control over repository proxy creation | Repository factory customization |

Fragments fit when custom behavior belongs to the repository contract and needs independent reuse or testing. If a query only serves a single orchestration step inside a service, injecting operations directly into the service can be simpler.

Do not create a fragment merely to forward a one-line `operations.search(...)` call if it adds no abstraction or reuse.

## 18. Distinguishing Custom Fragments from Custom Base Repositories

A custom fragment adds a group of methods to a specific repository:

~~~java
public interface ProductSearchRepository {
    List<Product> searchByText(String text);
}
~~~

A custom base repository alters foundational behavior for every repository within the configuration scope. It typically extends the store's repository implementation class and is registered via `repositoryBaseClass`.

Do not use a custom base repository just to inject `ElasticsearchOperations` for one query. Fragments generally have lower coupling and compose more easily.

If you need to alter shared logic across all repositories, check the constructor required by the repository factory and supply the appropriate constructor and store infrastructure. This is a more advanced technique than fragment injection.

## 19. Implementation Workflow

When adding a custom repository that uses Elasticsearch operations:

1. Determine whether the query truly needs a custom implementation or can use a derived query or `@Query`.
2. Choose imperative or reactive according to your application stack.
3. Create a fragment interface declaring the custom methods.
4. Have the main repository extend the fragment interface.
5. Create the implementation class named after the fragment plus the `Impl` suffix.
6. Inject `ElasticsearchOperations` or `ReactiveElasticsearchOperations` via the constructor.
7. Use `IndexCoordinates` and query objects to specify target indexes and conditions.
8. Preserve the appropriate imperative or reactive return types.
9. If multiple operations beans exist, use `@Qualifier` and configure repository template references for the right cluster.
10. Place the fragment within the repository scan scope or register it via the appropriate fragment mechanism.
11. Unit test the implementation with mocked operations.
12. Integration test repository composition, bean injection, mappings, and real queries.
13. Avoid blocking/subscribing on reactive paths and avoid calling imperative operations on event loops.

## 20. Summary

Spring Data Elasticsearch custom repository implementations can inject `ElasticsearchOperations` or `ReactiveElasticsearchOperations` just like regular Spring beans. The recommended pattern is repository fragments: declare a custom interface, have the main repository extend that interface, and provide an implementation class named after the fragment plus the `Impl` suffix. Spring Data discovers and composes the fragment into the repository proxy.

For the imperative stack, inject `ElasticsearchOperations`; search methods return `SearchHits<T>` and run synchronously. For the reactive stack, inject `ReactiveElasticsearchOperations`; search methods return `Flux<SearchHit<T>>` or `Mono<ReactiveSearchHits<T>>`. Never mix the two abstractions or call block/subscribe inside a reactive fragment.

Constructor injection keeps required dependencies explicit, simplifies testing, and surfaces wiring errors at startup. When multiple operations beans exist, use `@Qualifier` and ensure the repository infrastructure also references the right template. Fragment implementations must sit inside the scan scope and follow naming conventions. Choose a fragment when custom behavior belongs to the data access contract; if a query is only used once inside a service, injecting operations directly into the service can be cleaner.

## References

- [Spring Data Elasticsearch – Custom Repository Implementations](https://docs.spring.io/spring-data/elasticsearch/reference/repositories/custom-implementations.html)
- [Spring Data Elasticsearch – ElasticsearchOperations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/ElasticsearchOperations.html)
- [Spring Data Elasticsearch – ReactiveElasticsearchOperations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/ReactiveElasticsearchOperations.html)
- [Spring Data Elasticsearch – SearchOperations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/SearchOperations.html)
- [Spring Data Elasticsearch – ReactiveSearchOperations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/ReactiveSearchOperations.html)
- [Spring Data Elasticsearch – Elasticsearch Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories.html)
