# Avoiding Blocking or Race Conditions in Test Setup

## 1. The Problem: Reactive Tests Failing Even When the Contract Has Not Changed

In a **Spring WebFlux** application, a producer may accept HTTP requests, query a database via Reactive Streams, and return `Mono<T>` or `Flux<T>`. The consumer only sees HTTP status, headers, and the JSON body. **Spring Cloud Contract** lets you express those expectations in Groovy/YAML DSL, generate producer tests, publish stubs for consumers to run via Stub Runner, and integrate verification into CI.

Trouble strikes when **preparing test data** asynchronously **without waiting for it to finish**.

For example, a generated test will call:

~~~http
GET /api/orders/ORD-123 HTTP/1.1
Accept: application/json
~~~

and expect to receive:

~~~json
{
  "orderId": "ORD-123",
  "status": "CONFIRMED",
  "totalAmount": 120000
}
~~~

Before the test sends the request, the base class needs to insert order `ORD-123` into a reactive repository. If setup is written as:

~~~java
@BeforeEach
protected void setUp() {
    repository.save(new OrderEntity(
        "ORD-123", "CONFIRMED", 120000L
    )).subscribe();
}
~~~

then calling `subscribe()` **starts a subscription and returns immediately**; it does not guarantee the save operation finishes before the generated test sends its request. One run may get `200`, while another gets `404`. This is a **race condition in the test fixture**, not necessarily a producer API breakage.

Switching it to `Thread.sleep(1000)` still fails when CI runners are slow, while bloating test suite runtime. Calling `block()` on a reactive thread where blocking is forbidden can cause producer or test errors or thread starvation.

This lesson belongs to the **Reactive Testing** chapter of the `SPRING_CLOUD_CONTRACT` module, focusing on how to guarantee initial preconditions for generated contract tests **are ready** without blocking the event loop or relying on arbitrary wait durations.

### Learning Outcomes

After this lesson, you will be able to:

1. Explain cold publishers, subscriptions, completion, and why setup races happen.
2. Distinguish **bounded waiting on the test thread** from **dangerous blocking on an event-loop thread**.
3. Use `StepVerifier` to prepare test data in a verifiable way.
4. Choose a better fixture strategy: mocks returning `Mono.just(...)`, ordered reactive repository seeding, or waiting on deterministic events.
5. Configure WebFlux contract tests using `WEBTESTCLIENT`/`RestAssuredWebTestClient` and an appropriate base test.
6. Avoid shared state, late subscriber registration, and unbounded waits/timeouts.
7. Diagnose fixture misalignments vs. real API breaking changes before publishing stubs.

> **Principle:** *Data required by a test must be in an observably ready state before sending the request.* Never treat creating a `Mono`, calling `subscribe()`, or sleeping for an arbitrary interval as proof that setup has completed.

## 2. Mastering the Three Moments of a Publisher

In Project Reactor, `Mono<T>` represents at most one value or a completion/error signal, while `Flux<T>` represents 0 to many values. Many publishers are **cold**: I/O or logic is triggered only when subscribed.

Consider:

~~~java
Mono<OrderEntity> saveOperation =
    repository.save(new OrderEntity("ORD-123", "CONFIRMED", 120000L));
~~~

Distinguish carefully:

| Moment | What has happened | What is **not** guaranteed yet |
| --- | --- | --- |
| Creating the `Mono` | A description of the save work exists | I/O may not have started |
| Subscribing | The publisher begins being consumed | The operation may not have finished |
| Receiving `onNext` and/or `onComplete` | Publisher reports progress/success per its contract | External systems outside the publisher may not reflect it yet if eventual consistency applies |
| Receiving `onError` | The operation reported failure | Fixture cannot be considered ready |

With typical reactive repositories, completion from the write publisher is a critical synchronization point before issuing subsequent HTTP requests. If the system uses queues, async indexing, caches, or post-save events, **observe the actual readiness signal** of the component the request reads from.

### 2.1. Race Diagram Caused by Detached Subscribe

~~~mermaid
sequenceDiagram
    participant J as JUnit @BeforeEach
    participant DB as Reactive repository
    participant T as Generated contract test
    participant API as WebFlux controller
    J->>DB: save(order).subscribe()
    J-->>T: setup returns immediately
    T->>API: GET /api/orders/ORD-123
    API->>DB: findById(ORD-123)
    DB-->>API: Order not visible yet
    API-->>T: 404
    DB-->>J: save completes afterward
~~~

This failure mode is **schedule-dependent and nondeterministic**: outcomes hinge on which scheduler executes first, database latency, CPU, and CI load.

### 2.2. "Non-Blocking" Does Not Mean "Never Waiting"

In tests, the real questions are **which thread waits, whether the wait is bounded, and what condition it awaits**:

- **Wrong:** Calling `block()` or `Thread.sleep` inside a WebFlux callback running on a Reactor Netty event loop.
- **Risky:** Calling `subscribe()` in `@BeforeEach` and letting the test proceed without a completion signal.
- **Acceptable when controlled:** Using `StepVerifier.verify(Duration)` on the **JUnit test thread** to wait for setup publishers to finish with a finite timeout.
- **Even better for web-slice tests:** Mocking the reactive dependency to return `Mono.just(...)` or `Mono.empty()` so no async seeding I/O is needed.

The goal is avoiding **uncontrolled blocking** and **race conditions**, not forcing every Java helper method in a test to stay asynchronous.

