# Defining a Repository Fragment and Implementation Class

Spring Data repositories provide common operations out of the box, such as save, findById, delete, and query methods derived from method names. When an application needs custom behavior—such as combining multiple search conditions, calling ElasticsearchOperations, handling aggregations, or writing a specialized read model—you can extend the repository with a custom implementation.

Modern Spring Data organizes custom repositories using the **repository fragments** model. Each fragment is an independent piece of behavior consisting of an interface describing the API and a class implementing that interface. The main repository composes one or more fragments along with the repository base interface to form a complete proxy.

For example, ProductRepository can combine:

- ElasticsearchRepository for CRUD and standard query methods.
- ProductSearchFragment to provide advanced product search.
- ProductStatisticsFragment to provide custom aggregations or statistics.

Each fragment has its own responsibility and can be tested and reused independently. Spring Data assembles them into the repository proxy when initializing the application context.

## 1. What Is a Repository Fragment?

A repository fragment is a behavioral component that can be attached to a Spring Data repository. A fragment typically consists of two parts:

1. **Fragment interface:** declares the methods that the repository wants to expose.
2. **Fragment implementation:** a class implementing the declared methods.

Example:

~~~java
public interface ProductSearchFragment {

    List<Product> searchByTextAndBrand(
        String text,
        String brandId,
        Pageable pageable
    );
}
~~~

Implementation class:

