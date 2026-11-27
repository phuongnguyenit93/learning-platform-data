# Index Isolation Between Test Cases and Data Cleanup

Integration tests with Spring Data Elasticsearch typically write and read real data from an Elasticsearch cluster. If multiple tests share one index, data from an earlier test can affect subsequent tests: search results contain extra documents, counts are wrong, old documents get overwritten, or one test deletes data another test is using.

The issue becomes sharper when tests run in parallel on developer machines or CI. Two tests may concurrently create documents with the same ID, delete the index, or alter mappings. Results then depend on scheduling order rather than the logic under test.

A reliable approach is creating a dedicated index per test case or test class, writing data to that exact index, refreshing when immediate reads after writes are needed, and deleting the index during teardown. With Spring Data Elasticsearch, `IndexOperations` manages index lifecycle and `IndexCoordinates` specifies the target index for `ElasticsearchOperations`.

When a test uses a repository whose entity has `@Document(indexName = "...")`, note that the repository generally reads the index from entity metadata. Repository methods do not automatically adopt a random per-test index. This lesson clearly separates both approaches so you do not mistakenly assume creating a new index automatically redirects repositories to that index.

## 1. Why Is Index Isolation Between Tests Necessary?

Suppose two tests share the `products-test` index:

~~~text
Test A:
  index product P-1
  assert count = 1

Test B:
  index product P-2
  assert count = 1
~~~

If Test B runs after Test A without cleanup, the count may equal 2. If Test A deletes the whole index while Test B runs, Test B can hit an index-not-found error. If both use ID `P-1`, one test can overwrite the other's document.

Common forms of cross-test contamination:

- **Leftover data:** an earlier test leaves documents behind, breaking assertions in later tests.
- **Duplicate document IDs:** two tests write the same ID and overwrite each other.
- **Accidental deletion:** one test's teardown deletes an index or data another test relies on.
- **Mutated mappings/settings:** a test alters analyzers, mappings, or aliases, changing the environment for other tests.
- **Unsynchronized refresh:** a test writes and searches immediately, missing documents not yet refreshed.
- **Parallel execution:** interleaved create, write, refresh, and delete steps create race conditions.
- **Mid-test failure:** temporary indices remain on the cluster and pollute subsequent runs.

A dedicated index gives each test an independent data namespace. Deleting the entire index afterward also resets mapping, settings, alias, and document state cleanly.

## 2. Isolation Levels

Not every test needs a brand new index. Choose the isolation level based on the resource scope the test touches.

| Scope | Approach | Best suited for |
| --- | --- | --- |
| Unit test | Mock `ElasticsearchOperations` or repository | Logic testing that does not need real Elasticsearch |
| Test method | Dedicated index per test method | Parallel integration tests or per-test custom mapping/data |
| Test class | Dedicated index per test class | Methods in the class share mappings and clean documents between tests |
| Test run | Dedicated prefix or namespace per CI run | Multiple test classes or workers sharing one cluster |
| Dedicated cluster per suite | Dedicated container/cluster for the entire suite | Isolating cluster-wide settings, plugins, or security configuration |

A common pattern is running one Elasticsearch container for the test suite while creating a separate index per test method. This avoids starting a cluster for every test while keeping data isolated.

### 2.1. Unit Tests Do Not Need Real Indices

If you only verify that a service calls the right repository method, mock the repository. If verifying a query builder, inspect the query structure or mock `ElasticsearchOperations`.

Do not create real indices for every unit test; starting clusters and mappings slows tests down and couples unit tests to infrastructure.

### 2.2. Integration Tests Need Real Elasticsearch

When verifying mappings, analyzers, nested queries, sorting, aggregations, repository proxies, or specific Elasticsearch behavior, run integration tests against a real Elasticsearch instance.

Testcontainers usually fits well because each CI run can start a suite-dedicated cluster and stop the container upon completion. Pin an image version compatible with the Elasticsearch Java API Client and Spring Data Elasticsearch used by your project.

## 3. Naming Dedicated Test Indices

Index names should be recognizable, valid under Elasticsearch naming rules, and collision-free across concurrent tests.

An easy-to-operate convention:

~~~text
it-<module>-<test-class>-<test-method>-<run-token>
~~~

Examples:

~~~text
it-catalog-productsearch-searchbybrand-a13f92c1
it-catalog-productsearch-emptyresult-7bd421e0
it-order-orderrepository-save-4d90a8b2
~~~

Include:

- A fixed prefix such as `it-` to identify test indices.
- Module or domain name for traceability.
- Normalized test class/method name if helpful.
- A random token to avoid collisions across processes, CI jobs, and runs.

### 3.1. Index Naming Rules

Elasticsearch index names have constraints, notably:

- Must be lowercase.
- Cannot contain spaces or forbidden characters like backslashes, slashes, asterisks, question marks, double quotes, less-than/greater-than signs, pipes, commas, or hashes.
- Cannot start with underscores, hyphens, or plus signs.
- Must not exceed the maximum index name length.
- Avoid overly long names because test method names and tokens concatenate.

Using the `it-` prefix ensures names start with a valid character and separates test indices from application indices.

### 3.2. Generating a Unique Token

You can use a slice of a UUID:

~~~java
import java.util.UUID;

String token = UUID.randomUUID()
    .toString()
    .replace("-", "")
    .substring(0, 8);

String indexName = "it-products-" + token;
~~~

To include the test method name for traceability:

~~~java
String safeMethodName = testMethodName
    .toLowerCase(Locale.ROOT)
    .replaceAll("[^a-z0-9_-]", "-");

String indexName = "it-products-" + safeMethodName + "-" + token;
~~~

Do not use the method name alone as the index name, because the same method can run concurrently across modules, forks, or CI jobs.

### 3.3. Per-Test-Run Tokens

In CI, you can generate a `TEST_RUN_ID` at the start of the job and share it as a prefix across all indices in that job:

~~~text
it-<run-id>-products-<method-token>
~~~

Benefits:

- Find all indices created by a given CI run.
- Clean up leftover resources after a cancelled job.
- Avoid deleting indices belonging to another run.
- Separate data across parallel workers.

Never embed secret tokens or PII in index names. Index names appear in logs, metrics, and cluster APIs.

## 4. Using IndexOperations to Create and Delete Indices

Spring Data Elasticsearch provides `IndexOperations` to manage indices:

- Create an index.
- Check whether an index exists.
- Create and update mappings.
- Read mappings/settings.
- Refresh an index.
- Delete an index.
- Manage aliases and other index-level operations.

Obtain `IndexOperations` from `ElasticsearchOperations`:

~~~java
IndexOperations entityIndexOperations =
    operations.indexOps(Product.class);
~~~

This uses the `Product` entity's metadata, including the index name declared in `@Document`.

When needing a test-specific dynamic index, pass `IndexCoordinates`:

~~~java
IndexCoordinates coordinates = IndexCoordinates.of("it-products-a13f92c1");
IndexOperations testIndexOperations = operations.indexOps(coordinates);
~~~

Key distinction: `indexOps(Product.class)` resolves the index from entity metadata; `indexOps(IndexCoordinates)` targets the explicitly specified index.

### 4.1. Creating the Index and Mapping

~~~java
IndexOperations entityMetadata = operations.indexOps(Product.class);
Document mapping = entityMetadata.createMapping();

IndexCoordinates coordinates = IndexCoordinates.of(indexName);
IndexOperations testIndex = operations.indexOps(coordinates);

testIndex.create();
testIndex.putMapping(mapping);
~~~

`createMapping()` derives the mapping from `Product` metadata. `putMapping()` applies that mapping to the new test index.

If the entity relies on custom settings, analyzers, or ingest pipelines, tests must provision those configurations as well. Do not assume an empty index suffices to test production queries.

### 4.2. Checking Existence Before Deleting

In teardown:

~~~java
IndexOperations indexOperations =
    operations.indexOps(IndexCoordinates.of(indexName));

if (indexOperations.exists()) {
    indexOperations.delete();
}
~~~

Checking `exists()` makes cleanup idempotent when called repeatedly without requiring the index to exist. Depending on client version and cluster state, still handle exceptions if another process deletes the index concurrently.

### 4.3. Deleting the Index vs Deleting Documents

When a test needs a completely clean environment, deleting and recreating the index is cleaner than deleting individual documents:

- Mappings are rebuilt cleanly.
- Settings are reset.
- Test aliases attached to the index are removed.
- No leftover documents or metadata remain from prior tests.

