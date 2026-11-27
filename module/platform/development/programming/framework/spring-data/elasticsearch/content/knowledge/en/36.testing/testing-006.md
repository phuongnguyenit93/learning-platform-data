# Explicit Refresh or Condition Waiting Instead of Fixed Sleep Durations

When testing applications using Spring Data Elasticsearch, a successful write operation does not guarantee that the document immediately appears in search results. Elasticsearch is a near real-time system: indexing updates internal shard structures, while search only sees changes after the shard is refreshed. Consequently, a test that calls save and searches immediately may receive an empty list even though the document was saved successfully.

A common habit is calling `Thread.sleep(1000)` after saving data. That does not synchronize with Elasticsearch's real state: fast machines wait unnecessarily, and slow machines can still fail. Tests should synchronize using an explicit refresh when immediate search visibility is needed, use the `WAIT_UNTIL` refresh policy when the request should wait for the next refresh, or poll a condition with a timeout when work completes asynchronously.

This lesson explains refresh and near-real-time search, distinguishes GET by ID from search, shows how to refresh the right index in Spring Data Elasticsearch, how to choose `RefreshPolicy`, how to use Awaitility to wait on conditions, how to apply these techniques to reactive tests, and how to avoid timing-related flaky tests.

## 1. Why Does Search Miss a Document Right After Save?

Elasticsearch separates writing a document from making it visible to search. When an index request succeeds, the document has been accepted and updated in the shard's internal data structures. The current searcher does not necessarily see the new segment right away.

A refresh opens a new searcher so indexed changes become searchable. Because of this, Elasticsearch is described as near real-time rather than real-time for search.

Write and search flow:

~~~text
Test / Application
       |
       | save(document)
       v
Elasticsearch primary shard
       |
       | indexing operation succeeds
       v
Document is indexed internally
       |
       | refresh has not happened yet
       v
Current searcher may still be stale
       |
       | scheduled or explicit refresh
       v
New searcher sees the document
       |
       v
Search returns the document
~~~

This does not mean the save failed. It simply means search visibility has not been updated yet.

### 1.1. Refresh Differs from Flush

Refresh and flush are two separate operations:

| Operation | Purpose |
|---|---|
| Refresh | Makes indexed changes available for search by opening a new searcher |
| Flush | Clears the translog and creates a new Lucene commit according to Elasticsearch's durability mechanism |

In tests where search must see a document after writing, refresh is the relevant operation. Do not call flush just to solve search visibility.

### 1.2. Refresh Is Not a Transaction

Refresh does not turn multiple write operations into a transaction. It only controls when search can see already-indexed changes. If a bulk request has a failed item, refreshing does not roll back or repair that item.

## 2. Distinguishing Real-Time GET and Near-Real-Time Search

A crucial point in testing is that GET by ID and search have different semantics:

| Read approach | Behavior | Needs refresh to see recent writes? |
|---|---|---|
| GET document by ID | Real-time by default | Usually no |
| Search by field/query | Near real-time | May need to wait for refresh |
| Count via search/query | Depends on search visibility | May need to wait for refresh |

Example writing then reading directly by ID:

~~~java
Product saved = operations.save(
        new Product("p-100", "Keyboard"),
        IndexCoordinates.of("products"));

Product loaded = operations.get(
        saved.getId(),
        Product.class,
        IndexCoordinates.of("products"));
~~~

GET by ID is real-time by default, so it can usually read the newly written document without refreshing the index.

By contrast, searching by name:

~~~java
SearchHits<Product> hits = operations.search(
        new CriteriaQuery(Criteria.where("name").is("Keyboard")),
        Product.class,
        IndexCoordinates.of("products"));
~~~

Search may not see the document yet if a refresh has not occurred.

Do not blindly add refreshes to every test just because it saves documents. Identify whether the test verifies GET, search, count, or an asynchronous pipeline.

## 3. Default Refresh Interval

Elasticsearch typically refreshes indices actively receiving search requests on a default schedule of roughly one second. That is why tests using `Thread.sleep(1000)` sometimes appear to work. However, the refresh interval is an operational setting, not a synchronization clock meant for tests.

The refresh interval can be changed per index:

~~~http
GET products/_settings?filter_path=*.settings.index.refresh_interval
~~~

Example configuration:

~~~http
PUT products/_settings
{
  "index": {
    "refresh_interval": "2s"
  }
}
~~~

