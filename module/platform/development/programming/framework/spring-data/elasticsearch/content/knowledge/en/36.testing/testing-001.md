# Distinguishing Service Tests and Repository Integration Tests

In a Spring Data Elasticsearch application, the service and repository handle two different responsibilities. The service orchestrates business logic: checking conditions, combining data, deciding the order of operations, and converting results into application responses. The repository translates save/read/delete operations into Elasticsearch requests through mapping, query derivation, and the client.

Because their responsibilities differ, the two layers need to be tested at different levels:

- **Service unit test:** isolates the service by mocking the repository or external dependencies. The goal is to verify business rules and how the service reacts to results or errors from dependencies.
- **Repository integration test:** runs against a real Elasticsearch instance, typically via Testcontainers, to verify mapping, serialization, queries, CRUD, refresh, and real Elasticsearch behavior.

A service test can pass even if the repository query is wrong because the repository is mocked. A repository integration test can pass even if the service applies business rules incorrectly because it does not test the full service orchestration. The two types of tests complement each other.

## 1. Dividing Responsibilities to Test

Example product creation flow:

```text
HTTP Controller
      |
      v
ProductService
  - check whether SKU already exists
  - decide whether creation is allowed
  - call repository.save(...)
  - convert entity into response
      |
      v
ProductRepository
  - map entity to document
  - build Elasticsearch request
  - execute Get/Search/Index/Delete
      |
      v
Elasticsearch
  - mapping and analyzer
  - store document
  - refresh/search visibility
```

Service unit tests should focus on the decisions inside `ProductService`. Repository integration tests should focus on how `ProductRepository` and Elasticsearch work together properly.

| Aspect | Service unit test | Repository integration test |
|---|---|---|
| Repository dependency | Mock or fake. | Real repository created by Spring. |
| Elasticsearch instance | Not needed. | Requires real Elasticsearch or an equivalent environment. |
| `@Field`, `@Id`, `@Document` mapping | Not verified. | Can verify actual mapping and serialization. |
| Query method derivation | Does not verify executed query. | Verifies query results on a real index. |
| `NativeQuery`, CriteriaQuery | Can only check how the service calls the API or pure query builder. | Verifies query DSL and actual results. |
| Business rules | Primary focus. | Only tested if the test goes through the service. |
| Refresh/search visibility | Does not verify Elasticsearch semantics. | Can be tested directly. |
| Speed | Fast, runs frequently. | Slower due to container/index startup. |
| Bugs detected | Business branches, response mapping, empty/error handling in the service. | Incorrect mapping, incorrect query, client/configuration errors, Elasticsearch semantics. |

## 2. Example Service and Repository Structure

Suppose the application has a product entity:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products-it")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String status;

    // constructors, getters, setters
}
```

Repository:

```java
import java.util.Optional;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    Optional<Product> findBySku(String sku);
}
```

Service:

```java
import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Product register(Product product) {
        if (repository.findBySku(product.getSku()).isPresent()) {
            throw new DuplicateProductSkuException(product.getSku());
        }

        return repository.save(product);
    }

    public Product getRequired(String id) {
        return repository.findById(id)
                .orElseThrow(() -> new ProductNotFoundException(id));
    }
}
```

In this example, the service decides to reject duplicate SKUs and throw an error when an ID does not exist. The repository only provides save and read operations. This is an appropriate boundary for separating tests.

## 3. Service Unit Test: Mocking the Repository

A service unit test does not need to start a Spring context or Elasticsearch. Use JUnit and Mockito to create fake dependencies, then test the service's behavior.

Example with JUnit 5 and Mockito:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.when;

import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class ProductServiceTest {

    @Mock
    private ProductRepository repository;

    @InjectMocks
    private ProductService service;

    @Test
    void registerSavesWhenSkuDoesNotExist() {
        Product input = new Product(null, "SKU-100", "Keyboard", "ACTIVE");
        Product saved = new Product("P-100", "SKU-100", "Keyboard", "ACTIVE");

        when(repository.findBySku("SKU-100")).thenReturn(Optional.empty());
        when(repository.save(input)).thenReturn(saved);

        Product result = service.register(input);

        assertThat(result.getId()).isEqualTo("P-100");
        verify(repository).findBySku("SKU-100");
        verify(repository).save(input);
    }

    @Test
    void registerRejectsDuplicateSku() {
        Product input = new Product(null, "SKU-100", "Keyboard", "ACTIVE");
        Product existing = new Product("P-001", "SKU-100", "Old keyboard", "ACTIVE");

        when(repository.findBySku("SKU-100")).thenReturn(Optional.of(existing));

        assertThatThrownBy(() -> service.register(input))
                .isInstanceOf(DuplicateProductSkuException.class);

        verify(repository, never()).save(input);
    }

    @Test
    void getRequiredThrowsWhenIdDoesNotExist() {
        when(repository.findById("P-404")).thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.getRequired("P-404"))
                .isInstanceOf(ProductNotFoundException.class);
    }
}
```

