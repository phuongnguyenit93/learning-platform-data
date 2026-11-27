# Non-Blocking Save, Search, and Delete Chains

Spring Data Elasticsearch Reactive enables applications to perform read and write operations in a reactive model without holding a thread waiting synchronously for each Elasticsearch request. Instead of returning entities directly, reactive APIs return Project Reactor's `Mono<T>` or `Flux<T>`. Applications can chain publishers to save a document, search for the saved document, process the result, and delete the document without calling `block()` between steps.

A proper reactive chain requires three things:

1. Dependent steps are linked with the right operators so a subsequent step runs only after the previous step completes.
2. The publisher is returned to the caller so the framework manages subscription; the service does not call `subscribe()` itself and does not stall threads with `block()`.
3. The semantics of each operation are clearly understood. For example, `save()` completing does not mean the document is immediately searchable; the Search API is still subject to refresh behavior.

Example business flow:

```text
HTTP request
    |
    v
repository.save(product)          Mono<Product>
    |
    | flatMap(saved -> ...)
    v
repository.findBySku(saved.sku)   Mono<Product> (search query)
    |
    | flatMap(found -> ...)
    v
repository.delete(found)          Mono<Void>
    |
    | thenReturn(saved)
    v
Mono<Product> returned to WebFlux
```

The entire flow is described as a single publisher. Upon subscription, Reactor coordinates the operations according to their dependencies and emits completion or error signals.

## 1. Reactive in Spring Data Elasticsearch

Spring Data Elasticsearch has two primary API families:

- Imperative APIs such as `ElasticsearchOperations` and `ElasticsearchRepository`, which typically return entities, `List`, `Page`, or synchronous results.
- Reactive APIs such as `ReactiveElasticsearchOperations` and `ReactiveElasticsearchRepository`, which return `Mono` or `Flux`.

Reactive APIs fit Spring WebFlux applications or systems using Reactor end-to-end. They prevent request-handling threads from sitting idle waiting for Elasticsearch I/O to finish.

Reactivity is not merely changing a return type from `Product` to `Mono<Product>`. To retain non-blocking benefits, the entire path must use non-blocking clients and operations. Calling blocking JDBC, `Thread.sleep`, imperative repositories, or `.block()` inside the chain can still stall threads.

### 1.1. `Mono` and `Flux`

| Type | Element count | Example |
|---|---|---|
| `Mono<T>` | 0 or 1 element, followed by complete or error. | Save one product, fetch by ID, delete one document. |
| `Flux<T>` | 0 to many elements, followed by complete or error. | Search a list of products, stream hits, save multiple entities. |

Example:

```java
Mono<Product> saved = repository.save(product);

Mono<Product> byId = repository.findById("P-100");

Flux<Product> activeProducts = repository.findByStatus("ACTIVE");
```

These variables only hold publishers. They have not necessarily sent requests to Elasticsearch yet. Reactive publishers are typically lazy: operations execute when a subscriber requests data.

### 1.2. A Publisher Is a Description of Work

The code:

```java
Mono<Product> result = repository.save(product);
```

does not guarantee the request was sent at that line. It creates a publisher describing the save operation. Execution happens when a WebFlux handler returns the publisher to the framework or when a test subscribes.

Creating a publisher and discarding it without a subscriber means the operation may never execute:

```java
repository.save(product); // Neither used nor subscribed to: does not form a complete workflow.
```

Always chain publishers into the returned flow or let the framework subscribe at the proper boundary.

## 2. Declaring the Entity and Reactive Repository