If the refresh interval is set to `-1`, Elasticsearch does not refresh periodically on its own. Search may not see new documents until an explicit refresh or another refresh operation occurs.

In tests, do not rely on the cluster's current refresh interval value. Tests should actively control the synchronization point or wait on the exact condition.

## 4. What Not to Use: Fixed Thread.sleep

A common anti-pattern:

~~~java
repository.save(product);
Thread.sleep(1000);

assertThat(repository.findByName("Keyboard")).hasSize(1);
~~~

This approach has several problems:

- You do not know whether a refresh has actually happened.
- Fast machines waste a full second even when data becomes visible in milliseconds.
- Busy CI runners or loaded clusters may take longer than one second.
- It slows down the entire test suite.
- It makes tests timing-dependent and flaky.
- If a consumer or worker has not processed an event yet, sleeping one second does not prove the job finished.

Increasing sleep duration to 3 or 5 seconds only makes tests slower and still offers no synchronization guarantee.

### 4.1. Sleep Does Not Prove Business Conditions

Suppose a test sends a message to a broker, a consumer receives it, transforms the data, and indexes a document:

~~~text
Test publishes event
        |
        v
Broker queue
        |
        v
Consumer receives event
        |
        v
Transforms document
        |
        v
Indexes into Elasticsearch
        |
        v
Refresh makes document searchable
~~~

`Thread.sleep(1000)` does not prove the consumer received the message, indexing succeeded, or refresh occurred. Tests must wait for an observable condition, such as the document appearing in search.

## 5. Approach 1: Explicit Refresh in Integration Tests

When a test needs to verify search immediately after writing fixtures, the simple, deterministic approach is refreshing the exact index before searching.

Spring Data Elasticsearch provides `IndexOperations`:

~~~java
operations.indexOps(Product.class).refresh();
~~~

Or specify the index explicitly:

~~~java
operations.indexOps(IndexCoordinates.of("products")).refresh();
~~~

Imperative test example:

~~~java
@Autowired
ElasticsearchOperations operations;

@Autowired
ProductRepository repository;

@Test
void findsProductImmediatelyAfterRefresh() {
    repository.save(new Product("p-100", "Keyboard"));

    operations.indexOps(Product.class).refresh();

    assertThat(repository.findByName("Keyboard"))
            .hasSize(1);
}
~~~

The test writes the document, refreshes the index, and then checks via the query method. No guesswork over timing is required.

### 5.1. Refreshing After Preparing Fixtures

If a test creates multiple documents:

~~~java
@BeforeEach
void setUp() {
    repository.saveAll(List.of(
            new Product("p-100", "Keyboard"),
            new Product("p-101", "Mouse"),
            new Product("p-102", "Monitor")));

    operations.indexOps(Product.class).refresh();
}
~~~

Every test in the class can search fixtures immediately once setup completes.

### 5.2. Refreshing Only the Relevant Index

Prefer:

~~~java
operations.indexOps(IndexCoordinates.of("products")).refresh();
~~~

over refreshing the entire cluster:

~~~http
POST /_refresh
~~~

Cluster-wide refreshes can affect many indices and couple tests to other suites' data. Refreshing only the relevant index reduces impact and clarifies test scope.

If a repository uses an alias, identify which target indices the alias points to and refresh only the indices under test. For test isolation, a dedicated test index is usually easier to control than a shared alias.

### 5.3. Cleanup Also Needs Refresh If Subsequent Tests Search

If a test deletes fixtures and the next test runs search queries, the deletion might not be visible to the current searcher immediately either.

Example:

~~~java
@AfterEach
void cleanUp() {
    repository.deleteAll();
    operations.indexOps(Product.class).refresh();
}
~~~

For large suites, it is better to create a dedicated index per test class or test run and delete the index afterward. If sharing an index, manage data and refreshes in both setup and cleanup.

## 6. Approach 2: Using RefreshPolicy.IMMEDIATE

`RefreshPolicy.IMMEDIATE` tells Elasticsearch to refresh immediately after the write operation so changes become search-visible before the request returns.

Spring Data Elasticsearch accepts `RefreshPolicy` in APIs supporting refresh policies, such as `BulkOptions`:

~~~java
BulkOptions options = BulkOptions.builder()
        .withRefreshPolicy(RefreshPolicy.IMMEDIATE)
        .build();

