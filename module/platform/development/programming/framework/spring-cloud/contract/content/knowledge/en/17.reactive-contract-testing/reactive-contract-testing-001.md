# Distinguishing HTTP Contracts from Reactive Implementation

When a service migrates from **Spring MVC** to **Spring WebFlux**, controller code may change its return type from `OrderView` to `Mono<OrderView>` or `Flux<OrderEvent>`. However, a consumer usually **does not invoke the controller's Java method**: the consumer sends an **HTTP request** and observes the **status, headers, body, errors, and how the connection terminates**. Therefore, you must distinguish the **HTTP contract** from the **reactive programming model** inside the producer.

This lesson belongs to the **Reactive Testing** chapter of the **SPRING_CLOUD_CONTRACT** module. Spring Cloud Contract lets you specify HTTP or messaging interactions using a **Groovy/YAML DSL**, generate **producer** verification tests, package **stubs**, and then use **Stub Runner** in **consumer** tests and CI to detect incompatible API changes. The focus is on keeping the **HTTP commitment stable** when the implementation switches to WebFlux/Reactor, using **WebTestClient** to verify the producer, and understanding the limits of standard HTTP contracts when dealing with streaming, backpressure, or timeouts.

## 1. Contracts Describe Observable Outcomes

For example, **Order Service** provides an API for **Billing Service**:

~~~http
GET /api/orders/42
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"status":"PAID"}
~~~

The contract defines **which requests are accepted** and **which responses must be returned**; how Order Service queries data, manages threads, and orchestrates asynchronous execution is an implementation responsibility.

| Aspect | Part of the HTTP contract? | Example |
| --- | --- | --- |
| Method, path, query, request headers/body | **Yes** | `GET /api/orders/42`, `Accept` header. |
| Response status, headers, JSON, and important values | **Yes** | `200`, `application/json`, `status=PAID`. |
| Errors for missing resources, missing authentication, insufficient permissions | **Yes if committed** | `404`, `401`, `403`, and error payload. |
| Media type, data framing/packaging | **Yes** | JSON array, SSE, or NDJSON. |
| Returning `Mono`, `Flux`, or a synchronous Java object | **No** | Internal method signature of the controller. |
| Using JPA, R2DBC, WebClient, or JDBC | **No** | Storage technology / downstream service client. |
| Which `subscribeOn`, `publishOn`, or scheduler is used | **No** | Reactor execution policy. |
| Blocking calls, thread limits, internal backpressure | **Not automatically** | Requires separate architecture and performance testing. |

**Do not put `Mono` or `Flux` types into the body of a normal HTTP contract.** Those are not values transmitted over the wire. A consumer can be written in Java, JavaScript, Go, or still use Spring MVC; it only relies on the agreed-upon HTTP protocol.

## 2. Comparing Synchronous and Reactive Controllers

### 2.1. Spring MVC

~~~java
@RestController
@RequestMapping("/api/orders")
class MvcOrderController {

    @GetMapping("/{id}")
    ResponseEntity<OrderView> getOrder(@PathVariable long id) {
        if (id == 42L) {
            return ResponseEntity.ok(new OrderView(42L, "PAID"));
        }
        return ResponseEntity.notFound().build();
    }
}

record OrderView(long id, String status) {}
~~~

In the MVC example, the handler directly computes a `ResponseEntity<OrderView>`; Spring converts the result into an HTTP response.

### 2.2. Spring WebFlux

~~~java
@RestController
@RequestMapping("/api/orders")
class ReactiveOrderController {
    private final OrderLookup orders;

    ReactiveOrderController(OrderLookup orders) {
        this.orders = orders;
    }

    @GetMapping("/{id}")
    Mono<ResponseEntity<OrderView>> getOrder(@PathVariable long id) {
        ResponseEntity<OrderView> notFound =
                ResponseEntity.notFound().build();

        return orders.findById(id)
                .map(ResponseEntity::ok)
                .defaultIfEmpty(notFound);
    }
}

record OrderView(long id, String status) {}

interface OrderLookup {
    Mono<OrderView> findById(long id);
}
~~~

