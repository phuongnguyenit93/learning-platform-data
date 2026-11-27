# Timeouts and Asynchronous Tasks in Testing

## 1. Why Are Timeouts Part of Reactive Testing?

With **Spring Cloud Contract (SCC)**, producers and consumers agree on HTTP or messaging behavior through **Groovy DSL/YAML DSL**. Contract Verifier generates tests to verify the producer fulfills the commitment; the same contracts generate stubs for consumers to run via **Stub Runner**. Combining both in CI helps detect incompatible API changes.

In **Spring WebFlux/Reactor** applications, controllers can return `Mono<T>` or `Flux<T>`. Receiving a request and producing data may happen **asynchronously**: querying a reactive database, calling another service, awaiting a message signal, or running a long-lived task. If tests check only status/body without caring about **subscribing, awaiting, timeouts, errors, and task cancellation**, the application can:

- Return valid responses locally yet **hang indefinitely** when a dependency never signals.
- Flake occasionally in CI because test wait windows are too short or rely on wall-clock time.
- Pass as "green" by merely creating a `Mono` without **subscribing**, meaning the logic never executed.
- Test against stubs that always respond instantly, while the production consumer fails on slow responses.
- Configure **conflicting** timeouts across client, server, and runner, causing tests to misreport root causes.

This lesson focuses on **timeouts and asynchronous tasks in testing**: separating SCC's responsibilities from Reactor/WebFlux testing, choosing layered timeouts, using `StepVerifier`/virtual time, testing asynchronous HTTP, and coordinating candidate stubs in CI.

### Objectives

After this lesson, you will be able to:

1. Understand the differences between `Mono`, `Flux`, subscription, completion, error, and cancellation.
2. Distinguish **business timeouts**, **I/O timeouts**, **HTTP test client timeouts**, and **overall CI job timeouts**.
3. Write HTTP contracts for a WebFlux producer and verify them with WebTestClient.
4. Test Reactor flows with `StepVerifier` and **virtual time** without `Thread.sleep`.
5. Simulate slow/unresponsive dependencies and confirm proper status, errors, and cleanup.
6. Avoid false-green tests caused by mocking out producer behavior itself or failing to await real task completion.
7. Test consumers via Stub Runner, add delay/timeout tests, and build diagnosable CI gates.

## 2. How Does a Reactive Response Flow Unfold?

~~~mermaid
sequenceDiagram
    participant C as Checkout Consumer
    participant H as HTTP WebFlux
    participant S as Inventory Service
    participant D as Reactive Repository
    C->>H: GET /api/inventory/SKU-123
    H->>S: findStock("SKU-123")
    S->>D: Create query Publisher
    D-->>S: Mono<Stock>
    Note over H,D: Publisher usually does no work until subscribed
    H->>D: Subscribe through reactive chain
    D-->>H: onNext(stock), onComplete
    H-->>C: HTTP 200 + JSON
~~~

In Reactor, never equate "created a publisher" with "finished the work":

| Signal / concept | Meaning | Testing consequence |
|---|---|---|
| `Mono<T>` | Publisher of at most one item, then complete/error | Can return a value, complete empty, or error |
| `Flux<T>` | Publisher of 0..n items | Can be finite or infinitely long |
| **Subscription** | Consumer registers to receive signals | Most reactive chains begin working only when subscribed |
| `onNext` | A new item arrived | Tests must verify the data actually emitted |
| `onComplete` | Stream finished successfully | Critical for operations that must terminate |
| `onError` | Stream terminated with an error | Contract must reflect public errors if mapped to an HTTP response |
| **Cancellation** | Subscriber cancels | May need to halt queries, free resources, or stop retries |
| **Timeout** | No suitable signal received within the wait window | Depending on layer, may produce an error, fallback, HTTP status, or test termination |

**Rule:** reactive tests must trigger a subscription and have an explicit **termination/time-bound condition**. Asserting a `Mono<StockResponse>` variable is non-null does not prove the repository was called or the result handled.

## 3. Four Timeout Layers That Cannot Replace One Another

A WebFlux request passes through multiple layers. Each layer has a different purpose and owner.

| Layer | Example | What expires? | Role |
|---|---|---|---|
| **Producer application** | `mono.timeout(Duration.ofMillis(800))` | No signal from upstream chain within allowed window | Decides error/fallback per API semantics |
| **Consumer HTTP client** | Reactor Netty `responseTimeout` or client timeout | HTTP response not received on time | Protects consumer resources and latency |
| **Test client / StepVerifier** | `responseTimeout`, `verify(Duration)` | The test itself fails to finish on time | Prevents hanging tests, produces failure reports |
| **Test runner / CI** | JUnit timeout, job timeout | Entire test or full job runs too long | Final safety net, never replaces business assertions |

Example of an **illustrative budget** a team might pick:

~~~text
Producer awaits dependency:     up to 800 ms
Producer builds error response: ~1,000 ms from receiving request
Consumer client timeout:        1,500 ms
HTTP test client deadline:      2,500 ms
JUnit test deadline:            10 s
CI job deadline:                overall pipeline limit
~~~

These are **illustrative numbers**, not defaults or universal recommendations. They must be chosen based on your real system's SLOs, infrastructure, latency distribution, and retry strategy.

Each tier needs enough headroom for serialization, scheduling, and CI jitter, yet cannot be infinitely wide. A test timing out after 30 seconds does not prove an API meets a 1-second SLO; conversely, a 100 ms test deadline in a busy CI environment can cause flakiness.

## 4. Running Example: Inventory Service with WebFlux

Suppose **Inventory Service** is the producer and **Checkout Service** is the consumer. Endpoint:

~~~http
GET /api/inventory/SKU-123 HTTP/1.1
Accept: application/json
~~~

When the dependency returns on time:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"sku":"SKU-123","available":true,"quantity":12}
~~~

When the backend fails to signal within the business deadline, the practice API decides to return:

~~~http
HTTP/1.1 504 Gateway Timeout
Content-Type: application/json

{"code":"INVENTORY_TIMEOUT","message":"Inventory lookup timed out"}
~~~

**Design note:** `504` and code `INVENTORY_TIMEOUT` here are **commitments chosen by the service team** for this demo. Spring WebFlux does not automatically turn every `Mono.timeout` into this exact response. Without error handling, a `TimeoutException` may be mapped by the framework to a different response.