If a test class must share an index to save time, you can delete documents by ID or via delete-by-query scoped to test criteria. In that case, mappings/settings remain intact and tests must guarantee no related data remains before starting.

## 5. Integration Test Example with a Dedicated Index per Test Method

The example below uses `ElasticsearchOperations` to target the index explicitly. Each test method gets its own index so tests can run in parallel without overwriting one another's data.

~~~java
import java.util.Locale;
import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.TestInfo;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

@SpringBootTest
class ProductIndexIntegrationTest {

    @Autowired
    private ElasticsearchOperations operations;

    private String indexName;
    private IndexCoordinates coordinates;

    @BeforeEach
    void createTestIndex(TestInfo testInfo) {
        String method = testInfo.getTestMethod()
            .map(methodInfo -> methodInfo.getName())
            .orElse("unknown");

        String safeMethod = method
            .toLowerCase(Locale.ROOT)
            .replaceAll("[^a-z0-9_-]", "-");

        String token = UUID.randomUUID()
            .toString()
            .replace("-", "")
            .substring(0, 8);

        indexName = "it-products-" + safeMethod + "-" + token;
        coordinates = IndexCoordinates.of(indexName);

        IndexOperations entityMetadata = operations.indexOps(Product.class);
        IndexOperations testIndex = operations.indexOps(coordinates);

        testIndex.create();
        testIndex.putMapping(entityMetadata.createMapping());
    }

    @AfterEach
    void deleteTestIndex() {
        if (coordinates == null) {
            return;
        }

        IndexOperations testIndex = operations.indexOps(coordinates);
        if (testIndex.exists()) {
            testIndex.delete();
        }
    }
}
~~~

This is an integration test skeleton. Test methods in the class pass `coordinates` when saving and searching. Do not call default repository methods if the repository still uses the fixed index from `@Document`.

### 5.1. Writing and Reading on the Same Index

~~~java
Product product = new Product();
product.setId("P-100");
product.setName("Mechanical Keyboard");

operations.save(product, coordinates);

operations.indexOps(coordinates).refresh();

NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("name")
        .query("mechanical keyboard")
    ))
    .build();

SearchHits<Product> hits =
    operations.search(query, Product.class, coordinates);
~~~

Passing `IndexCoordinates` to both `save` and `search` guarantees both target the same test index. Passing only the entity class makes Spring Data fall back to the index name in `@Document`.

### 5.2. Do Not Share Index Fields Across Parallel Tests

The example above uses instance fields. JUnit Jupiter creates a new test instance per test method by default, so each instance holds its own `indexName` and `coordinates`.

If a class uses `@TestInstance(PER_CLASS)` or stores the index name in a `static` field, parallel test methods can overwrite each other's coordinates. In that case, manage index context per test invocation or disable parallel execution for methods sharing fields.

## 6. Repositories with Fixed @Document indexName

Spring Data Elasticsearch repositories normally derive the index from entity mapping metadata:

~~~java
@Document(indexName = "products")
public class Product {
    // ...
}
~~~

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

Calls such as `productRepository.save(product)` and `productRepository.findById(id)` target the index bound to entity metadata. Ordinary repository methods do not accept an extra `IndexCoordinates` argument per call.

Consequently, creating `it-products-<uuid>` and calling `repository.save` does not automatically write into that dynamic index. The repository may still write to `products` per its metadata.

### 6.1. Three Options for Testing Repositories

**Option A: dedicated index per test class.**

- Test entity uses a dedicated index name or resolves the index name via a property/SpEL mechanism supported by your project's version.
- Each test class gets its own context/index.
- Methods within the class clean documents or reset index state between runs.
- Different classes use distinct index names so they can run in parallel.

**Option B: testing repositories via a test-specific entity.**

- Define a test entity with matching mappings and a test-dedicated `@Document(indexName = "...")`.
- Define a repository for that entity.
- Use that fixed index for the test class and delete it in teardown.

This option is explicit, though you must avoid mapping model drift when the production entity changes.

**Option C: using ElasticsearchOperations with IndexCoordinates.**

- Use repositories for behaviors specifically needing verification through the repository proxy.
- Use `operations` for tests needing per-method dynamic indices.
- Never assume the repository proxy switches indices automatically based on coordinates passed elsewhere.

### 6.2. Properties or SpEL in @Document

Some Spring Data Elasticsearch configurations allow resolving the index name from a property or SpEL expression. You can use this so each test context gets its own index name.

