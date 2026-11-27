# Injecting Operations in Services or Repository Fragments

Spring Data Elasticsearch provides ElasticsearchOperations as an abstraction for applications to perform search, save, retrieve, and delete operations on documents. Instead of manually creating clients in every service or writing all queries as repository methods, an application can inject ElasticsearchOperations into a service or into a repository fragment dedicated to custom queries.

These two organization styles address slightly different needs:

- **Injecting into a service:** suitable when Elasticsearch operations are part of a service's use case or business flow. The service directly builds queries, invokes operations, and processes results.
- **Injecting into a repository fragment:** suitable when you want to consolidate specialized data queries into a reusable repository API. Services call meaningful domain methods on the repository, while the fragment handles query details.

In both approaches, use constructor injection, depend on the ElasticsearchOperations interface, and let Spring manage beans and the client lifecycle. Do not instantiate a new ElasticsearchTemplate or ElasticsearchClient inside every method.

## 1. What is ElasticsearchOperations?

ElasticsearchOperations is a high-level interface in Spring Data Elasticsearch that provides operations for working with documents and indices. ElasticsearchTemplate is the common implementation of this interface in synchronous applications.

Operations sits between the business layer and the Elasticsearch Java Client:

    Controller
       |
       v
    Service or Repository fragment
       |
       v
    ElasticsearchOperations
       |
       +-- MappingElasticsearchConverter
       |
       v
    Elasticsearch Java Client
       |
       v
    Elasticsearch cluster

When invoking operations with an entity class, Spring Data can use mapping metadata and converters to convert between Java objects and JSON documents. Thus, the application continues working with familiar entities and data types instead of manually serializing entire documents.

Common responsibilities of ElasticsearchOperations:

- Saving or updating entities.
- Retrieving documents by id.
- Deleting documents.
- Executing search queries.
- Returning SearchHits to preserve scores, highlights, and per-hit metadata.
- Performing operations via IndexCoordinates when an index or alias must be specified explicitly.

ElasticsearchOperations is an abstraction for data operations. Creating indices, mappings, and settings belongs to index management APIs like IndexOperations, even though operations provides an entry point to those APIs.

## 2. Why Inject ElasticsearchOperations?

If you only need standard CRUD operations, a repository may already suffice:

    public interface ProductRepository
            extends ElasticsearchRepository<Product, String> {
        List<Product> findByCategory(String category);
    }

However, when a query involves multiple conditions, native queries, aggregations, highlights, or handling SearchHits, a repository method derived from a method name may no longer be expressive enough.

Injecting ElasticsearchOperations enables a service to:

- Build queries with Query, NativeQuery, or CriteriaQuery.
- Combine must, should, filter, range, sort, and pagination.
- Retrieve SearchHits to read scores or highlights.
- Choose the entity class for Spring Data to map results into.
- Clearly control where queries live and how results are processed.

For example, a product search screen needs to search by name, return only active products, and paginate. That is a query that can be expressed with NativeQuery in a service.

Do not inject operations into every service just because you can. If a repository method expresses the business intent clearly and does not need a custom query, using a repository is usually simpler. Operations is useful when Spring Data-level query control is needed.

## 3. Spring Boot Provides the ElasticsearchOperations Bean

In a Spring Boot application using the Spring Data Elasticsearch starter, auto-configuration normally creates the required client and operations beans based on connection configuration.

Common Gradle dependency:

    dependencies {
        implementation("org.springframework.boot:spring-boot-starter-data-elasticsearch")
    }

Cluster address can be configured as:

    spring:
      elasticsearch:
        uris: http://localhost:9200

When auto-configuration is active, services can inject ElasticsearchOperations directly. The application does not need to manually instantiate ElasticsearchTemplate in constructors.

If a project configures the client manually, ensure the ElasticsearchOperations bean is constructed from the matching client and converter. In modern Spring Data lines, configuration typically connects ElasticsearchClient with ElasticsearchTemplate.

Manual bean configuration examples can depend on the Spring Data version and how the application constructs clients. Only provide custom beans when you need to override defaults, such as connecting to multiple clusters or configuring custom converters.

