# ElasticsearchRepository and Provided Data Operations

Spring Data Elasticsearch provides `ElasticsearchRepository` so Java applications can work with documents using the familiar Spring Data repository model. You declare an interface bound to an entity and an ID type; Spring generates the implementation at runtime to perform save, read, search, pagination, and delete operations.

Repositories reduce repetitive data-access code, but they do not eliminate the need to understand Elasticsearch. A `findById` operation reads a document by its identifier; a finder method by name must be mapped to an appropriate query; `save` writes the document to the index; and `deleteAll` can affect every document in the entity's index. Understanding each operation helps prevent misusing repositories or accidentally placing heavy load on the cluster.

## 1. Repositories in Spring Data Elasticsearch

### 1.1. A repository is a data-access abstraction

In a Spring application, a repository is an interface describing the data operations that a service needs. Instead of writing HTTP requests manually for each operation, you declare an interface that extends the appropriate repository:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {
}
~~~

The two generic parameters mean:

- `ProductDocument` is the entity/document type managed by the repository.
- `String` is the type of the ID annotated with `@Id`.

Spring Data creates a proxy implementation for the interface when the application starts and repositories are scanned. Services inject this interface and invoke the provided methods.

You do not need to write a `ProductRepositoryImpl` class manually just to get basic CRUD operations. When special queries are required, you can declare query methods, use `@Query`, or switch to a more flexible API such as `ElasticsearchOperations`.

### 1.2. Repository call flow

~~~mermaid
flowchart TD
    A[Controller] --> B[Service]
    B --> C[ProductRepository interface]
    C --> D[Spring Data repository proxy]
    D --> E[Mapping and query infrastructure]
    E --> F[Elasticsearch Java client]
    F --> G[Elasticsearch cluster]
    G --> F
    F --> E
    E --> D
    D --> C
    C --> B
    B --> A
~~~

Each layer has a distinct responsibility:

- The controller receives HTTP requests and returns responses.
- The service applies business rules.
- The repository provides the document-access API.
- Spring Data translates repository calls into appropriate operations.
- The mapping converter converts between Java objects and documents.
- The Elasticsearch client sends requests to the cluster.

Repositories should not become the place that holds all business logic. The service decides when to save, when to search, and how to process results.

### 1.3. Declaring the entity before declaring the repository

The repository needs to know which index the entity maps to and which property is the ID:

~~~java
@Document(indexName = "products", createIndex = false)
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    @Field(type = FieldType.Boolean)
    private boolean available;

    public ProductDocument() {
    }

    public ProductDocument(
            String id,
            String name,
            String category,
            BigDecimal price,
            boolean available) {
        this.id = id;
        this.name = name;
        this.category = category;
        this.price = price;
        this.available = available;
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

    public BigDecimal getPrice() {
        return price;
    }

    public boolean isAvailable() {
        return available;
    }
}
~~~

In the example, `createIndex = false` indicates that the index is provisioned in a separate management step. If a project allows the repository to create the index automatically, that behavior can be configured according to the application's strategy.

The `Double` type only illustrates a numeric field. For monetary data, consider precision and mapping options, such as scaled float with an appropriate scaling factor or storing the smallest currency unit as an integer. Do not choose a numeric type merely to match a Java type name.

## 2. Basic CRUD Operations

CRUD operations are the most frequently used group of APIs. They are typically inherited from Spring Data's repository abstractions and supported by `ElasticsearchRepository` for the corresponding entity.

### 2.1. Method overview

| Method | Purpose | Typical result |
|---|---|---|
| `save(entity)` | Save a single document | Saved entity |
| `saveAll(entities)` | Save multiple documents | Saved entities |
| `findById(id)` | Read a document by ID | `Optional<T>` |
| `existsById(id)` | Check whether an ID exists | `boolean` |
| `findAll()` | Retrieve documents | `Iterable<T>` |
| `findAllById(ids)` | Retrieve documents by multiple IDs | `Iterable<T>` |
| `count()` | Count documents | `long` |
| `deleteById(id)` | Delete by ID | No return value |
| `delete(entity)` | Delete an entity | No return value |
| `deleteAllById(ids)` | Delete by a list of IDs | No return value |
| `deleteAll(entities)` | Delete the passed-in entities | No return value |
| `deleteAll()` | Delete all documents belonging to the repository/index | No return value |

