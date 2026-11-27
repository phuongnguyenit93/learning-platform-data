# Testing Reactive Code with StepVerifier

Spring Data Elasticsearch Reactive returns `Mono` and `Flux` instead of synchronous results. These publishers describe an asynchronous processing flow; they normally execute only when subscribed to. Therefore, unit tests should not call `.block()` or manually `.subscribe()` just to obtain results. Project Reactor provides `StepVerifier` in the `reactor-test` module to subscribe to publishers, control demand, and verify emitted signals step by step.

`StepVerifier` helps test both outcomes and pipeline behavior: emitted elements, ordering, completion, errors, backpressure, cancellation, retries, and time. With Spring Data Elasticsearch, you can use it to unit test reactive services/repositories with mocks, then supplement with integration tests against real Elasticsearch to verify mappings, queries, persistence, and search visibility.

## 1. Why Is StepVerifier Needed?

In reactive programming, a method returning `Mono<T>` or `Flux<T>` does not necessarily perform work when invoked. It returns a publisher description. When a test calls the method without subscribing, the pipeline may never run and assertions verify nothing.

Example:

```java
Mono<ProductDocument> result = productService.findById("p-100");
```

The snippet above only constructs the publisher. `StepVerifier` subscribes to the publisher, requests items, and verifies signals:

```java
StepVerifier.create(result)
    .expectNextMatches(product -> product.getId().equals("p-100"))
    .verifyComplete();
```

`verifyComplete()` triggers verification and waits for the publisher to emit completion. If the publisher fails to emit expected signals or hangs, the test fails upon the verifier's timeout.

### StepVerifier Verifies Reactive Streams Signals

A publisher can emit signals:

- `onSubscribe`: subscriber receives a subscription.
- `onNext`: publisher emits an item.
- `onError`: publisher terminates with an error.
- `onComplete`: publisher completes normally.

`StepVerifier` describes expectations in sequence. If the publisher emits out of order, emits extra items, errors instead of completing, or fails to terminate, the test reports a failure.

## 2. Adding the `reactor-test` Dependency

`StepVerifier`, `TestPublisher`, and `PublisherProbe` live in the `reactor-test` artifact. With Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-elasticsearch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
```

With Maven:

```xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>
```

If the project uses Spring Boot dependency management, let the BOM manage compatible Reactor versions instead of picking a version different from the running Reactor Core. Without a BOM, ensure `reactor-test` and `reactor-core` have compatible versions.

Common imports:

```java
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.test.TestPublisher;
import reactor.test.publisher.PublisherProbe;
```

## 3. Testing Basic `Mono`

`Mono<T>` emits at most one item and completes, or emits an error. You can use `expectNext`, `assertNext`, `expectNextMatches`, and `verifyComplete`.

```java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class MonoStepVerifierTest {

    @Test
    void emitsOneValueAndCompletes() {
        Mono<String> source = Mono.just("wireless mouse");

        StepVerifier.create(source)
            .expectNext("wireless mouse")
            .verifyComplete();
    }

    @Test
    void emitsNoValueAndCompletes() {
        Mono<String> source = Mono.empty();

        StepVerifier.create(source)
            .verifyComplete();
    }

    @Test
    void assertsTheEmittedObject() {
        ProductDocument product = new ProductDocument("p-100", "Mouse");

        StepVerifier.create(Mono.just(product))
            .assertNext(actual -> {
                assertThat(actual.getId()).isEqualTo("p-100");
                assertThat(actual.getName()).isEqualTo("Mouse");
            })
            .verifyComplete();
    }
}
```

`expectNext(value)` compares values via `equals`. `assertNext(consumer)` suits multiple assertions on a single item. `expectNextMatches(predicate)` fits a concise boolean check.

### Verifying `Mono<Void>`

Operations like delete or updates returning no content often return `Mono<Void>`. The publisher completes without emitting `onNext`:

```java
StepVerifier.create(productService.delete("p-100"))
    .verifyComplete();
```

Never write `expectNext(null)`: Reactive Streams forbids emitting `null`.

## 4. Testing `Flux` and Element Ordering

`Flux<T>` can emit zero to many items. `expectNext` checks values in exact order:

```java
@Test
void emitsProductsInExpectedOrder() {
    Flux<String> names = Flux.just("Mouse", "Keyboard", "Monitor");

    StepVerifier.create(names)
        .expectNext("Mouse")
        .expectNext("Keyboard")
        .expectNext("Monitor")
        .verifyComplete();
}
```

Multiple values can be grouped in a single call:

```java
StepVerifier.create(names)
    .expectNext("Mouse", "Keyboard", "Monitor")
    .verifyComplete();
```

If only the count matters:

```java
StepVerifier.create(Flux.range(1, 100))
    .expectNextCount(100)
    .verifyComplete();
```

`expectNextCount(n)` verifies exactly `n` next items in the expected stream; it does not inspect item contents. When contents matter, use `assertNext` or `expectNextMatches`.

### Checking Final Items or Recorded Collections

You can record emitted items into a collection:

```java
StepVerifier.create(Flux.just("A", "B", "C"))
    .recordWith(ArrayList::new)
    .expectNextCount(3)
    .consumeRecordedWith(values ->
        assertThat(values).containsExactly("A", "B", "C")
    )
    .verifyComplete();