Two separate contracts protect **success behavior** and **timeout behavior**, though they do not by themselves prove internal deadlines hit exact millisecond targets. Timing measurements require separate tests with appropriate tools.

## 5. A Reactive Controller Is Still Real Producer Code

A controller class can keep responses wrapped in `Mono`:

~~~java
package com.example.inventory;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/inventory")
public class InventoryController {
    private final InventoryService service;

    public InventoryController(InventoryService service) {
        this.service = service;
    }

    @GetMapping("/{sku}")
    public Mono<ResponseEntity<StockResponse>> getStock(
            @PathVariable String sku) {
        return service.findStock(sku)
                .map(ResponseEntity::ok)
                .defaultIfEmpty(ResponseEntity.notFound().build());
    }
}
~~~

Supporting types used in the example:

~~~java
package com.example.inventory;

public record StockResponse(
        String sku, boolean available, int quantity) {
}
~~~

`InventoryService` is a real application service returning `Mono<StockResponse>`. If the repository finds no stock, the controller returns `404` via `defaultIfEmpty`. If `Mono` emits an error, the controller above **does not catch it yet**: error handling can live in the service or `@RestControllerAdvice` per the contract.

When testing, ensure generated/HTTP tests **call the real controller** and actually trigger subscriptions. Never let the base test return `Mono.just(new StockResponse(...))` instead of the controller, as that hides producer logic.

## 6. Put Timeouts in the Service, Not Just in Tests

A service can apply a deadline and translate timeout errors into results understood by the HTTP layer:

~~~java
package com.example.inventory;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class InventoryService {
    private final InventoryGateway gateway;

    public InventoryService(InventoryGateway gateway) {
        this.gateway = gateway;
    }

    public Mono<StockResponse> findStock(String sku) {
        return gateway.lookup(sku)
                .timeout(Duration.ofMillis(800))
                .onErrorMap(
                    TimeoutException.class,
                    error -> new InventoryTimeoutException(sku, error)
                );
    }
}
~~~

Assuming `InventoryGateway.lookup` returns `Mono<StockResponse>` and `InventoryTimeoutException` is the demo domain exception:

~~~java
package com.example.inventory;

public class InventoryTimeoutException extends RuntimeException {
    public InventoryTimeoutException(String sku, Throwable cause) {
        super("Inventory lookup timed out for " + sku, cause);
    }
}
~~~

To convert this exception into the committed HTTP response:

~~~java
package com.example.inventory;

import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class InventoryErrorHandler {
    @ExceptionHandler(InventoryTimeoutException.class)
    public ResponseEntity<Map<String, String>> timeout() {
        return ResponseEntity.status(HttpStatus.GATEWAY_TIMEOUT)
                .body(Map.of(
                    "code", "INVENTORY_TIMEOUT",
                    "message", "Inventory lookup timed out"
                ));
    }
}
~~~

These are **illustrative** classes in the lesson content, not code already built or executed in a project. In real architectures, you might return `503` or another fallback; stay consistent with contracts and supported consumers.

### Warnings About Mono.timeout

- `timeout(Duration)` starts measuring from **subscription**. For `Mono`, if no signal arrives within that window, the operator emits `TimeoutException` and cancels upstream.
- For `Flux`, default timeout variants may govern the **interval between consecutive signals**, not a total deadline for the entire stream. If the API needs an overall deadline, define and test it explicitly.
- Timeout **does not guarantee** uncooperative blocking code stops immediately. Cancelling a reactive subscription is not equivalent to safely interrupting every I/O library or external process.
- Using `onErrorResume` to return a default value can make consumers mistake an error for success; when a fallback is used, the contract must state it clearly.

## 7. Groovy Contract: Succeeding Even Though Producer Uses Mono

If the real endpoint returns JSON after `Mono` emits a value, the HTTP contract still describes **HTTP status, headers, and body**.