In WebFlux, `findById` returns a `Mono<OrderView>` publisher, which can emit one result, complete empty, or error. `map` transforms a found result into HTTP 200; `defaultIfEmpty` **explicitly** maps the missing-order case into HTTP 404. What Billing observes **does not differ** from the MVC example as long as both return the same status, headers, and body.

If the controller is changed to:

~~~java
@GetMapping("/{id}")
Mono<OrderView> getOrder(@PathVariable long id) {
    return orders.findById(id);
}
~~~

then `Mono.empty()` is no longer explicitly mapped to `404`; the application may return a successful response with no body, depending on how the WebFlux handler is configured. **An empty publisher does not automatically mean "resource not found" in HTTP.** When the API commits to 404, you must handle it explicitly with `ResponseEntity.notFound()` or an appropriate `ResponseStatusException`.

This shows that a very small change in the Reactor pipeline **can break the contract**, whereas replacing the entire implementation while preserving the HTTP response **does not necessarily break the contract**.

## 3. Mono and Flux Do Not Alone Determine HTTP Semantics

| Implementation approach | Internal meaning | What the HTTP consumer can observe |
| --- | --- | --- |
| `Mono<OrderView>` emits one item | Publisher containing a single result. | Usually a single JSON object when using `application/json`. |
| `Mono.empty()` | Completes without emitting an item. | May be a response with no body; 404 requires explicit mapping. |
| `Mono.error(exception)` | Pipeline terminates with an error. | HTTP status/body depends on the exception handler/mapping. |
| Finite `Flux<OrderView>`, `application/json` | Emits multiple items. | May be written as a single JSON array. |
| `Flux<?>`, `text/event-stream` | Emits events over time. | SSE streaming; the connection may remain open long-term. |
| `Flux<?>`, `application/x-ndjson` | Emits consecutive JSON records. | Independent JSON lines, not a JSON array. |
| `delayElements`, slow publisher | Data arrives late. | May cause consumer timeout; timeouts are not necessarily checked by body contracts. |

**Warning:** a method returning `Mono` is not guaranteed to perform non-blocking I/O. Conversely, an endpoint using `Flux` does not automatically become SSE. The media type and encoder/response configuration determine how data is transmitted over HTTP.

## 4. Groovy DSL Contracts Do Not Need to Mention Reactor

Create `src/test/resources/contracts/orders/get_order.groovy` in the producer:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

[
    Contract.make {
        name 'shouldReturnPaidOrder'
        description 'Order 42 exists, status PAID'

        request {
            method 'GET'
            url '/api/orders/42'
            headers {
                header('Accept', 'application/json')
            }
        }

        response {
            status 200
            headers {
                contentType(applicationJson())
            }
            body(id: 42, status: 'PAID')
        }
    },
    Contract.make {
        name 'shouldReturn404WhenOrderMissing'
        description 'Order 999 does not exist'

        request {
            method 'GET'
            url '/api/orders/999'
            headers {
                header('Accept', 'application/json')
            }
        }

        response {
            status 404
        }
    }
]
~~~

Both contracts verify **HTTP behavior**:

1. `GET /api/orders/42` must return 200 and JSON with `id=42`, `status=PAID`.
2. `GET /api/orders/999` must return 404.

Having two scenarios in one Groovy file **does not** turn them into a combined check: the script returns a list of two separate `Contract.make` definitions; the plugin must load and generate tests for **both**.

If you need to verify an error body (for example `code=ORDER_NOT_FOUND`), add headers and a response body to the 404 contract. Checking only status 404 in a consumer stub test can easily produce a false pass when WireMock returns 404 because the request **did not match any mapping**.

### 4.1. Equivalent Contracts in YAML

For teams using the YAML DSL, the success case:

~~~yaml
description: Order 42 exists, status PAID
request:
  method: GET
  url: /api/orders/42
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: 42
    status: PAID
~~~

The not-found case is placed in another YAML file:

~~~yaml
description: Order 999 does not exist
request:
  method: GET
  url: /api/orders/999
  headers:
    Accept: application/json
response:
  status: 404
~~~

Within a single build, **keep only one set—either Groovy or YAML—as the active contract source** for the same scenario. Loading both equivalent definitions simultaneously can easily produce duplicate generated tests and stub mappings.