## 4. Injecting ElasticsearchOperations into a Service via Constructor Injection

Example of a service directly executing a product search by name:

    @Service
    public class ProductSearchService {

        private final ElasticsearchOperations operations;

        public ProductSearchService(
                ElasticsearchOperations operations) {
            this.operations = operations;
        }

        public SearchHits<Product> searchByName(
                String keyword,
                Pageable pageable) {

            Query query = NativeQuery.builder()
                .withQuery(q -> q
                    .match(m -> m
                        .field("name")
                        .query(keyword)
                    )
                )
                .withPageable(pageable)
                .build();

            return operations.search(query, Product.class);
        }
    }

In this example:

1. Spring creates ProductSearchService and injects the ElasticsearchOperations bean.
2. The service builds a NativeQuery with a match query on the name field.
3. Pageable defines the page number and page size.
4. operations.search sends the query through the client integration layer.
5. Spring Data maps returned documents into Product and wraps the details in SearchHits.

Constructor injection offers several benefits:

- Dependencies are visible right in the constructor.
- The operations field can be declared final.
- The service is easy to test because mocks or alternative implementations can be passed in.
- No need for field injection or calling ApplicationContext to look up beans.

Do not write:

    public ProductSearchService() {
        this.operations = new ElasticsearchTemplate(...);
    }

Manually instantiating template inside the service ties the service to client configuration details, can create redundant clients/connection pools, and bypasses Spring's shared configuration.

## 5. Using NativeQuery and Reading SearchHits in a Service

When a query needs to combine full-text search with filter conditions, you can build a NativeQuery:

    public SearchHits<Product> searchProducts(
            String keyword,
            String category,
            Pageable pageable) {

        NativeQuery query = NativeQuery.builder()
            .withQuery(q -> q
                .bool(b -> b
                    .must(m -> m
                        .match(mm -> mm
                            .field("name")
                            .query(keyword)
                        )
                    )
                    .filter(f -> f
                        .term(t -> t
                            .field("category")
                            .value(FieldValue.of(category))
                        )
                    )
                )
            )
            .withPageable(pageable)
            .build();

        return operations.search(query, Product.class);
    }

In this example:

- must contains the match query, so product name content participates in relevance scoring.
- filter restricts category without contributing to the score.
- Pageable limits results per page.
- SearchHits retains both entity content and search result metadata.

You can read the results:

    SearchHits<Product> hits =
        searchProducts("mechanical keyboard", "accessories",
                       PageRequest.of(0, 20));

    for (SearchHit<Product> hit : hits) {
        Product product = hit.getContent();
        float score = hit.getScore();
        // Use product and score
    }

If the service only needs a list of entities, SearchHits can be converted into List<Product>. However, if the UI needs to show scores, highlights, or hit info, keep SearchHits in the appropriate processing layer instead of stripping metadata too early.

Specific builder names and query types must match the project's Spring Data Elasticsearch version. NativeQuery in modern releases integrates with the Elasticsearch Java Client.

## 6. When Should You Inject Operations into a Service?

Injecting ElasticsearchOperations directly into a service fits when the query is part of a single use case and used in only a few places.

Examples:

- A reporting screen requiring multiple aggregations.
- A use case combining search and permission-based filters.
- A workflow that searches and then processes SearchHits or scores.
- A data administration task performing specially structured operations.

A service can coordinate multiple data sources:

    @Service
    public class CatalogService {

        private final ProductRepository repository;
        private final ElasticsearchOperations operations;

        public CatalogService(
                ProductRepository repository,
                ElasticsearchOperations operations) {
            this.repository = repository;
            this.operations = operations;
        }

        public Product getProduct(String id) {
            return repository.findById(id).orElseThrow();
        }

        public SearchHits<Product> searchCatalog(
                String keyword,
                Pageable pageable) {
            Query query = NativeQuery.builder()
                .withQuery(q -> q
                    .multiMatch(m -> m
                        .query(keyword)
                        .fields("name", "description")
                    )
                )
                .withPageable(pageable)
                .build();

            return operations.search(query, Product.class);
        }
    }