## 3. Anti-Patterns to Spot Immediately

### 3.1. Creating a Mono Without Subscribing

~~~java
@BeforeEach
protected void setUp() {
    repository.deleteAll()
        .then(repository.save(order));
}
~~~

This only constructs a pipeline. Without an external subscription, normally **no delete or save executes at all**.

### 3.2. Fire-and-Forget in Setup

~~~java
@BeforeEach
protected void setUp() {
    repository.deleteAll().subscribe();
    repository.save(order).subscribe();
}
~~~

Two independent subscriptions provide **no guarantee deletion finishes before saving**, nor that saving finishes before the request. This is especially dangerous when generated tests run in parallel: one test can wipe data another test just wrote.

### 3.3. Sleeping to "Wait for Data to Settle"

~~~java
@BeforeEach
protected void setUp() throws InterruptedException {
    repository.save(order).subscribe();
    Thread.sleep(1000);
}
~~~

This approach is **time-dependent**. Passing locally does not mean CI will pass. Bumping 1 second to 10 seconds only hides the risk and slows down the suite.

### 3.4. `block()` Inside Request-Handling Pipelines

~~~java
@GetMapping("/api/orders/{id}")
Mono<OrderView> get(@PathVariable String id) {
    OrderEntity entity = repository.findById(id).block(); // Avoid
    return Mono.just(mapper.toView(entity));
}
~~~

The WebFlux/Netty event loop must remain non-blocking. Calling `block()` here can throw `IllegalStateException` on non-blocking threads or create a throughput bottleneck. Proper producer code **composes publishers**:

~~~java
@GetMapping("/api/orders/{id}")
Mono<OrderView> get(@PathVariable String id) {
    return repository.findById(id)
            .map(mapper::toView);
}
~~~

**Scope differs:** `block()` on a JUnit thread inside controlled setup is not the same as `block()` inside a WebFlux request pipeline. Still, an un-timed `block()` risks hanging tests, so prefer `StepVerifier` with timeouts and completion assertions.

## 4. Preparing Fixtures with Bounded StepVerifier

A straightforward pattern is **composing delete/save work into a single pipeline**, then awaiting the completion signal before JUnit proceeds to the generated test.

Assuming `repository` is a `ReactiveCrudRepository` and `order` is a sample entity:

~~~java
import java.time.Duration;
import org.junit.jupiter.api.BeforeEach;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@BeforeEach
protected void seedOrder() {
    OrderEntity order =
        new OrderEntity("ORD-123", "CONFIRMED", 120000L);

    Mono<Void> arrange = repository.deleteAll()
        .then(repository.save(order))
        .then();

    StepVerifier.create(arrange)
        .expectComplete()
        .verify(Duration.ofSeconds(5));
}
~~~

Step-by-step explanation:

1. `repository.deleteAll()` creates the delete publisher.
2. `then(repository.save(order))` runs the save **only after delete completes successfully**, never concurrently with deletion.
3. `then()` converts the result to `Mono<Void>`, caring only about completion/error signals.
4. `StepVerifier.create(arrange)` creates a verifier that subscribes when `verify(...)` is called.
5. `expectComplete()` requires the publisher to finish successfully, not merely accept subscription.
6. `verify(Duration.ofSeconds(5))` waits **at most** 5 seconds on the test thread, failing on timeout or unmet expectations.

This is a **bounded wait** on the test thread, not blocking the Reactor event loop inside an endpoint. The 5-second value is illustrative; choose a timeout suited to real test database and CI latency without letting waits stretch indefinitely.

### 4.1. Extra Assertion to Confirm the Fixture Was Persisted

If you want to verify the data is readable:

~~~java
StepVerifier.create(repository.findById("ORD-123"))
    .assertNext(saved -> {
        assertThat(saved.getStatus()).isEqualTo("CONFIRMED");
        assertThat(saved.getTotalAmount()).isEqualTo(120000L);
    })
    .expectComplete()
    .verify(Duration.ofSeconds(5));
~~~

This helps distinguish "save publisher signalled complete" from "read path does not see the data yet" when necessary. If reads depend on an eventually consistent search index or cache, wait for that readiness mechanism with a deterministic condition rather than polling endlessly.

### 4.2. Do Not Forget StepVerifier Timeouts

Shorthand methods like `verifyComplete()` are convenient, yet by default **may have no timeout** unless the project configures `StepVerifier.setDefaultTimeout(...)`. In a broken pipeline that never emits `onComplete`, tests can hang forever.

For setup that must finish before requests run, state both completion expectations and a timeout:

~~~java
StepVerifier.create(repository.save(order))
    .expectNextMatches(saved -> "ORD-123".equals(saved.getId()))
    .expectComplete()
    .verify(Duration.ofSeconds(5));
~~~

Do not pick a timeout so tight that CI produces frequent false failures; equally, never use multi-minute timeouts as a substitute for fixing races or database connection bugs.

## 5. When No Database Is Needed: Deterministic Reactive Mocks

For HTTP contract tests at the **web slice**, the goal is usually verifying method/path, status, JSON serialization, and controller mapping—not the full storage layer. In that case, **mocking a dependency to return deterministic publishers** is the simplest way to eliminate fixture races.

Suppose you have an interface:

~~~java
public interface OrderQuery {
    Mono<OrderView> findById(String orderId);
}
~~~

DTO:

~~~java
public record OrderView(
    String orderId,
    String status,
    long totalAmount
) {}
~~~