These tests verify three business branches:

- SKU does not exist: the service calls save and returns the saved entity.
- SKU already exists: the service throws a business exception and does not call save.
- ID does not exist: the service turns `Optional.empty()` into `ProductNotFoundException`.

No `@SpringBootTest`, no container, and no Elasticsearch connection are needed. The tests run fast because they only check service logic.

### 3.1. Mocking at the Right Boundary

Mocking the repository in a service test is appropriate because the repository is a dependency outside the service boundary. You should not mock the service under test itself or mock every internal method, which would make the test merely confirm the current implementation.

For example, if the goal is to verify that the service rejects a duplicate SKU, you only need to mock the result of `findBySku`. There is no need to set up Elasticsearch mapping, index, or queries in this test.

### 3.2. Checking Outcomes and Side Effects

Prioritize assertions on business outcomes:

- Does the returned response/entity have the expected ID/status?
- Is the expected domain exception thrown?
- When a condition is not met, is the write operation skipped?
- When the dependency returns empty/error, how does the service handle it?

`verify(...)` is useful when a side effect is an important part of the contract, such as not calling save when a SKU is duplicated. Do not mechanically verify every internal call, as tests will become brittle when refactoring without changing external behavior.

### 3.3. Mocking Exceptions from the Repository

The service needs to react properly when Elasticsearch is unavailable:

```java
@Test
void registerPropagatesPersistenceFailure() {
    Product input = new Product(null, "SKU-100", "Keyboard", "ACTIVE");

    when(repository.findBySku("SKU-100")).thenReturn(Optional.empty());
    when(repository.save(input)).thenThrow(
            new ElasticsearchAccessException("Unavailable", new RuntimeException())
    );

    assertThatThrownBy(() -> service.register(input))
            .isInstanceOf(ElasticsearchAccessException.class);
}
```

This tests the service's reaction to a dependency failure. It does not verify whether real Elasticsearch throws that exact exception type; that belongs to a repository integration test or adapter test.

## 4. Why Service Tests Do Not Prove the Repository Works

In a service test, Mockito replaces the real repository with a fake object. When a test writes:

```java
when(repository.findBySku("SKU-100"))
        .thenReturn(Optional.of(product));
```

Mockito returns the declared result without sending a query to Elasticsearch. Therefore, the test cannot detect errors such as:

- `sku` being mapped as `text` instead of `keyword`.
- Field names in the query not matching the mapping.
- Derived query `findBySku` not generating the intended query.
- `@Id` not mapping to `_id` properly.
- Converter serializing/deserializing the wrong data type.
- Index not being created or the application pointing to the wrong index/alias.
- Custom routing being missing.
- Search not having refreshed yet, so newly indexed documents are not visible.
- Native query DSL being invalid for the running Elasticsearch version.

Service tests are still valuable, but the question they answer is "does the service orchestrate properly when the repository returns result X?", not "does the repository query Elasticsearch correctly?".

## 5. Repository Integration Test: Using Real Elasticsearch