```

Do not collect huge streams solely for testing. Use small fixtures, or assert counts and key invariants.

## 5. `verifyComplete`, `verify`, and Timeouts

Terminal verification methods initiate subscription and wait for signals:

| Method | Expectation |
|---|---|
| `verifyComplete()` | Publisher terminates with `onComplete` |
| `verifyError()` | Publisher terminates with an error |
| `verifyError(Class)` | Error matches expected type |
| `verifyErrorMessage(String)` | Error matches expected message |
| `verify()` | Terminates according to the described scenario without forcing a specific terminal signal |
| `verify(Duration)` | Runs verification with an explicit timeout |

In tests with publishers that might never terminate, always specify a timeout to keep CI from hanging:

```java
StepVerifier.create(productService.search("mouse"))
    .expectNextCount(2)
    .thenCancel()
    .verify(Duration.ofSeconds(3));
```

You can configure a default `StepVerifier` timeout for a test suite, though explicit timeouts on potentially long-running tests make intent clearer.

## 6. Checking Errors

A publisher may terminate with an error. Use `expectError` to verify the error type:

```java
@Test
void propagatesSearchFailure() {
    RuntimeException failure = new RuntimeException("Elasticsearch unavailable");

    StepVerifier.create(Mono.error(failure))
        .expectError(RuntimeException.class)
        .verify();
}
```

Checking the message:

```java
StepVerifier.create(Mono.error(new IllegalStateException("invalid state")))
    .verifyErrorMessage("invalid state");
```

Or inspecting more deeply:

```java
StepVerifier.create(service.findById("missing"))
    .expectErrorSatisfies(error -> {
        assertThat(error)
            .isInstanceOf(ProductNotFoundException.class)
            .hasMessageContaining("missing");
    })
    .verify();
```

### Testing Fallbacks

When a service turns an error into a default value via `onErrorResume`, verify the final result instead of expecting an error:

```java
Mono<String> result = remoteCall()
    .onErrorResume(error -> Mono.just("fallback"));

StepVerifier.create(result)
    .expectNext("fallback")
    .verifyComplete();
```

Tests should verify which specific error types trigger the fallback. Never swallow all exceptions if mapping, validation, or programming errors should propagate.

## 7. Testing `switchIfEmpty` and Not-Found Behavior

Repositories looking up by ID typically return `Mono.empty()` when no document exists. Services often convert empty into a domain exception:

```java
public Mono<ProductDocument> getRequired(String id) {
    return repository.findById(id)
        .switchIfEmpty(Mono.error(
            new ProductNotFoundException(id)
        ));
}
```

Test both branches:

```java
@Test
void returnsProductWhenFound() {
    ProductDocument product = new ProductDocument("p-100", "Mouse");
    when(repository.findById("p-100")).thenReturn(Mono.just(product));

    StepVerifier.create(service.getRequired("p-100"))
        .expectNext(product)
        .verifyComplete();
}

