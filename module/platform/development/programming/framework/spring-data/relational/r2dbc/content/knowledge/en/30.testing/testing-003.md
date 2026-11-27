# Using TestPublisher or Mocks at the Right Boundary to Control

When testing a Spring Data Relational R2DBC application, not every test needs a real database connection. A unit test for a service usually only needs to control which `Mono` or `Flux` the repository returns in order to verify business rules. A test that needs to control when a publisher emits data, emits an error, completes empty, receives requests, or gets cancelled can use `TestPublisher`. Conversely, when you need to verify SQL, mapping, codecs, transactions, generated IDs, or driver behavior, you must test against a real database or equivalent environment.

Choosing the right boundary keeps tests focused on what they need to prove. Mocks are suitable for replacing a dependency outside the unit under test. `TestPublisher` is suitable for controlling Reactive Streams signals at test-determined timing. `StepVerifier` consumes a publisher and verifies output signals. Integration tests verify the real interaction between Spring Data, the driver, and the database.

An important rule: mock the repository when testing service logic; do not mock `Mono`, `Flux`, `Row`, `Connection`, or internal chains of `DatabaseClient` to simulate an entire database and then conclude that the real SQL is correct. Repository-layer tests need to verify the real behavior of the persistence infrastructure.

## 1. Identifying the Boundary to Control

Before choosing a tool, identify what the test is trying to prove.

| Testing goal | Boundary to control | Appropriate tool |
| --- | --- | --- |
| Service chooses the right branch when repository has data | Repository result | Mockito mock returning `Mono.just(...)` |
| Service handles not-found cases | Empty completion of repository | Mock returning `Mono.empty()` or `TestPublisher` completing empty |
| Service translates errors into business errors | Error signal from dependency | Mock returning `Mono.error(...)` |
| Publisher emits data late or errors after a delay | Upstream signal timing | `TestPublisher` and `StepVerifier` |
| Verifying backpressure or cancellation | Subscriber request/cancel | `TestPublisher` and `StepVerifier` |
| Verifying retry resubscribes to publisher | Source behavior per subscription | `Mono.defer`, `TestPublisher`, or mock returning controllable publisher |
| Verifying repository generates correct SQL | Spring Data, dialect, driver, and database | Integration test with target database |
| Verifying generated IDs, codecs, mapping, transactions | Real persistence stack | Integration test with target R2DBC driver/database |
| Verifying API calls to external services | Client/service at service boundary | Mock client or HTTP stub server |

No single tool fits every layer. The closer a test is to the database, the better it catches SQL, mapping, and driver bugs; in exchange, tests run slower and need a database environment. Unit tests using mocks run fast, but only prove logic inside the mocked boundary.

## 2. Dependencies Required for `TestPublisher` and `StepVerifier`

`TestPublisher` and `StepVerifier` are in the `reactor-test` module. In Gradle:

```kotlin
dependencies {
    testImplementation("io.projectreactor:reactor-test")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

With Maven:

```xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

If the project uses Spring Boot dependency management, let the BOM manage compatible versions. `spring-boot-starter-test` typically provides JUnit Jupiter, Mockito, and common assertion libraries; check actual dependencies if the project uses a minimal test setup.

Common Reactor Test imports:

```java
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;
```

Common Mockito imports:

```java
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
```

Do not add `reactor-test` to runtime dependencies just to run the application. It is a testing library.

## 3. Mocking a Repository with Real Publishers

Suppose a service needs to find a customer and convert it into a DTO:

```java
public record Customer(Long id, String name) {
}

public record CustomerView(Long id, String displayName) {
}

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}

@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Mono<CustomerView> findView(Long id) {
        return repository.findById(id)
                .map(customer -> new CustomerView(
                        customer.id(), customer.name()
                ));
    }
}
```

A unit test can mock the repository and return a real `Mono`:

```java
@ExtendWith(MockitoExtension.class)
class CustomerServiceTest {

    @Mock
    CustomerRepository repository;

    CustomerService service;

    @BeforeEach
    void setUp() {
        service = new CustomerService(repository);
    }

    @Test
    void mapsCustomerToView() {
        when(repository.findById(10L))
                .thenReturn(Mono.just(new Customer(10L, "Lan")));

        StepVerifier.create(service.findView(10L))
                .expectNext(new CustomerView(10L, "Lan"))
                .verifyComplete();

        verify(repository).findById(10L);
    }
}
```

Here Mockito replaces the repository dependency. `Mono.just(...)` is still a real Reactor publisher, and `StepVerifier` subscribes to the service's result to verify `onNext` and `onComplete`.

Do not mock `Mono<CustomerView>` itself with Mockito. `Mono` is a reactive abstraction with rich semantics around subscription, demand, cancellation, and terminal signals; using real publishers makes tests more natural and less coupled to implementation details.

### Verifying Not-Found Cases

If the service converts empty into an error:

```java
public Mono<CustomerView> requireView(Long id) {
    return repository.findById(id)
            .map(customer -> new CustomerView(
                    customer.id(), customer.name()
            ))
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)
            ));
}
```

Test:

```java
@Test
void emitsNotFoundWhenRepositoryIsEmpty() {
    when(repository.findById(99L)).thenReturn(Mono.empty());

    StepVerifier.create(service.requireView(99L))
            .expectError(CustomerNotFoundException.class)
            .verify();

    verify(repository).findById(99L);
}
```