Exact method names and return types can vary across Spring Data Commons / Spring Data Elasticsearch versions. Check the API for the version used by your project when you need exact method signatures.

### 2.2. Saving a document with save

~~~java
ProductDocument product = new ProductDocument(
    "P1001",
    "Wireless Keyboard",
    "ACCESSORY",
    new BigDecimal("49.90"),
    true
);

ProductDocument saved = productRepository.save(product);
~~~

`save` converts the entity into a document and sends a write operation to the index associated with the entity. For an existing ID, the write operation typically replaces the document contents at that ID according to Elasticsearch index operation semantics.

This means `save` is commonly used for both creating a new document and performing a full-document update by ID. If you want to update a subset of fields without replacing the entire document, use an appropriate update API or `ElasticsearchOperations`.

If the ID is not yet assigned, Elasticsearch can auto-generate an ID depending on the API and version. For business data that requires reliable reads/updates, proactively design the ID or check how the version in use returns generated IDs.

Do not assume `save` automatically merges every field. If the submitted object omits a property, the written document may no longer retain that property's previous value, depending on the write operation used.

### 2.3. Saving multiple documents with saveAll

~~~java
List<ProductDocument> products = List.of(
    new ProductDocument(
        "P1001", "Wireless Keyboard", "ACCESSORY",
        new BigDecimal("49.90"), true
    ),
    new ProductDocument(
        "P1002", "Wireless Mouse", "ACCESSORY",
        new BigDecimal("29.90"), true
    )
);

Iterable<ProductDocument> savedProducts =
    productRepository.saveAll(products);
~~~

`saveAll` is convenient when you need to save a group of entities. Spring Data Elasticsearch can optimize multi-document operations using the bulk API instead of sending an independent request per document, depending on the implementation and version.

Bulk requests reduce network overhead, but they do not mean the entire batch is processed as an atomic transaction. Some items can succeed while others fail. When importing large datasets, track per-item errors and implement an appropriate retry strategy.

Do not pass an unbounded list to `saveAll`. Split batches into sizes suited to document size, cluster load, request limits, and actual latency.

### 2.4. Reading by ID with findById

~~~java
Optional<ProductDocument> result =
    productRepository.findById("P1001");

result.ifPresent(product ->
    System.out.println(product.getName())
);
~~~

`findById` reads a document by `_id`. This is a direct access operation by identifier, suitable when the application already knows the ID.

The result is `Optional<T>` because the document may not exist. Distinguish between:

- `Optional.empty()`: no document exists with that ID.
- Entity present with a `null` property: the document exists, and the field may be missing or null.
- Exception: the request failed due to connectivity, permissions, server errors, or mapping errors.

Do not catch every exception and return `Optional.empty()`. Doing so causes system failures to be mistaken for missing data.

### 2.5. Checking existence with existsById

~~~java
boolean exists = productRepository.existsById("P1001");
~~~

This method is suitable when you only need to know whether a document exists by ID. If you need the data for display or further processing, calling `findById` is usually more sensible.

If the business logic needs to check complex conditions such as "whether there is an available product in this category", declare a clear query method or query. `existsById` only checks by identifier.

### 2.6. Reading multiple IDs with findAllById

~~~java
List<String> ids = List.of("P1001", "P1002", "P1003");

Iterable<ProductDocument> found =
    productRepository.findAllById(ids);
~~~

This method is useful when you already have a list of IDs and want to retrieve the corresponding documents. Do not assume the result order always matches the input ID order or that every ID has a matching document. Handle the case where some IDs do not exist.