@Test
void returnsNotFoundWhenEmpty() {
    when(repository.findById("missing")).thenReturn(Mono.empty());

    StepVerifier.create(service.getRequired("missing"))
        .expectError(ProductNotFoundException.class)
        .verify();
}
```

`switchIfEmpty` runs only when upstream completes without emitting an item. It does not handle errors; errors require `onErrorResume` or another error operator.

## 8. Testing Backpressure and Demand

One benefit of `StepVerifier` is controlling how many items the subscriber requests. You can create a verifier with `initialRequest(0)` so zero items are requested initially:

```java
@Test
void emitsOnlyWhenDemandIsRequested() {
    Flux<Integer> source = Flux.range(1, 3);

    StepVerifier.create(source, 0)
        .expectSubscription()
        .thenRequest(1)
        .expectNext(1)
        .thenRequest(2)
        .expectNext(2, 3)
        .verifyComplete();
}
```

`thenRequest(n)` requests `n` more items. This test checks that the publisher honors demand step by step.

### Verifying No Extra Items Emit Before Requesting

```java
StepVerifier.create(Flux.range(1, 3), 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNext(1)
    .then(() -> assertThat(true).isTrue())
    .thenRequest(1)
    .expectNext(2)
    .thenRequest(1)
    .expectNext(3)
    .verifyComplete();
```

Do not put dummy assertions like `assertThat(true)` in real tests; the example merely illustrates where synchronous side-effect checks or assertions can run between steps. To prove upstream never over-emits beyond demand, use `TestPublisher` or inspect the publisher's subscription/demand accordingly.

## 9. `thenRequest` and `expectNoEvent`

`thenRequest(n)` controls demand at specific points in the scenario. `expectNoEvent(duration)` verifies no signals occur during that time window.

Example publisher emitting after a delay:

```java
StepVerifier.withVirtualTime(() -> Mono.delay(Duration.ofSeconds(5)))
    .expectSubscription()
    .expectNoEvent(Duration.ofSeconds(4))
    .thenAwait(Duration.ofSeconds(1))
    .expectNext(0L)
    .verifyComplete();
```

`expectNoEvent` treats subscription itself as an event. Therefore, call `expectSubscription()` beforehand to avoid failing immediately on subscription.

## 10. Testing Cancellation

Cancellation occurs when a subscriber no longer wants data—for example, a client closes a connection or a user cancels an export stream.

```java
@Test
void cancelsAfterReceivingTwoItems() {
    StepVerifier.create(Flux.range(1, 10))
        .expectNext(1, 2)
        .thenCancel()
        .verify();
}
```

This test confirms the scenario ends with cancellation. If a service performs cleanup on cancel, verify cleanup runs using `PublisherProbe`, mocks, or an observable side effect.

### Cancellation Does Not Mean Rollback

Cancelling a publisher does not undo operations already completed beforehand. If a pipeline already wrote documents to Elasticsearch before being cancelled, those documents remain. For bulk or export jobs, design explicit checkpoints, idempotency, and cleanup.

## 11. Testing `doFinally` and Cleanup

`doFinally` receives termination signals `ON_COMPLETE`, `ON_ERROR`, or `CANCEL`. Use it to release lightweight metrics/resources or observe lifecycle:

```java
AtomicReference<SignalType> termination = new AtomicReference<>();

Flux<Integer> source = Flux.range(1, 10)
    .doFinally(termination::set);

StepVerifier.create(source)
    .expectNext(1, 2, 3)
    .thenCancel()
    .verify();

assertThat(termination.get()).isEqualTo(SignalType.CANCEL);
```

For asynchronous cleanup, use `usingWhen` and verify the cleanup publisher is subscribed to and completes. Do not check only a boolean flag if real resources require closing through an async API.

## 12. Virtual Time for Delayed Publishers

Tests using `Thread.sleep()` are slow and flaky. `StepVerifier.withVirtualTime` lets you advance virtual time to test `delay`, `timeout`, `interval`, retry backoff, and operators relying on supported schedulers.

Example:

```java
@Test
void emitsAfterFiveVirtualSeconds() {
    StepVerifier.withVirtualTime(
            () -> Mono.delay(Duration.ofSeconds(5))
        )
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(5))
        .expectNext(0L)
        .verifyComplete();
}
```

The test does not wait five real seconds. The verifier advances the virtual clock to the requested point.

### Create the Publisher Inside the Supplier

Create the publisher inside the lambda passed to `withVirtualTime`:

```java
StepVerifier.withVirtualTime(() -> service.delayedResult())
    .thenAwait(Duration.ofSeconds(10))
    .expectNext("ready")
    .verifyComplete();
```

Do not instantiate a publisher with schedulers/timers before calling `withVirtualTime`, because a real scheduler may already be bound before the virtual scheduler is installed.

### Custom Schedulers

If a service accepts an injected scheduler, tests should inject `VirtualTimeScheduler` or a suitable test scheduler rather than hardcoding `Schedulers.parallel()` inside the service. When a publisher uses a scheduler not replaced by virtual time, `thenAwait` cannot control that publisher's clock.

## 13. Testing Timeouts

`timeout` turns a publisher into an error if no signal arrives within the configured window:

```java
Mono<String> result = Mono.<String>never()
    .timeout(Duration.ofSeconds(3));

StepVerifier.withVirtualTime(() -> result)
    .thenAwait(Duration.ofSeconds(3))
    .expectError(TimeoutException.class)
    .verify();
```

In real tests, create both `Mono.never()` and the `timeout` operator inside the supplier so the virtual scheduler is used properly:

```java
StepVerifier.withVirtualTime(() ->
        Mono.<String>never().timeout(Duration.ofSeconds(3))
    )
    .thenAwait(Duration.ofSeconds(3))
    .expectError(TimeoutException.class)
    .verify();
```

Distinguish Reactor operator timeouts from Elasticsearch HTTP client or server timeouts. Virtual time controls only the scheduler used by Reactor; it does not speed up real Elasticsearch or replace network timeout integration tests.

## 14. Testing Retries and Backoff

Example service retrying on transient failures:

```java
Mono<String> call = Mono.defer(() -> remoteCall())
    .retryWhen(Retry.backoff(2, Duration.ofSeconds(1)));
```

You can test retries with virtual time:

```java
AtomicInteger attempts = new AtomicInteger();

Mono<String> retried = Mono.defer(() -> {
    int attempt = attempts.incrementAndGet();
    if (attempt < 3) {
        return Mono.error(new IOException("temporary"));
    }
    return Mono.just("ok");
}).retryWhen(Retry.backoff(2, Duration.ofSeconds(1))
    .jitter(0));

StepVerifier.withVirtualTime(() -> retried)
    .thenAwait(Duration.ofSeconds(3))
    .expectNext("ok")
    .verifyComplete();

assertThat(attempts.get()).isEqualTo(3);
```

To guarantee virtual time applies reliably, move the entire publisher and retry creation inside the supplier:

```java
AtomicInteger attempts = new AtomicInteger();