operations.bulkIndex(
        indexQueries,
        options,
        IndexCoordinates.of("products"));
~~~

Once `bulkIndex` returns successfully, the test can search the documents written by that request.

### 6.1. When Is IMMEDIATE Appropriate?

`IMMEDIATE` is appropriate when:

- The test needs to verify the semantics of an immediately refreshing request.
- A single write must be search-visible before returning a response due to a specific requirement.
- The test cannot perform an explicit refresh at the fixture layer because it is testing the refresh policy itself.

In ordinary tests, an explicit refresh after preparing data is simpler than enabling `IMMEDIATE` on every request.

### 6.2. Why Not Enable IMMEDIATE for Every Request in Production?

Refreshing creates a new searcher and incurs CPU, I/O, and segment management costs. Refreshing after every single request can create many small segments, increasing merge overhead and reducing indexing throughput.

Do not use `IMMEDIATE` by default on every write just to see data immediately in search. Choose policies based on visibility requirements and system load.

## 7. Approach 3: Using RefreshPolicy.WAIT_UNTIL

`WAIT_UNTIL` tells the write request to wait until the next scheduled or triggered refresh makes its changes search-visible. Elasticsearch does not force an immediate refresh at completion; it waits for a scheduled or external refresh.

Bulk example:

~~~java
BulkOptions options = BulkOptions.builder()
        .withRefreshPolicy(RefreshPolicy.WAIT_UNTIL)
        .build();

operations.bulkIndex(
        indexQueries,
        options,
        IndexCoordinates.of("products"));
~~~

When the request returns, the changes from that request have been refreshed and are searchable.

### 7.1. How WAIT_UNTIL Differs from IMMEDIATE

| Policy | Behavior | Cost/latency |
|---|---|---|
| NONE | Requests no special refresh | Usually best for throughput |
| IMMEDIATE | Forces an immediate refresh | Can increase refresh overhead |
| WAIT_UNTIL | Waits for the next refresh | Usually avoids redundant refreshes, though the request may wait |

`WAIT_UNTIL` is useful when the caller needs search visibility before proceeding without needing to force an immediate refresh.

### 7.2. WAIT_UNTIL Can Wait a Long Time

If an index disables automatic refresh via `refresh_interval = -1` and no other refresh runs, a `WAIT_UNTIL` request can wait until a refresh occurs or it times out. When using this policy, ensure the index has a refresh schedule or an explicit refresh trigger.

Tests should have test-framework-level timeouts so they do not hang indefinitely if the index is misconfigured.

### 7.3. WAIT_UNTIL in BulkOptions Does Not Make All Writes Wait Automatically

A refresh policy applies only to requests configured with those options. Separate `save` calls or other clients do not automatically inherit `BulkOptions` settings. Do not assume configuring `BulkOptions` in one helper affects every operation in the test suite.

## 8. Choosing the Right Strategy for Each Test Type

| Test goal | Recommended synchronization |
|---|---|
| Verify GET by ID after save | Read directly; usually no refresh needed |
| Write fixtures then search immediately | Explicit refresh after setup |
| Verify bulk request refresh semantics | `IMMEDIATE` or `WAIT_UNTIL` as required |
| Verify search visibility after a write | Explicit refresh or `WAIT_UNTIL` |
| Verify asynchronous consumer/event pipeline | Poll search-visible condition with timeout |
| Verify eventual consistency | Poll until condition holds or timeout |
| Unit test mocking repository | No Elasticsearch refresh needed |

Do not use one generic sleep helper across all tests. Pick synchronization matching the behavior under test.

## 9. Waiting on Conditions with Awaitility

Awaitility is a library that lets tests wait on asynchronous conditions declaratively. Instead of guessing how long to sleep, the test describes the desired state and maximum allowed time.

Gradle dependency:

~~~kotlin
testImplementation("org.awaitility:awaitility:4.2.2")
~~~

Maven dependency:

~~~xml
<dependency>
    <groupId>org.awaitility</groupId>
    <artifactId>awaitility</artifactId>
    <version>4.2.2</version>
    <scope>test</scope>
</dependency>
~~~

Example waiting for a document to appear in search:

~~~java
import static org.awaitility.Awaitility.await;
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