File `src/test/resources/contracts/inventory/stock-found.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Checkout reads stock from reactive producer'

    request {
        method GET()
        url '/api/inventory/SKU-123'
        headers {
            header('Accept', 'application/json')
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-123',
            available: true,
            quantity: 12
        )
    }
}
~~~

**Key point:** in the completed HTTP response, the consumer does not see a `Mono` object. The consumer receives **status and JSON bytes**. Therefore, there is no need to "write Mono in Groovy DSL." The test generation tool must be wired properly to the Spring WebFlux stack so requests **subscribe to the real publisher**.

### Equivalent YAML DSL

~~~yaml
description: Checkout reads stock from reactive producer
name: reactive_stock_found

request:
  method: GET
  url: /api/inventory/SKU-123
  headers:
    Accept: application/json

response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    available: true
    quantity: 12
~~~

Do not place both equivalent contracts in the same directory just to test syntax if they produce duplicate generated tests/mappings. Pick one DSL per project policy.

## 8. Contract for Timeout Responding with HTTP 504

If the API contract commits to an error status after timing out, write a **separate** contract with a clear scenario request:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Return error when upstream inventory fails to respond'

    request {
        method GET()
        url '/api/inventory/SKU-TIMEOUT'
    }

    response {
        status GATEWAY_TIMEOUT()
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'INVENTORY_TIMEOUT',
            message: 'Inventory lookup timed out'
        )
    }
}
~~~

If your DSL version does not support the `GATEWAY_TIMEOUT()` constant, use numeric status syntax supported by that version, such as `status 504`, and inspect actual generated code.

An equivalent YAML contract:

~~~yaml
description: Return error when upstream inventory fails to respond
name: reactive_inventory_timeout

request:
  method: GET
  url: /api/inventory/SKU-TIMEOUT

response:
  status: 504
  headers:
    Content-Type: application/json
  body:
    code: INVENTORY_TIMEOUT
    message: Inventory lookup timed out
~~~

**Do not make real tests wait 800 ms or tens of seconds on every run** if you can simulate a dependency timeout deterministically. For producer verification, the base test can configure the **test gateway** for this specific SKU to emit a timeout error or controlled delay, provided **the production service still runs its real timeout/error-mapping logic**.

The contract above primarily protects **HTTP status and error schema**. It does not directly confirm the response arrives in exactly 800 ms or that upstream was cancelled. Add Reactor/WebFlux tests for timing properties.

## 9. WebTestClient: Testing Reactive HTTP Endpoints

`WebTestClient` is Spring's tool for invoking/verifying reactive HTTP. It can bind to an application context or a running server, depending on the desired integration test scope.

Example of a **standalone WebFlux HTTP test**, not SCC's generated test pseudo-code:

~~~java
package com.example.inventory;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class InventoryHttpTest {
    @Autowired
    WebTestClient client;

    @Test
    void findsStock() {
        client.get()
                .uri("/api/inventory/SKU-123")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.sku").isEqualTo("SKU-123")
                .jsonPath("$.available").isEqualTo(true)
                .jsonPath("$.quantity").isEqualTo(12);
    }
}
~~~

In this example, `exchange()` sends the request and awaits the response for assertions. Returning `Mono` in the controller **does not require HTTP checks to call `block()` inside production code**.

Ensure the environment has fixture data for `SKU-123`. If the service calls an unstable real dependency, isolate at the exact dependency boundary while keeping the production controller/service in the verification flow.

### Do Not Confuse WebTestClient with Contract Verifier

- `WebTestClient` is a concrete HTTP testing tool.
- SCC **generates** tests from Groovy/YAML contracts; depending on version/plugin, the test mode may produce WebTestClient-based tests.
- A hand-written WebTestClient test **does not automatically** mean generated contract tests ran.

In CI, confirm both that contracts were discovered and generated tests executed.

## 10. Connecting Contract Verifier to WebFlux with the Right Test Mode

A WebFlux project typically uses a generated test mode compatible with **WebTestClient** (if supported by the SCC version in use), rather than mechanically using MockMvc on a reactive stack.

Illustrative Maven plugin configuration snippet:

~~~xml
<plugin>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-contract-maven-plugin</artifactId>
    <version>CONTRACT_PLUGIN_VERSION</version>
    <extensions>true</extensions>
    <configuration>
        <testFramework>JUNIT5</testFramework>
        <testMode>WEBTESTCLIENT</testMode>
        <baseClassForTests>
            com.example.inventory.ReactiveContractTestBase
        </baseClassForTests>
    </configuration>
</plugin>
~~~

`CONTRACT_PLUGIN_VERSION` is a placeholder that must be replaced with a **real version** compatible with your Spring Boot and Spring Cloud Release Train. Syntax and the `WEBTESTCLIENT` enum must be verified against the documentation for **your exact SCC version**, and then confirmed in the generated source.

Example base test that **initializes a real WebFlux context**:

~~~java
package com.example.inventory;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
public abstract class ReactiveContractTestBase {
    // Prepare test fixtures at the dependency boundary.
    // Inspect generated tests to see whether WebTestClient needs to be injected/bound
    // or which adapter must be configured for your test mode/plugin version.
}
~~~

This example mainly illustrates **the base class and test scope**. Never assume it is sufficient for every generated test: some versions/modes require a WebTestClient field, adapter initialization, base URL configuration, or a specific setup method. After generation, **read the generated class** and add exactly what it requires.

Do not let the base test construct `Mono.just(sampleResponse)` to bypass the producer behavior under verification; doing so easily creates false-green tests.

## 11. WebTestClient Timeout: The Test Tool's Deadline

When a test awaits an HTTP response, you can configure a timeout on `WebTestClient`. Example client **bound to a server**:

~~~java
WebTestClient client = WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .responseTimeout(Duration.ofSeconds(3))
        .build();
~~~

The example requires importing `java.time.Duration` and `org.springframework.test.web.reactive.server.WebTestClient`. `localhost:8080` is an illustrative address only; in Spring Boot tests with a random port, obtain the **actual port** from the test environment.

You can also configure a timeout when building a client from context depending on the binding API used:

~~~java
WebTestClient client = WebTestClient.bindToApplicationContext(context)
        .configureClient()
        .responseTimeout(Duration.ofSeconds(3))
        .build();
~~~

Here `context` is an initialized Spring WebFlux `ApplicationContext`. Binding to context does not test a real web server, yet still exercises the handler chain within the context.

**Keep meanings separate:** if `WebTestClient` times out after 3 seconds, that is a **test-tool failure while awaiting a response**, not proof that the producer returned HTTP 504. To verify a `504 INVENTORY_TIMEOUT` contract, the producer must **itself translate the upstream timeout into an HTTP 504 response** before the test client times out.

Never accidentally set the test timeout shorter than the business deadline: the test client might stop waiting before the producer can send its committed error response.

## 12. StepVerifier: Directly Inspecting Publisher Signals

`reactor-test` provides `StepVerifier` to verify reactive chains beneath the HTTP layer. This is the right place to verify **onNext, onComplete, onError**, while WebTestClient tests the HTTP interface.

Example for a service returning `Mono<StockResponse>`:

~~~java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class InventoryPublisherTest {
    @Test
    void emitsOneStockAndCompletes() {
        Mono<StockResponse> result = Mono.just(
            new StockResponse("SKU-123", true, 12)
        );

        StepVerifier.create(result)
                .expectNextMatches(stock ->
                    stock.sku().equals("SKU-123")
                    && stock.available()
                    && stock.quantity() == 12
                )
                .verifyComplete();
    }
}
~~~

**Scope note:** the example above illustrates the `StepVerifier` API. It tests a dummy publisher constructed by the test, **not the production InventoryService**. When testing the real service, invoke `service.findStock(...)` on the real service with a test dependency at the proper boundary.

Example bounding the total wait duration of the check:

~~~java
StepVerifier.create(service.findStock("SKU-123"))
        .expectNextMatches(stock -> stock.available())
        .expectComplete()
        .verify(Duration.ofSeconds(3));
~~~

`verify(Duration)` prevents tests from waiting forever. It is a **test deadline**; it does not establish HTTP 504 semantics or alter the producer's timeout logic.

### Empty Mono and Error Are Two Different Outcomes

~~~java
StepVerifier.create(Mono.<StockResponse>empty())
        .verifyComplete();

StepVerifier.create(Mono.<StockResponse>error(
            new IllegalStateException("backend unavailable")))
        .expectError(IllegalStateException.class)
        .verify();
~~~

An empty-completing `Mono` may be translated by a controller into 404; an erroring `Mono` may become 5xx or be mapped by a handler into a structured error. Tests must distinguish **not found**, **upstream error**, and **upstream timeout** per the contract.

## 13. Virtual Time: Testing Long Durations Without Waiting in Real Time

Testing with `Thread.sleep(5_000)` slows down test suites and causes flakiness in CI. Reactor's `StepVerifier.withVirtualTime` lets you control **virtual time** for operators using compatible Reactor schedulers.

Example of a publisher that only emits after 30 minutes:

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofMinutes(30))
                .map(tick -> "READY")
    )
    .expectSubscription()
    .expectNoEvent(Duration.ofMinutes(29))
    .thenAwait(Duration.ofMinutes(1))
    .expectNext("READY")
    .verifyComplete();
~~~

This snippet runs quickly because the scheduler advances in virtual time **without sleeping 30 real minutes**. Create the publisher **inside the Supplier** passed to `withVirtualTime` so timers/operators capture the virtual scheduler properly.

### Testing Timeout When Upstream Never Signals

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

StepVerifier.withVirtualTime(
        () -> Mono.<String>never()
                .timeout(Duration.ofSeconds(3))
    )
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(3))
    .expectError(TimeoutException.class)
    .verify();
~~~

This test verifies the **Reactor timeout operator** emits an error when no signal arrives. It does not yet prove the HTTP layer returns status 504; corresponding service/handler/WebTestClient tests are still needed.

### Limits of Virtual Time

- Works only for time-based operations using **virtualizable schedulers** created at the right moment.
- Cannot automatically speed up **HTTP sockets**, databases, brokers, or blocking I/O libraries running on real wall-clock time.
- Timers created before the virtual scheduler is activated may still use the real scheduler.
- Do not run virtual-time tests recklessly in parallel if global scheduler configuration causes interference; control test setup carefully.
- `expectNoEvent` at the start of a chain must account for **subscription**; call `expectSubscription()` before asserting no signals.

**Rule:** use virtual time to test **Reactor timing logic**; use WebTestClient/integration tests to check **real HTTP contracts and serialization**.

## 14. Testing Timeouts with a Controllable Gateway

To test the production service against an unresponsive dependency, control the **gateway** rather than faking the controller or mocking the entire service.

Suppose `InventoryGateway` is a port:

~~~java
package com.example.inventory;

import reactor.core.publisher.Mono;

public interface InventoryGateway {
    Mono<StockResponse> lookup(String sku);
}
~~~

A unit test instantiates the real service and a test gateway returning a never-completing publisher:

~~~java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class InventoryServiceTimeoutTest {
    @Test
    void turnsUpstreamTimeoutIntoDomainError() {
        InventoryGateway silentGateway =
                sku -> Mono.<StockResponse>never();

        InventoryService service = new InventoryService(silentGateway);

        StepVerifier.withVirtualTime(
                () -> service.findStock("SKU-TIMEOUT")
            )
            .expectSubscription()
            .thenAwait(Duration.ofMillis(800))
            .expectError(InventoryTimeoutException.class)
            .verify();
    }
}
~~~

In this example, **`InventoryService` is the real production class**, so `timeout` and `onErrorMap` inside the service are genuinely tested. Only the gateway is **controlled** to withhold signals.

However, if `InventoryService.findStock(...)` creates a timer eagerly at call time rather than at subscription time, or uses an externally fixed scheduler, ensure the publisher/timer is constructed inside the Supplier when using virtual time. That is why the test uses `() -> service.findStock(...)` instead of creating the `Mono` beforehand.

Another HTTP contract test should send `SKU-TIMEOUT` through the **production controller + production service + error handler**, using a deterministic test gateway. That is the right seam; never mock the controller to return `504` directly, as that skips the timeout-handling logic the contract is meant to protect.

## 15. Reactive Blocking Tasks: Timeouts Do Not Fix Blocking Code

A reactive controller does not make a blocking operation non-blocking merely because the method returns `Mono`.

Example—**do not** call a blocking API directly on the event loop:

~~~java
@GetMapping("/blocking-example")
public Mono<String> endpoint() {
    String result = legacyClient.callBlocking(); // Blocks the processing thread
    return Mono.just(result);
}
~~~

If you must integrate a legacy blocking library, one isolation pattern is:

~~~java
@GetMapping("/bounded-elastic-example")
public Mono<String> endpoint() {
    return Mono.fromCallable(() -> legacyClient.callBlocking())
            .subscribeOn(reactor.core.scheduler.Schedulers.boundedElastic());
}
~~~

`boundedElastic` is a better place for unavoidable blocking tasks, yet it **does not replace the blocking library's own timeouts/cancellation** and does not give the app infinite resources. Prefer genuinely non-blocking drivers/clients whenever possible.

In testing:

- Never use `Thread.sleep` inside handlers/tests to "simulate reactive" and then conclude the application is non-blocking.
- Never call `block()` on production event loops; in certain boundary tests, bounded waiting can retrieve results, though it should not replace signal assertions.
- For blocking I/O, configure **the client/driver's own timeout** and verify error paths; Reactor timeout operates only at the Publisher layer.
- Separate real-time integration tests from Reactor virtual-time tests.

## 16. Cancellation and Cleanup When the Client Stops Waiting

A subscriber may cancel before upstream responds—for instance, when the client closes the connection or a `timeout` operator cuts off the chain.

A pure Reactor test can verify cancellation callbacks:

~~~java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

AtomicBoolean cancelled = new AtomicBoolean(false);

Mono<String> pending = Mono.<String>never()
        .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(pending)
        .expectSubscription()
        .thenCancel()
        .verify(Duration.ofSeconds(2));

org.assertj.core.api.Assertions
        .assertThat(cancelled.get())
        .isTrue();
~~~

This is a **unit test of the cancellation mechanism**, not proof that closing an HTTP connection cancels every real I/O operation. For database calls, brokers, or blocking libraries, verify the real driver's cancellation behavior whenever resource usage or cost is critical.

In applications with retries, cancellation matters even more: a request whose deadline has expired must not keep triggering retries or orphaned background work. However, if processing launched an **independent background job with an ID**, cancellation semantics may differ and must be designed explicitly.

## 17. Retry, Backoff, and Timeout: Choose Operator Order Deliberately

Reactive pipelines often combine operators like `timeout`, `retryWhen`, and `onErrorResume`. **Operator order changes meaning**.

Example:

~~~java
Mono<StockResponse> result = gateway.lookup("SKU-123")
        .timeout(Duration.ofMillis(300))
        .retryWhen(
            reactor.util.retry.Retry.backoff(
                2, Duration.ofMillis(100)
            )
        );
~~~

In this pipeline, the 300 ms timeout applies **per subscription/attempt** before retrying; total elapsed time can exceed 300 ms across multiple attempts and backoffs. If you want an overall deadline, enforce it at an appropriate outer boundary:

~~~java
Mono<StockResponse> result = gateway.lookup("SKU-123")
        .retryWhen(
            reactor.util.retry.Retry.backoff(
                2, Duration.ofMillis(100)
            )
        )
        .timeout(Duration.ofSeconds(1));
~~~

Both snippets above are **examples of operator ordering**, not complete retry strategies: `retryWhen` as written retries **all errors**, including non-retryable ones, unless filtered with `filter`. Real systems must restrict transient error types, retry counts, backoff/jitter, time budgets, and idempotency.

Tests should verify:

- How many times the gateway is invoked on retryable errors.
- That the total deadline does not exceed the committed threshold.
- That 4xx or validation errors are not retried unnecessarily.
- That fallbacks do not disguise timeouts as semantically wrong success responses.

If the consumer times out before the producer finishes retrying, the consumer may see a network error instead of the contract-promised HTTP status. Budgets must be designed consistently.

## 18. Asynchronous HTTP Is Not the Same as a Background Job Returning 202

Distinguish two models:

**Model A — HTTP request awaits the Mono result:**

~~~text
GET /api/inventory/SKU-123
    -> Mono queries data
    -> HTTP 200 when result arrives, or error/timeout when absent
~~~

Here contracts can describe 200/404/504 responses. The HTTP request stays open until the producer completes or terminates.

**Model B — HTTP accepts a request and starts a background task:**

~~~text
POST /api/reports
    -> HTTP 202 Accepted + {"jobId":"JOB-1001","status":"PENDING"}
    -> task runs later
GET /api/reports/JOB-1001
    -> 200 + {"status":"READY",...} upon completion
~~~

In Model B, `202 Accepted` **does not mean the task has finished**. Contracts must separate:

1. The job-creation API returning `202` with an ID and tracking link/path.
2. The job-status API (`pending/running/ready/failed`).
3. If there is a callback/message upon completion, a corresponding contract for that message or callback.

Never use a generated test receiving `202` to claim the entire background job succeeded. Testing job completion requires bounded waiting, verifying the final state, and post-test cleanup.

## 19. Polling and Eventual Completion Conditions

If a consumer must poll until a job becomes `READY`, never use a fixed sleep assuming data is ready:

~~~java
// Do not use this as a primary synchronization strategy:
Thread.sleep(2000);
// Querying status afterward; slow CI may still not be done.
~~~

An integration test can use **Awaitility** to wait until an eventual condition holds, with a clear deadline:

~~~java
import static org.awaitility.Awaitility.await;
import java.time.Duration;

// Illustrative: getStatus calls the real endpoint/API to read job status.
await()
    .atMost(Duration.ofSeconds(5))
    .pollInterval(Duration.ofMillis(100))
    .untilAsserted(() -> {
        org.assertj.core.api.Assertions.assertThat(
            reportClient.getStatus("JOB-1001")
        ).isEqualTo("READY");
    });
~~~

`reportClient.getStatus` here is a **hypothetical consumer test API**; if the client returns `Mono`, use an appropriate test integration mechanism and avoid calling `block()` on an event loop. Awaitility fits **integration boundaries** where state changes in real time, whereas `StepVerifier.withVirtualTime` fits **Reactor timer logic** whose scheduler can be controlled.

When polling, consider:

- Having an explicit **final timeout**.
- Choosing a sensible polling interval to avoid excessive load.
- Ensuring the job ID belongs solely to the current test, without ambiguous shared state.
- Cleaning up and logging the final state on failure.
- Separating `FAILED` status so tests stop polling needlessly.

## 20. Streaming Flux and SSE: Standard HTTP Contracts Are Not Enough

An endpoint may emit a stream:

~~~java
@GetMapping(
    path = "/api/stock/events",
    produces = org.springframework.http.MediaType.TEXT_EVENT_STREAM_VALUE
)
public reactor.core.publisher.Flux<StockEvent> events() {
    return eventService.stream();
}
~~~

For **Server-Sent Events (SSE)** or non-terminating `Flux`, the response is not a single complete JSON object like `GET /api/inventory/SKU-123`.

In this case:

- Standard HTTP contracts can describe applicable protocol parts, yet **do not automatically verify** event cadence, pause intervals, backpressure, cancellation, or infinite streams.
- `WebTestClient` tests can retrieve the body as a `Flux` and use `StepVerifier` to inspect the first few events and cancel intentionally.
- You must set a **bounded event count or time limit** when testing non-terminating streams.
- `text/event-stream` `Content-Type` and event encoding must be verified separately.
- If the producer changes event schemas, use suitable message/event contracts alongside consumer tests processing real events.

Illustrative idea for testing the first three events:

~~~java
Flux<StockEvent> events = client.get()
        .uri("/api/stock/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .returnResult(StockEvent.class)
        .getResponseBody();

StepVerifier.create(events)
        .expectNextCount(3)
        .thenCancel()
        .verify(Duration.ofSeconds(5));
~~~

This snippet assumes `client` is a configured `WebTestClient` and the endpoint emits at least three events within 5 seconds. Add assertions on **event contents** if consumers rely on them; merely counting events does not validate schemas.

If the stream never emits events, the test expires via `verify(Duration)` rather than hanging forever. Never call `verifyComplete()` on a stream intentionally designed not to complete.

## 21. Asynchronous Messaging Contracts: Trigger Real Production Paths

Spring Cloud Contract supports message contracts with triggers and output messages. For example, Inventory Service emits a stock event after processing:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'inventoryChanged'

    input {
        triggeredBy('triggerInventoryChanged()')
    }

    outputMessage {
        sentTo('inventory.events')
        body(
            eventType: 'InventoryChanged',
            sku: 'SKU-123',
            available: true,
            quantity: 12
        )
    }
}
~~~

In producer tests, `triggerInventoryChanged()` must be supplied by the base class/test support. **It should invoke the real production use case that emits the message**, rather than sending a sample JSON directly to a test sink to make the test pass.

Because output messages may arrive after a delay, configure:

- Suitable messaging test infrastructure: Spring Cloud Stream test binder, test broker, or adapter supported by your SCC version.
- Message reception conditions with a **finite timeout** instead of waiting forever.
- A way to correlate scenario events using keys/correlation IDs so tests never read another test's messages.
- Cleanup of subscriptions/consumers between tests.
- Evidence that generated tests actually observe messages emitted by production code.

A message contract with a valid body **does not automatically test** production brokers, delivery latency, duplicate handling, or retries. Those properties require dedicated messaging/integration tests and operational monitoring.

## 22. Stub Runner and When the Consumer Receives Slow Responses

Once the producer builds stubs, Checkout Service can run its real client against Stub Runner to check request/response contracts. However, **stubs normally return sample responses immediately**; that does not prove the consumer handles high latency properly.

You can design **two groups of consumer tests**:

| Group | Tool | What to verify |
|---|---|---|
| **Contract compatibility** | Stub Runner and candidate stubs generated by producer | Client sends requests and decodes status/headers/body/schema properly |
| **Resilience/latency** | WireMock delays/faults or controllable HTTP test server | Client applies timeouts, retries, fallbacks, and cancellation properly |

Example of a WireMock mapping **dedicated to a resilience test**, not a claim that SCC DSL generates delays automatically:

~~~java
import static com.github.tomakehurst.wiremock.client.WireMock.*;

stubFor(get(urlEqualTo("/api/inventory/SKU-SLOW"))
    .willReturn(aResponse()
        .withStatus(200)
        .withHeader("Content-Type", "application/json")
        .withBody("{\"sku\":\"SKU-SLOW\",\"available\":true,\"quantity\":1}")
        .withFixedDelay(2500)));
~~~

If the consumer is designed to time out after 1,500 ms, a request to a stub delayed by 2,500 ms must be tested to confirm the right error/fallback outcome. This is a **slow-response resilience test**, not a substitute for producer verification.

**Note:** `withFixedDelay` introduces **wall-clock** delays, suitable for a few integration tests but potentially slow/flaky in CI. Reserve it for the small set of tests checking real timeouts, with sufficient headroom and a stable environment. Internal rules should use `StepVerifier.withVirtualTime` whenever possible.

Do not modify the generated candidate stub JAR to inject delays and still treat it as the producer's original artifact. Keep contract artifacts and resilience stubs separate, documenting the purpose of each test type.

## 23. Setting Timeouts on the Consumer HTTP Client

A `WebClient` backed by Reactor Netty can configure a response timeout at the HTTP client layer:

~~~java
import java.time.Duration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

HttpClient httpClient = HttpClient.create()
        .responseTimeout(Duration.ofMillis(1500));

WebClient webClient = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .baseUrl("http://localhost:8081")
        .build();
~~~

`http://localhost:8081` is an illustrative URL where a stub/test server might listen, not a real environment address. With Stub Runner, pull the actual host/port from test configuration.

