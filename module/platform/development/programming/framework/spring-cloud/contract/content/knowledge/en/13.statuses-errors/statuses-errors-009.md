# Slow Responses, Simulated Network Faults, and Consumer Test Scope

## Learning Objectives

In the **Statuses and Errors** chapter of **Spring Cloud Contract**, you have seen that an API returns more than just success responses. Beyond HTTP error codes such as `400`, `404`, or `503`, consumers can also encounter **overly slow responses**, **lost connections**, **TCP resets**, or **incomplete HTTP responses**.

Spring Cloud Contract uses **Groovy/YAML DSL** to describe agreed communication behaviors, generating **producer contract tests** and **stubs** for consumers to run with **Stub Runner**. However, it is vital to define **the scope of guarantees** accurately: HTTP contract testing and consumer network-resilience testing are related yet not identical.

After this lesson, you will be able to:

- Distinguish **HTTP error responses**, **client-side timeouts**, **connection failures**, and **network faults**.
- Design contracts for the HTTP error responses the consumer genuinely depends on.
- Use **WireMock** to simulate slow responses or broken connections in consumer tests without mistaking that for testing the real producer.
- Configure and verify timeouts, retries, fallbacks, and circuit breakers within the right scope.
- Identify when Stub Runner suffices and when supplementary testing is required.
- Build a consumer test matrix that runs reliably in CI and detects incompatible API changes.

## 1. Practical Scenario: Checkout Calls Inventory

Suppose:

- **Inventory Service** is the **producer**, exposing `GET /api/inventory/{sku}`.
- **Checkout Service** is the **consumer**, calling this endpoint right before a user confirms an order.
- When Inventory operates normally, the API returns stock data in JSON.
- When Inventory is overloaded, connections between the two services can stall or drop.

A successful interaction:

~~~http
GET /api/inventory/SKU-101 HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sku": "SKU-101",
  "available": true,
  "quantity": 8
}
~~~

Checkout needs to know **when it can rely on the stock result** and **when it should halt the operation, display an unknown state, or retry**. Never assume "cannot reach Inventory" means `available=false`: getting no response does not prove stock is out.

### Four Outcome Groups to Separate

| Group | Example | Does Consumer Get an HTTP Status? | Meaning |
|---|---|---|---|
| Valid response | `200 OK` + stock JSON | Yes | Producer returns result per contract |
| HTTP error response | `404`, `429`, `503` + API body/headers | **Yes** | Server or gateway sent an HTTP response |
| Overly slow response | Server delays 2 seconds, client caps at 300 ms | Possibly **no** if client times out first | Client stops waiting; server may still be processing |
| Connection/transport failure | Connection refused, reset, DNS/TLS failure | Usually **no** valid HTTP response | Failure happened before or during data exchange |

A key point: **HTTP `408 Request Timeout` or `504 Gateway Timeout` are HTTP statuses returned by a component**. They are **not identical** to timeout exceptions raised by the HTTP client itself. To test `504`-handling logic, a stub can return `504`; to test the client running out of wait time, create a delay or condition that triggers the timeout.

## 2. Distinguishing Protocol Errors from Network Errors

Ask: *did the consumer receive a complete HTTP response or not?*

~~~mermaid
flowchart TD
    A["Consumer calls producer"] --> B{"Complete HTTP response received?"}
    B -->|Yes| C{"What is the status?"}
    C -->|2xx| D["Handle success per contract"]
    C -->|4xx| E["Handle request/resource-state error"]
    C -->|5xx| F["Handle server/gateway error per policy"]
    B -->|No| G{"What happened?"}
    G -->|Wait deadline exceeded| H["Client-side timeout"]
    G -->|Cannot connect| I["Connect/DNS/TLS failure"]
    G -->|Connection dropped| J["Reset / incomplete response"]
~~~

### HTTP Error Response

The producer can proactively publish:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json
Retry-After: 2

{
  "code": "INVENTORY_TEMPORARILY_UNAVAILABLE",
  "message": "Inventory is temporarily unavailable"
}
~~~