If you need to preserve input order, the application can build a map by ID and sort the results according to the original ID list.

### 2.7. Retrieving all documents with findAll

~~~java
Iterable<ProductDocument> allProducts =
    productRepository.findAll();
~~~

`findAll()` is suitable for small datasets or bounded administrative tasks. On a large index, fetching all documents can create heavy requests, consume application memory, and put load on the cluster.

For list screens, use pagination. For large data scans, consider scroll, `search_after`, or an appropriate batching mechanism instead of materializing the entire index into RAM.

### 2.8. Counting documents with count

~~~java
long total = productRepository.count();
~~~

`count()` returns the number of documents in the repository's index under the default query scope. It is useful for high-level statistics or checking data volume.

Counting an entire index can be resource-intensive depending on size and workload. If you need counts by condition, use an appropriate query. For continuously updated dashboards, consider how frequently `count` is called and whether aggregations or pre-aggregated metrics are more appropriate.

### 2.9. Deleting documents

Delete by ID:

~~~java
productRepository.deleteById("P1001");
~~~

Delete by entity:

~~~java
productRepository.delete(product);
~~~

Delete by list of IDs:

~~~java
productRepository.deleteAllById(List.of("P1002", "P1003"));
~~~

Delete selected entities:

~~~java
productRepository.deleteAll(selectedProducts);
~~~

These operations are appropriate when the deletion scope is clearly defined.

Be especially careful with:

~~~java
productRepository.deleteAll();
~~~

This method can delete every document within the corresponding repository/index scope. Do not call it as a "clear current list" action or expose it in a public endpoint without strict controls.

In production environments, bulk delete operations should have scope confirmation, appropriate permissions, audit logging, and a data recovery plan if required by the business.

## 3. Pagination and Sorting

### 3.1. Why is Pageable needed?

Search results can contain thousands or millions of documents. Instead of fetching everything, the application requests a page with a bounded size.

Spring Data uses `Pageable` to describe the page number, page size, and sort information:

~~~java
Pageable pageable = PageRequest.of(0, 20);

Page<ProductDocument> page =
    productRepository.findAll(pageable);
~~~

In the example, the first page contains at most 20 documents. Page indices are zero-based.

### 3.2. Sorting with Sort

~~~java
Sort sort = Sort.by(Sort.Direction.ASC, "price");

Pageable pageable = PageRequest.of(0, 20, sort);

Page<ProductDocument> page =
    productRepository.findAll(pageable);
~~~

You can sort by multiple properties:

~~~java
Sort sort = Sort.by(
    Sort.Order.asc("category"),
    Sort.Order.desc("price")
);
~~~

Property names are typically declared using the Java property name in the entity so Spring Data maps them via metadata. Use fields whose type and mapping support sorting. For `text` content, direct sorting is usually unsuitable; use a `keyword` subfield or a dedicated sort field.

### 3.3. Reading information from Page

~~~java
Page<ProductDocument> page =
    productRepository.findAll(PageRequest.of(0, 20));

List<ProductDocument> content = page.getContent();
int pageNumber = page.getNumber();
int pageSize = page.getSize();
long totalElements = page.getTotalElements();
int totalPages = page.getTotalPages();
boolean hasNext = page.hasNext();
~~~

`Page<T>` contains the current page's content along with summary information about the results, such as total elements and total pages.

To construct a `Page`, the framework may need the total result count. Computing the total can add extra work for Elasticsearch. If the UI only needs to know whether there is a next page, a lighter pagination type like `Slice` can be suitable when supported by the query method and version.

### 3.4. Deep pagination

Standard offset pagination works well for early pages. As `from` grows very large, Elasticsearch must process many intermediate results and enforces a common default `index.max_result_window` limit of 10,000.

For large data traversal or deep pages, consider `search_after` combined with a stable sort and point-in-time (PIT) when consistency is required. These capabilities usually require lower-level query APIs rather than forcing every scenario into `findAll(Pageable)`.

## 4. Query Methods Derived from Method Names