However:

- Syntax and resolution timing vary by version.
- Repository metadata may be retained inside a cached `ApplicationContext`.
- Changing a property after context creation does not necessarily make the repository switch indices.
- Two tests sharing a context cannot safely mutate a global property per method.

If choosing this approach, scope contexts/indices per test class or test run, verify the actual index used by the repository, and avoid mutating shared properties under parallel execution. Never rely on `@DirtiesContext` as a primary data isolation tool; it merely evicts the context from the cache and can slow down the suite dramatically.

## 7. Cleaning Up Indices in JUnit Lifecycle

JUnit Jupiter provides lifecycle hooks:

- `@BeforeEach`: create index and mapping before each test method.
- `@AfterEach`: delete index after each test method.
- `@BeforeAll`: create class-shared resources.
- `@AfterAll`: clean up class-shared resources after the class finishes.

### 7.1. Using BeforeEach and AfterEach

This is the clearest pattern when each method owns an index:

~~~java
@BeforeEach
void setUp() {
    createUniqueIndex();
}

@AfterEach
void tearDown() {
    deleteCurrentIndexIfExists();
}
~~~

JUnit runs `@AfterEach` after the test method even when the test fails. However, if index creation in `@BeforeEach` fails partway through, cleanup must check whether the index was actually created.

### 7.2. Assign Coordinates Before Creating the Index

~~~java
indexName = createIndexName();
coordinates = IndexCoordinates.of(indexName);

IndexOperations indexOperations = operations.indexOps(coordinates);
indexOperations.create();
~~~

If `create` or `putMapping` fails after the index was already created, `@AfterEach` still holds the coordinates to attempt deletion.

### 7.3. Cleanup Must Be Safe to Call Repeatedly

~~~java
void deleteIndexIfExists(IndexCoordinates coordinates) {
    IndexOperations indexOperations = operations.indexOps(coordinates);
    if (indexOperations.exists()) {
        indexOperations.delete();
    }
}
~~~

Do not treat index-not-found as a fatal error if a previous cleanup already deleted it. Conversely, never swallow all cleanup exceptions silently, because permission errors or cluster outages can leave test indices behind permanently.

### 7.4. Do Not Mask Test Failures

If both the test method and teardown fail, preserve both details. JUnit typically reports teardown failures as lifecycle errors; log the index name so leftover indices can be cleaned manually if needed.

In larger test suites, you can build a JUnit extension to create and delete indices. The extension must store the index name in the test invocation's `ExtensionContext`, never in a shared `static` field across parallel tests.

## 8. Cleaning Documents When Sharing an Index Is Necessary

Sometimes a test must target a fixed repository index, or creating fresh indices is too costly. In such cases, keep the index for the test class and delete documents before/after each method.

Example using delete-by-query:

~~~java
Query deleteAll = Query.findAll();

operations.delete(
    deleteAll,
    Product.class,
    coordinates
);

operations.indexOps(coordinates).refresh();
~~~

Verify method names and `Query` types against your Spring Data Elasticsearch version. Delete-by-query on large datasets carries overhead and has specific semantics around refreshes and version conflicts.

### 8.1. Deleting by testRunId

If an index is shared across multiple tests and each document stores a `testRunId` field, delete only that test's data:

~~~json
{
  "query": {
    "term": {
      "testRunId": "run-a13f92c1"
    }
  }
}
~~~

Cleanup filters must use harness-generated test IDs, never arbitrary test inputs. After delete-by-query, refresh the index before other tests read data.

### 8.2. Why Deleting the Index Is Usually Cleaner

Delete-by-query removes only documents matching the query. Mappings, settings, aliases, and index-level metadata remain. If a test modified mappings or settings, deleting documents does not restore initial state.

When testing mapping migrations, analyzers, or index settings, creating a separate index and deleting the entire index afterward is much safer.

### 8.3. Avoid Whole-Index Delete-by-Query on Production Indices

Never run a `match_all` query or broad delete on an index that might contain non-test data. When a shared index is unavoidable, ensure:

- The cluster is test-only.
- Index names carry a test prefix.
- Every document carries a dedicated `testRunId`.
- Cleanup always filters strictly by `testRunId`.
- Tests have no credentials or network access to production clusters.

## 9. Refreshing After Writes

