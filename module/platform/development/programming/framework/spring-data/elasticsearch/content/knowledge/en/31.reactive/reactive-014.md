# Testing with StepVerifier and Real Elasticsearch Data

## 1. Purpose of Testing Reactive Elasticsearch Applications

A reactive Spring Data Elasticsearch application typically uses Mono<T> for operations returning at most one result and Flux<T> for streams that can emit multiple results. Repositories and ReactiveElasticsearchTemplate return these publishers so the application can chain queries, transform data, handle errors, and control flow.

Testing those publishers needs to verify two things:

1. The reactive chain emits the right signals: values, errors, or completion.
2. Persistence operations actually produce the expected state inside Elasticsearch.

Project Reactor provides StepVerifier to declare expectations on signal sequences. Testcontainers provides disposable Elasticsearch containers for testing real mappings, queries, repositories, and server behavior.

These two tools complement each other. StepVerifier verifies the reactive contract; a real Elasticsearch instance verifies integration behavior with the search engine.

For example, a test that only checks:

~~~java
StepVerifier.create(Mono.just("saved"))
    .expectNext("saved")
    .verifyComplete();
~~~

confirms a publisher emits the expected signal sequence. It does not prove the repository wrote a document, mappings are right, analyzers work, or Elasticsearch queries return accurate results.

Conversely, a test that merely calls block and compares objects can verify stored state, yet fails to describe signal ordering, error propagation, cancellation, or backpressure clearly.

This lesson combines both techniques to build integration tests for reactive Spring Data Elasticsearch.

## 2. Test Layers to Maintain

Not every test needs to spin up Elasticsearch. Choose the test type based on what you want to verify.

| Test type | Components | Purpose |
|---|---|---|
| Reactive unit test | Service and stubbed publishers | Verify business branches, DTO mapping, error handling |
| Publisher test | Mono, Flux, TestPublisher, PublisherProbe | Verify operators and subscription paths |
| Integration test | Reactive repository/template + real Elasticsearch | Verify mappings, queries, CRUD, and refresh behavior |
| End-to-end test | API or full application + real Elasticsearch | Verify configuration, serialization, and live request flow |

Unit tests remain valuable with mocked repositories. However, mocks cannot verify how Elasticsearch interprets Query DSL, applies analyzers, maps fields, handles version conflicts, or refreshes documents.

For engine-dependent behavior, run against a real Elasticsearch instance in tests. Testcontainers manages this instance alongside the JUnit lifecycle.

A solid integration test typically:

- Starts Elasticsearch matching the major version supported by the application.
- Creates the index and mappings under test.
- Writes data through the reactive API.
- Refreshes the index when the test searches newly written documents.
- Reads data back with a real query.
- Asserts both values and reactive signals.
- Cleans up data or the index after the test.

## 3. What Signals Does StepVerifier Verify?

StepVerifier belongs to the reactor-test artifact. It subscribes a test subscriber to the publisher under test and compares received signals against a declared script.

A Mono<T> can:

- Emit one onNext(T) followed by onComplete().
- Emit only onComplete() without any value.
- Emit onError(Throwable).

A Flux<T> can emit zero or more onNext signals and then complete or terminate with an error.

Example verifying a successful Mono:

~~~java
Mono<String> source = Mono.just("product-1");

StepVerifier.create(source)
    .expectNext("product-1")
    .expectComplete()
    .verify();
~~~

verify() actually triggers subscription and execution. Creating a Mono or Flux without subscribing means the underlying persistence operation may never execute.

You can use the shortcut:

~~~java
StepVerifier.create(repository.findById("product-1"))
    .expectNextMatches(product ->
        product.getId().equals("product-1")
    )
    .verifyComplete();
~~~

verifyComplete() both expects completion and runs verification. When an explicit timeout is desired, declare the terminal expectation and invoke verify(Duration):

~~~java
StepVerifier.create(repository.findById("product-1"))
    .expectNextMatches(product ->
        product.getId().equals("product-1")
    )
    .expectComplete()
    .verify(Duration.ofSeconds(10));
~~~

By default, verification methods have no timeout. If a publisher never emits a terminal signal, the test can hang indefinitely. For integration tests involving network I/O, set an explicit per-test timeout or configure StepVerifier's default timeout.

### Common Expectations

| Method | Purpose |
|---|---|
| expectNext(value) | Expects the next element to equal the specified value |
| expectNextMatches(predicate) | Checks the next element with a predicate |
| assertNext(consumer) | Runs assertions on the next element |
| consumeNextWith(consumer) | Consumes and inspects the next element |
| expectNextCount(n) | Expects exactly n subsequent elements |
| expectNextSequence(values) | Expects a sequence of values in order |
| expectComplete() | Expects the publisher to complete |
| expectError(type) | Expects an error of the specified type |
| expectErrorMatches(predicate) | Checks the error with a predicate |
| expectErrorMessage(message) | Checks the error message |
| thenAwait(duration) | Advances/waits for a duration in the scenario |
| thenRequest(n) | Requests n more elements to test backpressure |
| thenCancel() | Cancels the subscription |
| verify(duration) | Executes the scenario with a timeout |

Example verifying multiple results:

~~~java
StepVerifier.create(Flux.just("a", "b", "c"))
    .expectNext("a")
    .assertNext(value -> assertThat(value).isEqualTo("b"))
    .expectNext("c")
    .expectComplete()
    .verify(Duration.ofSeconds(2));
~~~

Example verifying an error:

~~~java
StepVerifier.create(Mono.error(
        new IllegalArgumentException("invalid product")
    ))
    .expectErrorMatches(error ->
        error instanceof IllegalArgumentException
            && error.getMessage().equals("invalid product")
    )
    .verify(Duration.ofSeconds(2));
~~~

### Naming Scenarios for Readable Failures

You can name the entire scenario using StepVerifierOptions:

~~~java
StepVerifierOptions options = StepVerifierOptions.create()
    .scenarioName("Save product and read back by ID");

StepVerifier.create(repository.save(product), options)
    .assertNext(saved ->
        assertThat(saved.getId()).isEqualTo(product.getId())
    )
    .expectComplete()
    .verify(Duration.ofSeconds(10));
~~~

You can also chain as("expectation description") after many expectation methods. When a StepVerifier expectation fails, these labels pinpoint which step failed.

## 4. Adding Test Dependencies

If the application already includes reactive Spring Data Elasticsearch and Reactor at runtime, tests typically add reactor-test, Testcontainers Elasticsearch, and JUnit Jupiter integration.

Gradle example with Testcontainers BOM:

~~~groovy
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("io.projectreactor:reactor-test")

    testImplementation(platform("org.testcontainers:testcontainers-bom:2.0.5"))
    testImplementation("org.testcontainers:testcontainers-elasticsearch")
    testImplementation("org.testcontainers:testcontainers-junit-jupiter")
}
~~~

If not using Spring Boot dependency management, declare compatible versions for Spring Data Elasticsearch, Reactor, and Testcontainers dependencies. Avoid mixing mismatched Testcontainers module versions in the same test runtime.

Equivalent Maven configuration:

~~~xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-elasticsearch</artifactId>
    <version>2.0.5</version>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-junit-jupiter</artifactId>
    <version>2.0.5</version>
    <scope>test</scope>
</dependency>
~~~

Choose an Elasticsearch image compatible with your Spring Data Elasticsearch version and production server version. For example, release train 2026.0 with Spring Data Elasticsearch 6.1.x aligns with Elasticsearch 9.4.7 per the compatibility matrix. Never pick an image just because it is the latest tag if your client and application do not yet support it.

For Spring Boot 4 examples using test slices and service connections, add the corresponding test modules:

~~~groovy
testImplementation("org.springframework.boot:spring-boot-testcontainers")
testImplementation("org.springframework.boot:spring-boot-data-elasticsearch-test")
~~~

## 5. Starting Elasticsearch with Testcontainers

Testcontainers runs the official Elasticsearch Docker image and exposes a dynamically mapped host port. Never hard-code host ports because the mapped port can vary on every container startup.

JUnit 5 example:

~~~java
import org.junit.jupiter.api.Test;
import org.testcontainers.elasticsearch.ElasticsearchContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
class ElasticsearchContainerIT {

    @Container
    static final ElasticsearchContainer elasticsearch =
        new ElasticsearchContainer(
            DockerImageName.parse(
                "docker.elastic.co/elasticsearch/elasticsearch:9.4.7"
            )
        );

    @Test
    void containerStarts() {
        assertThat(elasticsearch.isRunning()).isTrue();
    }
}
~~~

A static field shares the container across test methods in the class: it starts before the first test and stops after the last test. Declaring the container as an instance field makes Testcontainers restart it for every method, slowing down the suite.

Do not run multiple tests in parallel against a shared index if tests delete or overwrite each other's data. Use per-test indices or configure sequential execution for integration tests.

### Elasticsearch 8 and 9 Enable Security by Default

Starting with Elasticsearch 8, security and HTTPS are enabled by default. When testing with 8.x or 9.x images, the client must properly handle TLS and authentication.

With Spring Boot 4.1, you can combine ServiceConnection and Ssl so Boot detects the Elasticsearch container and configures SSL for the client automatically:

~~~java
import org.springframework.boot.data.elasticsearch.test.autoconfigure.DataElasticsearchTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.boot.testcontainers.service.connection.Ssl;
import org.junit.jupiter.api.Test;
import org.testcontainers.elasticsearch.ElasticsearchContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@DataElasticsearchTest
class ReactiveProductRepositoryContainerIT {

    @Container
    @ServiceConnection
    @Ssl
    static final ElasticsearchContainer elasticsearch =
        new ElasticsearchContainer(
            DockerImageName.parse(
                "docker.elastic.co/elasticsearch/elasticsearch:9.4.7"
            )
        );

    // Inject repository and ReactiveElasticsearchOperations here.
}
~~~

ServiceConnection supplies connection details to auto-configuration. Ssl instructs Spring Boot to handle the Elasticsearch container's TLS certificate. This is clean when your Spring Boot and Testcontainers versions support the corresponding service connection.

With Spring Boot 3.x, the DataElasticsearchTest package differs and service connection/SSL configuration may vary across minor versions. Use the exact package and SSL mechanism of your Spring Boot release line. If configuring manually via DynamicPropertySource, passing only URI and credentials is insufficient when TLS is active; the client must also trust the CA certificate provided by the container.

Never disable container security just to bypass SSL configuration if production uses TLS and authentication. Integration tests are far more valuable when connectivity matches real deployments.

## 6. Sample Entity and Reactive Repository

Example using a product index with simple fields:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "reactive-products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Boolean)
    private boolean active;

    public Product() {
    }

    public Product(
            String id,
            String name,
            String category,
            boolean active) {
        this.id = id;
        this.name = name;
        this.category = category;
        this.active = active;
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

    public void setCategory(String category) {
        this.category = category;
    }

    public boolean isActive() {
        return active;
    }
}
~~~

A reactive repository can declare query methods:

~~~java
import org.springframework.data.elasticsearch.repository.ReactiveElasticsearchRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ProductRepository
        extends ReactiveElasticsearchRepository<Product, String> {

    Flux<Product> findByCategory(String category);

    Flux<Product> findByCategoryOrderByNameAsc(String category);

    Mono<Product> findByName(String name);

    Mono<Long> countByCategory(String category);
}
~~~

Reactive Elasticsearch repositories use Project Reactor. Methods return Mono or Flux without manually wrapping synchronous results in publishers.

In a test slice, repositories and entities must live in packages scanned by Spring Boot. If using manual EnableReactiveElasticsearchRepositories, explicitly specify the repository packages.

## 7. Creating and Cleaning the Index for Each Test

Integration tests require isolated data. If an earlier test leaves documents behind, later tests may receive unexpected results.

ReactiveIndexOperations provides a reactive API to manage indices. You can delete any existing index and recreate it with mappings before each test.

~~~java
import java.time.Duration;

import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.elasticsearch.core.ReactiveElasticsearchOperations;
import org.springframework.data.elasticsearch.core.ReactiveIndexOperations;
import reactor.test.StepVerifier;

abstract class ReactiveElasticsearchTestSupport {

    @Autowired
    protected ReactiveElasticsearchOperations operations;

    protected ReactiveIndexOperations productIndex() {
        return operations.indexOps(Product.class);
    }

    @BeforeEach
    void recreateIndex() {
        StepVerifier.create(
                productIndex()
                    .delete()
                    .then(productIndex().createWithMapping())
            )
            .expectNext(true)
            .expectComplete()
            .verify(Duration.ofSeconds(30));
    }
}
~~~

delete() returns false if the index does not exist yet. You can therefore chain it before createWithMapping() without checking existence in a separate request.

createWithMapping() creates the index with settings and mappings derived from entity annotations. This also verifies the mapping metadata generated by Spring Data.

If a test requires manual index mappings, use create(settings, mapping) or put mappings explicitly and verify them against real Elasticsearch.

### Do Not Delete Indices Asynchronously Unawaited Between Tests

Since you are using the reactive API, keep index management composed as a Mono:

~~~java
Mono<Boolean> recreate = productIndex()
    .delete()
    .then(productIndex().createWithMapping());
~~~

Never call subscribe() in BeforeEach and let the test proceed immediately. When subscribe() returns, the asynchronous operation may not have finished yet. Use StepVerifier to wait for completion before the test begins.

JUnit lifecycle methods are inherently synchronous, so calling verify(Duration) to wait at the test boundary is appropriate. What you must avoid is blocking inside production reactive flows.

## 8. Testing Save and Read Back by ID

The first test confirms save returns the entity with its ID and Elasticsearch can read the document back.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import reactor.test.StepVerifier;

class ReactiveProductRepositoryCRUDIT
        extends ReactiveElasticsearchTestSupport {

    @Autowired
    ProductRepository repository;

    @Test
    void shouldSaveAndFindProductById() {
        Product product = new Product(
            "p-100",
            "Wireless Headphones",
            "audio",
            true
        );

        StepVerifier.create(repository.save(product))
            .assertNext(saved -> {
                assertThat(saved.getId()).isEqualTo("p-100");
                assertThat(saved.getName())
                    .isEqualTo("Wireless Headphones");
            })
            .expectComplete()
            .verify(Duration.ofSeconds(10));

        StepVerifier.create(repository.findById("p-100"))
            .assertNext(found -> {
                assertThat(found.getCategory()).isEqualTo("audio");
                assertThat(found.isActive()).isTrue();
            })
            .expectComplete()
            .verify(Duration.ofSeconds(10));
    }
}
~~~

findById normally uses Elasticsearch's GET-by-ID operation. GET is real-time in Elasticsearch, so no refresh wait is needed to read back a newly indexed document by ID.

This differs from search queries. Tests querying by category or derived query methods may require a refresh before reading.

When verifying that save() returns a properly mapped entity, assert its fields inside assertNext rather than checking only completion.

## 9. Testing Query Methods Requires Refreshing the Index

Elasticsearch is a near-real-time search engine. After indexing a document, GET by ID can see the data right away, whereas search does not necessarily see that document until the next refresh.

Never use Thread.sleep() to wait for refresh. Refresh timing varies with cluster settings and load, making tests both slow and flaky.

Use reactive index operations instead:

~~~java
@Test
void shouldFindProductsByCategoryAfterRefresh() {
    Product first = new Product(
        "p-101", "Headphones", "audio", true
    );

    Product second = new Product(
        "p-102", "Speaker", "audio", true
    );

    StepVerifier.create(
            repository.saveAll(Flux.just(first, second))
                .then(productIndex().refresh())
                .thenMany(repository.findByCategoryOrderByNameAsc("audio"))
        )
        .assertNext(product ->
            assertThat(product.getName()).isEqualTo("Headphones")
        )
        .assertNext(product ->
            assertThat(product.getName()).isEqualTo("Speaker")
        )
        .expectComplete()
        .verify(Duration.ofSeconds(20));
}
~~~

In this chain:

1. saveAll saves two documents.
2. then waits for all saves to finish.
3. refresh tells Elasticsearch to make changes searchable.
4. thenMany runs the query only after the refresh completes.
5. StepVerifier verifies the order and returned data.

ReactiveIndexOperations.refresh() returns Mono<Void>, so it signals completion without emitting a value. Use thenMany to transition to the search results Flux after refresh.

This prevents race conditions between writes and searches. Avoid inserting delayElement, Thread.sleep, or arbitrary waits to approximate refresh.

## 10. Testing Bulk Save and Document Counts