StepVerifier.withVirtualTime(() -> Mono.defer(() -> {
        int attempt = attempts.incrementAndGet();
        return attempt < 3
            ? Mono.error(new IOException("temporary"))
            : Mono.just("ok");
    }).retryWhen(Retry.backoff(2, Duration.ofSeconds(1)).jitter(0)))
    .thenAwait(Duration.ofSeconds(3))
    .expectNext("ok")
    .verifyComplete();

assertThat(attempts.get()).isEqualTo(3);
```

In production, never retry every Elasticsearch error. Mapping/validation errors should normally not retry; transient errors can use bounded retries; version conflicts need re-reading and recomputing per business logic. Tests should confirm which error types trigger retries and the maximum retry count.

## 15. `TestPublisher` to Control Emission Sources

`TestPublisher` is a test-purpose publisher. It lets tests programmatically emit items, completion, or errors to a subscriber.

```java
@Test
void processesItemsAsTheyArrive() {
    TestPublisher<String> source = TestPublisher.create();

    Flux<String> result = source.flux()
        .map(String::toUpperCase);

    StepVerifier.create(result)
        .then(() -> source.next("mouse"))
        .expectNext("MOUSE")
        .then(() -> source.next("keyboard"))
        .expectNext("KEYBOARD")
        .then(source::complete)
        .verifyComplete();
}
```

`TestPublisher` is helpful when controlling exactly when upstream emits, testing how pipelines react to incremental items, or simulating a custom application publisher.

### Emitting Errors Deterministically

```java
TestPublisher<ProductDocument> source = TestPublisher.create();
RuntimeException failure = new RuntimeException("source failed");

StepVerifier.create(source.flux())
    .then(() -> source.error(failure))
    .expectErrorMatches(error -> error == failure)
    .verify();
```

Do not use `TestPublisher` to simulate full Elasticsearch server behavior. It controls publishers at the reactive layer; mappings, query DSL, routing, and persistence require integration tests.

## 16. Checking Demand with `TestPublisher`

You can verify how the subscriber requested data:

```java
TestPublisher<Integer> source = TestPublisher.create();

StepVerifier.create(source.flux(), 0)
    .expectSubscription()
    .thenRequest(1)
    .then(() -> source.next(1))
    .expectNext(1)
    .thenCancel()
    .verify();

source.assertWasRequested();
```

`TestPublisher` provides assertions such as `assertWasSubscribed`, `assertWasRequested`, `assertWasNotRequested`, and `assertCancelled` depending on API/version. Use them to confirm the pipeline subscribed, requested, and cancelled as expected.

Do not intentionally over-emit past demand with a compliant publisher in ordinary tests. To test how a pipeline handles a Reactive Streams spec violation, `TestPublisher` offers non-compliant modes; use them only for explicit requirements simulating non-compliant sources.

## 17. `PublisherProbe` to Verify Publisher Branches

`PublisherProbe` wraps a publisher to observe whether it was subscribed to, requested, or cancelled. It is handy when testing `switchIfEmpty`, `onErrorResume`, `then`, or fallback branches.

Example:

```java
@Test
void usesFallbackWhenPrimaryIsEmpty() {
    PublisherProbe<String> fallback =
        PublisherProbe.of(Mono.just("fallback"));

    Mono<String> result = Mono.<String>empty()
        .switchIfEmpty(fallback.mono());

    StepVerifier.create(result)
        .expectNext("fallback")
        .verifyComplete();

    fallback.assertWasSubscribed();
    fallback.assertWasRequested();
}
```

When the primary publisher emits data, the fallback is not subscribed to:

```java
PublisherProbe<String> fallback =
    PublisherProbe.of(Mono.just("fallback"));

StepVerifier.create(Mono.just("primary").switchIfEmpty(fallback.mono()))
    .expectNext("primary")
    .verifyComplete();

fallback.assertWasNotSubscribed();
```

Probes verify publisher branch selection; they do not replace assertions on business values.

## 18. Testing Reactor Context

Reactor Context propagates subscription-scoped data, often used for correlation IDs or reactive metadata. Unlike `ThreadLocal`, it does not depend on the pipeline staying on the same thread.

You can supply context in tests:

```java
StepVerifier.create(
        Mono.deferContextual(context ->
            Mono.just(context.get("tenantId"))
        ),
        StepVerifierOptions.create()
            .withInitialContext(Context.of("tenantId", "tenant-42"))
    )
    .expectAccessibleContext()
    .contains("tenantId", "tenant-42")
    .then()
    .expectNext("tenant-42")
    .verifyComplete();