## 5. Preparing a WebFlux Producer with a Deterministic Fixture

Example Java 17+ project with `spring-boot-starter-webflux` and a compatible Spring Cloud Contract Verifier.

The application:

~~~java
package com.acme.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

A service returning stubbed data so the tests are reproducible:

~~~java
package com.acme.orders;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class InMemoryOrderLookup implements OrderLookup {
    @Override
    public Mono<OrderView> findById(long id) {
        if (id == 42L) {
            return Mono.just(new OrderView(42L, "PAID"));
        }
        return Mono.empty();
    }
}
~~~

The WebFlux controller and the `OrderView`, `OrderLookup` types use the code from section 2.2, with the corresponding Spring Web/`ResponseEntity` and Reactor imports added. An in-memory fixture helps test **HTTP communication**, not prove R2DBC, database behavior, or real non-blocking performance. For a real producer, use a test-environment repository/fixture, potentially paired with Testcontainers and migrations.

**Dependency note:** adding both `spring-boot-starter-web` and `spring-boot-starter-webflux` can cause Spring Boot to choose a Servlet/MVC application by default. To practice WebFlux, use the reactive stack explicitly and avoid thinking tests are running on WebFlux when the test context is actually MVC.

## 6. Choosing WEBTESTCLIENT for Contract Verifier

To have generated producer tests invoke WebFlux handlers, choose a compatible test mode. In Spring Cloud Contract, **`WEBTESTCLIENT`** is an option designed for WebFlux. Maven plugin example:

~~~xml
<plugin>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-contract-maven-plugin</artifactId>
    <version>4.1.5</version>
    <extensions>true</extensions>
    <configuration>
        <testFramework>JUNIT5</testFramework>
        <testMode>WEBTESTCLIENT</testMode>
        <baseClassForTests>com.acme.orders.ContractTestBase</baseClassForTests>
    </configuration>
</plugin>
~~~

This is a **POM configuration snippet**, not a complete POM. `4.1.5` is an **example 4.1.x version**, not a requirement to use that exact version; the plugin and dependencies must match your project's Spring Boot/Spring Cloud release train.

Illustrative dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-contract-verifier</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

`JUNIT5` is the **test framework** that runs the generated tests; `WEBTESTCLIENT` is the **request execution mode**. `.groovy` contracts can still generate Java/JUnit Jupiter tests; switching to Spock/Groovy is not required.

### 6.1. Base Test Class for WebFlux

A reference setup:

~~~java
package com.acme.orders;

import io.restassured.module.webtestclient.RestAssuredWebTestClient;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