A repository integration test requires an Elasticsearch instance compatible with the project's client and Spring Data version. Testcontainers helps start Elasticsearch in Docker and automatically manages the container lifecycle.

Illustrative dependencies for Gradle:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:elasticsearch'
}
```

The Testcontainers version should be managed by the project's BOM or dependency management. The Elasticsearch image should match a version compatible with the Spring Data Elasticsearch/Elasticsearch Java Client used by the application; avoid using `latest` automatically because it can introduce uncontrolled changes in tests.

### 5.1. Starting Elasticsearch with Testcontainers

Example integration test using JUnit 5:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.elasticsearch.ElasticsearchContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@SpringBootTest
class ProductRepositoryIT {

    @Container
    static final ElasticsearchContainer elasticsearch =
            new ElasticsearchContainer(
                    DockerImageName.parse(
                            "docker.elastic.co/elasticsearch/elasticsearch:8.15.0"
                    )
            ).withEnv("xpack.security.enabled", "false");

    @DynamicPropertySource
    static void elasticsearchProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.elasticsearch.uris", elasticsearch::getHttpHostAddress);
    }

    @Autowired
    ProductRepository repository;

    @Autowired
    ElasticsearchOperations operations;

    @BeforeEach
    void prepareIndex() {
        IndexOperations index = operations.indexOps(Product.class);
        index.delete();
        index.createWithMapping();
    }
}
```

This is an illustrative configuration. Connection property names, enabling/disabling security, container packages, and the Elasticsearch version must match the Spring Boot, Testcontainers, and Spring Data versions in use. Some Elasticsearch versions require configuring a password/TLS instead of disabling security; in production-like test environments, test with the corresponding security configuration.

`@SpringBootTest` initializes the real application context, so Spring Data creates the repository proxy and configures the client. The test will go through the real repository to Elasticsearch in the container.

### 5.2. Why Recreate the Index?

Each test should start from a known data state. The example above deletes the test index and recreates the mapping from the entity so that data or mapping from a previous test does not affect subsequent tests.

`createWithMapping()` instructs Spring Data to create the index and mapping from entity metadata. If the project manages mappings via JSON templates or separate migrations, integration tests should create the index using the exact production mechanism instead of accidentally testing a different mapping.

If tests run in parallel, deleting/recreating the same index can cause conflicts. In that case, use a separate index per test/class or disable parallel execution for the group of tests sharing an index.

## 6. Testing CRUD Through the Real Repository

Once the index is created, you can test save, get, search, and delete:

```java
import static org.assertj.core.api.Assertions.assertThat;

@Test
void savesAndReadsProductById() {
    Product input = new Product("P-100", "SKU-100", "Keyboard", "ACTIVE");

    Product saved = repository.save(input);

    Product loaded = repository.findById("P-100").orElseThrow();

    assertThat(saved.getId()).isEqualTo("P-100");
    assertThat(loaded.getSku()).isEqualTo("SKU-100");
    assertThat(loaded.getName()).isEqualTo("Keyboard");
}

@Test
void deletesProductById() {
    repository.save(new Product("P-200", "SKU-200", "Mouse", "ACTIVE"));

    repository.deleteById("P-200");

    assertThat(repository.findById("P-200")).isEmpty();
}
```

These assertions go through the real repository and Elasticsearch. `findById` uses the Get API, which has real-time semantics by default.

### 6.1. Testing Derived Queries

Derived queries should be verified with an actual search:

```java
@Test
void findsProductBySku() {
    repository.save(new Product("P-300", "SKU-300", "Headphones", "ACTIVE"));

    operations.indexOps(Product.class).refresh();

    Optional<Product> found = repository.findBySku("SKU-300");

    assertThat(found).isPresent();
    assertThat(found.orElseThrow().getName()).isEqualTo("Headphones");
}
```

`findBySku` uses the Search API, so the test refreshes the index before searching to avoid depending on background refresh timing. This test verifies that the property name, mapping, and query derivation work together on Elasticsearch.

### 6.2. Testing Search and Delete