### 4.1. Query derivation

Spring Data can generate queries from repository method names by convention. For example:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    List<ProductDocument> findByCategory(String category);

    List<ProductDocument> findByAvailableTrue();

    List<ProductDocument> findByPriceBetween(
        BigDecimal minimum,
        BigDecimal maximum
    );

    List<ProductDocument> findByCategoryAndAvailable(
        String category,
        boolean available
    );
}
~~~

Spring parses the method name, identifies properties and operators, and builds the corresponding query.

Common keywords in query derivation include:

| Keyword in method name | Meaning |
|---|---|
| `And`, `Or` | Combine conditions |
| `Is`, `Equals` | Equality comparison |
| `Between` | Within range |
| `LessThan`, `GreaterThan` | Less than / greater than comparison |
| `In` | Belongs to a set of values |
| `Not` | Negate condition |
| `True`, `False` | Boolean condition |
| `OrderBy` | Specify result ordering |

Not every Spring Data operator is supported identically across all field types and Elasticsearch versions. Inspect the generated query and test against real data.

### 4.2. Method names use Java properties

Suppose the entity has:

~~~java
@Field(name = "product_category", type = FieldType.Keyword)
private String category;
~~~

The query method should reference the Java property:

~~~java
List<ProductDocument> findByCategory(String category);
~~~

Spring Data uses metadata to map `category` to the `product_category` field. Do not rename the method to `findByProductCategory` unless the entity actually has a Java property with that name.

### 4.3. Query methods with Pageable

~~~java
Page<ProductDocument> findByCategory(
    String category,
    Pageable pageable
);
~~~

Invocation:

~~~java
Page<ProductDocument> page =
    productRepository.findByCategory(
        "ACCESSORY",
        PageRequest.of(
            0,
            20,
            Sort.by(Sort.Direction.ASC, "price")
        )
    );
~~~

Combining conditions with `Pageable` helps build filtered list APIs. Bound the page size from client input to prevent a single request from asking for tens of thousands of documents.

### 4.4. When is a method name no longer clear?

Method names work well for simple, readable conditions. When a query needs:

- Complex boolean queries with multiple `must`/`should`/`filter` branches.
- Full-text matching with a specific analyzer.
- Phrase queries, fuzzy queries, or proximity.
- Highlighting, aggregations, or function score.
- Scripts, nested queries, or many fields.
- Fine-grained control over scoring and sorting.

then the method name can become long and hard to express intent clearly. In those cases, using `@Query` or `ElasticsearchOperations` is clearer.

## 5. Declaring Queries with @Query

### 5.1. Using JSON queries directly

`@Query` lets you declare a JSON Elasticsearch query directly on a repository method:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    @Query("{\"match\": {\"name\": \"?0\"}}")
    List<ProductDocument> searchByName(String text);
}
~~~

The placeholder `?0` references the first parameter. With multiple parameters, you can use index-based placeholders as supported by your version's syntax.

Example query filtering by category and availability:

~~~java
@Query("""
{
  "bool": {
    "filter": [
      { "term": { "category": "?0" } },
      { "term": { "available": true } }
    ]
  }
}
""")
List<ProductDocument> findAvailableInCategory(String category);
~~~

This is an illustrative JSON query. Verify placeholder substitution and annotation syntax for your project's Java / Spring Data Elasticsearch version.

### 5.2. Query methods and @Query serve different roles

| Declaration approach | Best suited when |
|---|---|
| Query derivation | Conditions are simple and the method name remains easy to understand |
| `@Query` | You want to write Query DSL explicitly while keeping the repository interface |
| `ElasticsearchOperations` | You need dynamic queries, many optional conditions, or deep control |
| Elasticsearch Java client directly | You need specialized client APIs or features not conveniently supported by abstractions |

Do not stuff a huge JSON query into an annotation just to avoid using `ElasticsearchOperations`. When a query must be assembled from many optional parameters or involves complex logic, a code builder is usually easier to read and test.