```

`expectAccessibleContext()` checks context presence at subscription. `StepVerifierOptions` can configure scenario names or initial context.

### Context and Spring Security

In reactive applications using Spring Security, security context typically travels via Reactor Context. Do not assume `ThreadLocal`-backed `SecurityContextHolder` holds the right authentication inside reactive callbacks. When a service depends on principal/tenant, test both present-context and missing-context cases by configuring context explicitly or using WebFlux security test utilities.

## 19. Testing `Mono.zip` and Combining Multiple Sources

A service may combine multiple publishers—for instance, fetching a product and stock count:

```java
public Mono<ProductView> getView(String id) {
    return Mono.zip(
        productRepository.findById(id),
        inventoryClient.getStock(id)
    ).map(tuple -> new ProductView(
        tuple.getT1().getId(),
        tuple.getT1().getName(),
        tuple.getT2()
    ));
}
```

Test with `StepVerifier`:

```java
@Test
void combinesProductAndInventory() {
    ProductDocument product = new ProductDocument("p-100", "Mouse");
    when(productRepository.findById("p-100"))
        .thenReturn(Mono.just(product));
    when(inventoryClient.getStock("p-100"))
        .thenReturn(Mono.just(12));

    StepVerifier.create(service.getView("p-100"))
        .assertNext(view -> {
            assertThat(view.id()).isEqualTo("p-100");
            assertThat(view.name()).isEqualTo("Mouse");
            assertThat(view.stock()).isEqualTo(12);
        })
        .verifyComplete();
}
```

`Mono.zip` generally requires every source to emit one value. If any source completes empty, zip completes empty; if any source errors, zip emits an error. Write tests for those branches if the service defines fallback or not-found logic.

## 20. Testing Spring Data Elasticsearch Services with Mocks

Unit tests should focus on service logic and reactive contracts without launching Elasticsearch for every case.

Example service using a reactive repository:

```java
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Flux<ProductDocument> findByCategory(String category) {
        return repository.findByCategory(category)
            .filter(product -> product.getStatus() == ProductStatus.ACTIVE);
    }

    public Mono<ProductDocument> create(ProductDocument product) {
        return repository.save(product);
    }
}
```

Repository:

```java
public interface ProductRepository
        extends ReactiveElasticsearchRepository<ProductDocument, String> {

    Flux<ProductDocument> findByCategory(String category);
}
```

Unit test with Mockito:

```java
@ExtendWith(MockitoExtension.class)
class ProductServiceTest {

    @Mock
    ProductRepository repository;

    ProductService service;

    @BeforeEach
    void setUp() {
        service = new ProductService(repository);
    }

    @Test
    void returnsOnlyActiveProducts() {
        ProductDocument active = product("p-1", ProductStatus.ACTIVE);
        ProductDocument inactive = product("p-2", ProductStatus.INACTIVE);

        when(repository.findByCategory("accessories"))
            .thenReturn(Flux.just(active, inactive));

        StepVerifier.create(service.findByCategory("accessories"))
            .expectNext(active)
            .verifyComplete();

        verify(repository).findByCategory("accessories");
    }
}
```

Mocking the repository returns publishers for the service to transform. `StepVerifier` subscribes and verifies emitted contents. Mockito `verify` confirms the dependency was invoked with the expected arguments.

### Do Not Mock What the Test Intends to Verify

If the test aims to verify that a derived query method produces a query matching the Elasticsearch mapping, mocking the repository skips that verification. Unit tests only verify the service calls the repository and processes results; derived queries, mappings, and server behavior belong in integration tests.

## 21. Testing `ReactiveElasticsearchOperations`

For custom queries, a service may depend on `ReactiveElasticsearchOperations`:

```java
public class ProductSearchService {

    private final ReactiveElasticsearchOperations operations;

    public ProductSearchService(ReactiveElasticsearchOperations operations) {
        this.operations = operations;
    }

    public Flux<ProductDocument> search(Query query) {
        return operations.search(query, ProductDocument.class)
            .map(SearchHit::getContent);
    }
}
```

You can mock `search` to return a `Flux<SearchHit<ProductDocument>>` built in the test, then use `StepVerifier` to confirm the service maps `SearchHit` to entities properly. However, constructing `SearchHit` may require builders/constructors varying across Spring Data versions. Keep tests at the service level when verifying output mapping; use integration tests when verifying actual queries.

### Verifying Constructed Queries

If the service builds `NativeQuery` itself, extract the query builder into a separate component and unit test input parameters/fields/filters. For complex Query DSL, integration testing against real Elasticsearch is stronger evidence than comparing internal builder objects alone.

## 22. Testing Reactive Save and Delete

Example verifying `save` emits the saved entity:

```java
@Test
void createsProduct() {
    ProductDocument input = new ProductDocument("p-100", "Mouse");
    when(repository.save(input)).thenReturn(Mono.just(input));

    StepVerifier.create(service.create(input))
        .expectNext(input)
        .verifyComplete();

    verify(repository).save(input);
}
```

For delete returning `Mono<Void>`:

```java
@Test
void deletesProduct() {
    when(repository.deleteById("p-100")).thenReturn(Mono.empty());

    StepVerifier.create(service.delete("p-100"))
        .verifyComplete();
}
```

Exact return types of some repository methods depend on the interface/version. Use the real signature from your dependencies; do not force every delete method into `Mono<Boolean>` if the real API returns `Mono<Void>`.

## 23. Testing Lazy Execution and Side Effects

A pipeline with side effects should use `defer` if the side effect must occur at subscription time:

```java
AtomicInteger calls = new AtomicInteger();