```java
@Test
void deletesDocumentAndRemovesItFromSearchResultsAfterRefresh() {
    repository.save(new Product("P-400", "SKU-400", "Monitor", "ACTIVE"));
    operations.indexOps(Product.class).refresh();

    assertThat(repository.findBySku("SKU-400")).isPresent();

    repository.deleteById("P-400");
    operations.indexOps(Product.class).refresh();

    assertThat(repository.findBySku("SKU-400")).isEmpty();
}
```

Here, refreshing after delete verifies the Search API state. If you only call `findById` after delete, the real-time Get API can return empty without needing a refresh.

## 7. Testing Mapping and Serialization

Repository integration tests are the right place to detect incorrect mapping annotations.

For example, the entity declares:

```java
@Field(type = FieldType.Keyword)
private String sku;
```

Tests can verify:

- The index is created with the `sku` field as `keyword`.
- Documents are serialized with the correct field names.
- Values are deserialized back into the entity with the correct types.
- The `@Id` field is stored as `_id` and read back properly.
- Date, numeric, geo, nested, or join fields have the expected mapping.

You can read the mapping via:

```java
Map<String, Object> mapping = operations.indexOps(Product.class).getMapping();
assertThat(mapping).isNotNull();
```

Specific assertions should rely on the mapping structure returned by the Spring Data/Elasticsearch version rather than comparing an entire JSON string, which is easily affected by field ordering or formatting.

If mappings are managed with separate JSON files/templates, inspect the actual mapping on the index after creation. Having the right annotation on the entity does not guarantee an old index was updated if that index already existed beforehand.

## 8. Testing `NativeQuery` and CriteriaQuery

When a repository has a custom fragment using `ElasticsearchOperations`, integration tests should verify the query against real Elasticsearch.

Example fragment:

```java
public interface ProductSearchFragment {
    List<Product> searchActiveByKeyword(String keyword);
}
```

Implementation:

```java
public class ProductSearchFragmentImpl implements ProductSearchFragment {

    private final ElasticsearchOperations operations;

    public ProductSearchFragmentImpl(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public List<Product> searchActiveByKeyword(String keyword) {
        Query query = new CriteriaQuery(
                new Criteria("name").matches(keyword)
                        .and("status").is("ACTIVE")
        );

        return operations.search(query, Product.class)
                .stream()
                .map(SearchHit::getContent)
                .toList();
    }
}
```

Integration test:

```java
@Test
void customSearchFragmentExecutesAgainstElasticsearch() {
    repository.save(new Product("P-501", "SKU-501", "Mechanical Keyboard", "ACTIVE"));
    repository.save(new Product("P-502", "SKU-502", "Mechanical Keyboard Case", "INACTIVE"));
    operations.indexOps(Product.class).refresh();

    List<Product> results = repository.searchActiveByKeyword("keyboard");

    assertThat(results)
            .extracting(Product::getId)
            .contains("P-501")
            .doesNotContain("P-502");
}
```

This example verifies that the custom fragment is woven into the repository proxy, the query actually runs, and the status filter takes effect. If you only mock `ElasticsearchOperations`, the test will not catch field name or DSL errors.

### 8.1. Separate Unit Tests for Query Builders

If a query is complex and built inside a plain class, you can extract query construction into a function/builder to unit test the conditional branches.

For example:

```java
Query buildProductQuery(String keyword, String status) {
    // Return a Query based on the input criteria.
}
```

Unit tests can verify which filters the builder adds in each case. However, verifying that the query builder produces syntactically valid DSL with the right semantics still requires at least one repository integration test against real Elasticsearch.

## 9. Testing Service and Repository Together

In addition to service unit tests and repository integration tests, you can have a few service integration tests that run the entire service + repository + Elasticsearch stack.

For example:

```java
@Test
void registerRejectsExistingSkuUsingRealRepository() {
    repository.save(new Product("P-900", "SKU-900", "Existing", "ACTIVE"));
    operations.indexOps(Product.class).refresh();

    assertThatThrownBy(() -> productService.register(
            new Product(null, "SKU-900", "Duplicate", "ACTIVE")
    )).isInstanceOf(DuplicateProductSkuException.class);
}
```