Example product entity:

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

    @Field(type = FieldType.Keyword)
    private String status;

    // constructors, getters, setters
}
```

Declaring the reactive repository:

```java
import org.springframework.data.elasticsearch.repository.ReactiveElasticsearchRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ProductRepository
        extends ReactiveElasticsearchRepository<Product, String> {

    Mono<Product> findBySku(String sku);

    Flux<Product> findByStatus(String status);
}
```

The repository inherits reactive CRUD operations:

- `save(entity)` returns `Mono<S>`.
- `findById(id)` returns `Mono<T>`.
- `findAll()` returns `Flux<T>`.
- `delete(entity)` returns `Mono<Void>`.
- `deleteById(id)` returns `Mono<Void>`.
- `saveAll(Publisher<S>)` returns `Flux<S>`.

Derived methods such as `findBySku` and `findByStatus` are translated by Spring Data into property-based search queries. They follow Search API semantics, not Get API semantics by `_id`.

## 3. Non-Blocking Save of a Document

Saving an entity with the reactive repository:

```java
public Mono<Product> create(Product product) {
    return repository.save(product);
}
```

Or via `ReactiveElasticsearchOperations`:

```java
import org.springframework.data.elasticsearch.core.ReactiveElasticsearchOperations;
import reactor.core.publisher.Mono;

public Mono<Product> create(Product product) {
    return operations.save(product);
}
```

Both approaches return a publisher. The service does not need to spawn a separate thread or call `subscribe()` to start saving.

If you need to transform the entity before returning the result, use `map`:

```java
public Mono<ProductResponse> create(Product product) {
    return repository.save(product)
            .map(saved -> new ProductResponse(
                    saved.getId(),
                    saved.getSku(),
                    saved.getName()
            ));
}
```

`map` performs a synchronous value-to-value transformation. If the next step returns a `Mono` or `Flux`, use `flatMap` to chain the publisher and avoid nested structures like `Mono<Mono<T>>`.

## 4. Searching with a Reactive Repository

Derived methods return `Flux` when multiple results may exist:

```java
public Flux<Product> findActiveProducts() {
    return repository.findByStatus("ACTIVE");
}
```

If a query can return at most one result, use `Mono`:

```java
public Mono<Product> findBySku(String sku) {
    return repository.findBySku(sku);
}
```

For lookup by `_id`, use `findById`:

```java
public Mono<Product> findById(String id) {
    return repository.findById(id);
}
```

Distinguishing the two read modes:

| Method | Read type | Characteristics |
|---|---|---|
| `findById(id)` | Get by ID | Real-time by default in Elasticsearch. |
| `findBySku(sku)` | Derived search query | Near-real-time; depends on refresh to see new writes. |
| `findByStatus(status)` | Derived search query | Near-real-time; may return multiple results. |

If you save a product and immediately call `findBySku`, the query may not see the product yet because the index has not refreshed. Chaining two publishers with `flatMap` only enforces execution order; it does not force a refresh.

## 5. Searching with `ReactiveElasticsearchOperations`

When a CriteriaQuery or native query more complex than derived methods is needed, use `ReactiveElasticsearchOperations`.

CriteriaQuery example:

```java
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.ReactiveElasticsearchOperations;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.Query;
import reactor.core.publisher.Flux;

public Flux<SearchHit<Product>> searchActiveProducts() {
    Query query = new CriteriaQuery(
            new Criteria("status").is("ACTIVE")
    );

    return operations.search(query, Product.class);
}
```

`search` returns `Flux<SearchHit<Product>>`; each `SearchHit` holds the entity and metadata such as ID, score, and sort values. If only the entity is needed:

```java
public Flux<Product> searchActiveProductContents() {
    Query query = new CriteriaQuery(
            new Criteria("status").is("ACTIVE")
    );

    return operations.search(query, Product.class)
            .map(SearchHit::getContent);
}
```

When aggregated metadata in a `SearchHits` object is needed, you can use the `searchForHits` API returning `Mono<SearchHits<T>>` in Spring Data Elasticsearch versions that support it:

```java
Mono<SearchHits<Product>> searchHits =
        operations.searchForHits(query, Product.class);