Reactive controller:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderQuery orderQuery;

    public OrderController(OrderQuery orderQuery) {
        this.orderQuery = orderQuery;
    }

    @GetMapping("/{orderId}")
    public Mono<OrderView> getById(@PathVariable String orderId) {
        return orderQuery.findById(orderId);
    }
}
~~~

In the base class, the mock returns a **pre-defined** publisher:

~~~java
@MockitoBean
OrderQuery orderQuery;

@BeforeEach
protected void setUp() {
    given(orderQuery.findById("ORD-123"))
        .willReturn(Mono.just(
            new OrderView("ORD-123", "CONFIRMED", 120000L)
        ));
}
~~~

`Mono.just(...)` emits the value upon subscription without hitting a database or requiring a prior async write. That keeps web-slice contract tests focused on **request/response behavior** with stable fixtures.

To test a "not found" branch, prepare:

~~~java
given(orderQuery.findById("ORD-404"))
    .willReturn(Mono.empty());
~~~

Note that `Mono.empty()` only indicates the dependency has no data. **The final status and error body** depend on how the controller uses `switchIfEmpty(...)`, error mappings, or exception handlers. Never assume `Mono.empty()` automatically generates a `404` response with your desired JSON error envelope.

### 5.1. Limits of Mocking

Mocks make tests faster and more stable, yet **do not prove the reactive repository actually works** or that the system handles transactions and read/write races properly. Combine:

- Web-slice contract tests to protect the HTTP API.
- Repository integration tests to verify reactive reads/writes.
- Service/domain tests to verify business rules.
- End-to-end tests when consumers depend on eventual latency of external systems.

## 6. Writing HTTP Contracts and Choosing WEBTESTCLIENT Instead of MOCKMVC