You can use saveAll to test saving multiple entities. When asserting counts, refresh before running search or count when searchable visibility is required.

~~~java
@Test
void shouldSaveAllProductsAndCountByCategory() {
    List<Product> products = List.of(
        new Product("p-201", "Keyboard", "accessories", true),
        new Product("p-202", "Mouse", "accessories", true),
        new Product("p-203", "Monitor", "display", true)
    );

    Mono<Long> count = repository.saveAll(products)
        .then(productIndex().refresh())
        .then(repository.countByCategory("accessories"));

    StepVerifier.create(count)
        .expectNext(2L)
        .expectComplete()
        .verify(Duration.ofSeconds(20));
}
~~~

saveAll returns Flux<S>. Use then(...) to wait for the Flux to complete before refreshing and counting.

If the test needs to assert every entity returned from saveAll, use expectNextCount(3) or collect into a list to assert. Do not assume bulk response order always matches input order unless the API or implementation guarantees that order.

Example asserting only the element count:

~~~java
StepVerifier.create(repository.saveAll(products))
    .expectNextCount(3)
    .expectComplete()
    .verify(Duration.ofSeconds(20));
~~~

If subsequent test steps perform searches, chain refresh into the same sequence rather than running two independent subscriptions.

## 11. Testing Empty Results

Reactive repositories normally represent a missing entity as Mono.empty(). For multi-result queries, when no documents match, the Flux completes without emitting any onNext signal.

Example:

~~~java
@Test
void shouldCompleteEmptyWhenProductDoesNotExist() {
    StepVerifier.create(repository.findById("missing-id"))
        .expectComplete()
        .verify(Duration.ofSeconds(10));
}
~~~

With a query method:

~~~java
@Test
void shouldReturnEmptyFluxWhenCategoryDoesNotExist() {
    StepVerifier.create(repository.findByCategory("unknown"))
        .expectComplete()
        .verify(Duration.ofSeconds(10));
}
~~~

Never use expectNext(null). Reactor forbids emitting null as an element of Mono or Flux.

If a service turns an empty result into a business error using switchIfEmpty, test both behaviors:

~~~java
Mono<Product> findRequired(String id) {
    return repository.findById(id)
        .switchIfEmpty(Mono.error(
            new ProductNotFoundException(id)
        ));
}
~~~

~~~java
StepVerifier.create(productService.findRequired("missing-id"))
    .expectErrorMatches(error ->
        error instanceof ProductNotFoundException
    )
    .verify(Duration.ofSeconds(10));
~~~

## 12. Testing Delete and Confirming the Document Is Gone

Reactive repositories provide delete methods returning publishers. You can assert deletion completes and then confirm the document no longer exists.

~~~java
@Test
void shouldDeleteProduct() {
    Product product = new Product(
        "p-301", "Portable Speaker", "audio", true
    );

    Mono<Boolean> existsAfterDelete = repository.save(product)
        .then(repository.deleteById("p-301"))
        .then(productIndex().refresh())
        .then(repository.existsById("p-301"));

    StepVerifier.create(existsAfterDelete)
        .expectNext(false)
        .expectComplete()
        .verify(Duration.ofSeconds(20));
}
~~~

This is a single reactive chain: save, delete, refresh, and check existence. If a test calls repository.deleteById(id) and immediately searches, results may be affected by refresh timing.

If you only need to confirm the delete publisher completes, you can test:

~~~java
StepVerifier.create(repository.deleteById("p-301"))
    .expectComplete()
    .verify(Duration.ofSeconds(10));
~~~

However, that test alone does not prove the document disappeared from the index. Integration tests should include at least one check verifying post-delete state.

## 13. Testing Mappings and Data Types

One of the strongest reasons to test against real Elasticsearch is verifying mappings generated from annotations.

For example, the category field is declared as Keyword, so exact term queries should match the full value. If accidentally mapped as Text, queries and aggregations behave differently.

You can inspect mappings via index operations:

~~~java
@Test
void shouldCreateIndexWithExpectedMapping() {
    StepVerifier.create(productIndex().getMapping())
        .assertNext(mapping -> {
            assertThat(mapping.toJson())
                .contains("\"category\"");
            assertThat(mapping.toJson())
                .contains("\"keyword\"");
        })
        .expectComplete()
        .verify(Duration.ofSeconds(10));
}
~~~

Return types of mapping APIs and Document serialization depend on your Spring Data Elasticsearch version. For strict assertions, parse the mapping into JSON structures or use client APIs to inspect property types instead of relying solely on substring checks.

Mapping tests should focus on critical properties:

- Field types (keyword, text, date, nested, numeric).
- Analyzer and search analyzer settings.
- Multi-fields.
- Normalizers.
- Dynamic mapping rules.
- Routing and version metadata.
- Settings affecting search behavior.

Do not just assert an entity carries annotations. Tests should verify Elasticsearch accepts the mapping and real queries behave as intended.

## 14. Testing Custom Queries and Analyzers with Real Data

A simple repository query method does not cover all Query DSL scenarios. If your application uses @Query, NativeQuery, Criteria, or custom analyzers, index a purposeful dataset and assert real results from Elasticsearch.

Service example:

~~~java
public Flux<Product> activeProducts(String category) {
    return repository.findByCategory(category)
        .filter(Product::isActive);
}
~~~

Test:

~~~java
@Test
void shouldReturnOnlyActiveProducts() {
    List<Product> products = List.of(
        new Product("p-401", "Headphones", "audio", true),
        new Product("p-402", "Speaker", "audio", false)
    );

    StepVerifier.create(
            repository.saveAll(products)
                .then(productIndex().refresh())
                .thenMany(productService.activeProducts("audio"))
        )
        .assertNext(product ->
            assertThat(product.getId()).isEqualTo("p-401")
        )
        .expectComplete()
        .verify(Duration.ofSeconds(20));
}
~~~

This example tests both the repository query and the service's filter operator. When filters are pushed down into Elasticsearch via Query DSL, tests should invoke that exact method to exercise the query engine.

For full-text search, test data should include cases handled differently by analyzers:

- Uppercase and lowercase text.
- Punctuation.
- Accented and unaccented characters.
- Tokenization boundaries.
- Stop words.
- Synonyms.
- Prefixes or n-grams.
- Languages supported by the analyzer.

Do not test with an overly trivial string and conclude your production analyzer works properly.

## 15. Testing Errors and Exception Translation

The reactive client can emit errors when:

- Elasticsearch is unreachable.
- Authentication or TLS fails.
- The index does not exist.
- Mappings reject the payload.
- Query DSL is invalid.
- A version conflict occurs.
- A request times out or the server returns an error.

StepVerifier can assert errors propagated by the publisher:

~~~java
StepVerifier.create(
        repository.save(new Product(
            "p-501", null, "audio", true
        ))
    )
    .expectError()
    .verify(Duration.ofSeconds(10));
~~~

The snippet above only emits an error if the application or mapping enforces a constraint rejecting null values. Elasticsearch does not automatically treat every missing field as an error. Therefore, never write tests assuming Java fields are rejected by Elasticsearch unless mappings or validation enforce it.

To test mapping errors, define a mapping with strict field types and send incompatible types through the real write path. Assert the exception class or cause matching your Spring Data and client version.

Do not hard-code exact exception classes copied from a different version. Spring Data translates exceptions, yet concrete exception classes depend on the underlying error and library release.

## 16. Testing Validation Before Calling Elasticsearch

Many business errors should be rejected before sending a request to Elasticsearch. These can be tested with unit tests without starting a container.

Example:

~~~java
public Mono<Product> create(Product product) {
    if (product.getName() == null || product.getName().isBlank()) {
        return Mono.error(
            new IllegalArgumentException("Product name is required")
        );
    }

    return repository.save(product);
}
~~~

Test:

~~~java
@Test
void shouldRejectProductWithoutName() {
    Product invalid = new Product(
        "p-601", " ", "audio", true
    );

    StepVerifier.create(productService.create(invalid))
        .expectErrorMatches(error ->
            error instanceof IllegalArgumentException
                && error.getMessage().equals(
                    "Product name is required"
                )
        )
        .verify(Duration.ofSeconds(2));
}
~~~

This is a unit test for the validation branch. If you want to verify the repository was never called, use mocks or PublisherProbe/Mockito verifyNoInteractions per your service design. No Elasticsearch container is needed for a simple validation guard.

Integration tests should still exercise the valid write path to confirm the service actually persists data.

## 17. RefreshPolicy and Data Visibility in Tests

Spring Data Elasticsearch defines RefreshPolicy:

| Policy | Behavior |
|---|---|
| NONE | Requests no special refresh; uses cluster default behavior |
| IMMEDIATE | Refreshes immediately after the write operation |
| WAIT_UNTIL | Waits until the next refresh makes changes searchable |

You can derive an operations instance with a specific policy:

~~~java
ReactiveElasticsearchOperations testOperations =
    operations.withRefreshPolicy(RefreshPolicy.WAIT_UNTIL);
~~~

Example:

~~~java
StepVerifier.create(testOperations.save(product, IndexCoordinates.of("reactive-products")))
    .expectNextMatches(saved ->
        saved.getId().equals(product.getId())
    )
    .expectComplete()
    .verify(Duration.ofSeconds(20));
~~~

Exact save signatures have overloads for entity and index. Use the overload matching your project's Spring Data Elasticsearch version.

In integration tests, two common ways to guarantee searchable data are:

1. Calling ReactiveIndexOperations.refresh() after seeding data.
2. Using WAIT_UNTIL on writes that must be searchable immediately.

IMMEDIATE can simplify tests yet triggers extra refreshes and segment overhead. Never enable immediate refresh on every production write just to make tests easier to write.

When using default repository implementations, repository refresh behavior can differ from template operations depending on configuration and version. Verify actual policy behavior instead of assuming all save APIs share identical semantics.

## 18. Never Use Thread.sleep to Wait for Elasticsearch

Unreliable example:

~~~java
repository.save(product).block();

Thread.sleep(1000);

List<Product> products = repository.findByCategory("audio")
    .collectList()
    .block();
~~~

This code has multiple flaws:

- block prevents describing publisher behavior with StepVerifier.
- One second can be too short when the cluster is busy.
- One second can be needlessly slow when the cluster is idle.
- Tests become flaky in CI.
- Two independent subscriptions obscure operation ordering.

Clearer alternative:

~~~java
StepVerifier.create(
        repository.save(product)
            .then(productIndex().refresh())
            .thenMany(repository.findByCategory("audio"))
    )
    .expectNextMatches(found ->
        found.getId().equals(product.getId())
    )
    .expectComplete()
    .verify(Duration.ofSeconds(20));
~~~

Here refresh is a step inside the reactive chain. The query runs only after refresh finishes.

## 19. Distinguishing Real-Time GET from Near-Real-Time Search

Elasticsearch has two read behaviors to keep in mind:

- GET document by ID is real-time.
- Search reads refreshed segments, so it is near-real-time.

Consequently, a save-then-findById test can succeed immediately, while a save-then-search-by-category test needs a refresh.