@SpringBootTest(
    classes = OrderApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureWebTestClient
public abstract class ContractTestBase {
    @Autowired
    private ApplicationContext context;

    @BeforeEach
    void setUp() {
        RestAssuredWebTestClient.applicationContext(context);
    }
}
~~~

This class initializes the WebFlux application context and wires Rest Assured WebTestClient to the context so generated tests can invoke endpoints. **The exact setup API depends on the Spring Cloud Contract/Rest Assured version**; inspect the generated test to verify which client it actually uses and whether it extends the base class. Do not edit generated test files directly, as the next generation run may overwrite them.

### 6.2. Comparing Test Modes

| Test mode | Tool / target | When to use |
| --- | --- | --- |
| `MOCKMVC` | MockMvc tests Spring MVC/Servlet inside the test context. | Spring MVC producers, not the default for WebFlux. |
| `WEBTESTCLIENT` | WebTestClient/Rest Assured WebTestClient tests WebFlux handlers. | WebFlux producers, when the mode is supported by the release train. |
| `EXPLICIT` | Generated tests send HTTP requests to a real server at a host/port. | When you need to test a real HTTP server/transport in the test environment. |

The `EXPLICIT` mode can be used with `@SpringBootTest(webEnvironment = RANDOM_PORT)` and an HTTP client pointing to the runtime port. **Do not just replace `WEBTESTCLIENT` with `EXPLICIT` while keeping the same base test**: how the server binds and starts is different. Testing TLS, gateways, HTTP/2, or network timeouts may require separate integration tests.

## 7. Generated Producer Tests Should Verify HTTP, Not Reactor Operators

With the described contracts and proper configuration, a producer build performs:

1. Loads the Groovy or YAML contracts.
2. Generates tests using `JUNIT5` and `WEBTESTCLIENT`.
3. Extends the base test, initializes the Spring context and HTTP test client.
4. Calls `GET /api/orders/42`, verifying `200` and body `{"id":42,"status":"PAID"}`.
5. Calls `GET /api/orders/999`, verifying `404`.

In a Maven producer configured with Contract Verifier:

~~~shell
mvn clean verify
~~~

Inspect the **generated test code**, Surefire reports, and the number of executed tests. A `BUILD SUCCESS` line with 0 generated tests provides no contract verification value. A working contract test must catch an intentional mistake in the implementation.

| Change in the WebFlux producer | Behavior seen by the consumer | Expected result |
| --- | --- | --- |
| `status` changed from `PAID` to `PENDING` | JSON differs from the contract. | Generated test **FAILS**. |
| Removed mapping of `Mono.empty()` to 404 | Missing-order endpoint may return a different status. | Test for case 999 **FAILS**. |
| Changed route to `/orders/{id}` | Old path fails. | Generated test **FAILS**. |
| Replaced `map` with an equivalent implementation, HTTP unchanged | No observable difference. | Generated test **PASSES**. |

This is a key advantage: contracts protect **behavior** when the team refactors architecture, without forcing the code to use a specific operator.

### 7.1. Hand-Written WebTestClient Test for Comparison

In a Spring Boot WebFlux test configured with `WebTestClient`:

~~~java
@Autowired
WebTestClient webTestClient;

@Test
void shouldReadPaidOrder() {
    webTestClient.get()
        .uri("/api/orders/42")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.id").isEqualTo(42)
        .jsonPath("$.status").isEqualTo("PAID");
}

@Test
void missingOrderIs404() {
    webTestClient.get()
        .uri("/api/orders/999")
        .exchange()
        .expectStatus().isNotFound();
}
~~~

This snippet illustrates **the assertions needed**, not the plugin's verbatim generated test code. A passing hand-written test does not substitute for ensuring **generated producer tests actually run** against the stored contract sources.

## 8. Consumer Using WebClient and Stub Runner

On the Billing side, the client can use `WebClient`; whether the producer is implemented in MVC or WebFlux **does not change the HTTP request Billing must send**.

~~~java
package com.acme.billing;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component
public class OrderGateway {
    private final WebClient client;

    public OrderGateway(WebClient.Builder builder,
                        @Value("${orders.base-url}") String baseUrl) {
        this.client = builder.baseUrl(baseUrl).build();
    }

    public Mono<OrderView> getOrder(long id) {
        return client.get()
            .uri("/api/orders/{id}", id)
            .retrieve()
            .bodyToMono(OrderView.class);
    }

    public record OrderView(long id, String status) {}
}
~~~

The `getOrder` method returns `Mono` because **the consumer chose to use WebClient**, not because the contract requires that Java type.

After producer verification passes, the producer packages a versioned `stubs` artifact, for example `com.acme:order-service:1.0.0:stubs`. The consumer can write a test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = "orders.base-url=http://localhost:8089")
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs:8089",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class OrderGatewayContractTest {
    @Autowired
    private OrderGateway orders;

    @Test
    void readsPaidOrder() {
        StepVerifier.create(orders.getOrder(42))
            .assertNext(order -> {
                assertThat(order.id()).isEqualTo(42);
                assertThat(order.status()).isEqualTo("PAID");
            })
            .verifyComplete();
    }

    @Test
    void handles404() {
        StepVerifier.create(orders.getOrder(999))
            .expectError(WebClientResponseException.NotFound.class)
            .verify();
    }
}
~~~

This is an illustrative test; the project must declare Stub Runner, WebClient, Spring Boot Test, `reactor-test`, and AssertJ. With `LOCAL`, the stub artifact must be installed into local Maven before running consumer tests; in standalone CI machines use `REMOTE`, `repositoryRoot`, and the appropriate access credentials.

**Stubs do not run the producer's reactive implementation**: they only simulate HTTP responses from the contract. Consumer tests ensure WebClient sends the right request and handles the body/status properly. They **cannot replace generated producer tests**, because the real producer itself may have drifted from the contract.

