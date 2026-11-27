# Setting Up a Base Test for WebFlux Applications

## Lesson Objectives

**Spring Cloud Contract** lets you describe HTTP or messaging behavior using **Groovy DSL** and **YAML DSL**, generate **producer** contract tests, and publish stubs for **consumers** to use via **Stub Runner**. For applications built on **Spring WebFlux**, choosing the right HTTP test runner and configuring the **base test class** determine whether generated tests actually verify the reactive application.

An important distinction: WebFlux uses reactive types such as `Mono` and `Flux` and can implement endpoints via annotated controllers or functional routers. A test setup designed for Spring MVC/MockMvc does not automatically apply to a WebFlux application. **Spring Cloud Contract Verifier** must be configured so generated tests use a compatible mechanism, typically **WebTestClient** via Rest Assured WebTestClient integration in supporting versions.

After this lesson, you will be able to:

- Explain the role of the base test and distinguish between contract DSL, generated producer tests, WebTestClient, and stubs.
- Choose between **application context**, **standalone handler/router**, or **real HTTP server** testing strategies based on the required assurance level.
- Understand `WEBTESTCLIENT` configuration for Maven/Gradle and the prerequisites for generated tests to compile and run.
- Design a base test with controlled data, clocks, dependencies, and reactive state.
- Distinguish finite JSON responses from streams/SSE and identify which parts need specialized testing.
- Diagnose common issues with test modes, timeouts, security filters, Reactor Context, and CI reliability.

## 1. Why Does a WebFlux Application Need a Suitable Base Test?

A reactive endpoint can be written as:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderQueryService queryService;

    OrderController(OrderQueryService queryService) {
        this.queryService = queryService;
    }

    @GetMapping("/{id}")
    Mono<ResponseEntity<OrderResponse>> getOrder(@PathVariable String id) {
        return queryService.findById(id)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
    }
}
~~~

`OrderQueryService` and `OrderResponse` are application example types, not part of Spring Cloud Contract. Key points to note:

- The controller returns `Mono<ResponseEntity<OrderResponse>>`; processing may complete **asynchronously**.
- If the publisher emits an order, the HTTP response is **200 OK** with the corresponding JSON.
- If the publisher completes empty, the controller returns **404 Not Found** per the example logic.
- If the publisher emits an error, the HTTP outcome depends on WebFlux exception handling; **you cannot assume every error becomes 404**.

The contract only describes the **HTTP method, URL, headers, body, and status** that the consumer sees. The base test is responsible for setting up the right application, test client, and fixtures so generated producer tests execute that endpoint. Do not put `Mono`, `Flux`, or internal repository names into the contract just because the implementation is reactive.

### Diagram of Two Branches from One Contract

~~~mermaid
flowchart TD
    A["Groovy/YAML Contract"] --> B["Spring Cloud Contract Verifier"]
    B --> C["Generated producer test"]
    B --> D["Stub/mapping"]
    E["WebFlux base test<br/>Test client + context + fixtures"] --> C
    C --> F["Calls producer HTTP handler/route"]
    F --> G["Verifies status, headers, JSON"]
    D --> H["Publish stub artifact"]
    H --> I["Consumer test via Stub Runner"]
~~~

**Generated producer tests and consumer stubs do not run the same program.** The base test participates only in the producer branch. Stub Runner serves data from the generated stub mappings; it does not run `Mono` or invoke fixture methods from the producer's base class.

## 2. How Do WebTestClient, RestAssuredWebTestClient, and MockMvc Differ?