## 6. Using Repositories in Services

### 6.1. Constructor injection

Services should receive repositories through constructor injection:

~~~java
@Service
public class ProductService {

    private final ProductRepository productRepository;

    public ProductService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    public ProductDocument create(ProductDocument product) {
        return productRepository.save(product);
    }

    public Optional<ProductDocument> findById(String id) {
        return productRepository.findById(id);
    }

    public void delete(String id) {
        productRepository.deleteById(id);
    }
}
~~~

This keeps the service dependent on an abstraction and makes it easy to replace or mock the repository in unit tests.

### 6.2. Handling not-found cases

The service can convert an `Optional` result into a business exception or the result type used by the application:

~~~java
public ProductDocument getRequired(String id) {
    return productRepository.findById(id)
        .orElseThrow(() ->
            new ProductNotFoundException(id)
        );
}
~~~

`ProductNotFoundException` is an application-defined exception. A controller or exception handler can translate it into HTTP 404.

Do not let every layer decide independently how to handle missing data. Business rules should be centralized in the service.

### 6.3. Do not place business logic inside the repository

The repository should stay focused on data access. For example, `findByCategory` only queries data; deciding which categories a user may view, which products are allowed for sale, or how discounts apply belongs to service business logic.

If an operation involves multiple steps, the service coordinates the necessary repositories or APIs. However, do not assume consecutive Elasticsearch calls are wrapped in an ACID transaction like some relational database management systems. Explicitly design how to handle cases where one step succeeds and another fails.

## 7. Limits and Semantics of Repository Operations

### 7.1. Save typically writes documents by ID

`save` is suitable for writing a complete document by ID. If you need to update a few fields while keeping the rest intact, look into the appropriate update API. Reading a document, modifying the object, and calling `save` can cause lost updates if multiple processes update the same document concurrently without proper concurrency control.

For data with multiple writers, understand optimistic concurrency control, sequence numbers, primary terms, or versioning mechanisms supported by the API/client.

### 7.2. Bulk is not a transaction

`saveAll` and bulk operations can send multiple items in a single request. The bulk API typically processes each item individually; a failure on one item does not mean all other items are rolled back.

When importing data:

- Split into reasonable batches.
- Track per-item results.
- Record IDs of failed items.
- Apply bounded retries for transient errors.
- Do not retry mapping or malformed-data errors without fixing the root cause.
- Throttle throughput so you do not overload the cluster.

### 7.3. Deletes must have a clearly defined scope

`deleteById` and `delete(entity)` have a clearer scope than `deleteAll()`. Deleting an entire index can affect other features or services sharing the data.

For conditional deletes, use the appropriate query/delete API and verify the filter beforehand. A buggy filter can delete far more documents than intended.

### 7.4. Do not assume RDBMS-style transactions

Elasticsearch focuses on documents and distributed search. Do not assume a sequence of repository operations across multiple documents or indices will commit or roll back atomically.

If business workflows require coordinating multiple systems, you may need an outbox, saga, retries, idempotency, or compensating workflows. The choice depends on the consistency guarantees required by the business.

## 8. Repository or ElasticsearchOperations?

`ElasticsearchRepository` is a convenient choice for CRUD and predefined query methods. `ElasticsearchOperations` fits when the application needs more flexible control over queries.

| Need | Usually suitable tool |
|---|---|
| Save or read a single document by ID | Repository |
| Simple CRUD | Repository |
| Property-based query methods | Repository |
| Fixed JSON query | Repository with `@Query` |
| Dynamic filters across many optional parameters | `ElasticsearchOperations` |
| Complex aggregations | `ElasticsearchOperations` or Java client |
| Highlighting and accessing `SearchHit` metadata | Appropriate Spring Data Search API |
| `search_after`, PIT, or scroll | Specialized search APIs |
| Index, settings, and mapping management | `IndexOperations` |
| Newer client features without a convenient abstraction | Elasticsearch Java client |