The repository handles simple lookup by id; operations handles multi-field queries. Using both abstractions in the same service makes sense when each abstraction clarifies a distinct type of operation.

However, if multiple services repeat the same complex query, move that query into a repository fragment to avoid code duplication and keep the data API in one place.

## 7. What is a Repository Fragment?

A repository fragment is a custom extension composed into a Spring Data repository. Fragments let you add methods not provided by the default repository interface while preserving standard repository usage through dependency injection.

For example, ProductRepository can extend:

- ElasticsearchRepository<Product, String> for CRUD.
- ProductSearch for custom search queries.

Diagram:

    ProductService
         |
         v
    ProductRepository
         |
         +-------------------------------+
         |                               |
         v                               v
    ElasticsearchRepository         ProductSearch
    Default CRUD                    Fragment interface
                                         |
                                         v
                                  ProductSearchImpl
                                         |
                                         v
                                  ElasticsearchOperations

Spring Data composes the fragment implementation into the repository proxy. The service only injects ProductRepository and calls both CRUD methods and custom methods.

## 8. Creating a Repository Fragment Interface

First, declare an interface describing the custom search capability:

    public interface ProductSearch {

        SearchHits<Product> searchByName(
            String keyword,
            Pageable pageable
        );
    }

This interface describes the API the repository wants to add. It does not extend ElasticsearchRepository and contains no query construction details.

Next, the main repository extends the fragment:

    public interface ProductRepository
            extends ElasticsearchRepository<Product, String>,
                    ProductSearch {
    }

ProductRepository now has:

- CRUD methods from ElasticsearchRepository.
- The searchByName method from ProductSearch.

Services can inject ProductRepository and use both groups of methods without knowing which fragments compose the repository.

## 9. Writing the Fragment Implementation and Injecting Operations

By default convention, the implementation of fragment interface ProductSearch is named ProductSearchImpl. Spring Data locates implementations using the repository fragment convention and composes them into the repository proxy.

Example:

    public class ProductSearchImpl implements ProductSearch {

        private final ElasticsearchOperations operations;

        public ProductSearchImpl(
                ElasticsearchOperations operations) {
            this.operations = operations;
        }

        @Override
        public SearchHits<Product> searchByName(
                String keyword,
                Pageable pageable) {

            NativeQuery query = NativeQuery.builder()
                .withQuery(q -> q
                    .match(m -> m
                        .field("name")
                        .query(keyword)
                    )
                )
                .withPageable(pageable)
                .build();

            return operations.search(query, Product.class);
        }
    }

The implementation receives ElasticsearchOperations via its constructor just like a regular service. Spring Data manages instantiating the fragment implementation and providing its bean dependencies.

By default, the implementation class should reside in a package discovered by repository scanning, typically the same package or a subpackage of the repository interface. The default implementation suffix is Impl. You can configure the repository implementation postfix if your project uses a different naming convention.

Do not create a legacy monolithic custom repository implementation if you only need to add a focused group of methods. Fragment interfaces and fragment implementations separate extensions by responsibility, making them easier to compose and maintain.

## 10. Calling the Fragment from a Service

Once the fragment is composed into ProductRepository, the service only needs to inject the repository:

    @Service
    public class ProductService {

        private final ProductRepository repository;

        public ProductService(ProductRepository repository) {
            this.repository = repository;
        }

        public SearchHits<Product> search(
                String keyword,
                Pageable pageable) {
            return repository.searchByName(keyword, pageable);
        }
    }

The service does not need to know whether the query is executed using NativeQuery or CriteriaQuery. That detail stays inside ProductSearchImpl.

Benefits of this organization:

- The repository API reflects the data access capabilities the application needs.
- Services do not contain verbose Elasticsearch Query DSL details.
- Custom queries can be reused across multiple services via the same repository.
- Implementations can be changed without altering how services call them.
- Unit tests can be written specifically for fragments alongside repository integration tests.

## 11. Fragments Can Use Multiple Operations Methods

Fragments are not limited to search. They can use ElasticsearchOperations to build specialized queries or operations.