@Test
void waitsUntilProductBecomesSearchable() {
    eventPublisher.publishEvent(
            new ProductCreatedEvent("p-100", "Keyboard"));

    await()
            .alias("product becomes searchable")
            .atMost(Duration.ofSeconds(10))
            .pollInterval(Duration.ofMillis(100))
            .untilAsserted(() ->
                    assertThat(repository.findByName("Keyboard"))
                            .extracting(Product::getId)
                            .contains("p-100"));
}
~~~

Awaitility evaluates the assertion repeatedly until it succeeds or times out. The test does not have to guess when the consumer finishes or when the refresh happens.

### 9.1. until and untilAsserted

Two common waiting styles:

~~~java
await()
        .atMost(Duration.ofSeconds(5))
        .until(() -> repository.existsById("p-100"));
~~~

~~~java
await()
        .atMost(Duration.ofSeconds(5))
        .untilAsserted(() ->
                assertThat(repository.findByName("Keyboard"))
                        .isNotEmpty());
~~~

`until` waits for a boolean condition to become true. `untilAsserted` runs assertions and retries while they throw assertion errors.

Choose `untilAsserted` when verifying contents, counts, or document state. Choose `until` when the condition is cleanly expressed as a boolean.

### 9.2. Waiting for a Document Count

Example where a consumer creates multiple documents:

~~~java
await()
        .alias("all imported products are searchable")
        .atMost(Duration.ofSeconds(15))
        .pollInterval(Duration.ofMillis(200))
        .untilAsserted(() ->
                assertThat(repository.findByImportId("batch-42"))
                        .hasSize(100));
~~~

The condition succeeds only once all 100 documents appear in search. Checking only `isNotEmpty()` could exit as soon as the first document arrives even though the batch has not finished processing.

### 9.3. Waiting for a Specific State

If a document transitions through multiple states:

~~~java
await()
        .atMost(Duration.ofSeconds(10))
        .untilAsserted(() -> {
            Product product = repository.findById("p-100")
                    .orElseThrow();
            assertThat(product.getStatus()).isEqualTo("INDEXED");
        });
~~~

If the condition requires search visibility, use a query method/search instead of GET by ID. Real-time GET can see the document before the searcher refreshes, thereby failing to test the search-visible condition.

## 10. Waiting for an Asynchronous Pipeline to Complete

With message brokers, event listeners, or background workers, the condition to wait for is usually the final state in Elasticsearch.

Example:

~~~java
@Test
void indexesProductAfterReceivingEvent() {
    eventPublisher.publishEvent(
            new ProductImportedEvent("p-100", "Keyboard"));

    await()
            .atMost(Duration.ofSeconds(15))
            .pollInterval(Duration.ofMillis(100))
            .untilAsserted(() -> {
                List<Product> results =
                        repository.findByExternalId("p-100");

                assertThat(results).hasSize(1);
                assertThat(results.getFirst().getName())
                        .isEqualTo("Keyboard");
            });
}
~~~

This condition covers the entire pipeline: the event is handled, the document is written, and search visibility is updated.

If the pipeline emits a reliable completion signal, you can wait for that signal and then refresh the index before searching. If the test verifies eventual consistency from a reader's viewpoint, polling the search query is more accurate.

### 10.1. Do Not Poll an Unrelated Condition

Waiting for an event queue to drain does not prove the document is searchable: the consumer may acknowledge the message before a refresh happens. Conversely, search might see a document before the full batch completes.

The wait condition must match what the test intends to guarantee:

- Want to know the consumer received the event: wait for consumer acknowledgement/observable state.
- Want to know the document was written by ID: GET by ID.
- Want to know the document is search-visible: search query.
- Want to know the whole batch completed: verify total count or batch completion record.

## 11. Condition Waits Must Have a Timeout and Polling Interval

A wait without a timeout can hang the test suite forever. Every wait condition should define:

- Maximum timeout.
- Reasonable poll interval.
- A condition description via `alias` for clear failure messages.
- Assertions strong enough to prove the final state.
- Diagnostic details on timeout.

Example:

~~~java
await()
        .alias("projection batch batch-42 reaches 100 products")
        .atMost(Duration.ofSeconds(20))
        .pollInterval(Duration.ofMillis(250))
        .untilAsserted(() ->
                assertThat(repository.findByImportId("batch-42"))
                        .hasSize(100));
~~~

Do not poll every 1 millisecond. Aggressive polling creates unnecessary search load and can affect the cluster under test.