In Spring WebFlux, **WebTestClient** is the HTTP testing tool designed to interact with WebFlux servers or handlers. Spring Cloud Contract has different test generation modes; in WebTestClient mode, some versions generate code using **RestAssuredWebTestClient** (Rest Assured's adapter) to configure and assert HTTP calls.

| Tool | Typical role | Caution |
| --- | --- | --- |
| **WebTestClient** | Sends requests and asserts WebFlux responses in developer-written tests | Verifier's generated tests may not call the fluent `WebTestClient` API directly |
| **RestAssuredWebTestClient** | Integrates Rest Assured with WebTestClient; used by generated tests in the matching test mode | The base test must initialize the context/client properly before tests run |
| **RestAssuredMockMvc / MockMvc** | Testing tool for Servlet/Spring MVC | Cannot automatically substitute for WebFlux |
| **RestAssured over a real HTTP port** | Sends requests to a server listening on a network port | Requires starting an HTTP server and configuring host/port; usually slower than in-memory testing |
| **StepVerifier** | Verifies `Publisher` signals and timing in Reactor | Not an automated HTTP contract verification tool replacing Verifier |

For example, a hand-written WebFlux test might use `WebTestClient`:

~~~java
@Autowired
WebTestClient client;

@Test
void shouldReturnPaidOrder() {
    client.get()
        .uri("/api/orders/ORD-1001")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.id").isEqualTo("ORD-1001")
        .jsonPath("$.status").isEqualTo("PAID");
}
~~~

The snippet above is a **hand-written test**, not a generated Spring Cloud Contract test. To make Verifier generate tests compatible with WebFlux, select the right **test mode** and configure the base class to match the API the generated tests actually use.

## 3. Sample Contracts for a WebFlux Producer

In `src/test/resources/contracts/orders/get_paid_order.yml`:

~~~yaml
description: "Query a paid order via WebFlux"
name: get_paid_order
request:
  method: GET
  url: /api/orders/ORD-1001
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: ORD-1001
    status: PAID
~~~

This is still a **standard HTTP contract**. No special contract syntax is needed just because the controller returns `Mono`:

- Request: `GET /api/orders/ORD-1001`.
- Response: status 200, JSON containing `id` and `status`.
- Producer tests must initialize the WebFlux application/handler and fixtures enabling this response.
- Stubs can return the matching JSON to the consumer regardless of whether the consumer uses WebClient, RestTemplate, or another tool.

Contract for the not-found scenario:

~~~yaml
description: "Query a non-existent order"
name: get_missing_order
request:
  method: GET
  url: /api/orders/ORD-9999
response:
  status: 404
~~~

If the team needs to formalize an error body or headers, add them per the agreed interface. Do not assume WebFlux automatically returns the exact same error schema as Spring MVC across all configurations.

## 4. Choosing WebTestClient Test Generation Mode

In Spring Cloud Contract versions that support the **`WEBTESTCLIENT`** test mode, this option instructs Verifier to generate tests compatible with WebFlux HTTP testing instead of MockMvc.

### Maven Plugin

Minimal configuration example in `pom.xml`:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-contract-maven-plugin</artifactId>
            <version>COMPATIBLE_VERSION</version>
            <extensions>true</extensions>
            <configuration>
                <testMode>WEBTESTCLIENT</testMode>
                <baseClassForTests>
                    com.example.orders.contract.WebFluxContractBase
                </baseClassForTests>
                <contractsDirectory>
                    src/test/resources/contracts
                </contractsDirectory>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

`COMPATIBLE_VERSION` is a **placeholder**, not a version you can copy verbatim into a build. Pick a release compatible with your project's Spring Boot, Spring Cloud, and test libraries. This plugin configuration does not replace BOM-managed dependencies or required test dependencies.

### Gradle Groovy DSL

~~~groovy
plugins {
    id 'org.springframework.cloud.contract' version 'COMPATIBLE_VERSION'
}

contracts {
    testMode = 'WEBTESTCLIENT'
    baseClassForTests = 'com.example.orders.contract.WebFluxContractBase'
    contractsDslDir = file('src/test/resources/contracts')
}
~~~

This is a **Gradle Groovy DSL configuration skeleton**, not `build.gradle.kts` syntax. Option names, plugin declarations, and dependencies must be checked against the Spring Cloud Contract version in use.

### Verifying That the Test Mode Is Actually in Effect

After generating tests, verify:

1. Output files not only exist, but **are compiled and discovered by the test runner**.
2. Generated sources reference an **HTTP adapter suitable** for WebFlux and the exact base class name/package.
3. The base class initializes the HTTP test client before generated tests issue requests.
4. When tests run, requests hit the **actual producer handler/router**, not a standalone stub just echoing expected responses.
5. The test runner reports executed tests; never accept a green build where contract tests were skipped.

Do not manually edit generated tests to swap `MockMvc` for `WebTestClient`. Generated sources are overwritten on subsequent builds; fix the test mode configuration and base test instead.

## 5. Setting Up the Base Test with ApplicationContext

For applications using WebFlux annotated controllers or functional routers, testing through **Spring ApplicationContext** exercises configured routers, handlers, converters, exception handlers, and many filters.

Reference base class example for Verifier versions generating `RestAssuredWebTestClient` tests:

~~~java
package com.example.orders.contract;

import io.restassured.module.webtestclient.RestAssuredWebTestClient;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
public abstract class WebFluxContractBase {

    @Autowired
    private ApplicationContext applicationContext;

    @BeforeEach
    void setUpContractClient() {
        RestAssuredWebTestClient.applicationContextSetup(applicationContext);
    }
}
~~~

This is a **pattern for one integration approach**. APIs such as `applicationContextSetup(...)` and generated test styles must be verified against your project's Rest Assured/Spring Cloud Contract version. Some setups may choose to pass a pre-built `WebTestClient` to the adapter instead of passing the application context directly.

Meaning:

- `@SpringBootTest` builds the producer application's context.
- `MOCK` mode typically does not open a random HTTP port; WebTestClient can bind to the application context to process requests inside the test process.
- `@BeforeEach` ensures the adapter is configured before each generated test.
- Generated tests execute HTTP assertions based on the contracts.

**Important condition:** this annotation must actually spin up a **WebFlux application context**. If the project includes both Spring MVC and WebFlux, how Boot selects the web application type and dependencies can affect the active mode. Do not treat `@SpringBootTest` alone as sufficient proof that tests ran on WebFlux.

### The Base Test Does Not Necessarily Need a Real Server

In-memory testing via the application context is usually enough to verify controllers/routes, JSON serialization, and many filters. However, it does not automatically test real HTTP server details such as port bindings, TLS, reverse proxies, or certain Netty/network-runtime behaviors.

If those factors are part of critical commitments, add **real HTTP server integration tests** in a supplementary test layer or pick an appropriate test strategy.

## 6. Option Using an Auto-Configured WebTestClient

In a Spring Boot WebFlux project, `@AutoConfigureWebTestClient` can provide an injected client. Example:

~~~java
package com.example.orders.contract;

import io.restassured.module.webtestclient.RestAssuredWebTestClient;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
public abstract class WebFluxLiveServerContractBase {

    @Autowired
    WebTestClient webTestClient;

    @BeforeEach
    void configure() {
        RestAssuredWebTestClient.webTestClient(webTestClient);
    }
}
~~~

This is an **alternative** to `applicationContextSetup`, not something to combine into the same base class. With `RANDOM_PORT`, the server can run on a dynamic port, and `WebTestClient` is configured to target the running test application instance. Confirm that `@AutoConfigureWebTestClient`, autowiring, and the adapter API work properly on your chosen Boot/Rest Assured versions.

**Never hard-code port 8080** in generated tests. That port may be occupied by another process or differ from the test server port. Prefer a client configured by the test context or proper port injection.

### When to Use Which Approach?

| Criterion | Bind to ApplicationContext | HTTP server on RANDOM_PORT |
| --- | --- | --- |
| Speed | Usually faster, no network port opened | Usually heavier |
| Handler/router/serialization checks | Yes, within context scope | Yes, over real HTTP |
| HTTP server runtime checks | Incomplete | Covers more network/server factors |
| Isolation | Fewer port collisions | Requires server/client coordination |
| Best suited for | Frequent contract tests in producer CI | Verifying server config or HTTP socket handling |

Both approaches can be valid. Choose based on **what the contract needs to prove**, framework version, and CI cost; avoid assuming the heavier approach is always better.

## 7. Standalone Setup: Fast but Narrow Scope

Sometimes a team only wants to test a single standalone WebFlux handler or controller. `WebTestClient` supports binding to a controller/router using the appropriate builder methods. A **hand-written** WebFlux test example:

~~~java
WebTestClient client = WebTestClient
    .bindToController(new OrderController(fakeOrderQueryService))
    .build();

client.get()
    .uri("/api/orders/ORD-1001")
    .exchange()
    .expectStatus().isOk();
~~~

This snippet illustrates the **standalone** strategy, not a Verifier adapter command to copy directly. If you want generated tests to target a manually constructed handler, configure RestAssuredWebTestClient using the version-appropriate standalone API and ensure the base class supplies all required dependencies.

Standalone setup has limitations:

- It may **skip `WebFilterChain`/security** unless you manually register the required components.
- It does not automatically verify full `@ControllerAdvice`, codecs, routing, and configuration loaded by the real application.
- If the handler returns a mock response without exercising the producer logic under test, a passing test may only prove the mock satisfies the contract.

Therefore, for contract testing aimed at protecting integration compatibility, **application context** is usually a more representative starting point. Standalone fits when the scope is intentionally a single handler and its limitations are documented.

## 8. The Base Test Needs Fixture Data for Reactive Flows

A `Mono<OrderResponse>` endpoint may still depend on a reactive repository, cache, or HTTP client calling another service. Generated contract tests require **stable, independent** data, never production data.

Reactive repository test fixture example (illustrative code):

~~~java
import java.time.Duration;
import org.junit.jupiter.api.BeforeEach;

@BeforeEach
void seedFixture() {
    // Use only a test-dedicated database.
    orderRepository.deleteAll()
        .then(orderRepository.save(
            new OrderEntity("ORD-1001", "PAID")
        ))
        .block(Duration.ofSeconds(5));
}
~~~

`OrderEntity` and `orderRepository` belong to the sample application. The snippet above only shows the data-preparation idea; in real implementation, place it in the proper base class, declare dependencies, and make sure you do not wipe data shared by other tests.

### Is `block()` Allowed in the Base Test?

During the **test lifecycle**, inside a setup method running on an appropriate test thread, `block(Duration)` can be a convenient way to wait for fixture seeding to finish **before generated tests send HTTP requests**. This differs from calling `block()` in request-handling code running on a WebFlux event loop.

Rules:

1. Block only at the test boundary when needed; never carry that style into reactive controllers/services.
2. Always set an explicit timeout so tests never hang indefinitely.
3. Never block on Reactor non-blocking/event-loop threads; doing so can cause errors or thread starvation.
4. Consider how data is written/read under your backend's actual transaction and consistency model.
5. If tests running in parallel share a database, `deleteAll()` can wipe another test's fixtures. Use isolated databases/namespaces or proper isolation mechanisms.

A proper base test must ensure data is persisted **before** reactive requests are sent; if setup only calls `repository.save(...)` without subscribing or awaiting the publisher, the write may never execute.

## 9. Fake External Dependencies Without Mocking Away the Producer Itself

Order Service might use `WebClient` to call another service. If producer contract tests depend on external networks, results easily flake due to latency, DNS, tokens, or shifting data.

You can set up **test doubles** at dependency boundaries—for example, a fake `PaymentGateway` or fake `OrderQueryService`, depending on what is being verified.

| Safe to mock/fake | Should not be replaced entirely |
| --- | --- |
| External payment gateway | Controller/route being verified |
| Clock and ID generator | JSON serialization consumers depend on |
| Repository with controlled test data | Producer's HTTP status/error mapping |
| Event emitter at the appropriate boundary | Business logic deciding whether events are created |

If the base test merely provides a mock controller that always returns `200` and JSON identical to the contract, the test does nothing to verify that the **real producer controller** fulfills the interface.

With Spring WebFlux, test doubles typically return `Mono.just(...)`, `Mono.empty()`, `Mono.error(...)`, or `Flux` depending on the scenario. Build enough scenarios to distinguish:

- **Data present:** producer returns 200 and valid body.
- **Data missing:** producer returns 404 per defined rules.
- **Dependency failure:** producer translates errors into the agreed HTTP code and schema without guessing.
- **Timeout:** handled per contract or operational policy; do not assume timeouts are always specified by Contract DSL.

Mocks must simulate **inputs to the real producer**, not pre-fabricate the final output and bypass the logic under test.

## 10. WebFlux and Time: Do Not Fix Flaky Tests with Sleep

A finite reactive response may be produced after asynchronous work. When `WebTestClient` invokes `exchange()`, the test awaits response completion or timeout instead of sprinkling `Thread.sleep(...)` before requests.

Sources of flakiness:

| Cause | Symptom | Solution |
| --- | --- | --- |
| Reactive fixture not subscribed | Sometimes record exists, sometimes 404 | Await publisher completion in setup |
| Blocked event loop | Random timeouts | Remove blocking from non-blocking threads |
| Test uses real wall-clock time | Timestamps differ across runs | Inject `Clock` or use required matchers |
| Slow remote dependency | Network-dependent CI failures | Fake at boundaries or use controlled integration env |
| Timeout too low | Fails under heavy CI load | Choose grounded timeouts; separate performance tests |
| Shared test state | Passes alone, fails in suite | Isolate data, caches, subscriptions, and publishers |

For example, if an application populates `createdAt` with the current timestamp, inject `Clock` and provide `Clock.fixed(...)` in test setup when the contract expects a deterministic value. If the contract only requires a valid timestamp format, consider a matcher rather than nanosecond-exact equality.

For `Flux` with time-based operators or backpressure, `StepVerifier.withVirtualTime(...)` is helpful in **unit tests of reactive pipelines**, but virtual time does not automatically replace `Clock` across the whole application context or simulate network delays for Verifier. Keep those forms of evidence separate.

## 11. Testing Errors and Validation with Dedicated Contracts

A producer contract test suite should cover at least the scenarios consumers actually branch on. For Order Service:

~~~text
GET /api/orders/ORD-1001 -> 200 + order JSON
GET /api/orders/ORD-9999 -> 404
POST /api/orders with invalid body -> 400 + agreed error JSON
~~~

Example YAML scenario for validation:

~~~yaml
description: "Reject order creation request with negative quantity"
name: reject_negative_quantity
request:
  method: POST
  url: /api/orders
  headers:
    Content-Type: application/json
  body:
    customerId: "CUS-TEST-1001"
    quantity: -1
response:
  status: 400
  headers:
    Content-Type: application/json
  body:
    code: INVALID_QUANTITY
~~~

`INVALID_QUANTITY` is an **illustrative** error code—use it only if producer and consumer agreed on that commitment. In WebFlux, validation may run via Bean Validation, functional handlers, or custom logic; the base test must load the components that actually determine the error response.

**A risk of standalone setup** is bypassing filters, exception handlers, or validation configured outside the controller, causing generated tests to see responses that differ from runtime reality. Confirm your test setup includes every component the contract relies on.

## 12. WebFilter, Security, and Reactor Context

WebFlux applications commonly include components like:

- `WebFilter` adding request IDs, tenant info, trace headers, or authentication details.
- Spring Security filter chain controlling endpoint authorization.
- `Reactor Context` propagating data along the reactive flow, such as trace or tenant metadata.
- Codecs/exception handlers determining JSON output and HTTP codes.

In the base test:

1. If the contract covers authentication behavior or related headers, do not accidentally **skip filters** just because standalone tests are easier to configure.
2. If an endpoint requires a mocked identity, supply an appropriate **test principal/credential**, never production tokens in contracts.
3. If the producer uses Reactor Context, tests must go through the application's context-population flow rather than assuming a static `ThreadLocal` follows reactive execution.
4. Ensure custom filters or exception handlers are registered in the application context used by tests.

Not every security policy needs to live in the same HTTP contract. Dedicated security tests can be kept separate, yet **status/header/body contracts must be verified in a context meaningful to consumers**.

## 13. Do Functional Routers Differ from Annotated Controllers?

Spring WebFlux can use:

- `@RestController` with `@GetMapping`, `@PostMapping`.
- `RouterFunction<ServerResponse>` with handler functions.

The external contract remains the HTTP request/response:

~~~text
GET /api/orders/ORD-1001
Accept: application/json

-> 200, Content-Type: application/json
-> {"id":"ORD-1001","status":"PAID"}
~~~

Verifier does not care whether an endpoint is routed by annotations or functional routers. However, the **base test** must attach the HTTP client to the right components:

- Using application context: can include router functions/handlers loaded in the context.
- Using standalone: must bind the exact controller or router and explicitly register needed filters/exception handlers in the test setup.
- Using a real HTTP server: ensure routers are registered in the application and the port/client match.

In documentation or code reviews, state the **client binding strategy** explicitly rather than just writing "used WebTestClient". Two tests both using WebTestClient can cover very different slices of the application.

## 14. Streaming Responses: Not Every Flux Should Be Tested Like Single JSON

`Mono<OrderResponse>` returning a finite response usually fits generated HTTP contract tests well. However, a `Flux` can represent:

- A finite JSON list serialized completely.
- An event stream over `text/event-stream` (SSE).
- NDJSON streaming or a never-completing publisher.

**A standard HTTP contract for a fixed JSON body does not automatically verify full streaming semantics**, including event ordering, backpressure, cancellation, reconnects, timeouts, and messages emitted after intervals.

| Endpoint type | Suitable testing approach |
| --- | --- |
| `Mono<ResponseEntity<T>>` | Generated HTTP contract test with WebTestClient mode |
| `Flux<T>` returning a finite list | Can use HTTP contracts if serialized/completed as committed; check actual output |
| Continuous SSE | Consider contracts for observable events plus dedicated WebTestClient/StepVerifier/integration tests |
| Infinite publisher or backpressure requirements | Needs specialized reactive tests with controlled timing and signal counts |

Never hard-code `Thread.sleep(5000)` hoping a stream finishes emitting. When awaiting a number of events, use tools that bound signal counts and termination conditions, apply reasonable timeouts, and clean up subscriptions after the test.

A contract can verify the **structure of a message/event**; it is not full evidence for timing and operational behavior of the entire stream.

## 15. Diagnosing Generated Tests That Do Not Run Properly on WebFlux

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| Generated tests reference `RestAssuredMockMvc` | Test mode is still MockMvc | Check `WEBTESTCLIENT` and actual generated code |
| Cannot compile `RestAssuredWebTestClient` | Missing test module/dependency or wrong version | Inspect dependency management and test classpath |
| Generated test cannot call HTTP client | Base class didn't set up client or isn't extended | Check `baseClassForTests`, `@BeforeEach`, and generated source |
| Test gets 404 even though route works at runtime | Context/standalone setup missing router or mapping | Check loaded routes and binding strategy |
| Test unexpectedly returns 401/403 | Security filter active while test identity missing | Configure test principal/credentials per contract scope |
| Test PASSES yet production fails security | Standalone setup bypassed filters | Increase coverage via context/server tests |
| Test times out | Reactive fixture not subscribed, blocked event loop, or slow external dependency | Inspect reactive chains, timeouts, and external calls |
| `block()` throws error | Blocking on event-loop/non-blocking thread | Move blocking to test setup or use reactive chaining |
| Passes alone, fails in suite | Shared DB/cache/fake publisher/port | Isolate fixtures and manage lifecycle |
| Consumer Stub Runner PASSES, producer mismatched | Stale stubs or producer contract tests didn't run | Tie stub versions to verified revisions |

To diagnose, examine **three pieces of evidence**: the generated test source, actual executed test reports, and the packaged stub artifact. Looking only at a green build does not guarantee Verifier tested the WebFlux application.

## 16. Designing Verification Gates in CI

A practical producer/consumer workflow:

~~~mermaid
flowchart TD
    A["Checkout producer + contract revision"] --> B["Read Groovy/YAML contracts"]
    B --> C["Generate tests in WEBTESTCLIENT mode"]
    C --> D{"Generated tests compiled and discovered?"}
    D -->|No| X["BLOCK"]
    D -->|Yes| E["Base test prepares WebFlux context + fixtures"]
    E --> F["Run producer contract tests"]
    F --> G{"PASS with none skipped?"}
    G -->|No| X
    G -->|Yes| H["Build versioned stub artifact"]
    H --> I["Consumer tests via Stub Runner"]
    I --> J{"PASS with exact stub version?"}
    J -->|No| X
    J -->|Yes| K["Store scoped release evidence"]
~~~

A project-**designed** verification record:

~~~yaml
# Not default output of Spring Cloud Contract.
producer_revision: "order-service@abc123"
contracts_revision: "contracts@def456"
test_mode: WEBTESTCLIENT
base_test: "com.example.orders.contract.WebFluxContractBase"
expected_contracts:
  - get_paid_order
  - get_missing_order
generated_tests_detected: true
producer_contract_tests: PASS
stub_artifact: "com.example:order-service:2.4.0:stubs"
consumer_stub_tests: PASS
~~~

To keep CI reliable:

1. Cross-check the **expected contract list** against contracts actually processed.
2. Confirm generated tests are included in test compilation/tasks—not just sitting under `target` or `build`.
3. Ensure `WEBTESTCLIENT` test mode is active and the base test matches.
4. Confirm generated tests actually execute; catch `0 tests` or abnormal skips.
5. Pin the same contract revision, producer build, and stub artifact; avoid uncontrolled `latest`.
6. Run consumer tests against the **exact stub version** and assert consumer logic, not merely stub server startup.
7. Never equate a few passing contract tests with full coverage of WebFlux backpressure, load resilience, security, and operations.

## 17. Practice Scenarios

### Exercise A — Migrating from MVC to WebFlux

A producer switches from `spring-boot-starter-web` to `spring-boot-starter-webflux`. The YAML contract remains `GET /api/orders/ORD-1001`, but generated tests use MockMvc and fail to invoke the controller.

**Prompt:** state what must be checked/updated in test mode, base class, and dependencies; explain why **the URL in the contract does not need to change just because the server technology changed**.

**Hint:** select WebTestClient test mode if supported by the version, create a WebFlux base class, and inspect generated sources. HTTP behavior remains preserved if the API has not changed.

### Exercise B — Unsubscribed Publisher

In `@BeforeEach`, the base test calls `repository.save(entity)` and returns. Some test runs return 404 for an order that should exist.

**Prompt:** explain what may not have happened and propose a reliable way to prepare data before requests execute.

**Hint:** a cold `Mono` may not execute without a subscription. At the test boundary, await publisher completion in a controlled way; use timeouts and isolated data.

### Exercise C — Bypassed Security Filter

A generated test uses standalone setup, and producer tests PASS for an endpoint requiring authentication. When the consumer calls the real server, it receives 401.

**Prompt:** distinguish the tested scope from the expected contract scope; choose an appropriate context/identity setup.

**Hint:** standalone setups may omit security filters. If auth is part of the public interface, test via a context/server with real filters and suitable test credentials.

### Exercise D — Never-Ending Event Stream

The producer exposes `text/event-stream` and emits one event per second. A test waits for the entire response body to complete and times out.

**Prompt:** explain why this testing approach is unsuitable and propose a test for a finite event count or controlled time window.

**Hint:** infinite streams do not have a complete body like a standard JSON response. Use streaming tests with bounded signal counts, timeouts, cancellation, and appropriate StepVerifier/WebTestClient assertions; avoid fixed sleeps.

### Exercise E — Stale Stub Misleads CI

WebFlux producer version 2.4.0 passes contract tests, and consumer tests pass with Stub Runner, except they are pulling `order-service:2.3.0:stubs`.

**Prompt:** identify the missing evidence and propose how to lock revisions/versions.

**Hint:** publish stub 2.4.0 from the exact contract/build verified by producer tests, then re-run consumer tests against that artifact; record revisions and reports from both sides.

## 18. WebFlux Base Test Acceptance Checklist

- [ ] Groovy/YAML contracts describe HTTP/message behavior consumers truly need, without coupling to reactive implementation.
- [ ] Selected `WEBTESTCLIENT` test mode appropriately based on the plugin version in use.
- [ ] Base test class resides in the right package and is referenced by `baseClassForTests` or equivalent mapping.
- [ ] Generated tests use a WebFlux-compatible adapter, compile cleanly, and execute.
- [ ] Context, standalone, or real HTTP server strategy and its coverage scope are explicitly chosen.
- [ ] WebTestClient/RestAssuredWebTestClient is initialized before generated tests run.
- [ ] Routes/controllers, JSON codecs, exception handlers, and critical filters are properly loaded.
- [ ] Reactive fixtures are properly subscribed/awaited before requests and isolated across tests.
- [ ] Event loop is never blocked; setup uses explicit timeouts without arbitrary `Thread.sleep`.
- [ ] Timezones, clocks, IDs, and external data are controlled via appropriate fixtures/dependencies.
- [ ] Mocks sit at dependency boundaries without replacing the producer behavior under verification.
- [ ] Important 200/404/400 and security/error behaviors have matching scenarios.
- [ ] Streaming/SSE, timing properties, and backpressure are verified with specialized tests where needed.
- [ ] Stub artifacts are generated from the exact verified contract revision and producer build.
- [ ] Consumer tests via Stub Runner use the exact stub version with traceable CI results.
- [ ] Green builds with missing generated tests or skipped tests are never treated as compatibility proof.

**Key takeaway:** A **WebFlux base test** is not simply swapping MockMvc for WebTestClient. It must connect generated producer tests to the **right WebFlux handlers, application context, and test data**, while clearly defining which runtime parts are being verified. Only when test mode, fixtures, and CI are properly configured does Spring Cloud Contract provide reliable evidence that the reactive producer's HTTP behavior remains compatible with verified consumers.