A mock returning `Mono.empty()` is enough if the test only needs to verify the rule "when there is no customer, emit an error." You do not need `TestPublisher` just to simulate a simple empty publisher.

### Verifying Dependency Errors

```java
@Test
void propagatesRepositoryFailure() {
    when(repository.findById(10L))
            .thenReturn(Mono.error(new IllegalStateException("database unavailable")));

    StepVerifier.create(service.findView(10L))
            .expectError(IllegalStateException.class)
            .verify();
}
```

This test verifies that the service does not accidentally turn a data-access failure into a success value. If the service uses `onErrorMap` or `onErrorResume`, assertions should verify the exact error/value according to the service contract.

## 4. Mockito Mocks Control Dependency Calls, Not Signal Timing

A mocked repository usually returns a known publisher:

```java
when(repository.findById(10L))
        .thenReturn(Mono.just(customer));
```

This works well for mapping or business branch tests. But if you need to emit data after the test has subscribed, emit an error at a specific point, verify whether upstream was cancelled, or inspect requests propagated to the publisher, static mocks may not be convenient enough.

Mockito can return `Mono.defer`, `Flux.create`, or a custom publisher, but when the goal is controlling Reactive Streams signals, `TestPublisher` makes test intent clearer.

### Do Not Confuse Method Invocation Time with SQL Execution Time

In a simple service:

```java
public Mono<Customer> find(Long id) {
    return repository.findById(id);
}
```

The Java call `repository.findById(id)` typically happens when the service method assembles the pipeline. With Spring Data reactive repositories, the returned publisher is usually cold and the database query executes when the publisher is subscribed to.

Therefore, Mockito's `verify(repository).findById(id)` proves the repository method was called to obtain a publisher. It does not prove SQL was sent to the database or that the database returned results. Those require integration tests.

If the service uses `Mono.defer`:

```java
public Mono<Customer> findLazily(Long id) {
    return Mono.defer(() -> repository.findById(id));
}
```

then the repository method is only called when the publisher is subscribed to. You can verify this:

```java
@Test
void callsRepositoryOnSubscription() {
    when(repository.findById(10L))
            .thenReturn(Mono.just(new Customer(10L, "Lan")));

    Mono<Customer> result = service.findLazily(10L);

    verifyNoInteractions(repository);

    StepVerifier.create(result)
            .expectNext(new Customer(10L, "Lan"))
            .verifyComplete();

    verify(repository).findById(10L);
}
```

Placing assertions at the right moments avoids false tests about laziness. Do not assume every repository method is called only after subscription; that depends on whether the service code wraps the call in `defer`.

## 5. What Is `TestPublisher`?

`TestPublisher<T>` is a controllable publisher for tests. A test can imperatively emit elements, emit an error, or complete after the pipeline has been subscribed to. It is especially useful when simulating an asynchronous data source where signal timing is dictated by the test.

Example:

```java
TestPublisher<Customer> source = TestPublisher.create();

Mono<Customer> result = source.mono();

StepVerifier.create(result)
        .then(() -> source.next(new Customer(10L, "Lan")))
        .expectNext(new Customer(10L, "Lan"))
        .verifyComplete();
```

`StepVerifier` starts the subscription. Then the `then(...)` callback asks `TestPublisher` to emit the customer. The test verifies that the element flows through the pipeline and the publisher completes.

Common control operations:

| API | Meaning |
| --- | --- |
| `TestPublisher.create()` | Creates a controllable publisher |
| `source.mono()` | Provides a `Mono` view |
| `source.flux()` | Provides a `Flux` view |
| `source.next(value)` | Emits one or more elements via varargs API |
| `source.emit(values...)` | Emits elements and then completes |
| `source.complete()` | Completes without emitting further elements |
| `source.error(error)` | Emits a terminal error |
| `source.assertWasSubscribed()` | Asserts there was a subscriber |
| `source.assertWasNotSubscribed()` | Asserts there was no subscriber yet |
| `source.assertWasRequested()` | Asserts the subscriber requested data |
| `source.assertCancelled()` | Asserts the publisher was cancelled |
| `source.assertMinRequested(n)` | Asserts total demand reached at least n |

Request/cancel assertions are useful when testing the behavior of a downstream publisher. Exact API names and assertion details should match the `reactor-test` version used by your project.

## 6. Using TestPublisher When Signal Timing Matters

Suppose a service fetches a customer and builds a DTO. We want to be sure the service emits no result before upstream emits data:

```java
@Test
void waitsUntilSourceEmitsCustomer() {
    TestPublisher<Customer> source = TestPublisher.create();
    when(repository.findById(10L)).thenReturn(source.mono());

    Mono<CustomerView> result = service.findView(10L);

    StepVerifier.create(result)
            .then(() -> source.assertWasSubscribed())
            .then(() -> source.next(new Customer(10L, "Lan")))
            .expectNext(new CustomerView(10L, "Lan"))
            .verifyComplete();
}
```

Here `TestPublisher` is supplied through the mocked repository. Mockito controls which dependency is replaced; `TestPublisher` controls that dependency's signals. Both tools can be combined rather than forcing an either/or choice.

### Emitting an Error After the Pipeline Has Subscribed

```java
@Test
void forwardsLateUpstreamError() {
    TestPublisher<Customer> source = TestPublisher.create();
    when(repository.findById(10L)).thenReturn(source.mono());

    StepVerifier.create(service.findView(10L))
            .then(() -> source.assertWasSubscribed())
            .then(() -> source.error(new IllegalStateException("late failure")))
            .expectError(IllegalStateException.class)
            .verify();
}
```