```

`SearchHits` holds the collected list of results. For streaming large datasets, prefer `Flux<SearchHit<T>>` instead of collecting everything into a single object.

## 6. Non-Blocking Document Deletion

Delete by ID:

```java
public Mono<Void> deleteById(String id) {
    return repository.deleteById(id);
}
```

Delete an entity:

```java
public Mono<Void> delete(Product product) {
    return repository.delete(product);
}
```

Reactive `delete` usually returns `Mono<Void>`: the publisher signals completion when the operation finishes without emitting the deleted entity.

If you need to return a value after deletion, use `thenReturn`:

```java
public Mono<String> deleteAndReturnId(String id) {
    return repository.deleteById(id)
            .thenReturn(id);
}
```

`thenReturn(id)` only emits the ID after deletion completes. If the delete emits an error, `thenReturn` does not run.

## 7. Chaining `save → search → delete` into One Reactive Chain

This is the central pattern of the lesson. Suppose SKU is unique and the business workflow requires:

1. Save the product.
2. Search for the product again by SKU via a derived search query.
3. Delete the found product.
4. Return the saved entity as the workflow result.

```java
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ProductWorkflowService {

    private final ProductRepository repository;

    public ProductWorkflowService(ProductRepository repository) {
        this.repository = repository;
    }

    public Mono<Product> saveSearchAndDelete(Product input) {
        return repository.save(input)
                .flatMap(saved -> repository.findBySku(saved.getSku())
                        .switchIfEmpty(Mono.error(
                                new IllegalStateException(
                                        "Saved product was not found by SKU")))
                        .flatMap(found -> repository.delete(found)
                                .thenReturn(saved)));
    }
}
```

Reading the chain step by step:

- `repository.save(input)` returns `Mono<Product>`.
- `flatMap(saved -> ...)` waits for the save publisher to emit the entity before creating the next publisher.
- `findBySku(saved.getSku())` executes the derived search query.
- `switchIfEmpty(...)` turns an empty search result into a clear business exception.
- `flatMap(found -> repository.delete(found)...)` deletes only after the document has been found.
- `thenReturn(saved)` emits the saved entity after deletion completes.

The method returns `Mono<Product>`, never subscribes itself, and never blocks. If search finds no document or deletion fails, the publisher terminates with an error.

### 7.1. Refresh Warning in the Chain Above

The operator chain guarantees ordering: save finishes before search begins. However, `findBySku` uses the Search API, which is near-real-time. If the index has not refreshed, the search step might not find the newly saved product.

If the business flow truly requires searching immediately after saving, you can request an explicit refresh:

```java
public Mono<Product> saveRefreshSearchAndDelete(Product input) {
    return repository.save(input)
            .flatMap(saved -> operations.indexOps(Product.class)
                    .refresh()
                    .thenReturn(saved))
            .flatMap(saved -> repository.findBySku(saved.getSku())
                    .switchIfEmpty(Mono.error(
                            new IllegalStateException("Product not searchable")))
                    .flatMap(found -> repository.delete(found)
                            .thenReturn(saved)));
}
```

`ReactiveIndexOperations.refresh()` returns a publisher that completes when the refresh finishes. `thenReturn(saved)` passes control to the search step only after the refresh. Refreshing an entire index has cost, so avoid adding it to every request if the application tolerates near-real-time visibility. Another option is configuring the write refresh policy to `WAIT_UNTIL` for flows requiring search read-after-write, depending on your Spring Data Elasticsearch version and setup.

If you only need to read the newly saved document by ID, `findById(saved.getId())` is usually better and requires no refresh for GET visibility.

## 8. Which Operator for Which Step?

Key Reactor operators when chaining CRUD operations:

| Operator | Use when | Example |
|---|---|---|
| `map` | Synchronously transforming a value. | `Product` → `ProductResponse`. |
| `flatMap` | Next step returns a publisher; allows non-sequential execution when handling multiple elements. | Save first, then call find. |
| `concatMap` | Processing elements sequentially in order, waiting for the previous inner publisher to complete. | Search multiple products and delete sequentially. |
| `flatMapSequential` | Running inner publishers potentially concurrently while emitting results in source order. | Map multiple records in parallel while preserving output order. |
| `then` | Waiting for the previous publisher to complete and then running the next publisher, ignoring the prior value. | Save first, then refresh. |
| `thenReturn` | Waiting for completion and then emitting a fixed value. | Delete first, then return ID. |
| `thenMany` | Waiting for a `Mono`/publisher to complete and then starting the next `Flux`. | Save first, then stream search results. |
| `switchIfEmpty` | Providing an alternative publisher when upstream completes without emitting elements. | Throw an error if SKU is not found. |
| `zip` | Combining results from independent publishers. | Fetch two independent statistics. |
| `onErrorResume` | Translating an error into an alternative publisher. | Map errors into fallback responses or domain errors. |
| `retryWhen` | Retrying according to a policy on eligible errors. | Bounded retry for transient failures. |

### 8.1. `map` and `flatMap`

Type mismatch when using `map` to return a publisher:

```java
Mono<Mono<Product>> nested = repository.save(product)
        .map(saved -> repository.findById(saved.getId()));