Distinguish carefully:

- `responseTimeout` in Reactor Netty has **network response read/response timeout** semantics, not necessarily an **overall end-to-end deadline**.
- `Mono.timeout(Duration)` on `WebClient.retrieve().bodyToMono(...)` enforces a publisher-layer deadline measured from subscription per Reactor semantics.
- **Connect timeout**, pool acquisition timeout, DNS resolution, and other phases have separate policies.
- If the client retries, clarify whether the timeout applies **per attempt** or to the **entire call**. Test against the real configuration, not isolated snippets.

Consumer tests should assert the **error type or business fallback** handled by the application. Avoid brittle assertions on internal Netty exception messages not part of the public API, as exact messages can vary across library versions.

## 24. A Timeout Does Not Equal Error 504

Frequently conflated situations:

| What happens | What the client/consumer observes | Is it HTTP 504 from the producer? |
|---|---|---|
| Producer catches upstream timeout and returns HTTP 504 JSON | Receives `504` response with error code | **Yes**, per contract |
| WebTestClient hits its own `responseTimeout` before producer responds | Test fails for lack of response | **No** |
| Consumer WebClient times out while waiting | Client receives error signal or fallback | **Not necessarily** |
| JUnit timeout aborts the test | Test runner reports deadline exceeded | **No** |
| CI job times out | Pipeline is cancelled | **No** |
| Producer returns 202 and processes job later | Client receives early `202` response | Not a timeout |