## 9. Streaming: Where HTTP Contracts Need More Detail

Not every reactive endpoint is streaming. A finite `Flux<OrderView>` with media type `application/json` can be serialized into a complete JSON array, whereas `text/event-stream` and `application/x-ndjson` represent a **streaming** data transfer protocol.

| Sample endpoint | Media type | What the consumer needs to understand |
| --- | --- | --- |
| `GET /api/orders` returning a finite list | `application/json` | A single JSON array; check ordering if committed by the API. |
| `GET /api/orders/42/events` | `text/event-stream` | Stream of SSE events, may arrive incrementally, connection may be long-lived. |
| `GET /api/orders/feed` | `application/x-ndjson` | Line-delimited JSON objects; not a single JSON array. |

SSE handler example:

~~~java
@GetMapping(
    value = "/api/orders/42/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
Flux<OrderEvent> events() {
    return Flux.just(
        new OrderEvent("CREATED"),
        new OrderEvent("PAID")
    );
}

record OrderEvent(String type) {}
~~~

A WebTestClient test can verify two finite events:

~~~java
Flux<OrderEvent> events = webTestClient.get()
    .uri("/api/orders/42/events")
    .accept(MediaType.TEXT_EVENT_STREAM)
    .exchange()
    .expectStatus().isOk()
    .returnResult(OrderEvent.class)
    .getResponseBody();

StepVerifier.create(events.take(2))
    .assertNext(e -> assertThat(e.type()).isEqualTo("CREATED"))
    .assertNext(e -> assertThat(e.type()).isEqualTo("PAID"))
    .expectComplete()
    .verify(Duration.ofSeconds(3));
~~~

This code snippet is only the **test body**, assuming imports, WebTestClient, AssertJ, and Reactor Test are already present. The three-second deadline is an **example limit**, not an SLA. For real streams, you may need to protect **event IDs, ordering, framing, reconnects, heartbeats, timeouts, cancellation, and mid-stream error handling**.

**A static HTTP JSON body contract cannot automatically verify all behaviors of SSE/NDJSON**, especially infinite streams. Check the DSL/plugin capabilities of your version and add appropriate streaming integration tests; do not assume Stub Runner fully simulates timing, backpressure, and stream lifecycle.

## 10. Reactive Properties to Test Outside the Contract

### 10.1. Non-blocking

A method can return `Mono` and still use blocking I/O:

~~~java
Mono<OrderView> find(long id) {
    return Mono.fromCallable(() -> blockingRepository.findById(id));
}
~~~

If blocking I/O runs on the event loop, throughput and latency can degrade even though all contract tests **PASS**. Perform architecture reviews, use blocking-detection tools, or run concurrency/load tests. Even if blocking I/O is offloaded to `boundedElastic`, you still need to consider overhead and resource limits.

### 10.2. Backpressure

Backpressure allows a subscriber to request the amount of data a publisher emits under the Reactive Streams specification. An HTTP contract describing a finite JSON body does not automatically test **request(n)**, buffer overflow, memory pressure, or slow client read rates. Verify these with Reactor tests, streaming integration tests, and appropriate operational metrics.

### 10.3. Timeout, Retry, and Cancellation

A stub returning `200` immediately does not prove WebClient handles **timeouts, retries, 5xx responses, or connection drops** correctly. For those requirements, consumer tests should use stubs with explicitly configured delays/errors, `StepVerifier` or virtual time where appropriate, and dedicated network-environment tests when needed.

Layering principle: **Contract Verifier checks communication commitments**, while **unit/integration/performance tests** verify reactive properties that HTTP status/body cannot adequately express.

## 11. Reactive Error Handling Can Alter the HTTP Contract

WebFlux lets you map missing data to an HTTP error:

~~~java
return orders.findById(id)
    .switchIfEmpty(Mono.error(
        new ResponseStatusException(HttpStatus.NOT_FOUND)));
~~~

Or use `Mono<ResponseEntity<OrderView>>` as in section 2.2. Regardless of the implementation, when the contract requires `404`, the generated test must verify it.

Conversely, adding an error-swallowing operator like:

~~~java
.onErrorReturn(new OrderView(0L, "UNKNOWN"))
~~~

can turn an error case into a successful response with placeholder data. This is **no longer an internal refactor** if the HTTP status/body changes. Likewise, `onErrorResume`, `onErrorComplete`, or `retryWhen` can change the status, body, timing, or when the response finishes; you must review observable impacts.

## 12. Fixtures and State in Reactive Producer Tests

A contract test is only valid if the data needed by the producer **is already ready before the HTTP request is sent**. With reactive repositories, creating a `Publisher` does not automatically execute the write operation.

| Risk | Mitigation |
| --- | --- |
| `repository.save(...)` is called without subscribing/awaiting. | Wait for setup publishers to complete during test lifecycle, with a clear deadline. |
| Test uses an uncommitted transaction; HTTP request runs elsewhere. | Seed committed data visible to the handler. |
| Multiple tests mutate ID 42 concurrently. | Isolated database/schema/keys or controlled fixture reset. |
| Cache still holds data from a previous test. | Reset caches or isolate keys. |
| Test uses `Thread.sleep` to wait for side effects. | Use deterministic conditional/timeout publisher waiting. |
| Time/schedulers make tests flaky. | Fix `Clock` and use virtual time at the appropriate layer. |

Example **base test snippet** when using a Spring Data reactive repository:

~~~java
@BeforeEach
void prepareFixture() {
    StepVerifier.create(
        repository.deleteAll()
            .then(repository.save(new OrderEntity(42L, "PAID")))
    )
    .expectNextCount(1)
    .verifyComplete();
}
~~~

This snippet illustrates the idea: the fixture must **be executed and completed** before generated tests run. It does not replace proper database, repository, entity, or timeout configuration. `deleteAll()` should only be used with an isolated test database, never on data shared across tests or real environments.

## 13. CI Protecting Contracts During MVC-to-WebFlux Migration

~~~mermaid
flowchart TD
    A["Producer change or refactor to WebFlux"] --> B["Keep/read the same HTTP contracts"]
    B --> C["Verifier generates tests with matching WebFlux mode"]
    C --> D["Run producer tests for 200, 404, and schema"]
    D --> E{"Producer matches contract?"}
    E -->|No| F["Block publish, fix implementation or negotiate API"]
    E -->|Yes| G["Run additional reactive tests"]
    G --> H["Package/publish versioned stubs"]
    H --> I["Consumer uses Stub Runner"]
    I --> J["Assess compatibility with supported consumers"]
~~~

Recommended workflow:

1. **Keep existing HTTP contracts** as the baseline when migrating MVC to WebFlux. Do not delete contracts just because handlers changed from objects to `Mono`.
2. **Switch producer verification config** to `WEBTESTCLIENT` or `EXPLICIT` suitable for WebFlux, while verifying generated tests are created and **actually run**.
3. **Intentionally try breaking the API** such as changing `status` or breaking 404; contract tests must FAIL.
4. **Test reactive runtime properties separately** if there are non-blocking, concurrency, timeout, retry, or streaming/cancellation requirements.
5. **Publish stubs only after producer verification passes**. Stub artifacts must be traceable to verified source/contract/version.
6. **Consumer tests use Stub Runner** with a pinned version, checking client code and critical error handling.
7. **Review breaking changes** if changing a JSON array to SSE/NDJSON, changing status codes, `Content-Type`, schema, or error rules. These are communication changes even if both sides use Reactor.

## 14. Common Mistakes and How to Diagnose Them

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| Generated tests do not run on WebFlux. | `MOCKMVC` or Spring MVC base test is still configured. | Select a supported WebFlux mode, inspect generated imports/client and setup. |
| `BUILD SUCCESS` with 0 generated tests. | Wrong test discovery, lifecycle, or plugin configuration. | Open reports and generated test sources. |
| Missing ID receives empty `200` instead of 404. | `Mono.empty()` is not mapped to status 404. | Map HTTP error explicitly and run the 404 test. |
| WebTestClient cannot bind to handlers. | Base class/client binding version mismatch or app defaults to MVC. | Check classpath, test context, and generated tests. |
| Test intermittently sees order 42 and sometimes does not. | Reactive fixture not completed or state leak. | Await setup, seed/commit test data, and isolate state. |
| Consumer receives unexpected WireMock 404. | Mapping does not match path/header/body or wrong stub version. | Inspect mappings inside the `stubs` JAR and compare against actual request. |
| HTTP contract passes but throughput is poor. | Blocking I/O, scheduler, or backpressure outside contract scope. | Measure performance, check blocking and concurrency. |
| Consumer fails to parse response after migration. | Media type changed from JSON to SSE/NDJSON. | Review and version the communication change, add streaming tests. |
| Stream test hangs indefinitely. | Missing event limit, cancellation, or timeout. | Use `take(n)` and a finite deadline. |
| Stub test is green while real producer is wrong. | Producer generated tests were skipped or did not run real code. | Enforce producer verification before publishing. |

Diagnose along the path **contract → generated test → WebFlux base test → real HTTP response → stub mapping → consumer client**. When HTTP is right but concurrency is poor, the problem lies in the runtime branch, not a reason to relax HTTP matchers.

## 15. Practice: One Contract, Two Implementations

Perform this on a Spring Boot WebFlux producer and a `WebClient`-based consumer:

1. **Create HTTP contracts**: `GET /api/orders/42` returns 200 and `PAID`; `GET /api/orders/999` returns 404, choosing either Groovy or YAML as the single source of truth.
2. **Implement the WebFlux controller** returning `Mono<ResponseEntity<OrderView>>`, with `OrderLookup` emitting a result for ID 42 and `Mono.empty()` for ID 999.
3. **Configure Contract Verifier** using `JUNIT5` + `WEBTESTCLIENT` and a base test with the WebFlux application context.
4. **Run `mvn clean verify`**, confirming generated tests execute and both scenarios PASS.
5. **Intentionally break the contract**: remove 404 handling or change `status` to `state`. Confirm the test FAILS, then revert.
6. **Refactor internal reactive code** without changing status, headers, or body. Confirm generated tests still PASS.
7. **Package/install stubs** after producer tests pass; have Billing run `OrderGateway` and use `StepVerifier` to verify 200 and 404 through Stub Runner.
8. **Create a finite Flux endpoint** returning a JSON array and an SSE endpoint; explain differences in media type, framing, and testing approach.
9. **Write an additional out-of-contract test** for timeout, stream cancellation, blocking, or concurrency matching project goals.
10. **Document potentially breaking changes** when migrating MVC to WebFlux and put both producer/consumer verification into CI.

**Acceptance criteria:** you can explain **what belongs to the HTTP promise and what is a WebFlux/Reactor detail**, demonstrate that producer tests detect breaking changes, and demonstrate that the consumer can test client code with stubs **without starting the producer's reactive implementation**.

## 16. Self-Check Questions

1. Does changing a controller from `OrderView` to `Mono<OrderView>` while keeping the same HTTP status/JSON require changing the contract? Why or why not?
2. Why should `Mono.empty()` not be assumed to automatically mean 404?
3. What do `testFramework=JUNIT5` and `testMode=WEBTESTCLIENT` determine?
4. Does Stub Runner execute the producer's reactive repository or `Mono` operators?
5. Why does a passing contract test not prove the entire pipeline is non-blocking?
6. When can a `Flux` be serialized as a JSON array, and when must SSE/NDJSON be described separately?
7. Why is a static response body insufficient for verifying backpressure, reconnects, timeouts, and cancellation?
8. Why can calling `repository.save(...)` while ignoring the returned `Publisher` leave the reactive fixture unwritten?
9. Is changing 404 to an empty 200 an internal refactor or a potentially contract-breaking change?
10. When migrating from MVC to WebFlux, why should you keep existing HTTP contracts serving consumers as the baseline?

**Key takeaway:** **The HTTP contract describes what the consumer observes over the network; Reactor describes how the producer produces that result**. Contract Verifier with `WEBTESTCLIENT` or an appropriate mode verifies that the WebFlux producer still satisfies status, headers, and body; Stub Runner lets consumers test clients independently. Requirements around **non-blocking execution, backpressure, timing, retries, and streaming lifecycle** must be protected at the appropriate testing layer. Separating these two concerns enables modernizing to reactive without accidentally changing the API promise.