```

The result is `Mono<Mono<Product>>`, not `Mono<Product>`. Use `flatMap` to flatten:

```java
Mono<Product> loaded = repository.save(product)
        .flatMap(saved -> repository.findById(saved.getId()));
```

### 8.2. `then` and `flatMap`

If you do not need the value from the previous step, use `then`:

```java
Mono<Void> saveThenDelete(String id, Product product) {
    return repository.save(product)
            .then(repository.deleteById(id));
}
```

`then` ignores the saved entity and only cares that the publisher completed. If you need the saved entity to compute the ID, use `flatMap`.

### 8.3. `thenMany` for Search Streams

Example saving a product and then streaming products with the same status:

```java
Flux<Product> saveThenSearch(Product product) {
    return repository.save(product)
            .thenMany(repository.findByStatus(product.getStatus()));
}
```

The search starts only after save completes. As noted earlier, this alone does not guarantee search sees the newly saved write; refresh if the use case requires it.

## 9. Handling Multiple Results and Sequential Deletion

Suppose you need to find discontinued products and delete them. The repository returns `Flux<Product>`:

```java
public Mono<Void> deleteDiscontinuedProducts() {
    return repository.findByStatus("DISCONTINUED")
            .concatMap(repository::delete)
            .then();
}
```

`concatMap` processes each product in order: deleting the current item completes before moving to the next item. `.then()` discards intermediate signals and returns `Mono<Void>` once the entire stream finishes.

If order is not required and bounded concurrent operations are acceptable:

```java
public Mono<Void> deleteDiscontinuedProducts() {
    return repository.findByStatus("DISCONTINUED")
            .flatMap(repository::delete, 4)
            .then();
}
```

The parameter `4` limits how many inner publishers are subscribed to concurrently. This is a small concurrency example; choose an appropriate value based on cluster load and application requirements.

Do not use unbounded `flatMap` on a very large Flux when each element issues an Elasticsearch request. Doing so can issue too many simultaneous requests, straining connection pools, threads, the cluster, and memory.

## 10. Backpressure When Reading and Writing Many Documents

`Flux` supports backpressure: downstream can request data based on demand. When reactive publishers are properly chained, the system can pace reading and processing rather than pushing all data into memory at once.

Example limiting elements processed in a stream:

```java
Flux<Product> limited = repository.findAll()
        .limitRate(100);
```

`limitRate` adjusts how Reactor requests data from upstream; it is not a cap on total documents in the index. If you only want at most 100 results, use `take(100)`:

```java
Flux<Product> firstHundred = repository.findByStatus("ACTIVE")
        .take(100);
```

### 10.1. Saving a Stream of Entities

Reactive repositories support `saveAll(Publisher<S>)`:

```java
Flux<Product> source = productSource.readProducts();