Mono<Integer> result = Mono.defer(() ->
    Mono.just(calls.incrementAndGet())
);
```

You can verify the publisher has not executed before subscription and each subscription triggers one execution:

```java
assertThat(calls.get()).isZero();

StepVerifier.create(result)
    .expectNext(1)
    .verifyComplete();

assertThat(calls.get()).isEqualTo(1);

StepVerifier.create(result)
    .expectNext(2)
    .verifyComplete();

assertThat(calls.get()).isEqualTo(2);
```

Not all publishers are cold. Some share subscriptions or emit hot signals. Tests should understand the semantics of the data source rather than assuming every `Flux` re-executes from scratch per subscription.

## 24. Testing Retries Without Repeating Wrong Side Effects

If a publisher writes a document and retries on error responses, consider whether the prior write might have succeeded on the server before the response was lost. Retrying can send the same operation again.

Tests to consider:

- Stable document ID so upserts are idempotent.
- No duplicates created on retry.
- Only selected transient errors trigger retries.
- Retry count is bounded.
- Backoff with jitter in production; virtual time in tests.
- Never retry version conflicts with the same stale token.
- Final error propagates to the caller once retries exhaust.

`StepVerifier` checks signals and attempt counts; mocks/spies can count invocations. Integration tests verify final document state after retries.

## 25. Testing Timeouts and Errors from the Elasticsearch Client

Unit tests can simulate timeouts with `Mono.error(new TimeoutException(...))` or `never().timeout(...)`. However, they do not prove timeout configuration on the reactive Elasticsearch client works.

Integration tests should verify:

- Connection timeouts.
- Response timeouts.
- Elasticsearch returning 4xx/5xx errors.
- Cluster rejecting requests under overload.
- Publishers propagating errors to services/controllers.
- Cancellation handling when the HTTP client closes connections.

Never build tests waiting on a stalled real Elasticsearch server via `Thread.sleep`. Use a test server/proxy or controlled timeout configuration when verifying the network layer.

## 26. Integration Tests with Real Elasticsearch

Mocks cannot verify mappings, analyzers, derived queries, serialization, or server behavior. Keep a focused set of integration tests running against compatible Elasticsearch, usually via Testcontainers or an isolated test environment.

Test structure:

```text
JUnit test
   |
   v
Spring application context
   |
   v
ReactiveElasticsearchOperations / Repository
   |
   v
Elasticsearch test container
   |
   v
StepVerifier verifies Mono/Flux
```

Skeleton test example:

```java
@SpringBootTest
class ProductRepositoryIntegrationTest {

    @Autowired
    ProductRepository repository;

    @Autowired
    ReactiveElasticsearchOperations operations;

    @Test
    void savesAndFindsProduct() {
        ProductDocument product = new ProductDocument("p-100", "Mouse");

        StepVerifier.create(repository.save(product))
            .assertNext(saved -> assertThat(saved.getId()).isEqualTo("p-100"))
            .verifyComplete();

        StepVerifier.create(repository.findById("p-100"))
            .assertNext(found -> assertThat(found.getName()).isEqualTo("Mouse"))
            .verifyComplete();
    }
}
```

This is an illustrative skeleton. Tests need appropriate Elasticsearch endpoint/container and index mapping configuration. GET by ID has real-time semantics by default, while search tests must handle refresh visibility.

### Cleaning Up Data Between Tests

Each test should use unique IDs or clear test data before/after running. If tests run in parallel, avoid sharing index/document IDs in ways that cause races. You can create a dedicated index per test suite or use prefixes/namespaces.

## 27. Search Visibility and Refresh in Integration Tests

After saving a document, GET by ID can read it immediately; search queries may not see it until refresh. When a test verifies search, synchronize explicitly:

- Use the `WAIT_UNTIL` refresh policy for writes if supported by the test API.
- Or refresh the index via the appropriate `IndexOperations` API.
- Then run the search via `StepVerifier`.

Conceptual example with refresh:

```java
StepVerifier.create(repository.save(product))
    .expectNextCount(1)
    .verifyComplete();

// Refresh the test index using the index operations API for the
// Spring Data Elasticsearch version configured by the project.

StepVerifier.create(repository.findByName("Mouse"))
    .expectNextMatches(found -> found.getId().equals("p-100"))
    .verifyComplete();
```

Never use `Thread.sleep(1000)` to wait for refresh. Tests relying on the refresh API or refresh policy are deterministic and less sensitive to CI speed.

## 28. Testing Repository Derived Queries

Reactive repositories can declare query methods:

```java
public interface ProductRepository
        extends ReactiveElasticsearchRepository<ProductDocument, String> {

    Flux<ProductDocument> findByStatus(ProductStatus status);

    Flux<ProductDocument> findByCategoryAndStatus(
        String category,
        ProductStatus status
    );
}
```

Unit tests with mocks only verify the service calls the method. Integration tests must index fixtures and call the real method to confirm Spring Data generates the right query, fields are mapped properly, and results match.

When a method returns `Flux`, `StepVerifier` can verify counts, ordering under an explicit sort, and filter conditions. If order is not guaranteed by the query, never assert a fixed order; check sets or add an explicit sort.

## 29. Testing Service Backpressure

When a service returns a large `Flux` or uses concurrency operators, you can test partial demand:

```java
StepVerifier.create(service.streamProducts(), 0)
    .expectSubscription()
    .thenRequest(5)
    .expectNextCount(5)
    .thenCancel()
    .verify(Duration.ofSeconds(3));