| Test case | Refresh needed before reading? |
|---|---|
| save() then findById() | Usually no, because GET is real-time |
| save() then existsById() | Usually no, because it checks by ID |
| save() then field query method | May be needed |
| saveAll() then Search API | May be needed |
| save() then aggregation | Needed if the aggregation must include the new document |
| delete() then Search API | Needed for search results to reflect the new state |

If a test specifically verifies refresh semantics, isolate that test. Never accidentally rely on an environment's default refresh interval.

## 20. Testing Reactive Callbacks and Auditing

Spring Data Elasticsearch has dedicated reactive entity callbacks, such as:

- ReactiveBeforeConvertCallback.
- ReactiveAfterSaveCallback.
- ReactiveAfterLoadCallback.
- ReactiveAfterConvertCallback.
- ReactiveAuditingEntityCallback.

Synchronous callbacks are not automatically invoked by the reactive template. Therefore, when using the reactive API, register and test reactive callbacks directly.

Before-convert callback example:

~~~java
import org.reactivestreams.Publisher;
import org.springframework.data.elasticsearch.core.event.ReactiveBeforeConvertCallback;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class ProductDefaultsCallback
        implements ReactiveBeforeConvertCallback<Product> {

    @Override
    public Publisher<Product> onBeforeConvert(
            Product product,
            IndexCoordinates index) {

        if (product.getCategory() == null) {
            product.setCategory("general");
        }

        return Mono.just(product);
    }
}
~~~

An integration test can save an entity missing category via the reactive repository and read it back by ID:

~~~java
@Test
void shouldApplyReactiveBeforeConvertCallback() {
    Product product = new Product(
        "p-701", "Desk Lamp", null, true
    );

    StepVerifier.create(repository.save(product))
        .assertNext(saved ->
            assertThat(saved.getCategory()).isEqualTo("general")
        )
        .expectComplete()
        .verify(Duration.ofSeconds(10));

    StepVerifier.create(repository.findById("p-701"))
        .assertNext(found ->
            assertThat(found.getCategory()).isEqualTo("general")
        )
        .expectComplete()
        .verify(Duration.ofSeconds(10));
}
~~~

To confirm the callback bean is actually registered in the application context, use a test slice or SpringBootTest importing the callback configuration. If the callback is not loaded, the test only verifies repository behavior without exercising the callback.

For auditing, enable EnableReactiveElasticsearchAuditing and provide a ReactiveAuditorAware if the entity uses CreatedBy or LastModifiedBy. A fixed auditor can be used in test configuration for deterministic assertions.

## 21. Testing Reactor Context

Some applications propagate tenant IDs, security principals, or correlation IDs through Reactor Context. StepVerifier supports verifying context passed into a publisher.

Example:

~~~java
StepVerifier.create(
        Mono.deferContextual(context ->
            Mono.just(context.get("tenantId"))
        ),
        StepVerifierOptions.create()
            .withInitialContext(Context.of("tenantId", "tenant-7"))
    )
    .expectAccessibleContext()
    .contains("tenantId", "tenant-7")
    .then()
    .expectNext("tenant-7")
    .expectComplete()
    .verify(Duration.ofSeconds(2));
~~~

For Elasticsearch, context can identify a tenant or actor at the service layer, allowing tests to assert queries or callbacks use the right value.

However, do not assume Reactor Context automatically turns into Elasticsearch routing or security metadata. Application code must explicitly translate context into query filters, routing, or audit actors.

## 22. Testing Backpressure and Cancellation

Flux can emit multiple results. If a service must honor backpressure, StepVerifier lets you control how many elements are requested.

Example:

~~~java
StepVerifier.create(
        repository.findByCategory("audio"),
        0
    )
    .thenRequest(1)
    .expectNextCount(1)
    .thenRequest(1)
    .expectNextCount(1)
    .thenCancel()
    .verify(Duration.ofSeconds(10));
~~~

This scenario verifies the consumer requests elements one by one and then cancels the subscription.

With real Elasticsearch queries, cancellation may occur after a request has already reached the server. Never assume every cancellation immediately stops all work inside Elasticsearch. This test verifies client-side publisher behavior; deeper verification of resource usage or cancellation propagation requires dedicated instrumentation and tests.

## 23. Virtual Time Does Not Replace Real Elasticsearch

StepVerifier.withVirtualTime is helpful for publishers with timers, delays, retry backoff, or intervals:

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofHours(1))
    )
    .expectSubscription()
    .thenAwait(Duration.ofHours(1))
    .expectNext(0L)
    .expectComplete()
    .verify(Duration.ofSeconds(2));
~~~

Virtual time controls Reactor's scheduler. It does not speed up Elasticsearch's clock, the network, or the index refresh engine.

Never use virtual time to simulate indexing a document and waiting for Elasticsearch to refresh. Call the refresh API or use an appropriate refresh policy instead.

If a service uses backoff retries before calling Elasticsearch, split the retry policy into a unit test with virtual time and test the real repository path with integration tests.

## 24. Using TestPublisher and PublisherProbe Properly

reactor-test also provides TestPublisher and PublisherProbe.

TestPublisher lets you emit arbitrary signals to test operators or service logic without Elasticsearch:

~~~java
TestPublisher<String> publisher = TestPublisher.create();

StepVerifier.create(
        publisher.flux().map(String::toUpperCase)
    )
    .then(() -> publisher.emit("audio", "video"))
    .expectNext("AUDIO", "VIDEO")
    .expectComplete()
    .verify(Duration.ofSeconds(2));
~~~