This test verifies the service rule combined with a real repository query. It has a broader scope than a unit test and is slower, but it is useful for critical flows.

There is no need to run every service branch through real Elasticsearch. Keep most business logic in unit tests so tests stay fast, and pick a few important integration flows to verify that the layers collaborate properly.

## 10. Distinguishing `@SpringBootTest` and Test Slices

`@SpringBootTest` creates an application context according to the application's configuration. It is useful when you need to test the repository alongside real beans/configurations, though it may start more components than necessary.

A test slice narrows the context scope to a specific group of components. If your Spring Boot/Spring Data version provides an appropriate slice for Elasticsearch, you can use it to reduce startup time. Supported annotation names and auto-configuration depend on the version; check the list of test slices for your exact Spring Boot release.

If no suitable slice exists or you need to verify the full application configuration, `@SpringBootTest` combined with Testcontainers is a clear choice.

Do not use `@DataJpaTest` to test an Elasticsearch repository. It is a slice for JPA and does not configure Elasticsearch infrastructure.

## 11. Testcontainers and Connection Configuration

An integration test configuration must ensure Spring Boot connects to the container rather than a local Elasticsearch instance or production endpoint.

Example dynamic property configuration:

```java
@DynamicPropertySource
static void properties(DynamicPropertyRegistry registry) {
    registry.add("spring.elasticsearch.uris", elasticsearch::getHttpHostAddress);
}
```

The property name commonly used in modern Spring Boot is `spring.elasticsearch.uris`; older versions may use a different prefix. If the application needs username/password/TLS, register the corresponding properties from the container or test configuration.

Some notes:

- Pin the Elasticsearch image version instead of using `latest`.
- Choose a version compatible with Spring Data Elasticsearch and the Java API Client.
- Do not point integration tests at a shared cluster containing real data.
- Use a dedicated container so tests can delete/create indices without affecting others.
- If container security is enabled, configure credentials and certificates appropriate for the version.
- Wait for the container to be healthy before the application context creates the client.

## 12. Data Isolation Between Tests

Elasticsearch does not automatically roll back test data like a typical database transaction. `@Transactional` does not automatically delete indexed documents when a test finishes.

Isolation strategies:

### 12.1. Recreate the Index per Test

Delete the index and create a fresh mapping in `@BeforeEach`. This gives a clean state, but it can be time-consuming and is unsuitable if multiple tests run in parallel on the same index.

### 12.2. Use Unique IDs per Test

Generate IDs with a test/run prefix to avoid collisions:

```java
String id = "it-" + UUID.randomUUID();
```

After the test, delete the document by ID and refresh if needed. This works well when sharing an index within a test class, though it requires careful cleanup.

### 12.3. Dedicated Index per Suite

Use a dedicated index name such as `products-repository-it`. This separates test data from dev or other local indices. For parallel tests, you can generate index names per class/test run and pass the corresponding `IndexCoordinates` if the repository/operations allow dynamic configuration.

### 12.4. Do Not Depend on Test Ordering

Each test must prepare the data it needs. Do not write test B relying on a document created by test A. Whether tests run individually or in a different order, the results must remain the same.

## 13. Refresh and Consistency in Integration Tests

Get by ID is real-time by default; the Search API is near-real-time. This is a common reason repository integration tests become flaky.

Unstable example:

```java
repository.save(product);
assertThat(repository.findBySku(product.getSku())).isPresent();
```

`findBySku` is a search query. Without a refresh, the test may fail to see the document.

Clear approach:

```java
repository.save(product);
operations.indexOps(Product.class).refresh();

assertThat(repository.findBySku(product.getSku())).isPresent();
```

Do not use `Thread.sleep(1000)` to wait for a refresh. Sleeping depends on timing, machine load, and index configuration. Call refresh explicitly or use the `WAIT_UNTIL` refresh policy when a test needs to verify write visibility.