```

This test confirms the subscriber requests only five items before cancelling. It does not by itself prove Elasticsearch fetched only five documents; search page sizes, scroll/PIT, and prefetching at lower layers can cause the server/client to fetch more.

If the goal is bounding Elasticsearch requests, inspect query/page sizes and request counts via client mocks, metrics, or integration instrumentation.

## 30. Testing `flatMap` Concurrency

You can use active operation counters to verify concurrency bounds of a pipeline:

```java
AtomicInteger active = new AtomicInteger();
AtomicInteger maximum = new AtomicInteger();

Function<Integer, Mono<Integer>> operation = value ->
    Mono.defer(() -> {
        int current = active.incrementAndGet();
        maximum.accumulateAndGet(current, Math::max);

        return Mono.delay(Duration.ofMillis(10))
            .map(ignored -> value)
            .doFinally(signal -> active.decrementAndGet());
    });

Flux<Integer> result = Flux.range(1, 20)
    .flatMap(operation, 4);

StepVerifier.create(result)
    .expectNextCount(20)
    .verifyComplete();

assertThat(maximum.get()).isLessThanOrEqualTo(4);
```

Real delays can tie tests to thread scheduling. You can use virtual time with publishers constructed inside the supplier, or use latches/`TestPublisher` to control completion. The goal is measuring active inner publishers, not merely thread counts.

## 31. Testing `Context` and Correlation Metadata

If a service extracts tenant/correlation IDs from Reactor Context, tests must verify context flows to the expected operators:

```java
Mono<String> result = Mono.deferContextual(context ->
    Mono.just(context.get("correlationId"))
);

StepVerifier.create(
        result,
        StepVerifierOptions.create()
            .withInitialContext(Context.of("correlationId", "req-123"))
    )
    .expectNext("req-123")
    .verifyComplete();
```

When a service composes multiple publishers or switches schedulers, test context propagation across key operators. Avoid relying on `ThreadLocal` in reactive code unless framework context propagation is explicitly configured.

## 32. Naming Scenarios for Readable Failures

`StepVerifierOptions` lets you set a scenario name so failures are easier to identify:

```java
StepVerifier.create(
        service.findByCategory("accessories"),
        StepVerifierOptions.create()
            .scenarioName("active products are emitted")
    )
    .expectNextMatches(product -> product.getStatus() == ProductStatus.ACTIVE)
    .verifyComplete();
```

You can also place `as("description")` after an expectation to label a specific step in failure reports:

```java
StepVerifier.create(service.findById("p-100"))
    .expectNextMatches(product -> product.getId().equals("p-100"))
    .as("returns the requested product")
    .verifyComplete();