This test controls when the error occurs after subscription. It fits when testing how a pipeline handles late failures, such as an event source or reactive adapter.

### Completing Empty to Trigger a Fallback

```java
@Test
void usesFallbackWhenSourceCompletesEmpty() {
    TestPublisher<Customer> source = TestPublisher.create();
    when(repository.findById(10L)).thenReturn(source.mono());

    StepVerifier.create(service.requireView(10L))
            .then(() -> source.complete())
            .expectError(CustomerNotFoundException.class)
            .verify();
}
```

`complete()` emits no elements. Thus `switchIfEmpty` in the service is triggered. If the test only needs to check a static empty branch, `Mono.empty()` in Mockito is still simpler; `TestPublisher` adds value when the test needs to control completion timing or coordinate multiple signals.

## 7. TestPublisher with Multi-Element `Flux`

When a service processes a stream of multiple customers, use `flux()`:

```java
public Flux<CustomerView> streamViews() {
    return repository.findAll()
            .map(customer -> new CustomerView(
                    customer.id(), customer.name()
            ));
}
```

Test:

```java
@Test
void mapsItemsAsTheyArrive() {
    TestPublisher<Customer> source = TestPublisher.create();
    when(repository.findAll()).thenReturn(source.flux());

    StepVerifier.create(service.streamViews())
            .then(() -> source.next(
                    new Customer(1L, "Lan"),
                    new Customer(2L, "Minh")
            ))
            .expectNext(
                    new CustomerView(1L, "Lan"),
                    new CustomerView(2L, "Minh")
            )
            .then(() -> source.complete())
            .verifyComplete();
}
```

TestPublisher allows emitting a batch of elements, then emitting more or completing in subsequent steps. This lets tests verify ordering and how the service processes streams in chunks.

If the service uses `collectList()`, it only emits the list after upstream completes. The test must complete the source before expecting the list:

```java
StepVerifier.create(service.loadAllViews())
        .then(() -> source.next(customerA, customerB))
        .then(() -> source.complete())
        .expectNext(List.of(viewA, viewB))
        .verifyComplete();
```

Do not expect `collectList()` to emit a result immediately after `next(...)` if the source has not completed yet.

## 8. Testing Backpressure and Demand

Reactive Streams uses demand: subscribers request the number of elements they are ready to receive. `StepVerifier` can start with 0 demand and request elements step by step. `TestPublisher` can assert that upstream received the requests.

Example service returning a stream directly after mapping:

```java
public Flux<CustomerView> streamViews() {
    return repository.findAll()
            .map(customer -> new CustomerView(
                    customer.id(), customer.name()
            ));
}
```

Demand test:

```java
@Test
void requestsDataOnlyWhenDownstreamRequests() {
    TestPublisher<Customer> source = TestPublisher.create();
    when(repository.findAll()).thenReturn(source.flux());

    StepVerifier.create(service.streamViews(), 0)
            .then(() -> source.assertWasSubscribed())
            .then(() -> source.assertWasNotRequested())
            .thenRequest(1)
            .then(() -> source.assertMinRequested(1))
            .then(() -> source.next(new Customer(1L, "Lan")))
            .expectNext(new CustomerView(1L, "Lan"))
            .thenCancel()
            .verify();

    source.assertCancelled();
}
```

The test starts with an initial request of 0. After `thenRequest(1)`, the source can receive demand. The test emits one customer, verifies the DTO, and cancels the subscription. `assertCancelled()` confirms cancellation propagated back to the source.

### Do Not Assume One-to-One Demand Across All Operators

Some operators may prefetch or alter how data is requested. For example, `buffer`, `flatMap`, `publishOn`, `limitRate`, and `concatMap` have their own request strategies. Therefore, do not always assert that one downstream request corresponds to exactly one upstream request. Use demand assertions to check required contracts, and understand the prefetch behavior of the operators in use.

If testing a service that uses `flatMap` with concurrency/prefetch, determine the exact expected behavior before asserting request counts. TestPublisher helps observe requests, but it does not replace understanding Reactor operator semantics.

## 9. Testing Cancellation

Cancellation matters when a client disconnects, a timeout occurs, or a downstream operator no longer needs data. A well-behaved service should propagate cancellation upstream to stop unnecessary work.

Service example:

```java
public Flux<CustomerView> streamViews() {
    return repository.findAll()
            .map(customer -> new CustomerView(
                    customer.id(), customer.name()
            ));
}
```

Test:

```java
@Test
void propagatesCancellationToSource() {
    TestPublisher<Customer> source = TestPublisher.create();
    when(repository.findAll()).thenReturn(source.flux());

    StepVerifier.create(service.streamViews(), 0)
            .thenRequest(1)
            .then(() -> source.next(new Customer(1L, "Lan")))
            .expectNext(new CustomerView(1L, "Lan"))
            .thenCancel()
            .verify();

    source.assertCancelled();
}
```

After receiving one element, the verifier cancels the subscription. TestPublisher verifies that the source received cancellation. If the service adds buffering operators or creates inner publishers, check cancellation at meaningful boundaries and do not assume every inner resource is cancelled at the exact same instant.

### Cancellation Is Different from Error