If the contract requires `504 INVENTORY_TIMEOUT`, verify that the producer **actually emits that HTTP response**. A test confirming only that the client timed out does not prove the producer implemented error mapping.

## 25. Layer Real-Time Tests and Virtual-Time Tests

Do not cram every timing property into one heavy end-to-end test.

| Test type | Example | Waiting mechanism | Goal |
|---|---|---|---|
| **Reactor unit test** | `timeout`, `retryWhen`, `doOnCancel` | `StepVerifier.withVirtualTime` when appropriate | Accurate timing logic and signals |
| **Service integration test** | Slow gateway or `Mono.never` | Virtual time if adapter supports it, or bounded wait | Service emits expected error/fallback |
| **HTTP producer test** | WebFlux controller + error handler | WebTestClient with generous `responseTimeout` | Status/headers/body match contract |
| **Generated SCC producer test** | Groovy/YAML → generated test | Per plugin/test mode, runner deadline | Producer fulfills contract |
| **Consumer contract test** | Stub Runner + real client | Bounded client test timeout | Request/response compatibility |
| **Resilience test** | WireMock fixed delay/fault | Controlled real time | Consumer tolerates latency/cancellation |
| **E2E/observability** | Broker, database, tracing | Wait bounds per SLO | Production-like interactions and ops |