~~~java
public class ProductSearchFragmentImpl
        implements ProductSearchFragment {

    private final ElasticsearchOperations operations;

    public ProductSearchFragmentImpl(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public List<Product> searchByTextAndBrand(
            String text,
            String brandId,
            Pageable pageable) {
        // Build the query and call ElasticsearchOperations.
        return List.of();
    }
}
~~~

The main repository extends the fragment interface:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                ProductSearchFragment {
}
~~~

When Spring Data creates the ProductRepository proxy, calls to searchByTextAndBrand are routed to ProductSearchFragmentImpl. CRUD methods continue to be handled by the repository base implementation.

A fragment is not an Elasticsearch index, mapping type, or sub-document. It is a way of organizing Java behavior at the repository layer.

## 2. What Components Make Up a Repository?

A Spring Data repository can be viewed as a composition of multiple components:

~~~text
ProductRepository
       |
       +-------------------------------+
       |                               |
       v                               v
ElasticsearchRepository       ProductSearchFragment
       |                               |
       v                               v
Repository base implementation ProductSearchFragmentImpl
       |
       v
CRUD and query infrastructure

       ProductRepository proxy
               |
               v
       Unified API for callers
~~~

Repository composition typically includes:

- **Repository base interface:** e.g., CrudRepository, PagingAndSortingRepository, or ElasticsearchRepository.
- **Repository base implementation:** provides default behavior such as save, findById, and delete.
- **Custom fragments:** interfaces and implementations that add business-oriented data access behaviors.
- **Repository aspects:** additional infrastructure components supported by Spring Data, depending on the store and configuration.

Callers simply inject ProductRepository. They do not need to instantiate ProductSearchFragmentImpl or know which fragment handles a given method.

### 2.1. Why Split Into Fragments?

A large repository can accumulate many different kinds of logic: advanced search, statistics, bulk updates, exports, synchronization, and data processing. Cramming everything into a single implementation class makes that class hard to test and hard to reuse.

Splitting into fragments helps because:

- Each fragment owns a cohesive group of related methods.
- Fragments can be reused across multiple repositories.
- Separate dependencies can be injected into each implementation.
- Implementations can be tested directly without booting a repository proxy.
- Part of the behavior can be changed without altering the entire repository.
- Default repository methods can be overridden when there is a clear need.

## 3. Fragment and Implementation Naming Conventions

Spring Data locates a fragment's implementation based on the interface name and the implementation postfix. The default postfix is Impl.

If a fragment interface is named ProductSearchFragment, the implementation class is typically named:

~~~text
ProductSearchFragment
ProductSearchFragmentImpl
~~~

Example:

~~~java
public interface ProductSearchFragment {
    List<Product> searchSimilar(String text);
}
~~~

~~~java
public class ProductSearchFragmentImpl
        implements ProductSearchFragment {

    @Override
    public List<Product> searchSimilar(String text) {
        // Custom implementation.
        return List.of();
    }
}
~~~

The implementation name is formed from the fragment interface name plus the postfix. If a repository combines multiple fragments, each fragment has a corresponding implementation.

### 3.1. Distinguishing Fragment Implementations from Repository-Named Implementations

There are two easily confused naming styles:

| Style | Interface | Default implementation |
| --- | --- | --- |
| Modern fragment | ProductSearchFragment | ProductSearchFragmentImpl |
| Legacy custom implementation tied directly to repository name | ProductRepository | ProductRepositoryImpl |

Modern Spring Data recommends the fragment model because it clarifies responsibility boundaries and allows composing multiple independent pieces.

Avoid creating ProductRepositoryImpl to hold every custom method if those methods can be split into clear fragments. The legacy implementation style may still appear in older projects, so understand the discovery mechanism accurately and avoid mixing the two styles unintentionally.

### 3.2. Changing the Implementation Postfix

The default postfix is Impl. A different postfix can be configured when enabling repository scanning:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.repository.config.EnableElasticsearchRepositories;

@Configuration
@EnableElasticsearchRepositories(
    basePackages = "com.example.catalog.repository",
    repositoryImplementationPostfix = "Custom"
)
public class ElasticsearchRepositoryConfiguration {
}
~~~

When using the Custom postfix, the implementation of ProductSearchFragment must be named:

~~~text
ProductSearchFragmentCustom
~~~

The fragment interface name remains ProductSearchFragment. Only the implementation suffix changes.

Only change the postfix when the project has an explicit convention for doing so. Otherwise, keeping Impl makes code easy to recognize and aligns with Spring Data's default convention.

## 4. Package Location and Discovery Mechanism

Spring Data needs to find the fragment implementation on the classpath. Typically, the implementation is placed in the same package as the repository interface or in a subpackage where repository scanning can detect it.

Example structure:

~~~text
com.example.catalog
|
+-- repository
|   |
|   +-- ProductRepository.java
|   +-- ProductSearchFragment.java
|   +-- ProductStatisticsFragment.java
|   |
|   +-- ProductSearchFragmentImpl.java
|   +-- ProductStatisticsFragmentImpl.java
|
+-- document
|   |
|   +-- Product.java
|
+-- service
    |
    +-- ProductCatalogService.java
~~~

You can organize fragment interfaces and implementations in subpackages as long as the scanning configuration covers those locations. What matters is that the implementation sits within the package scope discoverable by the repository infrastructure.

### 4.1. Repository Scanning

With Spring Boot, repository scanning is typically auto-configured based on the application class's package and Spring Data Elasticsearch configurations.

If declared manually:

~~~java
@Configuration
@EnableElasticsearchRepositories(
    basePackages = {
        "com.example.catalog.repository",
        "com.example.inventory.repository"
    }
)
public class RepositoryConfiguration {
}
~~~

Ensure the packages for both repositories and fragment implementations fall within the appropriate scope. If a repository is discovered but its fragment implementation is not found, custom methods may fail when invoked or the repository may fail to initialize due to a missing fragment implementation.

### 4.2. Dependency Injection in the Implementation

A fragment implementation is a Spring-managed component within repository composition. You can inject ElasticsearchOperations, converters, services, or other dependencies via its constructor.

~~~java
public class ProductSearchFragmentImpl
        implements ProductSearchFragment {

    private final ElasticsearchOperations operations;
    private final ProductSearchMapper mapper;

    public ProductSearchFragmentImpl(
            ElasticsearchOperations operations,
            ProductSearchMapper mapper) {
        this.operations = operations;
        this.mapper = mapper;
    }
}
~~~

Prefer constructor injection so dependencies are explicit and easy to test. Do not instantiate ElasticsearchClient or ElasticsearchOperations inside the implementation if the application already configures the corresponding beans.

If the implementation is discovered and registered by Spring Data via convention, do not register a second bean with a duplicate name for the same implementation. If the project registers beans manually, ensure bean names and discovery do not create two competing candidates.

## 5. Complete Example: Product Search Fragment

Suppose the Product document has the following fields:

~~~java
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
    private String brandId;

    @Field(type = FieldType.Double)
    private double price;

    // Constructors, getters, and setters
}
~~~