### 13.1. Testing the Difference Between GET and Search

If you want to verify the exact semantics:

1. Create an index with a controlled refresh interval, such as disabling auto refresh in the test.
2. Save the document.
3. `findById` can read the document immediately.
4. A derived search query may not see the document yet.
5. Refresh the index.
6. The search query sees the document.

Disabling the refresh interval must be configured appropriately for the version/API in use and restored if the test uses a long-lived index. For most repository tests, an explicit refresh before querying is sufficient; only write a separate test when you need to verify near-real-time behavior.

## 14. Testing Custom Routing

If an entity uses `@Routing` or repository operations use custom routing, integration tests need to verify both indexing and get/search.

Example:

```java
@Document(indexName = "orders-it")
@Routing("routing")
public class OrderDocument {
    @Id
    private String id;
    private String routing;
    private String customerId;
}
```

Tests should:

1. Index a document with a specific routing value.
2. Read by ID with the same routing and confirm it is found.
3. Try reading without routing or with a different routing value to verify the expected behavior.
4. Verify that the repository/service preserves routing consistently across save/get/delete.

Mocking `ElasticsearchOperations` does not verify that the request actually carries the routing parameter. This is why integration tests are needed for custom routing.

## 15. Testing Aggregations, Nested, and Geo Queries

Elasticsearch features that depend on mapping and engine behavior require integration tests:

- Aggregation: bucket counts, metric values, pipeline aggregations.
- Nested query: path and relationships between fields within the same nested object.
- Geo query: `geo_point`, radius, and distance sorting.
- Join/parent-child: join mapping, routing, and `has_child`/`has_parent`.
- Analyzer: tokenization, lowercase, stemming, or synonyms.
- Highlight/suggest: response metadata and field mapping.

Service tests can verify that the service calls the custom repository with appropriate parameters, but only Elasticsearch integration tests can verify that the query/mapping has the right semantics.

## 16. Testing Errors and Timeouts Across Layers

Service unit test:

- Mock the repository throwing a timeout or unavailable error.
- Verify that the service translates the error into a domain exception or appropriate fallback.
- Verify that validation errors or business errors are not retried.
- Verify that the retry policy is applied properly if the service owns the retry logic.

Repository integration test:

- Verify mapping rejection with invalid data.
- Verify query errors or missing index handling when those are supported scenarios.
- Verify timeout/connection behavior if an appropriate simulation environment is available.
- Verify optimistic concurrency/version conflict if a custom repository uses sequence numbers/versions.

Do not intentionally break a shared cluster to test infrastructure failures. Use a dedicated container or test double at the network/client boundary when simulating outages.

## 17. Reactive Service Tests and Repository Integration Tests

If the application uses `ReactiveElasticsearchRepository`, the layering principles remain the same:

- Service unit tests mock the reactive repository returning `Mono`/`Flux`.
- Repository integration tests use the real reactive repository connected to real Elasticsearch.
- Use `StepVerifier` to verify publisher signals and ordering.
- Use an explicit refresh when testing search visibility.

Service unit test example:

```java
when(repository.findBySku("SKU-1")).thenReturn(Mono.just(product));

StepVerifier.create(service.findRequired("SKU-1"))
        .expectNext(product)
        .verifyComplete();
```

Repository integration test example:

```java
StepVerifier.create(repository.save(product))
        .expectNextMatches(saved -> saved.getId().equals(product.getId()))
        .verifyComplete();

StepVerifier.create(operations.indexOps(Product.class).refresh())
        .verifyComplete();

StepVerifier.create(repository.findBySku(product.getSku()))
        .expectNextMatches(found -> found.getId().equals(product.getId()))
        .verifyComplete();
```

These examples use Reactor Test. Do not call `.block()` in services/controllers to make tests easier; tests can use StepVerifier to subscribe and verify the publisher.

## 18. Distinguishing Mock, Fake, Embedded, and Testcontainers