Cancellation is not `onError`. Do not use `expectError` to test cancellation. `StepVerifier.thenCancel()` confirms the subscriber cancels, while `TestPublisher.assertCancelled()` confirms upstream observed the cancellation.

## 10. Testing `switchIfEmpty` Branches with TestPublisher

When testing a fallback branch, you can verify both the primary source and the alternative publisher. Service example:

```java
public Mono<Customer> findOrDefault(Long id) {
    return repository.findById(id)
            .switchIfEmpty(Mono.defer(() ->
                    repository.findDefaultCustomer()
            ));
}
```

Testing the case with data:

```java
@Test
void doesNotSubscribeFallbackWhenPrimaryHasValue() {
    TestPublisher<Customer> primary = TestPublisher.create();
    TestPublisher<Customer> fallback = TestPublisher.create();

    when(repository.findById(1L)).thenReturn(primary.mono());
    when(repository.findDefaultCustomer()).thenReturn(fallback.mono());

    StepVerifier.create(service.findOrDefault(1L))
            .then(() -> primary.next(new Customer(1L, "Lan")))
            .expectNext(new Customer(1L, "Lan"))
            .verifyComplete();

    fallback.assertWasNotSubscribed();
    verify(repository, never()).findDefaultCustomer();
}
```

Testing the empty source case:

```java
@Test
void subscribesFallbackWhenPrimaryIsEmpty() {
    TestPublisher<Customer> primary = TestPublisher.create();
    TestPublisher<Customer> fallback = TestPublisher.create();

    when(repository.findById(1L)).thenReturn(primary.mono());
    when(repository.findDefaultCustomer()).thenReturn(fallback.mono());

    StepVerifier.create(service.findOrDefault(1L))
            .then(() -> primary.complete())
            .then(() -> fallback.assertWasSubscribed())
            .then(() -> fallback.next(new Customer(0L, "Default")))
            .expectNext(new Customer(0L, "Default"))
            .verifyComplete();

    verify(repository).findDefaultCustomer();
}
```

To use `never()`, add the corresponding static import from Mockito. What the test needs to prove is that the fallback is only subscribed to when primary completes empty. If you only need to check the final result, mocks returning `Mono.just`/`Mono.empty` are more concise; TestPublisher is chosen because the test also checks subscription timing and which branch is actually activated.

## 11. Testing Retries and Subscription Counts

Retry resubscribes to the upstream publisher. When you want to verify how many times the source is subscribed to, you can use `TestPublisher` or a publisher created with `Mono.defer`.

Example of a source failing twice and then succeeding:

```java
AtomicInteger attempts = new AtomicInteger();

Mono<String> source = Mono.defer(() -> {
    int attempt = attempts.incrementAndGet();
    if (attempt < 3) {
        return Mono.error(new IllegalStateException("temporary"));
    }
    return Mono.just("ok");
});

StepVerifier.create(source.retry(2))
        .expectNext("ok")
        .verifyComplete();

assertThat(attempts).hasValue(3);
```

`Mono.defer` runs its supplier on each subscription, so the counter tracks upstream executions. With Mockito, note that the repository method may be invoked only once to obtain the publisher, while that publisher is resubscribed multiple times. Mockito's `verify(repository, times(3)).findById(id)` does not necessarily reflect three SQL executions if the publisher was created once and retried outside.

If you need to test how many times the publisher-creating method is called, place the repository call inside `Mono.defer` and use Mockito `thenAnswer` or `verify` appropriately. If you need to test how many times the publisher is subscribed to, count inside `Mono.defer`'s supplier or use appropriate TestPublisher assertions.

### Example Mocking a Repository to Create a Publisher per Call

```java
AtomicInteger attempts = new AtomicInteger();

when(repository.findById(10L)).thenAnswer(invocation ->
        Mono.defer(() -> {
            int attempt = attempts.incrementAndGet();
            if (attempt < 3) {
                return Mono.error(new IllegalStateException("temporary"));
            }
            return Mono.just(new Customer(10L, "Lan"));
        })
);

StepVerifier.create(service.findWithRetry(10L))
        .expectNext(new Customer(10L, "Lan"))
        .verifyComplete();

assertThat(attempts).hasValue(3);
```

In this example, `Mono.defer`'s supplier runs each time the source is subscribed to, so the counter reflects the simulated execution count. Mockito's `thenAnswer` only runs when the service invokes the mock method; if the service calls the method once and caches the publisher, `thenAnswer` is also only called once. Be clear about whether your counter is measuring method invocations or publisher subscriptions.

## 12. Mocking at the Right Service Boundary

A service unit test should replace dependencies outside the service, such as:

- Repositories the service calls.
- HTTP/gRPC clients.
- Message publishers or gateways.
- Clocks, ID generators, or policy providers when time/values need control.

Do not mock internal objects created by the service itself, such as DTOs, `Mono.just`, `Flux.map`, or a pure mapper if tests can invoke it directly.

Example service coordinating a repository and an external client:

```java
public Mono<OrderView> loadOrder(Long id) {
    return orderRepository.findById(id)
            .switchIfEmpty(Mono.error(new OrderNotFoundException(id)))
            .flatMap(order -> customerClient.findName(order.customerId())
                    .map(name -> new OrderView(order.id(), name)));
}
```

A unit test can mock both dependencies while still returning real publishers:

```java
when(orderRepository.findById(100L))
        .thenReturn(Mono.just(order));
when(customerClient.findName(20L))
        .thenReturn(Mono.just("Lan"));

StepVerifier.create(service.loadOrder(100L))
        .expectNext(new OrderView(100L, "Lan"))
        .verifyComplete();

verify(orderRepository).findById(100L);
verify(customerClient).findName(20L);
```

This test proves the service passes the right customer ID and combines the response properly. It does not prove the order query or actual HTTP request is right; those belong in tests at their respective repository/client boundaries.

## 13. Why Should You Avoid Deep-Mocking `DatabaseClient`?

`DatabaseClient` has a multi-layered fluent API:

```java
databaseClient.sql(sql)
        .bind("id", id)
        .map((row, metadata) -> ...)
        .one();
```

Mocking each nested interface couples the test to Spring's internal implementation. A minor change in the fluent API chain can break the test even when SQL behavior has not changed. Deep mocks also fail to verify:

- Whether the SQL is valid on the database.
- Whether bind markers are converted properly.
- Whether data types have codecs.
- Whether column aliases and `Row` mapping are accurate.
- Whether transactions actually roll back.
- Whether generated values are returned by the driver.

If service logic calls a dedicated adapter, mock that adapter. If testing the adapter that uses `DatabaseClient`, run an integration test with an appropriate database. You can unit-test a pure mapping function with fixture data if mapping is extracted into a directly callable function, while still keeping at least one integration test confirming that the real `Row`/driver provides data as expected.

## 14. Boundaries Between R2DBC Unit Tests and Integration Tests

A practical split:

| Layer | Real components | Replaceable components | What the test proves |
| --- | --- | --- | --- |
| Service unit test | Service, Reactor operators, DTO mapping | Repository/client/clock | Business rules and publisher coordination |
| Reactive flow test | Service/adapter pipeline | Source publisher via TestPublisher | Timing, signals, demand, cancellation, fallback |
| Repository integration | Spring Data repository, mapping, driver, database | Unrelated external services | SQL, mapping, codecs, constraints, generated IDs |
| Transaction integration | Transaction manager, connection factory, database | External APIs outside the transaction | Commit/rollback and resource binding |
| End-to-end | Application wiring and core components | External systems may use stubs | Full-flow behavior close to production |

You do not need a real database for every unit test. Conversely, you cannot prove persistence works solely by mocking repositories.

## 15. Repository Integration Tests with a Real Database

To test Spring Data R2DBC, use the same database kind as production, typically via Testcontainers or a dedicated managed test environment.

Example test skeleton with Spring Boot:

```java
@SpringBootTest
class CustomerRepositoryIntegrationTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void savesAndReadsCustomer() {
        StepVerifier.create(
                repository.save(new Customer(null, "Lan"))
        )
        .assertNext(saved -> {
            assertThat(saved.id()).isNotNull();
            assertThat(saved.name()).isEqualTo("Lan");
        })
        .verifyComplete();
    }
}
```

The example assumes the entity and constructor match the project mapping, the database is running, and migrations have executed. Testcontainers/R2DBC URL configuration depends on the server and Spring Boot version. For repository tests, ensure the container is configured before the application context creates `ConnectionFactory`.

Items to verify with integration tests:

- `@Table`, `@Column`, `@Id`, and naming strategies.
- Real inserts/updates/deletes.
- Generated IDs and default values.
- Mapping `NULL`, `UUID`, `Instant`, `BigDecimal`, JSON, or custom types.
- `@Version` and optimistic locking.
- `@MappedCollection` or aggregate relationships if used.
- Custom conversions and entity callbacks.
- `@Query` SQL, joins, pagination, and dialect-specific upserts.

H2 does not fully substitute for PostgreSQL, MySQL, MariaDB, or SQL Server when an application depends on specific syntax, data types, generated values, or transaction semantics.

## 16. Integration Testing Transactions and Mid-Flight Failures

If a service writes to multiple tables in a reactive transaction, tests must prove real rollback:

```java
@Transactional
public Mono<Void> createOrderThenFail(Order order) {
    return orderRepository.save(order)
            .flatMap(saved -> auditRepository.save(
                    new AuditEntry(saved.id(), "CREATED")
            ))
            .then(Mono.error(new IllegalStateException("force rollback")));
}
```

An integration test can call the service, assert that the publisher emits an error, and then query both tables using an operation outside the test transaction to verify no data was persisted. Be careful if the test method itself is annotated with `@Transactional`: the test transaction can mask commit/rollback results or cause the verification query to run inside the same transaction. Design test transaction boundaries explicitly.

Mocking the repository can verify that the service chains publishers properly, but it does not prove `R2dbcTransactionManager` uses the same connection, that the database actually rolls back, or that the driver handles cancellation properly.

## 17. TestPublisher and Hot/Cold Sources

Reactor TestPublisher can be created in cold or hot modes:

- **Cold TestPublisher** can retain signals emitted before a subscriber arrives and deliver them to the subscriber according to cold semantics.
- **Hot TestPublisher** emits signals to current subscribers; signals emitted when there are no subscribers are not replayed to later subscribers.

When testing subscription and emission timing, pick the mode matching the source the application integrates with. For event sources or callback APIs, hot behavior may matter; for a publisher recomputed per subscription, cold semantics usually fit better.

Conceptual example with a hot source:

```java
TestPublisher<String> hot = TestPublisher.createHot();
hot.next("before-subscribe");

StepVerifier.create(hot.flux())
        .then(() -> hot.next("after-subscribe"))
        .expectNext("after-subscribe")
        .then(() -> hot.complete())
        .verifyComplete();
```

Signals emitted before subscription are not expected to replay to a late hot subscriber. When signals prior to subscription must be retained, use a cold publisher or appropriate buffering semantics.

With a cold source:

```java
TestPublisher<String> cold = TestPublisher.createCold();
cold.next("queued");

StepVerifier.create(cold.flux())
        .expectNext("queued")
        .then(() -> cold.complete())
        .verifyComplete();
```

Exact modes and APIs must match your Reactor Test version. Do not choose hot/cold based purely on the name; match the actual semantics of the publisher source the adapter receives.

## 18. TestPublisher Does Not Replace `StepVerifier`

The two tools play complementary roles:

- `TestPublisher` drives the source: emits `next`, `error`, `complete`, and observes request/cancel.
- `StepVerifier` is the test subscriber: subscribes to the publisher, requests data, and asserts the signal sequence.

Example:

```java
TestPublisher<Integer> source = TestPublisher.create();
Flux<Integer> result = source.flux().map(value -> value * 2);

StepVerifier.create(result)
        .then(() -> source.next(2))
        .expectNext(4)
        .then(() -> source.complete())
        .verifyComplete();
```

Creating `TestPublisher` without subscribing to the result tests nothing in the pipeline. Using `StepVerifier` with `Flux.just(...)` fits ordinary output tests, but does not let you drive upstream signal timing like TestPublisher does.

## 19. Using `createNoncompliant` When Testing Reactive Streams Violations

`TestPublisher.createNoncompliant(...)` creates a publisher that intentionally violates specific Reactive Streams rules, such as emitting signals without demand or emitting after a terminal signal, depending on the selected `Violation`.

This is a specialized tool for testing whether custom adapters or operators withstand non-compliant publisher sources. Do not use it in routine tests for R2DBC repositories. A non-compliant source can produce behavior unrepresentative of valid publishers and make tests hard to interpret.

Use it only when:

- Building an adapter that must accept publishers from an untrusted third-party library.
- Needing to verify that a component handles/drops violating signals as required.
- The test clearly documents which violation is simulated and why.

For standard R2DBC repository and driver flows, `TestPublisher.create()` or `createCold()`/`createHot()` is sufficient.

## 20. Checking Whether a Publisher Was Invoked: Mock or TestPublisher?

Sometimes a test needs to verify that a fallback branch was not invoked. Mockito `verify` checks dependency method calls; TestPublisher assertions check whether a publisher received a subscriber. These two are not identical.

Service example:

```java
public Mono<Customer> findOrDefault(Long id) {
    return repository.findById(id)
            .switchIfEmpty(Mono.defer(repository::findDefaultCustomer));
}
```

If you want to verify the service did not call the fallback method, use:

```java
verify(repository, never()).findDefaultCustomer();
```

If the fallback publisher was created ahead of time and you want to verify it was not subscribed to, use TestPublisher:

```java
fallback.assertWasNotSubscribed();
```

With `Mono.defer`, invoking the method that builds the fallback publisher is also deferred. Thus `verify(..., never())` checks that the method was not called, while `assertWasNotSubscribed()` checks that the source was not subscribed to. Choose the assertion matching the exact behavior to guarantee.

## 21. Do Not Use TestPublisher to Fake Drivers or Connections

`TestPublisher` can replace a `Publisher` at a unit test boundary, but it does not simulate the R2DBC protocol. It does not verify:

- Whether the driver opens and closes connections properly.
- Whether SQL is sent and parsed properly by the database.
- Whether bind parameters are encoded with the right types.
- Whether `Row` carries expected metadata and codecs.
- Whether the connection pool returns connections after cancel.
- Whether transactions commit/roll back on the server.
- Whether generated values are returned by the server/driver.

When you need to test those behaviors, use a real database or Testcontainers with the real driver. You cannot prove generated IDs work by having TestPublisher emit a `Customer` with a pre-assigned ID.

## 22. Mocking Repositories in Service Tests: Common Mistakes

### Mock Returns `null` Instead of a Publisher

A reactive repository method must return a publisher:

```java
when(repository.findById(id)).thenReturn(Mono.empty());
```

Do not let mocks return `null`. Calling `.map` or `.switchIfEmpty` on null throws a `NullPointerException`, which is a test configuration error rather than "not found" semantics.

### Using `Mono.just(null)`

Reactor does not allow `Mono.just(null)`. Use `Mono.empty()` to represent no element:

```java
when(repository.findById(id)).thenReturn(Mono.empty());
```

If you need to turn a nullable Java value into a publisher, use `Mono.justOrEmpty(value)`.

### Calling `block()` for Assertions

Do not block publishers in reactive unit tests. Use `StepVerifier` to check signals:

```java
StepVerifier.create(service.findView(id))
        .expectNext(expected)
        .verifyComplete();
```

`block()` creates a subscription and blocks the thread; using it can hide cancellation/backpressure behavior and makes the test unlike how reactive applications consume publishers.

### Only Verifying Method Calls Without Subscribing to the Publisher

```java
Mono<CustomerView> result = service.findView(id);
verify(repository).findById(id);
```

This snippet may prove the repository method was called at assembly time, but it does not prove the publisher was consumed or produced the right output. Use `StepVerifier` to subscribe and verify the result.