Elasticsearch is a near-real-time search engine. A successfully indexed document does not necessarily appear immediately in the very next search request.

Example:

~~~java
operations.save(product, coordinates);

SearchHits<Product> hits =
    operations.search(query, Product.class, coordinates);
~~~

Search may miss the document if a refresh has not happened yet.

### 9.1. Explicit Refresh in Tests

After finishing batch writes:

~~~java
operations.indexOps(coordinates).refresh();
~~~

Only then run search or aggregation assertions expecting the newly written data.

Refreshing in tests makes outcomes deterministic. Avoid calling refresh after every single document in a large batch, as that slows tests down and misrepresents how production applications normally operate.

### 9.2. Refresh Policies

Some write APIs support refresh policies like `wait_for`. Use them when verifying that changes are searchable upon completion, while understanding the cost and exact API semantics.

In integration tests, a single refresh after all writes finish is usually simpler and clearer.

### 9.3. Reactive Operations

With `ReactiveElasticsearchOperations`, subscribe/await writes and refreshes to finish before running search. Never build a publisher and ignore it assuming the operation ran.

Conceptual example:

~~~java
reactiveOperations.save(product, coordinates)
    .then(reactiveOperations.indexOps(coordinates).refresh())
    .thenMany(reactiveOperations.search(query, Product.class, coordinates))
    .collectList()
    .block();
~~~

Adjust this snippet to the actual return type of `refresh()` in your Spring Data version. Blocking at the test boundary to await results is acceptable in tests; never block arbitrarily inside production reactive pipelines.

## 10. Isolating Parallel Tests

Parallel execution speeds up CI, yet it is safe only when tests share no mutable resources.

### 10.1. Each Test Method Gets Its Own Index

~~~text
Test worker 1 -> it-products-testA-uuid1
Test worker 2 -> it-products-testB-uuid2
Test worker 3 -> it-orders-testC-uuid3
~~~

Workers can share an Elasticsearch cluster without ever writing to or deleting the same index.

### 10.2. Avoid Fixed Index Names in Parallel Tests

Names like `products-test` or `test-index` collide easily when multiple test classes or build processes share a cluster.

Even if every test calls delete before create, two tests can interleave:

~~~text
Worker A: exists? no
Worker B: exists? no
Worker A: create index
Worker B: create index -> resource already exists
Worker A: write documents
Worker B: delete index
Worker A: search -> index missing
~~~

Unique names eliminate index-level races.

### 10.3. Avoid Static Mutable Index Names

Never keep a `static` field mutated by every test invocation. One test can overwrite the value while another test is still using it. Store state per test instance or per extension context.

### 10.4. Parallel Test Classes and Spring Context Caching

Spring TestContext can reuse an `ApplicationContext` across test classes for speed. That does not automatically isolate Elasticsearch data.

Beans like `ElasticsearchOperations` are shared inside the context; physical indices remain shared cluster resources. Therefore, index isolation must be implemented explicitly per test scope.

If a repository binds to a fixed index name in entity metadata, two test classes sharing a context can both write to the same index. Use distinct names per class/context or serialize that test group.

## 11. Using Testcontainers for Elasticsearch Integration Tests

Testcontainers can start Elasticsearch inside a container for a test suite. This keeps tests independent of a developer's local cluster or shared environments.

Conceptual configuration:

~~~java
@Testcontainers
@SpringBootTest
class ProductSearchIntegrationTest {

    @Container
    static final ElasticsearchContainer elasticsearch =
        new ElasticsearchContainer(
            DockerImageName.parse(
                "docker.elastic.co/elasticsearch/elasticsearch:<pinned-version>"
            )
        );

    @DynamicPropertySource
    static void elasticsearchProperties(
            DynamicPropertyRegistry registry) {
        registry.add(
            "spring.elasticsearch.uris",
            elasticsearch::getHttpHostAddress
        );
    }
}
~~~

This is an illustrative structure. `ElasticsearchContainer` packages, constructors, and security setup vary by Testcontainers version. Pin an image version compatible with your project's Elasticsearch client instead of using `latest`.

### 11.1. Container per Suite, Index per Method

Starting a container for every test method can be very expensive. A balanced setup:

- One container per test class or suite.
- One dedicated index per test method.
- Clean up the index in `@AfterEach`.
- Stop the container when the suite finishes.