### 11.1. Choosing Timeout Based on the Test Contract

Timeouts should reflect the pipeline's SLA or reasonable upper bound in the test environment. A consumer running locally may finish fast, whereas a CI runner and Elasticsearch container may be slower.

Do not set huge timeouts just to hide pipeline bugs. If a test routinely consumes nearly the entire timeout, investigate throughput, queues, refresh intervals, or race conditions.

### 11.2. Timeout Is Not Sleep Time

A timeout is an upper bound. Polling stops immediately once the condition passes. If data appears after 80 ms, the test completes in roughly 80 ms rather than waiting the full 10 seconds.

## 12. Combining Explicit Refresh and Awaitility

These two approaches solve different problems:

- Explicit refresh synchronizes search visibility for already-completed writes.
- Awaitility waits for an asynchronous condition that may involve multiple steps or retries.

Example preparing fixtures via `saveAll`:

~~~java
@BeforeEach
void prepareProducts() {
    repository.saveAll(testProducts);
    operations.indexOps(Product.class).refresh();
}
~~~

Then test search directly:

~~~java
@Test
void filtersProductsByCategory() {
    List<Product> results = repository.findByCategory("accessories");

    assertThat(results).hasSize(3);
}
~~~

With an asynchronous consumer:

~~~java
@Test
void eventuallyIndexesImportedProduct() {
    eventPublisher.publishEvent(
            new ProductImportedEvent("p-200", "Monitor"));

    await()
            .atMost(Duration.ofSeconds(10))
            .untilAsserted(() ->
                    assertThat(repository.findByExternalId("p-200"))
                            .hasSize(1));
}
~~~

Do not call explicit refresh immediately after publishing an event if the consumer has not finished writing yet; refreshing early does not make the event process any faster. Polling the final condition fits that pipeline better.

## 13. Refresh in Reactive Tests

Reactive Spring Data Elasticsearch provides reactive index operations. In tests, you can chain the refresh publisher before the query publisher:

~~~java
Mono<Void> refresh = reactiveOperations
        .indexOps(Product.class)
        .refresh();

Flux<Product> searchableProducts = refresh
        .thenMany(repository.findByCategory("accessories"));

StepVerifier.create(searchableProducts)
        .expectNextCount(3)
        .verifyComplete();
~~~

The key is using `thenMany` so the query starts only after refresh finishes. Creating two separate publishers without chaining them does not guarantee execution order.

### 13.1. Do Not Subscribe Separately to Refresh

Avoid:

~~~java
reactiveOperations.indexOps(Product.class).refresh().subscribe();

return repository.findByCategory("accessories");
~~~

Refresh and search run in two independent subscriptions. Search may execute before refresh completes.

Compose them instead:

~~~java
return reactiveOperations.indexOps(Product.class)
        .refresh()
        .thenMany(repository.findByCategory("accessories"));
~~~

### 13.2. Using StepVerifier with Timeouts

~~~java
StepVerifier.create(
        reactiveOperations.indexOps(Product.class)
                .refresh()
                .thenMany(repository.findByCategory("accessories")))
        .expectNextCount(3)
        .verify(Duration.ofSeconds(5));
~~~

`StepVerifier`'s timeout prevents the test from waiting forever if the publisher never terminates. This timeout differs from polling: it bounds how long to wait on one publisher execution rather than retrying searches for eventual consistency.

### 13.3. Polling Reactive Conditions for Asynchronous Pipelines

If a test needs to wait for an event consumer to update the search index, you can use Awaitility to retry an assertion backed by a publisher. The test thread can wait on the publisher on each attempt; never put `block` into application code:

~~~java
await()
        .atMost(Duration.ofSeconds(10))
        .pollInterval(Duration.ofMillis(150))
        .untilAsserted(() ->
                StepVerifier.create(
                                repository.findByExternalId("p-200").take(1))
                        .expectNextCount(1)
                        .verifyComplete());
~~~

Each time Awaitility runs the assertion, `StepVerifier` subscribes once to the reactive query. When there is no hit yet, the assertion fails and Awaitility retries until the timeout.

## 14. Refresh Policies for Bulk Indexing

Bulk requests can configure a refresh policy. In Spring Data Elasticsearch:

~~~java
BulkOptions options = BulkOptions.builder()
        .withRefreshPolicy(RefreshPolicy.WAIT_UNTIL)
        .build();