### Reusing One Mutable Publisher Across Multiple Tests

`TestPublisher` holds subscription state and terminal signals. Create a fresh publisher per test so signals or cancellations from an earlier test do not leak into later tests. Do not share a static TestPublisher across tests running in parallel.

## 23. Testing Retries with Mockito and TestPublisher

Suppose a service retries once on a transient dependency error:

```java
public Mono<Customer> findWithRetry(Long id) {
    return Mono.defer(() -> repository.findById(id))
            .retryWhen(Retry.max(1));
}
```

You can use Mockito `thenAnswer` to return a different publisher on each invocation:

```java
AtomicInteger calls = new AtomicInteger();

when(repository.findById(10L)).thenAnswer(invocation -> {
    if (calls.incrementAndGet() == 1) {
        return Mono.error(new R2dbcTransientResourceException("temporary"));
    }
    return Mono.just(new Customer(10L, "Lan"));
});

StepVerifier.create(service.findWithRetry(10L))
        .expectNext(new Customer(10L, "Lan"))
        .verifyComplete();

assertThat(calls).hasValue(2);
```

Here `Mono.defer` wraps the repository call so the mock method is invoked again when retry resubscribes. Without `defer`, the method might be called only once when the service builds the pipeline while the returned publisher gets resubscribed.

If a test wants to control a late error and decide whether the next attempt succeeds, you can use a separate TestPublisher per attempt or a stateful publisher factory. However, avoid making tests more complex than necessary: for simple retry logic, `Mono.defer` and `AtomicInteger` are usually clearer.

## 24. Testing Concurrency and Race Conditions at the Right Boundary

Some bugs only appear when multiple subscriptions run concurrently, such as two requests creating a customer with the same unique email. TestPublisher can help control when sources emit data to set up a race scenario in a unit test, but it does not prove database constraints protect properly.

For example, `findOrCreate` service logic can be tested with two publishers both completing empty, which only proves the service chooses the insert branch on both subscriptions. To prove only one row is created, you must run two real transactions against a database with a unique constraint and verify that one insert succeeds while the other request handles the duplicate properly.

When testing concurrency against a database:

- Use the target database engine and isolation level.
- Initialize clean data and synchronize the starting point of the two operations.
- Do not rely on sleep to induce a race when deterministic latches/barriers or test hooks can be used.
- Verify final database state and translated exceptions.
- Ensure tests clean up data and do not share unique keys with other parallel tests.

## 25. A Layered Testing Strategy

An R2DBC module usually needs a combination of test types:

### Service Unit Tests

- Mock repositories/clients.
- Return `Mono.just`, `Mono.empty`, `Flux.just`, `Mono.error`.
- Use `StepVerifier` to check outputs and terminal signals.
- Verify dependencies are called with expected arguments.
- Do not start a database.

### Reactive Flow Tests

- Use `TestPublisher` to emit data late.
- Check empty/error/complete.
- Check demand and cancellation.
- Check retry or fallback when timing is part of the behavior.
- Use virtual time when testing delays/timeouts without real-time waiting.

### Repository Integration Tests

- Start a database matching production.
- Use the real R2DBC driver and real migrations.
- Verify SQL, mapping, codecs, generated keys, and constraints.
- Do not mock the repository under test.

### Transaction Integration Tests

- Use the real `R2dbcTransactionManager`.
- Verify commit and rollback.
- Verify shared `ConnectionFactory` and connection binding.
- Verify cancellation/timeout if those guarantees are required.

You do not need to repeat every case at every layer. Unit tests should focus on fast logic checks; integration tests should focus on contracts with the database and driver.

## 26. Full Example: Service Tested with Mocks and TestPublisher

Service:

```java
public interface CustomerRepository {
    Mono<Customer> findById(Long id);
    Flux<Customer> findAll();
}

public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Mono<CustomerView> findView(Long id) {
        return repository.findById(id)
                .map(customer -> new CustomerView(
                        customer.id(), customer.name()
                ))
                .switchIfEmpty(Mono.error(
                        new CustomerNotFoundException(id)
                ));
    }

    public Flux<CustomerView> streamViews() {
        return repository.findAll()
                .map(customer -> new CustomerView(
                        customer.id(), customer.name()
                ));
    }
}
```

Test class:

```java
@ExtendWith(MockitoExtension.class)
class CustomerServiceTest {

    @Mock
    CustomerRepository repository;

    CustomerService service;

    @BeforeEach
    void setUp() {
        service = new CustomerService(repository);
    }

    @Test
    void mapsFoundCustomer() {
        when(repository.findById(1L))
                .thenReturn(Mono.just(new Customer(1L, "Lan")));

        StepVerifier.create(service.findView(1L))
                .expectNext(new CustomerView(1L, "Lan"))
                .verifyComplete();

        verify(repository).findById(1L);
    }

    @Test
    void errorsWhenCustomerIsMissing() {
        when(repository.findById(1L)).thenReturn(Mono.empty());

        StepVerifier.create(service.findView(1L))
                .expectError(CustomerNotFoundException.class)
                .verify();
    }

    @Test
    void mapsItemsFromControllableSource() {
        TestPublisher<Customer> source = TestPublisher.create();
        when(repository.findAll()).thenReturn(source.flux());

        StepVerifier.create(service.streamViews())
                .then(() -> source.next(new Customer(1L, "Lan")))
                .expectNext(new CustomerView(1L, "Lan"))
                .then(() -> source.next(new Customer(2L, "Minh")))
                .expectNext(new CustomerView(2L, "Minh"))
                .then(() -> source.complete())
                .verifyComplete();
    }

    @Test
    void propagatesCancellation() {
        TestPublisher<Customer> source = TestPublisher.create();
        when(repository.findAll()).thenReturn(source.flux());

        StepVerifier.create(service.streamViews(), 0)
                .thenRequest(1)
                .then(() -> source.next(new Customer(1L, "Lan")))
                .expectNext(new CustomerView(1L, "Lan"))
                .thenCancel()
                .verify();

        source.assertCancelled();
    }
}
```