| Testing approach | Real Elasticsearch? | Best suited for |
|---|---|---|
| Mock repository | No. | Service unit tests. |
| In-memory fake repository | No. | Service logic needing a simple fake implementation. |
| Mock `ElasticsearchOperations` | No. | Service/custom adapter unit tests; verifying API-level interactions. |
| Legacy embedded Elasticsearch | Depends on solution, often does not reflect production version. | Should not be the default if not version-compatible. |
| Testcontainers Elasticsearch | Yes, runs in a container. | Repository integration tests and service integration tests. |
| Shared Elasticsearch test cluster | Yes. | Only with strict data/namespace management; prone to cross-test interference. |

Testcontainers is usually the practical choice because the version can be pinned, the environment is isolated, and tests can run in CI with Docker/a container runtime.

## 19. Choosing the Test Level Based on the Question

| Question to answer | Appropriate test |
|---|---|
| Does the service reject duplicate SKUs? | Service unit test. |
| Does the service throw NotFound when the repository returns empty? | Service unit test. |
| How does the API/service react when Elasticsearch is unavailable? | Service unit test with mocked error; add integration/contract test if real exception verification is needed. |
| Does `findBySku` generate the right query? | Repository integration test. |
| Does `@Field(Keyword)` create the right mapping? | Repository integration test. |
| Does the entity serialize/deserialize properly? | Repository integration test. |
| Does search after save find the document after refresh? | Repository integration test. |
| Does the `NativeQuery` aggregation return the right buckets? | Repository integration test. |
| Is custom routing sent properly? | Repository integration test. |
| Do service + repository collaborate properly on a critical flow? | Selective service integration test. |

There is no need to test everything at every layer. Place assertions at the layer that owns the behavior so failures clearly point to the root cause.

## 20. Organizing Test Sources

A simple structure:

```text
src
├── main
│   └── java/com/example/catalog
│       ├── product
│       │   ├── Product.java
│       │   ├── ProductRepository.java
│       │   └── ProductService.java
│       └── ...
└── test
    └── java/com/example/catalog
        ├── product
        │   ├── ProductServiceTest.java
        │   ├── ProductRepositoryIT.java
        │   └── ProductServiceIT.java
        └── support
            └── ElasticsearchTestContainerConfiguration.java
```

The `IT` suffix is commonly used for integration tests, though Gradle/Maven do not necessarily run every class with that suffix automatically under default configuration. Configure the appropriate test task/source set or plugin so integration tests actually run in CI.

Tasks can be separated:

```groovy
tasks.named('test') {
    useJUnitPlatform()
    exclude '**/*IT.class'
}

tasks.register('integrationTest', Test) {
    useJUnitPlatform()
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    include '**/*IT.class'
    shouldRunAfter tasks.test
}
```

This is an illustrative Gradle configuration; a project may use a separate source set, convention plugin, or different task. What matters is that the CI pipeline separates fast tests from container-based tests while still running integration tests at the appropriate stage.

## 21. Avoiding Testing Anti-Patterns

### 21.1. Mocking the Repository in a Test Called a Repository Integration Test

If the repository is mocked, the test does not verify Elasticsearch. Name tests according to their true scope: service unit test or service orchestration test.

### 21.2. Using Real Elasticsearch for Every Service Branch

This makes tests slow, hard to set up, and makes it harder to pinpoint business logic errors. Use mocks for most service branches; pick only the necessary integration flows.

### 21.3. Checking Only HTTP Status

Repository integration tests should inspect actual documents/queries, not just verify that the request did not throw an exception. For example, a query returning 0 results could still be a valid request with the wrong field name.

### 21.4. Relying on Leftover Data from Previous Tests

Order-dependent tests will flake when run individually, in parallel, or on CI. Prepare and clean up data explicitly.

### 21.5. Using Sleep to Wait for Refresh

Sleeping is not synchronized with Elasticsearch. Use the refresh API or the `WAIT_UNTIL` refresh policy.

### 21.6. Assuming `@Transactional` Will Roll Back Elasticsearch