```

Naming scenarios after business behavior speeds up reading CI failures, especially when a single test has multiple expectations.

## 33. Avoiding Anti-Patterns in Reactive Testing

### Calling `.block()` to Grab Results

```java
ProductDocument product = service.findById("p-100").block();
```

This turns the test into a synchronous call, hides subscription semantics, and can block threads. Use `StepVerifier` to verify publishers directly.

### Manually Calling `.subscribe()` and Asserting Immediately

```java
AtomicReference<ProductDocument> result = new AtomicReference<>();
service.findById("p-100").subscribe(result::set);
assertThat(result.get()).isNotNull();
```

This creates a race condition because the callback may not have run when the assertion executes. `StepVerifier` manages subscription and waits for terminal signals.

### Using `Thread.sleep()` to Wait for Publishers

Sleeping makes tests slow and non-deterministic. Use virtual time for time-based operators, or let `StepVerifier` wait on real signals.

### Omitting Timeouts

A `never()` publisher or a bug that fails to complete can hang tests. Set appropriate timeouts on verifications.

### Cramming Too Much Logic Into One Verifier

Each test should describe one primary behavior. Separate success, empty, error, retry, and cancellation into distinct tests so failures are easy to diagnose.

### Mocking Elasticsearch in Integration Tests

When the goal is verifying mappings or queries, mocking the repository skips the exact thing under test. Use real Elasticsearch for a small, focused integration suite.

### Assuming Flux Ordering Without Sorting

Without an explicit sort in the query, Elasticsearch does not guarantee stable ordering. Do not use `expectNext` with an arbitrary order; add sorting or compare value sets.

## 34. Organizing the Test Suite by Layer

A balanced test suite typically has three layers:

| Test type | Tools | Scope |
|---|---|---|
| Service unit test | Mockito + `StepVerifier` | Mapping, filtering, fallbacks, errors, retries, composition |
| Reactive operator test | `StepVerifier` + `TestPublisher` + `PublisherProbe` | Demand, cancellation, virtual time, branch subscriptions |
| Integration test | JUnit + Spring context + Elasticsearch test instance + `StepVerifier` | Mappings, repository queries, save/delete/search, refresh, and server behavior |

Unit tests should run fast with no containers. Integration tests can run less frequently while verifying real behavior. There is no need to start Elasticsearch just to test a simple `map` or `switchIfEmpty`.

## 35. Complete Service and Test Example

Service:

```java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Mono<ProductDocument> getRequired(String id) {
        return repository.findById(id)
            .switchIfEmpty(Mono.error(new ProductNotFoundException(id)));
    }

    public Flux<ProductDocument> activeProducts(String category) {
        return repository.findByCategory(category)
            .filter(product -> product.getStatus() == ProductStatus.ACTIVE);
    }

    public Mono<ProductDocument> create(ProductDocument product) {
        return repository.save(product);
    }
}
```

Test:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ProductServiceTest {

    @Mock
    ProductRepository repository;

    ProductService service;

    @BeforeEach
    void setUp() {
        service = new ProductService(repository);
    }

    @Test
    void getRequiredEmitsProduct() {
        ProductDocument product = product("p-100", ProductStatus.ACTIVE);
        when(repository.findById("p-100")).thenReturn(Mono.just(product));

        StepVerifier.create(service.getRequired("p-100"))
            .assertNext(actual -> {
                assertThat(actual.getId()).isEqualTo("p-100");
                assertThat(actual.getStatus()).isEqualTo(ProductStatus.ACTIVE);
            })
            .verifyComplete();

        verify(repository).findById("p-100");
    }

    @Test
    void getRequiredEmitsNotFoundWhenRepositoryIsEmpty() {
        when(repository.findById("missing")).thenReturn(Mono.empty());

        StepVerifier.create(service.getRequired("missing"))
            .expectError(ProductNotFoundException.class)
            .verify();
    }

    @Test
    void activeProductsFiltersInactiveDocuments() {
        ProductDocument active = product("p-1", ProductStatus.ACTIVE);
        ProductDocument inactive = product("p-2", ProductStatus.INACTIVE);
        when(repository.findByCategory("accessories"))
            .thenReturn(Flux.just(active, inactive));

        StepVerifier.create(service.activeProducts("accessories"))
            .expectNext(active)
            .verifyComplete();
    }

    private ProductDocument product(String id, ProductStatus status) {
        ProductDocument product = new ProductDocument();
        product.setId(id);
        product.setStatus(status);
        return product;
    }
}
```

This snippet is an illustrative sample; constructors, getters/setters, and repository methods must match your project's real model. The tests focus on reactive behavior: the service emits expected values, turns empty into not-found, and filters out inactive documents.

## 36. Workflow for Writing a StepVerifier Test

When writing a test for a publisher:

1. Create small fixtures and identify the publisher under test.
2. Prepare dependencies with mocks or test publishers if needed.
3. Use `StepVerifier.create(...)` or `withVirtualTime(...)`.
4. Specify subscription/demand if backpressure behavior matters.
5. Verify values, ordering, or predicates with appropriate expectations.
6. Verify the terminal signal: complete, error, or cancel.
7. Call `verify...` to execute the scenario.
8. Set timeouts on tests that may wait.
9. Assert side effects/dependency invocations after verification.
10. Use integration tests when Elasticsearch server behavior needs verification.

## 37. Conclusion

`StepVerifier` is the primary tool for testing `Mono` and `Flux` because it subscribes to publishers, controls demand, and verifies Reactive Streams signal sequences. Use `expectNext`, `assertNext`, `expectError`, `verifyComplete`, `thenRequest`, and `thenCancel` to verify data, errors, backpressure, and cancellation. `withVirtualTime` tests delays, timeouts, and retry backoff without waiting in real time.

`TestPublisher` lets you programmatically drive emission sources; `PublisherProbe` verifies whether a publisher branch was subscribed to. In Spring Data Elasticsearch, pair Mockito + `StepVerifier` for service logic with integration tests against real Elasticsearch to verify repository queries, mappings, persistence, and refresh visibility. Avoid `.block()`, manual `.subscribe()` with immediate assertions, or `Thread.sleep()`; always configure timeouts and verify exact semantics for empty results, errors, ordering, retries, and cancellation.

## References

- [Project Reactor – Testing](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Project Reactor – StepVerifier API](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html)
- [Project Reactor – TestPublisher API](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/TestPublisher.html)
- [Project Reactor – PublisherProbe API](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/PublisherProbe.html)
- [Project Reactor – Virtual Time](https://projectreactor.io/docs/core/release/reference/testing.html#_manipulating_time)
- [Spring Data Elasticsearch – Reactive repositories](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories/reactive.html)
- [Spring Data Elasticsearch – Reactive template](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/reactive-template.html)
- [Spring Data Elasticsearch – Testing](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/testing.html)