You do not have to pick one tool for the entire application. A service can use repositories for common CRUD operations and `ElasticsearchOperations` for advanced search screens.

## 9. Imperative Repositories and ReactiveElasticsearchRepository

`ElasticsearchRepository` is an imperative (synchronous) API: method calls return results directly or wait for the operation to finish in the conventional manner.

Spring Data Elasticsearch also provides `ReactiveElasticsearchRepository` for reactive applications:

~~~java
public interface ReactiveProductRepository
        extends ReactiveElasticsearchRepository<ProductDocument, String> {
}
~~~

Reactive methods typically return types like `Mono<T>` or `Flux<T>` instead of imperative types like `Optional<T>`, `Iterable<T>`, or `Page<T>`.

Do not mix the two models arbitrarily. If an application uses WebFlux and end-to-end reactive processing, avoid blocking the event loop with synchronous calls. In a traditional Spring MVC application, imperative repositories are usually simpler and more appropriate.

## 10. Configuration and Repository Discovery

In a Spring Boot application, repository scanning is usually auto-configured when the starter and package structure match conventions. Repository interfaces should reside in packages scanned by Spring.

For custom configurations or applications without auto-configuration, you can declare:

~~~java
@Configuration
@EnableElasticsearchRepositories(
    basePackages = "com.example.product.repository"
)
public class ElasticsearchRepositoryConfiguration {
}
~~~

Only use `@EnableElasticsearchRepositories` when the application configuration requires it. Avoid declaring duplicate repository scan configurations for the same package unless intentional.

If a repository is not injected, check:

- Does the interface extend the appropriate repository?
- Is the package within component/repository scan scope?
- Does the entity have proper `@Document` and `@Id` metadata?
- Is the Spring Data Elasticsearch dependency compatible with Spring Boot?
- Are there repository creation or connection errors in startup logs?

A repository proxy can be created successfully while actual requests still fail if Elasticsearch is unavailable or credentials lack permissions.

## 11. Testing Repositories

### 11.1. Unit tests for services

You can mock the repository to test service business logic without Elasticsearch:

~~~java
@ExtendWith(MockitoExtension.class)
class ProductServiceTest {

    @Mock
    private ProductRepository productRepository;

    @InjectMocks
    private ProductService productService;

    @Test
    void returnsProductWhenItExists() {
        ProductDocument product = new ProductDocument(
            "P1001",
            "Wireless Keyboard",
            "ACCESSORY",
            new BigDecimal("49.90"),
            true
        );

        when(productRepository.findById("P1001"))
            .thenReturn(Optional.of(product));

        ProductDocument result =
            productService.getRequired("P1001");

        assertEquals("P1001", result.getId());
    }
}
~~~

This unit test verifies how the service handles repository results. It does not prove that Elasticsearch executes queries properly.

### 11.2. Integration tests with real Elasticsearch or Testcontainers

To verify mappings, query derivation, and repository semantics, you need integration tests connected to a compatible Elasticsearch instance.

A basic test can:

1. Create the index with the required settings/mapping.
2. Save a few representative documents.
3. Read them back by ID.
4. Test query methods and `@Query`.
5. Test sorting and pagination.
6. Clean up test data or the test index after completion.

Do not only mock the repository and conclude that Elasticsearch queries work. Query derivation, analyzers, mappings, and version compatibility can only be reliably verified against Elasticsearch.

### 11.3. Test data should cover edge cases

Test:

- Non-existent IDs.
- Missing or null fields.
- Strings with uppercase/lowercase letters and diacritics.
- Numeric values at range boundaries.
- Documents with nested collections or objects.
- A final page with only a single element.
- A batch containing one failing item.
- Deleting a non-existent ID.
- Queries returning no results.

These cases help uncover differences between how Java represents data and how Elasticsearch mappings/queries process it.

## 12. Common Pitfalls When Using ElasticsearchRepository