### 5.1. Declaring the Fragment Interface

~~~java
import java.util.List;

import org.springframework.data.domain.Pageable;

public interface ProductSearchFragment {

    List<Product> searchByTextAndBrand(
        String text,
        String brandId,
        Pageable pageable
    );
}
~~~

The fragment interface only declares the contract. It does not need to extend ElasticsearchRepository and does not need to know how queries are constructed.

### 5.2. Writing the Implementation

~~~java
import java.util.stream.Collectors;

import org.springframework.data.domain.Pageable;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;

public class ProductSearchFragmentImpl
        implements ProductSearchFragment {

    private final ElasticsearchOperations operations;

    public ProductSearchFragmentImpl(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public List<Product> searchByTextAndBrand(
            String text,
            String brandId,
            Pageable pageable) {

        NativeQuery query = NativeQuery.builder()
            .withQuery(q -> q
                .bool(b -> b
                    .must(m -> m
                        .match(mm -> mm
                            .field("name")
                            .query(text)
                        )
                    )
                    .filter(f -> f
                        .term(t -> t
                            .field("brandId")
                            .value(brandId)
                        )
                    )
                )
            )
            .withPageable(pageable)
            .build();

        SearchHits<Product> hits =
            operations.search(query, Product.class);

        return hits.getSearchHits()
            .stream()
            .map(SearchHit::getContent)
            .collect(Collectors.toList());
    }
}
~~~

The implementation uses ElasticsearchOperations to send a NativeQuery. The query combines:

- A match query on the name field for full-text search.
- A term filter on brandId for exact brand filtering.
- Pageable for pagination.

In this example, the implementation returns List<Product>. If callers need total hits, scores, highlights, or per-hit metadata, return SearchHits<Product> or a dedicated DTO instead of unwrapping only the content.

Field names in the query must match the Elasticsearch mapping. If the mapping uses a different field or customizes the field name with @Field(name = "..."), use the actual field name.

### 5.3. Composing the Fragment into the Repository

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                ProductSearchFragment {
}
~~~

The repository is used as a unified API:

~~~java
List<Product> products = productRepository.searchByTextAndBrand(
    "mechanical keyboard",
    "BRAND-10",
    PageRequest.of(0, 20)
);
~~~

Callers depend only on ProductRepository. Spring Data finds the fragment implementation and wires the method into the repository proxy.

## 6. Combining Multiple Fragments in One Repository

A single repository can compose multiple fragments:

~~~java
public interface ProductStatisticsFragment {

    long countByBrand(String brandId);

    Map<String, Long> countByCategory();
}
~~~

~~~java
public interface ProductBulkFragment {

    void reindexProducts(List<Product> products);
}
~~~

Repository:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                ProductSearchFragment,
                ProductStatisticsFragment,
                ProductBulkFragment {
}
~~~

Corresponding implementations:

~~~text
ProductSearchFragmentImpl
ProductStatisticsFragmentImpl
ProductBulkFragmentImpl
~~~

The repository proxy merges all fragments into a single API. ProductSearchFragmentImpl handles search; ProductStatisticsFragmentImpl handles aggregations; ProductBulkFragmentImpl handles bulk write flows.

### 6.1. Fragment Order When Method Signatures Collide

A repository can compose fragments that share matching method signatures. In composition, the declaration order of fragments in the repository interface matters for selecting the implementation. An earlier fragment has higher precedence than a later fragment when multiple fragments provide the same method.

Example:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                PreferredProductSearch,
                LegacyProductSearch {
}
~~~

If both PreferredProductSearch and LegacyProductSearch declare the method search(String), the fragment listed first takes precedence in composition. You should not rely on this behavior if the design can avoid duplicate methods; it is best to name methods distinctly or have only one fragment own a given contract.

Custom fragments can also be used to override methods from the repository base implementation. Therefore, check signatures and composition order if defining methods that collide with save, findById, or other built-in methods.

### 6.2. Avoiding Duplicate Implementation Names

If multiple fragment interfaces share the same simple name in different packages, conventional implementation classes can cause ambiguity during discovery.

Best practices:

- Name fragments specifically enough to avoid collisions.
- Keep repository packages clean and clear.
- Avoid two fragments with the same simple name in the same scanning scope.
- Use explicit bean names if the project needs to disambiguate multiple implementation candidates via Spring bean naming mechanisms supported by your version.

Do not resolve conflicts by creating multiple classes with the same name in the same package or relying on scan ordering.

## 7. Using a Fragment to Customize Inherited Methods

Fragments do not only add new methods. They can also provide an alternative implementation for a method that the repository already inherits.

For example, suppose an application wants to normalize an entity before saving or apply a custom write rule. You can declare a fragment with the same save signature:

~~~java
public interface CustomizedProductSave {

    <S extends Product> S save(S entity);
}
~~~

Implementation:

~~~java
public class CustomizedProductSaveImpl
        implements CustomizedProductSave {

    private final ElasticsearchOperations operations;

    public CustomizedProductSaveImpl(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public <S extends Product> S save(S entity) {
        entity.setName(entity.getName().trim());
        return operations.save(entity);
    }
}
~~~

Repository:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                CustomizedProductSave {
}
~~~

The custom fragment can take precedence over the base repository implementation and alter save behavior for that repository composition.

### 7.1. Be Careful with Method Signatures

When intending to override an inherited method, the signature must be compatible:

- Method name.
- Parameter count and types.
- Compatible return type.
- Generic type bounds.

If the signature differs, Spring Data may treat it as a new method rather than overriding the existing one. Verify both compile-time compatibility and integration behavior.

### 7.2. Do Not Call Back into the Repository to Avoid Recursion

Inside CustomizedProductSaveImpl, do not inject ProductRepository and call repository.save(entity). That call can be dispatched right back to the currently executing fragment, causing recursion.

Call ElasticsearchOperations directly or an appropriate service/base mechanism. If you need to preserve all default behavior of the base repository implementation and add extra logic around it, design the fragment so it does not invoke the overridden method on itself.

### 7.3. Overriding CRUD Methods Can Affect the Entire Repository

If a fragment overrides save, every call to save through that repository composition may execute the custom implementation. This affects services, batch jobs, and other components using the repository.

Only override CRUD methods when the new rule is genuinely part of the repository's universal contract. If you only need a specialized operation, adding a separately named method is safer and clearer.

## 8. Fragments Reusable Across Multiple Repositories

Fragments can be designed generically to support multiple domain types.

Example:

~~~java
public interface SearchByText<T> {

    List<T> searchText(String text, Pageable pageable);
}
~~~

Generic implementation:

~~~java
public class SearchByTextImpl<T>
        implements SearchByText<T> {

    private final ElasticsearchOperations operations;
    private final Class<T> entityType;

    public SearchByTextImpl(
            ElasticsearchOperations operations,
            Class<T> entityType) {
        this.operations = operations;
        this.entityType = entityType;
    }

    @Override
    public List<T> searchText(String text, Pageable pageable) {
        // Build query according to entityType's mapping.
        // This example omits the query construction logic.
        return List.of();
    }
}
~~~

A generic fragment can share the contract, but the implementation needs to know the concrete domain type to call operations.search and determine search fields. Providing Class<T> to a generic implementation may require a factory configuration or another design depending on how Spring Data resolves fragment instances.

A more practical approach is sharing a generic contract while providing dedicated implementations per entity when field mappings and search behaviors differ.

### 8.1. When Should You Make a Fragment Generic?

Use a generic fragment when:

- The behavior is genuinely identical across multiple entities.
- Entities follow a shared interface or field naming convention.
- Mappings and queries can be determined reliably.
- The implementation does not need aggregate-specific business rules.

Do not generalize just to save a few lines of code. Separate implementations for Product and Order can be far more readable than a generic fragment littered with class-based if/else branches.

## 9. Fragments vs. Custom Repository Base Classes

Spring Data also allows replacing the repository base implementation with a custom base class. This is a different mechanism from repository fragments.

| Repository fragment | Custom base class |
| --- | --- |
| Adds a slice of behavior with its own interface | Replaces the foundational repository implementation |
| Can compose multiple fragments | One base class applied per repository configuration |
| Suitable for independent capabilities | Suitable for shared behavior across many repositories |
| Reusable via composition | Usually applied broadly across a group of repositories |
| Can override methods via fragment | Can override base methods directly |

### 9.1. Custom Base Class Example

With Spring Data Elasticsearch, a custom base class can extend SimpleElasticsearchRepository and add shared behavior. Constructor names and APIs must match your Spring Data Elasticsearch version.

Conceptual example:

~~~java
public class CustomElasticsearchRepository<T, ID>
        extends SimpleElasticsearchRepository<T, ID> {

    public CustomElasticsearchRepository(
            ElasticsearchEntityInformation<T, ID> metadata,
            ElasticsearchOperations operations) {
        super(metadata, operations);
    }

    // Shared behavior for all repositories using this base class.
}
~~~

Repository factory configuration can specify the base class via the repositoryBaseClass attribute in @EnableElasticsearchRepositories:

~~~java
@EnableElasticsearchRepositories(
    basePackages = "com.example.catalog.repository",
    repositoryBaseClass = CustomElasticsearchRepository.class
)
~~~

This is an illustrative example. SimpleElasticsearchRepository and ElasticsearchEntityInformation constructors may vary by version. Check the exact API matching your project's dependencies before implementing.

Choose a custom base class when every repository in a configuration scope needs the same foundational change. Choose a fragment when only specific repositories need a particular capability.

## 10. Fragments vs. Query Methods and @Query

Not every custom query requires a fragment.

Spring Data Elasticsearch can generate queries from method names or use @Query for declarative queries. Fragments become useful when logic spans multiple steps or requires direct use of Elasticsearch Java API Client / ElasticsearchOperations APIs.

| Requirement | Appropriate approach |
| --- | --- |
| Search by simple fields | Derived query method |
| Fixed, concise query | @Query |
| Combining dynamic conditions, analyzing parameters | Repository fragment |
| Using aggregations or multiple requests | Repository fragment |
| Custom bulk/reindex handling | Repository fragment or dedicated service |
| Shared behavior across all repositories | Custom base class |

Example:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByBrandId(String brandId);
}
~~~

The method findByBrandId fits a derived query. If you need to search with multiple dynamic conditions, highlights, custom scoring, or multiple aggregations, a fragment will be much easier to manage.

## 11. Using ElasticsearchOperations Inside a Fragment

Fragment implementations commonly use ElasticsearchOperations to access lower-level capabilities than the repository abstraction provides.

Some capabilities include:

- Searching with NativeQuery.
- Aggregations and reading aggregation results.
- Indexing/updating/deleting documents with custom logic.
- Bulk operations.
- Querying with IndexCoordinates.
- Using SearchHits to retrieve scores, highlights, and metadata.

### 11.1. Keeping Mapping Consistent

When using ElasticsearchOperations with an entity class:

~~~java
SearchHits<Product> hits =
    operations.search(query, Product.class);
~~~

Spring Data uses Product's mapping metadata to convert source documents into entities.

If a query targets specific fields, the field names must match the Elasticsearch mapping. Do not assume Java property names always match index field names if the entity has custom mapping annotations.

### 11.2. Using IndexCoordinates When Needed

You can specify a concrete index:

~~~java
SearchHits<Product> hits = operations.search(
    query,
    Product.class,
    IndexCoordinates.of("products-read")
);
~~~

This is helpful when a repository needs to read from an alias or an index selected by tenant/partition. Carefully control the target index to avoid writing to an unintended index.

### 11.3. Do Not Put All Business Logic Inside a Fragment

A fragment should act as an adapter for data access behavior. Complex business rules—such as authorization checks, pricing calculations, state transitions, or coordinating multiple systems—generally belong in the service/domain layer.

A fragment can receive DTOs/query criteria prepared by a service, build the Elasticsearch request, and convert the results into an appropriate return type.

## 12. Reactive Repository Fragments

If an application uses ReactiveElasticsearchRepository or ReactiveElasticsearchOperations, fragments should also use the reactive API.

Example contract:

~~~java
public interface ReactiveProductSearchFragment {

    Flux<Product> searchByBrand(String brandId);
}
~~~

The implementation can inject ReactiveElasticsearchOperations:

~~~java
public class ReactiveProductSearchFragmentImpl
        implements ReactiveProductSearchFragment {

    private final ReactiveElasticsearchOperations operations;

    public ReactiveProductSearchFragmentImpl(
            ReactiveElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public Flux<Product> searchByBrand(String brandId) {
        // Build a reactive query and call operations.search(...).
        return Flux.empty();
    }
}
~~~

Repository:

~~~java
public interface ReactiveProductRepository
        extends ReactiveElasticsearchRepository<Product, String>,
                ReactiveProductSearchFragment {
}
~~~

Reactive implementations must return an appropriate Publisher type such as Mono or Flux. Do not call block() inside a fragment, as doing so defeats non-blocking execution and can cause deadlocks or stall event-loop threads.

Do not mix imperative and reactive APIs arbitrarily. Fragments designed for reactive repositories should use ReactiveElasticsearchOperations and reactive return types.

## 13. Testing Repository Fragments

Fragments can be tested in isolation because the implementation is a plain Java class receiving dependencies via constructor.

### 13.1. Unit Testing the Implementation

You can mock ElasticsearchOperations and verify that the fragment calls the right APIs:

~~~java
@ExtendWith(MockitoExtension.class)
class ProductSearchFragmentImplTest {

    @Mock
    ElasticsearchOperations operations;

    @Test
    void shouldExecuteSearch() {
        ProductSearchFragmentImpl fragment =
            new ProductSearchFragmentImpl(operations);

        // Set up mock SearchHits and invoke the method.
        // Verify operations.search is called with the expected query.
    }
}
~~~

Unit tests should focus on:

- Ensuring queries are constructed with the right fields and conditions.
- Verifying Pageable is passed into the query.
- Ensuring results are mapped accurately.
- Handling empty result cases.
- Validating input parameters if the fragment is responsible for validation.

### 13.2. Integration Testing Repository Composition

Unit testing the implementation does not prove Spring Data discovered the fragment. You need an integration test with an ApplicationContext to verify:

- The ProductRepository bean is created.
- The fragment interface is composed into the repository proxy.
- Custom methods invoke the correct implementation.
- Dependencies are injected.
- Default CRUD methods continue to work.
- If the fragment overrides a base method, the custom implementation is actually invoked.

You can use an Elasticsearch test container or a dedicated test Elasticsearch instance depending on project infrastructure.

### 13.3. Testing Naming Conventions

If repository initialization fails because the implementation cannot be found:

1. Check whether the fragment interface is extended by the repository.
2. Check whether the implementation class implements the correct interface.
3. Check whether the class name has the right suffix.
4. Check whether the package lies within the scanning scope.
5. Check repositoryImplementationPostfix if configured.
6. Check whether the class has any dependencies that cannot be instantiated.
7. Check whether there are duplicate bean names or ambiguous implementation candidates.

## 14. Common Pitfalls

**Declaring a fragment interface without an implementation.** Spring Data cannot execute the custom method. Create a class implementing the interface and following the naming convention.

**Naming the implementation ProductRepositoryImpl while using ProductSearchFragment.** With modern fragments, the name derived from the fragment interface is ProductSearchFragmentImpl.

**Placing the implementation outside the scanning package.** The repository may fail to discover the fragment. Place the class in the appropriate package or adjust the scanning scope.

**Forgetting to add the fragment interface to the repository's extends clause.** The implementation exists, but it is not composed into the repository if the fragment is missing from the composition.

**Using the wrong postfix.** If repositoryImplementationPostfix is configured as Custom, a class ending in Impl may not be discovered under that convention.

**Creating duplicate implementation beans.** Registering via multiple mechanisms simultaneously can produce ambiguous bean candidates. Pick one registration mechanism.

**Injecting the repository into its own fragment to call an overridden method.** This can cause a dispatch loop. Use ElasticsearchOperations or an appropriate service.

**Letting multiple fragments provide the same method without controlling order.** The outcome depends on fragment composition order. Avoid duplicate methods or declare order intentionally.

**Overriding save just to add a tiny side effect.** This can alter every save call through the repository. Consider a separate method or an appropriate callback.

**Using fragments instead of a service layer.** Fragments should focus on data access and queries. Broad business rules belong in the service/domain layer.

**Using blocking ElasticsearchOperations in a reactive fragment.** This can block reactive threads. Inject ReactiveElasticsearchOperations and return Flux/Mono.

**Assuming custom base classes and fragments are the same mechanism.** Fragments are independent composition units; base classes replace the repository's foundational implementation.

**Not testing the repository proxy.** Unit testing the implementation does not verify Spring Data discovery. Add integration tests for the ApplicationContext.

## 15. Steps to Create a Repository Fragment

When you need to add custom repository behavior:

1. Identify which methods do not fit derived queries or @Query.
2. Create a fragment interface whose name reflects its responsibility.
3. Declare clear methods and return types.
4. Create an implementation class following the fragment name plus Impl postfix convention.
5. Inject ElasticsearchOperations or required dependencies via the constructor.
6. Build queries and process results in the implementation.
7. Add the fragment interface to the main repository.
8. Place the implementation within the package scanning scope.
9. If using a custom postfix, keep class names and repository scanning configuration synchronized.
10. Test both the implementation and repository composition.
11. Check for methods sharing signatures with other fragments or the base repository.
12. Only override CRUD methods when the change is an intentional repository-wide behavior.

## 16. Complete Project Structure Example

~~~text
src/main/java/com/example/catalog
|
+-- document
|   |
|   +-- Product.java
|
+-- repository
|   |
|   +-- ProductRepository.java
|   |
|   +-- fragment
|       |
|       +-- ProductSearchFragment.java
|       +-- ProductSearchFragmentImpl.java
|       +-- ProductStatisticsFragment.java
|       +-- ProductStatisticsFragmentImpl.java
|
+-- service
|   |
|   +-- ProductCatalogService.java
|
+-- config
    |
    +-- ElasticsearchConfiguration.java
~~~

Repository:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                ProductSearchFragment,
                ProductStatisticsFragment {
}
~~~

Fragment interface:

~~~java
public interface ProductSearchFragment {
    SearchHits<Product> searchProducts(ProductSearchCriteria criteria);
}
~~~

Implementation:

~~~java
public class ProductSearchFragmentImpl
        implements ProductSearchFragment {

    private final ElasticsearchOperations operations;

    public ProductSearchFragmentImpl(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public SearchHits<Product> searchProducts(ProductSearchCriteria criteria) {
        Query query = buildQuery(criteria);
        return operations.search(query, Product.class);
    }

    private Query buildQuery(ProductSearchCriteria criteria) {
        // Convert criteria into a NativeQuery or appropriate Spring Data query.
        return NativeQuery.builder().build();
    }
}
~~~

Service using the repository:

~~~java
@Service
public class ProductCatalogService {

    private final ProductRepository repository;

    public ProductCatalogService(ProductRepository repository) {
        this.repository = repository;
    }

    public SearchHits<Product> search(ProductSearchCriteria criteria) {
        return repository.searchProducts(criteria);
    }
}
~~~

The service does not need to know which fragment provides searchProducts. It simply relies on ProductRepository's contract.

## 17. References

- [Spring Data Elasticsearch - Custom Repository Implementations](https://docs.spring.io/spring-data/elasticsearch/reference/repositories/custom-implementations.html): repository fragments, custom implementation discovery, and composition.
- [Spring Data Commons - Custom Repository Implementations](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html): fragment interfaces, implementation postfixes, multiple fragments, and composition order.
- [Spring Data Elasticsearch - Repository configuration](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories.html): declaring repositories and configuring scanning.
- [Spring Data Elasticsearch - Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html): using ElasticsearchOperations for lower-level operations.
- [Spring Data Elasticsearch API - EnableElasticsearchRepositories](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/repository/config/EnableElasticsearchRepositories.html): configuration attributes for repository scanning, implementation postfix, and base class.

Exact classes, constructors, and builder methods in the examples depend on the Spring Data Elasticsearch and Elasticsearch Java API Client versions. Consult your project dependencies' Javadoc when implementing. The core idea is that a fragment interface defines a slice of the repository API, an implementation class provides the behavior, and the main repository composes the fragment with the base repository into a unified proxy.