Flux<Product> saved = repository.saveAll(source);
```

This expresses a reactive save stream. However, `saveAll(Publisher)` should not be assumed by default to execute as a single Bulk API request. Implementation semantics and request batching depend on the Spring Data/client version. If specific bulk requests are required, use the appropriate bulk API and control batch sizes explicitly.

### 10.2. Buffering into Batches

When processing in small groups is needed:

```java
Flux<List<Product>> batches = source.buffer(500);
```

Then process each batch sequentially:

```java
Mono<Void> importProducts(Flux<Product> source) {
    return source
            .buffer(500)
            .concatMap(batch -> repository.saveAll(batch).then())
            .then();
}
```

This snippet buffers up to 500 elements and moves to the next batch only after the current batch completes. For very large sources, ensure the source truly streams; do not build a `List` holding all data before calling `buffer`.

### 10.3. Limiting Concurrency During Imports

If you want to process a few batches concurrently:

```java
Mono<Void> importProducts(Flux<Product> source) {
    return source
            .buffer(500)
            .flatMap(batch -> repository.saveAll(batch).then(), 2)
            .then();
}
```

This limits the pipeline to at most two concurrent batches. Raising concurrency can increase throughput up to a point, while also increasing memory usage and pressure on Elasticsearch. Benchmark and monitor for 429 errors and latency.

## 11. Handling Missing Results

A `Mono` can complete without emitting an element. For `findById` or queries returning at most one document, define the business behavior when no result exists.

Returning 404 in a WebFlux controller can be handled using `switchIfEmpty`:

```java
public Mono<Product> getRequired(String id) {
    return repository.findById(id)
            .switchIfEmpty(Mono.error(
                    new ProductNotFoundException(id)));
}
```

Or returning a default value:

```java
public Mono<Product> findOrDefault(String sku) {
    return repository.findBySku(sku)
            .switchIfEmpty(Mono.just(Product.notFoundPlaceholder()));
}
```

Only use a default when the domain permits it. For update/delete operations, clearly distinguish missing documents from success.

Never use `defaultIfEmpty(null)` because Reactor forbids emitting `null` as an element. Use `switchIfEmpty`, `Mono.empty()`, or a dedicated result type.

## 12. Error Handling in Reactive Chains

Errors from an operation in the chain typically propagate downstream and terminate the stream unless handled by an appropriate operator.

Example translating infrastructure exceptions into domain exceptions:

```java
public Mono<Product> create(Product product) {
    return repository.save(product)
            .onErrorMap(error ->
                    new ProductPersistenceException(
                            "Could not save product", error));
}
```

### 12.1. `onErrorResume`

`onErrorResume` replaces an errored publisher with another publisher:

```java
public Mono<Product> findOrCreate(String sku) {
    return repository.findBySku(sku)
            .switchIfEmpty(Mono.defer(() -> repository.save(newProduct(sku))))
            .onErrorResume(TemporaryElasticsearchException.class,
                    error -> fallbackLookup(sku));
}
```

Only use a fallback when the alternative result makes business sense. Avoid catching every exception and returning `Mono.empty()`, as real failures can be masked as missing data.

### 12.2. `retryWhen`

Transient failures can be retried with limits and backoff:

```java
import java.time.Duration;
import reactor.util.retry.Retry;

public Mono<Product> findByIdWithRetry(String id) {
    return repository.findById(id)
            .retryWhen(Retry.backoff(3, Duration.ofMillis(200))
                    .maxBackoff(Duration.ofSeconds(2))
                    .filter(this::isTransientFailure));
}
```

This example retries only when `isTransientFailure` identifies a transient failure. Never retry validation, mapping, authorization, or non-recoverable business errors.

Be especially careful when retrying write operations. If Elasticsearch already wrote the document but the response was lost due to a timeout, a retry can resubmit the operation. Use stable IDs and idempotent operations; with incremental updates or non-idempotent scripts, retries can apply changes multiple times.

### 12.3. Avoid Abusing `onErrorContinue`

`onErrorContinue` can swallow certain errors and keep the stream running, yet it easily loses context about which item failed and causes silent data drops. For imports or multi-document operations, classify errors per item, write explicit dead-letter records or checkpoints, and use operators with predictable semantics.

## 13. Reactivity Does Not Equal Transactions

A chain such as:

```java
repository.save(product)
        .flatMap(saved -> repository.findBySku(saved.getSku()))
        .flatMap(repository::delete);
```

enforces dependency ordering between steps in the publisher. It does not turn those three operations into an atomic transaction in Elasticsearch.

If save succeeds but search or delete fails, the document may remain present. If delete succeeds but the response is lost, the application may not know the exact final state.

For multi-step workflows, design:

- Operations that can be retried safely.
- Stable IDs and version conditions on updates.
- Workflow state/checkpoints if resuming after failures is required.
- Compensation if business rules require undoing a previously completed step.
- Logging and metrics to observe which steps completed.

Never assume `flatMap` provides rollback or isolation like a relational database transaction.

## 14. Returning Publishers from WebFlux Controllers

In a Spring WebFlux application, controllers can return `Mono` or `Flux` directly. WebFlux manages the subscription and writes the response as the publisher emits data.

Controller example:

```java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/products")
public class ProductController {