operations.bulkIndex(
        indexQueries,
        options,
        IndexCoordinates.of("products"));
~~~

If the test verifies that the bulk request returns only once data is search-visible, `WAIT_UNTIL` is an appropriate choice.

Use `IMMEDIATE` if the test verifies forced refresh behavior:

~~~java
BulkOptions options = BulkOptions.builder()
        .withRefreshPolicy(RefreshPolicy.IMMEDIATE)
        .build();
~~~

Use `NONE` if the test only inspects the indexing response or reads directly by ID without needing immediate search visibility.

### 14.1. Bulk Partial Failures Must Still Be Checked

A refresh policy does not guarantee every bulk item succeeded. Tests must inspect item-level results or corresponding exceptions. If an item hits a mapping error, refreshing does not turn that item into a valid document.

### 14.2. Do Not Treat WAIT_UNTIL as a Substitute for Consumer Completion

`WAIT_UNTIL` applies only to the write request waiting for refresh. It does not wait for other messages in a broker, other jobs writing more documents, or guarantee an external batch has completed.

To wait for an entire pipeline, poll the final state or await an appropriate completion signal.

## 15. Refresh in the Elasticsearch REST API

Elasticsearch provides the Refresh API:

~~~http
POST products/_refresh
~~~

Or refresh all indices:

~~~http
POST /_refresh
~~~

In Spring Data applications, `IndexOperations.refresh()` is generally preferred because it keeps test logic at the abstraction already in use and resolves indices from domain/index coordinates.

Index, update, and bulk REST APIs also support the `refresh` query parameter with values:

| Value | Meaning |
|---|---|
| `false` or omitted | Do not request a refresh |
| `true` | Immediately refresh affected shards |
| `wait_for` | Wait for the next scheduled refresh |

`true` corresponds to immediate refresh; `wait_for` corresponds to waiting for refresh. The enum names in Spring Data are `RefreshPolicy.IMMEDIATE`, `RefreshPolicy.WAIT_UNTIL`, and `RefreshPolicy.NONE`.

## 16. Setting Up Indices in Integration Tests

Tests should manage their own indices and mappings to avoid depending on developer environments or shared clusters.

Example:

~~~java
@BeforeEach
void createIndexIfNeeded() {
    IndexOperations indexOps = operations.indexOps(Product.class);

    if (!indexOps.exists()) {
        indexOps.createWithMapping();
    }
}
~~~

If the test requires an empty state:

~~~java
@BeforeEach
void resetIndex() {
    IndexOperations indexOps = operations.indexOps(Product.class);

    if (indexOps.exists()) {
        indexOps.delete();
    }

    indexOps.createWithMapping();
}
~~~

Deleting/recreating an index suits dedicated test indices. Never do this on production indices or indices shared with non-test data.

After seeding fixtures, refresh once:

~~~java
repository.saveAll(products);
operations.indexOps(Product.class).refresh();
~~~

A single refresh after a batch of fixtures is generally more efficient than refreshing after every entity.

## 17. Testcontainers and Refresh

Testcontainers runs integration tests against real Elasticsearch inside a container. Even when the container starts cleanly, tests must still handle Elasticsearch's refresh semantics.

A test can:

1. Start the Elasticsearch container.
2. Point the Spring Data client to the mapped port.
3. Create the test index and mapping.
4. Write fixtures.
5. Refresh the index.
6. Run search assertions.
7. Clean up the index or documents after the test.

Testcontainers solves test environment consistency; explicit refresh solves search visibility. These two mechanisms complement each other.

Do not add sleep after container startup to guess when Elasticsearch is ready. Use Testcontainers' wait strategy/health check or verify the cluster health endpoint before running tests.

## 18. Waiting for Elasticsearch Readiness vs Waiting for Document Searchability

Two conditions are often confused:

1. The Elasticsearch service is ready to accept requests.
2. A specific document has appeared in search results.

To wait for service readiness, use health checks or Testcontainers wait strategies:

~~~java
static ElasticsearchContainer elasticsearch =
        new ElasticsearchContainer("docker.elastic.co/elasticsearch/elasticsearch:8.17.0");
~~~

Testcontainers can wait for the HTTP endpoint to return the expected response before reporting the container ready. The image version must be compatible with the Spring Data Elasticsearch and Java client versions in use.