A fast virtual-time test does not replace verifying **real I/O**; a real-time waiting HTTP test does not replace checking operators/retries with deterministic signals.

## 26. Preventing Flakiness in Asynchronous Tests

Practical guidelines:

1. **Never use fixed sleeps** to wait for events when you can await conditions or use virtual time.
2. **Do not set timeouts too close together**: test clients need enough headroom to receive business-timeout responses from the producer.
3. **Bound every wait**: `verify(Duration)`, `responseTimeout`, Awaitility `atMost`, JUnit/CI job timeouts.
4. **Isolate resources between tests**: correlation IDs, queues/topics, subscriptions, test DBs, schedulers.
5. **Do not rely on execution order**: publishers can emit at varying times; never assume global ordering across async flows.
6. **Avoid wall-clock dependencies when unnecessary**: inject `Clock`, use virtual schedulers, or use fixed fixtures.
7. **Never let tests spawn uncleaned background work**: cancellation and shutdown can matter more than happy-path results.
8. **Do not mask errors with infinite retries**: cap attempts, classify retryable errors, and guard deadlines.
9. **Log sufficient context**: request/contract ID, correlation ID, start/end timestamps, and timeout layer.
10. **Verify the real outcome actually occurred**: assert final signals, HTTP status/body, or observed messages—not merely "job submitted."