    private final ProductWorkflowService service;

    public ProductController(ProductWorkflowService service) {
        this.service = service;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public Mono<Product> create(@RequestBody Product product) {
        return service.create(product);
    }

    @GetMapping("/{id}")
    public Mono<Product> get(@PathVariable String id) {
        return service.getRequired(id);
    }

    @GetMapping
    public Flux<Product> findByStatus(@RequestParam String status) {
        return service.findByStatus(status);
    }

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public Mono<Void> delete(@PathVariable String id) {
        return service.deleteById(id);
    }
}
```

The controller does not call `.subscribe()` or `.block()`. It returns the publisher to the WebFlux runtime. When a request arrives, the framework subscribes, manages signals, and writes the result to the HTTP response.

### 14.1. When Is `subscribe()` Actually Needed?

In a normal WebFlux application, never subscribe manually inside a service or controller. If a service writes:

```java
public void create(Product product) {
    repository.save(product).subscribe();
}
```

then the service returns before knowing whether the operation completed, errors are not propagated to the caller, and the framework cannot manage the operation's lifecycle as part of the request.

`subscribe()` is appropriate at explicit boundaries managing background tasks, such as a consumer or scheduler that owns lifecycle, cancellation, and error handling. In those cases, manage the `Disposable`, shutdown, and error monitoring. Never use it as a substitute for returning publishers.

### 14.2. Why Avoid `block()`?

The following code defeats the benefits of reactivity:

```java
public Product createBlocking(Product product) {
    return repository.save(product).block();
}
```

`block()` waits synchronously for the result. If called on a WebFlux event-loop thread, it can cause starvation or throw blocking-call errors on non-blocking threads. Return `Mono<Product>` and chain steps with operators instead.

If you must call an irreplaceable blocking library, isolate it on an appropriate scheduler such as `Schedulers.boundedElastic()` and cap the load. Do not offload all reactive Elasticsearch operations onto a scheduler just because a small part of the flow is blocking.

## 15. Reactive Search and Read-After-Write

Reactivity does not alter Elasticsearch's consistency model. `ReactiveElasticsearchOperations.get` still uses the Get API; `search` still uses the Search API.

Example:

```java
public Mono<Product> saveThenGet(Product product) {
    return repository.save(product)
            .flatMap(saved -> repository.findById(saved.getId()));
}
```

Get by ID can see the newly saved document immediately because the Get API is real-time by default.

Conversely:

```java
public Mono<Product> saveThenSearch(Product product) {
    return repository.save(product)
            .flatMap(saved -> repository.findBySku(saved.getSku()));
}
```

`findBySku` is a search query. It may not yet see the document if the index has not refreshed.

If immediate search visibility is required, you can refresh within the reactive chain:

```java
public Mono<Product> saveRefreshThenSearch(Product product) {
    return repository.save(product)
            .flatMap(saved -> operations.indexOps(Product.class)
                    .refresh()
                    .thenReturn(saved))
            .flatMap(saved -> repository.findBySku(saved.getSku()));
}
```

Refreshing returns `Mono<Void>`, so it composes cleanly with `thenReturn`. There is no need to call `block()` to wait for the refresh. Use this approach only when search visibility is genuinely required; refreshing too frequently reduces throughput.

## 16. Reactive Delete and Search Visibility

Delete completion does not mean a search query immediately stops returning the document. Search remains near-real-time and requires a refresh to reflect the deletion.

Example:

```java
public Mono<Void> deleteAndRefresh(String id) {
    return repository.deleteById(id)
            .then(operations.indexOps(Product.class).refresh());
}
```

The publisher completes only after both the delete and refresh finish. If you only need to delete a document by ID, no refresh is needed for the Get API to reflect the new state; refresh is only needed when search queries must immediately reflect the deletion.

## 17. Combining Independent Operations with `zip`

If two operations are independent, they can run concurrently and have their results combined:

```java
public Mono<DashboardSummary> loadSummary() {
    Mono<Long> activeCount = operations.count(
            new CriteriaQuery(new Criteria("status").is("ACTIVE")),
            Product.class
    );

    Mono<Long> discontinuedCount = operations.count(
            new CriteriaQuery(new Criteria("status").is("DISCONTINUED")),
            Product.class
    );

    return Mono.zip(activeCount, discontinuedCount)
            .map(tuple -> new DashboardSummary(
                    tuple.getT1(),
                    tuple.getT2()
            ));
}
```

The two counts are independent, so they can run concurrently. In contrast, saving and then searching for the newly saved document is a dependent relationship; use `flatMap`/`then`, not `zip`, when expecting the later step to wait for the earlier one.

Count method names and return types must match your project's `ReactiveElasticsearchOperations` version; in modern reactive versions, count returns `Mono<Long>`.

## 18. Testing Reactive Chains with StepVerifier

Do not test reactive code by calling `.block()` inside production test helpers. Reactor provides `StepVerifier` to subscribe and verify signals.

Unit test example with a mocked repository:

```java
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.verify;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ProductWorkflowServiceTest {

    @Test
    void saveSearchAndDeleteInOrder() {
        Product input = new Product("P-100", "SKU-100", "Keyboard", "ACTIVE");
        Product saved = input;

        when(repository.save(input)).thenReturn(Mono.just(saved));
        when(repository.findBySku("SKU-100")).thenReturn(Mono.just(saved));
        when(repository.delete(saved)).thenReturn(Mono.empty());

        StepVerifier.create(service.saveSearchAndDelete(input))
                .expectNext(saved)
                .verifyComplete();

        verify(repository).save(input);
        verify(repository).findBySku("SKU-100");
        verify(repository).delete(saved);
    }
}
```

This unit test illustrates the operator flow. Mocks do not verify Elasticsearch refresh, mappings, or actual Query DSL.

### 18.1. Testing the Empty Search Case

```java
when(repository.save(input)).thenReturn(Mono.just(saved));
when(repository.findBySku(saved.getSku())).thenReturn(Mono.empty());

StepVerifier.create(service.saveSearchAndDelete(input))
        .expectError(IllegalStateException.class)
        .verify();
```

Verify that delete is not called if the search does not find the document. With mocks, you can use `verify(repository, never()).delete(any())`.

### 18.2. Integration Testing with Elasticsearch

To verify real semantics, use a real Elasticsearch instance or Testcontainers with a compatible version:

1. Create the index and mapping for the entity.
2. Call reactive save.
3. Use `StepVerifier` to confirm save completion.
4. Check Get by ID.
5. Perform a controlled refresh if the search test needs immediate write visibility.
6. Run the reactive search and assert results.
7. Call reactive delete and verify completion.
8. Refresh if you need to verify search no longer returns the document.

Do not use `Thread.sleep` to wait for refresh. Use the refresh API or the `WAIT_UNTIL` write refresh policy when tests require visibility.

## 19. Common Pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| Calling `save()` does not save the document | Publisher was created without a subscription or not returned in the response chain. | Return the publisher to the caller/framework or manage subscription at the proper boundary. |
| Service returns before operation finishes | Called `subscribe()` internally and discarded the publisher. | Return `Mono`/`Flux` and let WebFlux manage subscription. |
| Event loop gets blocked | Called `.block()`, `Thread.sleep`, or a blocking library inside the chain. | Use reactive APIs; isolate blocking libraries on an appropriate scheduler if unavoidable. |
| Result type becomes `Mono<Mono<T>>` | Used `map` to return a publisher. | Use `flatMap`. |
| Search right after save misses document | Search API is near-real-time; index not refreshed yet. | Use GET by ID or refresh/`WAIT_UNTIL` if search visibility is required. |
| Delete completes yet search still returns document | Delete not refreshed yet. | Refresh if search must reflect the deletion immediately. |
| Chain runs in the wrong order | Used independent publishers or `zip` for dependent steps. | Use `flatMap`, `then`, `thenMany` to express dependencies. |
| Excessive concurrent Elasticsearch requests | Unbounded `flatMap` on a large Flux. | Use a concurrency limit, `concatMap`, or bounded queue. |
| Import still consumes high heap | Loaded the entire source into a `List` before creating a Flux. | Use a streaming source, bounded `buffer`, and backpressure. |
| Retry applies update twice | Operation is non-idempotent or response timed out after server wrote. | Use stable IDs/versions and selective retries. |
| Errors silently lost in background job | `subscribe()` without error handler or Disposable lifecycle. | Return the publisher or manage errors/lifecycle of the background task. |
| Tests are timing-dependent | Used `Thread.sleep` to wait for refresh. | Use the refresh API, `WAIT_UNTIL`, and StepVerifier. |

## 20. Workflow for Designing a Reactive CRUD Chain

1. **Identify each operation:** save, get, search, or delete; select the matching repository method or operations API.
2. **Choose the publisher type:** `Mono` for 0/1 results, `Flux` for multiple results.
3. **Map dependencies:** does a later step need the result or completion of an earlier step?
4. **Pick operators:** `map` for synchronous transforms, `flatMap` for dependent publishers, `then` when discarding the previous value, `concatMap` when ordering is required.
5. **Determine consistency:** real-time GET vs. near-real-time Search; is a refresh required?
6. **Handle empty cases:** decide between not-found error, default value, or ignoring.
7. **Handle errors:** classify domain, data, and infrastructure errors; apply bounded retries.
8. **Control load:** apply backpressure, batch sizes, and concurrency limits.
9. **Return the publisher:** let WebFlux or the calling layer manage subscription; avoid `block()` and `subscribe()` in services.
10. **Test:** StepVerifier for operator flows and integration tests for Elasticsearch behavior.

## 21. Key Takeaways

- Reactive Elasticsearch uses `Mono` for 0/1 results and `Flux` for 0/many results.
- `ReactiveElasticsearchRepository` and `ReactiveElasticsearchOperations` provide non-blocking CRUD and search APIs.
- Publishers are typically lazy; creating a publisher does not mean the request has executed.
- Use `flatMap` when the next step returns a publisher; use `map` for synchronous transformations.
- Use `then`/`thenMany` when only waiting for completion of the prior step; `thenReturn` emits a value after completion.
- Use `concatMap` when sequential per-item processing is required; cap concurrency when using `flatMap` on a large Flux.
- `findById` uses the Get API; derived queries like `findBySku` use the Search API and may experience refresh delay.
- Saving and then searching in the same chain does not force a refresh; refreshing is an explicit choice based on visibility requirements.
- Reactive delete returns `Mono<Void>`; use `thenReturn` if you need to emit a result after deletion.
- `saveAll(Publisher)` is a reactive API, not automatically synonymous with a single Bulk API request.
- Backpressure and bounded batches prevent pushing entire datasets onto the heap.
- Never call `.block()` or manually call `.subscribe()` in typical WebFlux services or controllers.
- Retries require conditions, backoff, and idempotent operations; a reactive chain is not a transaction.
- Use StepVerifier to test signals and integration tests to verify Elasticsearch behavior.

Non-blocking save, search, and delete chains are built by expressing each step as a `Mono` or `Flux` and linking them according to their dependencies. By preserving publishers across services and controllers, controlling backpressure, handling empty and error cases explicitly, and understanding Search API refresh semantics, Spring Data Elasticsearch applications can execute reactive workflows that are readable, non-blocking, and operationally reliable.

## References

- [Spring Data Elasticsearch — Reactive Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/reactive-template.html)
- [Spring Data Elasticsearch — Reactive repositories](https://docs.spring.io/spring-data/elasticsearch/reference/repositories/reactive-repositories.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [Project Reactor — Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
- [Project Reactor — Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html)
- [Elasticsearch — Near real-time search](https://www.elastic.co/guide/en/elasticsearch/reference/current/near-real-time.html)