For example, a fragment can provide:

    public interface ProductCatalogOperations {

        SearchHits<Product> searchAvailable(
            String keyword,
            Pageable pageable
        );

        long countAvailable(String category);
    }

Implementation:

    public class ProductCatalogOperationsImpl
            implements ProductCatalogOperations {

        private final ElasticsearchOperations operations;

        public ProductCatalogOperationsImpl(
                ElasticsearchOperations operations) {
            this.operations = operations;
        }

        @Override
        public SearchHits<Product> searchAvailable(
                String keyword,
                Pageable pageable) {

            NativeQuery query = NativeQuery.builder()
                .withQuery(q -> q
                    .bool(b -> b
                        .must(m -> m
                            .match(mm -> mm
                                .field("name")
                                .query(keyword)
                            )
                        )
                        .filter(f -> f
                            .term(t -> t
                                .field("status")
                                .value(FieldValue.of("ACTIVE"))
                            )
                        )
                    )
                )
                .withPageable(pageable)
                .build();

            return operations.search(query, Product.class);
        }

        @Override
        public long countAvailable(String category) {
            NativeQuery query = NativeQuery.builder()
                .withQuery(q -> q
                    .bool(b -> b
                        .filter(f -> f
                            .term(t -> t
                                .field("status")
                                .value(FieldValue.of("ACTIVE"))
                            )
                        )
                        .filter(f -> f
                            .term(t -> t
                                .field("category")
                                .value(FieldValue.of(category))
                            )
                        )
                    )
                )
                .build();

            return operations.count(query, Product.class);
        }
    }

The repository can extend the fragment:

    public interface ProductRepository
            extends ElasticsearchRepository<Product, String>,
                    ProductCatalogOperations {
    }

This example shows a fragment can encapsulate multiple related operations in one interface. Name fragments by capability or responsibility, avoiding dumping unrelated queries into one huge implementation class.

## 12. Multiple Repository Fragments in the Same Repository

One repository can compose multiple fragments:

    public interface ProductRepository
            extends ElasticsearchRepository<Product, String>,
                    ProductSearch,
                    ProductCatalogOperations,
                    ProductExportOperations {
    }

Each fragment has its own interface and implementation:

    ProductSearch
        -> ProductSearchImpl

    ProductCatalogOperations
        -> ProductCatalogOperationsImpl

    ProductExportOperations
        -> ProductExportOperationsImpl

Implementations can each inject ElasticsearchOperations. This keeps each responsibility small and allows services to call one unified repository.

If two fragments have methods with identical signatures or conflicting default methods, redesign the API or explicitly specify composition rules to avoid conflicts. Do not create fragments with overlapping responsibilities merely to split files.

## 13. Using CriteriaQuery Instead of NativeQuery

Not every query needs to be expressed in Elasticsearch Query DSL. For simple conditions, CriteriaQuery can be easier to read.

Example inside a fragment:

    Criteria criteria = new Criteria("status").is("ACTIVE")
        .and("category").is("accessories");

    Query query = new CriteriaQuery(criteria)
        .setPageable(pageable);

    return operations.search(query, Product.class);

CriteriaQuery fits basic filter or query conditions. NativeQuery is useful when you need advanced Elasticsearch capabilities, specific Query DSL, multiple nested clauses, or features the Criteria API does not express conveniently.

Choose the API based on complexity and query requirements. Do not force every query into NativeQuery if CriteriaQuery is clear enough; equally, do not overcomplicate CriteriaQuery when a query needs exact Elasticsearch DSL semantics.

## 14. Choosing the Right Return Type

ElasticsearchOperations offers multiple result shapes. Choose the return type according to what callers need:

| Return Type | When to Use |
|---|---|
| List<T> | Only need the list of entities |
| SearchHits<T> | Need total hits, scores, highlights, and metadata |
| SearchPage<T> | Need search results combined with pagination info |
| long from count | Only need the number of matching documents |
| From get | Need to read one document by id |