Under heavy CI load, do not blindly multiply timeouts by ten just to "make it green"; first classify whether it is **test flakiness**, **dependency slowness**, or a **producer latency regression**.

## 27. Common Errors and How to Diagnose Them

| Symptom | Possible cause | Resolution |
|---|---|---|
| StepVerifier test hangs | No completion/error or missing deadline | Use `verify(Duration)` and assert proper terminal signals |
| Test never triggers query | Publisher created without subscribing | Use StepVerifier/WebTestClient or controlled subscriber |
| Virtual time still takes seconds/minutes | Publisher/timer created outside supplier, non-virtualized scheduler, or real I/O | Build publisher inside supplier; separate real I/O integration tests |
| HTTP test times out instead of receiving 504 | Test client expires before producer sends error response | Adjust timeout budgets; test producer error mapping |
| Producer returns 500 instead of timeout contract | `TimeoutException` is unmapped | Check `onErrorMap`/`@RestControllerAdvice` and generated test |
| Test passes using base class `Mono.just(...)` | Producer behavior itself was mocked/faked | Route tests through production controller/service |
| Consumer test passes yet WebClient fails under slowness | Normal stub responds immediately | Add WireMock delay test and configure client timeout |
| Flux test never finishes | Intentionally non-terminating stream | Assert a few items then `thenCancel` |
| Retries push request past budget | Timeout placed inside retry or missing total deadline | Check operator order, attempt limits, total call timeout |
| CI flakes between green and red | Fixed sleep, shared resources, load/scheduler variance | Eventual conditions + deadlines, isolation, virtual time |
| Message test receives no event | Trigger bypasses production flow or wrong test binder/broker | Check trigger, destination, serialization, consumer subscription |
| Cancel does not stop blocking I/O | Driver/library lacks cooperative cancellation | Configure I/O timeouts, bound resources, test driver directly |
| Green build with zero generated tests | Plugin didn't find contracts or test task skipped | Check generated sources, test counts, and pipeline flags |
| Consumer uses stale stub | Version/cache not pointing to candidate artifact | Pin group/artifact/version/classifier and inspect mappings |

## 28. Integrating Reactive/Contract Gates into CI

~~~mermaid
flowchart TD
    A["PR changes WebFlux code, contract, or timeout"] --> B["StepVerifier / virtual-time unit tests"]
    B --> C{"Signals and deadlines correct?"}
    C -- "No" --> X["Block merge"]
    C -- "Yes" --> D["Generate and run SCC producer tests"]
    D --> E{"HTTP/message contract passes?"}
    E -- "No" --> X
    E -- "Yes" --> F["Package candidate stubs"]
    F --> G["Consumer tests via Stub Runner"]
    G --> H{"Client handles request/response?"}
    H -- "No" --> X
    H -- "Yes" --> I["Targeted resilience tests: delay/fault/cancel"]
    I --> J{"Pass?"}
    J -- "No" --> X
    J -- "Yes" --> K["Pass compatibility gate; proceed to release"]
~~~

Reference commands for projects with the SCC plugin integrated:

~~~bash
# Maven: generate, compile, run tests, and package per build configuration.
./mvnw clean verify

# Gradle: run generated tests if plugin is wired to the task properly.
./gradlew clean test
~~~

Task names, generated source paths, and artifact names may vary by version/plugin. On Windows, use the matching wrapper `mvnw.cmd` or `gradlew.bat`.

CI should record:

- Discovered contract names and **count of generated tests actually executed**.
- Versions of Spring Boot/Spring Cloud/Contract, JDK, and test mode.
- Reactor test results for critical timeout, retry, and cancellation cases.
- Failure stage/code when HTTP tests fail: app 504, client timeout, or runner timeout.
- Group, artifact, version, classifier, and commit of **candidate stubs**.
- Consumer test reports using the real client, avoiding stale production stubs.
- Classification between virtual-time and real-time tests to track stability.

Never declare a pipeline compatible based merely on a "green build" or a mock returning canned responses. Both producer and consumer must be verified with **real code inside the committed scope**.

## 29. Practice Lab: Three-Layer Timeouts

**Context:** Inventory Service exposes WebFlux API `GET /api/inventory/{sku}`; Checkout Service calls this endpoint. The service fetches data from a reactive gateway.

### Round A — Successful HTTP Contract

1. Write a Groovy or YAML contract for `SKU-123` returning `200` with `available:true` and `quantity:12`.
2. Create controller `Mono<ResponseEntity<StockResponse>>`.
3. Configure generated tests with the appropriate WebFlux test mode; base class invokes the real controller.
4. Run producer verification, inspect generated source and test reports.
5. Package the candidate stub and run Checkout client tests with Stub Runner.

**Expected result:** producer and consumer agree on the same JSON schema.

### Round B — Service-Layer Timeout