If multiple test classes share a static container, ensure the container does not stop before other classes finish using it. Use a singleton container pattern or lifecycle management matching your Testcontainers version.

### 11.2. Keeping Versions Synchronized

Spring Data Elasticsearch, the Elasticsearch Java API Client, and the server must be compatible. When upgrading the server version, update client dependencies and rerun the integration suite.

Avoid running tests against an Elasticsearch version drastically different from production when tests depend on specific mapping behavior, Query DSL, or API versions.

## 12. Protecting Non-Test Environments

Cleanup is destructive. Test configuration must ensure tests connect only to test clusters.

Practices:

- Use a dedicated profile such as `test`.
- Use URIs supplied by Testcontainers or a dedicated test cluster.
- Use credentials scoped exclusively to test clusters/indices.
- Validate host/URI when integration tests initialize.
- Use a distinct index prefix like `it-`.
- Never let tests fall back to a production URI when environment variables are missing.

Example configuration guard:

~~~java
String uri = environment.getProperty("spring.elasticsearch.uris");

if (uri == null || uri.isBlank()) {
    throw new IllegalStateException(
        "Elasticsearch test URI must be configured"
    );
}

if (uri.contains("prod")) {
    throw new IllegalStateException(
        "Integration tests must not connect to production"
    );
}
~~~

This is only an illustrative guard; checking the substring `prod` is not a full security boundary. Far better is supplying endpoints solely from containers/test environments alongside credentials lacking production permissions.

Never write cleanup logic that deletes all indices or all aliases in a cluster. One endpoint misconfiguration could turn cleanup into unintended data loss.

## 13. Cleaning Leftover Indices After Killed Processes

`@AfterEach` cannot run if the JVM is killed, the machine powers off, or a CI job is cancelled abruptly. Thus, test indices can linger after aborted runs.

### 13.1. Dedicated Prefix

Use a fixed prefix for identification:

~~~text
it-products-...
it-orders-...
~~~

Do not use overly broad prefixes like `test-` if a cluster holds indices belonging to other application teams.

### 13.2. Per-Test-Run Cleanup

Embed a run ID in every index:

~~~text
it-run-20261113-8f2a-products-...
it-run-20261113-8f2a-orders-...
~~~

After the suite, cleanup deletes only indices matching that exact run ID prefix. If a job is aborted, a scheduled cleanup job on the test cluster can prune indices from expired runs.

### 13.3. Age- and Namespace-Based Cleanup

Scheduled cleanup must:

1. Run solely against test clusters.
2. Select only indices matching the designated test prefix.
3. Check the run ID or index age.
4. Never delete indices belonging to active runs.
5. Log the exact list of indices to be deleted.
6. Delete by the explicit, verified list of names.

Never run wildcard deletions against a non-isolated cluster. For test isolation, a disposable container is often the best cleanup mechanism: stopping the container removes every index inside it.

## 14. Aliases and Templates in Tests

Some integration tests verify aliases, index templates, or rollovers. In those cases, index isolation must encompass related aliases and templates as well.

### 14.1. Dedicated Test Aliases

If a test creates aliases:

~~~text
it-products-<token>       physical index
it-products-read-<token>  read alias
it-products-write-<token> write alias
~~~

Never use shared aliases like `products-read` in a cluster accessed by multiple tests. One test flipping an alias can make another test read the wrong index.

Deleting the physical test index usually removes aliases bound exclusively to it. If an alias spans multiple indices or is managed separately, remove the test alias explicitly during cleanup.

### 14.2. Index Templates

If production uses index templates, tests must confirm templates apply to test index names. Template patterns should cover test prefixes or use test-dedicated templates.

Avoid mutating shared templates during parallel tests. Templates are cluster-level resources, not scoped to one index. If a test must modify templates, use a dedicated cluster/container or serialize that test.

### 14.3. Rollover Tests

Rollovers involve aliases and index generations. Each test should use its own write alias and index prefix so rollover operations do not interfere with other tests.

After the test, delete all index generations and aliases inside the test's namespace. Deleting only the current index can leave older generations behind.

## 15. Testing Mappings and Settings

When the test focuses on mappings:

1. Create a dedicated index.
2. Apply mappings from the entity or JSON mapping under test.
3. Read the actual mapping back from Elasticsearch.
4. Assert field types, analyzers, nested/object types, and multi-fields.
5. Delete the index after the test.