PublisherProbe helps confirm whether an alternative publisher—such as a switchIfEmpty branch—was actually subscribed to.

These tools are great for reactive unit tests. Never use them as substitutes for integration tests when confirming Elasticsearch actually stores and finds documents.

## 25. Using DataElasticsearchTest vs. SpringBootTest?

Spring Boot provides DataElasticsearchTest to narrow the context to Elasticsearch data components. Test slices usually fit when only repositories, entity mappings, and templates are needed.

Use SpringBootTest when tests require the full application context, such as:

- Services with many dependencies.
- Reactive security configuration.
- Custom converters or callbacks configured at the application layer.
- WebFlux controllers and services together.
- Routing or tenant resolution beans.

| Annotation | Scope | When suitable |
|---|---|---|
| DataElasticsearchTest | Elasticsearch data components | Repositories, mappings, templates |
| SpringBootTest | Full application context | Multi-bean integration flows |
| Plain JUnit test | No Spring context | Publisher utilities, validation, mappers |

In Spring Boot 4, DataElasticsearchTest resides in org.springframework.boot.data.elasticsearch.test.autoconfigure. In Spring Boot 3.x, the common package is org.springframework.boot.test.autoconfigure.data.elasticsearch.

When a test slice does not automatically load a needed service or callback bean, import that specific configuration via Import rather than booting the entire application context.

## 26. DynamicPropertySource When Not Using ServiceConnection

If your Spring Boot version or project setup cannot use ServiceConnection, DynamicPropertySource lets you register properties dynamically after Testcontainers starts.

General example:

~~~java
@Container
static final ElasticsearchContainer elasticsearch =
    new ElasticsearchContainer(ELASTICSEARCH_IMAGE);

@DynamicPropertySource
static void elasticsearchProperties(
        DynamicPropertyRegistry registry) {

    registry.add(
        "spring.elasticsearch.uris",
        elasticsearch::getHttpHostAddress
    );
}
~~~

This only illustrates supplying the URI to client configuration. Because Elasticsearch 8/9 enables HTTPS and authentication by default, the application also needs username, password, and SSL trust settings. getHttpHostAddress() does not configure TLS certificates for the client.

When using TLS, prefer Ssl/ServiceConnection if supported by Spring Boot, or configure the client bean with the container's CA certificate. Never disable SSL verification in tests arbitrarily and treat it as equivalent to production.

Dynamic properties have high precedence in Spring TestContext, making them well suited for swapping service addresses per test run.

## 27. Testing Data with ReactiveElasticsearchOperations

Not every test needs a repository. When testing a specific query, inject ReactiveElasticsearchOperations directly.

Example saving and reading with operations:

~~~java
@Test
void shouldUseReactiveOperationsForSaveAndSearch() {
    Product product = new Product(
        "p-801", "Studio Monitor", "audio", true
    );

    Mono<Product> saveAndRefresh = operations.save(product)
        .flatMap(saved ->
            productIndex().refresh().thenReturn(saved)
        );

    StepVerifier.create(
            saveAndRefresh.flatMapMany(saved ->
                operations.search(
                    Query.findAll(),
                    Product.class
                )
            )
        )
        .expectNextMatches(hit ->
            hit.getContent().getId().equals("p-801")
        )
        .expectComplete()
        .verify(Duration.ofSeconds(20));
}
~~~

Search signatures and return types can differ across overloads. Using ReactiveElasticsearchOperations.search(Query, Class<T>) emits SearchHit<T>; if using another overload, verify the exact return type in your project version.

The key is keeping save, refresh, and search inside a single reactive chain so execution order is guaranteed.

For complex Query DSL, keep query builders inside the service and test through the service itself. If tests build a separate query from production code, tests can pass while production queries remain broken.

## 28. Deterministic Test Data

Integration tests need small datasets specifically crafted to distinguish edge cases.

Example dataset for categories:

| ID | Name | Category | Active |
|---|---|---|---|
| p-1 | Headphones | audio | true |
| p-2 | Speaker | audio | false |
| p-3 | Keyboard | accessories | true |

With this dataset you can verify:

- Querying category audio returns exactly two documents.
- Filtering active keeps only p-1.
- Sorting by name yields deterministic ordering.
- Counting category audio equals two.
- Deleting p-2 leaves count at one after refresh.
- Searching a non-existent category returns an empty Flux.

Avoid random IDs for assertions if tests verify ordering or exact comparisons. Deterministic IDs inside an isolated test index work cleanly.

If generating random data for load tests, fix a seed so failures are reproducible.

## 29. Running Multiple Test Methods and Parallel Execution

Testcontainers JUnit Jupiter supports both static containers shared across methods and instance containers started per method.

With a static container, each test method still needs data isolation. You can:

- Delete and recreate the index before each test.
- Use a unique index name per test.
- Prefix IDs per test.
- Clean up documents after the test completes.

Never let two parallel tests delete the same shared index.

Testcontainers' JUnit Jupiter integration is primarily tested with sequential execution; parallel execution can cause unexpected interference when containers or data are shared. If enabling parallel execution, design explicit index isolation and lifecycles and verify concurrency behavior thoroughly.

## 30. Performance Testing Is Not Functional Testing

An integration test with a handful of documents only verifies correctness. It does not prove the application can handle millions of documents or high concurrent request rates.

Never use the execution time of a small JUnit test as a benchmark. Performance depends on:

- Index size and structure.
- Shard and replica counts.
- Mappings, analyzers, and aggregations.
- Refresh intervals.
- Concurrent request volume.
- Network, CPU, heap, and disk performance.
- Cache state.
- Response payload sizes and consumer speed.