| Symptom | Possible cause | Resolution |
|---|---|---|
| Repository is not injected | Package is not scanned or repository configuration is missing | Check packages and `@EnableElasticsearchRepositories` if needed |
| Generic ID or mapping error | ID type does not match `@Id` property | Align the generic ID type and property type |
| `findById` does not find document | Passing an ID different from `_id` or document is not indexed yet | Check actual `_id` and target index |
| `findBy...` returns unexpected results | Query derivation does not match field type/analyzer | Inspect mapping and executed query |
| Sort fails or is inaccurate | Sorting on a `text` field or unsortable field | Use a `keyword` subfield or appropriate field |
| `save` drops existing fields | Writing full document from an object missing prior values | Use proper update semantics or read/modify with concurrency control |
| `saveAll` has failing items | Some documents are incompatible with mapping or rejected | Inspect per-item bulk errors |
| `findAll` is too slow or memory-heavy | Reading a large index entirely | Use `Pageable`, `search_after`, scroll, or batching |
| `deleteAll` removes too much data | Misunderstanding operation scope | Verify index/repository and permissions before deleting |
| Repository fails to create index | Cluster unavailable or runtime lacks privileges | Check `@Document.createIndex`, permissions, and provisioning |

When errors occur, inspect logs and responses from Elasticsearch. Do not catch generic exceptions and return empty results, as that hides connectivity, permission, mapping, or query failures.

## 13. Complete Example

A product repository can be declared as:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    List<ProductDocument> findByCategory(String category);

    Page<ProductDocument> findByCategory(
        String category,
        Pageable pageable
    );

    List<ProductDocument> findByAvailableTrue();

    List<ProductDocument> findByPriceBetween(
        BigDecimal minimum,
        BigDecimal maximum
    );

    @Query("{\"match\": {\"name\": \"?0\"}}")
    List<ProductDocument> searchByName(String text);
}
~~~

Service using the repository:

~~~java
@Service
public class ProductCatalogService {

    private final ProductRepository productRepository;

    public ProductCatalogService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    public ProductDocument save(ProductDocument product) {
        return productRepository.save(product);
    }

    public Optional<ProductDocument> find(String id) {
        return productRepository.findById(id);
    }

    public Page<ProductDocument> browseCategory(
            String category,
            int page,
            int size) {

        int safePage = Math.max(page, 0);
        int safeSize = Math.min(Math.max(size, 1), 100);

        Pageable pageable = PageRequest.of(
            safePage,
            safeSize,
            Sort.by(Sort.Direction.ASC, "name")
        );

        return productRepository.findByCategory(category, pageable);
    }

    public List<ProductDocument> searchName(String text) {
        return productRepository.searchByName(text);
    }

    public void remove(String id) {
        productRepository.deleteById(id);
    }
}
~~~

This example illustrates code organization. In a real project, ensure the `name` field supports sorting under an appropriate mapping; for `text` fields, sorting is usually done via a `keyword` subfield. Query methods and `@Query` should also be verified against the active Spring Data Elasticsearch version and mapping.

## 14. How to Choose the Right Operation

When designing a feature, start from the data requirement:

- ID is known and a single document is needed: use `findById`.
- Need to check whether a document exists by ID: use `existsById`.
- Need to save or replace a document: use `save`.
- Need to import a group of documents: use `saveAll` in batches.
- Need to search by property with simple conditions: use a query method.
- Need a fixed Query DSL query: use `@Query`.
- Need dynamic filtering, aggregations, or scoring control: consider `ElasticsearchOperations`.
- Need a bounded list: use `Pageable` or an appropriate pagination API.
- Need to traverse very large datasets: consider `search_after`, PIT, or scroll.
- Need to delete: confirm exact IDs/document set before calling delete operations.

`ElasticsearchRepository` is a good starting point for most common data operations. Understanding IDs, mappings, query derivation, pagination, bulk behavior, and write/delete semantics helps you use repositories safely. When a problem requires deeper control over queries or index lifecycles, combine it with `ElasticsearchOperations` and specialized Elasticsearch APIs.