1. Put `timeout(Duration.ofMillis(800))` in the production service, mapping timeouts to `InventoryTimeoutException`.
2. Create a test gateway returning `Mono.never()` (this is an isolated dependency, not a faked service).
3. Use `StepVerifier.withVirtualTime` to verify the expected error type occurs after 800 virtual ms.
4. Use WebTestClient/integration tests to verify the error handler returns `504 INVENTORY_TIMEOUT`.
5. Write a dedicated HTTP contract for the timeout error with deterministic test data.

**Expected result:** clear distinction between "service raises timeout error" and "HTTP returns the committed error contract."

### Round C — Consumer with Its Own Deadline

1. Configure Checkout's WebClient with an appropriate response timeout.
2. Use the candidate stub to verify normal schema handling.
3. Add a separate WireMock delay test (e.g., 2.5 seconds) exceeding the 1.5-second client deadline.
4. Assert the client emits the proper error/fallback and does not retry infinitely.
5. Compare with the scenario where the producer itself returns 504; the two cases are not identical.

**Expected result:** consumer handles both public error responses and local transport/timeout errors.

### Round D — Non-Terminating Flux and Cleanup

1. Create a stock event stream `Flux<StockEvent>`.
2. Use WebTestClient to obtain the event `Flux` and `StepVerifier` to check a few elements.
3. Call `thenCancel` and confirm the test does not hang.
4. Verify cleanup/cancellation in the adapter if required.
5. Bring the checks from all rounds into CI.

**Submission evidence:** HTTP contracts, WebFlux service/controller code, generated producer test report, StepVerifier virtual-time test, WebTestClient 504 status test, candidate stub coordinates, consumer delay test, and cleanup logs.

## 30. Pre-Merge Checklist

- [ ] Reactive controller returns proper `Mono`/`Flux` and generated tests truly subscribe/call the implementation.
- [ ] HTTP contracts describe status/headers/body seen by consumers, not internal Reactor types.
- [ ] Upstream timeouts, client timeouts, test deadlines, and CI job timeouts are clearly separated.
- [ ] Business timeouts map to API-contract responses where required.
- [ ] Test client deadlines leave enough headroom to receive producer error responses without aborting early.
- [ ] StepVerifier tests cover critical completion, error, timeout, and cancellation cases.
- [ ] Virtual-time publishers/timers are created **inside the Supplier** so they pick up the virtual scheduler.
- [ ] Virtual time is never assumed to speed up real networks/brokers/blocking I/O.
- [ ] `Thread.sleep` is not used as a primary synchronization mechanism.
- [ ] Background 202 tasks have both job-creation contracts and status/completion tracking contracts as needed.
- [ ] Non-terminating Flux/SSE streams are tested with bounded event counts and `thenCancel`.
- [ ] Base tests do not mock out the controller/service logic protected by contracts.
- [ ] Messaging contracts go through production triggers, with finite waits and event correlation.
- [ ] Stub Runner uses candidate artifacts and is not assumed to simulate real latency by default.
- [ ] Consumers have separate delay/transport-timeout and fallback tests.
- [ ] CI confirms generated test count > 0, records versions/commits, and classifies timeout errors clearly.

## 31. Self-Check Questions

**1. Why does creating a `Mono` without subscribing fail to prove the task ran?**

Because many Reactor publishers are **lazy**; building the chain does not execute upstream I/O. `StepVerifier` or an HTTP test subscribes and verifies real signals.

**2. How do `WebTestClient.responseTimeout` and `Mono.timeout` differ?**

The former limits how long **the test client waits for an HTTP response**; the latter is a reactive pipeline operator that can emit `TimeoutException`. The producer returns HTTP 504 only when the application/error handler maps that error to a response per the contract.

**3. Does virtual time speed up an HTTP request slowed by real networking?**

No. Virtual time only controls compatible Reactor schedulers/timers; real sockets, brokers, and blocking I/O still run on wall-clock time.

**4. Why must the publisher be created inside `withVirtualTime`'s Supplier?**

So operators use the virtual scheduler installed when StepVerifier creates the subscription. Timers created outside may capture the real scheduler and make the test wait in real time.

**5. Should an infinite SSE stream be tested with `verifyComplete()`?**

No, if the stream is designed never to end. Assert the needed items and then `thenCancel` with an explicit test deadline.

**6. When Stub Runner responds immediately, what does that prove and what does it leave unproven?**

It proves the consumer client sends valid requests and decodes sample status/headers/body/schema. It does not prove the client handles latency, timeouts, network errors, or task cancellation properly; separate resilience tests are required.

**7. Why does placing a timeout before vs. after retry change the outcome?**

A timeout inside a retried chain applies **per attempt**, allowing total time to grow across retries. An outer timeout caps the entire retry sequence; choose based on SLOs and test the exact operator order.

## 32. References

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/): Contract Verifier, HTTP/message contracts, generated tests, and Stub Runner.
- [Spring Cloud Contract – Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): Groovy/YAML DSL and matchers.
- [Spring Framework – WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): WebFlux HTTP testing, client timeouts, and streaming.
- [Spring Framework – WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): reactive HTTP processing model.
- [Project Reactor – Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, virtual time, and test publishers.
- [Reactor Core API](https://projectreactor.io/docs/core/release/api/): `Mono.timeout`, `Flux.timeout`, `retryWhen`, and cancellation.
- [Reactor Netty Reference](https://projectreactor.io/docs/netty/release/reference/): HTTP client timeouts and connections.
- [WireMock Documentation](https://wiremock.org/docs/simulating-faults/): delayed responses and network faults in consumer resilience tests.

**Version note:** Contract Verifier's WebTestClient test mode, Spring Boot annotations, client binding APIs, and timeout options may vary by version. Always verify against the documentation for the exact Spring Boot–Spring Cloud Release Train–Spring Cloud Contract combination used by your project and inspect actual generated sources. Code snippets in this lesson are educational examples, **not output from a live executed build**.

---

**Key takeaway:** In reactive testing, separate **HTTP/message contracts**, **`Mono`/`Flux` signals**, and **per-layer deadlines**. Use Contract Verifier to check the producer, `StepVerifier`/virtual time to test asynchronous logic, WebTestClient to check real HTTP, and Stub Runner plus resilience tests to protect consumers. Every test needs a subscription, a finite deadline, and proof it actually executed; that enables CI to catch incompatible API changes without turning waits into flaky tests.