Do not assume Elasticsearch repositories participate in transaction rollbacks like JPA. Tests need to delete indices/documents or use a dedicated namespace.

### 21.7. Using the `latest` Version for Containers

Test results can change when the image is updated. Pin the version and upgrade intentionally.

## 22. Example Test Matrix for ProductService/ProductRepository

| Test case | Service unit | Repository integration | Service integration |
|---|:---:|:---:|:---:|
| Reject creation when SKU already exists | Yes | Optional | Selective |
| Call save when SKU does not exist | Yes | Separate CRUD save | Selective |
| `findById` maps `_id` correctly | No | Yes | Optional |
| `findBySku` queries the right field | No | Yes | Optional |
| `sku` field is mapped as keyword | No | Yes | Optional |
| Elasticsearch timeout mapped to domain error | Yes, with mocked exception | Can test adapter/client | Selective |
| Save then search after refresh | No | Yes | Selective |
| Custom routing is passed properly | No | Yes | Selective |
| Aggregation query returns right metrics | No | Yes | Optional |
| API returns right status/error body | Controller/web test | Optional | Can use WebTestClient/MockMvc with suitable context |

The matrix prevents a single test from being tasked with verifying multiple layers at once. When a failure occurs, the team can easily identify whether to look at the service, mapping, query, or client configuration.

## 23. Process for Building a Test Suite

1. **Identify service responsibilities:** list rules, conditional branches, errors, and side effects.
2. **Write service unit tests:** mock the repository and assert business outcomes.
3. **Define the repository contract:** mapping, query methods, custom fragments, routing, and semantics to verify.
4. **Prepare the Elasticsearch test environment:** use Testcontainers with an appropriately pinned version.
5. **Create index/mapping:** use the same mapping strategy as production.
6. **Write repository integration tests:** verify CRUD, queries, serialization, refresh, and the Elasticsearch features in use.
7. **Isolate data:** recreate the index or use dedicated IDs/indices; do not rely on test ordering.
8. **Add selective service integration tests:** verify critical flows from the service to the real repository.
9. **Separate CI tasks:** run fast unit tests frequently and integration tests in a pipeline with container support.
10. **Keep tests deterministic:** pin versions, refresh explicitly, avoid sleep, and clean up cleanly.

## 24. Key Takeaways

- Service unit tests verify business logic and orchestration; repository integration tests verify real interaction with Elasticsearch.
- Mocking the repository in service tests keeps them fast and isolated, but does not verify mapping/query/serialization.
- Repository integration tests need the real repository proxy and real Elasticsearch or a compatible environment.
- Testcontainers helps launch version-pinned Elasticsearch and isolate data for CI.
- Verify `@Document`, `@Id`, `@Field`, mappings, query derivation, `NativeQuery`, custom routing, and converters at the integration layer.
- Get by ID has real-time semantics; search queries are near-real-time, so refresh explicitly in tests.
- Do not use `Thread.sleep` to wait for refresh, and do not assume `@Transactional` rolls back Elasticsearch data.
- Use unique IDs, dedicated indices, or index recreation so tests do not depend on one another.
- Testing service + repository together is only needed for selected critical flows; it does not replace fast unit tests.
- Pin an Elasticsearch image version compatible with Spring Data/Java API Client.
- Place tests at the right layer so failures pinpoint which responsibility has an issue.

Service unit tests and repository integration tests answer two different questions. Mocking the repository verifies that the service makes the right decisions when a dependency returns specific results or errors; Elasticsearch integration tests verify that the repository actually maps and queries data correctly on the engine. Deliberately combining both layers creates a fast, reliable test suite capable of catching bugs in both business logic and integration.

## References

- [Spring Data Elasticsearch — Testing](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/testing.html)
- [Spring Data Elasticsearch — Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/repositories.html)
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html)
- [Testcontainers — Elasticsearch Module](https://java.testcontainers.org/modules/elasticsearch/)
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/)
- [Mockito Documentation](https://javadoc.io/doc/org.mockito/mockito-core/latest/org/mockito/Mockito.html)