Example contract `src/test/resources/contracts/orders/get_order.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_confirmed_order')

    request {
        method GET()
        urlPath('/api/orders/ORD-123')
        headers {
            accept(applicationJson())
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            orderId: 'ORD-123',
            status: 'CONFIRMED',
            totalAmount: 120000
        )
    }
}
~~~

The DSL describes **HTTP behavior**, not whether tests run with MockMvc or WebTestClient. For producers built on Spring WebFlux, Spring Cloud Contract supports **`WEBTESTCLIENT`** test mode, and generated code can use **RestAssuredWebTestClient**. This is documented in the official Spring Cloud Contract reference.

Illustrative Maven configuration:

~~~xml
<plugin>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-contract-maven-plugin</artifactId>
    <version>REPLACE_WITH_COMPATIBLE_VERSION</version>
    <extensions>true</extensions>
    <configuration>
        <testMode>WEBTESTCLIENT</testMode>
        <testFramework>JUNIT5</testFramework>
        <baseClassForTests>
            com.example.orders.contract.ContractVerifierBase
        </baseClassForTests>
    </configuration>
</plugin>
~~~

Illustrative Gradle configuration:

~~~groovy
contracts {
    testMode = 'WEBTESTCLIENT'
}
~~~

Exact configuration must match your project's plugin version, base class declaration, and JUnit setup. Never paste placeholder `REPLACE_WITH_COMPATIBLE_VERSION` into a real project expecting Maven to resolve it.

### 6.1. Test Modes Are Not Interchangeable

| Test mode | Main characteristics | When to consider |
| --- | --- | --- |
| `WEBTESTCLIENT` | Generates tests for WebTestClient/RestAssuredWebTestClient without requiring an open server socket | WebFlux controller/HTTP boundary |
| `EXPLICIT` | Uses an HTTP client against a running real server (per plugin configuration) | When testing network and broader runtime layers |
| `MOCKMVC` | Spring MVC test stack | Spring MVC producers; not the default choice for pure WebFlux |

If you pick `EXPLICIT` without starting the server or configuring ports properly, you may hit `Connection refused`. If you pick `MOCKMVC` for pure WebFlux, tests may not match the producer's routing mechanism. Never switch test modes merely to hide fixture bugs.

## 7. Base Class for Reactive HTTP Contract Tests

Two main strategies exist: **web slice with Spring's real WebTestClient** or **standalone controller setup** for RestAssuredWebTestClient.

### 7.1. Web-Slice Base Class with @WebFluxTest

Example using Spring Boot's `@WebFluxTest` and Spring Framework's `@MockitoBean`:

~~~java
package com.example.orders.contract;

import com.example.orders.api.OrderController;
import com.example.orders.api.OrderView;
import com.example.orders.api.OrderQuery;
import io.restassured.module.webtestclient.RestAssuredWebTestClient;
import io.restassured.module.webtestclient.RestAssuredWebTestClientClient;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

import static org.mockito.BDDMockito.given;

@WebFluxTest(OrderController.class)
public abstract class ContractVerifierBase {

    @Autowired
    WebTestClient webTestClient;

    @MockitoBean
    OrderQuery orderQuery;

    @BeforeEach
    protected void setUp() {
        given(orderQuery.findById("ORD-123"))
            .willReturn(Mono.just(
                new OrderView("ORD-123", "CONFIRMED", 120000L)
            ));

        RestAssuredWebTestClient.useClient(
            RestAssuredWebTestClientClient.builder()
                .webTestClient(webTestClient)
                .build()
        );
    }

    @AfterEach
    protected void tearDown() {
        RestAssuredWebTestClient.resetClient();
    }
}
~~~

Using `useClient(...)`/`resetClient()` above relies on **modern REST Assured Spring WebTestClient APIs** supporting per-thread client binding, helpful when multiple tests use separate configurations. **Check the REST Assured version managed by Spring Cloud Contract in your project**: if those APIs are not available, use the compatible setup mechanism provided by that version—such as `standaloneSetup(...)` or the WebTestClient setup documented for that release. Do not adopt a newer API while ignoring version compatibility.

Key points:

1. `@WebFluxTest(OrderController.class)` tests the WebFlux slice; many service beans are not loaded and must be mocked or imported appropriately.
2. `@MockitoBean` provides a fake dependency whose methods return `Mono.just(...)` without async writes/subscriptions.
3. `@BeforeEach` prepares fixtures **before** generated tests run.
4. `RestAssuredWebTestClient.useClient(...)` connects generated test requests to the Spring-configured `WebTestClient`.
5. `@AfterEach` clears thread-local client bindings to prevent configuration leaks between tests.
6. The `public abstract` base class can be extended by generated tests per `baseClassForTests`.

**JUnit note:** JUnit 5 uses `@BeforeEach` and `@AfterEach`; older examples may use JUnit 4 `@Before`. Never copy annotations from another JUnit generation without adapting them.

### 7.2. Standalone Setup When Testing an Isolated Controller

REST Assured and Spring Cloud Contract also support a simpler setup form:

~~~java
import io.restassured.module.webtestclient.RestAssuredWebTestClient;
import org.junit.jupiter.api.BeforeEach;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.mock;

public abstract class ContractVerifierBase {

    private final OrderQuery orderQuery = mock(OrderQuery.class);

    @BeforeEach
    protected void setUp() {
        given(orderQuery.findById("ORD-123"))
            .willReturn(Mono.just(
                new OrderView("ORD-123", "CONFIRMED", 120000L)
            ));

        RestAssuredWebTestClient.standaloneSetup(
            new OrderController(orderQuery)
        );
    }
}
~~~

This snippet is **illustrative and requires your project's full imports/packages**. Standalone setup is fast and avoids loading a full Spring application context, yet may omit production security filters, controller advice, codecs, and custom web configurations. If contracts depend on those, use an appropriate context-based setup.

**Parallel execution note:** Static global setup like `standaloneSetup(...)` can affect other tests when running suites in parallel with differing configurations. When using multiple base classes or parallel execution, prefer per-thread client binding if supported, separate contexts, or intentionally constrain parallelism.

## 8. Connecting Reactive Repository Seeding to the Base Test

When using a **real integration-test database**, do not mock the repository and claim the full web-to-persistence path was verified. Still, seeding must follow a completed sequence of operations.

Base class skeleton example:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureWebTestClient
public abstract class ReactiveContractBase {

    @Autowired
    ReactiveOrderRepository repository;

    @Autowired
    WebTestClient webTestClient;

    @BeforeEach
    protected void prepareFixture() {
        Mono<Void> arrange = repository.deleteAll()
            .then(repository.save(
                new OrderEntity("ORD-123", "CONFIRMED", 120000L)
            ))
            .then();

        StepVerifier.create(arrange)
            .expectComplete()
            .verify(Duration.ofSeconds(5));

        // Choose the RestAssuredWebTestClient setup matching your version
        // before generated tests send HTTP requests.
    }
}
~~~

This snippet covers only preparation; imports, entity/repository types, database config, and REST Assured wiring must be completed for your project. **Do not simultaneously mock `OrderQuery` and seed the reactive repository** if the controller still uses the mock: database seeding would have no effect on HTTP responses, creating the illusion that persistence was tested when it was not.

### 8.1. Why Not Put deleteAll and save in Two Separate @BeforeEach Methods?

If two setup methods lack an explicit ordering relationship, execution order may differ from expectations, especially across inheritance or multiple extensions. A single pipeline:

~~~java
repository.deleteAll()
    .then(repository.save(order))
    .then()
~~~

guarantees **delete completes before save inside one subscription**, rather than depending on callback order or schedulers.

When multiple entity types depend on one another, compose order explicitly:

~~~java
Mono<Void> seed = customerRepository.save(customer)
    .then(orderRepository.save(order))
    .then();
~~~

In this example, the order is saved after the customer save finishes. If the schema has foreign keys, event handlers, or dependent data, **setup ordering must reflect those constraints**.

### 8.2. Avoid Wiping Shared Databases

`deleteAll()` is safe only when the test environment is **isolated and owned by the test**. If multiple tests or workers share a database, wiping everything creates an even bigger race.

Prefer:

- Dedicated test-suite databases/containers or isolated namespaces/schemas.
- Unique IDs per test case.
- Cleaning up only records created by the current test.
- Transaction/cleanup strategies verified with the reactive driver.
- Never running tests that mutate the same aggregate in parallel without solid isolation.

Do not assume `@Transactional` on a JUnit method automatically rolls back **every** asynchronous reactive operation; reactive transactions bind to Reactor Context and subscriptions, so understand your application's actual transaction boundaries.

## 9. Concurrency Pitfalls When Generated Tests Run in Parallel

JUnit 5 can execute tests in parallel depending on project configuration. Even when every test has its own `@BeforeEach`, shared data can still collide.

Consider two contracts:

- Test A requires `ORD-123` in state `CONFIRMED`.
- Test B requires `ORD-123` in state `CANCELLED`.

If both update the same table, outcomes depend on which test seeds first. One generated test can read data another test just overwrote.

### 9.1. Common Causes of Races

| Shared resource | Example | Risk mitigation |
| --- | --- | --- |
| Same database | Two tests update ID `ORD-123` | Distinct IDs or isolated databases/schemas |
| Same singleton mock | Test A overwrites stubbing of Test B | Scope mocks to matching context and lifecycle |
| Static client config | Test A mutates global `RestAssuredWebTestClient` setup | Per-test/per-thread client binding or limit parallelism |
| Shared Reactor sink | One test subscribes early, another emits | Dedicated sink/bus per scenario |
| Shared Kafka topic | Message from another test read by consumer test | Correlation keys, dedicated test topics/consumer groups |
| System clock | Response has varying `createdAt` | Fixed `Clock` or format matchers |
| Global cache | Stale cache entries affect reads | Controlled cache isolation/eviction |
| Random UUIDs | Inconsistent fixtures/stubs | Deterministic sample values or matchers |

### 9.2. Choosing a Strategy by Cost

1. For web contract tests verifying controller JSON: **mock the reactive service**.
2. For repository integration tests: isolated databases/schemas or uniquely keyed data.
3. For message integration tests: correlation IDs and explicit completion awaits.
4. If a resource cannot yet be isolated: temporarily limit parallel execution **for just that test group**, rather than disabling parallelism project-wide as a permanent crutch.

Never loosen a contract into an overly broad regex to turn tests green when the real failure is tests overwriting each other's data.

## 10. Asynchronous Events: Subscribers Must Be Ready Before the Trigger

A reactive HTTP request can trigger a side effect, such as publishing an `OrderConfirmed` event. If a test calls the endpoint and **only afterward subscribes** to a hot publisher, the event may already have been emitted before the subscriber was ready.

### Anti-Pattern

~~~java
webTestClient.post()
    .uri("/api/orders/ORD-123/confirm")
    .exchange()
    .expectStatus().isAccepted();

// If the publisher is hot with no replay, the event may already be gone.
StepVerifier.create(orderEvents.take(1))
    .expectNextMatches(e -> "ORD-123".equals(e.orderId()))
    .expectComplete()
    .verify(Duration.ofSeconds(3));
~~~

If `orderEvents` is a hot `Flux` with no history replay, a test subscribing after the action can **miss the event**. The test then flakes or always times out depending on scheduling.

### Better Arrangement

When a properly prepared event publisher is available, `StepVerifier` can subscribe **before** the trigger:

~~~java
Flux<OrderEvent> eventsForOrder = orderEvents
    .filter(e -> "ORD-123".equals(e.orderId()))
    .take(1);

StepVerifier.create(eventsForOrder)
    .then(() ->
        webTestClient.post()
            .uri("/api/orders/ORD-123/confirm")
            .exchange()
            .expectStatus().isAccepted()
    )
    .expectNextMatches(e -> "CONFIRMED".equals(e.status()))
    .expectComplete()
    .verify(Duration.ofSeconds(3));
~~~

Here the verifier activates the subscription before executing the action inside `then(...)`, with a bounded timeout. When the messaging pipeline uses a real broker, confirm the system subscription itself is active and correlated properly; merely having a subscription in the client test does not prove the broker consumer is ready.

### 10.1. Never Use Thread.sleep to Wait for Messages

~~~java
sendMessage();
Thread.sleep(2000);
assertThat(receivedMessages).hasSize(1);
~~~

This can fail on slow CI or pass falsely by catching messages from another test. Prefer awaiting **specific signals/conditions** with timeouts, correlation IDs, and direct payload assertions.

### 10.2. HTTP Contracts and Event/Message Testing Are Not the Same

An HTTP contract returning `202 Accepted` **does not prove** a message was published, the broker delivered it, or a consumer processed it. If the producer also has messaging contracts, verify message destinations, headers, and bodies separately; when side effects must be guaranteed, add integration tests at the proper layer.

## 11. Bounded Waits: Wait for Conditions, Not Guessed Durations

When setup relies on eventual consistency (e.g., writing to a database before data appears in a search index), completion of the `save(...)` publisher may not yet guarantee index queries return results.

A solid strategy specifies:

1. **Readiness condition:** e.g., query returns a record with status `CONFIRMED`.
2. **Maximum deadline:** e.g., 5–10 seconds, tuned to the test environment.
3. **Reasonable polling interval:** avoid tight spin loops that overload resources.
4. **Clear failure reporting:** print which condition remained unmet upon timeout.
5. **Test-owned data:** avoid confusing results with another test's records.

Example with a publisher polling status reactively:

~~~java
Mono<OrderView> waitUntilVisible = Mono.defer(
        () -> searchClient.findById("ORD-123")
    )
    .filter(order -> "CONFIRMED".equals(order.status()))
    .repeatWhenEmpty(repeat ->
        repeat.delayElements(Duration.ofMillis(100))
    )
    .timeout(Duration.ofSeconds(5));

StepVerifier.create(waitUntilVisible)
    .expectNextMatches(order -> "ORD-123".equals(order.orderId()))
    .expectComplete()
    .verify(Duration.ofSeconds(6));
~~~

This is an **illustrative pattern**: check `repeatWhenEmpty` signatures in your Reactor version and how `searchClient` signals errors vs. empty. Here `timeout(...)` prevents endless waiting; `Mono.defer(...)` creates a fresh query on each attempt.

**Avoid polling if the resource can emit a direct completion signal.** When an "index updated" confirmation event exists, awaiting that signal is clearer and lighter.

## 12. Testing Time-Based Logic with Virtual Time

Other tests may involve `delayElement`, `timeout`, or `retryWhen`. Waiting in real wall-clock time across all tests makes suites slow and unstable.

Project Reactor supports `StepVerifier.withVirtualTime(...)` for publishers using compatible schedulers. Example:

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofMinutes(5))
    )
    .expectSubscription()
    .thenAwait(Duration.ofMinutes(5))
    .expectNext(0L)
    .expectComplete()
    .verify(Duration.ofSeconds(2));
~~~

`Mono.delay(Duration.ofMinutes(5))` is created **inside the supplier** so the virtual scheduler is active before the publisher is built. The test verifies 5 virtual minutes of behavior without sleeping 5 real minutes.

### 12.1. Limits of Virtual Time

- Does not make databases, Kafka, Redis, HTTP servers, or external systems run on a virtual clock.
- Has no effect on sources using custom schedulers or system clocks outside Reactor's schedulers.
- When running virtual-time tests in parallel environments, know it can alter shared scheduler factories; isolate tests or follow Reactor best practices.
- If a publisher is constructed **before** virtual time is enabled, some timers may not be affected as intended.
- `verify(...)` still needs a timeout to prevent hanging tests.

Virtual time fits **unit tests of operators/time logic**. When contract tests must verify real HTTP responses, it is usually better to inject a fixed `Clock` or mock intentional delay logic rather than manipulating time across the entire web context.

## 13. Mandatory Blocking Resources: Must Be Isolated from the Event Loop

An application may need to call legacy blocking libraries like JDBC or classic file I/O. In reactive code, the standard approach is offloading blocking work to a suitable scheduler, such as `Schedulers.boundedElastic()`:

~~~java
Mono<LegacyResult> result = Mono
    .fromCallable(() -> legacyClient.load("ORD-123"))
    .subscribeOn(Schedulers.boundedElastic());
~~~

Meaning:

- `fromCallable(...)` defers invoking the blocking library until subscription.
- `subscribeOn(boundedElastic())` shifts blocking execution to a thread pool suited for it rather than the event loop.
- This prevents event-loop starvation, yet **does not turn a blocking library into a non-blocking one** and does not eliminate timeout or connection-exhaustion risks.

For test fixtures, prefer reactive clients/databases or mocks. If a setup step must call a blocking API, run it on the test setup thread outside the event loop with clear timeouts and cleanup. Never sprinkle `boundedElastic()` indiscriminately onto every publisher: it obscures design and can mask producer architecture bugs.

### 13.1. Spotting Unintended Blocking

Watch for these signs:

- `IllegalStateException: block()/blockFirst()/blockLast() are blocking ...`.
- Request timeouts under moderate concurrency despite simple logic.
- CPU or event loop becomes unresponsive to other tasks during long I/O.
- Tests fail only when running the full suite, passing when run individually.
- A controller method calls `Future.get()`, `Thread.sleep(...)`, or synchronous database APIs.

You can add BlockHound in suitable tests to catch blocking calls on non-blocking threads, provided configuration and library compatibility are verified; do not treat it as a prerequisite for writing contracts.

## 14. Reading Generated Contract Tests to Isolate Reactive Failures

Contract Verifier generates requests and assertions from the DSL. When a test fails, distinguish **actual HTTP behavior bugs** from **data-preparation races**.

Example failure:

~~~text
Contract: get_confirmed_order
Expected status: 200
Actual status: 404
~~~

Investigate in order:

1. Did the generated test call `GET /api/orders/ORD-123` properly?
2. Does the test mode match `WEBTESTCLIENT` and extend the right base class?
3. Did `@BeforeEach` execute?
4. Was the reactive repository fixture **subscribed to and completed** before the request?
5. Is the test sharing IDs/databases with another test?
6. Did controller/serializer changes cause the real producer to stop meeting the contract?

If a test passes in isolation but fails in parallel, suspect **shared state or sequencing**. If it fails consistently after the producer changed a path, field, or status, investigate a **breaking change**.

### 14.1. Quick Diagnostic Table

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Intermittent `404` | Seeding via `subscribe()` let request run early | Await seed completion or mock `Mono.just(...)` |
| Tests fail in parallel | Shared IDs, caches, sinks, DB, or static client | Isolate fixtures and client configuration |
| `IllegalStateException` about blocking | Calling `block()` on an event-loop thread | Compose publishers or move blocking to right scheduler |
| Test hangs | Publisher never completes or verifier lacks timeout | Add timeouts; inspect lifecycle and errors |
| `onError` in setup ignored | `subscribe()` lacks error handling/verification | Use `StepVerifier` and error assertions |
| Fixture never appears | Only created `Mono`, never subscribed | Execute and verify the pipeline |
| Fixture disappears | `deleteAll()` and `save()` subscribed independently | Compose sequentially with `then(...)` |
| `Connection refused` | Using explicit mode without running server | Configure server/port or appropriate mode |
| Context load failure | `@WebFluxTest` missing mocks/imports or wrong dependencies | Inspect bean graph and annotations |
| Wrong response body types | JSON serializer/DTO differs from contract | Align producer/schema with commitment |
| HTTP `200` but missing message | HTTP contracts do not verify async side effects | Add messaging/integration tests |
| Stub exists yet consumer test fails | Wrong stub version or request matcher mismatch | Check Stub Runner and runtime requests |
| Green build with 0 tests | Plugin or runner skipped generated tests | Check source paths and executed test count |

### 14.2. How to Report a Race Condition Helpfully

Instead of writing "CI is flaky," include:

- Which contract/source test failed and its reproduction rate.
- Actual request/response, status, and body.
- Which setup publishers ran, when, and how completion was awaited.
- Whether tests ran in parallel or shared a database/topic/client.
- Log timeline `seed started → seed completed → request sent`.
- The sequencing fix and repeated run results afterward.

That lets the team separate **test infrastructure bugs** from **consumer-breaking API changes**.

## 15. Testing Slow HTTP Responses and Client Timeouts

With `WebTestClient`, response-check timeouts can stem from:

- The producer failing to emit `onNext` or `onComplete`.
- Blocking operations stalling the event loop.
- Unready fixtures causing requests to wait on dependencies.
- Downstream connection timeouts.
- A test client `responseTimeout` configured too short.

A direct `WebTestClient` can configure its response timeout in tests:

~~~java
WebTestClient client = WebTestClient
    .bindToController(new OrderController(orderQuery))
    .configureClient()
    .responseTimeout(Duration.ofSeconds(5))
    .build();
~~~

This setting is only a **test-client timeout**; it does not fix producer logic. If the service has latency/SLA commitments, it needs dedicated performance tests and realistic environment conditions; never equate a single HTTP contract test with a performance test.

## 16. Producer Verification, Stubs, and CI: Three Different Kinds of Synchronization

~~~mermaid
flowchart LR
    C["Groovy/YAML contract"] --> G["Generate producer tests"]
    G --> S["Base setup: fixture ready"]
    S --> H["WebTestClient calls WebFlux producer"]
    H --> A{"Assertions match?"}
    A -- "No" --> F["Block build"]
    A -- "Yes" --> P["Producer verification passes"]
    C --> M["Generate stub mappings"]
    P --> R["Publish versioned stub"]
    M --> R
    R --> U["Consumer tests via Stub Runner"]
~~~

Distinguish three synchronizations:

1. **Producer fixture synchronization:** ensuring data/mocks/buses are ready before requests.
2. **HTTP response synchronization:** generated tests await responses and assert per test mode; never insert `Thread.sleep`.
3. **Consumer/stub synchronization:** consumer sends requests to the stub and checks responses; whether the producer uses reactive or MVC internally does not give stubs the database fixture races of the real producer.

**Stubs do not run the producer's reactive repository.** Hence consumer tests with Stub Runner can pass even when producer verification fails due to fixture races or producer API changes. Both test suites complement each other; run the pipeline so stubs publish only after producer tests pass.

### 16.1. Illustrative CI Commands

With Maven on a project configured with the Spring Cloud Contract plugin:

~~~bash
./mvnw -B clean verify
~~~

With Gradle on a project configured with the plugin and test tasks:

~~~bash
./gradlew clean build
~~~

Never assume `BUILD SUCCESS` is enough. CI must verify:

- Groovy/YAML contracts are discovered properly.
- Generated producer tests are generated, compiled, and **executed**.
- `WEBTESTCLIENT` test mode and base class match the WebFlux stack.
- Fixture setup completes, or mock publishers are deterministic before requests.
- Timeouts are finite and isolation is explicit.
- Race-induced `404` errors are never masked by loosening contracts.
- Stub artifacts are published under the exact verified producer version.
- Consumer CI uses Stub Runner to test the scenarios consumers need.

## 17. Practice Exercise: Fixing Flaky Tests for Inventory Service

Suppose `Inventory Service` uses Spring WebFlux + R2DBC. The consumer calls:

~~~http
GET /api/inventory/SKU-100 HTTP/1.1
Accept: application/json
~~~

Expected response:

~~~json
{
  "sku": "SKU-100",
  "quantity": 8,
  "available": true
}
~~~

### 17.1. Groovy Contract

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('inventory_get_available')

    request {
        method GET()
        urlPath('/api/inventory/SKU-100')
        headers {
            accept(applicationJson())
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-100',
            quantity: 8,
            available: true
        )
    }
}
~~~

### 17.2. Part A — Spot the Race in the Base Class

Broken setup snippet:

~~~java
@BeforeEach
protected void setUp() {
    inventoryRepository.deleteAll().subscribe();
    inventoryRepository.save(
        new InventoryEntity("SKU-100", 8, true)
    ).subscribe();
}
~~~

Identify three problems:

1. Two independent subscriptions do not guarantee `deleteAll` finishes before `save`.
2. JUnit does not wait for either publisher to finish before sending the generated request.
3. Tests running in parallel can wipe each other's data.

### 17.3. Part B — Fix with a Completion-Verified Pipeline

Hint:

~~~java
@BeforeEach
protected void setUp() {
    Mono<Void> arrange = inventoryRepository.deleteAll()
        .then(inventoryRepository.save(
            new InventoryEntity("SKU-100", 8, true)
        ))
        .then();

    StepVerifier.create(arrange)
        .expectComplete()
        .verify(Duration.ofSeconds(5));
}
~~~

After ensuring the test environment **has an isolated database**, add a check verifying the record can be read back. If a database is shared, switch from `deleteAll` to unique test IDs / selective cleanup.

### 17.4. Part C — Replace with a Mock for the Web Slice

If the goal is solely testing HTTP mapping, JSON, and status, create `@WebFluxTest(InventoryController.class)`, mock `InventoryQuery`, and return:

~~~java
given(inventoryQuery.findBySku("SKU-100"))
    .willReturn(Mono.just(
        new InventoryView("SKU-100", 8, true)
    ));
~~~

Comparison:

| Strategy | Benefit | What remains unverified |
| --- | --- | --- |
| Real reactive repository, completion-verified seed | Exercises real data read/write paths more thoroughly | Does not automatically cover every downstream/broker |
| Mock `Mono.just(...)` in web slice | Fast, deterministic, low race risk | Does not test real persistence |

### 17.5. Part D — Test Parallel Execution Impact

Create two tests with **two distinct SKUs**, or use isolated test databases/schemas. Run a group of tests repeatedly and verify:

- No `404` appears randomly.
- No dependency on `Thread.sleep` remains.
- Intentionally omitting `subscribe`/`StepVerifier` fails setup validation as expected.
- Changing `quantity` from a number to a String is caught by generated contract assertions if types are protected.
- Changing producer path `/api/inventory/SKU-100` to `/api/stock/SKU-100` without keeping the old path causes contract tests to catch the real breaking change.

### 17.6. Part E — Practice with Virtual Time

Write a unit test for an operator supposed to wait 30 seconds before emitting `READY`, using `StepVerifier.withVirtualTime(...)` instead of `Thread.sleep(30000)`. Explain why the publisher must be built inside the supplier and why virtual time cannot replace database fixture seeding.

### 17.7. Self-Assessment Questions

1. Why might `repository.save(entity)` not have executed yet?
2. Why can `subscribe()` inside `@BeforeEach` cause races?
3. Does `StepVerifier.verify(Duration)` "block"? Which thread is allowed to run it?
4. Why is calling `block()` inside a WebFlux controller dangerous?
5. When is `Mono.just(...)` a better fixture strategy than a real reactive database?
6. Does an HTTP `202 Accepted` test prove a message was published?
7. Why is `deleteAll()` dangerous when tests share a database?
8. When parallel tests use `RestAssuredWebTestClient`, which configuration pattern should be avoided?
9. How do you distinguish a `404` caused by unready fixtures from a `404` caused by a removed producer endpoint?
10. Why do consumer tests with Stub Runner not replace producer verification?

**Hints:** Reactor publishers are typically lazy; detached `subscribe()` does not guarantee completion; `StepVerifier.verify(...)` waits with a timeout on the test thread; event loops must stay non-blocking; mocks suit web slices; messages need dedicated tests; isolation solves races; inspect generated requests, setup, and responses before concluding a breaking change occurred.

## 18. Checklist Before Declaring Reactive Contract Tests Stable

- [ ] DSL accurately describes the HTTP method, path, headers, and response consumers use.
- [ ] Producer uses a WebFlux-compatible test mode, e.g. `WEBTESTCLIENT`, with a matching base class.
- [ ] No `block()` or `Thread.sleep` appears inside request-handling pipelines on the event loop.
- [ ] No fire-and-forget `subscribe()` appears in `@BeforeEach` to seed request-required data.
- [ ] Fixture preparation pipelines are ordered and verified to complete.
- [ ] Wait points have finite timeouts; no infinite polling or sleep.
- [ ] Reactive dependencies are mocked with deterministic publishers when tests only need the web slice.
- [ ] Reactive databases/test resources are isolated; no `deleteAll` on shared data.
- [ ] Parallel tests do not mutate the same IDs, mocks, sinks, caches, or static client configs.
- [ ] Subscribers observing hot publishers are ready before triggering side effects.
- [ ] Correlation IDs are used when reading messages/events from shared resources.
- [ ] Virtual time is used only where supported by operators and schedulers.
- [ ] Generated tests actually execute; avoid green builds with 0 tests.
- [ ] Setup bugs are distinguished from real response mismatches / breaking changes.
- [ ] Stubs publish only after producer verification passes, and consumers run Stub Runner with the right version.
- [ ] Broker delivery, idempotency, latency, and security properties have supplementary tests at appropriate layers.

## 19. References

- [Spring Cloud Contract — WebFlux with WebTestClient](https://docs.spring.io/spring-cloud-contract/reference/project-features-flows/feature-webflux.html): `testMode=WEBTESTCLIENT` configuration and WebFlux base classes.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): testing WebFlux via controllers, application contexts, or real servers.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, wait timeouts, virtual time, and signal verification.
- [REST Assured — Spring WebTestClient](https://rest-assured.io/docs/spring/web-test-client/): setting up `RestAssuredWebTestClient` and managing clients under parallel execution.
- [Spring Cloud Contract — HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html): declaring methods, paths, and response bodies.
- [Spring Cloud Contract — Reference Documentation](https://docs.spring.io/spring-cloud-contract/reference/): producer verification plugins, stubs, and build lifecycles.

**Key takeaway:** In reactive testing, **starting work does not mean the work is finished**. Detached `subscribe()` in setup creates races; `Thread.sleep` only guesses timing; `block()` on the event loop can break the application. **Compose publishers in the right order**, await bounded completion signals **on the test thread** when needed, isolate parallel test data, or mock dependencies with `Mono.just(...)` for web slices. Only then should generated producer tests send requests and verify HTTP contracts before publishing stubs to consumers.