The consumer receives **status, headers, and body**. This behavior can be written explicitly in Spring Cloud Contract so generated producer tests verify it and Stub Runner simulates it.

`Retry-After: 2` in the example suggests waiting 2 seconds before resending. This header can use delay-seconds or an HTTP-date per protocol; whether to retry, maximum attempts, and total time budget remain up to the consumer and application policy.

### Client-Side Timeout

The producer responds successfully after 1,500 ms, yet the consumer allows a request at most 250 ms. In that case, **the consumer may throw a timeout exception before the response arrives**. Tests should not expect status `200` or `503` because the client may never have received an HTTP response.

### Connection Failures

**Connection refused** typically happens when no process is listening at the address/port. **Connection reset** typically happens after a connection is established and then abruptly closed; the error may occur while sending the request or reading the response. DNS/TLS failures occur at distinct stages as well.

Do not catch every exception and label it "service returned 503." Application-level error normalization may group them under an external dependency error category, yet logs/telemetry and retry policies must preserve the underlying cause.

## 3. Distinguishing Timeout Types in the Consumer

| Timeout Type | What Does It Bound? | Suitable Test Approach |
|---|---|---|
| **Connection timeout** | Time to establish TCP connection (and corresponding client config) | Unreachable network/destination conditions; do not use server `fixedDelay` alone to infer connect timeout |
| **Response/read timeout** | Time waiting for data or between read packets, depending on HTTP library | WireMock delayed response, or slow data streaming scenario |
| **Request/overall timeout** | Total budget for a request or operation sequence per client | Configure overall timeout and simulate prolonged execution |
| **Circuit-breaker time limiter** | Time limit on a guarded call at the application layer | Test limit config and cancellation/fallback state |

Different Java libraries compute read timeouts and total durations differently. For example, `HttpClient`, `RestClient`, `WebClient`, Feign, and underlying HTTP clients each have distinct configuration APIs. **Do not call every timeout a "read timeout"** without verifying which timeout is actually configured.

Suppose Checkout has an overall budget of 800 ms to respond to the user. If each attempt has a 700 ms timeout and the retry policy allows three more tries with backoff, total latency can far exceed 800 ms. Therefore, design an **end-to-end budget**, not just independent per-call timeouts.

> Distinguish "caller stopped waiting" from "producer cancelled processing." A client timeout **does not prove** the server stopped working. For operations with side effects, retrying without idempotency can create duplicate transactions.

## 4. Spring Cloud Contract for HTTP 503

Suppose Inventory has a behavior **genuinely agreed upon by both teams**: when temporarily unable to serve, the API returns `503`, a stable error code, and a `Retry-After` header.