To wait for a document to be searchable, use refresh or poll a specific query. Cluster health checks do not prove a document has been indexed.

## 19. Designing Shared Helpers for Tests

If many tests need explicit refreshes, create a small helper:

~~~java
public final class ElasticsearchTestSupport {

    private final ElasticsearchOperations operations;

    public ElasticsearchTestSupport(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void refreshProducts() {
        operations.indexOps(IndexCoordinates.of("products")).refresh();
    }
}
~~~

Test:

~~~java
repository.saveAll(products);
testSupport.refreshProducts();

assertThat(repository.findByCategory("accessories"))
        .hasSize(3);
~~~

Helper names should clearly state that the index is being refreshed. Avoid generic methods like `sleepUntilReady()` that obscure the real synchronization mechanism.

### 19.1. Condition-Waiting Helpers

For async pipelines, you can wrap Awaitility:

~~~java
public final class ElasticsearchAwait {

    public static void untilAsserted(ThrowingRunnable assertion) {
        await()
                .atMost(Duration.ofSeconds(10))
                .pollInterval(Duration.ofMillis(100))
                .untilAsserted(assertion);
    }

    private ElasticsearchAwait() {
    }
}
~~~

Do not make the default timeout overly long or impossible to override. Tests with slower pipelines should pass an explicit timeout instead of silently inflating wait limits for every test.

## 20. Diagnosing Test Timeouts

If search still misses a document after an explicit refresh, the issue may no longer be refresh:

- The document was never written successfully.
- The test wrote to a different index than the query searches.
- An alias points to another index.
- ID or field mapping is wrong.
- The query does not match the data.
- A bulk item failed.
- The document was deleted or updated by another test.
- Search filters or routing excluded the document from results.

When Awaitility times out, log safe diagnostic details:

- Index/alias being queried.
- Fixture ID or correlation ID.
- Current hit count.
- Consumer/job status if applicable.
- Bulk failure summary if applicable.
- Cluster health and connection errors if needed.

Never log full documents containing sensitive data just for diagnostics.

## 21. Avoiding Race Conditions Between Tests

Tests running in parallel on the same index can break one another:

- Test A deletes the entire index while Test B is searching.
- Test A refreshes right after Test B seeds fixtures.
- Test B counts documents while Test A also inserts data.
- Two tests use the same ID and overwrite each other.

Solutions:

- Use a dedicated index per test class or test run.
- Use test-namespaced IDs.
- Do not call `deleteAll` on a shared index across parallel tests.
- Clean up data by ID or delete test-owned indices.
- Refresh only indices owned by the test.
- Disable parallel execution if tests genuinely share resources without isolation.

Refresh does not resolve race conditions caused by shared test data. It only updates search visibility.

## 22. Choosing Reasonable Poll Intervals and Timeouts

Too short a poll interval generates excessive search requests; too long a poll interval makes tests wait unnecessarily after a condition becomes true.

Starting points:

| Test type | Example poll interval | Example timeout |
|---|---:|---:|
| Single document in local container | 50–100 ms | 3–5 s |
| Simple event consumer | 100–200 ms | 5–10 s |
| Large batch import | 200–500 ms | 15–30 s |
| Slow CI environment | 200–500 ms | Per test SLA |

These are starting points to tune against observed runtimes, not mandatory constants. Track pipeline completion times and timeout rates in CI.

If a pipeline processes thousands of documents, prefer a batch completion signal or job status rather than polling a heavy search query at high frequency.

## 23. Common Pitfalls

### Calling save and Searching Immediately

The index request may succeed before the searcher refreshes. Refresh the index before searching or wait with `WAIT_UNTIL`.

### Using Thread.sleep(1000)

Sleeping does not know whether refresh happened. Use explicit refresh or condition polling with a timeout.

### Refreshing the Whole Cluster

Refreshing all indices can affect other tests. Refresh only the index or alias owned by the test.

### Refreshing Before the Consumer Finishes Writing

Refreshing early does not process events or finish worker tasks. Wait for the pipeline's final condition.

### Using GET by ID to Verify Search Visibility

Real-time GET can return the document before search sees it. Use a search query if search visibility is the goal.

### Using WAIT_UNTIL When Refresh Interval Is Disabled

Without scheduled refreshes, the request may wait until another refresh arrives or it times out. Configure refresh explicitly in tests.

### Using IMMEDIATE for Every Production Write

Frequent refreshes degrade indexing throughput. Choose policies per requirement and keep `NONE` for writes that do not need immediate visibility.

### Creating a Refresh Publisher Without Chaining It to Search

In reactive tests, two separate publishers do not guarantee execution order. Use `thenMany` or `concat` so the query runs after refresh.

### Calling subscribe in Test Setup and Searching Immediately

An independent subscription might not finish before search runs. Compose publishers and verify outcomes with `StepVerifier`.

### Polling a Condition That Is Too Weak

Checking only for at least one document can finish early before a batch completes. Assert exact counts or terminal states.

### Polling Without a Timeout

Tests can hang indefinitely. Always specify `atMost` and describe the condition with `alias`.

### Polling Too Frequently

Creates unnecessary search load. Pick a sensible poll interval and limit concurrency.

### Confusing Cluster Readiness with Document Visibility

Health checks only prove Elasticsearch can receive requests. They do not prove events were processed or documents are searchable.

### Sharing an Index Across Parallel Tests

Refresh does not prevent other tests from deleting/overwriting data. Isolate indices and fixtures.

## 24. Recommended Testing Workflow

When writing integration tests with Spring Data Elasticsearch:

1. Determine whether the test checks real-time GET or search visibility.
2. Use a version-compatible Elasticsearch container/cluster.
3. Wait for cluster readiness using health checks or a Testcontainers wait strategy.
4. Create dedicated test indices and mappings.
5. Write fixtures via the repository or operations.
6. If searching right after fixtures, call `IndexOperations.refresh` on the exact index.
7. If testing refresh policies, configure `IMMEDIATE` or `WAIT_UNTIL` on that request.
8. If waiting on a consumer/event pipeline, poll the search-visible condition with Awaitility.
9. Set explicit timeouts and poll intervals.
10. Assert final counts/states rather than checking for a single hit.
11. When testing reactively, compose refresh and search with `thenMany`; use `StepVerifier` to await publishers.
12. Clean up test-scoped data/indices and refresh if subsequent tests expect deleted state in search.
13. Isolate indices when running tests in parallel.
14. On timeouts, inspect indexing results, target indices, queries, mappings, and pipeline status instead of increasing sleep durations.

## 25. Summary

Elasticsearch search is near real-time. A document may be written successfully yet remain invisible to search until the shard refreshes. GET by ID is real-time by default and generally does not require refresh; search and count depend on the searcher and may need to wait for refresh.

In integration tests, explicit refresh via `IndexOperations` is a clear way to make fixtures immediately search-visible. For bulk requests, `RefreshPolicy.IMMEDIATE` forces an immediate refresh, `WAIT_UNTIL` waits for the next refresh, and `NONE` requests no special refresh. Avoid using `IMMEDIATE` for all production writes because refreshes carry overhead.

For asynchronous pipelines, use Awaitility to wait on observable conditions such as the document appearing in search, reaching expected counts, or achieving final state. Every wait needs a reasonable timeout and poll interval. For reactive tests, chain refresh and search with `thenMany` and verify publishers with `StepVerifier`; do not subscribe separately or block in application code.

Fixed `Thread.sleep` does not synchronize with real state and makes tests both slow and flaky. Choose explicit refresh, refresh policies, or condition polling based on what the test proves; isolate indices and fixtures to avoid cross-test races.

## References

- [Spring Data Elasticsearch – IndexOperations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/IndexOperations.html)
- [Spring Data Elasticsearch – ReactiveIndexOperations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/ReactiveIndexOperations.html)
- [Spring Data Elasticsearch – BulkOptions API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/BulkOptions.html)
- [Spring Data Elasticsearch – RefreshPolicy API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/RefreshPolicy.html)
- [Elasticsearch – Near real-time search](https://www.elastic.co/guide/en/elasticsearch/reference/current/near-real-time.html)
- [Elasticsearch – Refresh API](https://www.elastic.co/guide/en/elasticsearch/reference/current/indices-refresh.html)
- [Elasticsearch – Index API refresh parameter](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-index_.html#index-refresh)
- [Awaitility – Usage](https://github.com/awaitility/awaitility/wiki/Usage)
- [Testcontainers – Elasticsearch Module](https://java.testcontainers.org/modules/elasticsearch/)