When benchmarking, use a dedicated environment and realistic workload with representative data, measuring latency percentiles, throughput, heap usage, and cluster load.

## 31. Common Pitfalls

**Creating a publisher without calling verify.** No subscription occurs, so persistence operations never run.

**Calling subscribe in tests without waiting.** Tests can finish before Elasticsearch operations complete.

**Calling block everywhere.** This obscures reactive signal semantics and creates brittle ordering. Use StepVerifier on the publisher under test.

**Using Thread.sleep to wait for refresh.** Fixed waits cause flakiness. Use ReactiveIndexOperations.refresh() or a refresh policy.

**Confusing GET by ID with Search.** Real-time GET can see new documents before search does.

**Mocking repositories and assuming mappings are valid.** Mocks do not run the query engine or validate real mappings.

**Using embedded fakes instead of Elasticsearch for Query DSL tests.** Analyzers, mappings, aggregations, and refresh require the real engine.

**Not resetting the index.** Leftover data from earlier tests skews counts and ordering.

**Running parallel tests on the same index.** One test deleting the index while another searches causes sporadic failures.

**Omitting timeouts on StepVerifier.** Hung networks or non-terminating publishers can stall tests indefinitely.

**Using virtual time to wait for Elasticsearch refresh.** Virtual schedulers do not control the real server.

**Expecting null to be emitted by a Mono.** Reactor does not emit null; missing data is represented by empty completion.

**Asserting only one element and ignoring the rest.** For Flux, verify element counts or terminal signals so unexpected extra items do not slip by.

**Assuming bulk save order always matches input order.** Only assert order when queries specify sorting or the contract guarantees it.

**Using an Elasticsearch image incompatible with the client.** Tests must run on a server version supported by your Spring Data line.

**Disabling security/TLS in tests without testing production config.** Doing so misses certificate, authentication, and connection detail bugs.

**Using test slices while forgetting callback/service beans.** DataElasticsearchTest narrows component scanning; import required beans or use SpringBootTest.

**Testing reactive services without verifying persisted data.** A publisher can emit expected mock objects without saving anything to Elasticsearch.

## 32. Workflow for Writing a Complete Integration Test

A test can follow this sequence:

1. Start Elasticsearch via Testcontainers.
2. Configure the Spring Data reactive client to point to the container.
3. Create the index and mapping with reactive index operations.
4. Seed documents through the repository or template.
5. Use StepVerifier to confirm save publishers complete.
6. Refresh the index if the next step uses the Search API.
7. Execute real queries via the repository or template.
8. Use assertNext, expectNextCount, or collectList to verify results.
9. Verify terminal signals with expectComplete or expectError.
10. Supply timeouts to prevent hanging tests.
11. Delete the index or data to keep subsequent tests independent.

Combined example test:

~~~java
@Test
void shouldIndexSearchAndDeleteProduct() {
    Product product = new Product(
        "p-901", "Noise Cancelling Headphones", "audio", true
    );

    Mono<Boolean> existsAfterDelete = repository.save(product)
        .then(productIndex().refresh())
        .then(repository.findByCategory("audio").collectList())
        .flatMap(found -> {
            assertThat(found)
                .extracting(Product::getId)
                .contains("p-901");

            return repository.deleteById("p-901")
                .then(productIndex().refresh())
                .then(repository.existsById("p-901"));
        });

    StepVerifier.create(existsAfterDelete)
        .expectNext(false)
        .expectComplete()
        .verify(Duration.ofSeconds(30));
}
~~~

This test verifies both the operator sequence and state inside Elasticsearch. If any step fails, the publisher terminates with an error and StepVerifier fails the test.

In larger test suites, split behaviors into focused tests: save/read, query/search, delete, callbacks, errors, and refresh. Reserve end-to-end combined tests for key business workflows.

## Conclusion

StepVerifier lets you test Mono and Flux by declaring expected signals, value sequences, errors, completion, cancellation, and backpressure. Calling verify() triggers subscription; always include timeouts for tests doing network I/O.

To verify reactive Spring Data Elasticsearch works properly against the search engine, run integration tests against real Elasticsearch using Testcontainers. Recreate indices and mappings per test, write data via reactive repositories or templates, refresh before searching, and verify outcomes with StepVerifier. Use GET by ID for real-time reads and the Search API when testing search visibility.

Never replace mapping or Query DSL tests with mocks, never use Thread.sleep() to wait for refresh, and never call block() arbitrarily inside reactive chains. Combining unit tests for business logic with integration tests for engine behavior creates a fast, reliable test suite capable of catching real defects.

## References

- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Project Reactor — StepVerifier API](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html)
- [Spring Data Elasticsearch — Reactive Elasticsearch Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/6.1/elasticsearch/repositories/reactive-elasticsearch-repositories.html)
- [Spring Data Elasticsearch — Version compatibility](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/versions.html)
- [Spring Data Elasticsearch — ReactiveElasticsearchTemplate API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/ReactiveElasticsearchTemplate.html)
- [Spring Data Elasticsearch — ReactiveElasticsearchOperations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/ReactiveElasticsearchOperations.html)
- [Spring Data Elasticsearch — ReactiveIndexOperations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/ReactiveIndexOperations.html)
- [Spring Boot — Working with Elasticsearch](https://docs.spring.io/spring-boot/reference/data/nosql.html)
- [Spring Boot — Testcontainers and Service Connections](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
- [Testcontainers — Elasticsearch module](https://java.testcontainers.org/modules/elasticsearch/)
- [Testcontainers — JUnit Jupiter integration](https://java.testcontainers.org/test_framework_integration/junit_5/)