The example combines four goals into one class for illustration; in a project you can separate tests by behavior. `Customer`, `CustomerView`, and exception types must be declared according to actual code. A new `TestPublisher` is created in each test to avoid sharing state.

## 27. Common Mistakes When Choosing the Wrong Boundary

| Symptom | Possible cause | Solution |
| --- | --- | --- |
| Unit test needs a database just to test service branches | Service test reaches too deeply into persistence | Mock the repository and return real publishers |
| Test cannot control when the source emits data | Mock returns fixed `Mono.just`/`Flux.just` | Use `TestPublisher` |
| Mock test passes but production SQL fails | Repository was mocked in a test meant to check SQL | Write an integration test with a real database/driver |
| Mock returning `null` throws NPE | Reactive method not stubbed | Return `Mono.empty()`, `Flux.empty()`, or a suitable publisher |
| Using `Mono.just(null)` | Reactor forbids null elements | Use `Mono.empty()` or `Mono.justOrEmpty()` |
| `verify` passes without output assertions | Only checked method call, never consumed publisher | Use `StepVerifier` |
| Wrong retry count | Confused method invocation with publisher subscription | Count at the right boundary; use `defer` to recreate sources |
| TestPublisher does not receive expected signals | Source not subscribed, already terminated, or wrong hot/cold semantics | Assert subscription and drive steps in the right order |
| Backpressure test expects exact request count and fails | Operators prefetch or modify demand | Check operator semantics, assert appropriate demand |
| Cancellation not observed | Downstream did not cancel or source is not the checked upstream | Use `thenCancel()` and assert on the right publisher |
| Flaky parallel test runs | Shared TestPublisher or mutable mock state | Create dedicated fixtures per test |
| Deep-mocking `DatabaseClient` is brittle | Test depends on fluent chain implementation | Extract an adapter and use integration tests for SQL |
| H2 passes but SQL Server/MySQL/PostgreSQL fails | Different dialects, types, and drivers | Run tests against a production-compatible database |

## 28. Decision Flow for Choosing Mocks vs. TestPublisher

Before writing a test, answer:

1. Is the subject under test a service, a reactive adapter, or a repository?
2. Which dependencies lie outside that subject's boundary?
3. Does the test only need a fixed result or does it need to control signal timing?
4. Does it need to observe requests, backpressure, or cancellation?
5. Does it need to verify SQL, mapping, drivers, transactions, or constraints?

From there, choose:

- **Mock returning a real publisher** if you only need to control dependency outputs.
- **Mock combined with TestPublisher** if you need to replace a dependency and control signal timing.
- **TestPublisher directly** if testing an adapter/pipeline that accepts a `Publisher` and no other mocks are needed.
- **Database integration test** if behavior depends on SQL Server/the database, driver, mapping, or transactions.

Do not pick TestPublisher simply because the code uses Reactor. A `Mono.just`, `Mono.empty`, or `Mono.error` is often the simplest and clearest fixture. Use TestPublisher when signal control adds real value to the test.

## 29. Key Takeaways

- Mock repositories in service unit tests to control dependencies; return real `Mono`/`Flux` instances instead of mocking reactive types.
- `StepVerifier` subscribes to publishers and asserts `onNext`, `onComplete`, `onError`, requests, and cancellation.
- `TestPublisher` lets tests imperatively emit data, complete empty, error, and observe subscription/request/cancel.
- Use static mocks for simple results; use TestPublisher when you need to control timing or upstream signals.
- Mockito verifying method invocation does not mean SQL ran; reactive publishers usually execute only when subscribed to.
- With `Mono.defer`, dependency methods may only run when subscription begins; place verify calls at the right moment.
- Retries resubscribe to the publisher; repository method call counts and publisher subscription counts can differ.
- Do not deep-mock `DatabaseClient`, `Row`, or `Connection` to prove SQL/driver correctness.
- Repository integration tests need the target database and R2DBC driver to verify mapping, codecs, generated values, constraints, and transactions.
- TestPublisher does not simulate database protocols or connection pools; it only drives a publisher at the test boundary.
- Test cancellation with `StepVerifier.thenCancel()` and source assertions; cancellation is not an error.
- Backpressure tests must account for prefetching and Reactor operator semantics.
- Create a fresh TestPublisher for each test; do not share mutable publishers across parallel tests.
- Use non-compliant TestPublisher only when testing sources that violate Reactive Streams.

Choosing between mocks and TestPublisher depends on the behavior you need to control. Mocks isolate a service from repositories/clients; TestPublisher actively drives signals and demand of reactive sources; StepVerifier verifies the output publisher. When you need to prove that SQL, mapping, codecs, generated keys, or R2DBC transactions truly work, move to integration tests with the appropriate database and driver.