For example, if a fragment returns SearchHits<Product>, the service can process it:

    SearchHits<Product> hits =
        repository.searchByName(keyword, pageable);

    long total = hits.getTotalHits();

    List<Product> products = hits.getSearchHits()
        .stream()
        .map(SearchHit::getContent)
        .toList();

If the service immediately converts to List<Product>, scores and highlights will no longer be available in the returned data type. Keep SearchHits when the UI or ranking logic needs that metadata.

## 15. Explicitly Specifying an Index or Alias

Normally an entity has @Document with indexName and Spring Data uses that information to identify the index. If a query needs to target another index or alias, pass IndexCoordinates to the corresponding operations overload:

    SearchHits<Product> hits = operations.search(
        query,
        Product.class,
        IndexCoordinates.of("products")
    );

This is useful when:

- Using a stable alias pointing to versioned physical indices.
- Having multiple indices mapped to one entity.
- An administrative job needs to query a specific index.

Do not hardcode physical index names across multiple services. If the application uses aliases, let configuration or appropriate metadata decide the logical name, while ensuring mappings across indices behind the alias are compatible with the entity.

## 16. When Should Queries Not Go into a Repository Fragment?

Fragments suit reusable data access logic. However, not all business logic belongs in a repository.

Keep it in a service when:

- The query serves a single use case and coordinates multiple data sources.
- Results require applying business rules or combining multiple repositories.
- The query is one step in a longer workflow rather than a reusable data API.

Use a fragment when:

- Multiple services need the same complex query.
- You want the repository to expose a clear API for custom searches.
- Multiple Elasticsearch operations relate to the same data domain.
- You want to isolate NativeQuery/CriteriaQuery details from the business layer.

Repositories should stay focused on data access. Do not put sending emails, calling payment systems, or orchestrating long business workflows inside a fragment simply because they start with a query.

## 17. Testing Services and Fragments

Constructor injection makes unit testing easier.

For services injecting ElasticsearchOperations, you can mock the interface to test how the service builds queries and handles results. However, mock tests do not verify that Elasticsearch actually understands the query as intended.

For repository fragments, you can:

- Unit test the implementation with a mock ElasticsearchOperations.
- Integration test the repository with an appropriate Elasticsearch version.
- Verify mappings, analyzers, Query DSL, and sample data.
- Test pagination, sorting, filtering, and zero-result cases.

Example service test structure:

    @ExtendWith(MockitoExtension.class)
    class ProductSearchServiceTest {

        @Mock
        ElasticsearchOperations operations;

        @InjectMocks
        ProductSearchService service;

        // Stub operations.search(...) and verify the service behavior.
    }

This is just an illustrative skeleton. When mocking methods accepting Query, you can use ArgumentCaptor to capture the query and assert required conditions. Integration tests remain essential for verifying analyzers, mappings, and Elasticsearch semantics.

## 18. Notes on Package Scanning and Implementation Naming

Spring Data needs to discover the fragment implementation to compose it into the repository proxy.

With default configuration:

- The repository interface sits in a package scanned by Spring Data Elasticsearch.
- The fragment interface is extended by the repository.
- The implementation class follows the fragment interface name plus the Impl suffix.
- The implementation resides in a package searched by repository infrastructure.

Example:

    com.example.catalog.repository
        ProductRepository.java
        ProductSearch.java
        ProductSearchImpl.java

If the implementation is not found, the application may fail when creating the repository bean or fail to compose the fragment as expected. Check base packages on @EnableElasticsearchRepositories, implementation class names, and the configured suffix.

If using multiple repository packages, you can configure:

    @EnableElasticsearchRepositories(
        basePackages = "com.example.catalog.repository"
    )

In Spring Boot applications, repository scanning may already be auto-configured from the application class's package. Only add @EnableElasticsearchRepositories when you need to control scanning scope or use custom repository configuration.

Do not register the fragment implementation as a standalone bean via duplicate mechanisms if Spring Data already discovers implementations by convention. Avoid creating two beans with the same role leading to ambiguity.

## 19. Multiple ElasticsearchOperations or Multiple Clusters

An application may connect to multiple Elasticsearch clusters. In that case there may be multiple ElasticsearchOperations beans. Injecting by type alone may prevent Spring from resolving the right bean.