Example:

~~~java
IndexOperations indexOperations =
    operations.indexOps(coordinates);

indexOperations.create();
indexOperations.putMapping(
    operations.indexOps(Product.class).createMapping()
);

Document actualMapping = indexOperations.getMapping();
~~~

When testing analyzers or settings, apply settings at index creation time as required by the API. Certain analyzer settings can only be configured upon index creation and cannot be added arbitrarily afterward.

Using a dedicated index guarantees mapping tests never alter indices used by other tests.

## 16. Bulk Test Data and Cleanup

When tests need many documents, use bulk inserts rather than individual requests:

~~~java
BulkOperations bulk = operations.bulkOps(
    BulkMode.BULK,
    Product.class,
    coordinates
);

bulk.insert(products);
bulk.execute();

operations.indexOps(coordinates).refresh();
~~~

After the test finishes, delete the entire index in one shot instead of deleting documents one by one. If the test specifically verifies document deletion, perform those assertions before teardown deletes the index.

Bulk responses can contain item-level failures even when the HTTP request succeeds. For large test datasets, check bulk results according to your API/version and never assume `execute` returning means every item was indexed.

### 16.1. Deterministic Test Data

Create fixtures with stable IDs and values within the test index scope:

~~~java
List<Product> products = List.of(
    product("P-100", "Keyboard", "BRAND-A"),
    product("P-101", "Mouse", "BRAND-B"),
    product("P-102", "Monitor", "BRAND-A")
);
~~~

Dedicated indices allow short, readable IDs without worrying about collisions with other tests. When writing into a shared index, IDs should carry a `testRunId` or separate namespace.

### 16.2. Do Not Rely on Default Return Order

When searching multiple documents, do not assume results follow insertion order. If order matters, declare an explicit sort with a deterministic tie-breaker.

## 17. Handling Test Failures and Retries

A test may fail before teardown finishes. Design cleanup so that:

- The index name is known as soon as setup starts.
- Existence is checked before deleting.
- Exactly the one index belonging to that test invocation is deleted.
- The index name is logged if deletion fails.
- Other indices are never deleted via wildcards.

If cleanup fails due to temporary cluster unavailability, log the index name for subsequent cleanup jobs. Do not loop endlessly in `@AfterEach`, as that can hang the suite.

When CI retries a failed test, each retry must receive a fresh run token or index token. Never reuse an index from a failed run unless the test specifically verifies resume behavior.

## 18. A JUnit Extension for Managing Indices

When multiple test classes share the same mapping setup flow, encapsulate lifecycle management in a JUnit extension.

An extension should:

- Generate an index name per test invocation.
- Store `IndexCoordinates` in `ExtensionContext.Store`.
- Create the index and mapping before the test.
- Provide coordinates to the test via a parameter resolver or fixture object.
- Delete the index after the test.
- Never use a static mutable field to track the active index.

Conceptual example:

~~~java
public record TestIndex(IndexCoordinates coordinates) {}
~~~

Test receiving the fixture:

~~~java
@Test
void shouldSearchWithinItsOwnIndex(TestIndex testIndex) {
    // Write and read using testIndex.coordinates().
}
~~~

Details of `ParameterResolver`, `BeforeEachCallback`, and `AfterEachCallback` depend on how the extension is registered. Extensions work well when many tests share identical setup; for a small test class, `@BeforeEach` and `@AfterEach` are often easier to read.

## 19. Common Pitfalls

**Using one fixed index for the entire suite.** Data and cleanup from one test can break others. Create dedicated indices per test or test class.

**Creating a random index yet calling default repository methods.** The repository may still use `@Document`'s index name. Use `IndexCoordinates` with `operations` or configure repository metadata for the appropriate test scope.

**Naming indices solely after the test method.** Parallel CI forks or build runs can collide on the same name. Append a unique token.

**Keeping the active index in a static field.** Parallel tests can overwrite coordinates. Scope state to each test invocation.

**Deleting only documents while ignoring mappings/settings.** Subsequent mapping tests may run against a previously altered index. Delete and recreate the index when clean state is required.

**Searching without refreshing first.** Newly written documents may not be searchable yet. Refresh once after seeding fixtures.

**Deleting indices with broad wildcards.** Risks deleting non-test data. Delete only the explicit index names created and verified within the test namespace.