In a producer project configured with Spring Cloud Contract, you can write `src/test/resources/contracts/inventory/serviceUnavailable.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Inventory is temporarily unavailable'

    request {
        method 'GET'
        url '/api/inventory/SKU-UNAVAILABLE'
        headers {
            accept(applicationJson())
        }
    }

    response {
        status 503
        headers {
            contentType(applicationJson())
            header('Retry-After', '2')
        }
        body(
            code: 'INVENTORY_TEMPORARILY_UNAVAILABLE',
            message: 'Inventory is temporarily unavailable'
        )
    }
}
~~~

Meaning:

- `request` describes the scenario to identify.
- `response.status 503` is an **HTTP error status**, not a network exception.
- `Retry-After` is the header committed by the producer in this scenario.
- `code` is the machine-readable code for consumer branching; `message` should only be constrained verbatim if the API commits to exact wording.

**Note when running producer tests:** `SKU-UNAVAILABLE` is only an illustrative scenario key. The producer test must **arrange the error state** for this branch using a fake dependency, test state, or controlled simulation mechanism. Never put "if SKU contains UNAVAILABLE then return 503" into production business logic just to make tests easy.

### Equivalent YAML DSL

You can choose YAML instead of Groovy, e.g., `serviceUnavailable.yml`:

~~~yaml
description: 'Inventory is temporarily unavailable'
request:
  method: GET
  url: '/api/inventory/SKU-UNAVAILABLE'
  headers:
    Accept: 'application/json'
response:
  status: 503
  headers:
    Content-Type: 'application/json'
    Retry-After: '2'
  body:
    code: 'INVENTORY_TEMPORARILY_UNAVAILABLE'
    message: 'Inventory is temporarily unavailable'
~~~

In YAML, quoting `'2'` expresses a **text header value**. This is an **alternative syntax**; do not keep both files in the same build for the same scenario if they generate duplicate mappings.

This contract is suited for verifying **whether the producer returns the right 503/headers/body when the error condition is arranged**, and for letting the consumer test **503**-handling logic. It **does not yet verify** reset connections, silent servers, or consumer timeouts.

## 5. Stub Runner: Verifying Consumer Handling of HTTP Error Responses

In a standard Spring Cloud Contract pipeline:

1. Producer maintains Groovy/YAML DSL and runs **generated contract tests**.
2. Once producer tests pass, the build creates/publishes a **stub artifact**.
3. Consumer uses **Spring Cloud Contract Stub Runner** to run the right version of the stub.
4. Consumer tests invoke **the application's real HTTP client** pointed at the stub port and verify behavior.

Example skeleton for a consumer using Spring Boot and JUnit 5:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest(properties = {
    "inventory.base-url=http://localhost:10000"
})
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.0.0:stubs:10000",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class InventoryUnavailableConsumerTest {

    @Test
    void handlesHttp503WithoutTreatingItAsOutOfStock() {
        // Call Checkout's real InventoryClient/Gateway.
        // Request /api/inventory/SKU-UNAVAILABLE.
        // Assert app reports "unable to verify stock",
        // without setting available=false as if out of stock.
        // If client reads Retry-After, assert related policy.
    }
}
~~~

This is an **illustrative skeleton**: client classes, injection, assertions, and the `inventory.base-url` property must be adapted to your real application code. The example uses `LOCAL` mode, so `com.example:inventory-producer:1.0.0:stubs` must exist in the test environment's local Maven repository. In CI, use a properly configured repository instead of assuming local cache availability.

When running consumer tests against the `503` stub, verify:

- The client **does not** treat the HTTP response as success just because the server returned a JSON body.
- Policy classifies `503` differently from `404` and `400`.
- The UI or workflow does not draw false conclusions like "out of stock" when inventory data could not be confirmed.
- If retries are configured, behavior follows the designed policy (attempt cap, backoff, total time budget).
- Headers or error codes the consumer genuinely relies on are preserved accurately.

**Never use Stub Runner consumer tests as a substitute for generated producer tests.** Stubs can return DSL responses even if real producer code has not implemented them properly.

## 6. Why Network Failures Are Not Just an HTTP Contract

Spring Cloud Contract excels at **interfaces describable via request and response**, including status, headers, bodies, and matchers. Failures at the TCP, DNS, TLS layers or client-initiated timeouts may **never produce a complete HTTP response**.

For example:

| Scenario | Representable as a Normal HTTP Response? | Testing Suggestion |
|---|---|---|
| Producer returns `503` with JSON | Yes | Spring Cloud Contract DSL + Stub Runner |
| Gateway returns `504` | Yes, if published at the consumer boundary | HTTP stub returning `504`, verify consumer logic |
| Server stalls very long then returns `200` | Has a response, yet **latency** is an extra behavior | WireMock fixed delay and client timeout |
| TCP connection reset before response | No valid HTTP response to express as normal status/body | WireMock fault injection or transport tests |
| DNS fails to resolve | No | Suitable network test environment / fake transport |
| TLS handshake fails | No | Integration test with specific TLS config |
| Client skips call because circuit breaker is open | No HTTP call reaches producer | Application-layer resilience tests |

**Practical rule:** use contracts to guard committed HTTP behavior; use **fault-injection tests** to guard how the consumer copes with operational failures. The two test groups serve different purposes and must complement each other.

Do not assume a Groovy/YAML contract file containing `status: 503` will create a network timeout. Nor should you assume every **WireMock** option is passed verbatim from Spring Cloud Contract DSL to stub mappings; check your version's support and inspect **the actual generated mappings**.

## 7. Using WireMock to Simulate Slow Responses

**WireMock** is the HTTP stubbing tool used in the Spring Cloud Contract ecosystem. Beyond response status/body, WireMock can simulate **latency** to test consumer timeouts.

### Mapping JSON: Fixed Delay

Illustrative mapping for `GET /api/inventory/SKU-SLOW`:

~~~json
{
  "request": {
    "method": "GET",
    "url": "/api/inventory/SKU-SLOW"
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "sku": "SKU-SLOW",
      "available": true,
      "quantity": 8
    },
    "fixedDelayMilliseconds": 1500
  }
}
~~~

`fixedDelayMilliseconds: 1500` instructs WireMock to **delay returning the response by roughly 1,500 ms**. If the consumer has a 200 ms request timeout, the test can exercise the timeout branch.

This is a **handwritten WireMock mapping to illustrate fault/latency testing**, not a claim that Spring Cloud Contract auto-generates that delay field from standard Groovy/YAML DSL. You can run a separate WireMock test server, or inject extra mappings into stub tests **if** your project supports it without mapping collisions.

### Java Example with WireMockServer

Suppose the consumer test already includes a WireMock dependency compatible with your Spring Boot and Java versions. This example uses JUnit 5 and JDK `HttpClient` to demonstrate an HTTP request timing out before receiving a response:

~~~java
import com.github.tomakehurst.wiremock.WireMockServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.time.Duration;

import static com.github.tomakehurst.wiremock.client.WireMock.*;
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.options;
import static org.junit.jupiter.api.Assertions.assertThrows;

class InventoryTimeoutTransportTest {

    private WireMockServer wireMock;

    @BeforeEach
    void startServer() {
        wireMock = new WireMockServer(options().dynamicPort());
        wireMock.start();
    }

    @AfterEach
    void stopServer() {
        if (wireMock != null) {
            wireMock.stop();
        }
    }

    @Test
    void clientTimesOutBeforeSlowResponse() {
        wireMock.stubFor(get(urlEqualTo("/api/inventory/SKU-SLOW"))
            .willReturn(aResponse()
                .withStatus(200)
                .withHeader("Content-Type", "application/json")
                .withBody("{\"sku\":\"SKU-SLOW\",\"available\":true,\"quantity\":8}")
                .withFixedDelay(1500)));

        HttpClient httpClient = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(wireMock.baseUrl() + "/api/inventory/SKU-SLOW"))
            .timeout(Duration.ofMillis(200))
            .GET()
            .build();

        assertThrows(HttpTimeoutException.class, () ->
            httpClient.send(request, HttpResponse.BodyHandlers.ofString()));
    }
}
~~~

**This test illustrates JDK HttpClient transport timeout**, not full Checkout logic verification. In your project, point the **real `InventoryClient`** at `wireMock.baseUrl()` and assert application-layer outcomes: returning an unknown state, showing the right message, halting the workflow, or triggering fallback per policy.

When a test measures real elapsed time, the OS/CI scheduler can introduce jitter. Leave a generous gap between the timeout and fake delay, and avoid asserting exact millisecond timings; timing-sensitive tests should be designed to minimize flakiness. For retries/backoff, prefer virtual clocks or controllable schedulers where technology permits.

### Delays Do Not Simulate Every Fault

WireMock's `fixedDelayMilliseconds` is well suited to testing **a client waiting too long for a response**. It **does not simulate a connection timeout**, because the WireMock server is still listening and accepts the TCP connection immediately. To test connect timeouts, use matching network/transport conditions (such as a proxy, simulated network, or fake connector), rather than using fixed-delay results to claim connect timeout policy was tested.

## 8. Using WireMock to Simulate Connection Resets

WireMock provides **fault injection** to produce failures other than normal HTTP responses. Illustrative mapping:

~~~json
{
  "request": {
    "method": "GET",
    "url": "/api/inventory/SKU-RESET"
  },
  "response": {
    "fault": "CONNECTION_RESET_BY_PEER"
  }
}
~~~

When the consumer calls that endpoint, WireMock attempts to simulate **peer connection reset**. Depending on the HTTP client, OS, and protocol, the test may observe `IOException`, a specific I/O error, or a client-library wrapper exception. **Do not assume every client always throws the exact same exception class or message.**

With WireMock's Java DSL, you can configure:

~~~java
wireMock.stubFor(get(urlEqualTo("/api/inventory/SKU-RESET"))
    .willReturn(aResponse()
        .withFault(Fault.CONNECTION_RESET_BY_PEER)));
~~~

`Fault` here is `com.github.tomakehurst.wiremock.http.Fault`. Real tests should assert **application behavior** (such as an "unable to verify stock" status) rather than matching JDK I/O error messages verbatim.

### Other WireMock Faults

Commonly used fault modes in WireMock include:

| Fault | Simulated Meaning | Notes |
|---|---|---|
| `CONNECTION_RESET_BY_PEER` | Connection was reset | Specific exception depends on client/OS |
| `EMPTY_RESPONSE` | Peer closed connection without returning a normal HTTP response | Not equivalent to HTTP `204 No Content` |
| `MALFORMED_RESPONSE_CHUNK` | Corrupted chunked response data | Tests how HTTP parser handles framing errors |
| `RANDOM_DATA_THEN_CLOSE` | Sends invalid non-HTTP data then closes connection | Verifies protocol/transport error handling |

You do not need to include all four faults in every test suite. Pick failures plausible in your architecture that protect **distinct consumer behaviors**.

An `EMPTY_RESPONSE` or connection reset is **not the same** as `HTTP 200` with an empty body `""`, `HTTP 204`, or `HTTP 503`. If consumer code collapses them into one branch, ensure that is an intentional business decision.

## 9. Scope of Consumer Tests: What Should Be Verified?

Consumer testing should confirm **the consumer's own client and application logic** when external dependencies behave normally or fail.

| Behavior to Verify | Appropriate Test Type | Key Assertions |
|---|---|---|
| Deserialize `200` response per contract | Stub Runner with generated stubs | Reads `sku`, `available`, `quantity` with right types and semantics |
| Handle `400`/`404`/`503` with error bodies | Stub Runner with error contracts | Branches properly on status, error code, headers |
| Timeout on slow server response | WireMock delay or fake transport | Consumer stops waiting per policy, does not mistake for `available=false` |
| Connection reset / empty response | WireMock fault | Consumer recovers/displays error properly; does not pretend a response arrived |
| Retry/backoff | Call-count scenario fault stub, fake clock if possible | Bounded attempt count, no duplicate side effects |
| Circuit breaker opens after failures | Resilience test with fake dependency and controllable clock | Once threshold hit, subsequent calls skip the network |
| User impact | Service/controller/UI tests | Clearly reports "cannot check stock yet," avoids wrong conclusions |
| Real producer returns right `503` | Generated producer contract test | Producer status/headers/body match contract |
| DNS/TLS, proxy, service mesh | Integration/network tests | Behavior with real or suitably simulated network infrastructure |

**Out of scope** is proving end-to-end producer correctness using consumer tests alone: when consumer tests run against stubs, they never call the real producer. Likewise, WireMock tests cannot prove production networks never fail.

### Example Checkout Behavior When Inventory Is Lost

Suppose Checkout has three states:

- `IN_STOCK`: API returns `200` and `available=true`.
- `OUT_OF_STOCK`: API returns `200` and `available=false`.
- `UNKNOWN`: timeout, reset, or infrastructure failure leaves inventory unverified.

A safe UI fallback can show "Unable to check stock right now, please try again" for `UNKNOWN`, rather than inferring `OUT_OF_STOCK`. Depending on business rules, checkout payment may be blocked until re-verified. This is an **illustrative business decision** that should be agreed upon with product owners.

## 10. Retries, Backoff, Idempotency, and Circuit Breakers

### Retries Must Be Bounded

Not every error should be retried automatically:

| Case | Decision Hint |
|---|---|
| `400 Bad Request` due to invalid data | Usually do not retry unmodified request |
| `404 Not Found` for non-existent resource | Usually do not retry indefinitely; check eventual-consistency policy if any |
| `429 Too Many Requests` | May retry per `Retry-After` and quota policy |
| `503 Service Unavailable` | May retry in a controlled manner, preferring backoff/jitter |
| Client timeout on `GET` | May retry if budget remains and request is idempotent |
| Timeout on `POST` creating transaction | **Risk of duplicate side effects**; requires idempotency key/deduplication or status-check workflow |
| Connection reset | Outcome before reset may be unknown | Never assume the operation definitely did not execute |

### Idempotency Matters More Than Retry Counts

Suppose Checkout calls `POST /api/reservations` to hold inventory, the server **already persisted it**, yet the connection resets before the consumer receives the response. If the consumer retries without duplicate-detection mechanisms, the system may reserve inventory twice.

For operations with side effects, consider an **idempotency key** published and handled by the producer, or a status re-query mechanism. Contracts can describe headers/bodies and responses for duplicate keys; however, full idempotency verification usually requires multi-call business-state tests rather than a single request/response contract.

### Circuit Breaker

A circuit breaker can open after repeated failures and temporarily stop calling the dependency. Consumer tests should distinguish:

1. When the breaker is **closed**, requests go out.
2. After meeting failure thresholds, the breaker transitions to **open**.
3. While **open**, subsequent calls fail fast **with no HTTP request sent to the stub**.
4. When entering recovery per configuration, trial calls are controlled.

Testing the circuit breaker's state machine depends on your resilience library (such as Resilience4j) and actual configuration. Do not assume Spring Cloud Contract or Stub Runner provides breaker logic themselves; they are primarily communication verification tools.

## 11. Designing Stable Tests, Avoiding "Flaky" Runs in CI

### Recommended Scenario Matrix

| ID | How Scenario Is Created | Consumer Expectation | Tool |
|---|---|---|---|
| `OK` | `200` + valid JSON | Handles stock properly | Spring Cloud Contract stub |
| `NOT_FOUND` | `404` + error code | Distinguishes non-existent SKU | Spring Cloud Contract stub |
| `UNAVAILABLE` | `503` + error code, `Retry-After` if committed | Reports temporary unavailability, retries per policy | Spring Cloud Contract stub |
| `SLOW` | `200` delayed past client timeout | Takes timeout branch, does not conclude out of stock | WireMock delay |
| `RESET` | TCP reset | Connection-error/fallback branch | WireMock fault |
| `EMPTY_RESPONSE` | Close connection with no HTTP response | Not mistaken for HTTP 204 | WireMock fault |
| `RETRY_BOUND` | Fail then succeed within bounded scenario | Right attempt count and wait intervals | Stateful stub / fake dependency |
| `BREAKER_OPEN` | Trip circuit breaker | No requests sent while open | Application-layer resilience test |

This is a **suggested matrix**, not a requirement for every project to implement identically. Pick the subset that delivers value for your business flows and real risks.

### Principles to Reduce Flakiness

1. Use **dynamic ports** for WireMock when multiple tests run in parallel; avoid fixed-port collisions.
2. Make request paths/headers/bodies **clearly distinct** across mappings; avoid two mappings matching the same request with different outcomes.
3. For timeout tests, set **delay visibly larger than timeout**, while keeping total CI duration reasonable.
4. For retries/backoff, use a **fake clock**, virtual scheduler, or controllable time utilities when the library allows, instead of excessive `Thread.sleep`.
5. Reset mappings and request journal/stub state between tests whenever they might affect one another.
6. Use **pinned stub versions**, avoiding stale artifacts from local Maven caches or `latest` tags.
7. Assert stable application behavior and error categories rather than matching OS-specific exception messages verbatim.
8. Never assert millisecond-exact timeout thresholds in shared-resource CI environments.

### Common Mistakes

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Slow test still receives `200` | Client timeout unconfigured or set too high | Inspect actual HTTP client timeout, not just app config |
| "Connection timeout" test only waits for server response | Used `fixedDelay` after connection already succeeded | Arrange a genuine connect-failure condition |
| Consumer gets `404` from WireMock despite expecting `503` | Request did not match mapping or wrong stub version | Inspect unmatched request logs and loaded mappings |
| Reset test occasionally raises a different exception | OS/client/JDK handle TCP differently | Assert application behavior, do not lock message text |
| Retries create multiple reservations | POST lacks idempotency | Add duplicate-request protection and state tests |
| CI stays green even though producer changed error body | Consumer running against stale stub | Pin and log stub artifact version/commit |
| 503 test passes yet consumer still crashes on network drop | HTTP error differs from network exception | Add dedicated fault tests |

## 12. Hands-On Exercise: Picking the Right Test for Each Requirement

### Problem Statement

Checkout configures a total wait timeout of **400 ms** when calling Inventory. Product defines three requirements:

1. If Inventory returns `503` with `code=INVENTORY_TEMPORARILY_UNAVAILABLE`, Checkout displays "Inventory temporarily busy."
2. If Inventory responds `200` after **1,200 ms**, Checkout stops waiting and displays "Unable to verify yet."
3. If TCP resets, Checkout must neither treat items as out of stock nor loop indefinitely.

A colleague only wrote this contract:

~~~yaml
description: 'Inventory unavailable'
request:
  method: GET
  url: '/api/inventory/SKU-UNAVAILABLE'
response:
  status: 503
  headers:
    Content-Type: 'application/json'
  body:
    code: 'INVENTORY_TEMPORARILY_UNAVAILABLE'
~~~

Answer the following:

**Question 1. Which requirement does the contract above protect?**

It describes **HTTP `503`** and the error code, so it underpins requirement (1) when generated producer tests and corresponding consumer tests run. It does **not** create slow servers or TCP resets on its own.

**Question 2. Which tool should be used for requirement (2)?**

Use WireMock with a `fixedDelayMilliseconds` sufficiently larger than 400 ms, or a suitable fake transport. Checkout's real client must have timeouts configured; assert the `UNKNOWN`/"Unable to verify yet" branch rather than strict wall-clock timing in CI.

**Question 3. Which tool should be used for requirement (3)?**

Use WireMock `CONNECTION_RESET_BY_PEER` or an equivalent transport simulation tool. Assert proper fallback and bounded retry counts without coupling to a specific HTTP client version's exception class name.

**Question 4. If the endpoint changes to `POST /api/reservations` with side effects, what changes?**

You must consider idempotency, the risk that the server processed the request even though the client received no response, and duplicate-prevention rules. Never apply `GET` retry logic mechanically to `POST`.

**Question 5. Why does a `503` test with Stub Runner still require producer tests?**

Because Stub Runner uses **simulated stubs** generated from contracts; it does not confirm the real producer code returns `503`, headers, and body under the designed error conditions. Generated producer tests verify that side.

### Self-Check Questions

- What is the difference between HTTP `504` and a client-triggered timeout?
- Why does `fixedDelayMilliseconds` not test a connect timeout?
- How does `EMPTY_RESPONSE` differ from `204 No Content`?
- When a connection drops during a `POST`, why can't you always know whether the transaction succeeded?
- Can a consumer test using Stub Runner verify retry/circuit-breaker logic? How must stubs and time be arranged?
- Why are green producer and consumer builds still insufficient if they use two different contract/stub revisions?

## 13. Takeaways

**Do not conflate HTTP error responses with network failures.** With Spring Cloud Contract, use Groovy/YAML DSL to define the status/headers/body committed by the producer, generate producer tests, and publish stubs for consumers to test with Stub Runner. When you need to test the consumer under **slow responses, connection resets, timeouts, retries, or circuit breakers**, supplement with WireMock fault/delay tests or appropriate resilience tools.

A trustworthy test suite verifies **consumer behavior under uncertainty**—never turning a timeout into "out of stock"—while managing stub versions and testing both sides in CI. Contract tests protect the described interface; fault-injection and integration tests protect operational boundaries that single contracts do not cover.