You can use qualifiers:

    @Service
    public class ProductSearchService {

        private final ElasticsearchOperations catalogOperations;

        public ProductSearchService(
                @Qualifier("catalogOperations")
                ElasticsearchOperations catalogOperations) {
            this.catalogOperations = catalogOperations;
        }
    }

Exact bean names and configuration depend on how the application declares each client/template. Name beans after their purpose or cluster, avoiding generic names that are hard to tell apart.

Repository fragments may also need qualifiers when injecting multiple operations beans:

    public class ProductSearchImpl implements ProductSearch {

        private final ElasticsearchOperations operations;

        public ProductSearchImpl(
                @Qualifier("catalogOperations")
                ElasticsearchOperations operations) {
            this.operations = operations;
        }
    }

Ensure the fragment uses the operations bean corresponding to the cluster holding the products index. Querying the wrong cluster can produce index-not-found errors or unexpected results.

## 20. Do Not Use Synchronous ElasticsearchOperations in Reactive Flows

ElasticsearchOperations is a synchronous API. If an application uses Spring WebFlux and requires non-blocking processing, do not call synchronous operations directly on an event-loop thread.

In reactive applications, consider ReactiveElasticsearchOperations and APIs returning Mono/Flux:

    public class ProductReactiveService {

        private final ReactiveElasticsearchOperations operations;

        public ProductReactiveService(
                ReactiveElasticsearchOperations operations) {
            this.operations = operations;
        }
    }

ReactiveElasticsearchOperations is a different abstraction from ElasticsearchOperations. You cannot turn a blocking call into a non-blocking one merely by changing the return type to Mono.

If calling a blocking library inside a reactive pipeline is unavoidable, isolate the blocking section on an appropriate scheduler, though that is only an integration workaround. For WebFlux systems, keep reactive APIs throughout the data access layer.

## 21. Common Pitfalls

### Manually Creating ElasticsearchTemplate in Services

Instantiating templates manually ties services to client configuration, can create redundant connection pools, and bypasses Spring-managed beans. Inject ElasticsearchOperations instead.

### Using Field Injection

Field injection hides dependencies and makes testing harder. Use constructor injection to declare required beans explicitly.

### Putting Every Query Directly in Services

If multiple services repeat the same complex query, code becomes scattered and inconsistent. Consider repository fragments for reusable data queries.

### Putting All Business Logic in Repository Fragments

Fragments should encapsulate data access operations. Business rules, coordinating multiple sources, and use-case orchestration belong in services.

### Forgetting to Extend the Fragment in the Main Repository

Having ProductSearch interface and ProductSearchImpl implementation is not enough. ProductRepository must extend ProductSearch for Spring Data to compose the fragment into the repository.

### Misnaming or Misplacing the Implementation Package

If the implementation name does not match the suffix or lies outside repository scanning scope, the fragment may not be detected. Verify class names, packages, and basePackages settings.

### Injecting the Wrong Operations Bean with Multiple Clusters

When multiple beans of the same type exist, use @Qualifier to unambiguously identify the cluster/operations bean needed.

### Using SearchHits but Discarding Metadata

If the application needs scores, highlights, or total hits, do not immediately convert to a plain entity List and drop search metadata.

### Calling Synchronous Operations on the Event Loop

In WebFlux, blocking calls can stall the event loop. Use ReactiveElasticsearchOperations for reactive flows.

## Conclusion

ElasticsearchOperations is the right abstraction when you need more flexible Elasticsearch queries and operations than standard repository methods provide. Injecting operations into a service lets the use case control queries right where business logic is orchestrated. Injecting operations into a repository fragment encapsulates custom queries into a reusable repository API.

For fragments, declare an interface, have the main repository extend that interface, and provide an implementation following naming conventions so Spring Data composes it into the repository proxy. Both services and fragments should use constructor injection, depend on ElasticsearchOperations, and let Spring manage the client/template. Choose between service and fragment based on query reuse scope, keep business logic in services, verify package scanning, and use ReactiveElasticsearchOperations if the application requires reactive I/O.