**Teardown deleting a shared index.** Parallel tests may actively use that index. Never share mutable indices across concurrent test invocations.

**Failing to clean up when tests fail.** Use lifecycle teardown and run-ID-based cleanup jobs to handle killed processes too.

**Using `@DirtiesContext` as a substitute for data isolation.** It refreshes the `ApplicationContext`, not Elasticsearch indices. Manage indices explicitly.

**Assuming Spring context caching isolates indices.** Contexts can be reused while cluster indices remain shared resources.

**Using repositories and operations on two different indices unknowingly.** Repositories derive indices from entity metadata; operations accept explicit `IndexCoordinates`. Verify both read and write targets.

**Sharing aliases across parallel tests.** Aliases are cluster-level resources. Use dedicated aliases per test or dedicated clusters.

**Modifying index templates during parallel tests.** Templates apply by pattern and can affect other indices. Use test-dedicated templates or dedicated test clusters.

**Not waiting for reactive operations to finish.** Unsubscribed publishers may never execute. Await results before searching and cleaning up.

**Deleting an index before async bulk writes finish.** In-flight requests can fail with missing-index errors. Wait for all write tasks to complete before deleting.

## 20. Recommended Workflow for Integration Tests

For a test method requiring real Elasticsearch:

1. Connect to an Elasticsearch test cluster or Testcontainers.
2. Generate an index name with a test prefix and unique token.
3. Store `IndexCoordinates` in the test invocation's state.
4. Create the index via `IndexOperations`.
5. Apply the mappings/settings under test.
6. Write fixtures via `ElasticsearchOperations` with explicit coordinates.
7. Refresh the index once writes finish.
8. Run search, aggregation, or repository assertions.
9. Wait for any related async/reactive tasks to finish.
10. In teardown, verify the index exists and delete that exact index.
11. If cleanup fails, log the index name for the test cleanup job.

For repository integration tests, pick a dedicated index per test class/context or configure entity metadata properly. Never assume a repository proxy switches indices merely because you instantiated another `IndexCoordinates` in the test.

## 21. Safe Test Design Checklist

- [ ] Integration tests connect only to Elasticsearch test clusters.
- [ ] Index names include a test prefix and unique token.
- [ ] Index names comply with Elasticsearch naming rules.
- [ ] Each test invocation gets its own `IndexCoordinates` when running in parallel.
- [ ] Mappings/settings are created explicitly before writing.
- [ ] Tests pass identical coordinates to create, write, search, and delete.
- [ ] Refresh after writes before searches expecting fresh data.
- [ ] Repository tests account for indices resolved from `@Document` metadata.
- [ ] No static mutable index names are shared across tests.
- [ ] Teardown deletes the exact index after checking existence.
- [ ] Cleanup never uses wildcards capable of touching non-test data.
- [ ] Aliases and templates use isolated namespaces when tested.
- [ ] Async/reactive/bulk operations complete before cleanup runs.
- [ ] CI has a mechanism to prune leftover indices if processes are killed.

## 22. References

- [Spring Data Elasticsearch - Index Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html): managing indices, mappings, refreshes, and `ElasticsearchOperations`.
- [Spring Data Elasticsearch API - IndexOperations](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/IndexOperations.html): API for creating, checking, refreshing, and deleting indices.
- [Spring Data Elasticsearch API - IndexCoordinates](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/mapping/IndexCoordinates.html): representing target indices for operations.
- [Spring Data Elasticsearch - Object Mapping](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html): entity metadata and `@Document` configuration.
- [Spring Boot - Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): test configuration and `ApplicationContext` management in tests.
- [JUnit 5 - User Guide](https://junit.org/junit5/docs/current/user-guide/): lifecycle hooks, test instance lifecycles, and parallel execution.
- [Testcontainers - Elasticsearch module](https://java.testcontainers.org/modules/elasticsearch/): running Elasticsearch containers for integration tests.
- [Elasticsearch - Near real-time search](https://www.elastic.co/guide/en/elasticsearch/reference/current/near-real-time.html): refreshes and when documents become visible in search.

API overloads across Spring Data Elasticsearch, Testcontainers, and Elasticsearch clients can change between versions. Always consult the Javadoc for your project's exact dependencies. The core principle is keeping test data in an isolated namespace, targeting the exact intended index in every operation, and ensuring cleanup deletes only resources created by that test invocation.
